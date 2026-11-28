# Đọc thay đổi tương thích trước khi chuyển lên Java 26

Nâng ứng dụng lên Java 26 cần đánh giá cả khả năng biên dịch, liên kết bytecode và hành vi khi chạy. Một dự án có thể biên dịch thành công nhưng vẫn lỗi ở runtime vì API đã bị gỡ, thư viện dùng reflection sâu, chứng thư TLS không còn được tin cậy, JVM flag đã lỗi thời hoặc dữ liệu locale thay đổi. Vì vậy, trước khi đổi runtime production, hãy lập danh sách thay đổi từ các JDK trung gian, quét ứng dụng và dependency, chạy thử trên đúng bản JDK/vendor dự kiến triển khai, rồi kiểm thử theo workload thực tế.

Bài này tập trung vào các thay đổi còn có ảnh hưởng khi chuyển lên JDK 26, cách phân biệt API đã bị gỡ với API mới chỉ bị đánh dấu deprecated, công cụ phân tích tương thích và quy trình rollout. Những tính năng mới còn ở trạng thái preview hoặc incubator được nhận diện riêng để tránh đưa API chưa ổn định vào hợp đồng production một cách vô ý.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt source compatibility, binary compatibility và behavioral compatibility.
- Xác định các release notes cần đọc khi nâng từ một JDK cũ lên JDK 26.
- Dùng `jdeprscan`, `jdeps`, `javac`, `jcmd` và test suite để tìm rủi ro trước khi nâng cấp.
- Nhận diện API, công cụ và JVM options đã bị gỡ trong JDK 26.
- Phân biệt thay đổi bị gỡ, deprecated for removal và proposed for removal.
- Kiểm thử các thay đổi hành vi về HTTP, TLS, JMX, JDBC, locale, time zone và JVM defaults.
- Phát hiện thư viện đang mutate `final` field qua deep reflection.
- Phân biệt tính năng Java 26 đã final với preview và incubator.
- Xây dựng kế hoạch nâng cấp có baseline, canary, rollback và kiểm tra sau triển khai.

## 1. Xác định phạm vi tương thích cần kiểm tra

JDK 26 không chỉ là compiler mới. Nó bao gồm Java language, Java SE APIs, JVM, công cụ, security providers, dữ liệu Unicode/locale/time zone và các implementation mặc định. Khi đọc một thay đổi, hãy xác định nó tác động tới lớp nào của hệ thống.

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Source compatibility | Source cũ còn biên dịch được không? | `javac` báo không tìm thấy API đã bị xóa |
| Binary compatibility | Class file cũ còn liên kết được với runtime mới không? | `NoSuchMethodError`, `NoClassDefFoundError` |
| Behavioral compatibility | Chương trình có còn cho kết quả và hành vi như trước không? | HTTP timeout bao phủ cả response body, định dạng số thay đổi, TLS handshake thất bại |
| Operational compatibility | Ứng dụng có chạy đúng trong container, OS và pipeline hiện tại không? | JVM flag không còn tồn tại, memory sizing khác, build tool không hỗ trợ JDK |
| Security compatibility | Chính sách certificate, thuật toán và provider có còn chấp nhận cấu hình cũ không? | Certificate chain không còn trusted, JCE provider không được xác thực |

Không dừng ở việc compile pass. Binary cũ có thể chạy tới khi một nhánh hiếm gọi method đã bị gỡ; test đơn vị có thể không phát hiện một thay đổi định dạng chỉ xảy ra với một locale; TLS chỉ lỗi khi kết nối tới một CA hoặc server cụ thể.

## 2. Đọc đúng tài liệu migration và release notes

Nguồn chính để nâng cấp là Oracle JDK Migration Guide, JDK Release Notes, Java SE API Specification và tài liệu của vendor JDK mà hệ thống sẽ sử dụng. Release notes có thể liệt kê thay đổi có ảnh hưởng tương thích; migration guide gom các thay đổi qua nhiều release.

Nếu nâng từ JDK 17 lên JDK 26, cần xem các thay đổi từ JDK 18 đến JDK 26, không chỉ trang JDK 26. Nếu nâng từ JDK 21 lên JDK 26, xem các release từ JDK 22 đến JDK 26. Các thay đổi như default charset UTF-8, Security Manager, annotation processing và locale provider xuất hiện ở release trước nhưng vẫn ảnh hưởng khi tới JDK 26.

Oracle mô tả ba loại compatibility trong release notes:

- **Source:** khả năng biên dịch source cũ.
- **Binary:** khả năng liên kết class file đã biên dịch.
- **Behavioral:** ngữ nghĩa của code khi chạy.

Hãy đọc theo thứ tự:

1. Getting Started và Preparing for Migration để hiểu quy trình chung.
2. Significant Changes in JDK 26 để nhận diện tính năng và thay đổi lớn.
3. Removed APIs, Removed Tools and Components để tìm các hard break.
4. Security Updates để kiểm tra certificate, algorithm, provider và TLS.
5. Deprecated APIs và các option bị đánh dấu deprecated for removal.
6. Release notes của mọi JDK trung gian kể từ runtime hiện tại.
7. Compatibility notes của framework, JDBC driver, application server, agent và thư viện bên thứ ba.

Một thay đổi được đánh dấu *removed* có thể làm source cũ không compile hoặc bytecode cũ ném linkage error. Một API *deprecated for removal* vẫn có thể tồn tại nhưng cần thay thế trước release tương lai. Một API *proposed for removal* là cảnh báo kế hoạch, chưa phải API đã bị gỡ.

## 3. Kiểm kê môi trường trước khi chạy phân tích

Ghi lại tất cả nơi chạy Java, không chỉ máy developer:

| Nhóm | Thông tin cần kiểm kê |
|---|---|
| Runtime | Vendor, JDK build/update, architecture, OS, libc và container base image |
| Build | Maven/Gradle wrapper, compiler toolchain, test runner, annotation processor và plugin |
| Ứng dụng | Artifact, dependency lock, multi-release JAR, module path/classpath, startup script |
| JVM options | `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `JAVA_OPTS`, service flags, GC flags và diagnostic flags |
| Thư viện | Framework, ORM, JSON/XML, logging, HTTP client/server, JDBC driver, JMX và security provider |
| Runtime extensions | Java agent, APM/profiler, JVMTI agent, JNI/FFM native library và custom class loader |
| Security | Truststore, keystore, TLS version/cipher, certificate chain, crypto provider, JAR signing |
| Operations | Heap/memory limit, CPU quota, readiness, health check, autoscaling và shutdown behavior |

Lấy thông tin từ đúng process đang chạy:

```bash
java -version
javac -version
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

`java -version` trên terminal có thể trỏ tới JDK khác với service đang chạy trong container hoặc được khởi động bởi service manager. `jcmd` cần được chạy trên cùng máy và thường với cùng user/group đã khởi chạy JVM.

Kiểm tra các biến môi trường và file cấu hình khởi động để tìm JVM option bị truyền gián tiếp. Một flag không nằm trong source code vẫn có thể làm JVM không khởi động được sau khi nâng JDK.

## 4. Dùng công cụ phân tích trước khi chạy ứng dụng

### `jdeprscan`: tìm Java SE API deprecated

`jdeprscan` quét class file, thư mục class hoặc JAR để tìm các API Java SE đã deprecated. Để liệt kê API được đánh dấu deprecated for removal trong Java 26:

```bash
jdeprscan --release 26 --list --for-removal
```

Để quét một artifact đã build:

```bash
jdeprscan --release 26 --for-removal \
  --class-path "lib/*" \
  build/libs/application.jar
```

Muốn quét tất cả deprecated API, bỏ `--for-removal`:

```bash
jdeprscan --release 26 \
  --class-path "lib/*" \
  build/libs/application.jar
```

`jdeprscan` chỉ nhận diện deprecated API thuộc Java SE; nó không báo deprecated API riêng của thư viện bên thứ ba. Hãy xem dependency release notes và cảnh báo compiler để đánh giá phần đó.

### `jdeps`: tìm JDK internal API

Chạy `jdeps` để tìm dependency tới package/class nội bộ của JDK:

```bash
jdeps --jdk-internals \
  --class-path "lib/*" \
  build/libs/application.jar
```

Có thể phân tích đệ quy dependency bằng `-R`:

```bash
jdeps -R --jdk-internals \
  --class-path "lib/*" \
  build/libs/application.jar
```

JDK internal API không phải hợp đồng Java SE ổn định. Nếu `jdeps` tìm thấy dependency, ưu tiên API chuẩn thay thế như `java.util.Base64`, `VarHandle` hoặc Foreign Function & Memory API tùy trường hợp. `--add-exports` và `--add-opens` chỉ nên là workaround có phạm vi rõ ràng trong lúc nâng cấp; chúng không biến internal API thành API được hỗ trợ.

`jdeps` là static analysis nên không phát hiện đầy đủ truy cập qua reflection, tên class được tạo động, JNI hoặc native code tự đọc cấu trúc JVM. Cần kết hợp log runtime, test, JFR và kiểm tra source của agent/native library.

### Kiểm tra warning và compiler behavior

Compile bằng JDK 26 để nhận warning/error mới:

```bash
javac --release 26 -Xlint:deprecation -d build/classes @sources.txt
```

Nếu ứng dụng vẫn cần phát hành bytecode cho Java thấp hơn, chọn release tương ứng, ví dụ `--release 21`; khi đó source không được tham chiếu API chỉ có từ Java 26. Dùng `--release` để đồng bộ language level, API surface và target class file. Không ghép `--release` với `-source` hoặc `-target`.

## 5. API và công cụ đã bị gỡ trong JDK 26

Các mục dưới đây là những hard break cần tìm trong source, dependency, script và cấu hình.

| Thành phần đã bị gỡ | Tác động có thể gặp | Hướng xử lý |
|---|---|---|
| Applet API: `java.applet`, `Applet`, `AppletContext`, `AppletStub`, `AudioClip`, `javax.swing.JApplet`, `AppletInitializer` | Source cũ không compile; bytecode gọi class đã gỡ không thể liên kết | Thay kiến trúc applet bằng ứng dụng web hoặc desktop được hỗ trợ; không tiếp tục dựa vào browser plug-in |
| `Thread.stop()` | Source mới không compile; bytecode cũ có thể ném `NoSuchMethodError` | Dùng interruption, cancellation token, timeout và đóng resource theo quy trình hợp tác |
| `DatagramSocketImpl.setTTL/getTTL()` và `MulticastSocket.setTTL/getTTL/send(DatagramPacket, byte)` | Code multicast dùng API TTL cũ không compile hoặc không liên kết | Dùng API integer `setTimeToLive(int)`/`getTimeToLive()` và thiết kế lại thao tác gửi theo API còn được hỗ trợ |
| XML interchange trong `javax.management.modelmbean.DescriptorSupport` | Constructor nhận XML, `toXMLString()` và `XMLParseException` đã bị gỡ | Dùng định dạng serialization được ứng dụng quản lý, không phụ thuộc XML interchange đã loại bỏ |
| `jrunscript` | Script dựa vào tool này không chạy được | Dùng `jshell` cho tương tác Java hoặc một runtime scripting riêng còn được hỗ trợ |
| Module `jdk.jsobject` trong Oracle JDK | Ứng dụng JavaFX/browser bridge có thể thiếu module | Kiểm tra JavaFX version; `jdk.jsobject` được cung cấp cùng JavaFX 24 trở lên |
| InfiniBand Sockets Direct Protocol (SDP) và `com.sun.sdp.conf` | Cấu hình SDP không còn tác dụng; kết nối dựa trên SDP có thể thất bại | Chuyển sang transport được OS/JDK hiện tại hỗ trợ, ví dụ TCP hoặc giải pháp InfiniBand được vendor duy trì |
| Property `jdk.nio.path.useNormalizationFormD` trên macOS | Cấu hình path normalization cũ không còn được nhận diện | Dùng semantics path của APFS hiện hành; loại bỏ phụ thuộc property tương thích HFS+ |

JDK 26 cũng loại bỏ các phương thức finalization khỏi một số lớp `javax.imageio.stream`. Nếu plugin ImageIO của bên thứ ba trông chờ finalization để flush hoặc giải phóng native resource, hãy cập nhật plugin và đóng stream rõ ràng bằng `close()`/try-with-resources.

`Object.finalize()` và cơ chế finalization tổng thể chưa bị gỡ khỏi Java 26, nhưng đã deprecated for removal từ các release trước. Không viết code mới dựa vào finalizer; chuyển sang `AutoCloseable` cho resource có vòng đời xác định hoặc `Cleaner` cho trường hợp cleanup dự phòng phù hợp.

### Phân biệt removed và proposed for removal

Các API như `SecurityManager`, `AccessController`, một số permission classes và `java.beans.beancontext` có thể xuất hiện trong danh sách proposed for removal hoặc deprecated for removal. Không được ghi chúng như thể đã bị xóa khỏi JDK 26. Kiểm tra trạng thái chính xác trên API Specification của release mục tiêu và kết quả `jdeprscan --release 26 --for-removal`.

Security Manager đã bị vô hiệu hóa vĩnh viễn từ JDK 24; API còn tồn tại trong một số trường hợp để hỗ trợ tương thích nhưng không còn là cơ chế sandbox để bảo vệ code. Ứng dụng dựa vào `System.setSecurityManager` hoặc policy-based sandbox phải chuyển sang cô lập bằng process, container, OS permissions hoặc cơ chế bảo mật ở tầng triển khai.

## 6. JVM options đã bị gỡ hoặc deprecated

JDK 26 tiếp tục loại bỏ các option rất cũ và đánh dấu một số option tuning là deprecated for removal. Kiểm tra mọi script khởi động, Dockerfile, systemd unit, Helm chart, CI variable và cấu hình application server.

| Option/thành phần | Trạng thái/khuyến nghị |
|---|---|
| `-t`, `-tm`, `-Xfuture`, `-checksource`, `-cs`, `-noasyncgc` | Đã bị gỡ từ JDK 24; loại khỏi launcher script nếu còn sót |
| `-verbosegc`, `-noclassgc`, `-verify`, `-verifyremote`, `-ss`, `-ms`, `-mx` | Các option cũ đã deprecated for removal; dùng Unified Logging và option hiện hành như `-Xss`, `-Xms`, `-Xmx` khi đúng mục đích |
| `-Xmaxjitcodesize` | Deprecated for removal; dùng `-XX:ReservedCodeCacheSize` |
| `-XX:+AggressiveHeap` | Deprecated for removal; cấu hình GC, heap và TLAB cụ thể dựa trên workload |
| `-XX:MaxRAM` | Deprecated for removal; default của flag đã bị loại bỏ. Nếu cần kiểm soát heap, ưu tiên `-Xms`/`-Xmx` |
| `AlwaysActAsServerClassMachine`, `NeverActAsServerClassMachine` | Deprecated for removal; chọn collector rõ ràng nếu ứng dụng có yêu cầu |
| `-XX:+TraceClassLoading`, `-XX:+TraceClassUnloading`, `-XX:+TraceExceptions` | Đã obsolete; dùng `-Xlog:class+load=info`, `-Xlog:class+unload=info`, `-Xlog:exceptions=info` |

Ví dụ thay tracing flags cũ bằng Unified Logging:

```bash
java \
  -Xlog:class+load=info,class+unload=info,exceptions=info \
  -jar application.jar
```

Đừng giữ một JVM flag chỉ vì nó từng làm ứng dụng chạy nhanh hơn trong một benchmark cũ. Một flag deprecated có thể không còn tác dụng tương đương hoặc bị gỡ ở release tiếp theo. Xác minh mục đích ban đầu, thay bằng option cụ thể, rồi benchmark lại.

Ba cờ `TraceClassLoading`, `TraceClassUnloading` và `TraceExceptions` đã obsolete từ các JDK cũ, không phải thay đổi mới riêng của JDK 26; vẫn cần loại bỏ nếu script legacy còn sử dụng chúng.

## 7. Thay đổi hành vi HTTP và network cần kiểm thử

### HTTP Client hỗ trợ HTTP/3 nhưng không tự chọn HTTP/3 mặc định

JDK 26 bổ sung HTTP/3 cho `java.net.http.HttpClient` qua JEP 517. HTTP/3 chạy trên QUIC/UDP, trong khi HTTP/1.1 và HTTP/2 dùng TCP. HTTP/3 không phải mặc định; ứng dụng phải đặt preferred version là `HttpClient.Version.HTTP_3` ở client hoặc request.

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api"))
        .version(HttpClient.Version.HTTP_3)
        .GET()
        .build();
```

Khi nâng cấp:

- Kiểm tra firewall, network policy, load balancer và egress có cho phép QUIC/UDP không.
- Kiểm tra server có quảng bá và hỗ trợ HTTP/3 hay không.
- Chỉ URI `https` mới có thể dùng HTTP/3 trong implementation JDK.
- Built-in implementation không dùng HTTP/3 khi request đi qua proxy.
- HTTP/3 có thể fallback về HTTP/2 hoặc HTTP/1.1 tùy cách cấu hình và khả năng kết nối; nếu ép HTTP/3-only mà client không hỗ trợ, có thể nhận `UnsupportedProtocolVersionException`.
- `SSLContext`/`SSLParameters` tùy chỉnh có thể không tương thích với HTTP/3; kiểm thử chính xác cấu hình TLS đang triển khai.

Không giả định việc gọi `.version(HTTP_3)` đồng nghĩa request thực tế luôn chạy HTTP/3. Ghi nhận protocol được thương lượng và đo fallback trên môi trường gần production.

### Request timeout giờ bao gồm cả response body

`HttpRequest.Builder.timeout()` trước đây chỉ áp dụng tới khi nhận response headers. Trong JDK 26, timeout bao phủ cả việc tiêu thụ response body. Một client cũ dùng timeout ngắn cho request streaming hoặc body lớn có thể bắt đầu timeout trong lúc đọc body dù headers đã đến.

Kiểm tra các trường hợp:

- Body tải xuống lớn hoặc streaming kéo dài.
- Response body được đọc chậm bởi consumer.
- `BodyHandlers.ofInputStream()` hoặc publisher/subscriber có vòng đời đọc riêng.
- Timeout được đặt thấp hơn thời gian hoàn tất thực tế của response.

Thiết kế timeout theo SLA của toàn request, đồng thời đóng/cancel body đúng cách để giải phóng connection và tài nguyên.

### Các thay đổi HTTP khác

| Thay đổi | Rủi ro tương thích | Test cần chạy |
|---|---|---|
| Request HTTP/1.1 không có body với method ngoài POST/PUT không còn tự gửi `Content-Length: 0` | Server/proxy cũ có thể phụ thuộc header này | Kiểm tra request thực tế và hợp đồng với server; chỉ cho phép restricted header nếu có lý do cụ thể |
| `HttpCookie` ưu tiên `Max-Age` hơn `Expires` khi cả hai cùng xuất hiện | Thời hạn cookie có thể khác cách code cũ suy luận | Test session, expiration và cookie từ các domain tích hợp |
| `CookieStore.getURIs()` và `get(URI)` trả immutable list trong implementation JDK | Code sửa trực tiếp list nhận về sẽ ném `UnsupportedOperationException` | Copy sang list mutable nếu cần sửa dữ liệu |
| `BodyPublishers.ofFile()` dùng `FileNotFoundException` nhất quán khi path không tồn tại/không thuộc default filesystem | Catch cụ thể `NoSuchFileException` có thể không còn đúng | Kiểm thử exception handling cho file provider và filesystem tùy chỉnh |
| `HttpClient` nay dùng named groups và signature schemes cấu hình trong `SSLParameters` khi TLS handshake | Cấu hình TLS trước đây bị bỏ qua nay có hiệu lực, làm thay đổi khả năng thương lượng | Kiểm thử handshake với server và certificate thực tế |

### HTTP Server: attribute của HttpExchange không còn chia sẻ mặc định

Trong implementation HTTP server của module `jdk.httpserver`, trước JDK 26 attribute map của `HttpExchange` được chia sẻ với `HttpContext`. Từ JDK 26, mỗi exchange có map riêng theo mặc định. Code dùng `exchange.setAttribute()` để chia sẻ state giữa các request sẽ không còn hoạt động như trước.

Hãy phân biệt:

- Dữ liệu chung của context: đặt bằng `HttpContext.setAttribute()`.
- Dữ liệu riêng của một request: đặt bằng `HttpExchange.setAttribute()`.

Có thể khôi phục behavior cũ tạm thời bằng system property `jdk.httpserver.attributes`, nhưng nên sửa code theo scope dữ liệu rõ ràng.

## 8. JMX, JDBC và các API thư viện có thay đổi hành vi

### JMXServiceURL cần protocol tường minh

`JMXServiceURL` không còn tự chọn protocol `jmxmp` khi tạo từ các tham số rời mà không chỉ định protocol. Constructor có thể ném `MalformedURLException` nếu thiếu protocol. Hãy tìm mọi nơi tạo URL JMX và khai báo protocol đã được cấu hình rõ ràng, ví dụ `service:jmx:rmi:///jndi/rmi://host:port/jmxrmi` nếu hệ thống dùng RMI/JMX.

Không dựa vào default `jmxmp` cũ. Kiểm tra cả agent, monitoring system, JConsole/JMX client và script quản trị.

### JDBC 4.5 và driver

JDK 26 bổ sung các thay đổi JDBC 4.5, gồm SQL types `DECFLOAT` và `JSON`, các interface `Array`, `Blob`, `Clob`, `Nclob`, `SQLXML` hỗ trợ `AutoCloseable`, cùng default methods mới trên `Connection` cho quoted identifier.

Một số JDBC driver có thể bị ảnh hưởng nếu implementation nội bộ khai báo method trùng với default method mới ở dạng private/protected hoặc nhiều interface cung cấp default implementation khác nhau. Cần:

- Cập nhật driver lên version hỗ trợ JDK/JDBC mục tiêu.
- Test connection, statement, metadata, transaction, LOB và SQLXML.
- Test code custom implement `Connection` hoặc wrapper/proxy JDBC.
- Kiểm tra behavior của `enquoteIdentifier()` và `isSimpleIdentifier()` với SQL reserved words.

Không tự triển khai lại toàn bộ JDBC interface nếu có thể dùng driver chính thức và wrapper được duy trì.

### Một số thay đổi API khác

- `java.nio.ByteOrder` được chuyển thành enum; các constant `BIG_ENDIAN`, `LITTLE_ENDIAN` và `nativeOrder()` vẫn là cách sử dụng chuẩn. Nếu reflection hoặc framework kiểm tra class metadata của `ByteOrder`, hãy test lại.
- `AnnotatedType` methods như `isAnnotationPresent`, `getAnnotation` và `getDeclaredAnnotation` ném `NullPointerException` khi truyền null, phù hợp hợp đồng `AnnotatedElement`; code cũ dựa vào kết quả `false`/`null` cần sửa.
- `AttributeList`, `RoleList` và `RoleUnresolvedList` không còn chấp nhận object sai kiểu rồi trì hoãn kiểm tra tới `asList()`; lỗi có thể xuất hiện sớm hơn.
- `MBeanServer.registerMBean(null, ...)` nay ném `RuntimeOperationsException` thay vì `NullPointerException`.
- Native code không được giả định `jmethodID` là pointer tới cấu trúc Method nội bộ của JVM. JDK 26 thay đổi representation; coi `jmethodID` là opaque identifier theo JNI contract.

## 9. Locale, number format, charset và time zone

### CLDR và locale data

JDK 26 cập nhật dữ liệu locale lên CLDR 48. Các thay đổi có thể tác động tới định dạng ngày/giờ, số, dấu phân nhóm, tên múi giờ, thứ tự ngày đầu tuần và tên locale. `DecimalFormat` cũng chuyển sang thuật toán dựa trên `Double.toString(double)`; một số giá trị hiếm có thể cho chuỗi kết quả khác so với JDK trước.

Nếu ứng dụng:

- So sánh chuỗi ngày/giờ/số đã format trong test.
- Ghi dữ liệu số đã format ra file hoặc database.
- Tạo báo cáo, hóa đơn, CSV hoặc nội dung gửi cho hệ thống bên ngoài.
- Dùng locale mặc định của máy thay vì locale tường minh.

thì cần kiểm thử snapshot và integration bằng các locale thật sự được hỗ trợ. Không dùng chuỗi đã format làm dữ liệu trao đổi máy-máy nếu có thể dùng kiểu dữ liệu và định dạng giao thức rõ ràng.

JDK 26 có property tạm thời `-Djdk.compat.DecimalFormat=true` để bật lại thuật toán cũ trong một số release chuyển tiếp. Chỉ dùng để khoanh vùng regression và lập kế hoạch sửa; không nên xem đây là cấu hình tương thích lâu dài.

### Locale provider cũ và charset mặc định

Nếu nâng từ JDK rất cũ:

- Locale provider `JRE`/`COMPAT` đã bị loại khỏi JDK 23. Nếu `java.locale.providers` còn chứa chúng, chuyển sang CLDR hoặc SPI provider được ứng dụng chủ động cung cấp.
- Charset mặc định của Java là UTF-8 từ JDK 18. Nếu code đọc/ghi file mà không chỉ định charset và trước đây dựa vào encoding mặc định của Windows/Linux, dữ liệu có thể thay đổi. Dùng `StandardCharsets.UTF_8` hoặc charset được giao thức quy định.

### Time zone data phụ thuộc bản update

JDK 26 GA có IANA time zone data 2025b; các bản update sau có thể mang dữ liệu mới hơn. Vì vậy, không chỉ kiểm tra major version `26`; hãy ghi vendor, update build và time zone data của runtime thực tế. Test các ngày chuyển DST, lịch sử thay đổi timezone và deadline theo giờ địa phương.

## 10. Security, TLS, keystore và cryptographic provider

### Thuật toán mật mã

Trong JDK 26, một số implementation requirements cũ như DESede và `RSA/ECB/PKCS1Padding` được loại khỏi danh sách thuật toán mà Java SE yêu cầu mọi implementation phải hỗ trợ. Điều này **không có nghĩa mọi provider đều đã xóa các thuật toán này**, nhưng ứng dụng không còn được dựa vào bảo đảm chúng có mặt ở mọi JDK/provider.

Các thuật toán PBES2 dùng AES và HMAC mới được bổ sung vào yêu cầu hỗ trợ. Nếu ứng dụng dùng DESede, RSA PKCS#1 v1.5 encryption padding hoặc một provider cụ thể, hãy:

- Xác định nơi thuật toán được dùng: encryption, keystore, signature hay interoperability.
- Kiểm tra provider thực tế bằng `Cipher.getInstance(...)`, `SecretKeyFactory.getInstance(...)` và test dữ liệu thật.
- Lập kế hoạch chuyển sang thuật toán hiện đại được protocol và peer hỗ trợ.
- Không tự thay thuật toán trong dữ liệu đã mã hóa mà chưa có chiến lược re-encryption/migration.

JDK 26 thêm security property `jdk.crypto.disabledAlgorithms` để giới hạn một số JCE/JCA services ở tầng `Cipher`, `KeyStore`, `MessageDigest` và `Signature`. Ban đầu không có thuật toán nào bị disable mặc định bởi property mới này; giá trị có thể thay đổi trong các release sau. Kiểm tra cả `java.security` tùy chỉnh và system property cùng tên.

### Certificate và truststore

JDK 26 loại bỏ bốn root certificates AffirmTrust đã ngừng sử dụng khỏi `cacerts`. Release notes cũng mô tả chính sách distrust đối với TLS server certificates được cấp sau ngày 17-03-2026 và chain về Chunghwa root certificates. Nếu hệ thống kết nối tới server có certificate chain phụ thuộc các root này, handshake có thể thất bại.

Trước khi chuyển production:

- Kiểm tra certificate chain của database, LDAP, message broker, API gateway, artifact repository và remote service.
- Kiểm tra SAN/hostname, expiration, issuer, intermediate và trust anchor.
- Cập nhật certificate phía server hoặc truststore theo chính sách bảo mật; không thêm lại root đã bị distrust một cách tùy tiện.
- Dùng `keytool -printcert -sslserver host:port` hoặc kiểm tra keystore/truststore đã cấu hình để xem chain.

### JKS/JCEKS và PKCS12

JDK 26 phát warning khi dùng keystore JKS/JCEKS vì chúng dùng thuật toán cũ và dự kiến bị loại trong tương lai. Nên lập kế hoạch chuyển sang PKCS12:

```bash
keytool -importkeystore \
  -srckeystore legacy.jks \
  -srcstoretype JKS \
  -destkeystore application.p12 \
  -deststoretype PKCS12
```

Sau khi chuyển, xác nhận alias, private key, certificate chain, key password, store password và ứng dụng thực sự đọc được keystore mới. Không xóa bản gốc cho tới khi quy trình backup/restore và rollout đã được kiểm chứng.

### Third-party JCE provider và TLS

Oracle JDK không còn chấp nhận third-party cryptographic provider JAR được ký bằng certificate từ Sun Microsystems JCE Code Signing Root CA cũ. Provider có thể gặp `SecurityException: JCE cannot authenticate the provider`. Kiểm tra chữ ký bằng `jarsigner -verify -verbose -certs provider.jar` và cập nhật provider JAR được ký bằng certificate chain hiện được tin cậy. Đây là thay đổi cần kiểm tra theo vendor JDK; không mặc định mọi distribution xử lý giống Oracle JDK.

`SunX509` KeyManager nay áp dụng algorithm constraints và certificate checks tương tự `PKIX`, gồm kiểm tra signature algorithms phía peer và `jdk.tls.disabledAlgorithms`/`jdk.certpath.disabledAlgorithms`. Việc chọn certificate local có thể khác trước. Đừng dựa vào legacy behavior bỏ qua certificate checks.

Với RMI qua TLS, endpoint identification được bật mặc định khi dùng `SslRMIClientSocketFactory`. Certificate server cần SAN khớp hostname; kết nối từng chạy được nhờ bỏ qua hostname verification có thể thất bại. Hãy sửa certificate/hostname trước khi cân nhắc property tắt endpoint identification.

JDK 26 cũng cải thiện xử lý password của `keytool`/`jarsigner` khi stdout bị redirect. Kiểm tra automation không dựa vào password echo hoặc prompt cũ.

### Security Manager và JNDI từ các release trước

Nếu nâng từ JDK 17 trở xuống, kiểm tra các hệ thống dùng Security Manager, policy file hoặc JNDI remote code downloading. Security Manager đã bị vô hiệu hóa vĩnh viễn từ JDK 24; JNDI remote code downloading cũng đã bị vô hiệu hóa vĩnh viễn. Không tìm cách bật lại cơ chế cũ bằng flag; thiết kế lại isolation và kiểm soát truy cập ở tầng process/container/OS.

## 11. Reflection và final field: cảnh báo cần xử lý trước khi nâng tiếp

JDK 26 bắt đầu phát warning khi code dùng deep reflection để mutate non-static `final` field sau khi object đã được khởi tạo. Đây là bước chuẩn bị cho release tương lai, khi mutation trái phép sẽ bị chặn mặc định.

Ví dụ thư viện có thể làm điều này:

```java
Field field = SomeConfig.class.getDeclaredField("value");
field.setAccessible(true);
field.set(config, "replacement");
```

Trên JDK 26, lần mutation đầu tiên của một module sẽ phát warning và chỉ ra field cùng caller. Chỉ thêm `--add-opens` không đủ để cho phép mutate final field; quyền này được kiểm soát riêng.

Để tìm dependency gây warning:

```bash
java --illegal-final-field-mutation=debug \
  -jar application.jar
```

Hoặc thử mode nghiêm ngặt trong test/CI:

```bash
java --illegal-final-field-mutation=deny \
  -jar application.jar
```

`deny` làm `Field::set` ném `IllegalAccessException` cho mutation trái phép, hữu ích để phát hiện sớm thư viện sẽ lỗi ở future JDK. Nếu một thư viện thiết yếu chưa thể thay thế, `--enable-final-field-mutation=ALL-UNNAMED` hoặc danh sách module có thể cấp quyền cụ thể khi package đã được mở; đây nên là ngoại lệ tạm thời, có owner và thời hạn loại bỏ.

Ưu tiên cập nhật framework/serializer/DI/mock library để không cần mutate final field. Nếu ứng dụng tự thiết kế object, dùng constructor, factory hoặc builder để thiết lập trạng thái trước khi object được publish.

## 12. JVM defaults và hiệu năng khi nâng lên JDK 26

### Initial heap mặc định nhỏ hơn

JDK 26 bỏ default value trước đây của `InitialRAMPercentage`. Nếu không chỉ định `-Xms` hoặc `-XX:InitialHeapSize`, JVM khởi tạo heap ở mức tối thiểu (`MinHeapSize`) thay vì mặc định khoảng 1/64 RAM vật lý. Điều này giảm thời gian khởi động trên máy nhiều RAM, nhưng có thể làm heap tăng dần trong giai đoạn đầu.

Nếu workload nhạy với startup hoặc cần heap ban đầu lớn để tránh resize, hãy đo cold start và xác định `-Xms` rõ ràng thay vì dựa vào default cũ. Với container, kiểm tra memory limit thực tế và hành vi cgroup.

### G1 và `GCTimeRatio`

G1 được cải thiện throughput qua JEP 522 bằng cách giảm đồng bộ giữa application threads và GC refinement threads. Tuning guide JDK 26 mô tả `-XX:GCTimeRatio=24` cho G1, tương ứng mục tiêu khoảng 4% tổng thời gian dành cho GC theo công thức `1 / (1 + GCTimeRatio)`. Đây là mục tiêu heuristic dùng trong điều chỉnh heap, không phải giới hạn cứng cho CPU hoặc cam kết mọi workload chỉ dùng 4% thời gian GC.

Khi so sánh JDK cũ với JDK 26, ghi lại collector và giá trị flags thực tế. Chạy cả phép đo với default mới lẫn phép đo kiểm soát có cùng heap/GC settings nếu cần tách tác động của code khỏi thay đổi ergonomics.

### Các flag heap cũ

`AggressiveHeap` và `MaxRAM` đã deprecated for removal; default `MaxRAM` cũng bị loại bỏ. Nếu cần kiểm soát memory footprint, dùng `-Xms`/`-Xmx` và container limit rõ ràng. Không phụ thuộc `AggressiveHeap` để tạo một cấu hình benchmark khó giải thích.

### AOT object caching và virtual threads

JEP 516 giúp AOT object cache dùng được với mọi garbage collector, kể cả ZGC, bằng cách nạp object từ định dạng trung lập với GC. Nếu ứng dụng dùng AOT cache, phải ghi rõ cache được tạo bởi bản nào, được nạp ở runtime nào và đo startup/warm-up với trạng thái cache tương đương.

JDK 26 cũng thay đổi hành vi virtual thread khi chờ một thread khác hoàn tất class initialization: trong phần lớn trường hợp virtual thread được unmount khỏi carrier trong lúc chờ. Điều này có thể giảm pinning và tránh một số tình huống cạn carrier. Test lại ứng dụng dùng virtual thread, static initializer có blocking I/O, class loading đồng thời và thread dump.

## 13. Phân biệt tính năng final, preview và incubator

Không phải tính năng mới trong JDK 26 đều là API ổn định. Release notes phân loại các tính năng quan trọng như sau:

| Tính năng | Trạng thái trong JDK 26 | Hệ quả khi triển khai |
|---|---|---|
| HTTP/3 trong `HttpClient` — JEP 517 | Final | Dùng API chuẩn; HTTP/3 vẫn phải được yêu cầu và có thể fallback theo điều kiện kết nối |
| G1 giảm đồng bộ — JEP 522 | Final | Runtime improvement, không cần preview flag |
| AOT object caching với mọi GC — JEP 516 | Final | Kiểm thử startup/cache theo GC đang triển khai |
| Primitive types in patterns, `instanceof`, `switch` — JEP 530 | Fourth Preview | Compile và run với `--enable-preview`; syntax/API còn có thể thay đổi |
| Lazy Constants — JEP 526 | Second Preview | Preview API; không coi là hợp đồng ổn định cho thư viện lâu dài |
| Structured Concurrency — JEP 525 | Sixth Preview | Preview API; cần chấp nhận thay đổi giữa các JDK preview |
| PEM encodings — JEP 524 | Second Preview | Preview API; không phụ thuộc vào API preview cho định dạng bảo mật lâu dài nếu chưa chấp nhận rủi ro |
| Vector API — JEP 529 | Eleventh Incubator | Module incubator `jdk.incubator.vector`; API có thể thay đổi và cần module flag |

### Bật preview có chủ đích

Nếu thực sự cần thử preview feature của Java 26:

```bash
javac --enable-preview --release 26 -d out @sources.txt
java --enable-preview -cp out example.Main
```

Compiler và runtime phải dùng cùng release preview tương ứng. Preview feature không phải API final; khi chuyển sang JDK khác, source có thể cần sửa.

### Dùng incubator module

Vector API là incubator module, cần được thêm vào module graph:

```bash
javac --release 26 --add-modules jdk.incubator.vector \
  -d out @sources.txt

java --add-modules jdk.incubator.vector \
  -cp out example.VectorApplication
```

Với ứng dụng modular, khai báo `requires jdk.incubator.vector;` trong `module-info.java`. Incubator module không đồng nghĩa với preview language feature; không bật `--enable-preview` chỉ vì dùng Vector API. Tuy nhiên, API incubator vẫn có thể thay đổi hoặc bị thay thế.

Không đưa preview/incubator vào public API của thư viện dùng chung nếu chưa có chính sách versioning và nâng cấp rõ ràng. Nếu chỉ đang đánh giá tính năng, tách code thử nghiệm khỏi phần production-critical.

## 14. Quy trình nâng cấp đề xuất

### Giai đoạn A — chuẩn bị và phân tích

1. Chốt JDK nguồn, JDK vendor đích, bản update/build, OS, architecture và container image.
2. Thu thập release notes của tất cả release trung gian.
3. Kiểm kê JVM flags, environment variables, build tools, framework, JDBC driver, security provider, agent, JNI và native libraries.
4. Chạy `jdeprscan` và `jdeps`; phân loại từng finding theo mức độ bắt buộc sửa.
5. Tìm các API đã gỡ, final-field mutation, internal API, TLS/keystore legacy và feature preview/incubator.
6. Lập danh sách test regression có owner cho từng rủi ro.

### Giai đoạn B — chạy thử trước khi recompilation

Oracle khuyến nghị thử chạy ứng dụng hiện có trên JDK mới trước khi recompilation, sau đó cập nhật third-party libraries, compile và chạy `jdeps` theo vòng lặp. Cách này giúp tách lỗi runtime từ binary cũ khỏi lỗi do source/compiler mới.

Chạy artifact cũ trên JDK 26 trong môi trường kiểm thử, thu stdout/stderr, warning JVM, startup flags, JFR và kết quả test. Nếu JVM không khởi động, kiểm tra option đã bị gỡ hoặc GC flags. Nếu app chạy, so sánh hành vi với baseline cũ.

### Giai đoạn C — cập nhật dependency và build

- Cập nhật framework, Maven/Gradle wrapper, compiler plugin, annotation processor, JDBC driver, JMX client, security provider và agent lên phiên bản hỗ trợ JDK 26.
- Khai báo annotation processor tường minh. Từ JDK 23, `javac` không còn tự động chạy processor được phát hiện trên classpath theo mặc định.
- Dùng `--release` để xác định API/source/bytecode target.
- Không bật preview/incubator trong build production trừ khi đã có quyết định kiến trúc và kế hoạch nâng cấp.
- Kiểm tra dependency tree, license, checksum và nguồn tải artifact.

### Giai đoạn D — test theo ma trận rủi ro

| Khu vực | Kiểm thử tối thiểu |
|---|---|
| Startup/operations | Startup, readiness, shutdown, container memory, JVM flags, liveness probe |
| API/business | Unit, integration, contract, serialization và database migration |
| HTTP/network | HTTP/1.1, HTTP/2, HTTP/3 nếu bật, timeout, proxy, streaming, cookies, TLS |
| Security | Truststore, certificate chain, TLS hostname, crypto provider, keystore, JAR signature |
| JMX/monitoring | JMX URL, authentication, remote monitoring, APM agent, JFR |
| JDBC | Driver compatibility, transaction, LOB, SQL types, pool và failover |
| Locale/time | Locale formats, decimal, currency, charset, DST và time zone |
| Concurrency | Virtual threads, cancellation, locks, class initialization và thread dumps |
| Performance | Cold start, warm-up, throughput, p95/p99, CPU, RSS, allocation và GC |

### Giai đoạn E — canary và rollback

Triển khai một phần traffic hoặc một nhóm instance trước. So sánh error rate, latency percentile, CPU, heap, GC, TLS failures, database pool, queue depth và startup. Giữ artifact/runtime cũ cùng cấu hình để rollback được. Không xóa truststore, keystore hoặc JDK cũ cho tới khi thời gian quan sát đủ dài và các luồng tích hợp đã được xác nhận.

Chọn ngưỡng rollback trước khi rollout, ví dụ error rate vượt SLO, p99 tăng quá ngưỡng, startup/readiness thất bại hoặc TLS/database connection không ổn định. Rollback phải khôi phục cả JDK, JVM flags, container image và cấu hình tương ứng; chỉ đổi binary mà giữ JVM flags mới có thể không khôi phục được trạng thái cũ.

## 15. Checklist trước khi chuyển production

- [ ] Đã xác định chính xác JDK nguồn, vendor/build đích và các JDK trung gian cần đọc.
- [ ] Đã đọc JDK 26 Migration Guide, Release Notes và release notes của vendor.
- [ ] Đã quét deprecated API bằng `jdeprscan`.
- [ ] Đã quét JDK internal API bằng `jdeps` và kiểm tra cả reflection/JNI/native code.
- [ ] Đã kiểm tra Applet, `Thread.stop`, multicast TTL cũ, `jrunscript`, `jdk.jsobject`, SDP và XML interchange JMX.
- [ ] Đã tìm JVM options removed/deprecated trong script, container và service manager.
- [ ] Đã kiểm tra final field mutation bằng warning/debug và thử `deny` trong test.
- [ ] Đã cập nhật framework, build tool, annotation processor, driver, agent và provider.
- [ ] Đã kiểm tra TLS, truststore, keystore, certificate chain và algorithm support.
- [ ] Đã kiểm tra locale, decimal, charset, time zone và dữ liệu được format.
- [ ] Đã kiểm tra HTTP timeout/body, HTTP/3, proxy, cookies và `HttpContext` attributes nếu dùng.
- [ ] Đã kiểm tra JMXServiceURL, JDBC 4.5 và native/JVMTI integration nếu dùng.
- [ ] Đã phân loại preview/incubator và không vô tình bật chúng trong production.
- [ ] Đã chạy regression, load, soak và canary trên môi trường gần production.
- [ ] Đã ghi baseline, ngưỡng rollback, người phụ trách và cách khôi phục runtime cũ.

## 16. Các lỗi thường gặp khi đánh giá tương thích

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ đọc release notes JDK 26 khi nâng từ JDK 17 | Bỏ sót thay đổi từ JDK 18–25 | Đọc từng release trung gian hoặc migration guide đầy đủ |
| Chỉ chạy compile | Không thấy binary linkage, TLS, locale hoặc behavior regression | Chạy artifact cũ trên runtime mới và test end-to-end |
| Xem deprecated for removal như đã removed | Lập kế hoạch sửa sai hoặc kết luận sai khả năng chạy | Phân biệt removed, deprecated for removal và proposed for removal |
| Nghĩ `jdeps` phát hiện mọi reflection | Bỏ sót dynamic access và native code | Kết hợp static analysis, runtime warning, JFR và test |
| Thêm `--add-opens` cho mọi lỗi reflection | Che vấn đề encapsulation và final-field mutation | Mở đúng package/module khi cần, cập nhật library và xử lý final field riêng |
| Dùng `--enable-preview` để bật Vector API | Nhầm incubator module với preview language feature | Dùng `--add-modules jdk.incubator.vector` |
| Coi HTTP/3 là mặc định sau JDK 26 | Kỳ vọng giao thức không được thương lượng | Chọn HTTP_3 có chủ đích và xác minh protocol thực tế |
| Giữ JKS/JCEKS và certificate cũ mà không test | Warning hoặc TLS/provider failure | Chuyển PKCS12, cập nhật trust chain và kiểm tra provider |
| Giữ `-XX:+AggressiveHeap` hoặc `MaxRAM` cũ | JVM warning, tuning không rõ ràng hoặc lỗi ở future release | Dùng `-Xms`/`-Xmx` và collector rõ ràng |
| Bỏ qua final-field mutation warning | Thư viện có thể lỗi khi future JDK mặc định deny | Tìm caller, cập nhật dependency hoặc loại bỏ mutation |
| Chỉ kiểm thử trên máy developer | Bỏ sót container quota, OS, provider và certificate production | Test trên image, quota và network gần production |

## 17. Bài tập thực hành

Một dịch vụ đang chạy JDK 17, dùng Spring, Hibernate, JDBC driver, JMX monitoring, HTTP Client, keystore JKS và một thư viện serialization dùng reflection. Nhóm muốn nâng lên JDK 26 trong đợt triển khai tiếp theo.

**Yêu cầu:**

1. Lập inventory runtime, build tools, dependencies, JVM flags, agents và native integrations.
2. Lập danh sách release notes cần đọc từ JDK 18 đến JDK 26.
3. Chạy `jdeprscan --release 26` và `jdeps --jdk-internals` trên artifact cùng dependencies.
4. Kiểm tra code có dùng API đã gỡ như Applet hoặc `Thread.stop`, và phân biệt các API chỉ deprecated for removal.
5. Chạy ứng dụng cũ trên JDK 26, ghi nhận warning, TLS failures, locale output và JVM flag errors.
6. Bật `--illegal-final-field-mutation=debug`, xác định thư viện mutate `final` field và thử `deny` trong CI.
7. Cập nhật keystore sang PKCS12, kiểm tra trust chain và JCE provider.
8. Viết test cho HTTP request timeout với response body dài, `HttpContext` attributes và JMXServiceURL.
9. So sánh cold start/heap sizing và steady-state performance với cấu hình G1 của JDK cũ.
10. Lập rollout canary, ngưỡng rollback và kế hoạch khôi phục JDK 17.

**Kết quả mong đợi:**

- Có danh sách rủi ro tương thích được phân loại theo source, binary, behavioral, operational và security.
- Không nhầm API removed với API deprecated/proposed for removal.
- Dependency, JVM flags và security configuration đã được kiểm tra trên đúng vendor/build đích.
- Các thay đổi HTTP/JDBC/JMX/locale có regression test.
- Preview/incubator được ghi rõ và không trở thành dependency production ngoài chủ đích.
- Có baseline và quy trình rollout/rollback mà nhóm vận hành có thể thực hiện.

## Tài liệu tham khảo

- [Oracle JDK Migration Guide — Release 26](https://docs.oracle.com/en/java/javase/26/migrate/index.html): quy trình migration, significant changes, security updates, removed APIs và removed tools.
- [Preparing for Migration — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html): chạy ứng dụng trước recompilation, cập nhật thư viện, dùng `--release` và phân tích `jdeps`.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): source/binary/behavioral compatibility, preview/incubator, removed/deprecated features và thay đổi hành vi.
- [Removed APIs — JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html): API đã bị gỡ và API được đề xuất gỡ trong các release sau.
- [Removed Tools and Components — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/removed-tools-components.html): công cụ, module, JVM option, certificate và tính năng đã gỡ/deprecated.
- [Security Updates — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/security-updates.html): thay đổi về crypto, provider, certificate, HPKE và TLS.
- [Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html): warning, `--illegal-final-field-mutation`, `--enable-final-field-mutation` và cách tìm library gây mutation.
- [The `jdeprscan` Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html): quét deprecated Java SE APIs.
- [The `jdeps` Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html): phân tích dependency và JDK internal APIs.
- [HttpClient — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP/1.1, HTTP/2, HTTP/3 và lựa chọn protocol.
- [HotSpot Virtual Machine Garbage Collection Tuning Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/hotspot-virtual-machine-garbage-collection-tuning-guide.html): G1 ergonomics và `GCTimeRatio`.
