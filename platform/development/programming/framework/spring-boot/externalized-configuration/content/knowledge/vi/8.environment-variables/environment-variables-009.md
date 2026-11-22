# Ý nghĩa của null trong JSON khi cần ghi đè giá trị

Trong Spring Boot, một cách đưa nhiều property vào ứng dụng qua biến môi trường là dùng **`SPRING_APPLICATION_JSON`**. Biến này chứa một chuỗi JSON; Spring Boot đọc JSON và thêm các giá trị vào hệ thống **externalized configuration**. Cách làm đó hữu ích khi deployment muốn cung cấp một nhóm cấu hình có cấu trúc mà không phải tạo nhiều biến môi trường riêng lẻ.

Tuy nhiên, có một quy tắc dễ gây bất ngờ: **giá trị JSON `null` không thể được dùng như lệnh “xóa” hoặc “che” giá trị trùng key đến từ nguồn cấu hình có thứ tự ưu tiên thấp hơn**. Spring Boot có thể đưa một mục có giá trị null vào nguồn property được tạo từ JSON, nhưng khi phân giải property, `PropertySourcesPropertyResolver` coi `null` như **không tìm thấy giá trị** và tiếp tục xem các nguồn khác. Vì vậy, nếu `application.yml` đã có giá trị, đặt key ấy thành `null` trong `SPRING_APPLICATION_JSON` không làm giá trị đó biến mất.

Bài này tập trung vào ý nghĩa của `null` khi muốn ghi đè cấu hình bằng JSON, cách phân biệt với chuỗi `"null"` và chuỗi rỗng, cách quan sát giá trị có hiệu lực trong ứng dụng, và những lựa chọn đúng khi thực sự muốn bỏ hoặc vô hiệu một cấu hình.

## 1. SPRING_APPLICATION_JSON là gì?

Ví dụ ứng dụng có `application.yml`:

~~~yaml
app:
  display-name: "Order Service"
  feature:
    enabled: true
  request:
    timeout: 5s
~~~

Một deployment có thể cung cấp biến môi trường:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"feature":{"enabled":false},"request":{"timeout":"2s"}}}'
java -jar order-service.jar
~~~

Trong ví dụ shell POSIX trên, giá trị của `SPRING_APPLICATION_JSON` là **một chuỗi JSON hoàn chỉnh**. Spring Boot đọc nội dung JSON và đưa các key đã phân rã vào hệ thống property, chẳng hạn:

~~~text
app.feature.enabled = false
app.request.timeout = 2s
~~~

Khi không có nguồn ưu tiên cao hơn ghi đè, cấu hình được cung cấp từ JSON có thể thắng các giá trị tương ứng trong `application.yml`. Ứng dụng nhận cờ `false` và thời lượng `2s` thay vì `true` và `5s`.

Điểm cần hiểu:

- `SPRING_APPLICATION_JSON` là **tên một biến môi trường**, còn nội dung biến là **văn bản JSON**.
- Spring Boot cũng hỗ trợ cung cấp cùng loại dữ liệu qua Java system property `spring.application.json` hoặc tham số dòng lệnh tương ứng trong những cách khởi động phù hợp.
- JSON có thể biểu diễn object lồng nhau; Spring Boot tạo các property mang tên dạng chấm, như `app.feature.enabled`.
- JSON được xử lý trong quá trình chuẩn bị môi trường cấu hình ở startup; đây không phải nơi lưu dữ liệu nghiệp vụ theo request.
- JSON phải hợp lệ về cú pháp, và giá trị cuối cùng còn phải phù hợp với kiểu Java khi binding.

Không nên nhầm `SPRING_APPLICATION_JSON` với một file JSON bất kỳ nằm trên ổ đĩa. Cơ chế này đặc biệt liên quan tới property có tên `spring.application.json` hoặc biến môi trường tương ứng.

## 2. Quy tắc cốt lõi: JSON null không phải “xóa cấu hình”

Xét file `application.yml`:

~~~yaml
app:
  mode: "normal"
  retry-count: 3
~~~

Deployment muốn bỏ giá trị `app.mode` bằng cách ghi JSON:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":null}}'
java -jar order-service.jar
~~~

Nhiều người dự đoán:

~~~text
app.mode = null
~~~

Nhưng khi ứng dụng truy vấn giá trị qua Spring `Environment`, kết quả điển hình lại là:

~~~text
app.mode = normal
~~~

Vì `app.mode` từ JSON có giá trị null, bộ phân giải property coi giá trị này như vắng mặt, tiếp tục tìm ở nguồn cấu hình kế tiếp và thấy `app.mode=normal` từ `application.yml`.

Có thể hình dung:

~~~text
Tra cứu: app.mode
        |
        v
SPRING_APPLICATION_JSON
  app.mode -> null
        |
        | null được xem như không có giá trị dùng được
        v
application.yml
  app.mode -> "normal"
        |
        v
Giá trị hiệu lực: "normal"
~~~

**Đây là cơ chế phân giải property, không phải thao tác hợp nhất JSON theo kiểu JSON Merge Patch.** Trong một số đặc tả patch, `null` có nghĩa xóa field. `SPRING_APPLICATION_JSON` của Spring Boot không có ngữ nghĩa “tombstone” (dấu xóa) như vậy.

Nếu nguồn ưu tiên thấp hơn cũng không có key ấy, kết quả có thể là property không tìm thấy. Nếu một nguồn khác có giá trị, Spring có thể dùng giá trị đó. Việc gõ `null` vào JSON không bảo đảm một trường Java sẽ được nhận null.

## 3. Vì sao nguồn ưu tiên cao hơn có null vẫn không thắng?

Khi giải quyết một key cấu hình, Spring Boot dựa trên mô hình các `PropertySource` có thứ tự ưu tiên. Ý tưởng chung là tìm nguồn có giá trị sử dụng được cho key đó, theo thứ tự từ ưu tiên cao xuống thấp.

Ví dụ:

| Nguồn | Giá trị `app.mode` |
| --- | --- |
| JSON từ `SPRING_APPLICATION_JSON` | `null` |
| `application-prod.yml` | `"safe"` |
| `application.yml` | `"normal"` |

Giả sử profile `prod` đang được bật và không có nguồn nào cao hơn cung cấp `app.mode`. JSON có null nên không chặn truy vấn; nguồn tiếp theo có `"safe"`, vì vậy giá trị hiệu lực là `"safe"`.

Nếu JSON đổi thành:

~~~json
{
  "app": {
    "mode": "maintenance"
  }
}
~~~

thì `"maintenance"` là giá trị khác null và có thể ghi đè `"safe"` theo thứ tự ưu tiên thông thường.

Điểm quan trọng là:

- **Độ ưu tiên xác định nguồn nào được xét trước.**
- **Null có ý nghĩa “không có giá trị” đối với bộ phân giải property.**
- **Một mục null ở nguồn ưu tiên cao không ngăn quá trình tìm giá trị ở nguồn thấp hơn.**

Thứ tự ưu tiên tổng thể còn có thể có tham số dòng lệnh, Java system properties, OS environment variables, Config Data, v.v. Ví dụ nếu command line cung cấp `--app.mode=forced` thì giá trị đó có thể ưu tiên hơn JSON. Khi chẩn đoán sự cố, hãy xét đúng danh sách nguồn thực tế của phiên chạy.

## 4. So sánh null, "null", chuỗi rỗng, false và 0

Các giá trị sau **khác nhau** ngay từ JSON:

~~~json
{
  "app": {
    "nullable": null,
    "literalNull": "null",
    "emptyText": "",
    "feature": {
      "enabled": false
    },
    "retryCount": 0
  }
}
~~~

| Cách viết trong JSON | Loại giá trị JSON | Tác động khi phân giải property |
| --- | --- | --- |
| `null` | JSON null | Không thể che giá trị ở nguồn thấp hơn |
| `"null"` | Chuỗi gồm bốn ký tự | Là một giá trị chuỗi thực, có thể ghi đè text |
| `""` | Chuỗi rỗng | Là giá trị khác null; có thể ghi đè chuỗi |
| `false` | Boolean false | Là giá trị có mặt; có thể ghi đè cờ true |
| `0` | Number zero | Là giá trị có mặt; có thể ghi đè số khác 0 |
| Không khai báo key | Không có property trong nguồn JSON | Spring tiếp tục tìm ở các nguồn khác |

Giả sử `application.yml` chứa:

~~~yaml
demo:
  nullable: "fallback"
  literal-null: "fallback"
  empty-text: "fallback"
  feature:
    enabled: true
  retry-count: 5
~~~

Khi deployment cung cấp JSON tương ứng, kết quả về ý định sẽ là:

~~~text
demo.nullable        -> "fallback"  # JSON null không che được
demo.literal-null    -> "null"      # chuỗi literal
demo.empty-text      -> ""          # chuỗi rỗng
demo.feature.enabled -> false       # boolean false
demo.retry-count     -> 0           # số 0
~~~

Kết quả cuối cùng ở bean Java vẫn phụ thuộc bước **conversion/binding**. Chẳng hạn chuỗi rỗng có thể được giữ khi field là `String`, nhưng không nên dùng chuỗi rỗng để giả vờ là “xóa” một `int`, `Duration` hay `URI`: converter hoặc validation có thể báo lỗi hoặc áp dụng cách xử lý riêng theo kiểu đích.

**Không nên thay JSON `null` bằng `"null"` chỉ để ép override** nếu field thật sự là boolean, số, URL hay thời lượng. Khi ấy một chuỗi `"null"` có thể gây lỗi binding, và nó không mang ý nghĩa “không có giá trị”.

## 5. Dấu nháy trong JSON và kiểu dữ liệu

Trong JSON, các kiểu dữ liệu được biểu diễn rõ bằng cú pháp:

~~~json
{
  "name": "api-service",
  "attempts": 3,
  "enabled": true,
  "missing": null
}
~~~

- `"api-service"` là string.
- `3` là number.
- `true` là boolean.
- `null` là giá trị null.
- `"true"`, `"3"`, `"null"` là string, không phải các literal tương ứng.

Không nên coi giá trị biến môi trường `SPRING_APPLICATION_JSON` tự nó là một JSON object trong hệ điều hành: ở tầng OS, giá trị biến môi trường vẫn là **chuỗi text**. Chuỗi này được Spring Boot parse lại thành JSON khi khởi động.

Trong shell, ngoài quy tắc JSON còn có quy tắc **quote của shell**. Ví dụ ở Linux/macOS với POSIX shell:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":null,"enabled":false}}'
java -jar app.jar
~~~

Ở PowerShell:

~~~powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"mode":null,"enabled":false}}'
java -jar .\app.jar
~~~

Trong các ví dụ này, dấu nháy đơn bên ngoài chỉ giúp shell giữ một JSON string. Dấu nháy kép bên trong là **cú pháp JSON** cho các tên key. Dấu `null` không nháy ở bên trong mới là JSON null thực sự.

Nếu viết:

~~~json
{"app":{"mode":"null"}}
~~~

thì Spring Boot nhận chữ `"null"`, không phải null.

## 6. Ví dụ có thể quan sát bằng Spring Environment

Cấu hình cơ bản:

~~~yaml
# application.yml
app:
  mode: "normal"
  feature:
    enabled: true
  retry-count: 3
~~~

Một ứng dụng tối giản để in ra **các giá trị không nhạy cảm**:

~~~java
package example.configdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ConfigDemoApplication implements CommandLineRunner {

    private final Environment environment;

    public ConfigDemoApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
            "app.mode=" + environment.getProperty("app.mode"));
        System.out.println(
            "app.feature.enabled=" +
                environment.getProperty("app.feature.enabled"));
        System.out.println(
            "app.retry-count=" +
                environment.getProperty("app.retry-count"));
    }
}
~~~

Đây là ví dụ quan sát property, không phải khuyến nghị in mọi cấu hình ứng dụng ra stdout; tuyệt đối tránh in secret, token và thông tin nhạy cảm.

Chạy với JSON null:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":null}}'
java -jar app.jar
~~~

Kết quả dự kiến (nếu không có nguồn ưu tiên cao hơn):

~~~text
app.mode=normal
app.feature.enabled=true
app.retry-count=3
~~~

Chạy với JSON có giá trị cụ thể:

~~~bash
export SPRING_APPLICATION_JSON='{"app":{"mode":"maintenance","feature":{"enabled":false},"retry-count":0}}'
java -jar app.jar
~~~

Kết quả dự kiến:

~~~text
app.mode=maintenance
app.feature.enabled=false
app.retry-count=0
~~~

Bài học: `null` không xóa `normal`, nhưng `"maintenance"`, `false` và `0` là các giá trị hợp lệ để override, tùy key và kiểu Java.

Trong dự án thực tế, các key nên được đặt tên theo một quy ước nhất quán (ví dụ dạng kebab-case), và test có thể đọc trực tiếp giá trị hiệu lực từ `Environment` mà không cần log ở production.

## 7. Ý nghĩa với @Value và @ConfigurationProperties

Spring Boot có nhiều cách đưa cấu hình vào Java. Hai cách quen thuộc:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class ModePrinter {

    private final String mode;

    ModePrinter(@Value("${app.mode:normal}") String mode) {
        this.mode = mode;
    }
}
~~~

Và binding theo nhóm:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppSettings(String mode) {}
~~~

Nếu nguồn JSON trả về null cho `app.mode` nhưng `application.yml` có `app.mode=normal`, quá trình phân giải property vẫn tìm thấy `normal` ở nguồn thấp hơn. Vì vậy:

- Với `@Value`, placeholder có thể nhận `normal` thay vì coi JSON null là một lệnh xóa.
- Với `@ConfigurationProperties`, Binder cũng làm việc trên các nguồn cấu hình hiệu lực và không mặc nhiên biến JSON null thành “xóa giá trị có sẵn”.
- Nếu không nguồn nào cung cấp một giá trị dùng được, kết quả phụ thuộc kiểu field, mặc định, constructor và validation; không thể suy luận chung rằng mọi field sẽ nhận `null` hoặc rằng ứng dụng sẽ khởi động thành công.

Lưu ý về `@Value("${app.mode:normal}")`: phần `:normal` là **giá trị fallback của placeholder** khi không tìm thấy property phù hợp. Nó khác hoàn toàn JSON `null` và không phải chỉ thị xóa.

Một trường kiểu primitive như `boolean` không nhận được Java null; ngược lại, `Boolean` có thể biểu diễn null nhưng cơ chế binding và validation cần được thiết kế rõ. Không dùng JSON null như một shortcut để chuyển kiểu field.

## 8. Null ở object cha không xóa các property con

Một hiểu nhầm khác là nghĩ JSON null cho cả object có thể loại bỏ toàn bộ các key lồng bên dưới.

Giả sử cấu hình gốc:

~~~yaml
app:
  remote:
    url: "https://api.example.invalid"
    timeout: 3s
    enabled: true
~~~

Deployment cung cấp:

~~~json
{
  "app": {
    "remote": null
  }
}
~~~

Không nên kỳ vọng cấu hình hiệu lực trở thành một `app.remote=null` che toàn bộ `app.remote.url`, `app.remote.timeout` và `app.remote.enabled`. Hệ thống property của Spring xử lý các key cấu hình sau khi nguồn được đọc/flatten; giá trị null không phải một dấu xóa cả cây property. Những key con từ `application.yml` có thể vẫn được phân giải và bind.

Tương tự:

~~~json
{
  "app": {
    "remote": {
      "url": null
    }
  }
}
~~~

không tự làm mất URL đã có trong nguồn thấp hơn. Để thay đổi URL, hãy cung cấp URL cụ thể và hợp lệ; để vô hiệu hóa remote integration, dùng cờ có ngữ nghĩa rõ hoặc đổi cấu trúc cấu hình.

Nguyên tắc: **không áp dụng trực giác của JSON Merge Patch hoặc phép hợp nhất object trong JavaScript vào Spring property sources**. Chúng là những mô hình khác nhau.

## 9. Muốn xóa hoặc vô hiệu giá trị thì làm gì?

Trước khi chọn cách xử lý, phải phân biệt **xóa giá trị** và **không sử dụng tính năng**.

### 9.1. Muốn không bật một tính năng

Dùng một property boolean rõ nghĩa:

~~~yaml
# application.yml
notifications:
  enabled: true
  destination: "https://notify.example.invalid"
~~~

Ở deployment muốn tắt:

~~~json
{
  "notifications": {
    "enabled": false
  }
}
~~~

Cờ `false` là giá trị thực và có thể ghi đè `true`. Ứng dụng cần dùng cờ này để quyết định có tạo bean tích hợp hay có thực hiện chức năng:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "notifications",
        name = "enabled",
        havingValue = "true"
    )
    NotificationClient notificationClient(
            NotificationProperties properties) {
        return new NotificationClient(properties.destination());
    }
}
~~~

`NotificationClient` và `NotificationProperties` là các kiểu minh họa của module. Khi `enabled=false`, bean có điều kiện không được đăng ký; các bean phụ thuộc bắt buộc khác cần thiết kế phù hợp với trường hợp tích hợp bị tắt.

Điểm chính là cờ `enabled=false` diễn đạt hành vi rõ ràng hơn `destination=null`.

### 9.2. Muốn thay một giá trị đã định nghĩa

Cung cấp giá trị thay thế hợp lệ:

~~~json
{
  "notifications": {
    "destination": "https://notify-staging.example.invalid"
  }
}
~~~

Khi có một giá trị khác null, quy tắc ưu tiên nguồn có thể chọn giá trị mới. Nếu muốn thay URL bằng địa chỉ của mock server, hãy dùng URL mock cụ thể thay vì null.

### 9.3. Muốn thực sự không còn property mặc định

Nếu mục tiêu là một môi trường **không có** property, cách sạch nhất là **không khai báo property đó ở nguồn cấu hình thấp hơn vốn luôn được nạp**. Có thể:

- Di chuyển property chỉ dùng ở production sang cấu hình được kích hoạt riêng ở production.
- Xóa giá trị mặc định không còn đúng khỏi cấu hình chung.
- Chỉ đưa một cấu hình tích hợp vào nguồn import/nguồn deployment khi tính năng đó cần chạy.
- Thiết kế bean có điều kiện và validation để vắng property là một trạng thái được hỗ trợ.

Ví dụ thay vì để endpoint production trong file chung:

~~~yaml
# application.yml — cấu hình chung
notifications:
  enabled: false
~~~

Chỉ production cung cấp:

~~~yaml
# application-prod.yml
notifications:
  enabled: true
~~~

Và endpoint nhạy cảm hoặc thay đổi theo deployment được cung cấp qua nguồn cấu hình bên ngoài. Lúc này môi trường không cần tích hợp sẽ không kế thừa endpoint production từ file chung.

### 9.4. Muốn biểu diễn trạng thái “không chọn”

Có thể dùng một giá trị sentinel tường minh, ví dụ `provider: "none"`, nếu **ứng dụng định nghĩa và kiểm tra** trạng thái đó:

~~~yaml
storage:
  provider: "none"
~~~

Trong Java, enum như `NONE`, `S3`, `AZURE` có thể làm trạng thái rõ ràng hơn. Đây là thiết kế miền cấu hình của ứng dụng; Spring Boot không tự hiểu mọi chuỗi `"none"` là một lệnh tắt.

### 9.5. Muốn chuỗi rỗng

Với property thực sự là chuỗi và giá trị rỗng có nghĩa, có thể ghi:

~~~json
{
  "app": {
    "display-name": ""
  }
}
~~~

Chuỗi rỗng khác null; khi đích là `String`, nó có thể ghi đè tên hiển thị. Nhưng **không dùng chuỗi rỗng để xóa mọi loại property**: field có validation `@NotBlank` sẽ không chấp nhận nó; kiểu số, boolean, duration hoặc URI có quy tắc conversion riêng. Cần thiết kế và thử nghiệm dựa trên kiểu đích thực tế.

## 10. Trường hợp security: null có thể khiến giá trị cũ vẫn được dùng

Giả sử cấu hình chung hoặc một nguồn thấp hơn vô tình chứa:

~~~yaml
external:
  api:
    endpoint: "https://legacy.example.invalid"
~~~

Ở deployment mới, người vận hành nghĩ rằng ghi:

~~~json
{
  "external": {
    "api": {
      "endpoint": null
    }
  }
}
~~~

sẽ ngăn ứng dụng dùng endpoint cũ. Nhưng Spring có thể tiếp tục lấy `endpoint` từ cấu hình thấp hơn, dẫn đến **vẫn kết nối tới endpoint cũ**.

Đây là lý do không nên dùng `null` như một cách “reset” bảo mật hoặc vận hành. Nếu endpoint cũ không còn hợp lệ, cần bỏ nó khỏi nguồn gốc, cấp endpoint mới hoặc tắt rõ ràng tích hợp. Với secret cũng vậy: JSON null không phải phương pháp xóa credential được kế thừa; secret phải được quản lý ở hạ tầng và không nằm trong file cấu hình chung được commit.

Các ràng buộc nên có:

- Không đưa credential mặc định nhạy cảm vào `application.yml`.
- Xác thực các property bắt buộc trước khi bắt đầu xử lý traffic.
- Dùng cờ disable hoặc môi trường riêng khi không muốn chạy tích hợp.
- Kiểm tra giá trị hiệu lực sau các lần thay đổi deployment, nhưng không tiết lộ token/password trong log.

## 11. Chẩn đoán: biết property đến từ nguồn nào

Khi JSON null “không có tác dụng”, trước tiên xác định:

1. **Tên property có đúng không?** `app.remote.url` khác `app.remote-url` ở cách tổ chức, và JSON lồng nhau phải tương ứng với key cần tra cứu.
2. **Biến môi trường có đúng tên và chứa JSON hợp lệ không?** `SPRING_APPLICATION_JSON` phải được truyền tới chính tiến trình Java cần cấu hình.
3. **JSON có dùng null literal hay string `"null"`?** Hai dạng có hành vi khác nhau.
4. **Có nguồn thấp hơn vẫn cung cấp giá trị không?** Kiểm tra `application.yml`, file profile, config import và nguồn mặc định khác.
5. **Có nguồn cao hơn đang override không?** Ví dụ tham số dòng lệnh có thể thắng JSON.
6. **Đích Java nhận kiểu gì?** Phân biệt lỗi property resolution với lỗi conversion/validation.
7. **Ứng dụng đã được khởi động lại để đọc cấu hình mới chưa?** Biến môi trường của tiến trình đang chạy không tự đổi chỉ vì chỉnh manifest hoặc shell bên ngoài.

Có thể dùng Spring Boot Actuator `/actuator/env` hoặc `/actuator/configprops` trong môi trường kiểm soát nếu ứng dụng bật, cấu hình và bảo vệ các endpoint này đúng cách. Chúng có thể giúp tra cứu property và nguồn cấu hình, nhưng **không được mở công khai hoặc dùng để in dữ liệu nhạy cảm**.

Trong test hoặc công cụ debug nội bộ, truy vấn một key không nhạy cảm qua `Environment` là cách đơn giản để phân biệt “JSON null bị xem là vắng mặt” với “giá trị bị một nguồn khác ghi đè”.

## 12. Ba tình huống dễ nhầm

### 12.1. “Tôi truyền null nhưng @Value vẫn lấy giá trị mặc định”

Ví dụ:

~~~yaml
# application.yml
mail:
  sender-name: "Default Sender"
~~~

JSON:

~~~json
{"mail":{"sender-name":null}}
~~~

Khi truy vấn property, Spring có thể tiếp tục lấy `Default Sender` từ file YAML. Điều này phù hợp với cách xử lý null của `PropertySourcesPropertyResolver`.

Nếu mục tiêu là làm rỗng tên người gửi, cần xem chuỗi rỗng có hợp lệ với nghiệp vụ hay không. Nếu mục tiêu tắt email, dùng `mail.enabled=false` và điều kiện ứng dụng tương ứng.

### 12.2. “Tôi đổi sang "null" thì property đã được override, nhưng app lỗi”

JSON:

~~~json
{"mail":{"timeout":"null"}}
~~~

Nếu Java cần `Duration`, `"null"` không phải một thời lượng hợp lệ. Việc override bằng chuỗi không có nghĩa bước binding sẽ chấp nhận nó. Hãy cung cấp một duration hợp lệ như `"3s"` hoặc tắt chức năng bằng property riêng.

### 12.3. “Tôi đặt object cha thành null để xóa cả cấu hình con”

JSON:

~~~json
{"datasourceSettings":null}
~~~

Nếu các key con được cung cấp bởi nguồn cấu hình khác, không có cơ chế xóa toàn bộ cây property chỉ bằng null ở object cha. Với cấu hình cần tách theo môi trường, hãy tổ chức lại các nguồn cấu hình, tránh đưa các giá trị không nên dùng vào nguồn luôn được nạp.

## 13. Một bộ tình huống tự thử

Bắt đầu với:

~~~yaml
# application.yml
demo:
  mode: "base"
  label: "base-label"
  enabled: true
  retries: 5
~~~

Có thể dùng `Environment#getProperty` để đọc các key không nhạy cảm. Thử từng giá trị JSON trong một lần khởi động riêng:

| JSON cung cấp | Giá trị dự kiến khi không có nguồn cao hơn |
| --- | --- |
| `{"demo":{"mode":null}}` | `demo.mode=base` |
| `{"demo":{"mode":"null"}}` | `demo.mode=null` dưới dạng chữ |
| `{"demo":{"mode":""}}` | `demo.mode` là chuỗi rỗng |
| `{"demo":{"enabled":false}}` | `demo.enabled=false` |
| `{"demo":{"retries":0}}` | `demo.retries=0` |
| `{"demo":{"label":"override"}}` | `demo.label=override` |
| `{"demo":{}}` | Các key gốc vẫn có thể được tìm thấy từ YAML |

Thử riêng trường hợp **bỏ cả key khỏi JSON**. Bạn sẽ thấy với một nguồn thấp hơn có giá trị, kết quả tra cứu giống trường hợp key bị đặt thành null: Spring vẫn dùng nguồn thấp hơn.

Nếu muốn làm rõ hơn, bỏ `demo.mode` khỏi `application.yml` rồi chạy với JSON null. Khi không có nguồn nào khác cung cấp key, `Environment#getProperty("demo.mode")` có thể trả null theo nghĩa **không tìm thấy property**. Đó không phải là một giá trị null có khả năng che nguồn khác.

## 14. Dữ liệu JSON null trong API không giống JSON null cấu hình

Trong ứng dụng, bạn cũng có thể gặp JSON null trong HTTP request/response:

~~~json
{
  "customerId": "C-001",
  "phoneNumber": null
}
~~~

Tùy thiết kế API và DTO, `phoneNumber: null` trong request có thể có ý nghĩa riêng, ví dụ muốn xóa số điện thoại của khách hàng trong một thao tác cập nhật. Ý nghĩa ấy do **hợp đồng API**, serializer, validation và logic nghiệp vụ quyết định.

Nhưng JSON ở `SPRING_APPLICATION_JSON` được Spring Boot dùng để tạo property source. Ở đây null không phải là “xóa property”. Không nên lấy ngữ nghĩa của một API PATCH hay quy ước update DTO áp vào externalized configuration.

Cùng là văn bản JSON, nhưng **hợp đồng của hệ thống xử lý JSON khác nhau**:

| Ngữ cảnh | Ai định nghĩa ý nghĩa null? |
| --- | --- |
| `SPRING_APPLICATION_JSON` | Spring Boot Config Data / property source resolution |
| HTTP JSON request | Hợp đồng API, serializer và logic nghiệp vụ |
| JSON Merge Patch | Đặc tả patch và cách server thực thi |
| Dữ liệu JSON lưu database | Schema và cách ứng dụng truy cập dữ liệu |

Vì vậy, khi hỏi “null có xóa được không?”, luôn phải xác định **ngữ cảnh** trước.

## 15. Quy ước thiết kế tránh lỗi

Một hệ thống dễ vận hành nên tuân theo các quy ước sau:

- **Đừng dùng null như một lệnh xóa** trong `SPRING_APPLICATION_JSON`. Nếu cần tắt một tính năng, biểu diễn bằng property có ý nghĩa như `enabled=false`.
- **Đặt giá trị mặc định có trách nhiệm.** Một endpoint production hoặc credential không nên nằm trong cấu hình chung chỉ để mọi môi trường “có cái mà dùng”.
- **Phân biệt vắng mặt với rỗng.** Chuỗi `""` là một giá trị nhưng chỉ phù hợp khi ứng dụng chấp nhận chuỗi rỗng.
- **Giữ kiểu nhất quán.** Đừng thay số, boolean, URL hay duration bằng `"null"` rồi mong Binder hiểu là không có dữ liệu.
- **Không coi object null là xóa nguyên cây property.** Các key con có thể tiếp tục đến từ nguồn thấp hơn.
- **Kiểm tra cấu hình hiệu lực ở đúng môi trường.** Ưu tiên nguồn, profile và command line đều có thể làm giá trị runtime khác với trực giác.
- **Thiết kế validation theo điều kiện sử dụng.** Feature bật thì các property cần thiết phải có và hợp lệ; feature tắt thì tránh khởi tạo dependency không cần thiết.
- **Tách cấu hình triển khai khỏi dữ liệu nghiệp vụ.** JSON trong biến môi trường phục vụ startup configuration, không phải cơ chế cập nhật đơn hàng hoặc hồ sơ khách hàng.

## 16. Kết luận bằng một quy tắc

Nếu `application.yml` có:

~~~yaml
app:
  mode: "normal"
~~~

thì:

~~~json
{"app":{"mode":null}}
~~~

**không xóa** `app.mode` và cũng không bảo đảm `@ConfigurationProperties` nhận null. Bộ phân giải property tiếp tục tìm nguồn có giá trị và có thể nhận `"normal"` từ YAML.

Ngược lại:

~~~json
{"app":{"mode":"maintenance"}}
~~~

cung cấp một giá trị thực để ghi đè. Nếu mong muốn là không chạy một thành phần, hãy dùng một cờ như `app.feature.enabled=false` và triển khai logic tương ứng. Nếu mong muốn là property thực sự vắng mặt, hãy sửa thiết kế nguồn cấu hình để nó không được cung cấp bởi các nguồn đang active.

**Nhớ công thức: JSON `null` là giá trị không dùng được để che property nguồn thấp hơn; JSON `"null"` là chuỗi; `false`, `0` và `""` là những giá trị khác null có thể override tùy kiểu đích.**