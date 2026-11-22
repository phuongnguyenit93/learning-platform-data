# Kiểm thử runtime image tạo bằng jlink

## Mục tiêu

Sau bài này, bạn có thể lập kế hoạch kiểm thử custom runtime image do jlink tạo ra; xác minh image chứa đúng module và phiên bản Java; chạy ứng dụng bằng chính runtime được đóng gói; phát hiện module, service provider, locale, security provider hoặc thư viện native bị thiếu; kiểm tra launcher và môi trường triển khai; và đưa các bài kiểm thử runtime image vào CI trước khi phát hành.

## 1. Runtime image là gì?

**Runtime image** là một môi trường Java có thể chạy ứng dụng, được đóng gói thành một thư mục độc lập. Với jlink, bạn chọn các module cần thiết và công cụ liên kết chúng cùng dependency bắc cầu để tạo image riêng.

Một runtime image thường có:

- bin/java: Java launcher.
- lib/modules: kho chứa các module đã liên kết vào image.
- conf: cấu hình runtime.
- legal: thông tin giấy phép của các thành phần được đóng gói.
- release: metadata của bản runtime.
- Các file khác tùy hệ điều hành, phiên bản JDK và tùy chọn build.

Cấu trúc nội bộ có thể thay đổi theo nền tảng và phiên bản. Khi kiểm thử, hãy gọi launcher công khai trong bin và kiểm tra hành vi của ứng dụng thay vì phụ thuộc vào mọi file nội bộ.

Runtime image do jlink tạo thường nhỏ hơn JDK đầy đủ vì chỉ chứa các module được chọn và dependency cần thiết. Nó có thể không có công cụ phát triển như javac, jar, javadoc, jcmd hoặc jdeps. Các công cụ này thường được dùng ở giai đoạn build/test; runtime image bàn giao chỉ cần thành phần để chạy ứng dụng.

**Kiểm thử runtime image** là xác minh image thực sự chạy được ứng dụng trên môi trường đích với đúng tính năng, cấu hình, dependency và hành vi mong đợi. Build thành công bằng jlink chỉ chứng minh công cụ đã tạo image; nó chưa chứng minh ứng dụng chạy đúng.

## 2. Vì sao ứng dụng chạy với JDK đầy đủ nhưng lỗi với runtime image?

Các rủi ro thường gặp:

- **Thiếu module:** ứng dụng dùng XML, logging, desktop, naming, crypto hoặc API khác mà module tương ứng chưa được đưa vào image.
- **Thiếu service provider:** ứng dụng dùng ServiceLoader, JDBC driver, security provider hoặc SPI nhưng provider module không được liên kết.
- **Reflection và framework:** framework nạp class theo tên, quét package hoặc truy cập member bằng reflection mà phân tích dependency tĩnh không phát hiện đầy đủ.
- **Resource và locale:** thiếu resource bundle, locale data, charset hoặc file cấu hình.
- **TLS và security:** thiếu security provider, truststore, certificate hoặc thuật toán mà ứng dụng sử dụng.
- **Native library:** thiếu JNI/JNA library, sai kiến trúc CPU, sai ABI hoặc thiếu thư viện hệ điều hành.
- **Khác biệt môi trường:** runtime chạy trên container/server có libc, timezone, certificate store, quyền file và biến môi trường khác máy build.
- **Sai launcher:** script dùng sai main class, module path, classpath, JVM options hoặc working directory.
- **Khác phiên bản Java:** class file, API hoặc preview feature không tương thích với runtime image.

Kiểm thử phải chạy bằng chính Java executable trong image. Nếu lệnh test vô tình gọi Java từ PATH hoặc JAVA_HOME của JDK đầy đủ, ứng dụng có thể chạy thành công dù runtime image đang thiếu module.

## 3. Xác định phạm vi và baseline kiểm thử

Trước khi test, ghi lại thông tin artifact:

| Thông tin | Cần xác nhận |
|---|---|
| JDK dùng để tạo image | Vendor, phiên bản đầy đủ và update level |
| Java feature release | Ví dụ 17, 21 hoặc 25 |
| Hệ điều hành | Windows, Linux hoặc macOS |
| CPU architecture | x64, AArch64/ARM64 hoặc kiến trúc được hỗ trợ |
| Loại ứng dụng | Modular application hay classpath application |
| Module roots | Module ứng dụng và module JDK được yêu cầu |
| Service providers | JDBC, logging, crypto, plugin hoặc SPI provider |
| Tùy chọn jlink | --bind-services, compression, locale, launcher và plugin |
| Runtime target | Máy vật lý, VM, container hoặc package cài đặt |
| Cấu hình runtime | JVM flags, system properties, environment variables và file cấu hình |

Image được tạo trên Linux x64 không phải artifact có thể mang sang Windows hoặc macOS rồi chạy. Runtime image có thành phần native và được tạo cho nền tảng cụ thể. Hãy build/test image trên từng OS và architecture mà sản phẩm hỗ trợ.

Nếu sản phẩm phát hành nhiều biến thể runtime, mỗi biến thể là một artifact cần được kiểm thử độc lập. Lưu module list và runtime properties làm baseline để so sánh giữa các lần build.

## 4. Phân tích dependency trước khi tạo image

Kiểm thử hiệu quả bắt đầu từ việc xác định module mà ứng dụng cần.

### Dùng jdeps

jdeps phân tích dependency package/class của ứng dụng và có thể in danh sách module JDK cần thiết:

~~~bash
jdeps --print-module-deps app.jar
~~~

Nếu cần chọn phiên bản của multi-release JAR:

~~~bash
jdeps --multi-release 17 --print-module-deps app.jar
~~~

Nếu ứng dụng cần thư viện ngoài JAR chính, chỉ định classpath tương ứng:

~~~bash
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

Với ứng dụng modular, chỉ định module path và module cần phân tích:

~~~bash
jdeps --module-path mods --print-module-deps --module com.example.app
~~~

Kết quả --print-module-deps là danh sách module dependency dạng phân tách bằng dấu phẩy. Dùng kết quả này để hỗ trợ quyết định --add-modules khi tạo image; module ứng dụng vẫn cần được đưa vào root modules nếu đó là modular application.

### Giới hạn của phân tích tĩnh

jdeps không bảo đảm tìm thấy mọi dependency được nạp lúc chạy. Cần rà soát thủ công nếu ứng dụng sử dụng:

- Class.forName, reflection hoặc tên class lấy từ cấu hình.
- Framework tự quét classpath/module path.
- ServiceLoader, plugin hoặc provider được đăng ký động.
- JDBC driver được nạp qua SPI.
- JNI/JNA và native library.
- Resource bundle, charset, locale hoặc file resource được tạo tên lúc chạy.
- Java serialization hoặc framework phụ thuộc vào metadata/reflection.

Không dùng --ignore-missing-deps để che lỗi dependency trong bước xác nhận cuối. Nếu dùng tùy chọn này trong phân tích ban đầu, hãy điều tra từng dependency bị thiếu và chứng minh ứng dụng không cần nó.

### Kiểm tra service provider

Nếu ứng dụng cần provider cho một service, jlink có thể gợi ý module cung cấp service đó. Ví dụ với security provider có sẵn trong JDK:

~~~bash
jlink --suggest-providers java.security.Provider
~~~

Với provider nằm trong thư viện ứng dụng, cần đưa module chứa provider vào module path khi chạy lệnh gợi ý. Tên service phải là interface mà ứng dụng thực sự sử dụng.

Khi cần liên kết các provider được phát hiện qua service binding, tạo image với:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output image
~~~

--bind-services yêu cầu jlink liên kết service provider module cùng dependency của chúng. Nếu bỏ tùy chọn này, image có thể không chứa provider mà ứng dụng tìm bằng ServiceLoader, dù ứng dụng vẫn biên dịch thành công.

## 5. Kiểm tra image ngay sau khi tạo

Thực hiện các kiểm tra cơ bản trước khi chạy test nghiệp vụ.

### Xác minh image tồn tại và có launcher

Linux/macOS:

~~~bash
test -x image/bin/java
~~~

Windows PowerShell:

~~~powershell
Test-Path .\image\bin\java.exe
~~~

Nếu launcher không tồn tại hoặc không chạy được, image chưa thể dùng làm runtime.

### Kiểm tra phiên bản Java của chính image

Linux/macOS:

~~~bash
./image/bin/java --version
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --version
~~~

Đối chiếu output với phiên bản JDK dùng để tạo image và phiên bản runtime mà sản phẩm yêu cầu. Đừng chỉ chạy java --version vì lệnh đó có thể trỏ đến JDK khác trong PATH.

### Kiểm tra danh sách module

Linux/macOS:

~~~bash
./image/bin/java --list-modules
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --list-modules
~~~

Xác nhận:

- Có module ứng dụng nếu đây là modular runtime image.
- Có các module JDK mà ứng dụng cần.
- Có provider module cần thiết nếu sử dụng service binding.
- Không có module ngoài dự kiến nếu mục tiêu là giảm kích thước image.

Danh sách module không nhất thiết giống JDK đầy đủ. Điều quan trọng là khớp với module baseline đã được review và test.

### Kiểm tra tính hợp lệ của module graph

Linux/macOS:

~~~bash
./image/bin/java --validate-modules
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --validate-modules
~~~

Lệnh này yêu cầu launcher xác thực các module mà runtime nhìn thấy rồi kết thúc. Nếu có xung đột hoặc lỗi module, xử lý trước khi chạy test ứng dụng. Lệnh thành công không thay thế smoke test hay integration test.

### Kiểm tra runtime properties

Linux/macOS:

~~~bash
./image/bin/java -XshowSettings:properties -version
~~~

Đọc các thuộc tính java.home, java.version, java.vendor, os.name và os.arch. java.home cần trỏ vào runtime image đang kiểm tra. Lệnh này khởi chạy một JVM kiểm tra riêng; nó không chứng minh ứng dụng có thể chạy.

## 6. Ví dụ thực hành: tạo và kiểm thử runtime image

Ví dụ sau tạo một modular application nhỏ, liên kết runtime image rồi chạy ứng dụng bằng Java nằm bên trong image.

### Cấu trúc source

~~~text
project/
└── src/
    └── com.example.runtimecheck/
        ├── module-info.java
        └── com/example/runtimecheck/Main.java
~~~

File src/com.example.runtimecheck/module-info.java:

~~~java
module com.example.runtimecheck {
}
~~~

File src/com.example.runtimecheck/com/example/runtimecheck/Main.java:

~~~java
package com.example.runtimecheck;

public class Main {
    public static void main(String[] args) {
        System.out.println("runtime-image-ok");
        System.out.println("args=" + String.join(",", args));
    }
}
~~~

Ứng dụng chỉ dùng java.base, là module nền tảng luôn có trong Java runtime.

### Biên dịch module

Mở terminal tại thư mục project:

~~~bash
javac --module-source-path src -d mods -m com.example.runtimecheck
~~~

Sau lệnh này, module đã biên dịch nằm trong:

~~~text
mods/
└── com.example.runtimecheck/
    ├── module-info.class
    └── com/example/runtimecheck/Main.class
~~~

### Tạo runtime image trên Linux/macOS

Giả sử JAVA_HOME trỏ đến JDK 17 trở lên:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.runtimecheck \
  --launcher check=com.example.runtimecheck/com.example.runtimecheck.Main \
  --output image
~~~

Trong PowerShell trên Windows, dấu phân tách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.runtimecheck --launcher check=com.example.runtimecheck/com.example.runtimecheck.Main --output image
~~~

Tùy chọn --launcher tạo một launcher riêng tên check cho module và main class. Tên file launcher trên đĩa phụ thuộc hệ điều hành.

### Kiểm tra runtime image

Linux/macOS:

~~~bash
./image/bin/java --version
./image/bin/java --list-modules
./image/bin/java --validate-modules
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --version
.\image\bin\java.exe --list-modules
.\image\bin\java.exe --validate-modules
~~~

Xác nhận danh sách module có com.example.runtimecheck và java.base. --validate-modules hoàn tất mà không báo lỗi.

### Chạy ứng dụng bằng Java trong image

Linux/macOS:

~~~bash
./image/bin/java -m com.example.runtimecheck/com.example.runtimecheck.Main one two
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe -m com.example.runtimecheck/com.example.runtimecheck.Main one two
~~~

Output chính xác:

~~~text
runtime-image-ok
args=one,two
~~~

Đây là smoke test quan trọng: chương trình được chạy bởi runtime image vừa tạo, không phải JDK đầy đủ đang cài trên máy.

### Kiểm tra launcher riêng

Linux/macOS:

~~~bash
./image/bin/check one two
~~~

Windows PowerShell:

~~~powershell
.\image\bin\check.exe one two
~~~

Output vẫn là:

~~~text
runtime-image-ok
args=one,two
~~~

Nếu launcher riêng không chạy nhưng lệnh java -m chạy được, kiểm tra module/main class trong tùy chọn --launcher, tên launcher, file cấu hình và quyền thực thi của file trên OS.

## 7. Kiểm thử theo chức năng ứng dụng

Smoke test xác nhận runtime có thể khởi động một luồng cơ bản. Sau đó cần chạy các test bao phủ những tính năng thật sự được sử dụng.

| Nhóm kiểm thử | Tình huống cần xác minh | Dấu hiệu thiếu dependency |
|---|---|---|
| Class loading | Nạp class chính, class phụ và class được tạo tên động | ClassNotFoundException, NoClassDefFoundError |
| Resource | Đọc properties, JSON, XML, template, ảnh hoặc resource trong JAR | Resource URL null, file không tìm thấy |
| Logging | Khởi tạo logging backend/provider và ghi log | Không có provider, logging fallback |
| ServiceLoader | Tìm và khởi tạo tất cả provider cần thiết | ServiceConfigurationError hoặc không tìm thấy provider |
| JDBC | Tìm driver, mở connection, chạy query và đóng resource | No suitable driver, provider không được tìm thấy |
| TLS/crypto | Tạo SSLContext, xác thực certificate và kết nối HTTPS | NoSuchAlgorithmException, provider/certificate error |
| Locale | Format số/ngày, ResourceBundle và ngôn ngữ cần hỗ trợ | Locale data hoặc bundle không đầy đủ |
| Charset | Đọc/ghi các charset mà ứng dụng sử dụng | UnsupportedCharsetException hoặc lỗi encoding |
| XML | Parse/transform XML nếu ứng dụng dùng | Factory/provider hoặc module XML bị thiếu |
| Desktop/image | Tạo font, render ảnh, clipboard hoặc AWT/Swing nếu cần | HeadlessException, thiếu module desktop |
| JNI/JNA | Nạp và gọi native library | UnsatisfiedLinkError |
| Process/file | Đọc cấu hình, ghi file, tạo thư mục và gọi tiến trình ngoài | AccessDeniedException, file không tìm thấy |
| Network/DNS | Kết nối host, resolve DNS và timeout | UnknownHostException, ConnectException |
| Timezone | Chuyển đổi múi giờ và lịch theo yêu cầu | Dữ liệu timezone hoặc cấu hình môi trường khác |

Không cần test tất cả nhóm trên cho mọi ứng dụng. Hãy chọn theo dependency và chức năng mà sản phẩm hỗ trợ, đồng thời kiểm tra các luồng rủi ro cao của chính ứng dụng.

### Kiểm thử TLS và security provider

Một ứng dụng dùng HTTPS có thể cần các module security provider cụ thể. Hãy chạy test kết nối thật đến endpoint kiểm thử, xác minh:

- DNS và TCP connection hoạt động.
- Certificate chain được tin cậy.
- TLS protocol và cipher suite phù hợp.
- Provider cho thuật toán cần dùng có sẵn.
- Truststore và cấu hình certificate được đóng gói hoặc cung cấp đúng cách.

Đừng chỉ test SSLContext.getDefault() hoặc khởi tạo một class crypto rồi kết luận TLS production hoạt động. Cần thực hiện handshake và xác minh certificate trong môi trường gần production.

### Kiểm thử locale và charset

Nếu ứng dụng hỗ trợ nhiều ngôn ngữ, kiểm tra các locale thực tế. Khi dùng jlink --include-locales, phải đưa module jdk.localedata vào image và chỉ định module path chứa ứng dụng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app,jdk.localedata --include-locales=en,vi,ja --output image
~~~

Danh sách locale cần phù hợp yêu cầu sản phẩm. Kiểm tra định dạng ngày/giờ, số, tiền tệ và ResourceBundle bằng runtime image, vì JDK đầy đủ có thể có dữ liệu mà image tối giản không có.

## 8. Kiểm thử service binding và provider

Đối với ứng dụng dùng ServiceLoader, test cần xác nhận provider được phát hiện và hoạt động, không chỉ xác nhận module app tồn tại.

Một bài test có thể:

1. Gọi ServiceLoader.load(ServiceType.class).
2. Đếm provider tìm thấy.
3. Kiểm tra provider type hoặc metadata mong đợi.
4. Gọi một method thực tế trên từng provider cần hỗ trợ.
5. Xác minh kết quả và lỗi khởi tạo.

Nếu provider module không được liên kết, có thể cần tạo image bằng --bind-services. Đừng thêm provider module theo phỏng đoán; hãy xác định service type và provider cần thiết từ kiến trúc ứng dụng.

**Lưu ý về jpackage từ JDK 25:** runtime image do jpackage tự tạo không còn bao gồm service bindings theo mặc định. Nếu ứng dụng cần các provider được liên kết, truyền tùy chọn --bind-services cho jlink qua --jlink-options. Ví dụ:

~~~bash
jpackage --name ExampleApp --input input --main-jar app.jar --jlink-options --strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services
~~~

Khi chỉ định --jlink-options, hãy giữ các tùy chọn mặc định mà bạn vẫn cần. Nếu không, image được tạo có thể khác cấu hình dự định. Có thể tạo runtime bằng jlink riêng rồi truyền image đó cho jpackage --runtime-image.

## 9. Kiểm thử trong môi trường triển khai thực tế

Runtime image có thể hoạt động trên máy build nhưng thất bại trên máy đích vì môi trường hệ điều hành khác nhau.

### Kiểm tra container

Chạy integration test trong chính container image sẽ phát hành. Xác minh:

- Runtime image được copy vào đúng đường dẫn.
- Entrypoint gọi đúng launcher.
- User chạy container có quyền đọc/execute runtime và ghi vào thư mục dữ liệu cần thiết.
- CA certificates, timezone data và thư viện native hệ điều hành có sẵn.
- DNS, network policy, proxy và secret/config mount hoạt động.
- Container memory/CPU limit không làm thay đổi hành vi theo cách ngoài dự kiến.

Một runtime image tối giản không tự cung cấp mọi dependency của hệ điều hành. Ví dụ, native library mà JNI cần vẫn phải có trên OS/container.

### Kiểm tra kiến trúc và thư viện native

Xác minh os.name, os.arch và các native dependency trên môi trường đích. Kiểm tra đúng:

- x64 hay ARM64.
- glibc hay musl trên Linux.
- Phiên bản thư viện hệ thống mà native library yêu cầu.
- Đường dẫn tìm kiếm native library.
- Quyền execute và quyền truy cập file.

Image được tạo cho một nền tảng không thể được coi là binary portable sang nền tảng khác. Hãy build và test theo từng target platform được hỗ trợ.

### Kiểm tra Windows service hoặc Linux service

Nếu ứng dụng chạy như service, test chính lệnh/launcher mà service manager gọi. Xác minh working directory, environment variables, file permissions, log path, restart policy và shutdown behavior.

Một lệnh chạy thành công trong terminal tương tác không chứng minh service sẽ chạy thành công dưới tài khoản hệ thống với môi trường khác.

## 10. Kiểm tra launcher và cấu hình JVM

Nếu jlink tạo launcher riêng, kiểm tra:

- Module và main class được chỉ định đúng.
- Đối số dòng lệnh được truyền nguyên vẹn.
- JVM options được áp dụng.
- System properties có giá trị mong đợi.
- File cấu hình và resource được tìm thấy từ working directory thực tế.
- Exit code được trả về đúng cho script/service.

Có thể kiểm tra runtime version và home ngay trong ứng dụng:

~~~java
System.out.println("java.version=" + System.getProperty("java.version"));
System.out.println("java.home=" + System.getProperty("java.home"));
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("os.arch=" + System.getProperty("os.arch"));
~~~

Trong test, so sánh java.home với vị trí runtime image dự kiến. Điều này giúp phát hiện test đang vô tình chạy bằng JDK khác.

Nếu runtime image không chứa jcmd, jstack hoặc jfr, dùng công cụ tương ứng từ JDK đầy đủ tương thích để chẩn đoán theo quyền và chính sách môi trường. Không giả định mọi diagnostic tool có sẵn trong image tối giản.

## 11. Kiểm thử kích thước, khởi động và hiệu năng

Một mục tiêu phổ biến của jlink là giảm kích thước runtime. Hãy đo các chỉ số trước/sau bằng cùng điều kiện:

- Tổng kích thước runtime image.
- Kích thước artifact sau nén.
- Thời gian khởi động ứng dụng.
- Thời gian hoàn thành một workload đại diện.
- Memory footprint và peak memory.
- Số module và native dependency.
- Kết quả benchmark qua nhiều lần chạy.

Không kết luận image tốt hơn chỉ vì thư mục nhỏ hơn. Tùy chọn compression có thể giảm dung lượng nhưng không nhất thiết làm thời gian khởi động hoặc throughput tốt hơn.

Nếu dùng --generate-cds-archive, kiểm tra image thực sự khởi động với archive tương ứng và đo lại startup. CDS archive có thể phụ thuộc module graph và tùy chọn runtime; khi cấu hình thay đổi, kiểm tra log và khả năng sử dụng archive.

Các bài test hiệu năng nên chạy trong môi trường ổn định, cùng CPU/RAM, OS, container limit, input data và JVM options. Tách benchmark khỏi smoke test để tránh biến kết quả hiệu năng thành điều kiện pass/fail thiếu ổn định.

## 12. Kiểm thử cập nhật và bảo mật

Custom runtime image không tự động được cập nhật khi JDK gốc phát hành bản vá. Đội phát triển chịu trách nhiệm tạo lại image từ JDK đã cập nhật và phát hành artifact mới.

Mỗi lần cập nhật JDK hoặc jlink options, cần:

1. Ghi nhận vendor, version và update level mới.
2. Rebuild runtime image từ bộ JDK đã được phê duyệt.
3. So sánh module list và runtime properties với baseline.
4. Chạy lại smoke, integration và security-sensitive tests.
5. Kiểm tra certificate, TLS, crypto provider và native libraries.
6. Kiểm tra image size, startup và memory nếu đây là chỉ số phát hành.
7. Tạo checksum và lưu metadata build.
8. Phát hành artifact mới và giữ khả năng rollback.

Không coi việc loại bỏ module bằng jlink là một cơ chế sandbox hoặc ranh giới bảo mật hoàn chỉnh. Runtime image nhỏ hơn có thể giảm thành phần được đóng gói, nhưng quyền truy cập file, network, process, secret và tài nguyên hệ điều hành vẫn phải được kiểm soát bằng cơ chế bảo mật của nền tảng.

## 13. Quy trình kiểm thử đề xuất trong CI

Một pipeline kiểm tra runtime image có thể tổ chức như sau:

~~~text
Compile application
       |
       v
Analyze dependencies (jdeps + manual review)
       |
       v
Create runtime image (jlink)
       |
       v
Inspect image and module list
       |
       v
Validate modules and launcher
       |
       v
Smoke test using image/bin/java
       |
       v
Integration tests on target OS/container
       |
       v
Security and native dependency tests
       |
       v
Size/startup regression checks
       |
       v
Publish image + checksum + build metadata
~~~

Mỗi OS/architecture cần một job build/test phù hợp. Nếu sản phẩm hỗ trợ Linux x64, Linux ARM64 và Windows x64, không nên chỉ build một image rồi dùng cùng artifact cho cả ba target.

Lưu lại:

- JDK vendor/version dùng để build.
- Lệnh jlink và module roots.
- Kết quả java --list-modules.
- Kết quả smoke/integration test.
- Runtime properties từ image.
- OS/architecture của build target.
- Checksum của image/package.
- Phiên bản source và dependency.
- Kết quả security scan và ngày cập nhật runtime.

## 14. Lỗi thường gặp khi kiểm thử runtime image

### Chạy nhầm Java từ PATH

**Dấu hiệu:** ứng dụng chạy tốt trong terminal nhưng không chạy khi deploy.

**Nguyên nhân:** test dùng java của JDK đầy đủ thay vì image/bin/java.

**Cách xử lý:** gọi executable bằng đường dẫn bên trong image; kiểm tra java.home và java.version trong ứng dụng.

### Thiếu module JDK

**Dấu hiệu:** NoClassDefFoundError, ClassNotFoundException, NoSuchMethodError hoặc lỗi factory/provider khi chạy.

**Nguyên nhân:** module cần thiết chưa được thêm vào image hoặc dependency động chưa được phát hiện.

**Cách xử lý:** phân tích lại bằng jdeps, rà soát reflection/service/resource và thêm module cần thiết vào --add-modules. Chạy lại toàn bộ test trên image mới.

### ServiceLoader không tìm thấy provider

**Dấu hiệu:** danh sách provider rỗng hoặc ServiceConfigurationError.

**Nguyên nhân:** thiếu provider module, thiếu service binding hoặc module consumer chưa khai báo uses.

**Cách xử lý:** kiểm tra module descriptor và module path; dùng jlink --bind-services khi cần; chạy test ServiceLoader trên runtime image thật.

### Thiếu locale hoặc charset

**Dấu hiệu:** kết quả format ngày/số khác, thiếu ResourceBundle hoặc không hỗ trợ charset.

**Nguyên nhân:** image không chứa jdk.localedata hoặc module charset cần thiết.

**Cách xử lý:** bổ sung module/dữ liệu locale theo nhu cầu, kiểm tra tùy chọn --include-locales và test các locale thực tế.

### Lỗi TLS hoặc certificate

**Dấu hiệu:** handshake thất bại, không tìm thấy algorithm/provider hoặc certificate không được tin cậy.

**Nguyên nhân:** thiếu security provider/module, truststore không đúng, CA certificates không có trong container hoặc môi trường mạng khác.

**Cách xử lý:** test handshake thật, kiểm tra provider và truststore; xác minh certificate chain trong môi trường đích.

### UnsatisfiedLinkError

**Dấu hiệu:** JVM không nạp được thư viện native.

**Nguyên nhân:** thiếu file native, sai kiến trúc, sai ABI hoặc thiếu thư viện hệ thống.

**Cách xử lý:** build/copy đúng native binary cho target OS/CPU; kiểm tra dependency bằng công cụ của hệ điều hành và chạy test trong container/host đích.

### Launcher chạy sai cấu hình

**Dấu hiệu:** java -m chạy được nhưng launcher riêng không chạy.

**Nguyên nhân:** --launcher trỏ sai module/main class hoặc cấu hình launcher/JVM options không phù hợp.

**Cách xử lý:** so sánh lệnh launcher thực tế với lệnh java -m hoạt động; kiểm tra file launcher và chạy test với chính launcher sẽ phát hành.

### Image không nhận bản vá JDK mới

**Dấu hiệu:** ứng dụng tiếp tục báo version/update cũ dù máy build đã cập nhật JDK.

**Nguyên nhân:** image cũ được copy lại từ artifact cache hoặc pipeline không tạo lại runtime.

**Cách xử lý:** rebuild image từ JDK đã vá, kiểm tra version bên trong image và chạy lại test trước khi phát hành.

## 15. Checklist kiểm thử runtime image

- [ ] Ghi nhận JDK vendor, version, OS và architecture của image.
- [ ] Xác nhận image có Java launcher thực thi được.
- [ ] Kiểm tra java --version bằng launcher trong image.
- [ ] Kiểm tra module list và module graph bằng --list-modules / --validate-modules.
- [ ] Đối chiếu module roots với kết quả jdeps và dependency động đã rà soát.
- [ ] Kiểm tra provider/service binding nếu ứng dụng dùng ServiceLoader, JDBC hoặc SPI.
- [ ] Chạy main class/JAR/module bằng chính runtime image.
- [ ] Chạy launcher riêng nếu image có launcher.
- [ ] Kiểm tra args, JVM options, system properties và working directory.
- [ ] Test resource, logging, locale, charset, XML và database theo chức năng ứng dụng.
- [ ] Test TLS, certificate và crypto provider nếu ứng dụng dùng bảo mật mạng.
- [ ] Test JNI/JNA và native library trên đúng OS/CPU.
- [ ] Chạy integration test trong container hoặc service environment thực tế.
- [ ] Đo size/startup/memory khi đây là tiêu chí phát hành.
- [ ] Rebuild và test lại sau mỗi JDK security update.
- [ ] Lưu checksum, module list và metadata của artifact đã kiểm thử.

## 16. Tài liệu tham khảo chính thức

- [The jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html) — module roots, dependency closure, --bind-services, launcher, locale plugin và cấu trúc runtime image.
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — phân tích dependency và --print-module-deps để hỗ trợ tạo runtime image.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — --version, --list-modules, --validate-modules, module launcher và runtime options.
- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html) — đóng gói ứng dụng cùng runtime image và truyền tùy chọn cho jlink.
- [Java SE 26 Packaging Tool User's Guide — Runtime Requirements](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html) — cấu trúc application image, runtime requirements và thay đổi service binding của jpackage từ JDK 25.

Runtime image chỉ đáng tin khi ứng dụng đã được chạy và kiểm thử bằng chính image đó trên các nền tảng đích. Hãy kiểm tra module, service, resource, native dependency và cấu hình triển khai trước khi phát hành.
