# Idempotency record storage

## 1. Mục tiêu và phạm vi

Trong một API tạo đơn hàng, hoàn tiền hoặc phê duyệt giao dịch, client có thể gửi lại cùng một yêu cầu vì timeout, mất kết nối hoặc thao tác lặp. Kẻ tấn công cũng có thể chủ động gửi nhiều yêu cầu đồng thời để khai thác cửa sổ xử lý. Nếu server chỉ nhớ kết quả trong bộ nhớ của một tiến trình, việc khởi động lại hoặc chuyển request sang instance khác có thể làm tác dụng nghiệp vụ xảy ra thêm lần nữa.

**Idempotency record** là bản ghi bền vững liên kết một định danh yêu cầu với phạm vi của nó, nội dung yêu cầu và kết quả xử lý. Thiết kế nơi lưu bản ghi này quyết định hệ thống có thực sự ngăn thực thi lặp hay chỉ giảm xác suất thực thi lặp.

Trong phạm vi bảo mật logic nghiệp vụ, mục tiêu không dừng ở việc trả cùng một HTTP response. Các bất biến cần bảo vệ còn gồm:

- Một ý định hoàn tiền hợp lệ không tạo ra hai lần hoàn tiền.
- Cùng một key nhưng khác nội dung không được thực hiện như một yêu cầu mới.
- Bản ghi của người dùng hoặc tenant khác không trở thành nguồn rò rỉ dữ liệu.
- Một kết quả đã báo thành công phải có dữ liệu nghiệp vụ tương ứng được commit.
- Retry sau sự cố không vượt qua phê duyệt, quyền theo đối tượng hoặc giới hạn nghiệp vụ.

Bài học tập trung vào cấu trúc lưu trữ, ràng buộc dữ liệu, transaction, vòng đời bản ghi và các điểm lỗi ảnh hưởng đến những bất biến này.

## 2. Bản ghi cần trả lời những câu hỏi nào?

Một bản ghi chỉ chứa `key → response` thường chưa đủ. Khi nhận request, server cần trả lời:

1. Key này thuộc tenant, chủ thể và thao tác nào?
2. Request mới có cùng ý nghĩa với request đã nhận trước đó không?
3. Đã có một lần xử lý được quyền thực thi chưa?
4. Tác dụng nghiệp vụ đã commit, đang xử lý hay chưa xác định được?
5. Có thể trả lại kết quả nào cho người gọi hiện tại?
6. Bản ghi phải được giữ đến khi nào và xóa theo điều kiện nào?

Ví dụ một request hoàn tiền có thể sử dụng định danh tra cứu:

```text
tenant_id       = tenant-A
subject_id      = user-17
operation       = refund.create.v1
idempotency_key = 79e1f884-3b39-4cb1-b07f-3c09b872bc4a
```

Đây là khóa nhận diện một lần gửi lệnh trong phạm vi đã chọn. Nó không tự chứng minh người gọi sở hữu đơn hàng, được phép hoàn tiền hoặc số tiền hoàn là hợp lệ.

## 3. Các trường dữ liệu quan trọng

| Nhóm | Trường điển hình | Vai trò |
|---|---|---|
| Định danh | `record_id` | Định danh nội bộ cho một thế hệ bản ghi; hữu ích khi đối soát và chống cập nhật nhầm bản ghi đã bị thay thế |
| Phạm vi | `tenant_id`, `subject_id`, `operation` | Ngăn va chạm hoặc truy cập chéo tenant, chủ thể và loại thao tác |
| Key | `idempotency_key` | Định danh request do client gửi, được kiểm tra định dạng và độ dài |
| So khớp | `request_fingerprint`, `fingerprint_version` | Phát hiện việc dùng lại cùng key cho nội dung khác |
| Tiến trình | `status` | Thể hiện trạng thái xử lý theo mô hình lưu trữ đã chọn |
| Kết quả | `response_status`, `response_headers`, `response_body` | Lưu ảnh chụp phản hồi cần phát lại |
| Liên kết nghiệp vụ | `business_resource_id` | Trỏ tới giao dịch, đơn hàng hoặc kết quả để đối soát |
| Thời gian | `created_at`, `completed_at`, `expires_at` | Quản lý vòng đời, đo độ trễ và xác định thời điểm đủ điều kiện dọn dẹp |
| Quyền thực thi, nếu cần | `owner_token`, `generation`, `lease_until` | Điều phối worker khi trạng thái đang xử lý được commit riêng |

Không phải thiết kế nào cũng cần toàn bộ các trường. Đặc biệt, mô hình xử lý trọn vẹn trong một database transaction thường không cần lease cho bản ghi idempotency. Thêm lease vào một thiết kế vốn đã có transaction có thể tạo ra hai nguồn quyết định quyền thực thi khó thống nhất.

### 3.1. Chọn phạm vi khóa theo nghiệp vụ

Một ràng buộc phổ biến là:

```text
UNIQUE(tenant_id, subject_id, operation, idempotency_key)
```

`tenant_id` và `subject_id` phải được suy ra từ ngữ cảnh xác thực đáng tin cậy. Không nhận trực tiếp các giá trị này từ body rồi dùng để truy vấn bản ghi.

`operation` nên là tên lệnh ổn định do server quy định, chẳng hạn `refund.create.v1`. Nếu đường dẫn chứa mã đơn hàng, mã đó phải nằm trong fingerprint hoặc một thành phần định danh tương đương; không chỉ dùng tên route chung rồi bỏ qua đối tượng đích.

Có hệ thống chọn phạm vi ở cấp tenant thay vì cấp người dùng, ví dụ nhiều nhân viên cùng gửi lại một lệnh đã được cấp định danh chung. Khi đó cần thiết kế rõ quyền đọc kết quả và quyền sử dụng lại key. Phạm vi tra cứu rộng hơn không được đồng nghĩa với quyền đọc phản hồi rộng hơn.

Nếu đưa `subject_id` vào phạm vi, hai người dùng dùng cùng một key sẽ tạo hai bản ghi khác nhau. Vì thế, quy tắc “mỗi ý định hoàn tiền chỉ được thực hiện một lần dù ai gửi” cần thêm ràng buộc trên dữ liệu nghiệp vụ, ví dụ:

```text
UNIQUE(tenant_id, refund_intent_id)
```

`refund_intent_id` phải đại diện cho một ý định nghiệp vụ được server kiểm tra và cho phép. Không mặc định đặt unique trên `order_id` nếu đơn hàng được phép hoàn từng phần nhiều lần.

### 3.2. Thay đổi phiên bản là thay đổi không gian định danh

Nếu triển khai mới đổi `refund.create.v1` thành `refund.create.v2`, cùng key có thể không còn tìm thấy bản ghi cũ. Cần chủ động quyết định chính sách tương thích và giữ ràng buộc nghiệp vụ xuyên phiên bản. Không dùng việc đổi namespace như cách bỏ qua bản ghi chưa hết thời hạn bảo vệ.

## 4. Fingerprint: lưu dấu vết của ý nghĩa request

Key xác định request cần tra cứu; fingerprint xác định request đang tra cứu có khớp với request ban đầu hay không.

Giả sử client gửi:

```json
{
  "order_id": "order-125",
  "refund_intent_id": "refund-intent-42",
  "amount_minor": 150000,
  "currency": "VND"
}
```

Server có thể tạo biểu diễn chuẩn hóa gồm tên thao tác, đối tượng đích và những trường có ảnh hưởng đến ý nghĩa lệnh, sau đó băm bằng SHA-256. Nếu request sau dùng cùng key nhưng đổi `amount_minor` thành `900000`, server phải từ chối vì fingerprint khác; không thực hiện hoàn tiền mới và không trả kết quả cũ như thể hai yêu cầu tương đương.

Việc chuẩn hóa cần có hợp đồng cụ thể:

- Thứ tự thuộc tính JSON không làm thay đổi ý nghĩa.
- Phân biệt trường bị bỏ qua và giá trị `null` nếu nghiệp vụ phân biệt chúng.
- Chuẩn hóa tiền theo đơn vị nhỏ nhất của loại tiền, hoặc dùng biểu diễn thập phân chính xác có quy tắc rõ ràng.
- Giữ thứ tự mảng khi thứ tự có ý nghĩa; chỉ sắp xếp khi hợp đồng xác định đó là tập hợp.
- Không đưa trace ID, token xác thực hoặc timestamp truyền tải vào fingerprint.
- Có đưa các điều kiện do client yêu cầu, như phiên bản tài nguyên kỳ vọng, nếu chúng ảnh hưởng đến ý nghĩa lệnh.
- Dùng phiên bản thuật toán để retry qua đợt triển khai vẫn so khớp đúng với bản ghi cũ.

Không cần đưa giá hiện tại, thời gian hiện tại hoặc dữ liệu động vừa đọc từ server vào fingerprint của ý định client. Nếu những giá trị này thay đổi giữa hai lần retry, request cũ có thể bị hiểu sai thành request khác. Các giá trị nghiệp vụ đã áp dụng, như giá được chốt khi tạo đơn, cần được lưu cùng dữ liệu giao dịch để đối soát.

Fingerprint phải được server tính. Giá trị hash do client gửi không đủ tin cậy để làm căn cứ so khớp. Băm cũng không phải mã hóa: không coi fingerprint là biện pháp che giấu chắc chắn cho dữ liệu có không gian giá trị nhỏ; nếu cần, cân nhắc HMAC và quản lý phiên bản khóa phù hợp.

**Fingerprint khớp không làm request trở nên hợp lệ.** Số tiền, trạng thái đơn, quyền hoàn tiền và yêu cầu phê duyệt vẫn phải được kiểm tra trong luồng nghiệp vụ.

## 5. Chọn nơi lưu trữ theo ranh giới bảo đảm

| Nơi lưu | Điểm mạnh | Rủi ro phải xử lý | Cách dùng phù hợp |
|---|---|---|---|
| Bộ nhớ của process | Truy cập nhanh, triển khai đơn giản | Mất khi restart; không chia sẻ giữa instance | Tối ưu cục bộ, không làm nguồn quyết định duy nhất cho giao dịch quan trọng |
| Cache phân tán | Có thao tác nguyên tử và thời hạn lưu | Eviction, failover, độ bền cấu hình và khó đồng bộ transaction với database nghiệp vụ | Lớp tăng tốc hoặc cơ chế điều phối có giới hạn bảo đảm được xác định rõ |
| Database quan hệ | Unique constraint, transaction và liên kết với dữ liệu nghiệp vụ | Chờ khóa, tăng dung lượng, cần chính sách dọn dẹp và vận hành | Lưu bản ghi cùng transaction với thay đổi nghiệp vụ trong database đó |
| Kho dữ liệu có conditional write | Có thể nhận quyền bằng put-if-absent hoặc compare-and-set | Phải hiểu consistency, thời hạn xóa và phạm vi transaction của sản phẩm | Hệ thống thiết kế dựa trên những primitive nguyên tử này |

Tiêu chí quan trọng là nơi nào quyết định request được phép thực thi và nơi đó có thể ràng buộc với tác dụng nghiệp vụ như thế nào.

Ví dụ, `SET NX` thành công trên cache rồi cập nhật số dư trong database là hai thao tác thuộc hai hệ thống. Nếu process chết giữa hai bước, cần một quy trình phục hồi. Chỉ thêm TTL cho key không giải quyết được khoảng trống này.

## 6. Hai mô hình lưu trạng thái cần phân biệt

### 6.1. Mô hình A: bản ghi và nghiệp vụ trong cùng một transaction

Mô hình này phù hợp khi tác dụng cần bảo vệ nằm trong cùng database và thời gian xử lý đủ ngắn:

```text
BEGIN
  Nhận quyền bằng INSERT có unique constraint
  Kiểm tra và cập nhật dữ liệu nghiệp vụ
  Lưu kết quả cuối vào bản ghi idempotency
COMMIT
Trả phản hồi
```

Nếu transaction rollback, cả bản ghi nhận quyền và thay đổi nghiệp vụ cùng biến mất. Nếu commit thành công nhưng response bị mất trên đường truyền, retry tìm thấy bản ghi kết quả để phát lại.

Trạng thái `PROCESSING` có thể tồn tại bên trong transaction chưa commit. Một request khác không nhất thiết đọc thấy trạng thái này; thao tác insert của nó có thể chờ unique constraint được giải quyết. Vì vậy, không nên mô tả mô hình này như thể mọi client đều nhìn thấy một bản ghi “đang xử lý” đã lưu bền vững.

### 6.2. Mô hình B: commit nhận việc, rồi xử lý ngoài transaction đó

Mô hình này thường xuất hiện trong tác vụ dài hoặc công việc có nhiều bước:

```text
Transaction 1: ghi PROCESSING và commit
Worker:       xử lý tác vụ
Transaction 2: ghi COMPLETED và kết quả
```

Nếu worker chết, bản ghi `PROCESSING` còn tồn tại. Hệ thống cần quyền sở hữu, lease, phục hồi, đối soát và cơ chế ngăn worker cũ tiếp tục ghi sau khi mất quyền.

Hai mô hình có cùng tên trạng thái nhưng khác hẳn về tính nhìn thấy, phục hồi và quyền thực thi. Không lấy quy tắc xử lý timeout của mô hình B rồi áp dụng máy móc cho mô hình A.

## 7. Ví dụ schema PostgreSQL cho mô hình transaction chung

Ví dụ sau minh họa mô hình A. `record_id` do ứng dụng sinh bằng bộ sinh UUID phù hợp; bảng này không chứa lease vì không commit trạng thái nhận việc riêng.

```sql
CREATE TABLE idempotency_records (
    record_id             UUID        NOT NULL UNIQUE,
    tenant_id             UUID        NOT NULL,
    subject_id            UUID        NOT NULL,
    operation             VARCHAR(100) NOT NULL,
    idempotency_key       VARCHAR(200) NOT NULL,
    fingerprint_version   SMALLINT    NOT NULL,
    request_fingerprint   BYTEA       NOT NULL,
    status                VARCHAR(20) NOT NULL,
    business_resource_id  UUID,
    response_status       SMALLINT,
    response_headers      JSONB,
    response_body         BYTEA,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at          TIMESTAMPTZ,
    expires_at            TIMESTAMPTZ,

    PRIMARY KEY (
        tenant_id, subject_id, operation, idempotency_key
    ),

    CHECK (fingerprint_version > 0),
    CHECK (octet_length(request_fingerprint) = 32),
    CHECK (status IN ('PROCESSING', 'COMPLETED')),
    CHECK (
        (status = 'PROCESSING'
            AND response_status IS NULL
            AND response_headers IS NULL
            AND response_body IS NULL
            AND completed_at IS NULL
            AND expires_at IS NULL)
        OR
        (status = 'COMPLETED'
            AND response_status IS NOT NULL
            AND response_status BETWEEN 200 AND 599
            AND response_headers IS NOT NULL
            AND response_body IS NOT NULL
            AND completed_at IS NOT NULL
            AND expires_at IS NOT NULL
            AND expires_at >= completed_at)
    )
);

CREATE INDEX idempotency_records_cleanup_idx
    ON idempotency_records (expires_at)
    WHERE status = 'COMPLETED';
```

`response_body` lưu bytes để có thể phát lại nội dung đã tuần tự hóa; body rỗng vẫn được biểu diễn bằng mảng bytes rỗng. `response_headers` chỉ chứa các header được cho phép lưu, chẳng hạn `Content-Type` và `Location`.

Khoảng mã HTTP trong schema là kiểm tra cấu trúc, không phải chính sách yêu cầu lưu mọi lỗi từ 200 đến 599. Ứng dụng vẫn phải quyết định kết quả nào được lưu và kết quả nào phải rollback.

Các check constraint trên chưa buộc mọi transaction phải kết thúc với `COMPLETED`. Luồng ứng dụng phải bảo đảm không commit một bản ghi `PROCESSING` trong mô hình A. Nếu có đường đi như vậy, nó là lỗi triển khai cần cảnh báo và đối soát; không tự động “thử lại nghiệp vụ” chỉ vì bản ghi bị treo.

## 8. Nhận quyền bằng unique constraint

Mẫu nguy hiểm là kiểm tra trước rồi mới ghi:

```text
Nếu chưa có key:
    Thực hiện hoàn tiền
    Ghi key và kết quả
```

Hai request có thể cùng nhìn thấy “chưa có key” và cùng hoàn tiền. Ngay cả khi sau đó chỉ một request ghi key thành công, tác dụng trước đó có thể đã xảy ra hai lần.

Với mô hình A, thao tác nhận quyền phải diễn ra trước thay đổi nghiệp vụ và trong cùng transaction:

```sql
INSERT INTO idempotency_records (
    record_id,
    tenant_id,
    subject_id,
    operation,
    idempotency_key,
    fingerprint_version,
    request_fingerprint,
    status
)
VALUES (
    :record_id,
    :tenant_id,
    :subject_id,
    :operation,
    :idempotency_key,
    :fingerprint_version,
    :request_fingerprint,
    'PROCESSING'
)
ON CONFLICT (
    tenant_id, subject_id, operation, idempotency_key
)
DO NOTHING
RETURNING record_id;
```

- Có dòng trả về: transaction này đã nhận quyền và có thể tiếp tục kiểm tra nghiệp vụ.
- Không có dòng trả về: đã có bản ghi xung đột; đọc bản ghi đó, so fingerprint và xử lý theo trạng thái.
- Chờ khóa quá thời hạn: trả lỗi retry theo hợp đồng; không chuyển sang thực hiện nghiệp vụ để “tránh chờ”.

Ở PostgreSQL với `READ COMMITTED`, insert có thể chờ transaction khác kết thúc. Nếu transaction kia commit, `DO NOTHING` có thể không trả dòng nào. Sau đó dùng một câu `SELECT` riêng để đọc bản ghi đã commit:

```sql
SELECT record_id,
       fingerprint_version,
       request_fingerprint,
       status,
       business_resource_id,
       response_status,
       response_headers,
       response_body
FROM idempotency_records
WHERE tenant_id = :tenant_id
  AND subject_id = :subject_id
  AND operation = :operation
  AND idempotency_key = :idempotency_key;
```

Không mặc định một CTE gộp `INSERT ... DO NOTHING` và `SELECT` trong cùng một statement luôn thấy dòng vừa gây xung đột: snapshot của statement và cơ chế kiểm tra unique có thể khiến kỳ vọng đó không đúng. Với isolation level khác, cũng phải xử lý đúng lỗi transaction và quy tắc snapshot tương ứng.

Nếu câu đọc riêng không tìm thấy dòng, chẳng hạn vì dọn dẹp đồng thời, cần thử lại quy trình nhận quyền có giới hạn hoặc trả lỗi có thể retry. Chỉ được thực thi khi đã nhận quyền thành công; “không đọc thấy” không tự cấp quyền thực thi.

## 9. Luồng xử lý hoàn chỉnh và thứ tự kiểm tra quyền

Mã giả sau thể hiện ranh giới transaction; nó không phụ thuộc vào annotation hoặc cơ chế proxy của một framework Java cụ thể:

```java
Response handleRefund(Request request, AuthContext auth) {
    Scope scope = trustedScope(auth, "refund.create.v1");
    validateKeyAndRequestShape(request);

    // Kiểm tra quyền hiện tại trước khi tiết lộ kết quả đã lưu.
    authorizeTargetAccess(auth, request.orderId());

    return transactionRunner.runAndCommit(() -> {
        Claim claim = records.tryInsert(scope, request);

        if (!claim.acquired()) {
            StoredRecord record = records.find(scope, request.key());
            if (record == null) {
                throw new RetryableClaimFailure();
            }

            Fingerprint actual = fingerprints.compute(
                request, record.fingerprintVersion()
            );
            requireSameFingerprint(record, actual);
            authorizeReplay(auth, record);
            requireCompleted(record);
            return record.toReplayResponse();
        }

        // Bên trong: kiểm tra phê duyệt, giới hạn hoàn tiền,
        // quyền thực thi và cập nhật dữ liệu có khóa/ràng buộc phù hợp.
        RefundResult refund = refunds.executeChecked(request, auth);
        Response response = serializeRefundResult(refund);
        records.markCompleted(claim.recordId(), refund.id(), response);
        return response;
    });
}
```

Hợp đồng của `runAndCommit` là chỉ trả kết quả cho tầng HTTP sau khi commit thành công. Nếu commit lỗi hoặc chưa xác định được kết quả, không phát response thành công chỉ vì callback đã tạo xong body.

Nhánh nhận quyền mới phải tính và lưu fingerprint bằng phiên bản chuẩn hóa đang áp dụng. Nhánh phát lại tính fingerprint theo phiên bản của bản ghi cũ; nếu phiên bản đó không còn được hỗ trợ, cần xử lý tương thích hoặc từ chối rõ ràng, không giả định request khớp.

Có hai nhóm kiểm tra quyền cần phân biệt:

- **Quyền nhận thông tin hiện tại:** người gọi còn được xem đối tượng và kết quả hay không. Cần kiểm tra trước khi trả dữ liệu từ bản ghi, kể cả khi key và fingerprint khớp.
- **Điều kiện thực thi lệnh mới:** đơn chưa hoàn đủ, phê duyệt còn hiệu lực, số dư đủ hoặc trạng thái cho phép chuyển tiếp. Cần kiểm tra trên nhánh thực thi mới, trong ranh giới đồng bộ phù hợp.

Không kiểm tra lại một cách máy móc điều kiện “chưa hoàn tiền” để chặn phát lại một lần hoàn tiền đã thành công: chính lần thành công trước đã thay đổi trạng thái đó. Đồng thời, không dùng idempotency để bỏ qua việc kiểm tra người gọi đã bị thu hồi quyền đọc kết quả.

Việc kiểm tra quyền và thay đổi dữ liệu có thể cần khóa, kiểm tra phiên bản hoặc điều kiện cập nhật nguyên tử để chống thay đổi đồng thời. Nếu bản ghi quyền nằm trong cùng database và ảnh hưởng trực tiếp đến quyết định thực thi, thiết kế transaction phải tính đến cuộc đua thu hồi quyền.

## 10. Phát lại kết quả và chính sách lỗi

### 10.1. Chọn nội dung cần lưu

Một phản hồi đã lưu thường gồm:

- Mã trạng thái HTTP có ý nghĩa nghiệp vụ.
- Body đã tuần tự hóa hoặc tham chiếu tới một ảnh chụp kết quả bất biến.
- Một tập header được phép phát lại.
- Định danh tài nguyên nghiệp vụ và các mốc thời gian cần đối soát.

Nếu chỉ lưu `resource_id` rồi đọc trạng thái hiện tại để tạo response, retry có thể nhận nội dung khác lần đầu. Cách đó có thể phù hợp với hợp đồng “trả tài nguyên hiện tại”, nhưng cần mô tả rõ. Nếu hợp đồng yêu cầu phát lại kết quả ban đầu, phải lưu ảnh chụp hoặc phiên bản dữ liệu tương ứng.

Không lưu nguyên tất cả header hoặc toàn bộ request. Token xác thực, `Set-Cookie`, mật khẩu và bí mật thanh toán không nên trở thành dữ liệu phát lại. Trace ID của lần retry nên phục vụ quan sát lần retry hiện tại; có thể lưu liên kết với lần xử lý gốc ở hệ thống theo dõi riêng.

### 10.2. Lỗi nào giữ lại, lỗi nào cho retry?

| Tình huống | Chính sách lưu trữ có thể áp dụng |
|---|---|
| Request sai định dạng hoặc chưa xác thực | Từ chối trước khi tạo bản ghi; tránh làm đầy kho bằng đầu vào vô nghĩa |
| Cùng key, khác fingerprint | Từ chối xung đột, giữ nguyên bản ghi ban đầu |
| Kết quả nghiệp vụ cuối cùng đã xác định | Lưu và phát lại theo hợp đồng; có thể là thành công hoặc một từ chối nghiệp vụ |
| Lỗi hạ tầng trước commit của mô hình A | Rollback cả bản ghi và dữ liệu nghiệp vụ; retry có thể nhận quyền mới |
| Client mất kết nối sau commit | Giữ kết quả; retry cùng key phát lại |
| Không biết transaction đã commit hay chưa | Tra cứu lại và đối soát; không kết luận rằng tác dụng chưa xảy ra |
| Không biết nhà cung cấp bên ngoài đã thực hiện hay chưa | Giữ trạng thái cần đối soát theo thiết kế; không phát lệnh mới chỉ vì timeout |

Nếu lưu một từ chối nghiệp vụ, chẳng hạn không đủ điều kiện hoàn tiền tại thời điểm xử lý, cùng key sẽ tiếp tục trả kết quả đó trong thời hạn hợp đồng. Khi muốn thể hiện một ý định mới sau khi điều kiện thay đổi, client phải dùng định danh mới theo quy tắc API.

Không cache mọi HTTP 500 thành kết quả cuối một cách máy móc. Ngược lại, cũng không xóa bản ghi với mọi lỗi rồi chạy lại nếu tác dụng bên ngoài có thể đã xảy ra. Quyết định phải dựa vào trạng thái commit và tác dụng thực tế, không chỉ mã HTTP.

## 11. Khi có dịch vụ thanh toán, hàng đợi hoặc worker dài hạn

Database transaction không bao trùm một HTTP request tới nhà cung cấp thanh toán. Giữ transaction mở trong lúc gọi dịch vụ bên ngoài vừa kéo dài thời gian giữ khóa, vừa không tạo ra một commit nguyên tử giữa hai hệ thống.

Một thiết kế thường dùng là:

1. Trong cùng transaction, ghi ý định nghiệp vụ, bản ghi idempotency phù hợp và outbox event.
2. Commit kết quả tiếp nhận, ví dụ response `202` chứa `operation_id`.
3. Worker gửi lệnh ra ngoài với định danh nghiệp vụ ổn định làm key chống lặp của phía nhận, nếu phía nhận hỗ trợ.
4. Lưu kết quả và đối soát khi phản hồi bị mất hoặc trạng thái chưa xác định.

Outbox giúp tránh khoảng trống giữa commit dữ liệu nội bộ và phát thông điệp. Nó không tự ngăn tác dụng bên ngoài bị thực hiện lặp; consumer hoặc nhà cung cấp vẫn cần cơ chế chống lặp tương ứng. Khi không có cơ chế đó, hệ thống cần quy trình đối soát và giới hạn rõ những trường hợp có thể tự động thử lại.

Trong mô hình bất đồng bộ, bản ghi idempotency của request tiếp nhận có thể luôn phát lại response `202` ban đầu. Trạng thái xử lý thực tế nằm ở tài nguyên `operation_id` riêng. Nếu API chọn trả trạng thái mới nhất khi retry, đó là một hợp đồng khác và cần được mô tả nhất quán.

### 11.1. Lease không chứng minh tác vụ cũ đã dừng

Với mô hình B, worker A có thể bị tạm dừng lâu hơn lease. Worker B nhận việc, rồi A hoạt động trở lại. Cả hai có thể cùng cố tạo tác dụng.

Khi cập nhật kết quả, cần điều kiện quyền sở hữu như:

```sql
UPDATE idempotency_records
SET status = 'COMPLETED',
    response_status = :response_status,
    response_headers = :response_headers,
    response_body = :response_body,
    completed_at = :completed_at,
    expires_at = :expires_at
WHERE record_id = :record_id
  AND status = 'PROCESSING'
  AND owner_token = :owner_token
  AND generation = :generation;
```

Đoạn SQL này thuộc mô hình B, đòi hỏi schema riêng có thêm `owner_token` và `generation`; không chạy trực tiếp với schema mô hình A ở trên. Phải kiểm tra số dòng cập nhật, không xem `UPDATE` chạy không lỗi là đã hoàn tất thành công.

Điều kiện trên chỉ ngăn worker cũ ghi kết quả vào bản ghi. Để ngăn worker cũ tạo tác dụng nghiệp vụ, nơi nhận tác dụng cũng phải kiểm tra thế hệ quyền thực thi, khóa/ràng buộc nghiệp vụ hoặc định danh chống lặp. Fencing chỉ có tác dụng khi thành phần nhận thao tác thực sự kiểm tra token; bản thân con số `generation` trong kho idempotency không bảo vệ được một API bên ngoài không hiểu nó.

`record_id` cũng giúp tránh trường hợp xóa bản ghi cũ, tạo bản ghi mới cùng key rồi để một worker cũ cập nhật nhầm thế hệ mới. Không chỉ cập nhật bằng key khi quyền sở hữu có thể thay đổi qua các lần tạo lại.

## 12. Thời hạn giữ bản ghi và dọn dẹp

TTL là quyết định nghiệp vụ và vận hành. Nó xác định khoảng thời gian hệ thống còn nhận diện được request cũ, không chỉ thời gian cache một response.

Thời hạn cần xét đến:

- Khoảng retry tối đa được công bố cho client.
- Thời gian hàng đợi có thể lưu hoặc phát lại thông điệp.
- Thời gian khôi phục sau sự cố và khoảng chậm trễ đối soát.
- Thời hạn chống lặp của dịch vụ bên ngoài.
- Yêu cầu lưu vết và tối thiểu hóa dữ liệu nhạy cảm.

Nếu client retry sau khi bản ghi bị xóa, cùng key có thể được xử lý như request mới. Tăng TTL chỉ kéo dài cửa sổ bảo vệ; các quy tắc dài hạn như “một ý định chỉ hoàn tiền một lần” vẫn cần được bảo vệ trong dữ liệu nghiệp vụ.

Một chính sách có thể xóa body nhạy cảm sớm hơn nhưng giữ dấu vết tối thiểu gồm scope, key hoặc dẫn xuất phù hợp, fingerprint và định danh nghiệp vụ lâu hơn. Khi không còn body để phát lại, API phải có hành vi rõ ràng, chẳng hạn trả liên kết tới tài nguyên được phép xem hoặc từ chối việc tái sử dụng key. Không tự chạy lại lệnh chỉ vì body đã bị xóa.

### 12.1. Điều kiện dọn dẹp an toàn

- Chỉ xóa bản ghi kết thúc, đủ thời hạn và không còn thuộc diện đối soát hoặc giữ lại bắt buộc.
- Không coi `PROCESSING` quá hạn là bằng chứng chưa có tác dụng nghiệp vụ.
- Dọn theo lô có giới hạn, sử dụng index phù hợp và theo dõi độ trễ.
- Phối hợp với luồng claim/read để xử lý trường hợp bản ghi bị xóa giữa hai câu lệnh.
- Không gia hạn thời hạn vô hạn chỉ vì có người liên tục retry, trừ khi đó là chính sách có chủ đích và có hạn mức.

Kho dữ liệu có TTL tự động có thể xóa trễ. Ngược lại, cache có thể loại bỏ dữ liệu trước thời hạn do áp lực bộ nhớ. Cần hiểu bảo đảm của cơ chế đang dùng, không coi một trường `expires_at` là cam kết lưu đủ và xóa đúng thời điểm.

Với phân vùng dữ liệu, phải kiểm tra ràng buộc unique còn bao phủ được toàn bộ phạm vi key cần bảo vệ. Chia bảng theo ngày rồi chỉ unique trong từng phân vùng có thể làm cùng key xuất hiện ở hai ngày khác nhau nếu thiết kế không giữ được tính duy nhất toàn cục cần thiết.

## 13. Bảo vệ kho bản ghi khỏi lạm dụng

### 13.1. Cô lập dữ liệu và quyền phát lại

Mọi đường đọc, ghi, cleanup có liên quan đến một request phải dùng đúng phạm vi đã thiết kế. Một truy vấn chỉ có `WHERE idempotency_key = ?` có thể trả nhầm response của tenant khác ngay cả khi key trông ngẫu nhiên.

Key là đầu vào do client kiểm soát, không phải mật khẩu hay capability cho phép xem dữ liệu. Không có quy tắc “biết key thì được xem phản hồi”. Ngay cả khi ứng dụng có row-level security, cũng cần bảo đảm ngữ cảnh tenant được thiết lập đúng và các công việc nền dùng quyền phù hợp.

### 13.2. Ngăn chiếm dụng tài nguyên

Kẻ tấn công có thể gửi nhiều key mới hoặc gửi đồng thời một key để tiêu thụ dung lượng và connection chờ khóa. Các biện pháp cần gắn trực tiếp vào luồng xử lý:

- Giới hạn độ dài key, request và response được lưu.
- Xác thực và kiểm tra đầu vào trước khi cấp phát bản ghi lâu dài.
- Áp dụng hạn mức theo tenant, chủ thể và loại thao tác.
- Giới hạn thời gian chờ khóa và số request đồng thời.
- Trả phản hồi yêu cầu retry có backoff khi đang xử lý, thay vì giữ kết nối vô hạn.
- Không cho client điều khiển TTL, trạng thái, owner token hoặc định danh tenant dùng trong kho.

Với phản hồi lớn, có thể dùng tham chiếu tới một đối tượng lưu trữ bất biến được bảo vệ quyền truy cập. Khi đó phải giải quyết độ bền, thứ tự ghi, thời hạn lưu và quyền đọc của cả hai nơi; không lưu một URL công khai rồi xem như đã bảo vệ dữ liệu.

### 13.3. Quan sát mà không rò rỉ bí mật

Không log toàn bộ body, token hoặc key thô theo mặc định. Nếu cần liên kết các lần retry, có thể log định danh nội bộ hoặc dẫn xuất có khóa, tùy mức nhạy cảm. Không dùng key hay user ID làm nhãn metric có số lượng giá trị không giới hạn.

Mã hóa, phân quyền dịch vụ và sao lưu của kho idempotency phải được xem xét như đối với dữ liệu giao dịch mà nó sao chép. Một response hoàn tiền có thể chứa thông tin nhạy cảm dù bản ghi được gọi là “cache”.

## 14. Failover, nhiều vùng và khôi phục dữ liệu

Không nên đọc replica có độ trễ để quyết định “key chưa tồn tại, được thực thi”. Quyết định nhận quyền phải đi qua cơ chế ghi nguyên tử và nhất quán đủ mạnh cho phạm vi key. Cache miss hoặc replica miss chỉ cho biết lớp đó chưa có bản ghi.

Trong hệ thống nhiều vùng cùng nhận ghi, unique constraint chỉ có hiệu lực cục bộ có thể không ngăn hai vùng cùng xử lý. Cần một nơi điều phối quyền cho cùng scope, một primitive ghi có bảo đảm xuyên vùng phù hợp, hoặc định tuyến cùng định danh về cùng miền quyết định có cơ chế failover an toàn.

Sao lưu và khôi phục cũng có thể làm mất các bản ghi mới hơn mốc phục hồi. Nếu dữ liệu idempotency và dữ liệu nghiệp vụ được khôi phục về những thời điểm khác nhau, một phía có thể báo đã hoàn tất còn phía kia không có giao dịch tương ứng. Ngay cả khi khôi phục nhất quán trong database, tác dụng ở nhà cung cấp bên ngoài có thể vẫn tồn tại sau mốc phục hồi.

Quy trình khôi phục cần đối soát bằng định danh nghiệp vụ ổn định trước khi cho retry các thao tác có trạng thái chưa rõ. Khi kho nhận quyền không khả dụng và không có cơ chế thay thế đã được thiết kế, thao tác quan trọng nên trả lỗi có thể retry; không bỏ qua idempotency để tiếp tục gây tác dụng.

## 15. Tình huống lỗi và kết quả cần đạt

| Tình huống | Rủi ro | Hành vi lưu trữ cần đạt |
|---|---|---|
| Hai request cùng scope, key và nội dung đến đồng thời | Hai lần thực thi | Chỉ một transaction nhận quyền; request còn lại phát lại hoặc nhận thông báo retry |
| Cùng scope và key nhưng đổi số tiền | Dùng key che giấu một lệnh mới | Fingerprint khác bị từ chối; bản ghi gốc giữ nguyên |
| Hai tenant dùng cùng key | Va chạm hoặc rò rỉ | Bản ghi được cô lập theo scope, quyền được kiểm tra độc lập |
| Commit thành công nhưng mất response | Client chạy lại giao dịch | Retry nhận kết quả đã lưu |
| Process chết trước commit trong mô hình A | Bản ghi và nghiệp vụ lệch nhau | Transaction rollback cả hai; lần sau chỉ chạy khi nhận quyền mới |
| Worker cũ tiếp tục sau khi lease hết | Hai worker cùng gây tác dụng | Kiểm tra quyền sở hữu kết hợp cơ chế chống lặp tại nơi gây tác dụng |
| Kho idempotency tạm mất kết nối | Thực thi khi không xác định được quyền | Trả lỗi retry, không tự bỏ qua bước nhận quyền |
| Key đã bị xóa rồi client gửi lại | Tác dụng lặp sau TTL | Hợp đồng thời hạn rõ ràng và ràng buộc nghiệp vụ dài hạn vẫn có hiệu lực |
| Người gọi bị thu hồi quyền sau lần đầu | Phát lại dữ liệu không còn được phép xem | Kiểm tra quyền hiện tại trước khi phát lại |
| Triển khai đổi thuật toán fingerprint | Retry hợp lệ bị hiểu thành request khác | Phiên bản hóa và so khớp theo bản ghi đã lưu |

Các tình huống này cần được kiểm thử bằng nhiều kết nối hoặc nhiều worker thật sự độc lập, không chỉ gọi tuần tự một method hai lần.

## 16. Kiểm thử và vận hành

### 16.1. Kiểm thử tính nguyên tử và phục hồi

Tạo một ý định hoàn tiền hợp lệ, rồi gửi nhiều request cùng scope, key và fingerprint qua các connection riêng. Xác nhận số giao dịch nghiệp vụ đã commit là một; không chỉ xác nhận số bản ghi idempotency là một.

Chèn điểm dừng hoặc sự cố tại các vị trí quan trọng:

1. Sau khi insert nhận quyền nhưng trước khi cập nhật nghiệp vụ.
2. Sau khi cập nhật nghiệp vụ nhưng trước khi lưu response.
3. Sau khi lưu response nhưng trước commit.
4. Sau commit nhưng trước khi client nhận response.

Với mô hình A, ba trường hợp đầu phải rollback nếu transaction chưa commit và bị hủy; trường hợp cuối phải phát lại kết quả. Với mô hình B và tác dụng bên ngoài, cần kịch bản riêng cho mất lease, worker cũ quay lại và trạng thái nhà cung cấp chưa xác định.

### 16.2. Kiểm thử ranh giới bảo mật

Thử đổi tenant, chủ thể, đối tượng đích, số tiền và currency trong khi giữ nguyên key. Kết quả phải đúng theo scope và fingerprint đã công bố, đồng thời không lộ response của request khác.

Thử thu hồi quyền rồi retry; thử gửi key mới cho cùng ý định nghiệp vụ; thử retry sau TTL. Những trường hợp này xác minh rằng quyền theo đối tượng và ràng buộc nghiệp vụ vẫn hoạt động khi cơ chế chống lặp ở tầng request không đủ để chặn.

### 16.3. Chỉ số hữu ích

Theo dõi số lần nhận quyền mới, phát lại, xung đột fingerprint, timeout chờ khóa, lỗi commit và bản ghi xử lý quá lâu. Kết hợp với dung lượng kho, độ trễ cleanup và số tác vụ đang chờ đối soát.

Tỷ lệ phát lại cao có thể phản ánh mạng kém hoặc client retry quá nhanh. Xung đột fingerprint tăng đột biến có thể do client dùng lại key sai hoặc do hành vi lạm dụng. Các chỉ số cần giúp tìm nguyên nhân; không tự kết luận mọi retry đều là tấn công.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng sửa |
|---|---|---|
| Chỉ lưu key trong RAM | Retry sang instance khác hoặc sau restart có thể chạy lại | Dùng nơi nhận quyền chia sẻ có độ bền phù hợp |
| Kiểm tra tồn tại rồi mới insert | Cuộc đua cho phép hai lần thực thi | Dùng unique constraint hoặc conditional write để nhận quyền |
| Ghi bản ghi ở transaction riêng rồi cập nhật nghiệp vụ mà không có phục hồi | Bản ghi có thể treo hoặc không phản ánh tác dụng | Chọn transaction chung hoặc thiết kế đầy đủ mô hình worker và đối soát |
| `UPSERT` ghi đè fingerprint khi key trùng | Request mới thay đổi danh tính của request cũ | Giữ dữ liệu nhận diện ban đầu bất biến; từ chối mismatch |
| Lưu response thành công trước khi nghiệp vụ commit | Phát lại một thành công không tồn tại | Commit đồng bộ bản ghi và dữ liệu trong cùng ranh giới bảo đảm |
| Xóa mọi lỗi để cho retry | Tác dụng ngoài database có thể xảy ra thêm lần nữa | Phân biệt rollback chắc chắn và trạng thái chưa xác định |
| Dùng key thay kiểm tra quyền | Người biết key đọc được kết quả trái phép | Kiểm tra quyền hiện tại và scope đáng tin cậy |
| Coi hết TTL hoặc lease là chưa thực thi | Tác dụng cũ bị lặp | Đối soát và bảo vệ bằng định danh nghiệp vụ |
| Chỉ kiểm thử hai lần gọi tuần tự | Bỏ sót cuộc đua và lỗi commit | Kiểm thử đồng thời và sự cố tại ranh giới transaction |

## 18. Câu hỏi tự kiểm tra

1. Nếu process chết sau khi dữ liệu nghiệp vụ thay đổi nhưng trước khi lưu response, hai thay đổi có cùng rollback được không?
2. Unique constraint có bao phủ đúng tenant, chủ thể và thao tác cần bảo vệ không?
3. Một người dùng khác gửi cùng ý định nghiệp vụ với key mới có bị ràng buộc nghiệp vụ chặn khi cần không?
4. Retry qua một lần triển khai có được so khớp bằng đúng phiên bản fingerprint không?
5. Response được lưu có chứa dữ liệu người gọi hiện tại không còn quyền xem không?
6. Khi kho không khả dụng, khi cleanup chạy đồng thời hoặc khi trạng thái commit chưa rõ, luồng xử lý có vô tình cấp quyền thực thi không?
7. Nếu có tác dụng ngoài database, thành phần nào thực sự chặn việc tạo tác dụng lặp và thành phần nào chịu trách nhiệm đối soát?
8. Sau khi bản ghi hết hạn hoặc dữ liệu được khôi phục từ backup, bất biến nghiệp vụ nào vẫn bảo vệ hệ thống?

Thiết kế nơi lưu idempotency record cần bắt đầu từ tác dụng nghiệp vụ phải bảo vệ, rồi chọn phạm vi khóa, cơ chế nhận quyền và ranh giới commit tương ứng. Một bản ghi chỉ có giá trị bảo mật khi việc tồn tại, thay đổi và hết hạn của nó gắn với những bảo đảm cụ thể về quyền, trạng thái và dữ liệu nghiệp vụ.
