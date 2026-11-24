# Duy trì so sánh chức năng, hiệu năng giữa JVM, JVM AOT và native

## 1. Mục tiêu và phạm vi so sánh

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring Boot sử dụng **Spring Ahead-of-Time (AOT)** để chuẩn bị mã khởi tạo và metadata, sau đó có thể chạy ứng dụng theo ba cách: JVM thông thường, JVM sử dụng mã Spring AOT đã sinh, hoặc GraalVM Native Image. Mỗi cách chạy có đặc điểm về startup, runtime, memory và khả năng tương thích khác nhau.

Khi nâng cấp Spring Boot, JDK/GraalVM hoặc dependency, nhóm cần duy trì một bộ so sánh có thể lặp lại. Mục tiêu là trả lời hai câu hỏi độc lập:

- **Chức năng:** ba cách chạy có cùng hành vi nghiệp vụ và hợp đồng API dưới cùng cấu hình hay không?
- **Hiệu năng:** với cùng workload và giới hạn tài nguyên, mỗi cách chạy có startup, throughput, latency, CPU và memory như thế nào?

Bài này định nghĩa rõ ba mode, cách tạo artifact, kiểm tra functional parity, thiết kế benchmark và lưu baseline qua các lần nâng cấp.

Sau bài học, người học có thể:

1. Phân biệt JVM thường, JVM chạy Spring AOT và GraalVM Native Image.
2. Giải thích JVM AOT vẫn sử dụng JVM runtime và JIT compiler.
3. Tạo ba biến thể từ cùng source revision và dependency graph.
4. Kiểm soát build-time profile/condition để tránh so sánh sai cấu hình.
5. Thiết kế test suite kiểm tra chức năng trên cả ba mode.
6. So sánh startup, cold request, warm throughput, latency và memory.
7. Chọn benchmark phù hợp cho service HTTP và code path nhỏ.
8. Kiểm soát CPU, memory, container, dataset và downstream services.
9. Phân tích khác biệt do JIT warm-up, GC, image size và static analysis.
10. Lưu benchmark provenance, baseline và regression gates cho từng release.

> **Nguyên tắc:** xác nhận chức năng tương đương trước khi so sánh tốc độ. Mỗi lần đo phải ghi rõ source, build mode, runtime, platform, cấu hình, workload và giới hạn tài nguyên.

## 2. Ba mode cần phân biệt

### 2.1. JVM thông thường

Đây là cách chạy Spring Boot quen thuộc:

~~~bash
java -jar orders-service.jar
~~~

Spring tạo và cấu hình ApplicationContext trong runtime theo classpath và environment của process. JVM nạp class khi cần, thực thi bytecode và có thể biên dịch các method nóng bằng JIT compiler.

Đặc điểm thường thấy:

- Classpath và nhiều quyết định cấu hình được xử lý lúc ứng dụng chạy.
- JIT có thời gian warm-up và tối ưu dựa trên hành vi thực tế.
- Có thể dùng dynamic class loading, reflection và các cơ chế runtime linh hoạt trong phạm vi JVM hỗ trợ.
- Startup và memory phụ thuộc JDK, GC, heap options, classpath và workload.

Đây là baseline JVM truyền thống để so sánh với hai mode còn lại.

### 2.2. JVM chạy mã Spring AOT

**JVM AOT** trong bài này có nghĩa là ứng dụng đã trải qua Spring AOT processing, nhưng vẫn chạy bằng lệnh java trên JVM:

~~~bash
java -Dspring.aot.enabled=true -jar orders-service.jar
~~~

Spring AOT phân tích ApplicationContext ở build time và sinh mã khởi tạo/bean definitions cùng các hints cần thiết. Khi bật spring.aot.enabled=true, Spring Boot dùng mã AOT đã sinh để khởi tạo context.

Cần hiểu chính xác phạm vi:

- Spring AOT tối ưu phần khởi tạo và cấu hình Spring.
- Bytecode của ứng dụng vẫn chạy trên JVM.
- JVM vẫn có JIT compiler, GC, class loading và runtime services của JDK.
- JVM AOT không phải executable native và không đồng nghĩa với việc mọi Java method đã được biên dịch thành machine code trước khi chạy.
- Classpath và các quyết định về bean được cố định ở build time theo giới hạn của Spring AOT.

Spring Boot hiện hỗ trợ chạy AOT-processed application trên JVM bằng spring.aot.enabled=true. Đây là mode hữu ích để đo lợi ích của Spring AOT và kiểm tra mã generated mà chưa phải chờ native-image compilation. [Spring Boot — Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html).

### 2.3. GraalVM Native Image

Native Image sử dụng AOT-generated assets để biên dịch ứng dụng thành executable riêng cho OS/architecture đích. Khi chạy, process không cần một JVM để thực thi bytecode và không dùng HotSpot JIT như JVM mode.

Đặc điểm:

- Static analysis xác định code reachable từ entry point.
- Reflection, resource, serialization, dynamic proxy và JNI cần metadata/hints phù hợp.
- Classpath được cố định tại build time.
- Executable gắn với platform/toolchain cụ thể.
- Không có lazy class loading như JVM thông thường.
- Runtime, GC, startup và memory behavior khác JVM.

Spring AOT là bước chuẩn bị cần thiết cho Spring ApplicationContext; Native Image compiler tiếp tục phân tích và tạo executable. [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html).

### 2.4. Bảng so sánh

| Thuộc tính | JVM thường | JVM + Spring AOT | Native Image |
| --- | --- | --- | --- |
| Artifact chạy | Executable JAR/classes | JAR có AOT-generated assets | Native executable |
| Spring context setup | Runtime parsing/configuration | Dùng mã Spring AOT generated | Dùng mã Spring AOT generated |
| Runtime engine | JVM | JVM | GraalVM Native Image runtime |
| JIT compiler | Có | Có | Không có HotSpot JIT |
| GC | JVM GC | JVM GC | Native Image GC được chọn khi build |
| Classpath | Runtime classpath | Cố định theo AOT build | Cố định trong image |
| Bean conditions | Đánh giá runtime | Đánh giá khi AOT processing | Đánh giá khi AOT processing |
| Reflection/resource | JVM runtime hỗ trợ linh hoạt | JVM runtime vẫn hỗ trợ, AOT có giới hạn | Cần reachability metadata/hints phù hợp |
| OS/architecture | JAR thường có tính portable theo JDK | JAR thường có tính portable theo JDK | Executable theo target platform |
| Mục tiêu đo nổi bật | JIT steady-state và linh hoạt | Startup của Spring AOT trên JVM | Cold start, footprint và native throughput |

Không kết luận Native Image luôn nhanh hơn JVM ở mọi workload. Native Image thường có lợi thế startup và memory trong nhiều ứng dụng; JVM có thể đạt throughput cao sau JIT warm-up. Kết quả phụ thuộc ứng dụng, runtime options, GC, PGO, CPU và traffic mix.

## 3. Tạo ba biến thể từ cùng một source

### 3.1. Cố định source và dependency graph

Trước khi build, ghi lại:

- Git commit hoặc source revision.
- Spring Boot/Spring Framework version.
- JDK vendor/version và GraalVM distribution/version.
- Maven/Gradle wrapper và Native Build Tools plugin version.
- Dependency lock/BOM và resolved dependency graph.
- Build profile, environment variables và system properties dùng trong AOT processing.
- OS, architecture, libc và CPU baseline của native build.

Không so sánh ba executable được tạo từ ba commit khác nhau rồi quy toàn bộ chênh lệch cho runtime mode.

### 3.2. Maven: tạo JAR có AOT assets

Nếu dự án dùng spring-boot-starter-parent, native profile của Spring Boot Maven Plugin có thể kích hoạt process-aot và chuẩn bị cấu hình Native Build Tools.

~~~bash
./mvnw clean package
./mvnw -Pnative clean package
~~~

JAR được build với -Pnative chứa AOT-generated assets. Có thể dùng cùng JAR đó để chạy hai JVM mode:

~~~bash
java -jar target/orders-service.jar
~~~

~~~bash
java -Dspring.aot.enabled=true -jar target/orders-service.jar
~~~

Lệnh thứ nhất chạy JVM thường; lệnh thứ hai yêu cầu Spring dùng AOT-generated initialization code. Khi chạy AOT mode, cần đảm bảo JAR thực sự có generated assets.

Để tạo native executable bằng Native Build Tools, dùng cấu hình plugin và native profile tương ứng với dự án:

~~~bash
./mvnw -Pnative native:compile
~~~

Trong một số cấu hình Spring Boot/Buildpacks, pipeline có thể dùng spring-boot:build-image với native profile. Chọn một đường build rõ ràng và ghi lại command thực tế trong benchmark report. [Spring Boot Maven AOT Plugin](https://docs.spring.io/spring-boot/maven-plugin/aot.html).

### 3.3. Gradle: tạo JVM AOT mode

Để chạy Spring AOT trên JVM mà không tạo native executable, áp dụng plugin org.springframework.boot.aot:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.2.0"
    id("org.springframework.boot.aot")
    java
}
~~~

Build AOT assets và JAR:

~~~bash
./gradlew processAot bootJar
~~~

Sau đó chạy:

~~~bash
java -jar build/libs/orders-service.jar
java -Dspring.aot.enabled=true -jar build/libs/orders-service.jar
~~~

Lệnh thứ nhất dùng JVM mode thường; lệnh thứ hai dùng Spring AOT trên JVM. Kiểm tra output startup để xác nhận ứng dụng đã vào AOT-processed mode.

### 3.4. Gradle: tạo Native Image

Khi áp dụng GraalVM Native Image plugin, Spring Boot tự cấu hình AOT tasks và nativeCompile sử dụng output của processAot:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.2.0"
    id("org.graalvm.buildtools.native") version "1.1.18"
    java
}
~~~

Build native executable:

~~~bash
./gradlew nativeCompile
~~~

Executable thường được đặt trong build/native/nativeCompile/. Phiên bản Spring Boot và Native Build Tools trong ví dụ chỉ minh họa; hãy pin các version tương thích của dự án. [Spring Boot Gradle AOT Plugin](https://docs.spring.io/spring-boot/gradle-plugin/aot.html).

### 3.5. Bảo đảm cả ba mode dùng cùng cấu hình AOT

Spring AOT chuẩn bị bean definitions tại build time. Các condition ảnh hưởng đến việc có bean hay không, chẳng hạn @Profile hoặc @ConditionalOnProperty, được đánh giá trong quá trình AOT. Vì vậy:

- Chọn profile và property ảnh hưởng bean trước khi chạy processAot.
- Ghi lại environment/system properties đã dùng khi build AOT.
- Không đổi một condition ở runtime rồi kỳ vọng AOT mode tạo thêm bean.
- Dùng cùng AOT-generated assets khi chạy JVM AOT và build Native Image.
- Nếu cần so sánh nhiều profile triển khai, tạo artifact AOT riêng cho từng profile hợp lệ.

Spring Boot nêu rõ classpath và tập bean được xác định ở build time khi dùng AOT. [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html).

## 4. Functional parity là cổng trước benchmark

### 4.1. Định nghĩa contract chung

Trước khi đo hiệu năng, lập một contract cho service:

- Endpoint, HTTP method và request schema.
- Response status, body schema và headers.
- Validation rules và error mapping.
- Authentication/authorization.
- Transaction boundaries và side effects.
- Database schema, migration version và isolation level.
- Message topics, serialization format và delivery semantics.
- Cache keys, TTL và eviction behavior.
- Timeout, retry, idempotency và circuit-breaker behavior.
- Health/readiness behavior và graceful shutdown.

Các mode phải chạy cùng contract, cùng dữ liệu và cùng phiên bản dependency. Nếu Native Image không hỗ trợ một dynamic feature mà JVM thường hỗ trợ, phải giải quyết compatibility hoặc ghi rõ giới hạn trước khi xem xét hiệu năng.

### 4.2. Xây dựng bộ dữ liệu kiểm thử chuẩn

Dùng một bộ input version hóa, bao gồm:

- Request hợp lệ thông thường.
- Boundary values và payload lớn.
- Field bị thiếu, null và giá trị không hợp lệ.
- Unicode, timezone và locale.
- Date/time tại các mốc biên.
- Serialization/deserialization của polymorphic types nếu ứng dụng dùng.
- Authentication success/failure.
- Downstream timeout, lỗi kết nối và response không hợp lệ.
- Duplicate request, retry và idempotency.
- Batch hoặc scheduled workload nếu service có.

Với mỗi case, lưu input và expected behavior. Tránh dùng dữ liệu thay đổi theo thời gian nếu không cố định Clock, random seed hoặc dataset snapshot.

Reset database, broker topic, cache và filesystem fixture về cùng trạng thái trước mỗi mode hoặc dùng namespace riêng cho từng lần chạy. Nếu chạy ba mode liên tiếp trên cùng dữ liệu đã bị thay đổi bởi request trước, kết quả functional diff có thể đến từ trạng thái test chứ không phải runtime.

### 4.3. So sánh response và side effects

Không chỉ kiểm tra HTTP status. So sánh:

| Thành phần | Cách xác nhận |
| --- | --- |
| Status code | Phải tương đương cho cùng request. |
| JSON body | So sánh cấu trúc/giá trị sau khi normalize field không ổn định. |
| Headers | Kiểm tra content type, cache, correlation và security headers. |
| Database | So sánh row state, transaction result và constraint behavior. |
| Messages | So sánh payload, key, headers và số lượng message phát ra. |
| Cache | Kiểm tra key/value/TTL và kết quả sau warm-up. |
| Errors | Cùng loại lỗi nghiệp vụ và cùng contract công khai. |
| Security | Cùng authorization decision và không lộ dữ liệu nhạy cảm. |

Có thể bỏ qua các trường thực sự không xác định như request ID hoặc timestamp được sinh riêng cho từng lần chạy, nhưng phải kiểm tra định dạng, tính hợp lệ và semantics của chúng. Không normalize những field mà khách hàng hoặc downstream phụ thuộc.

### 4.4. Differential test giữa ba mode

Dùng cùng test corpus, chạy lần lượt trên:

1. JAR chạy JVM thường.
2. Cùng JAR chạy với spring.aot.enabled=true.
3. Native executable.

Thu response và side effects của mỗi mode rồi so sánh với expected output hoặc với baseline đã được phê duyệt.

~~~mermaid
flowchart TD
    A[Canonical test corpus] --> B[JVM thường]
    A --> C[JVM + Spring AOT]
    A --> D[Native Image]
    B --> E[Capture responses and side effects]
    C --> E
    D --> E
    E --> F[Normalize nondeterministic fields]
    F --> G[Compare with contract]
    G --> H{All modes pass?}
    H -->|No| I[Investigate functional divergence]
    H -->|Yes| J[Open performance benchmark gate]
~~~

### 4.5. Test những phần dễ khác biệt trong Native Image

Tập trung thêm vào các khu vực có thể khác giữa JVM và Native Image:

- Reflection và dynamic class loading.
- Resource loading từ classpath hoặc filesystem.
- Serialization và polymorphic binding.
- Dynamic proxies và framework-generated classes.
- JNI, native libraries và cryptography providers.
- Timezone, locale, charset và filesystem assumptions.
- Class initialization và static state.
- ServiceLoader và provider discovery.
- Configuration được đọc lúc build so với lúc runtime.

Spring Boot khuyến nghị tiếp tục chạy phần lớn unit/integration tests trên JVM, sau đó tập trung native tests vào các khu vực có khả năng khác biệt. [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html).

## 5. Tổ chức test theo tầng

| Tầng | JVM thường | JVM AOT | Native |
| --- | --- | --- | --- |
| Unit tests | Chạy đầy đủ | Có thể dùng chung nếu test không phụ thuộc dynamic context | Chọn test cần kiểm chứng runtime native |
| Spring integration tests | Chạy đầy đủ | Chạy với AOT assets/context | Có thể dùng Native Build Tools native tests |
| Contract/API tests | Chạy cùng corpus | Chạy cùng corpus | Chạy cùng corpus |
| Database/broker integration | Cùng container/service | Cùng container/service | Cùng container/service |
| Smoke test executable | JAR startup/ready | AOT JAR startup/ready | Native startup/ready |
| End-to-end test | Chạy qua HTTP | Chạy qua HTTP | Chạy qua HTTP |
| Performance test | Baseline JVM | Baseline JVM AOT | Native executable |

Native tests có thể tốn thời gian vì test image cũng phải được biên dịch. Có thể chạy test native trong CI theo lịch hoặc ở các stage phù hợp, trong khi JVM tests vẫn là vòng phản hồi nhanh cho phần lớn thay đổi. Spring Boot và Native Build Tools cung cấp nativeTest cho Maven/Gradle theo cấu hình tương ứng.

~~~bash
./mvnw -PnativeTest test
~~~

~~~bash
./gradlew nativeTest
~~~

Tên profile/task phụ thuộc plugin version và cấu hình build. [Spring Boot — Native Image Testing](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html).

## 6. Phân biệt startup, cold request và steady state

Không gộp tất cả thành một con số “startup time”.

### 6.1. Process startup

Đo từ thời điểm process/container được tạo đến khi process bắt đầu phục vụ health endpoint. Dùng cùng readiness definition cho cả ba mode.

Spring Boot Actuator có hai metric hữu ích:

- application.started.time: thời gian ứng dụng khởi động.
- application.ready.time: thời gian từ lúc bắt đầu đến khi ứng dụng sẵn sàng nhận request.

Đồng thời đo từ bên ngoài bằng supervisor/load harness để không phụ thuộc vào cách mỗi runtime ghi metric. [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

### 6.2. Cold first request

Sau readiness, gửi request đầu tiên đến các endpoint đại diện. Request đầu có thể kích hoạt:

- Lazy initialization.
- Connection pool acquisition.
- TLS handshake hoặc DNS lookup.
- Cache miss và deserialization.
- JIT compilation trong JVM.
- Load dữ liệu hoặc khởi tạo client.

Ghi thời gian request đầu riêng. Đừng dùng application.ready.time thay cho latency của request đầu.

### 6.3. Warm-up và steady state

JVM thường cần warm-up để JIT nhận diện hot methods và tối ưu code. JVM chạy Spring AOT vẫn có đặc điểm này vì nó vẫn chạy trên JVM.

Native Image không có HotSpot JIT warm-up, nhưng service vẫn cần warm-up cho connection pool, cache, DNS/TLS, lazy data và downstream clients. Vì vậy:

1. Đợi readiness.
2. Chạy cùng chuỗi warm-up requests.
3. Loại bỏ khoảng warm-up khỏi steady-state result.
4. Chạy workload đo trong thời lượng cố định.
5. Lưu latency và throughput theo time series để phát hiện drift.

Nếu mục tiêu là cold-start/serverless, không loại first request khỏi kết quả. Nếu mục tiêu là service dài hạn, báo cáo cold-start và steady-state thành hai nhóm riêng.



## 7. Thiết kế benchmark cho service Spring Boot

### 7.1. Ưu tiên benchmark ở cấp HTTP

Với một Spring Boot service, dùng cùng external load generator để gửi request đến ba mode. Các công cụ như k6, Gatling hoặc wrk có thể tạo tải bên ngoài process.

Ví dụ:

~~~bash
k6 run --duration 10m --vus 40 orders-workload.js
~~~

Hoặc với endpoint đơn giản:

~~~bash
wrk -t4 -c40 -d10m http://localhost:8080/api/orders
~~~

Workload cần mô tả rõ:

- Request mix theo endpoint.
- Payload và dataset.
- Authentication.
- Concurrency hoặc offered RPS.
- Think time và retry behavior của client.
- Thời gian warm-up và measurement.
- Điều kiện dừng khi service vượt SLO.

Không dùng một endpoint /health đơn giản làm đại diện cho workload business nếu production xử lý database, serialization, cache và downstream calls.

### 7.2. Hai kiểu tải cần đo

**Fixed concurrency:** giữ số client đồng thời cố định để xem hệ thống xử lý được bao nhiêu request và latency thay đổi ra sao.

**Fixed offered load:** giữ tốc độ gửi request cố định để so sánh latency/error ở cùng nhu cầu traffic.

Hai phép đo trả lời câu hỏi khác nhau. Khi service bão hòa, fixed-concurrency có thể che giấu latency tăng bằng cách giảm throughput; fixed-offered-load giúp quan sát backlog, timeout và error khi hệ thống không theo kịp traffic.

### 7.3. JMH dùng đúng phạm vi

[JMH](https://github.com/openjdk/jmh) là harness cho nano/micro/milli benchmarks nhắm tới JVM. Dùng JMH để phân tích method hoặc algorithm trên JVM thường và JVM AOT nếu benchmark code path độc lập với container/application startup.

Không lấy một kết quả JMH microbenchmark rồi so trực tiếp với kết quả k6/HTTP của Native Image. Đó là hai cấp đo khác nhau. Với service-level comparison, dùng cùng external HTTP harness cho cả ba mode. Nếu cần microbenchmark cho native code, phải tạo harness native tương đương và xác nhận nó đo cùng operation, input và semantics.

### 7.4. Tránh benchmark sai

- Không chạy benchmark trong IDE hoặc trên máy có tải nền thay đổi.
- Không chạy ba biến thể đồng thời trên cùng CPU/memory nếu chúng cạnh tranh tài nguyên.
- Không thay request mix giữa các mode.
- Không chỉ lấy một lần chạy.
- Không bỏ qua JIT warm-up nếu mục tiêu là steady-state JVM.
- Không bỏ qua cache/connection warm-up của Native Image.
- Không đo instrumented/debug executable thay cho production build.
- Không để load generator trở thành bottleneck.
- Không so sánh khi downstream database/broker đang bị tải không đồng đều.

JMH cũng khuyến nghị benchmark project được cấu hình đúng, có warm-up/fork và được review; harness không tự loại bỏ mọi lỗi thiết kế benchmark. [OpenJDK JMH README](https://github.com/openjdk/jmh).

## 8. Kiểm soát môi trường benchmark

### 8.1. Giữ phần cứng và platform tương đương

Ghi lại và cố định:

- CPU model, core count và instruction set.
- RAM và memory bandwidth.
- OS/kernel và architecture.
- libc và container base image.
- CPU quota, CPU pinning nếu có.
- Memory limit và swap policy.
- Filesystem/storage và network path.
- JDK/GraalVM distribution và version.

Native executable được tạo theo target platform. Nếu baseline chạy trên Linux x64 còn native chạy trên ARM64, benchmark đang so sánh cả runtime lẫn phần cứng.

### 8.2. Giữ resource limits giống nhau

Nếu triển khai container, dùng cùng:

- CPU quota/request.
- Memory limit/request.
- Swap policy.
- Replica count.
- Network namespace và port path.
- Container logging và sidecars.
- Readiness/health behavior.

Không chạy JVM trên host không giới hạn rồi so với native container bị giới hạn 512 MiB. Mọi kết luận phải dựa trên cùng resource envelope.

### 8.3. Kiểm soát downstream

Database, cache, broker và external API có thể chi phối latency nhiều hơn runtime Java. Dùng cùng:

- Database snapshot/schema/indexes.
- Connection pool limits.
- Dataset và cache initial state.
- Broker topic/partition và consumer configuration.
- External service latency hoặc test double có phân bố cố định.
- Timeout/retry/circuit-breaker settings.

Nếu downstream có tải nền, đo riêng latency của dependency và chạy lại khi cần. Một mode không được nhận connection pool nóng trong khi mode khác phải khởi tạo pool mới.

## 9. Metric cần ghi cho cả ba mode

| Nhóm | Metric | Mục đích |
| --- | --- | --- |
| Startup | Process start-to-ready, application.started.time, application.ready.time | Đo thời gian sẵn sàng. |
| First request | p50/p95/p99 của request đầu | Tìm chi phí lazy initialization và cold path. |
| Throughput | Requests/second hoặc messages/second | Đo năng lực xử lý. |
| Latency | p50, p95, p99 và max | Đo thời gian phản hồi và tail latency. |
| Reliability | Error rate, timeout, retry, rejected request | Kiểm tra chất lượng dưới tải. |
| CPU | Average/peak CPU, throttling | Đo chi phí xử lý và saturation. |
| Memory | RSS/PSS, cgroup current/peak, heap khi có | So sánh footprint process/container. |
| GC | Count, total time, pause distribution khi có | Hiểu áp lực allocation/collection. |
| JVM | JIT compilation time, class loading và thread metrics | Hiểu chi phí riêng của JVM modes. |
| Build | Build duration, executable/JAR size | Đánh giá chi phí pipeline và artifact. |
| Operations | Restart, OOM, readiness failures | Kiểm tra khả năng vận hành. |

Không yêu cầu mọi runtime xuất cùng bộ metric nội bộ. Ví dụ JIT compilation time chỉ có ý nghĩa với JVM; Native Image không có HotSpot JIT. So sánh trực tiếp bằng các chỉ số chung như startup-to-ready, throughput, latency, CPU và RSS/cgroup; dùng metric riêng để giải thích nguyên nhân.

### 9.1. Spring Boot Actuator

Các meter hữu ích gồm:

- application.started.time và application.ready.time.
- http.server.requests.
- jvm.memory.*, buffer pool, GC và thread metrics ở JVM modes.
- process.* và system.* khi binder/runtime hỗ trợ.
- jdbc.connections.* và hikaricp.*.
- http.client.requests nếu dùng builder được instrument.

Tên meter và mức độ khả dụng phụ thuộc version, registry và runtime. Với Native Image, không giả định mọi JVM meter có cùng ý nghĩa như HotSpot. Hãy kết hợp process/cgroup metrics của OS với Actuator metrics. [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

### 9.2. Đo memory cùng một cách

Dùng RSS/PSS từ OS và cgroup current/peak cho cả ba mode. Heap used của JVM không tương đương RSS của native executable. Cũng không so executable file size với memory đang resident.

Ghi:

- RSS/peak RSS của process.
- PSS nếu nhiều process share pages.
- cgroup memory.current, memory.peak, memory.max.
- Heap used/committed/max của JVM modes.
- GC và buffer metrics nếu runtime expose.

Tính cả sidecar/helper process nếu chúng nằm trong cùng cgroup. Báo cáo rõ metric source và đơn vị.

## 10. Phân tích kết quả theo workload

### 10.1. Workload ưu tiên cold start

Nếu ứng dụng được scale-to-zero, chạy như serverless function hoặc thường xuyên tạo process mới, quan tâm:

- Process start-to-ready.
- First request latency.
- Memory sau startup.
- Thời gian tải image/container.
- Thời gian tạo replica mới.

Native Image có thể có lợi thế lớn ở đây, nhưng phải tính cả thời gian pull image, scheduling và dependency readiness nếu đó là mục tiêu production.

### 10.2. Workload chạy dài

Với service chạy nhiều giờ/ngày, đo:

- Warm steady-state throughput.
- p95/p99 latency dưới tải mục tiêu.
- CPU per request.
- Memory plateau và peak.
- GC frequency/time.
- Behavior khi burst và soak.

JVM thường có thể đạt hiệu năng cao sau JIT warm-up. JVM AOT có thể giảm startup của Spring context nhưng vẫn dùng JIT. Native Image có thể có footprint nhỏ hơn nhưng throughput phụ thuộc workload và optimization options. Không dùng startup result để kết luận steady-state throughput.

### 10.3. Workload memory-constrained

Khi chạy với container limit thấp, so sánh:

- Peak cgroup memory.
- RSS sau warm-up và khi peak load.
- GC pressure.
- OOM/restart.
- Throughput và latency ở cùng limit.

Một mode dùng ít memory hơn nhưng giảm throughput hoặc tăng tail latency có thể không phải lựa chọn tốt nhất cho service đó.

### 10.4. Workload CPU-bound và I/O-bound

CPU-bound workload giúp quan sát compiler/runtime efficiency. I/O-bound workload có thể bị chi phối bởi database, network, serialization và connection pool.

Tách ít nhất:

- CPU-bound operation.
- Database/API-heavy request.
- Serialization/payload-heavy request.
- Mixed production traffic.

Khi một mode không khác biệt trong I/O-bound test, không kết luận runtime tương đương về CPU. Ngược lại, CPU benchmark nhỏ không đại diện cho latency end-to-end.

## 11. Tính thống kê và cách báo cáo

### 11.1. Lặp lại độc lập

Mỗi mode cần nhiều lần chạy độc lập, mỗi lần khởi động process mới. Xen kẽ thứ tự chạy để giảm ảnh hưởng tải nền, thermal throttling hoặc thay đổi CPU frequency.

Báo cáo:

- Median của startup và latency.
- p95/p99 của request latency.
- Mean/median throughput theo run.
- Min/max hoặc confidence interval nếu phương pháp thống kê phù hợp.
- Peak memory mỗi run và phân bố giữa các lần chạy.

Không chỉ chọn run tốt nhất. Nếu kết quả dao động lớn, tăng số lần chạy hoặc ổn định môi trường trước khi kết luận.

### 11.2. Tách warm-up và measurement

Một run nên có các giai đoạn:

1. Khởi động process mới.
2. Đợi readiness.
3. Gửi warm-up traffic theo script cố định.
4. Bắt đầu measurement window.
5. Duy trì tải đến hết thời lượng.
6. Dừng process và lưu metrics/logs.
7. Chờ tài nguyên được giải phóng trước run tiếp theo.

Với cold-start benchmark, bỏ warm-up và đo riêng process start/first request. Không trộn kết quả cold-start và steady-state vào cùng một average.

### 11.3. Dùng cùng SLO và performance gate

Performance gate nên dựa trên yêu cầu của service, ví dụ:

- p99 latency không vượt SLO.
- Error rate không tăng vượt ngưỡng đã định.
- Throughput đạt traffic mục tiêu.
- Peak memory có headroom dưới container limit.
- Startup-to-ready đáp ứng thời gian scale-up.
- CPU không bị throttling ở operating point dự kiến.

Không đặt một ngưỡng cải thiện phần trăm cố định cho mọi module. Đánh giá độ lớn chênh lệch cùng độ dao động và tác động vận hành.

## 12. Lập bảng kết quả chuẩn

Dùng một bảng cho mỗi release và mỗi target platform:

| Metric | JVM thường | JVM + Spring AOT | Native Image |
| --- | ---: | ---: | ---: |
| Source commit | Ghi commit | Ghi commit | Ghi commit |
| JDK/GraalVM | Ghi version | Ghi version | Ghi version |
| Build mode | JVM | AOT JAR | Native executable |
| Startup-to-ready median | Ghi số đo | Ghi số đo | Ghi số đo |
| First request p95 | Ghi số đo | Ghi số đo | Ghi số đo |
| Throughput at target load | Ghi số đo | Ghi số đo | Ghi số đo |
| p95/p99 latency | Ghi số đo | Ghi số đo | Ghi số đo |
| Error/timeout rate | Ghi số đo | Ghi số đo | Ghi số đo |
| CPU average/peak | Ghi số đo | Ghi số đo | Ghi số đo |
| RSS/cgroup peak | Ghi số đo | Ghi số đo | Ghi số đo |
| Heap/GC metrics | Ghi nếu có | Ghi nếu có | Ghi nếu runtime expose |
| Artifact size | JAR size | AOT JAR size | Executable/image size |
| Build duration | Ghi số đo | Ghi số đo | Ghi số đo |
| Functional parity | PASS/FAIL | PASS/FAIL | PASS/FAIL |

Không để trống một metric mà không giải thích. Nếu metric không có ý nghĩa ở mode đó, ghi N/A và nêu lý do; nếu metric không thu được do thiếu instrumentation, ghi rõ là chưa đo.

## 13. Duy trì baseline qua nâng cấp

### 13.1. Pin toolchain

Mỗi baseline cần ghi:

- Spring Boot và Spring Framework.
- JDK/GraalVM distribution và version.
- Native Build Tools plugin.
- Maven/Gradle wrapper.
- OS/architecture/libc.
- Container base image.
- GC, heap options, march, PGO và build arguments.
- Runtime flags và environment configuration.

Khi nâng cấp, không thay đồng thời tất cả thành phần nếu mục tiêu là xác định nguồn regression. Ưu tiên nâng một nhóm có chủ đích, sau đó chạy lại parity và performance suites.

### 13.2. Khi nào phải tạo lại AOT/native artifacts?

Tạo lại AOT assets và Native Image khi thay đổi:

- Source code hoặc bean configuration.
- Spring Boot/Spring Framework version.
- Dependency graph.
- Build-time profile/condition/environment.
- GraalVM/JDK hoặc Native Build Tools.
- Reachability metadata, reflection/resource hints.
- OS/architecture/CPU target.
- Native build arguments, GC hoặc PGO profile.

Không dùng native executable cũ để đại diện cho source mới. Không dùng AOT-generated classes cũ sau khi dependency hoặc bean configuration đã thay đổi.

### 13.3. Baseline và regression history

Lưu mỗi run cùng metadata:

- Git commit.
- Build logs và command.
- Artifact checksum.
- Workload script/version.
- Dataset ID.
- Platform/resource limits.
- Raw time series và summary.
- Functional test report.
- Known deviations và decision.

So sánh release hiện tại với baseline đã phê duyệt và release liền trước. Nếu thay đổi lớn, tạo baseline mới nhưng vẫn giữ lịch sử cũ để giải thích xu hướng.

## 14. Ra quyết định chọn mode

| Ưu tiên sản phẩm | Mode cần đánh giá kỹ | Lý do |
| --- | --- | --- |
| Scale-to-zero/cold start | Native Image | Startup và memory lúc khởi động thường là yếu tố quan trọng. |
| Startup tốt nhưng cần JVM ecosystem | JVM + Spring AOT | Dùng generated Spring initialization code và vẫn giữ JVM/JIT. |
| Throughput dài hạn | JVM thường và JVM AOT | JIT có thể tối ưu theo workload khi chạy lâu. |
| Container memory thấp | Native Image và JVM với heap budget phù hợp | So peak RSS/cgroup dưới cùng limit. |
| Runtime flexibility cao | JVM thường | Giữ các quyết định classpath/bean/configuration ở runtime. |
| Native deployment/không có JRE | Native Image | Executable độc lập JVM và gắn với target platform. |
| Cần chuyển đổi từng bước | JVM AOT trước, Native sau | Kiểm tra Spring AOT generated code trước khi compile native. |

Không có một mode tối ưu cho mọi service. Chọn theo SLO, traffic pattern, chi phí build, platform, compatibility và năng lực vận hành của đội ngũ.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi JVM AOT là native | Nhầm rằng JVM AOT không có JIT. | Ghi rõ đây là Spring AOT code chạy trên JVM. |
| So sánh khác commit/dependencies | Không biết chênh lệch đến từ đâu. | Dùng cùng source revision và dependency lock. |
| Dùng AOT profile khác nhau | Tập bean giữa các mode không còn tương đương. | Ghi build-time profile/conditions và dùng cùng AOT assets. |
| Chỉ chạy startup benchmark | Không biết steady-state throughput/latency. | Đo cold start và warm steady-state riêng. |
| Không warm-up JVM | Đánh giá thấp hiệu năng sau JIT. | Dùng warm-up cố định và báo cáo cold-start riêng. |
| Không warm-up Native Image service | Cache/connection startup làm lệch kết quả. | Chạy cùng warm-up sequence cho mọi mode. |
| So heap với RSS | So sánh hai phạm vi memory khác nhau. | Dùng RSS/cgroup cho tất cả; thêm heap metrics để giải thích. |
| Dùng JMH score so với HTTP load test | Hai cấp benchmark không tương đương. | Dùng cùng external harness cho service-level comparison. |
| Dùng health endpoint làm workload duy nhất | Không đại diện business logic. | Dùng request mix và payload thực tế. |
| Bỏ qua downstream | Database/network có thể che khuất runtime effect. | Cố định hoặc đo riêng dependency latency. |
| Chỉ báo cáo average latency | Che khuất tail latency. | Báo p50/p95/p99 và error rate. |
| Chỉ benchmark một lần | Dễ bị ảnh hưởng bởi tải nền. | Lặp lại độc lập và báo độ dao động. |
| Không lưu build provenance | Không tái lập được baseline. | Lưu toolchain, command, artifact checksum và workload version. |

## 16. Bài thực hành: lập baseline ba mode cho Orders Service

**Bối cảnh:** một Orders Service hiện chạy bằng JVM thông thường. Nhóm muốn biết Spring AOT có giảm startup không và Native Image có giảm memory mà vẫn đáp ứng throughput/p99 latency hay không.

### Nhiệm vụ

1. Chọn một Git commit và khóa dependency graph.
2. Ghi Spring Boot, JDK/GraalVM, Maven/Gradle và Native Build Tools versions.
3. Xác định profile, feature flags và properties ảnh hưởng đến bean conditions.
4. Build AOT-generated JAR.
5. Chạy JAR ở JVM thường.
6. Chạy cùng JAR với spring.aot.enabled=true.
7. Build Native Image từ cùng AOT output.
8. Chạy cùng functional test corpus qua ba mode.
9. So sánh response, database state, message output và error behavior.
10. Chỉ mở performance gate khi cả ba mode đạt functional parity.
11. Chạy cold-start test với process/container mới.
12. Chạy warm-up và steady-state test bằng cùng k6/Gatling/wrk workload.
13. Thu startup-to-ready, first-request latency, RPS, p95/p99, errors, CPU, RSS và cgroup peak.
14. Chạy lại nhiều lần theo thứ tự xen kẽ.
15. Tạo bảng kết quả và đánh giá theo SLO.
16. Lưu raw data, artifact checksum, workload script và baseline metadata.
17. Nâng Spring Boot hoặc GraalVM ở một nhánh riêng rồi lặp lại quy trình.
18. Xác định regression do functional behavior, Spring AOT, Native Image compatibility hay runtime performance.

### Hồ sơ kết quả

| Bằng chứng | Nội dung cần lưu |
| --- | --- |
| Source | Git commit và dependency lock/BOM. |
| Toolchain | JDK/GraalVM, Spring Boot, Maven/Gradle và plugin versions. |
| AOT environment | Build profile, feature flags và properties dùng trong processAot. |
| Artifacts | JAR thường, AOT JAR, native executable và checksums. |
| Functional parity | Test corpus, response diff, DB/message side effects và result. |
| Workload | Script, request mix, dataset, concurrency và duration. |
| Environment | CPU, RAM, OS, architecture, container limits và downstream. |
| Startup | Process start, readiness và first request. |
| Performance | Throughput, p50/p95/p99, errors, CPU và memory. |
| Decision | Mode được chọn, SLO đạt được, regression và known limitations. |

### Tiêu chí hoàn thành

- [ ] Giải thích chính xác ba mode JVM thường, JVM AOT và Native Image.
- [ ] Tạo ba artifact/mode từ cùng source và dependency graph.
- [ ] Kiểm soát được profile/condition được đánh giá ở build time.
- [ ] Functional parity tests pass trước benchmark.
- [ ] Có cold-start, first-request và steady-state results.
- [ ] Dùng cùng workload và resource limits.
- [ ] Báo cáo throughput, tail latency, error rate, CPU và RSS/cgroup.
- [ ] Không dùng JMH result thay cho service-level load test.
- [ ] Có nhiều lần chạy độc lập và thống kê độ dao động.
- [ ] Lưu provenance để tái lập baseline sau nâng cấp.
- [ ] Có quyết định chọn mode dựa trên SLO và chi phí vận hành.

## 17. Câu hỏi tự đánh giá

1. JVM AOT trong Spring Boot khác Native Image ở runtime engine như thế nào?
2. Vì sao JVM AOT vẫn có JIT warm-up?
3. spring.aot.enabled=true làm thay đổi phần nào trong quá trình khởi tạo ứng dụng?
4. Vì sao @Profile và @ConditionalOnProperty có thể bị giới hạn khi dùng AOT?
5. Làm thế nào tạo ba mode từ cùng AOT-generated assets?
6. Functional parity cần so sánh những gì ngoài HTTP status?
7. Vì sao cần test reflection, serialization, resource và dynamic proxy trên Native Image?
8. Startup-to-ready khác first-request latency như thế nào?
9. Vì sao JVM cần warm-up nhưng Native Image service vẫn cần warm-up?
10. Vì sao không so JMH score với HTTP load test?
11. Những metric nào có thể so sánh trực tiếp giữa ba mode?
12. Vì sao heap used không thể thay RSS/cgroup memory?
13. Khi nâng Spring Boot/GraalVM, những artifact nào phải được tạo lại?
14. Làm thế nào quyết định chọn JVM, JVM AOT hoặc Native Image theo SLO?

## 18. Tài liệu chính thức

Các lệnh và plugin DSL phụ thuộc Spring Boot, JDK/GraalVM và Native Build Tools version. Hãy kiểm tra tài liệu đúng version của dự án:

- [Spring Boot — Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html): chạy AOT-generated initialization code trên JVM bằng spring.aot.enabled.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): khác biệt giữa JVM deployment, Spring AOT và Native Image.
- [Spring Boot — Maven AOT Plugin](https://docs.spring.io/spring-boot/maven-plugin/aot.html): process-aot, native profile và Maven build integration.
- [Spring Boot — Gradle AOT Plugin](https://docs.spring.io/spring-boot/gradle-plugin/aot.html): org.springframework.boot.aot, processAot và nativeCompile.
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html): kiểm thử AOT trên JVM và native tests.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): startup, JVM, process và HTTP metrics.
- [GraalVM Native Image — Optimizations and Performance](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/): optimization levels, GC, PGO và CPU target.
- [GraalVM Native Image — Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/): build resource usage, executable output và recommendations.
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh): cách tổ chức JVM microbenchmark và các lưu ý khi đo.

**Điểm cần nhớ:** JVM AOT là Spring AOT-generated initialization code chạy trên JVM, vì vậy vẫn có JIT. Native Image là executable được biên dịch AOT và có giới hạn closed-world riêng. Hãy kiểm tra functional parity trước, sau đó benchmark cả cold-start lẫn steady-state bằng cùng source, cấu hình, workload và resource limits; lưu provenance để phép so sánh tiếp tục có giá trị sau mỗi lần nâng cấp.

