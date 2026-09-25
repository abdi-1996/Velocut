Pod::Spec.new do |s|
  s.name = 'ReelRenderer'
  s.version = '0.2.0'
  s.summary = 'On-device ReelForge video renderer'
  s.description = 'Local AVFoundation editing, audio analysis and offline speech.'
  s.license = { :type => 'MIT' }
  s.author = 'ReelForge'
  s.homepage = 'https://github.com/abdi-1996/Velocut'
  s.platforms = { :ios => '16.4' }
  s.swift_version = '5.9'
  s.source = { :git => 'https://github.com/abdi-1996/Velocut.git' }
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.frameworks = 'AVFoundation', 'Speech', 'UIKit', 'QuartzCore'
  s.source_files = '**/*.swift'
end
