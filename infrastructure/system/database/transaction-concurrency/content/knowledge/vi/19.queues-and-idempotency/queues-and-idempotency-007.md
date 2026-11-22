# Lưu kết quả xử lý để phản hồi lại yêu cầu trùng

Trong hệ thống có retry, một yêu cầu có thể đến nhiều lần dù nghiệp vụ chỉ nên được thực hiện một lần. Client có thể gửi lại vì timeout mạng, người dùng nhấn nút nhiều lần, gateway retry hoặc worker nhận lại cùng một message sau khi chưa xác nhận được kết quả. Nếu server thực hiện nghiệp vụ lại mỗi lần nhận yêu cầu, một đơn hàng có thể được tạo hai lần, tồn kho bị trừ nhiều lần hoặc một khoản thanh toán bị ghi nhận lặp.

Một cách phổ biến để xử lý là lưu **khóa idempotency cùng kết quả xử lý**. Khi nhận yêu cầu trùng, server tìm bản ghi đã lưu và trả lại kết quả tương ứng thay vì thực hiện nghiệp vụ lần nữa. Cơ chế này giúp một yêu cầu logic có thể được gửi lại nhiều lần mà kết quả quan sát được vẫn nhất quán.

## 1. Vì sao cần lưu kết quả của yêu cầu?

Giả sử client gửi yêu cầu tạo đơn hàng:

~~~http
POST /orders
Idempotency-Key: 7d4c1b2a-...
Content-Type: application/json

{
  "productId": 42,
  "quantity": 2
}
~~~

Server xử lý thành công, tạo đơn hàng 9001 và trả về:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": 9001,
  "status": "PENDING"
}
~~~

Nhưng phản hồi bị mất trên đường truyền. Client không biết server đã tạo đơn hay chưa, nên gửi lại cùng yêu cầu. Nếu server chỉ nhìn thấy một POST mới, nó có thể tạo đơn 9002 và trừ tồn kho lần nữa.

Có hai sự kiện cần phân biệt:

- **Yêu cầu được thực hiện:** transaction đã tạo đơn và commit thành công.
- **Client nhận được phản hồi:** response đã đến được client.

Hai sự kiện này không xảy ra nguyên tử cùng nhau. Server có thể commit rồi mất kết nối trước khi gửi response. Vì vậy client không thể suy ra rằng timeout đồng nghĩa nghiệp vụ chưa chạy.

Nếu server lưu kết quả gắn với một idempotency key, lần gửi lại có thể nhận đúng kết quả của lần đầu:

~~~text
Lần 1: key K -> tạo đơn 9001 -> lưu response -> commit
                       |
                       +---- response bị mất

Lần 2: key K -> tìm thấy kết quả đã lưu -> trả lại response của đơn 9001
             -> không tạo đơn mới
~~~

Đây là ý nghĩa của việc lưu kết quả xử lý để phản hồi lại yêu cầu trùng.

## 2. Idempotency key là gì?

Idempotency key là một định danh do client tạo hoặc được cấp trước khi gửi yêu cầu. Các lần retry của cùng một thao tác logic phải gửi lại **cùng key**.

Một key cần có phạm vi xác định. Thông thường, danh tính yêu cầu được tạo từ tổ hợp:

- Tenant, tài khoản hoặc chủ thể gọi API.
- Tên thao tác hoặc endpoint.
- Idempotency key do client cung cấp.

Ví dụ, key abc-123 của tenant A khi tạo đơn hàng không nên va chạm với key cùng giá trị của tenant B hoặc một thao tác hoàn tiền khác.

Một định danh có phạm vi rõ ràng có thể được mô hình hóa:

~~~text
(tenant_id, operation_name, idempotency_key)
~~~

Các nguyên tắc quan trọng:

- Client tạo key đủ ngẫu nhiên và khó trùng, thường dùng UUID hoặc một giá trị ngẫu nhiên đủ entropy.
- Client giữ key đó trong suốt thời gian retry cùng một yêu cầu.
- Khi người dùng thực hiện một hành động mới, client tạo key mới.
- Server lưu key bền vững trong database, không chỉ trong bộ nhớ của một instance.
- Key cần được giới hạn độ dài và kiểm tra định dạng để tránh lạm dụng tài nguyên.

Không nên tự tạo key mới cho mỗi lần gửi lại. Nếu key thay đổi, server không có căn cứ để biết hai request là cùng một thao tác logic.

Cũng không nên dùng riêng email, product ID hoặc timestamp làm idempotency key. Những giá trị đó có thể lặp lại hợp lệ hoặc không đủ duy nhất cho từng lần người dùng chủ động thực hiện nghiệp vụ.

## 3. Cần lưu cả dấu vết yêu cầu và kết quả trả về

Chỉ lưu key đã dùng là chưa đủ. Khi request trùng đến, server cần biết:

- Yêu cầu ban đầu thuộc thao tác nào và tenant nào.
- Payload có giống yêu cầu đầu tiên không.
- Yêu cầu đang xử lý hay đã hoàn tất.
- Kết quả xử lý là gì.
- Response nào cần trả lại cho client.

Một bảng idempotency có thể có cấu trúc:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          BIGINT       NOT NULL,
    operation_name     VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64)     NOT NULL,
    status             VARCHAR(20)  NOT NULL,
    response_status    INTEGER,
    response_body      TEXT,
    resource_id        VARCHAR(100),
    created_at         TIMESTAMP    NOT NULL,
    completed_at       TIMESTAMP,
    expires_at         TIMESTAMP,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Các cột chính:

| Cột | Mục đích |
|---|---|
| tenant_id | Phân vùng quyền sở hữu yêu cầu |
| operation_name | Phân biệt loại thao tác, ví dụ CREATE_ORDER hoặc REFUND |
| idempotency_key | Định danh ổn định cho các lần gửi lại |
| request_hash | Dấu vân tay của nội dung yêu cầu đã chuẩn hóa |
| status | Trạng thái xử lý như PROCESSING, COMPLETED hoặc FAILED |
| response_status | Mã HTTP hoặc mã kết quả cần phát lại |
| response_body | Nội dung phản hồi đã lưu |
| resource_id | ID tài nguyên nghiệp vụ đã tạo hoặc thay đổi |
| created_at, completed_at | Thời điểm bắt đầu và hoàn tất |
| expires_at | Thời điểm bản ghi có thể được dọn theo chính sách lưu giữ |

Kiểu dữ liệu và cú pháp thời gian cần điều chỉnh theo hệ quản trị. Nếu response có thể lớn, cân nhắc kiểu JSON/JSONB hoặc lưu payload ở một bảng riêng. Có thể lưu thêm một tập header được phép phát lại, nhưng không nên lưu toàn bộ header của HTTP response một cách mù quáng.

Khóa chính hoặc unique constraint trên phạm vi key là phần rất quan trọng. Nó là trọng tài cuối cùng khi nhiều server nhận cùng một key đồng thời.

## 4. Vì sao cần request fingerprint?

Một client có thể gửi cùng key nhưng vô tình hoặc cố ý thay đổi payload. Ví dụ:

Lần đầu:

~~~json
{
  "productId": 42,
  "quantity": 2
}
~~~

Lần sau lại gửi:

~~~json
{
  "productId": 42,
  "quantity": 5
}
~~~

Nếu server chỉ tìm key và trả kết quả cũ, client có thể hiểu nhầm rằng yêu cầu mua 5 sản phẩm đã được chấp nhận. Nếu server xử lý payload mới, cùng key lại đại diện cho hai ý định khác nhau.

Vì vậy, server nên tính **request fingerprint** (*dấu vân tay yêu cầu*) từ các trường có ý nghĩa nghiệp vụ. Thông thường có thể dùng SHA-256 trên một biểu diễn đã chuẩn hóa.

Fingerprint nên bao gồm những yếu tố ảnh hưởng đến kết quả:

- HTTP method hoặc operation name.
- API version nếu khác phiên bản làm thay đổi ngữ nghĩa.
- Đường dẫn và tham số tài nguyên liên quan.
- Payload đã chuẩn hóa.
- Tenant hoặc chủ thể gọi nếu chưa được dùng trong phạm vi unique key.

Không nên băm trực tiếp JSON thô nếu thứ tự thuộc tính, khoảng trắng hoặc định dạng số có thể thay đổi mà không làm thay đổi ý nghĩa. Hãy chuẩn hóa dữ liệu trước, chẳng hạn sắp xếp trường, chuẩn hóa số, loại bỏ trường trình bày không ảnh hưởng nghiệp vụ và thống nhất cách biểu diễn thời gian.

Quy tắc xử lý:

- Cùng key và cùng fingerprint: đây là request trùng; trả kết quả đã lưu hoặc thông tin trạng thái hiện tại.
- Cùng key nhưng fingerprint khác: từ chối vì client đã tái sử dụng key cho một yêu cầu khác.
- Key chưa tồn tại: bắt đầu xử lý request mới.

API có thể trả 409 Conflict cho trường hợp key đã được dùng với payload khác. Mã và cấu trúc lỗi cụ thể cần được thống nhất trong hợp đồng API.

## 5. Luồng xử lý cơ bản

Một luồng xử lý có thể diễn ra như sau:

~~~mermaid
flowchart TD
    A["Nhận request và idempotency key"] --> B["Chuẩn hóa payload, tính request hash"]
    B --> C["Tìm hoặc tạo idempotency record"]
    C --> D{"Key đã tồn tại?"}
    D -->|Chưa| E["Đăng ký key và xử lý nghiệp vụ"]
    E --> F["Lưu kết quả response cùng transaction"]
    F --> G["COMMIT"]
    G --> H["Trả response đã lưu"]
    D -->|Rồi| I{"Fingerprint trùng?"}
    I -->|Không| J["Trả lỗi key đã dùng cho payload khác"]
    I -->|Có| K{"Đã COMPLETED?"}
    K -->|Có| H
    K -->|Đang xử lý| L["Chờ, hoặc trả trạng thái đang xử lý"]
    K -->|Thất bại cuối cùng| M["Phát lại kết quả thất bại đã lưu"]
~~~

Các bước cần được xác định rõ:

1. Xác thực request và quyền truy cập.
2. Xác định phạm vi idempotency key.
3. Chuẩn hóa request và tính fingerprint.
4. Giành quyền xử lý key bằng thao tác insert có unique constraint hoặc cơ chế claim phù hợp.
5. Nếu key đã có, so fingerprint và đọc trạng thái.
6. Nếu đây là lần xử lý đầu tiên, thực hiện nghiệp vụ.
7. Lưu response cuối cùng và các thay đổi nghiệp vụ trong ranh giới transaction được thiết kế.
8. Commit trước khi gửi response thành công cho client.

Không được để hai instance ứng dụng cùng xử lý nghiệp vụ chỉ vì cả hai cùng kiểm tra thấy key chưa tồn tại. Việc kiểm tra rồi insert phải được bảo vệ bằng unique constraint hoặc một thao tác claim nguyên tử.

## 6. Mẫu nguyên tử: lưu kết quả cùng transaction nghiệp vụ

Với nghiệp vụ có thể hoàn tất trong một transaction database ngắn, cách đơn giản là ghi idempotency record, thay đổi dữ liệu nghiệp vụ và lưu response cuối cùng trong **cùng một transaction**.

Ví dụ khái quát:

~~~sql
BEGIN;

-- 1. Đăng ký key. Unique constraint ngăn hai transaction
-- cùng sở hữu một key trong cùng phạm vi.
INSERT INTO idempotency_record (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    status,
    created_at
)
VALUES (
    7,
    'CREATE_ORDER',
    'client-key-abc',
    'sha256-fingerprint',
    'PROCESSING',
    CURRENT_TIMESTAMP
);

-- 2. Thực hiện thay đổi nghiệp vụ.
INSERT INTO orders (tenant_id, customer_id, status)
VALUES (7, 77, 'PENDING');

-- 3. Lấy ID đơn vừa tạo theo cơ chế của database,
-- rồi tạo các dòng đơn hàng cần thiết.

-- 4. Lưu response cuối cùng trước khi commit.
UPDATE idempotency_record
SET status = 'COMPLETED',
    response_status = 201,
    response_body = '{"orderId":9001,"status":"PENDING"}',
    resource_id = '9001',
    completed_at = CURRENT_TIMESTAMP
WHERE tenant_id = 7
  AND operation_name = 'CREATE_ORDER'
  AND idempotency_key = 'client-key-abc';

COMMIT;
~~~

Đây là SQL minh họa luồng; cách lấy ID, xử lý insert trùng và kiểu JSON tùy hệ quản trị.

Ưu điểm của thiết kế này là tính nguyên tử:

- Nếu transaction commit, cả đơn hàng và kết quả idempotency đều tồn tại.
- Nếu transaction rollback trước commit, cả thay đổi nghiệp vụ và idempotency record chưa commit đều bị hủy.
- Nếu server mất kết nối sau commit nhưng trước khi trả response, request gửi lại sẽ tìm thấy kết quả đã lưu.

Với mô hình này, một transaction khác cố insert cùng key sẽ bị điều phối bởi unique constraint. Tùy database, thao tác insert trùng có thể chờ transaction đầu tiên commit hoặc rollback. Sau khi transaction đầu tiên commit, transaction thứ hai đọc kết quả đã lưu; nếu transaction đầu rollback, transaction thứ hai có thể giành quyền tạo record và xử lý.

Cách này phù hợp với các thao tác ngắn, chủ yếu thay đổi dữ liệu trong cùng một database.

### 6.1. Xử lý insert trùng theo hệ quản trị

Không có một cú pháp insert-if-absent hoàn toàn giống nhau cho mọi database.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO idempotency_record (
    tenant_id, operation_name, idempotency_key,
    request_hash, status, created_at
)
VALUES (
    :tenant_id, :operation, :key,
    :request_hash, 'PROCESSING', CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, operation_name, idempotency_key)
DO NOTHING
RETURNING idempotency_key;
~~~

Nếu trả về một hàng, transaction đã đăng ký được key. Nếu không trả về hàng, key đã được transaction khác tạo hoặc đã tồn tại. Ứng dụng cần đọc bản ghi hiện hành và so fingerprint.

Ở PostgreSQL READ COMMITTED, một câu SELECT tiếp theo thường có thể thấy transaction cạnh tranh vừa commit sau khi câu INSERT đã chờ xử lý xung đột. Với isolation level snapshot cấp transaction, snapshot cũ có thể không thấy hàng vừa gây conflict; khi đó cần xử lý lỗi serialization hoặc bắt đầu transaction mới tùy isolation level.

Với MySQL, có thể dùng INSERT ... ON DUPLICATE KEY hoặc bắt duplicate-key exception. Với SQL Server có thể dùng unique constraint kết hợp xử lý lỗi duplicate key hoặc một mẫu insert/claim phù hợp với isolation và khóa. Dù dùng cú pháp nào, unique constraint vẫn là lớp bảo vệ cuối cùng.

Không nên dùng riêng mẫu SELECT xem key đã tồn tại rồi mới INSERT. Hai transaction có thể cùng SELECT thấy rỗng trước khi một trong hai insert.

## 7. Khi request trùng đến trong lúc request đầu đang xử lý

Cần định nghĩa rõ cách phản hồi khi bản ghi có trạng thái PROCESSING.

Có hai mô hình phổ biến.

### 7.1. Một transaction bao trọn xử lý

Trong mô hình transaction nguyên tử ở phần trước, record PROCESSING chưa commit cho đến khi nghiệp vụ và response được lưu xong. Request thứ hai cố tạo cùng key thường phải chờ quyết định unique key của transaction đầu.

- Nếu transaction đầu commit, request thứ hai thấy record đã hoàn tất và phát lại response.
- Nếu transaction đầu rollback, request thứ hai có thể tạo record và xử lý.
- Request thứ hai không nhất thiết quan sát được trạng thái PROCESSING vì trạng thái đó chưa commit.

Mô hình này đơn giản và tránh để lại record đang xử lý bị kẹt sau crash, nhưng không phù hợp với công việc kéo dài nhiều phút hoặc phải chờ dịch vụ bên ngoài.

### 7.2. Claim được commit riêng cho công việc dài

Với tác vụ dài hoặc xử lý qua queue, hệ thống có thể commit một record PROCESSING trước khi chạy nghiệp vụ. Khi đó cần thêm cơ chế quản lý quyền sở hữu:

- owner_id hoặc worker ID.
- lease_until để giới hạn thời gian giữ quyền xử lý.
- attempt_count và updated_at.
- Trạng thái PROCESSING, COMPLETED, FAILED hoặc RETRYABLE.
- Mã lỗi hoặc thông tin chẩn đoán nếu cần.

Request trùng khi record đang xử lý có thể nhận 202 Accepted kèm URL tra cứu trạng thái, hoặc 409 Conflict/một mã trạng thái đã thống nhất. Không nên tạo một response giả như thể nghiệp vụ đã hoàn tất.

Lease giúp hệ thống thu hồi công việc nếu worker chết. Tuy nhiên, worker cũ có thể tỉnh lại sau khi lease hết hạn và tiếp tục ghi. Vì vậy, khi claim lại, cần dùng **fencing token** hoặc phiên bản tăng dần để chỉ owner mới nhất được phép hoàn tất. Chỉ kiểm tra thời gian lease ở ứng dụng là chưa đủ để ngăn worker cũ ghi muộn.

Mô hình claim riêng cần được thiết kế kỹ hơn mô hình một transaction. Không được trộn hai mô hình mà không xác định rõ lúc nào record trở nên nhìn thấy với request trùng.

## 8. Phát lại response nào?

Mục tiêu là trả lại kết quả của lần xử lý đầu tiên một cách nhất quán. Thường cần lưu:

- HTTP status code hoặc mã kết quả nghiệp vụ.
- Response body đã được tạo.
- Resource ID hoặc operation ID.
- Một số header ổn định mà API cần phát lại.
- Phiên bản schema response nếu API có thay đổi.

Không nên lưu và phát lại mọi header nguyên xi. Các header như Date, trace ID, request ID, connection metadata hoặc cookie có thể cần được tạo mới cho lần phản hồi hiện tại. Không lưu access token, session cookie hoặc header chứa bí mật vào bản ghi idempotency.

Có thể lưu body dạng JSON đã serialize để phát lại chính xác cấu trúc. Nếu cần thay đổi định dạng response theo API version, hãy lưu phiên bản và cách chuyển đổi rõ ràng; không tùy tiện serialize lại resource hiện tại vì resource có thể đã thay đổi sau lần xử lý đầu tiên.

Ví dụ, đơn hàng ban đầu được tạo ở trạng thái PENDING, sau đó đã chuyển thành PAID. Một request tạo đơn trùng nên nhận lại response của thao tác tạo ban đầu theo hợp đồng idempotency, thay vì bất ngờ trả một trạng thái mới lấy từ resource hiện tại. Nếu API muốn cung cấp trạng thái mới nhất, hãy thiết kế endpoint tra cứu resource riêng.

## 9. Những lỗi nào nên lưu thành kết quả cuối cùng?

Không phải mọi lỗi đều nên được lưu vĩnh viễn như response cuối cùng.

Một chính sách thường dùng:

| Kết quả lần xử lý | Có lưu response cuối cùng? | Lý do |
|---|---|---|
| Thành công | Có | Request trùng phải nhận lại kết quả đã commit |
| Lỗi nghiệp vụ xác định, ví dụ không đủ hàng | Có thể có | Cùng một request logic nên nhận cùng kết quả; client cần key mới nếu muốn thử như một hành động mới sau khi điều kiện thay đổi |
| Request không hợp lệ trước khi bắt đầu xử lý | Tùy hợp đồng API | Có thể từ chối trước khi claim key; cần thống nhất việc key có bị tiêu thụ hay không |
| Deadlock hoặc serialization failure | Thường không lưu như kết quả cuối cùng | Transaction đã bị hủy; cùng request có thể được thử lại trong transaction mới |
| Lỗi tạm thời của database hoặc dependency | Thường không đánh dấu hoàn tất | Cho phép retry theo chính sách và trạng thái thực tế |
| Lỗi không rõ transaction đã commit hay chưa | Cần tra cứu trạng thái bền vững | Không được thực hiện lại mù quáng |

Nếu lưu lỗi nghiệp vụ cuối cùng, hãy lưu status và body để phát lại. Ví dụ lần đầu trả 409 INSUFFICIENT_STOCK; nếu client gửi lại cùng key sau khi kho được bổ sung, server vẫn trả kết quả cũ. Muốn tạo một yêu cầu mua mới, client cần một key mới.

Với lỗi tạm thời, chỉ xóa hoặc giải phóng trạng thái claim khi chắc chắn nghiệp vụ chưa commit. Nếu kết quả commit không rõ vì mất kết nối, hãy tra cứu idempotency record trước khi quyết định xử lý lại.

## 10. Ví dụ Java: phát lại kết quả đã lưu

Mã sau mô tả cách tổ chức logic ở tầng service. Các hàm truy cập database là phần triển khai theo driver và hệ quản trị cụ thể:

~~~java
public HttpResponse handle(CreateOrderRequest request,
                           String idempotencyKey,
                           Tenant tenant) {

    String requestHash = fingerprint(request);

    IdempotencyRecord existing =
        repository.find(tenant.id(), "CREATE_ORDER", idempotencyKey);

    if (existing != null) {
        if (!existing.requestHash().equals(requestHash)) {
            return HttpResponse.conflict(
                "Idempotency key đã được dùng cho payload khác"
            );
        }

        if (existing.status() == Status.COMPLETED
                || existing.status() == Status.FAILED) {
            return replay(existing);
        }

        return processingResponse(existing);
    }

    try {
        return transactionRunner.execute(connection -> {
            // Claim key bằng INSERT có unique constraint.
            repository.insertProcessing(
                connection,
                tenant.id(),
                "CREATE_ORDER",
                idempotencyKey,
                requestHash
            );

            // Nghiệp vụ và response phải được lưu trong cùng transaction.
            Order order = orderService.create(connection, request);

            HttpResponse response = HttpResponse.created(
                new OrderResponse(order.id(), order.status())
            );

            repository.complete(
                connection,
                tenant.id(),
                "CREATE_ORDER",
                idempotencyKey,
                requestHash,
                response.status(),
                serialize(response.body()),
                order.id()
            );

            return response;
        });
    } catch (DuplicateIdempotencyKey duplicate) {
        // Một request cạnh tranh đã giành key.
        // Đọc lại bản ghi đã commit, kiểm tra fingerprint rồi phát lại.
        IdempotencyRecord winner =
            repository.find(tenant.id(), "CREATE_ORDER", idempotencyKey);

        if (winner == null) {
            throw new RetryableConcurrencyException(duplicate);
        }

        if (!winner.requestHash().equals(requestHash)) {
            return HttpResponse.conflict(
                "Idempotency key đã được dùng cho payload khác"
            );
        }

        if (winner.status() == Status.COMPLETED
                || winner.status() == Status.FAILED) {
            return replay(winner);
        }

        return processingResponse(winner);
    }
}
~~~

Đây là pseudocode Java để thể hiện luồng, không phải một class có thể biên dịch ngay. transactionRunner phải tạo transaction mới cho lần thực thi; repository.insertProcessing cần dùng unique constraint để tranh quyền key một cách nguyên tử; lỗi duplicate phải được xử lý sau khi transaction đã rollback hoặc kết thúc theo yêu cầu của driver.

Không nên thực hiện find rồi tin rằng key chưa tồn tại mà bỏ qua bước insert có unique constraint. Kiểm tra trước chỉ là tối ưu để phát lại nhanh; thao tác insert nguyên tử mới quyết định ai được quyền xử lý lần đầu.

## 11. Xử lý crash ở các thời điểm khác nhau

Bản ghi idempotency cần được thiết kế theo các điểm crash có thể xảy ra.

| Thời điểm server gặp sự cố | Trạng thái có thể quan sát | Hành động khi request gửi lại |
|---|---|---|
| Trước khi tạo idempotency record | Không có record | Request mới có thể bắt đầu |
| Sau insert nhưng trước commit trong transaction nguyên tử | Transaction rollback khi connection bị đóng hoặc phục hồi | Request mới có thể claim key và xử lý |
| Sau khi ghi nghiệp vụ và response nhưng trước commit | Cả hai chưa commit; rollback | Request mới xử lý lại |
| Sau commit nhưng trước khi gửi response | Nghiệp vụ và response đã lưu | Phát lại response đã lưu |
| Sau khi gửi response | Đã hoàn tất | Phát lại nếu client gửi trùng |
| Worker chết khi record PROCESSING đã commit riêng | Có thể còn record đang xử lý | Lease/recovery xác định worker mới và kiểm tra kết quả trước khi chạy lại |

Mấu chốt là thay đổi nghiệp vụ và kết quả idempotency phải có quan hệ nguyên tử hoặc một giao thức phục hồi đủ mạnh. Nếu tạo đơn commit ở transaction thứ nhất nhưng lưu response ở transaction thứ hai, crash ở giữa có thể để lại đơn đã tạo nhưng không có kết quả để phát lại. Request trùng khi đó có thể tạo đơn thứ hai.

## 12. Kết hợp với transactional outbox và queue

Nếu xử lý request còn phải phát message đến queue, gửi email hoặc gọi dịch vụ khác, database transaction không thể tự rollback tác động đã xảy ra bên ngoài.

Một mẫu thường dùng:

1. Trong transaction database, tạo hoặc cập nhật tài nguyên nghiệp vụ.
2. Lưu idempotency response.
3. Ghi một sự kiện vào bảng outbox.
4. Commit cả ba thay đổi.
5. Worker đọc outbox và phát message sau commit.
6. Consumer lưu message ID hoặc business key đã xử lý để chống thực hiện lặp.

Ví dụ:

~~~sql
BEGIN;

-- Tạo đơn hàng.
INSERT INTO orders (tenant_id, customer_id, status)
VALUES (7, 77, 'PENDING');

-- Lưu response đã hoàn tất cho idempotency key.
UPDATE idempotency_record
SET status = 'COMPLETED',
    response_status = 201,
    response_body = '{"orderId":9001,"status":"PENDING"}',
    completed_at = CURRENT_TIMESTAMP
WHERE tenant_id = 7
  AND operation_name = 'CREATE_ORDER'
  AND idempotency_key = 'client-key-abc';

-- Ghi sự kiện để worker phát sau commit.
INSERT INTO outbox_event (event_id, event_type, aggregate_id, payload)
VALUES ('evt-9001', 'OrderCreated', '9001', '{"orderId":9001}');

COMMIT;
~~~

Worker có thể phát lại message nếu không chắc broker đã nhận. Vì vậy consumer cũng cần idempotency riêng, thường dựa trên event_id hoặc một business key có unique constraint.

Idempotency ở API và idempotency ở consumer là hai lớp khác nhau:

- API layer ngăn cùng một yêu cầu client tạo nhiều kết quả nghiệp vụ.
- Consumer layer ngăn cùng một message được áp dụng nhiều lần ở dịch vụ nhận.
- Outbox bảo đảm ý định phát sự kiện được ghi cùng transaction với thay đổi nghiệp vụ.

Không nên tuyên bố hệ thống đạt exactly-once end-to-end chỉ vì có idempotency key. Thực tế thường là giao nhận có thể lặp (*at-least-once*) kết hợp với xử lý idempotent ở từng ranh giới.

## 13. Lưu giữ và dọn dẹp idempotency record

Nếu xóa record quá sớm, một request retry muộn có thể bị coi là mới và thực hiện nghiệp vụ lần nữa. Thời gian lưu giữ cần dựa trên:

- Khoảng thời gian client có thể retry.
- Thời gian gateway, mobile client hoặc queue có thể gửi lại.
- Thời gian nghiệp vụ cần đối soát.
- Yêu cầu pháp lý và audit.
- Chi phí lưu trữ và tốc độ tăng dữ liệu.

Có thể dùng expires_at để xác định khi nào record đủ điều kiện dọn. Worker dọn dữ liệu nên xóa theo batch nhỏ, tránh khóa một lượng lớn hàng trong transaction dài.

Với thao tác tài chính, thanh toán hoặc cấp phát tài nguyên quan trọng, không nên chỉ dựa vào TTL ngắn. Có thể giữ một dấu vết key tối giản lâu hơn, hoặc dùng unique business reference để ngăn tạo trùng ngay cả khi response body đã được dọn.

Cần định nghĩa hành vi khi key hết hạn:

- Key hết hạn có được coi như chưa từng tồn tại không?
- Có lưu tombstone để từ chối key cũ không?
- Client có được phép tái sử dụng key không?
- Nếu key cũ xuất hiện sau khi record bị xóa, hệ thống có thể tạo nghiệp vụ trùng không?

Không nên tái sử dụng key cho hành động mới trong cùng phạm vi. Client nên tạo key mới cho mỗi ý định nghiệp vụ mới.

## 14. Bảo mật khi phát lại kết quả

Response được lưu có thể chứa dữ liệu riêng tư hoặc thông tin chỉ người dùng đã xác thực mới được xem. Vì vậy, khi phát lại:

- Xác thực người gọi hiện tại.
- Kiểm tra tenant và quyền truy cập resource.
- Giới hạn lookup theo đúng phạm vi tenant/operation/key.
- Không cho người dùng khác đoán key để lấy response.
- Không lưu token, cookie hoặc dữ liệu bí mật trong response cache nếu không cần.
- Nếu quyền truy cập đã bị thu hồi, áp dụng chính sách bảo mật hiện hành thay vì phát lại dữ liệu nhạy cảm một cách vô điều kiện.

Idempotency key là định danh chống lặp, không phải cơ chế xác thực hay quyền truy cập. Biết key không được phép đồng nghĩa với việc có thể đọc kết quả của yêu cầu.

## 15. Các tình huống cần định nghĩa rõ trong hợp đồng API

| Tình huống | Hành vi đề xuất |
|---|---|
| Key mới, payload hợp lệ | Claim key, xử lý nghiệp vụ, lưu response và trả kết quả |
| Cùng key, cùng payload, đã hoàn tất | Trả lại response đã lưu |
| Cùng key, payload khác | Trả lỗi xung đột, ví dụ HTTP 409 |
| Cùng key, request đầu đang xử lý | Chờ có giới hạn hoặc trả trạng thái đang xử lý theo hợp đồng API |
| Request đầu thất bại tạm thời và chưa commit | Cho phép thử lại theo trạng thái bền vững |
| Request đầu thất bại nghiệp vụ cuối cùng đã lưu | Phát lại cùng kết quả thất bại |
| Client mất response sau commit | Request gửi lại nhận response đã lưu |
| Key đã hết hạn | Xử lý theo chính sách TTL/tombstone được công bố |

API cần mô tả rõ client phải dùng lại key khi retry, key có hiệu lực trong bao lâu và response trùng được trả theo cách nào. Nếu không công bố hợp đồng này, client có thể tạo key mới cho mỗi lần retry và làm mất tác dụng chống lặp.

## 16. Checklist triển khai lưu kết quả cho yêu cầu trùng

- [ ] Client tạo một idempotency key ổn định cho mỗi ý định nghiệp vụ?
- [ ] Các lần retry cùng thao tác có gửi lại cùng key?
- [ ] Key được phân vùng theo tenant và operation?
- [ ] Database có unique constraint trên phạm vi key?
- [ ] Server tính request fingerprint từ payload đã chuẩn hóa?
- [ ] Cùng key nhưng payload khác bị từ chối rõ ràng?
- [ ] Kết quả cuối cùng gồm status và body được lưu bền vững?
- [ ] Thay đổi nghiệp vụ và response record được commit nguyên tử hoặc có giao thức phục hồi tương đương?
- [ ] Hai request đồng thời cùng key không thể cùng thực hiện nghiệp vụ?
- [ ] Trạng thái PROCESSING có quy tắc chờ, lease và recovery rõ ràng nếu được commit riêng?
- [ ] Request trùng đã hoàn tất được trả lại response cũ thay vì đọc trạng thái resource mới rồi dựng kết quả khác?
- [ ] Lỗi tạm thời và lỗi nghiệp vụ cuối cùng có chính sách lưu khác nhau?
- [ ] Tác động ngoài database dùng outbox hoặc idempotency ở hệ thống nhận?
- [ ] Record được lưu đủ lâu cho retry và đối soát?
- [ ] Việc phát lại response vẫn kiểm tra authentication, authorization và tenant?
- [ ] Kiểm thử crash sau commit nhưng trước khi gửi response?
- [ ] Kiểm thử hai request đồng thời dùng cùng key và cùng payload?
- [ ] Kiểm thử cùng key nhưng payload khác?

Lưu kết quả xử lý giúp server trả lời nhất quán khi cùng một yêu cầu được gửi lại. Idempotency key xác định thao tác logic; request fingerprint xác nhận payload không bị thay đổi; unique constraint điều phối các request cạnh tranh; response đã lưu cho phép phát lại kết quả sau timeout hoặc mất kết nối. Khi kết hợp thay đổi nghiệp vụ và kết quả trong cùng transaction, rồi dùng outbox và consumer idempotency cho tác động bên ngoài, hệ thống có thể xử lý retry và message trùng mà không tạo thêm hiệu ứng nghiệp vụ ngoài ý muốn.
