# Phân biệt báo cáo điều kiện tự cấu hình với bằng chứng giá trị thuộc tính thực tế — Spring Boot 3.3

## 1. Vấn đề: điều kiện “matched” không nói toàn bộ câu chuyện cấu hình

Khi ứng dụng Spring Boot khởi động, đôi khi bạn thấy:

```text
Positive matches:
    SomeAutoConfiguration matched
Negative matches:
    OtherAutoConfiguration did not match
```

Hoặc gọi:

```http
GET /actuator/conditions
```

và nhận một báo cáo cho biết những điều kiện tự cấu hình (*auto-configuration conditions*) đã đúng hay sai.

Thông tin này hữu ích để trả lời:

> Tại sao Spring Boot cho phép hoặc không cho phép một phần cấu hình/bean được tạo?

Nhưng nó **không trực tiếp trả lời**:

> Giá trị cuối của `app.payment.timeout` đang là bao nhiêu, được lấy từ file nào, có bị biến môi trường ghi đè không, và đối tượng `@ConfigurationProperties` đã nhận giá trị nào?

Hai câu hỏi khác nhau. Một báo cáo condition có thể ghi một class “matched” vì `@ConditionalOnClass` tìm thấy thư viện, nhưng hoàn toàn không liên quan giá trị `timeout`. Thậm chí khi điều kiện là `@ConditionalOnProperty`, kết quả “matched” chỉ thể hiện **điều kiện đã được đánh giá đạt ở thời điểm đánh giá**, không phải bản dump của mọi nguồn và giá trị cấu hình.

Bài này thuộc nhóm **Chẩn đoán lỗi** của **Spring Boot Externalized Configuration**, dành cho **Spring Boot 3.3.x và Java 17+**.

### Mục tiêu

- Hiểu cấu trúc và ý nghĩa thực tế của **Condition Evaluation Report**.
- Biết khi nào dùng `--debug` và endpoint `/actuator/conditions`.
- Hiểu `positiveMatches`, `negativeMatches`, `unconditionalClasses`.
- Phân biệt `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean` và `@ConditionalOnMissingBean`.
- Biết vì sao `matchIfMissing=true` có thể match mà property không tồn tại.
- Tra cứu giá trị hiệu lực bằng `Environment#getProperty` và nguồn bằng `/actuator/env`.
- Quan sát bean được bind bằng `/actuator/configprops`.
- Đối chiếu một khóa từ `application.yaml`, biến môi trường, Java system properties và CLI.
- Phân biệt snapshot tại startup với biến đổi `Environment` hoặc trạng thái nghiệp vụ về sau.
- Dùng các bài kiểm thử để chứng minh **cả điều kiện lẫn giá trị nguồn**, thay vì suy luận từ log.
- Tránh xuất lộ secret khi bật các endpoint chẩn đoán.

## 2. Bản đồ các công cụ chẩn đoán

| Công cụ | Câu hỏi chính | Không chứng minh trực tiếp |
| --- | --- | --- |
| `--debug` của Spring Boot | Vì sao một số auto-configuration/conditional configuration match hoặc không match lúc startup? | Giá trị cuối của tất cả property, nguồn của từng key |
| `/actuator/conditions` | Các condition nào match/not match trong những context được báo cáo? | Toàn bộ `PropertySource` và thứ tự ưu tiên |
| `ConditionEvaluationReport` | Bằng chứng điều kiện ở mức lập trình cho Spring context | Mọi giá trị đã bind hoặc trạng thái hệ thống ngoài |
| `Environment#getProperty("key")` | Giá trị mà property resolver nhận từ `Environment` tại lúc đọc | Đối tượng `@ConfigurationProperties` có chắc được bind/validate đúng |
| `/actuator/env` | Các `PropertySource`, active profiles và origin khi có | Tất cả bean đã nhận dữ liệu nào |
| `/actuator/env/{name}` | Giá trị hiệu lực, nguồn thắng và các nguồn có giá trị key đó khi endpoint hỗ trợ | Condition đã tạo bean thành công không |
| `/actuator/configprops` | Những bean `@ConfigurationProperties`, cấu trúc đã bind và inputs/origins khi có | Toàn bộ biến runtime được đọc thủ công bằng `@Value`/`System.getenv` |
| `/actuator/beans` | Các bean thực sự có trong context được báo cáo | Lý do đầy đủ của mọi điều kiện hoặc nơi giá trị đến |
| Test bằng `SpringApplication.run` | Hành vi nạp config data và tạo bean khi khởi động thật | Mọi thay đổi sau startup hoặc phụ thuộc production ngoài test |

Quy trình hợp lý thường là:

```text
Triệu chứng:
  tính năng không bật / bean không xuất hiện / timeout sai
                 |
                 v
1. conditions:
   bean/configuration có được phép tạo không?
                 |
                 v
2. env:
   key có giá trị hiệu lực nào, nguồn nào thắng?
                 |
                 v
3. configprops:
   đối tượng cấu hình nhận gì sau binding?
                 |
                 v
4. beans + runtime:
   bean có thật không, hành vi có đáp ứng yêu cầu không?
```

Không phải ứng dụng nào cũng cần bật đủ bốn endpoint. Trong môi trường nhạy cảm, một test cục bộ hoặc cơ chế chẩn đoán hạn chế quyền thường an toàn hơn.

## 3. Condition Evaluation Report là gì?

Trong Spring Boot, nhiều auto-configuration có các điều kiện:

```java
@ConditionalOnClass(...)
@ConditionalOnBean(...)
@ConditionalOnMissingBean(...)
@ConditionalOnProperty(...)
@ConditionalOnWebApplication
```

Chúng giúp Spring quyết định cấu hình nào được áp dụng trong một ứng dụng cụ thể.

Condition Evaluation Report ghi lại những kết quả đánh giá được framework lưu trong quá trình xử lý cấu hình. Ví dụ:

```text
ExampleAutoConfiguration matched:
  - @ConditionalOnClass found required class ...

ExampleJdbcAutoConfiguration did not match:
  - @ConditionalOnBean did not find bean ...
```

Vì là **báo cáo điều kiện**, nó không nhất thiết đề cập giá trị `app.worker.max-retries`, dù property ấy đang tồn tại trong `application.properties`.

Một condition có thể match vì:

- Có đúng một class trên classpath.
- Không có một bean kiểu tương ứng.
- Một bean khác tồn tại.
- Ứng dụng là web application.
- Một property có mặt hoặc thỏa yêu cầu `havingValue`.
- Một resource có mặt.
- Một profile phù hợp.
- Một biểu thức điều kiện tùy chỉnh trả về true.

**Không được gộp mọi điều kiện thành một kiểm tra tên property.**

### 3.1. “Matched” không bằng “có bean thật”

Một configuration class có điều kiện match có thể khai báo các bean với **điều kiện bổ sung ở cấp method**. Một bean vẫn có thể không được tạo, bị custom configuration thay thế, hoặc startup có thể thất bại do nguyên nhân khác.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.ExternalClient")
class ExternalClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

Việc class `ExternalClientAutoConfiguration` match theo `@ConditionalOnClass` không chứng minh method `externalClient()` chắc chắn tạo bean. Nếu một bean tương ứng đã tồn tại, `@ConditionalOnMissingBean` có thể không match.

Muốn biết bean cuối có tồn tại, hãy kiểm tra Spring context hoặc `/actuator/beans`. Nếu muốn biết vì sao nó không được tạo, xem condition ở cấp configuration **và** cấp bean method.

### 3.2. “Did not match” không bằng “thuộc tính không tồn tại”

Một auto-configuration có thể không match vì thiếu class hoặc không có một bean, mặc dù property liên quan đã được khai báo đúng.

Ví dụ ứng dụng viết:

```properties
app.cache.enabled=true
```

nhưng thư viện cache cần thiết không có trên classpath. `@ConditionalOnClass` có thể fail, nên cấu hình cache không được áp dụng. Điều đó không có nghĩa `app.cache.enabled` bị xóa khỏi `Environment`.

Phải tách hai bằng chứng:

```text
condition: thư viện cache không có
environment: app.cache.enabled=true
```

Hai kết quả này cùng đúng và giải thích được triệu chứng.

## 4. `positiveMatches`, `negativeMatches`, `unconditionalClasses`

Endpoint `/actuator/conditions` của Spring Boot 3.3 trả một object `contexts`. Mỗi context có thể có:

- `positiveMatches`: các điều kiện match.
- `negativeMatches`: những configuration/method không đạt đủ điều kiện.
- `unconditionalClasses`: các auto-configuration class không có điều kiện được báo cáo.
- `parentId` nếu context có quan hệ cha/con.

Một JSON rút gọn minh họa:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "ExampleAutoConfiguration#enabledBean": [
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty (app.feature.enabled=true) matched"
          }
        ]
      },
      "negativeMatches": {
        "OtherAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnClassCondition",
              "message": "Did not find a required class"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": [
        "ExampleBaseAutoConfiguration"
      ]
    }
  }
}
```

**Đây là JSON minh họa**, không phải bản chụp từ một ứng dụng cụ thể. Chuỗi message và danh sách class phụ thuộc classpath, các auto-configurations và phiên bản Boot.

### 4.1. Vì sao negative match có hai danh sách?

Một configuration có thể có **nhiều điều kiện**. Nó không được áp dụng nếu có điều kiện cần thiết không đạt, nhưng một số điều kiện khác của chính configuration đó vẫn đã đạt.

Vì vậy `negativeMatches` có thể chứa:

```text
notMatched: những điều kiện không đạt
matched:    những điều kiện đã đạt
```

Nếu bạn chỉ nhìn một dòng “Negative matches”, dễ bỏ qua rằng classpath đã đúng nhưng một bean hoặc property bổ sung còn thiếu.

### 4.2. Nhiều application contexts

Một ứng dụng có thể có management context tách khỏi application context hoặc cấu trúc parent-child. Endpoint có trường `contexts`, không phải một tập điều kiện toàn cục duy nhất.

Khi điều tra endpoint hoặc bean ở context quản trị, phải xem **đúng context ID**. Không nên gắn kết luận của context `application` lên một context khác.

### 4.3. Unconditional không có nghĩa “đã thực hiện đúng nghiệp vụ”

Một class nằm trong `unconditionalClasses` nghĩa là được báo cáo như class không có điều kiện theo cấu trúc endpoint, **không phải** đảm bảo bean nào đó hoạt động đúng hay API bên ngoài đã sẵn sàng.

## 5. Cách lấy báo cáo điều kiện bằng `--debug`

Trong một ứng dụng Spring Boot chạy JAR:

```bash
java -jar app.jar --debug
```

Spring Boot có thể in **Conditions Evaluation Report** vào startup logs.

Với Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Với Gradle `bootRun`:

```bash
./gradlew bootRun --args='--debug'
```

Trên PowerShell, biến thể Gradle:

```powershell
.\gradlew.bat bootRun '--args=--debug'
```

Điểm quan trọng là `--debug` **được chuyển đến Spring Boot application**, không phải lệnh:

```bash
./gradlew bootRun --debug
```

vốn bật logging ở phía Gradle. Hai lệnh không tương đương.

### 5.1. Thời điểm phát báo cáo

Spring Boot ghi báo cáo trong các tình huống startup liên quan; khi debug được bật, nó cung cấp thông tin về auto-configuration condition evaluation. Báo cáo phản ánh những điều kiện đã được đánh giá, không phải bản ghi liên tục cập nhật theo từng request.

Nếu một cấu hình lỗi trước khi đến giai đoạn điều kiện liên quan được đánh giá, log có thể không chứa mọi thông tin mà bạn mong đợi.

### 5.2. Phân biệt log debug với source of truth

Một đoạn log:

```text
FeatureAutoConfiguration matched:
  - @ConditionalOnProperty (app.feature.enabled) matched
```

là bằng chứng condition đạt vào lúc framework xử lý nó. Nhưng để chứng minh `app.feature.enabled` cuối cùng có giá trị `true` trong `Environment` đang chạy, phải đọc property từ đúng process/context.

Nếu property thay đổi sau khi condition được đánh giá, báo cáo đã ghi không tự được tính lại để phản ánh một ứng dụng đã được thay đổi động.

### 5.3. Debug report có thể rất dài

Một ứng dụng có nhiều starter tạo ra hàng trăm điều kiện. Thay vì đọc mọi class:

1. Tìm tên auto-configuration liên quan.
2. Xem condition nào fail hoặc match.
3. Xác định tên property nếu condition dùng property.
4. Đối chiếu property với nguồn dữ liệu thật.
5. Kiểm tra bean cuối.

Không nên sửa một file YAML chỉ vì một condition không liên quan xuất hiện ở phần “Negative matches”.

## 6. `@ConditionalOnProperty`: cùng một annotation có nhiều ý nghĩa

Spring Boot 3.3 có:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
```

Một ví dụ:

```java
@ConditionalOnProperty(
    prefix = "app.notify",
    name = "enabled",
    havingValue = "true"
)
```

Điều kiện này kiểm tra property hiệu lực `app.notify.enabled` theo quy tắc của annotation.

Nhưng nếu bỏ `havingValue`:

```java
@ConditionalOnProperty(
    prefix = "app.notify",
    name = "enabled"
)
```

thì **không phải chỉ giá trị `true` mới match**. Theo JavaDoc, mặc định property phải tồn tại và giá trị **không bằng `"false"`**.

### 6.1. Bảng kết quả cơ bản

| Giá trị property có mặt | `havingValue=""` (mặc định) | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | --- | --- | --- | --- |
| `"true"` | match | match | không | không |
| `"false"` | không | không | match | không |
| `"foo"` | match | không | không | match |

Ví dụ:

```properties
app.notify.enabled=maybe
```

Với annotation mặc định không có `havingValue`, điều kiện có thể **match** dù `maybe` không phải boolean hợp lệ cho một field `boolean`.

Khi ý định chính xác là bật theo boolean, khai báo:

```java
havingValue = "true"
```

và cân nhắc binding/validation kiểu Boolean ở cấu hình chính thức.

### 6.2. `matchIfMissing`

Mặc định:

```java
matchIfMissing = false
```

nghĩa là property không tồn tại thì condition không match.

Nhưng:

```java
@ConditionalOnProperty(
    prefix = "app.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

có thể match **khi `app.notify.enabled` hoàn toàn vắng mặt**.

Vì vậy, một condition report ghi “matched” không phải bằng chứng property tồn tại trong `Environment`, càng không phải bằng chứng property đến từ `application.yaml`.

Bảng logic:

| Property `app.notify.enabled` | Annotation có `havingValue="true"`, `matchIfMissing=false` | Với `matchIfMissing=true` |
| --- | --- | --- |
| `"true"` | match | match |
| `"false"` | không match | không match |
| Vắng mặt | không match | match |

### 6.3. Điều kiện không tự kiểm tra mọi collection

JavaDoc `@ConditionalOnProperty` của Spring Boot 3.3 lưu ý rằng nó không đáng tin cậy để kiểm tra sự hiện diện của những property ở dạng collection.

Ví dụ:

```properties
app.notify.channels[0]=email
```

không bảo đảm rằng condition kiểm tra:

```java
@ConditionalOnProperty(name = "app.notify.channels")
```

sẽ match. Một key phần tử và một key cha của collection không phải lúc nào cũng được property resolver coi là cùng một giá trị scalar.

Với logic phụ thuộc collection, hãy dùng loại condition hoặc cách xác nhận khác phù hợp với dữ liệu được bind, không cố dùng một condition scalar rồi kết luận danh sách có phần tử.

## 7. Phân biệt `@ConditionalOnProperty` với `@ConfigurationProperties`

Hai annotation dễ gây nhầm vì đều có từ “property”.

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true")
```

trả lời câu hỏi:

> Có nên bật cấu hình hoặc tạo bean có điều kiện này không?

Trong khi:

```java
@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout
) {}
```

trả lời câu hỏi:

> Các giá trị thuộc nhóm `app.notify.*` được chuyển và đưa vào Java object ra sao?

Điểm khác biệt:

| `@ConditionalOnProperty` | `@ConfigurationProperties` |
| --- | --- |
| Dùng trong quyết định điều kiện | Dùng để liên kết cấu hình có kiểu |
| Có `havingValue`, `matchIfMissing` | Có quy tắc type conversion, nested binding |
| Báo cáo qua conditions | Có thể quan sát qua configprops |
| Không phải bằng chứng bean có mọi field hợp lệ | Không tự bảo đảm một auto-configuration match |
| Kiểm tra tại giai đoạn condition evaluation | Thường bind khi tạo/khởi tạo bean |
| Có thể match khi key thiếu | Có thể có default/validation làm giá trị Java khác raw source |

Nếu một bean phụ thuộc cả hai:

```text
Condition -> quyết định bean có tham gia không
Binder    -> liên kết các field của bean cấu hình
Validation -> kiểm tra constraint của field
```

Ba bước có quan hệ nhưng không đồng nhất.

## 8. Nguồn của giá trị: `Environment` và precedence

Khi muốn biết property được dùng có giá trị nào, cách trực tiếp là:

```java
environment.getProperty("app.notify.enabled")
```

`Environment` truy cập các `PropertySource` của context. Trong cấu hình Spring Boot 3.3 thông thường, các nguồn phổ biến theo thứ tự ưu tiên rút gọn từ cao xuống thấp là:

```text
Spring Boot command-line properties
              |
              v
Java system properties của JVM ứng dụng
              |
              v
OS environment variables
              |
              v
Config Data (application.properties/YAML, import...)
              |
              v
Default properties
```

Spring Boot còn có test property sources, devtools, `SPRING_APPLICATION_JSON`, servlet/JNDI parameters và các nguồn tự viết. **Sơ đồ này không phải thứ tự đầy đủ** cho mọi deployment.

### 8.1. Ví dụ cùng một property xuất hiện ba lần

`application.properties`:

```properties
app.notify.enabled=false
```

Java launcher:

```bash
java -Dapp.notify.enabled=false -jar app.jar \
  --app.notify.enabled=true
```

Với cấu hình command-line properties mặc định, giá trị Spring Environment nhìn thấy có thể là:

```text
true
```

dù file và Java system property đều là `false`.

Báo cáo condition có thể nói:

```text
@ConditionalOnProperty (app.notify.enabled=true) matched
```

Nhưng **báo cáo đó không cho bạn biết chính CLI là nguồn thắng**. Để biết, kiểm tra `Environment`/`/actuator/env`.

### 8.2. `System.getProperty` khác `Environment#getProperty`

Trong ví dụ trên:

```java
System.getProperty("app.notify.enabled")
```

trả:

```text
false
```

nhưng:

```java
environment.getProperty("app.notify.enabled")
```

có thể trả:

```text
true
```

Hai kết quả không mâu thuẫn. API Java chỉ xem JVM system properties, còn Spring Environment xét tất cả nguồn theo precedence.

Tương tự, `System.getenv("APP_NOTIFY_ENABLED")` chỉ đọc biến môi trường OS, không thể thay thế `Environment#getProperty`.

### 8.3. Canonical name và relaxed binding

Với `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(boolean enabled) {}
```

biến môi trường thông thường:

```text
APP_NOTIFY_ENABLED=true
```

có thể được Binder nhận cho `app.notify.enabled`.

Với tên dạng:

```text
app.notify.retry-count
```

quy tắc đặt tên biến môi trường canonical là:

```text
APP_NOTIFY_RETRYCOUNT
```

thay dấu chấm bằng `_`, bỏ dấu gạch nối và đổi sang chữ hoa.

Cần phân biệt `Environment#getProperty("some.key")` với Binder của `@ConfigurationProperties`, vì mức linh hoạt tìm tên key không hoàn toàn trùng nhau với mọi API và mọi biến thể tên.

## 9. `/actuator/conditions` cho biết điều gì?

Khi ứng dụng có Spring Boot Actuator và endpoint được expose hợp lệ, có thể gọi:

```bash
curl http://localhost:8080/actuator/conditions
```

Endpoint có các cấu trúc:

```text
contexts
  |
  +-- application
        |
        +-- positiveMatches
        +-- negativeMatches
        +-- unconditionalClasses
```

Ví dụ một matched condition:

```json
{
  "condition": "OnPropertyCondition",
  "message": "@ConditionalOnProperty (app.notify.enabled=true) matched"
}
```

Các chuỗi trong báo cáo là **mô tả lý do đánh giá**. Không nên parse chúng như một giao thức bất biến để trích giá trị thực tế. Format thông điệp có thể đổi theo phiên bản hoặc implementation condition.

### Khi nào dùng?

- Một starter đáng lẽ phải tự cấu hình nhưng không chạy.
- Bean mà Boot dự kiến tạo không xuất hiện.
- Auto-configuration không kích hoạt do thiếu class/bean/property.
- Cần kiểm tra nguyên nhân `@ConditionalOnMissingBean` back off.
- Một property `enabled` dường như không tác động đến bean.

### Khi nào chưa đủ?

- Cần biết giá trị có hiệu lực của `app.notify.timeout`.
- Cần chứng minh property đến từ CLI hay profile YAML.
- Cần xem bean `@ConfigurationProperties` đã bind timeout thành bao nhiêu giây.
- Cần xác minh endpoint ngoài thực sự nhận request.
- Cần biết một refresh runtime đã cập nhật object hay chưa.

Đối với các câu hỏi này, chuyển sang `Environment`, `/actuator/env`, `/actuator/configprops`, kiểm tra bean thực và test vận hành.

## 10. `/actuator/env` là bằng chứng về nguồn cấu hình

Spring Boot Actuator có endpoint:

```http
GET /actuator/env
```

Nó mô tả `ConfigurableEnvironment`, active/default profiles, những PropertySources và các giá trị/origin khi endpoint cung cấp và quyền truy cập cho phép.

Một request hẹp hơn:

```http
GET /actuator/env/app.notify.enabled
```

có thể trả thông tin về **một property cụ thể**, thay vì dump nhiều thuộc tính.

Response minh họa rút gọn:

```json
{
  "activeProfiles": ["qa"],
  "property": {
    "source": "commandLineArgs",
    "value": "true"
  },
  "propertySources": [
    {
      "name": "commandLineArgs",
      "property": {
        "value": "true"
      }
    },
    {
      "name": "systemProperties",
      "property": {
        "value": "false"
      }
    }
  ]
}
```

Ví dụ trên chỉ mô tả cấu trúc có thể có, **không phải JSON nguyên văn từ một instance cụ thể**. Spring Boot 3.3 có cơ chế sanitization, nên `value` nhiều khi được hiển thị như `******` thay vì `true`/`false`.

### 10.1. `property.source` và `origin`

Endpoint `/actuator/env/{property.name}` có thể cho biết:

- Nguồn có giá trị được chọn.
- Danh sách các nguồn có/không có property.
- Origin nếu `PropertySource` chứa thông tin origin.

Một origin minh họa:

```text
class path resource [application.yaml] - 5:18
```

Nó giúp điều tra **vị trí trong file** của một khóa đã được nạp qua Config Data.

Nhưng không phải mọi PropertySource đều có thông tin dòng/cột. CLI, system properties, biến môi trường và nguồn tự tạo có thể có cách mô tả khác hoặc không có origin chi tiết. Không nên khẳng định endpoint luôn chỉ ra được tên file và số dòng cho mọi nguồn.

### 10.2. `property.value` có thể bị che

Theo Spring Boot 3.3, các endpoint như `/env` và `/configprops` **sanitization mặc định** để hạn chế lộ dữ liệu cấu hình.

Nếu JSON ghi:

```json
{
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  }
}
```

thì `******` **không nhất thiết là giá trị thực của ứng dụng**. Nó có thể chỉ là giá trị đã được che ở tầng management endpoint.

Không sửa cấu hình ứng dụng thành `******` chỉ vì nhìn response đó.

### 10.3. Source thắng không phải mọi chặng biến đổi

Giả sử property được khai báo:

```properties
app.notify.timeout=${APP_TIMEOUT:5s}
```

Một `Environment` có thể giải quyết placeholder rồi trả `Duration` hoặc String theo API gọi. Origin có thể trỏ tới file khai báo placeholder, trong khi giá trị được placeholder tham chiếu lại đến từ biến môi trường.

Khi có placeholder, import, config tree hoặc custom PropertySource, cần phân biệt:

1. Nơi khai báo key.
2. Nguồn của các biến được tham chiếu trong value.
3. Giá trị sau resolve/convert.
4. Đối tượng Java nhận được sau Binder.

Một source name đơn lẻ chưa mô tả toàn bộ chuỗi phụ thuộc này.

## 11. `/actuator/configprops` chứng minh điều gì?

Endpoint:

```http
GET /actuator/configprops
```

mô tả các bean được đánh dấu `@ConfigurationProperties`. Nó có thể thể hiện:

- Prefix cấu hình.
- Bean và class tương ứng.
- Những thuộc tính đã bind.
- Những input binding và origin khi có.
- Giá trị đã được sanitize theo chính sách management.

Một response rút gọn mang tính minh họa:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "app.notify-example.NotifyProperties": {
          "prefix": "app.notify",
          "properties": {
            "enabled": true,
            "timeout": "PT5S"
          },
          "inputs": {
            "enabled": {
              "value": "true",
              "origin": "command line"
            }
          }
        }
      }
    }
  }
}
```

Tên bean, format hiển thị `Duration` và cấu trúc chi tiết có thể khác tùy Boot version và application. Đừng dùng ví dụ trên làm hợp đồng JSON chính xác.

### 11.1. Vì sao `configprops` khác `env`?

`/actuator/env` nhìn vào **nguồn và phép resolve property**.

`/actuator/configprops` nhìn vào **đối tượng cấu hình đã được Spring Boot liên kết**.

Nếu bean có:

```java
@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout
) {}
```

và Environment có:

```properties
app.notify.timeout=5s
```

thì bean có thể nhận:

```java
Duration.ofSeconds(5)
```

Tầng `env` là chuỗi/nguồn, tầng `configprops` thể hiện dữ liệu có kiểu sau binding.

### 11.2. `configprops` không bao quát mọi nơi đọc cấu hình

Code dùng:

```java
@Value("${app.notify.timeout}")
private String timeout;
```

hoặc:

```java
System.getenv("APP_NOTIFY_TIMEOUT")
```

không nhất thiết tạo một `@ConfigurationProperties` bean xuất hiện trong `configprops`.

Không thể kết luận “property không được dùng” chỉ vì không thấy nó trong `/actuator/configprops`.

### 11.3. Default trong Java có thể không xuất hiện ở `Environment`

Ví dụ:

```java
@ConfigurationProperties(prefix = "app.notify")
public class NotifyProperties {

    private Duration timeout = Duration.ofSeconds(5);

    // getters/setters...
}
```

Nếu không có key `app.notify.timeout` ở bất cứ PropertySource nào, bean vẫn có thể có timeout mặc định `5s` từ Java.

Khi đó:

```java
environment.getProperty("app.notify.timeout")
```

có thể là `null`, trong khi:

```java
notifyProperties.getTimeout()
```

bằng năm giây.

Đây không phải lỗi. Đó là khác biệt giữa **giá trị có trong Environment** và **giá trị hiệu lực của đối tượng cấu hình đã khởi tạo**.

## 12. Một ví dụ xuyên suốt: property `app.notify.enabled`

Xây dựng một ứng dụng nhỏ với:

```text
app.notify.enabled
app.notify.timeout
app.notify.endpoint
```

Ta muốn:

- Chỉ tạo `NotificationSender` khi `app.notify.enabled=true`.
- Liên kết cấu hình kiểu Java qua `@ConfigurationProperties`.
- In giá trị đang thấy từ `Environment`.
- Quan sát bean thực sự tồn tại.
- So sánh ba nguồn bằng chứng với condition report.

### 12.1. File `application.properties`

`src/main/resources/application.properties`:

```properties
spring.application.name=condition-evidence-demo

app.notify.enabled=false
app.notify.timeout=5s
app.notify.endpoint=https://notify.example.test/api
```

Đây là file khởi đầu. Domain `.example.test` chỉ để minh họa, không phải API thật cần gọi.

### 12.2. Model `@ConfigurationProperties`

`src/main/java/example/evidence/NotifyProperties.java`:

```java
package example.evidence;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout,
        URI endpoint
) {
}
```

Spring Boot Binder có hỗ trợ conversion thông dụng cho `Duration` và `URI`.

### 12.3. Bean nghiệp vụ có điều kiện

`src/main/java/example/evidence/NotificationSender.java`:

```java
package example.evidence;

public class NotificationSender {

    public String status() {
        return "sender-created";
    }
}
```

Lớp cấu hình:

`src/main/java/example/evidence/NotificationConfiguration.java`:

```java
package example.evidence;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notify",
            name = "enabled",
            havingValue = "true"
    )
    NotificationSender notificationSender() {
        return new NotificationSender();
    }
}
```

`NotificationSender` ở đây là class Java đơn giản; phương thức `status()` không gọi network.

**Nếu condition không match**, Spring Boot không khai báo bean bằng phương thức `notificationSender()` đó. Nhưng vẫn có thể tồn tại một bean `NotificationSender` từ một cấu hình độc lập khác; vì vậy để kết luận bean thật, phải xem context.

### 12.4. Ứng dụng in bằng chứng

`src/main/java/example/evidence/EvidenceApplication.java`:

```java
package example.evidence;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(NotifyProperties.class)
public class EvidenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(EvidenceApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(
            Environment environment,
            NotifyProperties properties,
            ApplicationContext context
    ) {
        return args -> {
            System.out.println(
                    "env enabled="
                    + environment.getProperty("app.notify.enabled"));

            System.out.println(
                    "bound enabled=" + properties.enabled());

            System.out.println(
                    "bound timeout=" + properties.timeout());

            System.out.println(
                    "sender exists="
                    + !context.getBeansOfType(
                            NotificationSender.class).isEmpty());
        };
    }
}
```

Ở đây:

- `Environment` cho biết giá trị property tại lúc runner chạy.
- `NotifyProperties` cho biết đối tượng có kiểu đã được bind.
- `ApplicationContext` kiểm tra bean có tồn tại.
- `Condition Evaluation Report` giải thích điều kiện của `notificationSender()` được đánh giá thế nào.

Bốn dữ liệu này có liên quan nhưng khác nhau.

## 13. Chạy tình huống A: file đặt `enabled=false`

Giữ cấu hình:

```properties
app.notify.enabled=false
app.notify.timeout=5s
```

Chạy:

```bash
./mvnw spring-boot:run
```

Trong trường hợp không có nguồn ưu tiên hơn:

```text
env enabled=false
bound enabled=false
bound timeout=PT5S
sender exists=false
```

Ở đây:

- `enabled=false` là giá trị hiệu lực của Environment.
- `NotifyProperties.enabled()` bind thành `false`.
- Điều kiện `havingValue="true"` không match.
- Bean method có điều kiện không tạo `NotificationSender`.

Nếu bật `--debug`, báo cáo điều kiện có thể cho biết `OnPropertyCondition` của method đó không match.

**Điều kiện không match không có nghĩa ứng dụng thất bại.** Nó có thể là trạng thái mong muốn của một tính năng được tắt.

## 14. Chạy tình huống B: CLI ghi đè thành `enabled=true`

Giữ file `application.properties` vẫn là:

```properties
app.notify.enabled=false
```

Nhưng chạy:

```bash
java -jar app.jar --app.notify.enabled=true --debug
```

Thay `app.jar` bằng executable JAR của dự án.

Với Spring Boot mặc định thêm command-line properties:

```text
env enabled=true
bound enabled=true
sender exists=true
```

Condition report có thể ghi `OnPropertyCondition` match.

**Kết luận chính xác là:** property hiệu lực tại giai đoạn đánh giá condition thỏa `havingValue=true` và bean được tạo theo cấu hình demo.

**Không thể kết luận chỉ từ conditions rằng file `application.properties` đã được sửa thành true.** File có thể vẫn chứa false; CLI là nguồn ưu tiên cao hơn.

### 14.1. Vấn đề khi chỉ nhìn file

Một kỹ sư mở:

```properties
app.notify.enabled=false
```

rồi kết luận:

> Không thể có NotificationSender vì file đã tắt.

Kết luận sai nếu container nhận:

```text
APP_NOTIFY_ENABLED=true
```

hoặc câu lệnh Java nhận:

```text
--app.notify.enabled=true
```

Cần quan sát **đúng process đang chạy** và **giá trị sau precedence**, không chỉ file nguồn trên repository.

### 14.2. Vấn đề khi chỉ nhìn condition

Kỹ sư khác thấy:

```text
OnPropertyCondition matched
```

rồi kết luận:

> Người triển khai đã bật `enabled=true` trong YAML chính.

Cũng chưa có bằng chứng. Condition không chỉ rõ nguồn thắng. Cần `Environment`, origin và các `PropertySource`.

## 15. Chạy tình huống C: Java system property và CLI xung đột

Lệnh:

```bash
java -Dapp.notify.enabled=false \
  -jar app.jar \
  --app.notify.enabled=true
```

Trong ứng dụng:

```java
System.getProperty("app.notify.enabled")
```

trả `false`, nhưng:

```java
environment.getProperty("app.notify.enabled")
```

có thể trả `true`.

Vì command-line property có ưu tiên cao hơn Java system property trong cấu hình Boot thông thường, điều kiện `havingValue=true` có thể match.

Bảng:

| Bằng chứng | Giá trị kỳ vọng |
| --- | --- |
| File config | `false` |
| Java system property | `false` |
| Spring Environment | `true` |
| Bean `NotifyProperties.enabled()` | `true` |
| Condition cho `NotificationSender` | Match |
| `NotificationSender` | Có bean trong demo |

Đây là lý do **không nên dùng `System.getProperty` làm đại diện cho toàn bộ cấu hình Spring**.

## 16. Chạy tình huống D: thiếu property nhưng condition match

Đổi annotation trong một thử nghiệm độc lập:

```java
@Bean
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
NotificationSender notificationSender() {
    return new NotificationSender();
}
```

Loại bỏ `app.notify.enabled` khỏi tất cả nguồn cấu hình.

Trong điều kiện không có nguồn khác:

```java
environment.getProperty("app.notify.enabled")
```

trả `null`.

`NotifyProperties.enabled()` là primitive `boolean`, có thể bind thành giá trị mặc định `false` nếu property vắng mặt.

Nhưng condition **có thể vẫn match** vì `matchIfMissing=true`. Khi đó:

```text
Environment key hiện diện?      Không
Bound boolean enabled?          false
Condition matched?              Có
NotificationSender được tạo?    Có, theo bean method trong demo
```

Đây là ví dụ điển hình chứng minh:

> Một điều kiện match không phải là bằng chứng property thực sự được khai báo hoặc bean cấu hình có giá trị `true`.

Nếu việc bật tính năng phải phù hợp với giá trị của model, cần thiết kế thống nhất default và `matchIfMissing`. Không nên đặt mặc định condition là true trong khi Java model mặc định false nếu nghiệp vụ không chấp nhận sự lệch nhau.

## 17. Chạy tình huống E: condition match vì một class tồn tại

Một cấu hình:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.SomeClient")
public class SomeClientConfiguration {
    // ...
}
```

Nếu class được tìm thấy, báo cáo ghi positive match cho `OnClassCondition`.

Nhưng điều này không liên quan trực tiếp đến:

```properties
app.some-client.connect-timeout=3s
```

Bạn không thể từ `OnClassCondition matched` mà suy ra:

- `connect-timeout` đã khai báo.
- Nó có giá trị `3s`.
- Giá trị đến từ YAML.
- Kết nối đến dịch vụ ngoài đã thành công.
- Bean client có cấu hình timeout chính xác.
- Hệ thống đạt mục tiêu latency.

Mỗi câu hỏi yêu cầu bằng chứng tương ứng: env, configprops, bean inspection, metric hoặc integration test.

## 18. Chạy tình huống F: `@ConditionalOnMissingBean` “matched”

Một message:

```text
@ConditionalOnMissingBean (...) did not find any beans
```

có thể là **positive match**. Nghĩa là điều kiện “không có bean tương ứng” đã đạt, nên auto-configuration có thể tạo default bean.

Người đọc dễ nhầm chữ “did not find any beans” thành toàn bộ auto-configuration không hoạt động. Phải nhìn **điều kiện đang yêu cầu gì**:

```text
OnMissingBean condition:
  không có bean -> matched
  có bean       -> not matched
```

Ngược lại:

```text
@ConditionalOnBean did not find ...
```

có thể là negative match.

Cả hai message đều có từ “bean”, nhưng dấu nghĩa khác nhau.

### So sánh

| Điều kiện | Có bean mục tiêu | Kết quả có thể |
| --- | --- | --- |
| `@ConditionalOnBean` | Có | Match |
| `@ConditionalOnBean` | Không | Không match |
| `@ConditionalOnMissingBean` | Có | Không match |
| `@ConditionalOnMissingBean` | Không | Match |

Muốn biết bean nào thực sự có sau startup, dùng context hoặc `/actuator/beans`, không suy luận từ một dòng message trơ trọi.

## 19. Bật Actuator để quan sát ba lớp bằng chứng

Nếu muốn thử các endpoint qua HTTP, thêm dependency:

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Trong project dùng dependency management Spring Boot 3.3.x, phiên bản của hai starter thường do Boot quản lý.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

**Có Actuator starter không có nghĩa các endpoint chẩn đoán đều tự mở qua HTTP.** Spring Boot 3.3 mặc định chủ yếu chỉ expose `health` trên HTTP; các endpoint khác cần cấu hình exposure, availability và bảo mật phù hợp.

### 19.1. Chỉ bật trong môi trường phát triển cô lập

Ví dụ `application-local.properties`:

```properties
management.endpoints.web.exposure.include=health,conditions,env,configprops,beans
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Chạy cục bộ với profile `local`:

```bash
java -jar app.jar --spring.profiles.active=local
```

Rồi truy cập, nếu endpoint được expose và user có quyền:

```bash
curl http://localhost:8080/actuator/conditions
curl http://localhost:8080/actuator/env/app.notify.enabled
curl http://localhost:8080/actuator/configprops
curl http://localhost:8080/actuator/beans
```

Không bật `management.endpoints.web.exposure.include=*` trên một môi trường công khai chỉ vì muốn debug nhanh. Cần giới hạn mạng, định nghĩa truy cập bằng security, và kiểm tra cấu hình management port nếu ứng dụng dùng port riêng.

### 19.2. Endpoint bật nhưng 404 hoặc 401/403

Phân biệt:

- **404:** endpoint có thể không available, không được expose, base path/port khác, hoặc app chưa có dependency phù hợp.
- **401/403:** endpoint có thể được bảo vệ bởi security, thiếu xác thực/quyền.
- **200 với values bị che:** sanitization đang hoạt động, không phải dữ liệu cấu hình bị mất.
- **Không kết nối:** server chưa lên, management port khác hoặc firewall chặn.

Đừng “sửa” bằng cách mở tất cả endpoint vô điều kiện ở production. Kiểm tra từng lớp: dependency → enablement → exposure → routing → authentication/authorization.

## 20. Sanitization: vì sao `******` không phải giá trị thật

Dữ liệu môi trường có thể chứa:

```properties
spring.datasource.password=...
app.payment.api-token=...
```

Các endpoint `/env`, `/configprops` có thể làm lộ thông tin này nếu cấu hình quá rộng.

Trong Spring Boot 3.3, mặc định giá trị trên các endpoint nhạy cảm được sanitize. Thuộc tính quản lý giá trị có dạng:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Các lựa chọn được tài liệu hóa:

| Giá trị | Ý nghĩa |
| --- | --- |
| `never` | Luôn che giá trị |
| `when-authorized` | Cho user được cấp quyền xem giá trị nếu không bị custom sanitization áp dụng |
| `always` | Hiển thị giá trị cho mọi người truy cập được endpoint, nếu không có sanitization khác |

**Không khuyến nghị bật `always` ở production.** `when-authorized` cũng cần xác thực/quyền phù hợp và phải đánh giá rủi ro dữ liệu.

Ví dụ phân quyền có thể dùng:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=ENDPOINT_ADMIN
```

Nhưng chỉ đặt hai dòng này **không tự thiết lập toàn bộ Spring Security policy**. Còn phải bảo đảm endpoint được bảo vệ, user có role phù hợp, và cấu hình `SecurityFilterChain` không vô tình cho phép truy cập công khai.

Một `SanitizingFunction` tùy chỉnh vẫn có thể che dữ liệu ngay cả khi `show-values` khác `never`.

### Cách làm khi cần chứng minh một giá trị không nhạy cảm

Trong môi trường test/cục bộ, có thể assert một key được chọn:

```java
String mode = environment.getProperty("app.notify.enabled");
assertThat(mode).isEqualTo("true");
```

Thay vì mở endpoint không sanitize toàn bộ secrets.

Không gửi response `/actuator/env` chưa sanitize vào ticket công khai, chat nhóm không an toàn hoặc artifact CI được chia sẻ rộng.

## 21. Đối chiếu ba endpoint trong một tình huống

Giả sử:

`application.properties`:

```properties
app.notify.enabled=false
app.notify.timeout=5s
```

Runtime truyền:

```bash
java -jar app.jar \
  --app.notify.enabled=true \
  --app.notify.timeout=250ms
```

Khi startup thành công, ta có thể thu thập:

### A — conditions

```text
OnPropertyCondition của NotificationConfiguration#notificationSender:
  matched
```

Điều này giải thích vì sao bean method có thể được áp dụng.

### B — env

```text
app.notify.enabled = true
app.notify.timeout = 250ms
```

Với nguồn như `commandLineArgs` nếu command line là nguồn thắng.

Điều này chứng minh giá trị hiệu lực và có thể kèm nguồn/origin, tùy endpoint và sanitization.

### C — configprops

```text
NotifyProperties.enabled = true
NotifyProperties.timeout = PT0.25S
```

Điều này chứng minh model Java đã bind giá trị như kỳ vọng trong trường hợp cụ thể.

### D — beans

```text
notificationSender bean tồn tại
```

Điều này xác nhận bean thật có trong context.

### E — kiểm thử hành vi

Một method `status()` trả kết quả, hoặc integration test kiểm chứng gửi dữ liệu ở tầng phù hợp. Điều này chứng minh chức năng, không chỉ cấu hình.

**Không nên lấy A để thay B+C+D+E.** Mỗi thành phần chứng minh một phần của chuỗi xử lý.

## 22. Điều kiện được đánh giá lúc nào?

Condition thường được đánh giá trong giai đoạn Spring đang xử lý các configuration classes và bean definitions khi startup.

Vì vậy nếu:

1. Condition đã match ở startup vì `app.notify.enabled=true`.
2. Ứng dụng đã tạo bean.
3. Sau đó một thành phần sửa Environment thành `app.notify.enabled=false`.

thì **không mặc định** Spring sẽ xóa bean hoặc tính lại tất cả conditions.

Tương tự, một bean `@ConfigurationProperties` đã được bind không tự được refresh khi Environment thay đổi, trừ khi có cơ chế cập nhật/rebinding được cấu hình đúng từ một thư viện hoặc application logic cụ thể.

Ví dụ tình huống thời gian:

```text
T0: Env enabled=true
T1: OnPropertyCondition matched
T2: NotificationSender bean được tạo
T3: Env bị thay bằng enabled=false
T4: Condition report vẫn ghi outcome tại T1
T5: Bean có thể vẫn tồn tại
```

`/actuator/env` ở T4 có thể cho bạn một giá trị khác với điều kiện đã ghi lúc T1. **Đó không nhất thiết là lỗi report**; hai công cụ đang phản ánh những trạng thái/thời điểm khác nhau.

Khi dùng Spring Cloud refresh, config reload, `EnvironmentChangeEvent`, dynamic property source hoặc bean refresh tự thiết kế, phải kiểm tra rõ phần nào được cập nhật và phần nào không. Không mặc định Spring Boot core tự cấu hình lại toàn bộ ứng dụng theo thời gian thực.

## 23. Một ví dụ sai lệch khác: default trong code

Class:

```java
@ConfigurationProperties(prefix = "app.notify")
public class NotifyProperties {

    private boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Không có `app.notify.enabled` trong Environment.

Bean có thể nhận:

```text
NotifyProperties.enabled = true
```

vì field initializer.

Nhưng:

```java
environment.getProperty("app.notify.enabled")
```

vẫn có thể là `null`.

Nếu bean method dùng:

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true")
```

với `matchIfMissing=false`, condition không match.

Kết quả:

```text
Bound bean default enabled=true
Environment key absent
Conditional bean not created
```

Ba kết quả khác nhau nhưng hợp lý.

**Quy tắc thiết kế:** Nếu một feature được bật mặc định, hãy quyết định rõ default ở đâu và condition dùng `matchIfMissing` thế nào. Không nên để model và bean activation có hai default trái nhau một cách vô thức.

## 24. Nhiều nguồn ghi cùng một khóa: cần bằng chứng precedence

Giả sử có:

`application.yaml`:

```yaml
app:
  notify:
    enabled: false
    timeout: 5s
```

`application-prod.yaml`:

```yaml
app:
  notify:
    enabled: true
    timeout: 3s
```

Biến môi trường production:

```text
APP_NOTIFY_ENABLED=false
```

Lệnh chạy:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.notify.timeout=1s
```

Trong một environment sạch khác:

| Khóa | File gốc | Profile prod | Environment var | CLI | Giá trị Spring dự kiến |
| --- | --- | --- | --- | --- | --- |
| `app.notify.enabled` | false | true | false | Không | false |
| `app.notify.timeout` | 5s | 3s | Không | 1s | 1s |

Điều kiện:

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "enabled",
        havingValue = "true")
```

sẽ không match nếu key hiệu lực là `false`.

Một báo cáo “did not match” nói rằng yêu cầu `enabled=true` không đạt; nó **không nói** vì biến môi trường `APP_NOTIFY_ENABLED=false` hay vì file profile có giá trị khác. Nguồn có hiệu lực phải được điều tra riêng.

### Nguy cơ suy luận từ profile

Một người đọc `application-prod.yaml` thấy `enabled=true`, nhưng production vẫn tắt tính năng. Lý do có thể là environment variable có ưu tiên cao hơn profile file.

Thứ tự ưu tiên không thể suy ra chỉ từ tên profile. Mọi nguồn có thể cung cấp cùng key cần được xét trong context hiện tại.

## 25. Chẩn đoán khi `@ConditionalOnProperty` không match

Một quy trình thực hành:

1. **Đọc annotation**: prefix và name tạo tên đầy đủ nào?
2. **Kiểm tra `havingValue`**: yêu cầu chính xác true, false hay giá trị khác?
3. **Kiểm tra `matchIfMissing`**: thiếu key có được phép match không?
4. **Xem conditions**: condition thực sự match hay fail, ở class hay bean method?
5. **Xem env**: key có tồn tại trong Environment của đúng context/process không?
6. **Xem source**: property đến từ CLI, system property, env, file hay import?
7. **Xem profile**: những file profile-specific đã được nạp chưa?
8. **Kiểm tra tên biến môi trường**: có đúng quy tắc relaxed binding không?
9. **Xem configprops**: nếu có model, bean bind dữ liệu gì?
10. **Xem beans**: có bean cuối hay user bean ghi đè cấu hình mặc định không?
11. **Thử lại bằng test startup cô lập** với một giá trị xác định.
12. **Phân loại lỗi khác**: thiếu class/bean có thể là nguyên nhân chính, không phải property.

Không sửa annotations một cách tùy ý chỉ để làm positive match khi chưa biết yêu cầu nghiệp vụ của bean.

## 26. Cẩn trọng với tên property trong điều kiện

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "app.notify",
        name = "max-retry-count",
        havingValue = "5")
```

Tên canonical dùng kebab-case. Biến môi trường dạng phù hợp:

```text
APP_NOTIFY_MAXRETRYCOUNT=5
```

Tránh nhầm:

```text
APP_NOTIFY_MAX_RETRY_COUNT
```

với cách giữ nguyên dấu gạch nối như một segment. Quy tắc tên env thường bỏ dấu `-` khi tạo tên env theo property canonical.

Khi một condition liên quan property không match, đừng ngay lập tức kết luận giá trị sai; có thể **tên key đầu vào không được resolve** như người triển khai nghĩ.

Nếu cần xác nhận cách Binder liên kết một property cụ thể, dùng `@ConfigurationProperties` và test với các tên thực tế, vì `@ConditionalOnProperty` không tự đảm bảo mọi cơ chế relaxed binding của Binder được diễn giải như mong đợi cho mọi key phức tạp.

## 27. Chẩn đoán placeholder

Tệp:

```properties
app.notify.enabled=${NOTIFY_ENABLED:false}
```

Khi OS có:

```text
NOTIFY_ENABLED=true
```

giá trị được resolve có thể thành `"true"` khi được đọc từ Spring Environment.

Một condition report có thể thông báo match. Tuy nhiên, property này bao gồm:

- Key được khai báo trong file `application.properties`.
- Placeholder tham chiếu tới `NOTIFY_ENABLED`.
- Một nguồn OS environment cung cấp giá trị cho placeholder.
- Kết quả sau resolve là `true`.

Nếu bạn chỉ xem “source: application.properties”, có thể bỏ qua việc biến môi trường đã tác động gián tiếp. Hãy kiểm tra **cả key gốc và các placeholder nó tham chiếu**.

Nếu placeholder không có default và không thể resolve trong ngữ cảnh yêu cầu giá trị, có thể gây lỗi khi binding/bean tạo. Đừng khái quát rằng mọi placeholder thiếu đều tự thành `null` ở tất cả API.

## 28. Một số nguồn Config Data dễ bị bỏ sót

Khi kết quả env khác file bạn đang đọc, hãy kiểm tra:

```text
application.properties / application.yaml
application-{profile}.properties / YAML
spring.config.import
spring.config.location
spring.config.additional-location
Spring profile activation và location groups
Config tree
Tệp ngoài JAR
Command-line properties
Java system properties
OS environment variables
SPRING_APPLICATION_JSON
Test property sources
Nguồn do EnvironmentPostProcessor thêm
```

Ví dụ file:

```properties
spring.config.import=optional:file:./external/notify.properties
```

có thể làm một tài liệu import ghi đè key được khai báo trong file gốc theo quy tắc Config Data.

Nếu chỉ đọc `src/main/resources/application.properties`, có thể không thấy nguồn thực tế được import ở runtime. `/actuator/env/{name}` và origin (khi có) có thể chỉ ra nguồn thắng.

**Condition report không thay thế điều tra Config Data location/import.**

## 29. Phân biệt báo cáo conditions với configuration metadata

Tên gọi gần giống nhau nên dễ nhầm:

| Thành phần | Tác dụng |
| --- | --- |
| `META-INF/spring-configuration-metadata.json` | Mô tả những config properties để IDE gợi ý tên/kiểu/default |
| Condition Evaluation Report | Lý do auto-configuration/conditional configuration match hoặc không |
| `Environment` / `/actuator/env` | Nguồn và giá trị cấu hình có hiệu lực |
| `/actuator/configprops` | Những object được `@ConfigurationProperties` bind |
| `/actuator/beans` | Danh sách bean trong context |

Metadata do `spring-boot-configuration-processor` sinh khi compile **không phải** condition report, và cả hai đều không phải toàn bộ giá trị runtime.

Một IDE gợi ý `app.notify.enabled` không chứng minh property này có giá trị trong production. Tương tự, một positive condition không chứng minh metadata có description đúng.

## 30. Viết test nhỏ bằng `ApplicationContextRunner`

Đối với một condition của bean method, `ApplicationContextRunner` có thể kiểm tra có/không có bean và đọc giá trị trong `Environment`.

Trong test scope có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ:

```java
package example.evidence;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

class NotificationConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(OnlyConditionalConfig.class);

    @Configuration(proxyBeanMethods = false)
    static class OnlyConditionalConfig {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.notify",
                name = "enabled",
                havingValue = "true")
        NotificationSender notificationSender() {
            return new NotificationSender();
        }
    }

    @Test
    void trueCreatesBeanAndEnvironmentContainsTrue() {
        runner.withPropertyValues("app.notify.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NotificationSender.class);

                    assertThat(context.getEnvironment()
                            .getProperty("app.notify.enabled"))
                            .isEqualTo("true");
                });
    }

    @Test
    void falseDoesNotCreateConditionalBean() {
        runner.withPropertyValues("app.notify.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(NotificationSender.class);

                    assertThat(context.getEnvironment()
                            .getProperty("app.notify.enabled"))
                            .isEqualTo("false");
                });
    }

    @Test
    void missingPropertyDoesNotMatchByDefault() {
        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(NotificationSender.class);
            assertThat(context.getEnvironment()
                    .getProperty("app.notify.enabled"))
                    .isNull();
        });
    }
}
```

Ưu điểm:

- Mỗi test khai báo input rõ ràng.
- Xem **cả bean outcome và Environment**.
- Không cần mở web server.
- Không phụ thuộc external file hoặc database.

Giới hạn: `withPropertyValues(...)` cấp giá trị test trực tiếp. Nó **không chứng minh** Config Data đã tìm một file YAML thật, xử lý `spring.config.import`, hoặc tuân theo precedence giữa CLI/file trong một lần startup ứng dụng.

## 31. Test startup thật để chứng minh nguồn thắng

Khi cần chứng minh externalized configuration được nạp và điều kiện áp dụng tương ứng, dùng `SpringApplication.run(...)` với file tạm.

### 31.1. Model test

```java
package example.evidence;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notify")
public record NotifyProperties(
        boolean enabled,
        Duration timeout
) {}
```

Cho bài test riêng, đây là phiên bản record hai trường. Nếu copy vào cùng project demo ở trên, giữ **một định nghĩa** `NotifyProperties` nhất quán; không tạo hai class cùng tên/package.

### 31.2. Minimal application

```java
@SpringBootConfiguration(proxyBeanMethods = false)
@EnableConfigurationProperties(NotifyProperties.class)
static class MinimalApplication {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.notify",
            name = "enabled",
            havingValue = "true")
    NotificationSender notificationSender() {
        return new NotificationSender();
    }
}
```

Các annotation:

```java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
```

### 31.3. Test hoàn chỉnh với file ngoài và CLI

```java
package example.evidence;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class StartupConfigurationEvidenceTest {

    @TempDir
    Path tempDir;

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableConfigurationProperties(NotifyProperties.class)
    static class MinimalApplication {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.notify",
                name = "enabled",
                havingValue = "true"
        )
        NotificationSender notificationSender() {
            return new NotificationSender();
        }
    }

    private static ConfigurableApplicationContext start(
            String... args
    ) {
        SpringApplication app =
                new SpringApplication(MinimalApplication.class);

        app.setBannerMode(Banner.Mode.OFF);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setLogStartupInfo(false);

        return app.run(args);
    }

    @Test
    void cliOverridesFileAndConditionalBeanIsCreated()
            throws IOException {

        Path file = tempDir.resolve("application.properties");

        Files.writeString(
                file,
                "app.notify.enabled=false\n"
                + "app.notify.timeout=5s\n"
                + "app.notify.file-marker=external\n",
                StandardCharsets.UTF_8
        );

        try (ConfigurableApplicationContext context = start(
                "--spring.config.location=" + file.toUri(),
                "--app.notify.enabled=true",
                "--app.notify.timeout=2s"
        )) {
            assertThat(context.getEnvironment()
                    .getProperty("app.notify.enabled"))
                    .isEqualTo("true");

            assertThat(context.getEnvironment()
                    .getProperty("app.notify.file-marker"))
                    .isEqualTo("external");

            NotifyProperties props =
                    context.getBean(NotifyProperties.class);

            assertThat(props.enabled()).isTrue();
            assertThat(props.timeout())
                    .isEqualTo(Duration.ofSeconds(2));

            assertThat(context.getBeansOfType(
                    NotificationSender.class))
                    .hasSize(1);
        }
    }

    @Test
    void fileFalseDisablesTheConditionalBean()
            throws IOException {

        Path file = tempDir.resolve("another.properties");

        Files.writeString(
                file,
                "app.notify.enabled=false\n"
                + "app.notify.timeout=5s\n",
                StandardCharsets.UTF_8
        );

        try (ConfigurableApplicationContext context = start(
                "--spring.config.location=" + file.toUri()
        )) {
            assertThat(context.getEnvironment()
                    .getProperty("app.notify.enabled"))
                    .isEqualTo("false");

            assertThat(context.getBean(NotifyProperties.class)
                    .enabled()).isFalse();

            assertThat(context.getBeansOfType(
                    NotificationSender.class))
                    .isEmpty();
        }
    }
}
```

Dữ liệu ngoài được tạo bởi `@TempDir`, test không cần file thật trong repository hoặc dịch vụ ngoài. `spring.config.location` được cung cấp **ngay khi startup**, đúng thời điểm Boot cần nó.

### 31.4. Vì sao dùng marker độc lập?

Trong test thứ nhất:

```properties
app.notify.file-marker=external
```

không có trong CLI. Assert marker chứng minh file **đã được nạp**, còn assert `enabled=true` chứng minh CLI **thắng key xung đột**.

Nếu chỉ assert `enabled=true`, test vẫn có thể pass dù file ngoài chưa được nạp, vì CLI tự cung cấp true. Marker tách hai bằng chứng quan trọng:

```text
File có tham gia?   -> file-marker
Nguồn nào thắng?    -> enabled
```

### 31.5. Giới hạn của test

Nó xác nhận:

- Config Data startup qua `SpringApplication`.
- External file được nạp.
- CLI override.
- Binding thành `Duration`.
- Bean có điều kiện tồn tại hoặc không.

Nó không chứng minh:

- Một secret production được nạp an toàn.
- Endpoint ngoài reachable.
- Mọi profile, location group và imported document đều đúng.
- Một runtime refresh sau startup cập nhật lại condition.
- Hành vi trong một Kubernetes cluster cụ thể.

Chỉ kết luận phạm vi mà assertion thực sự kiểm chứng.

## 32. Cách kiểm tra report bằng API trong test

Khi cần điều tra report nội bộ, Spring Boot có:

```java
org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport
```

Báo cáo có thể truy xuất qua bean factory của một context phù hợp:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());
```

Đây là API ở package auto-configuration của Spring Boot. Nó cho phép đọc các condition outcomes đã được ghi, ví dụ các nguồn/condition trong:

```java
report.getConditionAndOutcomesBySource()
```

Khi dùng, hãy nhớ:

- Dữ liệu phản ánh những conditions được framework ghi trong context đó.
- Tên source thường là class hoặc method của configuration.
- Mỗi source có thể có nhiều outcomes.
- Dùng cho diagnostics/test nội bộ; đừng parse `message` như một schema ổn định.
- Kiểm tra bean context và `Environment` riêng.
- Một runner/test context có thể không kích hoạt mọi auto-configuration của ứng dụng production.

Không nhất thiết đưa tất cả cấu trúc `ConditionEvaluationReport` vào log. Đối với sự cố thường gặp, `/actuator/conditions` hoặc startup debug report dễ đọc hơn.

## 33. Một bảng quyết định “dùng công cụ nào trước?”

| Triệu chứng | Bước đầu ưu tiên | Bước tiếp theo |
| --- | --- | --- |
| Boot không tạo DataSource mặc dù có URL | `conditions` cho DataSourceAutoConfiguration | `env` cho `spring.datasource.*`, `beans` |
| Tính năng `enabled=true` nhưng bean không có | `conditions` ở class/method tương ứng | `env` key enabled, classpath/beans |
| Timeout runtime khác YAML | `env` cho key timeout | `configprops` hoặc kiểm tra code bind |
| `@ConfigurationProperties` bind sai Duration | `configprops` và logs binding | `env` và nguồn property thắng |
| IDE gợi ý property nhưng app không đọc | `env` và bean registration | code tiêu thụ property, metadata không đủ |
| Một auto-configuration báo negative do missing bean | `conditions` xem `OnBeanCondition` | `beans` xác nhận bean |
| Report positive nhưng chức năng không hoạt động | `beans`, integration test | kiểm tra dependency/runtime/network |
| Giá trị từ CLI nhưng `System.getProperty` null | `Environment` | `ApplicationArguments`/sources |
| Endpoint trả `******` | Kiểm tra sanitization | Test cục bộ có quyền, không bật show-values toàn cục |
| Profile `prod` nhưng config dùng giá trị `dev` | `env` + activeProfiles | config data import/location/CLI/env |
| Tính năng vẫn bật sau thay đổi property runtime | So sánh thời điểm condition và hiện tại | cơ chế refresh/rebinding nếu có |

Không có quy tắc một công cụ giải quyết mọi vấn đề. Cần chọn bằng chứng sát với **triệu chứng và tầng hoạt động**.

## 34. Các lỗi chẩn đoán dễ gặp

### Lỗi 1 — “Positive match nghĩa là YAML chứa true”

Sai. Positive match có thể từ default `matchIfMissing`, property source khác, classpath hoặc bean condition. Phải xác định loại condition và nguồn property.

### Lỗi 2 — “Negative match nghĩa là file chưa được đọc”

Sai. Auto-configuration có thể fail vì thiếu class/bean dù file có key đầy đủ.

### Lỗi 3 — “`Environment#getProperty` đúng nghĩa là bean có cùng giá trị”

Chưa chắc. Bean có thể dùng default, conversion, validation, binding từ source khác qua logic riêng, hoặc đã được bind trước khi Environment thay đổi.

### Lỗi 4 — “`configprops` là danh sách tất cả cấu hình Spring”

Không. Nó mô tả các `@ConfigurationProperties` beans, không bao gồm mọi lệnh `@Value`, `System.getenv` hoặc property chỉ được đọc thủ công.

### Lỗi 5 — “`/actuator/env` luôn hiện đầy đủ giá trị”

Không. Spring Boot 3.3 sanitize dữ liệu theo mặc định và quyền truy cập có thể hạn chế.

### Lỗi 6 — “Có `management.endpoints.web.exposure.include=*` là xong”

Đây có thể là rủi ro nghiêm trọng. Expose chỉ là một phần của endpoint availability; còn access control, network isolation, sensitive values và security chain.

### Lỗi 7 — “Sửa `application.properties` trong source sẽ đổi process đang chạy”

Không mặc định. Ứng dụng thường nạp cấu hình khi khởi động. Cần hiểu cơ chế restart/refresh thực tế, đặc biệt với artifact JAR hoặc image đã build.

### Lỗi 8 — “Condition được đánh giá lại khi Env thay đổi”

Không mặc định. Một report ở startup không phải monitor live condition cho từng request.

### Lỗi 9 — “CLI không ảnh hưởng vì YAML đã có khóa”

Sai. Command-line properties thường có precedence cao hơn config data trong cấu hình mặc định của Boot.

### Lỗi 10 — “`@ConditionalOnProperty` mặc định đòi true”

Sai. Không có `havingValue`, property có mặt và khác `"false"` có thể match.

### Lỗi 11 — “`matchIfMissing=true` chứng minh có default trong Env”

Sai. Condition có thể match chính vì key không tồn tại.

### Lỗi 12 — “Một `OnMissingBean` message có chữ 'missing' là negative”

Sai. Không tìm thấy bean có thể là **kết quả match** của `@ConditionalOnMissingBean`.

### Lỗi 13 — “`/actuator/conditions` liệt kê mọi bean”

Không. Endpoint `conditions` tập trung vào condition evaluation. Dùng `/actuator/beans` nếu cần danh sách bean đã đăng ký.

### Lỗi 14 — “Origin luôn có tên file và số dòng”

Không. Điều này phụ thuộc loại PropertySource và khả năng origin tracking; không phải mọi nguồn đều có line/column.

### Lỗi 15 — “Metadata IDE chính là condition report”

Không. Metadata sinh khi compile và cung cấp gợi ý tên/kiểu. Condition report phản ánh điều kiện tại startup.

## 35. Khi nhìn một dòng report, hãy đặt năm câu hỏi

Giả sử report ghi:

```text
NotificationConfiguration#notificationSender matched:
  - @ConditionalOnProperty (app.notify.enabled=true) matched
```

Trước khi kết luận, hãy hỏi:

1. **Condition nào?** `OnPropertyCondition` hay `OnClassCondition`, `OnBeanCondition`?
2. **Property nào?** Key đầy đủ, canonical, và chính xác `havingValue`/`matchIfMissing`?
3. **Thời điểm nào?** Startup hay một context được khởi tạo lại?
4. **Giá trị đến đâu?** `Environment`, Binder `@ConfigurationProperties`, hay code đọc trực tiếp Java API?
5. **Bean cuối và hành vi?** Bean có tồn tại không; đã được sử dụng chưa?

Năm câu hỏi này giúp tránh các bước sửa sai kiểu:

- Thêm một property vào YAML khi nguyên nhân thật là missing dependency.
- Bật toàn bộ actuator khi chỉ cần xem một key cục bộ.
- Đổi `@ConditionalOnProperty` dù property đến từ CLI có precedence cao hơn.
- Bỏ validation chỉ vì condition đã match.
- Chỉnh timeout trong file đã bị environment variable ghi đè.

## 36. Các bài tập tự kiểm tra

### Bài 1 — positive match không nói nguồn

`application.yaml` ghi `app.notify.enabled=false`, CLI ghi `--app.notify.enabled=true`. Conditions cho biết `OnPropertyCondition` với `havingValue=true` match.

**Hỏi:** Có chắc YAML đã chứa true không?

**Đáp án:** Không. CLI có thể ghi đè thành true. Dùng `Environment` hoặc `/actuator/env/app.notify.enabled` để xác định nguồn thắng.

### Bài 2 — điều kiện mặc định

```java
@ConditionalOnProperty(name = "app.mode")
```

`app.mode=experimental`.

**Hỏi:** Có thể match không?

**Đáp án:** Có. Mặc định, property có mặt và khác `"false"` có thể match.

### Bài 3 — matchIfMissing

```java
@ConditionalOnProperty(
    name = "app.notify.enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

Không có property `app.notify.enabled`.

**Hỏi:** Condition có thể match không?

**Đáp án:** Có. Đây là hợp đồng rõ của `matchIfMissing=true`.

### Bài 4 — default JavaBean

Một bean có `enabled=true` do field initializer, nhưng `Environment#getProperty("app.notify.enabled")` là null.

**Hỏi:** Có mâu thuẫn không?

**Đáp án:** Không. Default trong Java object không đồng nghĩa property đã tồn tại trong Environment.

### Bài 5 — System vs Spring

Lệnh:

```bash
java -Dapp.notify.enabled=false -jar app.jar \
  --app.notify.enabled=true
```

**Hỏi:** `System.getProperty` và `Environment#getProperty` có thể khác nhau thế nào?

**Đáp án:** Java system property là false, còn Spring Environment có thể chọn true từ CLI.

### Bài 6 — thiếu class

Config có `app.cache.enabled=true` nhưng auto-configuration có `OnClassCondition` fail.

**Hỏi:** Có thể kết luận key `app.cache.enabled` không tồn tại không?

**Đáp án:** Không. Điều kiện classpath fail độc lập với key; kiểm tra dependency và Environment riêng.

### Bài 7 — OnMissingBean

Báo cáo ghi `@ConditionalOnMissingBean did not find any beans`.

**Hỏi:** Đây có thể là positive match không?

**Đáp án:** Có. Điều kiện yêu cầu **không có bean**, nên không tìm thấy bean có thể là kết quả đạt.

### Bài 8 — Actuator endpoints

**Hỏi:** Endpoint nào cho condition outcomes, endpoint nào cho property source, endpoint nào cho bean đã bind?

**Đáp án:** `/actuator/conditions`, `/actuator/env`, `/actuator/configprops` tương ứng.

### Bài 9 — sanitization

`/actuator/env/app.secret.token` trả `"******"`.

**Hỏi:** Ứng dụng có chắc đang dùng literal sáu dấu sao không?

**Đáp án:** Không. Giá trị có thể đã bị sanitization che. Không tự mở unrestricted exposure để xác nhận secret.

### Bài 10 — source name và origin

Endpoint chỉ có source `systemEnvironment` mà không có line number.

**Hỏi:** Endpoint hỏng không?

**Đáp án:** Không. Nhiều nguồn không có thông tin file/line như cấu hình YAML.

### Bài 11 — test chứng minh CLI override

Một test gọi `SpringApplication.run("--app.notify.enabled=true")` rồi assert true.

**Hỏi:** Test đã chứng minh file external được nạp chưa?

**Đáp án:** Chưa. Cần marker property chỉ có ở external file để xác minh sự hiện diện.

### Bài 12 — condition report sau refresh

Report ghi condition match từ startup. Sau đó một thành phần đổi Environment thành false.

**Hỏi:** Bean sẽ tự bị xóa chứ?

**Đáp án:** Không mặc định. Conditions không tự động được đánh giá lại khi một property thay đổi.

### Bài 13 — bound model và nguyên nhân runtime

`NotifyProperties.timeout=PT5S`, nhưng request mất 20 giây.

**Hỏi:** Có thể kết luận Binder sai không?

**Đáp án:** Chưa. Timeout trong model có thể không được client sử dụng đúng, hoặc một thành phần khác có timeout riêng. Cần kiểm tra wiring và phép đo runtime.

### Bài 14 — `@ConditionalOnProperty` trên collection

Config chỉ có `app.notify.channels[0]=email`, condition kiểm tra `app.notify.channels`.

**Hỏi:** Có đáng tin cậy để quyết định list có phần tử không?

**Đáp án:** Không. JavaDoc cảnh báo điều kiện này không phù hợp để kiểm tra collection theo cách đó. Thiết kế condition phù hợp hoặc validate model đã bind.

### Bài 15 — bảo mật

Nhóm muốn bật:

```properties
management.endpoint.env.show-values=always
management.endpoints.web.exposure.include=*
```

trên public host.

**Hỏi:** Có an toàn không?

**Đáp án:** Không nên làm. Cần giới hạn exposure, xác thực/ủy quyền và chính sách sanitization để tránh lộ secret, thông tin hệ thống và endpoint nhạy cảm.

## 37. Checklist xử lý sự cố cấu hình

- [ ] Đang điều tra điều kiện, giá trị property hay trạng thái bean?
- [ ] Đã xác định chính xác process, profile và context đang chạy?
- [ ] Đã đọc condition **cụ thể** ở class/bean method liên quan?
- [ ] Đã phân biệt `positiveMatches` với `negativeMatches` và lý do từng condition?
- [ ] Đã đọc `havingValue` và `matchIfMissing` thay vì suy luận từ tên property?
- [ ] Đã kiểm tra nguồn có ưu tiên cao hơn `application.yaml` chưa?
- [ ] Đã kiểm tra `spring.config.import` và vị trí file ngoài JAR chưa?
- [ ] Đã lấy giá trị có hiệu lực từ `Environment#getProperty` hoặc endpoint env có quyền?
- [ ] Đã xem origin của key khi nguồn hỗ trợ?
- [ ] Đã phân biệt giá trị bị sanitize với giá trị literal?
- [ ] Đã kiểm tra `@ConfigurationProperties` được đăng ký và bind đúng kiểu?
- [ ] Đã xem bean thực qua context hoặc endpoint beans?
- [ ] Đã xem lỗi binding/validation riêng với condition?
- [ ] Đã phân biệt thời điểm startup với thay đổi dynamic config sau đó?
- [ ] Đã tránh in secret hoặc dump toàn bộ Environment vào log?
- [ ] Đã có ít nhất một test cô lập tái tạo precedence/bean outcome?
- [ ] Đã kiểm tra hoạt động nghiệp vụ bằng integration test khi cần?
- [ ] Đã tránh thay API/cấu hình để ép một condition match mà chưa biết nguyên nhân?
- [ ] Đã dùng đúng phiên bản tài liệu Spring Boot so với ứng dụng thực?
- [ ] Đã thu hẹp Actuator endpoints và giới hạn truy cập ở production?

## 38. Tóm tắt

Một chuỗi bằng chứng đúng cho vấn đề cấu hình:

```text
Yêu cầu nghiệp vụ:
"NotificationSender chỉ hoạt động khi bật"
                |
                v
Condition Evaluation Report
"Điều kiện của bean có đạt không?"
                |
                v
Environment / Actuator env
"Property có giá trị hiệu lực gì và nguồn nào thắng?"
                |
                v
@ConfigurationProperties / configprops
"Giá trị đã được chuyển và liên kết ra sao?"
                |
                v
ApplicationContext / beans
"Bean thực tế có tồn tại không?"
                |
                v
Integration test / runtime observation
"Tính năng có thực sự hoạt động đúng không?"
```

Những nguyên tắc cốt lõi:

1. **Condition report là báo cáo về điều kiện**, không phải bản kê toàn bộ cấu hình hiệu lực.
2. **`@ConditionalOnProperty` có các quy tắc `havingValue`, `matchIfMissing`**; match không nhất thiết chứng minh key tồn tại hoặc có boolean true.
3. **`Environment#getProperty` và `/actuator/env`** dùng để quan sát giá trị có hiệu lực và PropertySources, nhưng cần tính tới sanitization và origin availability.
4. **`/actuator/configprops`** dùng để xem các `@ConfigurationProperties` beans đã bind, không phải mọi nơi ứng dụng đọc cấu hình.
5. **Kiểm tra bean cuối riêng với condition outcome**, vì auto-configuration có thể back off do user bean, classpath, các điều kiện cấp method hoặc lifecycle.
6. **Bằng chứng startup không tự chứng minh trạng thái runtime sau khi Environment đổi**; cần xác định thời điểm và refresh mechanism.
7. **Bảo vệ dữ liệu cấu hình nhạy cảm** khi dùng các endpoint chẩn đoán; không mở toàn bộ Actuator ra internet chỉ để tìm một lỗi.
8. **Một bài test tốt nên assert source marker, property hiệu lực, model đã bind và bean outcome**, mỗi phần cho một loại kết luận khác nhau.

Nếu cần xác định “vì sao tính năng không bật”, hãy dùng `conditions` để hiểu quyết định điều kiện, `env` để xác định property thực tế, `configprops` để xem dữ liệu được bind và `beans`/test để xác minh hiệu quả. Đó là cách chẩn đoán đúng lớp, tránh nhầm một báo cáo tự cấu hình với bằng chứng giá trị thuộc tính đang được ứng dụng sử dụng.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 Reference — Externalized Configuration / PropertySource Order: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Actuator Endpoints, exposure, security, sanitization: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 Actuator REST — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 Actuator REST — Environment: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html
- Spring Boot 3.3 Actuator REST — Configuration Properties: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html
- Spring Boot 3.3 Java API — `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 Java API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
