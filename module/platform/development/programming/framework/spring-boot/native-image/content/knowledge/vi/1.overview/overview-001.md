# Native Image là gì và bài toán khởi động, bộ nhớ mà nó hướng tới

## 1. Vì sao cần quan tâm đến thời gian khởi động và bộ nhớ?

Một ứng dụng Spring Boot chạy trên JVM có nhiều ưu điểm: cùng một tệp JAR có thể chạy trên các hệ điều hành phù hợp, hệ sinh thái thư viện phong phú và JVM có thể tối ưu mã đang chạy bằng JIT (*Just-in-Time compilation*). Tuy nhiên, ở một số mô hình triển khai, việc khởi tạo cả JVM lẫn ứng dụng trở thành một phần chi phí đáng kể.

Hãy xem một dịch vụ REST quản lý đơn hàng. Khi khởi động theo cách truyền thống, tiến trình phải khởi tạo JVM, tải các lớp cần dùng, xây dựng `ApplicationContext`, tạo bean, áp dụng auto-configuration, khởi tạo web server và thực hiện những công việc mà ứng dụng yêu cầu trước khi sẵn sàng nhận request. Khi số lượng tiến trình tăng hoặc tiến trình thường xuyên bị tạo mới, chi phí này có thể xuất hiện nhiều lần.

Hai vấn đề chính là:

- **Thời gian khởi động (startup time):** khoảng thời gian từ khi bắt đầu tiến trình đến khi ứng dụng thực sự sẵn sàng phục vụ. Thời gian này ảnh hưởng tới scale-out, rolling deployment, phục hồi sau lỗi, job chạy ngắn và cold start của workload theo nhu cầu.
- **Bộ nhớ của tiến trình (memory footprint):** lượng bộ nhớ tiến trình cần sử dụng khi nhàn rỗi và khi có tải. Ngoài Java heap còn có bộ nhớ cho runtime, metadata, stack, mã đã biên dịch và các vùng native khác. Trong môi trường container có giới hạn RAM, footprint cao có thể làm giảm số instance triển khai được hoặc làm tăng nguy cơ vượt giới hạn bộ nhớ.

**GraalVM Native Image** là một lựa chọn nhằm tối ưu hai đặc điểm này. Kết hợp với **Spring AOT**, ứng dụng Spring Boot có thể được biên dịch trước thành mã máy và đóng gói thành tệp thực thi native cho một hệ điều hành và kiến trúc CPU cụ thể.

> Mục tiêu của Native Image không phải là bảo đảm mọi ứng dụng chạy nhanh hơn trên mọi tiêu chí. Giá trị nổi bật thường nằm ở thời gian khởi động, mức tiêu thụ bộ nhớ và khả năng chạy ngay trong những môi trường có vòng đời tiến trình ngắn.

## 2. GraalVM Native Image là gì?

**Native Image** là công nghệ biên dịch *ahead-of-time* (AOT) trong hệ sinh thái GraalVM. Thay vì chỉ phân phối bytecode `.class`/`.jar` để JVM biên dịch và thực thi khi chạy, quá trình build phân tích phần mã ứng dụng có thể được sử dụng, biên dịch trước thành mã máy, rồi liên kết thành một tệp thực thi cho nền tảng đích.

Ví dụ về hình thức chạy:

```bash
# Cách thông thường: cần Java runtime phù hợp trên máy chạy
java -jar target/order-service.jar

# Cách native: chạy trực tiếp tệp thực thi đã được build cho nền tảng này
./target/order-service
```

Lệnh và tên artifact chỉ mang tính minh họa; đường dẫn đầu ra thực tế phụ thuộc cấu hình dự án và hệ điều hành. Trên Windows, tệp thực thi native thường có đuôi `.exe`.

### 2.1. So sánh đường đi từ mã nguồn đến lúc chạy

| Khía cạnh | Ứng dụng Spring Boot chạy trên JVM | Ứng dụng Spring Boot Native Image |
|---|---|---|
| Artifact chính | JAR chứa bytecode và tài nguyên | Tệp thực thi mã máy cho OS/CPU đích |
| Lúc build | Biên dịch Java/Kotlin thành bytecode, đóng gói JAR | Thêm Spring AOT, phân tích mã có thể sử dụng, biên dịch và liên kết native |
| Lúc chạy | JVM tải lớp, quản lý runtime và có thể dùng JIT | Chạy mã máy đã biên dịch trước cùng runtime gọn hơn được đóng vào executable |
| Tính linh hoạt | Việc tải lớp và một số hành vi động được JVM hỗ trợ trực tiếp | Cần khai báo trước những phần động mà trình phân tích không phát hiện được |
| Khởi động | Có thêm công việc của JVM và khởi tạo ứng dụng | Thường nhanh hơn vì nhiều bước đã được xử lý ở build time |
| Bộ nhớ | Bao gồm các vùng nhớ của JVM và ứng dụng | Thường có footprint thấp hơn trong nhiều workload, nhưng vẫn có heap, stack và GC |
| Tối ưu thời gian chạy dài | JIT có thể thích nghi với mã và tải thực tế | Không hưởng lợi từ JIT của JVM trong quá trình chạy; throughput cần đo riêng |
| Tính di động artifact | JAR có thể chạy trên các JVM tương thích | Cần artifact tương ứng với OS, CPU và thư viện hệ thống liên quan |

Native Image **không** đơn thuần là nén JAR thành một tệp và cũng không chuyển ứng dụng Java sang một ngôn ngữ lập trình khác. Tệp thực thi vẫn mang theo các thành phần runtime cần thiết, chẳng hạn cơ chế cấp phát đối tượng, quản lý bộ nhớ, thu gom rác và hỗ trợ luồng. Vì vậy, "không cần cài JVM riêng để chạy" không có nghĩa là "không có runtime" hay "không có garbage collector".

### 2.2. Ba khái niệm AOT dễ nhầm lẫn

**AOT (Ahead-of-Time)** là cách gọi chung cho việc xử lý hoặc biên dịch trước khi chương trình thực thi. Trong một dự án Spring Boot native, cần phân biệt:

1. **Spring AOT:** phân tích cấu hình Spring tại build time và sinh mã/metadata phục vụ việc tạo `ApplicationContext`, đăng ký bean, proxy, reflection hoặc resource cần thiết. Nó giúp chuyển những quyết định có thể xác định sớm sang giai đoạn build và mô tả các hành vi động cho trình biên dịch.
2. **GraalVM Native Image:** phân tích khả năng truy cập mã (*reachability analysis*), biên dịch những phần cần thiết thành mã máy và tạo executable native.
3. **JIT của JVM:** tối ưu, biên dịch mã trong lúc chương trình đang chạy dựa trên những gì runtime quan sát được. Đây là một chiến lược khác, có thể mang lại lợi thế cho ứng dụng chạy lâu và xử lý tải lớn.

Spring AOT và GraalVM Native Image bổ trợ cho nhau: Spring AOT xử lý nhiều đặc thù framework, còn GraalVM tạo chương trình native.

```mermaid
flowchart LR
    A["Mã nguồn và cấu hình Spring Boot"] --> B["Biên dịch bytecode"]
    B --> C["Spring AOT: sinh mã và metadata"]
    C --> D["GraalVM Native Image: phân tích và biên dịch"]
    D --> E["Executable native cho OS/CPU đích"]
    E --> F["Khởi chạy và phục vụ request"]
```

Sơ đồ giản lược các bước; plugin build thực tế điều phối nhiều tác vụ tạo mã, xử lý dependency và liên kết thư viện.

## 3. Native Image cải thiện startup bằng cách nào?

### 3.1. Chi phí khi khởi động trên JVM

Khi chạy một Spring Boot JAR, JVM và framework thường thực hiện một số công việc sau:

1. Khởi tạo runtime, class loader và các cấu trúc cần thiết để thực thi Java.
2. Tải, liên kết và khởi tạo các lớp khi cần.
3. Phân tích cấu hình Spring, xác định bean và xây dựng `ApplicationContext`.
4. Khởi tạo những thành phần thiết yếu như web server, connection pool hoặc client kết nối bên ngoài.
5. Đưa ứng dụng tới trạng thái có thể phục vụ request; JIT có thể tiếp tục tối ưu các đường mã được gọi nhiều sau đó.

Không phải tất cả bước trên đều diễn ra tuần tự hoặc chỉ diễn ra lúc khởi động. Tuy nhiên, chúng cho thấy startup gồm cả công việc của JVM **và** công việc của chính ứng dụng.

### 3.2. Công việc được chuyển sang lúc build

Với Native Image, GraalVM biên dịch trước phần lớn mã có thể xác định được và đóng gói các dữ liệu runtime cần thiết. Spring AOT giúp tạo sẵn nhiều cấu trúc vốn thường phải phát hiện lúc chạy. Do đó, khi tiến trình native bắt đầu, nó có thể bỏ qua một phần chi phí nạp, phân tích và biên dịch mã động của cách chạy truyền thống.

Tuy vậy, **Native Image không loại bỏ mọi công việc startup**. Kết nối database, đọc cấu hình runtime, khởi tạo cache, chạy migration, tạo connection pool hoặc gọi dịch vụ ngoài vẫn tốn thời gian. Một ứng dụng bị chậm vì DNS hay database chưa sẵn sàng sẽ không tự nhiên hết chậm nhờ AOT.

### 3.3. Định nghĩa đúng "khởi động xong"

Khi so sánh hai bản build, phải chọn cùng một mốc đo:

| Mốc đo | Diễn giải | Lưu ý |
|---|---|---|
| Process start | Hệ điều hành bắt đầu tạo tiến trình | Đây là mốc bắt đầu đo, chưa nói ứng dụng đã sẵn sàng |
| Spring context started | Framework đã đi qua một số giai đoạn khởi tạo | Log `Started ... in ... seconds` hữu ích nhưng không thay thế hoàn toàn readiness |
| Application ready | `ApplicationReadyEvent` được phát ra | Phản ánh lifecycle của Spring; phụ thuộc các tác vụ ứng dụng thực hiện |
| Readiness đạt yêu cầu | Health/readiness endpoint trả kết quả mong muốn | Phù hợp để đo thời gian tới khi nhận traffic, nếu endpoint được cấu hình đúng |
| First successful request | Request nghiệp vụ đầu tiên hoàn tất thành công | Bao gồm ảnh hưởng của kết nối và phần khởi tạo trì hoãn khi request đầu tiên đến |

Với môi trường Kubernetes hoặc autoscaling, **thời gian từ process start đến readiness** thường gần với câu hỏi vận hành "bao lâu instance mới nhận được traffic?". Với batch job, cần đo cả thời gian thực thi xong công việc, vì startup nhanh nhưng xử lý chậm hơn chưa chắc là lựa chọn tốt.

## 4. Native Image hướng tới giảm phần bộ nhớ nào?

### 4.1. Bộ nhớ của một ứng dụng Java không chỉ là heap

Một tiến trình Spring Boot trên JVM có thể sử dụng:

- **Java heap:** nơi chứa phần lớn đối tượng Java do ứng dụng tạo.
- **Metaspace / metadata và các vùng runtime:** thông tin lớp, cấu trúc của JVM và dữ liệu phục vụ quản lý runtime.
- **Code cache:** nơi chứa mã máy được JIT biên dịch (nếu có).
- **Thread stack:** bộ nhớ stack của các luồng.
- **Native allocations / thư viện hệ thống:** bộ đệm, vùng nhớ dùng bởi thư viện native, mạng, TLS, compression và các thành phần khác.

Native Image thường giảm được một số chi phí runtime liên quan đến tải lớp và JIT, đồng thời tránh mang theo một JVM đầy đủ như khi chạy JAR. Nhưng **heap, thread stack, cấp phát native và garbage collection vẫn tồn tại**. Mức tiết kiệm thực tế phụ thuộc framework, thư viện, số lượng luồng, cache, tải và cấu hình GC.

### 4.2. Phân biệt các chỉ số thường gặp

| Chỉ số | Đang đo gì? | Dễ hiểu sai ở đâu? |
|---|---|---|
| Heap used | Dung lượng đối tượng đang dùng trong Java heap | Không phải toàn bộ RAM của tiến trình |
| Heap committed / max | Dung lượng heap đã cam kết / giới hạn cho heap | Không đồng nghĩa RSS hay RAM vật lý đang dùng |
| RSS (*Resident Set Size*) | Số trang bộ nhớ vật lý hiện nằm trong RAM và gắn với tiến trình | Có thể bao gồm trang chia sẻ; không thể dùng để kết luận riêng phần heap |
| Peak RSS | Mức RSS cao nhất ghi nhận trong khoảng đo | Không phản ánh đầy đủ đường biến thiên, nhưng hữu ích khi đặt memory limit |
| Container memory usage | Lượng bộ nhớ được môi trường container/cgroup hạch toán | Có thể bao gồm page cache và những loại bộ nhớ khác tùy chỉ số/công cụ |

Ví dụ, nếu bản native báo heap thấp hơn, chưa đủ để kết luận container sẽ giảm tương ứng từng ấy RAM. Cần kiểm tra **RSS, peak memory và chỉ số ở cấp container** trong cùng điều kiện.

### 4.3. Khi footprint thấp tạo ra lợi ích kinh tế

Giả sử một node có giới hạn bộ nhớ cố định và cần chạy nhiều service instance. Nếu mỗi instance dùng ít RAM hơn khi nhàn rỗi và ở mức tải mục tiêu, đội vận hành có thể đóng gói được nhiều instance hơn, hoặc đặt resource request/limit thấp hơn sau khi xác minh an toàn. Lợi ích này đặc biệt đáng cân nhắc với nhiều microservice nhỏ, API ít tải nhưng phải luôn sẵn sàng, hoặc workload thường xuyên scale lên rồi giảm xuống.

Không nên suy trực tiếp từ "RAM giảm" sang "chi phí cloud chắc chắn giảm": CPU, cơ chế tính phí, số bản sao tối thiểu, quota và khả năng chịu tải cũng quyết định chi phí thực tế.

## 5. Bài toán phù hợp và những đánh đổi

Native Image phù hợp khi **thời gian chờ instance sẵn sàng** hoặc **RAM cho mỗi instance** là một ràng buộc quan trọng. Một số tình huống tiêu biểu:

| Tình huống | Lý do đáng thử Native Image | Cần kiểm tra thêm |
|---|---|---|
| Function / tác vụ theo sự kiện | Tiến trình được tạo mới thường xuyên; cold start ảnh hưởng độ trễ | Thời gian xử lý toàn bộ sự kiện và giới hạn nền tảng |
| Microservice scale-out liên tục | Instance sẵn sàng sớm hơn có thể đáp ứng biến động traffic | Thời gian readiness thực tế và khả năng xử lý tải |
| Batch job ngắn | Startup chiếm tỷ trọng lớn trong tổng thời gian chạy | Tổng thời gian job, CPU và tương thích thư viện |
| Nhiều service nhỏ trên một node | Footprint thấp có thể tăng mật độ triển khai | Peak RSS, giới hạn RAM và biên an toàn khi tải tăng |
| API chạy lâu, tải CPU cao | Vẫn có thể có lợi về bộ nhớ hoặc startup | So sánh throughput, p95/p99 latency và mức CPU với JVM JIT đã warm-up |

Những đánh đổi phổ biến:

**Build nặng và chậm hơn.** Native compiler cần phân tích dependency, tối ưu mã và liên kết executable, thường dùng nhiều CPU/RAM trong pipeline. Nhóm phát triển cần tính cả thời gian build CI và tài nguyên máy build.

**Ít linh hoạt với hành vi động.** Native Image dựa trên giả định *closed world*: compiler cần biết phần mã và cấu trúc nào có thể được dùng. Reflection, dynamic proxy, resource được nạp qua tên đường dẫn, serialization, JNI hoặc tải lớp động có thể cần metadata/hints. Nếu thiếu, ứng dụng có thể build thành công nhưng lỗi ở một luồng nghiệp vụ ít được gọi.

**Phụ thuộc nền tảng build và môi trường chạy.** Executable native gắn với hệ điều hành, kiến trúc CPU và đôi khi với các thư viện hệ thống hoặc cách liên kết. Build Linux không tạo ngay executable Windows, và một binary Linux cần tương thích với runtime/container đích.

**Hiệu năng runtime không tăng đồng đều.** JVM JIT có thể dựa vào thông tin thu thập được trong quá trình chạy để tối ưu các đường mã nóng. Ứng dụng native khởi động nhanh nhưng có thể có throughput thấp hơn hoặc CPU cao hơn với một số workload chạy lâu; cũng có ứng dụng cho kết quả khác. Phải đo trên nghiệp vụ thật.

**Kích thước artifact và image container không có quy luật một chiều.** Executable native có thể lớn hơn JAR nhưng không cần phân phối JRE/JDK riêng trong runtime image. Tổng kích thước container phụ thuộc base image, thư viện hệ thống, debug symbols và cách đóng gói.

**Khả năng quan sát và debug cần được kiểm tra.** Cách profiling, thu thập heap/thread diagnostics, xử lý stack trace, tích hợp agent và thư viện APM có thể khác so với JVM. Xác nhận các công cụ vận hành đang dùng hỗ trợ biến thể native và phiên bản tương ứng.

## 6. Spring Boot đóng vai trò gì trong quá trình biên dịch native?

Spring Boot sử dụng rất nhiều cơ chế tiện lợi như component scanning, dependency injection, configuration properties và auto-configuration. Trên JVM, framework có thể khám phá hoặc tạo một số cấu trúc ở runtime. Với native, những thông tin quan trọng cần được xác định hoặc khai báo từ sớm.

**Spring AOT** thực hiện xử lý tại build time để sinh mã khởi tạo, cấu hình bean và các *runtime hints* cần thiết. Việc này giúp GraalVM nhìn thấy các kiểu dữ liệu, phương thức, resource hoặc proxy mà phần logic ứng dụng sử dụng gián tiếp.

### 6.1. Ví dụ một trường hợp cần runtime hints

Giả sử ứng dụng có một thư viện tự tìm và tạo đối tượng bằng reflection, hoặc đọc template không được tham chiếu trực tiếp từ Java code. Reachability analysis có thể không tự phát hiện mọi thành phần liên quan. Spring cung cấp cơ chế đăng ký hints:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration
@ImportRuntimeHints(OrderRuntimeHints.class)
class NativeConfig {
}

class OrderRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        // Ví dụ: một thư viện dùng reflection để gọi constructor của OrderDto.
        hints.reflection().registerType(
            OrderDto.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );

        // Ví dụ: ứng dụng đọc file mẫu từ classpath khi chạy.
        hints.resources().registerPattern("templates/order/*.html");
    }
}
```

Ở đây, `OrderDto` là một lớp DTO do dự án tự định nghĩa. Đoạn mã minh họa **cách** đăng ký reflection và resource; nhu cầu hints cụ thể phụ thuộc thư viện và đường truy cập mã. Không nên khai báo toàn bộ class hoặc bật reflection quá rộng theo thói quen. Nhiều tính năng của Spring Boot đã có hỗ trợ AOT nên không phải DTO nào cũng cần hints thủ công.

### 6.2. Những trường hợp cần rà soát tương thích

- Thư viện tự tìm class bằng chuỗi tên lớp, dùng `Class.forName(...)` hoặc tải plugin mới sau khi ứng dụng đã build.
- Framework tự sinh proxy/bytecode hoặc dùng reflection để đọc constructor, field, method.
- Nạp file JSON, XML, template, chứng chỉ hay cấu hình từ classpath theo đường dẫn chỉ xuất hiện ở runtime.
- Serialization/deserialization của kiểu được phát hiện động, kết nối JNI hoặc thư viện native.
- Cấu hình ứng dụng thay đổi cấu trúc bean theo những điều kiện chỉ biết khi chạy.

Một vấn đề tương thích không nhất thiết khiến dự án không dùng được Native Image. Cần xác định chính xác thành phần động, dùng hỗ trợ AOT của thư viện, bổ sung hints khi phù hợp, rồi thử lại ở **bản executable native thực tế**.

## 7. Thử Native Image trên một dự án Spring Boot

Để hình dung luồng làm việc, xét một dự án Spring Boot phiên bản có hỗ trợ GraalVM Native Image, dùng JDK/GraalVM và plugin build tương thích. Các ví dụ sau giả định dự án đã cấu hình `native-maven-plugin` hoặc plugin Gradle `org.graalvm.buildtools.native`, và đã có công cụ native-image cần thiết.

### 7.1. Với Maven

```bash
# Build JAR truyền thống để làm mốc đối chứng
./mvnw -DskipTests package

# Build executable native (khi profile 'native' đã được cấu hình)
./mvnw -Pnative native:compile
```

Trong dự án dùng Spring Boot parent và cấu hình native tương ứng, profile `native` thường điều phối xử lý Spring AOT và GraalVM Native Build Tools. Với dự án tùy biến, hãy kiểm tra plugin và cấu hình lifecycle trước khi chạy. Thao tác native compile sẽ đòi hỏi nhiều tài nguyên build hơn đóng gói JAR thông thường.

### 7.2. Với Gradle

```bash
# Build JAR truyền thống
./gradlew bootJar

# Build executable native khi đã bật GraalVM Native Build Tools
./gradlew nativeCompile
```

Spring Boot cũng hỗ trợ tạo container image thông qua buildpacks cho các dự án được cấu hình tương ứng. Cần xác nhận image dùng đúng executable native và kiểm thử trên cùng kiến trúc, hệ điều hành, tài nguyên container mục tiêu.

### 7.3. Kiểm chứng kết quả

Đừng dừng ở thông báo `BUILD SUCCESS`. Hãy chạy bản native trên môi trường phù hợp và thử ít nhất các luồng quan trọng: khởi động với cấu hình thực tế, gọi API, đọc template/resource, serialize dữ liệu, kết nối database, kiểm tra TLS, health/readiness và các luồng sử dụng reflection.

Nếu ứng dụng phụ thuộc external service, hãy phân biệt lỗi do cấu hình/kết nối với lỗi do metadata native. Kiểm thử integration trên executable native mới phát hiện được những vấn đề mà unit test trên JVM có thể bỏ sót.

## 8. Đo startup và bộ nhớ một cách công bằng

Giả sử cần trả lời: **"Bản native có giúp dịch vụ Order Service khởi động nhanh hơn và dùng ít RAM hơn không?"** Cách làm là build **hai biến thể từ cùng một commit**, cung cấp cùng chức năng và chạy trong điều kiện có thể so sánh.

### 8.1. Thiết lập thí nghiệm

1. Chốt cùng phiên bản ứng dụng, cấu hình, profile Spring, dữ liệu đầu vào và mức tải. Ghi lại phiên bản JDK, GraalVM, Spring Boot, plugin build, OS, CPU và kiến trúc máy.
2. Build bản JVM JAR và bản native release. Chạy trong điều kiện tương đương về CPU, memory limit, biến môi trường, database và network. Không chạy hai tiến trình cạnh tranh tài nguyên khi đang lấy số liệu.
3. Lặp phép đo cold start nhiều lần; chọn mốc bắt đầu tại thời điểm tạo tiến trình và mốc kết thúc khi readiness thành công. Ghi median, p95 và phạm vi dao động; tránh lấy một lần chạy làm kết luận.
4. Đo RSS/container memory khi ứng dụng nhàn rỗi và sau khi ổn định dưới một mức tải cố định. Theo dõi cả peak RSS trong giai đoạn startup và xử lý tải.
5. Chạy thử tải với cùng kịch bản và mức concurrency để so sánh requests/second, p95/p99 latency, CPU và tỷ lệ lỗi. Với JVM, ghi rõ giai đoạn warm-up trước khi đo hiệu năng ổn định.
6. So sánh tổng thời gian và tài nguyên build; ghi nhận độ tương thích thư viện, observability và khó khăn khi vận hành.

Ví dụ, trên Linux có thể lấy một **ảnh chụp tại thời điểm đo** của RSS (đơn vị KB) bằng:

```bash
ps -o pid,rss,cmd -p <PID>
```

Hoặc theo dõi các chỉ số của container bằng công cụ monitoring đang dùng. Lệnh `ps` chỉ trả về giá trị tại thời điểm chạy, **không đo peak RSS**. Cũng không nên đo startup bằng tổng thời gian một lệnh `curl` đơn lẻ sau khi server đã sẵn sàng: phép đo đó chủ yếu phản ánh độ trễ HTTP của request.

Với endpoint readiness của Spring Boot Actuator (khi đã bật và cấu hình), quy trình đo có thể mô tả như sau:

```text
start = đồng hồ monotonic tại lúc tạo tiến trình
khởi chạy bản JVM hoặc native
lặp kiểm tra GET /actuator/health/readiness cho tới khi đạt trạng thái sẵn sàng
startup_ready = đồng hồ monotonic hiện tại - start
ghi lại RSS/peak memory và số liệu CPU theo từng giai đoạn
```

Nếu phụ thuộc bên ngoài chưa ổn định, số liệu startup có thể phản ánh sự chờ đợi database hoặc mạng nhiều hơn bản thân công nghệ biên dịch. Khi đó cần đo riêng và ghi rõ giả định.

### 8.2. Mẫu bảng kết quả

Điền **số đo thực tế** vào bảng sau; không có mức cải thiện chung đúng cho mọi ứng dụng.

| Chỉ số | JVM JAR | Native Image | Cách diễn giải |
|---|---|---|---|
| Startup đến readiness, median | _(đo)_ | _(đo)_ | Càng thấp càng sẵn sàng nhận tải sớm |
| Startup đến readiness, p95 | _(đo)_ | _(đo)_ | Cho thấy mức dao động giữa các lần cold start |
| RSS nhàn rỗi | _(đo)_ | _(đo)_ | So sánh footprint ở trạng thái ít tải |
| Peak RSS khi có tải | _(đo)_ | _(đo)_ | Liên quan trực tiếp đến memory limit |
| Throughput ở tải mục tiêu | _(đo)_ | _(đo)_ | Cần đồng thời xem CPU và tỷ lệ lỗi |
| p95 latency khi ổn định | _(đo)_ | _(đo)_ | Phản ánh độ trễ của request thực tế |
| Thời gian build | _(đo)_ | _(đo)_ | Đánh đổi đối với CI/CD và vòng lặp phát triển |
| Kích thước runtime container | _(đo)_ | _(đo)_ | Phụ thuộc base image và thư viện hệ thống |

**Cách đọc kết quả:** nếu native thắng rõ ở startup và RAM nhưng giảm throughput, quyết định còn phụ thuộc vào mục tiêu triển khai. Một batch job chạy vài giây có thể đánh giá khác một API liên tục xử lý tải CPU lớn. Thước đo cuối cùng là hiệu quả *theo workload*, không phải nhãn "native" hay "JVM".

## 9. Ngộ nhận thường gặp

**"Native Image luôn nhanh hơn JVM."** Không chính xác. Native thường có lợi thế ở startup; throughput, latency sau warm-up và CPU có thể tốt hơn hoặc kém hơn tùy workload, cấu hình và phiên bản công cụ.

**"Native Image không dùng heap và không cần GC."** Không chính xác. Tệp native vẫn cần cấp phát đối tượng và quản lý vòng đời bộ nhớ, trong đó có garbage collection.

**"Cứ build được native là mọi tính năng đều hoạt động."** Không chính xác. Reflection, resource hoặc code path hiếm gặp có thể chỉ phát sinh lỗi lúc chạy. Kiểm thử bản native và tích hợp thực tế là bắt buộc trước khi triển khai.

**"JAR càng nhỏ thì ứng dụng dùng càng ít RAM."** Không có quan hệ trực tiếp. Kích thước artifact trên đĩa khác với bộ nhớ tiến trình khi hoạt động.

**"Native Image thay thế mọi kỹ thuật tối ưu Spring Boot."** Không chính xác. Việc tối giản dependency, giảm bean không cần thiết, cấu hình pool hợp lý, tối ưu truy vấn, cache và readiness vẫn ảnh hưởng trực tiếp tới startup và RAM.

## 10. Kết luận và định hướng học tiếp

GraalVM Native Image cho phép biên dịch trước ứng dụng Java thành tệp thực thi native, còn Spring AOT chuẩn bị mã và metadata để một ứng dụng Spring Boot vốn có nhiều thành phần động hoạt động trong mô hình đó. Hai lợi ích cần kiểm chứng là **rút ngắn thời gian tới lúc ứng dụng sẵn sàng** và **giảm bộ nhớ mỗi instance**. Cái giá có thể là build phức tạp hơn, hạn chế với tính năng động và hiệu năng xử lý dài hạn khác với JVM JIT.

Khi tiếp tục thực hành, hãy dùng cùng một dự án Spring Boot để: cấu hình Maven hoặc Gradle build native, phát hiện lỗi reflection/resource và đăng ký hints khi cần, chạy kiểm thử tương thích, đóng gói container, rồi so sánh cold start, readiness, RSS và hiệu năng dưới tải trước khi quyết định vận hành bản native.

### Tài liệu tham khảo chính thức

- [Spring Boot Reference — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/)
- [Spring Framework Reference — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [GraalVM — Native Image](https://www.graalvm.org/latest/reference-manual/native-image/)
