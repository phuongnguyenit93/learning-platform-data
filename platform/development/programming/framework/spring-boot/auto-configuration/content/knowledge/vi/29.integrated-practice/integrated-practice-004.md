# Thêm bean người dùng rồi kiểm chứng hành vi nhường chỗ theo kiểu và theo tên

## 1. Mục tiêu của bài thực hành

Auto-configuration thường cung cấp bean mặc định để ứng dụng có thể dùng starter ngay sau khi thêm dependency. Nhưng khi ứng dụng đã tự khai báo bean tương ứng, starter cần nhường chỗ để không tạo hai implementation cạnh tranh.

Spring Boot cung cấp **@ConditionalOnMissingBean** để thực hiện quy tắc này. Annotation có thể kiểm tra sự vắng mặt theo **kiểu bean** hoặc theo **tên bean**. Hai cách kiểm tra có ý nghĩa khác nhau:

- Theo kiểu: nếu context đã có bean tương thích với kiểu được chỉ định, bean mặc định không được đăng ký, bất kể bean người dùng mang tên gì.
- Theo tên: nếu context đã có bean mang tên được chỉ định, bean mặc định không được đăng ký, bất kể bean đó có đúng kiểu mà consumer mong đợi hay không.

Bài này hướng dẫn tạo bean do ứng dụng sở hữu, quan sát cách auto-configuration back off và kiểm chứng bằng **ApplicationContextRunner**. Ví dụ dùng Java 17+, Maven và Spring Boot 3.3.13.

Sau bài này, bạn có thể:

1. Phân biệt điều kiện thiếu bean theo type và theo name.
2. Tạo bean người dùng bằng **@Bean** trong configuration riêng.
3. Xác nhận bean mặc định có được đăng ký hay không.
4. Nhận diện trường hợp cùng type nhưng khác name và cùng name nhưng khác type.
5. Chọn cách kiểm tra phù hợp với hợp đồng bean mà starter công bố.

## 2. Bean do người dùng khai báo và cơ chế back-off

Giả sử starter cung cấp một interface **CatalogClient** cùng implementation mặc định. Nếu ứng dụng không khai báo client, starter tạo client mặc định. Nếu ứng dụng tự cung cấp **CatalogClient**, starter lùi lại.

Mẫu phổ biến:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient() {
    return new DefaultCatalogClient();
}
```

Điều kiện trên được hiểu là: chỉ đăng ký bean này khi chưa có bean phù hợp với **CatalogClient**.

### 2.1. Back-off không phải ghi đè hoặc xóa bean

**@ConditionalOnMissingBean** chỉ quyết định bean mặc định có được đăng ký hay không. Nó không:

- Xóa bean người dùng đã đăng ký.
- Thay implementation của bean người dùng.
- Đổi tên bean người dùng.
- Đặt bean mặc định thành **@Primary**.
- Tự giải quyết mọi xung đột giữa các bean cùng type.

Nếu bean người dùng đã tồn tại và condition không khớp, auto-configuration không tạo bean mặc định. Bean do ứng dụng sở hữu vẫn được giữ nguyên.

Đây là lý do test cần xác nhận cả hai phía: bean mặc định không xuất hiện và bean người dùng thực sự được sử dụng.

### 2.2. Vì sao thường đặt điều kiện trong auto-configuration?

**@ConditionalOnMissingBean** được thiết kế đặc biệt cho auto-configuration. Condition chỉ có thể đánh giá các bean definition đã được xử lý tại thời điểm nó chạy.

Spring Boot xử lý cấu hình ứng dụng trước các auto-configuration được import theo cơ chế chuẩn. Vì vậy, bean do ứng dụng khai báo thường đã được nhìn thấy khi auto-configuration quyết định có tạo bean mặc định hay không.

Nếu tự tạo một configuration thông thường và import nó theo thứ tự tùy ý, không nên giả định mọi bean người dùng luôn được xử lý trước. Khi có nhiều auto-configuration phụ thuộc thứ tự, dùng cơ chế ordering như **@AutoConfiguration(after = ...)** hoặc **@AutoConfiguration(before = ...)** khi thật sự cần thiết.

## 3. Kiểm tra thiếu bean theo kiểu

### 3.1. Cú pháp

Có thể chỉ định kiểu bằng class literal:

```java
@ConditionalOnMissingBean(CatalogClient.class)
```

Hoặc dùng thuộc tính tường minh:

```java
@ConditionalOnMissingBean(value = CatalogClient.class)
```

Với kiểu không thể tham chiếu trực tiếp trong source vì dependency là tùy chọn, có thể dùng tên class:

```java
@ConditionalOnMissingBean(type = "com.acme.catalog.CatalogClient")
```

**value/type** mô tả kiểu cần kiểm tra. Nếu context đã có bean có thể gán cho kiểu đó, condition không khớp và bean mặc định được bảo vệ bởi condition sẽ không được tạo.

### 3.2. Bean cùng type nhưng tên khác vẫn làm starter back off

Ví dụ ứng dụng khai báo:

```java
@Configuration(proxyBeanMethods = false)
class UserCatalogConfiguration {

    @Bean
    CatalogClient customCatalogClient() {
        return () -> "application-client";
    }
}
```

Tên bean mặc định do Spring suy ra từ method là **customCatalogClient**. Tên này khác **catalogClient**, nhưng object vẫn triển khai **CatalogClient**.

Với condition:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient() {
    return () -> "starter-default";
}
```

Spring Boot nhận diện bean người dùng theo type. Bean mặc định không được đăng ký, dù hai bean method có tên khác nhau.

Đây thường là hành vi mong muốn khi contract của thư viện là “ứng dụng có thể cung cấp implementation khác của interface này”.

### 3.3. Type matching dựa trên kiểu có thể dự đoán

Spring cần biết kiểu bean từ bean definition hoặc metadata mà nó có thể dự đoán. Vì vậy, hãy khai báo kiểu trả về của **@Bean** đủ cụ thể:

```java
@Bean
CatalogClient customCatalogClient() {
    return new CustomCatalogClient();
}
```

Không nên khai báo **Object** nếu hợp đồng thực sự là **CatalogClient**:

```java
@Bean
Object customCatalogClient() {
    return new CustomCatalogClient();
}
```

Khi chỉ công bố return type là **Object**, Spring có thể không nhận diện được kiểu mục tiêu từ metadata tại thời điểm condition được đánh giá. Khai báo return type theo interface công khai giúp type-based condition hoạt động dễ dự đoán và giúp consumer biết bean cung cấp contract nào.

### 3.4. Type là lựa chọn tự nhiên cho service contract

Ưu tiên kiểm tra theo type khi:

- Ứng dụng được phép thay implementation của một interface.
- Consumer inject bean theo type.
- Tên bean chỉ là chi tiết đặt tên trong configuration.
- Starter muốn back off khi có bất kỳ implementation tương thích nào.
- Người dùng có thể đặt tên bean theo quy ước riêng của ứng dụng.

Ví dụ thường gặp là **DataSource**, **ObjectMapper**, **Clock**, client interface hoặc một service contract do starter công bố.

## 4. Kiểm tra thiếu bean theo tên

### 4.1. Cú pháp

Có thể chỉ định một hoặc nhiều bean name:

```java
@ConditionalOnMissingBean(name = "catalogAudit")
```

Condition này hỏi liệu bean có tên **catalogAudit** đã tồn tại hay chưa. Nó không yêu cầu bean đó phải có kiểu **CatalogAudit**.

Nếu bean name được chỉ định đã tồn tại, bean mặc định được bảo vệ sẽ không được đăng ký.

### 4.2. Cùng tên nhưng khác type vẫn làm starter back off

Ứng dụng có thể khai báo:

```java
@Configuration(proxyBeanMethods = false)
class UserAuditConfiguration {

    @Bean(name = "catalogAudit")
    String catalogAuditMarker() {
        return "owned-by-application";
    }
}
```

Bean có tên **catalogAudit** nhưng kiểu thực tế là **String**.

Với condition:

```java
@Bean(name = "catalogAudit")
@ConditionalOnMissingBean(name = "catalogAudit")
CatalogAudit catalogAudit() {
    return new CatalogAudit("starter-default");
}
```

Condition theo tên nhìn thấy bean name đã tồn tại và không đăng ký **CatalogAudit** mặc định. Nó không kiểm tra xem bean có phải **CatalogAudit** hay không.

Đây là khác biệt cốt lõi giữa hai cách kiểm tra. Nếu consumer cần **CatalogAudit** nhưng một bean khác type vô tình chiếm tên đó, ứng dụng có thể không có bean cần thiết và gặp lỗi khi inject.

### 4.3. Cùng type nhưng tên khác không làm name-based condition back off

Giả sử ứng dụng khai báo:

```java
@Bean
CatalogAudit customCatalogAudit() {
    return new CatalogAudit("application");
}
```

Tên bean là **customCatalogAudit**, không phải **catalogAudit**.

Nếu auto-configuration dùng:

```java
@Bean(name = "catalogAudit")
@ConditionalOnMissingBean(name = "catalogAudit")
CatalogAudit catalogAudit() {
    return new CatalogAudit("starter-default");
}
```

thì condition theo tên vẫn khớp vì bean mang tên **catalogAudit** chưa tồn tại. Kết quả là context có hai bean cùng kiểu **CatalogAudit**:

- **customCatalogAudit**
- **catalogAudit**

Nếu một consumer inject **CatalogAudit** mà không dùng qualifier hoặc primary, Spring có thể báo **NoUniqueBeanDefinitionException**.

Do đó, name-based condition không phải cách thay thế cho type-based condition khi mục tiêu là “ứng dụng có thể cung cấp implementation cùng interface”.

### 4.4. Khi nào name-based condition phù hợp?

Kiểm tra theo tên có thể hợp lý khi tên bean là một phần contract có chủ ý, ví dụ:

- Một bean marker có tên cố định được nhiều module cùng nhận diện.
- Một resource hoặc infrastructure bean có identity được công bố theo tên.
- Thư viện cần nhường chỗ cho bean mang đúng tên đã tài liệu hóa, dù implementation type có thể khác.
- Một hệ thống có nhiều bean cùng type và việc lựa chọn được quản lý bằng tên/qualifier.

Nếu tên bean không phải contract công khai, đừng buộc người dùng phải biết tên method nội bộ của starter.

Khi dùng name-based condition, hãy cố định tên rõ ràng trong **@Bean(name = "...")** thay vì vô tình dựa vào tên method. Tài liệu hóa tên đó và kiểm thử rằng tên được giữ ổn định giữa các phiên bản.

## 5. So sánh trực tiếp type và name

| Tình huống bean người dùng | Condition theo type CatalogClient.class | Condition theo tên catalogClient |
|---|---|---|
| Có CatalogClient tên customCatalogClient | Back off | Không back off |
| Có CatalogClient tên catalogClient | Back off | Back off |
| Có String tên catalogClient | Không back off theo type | Back off theo tên |
| Có CatalogAudit tên customCatalogAudit | Không liên quan tới CatalogClient | Không back off nếu condition kiểm tra tên catalogAudit |
| Không có bean tương ứng | Đăng ký default | Đăng ký default |

Bảng này giả định mỗi cột đang kiểm tra đúng type/name được ghi ở tiêu đề. Nếu annotation chỉ định nhiều điều kiện, hãy đọc toàn bộ thuộc tính của annotation thay vì suy ra từ một thuộc tính riêng.

Một cách nhớ:

- **Type condition hỏi:** “Đã có implementation nào của contract này chưa?”
- **Name condition hỏi:** “Đã có bean mang identity này chưa?”

## 6. Ví dụ Maven hoàn chỉnh với Spring Boot 3.3.13

Ví dụ dùng hai bean contract độc lập để kiểm tra hai chiến lược trong cùng một auto-configuration:

- **CatalogClient** có default bean condition theo type.
- **CatalogAudit** có default bean condition theo name.

Hai bean có mục đích riêng để test không gây trùng tên. Trong một starter thực tế, chọn chiến lược theo hợp đồng của từng bean; không đăng ký hai default implementation cạnh tranh cho cùng một trách nhiệm.

### 6.1. Cấu trúc dự án

```text
bean-backoff-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/catalog/
    │   │   ├── CatalogClient.java
    │   │   └── CatalogAudit.java
    │   ├── java/com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/catalog/autoconfigure/
        └── CatalogAutoConfigurationTests.java
```

### 6.2. pom.xml

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
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>bean-backoff-demo</artifactId>
    <version>1.0.0</version>

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

### 6.3. CatalogClient.java

```java
package com.acme.catalog;

public interface CatalogClient {

    String source();
}
```

Interface này là contract theo type. Ứng dụng có thể cung cấp bất kỳ implementation nào miễn là đáp ứng **CatalogClient**.

### 6.4. CatalogAudit.java

```java
package com.acme.catalog;

public record CatalogAudit(String source) {
}
```

Record này là kiểu thứ hai để minh họa một bean có identity được kiểm tra theo tên.

### 6.5. CatalogAutoConfiguration.java

```java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.CatalogAudit;
import com.acme.catalog.CatalogClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient() {
        return () -> "starter-default-client";
    }

    @Bean(name = "catalogAudit")
    @ConditionalOnMissingBean(name = "catalogAudit")
    CatalogAudit catalogAudit() {
        return new CatalogAudit("starter-default-audit");
    }
}
```

Phân tích:

1. **catalogClient()** chỉ được tạo nếu chưa có bean tương thích với **CatalogClient**.
2. **catalogAudit()** chỉ được tạo nếu bean name **catalogAudit** chưa tồn tại.
3. Hai condition độc lập; một bean **CatalogClient** không ảnh hưởng tới điều kiện của **CatalogAudit**.
4. Tên **catalogAudit** được khai báo rõ bằng **@Bean(name = ...)**, nên không phụ thuộc vào việc đổi tên method Java.
5. Return type của bean method thể hiện contract mà Spring có thể dự đoán khi đánh giá condition.

### 6.6. AutoConfiguration.imports

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Spring Boot dùng file này để phát hiện auto-configuration. Trong test, **AutoConfigurations.of(...)** gọi class trực tiếp nên không phụ thuộc vào resource imports; resource vẫn cần có khi đóng gói starter để consumer tự động phát hiện.

## 7. Kiểm thử với ApplicationContextRunner

Mỗi test tạo một context độc lập. User configuration được cung cấp qua **withUserConfiguration(...)**, còn auto-configuration được đưa vào runner bằng **AutoConfigurations.of(...)**.

### 7.1. CatalogAutoConfigurationTests.java

```java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.CatalogAudit;
import com.acme.catalog.CatalogClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void createsDefaultsWhenNoUserBeansExist() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CatalogClient.class);
            assertThat(context).hasSingleBean(CatalogAudit.class);

            assertThat(context.getBean(CatalogClient.class).source())
                    .isEqualTo("starter-default-client");

            assertThat(context.getBean("catalogAudit", CatalogAudit.class)
                    .source())
                    .isEqualTo("starter-default-audit");
        });
    }

    @Test
    void typeConditionBacksOffForUserBeanWithDifferentName() {
        runner.withUserConfiguration(UserCatalogClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context).doesNotHaveBean("catalogClient");

                    assertThat(context.getBean(CatalogClient.class).source())
                            .isEqualTo("application-client");
                });
    }

    @Test
    void nameConditionBacksOffForSameNameEvenWhenTypeIsDifferent() {
        runner.withUserConfiguration(AuditNameCollisionConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CatalogAudit.class);

                    assertThat(context.getBean("catalogAudit"))
                            .isEqualTo("owned-by-application");
                });
    }

    @Test
    void nameConditionDoesNotBackOffForSameTypeWithDifferentName() {
        runner.withUserConfiguration(UserAuditDifferentNameConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    assertThat(context.getBeansOfType(CatalogAudit.class))
                            .hasSize(2);

                    assertThat(context.getBean(
                            "customCatalogAudit",
                            CatalogAudit.class).source())
                            .isEqualTo("application-audit");

                    assertThat(context.getBean(
                            "catalogAudit",
                            CatalogAudit.class).source())
                            .isEqualTo("starter-default-audit");
                });
    }

    @Test
    void nameConditionBacksOffForSameNameAndSameType() {
        runner.withUserConfiguration(UserAuditSameNameConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogAudit.class);

                    assertThat(context.getBean(
                            "catalogAudit",
                            CatalogAudit.class).source())
                            .isEqualTo("application-audit");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogClientConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return () -> "application-client";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AuditNameCollisionConfiguration {

        @Bean(name = "catalogAudit")
        String catalogAuditMarker() {
            return "owned-by-application";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditDifferentNameConfiguration {

        @Bean
        CatalogAudit customCatalogAudit() {
            return new CatalogAudit("application-audit");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditSameNameConfiguration {

        @Bean(name = "catalogAudit")
        CatalogAudit customCatalogAudit() {
            return new CatalogAudit("application-audit");
        }
    }
}
```

### 7.2. Giải thích năm test

| Test | Bean người dùng | Condition được quan sát | Kết quả |
|---|---|---|---|
| **createsDefaultsWhenNoUserBeansExist** | Không có | Type và name | Cả hai default được tạo |
| **typeConditionBacksOffForUserBeanWithDifferentName** | CatalogClient tên customCatalogClient | Theo type | Default client không được tạo |
| **nameConditionBacksOffForSameNameEvenWhenTypeIsDifferent** | String tên catalogAudit | Theo name | Default audit không được tạo |
| **nameConditionDoesNotBackOffForSameTypeWithDifferentName** | CatalogAudit tên customCatalogAudit | Theo name | Default audit vẫn được tạo; có hai bean cùng type |
| **nameConditionBacksOffForSameNameAndSameType** | CatalogAudit tên catalogAudit | Theo name | Default audit không được tạo |

Test thứ ba là trường hợp dễ gây bất ngờ: tên đã tồn tại nên condition nhường chỗ, dù type không phù hợp. Test thứ tư cho thấy chiều ngược lại: type đã tồn tại nhưng tên khác, vì vậy name-based condition vẫn cho phép default.

### 7.3. Chạy kiểm thử

Dùng JDK 17+ và Maven trong thư mục có **pom.xml**:

```bash
mvn test
```

Với năm test trên, kết quả mong đợi:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là kết quả kỳ vọng từ ví dụ, không phải log của một lần chạy đã thực thi. Các test chỉ tạo ApplicationContext và kiểm tra bean; chúng không khởi động server hoặc gọi dịch vụ ngoài.

## 8. Quy tắc thiết kế khi dùng hai chiến lược

### 8.1. Ưu tiên type-based condition cho service

Với một service contract, interface hoặc abstraction mà consumer inject theo type, thường nên dùng:

```java
@ConditionalOnMissingBean(CatalogClient.class)
```

Lợi ích:

- Ứng dụng có thể đặt tên bean theo quy ước riêng.
- Mọi implementation tương thích đều có thể thay thế default.
- Condition diễn đạt đúng ý định “đã có service này chưa?”.
- Người đọc không cần biết tên bean method nội bộ của starter.

Hãy dùng interface công khai làm kiểu kiểm tra nếu muốn cho phép nhiều implementation khác nhau. Kiểm tra một class implementation cụ thể sẽ làm hợp đồng thay thế hẹp hơn.

### 8.2. Chỉ dùng name-based condition khi identity theo tên là chủ đích

Dùng:

```java
@ConditionalOnMissingBean(name = "catalogAudit")
```

khi bean name **catalogAudit** được tài liệu hóa như một identity ổn định. Cần giải thích:

- Bean name đó đại diện cho tài nguyên hoặc vai trò nào.
- Consumer có được inject bằng **@Qualifier("catalogAudit")** hay lookup theo tên không.
- Bean khác type nhưng trùng tên có được phép thay thế không.
- Đổi tên bean có phải breaking change không.

Nếu không muốn bean khác type chiếm chỗ, name-only condition có thể quá rộng. Cân nhắc kiểm tra type, hoặc kết hợp điều kiện theo contract cụ thể với thiết kế bean name phù hợp.

### 8.3. Đừng nhầm back-off với @Primary

**@Primary** ảnh hưởng việc Spring chọn candidate khi có nhiều bean cùng type để inject. Nó không ngăn bean mặc định được đăng ký.

Ví dụ nếu có hai **CatalogClient**, đánh dấu bean người dùng **@Primary** có thể làm injection theo type chọn bean đó, nhưng cả hai bean vẫn tồn tại. **@ConditionalOnMissingBean(CatalogClient.class)** giải quyết vấn đề sớm hơn bằng cách không tạo default khi contract đã có.

### 8.4. Chú ý tên mặc định của @Bean method

Nếu không đặt tên tường minh, tên bean mặc định thường lấy từ tên method:

```java
@Bean
CatalogAudit catalogAudit() {
    return new CatalogAudit("starter");
}
```

Tên bean khi đó là **catalogAudit**. Đổi tên method có thể làm tên bean thay đổi.

Nếu name-based condition dựa vào tên đó, hãy khai báo tên rõ ràng:

```java
@Bean(name = "catalogAudit")
@ConditionalOnMissingBean(name = "catalogAudit")
CatalogAudit createCatalogAudit() {
    return new CatalogAudit("starter");
}
```

Cách này tách identity của bean khỏi tên method Java. Tuy nhiên, tên tường minh chỉ hữu ích khi thư viện thực sự muốn cam kết name đó cho consumer.

## 9. Ordering và phạm vi tìm kiếm

### 9.1. Condition chỉ thấy bean definition đã được xử lý

**@ConditionalOnMissingBean** không phải một truy vấn cuối cùng trên toàn bộ cấu hình tương lai. Nó đánh giá trạng thái bean factory tại thời điểm condition được xử lý.

Vì vậy:

- Dùng nó trong auto-configuration để user bean có cơ hội được đăng ký trước.
- Tránh đặt condition trong cấu hình được import quá sớm nếu bean người dùng chưa được xử lý.
- Khi hai auto-configuration phụ thuộc nhau, dùng **before/after** để khai báo ordering.
- Không dựa vào thứ tự ngẫu nhiên giữa các configuration class.

### 9.2. Bean definition và kiểu trả về

Khi đánh giá type-based condition, Spring cố gắng xác định type từ bean definition, factory method return type hoặc metadata. Đừng che giấu contract bằng return type quá chung như **Object** nếu consumer và condition đều cần một interface cụ thể.

Với factory method trả về interface, Spring có thể nhận diện contract mà không cần khởi tạo object chỉ để đoán type. Điều này giúp điều kiện hoạt động ổn định hơn và tránh khởi tạo sớm bean có side effect.

### 9.3. Context hierarchy

Trong ứng dụng có parent/child ApplicationContext, phạm vi tìm kiếm bean có thể ảnh hưởng kết quả. **@ConditionalOnMissingBean** cung cấp thuộc tính **search** với các chiến lược tìm kiếm context. Hãy đọc Javadoc của phiên bản Spring Boot đang dùng và chọn phạm vi phù hợp với kiến trúc context.

Không mặc định rằng bean trong mọi context cha/con đều có tác động giống nhau trong mọi cấu hình. Nếu ứng dụng có context hierarchy, hãy thêm test riêng cho bean ở parent và child thay vì chỉ kiểm tra một context phẳng.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Starter vẫn tạo default dù ứng dụng đã có implementation | Dùng name condition nhưng user bean có tên khác | Dùng type condition cho service contract |
| Default biến mất dù không có bean đúng type | Name condition bị một bean khác type chiếm tên | Kiểm tra bean name; dùng type condition nếu mục tiêu là contract |
| Có hai bean cùng type sau khi override | Name condition không nhận ra user bean cùng type nhưng tên khác | Dùng **@ConditionalOnMissingBean(TargetType.class)** |
| Context báo **NoUniqueBeanDefinitionException** | Default và user bean cùng type đều tồn tại | Sửa condition; chỉ dùng **@Primary** nếu thật sự muốn giữ nhiều candidate |
| Type condition không nhận diện user bean | **@Bean** method công bố return type quá chung | Khai báo return type là interface/contract thực tế |
| Condition chạy trước user configuration | Ordering hoặc cách import không phù hợp | Dùng auto-configuration đúng cơ chế và kiểm tra ordering |
| Đổi tên method làm consumer lookup thất bại | Bean name suy ra từ method nhưng bị dùng như contract | Khai báo **@Bean(name=...)** và tài liệu hóa nếu tên phải ổn định |
| Test chỉ kiểm tra có bean mà không kiểm tra nguồn bean | Test không chứng minh back-off thực sự | Assert tên/type và hành vi từ bean người dùng |
| Nghĩ **@Primary** ngăn default được tạo | Nhầm injection preference với bean registration condition | Dùng **@ConditionalOnMissingBean** để kiểm soát việc đăng ký |
| Name-only condition làm mất bean cần inject | Một bean khác type nhưng trùng tên đã làm condition back off | Kiểm tra type và name trong context; chọn condition phù hợp |

## 11. Quy trình thực hành và kiểm tra

Khi bổ sung customization cho auto-configuration:

1. Xác định contract mà ứng dụng muốn thay: interface/type hay một bean identity cụ thể.
2. Nếu thay service theo interface, dùng **@ConditionalOnMissingBean(ContractType.class)**.
3. Nếu thay theo identity, dùng **@ConditionalOnMissingBean(name = "...")** và tài liệu hóa tên.
4. Đặt condition trên bean mặc định hoặc configuration group phù hợp.
5. Đảm bảo user configuration được xử lý trước auto-configuration.
6. Khai báo return type của **@Bean** theo contract cụ thể.
7. Viết test không có user bean để xác nhận default xuất hiện.
8. Viết test có cùng type nhưng tên khác để kiểm tra type-based back-off.
9. Viết test có cùng name nhưng type khác để quan sát name-based back-off.
10. Viết test cùng type nhưng tên khác cho name-based condition để phát hiện hai bean cùng type.
11. Kiểm tra bean thực tế được inject hoặc lookup là bean người dùng.
12. Nếu có parent/child context, kiểm thử phạm vi **search** riêng.
13. Đọc Condition Evaluation Report khi condition khớp hoặc không khớp ngoài dự kiến.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** **@ConditionalOnMissingBean(CatalogClient.class)** kiểm tra điều gì?

**Đáp án:** Kiểm tra chưa có bean tương thích với type **CatalogClient**. Bean cùng type dù tên khác vẫn làm default back off.

**Câu 2.** **@ConditionalOnMissingBean(name = "catalogAudit")** kiểm tra điều gì?

**Đáp án:** Kiểm tra chưa có bean mang tên **catalogAudit**. Condition theo tên không yêu cầu bean đó có type **CatalogAudit**.

**Câu 3.** Nếu user cung cấp **CatalogClient** tên **customCatalogClient**, type-based condition có back off không?

**Đáp án:** Có, vì bean tương thích theo type đã tồn tại.

**Câu 4.** Nếu user cung cấp **String** tên **catalogAudit**, name-based condition có back off không?

**Đáp án:** Có. Tên đã tồn tại, dù type không phải **CatalogAudit**.

**Câu 5.** Nếu user cung cấp **CatalogAudit** tên **customCatalogAudit**, name-based condition kiểm tra **catalogAudit** có back off không?

**Đáp án:** Không. Bean cùng type nhưng tên khác không thỏa điều kiện thiếu tên **catalogAudit**; default vẫn được đăng ký.

**Câu 6.** Vì sao nên khai báo return type của user **@Bean** theo interface thực tế?

**Đáp án:** Để Spring có thể dự đoán type từ bean definition khi đánh giá condition và để contract rõ ràng với consumer.

**Câu 7.** **@Primary** có ngăn auto-configuration tạo bean mặc định không?

**Đáp án:** Không. **@Primary** chỉ ảnh hưởng lựa chọn injection khi có nhiều candidate; **@ConditionalOnMissingBean** mới kiểm soát việc đăng ký default.

**Câu 8.** Khi nào nên dùng name-based condition?

**Đáp án:** Khi bean name là identity ổn định, được công bố và có ý nghĩa độc lập với type. Với service contract thông thường, type-based condition thường phù hợp hơn.

## 13. Ghi nhớ

- **@ConditionalOnMissingBean(CatalogClient.class)** kiểm tra theo type; bean cùng type tên khác vẫn làm default back off.
- **@ConditionalOnMissingBean(name = "catalogAudit")** kiểm tra theo tên; bean khác type nhưng cùng tên vẫn làm default back off.
- Name-based condition không phát hiện bean cùng type nếu tên khác; có thể dẫn đến hai bean cùng type.
- Type-based condition phù hợp với service/interface contract mà ứng dụng có thể thay implementation.
- Name-based condition phù hợp khi tên bean là identity được công bố và cần giữ ổn định.
- Khai báo return type của **@Bean** theo contract cụ thể để type condition dự đoán được bean.
- **@ConditionalOnMissingBean** chỉ quyết định đăng ký default; nó không xóa hoặc ghi đè bean người dùng.
- **@Primary** điều khiển lựa chọn injection, không thay thế back-off condition.
- Đặt condition trong auto-configuration và chú ý thứ tự xử lý bean definition.
- Kiểm thử đủ trường hợp cùng type/khác tên, cùng tên/khác type và không có user bean.

### Tài liệu chính thức

- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Framework 6.1 — Bean Definition and Factory Methods](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
