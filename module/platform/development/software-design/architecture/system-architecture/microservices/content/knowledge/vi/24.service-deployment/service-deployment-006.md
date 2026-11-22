# Triển khai khi hợp đồng cũ và mới cùng tồn tại trong Microservices

Một hệ thống Microservices hiếm khi nâng cấp đồng loạt mọi thành phần. Trong khi một dịch vụ đã triển khai bản mới, dịch vụ gọi đến nó có thể vẫn đang dùng SDK cũ; trong lúc rolling deployment, các pod của cùng dịch vụ có thể chạy hai phiên bản; còn mobile client hoặc consumer sự kiện có thể tiếp tục sử dụng hợp đồng cũ trong nhiều tuần. Khi đó, khả năng **duy trì đồng thời hợp đồng cũ và hợp đồng mới** là điều kiện quan trọng để phát hành độc lập và giảm downtime.

Bài học này trình bày cách thiết kế, triển khai, kiểm thử và gỡ bỏ giai đoạn chuyển tiếp hợp đồng trong Microservices. Hợp đồng ở đây bao gồm API request/response, event schema, quy tắc xử lý lỗi, ngữ nghĩa dữ liệu và các điều kiện lưu trữ mà phiên bản ứng dụng đang hoạt động cần. Mục tiêu là tạo đường nâng cấp có kiểm soát: **mở rộng khả năng tương thích → triển khai an toàn → chuyển consumer → loại bỏ hợp đồng cũ**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao phiên bản cũ và mới phải tồn tại đồng thời trong rolling deploy, canary và phát hành độc lập.
- Phân biệt hợp đồng API, event và storage; xác định bên cung cấp và bên tiêu thụ của từng hợp đồng.
- Thiết kế thay đổi theo mô hình Expand–Migrate–Contract để không buộc các service nâng cấp cùng một thời điểm.
- Triển khai hai phiên bản REST API cùng dùng một lõi nghiệp vụ thay vì nhân đôi logic.
- Lập kế hoạch tương thích cho producer/consumer event, database migration và retry.
- Chọn thứ tự triển khai, điều kiện canary, ngưỡng rollback và thời điểm deprecate hợp đồng.
- Xây dựng kiểm thử hỗn hợp phiên bản và quan sát hành vi thực tế trong giai đoạn chuyển tiếp.
- Nhận biết rủi ro của dual-write, dữ liệu hai định dạng, feature flags và các thay đổi ngữ nghĩa không thể đảo ngược.

## 2. Vì sao hợp đồng cũ và mới thường cùng tồn tại?

Giả sử Order Service gọi Payment Service qua HTTP:

~~~text
Order Service v1 ----------+
                           |--> Payment Service v2
Order Service v2 ----------+
~~~

Nhóm Payment muốn đổi request từ amount dạng số nguyên biểu diễn đồng sang amountMinorUnits biểu diễn đơn vị tiền nhỏ nhất và bổ sung currency. Nếu Payment chỉ chấp nhận request mới, Order v1 ngừng hoạt động ngay khi Payment được triển khai. Nếu Order v2 được triển khai trước nhưng Payment v1 chưa hiểu request mới, kết quả cũng có thể lỗi.

Tình huống tương tự xảy ra với:

1. **Rolling deployment:** bộ cân bằng tải vẫn chuyển request đến instance phiên bản cũ và mới.
2. **Canary release:** chỉ một phần lưu lượng được thử nghiệm trên phiên bản mới.
3. **Blue–green deployment:** hai môi trường tồn tại trước khi chuyển toàn bộ traffic.
4. **Client không nâng cấp đồng thời:** mobile app, đối tác hoặc dịch vụ khác tiếp tục gọi endpoint cũ.
5. **Async messaging:** event được lưu trong broker có thể được consumer mới đọc lại; consumer cũ vẫn nhận event từ producer mới.
6. **Rollback:** một binary cũ được chạy trở lại sau khi schema và dữ liệu đã thay đổi.
7. **Triển khai nhiều vùng:** các region được nâng cấp ở thời điểm khác nhau hoặc cache/CDN giữ payload cũ.

Điểm chung là **thời điểm chuyển đổi không đồng nhất**. Thiết kế phải xác định một giai đoạn mà các tổ hợp còn được hỗ trợ đều hoạt động.

## 3. “Hợp đồng” bao gồm những gì?

Không nên đồng nhất hợp đồng với tên endpoint hoặc định dạng JSON. Một hợp đồng thực tế có nhiều lớp:

| Loại hợp đồng | Bề mặt thay đổi | Ví dụ |
|---|---|---|
| HTTP/REST | URL, method, header, status code, request/response | POST /v1/payments và POST /v2/payments |
| gRPC/Protobuf | RPC method, message field number/type, enum, streaming | Thêm field optional vào PaymentRequest |
| Sự kiện | Topic, event type/version, schema, routing key, ordering | OrderPlaced v1 và v2 cùng tồn tại |
| Database | Schema, column, constraint, dữ liệu lịch sử | Bổ sung cột mới trước khi xóa cột cũ |
| Ngữ nghĩa nghiệp vụ | Đơn vị, quy tắc tính toán, ý nghĩa trạng thái, idempotency | amount chuyển từ VND sang minor units |
| Vận hành | Auth, deadline, timeout, retry, feature flags | Header mới hoặc scope quyền mới |

Một thay đổi có thể tương thích cú pháp mà vẫn không tương thích ngữ nghĩa. Ví dụ giữ tên trường amount nhưng đổi từ 100000 VND thành 100000 cents làm consumer tính tiền sai; JSON vẫn parse bình thường.

Để lập kế hoạch, luôn ghi rõ **bên cung cấp, bên tiêu thụ, version của mỗi bên và hợp đồng cụ thể**. “Service v2 tương thích v1” là phát biểu quá rộng nếu dịch vụ có nhiều endpoint và event với chính sách khác nhau.

### 3.1. Phân biệt tương thích ngược và tương thích xuôi

Có hai câu hỏi thực dụng:

- **Provider mới phục vụ consumer cũ được không?** Cần cho rollout provider trước, khi client cũ chưa đổi.
- **Consumer mới làm việc với provider cũ được không?** Cần khi consumer được phát hành trước hoặc traffic vẫn đến instance provider cũ.

Đối với event/schema, thường cần thêm:

- **Consumer mới đọc event cũ được không?** Quan trọng khi replay, đọc backlog hoặc reprocess.
- **Consumer cũ đọc event mới được không?** Quan trọng khi producer mới phát hành trước consumer.

Hai hướng không tự động suy ra nhau. Trường mới là optional ở producer cũng chưa đủ nếu parser cũ strict hoặc xử lý enum mới không an toàn.

## 4. Thiết kế chiến lược Expand–Migrate–Contract

Đây là mô hình cốt lõi cho triển khai nhiều phiên bản:

~~~text
Giai đoạn 0: Chỉ hợp đồng cũ
      |
      v
EXPAND: Provider hiểu/đáp ứng cả hợp đồng cũ và mới
      |
      v
MIGRATE: Chuyển consumer theo từng nhóm; theo dõi sử dụng cũ
      |
      v
CONTRACT: Chỉ gỡ hợp đồng cũ khi điều kiện hỗ trợ đã kết thúc
      |
      v
Trạng thái đích: Hợp đồng mới là chuẩn
~~~

**Expand** không đồng nghĩa lập tức sử dụng định dạng mới trên mọi đường truyền. Mục tiêu đầu tiên là làm cho thành phần có thể tiếp nhận cả hai cách giao tiếp một cách an toàn. **Migrate** có thể gồm chuyển ứng dụng, dữ liệu, event, client SDK và quy trình vận hành. **Contract** là thời điểm xóa code hỗ trợ cũ sau khi đã có bằng chứng consumer không còn phụ thuộc.

### 4.1. Những điều kiện phải xác định trước

- Version hiện đang chạy ở production, canary, các vùng và những client không thể ép nâng cấp.
- Contract nào đang được consumer thực sự dùng: field, endpoint, enum, error handling, event.
- Thời gian tồn tại dự kiến của phiên bản cũ và chính sách deprecation.
- Có cần chạy song song binary v1/v2 với cùng database hay không.
- Khi rollback, binary cũ có đọc được dữ liệu do binary mới tạo ra không.
- Cách xác nhận traffic cũ đã giảm về ngưỡng cho phép trước khi xóa đường tương thích.

Nếu không có inventory và telemetry, việc “đã thông báo nâng cấp” không phải bằng chứng rằng mọi consumer đã chuyển xong.

## 5. Ví dụ xuyên suốt: đổi hợp đồng thanh toán

Ban đầu, Order Service v1 gửi:

~~~http
POST /v1/payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-42

{
  "orderId": "order-42",
  "amount": 150000
}
~~~

Trong ví dụ, amount của v1 được hiểu là VND. Nhóm muốn hỗ trợ nhiều loại tiền tệ và định nghĩa v2:

~~~http
POST /v2/payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-42

{
  "orderId": "order-42",
  "amountMinorUnits": 150000,
  "currency": "VND"
}
~~~

Đối với VND, giá trị minh họa này có thể trùng số học với amount cũ theo quy tắc nội bộ, nhưng với tiền tệ có phần thập phân thì amountMinorUnits có thể khác. Vì vậy, adapter phải **chuyển đổi theo quy tắc đơn vị được đặc tả**, không tự giả định hai trường tương đương cho mọi currency.

Trong giai đoạn chuyển tiếp:

- Payment v2 phục vụ cả /v1/payments và /v2/payments.
- Order v1 vẫn dùng /v1/payments.
- Order v2 dùng /v2/payments sau khi Payment v2 có mặt và vượt kiểm thử.
- Cả hai endpoint đi vào cùng logic thanh toán nội bộ với mô hình tiền tệ chuẩn.
- Khi Order v1 và các consumer cũ đã hết thời hạn hỗ trợ, nhóm mới gỡ /v1/payments.

### 5.1. Ma trận tương thích minh họa

| Consumer \ Provider | Payment v1 (chỉ API v1) | Payment v2 (API v1 + API v2) |
|---|---|---|
| Order v1 (gọi API v1) | PASS | PASS |
| Order v2 (chỉ gọi API v2) | FAIL | PASS |
| Order v2 có fallback API v1 | Có thể PASS sau kiểm thử | PASS |

Kết quả là **giả định dành cho ví dụ**, không phải số liệu thực tế. Ma trận cho thấy nên triển khai Payment v2 trước khi bật đường gọi API v2 của Order v2. Khi rolling rollout Payment v2, nếu còn instance v1 nhận traffic, gateway hoặc service discovery cần bảo đảm request API v2 đến đúng instance hỗ trợ nó.

## 6. Tổ chức code để phục vụ hai hợp đồng

Một cách triển khai an toàn là giữ **hai adapter giao tiếp mỏng** và dùng chung service nghiệp vụ. Mỗi adapter chuyển payload sang một mô hình nội bộ thống nhất:

~~~text
HTTP /v1/payments ---> V1 Controller ---> V1 Mapper ---+
                                                        |
                                                        v
                                                 PaymentUseCase
                                                        |
                                                        v
                                                Domain / Persistence
                                                        ^
                                                        |
HTTP /v2/payments ---> V2 Controller ---> V2 Mapper ---+
~~~

Cấu trúc này giữ logic nghiệp vụ ở một nơi. Khi hợp đồng cũ hết hỗ trợ, có thể xóa controller/mapper v1 mà ít rủi ro tác động đến lõi nghiệp vụ.

### 6.1. Ví dụ Spring Boot rút gọn

~~~java
record PaymentV1Request(String orderId, long amount) {}

record PaymentV2Request(
    String orderId,
    long amountMinorUnits,
    String currency
) {}

record PaymentCommand(
    String orderId,
    long amountMinorUnits,
    String currency
) {}

interface PaymentUseCase {
    String pay(PaymentCommand command, String idempotencyKey);
}
~~~

Adapter v1 có thể giữ đơn vị VND theo hợp đồng cũ:

~~~java
@RestController
@RequestMapping("/v1/payments")
class PaymentV1Controller {
    private final PaymentUseCase useCase;

    PaymentV1Controller(PaymentUseCase useCase) {
        this.useCase = useCase;
    }

    @PostMapping
    ResponseEntity<Map<String, String>> create(
            @RequestBody PaymentV1Request request,
            @RequestHeader("Idempotency-Key") String key) {

        // Quy ước v1 trong ví dụ: amount là số nguyên VND.
        PaymentCommand command = new PaymentCommand(
            request.orderId(), request.amount(), "VND"
        );

        String id = useCase.pay(command, key);
        return ResponseEntity.status(201).body(Map.of("paymentId", id));
    }
}
~~~

Adapter v2 chấp nhận currency và minor units tường minh:

~~~java
@RestController
@RequestMapping("/v2/payments")
class PaymentV2Controller {
    private final PaymentUseCase useCase;

    PaymentV2Controller(PaymentUseCase useCase) {
        this.useCase = useCase;
    }

    @PostMapping
    ResponseEntity<Map<String, String>> create(
            @RequestBody PaymentV2Request request,
            @RequestHeader("Idempotency-Key") String key) {

        PaymentCommand command = new PaymentCommand(
            request.orderId(),
            request.amountMinorUnits(),
            request.currency()
        );

        String id = useCase.pay(command, key);
        return ResponseEntity.status(201).body(Map.of("paymentId", id));
    }
}
~~~

Code minh họa chủ ý tập trung vào hai endpoint và lớp chuyển đổi. Ứng dụng thật cần bean cấu hình, validation, quy tắc đổi minor units cho từng currency, phân quyền, exception mapping, persistence, event publication và idempotency được kiểm tra riêng. Nếu v1 có cấu trúc response hoặc mã lỗi khác, adapter cần duy trì chính xác hợp đồng response v1; không được vô tình đổi chỉ vì dùng chung use case.

### 6.2. Một phiên bản endpoint hay một versioned endpoint?

Có nhiều cách phân biệt hợp đồng:

| Cách | Ví dụ | Điểm mạnh | Cân nhắc |
|---|---|---|---|
| Version trong URL | /v1/orders, /v2/orders | Dễ nhìn, log và định tuyến | Phải quản lý endpoint trùng và lịch deprecate |
| Version trong header | API-Version: 2 | URL ổn định | Gateway, cache và observability phải nhận diện header |
| Media type version | Accept: application/vnd.example.order-v2+json | Rõ representation | Vận hành và công cụ có thể phức tạp hơn |
| Tương thích trong một contract | Thêm optional fields, giữ semantics cũ | Ít endpoint hơn | Chỉ phù hợp khi không có breaking behavior |

Version của endpoint không nhất thiết bằng version triển khai của service. Payment Service v2.7 có thể phục vụ cả hợp đồng API v1 và API v2. Version service dùng để định danh artifact; API version dùng để quản lý hợp đồng công khai.

## 7. Đặt ranh giới chuyển đổi tại adapter

Nếu phải chấp nhận hai payload, hãy chuyển đổi ở sát giao diện nhất và dùng mô hình nội bộ duy nhất. Tránh để mọi lớp nghiệp vụ phải phân nhánh theo kiểu “request đến từ v1 hay v2”.

Ví dụ quy tắc adapter:

1. Xác minh payload theo schema của phiên bản tương ứng.
2. Chuyển field, đơn vị, enum và default value sang mô hình nội bộ.
3. Từ chối các đầu vào mơ hồ thay vì đoán; ví dụ amount và amountMinorUnits cùng có nhưng mâu thuẫn.
4. Thực hiện use case chung và xử lý idempotency ở một nơi.
5. Ánh xạ kết quả trở lại cấu trúc response/status code mà phiên bản yêu cầu.

Một thay đổi thuần hình thức có thể dùng mapper đơn giản. Một thay đổi quy tắc nghiệp vụ cần thêm test semantics; nếu hai API có cam kết thật sự khác nhau, dùng các policy rõ ràng ở lớp application thay vì trộn điều kiện version vào domain.

## 8. Database schema khi binary cũ và mới cùng chạy

Rolling deployment có thể tạo giai đoạn App v1 và App v2 truy cập cùng một database. Nếu migration xóa cột cũ ngay trước khi toàn bộ pod cũ rời hệ thống, v1 có thể lỗi trong thời gian rollout.

### 8.1. Ví dụ đổi tên cột

Giả sử bảng customers có cột full_name, App v2 muốn dùng display_name.

**Giai đoạn Expand:** thêm cột mới theo cách an toàn đối với binary cũ:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name text;
~~~

App v1 vẫn đọc/ghi full_name. App v2 có thể đọc display_name và fallback về full_name khi chưa backfill. Nếu cả v1 và v2 còn ghi, thiết kế đồng bộ giá trị cần được xác định rõ.

**Giai đoạn Migrate:** backfill dữ liệu lịch sử:

~~~sql
UPDATE customers
SET display_name = full_name
WHERE display_name IS NULL;
~~~

Trên bảng lớn, backfill nên theo lô, có giới hạn khóa/transaction, theo dõi tiến độ và khả năng chạy lại. Trong thời gian chuyển đổi, nếu còn writer v1, chỉ backfill một lần không bảo đảm display_name luôn cập nhật; cần giải pháp đồng bộ được kiểm soát.

**Giai đoạn Contract:** chỉ xóa trường cũ sau khi mọi binary, job nền và báo cáo được hỗ trợ đã ngừng phụ thuộc:

~~~sql
ALTER TABLE customers
DROP COLUMN full_name;
~~~

Các lệnh SQL trên là minh họa. Trong dự án thực tế, migration phải được phiên bản hóa (Flyway/Liquibase hoặc công cụ tương đương), được kiểm thử trên dữ liệu và quy mô gần thực tế, và có kế hoạch rollback/roll-forward.

### 8.2. Những câu hỏi phải trả lời trước migration

- App v1 có chạy với schema đã Expand không?
- App v2 có đọc được row trước và sau backfill không?
- Nếu App v1 tiếp tục ghi, dữ liệu App v2 đọc có nhất quán không?
- Nếu App v2 đã ghi theo format mới, App v1 có thể đọc hoặc rollback được không?
- Migration có gây lock dài, làm tăng latency hoặc không tương thích với connection pool hiện tại không?
- Có hệ thống báo cáo/ETL nào đọc trực tiếp cột cũ ngoài danh sách service không?

Nhiều hệ thống cần một thời gian dài giữa Expand và Contract. Không nên đồng nhất “schema migration đã chạy” với “an toàn xóa cột”.

### 8.3. Dual-write: chỉ dùng khi thật sự cần

Nếu hai phiên bản cần đồng thời viết full_name và display_name, có thể dùng adapter ghi cả hai hoặc một cơ chế đồng bộ dữ liệu trong thời gian chuyển đổi. Nhưng dual-write tạo các tình huống bất thường: một nhánh ghi thành công còn nhánh khác lỗi; thứ tự ghi khác nhau; backfill đè dữ liệu mới; retry tạo trạng thái không nhất quán.

Các biện pháp thiết kế:

- Xác định một **nguồn sự thật** và quy tắc ưu tiên khi hai giá trị mâu thuẫn.
- Với hai cột cùng database, cân nhắc một transaction thích hợp và cách xử lý tác vụ cập nhật từ binary cũ.
- Có chỉ số so sánh dữ liệu cũ/mới; không xóa trường cũ khi dữ liệu chưa hội tụ.
- Với hai datastore khác nhau, dùng outbox/CDC hoặc cơ chế có retry, idempotency và theo dõi lỗi; không giả định hai lệnh mạng sẽ là một transaction nguyên tử.
- Thiết kế đường đọc fallback và mốc kết thúc dual-write rõ ràng.

Không dùng dual-write vô thời hạn như một cách thay thế cho việc hoàn tất migration.

## 9. Sự kiện cũ và mới trên message broker

Event thường có vòng đời dài hơn thời gian một HTTP request. Một event đã ghi trong Kafka có thể được giữ theo retention hoặc replay về sau; một consumer chưa nâng cấp vẫn có thể nhận event do producer mới phát ra.

Ví dụ hợp đồng cũ:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "orderId": "o-100",
  "amount": 150000
}
~~~

Hợp đồng mới có currency và amountMinorUnits:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderPlaced",
  "eventVersion": 2,
  "orderId": "o-100",
  "amountMinorUnits": 150000,
  "currency": "VND"
}
~~~

Nếu consumer v1 bắt buộc trường amount, nó có thể không hiểu event v2. Nếu consumer v2 chỉ hiểu amountMinorUnits, việc replay v1 có thể lỗi.

### 9.1. Chiến lược phát triển event

**Phương án A — Mở rộng tương thích trên cùng event:** giữ field cũ, thêm field mới và đặt quy tắc default/validation. Phù hợp khi ngữ nghĩa không mâu thuẫn và consumer cũ bỏ qua field mới.

**Phương án B — Dual publish có thời hạn:** producer phát cả event v1 và v2 đến kênh hoặc event type được phân biệt rõ. Phù hợp khi thay đổi breaking và consumer có lộ trình chuyển đổi khác nhau. Cần thiết kế eventId/correlationId và cơ chế chống xử lý nghiệp vụ hai lần.

**Phương án C — Event translator:** adapter đọc event cũ và chuyển thành event mới cho một tập consumer, hoặc ngược lại nếu chuyển đổi là không mất thông tin. Cần lưu nguồn, version và khả năng truy vết.

**Phương án D — Consumer đọc nhiều version:** consumer mới chấp nhận v1/v2 bằng các parser versioned rồi chuẩn hóa thành domain event chung. Phù hợp khi cần replay lịch sử trong một thời gian dài.

Không có phương án luôn đúng cho mọi hệ thống. Quyết định phụ thuộc số lượng consumer, độ trễ nâng cấp, retention/replay, quy tắc schema, khả năng chuyển đổi semantics và chi phí vận hành.

### 9.2. Tránh nhân đôi side effect khi dual publish

Khi cùng một thay đổi nghiệp vụ tạo event v1 và v2, một consumer đang đăng ký cả hai kênh có thể xử lý cùng đơn hàng hai lần. Cần quy định:

- Event v1 và v2 mô tả **cùng business occurrence** hay là hai event độc lập?
- Có business key, aggregate ID hoặc correlation ID chung để liên hệ không?
- Consumer có cơ chế idempotency dựa trên business occurrence thay vì chỉ dựa trên message ID không?
- Routing/subscription có chặn một consumer nhận trùng hai format khi chưa hỗ trợ deduplication không?
- Nếu retry publish một phần, có phục hồi nhất quán được không?

Một triển khai thường dùng transactional outbox trong service sở hữu thay đổi, sau đó các publisher/adapters phát event theo contract. Transactional outbox không tự bảo đảm exactly-once cho mọi side effect ở consumer; idempotency vẫn cần được kiểm tra.

### 9.3. Schema Registry và compatibility rule

Avro, Protobuf và JSON Schema có các quy tắc tương thích khác nhau. Schema Registry có thể từ chối thay đổi vi phạm chính sách BACKWARD, FORWARD hoặc FULL, tùy cấu hình và cách diễn giải reader/writer. Tuy nhiên, kiểm tra schema không phát hiện mọi breaking change về nghĩa, ví dụ đổi amount từ đơn vị đồng sang xu hoặc thay thứ tự ưu tiên nghiệp vụ.

## 10. Thứ tự triển khai producer và consumer

Trình tự rollout phụ thuộc **hướng tương thích** của hợp đồng mới. Ví dụ khi thay REST API:

**Trường hợp provider mới chấp nhận cả API v1 và v2:**

~~~text
Trạng thái đầu: Consumer v1 ----> Provider v1
Bước 1:         Consumer v1 ----> Provider v2 (v1 + v2)
Bước 2:         Consumer v2 ----> Provider v2 (v1 + v2)
Bước 3:         Chỉ khi hết consumer v1 mới bỏ API v1
~~~

Trình tự “provider trước” hợp lý vì provider mới đã được thiết kế để phục vụ consumer cũ.

**Trường hợp consumer mới có fallback với provider cũ:**

~~~text
Trạng thái đầu: Consumer v1 ----> Provider v1
Bước 1:         Consumer v2 (fallback) ----> Provider v1
Bước 2:         Consumer v2 (fallback) ----> Provider v2
Bước 3:         Khi ổn định mới tắt fallback nếu không cần
~~~

Không suy ra một thứ tự triển khai chung từ tên gọi producer/consumer. Với event, cần phân tích cả consumer cũ nhận event mới và consumer mới đọc event cũ. Thứ tự an toàn là kết quả từ **ma trận tương thích** và tính chất thực tế của message broker.

## 11. Ma trận mixed-version là điều kiện release

Ví dụ một provider P v1/v2 và consumer C v1/v2:

| | P v1 | P v2 |
|---|---|---|
| C v1 | Đang chạy: bắt buộc PASS | Bắt buộc PASS khi triển khai P trước |
| C v2 | Cần PASS nếu có thể rollout C trước hoặc rollback P | Trạng thái đích: bắt buộc PASS |

Ma trận cần mở rộng khi có shared database schema, feature flag và event version. Kết quả nên có ít nhất: service version hoặc image digest, contract revision, test suite, môi trường, trạng thái và bằng chứng CI.

Trạng thái nên phân biệt rõ:

- **PASS:** tổ hợp đã chạy đủ test bắt buộc và đạt.
- **FAIL:** đã chạy nhưng có lỗi.
- **NOT_TESTED:** chưa có chứng cứ xác nhận.
- **BLOCKED:** test không thể hoàn tất do môi trường/phụ thuộc.
- **UNSUPPORTED:** tổ hợp nằm ngoài chính sách hỗ trợ, dù có thể vẫn chạy được.

Không dùng kết quả PASS của “latest + latest” để suy ra các tổ hợp giữa phiên bản cũ và mới cũng an toàn.

## 12. Canary, rolling và blue–green khi có hai hợp đồng

### 12.1. Rolling deployment

Trong rolling deployment, cùng một hostname/service discovery entry có thể trỏ tới cả pod v1 và v2. Nếu request API v2 được gửi đến pod v1 không hỗ trợ, request thất bại dù một phần pod mới đang hoạt động.

Có một số cách xử lý:

1. Thiết kế binary mới tương thích request cũ, rồi chỉ bật consumer v2 khi **toàn bộ provider có thể nhận request** đều đã nâng cấp.
2. Dùng API gateway hoặc service mesh để route có ý thức theo version/contract.
3. Triển khai một pool/vhost riêng cho API v2 trong thời gian chuyển tiếp, sau đó hợp nhất khi tương thích hoàn toàn.

Lựa chọn cần tính đến retry, connection reuse, sticky session, background job và các lệnh gọi không đi qua gateway. Một quy tắc route đúng ở ingress chưa chắc giải quyết được service-to-service traffic nội bộ.

### 12.2. Canary

Canary đưa lưu lượng thật đến binary mới theo một tỷ lệ hoặc nhóm người dùng giới hạn. Những điều nên theo dõi theo từng contract version:

- Request volume của API v1/v2 và nguồn consumer tương ứng.
- Tỷ lệ lỗi HTTP/gRPC, lỗi validation, auth và serialization.
- Latency p95/p99, timeout và retry.
- Chênh lệch kết quả nghiệp vụ giữa đường cũ và mới.
- Event deserialize failure, dead-letter count và consumer lag.
- Số request/transaction bị từ chối hoặc side effect trùng lặp.

Nếu canary được bật cho producer mới, kiểm tra consumer cũ có thể nhận event mới hay không. Không chỉ nhìn các metric cấp pod của producer.

### 12.3. Blue–green

Blue–green giúp chuyển traffic giữa hai môi trường, nhưng cả blue và green vẫn có thể chia sẻ database, broker, cache hoặc bên thứ ba. Vì thế, sự tách biệt traffic không tự động giải quyết tương thích schema hay event. Cần tính đến dữ liệu đã ghi bởi green và việc blue tiếp tục xử lý sau rollback.

## 13. Feature flag trong giai đoạn chuyển tiếp

Feature flag giúp tách **triển khai code** khỏi **kích hoạt hành vi mới**. Có thể triển khai producer đã hiểu hai format, giữ đường mới OFF, sau đó bật dần cho consumer phù hợp.

~~~text
T0: Triển khai Payment v2 có /v1 và /v2, flag new-contract OFF
T1: Xác nhận Payment v2 ổn định trên đường /v1
T2: Bật flag với nhóm Order v2 đã kiểm thử
T3: Tăng tỷ lệ lưu lượng theo chỉ số quan sát
T4: Khi consumer cũ hết dùng, lên lịch loại bỏ /v1
~~~

Những yêu cầu thực tế:

- Flag có owner, mục đích và ngày xem xét xóa.
- Flag được định danh theo consumer/tenant/correlation ID ổn định nếu cần cùng một workflow dùng cùng contract.
- Có telemetry biết mỗi request/event chạy qua đường nào.
- Nếu flag có thể thay đổi giữa chừng, logic phải chịu được một workflow đang dở dang.
- Flag không thay thế contract test hay đảm bảo rollback database an toàn.

Không nên để số lượng flag tương thích tăng mãi sau mỗi lần phát hành. Giai đoạn Contract phải bao gồm việc dọn code và cấu hình hết hiệu lực.

## 14. Retry, idempotency và các tình huống lỗi

Trong giai đoạn hai hợp đồng cùng tồn tại, retry có thể đổi đích từ instance v1 sang v2 hoặc từ adapter cũ sang adapter mới. Nếu mỗi adapter tạo idempotency key theo cách khác nhau, hệ thống có thể xử lý cùng nghiệp vụ hai lần.

Ví dụ một request trả timeout sau khi thanh toán đã thành công. Client retry bằng API v2 trong khi lần đầu gọi API v1. Nếu hai endpoint không cùng cơ chế idempotency, giao dịch có nguy cơ nhân đôi.

Cần:

1. Xác định idempotency key theo cùng business operation, không theo version endpoint.
2. Ánh xạ cả API v1 và v2 về cùng use case và kho kiểm soát idempotency.
3. Kiểm tra trường hợp lỗi sau commit nhưng trước response.
4. Giữ mapping error và retryable/non-retryable tương thích với consumer cũ.
5. Kiểm thử timeout, disconnect, duplicate request, reordering và retry xuyên các phiên bản.

Nếu version mới mở rộng enum lỗi, consumer cũ phải có hành vi mặc định an toàn, ví dụ lỗi không biết được phân loại thành thất bại có kiểm soát thay vì bỏ qua và coi như thành công.

## 15. Tương thích authentication và authorization

Đổi hợp đồng có thể đồng thời đổi cơ chế xác thực:

- Thêm OAuth scope mới hoặc đổi audience.
- Bắt buộc header X-Correlation-ID hoặc mTLS mới.
- Đổi định dạng token, key rotation hoặc claim được tiêu thụ.
- Bổ sung endpoint mới có quyền truy cập rộng hơn.

Trong thời gian hai hợp đồng cùng tồn tại, cần ghi rõ policy của mỗi phiên bản. Đường v1 không được vô tình bỏ qua kiểm tra quyền chỉ vì được giữ lại để tương thích; đường v2 không thể mặc nhiên yêu cầu một claim mà consumer cũ không bao giờ gửi nếu còn cam kết hỗ trợ v1.

Mọi đường phiên bản phải có cùng mức bảo vệ đối với dữ liệu nhạy cảm, rate limit và audit. Có thể khác cách biểu diễn token hoặc scope, nhưng khác biệt phải được thiết kế và kiểm chứng.

## 16. Quan sát việc sử dụng hợp đồng cũ

Không thể gỡ hợp đồng cũ an toàn nếu không biết ai còn dùng nó. Telemetry nên có:

| Metric/Log | Mục đích |
|---|---|
| request_count theo api_version | Đếm lưu lượng v1/v2 |
| unique consumer/service ID | Xác định đơn vị còn gọi v1 |
| response status/error mapping | Phát hiện consumer bị phá trong canary |
| event_count theo event_version | Theo dõi producer phát v1/v2 |
| consumer lag / dead-letter | Phát hiện consumer không đọc được event |
| fallback_count | Biết bao nhiêu request mới vẫn phải quay về đường cũ |
| mismatch_count của dữ liệu | Theo dõi backfill và đồng bộ hai schema |
| deployment version / image digest | Gắn lỗi với artifact thực tế |
| correlation ID / trace ID | Theo dấu request qua hai bản dịch vụ |

Tránh gắn userId hoặc orderId trực tiếp làm label Prometheus có cardinality rất cao. Các ID này phù hợp hơn trong log/trace có kiểm soát. Metric label nên là các giá trị hữu hạn như api_version, consumer_name đã chuẩn hóa hoặc service_version theo nhóm.

### 16.1. Tiêu chí gỡ hợp đồng cũ

Một điều kiện thực dụng cần xác nhận đồng thời:

- Không còn consumer được hỗ trợ nào phụ thuộc v1 theo inventory và telemetry.
- Mốc deprecation/sunset đã được công bố và đáp ứng cam kết.
- Các kịch bản rollback không còn đòi hỏi binary hoặc schema cũ.
- Backfill và kiểm tra nhất quán dữ liệu đã hoàn tất.
- Event v1 trong backlog/replay vẫn có đường xử lý hoặc đã hết thời gian cần hỗ trợ.
- Test của contract mới và kế hoạch thu hồi endpoint cũ đã sẵn sàng.
- Có owner phê duyệt và kế hoạch xử lý consumer ngoài dự kiến.

Không dựa vào một ngày không có traffic để kết luận mọi client đã nâng cấp; có thể tồn tại batch job hàng tuần, client offline hoặc disaster-recovery path ít chạy.

## 17. Kiểm thử hợp đồng trong CI/CD

Bộ kiểm thử cần bao phủ những **tổ hợp được kỳ vọng xảy ra** trong rollout, chứ không chỉ test code mới với code mới.

### 17.1. Kiểm thử API

- Provider v2 với contract do consumer v1 công bố.
- Provider v2 với contract của consumer v2.
- Consumer v2 với provider v1 nếu trình tự rollout hoặc rollback có thể tạo tổ hợp này.
- Các nhánh success, validation error, auth error, timeout, retry và idempotency.
- Response có trường mới, trường optional thiếu, enum mới và payload không hợp lệ.

Consumer-driven contract test (ví dụ Pact) và OpenAPI diff hữu ích để phát hiện thay đổi cấu trúc. Với thay đổi ngữ nghĩa hoặc side effect, cần thêm integration test và workflow test.

### 17.2. Kiểm thử event

- Consumer v1 đọc payload v2 nếu trong giai đoạn transition có thể nhận event mới.
- Consumer v2 đọc payload v1 từ backlog hoặc replay.
- Cả hai event version phát cùng lúc không gây double-processing.
- Thông điệp malformed, duplicate, out-of-order, timeout và dead-letter được xử lý có kiểm soát.
- Mọi schema revision được ghi rõ cùng producer/consumer version.

### 17.3. Kiểm thử persistence

- Binary cũ trên schema đã Expand.
- Binary mới đọc các row chưa backfill và đã backfill.
- Hai writer khác version ghi xen kẽ mà không mất dữ liệu.
- Rollback binary sau khi có dữ liệu từ bản mới.
- Migration chạy lặp lại và dừng/tiếp tục không làm hỏng dữ liệu.

Dùng môi trường tạm thời hoặc database riêng cho test; không reset bảng production hoặc dữ liệu chia sẻ vì mục đích kiểm thử.

### 17.4. Kiểm thử triển khai

Một kịch bản canary/rolling test có thể gồm:

~~~text
1. Dựng Provider v1 + Consumer v1.
2. Kiểm tra luồng nghiệp vụ nền.
3. Bật thêm Provider v2, duy trì Provider v1.
4. Kiểm tra Consumer v1 trên cả đường route.
5. Hoàn tất chuyển provider sang v2.
6. Bật Consumer v2 theo nhóm.
7. Kiểm tra success/error/retry với hợp đồng v2.
8. Thử rollback consumer nếu được cam kết.
9. Thu report, log, trace và dọn môi trường.
~~~

Khi test phụ thuộc routing version, phải xác minh traffic thật sự đến version đã khai báo. “Test PASS” với pod v2 duy nhất không chứng minh giai đoạn mixed pods an toàn.

## 18. Rollback trong giai đoạn hai hợp đồng

Rollback là khả năng quay lại một trạng thái hoạt động đã được kiểm chứng, không chỉ lệnh triển khai image cũ.

| Điều đã thay đổi | Nguy cơ rollback | Cách kiểm soát |
|---|---|---|
| Provider thêm API v2 | Consumer mới không còn endpoint khi provider về v1 | Rollback consumer trước, hoặc giữ route/provider tương thích |
| Database đã ghi format mới | Binary cũ không đọc được dữ liệu mới | Expand schema và kiểm thử old reader |
| Event v2 đã vào broker | Consumer v1 không hiểu event đã tồn tại | Hỗ trợ đọc v2, translator hoặc đường cách ly |
| Feature flag ON | Dữ liệu mới/side effect được tạo | Xác định điều kiện tắt flag và hành vi workflow đang dở |
| Auth scope mới | Token cũ/mới không trao đổi được | Giữ chính sách chuyển tiếp và key rotation |
| Dual-write chưa hội tụ | Hai nguồn dữ liệu mâu thuẫn | Quy tắc ưu tiên, đối soát và kế hoạch repair |

Nếu đã thực hiện migration phá hủy và data không còn đọc được bởi binary cũ, có thể phải **roll forward** bằng bản sửa mới thay vì rollback. Quyết định này cần được chuẩn bị trước trong runbook phát hành.

## 19. Runbook triển khai an toàn: ví dụ Payment API v1 → v2

Đây là kịch bản cụ thể cho thay đổi hợp đồng ở ví dụ thanh toán. Các bước cần được chỉnh theo hạ tầng thực tế và bằng chứng từ ma trận tương thích.

### Pha A — Chuẩn bị

1. Xác định consumer còn dùng /v1/payments và người phụ trách từng consumer.
2. Công bố API v2, bao gồm đơn vị tiền, validation, error code và idempotency.
3. Thiết kế mapper v1/v2 → PaymentCommand chung.
4. Nếu cần storage migration, triển khai Expand trước và xác minh old binary vẫn hoạt động.
5. Viết contract test cho các consumer v1 và v2.
6. Bổ sung telemetry theo endpoint version/consumer, không làm lộ thông tin nhạy cảm.

### Pha B — Triển khai provider

1. Đưa Payment v2 lên staging/môi trường tạm với cả hai endpoint.
2. Chạy ma trận tương thích Payment v2 + Order v1; Payment v2 + Order v2.
3. Canary Payment v2 khi phần lớn traffic còn dùng /v1.
4. Theo dõi lỗi, độ trễ, idempotency và side effect; nếu không đạt ngưỡng thì dừng rollout theo runbook.
5. Hoàn tất rollout Payment v2; xác nhận không còn provider v1 nhận request API v2.
6. Giữ /v1 ổn định trong suốt thời gian còn consumer cũ.

### Pha C — Chuyển consumer

1. Nâng cấp Order/consumer theo nhóm nhỏ.
2. Bật gọi /v2 cho nhóm đã kiểm thử.
3. Theo dõi request_count của v1 và v2 theo consumer, error rate và fallback.
4. Chạy thử các nhánh nghiệp vụ quan trọng và khả năng rollback của consumer.
5. Cập nhật inventory khi mỗi consumer đã chuyển xong.

### Pha D — Kết thúc chuyển tiếp

1. Đợi đủ thời gian deprecation và xét các client ít hoạt động.
2. Xác nhận không còn consumer được hỗ trợ nào cần /v1.
3. Hoàn tất backfill/đối soát dữ liệu và kiểm tra backlog event nếu liên quan.
4. Gỡ flag, adapter v1 và compatibility code trong đợt phát hành riêng.
5. Chạy lại contract test và rollout với theo dõi riêng cho việc xóa v1.
6. Cập nhật tài liệu, SDK và trạng thái support.

Không trộn gỡ hợp đồng cũ vào cùng lần phát hành lần đầu mở đường mới nếu chưa có bằng chứng toàn bộ hệ thống đã chuyển.

## 20. Phân phối trách nhiệm giữa các nhóm

Trong hệ thống nhiều nhóm, tương thích không tự xảy ra chỉ nhờ service ownership. Cần có quy ước:

| Vai trò | Trách nhiệm chính |
|---|---|
| Provider owner | Công bố hợp đồng, bảo đảm đường chuyển tiếp, chạy provider verification |
| Consumer owner | Cung cấp consumer contract, nâng cấp client, xác nhận bỏ phụ thuộc cũ |
| Platform/SRE | Hỗ trợ routing, rollout, telemetry, rollback và môi trường kiểm thử |
| Data owner | Thiết kế migration, backfill, consistency check và chính sách retention |
| Release owner | Đối chiếu ma trận tương thích, ngưỡng release và mốc deprecation |

Các quyết định nên lưu ngay trong thay đổi kỹ thuật: contract revision, support window, migration order, release gate, rollback limit, metric/alert và lịch gỡ bỏ. Tránh để kế hoạch chỉ tồn tại trong trao đổi miệng.

## 21. Những mẫu thiết kế thường gặp

### 21.1. Adapter tại biên

Giữ cả hai phiên bản request/response, chuyển đổi về domain chung. Đây thường là cách bắt đầu phù hợp khi thay đổi hợp đồng giao tiếp.

### 21.2. Anti-corruption layer

Một dịch vụ/adapter cô lập ngữ nghĩa của hệ thống cũ khi cần giao tiếp với domain mới. Hữu ích khi hai mô hình dữ liệu có cách hiểu nghiệp vụ khác nhau và không thể chỉ đổi tên field.

### 21.3. Strangler migration

Dần chuyển nhóm endpoint/luồng từ implementation cũ sang implementation mới; có gateway hoặc dispatcher định tuyến phù hợp. Cần trạng thái sở hữu nghiệp vụ rõ ràng để tránh hai implementation cùng xử lý một lệnh có side effect.

### 21.4. Dual-read

Trong thời gian chuyển schema, đọc trường mới rồi fallback về trường cũ khi cần. Phải đo fallback rate và phân biệt dữ liệu thật sự trống với dữ liệu chưa migrate.

### 21.5. Shadow traffic

Gửi bản sao request đến implementation mới để so sánh kết quả mà chưa sử dụng response mới. Chỉ dùng với nhánh xử lý được cô lập side effect; không được phát sinh thanh toán, email hoặc ghi dữ liệu thật hai lần.

### 21.6. Versioned topic/event translator

Khi event semantics thay đổi lớn, dùng phiên bản sự kiện riêng và dịch qua adapter có kiểm soát. Theo dõi chặt event ID, replay, retention và duplicate processing.

Những mẫu này có thể kết hợp, nhưng mỗi lớp tương thích mới tạo thêm chi phí kiểm thử và vận hành. Luôn xác định điều kiện kết thúc để tránh giữ legacy path mãi mãi.

## 22. Các lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Biện pháp |
|---|---|---|
| Đổi required field khi consumer cũ vẫn đang chạy | Consumer lỗi parse/validation | Expand contract, giữ đường cũ |
| Provider v2 chỉ chạy một phần pod nhưng consumer đã gọi v2 | Request ngẫu nhiên rơi vào pod v1 | Hoàn tất provider rollout hoặc version-aware routing |
| Đổi ý nghĩa của field nhưng giữ tên | Sai nghiệp vụ âm thầm | Version semantics, test với số liệu biên |
| Xóa cột database trước khi old pod ngừng hoạt động | Old binary lỗi runtime | Expand–Migrate–Contract |
| Consumer mới không đọc event cũ | Replay/backlog thất bại | Test new reader + historical payload |
| Dual publish event không chống trùng | Nhân đôi side effect | Business idempotency, định tuyến rõ |
| Dual-write hai nơi không có đối soát | Dữ liệu lệch | Outbox/CDC, metrics và repair plan |
| Chỉ kiểm thử latest–latest | Không phát hiện mixed-version outage | Test ma trận active/candidate |
| Không phân biệt API version với service version | Routing và báo cáo sai | Lưu cả contract revision và image digest |
| Bật flag mà không có metric | Không biết ai đang dùng đường mới | Ghi version, consumer ID và rollout cohort |
| Sunset dựa vào suy đoán | Batch/mobile client cũ hỏng | Inventory + telemetry + support policy |
| Rollback chỉ hạ image | Binary cũ không đọc data/event mới | Kiểm thử rollback thật, sẵn phương án roll-forward |

## 23. Bài thực hành

**Tình huống:** Inventory Service v1 trả stockCount trong response GET /inventory/{sku}. Nhóm muốn chuyển sang availableQuantity và reservedQuantity trong v2. Order v1, Order v2 và hệ thống báo cáo batch vẫn còn hoạt động.

Hãy thực hiện:

1. Viết contract v1 và v2; làm rõ stockCount ở v1 có bằng availableQuantity ở v2 hay có quy tắc tính khác.
2. Lập inventory consumer và ma trận các cặp Order/Inventory đang cần hỗ trợ.
3. Thiết kế adapter trả response v1 dựa trên mô hình tồn kho nội bộ nhất quán; định nghĩa cách tính rõ ràng.
4. Xác định tác động đến event StockChanged và database schema nếu có.
5. Lập trình tự Expand → rollout Inventory v2 → nâng cấp Order/reporting → Contract.
6. Viết test cho response v1/v2, reservation, timeout, rollback và dữ liệu cũ.
7. Chọn metric cho lưu lượng v1, lỗi parse, số lần fallback và sai lệch đối soát.
8. Xác định điều kiện cụ thể để xóa v1 và hành vi nếu vẫn còn batch job gọi bản cũ.

**Câu hỏi suy luận:** Vì sao đổi tên stockCount có thể gây lỗi dù Inventory vẫn trả số nguyên? Vì tên field và ngữ nghĩa được consumer sử dụng là một phần của hợp đồng; đổi tên làm parser/mapper cũ thiếu trường, còn đổi cách tính có thể gây sai nghiệp vụ ngay cả khi parse được.

## 24. Checklist phát hành khi hai hợp đồng cùng tồn tại

- [ ] Đã xác định API/event/storage contract cũ và mới, gồm cả ý nghĩa dữ liệu.
- [ ] Đã liệt kê consumer đang chạy và thời gian họ được hỗ trợ.
- [ ] Có ma trận các tổ hợp phiên bản có thể xảy ra trong rollout và rollback.
- [ ] Provider mới có thể phục vụ consumer cũ trong giai đoạn chuyển tiếp.
- [ ] Consumer mới có đường tương thích với provider/event cũ khi cần.
- [ ] Nếu có shared database, schema Expand tương thích với binary cũ và mới.
- [ ] Migration, backfill, dual-read/dual-write và đối soát được thiết kế có điều kiện kết thúc.
- [ ] Event cũ/mới và replay được kiểm thử; side effect trùng có cơ chế ngăn chặn.
- [ ] Gateway/mesh/service discovery route request đúng phiên bản hỗ trợ.
- [ ] Feature flag có owner, telemetry và phương án tắt an toàn.
- [ ] Auth, retry, timeout, idempotency và error mapping đã được kiểm tra cho cả hai hợp đồng.
- [ ] CI kiểm thử các tổ hợp bắt buộc, lưu image digest và contract revision.
- [ ] Canary theo dõi cả lỗi kỹ thuật và kết quả nghiệp vụ.
- [ ] Rollback đã được thực hành hoặc ghi rõ giới hạn và phương án roll-forward.
- [ ] Có lịch deprecation, cách xác nhận hết consumer v1 và kế hoạch xóa legacy code.
- [ ] Documentation, SDK và release notes phản ánh thời gian cùng tồn tại của hai hợp đồng.

## 25. Kết luận

Triển khai khi hợp đồng cũ và mới cùng tồn tại là công việc phối hợp giữa thiết kế API, dữ liệu, message, kiểm thử và vận hành. Một đợt release an toàn tạo được **khoảng thời gian tương thích có chủ đích**: mở rộng khả năng phục vụ trước, chuyển từng consumer theo bằng chứng, quan sát các tổ hợp mixed-version, rồi mới loại bỏ đường cũ.

Trong Microservices, tính độc lập khi phát hành đến từ **hợp đồng được quản lý theo thời gian**, không chỉ từ việc chia code thành nhiều dịch vụ. Giữ adapter mỏng, mô hình nghiệp vụ thống nhất, cơ chế kiểm tra có bằng chứng và kế hoạch sunset rõ ràng giúp nhóm triển khai liên tục mà vẫn duy trì hành vi ổn định cho các phiên bản đang hoạt động.