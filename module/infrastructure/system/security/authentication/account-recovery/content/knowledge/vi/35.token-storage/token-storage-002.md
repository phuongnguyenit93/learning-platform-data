# Token lookup strategy

## 1. Tra cứu token là tìm ứng viên, chưa phải cấp quyền

Trong khôi phục tài khoản, **token lookup strategy** là cách máy chủ tìm bản ghi tương ứng với token người dùng trình bày. Một chiến lược tốt phải tìm nhanh, không cần lưu bí mật token ở dạng rõ và không vô tình cho phép một token tác động tới sai tài khoản hoặc sai mục đích.

Có ba câu hỏi riêng biệt:

1. **Lookup:** token này có thể thuộc bản ghi nào?
2. **Verification:** bí mật được trình bày có khớp với thông tin xác minh đã lưu không?
3. **Authorization và consumption:** bản ghi ấy còn cho phép thực hiện hành động này không, và request có giành được quyền sử dụng một lần không?

Ví dụ, tìm được một bản ghi có selector trùng không có nghĩa người gửi biết phần bí mật. Ngay cả khi bí mật khớp, token có thể đã hết hạn, bị thu hồi, đã sử dụng hoặc thuộc một recovery flow bị hủy.

```text
Input
  → kiểm tra định dạng
  → tìm bản ghi ứng viên
  → xác minh bí mật
  → kiểm tra account, tenant, flow, purpose và trạng thái
  → tiêu thụ nguyên tử cùng hành động được cấp phép
```

Token đặt lại mật khẩu cần được sinh an toàn, gắn với người dùng, lưu an toàn, có thời hạn và dùng một lần. Đây là những yêu cầu được nêu trong [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). Cách tra cứu trong bài này là thiết kế minh họa để thực hiện các yêu cầu ấy, không phải schema bắt buộc của OWASP.

## 2. Chọn chiến lược theo loại bí mật

Không thể quyết định cách lưu và tìm chỉ bằng việc trường dữ liệu được đặt tên là `token`.

| Loại dữ liệu | Đặc điểm | Hướng tra cứu thường phù hợp |
| --- | --- | --- |
| Token ngẫu nhiên dài từ CSPRNG | Không gian đoán đủ lớn nếu sinh và giữ bí mật đúng | Digest có index hoặc selector + verifier |
| Mã ngắn như OTP | Có ít giá trị có thể thử | Xác định challenge/flow trước, rồi xác minh mã và giới hạn lần thử |
| Backup code | Dùng một lần; entropy phụ thuộc cách sinh | Tìm trong đúng tập mã của tài khoản, bảo vệ verifier theo entropy |
| Token có chữ ký như JWT | Có thể xác minh cấu trúc và chữ ký, nhưng vẫn có vòng đời | Kiểm tra đầy đủ token và tra trạng thái nếu cần thu hồi hoặc dùng một lần |

Token JWT có chữ ký không tự giải quyết bài toán dùng một lần. Nếu hệ thống cần biết `jti` đã được sử dụng chưa hoặc recovery flow đã bị thu hồi chưa, vẫn cần trạng thái phía máy chủ.

Bài này chủ yếu dùng ví dụ token khôi phục **ngẫu nhiên đủ mạnh**. Các lựa chọn hash nhanh trong ví dụ không được áp dụng máy móc cho mật khẩu người dùng hoặc mã sáu chữ số.

### 2.1. Tránh lưu token rõ chỉ để tìm dễ

Thiết kế sau thuận tiện nhưng làm bản sao cơ sở dữ liệu trở thành kho quyền khôi phục còn hiệu lực:

```sql
SELECT *
FROM recovery_token
WHERE raw_token = :presented_token;
```

Mã hóa dữ liệu khi lưu trữ hoặc mã hóa ổ đĩa không thay thế việc giảm bí mật trong bảng. Nếu một ứng dụng hoặc bản dump đọc được token rõ, kẻ tấn công có thể thử trình lại chúng.

Một thiết kế verifier không cần khôi phục token gốc chỉ để so sánh. Máy chủ biến đổi đầu vào bằng quy tắc đã chọn và đối chiếu với dữ liệu đã lưu.

Không đưa token rõ vào index, log SQL, tracing, khóa cache hoặc thông báo lỗi. Việc bảng chính chỉ giữ digest sẽ không có nhiều ý nghĩa nếu tầng proxy vẫn ghi toàn bộ URL chứa token.

## 3. Phương án A: tra cứu trực tiếp bằng digest

Giả sử máy chủ sinh 32 byte ngẫu nhiên bằng CSPRNG và biểu diễn thành chuỗi base64url theo một định dạng cố định. Đây là tham số minh họa của thiết kế.

Khi cấp token:

```text
secret = CSPRNG(32 byte)
token_to_user = base64url_without_padding(secret)
lookup_digest = SHA-256(secret)

Lưu:
  lookup_digest
  account_id, recovery_flow_id, purpose
  expires_at, consumed_at, revoked_at
```

Khi nhận token:

```text
Giải mã nghiêm ngặt theo đúng định dạng đã cấp.
Tính SHA-256 trên cùng biểu diễn byte.
Tra cứu bằng lookup_digest có index.
Kiểm tra toàn bộ điều kiện sử dụng trước khi thay đổi tài khoản.
```

Cơ sở của lựa chọn hash nhanh ở đây là bí mật có entropy cao, không phải vì SHA-256 làm mọi loại đầu vào khó đoán. Nếu đầu vào chỉ có một triệu giá trị, hash vẫn cho phép thử hết không gian nhỏ ấy khi kẻ tấn công có bản dump.

### 3.1. Digest có khóa

Một lựa chọn khác là:

```text
lookup_digest = HMAC-SHA-256(K_lookup, encode(context, secret))
```

Trong đó:

- `K_lookup` là khóa do máy chủ quản lý, tách khỏi dữ liệu token.
- `context` có thể gồm loại token, tenant và mục đích theo quy tắc cố định.
- `encode` phải có cách phân định trường rõ ràng, chẳng hạn tiền tố độ dài; không nối chuỗi tùy ý gây nhập nhằng.
- Bản ghi có phiên bản khóa để hỗ trợ vòng đời khóa.

HMAC giúp tách khả năng kiểm tra bí mật khỏi việc chỉ sở hữu bản dump nếu khóa không bị lộ cùng dữ liệu. Nếu cả ứng dụng và khóa đều bị chiếm quyền, không được coi đây là lớp bảo vệ còn nguyên vẹn.

Máy chủ phải tính digest từ token nhận được. Một endpoint chấp nhận `lookup_digest` do client gửi thay cho bí mật sẽ biến digest lưu trong cơ sở dữ liệu thành một bearer token khác.

### 3.2. Index và tính duy nhất

Một mẫu truy vấn cho thiết kế HMAC có phiên bản khóa:

```sql
SELECT id, account_id, recovery_flow_id,
       expires_at, consumed_at, revoked_at, version
FROM recovery_token
WHERE tenant_id = :tenant_id
  AND purpose = :server_selected_purpose
  AND lookup_key_version = :key_version
  AND lookup_digest = :computed_digest;
```

Có thể đặt unique constraint trên cùng bộ trường nếu đó là hợp đồng định danh của thiết kế. Trường digest nên là kiểu byte hoặc biểu diễn cố định có so sánh chính xác; không dùng quy tắc collation bỏ qua hoa thường cho dữ liệu mật mã.

Theo [tài liệu PostgreSQL về unique indexes](https://www.postgresql.org/docs/18/indexes-unique.html), unique constraint có thể áp dụng cho một cột hoặc tổ hợp nhiều cột. Tính duy nhất giúp ngăn dữ liệu mơ hồ; nó không tự thực hiện việc kiểm tra quyền khôi phục.

## 4. Phương án B: selector để tìm, verifier để chứng minh

Một token có thể gồm hai phần độc lập:

```text
r1.<selector>.<verifier>
```

Ví dụ thiết kế:

- `r1` xác định phiên bản định dạng.
- Selector là 16 byte ngẫu nhiên, dùng làm khóa tìm bản ghi.
- Verifier là 32 byte ngẫu nhiên khác, dùng làm bí mật cấp quyền.
- Hai phần được mã hóa base64url theo quy tắc cố định.

Selector không được coi là bí mật đủ để khôi phục tài khoản. Lộ selector có thể làm lộ khả năng liên kết hoạt động hoặc giúp kẻ tấn công tập trung lần thử, nhưng không được tự cho phép đặt lại mật khẩu.

Khi cấp token, máy chủ lưu selector và thông tin xác minh verifier, không lưu verifier rõ:

```text
verifier_mac =
  HMAC-SHA-256(
    K_version,
    encode("recovery-verifier-v1",
           tenant_id, account_id, recovery_flow_id,
           purpose, selector, verifier)
  )
```

Công thức là mô hình minh họa. Định dạng `encode`, phiên bản và cách quản lý khóa cần được định nghĩa nhất quán trong triển khai.

Khi sử dụng:

1. Parse token và lấy selector.
2. Tìm đúng một bản ghi ứng viên bằng selector.
3. Lấy phiên bản khóa và ngữ cảnh từ bản ghi đã lưu.
4. Tính MAC từ verifier người dùng trình và ngữ cảnh ấy.
5. So sánh MAC với giá trị đã lưu bằng hàm so sánh có thời gian không phụ thuộc vị trí byte khác nhau.
6. Chỉ khi khớp mới tiếp tục xét quyền và trạng thái.

Không nhận `account_id` do client cung cấp để thay thế account của bản ghi. Nếu endpoint có account hoặc tenant trong ngữ cảnh, phải đối chiếu chúng với bản ghi đã tìm được.

### 4.1. Vì sao không quét mọi hash?

Nếu mỗi token được lưu bằng một hàm có salt riêng, cùng đầu vào không tạo ra cùng chuỗi hash. Không thể tự tạo một hash duy nhất từ input rồi dùng phép bằng để tìm trực tiếp mọi bản ghi.

Một cách làm sai là đọc tất cả token còn hiệu lực và lần lượt chạy hàm xác minh tốn CPU cho từng hàng. Khi dữ liệu tăng, mỗi request không hợp lệ cũng có thể khiến máy chủ thực hiện nhiều phép tính đắt tiền.

Selector tách việc tìm hàng khỏi việc xác minh bí mật. Sau khi tìm đúng một ứng viên, máy chủ có thể dùng cơ chế verifier phù hợp với loại bí mật mà không cần quét toàn bảng.

Với token ngẫu nhiên đủ mạnh, HMAC hoặc digest có thể phù hợp theo mô hình đe dọa. Với bí mật entropy thấp, cần lựa chọn cách lưu chống tấn công ngoại tuyến tương ứng; không mặc định cứ có selector thì một hash nhanh đã đủ an toàn.

## 5. Schema và truy vấn minh họa

Schema PostgreSQL dưới đây dành cho phương án selector + verifier MAC với token ngẫu nhiên dài:

```sql
CREATE TABLE recovery_token (
    id                  UUID PRIMARY KEY,
    selector            BYTEA NOT NULL UNIQUE,
    verifier_mac        BYTEA NOT NULL,
    mac_key_version     SMALLINT NOT NULL,
    tenant_id           UUID NOT NULL,
    account_id          UUID NOT NULL,
    recovery_flow_id    UUID NOT NULL,
    purpose             TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    consumed_at         TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ,
    version             BIGINT NOT NULL DEFAULT 0,
    CHECK (octet_length(selector) = 16),
    CHECK (octet_length(verifier_mac) = 32),
    CHECK (expires_at > created_at)
);
```

Các quan hệ tới account, tenant và recovery flow cần được bảo vệ bằng ràng buộc hoặc logic giao dịch phù hợp với hệ thống thực tế. Schema này minh họa dữ liệu lookup; nó không thay toàn bộ mô hình nghiệp vụ của module.

Selector có unique constraint toàn bảng nên truy vấn không được chọn ngẫu nhiên giữa nhiều ứng viên:

```sql
SELECT id, selector, verifier_mac, mac_key_version,
       tenant_id, account_id, recovery_flow_id, purpose,
       expires_at, consumed_at, revoked_at, version
FROM recovery_token
WHERE selector = :decoded_selector
  AND tenant_id = :resolved_tenant
  AND purpose = 'PASSWORD_RESET';
```

Tenant và purpose không phải các quyền mà token được tự khai báo. Endpoint xác định mục đích được phép; tenant được lấy hoặc đối chiếu qua ngữ cảnh định tuyến đã xác minh.

Unique selector giúp đơn giản hóa đường tìm kiếm. Nếu sinh selector trùng trong lúc cấp token, tạo giá trị mới; không cập nhật bản ghi cũ để “tái sử dụng” selector.

Không dùng `LIKE`, tìm theo tiền tố hoặc cắt ngắn verifier để tăng tốc. Truy vấn cần tìm chính xác ứng viên và xác minh toàn bộ bí mật. Việc selector là một phần công khai có thể tìm được không làm giảm yêu cầu bảo vệ verifier.

### 5.1. Đặt index theo câu hỏi thực tế

Ngoài index cho lookup, hệ thống có thể cần:

- Index trên `expires_at` để dọn dữ liệu theo lô.
- Index theo account và purpose để thu hồi token liên quan.
- Index theo recovery flow để quản lý vòng đời một quy trình.

Không thêm mọi tổ hợp cột một cách máy móc. Index làm tăng chi phí ghi và dung lượng; index phục vụ cleanup không nhất thiết thay được index phục vụ tra cứu token.

Với index nhiều cột, thứ tự cột ảnh hưởng cách thu hẹp phạm vi tìm. Xem [tài liệu PostgreSQL về multicolumn indexes](https://www.postgresql.org/docs/18/indexes-multicolumn.html). Thiết kế cần dựa trên đúng điều kiện truy vấn; không giả định rằng có index ở đâu đó thì mọi đường lookup đều hiệu quả.

## 6. Từ lookup tới tiêu thụ token

Một quy trình xử lý có thể được mô tả như sau:

```text
validateInputFormat(request.token)

parts = decodeStrictly(request.token)
candidate = findBySelector(parts.selector, expectedTenant, expectedPurpose)

if candidate không tồn tại:
    từ chối theo thông báo chung

key = allowedKeyRegistry.get(candidate.macKeyVersion)
if key không sử dụng được:
    không cấp quyền; xử lý lỗi vận hành phù hợp

computedMac = mac(key, storedContext(candidate), parts.verifier)
if not constantTimeEquals(computedMac, candidate.verifierMac):
    ghi nhận lần thử phù hợp và từ chối

BEGIN
    Kiểm tra lại token, account và recovery flow có liên quan.
    Xác nhận version và các ràng buộc không đổi sau khi xác minh.
    Xác nhận chưa hết hạn, chưa dùng, chưa thu hồi.
    Xác nhận bằng chứng và điều kiện rủi ro bắt buộc.

    Tiêu thụ token bằng cập nhật có điều kiện.
    Thực hiện hành động được cho phép trong cùng giao dịch
      khi dữ liệu nằm trong cùng cơ sở dữ liệu.
    Ghi audit/outbox nếu có.
COMMIT
```

Một câu lệnh tiêu thụ minh họa sau khi verifier đã được xác minh:

```sql
UPDATE recovery_token
SET consumed_at = clock_timestamp(),
    version = version + 1
WHERE id = :verified_token_id
  AND tenant_id = :verified_tenant_id
  AND account_id = :verified_account_id
  AND recovery_flow_id = :verified_flow_id
  AND purpose = 'PASSWORD_RESET'
  AND version = :verified_version
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND expires_at > clock_timestamp()
RETURNING id;
```

Nếu không cập nhật đúng một hàng, không được đổi mật khẩu hoặc tạo quyền khôi phục mới. Nếu thay đổi nghiệp vụ bắt buộc thất bại, giao dịch phải rollback cả trạng thái tiêu thụ.

Cột version chỉ giúp khi mọi thay đổi có liên quan tới việc xác minh token đều tuân theo quy tắc cập nhật version. Nó không tự bảo vệ trạng thái nằm ở bảng account hoặc recovery flow; các đối tượng ấy cần khóa hoặc kiểm tra version riêng theo thiết kế.

Request có thể đã lookup thành công nhưng thua một request khác ở lúc tiêu thụ. Vì vậy, kết quả đọc trước đó không được cache thành một quyết định cho phép sử dụng lại.

## 7. Parse đầu vào và tránh tạo nhiều biểu diễn cho cùng bí mật

Đường lookup thường là endpoint công khai, nên cần giới hạn công việc trước khi truy cập kho dữ liệu hoặc gọi dịch vụ khóa.

Đối với định dạng `r1.selector.verifier`, máy chủ cần quy định rõ:

- Tổng độ dài tối đa và số đoạn chính xác.
- Bộ ký tự được chấp nhận.
- Phiên bản định dạng được hỗ trợ.
- Có cho phép padding hay không.
- Số byte của từng đoạn sau giải mã.
- Cách xử lý các biểu diễn base64url không chuẩn.

Không tùy ý chuyển token sang chữ thường, cắt mất ký tự, bỏ khoảng trắng bên trong hoặc giải mã URL nhiều lần. Những thao tác này có thể làm token khác nhau bị gộp thành một giá trị hoặc làm các tầng proxy và ứng dụng hiểu đầu vào khác nhau.

Một lựa chọn đơn giản là chỉ chấp nhận biểu diễn chuẩn mà máy chủ đã cấp: giải mã, kiểm tra độ dài rồi mã hóa lại theo quy tắc cố định để đối chiếu. Nếu cần hỗ trợ thêm biểu diễn vì tương thích, quy tắc phải được xác định nhất quán ở mọi đường xử lý.

Truy vấn phải dùng tham số ràng buộc. Không nối selector hoặc token vào chuỗi SQL. Lỗi parse phải được xử lý có giới hạn, không tạo stack trace chứa token gốc trong log.

## 8. Mã ngắn và backup code cần chiến lược riêng

### 8.1. Không tìm tài khoản chỉ bằng một OTP

Một mã sáu chữ số có thể xuất hiện đồng thời trong nhiều challenge. Không được làm:

```text
Tìm bản ghi có code = "123456"
Lấy tài khoản đầu tiên tìm thấy
Cho phép đặt lại mật khẩu của tài khoản ấy
```

Thay vào đó, cần xác định challenge hoặc recovery flow bằng một định danh được ràng buộc với ngữ cảnh, rồi kiểm tra mã trong đúng bản ghi:

```text
challenge_id → một challenge cụ thể
challenge → account, tenant, flow, purpose
submitted_code → xác minh bí mật của challenge đó
```

Challenge ID cũng không tự cấp quyền. Nó chỉ giúp xác định nơi cần kiểm tra mã.

Với mã ngắn, kẻ có bản dump có thể thử hết không gian đầu vào nếu thông tin xác minh cho phép. Salt riêng không làm số giá trị có thể thử trở nên lớn hơn; một hash nhanh có salt vẫn có thể bị dò hết khi không gian mã nhỏ.

Cần chọn cách bảo vệ verifier theo mô hình đe dọa, tách khóa nếu dùng cơ chế có khóa và áp dụng giới hạn lần thử trực tuyến. Nếu loại bí mật hoặc yêu cầu áp dụng đòi hỏi password hashing có salt và chi phí tính toán, có thể tìm challenge trước rồi xác minh đúng một verifier; không vì khó index mà chuyển sang lưu mã rõ.

Các bộ đếm thất bại cần được cập nhật nguyên tử. Giới hạn theo IP riêng lẻ không đủ khi kẻ tấn công phân tán request; cũng cần xét challenge, account hoặc các phạm vi phù hợp khác. Không vô tình khóa một tài khoản chỉ vì người lạ gửi yêu cầu khôi phục tới nó.

### 8.2. Backup code không phải mọi mã đều giống nhau

Nếu backup code được sinh dài và ngẫu nhiên, cách bảo vệ có thể khác một mã ngắn dễ nhập tay. Cần đánh giá entropy thực tế, không suy từ số ký tự hiển thị nếu một phần chỉ là dấu phân cách hoặc thông tin công khai.

Có thể dùng code ID hoặc selector để tìm một mã, hoặc kiểm tra trong một tập nhỏ có giới hạn của đúng tài khoản sau khi đã xác định ngữ cảnh. Không quét backup code của toàn bộ người dùng.

Sau khi xác minh thành công, backup code vẫn phải được tiêu thụ nguyên tử. Việc tìm đúng verifier không cho phép mã được sử dụng lần thứ hai.

## 9. Xoay khóa, cache và các bản sao dữ liệu

### 9.1. Phiên bản khóa khác phiên bản định dạng

`r1` có thể mô tả cách parse token, còn `mac_key_version` mô tả khóa dùng để tạo MAC. Hai khái niệm cần được quản lý riêng.

Với selector + verifier, máy chủ tìm bản ghi trước và đọc phiên bản khóa từ dữ liệu được quản lý. Phiên bản đó phải thuộc danh sách cho phép. Không biến một chuỗi do client hoặc bản ghi bất thường cung cấp thành đường dẫn tùy ý tới secret manager.

Với lookup bằng HMAC trên toàn token, cần biết khóa nào để tính giá trị tìm kiếm. Có thể:

- Dùng một định danh phiên bản công khai trong định dạng token và kiểm tra nó theo danh sách cho phép.
- Thử một số lượng nhỏ, cố định các khóa đang được chấp nhận trong giai đoạn chuyển tiếp.

Không thử toàn bộ lịch sử khóa hoặc quét toàn bộ token khi lookup không khớp. Không fallback sang token rõ hay một thuật toán yếu hơn chỉ để “tìm cho ra”.

Từ MAC cũ, máy chủ không thể tự tính MAC mới cho cùng bí mật khi không có bí mật gốc. Vì vậy, kế hoạch xoay khóa cần tính đến thời hạn token: giữ khóa cũ trong phạm vi chuyển tiếp được cho phép, thu hồi token liên quan hoặc chuyển đổi khi người dùng thực sự trình bí mật qua một thao tác được kiểm soát.

Xoay khóa khẩn cấp sau sự cố có thể buộc vô hiệu hóa token đang chờ. Không tiếp tục nhận khóa bị đánh giá là đã lộ chỉ để tránh người dùng phải khởi động lại quy trình.

### 9.2. Cache không được trở thành nguồn cấp quyền độc lập

Một cache có thể giữ ánh xạ selector tới token ID để giảm chi phí tìm. Tuy nhiên:

- Không dùng token rõ làm cache key.
- Không coi một cache hit là bằng chứng verifier đã khớp.
- Không dùng một kết quả `ACTIVE` cũ để bỏ qua trạng thái tiêu thụ hiện tại.
- Kết quả chấp nhận cuối phải dựa trên trạng thái có thẩm quyền và thao tác nguyên tử.
- Cache miss không phải bằng chứng một tài khoản không tồn tại.

Nếu dùng Redis làm kho trạng thái chính, thiết kế cần xác định tính nguyên tử của thao tác kiểm tra và tiêu thụ, chính sách mất dữ liệu, replication và failover. Chỉ đặt TTL trên một khóa không tự bảo đảm mã dùng một lần qua mọi tình huống.

### 9.3. Replica và backup có thể mang trạng thái cũ

Read replica bị trễ có thể chưa thấy token vừa được cấp hoặc vẫn thấy token chưa tiêu thụ. Không đưa ra quyết định cuối chỉ dựa vào trạng thái đọc từ replica.

Tra cứu trên replica nếu có cần có chính sách nhất quán rõ ràng; thao tác xác nhận và tiêu thụ phải chống được dữ liệu cũ. Không retry bằng cách bỏ các điều kiện trạng thái sau khi thấy kết quả giữa các node khác nhau.

Một bản backup được phục hồi cũng có thể làm sống lại trạng thái “chưa dùng” của token đã được tiêu thụ. Kế hoạch phục hồi cần xác định cách vô hiệu hóa quyền khôi phục cũ, chẳng hạn khóa/epoch còn hiệu lực được quản lý nhất quán hoặc thu hồi toàn bộ token đang chờ khi phù hợp. Chỉ khôi phục bảng rồi tin mọi trạng thái cũ có thể tạo đường replay.

## 10. Phản hồi, quan sát vận hành và lựa chọn thiết kế

### 10.1. Lookup thất bại không được làm lộ bí mật

Các trường hợp selector không có, verifier sai, token hết hạn, đã dùng hoặc bị thu hồi có thể được phân loại nội bộ. Response công khai không cần tiết lộ tài khoản, thời gian sử dụng hoặc trạng thái thiết bị tương ứng.

Dùng hàm so sánh phù hợp cho verifier giúp giảm rò rỉ từ phép so sánh, nhưng không tự làm toàn bộ endpoint có thời gian tuyệt đối bằng nhau. Truy vấn cơ sở dữ liệu, cache, gọi dịch vụ khóa và các nhánh xử lý vẫn ảnh hưởng độ trễ. Cần thiết kế đường lỗi nhất quán, chống lạm dụng và tránh công bố thêm thông tin không cần thiết.

Không dùng sleep dài như giải pháp duy nhất cho chênh lệch thời gian. Nó có thể biến endpoint thành nơi giữ tài nguyên rẻ cho kẻ tấn công.

### 10.2. Dữ liệu phục vụ vận hành

Có thể quan sát:

- Độ trễ lookup và số lượng ứng viên trả về.
- Tỷ lệ lỗi định dạng, không có bản ghi hoặc verifier không khớp.
- Lỗi lấy khóa và tỷ lệ dùng phiên bản khóa cũ.
- Số lần tiêu thụ xung đột sau khi lookup đã thành công.
- Tốc độ cleanup và kích thước index.

Không đưa token, verifier, mã OTP hoặc toàn bộ MAC vào log và metric label. Dùng correlation ID hoặc token record ID nội bộ khi cần điều tra, với quyền truy cập và thời hạn lưu phù hợp.

Bản ghi hết hạn có thể được dọn theo lô, nhưng cleanup không thay kiểm tra `expires_at` trên đường sử dụng. Một hàng vẫn tồn tại trong bảng không có nghĩa token còn hiệu lực.

### 10.3. Bảng quyết định

| Điều kiện | Lựa chọn đáng cân nhắc | Điểm phải giữ |
| --- | --- | --- |
| Token dài, ngẫu nhiên; cần thiết kế đơn giản | Digest có index | Parse nhất quán, không chấp nhận digest thay bí mật, kiểm tra trạng thái |
| Muốn tách khóa tìm kiếm và bí mật | Selector + verifier | Selector không cấp quyền, xác minh toàn bộ verifier |
| Cần tách khả năng xác minh khỏi bản dump | Cơ chế có khóa được quản lý riêng | Vòng đời khóa, danh sách phiên bản được phép, không fallback yếu |
| Mã ngắn hoặc backup code entropy thấp | Tìm đúng challenge/tập mã trước rồi xác minh | Bảo vệ chống dò ngoại tuyến và giới hạn lần thử trực tuyến |
| Nhiều instance hoặc có cache | Kho trạng thái có quyết định tiêu thụ nhất quán | Không cấp quyền từ cache hit hoặc bản sao cũ |

Ví dụ, request chứa selector S và verifier V có thể tìm được bản ghi của tài khoản A. Nếu V sai, không có quyền nào được cấp. Nếu V đúng nhưng token đã dùng, cũng không có quyền mới. Chỉ khi bí mật khớp, mọi ràng buộc còn hợp lệ và cập nhật tiêu thụ thành công thì hành động được token cho phép mới được commit.

Thiết kế lookup đạt mục tiêu khi việc tìm ứng viên đủ rẻ để vận hành, dữ liệu lưu không trở thành bí mật có thể trình lại và mọi kết quả tìm kiếm vẫn phải đi qua quyết định cấp quyền chính xác.
