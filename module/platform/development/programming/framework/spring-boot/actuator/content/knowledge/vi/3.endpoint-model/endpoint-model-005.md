# Khám phá discovery page và liên kết giữa các endpoint

## 1. Discovery page giúp giải quyết vấn đề gì?

Khi vận hành một ứng dụng, bạn cần biết ứng dụng đang công bố những địa chỉ quản trị nào: kiểm tra sức khỏe ở đâu, xem thông tin ứng dụng ở đâu, đọc danh sách số đo ở đâu. Nếu tự ghép mọi URL từ trí nhớ, một thay đổi về cổng hoặc đường dẫn có thể làm công cụ kiểm tra gọi sai địa chỉ.

Trang khám phá (discovery page) là điểm vào HTTP trả về một tài liệu JSON chứa các liên kết đến các endpoint Actuator được công bố qua web. Mặc định, điểm vào này là `GET /actuator`. Từ đó, bên gọi đọc tên quan hệ rồi sử dụng URL trong `href`.

Hãy hình dung discovery page như bảng chỉ dẫn trong một tòa nhà: bảng cho biết cửa phòng nằm ở đâu; muốn biết trong phòng có gì và bạn có được vào hay không thì vẫn phải đi đến đúng cửa.

Trong bài này, bạn sẽ học theo thứ tự:

1. Đọc cấu trúc `_links` và hiểu quan hệ giữa endpoint, thao tác và liên kết.
2. Gọi discovery page rồi đi theo liên kết `health` và `metrics`.
3. Phân biệt URL dùng ngay với URL mẫu cần điền tham số.
4. Quan sát liên kết khi đổi đường dẫn, thay đổi phạm vi công bố hoặc tắt discovery.
5. Chẩn đoán tình huống có liên kết nhưng gọi endpoint không thành công.

Phạm vi ví dụ là Spring Boot **3.3.13**, ứng dụng Spring MVC, JDK 21. Discovery page ở đây không phải cơ chế đăng ký và tìm các dịch vụ như Eureka hoặc Consul, cũng không phải giao diện Swagger.

## 2. Endpoint, thao tác và liên kết có quan hệ thế nào?

Ba khái niệm này nằm ở ba mức khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Endpoint | Một khả năng quản trị, có định danh riêng | `health`, `metrics` |
| Thao tác | Một hành động mà endpoint cung cấp | Đọc danh sách tên số đo; đọc một số đo theo tên |
| Liên kết | Địa chỉ được quảng bá để bên gọi tìm một tài nguyên hoặc thao tác | `metrics`, `metrics-requiredMetricName` trong `_links` |

Một endpoint có thể tạo nhiều liên kết. Chẳng hạn, endpoint `metrics` có đường dẫn đọc danh sách tên số đo và đường dẫn đọc một số đo cụ thể. Vì vậy, **số phần tử trong `_links` không phải số endpoint**.

Trong Spring Boot 3.3.13, `EndpointLinksResolver` thêm liên kết `self`, sau đó thu thập các liên kết từ tập endpoint được cung cấp; với endpoint web, nó duyệt các thao tác để tạo liên kết. Đây là lý do xuất hiện cả liên kết gốc và liên kết có tham số cho cùng một endpoint. [Mã nguồn EndpointLinksResolver 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java).

Dạng tài liệu mà ta sẽ đọc:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://localhost:8080/actuator/health",
      "templated": false
    },
    "health-path": {
      "href": "http://localhost:8080/actuator/health/{*path}",
      "templated": true
    },
    "info": {
      "href": "http://localhost:8080/actuator/info",
      "templated": false
    },
    "metrics": {
      "href": "http://localhost:8080/actuator/metrics",
      "templated": false
    },
    "metrics-requiredMetricName": {
      "href": "http://localhost:8080/actuator/metrics/{requiredMetricName}",
      "templated": true
    }
  }
}
```

Đây là cấu trúc phản hồi của ví dụ bên dưới khi gọi qua `localhost:8080`; thứ tự các khóa JSON không có ý nghĩa và có thể khác.

Cách đọc:

- `_links`: đối tượng chứa các liên kết.
- `self`: liên kết quay lại chính tài liệu khám phá.
- `health`, `info`, `metrics`: tên quan hệ (relation) dùng để chọn liên kết.
- `href`: địa chỉ của liên kết.
- `templated: false`: URL không còn biến mẫu cần thay thế.
- `templated: true`: đây là mẫu URI, cần điền biến phù hợp trước khi gửi yêu cầu.

Tên quan hệ không phải lúc nào cũng trùng với một đoạn URL. Sau khi đổi đường dẫn của `health` thành `alive`, quan hệ vẫn có thể mang tên `health`, còn `href` trỏ đến đường dẫn mới.

## 3. Chuẩn bị một ứng dụng chạy độc lập

Ví dụ này là một dự án Maven nhỏ, độc lập với các quy ước build riêng của một repository. Cần JDK 21, Maven 3.6.3 trở lên, cổng 8080 đang rảnh và kết nối mạng cho lần tải thư viện đầu tiên.

Cấu trúc tệp:

```text
actuator-discovery-demo/
  pom.xml
  src/main/java/example/discovery/DiscoveryApplication.java
  src/main/resources/application.yml
```

Tệp `pom.xml`:

```xml
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

  <groupId>example</groupId>
  <artifactId>actuator-discovery-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>21</java.version>
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
```

Tệp `src/main/java/example/discovery/DiscoveryApplication.java`:

```java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryApplication.class, args);
    }
}
```

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
```

`spring-boot-starter-web` cung cấp môi trường HTTP và chuyển đổi JSON; `spring-boot-starter-actuator` cung cấp các khả năng quản trị. Không cần viết controller cho `/actuator`. Dự án này không có Spring Security, nên các yêu cầu trong phần thực hành không cần thông tin đăng nhập.

Tại thư mục chứa `pom.xml`, đóng gói rồi chạy:

```shell
mvn -q package
java -jar target/actuator-discovery-demo-1.0.0.jar
```

Maven biên dịch và đóng gói cùng các thư viện cần thiết; dùng riêng `javac DiscoveryApplication.java` không đủ vì lớp này phụ thuộc Spring Boot. Giữ tiến trình chạy trong một cửa sổ và thực hiện yêu cầu HTTP từ cửa sổ khác. Dùng `Ctrl+C` để dừng trước khi chạy lại với cấu hình khác.

Nhật ký khởi động chứa các thông tin về phiên bản và cổng; thời gian, PID và thời lượng khởi động thay đổi theo máy. Không dùng toàn bộ nhật ký làm kết quả cố định để so sánh.

## 4. Đọc discovery page rồi đi theo liên kết

### 4.1. Quan sát phản hồi HTTP

Trong terminal có cURL:

```shell
curl -i -H "Accept: application/json" http://localhost:8080/actuator
```

Trên Windows PowerShell, có thể dùng `curl.exe` để tránh nhầm với bí danh `curl` của một số phiên bản PowerShell.

Trong ứng dụng mẫu, yêu cầu thành công trả về HTTP 200 với JSON chứa `_links` như phần 2. Nếu không chỉ định `Accept`, phản hồi có thể mang kiểu nội dung Actuator như `application/vnd.spring-boot.actuator.v3+json`; đó vẫn là tài liệu JSON.

Hãy đọc cả mã trạng thái và nội dung. Một trang HTML đăng nhập được chuyển hướng đến không phải tài liệu khám phá, dù trình duyệt vẫn hiển thị được nội dung.

### 4.2. Đi theo liên kết bằng PowerShell

Đoạn sau chạy trong PowerShell, sau khi ứng dụng đã khởi động:

```powershell
$entry = 'http://localhost:8080/actuator'
$index = Invoke-RestMethod -Uri $entry -Headers @{ Accept = 'application/json' }

$healthLink = $index._links.health
if ($null -eq $healthLink) {
    throw 'Discovery page khong co lien ket health.'
}
if ($healthLink.templated -eq $true) {
    throw 'Can xu ly URI template truoc khi goi.'
}

$healthUri = [uri]$healthLink.href
if ($healthUri.Authority -ne ([uri]$entry).Authority -or
    $healthUri.Scheme -ne ([uri]$entry).Scheme) {
    throw 'Lien ket khong cung dia chi goc da tin cay.'
}

$health = Invoke-RestMethod -Uri $healthUri.AbsoluteUri
$health.status
```

Với ứng dụng mẫu đang khỏe, dòng cuối in:

```text
UP
```

Ở đây, địa chỉ `health` được lấy từ phản hồi. Bên gọi chỉ cần biết địa chỉ khởi đầu và quan hệ muốn tìm. Khi đường dẫn endpoint thay đổi, phần đọc `href` vẫn dùng được nếu địa chỉ khởi đầu đã được cập nhật đúng.

Kiểm tra địa chỉ gốc trong đoạn mã là lựa chọn phù hợp cho ví dụ chạy trên một máy. Một công cụ dùng trong hệ thống thực tế có thể cho phép một danh sách địa chỉ tin cậy; không nên tự động mang thông tin xác thực đi theo liên kết đến một máy chủ bất kỳ.

Tài liệu Health mô tả `status` và các phần chi tiết có thể xuất hiện. `UP` là kết quả kỳ vọng của ví dụ khỏe mạnh, không phải giá trị mà mọi ứng dụng luôn trả về. [Health API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 4.3. Không suy diễn rằng mọi phản hồi đều có liên kết

Gọi `health` trong ví dụ trả về dữ liệu sức khỏe, thường chỉ có:

```json
{"status":"UP"}
```

Không có quy tắc bắt buộc rằng phản hồi này phải chứa `_links.metrics` hoặc liên kết ngược về discovery page. Muốn chuyển từ kiểm tra sức khỏe sang đọc số đo, bên gọi có thể quay lại dùng tài liệu khám phá đã lấy.

Mối liên hệ ở đây là **điều hướng từ điểm vào đến các khả năng quản trị**. Nó không có nghĩa `health` gọi `metrics`, không chứng minh hai endpoint phụ thuộc nhau và không tạo ra sơ đồ phụ thuộc nghiệp vụ.

## 5. Hiểu và sử dụng URL mẫu

Liên kết `metrics-requiredMetricName` trong ví dụ có dạng:

```text
http://localhost:8080/actuator/metrics/{requiredMetricName}
```

Đây chưa phải URL của một số đo cụ thể. Biến `requiredMetricName` phải được thay bằng tên số đo có thật.

Trước hết, lấy danh sách tên từ liên kết `metrics`:

```powershell
$metricsLink = $index._links.metrics
if ($null -eq $metricsLink) {
    throw 'Discovery page khong co lien ket metrics.'
}

$metrics = Invoke-RestMethod -Uri $metricsLink.href
$metricName = 'jvm.memory.used'
if ($metricName -notin $metrics.names) {
    throw 'Ung dung chua dang ky so do jvm.memory.used.'
}
```

Sau đó điền mẫu URI:

```powershell
$metricLink = $index._links.'metrics-requiredMetricName'
if ($null -eq $metricLink -or $metricLink.templated -ne $true) {
    throw 'Khong tim thay mau URI metrics nhu vi du.'
}

$metricUri = $metricLink.href.Replace(
    '{requiredMetricName}',
    [uri]::EscapeDataString($metricName)
)

$metric = Invoke-RestMethod -Uri $metricUri
$metric.name
```

Kết quả của dòng cuối trong ví dụ:

```text
jvm.memory.used
```

Các số trong `measurements` biến động khi ứng dụng chạy; không gán một giá trị bộ nhớ cố định cho mọi lần thử. Cơ chế đọc danh sách tên và đọc số đo theo tên được mô tả trong [Metrics API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Các điểm cần hiểu từ ví dụ:

- Khóa quan hệ có dấu gạch nối nên được truy cập bằng `$index._links.'metrics-requiredMetricName'`.
- Đoạn `Replace` chỉ xử lý đúng mẫu một biến đã biết của bài học; đây không phải bộ xử lý URI Template tổng quát.
- Kiểm tra `templated` trước khi gọi. Không gửi nguyên dấu ngoặc nhọn đến máy chủ hoặc mong cURL tự hiểu cách điền biến.
- Danh sách tên số đo nằm trong dữ liệu của endpoint `metrics`; discovery page không quảng bá một liên kết riêng cho mọi số đo.

Với `health-path`, mẫu `{*path}` có thể đại diện cho nhiều đoạn đường dẫn. Không áp dụng máy móc cách mã hóa một đoạn đường dẫn đơn của `requiredMetricName` cho toàn bộ trường hợp này. Chỉ truy vấn thành phần hoặc nhóm sức khỏe thực sự tồn tại và được phép xem; sự xuất hiện của mẫu không bảo đảm mọi giá trị bạn điền đều hợp lệ.

Trong mã 3.3.13, thao tác đọc một số đo có tham số selector tên `requiredMetricName`; thao tác đọc sức khỏe theo đường dẫn dùng selector nhận các đoạn còn lại. Các mẫu trên phản ánh các thao tác đó. [MetricsEndpoint](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java), [HealthEndpointWebExtension](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointWebExtension.java).

## 6. Liên kết thay đổi thế nào khi đổi địa chỉ?

### 6.1. Đổi base path và đường dẫn một endpoint

Dừng ứng dụng, rồi chạy lại:

```shell
java -jar target/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.health=alive
```

Bây giờ:

| Thành phần | Trước | Sau |
| --- | --- | --- |
| Discovery page | `/actuator` | `/manage` |
| Đường dẫn sức khỏe | `/actuator/health` | `/manage/alive` |
| Quan hệ dùng để tìm sức khỏe | `health` | `health` |

Đọc lại tài liệu từ địa chỉ khởi đầu mới:

```powershell
$entry = 'http://localhost:8080/manage'
$index = Invoke-RestMethod -Uri $entry
$index._links.health.href
```

Dòng cuối in:

```text
http://localhost:8080/manage/alive
```

Như vậy, một bên gọi tự ghép `$entry + '/health'` sẽ dùng sai đường dẫn, còn bên gọi lấy `_links.health.href` sẽ nhận đúng địa chỉ đã ánh xạ.

Định danh endpoint vẫn là `health`; danh sách `exposure.include` tiếp tục dùng `health`, không đổi thành `alive`.

### 6.2. Context path và cổng quản trị

Bảng dưới mô tả các cấu hình **độc lập**, mỗi hàng bắt đầu từ ứng dụng mẫu ban đầu:

| Cấu hình thêm khi khởi động | Địa chỉ discovery |
| --- | --- |
| Không thêm | `http://localhost:8080/actuator` |
| `--server.servlet.context-path=/demo` | `http://localhost:8080/demo/actuator` |
| `--management.server.port=8081` | `http://localhost:8081/actuator` |
| `--management.server.port=8081 --management.server.base-path=/ops --management.endpoints.web.base-path=/manage` | `http://localhost:8081/ops/manage` |

Khi dùng cùng cổng trong ứng dụng Servlet, base path của endpoint tương đối với `server.servlet.context-path`. Khi dùng cổng quản trị riêng, nó tương đối với `management.server.base-path`. Vì vậy, không ghép context path của ứng dụng chính vào URL quản trị một cách mặc định. [Monitoring and Management over HTTP 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-endpoint-paths).

Discovery giúp tìm các đường dẫn nằm sau điểm vào; địa chỉ ban đầu, cổng và quyền kết nối đến mạng quản trị vẫn phải được cung cấp từ cấu hình triển khai.

### 6.3. Trường hợp base path bằng `/`

Với Spring MVC 3.3.13, cần phân biệt:

- Dùng **cùng cổng** và `management.endpoints.web.base-path=/`: không đăng ký discovery tại gốc để tránh xung đột với các ánh xạ khác. Endpoint như `/health` vẫn có thể hoạt động.
- Dùng **cổng quản trị riêng**: ánh xạ discovery tại gốc của phía quản trị vẫn có thể được đăng ký nếu `management.endpoints.web.discovery.enabled=true`.

Trong ứng dụng mẫu không có controller ở gốc, trường hợp thứ nhất làm `GET /` trả 404 còn `GET /health` vẫn thành công. Với cổng quản trị 8081 và base path `/`, điểm vào ở phía quản trị là `http://localhost:8081/`.

Tài liệu tổng quan mô tả việc tắt discovery khi đường dẫn gốc là `/`; điều kiện trong mã Spring MVC 3.3.13 cụ thể hơn: discovery bật và có base path không rỗng **hoặc** cổng quản trị khác cổng ứng dụng. Khi áp dụng trường hợp biên này, đối chiếu đúng phiên bản và công nghệ web đang dùng. [Điều kiện shouldRegisterLinksMapping trong Spring MVC 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/servlet/WebMvcEndpointManagementContextConfiguration.java).

## 7. Vì sao có hoặc không có một liên kết?

Trong Boot 3.3, cần tách ba câu hỏi:

1. Khả năng quản trị đó có tồn tại và được bật không?
2. Nó có được công bố qua HTTP không?
3. Người gọi có quyền thực hiện yêu cầu đó không?

Mặc định chỉ `health` được công bố qua HTTP. Ví dụ đã chủ động thêm `info` và `metrics` để bạn có nhiều liên kết mà quan sát. Nếu thêm:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
        exclude: metrics
```

thì `exclude` thắng `include`: discovery không còn quảng bá các liên kết web của `metrics`. Không thể dùng discovery để nhìn thấy những endpoint chỉ được công bố qua JMX. Cơ chế bật endpoint và cơ chế công bố qua web là hai thiết lập khác nhau. [Endpoint exposure trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Một controller nghiệp vụ thông thường như `GET /orders` không tự xuất hiện trong discovery page chỉ vì nó nằm trong cùng ứng dụng. Discovery của Actuator có phạm vi quản trị của nó.

Ngược lại, **có liên kết không đồng nghĩa đã được cấp quyền gọi**. Các liên kết được tạo từ tập endpoint phía máy chủ; không nên xem chúng là danh sách quyền được cá nhân hóa theo người dùng. Một yêu cầu tiếp theo có thể gặp 401 hoặc 403 do cấu hình bảo mật.

Tương tự, `href` không mô tả đầy đủ phương thức HTTP, kiểu dữ liệu yêu cầu hay điều kiện thực hiện thao tác. Với các endpoint có thao tác thay đổi trạng thái, phải đọc hợp đồng API trước khi sử dụng; không suy ra rằng mọi liên kết đều dùng được bằng `GET`.

## 8. Tắt discovery có làm các endpoint biến mất không?

Dừng ứng dụng rồi khởi động lại từ cấu hình mẫu:

```shell
java -jar target/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.discovery.enabled=false
```

Thử hai yêu cầu:

```shell
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/health
```

Trong đúng ứng dụng mẫu:

| Yêu cầu | Kết quả kỳ vọng | Giải thích |
| --- | --- | --- |
| `GET /actuator` | 404 | Không còn ánh xạ discovery |
| `GET /actuator/health` | 200 và trạng thái `UP` khi ứng dụng khỏe | Endpoint sức khỏe vẫn được bật và công bố |

Cấu hình này tắt bảng chỉ dẫn; nó không tự thay đổi cấu hình của từng endpoint. Vì thế, tắt discovery không thể thay thế việc kiểm soát quyền truy cập hoặc phạm vi công bố endpoint. Thuộc tính được mô tả tại phần [Hypermedia for Actuator Web Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.hypermedia).

## 9. Chẩn đoán những lỗi dễ gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Discovery trả 404 nhưng `health` gọi trực tiếp được | Kiểm tra `discovery.enabled`, base path `/`, context path và cổng quản trị |
| Không thấy `metrics` trong `_links` | Kiểm tra endpoint có được tạo, được bật, được công bố qua web hay bị `exclude` không |
| Có `metrics` nhưng không có tên số đo mong muốn | Đọc `names` của endpoint; số đo phụ thuộc những gì ứng dụng đã đăng ký |
| Gọi URL còn `{requiredMetricName}` và nhận lỗi | Đọc `templated`, điền biến bằng tên hợp lệ rồi mã hóa giá trị theo đúng vị trí trong URI |
| Có liên kết nhưng nhận 401 hoặc 403 | Kiểm tra thông tin xác thực và quy tắc phân quyền; không kết luận rằng endpoint chưa được công bố |
| Gọi discovery nhận HTML | Kiểm tra chuyển hướng đăng nhập hoặc đang gọi nhầm trang của ứng dụng/proxy |
| `href` có scheme, host hoặc prefix nội bộ sau reverse proxy | Đối chiếu cấu hình chuyển tiếp địa chỉ của proxy và ứng dụng; kiểm thử qua URL mà bên gọi thực sự dùng |
| Đổi `health` thành đường dẫn `alive` rồi không tìm thấy quan hệ `alive` | Tìm bằng quan hệ `health`; đường dẫn trong `href` và tên quan hệ có vai trò khác nhau |

Mã lỗi là dấu hiệu cần điều tra, không phải bằng chứng tuyệt đối của một nguyên nhân: proxy hoặc quy tắc bảo mật tùy chỉnh có thể thay đổi phản hồi.

Khi chẩn đoán, thực hiện tuần tự: kiểm tra địa chỉ khởi đầu → xem mã trạng thái và kiểu nội dung → xác nhận JSON có `_links` → tìm quan hệ → xử lý mẫu URI nếu có → gọi endpoint → đọc kết quả theo hợp đồng của endpoint đó.

## 10. Thực hành để tự kiểm tra cách hiểu

Mỗi bài bắt đầu từ ứng dụng mẫu, dừng tiến trình trước rồi chạy lại để tránh trộn cấu hình giữa các bài.

1. **Đổi cách tìm URL:** gọi discovery, đọc `_links.health.href` và kiểm tra sức khỏe mà không tự nối chuỗi `'/health'`. Kết quả cần giải thích được là bạn chọn một quan hệ rồi đi theo địa chỉ máy chủ cung cấp.
2. **Đếm đúng đối tượng:** công bố `health,info,metrics`, so sánh ba endpoint với các khóa trong `_links`. Giải thích phần chênh lệch bằng `self` và các thao tác có URL mẫu; không xem mỗi khóa là một endpoint độc lập.
3. **Đổi đường dẫn:** đặt base path `/manage` và ánh xạ `health` thành `alive`. Chỉ cập nhật điểm vào trong đoạn mã đọc discovery, sau đó xác nhận quan hệ `health` đưa đến `/manage/alive`.
4. **Thử mẫu URI:** lấy danh sách tên số đo, chọn một tên có thật, điền mẫu `metrics-requiredMetricName` và đọc trường `name`. Giải thích vì sao không cố định giá trị `measurements` giữa các lần chạy.
5. **Tách discovery khỏi endpoint:** tắt discovery, kiểm tra riêng `/actuator` và `/actuator/health`. Nêu rõ 404 của bảng chỉ dẫn không chứng minh endpoint sức khỏe đã bị tắt.
6. **Thay đổi phạm vi công bố:** thêm `exposure.exclude=metrics` trong khi `include` vẫn chứa `metrics`. Xác nhận các liên kết của `metrics` biến mất và giải thích thứ tự ưu tiên.

Sau các bài thực hành, bạn cần giải thích được vì sao bên gọi vẫn phải biết điểm vào, vì sao nên đọc `href` thay cho ghép URL, và vì sao tìm thấy một địa chỉ chưa đủ để kết luận rằng yêu cầu đến địa chỉ đó sẽ thành công.
