# Giới hạn nạp tài liệu nhiều phần qua @PropertySource và @TestPropertySource trong Spring Boot 3.3

## 1. Vấn đề cốt lõi

Trong Spring Boot 3.3, một file cấu hình có thể gồm nhiều **logical document** (tài liệu logic) đặt trong cùng một file vật lý. Các tài liệu được ngăn cách bằng `---` đối với YAML hoặc `#---`/`!---` đối với .properties. Cơ chế **Config Data** của Spring Boot nhận biết từng tài liệu, áp dụng điều kiện `spring.config.activate.*` và đưa các tài liệu hợp lệ vào `Environment` theo thứ tự ưu tiên.

Ngược lại, các annotation của Spring Framework như:

- `@PropertySource`: khai báo nguồn property tại lớp `@Configuration`.
- `@TestPropertySource`: cung cấp file hoặc thuộc tính bổ sung cho `ApplicationContext` trong test.

**không tự sử dụng bộ nạp multi-document Config Data của Spring Boot**. Hệ quả:

1. File `.properties` nhiều tài liệu **không được xử lý theo ngữ nghĩa multi-document** khi nạp qua hai annotation này. Với bộ nạp properties tiêu chuẩn, dòng `#---`/`!---` chỉ là comment; điều kiện `spring.config.activate.on-profile` không tự bật/tắt phần nằm sau dấu phân cách.
2. File YAML nói chung **không được hai annotation này hỗ trợ trực tiếp với factory mặc định**, kể cả YAML một tài liệu. Spring Framework 6.1 (đi kèm Spring Boot 3.3) có cơ chế cấu hình `PropertySourceFactory` riêng, nhưng một factory tùy chỉnh để đọc YAML **không đồng nghĩa tự nhận đầy đủ ngữ nghĩa Config Data**, đặc biệt là điều kiện kích hoạt tài liệu.
3. Nếu cần **multi-document, profile/cloud activation, thứ tự ưu tiên giữa các document**, nên dùng `application.properties`/`application.yaml` được Spring Boot nạp qua Config Data, hoặc `spring.config.import`/`spring.config.location` hợp lệ.

Đây là một **giới hạn của cách nạp**, không phải việc file .properties/YAML bị sai cú pháp: cùng một file có thể hoạt động đúng qua Config Data nhưng cho kết quả khác khi được đọc dưới dạng `PropertySource` thông thường.

## 2. Multi-document là gì?

### 2.1. Một file .properties có hai tài liệu

```properties
# src/main/resources/application.properties
demo.mode=standard
demo.endpoint=https://api.example.test

#---
spring.config.activate.on-profile=dev
demo.mode=development
demo.endpoint=http://localhost:8080
```

Khi **Config Data loader** nạp file này:

- Document 1 không có điều kiện, nên `demo.mode=standard` và `demo.endpoint=https://api.example.test` là cấu hình chung.
- Document 2 chỉ được kích hoạt nếu biểu thức profile `dev` khớp.
- Nếu `dev` không có hiệu lực, document 2 không được dùng; giá trị chung giữ nguyên.
- Nếu `dev` có hiệu lực, document 2 được thêm sau và có thể ghi đè `demo.mode`, `demo.endpoint` thành giá trị dành cho dev.

Ví dụ chạy:

```bash
java -jar myapp.jar
# demo.mode: standard (nếu dev không được kích hoạt)

java -jar myapp.jar --spring.profiles.active=dev
# demo.mode: development
```

Đây là ngữ nghĩa mà Spring Boot mô tả trong phần **Working With Multi-Document Files** và **Activation Properties**.

### 2.2. YAML tương đương

```yaml
# src/main/resources/application.yaml
demo:
  mode: standard
  endpoint: https://api.example.test
---
spring:
  config:
    activate:
      on-profile: dev
demo:
  mode: development
  endpoint: http://localhost:8080
```

Trong YAML, `---` là cú pháp phân tách tài liệu chuẩn. Trong Config Data, Spring Boot có thể nạp nhiều YAML document, chuyển chúng thành các cặp property phẳng và áp dụng `spring.config.activate.on-profile` cho từng document.

Không dùng `#---` để ngăn cách YAML document: trong YAML đó chỉ là dòng comment, không có chức năng tách tài liệu. Ngược lại, đối với .properties, dùng `#---` hoặc `!---` chứ không dùng `---` trần.

### 2.3. Quy tắc dấu phân cách của .properties

Theo Spring Boot 3.3:

- Separator phải là `#---` hoặc `!---`, đứng **đầu dòng**, không có khoảng trắng phía trước.
- Có **đúng ba dấu gạch nối**.
- Dòng ngay trước và ngay sau separator **không được có cùng prefix comment** với separator.
- Các tài liệu hợp lệ được xử lý **từ trên xuống dưới**; tài liệu sau có thể ghi đè khóa trùng của tài liệu trước khi cùng có hiệu lực.

Ví dụ định dạng dễ đọc:

```properties
demo.mode=standard
#---
spring.config.activate.on-profile=dev
demo.mode=development
```

Ví dụ sau **không phải separator hợp lệ** vì thụt đầu dòng:

```properties
demo.mode=standard
  #---
spring.config.activate.on-profile=dev
demo.mode=development
```

Một dấu `#---` xuất hiện đúng chỗ là cú pháp riêng do **Spring Boot Config Data** hiểu. Bộ đọc `java.util.Properties` truyền thống coi đó là dòng comment; nó không biết khái niệm “document thứ hai”.

## 3. Điều kiện áp dụng cho từng document: `spring.config.activate.*`

Spring Boot 3.3 hỗ trợ các activation property tiêu biểu:

| Thuộc tính | Ý nghĩa trong Config Data |
| --- | --- |
| `spring.config.activate.on-profile` | Chỉ kích hoạt document khi biểu thức profile khớp, ví dụ `dev`, `prod | staging`, `!prod`. |
| `spring.config.activate.on-cloud-platform` | Chỉ kích hoạt document nếu môi trường được phát hiện là nền tảng cloud tương ứng, ví dụ `kubernetes`. |

Ví dụ .properties có hai điều kiện:

```properties
app.label=generic
#---
spring.config.activate.on-profile=prod | staging
spring.config.activate.on-cloud-platform=kubernetes
app.label=k8s-runtime
```

Document thứ hai chỉ có hiệu lực khi **cả hai điều kiện** của document đều thỏa: profile khớp một trong `prod` hoặc `staging` và Spring Boot phát hiện cloud platform là `kubernetes`. Nếu điều kiện không thỏa, `app.label` giữ giá trị `generic` từ document chung, trừ nguồn khác ghi đè.

**Không nhầm với `@Profile` trên bean:** `spring.config.activate.on-profile` là cơ chế kích hoạt **Config Data document**, còn `@Profile` lọc bean/`@Configuration`. Hai cơ chế có thể cùng phụ thuộc tên profile, nhưng chúng diễn ra ở các tầng xử lý khác nhau.

Một document có thể chứa property thông thường, như `app.label`, và điều kiện để file nạp document đó. Điều kiện **chỉ được áp dụng khi chính document được Config Data loader xử lý**.

## 4. `@PropertySource` nạp file bằng cơ chế nào?

`@PropertySource` là annotation của **Spring Framework**, thường viết trên một lớp `@Configuration`:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@PropertySource("classpath:/settings/features.properties")
public class FeatureSettingsConfiguration {
}
```

Với factory mặc định, Spring Framework đọc tài nguyên dạng **properties/XML properties** và đưa các cặp khóa–giá trị vào `Environment`. Đây là cách hợp lệ để bổ sung các property **đơn giản** không yêu cầu Spring Boot Config Data diễn giải nhiều tài liệu.

Ví dụ file một phần:

```properties
# src/main/resources/settings/features.properties
feature.search.enabled=true
feature.search.max-results=20
```

Có thể đọc `feature.search.enabled` và `feature.search.max-results` qua `Environment` hoặc bind phù hợp.

Điều **không có sẵn** khi dùng annotation mặc định là logic:

- Nhận biết `#---` là ranh giới giữa nhiều Config Data documents.
- Diễn giải `spring.config.activate.on-profile` của từng tài liệu.
- Diễn giải `spring.config.activate.on-cloud-platform` để loại bỏ tài liệu.
- Áp dụng quy tắc chọn file/profile và thứ tự document như Boot's Config Data loader.

Vì thế, **“nạp một file thành một PropertySource” và “nạp file nhiều document theo Config Data” là hai hành vi khác nhau**.

### Thời điểm `@PropertySource` được xử lý

`@PropertySource` trên `@Configuration` được thêm trong quá trình `ApplicationContext` refresh. Điều này cũng **muộn hơn** giai đoạn Spring Boot quyết định vị trí tìm Config Data và một số cấu hình bootstrap sớm như logging hoặc `spring.main.*`.

Không nên đặt `spring.config.location` hoặc `spring.config.name` trong file nạp qua `@PropertySource` rồi hy vọng chúng sẽ định tuyến lại bước tải `application.*` từ đầu.

## 5. Ví dụ lỗi rõ nhất: cùng file, kết quả khác nhau

Giả sử có file:

```properties
# src/main/resources/settings/modes.properties
demo.mode=standard
#---
spring.config.activate.on-profile=prod
demo.mode=production
```

### Cách A: nạp qua Config Data

Trong `src/main/resources/application.properties`:

```properties
spring.config.import=classpath:/settings/modes.properties
```

Khi không bật profile `prod`, giá trị từ file import là:

```text
demo.mode=standard
```

Khi chạy `--spring.profiles.active=prod`, document thứ hai của file import được kích hoạt, nên:

```text
demo.mode=production
```

Ví dụ giả định không có nguồn khác ưu tiên cao hơn ghi đè `demo.mode`.

### Cách B: nạp trực tiếp qua `@PropertySource`

```java
@Configuration
@PropertySource("classpath:/settings/modes.properties")
public class ModeConfiguration {
}
```

Với cách đọc `.properties` thông thường, `#---` là comment và hai dòng `demo.mode=...` cùng nằm trong một tập properties. Khi key xuất hiện nhiều lần, giá trị xuất hiện sau có thể ghi đè giá trị trước trong map được parser tạo ra:

```text
demo.mode=production
spring.config.activate.on-profile=prod
```

Ngay cả khi active profile **không phải** `prod`, `demo.mode` vẫn có thể là `production` từ nguồn `@PropertySource` (nếu một nguồn ưu tiên cao hơn không ghi đè nó). Dòng `spring.config.activate.on-profile=prod` ở đây là **một property được đọc như dữ liệu**, không tự biến phần phía sau thành một document được kích hoạt có điều kiện.

**Đây là lỗi nguy hiểm:** ứng dụng có vẻ chạy được, không nhất thiết báo lỗi cú pháp, nhưng giá trị của profile khác lại xuất hiện trong môi trường hiện tại. Vì vậy không dùng `@PropertySource` như cách thay thế `spring.config.import` cho file đa tài liệu.

## 6. `@TestPropertySource` có giới hạn tương tự

`@TestPropertySource` được Spring TestContext Framework dùng trên test class để bổ sung file hoặc các property inline vào `Environment` của test:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(locations = "classpath:/test-overrides.properties")
class FeatureServiceTest {
}
```

Ví dụ file hợp lệ khi dùng annotation:

```properties
# src/test/resources/test-overrides.properties
app.feature-enabled=true
app.timeout=2s
```

Đây là cách phù hợp để áp dụng **những property cố định cho một test**, không phụ thuộc vào việc trong cùng file có các document kích hoạt theo profile.

Nếu file `test-overrides.properties` được viết như sau:

```properties
app.feature-enabled=false
#---
spring.config.activate.on-profile=test
app.feature-enabled=true
```

thì `@TestPropertySource` **không dùng bộ nạp multi-document Config Data** để xác định có nên bỏ qua document thứ hai hay không. Với parser properties tiêu chuẩn, `#---` là comment, `spring.config.activate.on-profile=test` là một cặp property thông thường, và giá trị `true` viết sau có thể thắng trong cùng file **ngay cả khi profile `test` không active**.

Không thể dùng thêm `@ActiveProfiles("test")` như một cách “nâng cấp” annotation để tự hỗ trợ `#---`. `@ActiveProfiles` xác định profile cho test context; còn bộ đọc file của `@TestPropertySource` vẫn là cơ chế Spring TestContext mặc định.

### `@TestPropertySource(properties = "...")` khác gì?

Annotation cho phép khai báo property ngay trong mã test:

```java
@SpringBootTest
@TestPropertySource(properties = {
    "app.feature-enabled=true",
    "app.timeout=2s"
})
class FeatureServiceTest {
}
```

Các chuỗi trên là những **thuộc tính inline**, không phải các document Config Data. `@TestPropertySource(properties = ...)` thuận tiện khi chỉ cần override một vài khóa cho test; không hỗ trợ dùng `#---` để kích hoạt một phần tùy theo profile.

### Thứ tự ưu tiên trong test

Các property test được đưa vào một hoặc nhiều `PropertySource` riêng và thường có độ ưu tiên cao hơn cấu hình ứng dụng thông thường. Điều này khiến lỗi nạp multi-document qua `@TestPropertySource` có thể **che lấp** một giá trị đúng từ `application-test.properties`. Khi một test nhận giá trị không ngờ, trước tiên cần xác định **nó được nạp từ Config Data hay từ test annotation**.

Trong Spring Framework, các property inline của `@TestPropertySource` có độ ưu tiên cao hơn các property từ file được khai báo ở `locations`. Thứ tự đầy đủ khi có thêm `@SpringBootTest(properties=...)`, `@DynamicPropertySource` hoặc custom initializers phụ thuộc cơ chế test cụ thể; không cần giả định annotation nào cũng nằm đúng cùng một tầng.

## 7. YAML: giới hạn mặc định và lựa chọn `PropertySourceFactory`

Spring Boot 3.3 hỗ trợ `application.yaml`/`application.yml` khi nạp qua Config Data. Nhưng Spring Framework **không mặc định dùng YAML parser** chỉ vì annotation trỏ tới một file có đuôi `.yaml` hoặc `.yml`:

```java
// Không phải cách mặc định để nạp YAML qua Spring Framework
@Configuration
@PropertySource("classpath:/settings/features.yaml")
class InvalidAssumptionConfig {
}
```

```java
// @TestPropertySource cũng không tự hiểu YAML khi không có factory thích hợp
@SpringBootTest
@TestPropertySource(locations = "classpath:/test-overrides.yaml")
class InvalidAssumptionTest {
}
```

Không nên cho rằng hai cách trên sẽ có cùng kết quả với việc đặt `features.yaml` vào Config Data.

### Tùy biến nâng cao: `factory`

- `@PropertySource` có thuộc tính `factory` để chỉ định một `PropertySourceFactory` tùy chỉnh.
- Từ Spring Framework **6.1**, `@TestPropertySource` cũng có thuộc tính `factory` để dùng một factory riêng cho định dạng khác như YAML.
- Các lớp hỗ trợ như `YamlPropertiesFactoryBean`, `YamlMapFactoryBean` của Spring Framework hoặc `YamlPropertySourceLoader` trong Spring Boot có thể hỗ trợ tác vụ nạp YAML ở mức thủ công.

Ví dụ chỉ minh họa **cách khai báo custom factory**, không phải bản thân factory:

```java
@Configuration
@PropertySource(
    value = "classpath:/settings/features.yaml",
    factory = CustomYamlPropertySourceFactory.class
)
class FeatureYamlConfig {
}
```

```java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/test-overrides.yaml",
    factory = CustomYamlPropertySourceFactory.class
)
class FeatureYamlTest {
}
```

`CustomYamlPropertySourceFactory` phải là **lớp do dự án tự triển khai** theo giao diện `PropertySourceFactory`; Spring Boot không tự tạo lớp mang tên đó.

**Quan trọng:** một factory tùy chỉnh có thể parse YAML thành property values nhưng **không mặc nhiên** làm đúng mọi bước của Config Data: tách document thành các nguồn độc lập, giải điều kiện on-profile/on-cloud-platform, đặt origin/precedence, xử lý import, location và các quy tắc kích hoạt. Muốn các tính năng đó, dùng cơ chế Config Data sẵn có thay vì tự xây dựng lại.

## 8. Khi cần nhiều tài liệu, nên nạp qua Config Data

### Cách 1 — Đặt trực tiếp trong `application.properties`

```properties
# src/main/resources/application.properties
service.transport=http
service.connect-timeout=3s

#---
spring.config.activate.on-profile=prod
service.transport=https
service.connect-timeout=10s

#---
spring.config.activate.on-profile=dev
service.transport=http
service.connect-timeout=1s
```

**Kết quả dự kiến:**

| Profile có hiệu lực | `service.transport` | `service.connect-timeout` |
| --- | --- | --- |
| Không khớp `prod`/`dev` | `http` | `3s` |
| `prod` | `https` | `10s` |
| `dev` | `http` | `1s` |

Nếu `prod` và `dev` đồng thời khớp thì cần xét **thứ tự document và các nguồn Config Data khác**. Trong file trên, document `dev` nằm sau document `prod`, nên có thể ghi đè khóa trùng nếu cả hai đều có hiệu lực.

Không đặt `spring.profiles.active` hoặc `spring.profiles.default` vào một document **được kích hoạt bằng `spring.config.activate.on-profile`**: Boot 3.3 hạn chế các property điều khiển tập profile ở đây. Hãy đặt chúng trong tài liệu chung không đặc thù profile hoặc nguồn startup phù hợp.

### Cách 2 — Import một file riêng có nhiều document

Giả sử muốn giữ file `settings/notifications.properties` độc lập:

```text
src/main/resources/
├── application.properties
└── settings/
    └── notifications.properties
```

**`application.properties`:**

```properties
spring.config.import=classpath:/settings/notifications.properties
```

**`settings/notifications.properties`:**

```properties
notifications.enabled=false
notifications.channel=console
#---
spring.config.activate.on-profile=prod
notifications.enabled=true
notifications.channel=email
```

`spring.config.import` được xử lý bởi **Config Data loader** khi nó đọc tài liệu khai báo import. Vì thế file được import có thể sử dụng quy tắc nhiều document và activation như các Config Data documents khác. Đây là giải pháp khi muốn file có tên riêng mà vẫn cần điều kiện theo profile.

Nếu location có thể thiếu, dùng `optional:`:

```properties
spring.config.import=optional:classpath:/settings/notifications.properties
```

`optional:` chỉ cho phép thiếu resource, không biến file sai cú pháp hoặc điều kiện không hợp lệ thành hợp lệ.

### Cách 3 — Tách file theo profile

Thay vì gom vào một file nhiều document, có thể đặt:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

**`application.properties`:**

```properties
app.mode=standard
app.timeout=3s
```

**`application-dev.properties`:**

```properties
app.mode=development
app.timeout=1s
```

**`application-prod.properties`:**

```properties
app.mode=production
app.timeout=10s
```

Khi profile phù hợp được kích hoạt, Spring Boot xét file `application-{profile}.properties` cùng với cấu hình chung. Cách này thường dễ đọc nếu số lượng property dành riêng cho từng môi trường lớn. Với nhiều location và profile, precedence vẫn tuân theo thứ tự Config Data.

### Cách 4 — Chỉ định location file từ sớm

Nếu file nằm ngoài các location mặc định:

```bash
java -jar myapp.jar \
  --spring.config.additional-location=optional:file:./deployment/
```

Hoặc khi cần **thay thế** danh sách location mặc định:

```bash
java -jar myapp.jar \
  --spring.config.location=optional:file:./deployment/application.properties
```

`spring.config.name`, `spring.config.location` và `spring.config.additional-location` được đọc rất sớm. Hãy truyền chúng qua OS environment, JVM system properties hoặc command-line arguments **trước khi Config Data quyết định nơi tìm file**. Không đặt chúng trong `@PropertySource` rồi trông đợi việc nạp Config Data quay lại bước tìm kiếm ban đầu.

Nếu chỉ muốn bổ sung một file và đã có `application.properties` đang được nạp, dùng `spring.config.import` thường rõ ràng hơn.

## 9. Khi cần test nhiều profile, nên cấu hình thế nào?

### Phương án A — `@ActiveProfiles` và file profile-specific

Ví dụ:

```text
src/test/resources/
└── application-test.properties
```

**`application-test.properties`:**

```properties
billing.base-url=http://localhost:19090
billing.enabled=false
```

**Test class:**

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class BillingConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void usesTestConfiguration() {
        assertEquals("http://localhost:19090",
                environment.getProperty("billing.base-url"));
        assertEquals("false",
                environment.getProperty("billing.enabled"));
    }
}
```

Trong một dự án Spring Boot Test được cấu hình thông thường, `@ActiveProfiles("test")` làm profile `test` hoạt động; Config Data có thể nạp `application-test.properties` từ classpath test. Không cần `@TestPropertySource` để ép file nhiều document hoạt động.

### Phương án B — Config Data nhiều tài liệu trong test

Đặt cấu hình chung và document dành cho test ở `src/test/resources/application.properties` hoặc một file Config Data được import:

```properties
app.region=global
app.retry-count=3
#---
spring.config.activate.on-profile=test
app.region=test-lab
app.retry-count=1
```

Dùng `@SpringBootTest` kèm `@ActiveProfiles("test")`. Ở đây file được nạp bởi **Spring Boot Config Data** và các document được kích hoạt đúng theo profile.

**Lưu ý:** file `src/test/resources/application.properties` có thể che khuất file cùng tên ở `src/main/resources` tùy classpath/build setup. Nếu cần chỉ thêm một số property, dùng `application-test.properties` hoặc import riêng để giảm nhầm lẫn.

### Phương án C — Một ít override test: `@TestPropertySource` vẫn rất phù hợp

```java
@SpringBootTest
@TestPropertySource(properties = {
    "billing.base-url=http://localhost:19090",
    "billing.enabled=false"
})
class BillingServiceTest {
}
```

Hoặc:

```java
@SpringBootTest(properties = "billing.enabled=false")
class BillingServiceTest {
}
```

Các cách này hữu ích khi chỉ cần **override trực tiếp** vài property, không cần bật/tắt nhiều document theo điều kiện. Không có lý do phải tạo file multi-document khi dữ liệu test chỉ gồm vài key/value cố định.

### Phương án D — File riêng nhưng không cần điều kiện: `@TestPropertySource(locations=...)`

```java
@SpringBootTest
@TestPropertySource(locations = "classpath:/test-overrides.properties")
class BillingServiceTest {
}
```

**`test-overrides.properties`:**

```properties
billing.base-url=http://localhost:19090
billing.enabled=false
```

Đây vẫn là cách được hỗ trợ vì file chỉ là **một tập properties thông thường**.

## 10. So sánh phạm vi hỗ trợ

| Tính năng | Config Data trong Spring Boot 3.3 | `@PropertySource` mặc định | `@TestPropertySource` mặc định |
| --- | --- | --- | --- |
| File `.properties` một phần | Có | Có | Có |
| File `.yaml`/`.yml` | Có | Không tự hỗ trợ | Không tự hỗ trợ |
| Tách file `.properties` bằng `#---`/`!---` thành nhiều document | Có | Không | Không |
| Tách YAML bằng `---` theo ngữ nghĩa Spring Boot | Có | Không | Không |
| `spring.config.activate.on-profile` cho từng document | Có | Không | Không |
| `spring.config.activate.on-cloud-platform` cho từng document | Có | Không | Không |
| `spring.config.import` và location theo cơ chế Config Data | Có | Không tự thực hiện | Không tự thực hiện |
| Thêm property từ file thường vào `Environment` | Có | Có | Có (trong test context) |
| Override một vài giá trị test inline | Qua nguồn khác/CLI/test API | Không phải mục đích chính | Có, với `properties={...}` |
| Factory tùy chỉnh để đọc định dạng khác | Có các Config Data SPI riêng | Có `factory` | Có `factory` từ Spring Framework 6.1 |

**“Không” ở bảng nghĩa là annotation/factory mặc định không có semantics tương ứng.** Việc tự viết `PropertySourceFactory` hoặc một extension SPI có thể cung cấp hành vi riêng, nhưng kết quả đó phải được kiểm tra theo implementation và không được tự động xem là hành vi chuẩn của Spring Boot Config Data.

## 11. Nếu chỉ muốn nạp file tùy theo profile mà không cần Config Data multi-document

Một cách khác là điều kiện hóa một lớp `@Configuration`:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.context.annotation.PropertySource;

@Configuration
@Profile("dev")
@PropertySource("classpath:/settings/dev-only.properties")
class DevOnlyPropertiesConfiguration {
}
```

Khi điều kiện bean/configuration profile `dev` khớp, lớp này được xử lý và file `dev-only.properties` có thể được thêm vào `Environment`. File cần ở **dạng properties thông thường, không đa tài liệu**.

Đây là lựa chọn hợp lệ cho một số cấu hình của bean hoặc ứng dụng chạy **sau khi context refresh**. Nó **không tương đương** với Config Data:

- Nguồn được thêm **muộn hơn**; không dùng cho cấu hình cần đọc rất sớm như định tuyến tìm file `spring.config.location` hoặc một phần cấu hình logging.
- Thứ tự ưu tiên của `@PropertySource` cũng **khác** Config Data.
- Không nhận `spring.config.activate.*` trong file được nạp, và không tạo cơ chế phân tách document.

Nếu mục tiêu thực sự là “file cấu hình theo profile” trong Spring Boot, `application-dev.properties` hoặc Config Data import vẫn là lựa chọn quen thuộc hơn.

## 12. Vì sao không nên tự xử lý `#---` bằng parser properties thông thường?

Dòng comment `#---` **không có ý nghĩa đặc biệt** trong chuẩn Java Properties. Parser chuẩn thường đọc mỗi cặp `key=value` và với key lặp lại, giá trị cuối sẽ thay thế giá trị trước. Ví dụ:

```properties
service.level=basic
#---
spring.config.activate.on-profile=prod
service.level=advanced
```

Nếu toàn bộ file được nạp như một tài liệu properties đơn, kết quả logic sẽ gần như:

```text
service.level=advanced
spring.config.activate.on-profile=prod
```

Không có thông tin “`advanced` chỉ áp dụng nếu profile prod”; thông tin đó chỉ xuất hiện khi Config Data phân tách tài liệu và xử lý activation trước khi đưa chúng vào `Environment`.

Điều này giải thích tại sao một ứng dụng/test có thể **không ném exception** nhưng vẫn chạy với cấu hình thuộc sai môi trường. Khi thấy sai giá trị, không chỉ kiểm tra tên profile; cần kiểm tra **nguồn nào và cơ chế loader nào** đã đưa key vào `Environment`.

## 13. Chẩn đoán lỗi tải file và sai điều kiện

### 13.1. Dấu hiệu thường gặp

| Dấu hiệu | Khả năng cao | Cần làm |
| --- | --- | --- |
| `@TestPropertySource` tải file có `#---` nhưng giá trị dev/prod xuất hiện ở mọi test | File bị parser properties thường đọc như một tập key/value | Chuyển nội dung điều kiện sang `application-{profile}.*` hoặc Config Data import |
| `@PropertySource` đọc YAML không ra thuộc tính như kỳ vọng | Annotation mặc định không có YAML parser | Dùng Config Data YAML hoặc factory riêng nếu thực sự cần |
| `spring.config.activate.on-profile` vẫn hiện trong `Environment` nhưng điều kiện không có hiệu lực | Nó chỉ được đọc như property thông thường | Xác định file có đi qua Config Data loader hay không |
| `application.properties` multi-document không kích hoạt đúng | Dấu phân cách sai hoặc profile không khớp | Kiểm tra `#---`, khoảng trắng và active/default profiles |
| File import không được nạp | File chứa `spring.config.import` chưa được tìm hoặc location sai | Xác định Config Data locations và resource path |
| Test profile thay đổi nhưng property vẫn giữ giá trị cố định từ test annotation | `@TestPropertySource` có độ ưu tiên riêng | Tìm và kiểm tra `@TestPropertySource`/inline test overrides |

### 13.2. Quan sát giá trị và nguồn

Ví dụ code chẩn đoán:

```java
package com.example.demo.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class PropertySourceDiagnostics {

    @Bean
    ApplicationRunner showDemoMode(ConfigurableEnvironment env) {
        return args -> {
            String key = "demo.mode";
            System.out.println("Effective value: " + env.getProperty(key));

            for (PropertySource<?> source : env.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("Source containing " + key + ": "
                            + source.getName());
                }
            }
        };
    }
}
```

Đoạn này giúp kiểm tra:

- Có nhiều nguồn cùng khai báo `demo.mode` không?
- Giá trị hiệu lực xuất hiện từ nguồn nào theo thứ tự xét của `Environment`?
- Nguồn có tên thể hiện Config Data resource hay một property source từ test annotation/custom source?

Tên cụ thể của các `PropertySource` có thể khác theo phương thức nạp; code trên chỉ in tên nguồn và một property không nhạy cảm, tránh in toàn bộ cấu hình chứa secret.

Nếu bật Spring Boot Actuator và có cấu hình bảo vệ phù hợp, endpoint `/actuator/env` cũng có thể giúp quan sát nguồn property và giá trị đã được che một phần. Không mở endpoint chẩn đoán công khai chỉ để kiểm tra tài liệu đa phần.

### 13.3. Một bài thử đơn giản

Để xác nhận cơ chế, tạo `src/main/resources/application.properties`:

```properties
demo.mode=base
#---
spring.config.activate.on-profile=dev
demo.mode=dev
```

Chạy lần 1:

```bash
java -jar myapp.jar
```

Khi không có active/default profile nào khớp `dev`, `demo.mode` dự kiến là `base`.

Chạy lần 2:

```bash
java -jar myapp.jar --spring.profiles.active=dev
```

`demo.mode` dự kiến là `dev`.

Sau đó so sánh với việc chuyển **cùng nội dung .properties** sang một file được gắn `@PropertySource`. Nếu chỉ dùng loader properties thông thường, giá trị cuối `dev` có thể còn hiện diện dù `dev` không active. Đó là chỉ dấu rõ ràng của khác biệt loader, không phải lỗi của `@Profile` hay `@ActiveProfiles`.

## 14. Những nhầm lẫn nên tránh

**Nhầm 1: “File kết thúc bằng .properties nên Boot chắc chắn xử lý #---.”** Không đúng. Cần biết **file được nạp bởi loader nào**. Một file `application.properties` do Config Data xử lý và một file `test-overrides.properties` do `@TestPropertySource` đọc có thể dùng cùng định dạng nhưng ngữ nghĩa tài liệu khác nhau.

**Nhầm 2: “Đã có @ActiveProfiles, @TestPropertySource tự hiểu on-profile.”** `@ActiveProfiles` cung cấp profile cho test context; nó không làm bộ parser properties của `@TestPropertySource` tự tách tài liệu theo `#---`.

**Nhầm 3: “Annotation tải được .yaml theo cách Boot tải application.yaml.”** `@PropertySource`/`@TestPropertySource` mặc định không dùng cùng YAML loader với Config Data. Muốn YAML qua annotation cần factory tương ứng, và factory thường vẫn không có activation semantics.

**Nhầm 4: “Dòng spring.config.activate.on-profile trong mọi PropertySource đều điều kiện hóa các khóa bên cạnh.”** Điều kiện này có ý nghĩa khi Config Data loader xử lý **document**. Đưa cùng key vào một `PropertySource` thông thường không tạo phạm vi điều kiện.

**Nhầm 5: “Chỉ cần đặt spring.config.import ở @PropertySource là Boot sẽ tải file theo import.”** `@PropertySource` được xử lý sau giai đoạn Config Data thông thường; property import được đọc muộn trong source này không làm bộ nạp Config Data tự chạy lại. Đặt import ở document Config Data hợp lệ.

**Nhầm 6: “Sau dấu #---, các dòng đều bị bỏ qua.”** Trong parser properties thường, chỉ **chính dòng comment** bị bỏ qua; các dòng key/value phía sau vẫn được đọc, nên giá trị trùng khóa có thể bị thay thế.

**Nhầm 7: “Nhiều file locations trong @TestPropertySource là nhiều logical document.”** Mỗi file có thể trở thành một property source test riêng, nhưng đó vẫn không phải multi-document Config Data với điều kiện `spring.config.activate.*`.

**Nhầm 8: “Có custom YAML factory là đã đủ thay thế Config Data.”** Factory hỗ trợ đọc định dạng; để có cùng semantics cần thêm logic tách document, activation, precedence, import và origin. Không giả định các hành vi này xuất hiện tự động.

## 15. Chọn công cụ đúng cho từng mục đích

1. **Cần một file cấu hình có nhiều phần, bật/tắt theo profile/cloud platform:** dùng **Config Data** và `#---`/`---`, với `spring.config.activate.*`.
2. **Cần một file riêng được nạp bằng Config Data dù tên không phải application:** đặt `spring.config.import` trong file Config Data đã tìm thấy, hoặc cấu hình location từ sớm.
3. **Cần một file theo môi trường:** sử dụng `application-dev.properties`, `application-prod.yaml` hoặc các biến thể tương ứng.
4. **Cần một file properties đơn giản được thêm khi cấu hình bean:** `@PropertySource` phù hợp nếu không phụ thuộc startup rất sớm và không dùng multi-document.
5. **Cần một số property test cố định:** `@TestPropertySource(properties=...)` hoặc `@SpringBootTest(properties=...)`.
6. **Cần file properties riêng cho test:** `@TestPropertySource(locations=...)` với file một tài liệu.
7. **Cần điều kiện profile cho test configuration:** `@ActiveProfiles` cùng Config Data profile-specific hoặc multi-document; không dựa vào việc `@TestPropertySource` hiểu separator.
8. **Cần YAML qua annotation vì lý do đặc thù:** triển khai `PropertySourceFactory` và xác định rõ ngữ nghĩa được hỗ trợ; nếu cần activation semantics chuẩn thì ưu tiên chuyển sang Config Data.

## 16. Nguồn tham khảo

- Spring Boot **3.3** Reference – **Externalized Configuration**, phần *Working With Multi-Document Files*, *Activation Properties*, *Working With YAML*, *Importing Additional Data* và *PropertySource Order*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework **6.1** Reference – **Context Configuration with Test Property Sources**, các thuộc tính `locations`, `properties` và `factory`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Framework **6.1** API – `TestPropertySource`, đặc biệt `factory()` và định dạng file được hỗ trợ mặc định: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/TestPropertySource.html
- Spring Framework Reference – **Using @PropertySource** và `PropertySourceFactory`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/propertysource.html

**Kết luận kiến thức:** Trong Spring Boot 3.3, **định dạng nhiều document là khả năng của Config Data loader**. `@PropertySource` và `@TestPropertySource` mặc định đọc nguồn properties như một tập key/value, không tự phân tách hoặc lọc các phần theo `spring.config.activate.*`. Muốn giữ đúng hành vi nhiều tài liệu có điều kiện, hãy nạp file qua **Config Data**, sử dụng file theo profile hoặc `spring.config.import`; còn hai annotation phù hợp với các nguồn properties đơn giản và override test.
