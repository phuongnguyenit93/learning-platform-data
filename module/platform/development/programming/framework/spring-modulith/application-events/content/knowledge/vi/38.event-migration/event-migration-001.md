# Di trú schema

Application event là hợp đồng dữ liệu giữa module phát và các listener hoặc hệ thống nhận. Theo thời gian, nghiệp vụ thay đổi: thêm thuộc tính, đổi kiểu dữ liệu, tách trường, thay enum hoặc đổi cách biểu diễn ngày giờ. Nếu producer triển khai schema mới trước khi consumer có thể đọc, luồng event có thể lỗi deserialize hoặc hiểu sai ý nghĩa dữ liệu. **Di trú schema** là quá trình thay đổi hợp đồng event theo từng bước để producer, consumer và dữ liệu lịch sử có thể cùng hoạt động trong giai đoạn chuyển tiếp.

Di trú an toàn cần quản lý cả schema của event mới lẫn những event cũ còn nằm trong publication store, Kafka topic hoặc archive. Cần biết consumer nào đang đọc, dữ liệu nào sẽ được replay, thay đổi có tương thích không và có thể rollback tới phiên bản nào. Việc đổi class Java rồi triển khai đồng loạt không đủ để bảo đảm các hệ thống phân tán cùng chuyển đổi đúng lúc.

## 1. Vì sao schema event phải tiến hóa có kiểm soát?

Producer và consumer thường được triển khai độc lập. Producer có thể phát event theo schema mới trong khi một consumer vẫn chạy phiên bản cũ. Ngược lại, consumer mới có thể phải đọc lại record cũ được tạo từ nhiều tháng trước.

Một thay đổi schema có thể ảnh hưởng tới:

- Deserialization: consumer không thể chuyển byte thành object.
- Validation: payload thiếu trường bắt buộc hoặc có giá trị ngoài miền cho phép.
- Mapping: cùng một trường nhưng được diễn giải theo đơn vị hoặc ý nghĩa khác.
- Ordering và replay: consumer mới phải đọc cả event lịch sử.
- Downstream contract: một hệ thống khác dùng trường bị đổi hoặc bị xóa.
- Data retention: event cũ còn tồn tại lâu hơn vòng đời một phiên bản ứng dụng.

Ví dụ, event v1 chứa trường amount là số nguyên theo đơn vị nhỏ nhất của tiền tệ. Phiên bản mới muốn dùng decimal amount và currency. Nếu chỉ đổi kiểu amount mà không có quy tắc chuyển đổi, consumer cũ có thể đọc sai giá trị hoặc thất bại.

Di trú schema phải giữ nguyên ý nghĩa nghiệp vụ. Tương thích cú pháp không đồng nghĩa tương thích semantics: trường vẫn deserialize được nhưng đổi từ milliseconds sang seconds cũng có thể gây lỗi nghiêm trọng.

## 2. Phân biệt event schema, event contract và schema registry

Ba khái niệm liên quan nhưng khác nhau:

| Khái niệm | Vai trò |
|---|---|
| Event schema | Cấu trúc kỹ thuật của payload: tên trường, kiểu, required/optional và quy tắc dữ liệu |
| Event contract | Ý nghĩa nghiệp vụ, điều kiện phát, semantics, owner, ordering và cách consumer sử dụng event |
| Schema Registry | Dịch vụ quản lý schema version, identifier và quy tắc compatibility cho format được hỗ trợ |

Schema Registry không tự định nghĩa ý nghĩa nghiệp vụ. Hai schema có thể tương thích về cấu trúc nhưng thay đổi ý nghĩa của trường. Ngược lại, một thay đổi contract có thể cần migration dù cấu trúc JSON không đổi.

Spring Modulith Event Publication Registry cũng là một thành phần khác. Nó theo dõi publication của application event tới listener và trạng thái hoàn tất/incomplete. Nó không phải Schema Registry và không quản lý compatibility giữa các phiên bản payload.

Với event nội bộ chỉ được dùng trong một ứng dụng, schema có thể được quản lý cùng source code và test contract. Khi externalize event qua Kafka hoặc chia sẻ giữa nhiều ứng dụng, cần có quy trình công bố schema và kiểm soát consumer compatibility rõ ràng.

## 3. Xác định compatibility trước khi đổi schema

Compatibility mô tả khả năng writer và reader ở các phiên bản khác nhau trao đổi dữ liệu. Các tên gọi phổ biến trong schema registry gồm:

| Chế độ | Câu hỏi cần trả lời |
|---|---|
| Backward | Reader mới có đọc được dữ liệu được ghi bằng schema cũ không? |
| Forward | Reader cũ có đọc được dữ liệu được ghi bằng schema mới không? |
| Full | Cả reader mới với dữ liệu cũ và reader cũ với dữ liệu mới có hoạt động không? |
| Transitive | Quy tắc compatibility được kiểm tra với phiên bản liền trước hay với toàn bộ lịch sử schema? |

Cách kiểm tra cụ thể phụ thuộc format và Schema Registry. Avro, Protobuf và JSON Schema có quy tắc compatibility riêng; không suy ra rằng thêm một trường hay đổi tên trường có cùng hành vi ở cả ba format.

Khi producer và consumer được triển khai độc lập, cần kiểm tra hai hướng:

- Consumer mới phải đọc được event cũ còn tồn tại.
- Consumer cũ có thể gặp event mới trong giai đoạn rollout hay không.

Nếu cần rollout consumer trước producer, thường ưu tiên thay đổi backward-compatible. Nếu cần producer mới chạy trong khi consumer cũ vẫn tồn tại, cần bảo đảm forward compatibility hoặc triển khai chiến lược dual-write/dual-read.

Compatibility kỹ thuật không thay thế contract test. Test cần xác minh cả giá trị mặc định, đơn vị, nullability và ý nghĩa nghiệp vụ.

## 4. Phân loại thay đổi schema

Trước khi chọn cách di trú, phân loại thay đổi:

| Thay đổi | Rủi ro | Cách tiếp cận thường dùng |
|---|---|---|
| Thêm trường optional | Thấp nếu consumer cũ bỏ qua trường không biết | Thêm trường với default/optional semantics rõ |
| Thêm trường required | Cao với dữ liệu cũ và producer cũ | Thêm optional trước, backfill/dual-write rồi mới bắt buộc |
| Xóa trường | Cao nếu consumer cũ còn sử dụng | Ngừng đọc trước, ngừng ghi sau, xóa ở phiên bản sau |
| Đổi tên trường | Thường không tương thích | Thêm trường mới, dual-read/dual-write trong giai đoạn chuyển tiếp |
| Đổi kiểu dữ liệu | Thường không tương thích | Thêm trường mới hoặc version contract |
| Thêm enum value | Có thể làm consumer cũ thất bại | Consumer cần xử lý unknown value hoặc dùng version mới |
| Đổi đơn vị/ý nghĩa | Rất cao dù kiểu dữ liệu không đổi | Trường mới với tên/contract rõ và migration có kiểm soát |
| Đổi cấu trúc lồng nhau | Tùy format và reader | Compatibility test, upcaster hoặc version mới |

Không coi việc đổi tên trường là thao tác refactor nội bộ nếu payload đã được lưu hoặc consumer ngoài ứng dụng đã phụ thuộc. Một event đã phát là dữ liệu lịch sử; thay đổi class Java không thay đổi các record cũ trong broker hoặc archive.

## 5. Dùng chiến lược expand-migrate-contract

Một cách triển khai an toàn là chia migration thành ba giai đoạn:

1. **Expand:** mở rộng schema để hệ thống cũ và mới cùng tồn tại.
2. **Migrate:** chuyển producer, consumer và dữ liệu theo từng bước.
3. **Contract:** loại bỏ trường hoặc đường tương thích cũ sau khi không còn consumer phụ thuộc.

Ví dụ đổi trường customerName thành customerDisplayName:

~~~text
Giai đoạn 1 — Expand
Producer ghi cả customerName và customerDisplayName
Consumer mới ưu tiên customerDisplayName, fallback customerName

Giai đoạn 2 — Migrate
Triển khai consumer mới cho tất cả nhóm nhận
Theo dõi consumer version và dữ liệu mới

Giai đoạn 3 — Contract
Producer ngừng ghi customerName
Consumer ngừng fallback
Schema version sau mới loại bỏ customerName
~~~

Trong giai đoạn chuyển tiếp, cần xác định trường nào là nguồn chuẩn nếu cả hai trường cùng xuất hiện nhưng khác giá trị. Không để producer và consumer tự chọn quy tắc khác nhau.

Không xóa trường cũ ngay khi producer đã ngừng ghi. Consumer cũ có thể vẫn đang đọc dữ liệu được lưu trước đó. Chỉ contract sau khi xác minh mọi consumer đã chuyển và thời gian lưu giữ/replay của event cũ đã được tính đến.

## 6. Ví dụ thêm trường optional

Giả sử v1 có payload:

~~~json
{
  "eventId": "d1a7c3d0-0000-4000-8000-000000000001",
  "orderId": "a3a0a1d0-0000-4000-8000-000000000001",
  "status": "PAID"
}
~~~

Phiên bản mới thêm currency:

~~~json
{
  "eventId": "d1a7c3d0-0000-4000-8000-000000000001",
  "orderId": "a3a0a1d0-0000-4000-8000-000000000001",
  "status": "PAID",
  "currency": "VND"
}
~~~

Consumer mới phải có cách xử lý event cũ không có currency. Có thể dùng default chỉ khi default đó đúng với semantics dữ liệu lịch sử. Nếu không thể suy ra currency an toàn, trường không nên được giả định là VND; cần giữ trạng thái unknown hoặc lấy từ nguồn có thẩm quyền.

Với JSON, consumer thường bỏ qua trường không biết nếu deserializer được cấu hình phù hợp, nhưng producer thêm trường không bảo đảm mọi reader đều bỏ qua. Cần test serializer/deserializer và validation thực tế. Với Avro, default của field mới có vai trò trong schema resolution và cần tuân thủ quy tắc format.

## 7. Đổi tên hoặc đổi kiểu trường bằng dual-read/dual-write

Đổi tên trường thường nên được thực hiện như thêm một trường mới. Ví dụ đổi totalAmount từ integer minor units sang decimal:

~~~json
{
  "schemaVersion": 2,
  "totalAmountMinor": 125000,
  "totalAmount": "1250.00",
  "currency": "VND"
}
~~~

Trong giai đoạn chuyển tiếp:

- Producer ghi trường mới và có thể tiếp tục ghi trường cũ.
- Consumer mới ưu tiên trường mới; nếu thiếu thì chuyển đổi từ trường cũ theo quy tắc đã công bố.
- Consumer cũ vẫn đọc trường cũ.
- Metric ghi nhận số event còn cần fallback.
- Sau khi mọi consumer đã nâng cấp và dữ liệu cũ hết thời hạn cần đọc, producer ngừng ghi trường cũ.
- Một schema version tiếp theo mới loại bỏ trường cũ.

Với tiền tệ, decimal phải có quy tắc scale và rounding rõ. Không chuyển integer minor units sang decimal bằng cách đoán số chữ số thập phân từ currency nếu contract chưa định nghĩa. Cũng không dùng floating-point để biểu diễn số tiền.

Dual-write có thể làm tăng kích thước payload và tạo hai nguồn dữ liệu cạnh tranh. Cần quy định trường nào authoritative trong giai đoạn migration và kiểm thử hai trường luôn biểu diễn cùng một giá trị.

## 8. Quản lý enum và giá trị chưa biết

Enum thường gây lỗi khi producer thêm giá trị mới mà consumer cũ không nhận diện. Ví dụ consumer chỉ biết CREATED, PAID và CANCELLED nhưng producer phát thêm REFUNDED.

Consumer có thể:

- Dùng kiểu dữ liệu cho phép unknown value và xử lý fallback.
- Ánh xạ giá trị không biết sang trạng thái UNKNOWN nếu nghiệp vụ cho phép.
- Quarantine event nếu giá trị mới ảnh hưởng đến quyết định quan trọng.
- Chỉ phát giá trị mới sau khi consumer đã được triển khai tương thích.

Không ánh xạ mọi enum không biết sang một trạng thái hợp lệ như CANCELLED hoặc PAID; điều đó làm sai nghiệp vụ. Nếu trạng thái mới có semantics quan trọng, consumer cũ cần dừng hoặc quarantine thay vì tiếp tục với giả định sai.

Contract nên quy định rõ hành vi của consumer khi gặp enum value chưa hỗ trợ và có test cho giá trị unknown.

## 9. Version hóa event contract

Có thể version hóa schema theo một trong các cách:

- Trường schemaVersion trong envelope.
- Version trong event type hoặc logical target.
- Version trong topic name.
- Schema identifier được lưu trong message header hoặc Schema Registry.

Ví dụ envelope:

~~~json
{
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "eventId": "d1a7c3d0-0000-4000-8000-000000000001",
  "occurredAt": "2026-11-25T10:15:30Z",
  "payload": {
    "orderId": "a3a0a1d0-0000-4000-8000-000000000001",
    "totalAmount": "1250.00",
    "currency": "VND"
  }
}
~~~

Version trong payload hữu ích khi cùng topic chứa nhiều schema hoặc consumer cần chọn mapper. Schema Registry ID có thể xác định chính xác schema dùng để ghi record. Hai cơ chế có thể cùng tồn tại nhưng không nên coi chúng là một.

Không tăng version cho mọi thay đổi nội bộ không ảnh hưởng contract. Ngược lại, thay đổi semantics hoặc kiểu dữ liệu có ảnh hưởng consumer phải được ghi nhận rõ. Version phải có chính sách hỗ trợ và thời hạn ngừng phiên bản cũ.

## 10. Upcasting event lịch sử

Khi consumer mới đọc event cũ, có thể cần chuyển payload cũ sang model nội bộ mới. Quá trình chuyển đổi này thường gọi là upcasting.

Ví dụ v1 dùng amountMinor và v2 dùng amount decimal:

~~~java
OrderPaidV2 upcast(OrderPaidV1 oldEvent) {
    BigDecimal amount = new BigDecimal(oldEvent.amountMinor())
        .movePointLeft(2);

    return new OrderPaidV2(
        oldEvent.eventId(),
        oldEvent.orderId(),
        amount,
        oldEvent.currency()
    );
}
~~~

Ví dụ chỉ đúng nếu contract v1 quy định amountMinor có hai chữ số thập phân. Nếu currency có scale khác hoặc dữ liệu cũ không lưu currency, phép chuyển đổi cần dùng metadata hoặc nguồn có thẩm quyền. Không áp dụng một phép chia cố định khi semantics lịch sử không bảo đảm.

Upcaster nên:

- Có tính xác định: cùng payload cũ luôn tạo cùng model mới.
- Không gọi API ngoài hoặc phụ thuộc trạng thái thay đổi.
- Có unit test cho từng schema version còn được hỗ trợ.
- Giữ nguyên event ID, occurredAt và causation metadata.
- Ghi rõ dữ liệu nào được suy ra và dữ liệu nào không thể khôi phục.

Không sửa payload lịch sử tại chỗ trong Kafka hoặc archive chỉ để phù hợp schema mới. Consumer có thể upcast khi đọc hoặc chạy migration sang kho dữ liệu mới có audit, tùy kiến trúc.

## 11. Di trú topic khi contract không tương thích

Nếu thay đổi không thể tương thích trong cùng topic, có thể tạo topic version mới, ví dụ:

~~~text
orders.order-paid.v1
orders.order-paid.v2
~~~

Một kế hoạch chuyển đổi có thể:

1. Triển khai consumer v2 và xác minh có thể đọc topic v2.
2. Triển khai producer phát v2; nếu cần, tiếp tục phát v1 trong giai đoạn chuyển tiếp.
3. So sánh số record, event ID và kết quả xử lý giữa hai luồng.
4. Chuyển consumer downstream sang v2.
5. Theo dõi consumer lag và lỗi của v1/v2.
6. Dừng phát v1 sau khi tất cả consumer đã chuyển.
7. Giữ topic v1 đủ lâu cho replay và audit theo retention policy.

Dual-publish có thể tạo hai record đại diện cùng một event. Consumer không được xử lý cả hai như hai sự kiện nghiệp vụ độc lập. Giữ cùng event ID hoặc một migration identity ổn định để downstream deduplicate; mỗi consumer cần quy tắc chọn topic authoritative.

Không đổi nghĩa của một topic đang được nhiều consumer sử dụng mà không có rollout plan. Tên topic version mới giúp cô lập contract nhưng cũng tạo thêm chi phí vận hành, ACL, retention, dashboard và quy trình decommission.

## 12. Triển khai consumer trước hay producer trước?

Thứ tự rollout phụ thuộc loại thay đổi:

| Thay đổi | Thứ tự thường phù hợp |
|---|---|
| Thêm trường optional, consumer mới hiểu trường | Consumer tolerant trước, producer phát trường sau |
| Consumer bắt đầu fallback trường mới/cũ | Consumer dual-read trước, producer dual-write sau |
| Ngừng trường cũ | Xác minh consumer không còn đọc trường cũ, rồi producer ngừng ghi, cuối cùng mới xóa schema |
| Thay đổi không tương thích | Tạo contract/topic version mới, triển khai consumer mới trước khi chuyển producer |
| Thêm enum value | Consumer hỗ trợ unknown/new value trước, producer phát giá trị mới sau |

Trước khi rollout, liệt kê mọi consumer: listener nội bộ, externalized consumer, data pipeline, analytics, replay job và hệ thống đối tác. Một consumer không hoạt động thường xuyên vẫn có thể đọc lại dữ liệu cũ khi được khởi động lại.

Không dựa vào việc tất cả service đã deploy để kết luận migration hoàn tất. Cần quan sát phiên bản consumer thực tế, fallback rate, schema ID và backlog của topic.

## 13. Liên hệ với Spring Modulith application events

Trong Spring Modulith, application event có thể được dùng giữa các module nội bộ và có thể được externalize ra hệ thống ngoài. Ví dụ:

~~~java
@Externalized("orders.order-paid.v1")
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    long schemaVersion
) {}
~~~

Logical target trong annotation định danh đích externalization theo integration đang dùng. Nó không tự tạo Schema Registry subject, Kafka topic hoặc serializer. Mapping target tới topic vật lý và format payload cần được cấu hình ở integration/adapter.

Khi thay schema event:

- Xác định listener nội bộ nào dùng class event hiện tại.
- Xác định externalized consumer nào nhận payload.
- Kiểm tra publication còn incomplete và có thể được resubmit sau rollout.
- Giữ compatibility của listener trong thời gian event cũ còn được giao.
- Nếu thay class Java, có thể cần adapter hoặc mapper để giữ contract external ổn định.
- Kiểm thử publication lifecycle riêng với schema compatibility và consumer behavior.

Event Publication Registry theo dõi việc giao event tới listener, không tự chuyển đổi schema. Schema Registry (nếu dùng) quản lý schema payload, không thay thế publication tracking.

## 14. Quản lý dữ liệu lịch sử và replay

Event cũ có thể còn tồn tại ở nhiều nơi: Kafka topic, event store, archive, database audit hoặc publication store. Trước khi bỏ hỗ trợ schema cũ, xác định thời gian dữ liệu còn có thể được replay.

Cần có:

- Danh sách schema version còn được hỗ trợ.
- Upcaster/reader cho từng version cần replay.
- Retention và archive policy.
- Consumer group riêng cho replay nếu đọc Kafka.
- Cơ chế deduplication giữ event ID ổn định.
- Checkpoint và audit cho quá trình migration.
- Kế hoạch xử lý payload không thể chuyển đổi.

Nếu retention của Kafka ngắn hơn thời gian replay nghiệp vụ, cần archive hoặc event store riêng. Không giả định Event Publication Registry giữ toàn bộ event lịch sử đã hoàn tất.

Replay có thể chạy trên dữ liệu lớn và tạo tải cao. Dùng batch, checkpoint, giới hạn tốc độ và projection generation riêng nếu replay phục vụ rebuild read model. Không thay offset của consumer production đang hoạt động để chạy migration nếu điều đó có thể làm mất hoặc lặp công việc của group hiện tại.

## 15. Rollback và tương thích ngược trong thời gian chuyển đổi

Rollback schema khác rollback một bản deploy thông thường. Sau khi producer đã phát payload mới, rollback binary producer không xóa được record mới đã nằm trong broker.

Trước khi triển khai, xác định:

- Consumer cũ có đọc được payload mới không?
- Producer cũ có đọc được dữ liệu mới từ database hoặc nguồn event không?
- Topic v1 còn nhận record trong giai đoạn rollback không?
- Có thể dừng phát schema mới mà không mất event không?
- Nếu dual-publish, làm sao tránh consumer xử lý trùng?
- Khi rollback consumer, nó có đọc được record đã phát trong thời gian chạy version mới không?

Một migration tốt duy trì khoảng tương thích đủ dài để rollback. Nếu không thể giữ tương thích, cần một kế hoạch forward-fix hoặc chuyển đổi dữ liệu có kiểm soát thay vì giả định redeploy version cũ sẽ khôi phục trạng thái trước đó.

## 16. Kiểm thử schema migration

Một bộ test nên xác minh cả schema mới và dữ liệu cũ:

1. Deserialize fixture của mọi schema version còn hỗ trợ.
2. Serialize event mới và kiểm tra schema ID/version cùng payload.
3. Kiểm tra backward/forward/full compatibility theo policy của registry.
4. Kiểm tra trường optional thiếu, null và default.
5. Kiểm tra enum value không biết.
6. Kiểm tra upcaster cho event lịch sử và tính xác định của kết quả.
7. Kiểm tra producer dual-write không tạo hai giá trị mâu thuẫn.
8. Kiểm tra consumer dual-read ưu tiên trường mới và fallback đúng.
9. Kiểm tra topic v1/v2 và deduplication khi dual-publish.
10. Replay dữ liệu cũ bằng consumer mới và xác minh kết quả nghiệp vụ.
11. Mô phỏng consumer cũ đọc payload mới trong giai đoạn rollout nếu compatibility yêu cầu.
12. Kiểm tra rollback và event đã phát trước thời điểm rollback.

Giữ fixture payload thực tế cho từng version trong repository test hoặc contract test suite. Không chỉ tạo fixture từ class hiện tại vì cách đó không đại diện schema cũ. Với Schema Registry, kiểm tra cả đăng ký schema và compatibility mode trong môi trường test cô lập.

## 17. Quan sát tiến trình migration

Migration cần metric và log để biết consumer nào đã chuyển và dữ liệu nào còn dùng schema cũ:

| Chỉ số | Mục đích |
|---|---|
| Event count by schema version | Biết producer còn phát version cũ hay không |
| Consumer version | Theo dõi phiên bản consumer đang chạy |
| Deserialization failure | Phát hiện schema không tương thích |
| Upcast count | Đo lượng event lịch sử cần chuyển đổi |
| Legacy field fallback count | Biết consumer còn phụ thuộc trường cũ |
| Topic v1/v2 throughput | Theo dõi luồng dual-publish |
| Consumer lag by topic/group | Xác định consumer đã bắt kịp chưa |
| Quarantine count | Phát hiện event không thể chuyển đổi |
| Replay progress | Theo dõi checkpoint và số event đã xử lý |

Log nên có event ID, schema version, event type, topic, consumer group, migration run ID và kết quả upcast khi cần. Không dùng event ID hoặc order ID làm metric tag vì cardinality cao.

Chỉ contract schema cũ khi fallback count bằng 0 trong khoảng thời gian đủ dài, consumer cũ đã được loại bỏ và replay window không còn yêu cầu đọc schema đó. Một lần quan sát không thấy event cũ không đủ chứng minh có thể xóa hỗ trợ.

## 18. Quy trình di trú schema

Một quy trình có thể áp dụng:

1. **Inventory:** liệt kê producer, consumer, topic, schema version và dữ liệu lịch sử.
2. **Classify:** phân loại thay đổi tương thích hay phá vỡ contract.
3. **Design:** xác định default, mapping, version, upcaster và rollout order.
4. **Validate:** kiểm tra schema compatibility và contract test.
5. **Expand:** triển khai consumer tolerant và hỗ trợ schema cũ/mới.
6. **Migrate:** cập nhật producer, dual-write hoặc dual-publish nếu cần.
7. **Observe:** theo dõi fallback, error, lag, schema version và replay.
8. **Contract:** ngừng trường/topic cũ sau khi đủ bằng chứng.
9. **Retain:** giữ fixture/upcaster/archive theo thời hạn hỗ trợ đã công bố.

Mỗi bước cần có owner và điều kiện hoàn tất. Không chuyển sang contract chỉ vì code mới đã được merge hoặc deploy.

## 19. Checklist trước khi phát schema mới

Trước khi đưa schema mới vào production, xác nhận:

- Event contract có owner và tài liệu semantics rõ.
- Đã liệt kê mọi consumer nội bộ và bên ngoài.
- Đã phân loại thay đổi và xác định compatibility direction.
- Default, nullability, enum, decimal, timestamp và unit đã rõ.
- Consumer mới đọc được event cũ còn trong retention.
- Consumer cũ xử lý được event mới hoặc rollout đã loại bỏ chúng trước đó.
- Upcaster có test và không phụ thuộc dữ liệu thay đổi.
- Dual-read/dual-write có quy tắc authoritative và deduplication.
- Topic versioning, Schema Registry và ACL đã được chuẩn bị nếu cần.
- Publication registry và retry vẫn hoạt động trong giai đoạn chuyển đổi.
- Replay, rollback, archive và retention có kế hoạch.
- Metrics/cảnh báo xác định được thời điểm có thể contract schema cũ.

Di trú schema là một quá trình chuyển đổi hợp đồng qua nhiều phiên bản producer, consumer và dữ liệu lịch sử. Khi phân loại compatibility, triển khai expand-migrate-contract, giữ reader cho event cũ, kiểm thử upcaster và quan sát consumer thực tế, các module Spring Modulith có thể tiến hóa event contract mà không làm gián đoạn giao tiếp giữa các module và hệ thống tích hợp.

