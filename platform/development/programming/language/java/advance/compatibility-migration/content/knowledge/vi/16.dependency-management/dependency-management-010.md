# Tránh nâng cấp đồng loạt không có bằng chứng kiểm thử

Trong quá trình **Java Advance Compatibility Migration**, việc chuyển sang JDK mới thường dẫn đến một danh sách dài thư viện và plugin được đề xuất nâng cấp: logging, HTTP client, JDBC driver, JSON serializer, ORM, test framework, Gradle plugin, bytecode enhancer, Java agent và nhiều dependency bắc cầu. Khi nhìn thấy hàng loạt phiên bản cũ, nhóm có thể muốn “nâng tất cả lên bản mới nhất” trong một pull request rồi xử lý những lỗi biên dịch xuất hiện.

Cách làm này có rủi ro cao. Mỗi dependency có thể thay đổi API, hành vi, yêu cầu Java tối thiểu, dependency graph, định dạng dữ liệu hoặc mặc định bảo mật. Khi hàng chục thành phần thay đổi cùng lúc, một test thất bại hoặc một lỗi production trở nên khó quy nguyên nhân; kể cả khi build thành công, điều đó cũng không chứng minh contract và hành vi vẫn tương thích.

Một chiến lược an toàn hơn là **nâng cấp theo từng nhóm thay đổi có ranh giới rõ, có giả thuyết và có bằng chứng kiểm thử**. Việc này không có nghĩa luôn nâng từng JAR một cách máy móc: những thành phần có yêu cầu version đồng bộ phải được nâng như một cụm nhất quán. Cốt lõi là kiểm soát phạm vi, xác định nguyên nhân và đo được kết quả ở mỗi bước.

## 1. “Nâng cấp đồng loạt không có bằng chứng” là gì?

Một đợt nâng cấp thiếu kiểm soát thường có các dấu hiệu:

- Thay nhiều version trong `build.gradle.kts`, `pom.xml` hoặc version catalog mà chưa xác định lý do.
- Dùng `latest.release`, version range quá rộng hoặc bản `SNAPSHOT` để “bắt kịp” dependency.
- Chỉ chạy `compileJava` hoặc một smoke test rồi kết luận tương thích.
- Nâng đồng thời JDK, Gradle, framework, database driver, serializer và schema.
- Không lưu dependency graph trước/sau, không có lockfile hoặc checksum artifact phù hợp.
- Bỏ qua release notes về breaking changes, baseline JDK, module path và deprecation.
- Không biết ứng dụng đang sử dụng những API nào của library được nâng.
- Không có tập test cho lỗi, dữ liệu biên, serialization, authorization hoặc concurrency.
- Không có kế hoạch rollback và người sở hữu quyết định phát hành.

**Bằng chứng kiểm thử** không nhất thiết là một báo cáo lớn. Ở mức tối thiểu, cần nêu rõ phiên bản cũ/mới, lý do nâng, môi trường, phép kiểm tra đã chạy, kết quả và điều chưa được kiểm. Quan trọng hơn số lượng test là mức độ chúng bảo vệ hợp đồng thực sự được consumer sử dụng.

## 2. Vì sao “build xanh” chưa đủ?

Một build Java thường gồm nhiều bước: resolve dependency, compile, test, package, chạy ứng dụng và triển khai. Các bước này kiểm tra những thuộc tính khác nhau.

| Tín hiệu | Điều nó chứng minh trong phạm vi chạy | Điều chưa được chứng minh |
|---|---|---|
| Dependency resolution thành công | Gradle/Maven tìm được một tập artifact theo rules hiện tại | Phiên bản đã chọn an toàn hoặc tương thích hành vi |
| `compileJava` thành công | Source đã biên dịch với compiler/classpath hiện tại | Runtime cũ, dependency nhị phân và dữ liệu production hoạt động |
| Unit tests pass | Những test đã chạy không phát hiện sai lệch | Integration, database, TLS, load, consumer ngoài |
| Integration tests pass | Một số luồng ghép nối đã hoạt động trong môi trường test | Mọi cấu hình và đường lỗi của production |
| API diff không báo breaking | Công cụ không tìm thấy dạng break mà nó được cấu hình phát hiện | Behavior, runtime, reflective access, wire format |
| Staging smoke test pass | Ứng dụng khởi động và vài đường cơ bản hoạt động | Luồng ít gặp, dữ liệu lịch sử, peak load |
| Canary ổn định | Một tập traffic thực chạy tốt trong thời gian quan sát | Tình huống chưa xuất hiện và rủi ro vận hành về sau |

Một lỗi tương thích có thể chỉ xuất hiện khi đọc timestamp quanh DST, xử lý số DECIMAL có scale lớn, tạo proxy cho một class cụ thể, hoặc handshake TLS với một endpoint hiếm dùng. Không có lỗi trong một test suite mỏng không phải bằng chứng “không có rủi ro”.

## 3. Các chiều tương thích cần xem xét

Mỗi dependency có bề mặt tương thích khác nhau. Khi nâng, nên phân biệt:

1. **Source compatibility:** mã consumer còn biên dịch với API mới không?
2. **Binary compatibility:** bytecode consumer hoặc plugin được biên dịch trước còn liên kết với library mới không?
3. **Behavioral compatibility:** giá trị, exception, ordering, retry, timeout, side effect và concurrency còn theo hợp đồng không?
4. **Runtime/JDK compatibility:** class-file version, Java SE API, module access, security provider và OS có phù hợp không?
5. **Dependency compatibility:** direct/transitive dependencies có conflict hoặc thay đổi implementation được chọn không?
6. **Data/protocol compatibility:** schema DB, JDBC mapping, JSON/XML, event, serialization và HTTP contract có giữ đúng không?
7. **Operational compatibility:** startup, memory, latency, logging, metrics và resource lifecycle có đáp ứng SLO không?
8. **Security compatibility:** TLS, certificate validation, authorization và cơ chế kiểm soát dữ liệu không bị nới lỏng ngoài chính sách.

Không cần kiểm mọi chiều bằng cùng độ sâu cho mọi artifact. Thay thư viện chỉ dùng để test có phạm vi khác với đổi ORM hoặc HTTP client ở production. Nhưng phải **ghi lý do vì sao một phép kiểm được chọn hoặc bỏ qua**.

## 4. Kiểm kê dependency trước khi quyết định phiên bản mới

Một dự án Java có nhiều lớp dependency:

- **Direct dependency:** được khai báo trực tiếp trong module.
- **Transitive dependency:** được kéo vào qua dependency khác.
- **Build plugin/tool:** được Gradle/Maven sử dụng ở build time.
- **Annotation processor/code generator:** chạy khi biên dịch và có thể cần JDK mới.
- **Test dependency:** JUnit, mocking, test container, assertion library.
- **Runtime-only dependency:** JDBC driver, logging backend, service provider, native binding.
- **Optional/plugin/agent:** có thể được nạp động và không xuất hiện trong đường compile thông thường.
- **Platform/BOM:** định nghĩa phiên bản hoặc constraint cho một nhóm artifact.
- **Application server/container:** có thể cung cấp thư viện theo class loader khác với ứng dụng.

Với Gradle, phân biệt `compileClasspath`, `runtimeClasspath` và `testRuntimeClasspath`. Cùng một tọa độ thư viện có thể được chọn theo version hoặc variant khác trong các configuration khác nhau.

Ví dụ lệnh **để sử dụng trong dự án thực tế**, không phải bước bắt buộc khi soạn bài:

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency jackson-databind
~~~

Với dự án nhiều module, chọn đúng project hoặc task path, chẳng hạn `:service:dependencies`. Output dependency insight giúp biết **vì sao một phiên bản được chọn**, không tự chứng minh phiên bản đó tương thích.

Maven có thể dùng dependency tree ở scope phù hợp:

~~~bash
mvn dependency:tree
~~~

Đối với plugin dependency, toolchain hoặc artifact được tải động, có thể cần thêm báo cáo và cách kiểm kê riêng.

## 5. Lưu baseline có thể tái lập trước khi thay đổi

Trước đợt nâng cấp, lưu một baseline đủ để người khác tái tạo sự cố:

| Thông tin | Ý nghĩa |
|---|---|
| Git commit/tag | Xác định chính xác source và build scripts |
| Java feature/update/build, vendor | Phân biệt compiler, Gradle daemon, test JVM và production JVM |
| Gradle/Maven và plugin versions | Đảm bảo build tool được hỗ trợ trên JDK |
| Resolved dependency graph | Không chỉ version khai báo |
| Lockfile/verification metadata | Giúp cố định artifact và phát hiện sai khác nguồn |
| Artifact checksum/digest | Kiểm chứng binary được build/triển khai |
| Database/server/schema revision | Làm rõ môi trường integration |
| Test result và report | Bằng chứng trạng thái ban đầu |
| JVM options, container image | Giải thích những khác biệt runtime |
| Các lỗi đã tồn tại | Không quy nhầm chúng cho dependency mới |

**Baseline xanh** có nghĩa những phép thử đã chọn có kết quả chấp nhận được tại thời điểm đầu; không có nghĩa mọi behavior đều hoàn hảo. Nếu baseline đã có flaky test, ghi nhận thay vì che giấu. Khi phép thử thất bại sau nâng cấp, cần phân biệt lỗi mới với vấn đề tồn tại trước đó.

### 5.1. Dependency locking và verification không phải cùng một thứ

**Dependency locking** giúp cố định phiên bản đã resolve, làm giảm nguy cơ bản build tự chọn version mới ngoài ý muốn.

**Dependency verification** giúp xác nhận identity/checksum/signature của artifact được tải, theo chính sách build, nhằm hạn chế việc sử dụng binary không mong muốn.

Version lock không tự chứng minh artifact an toàn, và artifact verification không đảm bảo API tương thích. Đây là những công cụ hỗ trợ **tính tái lập và nguồn gốc**, cần kết hợp kiểm thử.

## 6. Phân loại dependency theo mức rủi ro

Không nên nâng theo thứ tự ngẫu nhiên hoặc số thứ tự trong catalog. Có thể lập risk register dựa trên:

| Nhóm | Rủi ro điển hình | Test ưu tiên |
|---|---|---|
| JSON/XML serializer | Đổi field naming, null handling, polymorphism, date/time, bảo mật parsing | Golden fixtures và consumer contract |
| JDBC driver | Numeric precision, timezone, null, transaction, TLS | Round-trip, integration DB, negative cases |
| ORM/framework | Entity mapping, proxy, transaction, SQL dialect | Repository tests, schema validation, rollback |
| HTTP client | Timeout, redirect, TLS, hostname, proxy, retry | Integration với endpoint và negative security |
| Logging | Binding conflict, format, MDC, sensitive data | Startup, log format, correlation, leak checks |
| Bytecode/proxy/agent | Class-file support, reflection, JPMS access | Startup, instrumentation, JDK runtime matrix |
| Cryptography/security | Provider, algorithm, certificate validation | Positive/negative security contract |
| Build plugins | Gradle API, JDK baseline, task configuration | Build reproducibility và plugin tasks |
| Test libraries | Test engine discovery, mocking, assertions | Test suite và coverage/test execution report |
| Core utility | API generic, null behavior, transitive dependencies | Compile test và targeted unit tests |

Ưu tiên cũng phải dựa trên **mức độ sử dụng**. Một dependency không nằm trong code path production có thể có rủi ro thấp hơn. Nhưng một build plugin cũ ngăn toàn bộ pipeline nâng JDK có thể là blocker cấp cao dù không vào runtime.

## 7. “Nâng một lần một thay đổi” không đồng nghĩa “chỉ đổi đúng một JAR”

Nguyên tắc quan trọng là **mỗi đợt nâng có ranh giới đủ rõ để suy luận**. Nếu hai artifact có yêu cầu phiên bản đồng bộ, nâng riêng chúng có thể tạo một tổ hợp mà vendor chưa hỗ trợ.

Ví dụ:

- Một nhóm module của cùng framework thường nên dùng BOM/platform để đồng bộ.
- Một thư viện core và module extension có thể cần cùng thế hệ.
- Driver và ORM dialect có thể cần phiên bản hỗ trợ lẫn nhau.
- Plugin Gradle có thể yêu cầu một mức Gradle/JDK tối thiểu.
- Servlet/Jakarta namespace migration có thể cần thay đồng thời framework và các integration.

Đơn vị nâng thích hợp là **coherent upgrade unit**: một tập dependency thay đổi cùng nhau vì một điều kiện kỹ thuật có căn cứ, đi kèm một mục tiêu kiểm tra rõ ràng.

Chẳng hạn:

~~~text
Đợt 1: nâng Gradle wrapper và plugin bắt buộc để build trên JDK mới
Đợt 2: đổi toolchain/compiler release và chứng minh bytecode baseline
Đợt 3: nâng JSON stack đồng bộ theo BOM
Đợt 4: nâng JDBC driver, giữ DB server/schema cố định
Đợt 5: nâng ORM/dialect và kiểm chứng transaction
Đợt 6: thay đổi schema/database server theo kế hoạch riêng
~~~

Đây là ví dụ phân tách, không phải thứ tự bắt buộc cho mọi hệ thống. Nếu dependency có ràng buộc version, cần thiết kế lại thứ tự cho phù hợp.

## 8. Tại sao không nên dùng “latest” không kiểm soát?

Ví dụ cấu hình dễ tạo build không tái lập:

~~~kotlin
dependencies {
    implementation("com.example:client:+")
}
~~~

Dấu `+` thể hiện chọn một version động theo quy tắc resolution. Lần build hôm nay và lần build sau có thể resolve ra các binary khác nhau nếu repository có bản mới.

Với dependency đang được migration, thường nên chọn một version rõ ràng đã được xác minh:

~~~kotlin
dependencies {
    implementation("com.example:client:2.7.3")
}
~~~

Tên artifact và version trên chỉ là ví dụ. Trong dự án thật, phải xác minh thông tin version và chọn bản có chính sách hỗ trợ phù hợp. Version cố định giúp tăng khả năng tái lập nhưng không thay thế việc kiểm tra transitive dependencies hay compatibility.

Tương tự, việc gọi phiên bản mới nhất là “tốt nhất” không luôn đúng. Một bản major mới có thể yêu cầu JDK cao hơn baseline, đổi namespace hoặc không tương thích với framework hiện tại. Quyết định nên dựa trên **yêu cầu và bằng chứng**, không chỉ tuổi của phiên bản.

## 9. Version catalog, BOM và constraints: công cụ quản lý, không phải bằng chứng

Với Gradle, version catalog giúp quản lý tọa độ và phiên bản ở một nơi:

~~~toml
# gradle/libs.versions.toml - ví dụ minh họa
[versions]
jackson = "2.17.2"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
~~~

Trong `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation(libs.jackson.databind)
}
~~~

Version catalog giúp tránh version rải rác, nhưng bản thân nó **không áp đặt** mọi dependency phải thống nhất. Một transitive dependency hoặc platform constraint có thể khiến version thực tế khác với version được viết trong catalog. Phải kiểm tra **resolved graph**.

Đối với các hệ sinh thái có BOM/platform, ví dụ:

~~~kotlin
dependencies {
    implementation(platform("com.example:example-bom:3.1.0"))
    implementation("com.example:module-a")
    implementation("com.example:module-b")
}
~~~

Các tọa độ trên là placeholder. BOM định nghĩa quy tắc chọn phiên bản cho các module mà nó quản lý; nó không đảm bảo tất cả những module ấy đã được consumer của bạn kiểm thử.

Nếu dùng `enforcedPlatform` hoặc version constraints chặt, cần hiểu tác động tới dependency resolution và consumer của thư viện. Ép version để “hết conflict” có thể làm module khác gặp lỗi binary ở runtime.

## 10. Tránh thay đổi quá nhiều biến trong cùng pull request

Giả sử một pull request cùng lúc:

1. Nâng JDK 17 lên 21.
2. Nâng Gradle wrapper.
3. Nâng framework web lên một major release.
4. Nâng Jackson, JDBC driver, Hibernate, logging.
5. Đổi database schema và JSON DTO.
6. Thay cấu hình TLS và garbage collector.

Khi hệ thống xuất hiện lỗi `NoSuchMethodError`, không rõ đó là do library nào, classloader, BOM conflict hay một API được thay đổi. Khi latency tăng, cũng khó quy về GC, driver, ORM hoặc query plan.

Nên tách thành các pull request có mục tiêu và tiêu chí riêng. Một PR phù hợp thường có:

- Một giả thuyết rõ: “Nâng HTTP client X từ A lên B để hỗ trợ JDK mục tiêu”.
- Tập artifact thay đổi có quan hệ giải thích được.
- Thay đổi mã migration kèm theo nếu API break.
- Test thể hiện rủi ro đã nhận diện.
- Resolved graph diff và release notes quan trọng.
- Một cách rollback không phụ thuộc thay đổi không liên quan.

Tuy nhiên, việc chia PR cũng cần giữ repository ở trạng thái build được. Đôi khi hai thay đổi phải nằm cùng một đợt vì không tồn tại trạng thái trung gian được hỗ trợ; trường hợp đó cần ghi rõ và tăng độ sâu test.

## 11. “Không đổi mã nguồn” không có nghĩa “không đổi hành vi”

Một driver hoặc thư viện có thể giữ nguyên chữ ký method nhưng thay đổi ngữ nghĩa:

| Thư viện | Thay đổi có thể xảy ra dù source build pass |
|---|---|
| HTTP client | Retry, redirect, proxy, TLS defaults |
| JSON mapper | Null inclusion, enum naming, unknown fields, date format |
| JDBC driver | `getObject()` mapping, timezone, decimal scale |
| ORM | Flush ordering, lazy loading, query generation |
| Logging | Timestamp format, MDC propagation, log level |
| Metrics | Metric names, tags và đơn vị |
| Caching | TTL interpretation, eviction order, serializer |
| Security library | Token validation, certificate rules, algorithm availability |

Do đó, nâng dependency cần có **behavioral contract tests** ở những nơi consumer dựa vào hành vi. Một test có thể tốt hơn hàng trăm test đơn giản nếu nó bảo vệ đúng hợp đồng phức tạp.

## 12. Ví dụ: nâng thư viện JSON theo hợp đồng dữ liệu

Một service có API trả về:

~~~json
{
  "customerId": "C-42",
  "active": true,
  "registeredAt": "2026-11-12T08:00:00Z"
}
~~~

Khi nâng JSON library, cần xác định:

- Trường null có được đưa vào JSON hay bỏ qua?
- Enum được viết theo name, value hay custom serializer?
- `Instant`, `LocalDateTime`, `OffsetDateTime` có format và timezone nào?
- Số lớn có mất precision không?
- Unknown properties khi deserialize bị bỏ qua hay gây lỗi?
- Cách deserialize polymorphic type có chịu ràng buộc bảo mật thích hợp?
- Có thay đổi key ordering mà consumer thực sự phụ thuộc hay không?
- Những bản payload lịch sử có còn đọc được không?

Một **golden fixture** có thể lưu input và expected domain result, hoặc expected JSON theo hợp đồng. Nếu thay đổi hợp lệ được chủ đích công bố, cập nhật fixture có kiểm soát; không tự chấp nhận mọi diff bằng cách “regenerate snapshots” mà không xem nội dung.

Ví dụ Java record để thể hiện contract (Java 16+):

~~~java
public record CustomerPayload(
        String customerId,
        boolean active,
        java.time.Instant registeredAt
) {}
~~~

Đây là kiểu domain minh họa; mapping thực tế phụ thuộc cấu hình serializer. Việc record compile không chứng minh output JSON tương thích. Cần kiểm tra hai chiều serialize–deserialize theo đúng phiên bản thư viện đã chọn.

## 13. Ví dụ: nâng JDBC driver mà giữ schema cố định

Nếu muốn xác định tác động riêng của driver, giữ database server/schema và dữ liệu test giống nhau rồi chạy đối chiếu:

~~~text
Driver A + schema S + JDK R --> Result set A
Driver B + schema S + JDK R --> Result set B

So sánh theo hợp đồng:
- NULL vs 0/false
- DECIMAL precision/scale
- DATE/TIMESTAMP/timezone/DST
- Unicode/emoji
- generated keys
- transaction rollback
- SQLState/exception classification
~~~

Đối với monetary values, dùng `BigDecimal` và phép so sánh phù hợp contract thay vì chuyển thành `double`. Đối với timestamp, phải xác định cột biểu diễn instant hay local date-time; nếu không, việc so sánh “giống hệt output cũ” có thể củng cố một bug tồn tại lâu.

Nếu driver mới chỉ hỗ trợ JDK mới, không thể luôn giữ JVM giống nhau. Khi đó phải ghi rõ test đang so sánh **tổ hợp driver/JDK** thay vì tuyên bố tác động thuần từ driver.

## 14. Ví dụ: nâng plugin build cần tách khỏi runtime dependency

Một plugin có thể thất bại khi Gradle chạy trên JDK mới dù mã business application không có vấn đề. Các yếu tố gồm:

- Plugin dùng API Gradle đã thay đổi.
- Plugin phụ thuộc API JDK nội bộ hoặc deep reflection.
- Plugin cần class-file version hoặc JDK tool khác.
- Annotation processor không nhận cú pháp hoặc bytecode mới.
- Code generator tạo source khác khi nâng bản.
- Plugin thay đổi order task hoặc incremental build behavior.

Quy trình hợp lý:

1. Chốt JDK đang chạy Gradle/Maven.
2. Kiểm tra compatibility matrix của build tool và plugin.
3. Nâng wrapper/plugin cần thiết theo đơn vị đồng bộ.
4. Giữ source level/target/release của ứng dụng theo baseline công bố.
5. So sánh generated sources và packaging.
6. Chạy build sạch và các task quan trọng.
7. Tách kết quả build-tool compatibility khỏi test behavior của ứng dụng.

Với Gradle Java toolchain, JDK chạy Gradle và JDK dùng để compile/test có thể khác nhau. Cấu hình **toolchain** không tự động chứng minh artifact chạy được trên JDK tối thiểu.

## 15. Java `--release` và bytecode không bảo đảm toàn bộ dependency tương thích

Khi build trên JDK mới nhưng hỗ trợ runtime cũ, có thể cấu hình Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Ví dụ minh họa trên yêu cầu compiler Java 21 tạo source/bytecode theo Java 17 và giới hạn API Java SE tham chiếu ở release 17. Nó không kiểm soát bytecode của dependency JAR đã được build ở nơi khác.

Một thư viện có thể phát hành bản mới yêu cầu Java 21. Ứng dụng chính biên dịch với `--release 17` nhưng runtime Java 17 vẫn có thể nạp class dependency thất bại với `UnsupportedClassVersionError`.

Do đó, cần kiểm tra:

- Minimum Java version của **mọi runtime dependency** quan trọng.
- Class-file major version của các artifact liên quan.
- Module path, automatic modules và `exports/opens`.
- Runtime test thật trên JDK tối thiểu được hỗ trợ.
- Plugin hoặc Java agent có version phù hợp JDK đích.

Không ghi “Java 17 compatible” chỉ vì module của mình có `options.release = 17`.

## 16. Phát hiện dependency conflict trước khi chạy production

Một thư viện A có thể yêu cầu module C phiên bản mới, trong khi thư viện B được viết cho một version C cũ. Gradle resolution có thể chọn version theo constraint/rule, nhưng Java runtime vẫn có thể gặp binary incompatibility.

Ví dụ:

~~~text
service
  +-- library-a:2.0 --> common-core:4.0
  +-- library-b:1.0 --> common-core:2.0
  |
  +-- resolved common-core:4.0
~~~

Graph này không chứng minh B tương thích với common-core 4.0. B có thể gọi method bị xóa, dẫn đến `NoSuchMethodError` khi code path chạy.

Các thao tác cần cân nhắc:

- Đọc release notes và requirement của A/B/C.
- Kiểm tra version constraints/BOM của hệ sinh thái.
- Chạy `dependencyInsight` và so sánh graph.
- Dùng API/binary compatibility analysis khi có artifact cũ/mới.
- Chạy integration tests kích hoạt thật các thành phần.
- Nếu không có tổ hợp được hỗ trợ, nâng cả cụm hoặc thay dependency.

Không tự dùng `force` một version chỉ để hết warning resolution mà không đánh giá consumer. **Resolution success** là điều kiện cần để build, không phải kết luận tương thích.

## 17. Thay đổi API và binary compatibility

Một bản thư viện mới có thể:

- Đổi tên hoặc xóa method/class.
- Đổi method descriptor hoặc visibility.
- Thay generic signature và ảnh hưởng source.
- Thêm overload tạo ambiguity với `null` hoặc lambda.
- Thêm abstract method vào interface khiến implementor bị ảnh hưởng.
- Thêm default method tạo xung đột.
- Thay type hoặc checked exception trong hợp đồng API.
- Đổi module exports và quyền reflective access.

Ví dụ API cũ:

~~~java
public String normalize(String input);
~~~

API mới:

~~~java
public String normalize(CharSequence input);
~~~

Source có thể compile nếu dùng kiểu thích hợp, nhưng bytecode consumer cũ tham chiếu `normalize(String)` có thể gặp `NoSuchMethodError` nếu library không còn method cũ.

Vì vậy, nên kiểm tra **source compatibility** bằng cách biên dịch lại consumer cũ và **binary compatibility** bằng cách chạy bytecode đã biên dịch với library cũ trên artifact library mới. Hai phép thử trả lời hai câu hỏi khác nhau.

Công cụ API diff có thể giúp phát hiện thay đổi tĩnh nhưng không thay thế runtime behavior test.

## 18. Đặt chuẩn bằng chứng cho mỗi upgrade PR

Một pull request nâng dependency nên có cấu trúc ngắn nhưng đủ thông tin:

| Mục | Nội dung |
|---|---|
| Lý do nâng | Sửa lỗ hổng, hỗ trợ JDK mới, tính năng hoặc lỗi cụ thể |
| Artifact | Group, name, version cũ → mới |
| Cụm liên quan | BOM/platform và dependency buộc nâng cùng |
| Môi trường | JDK, OS, Gradle/Maven, database/framework |
| API/behavior diff | Thay đổi đáng chú ý và consumer bị ảnh hưởng |
| Graph diff | Thay đổi direct/transitive và conflict resolution |
| Test | Compile, unit, integration, contract, runtime, security |
| Kết quả | PASS/FAIL, log/report, phiên bản và giới hạn |
| Rollback | Cách quay lại build trước và giới hạn dữ liệu |
| Owner | Người phụ trách và người duyệt |
| Rủi ro còn lại | Những case chưa kiểm, lý do chấp nhận |

Ví dụ bản ghi:

~~~yaml
dependencyUpgrade:
  component: "example-service"
  changedArtifacts:
    - artifact: "com.example:client"
      fromVersion: "2.4.1"
      toVersion: "2.7.3"
  javaRuntime: "17"
  evidence:
    sourceCompile: PASS
    unitTests: PASS
    integrationTests: PASS
    consumerContract: PASS
    securityNegativeCases: PASS
  unresolved:
    - "not tested on Windows"
  rollback:
    artifact: "previous signed deployment artifact"
  decision: CONDITIONAL_GO
~~~

Đây là mẫu minh họa, **không phải kết quả kiểm thử có thật**. Khi áp dụng trong CI, kèm commit, artifact digest, resolved dependency report, JDK build, đường dẫn logs và phạm vi test thật.

## 19. Bằng chứng phải có độ sâu phù hợp với thay đổi

Không phải thư viện nào cũng cần cùng một test matrix. Có thể đặt **risk-tier** như sau:

### Tier thấp: dependency ít ảnh hưởng runtime

Ví dụ helper dùng trong test, thay patch nhỏ và không lộ API ra consumer. Thường cần kiểm compile, test suite có liên quan, kiểm dependency graph và kiểm phát hành artifact.

### Tier trung bình: runtime utility hoặc HTTP client

Cần targeted unit, integration, contract, kiểm exception, timeout, TLS và startup. Nếu có consumer ngoài module, cân nhắc binary compatibility test.

### Tier cao: ORM, JDBC, serialization, security, runtime agent

Cần contract tests, dữ liệu biên, negative tests, JDK runtime matrix, integration với hệ thống thật hoặc môi trường tương đương, load/canary và rollback plan. Với schema hoặc event format, cần kiểm rolling deployments và khả năng đọc dữ liệu lịch sử.

Đây chỉ là gợi ý cấu trúc. Một “patch release” vẫn có thể cần Tier cao nếu nó tác động luồng thanh toán hoặc bảo mật. **Mức rủi ro dựa trên impact thực tế**, không chỉ con số MAJOR/MINOR/PATCH.

## 20. Trường hợp cần nâng gấp vì bảo mật

Nguyên tắc không nâng đồng loạt không có nghĩa trì hoãn vô thời hạn bản vá lỗ hổng nghiêm trọng. Nếu có một advisory ảnh hưởng ứng dụng thực tế, cần ưu tiên remediation theo chính sách bảo mật và mức phơi nhiễm.

Quy trình khẩn cấp vẫn nên giữ tính kiểm chứng tối thiểu:

1. Xác minh artifact/version bị ảnh hưởng và code path phơi nhiễm.
2. Xác định version sửa lỗi hoặc cách giảm thiểu được nhà cung cấp hỗ trợ.
3. Nâng **cụm tối thiểu cần thiết** thay vì kéo tất cả dependency không liên quan.
4. Chạy focused build/tests và security negative tests cho rủi ro liên quan.
5. Thử staging/canary nếu có thể, có rollback và quan sát.
6. Lưu lý do chấp nhận những vùng chưa kiểm đầy đủ và kế hoạch follow-up.

Có trường hợp cần tạm thời áp dụng mitigation ngoài dependency update, nhưng phải ghi owner, thời hạn và điều kiện thay thế. Tránh bật lại thuật toán TLS yếu, bỏ authorization hoặc nới policy chỉ để làm phiên bản mới chạy.

Tốc độ và kiểm chứng không phải hai lựa chọn loại trừ nhau; mục tiêu là **bằng chứng nhỏ nhưng đúng trọng tâm dưới áp lực thời gian**.

## 21. Tách nâng dependency khỏi sửa lỗi nghiệp vụ không liên quan

Một nguy cơ khác là lợi dụng “upgrade PR” để refactor lớn hoặc thay đổi business logic. Điều này làm diff khó đọc và test failure khó giải thích.

Nên phân biệt:

- **Dependency bump:** version hoặc artifact được chọn.
- **Required migration:** thay code để đáp ứng API, cấu hình hoặc behavior mới.
- **Incidental cleanup:** thay đổi style, tên biến, cấu trúc không bắt buộc.
- **Behavior redesign:** thay đổi hợp đồng của chính ứng dụng.

Những thay đổi bắt buộc để upgrade hoạt động có thể nằm cùng PR, nhưng nên được mô tả riêng. Refactor không liên quan nên tách nếu có thể.

Ví dụ, khi nâng serializer và cần thay adapter xử lý null, hãy ghi rõ hành vi nào thay đổi, tại sao, và contract test nào bảo vệ consumer. Không gộp thêm việc đổi toàn bộ DTO format nếu đó không phải điều kiện của dependency bump.

## 22. Rủi ro khi nâng đồng thời dữ liệu/schema

Dependency upgrade có thể yêu cầu schema hoặc dữ liệu mới. Một khi đã migrate dữ liệu production, rollback binary chưa chắc đảo ngược được schema hoặc nội dung.

Ví dụ:

~~~text
Release A:
  app v1 + driver v1 + schema S1

Release B:
  app v2 + driver v2 + schema S2
~~~

Nếu S2 đổi kiểu cột, cách mã hóa JSON hoặc bỏ field, app v1 có thể không đọc dữ liệu đã ghi bởi v2. Do đó, cần thiết kế khả năng **roll-forward/rollback** của cả dữ liệu và code.

Chiến lược expand–migrate–contract có thể phù hợp:

1. **Expand schema:** thêm cột/field hoặc compatibility layer mà app cũ vẫn sử dụng được.
2. **Migrate consumers và dữ liệu:** chuyển dần, có đo lường và kiểm soát tính nhất quán.
3. **Contract:** chỉ xóa trường cũ sau khi tất cả consumer được hỗ trợ đã chuyển.

Khi thay đổi không thể rollback an toàn, bản kế hoạch phải nói rõ và ưu tiên roll-forward recovery thay vì hứa một rollback không thực hiện được.

## 23. CI pipeline: nhiều tầng kiểm chứng, tránh chỉ dùng một tín hiệu

Một pipeline nâng dependency có thể được chia:

~~~text
Dependency change
      |
Resolve + lock + verify artifact identity
      |
Compile / static analysis / API diff
      |
Focused unit tests
      |
Contract + integration tests
      |
Target JDK runtime matrix
      |
Package + staging / canary
      |
Evidence review + go/no-go
~~~

Các bước cần được chọn theo rủi ro và hạ tầng. Đối với các test chậm hoặc phụ thuộc môi trường bên ngoài, có thể dùng CI job riêng, nhưng kết luận phát hành cần biết test nào đã chạy và thời điểm nào.

### 23.1. Gradle dependency checks

Những lệnh tham khảo:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind \
  --configuration runtimeClasspath
./gradlew test
./gradlew integrationTest
~~~

`integrationTest` chỉ là ví dụ task tùy chỉnh; không phải mọi dự án đều có task này. Tài liệu hoặc pipeline phải dùng task thật đã cấu hình trong repository.

**Không nên xem một lệnh đã tồn tại trong checklist là bằng chứng đã chạy.** Kết quả cần có log, commit, JDK và artifact tương ứng.

### 23.2. Kiểm JDK tối thiểu

Nếu library tuyên bố hỗ trợ Java 17, cần có test trên Java 17 thực sự; chỉ compile bằng JDK 21 với `--release 17` không chứng minh dependency runtime có bytecode và API tương thích Java 17.

Có thể đặt test launcher bằng Gradle toolchain:

~~~kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

Cần JDK 17 có sẵn hoặc môi trường resolver cung cấp nó. Với các matrix JDK rộng hơn, nên tạo job riêng để tránh hiểu nhầm một test launcher là đủ cho mọi runtime được hỗ trợ.

## 24. Đọc kết quả thất bại để giữ nguyên khả năng quy nguyên nhân

Khi một bước upgrade fail, đừng vội nâng thêm hàng loạt dependency nhằm “làm hết lỗi”. Phân loại failure:

| Dấu hiệu | Điều tra |
|---|---|
| `cannot find symbol` | API source thay đổi, compile classpath, JDK baseline |
| `NoSuchMethodError` | Binary API không tương thích hoặc transitive version conflict |
| `ClassNotFoundException` | Artifact thiếu, classloader, shading, module path |
| `UnsupportedClassVersionError` | Dependency bytecode cần JDK cao hơn |
| `InaccessibleObjectException` | Reflection vào package chưa mở, framework cũ |
| `SSLHandshakeException` | TLS/certificate/endpoint/provider, không tự bỏ validation |
| `SQLDataException` hoặc mapping sai | JDBC driver, SQL type, precision/timezone |
| Serialization snapshot khác | Mapper config, library behavior, contract của API |
| Memory/latency tăng | Pooling, buffering, serializer, GC, instrumentation |
| Flaky test | Timing, concurrency, shared fixture, external service |

Một thử nghiệm tốt sẽ khoanh vùng thay đổi nhỏ nhất đủ gây lỗi. Có thể tạm revert một bump trong nhánh thử nghiệm, so sánh artifact/graph, hoặc tạo reproduction tối thiểu. Các thao tác điều tra này giúp chứng minh nguyên nhân thay vì đoán từ thời điểm lỗi xuất hiện.

## 25. Lộ trình upgrade theo batch có checkpoint

Với một repository nhiều module, có thể triển khai:

### Giai đoạn A: kiểm kê và chọn JDK mục tiêu

Ghi dependency graph và JDK compatibility, chọn compiler/runtime baseline. Phân loại các blocker trực tiếp.

### Giai đoạn B: nâng build tool và plugin nền tảng

Đảm bảo Gradle/Maven, code generator, test framework có thể chạy trên JDK mục tiêu. Giữ output artifact tương thích với runtime tối thiểu.

### Giai đoạn C: nâng các cụm thư viện độc lập

Tách logging, HTTP, JSON, JDBC, ORM hoặc framework stack theo ràng buộc thực tế. Mỗi cụm có contract test riêng.

### Giai đoạn D: kiểm thử integration và consumer

Kiểm source/binary, behavior, schema, security và performance theo phạm vi đã chọn. Không đánh đồng “module của mình xanh” với “downstream consumer an toàn”.

### Giai đoạn E: canary và quan sát

Theo dõi lỗi, latency, memory, success rate, data anomalies và các chỉ số nghiệp vụ. Có tiêu chí dừng triển khai.

### Giai đoạn F: chốt bằng chứng và mở cụm tiếp theo

Lưu report, cập nhật trạng thái, rollback/roll-forward plan rồi mới mở đợt nâng kế tiếp. Nếu phát hiện lỗi, giữ lại baseline gần nhất có thể tái lập.

Một checkpoint không cần tách thành release công khai riêng, nhưng phải xác định được commit, artifact và test tương ứng.

## 26. Quản lý consumer bên ngoài module

Một thư viện dùng chung có thể được nhiều ứng dụng sử dụng. Ngay cả khi tác giả thư viện và test của thư viện pass, consumer có thể bị tác động bởi:

- API public/protected hoặc SPI bị thay đổi.
- Runtime dependency bị nâng bắc cầu.
- Version conflict với thư viện do consumer tự khai báo.
- Interface/default method hoặc exception behavior thay đổi.
- Module exports/opens, reflective integration khác.
- Serialization hoặc persistence data contract thay đổi.
- Java minimum version mới.

Cần có **consumer inventory** và contract test đại diện. Nếu không biết hết consumer bên ngoài, không tuyên bố “backward compatible với mọi ứng dụng”; ghi phạm vi đã xác minh và rủi ro còn lại.

Khi thư viện công bố SemVer, PATCH/MINOR/MAJOR là tín hiệu về chính sách phát hành chứ không thay kết quả kiểm thử. Một patch release vẫn có thể thay behavior; một major release không tự động làm hỏng mọi consumer.

## 27. Khi nào được gộp nhiều dependency vào một đợt?

Có những trường hợp gộp nhiều artifact là lựa chọn kỹ thuật hợp lý:

- Một BOM/framework release yêu cầu nâng đồng bộ.
- Các module là một distribution và có version alignment bắt buộc.
- Thư viện A mới yêu cầu B/C mới, không tồn tại tổ hợp hỗ trợ ở giữa.
- Một security fix được phát hành dưới dạng phiên bản stack thống nhất.
- Một namespace migration (ví dụ hệ sinh thái Jakarta) đòi hỏi thay các integration liên quan.

Để gộp có kiểm soát, cần:

1. Nêu dependency constraint hoặc lý do không thể chia.
2. Giữ tập gộp nhỏ nhất có thể về mặt kỹ thuật.
3. Xác định “hợp đồng chung” của cả cụm.
4. Chạy integration/consumer tests cho tương tác của cụm.
5. Lưu graph trước/sau và xác nhận version alignment.
6. Coi đó là một đơn vị rollback hoặc roll-forward phù hợp.

**Nâng đồng thời có lý do và bằng chứng** không phải “nâng đồng loạt vô tội vạ”. Khác biệt nằm ở khả năng giải thích, kiểm tra và chịu trách nhiệm.

## 28. Mẫu báo cáo cho Prime hoặc reviewer

Một bản tóm tắt upgrade có thể viết:

~~~text
Mục tiêu:
  Nâng library-client A -> B để tương thích với JDK 21.

Phạm vi:
  library-client + required transport module theo BOM.
  Không đổi database schema, JSON DTO hoặc runtime JDK.

Bằng chứng:
  Dependency graph diff: reviewed
  Source compile: PASS
  Old consumer binary test: PASS
  Contract integration tests: PASS
  TLS negative tests: PASS
  JDK 17 runtime test: NOT_APPLICABLE (artifact now requires Java 21)

Rủi ro còn lại:
  Windows deployment và external plugin chưa được thử.

Quyết định:
  Staging/canary trước rollout; theo dõi handshake errors,
  latency và client retries; rollback về artifact cũ nếu cần.
~~~

Đây là **mẫu trình bày**, không phải kết quả thực tế của một hệ thống đã chạy. Cần thay tên artifact, JDK, kết quả và phạm vi theo report chính xác.

Nếu một test chưa chạy, ghi `NOT_RUN` hoặc `NOT_TESTED`, không coi đó là PASS. Nếu phép thử không áp dụng, nêu lý do. Nếu có exception được duyệt, ghi owner, ngày rà soát và mức rủi ro còn lại.

## 29. Những hiểu lầm cần tránh

**“Nâng càng nhiều dependency cùng lúc thì càng nhanh.”** Có thể ít PR hơn nhưng khó điều tra lỗi và rollback; tổng thời gian sửa regression có thể lớn hơn.

**“Một dependency là một đơn vị nâng bắt buộc.”** Không đúng với framework, BOM hoặc các module có version alignment. Cần chọn cụm phụ thuộc nhất quán.

**“Version catalog đã tập trung là không còn conflict.”** Catalog quản lý khai báo; graph resolve vẫn có thể khác bởi transitive dependencies hoặc constraints.

**“Build xanh chứng minh production an toàn.”** Build không tự thực thi mọi contract, dữ liệu và môi trường production.

**“Patch release chắc chắn không breaking.”** Versioning mô tả ý định của nhà phát hành; cần kiểm nghiệm consumer thực tế.

**“Nâng lên latest luôn bảo mật và tương thích nhất.”** Một bản quá mới có thể cần baseline JDK hoặc framework khác, còn một bản cũ có thể chứa advisory quan trọng. Chọn theo support và bằng chứng.

**“Có `--release 17` thì mọi dependency chạy được trên Java 17.”** `--release` chỉ kiểm soát code được compiler tương ứng biên dịch, không thay bytecode JAR có sẵn.

**“Dependency resolution thành công nghĩa là binary-compatible.”** Một graph resolve được vẫn có thể chứa method mismatch ở runtime.

**“Thay driver mà không đổi code thì không cần test dữ liệu.”** JDBC mapping có thể khác về null, decimal, timestamp và vendor type.

**“Nâng thư viện bảo mật thì tắt validation để không làm gián đoạn.”** Bỏ kiểm tra bảo mật không phải sửa tương thích an toàn.

**“Rollback chỉ cần quay lại Git commit.”** Nếu schema hoặc dữ liệu đã thay đổi không tương thích ngược, rollback binary có thể thất bại.

**“Bằng chứng kiểm thử phải thật lớn mới có ích.”** Một tập test nhỏ nhưng trúng rủi ro, có log và version chính xác, hữu ích hơn danh sách test không gắn với quyết định.

## 30. Checklist khi phê duyệt nâng dependency

- [ ] Đã mô tả lý do cụ thể của mỗi upgrade.
- [ ] Đã ghi JDK, Gradle/Maven, runtime, container và baseline hiện tại.
- [ ] Đã kiểm kê direct, transitive, test, plugin, runtime và agent dependencies.
- [ ] Đã giữ lại resolved graph, lockfile/verification metadata nếu áp dụng.
- [ ] Đã xác định cụm artifact bắt buộc nâng đồng bộ.
- [ ] Đã tránh version động hoặc pin sai phạm vi mà thiếu bằng chứng.
- [ ] Đã đọc breaking changes, deprecation, Java baseline và compatibility policy.
- [ ] Đã kiểm source, binary và behavioral compatibility phù hợp rủi ro.
- [ ] Đã chạy targeted unit/contract/integration tests.
- [ ] Đã kiểm dữ liệu biên và format JSON/JDBC/schema nếu liên quan.
- [ ] Đã thử JVM tối thiểu mà ứng dụng vẫn tuyên bố hỗ trợ.
- [ ] Đã kiểm positive/negative security cases liên quan.
- [ ] Đã kiểm performance và resource lifecycle cho các thành phần nhạy cảm.
- [ ] Đã lưu test report, commit, resolved versions và artifact digest.
- [ ] Đã ghi rõ những môi trường/consumer chưa được kiểm tra.
- [ ] Đã có owner, quyết định go/no-go và phương án rollback/roll-forward.
- [ ] Đã lập checkpoint trước khi tiếp tục nhóm dependency kế tiếp.

## Kết luận

**Tránh nâng cấp đồng loạt không có bằng chứng kiểm thử** không có nghĩa chậm nâng cấp hoặc giữ dependency cũ vô thời hạn. Đó là nguyên tắc kiểm soát rủi ro: chia thay đổi thành những cụm hợp lý, xác định ranh giới tương thích, cố định môi trường có thể tái lập, chọn test gắn với hợp đồng của consumer và lưu kết quả ở từng checkpoint.

Với Java Advance Compatibility Migration, phải kiểm tra cả JDK/compiler/runtime, build plugins, direct/transitive dependencies, API/binary compatibility, behavior, dữ liệu và bảo mật. Một pull request nhỏ, có phạm vi rõ và bằng chứng mạnh thường an toàn hơn một đợt “nâng tất cả lên latest” chỉ có build xanh. Khi cần nâng cả một stack đồng bộ hoặc khắc phục lỗ hổng khẩn cấp, vẫn áp dụng cùng tinh thần: **nêu lý do, hạn chế phạm vi, kiểm tra đúng rủi ro, ghi giới hạn và có đường khôi phục**.
