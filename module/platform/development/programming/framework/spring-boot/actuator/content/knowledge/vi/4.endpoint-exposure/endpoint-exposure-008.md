# Tùy chỉnh đường dẫn endpoint bằng base-path và path-mapping

## 1. Phân biệt tên endpoint với địa chỉ HTTP

Một hệ thống có thể cần dùng `/manage` làm vùng quản trị, hoặc cần địa chỉ kiểm tra sức khỏe là `/healthcheck` để khớp với công cụ triển khai. Actuator cho phép cấu hình những địa chỉ này mà không phải viết thêm controller chỉ để chuyển tiếp yêu cầu.

Bài này áp dụng **Spring Boot 3.3.x**, đối chiếu tài liệu 3.3.13. Hai thuộc tính cần phân biệt:

| Thuộc tính | Vai trò | Ví dụ |
| --- | --- | --- |
| `management.endpoints.web.base-path` | Tiền tố chung của các endpoint Actuator qua HTTP | `/manage` |
| `management.endpoints.web.path-mapping.<id>` | Ánh xạ ID của một endpoint sang phần đường dẫn riêng | `health=status` |

Theo mặc định, tiền tố là `/actuator` và phần đường dẫn riêng thường lấy từ ID. Vì vậy ID `health` được truy cập bằng `/actuator/health`. Khi đổi cả hai thuộc tính như bảng trên, đường dẫn trở thành `/manage/status`. [Tùy chỉnh đường dẫn quản trị HTTP trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-context-path).

Cần giữ ba khái niệm riêng:

- **ID:** tên định danh như `health`, dùng trong cấu hình bật/tắt và công bố.
- **Đường dẫn đã ánh xạ:** địa chỉ HTTP như `/manage/status`.
- **Dữ liệu và thao tác:** endpoint vẫn kiểm tra sức khỏe, không đổi chức năng vì tên đường dẫn thay đổi.

Spring Boot cũng có mô hình API phân biệt endpoint theo ID và đường dẫn đã ánh xạ. [API `PathMappedEndpoints`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/PathMappedEndpoints.html).

## 2. Chỉ đổi tiền tố chung bằng base-path

Giả sử ứng dụng đang dùng chung cổng 8080, không có tiền tố đường dẫn ứng dụng. Cấu hình:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - info
```

Các đường dẫn HTTP thay đổi theo tiền tố mới:

| Endpoint | Đường dẫn mặc định | Đường dẫn sau cấu hình |
| --- | --- | --- |
| `health` | `/actuator/health` | `/manage/health` |
| `info` | `/actuator/info` | `/manage/info` |

`base-path` đổi phần chung, nên không cần khai báo riêng cho từng endpoint chỉ để thay chữ `actuator`. Các endpoint chưa được công bố không tự xuất hiện chỉ vì có tiền tố mới.

Ví dụ tương đương bằng `application.properties`:

```properties
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health,info
```

Đây là hai cách biểu diễn cùng cấu hình; dùng một định dạng nhất quán trong ứng dụng. Các thuộc tính web quản trị được gom dưới tiền tố `management.endpoints.web`. [API `WebEndpointProperties`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.html).

Việc đổi tiền tố không tạo sẵn một địa chỉ cũ làm bí danh hoặc một quy tắc chuyển hướng HTTP. Với ứng dụng thử không có ánh xạ bổ sung, sau khi chuyển sang `/manage`, hãy gọi `/manage/health` thay cho `/actuator/health`.

## 3. Đổi đường dẫn của từng endpoint bằng path-mapping

Ví dụ đổi `health` thành `status`, `metrics` thành `meters`, đồng thời dùng tiền tố `/manage`:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - metrics
      path-mapping:
        health: status
        metrics: meters
```

Kết quả khi các endpoint đủ điều kiện hoạt động:

| ID endpoint | Giá trị ánh xạ | Đường dẫn HTTP |
| --- | --- | --- |
| `health` | `status` | `/manage/status` |
| `metrics` | `meters` | `/manage/meters` |

Chú ý các chi tiết:

- Viết khóa ánh xạ là ID gốc: `health:`, không phải `status:`.
- Trong ví dụ, giá trị `status` chỉ là phần đường dẫn riêng; không lặp lại `/manage` vào giá trị đó.
- Danh sách công bố vẫn chứa `health`, `metrics`. Không đổi thành `status`, `meters`.
- Nếu cần đặt trạng thái bật riêng, vẫn dùng `management.endpoint.health.enabled`, không tạo một khóa bật cho tên đường dẫn `status`.

Nếu chỉ cần đổi riêng `health` và giữ tiền tố mặc định, cấu hình ngắn hơn là:

```properties
management.endpoints.web.path-mapping.health=status
```

Với cấu hình độc lập này, địa chỉ là `/actuator/status`. Đổi riêng phần ánh xạ không tự xóa tiền tố `/actuator`.

### Đường dẫn thao tác nằm dưới endpoint

Endpoint `metrics` có thao tác đọc một số đo theo mẫu `/{metric.name}`. Khi ánh xạ gốc của endpoint thành `meters`, ví dụ URL đọc số đo trở thành:

```text
GET /manage/meters/jvm.memory.used
```

Phần `jvm.memory.used` là tên số đo được chọn, không phải ID endpoint để khai báo trong `path-mapping`. Cấu trúc chọn số đo vẫn thuộc API metrics; dữ liệu thực tế phụ thuộc những số đo ứng dụng đã đăng ký. [API đọc số đo của endpoint metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

## 4. Ghép đường dẫn khi dùng chung cổng ứng dụng

Để xác định địa chỉ, cần xét đường dẫn nền của ứng dụng ngoài hai thuộc tính Actuator.

Mô hình ghép các phần, với dấu `/` phân cách phù hợp:

```text
Đường dẫn nền của ứng dụng
    + base-path của Actuator
    + phần ánh xạ của endpoint hoặc ID mặc định
    + phần đường dẫn thao tác, nếu có
```

### 4.1. Ứng dụng Servlet

Với Spring MVC/Servlet, khi dùng chung cổng, đường dẫn nền liên quan là `server.servlet.context-path`.

```yaml
server:
  port: 8080
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
      path-mapping:
        health: status
```

Địa chỉ của `health` trong ví dụ:

```text
http://localhost:8080/shop/manage/status
```

Nếu gọi `http://localhost:8080/manage/status`, bạn đã bỏ sót phần `/shop`. Các ví dụ này giả định không có cấu hình đường dẫn servlet bổ sung hoặc proxy viết lại URL.

### 4.2. Ứng dụng Reactive

Với Spring WebFlux, khi dùng chung cổng, xét `spring.webflux.base-path` thay cho `server.servlet.context-path`:

```yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /api

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
      path-mapping:
        health: status
```

Địa chỉ trong ví dụ reactive:

```text
http://localhost:8080/api/manage/status
```

Hai đoạn cấu hình Servlet và Reactive là hai trường hợp độc lập. Không cần đặt đồng thời cả hai loại đường dẫn nền để “chắc chắn có hiệu lực”.

Quan hệ giữa đường dẫn ứng dụng và `management.endpoints.web.base-path` được nêu trong [danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

## 5. Khi tách sang cổng quản trị riêng

Nếu cổng quản trị **khác** cổng ứng dụng, đường dẫn nền của máy chủ quản trị được cấu hình bằng `management.server.base-path`. Không tự nối tiếp context path của máy chủ ứng dụng vào URL quản trị.

Ví dụ Servlet:

```yaml
server:
  port: 8080
  servlet:
    context-path: /shop

management:
  server:
    port: 9091
    base-path: /ops
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
      path-mapping:
        health: status
```

Đọc từng lớp:

| Thành phần | Giá trị |
| --- | --- |
| Cổng ứng dụng | `8080` |
| Context path của ứng dụng | `/shop` |
| Cổng quản trị riêng | `9091` |
| Đường dẫn nền của máy chủ quản trị | `/ops` |
| Tiền tố endpoint web | `/manage` |
| Phần ánh xạ của health | `status` |

URL quản trị thu được:

```text
http://localhost:9091/ops/manage/status
```

Không ghép thành `http://localhost:9091/shop/ops/manage/status`. `/shop` thuộc cấu hình máy chủ ứng dụng trong ví dụ, còn URL quản trị sử dụng đường dẫn nền riêng.

`management.server.base-path` yêu cầu cổng quản trị riêng; `management.endpoints.web.base-path` vẫn là tiền tố endpoint nằm bên trong vùng quản trị đó. [Thuộc tính máy chủ quản trị](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

Bảng suy luận nhanh từ các ví dụ, đều ánh xạ `health=status`:

| Trường hợp | URL cuối |
| --- | --- |
| Chung cổng, không có đường dẫn nền, Actuator `/manage` | `http://localhost:8080/manage/status` |
| Chung cổng Servlet, context `/shop`, Actuator `/manage` | `http://localhost:8080/shop/manage/status` |
| Chung cổng WebFlux, nền `/api`, Actuator `/manage` | `http://localhost:8080/api/manage/status` |
| Cổng riêng 9091, nền quản trị `/ops`, Actuator `/manage` | `http://localhost:9091/ops/manage/status` |

## 6. Đưa endpoint về gốc và ảnh hưởng đến trang khám phá

Nếu cần địa chỉ `/healthcheck` ngay ở gốc, trong ứng dụng dùng chung cổng và không có đường dẫn nền bổ sung:

```yaml
management:
  endpoints:
    web:
      base-path: /
      exposure:
        include: health
      path-mapping:
        health: healthcheck
```

Địa chỉ mới:

```text
http://localhost:8080/healthcheck
```

Nếu giữ `base-path` mặc định và chỉ ánh xạ `health=healthcheck`, kết quả sẽ là `/actuator/healthcheck`. Chính `base-path: /` mới đưa tiền tố Actuator về gốc. Nếu ứng dụng có context path, vẫn phải xét phần nền đó; ví dụ Servlet dùng chung cổng với `/shop` sẽ có `/shop/healthcheck`.

### Trang khám phá không phải endpoint health

Actuator thường có trang khám phá liên kết tại tiền tố chung: mặc định là `/actuator`; với `base-path=/manage`, có thể tìm các liên kết ở `/manage`, kèm phần nền/cổng tương ứng.

Trong ví dụ dùng chung cổng ở trên, khi đặt tiền tố Actuator về `/`, trang khám phá này được tắt để tránh xung đột với ánh xạ gốc của ứng dụng. Điều đó không có nghĩa endpoint `/healthcheck` bị tắt. Cũng không thể kết luận URL `/` sẽ trả 404, vì ứng dụng có thể có trang chủ riêng. [Trang khám phá liên kết của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.hypermedia).

Có một khác biệt cần xét khi tách cổng: trong **Spring MVC 3.3.13**, mã đăng ký liên kết còn cho phép trang khám phá khi cổng quản trị riêng đang hoạt động và discovery được bật, kể cả khi tiền tố endpoint ở gốc. Vì vậy kết luận tự tắt phía trên được giới hạn ở trường hợp dùng chung cổng. Đây là suy luận trực tiếp từ [điều kiện đăng ký liên kết trong mã Spring MVC 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/servlet/WebMvcEndpointManagementContextConfiguration.java), chi tiết hơn phần mô tả ngắn trong tài liệu người dùng.

Nếu yêu cầu là chủ động tắt trang khám phá, đặt rõ thuộc tính sau thay vì suy từ đường dẫn:

```properties
management.endpoints.web.discovery.enabled=false
```

Khi đưa endpoint gần gốc, chọn đường dẫn không trùng với controller nghiệp vụ hoặc endpoint khác. Ví dụ không ánh xạ hai endpoint khác nhau cùng thành `status`.

## 7. Thực hành xác minh đường dẫn cũ và mới

### Điều kiện của bài thử

Dùng ứng dụng Spring Boot 3.3.x đã có lớp khởi động cùng `spring-boot-starter-web` và `spring-boot-starter-actuator`, Java 17 trở lên. Không cần thêm controller để tùy chỉnh đường dẫn.

Giả định ứng dụng thử:

- Dùng HTTP cổng 8080, không có context path.
- Không có Spring Security hoặc proxy thay đổi kết quả.
- Không có controller trùng các URL đang kiểm tra.
- Không có nguồn cấu hình khác ghi đè; trạng thái sức khỏe tổng hợp là `UP`.

Các kết quả sau là kết quả dự kiến theo điều kiện này.

### Cấu hình thực hành

Dùng nội dung sau trong `src/main/resources/application.yml` của ứng dụng thử:

```yaml
server:
  port: 8080

management:
  endpoints:
    enabled-by-default: false
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - metrics
      path-mapping:
        health: status
        metrics: meters
  endpoint:
    health:
      enabled: true
    metrics:
      enabled: true
```

Khởi động ứng dụng theo cách thông thường của dự án. Trong PowerShell trên Windows, chạy lần lượt:

```powershell
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/manage/status"
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/actuator/health"
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/manage/health"
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/manage/meters"
```

Stdout dự kiến khi chạy bốn lệnh đúng thứ tự:

```text
200
404
404
200
```

Giải thích:

- `/manage/status` dùng đúng tiền tố và phần ánh xạ mới.
- `/actuator/health` dùng địa chỉ cũ.
- `/manage/health` đã đổi tiền tố nhưng vẫn dùng phần đường dẫn riêng cũ.
- `/manage/meters` là đường dẫn mới của endpoint ID `metrics`.

Các lệnh dùng `--output NUL` để bỏ phần thân và in riêng mã HTTP, mỗi mã kèm xuống dòng. Muốn xem dữ liệu health:

```powershell
curl.exe --silent "http://localhost:8080/manage/status"
```

Trong điều kiện `UP` và không công khai chi tiết, phản hồi JSON thường thấy là:

```json
{"status":"UP"}
```

Cấu hình đường dẫn không đảm bảo ứng dụng luôn khỏe; API health phản ánh trạng thái của các thành phần và có thể có phần chi tiết khác. [Cấu trúc API health](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

Để kiểm tra việc giữ nguyên thao tác chọn số đo:

```powershell
curl.exe --silent "http://localhost:8080/manage/meters/jvm.memory.used"
```

Kiểm tra trường `name` tương ứng, thay vì cố so khớp giá trị bộ nhớ vốn thay đổi theo thời gian. Nếu cần kiểm tra bảng URL ở mục 4 hoặc 5, dùng từng cấu hình đó độc lập và khởi động lại ứng dụng trước khi thử.

## 8. Những điều việc đổi đường dẫn không tự thực hiện

### Không thay quyết định bật hoặc công bố

`base-path` và `path-mapping` chọn địa chỉ. Endpoint vẫn phải được bật, được công bố qua HTTP và có đủ điều kiện tạo thành phần cần thiết. Đổi đường dẫn của `metrics` không làm mất tác dụng của `management.endpoint.metrics.enabled=false` hoặc `web.exposure.exclude=metrics`. [Điều kiện công bố endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

### Không đổi ID trong JMX

Hai thuộc tính nằm dưới `management.endpoints.web` và điều chỉnh đường dẫn web. Không suy ra rằng MBean health được đổi tên thành `status`. JMX có cơ chế tên/miền riêng và cần được cấu hình riêng. [Tên MBean endpoint qua JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### Không tự cập nhật nơi gọi hoặc bảo vệ endpoint

Sau khi đổi URL, rà soát các nơi đang giữ địa chỉ cũ: kiểm tra sức khỏe của nền tảng triển khai, công cụ giám sát, tập lệnh vận hành, quy tắc proxy và các quy tắc bảo vệ viết theo URL cụ thể.

Đổi `/actuator` thành một tên khó đoán không thay thế xác thực, phân quyền hoặc giới hạn kết nối. Nếu có Spring Security, xác minh quy tắc bảo vệ vẫn áp dụng cho đường dẫn mới; không gỡ bảo vệ chỉ để làm lệnh curl thành công.

Các URL trong bài là địa chỉ ứng dụng trực tiếp. Khi có proxy thêm/bớt tiền tố hoặc đổi cổng bên ngoài, phải phân biệt URL phía người gọi với URL mà ứng dụng thực sự nhận.

## 9. Lỗi thường gặp và thứ tự kiểm tra

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Đổi sang `/manage` nhưng vẫn gọi `/actuator/health` | Cập nhật tiền tố của URL |
| Gọi `/manage/health` sau khi ánh xạ `health=status` | Dùng phần đường dẫn riêng mới là `status` |
| Dùng `include=status` mà không thấy health | Danh sách công bố phải dùng ID `health` |
| Gọi `/manage/status` trong ứng dụng Servlet có context `/shop` | Ghép thêm `/shop` khi dùng chung cổng |
| Tách cổng nhưng vẫn gọi cổng 8080 | Dùng cổng quản trị và đường dẫn nền của nó |
| Không thấy trang khám phá khi dùng chung cổng và đặt `base-path=/` | Thử endpoint cụ thể; trang khám phá gốc được tắt |
| File có URL mới nhưng ứng dụng vẫn dùng URL cũ | Kiểm tra profile, giá trị hiệu lực và lần khởi động gần nhất |

Nguồn cấu hình như biến môi trường hoặc tham số dòng lệnh có thể ghi đè nội dung file. Ví dụ tham số `--management.endpoints.web.base-path=/ops` có thể làm tiền tố thực tế khác với `/manage` trong YAML. [Thứ tự nguồn cấu hình Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Khi gặp lỗi, ghi lại bộ dữ kiện: **giao thức, cổng, đường dẫn nền, base-path, ID, path-mapping, trạng thái bật/công bố**. Sau đó tính URL trước khi sửa cấu hình. Mã 404 chỉ cho biết chưa tìm được tài nguyên theo yêu cầu trong tình huống đó; nếu có bộ lọc bảo vệ hoặc proxy, cần kiểm tra thêm cách chúng xử lý yêu cầu.

## 10. Tự tính URL trước khi chạy

**Tình huống 1:** Không có đường dẫn nền, `base-path=/ops`, `path-mapping.health=ready`, chung cổng 8080.

Địa chỉ: `http://localhost:8080/ops/ready`. Endpoint ID vẫn là `health`; tên `ready` trong ví dụ không tự tạo nhóm readiness.

**Tình huống 2:** Servlet có context `/billing`, chung cổng 8080, `base-path=/monitor`, không ánh xạ riêng cho health.

Địa chỉ: `http://localhost:8080/billing/monitor/health`.

**Tình huống 3:** Cổng ứng dụng 8080 có context `/billing`, cổng quản trị riêng 9091 có `management.server.base-path=/internal`, `base-path=/monitor`, ánh xạ `health=alive`.

Địa chỉ: `http://localhost:9091/internal/monitor/alive`. Không thêm `/billing`.

**Tình huống 4:** Không có đường dẫn nền, chung cổng, `base-path=/`, ánh xạ `health=healthcheck`.

Địa chỉ: `http://localhost:8080/healthcheck`; trang khám phá Actuator ở gốc bị tắt, còn endpoint health vẫn có thể hoạt động khi đủ điều kiện.
