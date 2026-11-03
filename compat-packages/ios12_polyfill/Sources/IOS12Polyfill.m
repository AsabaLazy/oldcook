#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <objc/runtime.h>
#import <unistd.h>

// Runtime shim active ONLY prior to iOS 13.0.
// Prevents unrecognized-selector crashes when Flutter/Impeller or plugins call iOS 13+ APIs.

#define OC_IMP(fn) ((IMP)(void (*)(void))(fn))

@protocol OCIOS12MTLDeviceLegacy <NSObject>
- (BOOL)supportsFeatureSet:(NSUInteger)featureSet;
@end

@protocol OCIOS12PHPhotoLibraryLegacy <NSObject>
+ (NSInteger)authorizationStatus;
+ (void)requestAuthorization:(void (^)(NSInteger status))handler;
@end

@interface OCIOS12StatusBarManagerProxy : NSObject
@end

@implementation OCIOS12StatusBarManagerProxy
+ (instancetype)sharedProxy {
  static OCIOS12StatusBarManagerProxy *inst = nil;
  static dispatch_once_t onceToken;
  dispatch_once(&onceToken, ^{
    inst = [[OCIOS12StatusBarManagerProxy alloc] init];
  });
  return inst;
}
- (CGRect)statusBarFrame {
  return [UIApplication sharedApplication].statusBarFrame;
}
- (BOOL)isStatusBarHidden {
  return [UIApplication sharedApplication].statusBarHidden;
}
- (UIStatusBarStyle)statusBarStyle {
  return [UIApplication sharedApplication].statusBarStyle;
}
@end

@interface OCIOS12WindowSceneProxy : NSObject
@property(nonatomic, weak) UIWindow *targetWindow;
@end

@implementation OCIOS12WindowSceneProxy
+ (instancetype)sharedProxy {
  static OCIOS12WindowSceneProxy *inst = nil;
  static dispatch_once_t onceToken;
  dispatch_once(&onceToken, ^{
    inst = [[OCIOS12WindowSceneProxy alloc] init];
  });
  return inst;
}
- (UIScreen *)screen {
  UIWindow *w = self.targetWindow ?: [UIApplication sharedApplication].keyWindow;
  return w.screen ?: [UIScreen mainScreen];
}
- (UIInterfaceOrientation)interfaceOrientation {
  return [UIApplication sharedApplication].statusBarOrientation;
}
- (NSArray<UIWindow *> *)windows {
  return [UIApplication sharedApplication].windows ?: @[];
}
- (NSInteger)activationState {
  UIApplicationState st = [UIApplication sharedApplication].applicationState;
  if (st == UIApplicationStateActive) return 0;   // UISceneActivationStateForegroundActive
  if (st == UIApplicationStateInactive) return 1; // UISceneActivationStateForegroundInactive
  return 2;                                       // UISceneActivationStateBackground
}
- (id)statusBarManager {
  return [OCIOS12StatusBarManagerProxy sharedProxy];
}
- (id<UICoordinateSpace>)coordinateSpace {
  return [self screen].coordinateSpace;
}
- (UITraitCollection *)traitCollection {
  return [self screen].traitCollection;
}
- (id)delegate {
  return nil;
}
@end

static void oc_addClassMethod(Class cls, SEL sel, IMP imp, const char *types) {
  Class meta = object_getClass((id)cls);
  if (meta && !class_respondsToSelector(meta, sel)) {
    class_addMethod(meta, sel, imp, types);
  }
}

static void oc_addInstanceMethod(Class cls, SEL sel, IMP imp, const char *types) {
  if (cls && !class_respondsToSelector(cls, sel)) {
    class_addMethod(cls, sel, imp, types);
  }
}

static UIColor *oc_labelColor(__unused id self, __unused SEL _cmd) {
  return [UIColor blackColor];
}
static UIColor *oc_secondaryLabelColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithWhite:0.24 alpha:0.6];
}
static UIColor *oc_tertiaryLabelColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithWhite:0.24 alpha:0.3];
}
static UIColor *oc_quaternaryLabelColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithWhite:0.24 alpha:0.18];
}
static UIColor *oc_systemBackgroundColor(__unused id self, __unused SEL _cmd) {
  return [UIColor whiteColor];
}
static UIColor *oc_secondarySystemBackgroundColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithRed:0.95 green:0.95 blue:0.97 alpha:1.0];
}
static UIColor *oc_tertiarySystemBackgroundColor(__unused id self, __unused SEL _cmd) {
  return [UIColor whiteColor];
}
static UIColor *oc_separatorColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithWhite:0.24 alpha:0.29];
}
static UIColor *oc_opaqueSeparatorColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithWhite:0.78 alpha:1.0];
}
static UIColor *oc_linkColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithRed:0.0 green:0.48 blue:1.0 alpha:1.0];
}
static UIColor *oc_placeholderTextColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithWhite:0.24 alpha:0.3];
}
static UIColor *oc_systemFillColor(__unused id self, __unused SEL _cmd) {
  return [UIColor colorWithWhite:0.47 alpha:0.2];
}

static UIColor *oc_colorWithDynamicProvider(__unused id self, __unused SEL _cmd,
                                            UIColor *(^provider)(UITraitCollection *)) {
  if (!provider) return [UIColor clearColor];
  UITraitCollection *traits =
      [UITraitCollection traitCollectionWithUserInterfaceIdiom:UIUserInterfaceIdiomPhone];
  UIColor *resolved = provider(traits);
  return resolved ?: [UIColor clearColor];
}

static UIImage *oc_emptyImage(__unused id self, __unused SEL _cmd, __unused NSString *name) {
  return [[UIImage alloc] init];
}

static UIImage *oc_emptyImageConfig(__unused id self, __unused SEL _cmd,
                                    __unused NSString *name, __unused id configOrTraits) {
  return [[UIImage alloc] init];
}

static UIImage *oc_selfImage(UIImage *self, __unused SEL _cmd) {
  return self;
}

static CGFloat oc_zeroFloatGetter(__unused id self, __unused SEL _cmd) { return 0.0; }

static id oc_windowSceneGetter(id self, __unused SEL _cmd) {
  OCIOS12WindowSceneProxy *proxy = [OCIOS12WindowSceneProxy sharedProxy];
  if ([self isKindOfClass:[UIWindow class]]) {
    proxy.targetWindow = (UIWindow *)self;
  }
  return proxy;
}

static NSSet *oc_connectedScenesGetter(__unused id self, __unused SEL _cmd) {
  return [NSSet setWithObject:[OCIOS12WindowSceneProxy sharedProxy]];
}

static UITraitCollection *oc_currentTraitCollection(__unused id self, __unused SEL _cmd) {
  return [UIScreen mainScreen].traitCollection;
}

static NSInteger oc_accessibilityContrast(__unused id self, __unused SEL _cmd) {
  return UIAccessibilityDarkerSystemColorsEnabled() ? 1 : 0;
}

static NSInteger oc_legibilityWeight(__unused id self, __unused SEL _cmd) {
  return UIAccessibilityIsBoldTextEnabled() ? 1 : 0;
}

static void oc_performAsCurrentTraitCollection(__unused id self, __unused SEL _cmd, void (^actions)(void)) {
  if (actions) actions();
}

static BOOL oc_fileHandleSeekToEnd(NSFileHandle *self, __unused SEL _cmd,
                                   unsigned long long *offsetOut, __unused NSError **error) {
  unsigned long long off = [self seekToEndOfFile];
  if (offsetOut) *offsetOut = off;
  return YES;
}

static BOOL oc_fileHandleClose(NSFileHandle *self, __unused SEL _cmd, __unused NSError **error) {
  [self closeFile];
  return YES;
}

static NSInteger oc_photoAuthStatus(id self, __unused SEL _cmd, __unused NSInteger level) {
  if ([self respondsToSelector:@selector(authorizationStatus)]) {
    return [(id<OCIOS12PHPhotoLibraryLegacy>)self authorizationStatus];
  }
  return 0;
}

static void oc_photoRequestAuth(id self, __unused SEL _cmd, __unused NSInteger level,
                                void (^handler)(NSInteger status)) {
  if ([self respondsToSelector:@selector(requestAuthorization:)]) {
    [(id<OCIOS12PHPhotoLibraryLegacy>)self requestAuthorization:handler];
  } else if (handler) {
    handler(0);
  }
}

static BOOL oc_audioSessionBoolSetter(__unused id self, __unused SEL _cmd,
                                      __unused BOOL val, __unused NSError **outError) {
  return YES;
}

static id oc_nilGetter(__unused id self, __unused SEL _cmd) { return nil; }
static NSSet *oc_emptySetGetter(__unused id self, __unused SEL _cmd) { return [NSSet set]; }
static BOOL oc_falseGetter(__unused id self, __unused SEL _cmd) { return NO; }
static BOOL oc_trueGetter(__unused id self, __unused SEL _cmd) { return YES; }
static NSInteger oc_zeroIntGetter(__unused id self, __unused SEL _cmd) { return 0; }
static NSInteger oc_oneIntGetter(__unused id self, __unused SEL _cmd) { return 1; }
static void oc_noopSetter(__unused id self, __unused SEL _cmd) {}
static void oc_noopIdSetter(__unused id self, __unused SEL _cmd, __unused id val) {}
static void oc_noopIntSetter(__unused id self, __unused SEL _cmd, __unused NSInteger val) {}
static void oc_noopBoolSetter(__unused id self, __unused SEL _cmd, __unused BOOL val) {}

static BOOL oc_mtlSupportsFamily(id self, __unused SEL _cmd, NSInteger family) {
  if (![self respondsToSelector:@selector(supportsFeatureSet:)]) {
    return NO;
  }
  id<OCIOS12MTLDeviceLegacy> dev = (id<OCIOS12MTLDeviceLegacy>)self;
  switch (family) {
    case 1001: return [dev supportsFeatureSet:0];  // MTLGPUFamilyApple1 (A7)
    case 1002: return [dev supportsFeatureSet:1];  // MTLGPUFamilyApple2 (A8)
    case 1003: return [dev supportsFeatureSet:4];  // MTLGPUFamilyApple3 (A9/A10)
    case 1004: return [dev supportsFeatureSet:11]; // MTLGPUFamilyApple4 (A11)
    case 1005: return [dev supportsFeatureSet:14]; // MTLGPUFamilyApple5 (A12)
    case 3001:
    case 3002:
      return [dev supportsFeatureSet:1];           // MTLGPUFamilyCommon1/2
    default:
      return NO;
  }
}

@interface OCIOS12PolyfillLoader : NSObject
@end

@implementation OCIOS12PolyfillLoader

+ (void)load {
  NSOperatingSystemVersion ios13 = {13, 0, 0};
  if ([[NSProcessInfo processInfo] isOperatingSystemAtLeastVersion:ios13]) {
    return;
  }

  Class colorCls = [UIColor class];
  oc_addClassMethod(colorCls, NSSelectorFromString(@"labelColor"), OC_IMP(oc_labelColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"secondaryLabelColor"), OC_IMP(oc_secondaryLabelColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"tertiaryLabelColor"), OC_IMP(oc_tertiaryLabelColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"quaternaryLabelColor"), OC_IMP(oc_quaternaryLabelColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"systemBackgroundColor"), OC_IMP(oc_systemBackgroundColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"secondarySystemBackgroundColor"), OC_IMP(oc_secondarySystemBackgroundColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"tertiarySystemBackgroundColor"), OC_IMP(oc_tertiarySystemBackgroundColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"systemGroupedBackgroundColor"), OC_IMP(oc_secondarySystemBackgroundColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"secondarySystemGroupedBackgroundColor"), OC_IMP(oc_systemBackgroundColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"separatorColor"), OC_IMP(oc_separatorColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"opaqueSeparatorColor"), OC_IMP(oc_opaqueSeparatorColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"linkColor"), OC_IMP(oc_linkColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"placeholderTextColor"), OC_IMP(oc_placeholderTextColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"systemFillColor"), OC_IMP(oc_systemFillColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"secondarySystemFillColor"), OC_IMP(oc_systemFillColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"tertiarySystemFillColor"), OC_IMP(oc_systemFillColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"quaternarySystemFillColor"), OC_IMP(oc_systemFillColor), "@@:");
  oc_addClassMethod(colorCls, NSSelectorFromString(@"colorWithDynamicProvider:"), OC_IMP(oc_colorWithDynamicProvider), "@@:@?");
  oc_addInstanceMethod(colorCls, NSSelectorFromString(@"initWithDynamicProvider:"), OC_IMP(oc_colorWithDynamicProvider), "@@:@?");

  Class imageCls = [UIImage class];
  oc_addClassMethod(imageCls, NSSelectorFromString(@"systemImageNamed:"), OC_IMP(oc_emptyImage), "@@:@");
  oc_addClassMethod(imageCls, NSSelectorFromString(@"systemImageNamed:withConfiguration:"), OC_IMP(oc_emptyImageConfig), "@@:@@");
  oc_addClassMethod(imageCls, NSSelectorFromString(@"systemImageNamed:compatibleWithTraitCollection:"), OC_IMP(oc_emptyImageConfig), "@@:@@");
  oc_addInstanceMethod(imageCls, NSSelectorFromString(@"imageWithBaselineOffsetFromBottom:"), OC_IMP(oc_selfImage), "@@:d");
  oc_addInstanceMethod(imageCls, NSSelectorFromString(@"baselineOffsetFromBottom"), OC_IMP(oc_zeroFloatGetter), "d@:");
  oc_addInstanceMethod(imageCls, NSSelectorFromString(@"imageWithTintColor:"), OC_IMP(oc_selfImage), "@@:@");
  oc_addInstanceMethod(imageCls, NSSelectorFromString(@"imageWithTintColor:renderingMode:"), OC_IMP(oc_selfImage), "@@:@q");

  Class traitCls = [UITraitCollection class];
  oc_addClassMethod(traitCls, NSSelectorFromString(@"currentTraitCollection"), OC_IMP(oc_currentTraitCollection), "@@:");
  oc_addInstanceMethod(traitCls, NSSelectorFromString(@"accessibilityContrast"), OC_IMP(oc_accessibilityContrast), "q@:");
  oc_addInstanceMethod(traitCls, NSSelectorFromString(@"legibilityWeight"), OC_IMP(oc_legibilityWeight), "q@:");
  oc_addInstanceMethod(traitCls, NSSelectorFromString(@"userInterfaceLevel"), OC_IMP(oc_zeroIntGetter), "q@:");
  oc_addInstanceMethod(traitCls, NSSelectorFromString(@"activeAppearance"), OC_IMP(oc_oneIntGetter), "q@:");
  oc_addInstanceMethod(traitCls, NSSelectorFromString(@"imageConfiguration"), OC_IMP(oc_nilGetter), "@@:");
  oc_addInstanceMethod(traitCls, NSSelectorFromString(@"hasDifferentColorAppearanceComparedToTraitCollection:"), OC_IMP(oc_falseGetter), "B@:@");
  oc_addInstanceMethod(traitCls, NSSelectorFromString(@"performAsCurrentTraitCollection:"), OC_IMP(oc_performAsCurrentTraitCollection), "v@:@?");

  oc_addInstanceMethod([UIWindow class], NSSelectorFromString(@"windowScene"), OC_IMP(oc_windowSceneGetter), "@@:");
  oc_addInstanceMethod([UIWindow class], NSSelectorFromString(@"setWindowScene:"), OC_IMP(oc_noopIdSetter), "v@:@");
  oc_addInstanceMethod([UIApplication class], NSSelectorFromString(@"connectedScenes"), OC_IMP(oc_connectedScenesGetter), "@@:");
  oc_addInstanceMethod([UIApplication class], NSSelectorFromString(@"openSessions"), OC_IMP(oc_emptySetGetter), "@@:");
  oc_addInstanceMethod([UIApplication class], NSSelectorFromString(@"supportsMultipleScenes"), OC_IMP(oc_falseGetter), "B@:");

  oc_addInstanceMethod([UIView class], NSSelectorFromString(@"overrideUserInterfaceStyle"), OC_IMP(oc_zeroIntGetter), "q@:");
  oc_addInstanceMethod([UIView class], NSSelectorFromString(@"setOverrideUserInterfaceStyle:"), OC_IMP(oc_noopIntSetter), "v@:q");
  oc_addInstanceMethod([UIViewController class], NSSelectorFromString(@"overrideUserInterfaceStyle"), OC_IMP(oc_zeroIntGetter), "q@:");
  oc_addInstanceMethod([UIViewController class], NSSelectorFromString(@"setOverrideUserInterfaceStyle:"), OC_IMP(oc_noopIntSetter), "v@:q");
  oc_addInstanceMethod([UIViewController class], NSSelectorFromString(@"setNeedsUpdateOfSupportedInterfaceOrientations"), OC_IMP(oc_noopSetter), "v@:");

  oc_addInstanceMethod([UIScrollView class], NSSelectorFromString(@"automaticallyAdjustsScrollIndicatorInsets"), OC_IMP(oc_trueGetter), "B@:");
  oc_addInstanceMethod([UIScrollView class], NSSelectorFromString(@"setAutomaticallyAdjustsScrollIndicatorInsets:"), OC_IMP(oc_noopBoolSetter), "v@:B");

  oc_addInstanceMethod([UIButton class], NSSelectorFromString(@"configuration"), OC_IMP(oc_nilGetter), "@@:");
  oc_addInstanceMethod([UIButton class], NSSelectorFromString(@"setConfiguration:"), OC_IMP(oc_noopIdSetter), "v@:@");

  oc_addInstanceMethod([UIEvent class], NSSelectorFromString(@"buttonMask"), OC_IMP(oc_zeroIntGetter), "q@:");
  oc_addInstanceMethod([UIPress class], NSSelectorFromString(@"key"), OC_IMP(oc_nilGetter), "@@:");

  oc_addInstanceMethod([NSProcessInfo class], NSSelectorFromString(@"isiOSAppOnMac"), OC_IMP(oc_falseGetter), "B@:");
  oc_addInstanceMethod([NSProcessInfo class], NSSelectorFromString(@"isiOSAppOnVision"), OC_IMP(oc_falseGetter), "B@:");

  oc_addInstanceMethod([NSFileHandle class], NSSelectorFromString(@"seekToEndReturningOffset:error:"), OC_IMP(oc_fileHandleSeekToEnd), "B@:^Q^@");
  oc_addInstanceMethod([NSFileHandle class], NSSelectorFromString(@"closeAndReturnError:"), OC_IMP(oc_fileHandleClose), "B@:^@");

  Class phCls = NSClassFromString(@"PHPhotoLibrary");
  if (phCls) {
    oc_addClassMethod(phCls, NSSelectorFromString(@"authorizationStatusForAccessLevel:"), OC_IMP(oc_photoAuthStatus), "q@:q");
    oc_addClassMethod(phCls, NSSelectorFromString(@"requestAuthorizationForAccessLevel:handler:"), OC_IMP(oc_photoRequestAuth), "v@:q@?");
  }

  Class avAudioCls = NSClassFromString(@"AVAudioSession");
  if (avAudioCls) {
    oc_addInstanceMethod(avAudioCls, NSSelectorFromString(@"allowHapticsAndSystemSoundsDuringRecording"), OC_IMP(oc_falseGetter), "B@:");
    oc_addInstanceMethod(avAudioCls, NSSelectorFromString(@"setAllowHapticsAndSystemSoundsDuringRecording:error:"), OC_IMP(oc_audioSessionBoolSetter), "B@:B^@");
    oc_addInstanceMethod(avAudioCls, NSSelectorFromString(@"prefersNoInterruptionsFromSystemAlerts"), OC_IMP(oc_falseGetter), "B@:");
    oc_addInstanceMethod(avAudioCls, NSSelectorFromString(@"setPrefersNoInterruptionsFromSystemAlerts:error:"), OC_IMP(oc_audioSessionBoolSetter), "B@:B^@");
  }

  Class caLayerCls = NSClassFromString(@"CALayer");
  if (caLayerCls) {
    oc_addInstanceMethod(caLayerCls, NSSelectorFromString(@"setCornerCurve:"), OC_IMP(oc_noopIdSetter), "v@:@");
  }

  // Metal iOS 13+ MTLDevice shims (inherited by concrete MTLDevice implementations via NSObject)
  Class objCls = [NSObject class];
  oc_addInstanceMethod(objCls, NSSelectorFromString(@"supportsFamily:"), OC_IMP(oc_mtlSupportsFamily), "B@:q");
  oc_addInstanceMethod(objCls, NSSelectorFromString(@"hasUnifiedMemory"), OC_IMP(oc_trueGetter), "B@:");
}

@end
