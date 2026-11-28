# Chọn nội dung áp dụng theo ứng dụng, thư viện, dịch vụ và công cụ dòng lệnh

> **Chương:** Tổng quan Java 25
>
> **Mục tiêu:** Chọn đúng những khả năng của Java 25 còn có giá trị khi phát triển Java hiện đại, thay vì cố dùng tất cả tính năng mới cho mọi loại dự án. Phân biệt tính năng đã chính thức, preview/incubator/experimental, khả năng tương thích Java cũ và lợi ích vận hành đo được.

## 1. Vì sao “dùng Java 25” không đồng nghĩa “dùng mọi JEP”?

Java 25 được phát hành vào **16/09/2025** và là một bản phát hành có chính sách hỗ trợ dài hạn từ các nhà cung cấp JDK tương ứng. Tại thời điểm viết bài (tháng 11/2026), Java 25 không phải bản Java mới nhất; việc chọn JDK phải dựa vào chính sách hỗ trợ, hệ sinh thái, yêu cầu bảo mật và mức độ tương thích của **nhà cung cấp** đang dùng, chứ không suy diễn rằng mọi build đều có cùng lịch bảo trì.

Một nhóm có thể nâng **runtime của dịch vụ** lên Java 25 nhưng vẫn phải xuất bản **thư viện** chạy trên Java 21; một công cụ quản trị chạy nội bộ có thể tận dụng **compact source file**, trong khi ứng dụng lớn cần giữ class/module rõ ràng; một hệ thống latency-sensitive có thể thử **Compact Object Headers** hoặc **AOT cache**, nhưng phải đo bằng workload đại diện trước khi bật.

Vì vậy, câu hỏi quan trọng không phải “Java 25 có những tính năng nào?”, mà là:

1. **Chúng ta xây gì?** Ứng dụng độc lập, thư viện phát hành, dịch vụ dài hạn hay công cụ dòng lệnh?
2. **Ai quyết định runtime?** Nhóm mình kiểm soát toàn bộ JDK hay người dùng thư viện chọn Java của họ?
3. **Tính năng ở trạng thái nào trong JDK 25?** Final, preview, incubator hay experimental?
4. **Có lợi ích rõ ràng không?** Ít boilerplate, API bảo mật chuẩn, context propagation an toàn, startup nhanh hoặc profiling tốt hơn?
5. **Chi phí là gì?** JDK tối thiểu, yêu cầu JVM flag, kiểm thử tương thích, chi phí vận hành hay rủi ro API thay đổi?

### Kết quả sau bài học

Bạn sẽ biết xây ma trận lựa chọn tính năng Java 25 cho bốn kiểu sản phẩm; sử dụng đúng một số API final (module import, compact source, flexible constructors, ScopedValue, KDF); thiết kế quy trình đánh giá AOT/JFR; lập checklist nâng cấp JDK; và tránh đưa API preview hoặc công nghệ cũ không còn phù hợp vào nền tảng mặc định.

## 2. Bộ lọc đầu tiên: trạng thái và phạm vi của tính năng

Java 25 có nhiều thay đổi trong ngôn ngữ, thư viện và JVM. Bảng sau **chỉ tập trung các lựa chọn có ý nghĩa hiện nay**; các mục preview được ghi để tránh sử dụng nhầm, không phải để khuyến khích dùng đại trà.

| Khả năng | JEP | Trạng thái **trong Java 25** | Lý do nên cân nhắc |
| --- | --- | --- | --- |
| Scoped Values | **506** | Final | Mang dữ liệu ngữ cảnh chỉ đọc theo dynamic scope, phù hợp nhiều request/task. |
| Key Derivation Function API | **510** | Final | Dùng `javax.crypto.KDF` và HKDF chuẩn thay vì tự cài thuật toán dẫn xuất khóa. |
| Module Import Declarations | **511** | Final | Rút gọn import cho source dùng nhiều package do một module xuất ra. |
| Compact Source Files và instance `main` | **512** | Final | Viết chương trình/tiện ích một file mà không phải dựng class boilerplate. |
| Flexible Constructor Bodies | **513** | Final | Kiểm tra dữ liệu và chuẩn bị đối số trước lời gọi `super(...)`/`this(...)` hợp lệ. |
| AOT Command-Line Ergonomics | **514** | Tính năng JDK | Đơn giản hóa tạo và sử dụng AOT cache. |
| AOT Method Profiling | **515** | Tính năng JDK | Cải thiện warmup từ profile thu thập trong training run AOT. |
| JFR Cooperative Sampling | **518** | Tính năng JDK | Cải thiện cách JFR thu thập stack sampling. |
| Compact Object Headers | **519** | Tính năng JDK, **opt-in ở JDK 25** | Có thể giảm heap footprint khi điều kiện phù hợp. |
| JFR Method Timing & Tracing | **520** | Tính năng JDK | Hỗ trợ phân tích thời gian/phương thức bằng JFR instrumentation. |
| Generational Shenandoah | **521** | Tính năng JDK, **chủ động chọn GC/mode** | Thử nghiệm cấu hình GC phù hợp mục tiêu pause/throughput của dịch vụ. |

Trong **Java 25**, một số khả năng vẫn ở trạng thái không final: PEM Encodings (JEP 470, preview), Stable Values (502, preview), Structured Concurrency (505, preview lần thứ 5), primitive patterns trong `instanceof`/`switch` (507, preview lần thứ 3), Vector API (508, incubator lần thứ 10), JFR CPU-Time Profiling (509, experimental). Không đưa những API này vào **public contract ổn định** của thư viện hoặc mặc định triển khai sản xuất mà chưa có quyết định rủi ro riêng. Trạng thái ở các bản JDK **sau 25** cần kiểm tra lại theo chính bản đó; không coi trạng thái preview của Java 25 là kết luận vĩnh viễn.

### Quy tắc “final trước, preview có kiểm soát”

- **Final Java SE language/API:** có thể cân nhắc cho mã mới nếu chấp nhận yêu cầu runtime/toolchain Java 25. Không đồng nghĩa mọi Java cũ đều chạy được.
- **Tính năng JVM/tooling:** lợi ích phụ thuộc workload, hệ điều hành, architecture, build và flags; phải benchmark, không áp dụng vì mặc định “mới hơn là nhanh hơn”.
- **Preview:** có thể cần `--enable-preview` ở compile và runtime, gắn vào đúng release; API/cú pháp chưa có cam kết ổn định như final.
- **Incubator/experimental:** còn có rủi ro chuyển package, đổi API hoặc bị loại bỏ; phù hợp nghiên cứu có thời hạn, không phải nền tảng cho tất cả sản phẩm.

Đặc biệt, Java 25 đã loại bỏ cổng **32-bit x86** (JEP 503). Đây là ràng buộc kiểm tra môi trường **khi nâng cấp**, không phải tính năng ứng dụng để “tận dụng”. Không hướng dẫn tiếp tục phụ thuộc vào port đã bị loại bỏ.

## 3. Ma trận quyết định nhanh theo loại dự án

| Nhóm khả năng | **Ứng dụng độc lập** | **Thư viện dùng chung** | **Dịch vụ/API dài hạn** | **Công cụ CLI/script** |
| --- | --- | --- | --- | --- |
| Compact source / instance `main` | Có ích cho tiện ích bên cạnh app | Không làm kiểu API xuất bản | Không dùng thay cấu trúc ứng dụng lớn | **Rất phù hợp** cho một file nhỏ |
| Module import | Tốt khi mã dùng nhiều JDK packages | Dùng có chọn lọc; ưu tiên import rõ ràng trong API công khai | Tiện cho code thao tác nhiều API | Tốt, giảm boilerplate |
| Flexible constructor bodies | Dùng cho class kế thừa có invariant | Hữu ích khi thiết kế lớp public | Hữu ích cho domain/entity adapter cần validation | Ít khi cần |
| ScopedValue | Khi kiểm soát runtime Java 25 | Tránh bắt buộc nếu phải hỗ trợ Java cũ | **Đáng cân nhắc** cho request context chỉ đọc | Phù hợp nếu có nhiều lời gọi lồng nhau |
| KDF / HKDF API | Khi ứng dụng thật sự cần dẫn xuất khóa | Chỉ trong thư viện bảo mật với yêu cầu min JDK 25 | **Phù hợp** cho key hierarchy/protocol có thiết kế mật mã đúng | Chỉ khi CLI xử lý key; không tự cài HKDF |
| AOT cache, method profiling | Khi startup/warmup quan trọng | **Không đóng gói cache** như API thư viện | Đáng benchmark cho serverless/scale-to-zero hoặc deploy thường xuyên | Hữu ích cho CLI khởi động nhiều lần |
| Compact Object Headers / GC | Benchmark theo heap | Không quyết định thay người dùng thư viện | Thử trên staging với load, GC/JFR và rollback | Thường không ưu tiên |
| JFR sampling/method timing | Có ích khi profile | Dùng để profile benchmark thư viện | **Rất phù hợp** cho chẩn đoán hiệu năng sản xuất có kiểm soát | Chọn lọc khi CLI chạy lâu |

**Đọc ma trận theo chiều dọc:** thư viện chủ yếu tối ưu **khả năng tương thích người dùng**; dịch vụ ưu tiên **tính ổn định, context, startup, heap và quan sát**; CLI ưu tiên **khởi động nhanh, triển khai đơn giản**; ứng dụng độc lập linh hoạt hơn vì thường có quyền kiểm soát JDK.

## 4. Ứng dụng độc lập: áp dụng API final có chủ đích

Giả sử một ứng dụng desktop/nội bộ được đóng gói và phát hành cùng Java 25. Nhóm kiểm soát cả JDK lẫn quá trình cài đặt, nên có thể dùng các API final để đơn giản hóa mã, nhưng không nhất thiết phải thay toàn bộ code đang chạy ổn định.

### 4.1. Module import dành cho đoạn mã dùng nhiều package

Từ Java 25, `import module java.base;` nhập theo nhu cầu các public top-level types từ các package được `java.base` xuất ra. Ví dụ:

~~~java
// File: DateReport.java
import module java.base;

public class DateReport {

    public static void main(String[] args) {
        var days = List.of(LocalDate.now(), LocalDate.now().plusDays(1));
        days.stream()
                .map(LocalDate::toString)
                .forEach(System.out::println);
    }
}
~~~

`List` thuộc `java.util` và `LocalDate` thuộc `java.time`, đều do `java.base` export. Import module không tự thay thế hoàn toàn `module-info.java`: với một **named module**, bạn vẫn cần quy định các phụ thuộc `requires` và API `exports` phù hợp.

**Khi nào không nên dùng?** Code dùng nhiều module có thể gặp tên trùng. Ví dụ `java.awt.List` và `java.util.List` nếu cùng import `java.desktop` và `java.base`. Trong mã public hoặc thư viện phức tạp, một `import java.util.List;` rõ ràng đôi khi dễ review hơn. JEP 511 là công cụ rút ngắn import, không phải cơ chế mới để phá encapsulation.

### 4.2. Flexible constructor bodies giúp xác thực trước super

Ở Java 25 (JEP 513 final), bạn có thể thực thi các câu lệnh không đụng vào instance đang xây dựng **trước** `super(...)` hoặc `this(...)`:

~~~java
// File: CheckedPort.java
class Port {
    Port(int number) {
        System.out.println("Port " + number);
    }
}

final class CheckedPort extends Port {
    CheckedPort(int number) {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("Invalid port");
        }
        super(number);
    }
}
~~~

Tính năng này có ích khi cần giữ invariant của class được kế thừa hoặc chuẩn bị đối số phức tạp. **Không được đọc `this`, gọi instance method hoặc truy cập instance field chưa hợp lệ trong early construction context.** Không cố viết lại constructor đang ngắn gọn bằng cách tách thành nhiều bước vô ích.

### 4.3. Khi nào chọn API final thay cho “mẹo”

- Nếu cần truyền context **chỉ đọc**, xét `ScopedValue`; nếu chia sẻ trạng thái thay đổi, không ép `ScopedValue` thay cho object/service quản lý trạng thái.
- Nếu cần HKDF theo protocol, dùng `KDF` của JDK, không sao chép implementation không kiểm toán trên blog.
- Nếu ứng dụng có nhiều luồng hiệu năng nhạy cảm, thu số liệu trước khi đổi GC hoặc JVM flag.

## 5. Thư viện: đặt mức Java tối thiểu và hợp đồng API lên trước

Thư viện Java có một đặc thù: **người dùng quyết định runtime**, không phải tác giả thư viện. Ví dụ một thư viện `payment-utils` phục vụ cả ứng dụng Java 21 lẫn Java 25 thì không thể dùng `ScopedValue` của Java 25 trong nhánh bytecode xuất bản cho Java 21 mà vẫn gọi đó là “tương thích Java 21”.

### 5.1. Hai chiến lược hợp lệ

**Chiến lược A — giữ tương thích JDK thấp hơn:** build bằng JDK 25, chọn `--release 21`. Java compiler hạn chế API và class file về Java 21, nghĩa là các API chỉ có từ 25 không thể xuất hiện trong code biên dịch cho mục tiêu này.

~~~bash
javac --release 21 -d out src/com/example/api/*.java
~~~

Ví dụ cấu hình Gradle Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Đây là cách **dùng JDK 25 để build** nhưng không tuyên bố thư viện yêu cầu Java 25. Nếu dự án dùng test runtime 25, vẫn cần test cả Java 21 thực tế để kiểm tra reflection, dependency và hành vi bên ngoài compile.

**Chiến lược B — nâng Java tối thiểu lên 25:** chỉ áp dụng sau khi xác nhận phần lớn người dùng thư viện đã có runtime phù hợp và có lý do kỹ thuật rõ ràng (ví dụ public API cần `KDF`/`ScopedValue`). Công bố thay đổi là breaking compatibility, cập nhật Gradle/Maven metadata, release notes và ma trận CI.

### 5.2. Những điều không nên làm với thư viện

- Đưa preview API của Java 25 vào **public method signatures**; người dùng có thể phải bật preview và bị khóa vào release cụ thể.
- Phát hành bytecode Java 25 (**class file major version 69**) rồi ghi tài liệu “hỗ trợ Java 21” (class file Java 21 là version 65).
- Đưa AOT cache của ứng dụng thử nghiệm vào JAR thư viện rồi giả định người dùng nào cũng dùng được. Cache gắn với **app, JDK và platform**.
- Ép người dùng đổi GC/heap flags chỉ để chạy một helper library; thư viện có thể đưa kết quả benchmark và đề xuất, nhưng quyền chọn JVM thuộc ứng dụng.
- Dùng module import như cách giấu một dependency mà `module-info.java` cần công bố qua `requires`.

Một **multi-release JAR** có thể là giải pháp nâng cao khi cần implementation Java 25 nhưng vẫn giữ base API trên JDK cũ. Đổi lại là kiểm thử và bảo trì nhiều đường code, nên không phải lựa chọn mặc định cho thư viện nhỏ.

## 6. Dịch vụ: ưu tiên ScopedValue, vận hành và quan sát

Dịch vụ Spring Boot, Jakarta EE hoặc framework khác chạy lâu dài thường có request/job context, nhiều luồng và yêu cầu quan sát. Java 25 mang đến một số khả năng đáng thử, nhưng không phải chúng tự động thay thế cách framework quản lý security context, transaction hay tracing.

### 6.1. ScopedValue: dữ liệu không đổi theo dynamic scope

`ScopedValue` đã trở thành API final trong Java 25 (JEP 506). Nó có ích khi nhiều lời gọi lồng nhau cần truy cập **một giá trị ngữ cảnh bất biến** mà không muốn truyền cùng tham số qua hàng loạt tầng.

~~~java
// File: RequestScopeDemo.java
public class RequestScopeDemo {

    record RequestContext(String correlationId) {}

    private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        var context = new RequestContext("demo-42");

        ScopedValue.where(CURRENT, context)
                .run(RequestScopeDemo::handle);

        System.out.println(CURRENT.isBound()); // false: đã ra khỏi scope
    }

    private static void handle() {
        audit();
    }

    private static void audit() {
        System.out.println(CURRENT.get().correlationId());
    }
}
~~~

Ý nghĩa:

- Giá trị được bind trong phạm vi `run(...)`; khi ra khỏi phạm vi, binding được dỡ bỏ, kể cả khi có ngoại lệ.
- Không cần `remove()` thủ công như một số cách dùng `ThreadLocal` cũ; `ScopedValue` không phải mutable global variable.
- Mỗi thread có binding của riêng nó. **Không tự động truyền sang arbitrary executor, thread pool hoặc HTTP request khác**. Với child tasks được tạo qua cơ chế structured concurrency phù hợp, JVM có thể kế thừa scoped value theo mô hình đó, nhưng Structured Concurrency trong **Java 25 vẫn preview**.
- Đừng đặt token, mật khẩu hoặc dữ liệu nhạy cảm vào context nếu không có lý do, chính sách truy cập và retention rõ ràng.

**Trường hợp tốt:** correlation ID không nhạy cảm, locale hoặc immutable request metadata cần được đọc qua nhiều tầng. **Trường hợp không phù hợp:** thay thế toàn bộ Spring SecurityContext, MDC, transaction context hoặc tracing propagation mà chưa có framework integration được kiểm chứng.

### 6.2. Startup và warmup: AOT cache chỉ khi đo được hiệu quả

Java 25 cải thiện AOT cache qua **JEP 514** (ergonomics dòng lệnh) và **JEP 515** (method profiling từ training run). Một quy trình minh họa:

~~~bash
# Training: ứng dụng chạy với workload đại diện, sau đó thoát an toàn.
java -XX:AOTCacheOutput=shop.aot -jar shop.jar

# Chạy lại với cache tương thích.
java -XX:AOTCache=shop.aot -jar shop.jar
~~~

Đối với dịch vụ, ở training run cần gửi **request đại diện**, rồi dừng tiến trình đúng cách để hoàn tất tạo cache. `-XX:AOTCacheOutput` hỗ trợ workflow đơn giản hóa ở JDK 25, bao gồm giai đoạn ghi cấu hình và tạo cache khi kết thúc training. Đừng xem cache như một file binary dùng chung không giới hạn:

- Cache phụ thuộc ứng dụng/classpath, **JDK release**, hệ điều hành và kiến trúc CPU; đổi một trong những điều đó thì phải tạo lại cache.
- Training workload không đại diện có thể không đem lại lợi ích đáng kể cho đường code quan trọng.
- Cấu hình production và training cần tương thích; dùng `-Xlog:aot` để kiểm tra cache có thật sự được nạp hay không.
- Trong chế độ tự động mặc định, nếu cache không thể dùng, JVM có thể tiếp tục **không sử dụng cache**. Nếu cần fail fast để kiểm tra, đọc `-XX:AOTMode` trong tài liệu `java` của đúng JDK trước khi áp dụng.
- So sánh **cold start, time to ready, warmup, p95/p99 latency, CPU và RSS** giữa baseline và cache. Không chỉ xem một lần in log “AOT loaded”.

**Dịch vụ quy mô nhỏ / serverless / autoscaling nhanh** có thể hưởng lợi; dịch vụ sống hàng tháng với workload ổn định có thể ít được lợi hơn từ cải thiện startup. Không nên đặt tối ưu startup lên trên tính chính xác và độ tin cậy.

### 6.3. Heap và GC: đánh giá thay vì bật tất cả flags

**Compact Object Headers** (JEP 519) là tính năng chính thức trong JDK 25 nhưng **tắt mặc định trong chính JDK 25**. Có thể thử trên staging:

~~~bash
java -XX:+UseCompactObjectHeaders -jar shop.jar
~~~

Nếu ứng dụng tạo nhiều đối tượng nhỏ, heap live set có thể giảm; nhưng cần xem tương tác với GC, CPU và layout đối tượng thực tế. Ở các bản JDK sau, giá trị mặc định có thể đã thay đổi, nên luôn ghi lại `java -version` và JVM flags thực tế, không dựa vào giả định từ tài liệu Java 25.

**Generational Shenandoah** (JEP 521) cho phép mô hình nhiều thế hệ khi dùng Shenandoah. Ví dụ kiểm thử trên một bản phân phối có hỗ trợ:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -jar shop.jar
~~~

Không khẳng định Shenandoah là lựa chọn tốt nhất cho mọi dịch vụ. So sánh với GC đang dùng dựa trên pause percentiles, allocation rate, throughput, peak RSS và CPU; kiểm tra hỗ trợ trên JDK vendor, hệ điều hành và architecture cụ thể. Không tự ý thay GC trên production nếu chưa có baseline và cách rollback.

## 7. Công cụ dòng lệnh: áp dụng compact source và module import

CLI nhỏ thường được gọi nhiều lần, cần dễ đọc, dễ triển khai và khởi động nhanh. Đây là nơi **JEP 512** và **JEP 511** có lợi ích rõ rệt nhất.

### 7.1. Một file Java 25 chạy trực tiếp

Lưu đoạn sau vào `HelloTool.java`:

~~~java
// File: HelloTool.java
void main(String[] args) {
    if (args.length == 0) {
        IO.println("Usage: java HelloTool.java <name>");
        return;
    }
    IO.println("Hello, " + args[0]);
}
~~~

Chạy:

~~~bash
java HelloTool.java Alice
~~~

Đây là **compact source file**: không cần khai báo `class`, có instance `main`, và dùng `java.lang.IO.println(...)`. Trong **Java 25**, `IO` nằm ở `java.lang` và **không** được tự động import static method `println`; dạng `println("Hi")` không thể coi là tương đương `IO.println("Hi")` nếu chưa có `import static java.lang.IO.println;`.

Compact source file tự động import các public types được `java.base` export, tương tự `import module java.base;`. Ví dụ xử lý ngày giờ cũng không cần import thông thường:

~~~java
// File: Today.java
void main() {
    IO.println(LocalDate.now());
    IO.println(List.of("build", "test", "deploy"));
}
~~~

**Ranh giới:** compact source file có **implicitly declared class** trong unnamed package, không thiết kế để các module khác import class ấy như public API. Với CLI đã phát triển thành sản phẩm nhiều file, có plugin architecture hoặc module descriptors, hãy dùng class/package và build system thông thường. Tính năng mới **giảm độ phức tạp khởi đầu**, không loại bỏ các khái niệm kiến trúc khi chương trình lớn lên.

### 7.2. Module import trong CLI có class rõ ràng

Nếu CLI đã có `class`:

~~~java
// File: InspectFile.java
import module java.base;

public class InspectFile {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected one path");
        }
        Path file = Path.of(args[0]);
        System.out.println(file.getFileName());
        System.out.println(Files.size(file));
    }
}
~~~

`Path` và `Files` đều từ `java.nio.file`. Trong mã có import nhiều module khác nhau, tránh `import module java.se;` chỉ vì tiện nếu nó gây nhập thừa hoặc va chạm tên; cân nhắc các import đơn lẻ cho code quan trọng.

### 7.3. AOT cache cho CLI: chỉ đáng làm khi chạy lặp lại

Một CLI chạy trong vài chục mili-giây và bị gọi hàng nghìn lần có thể hưởng lợi từ tối ưu startup; một CLI chạy một lần rồi chờ I/O nhiều phút thường không cần AOT. Hãy so thời gian từ `start` đến kết thúc trên nhiều lần chạy, cùng input/dataset và cùng bản JDK. Cache cần được huấn luyện từ luồng CLI thường dùng, không phải từ một câu lệnh `--help` nếu phần tốn thời gian là xử lý dữ liệu.

## 8. Bảo mật: KDF API phù hợp khi thật sự có dẫn xuất khóa

`javax.crypto.KDF` (JEP 510, final) cung cấp cách gọi chuẩn cho Key Derivation Function, ví dụ **HKDF-SHA256**. Đây là lựa chọn có giá trị cho **dịch vụ/ứng dụng** có thiết kế key hierarchy hoặc cryptographic protocol cần dẫn xuất khóa từ input keying material có entropy phù hợp.

~~~java
// File: HkdfDemo.java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.spec.AlgorithmParameterSpec;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

public class HkdfDemo {
    public static void main(String[] args) throws Exception {
        byte[] ikm = new byte[32];
        byte[] salt = new byte[32];
        new SecureRandom().nextBytes(ikm);
        new SecureRandom().nextBytes(salt);

        byte[] info = "example session-key".getBytes(StandardCharsets.UTF_8);
        AlgorithmParameterSpec spec = HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, 32);

        KDF hkdf = KDF.getInstance("HKDF-SHA256");
        SecretKey aesKey = hkdf.deriveKey("AES", spec);
        System.out.println("Derived AES key algorithm: " + aesKey.getAlgorithm());
        // Không in raw key bytes; ứng dụng thực quản lý vòng đời key nghiêm ngặt.
    }
}
~~~

**Lưu ý an toàn:**

- Demo sinh input keying material ngẫu nhiên để tránh hardcode secret trong source; hệ thống thật phải lấy material từ nguồn khóa được bảo vệ (HSM/KMS hoặc cơ chế được thiết kế cho protocol).
- HKDF không phải hàm hash mật khẩu dành cho password storage. Đừng dùng nó thay các password hashing/KDF chuyên dụng có tham số chi phí thích hợp.
- `salt`, `info`, độ dài key và thuật toán phải tuân thủ protocol được thiết kế, không tùy chọn ngẫu nhiên cho dữ liệu đã tồn tại.
- Không ghi key bytes, token hoặc material vào log, exceptions, traces hay test reports. Cần xét xóa mảng chứa secret khi có thể, nhưng không giả định JVM bảo đảm xóa mọi bản sao trong bộ nhớ.
- API chuẩn giúp giảm rủi ro tự viết HKDF, **không thay thế** việc thẩm định mô hình đe dọa, vòng đời khóa và quyền truy cập.

**Thư viện bảo mật dùng chung** chỉ nên đưa `KDF` vào public API khi đã nâng minimum Java lên 25. Nếu vẫn hỗ trợ runtime cũ, tách implementation theo phiên bản hoặc giữ API tương thích thay vì khiến mọi consumer bị ép nâng cấp.

## 9. JFR: đo trước, sửa sau

JDK Flight Recorder (JFR) vẫn là công cụ có giá trị để quan sát CPU, allocation, lock contention và các sự kiện JVM. Java 25 có **JFR Cooperative Sampling** (JEP 518) và **JFR Method Timing & Tracing** (JEP 520), cải thiện khả năng phân tích chương trình. Không phải cứ chạy `java -jar` là đã bật mọi event tracing method; cần profile/configuration phù hợp.

Ví dụ ghi một profile có thời lượng giới hạn:

~~~bash
# Chạy ứng dụng mới với recording có giới hạn.
java -XX:StartFlightRecording=filename=baseline.jfr,duration=60s,settings=profile -jar shop.jar

# Tóm tắt file đã ghi bằng bộ công cụ JDK 25.
jfr summary baseline.jfr
~~~

Hoặc khi tiến trình đã chạy:

~~~bash
jcmd <pid> JFR.start name=upgrade settings=profile duration=60s filename=upgrade.jfr
~~~

Sử dụng file `.jfr` để so sánh **trước/sau nâng cấp**: stack sampling, allocation, GC pauses, lock contention, thread states và các sự kiện có liên quan. Nếu cần JFR method tracing chuyên sâu, cấu hình các event/điểm instrument có chủ đích theo JEP 520; bật tràn lan có thể làm tăng overhead và dữ liệu nhạy cảm trong recording.

**Không nhầm lẫn JEP 509:** JFR CPU-Time Profiling trong **JDK 25 còn experimental**, dù cơ chế sampling khác trong JEP 518 đã chính thức. Với hệ thống production, ưu tiên các sự kiện JFR đã được hỗ trợ ổn định và giới hạn quyền truy cập recording, vì stack/method/URL có thể tiết lộ thông tin vận hành.

## 10. Preview / incubator trong Java 25: biết để tránh khóa sản phẩm

Những khả năng dưới đây có ý nghĩa nghiên cứu nhưng không phải nhóm **tính năng final nên dùng làm nền tảng mặc định**:

| JEP | Trạng thái ở 25 | Quyết định thực tế |
| --- | --- | --- |
| **470** PEM Encodings of Cryptographic Objects | Preview | Đánh giá API cho định dạng PEM; code sản xuất muốn ổn định nên chọn giải pháp được hỗ trợ trên minimum JDK và kiểm toán bảo mật. |
| **502** Stable Values | Preview | Thử nghiệm nếu cần stable initialization; không mặc định đưa vào thư viện public. |
| **505** Structured Concurrency | Fifth Preview | Thử trong PoC phục vụ cancellation/task ownership; không giả định signature ổn định giữa JDK releases. |
| **507** Primitive Types in Patterns/`instanceof`/`switch` | Third Preview | Không viết cú pháp preview trong nhánh production chỉ để rút vài dòng. |
| **508** Vector API | Tenth Incubator | Benchmark workload vector hóa; có nguy cơ đổi API/module trong tương lai. |
| **509** JFR CPU-Time Profiling | Experimental | Chỉ bật phục vụ chẩn đoán có kiểm soát trên platform được hỗ trợ; không đánh đồng với các cải tiến JFR final. |

Nếu nhóm buộc phải dùng preview:

~~~bash
# Chỉ minh họa cờ khi nghiên cứu tính năng preview *của Java 25*.
javac --enable-preview --release 25 PreviewSample.java
java --enable-preview PreviewSample
~~~

Chỉ biên dịch khi source thật sự dùng đúng API/cú pháp preview tương thích với Java 25; đây không phải công thức để bật incubator hoặc experimental. Với incubator có thể cần `--add-modules` và tên module phù hợp; không trộn nhiều flags chỉ vì thấy trên ví dụ của JDK khác.

**Quy tắc theo ghi chú của module học:** khi xây bài tập hoặc code mẫu dùng lâu dài, **ưu tiên final feature**; giới thiệu preview để hiểu trạng thái và quyết định tránh hoặc cô lập rủi ro, không dạy những mẹo/tùy chọn đã lỗi thời như phương án triển khai nên áp dụng hôm nay.

## 11. Nâng cấp JDK: hai trục tương thích phải kiểm riêng

Có hai trường hợp:

- **Nâng runtime:** chạy artifact hiện tại trên JDK 25. Cần kiểm tra dependency, agents, JNI/native libs, module encapsulation, TLS và thuật toán bảo mật, GC flags, container image, monitoring.
- **Nâng language/API target:** biên dịch source sang `--release 25`, có thể dùng final feature mới. Điều này nâng minimum runtime cho artifact xuất bản.

Không nên gom hai bước vào một PR lớn chỉ vì toolchain mới đã sẵn có.

### 11.1. Ma trận CI/CD đề xuất

| Thử nghiệm | JDK build | Target `--release` | JDK chạy | Mục tiêu |
| --- | --- | --- | --- | --- |
| Runtime upgrade | 25 (hoặc toolchain hiện tại) | 21 | 25 | Kiểm tra app cũ chạy đúng trên JDK mới. |
| Library backward compatibility | 25 | 21 | **21 và 25** | Không lộ API 25 và class file 69. |
| Ứng dụng chỉ chạy Java 25 | 25 | 25 | 25 | Cho phép dùng ScopedValue/KDF/flexible constructors. |
| CLI Java 25 source launcher | 25 | Đường source file | 25 | Chạy `java Tool.java`, không cần phát hành class API. |
| Performance A/B | 25 | Theo artifact thật | 25 | So startup/warmup/GC/JFR cùng workload. |

Mục tiêu `--release 21` là **ví dụ** cho sản phẩm cần hỗ trợ Java 21. Nếu dự án phải hỗ trợ Java 17 thì dùng 17 và test trên runtime 17, không suy luận từ việc chạy thành công trên JDK 25.

### 11.2. Các kiểm tra không nên bỏ qua

1. **Tương thích framework/library:** kiểm tra Spring, ORM, build plugins, test engines, agents/instrumentation và bytecode manipulation có nhận class file Java 25 không.
2. **Hệ điều hành và architecture:** JDK 25 không còn 32-bit x86 port; xem image base và native dependencies.
3. **Flags bị bỏ/thay đổi:** đọc release notes JDK 25; không bê nguyên tập JVM options từ ứng dụng Java 8/11 cũ mà không kiểm tra.
4. **Security:** chạy bài test TLS, certificate, cryptographic provider, policy, serialization và key management; không trì hoãn cập nhật bản vá bảo mật.
5. **JFR/JVM baseline:** đo p50/p95/p99 latency, startup, throughput, peak RSS, GC pause và CPU. Cùng phần cứng/cấu hình/workload.
6. **Rollback:** giữ khả năng quay về JDK/artifact trước trong thời gian triển khai; cache AOT phải được tái tạo cho đúng bản JDK.
7. **Lịch bảo trì:** chọn vendor/distro có bản vá định kỳ và định nghĩa quy trình nâng bản cập nhật 25.x; “LTS” không miễn trừ kiểm soát CVE.

### 11.3. Maven và Gradle: chọn mục tiêu có chủ ý

Nếu muốn Java 25 làm minimum runtime:

~~~xml
<!-- Fragment pom.xml: với Maven Compiler Plugin cấu hình phù hợp. -->
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
~~~

Nếu muốn tiếp tục hỗ trợ Java 21, đặt `maven.compiler.release=21` thay vì 25; không chỉ thay `JAVA_HOME` rồi kỳ vọng minimum runtime giữ nguyên.

## 12. Khung ra quyết định có thể áp dụng cho dự án thật

Một tính năng Java 25 chỉ nên được chọn khi trả lời được năm câu hỏi:

~~~mermaid
flowchart TD
    A["Đang làm app / library / service / CLI?"] --> B{"Kiểm soát runtime Java 25?"}
    B -->|"Không / nhiều runtime"| C["Ưu tiên tương thích --release thấp hơn"]
    B -->|"Có"| D{"Tính năng final ở JDK 25?"}
    D -->|"Không"| E["PoC cô lập, có chấp thuận rủi ro"]
    D -->|"Có"| F{"Có lợi ích và test xác minh?"}
    F -->|"Không"| G["Giữ code/cấu hình hiện tại"]
    F -->|"Có"| H["Thử nghiệm, đo benchmark và security"]
    H --> I{"Đạt CI, SLO, rollback?"}
    I -->|"Chưa"| G
    I -->|"Có"| J["Áp dụng có kiểm soát"]
~~~

Ghi quyết định vào ADR ngắn:

| Tiêu chí | Ví dụ: dịch vụ checkout | Kết luận |
| --- | --- | --- |
| Loại sản phẩm | REST service chạy container, nhóm kiểm soát JDK | Có quyền nâng runtime lên 25. |
| Tính năng | `ScopedValue` cho immutable correlation context | Final trong Java 25. |
| Lợi ích | Giảm truyền tham số qua nhiều tầng; binding có scope rõ ràng | Nên làm PoC. |
| Rủi ro | Framework tracing/MDC không tự đồng bộ; async tasks không tự inherit | Phải có integration test thread hop. |
| Test | Request sync, exception, executor, shutdown, context không rò | Điều kiện bắt buộc. |
| Quyết định | Chỉ đưa ScopedValue vào lớp adapter nội bộ sau khi test PASS | Không thay mọi `ThreadLocal` một cách cơ học. |

Phương pháp này dùng được cho cả thư viện, dịch vụ, CLI và ứng dụng; chỉ thay tiêu chí ưu tiên và mức độ tự chủ runtime.

## 13. Bài tập tổng hợp theo bốn dạng sản phẩm

### Tình huống A — Ứng dụng quản lý kho

Một ứng dụng nội bộ chạy duy nhất trên Java 25; lớp `ValidatedQuantity` kế thừa một base class có constructor cần tham số hợp lệ.

**Yêu cầu:** viết constructor kiểm tra quantity trước `super(...)` theo JEP 513; nếu chương trình dùng nhiều API `java.base`, thử `import module java.base;` rồi nhận xét về khả năng đọc code. **Tiêu chí đạt:** kiểm tra invariant rõ ràng, không dùng `this` sai quy tắc, test cho giá trị hợp lệ và không hợp lệ.

### Tình huống B — Thư viện mã hóa dùng chung

Thư viện hỗ trợ Java 21 và Java 25, đồng thời một nhóm muốn sử dụng `javax.crypto.KDF` trong public API.

**Yêu cầu:** trình bày hai lựa chọn (duy trì `--release 21` hoặc nâng minimum lên 25), chi phí tương thích, cách cô lập implementation và ma trận CI. **Tiêu chí đạt:** không tuyên bố chạy được Java 21 nếu artifact/reference API chỉ có từ 25; không dùng HKDF thay password hashing.

### Tình huống C — Dịch vụ thanh toán

Service có 100 replica, yêu cầu p99 latency ổn định, khởi động thường xuyên và heap áp lực.

**Yêu cầu:** thiết kế phép đo **baseline → AOT → Compact Object Headers → Generational Shenandoah** (mỗi thay đổi một thử nghiệm độc lập), dùng JFR để đo, ghi `-Xlog:aot` và xây rollback. **Tiêu chí đạt:** quyết định dựa trên dữ liệu, không bật mọi JVM flag cùng lúc rồi đo một kết quả không thể quy nguyên nhân.

### Tình huống D — CLI hỗ trợ vận hành

Công cụ `inspect-config` đọc một file, in thông tin hợp lệ và chạy trong image có JDK 25.

**Yêu cầu:** triển khai phiên bản compact source file dùng instance `main` và `IO.println`, so sánh với class `main` thông thường, đo startup với và không có AOT khi chạy lặp lại. **Tiêu chí đạt:** script dễ đọc, không tự chứa secret hardcoded và không coi implicitly declared class là public API dùng cho thư viện.

## 14. Checklist áp dụng và tài liệu tham khảo

Trước khi mở PR sử dụng tính năng Java 25, đánh dấu các điều kiện:

- [ ] Đã xác định rõ loại dự án: **ứng dụng / thư viện / dịch vụ / CLI** và ai kiểm soát runtime.
- [ ] Có danh sách minimum JDK, target `--release`, CI runtime và chính sách cập nhật JDK.
- [ ] Tính năng được chọn là **final ở Java 25**, hoặc có quyết định riêng nếu preview/incubator/experimental.
- [ ] Không dùng API đã loại bỏ/không còn phù hợp, không dựa vào 32-bit x86, không bê flags JVM cũ mà không kiểm chứng.
- [ ] Với thư viện, public API và bytecode không vi phạm minimum JDK đã công bố.
- [ ] Với dịch vụ, thử đúng **workload**, đo JFR, heap, GC, startup, p95/p99, kiểm tra context propagation.
- [ ] Với CLI, tính năng compact source và module import thực sự giảm độ phức tạp.
- [ ] Với API mật mã, sử dụng KDF đúng protocol, bảo vệ key material và không tự chế thuật toán.
- [ ] Có bài test hồi quy, benchmark hoặc bằng chứng có thể tái tạo và kế hoạch rollback.

### Tài liệu chính thức nên tra

1. [OpenJDK — JDK 25 Project](https://openjdk.org/projects/jdk/25/): danh sách JEP và trạng thái theo release.
2. [Oracle — Significant Changes in JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): tổng quan API, preview, runtime, JFR và các thay đổi ảnh hưởng di trú.
3. [Oracle — Java Language Changes for SE 25](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): JEP 507/511/512/513 và trạng thái ngôn ngữ.
4. [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511) và [Oracle — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html).
5. [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512) và [Oracle — Compact Source Files](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html).
6. [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513) và [Oracle — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html).
7. [JEP 506 — Scoped Values](https://openjdk.org/jeps/506) và [Java SE 25 ScopedValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html).
8. [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510) và [Java SE 25 KDF API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html).
9. [JEP 514 — AOT Command-Line Ergonomics](https://openjdk.org/jeps/514), [JEP 515 — AOT Method Profiling](https://openjdk.org/jeps/515), [JDK 25 `java` man page](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
10. [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518), [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520), [JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html).
11. [JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519), [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521), [Oracle — Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/).

**Kết luận:** Giá trị của Java 25 không nằm ở việc một codebase dùng nhiều cú pháp mới nhất, mà ở khả năng **chọn đúng tính năng chính thức cho đúng sản phẩm, giữ tương thích nơi cần thiết, áp dụng API bảo mật chuẩn và đo được lợi ích vận hành**. Với mọi quyết định, hãy khóa phiên bản JDK thực tế, đọc tài liệu của đúng bản đó và kiểm chứng bằng test hoặc benchmark thay vì phỏng đoán.
