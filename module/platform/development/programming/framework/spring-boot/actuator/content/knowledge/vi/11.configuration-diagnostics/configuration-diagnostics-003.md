# Đọc endpoint configprops để kiểm tra bean gắn @ConfigurationProperties

## 1. Từ “tệp cấu hình viết gì” đến “bean đang giữ giá trị gì”

Giả sử trong YAML ta đặt thời gian chờ kết nối là `1500ms`, nhưng ứng dụng lại chờ ngắn hơn dự kiến. Đọc lại tệp đó chưa đủ để kết luận: tham số khởi động có thể đã ghi đè giá trị, profile khác có thể đang hoạt động, hoặc lớp cấu hình chưa được đăng ký thành bean.

**Endpoint `configprops`** cung cấp báo cáo về các bean gắn `@ConfigurationProperties` trong ứng dụng đang chạy. Nó giúp kiểm tra ba câu hỏi liên tiếp:

1. Bean cấu hình cần tìm có xuất hiện không và được liên kết với tiền tố nào?
2. Những thuộc tính được báo cáo của bean đang có giá trị gì?
3. Giá trị đầu vào dùng khi liên kết đến từ đâu, nếu thông tin nguồn được ghi nhận?

Trong bài, **liên kết cấu hình (binding)** là quá trình lấy thuộc tính từ nguồn cấu hình, chuyển kiểu và đưa vào đối tượng Java. **Tiền tố (prefix)** xác định nhóm tên cấu hình, ví dụ `app.catalog`. **Nguồn gốc (origin)** mô tả nơi một đầu vào được lấy ra, chẳng hạn tệp YAML và vị trí dòng/cột.

```text
application.yml / profile / biến môi trường / tham số khởi động
                  ↓ Environment và thứ tự ưu tiên
                  ↓ Binder: tìm thuộc tính, chuyển kiểu, tạo/gán bean
           bean @ConfigurationProperties
                  ↓ GET /actuator/configprops
       báo cáo theo context, bean, properties và inputs
```

Đây là công cụ quan sát để chẩn đoán. Thao tác GET không chỉnh tệp YAML, không thay đổi giá trị và không tự làm các bean được liên kết lại.

### Đặt configprops đúng vị trí trong bộ công cụ

| Công cụ | Câu hỏi phù hợp |
| --- | --- |
| `configprops` | Bean `@ConfigurationProperties` nào đang được báo cáo, với giá trị và đầu vào nào? |
| `env` | Environment có thuộc tính nào, ở nguồn nào và nguồn nào đang có ưu tiên? |
| `beans` | Những bean nào tồn tại trong ngữ cảnh Spring? |
| `conditions` | Điều kiện auto-configuration nào khớp hoặc không khớp? |
| Log lỗi khởi động | Vì sao chuyển kiểu, tạo bean hoặc kiểm tra dữ liệu cấu hình thất bại? |

`configprops` không phải bản sao tất cả tệp cấu hình, cũng không phải danh sách mọi field được gắn `@Value`. Báo cáo chỉ cho thấy phần mà endpoint thu thập và biểu diễn được từ các bean cấu hình.

## 2. Đọc cấu trúc response trước khi kết luận

Hai URL quan trọng trong Spring Boot 3.3:

```http
GET /actuator/configprops
GET /actuator/configprops/app.catalog
```

URL đầu trả báo cáo chung. URL sau lọc theo tiền tố đã đăng ký của bean; vẫn giữ cấu trúc báo cáo theo context. Có thể dùng tiền tố rộng hơn, ví dụ `/actuator/configprops/app`. [Hợp đồng REST configprops của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

| Thành phần | Ý nghĩa khi đọc |
| --- | --- |
| `contexts` | Các ngữ cảnh ứng dụng được báo cáo, khóa là mã định danh context |
| `contexts.*.parentId` | Mã định danh context cha, nếu có |
| `contexts.*.beans` | Các bean cấu hình trong từng context, khóa là tên bean |
| `prefix` | Tiền tố liên kết của bean |
| `properties` | Biểu diễn những thuộc tính được báo cáo của đối tượng bean |
| `inputs` | Giá trị đầu vào và thông tin nguồn được ghi nhận khi binding |

Không cố định mọi công cụ vào `contexts.application`: mã định danh context có thể thay đổi theo tên ứng dụng, cấu hình hoặc cấu trúc context. Cũng không dùng tên bean làm tên thuộc tính cấu hình.

Với lớp đăng ký bằng `@EnableConfigurationProperties` trong ví dụ phía sau, tên bean theo quy ước là:

```text
app.catalog-example.configprops.CatalogClientProperties
```

Đây là **một khóa JSON chứa cả dấu chấm và dấu gạch nối**, không phải chuỗi đường dẫn JSON lồng nhau. Khi dùng thư viện JSON, truy cập nó như khóa map hoặc tìm mục có `prefix` phù hợp; tránh viết đường dẫn dùng dấu chấm khiến công cụ tách tên bean thành nhiều đoạn.

### properties và inputs giải thích hai mặt khác nhau

Nếu cấu hình chứa `connect-timeout: 1500ms`, bean dùng kiểu `Duration`, ta có thể thấy:

```json
{
  "properties": {
    "connectTimeout": "PT1.5S"
  },
  "inputs": {
    "connectTimeout": {
      "value": "1500ms"
    }
  }
}
```

Đây là phần trích để tập trung vào giá trị; báo cáo thực còn có các trường khác và thông tin nguồn khi có.

- `properties.connectTimeout` thể hiện giá trị sau chuyển kiểu, được biểu diễn ra JSON. `PT1.5S` là thời lượng 1,5 giây theo cách biểu diễn ISO-8601.
- `inputs.connectTimeout.value` là giá trị đầu vào đã ghi nhận cho thuộc tính đó.
- `inputs.connectTimeout.origin` giúp tìm nguồn của đầu vào; vị trí dòng/cột là thông tin của môi trường chạy cụ thể.

Sự khác nhau giữa `1500ms` và `PT1.5S` không chứng minh cấu hình sai. Cần so sánh **ý nghĩa và kiểu dữ liệu**, không chỉ chuỗi ký tự.

Nếu một thuộc tính lấy mặc định từ mã Java hoặc `@DefaultValue`, `properties` có thể có giá trị trong khi mục tương ứng của `inputs` là `{}`. Không được suy luận rằng `inputs` trống đồng nghĩa bean không có giá trị.

## 3. Dự án thực hành: kiểm tra cấu hình một client danh mục

Ví dụ độc lập dùng Java 21, Spring Boot 3.3.0 và Gradle 8.5, thuộc nền tảng Boot 3.3.x của bài học. Không cần cơ sở dữ liệu hoặc dịch vụ từ xa: URL trong cấu hình chỉ là dữ liệu minh họa và không được gọi.

Mục tiêu là quan sát:

- `baseUrl` được chuyển thành `URI`;
- `connectTimeout` được chuyển thành `Duration`;
- `maxAttempts` nhận mặc định `3`;
- giá trị đầu vào và vị trí nguồn khác với biểu diễn trong bean;
- che giá trị chỉ tác động đến báo cáo, không thay đổi bean.

### 3.1. Tệp build

Tệp `settings.gradle`:

```groovy
rootProject.name = 'configprops-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các tệp build này dành cho thư mục thực hành mới. Trong repository có quy ước Gradle chung, hãy sử dụng quy ước sẵn có của module thay vì thay thế build bằng ví dụ này.

### 3.2. Bean cấu hình và ứng dụng

Tệp `src/main/java/example/configprops/CatalogClientProperties.java`:

```java
package example.configprops;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        @DefaultValue("3") int maxAttempts) {
}
```

Tệp `src/main/java/example/configprops/ConfigpropsDemoApplication.java`:

```java
package example.configprops;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CatalogClientProperties.class)
public class ConfigpropsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigpropsDemoApplication.class, args);
    }
}
```

`@ConfigurationProperties` mô tả cách liên kết; `@EnableConfigurationProperties` đăng ký kiểu đó theo cơ chế cấu hình của Boot. Chỉ viết annotation trên một lớp rồi để nó ngoài mọi cơ chế đăng ký sẽ không tự tạo bean.

Có thể sử dụng `@ConfigurationPropertiesScan` thay cho đăng ký tường minh. Với record liên kết qua constructor như ví dụ, không thêm `@Component` chỉ để cố ép nó trở thành bean thông thường.

Khóa YAML dùng `base-url`, `connect-timeout`, `max-attempts`; thành phần record dùng `baseUrl`, `connectTimeout`, `maxAttempts`. Đây là cách đặt tên tương ứng được hỗ trợ bởi cơ chế liên kết linh hoạt tên thuộc tính (relaxed binding). [Liên kết cấu hình có kiểu trong Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).

### 3.3. Cấu hình nền: báo cáo có che giá trị

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: configprops-demo

app:
  catalog:
    base-url: https://catalog.example.test
    connect-timeout: 1500ms

management:
  endpoint:
    configprops:
      enabled: true
      show-values: never
  endpoints:
    web:
      exposure:
        include: health,configprops
```

`max-attempts` được chủ ý bỏ khỏi YAML để quan sát mặc định từ `@DefaultValue`.

Có ba việc độc lập:

1. `enabled` quyết định endpoint có được bật.
2. `web.exposure.include` đưa endpoint vào tập được công bố qua HTTP.
3. `show-values` quyết định chính sách hiển thị giá trị trong response.

Ví dụ không thêm Spring Security và chỉ lắng nghe loopback. Trong ứng dụng đã có chuỗi bộ lọc bảo mật, exposure không tự cấp quyền truy cập; phải đáp ứng cơ chế xác thực và phân quyền của ứng dụng.

### 3.4. Chế độ chẩn đoán cục bộ

Tệp `src/main/resources/application-diagnostic.yml`:

```yaml
management:
  endpoint:
    configprops:
      show-values: always
```

Profile này phục vụ thực hành với dữ liệu giả trên loopback. Khi bật, chính sách hiển thị áp dụng cho toàn bộ báo cáo `configprops` mà người gọi truy cập được, không chỉ bean `app.catalog`.

Tên `diagnostic` không có quyền đặc biệt: đây chỉ là profile do ta đặt tên. Không coi tên profile là cơ chế bảo mật.

## 4. Thực hiện một lượt đọc và giải thích bằng chứng

### 4.1. Khởi động ở chế độ nền

Trong thư mục dự án, với JDK 21 và Gradle 8.5 đã cài, tạo wrapper:

```shell
gradle wrapper --gradle-version 8.5
```

Sau đó, trên PowerShell:

```powershell
.\gradlew.bat bootRun
```

Linux/macOS sử dụng `./gradlew bootRun`. Không chạy riêng các class bằng `javac` thiếu classpath; dự án cần các dependency Spring và tài nguyên YAML.

Ở terminal thứ hai:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/configprops/app.catalog
```

Trên Windows dùng `curl.exe` nếu `curl` là alias. Có thể thêm `-i` để xem status và header. Response thành công có mã HTTP 200; không cố định thứ tự khóa, mã context, Content-Length hay cách xuống dòng.

Tìm bean có `prefix` bằng `app.catalog`. Phần `properties` của nó ở chế độ nền có dạng:

```json
{
  "baseUrl": "******",
  "connectTimeout": "******",
  "maxAttempts": "******"
}
```

Cả giá trị không có vẻ nhạy cảm cũng bị che. `******` là kết quả của chính sách hiển thị, không phải mật khẩu mặc định, dữ liệu gốc hoặc dấu hiệu binding thất bại. Đừng sửa YAML thành `******` để “khớp” response.

### 4.2. Đọc giá trị thật trong bài thực hành

Dừng tiến trình đang chạy, rồi khởi động lại:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=diagnostic"
```

Đọc lại URL trên. Nếu có `jq`, lệnh sau duyệt mọi context và chọn bean theo tiền tố:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/configprops/app.catalog | jq '.contexts[] | .beans | to_entries[] | select(.value.prefix == "app.catalog") | .value.properties'
```

Kết quả về mặt cấu trúc và giá trị:

```json
{
  "baseUrl": "https://catalog.example.test",
  "connectTimeout": "PT1.5S",
  "maxAttempts": 3
}
```

Đây là JSON đã định dạng để đọc; thứ tự trường không phải cam kết. `jq` là công cụ tùy chọn, không phải dependency của ứng dụng.

Đọc thông tin đầu vào:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/configprops/app.catalog | jq '.contexts[] | .beans | to_entries[] | select(.value.prefix == "app.catalog") | .value.inputs'
```

Quan sát và đối chiếu:

| Thuộc tính trong báo cáo | properties | inputs | Diễn giải |
| --- | --- | --- | --- |
| `baseUrl` | Chuỗi biểu diễn URI | Có giá trị URL và nguồn YAML | Bean nhận đầu vào được cấu hình |
| `connectTimeout` | `PT1.5S` | Giá trị `1500ms` và nguồn YAML | Chuyển kiểu thời lượng đã diễn ra |
| `maxAttempts` | Số `3` | `{}` trong ví dụ này | Mặc định từ annotation, không phải một dòng YAML bị bỏ sót |

Nguồn YAML thường chỉ ra tài nguyên `application.yml` cùng dòng/cột. Không viết công cụ kiểm tra phụ thuộc cứng vào số dòng, vì thêm chú thích hoặc đổi vị trí khai báo sẽ làm vị trí thay đổi.

### 4.3. Chứng minh một giá trị bị ghi đè

Dừng tiến trình, khởi động lại với đầu vào ưu tiên hơn:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=diagnostic --app.catalog.connect-timeout=750ms"
```

Đọc lại cùng bean. Kết quả kỳ vọng:

```json
{
  "baseUrl": "https://catalog.example.test",
  "connectTimeout": "PT0.75S",
  "maxAttempts": 3
}
```

`inputs.connectTimeout.value` lúc này là `750ms`; thông tin nguồn nhận diện đầu vào từ tham số khởi động. YAML vẫn ghi `1500ms`, nhưng nó không phải nguồn thắng cho thuộc tính này trong lượt chạy đó.

Các nguồn cấu hình có thứ tự ưu tiên. Với ứng dụng mẫu dùng hành vi mặc định, tham số dòng lệnh có thể ghi đè cấu hình trong tệp. Không suy rộng một thứ tự đơn giản cho mọi bối cảnh kiểm thử, Config Data hoặc tích hợp tùy biến. [Thứ tự nguồn và tham số dòng lệnh](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.command-line-args).

**Bằng chứng chẩn đoán đầy đủ** là ba điểm cùng khớp: đúng bean/tiền tố → giá trị có kiểu trong `properties` → đầu vào và nguồn trong `inputs`. Chỉ thấy một dòng YAML hoặc một giá trị trong Environment chưa hoàn thành chuỗi đối chiếu này.

## 5. Lọc theo tiền tố đúng cách

```http
GET /actuator/configprops/app.catalog
GET /actuator/configprops/app
```

Cả hai đều có thể chọn bean mẫu vì tiền tố đăng ký của nó bắt đầu bằng chuỗi được yêu cầu. Bộ lọc dùng tiền tố của **bean**, không phải một phép tìm kiếm nội dung response.

Những yêu cầu sau không mang nghĩa thường bị nhầm:

- `/actuator/configprops/catalog`: không tìm mọi prefix có chứa từ `catalog` ở giữa.
- `/actuator/configprops/app.catalog.connect-timeout`: không chọn một field riêng trong bean `app.catalog`.
- Truyền tên class hay tên bean làm đoạn URL: không phải bộ lọc theo định danh bean.
- Thêm `?prefix=app.catalog`: không thay thế cú pháp đường dẫn selector được mô tả ở trên.

Trong ví dụ Boot 3.3.0, yêu cầu HTTP có prefix không khớp bean nào trả **404**. Điều này khác với gọi báo cáo chung thành công nhưng không thấy bean mong muốn trong nội dung. Khi chẩn đoán 404 ở URL có prefix, hãy thử URL chung `/actuator/configprops` để phân biệt endpoint không truy cập được với bộ lọc không có kết quả.

Trong Boot 3.3.0, điều kiện lọc thực hiện bằng `bean.getAnnotation().prefix().startsWith(prefix)`. Vì vậy một stem rộng có thể lấy thêm các prefix cùng bắt đầu bằng chuỗi đó; nó không phải kiểm tra biên phân đoạn tên và không phải ranh giới phân quyền. [Mã nguồn ConfigurationPropertiesReportEndpoint](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/context/properties/ConfigurationPropertiesReportEndpoint.java).

Nếu quyền truy cập cho phép báo cáo đầy đủ, việc người dùng chọn URL hẹp không ngăn họ yêu cầu URL rộng hơn. Chọn prefix giúp giảm dữ liệu cần đọc; phân quyền phải được thiết kế ở lớp truy cập.

## 6. Hiểu chính sách che giá trị

Trong Spring Boot 3.3, `configprops` mặc định che giá trị. Dùng `management.endpoint.configprops.show-values` để chọn chính sách:

| Giá trị | Chính sách hiển thị |
| --- | --- |
| `never` | Che giá trị cho mọi người gọi |
| `always` | Cho phép hiện giá trị với mọi người đã truy cập được endpoint |
| `when-authorized` | Chỉ hiện với người gọi đủ điều kiện được xem giá trị |

Các `SanitizingFunction` tùy chỉnh vẫn có thể che dữ liệu khi chúng áp dụng. Vì thế `always` không bảo đảm mọi trường đều được hiện nguyên bản. [Chính sách hiển thị và che dữ liệu Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#sanitizing).

Trong ứng dụng có xác thực, một cấu hình chính sách có thể là:

```yaml
management:
  endpoint:
    configprops:
      show-values: when-authorized
      roles: CONFIG_READER
```

Đoạn YAML này chỉ bổ sung chính sách hiển thị. Nó không tạo tài khoản, không cấu hình đăng nhập và không tự bảo vệ URL. Đối với HTTP, việc xem giá trị cần danh tính đã xác thực và vai trò phù hợp với cấu hình; khi không đặt danh sách roles, mặc định người dùng đã xác thực được coi là đủ điều kiện theo chính sách này.

Cần phân biệt:

```text
Có được truy cập /actuator/configprops không?
             ↓
Nếu truy cập được, có được thấy giá trị thật không?
             ↓
Có bộ che dữ liệu tùy chỉnh nào vẫn áp dụng không?
```

`401/403` và `200` với giá trị `******` thuộc các tình huống khác nhau. Không chuyển sang `always` để chữa một lỗi xác thực.

Quyền xem giá trị của HTTP và JMX cũng không nên được suy luận là giống nhau. Khi thiết kế cho nhiều kênh quản trị, cần kiểm tra chính sách của từng kênh thay vì coi cấu hình vai trò HTTP là một lớp bảo vệ chung.

## 7. Quy trình chẩn đoán một bean cấu hình

### Bước 1: Xác minh đúng ứng dụng và đường truy cập

Kiểm tra tiến trình, cổng, base path Actuator và context path thực tế. Ví dụ bài học dùng `127.0.0.1:8080/actuator`; ứng dụng khác có thể dùng cổng quản trị hoặc đường dẫn khác.

Nếu URL chung trả `404`, kiểm tra enablement, exposure và exclusion trước khi sửa lớp cấu hình. Với URL có prefix, 404 còn có thể do không có bean khớp bộ lọc. Nếu trả `401/403`, giải quyết theo chính sách xác thực/phân quyền.

### Bước 2: Tìm đúng bean qua prefix

Bắt đầu bằng prefix đủ hẹp, sau đó duyệt các context và bean phù hợp. Ghi lại tên bean khi có nhiều đối tượng cùng prefix; đừng dừng ở mục khớp đầu tiên rồi mặc nhiên coi đó là đối tượng nghiệp vụ đang sử dụng.

Không thấy bean thì kiểm tra:

- Lớp có `@ConfigurationProperties` đúng prefix không?
- Có đăng ký bằng `@EnableConfigurationProperties`, scan hoặc `@Bean` phù hợp không?
- Profile hoặc điều kiện tạo bean có đang loại nó ra không?
- Có đang đọc nhầm tiến trình, phiên bản triển khai hay context không?

Một đối tượng do mã ứng dụng tự `new` không tự trở thành bean cấu hình của Spring.

### Bước 3: So sánh properties với kiểu Java và mặc định

Đọc tên thuộc tính theo cách nó được biểu diễn trong bean, thường là camelCase. Xem `Duration`, enum, collection hoặc kiểu lồng nhau theo ý nghĩa của chúng.

Nếu thuộc tính thiếu, chưa kết luận nó không tồn tại trong Java: trường `null`, khả năng báo cáo/tuần tự hóa hoặc cấu trúc đặc thù của bean có thể ảnh hưởng đến response. Trong Boot 3.3.0, endpoint lọc các thuộc tính có thể báo cáo, tránh tham chiếu vòng và có thể trả thông tin lỗi khi không tuần tự hóa được bean. Không coi báo cáo là một bản chụp phản chiếu toàn bộ object graph.

### Bước 4: Theo inputs về nguồn

Với giá trị bất ngờ, tìm `inputs` tương ứng. Nếu có origin, kiểm tra đúng tệp/profile, tham số khởi động hoặc nguồn override được nêu.

`inputs` không liệt kê mọi giá trị ứng viên đã bị ghi đè. Khi cần phân tích các nguồn đang tồn tại và quan hệ ưu tiên, dùng `env` cùng log/cấu hình khởi động như công cụ bổ sung, theo quyền đã cấp.

Nếu `inputs` là `{}`, xem lại mặc định trong class/constructor/annotation và khả năng thu thập thông tin nguồn. Không tự gán cho nó ý nghĩa “thuộc tính chưa bao giờ được cấu hình” trong mọi ứng dụng.

### Bước 5: Đối chiếu việc sử dụng bean

Có bean đúng giá trị chỉ chứng minh trạng thái cấu hình được báo cáo. Một HTTP client có thể đã sao chép timeout lúc nó được tạo; sửa cấu hình về sau không chứng minh client đó đã nhận giá trị mới.

Kiểm tra bean nào được inject, có `@Qualifier` hay đối tượng tự tạo không, và thời điểm cấu hình được áp dụng. `configprops` không chứng minh có kết nối thành công tới URL trong cấu hình.

### Bước 6: Sửa nguồn có thẩm quyền rồi quan sát lại

Sửa đúng nguồn đang chi phối giá trị, khởi động lại hoặc dùng cơ chế cập nhật được ứng dụng hỗ trợ. Đọc lại cùng bean và kiểm tra cùng tập bằng chứng.

Một thay đổi trong Environment không bảo đảm mọi `@ConfigurationProperties` bean tự cập nhật. Ứng dụng mẫu dùng binding lúc khởi động và không có tính năng refresh cấu hình động.

## 8. Kiểm thử báo cáo: giá trị, nguồn và cơ chế che

Các kiểm thử sau dùng MockMvc để đọc endpoint trong ngữ cảnh Spring; không mở socket HTTP thật. Chúng kiểm tra cấu trúc JSON theo prefix thay vì gắn cứng mã context hoặc tên bean.

### 8.1. Hàm hỗ trợ đọc một bean trong report

Tệp `src/test/java/example/configprops/ConfigpropsJson.java`:

```java
package example.configprops;

import com.fasterxml.jackson.databind.JsonNode;

final class ConfigpropsJson {

    private ConfigpropsJson() {
    }

    static JsonNode findBean(JsonNode report, String prefix) {
        for (JsonNode context : report.path("contexts")) {
            for (JsonNode bean : context.path("beans")) {
                if (prefix.equals(bean.path("prefix").asText())) {
                    return bean;
                }
            }
        }
        throw new AssertionError("Missing configprops prefix: " + prefix);
    }

}
```

Hàm `findBean` phù hợp mẫu chỉ có một bean với prefix này. Nếu thiết kế có nhiều bean cùng prefix, hãy trả danh sách hoặc chọn thêm context/tên bean đã xác minh.

### 8.2. Kiểm thử chế độ che và bean thật

Tệp `src/test/java/example/configprops/ConfigpropsMaskedTest.java`:

```java
package example.configprops;

import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConfigpropsMaskedTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @Autowired
    private CatalogClientProperties properties;

    @Test
    void masksBothReportedAndInputValues() throws Exception {
        String body = mvc.perform(get("/actuator/configprops/app.catalog"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        var bean = ConfigpropsJson.findBean(
                mapper.readTree(body), "app.catalog");

        assertEquals("******",
                bean.path("properties").path("connectTimeout").asText());
        assertEquals("******",
                bean.path("inputs").path("connectTimeout")
                        .path("value").asText());
    }

    @Test
    void maskingDoesNotModifyTheBoundBean() {
        assertEquals("https://catalog.example.test",
                properties.baseUrl().toString());
        assertEquals(Duration.ofMillis(1500),
                properties.connectTimeout());
        assertEquals(3, properties.maxAttempts());
    }
}
```

Kiểm thử thứ hai tách rõ sự khác biệt giữa hiển thị và dữ liệu thật: giá trị bean vẫn có kiểu và giữ nguyên ngay khi response bị che.

### 8.3. Kiểm thử chuyển kiểu, nguồn override và bộ lọc prefix

Tệp `src/test/java/example/configprops/ConfigpropsVisibleTest.java`:

```java
package example.configprops;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoint.configprops.show-values=always",
        "app.catalog.connect-timeout=750ms"
})
@AutoConfigureMockMvc
class ConfigpropsVisibleTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @Test
    void reportsConvertedValueRecordedInputAndCodeDefault() throws Exception {
        String body = mvc.perform(get("/actuator/configprops/app.catalog"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        var bean = ConfigpropsJson.findBean(
                mapper.readTree(body), "app.catalog");
        var values = bean.path("properties");
        var inputs = bean.path("inputs");

        assertEquals("https://catalog.example.test",
                values.path("baseUrl").asText());
        assertEquals("PT0.75S",
                values.path("connectTimeout").asText());
        assertEquals(3, values.path("maxAttempts").asInt());
        assertEquals("750ms",
                inputs.path("connectTimeout").path("value").asText());
        assertTrue(inputs.path("connectTimeout").path("origin")
                .asText().contains("Inlined Test Properties"));
        assertTrue(inputs.path("maxAttempts").isObject());
        assertEquals(0, inputs.path("maxAttempts").size());
    }

    @Test
    void selectsByPrefixStemRatherThanSubstringOrFieldName()
            throws Exception {
        String broadBody = mvc.perform(get("/actuator/configprops/app"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        ConfigpropsJson.findBean(mapper.readTree(broadBody), "app.catalog");

        for (String prefix : new String[]{
                "catalog", "app.catalog.connect-timeout"}) {
            mvc.perform(get("/actuator/configprops/" + prefix))
                    .andExpect(status().isNotFound());
        }
    }
}
```

`@SpringBootTest(properties=...)` tạo override trong nguồn cấu hình của kiểm thử, không phải tham số dòng lệnh. Do đó origin được kiểm tra là `Inlined Test Properties`, còn thí nghiệm khởi động ở phần trước cho thấy nguồn tham số khởi động. Hai tình huống cùng minh họa việc đầu vào ưu tiên hơn YAML thắng.

Chạy trên PowerShell:

```powershell
.\gradlew.bat test
```

Bộ mẫu có bốn kiểm thử. Báo cáo Gradle nằm ở `build/reports/tests/test/index.html`; log và thời gian thực thi thay đổi theo máy. Các kiểm thử không in cố định JSON ra stdout.

Không coi việc kiểm thử trả HTTP 200 là đủ: các assertion kiểm tra cả giá trị, kiểu biểu diễn, nguồn, mặc định và tập bean được chọn.

## 9. Tình huống dễ đọc sai

| Hiện tượng | Diễn giải cần kiểm tra |
| --- | --- |
| Mọi giá trị đều là `******` | Chính sách che giá trị có thể đang hoạt động bình thường |
| `properties` có số `3`, `inputs` là `{}` | Trong mẫu, giá trị đến từ `@DefaultValue` |
| YAML là `1500ms`, bean báo `PT0.75S` | Tìm nguồn override trong `inputs`, không chỉ sửa YAML |
| Không tìm được tên class trong response | Tìm theo prefix và duyệt các context trước; xác minh cách đăng ký bean |
| `@Value` có giá trị nhưng không thấy bean tương ứng | `configprops` không phải báo cáo mọi field `@Value` |
| Prefix lọc dài hơn không có kết quả | Có thể đã dùng tên field thay vì prefix của bean |
| URL trả 200 nhưng không có bean | Status thành công chỉ chứng minh thao tác đọc đã xử lý được |
| Ứng dụng không khởi động do dữ liệu cấu hình sai | Đọc lỗi binding/validation ở log; endpoint chưa sẵn sàng để chẩn đoán |
| Bean đúng nhưng client vẫn dùng timeout khác | Kiểm tra đối tượng được inject và thời điểm client sao chép cấu hình |
| Báo cáo thiếu field hoặc có lỗi tuần tự hóa | Kiểm tra kiểu dữ liệu, khả năng báo cáo và cấu trúc bean |

Một lỗi chuyển kiểu như `connect-timeout=abc` có thể làm quá trình tạo bean thất bại. Nếu ứng dụng không lên, không thể kỳ vọng `configprops` của chính tiến trình đó vẫn phục vụ đầy đủ để giải thích lỗi.

Ngược lại, một khóa viết sai có thể bị bỏ qua tùy chính sách binding. Chẳng hạn viết thêm `max-attemps` thay vì `max-attempts` có thể khiến bean vẫn giữ mặc định `3`. Trong trường hợp đó, việc đọc cả `properties` lẫn `inputs` giúp phát hiện giả định sai; báo cáo không phải công cụ phát hiện mọi khóa thừa trong mọi tệp.

## 10. Thực hành và tiêu chí hoàn thành

1. Chạy không bật profile chẩn đoán; chứng minh endpoint trả báo cáo có che giá trị nhưng bean vẫn nhận timeout 1,5 giây.
2. Bật profile `diagnostic`; tìm bean bằng prefix và đối chiếu `1500ms` với `PT1.5S`.
3. Thêm override dòng lệnh `750ms`; xác minh `properties`, `inputs.value` và nguồn thay đổi đúng ý nghĩa.
4. Bỏ override rồi thêm `max-attempts: 5` vào YAML; dự đoán `inputs.maxAttempts` thay đổi thế nào trước khi đọc lại.
5. Thử prefix `app`, `catalog` và `app.catalog.connect-timeout`; giải thích tập bean mỗi yêu cầu chọn được.
6. Tạo lỗi chuyển kiểu ở môi trường thực hành, quan sát log khởi động rồi khôi phục giá trị hợp lệ; phân biệt lỗi này với dữ liệu bị che.
7. Khi kết thúc, tắt profile hiển thị giá trị hoặc dừng ứng dụng thực hành. Không lưu response chẩn đoán có thông tin riêng vào mã nguồn, tài liệu công khai hay log dùng chung.

Hoàn thành bài khi có thể đưa ra một kết luận kiểm chứng được: **bean nào được liên kết với prefix nào, đang báo cáo giá trị gì, đầu vào được ghi nhận từ đâu và chính sách hiển thị đã ảnh hưởng thế nào đến dữ liệu nhìn thấy**. Chỉ sau đó mới kết luận cần sửa nguồn cấu hình hay kiểm tra cách ứng dụng sử dụng bean.
