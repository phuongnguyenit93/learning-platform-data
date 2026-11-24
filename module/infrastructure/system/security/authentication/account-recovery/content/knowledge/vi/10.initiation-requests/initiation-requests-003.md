# Recovery request idempotency

## 1. Vì sao yêu cầu khôi phục cần tính lũy đẳng?

Trong luồng khôi phục tài khoản, người dùng có thể gửi lại yêu cầu vì mạng chập chờn, bấm nút nhiều lần hoặc không thấy email đến. Ứng dụng cũng có thể tự gửi lại khi hết thời gian chờ. Máy chủ cần phân biệt một lần thử truyền lại với một hành động mới mà người dùng thực sự muốn thực hiện.

**Idempotency, hay tính lũy đẳng, là cam kết rằng nhiều lần xử lý cùng một thao tác logic tạo ra cùng hiệu ứng nghiệp vụ như xử lý một lần, trong phạm vi và thời gian mà hợp đồng API quy định.** Máy chủ vẫn có thể ghi nhận từng lần gọi vào nhật ký và bộ đếm chống lạm dụng; điều cần tránh là lặp lại tác dụng phụ của thao tác khởi tạo khôi phục.

Ví dụ, người dùng mất mật khẩu gửi yêu cầu khôi phục. Máy chủ đã tạo một phiên khôi phục và ghi việc gửi email, nhưng phản hồi bị mất trên đường về. Khi ứng dụng gửi lại, một thiết kế lũy đẳng trả lại xác nhận của thao tác ban đầu, không tạo thêm token và không gửi thêm một email mới chỉ vì lần truyền đầu bị lỗi.

Điều này cũng quan trọng khi người dùng mất MFA, passkey hoặc thiết bị xác thực. Các trường hợp đó có thể cần quy trình xác minh khác nhau, nhưng việc gửi lại yêu cầu khởi tạo không được tự động tạo nhiều hồ sơ xác minh, nhiều yêu cầu hỗ trợ hay nhiều lịch chờ độc lập.

Khởi tạo chỉ mở một quy trình. Nó chưa chứng minh người gửi sở hữu tài khoản và chưa cho phép đổi mật khẩu, bỏ MFA, thêm passkey hoặc cấp session đăng nhập.

### Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt retry cùng thao tác, yêu cầu mới và hành động gửi lại thông báo.
- Thiết kế khóa lũy đẳng, phạm vi khóa và dấu vân tay nội dung yêu cầu.
- Dùng giao dịch và ràng buộc duy nhất để xử lý các yêu cầu đồng thời.
- Phối hợp bản ghi lũy đẳng với phiên khôi phục, token dùng một lần và transactional outbox.
- Xác định hành vi khi timeout, lỗi, hết hạn hoặc có hành vi lạm dụng mà không làm lộ sự tồn tại của tài khoản.

## 2. Ba việc dễ bị nhầm lẫn

| Cơ chế | Câu hỏi mà cơ chế trả lời | Ví dụ trong khôi phục tài khoản |
| --- | --- | --- |
| Idempotency | Đây có phải lần truyền lại của cùng một thao tác không? | Cùng khóa và cùng nội dung nhận lại cùng xác nhận khởi tạo. |
| Dedupe nghiệp vụ | Hai thao tác khác nhau có nên cùng dẫn tới một hiệu ứng không? | Hai khóa khác nhau cùng yêu cầu email trong thời gian cooldown có thể được gộp theo chính sách. |
| Rate limiting | Nguồn gửi hoặc đối tượng đang bị tác động có vượt giới hạn không? | Hạn chế số lần gọi API và số thông báo thực sự gửi tới một tài khoản. |

Ba cơ chế bổ sung cho nhau. Nếu kẻ tấn công luôn tạo khóa mới, idempotency đơn thuần không ngăn được việc gửi email hàng loạt. Ngược lại, rate limiter không giúp ứng dụng nhận lại kết quả của một thao tác đã commit nhưng bị mất phản hồi.

Một thao tác `resend` cũng không mặc nhiên là retry. Retry tìm lại kết quả cũ; resend là đề nghị tạo thêm một lần giao thông báo, phải có quyền, cooldown và giới hạn riêng. Resend có thể dùng khóa lũy đẳng riêng để tránh chính thao tác resend bị nhân đôi.

## 3. Xác định hợp đồng của thao tác khởi tạo

Một API minh họa:

```http
POST /account-recovery/requests
Content-Type: application/json
Idempotency-Key: <gia-tri-ngau-nhien-cho-mot-thao-tac>

{
  "identifier": "nguoidung@example.test",
  "recoveryIntent": "PASSWORD_LOST",
  "locale": "vi"
}
```

Phản hồi chấp nhận có thể là:

```http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Type: application/json

{
  "requestId": "<ma-tham-chieu-cong-khai-ngau-nhien>",
  "message": "Nếu thông tin phù hợp, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký."
}
```

Đây là một hợp đồng thiết kế minh họa. `202` cho biết hệ thống đã tiếp nhận thao tác, không xác nhận tài khoản tồn tại, email đã được giao hay danh tính đã được chứng minh.

Với cùng phạm vi khóa, cùng khóa và cùng nội dung hợp lệ, máy chủ trả lại cùng `requestId`, cùng nội dung xác nhận đã lưu. Các header riêng của lần truyền như trace ID hoặc thời gian phản hồi có thể khác. Phản hồi không chứa token khôi phục, địa chỉ nhận đầy đủ, trạng thái MFA hoặc thông tin có thể dùng để suy ra tài khoản.

`requestId` chỉ là mã tham chiếu. Nó không có quyền đổi thông tin xác thực, không thay thế bằng chứng danh tính và không phải bearer token để đọc chi tiết hồ sơ khôi phục. Nếu có API theo dõi tiến trình, API đó phải có cơ chế kiểm soát quyền riêng; không thể chỉ dựa vào việc biết `requestId`.

### Các bất biến cần giữ

1. Trong cửa sổ bảo đảm, mỗi cặp phạm vi–khóa chỉ có một kết quả khởi tạo đã commit.
2. Khóa đã gắn với một nội dung không thể được dùng lại cho nội dung khác.
3. Retry không tạo thêm phiên khôi phục, token hoặc sự kiện yêu cầu gửi thông báo.
4. Retry không kéo dài hạn token, đặt lại số lần thử hay bỏ qua đánh giá rủi ro của quy trình khôi phục.
5. Hoàn tất bản ghi khởi tạo không có nghĩa là hoàn tất khôi phục tài khoản.
6. Phản hồi công khai không tiết lộ việc tra cứu tài khoản hoặc quyết định gửi thông báo nội bộ.

Cần nói rõ phạm vi bảo đảm. Sau khi dữ liệu lũy đẳng đã được xóa theo chính sách lưu giữ, máy chủ không còn đủ thông tin để hứa rằng cùng một khóa cũ sẽ luôn trả lại kết quả ban đầu.

## 4. Khóa, phạm vi và dấu vân tay yêu cầu

### 4.1. Khóa thuộc về một thao tác logic

Client tạo khóa ngẫu nhiên có đủ entropy, chẳng hạn một giá trị ngẫu nhiên 128 bit từ bộ sinh số ngẫu nhiên an toàn. Client giữ nguyên khóa và payload trong mọi lần retry của thao tác đó. Khóa phải mới khi người dùng chủ động bắt đầu thao tác khác.

Không dùng email, số điện thoại, ID tài khoản, timestamp đơn lẻ hoặc hash trực tiếp của email làm khóa. Các giá trị này dễ đoán, dễ trùng hoặc làm lộ dữ liệu định danh. Không gửi khóa trong URL vì URL dễ xuất hiện trong lịch sử, log và referrer.

Máy chủ phải giới hạn độ dài và định dạng khóa trước khi truy cập bộ nhớ lưu trữ. Một header dài bất thường không được phép làm tăng không giới hạn bộ nhớ, log hay chi phí truy vấn.

Khóa lũy đẳng là dữ liệu tương quan thao tác, không phải bằng chứng sở hữu tài khoản. Dù khóa khó đoán, thiết kế vẫn không được cho phép người biết khóa lấy token hay bỏ qua bước xác minh.

### 4.2. Phạm vi khóa phải xác định được trước khi tra cứu tài khoản

Một phạm vi có thể gồm:

```text
scope = môi_trường + tenant_đã_xác_định_hợp_lệ + thao_tác + phiên_bản_hợp_đồng
```

Ví dụ, khóa cho `recovery.initiate.v1` không dùng chung với khóa cho `recovery.resend.v1`. Tenant phải lấy từ ngữ cảnh đã kiểm tra, không tin trực tiếp một giá trị mà client có thể sửa để truy cập tenant khác.

Nếu dùng thêm ngữ cảnh trước đăng nhập do máy chủ cấp để ràng buộc thao tác với trình duyệt, cần xác định cách xác thực ngữ cảnh và cách retry khi cookie mất. Nếu phạm vi đổi giữa hai lần truyền, cùng một khóa sẽ trở thành thao tác khác. Không buộc tính đúng đắn vào IP hoặc User-Agent vì chúng có thể đổi và không phải danh tính đáng tin cậy.

Không đưa kết quả tra cứu tài khoản vào cách tính phạm vi công khai. Nếu tài khoản tồn tại dùng một nhánh khóa, còn không tồn tại dùng nhánh khác, hành vi replay hoặc conflict có thể trở thành kênh dò tài khoản.

### 4.3. Dấu vân tay ràng buộc khóa với ý nghĩa của yêu cầu

Máy chủ cần phát hiện trường hợp cùng khóa nhưng payload khác. Có thể tạo fingerprint từ một biểu diễn chuẩn hóa có phiên bản:

```text
canonical = encode_with_lengths(
    version,
    trusted_tenant,
    operation,
    normalize_identifier_by_login_policy(identifier),
    recovery_intent,
    locale
)

fingerprint = HMAC(server_fingerprint_key, canonical)
```

HMAC giúp tránh để một cơ sở dữ liệu fingerprint bị lộ trở thành bảng hash dễ dò của các địa chỉ email phổ biến. Khóa HMAC phải được quản lý như bí mật, có phiên bản và kế hoạch xoay khóa tương thích với cửa sổ replay còn hiệu lực. Fingerprint không thay thế mã hóa dữ liệu định danh mà nghiệp vụ cần lưu.

Việc chuẩn hóa identifier phải giống chính sách đăng nhập của hệ thống. Không tự ý bỏ dấu chấm, bỏ phần `+tag` hay chuyển toàn bộ địa chỉ email sang chữ thường nếu mô hình định danh chưa quy định như vậy. Nếu chuẩn hóa sai, hai người hoặc hai tài khoản khác nhau có thể bị gộp vào cùng một ý nghĩa yêu cầu.

Không hash chuỗi JSON nguyên bản: thay đổi khoảng trắng hoặc thứ tự field có thể làm fingerprint khác dù ý nghĩa không đổi. Dùng biểu diễn xác định với phân tách không nhập nhằng. Loại bỏ trace ID và thời điểm gửi lại khỏi fingerprint. Những trường được loại khỏi fingerprint cũng không được âm thầm dùng để thay đổi hiệu ứng của một lần replay.

Trong hợp đồng trên, `locale` có mặt trong fingerprint vì nó ảnh hưởng ngôn ngữ thông báo. Nếu sản phẩm muốn coi thay đổi locale là không đáng kể, cần định nghĩa rõ rằng lần gọi đầu quyết định locale cho toàn bộ thao tác.

### 4.4. Cùng khóa nhưng khác payload

Nếu khóa cũ được gửi cùng một identifier hoặc mục đích khôi phục khác, máy chủ trả lỗi xung đột chung, ví dụ `409 Conflict` theo hợp đồng API:

```json
{
  "code": "IDEMPOTENCY_KEY_REUSED",
  "message": "Khóa đã được dùng cho một yêu cầu khác. Hãy bắt đầu thao tác mới."
}
```

Không trả payload cũ, địa chỉ cũ hoặc `requestId` của nội dung khác. Việc xác định xung đột chỉ dựa vào dữ liệu của hai yêu cầu và bản ghi lũy đẳng, không phụ thuộc tài khoản có tồn tại hay không.

## 5. Mô hình dữ liệu và ranh giới giao dịch

Một lỗi phổ biến là làm theo thứ tự: kiểm tra cache, tạo token, gửi email, rồi ghi khóa vào cache. Hai máy chủ có thể cùng thấy cache trống; tiến trình cũng có thể chết trước khi ghi khóa. Kết quả là tạo nhiều token hoặc gửi nhiều email.

Cần một điểm phân xử nguyên tử. Với cơ sở dữ liệu quan hệ, ràng buộc duy nhất trên phạm vi–khóa và một giao dịch chứa toàn bộ thay đổi bền vững là một cách triển khai.

### 5.1. Dữ liệu minh họa

```sql
-- SQL minh họa cho một thiết kế dùng PostgreSQL.
CREATE TABLE recovery_initiation_idempotency (
    scope_digest         BYTEA NOT NULL,
    key_digest           BYTEA NOT NULL,
    fingerprint          BYTEA NOT NULL,
    fingerprint_version  INTEGER NOT NULL,
    state                VARCHAR(16) NOT NULL,
    public_request_id    UUID NOT NULL,
    response_status      INTEGER,
    response_body        TEXT,
    created_at           TIMESTAMPTZ NOT NULL,
    replay_until         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (scope_digest, key_digest),
    CHECK (state IN ('PROCESSING', 'COMPLETED')),
    CHECK (replay_until > created_at),
    CHECK (
        state <> 'COMPLETED'
        OR (response_status IS NOT NULL AND response_body IS NOT NULL)
    )
);

CREATE TABLE recovery_notification_outbox (
    event_id             UUID PRIMARY KEY,
    recovery_attempt_id  UUID NOT NULL,
    event_kind           VARCHAR(40) NOT NULL,
    delivery_sequence    INTEGER NOT NULL,
    encrypted_payload    BYTEA NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL,
    delivered_at         TIMESTAMPTZ,
    UNIQUE (recovery_attempt_id, event_kind, delivery_sequence)
);
```

Đây là phần dữ liệu phục vụ bài học, chưa phải schema sản xuất đầy đủ. Bảng phiên khôi phục, khóa ngoại, chính sách lưu giữ và hệ thống mã hóa phụ thuộc hệ thống thực tế. `key_digest` có thể được tạo bằng HMAC có phân miền; không cần lưu khóa client nguyên văn trong mọi bảng.

`COMPLETED` chỉ có nghĩa là giao dịch khởi tạo đã hoàn tất và có thể replay xác nhận. Nó không có nghĩa là email đã gửi thành công hoặc tài khoản đã được khôi phục.

Với thao tác khởi tạo, `delivery_sequence` có thể cố định bằng `0`. Một thao tác resend đã được chấp thuận mới nhận số thứ tự riêng. Worker gửi thông báo không tự tăng số thứ tự khi retry giao cùng một sự kiện.

### 5.2. Xử lý trong một giao dịch ngắn

```text
validate_request_shape_and_key()
apply_ingress_abuse_controls()

scope = trusted_scope()
fingerprint = canonical_fingerprint(request)

BEGIN TRANSACTION

insert idempotency row as PROCESSING
    using unique(scope_digest, key_digest)

if this transaction did not insert the row:
    read committed row using database conflict-handling rules
    if fingerprint does not match:
        ROLLBACK
        return generic key-reuse conflict
    if replay window is over:
        ROLLBACK
        return generic expired-key result
    if completed:
        copy stored public response
        end transaction
        return stored public response
    otherwise:
        end transaction
        return documented retryable pending result

resolve account and evaluate initiation policy internally

if policy permits creating a real recovery attempt:
    create recovery attempt with fixed proof expiry
    create one initial notification outbox event
else:
    record only the internal outcome allowed by privacy policy

store the same public acceptance shape for all account outcomes
mark idempotency row COMPLETED
COMMIT

return stored acceptance response
```

Phần `insert` phải dùng cơ chế xử lý conflict thực sự của cơ sở dữ liệu, chẳng hạn `INSERT ... ON CONFLICT DO NOTHING` kết hợp quy tắc đọc phù hợp. Không chỉ bắt lỗi unique rồi tiếp tục sử dụng một transaction đã bị đánh dấu thất bại. Khi có cạnh tranh, câu lệnh có thể phải chờ transaction sở hữu khóa commit hoặc rollback. Nếu hết thời gian chờ, trả trạng thái retry được theo hợp đồng, không chuyển sang tạo phiên thứ hai.

Ở thiết kế giao dịch ngắn này, bản ghi `PROCESSING` được tạo và chuyển sang `COMPLETED` trong cùng transaction. Tiến trình chết trước commit làm rollback cả bản ghi lũy đẳng, phiên khôi phục và outbox. Một yêu cầu khác có thể thực hiện lại từ đầu vì chưa có hiệu ứng bền vững nào được commit.

Không gọi nhà cung cấp email hoặc dịch vụ xác minh từ xa khi đang giữ giao dịch. Giao dịch chỉ ghi quyết định và công việc cần xử lý bất đồng bộ. Nếu cần đánh giá lâu ở hệ thống ngoài, hãy thiết kế trạng thái công việc bền vững riêng thay vì giữ khóa cơ sở dữ liệu trong suốt quá trình.

Nếu bản ghi claim được commit riêng trước khi làm nghiệp vụ, thiết kế đã khác: cần lease, thời hạn, cơ chế nhận lại công việc và fencing token để worker cũ không ghi kết quả sau khi mất quyền xử lý. Chỉ đặt một cờ `PROCESSING` rồi cho phép bất kỳ tiến trình nào tiếp quản sau timeout là chưa đủ.

## 6. Transactional outbox và giới hạn của “gửi đúng một lần”

Ghi phiên khôi phục và outbox trong cùng giao dịch giải quyết hai tình huống:

- Không có phiên đã commit nhưng mất hoàn toàn công việc gửi thông báo vì máy chủ chết trước khi enqueue.
- Không có thông báo được gửi trước khi phiên khôi phục tương ứng tồn tại bền vững.

Worker đọc outbox và gọi nhà cung cấp thông báo sau commit. Tuy nhiên, một điểm mơ hồ vẫn còn: nhà cung cấp đã nhận email, nhưng worker chết trước khi ghi `delivered_at`. Khi chạy lại, worker có thể gửi lại sự kiện.

Vì vậy, **một outbox event không tự bảo đảm người dùng chỉ nhận đúng một email**. Cần phân biệt:

| Mức bảo đảm | Cơ chế |
| --- | --- |
| Một thao tác khởi tạo đã commit | Ràng buộc duy nhất và giao dịch cho khóa lũy đẳng. |
| Một sự kiện thông báo ban đầu | Unique theo phiên khôi phục, loại sự kiện và số lần giao logic. |
| Một lần nhà cung cấp chấp nhận sự kiện | Cần cơ chế idempotency/dedup của nhà cung cấp hoặc phía nhận trong phạm vi họ hỗ trợ. |
| Một email xuất hiện trong hộp thư | Không thể suy ra chỉ từ giao dịch nội bộ hoặc trạng thái outbox. |

Dùng `event_id` ổn định làm khóa giao tới nhà cung cấp nếu họ hỗ trợ và nếu cửa sổ lưu khóa của họ đáp ứng yêu cầu. Retry cùng outbox event phải giữ nguyên khóa và nội dung giao. Nếu nhà cung cấp không có cơ chế này, thiết kế cần chấp nhận khả năng gửi trùng có kiểm soát và tránh làm phát sinh thêm quyền khôi phục.

Với token, worker không được tạo token mới ở mỗi lần gửi lại outbox. Nếu thông báo cần chứa cùng một token, hệ thống có thể lưu payload đã mã hóa trong outbox, hạn chế quyền giải mã và xóa theo thời hạn phù hợp. Phần xác minh token nên lưu giá trị kiểm tra như hash của token ngẫu nhiên đủ mạnh; không ghi token rõ vào log. Lựa chọn lưu payload phải xét cả nhu cầu retry lẫn rủi ro khi kho dữ liệu bị lộ.

Token hoặc attempt hết hạn trước khi email được giao thì worker phải áp dụng chính sách hết hạn đã định. Không tự gia hạn token chỉ để giao một công việc bị tồn đọng. Sau khi attempt hoàn tất hoặc bị hủy, worker cũng cần kiểm tra điều kiện gửi; vẫn phải tính đến khả năng thông báo đã đi qua hệ thống ngoài trước khi trạng thái thay đổi.

## 7. Retry không được thay đổi vòng đời bằng chứng

Giả sử hệ thống minh họa quy định token sống 15 phút kể từ lúc tạo và bản ghi lũy đẳng cho phép replay trong 24 giờ. Đây là các giá trị ví dụ để phân biệt hai đồng hồ, không phải khuyến nghị mặc định cho mọi sản phẩm.

```text
09:00  Commit yêu cầu K: tạo attempt A và token T, T hết hạn lúc 09:15.
09:01  Retry K: trả lại xác nhận của A, không tạo token khác.
09:14  Retry K: T vẫn hết hạn lúc 09:15.
09:20  Retry K: có thể replay xác nhận cũ; T đã hết hạn.
```

Xác nhận cũ cho biết thao tác đã được tiếp nhận tại thời điểm ban đầu. Nó không hứa rằng token vẫn còn hiệu lực. Giao diện cần nói rõ ý nghĩa này; thao tác “gửi lại hướng dẫn” phải dẫn tới luồng resend hoặc yêu cầu mới theo chính sách, không chỉ retry vô hạn khóa cũ.

Có ít nhất bốn loại thời hạn khác nhau:

| Thời hạn | Vai trò |
| --- | --- |
| Cửa sổ retry của client | Thời gian client tiếp tục cùng thao tác khi chưa biết kết quả. |
| Cửa sổ replay của khóa | Thời gian máy chủ còn cam kết tìm lại kết quả cùng khóa. |
| Hạn dùng bằng chứng/token | Thời gian bằng chứng được phép tham gia xác minh. |
| Cooldown hoặc hạn chế theo rủi ro | Thời gian chờ trước khi chấp nhận thêm hoạt động nghiệp vụ. |

Không dùng chung một TTL cho tất cả chỉ vì triển khai thuận tiện. Cửa sổ replay phải bao phủ các retry được sản phẩm cho phép; tác vụ dọn dữ liệu không được xóa khóa sớm hơn cam kết. Thay đổi thời hạn lưu khóa cũng phải tính đến các thao tác đã tiếp nhận.

Sau `replay_until`, có thể giữ một dấu vết tối thiểu để trả lỗi khóa đã quá hạn và yêu cầu thao tác mới. Sau khi cả dấu vết bị xóa, cùng chuỗi khóa có thể được coi là mới; tài liệu API phải công bố giới hạn này. Các kiểm soát theo tài khoản và theo nguồn vẫn phải ngăn việc dùng lại khóa cũ để lách cooldown.

Nếu attempt A đã hoàn tất hoặc bị hủy, replay xác nhận khởi tạo của A không được làm A hoạt động trở lại, đặt lại số lần thử bằng chứng hay phục hồi session đã bị thu hồi. Các hành động đổi mật khẩu, bỏ yếu tố xác thực và kiểm soát session thuộc những chuyển trạng thái có điều kiện riêng.

## 8. Bảo vệ trước dò tài khoản và lạm dụng

### 8.1. Phản hồi lặp lại cũng phải giữ bí mật

Một endpoint có câu trả lời chung ở lần đầu vẫn có thể rò rỉ nếu chỉ lưu bản ghi lũy đẳng cho tài khoản tồn tại. Kẻ tấn công gửi lại cùng khóa rồi so sánh `requestId`, mã lỗi hoặc độ trễ để suy ra nhánh xử lý.

Với mọi yêu cầu đã được chấp nhận theo hợp đồng, cần lưu kết quả công khai ổn định, kể cả khi không tạo attempt thật do identifier không tồn tại, tài khoản không đủ điều kiện hoặc chính sách nội bộ không cho gửi. Không cần tạo token giả; chỉ cần bản ghi xác nhận không trao quyền và có hành vi replay tương đương.

Cùng dạng body chưa đủ để bảo đảm bí mật. Cần xem xét mã trạng thái, header, kích thước phản hồi, thời gian xử lý, lỗi và hành vi rate limit. Có thể chuyển xử lý nhạy cảm sang hàng đợi để rút ngắn khác biệt đồng bộ; vẫn cần quan sát phân bố thời gian thay vì giả định rằng thêm một thời gian ngủ cố định giải quyết mọi kênh rò rỉ.

Đích nhận thông báo phải lấy từ kênh khôi phục đã đăng ký và chính sách tài khoản. `identifier` hoặc một field địa chỉ nhận tùy ý từ người gửi không tự trở thành nơi hệ thống gửi bằng chứng khôi phục.

### 8.2. Hai lớp giới hạn có mục tiêu khác nhau

- Lớp vào API giới hạn lưu lượng, kích thước dữ liệu và chi phí truy cập. Replay vẫn tiêu thụ tài nguyên nên vẫn chịu kiểm soát này.
- Lớp nghiệp vụ giới hạn số attempt, số thông báo và số thao tác trên tài khoản hoặc kênh nhận. Chỉ một thao tác nghiệp vụ mới được tính cho một khóa đã commit; một lần replay hợp lệ không tiêu thụ thêm quota gửi email.

Các bộ đếm quyết định có tạo hiệu ứng mới phải được cập nhật nguyên tử hoặc có thiết kế phân tán đủ chặt cho mức rủi ro. Nếu nhiều khóa mới cùng vượt qua một phép “đọc rồi tăng” không nguyên tử, hệ thống vẫn có thể gửi quá giới hạn.

Giới hạn ở lớp vào có thể trả `429` theo chính sách công khai dựa trên nguồn yêu cầu. Quyết định nội bộ theo tài khoản không nên được phản ánh bằng một kiểu lỗi chỉ xuất hiện khi identifier tồn tại. Phải phân biệt rõ hạn chế lưu lượng công khai với kết quả nghiệp vụ được che giấu.

Không khóa tài khoản đăng nhập chỉ vì ai đó liên tục gửi yêu cầu khôi phục. Kẻ tấn công có thể dùng cách này để gây từ chối dịch vụ cho chủ tài khoản. Hạn chế thông báo và đánh giá rủi ro cần được thiết kế để giảm khả năng gây hại từ người chưa chứng minh được danh tính.

### 8.3. Chống chiếm tài nguyên kho khóa

Khóa ngẫu nhiên không đồng nghĩa người gửi đáng tin. Kẻ tấn công có thể tạo hàng triệu khóa khác nhau. Cần giới hạn retention, kích thước response được lưu, số bản ghi mới theo nguồn và tổng công suất tiếp nhận.

Không dùng việc chống trùng toàn cục theo identifier như một phép thay thế đơn giản. Nếu mọi yêu cầu cho một tài khoản đều trả cùng mã công khai, mã đó có thể liên kết các người gửi khác nhau và làm lộ hoạt động khôi phục. Dedupe nội bộ không yêu cầu chia sẻ cùng mã tham chiếu ra ngoài.

## 9. Xử lý timeout, lỗi và yêu cầu đồng thời

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Hai yêu cầu cùng khóa và cùng payload đến hai máy chủ | Một bên sở hữu việc tạo; bên còn lại chờ kết quả hoặc nhận phản hồi pending để retry. Chỉ một attempt và một outbox ban đầu được commit. |
| Cùng khóa nhưng payload khác | Trả xung đột chung, không tạo hiệu ứng thứ hai và không lộ payload trước. |
| Tiến trình chết trước commit trong thiết kế giao dịch đơn | Cả claim, attempt và outbox rollback; retry có thể thực hiện thao tác từ đầu. |
| Commit thành công nhưng phản hồi mất | Retry đọc kết quả đã lưu, không tạo lại token hoặc thông báo. |
| Không biết commit đã thành công do kết nối DB đứt | Tra cứu lại bằng cùng khóa trên nguồn dữ liệu có tính nhất quán phù hợp; nếu còn chưa xác định, trả lỗi retry được. |
| Nhà cung cấp nhận thông báo nhưng worker chưa ghi nhận | Retry cùng event ID; dựa vào dedupe phía nhà cung cấp nếu có, không tạo token mới. |
| Kho idempotency không khả dụng | Không thực hiện hiệu ứng khởi tạo trong một nhánh bỏ qua kho; trả lỗi dịch vụ chung theo hợp đồng. |
| Khóa quá hạn nhưng còn dấu vết | Trả kết quả quá hạn chung theo hợp đồng, không ghi đè bản ghi bằng thao tác mới. |
| Khóa mới cho cùng identifier | Xử lý như thao tác mới rồi áp dụng dedupe nghiệp vụ, cooldown và kiểm soát rủi ro. |

Sau timeout không xác định, client cần giữ nguyên khóa. Tạo khóa mới ngay có thể biến một lần thử truyền lại thành yêu cầu nghiệp vụ thứ hai. Client có thể dùng backoff có jitter và số lần thử hữu hạn theo hợp đồng; backoff không tự giải quyết lỗi thiếu nguyên tử ở máy chủ.

Không replay mọi lỗi một cách máy móc. Lỗi cấu trúc request thường được xử lý trước khi claim. Lỗi hạ tầng trước commit không nên bị lưu thành kết quả nghiệp vụ hoàn tất khiến cùng khóa không bao giờ có cơ hội xử lý thành công. Nếu hệ thống chủ động lưu một lỗi cuối cùng vào bản ghi, phải định nghĩa rõ lỗi nào là kết quả ổn định và lỗi nào còn được phép thử lại.

Nếu commit đã thành công thì không ghi đè phản hồi xác nhận bằng lỗi tạm thời của bước gửi thông báo. Gửi thông báo là vòng đời bất đồng bộ của outbox, không thay đổi lịch sử tiếp nhận thao tác.

Trong hệ thống nhiều vùng, một bảng chỉ unique trong từng vùng không tạo ra bảo đảm toàn cục. Cần định tuyến cùng phạm vi–khóa về một nơi phân xử hoặc dùng kho có ràng buộc nhất quán tương ứng. Đọc từ replica bị trễ sau commit có thể trả “chưa có”; không được dựa vào kết quả đó để tạo hiệu ứng ở một kho khác.

## 10. Thiết kế phía client và trải nghiệm người dùng

Client tạo khóa khi người dùng bắt đầu gửi biểu mẫu và khóa payload của thao tác đó. Một lần bấm đúp hoặc retry do mạng dùng cùng khóa. Nếu người dùng sửa identifier hoặc chọn mục đích khôi phục khác, client bắt đầu thao tác mới với khóa mới.

Có thể lưu khóa cùng dữ liệu tối thiểu của thao tác trong bộ nhớ hoặc lưu trữ phiên theo nhu cầu tiếp tục sau reload. Cần giới hạn thời gian lưu và tránh lưu token hoặc dữ liệu định danh không cần thiết. Hai tab có thể tạo hai khóa khác nhau; phía máy chủ vẫn phải áp dụng chính sách nghiệp vụ, không giả định trình duyệt luôn hợp tác.

Vô hiệu hóa nút gửi trong lúc chờ giúp giảm thao tác lặp ngoài ý muốn, nhưng không phải cơ chế bảo đảm tính đúng đắn. Request vẫn có thể được gửi lại bởi mạng, ứng dụng, proxy đã cấu hình retry hoặc một client tự viết.

Thông báo trên giao diện nên giải thích được ba trạng thái:

1. Đã tiếp nhận yêu cầu và sẽ hướng dẫn qua kênh phù hợp nếu thông tin hợp lệ.
2. Chưa xác định kết quả do kết nối; ứng dụng đang thử lại cùng thao tác.
3. Muốn gửi thêm hướng dẫn; cần dùng hành động gửi lại theo chính sách, không tái sử dụng retry vô hạn.

Không hiển thị kết quả khác nhau chỉ vì email có hay không có trong hệ thống. Các gợi ý an toàn như kiểm tra thư rác có thể dùng chung, nhưng không được biến xác nhận tiếp nhận thành lời khẳng định email đã giao thành công.

## 11. Quan sát và các tình huống cần kiểm chứng khi triển khai

Nhật ký có thể ghi trace ID, public request ID, trạng thái lần xử lý (`created`, `replayed`, `conflict`, `pending`), thời gian xử lý và mã lỗi nội bộ đã giới hạn quyền xem. Tránh ghi email đầy đủ, khóa client nguyên văn, token và payload thông báo đã giải mã.

Không đưa khóa hoặc identifier vào nhãn metric có số lượng giá trị không giới hạn. Có thể theo dõi số yêu cầu mới, số replay, số conflict, độ trễ chờ conflict, tuổi outbox và số lần giao lại. Tỷ lệ replay tăng có thể phản ánh mạng kém hoặc timeout; số khóa mới tăng mạnh mới có thể là dấu hiệu tấn công, và cần kết hợp nhiều tín hiệu để kết luận.

Khi triển khai, cần kiểm chứng theo hiệu ứng nghiệp vụ thay vì chỉ so sánh HTTP response:

- Gửi nhiều request song song cùng khóa từ nhiều tiến trình; kiểm tra chỉ một attempt và một outbox ban đầu được commit.
- Thay đổi payload với cùng khóa; kiểm tra không có effect mới và không trả dữ liệu của yêu cầu trước.
- Ngắt tiến trình ở trước commit, sau commit và sau khi nhà cung cấp nhận thông báo; đối chiếu từng trạng thái phục hồi.
- Replay sau khi token đã dùng, hết hạn hoặc attempt bị hủy; kiểm tra quyền khôi phục không được tái tạo.
- So sánh hành vi khởi tạo và replay cho identifier tồn tại và không tồn tại, bao gồm độ trễ và lỗi ở các lớp phụ thuộc.
- Tạo nhiều khóa mới cho cùng identifier; kiểm tra cooldown và quota không bị vượt do cạnh tranh.
- Thử đúng biên thời gian retention, tác vụ dọn dữ liệu, xoay khóa HMAC và định tuyến nhiều vùng.

Đây là các tình huống cần kiểm chứng cho một hệ thống thực thi; một ví dụ schema hoặc thuật toán trong tài liệu không phải bằng chứng rằng hệ thống đã đáp ứng chúng.

## 12. Những lựa chọn dễ tạo lỗ hổng

| Lựa chọn | Vấn đề | Cách thiết kế phù hợp hơn |
| --- | --- | --- |
| Kiểm tra cache rồi gửi email rồi mới lưu khóa | Có cửa sổ cạnh tranh và mất thông tin khi tiến trình chết. | Unique và transaction cho thay đổi bền vững, outbox cho việc gửi. |
| Coi cùng khóa là giống nhau mà không so payload | Khóa có thể bị dùng lại cho identifier hoặc ý định khác. | Fingerprint có phiên bản và lỗi xung đột không lộ dữ liệu cũ. |
| Dùng khóa làm quyền truy cập recovery session | Biết khóa trở thành khả năng đọc hoặc thay đổi dữ liệu nhạy cảm. | Giữ khóa trong phạm vi chống lặp; xác minh và phân quyền riêng. |
| Retry tự tạo token mới hoặc gia hạn token | Nhiều lần truyền mở rộng thời gian và số cơ hội tấn công. | Replay xác nhận; giữ nguyên vòng đời bằng chứng. |
| Chỉ lưu khóa cho tài khoản tồn tại | Replay trở thành kênh dò tài khoản. | Kết quả công khai ổn định cho mọi yêu cầu được tiếp nhận. |
| Tắt rate limit cho mọi khóa đã biết | Replay được dùng để làm cạn tài nguyên đọc hoặc log. | Giới hạn lớp vào cho mọi request, đếm riêng hiệu ứng nghiệp vụ. |
| Xóa khóa ngay khi token hết hạn | Retry hợp lệ có thể bị coi là yêu cầu mới. | Quản lý riêng hạn replay và hạn bằng chứng. |
| Khẳng định outbox bảo đảm gửi email đúng một lần | Không xử lý được khoảng trống giữa nhà cung cấp nhận và worker ghi kết quả. | Giữ event ID ổn định, dùng dedupe phù hợp và công bố giới hạn. |

Một thiết kế idempotency tốt giúp người dùng tiếp tục khi mạng lỗi mà vẫn giữ nguyên ranh giới an toàn của khôi phục tài khoản: cùng một hành động không tự tạo thêm bằng chứng, quyền hạn hoặc cơ hội thử; hành động mới vẫn đi qua chính sách rủi ro, xác minh danh tính và chống lạm dụng của hệ thống.