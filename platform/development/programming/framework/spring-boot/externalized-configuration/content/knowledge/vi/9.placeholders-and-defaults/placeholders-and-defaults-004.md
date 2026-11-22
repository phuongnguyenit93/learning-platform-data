# Tên khóa chuẩn dạng kebab-case trong placeholder của Spring Boot

## 1. Vì sao cách viết tên khóa trong `${...}` quan trọng?

Spring Boot cho phép tham chiếu một cấu hình từ cấu hình khác, từ Java hoặc từ annotation bằng **property placeholder**. Ví dụ:

```yaml
catalog:
  display-label: "Sản phẩm mẫu"

screen:
  title: "${catalog.display-label}"
```

Cú pháp `${catalog.display-label}` yêu cầu Spring Boot tìm một property mang tên `catalog.display-label` và thay nó bằng giá trị có hiệu lực tại thời điểm xử lý placeholder.

Tuy nhiên, cùng một ý nghĩa cấu hình có thể được viết theo nhiều kiểu tên tùy nguồn:

```text
catalog.display-label       # canonical kebab-case
catalog.displayLabel        # camelCase trong một số file
CATALOG_DISPLAYLABEL        # biến môi trường theo quy tắc Spring Boot
```

`@ConfigurationProperties` có cơ chế **relaxed binding** để liên kết các biến thể tên vào một thuộc tính Java. Khi viết **placeholder**, Spring Boot khuyến nghị dùng **tên chuẩn dạng kebab-case, toàn chữ thường**, ví dụ `${catalog.display-label}`. Điều này giúp cơ chế phân giải placeholder áp dụng được logic phù hợp với relaxed binding.

Nếu viết `${catalog.displayLabel}`, khả năng nhận những biến thể khác, đặc biệt `catalog.display-label` và biến môi trường tương ứng, có thể bị hạn chế. Đây là lỗi khó thấy: ứng dụng chạy đúng khi cấu hình nằm trong một file thử nghiệm nhưng không nhận được giá trị khi chuyển sang file YAML chuẩn hóa hoặc container.

Bài này giúp bạn:

- Nhận diện cách viết canonical cho property nhiều cấp.
- Phân biệt **tên khóa trong nguồn** với **tên tham chiếu ở placeholder**.
- Dùng `${key}` và `${key:default}` đúng cách.
- Giải thích vì sao kebab-case giúp nhất quán giữa file cấu hình, biến môi trường và `@ConfigurationProperties`.
- Thực hành so sánh placeholder chuẩn, camelCase, giá trị mặc định và tham số ghi đè.
- Chẩn đoán tình huống “property có tồn tại nhưng placeholder không nhận”.
- Tổ chức tên khóa đủ rõ để dễ bảo trì và ít gây xung đột.

**Bối cảnh kỹ thuật:** Java 21 và Spring Boot 3.3.x. Ví dụ trong bài dùng những chuỗi giả lập không nhạy cảm.

## 2. Cấu trúc của một tên khóa canonical

Một tên property Spring Boot được khuyến nghị viết theo dạng:

```text
nhom-cong-viec.thuoc-tinh-con
```

Quy tắc dễ nhớ:

1. Dùng **chữ thường**.
2. Dùng dấu chấm `.` để phân tách **các nhóm/cấp** thuộc tính.
3. Dùng dấu gạch nối `-` để phân tách các từ **trong cùng một phần tên**.
4. Khi tham chiếu bằng placeholder, dùng đúng dạng canonical này.
5. Giữ một quy ước đặt tên duy nhất cho toàn bộ tài liệu và các khóa do ứng dụng tự định nghĩa.

Ví dụ:

| Ý nghĩa | Tên canonical nên dùng | Tên khác có thể xuất hiện |
| --- | --- | --- |
| Nhãn hiển thị của catalog | `catalog.display-label` | `catalog.displayLabel` |
| Thời gian chờ của client | `client.request-timeout` | `client.requestTimeout` |
| Số lần thử lại tối đa | `retry.max-attempts` | `retry.maxAttempts` |
| Cờ bật cache | `cache.feature-enabled` | `cache.featureEnabled` |
| URL máy chủ API | `remote.api-base-url` | `remote.apiBaseUrl` |
| Kích thước lô dữ liệu | `batch.page-size` | `batch.pageSize` |

Dấu chấm không có cùng ý nghĩa với dấu gạch nối:

```text
remote.api-base-url
remote.api.base-url
```

Hai khóa trên mô tả **hai cấu trúc phân cấp khác nhau**. Khóa thứ nhất đặt `api-base-url` dưới `remote`; khóa thứ hai đặt `base-url` dưới `remote.api`. Đừng đổi `.` thành `-` hoặc ngược lại chỉ để làm một tên trông đồng nhất hơn.

Tương tự:

```text
catalog.display-label
catalog.display.label
```

đều có thể là những khóa hợp lệ, nhưng chúng không nên được coi là một property chỉ vì có cùng các từ tiếng Anh.

### 2.1. Canonical không đồng nghĩa với tên biến Java

Ở Java, trường và record component thường được viết bằng camelCase:

```java
public record CatalogProperties(String displayLabel) {}
```

Đó là quy ước cú pháp Java. Trong YAML và placeholder, cách viết được khuyên dùng lại là:

```yaml
catalog:
  display-label: "Sản phẩm mẫu"
```

```java
@Value("${catalog.display-label}")
private String displayLabel;
```

Spring Boot có thể binding `catalog.display-label` vào trường `displayLabel` của Java. **Tên Java không phải lý do để chuyển placeholder thành `${catalog.displayLabel}`.**

### 2.2. Canonical không yêu cầu mọi nguồn dùng một kiểu ký tự

Một biến môi trường thông thường không đặt dấu `.` hoặc `-` theo cách các file `.properties` hay YAML sử dụng. Spring Boot hỗ trợ ánh xạ tên property sang kiểu biến môi trường, nên **tên bạn nhập vào hệ điều hành** và **tên bạn tham chiếu trong mã** có thể khác nhau.

Ví dụ:

```text
Tên canonical:        catalog.display-label
Biến môi trường:      CATALOG_DISPLAYLABEL
Placeholder trong mã: ${catalog.display-label}
```

Chủ ý của canonical form là tạo **một tên tham chiếu ổn định** bất kể giá trị đến từ nguồn nào.

## 3. Placeholder và relaxed binding liên quan ra sao?

Cần phân biệt hai cơ chế:

- **Property placeholder:** `${...}` tham chiếu một giá trị từ `Environment` và thay giá trị vào một chuỗi khác hoặc điểm tiêm `@Value`.
- **Configuration properties binding:** `@ConfigurationProperties` tập hợp nhiều khóa và chuyển thành thuộc tính của một bean Java, có quy tắc ánh xạ tên và kiểu dữ liệu riêng.

Giả sử YAML chứa:

```yaml
catalog:
  display-label: "from-yaml"
```

Java:

```java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String displayLabel) {}
```

Binder có thể đi từ `display-label` đến `displayLabel`. Với placeholder, hãy tham chiếu:

```java
@Value("${catalog.display-label}")
String displayLabel;
```

Cách viết trên giúp Spring Boot dùng logic tương thích với relaxed binding để tìm giá trị khi tên trong nguồn có biến thể.

So sánh:

```text
NÊN DÙNG
${catalog.display-label}

DỄ GÂY HẠN CHẾ KHỚP TÊN
${catalog.displayLabel}
```

Một ví dụ điển hình trong Spring Boot 3.3:

- `${demo.item-price}` có thể xem xét các dạng `demo.item-price`, `demo.itemPrice` trong file cấu hình và dạng môi trường tương ứng `DEMO_ITEMPRICE`.
- `${demo.itemPrice}` không có cùng khả năng xem xét `demo.item-price` và `DEMO_ITEMPRICE`.

Điều này không có nghĩa mọi tổ hợp chữ hoa, dấu gạch dưới, dấu chấm hoặc kiểu viết ngẫu nhiên đều tương đương. Các quy tắc thư giãn tên phụ thuộc nguồn, tính chất của property và dạng tên được hỏi. Vì vậy, **học và dùng tên chuẩn** là phương án bền vững hơn việc ghi nhớ từng biến thể tình cờ hoạt động.

### 3.1. Ưu tiên nguồn vẫn được áp dụng

Canonical form giúp phân giải tên. Nó **không thay đổi thứ tự ưu tiên** giữa file YAML, file profile, biến môi trường, Java system property và đối số dòng lệnh.

Ví dụ:

```yaml
catalog:
  display-label: "from-file"
```

Nếu tiến trình còn có biến môi trường hợp lệ:

```text
CATALOG_DISPLAYLABEL=from-env
```

thì trong trường hợp thông thường, giá trị từ môi trường có ưu tiên hơn file ứng dụng. Placeholder canonical nhận giá trị hiệu lực sau khi Spring Boot xử lý các nguồn. Không nên coi việc placeholder trả `from-env` là bằng chứng file YAML không được nạp; file vẫn có thể đóng góp những thuộc tính khác.

## 4. Ba nơi cần viết tên khóa nhất quán

### 4.1. Trong `application.properties`

Cách trực tiếp:

```properties
catalog.display-label=from-properties
ui.header-text=${catalog.display-label}
```

Trong `application.properties`, dấu `.` thể hiện phân cấp bằng chính tên khóa, còn dấu `-` nằm trong một đoạn tên.

### 4.2. Trong `application.yaml`

Cách lồng nhau:

```yaml
catalog:
  display-label: "from-yaml"

ui:
  header-text: "${catalog.display-label}"
```

YAML nesting tạo ra cấu trúc tương đương `catalog.display-label`. Nếu cần khóa phẳng, có thể viết:

```yaml
catalog.display-label: "from-yaml"
```

nhưng với các nhóm thuộc tính dài, nesting thường dễ đọc hơn.

### 4.3. Trong Java `@Value`

```java
@Value("${catalog.display-label}")
private String catalogLabel;
```

`@Value` hỗ trợ cả giá trị mặc định:

```java
@Value("${catalog.display-label:Chưa đặt nhãn}")
private String catalogLabel;
```

Điểm cần nhớ: sau dấu `:` là fallback của placeholder **khi property không được giải quyết**, không phải tên một profile hay một kiểu property. Tên property trong biểu thức vẫn nên canonical.

## 5. Quy tắc biến môi trường: dấu chấm, gạch nối và gạch dưới

Spring Boot có quy tắc chuyển tên canonical thành tên biến môi trường thường gặp:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch nối `-`.
3. Chuyển tên thành chữ hoa.

Ví dụ:

| Property canonical | Biến môi trường tương ứng |
| --- | --- |
| `catalog.display-label` | `CATALOG_DISPLAYLABEL` |
| `client.request-timeout` | `CLIENT_REQUESTTIMEOUT` |
| `cache.feature-enabled` | `CACHE_FEATUREENABLED` |
| `remote.api-base-url` | `REMOTE_APIBASEURL` |
| `retry.max-attempts` | `RETRY_MAXATTEMPTS` |
| `batch.page-size` | `BATCH_PAGESIZE` |

Dễ nhầm nhất là:

```text
CATALOG_DISPLAYLABEL   # tương ứng catalog.display-label
CATALOG_DISPLAY_LABEL  # thường biểu diễn các cấp catalog.display.label
```

Tương tự, đừng viết `CLIENT_REQUEST_TIMEOUT` rồi mặc định rằng nó luôn ánh xạ giống `client.request-timeout`. Trong một số hệ thống cấu hình khác, quy ước có thể khác; bài này dùng cơ chế relaxed binding của Spring Boot.

Một ví dụ container:

```yaml
# Một phần cấu hình container, chỉ minh họa trường env.
env:
  - name: CATALOG_DISPLAYLABEL
    value: "from-container"
```

Trong application code vẫn dùng:

```java
@Value("${catalog.display-label}")
String label;
```

Cách làm này giữ hợp đồng cấu hình nhất quán giữa chạy local, triển khai Docker và môi trường có quản lý biến.

### 5.1. Dấu gạch nối bị bỏ, không thay thành gạch dưới

Nhìn lại khóa:

```text
service.mail-server-host
```

Nó biểu diễn hai cấp: `service` và `mail-server-host`. Tên biến môi trường là:

```text
SERVICE_MAILSERVERHOST
```

Nếu tự thay mọi dấu gạch nối bằng `_` sẽ nhận:

```text
SERVICE_MAIL_SERVER_HOST
```

Tên thứ hai có thể được diễn giải như các cấp `service.mail.server.host`, khác cấu trúc ban đầu. Đây là nguyên nhân thực tế khiến biến môi trường “có trong container” nhưng placeholder canonical không nhận giá trị mong đợi.

### 5.2. Tránh thiết kế hai khóa dễ va chạm

Nếu nhóm cấu hình cố ý có cả:

```text
feature.my-flag
feature.myflag
```

thì khi chuyển tên theo quy tắc môi trường, hai khóa có thể dẫn tới cùng dạng dễ va chạm. Đừng tạo những tên khác nhau chỉ bằng dấu gạch nối khi ứng dụng phải hỗ trợ nhiều kiểu nguồn. Hãy đặt tên độc lập theo ngữ nghĩa, dùng phân cấp rõ ràng, và kiểm tra các trường hợp triển khai quan trọng.

## 6. Cú pháp giá trị mặc định `${key:default}`

Placeholder thường có hai dạng:

```text
${key}
${key:default}
```

Với `${catalog.display-label}`, nếu không có nguồn nào cung cấp khóa và bộ phân giải placeholder yêu cầu phải giải quyết được, ứng dụng có thể báo lỗi trong quá trình khởi động hoặc tạo bean.

Với:

```yaml
ui:
  header-text: "${catalog.display-label:Catalog}"
```

Spring Boot sử dụng `Catalog` khi `catalog.display-label` không được giải quyết.

Điểm quan trọng:

- **Fallback thuộc về placeholder**, không tự tạo một property mới có tên `catalog.display-label` trong `Environment`.
- Fallback được dùng khi property không có giá trị phù hợp; đừng mặc định rằng chuỗi rỗng, chuỗi chỉ chứa dấu cách hay giá trị sai kiểu sẽ luôn kích hoạt fallback.
- Nếu giá trị có chứa dấu `:` như URL, cần viết expression rõ ràng và thử trong ngữ cảnh sử dụng.
- Placeholder có thể lồng nhau, nhưng nhiều tầng fallback làm cấu hình khó đọc nếu không có lý do rõ.

Ví dụ lồng nhau:

```yaml
ui:
  header-text: "${catalog.display-label:${defaults.display-label:Catalog}}"
```

Ý nghĩa: ưu tiên `catalog.display-label`; nếu thiếu thì đọc `defaults.display-label`; nếu cả hai thiếu thì dùng `Catalog`.

Dù có thể viết:

```yaml
ui:
  header-text: "${catalog.displayLabel:Catalog}"
```

cách này không phải lựa chọn tốt. Hãy sửa **tên khóa bên trong placeholder** thành canonical, thay vì thêm fallback để che lỗi ánh xạ nguồn.

## 7. Ứng dụng mẫu: Canonical Placeholder Observer

Ta tạo ứng dụng Spring Boot console nhỏ để quan sát **cùng một khóa bằng hai cách tham chiếu**, đồng thời binding vào `@ConfigurationProperties`. Chương trình in:

- Giá trị file YAML của một cấu hình giả lập.
- Giá trị nhận được qua `@Value` với placeholder canonical.
- Giá trị qua `@Value` với placeholder camelCase để so sánh.
- Giá trị qua bean `@ConfigurationProperties`.
- Giá trị của một placeholder có fallback.

Chương trình chỉ dùng dữ liệu công khai để học; không in secret hoặc toàn bộ environment variables.

### 7.1. Cấu trúc project

```text
canonical-placeholder/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/placeholder/
    │   │   ├── CanonicalPlaceholderApplication.java
    │   │   ├── CatalogProperties.java
    │   │   └── PlaceholderReport.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/placeholder/
            └── CanonicalPlaceholderTest.java
```

Có thể tạo project từ Spring Initializr với Java 21 và Spring Boot 3.3.x, dùng Gradle. Không cần web dependency vì ứng dụng chỉ in báo cáo. Dùng Gradle Wrapper (`gradlew` và `gradlew.bat`) của project thay vì phụ thuộc bản Gradle cài sẵn trên toàn máy.

### 7.2. Cấu hình Gradle

`settings.gradle`:

```groovy
rootProject.name = 'canonical-placeholder'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong một repository có build convention riêng, giữ quy ước phiên bản Spring Boot và Gradle đang dùng của repository. Bản Gradle trên chỉ minh họa một project đứng riêng.

### 7.3. Khai báo YAML nền

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none

catalog:
  display-label: "from-kebab-file"

ui:
  canonical-title: "${catalog.display-label:missing}"
  camel-title: "${catalog.displayLabel:missing}"
  subtitle: "${catalog.subtitle:No subtitle configured}"
```

Trong file này, `catalog.display-label` có dạng canonical; không có `catalog.displayLabel` như một tên khóa độc lập.

Hai property `ui.canonical-title` và `ui.camel-title` giúp quan sát cách phân giải placeholder. Khi nội dung được dùng ở runtime, `ui.canonical-title` dự kiến nhận giá trị từ `catalog.display-label`, còn `ui.camel-title` có thể nhận fallback `missing` vì tham chiếu không ở dạng canonical.

`ui.subtitle` cho thấy cú pháp fallback thông thường: không có `catalog.subtitle` nên kết quả là `No subtitle configured`.

### 7.4. Khởi động ứng dụng

`src/main/java/dev/example/placeholder/CanonicalPlaceholderApplication.java`:

```java
package dev.example.placeholder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CanonicalPlaceholderApplication {

    public static void main(String[] args) {
        SpringApplication.run(CanonicalPlaceholderApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` giúp phát hiện lớp record binding bên dưới.

### 7.5. Tạo bean binding có kiểu

`src/main/java/dev/example/placeholder/CatalogProperties.java`:

```java
package dev.example.placeholder;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String displayLabel) {}
```

Tên `displayLabel` trong record dùng camelCase vì đó là quy ước Java. Với property `catalog.display-label` trong YAML, Spring Boot binder có thể tạo bean có `displayLabel()` bằng `from-kebab-file`.

Đây là điểm đối chiếu quan trọng: **binder hỗ trợ relaxed binding**; placeholder nên dùng canonical để được áp dụng logic tìm tên tương thích.

### 7.6. In báo cáo theo từng cách truy cập

`src/main/java/dev/example/placeholder/PlaceholderReport.java`:

```java
package dev.example.placeholder;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class PlaceholderReport {

    @Bean
    ApplicationRunner printReport(
            Environment environment,
            CatalogProperties catalog,
            @Value("${catalog.display-label:missing}")
            String canonicalValue,
            @Value("${catalog.displayLabel:missing}")
            String camelValue,
            @Value("${ui.canonical-title:missing}")
            String uiCanonical,
            @Value("${ui.camel-title:missing}")
            String uiCamel,
            @Value("${ui.subtitle:missing}")
            String subtitle) {
        return args -> {
            System.out.println("=== CANONICAL PLACEHOLDER ===");
            System.out.println("canonical @Value = " + canonicalValue);
            System.out.println("camelCase @Value = " + camelValue);
            System.out.println("bound displayLabel = "
                    + catalog.displayLabel());
            System.out.println("ui.canonical-title = " + uiCanonical);
            System.out.println("ui.camel-title = " + uiCamel);
            System.out.println("ui.subtitle = " + subtitle);
            System.out.println("Environment canonical = "
                    + environment.getProperty("catalog.display-label"));
        };
    }
}
```

Chương trình có chủ đích đặt hai tham chiếu cạnh nhau để chứng minh khác biệt về tên. Trong code nghiệp vụ thật, nên dùng `@ConfigurationProperties` cho một nhóm thuộc tính và chỉ dùng `@Value` khi thật sự cần một giá trị đơn lẻ.

`Environment.getProperty("catalog.display-label")` dùng để kiểm tra giá trị theo tên canonical. Nó không phải một phương tiện thay thế cho chính sách bảo vệ secret hoặc công cụ báo nguồn gốc đầy đủ của mọi property.

### 7.7. Chạy chương trình

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Với file nền như trên, các dòng đáng quan sát:

```text
canonical @Value = from-kebab-file
camelCase @Value = missing
bound displayLabel = from-kebab-file
ui.canonical-title = from-kebab-file
ui.camel-title = missing
ui.subtitle = No subtitle configured
Environment canonical = from-kebab-file
```

Khi một dòng trên máy khác dự kiến không giống, hãy kiểm tra các nguồn giá trị bên ngoài trước khi kết luận về cơ chế placeholder. Biến môi trường hoặc đối số CLI có thể đang cấp một dạng tên khác hoặc ghi đè giá trị.

## 8. Thí nghiệm A: đổi khóa trong file thành camelCase

Sửa phần `catalog` của `application.yaml` thành:

```yaml
catalog:
  displayLabel: "from-camel-file"
```

Giữ nguyên các placeholder:

```yaml
ui:
  canonical-title: "${catalog.display-label:missing}"
  camel-title: "${catalog.displayLabel:missing}"
```

Khởi động lại ứng dụng. Kỳ vọng quan trọng:

```text
canonical @Value = from-camel-file
camelCase @Value = from-camel-file
bound displayLabel = from-camel-file
```

Cả hai tham chiếu đều có thể thấy giá trị ở dạng camelCase. Tuy nhiên, việc tham chiếu camelCase **chạy được trong thí nghiệm này** không làm nó thành cách viết tốt hơn. Sự khác nhau rõ hơn khi chuyển ngược về tên kebab-case hoặc dùng biến môi trường.

Sau thí nghiệm, khôi phục YAML gốc với:

```yaml
catalog:
  display-label: "from-kebab-file"
```

và nhớ khởi động lại. Externalized configuration thông thường được nạp khi ứng dụng khởi động; thay file không tự cập nhật bean đang chạy.

## 9. Thí nghiệm B: biến môi trường ghi đè file

Với file nền gốc:

```yaml
catalog:
  display-label: "from-kebab-file"
```

hãy cung cấp biến môi trường theo quy tắc canonical:

```text
CATALOG_DISPLAYLABEL=from-env
```

macOS/Linux (Bash):

```bash
CATALOG_DISPLAYLABEL=from-env ./gradlew bootRun
```

Windows PowerShell:

```powershell
$env:CATALOG_DISPLAYLABEL = 'from-env'
.\gradlew.bat bootRun
Remove-Item Env:CATALOG_DISPLAYLABEL
```

Kết quả cần chú ý:

```text
canonical @Value = from-env
bound displayLabel = from-env
ui.canonical-title = from-env
```

Placeholder canonical và bean binding đọc được nguồn môi trường ưu tiên cao hơn. Placeholder `${catalog.displayLabel:missing}` không được coi là cách tương đương đầy đủ với `${catalog.display-label:missing}`; trong thí nghiệm này nó có thể trở về `missing` nếu không có nguồn nào định nghĩa đúng dạng mà nó hỏi.

Kiểm tra tên biến môi trường trước khi chạy. Nếu bạn khai báo:

```text
CATALOG_DISPLAY_LABEL=from-env
```

đó không phải tên ánh xạ chuẩn của `catalog.display-label` theo quy tắc loại bỏ dấu `-`. Nó thường biểu diễn một cấu trúc property có thêm cấp phân tách.

Nếu dùng Gradle `bootRun`, môi trường của process Java thường kế thừa từ process Gradle. Khi chạy trong Docker hoặc CI, bạn cần bảo đảm biến có mặt trong **môi trường của process thực sự chạy ứng dụng**, không chỉ trong terminal hoặc bước pipeline khác.

## 10. Thí nghiệm C: CLI override và lý do canonical vẫn cần thiết

Dừng ứng dụng rồi chạy:

```bash
./gradlew bootRun --args='--catalog.display-label=from-cli'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--catalog.display-label=from-cli"
```

Kỳ vọng:

```text
canonical @Value = from-cli
bound displayLabel = from-cli
```

Đối số ứng dụng `--catalog.display-label=...` cung cấp tên canonical và trong điều kiện mặc định có ưu tiên cao hơn file ứng dụng. Có thể một số cú pháp tham số camelCase cũng được framework xử lý, nhưng hãy giữ một quy ước canonical cho cả CLI, YAML và placeholder để tránh nhầm lẫn giữa các môi trường.

Phân biệt `--args="..."` là tùy chọn của tác vụ Gradle `bootRun`, còn `--catalog.display-label=...` bên trong là **đối số Spring Boot**. Nếu chạy JAR trực tiếp:

```bash
./gradlew bootJar
java -jar build/libs/canonical-placeholder-0.0.1-SNAPSHOT.jar \
  --catalog.display-label=from-cli
```

Tên file JAR có thể khác khi build convention hoặc phiên bản project thay đổi; hãy dùng tên artifact thực tế của dự án.

## 11. Thí nghiệm D: fallback và placeholder lồng nhau

### 11.1. Khi không có property

YAML:

```yaml
ui:
  subtitle: "${catalog.subtitle:No subtitle configured}"
```

Vì chưa có `catalog.subtitle`, Spring Boot dùng chuỗi mặc định. Nếu thêm:

```yaml
catalog:
  display-label: "from-kebab-file"
  subtitle: "Đang có khuyến mãi"
```

thì `ui.subtitle` lấy từ `catalog.subtitle`.

### 11.2. Khi có hai cấp fallback

Thay thành:

```yaml
ui:
  subtitle: "${catalog.subtitle:${defaults.subtitle:No subtitle configured}}"
```

Ý nghĩa:

1. Ưu tiên `catalog.subtitle`.
2. Nếu thiếu, dùng `defaults.subtitle`.
3. Nếu cả hai thiếu, dùng `No subtitle configured`.

Đây là một ví dụ hợp lệ của **placeholder lồng nhau**, nhưng không nên lạm dụng nhiều tầng trong hệ thống thật: người vận hành sẽ khó biết nguồn nào quyết định giá trị cuối.

### 11.3. Khi giá trị cố ý là chuỗi rỗng

Nếu một nguồn khai báo:

```properties
catalog.subtitle=
```

thì property có thể được coi là **đã tồn tại nhưng có chuỗi rỗng**. Fallback `${catalog.subtitle:...}` không phải công cụ kiểm tra “chuỗi có ý nghĩa hay không”. Nếu cần từ chối chuỗi trống, hãy dùng validation trong `@ConfigurationProperties`, ví dụ `@NotBlank`, hoặc quy tắc nghiệp vụ có chủ đích.

### 11.4. Nếu property bắt buộc

Với cấu hình cần thiết để ứng dụng hoạt động, việc âm thầm dùng fallback có thể che lỗi triển khai. Có thể bỏ fallback:

```java
@Value("${catalog.display-label}")
String displayLabel;
```

hoặc dùng `@ConfigurationProperties` cùng validation phù hợp. Quyết định fallback phải dựa trên ý nghĩa nghiệp vụ, không dựa vào mong muốn để chương trình khởi động bằng mọi giá.

## 12. Kiểm thử hành vi với Spring Boot Test

Khi đổi tên khóa trong YAML hoặc migration từ file sang môi trường, kiểm thử có thể cho biết hợp đồng cấu hình còn hoạt động.

Ví dụ:

`src/test/java/dev/example/placeholder/CanonicalPlaceholderTest.java`:

```java
package dev.example.placeholder;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "catalog.display-label=from-test"
})
class CanonicalPlaceholderTest {

    @Autowired
    CatalogProperties catalog;

    @Test
    void bindsCanonicalKeyToCamelCaseJavaComponent() {
        assertEquals("from-test", catalog.displayLabel());
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên PowerShell:

```powershell
.\gradlew.bat test
```

Test này kiểm tra **tên canonical** trong nguồn cấu hình có thể binding vào trường Java camelCase. Với hệ thống phức tạp hơn, nên viết test cho các nguồn then chốt và các default quan trọng, thay vì suy luận rằng mọi biến thể tên đều được thư viện hỗ trợ.

Muốn kiểm tra trực tiếp placeholder, một bean sử dụng `@Value("${catalog.display-label}")` có thể được inject trong test context, sau đó assert giá trị theo input `catalog.display-label=from-test`. Lưu ý nếu có nhiều nguồn cùng khai báo khóa, test cũng cần kiểm soát thứ tự ưu tiên và các profile đang hoạt động.

### 12.1. Một phép thử nhanh với hai dạng khóa

Hãy đặt cạnh nhau:

```yaml
catalog:
  display-label: "from-kebab"
```

và:

```java
@Value("${catalog.display-label:missing}")
String canonical;

@Value("${catalog.displayLabel:missing}")
String nonCanonical;
```

Khi chạy bài lab, hãy đối chiếu kết quả của cả hai. Sau đó chỉ đổi **một yếu tố**: tên khóa trong YAML thành `displayLabel`. So sánh lại kết quả.

Điểm cần rút ra là **một placeholder không canonical có thể tình cờ chạy đúng với một dạng khai báo**, nhưng dễ mất khả năng tương thích với các dạng khác. Đặt tên canonical giải quyết sự không nhất quán tại điểm tham chiếu.

## 13. Những lỗi đặt tên khóa dễ xảy ra

### 13.1. Dùng camelCase trong placeholder vì trường Java camelCase

```java
// Không nên dùng làm quy ước
@Value("${client.requestTimeout:5s}")
String timeout;
```

Trong khi file dùng:

```yaml
client:
  request-timeout: 5s
```

Cách sửa:

```java
@Value("${client.request-timeout:5s}")
String timeout;
```

Tên record component `requestTimeout` vẫn giữ nguyên. Chỉ chuẩn hóa phần property nằm trong `${...}`.

### 13.2. Đổi dấu gạch nối thành dấu chấm

```text
Đúng ý định:       service.connection-timeout
Khóa khác:         service.connection.timeout
```

Nếu bạn dùng một khóa mới có thêm dấu chấm, đó là một thay đổi cấu trúc, không đơn thuần đổi style. Cần thống nhất schema cấu hình, file, biến môi trường và kiểu binding trước khi triển khai.

### 13.3. Đặt nhầm biến môi trường

```text
APP_FEATUREENABLED   # tương ứng app.feature-enabled
APP_FEATURE_ENABLED  # thường hiểu theo app.feature.enabled
```

Khi giá trị từ Docker không được nhận, hãy kiểm tra đúng tên biến sau chuyển đổi canonical. Đừng thêm hàng loạt alias vào code để sửa một typo trong manifest.

### 13.4. Viết chữ hoa trong placeholder

```java
@Value("${CATALOG_DISPLAYLABEL}")
String label;
```

Cú pháp trên nhắm vào tên property theo kiểu môi trường cụ thể, khiến code dễ phụ thuộc vào cách triển khai. Nếu mục đích là đọc property Spring Boot `catalog.display-label`, nên dùng:

```java
@Value("${catalog.display-label}")
String label;
```

Đây là cách giúp mã Java ít phải biết giá trị đến từ YAML, CLI hay environment.

### 13.5. Dùng fallback để che lỗi tên khóa

```yaml
ui:
  title: "${catalog.displayLabel:Catalog}"
```

Nếu file thực tế chứa `catalog.display-label`, fallback có thể làm ứng dụng trả `Catalog` khiến người phát triển tưởng người vận hành chưa cấu hình. Cách tốt nhất là sửa thành:

```yaml
ui:
  title: "${catalog.display-label:Catalog}"
```

Chỉ sau khi tên chuẩn đã đúng mới quyết định fallback có phù hợp hay không.

### 13.6. Trộn hai khóa tương tự trong cùng file

```properties
catalog.displayLabel=from-camel
catalog.display-label=from-kebab
```

Đây là một cấu hình dễ gây khó đoán khi binding và placeholder vì có hai biểu diễn gần nhau của cùng một ý nghĩa. Hãy chọn một khóa canonical duy nhất, di chuyển giá trị về đó và bỏ alias tự phát nếu không có hợp đồng tương thích rõ ràng.

### 13.7. Quên nguồn ưu tiên cao hơn

Bạn sửa `application.yaml`, nhưng biến môi trường `CATALOG_DISPLAYLABEL` hoặc CLI vẫn có giá trị khác. Placeholder canonical trả nguồn có ưu tiên cao hơn. Đó là hành vi đúng của Externalized Configuration, không phải dấu hiệu kebab-case bị bỏ qua.

### 13.8. Mong giá trị mới có hiệu lực tức thì

Spring Boot thường xử lý file cấu hình và inject/binding giá trị lúc khởi động. Nếu sửa YAML sau khi process đã chạy, bean `@Value` hay `@ConfigurationProperties` không tự động đổi trong cấu hình cơ bản. Cần restart hoặc dùng một cơ chế refresh được thiết kế riêng; cơ chế ấy có vòng đời và giới hạn khác.

## 14. Quy trình chẩn đoán một placeholder không nhận giá trị

Khi gặp ví dụ:

```java
@Value("${catalog.displayLabel:missing}")
String label;
```

mà kết quả không như mong đợi, có thể đi từng bước:

1. **Xác định property có ý nghĩa gì.** Trong ví dụ là “nhãn hiển thị catalog”, không phải một property phụ khác.
2. **Viết lại tên canonical.** Với schema hiện tại là `catalog.display-label`.
3. **Xem giá trị được khai báo từ đâu.** `application.yaml`, `application-dev.yaml`, file ngoài JAR, biến môi trường, system property hay CLI.
4. **Đổi placeholder thành canonical.** Sử dụng `${catalog.display-label:missing}`.
5. **Kiểm tra ánh xạ tên biến môi trường.** Nếu nguồn là hệ điều hành, dùng `CATALOG_DISPLAYLABEL` theo quy tắc chuẩn.
6. **Kiểm tra profile và location.** File có tồn tại không đồng nghĩa nó được nạp; có thể profile không hoạt động hoặc location bị thay bằng `spring.config.location`.
7. **Kiểm tra ưu tiên.** Có nguồn nào cùng khai báo property với ưu tiên cao hơn?
8. **Khởi động mới và quan sát.** Giữ chỉ một yếu tố thay đổi trong mỗi lần thử, ghi lại giá trị hiệu lực từ ứng dụng.
9. **Kiểm tra fallback.** Nếu ứng dụng trả chuỗi mặc định, phân biệt trường hợp property thực sự thiếu với trường hợp viết sai tên.
10. **Kiểm thử lại hợp đồng cấu hình.** Tạo test cho tên canonical đang được ứng dụng và tài liệu dùng.

Trong bài lab có thể dùng `Environment.getProperty("catalog.display-label")` để quan sát một khóa giả lập. Nếu dùng Actuator `/actuator/env` trong môi trường thử nghiệm, phải giới hạn quyền truy cập và không tự động mở giá trị nhạy cảm. Không cần xuất toàn bộ `Environment` để kiểm tra một property cụ thể.

## 15. Phân biệt placeholder, SpEL và shell expansion

Ba cú pháp có thể trông giống nhau nhưng được xử lý ở những tầng khác nhau:

| Cú pháp | Ai xử lý? | Ví dụ |
| --- | --- | --- |
| `${catalog.display-label}` | Bộ phân giải property placeholder của Spring | `@Value("${catalog.display-label}")` |
| `#{...}` | Spring Expression Language (SpEL), trong ngữ cảnh được hỗ trợ | `@Value("#{2 * 3}")` |
| `${VAR}` trong một shell script | Shell, trước khi Java nhận đối số | `echo "${HOME}"` |

Không nên coi cú pháp `${...}` trong tài liệu YAML đồng nghĩa với shell expansion. Trong Spring config, Spring xử lý placeholder; trong shell, trình thông dịch lệnh có thể xử lý chuỗi trước khi chạy ứng dụng. Khi viết lệnh thử nghiệm chứa ký tự `$`, dùng kiểu nháy phù hợp để tránh shell thay thế sai.

Ví dụ muốn truyền một literal placeholder trong lệnh Bash có thể cần dùng nháy đơn để giữ nguyên ký tự `$`, nhưng khi thực sự muốn truyền một property value thì thường chỉ cần:

```bash
./gradlew bootRun --args='--catalog.display-label=from-cli'
```

Sự khác nhau này quan trọng khi viết script triển khai, CI và Docker entrypoint: lỗi expansion của shell có thể xảy ra trước cả khi Spring Boot nhìn thấy cấu hình.

## 16. Khi nào ưu tiên `@ConfigurationProperties` thay vì `@Value`?

Với một giá trị đơn lẻ, `@Value("${catalog.display-label}")` dễ đọc. Nhưng khi có nhiều property liên quan, hãy cân nhắc:

```yaml
client:
  base-url: "https://api.example.test"
  connection-timeout: 3s
  max-attempts: 4
```

Bean binding:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        java.net.URI baseUrl,
        java.time.Duration connectionTimeout,
        int maxAttempts
) {}
```

Spring Boot binding nhóm property vào record với các kiểu `URI`, `Duration` và `int`. Đây là cơ chế phù hợp cho cấu hình có cấu trúc, có validation và được tái sử dụng ở nhiều nơi.

Trong khi đó, placeholder thường xuất hiện khi bạn muốn dùng **giá trị một property bên trong giá trị property khác**, chẳng hạn:

```yaml
client:
  base-url: "https://api.example.test"

report:
  endpoint: "${client.base-url}/reports"
```

Ngay cả khi bean Java đang dùng camelCase `baseUrl`, tên bên trong placeholder vẫn là **`client.base-url`**.

Lưu ý Spring Boot có hỗ trợ relaxed binding sâu cho `@ConfigurationProperties` và conversion kiểu, nhưng `@Value` không phải bản sao của toàn bộ tính năng binder. Càng có nhiều property, việc tập trung qua một bean có kiểu càng giúp giảm phụ thuộc vào chuỗi placeholder rải rác.

## 17. Bài tập luyện tập

Hãy tự viết tên canonical và biến môi trường tương ứng cho những trường sau:

| Thuộc tính trong Java | Prefix | Canonical mong đợi | Biến môi trường |
| --- | --- | --- | --- |
| `requestTimeout` | `client` | `client.request-timeout` | `CLIENT_REQUESTTIMEOUT` |
| `featureEnabled` | `search` | `search.feature-enabled` | `SEARCH_FEATUREENABLED` |
| `maxRetries` | `worker` | `worker.max-retries` | `WORKER_MAXRETRIES` |
| `displayName` | `product` | `product.display-name` | `PRODUCT_DISPLAYNAME` |
| `baseUrl` | `proxy.upstream` | `proxy.upstream.base-url` | `PROXY_UPSTREAM_BASEURL` |

Tiếp theo, xét các trường hợp:

**Câu 1.** File YAML chứa `client.request-timeout`. Bạn nên dùng `${client.requestTimeout}` hay `${client.request-timeout}`? Vì sao?

**Câu 2.** Biến môi trường nào tương ứng với `search.feature-enabled` theo quy tắc canonical: `SEARCH_FEATURE_ENABLED` hay `SEARCH_FEATUREENABLED`?

**Câu 3.** Nếu cả file YAML và biến môi trường có cùng property, placeholder canonical tự chọn file mới sửa hay giá trị có ưu tiên cao hơn trong `Environment`?

**Câu 4.** `${catalog.subtitle:Default subtitle}` được đánh giá như thế nào khi property không có? Nếu property tồn tại với giá trị rỗng thì có luôn dùng `Default subtitle` không?

**Câu 5.** Vì sao `feature.search-timeout` và `feature.search.timeout` không nên được dùng thay nhau?

**Câu 6.** Bạn có record `ClientProperties(Duration connectTimeout)`. Tên key trong YAML và trong placeholder nên viết thế nào?

**Câu 7.** Vì sao việc một placeholder camelCase trả đúng giá trị trên máy phát triển không bảo đảm nó tương thích khi triển khai bằng biến môi trường?

**Câu 8.** Có cần đổi trường Java `displayLabel` thành `display-label` để đúng canonical không?

Gợi ý:

1. `${client.request-timeout}`, vì đây là tên tham chiếu canonical.
2. `SEARCH_FEATUREENABLED` (bỏ dấu gạch nối, thay dấu chấm bằng gạch dưới, viết hoa).
3. Giá trị có hiệu lực theo thứ tự ưu tiên của các property source.
4. Fallback dùng khi không giải quyết được property; chuỗi rỗng là một trường hợp cần xử lý tách biệt.
5. Dấu chấm tạo cấp property khác.
6. `client.connect-timeout` trong YAML và `${client.connect-timeout}` trong placeholder; Java vẫn là `connectTimeout`.
7. Vì camelCase trong placeholder có thể làm mất khả năng phân giải các tên relaxed tương ứng.
8. Không; Java vẫn dùng camelCase, còn YAML/placeholder dùng kebab-case.

## 18. Mẫu quy ước cho dự án thật

Một nhóm phát triển có thể ghi lại quy ước như sau:

```text
Property keys:       canonical kebab-case, phân cấp bằng dấu chấm.
Java fields:         camelCase.
YAML/properties:     dùng canonical form.
@Value placeholders: dùng ${canonical.property-name}.
Default values:      chỉ thêm khi có ý nghĩa nghiệp vụ.
Environment vars:    dot -> underscore, hyphen -> removed, uppercase.
Secrets:             quản lý ở nguồn an toàn, không in log.
```

Ví dụ xuyên suốt:

```yaml
# application.yaml
notification:
  sender-name: "System"
  retry-delay: 5s

mail:
  sender-label: "${notification.sender-name}"
```

```java
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        String senderName,
        java.time.Duration retryDelay
) {}
```

```text
Biến môi trường:
NOTIFICATION_SENDERNAME=Operations

Placeholder:
${notification.sender-name}

Giá trị hiệu lực theo nguồn và ưu tiên:
Operations
```

Việc giữ tên canonical cho placeholder giúp cấu hình còn đọc được khi chuyển từ file đóng gói sang file ngoài, từ laptop sang container hoặc từ test sang production. Điều cần kiểm tra mỗi khi có lỗi là **tên khóa chuẩn, tên nguồn thực tế, ánh xạ của nguồn và thứ tự ưu tiên**. Bắt đầu từ bốn yếu tố này thường giúp tìm nguyên nhân nhanh hơn việc thay đổi fallback hoặc tạo thêm alias ngẫu nhiên.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html), mục **Property Placeholders** và phần sử dụng tên canonical.
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties), mục **Relaxed Binding** và **Binding From Environment Variables**.
- [Spring Framework — Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html), về placeholder và biểu thức giá trị trong bean.