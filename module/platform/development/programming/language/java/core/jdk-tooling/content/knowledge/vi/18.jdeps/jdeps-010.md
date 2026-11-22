# Hỗ trợ migration module bằng jdeps

## Mục tiêu

Sau bài này, bạn có thể dùng jdeps để chuẩn bị và thực hiện migration từ ứng dụng Java chạy trên classpath sang Java Platform Module System (JPMS); kiểm kê dependency; phát hiện JDK internal API và dependency bị thiếu; tạo bản nháp module-info.java; hiểu vai trò của unnamed module và automatic module trong giai đoạn chuyển tiếp; thiết kế requires, exports, opens, uses và provides; xử lý split package, reflection và service provider; và xác minh module graph sau khi migration.

## 1. Migration module là gì?

**Module migration** là quá trình chuyển ứng dụng và thư viện Java từ mô hình classpath truyền thống sang mô hình module có tên (named module) của JPMS, được giới thiệu từ Java 9.

Trong mô hình classpath, các JAR thường được nạp vào unnamed module của class loader. Mã trong classpath có thể truy cập các public type mà class loader tìm thấy, và ranh giới đóng gói chủ yếu dựa vào package, classpath và quy ước của dự án.

Trong JPMS, mỗi explicit named module có module descriptor, thường là file module-info.java trong source và module-info.class trong artifact. Descriptor khai báo:

- Module phụ thuộc vào module nào bằng requires.
- Package nào được công khai bằng exports.
- Package nào mở cho reflection bằng opens.
- Service nào module cần bằng uses.
- Service provider nào module cung cấp bằng provides ... with ....

Module system bổ sung hai khái niệm quan trọng: **readability** (module có đọc được module khác hay không) và **accessibility** (package/type có được truy cập qua ranh giới module hay không).

Migration không chỉ là thêm module-info.java. Bạn phải hiểu dependency thật, API công khai, reflection, service loading, package ownership, thư viện bên thứ ba và cách ứng dụng được triển khai.

## 2. jdeps hỗ trợ migration như thế nào?

jdeps là công cụ phân tích bytecode. Nó giúp trả lời những câu hỏi quan trọng trước và trong migration:

| Câu hỏi | Công cụ hoặc tùy chọn |
|---|---|
| Ứng dụng tham chiếu package/class nào? | -verbose:package, -verbose:class |
| Cần module JDK nào? | --list-deps, --print-module-deps |
| Có phụ thuộc JDK internal API không? | --jdk-internals |
| Có dependency nào không phân giải được? | --missing-deps |
| JAR cũ có thể bắt đầu bằng module descriptor nào? | --generate-module-info |
| Thư viện phụ thuộc reflection sâu cần open module không? | --generate-open-module |
| Module descriptor hiện tại có dependency nào? | --check |
| Package nào được API công khai phơi bày? | --api-only |
| Artifact nào phụ thuộc ngược vào module/package? | --inverse kết hợp --require hoặc --package |

jdeps giúp lập bản đồ dependency và tạo bản nháp descriptor. Nó không tự chuyển toàn bộ source code thành module, không tự thiết kế API, không xác định chính xác mọi nhu cầu reflection và không bảo đảm ứng dụng hoạt động sau migration.

Hãy xem kết quả jdeps như bằng chứng để đưa ra quyết định thiết kế, sau đó xác minh bằng compiler, module resolver và test runtime.

## 3. Hiểu ba trạng thái trong giai đoạn chuyển tiếp

JPMS hỗ trợ phối hợp code cũ và code mới qua unnamed module, automatic module và explicit named module.

### Unnamed module: JAR trên classpath

Các class được nạp từ classpath thuộc unnamed module của class loader tương ứng. Unnamed module đọc tất cả observable modules và các package của nó được xem là exported và open.

Điểm quan trọng: explicit named module không thể viết requires để đọc unnamed module. Vì vậy, nếu một thư viện chỉ tồn tại trên classpath và không phải automatic module, code trong named module không thể khai báo dependency bình thường đến thư viện đó.

Đây là lý do thường cần đưa các thư viện phụ thuộc lên module path hoặc chuyển chúng thành named/automatic modules trước khi modularize ứng dụng.

### Automatic module: JAR không có module-info trên module path

Một JAR không có module-info.class khi được đặt trên module path sẽ trở thành automatic module. Nó có tên module và được module system xử lý với các quy tắc tương thích migration:

- Automatic module đọc tất cả module trong configuration.
- Khi được tạo trong JVM, nó đọc cả unnamed modules.
- Tất cả package của automatic module được xem là exported và open.
- Descriptor của automatic module không khai báo requires, exports, opens, uses hoặc provides tường minh (ngoài quan hệ nền tảng java.base theo mô hình descriptor).

Tên automatic module được lấy từ thuộc tính Automatic-Module-Name trong manifest nếu có; nếu không, tên được suy ra từ tên file JAR. Vì vậy, đổi tên file có thể làm thay đổi module name.

Kiểm tra tên và trạng thái module của JAR:

~~~bash
jar --describe-module --file lib/legacy-library.jar
~~~

Nếu bạn kiểm soát thư viện nhưng chưa thể thêm module-info.java, có thể yêu cầu nhà phát hành đặt Automatic-Module-Name ổn định trong manifest. Đây là cầu nối hữu ích, nhưng vẫn nên chuyển sang explicit module khi thư viện sẵn sàng.

### Explicit named module: module có descriptor

Explicit module có module-info.java/module-info.class. Nó chỉ đọc các module được khai báo qua requires (cùng các cạnh readability được suy ra), chỉ công khai package được exports và chỉ mở package được opens hoặc open module.

Đây là đích đến thường mong muốn vì dependency và ranh giới API được khai báo rõ ràng.

### So sánh nhanh

| Đặc điểm | Unnamed module | Automatic module | Explicit module |
|---|---|---|---|
| Vị trí phổ biến | Classpath | Module path, JAR không có descriptor | Module path, có module-info |
| Tên module | Không có tên | Suy ra từ manifest/tên JAR | Khai báo trong module-info |
| Đọc module khác | Đọc tất cả observable modules | Đọc tất cả modules trong configuration | Theo requires và module resolution |
| Package được export | Tất cả package | Tất cả package tại runtime | Chỉ package được exports |
| Package được open | Tất cả package | Tất cả package tại runtime | Chỉ package được opens, trừ open module |
| Dùng để migration | Chạy code cũ | Cầu nối cho thư viện cũ | Đích đến rõ ràng |

Automatic module tiện lợi cho migration nhưng không nên trở thành hợp đồng lâu dài của API. Khi thư viện đổi sang explicit module, module name và package exports có thể thay đổi; JLS khuyến nghị compiler cảnh báo khi requires trỏ đến automatic module, đặc biệt với requires transitive.

## 4. Quy trình migration theo từng giai đoạn

Một lộ trình thực tế thường bắt đầu bằng việc giữ ứng dụng chạy được, sau đó modularize dependency theo từng lớp.

### Giai đoạn 1: lập baseline

Trước khi thay đổi module:

1. Ghi nhận JDK hiện tại, JDK mục tiêu, build tool và phiên bản dependency.
2. Chạy test hiện có và lưu kết quả.
3. Ghi nhận cách ứng dụng khởi động, classpath, JVM flags và system properties.
4. Liệt kê thư viện, plugin, JDBC driver, logging provider, serializer và framework.
5. Ghi lại các tính năng dùng reflection, ServiceLoader, JNI/JNA hoặc nạp class theo tên.

Migration là quá trình lặp. Chạy ứng dụng trên JDK mục tiêu trước khi recompile có thể giúp phát hiện vấn đề runtime và thư viện cần nâng cấp. Sau đó cập nhật thư viện, biên dịch và chạy jdeps để bổ sung thông tin.

### Giai đoạn 2: phân tích bytecode và dependency

Chạy các lệnh cơ bản trên artifact đã build:

~~~bash
jdeps -summary app.jar
jdeps -verbose:package app.jar
jdeps --missing-deps --class-path "lib/*" app.jar
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

- -summary cho bức tranh tổng quan.
- -verbose:package giúp thấy quan hệ giữa các package.
- --missing-deps tìm dependency không phân giải được.
- --jdk-internals tìm tham chiếu đến JDK internal API.

Nếu cần biết dependency nào xuất hiện trong public/protected API của thư viện:

~~~bash
jdeps --api-only --verbose:package library.jar
~~~

Phân tích API-only tập trung vào type xuất hiện trong public/protected signatures của public class, chẳng hạn kiểu field, tham số, kiểu trả về và checked exception. Kết quả giúp xác định dependency nào có thể cần requires transitive khi chuyển thư viện thành module.

### Giai đoạn 3: chuyển dependency sang module path

Đưa các thư viện bên thứ ba lên module path để quan sát cách module system nhìn nhận chúng:

~~~bash
jdeps --module-path "mods:lib" --list-deps app.jar
~~~

Trên Windows, dùng dấu chấm phẩy để phân tách module path:

~~~powershell
jdeps --module-path "mods;lib" --list-deps app.jar
~~~

Dùng jar --describe-module để xem từng JAR là explicit module hay automatic module và tên module mà compiler/runtime sẽ dùng.

Ở giai đoạn này, ứng dụng có thể vẫn chạy trên classpath trong khi các dependency được kiểm tra trên module path. Khi bắt đầu chuyển ứng dụng thành named module, mọi dependency mà nó cần đọc phải có mặt dưới dạng module có thể quan sát và resolve được.

### Giai đoạn 4: modularize thư viện nền trước

Thường nên chuyển những thư viện ít phụ thuộc nhất trước, rồi mới đến thư viện tầng trên và ứng dụng cuối cùng.

Với JAR chưa có descriptor, jdeps có thể tạo bản nháp module-info.java:

~~~bash
jdeps --generate-module-info build/generated-modules lib/legacy-library.jar
~~~

Nếu thư viện dựa vào deep reflection trên nhiều package và cần một descriptor mở toàn bộ package trong giai đoạn đầu, có thể thử:

~~~bash
jdeps --generate-open-module build/generated-open-modules lib/legacy-library.jar
~~~

Hai lệnh này phân tích các JAR được chỉ định và sinh module-info.java trong thư mục đích. Không dùng --class-path hoặc --dot-output cùng các tùy chọn generate này.

File được sinh ra là bản nháp. Hãy review tên module, requires, exports, package, service và hành vi reflection trước khi dùng trong build chính thức.

### Giai đoạn 5: chuyển ứng dụng thành explicit module

Sau khi dependency cần thiết đã có thể được đặt trên module path, tạo module-info.java cho ứng dụng. Khai báo requires tới module API mà source thực sự dùng; export package ứng dụng chỉ khi module khác cần gọi API đó.

Compile và chạy trên module path, sau đó kiểm tra module graph bằng jdeps --check.

### Giai đoạn 6: loại bỏ bridge options

Trong quá trình migration, có thể tạm dùng --add-reads, --add-exports hoặc --add-opens để chẩn đoán hoặc duy trì tương thích. Ghi lại từng option, module/package liên quan và lý do.

Khi module descriptor và code đã được sửa đúng, loại bỏ từng option rồi chạy lại test. Mục tiêu là descriptor thể hiện chính xác dependency và ranh giới truy cập, không phải giữ danh sách flags đặc biệt vô thời hạn.

## 5. Tạo và review module-info.java bằng jdeps

### --generate-module-info

Cú pháp:

~~~bash
jdeps --generate-module-info output-dir library.jar
~~~

jdeps phân tích JAR và tạo module-info.java dựa trên dependency/package mà nó quan sát được. Có thể dùng kết quả làm điểm bắt đầu để chuyển thư viện thành explicit module.

Ví dụ, sau khi chạy lệnh, xem file module-info.java được sinh trong thư mục output. Cấu trúc thư mục và module name thực tế phụ thuộc tên module được suy ra từ JAR.

Cần review các điểm sau:

- Module name có ổn định và phù hợp quy ước tên chưa?
- requires có đúng dependency trực tiếp không?
- Package nào thực sự là public API và cần exports?
- Có package nội bộ nào đang bị export rộng quá mức?
- API công khai có để lộ type từ module khác không?
- Có service provider hoặc service consumer nào chưa được khai báo?
- Có framework cần reflection vào package nào?
- Có package split với một JAR/module khác không?
- Dependency có bị thiếu khi jdeps phân tích không?

Tùy chọn -q hoặc --quiet có thể ẩn thông báo missing dependencies trong output của generate-module-info. Không nên dùng chế độ quiet trong bước điều tra ban đầu vì missing dependency là thông tin cần xử lý.

### --generate-open-module

Cú pháp:

~~~bash
jdeps --generate-open-module output-dir library.jar
~~~

Lệnh tạo descriptor dạng open module. Một open module cho phép deep reflection trên tất cả package của module tại runtime.

Đây có thể là cầu nối cho thư viện phụ thuộc mạnh vào reflection, nhưng phạm vi mở rộng hơn mức cần thiết. Nếu biết framework chỉ cần truy cập một số package, nên dùng opens package to framework.module trong descriptor cuối cùng thay vì giữ open module.

### jdeps không tự quyết định thiết kế module

Phân tích bytecode có thể tìm thấy dependency type, nhưng không thể tự biết package nào nên trở thành API công khai, package nào chỉ là implementation, service nào được chọn động hoặc package nào framework cần mở bằng reflection.

Vì vậy, module-info.java do jdeps sinh ra phải được review cùng source, public API, tài liệu framework và test runtime.

## 6. Thiết kế các directive trong module-info.java

### requires

Khai báo module hiện tại phụ thuộc vào module khác:

~~~java
module com.example.orders {
    requires com.example.customer.api;
    requires java.sql;
}
~~~

Dùng requires cho dependency mà code module hiện tại trực tiếp sử dụng. Không thêm requires chỉ vì module đó tình cờ có trên module path.

### requires transitive

Nếu public API của module sử dụng type từ một module khác trong chữ ký public/protected, consumer của module có thể cần đọc dependency đó. Khi đó cân nhắc requires transitive:

~~~java
module com.example.orders.api {
    requires transitive com.example.customer.api;
    exports com.example.orders.api;
}
~~~

Không dùng transitive cho mọi dependency implementation. Nó mở rộng readability tới consumer và có thể làm dependency graph phức tạp.

Kết hợp jdeps --api-only với review public signatures để tìm dependency được phơi bày qua API.

### requires static

requires static khai báo dependency cần ở compile time nhưng có thể không cần ở runtime:

~~~java
module com.example.report {
    requires static java.compiler;
}
~~~

Chỉ dùng khi ứng dụng thực sự có thể chạy mà không cần module đó. Nếu code truy cập type hoặc gọi chức năng của module ở runtime, dependency vẫn phải có mặt khi đường chạy đó được thực hiện.

### exports

exports công khai package cho module khác truy cập các public type:

~~~java
module com.example.customer.api {
    exports com.example.customer.api;
}
~~~

Không export package implementation chỉ vì jdeps nhìn thấy dependency tới package đó. Dependency tham chiếu và API công khai là hai khái niệm khác nhau.

Có thể dùng qualified export để chỉ cho một số module được truy cập:

~~~java
exports com.example.customer.internal to com.example.customer.test;
~~~

Dùng qualified export khi có một lý do kiến trúc rõ ràng, chẳng hạn hỗ trợ module test hoặc một integration module cụ thể.

### opens

opens cho phép deep reflection vào package:

~~~java
module com.example.orders {
    opens com.example.orders.model to com.example.json;
}
~~~

Framework serialization, dependency injection, ORM hoặc binding có thể cần opens để truy cập member không public bằng reflection.

exports không thay thế opens: exports cho phép truy cập các public type/member theo quy tắc Java; opens cấp quyền deep reflection. Chỉ mở package mà framework thực sự cần.

### uses và provides

Nếu module tìm service bằng ServiceLoader, khai báo uses:

~~~java
uses com.example.codec.spi.Codec;
~~~

Nếu module cung cấp implementation:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.Utf8Codec;
~~~

jdeps không thể suy luận đầy đủ mọi quyết định service loading chỉ từ tham chiếu class thông thường. Hãy kiểm tra file META-INF/services, ServiceLoader.load, JDBC driver, security provider, logging provider và plugin system khi migration.

## 7. Automatic module và module name ổn định

Automatic module là cơ chế tương thích rất hữu ích khi dependency bên thứ ba chưa có module-info.class.

Ví dụ, nếu lib/legacy-json-2.4.0.jar nằm trên module path, tên module có thể được suy ra từ tên JAR. Nếu nhà phát hành đặt manifest attribute:

~~~text
Automatic-Module-Name: com.example.legacy.json
~~~

thì tên automatic module được xác định ổn định theo attribute này.

Kiểm tra module name:

~~~bash
jar --describe-module --file lib/legacy-json-2.4.0.jar
~~~

Trong module descriptor, bạn có thể tạm khai báo:

~~~java
module com.example.app {
    requires com.example.legacy.json;
}
~~~

Lưu ý:

- Tên module suy ra từ filename có thể thay đổi khi artifact đổi tên/version.
- Khi thư viện thêm module-info.java, tên module và danh sách package exported có thể thay đổi.
- Compiler có thể cảnh báo khi requires trỏ tới automatic module.
- Automatic module không cung cấp ranh giới exports/opens hẹp như explicit module.
- Không nên để public API của thư viện lâu dài phụ thuộc vào tên automatic module nếu có thể tránh.

Nếu bạn phát hành thư viện, hãy công bố tên module ổn định và kế hoạch chuyển sang explicit module. Nếu bạn là consumer, theo dõi release notes của dependency trước khi nâng cấp major/minor version.

## 8. Xử lý split package trước khi migration

**Split package** xảy ra khi nhiều artifact/module chứa class thuộc cùng một package. Ví dụ:

- legacy-core.jar chứa com.example.shared.Config.
- legacy-util.jar cũng chứa com.example.shared.Helper.

Trong classpath, hai JAR có thể cùng đóng góp class cho package đó. Khi chuyển sang named modules, package ownership và module readability được kiểm soát chặt hơn; split package có thể gây lỗi compile, resolution hoặc module layer.

Cách xử lý:

1. Dùng jdeps -verbose:package để phát hiện quan hệ package giữa các JAR.
2. Dùng jar --describe-module để xem package mà từng module chứa.
3. Xác định artifact nào sở hữu package và API nào thực sự cần.
4. Nếu có thể, hợp nhất các class liên quan vào một module.
5. Hoặc relocate package bằng quy trình build/shading có kiểm soát, cập nhật mọi reference và resource.
6. Nếu không thể sửa ngay, giữ các JAR liên quan trên classpath trong một giai đoạn chuyển tiếp, trước khi modularize phần phụ thuộc vào chúng.

Không nên tạo hai explicit modules cùng sở hữu một package chỉ để giữ nguyên cấu trúc JAR cũ. Module system cần ranh giới package/module rõ ràng.

## 9. Reflection và các bridge options trong migration

Một ứng dụng có thể compile thành công nhưng runtime thất bại khi framework truy cập field/method không public bằng reflection.

Phân biệt các option:

| Option | Tác dụng | Trường hợp thường gặp |
|---|---|---|
| --add-reads | Thêm cạnh readability giữa hai module | Module cần đọc module khác tạm thời |
| --add-exports | Export package của source module cho target module | Truy cập public type trong package không được export |
| --add-opens | Open package của source module cho deep reflection từ target | Framework cần truy cập member không public |
| open module | Mở tất cả package của module cho deep reflection | Thư viện cũ phụ thuộc reflection rộng |

Ví dụ runtime bridge cho code classpath:

~~~bash
java --add-opens com.example.app/com.example.app.model=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Ví dụ export một package cho module cụ thể:

~~~bash
java --add-exports java.management/sun.management=com.example.monitor -m com.example.monitor/com.example.monitor.Main
~~~

Các option này thay đổi quyền truy cập ở runtime (và một số option có biến thể compiler). Chúng có thể giúp ứng dụng tiếp tục chạy trong lúc migration, nhưng không biến internal API thành API được hỗ trợ và không thay thế descriptor tốt.

Quy trình tốt là ghi lại bridge option, xác định framework/module cần quyền đó, sửa code hoặc module descriptor, rồi loại bỏ option khi test đã pass.

## 10. Kiểm tra JDK internal API khi chuyển JDK và module

JDK internal API không phải API Java SE được hỗ trợ ổn định. Ví dụ package sun.* hoặc com.sun.* có thể thay đổi hoặc bị đóng gói mạnh hơn giữa các release.

Chạy:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

jdeps có thể xác định class tham chiếu internal API và gợi ý API thay thế nếu biết được.

Ví dụ, nếu code dùng sun.misc.BASE64Encoder, có thể thay bằng java.util.Base64:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64Example {
    public static void main(String[] args) {
        String input = "Java";
        String encoded = Base64.getEncoder().encodeToString(
                input.getBytes(StandardCharsets.UTF_8));
        System.out.println(encoded);
    }
}
~~~

Compile và chạy:

~~~bash
javac --release 17 -d out src/Base64Example.java
java -cp out Base64Example
~~~

Output chính xác:

~~~text
SmF2YQ==
~~~

Không nên giữ dependency internal API bằng cách thêm --add-exports hoặc --add-opens lâu dài. Hãy ưu tiên API công khai, tài liệu hóa và được hỗ trợ.

## 11. Ví dụ thực hành: chuyển hai phần của ứng dụng thành named modules

Ví dụ này tạo hai module: thư viện cung cấp API và ứng dụng sử dụng API đó.

### Cấu trúc source

~~~text
project/
└── src/
    ├── com.example.library/
    │   ├── module-info.java
    │   └── com/example/library/api/MessageFormatter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

### Module thư viện

File src/com.example.library/module-info.java:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

File src/com.example.library/com/example/library/api/MessageFormatter.java:

~~~java
package com.example.library.api;

public class MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
~~~

Module này chỉ export package API. Consumer không thể truy cập package nội bộ nếu không được export.

### Module ứng dụng

File src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.library.api.MessageFormatter;

public class Main {
    public static void main(String[] args) {
        MessageFormatter formatter = new MessageFormatter();
        System.out.println(formatter.format("JPMS"));
        System.out.println("module-migration-ok");
    }
}
~~~

### Biên dịch module

Chạy từ thư mục project với JDK 17 trở lên:

~~~bash
javac --module-source-path src -d mods -m com.example.library,com.example.app
~~~

Compiler tìm module-info.java trong từng thư mục module, resolve requires và biên dịch các module được chỉ định.

### Phân tích module graph

~~~bash
jdeps --module-path mods --module com.example.app --list-deps
~~~

Kiểm tra descriptor và dependency graph:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Kết quả phải thể hiện app phụ thuộc vào library và java.base. Nếu có dependency dư thừa hoặc module descriptor sai, review output trước khi tiếp tục.

### Chạy trên module path

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Output chính xác:

~~~text
Hello, JPMS
module-migration-ok
~~~

Đây là ví dụ migration tối giản: ứng dụng đọc API qua requires và package được export. Trong dự án thực tế, hãy thêm service, reflection, resources, test module và dependency bên thứ ba vào module graph theo nhu cầu thật.

## 12. Kiểm tra module sau migration

Sau khi thêm module descriptor, chạy các lệnh:

### Xem dependency của module

~~~bash
jdeps --module-path mods --module com.example.app --list-deps
~~~

### Kiểm tra module graph và qualified exports

~~~bash
jdeps --module-path mods --check com.example.app
~~~

--check in module descriptor, dependency sau phân tích và graph sau transition reduction; nó cũng nhận diện qualified exports không được sử dụng.

### Kiểm tra module descriptor trong JAR

~~~bash
jar --describe-module --file build/com.example.app.jar
~~~

Xác nhận tên module, requires, exports, opens, uses và provides như thiết kế.

### Hiển thị quá trình module resolution

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Lệnh này giúp xem module nào được resolve khi ứng dụng khởi động. Nó hữu ích khi dependency không được tìm thấy hoặc provider module không được đưa vào configuration.

### Tìm dependency còn thiếu

~~~bash
jdeps --missing-deps --module-path mods --class-path "lib/*" app.jar
~~~

Đối chiếu classpath và module path với build thực tế. Một dependency bị thiếu trong phân tích có thể do đầu vào chưa đầy đủ, không nhất thiết là lỗi trong source.

## 13. Service provider trong migration

Một thư viện cũ có thể đăng ký provider qua file:

~~~text
META-INF/services/com.example.codec.spi.Codec
~~~

Khi chuyển sang explicit module, cần khai báo service consumer/provider trong module descriptor:

Consumer:

~~~java
uses com.example.codec.spi.Codec;
~~~

Provider:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.impl.Utf8Codec;
~~~

Nếu ứng dụng được đóng gói thành runtime image bằng jlink, hãy kiểm tra service binding. Tùy kiến trúc, có thể cần --bind-services để đưa provider module vào image.

Đừng giả định jdeps tự sinh đầy đủ uses/provides chỉ từ class reference. Kiểm tra service configuration files, JDBC driver, security provider, logging implementation và plugin registry.

## 14. Kiểm thử migration theo chức năng

Sau khi compile được trên module path, chạy các test sau:

| Khu vực | Nội dung cần kiểm tra |
|---|---|
| Startup | Main module/class và launcher hoạt động |
| Class loading | Không có ClassNotFoundException hoặc NoClassDefFoundError |
| API access | Consumer chỉ dùng package được export |
| Reflection | ORM, JSON binding, DI và serializer truy cập đúng package được opens |
| ServiceLoader | Tất cả provider cần thiết được tìm và khởi tạo |
| Resource | Properties, ResourceBundle, template và file cấu hình được tìm thấy |
| Serialization | Đọc/ghi dữ liệu cũ và mới tương thích |
| Native code | JNI/JNA load đúng thư viện trên OS/architecture đích |
| Security | TLS, certificate và security provider hoạt động |
| Test framework | Test module, annotation processor và plugin build vẫn hoạt động |
| Packaging | JAR, module path, jlink/jpackage và launcher đúng cấu hình |
| Compatibility | Hành vi API và kết quả nghiệp vụ giữ đúng baseline |

Chạy test trên module path thực tế. Một test vẫn chạy trên classpath không chứng minh explicit modules đã được cấu hình đúng.

## 15. Những lỗi thường gặp khi migration

### Module không tìm thấy

**Dấu hiệu:** compiler hoặc launcher báo module not found.

**Nguyên nhân:** thiếu JAR trên module path, sai module name hoặc dependency không được resolve.

**Cách xử lý:** dùng jar --describe-module để xác nhận module name; kiểm tra module path và requires.

### Package không được export

**Dấu hiệu:** compiler báo package không được export hoặc type không accessible.

**Nguyên nhân:** module có package nhưng không export package đó cho consumer.

**Cách xử lý:** chỉ thêm exports nếu package thực sự là API cần công khai; nếu là implementation, sửa consumer để dùng API công khai.

### Framework không thể reflection

**Dấu hiệu:** InaccessibleObjectException hoặc lỗi truy cập member trong ORM/serializer/DI.

**Nguyên nhân:** package chưa được opens cho framework module.

**Cách xử lý:** thêm opens package to framework.module; dùng --add-opens tạm thời để xác nhận nguyên nhân rồi chuyển vào module descriptor khi phù hợp.

### Split package

**Dấu hiệu:** lỗi package thuộc nhiều module hoặc module resolution thất bại.

**Nguyên nhân:** nhiều JAR/module chứa class trong cùng package.

**Cách xử lý:** hợp nhất package owner, relocate class hoặc giữ dependency trên classpath trong giai đoạn chuyển tiếp.

### Automatic module name thay đổi

**Dấu hiệu:** requires module name không còn tìm thấy sau khi cập nhật thư viện.

**Nguyên nhân:** tên module suy ra từ tên file JAR hoặc thư viện đã đổi descriptor.

**Cách xử lý:** dùng Automatic-Module-Name ổn định khi có thể; cập nhật requires theo module name được nhà phát hành công bố; ưu tiên explicit module.

### ServiceLoader không tìm thấy provider

**Dấu hiệu:** provider list rỗng hoặc ServiceConfigurationError.

**Nguyên nhân:** thiếu uses/provides, provider module không được resolve hoặc service metadata không được chuyển đổi.

**Cách xử lý:** kiểm tra META-INF/services, module descriptor, module path và service binding.

### jdeps không báo dependency mà runtime vẫn lỗi

**Dấu hiệu:** jdeps không báo lỗi nhưng ứng dụng thất bại khi dùng plugin hoặc reflection.

**Nguyên nhân:** dependency được nạp bằng tên động, reflection, cấu hình hoặc native library.

**Cách xử lý:** rà soát framework, resource, service provider và native dependency; thêm integration test cho từng đường chạy.

### Giữ quá nhiều --add-opens hoặc --add-exports

**Dấu hiệu:** ứng dụng chỉ chạy khi có danh sách flags lớn.

**Nguyên nhân:** migration chưa hoàn tất hoặc framework vẫn phụ thuộc implementation detail.

**Cách xử lý:** xác định từng flag, nâng cấp framework, sửa module descriptor và loại bỏ flag theo từng đợt.

## 16. Chiến lược migration được khuyến nghị

Một chiến lược an toàn thường gồm:

1. Chạy ứng dụng và test trên JDK mục tiêu trước khi thay đổi kiến trúc.
2. Cập nhật build tool và thư viện bên thứ ba.
3. Chạy jdeps trên toàn bộ ứng dụng và dependency.
4. Xử lý JDK internal API và dependency bị thiếu.
5. Xác định automatic module name, split package, service và reflection.
6. Modularize thư viện nền trước; dùng automatic modules làm cầu nối có thời hạn.
7. Tạo và review module-info.java bằng jdeps khi phù hợp.
8. Modularize ứng dụng, khai báo requires/exports/opens/uses/provides.
9. Compile, chạy và test trên module path.
10. Dùng jdeps --check và java --show-module-resolution để kiểm tra graph.
11. Gỡ dần --add-reads, --add-exports và --add-opens tạm thời.
12. Chỉ tạo runtime image sau khi module graph và integration test ổn định.
13. Lưu lại module list, test result và lệnh build để có thể tái lập migration.

Nếu một thư viện chưa thể modularize, có thể giữ nó dưới dạng automatic module trong giai đoạn chuyển tiếp. Ghi rõ owner, version và kế hoạch chuyển sang explicit module; tránh để module name suy ra từ filename trở thành dependency công khai lâu dài.

## 17. Giới hạn của jdeps trong migration

jdeps phân tích tham chiếu bytecode tĩnh. Nó không thể đảm bảo tìm thấy tất cả dependency trong các trường hợp:

- Reflection hoặc Class.forName với tên class lấy từ cấu hình.
- ServiceLoader, plugin hoặc provider được chọn động.
- Framework tự quét package/module.
- Resource bundle, template, file properties và metadata.
- JNI/JNA và thư viện native của hệ điều hành.
- Class được sinh động hoặc tải từ network.
- Truy cập file, network, process và cấu hình môi trường.

jdeps cũng không quyết định package nào là API công khai, package nào nên opens, service nào cần provides hoặc dependency nào có ý nghĩa nghiệp vụ.

Do đó, migration cần kết hợp phân tích tĩnh, review kiến trúc, kiểm tra descriptor, test module path và integration test trong môi trường gần production.

## 18. Checklist trước khi hoàn tất migration

- [ ] Đã ghi baseline JDK, build tool, dependency và test.
- [ ] Đã chạy jdeps trên app và tất cả thư viện liên quan.
- [ ] Đã xử lý kết quả --missing-deps.
- [ ] Đã xử lý kết quả --jdk-internals.
- [ ] Đã kiểm tra public API dependency bằng --api-only.
- [ ] Đã xác nhận module name của automatic modules.
- [ ] Đã kiểm tra split package.
- [ ] Đã review module-info.java được jdeps sinh ra.
- [ ] requires chỉ bao gồm dependency cần thiết.
- [ ] requires transitive chỉ dùng khi public API phơi bày dependency.
- [ ] exports chỉ công khai package cần thiết.
- [ ] opens chỉ mở package cần deep reflection.
- [ ] uses/provides phản ánh đúng service contract.
- [ ] Đã kiểm tra module graph bằng jdeps --check.
- [ ] Đã chạy ứng dụng và test trên module path.
- [ ] Đã kiểm tra reflection, service loading, resource và native library.
- [ ] Đã loại bỏ bridge flags không còn cần.
- [ ] Đã kiểm tra packaging và runtime image nếu có.
- [ ] Đã lưu kết quả test và module descriptor trong build/release artifact.

## 19. Tài liệu tham khảo chính thức

- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — phân tích dependency, --api-only, --jdk-internals, --generate-module-info, --generate-open-module, --check và --missing-deps.
- [Java Language Specification, Java SE 26 — Chapter 7: Packages and Modules](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html) — explicit, automatic và unnamed modules; requires, exports, opens, uses và provides.
- [ModuleDescriptor API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.html) — biểu diễn module descriptor, automatic module, exports, opens và service metadata.
- [Oracle JDK Migration Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/migrate/index.html) — quy trình chuẩn bị migration, cập nhật thư viện, compile và dùng jdeps.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — module path, module resolution, --add-reads và --add-exports.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — runtime module options, --add-reads, --add-exports và --add-opens.
- [The jar Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html) — kiểm tra module descriptor bằng jar --describe-module.
- [JEP 261: Module System](https://openjdk.org/jeps/261) — thiết kế JPMS và các cơ chế migration.

jdeps hỗ trợ migration bằng cách làm rõ dependency, phát hiện rủi ro và tạo bản nháp module descriptor. Migration thành công khi module boundaries phản ánh đúng API, service và nhu cầu reflection của ứng dụng, đồng thời toàn bộ test chạy được trên module path mà không cần các bridge flags tạm thời.
