# Health indicator của bộ ngắt mạch và ảnh hưởng tới readiness

Circuit Breaker cung cấp tín hiệu về tình trạng của dependency: breaker có thể đang CLOSED, OPEN hoặc HALF_OPEN. Spring Boot Actuator có thể công bố thông tin này qua health endpoint để hệ thống vận hành và nền tảng triển khai quan sát được tình trạng bảo vệ dịch vụ. Tuy nhiên, đưa trạng thái Circuit Breaker vào readiness sẽ ảnh hưởng trực tiếp tới quyết định nhận traffic của instance. Nếu một dependency tùy chọn bị lỗi và làm toàn bộ instance chuyển sang NOT_READY, ứng dụng có thể tự loại mình khỏi load balancer dù vẫn phục vụ được phần lớn request.

Trong module SPRING_CLOUD_CIRCUIT_BREAKER, bài này giải thích cách bật health indicator cho Resilience4j, đọc trạng thái breaker qua Actuator, tổ chức health group và quyết định có đưa breaker vào readiness hay không. Trọng tâm là phân biệt health để chẩn đoán với readiness để điều phối traffic và liveness để xác định tiến trình còn sống.

## 1. Phân biệt liveness, readiness và health tổng hợp

Ba khái niệm thường được dùng trong Spring Boot Actuator và nền tảng triển khai:

| Khái niệm | Câu hỏi | Hành động thường gắn với nó |
|---|---|---|
| Liveness | Tiến trình còn hoạt động và có thể tiếp tục chạy không? | Nếu thất bại kéo dài, nền tảng có thể khởi động lại container |
| Readiness | Instance có sẵn sàng nhận request mới không? | Nếu thất bại, nền tảng tạm ngừng gửi traffic tới instance |
| Health tổng hợp | Những thành phần được theo dõi đang có trạng thái nào? | Dùng để chẩn đoán, dashboard, cảnh báo và kiểm tra vận hành |

Liveness không nên phụ thuộc trực tiếp vào một dịch vụ bên ngoài như Catalog, Payment hoặc Redis. Nếu dependency gặp sự cố và liveness của mọi instance đều DOWN, Kubernetes có thể liên tục khởi động lại các instance đang chạy tốt. Việc restart không khắc phục được dependency bên ngoài và còn làm giảm năng lực phục vụ.

Readiness có mục tiêu khác: quyết định một instance có thể nhận traffic hay không. Một ứng dụng vẫn có thể READY dù một dependency tùy chọn đang OPEN, miễn là ứng dụng có fallback hoặc vẫn phục vụ được các chức năng quan trọng. Ngược lại, nếu một dependency bắt buộc và mọi request cần nó đều không thể hoàn tất, việc đưa instance khỏi load balancer có thể là lựa chọn phù hợp.

Health tổng hợp có thể hiển thị trạng thái Circuit Breaker để người vận hành biết dependency nào đang suy giảm. Không nhất thiết phải biến mọi trạng thái DOWN trong health tổng hợp thành readiness failure.

## 2. Bật health indicator cho Resilience4j

Để Actuator công bố trạng thái Circuit Breaker, ứng dụng cần có Spring Boot Actuator và phần tích hợp Resilience4j tương thích với phiên bản Spring Boot/Spring Cloud đang dùng. Hãy để Spring Cloud BOM quản lý các phiên bản Spring Cloud; tránh tự ghép các bản Resilience4j không tương thích.

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  health:
    circuitbreakers:
      enabled: true

resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
~~~

Thuộc tính management.health.circuitbreakers.enabled bật health indicator của nhóm Circuit Breaker trong Actuator. Thuộc tính registerHealthIndicator bật việc đăng ký thông tin health cho instance được cấu hình. Tên catalog-read là ID của Circuit Breaker và phải khớp với ID mà ứng dụng dùng khi tạo breaker.

Nếu ứng dụng có nhiều breaker, có thể bật health indicator cho những instance cần quan sát. Không nên đăng ký quá nhiều chi tiết không cần thiết nếu số lượng breaker được tạo động rất lớn; health endpoint cần giữ payload dễ đọc và ổn định.

Health endpoint thường có thể được xem tại:

~~~text
GET /actuator/health
GET /actuator/health/circuitBreakers
~~~

Đường dẫn component cụ thể và tên contributor có thể thay đổi theo phiên bản starter và cấu hình. Hãy kiểm tra response thực tế của endpoint health tổng hợp để xác nhận tên component được expose. Nếu component không xuất hiện, kiểm tra dependency Actuator, Resilience4j integration, thuộc tính enable và registerHealthIndicator, cùng cấu hình exposure.

## 3. Hiểu trạng thái health của Circuit Breaker

Health indicator ánh xạ trạng thái Circuit Breaker thành trạng thái health của Spring Boot. Với tích hợp Resilience4j thông dụng, CLOSED được báo UP, OPEN được báo DOWN và HALF_OPEN có thể được báo UNKNOWN. Cách ánh xạ và cách health aggregator tổng hợp các trạng thái cần được xác nhận trên đúng phiên bản đang dùng.

| Circuit Breaker | Ý nghĩa bảo vệ | Health thường gặp | Cách diễn giải |
|---|---|---|---|
| CLOSED | Cho phép lời gọi và ghi nhận kết quả | UP | Dependency đang được cho phép gọi; chưa có nghĩa mọi request đều thành công |
| OPEN | Từ chối lời gọi mới trong thời gian chờ | DOWN | Dependency đang bị breaker cô lập do lỗi hoặc lời gọi chậm vượt ngưỡng |
| HALF_OPEN | Cho phép số lời gọi thăm dò giới hạn | UNKNOWN hoặc trạng thái trung gian tùy tích hợp | Breaker đang đánh giá khả năng phục hồi |

Health UP không thay thế metric failure rate hoặc latency. Một breaker ở CLOSED vẫn có thể có tỷ lệ lỗi thấp hơn ngưỡng mở; một số request vẫn có thể thất bại. Tương tự, breaker OPEN cho biết chính sách đang ngăn lời gọi mới, không nhất thiết cho biết toàn bộ ứng dụng đã ngừng phục vụ.

Khi health là UNKNOWN, không nên tự suy ra dependency khỏe hay hỏng. Hãy xem chi tiết state của breaker, metric và log. Trạng thái tổng hợp của Actuator có thể dùng status aggregator để sắp xếp DOWN, OUT_OF_SERVICE, UNKNOWN và UP; thứ tự này ảnh hưởng kết quả health group.

## 4. Health indicator không tự quyết định readiness

Việc bật health indicator chỉ làm cho trạng thái breaker xuất hiện trong health endpoint. Nó không đồng nghĩa với việc readiness tự động phụ thuộc vào breaker. Readiness chỉ bị ảnh hưởng khi health contributor được đưa vào group readiness hoặc có logic tùy chỉnh dùng trạng thái breaker để quyết định.

Spring Boot có thể bật health probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Khi probes được bật, ứng dụng cung cấp các group readiness và liveness, thường qua các endpoint:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Có thể xem trạng thái readiness mà không đưa Circuit Breaker vào group. Khi đó, readiness phản ánh các điều kiện ứng dụng sẵn sàng nhận traffic do Spring Boot và ứng dụng định nghĩa.

Nếu muốn đưa Circuit Breaker vào readiness, có thể cấu hình health group, ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,circuitBreakers
~~~

Tên contributor circuitBreakers là tên thường gặp của composite health contributor từ tích hợp Resilience4j. Hãy xác nhận bằng response /actuator/health trước khi dùng trong cấu hình group. Nếu tên khác ở phiên bản đang dùng, hãy thay bằng component ID thực tế. Không đưa tên đoán vào production vì health group có thể không khởi tạo hoặc không bao gồm contributor mong muốn.

## 5. Khi nào nên đưa breaker vào readiness?

Chỉ đưa Circuit Breaker vào readiness khi trạng thái của dependency thực sự quyết định instance có thể phục vụ request hay không. Cần xét mức độ bắt buộc của dependency, fallback và tỷ lệ request bị ảnh hưởng.

| Tình huống | Có nên đưa vào readiness? | Lý do |
|---|---|---|
| Catalog chỉ cung cấp hình ảnh hoặc mô tả bổ sung; có cache dùng được | Thường không | Ứng dụng vẫn phục vụ nội dung chính |
| Recommendation là tính năng tùy chọn | Thường không | Có thể bỏ phần gợi ý khi breaker OPEN |
| Payment authorization là bắt buộc cho endpoint thanh toán, không có phương án thay thế | Có thể cân nhắc | Instance không thể hoàn tất chức năng trọng yếu này |
| Một dependency quan trọng lỗi nhưng chỉ ảnh hưởng một nhóm endpoint | Thường không nên đánh dấu toàn instance NOT_READY | Có thể định tuyến hoặc xử lý lỗi ở cấp endpoint/chức năng |
| Mọi request cần một kho dữ liệu bắt buộc và không thể phục vụ nếu kho dữ liệu mất kết nối | Có thể phù hợp | Instance thực sự không thể nhận request hữu ích |
| Breaker HALF_OPEN đang thăm dò phục hồi | Không nên tự động loại toàn bộ instance chỉ vì trạng thái trung gian | Một số lời gọi thăm dò có thể thành công và ứng dụng vẫn có thể phục vụ request khác |

Một ứng dụng thường có nhiều dependency. Nếu chỉ một breaker OPEN làm readiness DOWN, load balancer có thể loại tất cả instance vì các instance thường cùng gọi một dependency chung. Kết quả là số instance READY giảm về 0 dù các instance đều đang chạy và vẫn có thể phục vụ những chức năng không phụ thuộc dịch vụ lỗi.

Đây là hiện tượng cần tránh khi thiết kế readiness. Đối với dependency tùy chọn, hãy giữ breaker trong health tổng hợp hoặc một health group riêng để chẩn đoán, đồng thời để readiness phản ánh khả năng phục vụ tổng thể.

## 6. Tạo health group riêng cho dependency

Nếu cần một endpoint phản ánh trạng thái dependency nhưng không muốn ảnh hưởng readiness, tạo health group riêng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        dependencies:
          include: circuitBreakers
~~~

Sau khi xác nhận component ID đúng, endpoint group có thể được truy cập theo dạng:

~~~text
GET /actuator/health/dependencies
~~~

Group này giúp dashboard hoặc hệ thống giám sát xem trạng thái các breaker mà không tác động trực tiếp đến quyết định routing của readiness probe.

Có thể tổ chức nhiều group theo mục đích:

- readiness: trạng thái ứng dụng có thể nhận request hay không.
- liveness: tiến trình có thể tiếp tục hoạt động hay cần restart.
- dependencies: trạng thái dependency và các breaker để chẩn đoán.
- health tổng hợp: thông tin của các contributor được expose cho vận hành.

Không cần đưa tất cả health contributor vào mọi group. Hãy chọn đúng tín hiệu cho đúng quyết định.

## 7. Hệ quả khi readiness chuyển NOT_READY

Khi readiness endpoint trả trạng thái không đạt điều kiện thành công, nền tảng triển khai thường ngừng gửi traffic mới tới instance đó. Với Kubernetes, readiness probe thất bại làm Pod bị đánh dấu không sẵn sàng trong EndpointSlice/Service routing. Container không nhất thiết bị restart; restart thường liên quan liveness probe thất bại.

Nếu Circuit Breaker của dependency tùy chọn được đưa vào readiness, một sự cố downstream có thể gây ra chuỗi tác động:

1. Dependency chung bắt đầu trả lỗi.
2. Circuit Breaker trên các instance chuyển OPEN.
3. Health indicator báo DOWN.
4. Readiness group bao gồm contributor đó chuyển DOWN.
5. Kubernetes loại các Pod khỏi endpoint nhận traffic.
6. Số Pod READY giảm, có thể về 0.
7. Các request mới không tới ứng dụng dù nhiều chức năng vẫn có thể hoạt động.

Vì vậy, đừng dùng readiness như một bản sao của health tổng hợp. Readiness phải phản ánh khả năng nhận traffic của instance theo hợp đồng vận hành của ứng dụng.

## 8. Liveness không nên phụ thuộc vào Circuit Breaker

Không đưa health indicator của dependency vào liveness group. Nếu Catalog Service hoặc Payment Service bị lỗi, restart ứng dụng gọi không làm dịch vụ đó phục hồi. Restart liên tục còn làm mất cache cục bộ, warm-up connection pool và tăng tải lên các dependency đang yếu.

Liveness nên tập trung vào khả năng tiến trình tiếp tục chạy. Nếu ứng dụng có deadlock hoặc trạng thái nội bộ không thể phục hồi, liveness có thể báo lỗi để nền tảng restart. Lỗi dependency bên ngoài nên được xử lý bằng Circuit Breaker, timeout, Bulkhead, fallback và cảnh báo vận hành.

Một cấu hình giữ liveness và readiness probes riêng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
        dependencies:
          include: circuitBreakers
~~~

Cấu hình này minh họa việc giữ trạng thái dependency ở group riêng. Tên component phải được xác nhận trên endpoint thực tế. Nếu ứng dụng có health contributor nội bộ khác cần tham gia readiness, hãy bổ sung có chủ đích.

## 9. Chi tiết health và bảo mật endpoint

Health endpoint có thể chứa tên dependency, ID Circuit Breaker, state, failure rate hoặc thông tin lỗi. Không nên công khai chi tiết này cho mọi người dùng bên ngoài nếu có thể tiết lộ cấu trúc nội bộ hoặc trạng thái hệ thống.

Có thể giới hạn chi tiết health:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Tùy phiên bản Spring Boot, cách cấu hình show-details và show-components có thể thay đổi hoặc được kiểm soát qua Spring Security. Hãy chỉ expose endpoint cần thiết và giới hạn quyền truy cập theo môi trường. Kubernetes probe thường chỉ cần status UP/DOWN, không cần stack trace hoặc exception message.

Đừng đưa token, URL nội bộ có credential, payload request hoặc thông tin người dùng vào health detail. Lỗi nên được phân loại ngắn gọn và tránh lộ thông tin nhạy cảm.

## 10. Kết hợp health với metrics và alert

Health indicator là ảnh chụp trạng thái tại thời điểm truy vấn. Nó không thay thế metrics lịch sử. Để hiểu breaker đang hoạt động ra sao, cần theo dõi:

- Trạng thái hiện tại của từng breaker: CLOSED, OPEN, HALF_OPEN.
- Số lần state transition trong khoảng thời gian.
- Failure rate và slow call rate.
- Số lần lời gọi bị từ chối khi breaker OPEN.
- Số lần fallback được kích hoạt và tỷ lệ fallback thành công.
- Latency p50, p95, p99 của dependency.
- Tỷ lệ request đầu cuối thành công và số instance READY.

Có thể dùng Actuator metrics cùng Micrometer và exporter phù hợp để gửi số liệu tới Prometheus hoặc hệ thống quan sát hiện có. Health endpoint hỗ trợ kiểm tra nhanh, còn metrics giúp phân tích xu hướng và cảnh báo trước khi sự cố kéo dài.

Ví dụ, breaker OPEN trong vài giây có thể là phản ứng bảo vệ bình thường. Nếu OPEN kéo dài, fallback thất bại tăng và p99 của API tăng, cần cảnh báo. Cũng cần theo dõi readiness của toàn bộ deployment để phát hiện trường hợp tất cả Pod cùng NOT_READY do một health contributor chung.

## 11. Kịch bản kiểm tra readiness

Trước khi đưa health indicator vào readiness production, hãy kiểm tra trong môi trường tích hợp:

1. Dependency hoạt động bình thường: breaker CLOSED, health indicator hiển thị trạng thái tương ứng.
2. Mô phỏng lỗi dependency: breaker OPEN, health indicator phản ánh trạng thái OPEN.
3. Kiểm tra readiness khi breaker OPEN nhưng dependency là tùy chọn: instance vẫn READY nếu thiết kế yêu cầu.
4. Kiểm tra readiness khi dependency bắt buộc: xác nhận quyết định NOT_READY là có chủ ý và không loại tất cả instance ngoài dự kiến.
5. Khôi phục dependency: breaker chuyển HALF_OPEN rồi CLOSED theo cấu hình; readiness phục hồi đúng cách nếu có phụ thuộc.
6. Mô phỏng nhiều instance cùng dùng dependency: xác nhận sự cố chung không khiến toàn deployment mất endpoint ngoài ý muốn.
7. Kiểm tra liveness: dependency ngoài bị lỗi không làm liveness thất bại.
8. Kiểm tra endpoint từ góc nhìn nền tảng triển khai: path, port, authentication, status code và timeout probe phải phù hợp.

Không chỉ kiểm tra response JSON. Cần kiểm tra hành vi routing thực tế: Pod nào còn trong endpoint, số replica READY, request có được định tuyến tới instance khác và fallback có đáp ứng được chức năng quan trọng không.

## 12. Sơ đồ quyết định đưa Circuit Breaker vào readiness

~~~mermaid
flowchart TD
    A["Circuit Breaker health indicator"] --> B{"Dependency có bắt buộc để phục vụ request chính?"}
    B -- "Không" --> C["Đưa vào health group dependencies"]
    C --> D["Giữ readiness độc lập"]
    B -- "Có" --> E{"Có fallback an toàn và còn khả năng phục vụ?"}
    E -- "Có" --> C
    E -- "Không" --> F["Cân nhắc đưa vào readiness"]
    F --> G{"Ảnh hưởng có thể làm mọi instance NOT_READY?"}
    G -- "Có" --> H["Thiết kế readiness theo chức năng hoặc chính sách deployment"]
    G -- "Không" --> I["Áp dụng readiness có kiểm soát"]
~~~

Quyết định readiness là một quyết định vận hành của ứng dụng, không phải hệ quả bắt buộc của việc bật Circuit Breaker health indicator.

## Kết luận

Health indicator của Resilience4j giúp Actuator công bố trạng thái Circuit Breaker để chẩn đoán và theo dõi. Hãy phân biệt health tổng hợp, readiness và liveness: health cho biết thành phần đang ở trạng thái nào, readiness quyết định instance có nhận traffic không, còn liveness quyết định tiến trình có cần restart không. Chỉ đưa breaker vào readiness khi dependency thực sự bắt buộc và không có fallback an toàn; giữ breaker của dependency tùy chọn trong health group riêng. Theo dõi thêm metrics, state transition và số Pod READY để tránh một sự cố downstream làm toàn bộ deployment tự loại mình khỏi routing.

