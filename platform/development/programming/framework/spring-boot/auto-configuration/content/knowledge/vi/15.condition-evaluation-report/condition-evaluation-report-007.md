# Điểm cuối Actuator `/conditions` và phạm vi thông tin theo từng context

Khi Spring Boot không tạo một bean như mong đợi, hoặc một auto-configuration bị bỏ qua, câu hỏi quan trọng nhất thường là: **condition nào đã được đánh giá, điều kiện nào khớp, điều kiện nào không khớp và trong context nào?** Spring Boot Actuator cung cấp endpoint `conditions` để trả lời những câu hỏi này.

Endpoint mặc định có đường dẫn `GET /actuator/conditions`. Nó hiển thị **Condition Evaluation Report** được Spring Boot ghi lại trong quá trình xử lý cấu hình và auto-configuration. Report phân nhóm theo **ApplicationContext**: mỗi context có tập điều kiện khớp/không khớp riêng và có thể liên kết với context cha bằng `parentId`.

Điểm quan trọng nhất của bài này là: **report không phải một bản đồ bean toàn JVM đã được gộp chung**. Endpoint đi từ context đang chứa endpoint lên các context cha của nó; mỗi entry trong `contexts` mô tả kết quả condition của một context. Vì vậy, muốn đọc đúng kết quả phải xác định cả **source configuration** lẫn **context id**.

## 1. `/actuator/conditions` dùng để làm gì?

`conditions` là một Actuator endpoint có id `conditions`, được triển khai bởi `ConditionsReportEndpoint` và công bố `ConditionEvaluationReport` dưới dạng dữ liệu JSON.

Nó hữu ích khi cần điều tra:

- Vì sao một auto-configuration không được áp dụng?
- `@ConditionalOnClass` có tìm thấy thư viện cần thiết trên classpath không?
- `@ConditionalOnProperty` có đọc được property và giá trị có khớp không?
- `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` đã tìm thấy bean nào?
- Vì sao một nhánh Servlet/WebFlux, database, messaging hoặc security không được cấu hình?
- Một condition khớp ở application context hay ở management context?
- Một auto-configuration có bị exclude khỏi danh sách xử lý không?

Ví dụ message trong report có thể giống:

```text
@ConditionalOnClass found required class 'com.example.Driver'
@ConditionalOnProperty (demo.feature.enabled=true) matched
@ConditionalOnMissingBean (types: com.example.PaymentClient) did not find any beans
OnWebApplicationCondition: not a reactive web application
```

Các message trên là **ví dụ minh họa**, không phải output cố định của mọi ứng dụng. Nội dung thật phụ thuộc version, dependency, cấu hình và những condition đã được đánh giá.

### Phân biệt với các endpoint Actuator khác

| Endpoint | Trả lời câu hỏi nào? |
| --- | --- |
| `/actuator/conditions` | Vì sao condition trên configuration/auto-configuration khớp hoặc không khớp? |
| `/actuator/beans` | Context đang đăng ký những bean nào, tên và kiểu của chúng là gì? |
| `/actuator/env` | Environment chứa property và property source nào? |
| `/actuator/configprops` | Các bean `@ConfigurationProperties` đã bind cấu hình ra sao? |
| `/actuator/health` | Trạng thái health của ứng dụng và các contributor là gì? |

`conditions` giúp giải thích **quyết định cấu hình**; nó không thay thế việc kiểm tra bean instance, property đang chạy hoặc trạng thái health. Endpoint này cũng không phải công cụ chạy lại mọi condition theo từng HTTP request. Nó trình bày kết quả mà Spring Boot đã ghi trong `ConditionEvaluationReport`.

## 2. Bật Actuator và truy cập endpoint

### 2.1. Thêm dependency

Với Maven, thêm starter Actuator vào ứng dụng Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Nếu ứng dụng cần HTTP endpoint, ứng dụng cũng phải có một web stack được Spring Boot hỗ trợ, ví dụ `spring-boot-starter-web` hoặc `spring-boot-starter-webflux`.

### 2.2. Cho phép expose qua HTTP

Trong Spring Boot 3.3, **mặc định chỉ endpoint `health` được expose qua HTTP và JMX**. Vì vậy, có dependency Actuator nhưng truy cập `/actuator/conditions` vẫn có thể nhận `404 Not Found`.

Để expose `health` và `conditions`, cấu hình `src/main/resources/application.properties`:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Sau khi ứng dụng khởi động, gọi:

```bash
curl -i http://localhost:8080/actuator/conditions
```

Đường dẫn mặc định là `/actuator` cộng với endpoint id `conditions`. Nếu ứng dụng đổi `management.endpoints.web.base-path`, dùng management port riêng hoặc đổi path mapping, URL thực tế sẽ khác.

Có thể expose qua JMX nếu môi trường quản trị dùng JMX:

```properties
management.endpoints.jmx.exposure.include=health,conditions
```

`include` là danh sách endpoint được expose. Nếu có `management.endpoints.web.exposure.exclude` hoặc JMX exclude, danh sách exclude có độ ưu tiên cao hơn include.

### 2.3. Phân biệt endpoint enabled và endpoint exposed

Hai bước này khác nhau:

- **Enabled:** endpoint có được tạo/đưa vào ApplicationContext hay không.
- **Exposed:** endpoint có được công bố qua HTTP hoặc JMX hay không.

Thông thường Actuator endpoint được enable theo mặc định. Nếu dự án tắt tất cả endpoint theo cấu hình chung:

```properties
management.endpoints.enabled-by-default=false
management.endpoint.conditions.enabled=true
management.endpoints.web.exposure.include=health,conditions
```

thì cần enable riêng `conditions` và expose nó qua giao thức mong muốn. Nếu endpoint bị disable, chỉ thêm `conditions` vào danh sách exposure không làm endpoint xuất hiện trở lại.

### 2.4. Security và dữ liệu nhạy cảm

Khi `spring-security` có trên classpath và ứng dụng không tự khai báo `SecurityFilterChain`, Spring Boot mặc định bảo vệ các Actuator endpoint khác `health`. Vì vậy, request tới `/actuator/conditions` có thể trả `401 Unauthorized` hoặc `403 Forbidden` tùy cấu hình xác thực/phân quyền.

Nếu ứng dụng khai báo một `SecurityFilterChain` tùy chỉnh, auto-configuration security của Actuator sẽ nhường quyền kiểm soát; chính ứng dụng phải cấu hình bảo vệ endpoint cần thiết. Hãy giới hạn endpoint cho người vận hành hoặc mạng quản trị.

Không nên expose `conditions` công khai. Report có thể tiết lộ:

- Tên package, class và method cấu hình nội bộ.
- Bean name và kiểu bean được condition tìm thấy.
- Property key, giá trị kỳ vọng và lý do property không khớp.
- Thư viện/class có hoặc không có trên classpath.
- Chi tiết cấu hình của các tích hợp đang dùng.

Nếu nhận `404`, kiểm tra dependency, endpoint enabled, exposure include/exclude và management base path. Nếu nhận `401/403`, kiểm tra security. Nếu endpoint không tồn tại trong ứng dụng non-web, có thể xem report qua log `--debug` hoặc JMX thay vì HTTP.

## 3. Đọc cấu trúc JSON của response

Response có object gốc `contexts`. Các key bên trong là **id của ApplicationContext**. Mỗi entry là một `ContextConditionsDescriptor`.

Ví dụ rút gọn:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.ClientAutoConfiguration#client": [
          {
            "condition": "OnClassCondition",
            "message": "@ConditionalOnClass found required class 'com.example.Client'"
          }
        ]
      },
      "negativeMatches": {
        "com.example.CacheAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "Property 'demo.cache.enabled' did not match"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "Required cache API was found"
            }
          ]
        }
      },
      "unconditionalClasses": [
        "com.example.BaseInfrastructureAutoConfiguration"
      ],
      "exclusions": [],
      "parentId": null
    }
  }
}
```

Đây là JSON minh họa cấu trúc, đã rút gọn và dùng tên class giả định. Tùy context và kết quả đánh giá, một số collection có thể rỗng hoặc không có entry.

### 3.1. `contexts`

`contexts` là map các context theo id. Đừng hard-code rằng key luôn là `application`: tên có thể khác khi ứng dụng tự đặt id hoặc dùng context hierarchy. Hãy đọc key thực tế trong response.

### 3.2. `positiveMatches`

`positiveMatches` chứa các configuration class hoặc bean method mà **các condition liên quan đã khớp**. Mỗi key là source được đánh giá:

- Chỉ tên class: condition đặt trên configuration class.
- `ClassName#methodName`: condition gắn với phương thức `@Bean` hoặc source method tương ứng.

Mỗi source có thể có nhiều condition; mỗi phần tử cung cấp:

- `condition`: tên condition, thường là dạng như `OnClassCondition`, `OnPropertyCondition`, `OnBeanCondition`, `OnWebApplicationCondition`.
- `message`: giải thích vì sao condition đó khớp.

Một source có nhiều condition chỉ xuất hiện trong positive matches khi các điều kiện cần thiết của source đã khớp. Đọc toàn bộ message để biết nó khớp do classpath, property, bean hay web application type.

### 3.3. `negativeMatches`

`negativeMatches` chứa configuration source có **ít nhất một condition không khớp**. Mỗi source có hai nhóm:

- `notMatched`: condition không khớp, kèm lý do.
- `matched`: những condition khác trong cùng source đã khớp.

Điều này đặc biệt hữu ích với condition kết hợp hoặc condition lồng nhau. Một configuration có thể tìm thấy class cần thiết nhưng vẫn không được áp dụng vì property sai giá trị. Khi đó `matched` cho biết phần classpath đã đúng, còn `notMatched` chỉ ra nguyên nhân chặn.

Ví dụ:

```json
{
  "negativeMatches": {
    "com.example.RedisAutoConfiguration": {
      "notMatched": [
        {
          "condition": "OnPropertyCondition",
          "message": "Property 'app.redis.enabled' did not match"
        }
      ],
      "matched": [
        {
          "condition": "OnClassCondition",
          "message": "Redis client class was found"
        }
      ]
    }
  }
}
```

Cách đọc: class Redis client có trên classpath, nhưng property kích hoạt không đúng nên cấu hình Redis không được áp dụng. Đừng chỉ nhìn thấy key trong `negativeMatches` rồi kết luận mọi condition của class đều sai.

### 3.4. `unconditionalClasses`

Đây là danh sách tên các auto-configuration class **không có condition cần đánh giá** được ghi trong report của context đó. Nó không có nghĩa các bean bên trong chắc chắn đã được khởi tạo thành instance hoặc mọi method đều thành công. Đây là thông tin về lớp cấu hình vô điều kiện được ghi nhận.

### 3.5. `exclusions`

Khi có, `exclusions` liệt kê các auto-configuration class đã bị exclude. Ví dụ loại trừ qua `@SpringBootApplication(exclude = …)` hoặc `spring.autoconfigure.exclude`. Một lớp bị loại trừ khác với một lớp được xét rồi có condition không khớp:

- **Excluded:** lớp bị loại khỏi quá trình áp dụng auto-configuration.
- **Negative match:** lớp đã được đánh giá nhưng ít nhất một condition không khớp.

### 3.6. `parentId`

`parentId` là id của **ApplicationContext cha** nếu context hiện tại có cha. Nếu không có cha, giá trị thường là `null`.

Nó là liên kết cấu trúc context, không phải kết luận rằng mọi bean trong cha đều được gộp vào report của con. Mỗi entry vẫn mô tả kết quả condition của context tương ứng.

## 4. Phạm vi report theo từng ApplicationContext

Đây là phần dễ đọc nhầm nhất của endpoint.

`ConditionsReportEndpoint` được tạo với một `ConfigurableApplicationContext`. Khi tạo report, endpoint đi từ context chứa endpoint **lên từng context cha** cho tới khi không còn cha. Vì vậy:

1. Context chứa endpoint luôn là điểm bắt đầu.
2. Mỗi context cha được thêm thành một entry riêng trong `contexts`.
3. `parentId` giúp lần theo chuỗi context.
4. Context con, context anh em hoặc một context độc lập khác không nằm trên đường cha của endpoint **không tự động xuất hiện** trong report đó.

Nói cách khác, phạm vi là **context hiện tại và tổ tiên của nó**, không phải toàn bộ cây theo cả hai chiều.

### 4.1. Ví dụ parent và child

Giả sử cấu trúc context:

```text
application-context
       |
       v
management-context
       |
       v
monitoring-child
```

Nếu endpoint được phục vụ từ `management-context`, report của endpoint sẽ có `management-context` và `application-context`. Nó không tự liệt kê `monitoring-child` vì đó là context con của context đang chứa endpoint.

Nếu endpoint được phục vụ từ `monitoring-child`, report có thể lần ngược `monitoring-child` → `management-context` → `application-context`.

Nếu endpoint nằm ở `application-context`, report của endpoint đó không tự đi xuống management context hoặc các child context khác.

### 4.2. Trường hợp management port riêng

Khi cấu hình Actuator chạy trên management port khác với server port chính, Spring Boot có thể tạo **management context riêng** trong quan hệ cha/con với application context. Khi đó, endpoint được phục vụ từ management context có thể trả report gồm:

- Entry của management context, nơi endpoint được đặt.
- Entry của application context cha, nơi cấu hình ứng dụng chính được xử lý.
- `parentId` nối management context với application context.

Tên id cụ thể phụ thuộc cách khởi tạo context; không giả định luôn có đúng hai key hoặc tên luôn là `management` và `application`. Hãy xem response thực tế.

### 4.3. Condition của context con có thể nhìn thấy bean từ cha không?

Đây là một vấn đề riêng với phạm vi report.

Mỗi entry lưu kết quả condition của BeanFactory/context tương ứng. Tuy nhiên, **một condition cụ thể có thể được cấu hình để tìm bean trong context cha**. Ví dụ, một condition của Boot có thể dùng search strategy cho phép tìm cả bean trong ancestor context. Message đôi khi ghi rõ `SearchStrategy: all` hoặc chiến lược tìm kiếm tương ứng.

Do đó, cần tách hai câu hỏi:

- **Condition được đánh giá ở context nào?** Xem key trong `contexts` và quan hệ `parentId`.
- **Condition đã tìm bean ở phạm vi nào?** Xem message của condition, kiểu bean, tên bean và search strategy.

Một child context có thể ghi nhận condition của chính nó nhưng condition đó vẫn nhìn thấy bean do parent cung cấp nếu chiến lược tìm kiếm cho phép. Report không phải danh sách bean đã hợp nhất giữa cha và con.

### 4.4. Context độc lập hoặc sibling

Hai ứng dụng chạy song song hoặc hai child context cùng chung một parent không tự xuất hiện đầy đủ trong report của endpoint đặt ở một nhánh. Endpoint chỉ lần theo context hiện tại và cha của nó. Muốn xem nhánh còn lại, cần truy cập report được phục vụ trong context của nhánh đó hoặc ghi report riêng từ chính context đó.

## 5. Quy trình chẩn đoán một auto-configuration

Khi một bean không xuất hiện, đọc report theo trình tự sau:

1. **Xác định context id.** Kiểm tra `contexts` và `parentId` trước. Đừng kết luận condition không khớp nếu đang xem nhầm context.
2. **Tìm source class hoặc method.** Ví dụ `DataSourceAutoConfiguration` hoặc `DataSourceAutoConfiguration#dataSource`. Nếu không tìm thấy, kiểm tra lớp có được nạp/đưa vào danh sách auto-configuration không.
3. **Nếu ở positiveMatches:** đọc từng condition và message để hiểu tại sao cấu hình được áp dụng.
4. **Nếu ở negativeMatches:** xem `notMatched` trước để xác định điều kiện chặn; sau đó đọc `matched` để biết các phần đã đúng.
5. **Kiểm tra exclusions.** Nếu class bị exclude, điều tra nơi khai báo exclude trước khi sửa property hoặc classpath.
6. **Đối chiếu property/classpath/bean.** Kiểm tra property key, giá trị, dependency, kiểu bean, bean name và điều kiện web stack tương ứng.
7. **Đối chiếu bean thực tế nếu cần.** Dùng `/actuator/beans` để xem bean đã đăng ký; dùng `/actuator/env` hoặc `/actuator/configprops` khi cần xác minh cấu hình, có xét bảo mật.
8. **Viết test cô lập.** `ApplicationContextRunner` cho phép thay property, user configuration và auto-configuration để tái hiện đúng nhánh condition.

### Một số tình huống thường gặp

| Triệu chứng | Nơi nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Class xuất hiện trong `negativeMatches` với `OnClassCondition` | `notMatched` message | Thêm đúng dependency hoặc kiểm tra class name/version/optional dependency. |
| `OnPropertyCondition` không khớp | Property key và giá trị mong đợi | Kiểm tra profile, nguồn cấu hình, spelling, `havingValue` và `matchIfMissing`. |
| `OnBeanCondition` báo không tìm thấy bean | Kiểu/tên bean và search strategy | Kiểm tra bean có được đăng ký trước lúc condition chạy, có đúng type/interface và có nằm trong context cha không. |
| `OnWebApplicationCondition` không khớp | Loại context đang chạy | Xác định ứng dụng Servlet, Reactive hay non-web; classpath đơn thuần không quyết định loại context. |
| Auto-configuration không xuất hiện ở cả positive lẫn negative | Danh sách ứng viên và exclusions | Kiểm tra starter, file auto-configuration imports, exclude và classpath. |
| Condition khớp nhưng bean không thấy trong `/actuator/beans` | Source method và lỗi khởi tạo | Kiểm tra bean method, exception trong startup và context id. |
| Kết quả ở management khác application | `contexts`, `parentId` | Xem report từng context, không gộp hai kết quả thành một. |

### Report không giải thích mọi lỗi khởi tạo bean

Một condition khớp chỉ cho biết **điều kiện cho phép cấu hình/bean definition được xử lý**. Nó không đảm bảo bean instance đã tạo thành công. Bean có thể gặp lỗi constructor, dependency, post-processor hoặc kết nối tài nguyên sau đó. Khi report cho thấy condition đã khớp nhưng ứng dụng vẫn không có bean mong đợi, xem thêm startup exception, `/actuator/beans` và dependency graph.

## 6. Ví dụ chạy được: Spring Boot 3.3.5, Java 17 và JUnit 5

Ví dụ gồm hai kiểm thử:

- Kiểm tra endpoint HTTP trả report và giải thích vì sao một configuration không khớp property.
- Tạo một parent context và một child context để kiểm chứng report được tạo từ child có entry của child và ancestor, trong khi report tạo từ parent không đi xuống child.

### 6.1. Cấu trúc dự án

```text
conditions-report-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ConditionsEndpointIntegrationTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>conditions-report-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
</project>
```

### 6.2. Mã kiểm thử hoàn chỉnh

Tạo `src/test/java/demo/ConditionsEndpointIntegrationTest.java`:

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.autoconfigure.condition.ConditionsReportEndpoint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ConditionsEndpointIntegrationTest.DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.endpoints.web.exposure.include=health,conditions",
                "demo.feature.enabled=false"
        }
)
class ConditionsEndpointIntegrationTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void endpointReportsWhyFeatureConfigurationDidNotMatch() {
        ResponseEntity<JsonNode> response =
                http.getForEntity("/actuator/conditions", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);

        JsonNode body = response.getBody();
        assertThat(body).isNotNull();

        JsonNode contexts = body.path("contexts");
        assertThat(contexts.isObject()).isTrue();
        assertThat(contexts.isEmpty()).isFalse();

        String source = FeatureConfiguration.class.getName();
        boolean foundReason = false;

        var reports = contexts.elements();
        while (reports.hasNext()) {
            JsonNode negativeMatches =
                    reports.next().path("negativeMatches");
            JsonNode feature = negativeMatches.path(source);

            if (!feature.isMissingNode()) {
                foundReason = feature.path("notMatched")
                        .toString()
                        .contains("demo.feature.enabled");
            }
        }

        assertThat(foundReason).isTrue();
    }

    @Test
    void endpointReportContainsItsContextAndAncestorsOnly() {
        try (AnnotationConfigApplicationContext parent =
                     new AnnotationConfigApplicationContext();
             AnnotationConfigApplicationContext child =
                     new AnnotationConfigApplicationContext()) {

            parent.setId("parent-context");
            parent.refresh();

            child.setId("child-context");
            child.setParent(parent);
            child.refresh();

            var childContexts =
                    new ConditionsReportEndpoint(child)
                            .conditions()
                            .getContexts();

            assertThat(childContexts.keySet())
                    .containsExactlyInAnyOrder(
                            "child-context",
                            "parent-context"
                    );

            assertThat(childContexts.get("child-context").getParentId())
                    .isEqualTo("parent-context");

            assertThat(childContexts.get("parent-context").getParentId())
                    .isNull();

            var parentContexts =
                    new ConditionsReportEndpoint(parent)
                            .conditions()
                            .getContexts();

            assertThat(parentContexts.keySet())
                    .containsExactly("parent-context");
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(FeatureConfiguration.class)
    static class DemoApplication {
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true"
    )
    static class FeatureConfiguration {

        @Bean
        String featureMarker() {
            return "enabled";
        }
    }
}
```

Chạy từ thư mục `conditions-report-demo` bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả kỳ vọng:** hai test thành công.

- Test HTTP nhận `200 OK` và tìm được source `FeatureConfiguration` trong `negativeMatches`; message trong `notMatched` giải thích property `demo.feature.enabled` không khớp vì test đặt `false` trong khi condition yêu cầu `true`.
- Test context hierarchy xác nhận endpoint được tạo từ `child-context` trả về hai entry `child-context` và `parent-context`; `parentId` của child trỏ tới parent. Khi endpoint được tạo từ parent, report chỉ có parent, không tự đi xuống child.

Bộ test dùng trực tiếp `ConditionsReportEndpoint` ở test thứ hai để kiểm chứng phạm vi context mà không cần dựng hai web server. Test thứ nhất kiểm chứng HTTP exposure và nội dung report thật của một ứng dụng Boot. Test không in stdout nghiệp vụ; log startup của embedded server và Maven có thể khác nhau theo môi trường.

### 6.3. Tự thay đổi property để quan sát report

Đổi property của test:

```properties
demo.feature.enabled=true
```

Khi đó `FeatureConfiguration` có thể khớp và source sẽ chuyển sang `positiveMatches`, đồng thời bean `featureMarker` được đăng ký. Nếu muốn xác nhận bean instance, có thể kiểm tra thêm `/actuator/beans` hoặc inject bean trong test; không nên chỉ dựa vào condition report để khẳng định bean đã khởi tạo thành công.

## 7. Khi không muốn expose endpoint HTTP

Có thể xem Condition Evaluation Report qua log bằng cách khởi động ứng dụng với:

```bash
java -jar app.jar --debug
```

`--debug` bật log report auto-configuration trong quá trình khởi động. Đây là cách hữu ích cho môi trường local hoặc khi endpoint HTTP chưa được expose.

Trong kiểm thử auto-configuration, Spring Boot còn có `ConditionEvaluationReportLoggingListener`. Ví dụ:

```java
ApplicationContextRunner runner = new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        )
        .withConfiguration(
                AutoConfigurations.of(MyFeatureAutoConfiguration.class)
        );
```

Đây là **trích đoạn** cần đặt trong test class, với các import tương ứng từ Spring Boot Test và Logback. `ApplicationContextRunner` tạo context cô lập; listener ghi report ở log level được chọn. Cách này thuận tiện khi muốn biết vì sao test context không áp dụng một auto-configuration mà không cần chạy HTTP server.

## 8. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
| --- | --- |
| “Có Actuator là truy cập được `/actuator/conditions` ngay.” | Mặc định HTTP chỉ expose `health`; phải include `conditions`. |
| “`negativeMatches` nghĩa là tất cả condition trong class đều sai.” | Chỉ cần một condition không khớp; xem `notMatched` và `matched` để phân biệt. |
| “`positiveMatches` chứng minh bean instance đã được tạo.” | Nó chứng minh condition của source khớp; việc tạo instance vẫn có thể thất bại sau đó. |
| “`contexts` là toàn bộ ApplicationContext trong JVM.” | Nó là chuỗi context bắt đầu từ context chứa endpoint và đi lên các context cha. |
| “Endpoint từ parent sẽ liệt kê tất cả child.” | Không. Report không tự đi xuống các context con hoặc sibling. |
| “`parentId` là tên bean parent.” | Đây là id của ApplicationContext cha. |
| “Hai context có thể gộp kết quả condition vì chúng chia sẻ bean.” | Mỗi entry có report riêng; condition cụ thể có thể tìm bean ở ancestor nếu search strategy cho phép. |
| “Class không xuất hiện trong negative matches tức là condition đã khớp.” | Có thể class không phải candidate, đã bị exclude hoặc không được nạp; kiểm tra `exclusions` và nguồn auto-configuration. |
| “GET endpoint sẽ chạy lại tất cả condition.” | Endpoint serialize report đã ghi trong quá trình xử lý cấu hình. |
| “`conditions` giống `beans`.” | Conditions giải thích quyết định cấu hình; `beans` liệt kê bean đã đăng ký. |
| “Bật include là đã bảo vệ endpoint.” | Exposure không thay thế authentication/authorization hoặc firewall. |

## 9. Checklist đọc report nhanh

Khi mở `/actuator/conditions`, hãy lần lượt:

1. Xác định context key và `parentId`.
2. Tìm class hoặc method cần điều tra.
3. Nếu ở `positiveMatches`, đọc các message để biết vì sao nó khớp.
4. Nếu ở `negativeMatches`, đọc `notMatched` trước rồi đối chiếu `matched`.
5. Kiểm tra `exclusions` nếu auto-configuration không được đánh giá.
6. Đối chiếu property, classpath, bean name/type và web application type.
7. Nếu condition khớp nhưng bean vẫn thiếu, kiểm tra `/actuator/beans` và lỗi khởi tạo.
8. Nếu context hierarchy có nhiều tầng, đọc từng entry theo `parentId` và nhớ report chỉ đi từ endpoint context lên parent.

**Ghi nhớ:** `/actuator/conditions` là cửa sổ nhìn vào **lý do condition đã khớp hoặc không khớp**. Hãy đọc `positiveMatches`, `negativeMatches`, `unconditionalClasses`, `exclusions` và đặc biệt là `contexts`/`parentId`. Khi biết endpoint đang chạy trong context nào và report bao gồm những ancestor nào, bạn sẽ tránh kết luận sai khi application context và management context có cấu hình khác nhau.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Conditions Evaluation Report API: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 — Actuator Endpoints: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 API — `ConditionsReportEndpoint`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/condition/ConditionsReportEndpoint.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration and `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html