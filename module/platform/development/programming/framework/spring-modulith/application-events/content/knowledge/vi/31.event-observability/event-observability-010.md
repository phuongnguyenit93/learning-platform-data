# Kiểm tra health

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Một hệ thống có thể vẫn trả HTTP 200 trong khi listener không xử lý được event, publication tồn đọng hoặc consumer Kafka bị tụt lại nhiều giờ. Vì vậy, health check cần quan sát cả khả năng phục vụ request lẫn sức khỏe của luồng giao sự kiện.

**Kiểm tra health** là việc đánh giá một ứng dụng hoặc một thành phần có đủ điều kiện để tiếp tục nhận công việc hay không. Với kiến trúc event-driven, health cần phản ánh publisher, listener, publication registry, broker, consumer, database và các dependency liên quan. Health check tốt giúp phát hiện sự cố sớm, hỗ trợ orchestrator quyết định đưa instance vào hoặc ra khỏi traffic và cung cấp tín hiệu rõ ràng cho vận hành.

## 1. Health check cần trả lời câu hỏi nào?

Không nên gom mọi tín hiệu kỹ thuật vào một trạng thái UP/DOWN duy nhất mà không xác định mục đích. Một health check nên trả lời một câu hỏi cụ thể:

- Ứng dụng còn sống và có thể tiếp tục chạy không?
- Instance đã khởi tạo xong và có thể nhận traffic hoặc message mới chưa?
- Database lưu publication và dữ liệu nghiệp vụ có truy cập được không?
- Listener có xử lý event thành công hay publication đang tồn đọng?
- Kafka consumer có được gán partition và theo kịp tốc độ producer không?
- Có dependency nào đang lỗi đến mức cần ngừng nhận công việc mới không?

Health endpoint phục vụ quyết định vận hành. Metrics và dashboard phục vụ phân tích xu hướng; logs và traces phục vụ điều tra từng lần xử lý. Không nên biến một health check thành truy vấn báo cáo nặng hoặc trả toàn bộ trạng thái nội bộ của hệ thống.

## 2. Phân biệt liveness, readiness và startup

Spring Boot Actuator hỗ trợ các health group dành cho Kubernetes probes. Ba khái niệm có mục đích khác nhau:

| Probe | Câu hỏi | Khi thất bại |
| --- | --- | --- |
| Liveness | Process còn hoạt động và có thể tiếp tục chạy không? | Orchestrator có thể restart container. |
| Readiness | Instance đã sẵn sàng nhận traffic hoặc công việc mới chưa? | Orchestrator tạm ngừng gửi traffic đến instance. |
| Startup | Ứng dụng đã hoàn tất khởi động chưa? | Chưa áp dụng liveness/readiness theo chu kỳ bình thường. |

Liveness nên kiểm tra những điều kiện nội tại của process. Nếu database hoặc Kafka tạm thời mất kết nối, không nên mặc định làm liveness DOWN; restart liên tục có thể khiến sự cố dependency nặng hơn và tạo vòng lặp khởi động.

Readiness có thể phản ánh việc ứng dụng đã khởi tạo listener, kết nối cần thiết và đủ khả năng nhận công việc. Tuy nhiên, không phải mọi dependency suy giảm đều phải làm readiness DOWN. Nếu một consumer vẫn có thể lưu event vào inbox hoặc buffer bền vững khi một hệ thống phụ không sẵn sàng, việc loại instance khỏi traffic có thể không cần thiết.

Startup probe hữu ích khi ứng dụng cần thời gian khởi tạo dài, ví dụ tạo schema, phục hồi publication hoặc warm up cache. Trong thời gian startup chưa hoàn tất, liveness không nên kết luận process bị treo chỉ vì chưa sẵn sàng.

## 3. Các lớp health của event pipeline

Một event pipeline đi qua nhiều thành phần. Nên kiểm tra theo lớp để xác định chính xác nơi phát sinh vấn đề:

| Lớp | Tín hiệu health | Ví dụ vấn đề |
| --- | --- | --- |
| Publisher | Ứng dụng có thể ghi nhận và công bố event theo transaction không? | Database transaction lỗi hoặc không tạo được publication record. |
| Publication registry | Store bền vững truy cập được; publication incomplete có tăng bất thường không? | Registry database lỗi hoặc listener liên tục thất bại. |
| Listener | Handler có xử lý được event và hoàn tất transaction không? | Exception tăng, xử lý quá chậm hoặc lỗi mapping. |
| Broker | Kafka/broker có thể kết nối và chấp nhận thao tác cần thiết không? | Authentication failure, broker unavailable hoặc quota. |
| Consumer | Consumer có hoạt động, được gán partition và commit offset không? | Consumer group rebalance liên tục hoặc lag tăng. |
| Persistence | Database của read model/inbox/outbox có hoạt động không? | Connection pool cạn hoặc transaction timeout. |
| Dependency nghiệp vụ | API bên ngoài có đáp ứng SLA cần thiết không? | Payment gateway hoặc dịch vụ vận chuyển bị gián đoạn. |

Không nhất thiết mọi lớp đều có một HealthIndicator riêng. Hãy chọn các tín hiệu ảnh hưởng trực tiếp đến khả năng phục vụ và khả năng tiếp tục xử lý event. Các chỉ số chi tiết nên được đưa vào metrics và dashboard.

## 4. Sử dụng Spring Boot Actuator

Spring Boot Actuator cung cấp endpoint health và cơ chế tổng hợp các HealthIndicator. Có thể bật endpoint để kiểm tra trạng thái:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when_authorized
~~~

Chỉ expose endpoint cần thiết. Health details có thể chứa tên dependency, trạng thái kết nối hoặc thông tin vận hành; cần giới hạn truy cập qua mạng nội bộ, authentication và authorization phù hợp. Không bật hiển thị toàn bộ details công khai trên internet.

Endpoint /actuator/health tổng hợp các indicator được cấu hình. Các endpoint probe thường dùng là /actuator/health/liveness, /actuator/health/readiness và /actuator/health/startup khi startup group được cấu hình. Đường dẫn cụ thể có thể thay đổi theo context path và cấu hình management server.

Một response health tổng quát có thể gồm status và các component:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" },
    "eventDelivery": {
      "status": "UP",
      "details": {
        "incompletePublications": 2,
        "oldestIncompleteAgeSeconds": 14
      }
    }
  }
}
~~~

Đây là JSON minh họa cho cấu trúc response, không phải kết quả từ một ứng dụng cụ thể. Số liệu trong details phải được tính từ nguồn dữ liệu thực tế và chỉ hiển thị cho người có quyền.

## 5. Viết HealthIndicator cho event delivery

Với Spring Boot, có thể triển khai HealthIndicator để bổ sung tín hiệu cho event pipeline. Nên tách việc đọc số liệu khỏi việc quyết định trạng thái để dễ kiểm thử và không phụ thuộc trực tiếp vào cấu trúc nội bộ của publication registry.

Ví dụ, EventDeliveryHealthSnapshot là một service do ứng dụng định nghĩa, đọc thống kê từ persistent publication repository hoặc nguồn metrics đã chọn:

~~~java
public record EventDeliveryHealthSnapshot(
    long incompletePublications,
    long oldestIncompleteAgeSeconds,
    boolean publicationStoreAvailable
) {}
~~~

~~~java
@Component
@RequiredArgsConstructor
class EventDeliveryHealthIndicator implements HealthIndicator {

    private final EventDeliveryHealthService healthService;

    @Override
    public Health health() {
        EventDeliveryHealthSnapshot snapshot =
            healthService.snapshot();

        if (!snapshot.publicationStoreAvailable()) {
            return Health.down()
                .withDetail("reason", "publication-store-unavailable")
                .build();
        }

        Health.Builder builder = Health.up()
            .withDetail(
                "incompletePublications",
                snapshot.incompletePublications()
            )
            .withDetail(
                "oldestIncompleteAgeSeconds",
                snapshot.oldestIncompleteAgeSeconds()
            );

        if (snapshot.oldestIncompleteAgeSeconds() > 900) {
            return Health.status("DEGRADED")
                .withDetails(builder.build().getDetails())
                .build();
        }

        return builder.build();
    }
}
~~~

Đoạn code chỉ minh họa cách tạo indicator. EventDeliveryHealthService và snapshot() là API của ứng dụng, không phải API mặc định của Spring Modulith. Cần triển khai việc truy vấn phù hợp với phiên bản thư viện và publication repository đang dùng. Trạng thái tùy chỉnh như DEGRADED cần được ánh xạ và xử lý nhất quán ở health aggregator; không nên giả định mọi orchestrator đều hiểu status này.

Health check nên dùng truy vấn nhẹ, có timeout và giới hạn số bản ghi. Tránh tải toàn bộ publication history hoặc chạy phép tổng hợp nặng mỗi lần kubelet gọi probe. Có thể cập nhật snapshot định kỳ trong background rồi để HealthIndicator đọc giá trị gần nhất.

## 6. Theo dõi Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication đến transactional listener. Mỗi publication được ghi nhận và đánh dấu hoàn tất khi listener xử lý thành công theo transaction. Publication chưa hoàn tất có thể là dấu hiệu listener lỗi, ứng dụng dừng giữa quá trình xử lý hoặc dependency không sẵn sàng.

Các tín hiệu nên quan sát:

- Số publication incomplete hiện tại.
- Tuổi của publication incomplete lâu nhất.
- Số publication mới phát sinh trong một khoảng thời gian.
- Tỷ lệ publication được hoàn tất thành công.
- Số lần recovery/resubmit và số listener thường xuyên thất bại.
- Phân bố incomplete theo listener/module nếu nguồn dữ liệu hỗ trợ.

Chỉ đếm số publication incomplete chưa đủ. Một hệ thống có hai publication incomplete mới phát sinh trong vài giây có thể bình thường; một publication tồn tại nhiều giờ có thể cần điều tra. Nên kết hợp số lượng, tuổi và tốc độ tăng.

Registry không phải event store lưu toàn bộ lịch sử nghiệp vụ và không thay thế trạng thái saga, inbox hoặc consumer offset. Health indicator cần phản ánh đúng phạm vi của registry, không suy diễn rằng mọi event đã được xử lý bởi mọi thành phần bên ngoài.

## 7. Health của listener và handler

Listener có thể vẫn được đăng ký trong application context nhưng không xử lý được event. Vì vậy, health của listener nên được đánh giá qua kết quả xử lý và khả năng giao event, không chỉ qua việc bean tồn tại.

Các tín hiệu hữu ích:

- Số lần listener thành công/thất bại theo event type.
- Thời gian xử lý p50/p95/p99.
- Số handler đang chạy và số handler bị timeout.
- Tỷ lệ exception theo failure category.
- Số publication incomplete theo listener.
- Số event được chuyển sang quarantine hoặc dead-letter.

Không nên gọi thử từng handler trong health endpoint bằng một event giả. Cách đó có thể tạo side effect, ghi dữ liệu, gửi email hoặc gọi hệ thống ngoài. Dùng metrics, registry và synthetic check có kiểm soát nếu cần kiểm tra đường đi end-to-end.

Một listener có thể xử lý một số event type thành công nhưng thất bại với loại khác. Nếu health check cần phân biệt, hãy xuất metrics theo event type hoặc listener ID; tránh tạo một endpoint health riêng cho hàng trăm loại event.

## 8. Health của Kafka consumer

Với consumer Kafka, kiểm tra broker kết nối được chưa chỉ là một phần. Consumer có thể kết nối thành công nhưng không được gán partition, không commit offset hoặc xử lý chậm đến mức lag tăng liên tục.

Các tín hiệu nên theo dõi:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Broker connectivity | Client có thể kết nối và thực hiện thao tác cần thiết. |
| Consumer group state | Group có member ổn định và assignment hợp lệ không. |
| Partition assignment | Consumer có được gán partition mong đợi không. |
| Consumer lag | Khoảng cách giữa dữ liệu mới nhất và tiến độ consumer. |
| Commit progress | Offset có được commit theo nhịp xử lý không. |
| Rebalance rate | Group có liên tục rebalance bất thường không. |
| DLT volume | Số record lỗi đã được chuyển sang dead-letter. |

Lag cần được đánh giá theo tốc độ tăng và thời gian xử lý cho phép của nghiệp vụ. Một lag nhỏ trong giờ cao điểm có thể bình thường; lag tăng liên tục hoặc tuổi record vượt SLA mới là dấu hiệu đáng cảnh báo.

Không nên làm readiness DOWN chỉ vì lag khác 0. Nếu consumer vẫn đang xử lý và backlog nằm trong ngưỡng cho phép, instance vẫn có thể khỏe. Khi lag vượt ngưỡng nghiêm trọng, có thể cảnh báo hoặc giảm nhận thêm công việc theo chính sách riêng.

## 9. Health của database, outbox và inbox

Event pipeline có thể phụ thuộc database để lưu publication, outbox, inbox hoặc projection. Health check nên xác minh khả năng thực hiện thao tác tối thiểu cần thiết thay vì chỉ kiểm tra TCP connection.

Ví dụ tín hiệu:

- Database có thể mở connection và chạy truy vấn nhẹ.
- Publication repository có thể đọc/ghi theo transaction cần thiết.
- Outbox publisher còn xử lý được bản ghi chờ gửi.
- Inbox/deduplication store có thể ghi nhận event ID.
- Projection database còn khả năng cập nhật dữ liệu.
- Connection pool còn dung lượng và không có thời gian chờ bất thường.

Không nên ghi một bản ghi thử vào bảng nghiệp vụ mỗi lần health endpoint được gọi. Nếu cần kiểm tra write path, dùng bảng health riêng hoặc synthetic transaction có cleanup và tần suất giới hạn. Truy vấn health phải tránh khóa bảng lớn và không ảnh hưởng workload thực.

## 10. Dependency health và cách tránh cascade failure

Một hệ thống có thể phụ thuộc nhiều dịch vụ ngoài. Nếu mọi dependency đều được đưa vào readiness và chỉ cần một dịch vụ DOWN là toàn bộ instance ngừng nhận traffic, một sự cố ở dependency phụ có thể làm toàn hệ thống ngừng hoạt động.

Phân loại dependency:

| Loại dependency | Cách cân nhắc đưa vào readiness |
| --- | --- |
| Bắt buộc để nhận request hoặc event mới | Có thể ảnh hưởng readiness nếu không có phương án lưu/đệm an toàn. |
| Chỉ dùng cho một use case phụ | Có thể giữ readiness UP và trả lỗi có kiểm soát cho use case đó. |
| Có thể retry qua outbox hoặc queue bền vững | Thường không cần loại instance khỏi traffic chỉ vì dependency tạm lỗi. |
| Dependency quan sát/analytics | Không nên làm liveness/readiness của nghiệp vụ chính DOWN. |
| Dependency có circuit breaker đang mở | Có thể báo DEGRADED hoặc metric/alert; quyết định readiness tùy khả năng phục vụ còn lại. |

Health check phải phản ánh khả năng thực tế của instance. Nếu event có thể được lưu bền vững và xử lý sau khi dependency phục hồi, instance có thể tiếp tục nhận công việc trong giới hạn backlog. Nếu không thể bảo đảm durability, cần xem xét ngừng nhận công việc mới để tránh mất dữ liệu.

## 11. Cấu hình health groups cho probes

Spring Boot cho phép tổ chức các health indicator thành group. Ví dụ cấu hình:

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
          include: readinessState,db,eventDelivery
~~~

Đây là cấu hình minh họa. Chỉ đưa db hoặc eventDelivery vào readiness nếu việc không truy cập được chúng thực sự khiến instance không thể nhận công việc an toàn. Không đưa Kafka, payment gateway hoặc mọi dependency vào liveness một cách mặc định.

Nếu indicator eventDelivery phản ánh backlog vượt ngưỡng, cân nhắc dùng metric/alert riêng thay vì làm readiness thất bại ngay. Khi readiness DOWN, orchestrator có thể loại instance khỏi traffic nhưng không giải quyết nguyên nhân backlog; nếu tất cả instance cùng DOWN, khả năng xử lý phục hồi có thể còn tệ hơn.

## 12. Thiết kế ngưỡng và trạng thái health

Ngưỡng cần dựa trên SLA, năng lực xử lý và hậu quả nghiệp vụ. Không có một con số chung phù hợp cho mọi hệ thống.

Ví dụ chính sách:

| Tín hiệu | Bình thường | Cần cảnh báo | Cần hành động |
| --- | --- | --- | --- |
| Oldest incomplete publication | Dưới vài phút | Tăng liên tục hoặc vượt SLA listener | Điều tra listener/dependency và recovery |
| Consumer lag | Ổn định trong ngưỡng | Tăng qua nhiều chu kỳ | Scale consumer hoặc xử lý partition bị nghẽn |
| DLT count | Không tăng bất thường | Có record mới | Phân tích lỗi, sửa nguyên nhân và lập kế hoạch replay |
| Listener failure rate | Thấp, có xu hướng ổn định | Spike theo event type | Kiểm tra deploy, schema và dependency |
| Database pool wait | Gần 0 hoặc thấp | Tăng kéo dài | Kiểm tra query, transaction và pool capacity |

Spring Boot Health hỗ trợ các status phổ biến như UP, DOWN, OUT_OF_SERVICE và UNKNOWN; có thể định nghĩa status bổ sung nhưng cần cấu hình thứ tự và mapping phù hợp. Nếu một status tùy chỉnh không được hệ thống giám sát hiểu, kết quả có thể bị diễn giải sai. Hãy chọn mapping rõ ràng và kiểm tra HTTP status code của endpoint.

Health check không nên chuyển DOWN chỉ vì một metric vượt ngưỡng trong một mẫu đơn lẻ. Có thể dùng nhiều lần liên tiếp, cửa sổ thời gian hoặc hysteresis để tránh trạng thái chập chờn. Ngưỡng cảnh báo và ngưỡng loại instance khỏi traffic có thể khác nhau.

## 13. Bảo mật health endpoint

Health endpoint thường được kubelet, load balancer và hệ thống monitoring truy cập. Chỉ expose đường dẫn cần thiết và giới hạn nguồn truy cập.

Các nguyên tắc:

- Cho phép probe nội bộ truy cập trạng thái tối thiểu cần thiết.
- Yêu cầu authorization cho health details chứa tên dependency, listener hoặc thông tin vận hành.
- Không trả credential, connection string, stack trace hoặc payload event.
- Không cho người dùng ngoài hệ thống truy cập actuator endpoint quản trị.
- Tách management port/network nếu môi trường yêu cầu.
- Ghi audit cho thao tác quản trị hoặc endpoint có dữ liệu nhạy cảm.

Không đưa secret vào detail chỉ để giúp debug. Trạng thái DOWN cùng một error code an toàn thường đủ cho probe; thông tin chi tiết cần nằm trong log có kiểm soát.

## 14. Synthetic health check và end-to-end flow

Health indicator đọc trạng thái hiện tại có thể không phát hiện một lỗi định tuyến chỉ xảy ra khi event đi qua toàn bộ pipeline. Nếu cần xác minh end-to-end, có thể dùng synthetic event hoặc canary flow được thiết kế riêng.

Một synthetic flow an toàn nên:

1. Dùng event type và tenant/test identity riêng.
2. Có correlationId và marker để phân biệt với nghiệp vụ thật.
3. Không kích hoạt thanh toán, email hoặc side effect không thể đảo ngược.
4. Đi qua publisher, broker hoặc listener cần kiểm tra.
5. Ghi nhận thời gian từ publish đến acknowledgement.
6. Có timeout, cleanup và cảnh báo khi không nhận được kết quả.

Không phát synthetic event mỗi lần kubelet gọi readiness. Tần suất probe có thể rất cao và tạo tải hoặc side effect. Chạy canary theo chu kỳ riêng, với rate limit và dashboard độc lập.

## 15. Kiểm thử health check

Health indicator cần được kiểm thử cho cả trạng thái bình thường và suy giảm. Không chỉ xác minh response UP; cần bảo đảm các điều kiện lỗi được phân loại đúng và probe không gây side effect.

Các trường hợp nên kiểm tra:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Publication store hoạt động | Indicator báo trạng thái phù hợp và số liệu chính xác. |
| Publication store không truy cập được | Health phản ánh lỗi theo policy đã chọn. |
| Incomplete publication mới phát sinh | Không làm readiness thất bại ngay nếu còn trong ngưỡng. |
| Incomplete publication quá cũ | Metric/alert hoặc trạng thái suy giảm được kích hoạt theo policy. |
| Kafka broker mất kết nối | Health của broker phản ánh đúng; liveness không bị hạ theo mặc định. |
| Consumer lag tăng | Metric và alert phản ánh xu hướng; không đánh giá chỉ bằng lag khác 0. |
| Dependency phụ lỗi | Use case còn lại vẫn phục vụ nếu có phương án an toàn. |
| Health endpoint bị gọi liên tục | Không tạo write nghiệp vụ, event giả hoặc truy vấn nặng. |
| Health details | Không lộ secret, payload hoặc thông tin nhạy cảm. |
| Readiness/liveness groups | Mỗi probe chỉ bao gồm indicator đúng mục đích. |
| Startup chậm | Startup probe tránh restart sớm khi khởi tạo hợp lệ. |
| Synthetic flow lỗi | Canary báo lỗi độc lập và không tạo side effect ngoài dự kiến. |

Có thể mock service đọc snapshot để unit test logic ngưỡng; integration test nên xác minh Actuator group, security rule và HTTP status code thực tế. Với Kafka hoặc broker, dùng môi trường kiểm thử phù hợp để xác minh kết nối và consumer group.

## 16. Quan sát và runbook khi health suy giảm

Khi health chuyển DEGRADED hoặc DOWN, người vận hành cần biết thành phần nào gây ra trạng thái đó và hành động nào an toàn.

Dashboard nên hiển thị:

- Liveness/readiness/startup theo instance.
- Publication incomplete count và tuổi lớn nhất theo listener.
- Listener success/failure rate và latency.
- Consumer group lag, assignment, rebalance và commit progress.
- Outbox/inbox backlog và DLT count.
- Database availability, pool utilization và transaction latency.
- Dependency availability, circuit breaker state và request latency.

Runbook điều tra có thể đi theo thứ tự:

1. Xác định probe hoặc health component nào báo lỗi.
2. Kiểm tra lỗi dependency, database, broker và credential.
3. Xem publication incomplete lâu nhất, listener liên quan và exception category.
4. Với Kafka, kiểm tra group state, partition assignment, lag và offset commit.
5. Kiểm tra backlog/DLT và xác định có event độc hại hoặc schema không tương thích không.
6. Xác minh side effect và idempotency trước khi resubmit hoặc replay.
7. Sau khi khắc phục, theo dõi backlog giảm và health ổn định qua nhiều chu kỳ.

Không nên xóa publication incomplete hoặc reset consumer offset chỉ để làm health trở lại UP. Những thao tác đó có thể che giấu sự cố hoặc làm mất khả năng xử lý event. Recovery cần dựa trên nguyên nhân, trạng thái nghiệp vụ và chính sách replay.

## 17. Checklist thiết kế health cho event-driven application

- Phân biệt rõ liveness, readiness và startup.
- Health check phản ánh khả năng phục vụ, không chỉ kiểm tra process còn chạy.
- Event Publication Registry được quan sát qua incomplete count, tuổi và listener.
- Health của listener dựa trên kết quả xử lý, latency và failure rate.
- Kafka health bao gồm broker connectivity, group state, assignment, lag và commit progress.
- Database/outbox/inbox có kiểm tra nhẹ và timeout.
- Dependency phụ không tự động làm toàn bộ ứng dụng readiness DOWN.
- Health endpoint không phát event giả hoặc tạo side effect.
- Probe query nhẹ, có timeout, không tải toàn bộ history.
- Status và ngưỡng được mapping rõ ràng cho orchestrator/monitoring.
- Health details được bảo vệ; không trả secret hoặc payload nhạy cảm.
- Synthetic flow chạy riêng với tần suất giới hạn nếu cần kiểm tra end-to-end.
- Test bao phủ dependency failure, backlog, security, probe groups và side effect.
- Dashboard và runbook hướng dẫn điều tra, recovery và xác minh sau phục hồi.

Kiểm tra health cho event pipeline cần kết hợp trạng thái ứng dụng với khả năng giao và xử lý sự kiện. Khi liveness/readiness được phân biệt, publication registry và consumer được quan sát theo tuổi backlog, health check nhẹ và an toàn, còn ngưỡng được gắn với SLA nghiệp vụ, đội vận hành có thể phát hiện sự cố mà không tạo thêm tải hoặc restart dây chuyền.
