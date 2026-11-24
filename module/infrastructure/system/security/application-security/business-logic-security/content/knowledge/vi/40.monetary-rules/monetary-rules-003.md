# Credit authorization

## 1. Credit authorization bảo vệ quyết định nào?

Trong chương **Monetary Rules** của module **Business Logic Security**, credit authorization là quyết định phía máy chủ cho phép một nghĩa vụ thanh toán cụ thể sử dụng một phần hạn mức tín dụng, kèm điều kiện về chủ thể, số tiền, tiền tệ, thời hạn và trạng thái nghiệp vụ.

Ví dụ: nhà cung cấp cho doanh nghiệp A mua hàng trả sau với hạn mức 100 triệu VND. Khi A đặt đơn hàng 30 triệu VND, hệ thống cần xác định:

- Người thao tác có quyền mua trả sau cho đúng doanh nghiệp và đúng đơn hàng hay không.
- Giá cuối cùng có được tính từ dữ liệu tin cậy và đã qua phê duyệt bắt buộc hay chưa.
- Sau khi tính cả công nợ và các khoản đang giữ chỗ, doanh nghiệp còn đủ hạn mức hay không.
- Quyết định này có bị dùng lại cho đơn khác, số tiền khác hoặc sau khi hết hạn hay không.
- Gửi lại yêu cầu hoặc chạy đồng thời có làm giữ chỗ hay ghi nợ nhiều lần hay không.

Một API chỉ kiểm tra người dùng đã đăng nhập và số tiền lớn hơn 0 vẫn có thể cho phép lạm dụng nghiệp vụ. Bài học tập trung vào các bất biến, quyền theo đối tượng, state machine, transaction và idempotency để bảo vệ quyết định tài chính này.

### 1.1. Phân biệt các khái niệm gần nhau

| Khái niệm | Câu hỏi được trả lời | Kết quả điển hình |
| --- | --- | --- |
| Authentication | Ai đang gửi yêu cầu? | Xác định người dùng hoặc dịch vụ |
| Object authorization | Chủ thể này được thao tác trên tài khoản, đơn hàng nào? | Cho phép hoặc từ chối truy cập đối tượng |
| Credit approval | Ai được cấp hoặc thay đổi hạn mức, theo quy trình nào? | Hạn mức được phê duyệt |
| Credit authorization | Nghĩa vụ này được sử dụng bao nhiêu hạn mức vào lúc này? | Một khoản giữ chỗ có ràng buộc |
| Capture trong mô hình nội bộ | Khi đủ điều kiện, chuyển bao nhiêu tiền đã giữ thành công nợ? | Tăng công nợ, giảm khoản giữ |
| Release | Phần giữ chỗ nào được giải phóng? | Giảm khoản giữ, chưa thu hồi công nợ đã ghi |
| Repayment | Khoản trả nợ hợp lệ nào được ghi nhận? | Giảm công nợ theo quy tắc kế toán của sản phẩm |

Trong thanh toán thẻ, authorization thường giữ một khoản trên phương thức thanh toán để capture sau; thời hạn và khả năng capture phụ thuộc nhà cung cấp, mạng thẻ và loại giao dịch. Giữ chỗ chưa đồng nghĩa đã nhận tiền về tài khoản. Xem [tài liệu Stripe về tách authorization và capture](https://docs.stripe.com/payments/place-a-hold-on-a-payment-method).

Bài này dùng mô hình **hạn mức mua trả sau nội bộ** để giải thích các bất biến. Từ “capture” trong ví dụ nghĩa là chuyển khoản giữ sang công nợ; không tự động có nghĩa là thẻ đã được thu tiền hoặc tiền đã quyết toán.

Việc cộng điểm thưởng, phát hành store credit hoặc hoàn tiền cũng cần authorization, nhưng không được trộn các loại số dư đó vào hạn mức mua trả sau nếu sản phẩm chưa định nghĩa rõ quy tắc chuyển đổi.

## 2. Xác định bất biến trước khi thiết kế API

### 2.1. Hạn mức khả dụng phải tính cả khoản giữ

Với một tài khoản và một loại tiền:

- **L**: hạn mức đã được phê duyệt, còn hiệu lực.
- **D**: công nợ đang chiếm hạn mức.
- **R**: tổng số tiền còn được giữ bởi các authorization chưa kết thúc.
- **A**: hạn mức khả dụng để cấp authorization mới.

Công thức của mô hình:

~~~text
A = L - D - R

L >= 0
D >= 0
R >= 0
D + R <= L
~~~

Ví dụ:

~~~text
L = 100.000.000 VND
D =  50.000.000 VND
R =  20.000.000 VND
A =  30.000.000 VND
~~~

Yêu cầu 40 triệu phải bị từ chối, dù chỉ nhìn công nợ sẽ thấy còn 50 triệu.

Trong mô hình bài học, việc giảm hạn mức xuống dưới D + R bị từ chối. Nếu sản phẩm cho phép tài khoản vượt hạn mức sau khi điều chỉnh chính sách, cần mô hình hóa riêng trạng thái đó, chặn cấp thêm và định nghĩa cách xử lý các nghĩa vụ hiện hữu; không âm thầm bỏ bất biến.

### 2.2. Một authorization phải gắn với một phạm vi xác định

Authorization không phải một cờ `approved = true` có thể gắn vào bất kỳ giao dịch nào. Nó phải liên kết ít nhất với:

~~~text
tenant
credit account
payment obligation
order and order version
amount and currency
pricing version
approval or policy version
authorization attempt
expiry
current state
~~~

**Payment obligation** là nghĩa vụ thanh toán do máy chủ định danh, chẳng hạn khoản phải trả của một phiên bản đơn hàng. Hai yêu cầu HTTP khác nhau vẫn có thể đang cố thực hiện cùng một nghĩa vụ.

Các bất biến bổ sung:

1. Tài khoản, đơn hàng và nghĩa vụ phải thuộc cùng tenant và có quan hệ nghiệp vụ hợp lệ.
2. Số tiền được giữ phải bằng số tiền máy chủ tính cho phạm vi đã phê duyệt.
3. Một nghĩa vụ chưa được thanh toán chỉ có tối đa một authorization đang giữ chỗ theo chính sách của bài.
4. Tổng capture không vượt số tiền đã được giữ hợp lệ.
5. Một nghĩa vụ chỉ được ghi công nợ một lần trong mô hình capture một lần.
6. Release không được giải phóng lại phần đã capture hoặc đã giải phóng.
7. Mọi thay đổi phải để lại dấu vết liên kết được với quyết định và nghĩa vụ gốc.
8. Phản hồi thành công chỉ được trả sau khi các thay đổi liên quan đã commit.

Một sản phẩm hỗ trợ giao hàng nhiều đợt có thể chia thành nhiều nghĩa vụ hoặc hỗ trợ nhiều lần capture. Cần chọn rõ mô hình; không để client tự biến một khoản thanh toán thành nhiều nghĩa vụ để vượt kiểm soát.

## 3. Ví dụ lạm dụng: hai đơn cùng tiêu một hạn mức

Giả sử:

~~~text
L = 100 triệu
D = 70 triệu
R = 0
A = 30 triệu
~~~

Hai yêu cầu, mỗi yêu cầu 20 triệu, đến gần như đồng thời:

| Thời điểm | Yêu cầu X | Yêu cầu Y |
| --- | --- | --- |
| T1 | Đọc A = 30 triệu | |
| T2 | | Đọc A = 30 triệu |
| T3 | Thấy đủ hạn mức | |
| T4 | | Thấy đủ hạn mức |
| T5 | Tạo khoản giữ 20 triệu | |
| T6 | | Tạo khoản giữ 20 triệu |

Nếu cả hai thành công, D + R = 110 triệu. Mỗi yêu cầu riêng lẻ đều vượt qua validation, nhưng tổng thể đã vi phạm hạn mức.

Mẫu code dễ mắc lỗi:

~~~java
// Ví dụ cố ý không an toàn.
if (account.availableMinor() >= requestedMinor) {
    authorizations.insert(account.id(), requestedMinor);
    account.increaseReserved(requestedMinor);
}
~~~

Vấn đề nằm ở khoảng trống giữa đọc, quyết định và ghi. Chỉ thêm `@Transactional` chưa đủ nếu các transaction vẫn quyết định trên dữ liệu đọc không được bảo vệ phù hợp.

Idempotency cũng chưa giải quyết trường hợp này: X và Y có thể là hai đơn khác nhau với hai key hợp lệ. Cần bảo vệ việc phân bổ hạn mức dùng chung.

## 4. Chọn dữ liệu tin cậy và kiểm tra quyền theo đối tượng

### 4.1. Client yêu cầu hành động, máy chủ quyết định điều kiện

Một request có thể có dạng:

~~~http
POST /orders/ord-842/credit-authorizations
Idempotency-Key: 7b4ccaf1-60a9-4c4c-beca-caf27a240d85
Content-Type: application/json

{
  "orderVersion": 12,
  "paymentMethod": "TRADE_CREDIT"
}
~~~

Máy chủ lấy tenant và principal từ ngữ cảnh xác thực, tải đơn hàng trong phạm vi được phép, xác định tài khoản tín dụng đã liên kết và tính lại số tiền. Nếu sản phẩm cho phép chọn tài khoản, tài khoản được chọn vẫn phải qua kiểm tra quyền và quan hệ với bên mua.

Không nhận các trường sau làm bằng chứng:

~~~json
{
  "approved": true,
  "approvedBy": "finance-director",
  "creditLimit": 999999999,
  "remainingCredit": 999999999,
  "riskPassed": true
}
~~~

Nếu API có nhận `amount` để client xác nhận số tiền đang hiển thị, máy chủ chỉ dùng nó để phát hiện lệch giá hoặc phiên bản. Giá trị đó không thay thế phép tính giá phía máy chủ.

Tổng tiền phải xét đúng số lượng, đơn giá, khuyến mãi, thuế, phí vận chuyển và quy tắc làm tròn của sản phẩm. Khi giá hoặc điều kiện liên quan đổi, authorization cũ không được tự động mở rộng theo.

### 4.2. Quyền phải bao phủ toàn bộ chuỗi đối tượng

Kiểm tra vai trò “BUYER” là chưa đủ. Cần kiểm tra quan hệ:

~~~text
principal
  -> được mua cho doanh nghiệp A
  -> thuộc tenant T
  -> được thao tác đơn O của doanh nghiệp A
  -> đơn O sử dụng tài khoản tín dụng C được phép
  -> được yêu cầu credit authorization
~~~

Với capture, principal có thể là dịch vụ giao hàng nội bộ. Khi đó vẫn cần quyền dịch vụ, phạm vi tenant, liên kết nghĩa vụ và bằng chứng đơn đã đạt trạng thái cho phép ghi nợ. Một header tự khai `X-Internal: true` không tạo ra quyền.

Một authorization ID khó đoán chỉ giảm khả năng dò tìm. Nó không thay cho kiểm tra quyền khi đọc, capture, hủy hoặc trả lại kết quả idempotency.

### 4.3. Phê duyệt phải khớp với dữ liệu được thực thi

Ví dụ chính sách yêu cầu đơn trên 20 triệu được quản lý phê duyệt. Bản phê duyệt cần gắn với phiên bản đơn, số tiền, tiền tệ và điều kiện quan trọng.

Nếu người dùng được duyệt đơn 19 triệu rồi đổi số lượng thành 29 triệu, hệ thống phải đánh giá lại điều kiện phê duyệt. Khi cần nguyên tắc người tạo và người duyệt độc lập, máy chủ phải kiểm tra hai chủ thể thực sự khác nhau và người duyệt có thẩm quyền tương ứng.

Khuyến nghị gắn quyết định với dữ liệu giao dịch và kiểm tra trước thực thi cũng xuất hiện trong [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html). Cách liên kết tài khoản, nghĩa vụ và hạn mức ở đây là thiết kế minh họa cho bài học.

## 5. State machine: được làm gì sau khi giữ chỗ?

Bài học chọn **capture một lần, có thể ít hơn số tiền đã giữ; phần còn lại được giải phóng ngay**.

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Đủ quyền, đủ hạn mức, tạo khoản giữ
    HELD --> CAPTURED: Ghi nợ một lần và giải phóng phần dư
    HELD --> CANCELLED: Hủy hợp lệ, giải phóng toàn bộ
    HELD --> EXPIRED: Hết hạn, giải phóng toàn bộ
    CAPTURED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

Yêu cầu bị từ chối không tạo khoản giữ. Kết quả từ chối có thể được lưu trong bản ghi thao tác để xử lý retry nhất quán.

### 5.1. Tác động tiền tệ của từng chuyển trạng thái

Gọi **h** là số tiền giữ ban đầu và **c** là số tiền capture:

| Hành động | Điều kiện chính | Thay đổi tài khoản | Kết quả authorization |
| --- | --- | --- | --- |
| Authorize h | h > 0, đủ A, quyền và phê duyệt hợp lệ | R tăng h | HELD |
| Capture c | HELD, chưa hết hạn, 0 < c <= h, nghĩa vụ được thực thi | R giảm h; D tăng c | CAPTURED; giải phóng h - c |
| Cancel | HELD, người gọi có quyền hủy | R giảm h | CANCELLED |
| Expire | HELD, thời hạn đã đến | R giảm h | EXPIRED |
| Retry một hành động đã hoàn tất | Khớp thao tác và quyền hiện tại cho phép xem kết quả | Không thay đổi lần nữa | Trả kết quả đã ghi |

Sau khi giữ 20 triệu, capture 15 triệu:

~~~text
Trước capture: D = 70, R = 20, A = 10 triệu
Sau capture:   D = 85, R =  0, A = 15 triệu
~~~

Không được vừa tăng D thêm 15 triệu vừa giữ nguyên R = 20 triệu. Cũng không được giải phóng 20 triệu rồi cộng thêm 15 triệu vào hạn mức, vì phần công nợ vẫn đang chiếm hạn mức.

### 5.2. Bất biến bảo toàn của một authorization

Lưu riêng:

~~~text
authorized = captured + released + remaining
~~~

- Khi HELD: captured = 0, released = 0, remaining = authorized.
- Khi CAPTURED: captured > 0, released = authorized - captured, remaining = 0.
- Khi CANCELLED hoặc EXPIRED: captured = 0, released = authorized, remaining = 0.

Đồng thời:

~~~text
account.reserved = tổng remaining của các authorization thuộc tài khoản
~~~

Đây là bất biến liên bản ghi; một `CHECK` trên một dòng tài khoản không tự chứng minh được nó.

Ở mô hình nhiều lần capture, phải bổ sung trạng thái và phép tính cho phần còn lại, định danh từng đợt, kiểm soát tổng đã capture và quy tắc đóng cuối cùng. Không áp dụng nguyên xi thuật toán giải phóng toàn bộ h của bài này.

### 5.3. Hết hạn phải kiểm tra lúc thực thi

Điều kiện capture gồm:

~~~text
state == HELD
authoritativeNow < expiresAt
~~~

Job hết hạn chỉ là cơ chế giải phóng khoản giữ. Job chưa chạy không làm authorization hết hạn trở nên hợp lệ.

Nên chọn một nguồn thời gian phía máy chủ có thẩm quyền và lấy mốc thời gian quyết định sau khi có khóa cần thiết. Nếu transaction chờ khóa lâu, timestamp lấy từ đầu request có thể đã cũ. Không dùng giờ client; khi dùng thời gian database, cần hiểu hàm thời gian đang phản ánh đầu transaction hay thời điểm thực tế.

Capture và expire cùng đến phải tranh chấp trên cùng dữ liệu bảo vệ, để chỉ một chuyển trạng thái kết thúc có hiệu lực.

## 6. Biểu diễn tiền và dữ liệu miền

Trong ví dụ VND, số tiền được lưu bằng số nguyên theo đơn vị đồng. Với tiền tệ khác, dùng quy ước minor unit đã được cấu hình và kiểm tra; không mặc định mọi loại tiền có hai chữ số thập phân.

Các nguyên tắc:

- Không dùng `float` hoặc `double` làm giá trị tiền tệ có thẩm quyền.
- Mỗi Money gồm amount và currency; không cộng hoặc so sánh trực tiếp hai loại tiền.
- Nếu dùng `BigDecimal`, tạo từ chuỗi hoặc dữ liệu thập phân chính xác, quy định scale và thời điểm làm tròn.
- Nếu dùng `long`, đặt giới hạn nghiệp vụ và kiểm tra tràn số khi cộng, trừ, nhân.
- Số tiền authorize/capture phải dương; hoàn nợ là thao tác riêng, không dùng capture âm.
- Lưu phiên bản quy tắc giá để truy vết vì sao số tiền được quyết định như vậy.

Một kiểu dữ liệu nhỏ cho ví dụ VND:

~~~java
record VndAmount(long minor) {
    VndAmount {
        if (minor <= 0 || minor > 1_000_000_000_000L) {
            throw new IllegalArgumentException("Invalid VND amount");
        }
    }
}
~~~

Giới hạn một nghìn tỷ ở đây là giả định kỹ thuật của ví dụ, không phải quy định chung. Kiểu dữ liệu này không đủ cho phép trừ số dư hoặc số tiền bằng 0; các giá trị miền khác cần validation tương ứng.

Trong hệ thống nhiều tiền tệ, tỷ giá và phiên bản tỷ giá phải thuộc quyết định phía máy chủ. Không dùng tổng các con số khác currency để xác định hạn mức chung.

## 7. Bảo vệ ở database và trong transaction

### 7.1. Phác thảo bảng hạn mức và authorization

Đoạn PostgreSQL dưới đây minh họa các ràng buộc chính, chưa phải toàn bộ schema sản phẩm:

~~~sql
CREATE TABLE credit_account (
    tenant_id UUID NOT NULL,
    account_id UUID NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    limit_minor NUMERIC(20, 0) NOT NULL CHECK (limit_minor >= 0),
    outstanding_minor NUMERIC(20, 0) NOT NULL CHECK (outstanding_minor >= 0),
    reserved_minor NUMERIC(20, 0) NOT NULL CHECK (reserved_minor >= 0),
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, account_id),
    UNIQUE (tenant_id, account_id, currency),
    CHECK (outstanding_minor + reserved_minor <= limit_minor)
);

CREATE TABLE credit_authorization (
    tenant_id UUID NOT NULL,
    authorization_id UUID NOT NULL,
    account_id UUID NOT NULL,
    currency VARCHAR(3) NOT NULL,
    obligation_id UUID NOT NULL,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    order_id UUID NOT NULL,
    order_version BIGINT NOT NULL,
    pricing_version VARCHAR(80) NOT NULL,
    policy_version VARCHAR(80) NOT NULL,
    amount_minor NUMERIC(20, 0) NOT NULL CHECK (amount_minor > 0),
    captured_minor NUMERIC(20, 0) NOT NULL CHECK (captured_minor >= 0),
    released_minor NUMERIC(20, 0) NOT NULL CHECK (released_minor >= 0),
    remaining_minor NUMERIC(20, 0) NOT NULL CHECK (remaining_minor >= 0),
    state VARCHAR(20) NOT NULL
        CHECK (state IN ('HELD', 'CAPTURED', 'CANCELLED', 'EXPIRED')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, authorization_id),
    UNIQUE (tenant_id, obligation_id, attempt_no),
    FOREIGN KEY (tenant_id, account_id, currency)
        REFERENCES credit_account (tenant_id, account_id, currency),
    CHECK (expires_at > created_at),
    CHECK (amount_minor = captured_minor + released_minor + remaining_minor),
    CHECK (
        (state = 'HELD' AND remaining_minor = amount_minor
                       AND captured_minor = 0 AND released_minor = 0)
        OR
        (state = 'CAPTURED' AND remaining_minor = 0 AND captured_minor > 0)
        OR
        (state IN ('CANCELLED', 'EXPIRED') AND remaining_minor = 0
                                         AND captured_minor = 0)
    )
);

CREATE UNIQUE INDEX one_held_authorization_per_obligation
    ON credit_authorization (tenant_id, obligation_id)
    WHERE state = 'HELD';
~~~

Cần bổ sung khóa ngoại tới đơn và nghĩa vụ, đồng thời đảm bảo nghĩa vụ ràng buộc đúng tài khoản, currency và phiên bản đơn. UUID tồn tại ở một bảng chưa đủ chứng minh quan hệ nghiệp vụ.

Index trên chỉ ngăn hai dòng HELD cùng nghĩa vụ. Nó không ngăn tạo authorization mới sau khi nghĩa vụ đã CAPTURED. Vì vậy, transaction còn phải khóa nghĩa vụ, kiểm tra nó chưa hoàn tất và bảo vệ bản ghi capture bằng unique key theo nghĩa vụ.

Khi authorization hết hạn nhưng vẫn HELD, cần chuyển trạng thái và giải phóng khoản giữ trong transaction trước khi tạo lần giữ mới. `attempt_no` do máy chủ cấp; client không được tự tăng để mở nhiều khoản giữ.

### 7.2. Chọn một điểm tuần tự hóa cho hạn mức

Một cách dễ giải thích là khóa dòng tài khoản trước khi đọc số liệu dùng để quyết định:

~~~sql
BEGIN;

SELECT limit_minor, outstanding_minor, reserved_minor, status, currency
FROM credit_account
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
FOR UPDATE;

-- Khóa nghĩa vụ liên quan, kiểm tra quyền, phiên bản và phê duyệt.
-- Kiểm tra amount > 0 và amount <= limit - outstanding - reserved.
-- Tăng reserved, tạo authorization, ghi kết quả thao tác và outbox.

COMMIT;
~~~

Trong PostgreSQL, khóa dòng `FOR UPDATE` ngăn các thao tác ghi/khóa xung đột trên dòng đó cho tới khi transaction kết thúc. Nó không tự khóa toàn bộ quan hệ nghiệp vụ; mọi luồng cấp hạn mức phải dùng cùng cơ chế bảo vệ. Xem [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/18/explicit-locking.html).

Với ví dụ hai yêu cầu 20 triệu, yêu cầu thứ hai phải quyết định sau khi yêu cầu thứ nhất commit: A khi đó chỉ còn 10 triệu.

Một phương án khác là cập nhật có điều kiện:

~~~sql
UPDATE credit_account
SET reserved_minor = reserved_minor + :amount_minor,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND status = 'ACTIVE'
  AND currency = :currency
  AND :amount_minor > 0
  AND limit_minor - outstanding_minor - reserved_minor >= :amount_minor
RETURNING account_id;
~~~

Không trả dòng nào nghĩa là chưa cấp được hạn mức. Không được tiếp tục tạo authorization như thể thành công. Cập nhật này và việc tạo authorization phải ở cùng transaction; nếu insert hoặc ghi nghĩa vụ thất bại, toàn bộ thay đổi phải rollback.

### 7.3. Phạm vi transaction phải bao phủ toàn bộ quyết định

Một transaction authorize thành công cần ghi nguyên tử:

1. Kiểm tra dữ liệu quyết định đã được bảo vệ khỏi thay đổi xung đột.
2. Tăng tổng khoản giữ của tài khoản.
3. Tạo authorization gắn đúng nghĩa vụ và phiên bản.
4. Ghi sự kiện hoặc bản ghi biến động để truy vết khoản giữ.
5. Lưu kết quả idempotency.
6. Tạo outbox event nếu cần phát thông báo ra ngoài.

Nếu mọi thao tác có cùng idempotency scope, quy ước thứ tự bảo vệ có thể là:

~~~text
idempotency operation -> credit account -> payment obligation -> authorization
~~~

Các luồng cancel, capture, expire và thay đổi hạn mức phải tuân thủ thứ tự tương thích. Khi cần nhiều tài khoản, khóa theo thứ tự ID ổn định để giảm khả năng deadlock.

Không gọi dịch vụ mạng chậm trong transaction đang giữ khóa tiền tệ. Lỗi deadlock hoặc serialization cần rollback và retry có giới hạn ở cấp toàn bộ thao tác, giữ nguyên định danh nghiệp vụ.

## 8. Phác thảo service Java: authorize có kiểm soát

Đây là mã giả Java theo phong cách service; các repository và policy thể hiện hợp đồng cần triển khai, không phải một ứng dụng có thể biên dịch ngay.

~~~java
@Transactional
public AuthorizationResult authorize(Principal principal, AuthorizeCommand cmd) {
    // Lookup này phải được giới hạn tenant và không tạo quyền từ ID client gửi.
    OrderRef ref = orders.findAccessibleRef(principal, cmd.orderId());
    permissions.requireCreditAuthorization(principal, ref);

    String fingerprint = fingerprints.forAuthorize(
        principal.tenantId(),
        principal.clientId(),
        cmd.orderId(),
        cmd.orderVersion(),
        cmd.paymentMethod()
    );

    // Claim có unique constraint; request trùng đồng thời phải chờ hoặc retry.
    OperationClaim claim = operations.claimOrLoad(
        principal.tenantId(),
        principal.clientId(),
        "AUTHORIZE_CREDIT",
        cmd.idempotencyKey(),
        fingerprint
    );

    if (claim.completed()) {
        return claim.savedResult(); // Quyền xem kết quả đã được kiểm tra.
    }

    CreditAccount account = accounts.lock(
        principal.tenantId(), ref.creditAccountId()
    );
    PaymentObligation obligation = obligations.lock(
        principal.tenantId(), ref.obligationId()
    );

    // Account binding của nghĩa vụ phải ổn định hoặc được kiểm tra lại tại đây.
    policies.requireConsistentBinding(principal, account, obligation);
    orders.requireVersionAndState(obligation, cmd.orderVersion());
    obligations.requireUnpaidAndNoActiveHold(obligation);
    account.requireActive();

    // Tính từ dữ liệu nội bộ đã khóa hoặc snapshot bất biến, không gọi mạng.
    PricingSnapshot price = pricing.forLockedObligation(obligation);
    approvals.requireValidFor(principal, obligation, price);
    price.requirePositiveAndCurrency(account.currency());

    if (!account.canReserve(price.totalMinor())) {
        return operations.completeDeclined(claim, "CREDIT_UNAVAILABLE");
    }

    Instant decisionTime = time.authoritativeNowAfterLocks();
    CreditAuthorization hold = CreditAuthorization.create(
        obligation,
        price,
        policies.currentVersionFor(account),
        decisionTime,
        expiryPolicy.expiresAt(account, decisionTime)
    );

    account.reserveExactly(hold.amountMinor());
    authorizations.insert(hold);
    movements.appendReservation(hold);
    outbox.appendCreditHeld(hold);

    return operations.completeApproved(claim, hold);
}
~~~

Các điểm cần làm rõ khi triển khai:

- `claimOrLoad` phải phát hiện cùng key nhưng fingerprint khác và trả lỗi xung đột. Nó không được trả kết quả của một payload khác.
- Mỗi `complete...` phải được lưu cùng transaction với thay đổi tương ứng.
- Lỗi sau khi giữ hạn mức phải làm rollback mọi ghi nhận của transaction. Cấu hình rollback phải khớp loại exception thực tế.
- Từ chối vì thiếu hạn mức là một kết quả nghiệp vụ; lưu nó cho key hiện tại giúp retry nhận cùng kết quả.
- `requireUnpaidAndNoActiveHold` không chỉ xem một cờ nằm trên client. Nó cần dữ liệu nghĩa vụ và authorization có thẩm quyền.
- Phê duyệt, giá và chính sách cần snapshot hoặc cơ chế version/khóa thích hợp. Kiểm tra trên bản đọc cũ rồi thực thi sau khi dữ liệu đổi vẫn tạo lỗ hổng.

Quyền được kiểm tra trước khi replay để key không trở thành cách đọc dữ liệu sau khi quyền truy cập đối tượng đã bị thu hồi.

## 9. Capture, cancel và expire phải dùng cùng bất biến

### 9.1. Capture một lần

Trong cùng transaction, sau khi claim thao tác, khóa tài khoản, nghĩa vụ và authorization theo thứ tự thống nhất:

~~~text
1. Kiểm tra quyền capture và quan hệ tenant/account/obligation.
2. Kiểm tra nghĩa vụ chưa được capture.
3. Kiểm tra authorization đang HELD và chưa hết hạn.
4. Kiểm tra phiên bản đơn, điều kiện giao hàng và chính sách capture.
5. Tính c từ dữ liệu máy chủ; yêu cầu 0 < c <= h.
6. account.reserved    -= h
   account.outstanding += c
7. authorization.captured  = c
   authorization.released  = h - c
   authorization.remaining = 0
   authorization.state     = CAPTURED
8. Ghi capture receipt duy nhất cho nghĩa vụ, biến động và outbox.
9. Ghi kết quả idempotency rồi commit.
~~~

Với trạng thái HELD của bài, h chính là remaining. Ràng buộc unique của capture receipt theo `(tenant_id, obligation_id)` bảo vệ khỏi ghi nợ lại bằng key khác hoặc authorization attempt khác.

Nếu đơn tăng giá vượt h, phải qua quy trình thay đổi được phê duyệt và cấp hạn mức bổ sung hoặc authorize lại theo chính sách. Không âm thầm capture vượt khoản giữ.

Tài khoản bị SUSPENDED luôn bị chặn authorize mới trong ví dụ. Việc capture khoản giữ đã có cần chính sách rõ ràng: có thể cho phép hoàn tất nghĩa vụ đã cam kết hoặc chặn vì lý do rủi ro. Dù chọn cách nào, không để mỗi endpoint tự quyết khác nhau.

### 9.2. Cancel và expire

Hai hành động đều chỉ giải phóng phần còn giữ khi trạng thái là HELD:

~~~text
account.reserved -= authorization.remaining
authorization.released += authorization.remaining
authorization.remaining = 0
authorization.state = CANCELLED hoặc EXPIRED
~~~

Các thay đổi phải commit cùng nhau. Không giảm R dựa trên số tiền client gửi.

Sau CAPTURED, cancel không phải hoàn nợ. Muốn giảm công nợ cần một credit note, điều chỉnh hoặc hoàn trả riêng, có quyền và bằng chứng riêng, gắn với capture gốc và giới hạn số tiền được điều chỉnh.

Job expire phải an toàn khi chạy lại. Nếu capture đã thắng và commit, job không được giải phóng khoản giữ cũ lần nữa. Nếu expire đã thắng, capture phải bị từ chối hoặc đi qua quy trình authorize mới.

## 10. Idempotency và chống lặp nghiệp vụ là hai lớp bổ sung

### 10.1. Một key phải đại diện cho cùng một ý định

Có thể đặt unique key cho bảng thao tác theo:

~~~text
(tenant_id, client_id, operation_type, idempotency_key)
~~~

Bản ghi nên gồm fingerprint của request đã chuẩn hóa, trạng thái xử lý, đối tượng kết quả và phản hồi đã chốt. Fingerprint bao gồm các trường ảnh hưởng ý định như order ID, order version và payment method; không chỉ hash số tiền.

| Tình huống | Hành vi mong muốn |
| --- | --- |
| Cùng key, cùng payload, thao tác đã commit | Trả lại kết quả được phép xem, không giữ tiền lần hai |
| Cùng key, payload khác | Từ chối xung đột |
| Cùng key, hai request đồng thời | Chỉ một request được thực hiện; request còn lại chờ hoặc nhận trạng thái để retry |
| Khác key, cùng nghĩa vụ đang giữ | Không tạo khoản giữ thứ hai |
| Khác key, nghĩa vụ đã capture | Không ghi công nợ lần nữa |
| Cùng key sau timeout không rõ commit | Tra cứu hoặc retry cùng key, không tự coi là thất bại |
| Key cũ đã hết thời gian lưu | Ràng buộc nghĩa vụ vẫn ngăn thực thi lại sai quy tắc |

Thời gian lưu key phải phù hợp chu kỳ retry và đối soát của hệ thống. Không dùng việc key đã hết TTL làm căn cứ cho phép ghi nợ lại.

Stripe cũng mô tả việc dùng key để retry và phát hiện tham số khác nhau; chi tiết phản hồi và thời gian lưu phụ thuộc phiên bản API. Xem [Stripe: Idempotent requests](https://docs.stripe.com/api/idempotent_requests). Bảng hành vi trên là hợp đồng đề xuất cho hệ thống minh họa, cần triển khai bằng database thay vì chỉ cache trong một tiến trình.

### 10.2. Timeout tạo ra trạng thái chưa biết

Ví dụ:

~~~text
Client -> Server: authorize(key=K)
Server: đã commit khoản giữ H
Server -> Client: phản hồi bị mất
Client: timeout
~~~

Timeout không chứng minh giao dịch đã rollback. Client cần retry với K hoặc gọi endpoint tra cứu thao tác có kiểm tra quyền. Nếu tự đổi sang K2, ràng buộc nghĩa vụ vẫn phải chặn tạo H2.

Không tách việc lưu key và giữ chỗ thành hai transaction độc lập. Nếu giữ chỗ commit trước nhưng key chưa lưu, retry sẽ nhìn như thao tác mới.

## 11. Khi credit authorization liên quan hệ thống bên ngoài

Một database transaction nội bộ không thể tự rollback tác động đã xảy ra tại nhà cung cấp thanh toán. Cần mô hình hóa khoảng thời gian chưa biết kết quả.

Một luồng tham khảo:

1. Transaction nội bộ tạo payment attempt, giữ phần hạn mức nội bộ cần thiết theo chính sách và ghi outbox.
2. Worker gửi yêu cầu nhà cung cấp với key ổn định theo attempt và operation.
3. Timeout chuyển attempt sang trạng thái cần xác minh, không kết luận từ chối và không tự giải phóng khoản giữ.
4. Worker tra cứu hoặc retry theo hợp đồng nhà cung cấp.
5. Khi có kết quả đáng tin cậy, transaction nội bộ cập nhật trạng thái, khoản giữ và outbox nhất quán.
6. Tác vụ đối soát phát hiện chênh lệch hoặc attempt treo quá lâu.

Các trạng thái như `PENDING_PROVIDER` và `UNKNOWN` thuộc mô hình tích hợp mở rộng, không nằm trong state machine nội bộ tối giản ở trên. Phần giữ tương ứng phải được tính vào exposure cho tới khi có cơ sở xác định việc giải phóng là an toàn.

Khi nhận webhook:

- Xác minh chữ ký và ngữ cảnh tài khoản nhà cung cấp.
- Deduplicate event, nhưng vẫn chống ghi nhận lặp theo operation nghiệp vụ vì nhiều event có thể nói về cùng một thay đổi.
- So khớp provider object với đúng payment attempt, tenant, amount và currency.
- Không cho event đến trễ đưa trạng thái đã kết thúc quay về HELD.
- Không dùng trang redirect “thanh toán thành công” trên trình duyệt làm bằng chứng đã capture.
- Với kết quả mâu thuẫn hoặc thiếu thông tin, tra cứu nguồn có thẩm quyền và đưa vào đối soát.

Thời hạn giữ thẻ phải lấy từ dữ liệu/hợp đồng của nhà cung cấp, không sao chép thời hạn giả định của hạn mức nội bộ. Stripe cung cấp thông tin hết hạn capture cho các giao dịch phù hợp trong [hướng dẫn manual capture](https://docs.stripe.com/payments/place-a-hold-on-a-payment-method).

## 12. Các đường lạm dụng và nơi chặn

| Đường lạm dụng | Hậu quả nếu chỉ kiểm tra đầu vào | Kiểm soát cần có |
| --- | --- | --- |
| Đổi account ID sang doanh nghiệp khác | Dùng hạn mức người khác | Quyền theo đối tượng và ràng buộc tenant/account/order |
| Gửi giá thấp hơn giá thật | Được giữ ít tiền rồi nhận hàng giá cao | Tính giá phía máy chủ, ràng buộc phiên bản |
| Duyệt giá thấp rồi sửa đơn | Bỏ qua ngưỡng phê duyệt | Approval gắn snapshot; dữ liệu đổi phải đánh giá lại |
| Chia đơn để né ngưỡng | Né phê duyệt hoặc hạn mức theo kỳ | Nếu chính sách xét tổng, gộp theo phạm vi và kỳ do máy chủ định nghĩa |
| Gửi nhiều key cho cùng đơn | Giữ hoặc ghi nợ nhiều lần | Ràng buộc nghĩa vụ và capture receipt duy nhất |
| Hai đơn khác nhau chạy song song | Vượt hạn mức dùng chung | Khóa hoặc cập nhật có điều kiện trên tài khoản |
| Capture authorization của đơn khác | Dùng lại sự chấp thuận sai mục đích | Ràng buộc authorization với nghĩa vụ và phiên bản |
| Capture sau hết hạn | Ghi nợ dựa trên quyết định không còn hiệu lực | Kiểm tra hạn tại thời điểm quyết định |
| Cancel lặp hoặc cancel sau capture | Cộng lại hạn mức sai | State machine và biến động nguyên tử |
| Gửi số âm, currency khác hoặc số quá lớn | Tăng hạn mức giả, sai đơn vị, tràn số | Money type, miền giá trị và currency chính xác |
| Mở nhiều đơn để giữ cạn hạn mức | Từ chối dịch vụ đối với bên mua | Quyền, giới hạn số khoản giữ, thời hạn và theo dõi bất thường |
| Giả trạng thái thành công từ client/webhook | Giao hàng hoặc tăng công nợ sai | Nguồn có thẩm quyền và xác minh tích hợp |

Rate limit giúp hạn chế lạm dụng tần suất, nhưng không thay cho bất biến tiền tệ. Một cặp yêu cầu được phép về tốc độ vẫn có thể phá hạn mức nếu transaction sai.

## 13. Kiểm thử theo chuỗi hành động và điểm lỗi

Kiểm thử business logic cần xác minh **trạng thái cuối cùng của dữ liệu**, không chỉ mã HTTP. Những tình huống sau dành cho môi trường thử nghiệm được kiểm soát.

### 13.1. Ma trận kiểm thử tối thiểu

| Nhóm | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| Biên hạn mức | Số tiền đúng bằng A | Tạo đúng một khoản giữ, A về 0 |
| Biên hạn mức | Số tiền lớn hơn A một đơn vị | Không tạo authorization, R không đổi |
| Đầu vào | 0, số âm, quá giới hạn, currency sai | Từ chối, không phát sinh biến động |
| Quyền | User tenant A dùng order hoặc account tenant B | Không đọc hoặc thay đổi đối tượng ngoài quyền |
| Giá/phê duyệt | Sửa đơn sau khi duyệt | Không sử dụng quyết định cũ cho phiên bản mới |
| Retry | Gửi cùng key và payload nhiều lần | Chỉ một khoản giữ, cùng kết quả thao tác |
| Key conflict | Cùng key nhưng đổi order hoặc version | Xung đột, không lộ kết quả của payload khác |
| Lặp nghiệp vụ | Hai key cho cùng nghĩa vụ | Tối đa một khoản giữ đang hoạt động |
| Đồng thời | Hai đơn 20 triệu khi A = 30 triệu | Tối đa một thành công, tổng exposure không vượt L |
| Capture | Giữ 20, capture 15 triệu | D tăng 15, R giảm 20, released = 5 |
| Capture lặp | Capture cùng nghĩa vụ bằng key khác | Không tăng D lần hai |
| Hết hạn | Job expire chưa chạy nhưng đã qua expiresAt | Capture vẫn bị từ chối |
| Race | Capture và expire đồng thời | Một trạng thái kết thúc thắng; tiền chỉ thay đổi một lần |
| Race | Giảm hạn mức đồng thời authorize | Không xuất hiện D + R > L trong mô hình |
| Sự cố | Lỗi giữa tăng R và insert authorization | Rollback toàn bộ, không có khoản giữ mồ côi |
| Sự cố | Commit xong nhưng mất response | Retry truy ra cùng kết quả, không tạo khoản giữ mới |
| Sự cố | Worker phát outbox sau crash | Có thể gửi lại nhưng bên nhận không áp dụng lặp |
| Tích hợp | Timeout rồi webhook thành công đến trễ | Xác minh kết quả, không authorize lại hoặc release sai |

Với race condition, dùng nhiều transaction/kết nối database thật và một barrier để hai yêu cầu bắt đầu gần nhau. Test chỉ dùng mock repository sẽ không chứng minh được hành vi khóa hoặc unique constraint.

### 13.2. Các khẳng định sau mỗi kịch bản

~~~text
outstanding >= 0
reserved >= 0
outstanding + reserved <= limit
reserved == sum(authorization.remaining)
authorization.amount == captured + released + remaining
không có hai HELD cùng nghĩa vụ
không có hai capture receipt cùng nghĩa vụ
không có biến động của tenant khác
~~~

Khi so sánh số tổng hợp và chi tiết, đọc trên snapshot nhất quán hoặc tại trạng thái đã ổn định để tránh báo chênh lệch giả do đọc hai thời điểm khác nhau.

Có thể sinh các chuỗi authorize, retry, capture, cancel và expire để tìm thứ tự thao tác bất ngờ. Mỗi bước cần kiểm tra bất biến, nhất là quanh thời điểm commit và hết hạn.

## 14. Audit, đối soát và vận hành

Mỗi quyết định nên ghi đủ dữ liệu để trả lời “ai đã cho phép nghĩa vụ nào sử dụng bao nhiêu hạn mức, theo điều kiện nào”:

- Tenant, account, order, obligation, authorization và operation ID.
- Principal hoặc service identity; quan hệ người tạo/người duyệt nếu áp dụng.
- Amount, currency, phiên bản giá, phiên bản chính sách và tham chiếu phê duyệt.
- Trạng thái trước/sau, loại biến động, thời điểm quyết định và thời điểm hết hạn.
- Mã kết quả, lý do từ chối nội bộ, correlation ID và provider reference nếu có.

Không ghi OTP, thông tin xác thực, dữ liệu thẻ đầy đủ hoặc token bí mật vào log. Thông báo phía client cần đủ để xử lý như yêu cầu duyệt lại hoặc thử lại; chi tiết rủi ro và hạn mức chỉ được cung cấp cho đối tượng có quyền xem.

Theo dõi các dấu hiệu:

- Khoản giữ đã quá hạn nhưng chưa được giải phóng.
- R khác tổng remaining, hoặc có nghĩa vụ đã capture nhưng còn HELD.
- Tỷ lệ key conflict tăng, nhiều key cùng nghĩa vụ, nhiều lần capture bị chặn.
- Thời gian chờ khóa, số lần retry transaction và các attempt bên ngoài chưa xác minh.
- Chuỗi giữ rồi hủy bất thường hoặc quá nhiều đơn không hoàn tất của cùng bên mua.

Đối soát phát hiện vấn đề, không thay thế transaction đúng. Khi phát hiện chênh lệch, không tự cộng lại hạn mức theo một bản đọc đơn lẻ. Cần xác định nguồn dữ liệu có thẩm quyền, liên kết các biến động và thực hiện điều chỉnh có audit.

Nếu bảng tài khoản là số tổng hợp còn sổ biến động là nguồn gốc, phải quy định rõ cách dựng lại số dư và xử lý sai lệch. Không coi log ứng dụng rời rạc là sổ tiền tệ có thể dùng để tái dựng chính xác.

## 15. Tiêu chí hoàn thành thiết kế

Một luồng credit authorization có thể được xem xét đầy đủ khi trả lời rõ các câu sau:

1. Định danh nghĩa vụ nào ngăn một giao dịch được thực hiện lại bằng key khác?
2. Số tiền, currency, tài khoản và phiên bản đơn được lấy từ nguồn nào?
3. Người gọi được phép thao tác trên từng đối tượng liên quan bằng căn cứ nào?
4. Phê duyệt có gắn với dữ liệu thực thi và bị đánh giá lại khi dữ liệu đổi không?
5. D + R <= L được bảo vệ ở đâu khi có nhiều request và nhiều instance?
6. Capture, cancel và expire cạnh tranh thế nào để chỉ thay đổi tiền một lần?
7. Retry sau timeout tra lại quyết định đã commit bằng cách nào?
8. Trạng thái chưa biết của nhà cung cấp có giữ được exposure cho tới khi xác minh không?
9. Quyền thay đổi hạn mức, quyền authorize và quyền capture được phân định thế nào?
10. Có thể đối chiếu số dư, authorization và biến động để giải thích từng khoản tiền không?

Điểm cốt lõi của credit authorization là một quyết định có phạm vi và thời hạn, được thực thi nguyên tử trên dữ liệu có thẩm quyền. Quyết định đó chỉ bảo vệ được quy tắc nghiệp vụ khi không thể bị mở rộng sang đối tượng khác, dùng lại cho nghĩa vụ khác hoặc áp dụng nhiều lần do cạnh tranh và retry.
