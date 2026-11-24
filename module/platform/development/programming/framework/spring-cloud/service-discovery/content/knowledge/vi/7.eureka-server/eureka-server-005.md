# Đọc Dashboard và kiểm tra ứng dụng cùng các instance

Eureka Server cung cấp một Dashboard để người vận hành quan sát các ứng dụng đã đăng ký và những instance mà registry đang lưu. Khi một service không xuất hiện, có trạng thái bất thường hoặc consumer không gọi được instance, Dashboard là điểm kiểm tra ban đầu hữu ích.

Dashboard phản ánh dữ liệu mà Eureka Server đang biết tại thời điểm hiển thị. Một dòng instance có trạng thái `UP` không phải là bảo đảm rằng request tiếp theo chắc chắn thành công: dữ liệu có thể trễ do heartbeat, cache, mạng hoặc cơ chế self-preservation. Vì vậy, cần kết hợp thông tin trên Dashboard với địa chỉ instance, endpoint health, log của ứng dụng và REST API của Eureka.

Bài học thuộc module `SPRING_CLOUD_SERVICE_DISCOVERY`, tập trung vào việc tìm instance bằng tên dịch vụ qua `DiscoveryClient`, `ServiceRegistry`, Eureka hoặc Consul, đồng thời hiểu vòng đời đăng ký, health check, load balancing, bảo mật và xử lý sai lệch registry. Nội dung này hướng dẫn đọc các vùng chính trên Eureka Dashboard và kiểm tra một ứng dụng từ cấp service đến từng instance.

## 1. Mở Eureka Dashboard

Trong cấu hình phát triển phổ biến, Eureka Server chạy ở cổng `8761`. Nếu không đổi context path hoặc cấu hình endpoint, mở địa chỉ:

```text
http://localhost:8761/
```

Dashboard là giao diện web do Eureka Server cung cấp. Đường dẫn truy cập thực tế phụ thuộc `server.port`, `server.servlet.context-path`, cấu hình reverse proxy và cách triển khai. Nếu chạy trong container hoặc máy chủ từ xa, thay `localhost` bằng hostname hoặc địa chỉ có thể truy cập từ máy quản trị.

Một ứng dụng Eureka Server tối giản thường có cấu hình như sau:

```yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
```

Và bật Eureka Server trong ứng dụng Spring Boot:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
```

Hai thuộc tính `register-with-eureka: false` và `fetch-registry: false` thường được dùng cho server độc lập để server không tự đăng ký và tra cứu chính nó như một Eureka client. Trong cụm peer-aware, cấu hình client và danh sách peer sẽ khác; không sao chép nguyên cấu hình standalone cho mọi topology.

## 2. Nhận diện các vùng trên Dashboard

Tên và cách sắp xếp một số nhãn có thể thay đổi theo phiên bản Eureka, nhưng Dashboard thường có các khu vực chính sau:

| Khu vực | Nội dung | Mục đích kiểm tra |
|---|---|---|
| System Status | Thông tin trạng thái của Eureka Server như môi trường, datacenter, thời gian chạy hoặc thông tin vận hành liên quan. | Xác nhận đang mở đúng server và server đã khởi động. |
| DS Replicas | Các peer/replica Eureka mà server biết. | Kiểm tra cấu hình peer và khả năng liên lạc giữa các server. |
| Instances currently registered with Eureka | Danh sách ứng dụng và các instance đã đăng ký. | Kiểm tra service ID, số instance và trạng thái từng instance. |
| General Info hoặc thông tin bổ sung | Một số thông tin về registry, lease, renewal hoặc cấu hình tùy phiên bản. | Hỗ trợ điều tra heartbeat, eviction và self-preservation. |

<text color="secondary" size="sm">Dashboard thực tế phụ thuộc phiên bản Spring Cloud Netflix Eureka, phiên bản Eureka Server và cấu hình giao diện. Các nhãn trong bảng là cách nhận diện theo chức năng, không phải cam kết mọi phiên bản có cùng bố cục.</text>

## 3. Đọc danh sách ứng dụng đã đăng ký

Vùng `Instances currently registered with Eureka` là nơi quan trọng nhất khi kiểm tra provider. Eureka thường nhóm các instance theo application/service name. Ví dụ, `ORDER-SERVICE` có thể có ba instance:

| Application | Instance ID minh họa | Host/Port | Status |
|---|---|---|---|
| `ORDER-SERVICE` | `order-01` | `10.0.1.21:8080` | `UP` |
| `ORDER-SERVICE` | `order-02` | `10.0.1.22:8080` | `UP` |
| `ORDER-SERVICE` | `order-03` | `10.0.2.15:8080` | `OUT_OF_SERVICE` |

Tên ứng dụng thường được hiển thị ở dạng chữ hoa trong giao diện Eureka, dù `spring.application.name` trong cấu hình có thể được viết thường. Hãy đối chiếu service ID mà consumer tra cứu với tên ứng dụng được đăng ký; không dựa vào cách viết hoa/thường trên giao diện để suy ra instance ID.

Khi đọc một nhóm ứng dụng, kiểm tra lần lượt:

1. **Application name:** có đúng service ID mà consumer sử dụng không?
2. **Số lượng instance:** số bản chạy trên Dashboard có phù hợp với số replica dự kiến không?
3. **Instance ID:** từng bản chạy có định danh riêng và không bị trùng ngoài ý muốn không?
4. **Host và port:** địa chỉ có thể truy cập từ mạng của consumer không?
5. **Status:** instance có đang ở trạng thái đủ điều kiện phục vụ không?
6. **Links và metadata:** status page, home page, health URL hoặc metadata có trỏ tới địa chỉ phù hợp không?

Số instance trên Dashboard là số bản ghi Eureka đang giữ, không nhất thiết bằng số process đang chạy ở mọi thời điểm. Một process có thể chưa đăng ký; một bản ghi cũ cũng có thể còn tồn tại sau khi process đã dừng.

## 4. Hiểu trạng thái của instance

Eureka biểu diễn trạng thái instance bằng các giá trị như `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE` và `UNKNOWN`. Ý nghĩa thực tế cần được xem cùng cấu hình health và lifecycle của client.

| Status | Ý nghĩa khái quát | Cách kiểm tra tiếp |
|---|---|---|
| `UP` | Instance được Eureka ghi nhận là đang hoạt động. | Kiểm tra endpoint thực tế và khả năng kết nối từ consumer. |
| `DOWN` | Instance được đánh dấu không hoạt động. | Xem health, log client, lỗi heartbeat hoặc cập nhật trạng thái. |
| `STARTING` | Instance đang trong giai đoạn khởi động. | Kiểm tra readiness và thời điểm ứng dụng bắt đầu đăng ký. |
| `OUT_OF_SERVICE` | Instance được đánh dấu không phục vụ traffic. | Kiểm tra thao tác bảo trì, trạng thái ứng dụng hoặc quy trình shutdown. |
| `UNKNOWN` | Eureka chưa có trạng thái xác định phù hợp. | Kiểm tra quá trình đăng ký, cập nhật status và cấu hình health. |

Không nên coi màu sắc của dòng trạng thái là hợp đồng ổn định giữa các phiên bản Dashboard. Hãy đọc giá trị status và đối chiếu với API hoặc log khi cần xác nhận.

### 4.1. `UP` không đồng nghĩa endpoint chắc chắn khỏe

Eureka client thường duy trì registration bằng heartbeat/lease. Tùy cấu hình, client có thể tích hợp trạng thái sức khỏe của ứng dụng. Nếu health check chưa được tích hợp, một tiến trình còn gửi heartbeat có thể vẫn được registry xem là `UP` dù endpoint nghiệp vụ đã lỗi.

Để client dùng trạng thái health của Spring Boot Actuator, cần expose endpoint phù hợp và bật health check integration theo cấu hình của phiên bản đang sử dụng. Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info

eureka:
  client:
    healthcheck:
      enabled: true
  instance:
    status-page-url-path: ${management.endpoints.web.base-path}/info
    health-check-url-path: ${management.endpoints.web.base-path}/health
```

Với cấu hình mặc định của Spring Boot Actuator, base path thường là `/actuator`; nếu đã thay đổi `management.endpoints.web.base-path`, các URL phải khớp với giá trị thực tế. Bảo đảm endpoint health được expose và bảo vệ đúng cách. Không mở endpoint quản trị ra mạng công khai chỉ để Dashboard có thể hiển thị link.

## 5. Kiểm tra một instance cụ thể

Khi đã tìm được ứng dụng trên Dashboard, chọn instance cần điều tra và ghi nhận các thông tin sau:

- **Instance ID:** định danh bản chạy cần kiểm tra.
- **Host name / IP address:** địa chỉ được công bố cho consumer.
- **Port:** cổng ứng dụng đăng ký.
- **Status:** trạng thái hiện tại mà Eureka lưu.
- **Home page URL:** URL gốc được khai báo cho instance, nếu có.
- **Status page URL:** trang thông tin trạng thái ứng dụng, nếu được khai báo.
- **Health check URL:** endpoint health được tích hợp hoặc công bố, tùy cấu hình và giao diện.
- **Metadata:** thông tin bổ sung như zone, version, instance group hoặc dữ liệu do ứng dụng công bố.

Các URL trên thường được hình thành từ thông tin registration. Việc Dashboard hiển thị link không có nghĩa Eureka đã gọi endpoint đó thành công mỗi lần trang được mở. Hãy mở hoặc gọi endpoint từ một máy có cùng góc nhìn mạng với consumer để xác minh DNS, routing, firewall và TLS.

### 5.1. Kiểm tra endpoint từ máy consumer

Ví dụ instance đăng ký `10.0.1.21:8080` và expose Actuator health ở `/actuator/health`. Có thể kiểm tra bằng `curl`:

```bash
curl -i http://10.0.1.21:8080/actuator/health
```

Nếu service dùng HTTPS hoặc cần xác thực, dùng scheme và credential phù hợp với môi trường. Không đưa token hoặc mật khẩu thật vào lệnh lưu trong tài liệu, shell history hay log chia sẻ.

Khi endpoint không truy cập được, chia nhỏ kiểm tra:

1. Host có phân giải DNS đúng không?
2. Port có mở từ mạng consumer không?
3. Ứng dụng có bind vào interface mà consumer truy cập được không?
4. Container port, service port hoặc reverse proxy có ánh xạ đúng không?
5. TLS certificate và hostname có khớp không?
6. Endpoint có yêu cầu authentication hoặc quyền truy cập riêng không?

Nếu kiểm tra từ chính máy provider thành công nhưng từ consumer thất bại, vấn đề có thể nằm ở network route, firewall, DNS hoặc địa chỉ đăng ký chứ không phải logic discovery.

## 6. Kiểm tra ứng dụng có đăng ký đúng với Eureka không

Một Eureka client cần dependency phù hợp, service ID và URL Eureka Server có thể truy cập. Cấu hình client minh họa:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
  instance:
    prefer-ip-address: true
```

Trong môi trường nhiều máy hoặc container, `localhost` chỉ trỏ về chính container/máy đang chạy client. Hãy thay bằng địa chỉ Eureka Server mà client thực sự truy cập được. `prefer-ip-address: true` khiến client công bố IP thay vì hostname trong một số cấu hình; chỉ bật khi IP đó có thể định tuyến từ các consumer liên quan.

Khi ứng dụng không xuất hiện trên Dashboard, kiểm tra theo thứ tự:

1. Ứng dụng có khởi động hoàn tất và có Eureka client starter trên classpath không?
2. `spring.application.name` có đúng service ID mong muốn không?
3. `eureka.client.service-url.defaultZone` có đúng URL và có dấu `/eureka/` theo cấu hình server không?
4. Client có kết nối được tới Eureka Server không? Kiểm tra DNS, port, TLS, proxy và authentication.
5. Auto-registration có bị tắt hoặc bị điều kiện cấu hình vô hiệu hóa không?
6. Client log có báo lỗi đăng ký, lỗi renew heartbeat hoặc lỗi serialize metadata không?
7. Server có đang nhận registration ở đúng profile, namespace hoặc cụm không?

Dashboard không hiển thị ứng dụng ngay sau khi process vừa khởi động chưa chắc là lỗi. Cần xem log client và chờ chu kỳ đăng ký/đồng bộ phù hợp với cấu hình thay vì kết luận chỉ từ một lần refresh.

## 7. Kiểm tra bằng Eureka REST API

Dashboard thuận tiện cho quan sát trực quan; REST API hữu ích khi cần kiểm tra dữ liệu có cấu trúc, viết script giám sát hoặc so sánh kết quả giữa các server. Với cấu hình mặc định phổ biến, Eureka API nằm dưới context `/eureka`.

| Request | Mục đích |
|---|---|
| `GET /eureka/apps` | Lấy danh sách ứng dụng và các registration. |
| `GET /eureka/apps/{appName}` | Lấy thông tin một ứng dụng theo tên. |
| `GET /eureka/apps/{appName}/{instanceId}` | Lấy thông tin một instance cụ thể. |

Ví dụ đọc danh sách ứng dụng ở định dạng JSON:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps
```

Đọc một ứng dụng:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/ORDER-SERVICE
```

Đọc một instance:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/ORDER-SERVICE/order-01
```

`appName` và `instanceId` phải khớp dữ liệu registration. Tùy phiên bản, server context path, reverse proxy và cấu hình bảo mật, URL thực tế hoặc định dạng phản hồi có thể khác. Các ví dụ trên chỉ dùng GET để đọc dữ liệu; thao tác POST/PUT/DELETE lên registry có thể làm thay đổi trạng thái hệ thống và cần được kiểm soát riêng.

Khi so sánh Dashboard và API, hãy kiểm tra cùng một Eureka Server, cùng thời điểm và cùng service ID. Nếu hai kết quả khác nhau, xem thêm cache, replica và thời điểm cập nhật.

## 8. Đọc DS Replicas và kiểm tra cụm Eureka

Trong triển khai peer-aware, khu vực `DS Replicas` hiển thị các server peer mà node hiện tại biết. Mục này giúp kiểm tra cấu hình liên kết giữa các Eureka Server.

Khi vận hành cụm, hãy xác minh:

- Danh sách peer có đúng hostname và port của các server dự kiến không?
- Các peer có thể phân giải DNS và kết nối qua mạng không?
- Cấu hình `eureka.client.service-url.defaultZone` trên từng server có trỏ tới peer phù hợp không?
- Các server có đang dùng cùng cách định danh và cấu hình datacenter/region theo kiến trúc dự kiến không?
- Có cảnh báo replication, heartbeat hoặc lỗi kết nối peer trong log không?

Không nên chỉ nhìn thấy tên peer trong `DS Replicas` rồi kết luận replication hoàn toàn khỏe. Cần kiểm tra log và dữ liệu đăng ký quan sát được từ từng peer. Trong một cụm có độ trễ đồng bộ, hai Dashboard có thể tạm thời hiển thị số instance hoặc status khác nhau.

## 9. Heartbeat, eviction và self-preservation

Eureka client định kỳ renew lease bằng heartbeat. Nếu server không nhận renewal trong thời gian quy định, instance có thể bị xem là hết hạn và bị eviction. Các chu kỳ và ngưỡng cụ thể phụ thuộc cấu hình client/server.

Eureka có cơ chế self-preservation để hạn chế việc xóa hàng loạt instance khi số heartbeat nhận được giảm bất thường. Cơ chế này nhằm tránh xóa nhầm registration trong sự cố mạng diện rộng, nhưng có thể khiến một số bản ghi cũ vẫn xuất hiện sau khi process đã dừng.

Khi thấy instance cũ trên Dashboard:

1. Xác minh process hoặc container có còn chạy không.
2. Kiểm tra log client xem heartbeat có được gửi và server có nhận được không.
3. Kiểm tra log server về lease expiration, eviction và self-preservation.
4. Kiểm tra trạng thái peer và replication nếu đang chạy cluster.
5. So sánh registration trong Dashboard với REST API và kết quả tra cứu từ consumer.
6. Kiểm tra thời gian chờ lease/eviction theo cấu hình thực tế.

Không tắt self-preservation chỉ để làm Dashboard sạch hơn. Trước hết xác định nguyên nhân heartbeat giảm là instance chết thật hay mạng giữa client và server đang gặp sự cố. Thay đổi ngưỡng hoặc tắt cơ chế bảo vệ có thể khiến registry xóa nhầm hàng loạt instance trong một đợt mất kết nối.

## 10. Những tình huống thường gặp trên Dashboard

| Hiện tượng | Nguyên nhân có thể | Cách xử lý ban đầu |
|---|---|---|
| Không thấy application | Client chưa đăng ký, sai server URL, sai profile hoặc auto-registration bị tắt. | Kiểm tra log client, service ID, starter và `defaultZone`. |
| Có application nhưng không có instance mong đợi | Một số replica chưa khởi động hoặc đăng ký thất bại. | So sánh số replica thực tế với số registration; kiểm tra log từng instance. |
| Instance ở `DOWN` | Health/status được cập nhật là không hoạt động hoặc client gặp lỗi. | Kiểm tra Actuator, log ứng dụng và cơ chế cập nhật status. |
| Instance ở `OUT_OF_SERVICE` | Instance đang bảo trì hoặc được chủ động rút khỏi traffic. | Kiểm tra quy trình deploy, readiness và thao tác quản trị. |
| Instance `UP` nhưng gọi không được | Địa chỉ đăng ký sai, dữ liệu cũ, lỗi mạng hoặc endpoint không khỏe. | Gọi URL từ mạng consumer; kiểm tra host, port, DNS, TLS và health. |
| Instance đã dừng vẫn còn | Deregistration thất bại, heartbeat chưa hết lease hoặc self-preservation đang giữ bản ghi. | Kiểm tra renewals, eviction, self-preservation và log peer. |
| Các peer hiển thị danh sách khác nhau | Replication chậm, mất kết nối peer hoặc truy vấn ở thời điểm khác nhau. | So sánh log, peer connectivity, REST API và thời điểm cập nhật. |
| Link status/home page không mở được | URL metadata sai hoặc máy quản trị không có route tới host đó. | Kiểm tra registration URL và network từ nơi truy cập. |

## 11. Quy trình kiểm tra một service từ đầu đến cuối

Khi có báo cáo “consumer không tìm thấy `order-service`” hoặc “gọi instance bị lỗi”, có thể đi theo quy trình sau:

**Bước 1 – Xác nhận đúng Eureka Server.** Mở Dashboard và kiểm tra địa chỉ, System Status, profile và peer. Tránh xem nhầm môi trường dev, staging hoặc một node khác trong cluster.

**Bước 2 – Tìm application name.** Xác nhận `ORDER-SERVICE` có xuất hiện hay không. Đối chiếu với `spring.application.name` của provider và service ID consumer đang tra cứu.

**Bước 3 – Đếm instance.** So sánh số bản ghi với số replica dự kiến. Nếu thiếu, kiểm tra log khởi động và đăng ký của từng provider.

**Bước 4 – Kiểm tra từng status.** Ghi lại instance ID, status, host và port. Với status bất thường, xem health check, heartbeat và lifecycle.

**Bước 5 – Thử kết nối từ consumer.** Dùng host/port trong registration để kiểm tra DNS, route, firewall, TLS và endpoint health. Không chỉ thử từ máy chạy provider.

**Bước 6 – Đối chiếu REST API.** Đọc `/eureka/apps/ORDER-SERVICE` và instance cụ thể để xác nhận dữ liệu registry đang trả về.

**Bước 7 – Kiểm tra cache và LoadBalancer.** Nếu Dashboard/API có instance nhưng consumer không dùng được, xem cache discovery, supplier, filter và chính sách LoadBalancer ở consumer.

**Bước 8 – Kiểm tra peer và self-preservation.** Nếu dữ liệu giữa các node khác nhau hoặc instance cũ tồn tại, xem replication, renewals, eviction và cảnh báo server.

**Bước 9 – Ghi nhận bằng chứng.** Lưu thời điểm, service ID, instance ID, status, host/port, log liên quan và kết quả health/API để đội vận hành có thể so sánh sau khi thay đổi.

## 12. Bảo mật Dashboard và dữ liệu registry

Dashboard có thể tiết lộ tên service, địa chỉ nội bộ, port, metadata và topology của hệ thống. Vì vậy, không nên công khai Dashboard hoặc Eureka REST API ra Internet nếu không có nhu cầu và biện pháp bảo vệ rõ ràng.

Các nguyên tắc cần áp dụng:

- Đặt Dashboard và REST API sau lớp xác thực/phân quyền phù hợp.
- Giới hạn truy cập theo mạng quản trị, VPN hoặc network policy.
- Dùng TLS khi truy cập qua mạng không tin cậy.
- Không đưa token, mật khẩu hoặc secret vào metadata registration.
- Giới hạn quyền xem và thao tác registry theo vai trò vận hành.
- Không để endpoint health hoặc info tiết lộ cấu hình nhạy cảm.
- Ghi audit log cho các thao tác quản trị làm thay đổi status hoặc registration.

Dashboard chủ yếu phục vụ quan sát; nó không thay thế hệ thống monitoring, alerting hoặc audit. Trong production, nên kết hợp metric và log của Eureka Server với giám sát ứng dụng và mạng.

## 13. Checklist đọc Dashboard

| Nhóm | Câu hỏi |
|---|---|
| Server | Có đang mở đúng Eureka Server và đúng môi trường không? |
| System Status | Server đã khởi động ổn định và có cảnh báo vận hành không? |
| DS Replicas | Peer có đúng địa chỉ và kết nối được không? |
| Application | Service ID có đúng với tên consumer tra cứu không? |
| Instance count | Số registration có khớp số replica dự kiến không? |
| Instance identity | Instance ID có riêng biệt và đúng bản chạy không? |
| Status | Instance đang `UP`, `DOWN`, `STARTING`, `OUT_OF_SERVICE` hay `UNKNOWN`? |
| Network address | Host/port có thể truy cập từ consumer không? |
| Health | Actuator/health và health integration có hoạt động không? |
| Lease | Heartbeat, eviction và self-preservation có giải thích được bản ghi cũ không? |
| API | REST API có trả cùng dữ liệu với Dashboard không? |
| Consumer | Discovery cache và LoadBalancer có dùng đúng service ID và instance không? |
| Security | Dashboard, REST API và endpoint quản trị đã được bảo vệ chưa? |

## Kết luận

Eureka Dashboard giúp quan sát các application đã đăng ký, số instance, trạng thái, địa chỉ và thông tin peer của Eureka Server. Khi kiểm tra một service, hãy bắt đầu từ application name, đếm instance, đọc status, xác minh host/port và thử health endpoint từ mạng consumer. Dùng REST API để đối chiếu dữ liệu có cấu trúc và kiểm tra `DS Replicas`, heartbeat, eviction cùng self-preservation khi nghi ngờ registry sai lệch.

Dashboard phản ánh trạng thái mà Eureka đang lưu; nó không bảo đảm endpoint vẫn khỏe hoặc có thể truy cập tại thời điểm request. Việc vận hành tin cậy cần kết hợp dữ liệu Dashboard với log client/server, health check, kết nối mạng, cache discovery và Spring Cloud LoadBalancer. Bảo vệ Dashboard và registry cũng là yêu cầu quan trọng vì chúng tiết lộ cấu trúc dịch vụ nội bộ của hệ thống.
