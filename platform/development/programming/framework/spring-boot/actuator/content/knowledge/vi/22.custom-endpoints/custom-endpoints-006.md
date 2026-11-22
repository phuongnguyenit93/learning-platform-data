# Nhận tham số truy vấn hoặc nội dung yêu cầu và kiểm soát tham số bắt buộc

Một operation của Actuator có thể nhận đầu vào từ phần truy vấn của URL hoặc các thuộc tính trong JSON body. Nhưng “có tham số trong chữ ký Java” chưa mô tả hết hợp đồng: cần biết tên nào được dùng để gắn dữ liệu, trường nào bắt buộc, trường nào cho phép thiếu, khi nào có chuyển đổi kiểu và phần nào phải tự kiểm tra theo nghiệp vụ.

Bài dùng Spring Boot 3.3.x, Spring MVC và Java 21. Ví dụ là endpoint xem trước đầu vào của một yêu cầu công việc: nó trả lại các giá trị đã nhận và giá trị mặc định, giúp quan sát cơ chế gắn tham số mà không thực thi công việc thật.

## 1. Hiểu đường đi của đầu vào

```text
Request HTTP
  → tìm operation phù hợp với đường dẫn và HTTP method
  → đọc query parameters và/hoặc JSON body
  → tìm giá trị theo tên tham số Java
  → kiểm tra tham số bắt buộc và chuyển đổi kiểu
  → gọi phương thức operation
  → mã của ứng dụng xử lý quy tắc nghiệp vụ
  → tạo phản hồi
```

Có ba câu hỏi riêng:

1. **Có đầu vào theo tên yêu cầu không?** Ví dụ operation cần `count` nhưng body chỉ có `amount`.
2. **Giá trị có chuyển sang kiểu Java được không?** Ví dụ `"many"` không chuyển thành `int`.
3. **Giá trị có hợp lệ với nghiệp vụ không?** Ví dụ `-1` chuyển được thành `int`, nhưng có thể không phải số lượng công việc được phép.

Tham số bắt buộc giải quyết câu hỏi về sự hiện diện, không tự thay thế mọi kiểm tra nghiệp vụ. Phần nhận đầu vào và chuyển kiểu được mô tả trong [tài liệu custom endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.input).

Khi công bố qua JMX, operation nhận tham số từ lời gọi MBean, không có query string hoặc HTTP body. Vì vậy, chữ ký của `@Endpoint` được thiết kế theo hợp đồng của Actuator, không mặc định giống chữ ký controller MVC.

## 2. Quy tắc đặt tên và dữ liệu gốc

### Query parameter được đối chiếu với tên tham số

Ví dụ chữ ký:

```java
@ReadOperation
public Map<String, Object> read(String name, @Nullable Integer limit)
```

Đây là chữ ký rút gọn; lớp hoàn chỉnh có ở phần 4. Request:

```http
GET /actuator/jobpreview?name=build&limit=3
```

cung cấp `name="build"` và giá trị `limit` được chuyển thành số nguyên `3`. Không cần thêm `@RequestParam` để có cách gắn đầu vào này.

Tên `name` không phải một thành phần đường dẫn trong ví dụ. Muốn lấy một giá trị từ đường dẫn, Actuator có `@Selector`; đó là một nguồn đầu vào khác, không phải lý do để tự thêm `/build` vào URL đang dùng.

### JSON được đối chiếu từ các thuộc tính ở cấp gốc

Với chữ ký:

```java
@WriteOperation
public Map<String, Object> write(String name, int count, @Nullable Boolean dryRun)
```

body phù hợp là:

```json
{
  "name": "build",
  "count": 2,
  "dryRun": false
}
```

Ba thuộc tính gốc tương ứng với ba tham số. Không cần bọc chúng trong một đối tượng `request`. Body sau có cấu trúc khác:

```json
{
  "request": {
    "name": "build",
    "count": 2
  }
}
```

Ở ví dụ này, nó không cung cấp các giá trị gốc `name` và `count` mà operation yêu cầu, nên bị từ chối vì thiếu tham số.

Không chuyển chữ ký thành một tham số DTO phức tạp rồi giả định Actuator sẽ xử lý như `@RequestBody` trong controller. Đầu vào operation dùng các kiểu đơn giản được hỗ trợ; đầu ra vẫn có thể là đối tượng hoặc `Map` để xuất JSON.

### Giữ tên tham số khi biên dịch

Actuator cần metadata tên tham số thực tế. Mã Java triển khai operation phải được biên dịch với `-parameters`; Spring Boot Gradle plugin và cấu hình Maven dùng `spring-boot-starter-parent` hỗ trợ việc này.

Nếu tự gọi `javac`, cờ cần có là `-parameters`. Nếu dùng build riêng, kiểm tra cấu hình của đúng tác vụ biên dịch và lớp đang chạy. Tên biến hiện trong mã nguồn hoặc IDE không bảo đảm metadata đã có trong class file.

Đổi tên `count` thành `amount` có thể đổi tên đầu vào được gắn vào operation. Hãy xem tên tham số là một phần hợp đồng của endpoint, không chỉ là chi tiết để làm mã đẹp hơn.

## 3. Bắt buộc, tùy chọn và giá trị mặc định

Một tham số operation mặc định là bắt buộc. Để cho phép thiếu, trong ví dụ Java này dùng `org.springframework.lang.Nullable`.

| Khai báo | Khi thiếu đầu vào | Điểm cần hiểu |
| --- | --- | --- |
| `String name` | Bị từ chối | Kiểu tham chiếu không tự làm tham số thành tùy chọn |
| `Integer limit` | Bị từ chối | Dùng wrapper chưa đủ để cho phép thiếu |
| `int count` | Bị từ chối | Không tự được điền `0` khi request thiếu trường |
| `@Nullable Integer limit` | Có thể nhận `null` | Mã ứng dụng tự chọn mặc định |
| `@Nullable Boolean dryRun` | Có thể nhận `null` | Cần giữ riêng giá trị `false` do người gọi gửi |

Nếu có khả năng nhận `null`, dùng kiểu tham chiếu như `Integer` hoặc `Boolean`, không dùng kiểu nguyên thủy `int` hoặc `boolean` để biểu diễn trạng thái ấy.

`@Nullable` không tự cung cấp giá trị mặc định. Chẳng hạn:

```java
int effectiveLimit = limit == null ? 10 : limit;
boolean effectiveDryRun = dryRun == null ? true : dryRun;
```

Đây là hai biểu thức trong ví dụ hoàn chỉnh, cho thấy mặc định là lựa chọn của ứng dụng. Giá trị `false` giữ nguyên; nó không bị coi là thiếu rồi thay bằng `true`.

Không suy ra rằng `Optional<T>` hoặc `@RequestParam(defaultValue = "...")` sẽ tự mang lại toàn bộ hành vi tương tự controller MVC. Với operation ở đây, hợp đồng tùy chọn được thể hiện rõ bằng `@Nullable` và phần xử lý mặc định.

## 4. Dự án thực hành hoàn chỉnh

### 4.1. Cấu hình build và endpoint

Chuẩn bị một dự án Gradle độc lập có Wrapper tương thích, ví dụ Gradle 8.5, và JDK 21.

`settings.gradle`:

```groovy
rootProject.name = 'actuator-input-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'demo'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`3.3.0` là mốc tái lập của ví dụ; trong dự án đã có, dùng bộ phiên bản 3.3.x đang được quản lý. BOM ở trên được đưa vào bằng cơ chế `platform` của Gradle.

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    jobpreview:
      enabled: true
  endpoints:
    web:
      exposure:
        include: jobpreview
```

Đây là cấu hình công bố riêng endpoint thực hành trên máy cục bộ. Nếu bổ sung Spring Security, request còn phải đi qua chính sách bảo vệ của ứng dụng; lỗi xác thực/phân quyền cần được phân biệt với lỗi gắn tham số.

### 4.2. Lớp khởi động

Tạo `src/main/java/demo/InputApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputApplication.class, args);
    }
}
```

### 4.3. Endpoint nhận đầu vào

Tạo `src/main/java/demo/JobPreviewEndpoint.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.lang.Nullable;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "jobpreview")
public class JobPreviewEndpoint {
    @ReadOperation
    public Map<String, Object> read(String name, @Nullable Integer limit) {
        int effectiveLimit = limit == null ? 10 : limit;
        return Map.of("name", name, "limit", effectiveLimit);
    }

    @WriteOperation
    public Map<String, Object> write(
            String name, int count, @Nullable Boolean dryRun) {
        boolean effectiveDryRun = dryRun == null ? true : dryRun;
        return Map.of("name", name, "count", count, "dryRun", effectiveDryRun);
    }
}
```

Trong lớp này:

- GET yêu cầu `name`; `limit` tùy chọn và mặc định là `10`.
- POST yêu cầu `name` và `count`; `dryRun` tùy chọn và mặc định là `true`.
- Mỗi operation chỉ tạo một bản xem trước từ dữ liệu đầu vào. Không có thao tác lưu hoặc thực thi công việc.
- Mã chưa đặt quy tắc như tên phải có chữ hoặc số lượng phải dương, để có thể quan sát rõ sự khác nhau giữa gắn tham số và kiểm tra nghiệp vụ.

Đầu ra dùng `Map`, vì vậy thứ tự các thuộc tính JSON có thể thay đổi. Khi đối chiếu kết quả, so sánh tên và giá trị trường, không dựa vào thứ tự ký tự của các thuộc tính.

### 4.4. Khởi động

Trên Linux/macOS:

```bash
./gradlew bootRun
```

Trên PowerShell/Windows:

```powershell
.\gradlew.bat bootRun
```

Có thể đóng tiến trình `bootRun`, đóng gói bằng `./gradlew bootJar` hoặc `.\gradlew.bat bootJar`, rồi chạy:

```bash
java -jar build/libs/actuator-input-demo-1.0.0.jar
```

Log khởi động thay đổi theo môi trường. Các ví dụ tiếp theo tập trung vào status và JSON phản hồi của operation.

## 5. Gửi query parameter

Các lệnh curl trong bài dùng cú pháp Bash.

### Có tham số bắt buộc, bỏ tham số tùy chọn

```bash
curl -i -H "Accept: application/json" "http://localhost:8080/actuator/jobpreview?name=build"
```

Kết quả là `200 OK` với dữ liệu:

```json
{"name":"build","limit":10}
```

`limit=10` do biểu thức mặc định trong phương thức `read`, không phải Actuator tự suy ra.

### Cung cấp tham số tùy chọn

```bash
curl -i -H "Accept: application/json" "http://localhost:8080/actuator/jobpreview?name=build&limit=3"
```

Kết quả `200`:

```json
{"name":"build","limit":3}
```

Query parameter đi qua URL dưới dạng văn bản; Actuator chuyển `"3"` thành `Integer`.

### Mã hóa giá trị có khoảng trắng hoặc ký tự đặc biệt

```bash
curl -i --get -H "Accept: application/json" --data-urlencode "name=nightly build" --data-urlencode "limit=3" http://localhost:8080/actuator/jobpreview
```

Dữ liệu phản hồi chứa `name="nightly build"`. Dùng mã hóa URL phù hợp thay vì tự nối một giá trị có `&`, `+`, dấu cách hoặc ký tự đặc biệt vào query string rồi mong nó giữ nguyên ý nghĩa.

### Thiếu hoặc sai kiểu

```bash
curl -i http://localhost:8080/actuator/jobpreview
curl -i "http://localhost:8080/actuator/jobpreview?name=build&limit=many"
```

Cả hai ca nhận `400 Bad Request`, nhưng lý do khác nhau:

- Ca đầu thiếu `name`, một tham số bắt buộc.
- Ca sau có `limit` nhưng không chuyển được `"many"` thành số nguyên.

Tùy chọn không có nghĩa là bỏ qua giá trị sai kiểu. `@Nullable Integer limit` cho phép thiếu, không làm mọi chuỗi đều hợp lệ.

## 6. Gửi JSON body

### Cung cấp các trường bắt buộc

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"build","count":2}' http://localhost:8080/actuator/jobpreview
```

Kết quả `200` có dữ liệu:

```json
{"name":"build","count":2,"dryRun":true}
```

### Giữ đúng giá trị false

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"build","count":2,"dryRun":false}' http://localhost:8080/actuator/jobpreview
```

Dữ liệu phản hồi có `dryRun=false`. Chỉ kiểm tra `null` khi chọn mặc định giúp giữ nguyên lựa chọn rõ ràng của người gọi.

### Phân biệt Content-Type và Accept

- `Content-Type: application/json` mô tả định dạng body gửi đến.
- `Accept: application/json` mô tả định dạng phản hồi người gọi muốn nhận.

Thêm `Accept` không làm một body `text/plain` trở thành JSON hợp lệ cho operation. Với ví dụ này, gửi JSON dưới content type `text/plain` nhận `415 Unsupported Media Type`; JSON sai cú pháp dưới content type JSON nhận `400`.

Khi có nhiều operation hoặc cấu hình khác, hãy kiểm tra điều kiện ánh xạ và phản hồi thực tế. Không gộp mọi lỗi request thành “thiếu tham số”.

### Gọi từ PowerShell

Có thể dùng các công cụ PowerShell để tránh khác biệt về dấu nháy khi truyền JSON cho chương trình native:

```powershell
$previewUri = 'http://localhost:8080/actuator/jobpreview'

Invoke-RestMethod -Method Get -Uri "$($previewUri)?name=build&limit=3"

$previewBody = @{
    name = 'build'
    count = 2
    dryRun = $false
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri $previewUri -ContentType 'application/json' -Body $previewBody
```

Kết quả được chuyển thành đối tượng PowerShell nên cách hiển thị khác chuỗi JSON nguyên bản. Những ca HTTP 4xx có thể xuất hiện dưới dạng lỗi của lệnh gọi, không phải dấu hiệu ứng dụng đã dừng.


## 7. Phân biệt thiếu, null, rỗng, 0 và false

Các kết quả sau áp dụng cho endpoint của bài, với những tham số bắt buộc còn lại đã được cung cấp đúng.

| Giá trị gửi đến | Kết quả của ví dụ | Điều nó chứng minh |
| --- | --- | --- |
| Không có `name` | `400` | Tham số bắt buộc chưa được cung cấp |
| JSON `"name": null` | `400` | `null` không thỏa yêu cầu của tham số bắt buộc |
| `name=` trong query hoặc JSON `"name": ""` | `200`, giữ chuỗi rỗng | Bắt buộc không đồng nghĩa không rỗng |
| Tên chỉ có dấu cách | `200`, giữ các dấu cách | Bắt buộc không tự kiểm tra `isBlank()` |
| Không có `count` | `400` | `int` không tự nhận `0` khi request thiếu |
| JSON `"count": null` | `400` | Giá trị null không dùng được cho `count` bắt buộc |
| JSON `"count": 0` | `200`, `count=0` | Có giá trị số, chưa có quy tắc phải dương |
| JSON `"count": -1` | `200`, `count=-1` | Số âm vẫn chuyển được sang `int` |
| JSON `"count": "2"` | `200`, `count=2` | Cơ chế chuyển kiểu chấp nhận chuỗi số trong trường hợp này |
| JSON `"count": "many"` | `400` | Không chuyển được thành số nguyên |
| JSON `"count": 2147483648` | `400` | Giá trị vượt phạm vi của `int` |
| Thiếu `dryRun` hoặc JSON `"dryRun": null` | `200`, `dryRun=true` | Mã ứng dụng dùng mặc định khi nhận null |
| JSON `"dryRun": false` | `200`, `dryRun=false` | False là giá trị rõ ràng, không phải thiếu |
| JSON `"dryRun": "maybe"` | `400` | Tham số tùy chọn vẫn phải chuyển kiểu được |

Hai request ngắn để tự kiểm tra:

```bash
curl -i -X POST -H "Content-Type: application/json" -d '{"name":"","count":0,"dryRun":false}' http://localhost:8080/actuator/jobpreview
curl -i -X POST -H "Content-Type: application/json" -d '{"name":"build","count":null}' http://localhost:8080/actuator/jobpreview
```

Request đầu được chấp nhận ở tầng gắn tham số của ví dụ. Request sau bị từ chối vì `count` không thể nhận null theo hợp đồng hiện tại.

### Không dùng required để thay thế kiểm tra nghiệp vụ

Nếu hợp đồng nghiệp vụ yêu cầu tên phải có chữ và số lượng phải lớn hơn không, cần kiểm tra thêm `name.isBlank()` và giới hạn của `count` trước khi thực hiện công việc. Có đầu vào, chuyển được kiểu và được phép thực hiện là các điều kiện khác nhau.

Tương tự, tham số `limit` cần giới hạn trên nếu sau này được dùng để đọc nhiều dữ liệu. Việc chuyển được một số rất lớn sang `Integer` chưa chứng minh số đó phù hợp với năng lực hệ thống.

Không giả định thêm `@Valid`, `@NotBlank` hoặc `@Min` vào chữ ký là đủ để nhận đúng toàn bộ hành vi validation của controller MVC. Nếu dùng Bean Validation, phải có cơ chế gọi validator phù hợp và kiểm tra nó thực sự chạy.

### Nullable không luôn giữ được ý định ban đầu

Ở ví dụ này, bỏ hẳn `dryRun` và gửi `"dryRun": null` đều làm phương thức nhận `null`, rồi chọn `true`.

Nếu một API cần phân biệt “không gửi thì giữ nguyên” với “gửi null thì đặt lại”, không thể dùng cùng một giá trị null trong chữ ký này để tự suy ra cả hai ý định. Hãy thiết kế hợp đồng thể hiện ý định rõ ràng và kiểm tra riêng các trường hợp đó.

## 8. Sai tên, cấu trúc lồng và tham số không được sử dụng

### Tên tham số cần khớp chính xác

Gửi `amount` thay cho `count` không tự tạo ra một bí danh cho tham số Java. Nếu không có giá trị `count`, request vẫn thiếu tham số bắt buộc.

Sai tên trường tùy chọn còn dễ bị bỏ sót hơn. Request:

```json
{
  "name": "build",
  "count": 2,
  "dryrun": false
}
```

dùng `dryrun` thay vì `dryRun`. Với bộ xử lý của ví dụ Spring MVC/Boot 3.3.0, trường không khớp này không được gắn vào `dryRun`; phương thức nhận null và trả giá trị mặc định `true`.

Điều đó có nghĩa request có thể nhận `200` nhưng không mang ý nghĩa người gọi tưởng là đã gửi. Không dùng “không có lỗi HTTP” làm bằng chứng duy nhất rằng mọi trường đã được sử dụng.

### JSON lồng không tự được trải phẳng

Body `{"request":{"name":"build","count":2}}` không tương đương `{"name":"build","count":2}`. Cấu trúc đầu tiên thiếu các trường gốc cần cho chữ ký hiện tại.

Nếu cần mô hình đầu vào có cấu trúc phức tạp và hợp đồng JSON nghiêm ngặt, hãy chọn thiết kế phù hợp thay vì mặc định áp dụng cơ chế DTO của MVC cho operation không phụ thuộc công nghệ.

### Chuyển kiểu không phải kiểm tra JSON theo một schema nghiêm ngặt

Ví dụ đã chấp nhận cả số JSON `2` lẫn chuỗi JSON `"2"` cho `count`. Đây là kết quả chuyển đổi sang kiểu đích, không phải lời hứa rằng body phải có đúng một kiểu JSON duy nhất.

Khi cần định dạng đầu vào chặt hơn, phải quy định và kiểm tra điều đó. Đối với chuyển đổi tùy chỉnh của Actuator, có thể sử dụng converter phù hợp với cơ chế `@EndpointConverter`; không coi một converter là sự thay thế cho tất cả quy tắc kiểm tra đầu vào.

## 9. Khi query và JSON cùng chứa một tên

Không nên thiết kế người gọi gửi cùng một tham số ở cả hai nơi rồi dựa vào phỏng đoán về thứ tự ưu tiên.

Với ví dụ chạy Spring MVC trên Boot 3.3.0, trường hợp sau được gắn theo giá trị query:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"body","count":2}' "http://localhost:8080/actuator/jobpreview?name=query&count=9"
```

Dữ liệu phản hồi là:

```json
{"name":"query","count":9,"dryRun":true}
```

Đây là hành vi của bộ xử lý đã nêu, không phải quy tắc để tự suy ra cho mọi web stack, mọi phiên bản hay mọi bộ xử lý tùy chỉnh. Hợp đồng sử dụng tốt hơn là chọn nguồn rõ ràng cho từng tham số và tránh cung cấp giá trị xung đột.

POST của ví dụ cũng có thể nhận các giá trị từ query. Khi thử, giữ content type phù hợp với điều kiện ánh xạ operation:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" "http://localhost:8080/actuator/jobpreview?name=query&count=4&dryRun=false"
```

Trong cấu hình Spring MVC của bài, request này trả `200` với `name=query`, `count=4`, `dryRun=false`. Dù vậy, chọn JSON body cho các đầu vào POST trong ví dụ giúp hợp đồng dễ đọc và kiểm tra hơn.

## 10. Chẩn đoán và kiểm tra đúng tầng

| Hiện tượng | Tầng cần kiểm tra trước |
| --- | --- |
| `400` do thiếu đầu vào | Tên tham số, thuộc tính gốc JSON, dấu `@Nullable` và giá trị null |
| `400` do sai giá trị | Kiểu đích, giá trị có chuyển được không, giới hạn kiểu số |
| `400` với JSON bị cắt hoặc sai cú pháp | Bộ đọc JSON, trước khi vào phương thức operation |
| `415` | Content type của request và điều kiện consumes |
| `404` | Đường dẫn, endpoint ID, enablement và exposure |
| `401` hoặc `403` | Cấu hình bảo vệ request, trước khi quy lỗi cho tham số |
| Lỗi liên quan tên tham số khi khám phá endpoint | Metadata biên dịch, đặc biệt `-parameters` |
| Request thành công nhưng dùng giá trị mặc định ngoài ý muốn | Tên trường tùy chọn, chữ hoa/thường và nguồn query/body |
| Ngoại lệ từ thân operation | Logic ứng dụng và cách ánh xạ lỗi, không phải chỉ required/type conversion |

Khi thiếu tham số bắt buộc hoặc không chuyển được sang kiểu cần thiết, Actuator từ chối trước khi gọi operation. Ngược lại, một ngoại lệ nghiệp vụ do chính phương thức ném ra không tự trở thành cùng loại lỗi chuyển tham số. Nếu muốn phản hồi `400` cho quy tắc nghiệp vụ, hãy triển khai cách biểu diễn/ánh xạ lỗi phù hợp ở tầng web và kiểm chứng nó; đừng mặc định mọi `IllegalArgumentException` đều thành `400`.

Một phép thử Java gọi trực tiếp:

```java
new JobPreviewEndpoint().write("build", 2, null);
```

chỉ kiểm tra phương thức chọn mặc định và tạo kết quả thế nào. Nó không kiểm tra việc lấy query, đọc JSON, phát hiện thiếu trường hoặc chọn mã HTTP. Muốn kiểm chứng hợp đồng nhận request, cần kiểm tra qua bộ xử lý web, chẳng hạn MockMvc với application context có Actuator, hoặc một ứng dụng đang chạy.

Các nhóm ca nên có khi kiểm tra endpoint này:

1. Query đầy đủ, query thiếu bắt buộc và query sai kiểu.
2. JSON đầy đủ, JSON thiếu trường và JSON null.
3. Giá trị tùy chọn được bỏ qua và được gửi rõ ràng.
4. Giá trị `false`/`0`, chuỗi rỗng và chuỗi chỉ có dấu cách.
5. Sai tên trường, cấu trúc lồng không phù hợp và JSON sai cú pháp.
6. Content type sai và đầu vào xung đột nếu hệ thống có thể gặp chúng.

Đối chiếu JSON theo dữ liệu, không theo thứ tự thuộc tính. Với lỗi framework, chỉ kiểm tra những phần hợp đồng thực sự cần thiết thay vì sao chép nguyên body lỗi có thể thay đổi theo cấu hình.

## 11. Tự kiểm tra khả năng giải thích

### Bài tập 1: wrapper có làm tham số tùy chọn không?

Đổi `@Nullable Integer limit` thành `Integer limit`, biên dịch lại rồi GET chỉ có `name`.

Kết quả cần giải thích: request bị thiếu `limit`. Khả năng một biến Java giữ null không đồng nghĩa hợp đồng operation cho phép bỏ tham số.

### Bài tập 2: mặc định có thay thế giá trị false không?

Giữ nguyên mã, lần lượt bỏ `dryRun`, gửi null và gửi false.

Kết quả: hai ca đầu dùng `true`; ca cuối giữ `false`. Hãy chỉ ra biểu thức chọn mặc định trong phương thức, thay vì gán hành vi ấy cho annotation.

### Bài tập 3: vì sao count=-1 không bị lỗi chuyển kiểu?

Gửi `count=-1` và `count="many"`.

Kết quả: số âm là giá trị `int` hợp lệ ở tầng chuyển kiểu của ví dụ; chuỗi `"many"` thì không. Sau đó thiết kế thêm quy tắc nghiệp vụ yêu cầu số lượng dương, cùng cách phản hồi lỗi rõ ràng.

### Bài tập 4: phát hiện lỗi âm thầm ở trường tùy chọn

Gửi `dryrun=false` rồi `dryRun=false`, giữ các trường khác đúng.

So sánh dữ liệu phản hồi để thấy request thành công không bảo đảm tên trường đã khớp. Khi thay đổi tên tham số trong mã, phải xem xét cả người gọi và các ca kiểm tra hợp đồng.

### Bài tập 5: chọn một nguồn đầu vào rõ ràng

Tạo hai request tương đương: một POST chỉ dùng JSON và một POST chỉ dùng query theo cấu hình của bài. Sau đó tạo một request có giá trị xung đột ở cả hai nơi.

Giải thích được kết quả thực tế, rồi quy định cách dùng endpoint để người gọi không phụ thuộc vào sự xung đột ấy.
