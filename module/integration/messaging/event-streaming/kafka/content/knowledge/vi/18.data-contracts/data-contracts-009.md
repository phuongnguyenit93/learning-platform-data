# Phân biệt tương thích cấu trúc với thay đổi ý nghĩa nghiệp vụ

Một schema có thể vẫn hợp lệ sau khi thay đổi mà ứng dụng tiêu thụ dữ liệu lại hiểu sai nghiệp vụ. Ngược lại, một thay đổi chỉ đổi tên field nhưng giữ nguyên ý nghĩa có thể làm consumer cũ không giải mã được payload. Vì vậy, khi quản lý data contract cho Kafka, cần kiểm tra hai lớp riêng biệt: **tương thích cấu trúc** (structural compatibility) và **tương thích ý nghĩa nghiệp vụ** (semantic compatibility).

Schema Registry và các quy tắc schema evolution giúp kiểm tra hình dạng dữ liệu giữa các phiên bản. Chúng không tự hiểu rằng amount đã đổi từ đồng sang xu, PAID đã đổi nghĩa từ “đã xác nhận thanh toán” sang “đã thu tiền”, hay eventTime đã đổi từ thời điểm phát sinh sang thời điểm xử lý. Những điều đó cần được mô tả, review và kiểm thử ở cấp hợp đồng nghiệp vụ.

## 1. Hai lớp tương thích giải quyết hai câu hỏi khác nhau

**Tương thích cấu trúc** trả lời: consumer dùng schema phiên bản này có thể deserialize dữ liệu được ghi bằng schema phiên bản kia không? Các yếu tố thường được kiểm tra gồm tên field, kiểu dữ liệu, field bắt buộc/tùy chọn, default, enum symbol, union, field number của Protobuf và các quy tắc riêng của format.

**Tương thích ý nghĩa nghiệp vụ** trả lời: sau khi giải mã thành công, consumer có còn hiểu đúng giá trị, đơn vị, trạng thái, thời điểm, định danh và quy tắc xử lý hay không? Lớp này gồm ý nghĩa field, invariant, miền giá trị, state transition, ordering, null semantics, key semantics và các cam kết nghiệp vụ khác.

| Lớp | Câu hỏi | Ví dụ kiểm tra |
|---|---|---|
| Structural | Payload có đọc được theo schema khác phiên bản không? | Field amount vẫn là long; field mới có default; enum symbol có được hỗ trợ |
| Semantic | Giá trị sau deserialize còn mang cùng ý nghĩa không? | amount vẫn tính bằng minor unit; PAID vẫn có cùng định nghĩa; timestamp vẫn là thời điểm tạo event |

Một lần kiểm tra Schema Registry thành công chỉ là bằng chứng về lớp cấu trúc theo policy và format đang dùng. Nó không chứng minh consumer sẽ cho ra cùng kết quả nghiệp vụ.

## 2. Ma trận bốn trường hợp

Hai lớp tương thích độc lập với nhau. Có bốn trường hợp cần nhận diện:

| Cấu trúc | Ý nghĩa nghiệp vụ | Ví dụ | Kết quả |
|---|---|---|---|
| Tương thích | Tương thích | Thêm field tùy chọn campaignId; field cũ giữ nguyên ý nghĩa | Thường có thể rollout an toàn nếu consumer bỏ qua field mới |
| Tương thích | Không tương thích | Giữ amount: long nhưng đổi đơn vị từ cents sang dollars | Deserialize thành công nhưng tính toán sai |
| Không tương thích | Tương thích | Đổi tên customerId thành clientId dù cùng một định danh | Ý nghĩa không đổi nhưng consumer cũ có thể không đọc được |
| Không tương thích | Không tương thích | Xóa field bắt buộc và đổi status từ trạng thái thanh toán sang trạng thái giao hàng | Cả parser lẫn logic nghiệp vụ đều có thể hỏng |

Không nên dùng kết quả “schema compatible” làm tiêu chí duy nhất để duyệt một thay đổi data contract. Review cần có cả câu hỏi kỹ thuật về deserialize và câu hỏi nghiệp vụ về ý nghĩa.

## 3. Schema Registry kiểm tra gì và không kiểm tra gì?

Với Avro, Protobuf hoặc JSON Schema, Schema Registry lưu schema theo subject và version, rồi áp dụng compatibility policy khi đăng ký schema mới. Policy xác định quan hệ đọc/ghi giữa schema mới và schema trước đó.

Các hướng phổ biến:

| Policy | Ý nghĩa khái quát khi schema thay đổi từ v1 sang v2 |
|---|---|
| BACKWARD | Consumer dùng schema mới có thể đọc dữ liệu được ghi bằng schema cũ |
| FORWARD | Consumer dùng schema cũ có thể đọc dữ liệu được ghi bằng schema mới |
| FULL | Hỗ trợ cả hai hướng backward và forward |
| BACKWARD_TRANSITIVE | Kiểm tra backward với các phiên bản trước trong lịch sử subject |
| FORWARD_TRANSITIVE | Kiểm tra forward với các phiên bản trước trong lịch sử subject |
| FULL_TRANSITIVE | Kiểm tra cả hai hướng với các phiên bản trước trong lịch sử subject |

Các policy không giống nhau về mọi chi tiết giữa format và phiên bản Registry. Cần kiểm tra quy tắc cụ thể của serializer, schema format và Registry đang dùng. Đặc biệt, policy không transitive thường tập trung vào phiên bản gần nhất; transitive mở rộng kiểm tra với lịch sử subject.

Schema Registry có thể phát hiện một số thay đổi như xóa field bắt buộc, thay đổi kiểu không đọc được, enum/union không tương thích hoặc tái sử dụng field number theo quy tắc format. Nhưng Registry không biết:

- amount đang tính theo VND, USD, cent hay micro-unit.
- createdAt là thời điểm nghiệp vụ xảy ra hay thời điểm producer gửi event.
- status=PAID có nghĩa đã authorize, đã capture hay đã đối soát.
- customerId là ID nội bộ, ID CRM hay mã định danh toàn cục.
- Một mảng rỗng có nghĩa “không có phần tử”, “chưa biết” hay “không áp dụng”.
- Event có được phép đến trễ, lặp hoặc sai thứ tự hay không.

Vì vậy, một schema có thể đăng ký thành công nhưng vẫn tạo ra breaking change về nghiệp vụ.

## 4. Ví dụ: giữ nguyên kiểu dữ liệu nhưng đổi đơn vị

Giả sử phiên bản đầu tiên định nghĩa:

    {
      "type": "record",
      "name": "PaymentCaptured",
      "fields": [
        { "name": "paymentId", "type": "string" },
        { "name": "amount", "type": "long" },
        { "name": "currency", "type": "string" }
      ]
    }

Producer v1 gửi:

    {
      "paymentId": "pay-42",
      "amount": 125000,
      "currency": "USD"
    }

Consumer hiểu amount là số dollar. Sau đó producer v2 vẫn giữ kiểu long, nhưng đổi cách biểu diễn thành minor unit và gửi 125000 cent (tương đương 1250 USD). Schema vẫn có cùng tên field và kiểu dữ liệu; Registry có thể không phát hiện thay đổi này. Consumer cũ vẫn deserialize được 125000 nhưng có thể hiểu thành 125000 USD, sai một hệ số 100.

Hợp đồng nên nói rõ đơn vị và độ chính xác, ví dụ:

    {
      "paymentId": "pay-42",
      "amountMinor": 125000,
      "currency": "USD"
    }

Tên amountMinor vẫn chưa đủ nếu không có quy ước về exponent theo currency. Cần mô tả amountMinor là integer theo minor unit ISO 4217, nêu rõ cách xử lý currency không có hai chữ số thập phân và giới hạn giá trị. Nếu đổi cách biểu diễn, nên thêm field mới hoặc phát event version mới; không âm thầm đổi ý nghĩa field cũ.

## 5. Ví dụ: giữ nguyên enum nhưng đổi nghĩa trạng thái

Một event OrderStatusChanged có thể giữ nguyên schema:

    {
      "orderId": "order-42",
      "status": "PAID"
    }

Ở hợp đồng cũ, PAID nghĩa là payment provider đã authorize khoản tiền. Ở hợp đồng mới, producer dùng PAID để nói rằng tiền đã capture và quyết toán. Field và enum symbol không đổi, nhưng consumer có thể bắt đầu giao hàng sớm hơn hoặc ghi nhận doanh thu trước thời điểm phù hợp.

Enum chỉ định danh một symbol. Nó không mô tả đầy đủ state machine. Hợp đồng cần quy định:

- Ý nghĩa chính xác của từng trạng thái.
- Điều kiện để chuyển sang trạng thái đó.
- Trạng thái nào là terminal, trạng thái nào có thể tiếp tục thay đổi.
- Có trạng thái trung gian như AUTHORIZED, CAPTURED, SETTLED, REFUNDED hay không.
- Event biểu diễn trạng thái hiện tại hay một transition vừa xảy ra.
- Consumer có thể nhận event lặp hoặc đến sai thứ tự hay không.

Nếu hai khái niệm nghiệp vụ khác nhau, hãy dùng trạng thái hoặc event type khác nhau thay vì tái sử dụng một enum symbol với nghĩa mới.

## 6. Ví dụ: null, field vắng mặt và giá trị rỗng

Các biểu diễn sau có thể deserialize được nhưng không nhất thiết có cùng ý nghĩa:

| Biểu diễn | Ý nghĩa có thể có | Câu hỏi hợp đồng cần trả lời |
|---|---|---|
| Field không xuất hiện | Producer cũ chưa biết field hoặc field không áp dụng | Consumer có được dùng default không? |
| Field có giá trị null | Giá trị chưa biết, bị xóa hoặc không được cung cấp | Null biểu thị điều gì? |
| Chuỗi rỗng | Chuỗi rỗng hợp lệ | Có khác với null không? |
| Mảng [] | Biết chắc hiện không có phần tử | Có khác với “chưa tải dữ liệu” không? |
| 0 | Giá trị bằng không | Có được dùng làm sentinel cho unknown không? |

Ví dụ, phone=null có thể nghĩa là người dùng chưa cung cấp số điện thoại; một field phone bị bỏ qua có thể nghĩa là producer không cập nhật field đó trong patch event. Nếu consumer coi cả hai là “xóa số điện thoại”, dữ liệu sẽ bị xóa ngoài ý muốn.

Với event dạng patch, cần quy định riêng:

- Field vắng mặt: giữ nguyên giá trị cũ.
- Field có giá trị: thay bằng giá trị mới.
- Field null: xóa giá trị, nếu contract định nghĩa như vậy.

Với event dạng snapshot, semantics có thể khác: field vắng mặt hoặc null có thể biểu thị trạng thái không biết. Không áp dụng một quy tắc null chung cho mọi topic.

## 7. Ví dụ: đổi ý nghĩa timestamp mà không đổi kiểu

Hai field sau đều có thể dùng kiểu long hoặc timestamp logical type:

- occurredAt: thời điểm nghiệp vụ thực sự xảy ra tại nguồn.
- publishedAt: thời điểm producer gửi event vào Kafka.

Nếu producer giữ tên eventTime nhưng chuyển từ thời điểm xảy ra nghiệp vụ sang thời điểm publish, schema có thể không đổi. Tuy nhiên, consumer tính SLA, độ trễ thanh toán hoặc thứ tự nghiệp vụ sẽ nhận kết quả khác.

Hợp đồng timestamp nên xác định:

- Mốc thời gian biểu diễn: occurrence, creation, publication, ingestion hay processing.
- Timezone và định dạng: khuyến nghị UTC/Instant cho thời điểm tuyệt đối.
- Độ chính xác: milliseconds, microseconds hay nanoseconds.
- Clock source và mức sai lệch có thể chấp nhận.
- Event có thể đến muộn bao lâu và consumer nên xử lý late arrival thế nào.

Không đổi nghĩa createdAt thành processedAt chỉ vì cả hai đều là timestamp. Nếu cần thêm mốc mới, hãy thêm field mới với định nghĩa rõ ràng.

## 8. Ví dụ: thay đổi key làm đổi partition, ordering và compaction

Kafka key thường quyết định partition theo partitioner. Với compacted topic, key còn xác định nhóm record mà log cleaner giữ trạng thái mới nhất. Thay đổi ý nghĩa key có thể gây thay đổi lớn dù schema key vẫn là string.

Ví dụ v1 dùng customerId làm key:

    key = customer-42

Consumer nhận mọi event của cùng customer theo cùng partition, giúp giữ thứ tự theo customer. Nếu v2 đổi key sang orderId nhưng vẫn dùng cùng topic, event của một customer có thể phân tán sang nhiều partition. Ordering theo customer không còn được bảo đảm bởi cùng một partition. Với compacted topic, record mới theo orderId cũng không còn ghi đè trạng thái theo customerId.

Key contract phải mô tả:

- Danh tính logic mà key đại diện.
- Quy tắc canonicalization, casing và namespace.
- Key có ổn định qua vòng đời entity không.
- Partitioning có dựa vào key không và ordering cần ở cấp nào.
- Topic có dùng compaction không; key có là khóa của snapshot không.
- Null key có được phép và có ý nghĩa gì.

Đổi key semantics thường là một thay đổi contract lớn. Có thể cần topic mới hoặc migration có giai đoạn, không nên triển khai như một thay đổi serializer đơn giản.

## 9. Thay đổi cấu trúc nhưng giữ nguyên ý nghĩa

Một số thay đổi có thể giữ nguyên ý nghĩa nghiệp vụ nhưng vẫn làm hỏng consumer cũ nếu schema không hỗ trợ tương thích.

Ví dụ:

- Đổi tên field customerId thành clientId.
- Chuyển int thành một kiểu không tương thích với reader cũ.
- Xóa field mà reader cũ yêu cầu và không có default.
- Đổi field number trong Protobuf hoặc tái sử dụng number đã xóa.
- Thay đổi enum theo cách reader cũ không thể xử lý symbol mới.

Nếu tên cũ và tên mới thực sự cùng nghĩa, có thể giữ field cũ trong giai đoạn chuyển tiếp, thêm field mới, dual-read/dual-write theo chính sách rõ ràng, rồi loại field cũ sau khi toàn bộ consumer đã migrate. Với Protobuf, không tái sử dụng field number hoặc tên đã xóa; dùng reserved để ngăn tái sử dụng ngoài ý muốn.

Tương thích cấu trúc là điều kiện để rollout an toàn, ngay cả khi ý nghĩa nghiệp vụ không đổi.

## 10. Mô tả ý nghĩa nghiệp vụ ngay trong data contract

Schema nên đi cùng một mô tả contract có thể review và kiểm thử. Tối thiểu, mỗi event/field quan trọng nên có:

| Thuộc tính contract | Nội dung cần mô tả |
|---|---|
| Event identity | eventType, domain, producer/owner và phiên bản contract |
| Field meaning | Định nghĩa nghiệp vụ ngắn, rõ, tránh tên mơ hồ |
| Type and unit | Kiểu dữ liệu, đơn vị, precision, currency hoặc timezone |
| Required/nullability | Bắt buộc, tùy chọn, null có nghĩa gì, default có áp dụng không |
| Domain/range | Miền giá trị, min/max, enum symbols và ý nghĩa |
| Invariants | Quy tắc luôn phải đúng giữa các field |
| State transitions | Trạng thái hợp lệ và điều kiện chuyển trạng thái |
| Identity/key | Ý nghĩa key, partitioning, ordering và compaction |
| Time semantics | Occurrence time, publish time, timezone và precision |
| Delivery behavior | Duplicate, ordering, late arrival, replay và idempotency |
| Privacy/classification | PII, retention, masking và quyền truy cập |
| Evolution policy | Structural compatibility policy và quy trình semantic versioning |

Ví dụ contract rút gọn cho event thanh toán:

    eventType: com.example.payment.captured
    contractVersion: 2
    owner: payments
    key:
      meaning: paymentId
      stable: true
    ordering:
      scope: paymentId
      guarantee: partition-order
    fields:
      amountMinor:
        type: integer
        required: true
        meaning: Amount captured, represented in the currency minor unit
        constraints:
          minimum: 0
      currency:
        type: string
        required: true
        meaning: ISO 4217 currency code
      occurredAt:
        type: timestamp
        required: true
        meaning: Time at which the capture was confirmed by the payment provider
    invariants:
      - amountMinor is non-negative
      - currency and amountMinor must be interpreted together
    delivery:
      duplicates: possible
      consumerMustBeIdempotent: true

Đây là ví dụ mô tả hợp đồng, không phải một chuẩn YAML bắt buộc của Kafka. Mục tiêu là làm cho semantics có thể đọc, review và chuyển thành kiểm thử.

## 11. Quy tắc thay đổi: không tái sử dụng ý nghĩa cũ

Khi thay đổi contract, nên phân loại trước:

**Thêm thông tin không đổi nghĩa cũ.** Có thể thêm field tùy chọn/default nếu format và policy cho phép. Consumer cũ cần bỏ qua field mới; consumer mới phải có default phù hợp khi đọc record cũ.

**Sửa mô tả nhưng không đổi hành vi.** Làm rõ documentation, đơn vị hoặc ví dụ nếu semantics vốn đã như vậy. Nếu phát hiện producer cũ đang gửi sai nghĩa, cần xử lý migration dữ liệu thay vì chỉ sửa mô tả.

**Đổi đơn vị, miền giá trị hoặc state semantics.** Đây thường là breaking change nghiệp vụ dù schema giữ nguyên. Thêm field mới, tạo event type/version mới hoặc topic mới theo phạm vi ảnh hưởng; không âm thầm đổi nghĩa field đang được consumer sử dụng.

**Đổi identity/key hoặc ordering.** Đánh giá ảnh hưởng partitioning, state store, compaction, ordering và consumer lag. Thường cần migration riêng hoặc topic mới.

**Xóa/đổi field hoặc kiểu dữ liệu.** Kiểm tra backward/forward compatibility theo consumer rollout và format; dùng giai đoạn expand-contract nếu có thể.

Một nguyên tắc an toàn là: **không tái sử dụng tên field, enum symbol, event type hoặc key với một ý nghĩa nghiệp vụ khác**. Nếu ý nghĩa đã thay đổi, biểu diễn sự thay đổi đó bằng contract mới có thể nhận diện.

## 12. Structural compatibility và rollout producer/consumer

Compatibility policy cần được chọn theo cách deploy:

| Tình huống triển khai | Câu hỏi cần kiểm tra |
|---|---|
| Deploy consumer mới trước producer | Consumer mới có đọc được record cũ không? Đây là yêu cầu backward phổ biến |
| Deploy producer mới trước consumer | Consumer cũ có đọc được record mới không? Đây là yêu cầu forward phổ biến |
| Nhiều phiên bản cùng tồn tại lâu | Các phiên bản cũ hơn một bước có còn được hỗ trợ không? Cân nhắc transitive |
| Replay dữ liệu lịch sử | Consumer hiện tại có đọc được toàn bộ schema version còn trong retention không? |
| Dùng compacted topic | Consumer bootstrap có hiểu các record còn lại và tombstone qua các version không? |

Quy trình expand-contract thường dùng:

1. **Expand schema:** thêm field mới theo cách tương thích, giữ field cũ.
2. **Deploy consumer:** consumer mới đọc cả field cũ và mới, có fallback rõ ràng.
3. **Deploy producer:** producer bắt đầu ghi field mới; nếu cần, dual-write trong giai đoạn chuyển tiếp.
4. **Observe:** kiểm tra tỷ lệ producer/consumer version và dữ liệu thực tế.
5. **Migrate:** xác nhận mọi consumer đã dùng field mới và dữ liệu lịch sử được xử lý.
6. **Contract:** chỉ xóa field cũ khi không còn consumer phụ thuộc và compatibility policy cho phép.

Expand-contract chỉ giải quyết rollout cấu trúc. Nếu field mới có semantics khác, cần thêm migration nghiệp vụ, mapping và kiểm thử để bảo đảm consumer không trộn hai ý nghĩa.

## 13. Version schema và version hợp đồng nghiệp vụ

Schema Registry version thường tăng mỗi khi đăng ký schema mới trong subject. Version đó phản ánh lịch sử schema của subject, không nhất thiết là phiên bản nghiệp vụ mà domain owner muốn công bố.

Nên phân biệt:

- **Schema version:** version do Registry quản lý cho một subject.
- **Event/contract version:** version nghiệp vụ được producer và consumer hiểu theo quy ước của domain.
- **Application version:** phiên bản triển khai của service; không tự động là version event.

Không cần tăng semantic contract version cho mọi thay đổi cấu trúc tương thích và không đổi nghĩa. Ngược lại, thay đổi semantics có thể cần contract version mới ngay cả khi schema không thay đổi một byte.

Một số chiến lược:

- Thêm field tương thích, giữ nghĩa cũ: giữ cùng event type/contract major nếu chính sách domain cho phép.
- Thay đổi semantics breaking: tạo event type/version mới hoặc topic mới theo khả năng coexist và migration.
- Cần chạy hai luồng song song: producer có thể phát cả event v1 và v2 trong giai đoạn chuyển đổi, nhưng phải xác định nguồn dữ liệu chuẩn và tránh side effect hai lần.

Không dựa vào một field version chung nếu không định nghĩa rõ version đó áp dụng cho envelope, schema hay semantics.

## 14. Kiểm thử hai lớp hợp đồng

Một pipeline CI nên có ít nhất hai nhóm kiểm thử riêng.

### Structural compatibility tests

- Đăng ký schema candidate lên subject test hoặc dùng Registry compatibility API.
- Kiểm tra đúng subject naming strategy cho key/value.
- Kiểm tra backward/forward/full/transitive theo rollout thực tế.
- Dùng fixture record từ các schema version cũ để deserialize bằng consumer mới.
- Kiểm tra unknown fields, defaults, nullability, enum và field numbering theo format.
- Kiểm tra serializer/deserializer thực tế của Java/Spring Kafka, không chỉ parse schema file.

### Semantic contract tests

- Kiểm tra đơn vị, currency, precision và range.
- Kiểm tra null/absent/empty semantics.
- Kiểm tra enum meaning và state transition hợp lệ.
- Kiểm tra timestamp meaning, timezone và late-arrival behavior.
- Kiểm tra key identity, partitioning, ordering và compaction assumptions.
- Kiểm tra duplicate/replay có tạo side effect lặp hay không.
- Kiểm tra invariant giữa các field và hành vi với dữ liệu biên.

Ví dụ test semantic cho amount:

    @Test
    void amountMinorMustBeNonNegativeAndPairedWithCurrency() {
        PaymentCaptured event = new PaymentCaptured(
                "pay-42", 125000L, "VND");

        assertThat(event.amountMinor()).isGreaterThanOrEqualTo(0);
        assertThat(Currency.getInstance(event.currency())).isNotNull();
    }

Đây chỉ là kiểm tra đầu vào cơ bản. Contract thực tế cần kiểm tra quy tắc exponent/precision theo currency và giới hạn domain, không chỉ kiểm tra currency code tồn tại.

### Consumer-driven contract tests

Consumer có thể công bố các giả định mà nó phụ thuộc, ví dụ:

- status=CAPTURED là điều kiện được phép phát hành hàng.
- amountMinor luôn là số nguyên theo currency minor unit.
- customerId là định danh ổn định trong toàn bộ vòng đời customer.
- Một event có thể lặp và consumer phải deduplicate theo eventId.

Producer chạy contract tests để xác nhận dữ liệu phát ra đáp ứng các giả định đó. Điều này bổ sung cho Schema Registry; nó không thay thế schema compatibility check.

## 15. Quản trị thay đổi và ownership

Mỗi topic quan trọng nên có producer owner và consumer owner. Khi đề xuất thay đổi, pull request hoặc change request cần nêu:

1. Schema diff và kết quả Registry compatibility check.
2. Field/event/key semantics thay đổi hay giữ nguyên.
3. Consumer nào bị ảnh hưởng và rollout order.
4. Fixture cũ/mới và kết quả structural + semantic tests.
5. Kế hoạch dual-read/dual-write, migration và rollback.
6. Cách xử lý dữ liệu đã nằm trong Kafka trước khi deploy.
7. Cách giám sát producer version, consumer version, lỗi deserialize và lỗi nghiệp vụ.

Schema Registry không phải nơi duy nhất lưu hợp đồng. Hãy quản lý mô tả nghiệp vụ, ví dụ payload, invariant, ownership và lifecycle trong tài liệu contract có version control. Mọi thay đổi semantics cần được domain owner review.

## 16. Những hiểu nhầm thường gặp

- **“Schema Registry báo compatible nghĩa là không breaking.”** Nó chỉ đánh giá structural compatibility theo format và policy; semantics vẫn có thể thay đổi.
- **“Giữ nguyên kiểu long thì có thể đổi đơn vị.”** Consumer vẫn deserialize nhưng kết quả nghiệp vụ có thể sai.
- **“Thêm enum symbol luôn an toàn.”** Consumer cũ có thể không hiểu symbol mới; còn ý nghĩa state cần được review riêng.
- **“Field nullable có nghĩa là tùy chọn nên không cần mô tả.”** Null, absent và empty có thể mang ba ý nghĩa khác nhau.
- **“Đổi key chỉ ảnh hưởng serializer.”** Key có thể thay đổi partition, ordering, compaction và cách dựng state.
- **“Schema version chính là contract version.”** Registry version và business version phục vụ hai mục đích khác nhau.
- **“Backward compatible là đủ cho mọi rollout.”** Cần xem consumer-first/producer-first, replay lịch sử và thời gian coexist.
- **“Tài liệu field là đủ.”** Invariant, state machine, duplicate, ordering và operational behavior cũng là một phần hợp đồng.

## 17. Checklist review data contract

- [ ] Đã kiểm tra structural compatibility theo format, subject và rollout direction.
- [ ] Đã xác định policy có cần transitive để hỗ trợ replay lịch sử không.
- [ ] Không tái sử dụng field, enum symbol, event type hoặc key với ý nghĩa mới.
- [ ] Mọi amount có đơn vị, currency và precision rõ ràng.
- [ ] Mọi timestamp có định nghĩa occurrence/creation/publication/processing và timezone.
- [ ] Null, absent, empty và default có semantics được mô tả.
- [ ] Enum/state machine có định nghĩa và transition hợp lệ.
- [ ] Key semantics, partitioning, ordering và compaction được đánh giá.
- [ ] Invariant và miền giá trị có semantic contract tests.
- [ ] Consumer có fixture test với schema version cũ; producer có test payload mới.
- [ ] Rollout expand-contract có thứ tự, quan sát và rollback plan.
- [ ] Contract version được phân biệt với schema version và application version.
- [ ] Producer/consumer owner đã review thay đổi nghiệp vụ.

Tương thích cấu trúc bảo đảm dữ liệu có thể được giải mã theo những schema version được hỗ trợ; tương thích ý nghĩa bảo đảm ứng dụng vẫn hiểu đúng giá trị và quy tắc nghiệp vụ. Hai lớp phải được review và kiểm thử riêng. Schema Registry là một hàng rào quan trọng cho schema evolution, còn data contract đầy đủ phải mô tả thêm đơn vị, trạng thái, thời gian, key, invariant, ordering và hành vi retry/replay để một thay đổi “đọc được” cũng thực sự “hiểu đúng”.
