# Bundle identifier và ký ứng dụng macOS theo môi trường phân phối

Khi đóng gói ứng dụng Java cho macOS bằng **jpackage**, cần xác định bundle identifier ổn định và chọn quy trình ký phù hợp với nơi phân phối. Bundle identifier nhận diện ứng dụng trong hệ thống macOS; chữ ký mã xác nhận nhà phát hành và bảo vệ tính toàn vẹn của bundle. Hai phần này liên quan chặt chẽ nhưng có vai trò khác nhau.

Ứng dụng phát hành trực tiếp qua website, CDN hoặc hệ thống quản lý thiết bị thường dùng **Developer ID** và notarization để Gatekeeper có thể xác minh ứng dụng. Ứng dụng đưa lên **Mac App Store** phải tuân theo quy trình App Store Connect, App Sandbox, provisioning profile và chữ ký phân phối App Store. Không dùng cùng một bộ cấu hình ký cho cả hai kênh.

Trong module Java 16, jpackage là công cụ đóng gói đã được hoàn thiện. Bài này tập trung vào bundle identifier, chữ ký code, Developer ID, Hardened Runtime, entitlements, notarization và quy trình App Store. Những nguyên tắc này vẫn áp dụng trong macOS hiện đại; các tùy chọn jpackage thay đổi theo JDK nên cần xác nhận bằng lệnh trợ giúp của đúng bản JDK đang chạy.

## 1. Bundle identifier là gì?

Bundle identifier là chuỗi định danh duy nhất của ứng dụng trong hệ sinh thái Apple. Với macOS app bundle, giá trị này được lưu trong khóa **CFBundleIdentifier** của file Info.plist bên trong bundle:

~~~text
InventoryDesk.app/
  Contents/
    Info.plist
    MacOS/
    Resources/
    app/
    runtime/
~~~

macOS dùng bundle identifier để nhận diện ứng dụng, áp dụng một số thiết lập, định tuyến tài liệu qua Launch Services và xác minh thông tin liên quan đến chữ ký. Bundle identifier thường dùng dạng reverse-DNS, ví dụ:

~~~text
com.example.inventory
~~~

Apple quy định chuỗi này chỉ gồm chữ cái Latin, chữ số, dấu gạch nối và dấu chấm. Bundle identifier không phân biệt chữ hoa/chữ thường. Nên dùng tên miền do tổ chức kiểm soát và tên sản phẩm ổn định để giảm nguy cơ trùng với ứng dụng của nhà phát triển khác.

## 2. Phân biệt tên ứng dụng và bundle identifier

jpackage có một số tùy chọn có tên gần nhau nhưng điều khiển thông tin khác nhau:

| Tùy chọn | Vai trò |
|---|---|
| --name | Tên ứng dụng dùng khi đóng gói và tên mặc định của bundle. |
| --mac-package-identifier | Bundle identifier được ghi vào metadata của ứng dụng macOS. |
| --mac-package-name | Tên ngắn hiển thị trong menu bar và cửa sổ thông tin ứng dụng. |
| --mac-package-signing-prefix hoặc tùy chọn prefix tương ứng trong JDK đang dùng | Tiền tố cho bundle identifier của thành phần cần ký nhưng chưa có identifier riêng. |

Ví dụ, tên hiển thị có thể là Inventory Desk, trong khi bundle identifier là com.example.inventory.desktop. Đổi tên hiển thị không nhất thiết phải đổi bundle identifier.

Không dùng tên main class làm bundle identifier mặc định cho sản phẩm phát hành lâu dài. jpackage có thể lấy main class làm giá trị mặc định, nhưng tên lớp có thể đổi khi refactor. Hãy chỉ định bundle identifier tường minh để giữ định danh ổn định qua các phiên bản.

## 3. Chọn bundle identifier ổn định

Trước khi phát hành, quyết định bundle identifier theo các nguyên tắc:

1. Dùng reverse-DNS dựa trên tên miền hoặc namespace do tổ chức kiểm soát.
2. Chọn một chuỗi riêng cho từng ứng dụng độc lập.
3. Giữ nguyên identifier khi nâng cấp cùng một ứng dụng.
4. Dùng identifier riêng cho sản phẩm khác, kể cả khi cùng nhà phát hành.
5. Đồng bộ identifier với App ID trong Apple Developer account nếu phân phối qua Mac App Store hoặc dùng capability gắn với App ID.
6. Kiểm tra cả app bundle, extension, helper và provisioning profile nếu ứng dụng có nhiều thành phần.

Ví dụ cấu trúc:

~~~text
com.example.inventory
com.example.inventory.helper
com.example.inventory.updater
~~~

Identifier của helper hoặc thành phần nhúng có thể có namespace riêng. Signing prefix có thể được dùng để gán identifier cho thành phần chưa có identifier, nhưng không thay thế việc thiết kế identifier cho từng bundle có vai trò độc lập.

## 4. Cấu hình bundle identifier bằng jpackage

Ví dụ tạo application image trên macOS:

~~~bash
jpackage \
  --type app-image \
  --name InventoryDesk \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --mac-package-identifier com.example.inventory \
  --dest build/mac
~~~

Trong lệnh:

- --type app-image tạo app bundle để kiểm tra trước khi tạo bộ phân phối.
- --name đặt tên ứng dụng hiển thị.
- --mac-package-identifier đặt CFBundleIdentifier.
- --dest xác định thư mục đầu ra.

Sau khi tạo image, kiểm tra identifier thực tế:

~~~bash
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \
  build/mac/InventoryDesk.app/Contents/Info.plist
~~~

Hoặc dùng:

~~~bash
plutil -p build/mac/InventoryDesk.app/Contents/Info.plist
~~~

Kết quả phải đúng với identifier đã chọn. Nếu bundle identifier sai, hãy sửa cấu hình và tạo lại image trước khi ký. Thay đổi Info.plist sau khi ký sẽ làm chữ ký không còn hợp lệ.

## 5. Bundle identifier trong Mac App Store

Nếu phân phối qua Mac App Store, bundle identifier phải khớp với App ID đã đăng ký trong Apple Developer account và bundle ID của app record trong App Store Connect.

Apple xác định một build bằng bundle ID, version và build string. Sau khi upload build đầu tiên lên App Store Connect, không thể đổi bundle ID của app record đó. Nếu cần một identifier khác, phải tạo app record mới và xử lý như một ứng dụng riêng.

Vì vậy:

- Chọn identifier trước khi tạo App ID và app record.
- Dùng đúng identifier trong --mac-package-identifier.
- Kiểm tra provisioning profile được tạo cho explicit App ID tương ứng.
- Không đổi identifier giữa các bản cập nhật của cùng ứng dụng.
- Nếu có app extension hoặc helper cần capability riêng, kiểm tra identifier và entitlement của từng target.

Đối với phân phối trực tiếp ngoài App Store, bundle identifier vẫn nên ổn định dù không cần tạo app record trong App Store Connect. Điều này giúp macOS nhận diện ứng dụng nhất quán và tránh tạo ra các ứng dụng có danh tính khác nhau sau mỗi lần đổi tên hoặc refactor.

## 6. Chữ ký mã trên macOS bảo vệ điều gì?

Code signing gắn một danh tính phát hành với executable, framework, helper và app bundle. Chữ ký cho phép macOS kiểm tra:

- Mã được ký bởi danh tính nào.
- Nội dung có bị thay đổi sau khi ký hay không.
- Các thành phần code nhúng có chữ ký hợp lệ hay không.
- Quyền truy cập đặc biệt nào được khai báo qua entitlements.

Chữ ký không thay thế kiểm thử bảo mật và không chứng minh ứng dụng không có lỗi. Nó xác nhận nguồn gốc theo danh tính ký và phát hiện việc sửa đổi nội dung đã ký.

Một app bundle có thể chứa launcher native của jpackage, runtime Java, thư viện native, framework và helper. Tất cả executable hoặc code bundle cần được ký đúng cách. Các file dữ liệu thông thường được đặt trong Resources theo cấu trúc bundle phù hợp.

## 7. Hai môi trường phân phối có quy trình ký khác nhau

| Nội dung | Phân phối trực tiếp ngoài Mac App Store | Mac App Store |
|---|---|---|
| Mục tiêu | Người dùng tải từ website, CDN hoặc kênh của tổ chức | Người dùng tải qua App Store |
| Danh tính ký ứng dụng | Developer ID Application | Apple Distribution theo quy trình phân phối App Store hiện hành |
| Ký installer PKG | Developer ID Installer | Danh tính installer phân phối App Store theo cấu hình Apple hiện hành |
| App Sandbox | Không bắt buộc cho mọi ứng dụng trực tiếp; chọn theo thiết kế | Bắt buộc |
| Hardened Runtime | Bắt buộc cho ứng dụng gửi notarization | Tuân theo yêu cầu ký và sandbox của App Store; không dùng cấu hình notarization thay thế |
| Notarization | Dùng notary service của Apple | Không cần gửi notarization riêng cho bản phân phối App Store |
| Provisioning profile | Chỉ cần trong các trường hợp sử dụng capability yêu cầu profile | Dùng profile phân phối App Store gắn với App ID |
| Phân phối và cập nhật | Nhà phát triển quản lý | App Store Connect và App Store quản lý |

Không lấy chứng thư Developer ID để thay thế chứng thư phân phối App Store. Cũng không dùng provisioning profile App Store cho gói Developer ID phát hành trực tiếp nếu profile đó không thuộc kênh phân phối đang dùng.

## 8. Phân phối trực tiếp: Developer ID Application và Developer ID Installer

Với ứng dụng tải trực tiếp từ website hoặc hệ thống của tổ chức, Apple cung cấp hai loại danh tính chính:

- **Developer ID Application:** ký app bundle, executable, framework và code nhúng.
- **Developer ID Installer:** ký installer package dạng .pkg có chứa ứng dụng đã ký.

Nếu phân phối một file .dmg chứa app bundle, cần ký app bundle bằng Developer ID Application. Có thể ký thêm disk image để bảo vệ container sau khi tạo.

Nếu phân phối file .pkg, app bên trong cần được ký bằng Developer ID Application; package cài đặt bên ngoài được ký bằng Developer ID Installer. Sau khi ký, gửi container phân phối tới notary service theo quy trình Apple.

Apple yêu cầu dùng Developer ID certificate phù hợp cho notarization. Chứng thư tự ký hoặc chứng thư dành cho mục đích khác không thay thế Developer ID.

## 9. Kiểm tra signing identity trong Keychain

Trước khi gọi jpackage, xác nhận chứng thư và private key tương ứng có trong keychain của tài khoản build:

~~~bash
security find-identity -v -p codesigning
~~~

Lệnh này liệt kê danh tính code signing hợp lệ, chẳng hạn Developer ID Application hoặc Apple Distribution.

Installer signing identity là loại danh tính riêng. Khi kiểm tra chứng thư dành cho .pkg, không lọc bằng tùy chọn -p codesigning vì bộ lọc đó có thể loại các installer identity:

~~~bash
security find-identity -v
~~~

Nếu dùng keychain riêng, xác nhận đường dẫn keychain và quyền truy cập private key. jpackage có tùy chọn --mac-signing-keychain để chỉ định keychain; nếu không chỉ định, công cụ tìm trong các keychain mặc định.

Không đưa file private key, mật khẩu keychain hoặc thông tin xác thực notarization vào repository hay log CI. Dùng secret store của hệ thống build và cấp quyền truy cập tối thiểu cho job ký.

## 10. Ký bằng jpackage cho phân phối trực tiếp

jpackage cung cấp các tùy chọn chính:

- --mac-sign yêu cầu ký application bundle hoặc package.
- --mac-signing-key-user-name chọn phần tên team/user trong Apple signing identity.
- --mac-signing-keychain chỉ định keychain chứa identity nếu không dùng keychain mặc định.
- Tùy chọn signing prefix gán tiền tố cho thành phần cần ký nhưng chưa có bundle identifier.

Ví dụ tạo DMG đã ký bằng Developer ID Application:

~~~bash
jpackage \
  --type dmg \
  --name InventoryDesk \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --mac-package-identifier com.example.inventory \
  --mac-sign \
  --mac-signing-key-user-name "Example Team" \
  --dest dist
~~~

Ví dụ tạo PKG có installer signature:

~~~bash
jpackage \
  --type pkg \
  --name InventoryDesk \
  --app-version 1.4.0 \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --mac-package-identifier com.example.inventory \
  --mac-sign \
  --mac-signing-key-user-name "Example Team" \
  --dest dist
~~~

Tên team trong ví dụ phải khớp phần tên của identity có trong keychain. Khi tạo DMG, jpackage cần identity ký ứng dụng. Khi tạo PKG, installer cần identity ký package phù hợp. Xác nhận identity thực tế trước khi chạy; không giả định chỉ cần một certificate cho cả app và installer.

Với JDK 16, man page Oracle ghi tùy chọn signing prefix là **--mac-bundle-signing-prefix**. Một trang hướng dẫn đóng gói JDK 16 khác dùng tên **--mac-package-signing-prefix**, trong khi man page của JDK mới dùng tên này. Do tài liệu JDK 16 có khác biệt, hãy chạy **jpackage --help** từ chính JDK dùng để build và dùng đúng tên tùy chọn mà executable công bố.

Ví dụ cú pháp prefix theo man page JDK 16:

~~~bash
jpackage \
  --type dmg \
  --name InventoryDesk \
  --input build/libs \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --mac-package-identifier com.example.inventory \
  --mac-sign \
  --mac-bundle-signing-prefix com.example.inventory. \
  --mac-signing-key-user-name "Example Team" \
  --dest dist
~~~

Trên JDK mới có tên tùy chọn đã đổi, thay **--mac-bundle-signing-prefix** bằng **--mac-package-signing-prefix** theo man page của JDK đó.

## 11. Signing prefix cho thành phần nhúng

Một bundle có thể chứa executable hoặc thư viện cần ký nhưng chưa có bundle identifier riêng. Signing prefix được dùng để tạo identifier cho các thành phần đó.

Ví dụ prefix:

~~~text
com.example.inventory.
~~~

Prefix kết thúc bằng dấu chấm để ghép với tên thành phần. Nó khác với bundle identifier chính:

| Giá trị | Ví dụ | Vai trò |
|---|---|---|
| Bundle identifier của ứng dụng | com.example.inventory | Định danh app chính. |
| Signing prefix | com.example.inventory. | Tạo identifier cho thành phần chưa có identifier. |
| Tên hiển thị | Inventory Desk | Tên người dùng nhìn thấy. |

Không dùng signing prefix để thay thế --mac-package-identifier. Nếu một helper hoặc framework đã có identifier riêng, hãy giữ identifier đó theo thiết kế của thành phần.

## 12. Hardened Runtime và entitlements khi notarize

Hardened Runtime bổ sung các biện pháp bảo vệ khi ứng dụng chạy. Apple yêu cầu bật Hardened Runtime cho app và command-line target trước khi gửi notarization.

Entitlements khai báo quyền hoặc ngoại lệ bảo mật mà executable cần. Chỉ thêm entitlement thực sự cần cho chức năng của ứng dụng:

- Ứng dụng Java có thể cần các entitlement mặc định do jpackage cung cấp để runtime Java hoạt động.
- Ứng dụng dùng JIT hoặc native component đặc thù có thể cần kiểm tra entitlement tương ứng.
- Ứng dụng truy cập tài nguyên được bảo vệ cần quyền phù hợp với mô hình sandbox và cách xin quyền của macOS.
- Không thêm entitlement rộng chỉ để làm cho notarization qua được.

Các JDK mới có tùy chọn --mac-entitlements để truyền file entitlement khi ký executable và library trong bundle. Tài liệu jpackage hiện hành mô tả resource mặc định dành cho runtime JDK. Nếu cần file tùy chỉnh, hãy dựa trên chức năng thực tế và tài liệu Apple.

JDK 16 man page không liệt kê --mac-entitlements. Không đưa tùy chọn của JDK mới vào lệnh JDK 16 nếu binary đang dùng không hỗ trợ. Khi cần cấu hình entitlement riêng với JDK 16, dùng quy trình ký ngoài được Apple hỗ trợ hoặc nâng lên JDK có tùy chọn tương ứng; sau mọi bước ký phải xác minh lại chữ ký.

## 13. Notarization cho ứng dụng phát hành trực tiếp

Notarization là quy trình gửi phần mềm đã ký Developer ID tới Apple để hệ thống tự động kiểm tra mã độc và các vấn đề ký. Đây không phải App Review và không chứng minh ứng dụng hoàn toàn an toàn.

Các yêu cầu chính:

1. Ký toàn bộ executable và code bundle cần phân phối.
2. Dùng Developer ID certificate đúng loại.
3. Bật Hardened Runtime cho app và command-line target.
4. Ký kèm secure timestamp.
5. Tạo container phân phối phù hợp và gửi tới notary service.
6. Xem log kết quả, xử lý lỗi hoặc cảnh báo.
7. Staple ticket notarization vào app, DMG hoặc PKG nếu định dạng hỗ trợ.

Apple hiện yêu cầu dùng **notarytool**; dịch vụ notarization không còn nhận upload qua altool từ ngày 1/11/2023. Không xây pipeline mới dựa trên altool hoặc Xcode 13 trở xuống.

## 14. Gửi và staple bằng notarytool

Trước tiên, tạo keychain profile cho notarytool bằng thông tin xác thực App Store Connect theo hướng dẫn Apple. Sau đó gửi container:

~~~bash
xcrun notarytool submit dist/InventoryDesk.dmg \
  --keychain-profile "notary-profile" \
  --wait
~~~

Nếu gửi PKG, thay đường dẫn bằng file PKG. Dùng --wait để chờ kết quả; khi job hoàn tất, kiểm tra trạng thái và log notarization. Không phát hành nếu kết quả là Invalid.

Khi notarization thành công, staple ticket vào container:

~~~bash
xcrun stapler staple dist/InventoryDesk.dmg
xcrun stapler validate dist/InventoryDesk.dmg
~~~

Với PKG:

~~~bash
xcrun stapler staple dist/InventoryDesk.pkg
xcrun stapler validate dist/InventoryDesk.pkg
~~~

Staple giúp Gatekeeper xác minh ticket ngay cả khi máy người dùng không kết nối Internet. Nếu phân phối ZIP, không thể staple trực tiếp vào ZIP; hãy staple app bundle trước khi tạo ZIP.

## 15. Thứ tự ký và đóng gói container

Nếu phân phối một app bên trong PKG rồi đặt PKG trong DMG, thứ tự cần được kiểm soát:

1. Ký code bên trong app bundle, từ thành phần nhúng đến bundle ngoài cùng.
2. Ký app bundle.
3. Tạo PKG và ký PKG bằng installer identity.
4. Tạo DMG chứa PKG và ký DMG nếu kênh phân phối yêu cầu.
5. Notarize container ngoài cùng mà người dùng tải xuống.
6. Staple ticket vào container ngoài cùng.

Nếu chỉ phân phối DMG chứa app bundle, ký app trước, tạo DMG, ký DMG rồi notarize DMG. Nếu chỉ phân phối PKG, ký app, tạo và ký PKG rồi notarize PKG.

Apple khuyến cáo không dùng codesign --deep để ký một sản phẩm phức tạp. Cách này có thể áp cùng entitlement cho mọi thành phần, dù helper hoặc executable nhúng cần quyền khác nhau. Hãy ký code theo thứ tự từ trong ra ngoài. Tùy chọn --deep có thể hữu ích khi xác minh đệ quy chữ ký, nhưng không nên dùng như cách ký tất cả thành phần trong một lệnh.

## 16. Phân phối qua Mac App Store

Mac App Store có quy trình khác với Developer ID distribution:

- Bundle identifier phải khớp explicit App ID và app record trong App Store Connect.
- Ứng dụng phải bật App Sandbox.
- Các capability cần thiết phải được cấu hình trong App ID, entitlement và provisioning profile.
- App phải được ký bằng danh tính phân phối App Store theo quy trình Apple hiện hành.
- App được đóng gói và upload qua App Store Connect để Apple review.

Apple hiện mô tả **Apple Distribution** là danh tính ký code cho ứng dụng Mac App Store. Tên certificate cũ như **3rd Party Mac Developer Application** hoặc **3rd Party Mac Developer Installer** có thể xuất hiện trong tài liệu jpackage hoặc quy trình cũ; không sao chép các tên này vào cấu hình mới nếu chúng không tồn tại trong keychain và không còn được Apple cấp cho workflow hiện hành. Xác nhận danh tính bằng Xcode/Apple Developer account và đối chiếu với tài liệu Apple mới nhất. Nếu jpackage của JDK đang dùng không nhận diện đúng danh tính hiện hành, hoàn tất bước ký và export bằng quy trình Xcode/Apple được hỗ trợ.

Với jpackage ở các JDK mới, có tùy chọn --mac-app-store để đánh dấu đầu ra dành cho Mac App Store và --mac-entitlements để chỉ định entitlement. Nếu không chỉ định entitlement tùy chỉnh, jpackage mới có thể dùng sandbox entitlement mặc định khi bật chế độ App Store.

JDK 16 man page không liệt kê --mac-app-store hoặc --mac-entitlements. Vì vậy, không sao chép các tùy chọn này vào lệnh chạy bằng JDK 16 nếu lệnh trợ giúp không hỗ trợ. Với ứng dụng Java cần đưa lên Mac App Store, hãy dùng toolchain Apple hiện hành để hoàn thiện profile, entitlement, ký, đóng gói và upload; hoặc chọn JDK mới có các tùy chọn cần thiết rồi kiểm tra toàn bộ artifact theo quy trình App Store.

Notarization dành cho kênh phân phối trực tiếp Developer ID. App được gửi qua Mac App Store đi qua quy trình xác minh và review của App Store; không cần gửi notarization riêng như bản tải trực tiếp.

## 17. Kiểm tra chứng thư và chữ ký

Sau khi tạo app image hoặc installer, kiểm tra danh tính ký và cấu trúc:

~~~bash
codesign -dv --verbose=4 build/mac/InventoryDesk.app
codesign --verify --deep --strict --verbose=2 build/mac/InventoryDesk.app
~~~

Lệnh đầu hiển thị thông tin chữ ký, bao gồm authority và identifier. Lệnh thứ hai xác minh đệ quy code nhúng. Dùng --deep ở đây cho mục đích verify, không dùng làm cách ký toàn bundle.

Kiểm tra bundle identifier:

~~~bash
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \
  build/mac/InventoryDesk.app/Contents/Info.plist
~~~

Với ứng dụng phân phối trực tiếp, có thể đánh giá Gatekeeper:

~~~bash
spctl --assess --type execute --verbose=4 \
  build/mac/InventoryDesk.app
~~~

Đối với DMG, kiểm tra integrity của image:

~~~bash
hdiutil verify dist/InventoryDesk.dmg
~~~

Kiểm tra chữ ký thành công không thay thế bước notarization. Tương tự, notarization thành công không thay thế kiểm thử chức năng và kiểm tra khả năng cài đặt trên các phiên bản macOS được hỗ trợ.

## 18. Kiểm tra bundle và chữ ký sau khi tạo

Trước khi phát hành, xác minh:

1. CFBundleIdentifier đúng và ổn định.
2. Tên hiển thị, version và icon đúng.
3. App bundle chứa runtime và resource cần thiết.
4. Mọi executable, framework, helper và native library có chữ ký hợp lệ.
5. Team ID và signing identity đúng kênh phân phối.
6. Entitlements chỉ cấp các quyền cần thiết.
7. Hardened Runtime được bật nếu gửi notarization.
8. Installer package được ký bằng installer identity đúng loại.
9. Notarization status là Accepted và ticket đã được staple khi cần.
10. Gatekeeper chấp nhận app trên máy macOS sạch.

Không chỉnh sửa file trong app bundle sau khi ký. Nếu thay Info.plist, runtime, native library, icon hoặc resource nằm trong vùng được chữ ký bảo vệ, hãy tạo lại chữ ký và kiểm tra lại quy trình notarization.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| App xuất hiện như ứng dụng mới sau nâng cấp | Bundle identifier bị đổi | Giữ --mac-package-identifier ổn định qua các phiên bản. |
| App Store Connect từ chối bundle ID | Identifier không khớp App ID/app record | Đồng bộ CFBundleIdentifier với explicit App ID và App Store Connect. |
| jpackage không tìm thấy signing identity | Certificate hoặc private key chưa có trong keychain của tài khoản build | Kiểm tra security find-identity và keychain đang dùng. |
| DMG ký được nhưng PKG không ký được | Dùng Developer ID Application thay cho Developer ID Installer | Dùng đúng installer signing identity cho PKG. |
| Notarization từ chối ứng dụng | Thiếu Developer ID, Hardened Runtime, timestamp hoặc chữ ký thành phần nhúng không hợp lệ | Đọc notarization log, sửa lỗi ký và gửi lại. |
| Chữ ký sai sau khi thay file trong app bundle | Nội dung đã thay đổi sau khi ký | Hoàn tất mọi thay đổi trước khi ký; sau chỉnh sửa phải ký lại. |
| Bundle identifier của helper bị trùng | Signing prefix hoặc identifier riêng không được thiết kế rõ | Cấp namespace riêng và kiểm tra từng nested bundle. |
| Lệnh jpackage báo không nhận --mac-entitlements | Đang dùng JDK không hỗ trợ tùy chọn này | Kiểm tra jpackage --help; dùng quy trình ký ngoài hoặc JDK có hỗ trợ. |
| App Store build bị từ chối do sandbox | Thiếu App Sandbox hoặc entitlement/profile không khớp | Kiểm tra App ID, provisioning profile và entitlement theo yêu cầu App Store. |
| Dùng altool không thể gửi notarization | Apple đã ngừng nhận upload qua altool | Chuyển sang notarytool và stapler. |

## 20. Quy trình phát hành trực tiếp đề xuất

1. Chọn bundle identifier reverse-DNS và giữ nguyên qua các phiên bản.
2. Tạo application image bằng jpackage trên macOS runner.
3. Kiểm tra Info.plist và CFBundleIdentifier.
4. Cài Developer ID Application identity; nếu tạo PKG, chuẩn bị thêm Developer ID Installer identity.
5. Ký app bundle và code nhúng bằng jpackage hoặc quy trình codesign được kiểm soát.
6. Bật Hardened Runtime và dùng entitlements tối thiểu.
7. Tạo DMG/PKG và ký container nếu cần.
8. Gửi container ngoài cùng bằng notarytool.
9. Xem log, staple và validate ticket.
10. Kiểm tra Gatekeeper và cài thử trên máy sạch.
11. Lưu artifact, checksum, bundle ID, Team ID, JDK, Xcode và kết quả notarization.

## 21. Quy trình phát hành Mac App Store đề xuất

1. Chọn bundle identifier và đăng ký explicit App ID.
2. Tạo app record trong App Store Connect với cùng bundle ID.
3. Cấu hình App Sandbox, capabilities và entitlements.
4. Tạo App Store provisioning profile tương ứng với App ID.
5. Dùng danh tính ký phân phối App Store theo hướng dẫn Apple hiện hành.
6. Tạo app bundle và installer package đáp ứng yêu cầu App Store.
7. Xác minh bundle ID, chữ ký, profile và entitlement.
8. Upload qua App Store Connect/Transporter và xử lý kết quả validation.
9. Gửi App Review và phát hành qua App Store.

Nếu dùng jpackage mới với --mac-app-store, xác nhận option và entitlement mặc định trong tài liệu đúng JDK. Không mặc định rằng cờ này tự tạo app record, profile, upload hay hoàn tất App Review.

## 22. Cách áp dụng trong quy trình Java hiện đại

- Chỉ định --mac-package-identifier tường minh và giữ ổn định qua các bản phát hành.
- Phân biệt bundle identifier với tên hiển thị và signing prefix.
- Dùng Developer ID Application cho app bundle phân phối trực tiếp; dùng Developer ID Installer cho PKG trực tiếp.
- Bật Hardened Runtime, secure timestamp và entitlement tối thiểu khi notarize.
- Dùng notarytool và stapler; không dùng altool đã ngừng được Apple hỗ trợ.
- Với Mac App Store, đồng bộ bundle ID, App ID, App Store Connect, sandbox, profile và danh tính phân phối.
- Kiểm tra phiên bản JDK trước khi dùng --mac-entitlements, --mac-app-store hoặc signing-prefix option.
- Ký code nhúng từ trong ra ngoài; không dùng codesign --deep để ký toàn bộ ứng dụng.
- Kiểm tra chữ ký, notarization, Gatekeeper và cài đặt thực tế trước khi phát hành.

Bundle identifier ổn định giúp macOS nhận diện ứng dụng nhất quán; code signing xác nhận nguồn gốc và tính toàn vẹn của ứng dụng. Chọn đúng Developer ID hoặc App Store distribution, cấu hình entitlement theo kênh phát hành và hoàn tất notarization khi phân phối trực tiếp sẽ giúp ứng dụng Java đáp ứng cơ chế bảo mật macOS hiện hành.

## Tài liệu tham khảo

- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle JDK 16 — Sign the Application Package (macOS)](https://docs.oracle.com/en/java/javase/16/jpackage/support-application-features.html)
- [Oracle JDK 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Oracle JDK 26 — Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)
- [Apple — CFBundleIdentifier](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleidentifier)
- [Apple — Developer ID Certificates](https://developer.apple.com/help/account/certificates/create-developer-id-certificates)
- [Apple — Certificates Overview](https://developer.apple.com/help/account/certificates/certificates-overview)
- [Apple — Creating Distribution-Signed Code for macOS](https://developer.apple.com/documentation/xcode/creating-distribution-signed-code-for-the-mac)
- [Apple — Notarizing macOS Software Before Distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Apple — Customizing the Notarization Workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow)
- [Apple — Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)
- [Apple — Preparing Your App for Distribution](https://developer.apple.com/documentation/xcode/preparing-your-app-for-distribution)
- [Apple — Packaging Mac Software for Distribution](https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution)
