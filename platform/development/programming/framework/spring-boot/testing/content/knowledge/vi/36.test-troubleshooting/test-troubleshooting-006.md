# Chẩn đoán lỗi kiểm thử — Nhiều bean cùng type, qualifier sai hoặc bean override không đúng

## 1. Vì sao lỗi chỉ xuất hiện khi chạy Spring Boot tests?

Một ứng dụng Spring Boot có thể đăng ký nhiều beans cùng implement một interface. Đây thường là thiết kế đúng: nhiều payment gateways, email senders, tax policies, object mappers hoặc HTTP clients. Vấn đề xảy ra khi Spring cần inject **một** bean nhưng thấy nhiều ứng viên, qualifier không khớp, hoặc một test muốn mock một bean nhưng lại override **nhầm bean** hay vô tình tạo thêm bean mới.

Ví dụ:

```java
public interface TaxPolicy {
    BigDecimal tax(BigDecimal subtotal);
}

@Component("domesticTaxPolicy")
class DomesticTaxPolicy implements TaxPolicy { /* ... */ }

@Component("exportTaxPolicy")
class ExportTaxPolicy implements TaxPolicy { /* ... */ }
```

Hai beans đều có type `TaxPolicy`. Một injection không đủ thông tin:

```java
@Service
class PricingService {
    PricingService(TaxPolicy policy) {
        // Khi có hai ứng viên và không có chỉ dấu khác,
        // Spring có thể báo NoUniqueBeanDefinitionException.
    }
}
```

Trường hợp khác: production code inject `@Qualifier("domesticTaxPolicy")` chính xác, nhưng trong test khai:

```java
@MockitoBean(name = "domestikTaxPolicy") // Sai chính tả.
TaxPolicy taxPolicy;
```

Với chiến lược mặc định của `@MockitoBean` là **REPLACE_OR_CREATE**, một tên không tồn tại có thể tạo ra một mock bean mới. Test context **vẫn có thể khởi động**, nhưng service vẫn dùng bean `domesticTaxPolicy` thật, không phải mock mà test vừa stub. Đây là dạng **false-positive hoặc test thất bại khó hiểu** nguy hiểm hơn lỗi startup rõ ràng.

Bài học tập trung vào ba câu hỏi:

1. **Bean nào thực sự được đăng ký** và đang là ứng viên injection?
2. **Spring đã chọn bean nào, vì sao?** `@Qualifier`, `@Primary`, `@Fallback`, bean name, generics hay profile?
3. **Test đã override chính xác bean mà collaborator dùng chưa?** Hay nó chỉ tạo một mock cô lập, không hề được gọi?

### Sau bài này bạn có thể

- Phân biệt `NoUniqueBeanDefinitionException`, `NoSuchBeanDefinitionException`, `BeanDefinitionOverrideException` và test mock không có interactions.
- Phân tích injection by-type/by-qualifier/by-name, bao gồm ưu tiên của `@Primary` và `@Fallback`.
- Dùng `@MockitoBean(name=..., enforceOverride=true)` để fail fast nếu mock sai đích.
- Phân biệt `@MockitoBean`, `@MockitoSpyBean`, `@TestBean`, Mockito `@Mock` và `@TestConfiguration`.
- Viết integration tests xác nhận **bean identity**, type, số candidates và luồng service thật.
- Kiểm các lỗi startup có chủ đích bằng `ApplicationContextRunner` mà không làm toàn bộ test suite đỏ.
- Biết khi nào cần `@WebMvcTest` và khi nào phải dùng `@SpringBootTest`.
- Giảm context cache fragmentation do names/qualifiers không nhất quán.
- Chẩn đoán proxy/transaction/conditional bean/profile errors mà không bật global bean overriding để che vấn đề.

## 2. Bản đồ triệu chứng → nguyên nhân → bằng chứng

| Triệu chứng | Nguyên nhân phổ biến | Cần kiểm trước |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException`: expected single matching bean, found 2 | Injection một type có nhiều ứng viên, không có discriminator | Danh sách bean names/types; constructor qualifier |
| `NoSuchBeanDefinitionException`: no bean named ... | Qualifier/name sai, package không scan, profile/condition loại bean | Bean names hiện có; `@Profile`, `@Conditional...` |
| `UnsatisfiedDependencyException` | Bean cần một dependency không resolve được; thường là wrapper | **Root cause** bên trong: no unique, no bean, create failure |
| `BeanDefinitionOverrideException` | Hai definitions trùng bean name và Spring Boot không cho ghi đè | Duplicate `@Bean`/`@Component`, test imports |
| `BeanCreationException` | Bean factory/injection/config thất bại; wrapper rộng | Chỗ `Caused by` cuối và condition report |
| Mockito “Wanted but not invoked” | Stub/verify một mock không được service sử dụng | `context.getBean(name)`; collaborator injection identity |
| Stub trả null dù đã `when(...).thenReturn(...)` | Có thể gọi real bean, mock khác hoặc args không khớp | Verify mock instance, method args, overloaded methods |
| `@MockitoSpyBean` không tìm thấy target | `WRAP` đòi bean hiện hữu, chọn đúng một candidate | Name/qualifier, bean scope, TestContext configuration |
| Unit test `@Mock` hoạt động, `@SpringBootTest` vẫn dùng real bean | Mockito `@Mock` không register thành Spring bean | Dùng `@MockitoBean` khi cần override context |
| Test chạy riêng pass, cả suite fail | Context cache/profile/mock reset/shared mutable state | Cache keys, mock fields, parallel tests, data isolation |
| Slice test thiếu service bean | `@WebMvcTest` chỉ nạp MVC slice | `@MockitoBean` collaborator hoặc `@Import` vừa đủ |
| Một app bean tồn tại ở production nhưng test không thấy | Config scan, active profiles, conditional auto-config khác | Effective profiles, test properties, component scan |

**Không sửa bằng cách bật `spring.main.allow-bean-definition-overriding=true` ngay lập tức.** Cờ đó có thể che việc trùng bean name, khiến behavior khác production. Trước tiên tìm chính xác hai definitions và quyết định xem muốn **chọn một bean**, **thay một bean**, hay **điều chỉnh component scan**.

## 3. Spring chọn bean bằng cách nào?

### 3.1. Bean type và bean name không đồng nghĩa

Spring đăng ký bean definitions với **tên** và **type**. Ví dụ:

```java
@Component("domesticTaxPolicy")
public class DomesticTaxPolicy implements TaxPolicy {
    // ...
}
```

Bean name là `domesticTaxPolicy`; concrete type là `DomesticTaxPolicy`; nó cũng assignable to `TaxPolicy`. Lời gọi:

```java
context.getBean("domesticTaxPolicy", TaxPolicy.class);
```

tìm theo **tên xác định** và kiểm compatible type. Ngược lại:

```java
context.getBean(TaxPolicy.class);
```

tìm một bean duy nhất theo type; nếu có hai beans cùng type và không có lựa chọn đơn nhất, nó có thể ném `NoUniqueBeanDefinitionException`.

Nhưng **autowiring một field/constructor** có thêm thông tin injection point, qualifier, primary/fallback, parameter name, generics... nên không phải lúc nào cũng y hệt `getBean(Type.class)`. Không kết luận service tiêm sai chỉ vì `getBean(TaxPolicy.class)` báo ambiguity; phải xem injection metadata của service.

### 3.2. @Qualifier để chỉ rõ semantics

```java
public PricingService(
        @Qualifier("domesticTaxPolicy") TaxPolicy domestic,
        @Qualifier("exportTaxPolicy") TaxPolicy export) {
    this.domestic = domestic;
    this.export = export;
}
```

Chọn bean theo type **kết hợp qualifier**. Tên bean cũng có thể được xem là fallback qualifier value. `@Qualifier` về bản chất là **lọc các ứng viên by-type**, không phải API thuần túy truy cập bean ID giống `@Resource(name=...)`.

Nếu qualifier không khớp bean type/name/qualifier metadata, injection thất bại. Nếu nhiều beans cùng mang **một** qualifier semantic, việc yêu cầu một bean vẫn có thể ambiguous; qualifier không bắt buộc duy nhất.

### 3.3. @Primary: default bean khi không chỉ rõ

```java
@Component("domesticTaxPolicy")
@Primary
class DomesticTaxPolicy implements TaxPolicy {
    // ...
}
```

Khi injection một `TaxPolicy` không có qualifier và hai beans hợp lệ, `@Primary` ưu tiên domestic. Nhưng một injection `@Qualifier("exportTaxPolicy")` vẫn có thể chọn export: **explicit qualifier filtering** không bị một primary unrelated bean thay thế.

Không đánh dấu mọi bean `@Primary`: nhiều primary candidates có thể vẫn ambiguous. Không dùng primary để tránh sửa một qualifier sai trong code đang thật sự cần **export** policy.

### 3.4. @Fallback của Spring Framework 6.2

`@Fallback` có thể đánh dấu các beans là lựa chọn dự phòng:

```java
@Component("exportTaxPolicy")
@Fallback
class ExportTaxPolicy implements TaxPolicy {
    // ...
}
```

Nếu còn đúng một regular candidate, ứng viên regular có thể được ưu tiên; đây là cơ chế mới của Spring Framework 6.2. **Snippet này không thuộc project runnable** vì project muốn có hai ứng viên ngang nhau để minh họa ambiguity. Cần đọc version-specific API khi dùng ở Boot 3.5/Framework 6.2.

### 3.5. Tên parameter/field cũng có thể là tín hiệu

Khi không có qualifier/primary/fallback rõ, Spring có thể dùng tên injection point để match bean name:

```java
public SomeService(TaxPolicy domesticTaxPolicy) {
    // Có thể match bean tên domesticTaxPolicy.
}
```

Đừng dựa hoàn toàn vào may mắn tên parameter: Java cần `-parameters` compiler flag để Spring đọc parameter names đáng tin. Spring 6.2 có fast shortcut cho name match khi không có điều kiện ưu tiên khác. Đổi parameter name lúc refactor có thể đổi behavior của DI nếu đang dựa vào implicit matching.

**Khuyến nghị:** Khi business logic yêu cầu chính xác một trong nhiều implementations, ghi `@Qualifier` trên constructor parameter. Tên bean nên rõ và ổn định; dùng `@Primary` cho default chung hợp lý; không phụ thuộc một tên biến tình cờ.

### 3.6. Inject tất cả beans khi thật sự cần nhiều candidates

```java
@Autowired
Map<String, TaxPolicy> allPolicies;

@Autowired
List<TaxPolicy> policyList;
```

Spring có thể inject collection/map chứa nhiều beans assignable cùng type; map key thường là bean names. Đó là yêu cầu **nhiều bean**, không còn ambiguity của injection **một** bean. Có thể dùng `ObjectProvider<TaxPolicy>` để truy vấn lazily hoặc stream, nhưng `getObject()` trên một type có nhiều ứng viên vẫn phải giải quyết ambiguity; nó không tự chọn đúng bean nghiệp vụ.

### 3.7. Generics và điều kiện tạo bean

Spring hỗ trợ generic types như một hình thức qualifier trong nhiều kịch bản: `Repository<Order>` và `Repository<Customer>` có thể khác nhau dù cùng raw type. Ngoài ra `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` và component-scan filters quyết định **bean có được đăng ký không**. Nếu test bật profile khác, cùng source code có thể cho một tập candidates khác.

## 4. Chẩn đoán bằng ApplicationContext thay vì đoán

Nếu context **khởi động được**, đọc metadata từ chính context trong test:

```java
Map<String, TaxPolicy> candidates =
        context.getBeansOfType(TaxPolicy.class);

assertThat(candidates).containsKeys(
        "domesticTaxPolicy", "exportTaxPolicy");

TaxPolicy actual =
        context.getBean("domesticTaxPolicy", TaxPolicy.class);
```

Dùng `ApplicationContext.getBeanNamesForType(TaxPolicy.class)` khi muốn chỉ danh sách tên mà không cần lấy tất cả instances. Với các beans lazy/`FactoryBean`, query behavior có thể phụ thuộc type prediction và factory initialization; không dùng các probes này tùy tiện ở production startup.

Với beans đã inject vào collaborators, kiểm:
- Injection point nằm ở **constructor nào**, parameter có `@Qualifier` không?
- Có hai beans cùng type nhưng chỉ một `@Primary` hay không?
- Bean name đúng chính tả, case và package scanning?
- Bean có bị `@Profile`/`@ConditionalOnMissingBean` loại khỏi test context?
- Bean là AOP proxy hay direct object? Kiểm target/proxy nếu cần.
- Test đang lấy bean từ **cùng ApplicationContext** hay parent/child/isolated runner?
- Override field được attach ở test class/superclass nào? Có meta annotation khác không?

**Đừng chỉ nhìn field test có `@Autowired SomeType` rồi đoán service cũng dùng cùng instance**. Một test bean field và một constructor dependency có thể có qualifiers khác nhau.

## 5. @MockitoBean: thay, tạo, hay thay nhầm?

Spring Framework 6.2 định nghĩa ba chiến lược của bean override infrastructure:

| Strategy | Công dụng | Khi target không tồn tại |
| --- | --- | --- |
| `REPLACE_OR_CREATE` | Thay nếu có; không có thì tạo mới | Tạo bean mới |
| `REPLACE` | Chỉ thay bean hiện hữu | Fail |
| `WRAP` | Bao bọc bean hiện hữu | Fail, yêu cầu target rõ ràng |

`@MockitoBean` mặc định dùng **REPLACE_OR_CREATE**. `@MockitoBean(enforceOverride=true)` buộc **REPLACE**. `@MockitoSpyBean` dùng **WRAP**, cần lựa chọn đúng bean hiện hữu, thường là singleton.

### 5.1. Override theo tên rõ ràng, fail fast nếu sai

```java
@MockitoBean(
    name = "domesticTaxPolicy",
    enforceOverride = true)
TaxPolicy domesticTaxPolicy;
```

Đây là cách an toàn khi có nhiều beans cùng type: chọn **đúng bean name**, và nếu nó biến mất/đổi tên thì test setup fail thay vì tự tạo ghost mock.

Trong bài mẫu, `PricingService` inject bean tên `domesticTaxPolicy`, nên stubbing/verification của field này có ý nghĩa thực.

### 5.2. Fallback qualifier từ tên field

Nếu có nhiều candidates, `@MockitoBean` trên field có thể suy luận mục tiêu theo **field type và qualifier**. Khi không khai `@Qualifier`, tên field được dùng làm **fallback qualifier**:

```java
@MockitoBean(enforceOverride = true)
TaxPolicy exportTaxPolicy;
```

Field name `exportTaxPolicy` khớp bean name, nên override tương ứng có thể được chọn. Dù vậy, để tránh phụ thuộc tên biến trong critical tests, bạn có thể khai `name="exportTaxPolicy"` rõ ràng.

**Cache implication:** qualifier và field name còn tham gia Spring TestContext cache key. Hai test classes cùng mock một bean nhưng khai field names khác có thể khởi tạo hai contexts không cần thiết. Chuẩn hóa names/qualifiers bằng shared base hoặc composed annotation khi tương đương.

### 5.3. Sai tên có thể tạo thêm bean mà không sửa service

```java
@MockitoBean(name = "domestikTaxPolicy")
TaxPolicy typoMock;
```

Nếu `domestikTaxPolicy` chưa tồn tại, chiến lược mặc định có thể **tạo mới**. Context lúc này có cả real domestic/export và typo mock. Service vẫn inject `@Qualifier("domesticTaxPolicy")` nên stubbing typo mock **không ảnh hưởng service**.

Một test chỉ assert “context loads” sẽ xanh giả; một test verify đúng service behavior có thể thất bại hoặc log `Wanted but not invoked`. Bài mẫu có một JUnit test riêng **chứng minh ghost mock được tạo nhưng không được business service sử dụng**.

### 5.4. @MockitoSpyBean khác @MockitoBean

```java
@MockitoSpyBean(name = "domesticTaxPolicy")
TaxPolicy domesticTaxPolicy;
```

Spy **giữ hành vi thật** khi method không được stub. Khi stubbing spy, ưu tiên:

```java
doReturn(new BigDecimal("2.00"))
        .when(domesticTaxPolicy)
        .tax(new BigDecimal("100.00"));
```

`when(spy.realMethod()).thenReturn(...)` có thể **gọi method thật ngay lúc stubbing**, gây side effect hoặc exception. `doReturn(...).when(spy)...` tránh điều này. Nếu bean có Spring AOP proxy (`@Transactional`, `@Cacheable`, `@Retryable`), spy/target/proxy relationships phức tạp hơn; verification có thể cần kiểm đúng layer và xử lý advice. Bài mẫu **không có AOP** để ngăn lỗi này nhiễu mục tiêu chính.

### 5.5. Chỉ inject Mockito @Mock không override Spring

```java
@Mock
TaxPolicy domesticTaxPolicy;
```

Mockito `@Mock` tạo mock cho một unit test; nó **không tự đăng ký mock vào ApplicationContext**. `PricingService` Spring bean vẫn sử dụng real `TaxPolicy`. Nếu muốn unit test thuần không context, dùng Mockito `@InjectMocks` hoặc gọi constructor với mock. Nếu muốn thay collaborator **bên trong Spring context**, dùng `@MockitoBean`.

### 5.6. @TestBean cho fake cố định

Spring TestContext còn có `@TestBean` để thay bean bằng instance từ static factory:

```java
// Snippet riêng, không thuộc Maven project runnable.
@TestBean(
    name = "domesticTaxPolicy",
    methodName = "fakeDomestic",
    enforceOverride = true)
TaxPolicy domesticTaxPolicy;

static TaxPolicy fakeDomestic() {
    return subtotal -> new BigDecimal("2.00");
}
```

Dùng khi muốn một deterministic fake **không cần Mockito stubbing/verification**. Cần static factory đúng kiểu, test context support và bean override đúng tên. Khác với đăng ký một `@Bean` cùng tên trong `@TestConfiguration` rồi bật overriding toàn cục.

### 5.7. Scope và FactoryBean

Override infrastructure được thiết kế chủ yếu cho singleton; các trường hợp non-singleton/prototype/custom scopes và `FactoryBean` có thể có semantics đặc biệt theo Spring Framework version/override strategy. Đừng giả định việc override một FactoryBean làm bean factory gốc còn nguyên. Với các beans scoped, ưu tiên test scope phù hợp và kiểm docs version, không ép biến mọi dependency thành singleton chỉ để mock.

## 6. Phân biệt lỗi injection và lỗi trùng bean definition

**Lỗi nhiều beans cùng type**:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
domesticTaxPolicy, exportTaxPolicy
```

Nguyên nhân: hai beans **khác tên** cùng type, injection thiếu lựa chọn. Sửa bằng qualifier, primary/fallback có ý nghĩa, thay thiết kế injection hoặc inject collection.

**Lỗi hai definitions cùng tên**:

```text
BeanDefinitionOverrideException:
Invalid bean definition with name 'domesticTaxPolicy'
```

Nguyên nhân: hai bean definitions **đè cùng name**, Spring Boot thường không cho overriding mặc định. Sửa bằng đổi bean name, bỏ duplicate import/scan, hoặc dùng TestContext `@MockitoBean`/`@TestBean` để override có chủ đích. Không bật global flag để trốn lỗi.

**Lỗi qualifier chỉ đến bean không tồn tại**:

```text
UnsatisfiedDependencyException
  caused by NoSuchBeanDefinitionException:
  No qualifying bean of type 'TaxPolicy' ...
```

Nguyên nhân có thể là `@Qualifier("wrongName")`, wrong profile, slice không load target bean, hoặc type không assignable. Không sửa bằng `@Primary`: primary chỉ hoạt động trong những candidates hiện có.

**Các log trên là ví dụ minh họa**, không phải exact exception message từ project dưới đây; log thực tùy Spring version, bean names và wrapping exceptions.

## 7. @Primary, @Qualifier, @Bean name: chọn giải pháp theo nhu cầu

| Nhu cầu | Giải pháp | Lưu ý |
| --- | --- | --- |
| Business code luôn cần **một** implementation cụ thể | `@Qualifier("domesticTaxPolicy")` tại constructor | Rõ semantics, ít lệ thuộc parameter names |
| Ứng dụng có default implementation cho injection không qualified | `@Primary` ở default bean | Đừng thêm nhiều primary |
| Một implementation chỉ là fallback | `@Fallback` (Spring 6.2+) | Chỉ khi còn một regular candidate rõ |
| Cần tất cả implementations | `List<T>`, `Map<String,T>` | Inject collection thay single bean |
| Cần optional/lazy lookup | `ObjectProvider<T>` | `getObject()` vẫn có thể ambiguous |
| Muốn bean theo name chính xác | `@Resource(name="...")` hoặc `getBean(name,type)` | Kiểm type compatibility |
| Test cần mock một named bean | `@MockitoBean(name=...,enforceOverride=true)` | Tránh tạo ghost bean |
| Test cần giữ real behavior, sửa một phương thức | `@MockitoSpyBean` + `doReturn` | Chú ý side effects/AOP |
| Test cần fake do static factory tạo | `@TestBean` | Fail fast bằng enforceOverride |
| Bean chỉ tồn tại theo profile | `@ActiveProfiles`/test properties đúng | Đừng bắt mock bean không tồn tại nếu fail fast |
| Nhiều beans bị tạo vì duplicate scan | Sửa `@ComponentScan`/`@Import` | Không bật global overriding để che vấn đề |

## 8. Project mẫu runnable — Spring Boot 3.5.0, Java 17

Ứng dụng báo giá có hai `TaxPolicy` beans **cùng interface nhưng khác tên**. `PricingService` dùng explicit constructor qualifiers, vì vậy app khởi động ổn định; test dùng `ApplicationContextRunner` tái hiện lỗi ambiguous/missing qualifier trong một context **cố ý lỗi**, không làm hỏng toàn bộ suite.

```text
bean-diagnosis-demo/
├── pom.xml
└── src/
    ├── main/java/example/diagnosis/
    │   ├── BeanDiagnosticsApplication.java
    │   ├── TaxPolicy.java
    │   ├── DomesticTaxPolicy.java
    │   ├── ExportTaxPolicy.java
    │   ├── PriceQuote.java
    │   └── PricingService.java
    └── test/java/example/diagnosis/
        ├── BeanCandidatesTest.java
        ├── DomesticPolicyOverrideTest.java
        ├── ExportPolicyOverrideTest.java
        ├── DomesticPolicySpyTest.java
        ├── PhantomOverrideTest.java
        └── MisconfiguredContextTest.java
```

Không cần HTTP server, database, Docker hoặc external network. `spring-boot-starter` và `spring-boot-starter-test` đủ cho JUnit, Spring TestContext/Mockito, AssertJ và `ApplicationContextRunner`.

### Các bài test có nhiệm vụ gì?

| Class | Loại | Số JUnit methods | Kiểm điều gì |
| --- | --- | ---: | --- |
| `BeanCandidatesTest` | Spring integration | 4 | Hai beans cùng type, ambiguity, qualifiers đúng, business behavior |
| `DomesticPolicyOverrideTest` | Spring + named mock | 3 | Chỉ mock domestic đúng tên, export thật không bị thay |
| `ExportPolicyOverrideTest` | Spring + field fallback | 2 | Fallback field name chọn export, domestic vẫn thật |
| `DomesticPolicySpyTest` | Spring + spy | 2 | Spy dùng real/stubbed behavior, không gọi real method lúc stub |
| `PhantomOverrideTest` | Spring + accidental bean create | 1 | Wrong-name mock tồn tại nhưng service không gọi |
| `MisconfiguredContextTest` | Isolated runner | 2 | Ambiguous unqualified injection và missing qualifier startup |
| **Tổng** | | **14** | 14 JUnit methods dự kiến |

**Không đưa một class `@SpringBootTest` cố ý lỗi vào Maven suite.** Nếu tạo test khởi động Spring với missing bean, các assertions chưa chạy được và Maven chỉ báo context load failed. `ApplicationContextRunner` là cách phù hợp để assert lỗi startup như một **kết quả mong đợi**.

## 9. pom.xml

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>bean-diagnosis-demo</artifactId>
    <version>1.0.0</version>

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
</project>
```

Spring Boot parent/BOM quản lý phiên bản Spring Framework (6.2.x trong Boot 3.5), JUnit Jupiter, Mockito và AssertJ. Dùng `org.springframework.test.context.bean.override.mockito.MockitoBean` thay cho `@MockBean` cũ đã deprecated trong Boot 3.4/3.5.

## 10. Main class và interface TaxPolicy

`src/main/java/example/diagnosis/BeanDiagnosticsApplication.java`:

```java
package example.diagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanDiagnosticsApplication.class, args);
    }
}
```

`src/main/java/example/diagnosis/TaxPolicy.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;

@FunctionalInterface
public interface TaxPolicy {
    BigDecimal tax(BigDecimal subtotal);
}
```

`TaxPolicy` có một abstract method. Điều này cũng cho phép `ApplicationContextRunner` diagnostic configs tạo lightweight lambdas.

## 11. Hai beans cùng type: DomesticTaxPolicy và ExportTaxPolicy

`src/main/java/example/diagnosis/DomesticTaxPolicy.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Component;

@Component("domesticTaxPolicy")
public class DomesticTaxPolicy implements TaxPolicy {
    @Override
    public BigDecimal tax(BigDecimal subtotal) {
        return subtotal.multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
```

`src/main/java/example/diagnosis/ExportTaxPolicy.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Component;

@Component("exportTaxPolicy")
public class ExportTaxPolicy implements TaxPolicy {
    @Override
    public BigDecimal tax(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.ZERO)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
```

Đây là **hai beans hợp lệ** cùng interface. Không có `@Primary`: bài cần giữ ambiguity cho test `getBean(TaxPolicy.class)`. Nhưng khi service dùng qualifiers chính xác, ứng dụng chạy bình thường.

- Với subtotal `100.00`, domestic tax là `10.00`.
- Với subtotal `100.00`, export tax là `0.00`.
- Mỗi policy trả tax có scale 2 theo `RoundingMode.HALF_UP`.

Không dùng implementation khác từ mạng hoặc đọc environment để ví dụ luôn deterministic.

## 12. PriceQuote và PricingService

`src/main/java/example/diagnosis/PriceQuote.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;

public record PriceQuote(
        BigDecimal subtotal,
        BigDecimal tax,
        BigDecimal total,
        String region) {
}
```

`src/main/java/example/diagnosis/PricingService.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final TaxPolicy domesticPolicy;
    private final TaxPolicy exportPolicy;

    public PricingService(
            @Qualifier("domesticTaxPolicy")
            TaxPolicy domesticPolicy,
            @Qualifier("exportTaxPolicy")
            TaxPolicy exportPolicy) {
        this.domesticPolicy = domesticPolicy;
        this.exportPolicy = exportPolicy;
    }

    public PriceQuote quote(
            BigDecimal subtotal,
            boolean exportOrder) {

        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }

        TaxPolicy selected =
                exportOrder ? exportPolicy : domesticPolicy;

        BigDecimal tax = Objects.requireNonNull(
                selected.tax(subtotal),
                "tax must not be null");

        return new PriceQuote(
                subtotal,
                tax,
                subtotal.add(tax),
                exportOrder ? "EXPORT" : "DOMESTIC");
    }
}
```

### Vì sao constructor injection có qualifier ở **cả hai** parameters?

Nếu bỏ hai qualifiers, Spring thấy hai candidates `TaxPolicy`. Parameter names `domesticPolicy`/`exportPolicy` không trùng với bean names `domesticTaxPolicy`/`exportTaxPolicy`, nên không thể dựa vào fallback match. Context có thể fail với `NoUniqueBeanDefinitionException` khi tạo `PricingService`.

Có người sửa tạm bằng `@Primary` cho domestic, nhưng như vậy parameter export cũng có thể nhận domestic nếu thiếu qualifier — lỗi nghiệp vụ **nguy hiểm**. Sửa đúng là chỉ rõ hai dependencies với qualifiers tương ứng.

### Business assertions

- `quote(new BigDecimal("100.00"), false)` ⇒ subtotal 100.00, tax 10.00, total 110.00, region DOMESTIC.
- `quote(new BigDecimal("100.00"), true)` ⇒ tax 0.00, total 100.00, region EXPORT.
- Input null/negative ⇒ `IllegalArgumentException`.
- Mock tax method trả null ⇒ `NullPointerException("tax must not be null")` vì service dùng `Objects.requireNonNull`.

## 13. BeanCandidatesTest.java — kiểm candidates và resolution

`src/test/java/example/diagnosis/BeanCandidatesTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BeanCandidatesTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    PricingService pricingService;

    @Autowired
    @Qualifier("domesticTaxPolicy")
    TaxPolicy domestic;

    @Autowired
    @Qualifier("exportTaxPolicy")
    TaxPolicy export;

    @Test
    void twoTaxPoliciesExistUnderDistinctNames() {
        Map<String, TaxPolicy> beans =
                context.getBeansOfType(TaxPolicy.class);

        assertThat(beans).containsOnlyKeys(
                "domesticTaxPolicy",
                "exportTaxPolicy");
    }

    @Test
    void unqualifiedTypeLookupIsAmbiguous() {
        assertThrows(NoUniqueBeanDefinitionException.class,
                () -> context.getBean(TaxPolicy.class));
    }

    @Test
    void qualifiersSelectExpectedImplementations() {
        assertThat(domestic)
                .isInstanceOf(DomesticTaxPolicy.class);
        assertThat(export)
                .isInstanceOf(ExportTaxPolicy.class);

        assertThat(context.getBean(
                "domesticTaxPolicy", TaxPolicy.class))
                .isSameAs(domestic);
        assertThat(context.getBean(
                "exportTaxPolicy", TaxPolicy.class))
                .isSameAs(export);
    }

    @Test
    void serviceRoutesToCorrectPolicyByQualifiers() {
        PriceQuote local = pricingService.quote(
                new BigDecimal("100.00"), false);
        PriceQuote overseas = pricingService.quote(
                new BigDecimal("100.00"), true);

        assertThat(local.tax())
                .isEqualByComparingTo("10.00");
        assertThat(local.total())
                .isEqualByComparingTo("110.00");
        assertThat(local.region()).isEqualTo("DOMESTIC");

        assertThat(overseas.tax())
                .isEqualByComparingTo("0.00");
        assertThat(overseas.total())
                .isEqualByComparingTo("100.00");
        assertThat(overseas.region()).isEqualTo("EXPORT");
    }
}
```

**4 JUnit methods.** Test thứ hai cố ý tạo exception bằng `ApplicationContext.getBean(Type.class)`, nhưng **bắt exception bằng assertThrows**, vì vậy chính test đó **PASS** khi hành vi ambiguity đúng.

Điểm học được: hai beans cùng type là hợp lệ; lỗi chỉ xuất hiện khi một dependency **cần một lựa chọn** mà không đủ discriminator.

## 14. DomesticPolicyOverrideTest.java — named override đúng đích

`src/test/java/example/diagnosis/DomesticPolicyOverrideTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DomesticPolicyOverrideTest {

    @MockitoBean(
        name = "domesticTaxPolicy",
        enforceOverride = true)
    TaxPolicy domesticTaxPolicy;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void namedMockReplacesOnlyDomesticBean() {
        assertThat(context.getBean("domesticTaxPolicy"))
                .isSameAs(domesticTaxPolicy);

        assertThat(Mockito.mockingDetails(
                domesticTaxPolicy).isMock()).isTrue();

        assertThat(context.getBean("exportTaxPolicy"))
                .isInstanceOf(ExportTaxPolicy.class);
    }

    @Test
    void pricingServiceUsesTheNamedMock() {
        BigDecimal subtotal = new BigDecimal("100.00");

        when(domesticTaxPolicy.tax(subtotal))
                .thenReturn(new BigDecimal("7.50"));

        PriceQuote quote = pricingService.quote(
                subtotal, false);

        assertThat(quote.tax())
                .isEqualByComparingTo("7.50");
        assertThat(quote.total())
                .isEqualByComparingTo("107.50");

        verify(domesticTaxPolicy).tax(subtotal);
    }

    @Test
    void exportPolicyRemainsRealAndDoesNotCallMock() {
        PriceQuote quote = pricingService.quote(
                new BigDecimal("100.00"), true);

        assertThat(quote.tax())
                .isEqualByComparingTo("0.00");
        assertThat(quote.region()).isEqualTo("EXPORT");

        verifyNoInteractions(domesticTaxPolicy);
    }
}
```

**3 JUnit methods**. `@MockitoBean` làm context của lớp này khác context không mock; test suite không giả định hai contexts sẽ share một bean graph. Nhờ `enforceOverride=true`, nếu đổi tên production bean `domesticTaxPolicy` mà không sửa test, quá trình load context **phải lỗi ngay** thay vì sinh ghost mock.

### Kiểm mock identity quan trọng hơn chỉ check stubbing

Lời gọi:

```java
context.getBean("domesticTaxPolicy")
```

phải trả đúng instance được field `domesticTaxPolicy` giữ. Service sau đó gọi same named bean do qualifier constructor. Với bean proxied/AOP, identity có thể phức tạp, nên cần kiểm phù hợp proxy; ví dụ này dùng simple unproxied component.

### Mock reset

Spring TestContext hỗ trợ reset Mockito bean mocks giữa test methods (default `MockReset.AFTER`). Mỗi test tự stub/verify; không dựa vào trạng thái của method khác. Nếu bật JUnit parallel tests chia sẻ same mock context, có thể cần isolation vì reset/stubbing đồng thời có thể race.

## 15. ExportPolicyOverrideTest.java — fallback field name

`src/test/java/example/diagnosis/ExportPolicyOverrideTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ExportPolicyOverrideTest {

    // Không khai name: field name là fallback qualifier.
    @MockitoBean(enforceOverride = true)
    TaxPolicy exportTaxPolicy;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void mockFieldNameSelectsExportBean() {
        assertThat(context.getBean("exportTaxPolicy"))
                .isSameAs(exportTaxPolicy);
        assertThat(context.getBean("domesticTaxPolicy"))
                .isInstanceOf(DomesticTaxPolicy.class);
    }

    @Test
    void exportMockDoesNotAffectDomesticCalculations() {
        BigDecimal subtotal = new BigDecimal("100.00");

        when(exportTaxPolicy.tax(subtotal))
                .thenReturn(new BigDecimal("5.00"));

        PriceQuote exportQuote = pricingService.quote(
                subtotal, true);
        PriceQuote domesticQuote = pricingService.quote(
                subtotal, false);

        assertThat(exportQuote.tax())
                .isEqualByComparingTo("5.00");
        assertThat(exportQuote.total())
                .isEqualByComparingTo("105.00");
        assertThat(domesticQuote.tax())
                .isEqualByComparingTo("10.00");
        assertThat(domesticQuote.total())
                .isEqualByComparingTo("110.00");

        verify(exportTaxPolicy).tax(subtotal);
    }
}
```

**2 JUnit methods**. Field name `exportTaxPolicy` trùng bean name. Cách suy luận này được Spring TestContext hỗ trợ, nhưng khi code refactor đổi field name thành `policy` có thể gây ambiguity hoặc cache keys khác. Với các test quan trọng, explicit `@MockitoBean(name=...,enforceOverride=true)` như mục 14 dễ audit hơn.

## 16. DomesticPolicySpyTest.java — WRAP, không REPLACE

`src/test/java/example/diagnosis/DomesticPolicySpyTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DomesticPolicySpyTest {

    @MockitoSpyBean(name = "domesticTaxPolicy")
    TaxPolicy domesticTaxPolicy;

    @Autowired
    PricingService pricingService;

    @Test
    void unstubbedSpyRunsRealImplementation() {
        BigDecimal subtotal = new BigDecimal("100.00");

        PriceQuote quote = pricingService.quote(
                subtotal, false);

        assertThat(quote.tax())
                .isEqualByComparingTo("10.00");

        verify(domesticTaxPolicy).tax(subtotal);
    }

    @Test
    void doReturnOverridesOnlySelectedSpyMethod() {
        BigDecimal subtotal = new BigDecimal("100.00");

        doReturn(new BigDecimal("2.00"))
                .when(domesticTaxPolicy).tax(subtotal);

        PriceQuote quote = pricingService.quote(
                subtotal, false);

        assertThat(quote.tax())
                .isEqualByComparingTo("2.00");
        assertThat(quote.total())
                .isEqualByComparingTo("102.00");

        verify(domesticTaxPolicy).tax(subtotal);
    }
}
```

**2 JUnit methods**. Spy không chỉ thay bean bằng mock hoàn toàn: hành vi thật vẫn chạy khi chưa stub. Dùng `doReturn` để tránh gọi real implementation khi đăng ký stub. Nếu production bean có side effects, DB writes, security proxies hoặc caching, phải hiểu rõ ranh giới proxy/target; có thể phù hợp hơn dùng mock hoặc test behavior với collaborator thật và test data riêng.

## 17. PhantomOverrideTest.java — mock sai tên nhưng context vẫn khởi động

`src/test/java/example/diagnosis/PhantomOverrideTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class PhantomOverrideTest {

    // Cố ý sai tên để thấy REPLACE_OR_CREATE.
    // Không copy pattern này vào test nghiệp vụ.
    @MockitoBean(name = "typoDomesticTaxPolicy")
    TaxPolicy typoDomesticTaxPolicy;

    @Autowired
    ApplicationContext context;

    @Autowired
    PricingService pricingService;

    @Test
    void wrongNameCreatesUnusedMockInsteadOfOverriding() {
        Map<String, TaxPolicy> beans =
                context.getBeansOfType(TaxPolicy.class);

        assertThat(beans).containsOnlyKeys(
                "domesticTaxPolicy",
                "exportTaxPolicy",
                "typoDomesticTaxPolicy");

        assertThat(context.getBean("typoDomesticTaxPolicy"))
                .isSameAs(typoDomesticTaxPolicy);

        PriceQuote actual = pricingService.quote(
                new BigDecimal("100.00"), false);

        // Service vẫn dùng implementation domestic thật.
        assertThat(actual.tax())
                .isEqualByComparingTo("10.00");

        verifyNoInteractions(typoDomesticTaxPolicy);
    }
}
```

**1 JUnit method**. Đây là test **cố ý mô phỏng anti-pattern nhưng vẫn PASS** để chứng minh lỗi thiết kế: mock typo tồn tại, nhưng business flow không hề sử dụng nó. Một test khác giả định mock typo đã thay real dependency sẽ fail hoặc có false assertion.

**Cách sửa đúng**:

```java
@MockitoBean(
    name = "domesticTaxPolicy",
    enforceOverride = true)
TaxPolicy domesticTaxPolicy;
```

Sau đó assert bean identity và collaborator call như `DomesticPolicyOverrideTest`. Không bật global bean-definition-overriding flag hoặc dùng `@Primary` bừa bãi chỉ để test qua.

## 18. MisconfiguredContextTest.java — tái hiện failures an toàn

`src/test/java/example/diagnosis/MisconfiguredContextTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class MisconfiguredContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    record BrokenConsumer(TaxPolicy policy) {
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfig {

        @Bean("alphaPolicy")
        TaxPolicy alphaPolicy() {
            return subtotal ->
                    subtotal.multiply(new BigDecimal("0.01"));
        }

        @Bean("betaPolicy")
        TaxPolicy betaPolicy() {
            return subtotal ->
                    subtotal.multiply(new BigDecimal("0.02"));
        }

        @Bean
        BrokenConsumer brokenConsumer(TaxPolicy policy) {
            return new BrokenConsumer(policy);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class WrongQualifierConfig {

        @Bean("alphaPolicy")
        TaxPolicy alphaPolicy() {
            return subtotal ->
                    subtotal.multiply(new BigDecimal("0.01"));
        }

        @Bean
        BrokenConsumer brokenConsumer(
                @Qualifier("missingPolicy") TaxPolicy policy) {
            return new BrokenConsumer(policy);
        }
    }

    @Test
    void unqualifiedInjectionFailsWithTwoCandidates() {
        runner.withUserConfiguration(AmbiguousConfig.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                        NoUniqueBeanDefinitionException.class);
            });
    }

    @Test
    void wrongQualifierFailsWithMissingCandidate() {
        runner.withUserConfiguration(WrongQualifierConfig.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                        NoSuchBeanDefinitionException.class);
            });
    }
}
```

**2 JUnit methods**. `ApplicationContextRunner` tạo **context nhỏ và riêng cho mỗi test run**, cho phép test khẳng định startup failure là expected behavior. Không annotate class này `@SpringBootTest`; các nested configs không được load vào production app context.

### Phân biệt hai root causes

- `AmbiguousConfig` có `alphaPolicy` và `betaPolicy`, `BrokenConsumer(TaxPolicy policy)` không có qualifier/name matching ⇒ có nhiều candidates ⇒ `NoUniqueBeanDefinitionException`.
- `WrongQualifierConfig` chỉ có `alphaPolicy` nhưng method yêu cầu `@Qualifier("missingPolicy")` ⇒ không có candidate phù hợp ⇒ `NoSuchBeanDefinitionException`.

Thông thường Spring sẽ bọc root cause trong `BeanCreationException` hoặc `UnsatisfiedDependencyException`; assertions dùng `hasRootCauseInstanceOf` thay vì hard-code toàn bộ exception message.

## 19. Chạy Maven và kết quả dự kiến

Tạo các files đúng như cây thư mục, dùng **JDK 17+**, Maven tương thích rồi chạy:

```bash
mvn test
```

Có thể chạy từng lớp:

```bash
mvn test -Dtest=BeanCandidatesTest
mvn test -Dtest=DomesticPolicyOverrideTest
mvn test -Dtest=ExportPolicyOverrideTest
mvn test -Dtest=DomesticPolicySpyTest
mvn test -Dtest=PhantomOverrideTest
mvn test -Dtest=MisconfiguredContextTest
```

| Lớp | Methods | Dự kiến |
| --- | ---: | --- |
| `BeanCandidatesTest` | 4 | PASS; assertThrows ambiguity |
| `DomesticPolicyOverrideTest` | 3 | PASS; domestic mock, export real |
| `ExportPolicyOverrideTest` | 2 | PASS; export mock, domestic real |
| `DomesticPolicySpyTest` | 2 | PASS; spy real/stubbed behavior |
| `PhantomOverrideTest` | 1 | PASS; ghost mock deliberately unused |
| `MisconfiguredContextTest` | 2 | PASS; asserted startup root causes |
| **Tổng** | **14** | **14 JUnit methods dự kiến** |

**Đây là kết quả kỳ vọng dựa trên mã nguồn, không phải log Maven đã chạy.** Cần kiểm `target/surefire-reports/` để xác nhận test count, failures, errors và skips. Đặc biệt các context tests **có intentional exceptions nhưng xử lý bằng assertions**, không phải một build vô tình fail.

## 20. Workflow chẩn đoán theo 8 bước

### Bước 1 — đọc root cause, không dừng ở “Failed to load ApplicationContext”

Spring Test có thể báo:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext
  ...
Caused by: UnsatisfiedDependencyException
  ...
Caused by: NoUniqueBeanDefinitionException
  ...
```

Truy đến `Caused by` mang thông tin cụ thể về type, bean names, injection point. Một số lần test sau có thể chỉ báo context failure threshold exceeded vì Spring Test cache biết config này từng fail; hãy đọc log **lần đầu** của cache key đó thay vì cố sửa triệu chứng threshold.

### Bước 2 — liệt kê candidates đúng context

Dùng `getBeanNamesForType(Type.class)`/`getBeansOfType(...)`, hoặc debug condition evaluation report trong Boot khi context chưa khởi động được. Với `@SpringBootTest(properties = "debug=true")` có thể bật nhiều log auto-configuration, nhưng đừng dump secrets/environment vào CI logs.

Nếu app context không thể start, `ApplicationContextRunner` với minimal config có thể dựng lại ambiguity trong scope hẹp.

### Bước 3 — kiểm tên, type và qualifiers

- Tên `@Component("...")` có khớp `@Qualifier` không?
- `@Bean` method name có phải bean name hay có custom `@Bean(name=...)`?
- Injection point parameter có `@Qualifier` hay chỉ trông vào variable name?
- Bean có assignable đúng interface type, generic arguments không?
- Có nhiều `@Primary`, hoặc `@Fallback` thay resolution không?

### Bước 4 — kiểm scope/registration

- Test profile khác production?
- `@Profile`/`@ConditionalOnProperty` active như mong muốn?
- `@WebMvcTest` chưa import collaborator hay `@SpringBootTest` đã load full graph?
- `@TestConfiguration` vô tình tạo bean trùng name?
- `@ComponentScan` quét packages test/legacy không nên có?
- Auto-configuration đã back off do `@ConditionalOnMissingBean` chưa?

### Bước 5 — kiểm mock override metadata

- `@MockitoBean` dùng correct interface/type?
- Có nhiều beans cùng type? Nếu có, khai `name=...` hoặc qualifier.
- Có `enforceOverride=true` để không tạo ghost bean không?
- Field name có khớp intended bean name nếu đang dùng fallback qualifier?
- Có nhiều class test override cùng target nhưng đặt field names khác nhau, gây context cache split?
- Có dùng `@Mock` đơn thuần thay vì Spring TestContext bean override?

### Bước 6 — kiểm collaborator có gọi đúng mock không

Đừng chỉ assert field mock được inject. Kiểm:

```java
assertThat(context.getBean("domesticTaxPolicy"))
        .isSameAs(domesticTaxPolicy);

when(domesticTaxPolicy.tax(subtotal))
        .thenReturn(new BigDecimal("7.50"));

PriceQuote result =
        pricingService.quote(subtotal, false);

verify(domesticTaxPolicy).tax(subtotal);
```

Nếu verification báo zero interactions, xem service có gọi đúng branch không, qualifier của constructor là gì, test đang verify bean nào, hoặc args khác `equals`. Với AOP proxies, phải hiểu Mockito wrapper/target semantics trước khi so object identity.

### Bước 7 — kiểm test boundaries và caching

`@WebMvcTest` chỉ quét MVC slice, `@SpringBootTest` full context; mock configuration khác có thể tạo cache key khác. `@MockitoBean` qualifier/field name tham gia cache key. Khi test suite chạy parallel, shared singleton mocks có thể bị reset/stub race. Dùng test isolation và consistent names; không dùng `@DirtiesContext` trên mọi test chỉ để reset Mockito.

### Bước 8 — sửa tối thiểu, chứng minh bằng negative test

- Với nhiều beans: thêm explicit qualifier vào **đúng injection point**.
- Với wrong qualifier: sửa tên/điều kiện registration, không thêm default primary sai.
- Với wrong override: dùng named `@MockitoBean(enforceOverride=true)`, assert actual collaborator interaction.
- Với duplicate name: loại duplicate bean definition/import; không bật overriding toàn cục.
- Với slice missing bean: `@MockitoBean` collaborator ở slice hoặc `@Import` config cần thiết.
- Viết test regression cho **loại lỗi đã gặp** trước khi merge.

## 21. @WebMvcTest và @SpringBootTest: khi nào bean bị thiếu là đúng?

`@WebMvcTest(MyController.class)` chỉ tạo MVC slice, thường không auto-scan `@Service`/`@Repository` collaborators. Nếu controller phụ thuộc `PricingService`, slice test có thể fail start với `NoSuchBeanDefinitionException` dù production `@SpringBootTest` vẫn có bean.

Đoạn minh họa:

```java
@WebMvcTest(PricingController.class)
class PricingControllerTest {

    @MockitoBean
    PricingService pricingService;

    // @Autowired MockMvc mvc; tests...
}
```

`PricingController` không nằm trong sample core, nên đây là **snippet kiến trúc**, không phải file runnable độc lập. Với MVC test, mock service khi chỉ muốn kiểm HTTP mapping/serialization/controller validation; dùng `@SpringBootTest`/`@AutoConfigureMockMvc` khi muốn kiểm service/repository thật.

**Đừng giải quyết slice failure bằng cách import toàn bộ ứng dụng không cần thiết**, vì mất lợi thế isolation/speed của slice. Import tối thiểu security/configuration hoặc mock đúng collaborator.

## 22. @TestConfiguration không tự động thay bean cũ

Giả sử test khai:

```java
@TestConfiguration
class FakeConfig {
    @Bean("domesticTaxPolicy")
    TaxPolicy domesticTaxPolicy() {
        return value -> new BigDecimal("0.00");
    }
}
```

Nếu context đã có bean tên `domesticTaxPolicy`, thêm một definition trùng name có thể gây `BeanDefinitionOverrideException` theo cấu hình Boot. `@TestConfiguration` không phải **cơ chế override an toàn tự động cho mọi trường hợp**.

Giải pháp:

1. `@MockitoBean(name="domesticTaxPolicy",enforceOverride=true)` khi cần Mockito mock.
2. `@TestBean(name="domesticTaxPolicy",enforceOverride=true)` khi cần fake từ static factory.
3. Dùng profile/conditional bean configuration để lựa chọn adapter test thay production, với semantics đã được test.
4. Dùng `@Primary` cho một test fake có **tên khác** khi muốn default injection thay đổi mà không replace definition, và đảm bảo các constructor `@Qualifier` explicit vẫn dùng đúng bean; không kỳ vọng primary override qualifier.
5. Nếu chỉ unit test `PricingService`, tạo instance trực tiếp với mock dependencies, không cần Spring context.

**Không khuyến khích `spring.main.allow-bean-definition-overriding=true`** làm cách sửa chung; nó có thể che duplicate components và làm order-dependent behavior.

## 23. @Primary và @Qualifier khi không có lỗi context nhưng kết quả sai

Một bẫy tinh vi là app có hai policies, domestic được `@Primary`. Service cần export nhưng constructor vô tình bỏ qualifier:

```java
public ExportService(TaxPolicy policy) {
    this.policy = policy; // Có thể nhận domestic @Primary.
}
```

Context vẫn khởi động và các unit tests mock raw type có thể pass, nhưng business behavior sai (export bị tính thuế domestic). Sửa bằng explicit `@Qualifier("exportTaxPolicy")`, viết integration test input export và assert tax=0.00.

Vì vậy **không có NoUniqueBeanDefinitionException không đồng nghĩa injection đúng**. Một default candidate có thể được Spring chọn hợp lệ theo cấu hình nhưng sai ý định nghiệp vụ. Test cần khẳng định behavior, không chỉ `contextLoads()`.

## 24. Bean overrides và AOP proxy: mock đúng tên vẫn có thể sai scope

`@MockitoBean` dùng replacement strategies nên bean mock có thể **không giữ AOP advice** vốn gắn với target: `@Transactional`, `@Cacheable`, `@Retryable`, method security... Test controller với service mock không chứng minh transaction/retry production behavior.

`@MockitoSpyBean` dùng `WRAP`; có thể giữ AOP proxy layer bao quanh spy theo Spring Framework behavior. Do đó:

- Nếu muốn test retry/transaction semantics, ưu tiên real bean và mock dependency **bên dưới**, không thay chính service chứa advice.
- Nếu muốn spy bean proxied, đọc docs về `@MockitoSpyBean`/AOP; `AopTestUtils.getUltimateTargetObject(...)` và proxy-aware verification có thể cần khi context sử dụng advisors.
- `doReturn`/`doThrow` thay `when(spy.method())` để tránh side effects trong stubbing.
- Đừng kết luận bean “không được gọi” nếu đang verify sai layer của proxy hoặc method bị cache bypass.
- `@ContextHierarchy` có thể áp bean overrides lên **nhiều levels**; đặt `contextName` để chỉ đúng context level khi cần.

Các vấn đề này là lý do **named override + expected behavior + actual interaction** đáng tin hơn chỉ kiểm `Mockito.mockingDetails(mock).isMock()`.

## 25. Profiles, @ConditionalOnMissingBean, component scan

Test báo thiếu bean không nhất thiết do qualifier sai. Trường hợp thường gặp:

**Profile khác**:

```java
@Profile("live")
@Component("externalTaxPolicy")
class ExternalTaxPolicy implements TaxPolicy {
    // ...
}
```

Khi test chạy `@ActiveProfiles("test")`, bean `externalTaxPolicy` không được tạo. Nếu code vẫn yêu cầu `@Qualifier("externalTaxPolicy")`, Spring báo thiếu dependency. Sửa thiết kế profile/test adapter, không tạo ghost mock vô điều kiện.

**Auto-configuration backs off**: `@ConditionalOnMissingBean` có thể không đăng ký default nếu test đã cung cấp bean cùng type. Một mock/fake có thể thay đổi condition evaluation và làm graph khác; cần xem Spring Boot condition evaluation report.

**Component scan ngoài ý muốn**: Import config test, scan package rộng, hoặc top-level test configuration đặt nhầm vị trí có thể tạo thêm bean. Spring Boot `@TestConfiguration` top-level không được component-scan thông thường như app component, nên nên import explicit đúng nơi cần.

**Bean methods và tên**: `@Bean` method mặc định lấy method name làm bean name, nhưng `@Bean(name="...")`/aliases có thể đổi. Kiểm bean names thực bằng context metadata, không đoán từ tên implementation.

## 26. Context caching: mock field name là một phần của hiệu năng kiểm thử

Spring TestContext cache keyed by `MergedContextConfiguration`, trong đó bean override customizers phản ánh mock definitions. Hai tests:

```java
@MockitoBean
TaxPolicy exportTaxPolicy;
```

và:

```java
@MockitoBean
TaxPolicy policy;
```

không nhất thiết share context key, dù developer nghĩ cùng type. Field names là fallback qualifiers và có thể dẫn tới **cả ambiguity lẫn context fragmentation**.

Tốt hơn:
- Dùng shared base annotation/test class cho nhóm cần cùng overrides.
- Dùng explicit bean names nhất quán.
- Giữ `@ActiveProfiles`/`@SpringBootTest(properties=...)` tương đương.
- Không thêm `@DirtiesContext` vô cớ để “làm mới mock”; Spring test framework có reset modes.
- Không cố gộp contexts có thật sự khác bean graph hoặc profiles.

Cache mặc định có capacity 32 (LRU) trong một JVM theo Spring TestContext. Nhiều keys không cần thiết tăng startup time, nhưng **đúng bean phải được ưu tiên hơn số cache hits**.

## 27. Chẩn đoán bằng negative tests trước khi sửa production

Một quy trình an toàn khi lỗi ambiguity xảy ra:

1. Viết `ApplicationContextRunner` configuration nhỏ tái hiện **hai candidates + một unqualified consumer**.
2. Assert root cause `NoUniqueBeanDefinitionException`.
3. Thêm explicit `@Qualifier("alphaPolicy")` vào consumer trong config test; xác nhận context có thể start.
4. Viết Spring Boot integration test trên application configuration thật với qualifiers đúng.
5. Viết test override named target với `enforceOverride=true`.
6. Thử sai tên bean trong một **isolated experiment**, xác minh fail fast thay vì ghost mock.
7. Giữ regression tests kiểm business behavior của từng implementation.
8. Chạy toàn suite để đảm bảo test mocks không thay nhầm một bean ở profile khác.

**Không đưa intentional broken config vào production component scan.** Nếu muốn chạy test failure, dùng isolated runner hoặc một dedicated negative test harness, không làm production app fail chỉ để xem stack trace.

## 28. Những cách sửa sai phổ biến

| Cách “sửa” hấp tấp | Vì sao sai | Thay thế |
| --- | --- | --- |
| Thêm `@Primary` lên bean bất kỳ | Có thể chọn nhầm business path | Qualifier explicit tại injection point |
| Bật global bean overriding | Che duplicate bean definitions | Dọn duplicate/import hoặc dùng TestContext override |
| Mock interface theo type khi có nhiều beans | Ambiguous hoặc override sai target | Named `@MockitoBean(...,enforceOverride=true)` |
| Đặt `@Mock` vào SpringBootTest, tưởng đã thay bean | Mock chỉ thuộc test instance | `@MockitoBean` hoặc unit constructor injection |
| Dùng `@MockitoBean` default cho một bean bắt buộc tồn tại | Tên sai tạo ghost bean | `enforceOverride=true` |
| Đổi tên mock field tùy ý | Có thể đổi qualifier/cache key | Thống nhất field name/explicit name |
| Chỉ check `contextLoads()` | Context có thể dùng sai implementation | Assert bean identities và business outcome |
| Spy bằng `when(spy.call())` | Gọi real method lúc stubbing | `doReturn(...).when(spy)...` |
| Bỏ hết @Qualifier để “đỡ annotation” | Spring có thể chọn @Primary sai | Document injection contract |
| Đổi @WebMvcTest thành full @SpringBootTest cho mọi lỗi | Mất test slice isolation/speed | Mock/import đúng collaborator trong slice |
| Xóa tests có NoUnique exception | Mất bằng chứng bug | Runner negative test với expected failure |
| Bắt exception message exact | Dễ thay đổi theo framework version | Assert exception/root cause class |
| @DirtiesContext sau mọi method | Lãng phí context cache | Reset mock/test data đúng scope |
| Cho Spring Boot quét toàn test config package | Tạo duplicate beans | Import test configs có chủ đích |

## 29. Checklist trước khi chốt QA

- [ ] Đọc tới root cause của `Failed to load ApplicationContext`?
- [ ] Liệt kê đúng names/types và number of candidate beans?
- [ ] Biết injection cần một bean hay collection?
- [ ] Kiểm `@Primary`/`@Fallback`/`@Qualifier` tại injection point?
- [ ] Không dựa vào parameter names nếu business cần explicit bean selection?
- [ ] Biết test profile/conditional registration và scanning?
- [ ] Phân biệt `NoUniqueBeanDefinitionException` với duplicate bean name?
- [ ] `@MockitoBean` có explicit target khi nhiều beans cùng type?
- [ ] Dùng `enforceOverride=true` khi target **phải** tồn tại?
- [ ] Kiểm named bean trong context là đúng mock/spy instance?
- [ ] Kiểm collaborator thật gọi expected mock và không gọi wrong mock?
- [ ] Không đặt một Mockito `@Mock` thuần rồi nghĩ Spring đã override?
- [ ] Hiểu `@MockitoSpyBean` WRAP và real-method side effects?
- [ ] Dùng `@TestBean`/`@TestConfiguration` đúng mục đích?
- [ ] Không bật `allow-bean-definition-overriding=true` để che setup lỗi?
- [ ] Không xóa sự khác nhau giữa unit, slice và integration tests?
- [ ] Có negative test `ApplicationContextRunner` cho missing/ambiguous candidates?
- [ ] Dùng root-cause assertion thay exact full message?
- [ ] Không để ghost mock hoặc accidental profile change trong release tests?
- [ ] Mocks được reset, tests chạy độc lập với method order?
- [ ] Kiểm context cache field qualifiers khi nhiều classes dùng cùng overrides?
- [ ] Đã chạy Maven test report thật trước khi tuyên bố tests pass?

## 30. Bài tập

1. Bỏ `@Qualifier` ở cả hai constructor parameters của `PricingService`, quan sát root cause và khôi phục. Không để bản lỗi trong main source.
2. Chỉ bỏ qualifier export rồi thêm `@Primary` cho domestic; phân tích vì sao context có thể start nhưng quote export tính sai.
3. Đổi tên `@Component("domesticTaxPolicy")` thành `"domesticTaxRules"`; kiểm các tests `enforceOverride=true` fail lúc load context.
4. Xóa `enforceOverride=true` rồi dùng sai `@MockitoBean(name="typo...")`; tái hiện phantom bean.
5. Dùng `@MockitoBean(enforceOverride=true) TaxPolicy exportTaxPolicy`, đổi tên field thành `policy`; quan sát fallback qualifier và context behavior.
6. Bổ sung `@Primary` cho một policy trong isolated runner và kiểm ambiguity được giải quyết khi hợp semantics.
7. Đặt `@Fallback` trên một policy (Framework 6.2+), kiểm cơ chế chọn regular candidate.
8. Đổi `@MockitoSpyBean` stubbing từ `doReturn` sang `when` trong isolated experiment, kiểm real method có được gọi ngay lúc stub không.
9. Tạo `@TestBean` cho domestic với static factory, xác minh name selection và enforceOverride.
10. Thêm một `@WebMvcTest` controller với missing service, sửa bằng `@MockitoBean`, không import toàn app.
11. Tạo profile-specific implementation, kiểm `@ActiveProfiles` thay tập candidates.
12. Gắn `@ConditionalOnMissingBean` vào optional adapter và kiểm thay đổi context khi test có mock.
13. Tạo duplicate bean definition cùng name trong isolated runner, assert startup failure thay vì bật global override.
14. Đánh dấu bean scoped khác singleton và kiểm giới hạn override theo Spring version.
15. Đo cache contexts trước/sau khi thống nhất mock field names giữa tests.

## 31. Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): field-name fallback qualifier, explicit name, `enforceOverride`, WRAP và context caching.
2. [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): `REPLACE`, `REPLACE_OR_CREATE`, `WRAP`, singleton/proxy semantics.
3. [Spring Framework — Autowired Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): type matching, qualifier narrowing và bean name/parameter name matching.
4. [Spring Framework — @Primary and @Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html): ưu tiên các implementations.
5. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, `@TestConfiguration` và `@MockitoBean`.
6. [Spring Framework 6.2 — @TestBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-testbean.html): static factory-based test override.
7. [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): context customizers, qualifiers, cache reuse.
8. [Spring Boot — Creating Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): `@ConditionalOnMissingBean` và `ApplicationContextRunner`.
9. [Spring Framework 6.2 — TestContext Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html): lifecycle và bean override support.

### Kết luận

**Nhiều beans cùng type không phải lỗi tự thân.** Lỗi nằm ở **thiếu thông tin chọn bean**, **qualifier/name sai** hoặc **test mock override sai target**. Hãy xem root cause, liệt kê candidates, phân biệt `@Primary`/`@Fallback`/`@Qualifier`, dùng `@MockitoBean(name=...,enforceOverride=true)` khi muốn thay đúng bean, kiểm **bean identity + business outcome + Mockito interactions**, và dùng `ApplicationContextRunner` để test lỗi khởi động có chủ đích mà vẫn giữ suite xanh.
