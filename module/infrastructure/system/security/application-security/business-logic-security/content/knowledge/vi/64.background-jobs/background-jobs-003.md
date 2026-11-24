# Job retry safety

## 1. Retry an toàn là giữ nguyên ý nghĩa nghiệp vụ khi chạy lại

Background job là công việc được xử lý ngoài luồng request trực tiếp: hoàn tiền, cộng điểm, cấp quyền sau thanh toán, giải phóng tồn kho hoặc gửi thông báo. Job có thể được thực thi lại vì lỗi mạng, tiến trình dừng, mất xác nhận với hàng đợi, lease hết hạn hoặc người vận hành chủ động chạy lại.

**Job retry safety** là khả năng xử lý lại một công việc mà vẫn giữ đúng các quy tắc nghiệp vụ đã định nghĩa. Ví dụ, yêu cầu hoàn 100.000 đồng không được biến thành hai lần hoàn 100.000 đồng chỉ vì worker nhận job hai lần.

Mục tiêu không phải làm mọi dòng code chỉ chạy đúng một lần. Mục tiêu là kiểm soát tác động được commit, xử lý kết quả chưa xác định và ngăn retry trở thành cách vượt quyền, vượt hạn mức hoặc bỏ qua bước phê duyệt.

Một retry an toàn cần trả lời được:

- Đây có phải cùng một thao tác nghiệp vụ đã được chấp nhận hay là thao tác mới?
- Lần trước chưa làm gì, đã commit, hay vẫn chưa xác định được kết quả?
- Những điều kiện nào phải kiểm tra lại trước khi tạo tác động?
- Cơ chế nào ngăn hai worker cùng gây tác động?
- Khi nào phải dừng retry và chuyển sang đối chiếu hoặc xử lý thủ công?
- Ai có quyền yêu cầu chạy lại, và quyền đó cho phép đến đâu?

## 2. Vì sao một job có thể chạy nhiều lần?

### 2.1. Khoảng hở giữa commit và acknowledgement

Xét job cộng tiền hoàn vào ví nội bộ:

~~~text
1. Worker nhận message.
2. Worker cộng tiền vào ví trong database.
3. Database commit.
4. Worker gửi ACK cho broker.
~~~

Nếu worker chết sau bước 3 nhưng trước bước 4, broker có thể giao lại message. Worker mới không thể kết luận “job chưa làm” chỉ vì message vẫn còn trong hàng đợi.

Đảo thứ tự cũng không an toàn:

~~~text
1. Worker nhận message.
2. Worker gửi ACK.
3. Worker chết trước khi cộng tiền.
~~~

Khi đó công việc có thể bị mất khỏi hàng đợi mà nghiệp vụ chưa hoàn thành. Thứ tự thông thường là chỉ ACK sau khi kết quả xử lý đã được ghi bền vững theo thiết kế. Dù vậy, vẫn cần idempotency vì khoảng hở giữa commit và ACK không biến mất.

### 2.2. Timeout không đồng nghĩa chưa thực hiện

Một worker gọi dịch vụ thanh toán và gặp timeout có thể đang ở một trong các tình huống:

| Tình huống thực tế | Điều worker biết |
| --- | --- |
| Request chưa tới dịch vụ thanh toán | Chưa nhận được kết quả đúng hạn |
| Dịch vụ nhận request nhưng chưa xử lý xong | Chưa nhận được kết quả đúng hạn |
| Dịch vụ đã hoàn tiền, response bị mất | Chưa nhận được kết quả đúng hạn |

Cùng một lỗi timeout không cho biết tác động bên kia đã xảy ra hay chưa. Nếu tạo yêu cầu hoàn tiền mới sau mỗi timeout, hệ thống có thể hoàn nhiều lần.

### 2.3. Nhiều nguồn gây thực thi lại

- Broker giao lại message khi chưa thấy ACK hoặc visibility timeout đã hết.
- Scheduler phát lại job sau khi tiến trình bị dừng.
- Hai worker cùng nhận công việc do race condition.
- Người dùng nhấn lại nút hoặc API đầu vào nhận request retry.
- Người vận hành replay job từ dead-letter queue.
- Hệ thống khôi phục sau sự cố và quét các operation chưa có trạng thái cuối.
- Một worker chạy chậm vẫn tiếp tục sau khi worker khác đã tiếp quản.

Không nên dựa vào xác suất “tình huống này hiếm xảy ra”. Với tác vụ tiền, quyền hoặc tồn kho, bất biến phải được giữ ngay cả khi các tình huống này xảy ra.

## 3. Phân biệt operation, job, attempt và message

| Khái niệm | Ý nghĩa | Định danh minh họa |
| --- | --- | --- |
| Business operation | Ý định nghiệp vụ được chấp nhận, như thực hiện một yêu cầu hoàn tiền đã duyệt | `refund-request-781` |
| Job | Công việc kỹ thuật để thực hiện operation hoặc một bước của operation | `job-491` |
| Attempt | Một lần worker thử xử lý job | `attempt-3` |
| Message | Một lần phát hoặc giao dữ liệu qua hàng đợi | `message-206` |
| External request key | Khóa ổn định dùng để chống tác động trùng ở hệ thống ngoài nếu được hỗ trợ | `refund-request-781:provider-refund` |

Một operation có thể gồm nhiều job, mỗi job có nhiều attempt và mỗi message có thể được giao lại. Không lấy message ID mới hoặc attempt ID làm khóa idempotency của tác động nghiệp vụ.

Ví dụ:

~~~text
operation_id = refund-request-781
step         = credit-internal-wallet
job_id       = job-491
attempt_id   = attempt-1, attempt-2, attempt-3
effect_key   = refund-request-781:credit-internal-wallet
~~~

Effect key giữ nguyên khi chạy lại cùng bước nghiệp vụ. Nếu operation có thêm bước thông báo, bước đó cần khóa riêng; không dùng một trạng thái “đã xử lý” chung làm mất các bước chưa hoàn tất.

### 3.1. Idempotency không thay thế bất biến nghiệp vụ

Giả sử một người gửi cùng yêu cầu hoàn tiền với mười khóa khác nhau. Cơ chế khử trùng theo từng khóa có thể coi đó là mười operation khác nhau.

Do đó cần đồng thời:

1. **Idempotency:** cùng operation không tạo cùng tác động nhiều lần.
2. **Bất biến:** tổng tiền hoàn không vượt phần còn được hoàn, không hoàn cho ví khác, không thực hiện khi thiếu phê duyệt hoặc trạng thái không hợp lệ.
3. **Kiểm soát đầu vào:** API hoặc quy trình tạo operation không cho client dùng khóa mới để vượt qua quy tắc của một đơn hàng.

Một bảng `processed_messages` chỉ giúp với những bản sao dùng cùng message ID. Nó không tự nhận ra hai message khác nhau cùng yêu cầu thực hiện một tác động.

## 4. Xác lập các bất biến trước khi chọn thư viện retry

Với job hoàn tiền vào ví nội bộ, có thể đặt các bất biến:

| Bất biến | Cách bảo vệ minh họa |
| --- | --- |
| Một yêu cầu hoàn đã duyệt chỉ được ghi có một lần | Unique constraint theo tenant và refund request |
| Không hoàn quá số tiền được phép của đơn | Khóa hoặc cập nhật có điều kiện trên sổ theo dõi tiền đã hoàn và phần đã giữ chỗ |
| Không đổi người nhận khi retry | Lưu người nhận trong dữ liệu operation đã được kiểm chứng, không lấy từ payload mới |
| Tiền và lịch sử tác động cùng tồn tại | Ghi ledger, số dư, trạng thái operation và audit/outbox trong cùng transaction |
| Hai worker không cùng vượt qua điều kiện số tiền | Kiểm tra và thay đổi trong cơ chế cạnh tranh thích hợp |
| Retry không tự mở rộng quyền | Worker chỉ được thực hiện operation đã chấp nhận và các bước được phép |
| Kết quả chưa rõ không bị đổi thành “chưa thực hiện” | Có trạng thái đối chiếu, không tạo lệnh mới tùy tiện |
| Replay thủ công không xóa dấu vết cũ | Giữ operation ID, các attempt và người yêu cầu replay |

Nếu hệ thống đã giữ chỗ một phần hạn mức hoàn ở bước phê duyệt, bước thực hiện phải chuyển phần giữ chỗ sang phần đã hoàn theo đúng mô hình đó. Không cộng lại hoặc trừ lại hạn mức theo một công thức khác khi retry.

Tiền nên được biểu diễn bằng kiểu số chính xác và đơn vị nhỏ nhất phù hợp với đồng tiền. Dùng số thực nhị phân cho số dư hoặc tính fingerprint từ một biểu diễn số không ổn định có thể tạo lỗi độc lập với retry.

## 5. State machine phải thể hiện đúng mức độ chắc chắn

Một mô hình cho job có tác động bên ngoài:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING: Claim hợp lệ
    RETRY_WAIT --> RUNNING: Đến hạn và claim lại
    RUNNING --> SUCCEEDED: Có kết quả thành công bền vững
    RUNNING --> RETRY_WAIT: Lỗi có thể thử lại an toàn
    RUNNING --> FAILED_FINAL: Lỗi không thể xử lý bằng retry
    RUNNING --> RECONCILING: Chưa xác định tác động bên ngoài
    RECONCILING --> SUCCEEDED: Đối chiếu xác nhận thành công
    RECONCILING --> RETRY_WAIT: Xác nhận chưa tạo tác động và được phép thử lại
    RECONCILING --> FAILED_FINAL: Có kết luận cuối theo chính sách
    PENDING --> CANCELLED: Hủy trước tác động
    RETRY_WAIT --> CANCELLED: Hủy trước lần thực thi tiếp
~~~

Các điểm quan trọng:

- `RUNNING` cho biết đã claim, không chứng minh tác động đã hoàn tất.
- `SUCCEEDED` phải dựa trên kết quả bền vững, không chỉ việc hàm xử lý đã trả về trước commit.
- `RECONCILING` dùng khi cần xác định điều gì đã xảy ra; không tự đưa về `PENDING` như thể chưa có tác động.
- `FAILED_FINAL` không đồng nghĩa chưa từng có tác động. Cần phân biệt trạng thái job với kết quả từng bước nghiệp vụ.
- `CANCELLED` chỉ được ghi khi thỏa ngữ nghĩa hủy đã định nghĩa. Một yêu cầu hủy không tự đảo ngược tiền đã chuyển.
- Một lease hết hạn cho biết quyền sở hữu kỹ thuật cần được xem xét lại, không cho biết giao dịch bên ngoài đã thất bại.

Với operation có nhiều bước, lưu kết quả từng bước hoặc checkpoint nghiệp vụ. Không dùng một cờ `done` cho cả việc giữ chỗ, chuyển tiền, ghi nhận và gửi thông báo.

## 6. Thiết kế transaction cho tác động nội bộ

### 6.1. Ghi tác động và dấu vết chống trùng cùng nhau

Với tác động nằm trong một cơ sở dữ liệu, mẫu thiết kế quan trọng là:

~~~text
BEGIN
  Đọc/khóa operation đã được server chấp nhận.
  Nếu đã thực hiện cùng nội dung: lấy kết quả cũ.
  Nếu chưa thực hiện:
    Kiểm tra trạng thái, quyền thực thi và bất biến hiện tại.
    Ghi ledger hoặc thay đổi nghiệp vụ.
    Cập nhật dữ liệu tổng hợp nếu có.
    Ghi kết quả thực hiện theo operation ID duy nhất.
    Ghi audit/outbox.
COMMIT
Sau đó mới ACK message.
~~~

Nếu transaction rollback, tác động và dấu vết hoàn tất đều rollback. Nếu commit thành công nhưng worker không nhận được xác nhận commit, lần xử lý sau tra cứu cùng operation ID để xác định kết quả.

Không thực hiện theo mẫu:

~~~text
if not processed(operationId):
    creditWallet(amount)
    markProcessed(operationId)
~~~

Nếu ba thao tác không được bảo vệ bởi transaction và cơ chế cạnh tranh, hai worker đều có thể thấy “chưa xử lý” rồi cùng cộng tiền. Một unique constraint đặt sau tác động không nguyên tử cũng không hoàn tác được một lần gọi dịch vụ ngoài.

### 6.2. Ràng buộc dữ liệu là lớp bảo vệ cuối

Ví dụ bảng kết quả thực hiện:

~~~sql
CREATE TABLE refund_execution (
    tenant_id VARCHAR(80) NOT NULL,
    refund_request_id VARCHAR(80) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    wallet_id VARCHAR(80) NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency VARCHAR(3) NOT NULL,
    ledger_entry_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, refund_request_id)
);
~~~

Khóa chính khẳng định một yêu cầu hoàn trong một tenant chỉ có một kết quả thực hiện được ghi nhận. Ledger và dữ liệu liên quan cũng cần ràng buộc phù hợp với mô hình của hệ thống.

Ràng buộc duy nhất phải được dùng cùng transaction chứa tác động. Không diễn giải mọi lỗi unique constraint là thành công: cần xác định đúng ràng buộc bị vi phạm, rollback phần đang làm nếu cần, đọc kết quả đã commit và đối chiếu nội dung. Nếu worker cạnh tranh chưa commit hoặc đã rollback, phải xử lý theo trạng thái thực tế của cơ sở dữ liệu.

Không chỉ đọc từ replica có thể trễ rồi kết luận operation chưa thực hiện. Quyết định tạo tác động cần dựa trên nguồn dữ liệu và cơ chế nhất quán đủ mạnh để thực thi ràng buộc.

### 6.3. Fingerprint phải ràng buộc đúng nội dung

Một operation ID chỉ được gắn với một ý nghĩa nghiệp vụ. Fingerprint có thể dựa trên biểu diễn chuẩn hóa của:

~~~text
schema_version
tenant_id
refund_request_id
order_id
wallet_id
amount_minor
currency
operation_type
~~~

Nếu cùng operation ID xuất hiện với số tiền, ví nhận hoặc loại nghiệp vụ khác, phải từ chối xung đột, không dùng kết quả cũ cho lệnh mới.

Không đưa attempt ID, thời điểm retry hoặc trace ID vào fingerprint nghiệp vụ, vì chúng thay đổi hợp lệ giữa các lần thử. Cũng không hash JSON tùy ý mà bỏ qua khác biệt về thứ tự field, biểu diễn số hoặc giá trị mặc định.

Fingerprint giúp phát hiện nội dung không khớp; nó không chứng minh người gửi có quyền. Phải xác minh nguồn lệnh và đọc dữ liệu operation đáng tin ở server.

### 6.4. Pseudocode Java: hoàn vào ví nội bộ

Ví dụ sau giả định refund request đã được tạo và phê duyệt đúng quy trình. Message chỉ mang ID để worker tải lại dữ liệu; số tiền và ví nhận không được tin trực tiếp từ message. Các repository, ledger, số dư, kết quả thực hiện và outbox dùng cùng transaction.

~~~java
ExecutionResult executeRefund(
        TrustedWorkerContext worker,
        RefundJobMessage message) {

    validateMessageShape(message);

    // transaction() chỉ trả kết quả thành công sau khi commit hoàn tất.
    return database.transaction(tx -> {
        RefundRequest request = refundRequests.lockById(
                tx, message.tenantId(), message.refundRequestId());

        // Kiểm tra worker, tenant và ràng buộc message với operation bền vững.
        commandPolicy.requireTrustedReference(worker, message, request);

        String fingerprint = fingerprintOfCanonicalRequest(request);

        RefundExecution completed = executions.find(
                tx, request.tenantId(), request.id());

        if (completed != null) {
            completed.requireSameFingerprint(fingerprint);
            return completed.storedResult();
        }

        // Chỉ xét điều kiện tạo tác động mới sau khi loại nhánh đã hoàn tất.
        executionPolicy.requireExecutableNow(worker, request);
        request.requireApprovedAndNotCancelled();

        OrderRefundTotals totals = refundTotals.lockForUpdate(
                tx, request.tenantId(), request.orderId());

        Wallet wallet = wallets.lockForUpdate(
                tx, request.tenantId(), request.walletId());

        executionPolicy.requireCorrectRecipientAndCurrency(request, wallet);
        totals.requireRefundFitsRemainingAmount(request.amountMinor());

        LedgerEntry entry = ledger.appendRefundCredit(
                tx, request, fingerprint);

        wallet.creditExact(request.amountMinor());
        totals.recordExecutedRefund(request.amountMinor());
        request.markExecuted(entry.id());

        wallets.save(tx, wallet);
        refundTotals.save(tx, totals);
        refundRequests.save(tx, request);

        ExecutionResult result = ExecutionResult.from(request, entry);

        executions.insert(tx, request, fingerprint, result);
        auditOutbox.append(tx, RefundExecuted.from(request, entry));

        return result;
    });
}
~~~

Mã giả tập trung vào phần tạo tác động nguyên tử. Khi triển khai còn cần:

- Trật tự khóa thống nhất giữa các luồng và cách xử lý deadlock hoặc xung đột đồng thời.
- Kiểm tra kiểu tiền, tràn số, tiền tệ và giới hạn nghiệp vụ.
- Ràng buộc duy nhất trên operation và các bản ghi ledger liên quan.
- Ngữ nghĩa của phần tiền đã giữ chỗ nếu phê duyệt đồng thời giữ hạn mức.
- Chính sách thực thi đối với operation bị hủy, hết thời hạn hoặc bị thu hồi quyền.
- Cơ chế claim job và cập nhật trạng thái job không cho attempt cũ ghi đè attempt mới.

Ở ví dụ này, request đã hoàn tất được nhận diện trước khi kiểm tra lại trạng thái `APPROVED`. Nếu bắt mọi lần retry phải thấy request còn `APPROVED`, một operation đã chuyển sang `EXECUTED` sẽ bị coi là lỗi dù đang xử lý đúng bản sao của nó.

Điều đó không có nghĩa được bỏ kiểm soát truy cập khi trả dữ liệu kết quả cho người dùng. Worker nội bộ và API cho người dùng có ranh giới quyền khác nhau; API đọc kết quả vẫn phải xác minh quyền hiện tại.

### 6.5. Transactional outbox cho bước tiếp theo

Giả sử sau khi cộng ví cần phát sự kiện để gửi thông báo. Nếu commit tiền rồi mới publish message, worker có thể chết giữa hai bước và làm mất thông báo. Nếu publish trước commit, dịch vụ thông báo có thể nói “đã hoàn tiền” trong khi transaction bị rollback.

Ghi outbox cùng transaction giải quyết khoảng hở giữa thay đổi nội bộ và ý định phát sự kiện. Relay chuyển các hàng đã commit và có thể chuyển lại khi mất xác nhận.

Consumer vẫn cần xử lý bản sao. Một hàng outbox duy nhất không bảo đảm message chỉ đến một lần, cũng không làm tác động của consumer tự trở nên idempotent.

## 7. Tác động bên ngoài cần chiến lược riêng

### 7.1. Không giữ transaction mở để hy vọng bao phủ HTTP

Transaction database nội bộ không rollback được một lần hoàn tiền đã thành công ở dịch vụ thanh toán. Giữ khóa database trong khi chờ HTTP còn kéo dài thời gian chiếm khóa và có thể gây nghẽn hệ thống.

Một luồng phù hợp hơn:

1. Ghi operation và ý định gửi lệnh ra ngoài một cách bền vững.
2. Dùng operation/step key ổn định khi gọi hệ thống ngoài.
3. Ghi lại tham chiếu giao dịch ngoài và kết quả đã xác minh.
4. Khi kết quả chưa rõ, đối chiếu theo cùng key hoặc tham chiếu, không tạo operation mới.
5. Chỉ thực hiện các bước phụ thuộc sau khi có mức xác nhận mà nghiệp vụ yêu cầu.

Nếu hệ thống ngoài có idempotency, cần hiểu phạm vi khóa, thời gian giữ khóa, điều kiện so khớp payload và cách truy vấn trạng thái của chính hệ thống đó. Không giả định một khóa sẽ có hiệu lực vô hạn.

### 7.2. Luồng minh họa khi mất response

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant DB as Database nội bộ
    participant P as Dịch vụ thanh toán

    W->>DB: Đọc operation và key bền vững
    W->>P: Hoàn tiền với key của operation
    P->>P: Thực hiện hoặc tìm kết quả cùng key
    P--xW: Response bị mất
    W->>DB: Ghi trạng thái cần đối chiếu
    W->>P: Tra cứu trạng thái theo key/tham chiếu
    P-->>W: Kết quả đủ tin cậy
    W->>DB: Ghi kết quả và bước tiếp theo
~~~

Nếu worker chết trước khi ghi trạng thái cần đối chiếu, bộ phục hồi phải có thể nhận ra operation đang gửi dở từ dữ liệu đã lưu trước lời gọi ngoài. Không để key chỉ tồn tại trong bộ nhớ của attempt đã chết.

Nếu hệ thống ngoài không hỗ trợ idempotency hoặc tra cứu đáng tin, không thể bảo đảm an toàn chỉ bằng vòng lặp retry phía client. Cần cơ chế đối chiếu khác, giới hạn retry tự động hoặc bước xử lý thủ công theo mức rủi ro của nghiệp vụ.

### 7.3. Một job có nhiều tác động

Một job làm lần lượt:

~~~text
Hoàn tiền -> cộng lại điểm -> gửi email
~~~

Nếu email thất bại, không được chạy lại toàn bộ đoạn code và hoàn tiền thêm lần nữa. Mỗi bước cần trạng thái, khóa tác động và điều kiện chuyển bước riêng.

Bước bù trừ trong saga cũng phải có operation ID và tính an toàn khi retry. Bù trừ là một hành động nghiệp vụ mới có quy tắc riêng; không phải phép rollback tuyệt đối xóa mọi tác động ngoài hệ thống.

Với email hoặc SMS, có thể chấp nhận mức bảo đảm khác với tiền, nhưng cần định nghĩa rõ. Việc ghi “đã gửi” trước khi gọi nhà cung cấp có thể làm mất thông báo; ghi sau lời gọi có thể tạo gửi trùng khi mất response. Chọn cơ chế chống trùng, tra cứu hoặc chấp nhận bản sao dựa trên khả năng nhà cung cấp và yêu cầu sản phẩm.

## 8. Claim, lease và fencing không thay thế idempotency

### 8.1. Claim phải là thao tác nguyên tử

Mẫu “đọc job chưa chạy rồi đánh dấu đang chạy” có thể để hai worker cùng nhận job. Cần claim bằng cơ chế nguyên tử, chẳng hạn cập nhật có điều kiện hoặc khóa phù hợp với cơ sở dữ liệu.

Một claim có thể ghi:

~~~text
job_id
lease_owner
lease_expires_at
claim_version
attempt_id
~~~

Chỉ attempt đang sở hữu claim hợp lệ được gia hạn lease hoặc cập nhật trạng thái điều phối tương ứng. Khi cập nhật, dùng điều kiện như `job_id + claim_version + lease_owner`, không chỉ `job_id`.

### 8.2. Lease hết hạn không làm worker cũ dừng chạy

Ví dụ:

~~~text
T0: Worker A nhận claim version 10.
T1: A bị pause lâu hoặc mất kết nối.
T2: Lease hết hạn; B nhận claim version 11.
T3: A tiếp tục chạy.
~~~

Nếu chỉ dựa vào lease, A và B có thể cùng tạo tác động. Heartbeat giúp phát hiện và giảm khả năng chồng lấn, nhưng không phải bằng chứng rằng worker cũ đã ngừng.

Với tác động trong database, phải kết hợp kiểm tra quyền sở hữu hiện hành ở transaction thích hợp và ràng buộc chống trùng theo operation. Với hệ thống ngoài, dùng khóa tác động ổn định hoặc cơ chế được bên nhận thực thi.

### 8.3. Fencing cần được nơi tạo tác động kiểm tra

Fencing token là số phiên bản tăng dần dùng để phát hiện người giữ quyền cũ. Nó chỉ có tác dụng khi nơi nhận thao tác kiểm tra token theo đúng phạm vi tài nguyên và từ chối token cũ theo thiết kế.

Chỉ ghi token vào log hoặc message không tạo ra khả năng fencing. Token tăng theo từng job cũng không tự sắp thứ tự hai job khác nhau cùng ghi một tài nguyên.

Cần định nghĩa cơ chế đăng ký hoặc ghi nhận token mới, mốc có hiệu lực và ràng buộc với tài nguyên đích. Đừng suy ra rằng cứ cấp token mới ở scheduler là hệ thống ngoài đã biết để chặn token cũ.

Fencing bảo vệ trước worker lỗi thời; idempotency bảo vệ trước thực hiện trùng một tác động. Một hệ thống có thể cần cả hai.

### 8.4. Attempt cũ không được ghi đè kết quả mới

Sau khi B đã hoàn tất, A không được đặt job về `RETRY_WAIT` vì nó vừa nhận timeout từ một lời gọi cũ. Cập nhật trạng thái phải kiểm tra claim version và state transition được phép.

Nếu cập nhật claim bị từ chối, attempt cũ dừng điều phối tiếp theo. Tuy nhiên, vẫn phải xác định tác động nó có thể đã gửi đi; mất quyền cập nhật trạng thái không làm tác động bên ngoài tự biến mất.

## 9. Chính sách retry: phân loại trước, lên lịch sau

### 9.1. Ba câu hỏi độc lập

Trước khi retry, cần phân biệt:

1. **Lỗi có thể hết sau một thời gian không?**
2. **Thử lại có an toàn về tác động không?**
3. **Operation còn được phép thực hiện tại thời điểm này không?**

Một lỗi mạng có thể là tạm thời nhưng tác động hoàn tiền đang chưa rõ. Ngược lại, một transaction bị database xác nhận rollback có thể thử lại phần transaction nếu operation vẫn hợp lệ.

| Loại kết quả | Hướng xử lý |
| --- | --- |
| Dữ liệu sai định dạng hoặc schema không hỗ trợ | Dừng hoặc cách ly message; không retry vô hạn |
| Thiếu phê duyệt, sai tenant, sai người nhận | Từ chối; chỉ thay đổi qua quy trình nghiệp vụ có quyền |
| Hết hạn thực thi hoặc trạng thái không còn cho phép | Kết thúc/hủy theo chính sách, không tự vượt điều kiện |
| Deadlock hoặc xung đột được xác nhận rollback | Có thể retry toàn transaction trong giới hạn |
| Dịch vụ phụ thuộc tạm thời không khả dụng | Backoff nếu operation vẫn an toàn để thử lại |
| Timeout khi tạo tác động ngoài hệ thống | Đối chiếu hoặc thử lại cùng key theo bảo đảm của bên nhận |
| Lỗi lập trình lặp lại với cùng dữ liệu | Cách ly và xử lý nguyên nhân; retry dày chỉ tăng tải |
| Đã có kết quả cùng operation và nội dung khớp | Dùng kết quả cũ, không tạo tác động mới |

Không ánh xạ máy móc mọi HTTP 5xx thành “chắc chắn chưa làm”. Một server có thể tạo tác động rồi lỗi khi dựng response. Tương tự, mã HTTP không thay thế hợp đồng nghiệp vụ về trạng thái cuối.

### 9.2. Backoff có jitter

Một chính sách minh họa:

~~~text
cap(n) = min(max_delay, base_delay * 2^(n - 1))
delay(n) = random_uniform(0, cap(n))
~~~

Trong đó `n = 1` là lần retry đầu tiên sau lần xử lý ban đầu. Ví dụ `base_delay = 1 giây`, `max_delay = 60 giây` chỉ là các giá trị minh họa; thực tế phải phù hợp với thời gian xử lý và giới hạn dịch vụ.

Jitter làm các worker giãn thời điểm thử lại. Backoff giảm áp lực lên hệ thống phụ thuộc; cả hai không sửa được lỗi cộng tiền trùng.

Nếu bên nhận yêu cầu thời gian chờ tối thiểu hợp lệ, lịch retry phải tôn trọng mốc đó. Đồng thời giới hạn phép tính để tránh tràn số khi attempt count lớn.

### 9.3. Giới hạn theo nhiều chiều

Nên định nghĩa rõ:

- Số attempt tối đa, bao gồm hay không bao gồm lần đầu.
- Tổng thời gian hoặc deadline của operation.
- Thời gian tối đa cho mỗi lần gọi.
- Số job đồng thời theo dịch vụ phụ thuộc, tenant hoặc loại nghiệp vụ.
- Retry budget để một đợt sự cố không tiêu thụ toàn bộ tài nguyên.
- Cách xử lý operation đã hết budget nhưng kết quả bên ngoài vẫn chưa rõ.

Một chuỗi ba tầng đều retry ba lần có thể khuếch đại số lần gọi tới tầng sâu. Cần phối hợp các tầng, thay vì bật retry độc lập ở HTTP client, service và worker mà không tính tổng.

Không giữ thread ngủ lâu chỉ để chờ retry nếu nền tảng có cơ chế lịch bền vững. Lưu `next_attempt_at` hoặc dùng cơ chế delay thích hợp, để tiến trình khởi động lại vẫn tiếp tục được.

### 9.4. Poison message và dead-letter queue

Poison message là message gây lỗi lặp lại, chẳng hạn sai schema hoặc dữ liệu không thể xử lý. Đưa vào dead-letter queue giúp bảo vệ luồng xử lý chính, nhưng không giải quyết nguyên nhân hay chứng minh nghiệp vụ chưa tạo tác động.

Bản ghi cách ly cần có operation ID, lỗi đã phân loại, số attempt và trạng thái tác động đã biết. Tránh lưu nguyên payload chứa bí mật hoặc dữ liệu nhạy cảm chỉ để thuận tiện debug.

Nếu hết retry budget trong khi kết quả thanh toán chưa rõ, giữ trạng thái nghiệp vụ cần đối chiếu. Đừng đổi nó thành “thất bại chắc chắn” chỉ vì message đã vào DLQ.

## 10. Giữ ranh giới quyền khi retry và replay

### 10.1. Worker không trở thành người dùng toàn quyền

Worker thường có quyền kỹ thuật rộng để truy cập dữ liệu. Quyền đó không được dùng để bỏ qua phê duyệt, quyền theo đối tượng hoặc các bất biến mà API ban đầu phải tuân thủ.

Một message an toàn thường chỉ tham chiếu operation bền vững đã được server chấp nhận. Worker tải lại tenant, người nhận, số tiền, phiên bản chính sách và trạng thái từ nguồn đáng tin, đồng thời kiểm tra message đúng loại và đúng operation.

Nếu payload cho phép đặt tên class, biểu thức, URL tùy ý hoặc câu lệnh động, retry có thể lặp lại một hành động nguy hiểm do người gửi kiểm soát. Chỉ hỗ trợ loại job và trường dữ liệu được cho phép; không biến queue thành công cụ thực thi tùy ý.

### 10.2. Quyền lúc chấp nhận và quyền lúc thực thi

Cần phân biệt hai mô hình:

| Mô hình | Ví dụ | Điều phải quy định |
| --- | --- | --- |
| Tiếp tục cam kết đã được chấp nhận bền vững | Hoàn tiền đã duyệt và giữ hạn mức | Ai có thể hủy, thời hạn cam kết, trạng thái nào còn cho thực hiện |
| Hành động mới cần quyền hiện tại | Job xuất dữ liệu nhạy cảm theo quyền truy cập hiện thời | Quyền và phạm vi phải được kiểm tra lại khi thực thi |

Không mặc định “người tạo job mất quyền thì mọi việc cũ phải hủy”, cũng không mặc định “đã vào queue thì luôn được làm”. Chính sách của từng loại operation phải trả lời được điều này.

Nếu operation được khởi tạo trong phiên impersonation, giữ cả người thao tác thật, effective subject và danh tính worker. Retry không được xóa dấu vết actor gốc hoặc mở rộng scope đã cấp.

### 10.3. Replay thủ công là một hành động cần kiểm soát

Công cụ replay nên:

- Yêu cầu quyền theo loại job, tenant và mức nhạy cảm của nghiệp vụ.
- Giữ nguyên operation ID và effect key khi tiếp tục cùng tác động.
- Hiển thị trạng thái đã biết, lý do lỗi và kết quả đối chiếu trước khi chạy lại.
- Ghi người yêu cầu replay, lý do, thời điểm và attempt mới.
- Không cho sửa số tiền hoặc người nhận bằng cách chỉnh payload rồi giữ tên “retry”.

Nếu cần sửa nội dung nghiệp vụ, đó là thay đổi operation hoặc một operation mới qua quy trình có quyền, không phải retry nguyên trạng. Không cung cấp nút xóa bản ghi idempotency để ép job chạy lại như một lối xử lý thông thường.

Quyền replay phải được kiểm tra ở server. Ẩn nút trên giao diện không ngăn người dùng gọi endpoint trực tiếp hoặc gửi lại yêu cầu cũ.

## 11. Dữ liệu thay đổi trong thời gian chờ retry

Một job có thể chờ nhiều phút hoặc lâu hơn. Trong thời gian đó, đơn hàng bị hủy, tài khoản nhận bị khóa hoặc chính sách thực thi thay đổi.

Cần tách hai nhóm dữ liệu:

- **Nội dung đã cam kết:** operation ID, số tiền đã duyệt, tiền tệ, người nhận và căn cứ phê duyệt. Retry không tự lấy payload mới để thay những giá trị này.
- **Điều kiện phải còn đúng lúc tạo tác động:** trạng thái operation, quyền thực thi theo chính sách, hạn mức còn lại, tình trạng tài khoản và điều kiện chuyển trạng thái.

Ví dụ, job xử lý đơn hàng không được tự tính lại mức giá từ một tham số giá do client sửa trong message retry. Nhưng nó vẫn có thể phải từ chối nếu đơn đã bị hủy trước khi tác động được tạo.

Nếu có ràng buộc theo version, cần định nghĩa version nào thuộc nội dung cam kết và version nào chỉ phản ánh thay đổi đồng thời. Không đưa mọi version hiện tại vào khóa idempotency để biến một lần retry thành operation mới.

### 11.1. Race giữa hủy và thực thi

Nếu yêu cầu hủy và job cùng thao tác operation, cần khóa hoặc cập nhật có điều kiện để xác lập thứ tự:

~~~text
Nếu hủy có hiệu lực trước khi thực thi:
  Worker không được tạo tác động mới.

Nếu thực thi đã commit trước khi hủy:
  Hủy không được ghi như thể tác động chưa từng xảy ra.
  Nếu được phép đảo tác động, tạo luồng bù trừ hoặc operation riêng.
~~~

Với hệ thống ngoài, có thể còn khoảng thời gian chưa rõ kết quả. Ghi “đã yêu cầu hủy” khác với “đã hủy chắc chắn”; cần đối chiếu theo khả năng của bên nhận.

## 12. Audit, giám sát và vòng đời dữ liệu chống trùng

### 12.1. Theo dõi attempt mà không nhân bản thành công nghiệp vụ

Mỗi attempt nên truy được:

~~~text
operation_id, job_id, step
attempt_id, claim_version, worker_id
actor_id hoặc initiating_actor_id nếu có
tenant_id
started_at, finished_at
outcome, error_category, reason_code
next_attempt_at
external_reference nếu có
~~~

Sự kiện `attempt.failed` không có nghĩa operation chắc chắn thất bại. Sự kiện `refund.executed` phải được gắn với tác động đã commit hoặc xác nhận nghiệp vụ đủ tin cậy.

Một operation hoàn tiền có thể có ba attempt lỗi ở tầng mạng, một kết quả hoàn tiền thực tế và hai lần chuyển phát cùng sự kiện. Báo cáo tài chính phải dựa trên ledger và operation, không đếm số dòng log chứa từ “success”.

Không ghi credential, token nhà cung cấp, dữ liệu thẻ hoặc toàn bộ request vào audit. Chỉ lưu thông tin cần thiết để liên kết và điều tra.

### 12.2. Những chỉ số hỗ trợ phát hiện rủi ro

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Số attempt trên mỗi operation | Có lỗi lặp lại hoặc vòng retry bất thường không? |
| Tuổi job và thời gian chờ | Có operation bị treo hoặc hết deadline không? |
| Số operation cần đối chiếu | Có nhiều kết quả bên ngoài đang chưa xác định không? |
| Lease hết hạn, claim cạnh tranh | Có worker xử lý chậm hoặc cấu hình lease chưa phù hợp không? |
| Xung đột fingerprint | Có client, công cụ replay hoặc producer đang đổi nội dung cùng key không? |
| Số message vào DLQ | Có poison message hay lỗi hệ thống chưa xử lý không? |
| Độ trễ outbox và lỗi consumer | Bước tiếp theo có đang thiếu sự kiện không? |
| Tác động nghiệp vụ trên mỗi operation | Ràng buộc một tác động có bị phá vỡ không? |

Idempotency hit thường là dấu hiệu cơ chế chống trùng đang hoạt động, không tự nó chứng minh có tấn công. Cần đặt trong ngữ cảnh tần suất, actor, tenant và loại nghiệp vụ.

### 12.3. Không xóa dấu vết chống trùng quá sớm

Nếu bản ghi idempotency chỉ giữ một ngày nhưng job có thể được replay sau một tuần, operation cũ có thể bị thực hiện lại sau khi dấu vết đã hết hạn.

Thời gian bảo vệ phải xét toàn bộ khả năng phát lại: broker, DLQ, backup, công cụ vận hành và thời hạn key của hệ thống ngoài. Cache idempotency ngắn hạn có thể phục vụ API, nhưng tác động tài chính thường cần ràng buộc nghiệp vụ bền vững hơn cache.

Nếu lưu trữ lạnh ledger hoặc kết quả cũ, cần giữ khả năng xác định operation đã thực hiện bằng một cơ chế thích hợp, chẳng hạn chỉ mục hoặc dấu vết chống trùng vẫn được thực thi khi replay. Không chỉ di chuyển dữ liệu ra khỏi nơi kiểm tra rồi coi như operation chưa có.

Đối chiếu định kỳ các operation với ledger, tham chiếu hệ thống ngoài và sự kiện hoàn tất. Không tự sửa số dư dựa trên một log thiếu; cần xác minh nguồn dữ liệu nghiệp vụ và nguyên nhân chênh lệch.

## 13. Ví dụ xuyên suốt: một lần hoàn tiền, ba attempt

Một yêu cầu hoàn 100.000 đồng vào ví nội bộ đã được duyệt cho đơn hàng cụ thể:

~~~text
operation_id = refund-request-781
tenant_id    = tenant-a
wallet_id    = wallet-901
amount_minor = 100000
currency     = VND
~~~

Luồng xử lý:

1. Attempt 1 mở transaction, kiểm tra phê duyệt, người nhận và số tiền còn được hoàn.
2. Ledger, số dư, kết quả thực hiện và audit/outbox cùng commit.
3. Worker chết trước khi gửi ACK.
4. Attempt 2 nhận lại message, tải cùng operation từ database và tìm thấy kết quả đã commit.
5. Worker đối chiếu fingerprint, không cộng thêm tiền, rồi thử ACK.
6. Kết nối broker lại gặp lỗi, message được giao lần nữa.
7. Attempt 3 vẫn dùng cùng operation, nhận kết quả cũ và ACK thành công.

Kết quả đúng:

- Ví chỉ tăng 100.000 đồng.
- Có một tác động ghi có cho yêu cầu hoàn này.
- Có thể có ba bản ghi attempt và nhiều bản sao chuyển phát sự kiện, nhưng sự kiện tác động giữ định danh ổn định.
- Người điều tra truy được yêu cầu phê duyệt, actor khởi tạo và các lần xử lý.

Những nhánh tấn công hoặc sai triển khai cần bị chặn:

- Thay wallet ID trong message retry để chuyển tiền sang ví khác.
- Gửi cùng operation ID với số tiền lớn hơn.
- Dùng operation ID mới để hoàn thêm khi đã hết hạn mức của đơn.
- Replay một job bị hủy rồi bỏ qua kiểm tra trạng thái.
- Xóa bản ghi chống trùng để ép hệ thống cộng tiền lại.
- Dùng quyền worker để tự tạo một refund request thiếu phê duyệt.

Nếu đây là hoàn tiền qua nhà cung cấp ngoài, các bước 4–5 phải dựa trên kết quả nội bộ đủ tin cậy hoặc quy trình tra cứu cùng key. Không suy ra đã hoàn hay chưa hoàn chỉ từ việc một bản ghi local chưa có trạng thái cuối.

## 14. Kiểm thử retry safety bằng cách tạo lỗi có chủ đích

Cần kiểm tra dữ liệu bền vững và tác động thực tế, không chỉ số lần gọi hàm hay response của worker.

| Tình huống | Kết quả cần kiểm chứng |
| --- | --- |
| Giao cùng message nhiều lần | Một tác động cho cùng operation, các attempt có thể khác nhau |
| Hai message khác nhau cùng tham chiếu operation | Không tạo thêm tác động chỉ vì message ID khác |
| Hai worker xử lý đồng thời | Ràng buộc transaction/unique giữ đúng kết quả và bất biến |
| Lỗi sau khi sửa số dư nhưng trước khi ghi execution | Transaction rollback toàn bộ; không còn số dư thay đổi đơn lẻ |
| Lỗi sau khi ghi execution nhưng trước commit | Không nhìn thấy kết quả hoàn tất từ bên ngoài transaction |
| Commit thành công rồi mất ACK | Retry tìm kết quả cũ, không cộng tiền lại |
| Mất xác nhận commit từ database | Xác định qua cùng operation ID, không tạo operation mới |
| Timeout sau khi nhà cung cấp đã hoàn tiền | Đối chiếu hoặc dùng cùng key; không tạo lệnh hoàn mới |
| Timeout khi request chưa tới nhà cung cấp | Có thể tiếp tục theo cơ chế an toàn, vẫn giữ key của tác động |
| Worker cũ tiếp tục sau khi lease hết hạn | Không tạo tác động trùng hoặc ghi đè trạng thái của claim mới |
| Cùng key nhưng payload khác | Từ chối xung đột, không dùng kết quả cũ cho nội dung mới |
| Dùng key mới để vượt số tiền còn được hoàn | Bất biến tài chính chặn tác động |
| Hai refund request khác nhau cùng tranh hạn mức | Tổng đã hoàn/giữ chỗ vẫn trong giới hạn theo mô hình nghiệp vụ |
| Hủy đồng thời với thực thi | Kết quả theo thứ tự hiệu lực đã định nghĩa, không giả vờ đảo tác động |
| Job thiếu phê duyệt hoặc sai tenant | Từ chối dù worker có quyền kỹ thuật truy cập database |
| Retry sau khi quyền/ngữ cảnh thay đổi | Tuân thủ mô hình cam kết hoặc kiểm tra quyền hiện tại đã chọn |
| Khôi phục job cũ sau khi cache idempotency hết hạn | Ràng buộc nghiệp vụ bền vững vẫn ngăn tác động trùng |
| Replay từ DLQ | Giữ operation/effect key và có audit người yêu cầu |
| Một bước thông báo thất bại sau khi tiền đã chuyển | Chỉ xử lý lại bước chưa hoàn tất; không chuyển tiền lần nữa |
| Lỗi dữ liệu lặp lại | Dừng/cách ly đúng chính sách; không retry vô hạn |
| Nhiều tenant cùng bị lỗi dịch vụ phụ thuộc | Retry budget và giới hạn đồng thời tránh một tenant chiếm hết tài nguyên |
| Relay phát lại sự kiện | Consumer xử lý bản sao mà không nhân bản tác động nghiệp vụ |

Với concurrency, dùng điểm đồng bộ để chủ động tạo hai worker đi qua các ranh giới kiểm tra/ghi. Một test chạy nhiều lần tuần tự không chứng minh an toàn khi có race.

Với transaction, kiểm tra dữ liệu sau commit hoặc rollback từ một kết nối độc lập. Đặc biệt kiểm tra ledger, số dư, execution và outbox có cùng tồn tại hoặc cùng không tồn tại theo thiết kế.

Với hệ thống ngoài, dùng mô phỏng có thể tạo hai trường hợp khác nhau: “đã thực hiện nhưng mất response” và “chưa nhận request”. Nếu mọi timeout giả đều xảy ra trước tác động, test sẽ bỏ sót tình huống nguy hiểm nhất.

Với chính sách thời gian, dùng đồng hồ điều khiển được để kiểm tra deadline, lease và lịch retry. Điều này giúp xác minh ranh giới chính xác mà không phải chờ thời gian thực dài.

## 15. Tiêu chí hoàn thành thiết kế

Trước khi bật retry tự động cho một job nhạy cảm, cần xác định được:

- Operation ID và khóa tác động ổn định qua mọi attempt, redelivery và replay.
- Nội dung cam kết được ràng buộc với operation; thay payload không trở thành retry hợp lệ.
- Bất biến về tiền, trạng thái, quyền và đối tượng được giữ dưới cạnh tranh.
- Transaction bao phủ tác động nội bộ và dấu vết hoàn tất; lời gọi ngoài có cơ chế xác nhận riêng.
- ACK, claim, lease và cập nhật trạng thái không khiến mất việc hoặc ghi đè kết quả mới.
- Kết quả chưa xác định có đường đối chiếu, không bị diễn giải như chưa thực hiện.
- Retry có phân loại lỗi, backoff, budget và điểm dừng cụ thể.
- Replay thủ công có quyền, audit và không làm mất dấu vết chống trùng.
- Dữ liệu chống trùng còn hiệu lực trong toàn bộ khoảng có thể phát lại công việc.
- Các ranh giới lỗi quan trọng có cách kiểm thử được tác động nghiệp vụ thực tế.

Retry chỉ nên được bật sau khi đã định nghĩa điều gì được phép lặp và điều gì chỉ được tạo tác động một lần. Trong bảo mật logic nghiệp vụ, khả năng phục hồi có giá trị khi nó giữ được các quy tắc về phê duyệt, quyền theo đối tượng, transaction và idempotency của operation.
