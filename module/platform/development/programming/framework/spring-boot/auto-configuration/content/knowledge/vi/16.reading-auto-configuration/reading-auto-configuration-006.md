# Đọc kiểm thử của framework để hiểu hành vi nhường chỗ và trường hợp biên

## 1. Vì sao cần đọc test của Spring Boot?

Tài liệu API cho biết `@ConditionalOnMissingBean` là condition cho phép auto-configuration cung cấp bean mặc định khi chưa có bean phù hợp. Nhưng khi thiết kế starter thực tế, câu hỏi thường khó hơn:

- Bean custom có tên khác default thì default có nhường chỗ không?
- Hai cấu hình được xử lý theo thứ tự khác nhau thì condition có nhìn thấy bean chưa?
- Bean được tạo từ `FactoryBean`, XML import, generic container hoặc scoped proxy có được nhận diện không?
- Khi bean definition cùng tên bị thay thế bằng một kiểu khác, condition sử dụng kiểu cũ hay kiểu mới?
- Bean nằm trong parent context có được tính không?
- Condition match nhưng dependency injection vẫn có thể thất bại trong trường hợp nào?

Các câu hỏi này nên được trả lời bằng **kiểm thử của chính framework**, vì test thể hiện input, cách tạo context, kết quả mong đợi và những giới hạn mà tài liệu khái quát có thể không trình bày hết.

Một test framework tốt thường không chỉ xác minh “bean mặc định có được tạo hay không”. Nó tạo nhiều biến thể của ApplicationContext rồi khẳng định **bean nào có mặt, bean nào vắng mặt, condition nào match, và context có khởi động thành công không**.

## 2. Bắt đầu từ cấu trúc một test auto-configuration

Spring Boot cung cấp `ApplicationContextRunner` trong package `org.springframework.boot.test.context.runner`. Đây là công cụ tạo một context nhỏ, chạy một kịch bản, cho phép assertion rồi đóng context sau khi callback hoàn tất.

Mẫu thường gặp:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        GreetingAutoConfiguration.class));

@Test
void defaultBeanIsCreatedWhenMissing() {
    this.contextRunner.run((context) -> {
        assertThat(context).hasSingleBean(GreetingService.class);
    });
}
```

Đọc test theo thứ tự sau:

1. **Runner setup:** context nào được tạo? Có phải web context hay non-web context? Có auto-configuration nào được nạp?
2. **Input của test:** test thêm user configuration, bean, property, parent context hay classloader nào?
3. **Điểm biến đổi:** so với test baseline, chỉ một điều gì đã thay đổi?
4. **Assertion:** test kiểm tra bean count, bean name, bean instance, giá trị trả về hay startup failure?
5. **Fixture:** các lớp cấu hình lồng bên dưới tạo bean nào, dùng annotation nào và thứ tự khai báo ra sao?

Không nên chỉ đọc tên method test rồi kết luận hành vi. Hãy lần theo toàn bộ fixture được truyền vào `withUserConfiguration` hoặc `withConfiguration` để biết chính xác điều kiện đang được thử.

### Các công cụ quan trọng trong runner

| API | Vai trò trong test |
| --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Nạp auto-configuration qua cơ chế test dành cho auto-configuration |
| `withUserConfiguration(...)` | Đăng ký cấu hình do ứng dụng/người dùng cung cấp |
| `withBean(...)` | Đăng ký bean trực tiếp trong context test |
| `withPropertyValues(...)` | Thay đổi Environment để thử property conditions |
| `withClassLoader(new FilteredClassLoader(...))` | Giả lập class hoặc package không có trên runtime classpath |
| `withParent(...)` | Tạo context hierarchy để thử tìm bean ở parent/child |
| `withAllowBeanDefinitionOverriding(...)` | Bật/tắt việc definition cùng tên được thay thế trong test |
| `run(context -> ...)` | Khởi tạo context, thực thi assertion và đóng context |

`ApplicationContextRunner` tạo context tiêu chuẩn không có web server. Nếu auto-configuration cần Servlet hoặc Reactive context, dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`. Đây là một khác biệt quan trọng: test đúng condition nhưng sai loại context vẫn có thể cho kết quả không đại diện cho ứng dụng thật.

## 3. “Back-off” thực sự có nghĩa gì?

Giả sử starter cung cấp default:

```java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return () -> "auto";
}
```

Khi ứng dụng đã đăng ký một bean `GreetingService` phù hợp, condition của phương thức mặc định không match. Spring **không đăng ký default bean đó**.

Đây là cơ chế nhường chỗ trước khi default bean definition được tạo. Nó không phải là:

- Tạo cả default lẫn custom rồi chọn một bean bằng `@Primary`.
- Tạo hai bean cùng tên rồi để bean đăng ký sau ghi đè.
- Khởi tạo default rồi xóa khỏi context.
- Tự động hợp nhất state của hai implementation.

Một test đúng nên kiểm tra đồng thời:

1. Context chỉ có một bean theo contract.
2. Bean custom vẫn tồn tại dưới tên của nó.
3. Bean default không được đăng ký.
4. Lời gọi method trả về đúng giá trị từ implementation custom.

Chỉ assert `hasSingleBean(GreetingService.class)` đôi khi chưa đủ để hiểu rõ bean nào được dùng. Hãy kiểm tra thêm bean name và kết quả nghiệp vụ.

### Bean custom không cần trùng tên default

Ví dụ ứng dụng khai báo:

```java
@Configuration(proxyBeanMethods = false)
class UserConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return () -> "user";
    }
}
```

Bean có tên `customGreetingService`, khác `greetingService`. Tuy vậy, `@ConditionalOnMissingBean(GreetingService.class)` kiểm tra theo **kiểu**, nên default vẫn nhường chỗ.

Đây là lý do test back-off nên dùng tên bean khác nhau. Nếu test chỉ khai báo cùng tên và bật bean-definition overriding, ta có thể vô tình kiểm tra cơ chế ghi đè tên thay vì cơ chế condition theo kiểu.

## 4. Đọc test upstream: từ assertion suy ra hợp đồng

Trong test suite upstream của Spring Boot, các test về bean condition dùng những cấu hình nhỏ để cô lập từng yếu tố. Một số nhóm test đáng đọc:

### 4.1. Type, name và annotation là ba hợp đồng khác nhau

Các test như `testNameOnBeanCondition`, `testNameAndTypeOnBeanCondition`, `testClassOnBeanCondition` và `testAnnotationOnBeanCondition` cho thấy condition có thể kiểm tra bean theo nhiều tiêu chí.

- `@ConditionalOnMissingBean(GreetingService.class)`: kiểm tra theo kiểu.
- `@ConditionalOnMissingBean(name = "greetingService")`: kiểm tra theo tên.
- `@ConditionalOnMissingBean(annotation = CustomQualifier.class)`: kiểm tra annotation trên bean.
- Khi khai báo đồng thời name và type, **cả các tiêu chí được chỉ định đều tham gia điều kiện**.

Ví dụ nếu user khai báo bean `customGreetingService` cùng kiểu `GreetingService` nhưng default chỉ kiểm tra tên `greetingService`, condition theo tên không tự suy ra rằng bean custom có cùng kiểu. Có thể xảy ra hai bean cùng contract.

Vì vậy, chọn tiêu chí theo hợp đồng mở rộng:

- Người dùng được phép thay implementation bằng bất kỳ tên bean nào → thường kiểm tra theo type.
- Chỉ một bean name cụ thể được coi là điểm thay thế → kiểm tra theo name.
- Mọi bean được đánh dấu bằng qualifier/annotation nhất định đều phải khiến default nhường chỗ → kiểm tra annotation và xác minh cả proxy.

### 4.2. Thứ tự xử lý cấu hình là một phần của input

Test `testNameOnBeanConditionReverseOrder` trong suite upstream cố ý đảo thứ tự đăng ký hai cấu hình. Khi cấu hình có condition được xử lý trước cấu hình tạo bean mà nó đang tìm, condition có thể chưa nhìn thấy bean definition và không match.

Điều này giải thích khuyến nghị của Spring Boot: đặt `@ConditionalOnBean` và `@ConditionalOnMissingBean` trong **auto-configuration**, vì auto-configuration được xử lý sau các user bean definitions theo cơ chế Boot.

Một consumer phụ thuộc bean do auto-configuration khác cung cấp nên khai báo thứ tự phù hợp:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // Conditions cần nhìn thấy bean definition từ FoundationAutoConfiguration.
}
```

Test với `AutoConfigurations.of(...)` giúp mô phỏng đường đi auto-configuration. Đừng dùng thứ tự các đối số truyền vào test như bằng chứng rằng bean instance sẽ được khởi tạo theo đúng thứ tự đó.

### 4.3. XML import có thể làm thay đổi thời điểm bean definition xuất hiện

Test `testOnBeanConditionWithXml` và `testOnBeanConditionWithCombinedXml` cho thấy test suite còn kiểm tra cấu hình Java kết hợp với `@ImportResource`.

Điểm cần đọc không chỉ là XML có chứa bean hay không, mà là **bean definition được đăng ký ở giai đoạn nào so với lúc condition được đánh giá**. Nếu test thất bại, hãy xem thứ tự xử lý XML import, Java configuration và auto-configuration trước khi kết luận condition sai.

Đây cũng là lý do starter nên ưu tiên đường đăng ký auto-configuration chuẩn của Boot thay vì trộn các cấu hình người dùng, XML import và condition theo một thứ tự không được kiểm soát.

### 4.4. Khi bean definition cùng tên bị thay thế bằng kiểu khác

Test `conditionEvaluationConsidersChangeInTypeWhenBeanIsOverridden` tạo definition ban đầu có kiểu `String` rồi thay definition cùng tên bằng kiểu `Integer` khi bật bean-definition overriding. Một cấu hình consumer có `@ConditionalOnBean(String.class)` được kỳ vọng **không** xuất hiện sau khi kiểu definition đã đổi.

Test này nhắc ta rằng condition theo kiểu phụ thuộc vào **metadata bean definition hiện hành**, không chỉ vào tên bean hoặc kiểu của definition đã bị thay thế trước đó.

Trong ứng dụng Boot, bean-definition overriding mặc định thường không được bật. Test bật nó có chủ ý để kiểm tra một trường hợp biên của container. Không nên bật overriding trong production chỉ để làm test pass.

### 4.5. `FactoryBean`: phân biệt factory và object do factory tạo ra

Các test như `beanProducedByFactoryBeanIsConsideredWhenMatchingOnAnnotation` kiểm tra việc bean product do `FactoryBean` tạo ra có được condition nhận diện khi kiểm tra annotation hay không.

Đừng nhầm hai đối tượng:

- Bean factory: object triển khai `FactoryBean<T>`, có tên thường được truy cập với tiền tố `&`.
- Bean product: object kiểu `T` do `getObject()` trả về.

Nếu condition kiểm tra kiểu/annotation của product, hãy đọc test xem nó đăng ký và assertion tên bean nào. Một test chỉ kiểm tra factory tồn tại chưa chứng minh product được match đúng.

### 4.6. Generic và parameterized container

Các test có tên `genericWhenTypeArgumentMatches`, `genericWhenTypeArgumentWithValueMatches` và `parameterizedContainerWhenValueIsOfExistingBeanMatches` kiểm tra thông tin generic và container type.

Ví dụ một bean `Store<Customer>` không tương đương với `Store<Order>` nếu condition quan tâm type argument. Tương tự, nếu kiểu cần tìm được chứa trong một container như `Registration<Customer>`, condition có thể khai báo `parameterizedContainer` để kiểm tra phần tử bên trong.

`@ConditionalOnMissingBean` và `@ConditionalOnBean` có hỗ trợ `parameterizedContainer`. Khi đọc test, chú ý cả kiểu khai báo của factory method, generic type argument và container được chỉ định; đừng chỉ nhìn tên bean.

### 4.7. Bean không phải autowire candidate

Các test ở upstream test suite mới hơn còn phân biệt điều kiện theo type/annotation với điều kiện theo name khi bean được khai báo `autowireCandidate = false`. Type/annotation matching có thể bỏ qua bean không được phép làm ứng viên autowire, trong khi kiểm tra theo tên vẫn có thể nhận ra tên bean đó.

Đây là ví dụ tốt về cách đọc test theo **loại tiêu chí** thay vì suy luận “bean có trong registry thì mọi condition đều thấy như nhau”.

**Giới hạn phiên bản:** test suite upstream mới hơn còn có các trường hợp `defaultCandidate = false`. Thuộc tính này thuộc thế hệ Spring Framework 6.2 / Spring Boot 3.4 trở lên; không được chép ngược ví dụ đó vào project Spring Boot 3.3.5. Khi học từ source test của nhánh mới, luôn kiểm tra API có tồn tại trong phiên bản đang dùng hay không.

## 5. Trường hợp biên quan trọng trên Spring Boot 3.3.5: scoped proxy và annotation back-off

Một issue upstream của Spring Boot, `#43423`, cung cấp test rất đáng đọc vì nó so sánh trực tiếp hành vi giữa 3.3.5 và 3.4.0.

Bài toán: auto-configuration cung cấp `Supplier<String>` mặc định nếu không tìm thấy bean mang annotation `AnnotationConditionQualifier`:

```java
@Bean
@AnnotationConditionQualifier
@ConditionalOnMissingBean(annotation = AnnotationConditionQualifier.class)
public Supplier<String> supplier() {
    return () -> "auto-configuration-string";
}
```

Ứng dụng có một `Supplier<String>` custom, được đánh dấu cùng annotation. Có hai biến thể:

1. Bean thông thường.
2. Bean request-scoped, sử dụng `ScopedProxyMode.INTERFACES`.

Test thường kiểm tra danh sách bean `Supplier` chỉ có `customSupplier`. Test scoped kiểm tra cả bean proxy và target bean name do `ScopedProxyUtils.getTargetBeanName("customSupplier")` tạo ra, và không có supplier mặc định của auto-configuration.

Issue ghi rõ: trường hợp thông thường pass ở cả 3.3.5 và 3.4.0; test scoped proxy pass ở 3.3.5 nhưng fail ở 3.4.0 sau một thay đổi trong cách xét autowire/default candidates. Issue có milestone 3.4.1. Với 3.3.5, ví dụ trong issue dùng thêm `value = Void.class` cùng annotation để tránh type-based matching và cô lập đúng tiêu chí annotation.

Điều học được từ test này:

- Một bean proxy có thể có nhiều bean name liên quan: proxy và target.
- Kiểm tra bean theo annotation có thể gặp khác biệt khi proxy/scoped target được tạo.
- Test chỉ với singleton thông thường chưa đủ để chứng minh hành vi đúng cho request/session scope.
- Khi nâng Spring Boot, cần chạy lại các test back-off có proxy thay vì giả định condition không thay đổi.

Không dùng workaround của một phiên bản cho mọi phiên bản. Hãy giữ test tái hiện, chạy trên đúng Boot/Framework version và kiểm tra issue/release note trước khi thay annotation hoặc cấu hình proxy.

## 6. Ví dụ kiểm thử back-off tối thiểu với Spring Boot 3.3.5 / Java 17+

Ví dụ này tạo một auto-configuration nhỏ, sau đó kiểm tra default và custom bean. Nó dùng `ApplicationContextRunner` như cách Spring Boot hướng dẫn kiểm thử auto-configuration.

### 6.1. Cấu trúc project

```text
greeting-autoconfigure-test/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── api/GreetingService.java
    │   └── autoconfigure/GreetingAutoConfiguration.java
    └── test/java/demo/autoconfigure/
        └── GreetingAutoConfigurationTests.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>greeting-autoconfigure-test</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 6.3. `src/main/java/demo/api/GreetingService.java`

```java
package demo.api;

public interface GreetingService {
    String greet();
}
```

### 6.4. `src/main/java/demo/autoconfigure/GreetingAutoConfiguration.java`

```java
package demo.autoconfigure;

import demo.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return () -> "auto";
    }
}
```

Ở đây condition khai báo rõ contract `GreetingService.class`. Khi người dùng cung cấp một bean có tên khác nhưng cùng kiểu, default vẫn nhường chỗ.

### 6.5. `src/test/java/demo/autoconfigure/GreetingAutoConfigurationTests.java`

```java
package demo.autoconfigure;

import demo.api.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenNoUserBeanExists() {
        this.contextRunner.run((context) -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasBean("greetingService");
            assertThat(context.getBean(GreetingService.class).greet())
                    .isEqualTo("auto");
        });
    }

    @Test
    void backsOffWhenUserProvidesBeanWithDifferentName() {
        this.contextRunner
                .withUserConfiguration(UserConfiguration.class)
                .run((context) -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasBean("customGreetingService");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class).greet())
                            .isEqualTo("user");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return () -> "user";
        }
    }
}
```

Chạy test:

```bash
mvn -q test
```

Hai test xác nhận hai trạng thái cốt lõi:

- Không có user bean: default được tạo.
- Có user bean khác tên nhưng cùng kiểu: default không được đăng ký và user implementation được sử dụng.

Đây là test nhỏ nhất để bảo vệ hợp đồng back-off. Khi đưa vào starter thực tế, hãy mở rộng theo classpath, property, annotation, scope và context hierarchy mà starter hỗ trợ.

## 7. Mở rộng ma trận kiểm thử cho trường hợp biên

Không cần nhồi mọi trường hợp vào một test lớn. Tạo một test riêng cho mỗi yếu tố thay đổi, dùng tên method thể hiện input và outcome.

| Yếu tố thay đổi | Setup test cần có | Assertion nên có |
| --- | --- | --- |
| Không có bean custom | Chỉ auto-configuration | Default tồn tại đúng một |
| Bean custom khác tên, cùng type | User configuration tạo custom bean | Custom tồn tại, default vắng mặt |
| Condition theo name | Bean cùng type nhưng tên khác | Default theo name vẫn có thể xuất hiện; xác nhận có thể tạo nhiều bean |
| Condition theo annotation | Bean custom được gắn annotation | Default nhường chỗ khi annotation được nhận diện |
| Property bật/tắt | `withPropertyValues` | Chỉ bean có property condition thay đổi |
| Classpath có/thiếu | `FilteredClassLoader` | Class-level auto-configuration được bật/tắt |
| Bean nằm ở parent context | `withParent` và SearchStrategy | Kết quả theo `ALL`, `ANCESTORS` hoặc `CURRENT` |
| Hai config đổi thứ tự | Đổi registration order | Phát hiện condition có nhìn thấy bean definition tại thời điểm đánh giá |
| FactoryBean product | Đăng ký `FactoryBean<T>` | Kiểm tra product type/annotation, không chỉ factory |
| Generic/parameterized container | `GenericType` hoặc `parameterizedContainer` | Type argument/container phù hợp mới match |
| Scoped proxy | Request scope và proxy mode | Kiểm tra proxy + target bean name, default không xuất hiện |
| Bean definition đổi kiểu | Cho phép override trong test riêng | Condition phản ánh kiểu definition cuối cùng |
| Nhiều candidate | Hai bean cùng type, primary/không primary | Kiểm tra single-candidate và dependency injection riêng biệt |

Đối với mỗi test, nên kiểm tra **cả positive và negative assertion**. Ví dụ, nếu test back-off chỉ assert custom bean có mặt mà không assert default vắng mặt, test có thể vẫn pass dù framework tạo thêm một default bean ngoài ý muốn.

## 8. Cách điều tra một test framework bị fail

Khi nâng version hoặc sửa auto-configuration, làm theo trình tự:

1. **Chạy đúng một test:** dùng Maven Surefire để chỉ chạy class/method đang lỗi, ví dụ `mvn -Dtest=GreetingAutoConfigurationTests#backsOffWhenUserProvidesBeanWithDifferentName test`.
2. **Đọc assertion đầu tiên bị fail:** context có startup failure không? Bean count sai, tên bean sai hay giá trị implementation sai?
3. **Đọc fixture:** user bean được đăng ký bằng `withUserConfiguration` hay `withBean`? Có class-level condition hoặc property condition nào khác không?
4. **Kiểm tra bean definitions:** lấy bean names theo type, bean definition class, factory method và role nếu cần. Đừng chỉ nhìn `getBean(Class)` vì nó có thể thất bại do nhiều candidate.
5. **Kiểm tra thời điểm xử lý:** auto-configuration provider/consumer có quan hệ `before`/`after` không? User config có được đăng ký trước auto-configuration không?
6. **Kiểm tra loại bean:** singleton hay scoped proxy? Bean product từ `FactoryBean`? Generic type có bị mất do return type quá rộng không?
7. **So sánh version:** đọc source test và implementation cùng tag/version. Một test mới ở nhánh main có thể dùng API hoặc semantics chưa tồn tại trong Boot 3.3.5.
8. **Tạo test hồi quy tối thiểu:** giữ nguyên input làm lỗi, bỏ mọi cấu hình không cần thiết, đặt tên test theo bug và assert đúng bean names/outcome.
9. **Chạy toàn bộ test suite:** sau khi test tối thiểu pass, chạy module tests để phát hiện ảnh hưởng đến các auto-configuration khác.

Khi cần xem condition report, dùng `ConditionEvaluationReport` hoặc bật `ConditionEvaluationReportLoggingListener` trong runner. Report giúp giải thích condition match/no match; assertion trên bean registry vẫn cần thiết để xác nhận kết quả cuối.

## 9. Các bẫy khi đọc test từ nhánh framework khác version

**Bẫy 1 — chép API mới vào Boot 3.3.5.** Test suite mới có thể dùng `@Bean(defaultCandidate = false)` hoặc semantics mới. Spring Boot 3.3.5 dùng Spring Framework 6.1; không giả định thuộc tính của Framework 6.2 đã có.

**Bẫy 2 — hiểu nhầm test current branch là hợp đồng của version cũ.** Dùng test suite mới để tìm nhóm edge case, sau đó xác nhận từng trường hợp trên đúng tag đang triển khai. Issue #43423 là ví dụ: scoped proxy annotation matching khác nhau giữa 3.3.5 và 3.4.0.

**Bẫy 3 — test chỉ dùng context tiêu chuẩn.** Một test với `ApplicationContextRunner` không tự kiểm tra Servlet/Reactive scope, request proxy hoặc web server. Dùng runner phù hợp với context cần mô phỏng.

**Bẫy 4 — chỉ kiểm tra một bean.** `@ConditionalOnMissingBean` có thể làm default nhường chỗ nhưng consumer khác vẫn lỗi, hoặc một bean khác cùng type vẫn tồn tại. Assert cả bean names, count, selected implementation và startup state.

**Bẫy 5 — nhầm condition với dependency injection.** `@ConditionalOnBean` có thể match khi có bean; nhưng một injection point đơn vẫn có thể mơ hồ nếu nhiều ứng viên. Condition match không chứng minh method factory sẽ tạo được bean thành công.

**Bẫy 6 — không để ý bean definition đã xử lý.** Bean condition không dự đoán mọi definition sẽ xuất hiện trong tương lai. Cấu hình bình thường bị đảo thứ tự có thể cho kết quả khác auto-configuration được Boot sắp xếp.

**Bẫy 7 — không phân biệt factory với product.** Test có `FactoryBean` cần kiểm tra đúng đối tượng mà condition đang match, đặc biệt khi kiểm tra annotation hoặc generic type.

**Bẫy 8 — chỉ assert rằng context không fail.** Context có thể khởi động nhưng default bị mất hoặc consumer không được đăng ký. Hãy assert cả chức năng cần có.

## 10. Checklist khi review auto-configuration dựa trên framework tests

- [ ] Đã đọc test class liên quan trong đúng version Spring Boot đang dùng.
- [ ] Đã xác định runner loại context và các auto-configuration được nạp.
- [ ] Đã đọc toàn bộ fixture của test, không chỉ method test.
- [ ] Đã kiểm tra default khi không có custom bean.
- [ ] Đã kiểm tra custom bean có tên khác default và default thực sự vắng mặt.
- [ ] Đã kiểm tra condition theo type/name/annotation đúng hợp đồng.
- [ ] Đã kiểm tra classpath/property condition nếu auto-configuration có các cổng này.
- [ ] Đã kiểm tra thứ tự đăng ký bean definitions.
- [ ] Đã kiểm tra FactoryBean, generic/container, parent context hoặc proxy nếu có liên quan.
- [ ] Đã kiểm tra cả bean names/count lẫn hành vi của bean được chọn.
- [ ] Đã chạy test hồi quy trên đúng version và toàn bộ test module.
- [ ] Đã ghi rõ khác biệt nếu tham khảo test từ nhánh Spring Boot mới hơn.

## Tài liệu và test upstream nên đọc

- [Spring Boot 3.3 — Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): cách dùng `ApplicationContextRunner`, `AutoConfigurations`, `FilteredClassLoader` và runner cho web context.
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): API tạo context test và các customization.
- [Upstream test source: `ConditionalOnBeanTests.java`](https://fossies.org/linux/spring-boot/core/spring-boot-autoconfigure/src/test/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBeanTests.java): test suite upstream ở nhánh mới hơn, hữu ích để xem cách tổ chức test type/name/annotation, order, FactoryBean, generic và candidate filtering. Các test có API mới phải được đối chiếu version trước khi áp dụng.
- [Spring Boot issue #43423 — OnBeanCondition và scoped proxy](https://github.com/spring-projects/spring-boot/issues/43423): test case cụ thể so sánh hành vi 3.3.5 và 3.4.0 khi `@ConditionalOnMissingBean(annotation = ...)` gặp request-scoped proxy.
- [Spring Boot issue #23069 — `@ConditionalOnMissingBean` và `@ImportResource`](https://github.com/spring-projects/spring-framework/issues/23069): ví dụ lịch sử cho thấy thứ tự XML/Java bean definition có thể ảnh hưởng back-off.
