# Kiểm soát module path và module source không tin cậy

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt rủi ro của module path ở runtime với module source path ở compile time.
- Giải thích vì sao JPMS encapsulation và module descriptor không phải cơ chế sandbox.
- Kiểm soát nguồn gốc, danh tính và tính toàn vẹn của modular JAR, exploded module và source tree.
- Nhận diện automatic module, module trùng tên, module override và service provider như các điểm cần kiểm soát.
- Giảm rủi ro khi biên dịch source không tin cậy, đặc biệt là annotation processor và build plugin.
- Thiết kế quy trình kiểm tra, staging và cô lập trước khi đưa module vào JVM có quyền truy cập dữ liệu thật.

## 1. Ranh giới tin cậy của Java module system

Java Platform Module System (JPMS) tổ chức ứng dụng thành các module có tên, dependency và package boundary. Module descriptor cho biết module yêu cầu module nào, export package nào, open package nào và cung cấp hoặc sử dụng service nào.

Các quy tắc đó giúp kiểm soát khả năng nhìn thấy và truy cập giữa module. Tuy nhiên, **JPMS không phải sandbox để chạy code không tin cậy**.

Khi một class được nạp và thực thi trong JVM của ứng dụng, code đó thường chạy với quyền của process hiện tại: đọc file mà process được phép đọc, mở network connection, sử dụng credential trong environment, tạo thread hoặc gọi native code qua các cơ chế được cấp phép. Việc code nằm trong named module không tự giới hạn các quyền hệ điều hành đó.

Vì vậy, cần phân biệt ba lớp:

1. **Module boundary**: kiểm soát readability, exports, opens, package và dependency trong Java.
2. **Supply-chain trust**: xác định artifact/source đến từ đâu, có đúng phiên bản và có bị thay đổi hay không.
3. **Execution isolation**: giới hạn tài nguyên và quyền của process bằng OS account, container, VM, filesystem/network policy và các cơ chế vận hành.

Một module có descriptor hợp lệ vẫn có thể chứa code độc hại. Một JAR có chữ ký vẫn có thể chứa code nguy hiểm nếu người ký không đáng tin. Một module không export package vẫn có thể thực hiện I/O hoặc gửi dữ liệu ra mạng từ code public mà nó cung cấp.

## 2. Module path ở runtime là đầu vào thực thi

### 2.1. JVM tìm module ở đâu?

Khi chạy ứng dụng modular, launcher nhận module path qua:

~~~bash
java --module-path mods -m com.acme.app/com.acme.Main
~~~

Module path có thể chứa:

- Modular JAR có module descriptor.
- Exploded module, tức thư mục có `module-info.class` và package tree.
- JAR trở thành automatic module khi được đặt trên module path.
- Nhiều thư mục hoặc archive được phân tách theo quy tắc path của hệ điều hành.

Các module được tìm thấy sẽ tham gia vào quá trình resolve configuration. Khi module được định nghĩa trong layer và class được nạp, code trong module có thể được thực thi.

Do đó, mọi thư mục và archive trên module path là một phần của chuỗi cung ứng code. Không thêm thư mục do người dùng không tin cậy ghi được vào module path của process production.

### 2.2. Module path không phải danh sách thư viện vô hại

Một modular JAR không chỉ là metadata. Nó có thể chứa class với static initializer, constructor, service provider hoặc method được ứng dụng gọi. Những đoạn code này có thể thực hiện side effect khi được khởi tạo hoặc thực thi.

Ví dụ, class có static initializer:

~~~java
package com.acme.plugin;

public final class PluginEntry {
    static {
        // Side effect có thể xảy ra khi class được khởi tạo.
        System.out.println("Plugin initialized");
    }

    public static void start() {
        System.out.println("Plugin started");
    }
}
~~~

Việc chỉ resolve module không đồng nghĩa mọi class trong module đều được khởi tạo ngay. Nhưng khi ứng dụng nạp và khởi tạo class, gọi service provider hoặc gọi API của plugin, code có thể chạy.

Không dựa vào việc “chưa gọi main class” để kết luận module hoàn toàn không có side effect. Các class loader, framework và service discovery có thể làm phát sinh việc nạp hoặc khởi tạo code trong những giai đoạn khác nhau.

## 3. Kiểm soát module identity và nguồn artifact

### 3.1. Tên module không chứng minh nguồn gốc

Một module có tên `com.acme.payment` không tự chứng minh nó được phát hành bởi tổ chức sở hữu namespace đó. Tên module là định danh để resolver và code tham chiếu; nó không phải chữ ký số hay bằng chứng xuất xứ.

Trước khi đưa artifact vào module path, cần xác định:

- Artifact đến từ repository hoặc build pipeline nào?
- Group, artifact, version và module name có khớp manifest phát hành đã duyệt không?
- File có đúng hash đã được ghi nhận không?
- Ai có quyền publish hoặc thay thế artifact?
- Có dependency transitive hoặc module mới nào được đưa vào ngoài dự kiến không?

Không dùng tên file, tên thư mục hoặc module name làm bằng chứng duy nhất cho độ tin cậy.

### 3.2. Xác minh descriptor và module name

Có thể xem descriptor của modular JAR bằng:

~~~bash
jar --describe-module --file libs/acme-plugin.jar
~~~

Với JAR không có explicit module descriptor, công cụ có thể hiển thị tên automatic module và các package được suy ra.

Kiểm tra này giúp phát hiện module name, requires, exports, opens, uses và provides được khai báo. Nó không chứng minh bytecode an toàn hoặc artifact đến từ nhà phát hành đáng tin.

Với module đang chạy, có thể kiểm tra danh sách module quan sát được:

~~~bash
java --list-modules
~~~

Để xem quá trình resolve trong một lần khởi chạy:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.Main
~~~

Thông tin resolution giúp điều tra module nào được chọn và dependency được nối ra sao. Hãy lưu log này trong môi trường kiểm thử hoặc điều tra sự cố khi cần tái hiện cấu hình runtime.

### 3.3. Tránh module name collision

Nếu nhiều nguồn cung cấp module cùng tên, cấu hình module path có thể trở nên mơ hồ hoặc bị resolve theo một nguồn khác với dự kiến. Không dựa vào thứ tự tình cờ của thư mục để chọn phiên bản.

Quy tắc vận hành nên là:

- Một module name chỉ có một artifact/version được phê duyệt trong runtime image.
- Không trộn thư mục build output cũ và mới.
- Không cho phép thư mục ghi được bởi người dùng không tin cậy nằm trước thư mục artifact đã xác minh.
- Kiểm tra module name và hash trước khi dựng module path cuối cùng.

Đặt artifact vào một staging directory riêng sau khi xác minh, rồi chạy JVM bằng đúng directory đó.

## 4. Automatic module và unnamed module cần được quản lý riêng

### 4.1. Automatic module

Một JAR không có `module-info.class` khi được đặt trên module path có thể trở thành automatic module. Tên module thường được suy ra từ manifest `Automatic-Module-Name` nếu có, nếu không sẽ suy ra từ tên JAR.

Automatic module có khả năng đọc các module khác và export các package của nó theo quy tắc automatic module. Đây là cơ chế chuyển tiếp để thư viện cũ có thể tham gia module path.

Vì phạm vi readability và exports rộng hơn explicit module thông thường, không nên xem automatic module là lựa chọn mặc định cho một plugin không tin cậy. Hãy xác minh JAR, kiểm tra module name và đánh giá dependency trước khi cho phép nó tham gia runtime.

### 4.2. Unnamed module và classpath

Code trên classpath thuộc unnamed module. Việc đưa thư viện lên classpath không biến nó thành code an toàn hơn. Nó chỉ thay đổi cách tổ chức và encapsulation của code.

Nếu ứng dụng trộn module path và classpath, hãy lập danh sách rõ:

- JAR nào là named/automatic module?
- JAR nào nằm trong classpath?
- Module nào có readability tới unnamed module?
- Có cờ `--add-reads`, `--add-exports` hoặc `--add-opens` nào đang mở thêm quyền không?

Không dùng classpath như một vùng “plugin không cần kiểm soát”. Code trên classpath vẫn chạy với quyền của process.

## 5. Các tùy chọn làm thay đổi nguồn module cần bảo vệ

Ngoài `--module-path`, một số launcher option có thể thay đổi tập module hoặc nội dung được nạp:

| Tùy chọn | Tác động | Rủi ro cần quản lý |
|---|---|---|
| `--upgrade-module-path` | Cho phép module trên upgrade path thay thế module hệ thống tương ứng | Có thể thay đổi implementation của module JDK |
| `--patch-module` | Bổ sung/thay thế class hoặc resource thuộc module | Runtime khác artifact đã phát hành |
| `--add-modules` | Thêm module vào graph cần resolve | Làm tăng tập code có thể được sử dụng |
| `--add-reads` | Thêm readability edge | Tạo dependency ngoài descriptor |
| `--add-exports` | Mở public package cho target | Mở rộng bề mặt API truy cập |
| `--add-opens` | Cho phép deep reflection | Làm lộ chi tiết triển khai cho target |

Không cho người dùng hoặc plugin không tin cậy tự cung cấp JVM arguments cho process có quyền cao. Một cờ như `--patch-module` hoặc `--upgrade-module-path` có thể thay đổi code được JVM nạp; cờ mở package có thể phá ranh giới encapsulation mà ứng dụng dựa vào.

Nên lưu launcher arguments trong cấu hình được quản lý, review và version hóa.

## 6. Module source path ở compile time có rủi ro khác

### 6.1. --module-source-path chỉ định source tree

Khi biên dịch nhiều module, javac có thể dùng:

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
~~~

Trong đó:

- `--module-source-path` chỉ định vị trí và cấu trúc source của các module.
- `-m` chọn module cần biên dịch.
- `-d` chọn nơi ghi output.

Source tree là đầu vào của compiler. Bản thân việc biên dịch Java source thông thường không có nghĩa các method trong source được chạy. Nhưng build pipeline có thể thực thi những thành phần khác trong lúc compile.

### 6.2. Annotation processor là code chạy trong build process

Annotation processor là Java code được javac nạp để xử lý annotation. Processor có thể đọc file, ghi file, truy cập environment, tạo source hoặc thực hiện các thao tác khác với quyền của process biên dịch.

Ví dụ một lệnh có processor path:

~~~bash
javac --processor-path tools/processor.jar ^
    -d out ^
    --module-source-path src ^
    -m com.acme.app
~~~

Nếu `processor.jar` không tin cậy, code processor có thể chạy trong máy build. Đây là rủi ro khác với việc class được tạo ra sau compile.

Các điểm cần kiểm soát:

- Không nạp annotation processor từ dependency không được phê duyệt.
- Dùng `--processor-path` hoặc `--processor-module-path` rõ ràng thay vì để processor được phát hiện từ nguồn không kiểm soát.
- Chỉ định processor cần thiết bằng `-processor` khi phù hợp.
- Nếu không cần annotation processing, cân nhắc `-proc:none` để tắt việc chạy processor.
- Kiểm soát plugin Gradle/Maven và script build vì chúng cũng có thể thực thi code trong build process.

Ví dụ tắt annotation processing khi compile source không cần processor:

~~~bash
javac -proc:none -d out --module-source-path src -m com.acme.app
~~~

`-proc:none` không phải sandbox cho compiler và không vô hiệu hóa mọi code có thể chạy trong build. Build plugin, compiler wrapper, script, công cụ generate code hoặc dependency task vẫn cần được quản lý.

### 6.3. Source không tin cậy có thể gây tiêu hao tài nguyên

Ngay cả khi không có processor, source code có thể được tạo để làm compiler tiêu tốn CPU, memory hoặc disk: file cực lớn, cấu trúc generic phức tạp, annotation lồng sâu hoặc số lượng source bất thường.

Với source không tin cậy, hãy giới hạn:

- CPU time và memory của build worker.
- Thời gian chạy và dung lượng output.
- Số lượng file và kích thước source/archive.
- Quyền ghi ra ngoài workspace.
- Network access trong build nếu không cần.
- Quyền truy cập credential và secret của pipeline.

## 7. Kiểm tra dependency và nội dung trước khi sử dụng

Có thể dùng công cụ JDK để thu thập thông tin trước khi đưa module vào runtime.

### 7.1. Kiểm tra module descriptor

~~~bash
jar --describe-module --file libs/acme-plugin.jar
~~~

Xem module name, package, requires, exports, opens và service declaration. Nếu descriptor không đúng với manifest phát hành hoặc chính sách dependency, dừng việc đưa artifact vào staging.

### 7.2. Kiểm tra dependency tĩnh

~~~bash
jdeps --print-module-deps --module-path libs libs/acme-plugin.jar
~~~

`jdeps` giúp phân tích dependency được thể hiện trong bytecode. Nó không phát hiện đầy đủ hành vi reflection động, tải class theo tên, truy cập file/network hay mọi dependency runtime.

Nếu muốn phát hiện tham chiếu tới JDK internal API:

~~~bash
jdeps --jdk-internals libs/acme-plugin.jar
~~~

Kết quả là đầu mối đánh giá tương thích và migration. Đây không phải công cụ chứng minh code an toàn.

### 7.3. Xác minh tính toàn vẹn artifact

Có thể ghi nhận hash của artifact đã duyệt:

~~~bash
sha256sum libs/acme-plugin.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\libs\acme-plugin.jar
~~~

Nếu sử dụng JAR signing, có thể kiểm tra chữ ký:

~~~bash
jarsigner -verify -strict -certs libs/acme-plugin.jar
~~~

Chữ ký chỉ hữu ích khi danh tính signer và certificate chain được tin cậy theo chính sách của tổ chức. Một JAR được ký không tự động trở thành an toàn; chữ ký xác nhận nguồn ký và tính toàn vẹn theo cơ chế ký, không chứng minh code không có hành vi nguy hiểm.

Nên kết hợp hash/signature với repository allowlist, provenance của build, version lock và quy trình phê duyệt dependency.

## 8. Service provider là một điểm kích hoạt code

Module descriptor có thể khai báo:

~~~java
module com.acme.plugin {
    provides com.acme.spi.PaymentProvider
        with com.acme.plugin.internal.DefaultPaymentProvider;
}
~~~

Ứng dụng có thể dùng `ServiceLoader` để tìm provider:

~~~java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    provider.process();
}
~~~

Việc phân giải service binding và việc khởi tạo/gọi provider là các thời điểm khác nhau. Khi ứng dụng duyệt hoặc sử dụng provider, constructor và method của provider có thể chạy. Không coi khai báo `provides` là metadata vô hại nếu module path chứa module không tin cậy.

Các nguyên tắc:

- Chỉ cho phép provider từ module/artifact đã phê duyệt.
- Không tự động load mọi provider tìm thấy trên module path nếu ứng dụng không cần.
- Kiểm tra module cung cấp service và version trước khi gọi.
- Thực hiện provider trong process hoặc sandbox phù hợp với mức độ tin cậy.

## 9. JPMS không thay thế process isolation

Nếu yêu cầu là chạy plugin hoặc source từ bên ngoài tổ chức, hãy thiết kế ranh giới an toàn bên ngoài module system.

Các lựa chọn thường dùng:

- **Process riêng** dưới OS account có quyền tối thiểu.
- **Container** với filesystem read-only, network policy, giới hạn CPU/memory và không mount secret.
- **VM hoặc sandbox chuyên biệt** khi cần ranh giới mạnh hơn container.
- **IPC có schema và authorization rõ ràng** để host chỉ cung cấp các capability đã chọn.
- **Timeout, quota và cancellation** cho từng request plugin.

Không truyền credential production, token CI hoặc file cấu hình nhạy cảm vào process chạy module không tin cậy. Nếu plugin cần một capability, host nên cung cấp API hoặc IPC hẹp thay vì chia sẻ toàn bộ environment và filesystem.

Security Manager từng là một cơ chế Java để giới hạn permission nhưng đã bị deprecated for removal. Không thiết kế hệ thống mới dựa vào giả định rằng JPMS hoặc Security Manager sẽ sandbox một module không tin cậy. Dùng isolation của hệ điều hành/runtime deployment làm ranh giới thực thi.

## 10. Quy trình staging an toàn cho modular artifact

Một quy trình thực tế có thể chia thành các bước:

1. **Nhận artifact/source** vào khu vực staging không có quyền production.
2. **Xác minh nguồn**: repository, publisher, version, provenance, hash và chữ ký nếu có.
3. **Kiểm tra cấu trúc**: module name, descriptor, package, dependency và service provider.
4. **Kiểm tra dependency** bằng công cụ như `jar` và `jdeps`, sau đó đối chiếu allowlist.
5. **Biên dịch trong build worker cô lập**; kiểm soát processor, plugin, network và resource quota.
6. **Chạy integration test trong process/container riêng** với dữ liệu giả và quyền tối thiểu.
7. **Đóng gói staging image bất biến** gồm đúng các module đã phê duyệt.
8. **Promote artifact đã xác minh** sang môi trường tiếp theo bằng cùng hash; không build lại âm thầm từ source khác.
9. **Quan sát runtime**: log module resolution, version, startup arguments và service provider được kích hoạt.

Một module path production nên được dựng từ một tập artifact bất biến và đã phê duyệt. Không dùng trực tiếp thư mục upload, thư mục workspace có thể bị sửa hoặc thư mục dùng chung giữa nhiều tenant.

## 11. Ví dụ: kiểm tra trước khi chạy plugin

Giả sử plugin nằm tại `incoming/payment-plugin.jar`. Có thể tổ chức kiểm tra thủ công trong staging:

~~~bash
jar --describe-module --file incoming/payment-plugin.jar
jdeps --print-module-deps --module-path approved-libs incoming/payment-plugin.jar
sha256sum incoming/payment-plugin.jar
~~~

Sau khi xác minh hash, publisher, module name và dependency theo chính sách, copy artifact vào thư mục runtime bất biến:

~~~text
runtime/
├── app/
│   └── com.acme.host/
└── approved-modules/
    ├── com.acme.spi.jar
    └── payment-plugin.jar
~~~

Chạy ứng dụng bằng module path đã duyệt:

~~~bash
java --show-module-resolution ^
    --module-path runtime/approved-modules ^
    -m com.acme.host/com.acme.host.Main
~~~

Các lệnh trên minh họa bước kiểm tra và staging. Trong hệ thống thực tế, cần tự động hóa việc so sánh hash/provenance với metadata đã được phê duyệt và đảm bảo process chạy không có quyền vượt quá mức cần thiết.

Nếu plugin đến từ người dùng hoặc tenant bên ngoài, chỉ xác minh hash không đủ để cho phép chạy trong host process. Hãy chạy plugin trong process/container riêng và giới hạn dữ liệu, network, filesystem mà nó có thể truy cập.

## 12. Checklist review

Trước khi cho module hoặc source tham gia build/runtime, hãy xác nhận:

- [ ] Nguồn artifact/source và publisher đã được xác minh.
- [ ] Module name và descriptor khớp manifest phát hành.
- [ ] Không có module name collision hoặc module override ngoài dự kiến.
- [ ] Automatic module và classpath dependency đã được nhận diện.
- [ ] Module path chỉ chứa thư mục/archive đã phê duyệt và không cho người dùng không tin cậy ghi.
- [ ] `--patch-module` và `--upgrade-module-path` được kiểm soát như thay đổi code.
- [ ] Annotation processor và build plugin được phê duyệt; tắt processing nếu không cần.
- [ ] Dependency, service provider và internal JDK API đã được kiểm tra ở mức phù hợp.
- [ ] Hash/signature/provenance được xác minh theo chính sách.
- [ ] Build và runtime không nhận credential hoặc quyền hệ điều hành vượt nhu cầu.
- [ ] Plugin không tin cậy được chạy trong process/container có isolation và quota.
- [ ] Runtime image bất biến và có thể tái hiện bằng hash/version.

## Kết luận

Module path quyết định những module nào có thể tham gia runtime; module source path quyết định source nào được compiler xử lý. Cả hai đều là đầu vào cần kiểm soát. Ở runtime, modular JAR vẫn là executable code chạy với quyền của process. Ở compile time, annotation processor và build plugin có thể thực thi code ngay trên máy build.

**JPMS bảo vệ ranh giới truy cập giữa module, không xác thực nguồn gốc và không sandbox code độc hại.** Hãy kết hợp xác minh provenance/integrity, kiểm soát dependency và launcher arguments, build worker cô lập, module path bất biến và process/container isolation để bảo vệ ứng dụng.
