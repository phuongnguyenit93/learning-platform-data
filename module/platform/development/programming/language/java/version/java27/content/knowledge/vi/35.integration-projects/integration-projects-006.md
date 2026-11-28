# Thực hiện nâng cấp lên Java 27 với báo cáo tương thích và số liệu hiệu năng

Nâng cấp JDK của một ứng dụng đang chạy không kết thúc khi thay `JAVA_HOME` và thấy server khởi động. Một bản nâng cấp đáng tin cậy phải trả lời **hai câu hỏi bằng bằng chứng**: (1) mã nguồn, thư viện, cấu hình và hành vi nghiệp vụ còn tương thích không; (2) hiệu năng, độ trễ, bộ nhớ và độ ổn định có đáp ứng yêu cầu trong môi trường thực tế không?

Bài thực hành tích hợp này hướng dẫn cách chuyển một dịch vụ Java **từ Java 21 sang Java 27** (hai phiên bản được chọn làm **kịch bản minh họa**, không phải điều kiện bắt buộc của mọi dự án), tổ chức các bước rà soát và lập **báo cáo tương thích kèm số liệu hiệu năng có thể kiểm chứng**. Java 27 đã phát hành chính thức ngày **15/09/2026**; khi thực hiện thực tế, cần chọn **bản cập nhật/bản vá còn được hỗ trợ** của JDK 27, xác minh lifecycle hỗ trợ và chính sách bảo mật phù hợp cho môi trường vận hành.

Bài thuộc chương **Thực hành tích hợp** của module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Các API/công cụ được trình bày dựa trên Java SE/JDK 27 và những phương pháp hiện hành; không hướng người học dùng lại Security Manager, phụ thuộc JDK internals hay bật preview/incubator features như đường nâng cấp production mặc định.

> **Phạm vi:** Đây là bài học mô phỏng quy trình kỹ thuật, **không phải báo cáo đo đạc trên một dự án thật**. Mọi số liệu benchmark trong bảng minh họa đều được gắn nhãn *giả định*. Ví dụ Java chạy độc lập để kiểm tra tính đúng đắn, còn các lệnh build, scan và đo tải cần áp dụng vào artifact/môi trường của người học. Không nên nhầm ví dụ mô phỏng với kết quả đã chạy hoặc được chứng nhận tương thích.

## 1. Đầu ra của bài thực hành: một bản nâng cấp có thể phê duyệt

Đầu ra không chỉ là một pull request thay JDK version. Một gói bằng chứng hoàn chỉnh gồm:

| Nhóm sản phẩm | Nội dung cần có | Vì sao cần? |
| --- | --- | --- |
| **Inventory** | JDK cũ/mới, vendor/build, OS/arch, framework/driver/agents, dependency tree | Biết đã thay đổi những thành phần nào |
| **Compatibility scan** | Báo cáo `jdeps`, `jdeprscan`, compiler warnings, missing classes | Phát hiện sớm API rủi ro và dependency gaps |
| **Remediation log** | Finding, mức độ, owner, replacement, commit, test chứng minh | Theo dõi các vấn đề tới khi đóng |
| **Regression evidence** | Unit, integration, smoke, security và migration tests | Xác minh hành vi ứng dụng chứ không chỉ biên dịch |
| **Performance baseline** | Tải, latency percentiles, throughput, errors, CPU, heap/RSS, GC | Có điểm so sánh trước nâng cấp |
| **Performance candidate** | Các chỉ số tương tự trên Java 27 trong môi trường tương đương | Thấy hiệu ứng của bản nâng cấp |
| **Decision report** | Gate PASS/FAIL, rủi ro còn mở, người chịu trách nhiệm | Có căn cứ go/no-go |
| **Rollout/rollback plan** | Canary, quan sát, ngưỡng dừng, cách quay về runtime cũ | Giảm rủi ro triển khai |

**Điều kiện thành công của bài:** Người học có thể chỉ ra các thay đổi bắt buộc, giải thích sự khác biệt của chỉ số đo, phân biệt kết quả giả định với thực đo và xây dựng quyết định triển khai có điều kiện rõ ràng.

## 2. Bối cảnh giả định và hợp đồng cần bảo vệ

Giả sử hệ thống **Order Quote Service** dùng Java 21 để nhận đơn hàng, tính tổng tiền chính xác và gọi cơ sở dữ liệu/dịch vụ khác. Dịch vụ đang chạy trong container, dùng một JDBC driver và một số thư viện JSON/HTTP.

Mục tiêu của dự án là dùng **Java 27** mà không làm thay đổi giá trị thanh toán, luồng lỗi và hợp đồng API. Bên cạnh kiểm tra chức năng, nhóm muốn biết JVM mới có cải thiện hiệu năng hay tạo ra regression.

<escape>Ví dụ yêu cầu kỹ thuật giả định:</escape>

| Tiêu chí | Mục tiêu acceptance minh họa |
| --- | --- |
| Kết quả tính tiền | Không lệch số tiền và quy tắc làm tròn ở bộ regression |
| API contract | Không thay schema/HTTP status/error mapping ngoài thay đổi đã phê duyệt |
| Tính tương thích | Không còn compile error, unresolved production dependency hoặc JDK internal access chưa chấp thuận |
| Tỷ lệ lỗi | Không tăng quá ngưỡng được thống nhất dưới cùng workload |
| p99 latency | Không tăng quá **10%** so với baseline, và vẫn đạt SLO tuyệt đối |
| Throughput | Không giảm quá **5%** ở cùng ngân sách CPU/RAM và tải |
| Bộ nhớ | Không vượt container memory limit; RSS và allocation có báo cáo |
| GC | Không có Full GC bất thường dưới tải mục tiêu |
| Rollback | Có thể chuyển runtime/artifact về phiên bản đã kiểm chứng mà không làm hỏng dữ liệu |

Các ngưỡng **10%** và **5%** chỉ là ví dụ để hiểu cách lập cổng quyết định. Dự án thực phải chọn theo SLA/SLO, mức biến động tự nhiên của phép đo và mức độ rủi ro.

### 2.1. Tách những thay đổi bắt buộc khỏi thay đổi tối ưu

Không nâng JDK, chuyển ORM, đổi database schema, thay HTTP framework và viết lại toàn bộ concurrency model **cùng một đợt** nếu không bắt buộc. Mỗi thay đổi bổ sung làm việc truy nguyên nguyên nhân lỗi và chênh lệch hiệu năng khó hơn.

Thứ tự ưu tiên:

1. Nâng toolchain/runtime và những dependencies tối thiểu cần thiết để chạy ổn định.
2. Khắc phục API/flags không tương thích, giữ nguyên hợp đồng nghiệp vụ.
3. Chạy các phép kiểm định trước và sau nâng cấp.
4. **Chỉ sau khi đạt compatibility** mới thử các tối ưu có chủ đích, đo tách biệt để biết hiệu quả riêng.

## 3. Ma trận môi trường: giữ biến so sánh dưới kiểm soát

Một benchmark không đáng tin nếu “Java 21” chạy ở máy 4 CPU/4 GiB RAM còn “Java 27” chạy ở máy 16 CPU/16 GiB, hoặc phiên bản ứng dụng khác nhau.

| Thành phần | Baseline A | Candidate B | Quy tắc |
| --- | --- | --- | --- |
| JDK | 21.x bản vá được duyệt | 27.x bản vá được duyệt | **Ghi exact vendor + build** |
| Source revision | Commit A | Commit B chỉ có thay đổi migration cần thiết | Ghi Git SHA, diff scope |
| OS/architecture | Linux x86-64 ví dụ | Cùng OS/architecture | Tránh đổi kernel/ISA trong cùng phép so |
| CPU quota | 4 vCPU | 4 vCPU | Kiểm tra throttling |
| Container memory | 4 GiB | 4 GiB | Không đặt heap bằng toàn bộ memory |
| Heap | `-Xmx2g` | `-Xmx2g` | Cố định cùng chính sách ban đầu |
| GC | G1 | G1 | Xác minh flags thực chạy |
| DB/API mock/data | Dataset và phiên bản cố định | Giống baseline | Kiểm soát độ trễ bên ngoài |
| Traffic | Cùng arrival rate/mix và concurrency | Giống baseline | Không đổi tải giữa hai lần đo |
| Observability | Cùng logging/JFR/metrics policy | Giống baseline | Tránh khác overhead đo |

**Chú ý:** Cùng `-Xmx2g` **không đảm bảo** hai JVM dùng cùng RSS, cùng young gen hoặc cùng hiệu năng. Các mặc định và cách bố trí đối tượng của HotSpot có thể đổi giữa các phiên bản; đó chính là điều cần quan sát.

### 3.1. Ghi lại exact runtime, không chỉ “Java 27”

Các lệnh dành cho máy build/runner:

```shell
java --version
javac --version
jdeps --version
jdeprscan --version
java -XshowSettings:system -version
```

`-XshowSettings:system` giúp quan sát một số thông tin môi trường/cgroup khi runtime hỗ trợ. Kết quả cụ thể tùy OS/JDK vendor. Không lưu bí mật trong command-line options, environment dump hay startup logs.

Với Oracle JDK, lịch phát hành bản vá riêng được công bố trong Release Notes. **Không hardcode một patch version cố định mãi mãi** trong hướng dẫn vận hành: hãy pin bản đã được kiểm thử cho từng đợt và lên lịch cập nhật bản vá bảo mật tiếp theo.

## 4. Tạo baseline trước khi chạm vào code

Trước nâng cấp, ghi nhận hiện trạng:

1. Build artifact ứng dụng trên toolchain cũ có thể lặp lại và lưu checksum.
2. Chạy test suite hiện có; ghi tests pass/fail/skipped và danh sách flaky được xác nhận.
3. Khởi động ứng dụng trong môi trường staging gần production.
4. Chạy workload warm-up và **ít nhất nhiều lượt đo** đủ dài cho JIT/GC ổn định.
5. Thu latency, throughput, error rate, CPU, RSS, heap, allocation và GC.
6. Lưu cấu hình workload, dữ liệu, image, tool versions và các logs dùng để giải thích kết quả.

```text
Baseline A (Java 21, artifact A)
           |
  Source + dependencies + flags
           |
  Run fixed workload / warm-up
           |
    Repeat measured runs
           |
  Application + system + JVM metrics
           |
    Baseline evidence bundle
```

**Đừng đo một lần tải rất ngắn rồi kết luận.** Cache warming, tiered compilation, JIT code cache, GC marking, request bursts và network variance đều có thể làm nhiễu số liệu.

### 4.1. Đo tải gần trải nghiệm thật

Một bộ workload nên có:

- **Normal load:** mức tải ứng dụng thường xử lý.
- **Peak load:** mức đỉnh gần giới hạn SLO.
- **Burst:** tăng đột ngột, kiểm tra hàng đợi và headroom.
- **Soak test:** chạy lâu để phát hiện memory leak, resource leak hoặc GC degradation.
- **Failure mode:** database timeout, downstream lỗi, endpoint chậm và cancellation.

Không cần thực hiện tất cả trong một phép benchmark duy nhất; phải **ghi loại workload** để tránh trộn kết quả của các kịch bản khác nhau.

## 5. Inventory dependencies và vận hành

Một nâng cấp JDK có thể bị chặn bởi một dependency dù source ứng dụng chỉ dùng API public. Lập bảng:

| Nhóm | Ví dụ | Cần kiểm tra |
| --- | --- | --- |
| Web/DI/serialization | Framework HTTP, JSON mapper | Bản release chính thức hỗ trợ JDK 27? Deep reflection? |
| Database | JDBC driver, connection pool | TLS, class loading, query/transaction và timeout |
| Observability | APM/JFR/bytecode agent, profiler | Agent có hỗ trợ JVM 27 và class file format? |
| Security | TLS provider, crypto library | Protocol/cipher/certificate defaults, truststore |
| Native | JNI/FFM, image codec, compression | OS/arch, native access policy và ABI |
| Build | Gradle/Maven plugins, compiler, annotation processors | Toolchain và source/target settings |
| Runtime image | Base image, container entrypoint, JVM flags | Module availability, OS libraries, memory limits |

**Không suy rằng bytecode biên dịch trên Java 8/11 đồng nghĩa thư viện không chạy được trên Java 27.** Nhiều thư viện vẫn tương thích; phải kiểm tra release notes và chạy đường code thật. Ngược lại, một dependency có build mới nhưng còn dùng JDK internals vẫn có thể lỗi ở runtime.

### 5.1. Dependency inventory và SBOM

Nên lưu dependency tree/lockfile hoặc **Software Bill of Materials (SBOM)** từ build system để biết artifact nào được đưa vào runtime, phiên bản và nguồn gốc của chúng. Công cụ `jdeps` không thay thế SBOM: nó mô tả các cạnh phụ thuộc tĩnh trong bytecode, không phải đầy đủ danh mục licenses, CVEs, package provenance hay dependency resolution.

### 5.2. Phân loại thay đổi

| Loại thay đổi | Ví dụ | Cách xác minh |
| --- | --- | --- |
| **Bắt buộc** | Nâng agent không tương thích class files Java 27 | Smoke/integration tests |
| **Có điều kiện** | Cấu hình `--add-opens` tạm thời cho framework cũ | Có owner/thời hạn, test reflection |
| **Cải thiện sau nâng cấp** | Điều chỉnh GC pause goal sau khi có metrics | A/B riêng, không gộp migration |
| **Chưa đưa vào scope** | Preview language feature chỉ để thử nghiệm | Tránh bật không cần trong production |

## 6. Source compatibility, binary compatibility và behavioral compatibility

Ba khía cạnh có thể **cho kết quả khác nhau**:

**Source compatibility**: mã nguồn cũ có thể biên dịch được bằng compiler JDK mới và API đích. Một method đã bị xóa có thể gây lỗi compile.

**Binary compatibility**: bytecode đã biên dịch có thể được JVM/linker tải và liên kết với những class/method signatures cần thiết. Một JAR compile thành công trên JDK cũ vẫn có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError` tại runtime mới nếu dependencies không tương thích.

**Behavioral compatibility**: cùng hành động nghiệp vụ tạo kết quả tương đương theo hợp đồng. Vẫn cần kiểm tra:

- Giá tiền, rounding, thời gian và timezone.
- JSON serialization, HTTP status, message schema.
- TLS/PKI và identity mapping.
- Transaction isolation, query semantics, retry/idempotency.
- Concurrency, ThreadLocal, locking và cancellation.

| Công cụ | Bằng chứng hỗ trợ | Không chứng minh |
| --- | --- | --- |
| `javac` | Source/API/language target và warnings | Runtime business behavior |
| `jdeps` | Class/module dependencies và một phần JDK internals | Reflection/native/resource usage |
| `jdeprscan` | Sử dụng Java SE APIs deprecated trong bytecode | Third-party deprecated API hoặc removed API đã mất metadata |
| Tests | Hành vi thuộc những case đã viết | Những case chưa được kiểm tra |
| Load/JFR/GC | Thời gian, CPU, memory trong workload đã đo | Tất cả môi trường và tải tương lai |

### 6.1. Cẩn trọng với `--release`

Nếu artifact **chỉ phải chạy trên Java 27**, có thể compile với `javac --release 27`. Nếu thư viện **vẫn phải chạy được trên Java 21**, compiler chạy bằng JDK 27 nên dùng `--release 21` để giữ giới hạn ngôn ngữ, public APIs và class-file target của Java 21.

Đừng dùng `-source 21 -target 21` thay cho `--release 21` khi cần chặn việc dùng nhầm API chỉ có trong JDK compiler mới.

## 7. Kiểm tra phụ thuộc với `jdeps`

`jdeps` phân tích **compiled classes/JARs**, không phải source `.java`. Ví dụ giả sử sau build tồn tại `build/libs/order-quote.jar` cùng các dependencies trong `lib/`:

```shell
# Tóm tắt các module/package phụ thuộc tĩnh.
jdeps -summary build/libs/order-quote.jar

# Tìm phụ thuộc vào JDK internal/unsupported APIs.
jdeps --jdk-internals \
  --class-path "lib/*" build/libs/order-quote.jar

# Kiểm tra classes không resolve được.
jdeps --missing-deps \
  --class-path "lib/*" build/libs/order-quote.jar

# Xem module dependencies (để inventory, không thay thế runtime test).
jdeps --print-module-deps \
  --class-path "lib/*" build/libs/order-quote.jar
```

`lib/*` giả định là một **class path wildcard** có ý nghĩa trong môi trường JVM/tool thực tế. Cách resolve nested JARs trong một executable/fat JAR có thể khác: chuẩn bị artifact/library JARs riêng và quét đúng dạng input mà `jdeps` hỗ trợ.

**Phân loại findings**: public dependencies bình thường, JDK internals cần loại bỏ/thay thế, class không resolve cần xử lý. Nếu `jdeps` báo thiếu dependency, **không gọi scan “PASS”** chỉ vì phần còn lại không có internals.

### 7.1. Multi-release JARs

Khi quét library có nhiều bản class files tùy runtime:

```shell
jdeps --multi-release 27 --jdk-internals lib/legacy-library.jar
```

`--multi-release 27` giúp chọn view phù hợp Java 27. Một JAR có thể dùng đường code khác trên Java 21 và 27; vì vậy phải test và phân tích đúng phiên bản runtime.

### 7.2. Khi `jdeps` không thấy vấn đề

Vắng static references không chứng minh không có `Class.forName`, `ServiceLoader`, JNI/FFM, reflection hoặc instrumentation. Các đường nạp động vẫn cần integration tests, đặc biệt với serializers/ORM/bytecode agents.

## 8. Phát hiện API Java SE deprecated với `jdeprscan`

`jdeprscan` tìm việc sử dụng **deprecated Java SE APIs** trong bytecode:

```shell
# Quét theo trạng thái API Java SE 27.
jdeprscan --release 27 \
  --class-path "lib/*" build/libs/order-quote.jar

# Chỉ những API deprecated for removal.
jdeprscan --release 27 --for-removal \
  --class-path "lib/*" build/libs/order-quote.jar
```

`jdeprscan` **không phải scanner chung cho mọi `@Deprecated` trong thư viện bên ngoài**. Nó không tự xác định các APIs đã bị removed khỏi Java SE và cũng không thấy những class được tải hoàn toàn động nếu không có bytecode reference.

Khi tool báo `cannot find class` hoặc resolution errors, bổ sung classpath phù hợp và đánh dấu **scan incomplete**. Không ghi “0 issues” khi chưa giải quyết điều kiện đầu vào.

### 8.1. Ưu tiên báo cáo

| Nhóm kết quả | Mức ưu tiên gợi ý | Hành động |
| --- | --- | --- |
| `forRemoval=true` trong API Java SE | Cao | Thay API hoặc nâng dependency, có regression tests |
| Deprecated API chưa có kế hoạch removal cụ thể | Theo rủi ro | Đọc Javadoc, lên lộ trình |
| API đã removed (compile/linkage failure) | Blocker | Sửa trước khi triển khai |
| Third-party deprecated API | Không phải đầu ra đầy đủ của `jdeprscan` | Dùng compiler/release notes/scanner khác |

## 9. Bật cảnh báo biên dịch bằng `javac` và build tool

Biên dịch source:

```shell
# Với file source mẫu trong thư mục hiện tại.
javac --release 27 \
  -Xlint:deprecation,removal,unchecked,rawtypes \
  -d out UpgradeProbe.java
```

Đây là command **minh họa**. Nếu cần compile Java 21-compatible artifact, thay `--release 27` thành `--release 21` và chỉ dùng APIs phù hợp Java 21.

| Compiler switch | Mục đích |
| --- | --- |
| `--release N` | Cấu hình source/API/class-file target phù hợp release N |
| `-Xlint:deprecation` | Báo usages của API deprecated |
| `-Xlint:removal` | Báo usages API deprecated for removal |
| `-Xlint:unchecked` | Phát hiện unchecked conversions/casts |
| `-Xlint:rawtypes` | Phát hiện raw generic types |
| `-Werror:removal` | Khi đã bật warning tương ứng, chuyển riêng category removal thành lỗi biên dịch |
| `-Werror` | Chuyển mọi warnings được phát ra thành lỗi build |

Với một codebase có warnings cũ, nên bật **report-only** trước, phân loại/khắc phục rồi mới bật `-Werror:removal` hoặc `-Werror` trên source sets đã sạch. `@SuppressWarnings` chỉ ẩn các cảnh báo được nhắm tới, không thay thế sửa code hoặc quản lý rủi ro.

### 9.1. Tích hợp Maven/Gradle

Trong một dự án Maven, `maven-compiler-plugin` có thể cấu hình `release` và `compilerArgs` để cảnh báo xuất hiện ở CI. Với Gradle Java plugin, dùng Java **toolchain** và `tasks.withType<JavaCompile>()` tương ứng. Đảm bảo **build tool/plugin, annotation processors và test framework** hỗ trợ phiên bản JDK thực tế; đừng giữ Gradle/Maven version quá cũ rồi quy mọi lỗi cho Java 27.

Lưu lại command và **exit code** nhưng **không chỉ nhìn exit code** của `jdeps`/`jdeprscan`: một scanner có thể chạy thành công và vẫn in findings. CI gate cần parse/triage có ý thức.

## 10. Những thay đổi của JDK 27 cần đưa vào kế hoạch kiểm chứng

Không phải mọi tính năng được giới thiệu trong Java 27 đều bắt buộc dùng để nâng cấp ứng dụng. Tuy nhiên, một số **mặc định và thay đổi runtime** có thể ảnh hưởng hành vi hoặc hiệu năng dù source không thay đổi.

| Thay đổi trong JDK 27 | Ý nghĩa khi nâng cấp | Cần thử nghiệm |
| --- | --- | --- |
| **G1 mặc định trong mọi môi trường** (JEP 523) | Một môi trường ít CPU/bộ nhớ trước đây có thể chọn collector khác theo ergonomics | Xác nhận collector, GC latency/CPU và RSS |
| **Compact Object Headers mặc định** (JEP 534, HotSpot) | Giảm chi phí header cho nhiều Java objects trên cấu hình hỗ trợ, có thể thay heap footprint | So heap occupancy, allocation/GC, throughput |
| **Cảnh báo sửa `final` field bằng deep reflection** (liên quan JEP 500) | Framework serializer/ORM cũ có thể sinh cảnh báo runtime, hướng tới hạn chế mạnh hơn trong tương lai | Review reflection paths, nâng dependencies, theo dõi warnings |
| **JFR In-Process Data Redaction** (JEP 536) | Thay đổi cách xử lý một số giá trị nhạy cảm trong recording | Kiểm tra observability, vẫn bảo vệ file JFR |
| **TLS 1.3 hybrid post-quantum key exchange** (JEP 527) | Có thể tác động tới negotiation theo khả năng của server và peers | Test TLS tới DB/API/edge/proxy thực tế |
| **TZDB và security updates theo patch release** | Hành vi ngày giờ/validation/trust có thể đổi | Regression tests cho timezone, certificates và integrations |
| **Preview/incubating features** | API/ngữ nghĩa chưa ổn định như features chuẩn | Không tự bật trong ứng dụng production chỉ để “dùng Java 27” |

Danh sách là **những điểm cần xem xét**, không khẳng định mỗi ứng dụng đều chịu tác động. Release notes và migration guide của **đúng JDK vendor/build** là nguồn quyết định phạm vi rà soát.

### 10.1. G1 và compact object headers có thể làm baseline khác đi

Với workload gồm rất nhiều objects nhỏ, compact headers có thể giảm live set và gián tiếp giảm GC pressure. Nhưng **không hứa mọi ứng dụng có throughput tăng**: hiệu ứng phụ thuộc object layout, allocation rate, memory bandwidth, JIT và cách đo.

Khi so Java 21 và 27, hãy ghi **collector thực tế** và những JVM flags đã được chọn. Nếu muốn cô lập riêng ảnh hưởng một tính năng, thiết kế **thử nghiệm phụ sau khi đạt compatibility**, không điều chỉnh một loạt GC flags trong phép so chính.

### 10.2. Cảnh báo deep reflection lên `final` fields

Một số thư viện có thể dùng reflection để ghi vào `final` instance fields. JDK 27 đưa ra cảnh báo nhằm chuẩn bị cho những hạn chế chặt hơn. Không dập cảnh báo bằng cách mở mọi package hay thêm mọi runtime option tìm thấy trên mạng.

Đường xử lý đúng: tìm thư viện/call site, kiểm tra phiên bản hỗ trợ, thay cách tạo object hoặc serialization, và chỉ dùng workaround được tài liệu hóa, có **owner/thời hạn** khi thực sự cần. `jdeps` không đảm bảo thấy thao tác reflection được dựng từ tên `String`.

### 10.3. Bảo vệ dữ liệu JFR dù runtime có redaction

JFR 27 có cải thiện redaction cho command-line arguments và một số giá trị ban đầu từ environment/system properties, nhưng recording vẫn có thể chứa **tên class, paths, endpoints, stack traces, custom events hoặc thông tin nhạy cảm khác**. Phải bảo vệ quyền đọc, nơi lưu, thời hạn giữ và quá trình chia sẻ artifact.

### 10.4. Kiểm tra TLS đúng môi trường

Không chỉ test HTTP client với một certificate giả định. Khi production dùng mTLS, proxy, JDBC TLS, custom truststore hoặc giao thức cũ, hãy chạy handshake thật với cấu hình đáng tin cậy. Không tắt hostname verification hay trust validation chỉ để vượt qua lỗi nâng cấp.

## 11. Chiến lược sửa lỗi tương thích mà không phá nghiệp vụ

Khi có finding, xử lý theo thứ tự:

1. **Xác định nguồn:** application code, generated code, dependency, agent hay runtime config.
2. **Xác định loại:** compile, linkage, deprecation, illegal reflection, protocol, native hoặc thay đổi behavior.
3. **Đọc migration guide/Javadoc/release notes:** biết replacement và khác biệt semantics.
4. **Viết regression test** bao phủ behavior cũ phải giữ.
5. **Thay source/nâng dependency**, không chỉ suppress warning.
6. **Build lại và re-scan** với chính artifact sẽ deploy.
7. **Kiểm thử production-like runtime**, đặc biệt đường lỗi ít gặp.

### 11.1. Ví dụ thay API ngày giờ theo semantics rõ ràng

Một codebase cũ có thể dùng:

```java
// Chỉ để minh họa code cần loại bỏ:
int oldYear = new java.util.Date(timestampMillis).getYear();
```

`Date.getYear()` là API deprecated, trả **năm trừ 1900**, không phải năm dương lịch đầy đủ. Thay đúng theo hợp đồng:

```java
import java.time.Instant;
import java.time.ZoneId;

int calendarYear = Instant.ofEpochMilli(timestampMillis)
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .getYear();
```

`timestampMillis` là biến giả định. Dùng `ZoneId` phù hợp với hợp đồng dữ liệu, **không** thay `Date.getYear()` bằng `LocalDate.now().getYear()` nếu cần năm của một thời điểm lịch sử. Đồng thời không mặc định việc đổi sang giá trị năm đầy đủ là tương thích nếu API công khai trước đó vô tình trả giá trị đã trừ 1900: cần migration contract/test.

### 11.2. Không dùng unsupported API làm cách khắc phục

Đừng đổi một JDK internal API sang `jdk.internal.*` khác hoặc thêm `--add-opens=ALL-UNNAMED` một cách đại trà mà không đánh giá. Chuyển sang public API còn được hỗ trợ, nâng dependency hay chỉnh module declarations đúng phạm vi là chiến lược bền vững hơn.

## 12. Ma trận kiểm thử sau migration

Đừng chỉ có “JUnit tests pass” trong báo cáo:

| Nhóm test | Ví dụ kịch bản | Bằng chứng |
| --- | --- | --- |
| Unit | Tính tiền, rounding, validation, logic ngày giờ | Số lượng tests, passed/failed/skipped |
| API contract | JSON fields/types, status codes, pagination | Contract/schema diff và tests |
| Database | JDBC driver, pool, transactions, rollback, generated keys | Integration logs, DB test results |
| Security | TLS/mTLS, certificate, authentication/authorization | Handshake/negative tests |
| Reflection/module | JSON binding, ORM proxy, annotation processor, dynamic loading | Startup + integration tests trên JDK 27 |
| Serialization | Đọc bản ghi trước migration, tạo bản ghi mới | Golden files/binary compatibility |
| Time zone/locale | DST, date boundaries, format theo khách hàng | Fixed clock, zone-specific test |
| Concurrency | Timeouts, cancellation, ThreadLocal, thread safety | Stress tests/race-sensitive tests |
| Operational | Startup/shutdown, health probes, signal handling, logging | Smoke report trong runtime image thật |
| Performance | Normal/peak/burst/soak workloads | Latency/throughput/CPU/memory/GC report |

**Skipped tests phải có lý do.** Một test tích hợp bị bỏ qua vì thiếu database test có nghĩa là chưa có bằng chứng cho JDBC behavior; không tự cộng nó vào danh sách “passed”.

### 12.1. Golden dataset để phát hiện behavior drift

Giữ một tập input/output bất biến, có đầy đủ tình huống:

- Giá trị thập phân ở ranh giới làm tròn.
- Input rỗng, không hợp lệ, rất lớn.
- Timestamps trong nhiều time zones và giao thoa ngày.
- Records tạo từ phiên bản cũ cần đọc lại.
- Error mapping khi database/API ngoài trả lỗi.

Có thể dùng JSON/CSV có checksum, nhưng cần **không chứa dữ liệu cá nhân/bí mật thật**. Đưa schema version và chính sách so sánh chính xác vào tài liệu.

## 13. Ví dụ chạy độc lập: bộ kiểm tra hành vi trên Java 21 và 27

Tạo file **`UpgradeProbe.java`** bên dưới. Chương trình dùng chỉ các **API chuẩn, ổn định có từ Java 21** để có thể chạy trên cả JDK 21 và 27; nó giúp chứng minh rằng việc nâng runtime **không làm thay đổi logic được kiểm tra**.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;

public final class UpgradeProbe {
    record OrderLine(String sku, BigDecimal unitPrice, int quantity) {
        OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (sku.isBlank()
                    || unitPrice.signum() < 0
                    || quantity < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }
    }

    static BigDecimal quote(List<OrderLine> lines, BigDecimal shipping) {
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(shipping, "shipping");
        if (shipping.signum() < 0) {
            throw new IllegalArgumentException("Invalid shipping fee");
        }

        BigDecimal subtotal = BigDecimal.ZERO;
        for (OrderLine line : lines) {
            subtotal = subtotal.add(
                    line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity())));
        }
        return subtotal.add(shipping)
                .setScale(2, RoundingMode.HALF_EVEN);
    }

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
                new OrderLine("A", new BigDecimal("10.00"), 2),
                new OrderLine("B", new BigDecimal("0.335"), 3));

        BigDecimal total = quote(lines, new BigDecimal("2.50"));
        if (!new BigDecimal("23.50").equals(total)) {
            throw new AssertionError("Unexpected quote: " + total);
        }

        LocalDate date = LocalDate.ofInstant(
                Instant.parse("2026-11-27T00:00:00Z"),
                ZoneOffset.UTC);
        if (!LocalDate.of(2026, 11, 27).equals(date)) {
            throw new AssertionError("Unexpected calendar date");
        }

        boolean rejectedNegativeShipping = false;
        try {
            quote(lines, new BigDecimal("-1.00"));
        } catch (IllegalArgumentException expected) {
            rejectedNegativeShipping = true;
        }
        if (!rejectedNegativeShipping) {
            throw new AssertionError("Missing input validation");
        }

        System.out.println("QUOTE_TOTAL=" + total.toPlainString());
        System.out.println("DATE_UTC=" + date);
        System.out.println("INVALID_SHIPPING_REJECTED=true");
    }
}
```

**Dữ liệu và công thức:** `20.00 + (0.335 × 3) + 2.50 = 23.505`; làm tròn đến hai chữ số thập phân theo `HALF_EVEN` cho `23.50`. Ví dụ cố ý kiểm tra trường hợp hòa ở chữ số làm tròn, giúp phát hiện việc vô tình đổi sang `HALF_UP`.

### 13.1. Biên dịch bằng JDK 27 nhưng giữ Java 21 target

```shell
# Chạy bằng công cụ của JDK 27; tạo class files cho Java 21.
javac --release 21 -d out UpgradeProbe.java

# Chạy với Java 27.
java -cp out UpgradeProbe

# Chạy lại cùng class files với java 21 từ một JDK 21 đã cài.
# Sử dụng đường dẫn /path/to/jdk21/bin/java thực tế.
/path/to/jdk21/bin/java -cp out UpgradeProbe
```

Đầu ra mong đợi ở cả hai runtime:

```text
QUOTE_TOTAL=23.50
DATE_UTC=2026-11-27
INVALID_SHIPPING_REJECTED=true
```

`--release 21` là phần quan trọng khi artifact còn hỗ trợ Java 21. Nếu sản phẩm quyết định **ngừng hỗ trợ Java 21**, có thể build `--release 27` và không cần chạy artifact đó trên JDK 21.

### 13.2. Vì sao không coi đây là performance benchmark?

Chương trình chỉ kiểm tra **đầu ra xác định**. Nó không đo latency, throughput, GC hay memory; kết quả pass **không chứng minh** ứng dụng lớn không bị ảnh hưởng bởi JDK 27. Đây là **smoke/golden test** để nối bước compatibility với bước đo hiệu năng có phương pháp.

### 13.3. Giới hạn của chương trình

Nó không có JDBC, TLS, third-party driver, HTTP server, framework reflection hoặc serialization. Những đường đó phải được kiểm tra bằng **integration tests thực tế** của Order Quote Service; không được ghi “database/TLS PASS” chỉ vì ví dụ `UpgradeProbe` chạy thành công.

## 14. Quy trình build, scan, test và đóng gói thực tế

Trong dự án thật, các lệnh có thể được điều phối qua Maven/Gradle/CI. Ví dụ sơ đồ:

```text
Commit được gắn nhãn
        |
        v
JDK 27 toolchain + dependency lock
        |
        v
Compile + lint + unit tests
        |
        v
Build deployable JAR/container
        |
        +----> jdeps / jdeprscan / findings report
        |
        +----> integration / API / security tests
        |
        +----> performance candidate run
        |
        v
Compatibility & performance evidence
        |
        v
Review và quyết định canary / rollback
```

Tùy build tool, thứ tự “compile → test → package” có thể khác; điều bất biến là **mọi scan/performance test cần gắn với một artifact version xác định**.

### 14.1. Ghi trạng thái từng cổng, không chỉ số lượng tests

| Gate | Điều kiện để PASS |
| --- | --- |
| Build | Compiler thành công, target release đúng hợp đồng |
| Dependency | Runtime graph resolve đầy đủ |
| Static scan | Không có finding blocker, các exceptions còn lại có owner |
| Regression | Chạy đủ bộ bắt buộc; mọi failure được phân loại |
| Integration | DB, TLS, serialization, modules và services thiết yếu có bằng chứng |
| Performance | So sánh đúng workload/môi trường; đạt ngưỡng SLO |
| Security | Không dùng API/flag nguy hiểm không được chấp thuận |
| Operations | Health checks, canary, alerting và rollback được chứng minh |

Một gate có thể là **NOT RUN** hoặc **INCOMPLETE**. Không được coi mặc định chúng là PASS vì không có lỗi nào được in.

## 15. Thiết kế phép đo hiệu năng: so cùng workload, không đoán từ logs

Để trả lời “Java 27 có nhanh hơn không?”, cần phân biệt **đo hiệu năng ứng dụng** và **microbenchmark**:

- **Application/load test:** nhiều requests thực tế qua HTTP/database/cache, đo latency và throughput end-to-end.
- **Microbenchmark:** đo một method/hot path đã được cô lập, dùng **JMH** (*Java Microbenchmark Harness*) với warm-up, forks, iterations và consumption phù hợp. JMH là công cụ OpenJDK **bên ngoài Java SE**, không thay thế load test.

Chạy `System.nanoTime()` quanh một vòng lặp nhỏ hoặc so hai kết quả console **không đủ** để công bố cải thiện hiệu năng JVM. JIT có thể tối ưu bỏ công việc, warm-up chưa ổn, GC hoặc CPU scaling gây nhiễu, và cách đo có thể bỏ qua tail latency thực tế.

### 15.1. Cố định traffic profile

Ví dụ một workload minh họa:

| Endpoint | Tỷ trọng requests | Đặc điểm |
| --- | ---: | --- |
| `POST /quotes` | 55% | Tính tổng, validation, JSON serialization |
| `GET /quotes/{id}` | 30% | Đọc DB/cache |
| `POST /orders` | 10% | Transaction + gọi đối tác |
| `GET /health/ready` | 5% | Health/readiness check |

Tỷ trọng này **không phải dữ liệu thực tế** của sản phẩm. Khi thực hiện, dùng phân bố requests đã được quan sát hoặc một load profile do nghiệp vụ phê duyệt.

### 15.2. Open-loop và closed-loop không tương đương

Nếu một load driver chỉ gửi request tiếp theo **sau khi request trước trả về**, hệ thống chậm sẽ **tự làm giảm số request được gửi**. Phép đo đó dễ che tail latency khi ứng dụng quá tải (*coordinated omission*).

Với mục tiêu đánh giá sức chịu tải tại một **arrival rate cố định**, dùng load generator có khả năng định lịch request arrivals theo thời gian, theo dõi **dropped/scheduled requests** và thời gian chờ. Có thể kết hợp closed-loop tests để mô phỏng tập users có think time, nhưng phải ghi rõ mô hình.

### 15.3. Quy định warm-up và thời gian đo

Một protocol giả định:

1. Khởi động dịch vụ và chờ health/readiness thành công.
2. Warm-up 5 phút (không cộng vào chỉ số đo chính).
3. Đo 10 phút ở normal load.
4. Đo 10 phút ở peak load trong một phép chạy riêng.
5. Chạy tối thiểu 5 repetitions hoặc số lượt đủ để ước lượng độ dao động thực tế.
6. Lưu raw histograms hoặc request-level aggregates có phương pháp percentile chính xác.

**5 phút, 10 phút và 5 repetitions đều chỉ là ví dụ**, phải điều chỉnh theo thời gian JIT/GC ổn định, kích thước tải và độ chính xác yêu cầu. Các thực nghiệm nên được interleave giữa baseline/candidate khi có thể để giảm bias do thời gian/hạ tầng thay đổi.

## 16. Những chỉ số phải thu cùng lúc

| Chỉ số | Ý nghĩa | Điểm dễ bị hiểu sai |
| --- | --- | --- |
| **RPS/throughput** | Requests thành công mỗi giây hoặc operations/giây | Throughput tăng có thể do bỏ qua lỗi/validation |
| **Latency p50/p95/p99** | Phân phối thời gian đáp ứng | Không thể lấy trung bình nhiều giá trị p99 để có p99 toàn bộ |
| **Error/timeout rate** | Tỷ lệ kết quả lỗi và quá hạn | Cần tính cả requests bị từ chối/đánh rơi |
| **CPU utilization** | Mức dùng CPU và throttling | 100% của một quota 2 vCPU khác 100% của 8 vCPU |
| **RSS/container memory** | Tổng memory resident/giới hạn triển khai | `-Xmx` chỉ là heap, không đại diện toàn process |
| **Heap used/committed/live set** | Áp lực bộ nhớ Java | Snapshot thấp không chứng minh không có leak |
| **GC pause p99/max** | Tail latency do stop-the-world GC | Không phải toàn bộ ứng dụng p99 |
| **GC CPU/overhead** | Công GC làm ảnh hưởng throughput | GC còn có work concurrent, không chỉ pauses |
| **Allocation rate** | Mức tạo objects/bytes theo thời gian | Một đợt burst và mức ổn định không tương đương |
| **Startup/readiness time** | Chi phí khởi động, quan trọng cho autoscaling | JIT/heap pre-touch có thể làm trade-off |
| **DB connection pool wait** | Thời gian chờ resources bên ngoài | Có thể là bottleneck dù GC rất tốt |
| **Queue depth/rejections** | Backpressure khi peak/burst | Chỉ ghi thành công có thể che quá tải |

### 16.1. Thu cùng khung thời gian

Đồng bộ timestamps/timezone của service, load generator, database và telemetry. Khi một request p99 tăng, cần biết có **GC pause, CPU throttling, network error hoặc DB wait** cùng thời điểm hay không.

### 16.2. Phân biệt latency của một request và GC pause

Một GC pause 40 ms không nhất thiết tạo thêm đúng 40 ms cho **mọi request**; nó có thể trùng với nhiều requests, chờ OS và các tình huống khác. Vì vậy không tính API latency bằng cách lấy GC pause nhân với số requests. Dùng tracing/histograms để kiểm chứng.

## 17. Ghi GC logs và xác minh collector trước khi so sánh

HotSpot dùng **Unified Logging** qua `-Xlog`, thay vì dựa trên các mẫu cờ GC logging cũ.

Ví dụ khởi động dịch vụ trong môi trường test:

```shell
java \
  -Xms512m -Xmx2g \
  -Xlog:gc*:file=artifacts/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar order-quote.jar
```

`order-quote.jar` và thư mục `artifacts/` phải tồn tại trong dự án thật; lệnh này **không tự tạo** những file/đường dẫn ứng dụng. Các giá trị heap chỉ minh họa và phải nằm trong ngân sách container memory.

### 17.1. Thống kê cần rút từ GC logs

| Dấu hiệu | Cách diễn giải |
| --- | --- |
| `Pause Young`, `Pause Mixed` | Loại G1 collection; xem số lần, p95/p99/max và thời gian |
| `Pause Full` | Thu gom toàn heap có thể kéo dài, điều tra nếu xảy ra dưới tải bình thường |
| `Humongous regions` | Vùng cho objects lớn; xem trend và allocation pattern |
| `Evacuation Failure` | Không di chuyển được một phần objects; kiểm tra headroom/pinning |
| `Concurrent Mark` | Thời gian/tiến độ marking khi ứng dụng còn hoạt động |
| `User/Sys/Real` | CPU time và elapsed time của pha, không đồng nghĩa một metric |

**GC pause p99** của candidate không tự là “cải thiện API p99”; phải xem cả hai và throughput, CPU, allocation, RSS.

### 17.2. Đừng giữ những flags GC cũ chỉ vì đã tồn tại lâu

Mục tiêu của vòng nâng cấp đầu tiên là so baseline/candidate với **chính sách heap/collector có thể giải thích**. Nếu trước đó ứng dụng có rất nhiều flags GC được copy từ một đời JDK cũ, hãy review tính hợp lệ/ý nghĩa với tài liệu Java 27, bỏ flags bị loại bỏ và đánh giá từng flag còn lại.

Nếu cần tách riêng tác động của GC ergonomics mới, tạo một vòng đo phụ sau khi đã có baseline chính, **không đồng thời đổi heap, collector, thread pool và DB size**.

## 18. Thu JFR/JVM diagnostics đúng mục đích

**Java Flight Recorder (JFR)** là công cụ hiện hành trong JDK cho việc thu và phân tích các sự kiện runtime. Với JDK 27, có thể dùng `jcmd` để khởi tạo recording cho một Java process đang chạy, giả sử PID là `12345`:

```shell
# Xác nhận JVM process và flags đang hoạt động.
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info

# Tạo JFR recording 120 giây.
jcmd 12345 JFR.start \
  name=upgrade-review \
  settings=profile \
  duration=120s \
  filename=artifacts/upgrade-review.jfr

# Đọc thông tin summary sau khi file đã ghi.
jfr summary artifacts/upgrade-review.jfr
```

Các lệnh chỉ có thể thực thi nếu máy có JDK tools, quyền attach vào JVM mục tiêu, đủ disk/permission và `artifacts/` đã được chuẩn bị. Với container, có thể cần thực thi công cụ trong đúng namespace/runner hỗ trợ; không mặc nhiên cho `jcmd` truy cập mọi PID trên host.

### 18.1. Các dữ liệu JFR hữu ích

- GC pauses và safepoint behavior.
- Allocation hot spots, object statistics tùy recording settings.
- CPU load, thread scheduling và blocking.
- Socket/file I/O events, tùy loại sự kiện đã bật.
- Thông tin hữu ích để liên hệ với request traces/metrics.

Không nên bật mọi event ở mức chi tiết tối đa trong production mà không đánh giá **overhead và tính nhạy cảm**. Recording có thể chứa tên classes, stacks, paths hoặc custom event payloads.

### 18.2. Phân biệt JFR và heap dump

JFR là dữ liệu sự kiện trong khoảng thời gian; nó **không thay thế** một heap dump khi cần phân tích retained object graph. Heap dump có thể chứa tokens, passwords và dữ liệu cá nhân, đồng thời chiếm nhiều disk và làm gián đoạn ứng dụng. Không tự động tạo heap dump như một phần của benchmark thông thường.

### 18.3. Khi RSS tăng mà heap không tăng

Có thể thu **Native Memory Tracking (NMT)** khi có lý do:

```shell
# Phải bật từ lúc khởi động JVM.
java -XX:NativeMemoryTracking=summary -Xmx2g -jar order-quote.jar

# Sau đó hỏi JVM process phù hợp.
jcmd 12345 VM.native_memory summary
```

NMT có overhead, và không nhất thiết bao phủ mọi native allocation của libraries bên ngoài JVM. Kết hợp với container memory metrics/OS metrics để điều tra RSS, direct buffers, thread stacks và native code.

## 19. Benchmark micro-level bằng JMH khi cần tìm nguyên nhân

Khi load test cho thấy candidate có throughput giảm nhưng chưa biết hot path nào thay đổi, có thể tạo **JMH benchmark** riêng cho đoạn CPU-bound cụ thể (serialization, hashing, parsing, mapping...). Không dùng một vòng lặp với `System.nanoTime()` trong `main` rồi công bố JVM nào nhanh hơn.

Một skeleton có thể dùng sau khi đã tạo **dự án JMH hợp lệ** bằng archetype chính thức:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class QuoteBenchmark {
    private final BigDecimal price = new BigDecimal("0.335");
    private final BigDecimal quantity = BigDecimal.valueOf(3);

    @Benchmark
    public BigDecimal calculate() {
        return price.multiply(quantity)
                .add(new BigDecimal("2.50"))
                .setScale(2, RoundingMode.HALF_EVEN);
    }
}
```

**Chú ý:** Đây không phải một benchmark build được chỉ với JDK. Cần JMH dependencies và **annotation-processing/bytecode generation** theo archetype/build configuration chính thức; JMH là tool riêng thuộc OpenJDK Code Tools.

### 19.1. Vì sao cần JMH?

JMH quản lý nhiều pitfalls thường gặp của microbenchmark:

- Warm-up để JIT có cơ hội biên dịch theo profile.
- Nhiều forks để giảm tác động state của JVM process.
- Measurement iterations, sampling/mode và confidence phù hợp.
- Tiêu thụ/đưa kết quả ra khỏi vùng có thể bị dead-code elimination.
- State scope và setup để đo đúng công việc cần quan tâm.

Không có nghĩa JMH tự bảo đảm benchmark không lỗi: workload, kiểu state, parameter inputs và cách tiêu thụ output vẫn phải được review.

### 19.2. Kết quả microbenchmark không đại diện toàn dịch vụ

Một phép tính BigDecimal nhanh hơn 12% trong JMH **không hứa** API HTTP nhanh hơn 12%. Service có thể bị giới hạn bởi DB/network, JSON parsing, garbage collection hoặc queueing. Chỉ dùng microbenchmark làm **bằng chứng hỗ trợ điều tra**; quyết định phát hành vẫn dựa vào **end-to-end workload/SLO**.

## 20. Thu số liệu có tính lặp lại: thiết kế A/B thay vì chọn số đẹp

Một số nguyên tắc:

1. **Cùng dữ liệu, image/environment và nguồn tải**; ghi exact versions/hashes.
2. **Không chạy hai dịch vụ tranh chấp cùng CPU/RAM/DB không kiểm soát** nếu điều đó làm nhiễu.
3. **Warm-up đầy đủ** và không tính startup vào latency steady-state trừ khi đang đo startup riêng.
4. Chạy **nhiều lượt**; ghi từng lượt thay vì chỉ giữ lần tốt nhất.
5. Tránh so B chạy buổi sáng với A chạy một tuần trước trên máy hạ tầng khác; cân nhắc thứ tự `A → B → B → A` hay interleaving khác khi môi trường cho phép.
6. Ghi requests đã scheduled/sent/completed/failed/timeout/dropped để phát hiện benchmark driver quá tải.
7. Đảm bảo **client/load generator có headroom**; nếu chính nó chạm CPU/network limit, kết quả đo là khả năng của load generator chứ không phải service.
8. Với percentiles, dùng histogram/request-level measurements đúng phép tổng hợp; **không lấy trung bình p99 từng phút** rồi gọi đó là p99 chung.

### 20.1. Biến động có thể lớn hơn mức cải thiện

Nếu lần chạy A cho p99 lần lượt 225, 245, 230 ms còn B cho 224, 235, 233 ms, việc chỉ chọn `245 → 224` để tuyên bố cải thiện 8,6% là không đúng phương pháp.

Hãy báo **phân phối theo nhiều lượt**, sample counts, median/IQR hoặc confidence interval khi đủ điều kiện. Nếu chênh lệch tương đương độ nhiễu, kết luận đúng là **chưa có bằng chứng đáng tin cậy về thay đổi**, không phải “Java 27 chắc chắn nhanh hơn”.

### 20.2. SLO tuyệt đối và so với baseline phải đồng thời đạt

Giả sử p99 giảm từ 600 xuống 500 ms, nhưng SLO yêu cầu p99 dưới 250 ms. Đó là **cải thiện tương đối** nhưng vẫn **FAIL** về mục tiêu tuyệt đối. Ngược lại, p99 từ 100 lên 108 ms vẫn dưới SLO 250 ms nhưng có thể vi phạm policy “không regress quá 5%”. Cần công bố rõ cả hai cổng.

## 21. Công thức tính báo cáo hiệu năng

**Throughput của requests thành công**:

\[
\text{success RPS} = \frac{\text{số requests thành công}}{\text{thời gian đo (giây)}}
\]

**Error rate** (theo định nghĩa cần ghi trước, ví dụ mọi failures/timeouts/rejections chia cho mọi requests dự kiến):

\[
\text{error rate (\%)} =
\frac{\text{failed + timed out + rejected}}{\text{total scheduled attempts}} \times 100
\]

**Phần trăm thay đổi của chỉ số**:

\[
\Delta_{\%} = \frac{B-A}{A} \times 100
\]

Trong đó `A` là baseline, `B` là Java 27 candidate. `A` phải khác 0. Chỉ số **càng thấp càng tốt** như latency/CPU/RSS: `Δ% < 0` thường là cải thiện nếu không làm hỏng mục tiêu khác. Chỉ số **càng cao càng tốt** như sustainable throughput: `Δ% > 0` thường là cải thiện.

### 21.1. Tách throughput ở tải cố định khỏi năng lực tối đa

Khi load generator gửi **3.000 requests/giây** và cả hai runtime đều xử lý thành công gần hết, throughput của A và B sẽ **gần bằng nhau**; không thể từ đó kết luận chúng có cùng **năng lực cực đại**. Để so headroom, chạy một bài **capacity test riêng**, tăng arrival rate có kiểm soát đến ngưỡng SLO/errors của mỗi runtime.

Những con số “capacity RPS” chỉ có ý nghĩa khi tiêu chí xác định **sustainable capacity** giống nhau, ví dụ “mức tải cao nhất duy trì 10 phút mà p99 và error rate vẫn đạt ngưỡng”.

### 21.2. Dữ liệu bị từ chối không được biến mất

Nếu A nhận 3.000 requests/giây nhưng chỉ có 2.500 thành công còn B thành công 2.950, không được chỉ tính latency của 2.500/2.950 thành công và bỏ qua phần bị timeout/đánh rơi. Cần báo riêng **success latency, error rate, completed vs scheduled throughput** để tránh ảo giác ứng dụng nhanh hơn nhờ từ chối công việc.

## 22. Bảng báo cáo minh họa: dữ liệu giả định, không phải benchmark đã chạy

Các số liệu dưới đây được **tạo để hướng dẫn cách đọc báo cáo**. Giả sử hai runtime cùng nhận normal-load arrival rate **3.000 req/s**, đo đủ warm-up/repetitions, đồng thời có capacity test riêng:

| Chỉ số minh họa | Java 21 (A) | Java 27 (B) | Thay đổi |
| --- | ---: | ---: | ---: |
| Scheduled arrival rate | 3.000 req/s | 3.000 req/s | 0% |
| Successful throughput | 2.997 req/s | 2.997 req/s | 0% |
| Error/timeout/rejection | 0,10% | 0,10% | 0 điểm % |
| API p50 | 46 ms | 43 ms | -6,5% |
| API p95 | 145 ms | 138 ms | -4,8% |
| API p99 | 240 ms | 225 ms | -6,25% |
| Process CPU utilization | 72% | 68% | -4 điểm % |
| Peak container RSS | 1,78 GiB | 1,64 GiB | -7,9% |
| GC pause p99 | 43 ms | 35 ms | -18,6% |
| Max sustainable RPS (capacity test riêng) | 3.900 | 4.050 | +3,85% |

Diễn giải đúng:

- Ở **cùng normal arrival rate**, Java 27 cho p99 thấp hơn, CPU và RSS thấp hơn trong bảng minh họa.
- **Successful throughput ở tải cố định không tăng**, vì cả hai đều đã phục vụ gần toàn bộ tải gửi tới.
- Capacity test riêng cho thấy số RPS tối đa ở cùng SLO có thể tăng 3,85%; **không** lấy con số đó ghép thành throughput của kịch bản normal load.
- Một kết quả tốt ở normal load **không chứng minh** candidate đạt peak-load SLO.

### 22.1. Ví dụ gate FAIL dù normal load cải thiện

Một phép chạy peak-load riêng có dữ liệu giả định:

| Kịch bản peak | Java 21 (A) | Java 27 (B) |
| --- | ---: | ---: |
| API p99 | 280 ms | 325 ms |
| Tăng p99 tương đối | — | **+16,1%** |
| Policy regression tối đa | — | **+10%** |

Nếu acceptance gate quy định `p99 không tăng quá 10%`, candidate **FAIL** ở peak load dù normal load tốt hơn. Quyết định hợp lý là **NO-GO** cho tới khi xác định nguồn regression và chạy lại toàn bộ nhóm kiểm tra bắt buộc.

Các mức 280/325 ms là **số giả định** để minh họa cách đưa ra quyết định, không phải nhận xét rằng Java 27 kém hơn Java 21 trong thực tế.

### 22.2. Sử dụng độ bất định trong quyết định

Nếu mức chênh lệch 1–2% trong khi kết quả giữa các lần chạy dao động ±8%, hãy ghi **INCONCLUSIVE**, kéo dài đo/ổn định hạ tầng thay vì tuyên bố PASS về “hiệu năng tăng”. Các ngưỡng gate nên có chính sách xử lý **sample size, confidence/variance và outliers** được thống nhất trước.

## 23. Cấu trúc báo cáo cuối cùng để người review có thể quyết định

Một **báo cáo nâng cấp** nên có phần máy đọc được (CSV/JSON/CI attachments) và phần giải thích cho con người:

```text
Upgrade Assessment
  1. Scope & owners
  2. Runtime/build/dependency inventory
  3. Compatibility findings & remediation
  4. Regression/integration/security test results
  5. Workload & measurement protocol
  6. Baseline vs candidate metrics
  7. Risks, exceptions & unknowns
  8. Go/No-go gates
  9. Rollout, rollback, monitoring
 10. Reproducibility appendix
```

### 23.1. Mẫu thông tin cốt lõi

| Trường báo cáo | Ví dụ điền (giả định) |
| --- | --- |
| Target JDK | Java 27.x, vendor/build được khóa trong CI |
| Baseline JDK | Java 21.x, vendor/build được khóa trong CI |
| Application revision | SHA của artifact baseline/candidate |
| Dependency scan | `jdeps` 0 blocker **sau khi classpath hoàn chỉnh** |
| Deprecated API scan | `jdeprscan` 2 findings, 2 fixed, 0 accepted |
| Compiler | No errors, removal warnings 0 |
| Regression | 612 passed, 0 failed, 3 skipped có lý do |
| DB/TLS/module integration | PASS với các case đã ghi trong test inventory |
| Normal-load | PASS theo metrics ở bảng minh họa |
| Peak-load | FAIL do p99 tăng 16,1% trong ví dụ |
| Open risks | Điều tra peak latency, owner/perf ticket |
| Decision | **NO-GO** cho tới khi xử lý peak regression |

Các số lượng `612/3` và `2 findings` chỉ là ví dụ về cách lập bảng, **không phải kết quả đã thu thập**. Khi dùng thật, mỗi kết quả phải dẫn tới CI run, log/report và artifact hash.

### 23.2. Không “làm xanh” bằng cách bỏ test hoặc bỏ field

Nếu scan chưa resolve đủ dependencies, ghi **SCAN INCOMPLETE**. Nếu database integration không chạy, ghi **NOT RUN**. Nếu p99 vượt gate, ghi **FAIL**. Trạng thái “không có dữ liệu” không được gộp với “đã kiểm tra và pass”.

## 24. Điều tra regression trước khi kết luận do Java 27

Trong ví dụ peak load ở mục 22, p99 tăng từ 280 lên 325 ms. Đây là **tín hiệu cần điều tra**, không tự chứng minh JDK 27 là nguyên nhân trực tiếp. Kiểm tra theo nhánh:

```text
Peak p99 candidate tăng
           |
     CPU bị giới hạn?
       /        \
     có         không
     |            |
  CPU/GC/JIT   DB/pool wait tăng?
                  /        \
                có         không
                |            |
          DB/query/locks   GC/safepoint?
                               /       \
                             có       không
                             |           |
                     Allocation/GC    Network,
                     and JVM flags    queue, app
                               \       /
                                v     v
                      Isolate + reproduce
                                |
                         Test one change
                                |
                        Repeat A/B runs
```

### 24.1. Một số nguyên nhân thường gặp

| Dấu hiệu | Phép đo cần kiểm tra | Không nên làm ngay |
| --- | --- | --- |
| p99 cao cùng thời điểm DB pool wait | Active connections, borrow wait, slow queries | Tăng heap JVM vô điều kiện |
| CPU throttling ở candidate | Cgroup quota, CPU time, run queue | Quy lỗi cho G1 chỉ vì có GC |
| GC pauses thực sự tăng | `-Xlog:gc*`, JFR, live set, humongous regions | Chỉnh nhiều GC flags đồng thời |
| RSS tăng mà heap không tăng | NMT, direct buffers, native threads | Tăng `-Xmx` |
| Startup chậm hơn | Class loading, JIT warm-up, pre-touch, module resolution | Dùng steady-state benchmark để kết luận startup |
| Bất thường chỉ ở TLS | Handshake trace, cipher/protocol/provider | Tắt certificate validation |
| Reflection warnings | Framework/agent version, deep access code | Thêm `--add-opens` toàn hệ thống không thời hạn |
| Latency tăng theo số requests đang chờ | Queue length, admission/backpressure, error counts | Chỉ tính requests thành công rồi bỏ drops |

### 24.2. Cách kiểm tra giả thuyết

Đặt giả thuyết cụ thể, ví dụ “candidate có thêm allocation do dependency JSON mapper đã được nâng cùng JDK”. Sau đó:

1. So phụ thuộc và app commits để biết JSON mapper có thật sự đổi.
2. Chụp allocation profile ở **cùng workload**.
3. So hot paths/JFR events và GC metrics, giữ nguyên các yếu tố khác.
4. Thử đưa dependency về phiên bản tương thích đã kiểm chứng (nếu khả thi) hoặc dùng một bản sửa tách biệt.
5. Chạy lại đủ repetitions; nếu chênh lệch biến mất, ghi bằng chứng liên hệ.

Đừng dựa vào một correlation ngẫu nhiên để kết luận causation.

## 25. Quy trình rollout canary và rollback có điều kiện

Khi **tất cả gate bắt buộc đã PASS**, có thể dùng một đợt triển khai theo giai đoạn:

```text
Approved artifact + JDK 27 image
                |
           Staging smoke
                |
         Canary 1% traffic
                |
         Monitor agreed SLOs
                |
         Canary 5% -> 25%
                |
          Full rollout 100%
                |
       Post-deployment review

Nếu gate FAIL ở bất kỳ giai đoạn nào:
  -> Stop promotion
  -> Rollback runtime/artifact when safe
  -> Capture evidence
```

Các tỷ lệ **1%, 5%, 25%, 100%** chỉ minh họa. Hệ thống thật có thể rollout theo instance, vùng, tenant hoặc traffic class. Quan trọng là có **cơ chế quan sát và điều kiện dừng trước khi bắt đầu**.

### 25.1. Những chỉ số canary phải theo dõi

- Tỷ lệ HTTP 5xx/4xx bất thường, timeouts và request rejections.
- p95/p99 latency theo endpoint và traffic class, so với control.
- CPU throttling, RSS/container restarts, OOMKilled.
- GC pause distribution và Full GC events.
- DB pool acquisition wait/timeout, TLS/auth failures.
- Số lượng errors mới trong logs: linkage, reflection, native agent.
- Startup/readiness, graceful shutdown và rollback time.

**Một canary quá nhỏ** có thể không nhận đủ traffic để thấy lỗi peak-load hoặc chu kỳ GC đặc biệt. Cần kết hợp canary với performance test trước đó, theo dõi đủ thời gian/khối lượng theo rủi ro.

### 25.2. Thế nào là một rollback an toàn?

“Đổi image về Java 21” chỉ an toàn nếu ứng dụng mới **chưa** tạo dữ liệu, schema, tokens hoặc messages không tương thích ngược. Kiểm tra:

1. Database migrations có tương thích cả phiên bản cũ và mới trong cửa sổ rollback không?
2. JSON/binary serialization có giữ khả năng đọc bởi bản cũ không?
3. Key/certificate/token formats có bị thay đổi không?
4. Thư viện mới có ghi storage state mà code cũ không hiểu không?
5. Dependencies/runtime image cũ còn có sẵn và vẫn được duy trì an toàn trong giai đoạn chuyển tiếp không?

Nếu các thay đổi state không thể đảo ngược, **rollback code đơn thuần không đủ**. Cần chiến lược expand/contract schema, compatibility window hoặc kế hoạch phục hồi khác đã được phê duyệt.

### 25.3. Tách rollback do chức năng và rollback do hiệu năng

Nếu một regression gây sai số tiền hoặc lộ dữ liệu, đó là blocker nghiêm trọng. Nếu chỉ có chênh lệch hiệu năng nhỏ trong phạm vi policy đã duyệt, có thể không cần rollback. Đặt ngưỡng **nghiêm trọng theo impact** thay vì một rule duy nhất cho mọi metric.

## 26. CI/CD gates: cho máy kiểm tra, để người phụ trách giải thích

Một pipeline có thể được chia thành:

```text
Stage 1. Build/test
  - Pin JDK 27 vendor/build
  - Compiler --release target + -Xlint
  - Unit tests + style/static quality

Stage 2. Artifact review
  - Dependency inventory/SBOM
  - jdeps internals & missing-deps
  - jdeprscan --release 27 and --for-removal
  - Known API/launch-option compatibility checks

Stage 3. Integration
  - Database, TLS, HTTP, serialization, agents
  - Staging startup/shutdown and health

Stage 4. Performance
  - Reuse identical workload configuration
  - Export raw/load + JVM metrics and reports
  - Evaluate SLO and confidence/variance

Stage 5. Decision
  - PASS/FAIL/INCOMPLETE evidence by gate
  - Review exceptions and owner signatures
  - Approve canary/rollback playbook
```

### 26.1. Quy tắc không cho “unknown” thành “pass”

| Scan/test outcome | Trạng thái | Có được release? |
| --- | --- | --- |
| Test chạy và assertions pass | **PASS** | Có thể, nếu các gate khác đạt |
| Test chạy và fail | **FAIL** | Không nếu là gate bắt buộc |
| Test không chạy do thiếu môi trường | **NOT RUN** | Không nếu là gate bắt buộc |
| Scanner thiếu class/dependency để phân tích | **INCOMPLETE** | Phải bổ sung input hoặc exception được phê duyệt |
| Finding đã được chấp nhận có owner/thời hạn | **ACCEPTED RISK** | Phụ thuộc policy, không tự động PASS |
| Performance variance quá lớn | **INCONCLUSIVE** | Cần đo lại nếu gate bắt buộc |

Một pipeline “xanh” chỉ vì lệnh quét trả exit code 0 **không chứng minh** kết quả tương thích. CI nên kiểm tra **scan completeness, findings severity và dữ liệu của đúng artifact**.

### 26.2. Không tự động xóa mọi cảnh báo

Ở source của chính ứng dụng, `javac -Werror:removal` có thể ngăn API for-removal quay lại. Với thư viện binary, cần `jdeprscan` và vendor inventory riêng. Với reflection/native, cần integration tests; suppress warnings hoặc dùng flags mở toàn bộ modules chỉ là workaround có rủi ro.

## 27. Kịch bản luyện tập có tiêu chí chấm kết quả

Áp dụng vào một service hoặc artifact thử nghiệm do người học kiểm soát. Không cần dùng dữ liệu thật của người dùng; ưu tiên staging dataset đã ẩn danh.

**Bài tập A — Compatibility inventory**

1. Chọn baseline JDK và Java 27 candidate, ghi vendor/build/OS/flags.
2. Tạo hoặc chọn artifact ứng dụng; ghi dependency inventory.
3. Chạy `jdeps --jdk-internals` và `--missing-deps` với classpath đầy đủ.
4. Chạy `jdeprscan --release 27` và `--for-removal`.
5. Bật `-Xlint:deprecation,removal,unchecked,rawtypes` ở build.
6. Tạo bảng finding gồm source/artifact, severity, owner, action và status.

**Tiêu chí hoàn thành:** Không kết luận scan PASS khi còn lỗi resolve; xác định ít nhất một loại finding theo đúng tool output hoặc ghi “không phát hiện trong phạm vi đã quét”, không tự bịa findings.

**Bài tập B — Regression**

1. Biên dịch `UpgradeProbe.java` bằng `--release 21` trên JDK 27.
2. Chạy class files ấy trên Java 21 và Java 27.
3. So toàn bộ output gồm tổng tiền, ngày UTC, input validation.
4. Bổ sung ít nhất ba test case biên của ứng dụng mình (rounding, date boundary, exception).

**Tiêu chí hoàn thành:** Output ứng dụng được kiểm tra bằng asserts hoặc so sánh snapshot, không dựa vào việc process chỉ exit 0 mà không xác minh kết quả.

**Bài tập C — Performance report**

1. Chọn một workload normal và một workload peak.
2. Giữ dữ liệu, CPU/RAM, JVM flags và load protocol tương đương.
3. Thu nhiều lượt latency, throughput, errors, CPU, RSS, heap và GC.
4. Tính `Δ%` theo bảng cùng với độ biến động.
5. Đánh giá từng acceptance gate và viết **GO/NO-GO/INCONCLUSIVE**.

**Tiêu chí hoàn thành:** Nêu rõ dữ liệu nào **thực đo** và dữ liệu nào **chưa đo/giả định**; có raw reports, số lượt chạy, artifact/JDK build và lý do quyết định.

## 28. Lỗi thường gặp trong một dự án nâng cấp có benchmark

| Anti-pattern | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ đổi `JAVA_HOME` rồi tuyên bố tương thích | Bỏ qua runtime/dependency behavior | Build, scan, regression và integration tests |
| Không khóa exact JDK vendor/build | Khó lặp lại kết quả | Pin và lưu toolchain versions |
| Quét source bằng `jdeps` | Sai input (cần bytecode) | Build artifact trước |
| Dùng `jdeprscan` để kết luận mọi third-party API sạch | Tool chỉ quét Java SE deprecations | Compiler/vendor inventory |
| Bỏ qua `cannot find class` của scanner | Báo cáo thiếu dữ liệu | Sửa classpath/module path |
| Dùng `--release 27` cho thư viện vẫn cần Java 21 | Làm mất backward compatibility | `--release 21`, test cả hai runtimes |
| Đổi framework, DB, GC và JDK trong một lần | Không biết nguyên nhân regression | Giảm phạm vi thay đổi hoặc phân lớp thí nghiệm |
| Chỉ so thời gian chạy một vòng lặp nhỏ | JIT/optimization/measurement bias | Dùng JMH cho microbenchmark và load test end-to-end |
| Không warm-up JVM | So sánh JIT/classloading thay vì steady state | Ghi riêng startup và steady-state |
| Load generator bị CPU-bound | Đo năng lực client thay vì server | Kiểm tra headroom và dropped requests |
| Chỉ đo successful requests | Che timeouts/rejections | Báo đầy đủ scheduled/completed/failed |
| Lấy trung bình p99 từng phút | Không cho p99 toàn tập đúng | Dùng raw histogram/đúng phép tổng hợp |
| Tăng `-Xmx` bằng 100% RAM container | Có thể OOMKilled vì native memory | Dành headroom và đo RSS |
| Chọn lần chạy tốt nhất | Cherry-picking | Nhiều repetitions và báo variance |
| Thấy normal-load cải thiện thì bỏ qua peak-load FAIL | Phát hành regression | Giữ tất cả gate bắt buộc |
| Coi JFR không có dữ liệu nhạy cảm | Có thể rò runtime/context | Phân quyền và retention |
| Coi `-Werror` là giải pháp tự sửa code | Chỉ làm build fail | Triage và remediation có owner |
| Tắt TLS verification để qua integration | Rủi ro bảo mật nghiêm trọng | Sửa truststore/certificates đúng |
| Quên schema/serialization rollback | Bản cũ không đọc được state mới | Expand/contract và rollback test |
| Ghi số giả định như thể đo thật | Báo cáo sai lệch, quyết định không đáng tin | Gắn nhãn minh họa và dẫn chứng thực đo |

## 29. Checklist go/no-go trước khi đưa Java 27 vào production

1. **JDK mới có đúng phiên bản/bản vá được duyệt không?** Đã xác minh thời hạn hỗ trợ và lịch cập nhật chưa?
2. **Cùng source/dependency scope đã được ghi rõ chưa?** Có SHA và artifact checksum?
3. **Build targets đúng Java release mà sản phẩm phải hỗ trợ chưa?**
4. **Dependency tree/SBOM có hoàn chỉnh, bao gồm agents và native libraries không?**
5. **`jdeps` có phát hiện internals, missing dependencies hoặc lỗi module chưa xử lý không?**
6. **`jdeprscan --release 27` và `--for-removal` đã chạy trên artifacts thích hợp chưa?**
7. **Compiler đã bật các warning categories cần thiết chưa?** Có bao nhiêu findings còn mở?
8. **Các findings nghiêm trọng đã có owner, PR sửa và test chứng minh chưa?**
9. **Đã xem JDK 27 Release Notes cho GC, compact headers, final-field reflection và TLS chưa?**
10. **Framework/ORM/JSON/JDBC/agents có xác nhận hỗ trợ Java 27 hoặc được kiểm thử tương ứng chưa?**
11. **Regression suite có bao phủ tiền, ngày giờ, validation và API contracts không?**
12. **DB transactions/connection pool, TLS và serialization integration tests đã PASS chưa?**
13. **Startup/readiness/shutdown trên đúng container image mới đã đạt chưa?**
14. **Load generator có đủ tài nguyên để đo, không bỏ requests mà không ghi nhận chưa?**
15. **Có normal/peak/soak workload phù hợp, warm-up và repetitions đủ chưa?**
16. **Báo cáo có p50/p95/p99, RPS, errors, CPU, RSS, heap, GC và sample counts không?**
17. **Đã tách fixed-load throughput khỏi sustainable capacity chưa?**
18. **JFR/GC logs và metrics có cùng khung thời gian và quyền truy cập phù hợp không?**
19. **Độ biến động giữa các lượt đo có đủ thấp để kết luận không?**
20. **Tất cả gate tuyệt đối và tương đối có PASS không?** Gate nào NOT RUN/INCOMPLETE?
21. **Có một decision record rõ ràng: GO/NO-GO/INCONCLUSIVE và lý do không?**
22. **Canary có ngưỡng dừng, người trực và dashboards phù hợp chưa?**
23. **Rollback có tương thích database schema, serialized data và credentials không?**
24. **Có bằng chứng thử rollback, không chỉ một ý tưởng trên giấy không?**
25. **Tất cả numbers trong báo cáo đều có nguồn/measurement hoặc nhãn giả định không?**

## 30. Tổng kết

Một dự án nâng cấp lên **Java 27** chỉ đáng tin cậy khi kiểm chứng được **tương thích và hiệu năng trong cùng một hồ sơ bằng chứng**. `jdeps`, `jdeprscan` và compiler warnings giúp phát hiện rủi ro sớm; regression/integration tests xác nhận những hành vi cần giữ, còn load testing/JFR/GC telemetry chỉ ra ảnh hưởng thực tế lên latency, throughput, CPU và bộ nhớ.

Mục tiêu không phải làm mọi con số đều “đẹp hơn Java 21”. Mục tiêu là **đúng hợp đồng, an toàn vận hành, đạt SLO và có thể rollback**. Một bản nâng cấp có p99 tốt hơn ở normal load nhưng vi phạm peak-load gate vẫn là **NO-GO** cho tới khi được xử lý hoặc policy được phê duyệt thay đổi có căn cứ.

Quy trình bền vững là **pin môi trường → baseline → inventory/scan → remediation → regression → đo tải lặp lại → báo cáo rõ PASS/FAIL/UNKNOWN → canary/rollback**. Đây cũng là phương pháp có thể áp dụng cho các phiên bản JDK tiếp theo, thay vì sao chép một bộ flags hoặc kết luận cảm tính về JVM.

## Tài liệu tham khảo

- [Oracle — JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — các thay đổi, cảnh báo tương thích và tính năng trong JDK 27 GA.
- [Oracle — Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — các bản vá và ghi chú thay đổi trong họ JDK 27.
- [Oracle — Java SE 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/index.html) — quy trình migration, removed APIs, security và thay đổi runtime.
- [Oracle — Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — G1 default, compact headers, JFR redaction, final-field warnings và các thay đổi nổi bật.
- [Java SE 27 — jdeps](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html) — phân tích dependency graph, JDK internals và multi-release JAR.
- [Java SE 27 — jdeprscan](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html) — quét API deprecated trong Java SE bytecode.
- [Java SE 27 — javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--release`, `-Xlint` và `-Werror`.
- [Java SE 27 — java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — heap, runtime options, GC logs và môi trường.
- [Java SE 27 — jcmd](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — JVM flags, heap information và JFR command.
- [Java SE 27 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html) — JFR, NMT và chẩn đoán runtime.
- [Java SE 27 — G1 GC Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html) — G1 pause/throughput tuning và diagnostics.
- [OpenJDK — JMH](https://github.com/openjdk/jmh) — chuẩn bị, chạy và phân tích JVM microbenchmarks.
- [OpenJDK — JEP 523](https://openjdk.org/jeps/523), [JEP 534](https://openjdk.org/jeps/534), [JEP 536](https://openjdk.org/jeps/536) — G1 mặc định, compact object headers và JFR redaction.
