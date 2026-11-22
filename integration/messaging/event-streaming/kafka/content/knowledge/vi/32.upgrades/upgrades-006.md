# Nâng client độc lập và kiểm thử thương lượng protocol

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn nâng cấp Kafka client độc lập với broker, kiểm tra khả năng tương thích và xác minh quá trình thương lượng phiên bản protocol giữa client với từng broker.

Kafka client và Kafka broker không bắt buộc phải cùng phiên bản. Client dùng Kafka wire protocol để gửi request đến broker; trong quá trình thiết lập kết nối, hai phía trao đổi thông tin API versions và client chọn phiên bản request nằm trong phạm vi broker hỗ trợ. Cơ chế này cho phép nhiều thế hệ client hoạt động với một cluster trong thời gian migration, nhưng không bảo đảm mọi tính năng mới đều dùng được trên broker cũ. Nâng client cần kiểm tra cả protocol compatibility, hành vi producer/consumer, serializer, security, dependency framework và các default có thể thay đổi giữa các phiên bản thư viện.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao client có thể được nâng cấp độc lập với broker.
- Phân biệt Kafka client version, broker version, API version và cluster feature level.
- Mô tả vai trò của ApiVersions request/response trong Kafka wire protocol.
- Giải thích cách client chọn API version chung cho từng request type.
- Đọc API version range broker công bố bằng kafka-broker-api-versions.sh.
- Phân biệt broker API capability inventory với API version thực tế được chọn trên connection.
- Xây dựng compatibility matrix giữa client cũ/mới và broker cũ/mới.
- Phân biệt protocol compatibility với record format, compression, schema và application semantics.
- Nâng Kafka Java client cùng Spring Kafka/Spring Boot dependency có kiểm soát.
- Kiểm tra producer, consumer, AdminClient, Kafka Streams và Connect integration.
- Kiểm thử TLS/SASL, idempotence, transaction, rebalance và offset behavior.
- Triển khai canary, theo dõi metrics và rollback client.
- Xác định khi nào tính năng mới cần broker upgrade hoặc cluster feature activation.
- Viết checklist nâng client độc lập có thể lặp lại.

## 2. Client và broker có thể nâng cấp độc lập

Kafka client là thư viện hoặc ứng dụng giao tiếp với broker qua Kafka protocol. Ví dụ:

- Java producer/consumer dùng dependency org.apache.kafka:kafka-clients.
- Spring Kafka dùng Kafka client thông qua dependency của framework.
- Kafka Streams dùng Kafka client cùng thư viện Streams.
- Kafka Connect worker và connector plugin sử dụng Kafka client trong runtime Connect.
- Client viết bằng .NET, Go, Python, Node.js hoặc ngôn ngữ khác dùng implementation riêng của Kafka protocol.

Broker là server lưu partition, xử lý produce/fetch request, quản lý consumer group, metadata và replication. Hai phía có chu kỳ phát hành khác nhau.

Một tổ chức có thể nâng Java client trong một service trước, quan sát một nhóm nhỏ, sau đó nâng các service còn lại. Broker cluster vẫn giữ nguyên phiên bản trong giai đoạn này nếu client mới còn tương thích với broker hiện tại.

### 2.1. Lợi ích của nâng client độc lập

- Giảm phạm vi thay đổi so với nâng toàn bộ broker cluster.
- Cho phép cập nhật thư viện bảo mật hoặc sửa lỗi client sớm.
- Kiểm chứng thay đổi producer/consumer trong một workload canary.
- Tách lỗi ứng dụng khỏi lỗi rolling broker upgrade.
- Dễ rollback dependency nếu client mới gây regression.
- Tạo compatibility window để nhiều service nâng cấp theo lịch riêng.

Nâng client độc lập vẫn có rủi ro. Phiên bản mới có thể thay đổi default, timeout, retry, partitioner, group protocol hoặc hành vi serialization. Một client kết nối thành công không chứng minh toàn bộ business flow hoạt động giống trước.

### 2.2. Không cần đồng bộ mọi client cùng một ngày

Trong một cluster, nhiều service có thể dùng các phiên bản Kafka client khác nhau nếu tất cả nằm trong compatibility range được hỗ trợ. Nên quản lý một ma trận version được kiểm thử thay vì buộc mọi service nâng đồng loạt.

Ví dụ minh họa:

| Workload | Client hiện tại | Client mục tiêu | Cách rollout |
|---|---|---|---|
| orders-api | Java client cũ | Java client mới | Canary một instance |
| payments-worker | Java client cũ | Java client mới | Sau khi producer test đạt |
| audit-consumer | Client Python | Giữ nguyên | Không liên quan thay đổi Java |
| streams-app | Kafka Streams cũ | Streams tương thích mới | Test state restore và internal topics |
| connect-worker | Connect runtime hiện tại | Giữ nguyên trong đợt này | Nâng riêng theo policy Connect |

Không coi một lần nâng Java client là lý do phải nâng Connect worker, broker hoặc mọi ứng dụng khác.

## 3. Phân biệt các lớp phiên bản

Một số khái niệm có tên gần nhau nhưng biểu diễn những thứ khác nhau.

| Khái niệm | Phạm vi | Ý nghĩa |
|---|---|---|
| Kafka client version | Thư viện/ứng dụng | Version package Kafka client |
| Kafka broker version | Server | Version binary đang chạy trên broker |
| API version | Một Kafka request type | Version của request/response schema cho API đó |
| Protocol version | Wire protocol | Tập API, request/response và encoding được client/broker hỗ trợ |
| Record batch format | Dữ liệu record | Cách record batch được encode trong log/request |
| Compression codec | Payload/batch | Thuật toán nén như gzip, snappy, lz4 hoặc zstd tùy hỗ trợ |
| Schema version | Event payload | Version Avro, Protobuf, JSON Schema hoặc contract riêng |
| inter.broker.protocol.version | Broker-to-broker ở các release có cấu hình này | Mốc tương thích protocol giữa broker |
| metadata.version | Kafka cluster feature level trong KRaft | Mức metadata/feature được cluster kích hoạt |

### 3.1. Client version không phải API version

Ví dụ một ứng dụng dùng Kafka client version X. Thư viện đó có thể hỗ trợ nhiều phiên bản Produce API, Fetch API, Metadata API và consumer group API.

Khi kết nối broker, client không chỉ gửi một chuỗi version của thư viện rồi yêu cầu broker phải giống hệt. Nó xác định API version có thể dùng cho từng loại request dựa trên khả năng được broker công bố.

### 3.2. API version không phải record schema version

Kafka protocol API version mô tả request/response giữa client và broker. Schema version mô tả payload event mà producer ghi và consumer giải mã.

Nâng client có thể không làm thay đổi payload schema. Ngược lại, một ứng dụng có thể thay đổi schema mà không nâng Kafka client. Hai thay đổi cần kiểm thử riêng.

### 3.3. API version không phải cluster feature level

Broker có thể hỗ trợ một API request version nhưng tính năng nghiệp vụ liên quan còn phụ thuộc cấu hình hoặc feature được kích hoạt trong cluster.

Với KRaft, metadata.version là cluster feature level được quản lý qua metadata quorum. Kafka client không tự nâng metadata.version khi kết nối. Không thay đổi cluster feature level chỉ để nâng thư viện client.

inter.broker.protocol.version liên quan giao tiếp broker-to-broker trong các phiên bản có sử dụng cấu hình này; nó không phải nút điều khiển API version của client. Hãy theo đúng tài liệu của release Kafka đang chạy khi nâng broker.

## 4. Cơ chế thương lượng ApiVersions

Kafka wire protocol định nghĩa ApiVersions API. Client dùng request này để hỏi broker các API key và version range mà broker hỗ trợ.

Một response thường mô tả cho từng API:

- API key hoặc tên API.
- Minimum version broker hỗ trợ.
- Maximum version broker hỗ trợ.
- Một số thông tin bổ sung theo version của ApiVersions response.

Ví dụ minh họa:

~~~text
Broker API capabilities:
  Produce: min=3, max=11
  Fetch: min=4, max=16
  Metadata: min=0, max=12
  FindCoordinator: min=0, max=6
  ApiVersions: min=0, max=3
~~~

Các con số trên chỉ minh họa cách đọc version range, không phải output hay cam kết cho một release Kafka cụ thể.

### 4.1. Client chọn version chung

Giả sử client hỗ trợ một API trong khoảng 4 đến 12, broker hỗ trợ khoảng 3 đến 10. Phạm vi chung là 4 đến 10. Client thường chọn version cao nhất trong phạm vi chung mà implementation của nó hỗ trợ.

\[
V_{common} = [\max(V_{client,min}, V_{broker,min}),\ \min(V_{client,max}, V_{broker,max})]
\]

Nếu:

\[
\max(V_{client,min}, V_{broker,min}) >
\min(V_{client,max}, V_{broker,max})
\]

thì không có version chung cho API đó. Request tương ứng có thể thất bại vì không tương thích.

Việc chọn version diễn ra theo từng API key. Client có thể dùng version khác nhau cho Produce, Fetch, Metadata và các request khác trên cùng một broker connection.

### 4.2. Negotiation theo từng broker connection

Một client thường kết nối tới nhiều broker theo metadata và leader placement. Khả năng API của broker có thể khác trong giai đoạn rolling broker upgrade hoặc khi cluster có node chưa đồng nhất.

Client cần thương lượng với broker mà nó kết nối, không nên giả định một response từ bootstrap broker đại diện tuyệt đối cho tất cả broker. Khi debug, kiểm tra broker cụ thể nhận request lỗi.

### 4.3. Thứ tự khởi tạo connection

Quá trình mở connection còn liên quan TCP, TLS, SASL và authentication. Thứ tự chi tiết có thể phụ thuộc security protocol, client và phiên bản. ApiVersions là cơ chế thương lượng Kafka API; TLS handshake và SASL authentication là các lớp riêng.

Không suy luận rằng lỗi SASL đồng nghĩa API version không tương thích, hoặc ngược lại. Phải phân loại lỗi theo lớp transport, authentication, authorization và protocol.

### 4.4. Flexible versions và tagged fields

Một số Kafka API version mới dùng flexible version encoding và tagged fields để bổ sung trường mà không phá vỡ parser tương thích. Đây là chi tiết wire protocol do client library xử lý.

Không tự viết raw request hoặc sửa byte payload để “bật” một API version. Dùng Kafka client library tương thích và kiểm tra bằng integration test thực tế.

## 5. Compatibility giữa client mới và broker cũ

Kafka được thiết kế để hỗ trợ nhiều phiên bản client/broker cùng tồn tại trong phạm vi tương thích được công bố. Tuy nhiên, khả năng kết nối và khả năng dùng tính năng mới là hai câu hỏi khác nhau.

### 5.1. Client cũ kết nối broker mới

Thông thường client cũ sẽ sử dụng API version mà nó hỗ trợ. Broker mới tiếp tục phục vụ các version cũ trong compatibility range.

Rủi ro còn lại:
- Broker có thể bỏ hỗ trợ một API version rất cũ ở release tương lai.
- Default hoặc semantics phía broker có thể thay đổi.
- Client cũ có thể thiếu khả năng xử lý behavior mới.
- Một số feature yêu cầu client mới dù broker mới đã hỗ trợ.

### 5.2. Client mới kết nối broker cũ

Client mới có thể fallback về API version chung, nhưng các tính năng chỉ có ở broker mới sẽ không hoạt động.

Ví dụ:
- Client mới có API cho một thao tác quản trị mà broker cũ chưa hỗ trợ.
- Client muốn dùng group protocol mới nhưng broker chưa cung cấp feature tương ứng.
- Client cấu hình compression codec hoặc record feature mà broker cũ không hiểu.
- Ứng dụng gọi API mới và nhận lỗi unsupported/invalid request.

Không chỉ test kết nối bootstrap. Hãy gọi các API thực tế mà ứng dụng sử dụng.

### 5.3. Ma trận tương thích tối thiểu

| Client | Broker | Kỳ vọng | Kiểm thử |
|---|---|---|---|
| Cũ | Cũ | Baseline hiện tại | Regression |
| Cũ | Mới | Client giữ API cũ | Đảm bảo service cũ tiếp tục chạy trong broker rollout |
| Mới | Cũ | Dùng API version chung | Xác minh không gọi feature mới ngoài broker support |
| Mới | Mới | Có thể dùng API/feature mới | Test riêng trước khi bật feature |

Với task nâng client độc lập, cặp quan trọng nhất là client mục tiêu kết nối broker hiện tại. Cặp client cũ/broker mới vẫn hữu ích để bảo đảm quá trình nâng broker sau này không phá service chưa được nâng.

## 6. Những gì ApiVersions không bảo đảm

ApiVersions negotiation không chứng minh mọi thứ trong ứng dụng đều tương thích.

| Phạm vi | ApiVersions giải quyết? | Cần kiểm tra thêm |
|---|---|---|
| Request/response schema | Có | API version chung và request behavior |
| Producer payload schema | Không | Schema Registry và contract test |
| Compression codec | Không đầy đủ | Broker/client codec support và record batch |
| TLS certificate | Không | Trust chain, hostname, protocol và cipher |
| SASL mechanism | Không | Broker/client mechanism và callback |
| ACL | Không | Principal mapping và authorization |
| Transaction semantics | Không đầy đủ | Transaction coordinator, fencing và read_committed |
| Consumer group behavior | Không đầy đủ | Group protocol, assignor, rebalance và commit |
| Kafka Streams state | Không | Internal topic, changelog và state restoration |
| Connect plugin | Không | Worker/plugin compatibility và connector behavior |
| Business idempotency | Không | eventId, database constraint và side effect |

Một client có thể negotiate thành công rồi vẫn gặp TopicAuthorizationException, schema deserialization error, unsupported compression, transaction timeout hoặc business duplicate.

## 7. Record format, compression và feature boundary

Nâng client có thể thay đổi cách producer encode record batch hoặc chọn compression codec. Đây là lớp dữ liệu riêng với API request version.

### 7.1. Record batch

Producer gửi record theo batch. Broker kiểm tra và lưu batch theo format Kafka hỗ trợ. Khi nâng client, kiểm tra:
- Producer có tạo record batch format mà broker hiện tại hiểu không?
- Broker có cần upgrade trước khi dùng một feature encode mới không?
- Consumer cũ có thể giải mã record mới không?
- Có yêu cầu interop với connector hoặc tool ngoài Kafka client không?

Không giả định API version chung đồng nghĩa mọi record format đều tương thích.

### 7.2. Compression

Kiểm tra codec mà client mới được cấu hình dùng. Broker, consumer và connector phải hỗ trợ codec tương ứng. Nếu codec mới chỉ được hỗ trợ bởi một phần client fleet, record có thể ghi thành công nhưng consumer cũ không đọc được.

Trong canary, gửi record với codec mục tiêu và kiểm tra tất cả consumer quan trọng. Không bật codec mới cho toàn bộ topic trước khi xác nhận compatibility.

### 7.3. Tính năng cần broker hỗ trợ

Một số tính năng có thể cần:
- API version mới.
- Broker configuration mới.
- Cluster feature level đã được kích hoạt.
- Metadata hoặc protocol capability ở tất cả broker liên quan.
- Consumer group coordinator support.
- Transaction coordinator support.
- ACL/resource type mới.

Lập danh sách feature theo từng API và broker release. Không dùng “client mới đã connect” làm tiêu chí duy nhất để bật tính năng.

## 8. Chuẩn bị nâng Kafka Java client

Với Java application, Kafka client thường là dependency trực tiếp hoặc dependency bắc cầu từ Spring Kafka, Kafka Streams hay Connect runtime.

### 8.1. Kiểm tra dependency graph

Gradle:

~~~bash
./gradlew dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.apache.kafka:kafka-clients
~~~

Ghi lại:
- Phiên bản kafka-clients thực tế được resolve.
- Thư viện nào kéo dependency vào.
- Có dependency constraint hoặc version override không.
- Runtime artifact có trùng hoặc lệch version không.
- Có thư viện connector/client khác dùng Kafka API riêng không.

Không chỉ đọc version khai báo trong build file. Version thực tế được dependency management resolve mới là thứ chạy ở production.

### 8.2. Spring Boot và Spring Kafka

Spring Boot dependency management có thể quản lý Spring Kafka và các dependency liên quan. Trước khi override kafka-clients, kiểm tra compatibility giữa:
- Spring Boot release.
- Spring Kafka release.
- Kafka client release.
- Kafka Streams release nếu dùng.
- Java runtime version.

Ví dụ Gradle dùng dependency management của Spring Boot:

~~~groovy
dependencies {
    implementation("org.springframework.kafka:spring-kafka")
}
~~~

Nếu dự án quản lý version thủ công, pin các dependency theo ma trận tương thích đã kiểm chứng. Không copy một version kafka-clients bất kỳ vào build file chỉ vì version đó mới hơn.

### 8.3. Kafka Streams

Kafka Streams library gắn với Kafka client version. Khi nâng Streams, cần kiểm tra:
- Kafka client transitive version.
- State store compatibility.
- Internal topic configuration.
- Changelog và repartition topic.
- Application reset/recovery behavior.
- Rolling upgrade policy của Streams version đang dùng.

Không nâng kafka-clients độc lập khỏi Kafka Streams nếu version pair nằm ngoài compatibility guidance của release đó.

### 8.4. Kafka Connect

Kafka Connect worker runtime và plugin có dependency/lifecycle riêng. Connector plugin có thể đóng gói hoặc yêu cầu một số version client/library cụ thể.

Nâng client của một ứng dụng producer không đồng nghĩa phải nâng Connect worker. Nếu nâng Connect runtime, kiểm tra worker protocol compatibility, plugin isolation, converter, SMT, connector version và internal topic behavior theo tài liệu của release.

### 8.5. Pin và ghi nhận version

Trong build pipeline, lưu:
- Version khai báo.
- Version được resolve.
- Java runtime.
- Spring Boot/Spring Kafka.
- Kafka Streams/Connect nếu có.
- Serializer và Schema Registry client.
- Client configuration có liên quan behavior.

Dùng dependency lock hoặc dependency constraints nếu dự án cần tái lập chính xác artifact giữa CI và production.

## 9. Kiểm kê broker API capability

Trước khi nâng client, lưu broker version và API range mà mỗi broker công bố.

### 9.1. Dùng kafka-broker-api-versions.sh

Ví dụ:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server broker-1.internal:9092
~~~

Nếu cluster yêu cầu security config:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server broker-1.internal:9092 --command-config client.properties
~~~

Lệnh truy vấn các broker được client khám phá và hiển thị API version range mà broker hỗ trợ. Output có thể thay đổi theo Kafka release.

### 9.2. Cách đọc output

Đọc:
- Broker endpoint/ID.
- API key hoặc tên API.
- Minimum API version.
- Maximum API version.
- Lỗi kết nối hoặc broker không phản hồi.

Dùng output để xác định broker nào có capability khác biệt. Nếu broker đang rolling upgrade, lưu kết quả từ nhiều thời điểm để thấy API range thay đổi.

### 9.3. Giới hạn của lệnh kiểm kê

kafka-broker-api-versions.sh cho biết broker công bố hỗ trợ version range nào. Nó không chứng minh client ứng dụng cụ thể đã chọn version nào cho mỗi request trong một session.

Để xác minh negotiated version thực tế:
- Dùng protocol/request trace hoặc logging phù hợp với client và broker release.
- Thu thập request API key/version trên connection trong môi trường test.
- Kiểm tra lỗi unsupported version và fallback behavior.
- Nếu TLS mã hóa traffic, packet capture thông thường không đọc được payload Kafka; dùng logging/instrumentation tại endpoint thay vì giả định có thể giải mã từ network trace.

Protocol debug logging có thể tạo log lớn hoặc lộ metadata. Chỉ bật trong lab/canary trong thời gian ngắn, bảo vệ log và tắt sau kiểm thử.

## 10. Thiết kế compatibility test matrix

Trước rollout, xác định các cặp version cần kiểm thử.

### 10.1. Ma trận broker/client

| Case | Client | Broker | Mục tiêu |
|---|---|---|---|
| A | Phiên bản production hiện tại | Broker hiện tại | Baseline |
| B | Phiên bản mục tiêu | Broker hiện tại | Mục tiêu của đợt nâng độc lập |
| C | Phiên bản hiện tại | Broker phiên bản kế hoạch | Chuẩn bị broker upgrade sau này |
| D | Phiên bản mục tiêu | Broker phiên bản kế hoạch | Tương thích tương lai |
| E | Phiên bản tối thiểu còn hỗ trợ | Broker hiện tại | Giới hạn compatibility nếu fleet còn client cũ |

Không phải môi trường nào cũng cần chạy tất cả case. Nhưng cần xác định rõ client fleet nào còn tồn tại và broker version range nào phải hỗ trợ.

### 10.2. Ma trận theo security

Kiểm thử từng listener/security path mà service thật sử dụng:
- PLAINTEXT chỉ trong lab nếu được phép.
- TLS với certificate/trust chain production-like.
- SASL/SCRAM.
- SASL/OAUTHBEARER nếu triển khai.
- mTLS/principal mapping nếu triển khai.

Một client mới có thể đổi yêu cầu TLS provider, JDK hoặc SASL callback. Không chỉ test bằng local plaintext cluster rồi kết luận production security tương thích.

### 10.3. Ma trận theo workload

- Producer: sync/async send, retries, idempotence, transactions, compression.
- Consumer: subscribe, assign, rebalance, commit, pause/resume, seek.
- AdminClient: create/describe topic, ACL/config APIs nếu ứng dụng dùng.
- Streams: state restoration, repartition, changelog và processing guarantee.
- Connect: source/sink task, converter, SMT, DLQ và plugin.
- Observability: client metrics, logs, tracing và alert.

## 11. Kiểm thử producer sau nâng client

Producer test cần xác minh cả protocol lẫn semantics.

### 11.1. Gửi và nhận acknowledgement

Gửi record vào topic test, đợi acknowledgement và kiểm tra:
- Topic.
- Partition.
- Offset.
- Timestamp.
- Key và headers.
- Serialization/deserialization.
- Error callback và retry.

Ví dụ Java:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

// producer là KafkaProducer đã được tạo với cấu hình của bài test.
ProducerRecord<String, String> record =
    new ProducerRecord<>("client-upgrade-test", "order-42", "{\"id\":\"order-42\"}");

RecordMetadata metadata = producer.send(record).get();

System.out.printf(
    "topic=%s partition=%d offset=%d%n",
    metadata.topic(),
    metadata.partition(),
    metadata.offset()
);
~~~

Đây là ví dụ kiểm thử đồng bộ để dễ quan sát. Trong production, cân nhắc async send và callback để tránh block request thread.

### 11.2. Idempotence và retry

Kiểm tra:
- enable.idempotence.
- acks.
- retries.
- max.in.flight.requests.per.connection.
- Request timeout và delivery timeout.
- Duplicate behavior khi broker/network tạm gián đoạn.

Một số default có thể thay đổi giữa client release. Ghi rõ cấu hình quan trọng thay vì phụ thuộc ngầm vào default mới.

### 11.3. Transactional producer

Nếu ứng dụng dùng transaction:
1. Khởi tạo producer với transactional.id.
2. Gọi initTransactions.
3. Begin transaction.
4. Gửi record.
5. Commit hoặc abort.
6. Đọc bằng consumer isolation.level=read_committed.
7. Xác minh aborted record không bị lộ cho consumer read_committed.
8. Kiểm tra producer fencing và transaction timeout.

Thử failover coordinator hoặc network timeout trong môi trường test. Không chỉ kiểm tra send success.

### 11.4. Partitioning behavior

Một client release có thể thay đổi partitioner hoặc batching defaults. Kiểm tra:
- Cùng key có tiếp tục vào partition như kỳ vọng không?
- Custom partitioner có còn tương thích không?
- Null key có phân phối khác không?
- Ordering theo key có được giữ không?
- Batch size và compression ratio có thay đổi không?

Không tăng partition count trong cùng change chỉ để “tối ưu” client mới; điều đó làm khó xác định nguyên nhân nếu ordering thay đổi.

## 12. Kiểm thử consumer sau nâng client

Consumer test cần kiểm tra group membership và offset semantics.

### 12.1. Subscribe và assignment

Xác minh:
- Group ID.
- Topic subscription.
- Partition assignment.
- Rebalance callback.
- Assignment strategy.
- Cooperative/eager behavior nếu cấu hình.
- Consumer group protocol đang dùng.

Không bật group protocol hoặc assignor mới cùng lúc nâng client nếu chưa có compatibility test riêng.

### 12.2. Offset commit

Kiểm tra:
- Auto commit hoặc manual commit.
- Commit sync/async.
- Retry khi commit lỗi.
- Duplicate khi xử lý xong nhưng commit thất bại.
- Offset reset policy khi group chưa có offset.
- Rebalance giữa lúc xử lý record.

Consumer nâng version có thể kết nối thành công nhưng thay đổi timing/rebalance khiến duplicate hoặc lag khác trước. Đo business processing và committed offset riêng.

### 12.3. Ordering

Kafka giữ ordering trong một partition. Sau nâng client, kiểm tra:
- Key serialization không đổi.
- Partitioner không đổi ngoài ý muốn.
- Consumer không xử lý song song cùng partition theo cách phá ordering.
- Retry/DLT không tạo ra thứ tự nghiệp vụ sai.
- Rebalance không làm side effect trùng.

### 12.4. Consumer group protocol

Một số release bổ sung hoặc cải tiến consumer group protocol/assignor. Việc sử dụng protocol mới phụ thuộc cả client và broker coordinator support.

Trong đợt nâng client độc lập:
- Giữ group protocol hiện tại nếu mục tiêu chỉ là nâng thư viện.
- Chỉ bật protocol mới khi broker support và migration policy đã được xác minh.
- Kiểm thử mixed-version consumer members nếu rollout rolling.
- Theo dõi rebalance rate, assignment churn và group coordinator errors.

## 13. Kiểm thử AdminClient và API quản trị

AdminClient có thể dùng API mà broker cũ chưa hỗ trợ. Kiểm thử chính xác những thao tác ứng dụng gọi.

Ví dụ:

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.DescribeClusterResult;

// properties chứa bootstrap.servers và cấu hình security phù hợp.
try (AdminClient admin = AdminClient.create(properties)) {
    DescribeClusterResult cluster = admin.describeCluster();

    System.out.println("clusterId=" + cluster.clusterId().get());
    System.out.println("nodes=" + cluster.nodes().get());
}
~~~

Các thao tác nên kiểm tra nếu ứng dụng dùng:
- DescribeCluster.
- DescribeTopics.
- CreateTopics.
- DescribeConfigs.
- IncrementalAlterConfigs.
- ACL describe/create/delete.
- Consumer group describe/delete.
- Partition reassignment hoặc preferred leader election API.

Không kết luận AdminClient tương thích chỉ vì describeCluster thành công. API quản trị mới có thể có minimum broker version cao hơn.

## 14. Kiểm thử Spring Kafka

Spring Kafka thêm abstraction như KafkaTemplate, listener container, error handler, transaction manager và retry mechanism. Nâng Kafka client có thể ảnh hưởng qua dependency bắc cầu hoặc thay đổi behavior bên dưới.

Kiểm tra:
- KafkaTemplate send future/callback API.
- ProducerFactory và ConsumerFactory.
- Listener container startup/shutdown.
- AckMode và manual acknowledgement.
- CommonErrorHandler và retry behavior.
- DeadLetterPublishingRecoverer.
- Transaction manager và transaction synchronization.
- Batch listener.
- RecordInterceptor.
- Micrometer metrics và observation/tracing.
- Serializer/deserializer và type mapping.

Ví dụ test slice/integration cần dùng broker thật tương thích mục tiêu. Mock producer/consumer chỉ kiểm tra application logic, không kiểm tra wire protocol negotiation.

## 15. Kiểm thử protocol negotiation thực tế

Protocol negotiation cần được kiểm tra trên đúng client artifact và broker version mà production dùng.

### 15.1. Kiểm kê broker API range

Chạy kafka-broker-api-versions.sh với từng bootstrap endpoint hoặc một endpoint có thể khám phá toàn cluster. Lưu output trước và sau thay đổi broker nếu có rolling upgrade.

### 15.2. Chạy client mục tiêu

Dùng một integration test application được build với đúng kafka-clients version mục tiêu. Kết nối vào broker hiện tại qua listener/security giống production.

Kiểm tra:
- Client kết nối tất cả broker cần thiết.
- ApiVersions handshake không thất bại.
- Metadata refresh hoạt động.
- Produce/fetch request thành công.
- Coordinator discovery và group request thành công.
- Admin API được ứng dụng dùng hoạt động.
- Không có UnsupportedVersionException hoặc protocol parse error.

### 15.3. Xác minh API version được chọn

Nếu cần biết chính xác request nào dùng API version nào:
- Bật protocol/request tracing phù hợp trong môi trường test.
- Thu thập API key và request version tại client/broker endpoint.
- Đối chiếu version được chọn với common range.
- Lưu bằng chứng cho các API quan trọng như Produce, Fetch, Metadata, FindCoordinator và OffsetCommit.

kafka-broker-api-versions.sh chỉ kiểm kê range broker công bố; không phải log của version được client chọn. Không báo cáo rằng negotiation cụ thể đã được xác minh nếu chỉ chạy lệnh kiểm kê.

### 15.4. Test khi broker đang rolling upgrade

Nếu cluster có broker cũ và mới cùng tồn tại:
- Lấy API range từ từng broker.
- Kết nối client đến broker leader của topic test.
- Kiểm tra metadata refresh khi leader thay đổi.
- Kiểm tra coordinator movement.
- Kiểm tra client reconnect sau broker restart.
- Kiểm tra request retry và timeout.
- Đảm bảo client không phụ thuộc một API chỉ có trên broker mới trong thời gian mixed version.

## 16. Lỗi thường gặp khi nâng client

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| UnsupportedVersionException | Không có API version chung hoặc gọi API chưa được broker hỗ trợ | Kiểm tra client/broker API range và feature requirement |
| UnsupportedVersion ở Admin API | Client gọi API quản trị mới | Dùng API cũ tương thích hoặc nâng broker theo kế hoạch |
| AuthenticationException | SASL/TLS config hoặc callback khác | Kiểm tra security layer, JDK và client config |
| TopicAuthorizationException | Principal mapping/ACL | Kiểm tra identity và quyền resource |
| SerializationException | Serializer/schema dependency thay đổi | Kiểm tra schema ID, registry và serializer version |
| RecordTooLargeException | Kích thước record/batch hoặc broker limit | Kiểm tra max.request.size, message limit và batch |
| Lỗi codec/compression | Consumer hoặc thành phần trung gian không hỗ trợ codec | Dùng codec chung hoặc nâng thành phần cần thiết |
| Transaction timeout | Timeout/retry/coordinator behavior thay đổi | Kiểm tra transaction config và coordinator health |
| Consumer rebalance tăng | Group protocol, assignor hoặc timing | Giữ protocol cũ và so sánh metrics |
| Consumer lag tăng | Processing, fetch hoặc commit behavior đổi | Đo poll/process/commit và downstream |
| Producer throughput giảm | Batch/linger/compression default thay đổi | So sánh batch size, request rate và compression |
| TLS handshake failure | JDK/provider/cipher/certificate mismatch | Kiểm tra trust chain, SAN, protocol và cipher |
| Connect plugin NoSuchMethodError | Plugin dùng dependency Kafka khác | Kiểm tra classloader và plugin compatibility |
| Client compile được nhưng runtime lỗi | Dependency resolve khác compile/runtime | Đọc dependency tree và runtime artifact |

## 17. Theo dõi sau khi nâng

Đặt baseline trước rollout và so sánh theo cùng workload.

| Nhóm | Chỉ số |
|---|---|
| Connection | connection count, creation rate, close rate |
| Protocol | unsupported version, request error, reconnect |
| Producer | send rate, error rate, retry, batch size, compression |
| Consumer | lag, poll rate, processing duration, commit latency |
| Group | rebalance rate, assignment changes, coordinator error |
| Request | request latency p50/p95/p99, request size |
| Security | authentication success/failure, TLS handshake error |
| Runtime | CPU, heap, GC, thread, file descriptor |
| Business | event throughput, duplicate, missing event, processing SLO |

Tên metric chính xác tùy client release, exporter và framework. Hãy xác định JMX/Micrometer metric hiện có thay vì giả định mọi client version cung cấp cùng sensor.

### 17.1. So sánh baseline

So sánh ít nhất:
- Cùng topic và partition.
- Cùng payload distribution.
- Cùng compression.
- Cùng producer rate.
- Cùng consumer concurrency.
- Cùng security listener.
- Cùng downstream dependency.
- Cùng khoảng thời gian có traffic tương đương.

Nếu thay đổi đồng thời client version, partition count, broker config và schema, sẽ khó biết thay đổi nào gây regression.

### 17.2. Canary

Bắt đầu với một phần nhỏ traffic:
1. Nâng một instance producer hoặc consumer.
2. Giữ các instance khác ở version cũ.
3. Theo dõi API errors, request latency, retry và business outcome.
4. Kiểm tra duplicate/missing event.
5. Mở rộng tỷ lệ nếu đạt SLO.
6. Dừng rollout nếu xuất hiện regression.

Với consumer group, mixed-version members cần được test vì group protocol và assignor behavior có thể khác. Nếu không chứng minh được compatibility, triển khai theo nhóm riêng hoặc dừng/pause group theo cutover plan.

## 18. Rollback client

Rollback thường là deploy lại artifact/client version cũ, nhưng phải xem xét những thay đổi đã xảy ra trong thời gian client mới hoạt động.

### 18.1. Điều kiện rollback

- UnsupportedVersion hoặc protocol error tăng.
- Authentication/TLS không ổn định.
- Producer error/retry vượt ngưỡng.
- Consumer rebalance hoặc lag tăng bất thường.
- Duplicate/missing event vượt mức chấp nhận.
- Transaction hoặc offset behavior sai.
- Business SLO bị vi phạm.

### 18.2. Các bước rollback

1. Dừng rollout tiếp theo.
2. Ghi lại client version, config và thời điểm bắt đầu lỗi.
3. Giữ nguyên broker và cluster feature state.
4. Deploy lại artifact client cũ.
5. Xác nhận dependency runtime đúng version cũ.
6. Kiểm tra producer/consumer connection và group assignment.
7. Xác minh offset, duplicate và downstream state.
8. So sánh metrics với baseline.
9. Ghi incident và nguyên nhân.
10. Chỉ thử lại sau khi compatibility issue được xử lý.

Không tự động rollback mọi schema hoặc record đã ghi. Client mới có thể đã phát event schema mới hoặc dùng compression mới. Bảo đảm client cũ đọc được dữ liệu đã được ghi trong giai đoạn canary trước khi rollback.

### 18.3. Giữ thay đổi tách biệt

Trong client-only upgrade:
- Không đổi broker version.
- Không đổi metadata.version.
- Không thay inter.broker.protocol.version.
- Không đổi partition count.
- Không đổi retention hoặc RF.
- Không bật consumer group protocol mới cùng lúc.
- Không đổi schema contract nếu không nằm trong mục tiêu change.

Tách thay đổi giúp rollback rõ ràng và giảm số biến cần điều tra.

## 19. Quy trình nâng client độc lập mẫu

### Giai đoạn A — Inventory

- Liệt kê service và client implementation.
- Xác định version thực tế trong runtime.
- Xác định broker version và API range.
- Liệt kê security protocol và listener.
- Liệt kê producer, consumer, AdminClient, Streams và Connect usage.
- Ghi lại các tính năng đang bật.

### Giai đoạn B — Compatibility

- Đọc compatibility guidance của client/framework.
- Kiểm tra Java runtime và dependency graph.
- Tạo client/broker compatibility matrix.
- Kiểm tra API version range.
- Kiểm tra record format, compression và schema.
- Xác định feature mới cần broker support.

### Giai đoạn C — Test

- Chạy protocol handshake với broker hiện tại.
- Test producer send/retry/idempotence/transaction.
- Test consumer group/commit/rebalance.
- Test AdminClient API đang dùng.
- Test TLS/SASL và ACL.
- Test schema và downstream side effects.
- Đo baseline latency/throughput.

### Giai đoạn D — Canary rollout

- Build artifact với dependency được pin.
- Deploy một instance hoặc workload nhỏ.
- Quan sát connection và protocol errors.
- So sánh producer/consumer metrics.
- Xác minh business event.
- Mở rộng rollout theo từng đợt.

### Giai đoạn E — Hoàn tất

- Xác nhận toàn bộ instance đã chạy version mục tiêu.
- Xác nhận không còn client cũ ngoài kế hoạch.
- Lưu dependency tree và test evidence.
- Cập nhật inventory/compatibility matrix.
- Ghi rollback artifact và owner.
- Đóng change khi SLO ổn định qua thời gian quan sát đã định.

## 20. Checklist production

Trước khi nâng:

1. Xác định đúng Kafka client version thực tế trong runtime.
2. Xác định broker version và API range của từng broker.
3. Đọc compatibility guidance của Kafka client và framework.
4. Kiểm tra Spring Boot/Spring Kafka/Kafka Streams dependency alignment.
5. Kiểm tra Java runtime và TLS provider.
6. Phân biệt API version, record format, schema và cluster feature level.
7. Liệt kê API và feature ứng dụng đang dùng.
8. Xác định broker feature tối thiểu cho tính năng mới.
9. Có baseline producer/consumer/connection metrics.
10. Có artifact cũ để rollback.

Trong kiểm thử:

11. Dùng broker version giống production.
12. Dùng listener/security giống production.
13. Kiểm tra ApiVersions handshake.
14. Kiểm tra API range từ tất cả broker.
15. Phân biệt broker API range với negotiated request version.
16. Test producer send, retry, idempotence và transaction.
17. Test consumer group, rebalance và commit.
18. Test AdminClient API thực tế.
19. Test serializer, compression và schema.
20. Test Connect/Streams nếu ứng dụng sử dụng.
21. Test mixed-version members nếu rollout rolling.
22. Kiểm tra lỗi UnsupportedVersion và authentication.

Sau rollout:

23. Theo dõi request latency, retry và error rate.
24. Theo dõi consumer lag và rebalance.
25. Kiểm tra duplicate/missing event.
26. So sánh throughput và batch/compression behavior.
27. Xác minh business SLO.
28. Lưu dependency tree, version matrix và test evidence.
29. Giữ rollback artifact và runbook.
30. Chỉ kết thúc change sau khi canary và rollout ổn định.

## 21. Bài tập thực hành

### Bài 1: Kiểm kê API version broker

1. Kết nối lab tới Kafka broker hiện tại.
2. Chạy kafka-broker-api-versions.sh.
3. Lưu output theo từng broker.
4. Tìm Produce, Fetch, Metadata và FindCoordinator.
5. Ghi min/max version.
6. Giải thích vì sao output không cho biết client cụ thể đã chọn version nào.

### Bài 2: Kiểm thử client mới với broker cũ

1. Dựng broker lab ở phiên bản cũ cần hỗ trợ.
2. Build một client app bằng kafka-clients version mục tiêu.
3. Kết nối qua listener/security tương tự production.
4. Gửi và đọc record.
5. Kiểm tra AdminClient API.
6. Kiểm tra lỗi UnsupportedVersion nếu gọi feature không được hỗ trợ.
7. Ghi lại capability và limitation.

### Bài 3: So sánh producer behavior

1. Chạy cùng workload với client cũ.
2. Ghi throughput, latency, batch size và compression.
3. Nâng client version.
4. Giữ nguyên broker, topic và payload.
5. Chạy lại cùng workload.
6. So sánh retry, idempotence và partitioning.
7. Giải thích thay đổi do default hoặc implementation.

### Bài 4: Kiểm thử consumer group

1. Chạy consumer group với client cũ.
2. Ghi assignment và rebalance rate.
3. Nâng một member trong lab.
4. Quan sát mixed-version group behavior.
5. Restart một member.
6. Kiểm tra commit, duplicate và lag.
7. Thử group protocol/assignor mới riêng biệt nếu broker hỗ trợ.

### Bài 5: Canary và rollback

1. Deploy client mới cho một instance.
2. Theo dõi request error và business outcome.
3. Tạo tình huống lỗi trong môi trường test.
4. Dừng rollout.
5. Rollback artifact cũ.
6. Xác minh client cũ đọc được record do client mới đã ghi.
7. Viết báo cáo và điều kiện thử lại.

### Bài 6: Xây dựng compatibility matrix

1. Chọn hai client version và hai broker version trong phạm vi hỗ trợ.
2. Chạy các cặp client/broker cần thiết.
3. Kiểm tra security, producer, consumer và AdminClient.
4. Ghi API range và feature support.
5. Đánh dấu unsupported combinations.
6. Đề xuất thứ tự nâng client và broker cho lần release tiếp theo.

## 22. Câu hỏi tự kiểm tra

1. Vì sao Kafka client và broker không cần cùng version?
2. Kafka client version khác API version như thế nào?
3. ApiVersions request dùng để làm gì?
4. Client chọn API version chung theo nguyên tắc nào?
5. Vì sao negotiation cần xét từng API key?
6. Vì sao một client có thể negotiate khác nhau với từng broker?
7. kafka-broker-api-versions.sh chứng minh điều gì và không chứng minh điều gì?
8. API version khác record batch format như thế nào?
9. Vì sao protocol compatibility không bảo đảm schema compatibility?
10. Client cũ kết nối broker mới cần kiểm tra gì?
11. Client mới kết nối broker cũ có thể mất khả năng nào?
12. metadata.version trong KRaft khác API version ra sao?
13. inter.broker.protocol.version áp dụng cho giao tiếp nào?
14. Vì sao cần kiểm tra dependency tree runtime?
15. Spring Boot và Spring Kafka ảnh hưởng Kafka client version thế nào?
16. Vì sao không nâng Kafka Streams và client tùy ý độc lập?
17. Những producer semantics nào cần kiểm thử sau nâng?
18. Những consumer group behavior nào cần kiểm thử?
19. Vì sao TLS/SASL test phải dùng môi trường tương tự production?
20. Khi nào cần broker upgrade để dùng feature mới?
21. Vì sao mixed-version consumer group cần kiểm thử?
22. Những metric nào giúp phát hiện client regression?
23. Khi rollback client, vì sao cần kiểm tra record đã ghi bởi client mới?
24. Làm sao chứng minh protocol negotiation thực tế thay vì chỉ kiểm kê broker capability?

## Kết luận

Kafka client có thể được nâng cấp độc lập với broker nếu phiên bản mới và broker hiện tại có API version chung, đồng thời các tính năng ứng dụng sử dụng vẫn được hỗ trợ. ApiVersions cho client biết broker hỗ trợ những API version nào; client chọn version tương thích theo từng API và từng connection. Broker API inventory là cơ sở kiểm tra capability, nhưng không phải bằng chứng trực tiếp về version đã được chọn trong một request cụ thể.

Nâng client cần kiểm thử cả wire protocol và hành vi thực tế: producer retry/idempotence/transaction, consumer group/offset/rebalance, AdminClient, security, compression, schema, Streams và Connect. Phân biệt API version với record format, schema version, metadata.version và broker-to-broker protocol để không bật nhầm feature hoặc thay đổi sai lớp.

Rollout nên bắt đầu bằng inventory và compatibility matrix, tiếp theo là integration test với broker/security tương tự production, canary, theo dõi SLO và rollback artifact. Giữ thay đổi client tách khỏi broker upgrade hoặc feature activation giúp giảm phạm vi rủi ro và làm kết quả kiểm thử dễ đánh giá.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Kafka client | Thư viện/ứng dụng producer, consumer hoặc admin giao tiếp với broker. |
| Kafka broker | Server lưu trữ và phục vụ partition, request và metadata. |
| Kafka wire protocol | Giao thức request/response giữa client và broker. |
| ApiVersions | Kafka API dùng để trao đổi API version range được hỗ trợ. |
| API key | Định danh loại request như Produce, Fetch hoặc Metadata. |
| API version range | Khoảng version thấp nhất/cao nhất mà implementation hỗ trợ cho một API. |
| Negotiated version | API version được chọn để gửi request trên connection cụ thể. |
| Compatibility matrix | Bảng kiểm thử kết hợp client version, broker version và feature. |
| Record batch | Đơn vị record được encode và lưu trong Kafka log. |
| Compression codec | Thuật toán nén record batch. |
| Schema Registry | Dịch vụ quản lý schema và compatibility của event payload. |
| metadata.version | Cluster feature level quản lý metadata trong KRaft. |
| inter.broker.protocol.version | Cấu hình tương thích giao tiếp broker-to-broker ở các release có sử dụng. |
| UnsupportedVersionException | Lỗi khi request/API version hoặc tính năng không được phía broker hỗ trợ. |
| Canary rollout | Triển khai trước cho một phần nhỏ workload để quan sát rủi ro. |
| Dependency graph | Cây dependency thể hiện thư viện nào kéo version nào vào runtime. |
| Client churn | Việc tạo/hủy client hoặc connection quá thường xuyên. |
| Consumer rebalance | Quá trình phân phối lại partition giữa các consumer member. |
| Fallback | Cách client tiếp tục dùng API version hoặc behavior cũ khi feature mới không có. |
| Rollback artifact | Bản build/client dependency trước đó dùng để quay lại khi nâng cấp lỗi. |

