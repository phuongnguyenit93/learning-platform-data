# Idempotency key và xử lý yêu cầu lặp

Trong hệ thống API, một yêu cầu có thể được gửi nhiều lần dù người dùng chỉ nhấn nút một lần. Mạng bị ngắt sau khi server đã ghi dữ liệu nhưng trước khi response đến client; ứng dụng di động tự retry; API gateway hoặc SDK gửi lại request sau timeout; một webhook được nhà cung cấp phát lại vì chưa nhận được acknowledgement. Nếu mỗi lần nhận đều tạo một giao dịch mới, khách hàng có thể bị đặt lịch hai lần, trừ tiền hai lần hoặc tạo nhiều đơn hàng giống nhau.

**Idempotency** là thuộc tính giúp một thao tác có thể được thực hiện lặp lại mà kết quả quan sát được vẫn tương đương với một lần thực hiện theo quy tắc đã định. Với API tạo tài nguyên hoặc thực hiện hành động có side effect, một **idempotency key** là mã do client hoặc hệ thống gọi cung cấp để nhận diện cùng một ý định nghiệp vụ. Server dùng khóa đó cùng phạm vi và dữ liệu yêu cầu để nhận ra request lặp, tránh thực hiện side effect lần nữa và trả lại kết quả phù hợp.

Idempotency đặc biệt quan trọng trong kiến trúc cloud vì API thường chạy nhiều instance, function có thể nhận sự kiện lặp, load balancer có thể chuyển request sang backend khác và các tầng retry có thể hoạt động độc lập. Một biến trong RAM của một instance không thể bảo vệ toàn bộ hệ thống. Cơ chế chống lặp phải có **phạm vi dùng chung, tính nguyên tử và khả năng phục hồi**.

Bài học thuộc phần **Kiến trúc API** trong học phần thiết kế kiến trúc đám mây. Mục tiêu là biến yêu cầu nghiệp vụ thành API và mô hình dữ liệu có thể vận hành tin cậy, đồng thời cân bằng tính đúng đắn, bảo mật, khả năng mở rộng, chi phí và khả năng quan sát theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Giải thích idempotency và phân biệt nó với retry, deduplication và exactly-once delivery.
- Thiết kế idempotency key theo tenant, operation và phạm vi nghiệp vụ.
- Xử lý request đồng thời, timeout và kết quả không rõ ràng bằng trạng thái bền vững và transaction.
- Phân biệt cùng key/cùng payload với cùng key/khác payload.
- Chọn thời gian lưu khóa, response replay, trạng thái đang xử lý và chính sách lỗi.
- Áp dụng idempotency cho HTTP API, webhook, queue consumer và workflow có side effect.
- Kiểm thử, quan sát và đánh giá chính sách chống yêu cầu lặp trước production.

## 1. Vì sao yêu cầu bị lặp?

Client không phải lúc nào cũng biết server đã hoàn tất thao tác hay chưa. Hãy xét luồng tạo lịch hẹn:

1. Khách hàng gửi POST để đặt lịch lúc 10:00.
2. Server ghi booking thành công vào database.
3. Kết nối mạng bị đứt trước khi response thành công đến điện thoại.
4. Client không biết booking đã được tạo và gửi lại POST.
5. Server nhận request thứ hai và có thể tạo booking khác.

Từ góc nhìn người dùng, lần đầu tiên “không có phản hồi”. Từ góc nhìn server, lần đầu đã thành công. Đây là **ambiguous outcome** — kết quả không rõ ràng đối với bên gọi.

Các nguồn tạo request trùng thường gặp:

| Nguồn | Tình huống | Rủi ro |
| --- | --- | --- |
| Người dùng | Nhấn nút hai lần, refresh hoặc mở nhiều tab | Tạo nhiều tài nguyên |
| Mobile/web client | Retry sau timeout, mất mạng hoặc app resume | Không biết request trước đã commit hay chưa |
| SDK / HTTP client | Retry tự động theo policy | Gửi lại POST có side effect |
| API gateway / proxy | Retry hoặc chuyển backend sau lỗi kết nối | Request trước có thể đã đến application |
| Webhook provider | Phát lại event vì chưa nhận acknowledgement | Xử lý một event nhiều lần |
| Queue/event broker | Redelivery khi consumer timeout hoặc không ack | Side effect lặp |
| Workflow engine | Chạy lại bước sau lỗi hoặc khôi phục execution | Gọi lại external service |
| Nhân viên vận hành | Bấm chạy lại job hoặc replay message | Tái thực hiện thao tác cũ |

Không phải mọi request lặp đều là lỗi. Người dùng có thể chủ động mua hai sản phẩm giống nhau; hai lần đặt lịch khác key có thể là hai ý định thật. Mục tiêu là phân biệt **một ý định được gửi nhiều lần** với **nhiều ý định độc lập**.

## 2. Idempotent khác retry và exactly-once như thế nào?

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Không bảo đảm điều gì |
| --- | --- | --- |
| **Idempotency** | Lặp thao tác cùng một ý định không tạo thêm kết quả nghiệp vụ ngoài quy tắc | Không tự làm request thành công, cũng không giải quyết mọi lỗi phân tán |
| **Retry** | Gửi lại thao tác khi gặp lỗi được xem là có thể phục hồi | Không biết chắc thao tác trước đã thực hiện hay chưa |
| **Deduplication** | Nhận diện và bỏ qua thông điệp/request đã thấy theo một khóa và thời hạn | Không bảo đảm hai side effect ngoài hệ thống cùng commit nguyên tử |
| **At-least-once delivery** | Hệ thống giao ít nhất một lần, có thể giao lặp | Không bảo đảm chỉ một lần xử lý |
| **At-most-once delivery** | Hệ thống không giao lặp theo semantics được công bố | Có thể mất thao tác nếu lỗi xảy ra |
| **Exactly-once effect** | Kết quả nghiệp vụ có hiệu lực đúng một lần trong một phạm vi xác định | Không thể suy ra chỉ từ queue hoặc transport; cần cơ chế phối hợp dữ liệu và side effect |

Một thao tác có tính idempotent về mặt HTTP có thể được gửi lại mà không tạo thêm tác dụng phụ. Ví dụ PUT đặt trạng thái tài nguyên thành giá trị cụ thể và DELETE xóa cùng một tài nguyên thường được thiết kế idempotent theo semantics HTTP. POST tạo giao dịch thường không idempotent nếu không có cơ chế riêng.

**Idempotency key không phải công tắc exactly-once toàn hệ thống.** Nó giúp server nhận diện các lần gửi lại của cùng ý định trong một phạm vi và khoảng thời gian. Cơ sở dữ liệu, message broker và dịch vụ bên ngoài vẫn có thể có ranh giới transaction, retry và failure riêng.

## 3. Chọn key và xác định phạm vi

Một idempotency key cần phân biệt được một ý định nghiệp vụ và tránh xung đột giữa các caller. Có thể là UUID ngẫu nhiên, token do client tạo hoặc mã operation do server cấp trước.

Ví dụ request:

~~~http
POST /v1/bookings
Authorization: Bearer <access-token>
Idempotency-Key: 3d7f5d6a-7d50-4f5b-9d5b-1e4b9b2a6f81
Content-Type: application/json

{
  "doctorId": "doc-42",
  "slotId": "slot-2026-11-18-1000"
}
~~~

Key trong ví dụ chỉ minh họa định dạng. Không sử dụng access token, email, số thẻ hoặc dữ liệu cá nhân làm key. Key không phải credential và không thay thế xác thực hay phân quyền.

### 3.1. Phạm vi duy nhất của key

Chỉ dùng key làm khóa duy nhất toàn hệ thống có thể gây va chạm hoặc rò rỉ kết quả giữa caller. Phạm vi thường cần kết hợp:

- **Principal hoặc tenant:** khách hàng, merchant, API client hay tổ chức đã xác thực.
- **Operation:** loại thao tác, endpoint hoặc hành động nghiệp vụ.
- **Key:** mã ý định do caller cung cấp.

Một định danh logic có thể là:

~~~text
scope = tenant_id + operation_name + idempotency_key
~~~

Ví dụ tenant A và tenant B cùng vô tình dùng chuỗi key request-001, chúng phải được coi là hai phạm vi độc lập. Đồng thời, cùng tenant dùng cùng key cho CreateBooking và CancelBooking không nhất thiết là cùng ý định.

Chọn phạm vi cụ thể:

| Thành phần scope | Câu hỏi |
| --- | --- |
| Tenant/principal | Ai là chủ thể của ý định? Key có được dùng chung giữa người dùng trong tổ chức không? |
| Operation | Cùng key trên hai endpoint có được coi là cùng thao tác không? |
| Resource/account | Có cần giới hạn trong một tài khoản thanh toán hoặc một đơn hàng không? |
| Environment | Key của sandbox có thể đụng với production không? |
| Version | Thay đổi semantics API có yêu cầu một namespace/version mới không? |

Scope phải ổn định trong suốt vòng đời retry. Không suy scope từ header do client chưa xác thực kiểm soát. Server cần lấy tenant/principal từ danh tính đã xác minh.

### 3.2. Sinh key ở client hay server?

Với API mà client gửi lại request sau timeout, client thường tạo key **trước lần gửi đầu tiên** rồi giữ nguyên key cho các lần retry của cùng ý định. Nếu mỗi lần retry lại tạo UUID mới, server sẽ thấy các thao tác độc lập và không thể deduplicate.

Với webhook, provider thường cung cấp event ID hoặc delivery ID. Server có thể dùng ID đó làm một phần idempotency scope sau khi xác thực chữ ký và nguồn phát.

Với job nội bộ, scheduler/workflow có thể cấp operation ID bền vững, không tạo ID mới khi retry cùng một bước.

Key nên có độ khó đoán đủ tốt để tránh xung đột và enumeration. Nhưng **độ ngẫu nhiên của key không thay thế kiểm soát quyền**. Một caller chỉ được xem hoặc replay kết quả thuộc phạm vi dữ liệu mà principal đó có quyền truy cập.

### 3.3. Một key gắn với một nội dung request

Server nên tính fingerprint/hash từ các trường có ý nghĩa nghiệp vụ của request sau khi chuẩn hóa. Không nên hash toàn bộ raw JSON một cách ngây thơ, vì thứ tự field, whitespace, header hoặc metadata không ảnh hưởng nghiệp vụ có thể khác.

Ví dụ fingerprint có thể tính từ:

~~~text
SHA-256(
  API operation version
  + normalized doctor_id
  + normalized slot_id
  + relevant booking options
)
~~~

Không đưa secret, bearer token hoặc dữ liệu không cần thiết vào fingerprint. Nếu payload nhạy cảm, tránh lưu nguyên body; chỉ lưu hash và kết quả tối thiểu cần replay.

**Cùng scope + cùng key + cùng fingerprint:** đây có thể là retry của cùng ý định.

**Cùng scope + cùng key + fingerprint khác:** từ chối hoặc báo xung đột. Không được âm thầm coi payload mới là request cũ và trả kết quả không liên quan.

## 4. Quy trình xử lý request với idempotency key

Một luồng phổ biến gồm bốn trạng thái logic:

1. **Chưa có record:** key chưa được dùng trong scope.
2. **In progress:** một request đã giành quyền xử lý key; các request cùng key cần được xử lý theo policy chờ hoặc trả kết quả tạm thời.
3. **Completed:** side effect đã hoàn tất và kết quả được lưu; retry cùng nội dung có thể nhận lại kết quả.
4. **Failed/retryable hoặc terminal:** xử lý thất bại; policy quyết định có cho phép thử lại, giữ nguyên lỗi hay yêu cầu key mới.

~~~mermaid
flowchart TD
    A["Nhận request và xác thực"] --> B["Tính scope + key + fingerprint"]
    B --> C{"Có idempotency record?"}
    C -- "Không" --> D["Atomic claim key"]
    D --> E{"Claim thành công?"}
    E -- "Không" --> C
    E -- "Có" --> F["Thực hiện transaction nghiệp vụ"]
    F --> G["Lưu kết quả và đánh dấu completed"]
    G --> H["Trả response"]
    C -- "Có, fingerprint khác" --> X["409 Conflict"]
    C -- "Có, đang xử lý" --> Y["Chờ hoặc trả trạng thái in progress"]
    C -- "Có, đã hoàn tất" --> Z["Kiểm tra quyền và replay kết quả"]
~~~

Sơ đồ là mô hình logic; cách khóa, transaction, thời gian chờ và trạng thái lỗi phải được định nghĩa cho hệ thống cụ thể.

### Response cho request lặp

Khi key đã completed và fingerprint trùng, API thường trả lại kết quả đã lưu. Có thể lưu:

- HTTP status code.
- Response body hoặc reference đến tài nguyên đã tạo.
- Một số header cần thiết như Location, resource ID hoặc version.
- Thời điểm hoàn tất và operation ID.

Không nhất thiết phải lưu toàn bộ header response. Tránh lưu header chứa credential, cookie hoặc thông tin thay đổi theo từng lần gọi. Quy định rõ response replay có giữ nguyên status/body ban đầu hay phản ánh trạng thái mới nhất của resource.

Ví dụ: request tạo booking đầu tiên trả 201 cùng booking ID. Retry có thể nhận lại booking ID đó, theo hợp đồng API có thể trả lại 201 ban đầu hoặc một status khác được tài liệu hóa như 200. Điều quan trọng là **không tạo booking thứ hai** và client hiểu cách diễn giải response.

### Request cùng key nhưng đang xử lý

Hai request đến gần như đồng thời có thể cùng kiểm tra “chưa có key” trước khi record được ghi nếu thiết kế không nguyên tử. Cần một thao tác **atomic claim** dựa trên unique constraint, conditional write hoặc primitive khóa thích hợp.

Nếu request thứ hai gặp record IN_PROGRESS, API có thể:

- Trả 409/202 kèm operation status hoặc Retry-After theo hợp đồng.
- Chờ trong giới hạn ngắn để request đầu hoàn tất, sau đó replay.
- Trả lỗi tạm thời để client retry cùng key sau một khoảng thời gian.

Không giữ một transaction hoặc database lock mở trong thời gian dài chỉ để chờ external API. Điều đó dễ làm cạn connection và lock. Workflow dài nên chuyển sang mô hình operation resource và xử lý bất đồng bộ.

## 5. Lưu record idempotency bền vững và nguyên tử

Record chống lặp cần tồn tại ở nơi các instance đều truy cập được. Dùng biến static, local cache hoặc file trong container làm nguồn dữ liệu duy nhất sẽ thất bại khi request tiếp theo đến instance khác hoặc môi trường được thay mới.

Một schema quan hệ minh họa:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_name     VARCHAR(120) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64) NOT NULL,
    state              VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    resource_id        VARCHAR(120),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Schema là ví dụ khái niệm. Database, độ dài key, kiểu JSON, index và chính sách lưu dữ liệu phải phù hợp với engine và tải thật. Response body có thể chứa dữ liệu nhạy cảm nên cần minimization, encryption, retention và quyền truy cập riêng.

### 5.1. Claim key bằng unique constraint

Mẫu thực thi đơn giản:

1. Xác thực request và kiểm tra input.
2. Chuẩn hóa payload, tạo fingerprint và scope.
3. Thử insert record IN_PROGRESS.
4. Nếu insert thành công, request hiện tại sở hữu lần xử lý.
5. Nếu vi phạm unique key, đọc record hiện hữu, so sánh fingerprint và trạng thái.
6. Chỉ một request có thể claim khóa theo constraint; các request đồng thời còn lại không chạy side effect lần nữa.

Ví dụ SQL minh họa:

~~~sql
INSERT INTO idempotency_record (
    tenant_id, operation_name, idempotency_key,
    request_hash, state, expires_at
)
VALUES (
    :tenant_id, :operation, :key,
    :request_hash, 'IN_PROGRESS', :expires_at
)
ON CONFLICT DO NOTHING;
~~~

Ứng dụng phải kiểm tra số dòng được insert. Nếu không insert được, đọc record hiện tại trong transaction phù hợp và quyết định replay, conflict hay in-progress. Việc insert và thao tác nghiệp vụ cần được phối hợp để xử lý crash đúng.

### 5.2. Ghi idempotency record cùng transaction nghiệp vụ

Nếu booking và idempotency record nằm trong **cùng một database**, phương án mạnh là commit cả hai trong một transaction:

~~~text
BEGIN
  claim idempotency key
  validate business constraints
  create booking
  save response/resource reference
  mark idempotency record COMPLETED
COMMIT
~~~

Nếu transaction rollback, booking và record claim cùng rollback; request retry có thể thử lại. Nếu commit thành công nhưng response bị mất, record completed giúp request sau replay kết quả.

Tuy nhiên, không phải lúc nào toàn bộ side effect nằm trong một database transaction. Gửi email, gọi cổng thanh toán hoặc publish đến broker là side effect bên ngoài, không thể tự động commit nguyên tử cùng transaction database thông thường.

### 5.3. Dùng outbox cho side effect bất đồng bộ

Với booking cần phát event để gửi thông báo, cùng transaction có thể ghi booking, idempotency record và một outbox event. Worker relay đọc outbox rồi phát message. Consumer có inbox/dedup record riêng để chống xử lý trùng.

~~~mermaid
flowchart LR
    API["API request"] --> TX["Database transaction"]
    TX --> BOOK["Booking row"]
    TX --> IDEM["Idempotency completed"]
    TX --> OUT["Outbox event"]
    OUT --> RELAY["Outbox relay"]
    RELAY --> Q["Queue / event bus"]
    Q --> CONSUMER["Consumer"]
    CONSUMER --> INBOX["Inbox / processed event ID"]
    INBOX --> EFFECT["External side effect"]
~~~

Outbox giải quyết khoảng trống giữa commit database và phát event, nhưng relay vẫn có thể phát lặp nếu đã gửi message rồi chết trước khi đánh dấu outbox sent. Consumer vẫn phải idempotent. Đây là **chống lặp ở từng ranh giới**, không phải bảo đảm exactly-once xuyên mọi dịch vụ.

## 6. Xử lý failure và kết quả không rõ ràng

Thiết kế idempotency cần trả lời điều gì xảy ra nếu tiến trình chết ở từng thời điểm:

| Thời điểm lỗi | Trạng thái có thể còn lại | Cách xử lý |
| --- | --- | --- |
| Trước khi claim key | Chưa có record | Retry cùng key có thể bắt đầu |
| Sau claim nhưng trước transaction nghiệp vụ | Record IN_PROGRESS nếu claim nằm ngoài transaction | Có lease/timeout để phục hồi record mồ côi |
| Trong transaction trước commit | Transaction rollback nếu database thực thi đúng | Retry dựa trên record/constraint |
| Sau commit, trước khi gửi response | Nghiệp vụ đã hoàn tất, response chưa đến client | Replay kết quả lưu trong record |
| Sau khi gọi external provider, trước khi lưu kết quả | Provider có thể đã thực hiện side effect | Dùng provider idempotency key hoặc reconciliation |
| Sau khi phát message, trước khi đánh dấu outbox sent | Message có thể được phát lại | Consumer dedup theo event ID |
| Trong consumer, sau side effect trước ack | Side effect có thể đã xảy ra, message sẽ redeliver | Inbox/transaction hoặc provider idempotency |

### Record IN_PROGRESS bị bỏ quên

Nếu claim được commit riêng trước khi xử lý, process có thể chết và để lại record IN_PROGRESS mãi mãi. Một số chiến lược:

- **Lease:** record có thời hạn sở hữu và heartbeat/renewal; sau lease có thể được tiếp quản theo điều kiện.
- **Attempt token/fencing:** mỗi lần sở hữu có token tăng dần; worker cũ không được ghi kết quả sau khi quyền sở hữu đã chuyển.
- **Recovery worker:** quét record quá hạn, đối chiếu trạng thái nghiệp vụ rồi quyết định tiếp tục, hoàn tất hoặc chuyển sang needs-review.
- **Transaction chung:** khi side effect chính nằm cùng database, giữ claim và nghiệp vụ trong một transaction để tránh record mồ côi.

Không được chỉ xóa record IN_PROGRESS quá tuổi rồi cho retry mù quáng. Side effect có thể đã xảy ra ở hệ thống bên ngoài nhưng kết quả chưa được ghi nhận. Trước khi thử lại cần đối chiếu provider hoặc tài nguyên nghiệp vụ.

### External provider có idempotency riêng

Khi gọi cổng thanh toán, dùng cùng operation key cho provider nếu API đó hỗ trợ. Lưu provider reference và kết quả. Khi timeout, tra cứu transaction theo reference/key trước khi phát lệnh thanh toán mới.

Không dùng key mới mỗi lần retry đến provider. Làm như vậy biến một ý định thanh toán thành nhiều giao dịch độc lập.

Nếu provider không có idempotency hoặc lookup đáng tin cậy, thiết kế cần reconciliation, trạng thái chờ xác minh và quy trình xử lý thủ công cho kết quả không chắc chắn. Không thể giải quyết mọi trường hợp chỉ bằng cách retry.

## 7. TTL, retention và tái sử dụng key

Idempotency record không cần lưu mãi mãi trong mọi hệ thống, nhưng xóa quá sớm có thể cho phép side effect lặp lại khi client retry muộn.

Thời gian giữ cần dựa trên:

- Thời gian retry tối đa từ client, gateway, SDK và job.
- Thời gian redelivery/replay từ queue hoặc webhook provider.
- Cửa sổ khôi phục workflow và thời gian nhân viên có thể replay tác vụ.
- Nghĩa vụ kiểm toán và nhu cầu tra soát giao dịch.
- Dung lượng bảng, tốc độ tăng record và chi phí đọc/ghi/xóa.

Ví dụ, nếu webhook provider có thể retry trong 72 giờ và vận hành cho phép replay trong 7 ngày, retention 24 giờ là không đủ. Có thể giữ response đầy đủ ngắn hơn và giữ tombstone/hash lâu hơn, miễn logic xử lý không cho key hết hạn bị tái sử dụng ngoài ý muốn.

### Hết TTL có nghĩa gì?

Sau thời hạn chống lặp, hệ thống có thể:

- Xóa record hoàn toàn, khi nghiệp vụ chấp nhận rằng request gửi lại rất muộn có thể được coi là thao tác mới.
- Chuyển sang tombstone tối giản, giữ scope/key/hash và trạng thái để chặn key cũ nhưng xóa body nhạy cảm.
- Duy trì resource ID và trạng thái nghiệp vụ lâu dài nếu đó là bằng chứng cần cho tra soát.

TTL của record chống lặp **không phải** thời gian tồn tại của booking hay thanh toán. Hai vòng đời có mục tiêu khác nhau.

### Key hết hạn và client gửi lại

Hợp đồng API cần nói rõ cửa sổ idempotency. Ví dụ “cùng key được nhận diện trong tối thiểu 24 giờ kể từ lần claim đầu; sau cửa sổ này client không được tái sử dụng key cho thao tác mới”. Với giao dịch tài chính, cần retention và đối soát dài hơn theo yêu cầu nghiệp vụ.

Nếu key hết hạn trong khi operation vẫn IN_PROGRESS, không được đơn giản xóa và chấp nhận request mới. Phải giải quyết trạng thái operation trước.

## 8. Bảo mật và quyền riêng tư

Idempotency store có thể chứa tenant ID, hash payload, resource reference, response và trạng thái giao dịch. Đây là dữ liệu có thể quan trọng về nghiệp vụ hoặc nhạy cảm.

Các nguyên tắc cần áp dụng:

1. **Authenticate trước khi truy cập record:** không cho người chưa xác thực dò key để biết operation có tồn tại.
2. **Scope theo principal/tenant:** không replay response của tenant khác dù key trùng.
3. **Authorize lại tài nguyên:** idempotency record không thay thế kiểm tra quyền xem booking/transaction.
4. **Không dùng key làm bearer secret:** ai biết key cũng không được mặc nhiên xem kết quả.
5. **Giới hạn key size/format:** tránh payload lớn, ký tự điều khiển hoặc dữ liệu làm tăng chi phí index.
6. **Rate limit:** chống dò key, spam record và tấn công làm đầy storage.
7. **Minimize response storage:** ưu tiên resource ID hoặc kết quả tối thiểu; mã hóa và đặt retention phù hợp nếu cần lưu body.
8. **Log an toàn:** có thể log hash/truncated identifier để trace, tránh ghi nguyên payload hoặc dữ liệu nhạy cảm.
9. **Phân quyền idempotency store:** chỉ service cần thiết được đọc/ghi; audit hành động quản trị và xóa.

Nếu API hỗ trợ key cho thanh toán hoặc dữ liệu nhạy cảm, cần review threat model và chính sách retention riêng.

## 9. Idempotency trong các loại API và event

### HTTP API tạo tài nguyên

POST thường tạo resource mới. Key giúp client retry cùng ý định tạo và nhận lại cùng resource ID. Server cần ràng buộc key theo principal và operation.

### API cập nhật trạng thái

PUT đặt resource về một trạng thái xác định thường đã idempotent về semantics. Nhưng các side effect phụ như phát email, tăng counter hoặc gửi event vẫn có thể lặp. Cần kiểm tra toàn bộ hành vi, không chỉ câu lệnh cập nhật chính.

### Webhook

Dùng event ID từ nhà phát hành trong scope gồm provider/account/event type. Xác thực chữ ký trước khi tin event ID. Lưu event processed cùng kết quả xử lý hoặc đưa vào inbox table. Event ID khác nhau có thể vẫn biểu diễn cùng một nghiệp vụ; khi cần, dedup theo business key bổ sung.

### Queue consumer

Message có thể redeliver. Consumer cần ghi nhận event ID đã xử lý, kết hợp transaction nghiệp vụ nếu có thể. Chỉ ACK sau khi trạng thái xử lý bền vững được lưu theo semantics của broker.

### Workflow nhiều bước

Mỗi bước cần operation ID ổn định. Nếu workflow retry một bước gọi provider, dùng cùng key cho operation đó. Với saga, mỗi hành động và compensation có ID riêng; compensation không phải là xóa lịch sử side effect.

### Batch import

Dùng source record ID hoặc file ID + row ID để nhận diện dòng đã áp dụng. Cần định nghĩa hành vi khi file được tải lên lại với nội dung khác, cùng tên file hoặc version mới.

## 10. Thiết kế API contract cho idempotency

Một cơ chế tốt phải được công bố rõ cho client. Tài liệu endpoint nên quy định:

| Thành phần contract | Nội dung nên chỉ rõ |
| --- | --- |
| Header/key location | Tên header hoặc trường yêu cầu, format và giới hạn độ dài |
| Required or optional | Endpoint nào bắt buộc key, endpoint nào không cần |
| Scope | Principal, tenant, endpoint, operation hoặc account |
| Payload mismatch | Cùng key khác request body trả lỗi nào |
| Duplicate completed | Response replay có status/body/header ra sao |
| In-progress duplicate | Trả 409/202/Retry-After hay chờ trong bao lâu |
| Retention window | Thời hạn tối thiểu được bảo vệ và hành vi sau hết hạn |
| Error handling | Lỗi nào giữ key, lỗi nào cho thử lại, lỗi nào terminal |
| Client retry | Dùng lại đúng key, backoff và không tạo key mới cho cùng ý định |

### Ví dụ response

Request đầu tiên:

~~~http
HTTP/1.1 201 Created
Location: /v1/bookings/bkg-9281
Content-Type: application/json

{
  "bookingId": "bkg-9281",
  "status": "CONFIRMED"
}
~~~

Request lặp cùng scope, key và payload có thể trả lại kết quả:

~~~http
HTTP/1.1 201 Created
Location: /v1/bookings/bkg-9281
Content-Type: application/json

{
  "bookingId": "bkg-9281",
  "status": "CONFIRMED"
}
~~~

Request dùng lại key nhưng thay slot có thể trả:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "IDEMPOTENCY_KEY_REUSED",
  "message": "Key đã được sử dụng với nội dung yêu cầu khác."
}
~~~

Request đến khi operation đầu vẫn đang xử lý có thể nhận 202 hoặc 409 tùy hợp đồng. Nếu trả 202, cung cấp operation/status URL và hướng dẫn poll; nếu trả 409, ghi rõ đây là trạng thái đang xử lý và client nên retry cùng key sau khoảng thời gian được chỉ định.

Không trả body cũ trước khi xác thực và kiểm tra quyền hiện tại. Việc người dùng từng có quyền tạo operation không có nghĩa họ luôn có quyền xem kết quả.

## 11. Ví dụ triển khai: tạo booking trong một database transaction

Pseudocode dưới đây nhấn mạnh thứ tự logic. Nó không gắn với một framework hoặc engine cụ thể:

~~~text
function createBooking(principal, key, request):
    authorize(principal, "booking:create")
    normalized = normalizeBusinessFields(request)
    fingerprint = hash(normalized)
    scope = (principal.tenantId, "create-booking", key)

    begin transaction
        record = tryInsertIdempotency(scope, fingerprint)

        if record already exists:
            if record.requestHash != fingerprint:
                rollback
                return 409 IDEMPOTENCY_KEY_REUSED

            if record.state == COMPLETED:
                result = loadReplayResult(record)
                commit or rollback read transaction
                authorizeResult(principal, result)
                return result

            if record.state == IN_PROGRESS:
                rollback
                return 202 OPERATION_IN_PROGRESS

        booking = insertBookingWithBusinessConstraint(normalized)
        response = buildCreatedResponse(booking)
        saveReplayResult(scope, response, booking.id)
        markCompleted(scope)
    commit

    return response
~~~

Trong triển khai thực tế, cần giải quyết insert conflict trong concurrent transaction, isolation level, retry serialization/deadlock, dữ liệu response và việc cùng key gặp record IN_PROGRESS. Nếu record và booking cùng database, giữ các ghi thuộc nghiệp vụ trong transaction phù hợp sẽ giúp crash trước commit rollback toàn bộ.

## 12. Quan sát và vận hành cơ chế idempotency

Đừng chỉ đếm số key trong database. Cần biết cơ chế chống lặp có đang hoạt động và có tạo nghẽn hay không.

| Metric / log field | Mục đích |
| --- | --- |
| New key claims | Số ý định mới được nhận |
| Duplicate completed hits | Số request được replay thay vì thực hiện lại |
| Payload mismatch conflicts | Phát hiện client tái sử dụng key sai |
| In-progress conflicts | Đo request đồng thời hoặc operation xử lý lâu |
| Orphaned in-progress count/age | Tìm claim bị bỏ quên |
| Processing latency | Thời gian xử lý lần đầu và thời gian chờ duplicate |
| Replay latency | Độ trễ lấy và trả kết quả cũ |
| Expired/deleted record count | Theo dõi retention và cleanup |
| Provider reconciliation | Kết quả không chắc chắn cần đối chiếu |
| Duplicate side-effect incidents | Bằng chứng lỗi nghiệp vụ còn sót |

Log nên có tenant identifier đã bảo vệ, operation name, correlation ID và một dấu vết key đã hash hoặc rút gọn. Không log key đầy đủ nếu nó có thể giúp dò operation, và không log response nhạy cảm.

### Cảnh báo vận hành

- IN_PROGRESS vượt ngưỡng tuổi bình thường.
- Tỷ lệ payload mismatch tăng đột ngột.
- Duplicate hits tăng sau một đợt lỗi mạng hoặc deploy.
- Idempotency store latency, lock wait hoặc connection pool tăng.
- Storage tăng nhanh hoặc cleanup không chạy.
- Provider timeout tăng và reconciliation backlog tồn đọng.

Duplicate hit tăng không nhất thiết là sự cố; nó có thể phản ánh client retry hoạt động đúng. Cần so với timeout/error rate và duplicate side effect để hiểu ý nghĩa.

## 13. Kiểm thử idempotency

Kiểm thử một request được gửi hai lần tuần tự là chưa đủ. Race condition thường chỉ xuất hiện khi nhiều request đồng thời hoặc lỗi xảy ra đúng thời điểm commit.

Các nhóm test:

1. **Sequential duplicate:** gửi cùng key/body hai lần; chỉ có một resource hoặc side effect.
2. **Concurrent duplicate:** gửi cùng scope/key/body đồng thời từ nhiều client/instance; chỉ một request claim và xử lý.
3. **Payload mismatch:** cùng key nhưng một field nghiệp vụ thay đổi; server trả conflict.
4. **Cross-tenant collision:** hai tenant cùng chuỗi key; không chia sẻ kết quả hoặc dữ liệu.
5. **Timeout after commit:** server commit nhưng test client đóng kết nối trước khi nhận response; retry trả resource cũ.
6. **Crash before commit:** kill worker trong transaction; retry có thể xử lý lại mà không để dữ liệu dở dang.
7. **Crash after external side effect:** mô phỏng provider thành công nhưng function timeout; kiểm tra provider key hoặc reconciliation.
8. **In-progress timeout:** dừng process sau claim, kiểm tra lease/recovery và không tạo duplicate.
9. **TTL boundary:** retry trước/sau retention window; xác minh hành vi đúng hợp đồng.
10. **Authorization change:** thay đổi quyền giữa request đầu và replay; response không rò rỉ.
11. **Load test:** đo lock contention, record lookup, latency và storage growth ở tải đỉnh.
12. **Replay/recovery:** chạy lại webhook/message/job qua quy trình vận hành và xác nhận cùng kết quả.

### Ví dụ ma trận kết quả

| Lần gọi | Scope/key | Payload | Trạng thái trước | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| 1 | Tenant A / K1 | Slot 10:00 | Chưa có | Tạo booking B1 |
| 2 | Tenant A / K1 | Slot 10:00 | Completed | Replay B1 |
| 3 | Tenant A / K1 | Slot 11:00 | Completed | Conflict |
| 4 | Tenant B / K1 | Slot 10:00 | Chưa có trong scope B | Tạo booking B2 nếu hợp lệ |
| 5 | Tenant A / K2 | Slot 10:00 đồng thời với K3 | Chưa có | Một giao dịch thắng; giao dịch còn lại theo constraint nghiệp vụ bị từ chối |
| 6 | Tenant A / K1 | Slot 10:00 sau khi hết retention | Đã hết record | Hành vi theo policy; không được giả định replay vô hạn |

Test cần kiểm tra **số side effect trong datastore/provider**, không chỉ status code trả về. Hai request cùng nhận 200 nhưng tạo hai giao dịch vẫn là lỗi.

## 14. Những sai lầm thường gặp

**Tạo key mới mỗi lần retry.** Server nhìn thấy các ý định khác nhau và tạo side effect lần nữa. Client cần giữ nguyên key cho cùng thao tác.

**Lưu key trong memory của một instance.** Request kế tiếp có thể đến instance khác; scale-out và restart làm mất dedup state.

**Dùng key làm bằng chứng xác thực.** Người biết key không mặc nhiên có quyền xem kết quả. Phải xác thực principal và phân quyền tài nguyên.

**Không ràng buộc key với payload.** Cùng key, nội dung khác có thể bị trả nhầm kết quả hoặc thực hiện hành động ngoài ý muốn.

**Check-then-insert không nguyên tử.** Hai request cùng đọc “không tồn tại” rồi cùng thực hiện; cần unique constraint/conditional write/atomic claim.

**Ghi record và business data ở transaction riêng không có recovery.** Crash giữa hai bước có thể để record completed nhưng resource chưa tồn tại hoặc ngược lại.

**Gọi payment/email bên ngoài trong khi nghĩ database transaction bảo vệ tất cả.** External side effect có ranh giới riêng; cần provider idempotency, outbox, reconciliation hoặc workflow.

**Xóa IN_PROGRESS mù quáng.** Side effect có thể đã xảy ra trước khi process chết; cần xác minh trạng thái trước khi cho thực hiện lại.

**TTL quá ngắn.** Retry hoặc replay hợp lệ đến muộn có thể tạo side effect lần nữa.

**Giữ response chứa dữ liệu nhạy cảm vô thời hạn.** Response replay store phải có data minimization, access control, encryption và retention.

**Coi deduplication là exactly-once.** Dedup trong một database hoặc queue không tạo transaction toàn cục với mọi hệ thống ngoài.

## 15. Bài thực hành: API đặt lịch và thanh toán không tạo giao dịch trùng

**Bối cảnh giả định:** Một nền tảng đặt lịch có endpoint tạo booking và endpoint thanh toán. Mobile client gửi request qua API gateway; service chạy nhiều instance hoặc function. Một số client mạng yếu thường retry sau timeout. Booking được lưu trong relational database; thanh toán gọi payment provider bên ngoài. Provider hỗ trợ idempotency key trong phạm vi một merchant account và có API tra cứu transaction theo operation reference.

Yêu cầu bài tập:

- Cùng một ý định đặt lịch không tạo hai booking.
- Cùng một ý định thanh toán không bị charge hai lần khi retry.
- Hai tenant có thể dùng cùng chuỗi key mà không nhìn thấy kết quả của nhau.
- Request cùng key nhưng payload khác phải bị phát hiện.
- Nếu provider đã charge nhưng API timeout, hệ thống không gửi một lệnh charge mới với key khác.
- Record chống lặp được giữ đủ lâu cho retry, webhook replay và tra soát theo policy.

Các con số retention, RPS và thời hạn xử lý là giả định cần học viên lựa chọn; không có một giá trị chung đúng cho mọi provider hoặc nghiệp vụ.

### Nhiệm vụ

1. **Thiết kế scope và fingerprint:** xác định scope cho CreateBooking và CapturePayment. Nêu ai tạo key, format/entropy, cách giữ key qua retry và các trường nghiệp vụ dùng để fingerprint. Giải thích cùng key nhưng khác slot hoặc khác số tiền.
2. **Thiết kế schema và trạng thái:** vẽ schema idempotency record gồm tenant, operation, key, fingerprint, trạng thái, resource/provider reference, response tối thiểu, created/updated time và expires_at. Định nghĩa transition giữa IN_PROGRESS, COMPLETED, FAILED_RETRYABLE và FAILED_TERMINAL nếu dùng.
3. **Xử lý cạnh tranh và lỗi:** mô tả transaction để claim key và tạo booking. Với thanh toán, mô tả cách dùng cùng provider key, lưu provider reference và tra cứu khi timeout. Chỉ ra cách xử lý crash ở từng bước.
4. **Thiết kế API contract:** viết ví dụ request/response cho lần đầu, duplicate completed, duplicate in progress và payload mismatch. Xác định status code, Retry-After/operation status URL và cửa sổ retention.
5. **Thiết kế test:** chạy 50 request đồng thời cùng key, cùng body; sau đó chạy cùng key với body khác; mô phỏng client timeout sau khi database commit và provider charge thành công. Kiểm tra số booking, số charge thực tế, response replay, audit log và reconciliation.
6. **Review Well-Architected:** đánh giá vận hành, bảo mật, độ tin cậy, hiệu năng, chi phí và bền vững cho cơ chế đã chọn.

### Tiêu chí nghiệm thu

| Mục tiêu | Bằng chứng |
| --- | --- |
| Chỉ tạo một booking cho cùng ý định | Database có một resource và các retry nhận cùng resource ID |
| Không nhầm hai tenant | Key trùng giữa tenant không chia sẻ record/response |
| Payload mismatch được phát hiện | Cùng scope/key, fingerprint khác trả conflict |
| Không charge lặp sau timeout | Provider chỉ ghi nhận một charge theo cùng provider operation key |
| Request đồng thời an toàn | 50 request đồng thời không tạo nhiều side effect |
| Có thể phục hồi trạng thái mồ côi | Lease/reconciliation xác định operation đã/ chưa xảy ra |
| Retention đúng hợp đồng | Test biên TTL và quy trình replay khớp policy |
| Không rò dữ liệu qua replay | Unauthorized tenant/principal không đọc được response |

## 16. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi đánh giá |
| --- | --- |
| **Operational Excellence** | Có metric duplicate, orphaned IN_PROGRESS, runbook reconcile và khả năng replay không? |
| **Security** | Scope gắn với principal, key không phải credential, response replay có authorization và retention không? |
| **Reliability** | Crash sau commit, provider timeout, webhook redelivery và concurrent duplicate đã được xử lý? |
| **Performance Efficiency** | Unique lookup/locking có tạo bottleneck? Có index phù hợp, latency và tải đỉnh được đo? |
| **Cost Optimization** | Storage record, response retention, cleanup và provider lookup có được tính? |
| **Sustainability** | Có giảm retry storm, polling và record thừa; cleanup theo vòng đời có kiểm soát? |

Một thiết kế tốt phải chứng minh cơ chế chống lặp không phụ thuộc execution instance, concurrency không làm hỏng dữ liệu hoặc downstream, và nhóm có đủ tín hiệu để phát hiện operation bị mắc kẹt hoặc side effect không rõ kết quả.

## 17. Checklist trước khi đưa idempotency vào production

- [ ] Endpoint có side effect đã xác định có cần idempotency key hay semantics idempotent tự nhiên.
- [ ] Client tạo key một lần cho một ý định và giữ nguyên qua mọi retry.
- [ ] Scope có tenant/principal và operation phù hợp; environment/version được cân nhắc.
- [ ] Server xác thực caller trước khi đọc/replay record.
- [ ] Fingerprint được tính từ dữ liệu nghiệp vụ đã chuẩn hóa.
- [ ] Cùng key/khác fingerprint có phản hồi rõ ràng, không thực hiện side effect.
- [ ] Atomic claim dùng unique constraint, conditional write hoặc primitive tương đương.
- [ ] Business state và idempotency completion được commit nguyên tử khi cùng datastore.
- [ ] Side effect ngoài database có provider key, outbox, inbox hoặc reconciliation phù hợp.
- [ ] Trạng thái IN_PROGRESS có timeout/lease và cơ chế phục hồi.
- [ ] Duplicate completed có response replay được định nghĩa trong API contract.
- [ ] Retry, timeout, backoff, concurrency và deadline phối hợp để tránh retry storm.
- [ ] Retention vượt cửa sổ retry/replay cần hỗ trợ; key hết hạn có semantics rõ.
- [ ] Response/key/fingerprint được bảo vệ, mã hóa và cleanup theo policy dữ liệu.
- [ ] Có metric, alert, audit, runbook và phép thử concurrent/failure/TTL.
- [ ] Đã xác minh số side effect thật ở database/provider, không chỉ response HTTP.

Idempotency key là một hợp đồng giữa caller và API để nhận diện cùng một ý định qua nhiều lần gửi. Cơ chế đáng tin cậy cần **scope đúng, fingerprint đúng, atomic claim, dữ liệu chống lặp bền vững và cách xử lý rõ cho timeout, concurrency, side effect bên ngoài và hết hạn**. Khi được thiết kế cùng transaction, outbox/inbox, retry policy và observability, nó giúp API chịu được mạng không ổn định và hệ thống phân tán mà vẫn giữ tính đúng đắn của nghiệp vụ.
