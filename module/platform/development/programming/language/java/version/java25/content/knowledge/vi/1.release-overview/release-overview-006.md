# Nguyên tắc đánh giá tính năng theo độ ổn định, lợi ích và chi phí nâng cấp

## 1. Tại sao cần một khung đánh giá trước khi dùng tính năng Java 25?

Java 25 được phát hành tháng 9/2025 và là một dòng **Long-Term Support (LTS)** được nhiều nhà cung cấp JDK hỗ trợ. Nhưng một JDK LTS **không đồng nghĩa mọi tính năng xuất hiện trong phiên bản đó đều đã hoàn thiện**. Bên cạnh các tính năng ngôn ngữ/API đã trở thành chuẩn, JDK 25 còn có các đề xuất ở trạng thái preview, incubator hoặc experimental, chỉ thích hợp để đánh giá trong điều kiện được kiểm soát.

Khi nâng cấp hệ thống từ Java 17/21 lên Java 25, phải tách hai quyết định:

1. **Nâng cấp runtime/compiler lên JDK 25:** nhằm có nền tảng được cập nhật, hỗ trợ dài hạn từ nhà cung cấp, các cải tiến VM, công cụ và thư viện chuẩn; có thể nâng cấp mà **không** viết lại ứng dụng để dùng tính năng ngôn ngữ mới.
2. **Chủ động áp dụng từng tính năng Java 25:** phải chứng minh một lợi ích riêng, độ ổn định đủ cao và chi phí áp dụng/đảo ngược chấp nhận được.

Ví dụ: một dịch vụ Spring Boot có thể chạy trên JDK 25, tiếp tục biên dịch mã theo mức Java 21 nếu cần tương thích, rồi thử hiệu quả AOT cache và JFR trong môi trường kiểm thử. Không có yêu cầu phải đổi ngay tất cả constructor sang cú pháp mới, đưa preview API vào production hoặc chuyển mọi `ThreadLocal` sang `ScopedValue`.

**Phạm vi bài:** phần *Tổng quan Java 25*, đề bài **“Nguyên tắc đánh giá tính năng theo độ ổn định, lợi ích và chi phí nâng cấp”**, thuộc module `JAVA_VERSION_JAVA25`. Bài ưu tiên kiến thức có giá trị áp dụng hiện nay: quy trình xét trạng thái JEP, API chuẩn, kiểm thử nâng cấp, đo hiệu quả, kiểm soát rủi ro và hoạch định chi phí. Các ý tưởng còn thử nghiệm chỉ được nêu để phân loại và quyết định **chưa dùng trong mã production**, không được giới thiệu như API ổn định.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt tính ổn định của **JDK release**, **JEP/tính năng** và **dependency ecosystem**.
- Chọn tính năng đáng áp dụng dựa trên mức ổn định, lợi ích có thể đo và chi phí nâng cấp.
- Viết một bản đánh giá ngắn có đường baseline, cách benchmark và điều kiện rollback.
- Dùng công cụ hiện hành như `jdeps`, `jdeprscan`, `javac --release` và JFR để đánh giá rủi ro.
- Hiểu vì sao Java 25 LTS vẫn cần kiểm thử tương thích về JDK vendor, build tool, framework, AOT, bảo mật và hành vi runtime.

## 2. Ba trục quyết định phải được đánh giá độc lập

~~~mermaid
flowchart TD
    A["Một tính năng / thay đổi JDK 25"] --> S["Ổn định và mức cam kết API"]
    A --> B["Lợi ích đo được"]
    A --> C["Chi phí và rủi ro chuyển đổi"]
    S --> D{"Có vượt các cổng bắt buộc?"}
    B --> D
    C --> D
    D -->|Không| E["Không áp dụng / chỉ thử nghiệm"]
    D -->|Có| F["PoC và benchmark"]
    F --> G{"Bằng chứng đạt ngưỡng?"}
    G -->|Không| E
    G -->|Có| H["Rollout có kiểm soát"]
    H --> I["Đo sau triển khai và duy trì rollback"]
~~~

**Độ ổn định** trả lời: *API/cú pháp đã được chốt chưa, còn yêu cầu flag thử nghiệm không, phạm vi hỗ trợ có rõ không?*

**Lợi ích** trả lời: *Giảm được bao nhiêu độ trễ khởi động, bao nhiêu CPU/heap, bao nhiêu lỗi vận hành, hoặc giảm được bao nhiêu mã lặp?* Một cải tiến “đọc code đẹp hơn” có giá trị nhưng cần giới hạn phạm vi để tránh refactor lớn không cần thiết.

**Chi phí nâng cấp** trả lời: *Phải sửa bao nhiêu mã, nâng toolchain nào, tạo/test AOT cache như thế nào, chi phí CI/CD ra sao và rollback mất bao lâu?* Chi phí phải tính cả bảo trì về sau, không chỉ thời gian viết code lần đầu.

Không nên cho phép một điểm lợi ích rất cao bù trừ cho vi phạm bảo mật, API preview không được chính sách cho phép hoặc platform không còn được hỗ trợ. Vì thế quy trình phải có **cổng loại trừ bắt buộc** trước khi tính điểm lợi ích.

## 3. “Ổn định” không chỉ là nhãn LTS

### 3.1. Độ ổn định của dòng JDK

JDK 25 là một dòng LTS theo cam kết của một số nhà cung cấp, nhưng **lịch cập nhật, bản vá, thời hạn hỗ trợ, giấy phép và kiến trúc máy** phụ thuộc vendor/bản phân phối. Việc Java 25 có nhãn LTS không tự bảo đảm mọi binary, mọi container base image và mọi framework đều đã hỗ trợ đầy đủ.

Khi lựa chọn runtime, cần kiểm tra bằng dữ liệu hiện hành:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Bản phân phối JDK 25 nào? | Vendor, build number, checksum, nguồn download |
| Đến khi nào còn cập nhật bảo mật? | Support roadmap chính thức và gói hợp đồng thực tế |
| Runtime hỗ trợ hệ điều hành/CPU nào? | Ma trận OS/architecture, container image |
| Có yêu cầu giấy phép? | Giấy phép đúng phiên bản, phạm vi sử dụng và thời điểm update |
| Framework hỗ trợ Java 25 chưa? | Compatibility matrix và test thực tế |
| Khi có CVE, ai cung cấp update và ai triển khai? | Chủ sở hữu vận hành và lịch cập nhật |

Java 25 không còn hỗ trợ **cổng x86 32-bit** của OpenJDK (JEP 503); nếu còn workload cũ ở kiến trúc đó, phải giải quyết nền tảng thay vì chỉ thay version JDK. Không đánh đồng việc một CPU thuộc họ x86 với việc nó dùng **32-bit x86 port**: phần lớn triển khai x86-64 hiện đại là nền tảng khác.

### 3.2. Độ ổn định của từng tính năng

| Trạng thái | Cách hiểu đúng | Chính sách mặc định |
| --- | --- | --- |
| **Final / permanent** | API/cú pháp được hoàn thiện trong bản JDK đang xét | Có thể đánh giá để áp dụng production khi lợi ích rõ và test đạt |
| **Preview** | Thiết kế được công bố để lấy phản hồi, có thể thay đổi hoặc bị bỏ | Chỉ PoC/đánh giá theo chính sách; không lấy làm nền tảng sản phẩm lâu dài nếu chưa được duyệt |
| **Incubator** | API thử nghiệm trong module riêng, còn có thể thay đổi | Hạn chế ở thử nghiệm; không coi như hợp đồng ổn định |
| **Experimental** | Tính năng JVM/tooling mang tính thí nghiệm hoặc chẩn đoán | Chỉ bật có chủ đích, hiểu platform/overhead/flag và giới hạn phạm vi |
| **Removed / deprecated for removal** | Không còn hỗ trợ hoặc có lộ trình bị bỏ | Không đưa vào kiến trúc mới; ưu tiên gỡ các phụ thuộc cũ |

**Điểm quan trọng về thời gian:** một JEP có thể ở trạng thái preview khi **Java 25 được phát hành**, sau đó thay đổi trạng thái ở bản JDK khác. Khi quyết định trên một JDK mới hơn Java 25, phải xem **JEP mới và tài liệu đúng JDK mục tiêu**, không sao chép nhãn preview của năm 2025 để mô tả trạng thái vĩnh viễn của API. Bài này ghi trạng thái **tại JDK 25** và không khuyến khích viết code mới dựa trên API cũ đã bị thay thế.

### 3.3. Preview cần bật tường minh

Ví dụ kiểm tra một tính năng ngôn ngữ preview của JDK 25 **trong môi trường thí nghiệm**:

~~~bash
javac --enable-preview --release 25 PreviewExample.java
java --enable-preview PreviewExample
~~~

Không dùng hai lệnh trên để biện minh rằng code preview phù hợp cho một ứng dụng production đa phiên bản. Code biên dịch cho preview của JDK 25 có thể phải chỉnh sửa khi chuyển lên JDK tiếp theo. `--enable-preview` chỉ cho phép dùng preview ở phiên bản phù hợp, **không** bảo đảm sự ổn định ngôn ngữ/API.

Tính năng đã final như `ScopedValue` và `Module Import Declarations` trong JDK 25 không yêu cầu `--enable-preview` chỉ để sử dụng chính chúng.

## 4. Những khả năng Java 25 đáng đánh giá hiện nay

Bảng dưới đây lấy trạng thái **theo JDK 25**. Nó không phải mệnh lệnh “dùng tất cả”, mà là danh sách ưu tiên kiểm tra lợi ích trong những bài toán phù hợp.

| Khả năng | JEP | Trạng thái JDK 25 | Tình huống đáng đánh giá |
| --- | ---: | --- | --- |
| `ScopedValue` | 506 | Final | Ngữ cảnh bất biến, có phạm vi xử lý, cần rõ vòng đời hơn state thread-local |
| Key Derivation Function API (`javax.crypto.KDF`) | 510 | Final | Ứng dụng cần HKDF/derive key theo chuẩn, muốn API chuẩn thay cách tự triển khai |
| Module Import Declarations | 511 | Final | Mã mẫu/tool nhỏ cần import gọn các package được export từ module |
| Compact Source Files and Instance Main Methods | 512 | Final | Chương trình nhỏ, ví dụ học tập, CLI/one-file utilities |
| Flexible Constructor Bodies | 513 | Final | Kiểm tra input/khởi tạo field an toàn trước lời gọi `super(...)` hoặc `this(...)` theo quy tắc ngôn ngữ |
| AOT Command-Line Ergonomics | 514 | Delivered | Đánh giá startup/warmup với luồng tạo AOT cache đơn giản hơn |
| AOT Method Profiling | 515 | Delivered | Cải thiện warmup/JIT bằng profile tạo từ chạy thực nghiệm |
| JFR Cooperative Sampling | 518 | Delivered | Đánh giá sự ổn định và đặc tính profiling của JFR |
| Compact Object Headers | 519 | Delivered | Kiểm chứng footprint/throughput của ứng dụng nhiều object |
| JFR Method Timing & Tracing | 520 | Delivered | Chẩn đoán có mục tiêu các method quan trọng với JFR |
| Generational Shenandoah | 521 | Delivered | Đánh giá collector khi ứng dụng có đặc tính latency/heap thích hợp |

Nhóm **delivered** ở đây chỉ nói rằng JEP có mặt trong JDK 25; nó không tự động có nghĩa tính năng đã phù hợp với mọi workload hoặc mọi vendor. Các tính năng JVM/GC/JFR cần số liệu và kiểm tra implementation thay vì dùng “final” như chứng cứ hiệu năng.

### Nhóm chưa nên đưa vào đường chính sản phẩm chỉ vì “mới”

| Khả năng ở Java 25 | JEP | Trạng thái tại Java 25 | Lựa chọn thận trọng |
| --- | ---: | --- | --- |
| Stable Values | 502 | Preview | Thử nghiệm ở nhánh PoC; theo dõi trạng thái API ở JDK mục tiêu |
| Structured Concurrency | 505 | Fifth Preview | Đánh giá mô hình task scope nhưng không khóa sản phẩm vào chữ ký preview của JDK 25 |
| Primitive Types in Patterns, `instanceof`, `switch` | 507 | Third Preview | Chỉ thử cú pháp và đánh giá thay đổi qua phiên bản |
| PEM Encodings of Cryptographic Objects | 470 | Preview | Không phụ thuộc vào API preview cho hợp đồng bảo mật production |
| Vector API | 508 | Tenth Incubator | Dùng thử benchmark chuyên biệt, có fallback ổn định |
| JFR CPU-Time Profiling | 509 | Experimental | Chỉ bật khi cần chẩn đoán có giới hạn; xem hỗ trợ platform |

Bảng này không dạy các giao diện preview như API đã hoàn thiện. Thay vào đó, nó dạy **cách nhận diện mức độ cam kết**. Đối với ứng dụng chạy trên một JDK mới hơn, cần đánh giá tài liệu/JEP của chính release đó để biết các tính năng đã final hoặc thay đổi cách dùng hay chưa.

## 5. Đặt bài toán thực tế trước tên tính năng

Một bảng lựa chọn theo vấn đề:

| Vấn đề hiện có | Khả năng nên thử | Câu hỏi phải đo |
| --- | --- | --- |
| Mã CLI học tập quá nhiều boilerplate | Compact source files, module imports | Giảm được bao nhiêu dòng, tính rõ ràng và khả năng đóng gói thế nào? |
| Validation constructor phải đặt sau `super(...)` theo cách cũ | Flexible constructor bodies | Loại được workaround nào, test kế thừa có an toàn hơn không? |
| Ngữ cảnh tạm thời bị rò khi dùng `ThreadLocal` | `ScopedValue` | Scope có gọn, bất biến và phù hợp async/task lifecycle không? |
| Cần dẫn xuất khóa HKDF an toàn | `javax.crypto.KDF` | Có hỗ trợ algorithm/provider, key handling và policy bảo mật không? |
| Startup/scale-out chậm | AOT cache/profiling | p50/p95 startup giảm bao nhiêu với cache thực tế và đúng workload? |
| Chậm do CPU hoặc latency bất thường | JFR (bao gồm khả năng mới của 25) | Có tìm được bottleneck mà không tạo overhead không chấp nhận được không? |
| Heap footprint cao với nhiều object | Compact object headers | RSS/heap/GC giảm bao nhiêu trên workload thực? |

**Không dùng công cụ để tạo ra bài toán.** Nếu startup đã dưới ngưỡng SLO, AOT cache có thể không đáng tăng phức tạp CI/CD. Nếu code đã đơn giản và ít thay đổi, không cần refactor hàng nghìn constructor chỉ để “đúng Java 25”.

## 6. Tính lợi ích bằng số liệu, không bằng cảm giác

Chọn baseline và chỉ số đủ đại diện, đo trước/sau trong cùng điều kiện.

| Loại giá trị | Chỉ số | Cách ghi nhận |
| --- | --- | --- |
| Hiệu năng khởi động | startup p50/p95, time-to-ready | Từ JVM start đến readiness có kiểm tra thực |
| Warmup | throughput/latency trong N phút đầu | Traffic mẫu theo nhiều giai đoạn |
| Độ trễ | p50/p95/p99 theo endpoint/use case | So sánh dưới cùng QPS và dữ liệu |
| Tài nguyên | RSS, heap, CPU, GC pause, allocation | JFR/JMX/metrics có cùng cấu hình |
| Bảo mật | số dependency tự triển khai crypto, số issue | Audit threat model/crypto provider |
| Chất lượng code | mã lặp, số điểm phải dọn context, test coverage | Review phạm vi thay đổi và lỗi sau deploy |
| Vận hành | MTTR, chi phí triage, số lần rollback | Sự cố thật và bài diễn tập |
| Độ tương thích | số test pass, lỗi reflection/agent/framework | CI matrix và canary |

Đối với hiệu năng, nên chạy nhiều lần, làm nóng workload hợp lý, kiểm soát CPU throttling, GC và workload noise. Một lần khởi động nhanh hơn không đủ kết luận JDK 25 hoặc một JEP mang lại cải tiến có ý nghĩa.

**Ví dụ cách tính:** baseline startup p95 là 4,0 s; sau khi tạo AOT cache hợp lệ còn 3,0 s. Mức giảm tương đối = `(4,0 - 3,0) / 4,0 = 25%`. Nhưng quyết định đưa vào production còn phụ thuộc bộ nhớ, thời gian build cache, khả năng tái tạo cache và sự tương thích ở các môi trường.

## 7. Tính đầy đủ chi phí nâng cấp

Chi phí một lần và chi phí duy trì phải được xem riêng:

| Nhóm chi phí | Câu hỏi |
| --- | --- |
| Build/CI | Maven/Gradle, compiler, test runners, annotation processors, plugin đã nhận diện JDK 25 chưa? |
| Framework/library | Spring, Hibernate, driver, Byte Buddy, mocking/agent, testcontainers có hỗ trợ không? |
| Runtime/container | Base image, architecture, GC, native libraries và startup scripts tương thích không? |
| Source migration | Sửa code cũ, internal API, reflection, illegal access hoặc preview có khó không? |
| Test và benchmark | Integration, performance, chaos, security tests có cần bổ sung? |
| Vận hành | Monitoring, JFR agent, heap diagnostics, debug symbols, rollback có thay đổi? |
| AOT | Có cần training representative và lưu cache theo đúng artifact/JDK/OS/CPU không? |
| Security/compliance | Crypto provider, TLS, certificates, giấy phép và kế hoạch vá CVE? |
| Đào tạo | Team đã hiểu `ScopedValue`, structured tasks, AOT/JFR và các công cụ mới chưa? |
| Duy trì dài hạn | Chi phí giữ nhiều JDK, nhánh code và profile build trong một thời gian? |

Có thể ước lượng đơn giản:

~~~text
Total cost =
  chi phí phát triển / sửa mã
+ chi phí test và benchmark
+ chi phí CI/CD + hạ tầng triển khai
+ chi phí vận hành định kỳ
+ chi phí đào tạo, hỗ trợ, compliance
+ chi phí rủi ro và dự phòng rollback
~~~

Đừng đưa tổng chi phí vào một số “độ khó” mơ hồ. Hãy ghi rõ số người-ngày, số pipeline bị ảnh hưởng, thời gian downtime cho phép và chi phí hạ tầng nếu là quyết định cần phê duyệt ngân sách.

### Phân biệt chi phí kỹ thuật và chi phí thay đổi hành vi

Nâng từ Java 21 lên 25 **nhưng giữ nguyên source level** thường có phạm vi sửa mã nhỏ hơn việc đồng thời dùng cú pháp Java 25, thay GC, thay security provider và tái thiết kế async flow. Thực hiện quá nhiều thay đổi cùng lúc làm khó truy nguyên nguyên nhân khi lỗi xuất hiện.

Bởi vậy nên chia việc thành **nâng runtime**, **kiểm chứng vận hành**, rồi **tận dụng từng tính năng mang lợi ích**.

## 8. Áp dụng nguyên tắc cho những tính năng đã hoàn thiện trong Java 25

Không phải feature final nào cũng có tỷ lệ lợi ích/chi phí giống nhau. Đọc từng ví dụ dưới đây như một **bài toán đánh giá**, không phải lời khuyên phải refactor toàn bộ hệ thống.

### 8.1. Compact source files và instance main methods — JEP 512

Khi cần viết một tiện ích nhỏ hoặc bài học đầu tiên, Java 25 cho phép cách viết cô đọng:

~~~java
// File: Hello.java (JDK 25)
void main() {
    IO.println("Hello from Java 25");
}
~~~

Chạy với JDK 25:

~~~bash
java Hello.java
~~~

Đây là tính năng **đã final ở Java 25**; không phải cú pháp preview cần `--enable-preview`. `IO.println(...)` thuộc `java.lang.IO` trong Java 25 và giúp in console đơn giản.

Đánh giá ba trục:

- **Ổn định:** final, dùng công cụ JDK 25 tiêu chuẩn.
- **Lợi ích:** chương trình nguồn ngắn, dễ hướng dẫn, script/utility nhỏ gọn.
- **Chi phí:** thấp với tệp độc lập, nhưng có thể cao nếu cố chuyển ứng dụng Spring Boot nhiều package sang cấu trúc chỉ dành cho chương trình nhỏ.

**Quyết định hợp lý:** khuyến khích trong tutorial, bài tập, CLI đơn giản. Không cố thay thế mọi class thông thường của codebase lớn. Nếu tiện ích phải chạy trên Java 21, cần cân nhắc vì source Java 25 không tương thích ngược với compiler 21.

### 8.2. Module Import Declarations — JEP 511

Java 25 cho phép import các package được xuất bởi một module theo dạng:

~~~java
import module java.base;

void main() {
    var names = List.of("alpha", "beta");
    IO.println(names);
}
~~~

Ví dụ này dùng cú pháp source Java 25. Mục tiêu là làm mã ngắn gọn khi phải dùng nhiều package chuẩn; ví dụ `List` đến từ `java.util` được exported bởi `java.base`.

**Đừng hiểu nhầm:** `import module java.base;` **không** tạo `module-info.java` cho ứng dụng, không tự yêu cầu module graph của dự án, không mở tất cả package nội bộ và không phải cách bỏ qua JPMS encapsulation.

Trong ứng dụng lớn, import cụ thể thường làm dependency của source file dễ thấy hơn. Chọn module import chỉ khi lợi ích về tính dễ đọc thực sự vượt sự kém rõ ràng của tập tên được đưa vào scope.

### 8.3. Flexible Constructor Bodies — JEP 513

Trong một số trường hợp, constructor cần xác thực input **trước** khi chuyển dữ liệu cho constructor của superclass. Java 25 cho phép một số câu lệnh hợp lệ đứng trước `super(...)` hoặc `this(...)`:

~~~java
class BaseCapacity {
    BaseCapacity(int capacity) {
        // Khởi tạo trạng thái của superclass.
    }
}

class StorageCapacity extends BaseCapacity {
    StorageCapacity(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        super(capacity);
    }
}
~~~

Ranh giới bắt buộc: những câu lệnh trước `super(...)` không thể tùy ý dùng đối tượng `this` đang được khởi tạo; cần tuân theo các giới hạn ngôn ngữ về truy cập instance state/dispatch trong constructor prologue.

**Giá trị:** biểu đạt validation tự nhiên hơn, giảm một số workaround hoặc lời gọi helper không cần thiết. **Chi phí:** phải xây dựng bằng JDK/source level hỗ trợ Java 25; không nhất thiết đổi constructor cũ nếu chúng đang dễ hiểu và an toàn.

### 8.4. ScopedValue — JEP 506

`ScopedValue` cung cấp cơ chế gắn dữ liệu ngữ cảnh theo **scope động có giới hạn** và được thiết kế theo hướng giá trị bất biến sau khi binding. Ví dụ:

~~~java
public class ScopedContextDemo {

    private static final ScopedValue<String> REQUEST_CONTEXT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_CONTEXT, "diagnostics-only")
                .run(ScopedContextDemo::handle);
    }

    static void handle() {
        String context = REQUEST_CONTEXT.get();
        System.out.println(context);
    }
}
~~~

Code minh họa cho Java 25, không cần preview flag cho `ScopedValue`. Khi scope kết thúc, binding không còn hiệu lực trong scope đó; truy cập ngoài scope nếu không có binding sẽ không giống truy cập một biến toàn cục.

Đánh giá:

- **Ổn định:** `ScopedValue` đã final trong Java 25.
- **Lợi ích:** làm rõ vòng đời dữ liệu ngữ cảnh so với cách dùng `ThreadLocal` không dọn đúng; phù hợp với nhiều kiểu structured operation.
- **Chi phí và rủi ro:** cần hiểu phạm vi binding, luồng con, context propagation, API framework đang dùng và sự khác nhau với mutable thread-local state.

**Không thay máy móc mọi `ThreadLocal`.** Với mutable state cần cập nhật hoặc integration của framework mà chỉ hiểu `ThreadLocal`, việc chuyển sang `ScopedValue` có thể sai mô hình. Cần test thực tế với executor, virtual threads và thư viện tracing/security nếu hệ thống sử dụng.

### 8.5. Key Derivation Function API — JEP 510

Java 25 bổ sung API `javax.crypto.KDF` để dẫn xuất key material bằng các thuật toán được hỗ trợ. Một ví dụ với HKDF:

~~~java
import java.nio.charset.StandardCharsets;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

class KeyDerivationExample {

    static SecretKey deriveAesKey(byte[] ikm, byte[] salt) throws Exception {
        byte[] info = "service-key-v1".getBytes(StandardCharsets.UTF_8);

        var spec = HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, 32);

        KDF kdf = KDF.getInstance("HKDF-SHA256");
        return kdf.deriveKey("AES", spec);
    }
}
~~~

Đoạn mã chỉ minh họa API, không phải thiết kế quản lý khóa hoàn chỉnh. `ikm` phải là keying material có tính entropy phù hợp; `salt` và `info` có ý nghĩa giao thức cụ thể; cần kiểm tra provider, vòng đời khóa, bí mật trong bộ nhớ, algorithm policy và threat model.

**HKDF không phải lựa chọn mặc định để hash mật khẩu người dùng.** Password-based key derivation có yêu cầu khác (mức tốn CPU/bộ nhớ, salt, chính sách chống brute-force). Không dùng ví dụ HKDF như công thức xử lý mật khẩu.

Độ ổn định của API đã cao, nhưng **chi phí bảo mật** vẫn có thể cao nếu mã cũ có format, provider hoặc protocol khác. Chỉ thay phương pháp dẫn xuất khóa khi có test vector, tính tương thích giao thức và review bảo mật.

## 9. Đánh giá AOT cache và cải tiến warmup thực tế

JDK 25 tiếp tục các cải tiến AOT nhằm giảm thời gian khởi động và làm nóng ứng dụng. Hai JEP đáng chú ý:

- **JEP 514 — Ahead-of-Time Command-Line Ergonomics:** giúp workflow tạo cache thuận tiện hơn.
- **JEP 515 — Ahead-of-Time Method Profiling:** cung cấp dữ liệu profile từ lần chạy trước để hỗ trợ tối ưu hóa warmup/JIT.

Chúng không biến JVM thành một chương trình native image và cũng không đảm bảo mọi ứng dụng tăng tốc như nhau.

### 9.1. Mẫu thử AOT cache

Với một ứng dụng Java đóng gói thành `app.jar` trên JDK 25, có thể thử:

~~~bash
# Giai đoạn training: chạy workload đại diện, dừng ứng dụng có kiểm soát.
java -XX:AOTCacheOutput=app.aot -jar app.jar

# Giai đoạn deployment thử nghiệm: tái sử dụng cache đã tạo.
java -XX:AOTCache=app.aot -jar app.jar
~~~

Lệnh đầu tạo cache khi quá trình training và assembly hoàn tất, theo cơ chế JDK 25. Với server chạy lâu dài, phải cho nó chạy qua startup và luồng nghiệp vụ cần đại diện, rồi kết thúc có kiểm soát để tạo cache. Không giả định chỉ gọi lệnh là cache xuất hiện ngay trong khi server vẫn đang chạy.

### 9.2. Các điều kiện bắt buộc

- Cache liên quan tới **bản ứng dụng/JDK/OS/CPU và các tùy chọn JVM**. Thay một trong các yếu tố có thể yêu cầu tạo lại cache hoặc làm cache không dùng được.
- Training phải đại diện cho class loading và luồng khởi động thực tế, nhưng không được đưa dữ liệu khách hàng hoặc secret thật vào tập training.
- So sánh **cùng app jar, cùng JDK 25, cùng container resources**: chạy không cache rồi chạy có cache.
- Ghi nhận cả `time-to-ready`, startup p50/p95, warmup throughput, RSS, CPU và chi phí tạo/lưu/phân phối cache.
- Thực hiện rollback bằng cách chạy lại cùng ứng dụng không có cờ cache nếu kết quả không đạt; tránh thay nhiều JVM flags trong cùng một phép thử.

Nếu workload server phải chạy 24/7 và startup rất hiếm, lợi ích AOT cần được cân nhắc với phức tạp CI/CD. Ngược lại, serverless, scale-out nhanh hoặc batch jobs có thể hưởng lợi nhiều hơn.

### 9.3. Đánh giá lợi ích ròng

Một thay đổi AOT chỉ đáng triển khai khi:

~~~text
Lợi ích đo được trong giai đoạn khởi động/warmup
  > chi phí tạo cache + lưu trữ/phân phối + tăng độ phức tạp deploy
    + rủi ro cache không tương thích + công sức vận hành
~~~

Công thức chỉ là khung suy nghĩ, không yêu cầu quy mọi lợi ích thành một số tiền. Nếu ứng dụng đang vi phạm startup SLO, ngay cả cải tiến nhỏ cũng có thể quan trọng. Nếu startup đã tốt, chi phí tạo cache có thể vượt lợi ích.

## 10. Đánh giá JFR, profiling và cải tiến VM

Java Flight Recorder (JFR) vẫn là công cụ quan trọng để điều tra hiệu năng JVM; Java 25 có một số cải tiến ở mảng profiling/monitoring, chẳng hạn JEP 518 và 520. JEP 509 (**CPU-Time Profiling**) ở trạng thái **experimental trong JDK 25**: chỉ dùng thử với phạm vi và platform được hỗ trợ, không coi là lời giải đo CPU mặc định cho mọi môi trường.

### 10.1. Chụp baseline bằng JFR

Ví dụ dùng `jcmd` và `jfr` của JDK phù hợp:

~~~bash
# Xác định PID bằng jcmd -l hoặc công cụ quản lý process.
jcmd -l

# Ví dụ PID là 12345: ghi 120 giây để phân tích.
jcmd 12345 JFR.start name=upgrade-baseline settings=profile duration=120s filename=baseline.jfr

# Xem thông tin ghi nhận.
jfr summary baseline.jfr
~~~

Các số 12345 và tên tệp chỉ là ví dụ. Cần quyền truy cập tiến trình JVM và đường dẫn file có quyền ghi phù hợp. Với hệ thống production, JFR file có thể chứa stack, class name, hostname hoặc thông tin vận hành; phải phân quyền và xử lý retention theo chính sách.

Khi dùng JFR Method Timing & Tracing (JEP 520), nên giới hạn vào các method thực sự cần điều tra; instrumentation rộng có thể làm tăng overhead. So sánh throughput/latency khi có và không có cấu hình ghi chi tiết.

### 10.2. Đánh giá Compact Object Headers và GC

JEP 519 thay đổi cách bố trí object headers, có thể ảnh hưởng footprint của ứng dụng tạo rất nhiều object. Một số cải thiện memory/GC có thể đến từ JDK mới mà **không thay source code**, nhưng vẫn cần đo.

Khi đánh giá một collector như Generational Shenandoah (JEP 521), cần xét workload latency, throughput, CPU budget và heap size. Không dùng GC mới chỉ vì tên tính năng có mặt trong JDK 25; phải so sánh với collector baseline trong đúng môi trường triển khai và trên bản phân phối JDK đang dùng.

### 10.3. Kết quả benchmark phải đủ tin cậy

Một bản benchmark tối thiểu cần ghi:

| Điều kiện | Ghi nhận |
| --- | --- |
| JDK | Vendor, exact `java -version` build |
| App | Commit/artifact checksum, dependencies |
| Môi trường | OS, CPU, RAM, container limits |
| JVM flags | GC, heap, JFR, AOT và flag khác |
| Tải | Request mix, concurrency, data size |
| Warmup | Cách làm nóng và thời điểm đo |
| Kết quả | Median, p95/p99, variation, error rate |
| Chi phí | RSS, CPU, cache artifact, CI duration |
| Kết luận | Có đạt ngưỡng đã đặt trước không? |

Không lấy một con số benchmark JEP trên workload tổng hợp để cam kết tương tự với ứng dụng có database/network dependency nặng.

## 11. Kiểm tra tương thích trước khi nâng JDK

Độ ổn định của một JEP chỉ là một phần. Một ứng dụng đang chạy có thể chịu ảnh hưởng của thay đổi runtime, giới hạn truy cập JDK internals, phản xạ, bytecode instrumentation hoặc thư viện native.

### 11.1. Kiểm kê nền tảng

Bắt đầu bằng danh sách được ghi lại từ môi trường đang vận hành:

~~~text
Ứng dụng: order-service
JDK hiện tại: Java 21 (vendor + exact build)
JDK mục tiêu: Java 25 (vendor + exact build)
OS/container: Linux x86-64, image được pin digest
Build: Maven/Gradle version, compiler plugin, annotation processors
Framework: Spring Boot, Hibernate, database driver
Agents: JFR, tracing, monitoring, security agent
Compatibility: các service vẫn dùng Java 17/21, client libraries
Rollback: image hiện tại + config cũ + kế hoạch đổi traffic
~~~

Đây là form mẫu, không phải trạng thái thực của một hệ thống cụ thể. Mục tiêu là tránh “chỉ thay biến `JAVA_HOME`” rồi kết luận đã nâng cấp đầy đủ.

### 11.2. Kiểm tra toolchain

~~~bash
java -version
javac -version
mvn -version
gradle --version
~~~

Nếu dùng Maven Wrapper hoặc Gradle Wrapper, ưu tiên lệnh wrapper của dự án để bảo đảm người chạy CI có cùng phiên bản. Với Maven, có thể điều khiển mức API nguồn bằng cấu hình compiler:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
~~~

Đây là ví dụ **khi chủ động biên dịch code Java 25**. Nếu cần artifact vẫn chạy trên Java 21, giữ `--release 21` và **không** dùng API Java 25 trong source chung; đừng nhầm “JDK dùng để chạy compiler là 25” với “bytecode và thư viện mục tiêu là Java 25”.

### 11.3. Phát hiện JDK internal API và API bị khuyến cáo thay thế

Các công cụ hiện hành của JDK có thể hỗ trợ phân tích tĩnh:

~~~bash
# Tìm tham chiếu đến API nội bộ của JDK.
jdeps --jdk-internals app.jar

# Kiểm tra việc sử dụng API deprecated theo release mục tiêu.
jdeprscan --release 25 app.jar
~~~

Kết quả phải được đọc trong bối cảnh dependencies thực tế. `jdeps` chỉ phát hiện được những tham chiếu mà phân tích tĩnh thấy; reflection hoặc code tạo động có thể không xuất hiện. `jdeprscan` và cảnh báo compiler giúp lập danh sách thay đổi, nhưng không thể thay integration tests.

Cần rà soát thêm:

- Bytecode/agent libraries (mocking, instrumentation, APM, code coverage).
- Annotation processors, Lombok hoặc plugin build còn hỗ trợ compiler mới.
- TLS, certificates, keystore formats và security provider.
- Native libraries/JNI/FFM và CPU architectures.
- Container base images, timezone data, charset và locale.
- JVM flags đã bị bỏ hoặc thay đổi hành vi.
- GC, memory sizing, startup và JFR profiling.

Tránh khôi phục khả năng truy cập JDK internals một cách vô hạn bằng `--add-opens` hoặc `--add-exports` nếu có giải pháp API công khai; nếu buộc phải dùng, cần ghi rõ dependency nào yêu cầu, thời hạn gỡ và test khi nâng JDK tiếp theo.

### 11.4. Ma trận test mục tiêu

| Tầng | Ví dụ | Điều kiện đạt |
| --- | --- | --- |
| Unit | Logic domain, constructor, collections | Kết quả giống baseline |
| Integration | Database, message broker, REST client | Transaction và serialization giữ nguyên |
| Security | TLS/crypto provider, token handling | Không đổi giao thức ngoài ý muốn |
| Build | Compile/package/test, reflection, agents | Không có lỗi plugin/bytecode |
| Contract | HTTP/JSON, message schema, gRPC | Consumer cũ vẫn tương thích |
| Performance | Load test, JFR, AOT, GC | Không vượt budget latency/CPU/memory |
| Deployment | Container image, readiness, startup | Rollout/rollback có thể thực hiện |
| Observability | Logs, metrics, traces, JFR | Không mất tín hiệu chẩn đoán, không lộ secret |

Đừng để một bài test mới dùng feature Java 25 làm mất khả năng chạy các module hoặc công cụ vẫn phải tương thích với runtime cũ.

## 12. Một khung chấm điểm có cổng loại trừ

**Cổng loại trừ (hard gates)** được xem trước khi chấm điểm:

- Tính năng chưa final và chính sách production không cho phép preview/incubator/experimental.
- Toolchain, framework hoặc JDK distribution không hỗ trợ triển khai mục tiêu.
- Không có test để chứng minh tính tương thích hoặc có vi phạm bảo mật.
- Không xác định được rollback khi xảy ra sự cố nghiêm trọng.
- Chi phí đo đạc/cơ sở hạ tầng vượt ngân sách bắt buộc.

Nếu không qua bất kỳ cổng nào, lựa chọn là **thử nghiệm có giới hạn** hoặc **hoãn áp dụng**, không dùng điểm số tổng để hợp thức hóa rủi ro.

Sau đó, chấm mỗi tiêu chí từ 1 đến 5. Gợi ý:

| Tiêu chí | 1 điểm | 3 điểm | 5 điểm |
| --- | --- | --- | --- |
| Độ ổn định và hỗ trợ | Chưa rõ hoặc experimental | Final nhưng ecosystem chưa đủ chứng cứ | Final, runtime/vendor/toolchain đã kiểm chứng |
| Lợi ích thực tế | Không có số liệu | Có PoC và tín hiệu tích cực | Có benchmark/test trên workload đại diện, đạt mục tiêu |
| Chi phí chuyển đổi thấp | Refactor lớn, nhiều phụ thuộc | Sửa có giới hạn và có test | Thay đổi nhỏ, rollback đơn giản |
| Rủi ro vận hành thấp | Dễ gây outage hoặc dữ liệu nhạy cảm | Cần canary và kiểm soát | Không ảnh hưởng đường trọng yếu, có giám sát rõ |
| Khả năng duy trì | Tăng phụ thuộc phiên bản/công cụ | Team có thể học và vận hành | Có tài liệu, owner, test, kế hoạch update |

Điểm tổng tham khảo:

~~~text
Score = 0.30 × Stability
      + 0.30 × Benefit
      + 0.20 × LowMigrationCost
      + 0.10 × LowOperationalRisk
      + 0.10 × Maintainability
~~~

Lưu ý `LowMigrationCost` và `LowOperationalRisk` càng **cao** thì chi phí/rủi ro càng thấp, để điểm tổng tăng theo hướng tốt. Trọng số chỉ là ví dụ. Nhóm nên điều chỉnh cho hệ thống thanh toán/bảo mật, dịch vụ latency-sensitive hoặc chương trình học tập.

Không cần ngưỡng cứng một cách máy móc, nhưng có thể quy ước:

- **4,0–5,0** và qua hard gates: ưu tiên thử canary, đo sau rollout.
- **3,0–dưới 4,0:** thử PoC/benchmark thêm, chỉ triển khai khi lợi ích đáng kể.
- **Dưới 3,0:** hoãn hoặc chỉ thử trong môi trường lab.

Một tính năng final không tự nhận 5 điểm ở “lợi ích”; phải có dữ liệu thật.

### Ví dụ ghi phiếu đánh giá

~~~yaml
feature: "AOT cache cho service khởi động thường xuyên"
targetJdk: "25 - vendor/build xác định trong CI"
lifecycleAtTargetJdk: "delivered"
problem: "time-to-ready p95 vượt mục tiêu"
baseline:
  startupP95Seconds: 4.0
candidate:
  startupP95Seconds: 3.0
risk:
  - "Cache phụ thuộc phiên bản JDK và artifact"
  - "Training phải đại diện cho startup thực"
  - "Tăng thời gian CI và kích thước artifact"
decision: "Canary; không bật cho mọi service ngay"
acceptance: "p95 giảm >= 15%, CPU/RSS không tăng quá ngân sách"
rollback: "Bỏ cờ -XX:AOTCache và sử dụng image chuẩn"
~~~

Phiếu YAML trên chỉ là **mẫu ghi quyết định** trong bài học, không phải format chuẩn của Oracle, OpenJDK hay tool cần được thêm vào repository.

## 13. Case study: chuyển dịch vụ từ Java 21 lên Java 25

Một nhóm có 12 service Spring Boot trên Java 21. Chỉ ba service có startup p95 chậm, một service có dùng `ThreadLocal` để chứa request context và nhiều service sử dụng library crypto đã được kiểm chứng.

### Phương án A — Áp dụng mọi tính năng một lần

Nhóm cập nhật Java 25, thay code constructor trên diện rộng, viết lại context propagation, đổi GC, chuyển crypto, bật AOT cho tất cả service, đồng thời bật các preview API mới. Kết quả: quá nhiều biến số cùng thay, khó xác định nguyên nhân khi lỗi xảy ra.

Đây là phương án **không nên chọn** theo nguyên tắc đánh giá.

### Phương án B — Tách nâng runtime khỏi adoption

**Giai đoạn 1: chuẩn hóa nền tảng.** Kiểm tra JDK vendor, roadmap hỗ trợ, build plugins, Spring Boot/driver tương thích; chạy test và canary trên Java 25 mà không thay API nghiệp vụ.

**Giai đoạn 2: ưu tiên theo điểm nghẽn.** Thử AOT cache ở ba service startup chậm, đo p95 trên workload đại diện. Không bật cho chín service chưa có vấn đề startup.

**Giai đoạn 3: cải thiện code có mục tiêu.** Chỉ đánh giá `ScopedValue` ở nơi đang có vấn đề vòng đời `ThreadLocal` và có test context propagation. Không refactor framework integration đã hoạt động nếu chưa có lợi ích được đo.

**Giai đoạn 4: cập nhật security/diagnostics.** Dùng `KDF` khi thực sự cần dẫn xuất khóa và có security review; dùng JFR để định vị CPU/memory bottleneck. Không tự triển khai thuật toán cryptography mới chỉ vì muốn tận dụng API mới.

**Giai đoạn 5: giữ preview trong phòng thí nghiệm.** Theo dõi Structured Concurrency, Vector API hoặc các preview khác bằng PoC không nằm trên đường sản phẩm bắt buộc; đánh giá lại trạng thái trên JDK mới nếu sau này muốn triển khai.

Bài học: giá trị chính của nâng cấp không phải “đã dùng tất cả JEP”, mà là **chuyển sang runtime được hỗ trợ, giảm rủi ro và giải quyết những vấn đề có bằng chứng**.

### Một bảng quyết định minh họa

| Hạng mục | Mức độ ưu tiên | Quyết định |
| --- | --- | --- |
| Runtime Java 25 và security updates | Cao | Nâng khi ecosystem và smoke/load test đạt |
| AOT cho 3 service khởi động chậm | Trung bình–cao | Canary theo kết quả đo |
| `ScopedValue` ở 1 module có bug context | Trung bình | PoC và test propagation trước |
| Compact source cho CLI nội bộ | Thấp | Áp dụng nơi có lợi ích dễ đọc |
| Refactor mọi constructor | Thấp | Không làm chỉ vì cú pháp mới |
| Vector API incubator | Không phải production baseline | Chỉ benchmark chuyên biệt |
| CPU-Time JFR experimental | Theo sự cố | Thử có kiểm soát trên platform phù hợp |

## 14. Quy trình rollout và rollback có thể kiểm chứng

Một luồng công việc khuyến nghị:

~~~mermaid
flowchart TD
    A["Inventory JDK/vendor/dependencies"] --> B["Chọn target JDK 25 và hard gates"]
    B --> C["Run test với runtime mới, giữ code cũ"]
    C --> D{"Regression?"}
    D -->|Có| E["Sửa tương thích / dừng rollout"]
    D -->|Không| F["PoC riêng từng JEP cần lợi ích"]
    F --> G["Benchmark, bảo mật, vận hành"]
    G --> H{"Có bằng chứng đạt?"}
    H -->|Không| I["Không áp dụng feature"]
    H -->|Có| J["Canary và quan sát"]
    J --> K{"SLO và test ổn?"}
    K -->|Không| L["Rollback image/flags"]
    K -->|Có| M["Mở rộng có kiểm soát và ghi ADR"]
~~~

Một lần rollout nên thay đổi ít biến số nhất có thể. Ví dụ:

1. Chạy production canary với **chỉ thay JDK runtime**.
2. Sau khi ổn định, thử **chỉ AOT cache** ở một service phù hợp.
3. Sau đó mới xem xét refactor `ScopedValue` ở phạm vi nhỏ.
4. Với JFR, có thể thực hiện profiling có thời hạn không làm thay source code.
5. Nếu thử GC mới, tách đợt với rollout AOT để tránh khó phân tích số liệu.

Theo dõi ít nhất startup p95, error rate, latency p95/p99, memory RSS, CPU, GC pause, crash/restart, connection pool, TLS failures và tracing/exporter errors. Giữ artifact/container image trước nâng cấp để rollback đáng tin cậy.

Không rollback bằng cách xóa tạm lỗi test hoặc bật `--add-opens` tràn lan mà không đánh giá hậu quả; cần quản lý compatibility exception rõ thời hạn.

## 15. Những sai lầm khi đánh giá tính năng

### “LTS nghĩa là mọi JEP ổn định”

Sai. Dòng JDK và trạng thái một tính năng là hai vấn đề khác nhau. Java 25 LTS vẫn có preview/incubator/experimental được công bố rõ.

### “Không dùng preview thì Java 25 không có giá trị”

Sai. Nền tảng runtime, các tính năng đã final, công cụ JFR, cải tiến VM/JIT/AOT và cập nhật bảo mật có thể có giá trị mà không cần preview.

### “Final nghĩa là chắc chắn nhanh hơn”

Sai. Một cú pháp final có thể là cải tiến khả năng diễn đạt chứ không phải performance. Với VM/JFR/AOT, hiệu quả phụ thuộc workload và cấu hình.

### “Cập nhật JDK thì phải nâng luôn source level lên 25”

Sai. Nếu cần duy trì compatibility với Java 21, có thể dùng compiler/JDK mới nhưng cấu hình `--release 21` và chỉ sử dụng API target đó. Khi chủ động dùng API Java 25, phải chấp nhận artifact yêu cầu runtime phù hợp.

### “AOT cache giống native image, dùng ở mọi máy đều được”

Sai. Cache liên quan bản ứng dụng, JDK/platform và tùy chọn liên quan. Phải dựng cache theo chính sách build/triển khai và đo lợi ích.

### “ScopedValue thay thế mọi ThreadLocal”

Sai. `ScopedValue` phù hợp với dữ liệu ngữ cảnh có scope và giá trị binding bất biến, nhưng không có cùng semantics với mọi kiểu mutable thread-local state.

### “JFR bật rộng không ảnh hưởng hiệu năng”

Sai. JFR thường có các chế độ ít overhead, nhưng tracing/timing method chi tiết hoặc event đặc biệt vẫn cần benchmark và giới hạn phạm vi. Tính năng CPU-time experimental không nên mặc định bật cho mọi môi trường.

### “Chỉ cần unit tests xanh là đủ”

Sai. JDK upgrade có thể ảnh hưởng reflection, agent, TLS, native library, GC và runtime flags. Cần integration/performance/canary.

### “Giấy phép Java giống nhau trên mọi vendor/bản update”

Sai. Đánh giá giấy phép và thời hạn hỗ trợ theo distribution, phiên bản cập nhật, kiểu sử dụng và hợp đồng. Không suy từ nhãn LTS ra quyền sử dụng tự do vĩnh viễn.

## 16. Mẫu ADR ngắn để chốt quyết định nâng cấp

Một bản ghi quyết định kỹ thuật (*Architecture Decision Record*, ADR) không cần dài, nhưng phải cho người khác biết **vì sao**, **bằng chứng nào** và **khi nào phải xem lại**.

~~~markdown
# ADR: Đánh giá [tên tính năng Java 25]

- Ngày / người phụ trách:
- JDK vendor, build, OS/architecture:
- Nguồn JEP/API chính thức:
- Trạng thái tại phiên bản JDK mục tiêu:
- Vấn đề và SLO/tiêu chí chất lượng muốn cải thiện:
- Phương án baseline:
- Phương án dùng tính năng:
- Hard gates: pass/fail và giải thích
- Lợi ích đo được: p50/p95, CPU, RAM hoặc chỉ số chất lượng code
- Chi phí một lần, chi phí vận hành thường xuyên:
- Rủi ro bảo mật, tương thích và phương án dự phòng:
- Quyết định: áp dụng / PoC tiếp / hoãn
- Kế hoạch canary, rollback:
- Ngày/điều kiện đánh giá lại:
~~~

Có thể dùng mẫu này cho ba kiểu quyết định rất khác nhau:

- **Chọn JDK 25 runtime:** quan trọng nhất là compatibility, support, security updates, vận hành.
- **Dùng tính năng source final:** quan trọng nhất là khả năng đọc, hỗ trợ toolchain và target bytecode/API.
- **Dùng tối ưu hóa VM hoặc tooling:** quan trọng nhất là benchmark, platform, flags, chi phí triển khai và chẩn đoán.

Đừng biến ADR thành giấy phép để bỏ test. Mỗi điều kiện được chấp thuận cần có lệnh chạy, báo cáo hoặc một bằng chứng có thể kiểm tra lại.

## 17. Bài thực hành: chọn tính năng cho một hệ thống giả định

### Đề bài

Bạn phụ trách một dịch vụ quản lý đơn hàng đang chạy Java 21, dùng Spring Boot, PostgreSQL và một hệ thống metrics/tracing. Nhóm muốn lên Java 25 vì kế hoạch hỗ trợ dài hạn. Những vấn đề đang được báo cáo:

- Startup p95 cao hơn yêu cầu khi scale-out.
- Có một module tự làm HKDF bằng utility nội bộ.
- Một số request context dùng `ThreadLocal` và bị quên dọn trong đường xử lý lỗi.
- Team muốn viết lại toàn bộ class main và constructor để “trông giống Java 25”.
- Một thành viên muốn bật mọi JFR event mới và preview feature ngay trên production.

### Nhiệm vụ

1. **Lập inventory:** ghi JDK vendor/build, build tool, framework, drivers, agents, OS/CPU và target support policy.
2. **Chia hai quyết định:** nâng runtime Java 25 riêng, áp dụng từng feature riêng.
3. **Phân loại độ ổn định:** với `ScopedValue`, `KDF`, compact source, constructor bodies, AOT và JFR; chỉ rõ preview/experimental cần giới hạn.
4. **Xây bảng lợi ích:** đề xuất baseline startup, CPU, memory, error rate và các kiểm thử context.
5. **Xác định hard gates:** library compatibility, licensing, security, rollback, canary.
6. **Thử AOT cache trong lab:** chạy workload đại diện, đo startup với/không có cache, không dùng dữ liệu khách hàng thật.
7. **Đánh giá `ScopedValue`:** viết một PoC nhỏ với scope bất biến, kiểm tra ngoài scope và luồng async thực tế; không thay mọi `ThreadLocal`.
8. **Đánh giá `KDF`:** đối chiếu API chuẩn với test vectors và cấu hình provider; mời review bảo mật trước khi thay crypto nội bộ.
9. **Xây ma trận quyết định:** chọn một cải tiến để canary, một cải tiến để chỉ PoC và một thay đổi nên hoãn.
10. **Viết ADR:** mỗi kết luận phải có lý do và cách quan sát hậu triển khai.

### Gợi ý kết quả kỳ vọng

| Đề xuất | Kết luận có thể hợp lý |
| --- | --- |
| Nâng runtime 21 → 25 | Ưu tiên nếu toolchain/framework và deployment matrix đạt |
| AOT cho service khởi động chậm | PoC/benchmark, sau đó canary khi chứng minh lợi ích |
| `ScopedValue` cho context bị rò | Refactor nhỏ có test vòng đời và async propagation |
| `KDF` thay utility HKDF tự viết | Ưu tiên review security và compatibility trước |
| Compact main cho toàn bộ Spring Boot | Không cần thiết vì không giải quyết pain point |
| Đổi mọi constructor sang cú pháp mới | Hoãn nếu không có lỗi/thiếu rõ ràng cần giải quyết |
| Bật JFR CPU-time experimental ở mọi pod | Không làm; chỉ thử có giới hạn khi cần chẩn đoán |
| Preview API cho code production chủ lực | Hoãn theo chính sách, kiểm tra trạng thái trên JDK mục tiêu |

Kết quả không cần giống mọi dòng trong bảng. Một quyết định khác vẫn có thể đúng nếu có **bằng chứng đo được, cổng rủi ro rõ ràng và phương án rollback**.

### Câu hỏi tự đánh giá

1. Java 25 là LTS có đồng nghĩa tất cả JEP trong 25 là final không?
2. Tại sao nên tách nâng JVM runtime khỏi refactor source để dùng JEP mới?
3. Khi nào `--release 21` có ích dù build đang dùng JDK 25?
4. Vì sao `ScopedValue` không phải replacement một-một cho mọi `ThreadLocal`?
5. Tại sao ứng dụng khởi động rất ít có thể không cần AOT cache?
6. Với `KDF`, vì sao API final vẫn cần threat model và test vector?
7. Preview ở JDK 25 có nhất thiết preview mãi trên các JDK sau không?
8. Vì sao điểm lợi ích cao không được vượt qua hard gate về bảo mật hoặc support?
9. Những thay đổi của GC/JVM nào có thể ảnh hưởng ứng dụng mà không sửa source code?
10. Một kết luận “tăng tốc 20%” cần những thông tin gì để người khác tái lập?

## 18. Checklist chấp thuận tính năng Java 25

- [ ] Đã xác nhận JDK vendor, exact build, hệ điều hành, CPU và thời hạn cập nhật bảo mật.
- [ ] Đã xem tài liệu chính thức cho JEP/API **ở JDK đang triển khai**, không dùng bài viết preview cũ làm chuẩn cuối.
- [ ] Tính năng đã final/delivered hoặc có chính sách rõ ràng cho thử nghiệm.
- [ ] Không chọn API đã bị gỡ hoặc tính năng legacy làm nền tảng cho code mới.
- [ ] Đã xác định vấn đề thực tế và chỉ số lợi ích cần cải thiện.
- [ ] Đã giữ baseline, dữ liệu test, môi trường benchmark đủ để tái lập.
- [ ] Đã kiểm tra framework, dependencies, build tools, bytecode agents và native libraries.
- [ ] Đã dùng `jdeps`/`jdeprscan` và test bổ sung cho reflection/runtime behavior.
- [ ] Nếu dùng source Java 25, đã xác định yêu cầu runtime và khả năng tương thích consumer.
- [ ] Nếu dùng crypto API, đã có test vectors, provider review và threat model.
- [ ] Nếu dùng AOT, đã có training representative, chính sách tạo lại cache và fallback không cache.
- [ ] Nếu dùng JFR profiling chi tiết, đã giới hạn phạm vi, kiểm tra overhead và bảo vệ dữ liệu.
- [ ] Đã tính đủ chi phí development, CI/CD, vận hành, đào tạo và rủi ro.
- [ ] Hard gates đạt trước khi tính điểm lợi ích.
- [ ] Đã xác định canary, chỉ số theo dõi và phương án rollback khả thi.
- [ ] Có ADR hoặc tài liệu ngắn ghi quyết định, người chịu trách nhiệm và thời điểm đánh giá lại.

**Nguyên tắc kết luận:** *Sử dụng Java 25* có thể là quyết định nâng nền tảng phù hợp cho hệ thống hiện đại, nhưng *áp dụng từng tính năng Java 25* phải có lý do riêng. Ưu tiên API/cú pháp đã hoàn thiện, có lợi ích thực tế và có test; chỉ dùng preview/incubator/experimental trong phạm vi được phép, đồng thời không phục hồi các kỹ thuật legacy đã bị thay thế. Quyết định tốt là quyết định có bằng chứng, chi phí được tính trước và có thể đảo ngược khi giả định ban đầu không đúng.

## 19. Nguồn tham khảo chính thức và cách cập nhật kiến thức

Các tài liệu bên dưới giúp kiểm tra trạng thái JEP và hành vi **của JDK 25**, không thay thế việc xem compatibility matrix cho vendor và JDK mục tiêu thực tế.

- [Oracle JDK 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): liệt kê các thay đổi đáng chú ý cần xem khi di chuyển.
- [Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): xác nhận nhóm tính năng ngôn ngữ đã hoàn thiện và preview.
- [Oracle JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html): hướng dẫn tương thích, `jdeps`, compiler và kiểm tra trước nâng cấp.
- [Java SE 25 — Preview Features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html): cách bật preview và giới hạn khả năng tương thích giữa releases.
- [JDK 25 — javac command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `--enable-preview` và tùy chọn biên dịch.
- [JDK 25 — java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cờ khởi chạy và AOT cache.
- [Java SE 25 — javax.crypto.KDF](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html): API và các phương thức dẫn xuất khóa.
- [JDK 25 — JFR performance troubleshooting](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): sử dụng JFR để điều tra hiệu năng.
- [OpenJDK Project JDK 25](https://openjdk.org/projects/jdk/25/): danh sách JEP được đưa vào bản phát hành.
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): thời hạn hỗ trợ theo dòng JDK và sản phẩm.
- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506), [JEP 510 — KDF API](https://openjdk.org/jeps/510), [JEP 511 — Module Import Declarations](https://openjdk.org/jeps/511), [JEP 512 — Compact Source Files](https://openjdk.org/jeps/512), [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): nền tảng của các ví dụ tính năng đã hoàn thiện.
- [JEP 514 — AOT Command-Line Ergonomics](https://openjdk.org/jeps/514), [JEP 515 — AOT Method Profiling](https://openjdk.org/jeps/515), [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): tính năng tooling/VM cần đánh giá với workload thực tế.

**Cách giữ tài liệu không lỗi thời:** khi một feature đi qua preview → final ở bản JDK tiếp theo, cập nhật đánh giá dựa trên tài liệu/JEP của bản đó và chạy lại test. Không copy code preview từ release cũ, không lấy release note mới nhất để suy ngược khả năng được hỗ trợ trong Java 25 và không đồng nhất status của API với cam kết support của vendor.



