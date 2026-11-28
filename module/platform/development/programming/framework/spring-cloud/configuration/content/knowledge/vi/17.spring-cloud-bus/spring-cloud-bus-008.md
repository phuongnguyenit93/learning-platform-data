# Sự kiện trễ, bị xử lý lặp hoặc bỏ lỡ và cách đối soát trạng thái

Spring Cloud Bus phát tán sự kiện qua message broker để nhiều instance nhận thông báo như yêu cầu refresh cấu hình. Trong môi trường phân tán, sự kiện có thể đến muộn, được giao lại nhiều lần hoặc không đến được một instance. Những tình huống này không nhất thiết có nghĩa cấu hình trung tâm đã sai; chúng cho thấy việc phát thông báo và việc từng instance thực sự áp dụng cấu hình là hai bước riêng.

Với sự kiện refresh mặc định, Bus chủ yếu báo cho client biết cần lấy lại cấu hình. Nguồn cấu hình thật vẫn nằm ở Config Server và backend của nó. Vì vậy, vận hành an toàn cần theo dõi cả việc giao nhận sự kiện lẫn revision mà từng instance đang sử dụng, sau đó đối soát và đưa instance bị lệch về trạng thái mong muốn.

Bài học này giải thích nguyên nhân và dấu hiệu của sự kiện trễ, lặp, sai thứ tự hoặc bị bỏ lỡ; cách quan sát bằng Bus trace và broker metrics; cách thiết kế xử lý idempotent; và quy trình reconciliation để bảo đảm các instance hội tụ về cùng một phiên bản cấu hình.

Sau bài học, bạn có thể:

- Phân biệt việc gửi, broker nhận, instance nhận và ứng dụng áp dụng cấu hình.
- Chẩn đoán sự kiện trễ, bị redeliver, đến sai thứ tự hoặc không được nhận.
- Hiểu giới hạn của acknowledgement và cơ chế chống xử lý lại event do chính instance phát ra.
- Thiết kế refresh an toàn khi cùng một thông báo được xử lý nhiều lần.
- Đối soát revision cấu hình của từng instance với trạng thái mong muốn.
- Dùng Bus trace, broker metrics, retry và dead-letter queue phù hợp với binder.
- Xây dựng quy trình phục hồi cho instance bỏ lỡ refresh event.

## 1. Bus event là thông báo, không phải bản cấu hình

Spring Cloud Bus dùng Spring Cloud Stream và binder tương ứng để phát tán message qua broker như RabbitMQ hoặc Kafka. Khi người vận hành gọi **POST /actuator/busrefresh**, Bus phát một refresh event đến các instance nằm trong phạm vi đích. Endpoint này làm mới RefreshScope cache và rebind các bean **@ConfigurationProperties** theo cơ chế của Spring Cloud. Xem [Spring Cloud Bus — Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html).

Điểm cần nhớ là event refresh không phải bản sao đầy đủ của mọi property. Nó là tín hiệu yêu cầu instance tải lại cấu hình. Client vẫn lấy dữ liệu từ Config Server theo application, profile và label mà nó đang sử dụng.

~~~mermaid
sequenceDiagram
    participant Op as Operator / Pipeline
    participant Bus as Spring Cloud Bus
    participant Broker as RabbitMQ / Kafka
    participant A as Instance A
    participant B as Instance B
    participant Config as Config Server

    Op->>Bus: POST /actuator/busrefresh
    Bus->>Broker: Publish refresh event
    Broker-->>A: Deliver event
    Broker-->>B: Deliver event
    A->>Config: Fetch configuration
    B->>Config: Fetch configuration
    Config-->>A: Environment / revision
    Config-->>B: Environment / revision
    A->>A: Refresh scope / rebind
    B->>B: Refresh scope / rebind
~~~

Do đó cần phân biệt các trạng thái sau:

| Trạng thái | Ý nghĩa |
|---|---|
| **Sent** | Ứng dụng phát event và Bus ghi nhận thao tác gửi |
| **Broker accepted** | Broker nhận message theo cơ chế xác nhận của broker/binder |
| **Received / Bus ack** | Một instance nhận event và phát acknowledgement của Bus |
| **Refresh completed** | Instance tải cấu hình và hoàn tất quá trình refresh tương ứng |
| **Applied and healthy** | Thành phần ứng dụng thực sự sử dụng revision mới và hoạt động bình thường |

Các trạng thái này không tương đương nhau. Một event được gửi thành công không chứng minh mọi instance đã nhận. Một Bus acknowledgement cũng không tự chứng minh tất cả resource mới đã khởi tạo thành công hoặc instance đã sẵn sàng nhận traffic.

## 2. Vì sao event có thể đến trễ?

Sự kiện trễ xảy ra khi thời gian từ lúc publish đến lúc instance xử lý vượt quá ngưỡng mong đợi. Một số nguyên nhân thường gặp:

- **Broker backlog:** queue hoặc topic có lượng message chờ xử lý lớn.
- **Consumer lag:** consumer xử lý chậm hơn tốc độ message được phát vào broker.
- **Mạng không ổn định:** kết nối giữa ứng dụng và broker bị gián đoạn rồi tự phục hồi.
- **Instance quá tải:** CPU, thread pool, garbage collection hoặc I/O làm chậm listener.
- **Refresh tốn thời gian:** instance nhận event đúng lúc nhưng gọi Config Server, Git hoặc backend cấu hình chậm.
- **Rebalance hoặc rolling deployment:** consumer tạm dừng khi instance khởi động lại hoặc nhóm consumer thay đổi.
- **Broker recovery:** broker failover, reconnect hoặc chuyển leader làm tăng thời gian giao message.

Cần xác định event trễ ở bước nào. Nếu broker chưa giao message, cần điều tra queue depth, consumer lag và kết nối. Nếu instance đã nhận event nhưng refresh kéo dài, hãy kiểm tra thời gian gọi Config Server, Git fetch, bean rebinding, callback đóng tài nguyên và tạo target mới.

Ví dụ, một đợt refresh toàn cụm có thể làm nhiều instance đồng thời gọi Config Server và Git backend. Nếu backend bị quá tải, event đã được giao nhưng quá trình áp dụng vẫn chậm. Khi đó cần theo dõi cả broker và Config Server, tránh chỉ tăng số lần retry của message.

## 3. Vì sao event có thể bị xử lý lặp?

Một số message broker và binder hỗ trợ redelivery. Message có thể được giao lại khi consumer xử lý xong nhưng acknowledgement đến broker bị mất, consumer dừng giữa quá trình xử lý hoặc lỗi tạm thời khiến broker đưa message trở lại hàng đợi. Producer cũng có thể gửi lại khi kết quả lần gửi trước không rõ ràng; người vận hành có thể gọi endpoint nhiều lần vì không nhận được phản hồi.

Các nguyên nhân thường gặp:

- Consumer xử lý event nhưng dừng trước khi xác nhận hoàn tất với broker.
- Kết nối bị ngắt ngay sau khi xử lý, khiến broker không biết consumer đã hoàn tất.
- Cấu hình retry hoặc redelivery của binder.
- Pipeline retry HTTP request sau timeout dù lần publish đầu có thể đã thành công.
- Operator gửi lại cùng yêu cầu khi chưa xác định kết quả lần trước.
- Nhiều hệ thống phát refresh event cho cùng một lần thay đổi.

Spring Cloud Bus có cơ chế nhận diện event do chính instance phát ra để tránh xử lý lại event đó khi nó quay về từ message queue. Cơ chế này dựa trên service ID của instance. Đây là bảo vệ cho đường đi của event do origin phát ra; không phải cam kết exactly-once hoặc cơ chế dedup tổng quát cho mọi event trùng lặp. Service ID của các instance phải duy nhất, nếu không việc định tuyến và nhận diện event có thể sai. Xem [Spring Cloud Bus — Addressing Instances](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/addressing.html).

Với refresh event mặc định, xử lý lặp thường khiến client tải lại cùng trạng thái cấu hình và làm mới scope thêm lần nữa. Nếu target mới đã được tạo sau lần refresh đầu, lần refresh thứ hai có thể loại target mới khỏi cache và khiến target khác được tạo ở lần truy cập tiếp theo. Vì vậy, callback đóng tài nguyên và quy trình tạo lại bean cần an toàn khi refresh được kích hoạt nhiều lần.

Với custom event có side effect nghiệp vụ, chẳng hạn tạo tài nguyên, gửi thông báo hoặc cập nhật dữ liệu, cần có idempotency key và cơ chế dedup ở tầng ứng dụng. Không dựa vào việc broker hoặc Bus chỉ giao event một lần.

## 4. Event đến sai thứ tự

Khi nhiều event được phát gần nhau, event có thể được xử lý theo thời điểm khác với thứ tự người vận hành mong đợi. Việc có bảo đảm thứ tự hay không phụ thuộc broker, partition, queue, concurrency, retry và cách các instance tiêu thụ message. Không nên mặc định toàn bộ event trong một cụm có thứ tự toàn cục.

Ví dụ:

1. Pipeline phát event cho revision cấu hình R10.
2. Một lúc sau, pipeline phát event cho R11.
3. Instance A xử lý event R10 trước rồi R11.
4. Instance B nhận R11 trước, nhưng event R10 bị trễ và được xử lý sau.

Với **RefreshRemoteApplicationEvent** mặc định, event chủ yếu yêu cầu client lấy lại cấu hình từ Config Server. Nếu cả hai lần fetch đều đọc cùng nguồn cấu hình hiện tại, event cũ đến muộn vẫn có thể khiến client tải trạng thái mới nhất. Nhưng nếu hệ thống gửi custom event chứa trực tiếp giá trị hoặc revision cũ và áp dụng payload đó, event đến sai thứ tự có thể khiến ứng dụng quay lại trạng thái cũ.

Không so sánh commit SHA theo thứ tự chữ cái để quyết định revision nào mới hơn. Git commit hash là định danh, không phải số thứ tự. Nếu cần kiểm soát thứ tự rollout, hãy gắn một **generation** hoặc sequence tăng đơn điệu cho mỗi lần phát hành cấu hình.

Ví dụ bản ghi rollout:

~~~yaml
rollout:
  generation: 42
  application: order-service
  profile: prod
  label: main
  git-revision: 7d2f8c1
~~~

Khi instance nhận tín hiệu refresh, nó đọc trạng thái rollout hiện tại từ nguồn điều phối đáng tin cậy. Nếu generation đã áp dụng bằng hoặc mới hơn generation cần xử lý, instance có thể bỏ qua thao tác lặp. Nếu generation mong muốn lớn hơn, instance tải cấu hình, xác minh revision và ghi nhận trạng thái mới.

Generation trong ví dụ là metadata do quy trình triển khai quản lý; nó không phải field mặc định được Spring Cloud Bus tự thêm vào mọi refresh event.

## 5. Event bị bỏ lỡ hoặc không được xử lý

Một instance có thể không nhận được event trong các tình huống:

- Instance chưa chạy hoặc chưa kết nối broker khi event được phát, trong khi cấu hình queue/topic không lưu message cho consumer đó.
- Consumer group, queue binding, subscription hoặc retention không được cấu hình theo nhu cầu replay.
- Instance dùng destination hoặc service ID không khớp với đích event.
- Nhiều instance vô tình dùng cùng service ID khiến Bus nhận diện sai origin hoặc định tuyến sai.
- Broker ACL, network policy hoặc credential ngăn instance subscribe.
- Consumer lỗi liên tục và message bị drop hoặc chuyển sang dead-letter destination theo cấu hình binder.
- Message đã hết thời gian lưu hoặc offset của consumer đã vượt qua vị trí cần xử lý.

Không thể kết luận một event chắc chắn được replay chỉ vì broker là Kafka hoặc RabbitMQ. Độ bền, retention, queue durability, consumer group, acknowledgement, retry và dead-letter behavior phụ thuộc broker cùng cấu hình binder. Hãy kiểm tra cấu hình thực tế của môi trường.

Spring Cloud Bus yêu cầu service ID duy nhất cho mỗi instance. Có thể cấu hình **spring.cloud.bus.id**; mặc định ID được tạo từ thông tin application và instance. Nếu chạy nhiều replica ngoài nền tảng tự cấp index, cần cung cấp index hoặc ID riêng cho từng instance. Xem [Spring Cloud Bus — Addressing Instances](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/addressing.html).

Ví dụ định danh cho từng replica:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    bus:
      id: order-service:replica-1:pod-7f8c
~~~

Đây là ví dụ cấu hình minh họa; giá trị định danh phải khác nhau ở mỗi replica. Không dùng cùng một ID tĩnh cho mọi replica.

## 6. Quan sát event bằng Bus trace

Spring Cloud Bus hỗ trợ trace event và acknowledgement. Với các phiên bản hiện hành có endpoint **/actuator/bustrace**, có thể bật:

~~~yaml
spring:
  cloud:
    bus:
      trace:
        enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh,bustrace
~~~

Sau đó đọc:

~~~text
GET /actuator/bustrace
~~~

Trace có thể ghi nhận:

- Thời điểm event được phát.
- Event ID.
- Event type, ví dụ **RefreshRemoteApplicationEvent**.
- Origin service.
- Destination.
- Acknowledgement từ các instance.

Tài liệu Spring Cloud Bus hiện hành dùng **spring.cloud.bus.trace.enabled=true** và yêu cầu expose endpoint **bustrace**. Các phiên bản cũ có thể dùng cách trace hoặc endpoint khác; hãy kiểm tra tài liệu đúng release train của dự án. Xem [Spring Cloud Stream — Bus Configuration and Tracing](https://docs.spring.io/spring-cloud-stream/reference/bus/configuration.html).

Ví dụ dữ liệu trace minh họa:

~~~json
{
  "timestamp": "2026-11-27T10:15:00Z",
  "origin": "config-admin:8080",
  "destination": "order-service:**",
  "id": "4c2a4b8a-6d10-4a7a-a40a-ec4a0e2b1a90",
  "type": "RefreshRemoteApplicationEvent",
  "signal": "spring.cloud.bus.sent"
}
~~~

Một instance nhận event có thể phát trace acknowledgement với cùng event ID. Dựa vào đó, vận hành có thể xác định instance nào đã báo nhận và instance nào chưa xuất hiện trong trace.

Tuy nhiên, trace acknowledgement chỉ là một tín hiệu trong chuỗi xử lý. Nó không thay thế xác nhận ứng dụng đã fetch đúng revision, tạo lại bean thành công và vượt qua readiness check.

Theo cấu hình mặc định hiện hành, Bus trace dùng **InMemoryTraceRepository**. Dữ liệu trong bộ nhớ có thể mất khi instance restart và không phù hợp làm audit log dài hạn. Nếu cần truy vấn tập trung hoặc lưu dấu vết rollout, hãy cung cấp TraceRepository phù hợp hoặc chuyển các sự kiện trace sang hệ thống quan sát tập trung.

## 7. Kết hợp broker metrics và application metrics

Bus trace cho biết đường đi của event ở tầng Bus. Broker metrics giúp tìm nguyên nhân giao nhận, còn application metrics xác nhận trạng thái cấu hình đã áp dụng.

| Lớp quan sát | Chỉ số hoặc dữ liệu cần theo dõi | Câu hỏi cần trả lời |
|---|---|---|
| Publisher | Số event gửi, lỗi publish, thời gian gửi | Lệnh refresh có phát được event không? |
| Broker | Queue depth, consumer lag, unacked, redelivery, DLQ count | Message đang chờ, bị giao lại hay bị chuyển DLQ? |
| Bus | Sent, ack, event ID, origin, destination, timestamp | Instance nào đã nhận event? |
| Config Client | Thời gian fetch, refresh success/failure, lỗi bind | Client có tải và xử lý cấu hình được không? |
| Application | Applied generation/revision, thời điểm áp dụng, readiness | Instance đang sử dụng cấu hình nào và có hoạt động tốt không? |

Nên gắn các thông tin sau vào log hoặc metric không nhạy cảm:

- Application, profile, label.
- Git commit SHA hoặc config revision.
- Rollout generation.
- Event ID và origin.
- Instance ID.
- Thời điểm nhận event, bắt đầu refresh và hoàn tất áp dụng.
- Kết quả thành công/thất bại cùng mã lỗi đã chuẩn hóa.

Không ghi toàn bộ Environment, password, token hoặc private key vào log. Nếu cần xác minh một giá trị nhạy cảm, chỉ ghi trạng thái đã có/thiếu hoặc fingerprint không thể khôi phục theo chính sách bảo mật.

## 8. Thiết kế xử lý idempotent

Một thao tác idempotent có thể được thực hiện nhiều lần mà trạng thái cuối không bị sai lệch. Với refresh cấu hình, mục tiêu là nhiều event cùng yêu cầu một trạng thái không khiến ứng dụng thực hiện side effect không cần thiết hoặc để lại resource cũ.

Một quy trình xử lý nên có:

1. Xác định application/profile/label và generation mong muốn.
2. Kiểm tra revision hiện tại của instance.
3. Nếu instance đã áp dụng generation đó, ghi nhận duplicate/no-op.
4. Nếu revision mới hơn đang được yêu cầu, tải cấu hình từ Config Server.
5. Kiểm tra response có đúng application, profile, label và revision dự kiến.
6. Áp dụng refresh; callback đóng tài nguyên cũ phải an toàn khi gọi lặp.
7. Buộc tạo hoặc kiểm tra target mới nếu cần.
8. Chỉ ghi nhận generation đã áp dụng sau khi bước xác minh thành công.

Ví dụ pseudocode cho custom event handler:

~~~java
public void handle(ConfigRefreshRequested event) {
    long desiredGeneration = rolloutState.currentGeneration();

    if (desiredGeneration <= appliedState.generation()) {
        return; // Event lặp hoặc trạng thái đã mới hơn
    }

    refreshFromConfigServer();

    ConfigRevision fetched = configRevisionReader.currentRevision();
    if (!fetched.matches(rolloutState.expectedRevision())) {
        throw new IllegalStateException("Fetched revision does not match rollout");
    }

    verifyCriticalBeans();
    appliedState.markApplied(desiredGeneration, fetched);
}
~~~

Đây là pseudocode mô tả nguyên tắc, không phải handler có thể sao chép trực tiếp cho event mặc định của Spring Cloud Bus. RefreshRemoteApplicationEvent mặc định không tự mang generation rollout tùy chỉnh. Muốn dùng generation, cần lưu trạng thái rollout ở một nguồn điều phối hoặc xây dựng custom event/handler phù hợp.

Với custom event gây side effect, có thể lưu event ID hoặc idempotency key đã xử lý trong kho dữ liệu bền vững. Cần cập nhật trạng thái xử lý theo cách nguyên tử phù hợp với side effect; chỉ lưu event ID trong memory không đủ nếu instance restart.

## 9. Đối soát trạng thái khi instance bỏ lỡ event

Đối soát trạng thái (reconciliation) là quá trình so sánh trạng thái thực tế của từng instance với trạng thái cấu hình mong muốn, sau đó sửa sai lệch. Đây là cơ chế phục hồi quan trọng vì event bus không nên là nơi duy nhất lưu trạng thái cần đạt.

Nguồn trạng thái mong muốn có thể là pipeline triển khai hoặc control plane lưu:

- Generation của lần rollout.
- Git commit SHA hoặc revision của backend.
- Application, profile và label.
- Thời điểm rollout bắt đầu.
- Danh sách instance dự kiến phải áp dụng.

Mỗi instance nên báo cáo trạng thái thực tế:

- Generation đã áp dụng.
- Revision đã fetch.
- Thời điểm refresh thành công gần nhất.
- Trạng thái health sau khi tạo lại bean.
- Lỗi gần nhất nếu refresh thất bại.

Bảng ví dụ:

| Instance | Desired generation | Applied generation | Revision | Trạng thái |
|---|---:|---:|---|---|
| order-0 | 42 | 42 | **7d2f8c1** | Đã đồng bộ |
| order-1 | 42 | 41 | **4ab31d0** | Cần đối soát |
| order-2 | 42 | 42 | **7d2f8c1** | Đã đồng bộ |
| order-3 | 42 | 0 | Chưa có | Chưa áp dụng |

Trong ví dụ này, order-1 và order-3 cần được xử lý. Pipeline không nên chỉ nhìn thấy event đã publish rồi kết luận rollout hoàn tất.

Một chu trình reconciliation có thể gồm:

~~~mermaid
flowchart TD
    A["Đọc desired generation và revision"] --> B["Thu thập applied state từ từng instance"]
    B --> C{"Tất cả instance đã đồng bộ?"}
    C -->|Có| D["Đánh dấu rollout hoàn tất"]
    C -->|Không| E["Xác định instance thiếu hoặc lệch revision"]
    E --> F["Kiểm tra broker, Config Server và lỗi refresh"]
    F --> G["Gửi lại refresh có mục tiêu hoặc yêu cầu instance tự reconcile"]
    G --> H["Xác minh revision và health"]
    H --> B
~~~

Có thể kích hoạt reconciliation theo ba cách:

- **Khi instance khởi động:** client đọc cấu hình và báo revision đã áp dụng trước khi readiness chuyển sang sẵn sàng.
- **Theo chu kỳ:** một controller hoặc job định kỳ so sánh desired/applied generation và yêu cầu refresh khi lệch.
- **Sau sự cố hoặc rollout:** pipeline kiểm tra từng instance và chỉ phát lại event cho nhóm chưa đồng bộ.

Không nên tạo một vòng polling quá dày làm Config Server và Git backend quá tải. Dùng chu kỳ có giới hạn, jitter và backoff; chỉ refresh khi phát hiện revision thực sự thay đổi.

## 10. Retry, dead-letter queue và phát lại message

Retry hữu ích khi lỗi có tính tạm thời, chẳng hạn Config Server timeout hoặc kết nối broker gián đoạn. Tuy nhiên, retry vô hạn có thể giữ message trong trạng thái lỗi, gây backlog và làm chậm các event khác.

Dead-letter queue/topic giúp giữ message không xử lý được sau khi retry hết giới hạn. Cấu hình cụ thể phụ thuộc binder:

- Với Kafka binder, DLQ phải được bật rõ ràng và consumer cần có group; DLQ không được bật mặc định. Sau khi số lần retry cấu hình đã hết, record lỗi có thể được chuyển đến dead-letter topic. Xem [Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html).
- Với Rabbit binder, cấu hình DLQ và retry sử dụng các thuộc tính riêng của binder. Không sao chép nguyên cấu hình Kafka sang RabbitMQ.
- Một số binder hoặc cấu hình có thể drop message lỗi, requeue hoặc chuyển DLQ. Hãy kiểm tra tài liệu binder đang dùng thay vì giả định mọi môi trường có cùng hành vi.

Khi phát lại message từ DLQ:

1. Xác định event ID, origin, destination và lỗi gốc.
2. Phân biệt lỗi tạm thời với lỗi vĩnh viễn.
3. Khắc phục nguyên nhân trước khi replay.
4. Giới hạn số lần replay và ghi lại người thực hiện.
5. Kiểm tra event có còn phù hợp với desired generation hiện tại không.
6. Nếu event đã cũ, có thể bỏ qua và chạy reconciliation để instance lấy trạng thái hiện hành.
7. Xác minh applied revision và health sau khi xử lý.

Không replay mù quáng một event cũ vào môi trường đã có revision mới. Với refresh notification mặc định, việc fetch lại trạng thái hiện tại thường phù hợp hơn việc cố áp dụng một snapshot cũ. Với custom event mang payload, cần kiểm tra generation trước khi áp dụng.

## 11. Định tuyến và service ID ảnh hưởng đến đối soát

Spring Cloud Bus dùng service ID để định tuyến event. Endpoint có thể nhắm đến một instance cụ thể hoặc tất cả instance của một service bằng destination pattern. Ví dụ:

~~~text
POST /actuator/busrefresh/order-service:9000
POST /actuator/busrefresh/order-service:**
~~~

Destination **order-service:**** nhắm đến các instance của service có ID phù hợp với pattern. Cần kiểm tra service ID thực tế trước khi gửi event; nếu ID không duy nhất hoặc pattern không khớp, một số instance có thể không xử lý message. Xem [Spring Cloud Bus — Addressing Instances](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/addressing.html).

Định tuyến đúng không thay thế reconciliation. Một event được gửi đến pattern toàn service vẫn có thể bị trễ hoặc không được xử lý bởi instance đang mất kết nối broker. Danh sách instance mong đợi phải được đối chiếu với danh sách instance báo applied state.

## 12. Quy trình vận hành một lần rollout cấu hình

Một quy trình có thể kiểm toán nên đi qua các bước:

1. **Tạo revision:** pipeline xác định Git commit hoặc revision cấu hình, application/profile/label và generation tăng dần.
2. **Kiểm tra Config Server:** gọi endpoint môi trường để xác nhận Config Server trả đúng revision trước khi phát event.
3. **Ghi desired state:** lưu generation và revision mong muốn vào hệ thống điều phối.
4. **Phát Bus event:** gửi refresh event đến service hoặc instance cần cập nhật; ghi nhận event ID.
5. **Theo dõi delivery:** kiểm tra sent/ack trong Bus trace và queue depth/consumer lag của broker.
6. **Theo dõi apply:** mỗi instance báo revision đã fetch, thời gian refresh và trạng thái health.
7. **Đối soát:** tìm instance thiếu acknowledgement, thiếu applied state hoặc đang ở revision cũ.
8. **Phục hồi có mục tiêu:** sửa broker/Config Server, replay nếu phù hợp hoặc yêu cầu instance reconcile lại.
9. **Xác nhận hoàn tất:** chỉ đánh dấu rollout thành công khi toàn bộ instance thuộc phạm vi đã đạt desired generation hoặc được xử lý theo chính sách ngoại lệ được phê duyệt.

Một acknowledgement không nên được dùng làm điều kiện duy nhất để hoàn tất rollout. Điều kiện hoàn tất nên dựa trên trạng thái cấu hình thực tế và health của từng instance.

## 13. Bảo vệ endpoint và dữ liệu vận hành

Các endpoint **busrefresh**, **busenv** và endpoint trace có thể ảnh hưởng diện rộng hoặc tiết lộ metadata vận hành. Hãy:

- Chỉ expose endpoint cần thiết.
- Bảo vệ bằng xác thực và phân quyền; giới hạn ai có quyền phát refresh.
- Giới hạn destination để tránh refresh nhầm toàn bộ hệ thống.
- Bảo vệ broker bằng TLS, ACL và credential riêng.
- Không đưa secret hoặc nội dung cấu hình nhạy cảm vào custom event.
- Lưu audit record cho người yêu cầu, thời điểm, lý do, event ID và phạm vi đích.
- Giới hạn quyền xem Bus trace và DLQ vì metadata có thể tiết lộ topology hoặc tên service nội bộ.

Một event refresh lặp có thể tạo tải lên Config Server và khiến nhiều target bị hủy/tạo lại. Vì vậy, quyền phát event cần được quản lý tương tự quyền triển khai cấu hình.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc khắc phục |
|---|---|---|
| Event sent nhưng một instance không có ack | Instance mất kết nối, sai destination hoặc service ID trùng | Kiểm tra broker subscription, Bus trace và ID từng replica |
| Event đến muộn | Queue backlog, consumer lag hoặc refresh chậm | So sánh timestamp sent/ack với broker và Config Server metrics |
| Một instance refresh nhiều lần | Redelivery, pipeline retry hoặc operator gửi lặp | Đối chiếu event ID, origin và log refresh; làm thao tác idempotent |
| Instance có ack nhưng vẫn dùng revision cũ | Ack chỉ phản ánh event được nhận, refresh/fetch có thể thất bại | Kiểm tra applied revision, refresh error và readiness |
| Một số instance không nhận event sau restart | Queue/topic retention hoặc consumer group không giữ vị trí cần thiết | Kiểm tra durability, offset, subscription và replay policy |
| Event cũ đến sau event mới | Publish đồng thời, retry hoặc thứ tự xử lý khác nhau | Dùng generation tăng dần và luôn đối chiếu desired state |
| DLQ tăng liên tục | Consumer xử lý lỗi vĩnh viễn hoặc retry policy không phù hợp | Phân tích exception, sửa nguyên nhân rồi replay có kiểm soát |
| Rollout báo thành công dù còn instance lệch | Chỉ kiểm tra publish/ack, không kiểm tra applied state | Bổ sung reconciliation theo từng instance và revision |

## 15. Tự kiểm tra

1. Vì sao cần phân biệt event được gửi, broker nhận, instance ack và cấu hình thực sự được áp dụng?
2. Những nguyên nhân nào có thể khiến một refresh event bị giao trễ?
3. Vì sao Bus có cơ chế bỏ qua event do origin phát ra nhưng vẫn không bảo đảm exactly-once cho mọi event?
4. Nếu hai refresh event đến sai thứ tự, vì sao generation tăng dần hữu ích hơn việc so sánh Git SHA?
5. Vì sao Bus acknowledgement không chứng minh target bean mới đã khởi tạo thành công?
6. Broker, binder và consumer group ảnh hưởng thế nào đến khả năng replay event bị bỏ lỡ?
7. Cần ghi nhận dữ liệu nào để so sánh desired state với applied state của từng instance?
8. Khi nào nên replay DLQ và khi nào nên bỏ event cũ rồi chạy reconciliation?
9. Vì sao service ID phải duy nhất trong một Bus deployment?
10. Điều kiện nào nên được dùng để đánh dấu một rollout cấu hình là hoàn tất?

Hãy dựng một môi trường test có Config Server, hai hoặc ba Config Client instance và một broker. Phát refresh event rồi mô phỏng ba tình huống: làm chậm consumer, gửi lặp cùng yêu cầu và tạm ngắt một instance khỏi broker. Ghi event ID, origin, destination, thời điểm sent/ack, broker lag và revision mà từng instance đang dùng. Sau đó khôi phục kết nối, chạy reconciliation để đưa tất cả instance về cùng generation. Cuối cùng, xác minh rằng duplicate event không tạo side effect không an toàn và rollout chỉ được đánh dấu hoàn tất sau khi từng instance đạt revision mong muốn.

## Tài liệu tham khảo

- [Spring Cloud Bus — Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)
- [Spring Cloud Bus — Addressing Instances](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/addressing.html)
- [Spring Cloud Stream — Bus Configuration and Tracing](https://docs.spring.io/spring-cloud-stream/reference/bus/configuration.html)
- [Spring Cloud Stream — Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html)

