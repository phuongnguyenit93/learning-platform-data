# Split package qua nhiều library

Trong Java, một package có thể xuất hiện trong nhiều file JAR khi ứng dụng còn chạy theo classpath. Khi chuyển các thư viện đó sang Java Platform Module System (JPMS), cùng một package lại có thể tạo ra xung đột giữa các named module. Đây là vấn đề thường gặp khi modular hóa một hệ thống cũ, nâng cấp dependency hoặc ghép các thư viện được phát triển độc lập.

**Split package** là tình huống các module hoặc artifact khác nhau cùng chứa class thuộc một package có cùng tên đầy đủ. Ví dụ, cả `library-a.jar` và `library-b.jar` đều chứa class trong package `com.acme.shared`. Trên classpath, classloader có thể tìm class từ cả hai JAR; trên module path, hai JAR có thể trở thành hai module riêng và làm module resolution thất bại nếu một module đọc cả hai module cùng export package đó.

Cách xử lý bền vững là xác định ai sở hữu package, sau đó hợp nhất các phần thuộc cùng một module, tách package theo namespace riêng hoặc đưa API dùng chung vào một module độc lập.

## 1. Split package là gì?

Một package được xác định bởi tên package, chẳng hạn `com.acme.shared`. Các class sau thuộc cùng package:

~~~java
package com.acme.shared;

public class JsonCodec {
}
~~~

~~~java
package com.acme.shared;

public class XmlCodec {
}
~~~

Nếu hai class nằm trong cùng một module thì không có split package giữa các module. Nhưng nếu `JsonCodec` nằm trong module `com.acme.json` còn `XmlCodec` nằm trong module `com.acme.xml`, cả hai module đều chứa package `com.acme.shared`.

Ví dụ cấu trúc:

~~~text
lib/
├── library-json.jar
│   └── com/acme/shared/JsonCodec.class
└── library-xml.jar
    └── com/acme/shared/XmlCodec.class
~~~

Tên file JAR không quyết định package ownership. Cần kiểm tra class entry bên trong từng JAR và module descriptor tương ứng.

Split package có thể phát sinh khi:

- Hai thư viện độc lập vô tình chọn cùng package name.
- Một thư viện lớn được chia thành nhiều JAR nhưng vẫn giữ package nội bộ giống nhau.
- Một thư viện cũ đặt class của nhiều thành phần trong một package chung.
- Ứng dụng thêm một class vào package vốn thuộc thư viện bên thứ ba.
- Dependency được thay thế hoặc nâng cấp khiến một package trước đây chỉ có một chủ sở hữu nay xuất hiện trong nhiều module.

Tên package theo reverse domain như `com.vendor.product` giúp giảm khả năng va chạm, nhưng không tự bảo đảm không có split package nếu các artifact cùng dùng một namespace.

## 2. Vì sao classpath thường che giấu split package?

Trước JPMS, nhiều ứng dụng đặt các JAR trên classpath:

~~~bash
java -cp "lib/library-json.jar:lib/library-xml.jar:app.jar" com.acme.app.Main
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "lib/library-json.jar;lib/library-xml.jar;app.jar" com.acme.app.Main
~~~

Các class trên classpath thuộc unnamed module của classloader tương ứng. Nhiều JAR có thể đóng góp class vào cùng một package của unnamed module. Vì vậy, hai JAR cùng chứa package `com.acme.shared` thường vẫn có thể chạy mà không gặp lỗi split package của named module.

Tuy nhiên, classpath không làm duplicate class trở nên an toàn:

- Nếu hai JAR chứa cùng một tên class đầy đủ, ví dụ `com.acme.shared.Codec`, classloader thường nạp bản tìm thấy trước theo thứ tự tìm kiếm.
- Đổi thứ tự JAR có thể làm hành vi thay đổi.
- Resource trùng tên có thể được tìm thấy theo thứ tự classloader.
- Một phần package có thể phụ thuộc vào package-private access hoặc giả định về cùng một codebase; khi tách module, những giả định này có thể không còn đúng.

Do đó, việc ứng dụng chạy được trên classpath không chứng minh các thư viện đã có ranh giới module tốt. Chuyển sang module path làm lộ ra những vấn đề ownership đã tồn tại.

## 3. JPMS phát hiện xung đột như thế nào?

Giả sử hai modular JAR có descriptor:

`library-json.jar`:

~~~java
module com.acme.json {
    exports com.acme.shared;
}
~~~

`library-xml.jar`:

~~~java
module com.acme.xml {
    exports com.acme.shared;
}
~~~

Ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.json;
    requires com.acme.xml;
}
~~~

Cả hai module dependency đều export package `com.acme.shared` cho module app. Khi resolve graph, app đọc cả hai module nhưng cùng nhìn thấy một package name từ hai module khác nhau. Module system không thể cung cấp một package duy nhất với ownership rõ ràng cho module đọc cả hai; resolution có thể thất bại với lỗi split package.

Thông báo lỗi có thể có dạng:

~~~text
java.lang.module.ResolutionException:
Modules com.acme.json and com.acme.xml
export package com.acme.shared to module com.acme.app
~~~

Tùy JDK và cách khởi chạy, lỗi có thể xuất hiện dưới dạng `FindException` bao ngoài hoặc thông báo từ launcher. Điểm cần tìm trong thông báo là hai module, package trùng tên và module đang đọc cả hai.

Quy tắc quan trọng không phải chỉ là “có hai file JAR trùng package”. Hãy xem các JAR đó được nhận diện thành module nào, module nào nằm trong configuration và module nào đọc các package được export. Một số trường hợp split package không tạo lỗi ngay nếu các module không cùng được resolve hoặc không có module đọc cả hai package export trùng nhau. Nhưng dựa vào điều đó để thiết kế hệ thống vẫn rất mong manh; hãy tránh để package có nhiều chủ sở hữu trong cùng một module graph.

## 4. Automatic module cũng có thể tạo split package

Một JAR không có `module-info.class` khi được đặt trên module path thường trở thành automatic module, với tên suy ra từ tên JAR hoặc từ metadata như `Automatic-Module-Name`.

Automatic module có các đặc tính tiện cho migration:

- Được xem là named module với một tên module.
- Export các package của nó.
- Có readability rộng hơn module thông thường.
- Có thể tham gia module graph cùng explicit module.

Nhưng automatic module không giải quyết split package. Nếu hai automatic module cùng chứa và export package `com.acme.shared`, một module đọc cả hai vẫn có thể gặp lỗi resolution tương tự.

Ví dụ hai JAR chưa có descriptor:

~~~text
lib/
├── library-json-1.0.jar
└── library-xml-1.0.jar
~~~

Nếu cả hai JAR cùng chứa `com/acme/shared/` và được đưa lên module path, hãy kiểm tra tên automatic module và các package mà chúng chứa. Không nên giả định rằng chỉ vì JAR chưa có `module-info.java` nên nó sẽ tiếp tục hành xử như classpath.

## 5. Cách phát hiện split package trong dependency

Nên kiểm tra trước khi chuyển toàn bộ ứng dụng từ classpath sang module path.

### Liệt kê nội dung từng JAR

~~~bash
jar --list --file lib/library-json.jar
jar --list --file lib/library-xml.jar
~~~

Tìm các entry có cùng prefix package, ví dụ:

~~~text
com/acme/shared/JsonCodec.class
com/acme/shared/XmlCodec.class
~~~

Nếu cần so sánh nhanh, tập trung vào đường dẫn package kết thúc bằng dấu gạch chéo, chẳng hạn `com/acme/shared/`. Đừng chỉ so sánh tên class: split package có thể tồn tại ngay cả khi hai JAR chứa các class khác nhau trong cùng package.

### Xem tên module và descriptor

~~~bash
jar --describe-module --file lib/library-json.jar
jar --describe-module --file lib/library-xml.jar
~~~

Với explicit module, kiểm tra các chỉ thị `exports`. Với automatic module, đầu ra cho biết tên module suy ra và các package được export.

Có thể dùng `java --describe-module` khi module đã nằm trên module path:

~~~bash
java --module-path lib --describe-module com.acme.json
~~~

### Kiểm tra graph lúc chạy

~~~bash
java --show-module-resolution --module-path "lib:mods" --module com.acme.app/com.acme.app.Main
~~~

Lệnh này giúp xác định module nào thực sự được resolve và nguồn module location. Nếu resolution dừng vì split package, kết hợp thông báo lỗi với descriptor và nội dung JAR để tìm hai module gây xung đột.

### Validate module path

Có thể yêu cầu launcher kiểm tra các module có thể quan sát được:

~~~bash
java --module-path lib --validate-modules
~~~

Lệnh này hữu ích để phát hiện một số vấn đề module configuration trước khi chạy main class. Kết quả phụ thuộc vào tập module mà module path cung cấp và các quy tắc resolve áp dụng.

### Kiểm tra dependency tĩnh

~~~bash
jdeps --module-path lib --check com.acme.app
~~~

`jdeps` hỗ trợ kiểm tra dependency và tính nhất quán của module. Nó không thay thế việc kiểm tra nội dung package của từng JAR; khi nghi ngờ split package, vẫn cần xem entry và descriptor của artifact.

## 6. Chiến lược 1: Gộp các JAR thuộc cùng một module

Nếu hai JAR là các phần của cùng một thư viện logic và cùng một nhóm sở hữu package, giải pháp có thể là đóng gói chúng thành một module duy nhất.

Ví dụ:

~~~text
Trước:
library-json.jar  -> com.acme.shared.JsonCodec
library-xml.jar   -> com.acme.shared.XmlCodec

Sau:
com.acme.codec.jar
  module com.acme.codec
  -> com.acme.shared.JsonCodec
  -> com.acme.shared.XmlCodec
~~~

Module descriptor sau khi hợp nhất:

~~~java
module com.acme.codec {
    exports com.acme.shared;
}
~~~

Ứng dụng chỉ cần:

~~~java
module com.acme.app {
    requires com.acme.codec;
}
~~~

Việc hợp nhất có thể được thực hiện bằng build tool, quy trình assembly hoặc tạo một modular JAR mới. Khi đóng gói, cần kiểm tra kỹ:

- Trùng class entry: không để hai phiên bản cùng ghi đè một class mà không có chủ đích.
- Resource và service provider configuration: giữ đúng nội dung cần thiết.
- Native library và file cấu hình: đặt đúng vị trí và cách nạp.
- Metadata module: chỉ có một `module-info.class` phù hợp với module cuối.
- License và notice: giữ đầy đủ thông tin của dependency được phân phối.

Không chỉ nối byte của các JAR với nhau. Một module cuối cần có cấu trúc archive và descriptor hợp lệ.

## 7. Chiến lược 2: Đổi package để mỗi thư viện có namespace riêng

Nếu hai thư viện thực sự độc lập và không thuộc cùng một module, cách rõ ràng là đổi package để không cùng sở hữu một package name.

Trước:

~~~text
com.acme.shared.JsonCodec
com.acme.shared.XmlCodec
~~~

Sau:

~~~text
com.acme.json.shared.JsonCodec
com.acme.xml.shared.XmlCodec
~~~

Các descriptor:

~~~java
module com.acme.json {
    exports com.acme.json.shared;
}
~~~

~~~java
module com.acme.xml {
    exports com.acme.xml.shared;
}
~~~

Ưu điểm:

- Ownership package rõ ràng.
- Module graph không có package export trùng nhau.
- Dễ phát triển và phát hành độc lập.
- Ít phụ thuộc vào thứ tự JAR hoặc classloader.

Đổi package là thay đổi API nhị phân và có thể ảnh hưởng source code của khách hàng. Nếu thư viện đã được sử dụng rộng rãi, cần có kế hoạch migration: phát hành phiên bản mới, cung cấp adapter hoặc deprecation period phù hợp.

## 8. Chiến lược 3: Tách API dùng chung thành module riêng

Đôi khi hai thư viện cùng chứa package vì chúng chia sẻ một số kiểu API. Thay vì để mỗi thư viện đóng gói một bản sao, có thể tách các kiểu dùng chung thành một module API duy nhất.

Ví dụ:

~~~text
com.acme.codec.api
    com.acme.codec.spi.Codec

com.acme.codec.json
    com.acme.codec.json.JsonCodec

com.acme.codec.xml
    com.acme.codec.xml.XmlCodec
~~~

Module API:

~~~java
module com.acme.codec.api {
    exports com.acme.codec.spi;
}
~~~

Module JSON:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;
    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Module XML:

~~~java
module com.acme.codec.xml {
    requires com.acme.codec.api;
    provides com.acme.codec.spi.Codec
        with com.acme.codec.xml.XmlCodec;
}
~~~

Ứng dụng tiêu thụ service:

~~~java
module com.acme.app {
    requires com.acme.codec.api;
    uses com.acme.codec.spi.Codec;
}
~~~

Mỗi package có một module sở hữu. Các provider phụ thuộc vào module API và triển khai interface chung, không đóng gói lại class API. Cách này tạo ranh giới module rõ ràng và giúp thay provider mà không làm consumer phụ thuộc trực tiếp vào implementation.

## 9. Chiến lược 4: Dùng classpath trong giai đoạn chuyển đổi

Nếu dependency chưa thể modular hóa ngay, có thể tiếp tục để một số JAR trên classpath trong giai đoạn migration. Khi đó chúng thuộc unnamed module thay vì trở thành nhiều named module riêng.

Ví dụ:

~~~bash
java --module-path mods --class-path "legacy-a.jar:legacy-b.jar" --module com.acme.app/com.acme.app.Main
~~~

Trên Windows:

~~~powershell
java --module-path mods --class-path "legacy-a.jar;legacy-b.jar" --module com.acme.app/com.acme.app.Main
~~~

Named module không tự động đọc unnamed module theo cách thông thường. Nếu module cần dùng class từ classpath, cần thiết kế bridge/migration phù hợp; không nên mặc định rằng chỉ thêm JAR vào `--class-path` là module app có thể truy cập chúng.

Classpath có thể là bước chuyển tiếp cho ứng dụng chưa thể tách module ngay, nhưng vẫn tồn tại rủi ro duplicate class và phụ thuộc vào thứ tự tìm kiếm. Hãy ghi nhận dependency legacy và đặt mục tiêu loại bỏ dần package trùng.

## 10. --patch-module không phải cách hợp nhất thư viện thông thường

Tùy chọn `--patch-module` cho phép bổ sung hoặc thay thế class/resource trong một module đã có. Nó hữu ích cho test, instrumentation hoặc một số tình huống migration có kiểm soát.

Ví dụ:

~~~bash
java --patch-module com.acme.library=patches/com.acme.library   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Nội dung trong thư mục patch được xem như một phần của module được chỉ định. Điều này khác với việc tạo một module thứ hai cùng chứa package.

Không dùng `--patch-module` như cách mặc định để gộp hai thư viện độc lập. Patch có thể làm thay đổi nội dung module runtime và tạo chênh lệch giữa môi trường test và production. Nếu hai JAR thực sự thuộc cùng một module, hãy tạo artifact module hợp nhất trong build process để kết quả có thể tái lập.

Tương tự, `--add-exports` và `--add-reads` chỉ điều chỉnh quyền truy cập/readability. Chúng không xóa package trùng và không hợp nhất hai module thành một module.

## 11. Quy trình xử lý một split package thực tế

Khi module resolution báo package được export từ hai module, hãy thực hiện theo thứ tự:

1. Ghi lại chính xác tên package và hai module được nêu trong lỗi.
2. Dùng `jar --list --file` để xác nhận cả hai JAR thật sự chứa package đó.
3. Dùng `jar --describe-module` để xác định explicit hay automatic module và xem export.
4. Dùng `--show-module-resolution` để xác định module nào đang được resolve và từ đường dẫn nào.
5. Xác định hai artifact có thuộc cùng một thư viện logic hay là hai chủ sở hữu độc lập.
6. Nếu cùng một module logic, hợp nhất artifact thành một module duy nhất.
7. Nếu độc lập, đổi package hoặc tách phần API chung thành module riêng.
8. Compile và chạy lại từ output sạch; kiểm tra module graph và dependency đã resolve.
9. Kiểm thử các consumer của thư viện vì đổi package hoặc hợp nhất artifact có thể ảnh hưởng API và resource.

Đừng sửa lỗi bằng cách xóa tùy tiện một JAR khỏi module path nếu ứng dụng vẫn cần class trong JAR đó. Hãy xác định class nào đang được sử dụng và đưa chúng về đúng module owner.

## 12. Lỗi thường gặp

**Ứng dụng chạy trên classpath nhưng không chạy trên module path.** Có thể hai JAR đang cùng chứa package và khi trở thành named/automatic module, resolution phát hiện xung đột. Kiểm tra module descriptor và package entry của từng JAR.

**Chỉ có class khác nhau nhưng vẫn split package.** Split package dựa trên tên package, không yêu cầu hai JAR phải có cùng tên class. `JsonCodec` trong một JAR và `XmlCodec` trong JAR khác vẫn là split package nếu cùng package và thuộc hai module.

**Hai JAR có cùng module name.** Đây là một vấn đề khác: duplicate module name trên module path. Kiểm tra `Automatic-Module-Name` hoặc `module-info.class`; đổi tên file không nhất thiết đổi tên module.

**Dùng --add-exports nhưng lỗi vẫn còn.** Export điều khiển quyền truy cập package. Nếu hai module cùng export package cho module đọc cả hai, thêm export không giải quyết ownership conflict.

**Gộp JAR nhưng có nhiều module-info.class.** Artifact cuối chỉ nên có một descriptor phù hợp. Hãy cấu hình build tool tạo descriptor cuối thay vì giữ nguyên nhiều descriptor đầu vào.

**Di chuyển class sang package mới làm consumer compile lỗi.** Đây là thay đổi API. Cập nhật import, module descriptor và dependency; nếu cần tương thích, phát hành adapter hoặc phiên bản chuyển tiếp.

**Một package xuất hiện trong nhiều JAR nhưng không báo lỗi ngay.** Có thể các module chưa cùng được resolve hoặc không có module đọc cả hai package export. Đừng coi đó là bảo đảm an toàn; khi root set hay dependency thay đổi, xung đột có thể xuất hiện.

## 13. Thực hành

1. Tạo hai modular JAR `com.acme.json` và `com.acme.xml`, cả hai cùng chứa package `com.acme.shared` và export package đó.
2. Tạo module app yêu cầu cả hai module. Compile và chạy để quan sát lỗi resolution.
3. Dùng `jar --list --file` và `jar --describe-module` để xác định chính xác package trùng và module owner.
4. Thử hợp nhất hai thư viện thành một module `com.acme.codec`, cập nhật app và chạy lại.
5. Tạo biến thể thứ hai bằng cách đổi package thành `com.acme.json.shared` và `com.acme.xml.shared`; kiểm tra graph không còn package export trùng.
6. Tạo module API dùng chung và hai provider độc lập; dùng `ServiceLoader` để quan sát cách chia sẻ API mà không chia sẻ package ownership.
7. Chạy `java --show-module-resolution` và `java --validate-modules` để đối chiếu kết quả trước và sau khi refactor.

Khi modular hóa nhiều library, hãy xem package là đơn vị ownership cần được quản lý rõ ràng. Mỗi package nên có một chủ sở hữu trong module graph mà ứng dụng sử dụng. Hợp nhất khi các JAR thuộc cùng một module logic; đổi namespace hoặc tách API chung khi chúng cần tồn tại độc lập. Như vậy module resolution sẽ dự đoán được và dependency không còn phụ thuộc vào thứ tự JAR trên classpath.
