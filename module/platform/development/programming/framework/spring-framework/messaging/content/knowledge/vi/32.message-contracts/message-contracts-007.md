# Khóa idempotency, lưu kết quả và thời hạn chống trùng

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao một request messaging có thể được gửi hoặc xử lý nhiều lần dù client chỉ định gửi một lần.
- Thiết kế khóa idempotency theo phạm vi tenant, operation và request.
- Phát hiện việc tái sử dụng cùng một khóa với payload khác bằng request fingerprint.
- Lưu trạng thái và kết quả để trả lại response cũ cho request trùng.
- Xử lý hai request cùng khóa đến đồng thời bằng ràng buộc unique và transaction.
- Chọn thời hạn lưu bản ghi chống trùng, chính sách lỗi và cơ chế phục hồi phù hợp.

## 1. Vì sao cần idempotency?

Trong hệ thống messaging, việc gửi message và việc nhận được kết quả là hai sự kiện khác nhau. Client có thể gửi một request, server xử lý thành công, nhưng response bị mất khi connection đóng. Client không biết server đã thực hiện nghiệp vụ hay chưa nên gửi lại request.

Một số nguyên nhân thường gặp:

- Client retry sau timeout vì không nhận được response.
- Message broker giao lại message khi consumer chưa xác nhận acknowledgement.
- Consumer xử lý xong nghiệp vụ nhưng process dừng trước khi ACK.
- Connection mất sau khi server commit dữ liệu nhưng trước khi client nhận response.
- Người dùng bấm nút gửi nhiều lần hoặc gateway chuyển tiếp request lặp.
- Nhiều consumer hoặc worker cùng nhận một công việc do cấu hình, redelivery hay lỗi vận hành.

Ví dụ: client gửi lệnh tạo đơn hàng. Server đã tạo đơn **ORD-42** và commit transaction, nhưng response không đến được client. Nếu request được gửi lại như một lệnh mới, server có thể tạo thêm **ORD-43**. Client chỉ muốn một đơn hàng nhưng hệ thống tạo hai.

**Idempotency** là hợp đồng xử lý trong đó nhiều lần gửi cùng một thao tác logic được xem như một thao tác duy nhất trong phạm vi và thời hạn đã quy định. Khi nhận lại request trùng, server trả lại kết quả đã lưu hoặc thông báo trạng thái đang xử lý thay vì thực hiện side effect lần nữa.

Idempotency không làm cho mạng chỉ gửi một lần. Nó giúp tầng ứng dụng chịu được việc giao nhận lặp.

## 2. Idempotent operation và idempotency key

Một operation vốn đã idempotent có thể thực hiện nhiều lần mà trạng thái cuối vẫn giống nhau. Ví dụ đặt một resource về trạng thái **ACTIVE** thường có thể idempotent; thao tác tăng số dư thêm 100 thì không.

Với thao tác tạo mới hoặc thực hiện side effect, client có thể gửi một **idempotency key** để nhận diện một ý định nghiệp vụ duy nhất.

Ví dụ HTTP API:

~~~http
POST /api/orders
Idempotency-Key: 8a12d3e7-7a25-4f42-9e11-21c4b7f64a10
Content-Type: application/json

{"customerId":"C-17","sku":"BOOK-01","quantity":1}
~~~

Nếu client retry cùng thao tác vì timeout, nó phải gửi lại cùng key và cùng nội dung logic. Khi người dùng chủ động tạo một đơn hàng khác, client phải tạo key mới.

Trong messaging, key có thể nằm trong header của message, metadata của RSocket, header STOMP hoặc thuộc tính message của broker. Cách truyền key phụ thuộc transport; ý nghĩa của nó thuộc hợp đồng nghiệp vụ.

Một key nên có các đặc điểm:

- Được tạo cho từng thao tác logic, thường bằng UUID hoặc giá trị ngẫu nhiên đủ khó đoán.
- Không chứa thông tin bí mật hoặc dữ liệu cá nhân.
- Được dùng lại khi retry cùng thao tác.
- Được thay mới khi bắt đầu một thao tác khác.
- Có phạm vi duy nhất được xác định rõ, ví dụ tenant + operation + key.

Không nên dùng riêng một chuỗi key toàn cục nếu nhiều tenant hoặc nhiều loại operation có thể dùng cùng giá trị. Một khóa phổ biến là bộ ba:

~~~text
(tenant_id, operation_name, idempotency_key)
~~~

Ví dụ cùng key **request-123** có thể hợp lệ ở hai tenant khác nhau; nó cũng có thể được dùng cho hai operation khác nhau nếu hợp đồng xác định scope riêng. Phạm vi phải được phản ánh trong unique constraint của kho lưu trữ.

## 3. Fingerprint: ngăn tái sử dụng key với request khác

Chỉ kiểm tra key là chưa đủ. Client có thể vô tình gửi cùng key nhưng payload đã thay đổi, ví dụ lần đầu đặt số lượng 1 và lần sau đặt số lượng 5.

Server cần tạo **request fingerprint** từ dữ liệu có ý nghĩa nghiệp vụ. Thường dùng SHA-256 trên biểu diễn đã chuẩn hóa của method, route, tenant và payload. Khi cùng key xuất hiện:

- Fingerprint giống nhau: đây là lần gửi lại của cùng thao tác.
- Fingerprint khác nhau: client đang tái sử dụng key sai hợp đồng; server nên từ chối, thường bằng lỗi conflict.

Không nên hash trực tiếp JSON thô nếu thứ tự thuộc tính hoặc khoảng trắng có thể thay đổi nhưng nội dung logic không đổi. Hãy canonicalize JSON hoặc serialize DTO theo một quy tắc ổn định. Chỉ đưa các trường ảnh hưởng đến nghiệp vụ vào fingerprint; loại bỏ timestamp truyền tải hoặc trace ID nếu chúng thay đổi giữa các lần retry.

Ví dụ fingerprint có thể được tính từ:

~~~text
SHA-256(
  tenantId + "\n" +
  HTTP_METHOD + "\n" +
  normalizedRoute + "\n" +
  canonicalRequestBody
)
~~~

Hash không phải cơ chế xác thực hay phân quyền. Server vẫn phải xác thực người gửi và kiểm tra quyền cho mỗi lần truy cập kết quả. Không đưa access token hoặc secret vào fingerprint/log.

## 4. Lưu trạng thái và response đã xử lý

Bản ghi idempotency thường cần lưu:

| Trường | Vai trò |
| --- | --- |
| tenant/scope | Phân tách phạm vi khóa |
| idempotency_key | Nhận diện thao tác logic |
| request_hash | Phát hiện cùng key nhưng payload khác |
| state | Trạng thái xử lý |
| response_status | Mã kết quả hoặc loại kết quả |
| response_body | Kết quả đã serialize để replay |
| resource_id | ID resource được tạo/cập nhật nếu có |
| created_at | Thời điểm nhận thao tác đầu tiên |
| completed_at | Thời điểm xử lý hoàn tất |
| expires_at | Mốc hết thời hạn chống trùng |

Các trạng thái thường dùng:

- **IN_PROGRESS:** đã nhận quyền xử lý nhưng kết quả chưa sẵn sàng.
- **COMPLETED:** nghiệp vụ đã hoàn tất và response được lưu.
- **FAILED_FINAL:** thất bại cuối cùng và hợp đồng quy định các lần retry phải nhận lại lỗi này.
- **FAILED_RETRYABLE:** thất bại có thể thử lại; cần quy tắc rõ ràng để lấy lại quyền xử lý.

Không phải hệ thống nào cũng cần cả bốn trạng thái. Với xử lý đồng bộ nằm trọn trong một transaction ngắn, bản ghi **IN_PROGRESS** có thể chỉ tồn tại trong transaction và được commit cùng trạng thái **COMPLETED**. Với job chạy dài, trạng thái **IN_PROGRESS** phải được commit để request trùng có thể nhìn thấy và nhận thông báo đang xử lý.

**Lưu response nào?** Nếu API cần replay đúng kết quả, lưu status, body, content type và những response header có ý nghĩa như **Location** hoặc mã phiên bản. Không nên lưu các header thay đổi theo từng lần truyền như **Date**, trace ID hoặc header kết nối. Nếu chỉ cần bảo đảm không tạo side effect lần nữa, có thể lưu resource ID và dựng lại response từ dữ liệu hiện tại; đây là hợp đồng khác với replay nguyên response.

Với body cần replay chính xác, lưu bytes hoặc chuỗi đã serialize cùng content type. JSONB có thể chuẩn hóa cấu trúc và không bảo toàn chính xác byte ban đầu hoặc thứ tự field.

## 5. Thiết kế bảng và unique constraint

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_name     VARCHAR(150) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64) NOT NULL,
    state              VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      TEXT,
    response_headers   JSONB,
    resource_id        VARCHAR(150),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at       TIMESTAMPTZ,
    expires_at         TIMESTAMPTZ NOT NULL,

    CONSTRAINT pk_idempotency_record
        PRIMARY KEY (tenant_id, operation_name, idempotency_key),

    CONSTRAINT ck_idempotency_state
        CHECK (state IN (
            'IN_PROGRESS',
            'COMPLETED',
            'FAILED_FINAL',
            'FAILED_RETRYABLE'
        ))
);

CREATE INDEX ix_idempotency_expiry
    ON idempotency_record (expires_at);
~~~

Điểm quan trọng nhất là **primary key/unique constraint** trên phạm vi khóa. Kiểm tra kiểu “SELECT trước, nếu chưa có thì INSERT” không đủ an toàn khi có hai request đến đồng thời: cả hai có thể cùng đọc thấy chưa tồn tại và cùng thực hiện nghiệp vụ.

Cơ sở dữ liệu phải là nơi phân xử quyền sở hữu khóa bằng thao tác insert có unique constraint. Trong PostgreSQL, có thể dùng:

~~~sql
INSERT INTO idempotency_record (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    state,
    expires_at
)
VALUES (
    :tenantId,
    :operationName,
    :key,
    :requestHash,
    'IN_PROGRESS',
    :expiresAt
)
ON CONFLICT (tenant_id, operation_name, idempotency_key)
DO NOTHING;
~~~

Nếu insert tạo được một hàng, request hiện tại giành được quyền xử lý. Nếu không tạo hàng, đã có một request khác sử dụng key đó; server phải đọc bản ghi hiện có, so sánh fingerprint và quyết định replay, báo đang xử lý hay từ chối key conflict.

Đừng thay unique constraint bằng distributed lock tự triển khai nếu cơ sở dữ liệu đã là nơi lưu trạng thái nghiệp vụ. Lock và bản ghi idempotency cần cùng một nguồn sự thật hoặc có giao thức đồng bộ rõ ràng.

## 6. Quy trình xử lý request trùng

Luồng đồng bộ điển hình:

~~~mermaid
flowchart TD
    A[Nhận request và idempotency key] --> B[Tính request fingerprint]
    B --> C[INSERT bản ghi với unique key]
    C --> D{INSERT thành công?}
    D -->|Có| E[Thực hiện nghiệp vụ]
    E --> F[Lưu response và COMPLETED]
    F --> G[COMMIT transaction và trả response]
    D -->|Không| H[Đọc bản ghi hiện có]
    H --> I{Fingerprint giống?}
    I -->|Không| J[Từ chối key conflict]
    I -->|Có| K{Trạng thái?}
    K -->|COMPLETED| L[Replay response đã lưu]
    K -->|IN_PROGRESS| M[Trả trạng thái đang xử lý hoặc chờ]
    K -->|FAILED_FINAL| N[Replay lỗi cuối cùng]
    K -->|FAILED_RETRYABLE| O[Áp dụng chính sách claim/retry]
~~~

Với request trùng có fingerprint giống nhau:

- Nếu **COMPLETED**, trả lại kết quả đã lưu. Không gọi service tạo đơn hàng lần nữa.
- Nếu **IN_PROGRESS**, trả trạng thái đang xử lý (ví dụ HTTP 202 kèm URL truy vấn trạng thái), hoặc chờ kết quả trong giới hạn thời gian. Đừng chạy song song một bản nghiệp vụ thứ hai.
- Nếu **FAILED_FINAL**, trả lại lỗi đã được lưu theo hợp đồng.
- Nếu **FAILED_RETRYABLE**, chỉ một worker được claim lại theo cơ chế nguyên tử; các worker khác phải chờ hoặc nhận trạng thái đang xử lý.

Với cùng key nhưng fingerprint khác, trả conflict (ví dụ HTTP 409). Không trả response cũ cho một payload mới vì điều đó có thể khiến client hiểu nhầm thao tác mới đã được thực hiện.

## 7. Tích hợp với Spring và transaction

Với Spring, có thể triển khai kho idempotency bằng **JdbcTemplate**/repository và đặt phần ghi idempotency cùng thay đổi dữ liệu nghiệp vụ trong một transaction.

Một transaction ngắn có thể thực hiện:

1. Insert bản ghi idempotency bằng **INSERT ... ON CONFLICT DO NOTHING**.
2. Nếu insert thành công, thực hiện thay đổi domain trong cùng transaction.
3. Serialize response và cập nhật bản ghi thành **COMPLETED**.
4. Commit cả domain data và response record cùng nhau.

Nếu transaction rollback, cả thay đổi domain lẫn bản ghi idempotency chưa hoàn tất đều rollback. Request retry sau đó có thể giành quyền xử lý. Nếu transaction commit nhưng response bị mất trên đường truyền, request retry đọc được **COMPLETED** và nhận lại kết quả đã lưu.

Ví dụ dưới đây minh họa phần điều phối ở mức service. Các phương thức repository đại diện cho câu SQL ở phần trước; implementation cần dùng unique constraint trong database và chạy cùng transaction manager.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CreateOrderHandler {

    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;
    private final OrderResponseMapper responses;

    CreateOrderHandler(
            IdempotencyRepository idempotency,
            OrderRepository orders,
            OrderResponseMapper responses) {
        this.idempotency = idempotency;
        this.orders = orders;
        this.responses = responses;
    }

    @Transactional
    StoredResponse handle(
            String tenantId,
            String key,
            String requestHash,
            CreateOrder command) {

        boolean claimed = idempotency.tryInsert(
                tenantId, "CREATE_ORDER", key, requestHash);

        if (!claimed) {
            IdempotencyRecord existing = idempotency.findForUpdate(
                    tenantId, "CREATE_ORDER", key);

            if (!existing.requestHash().equals(requestHash)) {
                throw new IdempotencyKeyConflictException();
            }

            if (existing.isCompleted()) {
                return existing.storedResponse();
            }

            if (existing.isInProgress()) {
                throw new RequestAlreadyInProgressException();
            }

            throw new IdempotencyRetryPolicyException(existing.state());
        }

        Order order = orders.create(command);
        StoredResponse response = responses.from(order);

        idempotency.markCompleted(
                tenantId, "CREATE_ORDER", key, order.id(), response);

        return response;
    }
}
~~~

Đây là skeleton minh họa, không phải lớp có thể biên dịch độc lập: các interface repository, domain model, mapper và exception cần được định nghĩa trong ứng dụng. Điều kiện bắt buộc là **tryInsert** dựa vào unique constraint và **orders.create** cùng **markCompleted** tham gia đúng transaction. Không bắt exception nghiệp vụ rồi âm thầm commit bản ghi **IN_PROGRESS**.

Trong PostgreSQL, khi hai transaction đồng thời insert cùng unique key, thao tác insert thứ hai có thể phải chờ transaction đầu tiên commit hoặc rollback. Nếu transaction đầu commit, insert thứ hai không tạo hàng; ở mức isolation **READ COMMITTED**, câu SELECT tiếp theo có thể đọc bản ghi đã commit. Nếu transaction đầu rollback, request thứ hai có thể insert thành công và trở thành request xử lý. Hãy kiểm tra hành vi này với isolation level và database thực tế của ứng dụng.

Với transaction dài, không giữ transaction database mở trong lúc chờ một API bên ngoài. Cách phù hợp hơn là lưu **IN_PROGRESS** cùng lease/owner token, commit, xử lý công việc bên ngoài, rồi cập nhật kết quả. Cần lease expiration và fencing/version token để worker cũ không thể ghi đè kết quả sau khi một worker mới đã nhận quyền xử lý.

## 8. Ví dụ Java 17: chống xử lý lặp trong một process

Ví dụ sau dùng **ConcurrentHashMap.putIfAbsent** để minh họa việc chỉ một thread thực thi operation cho cùng key. Những thread còn lại chờ cùng một **CompletableFuture** và nhận cùng kết quả. Fingerprint SHA-256 phát hiện trường hợp key bị dùng lại với payload khác.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Supplier;

public class IdempotencyDemo {

    record Response(int status, String body) {}

    static final class Entry {
        final String fingerprint;
        final CompletableFuture<Response> result = new CompletableFuture<>();

        Entry(String fingerprint) {
            this.fingerprint = fingerprint;
        }
    }

    static final class InMemoryIdempotency {
        private final ConcurrentMap<String, Entry> entries =
                new ConcurrentHashMap<>();

        Response execute(
                String scopedKey,
                String payload,
                Supplier<Response> operation) {

            String fingerprint = sha256(payload);
            Entry candidate = new Entry(fingerprint);
            Entry current = entries.putIfAbsent(scopedKey, candidate);

            if (current == null) {
                try {
                    Response response =
                            Objects.requireNonNull(operation.get());
                    candidate.result.complete(response);
                    return response;
                } catch (RuntimeException | Error error) {
                    candidate.result.completeExceptionally(error);
                    entries.remove(scopedKey, candidate);
                    throw error;
                }
            }

            if (!current.fingerprint.equals(fingerprint)) {
                throw new IllegalArgumentException(
                        "Idempotency key reused with a different request");
            }

            return current.result.join();
        }

        private static String sha256(String value) {
            try {
                byte[] digest = MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(digest);
            } catch (NoSuchAlgorithmException impossible) {
                throw new IllegalStateException(impossible);
            }
        }
    }

    public static void main(String[] args) {
        InMemoryIdempotency store = new InMemoryIdempotency();
        int[] executions = {0};

        String key = "tenant-17:CREATE_ORDER:client-key-42";
        String payload = "{\"customerId\":\"C-17\",\"quantity\":1}";

        Response first = store.execute(key, payload, () -> {
            executions[0]++;
            return new Response(201, "{\"orderId\":\"ORD-42\"}");
        });

        Response retry = store.execute(key, payload, () -> {
            executions[0]++;
            return new Response(201, "{\"orderId\":\"ORD-43\"}");
        });

        if (!first.equals(retry) || executions[0] != 1) {
            throw new AssertionError("Idempotency contract failed");
        }

        System.out.println("first=" + first.status() + " " + first.body());
        System.out.println("retry=" + retry.status() + " " + retry.body());
        System.out.println("businessExecutions=" + executions[0]);
    }
}
~~~

Chạy bằng Java 17:

~~~bash
javac IdempotencyDemo.java
java IdempotencyDemo
~~~

Stdout chính xác:

~~~text
first=201 {"orderId":"ORD-42"}
retry=201 {"orderId":"ORD-42"}
businessExecutions=1
~~~

Ví dụ này chỉ chứng minh cơ chế phối hợp thread trong **một process**. Nó không lưu bền vững qua restart, không chia sẻ trạng thái giữa nhiều instance và không có TTL. Map cũng giữ entry thành công vô thời hạn. Production cần database/Redis hoặc kho dùng chung có persistence, unique constraint/atomic claim và quy trình cleanup.

Trong demo, entry bị xóa khi operation ném exception nên lần gửi sau có thể thử lại. Chính sách này chỉ an toàn khi lỗi chắc chắn xảy ra trước side effect hoặc side effect đã rollback. Nếu operation đã commit side effect nhưng lỗi xảy ra trước khi lưu kết quả, xóa key và chạy lại có thể tạo tác động trùng. Production phải giải quyết trạng thái không chắc chắn bằng transaction chung, outbox, provider idempotency hoặc bước đối soát.

## 9. Thời hạn chống trùng (deduplication window / TTL)

Bản ghi idempotency không nhất thiết tồn tại mãi mãi. **TTL** xác định khoảng thời gian server cam kết nhận diện một key đã dùng và trả lại kết quả cũ.

Chọn TTL dựa trên:

- Thời gian retry tối đa của client, gateway và broker.
- Thời hạn redelivery của message broker.
- Thời gian người dùng có thể gửi lại thao tác từ giao diện.
- Độ trễ của job, lịch chạy lại và cơ chế khôi phục sau sự cố.
- Yêu cầu nghiệp vụ về việc không tạo giao dịch trùng.

TTL phải dài hơn toàn bộ cửa sổ retry/redelivery được hỗ trợ, cộng thêm biên an toàn cho độ trễ và vận hành. Ví dụ nếu broker có thể redeliver trong 48 giờ thì TTL 24 giờ không bảo vệ được các lần giao lại sau ngày đầu tiên.

Khi TTL hết hạn, cùng key có thể được xem như request mới nếu bản ghi đã bị xóa. Vì vậy:

- Nêu rõ TTL trong hợp đồng API/message.
- Chỉ xóa bản ghi đã hết hạn theo chính sách đã chọn.
- Không dùng thời điểm cleanup thực tế làm hợp đồng; job cleanup có thể chạy trễ.
- Cân nhắc lưu tombstone/key hash lâu hơn response body nếu nghiệp vụ vẫn cần ngăn thao tác trùng sau khi xóa kết quả lớn.
- Không xóa bản ghi **IN_PROGRESS** chỉ vì expires_at đã qua nếu worker còn có thể đang chạy; dùng lease và cơ chế thu hồi quyền có kiểm soát.

Ví dụ cleanup PostgreSQL:

~~~sql
DELETE FROM idempotency_record
WHERE state IN ('COMPLETED', 'FAILED_FINAL')
  AND expires_at < CURRENT_TIMESTAMP;
~~~

Lệnh này chỉ là ví dụ cho các bản ghi đã kết thúc. Cần batch delete để tránh transaction lớn trên bảng nhiều dữ liệu. Với bảng lớn, có thể partition theo thời gian hoặc dùng job cleanup có giới hạn. Bản ghi **IN_PROGRESS** cần xử lý riêng qua lease timeout, heartbeat worker và đối soát trước khi retry.

TTL là một phần của tính đúng đắn, không chỉ là tối ưu dung lượng. Xóa quá sớm có thể cho phép side effect lặp; giữ quá lâu làm tăng dung lượng và có thể ngăn một thao tác hợp lệ dùng lại key theo cách mà API không mong muốn.

## 10. Side effect bên ngoài và transactional outbox

Transaction database chỉ đảm bảo atomicity cho những thay đổi nằm trong cùng transaction manager/database. Nó không thể rollback một email đã gửi, một khoản thanh toán ở payment provider hoặc một message đã publish ra broker khác.

Ví dụ không an toàn:

1. Insert idempotency record.
2. Gọi payment provider và provider đã thu tiền.
3. Database transaction rollback vì lỗi lưu response.
4. Client retry và payment provider bị gọi lần nữa.

Có một khoảng thời gian không thể loại bỏ chỉ bằng **@Transactional**: side effect ngoài database đã xảy ra nhưng trạng thái local chưa được commit.

Các hướng xử lý:

- **Dùng idempotency key của provider:** truyền cùng key đến payment/email/remote API nếu provider hỗ trợ.
- **Transactional outbox:** trong cùng transaction với domain record và idempotency result, ghi một outbox event. Worker publish event và đánh dấu đã gửi; consumer vẫn cần dedup vì publish có thể lặp.
- **Inbox/dedup ở consumer:** lưu message ID cùng trạng thái xử lý và unique constraint để một message không tạo side effect local nhiều lần.
- **Saga/compensation:** với workflow nhiều dịch vụ, mô hình hóa các bước và hành động bù khi không thể rollback giao dịch đã hoàn tất ở dịch vụ khác.
- **Reconciliation:** định kỳ đối chiếu trạng thái provider với trạng thái local khi kết quả của một lời gọi bị mơ hồ.

Outbox không tự tạo exactly-once delivery. Nó giúp ghi ý định publish nguyên tử cùng thay đổi database; message vẫn có thể được gửi lại nên consumer phải idempotent.

## 11. Kiểm thử idempotency

Một bộ test tối thiểu nên bao gồm:

| Tình huống | Cách tạo | Kết quả cần xác nhận |
| --- | --- | --- |
| Gửi lần đầu | Key mới, payload hợp lệ | Nghiệp vụ chạy và response được lưu |
| Retry tuần tự | Cùng scope, key và fingerprint | Trả cùng response, nghiệp vụ chỉ chạy một lần |
| Retry đồng thời | Nhiều request cùng key đến cùng lúc | Chỉ một request claim và thực hiện side effect |
| Key khác payload | Cùng key, fingerprint khác | Conflict; không thực hiện nghiệp vụ lần hai |
| Mất response sau commit | Commit xong rồi ngắt response | Retry đọc và replay kết quả đã lưu |
| Rollback trước commit | Làm transaction thất bại | Không có kết quả COMPLETED giả; retry theo policy |
| Worker đang xử lý | Gửi duplicate khi trạng thái IN_PROGRESS | Chờ hoặc trả trạng thái đang xử lý; không chạy song song |
| Khác tenant | Cùng key nhưng tenant khác | Không lộ hoặc trả nhầm kết quả tenant khác |
| Hết TTL | Gửi lại sau khi hết thời hạn | Hành vi đúng theo hợp đồng TTL |
| Crash khi xử lý ngoài DB | Dừng worker sau side effect | Đối soát/provider key/outbox ngăn thực hiện trùng |
| Response lớn | Lưu và replay response nhiều dữ liệu | Kết quả không bị cắt hoặc serialize sai |

Trong unit test, mock service và dùng **AtomicInteger** để đếm số lần thực thi. Với test concurrency, dùng **CountDownLatch** hoặc barrier để cho các thread bắt đầu cùng thời điểm; không dựa vào **Thread.sleep**.

Trong integration test, chạy database thật (ví dụ PostgreSQL qua Testcontainers) và gửi nhiều transaction đồng thời cùng key. Assert unique constraint chỉ cho phép một bản ghi, domain resource chỉ được tạo một lần và mọi caller nhận cùng kết quả hoặc trạng thái đang xử lý theo thiết kế.

Một test quan trọng là **commit thành công nhưng response bị mất**. Hãy tạo request đầu tiên, commit dữ liệu, cố tình làm client không nhận được response, sau đó gửi lại cùng key. Nếu test chỉ gọi service hai lần tuần tự mà không mô phỏng tình huống mất response sau commit, nó chưa kiểm tra được failure mode quan trọng nhất.

## 12. Lỗi thiết kế thường gặp

- **Tạo key mới cho mỗi lần retry:** server không nhận ra hai request thuộc cùng thao tác.
- **Chỉ kiểm tra key bằng SELECT trước INSERT:** có race condition khi hai request đến đồng thời.
- **Không lưu fingerprint:** cùng key nhưng payload khác có thể nhận nhầm response.
- **Chỉ lưu key, không lưu kết quả:** request trùng biết đã từng chạy nhưng không thể replay kết quả theo hợp đồng.
- **Lưu kết quả trước khi nghiệp vụ commit:** có thể replay một kết quả cho nghiệp vụ đã rollback.
- **Giữ transaction mở khi gọi dịch vụ từ xa:** khóa DB lâu, tăng contention và vẫn không rollback được side effect ngoài hệ thống.
- **Xóa key ngay khi response gửi xong:** client có thể chưa nhận response và retry ngay sau đó.
- **TTL ngắn hơn cửa sổ redelivery:** message cũ đến muộn có thể thực hiện nghiệp vụ lần nữa.
- **Không giới hạn kích thước response record:** bảng idempotency có thể tăng dung lượng rất nhanh.
- **Giả định exactly-once end-to-end:** network, broker và dịch vụ ngoài vẫn có thể giao lặp; cần dedup ở mỗi ranh giới có side effect.

## 13. Checklist triển khai

- [ ] Client giữ nguyên key khi retry cùng một thao tác logic.
- [ ] Key có scope tenant/operation và được ràng buộc unique trong kho dùng chung.
- [ ] Fingerprint được tính từ request đã canonicalize.
- [ ] Cùng key nhưng request khác được từ chối rõ ràng.
- [ ] Claim key và cập nhật domain/result có transaction hoặc giao thức atomic phù hợp.
- [ ] Response/status/resource ID cần thiết được lưu để replay.
- [ ] Duplicate đang xử lý có hành vi được định nghĩa rõ.
- [ ] TTL dài hơn retry/redelivery window và có job cleanup an toàn.
- [ ] IN_PROGRESS có lease/recovery nếu xử lý kéo dài qua nhiều transaction.
- [ ] External side effect dùng provider idempotency, outbox, inbox hoặc reconciliation.
- [ ] Có test tuần tự, đồng thời, mất response sau commit, rollback, key conflict và hết TTL.
- [ ] Không ghi raw key hoặc payload nhạy cảm vào log nếu không cần thiết.

## Tài liệu tham khảo

- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework Reference — JDBC access](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [PostgreSQL — INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [Microservices.io — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
