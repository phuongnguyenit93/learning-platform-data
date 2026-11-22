# Xác định phiên bản nền và ma trận tương thích dependency

Trước khi nâng cấp Spring Authorization Server, cần biết chính xác ứng dụng đang chạy trên nền tảng nào và phiên bản dự kiến có thể kết hợp với những thành phần nào. Chỉ nhìn phiên bản Spring Boot trong `pom.xml` hoặc `build.gradle` là chưa đủ: Java runtime, Spring Framework, Spring Security, Spring Authorization Server, thư viện JOSE/JWT, database driver, migration tool, observability và test framework đều có thể ảnh hưởng đến quá trình build, khởi động và cấp token.

Phiên bản nền (baseline) là tập phiên bản đã được xác minh đang chạy ổn định. Ma trận tương thích ghi lại quan hệ giữa baseline, phiên bản mục tiêu, điều kiện hỗ trợ và bằng chứng kiểm thử. Tài liệu này hướng dẫn lập inventory, xác định baseline có thể hỗ trợ, quản lý dependency bằng BOM, phát hiện xung đột và xây dựng ma trận đủ rõ để quyết định nâng cấp.

## 1. Mục tiêu của việc xác định baseline

Một baseline tốt phải trả lời được:

- Ứng dụng đang dùng JDK nào để build và JRE nào để chạy?
- Spring Boot đang quản lý phiên bản Spring Framework, Spring Security, Jackson, Micrometer và các thư viện nền nào?
- Spring Authorization Server thuộc release line nào và có tương thích với Spring Security đang dùng không?
- Các thư viện JOSE/JWT, database driver, JDBC, cache, migration và test có bị override khỏi BOM không?
- Những phiên bản nào còn được nhà cung cấp hỗ trợ và nhận bản vá bảo mật?
- Phiên bản mục tiêu cần thay đổi những thành phần nào cùng lúc?
- Có thể rollback về baseline cũ sau khi schema hoặc dữ liệu authorization thay đổi không?

Không đồng nhất ba khái niệm sau:

| Khái niệm | Ý nghĩa |
|---|---|
| **Supported** | Quan hệ phiên bản được tài liệu/chính sách hỗ trợ chính thức xác nhận |
| **Resolved** | Build tool đã giải quyết được dependency graph mà không có lỗi phân giải |
| **Tested** | Tổ hợp đã được build và chạy qua bộ kiểm thử xác định của dự án |

Một build thành công chỉ chứng minh dependency graph có thể phân giải và biên dịch. Nó không tự chứng minh tổ hợp được hỗ trợ chính thức, không có lỗi runtime hoặc các luồng OAuth 2.0/OIDC vẫn hoạt động đúng.

## 2. Thu thập inventory từ dự án

Bắt đầu từ những gì build thực sự sử dụng, không chỉ đọc version được khai báo trực tiếp. Parent POM, BOM, Gradle plugin, version catalog, dependency constraints và lock file có thể quyết định phiên bản cuối cùng.

### 2.1. Thông tin build và runtime

Ghi nhận:

- JDK dùng để chạy Maven/Gradle và compiler toolchain.
- Java release/target bytecode.
- JRE hoặc container image đang chạy production.
- Maven Wrapper hoặc Gradle Wrapper và phiên bản plugin.
- Spring Boot plugin/parent/BOM.
- Profile build, repository nội bộ và cấu hình dependency management.
- Dependency lock, checksum hoặc SBOM nếu dự án đã tạo.

Lệnh kiểm tra cơ bản:

```bash
java -version
./mvnw -version
./gradlew -version
```

Chỉ chạy lệnh tương ứng với build system của dự án. Đầu ra Maven/Gradle cho biết JVM thực tế mà build tool đang dùng; có thể khác Java toolchain dùng để biên dịch và khác JRE trong container production.

### 2.2. Các dependency cần đưa vào inventory

| Nhóm | Thành phần cần ghi nhận | Vì sao quan trọng |
|---|---|---|
| Nền tảng | Java, Spring Boot, Spring Framework | Quyết định runtime, API và dependency management |
| Bảo mật | Spring Security Core/Config/Web/OAuth2 | Quyết định filter chain, authentication, authorization và decoder |
| Authorization Server | Spring Authorization Server | Cung cấp protocol endpoint, client, authorization và token services |
| JOSE/JWT | Nimbus JOSE + JWT và các module OAuth2 JOSE | Ký, xác minh, parse JWK/JWT và xử lý token |
| JSON | Jackson core/databind/modules | Serialize metadata, claim và dữ liệu tích hợp |
| Persistence | JDBC/JPA, connection pool, database driver | Lưu Registered Client, authorization và consent |
| Migration | Flyway hoặc Liquibase | Thay đổi schema có kiểm soát |
| Cache/coordination | Redis client hoặc cache provider nếu có | Lưu replay state, cache client/JWKS hoặc dữ liệu dùng chung |
| Observability | Actuator, Micrometer, tracing registry | Metric, health, trace và logging |
| Kiểm thử | JUnit, Mockito, Spring Test, Testcontainers, WireMock | Xác minh integration và dependency thật |
| Build | Maven/Gradle plugin, compiler plugin, image plugin | Tạo artifact nhất quán và tái lập |

Đối với Authorization Server, cần chú ý đặc biệt đến `spring-security-oauth2-authorization-server`, Spring Security OAuth2 JOSE, Nimbus JOSE + JWT và các lớp JDBC lưu authorization. Một thư viện được nâng riêng lẻ có thể làm thay đổi cách parse JWT, chọn JWK, serialize token metadata hoặc xử lý client authentication.

### 2.3. Lấy dependency graph thực tế

Với Maven:

```bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dverbose
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=com.nimbusds
```

`effective-pom` cho thấy version được kế thừa từ parent/BOM và các override sau cùng. `dependency:tree` giúp tìm dependency kéo một phiên bản vào graph và phát hiện nhiều phiên bản cùng artifact.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-authorization-server --configuration runtimeClasspath
./gradlew dependencyInsight --dependency nimbus-jose-jwt --configuration runtimeClasspath
```

Chạy thêm với `compileClasspath` hoặc configuration kiểm thử khi cần. Gradle có thể chọn phiên bản cao hơn theo conflict resolution; hãy đọc lý do chọn trong `dependencyInsight`, không chỉ nhìn version khai báo.

## 3. Xác định phiên bản nền hiện tại

Baseline phải phản ánh artifact đang chạy, không chỉ trạng thái working tree. Thu thập tối thiểu các bằng chứng sau:

1. Commit hoặc release tag đã được triển khai.
2. Phiên bản Java runtime và image digest đang chạy.
3. Spring Boot version và resolved dependency graph của artifact.
4. Spring Authorization Server và Spring Security version thực tế.
5. Database engine/version, schema migration level và driver.
6. Cấu hình issuer, signing algorithm, `kid`, token format và endpoint.
7. Kết quả smoke test, integration test và các chỉ số vận hành gần nhất.

Nếu production artifact không thể tái tạo từ commit hiện tại, ghi nhận khác biệt đó. Không gọi một cấu hình là baseline đã xác minh nếu chưa biết chính xác binary/dependency nào đang chạy.

### 3.1. Tách version khai báo và version được resolve

Ví dụ một dự án có thể khai báo Spring Security gián tiếp qua Spring Boot BOM, trong khi một dependency khác kéo thêm version riêng. Khi đó, version ghi trong một file build chưa chắc là version runtime sử dụng.

Inventory nên có hai cột:

- `declared_version`: version trực tiếp khai báo hoặc version property.
- `resolved_version`: version thực tế trong compile/runtime/test graph.

Với dependency được quản lý bởi BOM, ghi tên BOM và phiên bản BOM quyết định version. Với dependency bị override, ghi lý do, phạm vi và người sở hữu quyết định đó.

## 4. Xác định tổ hợp Spring Boot, Spring Security và Spring Authorization Server

Đây là trục tương thích quan trọng nhất của module.

### 4.1. Spring Boot BOM là nguồn quản lý nền tảng

Spring Boot dependency management quản lý một tập phiên bản Spring và thư viện tích hợp đã được nhóm phát hành kiểm thử cùng release line. Khi dùng Spring Boot parent hoặc BOM, nên để BOM quản lý Spring Framework, Spring Security, Jackson, Micrometer và các dependency nền thuộc phạm vi BOM.

Không tự đặt một version Spring Security khác chỉ vì muốn dùng API mới. Việc nâng riêng `spring-security-core`, `spring-security-web`, `spring-security-config` hoặc `spring-security-oauth2-*` có thể tạo tổ hợp không nhất quán giữa các module.

### 4.2. Spring Authorization Server phải tương thích với Spring Security

Spring Authorization Server có release line và yêu cầu nền tảng riêng. Cần kiểm tra tài liệu phiên bản, release notes và dependency metadata của đúng bản định dùng để xác nhận Spring Security tối thiểu/tối đa hoặc release line được hỗ trợ.

Không suy ra tương thích chỉ từ việc artifact có thể tải về Maven Central hoặc build không báo lỗi. Một bản Authorization Server mới có thể yêu cầu API Spring Security mới; một bản cũ có thể không được kiểm thử với Spring Security release line mới.

Quy tắc lựa chọn:

- Chọn Spring Boot release line còn được hỗ trợ và phù hợp JDK production.
- Lấy Spring Framework và Spring Security theo BOM của Boot, trừ khi tài liệu tương thích chính thức yêu cầu cách khác.
- Chọn Spring Authorization Server release line được xác nhận tương thích với Spring Security đã resolve.
- Nếu Authorization Server không được BOM hiện tại quản lý, khai báo version rõ ràng và ghi bằng chứng tương thích.
- Không override một module Spring Security đơn lẻ; nếu phải thay đổi release line, đánh giá toàn bộ nhóm module liên quan.

### 4.3. Ma trận tương thích không nên đóng cứng vào một ví dụ

Các release line thay đổi theo thời gian. Ma trận của dự án phải lấy dữ liệu từ tài liệu hỗ trợ và metadata của phiên bản mục tiêu tại thời điểm nâng cấp. Có thể dùng mẫu sau:

| Thành phần | Baseline đang chạy | Phiên bản mục tiêu | Ràng buộc phải xác minh |
|---|---|---|---|
| Java | `JDK_CURRENT` | `JDK_TARGET` | Boot và thư viện phải hỗ trợ JDK; build/runtime cùng tương thích |
| Spring Boot | `BOOT_CURRENT` | `BOOT_TARGET` | System requirements, support window, BOM |
| Spring Framework | `FRAMEWORK_RESOLVED` | `FRAMEWORK_TARGET` | Theo release line của Boot hoặc ma trận chính thức |
| Spring Security | `SECURITY_RESOLVED` | `SECURITY_TARGET` | Phù hợp với Boot và Authorization Server |
| Spring Authorization Server | `AS_CURRENT` | `AS_TARGET` | Tương thích Spring Security, Java và API đã dùng |
| Nimbus JOSE + JWT | `NIMBUS_RESOLVED` | `NIMBUS_TARGET` | Theo dependency management; không override tùy tiện |
| Jackson | `JACKSON_RESOLVED` | `JACKSON_TARGET` | Đồng bộ module Jackson và serializer |
| Database/driver | `DB_CURRENT` / `DRIVER_CURRENT` | `DB_TARGET` / `DRIVER_TARGET` | Driver hỗ trợ database, JDK và TLS/auth |
| Migration tool | `MIGRATION_CURRENT` | `MIGRATION_TARGET` | Hỗ trợ database và migration syntax |
| Micrometer/Tracing | `OBSERVABILITY_RESOLVED` | `OBSERVABILITY_TARGET` | Theo BOM và backend registry |
| Testcontainers | `TESTCONTAINERS_CURRENT` | `TESTCONTAINERS_TARGET` | Tương thích JDK, Docker/runtime và database image |

Các giá trị placeholder cần được thay bằng phiên bản đã kiểm tra. Không sao chép một bảng version từ dự án khác nếu dự án đó khác JDK, Boot, servlet container hoặc database.

## 5. Đánh giá trạng thái tương thích

Gán trạng thái cho từng cặp hoặc nhóm phiên bản, không chỉ cho từng artifact riêng lẻ:

| Trạng thái | Điều kiện sử dụng |
|---|---|
| `SUPPORTED` | Tài liệu/chính sách chính thức xác nhận tổ hợp được hỗ trợ |
| `TESTED` | Bộ kiểm thử dự án đã chạy trên đúng tổ hợp và đạt yêu cầu |
| `CONDITIONAL` | Có điều kiện, giới hạn hoặc patch bắt buộc đã ghi rõ |
| `UNKNOWN` | Chưa có tài liệu hoặc bằng chứng kiểm thử đủ tin cậy |
| `UNSUPPORTED` | Nằm ngoài yêu cầu chính thức hoặc đã biết không tương thích |

Một tổ hợp có thể vừa `SUPPORTED` vừa chưa `TESTED`. Ví dụ nhà cung cấp hỗ trợ nhưng dự án chưa chạy integration test. Ngược lại, một tổ hợp `TESTED` trong môi trường nội bộ vẫn có thể không được nhà cung cấp hỗ trợ; không dùng một lần test thành công để khẳng định support chính thức.

Ma trận nên lưu bằng chứng cụ thể: URL release notes hoặc system requirements, commit test, build number, log dependency tree, SBOM và kết quả test. Ghi ngày xác minh vì trạng thái hỗ trợ có thể thay đổi.

## 6. Quản lý version bằng BOM và dependency management

### 6.1. Maven với Spring Boot parent

Ví dụ cấu trúc Maven rút gọn:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-authorization-server.version>AS_VERSION</spring-authorization-server.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-oauth2-authorization-server</artifactId>
        <version>${spring-authorization-server.version}</version>
    </dependency>
</dependencies>
```

`BOOT_VERSION` và `AS_VERSION` là placeholder: thay chúng bằng version cụ thể đã xác minh trước khi build. Parent POM dùng version literal/CI-friendly version theo quy ước Maven của dự án; không giả định một property khai báo trong cùng POM có thể được dùng ở mọi vị trí model. Kiểm tra xem Boot BOM có quản lý artifact Authorization Server ở release line đó hay không. Nếu có, tránh khai báo version riêng; nếu không, pin version tương thích rõ ràng.

### 6.2. Maven với BOM được import

Khi không dùng Boot parent, có thể import Boot BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>BOOT_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khai báo version cụ thể của BOM trong dự án; `BOOT_VERSION` chỉ là placeholder. Không import nhiều BOM cùng quản lý một nhóm Spring mà không hiểu thứ tự ưu tiên và override. Nếu có corporate BOM, ghi rõ BOM nào là nguồn cuối cùng cho mỗi dependency.

### 6.3. Gradle

Với Gradle, dùng Spring Boot plugin và dependency management plugin hoặc native platform/BOM theo quy ước của dự án. Ví dụ:

```kotlin
plugins {
    id("org.springframework.boot") version "BOOT_VERSION"
    id("io.spring.dependency-management") version "DEPENDENCY_MANAGEMENT_VERSION"
}

dependencies {
    implementation("org.springframework.security:spring-security-oauth2-authorization-server:AS_VERSION")
}
```

Các chuỗi `*_VERSION` là placeholder, cần thay bằng phiên bản đã xác minh. Khi dùng `io.spring.dependency-management` cùng Spring Boot plugin, plugin dependency management tự import Boot BOM theo Boot plugin version. Nếu dự án dùng native Gradle platform thay cho dependency management plugin, bỏ plugin `io.spring.dependency-management` và khai báo `implementation(platform("org.springframework.boot:spring-boot-dependencies:BOOT_VERSION"))` trong `dependencies`. Không cần dùng cả hai cách quản lý BOM cùng lúc. Không khai báo Spring Security module với các version khác nhau trong từng dependency. Dùng version catalog hoặc convention plugin để tập trung version và tránh drift giữa module.

### 6.4. Tránh override dependency nền

Chỉ override version được BOM quản lý khi có lý do kỹ thuật rõ ràng, ví dụ bản vá bảo mật bắt buộc hoặc lỗi đã xác nhận. Mỗi override phải ghi:

- Dependency và version do BOM chọn.
- Version override và lý do.
- Phạm vi ảnh hưởng (compile, runtime, test).
- Tổ hợp dependency liên quan cần kiểm thử.
- Ngày dự kiến loại bỏ override và người sở hữu.

Không dùng `force`, `resolutionStrategy` hoặc exclusion hàng loạt để làm build xanh mà không hiểu dependency nào cần version đó. Những biện pháp này có thể che giấu xung đột nhị phân hoặc lỗi runtime.

## 7. Các điểm tương thích đặc thù Authorization Server

Khi so sánh baseline và candidate, kiểm tra cả API và hành vi runtime sau:

### 7.1. SecurityFilterChain và endpoint

- Thứ tự `SecurityFilterChain` và `securityMatcher`.
- Cách cấu hình authorization endpoint, token endpoint, JWK Set endpoint, introspection, revocation và OIDC endpoints.
- Default security headers, CSRF, CORS, session và exception handling.
- API builder/customizer và converter cho authorization request, token request, client authentication.
- Hành vi `AuthenticationProvider` và `AuthenticationConverter` tùy chỉnh.

Một thay đổi Spring Security có thể làm thay đổi API hoặc thứ tự filter; một thay đổi Authorization Server có thể đổi extension point hoặc default behavior. Kiểm tra compile là chưa đủ: cần test request thật đến từng endpoint.

### 7.2. Client, authorization và token persistence

- `RegisteredClientRepository` và cách serialize `ClientSettings`/`TokenSettings`.
- `OAuth2AuthorizationService` và `OAuth2AuthorizationConsentService`.
- JDBC schema, index, column type và migration.
- Cách serialize authorization attributes, principal name và token metadata.
- Refresh token rotation, reuse detection, revocation và consent lookup.

Nếu nâng serializer hoặc schema, phiên bản mới phải đọc được record được tạo bởi phiên bản cũ trong giai đoạn rollout. Nếu không thể giữ tương thích, cần migration offline hoặc buộc re-authentication theo kế hoạch.

### 7.3. JOSE, JWK và token customization

- `JwtEncoder`, `JwtDecoder`, `JWKSource` và key selection.
- `kid`, `alg`, `kty`, JWK use/key operations và JWKS cache.
- `OAuth2TokenCustomizer` và claim mapping.
- JWT header/claim, issuer, audience, token type và serialization.
- ID token signing, UserInfo và discovery metadata.

Thư viện Nimbus hoặc JOSE update có thể thay đổi API, kiểm tra thuật toán, cách chọn key hoặc parse JWK. Kiểm thử token đã phát hành bằng key cũ và token mới; xác minh Resource Server thực tế có thể đọc cả hai trong giai đoạn chuyển tiếp.

### 7.4. Java, Servlet container và runtime

Kiểm tra JDK bytecode, Java toolchain, servlet API/container và image runtime. Không build bằng JDK mới rồi chạy trên JRE thấp hơn mức bytecode hoặc yêu cầu runtime. Kiểm tra TLS provider, trust store, entropy, timezone, locale và container memory limit.

### 7.5. Database và driver

Kiểm tra database version, driver, TLS/authentication mode, connection pool, transaction isolation và SQL dialect. Migration tool phải hỗ trợ đúng database. Test schema trên database engine thực tế; H2 không thay thế được integration test với PostgreSQL, MySQL hoặc Oracle nếu production dùng các hệ đó.

## 8. Kiểm tra dependency graph và rủi ro xung đột

Các dấu hiệu cần điều tra:

- Nhiều version của cùng module Spring Security trong runtime graph.
- Spring Framework hoặc Security module không cùng release line.
- Nimbus JOSE + JWT bị kéo version khác với version mà Spring Security/Authorization Server đã kiểm thử.
- Các module Jackson không đồng bộ.
- Logging facade/provider bị trùng hoặc xung đột.
- Driver hoặc pool version không hỗ trợ JDK/database production.
- Dependency test bị đưa nhầm vào runtime hoặc dependency runtime bị thiếu ở image.
- Dependency bị exclude khỏi BOM mà không có thay thế tương thích.

Không phải mọi dependency tree có nhiều version đều là lỗi: build tool có thể chọn một version theo quy tắc resolution. Tuy nhiên, cần hiểu module nào yêu cầu version nào và có tương thích binary/API hay không.

Sau khi giải quyết graph, tạo SBOM cho artifact và quét lỗ hổng theo chính sách của tổ chức. Ghi lại cả direct và transitive dependency, license, CVE, nguồn tải và checksum/signature nếu pipeline hỗ trợ. Không nâng một thư viện chỉ để xóa cảnh báo scanner khi chưa xác nhận version đó tương thích với framework và không tạo lỗ hổng mới.

## 9. Xây dựng ma trận tương thích của dự án

Một ma trận hữu ích cần có cả version, điều kiện và bằng chứng. Ví dụ cấu trúc:

| Thành phần/quan hệ | Baseline | Candidate | Trạng thái | Bằng chứng | Rủi ro/ghi chú |
|---|---|---|---|---|---|
| JDK ↔ Boot | `JDK_A / BOOT_A` | `JDK_B / BOOT_B` | `SUPPORTED` | System requirements link | Runtime image cần cùng JDK line |
| Boot ↔ Framework/Security | BOM A | BOM B | `SUPPORTED` | Effective POM/dependency report | Không override module lẻ |
| Security ↔ Authorization Server | `SECURITY_A / AS_A` | `SECURITY_B / AS_B` | `CONDITIONAL` | Release notes + integration test | Xác minh API custom provider |
| AS ↔ JDBC schema | Schema A | Schema B | `TESTED` | Migration test report | Expand-and-contract |
| JOSE/JWK ↔ Resource Server | Nimbus A | Nimbus B | `UNKNOWN` | Chưa có rotation test | Cần test key overlap |
| Database ↔ Driver | DB A / Driver A | DB B / Driver B | `SUPPORTED` | Vendor matrix | Test TLS và transaction |
| Micrometer ↔ Registry | Metrics A | Metrics B | `TESTED` | Scrape/metric test | Kiểm tra tên và histogram |

Các dòng trên chỉ minh họa cách ghi. Không đánh dấu `SUPPORTED` hoặc `TESTED` trước khi có bằng chứng. Thêm cột `owner`, `verified_at`, `test_run`, `artifact_digest` nếu ma trận được dùng trong quy trình release.

### 9.1. Ma trận theo môi trường

Nếu development, staging và production chạy cấu hình khác nhau, ghi riêng từng môi trường:

| Trường | Development | Staging | Production |
|---|---|---|---|
| Java runtime | ... | ... | ... |
| Container/image | ... | ... | ... |
| Spring Boot/Security/AS | ... | ... | ... |
| Database/driver | ... | ... | ... |
| Key provider | Local test key | Staging KMS | Production KMS/HSM |
| Token format/alg | ... | ... | ... |
| Resource Server version | ... | ... | ... |

Tốt nhất là cùng artifact digest chạy xuyên các môi trường và chỉ khác cấu hình runtime/secret. Nếu production dùng artifact khác, ghi lý do và kiểm thử riêng.

## 10. Chuyển ma trận thành kế hoạch nâng cấp

Khi baseline đã rõ, chọn candidate theo thứ tự có thể kiểm soát:

1. Chọn JDK và Spring Boot release line còn được hỗ trợ.
2. Lấy Spring Framework/Security từ BOM tương ứng.
3. Chọn Spring Authorization Server tương thích với Spring Security đó.
4. Kiểm tra database driver, migration tool, JOSE/JWT, observability và test dependencies.
5. Đánh dấu dependency có API breaking change hoặc schema impact.
6. Chia nâng cấp thành nhóm có thể build/test độc lập nếu cần.
7. Tạo nhánh hoặc commit candidate, lưu dependency graph và SBOM.
8. Chạy compile, unit, integration, security regression và migration tests.
9. Chỉ chốt candidate khi tổ hợp có bằng chứng hỗ trợ và kết quả test đạt.

Không nhất thiết phải nâng mọi dependency lên phiên bản mới nhất. Chọn phiên bản được hỗ trợ, tương thích và có thể vận hành; ghi lại lý do nếu trì hoãn một nâng cấp.

## 11. Bộ kiểm tra trước khi chốt baseline/candidate

| Kiểm tra | Bằng chứng cần lưu |
|---|---|
| JDK build và runtime tương thích | Output version, toolchain config, image digest |
| Spring Boot release line được hỗ trợ | System requirements/release policy |
| Framework/Security lấy từ BOM nhất quán | Effective POM hoặc Gradle dependency report |
| Authorization Server tương thích Security | Tài liệu phiên bản và dependency metadata |
| Không có override không giải thích | Dependency tree và danh sách exception |
| JOSE/JWK/JWT hoạt động | Test ký, xác minh, JWKS và rotation |
| Persistence tương thích | Schema diff, migration test, serialization test |
| Database driver hỗ trợ database/JDK | Vendor compatibility documentation và integration test |
| Actuator/Micrometer hoạt động | Metric scrape, health và tracing test |
| Client flows không hồi quy | Authorization code + PKCE, client credentials, refresh, revoke/introspection nếu dùng |
| Build tái lập | Wrapper, lock/versions, SBOM và artifact digest |
| Bảo mật dependency | CVE/license scan và quyết định xử lý |

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ nhìn version trong `pom.xml` | Bỏ sót version do BOM/transitive dependency quyết định | Kiểm tra effective POM và dependency tree |
| Nâng riêng Spring Security module | Các module lệch release line, lỗi runtime hoặc binary incompatibility | Dùng Boot BOM hoặc bộ version đã được hỗ trợ |
| Chọn Authorization Server chỉ vì bản mới nhất | Có thể không tương thích Spring Security hiện tại | Xác minh release line và dependency metadata |
| Coi build thành công là tương thích | Bỏ sót lỗi protocol, persistence và key rotation | Chạy integration/security regression tests |
| Chỉ kiểm tra compileClasspath | Runtime thiếu hoặc xung đột dependency | Kiểm tra runtime/test graph và image cuối |
| Dùng H2 thay database production cho mọi test | Bỏ sót khác biệt SQL, transaction và driver | Test trên database engine tương ứng |
| Override Nimbus/Jackson không có bằng chứng | Lỗi JWT/JWK hoặc serialization khó chẩn đoán | Theo BOM; override có lý do và test riêng |
| Không lưu baseline artifact | Không tái hiện được môi trường trước nâng cấp | Lưu commit, digest, dependency report và SBOM |
| Nâng framework cùng schema phá vỡ tương thích | Rollback không đọc được authorization cũ | Dùng expand-and-contract và compatibility test |

## Kết luận

Xác định baseline và ma trận tương thích là bước đầu tiên để nâng cấp Authorization Server có kiểm soát. Hãy lấy version đã resolve từ artifact thực tế, dùng Spring Boot BOM làm nguồn quản lý nền tảng, xác minh Spring Authorization Server tương thích với Spring Security và đánh giá riêng các dependency có ảnh hưởng đến JWT, persistence, database và observability. Một ma trận có trạng thái, bằng chứng, ngày xác minh và kết quả test giúp phân biệt rõ tổ hợp được hỗ trợ với tổ hợp chỉ build được hoặc chưa được kiểm chứng. Khi baseline có thể tái lập và candidate được kiểm tra xuyên suốt các luồng OAuth 2.0/OIDC, đội dự án có cơ sở đáng tin cậy để lập kế hoạch nâng cấp và rollback.
