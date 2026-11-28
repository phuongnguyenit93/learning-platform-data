# Phân loại lỗi nâng cấp và chọn thay thế bằng API, công cụ hoặc nền tảng còn được hỗ trợ

## 1. Phạm vi và nguyên tắc đánh giá

Nâng cấp JDK không chỉ là đổi đường dẫn cài đặt. Ứng dụng có thể biên dịch được nhưng không liên kết được khi chạy, khởi động thành công nhưng thay đổi hành vi, hoặc vẫn đúng chức năng nhưng có độ trễ và mức sử dụng bộ nhớ khác trước.

Trong module **JAVA_VERSION_JAVA25**, bài này tập trung vào cách phân loại lỗi và chọn phương án thay thế còn được hỗ trợ khi nâng từ JDK 25 lên các bản phát hành mới hơn.

**Mốc phiên bản được dùng trong bài:**

- JDK 25: phát hành tháng 9/2025, là baseline cho các ví dụ về API và runtime.
- JDK 26: loại bỏ Applet API và phương thức Thread.stop; bắt đầu cảnh báo khi deep reflection sửa final field.
- JDK 27: phát hành tháng 9/2026; tiếp tục cảnh báo final-field mutation, loại bỏ JVMCI tích hợp, VFORK trên Linux và một số cờ launcher; G1 và compact object headers trở thành mặc định trong HotSpot.
- JDK 27.0.1.1: bản cập nhật phát hành ngày 17/11/2026. Khi triển khai thực tế, hãy chọn security update mới nhất của vendor đang dùng thay vì chỉ pin vào feature release ban đầu.

Oracle JDK, OpenJDK và các bản phân phối thương mại có thể khác nhau về thành phần đi kèm, flags và lịch cập nhật. Hãy kiểm tra release notes của đúng vendor và build đích. Bài dùng tài liệu Oracle/OpenJDK làm mốc kỹ thuật.

**Nguyên tắc quan trọng:** trước khi thay API, xác định lỗi thuộc source compatibility, binary compatibility, behavioral compatibility, cấu hình JVM, bảo mật hay hiệu năng. Một exception có thể chỉ ra triệu chứng, nhưng nguyên nhân thường nằm ở dependency, launcher hoặc môi trường chạy.

## 2. Phân loại lỗi tương thích

Java release notes phân biệt ba loại tương thích chính:

| Loại | Câu hỏi cần trả lời | Triệu chứng thường gặp |
|---|---|---|
| Source compatibility | Source hiện tại có biên dịch được bằng compiler mới không? | cannot find symbol, package does not exist, API bị xóa hoặc module không còn |
| Binary compatibility | Class file đã biên dịch có liên kết được với runtime và thư viện mới không? | NoSuchMethodError, NoSuchFieldError, NoClassDefFoundError, AbstractMethodError |
| Behavioral compatibility | Chương trình có còn tạo ra cùng kết quả và tác động vận hành không? | Format ngày/tiền tệ thay đổi, TLS handshake thất bại, route HTTP khác, latency hoặc heap thay đổi |

Ngoài ba nhóm trên, nên tách thêm ba nhóm vận hành:

- **Launch/configuration:** JVM không khởi động vì flag đã bị loại bỏ, bị đổi tên hoặc không còn được nhận diện.
- **Encapsulation/security:** reflection, native access, certificate, provider hoặc chính sách thuật toán không còn cho phép hành vi cũ.
- **Performance/observability:** collector mặc định, object layout, JIT, GC log hoặc monitoring counter thay đổi.

### Không nhầm lỗi class file với lỗi API

UnsupportedClassVersionError thường cho biết runtime quá cũ để đọc class file được biên dịch bằng target mới hơn. Đây là lỗi bytecode version, không phải bằng chứng một API đã bị xóa.

NoSuchMethodError thường xuất hiện khi class file liên kết với một chữ ký method không còn trong class được nạp lúc runtime. Nguyên nhân phổ biến là dependency version lệch giữa compile time và runtime, hoặc một API đã bị loại bỏ.

InaccessibleObjectException thường chỉ ra code đang cố truy cập thành phần bị strong encapsulation bảo vệ. Thay đổi JDK có thể làm lộ dependency reflection đã tồn tại từ trước.

## 3. Quy trình điều tra trước khi sửa code

Dùng quy trình có thể lặp lại cho mỗi baseline và mỗi vendor:

1. Ghi lại JDK vendor, full version/build, OS, architecture, container image, JVM flags và cách khởi chạy.
2. Chạy ứng dụng hiện tại trên JDK đích trước khi biên dịch lại. Ghi nhận warning, lỗi khởi động và hành vi khác biệt.
3. Nâng các framework, build plugins, agent và thư viện bên thứ ba lên phiên bản hỗ trợ JDK đích.
4. Chạy jdeps để tìm phụ thuộc vào internal JDK API.
5. Chạy jdeprscan để tìm API đã deprecated, đặc biệt nhóm forRemoval.
6. Biên dịch bằng compiler mới với --release phù hợp.
7. Chạy test chức năng, tích hợp, bảo mật và hiệu năng trên đúng runtime đích.
8. Chạy canary hoặc staging với workload đại diện; so sánh latency, throughput, heap, GC, TLS và lỗi.
9. Chỉ chuyển production khi có kết quả đối chiếu và phương án rollback đã được kiểm chứng.

Oracle khuyến nghị thử chạy ứng dụng trên JDK mới trước khi biên dịch lại, đồng thời cập nhật thư viện, biên dịch nếu cần và chạy jdeps. Việc ứng dụng khởi động thành công chưa đủ để kết luận nâng cấp an toàn.

## 4. Dùng công cụ JDK để tìm nguyên nhân

### 4.1. Xác nhận đúng runtime và compiler

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Ghi lại java.home, java.version, java.vendor, os.arch và các JVM arguments. Trong CI, kiểm tra JDK dùng cho compile, test, packaging và production launcher; các bước này có thể đang dùng các JDK khác nhau.

### 4.2. Tìm internal JDK API bằng jdeps

```bash
jdeps --multi-release 27 --jdk-internals --recursive application.jar
```

Dùng cùng lệnh với các JAR của framework và thư viện nội bộ. Kết quả chỉ ra phụ thuộc tĩnh vào internal API và đôi khi gợi ý API thay thế.

jdeps là phân tích tĩnh. Nó không phát hiện đầy đủ truy cập qua reflection, tên class được nạp động, cấu hình XML hoặc chuỗi class name lấy từ bên ngoài. Cần kết hợp test runtime, log và kiểm tra cấu hình.

### 4.3. Tìm API deprecated for removal bằng jdeprscan

```bash
jdeprscan --release 27 -l --for-removal application.jar
```

Lệnh này giúp lập danh sách API được đánh dấu chờ loại bỏ trong release mục tiêu. Chạy lại sau khi nâng dependency để biết thư viện mới còn tham chiếu API nào không.

### 4.4. Kiểm tra class file và JAR

```bash
javap -verbose -classpath application.jar com.example.Main
jar --validate --file application.jar
```

javap -verbose hiển thị major version và thông tin class file. jar --validate kiểm tra các vấn đề cấu trúc JAR như entry trùng tên, đường dẫn bất thường và tính nhất quán của header.

### 4.5. Dùng log và JFR khi lỗi chỉ xuất hiện lúc chạy

```bash
java -Xlog:class+load=info,exceptions=info -jar application.jar
```

Khi nghi ngờ monitor contention hoặc thay đổi final field, dùng JFR để ghi event tương ứng. Không cần bật tất cả log ở mức trace trong thời gian dài; hãy chọn tag theo giả thuyết và giữ recording đủ ngắn để so sánh.

## 5. API hoặc hành vi đã bị loại bỏ: chọn thay thế theo chức năng

Bảng dưới đây tổng hợp các thay đổi có tác động thực tế trong giai đoạn JDK 25–27. Tên API/cờ cũ chỉ xuất hiện để giúp nhận diện điểm cần sửa.

| Dấu hiệu trong code hoặc log | Trạng thái trên JDK mới | Hướng thay thế còn hỗ trợ |
|---|---|---|
| Socket constructor dùng stream=false để tạo datagram socket | Từ JDK 25 ném IllegalArgumentException | Dùng java.net.DatagramSocket cho UDP |
| java.applet.*, javax.swing.JApplet | Applet API bị loại bỏ trong JDK 26 | Chuyển giao diện sang web app hoặc ứng dụng desktop độc lập |
| Thread.stop | Bị loại bỏ trong JDK 26 | Dùng cooperative cancellation: interrupt, cờ hủy và kiểm tra trạng thái trong tác vụ |
| ThreadPoolExecutor.finalize | Bị loại bỏ trong JDK 27 | Quản lý vòng đời executor tường minh bằng shutdown, awaitTermination hoặc ExecutorService trong try-with-resources |
| Các method truy cập memory của sun.misc.Unsafe | Deprecated for removal | Dùng VarHandle cho field/array và thao tác memory có kiểu; dùng Foreign Function & Memory API cho native/off-heap memory |
| Counter sun.rt._sync* | Bị loại bỏ trong JDK 25 | Dùng các JFR monitor events tương ứng |
| PerfData periodic sampling | Bị loại bỏ trong JDK 25 | Dùng JFR hoặc JMX/MXBeans cho dữ liệu cần quan sát |
| jdk.lang.Process.launchMechanism=VFORK trên Linux | Deprecated trong JDK 25, bị loại bỏ trong JDK 27 | Dùng mặc định POSIX_SPAWN; nếu có lý do tương thích cụ thể, kiểm tra FORK |
| JVMCI/Graal JIT tích hợp của Oracle JDK | JVMCI và các cờ liên quan bị loại bỏ trong JDK 27 | Dùng C2 compiler mặc định của HotSpot hoặc chọn bản phân phối GraalVM có ghi rõ hỗ trợ JDK mục tiêu |
| UseCompressedClassPointers | Deprecated trong JDK 25, obsolete trong JDK 27 | Bỏ cờ; HotSpot JDK 27 luôn dùng compressed class pointers |
| noverify, Xverify:none | Bị loại bỏ trong JDK 27 | Không tắt bytecode verification; sửa bytecode hoặc dependency không hợp lệ |
| verifyremote | Bị loại bỏ trong JDK 27 | Nếu thực sự cần chế độ tương ứng, dùng Xverify:remote |
| noclassgc | Bị loại bỏ trong JDK 27 | Dùng Xnoclassgc nếu có yêu cầu vận hành đã được chứng minh; thông thường nên giữ class unloading mặc định |

Một số API không có phép thay thế một-một. Ví dụ, applet phải được chuyển đổi ở cấp kiến trúc giao diện và cách phân phối ứng dụng. Không nên tìm một thư viện giả lập Java plugin để kéo dài mô hình đã bị nền tảng loại bỏ.

## 6. Ví dụ: sửa việc dùng Socket cho UDP

Từ JDK 25, hai constructor java.net.Socket có tham số stream không còn cho phép tạo datagram socket khi stream là false. Dùng abstraction đúng với giao thức:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

public class UdpSender {
    public static void send(byte[] payload, String host, int port)
            throws Exception {
        InetAddress address = InetAddress.getByName(host);

        try (DatagramSocket socket = new DatagramSocket()) {
            DatagramPacket packet =
                new DatagramPacket(payload, payload.length, address, port);
            socket.send(packet);
        }
    }
}
```

DatagramSocket biểu diễn UDP và có vòng đời tài nguyên rõ ràng. Hãy kiểm tra timeout, packet size, DNS, firewall và xử lý mất/gửi lặp packet theo yêu cầu giao thức của ứng dụng.

## 7. Internal API, strong encapsulation và reflection

Từ JDK 17, strong encapsulation ngăn truy cập mặc định vào nhiều thành phần nội bộ của JDK. Khi một thư viện dùng reflection để truy cập private field hoặc method của JDK, lỗi có thể xuất hiện dưới dạng InaccessibleObjectException hoặc IllegalAccessError.

Cách xử lý:

1. Dùng jdeps --jdk-internals để tìm phụ thuộc tĩnh.
2. Kiểm tra stack trace để xác định thư viện gọi reflection.
3. Nâng thư viện lên phiên bản đã hỗ trợ module encapsulation và JDK mục tiêu.
4. Nếu đang truy cập internal API trong code của mình, thay bằng public API hoặc SPI được hỗ trợ.
5. Chỉ dùng --add-opens như biện pháp chuyển tiếp có phạm vi module/package cụ thể trong khi nâng cấp dependency.

Không dùng --illegal-access làm giải pháp. Tùy chọn này đã obsolete từ JDK 17 và không khôi phục relaxed encapsulation.

### Thay memory access của Unsafe theo mục đích

Không phải mọi thao tác Unsafe đều có cùng phép thay thế:

| Mục đích | API được hỗ trợ |
|---|---|
| Đọc/ghi field, array element hoặc thao tác truy cập có kiểu | VarHandle |
| Atomic update và memory ordering | VarHandle hoặc các lớp java.util.concurrent.atomic |
| Truy cập vùng nhớ native/off-heap | Foreign Function & Memory API (Arena, MemorySegment, Linker) |
| Gọi hàm native | Foreign Function & Memory API hoặc JNI khi dự án có yêu cầu tương thích cụ thể |

Ví dụ cấp phát vùng nhớ native có vòng đời được quản lý:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

public class NativeBuffer {
    public static void useBuffer() {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment buffer = arena.allocate(1024);
            buffer.fill((byte) 0);
            // Dùng buffer trong phạm vi arena.
        }
    }
}
```

Arena quản lý vòng đời vùng nhớ; sau khi arena đóng, segment không còn được phép truy cập. Với VarHandle, chọn đúng access mode và memory ordering theo yêu cầu đồng bộ hóa. Không thay một lệnh Unsafe bằng VarHandle chỉ dựa trên tên method mà chưa kiểm tra ngữ nghĩa.

## 8. Chuẩn bị cho hạn chế sửa final field bằng deep reflection

Từ JDK 26, JVM cảnh báo khi code dùng deep reflection để sửa final instance field. JDK 27 tiếp tục phát cảnh báo này. Một release tương lai dự kiến sẽ từ chối thao tác đó mặc định.

Nguyên nhân thường nằm trong thư viện serializer, dependency injection, mocking, object mapper hoặc framework cố ghi trực tiếp vào final field.

### Tìm thư viện gây mutation

Chạy ở môi trường kiểm thử:

```bash
java --illegal-final-field-mutation=debug -jar application.jar
```

Hoặc bật JFR và đọc event:

```bash
jfr print --events jdk.FinalFieldMutation recording.jfr
```

Event có class khai báo field, tên field, thread và stack trace để truy ra thư viện thực hiện mutation.

### Kiểm tra tương lai bằng chế độ deny

```bash
java --illegal-final-field-mutation=deny -jar application.jar
```

Nếu ứng dụng thất bại, nâng cấp hoặc thay thư viện gây mutation và kiểm tra cách khởi tạo object qua constructor, factory, builder hoặc API chính thức của framework.

--enable-final-field-mutation có thể bật tạm cho các module được xác định cụ thể nếu dependency chưa thể thay ngay. Đây là ngoại lệ chuyển tiếp, không phải cấu hình đích. Không bật ALL-UNNAMED cho toàn bộ classpath chỉ để che warning.

## 9. Thay monitoring counter đã bị loại bỏ bằng JFR và JMX

JDK 25 loại bỏ PerfData periodic sampling và các counter monitor cũ trong namespace sun.rt._sync*. Công cụ đọc trực tiếp file PerfData hoặc dựa vào các counter nội bộ này cần được cập nhật.

### Thay thế counter monitor

| Counter đã bị loại bỏ | JFR event thay thế |
|---|---|
| _sync_ContendedLockAttempts | jdk.JavaMonitorEnter |
| _sync_Parks | jdk.JavaMonitorWait |
| _sync_Notifications | jdk.JavaMonitorNotify |
| _sync_Inflations | jdk.JavaMonitorInflate |
| _sync_Deflations | jdk.JavaMonitorDeflate |
| _sync_MonExtant | jdk.JavaMonitorStatistics |
| _sync_FutileWakeups | Không có replacement tương ứng được chỉ định |

Với heap usage và dữ liệu quản trị, dùng JMX/MXBeans hoặc JFR thay cho việc đọc PerfData trực tiếp. JFR phù hợp để phân tích sự kiện theo thời gian và stack trace; MXBeans phù hợp cho metric trạng thái hiện tại và polling định kỳ.

Không giả định mọi counter cũ đều có metric thay thế tương đương. Nếu một counter không có replacement, hãy xác định câu hỏi vận hành thực sự cần trả lời rồi thiết kế metric cấp ứng dụng hoặc instrumentation khác.

## 10. Sửa JVM flags và logging đã obsolete

### 10.1. VFORK trên Linux

JDK 25 đã deprecated VFORK; JDK 27 loại bỏ cơ chế này. Hãy bỏ cấu hình launch mechanism cũ và dùng mặc định POSIX_SPAWN. Chỉ chọn FORK nếu đã có lý do tương thích được kiểm thử.

### 10.2. JVMCI/Graal JIT

JDK 27 loại bỏ JVMCI tích hợp trong HotSpot của Oracle JDK, các module JVMCI/Graal liên quan và cờ có tên chứa JVMCI, bao gồm UseGraalJIT.

Nếu ứng dụng phụ thuộc Graal JIT:

- Đánh giá lại hiệu năng với C2 compiler mặc định của HotSpot.
- Nếu Graal compiler là yêu cầu bắt buộc, chọn một bản phân phối GraalVM có hỗ trợ rõ ràng cho JDK baseline mà dự án định chạy; kiểm tra lịch phát hành và vòng đời hỗ trợ của vendor. Tại thời điểm 27/11/2026, lịch phát hành GraalVM công bố nhánh feature 25.x; không giả định bản đó là runtime thay thế trực tiếp cho JDK 27.
- Không giả định một module jdk.graal.compiler có thể được mang từ JDK cũ sang JDK 27.

### 10.3. Launcher options

| Cờ cũ | Hành động |
|---|---|
| noverify, Xverify:none | Xóa; không có replacement |
| verifyremote | Dùng Xverify:remote nếu chế độ này thực sự cần |
| noclassgc | Dùng Xnoclassgc nếu đã chứng minh cần giữ class không unload |

Không tắt verifier để che lỗi bytecode. Nếu một agent hoặc bytecode generator sinh class không hợp lệ, cập nhật agent/generator thay vì tắt kiểm tra.

### 10.4. Chuyển sang Unified Logging

JDK 27 loại bỏ một số tracing flags đã được thay thế từ lâu bằng Unified Logging:

| Tracing flag cũ | Cấu hình còn hỗ trợ |
|---|---|
| TraceClassLoading | -Xlog:class+load=info |
| TraceClassUnloading | -Xlog:class+unload=info |
| TraceExceptions | -Xlog:exceptions=info |
| Xloggc:gc.log | -Xlog:gc:file=gc.log |

Ví dụ ghi GC log có xoay vòng file:

```bash
java '-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar application.jar
```

Nếu parser cũ đọc format log riêng của GC, hãy cập nhật parser theo Unified Logging tags và decorators; không chỉ thay flag mà giữ nguyên giả định về format cũ.

## 11. Thay đổi hành vi: locale, charset và timezone

Một ứng dụng có thể không ném exception nhưng vẫn trả về chuỗi hoặc thời điểm khác trước.

### Charset mặc định

Từ JDK 18, UTF-8 là default charset trên mọi hệ điều hành. Ứng dụng nâng từ JDK 17 trở về trước có thể thay đổi cách đọc/ghi file nếu trước đây phụ thuộc code page của máy.

Chỉ định charset khi định dạng giao thức hoặc file yêu cầu một encoding cụ thể:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

byte[] bytes = Files.readAllBytes(Path.of("input.txt"));
String content = new String(bytes, StandardCharsets.UTF_8);
```

Với text protocol, config file và file được trao đổi giữa hệ thống, hãy chỉ định charset rõ ràng thay vì dựa vào default của host.

### Locale và định dạng ngày/tiền tệ

CLDR là nguồn locale data mặc định của Java. Phiên bản CLDR thay đổi theo JDK release; JDK 25 dùng CLDR 47, JDK 27 dùng CLDR 48.2. Format ngày, số, tiền tệ, tên quốc gia hoặc cách parse có thể thay đổi.

Property `java.locale.useOldISOCodes` không còn tác dụng từ JDK 25 và bị loại bỏ trong JDK 27. Nếu dữ liệu tích hợp còn dùng mã ngôn ngữ ISO cũ cho Hebrew, Indonesian hoặc Yiddish, cập nhật dữ liệu sang mã hiện hành `he`, `id` và `yi`; không giữ property cũ trong launcher.

Nếu kết quả là dữ liệu nghiệp vụ, hãy truyền Locale rõ ràng và dùng formatter có pattern đã được định nghĩa:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat format =
    NumberFormat.getCurrencyInstance(Locale.forLanguageTag("vi-VN"));
```

Không so sánh chuỗi format phụ thuộc locale như thể đó là định dạng lưu trữ ổn định. Với dữ liệu máy đọc, dùng định dạng chuẩn hóa; với hiển thị, kiểm thử theo locale mục tiêu.

### Timezone database

JDK mang theo dữ liệu IANA timezone và dữ liệu này được cập nhật theo release. JDK 25, JDK 27 và các bản cập nhật của JDK 27 có thể chứa các phiên bản timezone khác nhau.

Kiểm tra các nghiệp vụ phụ thuộc giờ mùa hè, lịch sử múi giờ, ngày chuyển đổi và thời điểm nửa đêm tại địa phương. Dùng ZoneId có tên vùng thay cho offset cố định khi nghiệp vụ gắn với timezone địa lý.

## 12. Thay đổi networking và security cần kiểm thử

### HTTP server tích hợp

Trong JDK 27, com.sun.net.httpserver.HttpServer đổi cách so khớp context path từ string-prefix sang path-prefix. Ví dụ context /foo khớp /foo, /foo/ và /foo/bar, nhưng không khớp /foobar.

Nếu ứng dụng dùng HttpServer, hãy kiểm thử route gần nhau, route có dấu / cuối và route có segment tương tự. Không dựa vào behavior string-prefix cũ để định tuyến hoặc kiểm soát truy cập.

### TLS, truststore và crypto provider

JDK release có thể cập nhật TLS algorithms, security properties, CA certificates và provider implementation.

Một số trường hợp cần kiểm tra:

- JDK 25 loại bỏ một số root certificate đã hết hạn hoặc không còn sử dụng khỏi cacerts.
- Một số SecretKeyFactory PBE implementation của SunPKCS11 bị loại bỏ trong JDK 25 do cách biểu diễn key encoding không nhất quán với SunJCE.
- JDK 27 bổ sung hybrid post-quantum key exchange cho TLS 1.3 trong JSSE; cần kiểm thử với proxy, load balancer và peer TLS trong hệ thống.

Khi handshake hoặc thao tác HSM thất bại, thu thập TLS handshake diagnostics, provider name, algorithm và certificate chain. Cập nhật truststore hoặc provider theo yêu cầu bảo mật hiện tại. Không khôi phục một CA đã hết hạn hoặc nới lỏng disabledAlgorithms chỉ để làm cho kết nối cũ tiếp tục chạy.

## 13. Thay đổi mặc định có thể ảnh hưởng hiệu năng

JDK 27 thay đổi một số mặc định của HotSpot:

- G1 trở thành garbage collector mặc định trong mọi môi trường.
- Compact object headers được bật mặc định.
- UseCompressedClassPointers trở thành obsolete; class pointers luôn được nén trong object.

Những thay đổi này có thể ảnh hưởng heap footprint, pause, throughput, native agent, profiler và công cụ phân tích heap. Một ứng dụng có thể chạy đúng chức năng nhưng có hiệu năng khác trước.

Quy trình kiểm tra:

1. Ghi baseline latency, throughput, allocation rate, heap committed/used và GC pause trên JDK cũ.
2. Chạy cùng workload trên JDK mới với mặc định của runtime.
3. So sánh CPU, GC, memory, safepoint và latency p95/p99.
4. Kiểm tra native agent/JVMTI/profiler không dựa vào layout object nội bộ.
5. Chỉ điều chỉnh collector hoặc object-header option khi có dữ liệu tái lập.

Không dùng object header layout hoặc offset nội bộ làm contract của ứng dụng. Nếu native code cần truy cập object, dùng JNI/FFM và API được hỗ trợ thay vì tự giả định cấu trúc heap.

## 14. Lỗi build, bytecode và preview/incubator

### Dùng --release để khóa API target

Khi compiler mới hơn runtime triển khai, dùng --release để khóa language level, class file target và Java SE API tương ứng:

```bash
javac --release 25 -d out src/com/example/*.java
```

Trong Maven/Gradle, cấu hình toolchain/compiler release nhất quán cho compile, test và packaging. Không chỉ đặt sourceCompatibility mà quên target runtime hoặc dependency bytecode.

### Kiểm tra class file version

Nếu gặp UnsupportedClassVersionError:

1. Kiểm tra runtime thực tế bằng java -version.
2. Kiểm tra compiler/build tool đã dùng JDK nào.
3. Xem major version bằng javap -verbose.
4. Biên dịch lại bằng --release phù hợp hoặc nâng runtime theo baseline được hỗ trợ.
5. Kiểm tra mọi dependency JAR, agent và plugin có class file mới hơn runtime không.

### Preview và incubator không phải API ổn định

Preview class file gắn với release mà nó được biên dịch; không giả định class file preview của JDK 25 chạy được trên JDK 26/27. Incubator module cũng có thể đổi API hoặc bị loại bỏ giữa các release.

Với ứng dụng production và thư viện dùng chung, ưu tiên API final. Nếu dự án thử nghiệm preview/incubator, pin đúng JDK, compile/run với đúng flags, cô lập dependency và có kế hoạch bỏ hoặc cập nhật khi nâng release. Không bật --enable-preview toàn cục để chữa lỗi tương thích.

## 15. Ví dụ thay cooperative cancellation cho Thread.stop

Khi tác vụ cần dừng, dùng interruption và cho phép code thoát an toàn:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WorkerExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                 Executors.newSingleThreadExecutor()) {
            Future<?> task = executor.submit(() -> {
                while (!Thread.currentThread().isInterrupted()) {
                    doOneUnitOfWork();
                }
            });

            // Khi cần hủy:
            task.cancel(true);
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static void doOneUnitOfWork() {
        // Thực hiện một phần công việc có thể kết thúc an toàn.
    }
}
```

Trong code thực tế, xử lý InterruptedException bằng cách phục hồi interrupt status khi cần và giải phóng resource trong finally hoặc try-with-resources. Tác vụ phải kiểm tra interrupt ở điểm an toàn; không giả định JVM có thể cưỡng bức dừng bất kỳ đoạn code nào mà vẫn giữ được invariant.

## 16. Ví dụ thay finalization bằng quản lý vòng đời tường minh

Đối với resource như file, socket, database connection hoặc native memory, dùng AutoCloseable và try-with-resources:

```java
public final class DataSession implements AutoCloseable {
    private boolean closed;

    public void execute() {
        if (closed) {
            throw new IllegalStateException("Session is closed");
        }
        // Thực hiện công việc.
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            // Giải phóng resource tường minh.
        }
    }
}

try (DataSession session = new DataSession()) {
    session.execute();
}
```

Cleaner chỉ phù hợp như lớp bảo vệ cuối cùng khi resource có thể bị bỏ quên; nó không thay thế quy trình đóng resource xác định. Với executor, gọi shutdown và chờ hoàn tất hoặc dùng ExecutorService trong try-with-resources trên JDK hỗ trợ.

## 17. Ma trận lỗi nâng cấp và hành động đầu tiên

| Triệu chứng | Nhóm lỗi ưu tiên | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|---|
| cannot find symbol | Source/API | Release notes, compile classpath, module graph | Thay API bị xóa hoặc nâng dependency |
| NoSuchMethodError | Binary/linkage | Dependency tree và class được nạp | Đồng bộ compile/runtime versions, rebuild |
| UnsupportedClassVersionError | Bytecode target | java -version, javap -verbose | Dùng --release hoặc nâng runtime |
| InaccessibleObjectException | Encapsulation | Stack trace, thư viện reflection | Nâng/thay library; mở package có giới hạn chỉ tạm thời |
| IllegalArgumentException khi tạo UDP | Behavioral/API | Constructor Socket với stream=false | Dùng DatagramSocket |
| JVM không khởi động, Unrecognized VM option | Launcher/config | JVM arguments trong script/container | Xóa hoặc chuyển sang option hiện hành |
| Warning final field mutation | Reflection/security | --illegal-final-field-mutation=debug, JFR | Nâng/thay thư viện, thử deny |
| GC/monitor dashboard mất số liệu | Observability | PerfData reader, sun.rt._sync* | Chuyển sang JFR/JMX/MXBeans |
| Date/currency parse hoặc format khác | Behavioral/locale | Locale, CLDR, timezone data | Truyền Locale/ZoneId/format rõ ràng, cập nhật test |
| TLS/HSM handshake thất bại | Security/provider | Certificate chain, provider, algorithm | Cập nhật truststore/provider và kiểm thử peer |
| p99/heap/CPU thay đổi | Performance/defaults | GC, object header, JIT, CPU quota | So sánh cùng workload, đo rồi mới tune |

## 18. Kế hoạch kiểm thử và rollout

Một migration có thể được chia thành các cổng kiểm tra:

### Gate 1 — Tĩnh

- jdeps --jdk-internals không còn dependency internal chưa có kế hoạch xử lý.
- jdeprscan --for-removal đã được phân loại theo owner và deadline.
- JAR, module descriptor, agents và JVM flags đã được kiểm kê.
- Không còn preview class file ngoài phạm vi project thử nghiệm được pin JDK.

### Gate 2 — Khởi động và liên kết

- Ứng dụng khởi động trên JDK đích.
- Không còn warning về option obsolete, internal reflection hoặc final-field mutation chưa được xử lý.
- Các service loader, JNI/FFM, agent và framework được load đúng.
- Test runner và production launcher dùng cùng bộ flags đã kiểm soát.

### Gate 3 — Hành vi và bảo mật

- Test route HTTP, locale, charset, timezone, serialization và dữ liệu biên.
- Test TLS handshake, trust chain, HSM/provider và certificate rotation.
- Test cancellation, resource cleanup, reflection và module access.
- Test API integrations với peer/agent bên ngoài.

### Gate 4 — Hiệu năng và vận hành

- So sánh latency p50/p95/p99, throughput, CPU, heap, GC và startup.
- Ghi JFR để phân tích CPU, allocation, lock và thread.
- Kiểm tra dashboards/alerts sau khi chuyển monitoring từ internal counters.
- Canary trước khi mở rộng; giữ artifact và JDK cũ để rollback trong thời gian được phê duyệt.

## 19. Checklist trước khi chốt nâng cấp

- [ ] Đã ghi rõ vendor, JDK full version/build, OS, architecture và container image.
- [ ] Đã phân loại vấn đề source, binary, behavioral, launch, security và performance.
- [ ] Đã chạy ứng dụng trên JDK đích trước khi biên dịch lại.
- [ ] Đã cập nhật framework, build tool, agent và dependency.
- [ ] Đã chạy jdeps --jdk-internals trên ứng dụng và thư viện liên quan.
- [ ] Đã chạy jdeprscan --release 27 -l --for-removal.
- [ ] Đã dùng --release và xác nhận class file target.
- [ ] Đã loại bỏ dependency internal JDK API và reflection không được hỗ trợ.
- [ ] Đã thay các API/cờ bị loại bỏ bằng lựa chọn còn được hỗ trợ.
- [ ] Đã xử lý final-field mutation và kiểm tra bằng chế độ deny.
- [ ] Đã chuyển monitoring sang JFR/JMX khi PerfData hoặc internal counters không còn phù hợp.
- [ ] Đã kiểm thử locale, charset, timezone, TLS, provider và HTTP routing.
- [ ] Đã đo lại G1, compact object headers, heap và latency trên workload đại diện.
- [ ] Đã xác nhận vendor runtime và bản cập nhật đang dùng còn được hỗ trợ.
- [ ] Đã có canary, rollback plan và tiêu chí dừng rollout.

### Tài liệu tham khảo chính thức

1. [Oracle JDK Migration Guide, Release 27](https://docs.oracle.com/en/java/javase/27/migrate/index.html)
2. [Oracle JDK Migration Guide — Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html)
3. [Oracle JDK Migration Guide — Removed APIs](https://docs.oracle.com/en/java/javase/27/migrate/removed-apis.html)
4. [Oracle JDK Migration Guide — Removed Tools and Components](https://docs.oracle.com/en/java/javase/27/migrate/removed-tools-components.html)
5. [Oracle JDK Migration Guide — Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/27/migrate/preparing-final-field-mutation-restrictions.html)
6. [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
7. [Consolidated JDK 27 Release Notes and Update History](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
8. [Oracle JDK 26 Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
9. [Oracle JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html)
10. [Oracle Java SE 27 — The java Command and Unified Logging](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
11. [Oracle Java SE 27 — The jdeps Tool](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html)
12. [Oracle Java SE 27 — The jdeprscan Tool](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html)
13. [Oracle Java SE 27 — Internationalization Guide](https://docs.oracle.com/en/java/javase/27/intl/index.html)
14. [Oracle Java SE 27 — Deprecated API List](https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html)
15. [GraalVM Release Calendar](https://www.graalvm.org/release-calendar/)
