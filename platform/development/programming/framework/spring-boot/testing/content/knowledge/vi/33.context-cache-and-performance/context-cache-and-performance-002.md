# Các thành phần tạo khóa cache: cấu hình, profile, properties và bean override

Trong một bộ kiểm thử Spring Boot, **khởi động ApplicationContext** thường tốn thời gian hơn chạy assertion. Spring TestContext giải quyết bằng **context cache**: nếu test sau cần **cùng cấu hình context** với test trước trong cùng JVM, framework có thể **dùng lại ApplicationContext đã khởi tạo**. Tuy nhiên, “cùng cấu hình” được xác định bởi một **khóa cache gồm nhiều thành phần**, không đơn giản là tên class test hay cùng có `@SpringBootTest`.

Ví dụ:

- Hai test classes khác tên nhưng cùng tập cấu hình, active profiles, test properties và bean overrides **có thể chia sẻ một context**.
- Một test thêm `@ActiveProfiles("qa")` trong khi test khác dùng `"dev"` → **khác cache key**.
- Hai tests đều dùng `@SpringBootTest` nhưng một test khai `@MockitoBean ExternalClient` còn test kia không → **khác contextCustomizers**, nên phải tạo context khác.
- Hai tests cùng mock một bean nhưng khác **field name fallback qualifier**, `@Qualifier` hoặc tên override có thể tạo **hai khóa khác nhau**, dù mục tiêu nghiệp vụ nhìn rất giống nhau.
- Một `@DynamicPropertySource` method khác có thể đổi khóa; nhưng **giá trị đang trả về bởi cùng supplier** không được tự động dùng làm một khóa cache mới cho mỗi lần thay đổi runtime.
- `@DirtiesContext` chủ động loại context khỏi cache; đó là **eviction**, không phải một trong các giá trị cấu hình của khóa.

Bài này thuộc nhóm **Context cache và hiệu năng** của **Spring Boot - testing**, tập trung vào chủ đề **“Các thành phần tạo khóa cache: cấu hình, profile, properties và bean override”**. Ta sẽ nhìn chính xác danh sách thuộc tính tạo khóa trong Spring Framework 6.2, cách các annotation Spring Boot/Jakarta/Mockito tham gia, lý do cache hit/miss, log thống kê, LRU, fork JVM, @DirtiesContext, thực hành Java 17 + Spring Boot 3.5 và cách cải thiện thời gian chạy suite mà không gây test phụ thuộc lẫn nhau.

**Quy tắc cốt lõi:** context cache là cơ chế **reuse các Spring beans**, không phải cơ chế tự cô lập trạng thái mutable của beans. Tối ưu hit rate phải đi cùng chiến lược reset mocks, dữ liệu test, queue và external resources để giữ đúng test isolation.

## 1. Spring TestContext cache hoạt động theo cơ chế nào?

Spring TestContext tải một `ApplicationContext` hoặc `WebApplicationContext` khi một test cần Spring-managed beans. Sau khi tải thành công, Spring có thể lưu context trong **static cache** của tiến trình JVM và tìm lại theo `MergedContextConfiguration` ở các lần chạy tiếp theo.

```text
JUnit test class A
       |
       v
TestContextBootstrapper
       |
       v
MergedContextConfiguration
  + classes / locations
  + initializers / loader / parent
  + profiles / property sources
  + context customizers (bean overrides, dynamic props,...)
  + resource base path
       |
       v
   build cache KEY
       |
       +---- cache HIT  ------> reuse ApplicationContext instance
       |                       (singleton beans còn trong context)
       |
       +---- cache MISS ------> load / refresh new ApplicationContext
                               -> cache put / LRU eviction
       |
       v
    inject beans into test
    execute test method
```

Khác biệt:

| Khái niệm | Nghĩa | Điều cần nhớ |
|---|---|---|
| Cache hit | Khóa đã có context còn hoạt động | Thường tránh khởi tạo context lần nữa |
| Cache miss | Không có context ứng với khóa | Tốn startup, auto-config, bean creation, DB fixtures tùy app |
| Cache key | Tập thuộc tính cấu hình merged | Không mặc định chứa **tên test class** |
| Cache size | Số context entries trong JVM | Default maximum **32**, không phải 32 test methods |
| Eviction | Loại context khỏi cache | LRU hoặc `@DirtiesContext`, context có thể bị close |
| Context state | Các singleton/caches/connections đang tồn tại | Có thể bị test trước thay đổi nếu tái sử dụng |
| Fork JVM | Một tiến trình Java khác | Static cache **không** chia sẻ qua các JVMs |

Một test chạy rất nhanh **không tự chứng minh cache hit**: có thể nó chỉ khởi động một context nhỏ. Một test chạy chậm **không luôn là cache miss**: có thể assertion đang truy vấn DB hoặc chờ network. Hãy dùng **thống kê cache** cùng bằng chứng context identity để hiểu nguyên nhân.

## 2. Danh sách chính xác các thành phần tạo khóa cache

Theo tài liệu chính thức Spring Framework 6.2, khóa của `MergedContextConfiguration` sử dụng các thuộc tính sau:

| Thành phần key | Nguồn thông thường | Ví dụ thay đổi khiến key khác |
|---|---|---|
| **`locations`** | `@ContextConfiguration(locations=...)` | Đổi XML/config resource |
| **`classes`** | `@ContextConfiguration(classes=...)` và các classes cấu hình được Spring Boot suy ra | `ConfigA.class` khác `ConfigB.class` |
| **`contextInitializerClasses`** | `@ContextConfiguration(initializers=...)` | `InitA.class` khác `InitB.class` |
| **`contextCustomizers`** | `ContextCustomizerFactory`: `@DynamicPropertySource`, `@MockitoBean`, `@MockitoSpyBean`, `@TestBean`, Boot test customizations, v.v. | Thêm mock/spy, đổi bean override, khác method DynamicPropertySource |
| **`contextLoader`** | `@ContextConfiguration(loader=...)`, Boot test bootstrapper | Loader class khác |
| **`parent`** | `@ContextHierarchy` | Parent context configuration khác |
| **`activeProfiles`** | `@ActiveProfiles`, resolver và kế thừa | `qa` khác `prod` |
| **`propertySourceDescriptors`** | `@TestPropertySource(locations=...)` | `classpath:/a.properties` khác `b.properties` |
| **`propertySourceProperties`** | `@TestPropertySource(properties=...)` và config test-inline liên quan | `feature.mode=a` khác `feature.mode=b` |
| **`resourceBasePath`** | `@WebAppConfiguration` | Web resource root khác |

**Điểm dễ bỏ sót:** `contextCustomizers` là thành phần key lớn và dễ bị phân mảnh bởi cơ chế test của **Spring Boot** và **Spring Framework 6.2**. Một annotation mock field tưởng chỉ tác động trong từng test method thực ra có thể thay đổi **cấu hình bean của cả context**. Tên field fallback, bean name, qualifier, override strategy và danh sách các overrides cần được giữ nhất quán nếu muốn reuse.

### Tên class test có nằm trực tiếp trong key không?

Không phải một key field độc lập. Spring Framework `MergedContextConfiguration.hashCode()` cố ý **không dùng testClass** để hai lớp kiểm thử có cấu hình merged tương đương có thể chia sẻ context. Tuy nhiên, **class test có thể ảnh hưởng gián tiếp**: nó khai báo profiles, properties, nested configuration, `@DynamicPropertySource` methods, mocks, imports hoặc customizers khác.

```text
CustomerServiceTest     PaymentServiceTest
  @SpringBootTest          @SpringBootTest
  cùng config/profiles     cùng config/profiles
  không override bean      không override bean
        |                       |
        +-------- SAME KEY -----+
                        |
                        v
               shared ApplicationContext
```

Nếu một lớp dùng `@SpringBootTest(classes=A.class)` còn lớp kia dùng `@SpringBootTest(classes=B.class)`, khác `classes` → key khác, kể cả hai cấu hình tạo các beans “trông giống nhau”.

## 3. Cấu hình: classes, locations, loader, initializers, parent

### 3.1. `@SpringBootTest(classes=...)`

Ví dụ:

```java
@SpringBootTest(
    classes = ApplicationForTest.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ServiceIntegrationTest {
}
```

`@SpringBootTest` là điểm khởi tạo Spring Boot application test context. `classes` ảnh hưởng đến cấu hình đã merge và từ đó đến khóa cache. Một số khác biệt của Boot test như `webEnvironment`, `properties` và context customizers cũng có thể khiến key khác; không suy từ việc hai classes dùng cùng annotation tổng quát là chúng sẽ share.

**Để reuse có chủ đích**, nhiều test classes có thể cùng chỉ định **một class cấu hình**, thay vì mỗi test khai một `@TestConfiguration` nested class riêng cho một thay đổi nhỏ. Nhưng không đánh đổi tính đúng: nếu test thực sự cần bean graph khác, context riêng là kết quả hợp lý.

### 3.2. `@ContextConfiguration` và initializer

```java
@ContextConfiguration(
    classes = ApplicationForTest.class,
    initializers = FeatureInitializer.class)
class FeatureTest {
}
```

Đổi `FeatureInitializer.class` sang class khác làm thay `contextInitializerClasses`. Điều này vẫn đúng khi hai initializers đặt **cùng property value**: cache key dựa trên **declarations**, không chạy application rồi so bean graph.

### 3.3. Context hierarchy và web resource base path

- `@ContextHierarchy` tạo parent/child relationships; key của child chứa cấu hình parent. `@DirtiesContext(hierarchyMode=...)` có thể evict nhiều contexts liên quan.
- `@WebAppConfiguration("src/main/webapp")` tham gia `resourceBasePath`; web test context có thể khác non-web context.
- `@ContextConfiguration(loader=CustomLoader.class)` thay đổi `contextLoader`, dù config classes giống nhau.

Các thuộc tính này ít xuất hiện trong unit tests nhưng quan trọng với legacy XML, servlet web contexts và nhiều tầng Spring context.

## 4. Active profiles và hành vi bean khác nhau

`@ActiveProfiles` chọn tập Spring profiles khi test context được tạo:

```java
@SpringBootTest(classes = CacheDemoApplication.class)
@ActiveProfiles("local")
class LocalTest {
}

@SpringBootTest(classes = CacheDemoApplication.class)
@ActiveProfiles("staging")
class StagingTest {
}
```

Hai contexts khác khóa dù cả hai profile **chưa khai bean `@Profile` nào**. Spring không tối ưu bằng cách dựng context rồi so sánh xem beans có giống nhau không; key được tính **trước startup**, dựa trên metadata. Việc đặt một profile riêng tùy tiện cho từng test class có thể làm tăng số context và thời gian suite.

### Profile resolution và kế thừa

- `@ActiveProfiles({"test","postgres"})` có thể khác `@ActiveProfiles("test")`.
- Profiles từ superclass/enclosing test class có thể được kế thừa theo `inheritProfiles`.
- `ActiveProfilesResolver` tùy biến có thể trả profiles động; muốn reuse ổn định cần resolver deterministic theo cấu hình.
- Việc thay đổi property `spring.profiles.active` bằng một nguồn khác **không thay thế** hiểu biết về `@ActiveProfiles` và các field key liên quan; kiểm chính những annotations/properties thực sự được merged.
- Spring Framework chuẩn hóa một số giá trị profiles (ví dụ loại trùng/sắp xếp trong cấu hình merged), nên không suy rằng chỉ đảo thứ tự bằng text luôn tạo key mới. Hãy kiểm metadata/log hoặc thử identity thực tế.
- Một profile tạo bean graph khác có thể yêu cầu context riêng, **không nên ép dùng chung** bằng cách bỏ annotation quan trọng chỉ để giảm thời gian test.

### Test fixture profile thống nhất

Khi nhiều integration tests chạy trên cùng database fake hoặc Testcontainers service với cùng bean definitions, có thể dùng base test class:

```java
@ActiveProfiles("integration")
abstract class IntegrationBaseTest {
}
```

Đây là snippet, không phải file runnable: các test subclasses còn cần `@SpringBootTest` hoặc Spring test context config phù hợp. Một base test class giúp profile policy nhất quán, nhưng **không đảm bảo key giống nhau** nếu mỗi subclass vẫn có khác `@MockitoBean`/`@DynamicPropertySource`/properties.

## 5. Test properties: inline, file, Boot annotations và dynamic suppliers

### 5.1. `@TestPropertySource(properties=...)`

```java
@TestPropertySource(properties = "checkout.mode=stub")
class StubModeTest {}

@TestPropertySource(properties = "checkout.mode=live")
class LiveModeTest {}
```

**Khác literal property string** → khác `propertySourceProperties`. TestContext không cần biết hai settings cuối cùng có làm bean khác nhau hay không. Nó phải tạo context riêng theo key để tránh vô tình dùng bean đã bind với cấu hình khác.

### 5.2. `@TestPropertySource(locations=...)`

```java
@TestPropertySource(
    locations = "classpath:/test-config/alpha.properties")
class AlphaConfigTest {}

@TestPropertySource(
    locations = "classpath:/test-config/beta.properties")
class BetaConfigTest {}
```

Đường dẫn/descriptor property resource tham gia `propertySourceDescriptors`. Hai files có nội dung giống nhau nhưng **đường dẫn khác** vẫn có thể tạo keys khác nhau. Cùng một descriptor nhưng **nội dung file bị sửa giữa hai lượt cùng JVM** không có nghĩa cache tự lập key mới; key không phải hash nội dung file. Test muốn reload có thể dùng `@DirtiesContext` hoặc tổ chức build/test fixtures để tránh runtime mutation.

### 5.3. `@SpringBootTest(properties=...)`

```java
@SpringBootTest(
    classes = CacheDemoApplication.class,
    properties = "checkout.mode=stub")
class CheckoutStubTest {}
```

Spring Boot tích hợp test properties/initializers với TestContext bootstrapstrapping; giá trị khác có thể làm key khác. Trên thực tế **@SpringBootTest(properties)** và **@TestPropertySource(properties)** không nhất thiết tạo cấu hình merged giống hệt nhau dù cuối cùng `Environment` có một key/value giống nhau, vì nguồn và customizers khác nhau. Hãy chuẩn hóa cách khai báo giữa các test classes cần reuse thay vì cho rằng “Environment giống nhau” đủ để share.

**Lưu ý:** `application-test.yml`/`application.properties` được nạp theo quá trình Boot start; các nguồn properties thông thường không tự là từng key field riêng kiểu “nội dung tất cả YAML files”. Cache key đến từ metadata test context cùng customizers. Khi muốn context phản ánh nguồn properties đã đổi, cần chạy fresh JVM, thay cấu hình test hoặc explicit eviction.

### 5.4. `@DynamicPropertySource` và giá trị thay đổi

`@DynamicPropertySource` được dùng nhiều cho Testcontainers:

```java
@DynamicPropertySource
static void dbProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.datasource.url",
        postgres::getJdbcUrl);
}
```

Snippet giả định `postgres` là container fixture đúng lifecycle. **Method được khai báo** tham gia `contextCustomizers`/cache key; **giá trị do supplier trả về** không tự trở thành danh sách key fields riêng cho mỗi lần supplier thay đổi. Vì vậy:

1. Hai test classes khai hai static dynamic property methods khác nhau có thể tạo **hai context keys** dù cả hai supplier đều trả cùng URL.
2. Một method cố định trỏ tới container có URL/port thay đổi giữa tests có thể tiếp tục reuse **context cũ** với DataSource/beans đã được tạo từ URL ban đầu. Cần tổ chức **container lifecycle, context cache và dynamic property methods** nhất quán.
3. Nếu một base class có `@DynamicPropertySource` và subclasses làm môi trường thay đổi ngoài cùng method, cân nhắc `@DirtiesContext` trên class cần refresh theo hướng dẫn Spring, hoặc tránh dùng mutable supplier bằng cách giữ container ổn định trong suốt suite.
4. Với Spring Boot `@ServiceConnection`, Testcontainers wiring cũng có thể đi qua Boot test customizers; không kết luận rằng mọi lần port thay đổi sẽ tự động tạo context mới.

Đừng đặt `@DynamicPropertySource` riêng cho từng test class nếu tất cả đều dùng một shared container đúng lifecycle; nó có thể làm cache bị chia nhỏ không cần thiết. Nhưng **đừng chia sẻ container đã stop** cùng cache key nếu cached DataSource còn trỏ tới port cũ.

## 6. Bean override là thành phần cache key, không chỉ là fixture

Với Spring Framework 6.2, có các annotations:

- **`@MockitoBean`:** thay bean bằng Mockito mock; mặc định chiến lược `REPLACE_OR_CREATE`, có thể dùng `enforceOverride=true` để bắt buộc phải có bean đích.
- **`@MockitoSpyBean`:** wrap một bean hiện có bằng spy, thường yêu cầu đúng một candidate.
- **`@TestBean`:** thay bean bằng đối tượng do test factory method tạo, không dựa trên Mockito.
- Spring Boot 3.4+ đánh dấu các test annotations cũ **`@MockBean`/`@SpyBean`** là deprecated để chuyển sang `@MockitoBean`/`@MockitoSpyBean` của Spring Framework, nên bài dùng API mới trên Boot 3.5.

Những overrides này tham gia `contextCustomizers`. Vì thế các test classes có overrides khác nhau có thể nhận context khác nhau **trước khi test method chạy**.

### 6.1. Có và không có mock → hai context keys

```java
@SpringBootTest(classes = CacheDemoApplication.class)
class RealClientTest {
    @Autowired ExternalClient externalClient;
}

@SpringBootTest(classes = CacheDemoApplication.class)
class MockClientTest {
    @MockitoBean ExternalClient externalClient;
}
```

Trường hợp thứ hai cần bean graph với mock; trường hợp đầu cần real client. Cho hai tests dùng cùng một context sẽ sai về bản chất. Cache miss là **đúng mục tiêu isolation theo cấu hình**.

### 6.2. Tên field fallback có thể làm key khác

`@MockitoBean` trên field suy ra type bean cần override. Nếu không có `@Qualifier` tường minh, **tên field được dùng làm fallback qualifier**. Tài liệu Spring Security? Không: đây là chính sách của **Spring Framework TestContext bean overriding**. Spring khuyến nghị đặt tên fields nhất quán giữa test classes để tránh context keys khác không cần thiết.

```java
// Test A:
@MockitoBean
ExternalClient externalClient;

// Test B:
@MockitoBean
ExternalClient paymentGateway;
```

Nếu chỉ có một bean phù hợp, cả hai có thể mock cùng target theo type, nhưng metadata qualifier/fallback khác nhau vẫn có thể gây **cache key split**. Đây là điểm quan trọng khi nhiều lớp copy test code rồi đổi field name cho “dễ đọc” mà vô tình tạo các contexts mới.

Giải pháp ổn định khi thật sự cần share mock setup:

```java
@MockitoBean(
    name = "externalClient",
    enforceOverride = true)
ExternalClient externalClient;
```

Dùng cùng **tên bean tường minh, type, qualifier và cấu hình mock** ở các test classes. Có thể đưa override policy lên một shared meta-annotation/test base khi phù hợp. Đừng ép hai test cần **khác override** thành một key giống nhau: chúng phải tách context để đúng semantics.

### 6.3. Vì sao thay đổi Mockito stubbing thường không đổi key?

```java
when(externalClient.call()).thenReturn("MOCK-A");
// Ở test method khác:
when(externalClient.call()).thenReturn("MOCK-B");
```

Hai lệnh `when(...)` ở runtime **không** phải field trong `MergedContextConfiguration`. Chúng thay đổi behavior của **mock instance** được chứa trong context, không tạo key mới. Với Spring TestContext bean override support, `MockitoResetTestExecutionListener` thường reset mocks sau hoặc trước mỗi test theo cấu hình `MockReset`; nếu tắt reset, mock stubs/interactions có thể leak khi context được share.

**Đừng dùng `@DirtiesContext` chỉ để reset mỗi Mockito stub**: vừa chậm vừa che test isolation issue. Ưu tiên reset đúng mock/lifecycle; giữ test code độc lập.

### 6.4. `@MockitoSpyBean` và `@TestBean`

- Spy dùng bean thật làm nền, nên có thể **thực thi side effects** khi stubbing sai; dùng `Mockito.doReturn(...).when(spy)...` khi cần tránh gọi real method.
- `@TestBean` có factory method, tên/qualifier/scope và cấu hình bean override sẽ tham gia context customizer phù hợp.
- Bean override không đồng nghĩa `spring.main.allow-bean-definition-overriding=true`. Framework test bean override infrastructure xử lý có chủ đích; **không bật global bean-definition overriding** chỉ để chữa sai test config.
- Với `@ContextHierarchy`, cần dùng `contextName` của `@MockitoBean` khi chỉ muốn override ở một level; nếu không nó có thể áp dụng tới nhiều hierarchy levels và gây lỗi/fragmentation.
- Không nên mock mọi dependency trong mỗi `@SpringBootTest` nếu chỉ muốn kiểm một service thuần Java: unit test Mockito không cần context sẽ nhanh hơn và không tạo cache key.

## 7. Demo runnable: Java 17 + Spring Boot 3.5, kiểm cache key bằng context identity

Demo sẽ **không dựa vào milliseconds** và không đòi thứ tự test methods. Ta tạo các **marker test configuration classes** được gắn annotations giống những test classes thường gặp, sau đó dùng `TestContextManager` để yêu cầu Spring TestContext tải context cho từng marker và so sánh **chính instance `ApplicationContext`**.

Đây là kỹ thuật diagnostic/training để thấy key behavior tập trung trong một test class. Trong dự án thực, thường chỉ đặt `@SpringBootTest` trên mỗi integration test class, không tự gọi `TestContextManager` ở mỗi method. Nhưng API chính thức cho phép minh họa reuse/miss mà không đợi hai test classes chạy theo thứ tự ngẫu nhiên.

### 7.1. Cấu trúc thư mục

```text
context-cache-key-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cache/
    │   ├── CacheDemoApplication.java
    │   ├── AlternativeApplication.java
    │   ├── Snapshot.java
    │   ├── ExternalClient.java
    │   └── SecondaryClient.java
    └── test/
        ├── java/com/example/cache/
        │   └── ContextCacheKeyTest.java
        └── resources/
            ├── variant-alpha.properties
            └── variant-beta.properties
```

Chỉ **`ContextCacheKeyTest`** chứa `@Test`. Các nested static marker classes bên trong nó **không chứa JUnit test methods**, chỉ mang annotations để `TestContextManager` tạo cấu hình tương ứng. Chúng không phải các `@Nested` JUnit tests.

### 7.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>context-cache-key-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-test` của Boot 3.5 kéo theo Spring TestContext, JUnit Jupiter, AssertJ và Mockito. `@MockitoBean` thuộc package `org.springframework.test.context.bean.override.mockito` có trong Spring Framework 6.2. Ví dụ không cần web server/JPA/DB/Kafka. Một Spring Boot config tối thiểu, không bật tất cả auto-configurations, giúp mọi context nhỏ nhưng vẫn bộc lộ các thuộc tính khóa của TestContext.

**Vì sao không gọi `ApplicationContextRunner` để chứng minh cache?** `ApplicationContextRunner.run(...)` tạo/đóng context cho từng invocation theo thiết kế kiểm auto-configuration; nó **không phải cơ chế static context cache của Spring TestContext**. Muốn chứng minh keys/cache, cần TestContext (`@SpringBootTest`/`@SpringJUnitConfig` hoặc `TestContextManager`).

### 7.3. Config gốc và beans

File **`src/main/java/com/example/cache/CacheDemoApplication.java`**:

```java
package com.example.cache;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootConfiguration
public class CacheDemoApplication {

    @Bean
    public Snapshot snapshot(Environment env) {
        return new Snapshot(
                env.getProperty("demo.value", "default"));
    }

    @Bean
    public ExternalClient externalClient() {
        return () -> "real-external";
    }

    @Bean
    public SecondaryClient secondaryClient() {
        return () -> "real-secondary";
    }
}
```

`@SpringBootConfiguration` là Spring configuration class để Boot test bootstrapper nhận diện. Ta không thêm `@EnableAutoConfiguration` hoặc `@ComponentScan` để giới hạn bean graph, phù hợp bài về cache key. `Snapshot` giữ **giá trị property tại lúc context khởi tạo**: nếu cùng context được reuse dù bên ngoài thay property supplier, bean snapshot vẫn mang giá trị cũ.

File **`src/main/java/com/example/cache/AlternativeApplication.java`**:

```java
package com.example.cache;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
public class AlternativeApplication {

    @Bean
    public Snapshot snapshot() {
        return new Snapshot("alternative");
    }
}
```

Thay class cấu hình `CacheDemoApplication` bằng `AlternativeApplication` tạo khác `classes`, nên context khác. Không cần thay test class name để thấy điều này.

File **`src/main/java/com/example/cache/Snapshot.java`**:

```java
package com.example.cache;

public record Snapshot(String value) {
}
```

File **`src/main/java/com/example/cache/ExternalClient.java`**:

```java
package com.example.cache;

@FunctionalInterface
public interface ExternalClient {
    String call();
}
```

File **`src/main/java/com/example/cache/SecondaryClient.java`**:

```java
package com.example.cache;

@FunctionalInterface
public interface SecondaryClient {
    String call();
}
```

Hai client interfaces có real beans nên `@MockitoBean(enforceOverride=true)` trong test có thể **thay bean đã tồn tại**. `Snapshot` là bean lấy property để chứng minh context được bind với giá trị ban đầu. Không có external network/real secrets.

### 7.4. Hai property resources

File **`src/test/resources/variant-alpha.properties`**:

```properties
demo.value=alpha-file
```

File **`src/test/resources/variant-beta.properties`**:

```properties
demo.value=beta-file
```

Đường dẫn files khác nhau → `propertySourceDescriptors` khác. Bài không kiểm hashing của nội dung file và không cố mutate file trong runtime.

### 7.5. JUnit test class: so sánh cấu hình, profile, properties và overrides

File **`src/test/java/com/example/cache/ContextCacheKeyTest.java`**:

```java
package com.example.cache;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mockingDetails;

class ContextCacheKeyTest {

    // Kỹ thuật học tập: tạo TestContext cho các marker classes.
    // Spring sẽ sử dụng CHUNG static ContextCache trong JVM.
    private static ApplicationContext load(Class<?> marker) {
        return new TestContextManager(marker)
                .getTestContext()
                .getApplicationContext();
    }

    private static String snapshotValue(ApplicationContext ctx) {
        return ctx.getBean(Snapshot.class).value();
    }

    // --------- Các @Test: 18 kịch bản kiểm cache key ---------

    @Test
    void twoDifferentTestClassesWithSameConfigShareContext() {
        ApplicationContext a = load(BaseA.class);
        ApplicationContext b = load(BaseB.class);

        assertThat(a).isSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("default");
    }

    @Test
    void repeatedLoadOfSameMarkerHitsCache() {
        ApplicationContext a = load(BaseA.class);
        ApplicationContext again = load(BaseA.class);

        assertThat(again).isSameAs(a);
    }

    @Test
    void differentConfigurationClassesProduceDifferentContexts() {
        ApplicationContext base = load(BaseA.class);
        ApplicationContext other = load(AlternativeConfig.class);

        assertThat(base).isNotSameAs(other);
        assertThat(snapshotValue(other))
                .isEqualTo("alternative");
    }

    @Test
    void differentActiveProfilesProduceDifferentContexts() {
        ApplicationContext alpha = load(ProfileAlphaA.class);
        ApplicationContext beta = load(ProfileBeta.class);

        assertThat(alpha).isNotSameAs(beta);
        assertThat(snapshotValue(alpha)).isEqualTo("default");
        assertThat(snapshotValue(beta)).isEqualTo("default");
        // Bean graphs giống nhau vẫn không làm keys giống nhau.
    }

    @Test
    void sameActiveProfileAcrossClassesReusesContext() {
        ApplicationContext a = load(ProfileAlphaA.class);
        ApplicationContext b = load(ProfileAlphaB.class);

        assertThat(a).isSameAs(b);
    }

    @Test
    void differentInlineTestPropertiesSplitCache() {
        ApplicationContext a = load(InlineAlphaA.class);
        ApplicationContext b = load(InlineBeta.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("inline-alpha");
        assertThat(snapshotValue(b)).isEqualTo("inline-beta");
    }

    @Test
    void sameInlineTestPropertiesAcrossClassesReuseContext() {
        assertThat(load(InlineAlphaA.class))
                .isSameAs(load(InlineAlphaB.class));
    }

    @Test
    void differentPropertyResourceDescriptorsSplitCache() {
        ApplicationContext a = load(FileAlphaA.class);
        ApplicationContext b = load(FileBeta.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("alpha-file");
        assertThat(snapshotValue(b)).isEqualTo("beta-file");
    }

    @Test
    void samePropertyFileAcrossClassesReusesContext() {
        assertThat(load(FileAlphaA.class))
                .isSameAs(load(FileAlphaB.class));
    }

    @Test
    void springBootTestInlinePropertiesAffectKey() {
        ApplicationContext a = load(BootPropertyA.class);
        ApplicationContext b = load(BootPropertyB.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("boot-a");
        assertThat(snapshotValue(b)).isEqualTo("boot-b");
    }

    @Test
    void differentInitializerClassesSplitContextKey() {
        ApplicationContext a = load(WithFirstInitializer.class);
        ApplicationContext b = load(WithSecondInitializer.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("init-one");
        assertThat(snapshotValue(b)).isEqualTo("init-two");
    }

    @Test
    void differentDynamicPropertyMethodsSplitKeysEvenIfValuesSame() {
        ApplicationContext a = load(DynamicProviderA.class);
        ApplicationContext b = load(DynamicProviderB.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("dynamic-same");
        assertThat(snapshotValue(b)).isEqualTo("dynamic-same");
    }

    @Test
    void mockOverrideChangesContextKeyAndBeanType() {
        ApplicationContext real = load(BaseA.class);
        ApplicationContext mocked = load(MockExternalA.class);

        assertThat(mocked).isNotSameAs(real);

        assertThat(mockingDetails(
                real.getBean(ExternalClient.class)).isMock())
                .isFalse();

        assertThat(mockingDetails(
                mocked.getBean(ExternalClient.class)).isMock())
                .isTrue();
    }

    @Test
    void identicalExplicitNamedOverridesReuseCacheAcrossClasses() {
        ApplicationContext a = load(MockExternalA.class);
        ApplicationContext b = load(MockExternalB.class);

        assertThat(a).isSameAs(b);
    }

    @Test
    void differentSetsOfMockOverridesNeedDifferentContexts() {
        ApplicationContext one = load(MockExternalA.class);
        ApplicationContext two = load(MockExternalAndSecondary.class);

        assertThat(two).isNotSameAs(one);
        assertThat(mockingDetails(
                two.getBean(ExternalClient.class)).isMock())
                .isTrue();
        assertThat(mockingDetails(
                two.getBean(SecondaryClient.class)).isMock())
                .isTrue();
    }

    @Test
    void differentFallbackMockFieldNamesCanSplitKeys() {
        ApplicationContext a = load(MockByTypeNamedAsBean.class);
        ApplicationContext b = load(MockByTypeRenamedField.class);

        assertThat(a).isNotSameAs(b);
        assertThat(mockingDetails(
                a.getBean(ExternalClient.class)).isMock()).isTrue();
        assertThat(mockingDetails(
                b.getBean(ExternalClient.class)).isMock()).isTrue();
    }

    @Test
    void samePropertyValueFromDifferentDeclarationPathsNeedNotShare() {
        ApplicationContext a = load(InlineFromTestProperty.class);
        ApplicationContext b = load(InlineFromBootTest.class);

        assertThat(snapshotValue(a)).isEqualTo("same-value");
        assertThat(snapshotValue(b)).isEqualTo("same-value");
        assertThat(a).isNotSameAs(b);
    }

    @Test
    void markingContextDirtyEvictsAndRecreatesIt() {
        TestContext tc = new TestContextManager(DirtyMarker.class)
                .getTestContext();

        ApplicationContext before = tc.getApplicationContext();

        tc.markApplicationContextDirty(
                DirtiesContext.HierarchyMode.EXHAUSTIVE);

        ApplicationContext after = tc.getApplicationContext();

        assertThat(after).isNotSameAs(before);
        assertThat(snapshotValue(after)).isEqualTo("dirty-marker");
        // @DirtiesContext có tác động tương đương khi
        // TestExecutionListener của Spring xử lý annotation.
    }

    // ------------ Marker classes: chỉ có annotations ------------

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class BaseA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class BaseB {}

    @SpringBootTest(
        classes = AlternativeApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class AlternativeConfig {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ActiveProfiles("alpha")
    static class ProfileAlphaA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ActiveProfiles("alpha")
    static class ProfileAlphaB {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ActiveProfiles("beta")
    static class ProfileBeta {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=inline-alpha")
    static class InlineAlphaA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=inline-alpha")
    static class InlineAlphaB {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=inline-beta")
    static class InlineBeta {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(
        locations = "classpath:/variant-alpha.properties")
    static class FileAlphaA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(
        locations = "classpath:/variant-alpha.properties")
    static class FileAlphaB {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(
        locations = "classpath:/variant-beta.properties")
    static class FileBeta {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.value=boot-a")
    static class BootPropertyA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.value=boot-b")
    static class BootPropertyB {}

    public static class FirstInitializer
            implements ApplicationContextInitializer<
                    ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext ctx) {
            ctx.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource(
                    "firstInit",
                    Map.of("demo.value", "init-one")));
        }
    }

    public static class SecondInitializer
            implements ApplicationContextInitializer<
                    ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext ctx) {
            ctx.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource(
                    "secondInit",
                    Map.of("demo.value", "init-two")));
        }
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ContextConfiguration(initializers = FirstInitializer.class)
    static class WithFirstInitializer {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ContextConfiguration(initializers = SecondInitializer.class)
    static class WithSecondInitializer {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class DynamicProviderA {
        @DynamicPropertySource
        static void sameValue(DynamicPropertyRegistry registry) {
            registry.add("demo.value", () -> "dynamic-same");
        }
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class DynamicProviderB {
        @DynamicPropertySource
        static void sameValue(DynamicPropertyRegistry registry) {
            registry.add("demo.value", () -> "dynamic-same");
        }
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockExternalA {
        @MockitoBean(
            name = "externalClient", enforceOverride = true)
        ExternalClient externalClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockExternalB {
        @MockitoBean(
            name = "externalClient", enforceOverride = true)
        ExternalClient externalClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockExternalAndSecondary {
        @MockitoBean(
            name = "externalClient", enforceOverride = true)
        ExternalClient externalClient;

        @MockitoBean(
            name = "secondaryClient", enforceOverride = true)
        SecondaryClient secondaryClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockByTypeNamedAsBean {
        @MockitoBean
        ExternalClient externalClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockByTypeRenamedField {
        @MockitoBean
        ExternalClient gateway;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=same-value")
    static class InlineFromTestProperty {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.value=same-value")
    static class InlineFromBootTest {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=dirty-marker")
    static class DirtyMarker {}
}
```

### 7.6. Giải thích bằng chứng của 18 JUnit tests

| Test method | Thành phần key | Kết luận |
|---|---|---|
| `twoDifferentTestClassesWithSameConfigShareContext` | Cấu hình merged giống nhau | Khác tên lớp vẫn **cùng instance context** |
| `repeatedLoadOfSameMarkerHitsCache` | Key giống hệt | Lần gọi tiếp theo reuse context |
| `differentConfigurationClassesProduceDifferentContexts` | `classes` | Khác class config → khác instance |
| `differentActiveProfilesProduceDifferentContexts` | `activeProfiles` | Khác profile → khác context dù beans có thể giống |
| `sameActiveProfileAcrossClassesReusesContext` | `activeProfiles` bằng nhau | Context reuse giữa hai marker classes |
| `differentInlineTestPropertiesSplitCache` | `propertySourceProperties` | Inline value khác → context khác |
| `sameInlineTestPropertiesAcrossClassesReuseContext` | Inline metadata giống | Context reuse |
| `differentPropertyResourceDescriptorsSplitCache` | `propertySourceDescriptors` | Test property file khác → context khác |
| `samePropertyFileAcrossClassesReusesContext` | Cùng descriptor | Context reuse |
| `springBootTestInlinePropertiesAffectKey` | Boot test properties | Khác property Boot test → context khác |
| `differentInitializerClassesSplitContextKey` | `contextInitializerClasses` | Khác initializer class → khác context |
| `differentDynamicPropertyMethodsSplitKeysEvenIfValuesSame` | `contextCustomizers` | Khác method nguồn, cùng value nhưng context khác |
| `mockOverrideChangesContextKeyAndBeanType` | `contextCustomizers` | Có override mock khác real, bean đúng là mock |
| `identicalExplicitNamedOverridesReuseCacheAcrossClasses` | Override metadata bằng nhau | Context mock được chia sẻ |
| `differentSetsOfMockOverridesNeedDifferentContexts` | Danh sách overrides | Thêm mock thứ hai → context khác |
| `differentFallbackMockFieldNamesCanSplitKeys` | Field fallback qualifier | Khác tên field có thể fragment cache |
| `samePropertyValueFromDifferentDeclarationPathsNeedNotShare` | Khai báo nguồn properties | Environment cùng value nhưng key khác |
| `markingContextDirtyEvictsAndRecreatesIt` | Eviction, **không phải key field** | Cùng marker nhưng context mới sau dirty |

**Test là kỹ thuật chứng minh cache identity**, không dựa vào log string hoặc elapsed time. Một assertion `isSameAs` đo đúng object identity của `ApplicationContext`, và `isNotSameAs` xác nhận có hơn một context instance. Cache hit/miss counters vẫn hữu ích khi tối ưu **toàn suite**, vì đây mới chỉ là vài marker cases.

**Về `markApplicationContextDirty`:** trong test thật, `@DirtiesContext` trên class/method được Spring test execution listeners thực hiện theo before/after modes. Ví dụ gọi method trực tiếp chỉ minh họa eviction trong một JUnit test mà không cần trông chờ thứ tự method. Không gọi dirty lên contexts dùng chung khác nếu không muốn tăng chi phí suite.

### 7.7. Chạy Maven

Yêu cầu JDK 17+, Maven. Trong thư mục `context-cache-key-demo`:

```bash
mvn test
mvn -Dtest=ContextCacheKeyTest test
```

Nếu có Maven Wrapper được thiết lập sẵn: `./mvnw test` hoặc `mvnw.cmd test` trên Windows.

Dự kiến **18 phương thức `@Test`**, tất cả PASS khi Spring Boot 3.5/Framework 6.2/Mockito test support hoạt động đúng. Mỗi test tự thực hiện so sánh trong method nên không phụ thuộc thứ tự JUnit. Một số methods tạo context mới theo đúng mục tiêu để kiểm key; vì vậy **tổng startup contexts của demo nhiều hơn một**, hoàn toàn hợp lý cho test đào tạo.

Mã ví dụ đã được rà soát theo API và semantics chính thức, **không phải tuyên bố đã chạy Maven trong quá trình biên soạn bài**. Khi áp dụng vào dự án thật, chạy trên JDK/CI và kiểm lại phiên bản Spring Framework/Boot cụ thể, đặc biệt nếu đang dùng Boot 4 và `@MockitoBean` với test infrastructure mới hơn.

## 8. Context cache khác object cache hoặc Testcontainers reuse

Ba lớp reuse độc lập:

| Lớp | Reuse cái gì? | Không tự làm |
|---|---|---|
| Spring TestContext cache | **ApplicationContext + Spring singleton beans** | Không tự rollback DB hoặc reset mutable state |
| JPA/Hibernate 1st/2nd-level cache | Entities/query data theo EntityManager/cache provider | Không quyết định TestContext cache key |
| Testcontainers container reuse/shared fixture | Docker process/port/database service | Không tự đảm bảo Spring context được reload khi container đổi URL |
| HTTP client connection pool | TCP connections | Không làm `@ActiveProfiles` giống nhau |
| Maven/Gradle build cache | Artifacts/compilation/test task outputs | Không chia sẻ JVM static Spring context giữa forks |

**Bẫy Testcontainers thường gặp:** mỗi test class khai một container riêng (port động), nhưng lại mong context reuse; hoặc ngược lại dùng shared `@DynamicPropertySource` method và context reuse trong khi container đã dừng. Cần đồng bộ **container lifecycle**, dữ liệu test, cách khai dynamic props và context reuse. Không tắt test isolation chỉ để đạt hit rate cao.

## 9. Đọc context cache stats và tối ưu dựa trên bằng chứng

### 9.1. Bật DEBUG cho cache

Ví dụ trong **`src/test/resources/application.properties`** của dự án thật:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Hoặc cấu hình log system tương đương cho test JVM. Spring TestContext ghi các thống kê như:
- `size`, `maxSize`;
- `hitCount`, `missCount`;
- `parentContextCount`;
- `failureCount` tùy phiên bản/log format.

Không assert nguyên văn log output vì format, hệ thống logging và thứ tự test có thể thay đổi. Mục tiêu là nhìn **số unique context keys**, tốc độ tăng miss, LRU evictions và những test classes tạo cấu hình lẻ.

### 9.2. Giới hạn maxSize và LRU

Spring Framework 6.2 có default maximum **32 contexts** trong static cache, có thể thay bằng system property:

```bash
mvn test -Dspring.test.context.cache.maxSize=64
```

Đặt đủ sớm trước khi cache được khởi tạo (system property trong JVM chạy tests). LRU loại/đóng contexts ít sử dụng khi vượt capacity; nếu suite dùng nhiều context keys hơn 32, có thể lặp **load → evict → reload**. Nhưng tăng maxSize quá cao có thể làm **tốn heap, threads, JDBC pools, sockets** vì mỗi context giữ resources. Giảm số keys không cần thiết thường tốt hơn chỉ tăng size.

### 9.3. Cache chỉ tồn tại trong một tiến trình JVM

TestContext cache là **static in-memory**, không phải distributed cache. Nếu Maven Surefire/Gradle/IDE chạy tests ở **nhiều forks/JVMs**, mỗi tiến trình có cache riêng. Ví dụ `reuseForks=false` hoặc fork-per-test-class có thể khiến bạn thấy quá nhiều context startups dù cấu hình cùng key. Trong một fork, các tests có thể share; **giữa forks thì không**.

Khi đo performance, ghi lại:
1. số JVM forks và test classes ở mỗi fork;
2. cache hits/misses;
3. thời gian startup context và tổng suite time;
4. memory/threads/external resources;
5. test isolation failures khi chạy parallel.

**Không khuyên tắt mọi fork/parallel một cách tuyệt đối:** có project nặng CPU hoặc integration I/O mà chạy nhiều forks cải thiện wall-clock time dù cache hit rate giảm. Cần đo theo CI profile, resources và sự ổn định.

### 9.4. Failure threshold khác LRU/eviction

Từ Spring Framework 6.1, `spring.test.context.failure.threshold` mặc định bằng **1**. Với một **failing context key**, framework thường không thử tải lại vô số lần trong cùng JVM mà báo lỗi preemptive ở lần sau để fail fast. Có thể cấu hình positive integer cao hơn để chẩn đoán, nhưng không nên biến điều đó thành cách giấu một cấu hình sai.

```bash
mvn test -Dspring.test.context.failure.threshold=2
```

Đây là **chính sách giới hạn thử load context lỗi**, không phải “cache thành công được reuse 2 lần”. Một `IllegalStateException` ghi rằng failure threshold exceeded **không tự là lỗi gốc**: hãy tìm failure **đầu tiên** của key đó trong logs để biết property, database, bean definition hoặc port nào đã làm context fail.

## 10. `@DirtiesContext`: dùng đúng lúc, không lạm dụng

`@DirtiesContext` báo cho TestContext rằng context **đã bị thay đổi ở mức không còn an toàn để dùng lại**. Spring loại entry liên quan khỏi cache theo before/after mode và hierarchy mode. Lần test sau với key tương đương cần load context mới.

```java
@SpringBootTest
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class ModifiesBeanDefinitionsTest {
}
```

Snippet không độc lập (cần imports/config), nêu rõ lớp test sẽ **làm context bẩn**. Chỉ cần dirty nếu bạn thay bean definitions/properties/runtime global state không reset an toàn. Không dùng `@DirtiesContext` sau mọi test chỉ vì dữ liệu test trong một `List` thay đổi — có thể reset list/dữ liệu đúng cách rẻ hơn rất nhiều.

### Những gì `@DirtiesContext` không làm

- Không tự xóa dữ liệu ở một database đã commit.
- Không rollback Kafka messages, cloud API calls, files đã ghi hoặc HTTP requests đã gửi.
- Không đảm bảo Testcontainers container được dừng/chạy lại theo mong muốn.
- Không fix race giữa parallel tests vốn dùng chung database.
- Không thay thế kiểm quyền truy cập, network isolation, transaction cleanup.

Một context mới còn có thể dùng **same external DB**; nếu dữ liệu cũ vẫn tồn tại, test mới vẫn bị ảnh hưởng. Cần test fixture isolation/cleanup, unique IDs, transaction boundaries hoặc container lifecycle phù hợp.

## 11. Test isolation khi context reuse

Context được cache nghĩa là các singleton có thể được dùng qua nhiều test methods/classes. Rủi ro:

| Thành phần mutable | Có thể leak sang test sau? | Cách cô lập thường hợp lý |
|---|---|---|
| Mockito stubbings/interactions | Có nếu reset không đúng/lifecycle custom | Mockito reset listener hoặc reset có chủ đích |
| In-memory List/Map/AtomicReference bean | Có | Reset `@BeforeEach`/`@AfterEach` hoặc per-test data ID |
| Database rows đã commit | Có | Truncate/test transaction, fixture cleanup/unique schema |
| Redis keys | Có | Prefix theo test ID, cleanup TTL |
| Kafka messages/consumer offsets | Có | Topic/group unique, explicit ack/cleanup |
| Clock/feature flags ở singleton | Có | Inject controlled clock, reset state |
| Thread pools/schedulers | Tasks có thể còn chạy | Await completion, shutdown đúng lifecycle |
| Spring `Environment` runtime mutation | Có, nếu shared context | Tránh sửa mutable environment giữa tests; context riêng khi cần |
| SecurityContext/MDC/ThreadLocal | Có thể leak theo thread nếu không clear | Security test listeners, explicit cleanup, executor propagation |
| HTTP mock server mappings | Có | Reset stubs/recorded requests từng test |

**Reuse không đồng nghĩa test thiếu độc lập.** Một test tốt có thể share application context và vẫn reset sạch business state. Nếu chỉ `@DirtiesContext` mới làm test pass, đó là tín hiệu nên tìm hiểu mutable global state, test order hoặc leaked async work.

### Khi `@MockitoBean` reset có hiệu lực

Spring Framework bean override support có `MockitoResetTestExecutionListener` để reset mock/spy trước hoặc sau test tùy cấu hình. Nó **không** đổi cache key giữa hai phương thức cùng annotation. Nếu bạn dùng manual Mockito mocks ngoài Spring context hoặc thay reset mode, cần xử lý lifecycle riêng.

Trong một base test:
- giữ tên mocked fields thống nhất;
- tách mocks bắt buộc với optional stubs;
- tránh mỗi test class thêm một mock chỉ để workaround setup;
- dùng slice tests nếu service/controller test không cần full app;
- giữ explicit qualifiers khi app có nhiều beans cùng interface.

**Đừng thay đổi role/qualifier của mock để cố “tạo context mới cho chắc”.** Điều đó làm suite chậm và thường che thiếu reset.

## 12. @DynamicPropertySource + bean override: trường hợp khó trong CI

Giả sử hai test classes đều cần database Testcontainers:

```java
abstract class PostgresIntegrationTestBase {

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                () -> sharedDatabaseJdbcUrl());
    }
}
```

Đây là snippet (helper giả định, cần định nghĩa container). Cần phân biệt:

- **Test class A** dùng base dynamic method; **Test class B** cũng kế thừa đúng method đó. Nếu mọi metadata khác giống nhau, có cơ hội share key.
- **Test class B** khai thêm một `@MockitoBean` hoặc `@TestPropertySource` → khác key dù database URL vẫn giống.
- **Container mới mỗi class** nhưng dùng cùng inherited method → context có thể bị reuse, giữ DataSource cũ. Đừng thiết kế container lifecycle trái với cache lifecycle.
- **Test A** gọi `@DirtiesContext` → entry bị loại, class B có thể phải khởi tạo lại context ngay cả khi key giống.
- **Maven Surefire fork mới** → static cache mới; dù key giống cũng không share object qua process.

Nếu muốn test một connection string khác, hãy cho context có **cấu hình thực sự khác** hoặc explicit dirty/recreate; không mong supplier runtime value vô tình tạo key mới. Với `@ServiceConnection` của Boot, cần kiểm connection details customization và lifecycle tương tự.

## 13. Checklist tối ưu hiệu năng dựa trên khóa cache

- [ ] Tôi biết context cache nằm trong **Spring TestContext**, không phải `ApplicationContextRunner`.
- [ ] Tôi đã đọc đủ các thành phần `MergedContextConfiguration`: locations, classes, initializers, customizers, loader, parent, profiles, property descriptors/properties, resourceBasePath.
- [ ] Tên test class đơn thuần **không phải cache key field**; annotations/config mới quyết định.
- [ ] Các integration tests cần reuse cùng **configuration classes** hoặc Boot bootstrap setup.
- [ ] Profiles được thống nhất khi môi trường thực sự giống nhau; không dùng mỗi test một profile vô lý.
- [ ] `@TestPropertySource` inline/file paths không bị biến thành nhiều variants không cần thiết.
- [ ] `@SpringBootTest(properties)` được khai ổn định giữa các classes.
- [ ] `@DynamicPropertySource` methods và resource lifecycle ổn định, không chỉ cùng supplier value tại một thời điểm.
- [ ] Bean overrides cùng mục đích dùng nhất quán `@MockitoBean` field name, type, qualifier, explicit name và mock config.
- [ ] Test classes cần real bean vs mock bean được **tách keys đúng**.
- [ ] Mock stubbings được reset đúng lifecycle, không làm dirty context vô cớ.
- [ ] Test data/DB/Redis/Kafka/async work được cô lập độc lập với cache context.
- [ ] `@DirtiesContext` chỉ dùng khi context thật sự không thể reuse an toàn.
- [ ] Tôi đo hits/misses qua logger `org.springframework.test.context.cache=DEBUG` và không suy từ millisecond duy nhất.
- [ ] Tôi kiểm `spring.test.context.cache.maxSize`, LRU, heap/resource cost.
- [ ] Tôi nhớ cache chỉ share **trong cùng JVM**, không qua test forks.
- [ ] Tôi tìm **lỗi khởi tạo đầu tiên** khi gặp context failure threshold exceeded.
- [ ] Với `@WebMvcTest`/`@DataJpaTest`/`@SpringBootTest`, tôi không giả định các test slices đều share context.
- [ ] Test ngoài framework (Mockito thuần, JUnit unit tests) không cần Spring context khi không cần.
- [ ] Tôi không “tối ưu” bằng cách xóa annotations tạo bean graph cần thiết.
- [ ] Với real external resources, fixture lifecycle và caching phải tương thích.
- [ ] Tôi chạy `mvn test`/CI với cùng test forks/profile/JVM options dự kiến.

**Kết luận:** Spring context cache được phân biệt bởi **cấu hình được merged**, đặc biệt bốn nhóm cần nhớ là **classes/configuration, active profiles, test properties và context customizers chứa bean overrides/dynamic properties**. Hai test khác tên có thể share, hai test cùng `@SpringBootTest` có thể miss. Tối ưu hiệu năng không phải xóa tất cả khác biệt: **chỉ chuẩn hóa những cấu hình thật sự tương đương**, đồng thời giữ mỗi test độc lập về dữ liệu và side effects. Dùng cache stats + context identity để chứng minh thay vì đoán.

### Tài liệu chính thức

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [Spring Framework 6.2 — @TestPropertySource](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-testpropertysource.html)
- [Spring Framework 6.2 — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dynamicpropertysource.html)
- [Spring Framework 6.2 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html)
- [Spring Framework 6.2 — MergedContextConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/MergedContextConfiguration.html)
- [Spring Framework 6.2 — TestContextManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/TestContextManager.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
