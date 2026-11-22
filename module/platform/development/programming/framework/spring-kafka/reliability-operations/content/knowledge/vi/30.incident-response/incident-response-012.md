# Rollback deployment

Rollback deployment là thao tác đưa một dịch vụ đang chạy về phiên bản ứng dụng hoặc cấu hình đã biết là ổn định sau khi một lần triển khai gây lỗi. Trong hệ thống Spring Kafka, rollback cần được xem là một phần của quy trình incident response vì một phiên bản mới có thể vừa chạy code, vừa tiêu thụ hoặc phát sự kiện, cập nhật database và tạo tác dụng phụ trên các hệ thống khác.

Khôi phục image cũ không tự động hoàn tác những việc phiên bản mới đã làm. Kafka record đã được publish vẫn còn trong topic; consumer offset đã commit vẫn giữ nguyên; dữ liệu database đã ghi và email hoặc yêu cầu thanh toán đã gửi vẫn tồn tại. Vì vậy, trước khi rollback phải xác định phiên bản cũ có thể đọc trạng thái hiện tại của hệ thống hay không, và những tác dụng phụ đã xảy ra cần được xử lý thế nào.

## 1. Phân biệt rollback ứng dụng, cấu hình và dữ liệu

Trong một lần triển khai, nhiều thành phần có thể thay đổi cùng lúc. Hãy xác định chính xác thành phần cần khôi phục:

| Thành phần | Rollback có nghĩa là gì | Điều không tự được hoàn tác |
|---|---|---|
| Application artifact | Đưa Deployment hoặc service về image/build đã biết là ổn định. | Record đã publish, offset đã commit và dữ liệu đã ghi. |
| Application configuration | Khôi phục ConfigMap, Secret reference, environment variable hoặc cấu hình runtime trước đó. | Thay đổi đã được cấu hình mới kích hoạt trong database hay Kafka. |
| Database schema | Chạy migration ngược nếu migration đó được thiết kế và kiểm chứng để đảo ngược. | Dữ liệu đã bị xóa, biến đổi hoặc ghi theo định dạng mới. |
| Kafka topic/configuration | Khôi phục cấu hình topic hoặc luồng routing nếu thay đổi đó có thể đảo ngược. | Record đã được ghi; partition đã tăng không thể giảm bằng thao tác thông thường. |
| Business data | Chạy quy trình sửa dữ liệu hoặc phát sự kiện bù trừ. | Tác dụng phụ bên ngoài như giao hàng, gửi email hoặc thanh toán đã hoàn tất. |

Không gọi việc deploy image cũ là “rollback toàn hệ thống” nếu database, Kafka và downstream đã nhận thay đổi từ phiên bản mới. Trong báo cáo incident, ghi rõ thành phần nào đã được khôi phục và phần nào cần reconciliation hoặc compensation.

## 2. Khi nào nên rollback?

Rollback phù hợp khi có đủ bằng chứng rằng phiên bản vừa triển khai là nguyên nhân chính, một phiên bản trước đó đã hoạt động ổn định, và phiên bản cũ tương thích với dữ liệu cùng schema hiện tại.

Các tín hiệu thường cần xem xét:

- Tỷ lệ lỗi listener tăng đột ngột sau deployment, chẳng hạn deserialization exception, lỗi xử lý nghiệp vụ hoặc lỗi ghi database.
- Producer không gửi được record, lỗi xác nhận publish tăng hoặc transaction Kafka liên tục abort.
- Consumer lag tăng nhanh, throughput giảm mạnh hoặc partition liên tục rebalance sau khi thay đổi concurrency hay cấu hình listener.
- Số record retry hoặc chuyển sang dead-letter topic (DLT) tăng bất thường.
- API downstream, database connection pool hoặc tài nguyên JVM bị quá tải sau khi triển khai.
- Kiểm thử smoke test hoặc canary phát hiện kết quả nghiệp vụ sai.

Không nên rollback chỉ vì có một cảnh báo đơn lẻ. So sánh thời điểm bắt đầu lỗi với thời điểm deploy, kiểm tra dependency và hạ tầng, xác định phạm vi ảnh hưởng và xem liệu lỗi có còn xuất hiện ở phiên bản cũ hay không.

### Rollback hay forward fix?

| Tình huống | Hướng xử lý thường phù hợp |
|---|---|
| Lỗi code mới, phiên bản trước tương thích với schema và dữ liệu hiện tại | Rollback về phiên bản trước, sau đó điều tra nguyên nhân. |
| Cấu hình mới gây lỗi và cấu hình cũ vẫn hợp lệ | Khôi phục cấu hình đã biết là ổn định. |
| Phiên bản mới đã ghi payload mà phiên bản cũ không thể deserialize | Cân nhắc forward fix hoặc chuyển đổi dữ liệu trước; rollback trực tiếp có thể làm consumer cũ thất bại liên tục. |
| Migration đã xóa hoặc đổi cấu trúc dữ liệu theo cách phiên bản cũ không hiểu | Ưu tiên forward fix hoặc migration phục hồi có kiểm soát. |
| Sự kiện sai đã được publish ra Kafka hoặc tác dụng phụ đã hoàn tất | Khôi phục ứng dụng nếu cần, đồng thời chạy quy trình bù trừ hoặc reconciliation riêng. |
| Sự cố nằm ở broker, network hoặc database độc lập với bản deploy | Xử lý dependency; rollback ứng dụng có thể không giải quyết nguyên nhân. |

Nếu chưa chứng minh được phiên bản cũ tương thích, hãy giữ hệ thống ở trạng thái được kiểm soát, hạn chế rollout hoặc tác vụ gây thêm dữ liệu lỗi, rồi chọn forward fix hay biện pháp containment. Không để việc rollback tạo ra vòng lặp lỗi mới.

## 3. Những điều phải kiểm tra trước khi rollback Spring Kafka

### Tương thích producer và consumer

Trong một hệ thống event-driven, producer và consumer có thể được deploy ở các thời điểm khác nhau. Phiên bản cũ phải đọc được những record mà phiên bản mới đã ghi. Kiểm tra cả hai chiều:

- Consumer cũ có đọc được payload do producer mới tạo ra không?
- Consumer mới hoặc producer mới có đọc/ghi tương thích với những record và schema cũ không?
- Enum, field bắt buộc, kiểu dữ liệu, header, Kafka key và serializer có thay đổi không?
- Schema Registry đang áp dụng compatibility policy nào, và schema mới có vượt qua policy đó không?
- Phiên bản cũ có hiểu được header hoặc metadata mà phiên bản mới thêm vào không?

Một thay đổi JSON có vẻ nhỏ vẫn có thể phá compatibility nếu đổi tên field, đổi kiểu, biến field tùy chọn thành bắt buộc hoặc phát ra enum value mà consumer cũ không nhận biết. Với Avro, Protobuf hoặc JSON Schema, kiểm tra quy tắc compatibility của định dạng và cấu hình registry đang dùng.

### Database migration và dữ liệu

Phiên bản cũ phải chạy được với schema database hiện tại. Mẫu expand-contract giúp giảm rủi ro:

1. **Expand:** thêm cột, bảng hoặc index theo cách phiên bản cũ vẫn hoạt động.
2. Triển khai code mới có thể đọc/ghi cấu trúc mới, đồng thời duy trì tương thích cần thiết.
3. Chuyển dữ liệu và xác nhận ứng dụng mới không còn phụ thuộc cấu trúc cũ.
4. **Contract:** chỉ xóa cột hoặc cấu trúc cũ trong một lần thay đổi riêng, sau khi không còn phiên bản cũ cần dùng đến.

Nếu deployment mới đã chạy migration destructive, ví dụ xóa cột hoặc đổi kiểu dữ liệu không tương thích, image cũ có thể khởi động thất bại hoặc ghi sai dữ liệu. Không chạy migration down một cách máy móc trên production. Kiểm tra backup, khả năng phục hồi, lượng dữ liệu đã ghi và tác động của migration trước khi quyết định.

### Consumer group, offset và topic

Rollback application không đưa consumer group về offset cũ. Committed offset vẫn nằm trong Kafka và consumer cũ tiếp tục từ vị trí group đã commit. Điều này thường là hành vi mong muốn vì tránh xử lý lại toàn bộ dữ liệu.

Không reset offset như một bước mặc định của rollback. Reset có thể khiến event được xử lý lại, tạo tác dụng phụ trùng lặp hoặc làm sai trạng thái nếu listener không idempotent. Chỉ replay/reset offset khi có kế hoạch riêng, phạm vi rõ ràng và cơ chế chống xử lý trùng.

Kiểm tra các thay đổi có liên quan đến:

- Topic mới, tên retry topic hoặc DLT được tạo bởi phiên bản mới.
- Số partition, replication factor, retention, cleanup policy và ACL.
- Kafka key hoặc chiến lược partitioning của producer.
- Consumer group ID, subscription pattern, concurrency và cách phân công partition.
- Offset đã commit, end offset, lag và record đang nằm trong retry topic hoặc DLT.

Các thay đổi topic thường tồn tại độc lập với vòng đời application. Ví dụ, tăng partition count không thể được đảo lại bằng cách giảm partition count theo thao tác thông thường. Phiên bản cũ phải hoạt động an toàn với trạng thái topic đang có.

### Transaction và producer identity

Nếu dùng Spring Kafka transactions hoặc exactly-once semantics cho luồng consume-process-produce, xác nhận cấu hình transaction còn phù hợp sau khi rollback. Đặc biệt, các instance chạy đồng thời phải có transaction ID prefix được cấu hình để tránh trùng định danh và producer fencing ngoài dự kiến. Khi blue-green hoặc rolling deployment làm hai revision cùng tồn tại, kiểm tra cách tạo transaction ID của từng revision.

Transaction Kafka không đảo ngược các transaction đã commit trước đó. Consumer dùng isolation level `read_committed` vẫn có thể đọc các record thuộc transaction đã commit của phiên bản mới. Nếu những record đó không tương thích với code cũ, cần xử lý payload hoặc forward fix.

## 4. Ghi lại trạng thái trước khi thao tác

Trước khi đổi phiên bản, lưu lại thông tin đủ để so sánh và tiếp tục điều tra:

| Nhóm | Thông tin nên ghi |
|---|---|
| Deployment | Tên service/Deployment, namespace, image digest hoặc build ID hiện tại, revision đang chạy và số replica. |
| Cấu hình | Config version, feature flag, secret/config reference và các giá trị Spring Kafka có liên quan. Không ghi secret value vào log incident. |
| Kafka | Cluster, topic, partition, consumer group, committed offset, end offset, lag và số record ở retry/DLT. |
| Database | Migration version, trạng thái backup, thời điểm ghi dữ liệu mới và các thay đổi schema liên quan. |
| Tác động | Request/event ID, correlation ID, khoảng thời gian lỗi, số giao dịch thành công/thất bại và downstream bị ảnh hưởng. |
| Quan sát | Dashboard, log, trace, alert và mốc thời gian bắt đầu triển khai/sự cố. |

Lưu image digest hoặc build ID chính xác thay vì chỉ ghi tag như `latest`. Tag có thể được trỏ sang artifact khác sau này; digest giúp xác định đúng image cần khôi phục.

## 5. Quy trình rollback deployment

### Bước 1: Tuyên bố incident và dừng rollout

Chỉ định người điều phối incident và người thực hiện rollback. Dừng pipeline hoặc rollout đang chạy để không có revision mới tiếp tục thay đổi trạng thái. Thông báo phạm vi ảnh hưởng trong kênh vận hành theo quy trình của tổ chức.

Xác định service nào là nguồn lỗi: producer, consumer, API đồng bộ hay một worker phụ trợ. Nếu nhiều service cùng được triển khai, rollback theo thứ tự dependency đã xác định, không rollback hàng loạt theo cảm tính.

### Bước 2: Chọn revision ổn định

Tra deployment history và xác nhận revision trước đó thực sự ổn định. Kiểm tra image digest, build ID, cấu hình và migration mà revision đó mong đợi. Nếu có nhiều revision, chọn bản đã được xác nhận bằng số liệu production hoặc canary.

Không chọn revision chỉ dựa trên số thứ tự gần nhất. Một revision trung gian có thể đã chứa cùng lỗi hoặc không tương thích với schema hiện tại.

### Bước 3: Kiểm tra điều kiện tương thích

Trước khi khôi phục, xác nhận consumer cũ đọc được record hiện tại, producer cũ không ghi dữ liệu mà downstream mới yêu cầu, và database schema không có thay đổi phá vỡ code cũ. Kiểm tra cả retry topic, DLT và các record đang chờ xử lý.

Nếu không đáp ứng được điều kiện, chọn phương án forward fix, sửa cấu hình hoặc chuyển đổi dữ liệu có kiểm soát trước khi đổi artifact.

### Bước 4: Thực hiện rollback qua đúng công cụ quản lý

Dùng cùng control plane đã quản lý deployment. Nếu hệ thống dùng GitOps, thay đổi desired state bằng cách revert commit cấu hình và để controller đồng bộ. Không vừa sửa trực tiếp cluster vừa để GitOps liên tục ghi đè trạng thái.

Với Kubernetes Deployment được quản lý trực tiếp, có thể xem history và trạng thái bằng:

~~~bash
kubectl rollout history deployment/orders-consumer -n production
kubectl rollout status deployment/orders-consumer -n production
~~~

Sau khi xác định revision cần khôi phục, ví dụ revision 12:

~~~bash
kubectl rollout undo deployment/orders-consumer -n production --to-revision=12
kubectl rollout status deployment/orders-consumer -n production
~~~

Đây là ví dụ cho Kubernetes Deployment; thay namespace, resource và revision theo môi trường thực tế. Nếu Deployment được quản lý bởi Helm hoặc GitOps, dùng công cụ đó làm nguồn thay đổi chính.

Với Helm release, có thể kiểm tra lịch sử và trạng thái:

~~~bash
helm history orders -n production
helm status orders -n production
~~~

Sau khi xác nhận revision chart cần khôi phục, thực hiện `helm rollback` theo revision đã chọn và theo dõi trạng thái release. Không chạy lệnh Helm rollback thủ công nếu quy trình GitOps của môi trường yêu cầu revert commit trong repository.

### Bước 5: Khôi phục cấu hình đi cùng artifact

Artifact cũ có thể yêu cầu cấu hình cũ, nhưng không được khôi phục mù quáng toàn bộ Secret hoặc ConfigMap. So sánh từng thay đổi, xác định cấu hình nào gây lỗi và kiểm tra cấu hình cũ còn hợp lệ với broker, database, schema registry và downstream hiện tại.

Các cấu hình Spring Kafka nên được kiểm tra gồm:

- Bootstrap servers, security protocol, SASL/SSL và truststore/keystore reference.
- Consumer group ID, topic subscription, concurrency, poll/batch behavior và acknowledgment mode.
- Deserializer, trusted packages, error handler, retry backoff, retry topic và DLT routing.
- Producer serializer, acks, retries, idempotence, transaction ID prefix và timeout.
- Timeout, connection pool, listener auto-startup và các feature flag liên quan.

Khôi phục cấu hình từng phần nếu chỉ một thay đổi gây lỗi. Tránh đưa credential cũ đã hết hạn hoặc cấu hình endpoint không còn tồn tại trở lại production.

### Bước 6: Chờ rollout hoàn tất và kiểm tra runtime

Xác nhận tất cả replica mục tiêu đã chạy đúng image digest và sẵn sàng nhận traffic. Kiểm tra pod restart, readiness/liveness, startup failure, log khởi tạo Kafka client và lỗi kết nối dependency.

Với consumer, xác nhận group membership ổn định, partition được assign, listener thực sự chạy và lag bắt đầu giảm theo tốc độ dự kiến. Với producer, xác nhận broker connection, metadata refresh và send acknowledgment hoạt động. Không coi việc Deployment báo Available là bằng chứng đầy đủ rằng luồng Kafka đã khỏe.

### Bước 7: Smoke test và theo dõi

Chạy smoke test an toàn với một event đại diện hoặc một giao dịch thử đã được phê duyệt. Xác nhận record được publish, consumer xử lý, dữ liệu đích đúng và không có tác dụng phụ lặp.

Theo dõi dashboard và log trong khoảng thời gian đủ dài để bao phủ chu kỳ xử lý bình thường. So sánh với baseline trước incident và xác nhận các chỉ số trở về vùng chấp nhận được trước khi đóng incident.

## 6. Lưu ý theo chiến lược triển khai

### Rolling deployment

Rolling deployment thay thế replica theo từng đợt. Trong thời gian chuyển đổi, pod cũ và mới có thể cùng tham gia một consumer group. Kafka sẽ phân phối partition giữa các consumer và có thể xảy ra rebalance.

Khi rollback, kiểm tra:

- Pod mới đã dừng nhận công việc và hoàn tất hoặc xử lý an toàn công việc đang chạy.
- Pod cũ khởi động với cùng consumer group và subscription dự kiến.
- Không có hai phiên bản cùng xử lý một tác vụ bên ngoài mà thiếu idempotency.
- Thời gian shutdown đủ để listener dừng có kiểm soát; không commit offset cho công việc chưa hoàn tất.

Nếu phiên bản mới và cũ cùng tham gia một group, Kafka xem chúng là các consumer trong cùng nhóm; record được chia theo partition. Đây không phải canary độc lập theo từng record và không bảo đảm mọi record của canary được xử lý bởi phiên bản mới.

### Blue-green deployment

Blue-green giữ hai môi trường để có thể chuyển traffic giữa phiên bản cũ và mới. Với HTTP, có thể chuyển traffic bằng service hoặc ingress. Với Kafka consumer, việc chuyển đổi cần kế hoạch riêng vì hai môi trường có thể cùng tham gia một group, dùng hai group khác nhau hoặc cùng ghi vào một database.

Nếu blue và green cùng dùng một consumer group, chúng chia partition và có thể gây rebalance khi chuyển phiên bản. Nếu dùng group ID riêng, mỗi môi trường sẽ đọc độc lập và có thể áp dụng cùng event hai lần vào đích dùng chung. Chỉ dùng group riêng khi đầu ra được cô lập hoặc có cơ chế deduplication/idempotency phù hợp.

Khi chuyển lại blue, xác nhận green đã dừng hoặc bị cô lập, group membership ổn định và blue có thể xử lý các record mà green đã publish hoặc tiêu thụ trong thời gian hoạt động.

### Canary deployment

Canary nên giới hạn phạm vi rủi ro bằng traffic, tenant, key hoặc một nhóm chức năng được chọn. Với Kafka, cách phân vùng và định tuyến phải được thiết kế rõ: producer có thể gửi một phần traffic qua phiên bản mới, còn consumer có thể dùng group riêng hoặc một chiến lược routing riêng.

Không dùng hai consumer group độc lập cùng ghi vào một đích chung mà bỏ qua deduplication. Cũng không giả định rằng chỉ tăng một replica canary trong cùng group sẽ khiến nó nhận một tỷ lệ record cố định; partition assignment quyết định việc phân phối.

Khi canary thất bại, dừng phát thêm traffic vào phiên bản mới, ghi nhận các event đã được phát hoặc xử lý bởi canary, rồi chuyển phần traffic còn lại về phiên bản ổn định. Các event đã phát vẫn cần được xử lý tương thích hoặc bù trừ.

## 7. Xử lý dữ liệu và sự kiện đã bị ảnh hưởng

Rollback code không xóa Kafka record đã publish và không hoàn tác database commit. Sau khi hệ thống trở lại ổn định, phân loại dữ liệu bị ảnh hưởng:

1. **Event hợp lệ và tương thích:** để consumer ổn định xử lý theo luồng bình thường.
2. **Event hợp lệ nhưng phiên bản cũ không tương thích:** cân nhắc forward fix consumer, chuyển đổi payload có audit hoặc route qua consumer tương thích.
3. **Event sai nhưng có thể sửa:** giữ bản gốc, tạo bản sửa có ghi nhận lý do, rồi phát lại theo quy trình replay có kiểm soát.
4. **Tác dụng phụ đã xảy ra:** dùng quy trình compensation hoặc reconciliation của nghiệp vụ, chẳng hạn phát event điều chỉnh, hoàn tiền hoặc cập nhật trạng thái giao hàng theo quy trình riêng.
5. **Event trùng do xử lý lại:** dựa vào event ID và idempotency key để ngăn áp dụng lặp; đối chiếu các trường hợp đã tạo tác dụng phụ trước khi kết luận.

Không xóa topic hoặc reset offset để “làm sạch” hậu quả deployment. Các thao tác này có thể phá hủy bằng chứng, làm mất dữ liệu cần xử lý hoặc tạo thêm tác dụng phụ. Nếu cần replay, hãy lập kế hoạch riêng với topic/partition/offset rõ ràng, event ID ổn định, consumer idempotent và điều kiện dừng.

Với transactional outbox, xác định trạng thái bản ghi outbox và record đã publish. Với consumer inbox, xác nhận dấu vết xử lý được lưu cùng transaction nghiệp vụ. Không xóa dữ liệu inbox chỉ để cho phép phiên bản cũ xử lý lại event.

## 8. Theo dõi sau rollback

Theo dõi cả trạng thái hạ tầng, luồng Kafka và kết quả nghiệp vụ:

| Nhóm chỉ số | Điều cần quan sát |
|---|---|
| Deployment | Image digest/revision, số replica ready, restart count, rollout status và readiness failures. |
| Consumer | Consumer group membership, rebalance rate, committed offset, end offset, lag theo partition và throughput. |
| Listener errors | Exception theo loại, deserialization failures, retry count, DLT publish rate và thời gian xử lý. |
| Producer | Send failures, request latency, retry, timeout, broker disconnect và transaction abort/fencing. |
| Database | Connection pool, transaction rollback, deadlock, lock wait, write latency và lỗi migration/schema. |
| Downstream | API error, timeout, rate limit, duplicate request và trạng thái tác dụng phụ. |
| Nghiệp vụ | Số giao dịch thành công, trạng thái aggregate, tổng tiền/số lượng, event bị bỏ sót hoặc áp dụng trùng. |

Các dấu hiệu cần điều tra ngay sau rollback gồm consumer lag tiếp tục tăng, DLT vẫn tăng, producer error không giảm, group rebalance liên tục hoặc lỗi nghiệp vụ vẫn xuất hiện ở phiên bản cũ. Khi đó, giả thuyết “bản deploy mới là nguyên nhân duy nhất” có thể sai hoặc còn một thay đổi phụ thuộc chưa được khôi phục.

Đặt tiêu chí đóng incident cụ thể, chẳng hạn error rate trở về baseline, lag ổn định hoặc giảm, không còn rollout ngoài dự kiến, các giao dịch quan trọng được đối chiếu và record lỗi có người phụ trách. Thời gian quan sát cần phù hợp với traffic và chu kỳ xử lý của hệ thống.

## 9. Kiểm thử khả năng rollback trước production

Rollback phải được diễn tập trước khi trở thành thao tác khẩn cấp. Trong staging hoặc môi trường tương đương, kiểm tra ít nhất các tình huống:

| Tình huống | Kết quả mong đợi |
|---|---|
| Phiên bản mới làm listener ném exception | Dừng rollout và đưa ứng dụng về revision ổn định; listener cũ hoạt động trở lại. |
| Phiên bản mới publish payload có field mới | Consumer cũ vẫn đọc được hoặc quy trình forward fix được kích hoạt theo thiết kế. |
| Migration expand đã chạy | Phiên bản cũ vẫn hoạt động với schema mở rộng. |
| Migration destructive đã chạy | Runbook chặn rollback trực tiếp và chỉ rõ phương án phục hồi/forward fix. |
| Consumer group rebalance trong rollout | Partition được assign lại, không mất record và không tạo tác dụng phụ trùng. |
| Pod dừng khi đang xử lý record | Record có thể được giao lại và idempotency bảo vệ thay đổi nghiệp vụ. |
| Producer transaction đang mở khi pod bị dừng | Transaction chưa commit được abort/fence theo cơ chế Kafka; record đã commit vẫn tồn tại. |
| DLT hoặc retry topic có record từ phiên bản mới | Phiên bản khôi phục có thể đọc hoặc record được giữ lại để xử lý riêng. |
| Blue-green cùng chạy | Group ID, routing và đích dữ liệu không gây xử lý trùng ngoài dự kiến. |
| Rollback xong nhưng downstream vẫn lỗi | Tiêu chí không đóng incident chỉ dựa trên trạng thái Deployment. |

Diễn tập cả đường đi đầy đủ: phát hiện, dừng rollout, lưu bằng chứng, kiểm tra compatibility, rollback, smoke test, theo dõi và đối chiếu dữ liệu. Ghi lại thời gian thực hiện và các bước thủ công dễ nhầm để cải thiện runbook.

## 10. Phòng ngừa rollback khó thực hiện

Một số thực hành giúp giảm thời gian phục hồi:

- Dùng image bất biến, lưu digest/build ID và giữ artifact của các revision đã chạy ổn định.
- Giữ deployment history, chart version, Git commit và cấu hình tương ứng có thể truy xuất.
- Triển khai thay đổi database theo expand-contract; tránh gộp migration phá vỡ tương thích vào cùng lần phát hành code.
- Thiết kế schema event theo hướng tương thích ngược và tiến; kiểm tra compatibility trong CI trước khi publish schema.
- Giữ event ID ổn định, dùng inbox/outbox hoặc idempotency key cho các tác dụng phụ quan trọng.
- Giữ consumer group ID ổn định qua các revision nếu đó là cùng một luồng xử lý; chỉ đổi group ID khi có kế hoạch backfill hoặc migration consumer rõ ràng.
- Tách feature flag khỏi artifact để có thể tắt hành vi mới nhanh chóng, nhưng kiểm soát quyền thay đổi và ghi lại lịch sử.
- Có health check phù hợp cho listener và dependency; phân biệt readiness với liveness để tránh restart loop khi dependency tạm thời lỗi.
- Theo dõi lag, retry, DLT, producer errors và các chỉ số nghiệp vụ ngay sau mỗi lần deploy.
- Diễn tập rollback định kỳ, bao gồm trường hợp dữ liệu mới đã được ghi và phiên bản cũ phải đọc chúng.

Feature flag có thể là biện pháp containment nhanh hơn rollback khi chỉ một tính năng mới gây lỗi. Tuy nhiên, tắt flag không khôi phục dữ liệu đã ghi và cũng không thay thế việc đánh giá compatibility.

## 11. Checklist thực hiện trong incident

### Trước rollback

- [ ] Đã xác nhận thời điểm lỗi có liên quan đến deployment.
- [ ] Đã dừng rollout và chọn người điều phối cùng người thao tác.
- [ ] Đã ghi image digest/build ID, revision, config version và mốc thời gian.
- [ ] Đã lưu trạng thái consumer group, offset, lag, retry topic và DLT.
- [ ] Đã kiểm tra producer/consumer schema compatibility với record hiện có.
- [ ] Đã xác nhận phiên bản cũ tương thích với database schema và dữ liệu hiện tại.
- [ ] Đã xác định tác dụng phụ đã xảy ra và kế hoạch compensation/reconciliation nếu cần.
- [ ] Đã chọn đúng control plane và revision để rollback.

### Trong rollback

- [ ] Chỉ thay đổi deployment/configuration qua control plane đã được chỉ định.
- [ ] Đã xác nhận replica mới dừng theo cách có kiểm soát.
- [ ] Đã xác nhận tất cả replica mục tiêu chạy đúng artifact và cấu hình.
- [ ] Đã kiểm tra kết nối Kafka, listener, producer và dependency.
- [ ] Đã xác nhận consumer group ổn định và offset không bị reset ngoài kế hoạch.
- [ ] Đã chạy smoke test an toàn.

### Sau rollback

- [ ] Error rate, lag, retry, DLT và producer failures trở về ngưỡng chấp nhận được.
- [ ] Đã xác nhận không có restart loop hoặc rebalance bất thường.
- [ ] Đã đối chiếu dữ liệu và các tác dụng phụ nghiệp vụ quan trọng.
- [ ] Đã phân công xử lý record lỗi hoặc dữ liệu cần compensation.
- [ ] Đã lưu timeline, revision đã khôi phục, quyết định và bằng chứng vận hành.
- [ ] Đã ghi nhận follow-up để sửa nguyên nhân gốc và cải thiện quy trình deploy.

## 12. Điều kiện kết thúc rollback

Rollback deployment chỉ hoàn tất khi revision ổn định đã chạy trên toàn bộ phạm vi dự kiến, producer và consumer hoạt động bình thường, các chỉ số kỹ thuật trở về ngưỡng chấp nhận được và các giao dịch nghiệp vụ quan trọng đã được đối chiếu. Những event hoặc tác dụng phụ phát sinh trong thời gian phiên bản lỗi hoạt động phải có kết luận riêng: đã xử lý, cần replay, cần compensation hoặc được chấp nhận theo quyết định có ghi nhận.

Một Deployment khỏe mạnh chỉ chứng minh ứng dụng đã khởi động. Nó không chứng minh dữ liệu Kafka và database đã đúng. Hãy đóng incident sau khi cả trạng thái runtime lẫn kết quả nghiệp vụ đều được xác nhận, đồng thời lưu lại bằng chứng để lần rollback tiếp theo có thể thực hiện nhanh và an toàn.
