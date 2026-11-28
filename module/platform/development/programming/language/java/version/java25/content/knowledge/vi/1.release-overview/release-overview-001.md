# Phạm vi Java 25 và những thay đổi còn hữu ích trong phát triển Java hiện đại

**Java 25 (JDK 25)** được phát hành ngày **16/09/2025** và là một bản Java có định hướng hỗ trợ dài hạn (LTS) ở nhiều nhà cung cấp JDK. Điểm quan trọng đối với người phát triển không phải ghi nhớ mọi JEP từng xuất hiện trong Java 25, mà là biết **tính năng nào đã ổn định, dùng vào việc gì, cần kiểm chứng điều gì khi nâng cấp từ JDK cũ**, và tính năng nào lúc Java 25 phát hành vẫn ở trạng thái preview/incubator/experimental.

Bài học thuộc chương **Tổng quan Java 25** và tập trung vào những thay đổi **vẫn có giá trị trong Java hiện đại**: chương trình nguồn gọn, module import, flexible constructor bodies, `ScopedValue`, Key Derivation Function (KDF) API, AOT cache, Java Flight Recorder (JFR) và tối ưu JVM. Đây là cách nhìn để lựa chọn công cụ **đang dùng được**, không phải một danh sách hướng dẫn sử dụng API đã lỗi thời.

> **Phạm vi phiên bản:** Các ví dụ Java bên dưới hướng tới **JDK 25** với những tính năng đã được hoàn thiện (final/permanent). Trong các bản Java mới hơn, hãy tra tài liệu của **JDK đích** vì option và mặc định của JVM có thể thay đổi. Đặc biệt, một API ở trạng thái *preview trong Java 25* không được coi là API ổn định của Java 25 chỉ vì nó tiếp tục được phát triển ở bản sau.

## 1. Java 25 nằm ở đâu trong lộ trình phát triển?

Java có nhịp phát hành tính năng định kỳ. JDK 25 kế thừa nền tảng hiện đại như records, sealed classes, pattern matching đã hoàn thiện ở các bản trước; đồng thời mang một số tính năng đã trải qua nhiều vòng preview thành API/ngôn ngữ **chính thức**, và mở rộng lựa chọn vận hành JVM.

Nên phân biệt ba lớp:

| Lớp | Ví dụ áp dụng | Vì sao có ích |
| --- | --- | --- |
| **Ngôn ngữ** | Compact source files, module import, flexible constructor bodies | Giảm nghi thức trong chương trình nhỏ, nhập API gọn hơn, kiểm tra đối số trước `super(...)` |
| **Thư viện chuẩn** | `ScopedValue`, `javax.crypto.KDF` | Truyền ngữ cảnh theo phạm vi rõ ràng, dẫn xuất khóa theo API chuẩn |
| **Runtime và công cụ** | AOT cache, JFR, compact object headers, generational Shenandoah | Tối ưu startup/warm-up, điều tra CPU/GC/latency, thử các lựa chọn bộ nhớ phù hợp tải |

**LTS không đồng nghĩa với bất biến.** Chính sách cập nhật bảo mật, thời hạn hỗ trợ và gói phân phối phụ thuộc vào nhà cung cấp (Oracle, Eclipse Temurin, Azul, Microsoft, v.v.). Luôn xác minh bản vá JDK 25 hiện đang được hỗ trợ cho hệ điều hành và kiến trúc triển khai; đừng nhầm bản GA `25.0.0` với một build đã nhận các bản vá mới.

### Tình trạng tính năng: cột mốc quan trọng để ra quyết định

JDK 25 có **18 JEP** trong danh sách phát hành. Đối với nội dung nền tảng phục vụ sản phẩm lâu dài, ưu tiên các JEP đã hoàn thiện:

| JEP | Năng lực | Trạng thái trong Java 25 | Ứng dụng thực tế |
| --- | --- | --- | --- |
| 511 | Module Import Declarations | Chính thức | Rút gọn import các API từ module đã xuất |
| 512 | Compact Source Files and Instance Main Methods | Chính thức | Script nhỏ, demo, công cụ CLI, bài học |
| 513 | Flexible Constructor Bodies | Chính thức | Validate và chuẩn bị đối số trước constructor cha |
| 506 | Scoped Values | Chính thức | Truyền dữ liệu bất biến có scope xác định |
| 510 | Key Derivation Function API | Chính thức | HKDF và các KDF được provider hỗ trợ |
| 514 | Ahead-of-Time Command-Line Ergonomics | Tính năng JDK | Quy trình tạo và dùng AOT cache thuận tiện hơn |
| 515 | Ahead-of-Time Method Profiling | Tính năng JVM | Cải thiện warm-up dựa vào profile trong cache |
| 518 | JFR Cooperative Sampling | Tính năng JFR/JVM | Tăng hiệu quả, độ tin cậy của lấy mẫu JFR |
| 520 | JFR Method Timing & Tracing | Tính năng JFR/JDK | Quan sát thời gian/thực thi method có chủ đích |
| 519 | Compact Object Headers | Tính năng JVM chính thức, **opt-in ở JDK 25** | Thử giảm footprint object sau khi đo |
| 521 | Generational Shenandoah | Tính năng GC chính thức, chọn bằng option | Đánh giá collector độ trễ thấp cho workload phù hợp |

Các JEP khác của Java 25 gồm **470 (PEM API preview), 502 (Stable Values preview), 505 (Structured Concurrency, preview lần 5), 507 (primitive patterns/switch preview lần 3), 508 (Vector API incubator lần 10), 509 (JFR CPU-Time Profiling experimental)** và 503 (loại bỏ cổng 32-bit x86). Đây là thông tin **cần nhận biết khi đọc release notes hoặc nâng cấp**, nhưng bài này **không dùng API preview/incubator làm nền tảng code production**, và không hướng dẫn quay lại cổng triển khai đã bị loại bỏ.

> Đặc biệt, **virtual threads** là tính năng chính thức từ Java 21, **records** từ Java 16 và **sealed classes** từ Java 17. Chúng vẫn rất hữu ích khi viết Java 25, nhưng **không phải tính năng mới của Java 25**. Phân biệt đúng mốc giúp đánh giá tác động nâng cấp một cách chính xác.

## 2. Compact source files và instance main methods (JEP 512)

Trước đây, chương trình Java ngắn thường cần khai báo một class và `public static void main(String[] args)`. Trong Java 25, một **compact source file** có thể đặt method `main()` trực tiếp ở cấp file:

```java
// Hello.java — JDK 25
void main() {
    IO.println("Xin chào từ Java 25!");
}
```

Chạy:

```bash
java Hello.java
```

Khi chạy, Java tạo một class ngầm định để chứa các thành viên của file; bản thân chương trình **vẫn là Java**, không phải ngôn ngữ script riêng hay một cú pháp preview cần bật cờ. `java.lang.IO` cung cấp các thao tác console cơ bản như `IO.println(...)`; đây là API trong Java 25, khác với `System.out.println(...)` vẫn được dùng bình thường.

Compact source file **tự import các kiểu public** của những package được module `java.base` export, vì vậy có thể viết:

```java
// Names.java
void main() {
    var names = List.of("An", "Bình", "Chi");
    names.stream()
         .map(String::toUpperCase)
         .forEach(IO::println);
}
```

Những trường hợp nên dùng:

- Công cụ kiểm tra dữ liệu ngắn, demo API Java, ví dụ trong tài liệu và bài tập nhập môn.
- Một file tiện ích cần chạy nhanh mà không phải tạo trước cấu trúc nhiều class.
- Chương trình dùng trực tiếp thư viện chuẩn; nếu cần thư viện ngoài, classpath/module-path vẫn phải được quản lý đúng.

Những trường hợp **không cần thay thế** bằng compact source files:

- Backend Spring Boot nhiều package, có lớp API công khai và cấu trúc module rõ ràng.
- Thư viện cần tên class ổn định, API công khai, test và versioning.
- Ứng dụng đã có build tool, kiểm thử và cấu trúc class hợp lý; giảm vài dòng boilerplate không tự làm kiến trúc tốt hơn.

Compact source file làm **đường vào Java nhẹ hơn**; nó không thay thế mọi hình thức tổ chức mã nguồn thông thường.

## 3. Module import declarations (JEP 511)

Java Platform Module System (JPMS) giới thiệu khái niệm module trong Java 9. Java 25 bổ sung cú pháp **`import module ...;`** cho phép import-on-demand các kiểu từ các package được export bởi một module, thay vì liệt kê nhiều package:

```java
// FruitNames.java
import module java.base;

public class FruitNames {
    public static void main(String[] args) {
        Map<String, Integer> sizes = Map.of(
            "apple", 5,
            "banana", 6
        );
        sizes.entrySet().stream()
             .sorted(Map.Entry.comparingByKey())
             .forEach(IO::println);
    }
}
```

Đây là cú pháp **ngôn ngữ chính thức** ở Java 25; không yêu cầu file nguồn là module JPMS hoặc phải sử dụng `module-info.java` mới được viết `import module java.base;`.

Đừng nhầm:

- `import module java.base;` làm cho **tên kiểu** được truy cập ngắn gọn khi biên dịch.
- `requires some.module;` trong `module-info.java` xác định **phụ thuộc module** ở mức JPMS.
- `--module-path` hoặc classpath chỉ định nơi lấy thư viện lúc biên dịch/chạy.

**Import module không tự thêm một dependency JAR còn thiếu.** Module bên ngoài vẫn phải hiện diện và có quan hệ truy cập hợp lệ.

### Cẩn thận xung đột tên kiểu

Import cả `java.desktop` và `java.base` có thể khiến `List` hoặc `Label` bị trùng tên giữa các package. Khi đó dùng explicit import hoặc tên đầy đủ:

```java
import module java.desktop;
import module java.base;
import java.util.List; // Nêu rõ List nào được ưu tiên.

class Sample {
    List<String> items = List.of("one", "two");
}
```

Trong codebase lớn, explicit imports thường giúp review dependencies dễ hơn. Module import hữu ích khi code cần nhiều API trong một module; không nên sử dụng chỉ để giảm số dòng nếu làm giảm khả năng hiểu mã.

## 4. Flexible constructor bodies (JEP 513)

Java 25 cho phép đặt **một số câu lệnh trước `super(...)` hoặc `this(...)`** để kiểm tra và chuẩn bị dữ liệu. Điều kiện quan trọng là đoạn **prologue** trước lời gọi constructor cha **không được truy cập instance đang được tạo** theo cách bị cấm.

Ví dụ kiểm tra đối số trước khi truyền vào lớp cha:

```java
import java.util.Objects;

class NamedEntity {
    private final String name;

    NamedEntity(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

class Account extends NamedEntity {
    Account(String rawName) {
        String normalized = Objects.requireNonNull(rawName).trim();
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("Tên không được rỗng");
        }
        super(normalized);
    }
}
```

Ý nghĩa: thay vì nhét toàn bộ validation vào biểu thức tham số của `super(...)`, constructor được phép sử dụng các câu lệnh dễ đọc hơn.

Giới hạn cần nhớ:

- Không gọi `this.someMethod()`, không đọc trạng thái instance chưa được tạo xong trong phần prologue.
- Không xem đây là quyền chạy mọi side effect trước khi gọi constructor cha.
- Cú pháp cũng hỗ trợ một số trường hợp **gán field của instance trước `super()`** để tránh lớp cha thấy field chưa gán khi gọi method có thể bị override; vẫn phải tuân theo các quy tắc *early construction context* của Java.
- Constructor của record có quy tắc riêng; không áp dụng máy móc mọi ví dụ class thường cho record.

Đây là một cải tiến **tính an toàn và tính dễ đọc**. Nó không thay thế validation ở service, API boundary hoặc invariant phải được duy trì bởi toàn bộ mô hình đối tượng.

## 5. Scoped Values (JEP 506): ngữ cảnh có phạm vi rõ ràng

`ScopedValue<T>` trong `java.lang` là API **chính thức** của Java 25. Nó cho phép một đoạn chương trình truy cập giá trị mà không cần truyền qua tham số ở mọi tầng method; binding chỉ có hiệu lực trong **dynamic scope** của lệnh gọi.

Ví dụ:

```java
public class RequestContextExample {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    static void process(String requestId) {
        ScopedValue.where(REQUEST_ID, requestId)
                .run(RequestContextExample::handle);
    }

    private static void handle() {
        IO.println("requestId = " + REQUEST_ID.get());
    }

    public static void main(String[] args) {
        process("req-123");
    }
}
```

`REQUEST_ID` chỉ được bind khi lambda bên trong `run(...)` đang thực thi; sau khi đoạn đó kết thúc hoặc ném exception, scope tự được đóng. Các method nằm trong nhánh gọi có quyền truy cập khóa `REQUEST_ID` có thể đọc giá trị, nhưng không thể tùy tiện sửa binding hiện hành như một `ThreadLocal.set(...)`. Có thể bind lại trong scope lồng nhau và khi thoát sẽ phục hồi scope trước.

### Khi nào chọn ScopedValue thay vì ThreadLocal?

| Tình huống | Đánh giá |
| --- | --- |
| Giá trị chỉ đọc theo vòng đời lời gọi, như request/correlation ID đã chuẩn hóa | Phù hợp với `ScopedValue` |
| Giá trị cần truyền qua nhiều lớp nhưng không muốn đặt vào mọi signature | Có thể phù hợp nếu phạm vi được xác định rõ |
| Giá trị thay đổi nhiều lần, phải `set/remove` trong cùng scope | Xem lại thiết kế; `ScopedValue` không thay thế trực tiếp mô hình mutable `ThreadLocal` |
| Task gửi vào executor không cấu trúc, chạy sau khi scope gốc kết thúc | **Không tự động** kế thừa binding; phải thiết kế propagation riêng |
| Nghiệp vụ chạy sau restart hoặc qua message broker | Truyền ID bằng event/message metadata bền; không dùng `ScopedValue` để lưu trạng thái |

Binding được gắn theo thread. Java hỗ trợ **chia sẻ có cấu trúc** cho một số mô hình child task; điều đó **không đồng nghĩa** mọi virtual thread, `ExecutorService` hoặc callback đều tự nhận giá trị. Nếu ứng dụng dùng OpenTelemetry/Micrometer, cần kiểm tra cơ chế context propagation của chính thư viện; đừng gán vai trò “tự động truyền trace toàn hệ thống” cho Scoped Values.

**Dữ liệu bất biến và bảo mật:** dùng giá trị bất biến hoặc đối tượng được quản lý đồng bộ phù hợp; hạn chế đưa token hoặc quyền truy cập chưa kiểm tra vào ngữ cảnh ngầm. Scoped values là phương tiện truyền dữ liệu theo scope, không phải hệ thống xác thực.

## 6. Key Derivation Function API (JEP 510)

Java 25 đưa `javax.crypto.KDF` vào API chuẩn (sau giai đoạn preview ở bản trước), cùng một implementation của **HKDF** theo chuẩn được hỗ trợ. KDF nhận **keying material** cùng tham số như salt/context để sinh khóa phục vụ mục đích cụ thể.

Ví dụ hàm tạo khóa AES 256-bit từ material đã có:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.spec.AlgorithmParameterSpec;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

public class SessionKeyDerivation {
    static SecretKey deriveAesKey(byte[] sharedSecret, byte[] salt)
            throws GeneralSecurityException {

        byte[] context = "shop-session-v1"
                .getBytes(StandardCharsets.UTF_8);

        AlgorithmParameterSpec spec = HKDFParameterSpec.ofExtract()
                .addIKM(sharedSecret)
                .addSalt(salt)
                .thenExpand(context, 32); // 32 bytes = 256 bits

        KDF hkdf = KDF.getInstance("HKDF-SHA256");
        return hkdf.deriveKey("AES", spec);
    }
}
```

Giải thích:

- `sharedSecret` là input keying material; nguồn cấp phải bảo đảm bí mật và đủ entropy cho mô hình bảo mật.
- `salt` và `context/info` giúp phân tách ngữ cảnh dẫn xuất theo thiết kế giao thức. Việc lựa chọn/trao đổi giá trị salt phải tuân theo protocol và threat model.
- `deriveKey("AES", ...)` trả về `SecretKey`. Điều đó **không tự mã hóa dữ liệu**, không giải quyết lưu trữ khóa hoặc trao đổi khóa.
- API hỗ trợ nhiều security providers; khi thuật toán/provider không khả dụng, ứng dụng phải xử lý lỗi rõ ràng.

**Không dùng HKDF như phép hash mật khẩu thay cho thuật toán password hashing có chi phí tính toán/memory thích hợp**. HKDF thích hợp dẫn xuất khóa từ key material đã đủ chất lượng; xử lý mật khẩu người dùng là bài toán khác. Không hardcode secret hoặc đưa bytes khóa vào log/test artifact. Các quyết định về thuật toán, output length, salt, key rotation và compliance phải được review bảo mật.

Đây là ví dụ về một **API chuẩn còn hữu ích** khi di chuyển khỏi cơ chế KDF tùy biến khó kiểm toán.

## 7. AOT cache: tối ưu startup và warm-up bằng dữ liệu huấn luyện

Java 25 tiếp tục công việc AOT của các bản trước, đặc biệt **JEP 514 (Ahead-of-Time Command-Line Ergonomics)** và **JEP 515 (Ahead-of-Time Method Profiling)**. Ý tưởng là chạy ứng dụng với workload đại diện để JVM thu thập thông tin phục vụ khởi động lần sau, lưu vào **AOT cache** phù hợp với ứng dụng và môi trường.

```mermaid
flowchart LR
    A["Build artifact + JDK 25"] --> B["Training run: workload đại diện"]
    B --> C["Tạo AOT cache"]
    C --> D["Deploy app + cache tương thích"]
    D --> E["Đo startup/warm-up và SLO"]
```

Một quy trình ngắn với Java 25:

```bash
# 1. Training: chạy workload đại diện, dừng ứng dụng đúng cách.
# Khi ứng dụng kết thúc, JVM có thể khởi chạy bước tạo cache.
java -XX:AOTCacheOutput=shop.aot -jar shop.jar

# 2. Chạy bản tương thích với cache vừa tạo.
java -XX:AOTCache=shop.aot -jar shop.jar
```

Ví dụ chỉ là **khung lệnh**: `shop.jar` cần tồn tại, quá trình training phải thật sự kích hoạt những đường code quan trọng rồi **kết thúc bình thường**. Với ứng dụng server chạy liên tục, phải có cách dừng có kiểm soát sau khi warm-up; không chờ vô hạn hoặc đo cache trước khi nó được tạo.

Các điều kiện quan trọng:

- Cache gắn với **ứng dụng/classpath**, **JDK release**, **OS và kiến trúc CPU**; khi thay đổi một trong các yếu tố đó, phải tạo lại.
- Không giả định cache của Java 25 có thể tái sử dụng ở Java 26/27 hoặc một bản triển khai có bộ JAR khác.
- Cache là **tối ưu hóa**, không phải yêu cầu chức năng. Khi cache không tương thích, ứng dụng có thể chạy không dùng cache trong chế độ mặc định thích hợp.
- Đo **startup time**, **time-to-first-request**, **warm-up throughput**, **p95 latency** và chi phí CPU/bộ nhớ cùng workload; không coi cache luôn giúp mọi hệ thống nhanh hơn.
- Những kỹ thuật có thay đổi bytecode/class loading hoặc JVM option đặc biệt cần kiểm tra tương thích với AOT cache.

Trong môi trường production, dùng cache sinh ra từ **build và runtime image được quản lý**, kiểm tra artifact integrity và khả năng rollback. Tuyệt đối không huấn luyện bằng request chứa secret rồi mặc định cache vô hại về dữ liệu; cần rà soát những gì môi trường build/training ghi lại.

## 8. JFR: quan sát thay vì suy đoán về hiệu năng

**Java Flight Recorder (JFR)** là công cụ quan sát JVM còn được sử dụng rộng rãi. Java 25 có các cải tiến như **JEP 518 (JFR Cooperative Sampling)** và **JEP 520 (JFR Method Timing & Tracing)**, giúp tăng khả năng lấy mẫu và điều tra method khi cần thiết.

### Tạo một recording phục vụ so sánh

Giả sử ứng dụng Java 25 đang chạy và bạn biết PID:

```bash
# Thay <pid> bằng PID của JVM, chạy trong môi trường được phép.
jcmd <pid> JFR.start name=upgrade-check settings=profile \
    duration=60s filename=upgrade-check.jfr

# Sau khi recording hoàn tất:
jfr summary upgrade-check.jfr
jfr print --events jdk.CPULoad,jdk.GarbageCollection upgrade-check.jfr
```

Trong hệ thống thật, lệnh và quyền truy cập có thể khác nhau giữa hệ điều hành/container. `settings=profile` thu thập thông tin nhiều hơn default; cần kiểm soát thời lượng, kích thước file, quyền truy cập và overhead. Không dùng path/recording của môi trường production làm bài tập nếu chưa được cho phép.

### Nên quan sát những gì?

| Câu hỏi | Dữ liệu JFR hoặc phép đo liên quan | Kết luận cần thận trọng |
| --- | --- | --- |
| Vì sao startup chậm? | Class loading, compilation, allocation, CPU profile | AOT có giúp trên workload thật hay không |
| Vì sao p99 latency tăng? | GC pauses, blocked/waiting threads, allocation hotspots | Độ trễ toàn request có thể bao gồm I/O bên ngoài JVM |
| Một method mất nhiều thời gian? | Method timing/tracing với cấu hình mục tiêu | Wall-clock duration không giống CPU time |
| Nâng cấp làm CPU tăng? | CPU sampling, CPU load, native/system metrics bổ sung | Phải giữ cùng concurrency và dữ liệu |
| Bộ nhớ tăng? | Allocation, GC, live set, heap/GC logs | Không lấy riêng peak heap làm bằng chứng memory leak |

**JFR Method Timing & Tracing** cho phép định hướng theo dõi các method cần quan tâm; nên bật có chọn lọc, vì tracing chi tiết mọi method có thể thêm overhead rất lớn. **JFR CPU-Time Profiling** của JEP 509 trong Java 25 là *experimental*, vì vậy nếu chính sách chỉ dùng thành phần ổn định thì không dựa vào nó làm công cụ quan sát bắt buộc. Các sự kiện JFR tiêu chuẩn về CPU/GC/threads và cơ chế sampling đã ổn định vẫn đủ để bắt đầu điều tra.

JFR và metrics ứng dụng bổ trợ nhau. JFR giúp thấy chuyện **bên trong JVM**; log/trace/Micrometer hoặc APM giúp thấy **request nghiệp vụ**, dependency, network và kết quả. Không kết luận ranh giới dịch vụ có lỗi chỉ từ một stack trace JVM.

## 9. Tối ưu object footprint và garbage collector

Java 25 đưa **Compact Object Headers (JEP 519)** thành tùy chọn sản phẩm chính thức, nhưng **mặc định vẫn tắt trong JDK 25**. Nó có thể giảm kích thước header của object, tăng mật độ dữ liệu và giảm áp lực heap, đặc biệt ở ứng dụng tạo nhiều object nhỏ.

Ví dụ **chỉ để benchmark** trên HotSpot/JDK 25 hỗ trợ:

```bash
java -XX:+UseCompactObjectHeaders -jar shop.jar
```

Lợi ích thực tế phụ thuộc kích thước object, heap, mức cấp phát và ứng dụng. Hãy so **heap footprint, allocation, GC pause, throughput và CPU** khi bật/tắt dưới cùng tải. Khi dùng agent, Unsafe hoặc thư viện lệ thuộc layout object, kiểm thử tương thích cẩn thận.

Java 25 cũng hoàn thiện **Generational Shenandoah GC (JEP 521)**. Đây là lựa chọn collector cho mục tiêu giảm pause phù hợp, không phải bảo đảm “nhanh nhất”:

```bash
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -jar shop.jar
```

Những điều cần tránh:

- Không đổi GC cho mọi service chỉ vì JDK mới có collector khác; benchmark **throughput**, **CPU**, **heap** và **tail latency**.
- Không quên hỗ trợ của bản phân phối JDK, hệ điều hành/CPU và cấu hình container.
- Không giữ nguyên những JVM flags đã lỗi thời trong script startup. Xem log cảnh báo và release notes của **đúng JDK đang chạy**.
- Không giả định mặc định của Java 25 sẽ là mặc định của các JDK mới hơn; các chính sách runtime tiếp tục phát triển.

## 10. Preview, incubator và experimental: biết để tránh phụ thuộc sai

Java cho phép thử ý tưởng mới qua các giai đoạn khác nhau. Khi chỉ chọn kiến thức **còn ổn định để áp dụng thực tế**, hãy đánh dấu riêng:

| Nhóm trong JDK 25 | Ví dụ | Cách tiếp cận hiện đại |
| --- | --- | --- |
| **Final/permanent** | JEP 511, 512, 513, 506, 510 | Có thể xem xét đưa vào code Java 25 khi phù hợp |
| **Tính năng JVM/JDK đã phát hành** | AOT, JFR 518/520, object headers, Shenandoah | Đánh giá theo workload và option thực tế |
| **Preview** | JEP 470, 502, 505, 507 | Có thể nghiên cứu hướng phát triển nhưng không biến thành contract ổn định Java 25 |
| **Incubator** | JEP 508 Vector API | Không mặc định hiện diện trong `java.base` như API chính thức |
| **Experimental** | JEP 509 JFR CPU-Time Profiling | Chỉ dùng thí nghiệm có kiểm soát nếu môi trường cho phép |
| **Đã bị loại bỏ** | Cổng x86 32-bit theo JEP 503 | Không thiết kế hệ thống mới dựa trên nền tảng đã bị xóa |

Một số API có thể **đổi trạng thái hoặc cách dùng ở JDK 26/27 và các bản sau**. Nếu phải dùng chúng, tra JEP/tài liệu của bản JDK mới tại thời điểm triển khai; không copy mã preview viết cho `--release 25` rồi kỳ vọng biên dịch tương thích vô hạn.

Chú ý thêm: **preview language features** yêu cầu `--enable-preview` ở bước biên dịch/chạy phù hợp; incubator modules có cơ chế opt-in riêng. Vì bài này ưu tiên kiến thức đang ổn định, **các ví dụ thực hành cốt lõi không cần `--enable-preview`**.

## 11. Chọn tính năng theo nhu cầu, không theo độ mới

| Nhu cầu | Chọn thứ gì trước? | Khi nào nên bỏ qua? |
| --- | --- | --- |
| Viết bài thử/CLI vài chục dòng | Compact source file | App nhiều module cần lớp/API rõ ràng |
| Import nhiều kiểu thuộc cùng JPMS module | `import module ...;` | Dễ xung đột tên hoặc cần explicit dependency review |
| Validate constructor trước `super(...)` | Flexible constructor bodies | Invariant nên đặt ở service/factory, không thuộc constructor |
| Context chỉ đọc trong một call chain | `ScopedValue` | Task chạy ngoài scope, retry sau restart |
| Dẫn xuất key từ key material | `KDF`/HKDF với security review | Hash password người dùng hoặc key management chưa được thiết kế |
| Startup/warm-up lâu | AOT cache + benchmark | Build/runtime không ổn định, workload training không đại diện |
| Không rõ CPU/GC/latency bottleneck | JFR + metrics/trace | Bật toàn bộ method tracing không giới hạn |
| Heap có nhiều object nhỏ | Thử compact object headers | Không có bằng chứng memory pressure |
| Nhạy với GC pause | So generational Shenandoah và collector đang dùng | Chưa có SLO và workload đo được |

**Lợi ích của nâng cấp** không phải dùng hết mọi JEP. Một tổ chức có thể chọn JDK 25 chỉ vì hỗ trợ runtime mới, hiệu năng tốt hơn ở workload đã đo và bản vá bảo mật; sau đó dùng dần các API ngôn ngữ/thư viện phù hợp.

## 12. Quy trình nâng cấp JDK có kiểm chứng

Nâng cấp Java ảnh hưởng nhiều lớp: source, bytecode, thư viện, reflection, TLS, GC, JVM options, container và công cụ quan sát. Hãy thực hiện trên nhánh thử:

### Bước 1 — Kiểm kê và đóng băng baseline

Ghi lại bản JDK hiện tại, JDK vendor/build, hệ điều hành, kiến trúc, dependency versions, Gradle/Maven plugins, flags, container base image, test results và SLO của ứng dụng.

```bash
java -version
javac -version
java --list-modules
java -XshowSettings:properties -version
```

Lưu **bản build cụ thể**, không chỉ ghi “Java 25”; những khác biệt giữa GA và security update có thể quan trọng với bảo mật và tính tương thích.

### Bước 2 — Nâng toolchain và kiểm tra code

Nếu muốn compile đích Java 25, dùng toolchain JDK 25 và `--release 25` hoặc cấu hình build tool tương ứng. Ví dụ Maven:

```xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
```

**Runtime JDK 25 và target bytecode Java 25 không bắt buộc giống nhau.** Nếu thư viện của bạn vẫn phải chạy trên Java 21, hãy biên dịch bằng `--release 21` với toolchain phù hợp và chỉ sử dụng API có trong Java 21. Các API mới như `ScopedValue` và `KDF` của Java 25 không thể đưa vào thư viện Java 21 mà vẫn giữ được cùng mức tương thích.

Kiểm tra các thư viện/framework hiện tại có hỗ trợ Java 25 không; đặc biệt bytecode enhancement, reflection, annotation processors, JNI/native libraries, test runners và monitoring agents. Dùng `jdeps` hoặc báo cáo của build tool để tìm phụ thuộc vào JDK internals, không dựa vào việc chương trình “vẫn chạy” ở một máy.

### Bước 3 — Chạy kiểm thử đúng ngữ nghĩa

- Unit tests, integration tests, contract tests và kiểm thử data serialization/deserialization.
- Kiểm thử TLS/chứng chỉ, provider crypto, timezone/locale và đường xử lý lỗi nếu liên quan.
- Kiểm thử startup, shutdown, scheduled jobs, virtual threads/thread pools và context propagation.
- Kiểm thử **không dùng preview flags** nếu sản phẩm định dùng duy nhất API chính thức.
- Kiểm thử cùng image/container/architecture như production, không chỉ chạy trên laptop.

### Bước 4 — So sánh bằng số liệu

Đo bằng cùng workload:

| Metric | Baseline JDK cũ | JDK 25 candidate | Kết luận |
| --- | --- | --- | --- |
| Startup đến health-ready | Chưa đo | Chưa đo | Chưa đánh giá |
| Time-to-first-useful-request | Chưa đo | Chưa đo | Chưa đánh giá |
| Throughput ở mức tải mục tiêu | Chưa đo | Chưa đo | Chưa đánh giá |
| p50/p95/p99 latency | Chưa đo | Chưa đo | Chưa đánh giá |
| CPU, allocation, heap, GC pauses | Chưa đo | Chưa đo | Chưa đánh giá |
| TLS/security compatibility | Chưa kiểm tra | Chưa kiểm tra | Chưa đánh giá |
| Error rate, timeout, recovery | Chưa đo | Chưa đo | Chưa đánh giá |
| JFR/observability health | Chưa kiểm tra | Chưa kiểm tra | Chưa đánh giá |

Không điền số giả định. Một cải thiện startup do AOT không chứng minh throughput tăng; một GC có p99 thấp hơn có thể đổi lại CPU cao hơn. Đọc cả hệ thống và quyết định theo SLO.

### Bước 5 — Phát hành có đường quay lui

Tạo image và AOT cache (nếu dùng) theo **build hiện tại**, kiểm tra rollout/canary, metric cảnh báo và khả năng rollback. Khi quay lại phiên bản JDK khác, **không dùng lại AOT cache không tương thích**. Giữ release notes, test evidence và thay đổi cấu hình cùng commit triển khai.

## 13. Ba bài thực hành có thể làm ngay

### Bài A — Chạy source file gọn và mở rộng thành class

1. Tạo `Hello.java` có `void main()` và `IO.println()`.
2. Chạy `java Hello.java` bằng JDK 25; không bật preview.
3. Dùng `List` và `Stream` trong compact source file để thấy auto-import `java.base`.
4. Chuyển thành `public class Hello` và dùng `import module java.base;`; so sánh ngữ nghĩa, test và khả năng tổ chức code.

**Cần giải thích:** khác biệt giữa giảm nghi thức khai báo và quản lý package/module ở project thực tế.

### Bài B — Truyền context có scope và dẫn xuất khóa

1. Viết `ScopedValue<String>` chứa request ID, bind bằng `where(...).run(...)`.
2. Đọc ID trong method được gọi nhiều tầng; sau scope, thử `isBound()` để xác nhận binding không còn.
3. Thử rebinding ở scope lồng nhau và xác minh khôi phục giá trị bên ngoài.
4. Viết hàm HKDF như mục 6 với keying material/salt **dữ liệu giả lập, không nhạy cảm**; xác minh output dài 32 byte và kết quả lặp lại theo cùng input (khi provider có cùng thuật toán).
5. Ghi bằng lời vì sao `ScopedValue` không tự truyền qua queue/restart và vì sao HKDF không phải password hash.

**Cần giải thích:** phạm vi hiệu lực của dữ liệu và biên an toàn của API bảo mật.

### Bài C — So JDK 25 có/không có AOT và đo JFR

1. Chọn ứng dụng có một đường khởi động ổn định, có workload training tái lập.
2. Đo startup/warm-up **không AOT** dưới cùng JDK 25 và cấu hình JVM.
3. Tạo cache bằng `-XX:AOTCacheOutput`, thực hiện workload đại diện, dừng có kiểm soát.
4. Chạy cùng build với `-XX:AOTCache`, đo lại startup/warm-up; xác nhận trong log JVM rằng cache thực sự được dùng.
5. Tạo JFR recording ngắn bằng `jcmd`, dùng `jfr summary` hoặc công cụ JFR để xem class loading/GC/CPU.
6. Ghi so sánh theo số lượt chạy, không lấy một phép đo đơn lẻ. Nếu AOT không cải thiện, nêu giả thuyết về training, classpath hoặc workload.

**Cần giải thích:** AOT cache không phải file bytecode dùng chung giữa mọi JDK; JFR cung cấp dữ liệu để kiểm chứng, không thay thế benchmark công bằng.

## 14. Những hiểu nhầm nên tránh

**“Java 25 là bản LTS nên mọi JEP của Java 25 đều ổn định.”** Sai. Release có đồng thời tính năng final, preview, incubator và experimental. Chọn theo trạng thái của **chính JEP/API**.

**“Compact source files thay thế class và build tool.”** Sai. Chúng hữu ích với chương trình nhỏ; ứng dụng lớn vẫn cần kiến trúc module, dependency, test và packaging phù hợp.

**“import module tự thêm JAR hoặc khai báo requires.”** Sai. Cú pháp import không thay thế module path, classpath hay graph dependencies.

**“ScopedValue là ThreadLocal mới nên bất kỳ thread async nào cũng thấy giá trị.”** Sai. Binding có scope và cơ chế kế thừa có giới hạn; task không cấu trúc, process khác hoặc restart không tự nhận context.

**“KDF chỉ cần gọi một lần là có hệ thống mã hóa an toàn.”** Sai. Dẫn xuất khóa chỉ là một bước trong thiết kế mật mã gồm xác thực nguồn material, giao thức, bảo quản khóa, algorithm choice và rotation.

**“AOT cache luôn tăng hiệu năng.”** Sai. Lợi ích phải được đo và cache phải tương thích với build/JDK/platform.

**“JFR Method Tracing càng nhiều càng tốt.”** Sai. Chỉ bật khi có câu hỏi cụ thể và giới hạn overhead, thời gian và dữ liệu ghi nhận.

**“JDK 25 dùng compact object headers mặc định.”** Không đúng với **JDK 25**: tính năng là product option nhưng cần bật chủ động; ở các bản JDK mới hơn mặc định có thể thay đổi.

## 15. Tài liệu tham khảo theo phiên bản

Các nguồn nên tra trực tiếp khi viết code hoặc quyết định nâng cấp:

- [JDK 25 Release Notes — Oracle](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): danh sách JEP và thay đổi tương thích, loại bỏ/deprecation.
- [Java 25 Language Changes](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): tính năng ngôn ngữ chính thức/preview.
- [Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): chương trình nguồn gọn, `IO` và auto-import.
- [Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): import-on-demand và xử lý ambiguous types.
- [Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): quy tắc prologue/early construction.
- [ScopedValue API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): scope, binding và chia sẻ có cấu trúc.
- [KDF API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html): `KDF`, `deriveKey` và provider handling.
- [Java 25 Launcher Options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): AOT cache và JVM flags.
- [jcmd — Java 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): thao tác tạo JFR recording.
- [Java 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): rủi ro và khác biệt khi nâng cấp.

**Kết luận:** Java 25 đáng học vì kết hợp những cải tiến **đã ổn định** cho lập trình hằng ngày (compact source files, module imports, flexible constructors, ScopedValue, KDF) với các công cụ **đo được tác động vận hành** (AOT cache, JFR, JVM memory/GC options). Áp dụng tốt Java hiện đại không có nghĩa chạy theo mọi preview; đó là chọn tính năng đã đủ trưởng thành, kiểm thử tương thích và đo kết quả trên workload thật trước khi triển khai.
