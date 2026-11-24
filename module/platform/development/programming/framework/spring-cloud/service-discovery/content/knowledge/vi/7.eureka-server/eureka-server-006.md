# Quan sát đăng ký và trạng thái qua Eureka REST API

## 1. Vì sao cần quan sát registry qua REST API?

Eureka Server lưu registry gồm các application và instance đã đăng ký. Mỗi instance công bố thông tin như service ID, host, port, trạng thái, metadata và thời hạn thuê (lease). Khi một microservice không tìm thấy instance, gọi nhầm địa chỉ hoặc vẫn thấy một instance đã dừng, người vận hành cần kiểm tra dữ liệu mà Eureka Server đang giữ.

Eureka cung cấp REST API để client đăng ký, gia hạn, hủy đăng ký và đọc registry. Các endpoint đọc dữ liệu rất hữu ích khi:

- Xác nhận một ứng dụng đã đăng ký đúng service ID hay chưa.
- Kiểm tra instance nào đang được công bố, host/port có chính xác không.
- Xem trạng thái như UP, DOWN hoặc OUT_OF_SERVICE.
- Kiểm tra metadata phiên bản và thông tin lease.
- So sánh registry giữa nhiều Eureka Server để phát hiện sai lệch.
- Điều tra vì sao một client chưa nhìn thấy instance hoặc vẫn nhìn thấy dữ liệu cũ.

REST API cho biết trạng thái mà Eureka Server đang lưu tại thời điểm truy vấn. Nó không tự kiểm tra trực tiếp mọi endpoint nghiệp vụ và cũng không chứng minh rằng mọi peer hoặc client đã có cùng dữ liệu.

## 2. Địa chỉ cơ bản của Eureka REST API

Trong cấu hình mặc định, Eureka Server thường chạy ở cổng 8761 và có service URL kết thúc bằng /eureka/:

~~~yaml
server:
  port: 8761

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
~~~

Dashboard thường truy cập tại:

~~~text
http://localhost:8761/
~~~

REST API quản lý registry thường có base path:

~~~text
http://localhost:8761/eureka
~~~

Nếu ứng dụng thay đổi port, context path, servlet path hoặc cấu hình reverse proxy, hãy ghép endpoint theo địa chỉ thực tế của môi trường. Không mặc định rằng mọi môi trường đều dùng localhost hoặc cổng 8761.

Các endpoint đọc thường dùng:

| HTTP method | Endpoint | Mục đích |
|---|---|---|
| GET | /eureka/apps | Đọc toàn bộ registry |
| GET | /eureka/apps/{APP_NAME} | Đọc các instance của một application |
| GET | /eureka/apps/{APP_NAME}/{INSTANCE_ID} | Đọc một instance cụ thể |
| GET | /eureka/apps/delta | Đọc phần thay đổi của registry kể từ lần đồng bộ trước theo cơ chế Eureka |

Eureka hỗ trợ biểu diễn dữ liệu bằng JSON hoặc XML thông qua content negotiation. Khi gọi bằng công cụ HTTP, gửi header Accept phù hợp, ví dụ application/json.

## 3. Đọc toàn bộ registry

Để xem danh sách application và instance mà Eureka Server đang giữ, gửi GET đến /eureka/apps:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8761/eureka/apps
~~~

Trên Windows PowerShell, dùng curl.exe để gọi chương trình curl thay vì alias Invoke-WebRequest:

~~~powershell
curl.exe -i -H "Accept: application/json" http://localhost:8761/eureka/apps
~~~

Phản hồi JSON có cấu trúc tổng quát tương tự:

~~~json
{
  "applications": {
    "versions__delta": "1",
    "apps__hashcode": "UP_2_",
    "application": [
      {
        "name": "PAYMENT-SERVICE",
        "instance": [
          {
            "instanceId": "payment-service:8081",
            "hostName": "payment-01",
            "app": "PAYMENT-SERVICE",
            "ipAddr": "10.0.1.21",
            "status": "UP",
            "overriddenStatus": "UNKNOWN",
            "port": {
              "$": 8081,
              "@enabled": "true"
            },
            "metadata": {
              "version": "2.4.1"
            }
          }
        ]
      }
    ]
  }
}
~~~

Đây là ví dụ rút gọn để minh họa cấu trúc; phản hồi thật có thể chứa thêm trường và cách biểu diễn phụ thuộc phiên bản Eureka. Trong JSON Eureka, danh sách application nằm trong applications.application; mỗi application có tên và danh sách instance.

### 3.1. Các trường cần chú ý

| Trường | Ý nghĩa |
|---|---|
| name | Tên application trong registry; Eureka thường chuẩn hóa tên thành chữ hoa |
| instanceId | Định danh một instance trong application |
| app | Tên application được gắn với instance |
| hostName | Hostname được instance công bố |
| ipAddr | Địa chỉ IP được công bố |
| status | Trạng thái hiện tại mà registry ghi nhận |
| overriddenStatus | Trạng thái override nếu có; UNKNOWN thường nghĩa là không có override |
| port | Cổng HTTP và thuộc tính cho biết cổng có được bật hay không |
| securePort | Cổng HTTPS và thuộc tính bật/tắt nếu instance công bố cổng bảo mật |
| metadata | Các cặp key/value do ứng dụng công bố, ví dụ version hoặc build |
| leaseInfo | Thông tin thời hạn thuê và các mốc đăng ký/gia hạn nếu có trong phản hồi |

Tên application trong registry có thể khác cách viết hoa/thường trong cấu hình ứng dụng. Khi truy vấn theo APP_NAME, hãy dùng tên application mà registry hiển thị để tránh nhầm lẫn.

## 4. Tra cứu một application hoặc một instance

### 4.1. Tra cứu tất cả instance của một application

Nếu chỉ quan tâm đến payment-service, dùng endpoint theo application name:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8761/eureka/apps/PAYMENT-SERVICE
~~~

Phản hồi chỉ chứa application được yêu cầu và các instance mà node Eureka đang giữ cho application đó. Đây là cách nhanh hơn khi registry có nhiều service.

### 4.2. Tra cứu một instance cụ thể

Khi đã biết instance ID, có thể đọc riêng instance:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8761/eureka/apps/PAYMENT-SERVICE/payment-service%3A8081
~~~

Trong URL ví dụ, dấu hai chấm trong instance ID được mã hóa thành %3A. Hãy dùng instance ID thực tế từ registry và mã hóa các ký tự đặc biệt nếu chúng xuất hiện trong path.

Tra cứu riêng một instance hữu ích khi cần xác minh host, port, metadata, trạng thái và lease của một bản triển khai cụ thể.

## 5. Đọc trạng thái instance

Trường status mô tả trạng thái mà Eureka registry ghi nhận cho instance. Một số giá trị thường gặp:

| Trạng thái | Ý nghĩa khái quát | Cách diễn giải khi vận hành |
|---|---|---|
| UP | Instance được đánh dấu sẵn sàng | Có thể được discovery client cân nhắc, tùy cache và chính sách chọn instance |
| DOWN | Instance được đánh dấu không sẵn sàng | Cần kiểm tra nguyên nhân và trạng thái ứng dụng |
| STARTING | Instance đang trong giai đoạn khởi động | Chưa nên xem là instance phục vụ bình thường |
| OUT_OF_SERVICE | Instance được đưa ra khỏi phục vụ | Thường dùng khi bảo trì hoặc loại instance khỏi luồng traffic |
| UNKNOWN | Không xác định được trạng thái cụ thể | Cần kiểm tra nguồn trạng thái và cấu hình |

Danh sách trạng thái và cách provider sử dụng chúng có thể phụ thuộc phiên bản, implementation và trạng thái override. Đừng suy luận rằng một instance chắc chắn khỏe chỉ vì status là UP.

### 5.1. Status và health check khác nhau

Status là trạng thái được instance hoặc registry công bố. Health check là việc đánh giá sức khỏe của ứng dụng hoặc một thành phần. Hai thông tin có liên quan nhưng không đồng nhất:

- Một ứng dụng có thể tiếp tục gửi heartbeat trong khi một endpoint nghiệp vụ đã lỗi.
- Instance có thể được đánh dấu OUT_OF_SERVICE trong thời gian bảo trì dù tiến trình vẫn chạy.
- Nếu health check integration chưa được bật hoặc chưa được cấu hình đúng, Eureka có thể không phản ánh trạng thái Actuator như mong đợi.

Với Eureka Client tích hợp Spring Boot Actuator, có thể bật health check integration bằng cấu hình ở application.yml:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Khi bật, Eureka Client sử dụng health state của ứng dụng để cập nhật trạng thái công bố theo cơ chế tích hợp. Hãy kiểm tra tài liệu của release train đang dùng và xác nhận hành vi trong môi trường thử nghiệm. Việc bật health check integration không thay thế việc thiết kế readiness/liveness probe phù hợp.

## 6. Đọc lease và heartbeat

Mỗi instance đăng ký với Eureka có lease để server biết client còn gia hạn đăng ký hay không. Trong phản hồi API, trường leaseInfo có thể chứa các dữ liệu như:

| Trường leaseInfo | Ý nghĩa |
|---|---|
| renewalIntervalInSecs | Khoảng cách heartbeat mà instance khai báo |
| durationInSecs | Thời hạn lease được công bố |
| registrationTimestamp | Thời điểm instance đăng ký |
| lastRenewalTimestamp | Thời điểm gia hạn gần nhất được ghi nhận |
| evictionTimestamp | Thời điểm eviction nếu instance đã bị loại |
| serviceUpTimestamp | Thời điểm instance chuyển sang UP nếu có |

Các timestamp trong phản hồi Eureka thường được biểu diễn dưới dạng số mili giây kể từ Unix epoch. Khi phân tích, cần đổi timestamp sang thời gian dễ đọc và đối chiếu múi giờ nhất quán.

Ví dụ, nếu renewalIntervalInSecs là 30 và durationInSecs là 90, client dự kiến gia hạn mỗi 30 giây và lease có thời hạn 90 giây. Nếu lastRenewalTimestamp đã cũ hơn đáng kể so với thời điểm hiện tại, hãy kiểm tra kết nối client-server, log renew và trạng thái eviction.

Lease hết hạn không nhất thiết khiến instance biến mất ngay tại thời điểm đó. Eureka Server chạy tác vụ eviction định kỳ; self-preservation cũng có thể trì hoãn eviction khi lượng heartbeat giảm bất thường. Vì vậy, một instance cũ có thể còn xuất hiện trong registry một thời gian.

## 7. Đọc metadata phiên bản

Metadata cho phép ứng dụng công bố thông tin bổ sung của instance. Ví dụ:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    metadata-map:
      version: 2.5.0
      build: 2026.11.24
      region: ap-southeast-1
~~~

Sau khi instance đăng ký và registry cập nhật, các giá trị này có thể xuất hiện trong trường metadata của phản hồi REST API.

Metadata hữu ích để:

- Phân biệt các phiên bản đang chạy trong cùng một application.
- Xác định build hoặc vùng triển khai.
- Hỗ trợ dashboard nội bộ và công cụ kiểm tra rollout.
- Cho phép client có logic riêng lọc instance theo metadata nếu kiến trúc yêu cầu.

Eureka chỉ lưu và phân phối metadata; nó không tự động thực hiện canary, blue-green hoặc định tuyến theo version. Nếu cần routing theo version, hãy triển khai chính sách rõ ràng ở gateway hoặc client load balancer.

Không đưa password, token, private key hoặc dữ liệu nhạy cảm vào metadata vì thông tin registry có thể được nhiều client truy vấn.

## 8. So sánh registry giữa các Eureka Server

Trong cụm Eureka, mỗi server giữ registry cục bộ và trao đổi thay đổi với peer. Vì quá trình replication có độ trễ, cùng một thời điểm truy vấn hai node có thể nhận được dữ liệu khác nhau tạm thời.

Ví dụ, đọc application từ hai node:

~~~bash
curl -s -H "Accept: application/json" http://eureka-a:8761/eureka/apps/PAYMENT-SERVICE
curl -s -H "Accept: application/json" http://eureka-b:8762/eureka/apps/PAYMENT-SERVICE
~~~

So sánh:

- Số lượng instance.
- Instance ID.
- Hostname và IP.
- Port.
- Status và overriddenStatus.
- Metadata version/build.
- Last renewal timestamp nếu có.

Nếu hai node khác nhau, trước hết hãy xác định có phải thay đổi vừa mới được đăng ký hay không. Sau đó kiểm tra log peer, lỗi kết nối, thời gian đồng bộ và trạng thái self-preservation. Một lần đọc lệch nhau không đủ để kết luận registry hỏng; cần lặp lại quan sát sau khoảng thời gian phù hợp.

### 8.1. Full registry và delta

Endpoint GET /eureka/apps trả về toàn bộ registry tại node được hỏi. Endpoint GET /eureka/apps/delta trả về các thay đổi kể từ lần đồng bộ trước theo cơ chế delta của Eureka. Eureka Client thường dùng delta để giảm lượng dữ liệu cần trao đổi.

Khi điều tra sự cố, full registry phù hợp để xem trạng thái tổng thể. Delta hữu ích khi cần hiểu những thay đổi gần đây, nhưng nội dung delta phụ thuộc trạng thái đồng bộ và cache của client/server. Không nên coi một phản hồi delta đơn lẻ là bản chụp đầy đủ của registry.

## 9. Các endpoint vòng đời liên quan

Ngoài các GET endpoint phục vụ quan sát, Eureka REST API còn có endpoint được Eureka Client dùng trong vòng đời đăng ký:

| HTTP method | Endpoint | Vai trò |
|---|---|---|
| POST | /eureka/apps/{APP_NAME} | Đăng ký instance mới |
| PUT | /eureka/apps/{APP_NAME}/{INSTANCE_ID} | Gia hạn lease (heartbeat/renew) |
| DELETE | /eureka/apps/{APP_NAME}/{INSTANCE_ID} | Hủy đăng ký instance |

Các thao tác POST, PUT và DELETE thường do Eureka Client thực hiện tự động. Không nên gọi thủ công trong vận hành thường ngày nếu không hiểu đầy đủ request body, instance ID, trạng thái và ảnh hưởng đến registry. Bài này tập trung vào các GET endpoint để quan sát dữ liệu.

## 10. Phân biệt Eureka REST API, dashboard và Actuator

Ba công cụ này trả lời các câu hỏi khác nhau:

| Công cụ | Dữ liệu chính | Dùng để trả lời |
|---|---|---|
| Eureka Dashboard | Cách trình bày trực quan registry tại một Eureka Server | Application và instance nào đang được server hiển thị? |
| Eureka REST API | Dữ liệu registry có cấu trúc JSON/XML | Instance có host, port, status, lease và metadata gì? |
| Spring Boot Actuator | Health, metrics và thông tin vận hành của một tiến trình | Bản thân ứng dụng đang khỏe đến mức nào? |

Ví dụ, REST API có thể cho thấy payment-service đang UP. Nhưng nếu endpoint /actuator/health của ứng dụng báo DOWN do database không truy cập được, instance vẫn có thể không phục vụ request đúng cách nếu health integration hoặc readiness chưa phản ánh trạng thái đó.

Hãy dùng REST API để xác nhận dữ liệu registry và Actuator để kiểm tra ứng dụng. Khi cần kết luận khả năng phục vụ, kết hợp cả hai với log và metric.

## 11. Bảo mật khi truy vấn Eureka REST API

Registry chứa topology nội bộ, địa chỉ instance, cổng và metadata. Vì vậy, cần bảo vệ endpoint:

- Chỉ cho phép truy cập từ mạng quản trị hoặc các workload cần discovery.
- Dùng TLS khi dữ liệu đi qua mạng không tin cậy.
- Cấu hình authentication/authorization nếu môi trường yêu cầu.
- Không công khai dashboard hoặc REST API ra Internet nếu không có lớp bảo vệ.
- Tránh đưa thông tin nhạy cảm vào metadata.
- Ghi log truy cập và giới hạn quyền của người dùng chỉ cần quan sát.

Nếu thêm Spring Security cho Eureka Server, hãy kiểm tra quy tắc bảo vệ các endpoint Eureka. Cấu hình CSRF không phù hợp có thể chặn các request POST/PUT/DELETE mà Eureka Client cần để đăng ký, renew hoặc cancel. Việc bảo vệ API phải cho phép đúng các client hợp lệ thực hiện thao tác cần thiết.

## 12. Quy trình điều tra một instance không xuất hiện

Giả sử payment-service vừa khởi động nhưng không thấy trên Eureka Dashboard. Có thể kiểm tra theo trình tự:

1. Gọi GET /eureka/apps để xác nhận registry tổng thể đang phản hồi.
2. Gọi GET /eureka/apps/PAYMENT-SERVICE để tìm đúng application.
3. Nếu application có mặt, kiểm tra từng instance ID, host, IP và port.
4. Đọc status, overriddenStatus và metadata để xác định instance đang được công bố như thế nào.
5. Đọc leaseInfo và lastRenewalTimestamp nếu có để xem heartbeat có được gia hạn gần đây không.
6. Kiểm tra log ứng dụng để tìm lỗi register/renew hoặc lỗi kết nối Eureka Server.
7. Nếu có cluster, truy vấn cùng application trên peer khác và so sánh registry.
8. Kiểm tra Actuator health, cấu hình health check, self-preservation và eviction khi instance đã dừng nhưng vẫn còn trong registry.

| Kết quả quan sát | Hướng điều tra tiếp |
|---|---|
| GET /eureka/apps không phản hồi | Kiểm tra Eureka Server, port, context path, DNS và mạng |
| Registry phản hồi nhưng không có application | Kiểm tra Eureka Client starter, service URL và log đăng ký |
| Application có nhưng thiếu một instance | Kiểm tra instance ID, register request và log của instance |
| Instance có status DOWN hoặc OUT_OF_SERVICE | Kiểm tra health state, status override và thao tác bảo trì |
| Instance UP nhưng gọi dịch vụ thất bại | Kiểm tra Actuator, host/port, network và endpoint nghiệp vụ |
| Hai peer hiển thị dữ liệu khác nhau | Kiểm tra replication, kết nối peer và độ trễ cập nhật |
| Instance cũ còn xuất hiện lâu | Kiểm tra heartbeat, lease, eviction interval và self-preservation |

## 13. Tổng kết

Eureka REST API cho phép quan sát registry bằng các GET endpoint như /eureka/apps, /eureka/apps/{APP_NAME} và /eureka/apps/{APP_NAME}/{INSTANCE_ID}. Phản hồi cung cấp thông tin application, instance, status, metadata và lease để hỗ trợ điều tra đăng ký và trạng thái dịch vụ.

Khi đọc dữ liệu, cần phân biệt trạng thái được registry công bố với health thực tế của ứng dụng, đồng thời hiểu rằng lease expiration, eviction, replication và cập nhật cache là những bước có độ trễ. Dashboard giúp quan sát nhanh, REST API cung cấp dữ liệu có cấu trúc, còn Actuator cho biết tình trạng bên trong tiến trình. Kết hợp cả ba cùng log và metric sẽ giúp xác định chính xác hơn nguyên nhân instance không xuất hiện, stale hoặc không thể phục vụ request.
