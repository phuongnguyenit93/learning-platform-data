# Tuyến mới chưa có hiệu lực sau thay đổi hoặc refresh

Trong chương **Chẩn đoán sự cố**, bài này hướng dẫn xử lý tình huống một tuyến (route) của **Spring Cloud Gateway** đã được sửa trong cấu hình hoặc nguồn khám phá dịch vụ nhưng request vẫn đi theo hành vi cũ. Gateway là cổng vào của hệ thống microservices: mỗi route kết hợp URI đích, route predicate và filter chain để quyết định request nào được chuyển tiếp, tới dịch vụ nào và được biến đổi ra sao. Vì vậy, một thay đổi chỉ có tác dụng khi cấu hình mới đã tới đúng instance và danh sách route đang chạy đã được cập nhật.

## Dấu hiệu và phạm vi cần kiểm tra

Các biểu hiện thường gặp:

- Route mới không xuất hiện trong danh sách route của Gateway.
- Route đã xuất hiện nhưng request vẫn khớp route cũ hoặc trả về 404.
- Một instance đã dùng route mới, trong khi instance khác vẫn dùng route cũ.
- Đã gọi endpoint refresh và nhận phản hồi thành công nhưng kết quả định tuyến không đổi.
- Route dùng `lb://...` đã được nạp nhưng request trả về 503 vì không tìm thấy instance dịch vụ đích.

Trước khi thao tác, ghi lại `route id`, URI đích, predicate, filter dự kiến, profile đang chạy và instance đang nhận request. Xác định nguồn khai báo route là file cấu hình lúc khởi động, Spring Cloud Config, DiscoveryClient hay một repository lưu route động. Cách cập nhật phụ thuộc vào nguồn này.

## Hiểu đúng các lớp cập nhật route

Một route đi qua ba lớp có liên quan:

1. **Nguồn cấu hình**: file YAML, Config Server, service registry hoặc kho route động chứa định nghĩa mà hệ thống mong muốn.
2. **Route definition**: Gateway đọc các định nghĩa từ những `RouteDefinitionLocator` đang được cấu hình. Các nguồn có thể được kết hợp, chẳng hạn route khai báo trong properties và route sinh từ DiscoveryClient.
3. **Route đang được sử dụng**: Gateway chuyển định nghĩa thành route có predicate và filter đã được tạo, sau đó `CachingRouteLocator` có thể lưu kết quả để phục vụ request.

Thay đổi ở lớp đầu tiên không đảm bảo hai lớp sau tự thay đổi. Ví dụ, sửa file `application.yml` trên máy hoặc trong container đang chạy thường không khiến Spring Boot tự đọc lại file. Tương tự, làm mới Environment và làm mới cache route là hai thao tác có mục đích khác nhau. Gateway phát sự kiện `RefreshRoutesEvent` để yêu cầu xây dựng lại danh sách route; endpoint refresh của Gateway thực hiện việc làm mới cache route này.

## Kiểm tra định nghĩa route trước khi refresh

Ví dụ một route được khai báo trong `application.yml`:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
```

Với cấu hình trên, request `/api/orders/42` được chuyển tới dịch vụ `orders-service` qua load balancer; filter `StripPrefix=1` loại bỏ phần `/api` trước khi gửi tiếp. Khi đổi URI, predicate hoặc filter, hãy kiểm tra chính xác file cấu hình, profile và tên property đang được instance sử dụng. Một file được cập nhật trong repository chưa chắc là nguồn cấu hình đang có hiệu lực trong tiến trình.

Nếu ứng dụng đã bật Gateway Actuator endpoint, có thể kiểm tra route từ chính instance cần điều tra. Ví dụ cấu hình quản lý endpoint:

```yaml
management:
  endpoint:
    gateway:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,gateway
```

Sau khi endpoint được bật và expose, gọi:

```bash
# Liệt kê route đang được Gateway công bố
curl -s http://localhost:8080/actuator/gateway/routes

# Xem chi tiết một route theo id
curl -s http://localhost:8080/actuator/gateway/routes/orders-api
```

Tên endpoint, quyền truy cập và cách expose có thể khác theo phiên bản Spring Boot/Spring Cloud Gateway. Chỉ expose endpoint quản trị trên mạng quản lý tin cậy và bảo vệ bằng cơ chế xác thực, phân quyền phù hợp; không công khai endpoint này ra Internet.

Khi đọc kết quả, đối chiếu `id`, URI, predicate và filter với cấu hình dự kiến. Nếu route không có trong kết quả, tập trung vào nguồn định nghĩa, profile, quá trình nạp cấu hình và instance. Nếu route đã có nhưng request vẫn không đi đúng nhánh, chuyển sang kiểm tra predicate, thứ tự route và filter.

## Quy trình làm mới theo từng nguồn cấu hình

### 1. Route khai báo tĩnh trong application.yml

Nếu route chỉ được nạp từ cấu hình lúc khởi động, sửa file trên đĩa không tự cập nhật Environment của tiến trình đang chạy. Hãy triển khai cấu hình mới bằng cơ chế phát hành của ứng dụng, thường là khởi động lại hoặc rolling restart các instance. Sau khi instance khởi động, kiểm tra route qua Actuator.

Không dùng riêng endpoint refresh cache để kỳ vọng Gateway đọc lại một file tùy ý trên đĩa. Endpoint đó làm mới route từ các nguồn locator hiện tại; nó không phải trình theo dõi file cấu hình.

### 2. Cấu hình lấy từ Spring Cloud Config

Khi ứng dụng dùng Spring Cloud Config và Spring Cloud Context, cần làm mới Environment để nhận giá trị mới từ Config Server. Nếu ứng dụng đã expose endpoint refresh và cho phép truy cập có kiểm soát, có thể gọi:

```bash
curl -i -X POST http://localhost:8080/actuator/refresh
```

Sau đó đọc lại route bằng `GET /actuator/gateway/routes`. Spring Cloud Gateway có thể phát sự kiện làm mới route khi nhận sự kiện refresh scope. Nếu route vẫn chưa phản ánh cấu hình mong muốn, có thể yêu cầu Gateway làm mới cache route trực tiếp:

```bash
curl -i -X POST http://localhost:8080/actuator/gateway/refresh
```

Hai endpoint không thay thế nhau: `/actuator/refresh` làm mới cấu hình Environment trong ứng dụng có tích hợp Spring Cloud Context; `/actuator/gateway/refresh` yêu cầu Gateway làm mới cache route từ các nguồn định nghĩa mà nó đang sử dụng. Cả hai chỉ có tác dụng khi endpoint tương ứng được bật, expose và được gọi đúng instance. Nếu dùng Spring Cloud Bus, xác nhận sự kiện refresh đã tới tất cả instance cần cập nhật.

### 3. Route sinh từ DiscoveryClient

Với cấu hình khám phá dịch vụ, Gateway có thể tạo route từ service registry. Kiểm tra service đã đăng ký đúng tên, trạng thái và namespace; kiểm tra DiscoveryClient có nhìn thấy bản ghi mới; sau đó xác nhận Gateway đã cập nhật danh sách route. Một thay đổi ở registry có thể phụ thuộc chu kỳ cập nhật hoặc cơ chế sự kiện của implementation discovery đang dùng.

Nếu route đã tồn tại nhưng `lb://service-name` trả về 503, hãy kiểm tra danh sách instance và tích hợp Spring Cloud LoadBalancer. Đây thường là lỗi phân giải hoặc lựa chọn instance của dịch vụ đích, không phải bằng chứng rằng route cache chưa refresh.

### 4. Route được lưu trong repository động

Nếu ứng dụng sử dụng `RouteDefinitionRepository` hoặc cơ chế quản trị route riêng, trước hết xác nhận thao tác cập nhật đã ghi định nghĩa mới thành công vào đúng repository mà Gateway đang đọc. Sau đó phát sự kiện `RefreshRoutesEvent` hoặc gọi endpoint Gateway refresh để xây dựng lại route đang sử dụng. Với repository trong bộ nhớ, dữ liệu có thể chỉ tồn tại trên một instance; cập nhật instance A không tự đồng bộ sang instance B.

## Kiểm tra khi chạy nhiều instance

Trong môi trường Kubernetes hoặc sau load balancer, request có thể lần lượt tới nhiều pod. Một lần refresh thành công trên pod A không chứng minh pod B, C cũng đã nhận cấu hình mới. Hãy kiểm tra từng pod qua cổng quản trị nội bộ hoặc port-forward, rồi so sánh route id, URI và predicate trên tất cả instance.

Nếu chỉ một số pod cũ, kiểm tra trạng thái rollout, ConfigMap/Secret được mount, biến môi trường, profile và phiên bản image của từng pod. Việc cập nhật ConfigMap không đảm bảo tiến trình Spring Boot nạp lại cấu hình. Chọn một cơ chế nhất quán cho toàn cụm: rolling restart khi dùng cấu hình tĩnh, hoặc refresh phân tán qua Spring Cloud Bus/cơ chế điều phối đã triển khai. Theo dõi kết quả trên từng instance sau khi phát sự kiện.

## Phân biệt lỗi refresh với lỗi khớp route

Khi route đã xuất hiện trong Actuator nhưng request vẫn thất bại, kiểm tra lần lượt:

- **Predicate**: request có đúng path, HTTP method, Host, header, query và scheme mà route yêu cầu không? Ví dụ `Path=/api/orders/**` không khớp một đường dẫn khác như `/orders/42`.
- **Thứ tự route**: một route có thứ tự ưu tiên cao hơn đã khớp request trước hay không? Kiểm tra `order` và các route có predicate chồng lấn.
- **Filter chain**: `StripPrefix`, `RewritePath`, `SetPath`, `AddRequestHeader` hoặc filter tùy chỉnh có biến đổi request đúng như dự kiến không?
- **URI đích**: `http://...` có trỏ đúng host/port không? Với `lb://...`, tên service và danh sách instance có hợp lệ không?
- **Phản hồi upstream**: phân biệt 404 do Gateway không tìm thấy route với 404 do dịch vụ phía sau trả về. Dùng log và trace để xác định request đã được chuyển tiếp hay chưa.

Có thể bật log chi tiết tạm thời trong môi trường kiểm thử hoặc trong khoảng thời gian điều tra:

```yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
    org.springframework.cloud.gateway.route: DEBUG
```

Đối chiếu thời điểm nhận request, route được chọn, filter được áp dụng và URI upstream. Tắt mức DEBUG sau khi hoàn tất vì log chi tiết có thể làm tăng dung lượng log và để lộ thông tin vận hành.

## Bảng khoanh vùng nhanh

| Quan sát | Nguyên nhân cần ưu tiên kiểm tra | Hướng xử lý |
|---|---|---|
| Route mới không có trong Actuator | Sai profile/property, nguồn cấu hình chưa cập nhật, locator chưa đọc định nghĩa mới | Kiểm tra nguồn cấu hình và instance; refresh Environment hoặc triển khai lại cấu hình theo đúng nguồn |
| Route vẫn có URI hoặc predicate cũ | Environment hoặc route cache chưa được làm mới | Làm mới nguồn cấu hình trước, sau đó kiểm tra và refresh route cache |
| Chỉ một vài pod có route mới | Refresh chỉ chạy trên một instance hoặc cấu hình giữa các pod không đồng nhất | Kiểm tra từng pod; dùng refresh phân tán hoặc rolling restart |
| Route mới có trong Actuator nhưng request trả 404 | Predicate không khớp, route khác được chọn hoặc upstream trả 404 | Kiểm tra path/host/method, route order, filter và log upstream |
| Route `lb://...` có trong Actuator nhưng trả 503 | Không có instance khả dụng hoặc LoadBalancer/discovery không phân giải được service | Kiểm tra service registry, tên service và trạng thái instance |
| Gọi refresh thành công nhưng route không đổi | Đã refresh cache nhưng nguồn định nghĩa vẫn chứa dữ liệu cũ, hoặc gọi nhầm instance | Kiểm tra nguồn route, Environment và từng pod trước khi refresh lại |

## Xác nhận hoàn tất và khôi phục

Chỉ kết luận sự cố đã được xử lý khi:

1. Nguồn cấu hình hoặc repository chứa đúng định nghĩa mới.
2. Endpoint route của từng instance cần phục vụ traffic hiển thị đúng URI, predicate và filter.
3. Request thử nghiệm khớp route dự kiến, tới đúng upstream và tạo ra đường dẫn/header sau biến đổi như mong đợi.
4. Các instance trong cụm có cùng trạng thái route; log không còn cho thấy request đi theo cấu hình cũ.

Nếu thay đổi gây lỗi, khôi phục định nghĩa trước đó trong đúng nguồn cấu hình, triển khai hoặc refresh theo cơ chế của nguồn đó, rồi xác nhận lại route trên mọi instance. Lưu lại route id, nguồn cấu hình, instance bị ảnh hưởng và thao tác refresh/rollout đã thực hiện để lần điều tra sau có thể tái hiện.

## Ghi nhớ

Khi một tuyến mới chưa có hiệu lực, hãy xác định dữ liệu mới đã tới nguồn cấu hình, route definition và route đang chạy ở đâu. Làm mới Environment khi nguồn cấu hình thay đổi; làm mới route cache khi Gateway cần xây dựng lại danh sách route; và xác minh từng instance trước khi kết luận. Cách kiểm tra theo từng lớp giúp tránh nhầm lỗi nạp cấu hình với lỗi predicate, filter, service discovery hoặc upstream.
