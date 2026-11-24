# Recovery audit entity trong mô hình dữ liệu khôi phục tài khoản

## 1. Recovery audit entity ghi nhận điều gì?

**Recovery audit entity** biểu diễn một sự kiện có cấu trúc về quá trình khôi phục tài khoản: điều gì đã được quan sát hoặc thực hiện, ai hoặc thành phần nào thực hiện, liên quan đến giao dịch nào và kết quả được xác nhận là gì.

Trong luồng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, lịch sử này giúp giải thích những thay đổi nhạy cảm. Ví dụ, một request đã được tiếp nhận, một lần kiểm tra mã bị từ chối, một nhân viên phê duyệt nhánh xem xét hoặc một tác vụ thay MFA thực sự hoàn tất.

Một bản ghi audit cần trả lời được các câu hỏi:

- Sự kiện thuộc loại nào và có ý nghĩa chính xác gì?
- Actor được nhận biết bằng cơ chế nào, hay vẫn chưa được xác thực?
- Tài khoản và request nào là đối tượng liên quan, nếu đã xác định được?
- Kết quả là thành công, bị từ chối hay lỗi xử lý?
- Sự kiện xảy ra khi nào, được ghi nhận khi nào và nằm ở đâu trong chuỗi xử lý?

Audit mô tả một sự kiện đã xảy ra; nó không tự tạo quyền khôi phục. Một hàng có tên `RECOVERY_ACTION_AUTHORIZED` không thay thế việc kiểm tra quyền và trạng thái hiện tại của giao dịch.

## 2. Phân biệt audit với trạng thái request, log và outbox

| Thành phần | Câu hỏi chính | Đặc điểm |
| --- | --- | --- |
| Recovery request | Giao dịch hiện ở trạng thái nào và còn được làm gì? | Có thể cập nhật theo chuyển trạng thái hợp lệ |
| Recovery audit event | Những sự kiện nào đã xảy ra và do đâu? | Thêm sự kiện mới, hạn chế sửa lịch sử |
| Log vận hành | Hệ thống đang chạy hoặc lỗi kỹ thuật ở đâu? | Phục vụ chẩn đoán, có thể khác thời hạn lưu |
| Outbox | Sự kiện hoặc thông báo nào cần được chuyển tiếp? | Có trạng thái gửi, thử lại và xử lý chuyển phát |
| Lịch sử hiển thị cho người dùng | Người dùng được phép biết điều gì? | Bản trình bày đã lọc theo quyền và mức tiết lộ |

Không cập nhật bản ghi audit thành “đã gửi” mỗi lần worker thử lại. Trạng thái chuyển phát thuộc outbox hoặc bản ghi delivery riêng. Bản thân sự kiện vẫn giữ nguyên ý nghĩa và định danh.

Không dùng một thông điệp log tự do như “user recovered” làm bằng chứng duy nhất rằng tài khoản đã được khôi phục. Nó thiếu phạm vi tác vụ, kết quả giao dịch, actor và quan hệ với các sự kiện trước đó.

Một dịch vụ có thể cùng tạo audit và log vận hành, nhưng không nên sao chép nguyên toàn bộ dữ liệu nhạy cảm sang cả hai. Mỗi loại dữ liệu cần mục đích, hợp đồng và quyền truy cập rõ ràng.

## 3. Những nhóm trường cốt lõi

### 3.1. Định danh và ngữ nghĩa sự kiện

| Trường | Vai trò |
| --- | --- |
| `id` | Định danh ổn định, duy nhất của sự kiện |
| `schema_version` | Phiên bản hợp đồng dữ liệu của sự kiện |
| `event_type` | Mã loại sự kiện có ngữ nghĩa được định nghĩa |
| `outcome` | Kết quả đối với chính thao tác mà sự kiện mô tả |
| `reason_code` | Lý do nội bộ được chuẩn hóa khi cần |
| `purpose` | Phạm vi tác vụ khôi phục liên quan |

`outcome=SUCCESS` chỉ có nghĩa thành công trong phạm vi `event_type`. Ví dụ, tạo request thành công không có nghĩa là đặt lại mật khẩu thành công. Một nhà cung cấp chấp nhận yêu cầu gửi SMS cũng không chứng minh người dùng đã nhận hoặc kiểm soát số điện thoại.

Các mã sự kiện cần ổn định qua ngôn ngữ giao diện. Không lưu câu tiếng Việt làm enum rồi dựa vào câu đó để truy vấn. Nội dung giải thích cho người đọc có thể được tạo từ mã và dữ liệu được phép hiển thị.

### 3.2. Actor, đối tượng và liên kết ngữ cảnh

| Trường | Vai trò |
| --- | --- |
| `actor_type` | Phân loại actor: chưa xác thực, tài khoản, nhân viên hoặc dịch vụ |
| `actor_ref` | Tham chiếu actor được server xác lập, nếu có |
| `subject_account_id` | Tài khoản là đối tượng của sự kiện, nếu đã xác định |
| `request_id` | Giao dịch khôi phục liên quan, nếu đã tồn tại |
| `request_event_seq` | Thứ tự sự kiện được cấp trong phạm vi request |
| `correlation_id` | Liên kết các thao tác trong một ngữ cảnh xử lý |
| `causation_event_id` | Tham chiếu sự kiện nguyên nhân khi có quan hệ rõ ràng |
| `source_service` | Thành phần phát sinh sự kiện |

Actor và đối tượng có thể khác nhau. Nhân viên hỗ trợ có thể đưa ra quyết định đối với tài khoản của người dùng; dịch vụ có thể đóng một request hết hạn; người chưa đăng nhập có thể gửi một bằng chứng không hợp lệ.

Không gán `actor_ref` bằng ID tài khoản chỉ vì người gửi nhập đúng email của tài khoản đó. Định danh được khai báo chưa chứng minh danh tính actor. Nếu ngữ cảnh chỉ xác định được đối tượng, actor vẫn có thể là `ANONYMOUS`.

### 3.3. Thời gian và dữ liệu bổ sung

`occurred_at` mô tả thời điểm sự kiện được nguồn tin cậy quan sát hoặc thực hiện. `recorded_at` mô tả thời điểm ghi nhận tại nơi lưu audit. Chúng có thể khác nhau do xử lý bất đồng bộ hoặc độ trễ.

Không mặc định rằng hai đồng hồ ở hai dịch vụ hoàn toàn đồng bộ. Thứ tự nhân quả cần thêm liên kết hoặc sequence phù hợp; sắp xếp timestamp đơn thuần không tạo ra bằng chứng chắc chắn về thứ tự thực thi.

`metadata` chỉ chứa các trường đã được định nghĩa cho từng loại sự kiện. Nó không phải nơi đổ toàn bộ request HTTP, exception hoặc hồ sơ xác minh.

## 4. Danh mục sự kiện cần có ngữ nghĩa rõ

Một danh mục minh họa:

| `event_type` | Khi nào ghi | Điều không được suy diễn |
| --- | --- | --- |
| `RECOVERY_REQUEST_CREATED` | Request nội bộ được tạo thành công | Người yêu cầu đã được xác minh |
| `RECOVERY_CHALLENGE_CHECKED` | Một lần kiểm tra bằng chứng có kết quả | Một bằng chứng đúng là đủ mọi điều kiện |
| `RECOVERY_REVIEW_DECIDED` | Quyết định xem xét hợp lệ được lưu | Mọi nhân viên có thể cấp quyền khôi phục |
| `RECOVERY_ACTION_AUTHORIZED` | Quyền thực hiện tác vụ cụ thể được cấp | Quyền đó còn hiệu lực vô thời hạn |
| `RECOVERY_ACTION_COMPLETED` | Tác vụ được bảo vệ thực sự commit thành công | Các tác vụ khác cũng đã hoàn tất |
| `RECOVERY_REQUEST_CLOSED` | Request bị hủy, từ chối hoặc đóng do hết hạn | Đã có thay đổi credential |
| `RECOVERY_DELIVERY_ACCEPTED` | Hạ tầng chuyển phát chấp nhận công việc gửi | Người dùng đã nhận hoặc sử dụng mã |

Có thể dùng các outcome như `SUCCESS`, `DENIED` và `FAILURE`, nhưng phải định nghĩa ranh giới. `DENIED` mô tả một quyết định không cho phép; `FAILURE` mô tả việc xử lý không hoàn thành do lỗi. Không gộp mọi mã sai và lỗi kết nối cơ sở dữ liệu vào một loại “khôi phục thất bại”.

`reason_code` nên là mã có kiểm soát, chẳng hạn `INVALID_PROOF`, `REQUEST_EXPIRED` hoặc `POLICY_REQUIREMENT_NOT_MET`. Mã nội bộ không mặc nhiên được trả cho người dùng và không chứng minh người gửi có ý định xấu.

Nếu ngữ nghĩa một sự kiện thay đổi đáng kể, cần phiên bản hợp đồng hoặc mã sự kiện mới. Không diễn giải lại toàn bộ lịch sử theo một nghĩa mới mà không có dấu hiệu phân biệt.

## 5. Khung bảng PostgreSQL minh họa

Trong ví dụ này, các ID tài khoản và request được lưu như tham chiếu ổn định. Bảng không đặt khóa ngoại tới dữ liệu nghiệp vụ để cho phép chính sách lưu audit độc lập với thời hạn giữ chi tiết request. Thành phần ghi phải kiểm tra tính đúng đắn của các liên kết trước khi tạo sự kiện.

```sql
CREATE TABLE recovery_audit_event (
    id                      uuid PRIMARY KEY,
    schema_version          smallint NOT NULL,
    event_type              varchar(64) NOT NULL,
    outcome                 varchar(16) NOT NULL,
    reason_code             varchar(64),
    purpose                 varchar(32),

    actor_type              varchar(16) NOT NULL,
    actor_ref               varchar(128),
    subject_account_id      uuid,
    request_id              uuid,
    request_event_seq       bigint,
    correlation_id          uuid NOT NULL,
    causation_event_id      uuid,
    source_service          varchar(64) NOT NULL,

    occurred_at             timestamptz NOT NULL,
    recorded_at             timestamptz NOT NULL,
    policy_version          varchar(64),
    from_state              varchar(24),
    to_state                varchar(24),
    metadata                jsonb NOT NULL DEFAULT '{}'::jsonb,

    CHECK (schema_version > 0),
    CHECK (outcome IN ('SUCCESS', 'DENIED', 'FAILURE')),
    CHECK (actor_type IN ('ANONYMOUS', 'ACCOUNT', 'OPERATOR', 'SERVICE')),
    CHECK (
        (actor_type = 'ANONYMOUS' AND actor_ref IS NULL)
        OR
        (actor_type <> 'ANONYMOUS'
         AND actor_ref IS NOT NULL
         AND length(actor_ref) > 0)
    ),
    CHECK (
        (request_id IS NULL AND request_event_seq IS NULL)
        OR
        (request_id IS NOT NULL
         AND request_event_seq IS NOT NULL
         AND request_event_seq > 0)
    ),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (octet_length(metadata::text) <= 4096),
    UNIQUE (request_id, request_event_seq)
);
```

Giới hạn metadata `4096` byte là một lựa chọn minh họa về kích thước. Nó không bảo đảm dữ liệu bên trong được phép lưu. Producer vẫn cần kiểm tra danh sách trường và schema cho từng `event_type`.

Các trường tùy chọn cho phép ghi một sự kiện trước khi có request hoặc trước khi biết tài khoản. Không tạo một tài khoản giả hay một request không hợp lệ chỉ để thỏa quan hệ audit.

Nếu chọn dùng khóa ngoại trong một thiết kế khác, cần phối hợp thời hạn lưu và cách xóa dữ liệu. Không mặc định `ON DELETE CASCADE` từ tài khoản hoặc request xuống lịch sử audit. Ngược lại, việc giữ ID trong audit cũng không cho phép giữ thông tin định danh mãi mãi mà không có chính sách.

## 6. Ví dụ một sự kiện hoàn tất tác vụ

Một sự kiện có thể được biểu diễn như sau; các ID và thời điểm đều là dữ liệu minh họa:

```json
{
  "id": "8e073b14-324e-47c6-a823-0ba1dbe5ea41",
  "schema_version": 1,
  "event_type": "RECOVERY_ACTION_COMPLETED",
  "outcome": "SUCCESS",
  "purpose": "RESET_PASSWORD",
  "actor_type": "SERVICE",
  "actor_ref": "account-recovery",
  "subject_account_id": "4b67c8aa-862e-42a9-a013-c26f51df920d",
  "request_id": "6bc97bb9-c7c3-4c1c-9cd7-cac01107ff11",
  "request_event_seq": 7,
  "correlation_id": "40788f19-77f4-40a7-859b-0b6218385692",
  "source_service": "account-recovery",
  "occurred_at": "2026-11-23T08:00:00Z",
  "recorded_at": "2026-11-23T08:00:00Z",
  "policy_version": "recovery-policy-v3",
  "from_state": "AUTHORIZED",
  "to_state": "COMPLETED",
  "metadata": {
    "operation": "PASSWORD_REPLACED"
  }
}
```

Actor ở đây là dịch vụ thực hiện thay đổi, không phải lời khẳng định rằng một người dùng đã có session đăng nhập đầy đủ. Các sự kiện trước và liên kết nguyên nhân có thể ghi nhận nguồn khởi xướng hoặc quyết định đã cho phép dịch vụ hành động.

Nếu cần ghi actor khởi xướng và thành phần thực thi trên cùng một sự kiện, hãy định nghĩa hai nhóm trường riêng. Không thay một ID nhân viên bằng tên service khi chuyển sang xử lý bất đồng bộ rồi làm mất dấu trách nhiệm.

Ví dụ không chứa mật khẩu cũ, mật khẩu mới, token, OTP hoặc toàn bộ dữ liệu bằng chứng. Một ID tham chiếu có quyền truy cập phù hợp thường hữu ích hơn việc sao chép hồ sơ nhạy cảm vào nhiều nơi.

## 7. Tính nhất quán giữa thay đổi tài khoản và audit

Đối với một thay đổi nhạy cảm được coi là bắt buộc có audit, nên ràng buộc sự kiện thành công với cùng kết quả giao dịch của tác vụ. Trong một cơ sở dữ liệu có thể giao dịch chung, mã giả có thể là:

```text
BEGIN TRANSACTION

  Kiểm tra và điều phối khóa trên tài khoản, request và quyền tác vụ
  Xác nhận trạng thái, thời hạn, scope và bằng chứng còn hiệu lực
  Thực hiện tác vụ được bảo vệ
  Tiêu thụ quyền và cập nhật trạng thái request
  Cấp request_event_seq theo cơ chế đồng thời của request
  INSERT recovery_audit_event cho kết quả thành công
  INSERT outbox tham chiếu cùng event_id nếu cần chuyển tiếp

COMMIT
```

Nếu giao dịch rollback, sự kiện thành công trong giao dịch đó cũng không được tồn tại như một thay đổi đã commit. Nếu không thể lưu audit bắt buộc, không âm thầm commit tác vụ nhạy cảm rồi hy vọng tạo lại lịch sử sau.

Sự kiện về một lần bị từ chối hoặc một lỗi cần được thiết kế khác: nếu chèn nó trong giao dịch rồi rollback toàn bộ, lịch sử lần từ chối cũng biến mất. Có thể ghi sự kiện sau khi rollback bằng một giao dịch audit riêng, với ngữ nghĩa chính xác về điều đã quan sát. Không biến sự kiện này thành bằng chứng rằng một thay đổi tài khoản đã xảy ra.

Đối với việc chuyển audit sang kho phân tích, outbox giúp tránh tình trạng cập nhật nghiệp vụ thành công nhưng mất công việc phát sự kiện. Worker có thể thử lại nên consumer cần xử lý trùng. Xem [AWS — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

Không gọi một hệ thống log từ xa trong lúc giữ khóa rồi coi lời gọi đó là giao dịch nguyên tử cùng cơ sở dữ liệu. Nếu các kho không có cùng giao dịch, phải xác định nơi lưu bền vững ban đầu, cách chuyển tiếp, phát hiện lỗi và phục hồi phù hợp.

## 8. Thứ tự, sequence và chống ghi trùng

`id` của audit là định danh sự kiện, không phải số lần worker gửi nó. Khi chuyển tiếp lại cùng một sự kiện, giữ nguyên ID. Consumer có thể dựa vào ID để nhận biết bản sao thay vì tạo một sự kiện nghiệp vụ mới mỗi lần nhận message.

Nếu một ID đã có nhưng payload mới khác payload cũ, không ghi đè bằng `UPSERT` tùy tiện. Đây là xung đột cần được xử lý và điều tra theo hợp đồng, vì cùng một ID đang được dùng cho hai nội dung khác nhau.

`request_event_seq` phải được cấp dưới một cơ chế đồng thời phù hợp. Ví dụ, một bộ đếm audit riêng của request được tăng trong giao dịch giữ khóa request. Không lấy `MAX(seq) + 1` ngoài giao dịch bảo vệ rồi kỳ vọng mọi luồng đều nhận số khác nhau.

Không đồng nhất sequence audit với `version` của request. Một chuyển trạng thái có thể tạo nhiều sự kiện, còn một lần kiểm tra bị từ chối có thể không thay đổi trạng thái nghiệp vụ.

Trong mô hình có nhiều producer, cần thỏa thuận ai cấp thứ tự của request. Không thể để mỗi dịch vụ tự tăng một bộ đếm riêng rồi diễn giải các số đó như một thứ tự chung. Các sự kiện không gắn request có thể chỉ có ID, timestamp và liên kết nhân quả, không nhất thiết có một thứ tự toàn cục.

Kho phân tích có thể nhận sự kiện lệch thứ tự do chuyển phát. `recorded_at` ở kho nguồn, thời điểm ingest ở kho đích và sequence theo request là những khái niệm riêng; không sửa timestamp gốc để làm dữ liệu có vẻ đã đến đúng thứ tự.

## 9. Giới hạn dữ liệu nhạy cảm và nguồn dữ liệu không đáng tin

Audit của khôi phục tài khoản có thể trở thành một kho dữ liệu rất nhạy cảm nếu ghi quá nhiều. Cần chọn dữ liệu theo mục đích điều tra và kiểm soát, thay vì ghi mọi thứ vì có thể hữu ích về sau.

Không lưu token khôi phục, OTP, mã dự phòng, mật khẩu, cookie session, header authorization hoặc khóa riêng. Không sao chép URL đầy đủ nếu query string có thể chứa token. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) đề cập việc loại trừ bí mật và dữ liệu nhạy cảm khỏi log.

Một số nguyên tắc thiết kế cụ thể:

- Dùng tham chiếu nội bộ cho tài khoản, challenge hoặc quyết định thay vì sao chép toàn bộ đối tượng.
- Ghi mã lý do có kiểm soát thay vì nguyên exception message có thể chứa đầu vào.
- Nếu cần dấu hiệu mạng hoặc thiết bị, xác định rõ mục đích, mức chi tiết, quyền xem và thời hạn lưu.
- Không coi ID actor hoặc correlation do client tự khai báo là sự thật đã xác minh.
- Nếu nhận địa chỉ nguồn qua proxy, cần xác định ranh giới proxy tin cậy trước khi diễn giải các header liên quan.
- Không tạo khóa băm đơn giản của email rồi mặc định rằng dữ liệu đó không còn nhận dạng được; tập giá trị có thể dễ đoán.

Trường metadata cần whitelist. Một lời gọi như `metadata = serialize(httpRequest)` có thể đưa bí mật vào audit dù schema SQL vẫn hợp lệ.

Dữ liệu có cấu trúc vẫn phải được hiển thị an toàn trong dashboard và khi xuất ra định dạng khác. Không nối dữ liệu từ client vào một dòng log rồi để ký tự xuống dòng tạo thành các bản ghi giả; không render chuỗi audit như HTML được tin cậy.

## 10. Bảo vệ lịch sử và tách quyền ghi, đọc, bảo trì

Ở cấp ứng dụng, mô hình thường chỉ cho phép thêm sự kiện mới. Muốn đính chính một thông tin, tạo sự kiện bổ sung tham chiếu sự kiện gốc, kèm lý do và actor có thẩm quyền; không sửa âm thầm lịch sử.

Ví dụ phân quyền ở mức bảng, giả định các role đã được tạo:

```sql
REVOKE ALL ON recovery_audit_event FROM PUBLIC;

GRANT INSERT ON recovery_audit_event
    TO recovery_audit_writer;

GRANT SELECT ON recovery_audit_event
    TO recovery_audit_reader;

REVOKE UPDATE, DELETE, TRUNCATE ON recovery_audit_event
    FROM recovery_audit_writer;
```

Writer không nên là chủ sở hữu bảng hoặc kế thừa một role có quyền rộng hơn. Quyền trực tiếp, quyền từ role khác và quyền của owner phải được xét cùng nhau. Xem [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html).

Đây là giới hạn quyền của một số principal, không phải bảo đảm rằng quản trị viên cơ sở dữ liệu không thể sửa dữ liệu. Nếu mô hình đe dọa bao gồm can thiệp vào kho chính, cần thêm sự tách biệt quản trị, bản sao lưu giữ phù hợp hoặc cơ chế phát hiện thay đổi độc lập.

Một cột hash không tự làm lịch sử bất biến nếu cùng actor có thể thay cả nội dung lẫn hash. Khi dùng chuỗi hash hoặc chữ ký, cần xác định cách bảo vệ khóa, điểm đối chiếu tin cậy và việc phát hiện xóa hoặc cắt ngắn lịch sử.

Tác vụ giữ liệu và xóa theo chính sách có thể cần quyền riêng. Những ngoại lệ bảo trì này phải được kiểm soát và ghi nhận; không cấp quyền xóa cho writer thường xuyên chỉ để thuận tiện dọn dữ liệu.

## 11. Truy vấn, phân quyền đọc và thời hạn lưu

Truy vấn lịch sử của một request có thể dùng sequence:

```sql
SELECT id, request_event_seq, event_type, outcome,
       actor_type, occurred_at, reason_code
FROM recovery_audit_event
WHERE request_id = :request_id
  AND request_event_seq > :after_seq
ORDER BY request_event_seq
LIMIT 100;
```

Khóa duy nhất `(request_id, request_event_seq)` trong khung bảng hỗ trợ mô hình truy xuất này. Tầng gọi vẫn phải kiểm tra quyền xem request; biết ID không tự cấp quyền đọc lịch sử.

Có thể thêm chỉ mục theo nhu cầu điều tra, chẳng hạn:

```sql
CREATE INDEX recovery_audit_subject_time_idx
    ON recovery_audit_event (subject_account_id, occurred_at, id);
```

Thứ tự `(occurred_at, id)` giúp tạo một cách sắp xếp ổn định cho truy vấn, nhưng không thay thế quan hệ nhân quả. Cũng không nên mở quyền truy vấn toàn bộ metadata cho mọi nhân viên hỗ trợ chỉ vì họ được xem một lịch sử đã lọc.

Nếu hệ thống nhiều tenant, tenant phải được xác lập từ ngữ cảnh tin cậy và đi cùng ràng buộc ghi, truy vấn, chỉ mục hoặc chính sách truy cập phù hợp. Không nhận tenant từ một tham số rồi dùng nó như bằng chứng quyền xem audit.

Thời hạn giữ request, thử thách, audit, bản sao phân tích và backup có thể khác nhau. Cần xác định dữ liệu tối thiểu được giữ sau khi chi tiết giao dịch bị xóa, cách gỡ liên kết nhận dạng khi cần và cách áp dụng chính sách trên các bản sao.

Đọc hoặc xuất audit nhạy cảm cũng cần được giám sát theo chính sách. Có thể dùng luồng audit truy cập riêng để tránh việc cơ chế ghi tự gọi lặp vô hạn khi kiểm tra chính nó.

## 12. Tình huống vận dụng

Một người dùng báo mất thiết bị MFA. Một request được tạo, hai lần kiểm tra bằng chứng bị từ chối, rồi một nhánh xem xét được phê duyệt. Sau khi đáp ứng điều kiện, dịch vụ hoàn tất thay MFA. Worker chuyển tiếp sự kiện cuối gặp lỗi mạng và gửi lại.

Mô hình audit phù hợp sẽ thể hiện được:

1. Hai lần kiểm tra bị từ chối là hai sự kiện riêng, không bị ghi đè thành lần thành công gần nhất.
2. Actor của lần phê duyệt là nhân viên hoặc thành phần có thẩm quyền đã được xác lập, không phải người dùng tự khai báo.
3. Quyết định cho phép và tác vụ thực sự hoàn tất là hai sự kiện có ngữ nghĩa khác nhau.
4. Sự kiện hoàn tất cùng thay đổi nghiệp vụ được lưu nhất quán; rollback không để lại một thành công giả.
5. Việc gửi lại cùng sự kiện tới kho phân tích giữ nguyên event ID và không bị đếm thành hai lần thay MFA.
6. Lịch sử đủ để nối các bước nhưng không chứa OTP, token hoặc hồ sơ nhạy cảm dạng rõ.

Recovery audit entity cần giữ rõ **ngữ nghĩa sự kiện, nguồn gốc actor, quan hệ với giao dịch, kết quả được xác nhận và giới hạn dữ liệu được lưu**. Khi những yếu tố đó được bảo toàn, audit hỗ trợ điều tra và giải thích quá trình khôi phục mà không trở thành nguồn cấp quyền hoặc một kho bí mật thứ hai.
