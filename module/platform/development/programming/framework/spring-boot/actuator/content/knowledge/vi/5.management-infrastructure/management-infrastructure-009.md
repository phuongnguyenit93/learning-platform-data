# Phân biệt tắt giao tiếp HTTP quản trị với tắt toàn bộ endpoint

## 1. Cần tắt điều gì?

Một ứng dụng có thể vừa phục vụ API nghiệp vụ, vừa cung cấp khả năng kiểm tra sức khỏe hoặc xem thông tin vận hành bằng Spring Boot Actuator. Khi nói “tắt Actuator”, cần xác định chính xác mục tiêu:

- **Ngừng truy cập Actuator qua HTTP:** không gọi được các đường dẫn quản trị, nhưng vẫn có thể giữ kênh JMX.
- **Không công bố endpoint trên một kênh:** lựa chọn tập endpoint được đưa ra HTTP hoặc JMX.
- **Vô hiệu hóa endpoint:** không cho endpoint đó tham gia cơ chế Actuator, thay vì chỉ thay đổi kênh truy cập.

Ví dụ, yêu cầu “API đặt hàng tiếp tục hoạt động, không có URL Actuator, quản trị viên vẫn xem sức khỏe bằng JMX” khác với “không sử dụng bất kỳ endpoint Actuator nào”. Chọn nhầm cấu hình có thể làm mất công cụ chẩn đoán cần giữ, hoặc để lại kênh quản trị ngoài dự kiến.

Bài này dùng **Spring Boot 3.3.x**, với cơ chế `enabled` của phiên bản này. Các ví dụ khởi động lại ứng dụng sau khi đổi cấu hình; việc sửa tệp YAML không tự thay đổi máy chủ hoặc dựng lại endpoint trong tiến trình đang chạy.

## 2. Mô hình: endpoint, kênh truy cập và quyền truy cập

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Endpoint Actuator | Khả năng quản trị nào được cung cấp? | `health`, `info` |
| Trạng thái bật/tắt | Endpoint có được phép hoạt động theo cấu hình? | `management.endpoint.health.enabled` |
| Công bố (exposure) | Endpoint được đưa ra kênh nào? | `management.endpoints.web.exposure.include` |
| Hạ tầng HTTP quản trị | Có phục vụ endpoint Actuator qua HTTP không? | `management.server.port` |
| Xác thực, phân quyền | Người đang gọi có quyền sử dụng không? | Quy tắc Spring Security cho HTTP |

Một cách suy luận khi kiểm tra đường gọi HTTP là:

```text
Endpoint đủ điều kiện hoạt động
  + được bật
  + được công bố qua web
  + HTTP quản trị hoạt động và URL đúng
  + yêu cầu vượt qua kiểm soát truy cập nếu có
  → có thể gọi operation của endpoint qua HTTP
```

Đây là mô hình kiểm tra điều kiện, không phải sơ đồ thứ tự tạo bean.

**Bật không đồng nghĩa với công bố; công bố không đồng nghĩa với cho phép mọi người gọi.** Trong Spring Boot 3.3, mặc định các endpoint tích hợp được bật trừ `shutdown`; tập công bố HTTP/JMX mặc định chỉ có `health`. Một số endpoint còn cần thư viện hoặc bean bổ sung. Không thể suy ra rằng tất cả endpoint đều truy cập được chỉ vì đã thêm starter Actuator. [Tài liệu endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Cũng cần phân biệt “không đổi cờ enabled” với “chắc chắn bean còn tồn tại”. Cấu hình tự động của nhiều endpoint kiểm tra cả trạng thái bật lẫn khả năng công bố. Khi không còn kênh nào phù hợp, endpoint có thể không được cấu hình tự động. Bean tự khai báo cần được xem theo điều kiện đăng ký riêng của nó. [Điều kiện tạo endpoint trong Spring Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 3. Tắt giao tiếp HTTP quản trị

### 3.1. Dùng management.server.port=-1

```yaml
server:
  port: 8080

management:
  server:
    port: -1
```

Cấu hình này ngừng phục vụ endpoint Actuator qua HTTP. API nghiệp vụ trên cổng 8080 vẫn có thể hoạt động bình thường.

Không có ý nghĩa “máy chủ lắng nghe cổng âm”, cũng không phải chỉ xóa một cổng quản trị riêng rồi tự đưa Actuator về cổng ứng dụng. `-1` là giá trị cấu hình dùng để tắt HTTP quản trị. Không dùng `server.port=-1` thay thế: `server.port` điều khiển máy chủ web chính, ảnh hưởng cả API nghiệp vụ.

Nếu trước đó dùng `management.server.port=8081`, chuyển thành `-1` sẽ không còn cung cấp HTTP Actuator ở 8081; đồng thời không vì thế mà xuất hiện lại `/actuator/health` ở 8080. Chỉ đổi cổng từ 8081 về 8080 thì vẫn đang cung cấp HTTP Actuator, không phải tắt.

### 3.2. Dùng web.exposure.exclude để không công bố endpoint qua HTTP

Một lựa chọn khác:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

Đây là chính sách công bố web: loại tất cả endpoint khỏi kênh HTTP. Nó không đặt `enabled=false` cho từng endpoint, không thay đổi tập công bố JMX và không phải chỉ thị đóng máy chủ web.

Nếu cấu hình sẵn cổng quản trị riêng, đừng dùng `exclude: "*"` để kết luận cổng đó đã được đóng. Khi mục tiêu có cả việc ngừng hạ tầng HTTP quản trị, chọn `management.server.port=-1`.

Cả hai cách đều được tài liệu Spring Boot mô tả để ngừng công bố endpoint qua HTTP. [Cấu hình HTTP quản trị của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

Trong YAML phải viết `"*"` có dấu nháy. Ví dụ sau cũng **không** cho phép `health` đi qua:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
        exclude: "*"
```

`exclude` được ưu tiên hơn `include`. Muốn chỉ giữ `health`, phải bỏ quy tắc loại toàn bộ rồi đặt danh sách `include` phù hợp.

### 3.3. Giữ JMX khi HTTP đã tắt

```yaml
server:
  port: 8080

spring:
  jmx:
    enabled: true

management:
  server:
    port: -1
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
  endpoints:
    jmx:
      exposure:
        include: health,info
```

Với ứng dụng có starter Actuator và các điều kiện cấu hình tự động phù hợp, `health` và `info` được đưa ra JMX trong khi HTTP quản trị bị tắt.

Spring Boot không bật hỗ trợ JMX của Spring theo mặc định; vì vậy ví dụ đặt rõ `spring.jmx.enabled=true`. MBean của health thường có tên `org.springframework.boot:type=Endpoint,name=Health` nếu không đổi domain hoặc cách đặt tên. Có thể dùng JConsole gắn vào JVM cục bộ để kiểm tra. Việc này không tự cấu hình một cổng JMX từ xa; truy cập từ xa là thiết lập riêng. [Quản trị qua JMX trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Điểm kiểm chứng quan trọng là **HTTP không truy cập được nhưng MBean health vẫn hiện diện**. Chỉ thử một URL không đủ để chứng minh toàn bộ khả năng quản trị đã bị tắt.

## 4. Vô hiệu hóa endpoint

### 4.1. Tắt một endpoint trên các kênh Actuator

```yaml
management:
  endpoint:
    health:
      enabled: false
```

Khi health bị vô hiệu hóa, thêm `health` vào danh sách công bố web hoặc JMX cũng không bật lại nó. Danh sách công bố chỉ chọn endpoint đủ điều kiện, không thay thế cờ `enabled`.

Lưu ý tên thuộc tính:

- `management.endpoint.<id>.enabled`: **endpoint** số ít, cấu hình một ID.
- `management.endpoints.enabled-by-default`: **endpoints** số nhiều, cấu hình mặc định chung.

Không có quy tắc wildcard được sử dụng ở đây dưới dạng `management.endpoint.*.enabled=false`.

### 4.2. Đặt mặc định tắt mọi endpoint

```yaml
management:
  endpoints:
    enabled-by-default: false
```

Đây là cơ chế **chỉ bật khi chọn rõ**. Với các endpoint tuân theo cấu hình Actuator, endpoint không có cấu hình riêng sẽ nhận mặc định tắt. Tuy nhiên, câu sau vẫn là một ngoại lệ hợp lệ:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

Kết quả là health được bật và được chọn công bố qua web; các endpoint khác tiếp tục theo mặc định tắt. Vì vậy, chỉ nhìn thấy `enabled-by-default=false` chưa đủ để xác nhận mọi endpoint thực tế đều tắt. Phải kiểm tra cấu hình hiệu lực của từng `management.endpoint.<id>.enabled`, gồm cấu hình theo môi trường và tham số khởi động.

Muốn vô hiệu hóa toàn bộ endpoint theo cơ chế này:

1. Đặt `management.endpoints.enabled-by-default=false`.
2. Gỡ hoặc đặt `false` mọi cấu hình bật riêng đang có hiệu lực.
3. Kiểm tra cả endpoint tự khai báo và điều kiện đăng ký của chúng; không suy rộng rằng mọi bean do ứng dụng tự tạo sẽ bị xóa.
4. Khởi động lại và xác minh những kênh trước đó đã sử dụng.

Tắt endpoint không đồng nghĩa với đóng cổng web chính, xóa controller nghiệp vụ hoặc kết thúc JVM.

### 4.3. Giấu cả HTTP lẫn JMX là một yêu cầu khác

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
    jmx:
      exposure:
        exclude: "*"
```

Hai chính sách này không công bố endpoint qua hai kênh tương ứng. Chúng diễn đạt quyết định về **kênh truy cập**, thay vì thay đổi mặc định bật/tắt endpoint. Không được dựa vào tên cấu hình này để khẳng định mọi đối tượng endpoint vẫn được tạo; điều kiện cấu hình tự động vẫn có thể làm chúng không hiện diện.

Tương tự, `spring.jmx.enabled=false` là quyết định về hỗ trợ JMX của Spring, không phải lệnh tắt HTTP Actuator và cũng không phải lệnh tắt mọi MBean của JVM hoặc thư viện khác.

## 5. Thí nghiệm: cùng một ứng dụng, các kết quả khác nhau

### 5.1. Chuẩn bị ứng dụng tối thiểu

Dùng JDK 21, Spring Boot **3.3.0**, Gradle Wrapper 8.5. Thí nghiệm độc lập này cần hai dependency:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đây là phần dependency của dự án đã có plugin Java và Spring Boot 3.3.0, không phải toàn bộ `build.gradle`. Không thêm Spring Security, cấu hình bảo mật tùy chỉnh, cơ sở dữ liệu hoặc dependency ứng dụng khác vào thí nghiệm; chúng có thể làm kết quả khác.

Tệp `src/main/java/example/ActuatorToggleApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorToggleApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorToggleApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

Dùng `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  jmx:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info
```

Bắt đầu bằng trạng thái này, chưa thêm bất kỳ cờ tắt endpoint nào. Trong PowerShell, chạy tại thư mục dự án:

```powershell
.\gradlew.bat bootRun
```

Trong Bash, lệnh tương ứng là `./gradlew bootRun`. Đây là ứng dụng cần thư viện Spring, nên dùng quy trình build của dự án thay vì gọi `javac` trực tiếp mà thiếu classpath.

### 5.2. Kiểm tra trạng thái ban đầu

Mở terminal PowerShell khác:

```powershell
curl.exe -s http://localhost:8080/ping
```

Nội dung phản hồi:

```text
pong
```

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

Khi ứng dụng tối thiểu khỏe mạnh, kết quả:

```text
200
```

Nội dung health mặc định trong điều kiện đó là `{"status":"UP"}`. Không dùng HTTP 200 làm quy luật cho mọi ứng dụng: các thành phần kiểm tra sức khỏe bổ sung có thể báo trạng thái khác.

Trong JConsole, chọn đúng JVM, mở thẻ MBeans và tìm `org.springframework.boot → Endpoint → Health`. Có thể gọi operation `health` để quan sát kết quả. Tên hiển thị có thể khác nếu đã tùy chỉnh cấu hình đặt tên MBean.

### 5.3. Thử từng biến thể độc lập

Mỗi lần chỉ thêm cấu hình của **một hàng** bên dưới vào trạng thái ban đầu, khởi động lại rồi kiểm tra. Trước biến thể tiếp theo phải gỡ phần cấu hình vừa thêm. Dấu chấm trong bảng thể hiện tên thuộc tính đầy đủ.

| Biến thể thêm vào trạng thái ban đầu | GET /ping | GET /actuator/health trên 8080 | MBean Health |
| --- | --- | --- | --- |
| Không thêm gì | 200, thân `pong` | 200 nếu khỏe mạnh | Có |
| `management.server.port=-1` | 200, thân `pong` | 404 | Có |
| `management.endpoints.web.exposure.exclude=*` | 200, thân `pong` | 404 | Có |
| `management.endpoints.enabled-by-default=false` | 200, thân `pong` | 404 | Không |
| Mặc định tắt, đồng thời `management.endpoint.health.enabled=true` | 200, thân `pong` | 200 nếu khỏe mạnh | Có |
| `management.endpoint.health.enabled=false` | 200, thân `pong` | 404 | Không |
| Loại `*` khỏi cả web và JMX | 200, thân `pong` | 404 | Không |

Các kết quả trên dành cho ứng dụng tối thiểu, dùng đường dẫn mặc định, không có bộ lọc bảo mật hoặc controller tự ánh xạ vào `/actuator/health`. “Không có MBean Health” chỉ nói đến endpoint health của Actuator trong thí nghiệm, không nói rằng JVM không còn MBean nào.

Khi thêm YAML, gộp vào các nhánh `management`, `endpoints`, `endpoint` hiện có; không tạo khóa gốc trùng nhau. Nếu thử file `.properties`, viết `exclude=*`; nếu thử YAML, viết `exclude: "*"`.

Có thể kiểm tra mã trạng thái của API nghiệp vụ bằng:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/ping
```

Với mọi biến thể trong bảng, kết quả vẫn là:

```text
200
```

Bảng cho thấy cùng một HTTP 404 ở health có thể xuất phát từ nhiều nguyên nhân. Sự hiện diện của JMX và cấu hình bật/tắt mới giúp phân biệt chúng.

## 6. Những kết luận dễ sai khi vận hành

### Chỉ thấy 404 rồi kết luận endpoint bị vô hiệu hóa

404 có thể do endpoint không được công bố, HTTP quản trị bị tắt, sai cổng, sai tiền tố URL hoặc endpoint bị tắt. Lỗi kết nối còn có thể do không có máy chủ lắng nghe hoặc vấn đề mạng.

401/403 liên quan đến kiểm soát truy cập; các bộ lọc có thể phản hồi trước cả khi tìm được handler. Vì vậy, chúng cũng không chứng minh endpoint được bật hay tắt. Kiểm tra cấu hình hiệu lực, đường dẫn/cổng và kênh JMX nếu có, thay vì đoán từ một mã phản hồi.

### Tắt trang khám phá rồi cho rằng mọi endpoint đều tắt

```yaml
management:
  endpoints:
    web:
      discovery:
        enabled: false
```

Cấu hình này điều khiển trang liên kết khám phá. Trong thí nghiệm ban đầu, `/actuator/health` vẫn truy cập được. Tắt một trang liệt kê không đồng nghĩa với vô hiệu hóa những operation được liệt kê.

### Tắt endpoint rồi cho rằng mọi dữ liệu giám sát đều ngừng

Endpoint `metrics` là một cách truy vấn số liệu. Việc thu thập số liệu và xuất dữ liệu qua Micrometer còn có cấu hình riêng. Tắt endpoint hoặc HTTP Actuator không tự đồng nghĩa với tắt toàn bộ cơ chế đo đạc, nhật ký, truy vết hay bộ xuất số liệu. [Cấu hình số liệu của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Ví dụ suy luận: hệ thống đẩy số liệu ra ngoài có thể không cần URL `/actuator/metrics`; ngược lại, hệ thống đang kéo số liệu từ một endpoint HTTP sẽ mất đường kéo đó khi HTTP quản trị bị tắt.

### Quên những thành phần đang gọi health

Nếu bộ cân bằng tải hoặc cơ chế kiểm tra tiến trình đang gọi health qua HTTP, tắt đường gọi này sẽ làm phép kiểm tra thất bại dù `/ping` vẫn trả lời. Trước khi đổi cấu hình, xác định bên nào đang gọi, URL/cổng nào được dùng và cơ chế thay thế.

Tình huống thực hành: yêu cầu “chỉ giữ health qua HTTP cho bộ cân bằng tải” phù hợp với danh sách công bố web tối thiểu. Yêu cầu “chỉ cho quản trị viên gắn JConsole cục bộ, không có HTTP Actuator” phù hợp với tắt HTTP quản trị và giữ JMX có chủ đích.

## 7. Tự kiểm tra cách chọn cấu hình

**Tình huống 1:** API nghiệp vụ phải hoạt động; quản trị viên vẫn cần JMX; không có HTTP Actuator.

Chọn `management.server.port=-1`, đồng thời bật JMX và công bố rõ những endpoint cần giữ. Không dùng mặc định tắt mọi endpoint nếu vẫn muốn sử dụng chúng qua JMX.

**Tình huống 2:** Muốn giữ HTTP health nhưng không sử dụng các endpoint còn lại.

Đặt `management.endpoints.enabled-by-default=false`, bật riêng `management.endpoint.health.enabled=true` và chọn `health` trong danh sách công bố web. Kiểm tra không còn cấu hình bật riêng endpoint khác.

**Tình huống 3:** Đã đặt `enabled-by-default=false` nhưng health vẫn gọi được.

Tìm cấu hình hiệu lực `management.endpoint.health.enabled=true`, kể cả tham số khởi động hoặc cấu hình theo môi trường. Nếu endpoint vẫn đủ điều kiện và được công bố, ngoại lệ bật riêng là hành vi đúng.

**Tình huống 4:** Đã đặt `web.exposure.exclude="*"` nhưng JConsole còn thấy Health.

Đây là kết quả phù hợp khi JMX đang bật và health vẫn được công bố qua JMX. Muốn thay đổi JMX thì dùng cấu hình JMX; muốn vô hiệu hóa health thì dùng cờ bật/tắt của endpoint.

Khi mô tả một thay đổi cho đồng đội, hãy ghi rõ: **tắt kênh nào, endpoint nào còn được bật, bên nào đang sử dụng và đã kiểm tra bằng cách nào**. Cách diễn đạt đó giúp người tiếp nhận biết chính xác điều gì sẽ tiếp tục hoạt động.
