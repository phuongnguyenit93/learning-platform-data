# Checklist nâng cấp dựa trên dependency, cấu hình, startup và kiểm thử

Nâng cấp Spring Boot là thay đổi có ảnh hưởng tới nhiều lớp của ứng dụng. Một phiên bản Boot mới có thể kéo theo Spring Framework, Spring Security, Spring Data, Hibernate, Jackson, Micrometer, servlet container và nhiều dependency transitive khác. Đồng thời, Java baseline, cấu hình mặc định, tên property, auto-configuration và API cũng có thể thay đổi.

Vì vậy, một lần nâng cấp không thể được đánh giá chỉ bằng việc sửa version trong build file rồi thấy project compile thành công. Cần xác nhận dependency graph nhất quán, cấu hình còn hợp lệ, application context khởi động đúng, các chức năng quan trọng giữ nguyên behavior và artifact thực tế có thể chạy trong môi trường triển khai.

Trong chương **Phiên bản và mở rộng** của *Spring Boot Fundamentals*, bài học này trình bày checklist nâng cấp theo bốn trục chính:

1. **Dependency:** phiên bản, BOM, release train, scope, transitive dependencies và compatibility.
2. **Cấu hình:** properties, profiles, security, server, persistence, logging và những default thay đổi.
3. **Startup:** component scanning, auto-configuration, bean wiring, migrations, external connections và lifecycle.
4. **Kiểm thử:** compile, unit, context, integration, regression, packaged artifact và smoke tests.

Checklist được tổ chức theo vòng đời công việc: chuẩn bị baseline, lập kế hoạch, cập nhật dependency, điều chỉnh cấu hình/code, xác minh startup, chạy kiểm thử, đóng gói và triển khai có kiểm soát. Có thể dùng nó khi nâng patch/minor release hoặc khi lập kế hoạch chuyển major version; phạm vi kiểm tra cần mở rộng tương ứng với mức thay đổi.

## 1. Nguyên tắc trước khi nâng cấp

Một lần nâng cấp tốt phải trả lời được bốn câu hỏi:

- **Đã thay đổi những gì?** Version nào, dependency nào, property nào, API nào và default nào thay đổi?
- **Ảnh hưởng tới đâu?** Module, service, endpoint, job, database, message consumer hay integration nào bị tác động?
- **Bằng chứng nào xác nhận an toàn?** Build, test, startup log, dependency report, artifact smoke test và metrics nào đã được kiểm tra?
- **Nếu có sự cố thì quay lại thế nào?** Artifact cũ, schema compatibility, configuration và rollout strategy có cho phép rollback không?

Không phải mọi patch upgrade đều cần một migration project lớn. Tuy nhiên, ngay cả khi thay đổi nhỏ, vẫn cần biết chính xác version trước/sau và chạy những kiểm tra tương ứng.

### 1.1. Phân biệt patch, minor và major upgrade

Theo semantic versioning, các thành phần version thường được biểu diễn là:

```text
MAJOR.MINOR.PATCH
```

Đây là cách đọc phổ biến, nhưng cần theo versioning policy cụ thể của Spring Boot và từng dependency:

- **Patch:** thường tập trung bug fixes và security fixes; vẫn cần kiểm tra release notes và regression tests.
- **Minor:** có thể bổ sung feature, thay đổi behavior, cập nhật dependency train hoặc deprecate API.
- **Major:** có thể chứa breaking changes, nâng Java baseline, thay package namespace, loại API cũ và thay đổi cấu hình đáng kể.

Không được suy luận rằng patch upgrade không thể gây tác động. Một dependency transitive, bug fix hoặc thay đổi runtime behavior vẫn có thể ảnh hưởng ứng dụng.

### 1.2. Chọn mục tiêu nâng cấp có lý do

Ghi rõ mục tiêu:

- Vá lỗ hổng bảo mật.
- Nhận bug fix cần thiết.
- Dùng một API/feature mới.
- Đáp ứng Java/runtime baseline mới.
- Thoát khỏi một version đã hết thời gian hỗ trợ.
- Đồng bộ release train của Spring Cloud hoặc thư viện tích hợp.

Mục tiêu giúp xác định phạm vi kiểm thử. Ví dụ, nâng cấp để sửa lỗi serialization cần có regression tests cho payload; nâng cấp do security fix cần thêm security tests; nâng cấp do Java baseline cần xác minh build tool và runtime image.

### 1.3. Không thay nhiều trục cùng lúc nếu không cần

Một PR vừa nâng Spring Boot, vừa đổi Java, thay database, đổi HTTP client và refactor cấu trúc module sẽ rất khó truy nguyên nguyên nhân khi test fail.

Nếu có thể, chia thay đổi thành các bước có thể review:

1. Chuẩn bị và cập nhật baseline.
2. Nâng Spring Boot/dependency train.
3. Sửa API/configuration bị ảnh hưởng.
4. Chuyển Java runtime hoặc platform riêng nếu cần.
5. Triển khai theo rollout plan.

Trong một đợt major upgrade, một số bước có thể buộc phải đi cùng nhau. Khi đó hãy ghi rõ dependency giữa các thay đổi và giữ bằng chứng cho từng nhóm.

## 2. Checklist 0 — Chụp baseline trước khi sửa

Đây là bước tạo điểm so sánh. Nếu không biết trạng thái trước nâng cấp, rất khó xác định lỗi nào mới xuất hiện.

### 2.1. Ghi nhận phiên bản hiện tại

- [ ] Spring Boot version trong build configuration.
- [ ] Spring Framework version thực tế được resolve.
- [ ] Java version dùng để compile.
- [ ] Java runtime version trong môi trường triển khai.
- [ ] Maven/Gradle version và wrapper version.
- [ ] Spring Cloud release train nếu có.
- [ ] Spring Security, Spring Data, Hibernate và các integration quan trọng.
- [ ] Database driver, servlet container và message client.
- [ ] Third-party SDK/API client có ảnh hưởng tới startup hoặc request path.

Không chỉ ghi version trong build file. Xác nhận dependency graph và artifact đang chạy, vì project có thể override BOM hoặc deploy nhầm artifact cũ.

### 2.2. Ghi nhận môi trường hiện tại

- [ ] Active profiles.
- [ ] Environment variables.
- [ ] Config maps/secrets và nguồn cấu hình.
- [ ] JVM options và memory limits.
- [ ] Server port, context path và management port.
- [ ] Database/schema version.
- [ ] Message broker, cache, object storage và external service endpoints.
- [ ] Container base image/JRE version.
- [ ] Deployment image digest hoặc build identifier.

Không ghi secret hoặc credential vào tài liệu checklist. Chỉ ghi tên biến, nguồn cung cấp và cách xác minh an toàn.

### 2.3. Ghi nhận behavior hiện tại

- [ ] Startup time và các bước startup quan trọng.
- [ ] Health/readiness behavior.
- [ ] Endpoint contract và status codes.
- [ ] Authentication/authorization behavior.
- [ ] Serialization format và error response.
- [ ] Database migrations và schema state.
- [ ] Scheduled jobs và message consumers.
- [ ] Logging, metrics, tracing và alert signals.
- [ ] Các tác vụ nền hoặc batch jobs.

Chọn một tập smoke tests đại diện cho những luồng nghiệp vụ quan trọng. Đây sẽ là điểm đối chiếu sau nâng cấp.

### 2.4. Lưu bằng chứng baseline

| Bằng chứng | Mục đích |
| --- | --- |
| Dependency tree/lock state | Biết dependency versions trước nâng cấp |
| Effective POM hoặc Gradle dependency reports | Hiểu version management và resolution |
| Build/test report | Biết trạng thái test trước khi thay đổi |
| Startup log | Có mẫu so sánh bean/configuration warnings |
| OpenAPI/API contract snapshot | So sánh contract HTTP |
| Database migration version | Biết schema đang ở trạng thái nào |
| Artifact checksum/image digest | Xác định đúng artifact đang chạy |
| Runtime metrics baseline | So sánh latency, error rate, resource usage |

Không nhất thiết phải lưu tất cả ở mọi project nhỏ. Hãy giữ những bằng chứng giúp xác định regression trong hệ thống thực tế.

## 3. Checklist 1 — Lập kế hoạch nâng cấp

Trước khi thay version, xác định đích và những dependency liên quan.

### 3.1. Xác định target release

- [ ] Chọn Spring Boot target version cụ thể, không ghi chung “latest”.
- [ ] Xác nhận release đã được phát hành và phù hợp policy hỗ trợ của tổ chức.
- [ ] Đọc release notes từ version hiện tại tới version đích.
- [ ] Đọc migration guide cho các major line đi qua.
- [ ] Xác định Java baseline tối thiểu.
- [ ] Xác định Maven/Gradle wrapper và plugin tương thích.
- [ ] Xác định target Spring Framework version do Boot quản lý.
- [ ] Kiểm tra Spring Cloud compatibility matrix nếu có.

Nếu phải nhảy qua nhiều major release, không bỏ qua migration notes của những major trung gian. Một thay đổi có thể được giới thiệu ở major trước và chỉ bị loại bỏ ở major sau.

### 3.2. Lập danh sách dependency có rủi ro

Ưu tiên:

- Spring Framework modules bị override.
- Spring Security và custom security adapters.
- Spring Data/JPA provider.
- Hibernate extensions và dialects.
- Jackson modules/custom serializers.
- Servlet filters/listeners.
- Micrometer registries/tracing bridges.
- Logging bridges/providers.
- HTTP clients và SDK bên thứ ba.
- Database drivers.
- Message broker clients.
- Libraries dùng javax.* hoặc API cũ.

### 3.3. Phân loại thay đổi

| Nhóm | Ví dụ | Cách xác minh |
| --- | --- | --- |
| Build/runtime baseline | Java hoặc Maven/Gradle version | Build trong CI và chạy bằng runtime target |
| Dependency change | Spring Framework, Hibernate, Jackson | Dependency report, compatibility docs, integration tests |
| API change | Method/annotation bị deprecated hoặc removed | Compile, Javadoc, source migration |
| Configuration change | Property đổi tên/default | Binding/context tests và config review |
| Startup change | Auto-configuration/bean condition | Context startup tests, condition report |
| Behavior change | Serialization, security, transaction | Regression/integration tests |
| Operational change | Health/readiness/logging/metrics | Packaged smoke test và observability checks |

### 3.4. Chọn tiêu chí hoàn thành

Đặt tiêu chí cụ thể trước khi làm:

- Build thành công trên JDK target.
- Dependency graph không có override ngoài ý muốn.
- Các cấu hình quan trọng được bind đúng.
- Application context khởi động với profile được hỗ trợ.
- Unit/integration/regression tests đạt yêu cầu.
- Executable artifact khởi động được.
- Readiness chỉ báo sẵn sàng khi dependency thiết yếu đã sẵn sàng.
- API contract không thay đổi ngoài dự kiến.
- Có phương án rollback tương thích schema và artifact.

## 4. Checklist 2 — Dependency và build system

Dependency là nền tảng của lần nâng cấp. Cần đảm bảo các module thuộc cùng release train và không có version transitive gây binary incompatibility.

### 4.1. Cập nhật Spring Boot ở một nguồn quản lý chính

Maven dùng Boot parent có thể khai báo:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>
```

Hoặc import Boot BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Gradle có thể quản lý Boot plugin/BOM qua plugin, dependency management integration hoặc native platform. Cần theo một cơ chế nhất quán trong project.

- [ ] Chỉ có một target Boot version rõ ràng.
- [ ] Version được định nghĩa tại đúng parent/plugin/catalog/BOM.
- [ ] Không có starter từ các dòng Boot khác nhau.
- [ ] Không có Boot autoconfigure/core module bị pin lệch ngoài ý muốn.
- [ ] Không có nhiều BOM ghi đè nhau mà chưa hiểu resolution.

### 4.2. Rà soát override Spring Framework

Tìm các khai báo trực tiếp như:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-core</artifactId>
    <version>...</version>
</dependency>
```

Một module Spring Framework riêng lẻ được pin version khác release train có thể gây NoSuchMethodError, NoClassDefFoundError hoặc behavior không tương thích.

- [ ] Tìm tất cả version override của org.springframework.
- [ ] Xác minh từng override có lý do và compatibility evidence.
- [ ] Bỏ override không còn cần thiết.
- [ ] Nếu phải override, kiểm tra các module Spring liên quan và chạy integration tests.

### 4.3. Kiểm tra dependency tree Maven

Chạy:

```bash
./mvnw dependency:tree
```

Lọc một dependency:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework
```

Kiểm tra effective POM:

```bash
./mvnw help:effective-pom
```

- [ ] Các module Spring Framework được resolve về version tương thích.
- [ ] Các starter Boot cùng release train.
- [ ] Không có dependency bị exclude nhầm.
- [ ] Scope provided, runtime, test và optional được dùng có chủ đích.
- [ ] Những conflict bị mediation có lý do rõ ràng.
- [ ] Không còn dependency cũ kéo API namespace không tương thích.

### 4.4. Kiểm tra dependency insight Gradle

Xem runtime graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm lý do chọn một module:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

So sánh compile và test runtime khi cần:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

- [ ] Version được chọn là version mong muốn.
- [ ] Selection reason và constraints đã được hiểu.
- [ ] Không có force rule che giấu incompatibility.
- [ ] Dependency locking được cập nhật theo workflow của project.
- [ ] Lock state thay đổi được review.

### 4.5. Rà soát Spring Cloud và các release train khác

Nếu ứng dụng dùng Spring Cloud:

- [ ] Xác định release train tương thích với target Boot.
- [ ] Cập nhật BOM Spring Cloud theo compatibility guidance.
- [ ] Không trộn starter Cloud từ các train khác nhau.
- [ ] Kiểm tra gateway, config client, discovery, circuit breaker và messaging integrations.
- [ ] Chạy integration tests cho các luồng Cloud đang sử dụng.

Với thư viện ngoài hệ sinh thái Spring:

- [ ] Đọc compatibility matrix của vendor.
- [ ] Kiểm tra JDK baseline.
- [ ] Kiểm tra Jakarta support.
- [ ] Kiểm tra các dependency transitives mà SDK yêu cầu.
- [ ] Ưu tiên BOM vendor nếu có.

### 4.6. Rà soát logging và observability dependencies

Logging/metrics dependencies có thể gây lỗi khó nhận biết khi bridge/provider không đồng bộ.

- [ ] Chỉ có logging backend/provider được dự định sử dụng.
- [ ] Không có nhiều SLF4J providers ngoài chủ đích.
- [ ] Logging bridges không tạo vòng lặp.
- [ ] Micrometer registry/tracing bridge tương thích với Boot release.
- [ ] Không trộn nhiều version của Micrometer core/observation.
- [ ] Metrics/tracing exporter khởi động và gửi dữ liệu đúng.

### 4.7. Kiểm tra Java và build tool

- [ ] Cập nhật Maven/Gradle wrapper nếu target release yêu cầu.
- [ ] Cập nhật Maven compiler plugin hoặc Gradle Java toolchain.
- [ ] Xác định source, target hoặc release phù hợp.
- [ ] CI dùng đúng JDK.
- [ ] Container runtime dùng JRE/JDK tương thích.
- [ ] IDE project SDK không che giấu khác biệt với CI.
- [ ] Annotation processors, Lombok, MapStruct và compiler plugins tương thích.

Ví dụ Gradle toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đây chỉ là ví dụ. Chọn Java version theo Spring Boot target và policy của ứng dụng.

## 5. Checklist 3 — API, namespace và source migration

Sau khi dependency graph được cập nhật, compiler sẽ chỉ ra một phần API không còn tương thích.

### 5.1. Tìm API deprecated hoặc removed

- [ ] Đọc compiler warnings.
- [ ] Tìm các API Deprecated.
- [ ] Đọc since và forRemoval.
- [ ] Tìm replacement trong Javadoc/migration guide.
- [ ] Thay API cũ bằng API được khuyến nghị.
- [ ] Kiểm tra semantics của replacement.

Không chỉ thay tên method để làm compiler hết cảnh báo. API mới có thể có behavior khác về null, timeout, exception, lifecycle hoặc security.

### 5.2. Kiểm tra javax sang jakarta

Khi chuyển sang các dòng Spring Boot sử dụng Jakarta EE:

- [ ] Rà soát import javax.servlet.*.
- [ ] Rà soát import javax.persistence.*.
- [ ] Rà soát import javax.validation.*.
- [ ] Kiểm tra servlet filters/listeners và container integration.
- [ ] Kiểm tra JPA provider và persistence extensions.
- [ ] Kiểm tra validation provider và custom validators.
- [ ] Nâng các SDK/plugin chưa hỗ trợ Jakarta.
- [ ] Không thêm cả hai namespace như một cách chữa tổng quát.

javax.* và jakarta.* là những package/type khác nhau. Việc thêm API mới không tự chuyển đổi một thư viện đã compile với namespace cũ.

### 5.3. Rà soát API Spring Framework

- [ ] Kiểm tra các class/method mới mà code bắt đầu sử dụng.
- [ ] Kiểm tra class/method bị loại bỏ.
- [ ] Kiểm tra thay đổi constructor/overload.
- [ ] Kiểm tra generic signatures và method return types nếu có linkage issue.
- [ ] Xác minh class nằm trong artifact đúng.
- [ ] Tránh phụ thuộc vào package internal.

### 5.4. Rà soát API Spring Security

- [ ] Kiểm tra DSL/configuration API theo version.
- [ ] Kiểm tra custom filter và filter ordering.
- [ ] Kiểm tra authentication providers.
- [ ] Kiểm tra method security annotations.
- [ ] Kiểm tra CSRF, CORS và session behavior.
- [ ] Kiểm tra authorization rules theo thứ tự.
- [ ] Viết tests cho anonymous, authenticated, allowed và denied requests.

### 5.5. Rà soát API Spring Data/JPA

- [ ] Kiểm tra repository interfaces và custom implementations.
- [ ] Kiểm tra query derivation và JPQL/native queries.
- [ ] Kiểm tra transaction behavior.
- [ ] Kiểm tra entity mappings và converters.
- [ ] Kiểm tra Hibernate dialect/provider changes.
- [ ] Kiểm tra lazy loading và fetch plans.
- [ ] Kiểm tra pagination/sorting và projections.

### 5.6. Rà soát API serialization và HTTP

- [ ] Kiểm tra Jackson modules và custom serializers/deserializers.
- [ ] Kiểm tra naming, date/time và enum serialization.
- [ ] Kiểm tra request/response DTO compatibility.
- [ ] Kiểm tra exception handler và error payload.
- [ ] Kiểm tra HTTP client timeout/retry behavior.
- [ ] Kiểm tra URI encoding và header handling.

## 6. Checklist 4 — Cấu hình và properties

Ứng dụng có thể compile thành công nhưng hoạt động khác sau nâng cấp vì một property đổi tên, bị deprecated, thay default hoặc không còn được bind.

### 6.1. Rà soát application.properties/application.yml

- [ ] Tìm property deprecated.
- [ ] Tìm property đã đổi tên hoặc chuyển prefix.
- [ ] Tìm property bị loại bỏ.
- [ ] Xác minh default values có thay đổi không.
- [ ] Xác minh type và format của property.
- [ ] Xác minh property có điều kiện theo classpath/profile không.
- [ ] Loại bỏ cấu hình không còn được hỗ trợ.

Không chỉ copy cấu hình từ migration guide. Hãy đối chiếu với cấu hình thực tế của từng profile.

### 6.2. Dùng configuration metadata

Spring Boot configuration metadata có thể mô tả property name, type, description, default value và deprecation. Kiểm tra metadata của dependency version mới khi IDE cảnh báo property.

Metadata hỗ trợ khám phá; reference docs và migration guide vẫn cần thiết để hiểu behavior và điều kiện áp dụng.

### 6.3. Kiểm tra profiles và property precedence

- [ ] Profile mặc định có đúng không?
- [ ] Profile production được active như dự kiến?
- [ ] spring.config.import và config locations còn hợp lệ?
- [ ] Environment variables có map đúng property không?
- [ ] Command-line args có ghi đè cấu hình dự kiến không?
- [ ] Config server/secret manager có trả về key tương thích không?
- [ ] Test profiles có vô tình che lỗi production không?

Ghi lại thứ tự nguồn cấu hình trong môi trường triển khai. Một property đúng trong file YAML vẫn có thể bị environment variable hoặc command-line argument ghi đè.

### 6.4. Kiểm tra server và web configuration

- [ ] Port, context path và servlet context path.
- [ ] Forward headers và reverse proxy settings.
- [ ] Multipart limits và upload behavior.
- [ ] Session/cookie settings.
- [ ] Compression và HTTP/2 settings.
- [ ] Error page/error response configuration.
- [ ] CORS và allowed origins.
- [ ] Static resources và resource handler mappings.
- [ ] Graceful shutdown behavior.

### 6.5. Kiểm tra management/Actuator configuration

- [ ] Management port và base path.
- [ ] Endpoint enablement.
- [ ] HTTP/JMX exposure.
- [ ] Security rules cho management endpoints.
- [ ] Health groups và health contributors.
- [ ] Liveness/readiness behavior.
- [ ] Metrics registry/exporter settings.
- [ ] Info contributors không lộ dữ liệu nhạy cảm.

Không giả định endpoint tồn tại là đã được expose hoặc cho phép truy cập.

### 6.6. Kiểm tra datasource và persistence

- [ ] JDBC URL và driver.
- [ ] Connection pool settings.
- [ ] Pool sizing/timeouts.
- [ ] Transaction manager selection.
- [ ] Hibernate/JPA properties.
- [ ] Naming strategy và dialect.
- [ ] Schema generation policy.
- [ ] Migration tool configuration.
- [ ] Read/write datasource routing nếu có.

### 6.7. Kiểm tra serialization và validation configuration

- [ ] Jackson modules/customizers.
- [ ] Date/time format.
- [ ] Unknown property handling.
- [ ] Enum serialization.
- [ ] Validation provider.
- [ ] Message interpolation.
- [ ] Validation groups.
- [ ] Request validation và error response.

### 6.8. Kiểm tra logging và metrics configuration

- [ ] Logging levels.
- [ ] Logging pattern/structured output.
- [ ] File/appender behavior.
- [ ] Correlation/request IDs.
- [ ] Metrics common tags.
- [ ] Exporter endpoints/credentials.
- [ ] Tracing sampling.
- [ ] Sensitive data redaction.

## 7. Checklist 5 — Startup và auto-configuration

Startup thành công là điều kiện quan trọng, nhưng không phải bằng chứng duy nhất cho thấy mọi chức năng đã hoạt động. Dù vậy, startup tests giúp phát hiện dependency, bean và configuration failures sớm.

### 7.1. Xác minh application context

- [ ] Context khởi động bằng cấu hình production-like.
- [ ] Không có BeanCreationException ngoài dự kiến.
- [ ] Không có UnsatisfiedDependencyException.
- [ ] Không có NoSuchBeanDefinitionException hoặc ambiguity mới.
- [ ] Không có NoClassDefFoundError/NoSuchMethodError.
- [ ] Không có lỗi static initialization.
- [ ] Không có warning quan trọng bị bỏ qua.

### 7.2. Kiểm tra auto-configuration conditions

Spring Boot auto-configuration có thể thay đổi điều kiện theo dependency/classpath/property.

- [ ] Các auto-configuration cần thiết được match.
- [ ] Các auto-configuration không mong muốn được back off.
- [ ] Conditional beans xuất hiện đúng profile.
- [ ] User-defined beans vẫn override/default theo contract.
- [ ] Không có bean trùng hoặc bean mặc định ngoài ý muốn.

Khi startup có kết quả bất ngờ, condition evaluation report có thể giúp xác định điều kiện nào match hoặc không match.

### 7.3. Kiểm tra bean wiring

- [ ] Constructor injection được giải quyết.
- [ ] Qualifier vẫn trỏ đúng bean.
- [ ] Primary vẫn chọn đúng candidate.
- [ ] Collection injection nhận đủ candidates.
- [ ] ConditionalOnMissingBean back off đúng khi user bean tồn tại.
- [ ] Optional dependencies thực sự optional theo thiết kế.
- [ ] Không có circular dependency mới.

Không dùng lazy initialization hoặc field injection để che một dependency bắt buộc bị thiếu. Nếu startup fail fast là yêu cầu, giữ dependency bắt buộc rõ ràng.

### 7.4. Kiểm tra component scanning và imports

- [ ] Base package của SpringBootApplication vẫn bao phủ components cần thiết.
- [ ] Import và ImportAutoConfiguration còn hợp lệ.
- [ ] Configuration classes không bị bỏ khỏi scan.
- [ ] Không vô tình scan test/demo configuration vào production.
- [ ] Các auto-configuration exclusions còn cần thiết và đúng tên.

### 7.5. Kiểm tra startup listeners và lifecycle

- [ ] ApplicationRunner/CommandLineRunner hoạt động đúng.
- [ ] Event listeners nhận đúng event.
- [ ] Scheduled jobs không chạy sớm ngoài ý muốn.
- [ ] Background consumers khởi động sau khi dependencies sẵn sàng.
- [ ] Graceful shutdown giải phóng resources.
- [ ] Startup failure đóng connections/executors đúng cách.

### 7.6. Kiểm tra external dependencies khi startup

- [ ] Database connection và migrations.
- [ ] Message broker connection.
- [ ] Cache connection.
- [ ] Config/discovery server nếu có.
- [ ] External client initialization.
- [ ] TLS certificates/truststores.
- [ ] DNS/service discovery.

Quyết định rõ dependency nào bắt buộc phải sẵn sàng trước readiness và dependency nào có thể kết nối lại sau. Không để ứng dụng báo ready khi một dependency thiết yếu chưa hoạt động.

### 7.7. Xác minh health/readiness

- [ ] Liveness phản ánh khả năng process tiếp tục chạy.
- [ ] Readiness phản ánh khả năng nhận traffic.
- [ ] Health checks không thực hiện công việc quá nặng hoặc gây side effects.
- [ ] Startup probes đủ thời gian cho startup/migration cần thiết.
- [ ] Management endpoint được bảo vệ và expose đúng.

Liveness và readiness có mục đích khác nhau. Không đưa mọi external dependency vào liveness nếu một outage tạm thời sẽ khiến orchestrator restart liên tục.

## 8. Checklist 6 — Kiểm thử sau nâng cấp

Không có một loại test duy nhất chứng minh nâng cấp thành công. Cần chọn nhiều lớp test theo rủi ro.

### 8.1. Compile và static checks

- [ ] Compile main source.
- [ ] Compile test source.
- [ ] Không có API removed chưa xử lý.
- [ ] Warnings mới được xem xét.
- [ ] Annotation processors chạy đúng.
- [ ] Static analysis/lint chạy được.
- [ ] Generated sources được cập nhật đúng.

### 8.2. Unit tests

- [ ] Business rules cốt lõi.
- [ ] Error handling.
- [ ] Validation logic.
- [ ] Mapping/serialization logic.
- [ ] Custom converters/formatters.
- [ ] Utility code phụ thuộc framework APIs.

Unit tests nên tập trung vào logic nhỏ. Không cần khởi động toàn bộ application context cho mỗi test đơn vị.

### 8.3. Context/startup tests

- [ ] Application context loads với profile quan trọng.
- [ ] Bean count/types quan trọng đúng.
- [ ] Auto-configuration conditions đúng.
- [ ] Configuration properties bind đúng.
- [ ] Bean selection/qualifiers đúng.
- [ ] Missing required dependencies làm startup fail theo dự kiến.
- [ ] Không có dependency cycle mới.

### 8.4. Web/API integration tests

- [ ] Endpoint quan trọng trả status code đúng.
- [ ] Request/response schema giữ contract.
- [ ] Error payload giữ contract.
- [ ] Validation errors giữ format.
- [ ] Authentication/authorization behavior đúng.
- [ ] CORS/CSRF behavior đúng.
- [ ] Filters/interceptors hoạt động đúng.
- [ ] Multipart/file upload hoạt động đúng.

### 8.5. Persistence/database tests

- [ ] Database migrations chạy từ schema baseline hỗ trợ.
- [ ] Repository queries chạy đúng.
- [ ] Transaction rollback/commit đúng.
- [ ] Lazy/eager loading behavior được kiểm tra.
- [ ] Pagination/sorting/projection đúng.
- [ ] Locking/concurrency behavior không thay đổi ngoài dự kiến.
- [ ] SQL generated không gây regression đáng kể.

Nếu migration thay đổi schema, test nâng cấp dữ liệu từ schema cũ và kiểm tra tương thích trong giai đoạn rollback.

### 8.6. Messaging và asynchronous tests

- [ ] Producer gửi message đúng format.
- [ ] Consumer deserialize được message cũ/mới theo contract.
- [ ] Retry/backoff behavior.
- [ ] Dead-letter handling.
- [ ] Acknowledgement semantics.
- [ ] Ordering/idempotency.
- [ ] Scheduled tasks và async executors.

### 8.7. Security tests

- [ ] Anonymous requests bị chặn/cho phép đúng.
- [ ] Authenticated requests hoạt động.
- [ ] Role/authority mapping đúng.
- [ ] Method security vẫn hoạt động.
- [ ] CSRF/CORS policy đúng.
- [ ] OAuth2/JWT/resource server integrations.
- [ ] Password encoder/provider compatibility.
- [ ] Management endpoints không bị lộ.

### 8.8. Regression tests cho behavior defaults

Tập trung vào behavior có thể thay đổi dù code không đổi:

- Jackson serialization defaults.
- Spring MVC content negotiation.
- Validation exception mapping.
- Transaction boundaries.
- Hibernate SQL/dialect.
- Security defaults.
- HTTP client timeout/retry.
- Logging format.
- Metrics naming/tags.

### 8.9. Test thực thi trên artifact đóng gói

Đây là bước dễ bị bỏ qua:

- [ ] Build executable JAR/image.
- [ ] Xác nhận đúng artifact version/build ID.
- [ ] Chạy java -jar hoặc container image như production.
- [ ] Kiểm tra dependency runtime được đóng gói.
- [ ] Xác nhận classpath không thiếu/duplicate dependency.
- [ ] Thực hiện smoke tests trên artifact đó.

Test chạy trong IDE hoặc test runtime không thay thế smoke test của executable artifact.

## 9. Checklist 7 — Đóng gói và triển khai

Sau khi tests đạt, cần xác nhận cách ứng dụng được đóng gói và vận hành.

### 9.1. Artifact

- [ ] Artifact được build từ commit đã review.
- [ ] Build version/commit ID được ghi nhận.
- [ ] Checksum hoặc image digest được lưu.
- [ ] Runtime dependencies có trong artifact/image.
- [ ] Không có JAR cũ được copy thủ công.
- [ ] Base image dùng JRE/JDK tương thích.
- [ ] Entrypoint/JVM args đúng.

### 9.2. Container và orchestration

- [ ] Container user/permissions phù hợp.
- [ ] Memory/CPU limits phù hợp.
- [ ] JVM container awareness được xác nhận.
- [ ] Health/readiness/startup probes đúng.
- [ ] Graceful shutdown timeout phù hợp.
- [ ] Environment variables và secrets được cung cấp.
- [ ] Image digest thực tế được deploy.
- [ ] Không dựa vào mutable tag mà không xác minh digest.

### 9.3. Database migration strategy

- [ ] Backup/restore strategy được xác nhận.
- [ ] Migration scripts được review.
- [ ] Migration chạy trên bản sao dữ liệu phù hợp.
- [ ] Migration duration và lock impact được ước lượng.
- [ ] Schema changes tương thích với phiên bản ứng dụng cũ trong thời gian rollout nếu cần.
- [ ] Rollback/forward-fix strategy rõ ràng.

Không giả định có thể rollback code nếu schema migration đã xóa hoặc đổi dữ liệu theo cách ứng dụng cũ không đọc được.

### 9.4. Rollout strategy

Tùy kiến trúc có thể chọn rolling update, canary deployment, blue/green deployment hoặc staged rollout theo nhóm instance.

Trước rollout:

- [ ] Xác định health gate.
- [ ] Xác định traffic/error thresholds.
- [ ] Xác định thời gian quan sát.
- [ ] Xác định người chịu trách nhiệm.
- [ ] Chuẩn bị artifact cũ và configuration rollback.

### 9.5. Quan sát sau deploy

- [ ] Startup success rate.
- [ ] Readiness transition.
- [ ] HTTP 5xx/error rate.
- [ ] Latency p50/p95/p99.
- [ ] JVM memory/GC.
- [ ] CPU/thread count.
- [ ] Database pool saturation.
- [ ] Message lag/retry/dead letters.
- [ ] Logs có lỗi linkage/configuration mới không.
- [ ] Metrics/traces được gửi đầy đủ.

So sánh với baseline trước nâng cấp. Một ứng dụng “đang chạy” nhưng latency tăng mạnh hoặc consumer lag tăng liên tục vẫn có thể là một lần nâng cấp không đạt.

## 10. Checklist 8 — Rollback và forward recovery

Rollback phải được nghĩ tới trước khi deploy, nhất là khi có database/schema changes.

### 10.1. Chuẩn bị rollback

- [ ] Giữ artifact/image cũ.
- [ ] Lưu configuration cũ.
- [ ] Xác định cách khôi phục image digest.
- [ ] Xác định schema có tương thích với app cũ không.
- [ ] Kiểm tra message format backward/forward compatibility.
- [ ] Xác định migration nào không thể rollback.
- [ ] Có backup/restore plan nếu cần.

### 10.2. Expand-and-contract cho database

Khi schema thay đổi có nguy cơ làm ứng dụng cũ không tương thích, có thể dùng chiến lược:

1. **Expand:** thêm cột/table/index mới mà code cũ vẫn có thể chạy.
2. Deploy code mới đọc/ghi theo cách tương thích.
3. Migrate/backfill dữ liệu.
4. **Contract:** chỉ xóa cấu trúc cũ sau khi không còn code cũ sử dụng và rollback window đã kết thúc.

Đây là mô hình tổng quát; cách áp dụng tùy database và migration tool.

### 10.3. Khi rollback không an toàn

Nếu migration đã xóa/biến đổi dữ liệu, rollback application binary có thể làm hệ thống hỏng thêm. Khi đó cần forward fix hoặc restore dữ liệu theo kế hoạch đã xác định.

### 10.4. Kiểm tra rollback thực tế

Trong môi trường staging:

- [ ] Triển khai target version.
- [ ] Chạy smoke tests.
- [ ] Rollback về artifact trước.
- [ ] Xác nhận app cũ vẫn đọc schema/message state.
- [ ] Kiểm tra readiness và business flows.

Rollback plan chưa được thử chỉ là giả định.

## 11. Checklist riêng cho patch/minor upgrade

Patch/minor upgrade thường có phạm vi nhỏ hơn major upgrade, nhưng vẫn cần:

- [ ] Đọc release notes.
- [ ] Xem security advisories/bug fixes liên quan.
- [ ] Xác nhận Java/build baseline không đổi ngoài dự kiến.
- [ ] Kiểm tra dependency tree diff.
- [ ] Xem property/default changes nếu có.
- [ ] Compile và chạy unit tests.
- [ ] Chạy context/startup tests.
- [ ] Chạy regression/integration tests của các luồng bị ảnh hưởng.
- [ ] Build và chạy packaged artifact.
- [ ] Quan sát metrics/logs sau deploy.

Nếu patch release sửa một bug mà ứng dụng đang dựa vào behavior cũ, regression test cần thể hiện behavior mong muốn sau khi fix.

## 12. Checklist riêng cho major upgrade

Major upgrade cần đánh giá sâu hơn:

### 12.1. Platform

- [ ] Java minimum version.
- [ ] Maven/Gradle version.
- [ ] Servlet/Jakarta platform.
- [ ] Container/JRE image.
- [ ] Build plugins và annotation processors.

### 12.2. Dependency train

- [ ] Spring Framework line.
- [ ] Spring Cloud train.
- [ ] Spring Security.
- [ ] Spring Data/JPA/Hibernate.
- [ ] Jackson and serialization modules.
- [ ] Micrometer/observability.
- [ ] Third-party SDK compatibility.

### 12.3. Source migration

- [ ] Removed APIs.
- [ ] Deprecated APIs.
- [ ] Package namespace changes.
- [ ] Annotation behavior changes.
- [ ] Security DSL changes.
- [ ] Persistence API changes.

### 12.4. Configuration migration

- [ ] Renamed/removed properties.
- [ ] Changed defaults.
- [ ] Auto-configuration changes.
- [ ] Management endpoints/exposure.
- [ ] Logging/metrics configuration.
- [ ] Profiles and external configuration.

### 12.5. Runtime behavior

- [ ] Startup and bean graph.
- [ ] Database schema and SQL behavior.
- [ ] HTTP/API behavior.
- [ ] Security policies.
- [ ] Messaging.
- [ ] Shutdown/lifecycle.
- [ ] Performance/resource usage.

### 12.6. Deployment

- [ ] Staging rollout.
- [ ] Rollback rehearsal.
- [ ] Observability dashboards.
- [ ] On-call/runbook updates.
- [ ] Production rollout gates.

## 13. Ma trận kiểm thử theo rủi ro

Không phải mọi project đều cần chạy mọi test trong mọi lần nâng cấp. Dùng ma trận này để chọn phạm vi theo những phần đã thay đổi.

| Thay đổi | Kiểm tra tối thiểu cần cân nhắc |
| --- | --- |
| Chỉ patch Boot | Dependency diff, build, unit/context tests, packaged smoke test |
| Spring Framework API | Compile, API tests, context startup, web/integration tests |
| Spring Security | Security configuration tests, authorization regression, CSRF/CORS |
| Spring Data/Hibernate | Repository integration, transactions, SQL/schema/migrations |
| Jackson | Serialization contract tests và backward compatibility payloads |
| Java baseline | Toolchain/CI/container build, runtime smoke, native/reflective integrations |
| Jakarta migration | Compile, servlet/JPA/validation integrations, third-party SDK checks |
| Actuator/Micrometer | Endpoint security/exposure, health/readiness, metrics/tracing export |
| Database driver | Connection, transaction, prepared statements, failover/timeouts |
| Messaging client | Producer/consumer, retries, acknowledgements, serialization |
| Major upgrade | Critical flows, migration tests, packaged artifact, rollout/rollback |

Hãy ưu tiên test các code paths chịu ảnh hưởng trực tiếp và những luồng nghiệp vụ có hậu quả lớn nếu thay đổi.

## 14. Cách đọc dependency diff sau nâng cấp

Sau khi cập nhật Boot version, không nên chỉ xem một dòng version mới trong POM. So sánh dependency graph trước/sau.

### 14.1. Những câu hỏi cần trả lời

- Dependency nào được thêm?
- Dependency nào bị loại?
- Artifact nào đổi major/minor version?
- Có dependency nào được nâng ngoài ý muốn?
- Có version override nào không còn cần?
- Có module nào bị resolve từ BOM khác?
- Compile/runtime/test classpaths có khác biệt bất ngờ?

### 14.2. Maven

Chạy dependency tree ở branch trước và sau nâng cấp, lưu output và so sánh. Với các artifact quan trọng, lọc theo group/artifact để hiểu đường kéo vào.

```bash
./mvnw dependency:tree -Dverbose
```

### 14.3. Gradle

Lưu dependency reports và dùng dependencyInsight cho các module quan trọng. Nếu dùng lockfiles, review diff lock state cùng build configuration.

### 14.4. Dependency convergence

Có thể dùng Maven Enforcer dependency convergence hoặc Gradle constraints/locking để phát hiện version drift. Những công cụ này giúp tìm conflict, nhưng không chứng minh mọi version đã tương thích binary/behavioral.

## 15. Cách kiểm tra configuration diff

Một cách thực tế là lập bảng cho từng property quan trọng:

| Property | Giá trị trước | Giá trị sau | Nguồn | Đã xác minh |
| --- | --- | --- | --- | --- |
| server.port | ... | ... | Environment | [ ] |
| spring.datasource.* | ... | ... | Secret/config store | [ ] |
| spring.jpa.* | ... | ... | Profile config | [ ] |
| management.* | ... | ... | Deployment config | [ ] |
| logging.* | ... | ... | Profile config | [ ] |

Không đưa secret values vào bảng. Có thể ghi tên secret key, source và kết quả kiểm tra đã thành công.

### 15.1. Kiểm tra property bị bỏ qua

Property không còn được bind có thể không gây startup failure. Để phát hiện:

- Kiểm tra configuration metadata.
- Đọc migration guide.
- Xác nhận ConfigurationProperties binding.
- Bật validation cho cấu hình bắt buộc.
- Assert giá trị trong context tests.
- Kiểm tra behavior thực tế.

### 15.2. Kiểm tra default behavior

Nếu một default thay đổi, quyết định:

- Chấp nhận default mới.
- Khai báo tường minh giá trị cũ.
- Điều chỉnh code để dùng behavior mới.

Không nên khai báo lại mọi default một cách máy móc; chỉ pin những giá trị là contract vận hành của ứng dụng.

## 16. Cách xác minh startup có ý nghĩa

Một log có dòng Started ... là bằng chứng hữu ích, nhưng chưa chứng minh mọi dependency hoặc code path đều hoạt động.

### 16.1. Startup gate

Startup test nên xác nhận:

- Context không có startup failure.
- Bean quan trọng tồn tại.
- Required properties được bind.
- Auto-configuration match.
- Database/messaging dependencies đạt trạng thái yêu cầu.
- Readiness chuyển trạng thái đúng.

### 16.2. Tránh chỉ kiểm tra process sống

Process còn sống không có nghĩa application ready. Một app có thể chạy nhưng không kết nối database, không consume message hoặc không expose endpoint đúng.

### 16.3. Không làm health check gây side effects

Health checks nên có chi phí thấp, timeout rõ và không tạo dữ liệu hoặc thực hiện business operation. Với dependency tạm thời không sẵn sàng, readiness thường phù hợp hơn liveness.

### 16.4. Kiểm tra startup trong profile thực tế

Một context test chỉ dùng profile test có thể không phát hiện lỗi trong prod. Hãy có cách kiểm tra cấu hình production-like mà không đưa secrets production vào CI.

## 17. Kiểm thử hợp đồng API sau nâng cấp

Nếu ứng dụng cung cấp REST API, nâng framework có thể ảnh hưởng cách serialize, validate, route hoặc xử lý lỗi.

### 17.1. Contract tests

- [ ] HTTP methods và paths.
- [ ] Request/response schema.
- [ ] Required/optional fields.
- [ ] Status codes.
- [ ] Error payloads.
- [ ] Headers/content types.
- [ ] Pagination/filtering/sorting.
- [ ] Date/time formats.

### 17.2. Backward compatibility

Nếu có client cũ, kiểm tra:

- Field mới có optional/default phù hợp không?
- Field cũ có bị rename/remove không?
- Enum mới có làm client cũ fail không?
- Date/time format có đổi không?
- Error response có thay đổi không?
- Authentication/session behavior có đổi không?

### 17.3. OpenAPI snapshots

Có thể so sánh OpenAPI document trước/sau. Một diff không phải lúc nào cũng là breaking change, nhưng mọi thay đổi cần được giải thích.

## 18. Kiểm thử database và migration

Nâng Spring Boot có thể nâng Hibernate, Spring Data hoặc JDBC driver. Điều đó có thể thay đổi SQL generation, dialect selection, transaction behavior hoặc schema handling.

### 18.1. Schema migration

- [ ] Chạy migrations từ schema version cũ.
- [ ] Xác nhận thứ tự migrations.
- [ ] Kiểm tra dữ liệu sau migration.
- [ ] Kiểm tra indexes/constraints.
- [ ] Đo thời gian và lock impact.
- [ ] Xác minh ứng dụng cũ có thể coexist trong rollout nếu cần.

### 18.2. ORM behavior

- [ ] Entity mappings.
- [ ] Lazy proxies.
- [ ] Cascade/orphan removal.
- [ ] Fetch joins/entity graphs.
- [ ] JPQL/native query results.
- [ ] Generated identifiers.
- [ ] Optimistic/pessimistic locking.
- [ ] Transaction rollback.

### 18.3. Kiểm tra SQL

Với query quan trọng, có thể ghi nhận SQL trước/sau trong test hoặc staging. Đặc biệt chú ý query plan, N+1 behavior và thay đổi dialect.

### 18.4. Không dùng schema auto-update làm migration plan

Cấu hình ddl-auto=update không thay thế một migration strategy có review. Trong production, schema changes cần được quản lý rõ ràng bằng công cụ migration và quy trình rollback/forward fix.

## 19. Kiểm thử messaging và integration

Framework/dependency upgrades có thể tác động client libraries, serializers, retry behavior và lifecycle.

- [ ] Producer message schema.
- [ ] Consumer deserialization.
- [ ] Compatibility với message đã lưu trong broker.
- [ ] Retry và backoff.
- [ ] Dead-letter queues.
- [ ] Acknowledgement/offset commit.
- [ ] Ordering và partition behavior.
- [ ] Idempotency.
- [ ] Shutdown và rebalance.
- [ ] Connection recovery.

Nếu message format được chia sẻ giữa nhiều service, cần test producer mới với consumer cũ và ngược lại trong phạm vi compatibility được yêu cầu.

## 20. Kiểm tra hiệu năng và tài nguyên

Một upgrade có thể thay đổi startup time, memory, GC, thread usage hoặc query performance.

### 20.1. So sánh cùng điều kiện

- [ ] Cùng dataset.
- [ ] Cùng resource limits.
- [ ] Cùng workload.
- [ ] Cùng JVM flags.
- [ ] Cùng external dependency conditions.
- [ ] Cùng warm-up period.

### 20.2. Chỉ số cần quan sát

- Startup duration.
- Heap/non-heap usage.
- GC frequency/pause.
- CPU utilization.
- Thread count.
- Request throughput.
- p95/p99 latency.
- Database connection pool.
- Queue/consumer lag.
- Error and retry rates.

### 20.3. Không kết luận từ một lần chạy

Đo performance trong điều kiện lặp lại và so sánh baseline. Một lần benchmark không kiểm soát có thể phản ánh cache, network hoặc tải nền chứ không phải khác biệt framework.

## 21. Ví dụ quy trình nâng cấp một service

Giả sử catalog-service đang dùng một Spring Boot release cũ và team muốn chuyển sang release mới để nhận security fixes và một API web client.

### Giai đoạn A — Baseline

1. Ghi Boot/Framework/Java versions.
2. Lưu dependency tree.
3. Lưu config profiles.
4. Chạy test suite hiện tại.
5. Lưu startup logs, API contract và metrics baseline.

### Giai đoạn B — Dependency plan

1. Chọn Boot target version.
2. Xác nhận Java baseline.
3. Đọc release notes/migration guide.
4. Kiểm tra Spring Cloud/vendor compatibility.
5. Cập nhật parent/plugin/BOM.
6. Loại bỏ version overrides không cần thiết.
7. So sánh dependency graph.

### Giai đoạn C — Source/config migration

1. Compile source và xử lý removed/deprecated APIs.
2. Rà soát javax/jakarta nếu major line yêu cầu.
3. Cập nhật properties đã đổi tên.
4. Xác nhận default values.
5. Sửa security/web/data configuration nếu cần.

### Giai đoạn D — Startup

1. Chạy context test.
2. Kiểm tra bean graph/auto-configuration.
3. Khởi động với profile production-like.
4. Xác nhận database/messaging connectivity.
5. Xác nhận readiness và Actuator security.

### Giai đoạn E — Tests

1. Unit tests.
2. Web/API contract tests.
3. Persistence/migration tests.
4. Security tests.
5. Messaging/integration tests.
6. Regression tests cho feature bị ảnh hưởng.

### Giai đoạn F — Artifact và rollout

1. Build executable JAR/image.
2. Xác minh dependency packaging.
3. Chạy smoke tests trên artifact.
4. Deploy staging.
5. Kiểm tra metrics/logs.
6. Thử rollback.
7. Canary/rolling production rollout theo gate.

## 22. Checklist review Pull Request nâng cấp

Reviewer có thể dùng các câu hỏi sau:

### Dependency

- [ ] Boot version được đổi ở đúng nguồn quản lý.
- [ ] BOM/parent/plugin nhất quán.
- [ ] Không có module Spring bị pin lệch vô cớ.
- [ ] Dependency transitive và exclusions đã được xem.
- [ ] Spring Cloud/vendor compatibility đã được xác nhận.
- [ ] Java/build tool versions phù hợp.

### Configuration

- [ ] Migration notes đã được xem.
- [ ] Properties deprecated/removed đã được xử lý.
- [ ] Defaults quan trọng đã được xác minh.
- [ ] Profiles và environment overrides đã được xem.
- [ ] Security/management exposure không bị nới ngoài ý muốn.

### Startup

- [ ] Context startup test đạt.
- [ ] Auto-configuration/bean conditions đúng.
- [ ] External dependencies và migrations được kiểm tra.
- [ ] Readiness/liveness phù hợp.
- [ ] Không có linkage/circular dependency errors.

### Testing

- [ ] Compile/unit tests đạt.
- [ ] Context/integration tests đạt.
- [ ] API/security/data/messaging regression tests phù hợp.
- [ ] Packaged artifact smoke test đạt.
- [ ] Dependency graph diff đã được review.

### Operations

- [ ] Artifact/image có build identifier.
- [ ] Rollout/rollback plan rõ.
- [ ] Schema compatibility được đánh giá.
- [ ] Dashboards/alerts/runbooks được cập nhật khi cần.

## 23. Mẫu checklist có thể sao chép cho một đợt nâng cấp

Mẫu dưới đây dùng để ghi nhận trạng thái công việc. Có thể bỏ mục không áp dụng, nhưng nên ghi lý do cho các mục rủi ro cao được đánh dấu N/A.

```markdown
# Spring Boot Upgrade Record

## Target
- Current Spring Boot:
- Target Spring Boot:
- Current Java:
- Target Java:
- Build tool:
- Upgrade reason:
- Target release notes:
- Migration guide:

## Baseline
- [ ] Dependency graph saved
- [ ] Effective POM / Gradle reports saved
- [ ] Active profiles recorded
- [ ] Runtime artifact/build ID recorded
- [ ] Existing tests and smoke tests pass
- [ ] API/configuration/metrics baseline saved

## Dependencies
- [ ] Boot parent/plugin/BOM updated
- [ ] Spring Framework modules aligned
- [ ] Spring Cloud compatibility confirmed
- [ ] Third-party SDK compatibility confirmed
- [ ] Transitive conflicts reviewed
- [ ] Exclusions and scopes reviewed
- [ ] Java/build tool/annotation processors compatible

## Source and configuration
- [ ] Deprecated/removed APIs handled
- [ ] javax/jakarta compatibility confirmed
- [ ] Properties and defaults reviewed
- [ ] Profiles and external config reviewed
- [ ] Security/web/data/Actuator configuration reviewed

## Startup
- [ ] Context starts in required profiles
- [ ] Auto-configuration conditions reviewed
- [ ] Required beans and dependencies available
- [ ] Database migrations/connectivity verified
- [ ] Messaging/external integrations verified
- [ ] Readiness/liveness verified

## Tests
- [ ] Compile and static checks pass
- [ ] Unit tests pass
- [ ] Context tests pass
- [ ] API/contract tests pass
- [ ] Security tests pass
- [ ] Persistence/migration tests pass
- [ ] Messaging/integration tests pass
- [ ] Packaged artifact smoke test passes

## Deployment
- [ ] Artifact/image digest recorded
- [ ] Staging rollout verified
- [ ] Performance/metrics compared
- [ ] Rollback plan reviewed/tested
- [ ] Production rollout gates defined

## Decision
- Known limitations:
- Accepted risks:
- Rollback trigger:
- Owner:
- Review date:
- Final decision:
```

## 24. Khi nào có thể đánh dấu nâng cấp hoàn tất?

Không nên đánh dấu hoàn tất chỉ vì build xanh. Một lần nâng cấp có thể được xem là sẵn sàng khi:

1. **Dependency set đã được hiểu và quản lý:** target version rõ, không có override/conflict ngoài dự kiến.
2. **Cấu hình được xác minh:** properties quan trọng bind đúng, profile/environment được kiểm tra và default changes được chấp nhận.
3. **Startup ổn định:** context tạo đúng bean, auto-configuration match và required dependencies sẵn sàng.
4. **Tests đại diện đạt:** các business flows và integration chịu ảnh hưởng đã được chạy.
5. **Artifact thực tế chạy được:** packaged JAR/image được xác minh, không chỉ chạy từ IDE.
6. **Vận hành có thể quan sát:** health, logs, metrics và alerts đủ để phát hiện regression.
7. **Rollback/recovery có kế hoạch:** artifact, schema và configuration có hướng xử lý khi rollout gặp lỗi.

Với thay đổi rủi ro cao, cần staging/canary evidence trước khi mở rộng rollout. Với patch nhỏ, có thể dùng phạm vi kiểm tra gọn hơn nếu dependency diff và impact analysis chứng minh được.

## 25. Những sai lầm thường gặp khi nâng cấp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đổi Boot version rồi deploy | Bỏ sót dependency/config/API changes | Dùng checklist theo từng lớp |
| Dùng tài liệu latest cho project cũ | Gọi API chưa có hoặc cấu hình sai | Chọn docs/Javadoc đúng release |
| Pin riêng một module Spring | Version skew và linkage errors | Ưu tiên Boot BOM/release train |
| Bỏ qua dependency transitive | Runtime nạp version không tương thích | Dependency tree/insight và compatibility docs |
| Chỉ chạy unit tests | Không phát hiện context/auto-config failures | Thêm context và integration tests |
| Chỉ test profile dev | Production config có thể lỗi | Test production-like profile an toàn |
| Chỉ kiểm tra dòng Started | Bean/endpoint/code path lazy có thể chưa hoạt động | Smoke tests và readiness checks |
| Không kiểm tra executable JAR | Runtime packaging có thể thiếu dependency | Chạy đúng artifact/image |
| Bỏ qua property defaults | Behavior thay đổi dù source không đổi | Đối chiếu metadata/migration guide |
| Chỉ thêm dependency để hết NoClassDefFoundError | Tạo thêm conflict hoặc duplicate class | Xác định artifact sở hữu class trước |
| Catch LinkageError để app tiếp tục | Che giấu lỗi triển khai nghiêm trọng | Sửa classpath/version/initialization |
| Rollback code nhưng không xét schema | App cũ không tương thích database mới | Expand-and-contract và rollback rehearsal |
| Không so sánh metrics | Performance regression bị bỏ qua | So sánh cùng workload/baseline |

## 26. Tổng kết

Checklist nâng cấp Spring Boot cần bao phủ **dependency, cấu hình, startup, kiểm thử và triển khai**. Mỗi lớp trả lời một câu hỏi khác nhau: dependency có tương thích không, ứng dụng có nhận đúng cấu hình không, container có khởi động đúng không, behavior có được bảo vệ bởi tests không và artifact thực tế có vận hành ổn định không.

Hãy giữ các nguyên tắc:

- Chụp baseline trước khi thay đổi.
- Chọn target release và đọc release notes/migration guide.
- Quản lý Spring modules bằng Boot BOM/release train phù hợp.
- Kiểm tra dependency graph, scopes, exclusions và third-party compatibility.
- Xác minh Java/build tool/runtime baseline.
- Rà soát API, namespace, properties và default behavior.
- Kiểm tra auto-configuration, bean wiring, external dependencies và readiness.
- Chạy unit, context, integration, regression và packaged artifact tests theo rủi ro.
- Chuẩn bị rollout, observability và rollback trước khi deploy.

Một lần nâng cấp chỉ có cơ sở để hoàn tất khi **dependency graph được kiểm soát, cấu hình được xác nhận, startup đạt yêu cầu, tests bảo vệ behavior và artifact đã đóng gói được kiểm chứng trong môi trường gần production**. Checklist này giúp biến việc nâng version thành một thay đổi có bằng chứng, có thể review và có thể phục hồi khi cần.
