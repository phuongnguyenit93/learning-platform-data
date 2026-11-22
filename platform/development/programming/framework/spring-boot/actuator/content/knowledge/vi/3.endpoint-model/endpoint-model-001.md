# Định danh endpoint và quan hệ với đường dẫn /actuator

## 1. health là định danh, /actuator/health là đường dẫn

Khi gọi:

~~~text
GET http://127.0.0.1:8080/actuator/health
~~~

cần phân biệt các phần sau:

| Thành phần | Giá trị trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scheme và địa chỉ | `http://127.0.0.1:8080` | Nơi ứng dụng đang nhận yêu cầu |
| Tiền tố web quản trị | `/actuator` | Base path của các endpoint Actuator trên HTTP |
| Định danh endpoint | `health` | Tên logic của khả năng kiểm tra sức khỏe |
| Đường dẫn HTTP | `/actuator/health` | Vị trí để gọi khả năng đó trong cấu hình hiện tại |

**Định danh endpoint (endpoint ID)** không phải toàn bộ URL. `actuator` trong đường dẫn mặc định cũng không phải ID của một endpoint chứa mọi endpoint khác.

Mối quan hệ mặc định có thể hình dung:

~~~text
Endpoint ID: health
       +
Web base path: /actuator
       ↓
Đường dẫn HTTP: /actuator/health
~~~

Đổi tiền tố thành `/manage` sẽ làm URL thay đổi nhưng endpoint vẫn có ID `health`. Quy ước đường dẫn mặc định được mô tả trong [Spring Boot 3.3 — Actuator REST API URLs](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html).

Mục tiêu bài này là biết phần nào giữ nguyên danh tính endpoint, phần nào quyết định nơi truy cập và phần nào chỉ chọn một tài nguyên con.

## 2. Endpoint ID dùng để nhận diện khả năng nào?

Các ID thường gặp:

| ID | Khả năng được nhận diện | Đường dẫn gốc mặc định trên HTTP |
| --- | --- | --- |
| `health` | Sức khỏe ứng dụng | `/actuator/health` |
| `info` | Thông tin ứng dụng được đóng góp | `/actuator/info` |
| `metrics` | Tra cứu các phép đo đã đăng ký | `/actuator/metrics` |
| `loggers` | Xem hoặc điều chỉnh mức log | `/actuator/loggers` |

Các URL chỉ tồn tại khi ứng dụng có thành phần phù hợp và endpoint được đưa ra HTTP.

### 2.1. ID không phải tên lớp, tên bean hoặc tên phương thức

Trong một endpoint tự xây dựng theo mô hình Actuator, `@Endpoint(id = "runtimeinfo")` khai báo ID logic. Tên lớp có thể khác, tên bean có thể khác và tên phương thức operation cũng có thể khác.

Annotation `@Endpoint` cùng các operation được thích nghi với công nghệ đưa endpoint ra ngoài, chẳng hạn HTTP hoặc JMX. Vì vậy, ID không nên chứa hostname, cổng hoặc một đường dẫn gắn chặt với một lần triển khai. Xem [Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

Một controller thông thường có `@GetMapping("/actuator/runtimeinfo")` không tự trở thành endpoint Actuator chỉ vì dùng cùng tiền tố. Cần phân biệt mô hình endpoint với chuỗi ký tự của URL.

### 2.2. Quy tắc đặt ID và tương thích tên cũ

Đối với ID mới, dùng tên bắt đầu bằng chữ thường, gồm chữ và số, chẳng hạn `runtimeinfo` hoặc `buildstatus`. Không dùng `/health` hoặc `/actuator/health` làm ID.

Tài liệu `EndpointId` quy định ID theo chữ và số, bắt đầu bằng chữ thường. Cơ chế so sánh ID còn có chuẩn hóa; điều đó không phải cam kết rằng mọi URL HTTP sẽ tự bỏ qua hoa/thường hoặc ký tự khác. Xem [EndpointId API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/EndpointId.html).

Có một chi tiết tương thích cần biết khi đọc hệ thống cũ: mã nguồn Boot 3.3.0 vẫn tiếp nhận một số ID có dấu chấm hoặc dấu gạch nối và phát cảnh báo. Vì thế, không nên khẳng định mọi tên cũ như vậy luôn gây lỗi khởi động ngay. Cũng không lấy hành vi tương thích này làm quy tắc đặt ID mới. Đối chiếu [mã nguồn EndpointId 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/EndpointId.java).

## 3. Tiền tố đường dẫn và ánh xạ riêng từng endpoint

### 3.1. Đổi base path cho cả nhóm

Cấu hình properties:

~~~properties
management.endpoints.web.base-path=/manage
~~~

YAML tương đương:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Với ứng dụng dùng cổng 8080, không có đường dẫn nền khác:

~~~text
ID health → http://127.0.0.1:8080/manage/health
ID info   → http://127.0.0.1:8080/manage/info
~~~

ID không đổi. Các cấu hình theo ID như `management.endpoint.health.show-details` vẫn dùng chữ health, không chuyển thành manage.

### 3.2. Đổi đường dẫn của riêng một ID

Có thể cấu hình:

~~~properties
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.health=status
~~~

Hoặc:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: status
~~~

Kết quả cho endpoint health:

~~~text
ID: health
Base path: /manage
Đường dẫn thay thế cho ID health: status
Đường dẫn HTTP: /manage/status
~~~

`status` là phần đường dẫn thay thế, không phải ID mới. Endpoint info không bị đổi theo: nó vẫn ở `/manage/info` nếu khả dụng.

Trong cấu hình này, `/manage/health` không mặc nhiên là bí danh còn hoạt động. Nếu không có ánh xạ bổ sung nào khác, đường dẫn gốc đã được thay bằng đường dẫn mới.

### 3.3. Đưa endpoint trực tiếp dưới đường dẫn gốc

Ví dụ:

~~~properties
management.endpoints.web.base-path=/
management.endpoints.web.path-mapping.health=healthcheck
~~~

Trong điều kiện không có context path khác:

~~~text
ID health → /healthcheck
~~~

Không phải `/actuator/healthcheck`, cũng không phải `/health/healthcheck`.

Các thuộc tính base-path và path-mapping được mô tả trong [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 3.4. Bảng đối chiếu nhanh

Giả định dùng cùng host/cổng, không có context path bổ sung:

| Base path | Path mapping của health | Đường dẫn health | ID dùng trong cấu hình |
| --- | --- | --- | --- |
| `/actuator` | Không cấu hình | `/actuator/health` | `health` |
| `/manage` | Không cấu hình | `/manage/health` | `health` |
| `/manage` | `status` | `/manage/status` | `health` |
| `/` | `healthcheck` | `/healthcheck` | `health` |

Đọc bảng theo hai bước: chọn vị trí gốc của nhóm, rồi chọn phần đường dẫn của endpoint. Không ghép thêm ID lần nữa nếu nó đã được thay bằng path mapping.

## 4. Cấu hình theo ID, không theo URL đã đổi

Giả sử đã đổi health thành `/manage/status`. Muốn đưa endpoint này ra HTTP, vẫn viết:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Không đổi include thành `status` chỉ vì đang gọi URL có chữ status. Cũng không dùng `/manage/status` làm một mục include.

Có thể tách ba việc:

~~~text
ID health
├── được bật/đủ điều kiện tạo?
├── có trong tập endpoint đưa ra HTTP?
└── được ánh xạ thành đường dẫn nào?
~~~

Sau đó, một yêu cầu tới đường dẫn đó còn chịu chính sách truy cập.

Trong Boot 3.3.x:

- `management.endpoint.health.enabled` liên quan việc bật endpoint health.
- `management.endpoints.web.exposure.include` và `exclude` chọn các ID đưa ra web.
- `management.endpoints.web.path-mapping.health` chọn phần đường dẫn HTTP thay thế.

Đổi đường dẫn không làm một endpoint bị tắt tự bật lại, không tự bổ sung thư viện và không cấp quyền cho người gọi. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Một URL trả 404 chưa đủ để kết luận endpoint ID không hợp lệ. Có thể đang gọi tiền tố cũ, sai cổng, thiếu exposure hoặc thành phần đó chưa được tạo.

## 5. Một endpoint có thể có nhiều đường dẫn con

### 5.1. Health và thành phần sức khỏe

Hai đường dẫn:

~~~text
/actuator/health
/actuator/health/db
~~~

đều thuộc endpoint ID `health`. Phần `db` chọn một thành phần sức khỏe khi thành phần đó tồn tại và có thể được truy cập theo cấu hình.

Không khai báo `health/db` như một ID riêng trong include. Cũng không cho rằng mọi ứng dụng đều có thành phần db. Xem [Spring Boot 3.3 — Health REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 5.2. Metrics và tên phép đo

Ví dụ:

~~~text
/actuator/metrics
/actuator/metrics/jvm.memory.used
~~~

ID là `metrics`. `jvm.memory.used` là tên phép đo được chọn, không phải một endpoint ID mới.

Do đó, dấu chấm trong tên phép đo không mâu thuẫn với quy tắc đặt ID. Hai chuỗi nằm ở hai vai trò khác nhau. Query parameter như `?tag=area:heap` tiếp tục lọc dữ liệu của thao tác đó; nó cũng không đổi ID. Xem [Spring Boot 3.3 — Metrics REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 5.3. Loggers và thao tác trên cùng tài nguyên

Ví dụ:

~~~text
GET  /actuator/loggers/com.example
POST /actuator/loggers/com.example
~~~

Cả hai đều thuộc ID `loggers`. Phần `com.example` chọn logger, còn phương thức HTTP phân biệt thao tác đọc với thay đổi cấu hình.

ID một endpoint không có nghĩa endpoint đó chỉ có đúng một URL hoặc chỉ hỗ trợ đúng một HTTP method. Hãy đọc hợp đồng của operation cụ thể. Xem [Spring Boot 3.3 — Loggers REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 6. /actuator còn có thể là trang khám phá liên kết

### 6.1. Base path khác với endpoint health

Khi discovery được bật theo cấu hình thông thường:

~~~text
GET /actuator        → tài liệu liên kết tới các endpoint được đưa ra web
GET /actuator/health → kết quả kiểm tra sức khỏe
~~~

Tài liệu liên kết thường có trường `_links`. Cấu trúc rút gọn để minh họa:

~~~json
{
  "_links": {
    "self": {
      "href": "http://127.0.0.1:8080/actuator"
    },
    "health": {
      "href": "http://127.0.0.1:8080/actuator/health"
    }
  }
}
~~~

Đây không phải toàn bộ phản hồi cố định: còn có thể có liên kết khác, cờ templated hoặc địa chỉ được tính theo môi trường.

Chỉ mở `/actuator` không có nghĩa đang thực hiện kiểm tra sức khỏe. Muốn đọc trạng thái health, đi tới liên kết thích hợp.

### 6.2. Sau khi đổi đường dẫn, theo liên kết thực tế

Với base path `/manage` và mapping `health=status`, tài liệu discovery ở `/manage` có thể chứa liên kết health trỏ đến `/manage/status`.

Tên quan hệ health trong tài liệu và đường dẫn chứa status có thể khác nhau mà vẫn nhất quán. Thành phần giải quyết liên kết làm việc với các endpoint và đường dẫn tương ứng; xem [EndpointLinksResolver API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.html).

Công cụ bên ngoài nên được cấu hình theo địa chỉ thực tế, thay vì luôn giả định mọi ứng dụng đều có `/actuator/health`.

### 6.3. Tắt discovery không đồng nghĩa tắt endpoint

Cấu hình:

~~~properties
management.endpoints.web.discovery.enabled=false
~~~

bỏ tài liệu liên kết. Với các điều kiện khác giữ nguyên, health vẫn có thể hoạt động tại `/actuator/health`.

Khi base path là `/`, Boot tắt discovery để tránh xung đột ánh xạ ở đường dẫn gốc. Điều đó không làm endpoint health đã map thành `/healthcheck` biến mất.

Vì vậy, không dùng riêng việc `GET /actuator` hoặc `GET /` không có tài liệu liên kết để kết luận mọi endpoint Actuator đều ngừng hoạt động.

## 7. Cổng và context path hoàn thiện URL

### 7.1. Dùng cùng cổng với ứng dụng Servlet

Giả sử:

~~~properties
server.port=8080
server.servlet.context-path=/shop
management.endpoints.web.base-path=/manage
~~~

Khi không tách cổng quản trị, health có đường dẫn:

~~~text
http://127.0.0.1:8080/shop/manage/health
~~~

Ở đây:

~~~text
Context path của ứng dụng: /shop
Base path Actuator:       /manage
Phần endpoint:            health
~~~

`shop` không phải ID Actuator, và `/shop` không cần được thêm vào include.

### 7.2. Dùng cổng quản trị riêng

Nếu cấu hình:

~~~properties
server.port=8080
management.server.port=8081
management.server.address=127.0.0.1
management.endpoints.web.base-path=/manage
~~~

và không có management base path bổ sung, health nằm ở:

~~~text
http://127.0.0.1:8081/manage/health
~~~

Khi cổng quản trị riêng được dùng, đường dẫn quản trị được xét theo máy chủ quản trị, không mặc định nối `server.servlet.context-path` của cổng ứng dụng chính vào URL đó. Nếu cấu hình `management.server.base-path` thì phải tính thêm phần này.

Đây là lý do cần biết cấu hình cổng trước khi ghép các phần đường dẫn. Không có một công thức luôn nối mọi thuộc tính path của cả hai máy chủ.

### 7.3. Sau reverse proxy

URL người dùng hoặc công cụ nhìn thấy có thể còn chịu việc định tuyến/viết lại đường dẫn của proxy. Phải phân biệt URL phía ngoài với đường dẫn ứng dụng nhận được.

Đổi prefix bên ngoài proxy không tự đổi endpoint ID trong Spring Boot. Khi chẩn đoán, ghi rõ đang gọi trực tiếp ứng dụng hay đi qua proxy để tránh so sánh hai địa chỉ thuộc hai lớp khác nhau.

## 8. Thực nghiệm với health: đổi đường dẫn, giữ ID

Ví dụ dùng một dự án Spring Boot **3.3.0**, JDK **21**, đã có quản lý phiên bản dependency, Gradle wrapper và tác vụ bootRun. Mã Java dùng cú pháp tương thích Java 17 trở lên.

Dự án chỉ dùng Web và Actuator, không có Spring Security, không có context path hoặc management port riêng. Các giả định này giúp quan sát riêng việc ánh xạ.

### 8.1. Dependency và mã khởi động

Phần dependencies ghép vào build.gradle hiện có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Tạo `src/main/java/example/endpointidentity/EndpointIdentityApplication.java`:

~~~java
package example.endpointidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointIdentityApplication.class, args);
    }
}
~~~

Không cần tự tạo controller health. Thư viện Actuator cung cấp khả năng tương ứng khi điều kiện cấu hình phù hợp.

Trong `src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Chỉ chạy một lần ứng dụng tại một thời điểm. Sau mỗi lần thay đổi đối số dưới đây, dừng tiến trình cũ rồi chạy lại.

### 8.2. Lần A: cấu hình đường dẫn mặc định

~~~powershell
.\gradlew.bat bootRun
~~~

Ở cửa sổ khác:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/actuator/health
~~~

Khi các kiểm tra sức khỏe hiện có đều tốt, mã HTTP dự kiến là 200; body tối thiểu:

~~~json
{"status":"UP"}
~~~

Đây là HTTP response body, không phải stdout do main tự in. Header và log khởi động không phải chuỗi cố định.

Có thể xem discovery tại:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/actuator
~~~

### 8.3. Lần B: đổi tiền tố

Dừng ứng dụng rồi chạy:

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.base-path=/manage"
~~~

Địa chỉ cần gọi:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/manage/health
~~~

Với đúng ví dụ không có ánh xạ khác:

| Đường dẫn | Kết quả mong đợi |
| --- | --- |
| `/manage/health` | 200 khi health UP |
| `/manage` | Tài liệu discovery |
| `/actuator/health` | 404 |

Định danh vẫn là health. Chưa thay tên endpoint hoặc dữ liệu mà nó trả.

### 8.4. Lần C: thay riêng phần đường dẫn health

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.health=status"
~~~

Sau khi ứng dụng khởi động:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/manage/status
~~~

Kết quả dự kiến vẫn là health 200/UP trong điều kiện kiểm tra khỏe.

| Đường dẫn | Kết quả mong đợi |
| --- | --- |
| `/manage/status` | Health |
| `/manage/info` | Info khi khả dụng |
| `/manage/health` | 404 |
| `/actuator/health` | 404 |

Cấu hình include trong tệp nền vẫn là `health,info`. Không đổi sang `status,info`.

Dạng YAML nếu muốn lưu cố định riêng cấu hình ánh xạ này:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
      path-mapping:
        health: status
  endpoint:
    health:
      show-details: never
~~~

Đoạn này ghép vào cấu hình dự án theo một định dạng đã chọn; không tạo hai khối management trùng nhau trong cùng tài liệu.

### 8.5. Lần D: base path là dấu gạch chéo

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.base-path=/ --management.endpoints.web.path-mapping.health=healthcheck"
~~~

Gọi:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/healthcheck
~~~

Health vẫn có thể trả 200/UP. `GET /` không có tài liệu discovery của Actuator trong cấu hình này. Không có controller hoặc trang tĩnh khác thì đường dẫn gốc của ví dụ trả 404.

### 8.6. Lần E: chỉ tắt discovery

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.discovery.enabled=false"
~~~

Trong lần chạy này không truyền base-path/path-mapping của các lần trước:

~~~text
/actuator/health → health vẫn hoạt động
/actuator        → không có tài liệu discovery
~~~

Muốn xem riêng mã trạng thái:

~~~powershell
curl.exe --silent --show-error --output NUL --write-out "%{http_code}" http://127.0.0.1:8080/actuator
~~~

Đầu ra dự kiến trong ví dụ là:

~~~text
404
~~~

Dùng `curl.exe` để tránh khác biệt alias curl trong một số môi trường Windows PowerShell.

## 9. Kiểm tra khi công cụ vẫn gọi địa chỉ cũ

Đổi base path hoặc path mapping có thể đòi hỏi cập nhật những nơi đang giữ URL, chẳng hạn bộ kiểm tra sức khỏe, cấu hình giám sát hoặc tài liệu vận hành.

Một quy trình đối chiếu ngắn:

1. Ghi lại ID mong muốn, ví dụ health.
2. Xác định endpoint được đưa ra HTTP và có thể truy cập theo chính sách hiện tại không.
3. Xác định cổng quản trị thực tế.
4. Tính context/base path đúng với máy chủ đang dùng.
5. Kiểm tra path mapping của ID đó.
6. Nếu discovery được bật, đối chiếu liên kết thực tế.
7. Nếu có proxy, so sánh đường dẫn phía ngoài với đường dẫn mà ứng dụng nhận.

Thay đổi đường dẫn không phải một cơ chế xác thực. Cấu hình bảo mật viết cứng theo `/actuator/**` cần được xem lại khi tiền tố thay đổi.

Trong ứng dụng Servlet dùng Spring Security, `EndpointRequest` hỗ trợ tạo matcher cho vị trí endpoint Actuator thay vì chỉ dựa vào một chuỗi tiền tố cố định. Việc dùng matcher vẫn cần quy tắc phân quyền đầy đủ cho cả các URL khác. Xem [EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

## 10. Các hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| actuator là ID của health | actuator là tiền tố web mặc định; health là ID |
| Đổi /actuator thành /manage sẽ đổi mọi ID | Chỉ thay vị trí gốc trên HTTP |
| Map health thành status thì include phải dùng status | Include vẫn chọn ID health |
| Đường dẫn cũ tự còn hoạt động như bí danh | Không có bảo đảm này nếu chưa cấu hình ánh xạ bổ sung |
| Mỗi đường dẫn con là một endpoint ID mới | Tài nguyên con có thể thuộc cùng một endpoint |
| Dấu chấm trong jvm.memory.used vi phạm quy tắc EndpointId | Đó là tên phép đo, không phải ID endpoint |
| Không có discovery nghĩa là không có health | Hai ánh xạ phục vụ hai mục đích khác nhau |
| Một endpoint ID chỉ có một HTTP method | Operation của cùng endpoint có thể dùng các method khác nhau |
| Chỉ cần nối context path của ứng dụng vào mọi URL | Cổng quản trị riêng có quy tắc đường dẫn riêng |
| Đổi URL làm endpoint an toàn hơn tự động | Cần kiểm tra riêng quyền truy cập và tuyến mạng |

### Tự thực hành

1. Với base path /ops và mapping health=ready, chỉ ra URL health và giá trị include cần dùng.
2. Phân tách `/actuator/metrics/jvm.memory.used` thành tiền tố, endpoint ID và đối tượng được chọn.
3. Tắt discovery rồi dự đoán kết quả của `/actuator` và `/actuator/health`.
4. Cùng cổng 8080, Servlet context path /shop và base path /ops: health nằm ở đâu khi chưa có path mapping?
5. Khi một bộ kiểm tra sức khỏe còn gọi /actuator/health sau khi đổi base path, hãy nêu những nơi cần đối chiếu trước khi kết luận ứng dụng hỏng.

**Gợi ý đối chiếu:** câu 1 có đường dẫn /ops/ready nhưng ID vẫn là health; câu 2 có ID metrics; câu 3 cần tách discovery và operation; câu 4 là /shop/ops/health. Luôn phân biệt danh tính endpoint với vị trí truy cập của lần triển khai cụ thể.
