# Giữ khóa điều khiển bật tắt nhất quán với cấu hình được tạo

> **Spring Boot Auto Configuration → Thuộc tính thư viện.** Bài học trình bày cách thiết kế một khóa `enabled` rõ ràng cho thư viện/starter, bảo đảm cùng một khóa được sử dụng trong tài liệu, `@ConditionalOnProperty`, `@ConfigurationProperties`, auto-configuration tạo bean và bài kiểm thử. Ví dụ dùng Java 17+ và Spring Boot 3.3.x.

## 1. Vấn đề: người dùng bật một khóa nhưng thư viện lại kiểm tra khóa khác

Một thư viện tích hợp có thể công bố:

~~~yaml
demo:
  notice:
    enabled: true
    message: "Welcome"
~~~

Người sử dụng kỳ vọng: đặt `demo.notice.enabled=true` thì Spring Boot tạo bean gửi thông báo; đặt `false` thì bean mặc định của thư viện không được tạo.

Thực tế rất dễ phát sinh **sự lệch giữa khóa công bố và khóa điều kiện**, ví dụ:

~~~java
// Tài liệu hướng dẫn người dùng: demo.notice.enabled=true
// Nhưng auto-configuration lại kiểm tra một prefix khác.
@ConditionalOnProperty(
    prefix = "demo.notification",
    name = "enabled",
    havingValue = "true"
)
~~~

Khi đó `demo.notice.enabled=true` **không kích hoạt** cấu hình vì annotation đọc `demo.notification.enabled`. Ứng dụng có thể vẫn chạy, nhưng bean mong đợi vắng mặt; lỗi không nằm ở cú pháp YAML mà ở **hợp đồng cấu hình không nhất quán**.

Lệch cũng xảy ra khi:
- `@ConfigurationProperties(prefix="demo.notice")` bind `enabled` trong khi condition đọc `demo.notice.active`.
- Tài liệu ghi `notice.enabled` nhưng code kiểm tra `demo.notice.enabled`.
- Trường Java mặc định `enabled=true` nhưng `@ConditionalOnProperty` dùng `matchIfMissing=false`, khiến thiếu khóa thì **bean không được tạo**.
- Condition kiểm tra `enabled=true` nhưng một nhánh `@Bean` tạo dịch vụ ở ngoài phạm vi điều kiện.
- Người dùng đặt `enabled=false` nhưng một auto-configuration khác vẫn tạo bean có cùng chức năng.
- Test chỉ kiểm tra khi `enabled=true` mà không kiểm tra mặc định, false và khóa sai.

**Nguyên tắc cốt lõi:** khóa bật/tắt phải có **một tên công khai ổn định, một chính sách mặc định rõ ràng và một phạm vi tác động xác định**. Điều kiện và cấu hình bean phải cùng thực hiện hợp đồng đó.

## 2. Trước khi viết code: xác định hợp đồng của khóa

Ví dụ thư viện có tên tính năng là *notice*:

| Thành phần hợp đồng | Quyết định minh họa | Ý nghĩa |
| --- | --- | --- |
| Namespace | `demo.notice` | Gom tất cả thuộc tính của một tính năng |
| Khóa bật/tắt | `demo.notice.enabled` | Khóa duy nhất quyết định có tự tạo dịch vụ notice hay không |
| Kiểu dữ liệu | Boolean | Người sử dụng viết `true` hoặc `false` |
| Mặc định | `false` | Tính năng chỉ bật khi người dùng chủ động cho phép |
| Điều kiện Spring Boot | `havingValue="true", matchIfMissing=false` | Cần hiện diện và bằng true để tạo bean |
| Bean chịu điều kiện | `NoticeSender` do auto-configuration cung cấp | Khi tắt, starter không tự cung cấp bean này |
| Thuộc tính đi kèm | `demo.notice.message` | Được sử dụng khi feature bật |
| Hợp đồng ghi đè | Bean người dùng tự khai báo được ưu tiên | `@ConditionalOnMissingBean` tránh tạo bản mặc định trùng lặp |
| Kiểm thử tối thiểu | missing, false, true, sai khóa, message tùy chỉnh | Phát hiện lệch tên, mặc định và bean thực tế |

Không phải thư viện nào cũng phải mặc định tắt. Có thể chọn **mặc định bật** khi tính năng là nền tảng và không gây tác động không mong muốn. Khi đó thay đổi nhất quán phải diễn ra **đồng thời** ở tài liệu, condition, giá trị Java mặc định và test; không chỉ chỉnh một nơi.

### 2.1. Một khóa bật/tắt có hai ý nghĩa cần tách biệt

**Ý nghĩa điều kiện:** Spring có đăng ký bean mặc định của starter hay không? Đây là vai trò của `@ConditionalOnProperty`.

**Ý nghĩa giá trị cấu hình:** bean đang được bind nhận `enabled` và các thuộc tính liên quan với giá trị nào? Đây là vai trò của `@ConfigurationProperties`.

Hai cơ chế nhìn vào cùng một `Environment` nhưng làm việc khác nhau. `@ConditionalOnProperty` thường được đánh giá lúc xử lý định nghĩa bean. `@ConfigurationProperties` bind giá trị vào một object cấu hình. **Binder không tự động đồng bộ quy tắc của condition với giá trị mặc định đặt trong Java object.**

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "demo.notice")
public class NoticeProperties {
    private boolean enabled = true;
}
~~~

Nếu auto-configuration cùng lúc dùng:

~~~java
@ConditionalOnProperty(
    prefix = "demo.notice",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

thì **khi không có property**:
- Giá trị mặc định của trường Java là `true` **nếu object properties được tạo**;
- Nhưng condition đọc `Environment` thấy **không có khóa** và trả về không match;
- Bean nằm sau condition sẽ không được đăng ký.

Do đó **mặc định trong Java object không thay thế `matchIfMissing`**. Nếu hợp đồng yêu cầu mặc định bật thì phải đặt `matchIfMissing=true` và mặc định của `enabled` cũng phản ánh điều đó.

## 3. Quy ước đặt tên: giữ một tên khóa ở mọi lớp

Chọn tên chuẩn dễ đọc, nhóm theo thư viện:

~~~properties
demo.notice.enabled=true
demo.notice.message=Welcome
~~~

Trong YAML:

~~~yaml
demo:
  notice:
    enabled: true
    message: Welcome
~~~

Các trường hợp dễ nhầm:

| Tài liệu / giá trị người dùng đặt | Annotation thực tế tìm | Kết quả |
| --- | --- | --- |
| `demo.notice.enabled=true` | `demo.notice.enabled` | Match khi `havingValue="true"` |
| `demo.notice.enabled=true` | `demo.notification.enabled` | Không match vì sai prefix |
| `demo.notice.active=true` | `demo.notice.enabled` | Không match vì sai name |
| `demo.notice.enabled=false` | `demo.notice.enabled` | Không match đúng chính sách |
| Không khai báo `demo.notice.enabled` | `demo.notice.enabled` | Không match khi `matchIfMissing=false` |

**Dùng tên thuộc tính chuẩn dạng kebab-case** cho các khóa có nhiều từ, như `retry-enabled`, `connection-timeout`. Khi sử dụng `@ConfigurationProperties`, Spring Boot hỗ trợ *relaxed binding* cho một số biến thể tên, nhưng đừng biến khả năng này thành lý do công bố nhiều tên không thống nhất. Tên trong tài liệu và code nên có một cách viết chuẩn.

Đối với biến môi trường, Spring Boot có quy ước ánh xạ tên kiểu `DEMO_NOTICE_ENABLED` sang khóa tương ứng khi lấy từ system environment. Với một danh sách property có nhiều cấp, cách đặt prefix cố định giúp tránh xung đột với tính năng khác.

## 4. Chọn chính sách bật/tắt: bảng chân trị

Giả sử `@ConditionalOnProperty(prefix="demo.notice", name="enabled", havingValue="true")` với `matchIfMissing=false`.

| `demo.notice.enabled` | Có match? | Có tạo bean mặc định của auto-config? |
| --- | --- | --- |
| `true` | Có | Có, nếu các điều kiện khác cũng thỏa |
| `false` | Không | Không |
| Không tồn tại | Không | Không |
| `foo` | Không | Không |
| Khóa bị viết sai, ví dụ `demo.notice.enable` | Không | Không vì khóa đúng bị thiếu |

Nếu đặt `matchIfMissing=true`, **chỉ hàng “không tồn tại” đổi thành match**. Property hiện diện và bằng `false` vẫn không match.

Tại sao nên khai báo `havingValue="true"` rõ ràng?

~~~java
@ConditionalOnProperty(prefix = "demo.notice", name = "enabled")
~~~

Khi không khai báo `havingValue`, quy tắc mặc định là **khóa tồn tại và giá trị khác `false`**. Một giá trị không mong đợi như `on` hoặc `unexpected` có thể vẫn được coi là match. Với một feature flag thực sự mong boolean, nên sử dụng giá trị chuẩn `true/false` và điều kiện tường minh.

**Cảnh giác với hai ngữ nghĩa chuyển đổi:** `@ConfigurationProperties` có cơ chế chuyển chuỗi sang kiểu Java (ví dụ boolean), còn `@ConditionalOnProperty` so sánh giá trị cấu hình theo quy tắc của annotation. Không nên dựa vào alias boolean không được công bố rõ; dùng `true` / `false` trong file và test để bảo đảm cả điều kiện lẫn binder thống nhất.

## 5. Thiết kế nhất quán từ mã nguồn: tập trung tên khóa

Khi thư viện có nhiều class cùng phụ thuộc một khóa, có thể khai báo **hằng compile-time** để tránh gõ sai giữa condition và properties:

~~~java
package demo.notice;

public final class NoticeKeys {
    public static final String PREFIX = "demo.notice";
    public static final String ENABLED = "enabled";

    private NoticeKeys() {
    }
}
~~~

Hai giá trị trên là hằng chuỗi `public static final`, nên hợp lệ trong các thuộc tính annotation đòi hỏi compile-time constant:

~~~java
@ConditionalOnProperty(
    prefix = NoticeKeys.PREFIX,
    name = NoticeKeys.ENABLED,
    havingValue = "true"
)
~~~

và:

~~~java
@ConfigurationProperties(prefix = NoticeKeys.PREFIX)
~~~

Cả hai luôn dùng **cùng prefix**; việc đặt tên property còn cần nhất quán giữa `ENABLED` và tên field Java `enabled`. Cần ghi khóa đầy đủ `demo.notice.enabled` một lần rõ ràng trong tài liệu. Hằng số giúp ngăn một số lỗi do copy/paste nhưng **không thể thay thế test**: chỉ một bên dùng nhầm `ACTIVE` thay `ENABLED` vẫn làm sai hợp đồng.

Không nhất thiết tạo một class hằng cho mọi dự án nhỏ. Nếu có ít annotation, dùng chuỗi trực tiếp và một bộ kiểm thử rõ ràng cũng phù hợp. Mục tiêu là giảm số nơi có thể vô tình đổi khác tên khóa công khai.

## 6. Ví dụ chạy được: starter notice bật bằng một khóa duy nhất

Xây một ứng dụng Maven Spring Boot 3.3.13 / Java 17 để quan sát:
- Khi thiếu `demo.notice.enabled` → starter **không tự tạo** bean `NoticeSender`;
- Khi `demo.notice.enabled=false` → không tự tạo;
- Khi `demo.notice.enabled=true` → bean được tạo và nhận `message` từ cùng namespace `demo.notice`;
- Khi sai prefix hoặc sai name → không có bean.

Dự án sử dụng `AutoConfiguration.imports` để mô phỏng một thư viện auto-configuration đúng cách. Chúng ta không dùng kết nối mạng hay tài nguyên ngoài. Kết quả có thể quan sát qua stdout.

### 6.1. Cấu trúc dự án

~~~text
notice-toggle-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/
    │   │       ├── app/
    │   │       │   └── NoticeDemoApplication.java
    │   │       └── notice/
    │   │           ├── NoticeKeys.java
    │   │           ├── NoticeProperties.java
    │   │           ├── NoticeSender.java
    │   │           └── autoconfigure/
    │   │               └── NoticeAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── demo/
                └── notice/
                    └── NoticeAutoConfigurationTest.java
~~~

`demo.app` và `demo.notice` là các package ngang cấp, vì vậy `@SpringBootApplication` trong `demo.app` **không tự component-scan** cấu hình thuộc `demo.notice.autoconfigure`. Cấu hình được đưa vào theo **AutoConfiguration.imports**, đúng chủ đích của lab.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>notice-toggle-demo</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. src/main/java/demo/notice/NoticeKeys.java

~~~java
package demo.notice;

public final class NoticeKeys {
    public static final String PREFIX = "demo.notice";
    public static final String ENABLED = "enabled";

    private NoticeKeys() {
    }
}
~~~

Class này là nơi định nghĩa tên chuẩn cho annotation. Chúng ta vẫn phải giữ tên được tài liệu công bố và các test trùng với nó.

### 6.4. src/main/java/demo/notice/NoticeProperties.java

~~~java
package demo.notice;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = NoticeKeys.PREFIX)
public class NoticeProperties {
    private boolean enabled = false;
    private String message = "default-message";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
~~~

`enabled=false` là mặc định **của object Java**. Nó phù hợp với chính sách opt-in; condition ở phần 6.6 cũng sẽ dùng `matchIfMissing=false`. `message` là thuộc tính hỗ trợ được bind cùng prefix. Tên field `enabled` tương ứng với hậu tố `NoticeKeys.ENABLED`.

Không chỉ dùng `@ConfigurationProperties` rồi mong Spring tự tìm mọi class cấu hình. Ở phần tiếp theo, auto-configuration sẽ đăng ký bind bằng `@EnableConfigurationProperties(NoticeProperties.class)`.

### 6.5. src/main/java/demo/notice/NoticeSender.java

~~~java
package demo.notice;

public record NoticeSender(String message) {
}
~~~

Đây là bean dịch vụ đơn giản để lab có đầu ra xác định. `record` là tính năng của Java 17, không cần Lombok. Ứng dụng thực tế có thể thay nó bằng publisher, client, processor hay một adapter khác.

### 6.6. src/main/java/demo/notice/autoconfigure/NoticeAutoConfiguration.java

~~~java
package demo.notice.autoconfigure;

import demo.notice.NoticeKeys;
import demo.notice.NoticeProperties;
import demo.notice.NoticeSender;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(NoticeProperties.class)
@ConditionalOnProperty(
        prefix = NoticeKeys.PREFIX,
        name = NoticeKeys.ENABLED,
        havingValue = "true",
        matchIfMissing = false
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeSender.class)
    NoticeSender noticeSender(NoticeProperties properties) {
        return new NoticeSender(properties.getMessage());
    }
}
~~~

**Ba ràng buộc được giữ nhất quán:**

1. `@ConditionalOnProperty` kiểm tra đúng `demo.notice.enabled`; chỉ khi giá trị là `true` (các điều kiện khác đủ) mới xử lý auto-configuration này.
2. `@EnableConfigurationProperties` bind `NoticeProperties` cùng prefix `demo.notice`. Bean `NoticeSender` nhận `message` qua chính object này.
3. `@ConditionalOnMissingBean(NoticeSender.class)` không tạo bean mặc định nếu ứng dụng đã có bean cùng type phù hợp.

Trong thiết kế minh họa, **điều kiện đặt trên cả class auto-configuration**. Nếu condition không match, cấu hình này **không đăng ký `NoticeProperties` cũng không đăng ký `NoticeSender`** qua các khai báo của nó. Nếu muốn `NoticeProperties` luôn sẵn có để đọc trạng thái ngay cả khi tính năng tắt, có thể chuyển điều kiện xuống một lớp cấu hình lồng nhau hoặc chỉ trên method `@Bean`; hãy chọn và ghi rõ phạm vi muốn bảo vệ.

Lưu ý việc `@ConditionalOnMissingBean` cho phép ứng dụng tự thay thế bean không có nghĩa một bean do **người dùng tự đăng ký** sẽ bị vô hiệu khi `demo.notice.enabled=false`. Nếu yêu cầu “tắt tính năng” phải áp dụng đến mọi provider, cần một thiết kế điều khiển nhất quán cả các provider tùy chỉnh.

### 6.7. src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Nội dung tệp **đúng một dòng**:

~~~text
demo.notice.autoconfigure.NoticeAutoConfiguration
~~~

Đường dẫn và FQCN phải khớp chính xác. Trong Spring Boot 3.3, đây là cơ chế đăng ký auto-configuration cho thư viện. Nếu quên tệp hoặc viết nhầm package, `NoticeAutoConfiguration` có thể **không bao giờ được áp dụng**, dù property `demo.notice.enabled=true`.

### 6.8. src/main/java/demo/app/NoticeDemoApplication.java

~~~java
package demo.app;

import demo.notice.NoticeSender;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NoticeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoticeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ObjectProvider<NoticeSender> senders) {
        return args -> {
            NoticeSender sender = senders.getIfAvailable();
            System.out.println("noticeSender present: " + (sender != null));
            if (sender != null) {
                System.out.println("noticeSender message: " + sender.message());
            }
        };
    }
}
~~~

`ObjectProvider<NoticeSender>` là cách lấy bean **tùy chọn**. Nếu dùng constructor injection bắt buộc cho `NoticeSender` trong một bean luôn được tạo, chương trình có thể khởi động lỗi khi tính năng tắt; đó là vấn đề thiết kế consumer chưa tôn trọng hợp đồng optional, **không phải lỗi của condition**.

### 6.9. Đóng gói và kiểm tra ba trạng thái

Từ thư mục `notice-toggle-demo`:

~~~bash
mvn -q -DskipTests package
~~~

**Ca A — không có khóa:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do `System.out.println` in:

~~~text
noticeSender present: false
~~~

**Ca B — khóa đúng nhưng tắt:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.enabled=false
~~~

Dòng cần quan sát:

~~~text
noticeSender present: false
~~~

**Ca C — khóa đúng và bật, kèm message riêng:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.enabled=true --demo.notice.message=custom-message
~~~

Hai dòng do chương trình in:

~~~text
noticeSender present: true
noticeSender message: custom-message
~~~

**Ca D — người dùng viết sai prefix:**

~~~bash
java -jar target/notice-toggle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notification.enabled=true
~~~

Dòng quan sát:

~~~text
noticeSender present: false
~~~

Ca D cho thấy giá trị `true` **không đủ**; nó phải thuộc **đúng khóa được điều kiện kiểm tra**. Các kết quả trên là các dòng do chương trình chủ động in; log của Maven hoặc startup có thể khác theo môi trường.

Trong PowerShell và Windows CMD có thể dùng nguyên các lệnh Java một dòng như trên; khi dùng Maven wrapper, thay `mvn` bằng `mvnw.cmd` nếu dự án có tệp đó.

## 7. Kiểm thử bằng ApplicationContextRunner: bảo vệ hợp đồng khóa công khai

Một starter nên có test cho chính việc lựa chọn bean. Trong Spring Boot, `ApplicationContextRunner` cho phép chạy context tối giản với property khác nhau và assert kết quả. Test này không yêu cầu chạy cả web server, đồng thời phát hiện lỗi như đổi nhầm `prefix` trong annotation.

**Tệp: `src/test/java/demo/notice/NoticeAutoConfigurationTest.java`**

~~~java
package demo.notice;

import demo.notice.autoconfigure.NoticeAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    NoticeAutoConfiguration.class
            ));

    @Test
    void missingEnabledDoesNotCreateSender() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(NoticeSender.class));
    }

    @Test
    void falseDoesNotCreateSender() {
        runner.withPropertyValues("demo.notice.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeSender.class));
    }

    @Test
    void trueCreatesSenderAndBindsMessage() {
        runner.withPropertyValues(
                "demo.notice.enabled=true",
                "demo.notice.message=custom-message"
        ).run(context -> {
            assertThat(context).hasSingleBean(NoticeSender.class);
            NoticeSender sender = context.getBean(NoticeSender.class);
            assertThat(sender.message()).isEqualTo("custom-message");
            assertThat(context.getBean(NoticeProperties.class).isEnabled())
                    .isTrue();
        });
    }

    @Test
    void wrongPrefixDoesNotEnableSender() {
        runner.withPropertyValues("demo.notification.enabled=true")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeSender.class));
    }

    @Test
    void unknownStringDoesNotEnableSender() {
        runner.withPropertyValues("demo.notice.enabled=unexpected")
                .run(context ->
                        assertThat(context).doesNotHaveBean(NoticeSender.class));
    }
}
~~~

Với `spring-boot-starter-test` trong pom, chạy:

~~~bash
mvn test
~~~

Kỳ vọng **5 test PASS**. Các case cung cấp bằng chứng về **đúng key, đúng prefix, đúng giá trị, đúng chính sách khi thiếu, và message có được bind vào bean được tạo**. Test dùng `@ConditionalOnProperty(havingValue="true")` nên giá trị `unexpected` không match, tránh tạo `NoticeProperties` có thể gây lỗi binding với boolean không hợp lệ.

### 7.1. Test một bean người dùng tự thay thế có ý nghĩa gì?

Với `@ConditionalOnMissingBean(NoticeSender.class)`, nếu user đã tự đăng ký bean `NoticeSender` trước lúc auto-config xét, starter nên nhường cho bean của user. Có thể thêm test sau vào cùng lớp:

~~~java
@Test
void userBeanWinsOverDefaultWhenEnabled() {
    runner.withPropertyValues("demo.notice.enabled=true")
            .withBean(NoticeSender.class,
                    () -> new NoticeSender("user-message"))
            .run(context -> {
                assertThat(context).hasSingleBean(NoticeSender.class);
                assertThat(context.getBean(NoticeSender.class).message())
                        .isEqualTo("user-message");
            });
}
~~~

Đây là **method test bổ sung** (đặt trong lớp `NoticeAutoConfigurationTest` ở trên), không phải tệp Java độc lập. Nó làm rõ phạm vi hợp đồng: khi tính năng bật, thư viện **không ghi đè** bean mà người dùng đã cung cấp.

Nếu tính năng tắt nhưng user vẫn đăng ký `NoticeSender`, context có thể vẫn có bean user. Khi mô tả `enabled=false`, nên nói chính xác **“starter không tự tạo NoticeSender”**, thay vì tuyên bố **“ứng dụng chắc chắn không có NoticeSender”**.

## 8. Mặc định bật và mặc định tắt: sửa theo một bộ thống nhất

### 8.1. Chính sách opt-in: tắt khi không cấu hình

Điều kiện:

~~~java
@ConditionalOnProperty(
    prefix = NoticeKeys.PREFIX,
    name = NoticeKeys.ENABLED,
    havingValue = "true",
    matchIfMissing = false
)
~~~

Giá trị trong `NoticeProperties`:

~~~java
private boolean enabled = false;
~~~

Tài liệu:
- Không khai báo `demo.notice.enabled` → không tự tạo sender.
- `demo.notice.enabled=true` → tạo sender nếu các điều kiện khác thỏa.
- `demo.notice.enabled=false` → không tự tạo sender.

Test phải bao gồm cả **missing** và **false** để ghi lại chính sách này.

### 8.2. Chính sách default-on: bật khi không cấu hình

Nếu product yêu cầu thư viện mặc định hoạt động, thay **đồng bộ**:

~~~java
@ConditionalOnProperty(
    prefix = NoticeKeys.PREFIX,
    name = NoticeKeys.ENABLED,
    havingValue = "true",
    matchIfMissing = true
)
~~~

và:

~~~java
private boolean enabled = true;
~~~

Sau đó đổi tài liệu thành “mặc định bật, có thể tắt bằng `demo.notice.enabled=false`”, và đổi test missing thành kỳ vọng **có** `NoticeSender`. Ca false vẫn phải kỳ vọng không tự tạo bean.

**Sai lầm phổ biến:** chỉ đổi giá trị mặc định của field trong `NoticeProperties` thành `true` mà quên `matchIfMissing=false`. Kết quả lúc chạy vẫn không có bean vì condition chưa bao giờ match.

### 8.3. Không bắt buộc object properties phải tồn tại khi feature tắt

Trong thiết kế lab, cả `@EnableConfigurationProperties` và `@ConditionalOnProperty` cùng đặt ở lớp `NoticeAutoConfiguration`. Khi disabled, lớp này không xử lý nội dung đăng ký liên quan và `NoticeProperties` từ nó không được tạo.

Nếu một module khác cần đọc `NoticeProperties` ngay cả khi feature disabled, có thể giữ việc bind properties ở lớp ngoài và đặt điều kiện ở **lớp cấu hình con**:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(NoticeProperties.class)
public class NoticeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = NoticeKeys.PREFIX,
            name = NoticeKeys.ENABLED,
            havingValue = "true"
    )
    static class SenderConfiguration {

        @Bean
        @ConditionalOnMissingBean(NoticeSender.class)
        NoticeSender noticeSender(NoticeProperties properties) {
            return new NoticeSender(properties.getMessage());
        }
    }
}
~~~

Đây là **đoạn thay thế** của `NoticeAutoConfiguration.java`, sử dụng các class/import từ lab và cần thêm import `org.springframework.context.annotation.Configuration`. Nó minh họa sự khác biệt:
- `NoticeProperties` có thể được đăng ký/bind dù `enabled=false`;
- Chỉ bean `NoticeSender` nằm trong lớp con được điều kiện bảo vệ.

Như vậy, **phạm vi gắn condition** cũng là một phần hợp đồng. Nếu condition ở mức method, những method khác trong cùng auto-config vẫn được xử lý theo điều kiện riêng.

## 9. Quy tắc viết tài liệu cấu hình cho người sử dụng starter

Người dùng thư viện cần biết tối thiểu **tên khóa, kiểu, mặc định, tác dụng và ví dụ**, thay vì chỉ nhìn annotation.

Ví dụ bảng cấu hình nên đưa vào README của thư viện:

| Property | Kiểu | Mặc định | Tác dụng |
| --- | --- | --- | --- |
| `demo.notice.enabled` | Boolean | `false` | `true` cho phép starter tự tạo `NoticeSender`; `false` hoặc thiếu thì không |
| `demo.notice.message` | String | `default-message` | Nội dung mà sender mặc định sẽ sử dụng khi được tạo |

Ví dụ chuẩn được khuyến nghị:

~~~yaml
demo:
  notice:
    enabled: true
    message: "Welcome"
~~~

Phần mô tả về `enabled` phải chính xác:
- **“Cho phép auto-configuration cung cấp bean mặc định”** đúng với ví dụ.
- **“Xóa mọi bean notice, kể cả bean người dùng tạo”** không đúng, vì condition không chặn các bean do cấu hình khác tạo.
- **“Đổi giá trị khi đang chạy sẽ tự tạo/xóa bean ngay”** không đúng: bean definitions thường được quyết định khi application context khởi tạo.

Nếu đổi tên khóa công khai, cần cân nhắc tương thích ngược. Ví dụ chuyển từ `demo.notice.enabled` sang `demo.notifications.enabled` có thể làm ứng dụng cũ mất chức năng trong im lặng. Một chiến lược migration cần chỉ rõ khóa cũ được hỗ trợ bao lâu, khóa nào được ưu tiên nếu cả hai xuất hiện, test cho từng trường hợp, và cảnh báo khi dùng khóa cũ. Không chỉ đổi prefix ở condition rồi coi là refactor nội bộ.

### 9.1. Configuration metadata và gợi ý IDE

Spring Boot có cơ chế sinh **configuration metadata** từ `@ConfigurationProperties` để công cụ và IDE gợi ý tên property. Trong thư viện, có thể thêm annotation processor theo hướng dẫn phiên bản Spring Boot đang dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Thông tin metadata giúp người dùng tìm `demo.notice.enabled` và `demo.notice.message` nhanh hơn. Tuy nhiên metadata **không tự áp đặt** giá trị của `@ConditionalOnProperty` hoặc ép condition phải đọc đúng tên khóa. Vẫn cần test bean registration.

Khi công bố metadata, cần đảm bảo mô tả mặc định thực tế đồng bộ với `NoticeProperties` và `matchIfMissing`. Metadata lỗi thời khiến người dùng hiểu sai ngay cả khi code chạy đúng.

## 10. Debug: người dùng đã bật đúng nhưng bean không xuất hiện

Giả sử cấu hình:

~~~properties
demo.notice.enabled=true
~~~

nhưng code tìm `NoticeSender` không thấy. Điều tra theo thứ tự:

1. **Xác định annotation điều kiện thực tế.** Ghép `prefix` và `name` để ra FQ property. Ví dụ `demo.notice` + `enabled` thành `demo.notice.enabled`. Kiểm tra class đang được deploy, không chỉ file source cục bộ.
2. **Xem Environment hiệu lực.** Active profile, biến môi trường, command-line arguments có thể ghi đè giá trị trong `application.yml`. Property đang là `true` hay bị `false` ở nguồn ưu tiên cao hơn?
3. **Xác minh auto-configuration có được import.** Spring Boot 3.3 sử dụng `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` cho các starter. Nếu thiếu hoặc sai FQCN, condition không được đánh giá.
4. **Dùng Condition Evaluation Report.** Chạy `java -jar app.jar --debug` hoặc xem Actuator `conditions` (khi endpoint được cài, bật và expose an toàn). Phân biệt *did not find property*, *property has different value* với các condition khác.
5. **Kiểm tra các điều kiện còn lại.** `@ConditionalOnClass` có thể không match vì thiếu dependency. `@ConditionalOnMissingBean` có thể ngăn bean mặc định vì người dùng đã cung cấp một bean khác.
6. **Nếu condition match mà context vẫn fail**, đọc chuỗi `Caused by`; vấn đề có thể là dependency bean bị thiếu, lỗi validation properties, factory method ném exception hoặc classpath không tương thích.
7. **Thử tối thiểu với ApplicationContextRunner.** Dùng chính bộ property true/false/missing và kiểm tra bean có được đăng ký. Nếu unit test pass nhưng ứng dụng triển khai fail, kiểm tra môi trường thật, import, profile và bean do ứng dụng tự cung cấp.
8. **Xem liệu consumer có xử lý feature optional đúng không.** Bean luôn inject một `NoticeSender` bắt buộc dù feature tắt sẽ dẫn tới lỗi; khi đó consumer cần được điều kiện bảo vệ hoặc dùng `ObjectProvider` đúng nghĩa tùy chọn.

### 10.1. Đừng nhầm property binding với điều kiện

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "demo.notice")
public class NoticeProperties {
    private boolean enabled;
}
~~~

Không có `@ConditionalOnProperty` hoặc logic khác bảo vệ bean thì chỉ việc bind `enabled=false` **không làm Spring tự ngưng tạo mọi bean dùng object đó**. Ngược lại, chỉ có `@ConditionalOnProperty` mà chưa đăng ký/bind properties cũng không tự làm `@ConfigurationProperties` được xử lý.

Điều kiện và binding là **hai hành động riêng**, cần nối bằng một thiết kế nhất quán.

### 10.2. Không lạm dụng @ConditionalOnMissingBean

`@ConditionalOnMissingBean` nhằm để **bean mặc định nhường quyền** khi đã có bean do ứng dụng cung cấp. Nó không phải công tắc bật/tắt. Thư viện muốn cả tính năng được opt-in vẫn phải có điều kiện property thích hợp. Kết hợp hai annotation là bình thường:

~~~java
@Bean
@ConditionalOnMissingBean(NoticeSender.class)
@ConditionalOnProperty(
    prefix = "demo.notice",
    name = "enabled",
    havingValue = "true"
)
NoticeSender noticeSender(NoticeProperties properties) {
    return new NoticeSender(properties.getMessage());
}
~~~

Đây là **đoạn method minh họa** trong một class configuration có import và binding `NoticeProperties` phù hợp. Đặt `@ConditionalOnProperty` trên method bảo vệ riêng `NoticeSender`; đặt trên class sẽ bảo vệ cả cấu hình chứa method đó.

## 11. Các lỗi thiết kế phổ biến

1. **Prefix không thống nhất.** Tài liệu ghi `demo.notice.enabled` nhưng `@ConditionalOnProperty` đọc `demo.notification.enabled`, khiến bật đúng theo tài liệu vẫn không match.
2. **Nhầm `value` với `havingValue`.** Trong `@ConditionalOnProperty`, `value` là alias của `name` (tên khóa), còn `havingValue` là giá trị để match.
3. **Khóa property và tên field khác nhau không chủ đích.** Code bind field `enabled` nhưng condition đọc `active`; không có chiến lược tương thích rõ ràng.
4. **Mặc định Java và mặc định condition trái nhau.** `enabled=true` trong object nhưng `matchIfMissing=false` khiến thiếu khóa vẫn không tạo bean.
5. **Condition đặt sai phạm vi.** Condition trên một bean nhưng những bean còn lại của feature vẫn khởi tạo, dù tài liệu nói “tắt toàn bộ”.
6. **Nhầm auto-configured bean với bean người dùng tự tạo.** `enabled=false` không xóa bean thủ công ngoài auto-config.
7. **Cho phép giá trị bất kỳ thay vì explicit true.** Bỏ `havingValue` làm chuỗi không phải `false` có thể vô tình bật tính năng.
8. **Quên kiểm tra missing và false.** Hai trạng thái này cần được kiểm thử riêng vì `matchIfMissing` có thể đổi nghĩa của missing.
9. **Dùng sai scope/registration.** Chỉ tạo class `@AutoConfiguration` mà quên tệp imports, khiến condition không chạy.
10. **Đọc mỗi application.yml.** Giá trị hiệu lực có thể đến từ profile, biến môi trường, system properties hoặc command-line.
11. **Consumer bắt buộc dùng bean tùy chọn.** `@Autowired` không optional khiến app lỗi khi feature bị tắt; phải thiết kế consumer phù hợp hợp đồng.
12. **Đổi tên khóa công khai không có migration.** Các ứng dụng cấu hình theo tên cũ có thể mất tính năng âm thầm.
13. **Metadata/README không cập nhật cùng code.** IDE gợi ý một khóa nhưng annotation kiểm tra khóa khác; trải nghiệm vận hành bị sai.
14. **Hiểu thay đổi cấu hình runtime là toggle bean động.** Conditional bean registration thường chỉ được đánh giá khi context được xây dựng, không tự tạo/xóa bean theo file thay đổi.
15. **Bỏ qua khả năng đã có bean khác.** Condition match nhưng `@ConditionalOnMissingBean` chủ động nhường cho bean user; đó có thể là hành vi đúng.

## 12. Checklist kiểm tra trước khi phát hành thư viện

- [ ] Đã chốt **tên công khai duy nhất** cho feature flag, ví dụ `demo.notice.enabled`.
- [ ] `@ConditionalOnProperty` ghép đúng `prefix` + `name`; giá trị match được chỉ định rõ.
- [ ] `@ConfigurationProperties` dùng cùng namespace và có field/validation phù hợp.
- [ ] `matchIfMissing` phản ánh đúng chính sách mặc định; giá trị mặc định Java được đồng bộ.
- [ ] Condition bảo vệ **đúng phạm vi** bean mà tài liệu tuyên bố bật/tắt.
- [ ] Các bean do người dùng tự định nghĩa được xử lý rõ ràng theo hợp đồng override.
- [ ] `AutoConfiguration.imports` đăng ký đúng lớp auto-config của starter.
- [ ] Test xác nhận **missing**, **false**, **true**, **sai prefix**, **dữ liệu bind** và trạng thái của bean.
- [ ] README/configuration metadata dùng cùng khóa, kiểu, mặc định và ví dụ.
- [ ] Đã kiểm tra behavior khi có property source ưu tiên cao hơn, profile hoặc thay đổi tên khóa.
- [ ] Consumer không yêu cầu bean tùy chọn ở môi trường feature đang tắt.
- [ ] Đã chạy lại test với phiên bản Spring Boot và JDK mà thư viện hỗ trợ.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Tài liệu công bố `acme.search.enabled=true`, nhưng annotation dùng `prefix="acme.search"` và `name="active"`. Tại sao bean không xuất hiện?  
**Đáp án:** Condition đọc `acme.search.active`, không đọc khóa đã công bố. Cần thống nhất tên hoặc có migration được thiết kế rõ ràng.

**Câu 2.** `NoticeProperties.enabled` có mặc định `true`, còn condition đặt `matchIfMissing=false`. Khi không khai báo property, bean có tự tạo không?  
**Đáp án:** Không qua condition đó. `matchIfMissing=false` làm điều kiện không match khi khóa vắng mặt, bất kể default của object Java.

**Câu 3.** `@ConditionalOnProperty(prefix="demo.notice", value="enabled", havingValue="true")` có tương đương với `name="enabled"` không?  
**Đáp án:** Có. `value` là alias của `name`, cả hai là tên khóa cần kiểm tra.

**Câu 4.** Nếu thư viện không tự tạo `NoticeSender` vì `enabled=false`, liệu chắc chắn context không có bean `NoticeSender`?  
**Đáp án:** Không. Ứng dụng vẫn có thể tự khai báo bean cùng type. Contract phải ghi rõ phạm vi của condition.

**Câu 5.** Khi phát hành starter, test nào trực tiếp bắt được việc refactor nhầm prefix?  
**Đáp án:** Test đặt **khóa công khai** `demo.notice.enabled=true` rồi assert bean được tạo, cùng test đặt prefix sai và assert bean không được tạo. Không dùng hằng nội bộ làm cả input test nếu cần bắt lỗi contract với người dùng.

**Câu 6.** Làm sao hỗ trợ default-on nhất quán?  
**Đáp án:** Đặt `matchIfMissing=true`, đặt default của properties hợp lý, cập nhật tài liệu và sửa test missing; vẫn cho phép `false` tắt tính năng.

**Câu 7.** Tại sao không chỉ dùng `enabled` trong `@ConfigurationProperties` rồi coi đó là điều kiện tự động của Spring?  
**Đáp án:** Property binding chỉ đưa giá trị vào object; muốn kiểm soát bean registration cần condition hoặc cơ chế điều khiển tương ứng.

## 14. Kết luận và nguồn tham khảo

Để giữ khóa bật/tắt nhất quán với cấu hình được tạo, phải xem `enabled` như **giao diện công khai của thư viện**. Tên khóa, giá trị mặc định, phạm vi bean được điều khiển, quá trình bind và tài liệu/test cùng mô tả **một hành vi duy nhất**. Khi một tính năng bật nhưng không tạo bean, hãy kiểm tra tên khóa hiệu lực trong `Environment`, điều kiện và auto-configuration registration trước khi kết luận do lỗi bean hay dependency.

Tài liệu chính thức để đối chiếu khi triển khai với Spring Boot cụ thể:

1. [Spring Boot Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
2. [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html).
3. [Spring Boot Reference — Externalized Configuration and @ConfigurationProperties](https://docs.spring.io/spring-boot/reference/features/external-config.html).
4. [Spring Boot Reference — Configuration Metadata](https://docs.spring.io/spring-boot/reference/configuration-metadata/index.html).
5. [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).