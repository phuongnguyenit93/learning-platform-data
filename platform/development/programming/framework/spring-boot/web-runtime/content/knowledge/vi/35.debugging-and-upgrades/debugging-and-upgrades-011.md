# Rà soát thay đổi mặc định, thuộc tính đổi tên và hỗ trợ máy chủ khi nâng phiên bản Spring Boot

## 1. Vì sao “nâng version rồi build xanh” chưa đủ?

Một ứng dụng Spring Boot có thể **compile, start và trả HTTP 200** sau khi nâng phiên bản nhưng vẫn thay đổi hành vi khi gặp request thật: URL có dấu `/` cuối không còn match, `server.*` được đổi tên nên giới hạn HTTP header không còn như dự kiến, `management.*` khiến endpoint quản trị được expose khác, Servlet/Jakarta API không tương thích với Tomcat cũ, hoặc test dùng mock context nên bỏ sót lỗi HTTP listener.

Nâng cấp Spring Boot là bài toán kiểm tra **hợp đồng web runtime**, không chỉ thay một số version trong `pom.xml`/`build.gradle`.

Ba nhóm rủi ro bắt buộc rà soát:

1. **Thay đổi mặc định (default behavior changes):** cùng code/config nhưng routing, security, encoding, shutdown, metrics, session, lỗi HTTP, server auto-configuration hoặc dependency behavior khác.
2. **Thuộc tính được đổi tên/xóa/thay ý nghĩa (configuration migration):** key cũ bị bỏ qua, alias chỉ còn tạm thời, default được áp dụng âm thầm hoặc cấu hình ở nguồn khác có ưu tiên cao hơn.
3. **Khả năng hỗ trợ máy chủ và nền tảng (server/platform support):** Java, Spring Framework, Jakarta Servlet, Tomcat/Jetty/Undertow, Netty, external WAR container, build plugins, Spring Cloud và dependencies phải thuộc **ma trận tương thích**.

Bài thuộc nhóm **Gỡ lỗi và nâng cấp** của module **Spring Boot - web-runtime**. Ví dụ thực hành dùng **Spring Boot 3.5.16, Java 17+, Maven, Spring MVC/Tomcat** làm baseline và giải thích riêng việc đi từ Spring Boot 2.x → 3.x và 3.5.x → 4.x. Các số version là **mốc minh họa được gắn với tài liệu của từng line**, không có nghĩa mọi ứng dụng phải nâng ngay lên mốc đó.

### Sau bài này bạn sẽ làm được

- Lập inventory code, dependencies, configurations và môi trường chạy trước nâng cấp.
- Phân biệt **changed default**, **renamed key**, **removed API** và **unsupported container**.
- Dùng release notes, migration guides, metadata, diagnostics và `spring-boot-properties-migrator` đúng cách.
- Kiểm tra cấu hình sau khi nhiều sources (profile, environment, CLI, Kubernetes) cùng tham gia.
- Viết regression tests cho HTTP path matching, status/body, header, health, security và startup.
- Kiểm tra embedded Tomcat/Jetty/Undertow và external WAR containers theo từng major line.
- Triển khai theo từng bước có canary, metrics, rollback và bằng chứng kết quả.

## 2. Bốn loại thay đổi thường bị lẫn lộn

| Loại thay đổi | Ý nghĩa | Ví dụ được kiểm chứng | Cách ứng phó |
| --- | --- | --- | --- |
| Default đổi | Property không đặt, behavior tự thay | Spring Framework 6 mặc định **không** match trailing slash | Viết contract test và cấu hình rõ policy |
| Property rename | Key mới thay key cũ | Boot 3: `server.max-http-header-size` → `server.max-http-request-header-size` | Đổi source configs, xác minh binding |
| API/dependency migration | Package/class/starter khác | Boot 3: Servlet imports `javax.servlet` → `jakarta.servlet` | Compile, update deps, test runtime |
| Support matrix đổi | Runtime/server cũ không còn hỗ trợ | Boot 4: baseline Servlet 6.1, Tomcat 11; Undertow bị bỏ | Chọn server compatible, cập nhật image/OS/deploy |

Một property được đổi tên **không đồng nghĩa giá trị mặc định vẫn như cũ**. Cũng không nên mặc định “migrator báo không có key cũ” nghĩa tất cả config đều hợp lệ: keys trong Kubernetes ConfigMap, environment, Helm templates, external secrets hoặc `@PropertySource` có thể không được migrator đọc ở đúng thời điểm.

### Ví dụ dễ nhầm

Giả sử API:

```java
@GetMapping("/api/items/{sku}")
public Item get(@PathVariable String sku) { ... }
```

Trong một hệ thống cũ, `/api/items/pen/` có thể trả 200. Spring Framework 6 thay mặc định trailing slash matching thành **false** nên cùng URL có thể trả 404. Chỉ so số lượng controllers hoặc compile không phát hiện được. Cần test hai URL thực tế và quyết định API contract: chấp nhận cả hai, redirect canonical URL hay trả 404.

Đoạn trên là **snippet** để minh họa behavior, không phải file Java chạy riêng. Mã runnable ở mục 11.

## 3. Ghi nhận baseline trước khi đổi version

Không bắt đầu bằng lệnh sửa POM. Đầu tiên lưu một **baseline có thể tái lập**.

### 3.1. Inventory bắt buộc

| Nhóm | Cần ghi lại |
| --- | --- |
| Build | Spring Boot parent/plugin, Maven/Gradle wrapper, Java toolchain, Gradle/Maven versions |
| Spring stack | Spring Framework, Spring Security, Spring Data, Spring Cloud train, Micrometer, Actuator |
| Web runtime | MVC hay WebFlux, Tomcat/Jetty/Undertow/Netty, embedded hay WAR external |
| Container | Tomcat image/version, Jakarta Servlet level, OS/JDK, connectors, HTTP/2/TLS |
| Dependencies | BOM, dependency tree, pin/override versions, direct `javax.*` libraries, native libs |
| Runtime config | `application*.yml/properties`, environment, CLI args, ConfigMap/Secret, JVM/system props |
| HTTP contract | Method/path/status, media types, validation, error schema, trailing slash, CORS |
| Edge behavior | Headers, forwarded proxies, sessions/cookies, compression, upload limits, shutdown |
| Observability | Actuator exposure, metrics names/tags, traces, health/readiness, log format |
| Operations | Resource limits, pool/thread counts, database schema, deploy strategy, rollback |

Cũng cần lưu **Git revision, container image digest, commit/build ID**, danh sách profiles đang active và cấu hình có thể công bố **đã loại secrets**. Không dump token/cookie/password từ `Environment` vào logs chỉ để so sánh.

### 3.2. Lấy thông tin build

Maven:

```bash
java -version
mvn -version
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:*,org.springframework:*
```

Cú pháp `-Dincludes` ở trên là ví dụ lọc dependency tree bằng Maven Dependency Plugin; nếu shell diễn giải ký tự `*`, bao quote hoặc dùng includes đơn giản. File `effective-pom` có thể chứa cấu hình nhạy cảm ở project thực; đừng publish ra nơi công khai.

Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot
./gradlew dependencyInsight --dependency tomcat
```

Khi cần audit dependency đầy đủ, lưu báo cáo SBOM/SCA do pipeline tổ chức hỗ trợ. Mục tiêu là phát hiện các transitive versions trái với Spring Boot BOM trước và sau đổi version.

### 3.3. Lưu một HTTP baseline

Ít nhất hãy chạy các request đại diện trước nâng cấp:

```bash
curl -i http://127.0.0.1:8080/api/items/pen
curl -i http://127.0.0.1:8080/api/items/pen/
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":2}'
curl -i http://127.0.0.1:8080/actuator/health
```

Đây là **mẫu commands**. Với ứng dụng thật, thay URL bằng contract thực; bảo đảm môi trường test được phép và test data synthetic. Ghi status, Content-Type, JSON schema, headers và body — không chỉ “endpoint trả được”.

## 4. Đọc tài liệu nâng cấp đúng đường đi

**Thứ tự đáng tin:**

1. **Spring Boot system requirements** cho target line/version.
2. **Migration guide** từ source major/feature line sang target line, đặc biệt phần web, property, tests và server.
3. **Release notes theo từng feature release đi qua**, không bỏ qua các version trung gian.
4. Release notes của Spring Framework, Security, Data, Cloud, Micrometer và libraries bạn thật sự dùng.
5. API Javadoc, configuration metadata và runtime diagnostics để xác minh keys/code của version đích.
6. Thực nghiệm regression tests trên target artifact/container.

Nếu đi từ **2.7.x → 3.5.x**, không chỉ đọc release notes 3.5. Cần nắm Boot 3.0 migration (Jakarta, Spring Framework 6, property changes, URL matching) rồi các thay đổi 3.1/3.2/3.3/3.4/3.5. Nếu đi từ **3.5.x → 4.x**, xem hướng dẫn Boot 4 vì đó là major migration: Spring Framework 7, Servlet 6.1, dependency modules/starters thay đổi và nhiều deprecated APIs bị loại.

**Không dựa vào một blog viết cho Boot 2 hoặc snapshot docs để kết luận behavior của target line mới.** Hãy đối chiếu URL/version của tài liệu.

## 5. Phác họa ma trận phiên bản và máy chủ

Các mốc dưới đây theo system requirements/migration guide chính thức, đọc theo **target line**, không ghép một server của Boot 4 với Boot 3 rồi suy đoán.

| Mốc | Java tối thiểu | Spring Framework | Embedded Servlet containers nổi bật | External WAR |
| --- | --- | --- | --- | --- |
| Boot 2.7.x | Java 8 (đối chiếu exact patch) | Spring Framework 5.3 | Tomcat 9 / `javax.servlet` generation | Servlet 3.1+/Java EE generation, tùy release |
| Boot 3.5.16 | Java 17 | Spring Framework 6.2.19+ | Tomcat **10.1** (Servlet 6), Jetty **12.0** (Servlet 6), Undertow **2.3** (Servlet 6) | **Servlet 5.0+ compatible** |
| Boot 4.0.x | Java 17 | Spring Framework **7.x** | Tomcat **11**, Jetty **12.1** (Servlet 6.1) | Servlet **6.1+**; Undertow support removed |
| Boot 4.1.x | Java 17 (theo docs hiện hành) | Spring Framework 7.x | Tomcat 11/Jetty 12.1 Servlet 6.1 | Kiểm tra trang system requirements của **đúng patch** |

**Lưu ý:** dòng 2.7.x là **tóm tắt thế hệ**, không dùng để phê duyệt Java 8 cho mọi dependency/JDK tương lai. Một số Boot 2.7 patch được biên dịch/có yêu cầu platform cụ thể; xác minh phiên bản exact. Với Boot 4.1, hãy đọc `https://docs.spring.io/spring-boot/4.1/system-requirements.html` thay vì giữ cố định nội dung bảng cho mọi patch.

### 5.1. Ba bước kiểm tra server compatibility

- Đọc target **Boot system requirements** và Embedded Container matrix.
- Đọc **Java/Jakarta Servlet** version của external Tomcat/application server. Tomcat 9 `javax.servlet.*` không chạy trực tiếp Boot 3 Jakarta Servlet app; Tomcat 10.1 là generation Servlet 6.0; Tomcat 11 là Servlet 6.1.
- Kiểm tra runtime thực khi deploy: `NoSuchMethodError`, `NoClassDefFoundError`, missing class, Servlet startup, HTTP routing, SSL connectors và proxy path. Compile success không chứng minh external WAR compatibility.

### 5.2. Undertow thay đổi giữa 3 và 4

Boot 3.5 hỗ trợ Undertow 2.3 như embedded Servlet option. Spring Boot 4 migration guide **loại Undertow support** vì baseline Servlet 6.1 trong khi Undertow chưa phù hợp tại thời điểm phát hành. Nếu app đang dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
```

thì đó là **snippet dependency của Boot 3.x**, không thể giữ nguyên để khẳng định Boot 4 còn hỗ trợ. Khi nâng Boot 4, chọn Tomcat/Jetty được hỗ trợ, kiểm tra connection settings, compression, websocket/session behavior và latency; không chỉ đổi một starter rồi kết luận giống nhau.

### 5.3. Spring Boot 4 modular starters

Boot 4 chuyển sang module/starter rõ hơn. Theo 4.0 migration guide, `spring-boot-starter-web` được đánh dấu deprecated và nên thay bằng **`spring-boot-starter-webmvc`** khi nâng cấp. Tương tự, một số technologies như Flyway/Liquibase cần Boot-specific starter tương ứng. Không tự cho rằng code Boot 3.5 compile nguyên xi trên 4.0 chỉ nhờ đổi số version: package names/test auto-configuration/dependencies có thể thay.

Với Boot 4, có thể dùng **classic starters** như một bước chuyển tiếp khi migration guide cho phép, nhưng đó không nên là đích cuối dài hạn. Hãy xem đúng bảng starter và package moves trong guide.

## 6. Thay đổi mặc định cần rà soát đặc biệt ở web runtime

Một default thay đổi có thể **không tạo lỗi build** nhưng gây vấn đề production. Nhóm sau nên có regression test hoặc quyết định explicit policy.

### 6.1. Trailing slash và path matching

Spring Framework 6.0 đổi default trailing-slash matching thành **false**: `/api/items/pen` và `/api/items/pen/` không mặc nhiên tương đương.

Ví dụ từ Boot 2.x/Spring MVC cũ có thể trả 200 cho cả hai, nhưng Boot 3.x có thể trả 404 ở URL có dấu `/` cuối. Đừng bật lại behavior global chỉ để làm tests xanh mà không xem ảnh hưởng security matchers/proxy; có thể:

- Trả 404 cho URL không canonical.
- Redirect `/api/items/pen/` về `/api/items/pen` tại gateway/filter với semantics đúng (308 có thể giữ method/body hơn 301 trong nhiều use case).
- Định nghĩa rõ cả hai routes khi hợp đồng API thật sự cho phép.
- Review Security matchers để tránh một path được bảo vệ còn path tương tự bị bỏ sót.

**Phải test actual URLs** trong môi trường target. MockMvc giúp test MVC mappings; live HTTP/proxy tests cần khi path rewrite/container context là vấn đề.

### 6.2. HTTP request header size và container differences

Trong Boot 3 migration, property cũ:

```properties
server.max-http-header-size=16KB
```

được thay bằng:

```properties
server.max-http-request-header-size=16KB
```

Key mới nhấn mạnh **request** header size. Tài liệu Boot 3.0 giải thích property cũ có behavior không nhất quán: Tomcat có lúc tác động cả response header, trong khi Jetty/Netty/Undertow không giống. Giới hạn **response header** của một số server cần server-specific customization, không tự áp từ key request mới.

Đừng mặc định giữ giá trị key cũ sẽ có cùng giới hạn sau upgrade. Test oversized request headers có kiểm soát với giới hạn môi trường test, xác định status của **actual target server** và không coi status code là bất biến giữa containers.

### 6.3. Actuator web và JMX exposure

Spring Boot 3.0 migration guide ghi JMX exposure mặc định chỉ còn **health** để đồng nhất với hướng mặc định web exposure. Đồng thời `httptrace` endpoint đổi tên thành **`httpexchanges`**, API và repository classes thay đổi.

Những điều cần test:

- Những endpoints nào thực sự exposed trên HTTP/JMX?
- Admin/metrics endpoint có bảo vệ bởi security/network policy không?
- Health/readiness paths có đổi vì context-path hay management base-path?
- Monitoring dashboards và alert rules còn đúng metrics names/tags không?
- Client cũ gọi `/actuator/httptrace` có cần migrate thành `/actuator/httpexchanges` không?

Đây là **endpoint rename**, không khẳng định mọi property nằm dưới prefix `management.endpoint.httptrace.*` có 1–1 mapping tự động sang prefix mới.

### 6.4. Spring Security mặc định và matcher behavior

Spring Security versions cũng thay theo Boot. Không dựa vào behavior pre-5.7 của `WebSecurityConfigurerAdapter`, ant matchers hoặc default security auto-configuration. Với Boot 3/Spring Security 6, thường dùng `SecurityFilterChain` bean và `requestMatchers` theo API tương thích. 

Regression tests phải bảo đảm:
- Anonymous vào endpoint public được phép, private nhận 401/403 đúng.
- POST/PUT/DELETE với session cookie có CSRF rule đúng.
- CORS preflight được xử lý theo policy.
- Matcher patterns cho trailing-slash/context path không để lọt route.
- Password encoders/session/cookie flags và authentication redirects không lệch.

**Không vô hiệu hóa toàn bộ SecurityFilterChain để làm một test nâng cấp “pass”.**

### 6.5. Request/response content, JSON, error handling

Check:
- Jackson version và module registration (Java Time/Records/Kotlin).
- Unknown JSON fields, enum coercion, naming strategy, dates/time zones.
- Bean Validation annotations/Jakarta packages, error body shape.
- `Accept`/`Content-Type` negotiation và 406/415.
- `ProblemDetail`/error responses nếu app bật hoặc customize chúng.
- Multipart limits, upload temp directory và proxy buffering.
- Compression, forwarded headers, redirects, host/scheme construction.

Nhiều lỗi chỉ xuất hiện khi traffic có invalid input. Do đó negative tests 400/404/405/415/401/403 cũng quan trọng như 200.

### 6.6. Graceful shutdown, async và resource lifecycle

Boot 3 migration guide ghi lifecycle phases của graceful shutdown đã thay đổi. Một app có `SmartLifecycle` custom, scheduler, message listener hoặc connection draining logic cần test thứ tự shutdown, thời gian terminate và readiness behavior. Ngoài ra xem:
- Request đang xử lý được hoàn tất hay bị ngắt?
- Kubernetes termination grace period có đủ không?
- JDBC pool/client/thread executor được đóng đúng?
- Sticky sessions hoặc WebSocket connections phục hồi như mong muốn?
- Health/readiness đổi trạng thái trước khi stop nhận traffic chưa?

Không áp một giá trị timeout chung mà không đo workload.

## 7. Property rename: đọc đúng key và phạm vi version

Các ví dụ có nguồn trong migration guides chính thức:

| Bối cảnh | Key/tên cũ | Key/tên mới hoặc cách xử lý |
| --- | --- | --- |
| Boot 2.7 → 3.0 | `server.max-http-header-size` | `server.max-http-request-header-size` |
| Boot 2.7 → 3.0 Redis | `spring.redis.*` | `spring.data.redis.*` |
| Boot 2.7 → 3.0 Cassandra | `spring.data.cassandra.*` | `spring.cassandra.*` |
| Boot 2.7 → 3.0 Actuator endpoint | `httptrace` | `httpexchanges` endpoint/API; review client |
| Boot 3.x → 4.0 Spring Session Redis | `spring.session.redis.*` | `spring.session.data.redis.*` |
| Boot 3.x → 4.0 Spring Session MongoDB | `spring.session.mongodb.*` | `spring.session.data.mongodb.*` |
| Boot 4 starters | `spring-boot-starter-web` | `spring-boot-starter-webmvc` được khuyến nghị |
| Boot 4 test HTTP clients | Boot 3 `TestRestTemplate` auto-configuration assumptions | Boot 4 requires explicit test auto-configuration/dependencies; xem migration guide |

**Không dùng bảng như một lệnh search-and-replace trên mọi repo**. Phải biết source/target version và component có xuất hiện trong app hay không. Ví dụ một app không dùng Cassandra không cần thay key Cassandra; một app có Redis client ngoài Spring Data có thể có namespace config riêng.

### 7.1. Rename khác với remove/semantic change

- **Rename:** property cùng ý nghĩa chuyển sang tên khác; key cũ có thể chỉ còn tương thích tạm.
- **Remove:** property bị loại hoàn toàn; cần xóa hoặc thay thiết kế, không có alias.
- **Split/merge:** một key cũ thành nhiều keys mới hoặc một key mới đổi scope.
- **Behavior changed:** tên key còn nguyên nhưng default, precedence hoặc implementation khác.
- **Conditional auto-configuration changed:** chỉ có bean khi classpath/feature dependency phù hợp.
- **Starter moved:** dependency đổi chứ property có thể không đổi.

Một auto-config không được load nữa có thể khiến property tồn tại mà không được bind. Hãy quan sát effective `@ConfigurationProperties` beans và condition evaluation, không chỉ grep key trong source code.

## 8. Spring Boot properties migrator: công cụ chuyển tiếp, không phải “fix”

Spring Boot có `spring-boot-properties-migrator` giúp phân tích Environment tại startup và log diagnostics về một số renamed/removed properties; trong những trường hợp được hỗ trợ nó có thể **tạm thời migrate values tại runtime**.

Thêm **tạm thời** vào Maven của target Spring Boot line:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Gradle:

```groovy
runtimeOnly("org.springframework.boot:spring-boot-properties-migrator")
```

Quy trình:

1. Nâng dependencies và chạy ứng dụng trong local/staging với profiles gần production.
2. Đọc warning diagnostics: key cũ, thay thế đề xuất hoặc key bị loại.
3. Sửa **nguồn cấu hình thực**: application YAML, environment, Helm/Kustomize/ConfigMap, deployment scripts, secret references, CI variables.
4. Khởi động lại để xác nhận không còn warning và behavior đúng.
5. **Gỡ dependency migrator** khỏi production build sau khi hoàn tất.

**Không giữ migrator vĩnh viễn.** Tài liệu Boot cảnh báo properties được thêm muộn vào Environment, ví dụ từ `@PropertySource`, có thể không được xử lý. Migrator không kiểm tra mọi ứng dụng tự tạo keys, không tìm tất cả Helm templates hoặc biến môi trường ngoài runtime hiện tại, và không thay integration tests.

### 8.1. Ví dụ sửa cấu hình

Cấu hình cũ khi chuyển từ 2.7 sang 3.x:

```properties
server.max-http-header-size=16KB
spring.redis.host=redis.internal.example
spring.redis.port=6379
```

Cấu hình theo Spring Boot 3.x:

```properties
server.max-http-request-header-size=16KB
spring.data.redis.host=redis.internal.example
spring.data.redis.port=6379
```

Tên host trên chỉ là **địa chỉ minh họa không dùng làm target thật**. Không commit credential hoặc địa chỉ private production vào bài hướng dẫn. Cần test network và Redis version riêng khi app thực sử dụng Redis.

### 8.2. Bước sau migrator vẫn bắt buộc

- Đảm bảo mọi key được config binder nhận, không chỉ không có warning.
- Đo effective behavior: header limit, Redis connection, session TTL, Actuator exposure, HTTP status.
- Kiểm tra profiles/local/staging/prod khác nhau.
- So dependency tree để bảo đảm appropriate auto-configuration có trên classpath.
- Re-run smoke và integration tests sau khi **gỡ migrator**; nếu app chỉ chạy được khi còn migrator thì chưa hoàn thành migration.

## 9. Property precedence và “giá trị bị thay ngầm”

Ngay cả khi đã đổi đúng key, runtime vẫn có thể dùng một giá trị khác do thứ tự ưu tiên của nguồn config.

Các nguồn thường gặp:

- `application.properties`/`application.yml` trong artifact.
- `application-prod.yml`/`application-staging.yml` với active profiles.
- External config locations/config trees.
- Environment variables của host/container/pod.
- JVM system properties và CLI arguments.
- Test-specific `@TestPropertySource`/`@SpringBootTest(properties=...)`.
- Spring Cloud Config hoặc một configuration provider khác (nếu có).

Ví dụ:

```properties
# Trong JAR
server.port=8080
```

Và process được chạy bằng:

```bash
java -jar app.jar --server.port=9090
```

CLI argument có thể override property file. Nếu developer nhìn file rồi kết luận app mở 8080, kết luận đó sai cho process trên.

### 9.1. Điều tra effective configuration an toàn

- Xem application startup logs: active profiles và port thực.
- Nếu có Actuator, dùng `configprops`/`env` **chỉ trong môi trường bảo vệ**, với sanitization và access control, khi cần điều tra bindings.
- Có thể in **các giá trị không nhạy cảm, được allowlist** trong một diagnostic endpoint chỉ dành cho test.
- Với secret values, kiểm tra **nguồn và trạng thái được bind**, không in plaintext.
- Chạy test trên artifact/container gần production, không chỉ `mvn test` với profile mặc định.
- Khi thấy key cũ, tìm trong CI/CD, ConfigMaps, Deployment env vars, Helm charts và external config; repository search không đủ.

### 9.2. Relaxed binding không sửa rename

Spring Boot cho phép relaxed binding, ví dụ `server.max-http-request-header-size` và `SERVER_MAX_HTTP_REQUEST_HEADER_SIZE` trong environment. Nhưng relaxed binding **không tự biến một tên property đã bị remove thành tên mới**. Nếu source dùng `SERVER_MAX_HTTP_HEADER_SIZE`, đó không phải cùng key hợp lệ như `SERVER_MAX_HTTP_REQUEST_HEADER_SIZE` ở Boot 3.

Cần xác định tên đầy đủ của key mới, không dựa vào việc Boot “tự hiểu” tên cũ.

## 10. BOM, starter, Jakarta và server chọn như thế nào?

### 10.1. Để Boot quản lý dependency versions khi có thể

Trong Maven dùng `spring-boot-starter-parent` hoặc import `spring-boot-dependencies` BOM. Trong Gradle dùng Boot plugin và dependency management/native platforms. Tránh pin riêng Spring Framework, Tomcat, Jackson, SnakeYAML, Netty, Hibernate, Micrometer trừ khi có lý do được hỗ trợ và có regression test.

Nếu Spring Cloud được dùng, phải chọn release train tương thích với **target Boot line**. Không đổi Boot 3.x → 4.x rồi giữ nguyên Cloud train chỉ vì code compile. Kiểm tra official compatibility matrix, enterprise support policy và third-party starter versions.

### 10.2. Servlet container khi chuyển Boot 2 sang 3

- Boot 2/Framework 5 dùng `javax.servlet` generation; Tomcat 9 thường là server.
- Boot 3/Framework 6 chuyển sang `jakarta.servlet`, Jakarta EE 10 baseline.
- Update import statements, compiled libraries, test dependencies và external Tomcat accordingly.
- External WAR chạy trên Tomcat 9 không tự tương thích khi Servlet API namespace khác.
- Đối với Tomcat 10.1, xác minh HTTP connectors, TLS, sessions, JSP, classpath/Servlet filters.

Code ví dụ Boot 3:

```java
import jakarta.servlet.http.HttpServletRequest;
```

Nếu thấy `javax.servlet.http.HttpServletRequest`, chưa hoàn thành migration. Tuy nhiên **đừng thay mọi `javax.*` package bằng `jakarta.*` vô điều kiện**: chỉ các Jakarta EE APIs đã migrate; `javax.crypto`, `javax.net`, `javax.xml` thuộc JDK và vẫn tồn tại.

### 10.3. Servlet container khi chuyển Boot 3.5 lên 4

Spring Boot 4 dựa trên Jakarta EE 11/Servlet 6.1 và Spring Framework 7. Tomcat 11 và Jetty 12.1 là các embedded servlet options được docs nêu; Undertow support bị loại trong 4.0 migration guide.

Nếu triển khai WAR vào external server, hãy kiểm tra **Servlet 6.1+**, không chỉ “Tomcat đang chạy”. Tomcat 10.1 (Servlet 6.0) **không đáp ứng** target Servlet 6.1 requirement của Boot 4. Không hạ target API version như một cách lách support matrix nếu vendor chưa xác nhận.

### 10.4. Reactor Netty và Spring WebFlux

Reactive WebFlux application thường dùng Reactor Netty, không nằm trong Servlet container table theo cùng nghĩa MVC. Kiểm tra Reactor Netty/Netty release, TLS, HTTP/2, event-loop threads, `WebClient` behavior và reactive security riêng. Không suy từ Tomcat 11 support rằng WebFlux application đã được kiểm thử.

### 10.5. `spring-boot-starter-web` và Boot 4

Theo Boot 4 migration guide, `spring-boot-starter-web` được deprecated để đổi sang `spring-boot-starter-webmvc` theo modular starter convention. Boot 4 còn thay auto-configuration package layout và test APIs. Một build cần review imports/dependencies hơn là chỉ đổi `<version>`.

**Lab mục 11 cố ý neo ở Boot 3.5.16.** Nếu dùng Boot 4, hãy chuyển starters, API packages và test configuration theo migration guide trước khi mong bộ mã đó compile.

## 11. Lab đầy đủ: khóa hành vi HTTP trước khi nâng Boot 3.5

Tạo một service nhỏ với:

- `GET /api/items/{sku}` trả JSON và header xác định API contract.
- `POST /api/quotes` validate JSON và tính tổng.
- `GET /api/contract` trả metadata **không nhạy cảm** để phân biệt version/config của sample.
- `@RestControllerAdvice` cho error code rõ.
- `application.properties` có các cấu hình minh họa được ghi rõ.
- JUnit service, MockMvc slice và `@SpringBootTest(RANDOM_PORT)` live HTTP tests.

Mục tiêu là **khóa behavior** trước khi thử upgrade; không phải tối ưu một Spring Boot 3.5 production template.

### 11.1. Cấu trúc thư mục

```text
boot-upgrade-audit/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/upgrade/
    │   │   ├── UpgradeAuditApplication.java
    │   │   ├── CatalogService.java
    │   │   ├── CatalogController.java
    │   │   └── ApiErrors.java
    │   └── resources/application.properties
    └── test/java/com/example/upgrade/
        ├── CatalogServiceTest.java
        ├── CatalogMvcTest.java
        └── UpgradeBehaviorHttpTest.java
```

Không cần database. Các files public classes trùng tên và package cùng root.

### 11.2. `pom.xml` chạy Spring Boot 3.5.16

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>boot-upgrade-audit</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Không thêm `spring-boot-properties-migrator` trong POM baseline cố định**. Dùng dependency đó **chỉ tạm thời khi đang migration**, gỡ sau khi sửa tất cả keys. Version Spring Boot 4 có starter/test package changes, không thay thẳng version rồi coi project đã Boot-4-compatible.

### 11.3. `UpgradeAuditApplication.java`

```java
package com.example.upgrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UpgradeAuditApplication {

    public static void main(String[] args) {
        SpringApplication.run(UpgradeAuditApplication.class, args);
    }
}
```

### 11.4. `CatalogService.java`

```java
package com.example.upgrade;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    public record Item(String sku, long unitPriceVnd) {
    }

    public record Quote(
            String sku,
            int quantity,
            long unitPriceVnd,
            long totalVnd) {
    }

    public Item item(String sku) {
        return switch (sku) {
            case "pen" -> new Item("pen", 12_000);
            case "book" -> new Item("book", 35_000);
            default -> throw new UnknownItemException(sku);
        };
    }

    public Quote quote(String sku, int quantity) {
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be 1..100");
        }
        Item found = item(sku);
        return new Quote(
                found.sku(),
                quantity,
                found.unitPriceVnd(),
                Math.multiplyExact(
                        found.unitPriceVnd(), (long) quantity));
    }
}

class UnknownItemException extends RuntimeException {
    UnknownItemException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

Business rules không phụ thuộc HTTP stack, nên unit tests sẽ tiếp tục có giá trị khi đổi server/Boot. `Math.multiplyExact` tránh silent overflow.

### 11.5. `CatalogController.java`

```java
package com.example.upgrade;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record QuoteRequest(
        @NotBlank String sku,
        @Min(1) @Max(100) int quantity) {
}

@RestController
@RequestMapping("/api")
public class CatalogController {

    private final CatalogService catalog;

    public CatalogController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            value = "/items/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CatalogService.Item> item(
            @PathVariable String sku) {
        return ResponseEntity.ok()
                .header("X-Api-Contract", "catalog-v1")
                .body(catalog.item(sku));
    }

    @PostMapping(
            value = "/quotes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public CatalogService.Quote quote(
            @Valid @RequestBody QuoteRequest request) {
        return catalog.quote(
                request.sku(), request.quantity());
    }

    @GetMapping(
            value = "/contract",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> contract() {
        return Map.of(
                "api", "catalog-v1",
                "routing", "explicit");
    }
}
```

`@Valid` cần Jakarta validation starter; record DTO dùng Java 17. Header `X-Api-Contract` là contract của **demo**, không phải header tự sinh bởi Spring Boot. Việc xác minh nó giúp bắt được fallback route trả HTML/response sai.

### 11.6. `ApiErrors.java`

```java
package com.example.upgrade;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(UnknownItemException.class)
    public ResponseEntity<Map<String, String>> missing(
            UnknownItemException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                Map.of("code", "ITEM_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalid(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_REQUEST"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_JSON"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badArgument(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_REQUEST"));
    }
}
```

Việc đưa error contract vào tests bảo vệ behavior khi framework thay default error response/exception mapping. Handler này chủ đích không serialize raw exception messages/stack traces ra client.

### 11.7. `application.properties`

```properties
spring.application.name=boot-upgrade-audit

server.port=8080
server.max-http-request-header-size=16KB
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s

management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
```

Property `server.max-http-request-header-size` là key của Boot 3, **không** phải key cũ `server.max-http-header-size`. `server.shutdown=graceful` và shutdown phase timeout là explicit config để người đọc nhìn thấy intention, nhưng vẫn cần test actual draining. Các giá trị số 16KB/15s là **lab choices**, không tự thích hợp cho mọi production workload.

Actuator chỉ expose health và info. Nếu thêm Redis/JPA/Security ở project thật, kiểm tra health contributors/endpoint security riêng.

## 12. Unit và MVC tests: khóa business/API contract

### 12.1. `CatalogServiceTest.java`

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogServiceTest {

    private final CatalogService catalog =
            new CatalogService();

    @Test
    void computesPriceExactly() {
        assertEquals(
                new CatalogService.Quote(
                        "pen", 2, 12000, 24000),
                catalog.quote("pen", 2));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> catalog.quote("pen", 0));
    }

    @Test
    void rejectsUnknownSku() {
        assertThrows(UnknownItemException.class,
                () -> catalog.item("unknown"));
    }
}
```

Unit tests không có network hoặc Spring context. Chúng không thể phát hiện path matching hoặc Servlet container incompatibility, nhưng cho baseline về business logic.

### 12.2. `CatalogMvcTest.java`

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogService catalog;

    @Test
    void itemContractIncludesHeaderAndBody()
            throws Exception {
        given(catalog.item("pen"))
                .willReturn(new CatalogService.Item("pen", 12000));

        mvc.perform(get("/api/items/pen")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Api-Contract", "catalog-v1"))
                .andExpect(jsonPath("$.sku")
                        .value("pen"))
                .andExpect(jsonPath("$.unitPriceVnd")
                        .value(12000));
    }

    @Test
    void trailingSlashDoesNotMatchByDefault()
            throws Exception {
        mvc.perform(get("/api/items/pen/"))
                .andExpect(status().isNotFound());
    }

    @Test
    void quantityZeroIsRejectedByMvcValidation()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(post("/api/items/pen"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

Trong Boot 3.5/Spring Framework 6.2, `@MockitoBean` có package `org.springframework.test.context.bean.override.mockito`. Test slice kiểm tra MVC route/validation/converter nhưng không start embedded server; vì vậy thêm live HTTP tests. `CatalogService` được mock để slice tập trung contract.

Lưu ý: `status().isNotFound()` khẳng định trailing slash behavior của **Boot 3.5 MVC default trong lab này**. Nếu ứng dụng của bạn có custom URL matching, proxy rewrites hoặc explicit route, expected status phải theo contract đã thống nhất, không rập khuôn 404.

## 13. Live HTTP tests: bắt lỗi embedded server thực

Tệp `UpgradeBehaviorHttpTest.java`:

```java
package com.example.upgrade;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class UpgradeBehaviorHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void actualServerStartsAndReturnsContract() {
        assertTrue(port > 0);

        ResponseEntity<Map> response = http.getForEntity(
                url("/api/items/pen"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pen", response.getBody().get("sku"));
        assertEquals(12000,
                ((Number) response.getBody()
                        .get("unitPriceVnd")).intValue());
        assertEquals("catalog-v1",
                response.getHeaders()
                        .getFirst("X-Api-Contract"));
    }

    @Test
    void actualServerRejectsTrailingSlash() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/api/items/pen/"), String.class);

        assertEquals(
                HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void actualServerValidatesJson() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("pen", 0),
                        Map.class);

        assertEquals(
                HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals("INVALID_REQUEST",
                response.getBody().get("code"));
    }

    @Test
    void healthEndpointIsReachable() {
        ResponseEntity<Map> response = http.getForEntity(
                url("/actuator/health"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("UP",
                response.getBody().get("status"));
    }
}
```

Các test dùng **Tomcat thực trên random loopback port**, nên không phụ thuộc `server.port=8080` và tránh đụng cổng trong CI. Chúng có giá trị hơn MockMvc khi kiểm tra server initialization, real HTTP status/headers và container routing. Nhưng chúng **chưa** thử external reverse proxy, Kubernetes ingress, TLS hoặc WAR trong Tomcat độc lập.

### Quan trọng khi nhắm tới Boot 4

Boot 4 migration guide nói test packages/auto-configurations thay đổi và `@SpringBootTest` không tự cung cấp TestRestTemplate như Boot 3.5. Cần explicit `@AutoConfigureTestRestTemplate`, các dependencies cần thiết, package imports mới; hoặc chuyển sang `RestTestClient` theo hướng dẫn Boot 4. **Không khẳng định Java test code Boot 3.5 trên sẽ compile nguyên xi trên Boot 4.** Mục đích của lab là có baseline đúng để thực hiện migration một cách quan sát được.

## 14. Chạy lab, xem kết quả và kiểm tra key đã đổi

### 14.1. Yêu cầu

Có Java 17+, Maven, source files đúng đường dẫn.

```bash
java -version
mvn -version
mvn clean test
mvn clean package
java -jar target/boot-upgrade-audit-1.0.0.jar
```

Maven có thể cần network để tải dependencies lần đầu. Output số tests phụ thuộc Surefire version; không gán một dòng stdout cố định cho mọi môi trường.

### 14.2. Smoke HTTP

Ở terminal khác:

```bash
curl -i http://127.0.0.1:8080/api/items/pen
curl -i http://127.0.0.1:8080/api/items/pen/
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":2}'
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":0}'
curl -i http://127.0.0.1:8080/actuator/health
```

Kỳ vọng **với source và config demo Boot 3.5.16**:

| Request | Status | Điều phải kiểm tra |
| --- | --- | --- |
| GET `/api/items/pen` | 200 | Header `X-Api-Contract: catalog-v1`, JSON `sku=pen`, `unitPriceVnd=12000` |
| GET `/api/items/pen/` | 404 | Không match trailing slash theo default |
| POST `/api/quotes`, quantity 2 | 200 | JSON có totalVnd 24000 |
| POST `/api/quotes`, quantity 0 | 400 | JSON `code=INVALID_REQUEST` |
| GET `/actuator/health` | 200 khi healthy | JSON `status=UP` |

JSON body của POST thành công:

```json
{"sku":"pen","quantity":2,"unitPriceVnd":12000,"totalVnd":24000}
```

JSON property order không phải hợp đồng cần assert. Các giá trị ví dụ là **kỳ vọng từ mã nguồn**, không phải báo cáo benchmark/thực thi đã đo.

### 14.3. Negative checks và server limits

Đoạn dưới minh họa **một phép thử không hợp lệ**, cần chạy ở môi trường chỉ dành cho kiểm thử:

```bash
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: text/plain" \
  --data 'sku=pen&quantity=2'
```

Do controller yêu cầu JSON, kỳ vọng HTTP **415 Unsupported Media Type**, trừ khi có filter/proxy/security chặn trước. Kết quả có thể thay khi thay lớp security/container, chính là lý do cần lưu baseline.

Giới hạn request header (16KB trong lab) nên kiểm tra bằng một automated test có bound và mục tiêu an toàn; không tạo payload khổng lồ nhắm vào host production để tự thử overload. Status và ngưỡng chính xác có thể khác giữa Servlet containers/proxies.

## 15. Giám sát cấu hình và auto-configuration sau upgrade

### 15.1. `ConditionEvaluationReport`

Khi một starter bị chuyển/xóa, một bean có thể không còn auto-configured. Sử dụng debug/condition evaluation report trong test hoặc startup diagnostics để xem auto-configuration nào match/unmatch, thay vì đoán chỉ từ dependencies.

Ví dụ chạy local:

```bash
java -jar target/boot-upgrade-audit-1.0.0.jar --debug
```

Boot có thể log condition evaluation report. Log có thể dài và mang tên classes/dependencies; hãy loại secrets/PII trước khi chia sẻ. Không bật `--debug` vô thời hạn ở production để tránh log volume.

### 15.2. Actuator `configprops` và `env`

`configprops` và `env` có thể cho biết bound configuration, nhưng nhạy cảm. Để điều tra:
- Chỉ expose trong môi trường quản trị riêng, có auth/network restriction.
- Kiểm tra source/properties đã được sanitize.
- Tắt exposure bổ sung sau khi xong.
- Không gửi raw response chứa identifiers/credentials vào issue tracker công khai.

`management.endpoints.web.exposure.include=health,info` của demo không expose `env` hoặc `configprops`, cố ý giữ an toàn.

### 15.3. Quét cấu hình bằng search

Có thể tìm những keys cũ trong repo bằng Git grep ở project thực:

```bash
git grep -n "server.max-http-header-size"
git grep -n "spring.redis."
git grep -n "spring.data.cassandra."
git grep -n "management.endpoint.httptrace"
git grep -n "javax.servlet"
```

`git grep` chỉ nhìn các files tracked trong repo, không tự quét **external** ConfigMaps, Helm variable values, CI secrets, runtime environment hoặc thư viện binary. Nếu source code chứa string giả trong docs/tests, phải đánh giá ngữ cảnh thay vì replace tất cả.

Không chạy các lệnh grep trên production filesystem có secrets rồi paste toàn bộ output vào chat công khai. Chỉ giữ các match names an toàn.

## 16. So sánh trước–sau với migration matrix

Một migration matrix nên ghi **expected behavior của source** và **observed behavior của target**:

| Check | Source baseline | Target candidate | Verdict |
| --- | --- | --- | --- |
| Java/version/build | Ghi JDK, Boot, plugin versions | Ghi JDK mới, Boot BOM | Compatible? |
| Servlet engine | Tomcat/Jetty/Undertow version | Exact embedded/external version | Supported? |
| `GET /api/items/pen` | Status + body/header | Status + body/header | Same contract? |
| Trailing slash | 200 hoặc 404 theo source | 200/404 theo target | Intentional? |
| Invalid JSON | 400 + error schema | 400 + error schema | Same? |
| HTTP header limits | Old effective threshold | New effective threshold | Policy upheld? |
| Session cookie | Path/Domain/SameSite/Secure | Current flags | Safe? |
| Login/CSRF/CORS | 401/403/preflight | Current status/headers | Safe? |
| Actuator exposure | Endpoint/roles | Endpoint/roles | Not wider? |
| Graceful shutdown | Timing/active requests | Timing/active requests | Meets SLO? |
| Metrics/traces | Names/tags | Names/tags | Alerts working? |
| Startup/resources | Heap/threads/pool | Same load profile | No regression? |

“Target version number higher” **không đủ để điền verdict PASS**. Có thể một behavior thay đổi là mong muốn (ví dụ reject trailing slash theo canonical URL), nhưng phải được quyết định và được phản ánh trong tests/docs/clients.

### Bằng chứng tối thiểu của một dòng PASS

- Test name/command, environment, version, timestamp.
- Request và expected status/contract.
- Observed status/body/headers đã sanitized.
- Owner/người phê duyệt thay đổi nếu breaking.
- Rollback criteria nếu thay đổi không được chấp nhận.

Khi có nhiều profiles/tenants/regions, cần matrix theo profile/cấu hình representative, không chỉ dev laptop.

## 17. Security review không được bỏ qua

Khi upgrade framework, security posture có thể thay đổi do matcher semantics, dependencies, default filter order, cookie flags, Actuator exposure và server connector settings.

### Checklist chủ chốt

- **Authentication/authorization:** anonymous vs authenticated, role-based access, method/path matchers, resource servers.
- **CSRF:** browser sessions/cookies, unsafe methods và token lifecycle.
- **CORS:** OPTIONS preflight, Access-Control-Allow-Origin, credentials, headers.
- **Cookies:** Secure/HttpOnly/SameSite, Domain/Path, session persistence/redeploy.
- **HTTPS:** TLS versions/certificates/proxy forwarded headers/redirect locations.
- **Actuator:** `health`, `info` và mọi other exposed endpoints có policy rõ; không vô tình mở `env`, `heapdump`, `mappings`, `loggers`, `shutdown`.
- **Error pages:** không expose stack traces/internal class names vì default changed.
- **Uploads/static content:** resource path matching, content-type sniffing, cache controls.
- **Dependencies:** CVEs, transitive libraries và third-party starters.

Đừng biến security 403 thành 200 bằng cách đặt `permitAll("/**")` trong lúc migration. Cần xác minh security behavior đúng theo policy, không sửa chỉ để test xanh.

## 18. Performance và vận hành: nâng code không có nghĩa capacity giữ nguyên

Thay Spring Framework/Tomcat/Jetty/JDK có thể thay latency, thread scheduling, buffer allocation, TLS, GC và metric instrumentation. Đặt cùng traffic profile và dataset để so:

- Achieved RPS, p95/p99 theo operation, error rate và timeout rate.
- Tomcat active/busy threads, servlet request queue, HTTP connections.
- Hikari active/pending/timeout (nếu app có DB).
- JVM heap/GC pauses, CPU throttling, RSS, native buffers.
- PostgreSQL query latency, locks và connections.
- Actuator metrics/tracing names/tags và alerts.
- Startup time, readiness, graceful shutdown và autoscaler behavior.

Chạy smoke tests trước, rồi baseline load/soak ở môi trường được phép. **Không dùng 10 requests local để khẳng định throughput production không bị ảnh hưởng**.

### Một số thay đổi cần đo sau major upgrade

- Jackson/codec response size và serialization cost.
- Tomcat 10.1 → 11 servlet engine changes.
- Undertow → Tomcat/Jetty khi chuyển Boot 3 lên 4.
- JDK upgrades và GC configuration.
- Security filters/Observability middleware overhead.
- Thread/connection limits và HTTP/2/TLS settings.
- Scheduler/async completion, graceful shutdown phase order.
- DB pool size tổng nếu số replicas/threads thay đổi.

## 19. Quy trình nâng cấp theo giai đoạn và rollback

### Giai đoạn A — baseline và plan

1. Chốt source version, target line, JDK, server/container matrix.
2. Đọc official migration guides/release notes theo **đường đi**.
3. Liệt kê properties cũ, deprecated APIs, removed starters và library overrides.
4. Đóng băng artifact/test data/HTTP contract/SLO.
5. Phân loại breaking change theo người dùng, vận hành, security, data.

### Giai đoạn B — chuyển đổi build và code

1. Update Boot parent/BOM và build plugin.
2. Update Java toolchain; chuyển `javax` → `jakarta` theo scope cần thiết khi đi 2→3.
3. Đổi property keys ở tất cả config sources, thêm migrator **tạm thời** nếu phù hợp.
4. Sửa các removed/deprecated APIs và starter/package moves.
5. Chọn compatible Tomcat/Jetty/Netty, external WAR container nếu có.
6. Rebuild, unit/MVC/integration tests; loại transitive conflicts.

### Giai đoạn C — xác minh runtime

1. Start với profiles/config gần target production.
2. Check effective properties và condition evaluation không có bean missing.
3. Thực hiện live HTTP smoke/contract tests (positive + negative).
4. Verify Actuator exposure, security, TLS/proxy, cookies, context path.
5. Chạy representative load/soak và so metrics.
6. Gỡ properties migrator, build lại và chạy tests lần cuối.

### Giai đoạn D — triển khai có kiểm soát

- Canary/blue-green/rolling phù hợp; giữ khả năng rollback nếu data schema/migration cho phép.
- Monitor 4xx/5xx, p95/p99, readiness, restart count, CPU, heap/GC, pools, logs/traces.
- Có **rollback trigger** cụ thể: business errors tăng, auth failures, SLO miss, startup failure, queue growth.
- Nếu database migration là **irreversible**, rollback application binary có thể không đủ; cần expand/contract schema strategy và backup plan.
- Không chỉ đổi version trên toàn fleet cùng lúc khi chưa có quan sát.
- Sau deploy, kiểm tra từ public entrypoint (Ingress/TLS) và internal health của đúng app.

### Mẫu runbook

```text
Baseline:  Boot/source artifact, JDK, server, config snapshot
Candidate: Boot/target artifact, JDK, server, dependency tree
Feature flags/profiles and property migration diff:
Functional pass/fail: routes, status, JSON, invalid cases
Security pass/fail: auth, CORS, CSRF, cookies, Actuator
Runtime pass/fail: live HTTP, readiness, graceful shutdown
Performance pass/fail: p95/p99/errors/throughput
Canary percentage and monitoring window:
Rollback artifact/trigger/owner:
Open risks and approved behavior changes:
```

Mẫu trên không chứa kết quả thực tế. Mọi field cần điền bằng bằng chứng kiểm tra của hệ thống cụ thể.

## 20. Những lỗi phổ biến và cách phân biệt

| Triệu chứng | Nghi ngờ | Cách xử lý |
| --- | --- | --- |
| `GET /api/foo/` từ 200 thành 404 | Trailing slash default đổi | Test cả 2 URL; quyết định canonical contract |
| App start nhưng header limit sai | Key `server.max-http-header-size` cũ | Đổi `server.max-http-request-header-size` |
| Redis config không còn hiệu lực | Prefix `spring.redis` cũ | Kiểm tra `spring.data.redis` và connection thực |
| Cassandra binding không đúng | Prefix thay đổi khi 2→3 | Kiểm tra `spring.cassandra` |
| Actuator `/httptrace` 404 | Endpoint rename | Review `/httpexchanges` và repository/API |
| JMX endpoint biến mất | JMX exposure default khác | Set exposure explicit và kiểm tra security |
| `javax.servlet` ClassNotFound | Boot3/Jakarta migration thiếu | Cập nhật imports/dependencies/container |
| WAR Boot3 fail trên Tomcat9 | Servlet API không tương thích | Dùng Jakarta-compatible container |
| Boot4 WAR fail trên Tomcat10.1 | Servlet6.1 baseline | Tomcat11/compatible Servlet6.1+ |
| Boot4 Undertow dependency fail | Server support removed | Chọn supported Tomcat/Jetty |
| Boot4 test TestRestTemplate không inject | Test auto-config/packages changed | Đọc Boot4 migration guide và imports/deps |
| Boot4 `starter-web` deprecation | Modular starter changes | Dùng `starter-webmvc` theo guide |
| App startup fail với missing bean | Auto-configuration/starter moved | Review classpath + condition report |
| JSON body đổi mà unit tests xanh | Thiếu HTTP contract tests | Add MockMvc/live HTTP response assertions |
| 401/403 tăng sau upgrade | Security matchers/filters/CSRF | Policy regression tests, không permitAll |
| Prometheus alerts im lặng | Metric names/tags changed | Compare scrape outputs và dashboard rules |
| Health 200 ở Tomcat root nhưng WAR 404 | Sai context/deploy fail | Check per-WAR `/catalog/actuator/health` |
| Connection pool exhausted sau upgrade | Thread/pool/resource profile đổi | Observe Hikari/Tomcat/DB metrics |
| Properties migrator warning mất nhưng behavior sai | External config hoặc key không bind | Check effective config và runtime tests |
| Upgrading 2.7 trực tiếp sang 4 làm quá nhiều errors | Bỏ qua 3.x migrations | Đi qua latest 2.7/3.5 và major guides |
| App chạy local nhưng ingress 502 | Container readiness, port, proxy mismatch | Stage/proxy smoke theo deployment |
| Rollback thất bại | Schema/data migration không backward compatible | Expand-contract schema strategy |

## 21. Bài tập thực hành

### A. Reproduce trailing slash difference

Dùng project demo, chạy `GET /api/items/pen` và `GET /api/items/pen/`. Test expected 200 và 404 trên Boot3.5. Nếu muốn cả hai trả 200, thêm mapping explicit hoặc redirect có chủ đích và chỉnh test.

### B. Cấu hình key cũ

Thay `server.max-http-request-header-size` thành `server.max-http-header-size` khi chạy Boot3.5. Thêm properties migrator tạm thời, quan sát warning diagnostics; sửa lại key mới, gỡ migrator và kiểm tra startup. Không coi việc Tomcat start là bằng chứng header size đã đúng.

### C. Di chuyển Redis prefix

Một app Boot2.x dùng `spring.redis.host`. Lập migration diff sang `spring.data.redis.host` trong Boot3. Kiểm tra cả application YAML, profile, environment variable (`SPRING_DATA_REDIS_HOST`) và Helm templates. Không copy thông tin Redis thực vào logs.

### D. Ma trận server

Lập bảng Boot2.7/Tomcat9, Boot3.5/Tomcat10.1 và Boot4/Tomcat11 theo Java/Jakarta Servlet. Xác định cái nào có thể deploy WAR, cái nào cần rebuild/migrate package imports.

### E. Kiểm tra Boot4 Undertow

Nếu dùng `spring-boot-starter-undertow` trong Boot3.5, đọc 4.0 migration guide và thiết kế chuyển sang Tomcat hoặc Jetty. So sánh HTTP2, compression, websocket/session config và p95 trước–sau.

### F. Đổi Actuator endpoint

Nếu monitoring client gọi `/actuator/httptrace` ở đời cũ, thiết kế kiểm tra `/actuator/httpexchanges` theo target supported API và đảm bảo endpoint nhạy cảm không public.

### G. Thử `@SpringBootTest(RANDOM_PORT)` và proxy

Thấy tests local pass, sau đó deploy staging sau gateway `/shop`; kiểm tra API contract qua public path, TLS, cookies và forwarded headers. Nêu khác biệt giữa embedded server test và deployed E2E.

### H. Default bảo mật

Tạo matrix GET public, POST authenticated, POST CSRF-invalid, GET Actuator private. Sau upgrade kiểm tra status không được nới authorization. Nếu 403 thay đổi, điều tra matcher/policy thay vì tắt filters.

### I. Không được để migrator thành dependency cố định

Khi đã sửa toàn bộ keys, gỡ `spring-boot-properties-migrator`, build lại và chạy cùng suite. Nếu app chỉ pass khi còn migrator, migration chưa hoàn chỉnh.

### J. Kế hoạch rollback

Giả lập canary tăng 5xx sau 10 phút nhưng database schema đã thay. Viết rollback plan gồm snapshot/migration expand-contract, binary version, traffic draining và người quyết định. Không hứa rollback bằng `kubectl rollout undo` là đủ nếu schema không tương thích.

## 22. Checklist nâng cấp trước khi merge/deploy

### Baseline và tài liệu

- [ ] Source/target Boot versions và official migration path được ghi rõ.
- [ ] Đã đọc từng migration guide/release notes theo line; không trộn docs Boot 3 và 4.
- [ ] Spring Framework, Security, Data, Cloud, Micrometer và third-party integrations được kiểm tra.
- [ ] Java, Maven/Gradle, Docker/image/JDK, external WAR requirements được ghi.
- [ ] Có artifact checksum, dependencies report và config snapshot sanitized.

### Properties và behavior

- [ ] Scan renamed/removed properties ở repo, CI/CD, deployment manifests và runtime config.
- [ ] Dùng `spring-boot-properties-migrator` **tạm thời** khi phù hợp; sau đó gỡ.
- [ ] Effective values/profiles/precedence đã được xác nhận, không chỉ grep key.
- [ ] HTTP routing/trailing slash/context path được test rõ.
- [ ] HTTP header request/response limits, encoding, compression/upload handling được kiểm tra.
- [ ] JSON serialization/error schemas, 400/404/405/415 được test.
- [ ] Actuator exposure/health/metrics/traces và dashboards còn đúng.
- [ ] Session cookies, CORS, CSRF, redirects và security matchers không nới quyền.
- [ ] Graceful shutdown và background resource cleanup được thử.

### Runtime/server và rollout

- [ ] Java/Jakarta Servlet level đúng target, Tomcat/Jetty/Undertow/Netty support đã được đối chiếu.
- [ ] External WAR nếu có đã deploy trên **đúng container/version**; embedded tests không được thay thế external smoke.
- [ ] Không còn incompatible `javax.servlet.*`/libraries trên Boot3/4.
- [ ] Boot4 modular starters/test API changes đã được xử lý khi target là 4.
- [ ] Unit, MockMvc, RANDOM_PORT và deployed HTTP tests pass với correct profiles.
- [ ] Load/performance/error budgets được so theo cùng workload.
- [ ] Canary/blue-green/rollback thresholds và schema migration strategy đã chốt.
- [ ] Health/readiness kiểm tra đúng app/context; quan sát đầy đủ sau deploy.
- [ ] Không giữ debug/diagnostic Actuator exposure hoặc migrator trong final artifact.

## 23. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Upgrading](https://docs.spring.io/spring-boot/3.5/upgrading.html): migration guides, `spring-boot-properties-migrator` và guidance.
- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): JDK/Framework/Tomcat/Jetty/Undertow/Servlet versions.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Jakarta, `server.max-http-request-header-size`, Redis/Cassandra, trailing slash, Actuator.
- [Spring Boot 3.5 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes): thay đổi tính năng/default của 3.5 như Tomcat APR default.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Servlet6.1, Tomcat11/Jetty12.1, Undertow removed, modular starters, Spring Session property prefixes và test API migrations.
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/4.1/system-requirements.html): tham chiếu phiên bản 4.1 và Servlet/JDK compatibility của target.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): config sources và property precedence.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): exposure và security.
- [Spring Boot 3.5 — MVC Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Servlet runtime, request handling và MVC.
- [Spring Framework — MVC Testing With MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): mock vs actual HTTP tests.
- [Apache Tomcat 10.1 Documentation](https://tomcat.apache.org/tomcat-10.1-doc/): Servlet6.0 container.
- [Apache Tomcat 11 Documentation](https://tomcat.apache.org/tomcat-11.0-doc/): Servlet6.1 container.

**Kết luận:** Một nâng cấp Spring Boot đáng tin cậy phải xác minh **ba điều riêng biệt**: default behavior có còn đúng HTTP/security contract không; renamed/removed properties đã được thay ở mọi config source và thực sự được bind không; Java/Spring/Jakarta/Servlet container có được hỗ trợ trong target line không. Build xanh hoặc `SpringApplication` start thành công chưa đủ: cần unit, MVC, live HTTP, external container/proxy tests, metrics và rollout/rollback có bằng chứng.