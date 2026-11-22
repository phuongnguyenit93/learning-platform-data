# Kiểu trả về của `@Bean` ảnh hưởng đến khả năng suy luận ứng viên

**Chủ đề:** Spring Boot Auto Configuration → Điều kiện bean  
**Trọng tâm:** Vì sao kiểu trả về khai báo trên phương thức `@Bean` có thể quyết định kết quả của `@ConditionalOnBean` và `@ConditionalOnMissingBean`, dù đối tượng thực tế được trả về vẫn là cùng một lớp.

## 1. Hiểu đúng vấn đề

Trong Spring, một phương thức `@Bean` vừa tạo đối tượng vừa cung cấp thông tin kiểu cho container:

```java
@Bean
AuditSink auditSink() {
    return new FileAuditSink();
}
```

Giả sử `FileAuditSink implements AuditSink`. Ở đây có **hai kiểu khác nhau**:

- **Kiểu khai báo (declared return type):** `AuditSink`, là kiểu Spring nhìn thấy ngay từ chữ ký phương thức.
- **Kiểu đối tượng lúc chạy (runtime type):** `FileAuditSink`, chỉ chắc chắn khi phương thức được gọi và đối tượng được tạo.

Spring không nhất thiết khởi tạo mọi bean trước khi quyết định có đăng ký các bean khác hay không. Khi đánh giá điều kiện dựa trên bean, framework phải sử dụng thông tin kiểu *đang có* trong các bean definition. Với bean đến từ `@Bean`, kiểu trả về khai báo là một nguồn thông tin quan trọng để dự đoán kiểu ứng viên.

**Hệ quả:** Một bean thực tế là `FileAuditSink` nhưng được khai báo trả về `AuditSink` có thể chưa được nhận ra là ứng viên của điều kiện tìm `FileAuditSink` tại thời điểm điều kiện chạy. Sau khi bean đã khởi tạo, một phép tra cứu kiểu tại runtime có thể nhìn thấy lớp cụ thể; điều đó không làm thay đổi quyết định điều kiện đã được đưa ra trước đó.

## 2. Vì sao auto-configuration đặc biệt nhạy với thông tin kiểu?

Hai điều kiện quen thuộc của Spring Boot là:

- `@ConditionalOnBean(X.class)`: chỉ khớp khi có bean phù hợp với kiểu `X` trong phạm vi tìm kiếm.
- `@ConditionalOnMissingBean(X.class)`: chỉ khớp khi chưa có bean phù hợp với kiểu `X` trong phạm vi tìm kiếm; thường dùng để cung cấp bean mặc định và **nhường chỗ (back off)** cho bean do ứng dụng tự định nghĩa.

Điều kiện được xét trên **những bean definition đã được xử lý đến thời điểm đó**. Vì vậy, có **hai biến số độc lập** phải kiểm soát: kiểu mà bean definition bộc lộ và thứ tự xử lý các configuration. Spring Boot khuyến nghị đặt các điều kiện phụ thuộc sự hiện diện của bean trong auto-configuration, vì cấu hình của người dùng thường được xử lý trước auto-configuration.

Hình dung trình tự thường gặp:

1. Spring đọc cấu hình người dùng, tạo bean definition cho `@Bean AuditSink auditSink()`.
2. Bean definition có thông tin trả về `AuditSink`; nó chưa nhất thiết chứa thông tin rằng đối tượng sẽ là `FileAuditSink`.
3. Auto-configuration kiểm tra `@ConditionalOnMissingBean(FileAuditSink.class)`.
4. Nếu không nhận diện được ứng viên kiểu `FileAuditSink`, điều kiện có thể khớp và đăng ký thêm bean mặc định.
5. Các singleton được tạo sau đó; lúc này cả hai đối tượng có thể cùng thực thi `AuditSink`.

Đây là vấn đề **khả năng suy luận kiểu trước khi khởi tạo**, không phải Java đánh mất kiểu runtime, cũng không phải bản thân `@Bean` luôn tạo thêm một đối tượng.

## 3. Trường hợp dễ sai: trả về interface nhưng điều kiện tìm implementation

Giả sử thư viện có hai kiểu:

```java
interface AuditSink {
}

final class FileAuditSink implements AuditSink {
}
```

Cấu hình ứng dụng khai báo rộng:

```java
@Configuration(proxyBeanMethods = false)
class UserAuditConfiguration {

    @Bean
    AuditSink auditSink() {
        return new FileAuditSink();
    }
}
```

Auto-configuration lại tìm kiểu cụ thể:

```java
@AutoConfiguration
class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FileAuditSink.class)
    FileAuditSink defaultAuditSink() {
        return new FileAuditSink();
    }
}
```

`auditSink` đã tồn tại dưới kiểu khai báo `AuditSink`, nhưng điều kiện của `defaultAuditSink` cần thấy `FileAuditSink`. Khi bean người dùng chưa được khởi tạo và container không suy luận được lớp cụ thể, điều kiện cho rằng chưa có ứng viên, dẫn đến **hai bean** (`auditSink` và `defaultAuditSink`).

Sửa chữ ký cấu hình người dùng:

```java
@Bean
FileAuditSink auditSink() {
    return new FileAuditSink();
}
```

Khi đó, bean definition bộc lộ trực tiếp `FileAuditSink`; `@ConditionalOnMissingBean(FileAuditSink.class)` nhận diện được ứng viên và bean mặc định sẽ nhường chỗ, với giả định cấu hình người dùng được xử lý trước điều kiện auto-configuration.

| Khai báo trong `@Bean` của người dùng | Điều kiện phía auto-configuration | Kết quả kỳ vọng khi đánh giá trước lúc tạo singleton |
| --- | --- | --- |
| `AuditSink auditSink()` | `@ConditionalOnMissingBean(AuditSink.class)` | Nhận diện bean theo interface; bean mặc định nhường chỗ |
| `AuditSink auditSink()` | `@ConditionalOnMissingBean(FileAuditSink.class)` | Có nguy cơ không nhận diện bean theo implementation; đăng ký thêm mặc định |
| `FileAuditSink auditSink()` | `@ConditionalOnMissingBean(FileAuditSink.class)` | Nhận diện được implementation; bean mặc định nhường chỗ |
| `FileAuditSink auditSink()` | `@ConditionalOnMissingBean(AuditSink.class)` | Nhận diện được vì `FileAuditSink` thực thi `AuditSink`; bean mặc định nhường chỗ |

Bảng mô tả trường hợp thông thường khi điều kiện được kiểm tra dựa trên bean definition trước khi singleton được khởi tạo. Các cơ chế như factory method đặc biệt, `FactoryBean`, proxy, bean đã khởi tạo hoặc custom type prediction có thể cung cấp thông tin khác; không nên coi ví dụ là quy luật tuyệt đối cho mọi thời điểm của vòng đời container.

## 4. Thí nghiệm có thể chạy: cùng đối tượng, khác chữ ký, khác kết quả điều kiện

Thí nghiệm dưới đây dùng **Java 17**, **Spring Boot 3.3.5**, JUnit 5 và `ApplicationContextRunner`. Đây là chương trình kiểm thử độc lập: không cần máy chủ web, cơ sở dữ liệu hay ứng dụng Boot đang chạy.

### 4.1. Tạo dự án Maven

Lưu tệp `pom.xml` tại thư mục dự án:

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
    <artifactId>bean-return-type-demo</artifactId>
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

### 4.2. Viết một lớp test hoàn chỉnh

Tạo `src/test/java/demo/BeanReturnTypeConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class BeanReturnTypeConditionTest {

    interface AuditSink {
    }

    static final class FileAuditSink implements AuditSink {
    }

    @Configuration(proxyBeanMethods = false)
    static class BroadReturnConfiguration {
        @Bean
        AuditSink auditSink() {
            return new FileAuditSink();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SpecificReturnConfiguration {
        @Bean
        FileAuditSink auditSink() {
            return new FileAuditSink();
        }
    }

    @AutoConfiguration
    static class DefaultAuditAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(FileAuditSink.class)
        FileAuditSink defaultAuditSink() {
            return new FileAuditSink();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DefaultAuditAutoConfiguration.class)
                    );

    @Test
    void broadReturnTypeCanHideConcreteCandidateAtConditionTime() {
        runner.withUserConfiguration(BroadReturnConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("auditSink");
                    assertThat(context).hasBean("defaultAuditSink");
                    assertThat(context.getBeansOfType(AuditSink.class)).hasSize(2);
                });
    }

    @Test
    void specificReturnTypeLetsConditionFindTheCandidate() {
        runner.withUserConfiguration(SpecificReturnConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("auditSink");
                    assertThat(context).doesNotHaveBean("defaultAuditSink");
                    assertThat(context.getBeansOfType(AuditSink.class)).hasSize(1);
                });
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn test
```

**Kết quả mong đợi:** hai bài kiểm thử đều PASS (Maven báo `Tests run: 2, Failures: 0, Errors: 0, Skipped: 0` trong phần kết quả Surefire ở cấu hình thông thường). Không có dòng `System.out.println` nào cần xuất ra từ mã Java. Các assert chứng minh:

- Với `AuditSink auditSink()`, bean `defaultAuditSink` vẫn có thể được đăng ký dù đối tượng của `auditSink` rốt cuộc cũng là `FileAuditSink`.
- Với `FileAuditSink auditSink()`, điều kiện nhìn thấy bean ứng viên và không đăng ký `defaultAuditSink`.
- Việc sau khi context đã refresh có thể đếm được hai instance kiểu `AuditSink` **không** có nghĩa là điều kiện trước đó phải biết được runtime type của chúng.

Nếu test đầu tiên thất bại do môi trường hoặc phiên bản thư viện có cơ chế type prediction khác, hãy xem bản báo cáo condition và bean definition thay vì kết luận rằng Java không hỗ trợ interface. Hai phép thử trên chủ đích kiểm tra hành vi trong cấu hình Spring Boot đã nêu.

## 5. Điểm tinh tế: chữ ký cũng ảnh hưởng đến kiểu *mặc định* của chính điều kiện

Ở phương thức `@Bean`, khi không chỉ rõ `value`, `type`, `name`, `annotation`... để xác định đối tượng tìm kiếm, `@ConditionalOnMissingBean` có thể dùng **kiểu trả về phương thức đang được chú thích** làm đích.

```java
@Bean
@ConditionalOnMissingBean
AuditSink defaultAuditSink() {
    return new FileAuditSink();
}
```

Trường hợp này, mục tiêu của điều kiện là `AuditSink`. Nếu thay kiểu trả về thành `FileAuditSink` nhưng **giữ nguyên** `@ConditionalOnMissingBean` không có tham số, đích kiểm tra sẽ trở thành `FileAuditSink`. Điều kiện lúc ấy không còn mang cùng ý nghĩa chính sách: một bean `OtherAuditSink implements AuditSink` có thể không khiến fallback của loại `FileAuditSink` nhường chỗ.

Nếu quy tắc nghiệp vụ là **chỉ được có một `AuditSink` do ứng dụng tự chọn, fallback dùng khi chưa có bất kỳ `AuditSink` nào**, cách viết thường rõ ràng hơn là:

```java
@Bean
@ConditionalOnMissingBean(AuditSink.class)
FileAuditSink defaultAuditSink() {
    return new FileAuditSink();
}
```

Cách này tách bạch hai mục đích:

- **Return type `FileAuditSink`:** cung cấp kiểu cụ thể cho container và những điều kiện/điểm injection khác.
- **Condition target `AuditSink.class`:** quy định chính xác khi nào fallback phải nhường chỗ cho một implementation khác.

Ngược lại, nếu fallback chỉ bị thay thế bởi *cùng implementation* `FileAuditSink`, hãy giữ `@ConditionalOnMissingBean(FileAuditSink.class)` và hiểu rõ rằng một `AuditSink` implementation khác không tự động vô hiệu hóa fallback.

Tương tự, nên khai báo rõ `@ConditionalOnBean(AuditSink.class)` hoặc `@ConditionalOnBean(FileAuditSink.class)` tùy phụ thuộc thực sự cần, thay vì để chữ ký phương thức được chú thích vô tình định nghĩa chính sách tìm kiếm.

## 6. Nguyên tắc áp dụng trong dự án

### 6.1. Bộc lộ kiểu đủ cụ thể nhưng đúng hợp đồng

Ưu tiên:

```java
@Bean
FileAuditSink auditSink() {
    return new FileAuditSink();
}
```

thay vì:

```java
@Bean
Object auditSink() {
    return new FileAuditSink();
}
```

hoặc khai báo interface quá rộng nếu hệ thống có điều kiện, injection hoặc cấu hình khác cần biết `FileAuditSink` trước khi bean được tạo. Một method trả về `Object` thường che giấu gần như toàn bộ khả năng dự đoán hữu ích.

Tuy nhiên, **không phải lúc nào khai báo interface cũng sai**. Nếu toàn bộ consumer và điều kiện chỉ phụ thuộc `AuditSink`, trả về `AuditSink` có thể là thiết kế API nhất quán. Đưa implementation vào kiểu trả về khi lớp cụ thể thực sự là phần thông tin các bean definition khác cần nhận diện và phù hợp mức độ công khai của API.

### 6.2. Cẩn thận với generic, factory và proxy

Ví dụ, khác biệt giữa kiểu đầy đủ `Handler<Order>` và raw type `Handler` có thể làm mất thông tin generic phục vụ phân giải dependency. Spring dùng `ResolvableType` để giữ thông tin kiểu khi có thể. Với `FactoryBean`, container còn cần metadata hoặc `getObjectType()` thích hợp để nhận diện loại đối tượng được sản xuất. Proxy có thể khiến kiểu runtime quan sát được khác với lớp implementation ban đầu.

Đây là các tình huống cần kiểm tra thực tế bằng `ApplicationContextRunner` và bean definition. Đừng suy luận toàn bộ kết quả chỉ từ `getClass()` hoặc chỉ từ một lần `getBeanNamesForType()` sau khi ứng dụng đã khởi động.

### 6.3. Đừng trộn lẫn ba cơ chế khác nhau

| Cơ chế | Mục đích | Có giải quyết thiếu thông tin kiểu tại thời điểm condition không? |
| --- | --- | --- |
| Kiểu trả về `@Bean` | Bộc lộ kiểu để container dự đoán và tìm bean | **Có**, khi kiểu cần nhận diện nằm trong chữ ký |
| `@ConditionalOnBean` / `@ConditionalOnMissingBean` | Quyết định có đăng ký bean dựa trên những bean đã biết | **Bị ảnh hưởng** bởi thông tin kiểu và thứ tự cấu hình |
| `@Primary` / `@Qualifier` | Hỗ trợ lựa chọn bean khi tiêm dependency | **Không tự sửa** một quyết định condition đã được đưa ra |
| Trùng tên bean / cho phép override bean definition | Kiểm soát xung đột bean definition theo tên | **Khác vấn đề** với hai bean khác tên nhưng cùng interface |

Có thể có hai bean khác tên (`auditSink`, `defaultAuditSink`) dù ứng dụng **không bật** `spring.main.allow-bean-definition-overriding`; cờ này không phải giải pháp cho lỗi type prediction.

## 7. Kiểm tra và gỡ lỗi có hệ thống

Khi auto-configuration không tạo bean như mong đợi hoặc tạo thừa bean:

1. **Đọc chữ ký `@Bean`** của bean ứng viên và xác định kiểu trả về khai báo, không chỉ nhìn lệnh `return new ...`.
2. **Đọc chính xác điều kiện:** điều kiện tìm interface, implementation, tên bean, annotation hay kiểu suy ra ngầm từ return type?
3. **Xác định thời điểm đăng ký:** bean người dùng đã được xử lý trước auto-configuration hay chưa? `@AutoConfiguration(after = ...)` và các thuộc tính điều phối thứ tự xử lý cần được dùng khi các auto-configuration phụ thuộc lẫn nhau.
4. **Viết test bằng `ApplicationContextRunner`** cho cả tình huống có bean người dùng, không có bean người dùng và bean có return type rộng.
5. **Xem Condition Evaluation Report**: chạy ứng dụng Spring Boot với `--debug`, hoặc dùng `ConditionEvaluationReportLoggingListener` trong test, để biết lý do `OnBeanCondition` khớp/không khớp. Khi ứng dụng có Actuator và endpoint được bật/expose phù hợp, `/actuator/conditions` cũng có thể giúp phân tích.
6. **Đối chiếu bean definition với instance**: một phép tra cứu sau khi refresh có thể thấy kiểu cụ thể mà điều kiện trước khi refresh không thấy.

Nếu phụ thuộc là tùy chọn và có thể hoàn toàn không tồn tại trên classpath, cần xử lý riêng việc tải lớp: đặt `@ConditionalOnClass` trên lớp cấu hình riêng (thường là nested `@Configuration`) để tránh JVM phải xử lý chữ ký `@Bean` chứa kiểu vắng mặt trước khi điều kiện trên phương thức được kiểm tra. Đó là vấn đề classpath/bytecode, khác với việc interface che khuất implementation.

## 8. Câu hỏi tự kiểm tra

**Câu 1.** Một `@Bean PaymentGateway gateway()` trả về `new StripeGateway()`. Khi `@ConditionalOnBean(StripeGateway.class)` được đánh giá trước khi singleton khởi tạo, có thể kết luận chắc chắn điều kiện khớp không?  
**Đáp án:** Không. Return type chỉ công khai `PaymentGateway`; thông tin `StripeGateway` có thể chưa được suy luận. Cần kiểm tra kiểu khai báo, các nguồn metadata khác và thời điểm đánh giá.

**Câu 2.** Nếu muốn fallback `DefaultPaymentGateway` chỉ xuất hiện khi chưa có *bất kỳ* `PaymentGateway` nào, nên viết thế nào?  
**Đáp án:** `@Bean @ConditionalOnMissingBean(PaymentGateway.class) DefaultPaymentGateway defaultGateway() { ... }`. Cách này vừa có return type cụ thể vừa có target theo interface đúng chính sách.

**Câu 3.** Thêm `@Primary` cho bean người dùng có chắc ngăn auto-configuration tạo fallback không?  
**Đáp án:** Không. `@Primary` thường chi phối chọn dependency khi có nhiều ứng viên, không làm condition kiểm tra implementation bị thiếu thông tin kiểu trở thành khớp.

**Câu 4.** Vì sao `getBeansOfType(StripeGateway.class)` sau khi context khởi động có thể cho kết quả khác đánh giá condition trước đó?  
**Đáp án:** Sau khi singleton được tạo, runtime type có thể đã được biết; điều kiện đăng ký bean được quyết định ở giai đoạn sớm hơn.

## 9. Điều cần nhớ

**Kiểu trả về của phương thức `@Bean` là thông tin thiết kế quan trọng trong `BeanDefinition`, không chỉ là kiểu Java dùng cho compiler.** Khi viết auto-configuration, hãy công khai kiểu cụ thể đủ hữu ích trong chữ ký; đồng thời ghi rõ kiểu mà điều kiện phải tìm theo đúng ý nghĩa nghiệp vụ. Kiểm tra cả chữ ký và thứ tự xử lý cấu hình trước khi kết luận rằng Spring Boot “không nhìn thấy” hoặc “tự tạo trùng” bean.

### Tài liệu tham khảo

- [Spring Boot — Creating Your Own Auto-configuration, mục Bean Conditions](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
