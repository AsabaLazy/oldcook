Pod::Spec.new do |s|
  s.name             = 'ios12_polyfill'
  s.version          = '0.1.0'
  s.summary          = 'Objective-C runtime polyfills for iOS 13+ UIKit/Scene selectors on iOS 12.'
  s.homepage         = 'https://example.invalid/oldcook'
  s.license          = { :type => 'MIT' }
  s.author           = { 'oldcook' => 'oldcook@localhost' }
  s.source           = { :path => '.' }
  s.platform         = :ios, '12.0'
  s.source_files     = 'Sources/**/*.{h,m}'
  s.frameworks       = 'UIKit', 'Foundation'
  s.requires_arc     = true
end
