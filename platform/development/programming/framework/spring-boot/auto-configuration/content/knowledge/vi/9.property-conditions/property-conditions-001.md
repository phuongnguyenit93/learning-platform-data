# @ConditionalOnProperty với prefix, name và value

> **Spring Boot Auto Configuration → Điều kiện thuộc tính.** Bài này giải thích cách `@ConditionalOnProperty` tính tên khóa và giá trị được phép, vì sao `value` là bí danh của `name`, khi nào `havingValue` hoặc `matchIfMissing` cần thiết, và cách kiểm chứng kết quả đăng ký bean trong ứng dụng Spring Boot sử dụng Java 17+.

## 1. Vấn đề mà @ConditionalOnProperty giải quyết

Khi viết auto-configuration hoặc cấu hình bean, có những tính năng chỉ được kích hoạt nếu người sử dụng đặt property tương ứng. Ví dụ: ứng dụng chỉ tạo một bean gửi thông báo nếu `demo.mail.enabled=true`, nhưng vẫn chạy bình thường khi tính năng bị tắt.

Spring Boot cung cấp annotation `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty` để kiểm tra các giá trị trong `Environment` khi xây dựng application context. Nếu điều kiện **match**, lớp cấu hình hoặc phương thức `@Bean` được xét để đăng ký. Nếu **không match**, cấu hình/bean được đánh dấu điều kiện đó sẽ không được đăng ký.

~~~java
@ConditionalOnProperty(
    prefix = "demo.mail",
    name = "enabled",
    havingValue = "true"
)
~~~

Trong trường hợp này:
- **Tên property đầy đủ:** `demo.mail.enabled`.
- **Giá trị cần so:** `true`.
- Khi property là `true` → điều kiện khớp.
- Khi property là `false` hoặc không có property → điều kiện không khớp (với mặc định `matchIfMissing=false`).

Annotation điều khiển **việc đăng ký cấu hình tại lúc khởi tạo context**. Nó không tự động thay đổi bean đang chạy khi property bị sửa trong file cấu hình, và không tự bảo đảm các dependency của bean đều hợp lệ.

## 2. Phân biệt prefix, name, value, havingValue và matchIfMissing

Cú pháp tổng quát:

~~~java
@ConditionalOnProperty(
    prefix = "app.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

| Thuộc tính | Kiểu | Mặc định | Vai trò |
| --- | --- | --- | --- |
| `prefix` | `String` | `""` | Nhóm các khóa, ví dụ `app.feature`. |
| `name` | `String[]` | `{}` | Một hoặc nhiều **tên property** cần kiểm tra, ví dụ `enabled`. |
| `value` | `String[]` | `{}` | **Alias của `name`**, cũng biểu diễn tên property. Không dùng để chỉ giá trị mong đợi. |
| `havingValue` | `String` | `""` | Giá trị mà property phải khớp; rỗng nghĩa là sử dụng quy tắc mặc định khác `false`. |
| `matchIfMissing` | `boolean` | `false` | Quyết định có match nếu khóa **không tồn tại** trong `Environment` hay không. |

### 2.1. prefix + name tạo thành khóa đầy đủ

~~~java
@ConditionalOnProperty(
    prefix = "app.payment",
    name = "retry-enabled",
    havingValue = "true"
)
~~~

Spring Boot ghép `app.payment` và `retry-enabled` để tìm khóa **`app.payment.retry-enabled`**. Cấu hình YAML tương ứng:

~~~yaml
app:
  payment:
    retry-enabled: true
~~~

Có thể viết prefix có dấu chấm cuối hoặc không; Spring Boot tự bổ sung dấu chấm phân tách khi cần. Với nhiều từ, nên dùng cách viết **chữ thường với dấu gạch nối**, ví dụ `retry-enabled`.

Nếu không dùng `prefix`, có thể ghi tên đầy đủ:

~~~java
@ConditionalOnProperty(
    name = "app.payment.retry-enabled",
    havingValue = "true"
)
~~~

Cách này cùng kiểm tra một property như ví dụ trên, nhưng dùng `prefix` dễ nhóm các điều kiện trong một module.

### 2.2. value là alias của name, tuyệt đối không nhầm với havingValue

Hai annotation sau **tương đương**:

~~~java
@ConditionalOnProperty(
    prefix = "app.payment",
    name = "retry-enabled",
    havingValue = "true"
)
~~~

~~~java
@ConditionalOnProperty(
    prefix = "app.payment",
    value = "retry-enabled",
    havingValue = "true"
)
~~~

Cả hai kiểm tra **khóa `app.payment.retry-enabled` có giá trị `true`**.

Ngược lại, cách viết:

~~~java
@ConditionalOnProperty(prefix = "app.payment", value = "true")
~~~

**không** có nghĩa “property nào đó phải bằng true”. Nó yêu cầu **property tên `app.payment.true`** theo quy tắc mặc định. Đây là lỗi ngữ nghĩa dễ xảy ra khi suy luận từ tên thuộc tính `value`.

Nên dùng `name` để người đọc thấy rõ ý định, `value` khi muốn viết gọn; **không khai báo cả hai alias với giá trị mâu thuẫn**. Muốn so sánh giá trị hãy dùng đúng `havingValue`.

### 2.3. havingValue là chuỗi được so khớp, không phải tên property

~~~java
@ConditionalOnProperty(
    prefix = "app.delivery",
    name = "mode",
    havingValue = "async"
)
~~~

Điều kiện này match khi `app.delivery.mode=async`. `havingValue` cũng có thể là `local`, `cloud`, `true`, `false` hoặc một trạng thái bằng chuỗi khác.

**Nếu bỏ `havingValue`**, điều kiện mặc định **không có nghĩa property phải parse thành boolean true**. Nó chỉ yêu cầu property **tồn tại và giá trị khác `false`**. Ví dụ `app.feature.enabled=on` hay `app.feature.enabled=unexpected` vẫn có thể match. Với một cờ chỉ được bật rõ ràng, nên khai báo `havingValue="true"`.

### 2.4. matchIfMissing chỉ tác động khi khóa không có mặt

~~~java
@ConditionalOnProperty(
    prefix = "app.metrics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

- `app.metrics.enabled=true`: match.
- `app.metrics.enabled=false`: không match.
- `app.metrics.enabled` **không được khai báo**: match vì `matchIfMissing=true`.

Do đó, `matchIfMissing=true` phù hợp với tính năng **bật mặc định** và cho phép người dùng tắt bằng `false`. Còn nếu yêu cầu opt-in rõ ràng, giữ `matchIfMissing=false`.

## 3. Bảng sự thật cần nhớ

Giả sử điều kiện kiểm tra một property `demo.feature.enabled`; `matchIfMissing=false` như mặc định.

| Giá trị của property | `havingValue=""` | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | :---: | :---: | :---: | :---: |
| `true` | Match | Match | Không | Không |
| `false` | Không | Không | Match | Không |
| `foo` | Match | Không | Không | Match |
| **Không tồn tại** | Không | Không | Không | Không |

Giải thích:

1. `havingValue=""` là mặc định: chỉ chặn giá trị **`false`** và yêu cầu property có mặt.
2. Khi `havingValue` được khai báo, Spring Boot so chuỗi giá trị property hiệu lực với chuỗi yêu cầu.
3. Nếu không có property, `matchIfMissing` quyết định. Đặt nó thành `true` sẽ khiến tình huống **thiếu khóa** match, kể cả khi `havingValue="true"` hoặc `havingValue="false"`.
4. Property **có mặt nhưng giá trị rỗng** không giống property bị thiếu. Ví dụ `demo.feature.enabled=` vẫn có thể match nếu `havingValue` không chỉ định, vì chuỗi rỗng khác chuỗi `false`.
5. `havingValue="false"` chỉ match giá trị **false có mặt** (trừ khi cho phép thiếu qua `matchIfMissing=true`). Đừng tự coi “không cấu hình” là “đã cấu hình false”.

Đây là ma trận hành vi được mô tả trong Javadoc của Spring Boot. Những từ như `on`, `yes`, `1` không thay thế cho `true` khi bạn đã yêu cầu **`havingValue="true"`**. Khi thiết kế cờ boolean, việc viết rõ giá trị yêu cầu sẽ tránh bật chức năng ngoài ý định.

## 4. Nhiều name/value là AND, không phải OR

`name` và `value` có kiểu `String[]`. Có thể kiểm tra nhiều khóa:

~~~java
@ConditionalOnProperty(
    prefix = "demo.security",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Điều kiện match khi **cả hai** khóa thỏa mãn:
- `demo.security.enabled=true`
- `demo.security.audit-enabled=true`

| `enabled` | `audit-enabled` | Kết quả |
| --- | --- | --- |
| true | true | Match |
| true | false | Không |
| false | true | Không |
| true | thiếu | Không, với mặc định `matchIfMissing=false` |
| thiếu | thiếu | Không, với mặc định `matchIfMissing=false` |

Mảng `name={"enabled","audit-enabled"}` dùng phép **AND**. Nó không diễn tả “chỉ cần một trong hai”. Đồng thời `havingValue` áp dụng **chung** cho mọi khóa trong mảng. Nếu cần điều kiện hỗn hợp như `enabled=true` **và** `mode=async`, có thể đặt điều kiện trên lớp lẫn method (minh họa ở phần sau) hoặc xây dựng một `Condition` riêng.

`matchIfMissing=true` khi có nhiều khóa làm các khóa thiếu được chấp nhận; **các khóa có mặt vẫn phải thỏa `havingValue`**. Phải cân nhắc chính sách mặc định của từng thuộc tính trước khi dùng.

## 5. Chạy thử hoàn chỉnh bằng Spring Boot và Java 17+

Mục tiêu là quan sát bean `mailGateway` được tạo **khi và chỉ khi** `demo.mail.enabled=true`. Ví dụ sau dùng Maven; chỉ cần JDK 17+, Maven và quyền tải thư viện. Đây là dự án Spring Boot, vì vậy không thể chạy bằng `javac` thuần nếu thiếu classpath thư viện.

Cấu trúc:

~~~text
property-condition-demo/
├── pom.xml
└── src/main/java/demo/condition/PropertyConditionDemo.java
~~~

**Tệp `pom.xml`**:

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
    <artifactId>property-condition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**Tệp `src/main/java/demo/condition/PropertyConditionDemo.java`**:

~~~java
package demo.condition;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PropertyConditionDemo {

    public static void main(String[] args) {
        SpringApplication.run(PropertyConditionDemo.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.mail",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    String mailGateway() {
        return "MAIL_GATEWAY_ACTIVE";
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> System.out.println(
                "mailGateway bean present: " + context.containsBean("mailGateway")
        );
    }
}
~~~

Ở đây `mailGateway` là bean dạng `String` để lab ngắn gọn, **không phải adapter gửi mail thật**. `ApplicationRunner` chạy sau khi context khởi động và in sự hiện diện của bean.

**Biên dịch và đóng gói:**

~~~bash
mvn -q -DskipTests package
~~~

**Ca A — property bằng true:**

~~~bash
java -jar target/property-condition-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.mail.enabled=true
~~~

Dòng do chính chương trình in:

~~~text
mailGateway bean present: true
~~~

**Ca B — property bằng false:**

~~~bash
java -jar target/property-condition-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.mail.enabled=false
~~~

Dòng do chương trình in:

~~~text
mailGateway bean present: false
~~~

**Ca C — property không tồn tại:**

~~~bash
java -jar target/property-condition-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do chương trình in:

~~~text
mailGateway bean present: false
~~~

Ba dòng trên là **dòng `System.out.println`**, không khẳng định đó là toàn bộ log nếu môi trường còn phát sinh thông tin khác.

Để thử `matchIfMissing=true`, thay giá trị trong annotation, **đóng gói lại** rồi lặp Ca C. Khi đó `mailGateway bean present: true`. Ca A vẫn true, Ca B vẫn false.

**Mô hình cơ chế:**

~~~text
Environment chứa demo.mail.enabled?
         |
         +-- Có: so giá trị với havingValue="true"
         |       +-- true  -> bean mailGateway được đăng ký
         |       +-- false -> bean mailGateway bị bỏ qua
         |
         +-- Không: xét matchIfMissing=false
                 +-- bean mailGateway bị bỏ qua
~~~

Dù giá trị property có thể nằm ở nhiều nguồn khác nhau, điều kiện xem **giá trị cuối cùng được Environment cung cấp** tại giai đoạn đăng ký bean.

## 6. Nên đặt điều kiện ở mức lớp hay mức method?

### 6.1. Ở method @Bean: điều kiện cho một bean cụ thể

Lab ở phần 5 đặt `@ConditionalOnProperty` ngay trên method `mailGateway()`, nên chỉ method này bị điều kiện quyết định. Các method `@Bean` khác trong cùng lớp vẫn được xét theo điều kiện của chúng.

Ví dụ thành phần:

~~~java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "feature",
        name = "cache-enabled",
        havingValue = "true"
    )
    CacheClient cacheClient() {
        return new CacheClient();
    }

    static final class CacheClient {}
}
~~~

Đây là **đoạn mã để tích hợp vào ứng dụng có Spring**, cần bổ sung các import cho `Configuration`, `Bean` và `ConditionalOnProperty`. Dùng mức method khi chỉ muốn một bean chịu ảnh hưởng của cờ cấu hình.

### 6.2. Ở lớp @Configuration / @AutoConfiguration: điều kiện cho cả nhóm bean

~~~java
package demo.extension;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditAutoConfiguration {

    @Bean
    AuditSink auditSink() {
        return new AuditSink();
    }

    public static final class AuditSink {
        public String name() {
            return "audit";
        }
    }
}
~~~

Ở đây, cả lớp `AuditAutoConfiguration` được điều khiển bởi `feature.audit.enabled`. Nếu không match, các bean khai báo bởi lớp đó không được đăng ký qua auto-configuration này.

Khi viết **starter / thư viện ngoài**, Spring Boot 3.x tìm auto-configuration từ tệp đăng ký:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Với lớp ví dụ trên, nội dung chính xác của tệp này là:

~~~text
demo.extension.AuditAutoConfiguration
~~~

Đây là **mã cấu hình có thể biên dịch trong một dự án có dependency Spring Boot**, nhưng không phải chương trình độc lập có phương thức `main`. Với lab `@SpringBootApplication` ở phần 5, không cần tự tạo tệp imports.

### 6.3. Hai giá trị mong đợi khác nhau: kết hợp điều kiện ở hai mức

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "feature.delivery",
    name = "enabled",
    havingValue = "true"
)
class DeliveryConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "feature.delivery",
        name = "mode",
        havingValue = "async"
    )
    AsyncWorker asyncWorker() {
        return new AsyncWorker();
    }

    static final class AsyncWorker {}
}
~~~

Đoạn trên là ví dụ thành phần với các import Spring tương ứng. Bean `AsyncWorker` chỉ được khai báo khi **`feature.delivery.enabled=true` và `feature.delivery.mode=async`**. Điều này rõ ràng hơn việc nhét hai tên property yêu cầu **hai giá trị khác nhau** vào một mảng `name` có chung `havingValue`.

Nếu nhiều điều kiện cùng áp dụng, tất cả điều kiện cần thiết phải thỏa. Một `@ConditionalOnProperty` match không bảo đảm bean thực sự tồn tại nếu `@ConditionalOnClass`, `@ConditionalOnMissingBean`, cơ chế import hoặc bean creation thất bại.

## 7. Property đến từ đâu và vì sao giá trị thực có thể khác file?

Những cấu hình sau thể hiện cùng ý định **`demo.mail.enabled=true`**.

**`application.yml`:**

~~~yaml
demo:
  mail:
    enabled: true
~~~

**`application.properties`:**

~~~properties
demo.mail.enabled=true
~~~

**Command-line arguments:**

~~~bash
java -jar app.jar --demo.mail.enabled=true
~~~

**Biến môi trường** trong một môi trường hỗ trợ Spring Boot externalized configuration:

~~~bash
export DEMO_MAIL_ENABLED=true
~~~

Spring Boot dùng nhiều property sources, gồm file mặc định, file theo profile, biến môi trường, thuộc tính hệ thống, command-line arguments. Chúng có **thứ tự ưu tiên**; một khóa đặt trong `application.yml` có thể bị giá trị ở nguồn ưu tiên cao hơn ghi đè.

Ví dụ: `application.yml` có `demo.mail.enabled=false`, nhưng lệnh chạy dùng `--demo.mail.enabled=true`. Trong ứng dụng Spring Boot thông thường, command-line argument có ưu tiên cao hơn file cấu hình, nên `@ConditionalOnProperty` sẽ nhìn thấy true.

**Phân biệt bốn tình huống khi debug:**
- Khóa đúng **không có mặt** → `matchIfMissing`.
- Khóa đúng **có mặt và bằng false** → xét `havingValue`, không được coi là missing.
- Khóa có mặt nhưng **rỗng** → vẫn là một giá trị đã tồn tại; mặc định có thể match do khác false.
- Bạn chỉ khai báo `demo.mail.enable` trong khi điều kiện cần `demo.mail.enabled` → khóa đúng vẫn thiếu.

Ưu tiên quy ước tên property chữ thường dạng kebab-case; khi dùng `@ConfigurationProperties`, Spring Boot hỗ trợ binding có cấu trúc và validation, còn `@ConditionalOnProperty` tập trung vào việc **đọc property để quyết định khởi tạo cấu hình**. Chúng là hai cơ chế có mục đích khác nhau.

**Lưu ý quan trọng về collection:** Javadoc nói `@ConditionalOnProperty` không đáng tin để kiểm tra các property dạng danh sách; chẳng hạn chỉ có `demo.targets[0]` không bảo đảm `demo.targets` được cung cấp như một property có thể kiểm tra. Nếu cần biết list có phần tử, nên bind list bằng `@ConfigurationProperties` hoặc viết `Condition` phù hợp thay vì dùng `@ConditionalOnProperty(name="targets")`.

## 8. Kiểm tra condition bằng test thay vì suy đoán

Với starter hoặc auto-configuration, kiểm tra ít nhất bốn trường hợp: `true`, `false`, **missing** và giá trị bất thường. Spring Boot cung cấp `ApplicationContextRunner` để tạo context nhỏ, thiết lập property cho từng case và kiểm tra bean.

Thêm dependency test vào `pom.xml` (bên trong `<dependencies>`):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo **`src/test/java/demo/condition/ConditionalPropertyTest.java`**:

~~~java
package demo.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalPropertyTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(TestConfiguration.class);

    @Test
    void trueValueCreatesBean() {
        runner.withPropertyValues("demo.mail.enabled=true")
                .run(context -> assertThat(context).hasBean("mailGateway"));
    }

    @Test
    void falseValueSkipsBean() {
        runner.withPropertyValues("demo.mail.enabled=false")
                .run(context -> assertThat(context).doesNotHaveBean("mailGateway"));
    }

    @Test
    void missingPropertySkipsBeanByDefault() {
        runner.run(context -> assertThat(context).doesNotHaveBean("mailGateway"));
    }

    @Test
    void otherValueDoesNotMatchExplicitTrue() {
        runner.withPropertyValues("demo.mail.enabled=on")
                .run(context -> assertThat(context).doesNotHaveBean("mailGateway"));
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "demo.mail",
                name = "enabled",
                havingValue = "true"
        )
        String mailGateway() {
            return "MAIL_GATEWAY_ACTIVE";
        }
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Kỳ vọng **4 test PASS**. Test này dùng cấu hình nhỏ trong lớp test, không phụ thuộc thời điểm chạy của cả web server. Khi đổi quy tắc mặc định `matchIfMissing` hoặc thêm nhiều `name`, hãy **bổ sung case phản ánh chính sách thực tế**, đặc biệt là trường hợp có một khóa bị thiếu.

## 9. Debug trong Spring Boot Auto Configuration

Khi một bean mong đợi không xuất hiện, xử lý theo trình tự sau.

**Bước 1 — biến annotation thành điều kiện kiểm tra cụ thể.** Ví dụ `prefix="feature.audit"`, `name="enabled"`, `havingValue="true"`, `matchIfMissing=false` nghĩa là **`feature.audit.enabled` phải hiện diện và có giá trị true**.

**Bước 2 — xem condition evaluation report.** Chạy ứng dụng với tham số `--debug`:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot có thể hiển thị báo cáo các điều kiện match/không match. Nếu ứng dụng dùng Actuator và endpoint được bật/expose đúng cách, endpoint `/actuator/conditions` cung cấp báo cáo hữu ích. Kiểm soát quyền truy cập endpoint này trong môi trường triển khai.

**Bước 3 — xác định giá trị `Environment` thực sự thấy.** Kiểm tra các property sources, profile đang active, biến môi trường, command-line arguments và thứ tự ưu tiên. Không kết luận từ một file `application.yml` duy nhất.

**Bước 4 — kiểm tra các điều kiện khác.** `@ConditionalOnClass` có thể chặn auto-configuration khi thiếu thư viện; `@ConditionalOnMissingBean` có thể bỏ qua bean vì người dùng đã tự khai báo; import/scan có thể chưa đăng ký lớp. Nếu quá trình tạo bean ném exception, phải đọc stack trace. `@ConditionalOnProperty` chỉ kiểm tra property, **không chứng minh bean sẽ tạo thành công**.

**Bước 5 — xác minh sau sửa.** Chạy lại các tình huống `true`, `false`, missing và giá trị biên; khi cần, dùng `ApplicationContextRunner` để kiểm tra hành vi có thể lặp lại.

## 10. Những lỗi phổ biến cần tránh

1. **Lấy `value="true"` để so với true.** `value` là tên property; so giá trị bằng `havingValue="true"`.
2. **Bỏ `havingValue` rồi tin điều kiện kiểm tra boolean đúng nghĩa.** Quy tắc mặc định chỉ loại giá trị `false`; các giá trị khác có thể match.
3. **Nhầm missing với false.** Property thiếu bị quyết định bởi `matchIfMissing`; `havingValue="false"` không tự match khi thiếu.
4. **Tưởng nhiều `name` có nghĩa OR.** Tất cả phải thỏa điều kiện; nếu muốn OR, cần mô hình điều kiện khác.
5. **Giả sử `prefix` tự dò tên sai hoặc tìm theo hậu tố.** Prefix và name tạo khóa cụ thể; lỗi chính tả dẫn đến missing.
6. **Dùng condition để xem list có phần tử.** Đối với collection, property indexed có thể khác property tổng; chọn binding/custom condition.
7. **Quên độ ưu tiên của nguồn config.** Profile, môi trường chạy và command-line có thể ghi đè `application.yml`.
8. **Trông đợi thay đổi config lúc runtime tự thay đổi bean.** Bean definition thường được quyết định trong quá trình tạo context; cần cơ chế runtime riêng nếu muốn chuyển trạng thái động.
9. **Chỉ kiểm tra điều kiện property mà không xem điều kiện khác.** Bean còn phụ thuộc classpath, bean hiện hữu, cấu hình import và lỗi khởi tạo.
10. **Không test trường hợp property vắng mặt.** Đây là trường hợp trực tiếp quyết định bởi `matchIfMissing` và thường là khác biệt giữa “opt-in” và “bật mặc định”.

## 11. Tình huống thực hành và câu hỏi tự kiểm tra

**Tình huống A: tính năng chỉ được bật nếu opt-in.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

Cấu hình không có property sẽ **không kích hoạt**. Ghi `feature.audit.enabled=true` để bật, `false` để tắt.

**Tình huống B: tính năng mặc định bật nhưng cho phép tắt.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.metrics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

Không khai báo property vẫn kích hoạt; `feature.metrics.enabled=false` tắt rõ ràng. Cần chọn cách này dựa trên chính sách sản phẩm, không chọn chỉ vì code gọn.

**Tình huống C: chỉ cấu hình ở chế độ async.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.delivery",
    name = "mode",
    havingValue = "async"
)
~~~

`mode=async` kích hoạt; `mode=sync` hoặc không khai báo thì không kích hoạt.

**Tình huống D: hai cờ cùng bật.**

~~~java
@ConditionalOnProperty(
    prefix = "feature.security",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Cả `feature.security.enabled` và `feature.security.audit-enabled` phải bằng true.

**Câu hỏi 1:** `@ConditionalOnProperty(prefix="demo", value="enabled", havingValue="true")` đọc property nào?  
**Đáp án:** `demo.enabled`; `value` là alias của `name`.

**Câu hỏi 2:** `@ConditionalOnProperty(prefix="demo", name="enabled")` gặp `demo.enabled=foo` có match không?  
**Đáp án:** Có; mặc định chỉ yêu cầu property hiện diện và khác `false`.

**Câu hỏi 3:** `havingValue="false"`, property không tồn tại và `matchIfMissing=false`: có match không?  
**Đáp án:** Không. Thiếu property khác với property có giá trị false.

**Câu hỏi 4:** `name={"a","b"}`, `havingValue="true"` và chỉ `a=true`, `b=false`: kết quả gì?  
**Đáp án:** Không match vì các tên được nối bằng AND.

**Câu hỏi 5:** `@ConditionalOnProperty` match nhưng bean vẫn không có, có chắc annotation bị lỗi không?  
**Đáp án:** Chưa. Kiểm tra các condition khác, cách đăng ký configuration, giá trị `Environment` và exception tạo bean.

## 12. Tóm tắt kiến thức cần nhớ

- **`prefix + "." + name`** tạo tên khóa đầy đủ; `prefix + "." + value` cũng vậy vì **`value` chính là alias của `name`**.
- **`havingValue`** quy định giá trị cần khớp. Mặc định rỗng → property tồn tại và giá trị **khác `false`**.
- **`matchIfMissing`** chỉ điều khiển trường hợp **khóa không tồn tại**; mặc định false.
- **Nhiều property trong `name`** cần **đồng thời** match và cùng chịu một `havingValue`.
- Bean xuất hiện hay không phụ thuộc vào **giá trị hiệu lực của `Environment` tại khi xử lý cấu hình**, và có thể còn phụ thuộc các điều kiện khác.
- Khi nghi ngờ, dùng **Condition Evaluation Report + kiểm tra property source + `ApplicationContextRunner`** để xác minh.

**Nguồn tham khảo chính thức:**
- [Spring Boot 3.3 Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot Reference — Creating Your Own Auto-configuration, Property Conditions](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)