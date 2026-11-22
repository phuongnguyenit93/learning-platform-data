# Automatic module và chuyển tiếp sang explicit module

Java Platform Module System (JPMS) được thiết kế để hỗ trợ quá trình chuyển đổi từ thư viện Java truyền thống sang ứng dụng modular. Trong thực tế, nhiều thư viện vẫn được phát hành dưới dạng JAR không có **module-info.class**. Để những JAR này có thể tham gia module path và được module có tên sử dụng, Java cung cấp cơ chế **automatic module**.

Automatic module là cầu nối migration: nó cho phép một thư viện cũ được tham chiếu bằng tên module và tham gia module graph mà chưa cần sửa mã nguồn để thêm descriptor. Khi thư viện đã sẵn sàng, nhà phát triển có thể bổ sung **module-info.java** để chuyển thành **explicit module**, khai báo rõ dependency, package API và service contract.

## 1. JAR trên classpath và JAR trên module path

Một JAR truyền thống khi đặt trên classpath thuộc **unnamed module**. JVM không dùng module descriptor riêng của JAR đó để xác định package nào được công bố hoặc module nào phụ thuộc vào nó.

Ví dụ chạy ứng dụng theo classpath:

~~~bash
java -cp "lib/*:app.jar" com.acme.app.Main
~~~

Khi chuyển một JAR không có **module-info.class** sang module path, Java có thể coi nó là automatic module. JVM tạo một module descriptor tự động dựa trên JAR và metadata của nó.

Ví dụ:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Nếu ứng dụng modular có khai báo **requires** đến automatic module, module đó có thể được phân giải như một named module. Đây là khác biệt quan trọng: JAR trên classpath thuộc unnamed module; cùng JAR đó trên module path có thể trở thành automatic module có tên.

| Vị trí JAR | Cách JVM quản lý |
|---|---|
| Classpath | Thuộc unnamed module; không có tên module riêng để khai báo trong **requires**. |
| Module path, có **module-info.class** | Là explicit named module với descriptor do nhà phát hành khai báo. |
| Module path, không có **module-info.class** | Có thể được xem là automatic module với descriptor tổng hợp. |

Named module thông thường không thể khai báo **requires** đến unnamed module. Vì vậy, automatic module là một bước trung gian hữu ích khi thư viện chưa có descriptor nhưng ứng dụng muốn chuyển sang module path.

## 2. Tên của automatic module được xác định thế nào?

Automatic module cần có tên để các module khác tham chiếu. Có hai nguồn chính:

1. Manifest của JAR có thuộc tính **Automatic-Module-Name**.
2. Nếu không có thuộc tính đó, Java suy ra tên từ tên file JAR theo quy tắc đặt tên automatic module.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy.json
~~~

Với thuộc tính này, JAR được nhận diện là **com.acme.legacy.json** khi đặt trên module path, kể cả khi tên file artifact thay đổi theo phiên bản.

Nếu không khai báo **Automatic-Module-Name**, tên module được suy ra từ filename. Ví dụ JAR có tên:

~~~text
legacy-json-parser-2.4.1.jar
~~~

có thể được suy ra thành tên dạng **legacy.json.parser**. Thuật toán suy luận loại bỏ phần version phù hợp và chuyển các dấu phân cách không hợp lệ thành dấu chấm theo quy tắc của JDK. Không nên tự đoán tên cuối cùng trong build; hãy kiểm tra bằng công cụ JDK.

Kiểm tra tên module:

~~~bash
jar --describe-module --file mods/legacy-json-parser-2.4.1.jar
~~~

Hoặc dùng **jar --describe-module** trên JAR cụ thể sau khi đã đặt vào thư mục dependency của dự án.

Tên suy ra từ filename có thể thay đổi khi artifact được đổi tên hoặc cách đóng gói phiên bản thay đổi. Với thư viện dự định được dùng lâu dài trên module path, nhà phát hành nên công bố **Automatic-Module-Name** để giữ tên module ổn định ngay cả trước khi có explicit descriptor.

## 3. Quyền đọc và exports của automatic module

Automatic module có ngữ nghĩa rộng hơn explicit module:

- Nó đọc tất cả các module khác trong module configuration, giúp thư viện cũ có thể tiếp tục truy cập nhiều dependency khi được chuyển lên module path.
- Tất cả package của automatic module được export, nên named module có thể truy cập các public type trong các package của nó nếu module đó đọc automatic module.
- Nó không yêu cầu nhà phát hành cung cấp **module-info.java** để bắt đầu tham gia module graph.

Ví dụ ứng dụng:

~~~java
module com.acme.application {
    requires com.acme.legacy.json;
}
~~~

Nếu JAR trên module path được nhận diện là **com.acme.legacy.json**, module application có thể đọc package mà automatic module export.

Tính tương thích rộng này giúp migration dễ bắt đầu, nhưng cũng làm ranh giới module kém chặt chẽ. Một explicit module chỉ export các package được chọn; automatic module lại export toàn bộ package của JAR. Các package nội bộ vốn chỉ nên dùng trong implementation có thể trở thành khả năng truy cập từ module khác.

Automatic module cũng có khả năng đọc rộng các module khác. Điều đó hữu ích cho thư viện cũ có dependency chưa được mô tả bằng JPMS, nhưng làm module graph ít thể hiện chính xác dependency thực tế. Đây là lý do nên xem automatic module như bước chuyển tiếp, không phải thiết kế đích cho thư viện mới.

## 4. Tại sao cần chuyển sang explicit module?

Explicit module có **module-info.class** được biên dịch từ **module-info.java**. Descriptor mô tả rõ:

- Tên module ổn định.
- Các dependency trực tiếp qua **requires**.
- Các dependency được truyền cho module tiêu thụ qua **requires transitive**.
- Package API được công bố qua **exports**.
- Package cần reflection được mở qua **opens**.
- Service mà module tiêu thụ qua **uses**.
- Service mà module cung cấp qua **provides ... with ...**.

Ví dụ:

~~~java
module com.acme.json {
    requires java.logging;

    exports com.acme.json.api;
}
~~~

Với descriptor này, package **com.acme.json.api** được công bố cho module khác; package implementation như **com.acme.json.internal** vẫn được đóng kín nếu không export. Dependency **java.logging** cũng được thể hiện tường minh.

Khi thư viện chuyển từ automatic sang explicit module, khả năng truy cập của người dùng có thể thay đổi. Một package trước đây được automatic module export có thể không còn truy cập được nếu explicit descriptor không khai báo **exports**. Tương tự, một dependency trước đây được automatic module đọc rộng có thể cần được khai báo **requires** rõ ràng.

## 5. Lộ trình migration từng bước

Có thể chuyển một thư viện cũ sang explicit module theo các giai đoạn sau.

### Giai đoạn 1: Kiểm kê thư viện trên classpath

Trước tiên, xác định JAR, dependency và package mà thư viện sử dụng. Kiểm tra các dependency được build tool phân giải, các API công khai và những framework có sử dụng reflection.

Ở giai đoạn này, thư viện vẫn có thể được dùng trên classpath. Mục tiêu là hiểu phạm vi package và dependency trước khi thay đổi cách phân phối.

### Giai đoạn 2: Đưa JAR lên module path

Nếu JAR không có **module-info.class**, đặt nó trên module path để Java nhận diện automatic module.

Dùng **jar --describe-module** để xem tên và package được nhận diện:

~~~bash
jar --describe-module --file lib/legacy-json-parser-2.4.1.jar
~~~

Nếu tên module suy ra không phù hợp hoặc không ổn định, yêu cầu nhà phát hành thêm **Automatic-Module-Name**. Nếu đang sở hữu thư viện, có thể thêm thuộc tính manifest vào artifact của mình.

### Giai đoạn 3: Cố định tên module

Trước khi công bố dependency module name cho người dùng, hãy cố định tên bằng manifest:

~~~text
Automatic-Module-Name: com.acme.json
~~~

Giữ tên này ổn định khi bổ sung explicit descriptor. Consumer có thể khai báo **requires com.acme.json** trong cả giai đoạn automatic và explicit nếu tên được duy trì nhất quán.

Đây là bước quan trọng để chuyển đổi không buộc mọi module tiêu thụ đổi tên dependency khi thư viện bắt đầu có **module-info.class**.

### Giai đoạn 4: Phân tích dependency và package

Có thể dùng **jdeps** để phân tích dependency của JAR:

~~~bash
jdeps --summary lib/legacy-json-parser-2.4.1.jar
~~~

Xem dependency ở cấp module:

~~~bash
jdeps --print-module-deps lib/legacy-json-parser-2.4.1.jar
~~~

Phân tích package và module dependency chi tiết hơn:

~~~bash
jdeps --verbose:class lib/legacy-json-parser-2.4.1.jar
~~~

Kết quả là dữ liệu hỗ trợ thiết kế descriptor, không phải descriptor hoàn chỉnh trong mọi trường hợp. Công cụ có thể không suy ra đầy đủ dependency phản ánh qua reflection, service loading, cấu hình runtime hoặc tên class được tạo động. Cần kết hợp phân tích với hiểu biết về API và cách thư viện thực sự chạy.

### Giai đoạn 5: Tạo module-info.java

Sau khi xác định dependency và package API, tạo descriptor:

~~~java
module com.acme.json {
    requires java.logging;

    exports com.acme.json.api;
}
~~~

Nếu thư viện cần service, bổ sung **uses** hoặc **provides** theo đúng vai trò. Nếu framework cần deep reflection, chỉ mở package cần thiết bằng **opens** hoặc qualified **opens**. Không export toàn bộ package chỉ để làm cho mọi truy cập hiện tại tiếp tục hoạt động.

Có thể dùng:

~~~bash
jdeps --generate-module-info generated-modules lib/legacy-json-parser-2.4.1.jar
~~~

Lệnh này tạo descriptor gợi ý trong thư mục đích cho những module mà công cụ phân tích được. Hãy xem kết quả là điểm khởi đầu để chỉnh sửa; không sao chép mù quáng vào thư viện vì các yêu cầu về service, reflection và API compatibility có thể cần khai báo bổ sung.

### Giai đoạn 6: Biên dịch và đóng gói explicit module

Biên dịch module descriptor cùng source code:

~~~bash
javac -d out --module-source-path src -m com.acme.json
~~~

Đóng gói:

~~~bash
jar --create --file mods/com.acme.json.jar -C out/com.acme.json .
~~~

Kiểm tra descriptor đã đóng gói:

~~~bash
jar --describe-module --file mods/com.acme.json.jar
~~~

Kết quả phải hiển thị tên module mong muốn, dependency, package export và các khai báo service. Xác nhận tên explicit module giữ nguyên tên automatic module đã công bố trước đó.

### Giai đoạn 7: Kiểm thử người dùng module

Chạy các module consumer thực tế trên module path. Kiểm tra compile, test, reflection, service loading và đóng gói runtime image nếu dự án cần **jlink**.

Đừng chỉ kiểm thử module thư viện riêng lẻ. Các thay đổi về exports, requires và opens có thể chỉ làm lộ lỗi khi một ứng dụng tiêu thụ cố import package, truy cập reflection hoặc khởi tạo service.

## 6. Giữ ổn định Automatic-Module-Name khi chuyển đổi

Giả sử phiên bản cũ của thư viện có manifest:

~~~text
Automatic-Module-Name: com.acme.legacy.client
~~~

Consumer khai báo:

~~~java
module com.acme.app {
    requires com.acme.legacy.client;
}
~~~

Khi nhà phát hành bổ sung explicit descriptor, tên trong descriptor nên tiếp tục là:

~~~java
module com.acme.legacy.client {
    exports com.acme.legacy.client.api;
}
~~~

Nếu explicit module dùng tên khác, mọi consumer có **requires com.acme.legacy.client** có thể cần cập nhật. Điều đó tạo ra một thay đổi migration không cần thiết.

Tên module là định danh ở cấp JPMS; tên file JAR và tọa độ Maven/Gradle có thể thay đổi độc lập. Có thể đổi artifact version hoặc filename mà vẫn giữ module name. Khi chuyển sang explicit module, duy trì module name đã công bố giúp quá trình nâng cấp ít gây gián đoạn.

## 7. Thay đổi hành vi exports khi chuyển từ automatic sang explicit

Đây là một khác biệt dễ gây lỗi nhất. Automatic module export tất cả package. Explicit module chỉ export các package được liệt kê trong descriptor.

Ví dụ JAR cũ chứa:

~~~text
com.acme.json.api
com.acme.json.internal
com.acme.json.spi
~~~

Khi là automatic module, cả ba package đều được export theo ngữ nghĩa automatic module. Consumer cũ có thể vô tình import class từ **com.acme.json.internal**.

Sau khi chuyển thành explicit module:

~~~java
module com.acme.json {
    exports com.acme.json.api;
    exports com.acme.json.spi;
}
~~~

Package **com.acme.json.internal** không còn là API được export. Consumer đang import class nội bộ có thể không biên dịch được. Đây là cơ hội để nhà phát hành xác định rõ package nào thực sự là hợp đồng công khai.

Trước khi migration, nên kiểm kê consumer đã sử dụng package nào. Nếu package từng bị dùng rộng rãi, cần quyết định giữ API tương thích, đưa ra giai đoạn deprecation hoặc công bố breaking change trong phiên bản phù hợp. Không export package nội bộ chỉ để che giấu việc chưa xác định API.

## 8. Chuyển dependency đọc rộng thành requires rõ ràng

Automatic module đọc các module khác trong module configuration. Explicit module không còn đặc quyền đọc rộng đó; nó cần khai báo dependency phù hợp.

Ví dụ descriptor mới:

~~~java
module com.acme.legacy.client {
    requires java.logging;
    requires java.sql;

    exports com.acme.legacy.client.api;
}
~~~

Nếu implementation sử dụng module **java.logging** hoặc **java.sql**, các dependency này cần được mô tả rõ. Nếu API công khai để lộ kiểu từ một dependency, hãy cân nhắc **requires transitive**. Nếu dependency chỉ phục vụ implementation, **requires** thường là đủ.

Dependency được build tool tải về không tự động thay thế chỉ thị **requires**. Khi chạy trên module path, module graph vẫn phải hợp lệ. Vì vậy cần đồng bộ dependency Maven/Gradle với descriptor explicit.

## 9. Reflection và service loading trong migration

Một thư viện cũ có thể dựa vào reflection rộng vì chạy trên classpath. Khi chuyển sang explicit module, framework có thể không còn truy cập private field hoặc constructor nếu package chưa được mở.

Ví dụ:

~~~java
module com.acme.persistence {
    requires com.acme.domain;
    requires some.orm.framework;

    opens com.acme.domain.entity to some.orm.framework;
}
~~~

Trong descriptor thực tế, **opens** phải được khai báo ở module sở hữu package entity, không phải module ORM. Ví dụ module domain:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to some.orm.framework;
}
~~~

Nếu thư viện dùng ServiceLoader, cần chuyển metadata provider cũ sang khai báo JPMS phù hợp:

~~~java
module com.acme.codec {
    exports com.acme.codec.api;
    uses com.acme.codec.spi.Codec;
}
~~~

Provider module:

~~~java
module com.acme.codec.json {
    requires com.acme.codec;

    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.internal.JsonCodec;
}
~~~

Package implementation của provider không cần export chỉ để ServiceLoader phát hiện class được đăng ký. Khi chuyển đổi, kiểm tra cả **META-INF/services** của thư viện cũ và khai báo **uses/provides** của explicit module để service discovery tiếp tục hoạt động.

## 10. Automatic module không thể dùng trực tiếp với jlink

Automatic module hữu ích cho module path nhưng không phải module phù hợp để đưa vào linked runtime image bằng **jlink**. **jlink** yêu cầu các module đầu vào là explicit modules có descriptor phù hợp.

Nếu ứng dụng cần tạo runtime image tối giản, các dependency automatic phải được nâng cấp hoặc thay bằng phiên bản explicit module trước khi link.

Có thể kiểm tra module dependency của ứng dụng bằng:

~~~bash
jdeps --print-module-deps --module-path mods --module com.acme.app
~~~

Sau khi các dependency cần thiết đều là explicit module, tạo image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --output runtime
~~~

Trên Windows, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --output runtime
~~~

Hãy kiểm thử runtime image trên từng nền tảng đích. Một ứng dụng chạy thành công với automatic module trên module path chưa chứng minh rằng nó có thể được link bằng jlink.

## 11. Những rủi ro khi chuyển tiếp

| Rủi ro | Biểu hiện | Cách giảm thiểu |
|---|---|---|
| Tên module thay đổi | Consumer không resolve được dependency sau nâng cấp. | Cố định **Automatic-Module-Name** và giữ nguyên tên trong explicit descriptor. |
| Package không còn export | Consumer không biên dịch vì import package trước đây truy cập được. | Kiểm kê API được dùng; export đúng package công khai và có kế hoạch tương thích. |
| Thiếu requires | Compile hoặc runtime báo module/package không được đọc. | Phân tích dependency, khai báo requires và kiểm thử trên module path. |
| Framework mất quyền reflection | Lỗi **InaccessibleObjectException** hoặc **trySetAccessible()** thất bại. | Mở đúng package bằng **opens** hoặc qualified **opens** cho framework. |
| ServiceLoader không tìm provider | Provider không được phát hiện sau khi thay đổi cách đóng gói. | Kiểm tra **uses**, **provides**, provider registration và service binding. |
| jlink thất bại | Dependency vẫn là automatic module. | Nâng cấp dependency lên explicit module hoặc chọn cách phân phối khác phù hợp. |
| Split package | Nhiều module cùng chứa package gây lỗi resolution/linking. | Tách package, loại dependency trùng hoặc dùng artifact có ranh giới module phù hợp. |

Migration nên được triển khai theo từng thư viện và kiểm thử bằng các ứng dụng tiêu thụ thật. Không nên chuyển đồng loạt mọi dependency chỉ bằng cách thêm descriptor sinh tự động.

## 12. Checklist trước khi phát hành explicit module

- Tên module được công bố ổn định và giữ nguyên từ giai đoạn automatic.
- Descriptor liệt kê đúng các dependency trực tiếp.
- **requires transitive** chỉ dùng khi dependency là một phần của API công khai.
- Chỉ export package API cần thiết; package implementation được giữ kín.
- Các package framework cần reflection được mở có giới hạn.
- Service consumer và provider được khai báo bằng **uses** và **provides** phù hợp.
- Không còn dependency automatic nếu mục tiêu phát hành cần **jlink**.
- Không có split package trong module graph.
- JAR có **module-info.class** đúng tên và có thể được resolve trên module path.
- Consumer compile và chạy được với descriptor mới; các framework và service discovery cũng được kiểm thử.

Automatic module giúp thư viện cũ tham gia JPMS mà chưa cần thay đổi mã nguồn. Explicit module hoàn thiện quá trình chuyển đổi bằng cách mô tả chính xác dependency, API và quyền truy cập. Giữ tên module ổn định, giới hạn exports, bổ sung opens có chủ đích và kiểm thử consumer thực tế sẽ giúp thư viện chuyển sang JPMS mà vẫn duy trì được hợp đồng tích hợp rõ ràng.