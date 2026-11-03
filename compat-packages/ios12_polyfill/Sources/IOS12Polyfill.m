#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

// Runtime shim active ONLY prior to iOS 13.0.
// Prevents unrecognized-selector crashes when plugins call common iOS 13+ UIKit/Scene APIs.

#define OC_IMP(fn) ((IMP)(void (*)(void))(fn))

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

static id oc_nilGetter(__unused id self, __unused SEL _cmd) { return nil; }
static NSSet *oc_emptySetGetter(__unused id self, __unused SEL _cmd) { return [NSSet set]; }
static BOOL oc_falseGetter(__unused id self, __unused SEL _cmd) { return NO; }

@interface OCIOS12PolyfillLoader : NSObject
@end

@implementation OCIOS12PolyfillLoader

+ (void)load {
  if (@available(iOS 13.0, *)) {
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
  oc_addClassMethod(colorCls, NSSelectorFromString(@"colorWithDynamicProvider:"), OC_IMP(oc_colorWithDynamicProvider), "@@:@?");
  oc_addInstanceMethod(colorCls, NSSelectorFromString(@"initWithDynamicProvider:"), OC_IMP(oc_colorWithDynamicProvider), "@@:@?");

  Class imageCls = [UIImage class];
  oc_addClassMethod(imageCls, NSSelectorFromString(@"systemImageNamed:"), OC_IMP(oc_emptyImage), "@@:@");
  oc_addClassMethod(imageCls, NSSelectorFromString(@"systemImageNamed:withConfiguration:"), OC_IMP(oc_emptyImageConfig), "@@:@@");
  oc_addClassMethod(imageCls, NSSelectorFromString(@"systemImageNamed:compatibleWithTraitCollection:"), OC_IMP(oc_emptyImageConfig), "@@:@@");

  oc_addInstanceMethod([UIWindow class], NSSelectorFromString(@"windowScene"), OC_IMP(oc_nilGetter), "@@:");
  oc_addInstanceMethod([UIApplication class], NSSelectorFromString(@"connectedScenes"), OC_IMP(oc_emptySetGetter), "@@:");
  oc_addInstanceMethod([UIApplication class], NSSelectorFromString(@"openSessions"), OC_IMP(oc_emptySetGetter), "@@:");
  oc_addInstanceMethod([UIApplication class], NSSelectorFromString(@"supportsMultipleScenes"), OC_IMP(oc_falseGetter), "B@:");
}

@end
