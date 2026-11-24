# Kết nối Eureka Server qua `serviceUrl.defaultZone`

## 1. Vai trò của `serviceUrl.defaultZone`

Trong Spring Cloud Service Discovery, Eureka Client cần biết địa chỉ của Eureka Server để đăng ký instance, gửi heartbeat, hủy đăng ký và tải registry. Thuộc tính `eureka.client.serviceUrl.defaultZone` (thường được viết trong YAML là `eureka.client.service-url.defaultZone`) cung cấp địa chỉ đó.

Giá trị của thuộc tính là URL gốc của Eureka REST API, ví dụ:

```text
http://localhost:8761/eureka/
```

Đây là địa chỉ mạng mà tiến trình Eureka Client có thể truy cập trực tiếp. Nó không phải tên service trong registry, không phải URL của một API nghiệp vụ và cũng không tự bật chức năng đăng ký hoặc tải registry. Những hành vi đó được điều khiển bằng các thuộc tính riêng như `register-with-eureka` và `fetch-registry`.

Trong module Spring Cloud Service Discovery, `DiscoveryClient` và `ServiceRegistry` cung cấp API ở mức Spring để khám phá hoặc đăng ký dịch vụ. Với Eureka, Eureka Client dùng `serviceUrl.defaultZone` để kết nối tới máy chủ registry thực hiện các thao tác tương ứng.

## 2. Cấu hình trong YAML

Một service tên `order-service` có thể khai báo địa chỉ Eureka Server như sau:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
```

Trong cấu hình này:

- `service-url.defaultZone` chỉ ra endpoint Eureka Server mà client sử dụng.
- `register-with-eureka: true` cho phép client đăng ký instance của ứng dụng lên registry.
- `fetch-registry: true` cho phép client tải registry để tìm các instance của service khác.

Hai cờ đăng ký và tải registry độc lập với nhau. Một ứng dụng có thể đăng ký nhưng không cần tải registry nếu nó không gọi dịch vụ khác qua discovery. Ngược lại, một consumer chỉ cần tìm dịch vụ có thể tắt đăng ký của chính nó.

### 2.1. Lưu ý về chữ hoa trong `defaultZone`

`serviceUrl` là một map cấu hình, trong đó `defaultZone` là tên khóa. Vì khóa map phân biệt chữ hoa và chữ thường, hãy giữ nguyên cách viết `defaultZone` với chữ `Z` viết hoa. Ví dụ dưới đây dễ gây lỗi cấu hình vì khóa đã bị đổi:

```yaml
eureka:
  client:
    service-url:
      defaultzone: http://localhost:8761/eureka/
```

Tên prefix `service-url` có thể dùng dạng kebab-case theo relaxed binding của Spring Boot; khóa `defaultZone` bên trong map phải giữ đúng chữ hoa. Khi xem tài liệu hoặc log, bạn cũng có thể gặp cách viết đầy đủ `eureka.client.serviceUrl.defaultZone`.

## 3. Cấu hình trong `application.properties`

Nếu dự án dùng properties thay vì YAML, khai báo trên một dòng:

```properties
spring.application.name=order-service
server.port=8081

eureka.client.serviceUrl.defaultZone=http://localhost:8761/eureka/
eureka.client.register-with-eureka=true
eureka.client.fetch-registry=true
```

Hai dạng YAML và properties có cùng mục đích. Hãy chọn một dạng phù hợp với cấu trúc cấu hình của dự án và tránh khai báo cùng một thuộc tính ở nhiều nơi với giá trị khác nhau, vì profile hoặc nguồn cấu hình có độ ưu tiên cao hơn có thể ghi đè giá trị bạn đang kiểm tra.

## 4. URL phải trỏ tới đâu?

Một Eureka Server Spring Cloud thường được chạy trên cổng `8761` và cung cấp Eureka API dưới context path `/eureka/`. Vì vậy, một địa chỉ thường gặp là `http://<host>:8761/eureka/`. Cổng và context path có thể thay đổi theo cấu hình triển khai; client phải dùng đúng địa chỉ mà server thực sự công bố.

Điều quan trọng là URL phải có thể truy cập từ môi trường đang chạy Eureka Client. `localhost` luôn có nghĩa là chính máy hoặc network namespace của tiến trình gọi URL đó, không phải máy của người dùng hay một container khác.

Ví dụ:

| Môi trường | URL ví dụ | Lý do |
|---|---|---|
| Client chạy cùng máy với Eureka Server | `http://localhost:8761/eureka/` | Hai tiến trình dùng chung network host |
| Client và server chạy trong hai container cùng Docker network | `http://eureka-server:8761/eureka/` | Client truy cập server qua DNS/service name trong network |
| Client chạy trên máy khác trong mạng nội bộ | `http://10.0.0.20:8761/eureka/` | Dùng địa chỉ server có thể định tuyến từ máy client |
| Server công bố endpoint bảo mật | `https://discovery.example.internal/eureka/` | Client kết nối qua HTTPS và phải tin cậy chứng thư của server |

Nếu `order-service` chạy trong container riêng, cấu hình `localhost:8761` thường khiến client tìm Eureka Server bên trong chính container `order-service`. Khi server nằm trong container khác, hãy dùng tên service hoặc hostname mà container client phân giải được, đồng thời bảo đảm hai container có kết nối mạng phù hợp.

Không nhầm URL của Eureka Server với URL của ứng dụng được đăng ký. Ví dụ, `http://order-service:8081/` là địa chỉ instance nghiệp vụ; `http://eureka-server:8761/eureka/` là địa chỉ registry mà client dùng để đăng ký và truy vấn.

## 5. Dùng biến môi trường cho từng môi trường triển khai

Địa chỉ Eureka Server thường khác nhau giữa máy phát triển, kiểm thử và production. Có thể đưa URL ra biến môi trường để không phải sửa mã nguồn khi triển khai:

```yaml
eureka:
  client:
    service-url:
      defaultZone: "${EUREKA_SERVER_URL:http://localhost:8761/eureka/}"
    register-with-eureka: true
    fetch-registry: true
```

Khi chạy ứng dụng, đặt `EUREKA_SERVER_URL` theo môi trường. Nếu không đặt biến này, Spring dùng URL mặc định trong biểu thức. Với production, nên quản lý URL và thông tin chứng thư qua cấu hình triển khai hoặc hệ thống quản lý secret của tổ chức; không đưa thông tin xác thực vào repository.

Có thể tách cấu hình bằng Spring profile, chẳng hạn `application-dev.yml` và `application-prod.yml`. Dù chọn profile hay biến môi trường, hãy xác minh giá trị cuối cùng mà ứng dụng thực sự nạp sau khi các nguồn cấu hình được hợp nhất.

## 6. Cấu hình nhiều Eureka Server URL

Trong môi trường có nhiều Eureka Server endpoint, một zone có thể khai báo nhiều URL phân tách bằng dấu phẩy:

```yaml
eureka:
  client:
    service-url:
      defaultZone: "http://eureka-1:8761/eureka/,http://eureka-2:8761/eureka/"
```

Danh sách này cung cấp nhiều endpoint để Eureka Client sử dụng khi kết nối tới registry. Khả năng tiếp tục hoạt động khi một endpoint lỗi còn phụ thuộc vào hành vi retry, cấu hình client và trạng thái cụm; khai báo nhiều URL không bảo đảm mọi yêu cầu sẽ thành công nếu các server đều không truy cập được.

Trong một cụm Eureka, các Eureka Server cần được cấu hình peer replication phù hợp để registry được đồng bộ giữa các node. Chỉ khai báo nhiều URL ở client không tự tạo cụm, không tự cấu hình replication và cũng không sửa được một node đang mất kết nối với các peer.

Ở cấu hình nhiều vùng (region/availability zone), Eureka có thể dùng các khóa zone và cấu hình region tương ứng để chọn danh sách URL phù hợp. Với triển khai đơn giản chỉ có một nhóm server, `defaultZone` thường là khóa cần dùng. Khi thiết kế nhiều region, cần cấu hình nhất quán region, availability zones và service URL ở các client/server theo kiến trúc thực tế.

## 7. Quan hệ giữa `defaultZone`, đăng ký và tải registry

`defaultZone` trả lời câu hỏi **client kết nối tới Eureka Server ở đâu**. Hai thuộc tính sau quyết định **client làm gì với registry**:

| Thuộc tính | Khi bật | Khi tắt |
|---|---|---|
| `eureka.client.register-with-eureka` | Đăng ký instance của ứng dụng, gia hạn lease và hủy đăng ký theo vòng đời client | Không đăng ký instance của ứng dụng lên Eureka Server |
| `eureka.client.fetch-registry` | Tải registry để khám phá instance của các ứng dụng khác | Không tải registry từ Eureka Server |

Ví dụ cấu hình cho một service chỉ cung cấp API và không gọi dịch vụ khác qua discovery:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
    register-with-eureka: true
    fetch-registry: false
```

Ví dụ cấu hình cho một thành phần chỉ cần khám phá các dịch vụ khác:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
    register-with-eureka: false
    fetch-registry: true
```

Trong thực tế, một microservice thường vừa đăng ký vừa tải registry nên cả hai cờ thường được bật. Một Eureka Server độc lập thường tắt cả hai chức năng client này để tránh tự đăng ký hoặc tải registry của chính nó; cấu hình peer trong cụm cần được cân nhắc riêng.

## 8. Kiểm tra kết nối khi Eureka Client không tìm thấy Server

Khi client không đăng ký được hoặc không tìm thấy service, hãy kiểm tra theo thứ tự từ URL đến trạng thái registry:

1. **Kiểm tra cấu hình cuối cùng:** xác nhận profile đang chạy, `serviceUrl.defaultZone` thực tế và khóa `defaultZone` viết đúng chữ hoa.
2. **Kiểm tra hostname và cổng:** từ đúng môi trường chạy client, xác nhận hostname phân giải được và cổng Eureka Server có thể kết nối.
3. **Kiểm tra context path:** xác nhận URL có đúng `/eureka/` hoặc context path mà server đang dùng. Sai path có thể trả về `404` dù hostname và cổng vẫn truy cập được.
4. **Kiểm tra giao thức:** dùng `http` hoặc `https` đúng với endpoint. Với HTTPS, kiểm tra chứng thư và truststore của JVM nếu client không tin cậy máy chủ.
5. **Kiểm tra log Eureka Client:** tìm các thông báo về kết nối server, đăng ký, heartbeat và tải registry; phân biệt lỗi DNS, timeout, connection refused và phản hồi HTTP.
6. **Kiểm tra trạng thái server:** xác nhận Eureka Server đang chạy, endpoint API hoạt động và registry có instance mong đợi.
7. **Kiểm tra các cờ chức năng:** nếu client không xuất hiện trên dashboard, xem `register-with-eureka`; nếu client không tìm thấy service khác, xem `fetch-registry` và chu kỳ làm mới registry.

Một số dấu hiệu thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `UnknownHostException` | Hostname không phân giải được trong môi trường client | Kiểm tra DNS, tên service và network của container |
| `Connection refused` | Không có tiến trình lắng nghe tại host/cổng hoặc kết nối bị từ chối | Kiểm tra server, port mapping và firewall |
| Timeout | Đường mạng bị chặn, server quá tải hoặc endpoint không phản hồi | Kiểm tra route, firewall, health và log server |
| HTTP `404` | Sai context path hoặc endpoint | Kiểm tra `/eureka/` và cấu hình context path |
| HTTP `401` hoặc `403` | Endpoint yêu cầu xác thực hoặc client không đủ quyền | Kiểm tra chính sách bảo mật và cấu hình xác thực |
| Kết nối thành công nhưng không thấy service | Client chưa fetch registry, ứng dụng chưa đăng ký hoặc registry chưa cập nhật | Kiểm tra hai cờ, trạng thái instance và chu kỳ fetch |

Có thể kiểm tra endpoint từ môi trường client bằng công cụ HTTP, ví dụ:

```bash
curl -i http://eureka-server:8761/eureka/apps
```

Lệnh này chỉ là phép thử kết nối và đọc registry; kết quả cụ thể phụ thuộc cấu hình bảo mật, định dạng phản hồi và phiên bản Eureka Server. Nếu endpoint yêu cầu HTTPS hoặc xác thực, hãy bổ sung cấu hình tương ứng cho công cụ kiểm tra. Truy cập được dashboard trên trình duyệt máy phát triển chưa chứng minh rằng một container production cũng truy cập được URL đó.

## 9. Ví dụ hoàn chỉnh: service kết nối Eureka trong Docker network

Giả sử Eureka Server có tên service `eureka-server`, lắng nghe cổng `8761`, còn `order-service` chạy trong container khác trên cùng Docker network. Cấu hình phía `order-service` có thể là:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: "${EUREKA_SERVER_URL:http://eureka-server:8761/eureka/}"
    register-with-eureka: true
    fetch-registry: true
```

Ở đây, tên `eureka-server` phải khớp với DNS/service name mà Docker network cung cấp. Nếu chạy ứng dụng trực tiếp trên máy phát triển bên ngoài Docker network, có thể đặt `EUREKA_SERVER_URL` thành URL được publish ra host, chẳng hạn `http://localhost:8761/eureka/` nếu cổng đó đã được ánh xạ.

Sau khi khởi động, có thể xác minh theo ba bước: log `order-service` cho thấy client kết nối và đăng ký; dashboard hoặc API registry của Eureka Server hiển thị instance `ORDER-SERVICE`; một consumer có `fetch-registry: true` tải được instance và có thể chọn nó qua cơ chế discovery/load balancing.

## 10. Những điểm cần ghi nhớ

- `eureka.client.serviceUrl.defaultZone` xác định URL Eureka Server mà Eureka Client kết nối tới.
- Giữ nguyên chữ hoa trong khóa map `defaultZone`; có thể dùng prefix YAML `service-url` hoặc dạng properties `serviceUrl`.
- URL phải truy cập được từ môi trường chạy client và phải trỏ đúng context path của Eureka API.
- `localhost` trong container là chính container đó; dùng DNS/service name hoặc hostname có thể định tuyến để kết nối container khác.
- Có thể khai báo nhiều URL cho một zone, nhưng cần cấu hình peer replication và kiểm tra retry/failover của cụm riêng.
- `register-with-eureka` và `fetch-registry` là hai chức năng độc lập; `defaultZone` chỉ cung cấp địa chỉ kết nối.

Khi cấu hình đúng `serviceUrl.defaultZone`, Eureka Client có thể trao đổi với registry. Việc instance có được đăng ký, consumer có tải được registry và request có đến đúng instance hay không còn phụ thuộc vào các cờ chức năng, trạng thái server, mạng và cấu hình load balancing của ứng dụng.
