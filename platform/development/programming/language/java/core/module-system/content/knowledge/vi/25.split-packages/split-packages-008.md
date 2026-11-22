# Không dùng open hoặc export để che lỗi split package

## 1. Split package là gì?

Trong Java, package là một phần của tên đầy đủ của class. Ví dụ, class \`com.acme.shared.Strings\` thuộc package \`com.acme.shared\`.

**Split package** xảy ra khi cùng một package name được chứa trong nhiều module hoặc nhiều artifact. Ví dụ:

~~~text
library-a.jar
  com/acme/shared/Strings.class

library-b.jar
  com/acme/shared/DateFormats.class
~~~

Cả hai JAR đều chứa package \`com.acme.shared\`. Khi hai thư viện được dùng chung trên classpath, tình trạng này có thể tồn tại trong các hệ thống class loader truyền thống. Tuy nhiên, khi chuyển sang JPMS, package có ranh giới module rõ ràng và việc cùng một package xuất hiện ở nhiều named module có thể gây xung đột trong module graph hoặc khi tạo module layer.

Ví dụ hai module:

~~~java
// module-info.java của com.acme.library.a
module com.acme.library.a {
    exports com.acme.shared;
}
~~~

~~~java
// module-info.java của com.acme.library.b
module com.acme.library.b {
    exports com.acme.shared;
}
~~~

Nếu một module ứng dụng đọc cả hai module và cả hai cùng export \`com.acme.shared\`, module graph có thể bị từ chối vì consumer nhìn thấy cùng package từ nhiều module. Tùy cấu hình và giai đoạn phát hiện, lỗi có thể xuất hiện khi resolve configuration, tạo ModuleLayer hoặc compile source tham chiếu package.

Đây là vấn đề về **quyền sở hữu package và cấu trúc module**, không phải vấn đề thiếu quyền truy cập reflection.

## 2. Vì sao open hoặc export không sửa được split package?

Các chỉ thị \`exports\` và \`opens\` điều khiển quyền truy cập vào package thuộc một module. Chúng không di chuyển class, hợp nhất package hoặc thay đổi module sở hữu class.

- \`exports p\`: cho phép module khác truy cập public API trong package \`p\` theo quy tắc Java thông thường.
- \`exports p to m\`: chỉ export package cho module đích được chỉ định.
- \`opens p\`: cho phép deep reflection vào package.
- \`opens p to m\`: mở package cho reflection từ module đích.
- \`open module\`: mở tất cả package của module cho deep reflection.

Nếu hai module cùng chứa package \`com.acme.shared\`, thêm \`exports com.acme.shared\` vào cả hai chỉ làm package đó được công khai từ cả hai module. Thêm \`opens com.acme.shared\` cũng không giải quyết xung đột ownership; nó chỉ thay đổi quyền reflection.

Tùy chọn runtime như \`--add-exports\` và \`--add-opens\` cũng không hợp nhất package. Chúng có thể làm thay đổi quyền truy cập và thậm chí khiến package xung đột trở nên quan sát được bởi nhiều module hơn.

Vì vậy, không nên thêm \`open\`, \`opens\`, \`exports\`, \`--add-exports\` hoặc \`--add-opens\` chỉ để làm biến mất lỗi split package. Trước hết phải xử lý nơi package và class thực sự được đóng gói.

## 3. Phân biệt split package trên classpath và module path

### 3.1. Trên classpath

Trên classpath, nhiều JAR có thể chứa class thuộc cùng package name. Các class được nạp bởi cùng class loader có thể thuộc cùng runtime package, vì runtime package được xác định bởi tên package và class loader.

Điều này giải thích vì sao một ứng dụng cũ có thể chạy dù package bị chia giữa nhiều JAR. Tuy nhiên, nó cũng tạo ra các rủi ro:

- Class có cùng fully qualified name có thể bị chọn theo thứ tự classpath.
- Package-private access có thể vô tình phụ thuộc vào việc các class dùng cùng class loader.
- Khi thay đổi thứ tự JAR, class được nạp hoặc resource được tìm thấy có thể thay đổi.
- Khi chuyển các JAR thành named module, các giả định về package ownership không còn phù hợp.

Classpath chạy được không chứng minh cấu trúc package đã tốt hoặc có thể chuyển nguyên trạng sang JPMS.

### 3.2. Trên module path

Trên module path, mỗi named module có module descriptor và tập package thuộc module. JPMS kiểm tra các package trong module graph. Xung đột thường xuất hiện khi nhiều module trong cùng configuration cùng chứa package có thể được một module khác đọc hoặc cùng tham gia một module layer theo cách không hợp lệ.

Không nên dựa vào việc một graph cụ thể tình cờ không phát hiện xung đột. Khi thiết kế module, hãy hướng tới một module owner rõ ràng cho mỗi package được chia sẻ.

Automatic module cũng cần được kiểm tra. Một JAR không có \`module-info.class\` khi được đặt trên module path có thể trở thành automatic module; việc chuyển từ classpath sang module path không tự loại bỏ package trùng giữa các dependency.

## 4. Ví dụ một dependency graph có split package

Giả sử hai thư viện được phát triển độc lập:

~~~text
com.acme.legacy-a
  com/acme/common/Strings.class
  com/acme/common/Checks.class

com.acme.legacy-b
  com/acme/common/DateFormats.class
  com/acme/common/LocaleNames.class
~~~

Khi modularize từng thư viện, descriptor có thể được viết như sau:

~~~java
module com.acme.legacy.a {
    exports com.acme.common;
}
~~~

~~~java
module com.acme.legacy.b {
    exports com.acme.common;
}
~~~

Module ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.legacy.a;
    requires com.acme.legacy.b;
}
~~~

Ứng dụng đọc cả hai module, trong khi cả hai module đều cung cấp package \`com.acme.common\`. Đây là dấu hiệu cần sửa dependency/package layout.

Không nên cố xử lý bằng cách thêm:

~~~java
module com.acme.legacy.a {
    exports com.acme.common;
    opens com.acme.common;
}
~~~

hoặc thêm các flag:

~~~bash
--add-exports=com.acme.legacy.a/com.acme.common=com.acme.app
--add-opens=com.acme.legacy.b/com.acme.common=com.acme.app
~~~

Những khai báo này không thay đổi việc hai JAR đều chứa class trong package đó. Chúng cũng không quyết định class nào là owner hợp lệ của package.

## 5. Cách tìm package bị trùng

Hãy kiểm tra artifact thực tế được đưa vào module path, không chỉ nhìn source tree. Package trùng có thể đến từ dependency bắc cầu, shaded JAR, JAR cũ còn sót trong thư mục distribution hoặc một module nội bộ được đóng gói hai lần.

### 5.1. Xem module descriptor của từng JAR

Dùng:

~~~bash
jar --describe-module --file libs/library-a.jar
jar --describe-module --file libs/library-b.jar
~~~

Lệnh này cho biết tên module, dependency và các package mà JAR export hoặc chứa trong descriptor. Với JAR không có descriptor, output có thể cho biết module name được suy ra theo quy tắc automatic module.

Lưu ý: danh sách \`exports\` không phải danh sách đầy đủ package bên trong JAR. Package nội bộ có thể tồn tại mà không được export.

### 5.2. Liệt kê class trong JAR

Dùng:

~~~bash
jar --list --file libs/library-a.jar
jar --list --file libs/library-b.jar
~~~

Tìm các đường dẫn package giống nhau, chẳng hạn:

~~~text
com/acme/common/Strings.class
com/acme/common/Checks.class
~~~

Có thể dùng công cụ archive hoặc script để trích xuất danh sách entry \`.class\` từ tất cả JAR trên module path, chuyển đường dẫn thành package name rồi so sánh. Khi làm việc này, bỏ qua \`module-info.class\` và các entry không đại diện cho class thông thường.

### 5.3. Dùng jdeps

\`jdeps\` có chế độ kiểm tra module và split package:

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

Lệnh kiểm tra dependency/module graph của module được chỉ định và có thể báo package bị split hoặc qualified export không được sử dụng. Đọc toàn bộ output để xác định module và package liên quan.

Có thể xem dependency của một JAR:

~~~bash
jdeps --list-deps --module-path mods app.jar
~~~

Nếu cần phân tích JDK internal API hoặc dependency sâu hơn, chọn các tùy chọn \`jdeps\` phù hợp với phiên bản JDK đang dùng. Kết quả của \`jdeps\` hỗ trợ điều tra dependency; vẫn cần đối chiếu danh sách class trong artifact thực tế.

### 5.4. Kiểm tra dependency tree của build tool

Với Gradle:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Để biết vì sao một dependency xuất hiện:

~~~bash
./gradlew :app:dependencyInsight --dependency library-a --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn -pl app dependency:tree
~~~

Dependency tree giúp tìm phiên bản hoặc dependency bắc cầu bị kéo vào nhiều lần. Tuy nhiên, hai artifact có tọa độ khác nhau vẫn có thể chứa package giống nhau; dependency tree không thay thế việc kiểm tra nội dung JAR.

## 6. Các cách sửa đúng

### 6.1. Hợp nhất package vào một module sở hữu

Nếu hai thư viện là các phần của cùng một subsystem và cùng một nhóm có thể thay đổi source, hãy chuyển các class cùng package vào một module owner duy nhất.

Ví dụ:

~~~text
com.acme.common
  Strings
  Checks
  DateFormats
  LocaleNames
~~~

được đóng gói trong một module:

~~~java
module com.acme.common {
    exports com.acme.common;
}
~~~

Các module cũ có thể trở thành facade hoặc được loại bỏ sau khi cập nhật caller. Cách này giữ nguyên package API và tạo một nơi quản lý ownership.

### 6.2. Đổi tên package để tách ranh giới

Nếu hai thư viện có trách nhiệm khác nhau, hãy chuyển class sang package phản ánh đúng module:

~~~text
com.acme.legacy.a
  com/acme/legacy/a/common/Strings.class
  com/acme/legacy/a/common/Checks.class

com.acme.legacy.b
  com/acme/legacy/b/common/DateFormats.class
  com/acme/legacy/b/common/LocaleNames.class
~~~

Descriptor:

~~~java
module com.acme.legacy.a {
    exports com.acme.legacy.a.common;
}
~~~

~~~java
module com.acme.legacy.b {
    exports com.acme.legacy.b.common;
}
~~~

Đây là thay đổi API nếu package cũ đã được consumer sử dụng. Cần cập nhật import, module descriptor, cấu hình reflection, tên class lưu trong cấu hình và các tích hợp dựa trên tên đầy đủ.

### 6.3. Loại bỏ dependency trùng hoặc dependency không cần thiết

Nếu cùng một thư viện bị kéo vào qua nhiều phiên bản hoặc qua dependency bắc cầu, chọn một phiên bản phù hợp và loại bỏ artifact không cần thiết.

Trong Gradle, có thể dùng dependency constraints, version catalog, resolution strategy hoặc exclude có chủ đích. Trong Maven, dùng dependency management và exclusions.

Không nên loại bỏ một JAR chỉ vì tên artifact giống nhau. Hãy xác nhận class và API mà module đang sử dụng, sau đó chạy lại compile/test và kiểm tra module graph.

### 6.4. Relocate package khi shading thư viện bên thứ ba

Nếu không thể sửa source của thư viện bên thứ ba và cần đưa hai thư viện vào cùng một ứng dụng, có thể relocate một package khi tạo shaded JAR.

Ví dụ về ý tưởng:

~~~text
com.vendor.common
    -> com.acme.shaded.vendor.common
~~~

Sau relocation, class của thư viện được đổi sang package riêng và không còn xung đột với package gốc.

Cần kiểm tra thêm các dữ liệu chứa tên class/package dưới dạng chuỗi, service provider file, resource, serialization metadata, reflection configuration và module descriptor. Công cụ shading phải cập nhật những metadata liên quan; chỉ đổi tên file \`.class\` mà bỏ sót nội dung tham chiếu sẽ tạo lỗi runtime khó tìm.

Relocation nên được cấu hình trong build, có thể tái lập và được kiểm tra trên artifact cuối.

### 6.5. Tạo một adapter hoặc facade module

Nếu cần giữ API công khai cũ trong khi di chuyển implementation, tạo một module facade có package API duy nhất và chuyển implementation vào các package/module nội bộ riêng.

Ví dụ:

~~~text
com.acme.common.api
com.acme.common.impl.strings
com.acme.common.impl.dates
~~~

Facade có thể cung cấp các interface hoặc class public cần thiết, còn implementation được đặt trong package không trùng. Cách này giúp chuyển đổi dần mà vẫn có một module owner rõ ràng cho mỗi package.

## 7. Những cách không nên dùng để che lỗi

| Cách thử | Vì sao không giải quyết split package |
| --- | --- |
| Thêm \`exports\` vào cả hai module | Làm public package từ nhiều module; không hợp nhất class hoặc xác định một owner. |
| Thêm \`opens\` hoặc dùng \`open module\` | Chỉ cấp quyền deep reflection, không thay đổi package ownership. |
| Thêm \`--add-exports\` | Bổ sung quyền truy cập public types, không loại bỏ package trùng. |
| Thêm \`--add-opens\` | Bổ sung quyền reflection, không sửa module graph. |
| Đổi thứ tự JAR trên classpath | Có thể làm thay đổi class được nạp, nhưng không loại bỏ class trùng hoặc cấu trúc package không ổn định. |
| Đưa mọi dependency về classpath | Có thể né một số kiểm tra JPMS trong ngắn hạn nhưng bỏ qua lợi ích và ranh giới module; không phải phương án modularization. |
| Chỉ đổi tên module trong \`module-info.java\` | Tên module thay đổi, còn package bên trong vẫn trùng. |

## 8. Quy trình xử lý split package trong dự án modular

1. Ghi lại lỗi đầy đủ và xác định module/package xuất hiện trong thông báo.
2. Xác định chính xác module path và tập artifact được đưa vào lần compile hoặc runtime bị lỗi.
3. Dùng \`jar --describe-module\` và \`jar --list\` để xác định module nào chứa package đó.
4. Dùng \`jdeps --check\` và dependency tree để tìm dependency trực tiếp hoặc bắc cầu đưa các module xung đột vào graph.
5. Chọn một owner cho package, hoặc đổi package/relocate artifact để tách ownership.
6. Cập nhật dependency, source import, descriptor và metadata liên quan.
7. Build lại từ trạng thái sạch để tránh JAR cũ còn sót trong output.
8. Chạy lại \`jdeps --check\`, compile module và ứng dụng bằng đúng module path triển khai.
9. Kiểm tra artifact cuối cùng và chạy integration test trong đúng runtime/module layer.

## 9. Kết luận về package ownership

Một package nên có một module owner rõ ràng trong thiết kế JPMS. \`exports\` quyết định module nào có thể dùng public API của package; \`opens\` quyết định module nào có thể deep reflection vào package. Hai cơ chế này không giải quyết việc cùng package bị chia giữa nhiều module.

Khi gặp split package, hãy truy ngược từ module graph tới các JAR chứa class, sau đó hợp nhất, đổi tên, loại bỏ dependency trùng hoặc relocate package. Giải quyết ownership ở artifact/source level giúp module graph ổn định và tránh tạo thêm quyền truy cập rộng chỉ để che một lỗi cấu trúc.
