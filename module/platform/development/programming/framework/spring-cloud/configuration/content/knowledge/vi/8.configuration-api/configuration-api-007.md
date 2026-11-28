# Kiểm tra mã HTTP khi thiếu tài nguyên, lỗi xác thực hoặc lỗi kho

Spring Cloud Config Server cung cấp cấu hình qua HTTP, vì vậy mã trạng thái HTTP là tín hiệu đầu tiên để xác định request đã đến đúng endpoint, người gọi có quyền truy cập hay backend Git có đọc được dữ liệu hay không. Tuy nhiên, không thể kết luận mọi trường hợp thiếu file đều trả `404`, hoặc mọi lỗi Git đều trả cùng một mã. Cần hiểu cách Config Server xử lý cấu hình rỗng, cách Spring Security bảo vệ endpoint và cách reverse proxy chuyển tiếp lỗi.

Khi một Config Client không lấy được cấu hình, hãy phân loại lỗi theo ba lớp: request và tài nguyên được yêu cầu; xác thực và phân quyền; kết nối giữa Config Server với kho cấu hình. Phân biệt các lớp này giúp sửa đúng nguyên nhân và tránh biến một lỗi quyền truy cập thành lỗi cấu hình mặc định khó phát hiện.

## 1. Các endpoint và phản hồi thành công

Config Server thường cung cấp một endpoint Environment dạng JSON theo application, profile và label:

```text
GET /{application}/{profile}/{label}
```

Ví dụ:

```bash
curl -i http://localhost:8888/order-service/prod/main
```

Response JSON mô tả tên ứng dụng, profile, label và danh sách `propertySources`. Mỗi property source chứa các thuộc tính lấy từ repository hoặc nguồn cấu hình đã khai báo. Client có thể sử dụng response này để xây dựng môi trường thuộc tính của ứng dụng.

Config Server cũng hỗ trợ các endpoint trả nội dung theo định dạng, chẳng hạn:

```text
GET /{application}-{profile}.yml
GET /{application}-{profile}.properties
```

Ví dụ:

```bash
curl -i http://localhost:8888/order-service-prod.yml
curl -i http://localhost:8888/order-service-prod.properties
```

Các endpoint này hữu ích khi kiểm tra nhanh một file cấu hình theo profile. Khi cần kiểm tra label cụ thể hoặc toàn bộ property source, endpoint Environment dạng JSON thường dễ quan sát hơn. Đường dẫn thực tế còn phụ thuộc context path, tiền tố Config Server và cấu hình reverse proxy.

Một response `200 OK` cho biết request đã được xử lý thành công ở tầng HTTP. Nó không đảm bảo mọi thuộc tính mà ứng dụng mong đợi đều tồn tại. Hãy đọc `propertySources` và xác nhận các khóa bắt buộc, profile và label trong response.

## 2. Thiếu cấu hình không phải lúc nào cũng là HTTP 404

Một trường hợp dễ gây hiểu nhầm là Config Server không tìm thấy file cho application/profile được yêu cầu. Theo mặc định, Config Server có thể chấp nhận kết quả rỗng và trả một Environment không có property source thay vì báo lỗi HTTP. Thuộc tính `spring.cloud.config.server.accept-empty` điều khiển hành vi này; mặc định là `true`.

Ví dụ response thành công nhưng không có cấu hình:

```json
{
  "name": "order-service",
  "profiles": ["prod"],
  "label": "main",
  "propertySources": []
}
```

Đây là `200 OK` với danh sách property source rỗng. Client có thể tiếp tục với các nguồn cấu hình khác hoặc default trong ứng dụng, tùy cách thiết lập. Trong production, hành vi này có thể nguy hiểm nếu các giá trị từ xa là bắt buộc nhưng ứng dụng vẫn khởi động bằng default.

Nếu muốn Config Server trả `404 Not Found` khi không có cấu hình cho request, có thể đặt:

```yaml
spring:
  cloud:
    config:
      server:
        accept-empty: false
```

Khi đó, trường hợp không có property source có thể được báo thành lỗi không tìm thấy môi trường. Trước khi bật tùy chọn này, cần xác nhận các ứng dụng thực sự phải có cấu hình từ xa và quy ước file chung như `application.yml` đã được tính đến.

Phân biệt các tình huống sau:

| Tình huống | Kết quả thường gặp | Cách hiểu |
|---|---|---|
| Có file cấu hình phù hợp | `200 OK` và có `propertySources` | Server đã tìm thấy cấu hình |
| Không có file/thuộc tính nào phù hợp, `accept-empty=true` | `200 OK`, `propertySources` rỗng | Request hợp lệ nhưng không có cấu hình từ xa |
| Không có cấu hình và `accept-empty=false` | `404 Not Found` | Server được cấu hình để từ chối Environment rỗng |
| Label Git không tồn tại | Thường là `404 Not Found` | Phiên bản cấu hình được yêu cầu không có trong repository |
| Sai URL, context path hoặc prefix | `404 Not Found` | Request có thể chưa tới đúng endpoint Config Server |

Nếu file `order-service-prod.yml` không tồn tại nhưng `application.yml` hoặc `order-service.yml` vẫn cung cấp thuộc tính, Environment có thể không rỗng. Vì vậy, phải kiểm tra toàn bộ property source của request thay vì chỉ tìm một file theo tên profile.

## 3. Phân biệt 401 và 403

Config Server có thể được bảo vệ bằng Spring Security, reverse proxy hoặc API gateway. Khi request không được chấp nhận, hãy phân biệt xác thực với phân quyền:

- `401 Unauthorized`: request thiếu thông tin xác thực hợp lệ, ví dụ không gửi token, token hết hạn hoặc username/password không đúng. API có thể trả header `WWW-Authenticate` để chỉ ra cơ chế xác thực.
- `403 Forbidden`: danh tính đã được nhận diện nhưng không được phép truy cập tài nguyên hoặc application được yêu cầu.

Ví dụ, nếu Config Server dùng HTTP Basic Authentication, có thể kiểm tra bằng biến môi trường đã được cấp an toàn:

```bash
curl -i --user "${CONFIG_USER}" \
  http://localhost:8888/order-service/prod/main
```

Với curl tương tác trong terminal, khi chỉ cung cấp tên người dùng, công cụ sẽ hỏi mật khẩu. Không ghi credential trực tiếp vào script được commit, tài liệu dùng chung hoặc lệnh được lưu trong lịch sử shell. Trong hệ thống production, ưu tiên token hoặc cơ chế danh tính của nền tảng, TLS và secret manager theo chính sách tổ chức.

Một số cấu hình Spring Security dùng form login có thể trả `302 Found` và chuyển hướng đến trang đăng nhập thay vì trả `401`. Đây thường không phải hành vi phù hợp cho Config Client không tương tác. Với API machine-to-machine, nên cấu hình xác thực rõ ràng và response không chuyển hướng, đồng thời kiểm tra header `Location` nếu client nhận `302` bất ngờ.

Nếu gateway đứng trước Config Server, `401` hoặc `403` có thể do gateway tạo ra trước khi request đến ứng dụng. Kiểm tra log ở cả hai lớp để biết thành phần nào từ chối request.

## 4. Lỗi từ Git repository và backend cấu hình

Config Server có thể xác thực người gọi thành công nhưng vẫn không đọc được repository. Đây là lỗi giữa Config Server và backend, khác với việc Config Client không có quyền truy cập API.

Các nguyên nhân thường gặp gồm:

- Git URI sai, repository đã bị di chuyển hoặc bị xóa.
- Credential mà Config Server dùng để clone/fetch đã hết hạn hoặc không còn quyền đọc.
- Branch, tag hoặc commit label không tồn tại.
- DNS, proxy, firewall hoặc TLS khiến Config Server không kết nối được Git host.
- Repository quá lớn, clone/fetch timeout hoặc thư mục cache local gặp lỗi.
- File YAML/properties không hợp lệ khiến quá trình đọc hoặc phân tích cấu hình thất bại.

Lỗi label không tồn tại thường được biểu diễn bằng `404`, còn lỗi truy cập hoặc xử lý backend có thể thành `5xx`, thường là `500 Internal Server Error`. Nếu Config Server nằm sau gateway hoặc load balancer, lỗi kết nối upstream có thể xuất hiện thành `502 Bad Gateway`, `503 Service Unavailable` hoặc `504 Gateway Timeout`. Mã chính xác phụ thuộc phiên bản, loại repository, exception handler và lớp proxy; không nên viết logic vận hành dựa trên giả định mọi lỗi Git đều có cùng một status.

| Mã HTTP | Khả năng liên quan đến backend | Hướng điều tra |
|---|---|---|
| `404` | Label không tồn tại hoặc Environment rỗng bị từ chối | Kiểm tra label, branch/tag, application/profile và `accept-empty` |
| `500` | Config Server gặp lỗi khi clone, fetch, đọc hoặc parse cấu hình | Xem log server, Git URI, credential, TLS, file cấu hình và stack trace nội bộ |
| `502` | Proxy không nhận được phản hồi hợp lệ từ upstream | Kiểm tra upstream host/port, kết nối và log proxy |
| `503` | Server hoặc backend tạm thời không sẵn sàng | Kiểm tra health, quá tải, maintenance và khả năng phục hồi |
| `504` | Proxy hoặc gateway chờ backend quá thời gian | Kiểm tra timeout, thời gian clone/fetch và độ trễ mạng |

Không trả stack trace, đường dẫn file nội bộ, Git credential hoặc chi tiết xác thực ra response công khai. Thông tin chẩn đoán đầy đủ nên nằm trong log có kiểm soát truy cập, kèm request ID để đối chiếu.

## 5. Phân tích 404: sai endpoint hay thiếu tài nguyên?

`404 Not Found` có thể đến từ nhiều lớp. Trước khi kết luận repository thiếu file, hãy kiểm tra theo thứ tự:

1. **Đường dẫn HTTP:** request có đi đúng host, cổng, context path và `spring.cloud.config.server.prefix` không?
2. **Định tuyến proxy:** reverse proxy có loại bỏ hoặc thêm prefix không đúng không?
3. **Tên application:** `spring.application.name` ở client có khớp tên file cấu hình không?
4. **Profile:** client có gửi đúng profile, ví dụ `prod` hay `production` không?
5. **Label:** branch, tag hoặc commit mà client yêu cầu có tồn tại trong repository được chọn không?
6. **File và search path:** file có nằm trong repository/nhánh/search path mà Config Server đang sử dụng không?
7. **Chính sách Environment rỗng:** `accept-empty` có được đặt thành `false` khiến server trả 404 không?

Ví dụ client khai báo:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888/config"
```

Nếu Config Server có prefix `/config`, client phải gọi base URL có `/config`. Nếu server không khai báo prefix, đoạn này có thể làm request đi vào một đường dẫn không tồn tại. Tương tự, `spring.application.name: order-service` thường dẫn server tìm các file như `order-service.yml`; tên `orders-service` sẽ tạo yêu cầu khác.

Để tách lỗi URL khỏi lỗi repository, gọi endpoint từ cùng mạng với client và dùng đúng application/profile/label. Sau đó kiểm tra log Config Server để biết request có đến controller và backend repository hay không.

## 6. Kiểm tra bằng curl và đọc response

`curl -i` hiển thị status line, header và body. Đây là cách nhanh để xác định response đến từ Config Server hay proxy:

```bash
curl -i \
  http://localhost:8888/order-service/prod/main
```

Để lưu body và header riêng trong lúc điều tra:

```bash
curl -sS \
  -D response-headers.txt \
  -o response-body.json \
  http://localhost:8888/order-service/prod/main
```

Sau đó kiểm tra status trong `response-headers.txt` và `propertySources` trong body. Nếu server trả `200` nhưng mảng `propertySources` rỗng, kiểm tra `accept-empty`, tên file và repository. Nếu trả `401` hoặc `403`, kiểm tra Security trước khi điều tra Git. Nếu trả `5xx`, đối chiếu log Config Server với thời điểm request.

Với API cần xác thực, thêm header/token theo cơ chế của hệ thống. Không bật trace hoặc ghi header Authorization vào log chia sẻ. Nếu dùng `curl -v`, lưu ý output verbose có thể chứa thông tin xác thực hoặc cookie.

### Phân biệt phản hồi của Config Server và proxy

Header `Server`, `Via`, request ID và định dạng body có thể gợi ý thành phần tạo response, nhưng không phải bằng chứng tuyệt đối vì proxy có thể thay đổi header. Cách chắc chắn hơn là so sánh:

- Request trực tiếp đến Config Server từ mạng nội bộ.
- Request đi qua ingress hoặc gateway.
- Log access của proxy và log ứng dụng tại cùng thời điểm.

Nếu request trực tiếp thành công nhưng request qua proxy thất bại, tập trung vào route, rewrite path, TLS, timeout và xác thực tại gateway. Nếu cả hai đều thất bại, tiếp tục kiểm tra Config Server và repository.

## 7. Health endpoint không thay thế kiểm tra API cấu hình

Spring Boot Actuator có thể cung cấp endpoint health, thường là `/actuator/health` nếu giữ base path mặc định. Endpoint này cho biết tình trạng của ứng dụng và các health indicator được cấu hình. Nó không nhất thiết xác nhận rằng một request cụ thể cho `order-service/prod/main` có thể lấy được đúng cấu hình.

Một Config Server có thể báo health tổng thể là `UP` nhưng một label không tồn tại, một application không có file hoặc một repository riêng gặp lỗi khi được truy cập. Ngược lại, health check có thể báo `DOWN` do một dependency không bắt buộc, trong khi một số request cấu hình vẫn phục vụ được từ cache. Hãy xác định rõ health indicator đang kiểm tra gì.

Với nhiều Git repository, kiểm tra một endpoint đại diện cho một ứng dụng không đảm bảo mọi repository đều sẵn sàng. Nên có kiểm tra tổng hợp hoặc giám sát theo từng repository quan trọng, nhưng không để health check công khai tiết lộ tên kho, credential hay cấu trúc nội bộ.

## 8. Xử lý lỗi ở Config Client

Config Client thường lấy cấu hình trong giai đoạn khởi động khi dùng `spring.config.import`. Nếu Config Server không truy cập được hoặc trả lỗi, ứng dụng có thể dừng khởi động tùy cấu hình import và cách lỗi được phân loại.

Ví dụ import bắt buộc:

```yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
```

Nếu dịch vụ được phép khởi động với cấu hình còn lại khi Config Server không sẵn sàng, có thể dùng import tùy chọn:

```yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
```

Chỉ dùng `optional:` khi ứng dụng có default an toàn và nhóm chấp nhận hành vi thiếu cấu hình từ xa. Nếu các thuộc tính như endpoint database hoặc chế độ bảo mật bắt buộc phải lấy từ Config Server, cho ứng dụng khởi động với giá trị mặc định có thể làm che giấu lỗi triển khai. `optional:` không sửa lỗi xác thực, không cấp quyền truy cập và không làm backend Git hoạt động trở lại.

Với lỗi mạng hoặc `5xx` tạm thời, có thể cấu hình retry có giới hạn và backoff tăng dần nếu phiên bản Config Client đang dùng hỗ trợ. Tránh retry vô hạn hoặc retry dồn dập khi Config Server/Git đang quá tải. Lỗi `401`, `403`, profile sai hoặc label không tồn tại thường cần sửa cấu hình hoặc quyền truy cập, không nên xử lý bằng retry liên tục.

Trong môi trường production, hãy xác định rõ:

- Thuộc tính nào bắt buộc phải có từ Config Server.
- Dịch vụ có được khởi động khi server tạm thời không truy cập được không.
- Retry bao nhiêu lần, khoảng nghỉ và tổng thời gian chờ tối đa.
- Khi nào cần dừng rollout và phát cảnh báo.
- Cách rollback về label/commit cấu hình đã biết là tốt.

## 9. Checklist chẩn đoán theo mã HTTP

| Mã/kết quả | Câu hỏi đầu tiên | Hành động tiếp theo |
|---|---|---|
| `200` có dữ liệu | Đúng application, profile, label và khóa cần dùng chưa? | Kiểm tra `propertySources` và thứ tự ưu tiên |
| `200` rỗng | `accept-empty` có đang giữ mặc định `true` không? | Kiểm tra file chung, file ứng dụng, profile, search path và label |
| `301`/`302` | Có redirect từ proxy hoặc form login không? | Kiểm tra `Location`, scheme HTTPS và cấu hình Security |
| `400` | Request path, tham số hoặc định dạng có hợp lệ không? | Kiểm tra URL encode, tên profile/label và log request |
| `401` | Client đã gửi đúng credential/token chưa? | Kiểm tra issuer, audience, expiry, header và TLS |
| `403` | Danh tính có quyền đọc application này không? | Kiểm tra role/authority và chính sách theo ứng dụng |
| `404` | Endpoint sai, cấu hình rỗng, file thiếu hay label sai? | Kiểm tra path, `accept-empty`, repository, branch và profile |
| `429` | Có rate limit ở gateway không? | Kiểm tra quota, `Retry-After` và nhịp gọi của client |
| `500` | Config Server có lỗi khi đọc hoặc phân tích backend không? | Kiểm tra log server, Git, YAML và cache |
| `502`/`503`/`504` | Proxy/backend có sẵn sàng và phản hồi đúng hạn không? | Kiểm tra upstream, health, timeout và mạng |

Mã `400` và `429` thường được tạo bởi validation hoặc gateway tùy hệ thống; không phải mọi phiên bản Config Server đều phát sinh các mã này cho cùng một nguyên nhân. Bảng là hướng khoanh vùng, cần đối chiếu response thực tế và log của lớp tạo ra nó.

## 10. Nguyên tắc xử lý lỗi an toàn

- Không xem `200 OK` là bằng chứng cấu hình đầy đủ; luôn kiểm tra property source và các khóa bắt buộc.
- Cân nhắc `spring.cloud.config.server.accept-empty=false` nếu môi trường cần từ chối Environment rỗng.
- Phân biệt `401` (chưa xác thực hợp lệ) với `403` (đã xác thực nhưng thiếu quyền).
- Không nhầm credential của Config Client gọi API với credential Config Server dùng để đọc Git.
- Phân biệt label không tồn tại với Git backend không truy cập được; mã HTTP có thể khác nhau.
- Kiểm tra URL, context path, prefix và proxy rewrite trước khi kết luận tài nguyên không tồn tại.
- Dùng retry có giới hạn cho lỗi tạm thời; sửa trực tiếp lỗi cấu hình và quyền truy cập.
- Không để response hoặc log chia sẻ lộ token, mật khẩu, private key, stack trace hay nội dung bí mật.
- Gắn request ID và thời điểm để đối chiếu log giữa client, gateway, Config Server và Git host.

Mã HTTP của Config Server chỉ có ý nghĩa khi được đọc cùng body, header, cấu hình `accept-empty`, chính sách bảo mật và trạng thái Git backend. Khi phân loại được lỗi request, lỗi quyền và lỗi kho cấu hình, nhóm có thể xử lý chính xác, giữ cho ứng dụng không âm thầm chạy bằng cấu hình thiếu và duy trì quá trình phân phối cấu hình đáng tin cậy.

## Tài liệu tham khảo

- [Spring Cloud Config Server — tài liệu chính thức](https://docs.spring.io/spring-cloud-config/reference/server.html)
- [Spring Cloud Config Client — tài liệu chính thức](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
