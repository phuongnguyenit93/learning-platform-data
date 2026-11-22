# Kiểm thử native image, AOT và reflection khi có yêu cầu triển khai

Khi triển khai Spring Data JPA dưới dạng GraalVM Native Image, các bài test chạy trên JVM thông thường chưa đủ để chứng minh ứng dụng hoạt động đúng. Native Image phân tích code có thể truy cập tại build time; những lời gọi reflection, tài nguyên classpath, proxy hoặc service được nạp động có thể cần metadata bổ sung. Spring AOT tạo sẵn một phần mã khởi tạo và runtime hints, nhưng không tự bảo đảm mọi thư viện bên thứ ba, Hibernate extension hay JDBC driver đều tương thích với native runtime.

Một quy trình kiểm thử đáng tin cậy nên có ba lớp: kiểm thử chức năng và tích hợp trên JVM với database mục tiêu, chạy ứng dụng bằng mã Spring AOT trên JVM, rồi build và smoke-test executable/container native thực tế. Chỉ bật native image khi yêu cầu triển khai có lợi ích rõ ràng về thời gian khởi động, footprint hoặc mô hình phân phối; nếu ứng dụng chạy JVM bình thường, không cần thêm độ phức tạp AOT/native chỉ để chạy theo xu hướng.

> Các đoạn Java dưới đây là snippet dành cho dự án Java 17+ dùng Spring Boot 3+ và `spring-boot-starter-data-jpa`. Chúng minh họa cấu hình và test cần tích hợp vào dự án, không phải chương trình độc lập có thể chạy trực tiếp bằng `javac`/`java`.

## 1. Phân biệt JVM, AOT và Native Image

Ba chế độ này có liên quan nhưng kiểm tra những rủi ro khác nhau:

| Chế độ | Cách chạy | Điều có thể phát hiện |
|---|---|---|
| JVM thông thường | Bytecode chạy trên JVM, Spring dựng ApplicationContext lúc runtime | Logic nghiệp vụ, mapping JPA, query, transaction và tương tác database |
| JVM với Spring AOT | Chạy JAR có mã AOT sinh sẵn và bật `spring.aot.enabled=true` | Lỗi trong mã khởi tạo Spring đã sinh, điều kiện bean được chốt ở build time và một số thiếu sót của AOT |
| GraalVM Native Image | Mã ứng dụng và phần thư viện có thể truy cập được biên dịch thành executable native | Các vấn đề reachability, reflection, resource, proxy, service loading, native runtime và môi trường hệ điều hành mục tiêu |

Spring AOT phân tích ApplicationContext ở build time, sinh mã khởi tạo và runtime hints. Khi chạy native image, Spring sử dụng phần khởi tạo đã được tạo. GraalVM tiếp tục phân tích reachability để xác định phần code nào được đưa vào executable.

Vì vậy, chạy JAR trên JVM với `spring.aot.enabled=true` là bước kiểm tra hữu ích nhưng không tương đương chạy executable native. Một ứng dụng có thể vượt qua JVM AOT nhưng vẫn lỗi trong native image vì thiếu metadata reflection hoặc thư viện không hỗ trợ native runtime.

AOT còn có giới hạn quan trọng: classpath và cấu hình ảnh hưởng đến bean graph được xác định ở build time. `@Profile`, các điều kiện `@Conditional` và property quyết định việc tạo bean cần được cung cấp đúng lúc build. Không thể giả định thay đổi profile hoặc thêm plugin JAR sau khi build sẽ làm native image tự phát hiện bean mới.

## 2. Chốt ma trận phiên bản và nền tảng mục tiêu

Trước khi viết test, ghi lại chính xác các thành phần sẽ được triển khai:

| Thành phần | Thông tin cần cố định |
|---|---|
| JDK | Phiên bản Java dùng để compile và target bytecode |
| Spring Boot | Phiên bản và dependency management |
| Spring Framework / Spring Data JPA | Phiên bản thực tế được Boot quản lý |
| Hibernate ORM | Phiên bản `hibernate-core` và các module mở rộng |
| GraalVM | Distribution, version và Native Image toolchain |
| Native Build Tools | Plugin Maven/Gradle và version |
| Hệ điều hành / kiến trúc | Linux, Windows, macOS; x86_64 hoặc ARM64 |
| libc / container base | glibc hoặc musl và image nền |
| JDBC driver | Artifact và version chính xác |
| Database | Hệ quản trị, major/minor version, extension và cấu hình |

Không nâng riêng `hibernate-core` ra khỏi dependency management của Spring Boot nếu chưa xác minh tương thích với Spring Data JPA, Jakarta Persistence, bytecode enhancement và các module Hibernate khác. Các module như Envers, Spatial, custom dialect, cache provider hoặc thư viện mở rộng có thể có giới hạn native khác nhau.

Với Hibernate ORM, cần kiểm tra tài liệu của đúng release. Tài liệu Hibernate hiện mô tả `hibernate-graalvm` là extension thử nghiệm hỗ trợ biên dịch GraalVM Native Image; điều đó không đồng nghĩa mọi cấu hình Spring Data JPA + Hibernate đều được bảo đảm native-ready. Hãy thử đúng phiên bản Hibernate, dialect, driver và extension đang dùng trong ứng dụng. Nếu native image là yêu cầu production bắt buộc, cần có bằng chứng kiểm thử cho toàn bộ stack mục tiêu trước khi chốt kiến trúc.

Không dùng `latest` hoặc tag image trôi nổi trong pipeline kiểm thử. Cố định version của database image và toolchain để lỗi có thể tái hiện. Nếu hỗ trợ nhiều tổ hợp phiên bản, tạo ma trận CI cho các tổ hợp tối thiểu và tối đa được cam kết hỗ trợ, thay vì chỉ kiểm tra một máy developer.

## 3. Xây dựng bộ test JVM với database thật

Phần lớn unit test và integration test vẫn nên chạy trên JVM để có vòng lặp phát triển nhanh. Tuy nhiên, test JPA cần dùng database cùng loại với môi trường triển khai nếu có hành vi phụ thuộc dialect, kiểu dữ liệu, sequence/identity, locking, JSON, stored procedure hoặc SQL riêng của vendor.

Testcontainers có thể dựng database thật trong Docker. Với Spring Boot 3.1+, có thể dùng `@ServiceConnection` để Spring Boot tự cấu hình connection từ container:

**Test database configuration:**

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class TargetDatabaseConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        // Chọn đúng major/minor gần với database triển khai.
        return new PostgreSQLContainer<>("postgres:16.4-alpine");
    }
}
```

Các dependency test cần thiết, với version được quản lý bởi Spring Boot BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Với Spring Boot cũ hơn 3.1, có thể dùng `@DynamicPropertySource` để đăng ký JDBC URL, username và password từ container. Tag database trong ví dụ chỉ minh họa; hãy thay bằng phiên bản database thật sự được hỗ trợ và pin chính xác trong CI.

Chạy migration production trên database test. Nếu production dùng Flyway hoặc Liquibase, không chỉ tạo schema bằng `hibernate.ddl-auto=create`. Migration mới là nguồn xác nhận schema, index, constraint, sequence, default và kiểu dữ liệu tương ứng với phiên bản ứng dụng.

Một integration test JPA nên flush rồi clear persistence context trước khi đọc lại, để xác nhận dữ liệu đã thực sự đi qua JDBC và database:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Import(TargetDatabaseConfiguration.class)
class JpaTargetDatabaseIT {

    @Autowired
    private AuditRecordRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    @Transactional
    void persistsAndReloadsVendorSpecificMapping() {
        AuditRecord saved = repository.save(
                new AuditRecord(Map.of(
                        "source", "native-compatibility-test",
                        "enabled", true)));

        entityManager.flush();
        Long id = saved.getId();

        entityManager.clear();

        AuditRecord loaded = repository.findById(id).orElseThrow();

        assertThat(loaded.getPayload())
                .containsEntry("source", "native-compatibility-test")
                .containsEntry("enabled", true);
    }
}
```

Ví dụ trên kiểm tra đường đi save → SQL → database → load lại. Nếu entity dùng kiểu dữ liệu vendor-specific, mapping phải được khai báo theo dialect mục tiêu. Chẳng hạn PostgreSQL `jsonb` có thể dùng Hibernate `@JdbcTypeCode(SqlTypes.JSON)` trong các phiên bản hỗ trợ; khi đổi database, cần kiểm tra lại SQL type, serializer và truy vấn JSON tương ứng.

Không dùng H2 thay cho PostgreSQL/MySQL/Oracle trong test xác nhận hành vi native của database. H2 vẫn hữu ích cho test nhanh, nhưng không chứng minh SQL và driver chạy đúng trên vendor đích.

## 4. Kiểm thử AOT trên JVM trước khi build native

Sau khi đã có JAR chứa mã AOT, chạy ứng dụng trên JVM với thuộc tính `spring.aot.enabled=true`. Với Maven dùng `spring-boot-starter-parent`, native profile có thể tạo các AOT asset cần thiết:

```bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/application.jar
```

Thay `target/application.jar` bằng tên artifact thực tế. Đối với Gradle, áp dụng Spring Boot AOT plugin hoặc GraalVM Native Image plugin theo cấu hình dự án để sinh AOT assets trước khi chạy.

Khi ứng dụng chạy ở AOT mode, thực hiện các smoke test quan trọng qua HTTP hoặc service layer:

- ApplicationContext khởi động với profile và property được chọn ở build time.
- DataSource khởi tạo và kết nối được tới database mục tiêu.
- EntityManagerFactory khởi tạo, mapping entity và repository scan thành công.
- Migration chạy đúng thứ tự và schema validation thành công.
- Các repository query quan trọng trả đúng dữ liệu.
- Transaction commit/rollback và lazy loading hoạt động như kỳ vọng.
- Các thành phần phụ thuộc reflection, proxy hoặc resource hoạt động.

AOT mode trên JVM giúp phát hiện lỗi generated initialization sớm, nhưng không thay thế bước chạy native executable. JVM vẫn có reflection và class loading linh hoạt hơn native image.

## 5. Build và chạy native executable thật

Khi AOT mode đã ổn định, build native image bằng Native Build Tools hoặc Cloud Native Buildpacks.

Với Maven, dự án dùng Spring Boot parent và native profile có thể chạy:

```bash
./mvnw -Pnative native:compile
```

Nếu cần tạo OCI image bằng Buildpacks:

```bash
./mvnw -Pnative spring-boot:build-image
```

Với Gradle đã áp dụng `org.graalvm.buildtools.native`:

```bash
./gradlew nativeCompile
```

Native compilation cần toolchain phù hợp và có thể tốn thời gian, vì vậy có thể chạy ở CI thay vì mỗi lần test unit. Sau khi build thành công, khởi chạy đúng executable hoặc container được tạo, cấu hình JDBC URL tới database test/staging, rồi chạy smoke test qua cổng thật của ứng dụng.

Không kết luận native test pass chỉ từ việc lệnh compile kết thúc thành công. Một native image có thể build được nhưng lỗi khi chạy do thiếu reflection hint, resource, proxy, JDBC service provider, encoding hoặc cấu hình runtime. Cần kiểm tra startup, health endpoint, thao tác đọc/ghi JPA và đóng kết nối trong chính native process.

Native image phụ thuộc hệ điều hành và kiến trúc đích. Build trên Linux x86_64 không tạo ra executable có thể mặc nhiên chạy trên Windows hoặc ARM64. Với deployment container, nên build bằng môi trường/Buildpack phù hợp với nền tảng production và kiểm tra image cuối cùng trong cùng loại runtime.

## 6. Chạy test bên trong native image

GraalVM Native Build Tools hỗ trợ chạy JUnit test bên trong native image. Đây là lớp kiểm thử sâu hơn, hữu ích cho các test cần xác nhận reflection, proxy và runtime behavior ngay trong native executable.

Với Maven, khi project có Spring Boot Maven plugin và Native Build Tools plugin cùng cấu hình `nativeTest` profile:

```bash
./mvnw test -PnativeTest
```

Với Gradle:

```bash
./gradlew nativeTest
```

Spring TestContext có thể thực hiện AOT processing cho test context và đóng gói JUnit TestEngine vào native test image. Có thể dùng `@SpringBootTest` hoặc test slice phù hợp. Native test build chậm hơn JVM test đáng kể, vì vậy thường chọn một nhóm test quan trọng chạy theo lịch hoặc trên pipeline release.

Không cần chuyển toàn bộ unit test sang native mode. Hãy giữ phần lớn test chạy trên JVM; chọn test đại diện cho các đường có rủi ro native cao như binding, custom converter, entity mapping, proxy, service loading và resource loading. Kiểm tra cả test infrastructure và mocking library vì không phải mọi thư viện test đều có cùng mức hỗ trợ native.

## 7. Kiểm thử Runtime Hints và reflection

Native Image cần metadata cho những hoạt động không thể suy ra đầy đủ từ phân tích tĩnh. Spring AOT tự tạo nhiều hint cho bean, proxy và kiểu dữ liệu mà Spring nhận diện được. Tuy nhiên, code ứng dụng hoặc thư viện gọi reflection theo quy ước riêng có thể cần hint bổ sung.

Spring RuntimeHints mô tả các nhu cầu như:

- Reflection để gọi constructor, method hoặc truy cập field.
- Classpath resources được đọc theo tên hoặc pattern.
- Java serialization.
- JDK dynamic proxy.

Nếu một DTO được bind bằng reflection nhưng Spring không thể suy luận từ controller signature hoặc cấu hình, có thể dùng `@RegisterReflectionForBinding` trên cấu hình/bean phù hợp. Với trường hợp tùy biến, triển khai `RuntimeHintsRegistrar` và đăng ký qua `@ImportRuntimeHints`.

Ví dụ đăng ký quyền reflection cho một kiểu legacy được gọi bằng reflection:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class LegacyPayloadHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                LegacyPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS,
                MemberCategory.DECLARED_FIELDS);
    }
}
```

Đăng ký registrar:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LegacyPayloadHints.class)
class NativeHintsConfiguration {
}
```

Chỉ thêm những member thật sự được sử dụng. Không đăng ký toàn bộ classpath hoặc mọi entity một cách máy móc; hint quá rộng có thể làm image lớn hơn và che khuất việc thư viện đang dùng một cơ chế động không phù hợp. Với Hibernate, phải theo hướng dẫn native-image của đúng Hibernate release và kiểm thử thực tế; không tự suy ra rằng đăng ký reflection cho entity là đủ để hỗ trợ bytecode provider, proxy, service loader và mọi extension.

Có thể kiểm thử registrar bằng RuntimeHintsPredicates trước khi build image:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

class LegacyPayloadHintsTests {

    @Test
    void registersReflectionForLegacyPayload() {
        RuntimeHints hints = new RuntimeHints();

        new LegacyPayloadHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onType(LegacyPayload.class))
                .accepts(hints);
    }
}
```

Test này xác nhận registrar đã đăng ký type hint. Nó không chứng minh toàn bộ native application hoạt động; vẫn phải build và chạy native image với đường code thật.

## 8. Dùng tracing agent để tìm hint còn thiếu

GraalVM tracing agent có thể chạy ứng dụng hoặc test trên JVM và ghi nhận các thao tác reflection, resource, proxy đã thực sự diễn ra. Đây là cách tìm hint còn thiếu khi thư viện hoặc code riêng sử dụng reflection mà Spring AOT chưa nhận diện.

Một lệnh minh họa khi chạy JAR có AOT assets:

```bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=build/native-agent-output \
  -jar target/application.jar
```

Sau khi khởi động, chạy các luồng nghiệp vụ cần kiểm tra: khởi tạo EntityManagerFactory, persist/find entity, chạy projection, converter, custom type, lazy association, serialization và query. Agent ghi metadata vào thư mục output khi process kết thúc.

Đọc và rà soát file metadata trước khi đưa vào `src/main/resources/META-INF/native-image/`. Agent chỉ ghi lại đường code đã được thực thi; đường chưa chạy vẫn có thể thiếu hint. Nếu chạy toàn bộ test suite, metadata có thể chứa quyền truy cập chỉ cần cho test framework. Dùng access-filter của tracing agent hoặc lọc cẩn thận để không đóng gói cấu hình thừa.

Không xem tracing agent output là bằng chứng tương thích. Nó là công cụ khám phá, còn kiểm thử native executable mới xác nhận metadata đó đủ cho workload mục tiêu.

## 9. Các đường Spring Data JPA/Hibernate cần kiểm tra trong native mode

Khi native image là yêu cầu triển khai, chọn test bao phủ những hành vi mà JVM và native runtime có thể khác nhau:

| Khu vực | Hành vi cần xác nhận |
|---|---|
| Entity metadata | Entity scan, constructor, field/property access, inheritance, embeddable và mapping |
| Repository proxy | Derived query, JPQL, native query, projection, specification và repository fragment |
| Association | Lazy/eager loading, proxy, collection wrapper, cascade và orphan removal |
| Type mapping | Enum, UUID, date/time, JSON, array, custom type, converter và null |
| Transaction | Commit, rollback, propagation, isolation, optimistic/pessimistic lock |
| Database | JDBC driver, dialect, sequence/identity, stored procedure, generated column và migration |
| Reflection | DTO binding, custom converter, method lookup và thư viện gọi reflection |
| Resource | SQL script, migration, template, message bundle, cấu hình và file được load theo tên |
| Proxy/service loading | JDK proxy, provider được đăng ký qua ServiceLoader và bytecode provider |

Với Hibernate extension, thêm test riêng cho từng tính năng thực sự dùng, chẳng hạn Envers audit revision, Spatial type/function, custom dialect, interceptor, event listener, filter hoặc cache provider. Đừng suy rộng từ việc core repository test thành công sang tất cả module extension.

Kiểm tra generated SQL trên database đích. Nếu query dùng cú pháp riêng của vendor, xác nhận nó thực thi trên đúng database và driver. Với native image, đặc biệt kiểm tra JDBC driver được đóng gói, tự đăng ký đúng và khởi tạo được trong executable. Một test repository trên JVM chỉ xác nhận đường JDBC ở JVM runtime.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| JVM test pass nhưng native startup fail | AOT generated code hoặc runtime hints chưa đủ | Chạy JVM AOT mode, xem lỗi đầu tiên và kiểm tra hint |
| Native image build fail với reflection warning/error | Thiếu reachability metadata hoặc thư viện dùng reflection động | Dùng tracing agent, kiểm tra thư viện và đăng ký hint tối thiểu |
| EntityManagerFactory không khởi tạo | Hibernate, bytecode provider, dialect hoặc service loading chưa tương thích native | Xác minh đúng Hibernate release/extension và JDBC driver; thử smoke test riêng |
| Repository proxy hoặc lazy association lỗi | Thiếu proxy/reflection metadata hoặc pattern không được AOT nhận diện | Kiểm tra generated hints và test đúng association trong native mode |
| DTO JSON lỗi khi serialize/deserialize | Binding reflection hoặc constructor/field access chưa được đăng ký | Kiểm tra `@RegisterReflectionForBinding` hoặc RuntimeHintsRegistrar cần thiết |
| File SQL/config không tìm thấy | Resource load theo tên không được đưa vào image | Đăng ký resource pattern và test đường đọc thực tế |
| Bean khác giữa JVM và AOT | Profile/conditional property được quyết định lúc build | Cung cấp đúng profile và environment ở build time |
| Chạy được trên máy dev nhưng lỗi ở container | Khác OS/arch/libc, charset, timezone hoặc native toolchain | Build/test trong môi trường gần deployment |
| Native test fail dù ứng dụng native chạy | Test framework hoặc mocking dependency chưa hỗ trợ native | Chọn test phù hợp, kiểm tra giới hạn test dependency và tách JVM test khỏi native test |

Không chữa mọi lỗi bằng cách thêm hàng loạt reflection hint hoặc bật khởi tạo class tại build time. Một hint rộng có thể che dấu vấn đề, còn build-time initialization sai có thể cố định trạng thái mà ứng dụng mong đợi khởi tạo ở runtime. Xác định chính xác đường code bị thiếu metadata, kiểm tra hỗ trợ của thư viện và thêm quyền tối thiểu cần thiết.

## 11. Pipeline kiểm thử khuyến nghị

Một pipeline có thể chia thành các tầng sau:

1. **Mỗi commit:** chạy unit test và integration test JVM với database mục tiêu, migration thật, query quan trọng và test mapping.
2. **Pull request hoặc nhánh chính:** build AOT assets, chạy ứng dụng trên JVM với `spring.aot.enabled=true`, kiểm tra startup và các endpoint JPA quan trọng.
3. **Nightly hoặc release candidate:** build native executable/container trên đúng OS/architecture, chạy smoke test với database mục tiêu và một tập integration test đại diện.
4. **Release:** kiểm tra image cuối cùng, cấu hình runtime, secret, JDBC URL, health/readiness, shutdown và kết nối database trong môi trường tương đương production.

Lưu artifact của mỗi lần build gồm version matrix, log AOT, log native compilation, metadata/hints được đóng gói, kết quả test và image digest. Khi nâng Spring Boot, Spring Data, Hibernate, JDBC driver hoặc GraalVM, chạy lại ma trận kiểm thử; không tái sử dụng kết quả của stack cũ để khẳng định stack mới tương thích.

## 12. Checklist trước khi triển khai

- Đã xác định native image có phải yêu cầu triển khai thực sự hay không.
- Spring Boot, Spring Data JPA, Hibernate ORM, GraalVM, Native Build Tools, JDBC driver và database version đã được pin.
- Đã kiểm tra tình trạng hỗ trợ native của Hibernate release và mọi extension đang dùng.
- JVM integration test chạy trên đúng loại database và migration mục tiêu.
- JAR chạy được với Spring AOT enabled trên JVM.
- Native executable/container build thành công và thực sự khởi động được.
- Native runtime kết nối database, chạy repository query, ghi/đọc entity và hoàn tất transaction.
- Reflection, proxy, serialization và resource hints được kiểm thử và giới hạn đúng nhu cầu.
- Tracing agent đã được dùng trên các đường code cần thiết nếu có dấu hiệu thiếu hint.
- Native smoke test chạy trên đúng OS, kiến trúc và container base của môi trường triển khai.
- CI lưu version matrix, build log và kết quả test để có thể tái hiện.

Native image và AOT có thể cải thiện đặc tính triển khai, nhưng chúng làm classpath, reflection và cấu hình build-time trở thành một phần của hợp đồng runtime. Với Spring Data JPA, hãy xác nhận cả Spring AOT lẫn Hibernate, JDBC driver và database mục tiêu bằng integration test và executable native thật; một lần compile thành công hoặc một bộ test JVM không đủ để chứng minh toàn bộ stack đã sẵn sàng.

## Tài liệu tham khảo

- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Boot — Advanced Native Image Topics and Custom Hints](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Framework — Runtime Hints and AOT](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Hibernate ORM — Getting Started and Modules](https://docs.hibernate.org/orm/7.2/quickstart/html_single/)
- [Hibernate ORM — Documentation and Version Support](https://hibernate.org/orm/documentation/)