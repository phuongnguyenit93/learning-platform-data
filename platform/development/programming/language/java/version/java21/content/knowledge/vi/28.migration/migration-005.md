# Thay truy cập JDK internal API bằng API được hỗ trợ

JDK internal API là các lớp, phương thức hoặc trường chỉ phục vụ việc triển khai JDK. Chúng không phải hợp đồng ổn định cho ứng dụng. Tên, cấu trúc, quyền truy cập hoặc hành vi của chúng có thể thay đổi giữa các bản JDK, khiến ứng dụng không biên dịch được hoặc gặp lỗi khi chạy.

Khi nâng cấp lên Java 21 và các JDK mới hơn, cần loại bỏ phụ thuộc vào internal API, thay bằng Java SE API hoặc API JDK được tài liệu hóa và hỗ trợ. Việc này đặc biệt quan trọng vì JDK 17 đã bật strong encapsulation cho hầu hết internal API; các quyền truy cập cũ qua reflection không còn được cho phép mặc định. Một số lớp như `sun.misc.Unsafe` vẫn còn trong JDK nhưng các phương thức truy cập bộ nhớ của nó đã bị deprecated for removal và phát cảnh báo ở các JDK mới.

## 1. Nhận diện JDK internal API

Các package như `sun.*`, `jdk.internal.*` và một số package triển khai nội bộ dưới `com.sun.*` thường chứa API không dành cho ứng dụng. Tuy nhiên, không nên kết luận chỉ từ prefix: JDK cũng có một số package `com.sun.*` được tài liệu hóa và export như API JDK. Hãy kiểm tra Javadoc, module descriptor và kết quả `jdeps` để xác định một API có được hỗ trợ hay không.

Phân biệt ba nhóm sau:

| Nhóm | Đặc điểm | Cách xử lý |
|---|---|---|
| Java SE API | Được đặc tả trong Java Platform API, ví dụ `java.util`, `java.lang.invoke`, `java.nio` | Ưu tiên sử dụng |
| API JDK được tài liệu hóa | Có thể thuộc module JDK mở rộng ngoài Java SE; có tài liệu và cam kết hỗ trợ theo sản phẩm | Kiểm tra yêu cầu runtime và mức tương thích trước khi dùng |
| Internal API | Chi tiết triển khai, không có cam kết tương thích cho ứng dụng | Thay bằng API được hỗ trợ |

Một API không tự trở thành API được hỗ trợ chỉ vì nó public, có thể import, nằm trong module `jdk.unsupported` hoặc hiện vẫn chạy được. Khả năng truy cập ở một phiên bản cụ thể không phải cam kết sẽ tồn tại ở phiên bản tiếp theo.

## 2. Strong encapsulation và thay đổi từ JDK 17

JDK 9 đưa vào module system (JPMS) và cơ chế encapsulation. JDK 16 chuyển sang strong encapsulation mặc định cho phần lớn internal API; JDK 17 hoàn tất việc strong encapsulation theo JEP 403. Vì vậy, code dựa vào truy cập nội bộ có thể gặp các lỗi như:

- `IllegalAccessError` khi bytecode truy cập kiểu hoặc thành viên trong package không được export.
- `InaccessibleObjectException` khi reflection cố truy cập thành viên không được mở cho module gọi.
- Lỗi biên dịch khi source import một internal type không được export hoặc không còn tồn tại.
- `NoClassDefFoundError` hoặc `NoSuchMethodError` nếu internal class hoặc method bị thay đổi/xóa giữa các runtime.

Tùy chọn `--illegal-access` đã obsolete từ JDK 17 và không còn mở lại cơ chế truy cập rộng của các JDK cũ. Không thêm `--illegal-access=permit`, `warn`, `debug` hoặc `deny` vào cấu hình Java 21 để xử lý lỗi migration; tùy chọn này không giải quyết được vấn đề.

### Phân biệt --add-exports và --add-opens

Hai tùy chọn sau vẫn tồn tại để hỗ trợ chuyển tiếp cho một package cụ thể, nhưng không thay thế việc migrate khỏi internal API:

```bash
# Cho phép truy cập các public type trong package chưa được export.
java --add-exports=java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar

# Cho phép deep reflection vào package được chỉ định tại runtime.
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
```

| Tùy chọn | Mục đích | Không làm được |
|---|---|---|
| `--add-exports` | Export package của module nguồn cho module đích; có thể dùng ở compile time và runtime | Không tự cho phép truy cập private member bằng reflection |
| `--add-opens` | Mở package cho deep reflection tại runtime | Không làm internal type trở thành API công khai ổn định hoặc tự giải quyết lỗi compile-time |

`ALL-UNNAMED` áp dụng cho code chạy trên classpath. Với ứng dụng modular, có thể chỉ định tên module đích. Nếu cần các flag này, hãy giới hạn đúng package và module, ghi nhận thư viện gây ra yêu cầu, nâng cấp hoặc thay thư viện đó, rồi loại bỏ flag khi migration hoàn tất. Tránh mở toàn bộ module hoặc nhiều package nội bộ một cách rộng rãi.

## 3. Tìm phụ thuộc bằng jdeps

`jdeps` là công cụ phân tích dependency của JDK. Tùy chọn `--jdk-internals` (cũng có tên ngắn `-jdkinternals`) tìm tham chiếu bytecode tới JDK internal API:

```bash
# Phân tích một JAR được build cho Java 21.
jdeps --jdk-internals --multi-release 21 app.jar

# Phân tích ứng dụng cùng các dependency trên classpath.
jdeps --jdk-internals --class-path "lib/*" app.jar
```

Kết quả có thể liệt kê class nội bộ được tham chiếu và gợi ý API thay thế. Ví dụ, `sun.misc.BASE64Encoder` có thể được thay bằng `java.util.Base64`.

Với multi-release JAR, `--multi-release 21` yêu cầu `jdeps` phân tích phiên bản class phù hợp với runtime mục tiêu. Nếu ứng dụng có nhiều module hoặc dependency phức tạp, hãy phân tích các artifact thực tế được đóng gói và đưa thư viện cần thiết vào classpath/module path khi chạy công cụ.

### Giới hạn của jdeps

`jdeps` phân tích dependency tĩnh từ bytecode. Nó không thể tìm đầy đủ những phụ thuộc được tạo động, ví dụ:

- `Class.forName("jdk.internal....")` hoặc tên class được ghép từ chuỗi.
- Reflection tìm field/method theo tên.
- Method handle được tạo từ dữ liệu runtime.
- Code sinh ra trong lúc chạy, script engine hoặc bytecode generator.
- Dependency chỉ được nạp trong một plugin hoặc profile triển khai cụ thể.

Vì vậy, kết quả không có cảnh báo không chứng minh ứng dụng không còn dùng internal API. Hãy kết hợp `jdeps` với tìm kiếm source/configuration, kiểm tra dependency bên thứ ba, test trên runtime đích và quan sát lỗi truy cập khi chạy.

`jdeprscan` là công cụ khác để tìm việc sử dụng API đã deprecated. Deprecated API vẫn có thể là API công khai có tài liệu; internal API là vấn đề về tính ổn định và hỗ trợ. Có thể cần cả hai phép kiểm tra trong một đợt nâng cấp, nhưng chúng trả lời hai câu hỏi khác nhau.

## 4. Bảng thay thế cho các trường hợp thường gặp

| Internal API hoặc cách dùng cũ | Nhu cầu thực tế | API được hỗ trợ nên xem xét |
|---|---|---|
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | Mã hóa và giải mã Base64 | `java.util.Base64` |
| `sun.misc.Unsafe` truy cập field/array, CAS, volatile hoặc memory ordering | Truy cập biến với atomic và memory semantics xác định | `VarHandle`; với thao tác đơn giản, `AtomicInteger`, `AtomicLong`, `AtomicReference` và các lớp atomic phù hợp |
| `sun.misc.Unsafe` cấp phát/truy cập native memory | Bộ nhớ ngoài heap hoặc dữ liệu native | Foreign Function & Memory API (`MemorySegment`, `Arena`) trên JDK 22+; `ByteBuffer.allocateDirect` cho trường hợp direct buffer đơn giản |
| `sun.misc.Unsafe.park/unpark` | Park và đánh thức thread | `LockSupport.park()` / `LockSupport.unpark()` |
| `sun.misc.Unsafe.defineClass` | Định nghĩa class động | `MethodHandles.Lookup.defineClass()` hoặc `defineHiddenClass()`; custom `ClassLoader#defineClass` nếu cần loader riêng |
| `sun.misc.Unsafe.ensureClassInitialized` | Chủ động khởi tạo class | `MethodHandles.Lookup.ensureInitialized()` hoặc `Class.forName(name, true, loader)` khi làm việc theo tên class |
| `sun.misc.Cleaner` hoặc cơ chế cleaner nội bộ | Cleanup khi object không còn được dùng | `java.lang.ref.Cleaner` cho cleanup dự phòng; ưu tiên `AutoCloseable` và try-with-resources để giải phóng tài nguyên xác định |
| `sun.nio.ch.*` | Socket, file, channel và selector | `java.nio.channels`, `java.net`, `java.nio.file` |
| `sun.security.*` | Chữ ký số, certificate, key, cipher và provider | `java.security`, `java.security.cert`, `javax.crypto`, JCA/JCE |
| `com.sun.org.apache.xerces.internal.*` | Parse/transform XML | JAXP: `javax.xml.parsers`, `javax.xml.transform`, `org.w3c.dom`, `org.xml.sax` |
| Truy cập private JDK field bằng reflection | Lấy thông tin hoặc thực hiện thao tác trên object JDK | API công khai được tài liệu hóa; `MethodHandles` chỉ khi caller có quyền truy cập hợp lệ |

Không phải mọi trường hợp đều có thay thế một-một. Nếu một thư viện cần một khả năng không có API công khai tương đương, hãy xem lại thiết kế hoặc chọn thư viện được duy trì có hỗ trợ JDK mục tiêu; không tạo một lớp wrapper mới quanh internal API rồi coi vấn đề đã được giải quyết.

## 5. Thay Base64 nội bộ bằng java.util.Base64

`java.util.Base64` là API chuẩn từ Java 8. Nó cung cấp encoder/decoder cho Base64 cơ bản, Base64 URL-safe và MIME:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "Java 21".getBytes(StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);

String restored = new String(decoded, StandardCharsets.UTF_8);
System.out.println(restored); // Java 21
```

Khi làm việc với dữ liệu trong URL hoặc tên file, dùng URL encoder/decoder:

```java
String token = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(input);

byte[] original = Base64.getUrlDecoder().decode(token);
```

Nếu cần định dạng MIME với line separator, dùng `Base64.getMimeEncoder()` và `getMimeDecoder()`. Hãy chọn đúng biến thể theo giao thức; Base64 không phải mã hóa bảo mật và không thay thế encryption.

## 6. Thay thao tác field/atomic của Unsafe bằng VarHandle

`VarHandle` là API chuẩn từ Java 9 để truy cập biến theo các memory access mode như plain, opaque, acquire/release, volatile và atomic update. Nó phù hợp khi code cũ dùng `Unsafe` để đọc/ghi field hoặc thực hiện compare-and-set.

Ví dụ dưới đây tạo `VarHandle` cho field `state` của chính class và dùng acquire/release cùng compare-and-set:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

final class StateCell {
    private int state;

    private static final VarHandle STATE;

    static {
        try {
            STATE = MethodHandles.lookup().findVarHandle(
                    StateCell.class, "state", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    int getAcquire() {
        return (int) STATE.getAcquire(this);
    }

    void setRelease(int value) {
        STATE.setRelease(this, value);
    }

    boolean compareAndSet(int expected, int update) {
        return STATE.compareAndSet(this, expected, update);
    }
}
```

`MethodHandles.lookup()` trong class khai báo field có quyền tìm private field đó. Nếu tạo lookup từ class khác, access check vẫn được áp dụng; `VarHandle` không phải cách vượt qua encapsulation. Không chuyển mọi lời gọi `Unsafe` thành `VarHandle` một cách máy móc: chọn memory access mode dựa trên memory ordering mà thuật toán cần.

Với một counter hoặc reference đơn giản, lớp atomic cấp cao thường dễ đọc và ít sai sót hơn:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    int increment() {
        return count.incrementAndGet();
    }
}
```

Chỉ dùng `VarHandle` khi cần memory mode, CAS hoặc truy cập array/field theo cách mà các lớp atomic thông thường không biểu đạt thuận tiện.

## 7. Thay cấp phát native memory bằng API phù hợp

Nếu code cũ dùng `Unsafe.allocateMemory`, `freeMemory`, `copyMemory` hoặc truy cập raw address, trước tiên xác định mục tiêu:

- Nếu chỉ cần buffer byte trực tiếp cho I/O, `ByteBuffer.allocateDirect()` có thể đáp ứng mà không cần quản lý raw pointer. Vòng đời vùng nhớ direct buffer do JDK quản lý; API này không cung cấp thao tác `free` xác định như `Arena.close()`.
- Nếu cần vùng nhớ native có lifetime xác định, truy cập theo layout, hoặc gọi native function, Foreign Function & Memory API là lựa chọn chuẩn trên JDK 22 trở lên.
- Nếu phải giữ Java 21, FFM ở Java 21 vẫn là preview API; không được coi nó là API Java 21 ổn định. Có thể dùng direct `ByteBuffer` nếu đủ, hoặc duy trì một binding native đã được kiểm thử trong khi lập kế hoạch nâng runtime.

Ví dụ FFM trên JDK 22+ (API đã final từ JDK 22):

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment memory = arena.allocate(4, 4);
    memory.set(ValueLayout.JAVA_INT, 0, 42);

    int value = memory.get(ValueLayout.JAVA_INT, 0);
    System.out.println(value); // 42
}
// Arena đóng và giải phóng vùng native memory.
```

`Arena` xác định lifetime của segment; khi arena đóng, segment gắn với arena không còn hợp lệ. Đây là lợi ích quan trọng so với quản lý địa chỉ thô bằng Unsafe. Với Java 21, FFM là preview ở lần thứ ba; nếu cần dùng nó, phải bật preview đúng cách và chấp nhận phụ thuộc vào API preview của đúng bản JDK 21. Với ứng dụng production cần API ổn định, nên dùng một giải pháp public API phù hợp với Java 21 hoặc nâng runtime lên JDK 22+.

`ByteBuffer.allocateDirect()` không phải thay thế tổng quát cho mọi thao tác raw memory. Nó cung cấp direct buffer cho I/O và native interop theo hợp đồng của `ByteBuffer`, nhưng không cung cấp quyền tùy ý thao tác pointer hoặc layout native như FFM.

## 8. Thay defineClass và truy cập reflection nội bộ

Một số framework cũ dùng `Unsafe.defineClass` để định nghĩa bytecode trong một loader/package. Hãy chọn API theo mục tiêu thật:

```java
import java.lang.invoke.MethodHandles;

// Định nghĩa class trong cùng package/loader với lookup class.
Class<?> generated = MethodHandles.lookup().defineClass(classBytes);
```

`Lookup.defineClass()` yêu cầu class bytes có package phù hợp với lookup class và tuân thủ quyền truy cập của lookup. Nếu cần tạo class ẩn danh theo nghĩa JVM (*hidden class*) cho framework hoặc runtime-generated implementation, xem `Lookup.defineHiddenClass()`.

Nếu mục tiêu là nạp class vào namespace riêng, hãy triển khai `ClassLoader` phù hợp và dùng API `defineClass` được bảo vệ của loader đó. Không cố dùng internal API để chèn class tùy ý vào loader của JDK.

Với reflection, ưu tiên API public của đối tượng. Nếu đang truy cập private member của chính module ứng dụng, có thể thiết kế module descriptor với `opens` có phạm vi tới module framework cần thiết hoặc dùng `MethodHandles.privateLookupIn()` khi module/package đã mở hợp lệ. Không thể dùng `privateLookupIn` để vượt qua strong encapsulation của package JDK không mở.

Nếu ứng dụng cần đọc một thuộc tính JDK không được public API cung cấp, hãy xem xét liệu nghiệp vụ có thực sự cần thuộc tính đó. Phụ thuộc vào private field như offset, cache nội bộ hoặc cấu trúc của implementation sẽ rất dễ vỡ khi nâng JDK.

## 9. Thay internal API trong networking, XML và security

### Networking và file I/O

Không khai báo kiểu `sun.nio.ch.*` trong public method signature hoặc lưu chúng như dependency của ứng dụng. Dùng các abstraction công khai:

- `Socket`, `ServerSocket`, `DatagramSocket` trong `java.net` cho socket blocking truyền thống.
- `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `Selector` trong `java.nio.channels` cho NIO.
- `HttpClient` trong `java.net.http` cho HTTP client.
- `Path`, `Files` và `FileChannel` trong `java.nio.file`/`java.nio.channels` cho file.

Các API này có hợp đồng công khai và được kiểm thử cùng JDK. Nếu cần hành vi đặc thù của implementation như direct buffer address hoặc selector internals, hãy đánh giá lại thiết kế thay vì import implementation class.

### XML

Thay `com.sun.org.apache.xerces.internal.*` bằng JAXP và các API XML công khai. Ví dụ dùng `DocumentBuilderFactory`/`DocumentBuilder` để parse DOM, `SAXParserFactory` cho SAX hoặc `TransformerFactory` để transform. Khi xử lý XML không tin cậy, cấu hình parser để tắt external entity và external DTD theo yêu cầu bảo mật; dùng provider mặc định không có nghĩa mọi cấu hình parse đều an toàn.

### Security và cryptography

Thay `sun.security.*` bằng JCA/JCE: `KeyStore`, `KeyFactory`, `Signature`, `Cipher`, `MessageDigest`, `CertificateFactory`, `X509Certificate` và các API trong `java.security`/`javax.crypto`. Nếu cần thuật toán hoặc provider cụ thể, chọn qua JCA provider mechanism và tên thuật toán được tài liệu hóa; không gọi class triển khai của Sun provider trực tiếp.

## 10. Quy trình migration an toàn

Một quy trình có thể lặp lại cho từng ứng dụng hoặc thư viện:

1. **Chốt runtime mục tiêu.** Xác định ứng dụng cần chạy trên Java 21 hay một JDK mới hơn; điều này quyết định API nào đã final và có thể sử dụng.
2. **Quét bytecode.** Chạy `jdeps --jdk-internals` trên JAR ứng dụng và các dependency được đóng gói.
3. **Quét source và cấu hình.** Tìm `sun.`, `jdk.internal.`, `com.sun.` cần xác minh, `Class.forName`, reflection string, `setAccessible`, method handle và các `--add-exports`/`--add-opens` đang được cấu hình.
4. **Xác định mục đích.** Ghi lại code đang cần memory access, native memory, class definition, Base64, XML, networking hay một thông tin private nào đó.
5. **Chọn API được hỗ trợ.** Dùng Java SE API trước; nếu API chỉ có ở JDK mới hơn, cân nhắc nâng runtime hoặc chọn giải pháp phù hợp với runtime hiện tại.
6. **Nâng cấp dependency.** Nếu framework hoặc thư viện bên thứ ba dùng internal API, ưu tiên phiên bản đã hỗ trợ JDK mục tiêu. Không patch class nội bộ của dependency trong ứng dụng nếu có bản cập nhật được duy trì.
7. **Thay và kiểm thử.** Kiểm thử kết quả, concurrency/memory semantics, hiệu năng, serialization, native interop và tương thích module theo đúng use case.
8. **Gỡ quyền truy cập tạm.** Xóa các `--add-exports`/`--add-opens` không còn cần và chạy lại toàn bộ test trên runtime mục tiêu.
9. **Đưa vào CI.** Chạy quét internal API trên artifact mới trong pipeline để tránh phụ thuộc quay trở lại.

Ví dụ một bước CI tối thiểu:

```bash
# Chạy sau khi build artifact cho Java 21.
jdeps --jdk-internals --multi-release 21 build/libs/application.jar
```

Đặt bước này cùng build/test và xử lý kết quả có internal dependency như một lỗi migration cần được xem xét. Với dependency reflection/dynamic, bổ sung kiểm tra source và integration test; không chỉ dựa vào `jdeps`.

## 11. Những điều không nên dùng làm giải pháp lâu dài

| Cách làm | Vì sao không phù hợp |
|---|---|
| Thêm `--illegal-access=permit` | Obsolete từ JDK 17, không mở lại truy cập rộng |
| Mở toàn bộ package của `java.base` bằng nhiều `--add-opens` | Làm yếu encapsulation, che giấu dependency cần sửa và tăng rủi ro khi nâng JDK |
| Coi `sun.misc.Unsafe` là API ổn định vì vẫn import được | Các memory-access method không được hỗ trợ, terminally deprecated từ JDK 23 và phát cảnh báo từ JDK 24 |
| Copy source hoặc bytecode của internal class vào ứng dụng | Tạo bản sao phụ thuộc implementation, dễ sai khác và có thể phát sinh vấn đề bảo trì/pháp lý |
| Chỉ kiểm tra compile trên JDK 21 | Không phát hiện đầy đủ lỗi do reflection, dynamic loading hoặc dependency chỉ chạy trong production |
| Bỏ qua warning vì ứng dụng hiện vẫn chạy | Warning có thể báo trước việc API sẽ bị hạn chế hoặc loại bỏ trong bản JDK tiếp theo |

### Lưu ý riêng về sun.misc.Unsafe trên JDK mới

`sun.misc.Unsafe` là ngoại lệ trong lịch sử strong encapsulation: lớp này vẫn có thể truy cập trong các JDK hiện hành. Tuy nhiên, các phương thức memory-access của nó là API không được hỗ trợ. JEP 471 terminally deprecated các phương thức đó từ JDK 23; JDK 24 bổ sung cảnh báo runtime khi chúng được gọi theo JEP 498. Không nên hiểu “class vẫn tồn tại” là “có thể tiếp tục dùng an toàn”. Hãy thay memory access bằng `VarHandle` hoặc FFM theo loại bộ nhớ và runtime mục tiêu.

## 12. Checklist hoàn tất migration

- [ ] Đã xác định rõ runtime mục tiêu và các API ổn định có thể dùng trên runtime đó.
- [ ] Đã chạy `jdeps --jdk-internals` trên ứng dụng và dependency liên quan.
- [ ] Đã kiểm tra reflection, class name dạng chuỗi, method handle và code sinh động.
- [ ] Đã xác định mục đích thực tế của từng internal API trước khi chọn replacement.
- [ ] Đã thay bằng Java SE API hoặc API JDK được tài liệu hóa.
- [ ] Với `Unsafe`, đã chọn `VarHandle`, lớp atomic hoặc FFM phù hợp; không giả định FFM final trong Java 21.
- [ ] Đã kiểm tra memory ordering, lifecycle native memory và cleanup sau khi thay thế.
- [ ] Đã nâng cấp framework/dependency dùng internal API.
- [ ] Đã gỡ các `--add-exports` và `--add-opens` không còn cần.
- [ ] Không còn dựa vào `--illegal-access`.
- [ ] Đã chạy test trên đúng runtime, classpath/module path và môi trường production tương đương.
- [ ] Đã đưa kiểm tra internal API vào CI và theo dõi warning trên JDK mới.

## Tài liệu tham khảo

- [Preparing for Migration — Java SE 21](https://docs.oracle.com/en/java/javase/21/migrate/preparing-migration.html): hướng dẫn chạy `jdeps --jdk-internals`, gợi ý replacement và giới hạn của phân tích tĩnh.
- [The jdeps Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): cú pháp `--jdk-internals`, classpath, module path và multi-release JAR.
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation mặc định từ JDK 17 và mục tiêu loại bỏ phụ thuộc internal API.
- [JDK 17 Release Notes](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html): `--illegal-access` obsolete và không còn tác dụng mở truy cập rộng.
- [VarHandle — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html): access modes và thao tác atomic trên field/array.
- [MethodHandles.Lookup — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineClass`, `defineHiddenClass`, `ensureInitialized` và quyền truy cập lookup.
- [Base64 — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.html): encoder/decoder Base64 cơ bản, URL-safe và MIME.
- [JEP 471: Deprecate the Memory-Access Methods in sun.misc.Unsafe for Removal](https://openjdk.org/jeps/471): lý do thay thế Unsafe bằng API được hỗ trợ.
- [JEP 498: Warn upon Use of Memory-Access Methods in sun.misc.Unsafe](https://openjdk.org/jeps/498): cảnh báo runtime từ JDK 24 khi gọi memory-access method của Unsafe.
- [Foreign Function & Memory API — Java SE 21 Guide](https://docs.oracle.com/en/java/javase/21/core/foreign-function-and-memory-api.html): trạng thái preview lần thứ ba của FFM trong Java 21.
- [Foreign Function & Memory API — Java SE 22 Guide](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): FFM final từ JDK 22, `MemorySegment`, `Arena` và native function.
