# Unique business constraint

## 1. Tính duy nhất phải gắn với ý nghĩa nghiệp vụ

Trong chương **Database Constraints** của module bảo vệ logic nghiệp vụ, một unique business constraint là ràng buộc ở cơ sở dữ liệu nhằm ngăn hai bản ghi cùng đại diện cho một điều mà nghiệp vụ chỉ cho phép tồn tại một lần trong phạm vi xác định.

Ví dụ:

- Một khách hàng chỉ được nhận một quyền lợi từ một chiến dịch trong cùng tenant.
- Một yêu cầu hoàn tiền chỉ tạo một kết quả hoàn tiền tương ứng.
- Một người dùng chỉ có một membership đang chiếm chỗ trong một chương trình.
- Một phiên bản yêu cầu chỉ có một quyết định kết thúc theo mô hình phê duyệt đã chọn.
- Một đối tác chỉ được dùng một mã tham chiếu giao dịch một lần trong namespace của đối tác đó.

Điểm quan trọng nằm ở **định danh nghiệp vụ**, không chỉ ở khóa chính kỹ thuật. Hai hàng có hai UUID khác nhau vẫn có thể là hai lần cấp cùng một quyền lợi cho cùng khách hàng.

```text
id=A, tenant=T, campaign=C, customer=U
id=B, tenant=T, campaign=C, customer=U
```

`PRIMARY KEY (id)` không phát hiện hai hàng trên trùng ý nghĩa. Nếu quy tắc là một lần nhận quyền lợi cho mỗi khách hàng trong mỗi chiến dịch, cần ràng buộc trên:

```text
(tenant_id, campaign_id, customer_id)
```

Bài học này giải thích cách chọn bộ cột đó, đưa ràng buộc vào transaction và xử lý xung đột mà không bỏ qua quyền, ghi đè dữ liệu cũ hoặc tạo thêm tác động bên ngoài.

## 2. Viết invariant và chọn business key

Trước khi viết `UNIQUE`, hãy diễn đạt quy tắc bằng một câu có thể kiểm tra:

> Trong một tenant, mỗi khách hàng chỉ có một record nhận quyền lợi của một chiến dịch trong toàn bộ vòng đời record, kể cả khi record đã bị hủy theo chính sách của ví dụ.

Từ đó xác định:

```text
Phạm vi: tenant
Loại quyền lợi: campaign
Đối tượng nhận: customer ổn định
Số record được phép: tối đa một
Vòng đời: không cấp lại chỉ bằng cách hủy hoặc ẩn record cũ
```

Đây là chính sách minh họa. Nếu nghiệp vụ cho phép cấp lại sau khi hủy, business key hoặc mô hình vòng đời phải thể hiện điều đó một cách có chủ đích.

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Tenant | Tính duy nhất là toàn hệ thống hay trong từng tổ chức? |
| Chủ thể nghiệp vụ | Dùng customer, merchant, tài khoản hay actor đang thao tác? |
| Tài nguyên hoặc chương trình | Quy tắc áp dụng theo campaign, order, refund request hay loại quyền lợi? |
| Khoảng nghiệp vụ | Một lần trọn đời, một lần mỗi kỳ hay một lần mỗi phiên bản được duyệt? |
| Trạng thái | Tất cả record hay chỉ những record đang chiếm quyền? |
| Biểu diễn | Những giá trị nào được xem là giống nhau, kể cả hoa thường hoặc giá trị thiếu? |

Một số lựa chọn sai thường gặp:

- Thêm `created_at` vào bộ unique khiến mỗi lần tạo có timestamp khác nhau và mọi bản sao đều hợp lệ.
- Thêm actor ID dù actor chỉ là người thao tác thay khách hàng; đổi nhân viên sẽ tạo namespace mới.
- Thêm API key ID khiến việc xoay credential cho phép dùng lại cùng mã tham chiếu nghiệp vụ.
- Thêm `rule_version` khi quy tắc thực sự là một lần cho cả campaign; cập nhật cấu hình vô tình mở thêm lượt nhận.
- Dùng ngày từ client khi chính sách quy định kỳ theo lịch có thẩm quyền của server.

Không thêm cột chỉ để làm hết lỗi trùng. Mỗi cột trong business key phải có lý do nghiệp vụ rõ ràng.

## 3. Vì sao kiểm tra trước khi INSERT không đủ?

Một cách cài đặt phổ biến nhưng có race condition:

```text
Nếu chưa có record cho (tenant, campaign, customer):
    tạo record
    cấp quyền lợi
```

Hai request có thể cùng đi qua kiểm tra:

| Bước | Request A | Request B |
| --- | --- | --- |
| 1 | SELECT không thấy record | |
| 2 | | SELECT không thấy record |
| 3 | INSERT với ID A | |
| 4 | | INSERT với ID B |
| 5 | Cấp quyền lợi | Cấp quyền lợi |

Ngay cả khi mỗi request có transaction riêng, điều kiện “chưa có” có thể vẫn đúng trong lần đọc của cả hai. Một attacker có thể chủ động tạo nhiều request song song để tăng khả năng vượt kiểm tra.

Kiểm tra ở application vẫn có ích để trả thông báo sớm, nhưng nó không phải hàng rào duy nhất. Unique constraint tạo điểm phân xử tại database cho những request cùng business key.

Khóa trong bộ nhớ một process cũng không đủ khi có nhiều instance, job nền hoặc công cụ quản trị cùng ghi. Ràng buộc cần tồn tại tại nơi lưu dữ liệu có thẩm quyền, trong phạm vi uniqueness mà hệ thống thực sự bảo đảm.

## 4. Ví dụ schema: một quyền lợi cho mỗi khách hàng và chiến dịch

Các ví dụ SQL bên dưới dùng PostgreSQL. Cú pháp chỉ mục có điều kiện, xử lý conflict và hành vi transaction cần được đối chiếu khi chuyển sang hệ quản trị khác.

```sql
CREATE TABLE coupon_redemption (
    id                    uuid        PRIMARY KEY,
    tenant_id             uuid        NOT NULL,
    campaign_id           uuid        NOT NULL,
    customer_id           uuid        NOT NULL,
    order_id              uuid        NOT NULL,
    command_fingerprint   bytea       NOT NULL,
    discount_minor        bigint      NOT NULL,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_redemption_once_per_customer
        UNIQUE (tenant_id, campaign_id, customer_id)
        NOT DEFERRABLE,
    CONSTRAINT ck_redemption_positive_discount
        CHECK (discount_minor > 0),
    CONSTRAINT ck_redemption_fingerprint_length
        CHECK (octet_length(command_fingerprint) = 32)
);
```

Trong ví dụ:

- `id` là định danh kỹ thuật của record.
- Bộ `(tenant_id, campaign_id, customer_id)` là business key.
- `order_id` là dữ liệu gắn với lần sử dụng, không phải chiều cho phép dùng lại quyền lợi ở đơn khác.
- `command_fingerprint` ràng buộc nội dung command để phân biệt gửi lại cùng ý định với một ý định khác nhắm cùng business key; ví dụ giả định digest SHA-256 dài 32 byte.
- `discount_minor` là giá trị được server tính và chấp nhận theo quy tắc giá, không phải giá trị client được tùy ý quyết định.

Các quan hệ tới campaign, customer và order còn cần foreign key phù hợp với tenant; phần sau minh họa riêng việc đó. Đây chưa phải toàn bộ schema thương mại điện tử.

### 4.1. Chọn đúng số cột

Nếu đổi thành:

```text
UNIQUE (tenant_id, campaign_id, customer_id, order_id)
```

thì một khách hàng có thể dùng quyền lợi ở nhiều đơn khác nhau. Đây là quy tắc khác, không phải phiên bản “đầy đủ hơn” của ràng buộc ban đầu.

Nếu bỏ `tenant_id`, tính duy nhất có thể bị áp dụng toàn hệ thống trong khi các tenant có namespace độc lập. Điều đó có thể gây từ chối nhầm hoặc trở thành kênh dò dữ liệu giữa tenant.

Nếu chỉ dùng `UNIQUE (id)`, database không thể nhận biết các bản sao nghiệp vụ có UUID khác nhau.

### 4.2. Không dùng hash làm chiều để né trùng

Ràng buộc sau làm payload khác trở thành record khác:

```text
UNIQUE (tenant_id, campaign_id, customer_id, command_fingerprint)
```

Một caller có thể đổi order hoặc tham số command để tạo fingerprint mới rồi nhận thêm quyền lợi. Fingerprint là dữ liệu so sánh, không phải một chiều làm suy yếu invariant “mỗi khách hàng một lần”.

Khi business key vừa với các kiểu dữ liệu thông thường, ưu tiên lưu và ràng buộc trực tiếp các thành phần có ý nghĩa. Chỉ lưu một hash của business key đưa thêm vấn đề encoding và va chạm hash mà ứng dụng phải xử lý rõ ràng.

## 5. Đưa ràng buộc vào cùng transaction với tác động

Một luồng an toàn cho tác động hoàn toàn trong database:

```text
1. Xác thực và xác định tenant cùng customer được phép thao tác.
2. Parse, kiểm tra command và xác minh quyền trên campaign, order.
3. Bắt đầu transaction.
4. Đọc hoặc khóa dữ liệu có thẩm quyền cần để tính quyền lợi.
5. Thử tạo coupon_redemption với business key được bảo vệ.
6. Nếu tạo được, áp dụng giảm giá và lưu kết quả trong cùng transaction.
7. Nếu không tạo được, không áp dụng thêm giảm giá; phân loại record cũ.
8. Commit trước khi xác nhận kết quả thay đổi đã bền vững.
```

Ví dụ thao tác giành quyền tạo record:

```sql
INSERT INTO coupon_redemption (
    id, tenant_id, campaign_id, customer_id,
    order_id, command_fingerprint, discount_minor
) VALUES (
    :id, :tenantId, :campaignId, :customerId,
    :orderId, :commandFingerprint, :discountMinor
)
ON CONFLICT ON CONSTRAINT uq_redemption_once_per_customer
DO NOTHING
RETURNING id;
```

Có dòng trả về nghĩa là transaction hiện tại đã chèn được record. Điều đó chưa đồng nghĩa transaction đã commit hoặc tác động giảm giá đã hoàn tất.

Không có dòng trả về nghĩa là không được cấp thêm quyền lợi. Cần đọc record theo đúng business key, kiểm tra quyền và phân loại theo hợp đồng.

Trong PostgreSQL, thao tác có thể phải đợi một transaction đang cạnh tranh cùng key kết thúc. Nếu transaction kia rollback, bên đang chờ có thể chèn thành công. Không cần bảo đảm request đến mạng trước luôn là bên thắng.

Ở Read Committed, sau câu INSERT có conflict đã hoàn tất, dùng câu SELECT tiếp theo để đọc record đã commit khi cần. Các mức cô lập khác, timeout và cơ chế dọn dữ liệu có thể đòi hỏi xử lý khác; không mặc định mọi cách ghép INSERT và SELECT trong một snapshot đều thấy được record cạnh tranh.

### 5.1. Vì sao phải cùng transaction?

Nếu commit redemption trước rồi mới áp dụng giảm giá, process có thể chết ở giữa và để lại record đã chiếm quyền nhưng chưa có kết quả. Nếu áp dụng giảm giá trước rồi mới tạo redemption ở transaction khác, hai request có thể cùng tạo tác động trước khi một bên gặp lỗi trùng.

Với dữ liệu nội bộ, đặt record nhận quyền, thay đổi đơn và kết quả liên quan trong cùng transaction giúp chúng cùng commit hoặc cùng rollback.

Nếu business flow thực sự cần trạng thái giữ chỗ dài hạn, hãy mô hình hóa nó bằng state machine và cơ chế phục hồi rõ ràng. Không coi mọi record chưa hoàn tất là được phép xóa rồi chạy lại.

### 5.2. Unique không thay thế kiểm soát đồng thời trên đơn

Hai campaign khác nhau có thể có hai business key khác nhau nhưng cùng tác động vào một đơn. Unique theo campaign và customer không ngăn tổng giảm giá vượt mức cho phép.

Đơn hàng cần cập nhật có điều kiện, khóa hoặc cơ chế transaction phù hợp để giữ các invariant về tổng tiền, trạng thái và kết hợp khuyến mãi. Các lớp này giải quyết vấn đề khác với tính duy nhất của quyền lợi.

## 6. Xử lý conflict mà không che giấu lỗi hoặc ghi đè dữ liệu

### 6.1. Xung đột không luôn là retry hợp lệ

Giả sử record đã tồn tại cho khách hàng U và campaign C:

| Request mới | Cách diễn giải |
| --- | --- |
| Cùng command gốc, cùng đơn, caller còn quyền | Có thể trả lại kết quả đã ghi nếu API có hợp đồng replay |
| Đổi sang đơn khác nhưng giữ customer và campaign | Một lần sử dụng khác bị business constraint chặn |
| Cùng ID khách hàng nhưng caller không được đại diện | Lỗi quyền, không được đọc hay nhận kết quả cũ |
| Khác tenant hợp lệ | Business key độc lập theo mô hình ví dụ |

Không trả thành công chung chung cho mọi conflict. Client có thể hiểu nhầm quyền lợi đã được áp dụng cho đơn mới trong khi record cũ thuộc đơn khác.

Một lỗi minh họa cho caller được phép truy cập phạm vi:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "CAMPAIGN_BENEFIT_ALREADY_CLAIMED",
  "message": "Quyền lợi này đã được sử dụng trong phạm vi cho phép.",
  "requestId": "req-901"
}
```

Đây là lựa chọn hợp đồng của ví dụ. Không đưa order ID, dữ liệu khách hàng khác hoặc thông báo SQL nội bộ vào lỗi nếu caller không có quyền xem.

### 6.2. Không ghi đè record gốc để làm hết conflict

Mẫu nguy hiểm:

```sql
-- Sai với hợp đồng record gốc thuộc một lần sử dụng bất biến.
INSERT INTO coupon_redemption (...)
VALUES (...)
ON CONFLICT ON CONSTRAINT uq_redemption_once_per_customer
DO UPDATE SET order_id = EXCLUDED.order_id;
```

Thao tác này có thể chuyển một quyền lợi đã sử dụng sang đơn khác và làm mất dấu vết ban đầu. Nếu cho phép chuyển quyền lợi, đó phải là một command nghiệp vụ riêng, có quyền, state machine và xử lý tác động liên quan.

Tương tự, không xóa record cũ rồi chèn lại chỉ vì client nhận lỗi trùng.

### 6.3. Phân loại lỗi bằng mã và constraint cụ thể

Trong PostgreSQL, SQLSTATE `23505` biểu thị unique violation. Tuy nhiên, một bảng có thể có nhiều unique constraint, kể cả khóa chính kỹ thuật.

Ứng dụng nên phân loại bằng SQLSTATE cùng thông tin constraint và ngữ cảnh thao tác, không dựa vào việc chuỗi lỗi có chứa từ “duplicate” hay không. Một lỗi trùng UUID kỹ thuật không mặc định là “khách hàng đã dùng quyền lợi”.

Các lỗi foreign key, NOT NULL hoặc CHECK không nên bị chuyển hết thành cùng một lỗi trùng nghiệp vụ. Không trả trực tiếp tên bảng, giá trị nhạy cảm và chi tiết driver cho client.

Nếu dùng INSERT thông thường và gặp lỗi constraint trong PostgreSQL, transaction có thể ở trạng thái lỗi cho đến khi rollback hoặc rollback về savepoint phù hợp. Không catch exception rồi tiếp tục SELECT trên transaction đã lỗi như thể chưa có gì xảy ra.

`ON CONFLICT` theo đúng constraint dự kiến giúp xử lý đường cạnh tranh bình thường mà không che mọi lỗi khác. Dùng `DO NOTHING` không chỉ rõ mục tiêu có thể vô tình che một xung đột khác mà ứng dụng cần biết.

## 7. Tenant, foreign key và quyền đối tượng

### 7.1. Uniqueness đúng scope chưa chứng minh dữ liệu thuộc đúng tenant

Ràng buộc:

```text
UNIQUE (tenant_id, campaign_id, customer_id)
```

không tự chứng minh campaign, customer và order đều thuộc tenant đó. Nếu các ID được tham chiếu mà không ràng buộc tenant, một hàng có thể kết hợp đối tượng từ những tenant khác nhau.

Ví dụ bổ sung foreign key, giả định bảng cha có khóa duy nhất tương ứng:

```sql
ALTER TABLE coupon_redemption
ADD CONSTRAINT fk_redemption_campaign
FOREIGN KEY (tenant_id, campaign_id)
REFERENCES coupon_campaign (tenant_id, id);

ALTER TABLE coupon_redemption
ADD CONSTRAINT fk_redemption_customer
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customer_account (tenant_id, id);
```

Bảng cha cần có primary key hoặc unique constraint phù hợp trên bộ cột được tham chiếu. Việc `id` riêng lẻ là primary key không có nghĩa mọi hệ quản trị tự chấp nhận một foreign key tham chiếu bộ `(tenant_id, id)` mà không có cấu trúc khóa tương ứng.

### 7.2. Đúng tenant vẫn chưa chắc đúng khách hàng của đơn

Hai customer trong cùng tenant có thể có hai đơn khác nhau. Foreign key chỉ trên `(tenant_id, order_id)` chưa buộc `customer_id` của redemption trùng customer của đơn.

Nếu mô hình yêu cầu điều đó và cột customer của đơn có ngữ nghĩa ổn định phù hợp, có thể biểu diễn quan hệ bằng khóa ghép:

```sql
ALTER TABLE purchase_order
ADD CONSTRAINT uq_order_tenant_id_customer
UNIQUE (tenant_id, id, customer_id);

ALTER TABLE coupon_redemption
ADD CONSTRAINT fk_redemption_order_customer
FOREIGN KEY (tenant_id, order_id, customer_id)
REFERENCES purchase_order (tenant_id, id, customer_id);
```

Cần quyết định rõ hành vi khi đổi chủ sở hữu hoặc chuyển đơn: không để một cập nhật quan hệ vô tình chuyển lịch sử nhận quyền lợi. Nếu quan hệ không được biểu diễn như ví dụ, application vẫn phải kiểm tra và giữ nó nhất quán bằng cơ chế transaction phù hợp.

### 7.3. Foreign key không thay authorization

Một caller biết customer ID hợp lệ có thể cố tạo redemption cho người khác để chiếm lượt nhận của họ. Mọi foreign key và unique constraint đều có thể thỏa mãn trong khi hành động vẫn trái phép.

Máy chủ phải xác minh caller được thao tác thay customer và được dùng order, campaign tương ứng. Tenant và business subject không được lấy nguyên từ body rồi coi là đã được cấp quyền.

## 8. NULL, chuẩn hóa và quy tắc so sánh

### 8.1. Cột thuộc business key thường cần NOT NULL

Trong PostgreSQL, UNIQUE theo mặc định cho phép nhiều giá trị NULL. Một bộ unique ghép có thành phần NULL có thể không tạo bảo đảm mà ứng dụng đang tưởng rằng nó có.

Ví dụ cấu trúc yếu:

```sql
CREATE TABLE external_reference (
    id                uuid PRIMARY KEY,
    tenant_id         uuid,
    partner_id        uuid,
    partner_reference varchar(100),
    UNIQUE (tenant_id, partner_id, partner_reference)
);
```

Nếu `partner_reference` bắt buộc cho một giao dịch được tiếp nhận, để nó NULL có thể mở đường tạo nhiều record không được phân biệt đúng.

Hãy xác định ngữ nghĩa:

- Nếu thành phần bắt buộc để xác lập danh tính, dùng NOT NULL và kiểm tra giá trị hợp lệ.
- Nếu reference thực sự tùy chọn, phải nói rõ uniqueness áp dụng khi nào.
- Nếu yêu cầu các giá trị thiếu cũng xung đột nhau, dùng cơ chế database hỗ trợ đúng ngữ nghĩa đó hoặc đổi mô hình dữ liệu; không giả định mặc định của mọi hệ quản trị giống nhau.

Không tự thay NULL bằng chuỗi rỗng hay một ID giả mà chưa phân tích va chạm với giá trị hợp lệ. NOT NULL cũng không loại bỏ chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng.

### 8.2. Hai giá trị giống nhau theo nghiệp vụ phải được biểu diễn nhất quán

Ví dụ mã chiến dịch chỉ cho phép chữ hoa ASCII, chữ số, `_` và `-`. Có thể lưu một dạng chuẩn với điều kiện rõ ràng:

```sql
CREATE TABLE campaign_code_registry (
    tenant_id      uuid NOT NULL,
    campaign_code  varchar(50) COLLATE "C" NOT NULL,
    CONSTRAINT ck_campaign_code_format
        CHECK (campaign_code ~ '^[A-Z0-9_-]+$'),
    CONSTRAINT uq_campaign_code_per_tenant
        UNIQUE (tenant_id, campaign_code)
);
```

Ví dụ này từ chối dạng không đúng hợp đồng ở database. Nếu application cho phép client nhập chữ thường và chuẩn hóa trước khi lưu, quy tắc chuyển đổi phải xác định và thống nhất ở mọi đường ghi.

Với dữ liệu Unicode, mã từ đối tác hoặc định danh phân biệt hoa thường, không áp dụng viết thường và trim một cách máy móc. Collation, Unicode normalization và quy tắc dấu cách có thể thay đổi quan hệ “bằng nhau”.

Unique constraint chỉ kiểm tra theo biểu diễn và quy tắc so sánh được cấu hình. Nó không tự biết hai tài khoản có thuộc cùng người ngoài đời hay hai chuỗi có cùng ý nghĩa nghiệp vụ.

## 9. Tính duy nhất theo trạng thái và vòng đời dữ liệu

### 9.1. Khi chỉ một record đang chiếm quyền được phép tồn tại

Một membership có thể có nhiều bản ghi lịch sử nhưng chỉ một bản ghi đang chiếm suất. Giả sử các trạng thái chiếm suất là:

```text
PENDING, ACTIVE, CANCEL_PENDING, UNKNOWN
```

`UNKNOWN` vẫn chiếm suất vì hệ thống chưa biết tác động cũ đã kết thúc hay chưa. `CANCEL_PENDING` chưa giải phóng suất cho đến khi việc hủy được xác nhận theo nghiệp vụ.

Ví dụ PostgreSQL:

```sql
CREATE UNIQUE INDEX uq_membership_occupied_slot
ON membership (tenant_id, program_id, customer_id)
WHERE state IN ('PENDING', 'ACTIVE', 'CANCEL_PENDING', 'UNKNOWN');
```

Đây là partial unique index, không phải cú pháp UNIQUE constraint toàn bảng. Khi xử lý INSERT hoặc UPDATE, application cần dùng cách nhận diện conflict phù hợp với loại chỉ mục và cú pháp của database.

Nếu chỉ đưa `ACTIVE` vào predicate, hai record `PENDING` có thể cùng được tạo rồi cùng bắt đầu cấp quyền bên ngoài. Việc một UPDATE sau đó gặp lỗi unique có thể đã quá muộn để ngăn tác động trùng.

Mọi cập nhật trạng thái phải tuân theo state machine, quyền và kết quả thực tế. Caller không được tự chuyển record cũ sang trạng thái ngoài predicate để mở thêm suất.

### 9.2. Không thêm cờ active vào unique một cách máy móc

```text
UNIQUE (tenant_id, program_id, customer_id, active)
```

Cấu trúc này thường chỉ cho phép một hàng `active=true` và một hàng `active=false` cho cùng bộ khóa, thay vì một hàng hoạt động và nhiều hàng lịch sử. Nó cũng có thể có hành vi ngoài dự kiến nếu cờ được để NULL.

Partial unique index hoặc tách bảng trạng thái hiện hành với bảng lịch sử thường diễn đạt rõ hơn, tùy mô hình.

### 9.3. Thời gian và soft delete cần chính sách riêng

Một partial index không nên được thiết kế như thể predicate theo `now()` sẽ tự đánh giá lại mọi hàng theo thời gian trôi qua. Trong PostgreSQL, biểu thức dùng cho predicate của index còn phải đáp ứng yêu cầu về tính bất biến. Hãy dùng trạng thái được duy trì đúng hoặc một mô hình thời gian khác phù hợp.

Nếu quy tắc là “không có hai khoảng hiệu lực chồng nhau”, unique trên thời điểm bắt đầu hoặc kết thúc thường không đủ. Có thể cần exclusion constraint, khóa hoặc transaction isolation phù hợp với predicate và database mục tiêu.

Với soft delete, một unique index chỉ áp dụng khi `deleted_at IS NULL` cho phép tạo lại business key sau khi xóa mềm. Điều đó đúng hay sai phụ thuộc chính sách cấp lại, không phải chỉ là lựa chọn tiện cho màn hình quản trị.

### 9.4. Xóa record có thể xóa luôn hàng rào chống trùng

Nếu coupon chỉ được dùng một lần trọn chiến dịch, xóa redemption để dọn dữ liệu có thể khiến cùng business key được cấp lại. Cần retention hoặc dấu vết tối thiểu phù hợp để giữ invariant sau khi đã dọn dữ liệu hiển thị.

Không coi việc xóa audit, archive hoặc chuyển bảng là thao tác thuần vận hành nếu nó làm mất phạm vi constraint. Cần xác định nguồn nào còn có thẩm quyền nhận diện quyền lợi đã dùng.

## 10. Phân biệt business uniqueness với idempotency

Hai lớp thường đi cùng nhau nhưng không thay thế nhau:

| Lớp | Bảo vệ điều gì? | Caller đổi khóa request thì sao? |
| --- | --- | --- |
| Idempotency | Nhận diện các lần gửi lại cùng ý định theo scope và key | Một key mới có thể là một ý định mới đối với lớp này |
| Unique business constraint | Không cho hai record cùng business identity tồn tại trong phạm vi quy định | Vẫn chặn dù caller dùng key mới |

Ví dụ:

```text
K1 + nhận quyền lợi campaign C cho customer U -> thành công
K1 + cùng command -> replay theo hợp đồng idempotency
K2 + nhận lại quyền lợi C cho U -> business unique chặn
K1 + đổi sang command khác -> idempotency mismatch nếu cùng scope
```

Business key không nên lấy trực tiếp từ một giá trị ngẫu nhiên mà attacker có quyền đổi nếu quy tắc thực sự gắn với customer và campaign.

Tương tự, `UNIQUE (tenant_id, refund_request_id)` chỉ bảo đảm một record cho một refund request. Nếu caller có thể tạo nhiều refund request hợp lệ khác nhau, hệ thống vẫn phải giữ invariant về tổng tiền đã hoàn và đang được giữ chỗ.

Một mã tham chiếu do đối tác cấp có thể là business key hợp lệ nếu hợp đồng thực sự yêu cầu đối tác không tái sử dụng mã trong namespace đó. Cần ràng buộc đúng đối tác ổn định, không chỉ một credential hiện tại.

## 11. Những invariant mà UNIQUE không thể tự bảo vệ

| Quy tắc | Vì sao UNIQUE chưa đủ? | Cơ chế bổ sung có thể cần |
| --- | --- | --- |
| Tổng giảm giá không vượt tổng tiền đơn | Có nhiều redemption hợp lệ với key khác nhau | Cập nhật có điều kiện, khóa hoặc transaction phù hợp |
| Tổng hoàn tiền không vượt số đã thu | Mỗi refund request khác nhau vẫn duy nhất | Sổ giao dịch, giữ chỗ và invariant tổng |
| Người tạo không tự phê duyệt | Record vẫn có thể duy nhất nhưng actor sai | Authorization và kiểm tra phân tách nhiệm vụ |
| Trạng thái không bị lùi | Cùng một record có thể bị UPDATE sai | State machine, version và điều kiện chuyển trạng thái |
| Dữ liệu thuộc đúng tenant | Bộ unique không kiểm tra quan hệ đối tượng | Foreign key ghép và quyền đối tượng |
| Hai khoảng đặt chỗ không chồng nhau | Hai khoảng khác điểm đầu vẫn có thể chồng | Cơ chế chống chồng khoảng hoặc điều phối đúng |
| Một tác động ngoài chỉ xảy ra một lần | Database không rollback được dịch vụ ngoài | Outbox, idempotency phía nhận và đối soát |

Check constraint và foreign key nên bổ sung khi biểu diễn được quy tắc. Transaction và isolation phải bao trọn các bước đọc–ghi quyết định. Không chọn một constraint rồi coi mọi đường lạm dụng logic đã được giải quyết.

## 12. Nhiều service, shard và tác động bên ngoài

### 12.1. Tính duy nhất cục bộ chưa chắc là tính duy nhất toàn hệ thống

Nếu hai shard đều có `UNIQUE (tenant_id, campaign_id, customer_id)` nhưng cùng business key có thể ghi vào cả hai shard, mỗi shard có thể chấp nhận một hàng.

Routing cần đưa cùng business identity đến cùng nơi có thẩm quyền, hoặc có cơ chế uniqueness phân tán đáp ứng yêu cầu. Không thêm shard ID hay region ID vào business key chỉ để các bản sao không còn conflict nếu nghiệp vụ vẫn yêu cầu một lần trên toàn hệ thống.

Đồng bộ bất đồng bộ rồi chọn một bản ghi thắng không hoàn tác hai quyền lợi đã được cấp. Việc hội tụ record sau đó khác với việc ngăn tác động trùng ngay từ đầu.

### 12.2. Unique phải bao phủ mọi đường ghi được phép

Một constraint ở database có thể chặn cả API, batch và job nền nếu chúng cùng ghi đúng bảng được bảo vệ. Nhưng vẫn có thể bị bỏ qua về mặt nghiệp vụ khi:

- Một service khác lưu record tương đương ở bảng riêng không có hàng rào chung.
- Một job tạo tác động trước khi ghi vào bảng có unique.
- Công cụ quản trị xóa record nhận diện rồi cấp lại.
- Một tài khoản đặc quyền thay đổi hoặc gỡ constraint ngoài quy trình kiểm soát.
- Hệ thống archive dữ liệu sang nơi khác nhưng tiếp tục nhận ghi mới mà không tra cứu dấu vết cũ.

Quyền của tài khoản ứng dụng không nên bao gồm thay đổi schema nếu ứng dụng không cần nhiệm vụ đó. Tuy nhiên, giới hạn quyền kỹ thuật cũng không thay thế quy trình nghiệp vụ cho các thao tác sửa dữ liệu đặc quyền.

### 12.3. Ghi ý định và outbox trước tác động ngoài

Mẫu nguy hiểm là gọi bên cấp quyền lợi hoặc nhà cung cấp thanh toán trước, rồi mới INSERT record có unique. Hai request có thể cùng tạo tác động; chỉ sau đó một bên mới biết mình bị trùng.

Một hướng thiết kế:

```text
Transaction nội bộ:
    giành business identity bằng constraint
    kiểm tra và ghi trạng thái nghiệp vụ
    ghi command vào outbox với intent ổn định
    commit

Worker:
    giao command có thể được gửi lại
    dùng idempotency hoặc định danh nghiệp vụ ở nơi tạo tác động
    ghi kết quả và đối soát khi chưa xác định
```

Outbox không tạo bảo đảm giao đúng một lần. Unique trên record nội bộ cũng không đủ nếu mỗi lần worker gửi lại đều tạo tác động mới ở downstream. Cần giữ định danh ý định và hiểu namespace chống trùng của bên nhận.

## 13. Thêm constraint vào dữ liệu đang tồn tại

Đối với một bảng legacy chưa có ràng buộc, không nên chỉ thêm UNIQUE rồi chờ database tự quyết định bản ghi nào đúng.

Một truy vấn khảo sát trùng theo business key:

```sql
SELECT tenant_id, campaign_id, customer_id, COUNT(*) AS duplicate_count
FROM coupon_redemption
GROUP BY tenant_id, campaign_id, customer_id
HAVING COUNT(*) > 1;
```

Cũng cần kiểm tra NULL, giá trị sai định dạng, quy tắc chuẩn hóa và các quan hệ tenant. Không chỉ tìm hai chuỗi giống hệt nếu nghiệp vụ định nghĩa bằng nhau theo dạng chuẩn khác.

Quy trình thay đổi cần xác định:

1. Invariant và business key cuối cùng đã được thống nhất.
2. Những đường ghi nào có thể tiếp tục tạo dữ liệu trùng trong lúc xử lý dữ liệu cũ.
3. Mỗi nhóm trùng đã gây tác động nghiệp vụ gì: quyền lợi đã cấp, tiền đã chuyển, hóa đơn đã phát hành.
4. Cách đối soát, hợp nhất hoặc bù trừ theo nghiệp vụ, giữ audit trail phù hợp.
5. Cách đưa constraint hoặc unique index vào mà không để cửa sổ ghi trùng mới và phù hợp khả năng migration của database.
6. Cách kiểm tra ràng buộc đã có hiệu lực và application xử lý conflict đúng.

Không xóa tùy tiện một hàng trùng chỉ vì nó có thời điểm tạo muộn hơn. Xóa record không thu hồi tác động bên ngoài và có thể phá foreign key hoặc lịch sử kiểm toán.

Việc tạo index online, đồng thời hoặc chuyển index thành constraint có điều kiện riêng theo hệ quản trị. Cần chuẩn bị phương án theo database thực tế, khả năng khóa và trạng thái khi migration thất bại. Các bước trong bài là hướng dẫn thiết kế; không phải lệnh yêu cầu chạy migration trên một hệ thống đang hoạt động.

## 14. Ma trận kiểm thử business uniqueness

Giả định chính sách chính: mỗi customer chỉ có một redemption cho mỗi campaign trong một tenant, không cấp lại khi xóa mềm.

| Ca kiểm thử | Kết quả cần có |
| --- | --- |
| Hai request tuần tự cùng business key | Không tạo record hoặc tác động thứ hai |
| Nhiều request đồng thời trên nhiều connection | Tối đa một transaction tạo được record tương ứng |
| Cùng business key nhưng UUID record khác nhau | Vẫn bị business unique chặn |
| Cùng business key nhưng idempotency key khác nhau | Vẫn giữ invariant một lần |
| Cùng customer và campaign, đổi order | Không cấp quyền lợi ở order mới trái chính sách |
| Cùng UUID kỹ thuật nhưng business key khác | Phân loại đúng lỗi khóa chính, không giả thành đã dùng quyền lợi |
| Cùng command được gửi lại sau mất response | Replay hoặc conflict đúng hợp đồng; không tạo thêm giảm giá |
| Customer khác hợp lệ trong cùng campaign | Có thể nhận độc lập nếu quy tắc cho phép |
| Cùng giá trị định danh trong tenant khác hợp lệ | Không xung đột ngoài phạm vi đã chọn |
| Caller dùng customer hoặc order của người khác | Từ chối quyền, không chiếm lượt của nạn nhân |
| Kết hợp campaign, customer, order từ tenant khác nhau | Bị kiểm tra quyền và ràng buộc quan hệ phù hợp chặn |
| Thành phần business key bị thiếu hoặc NULL | Không lọt qua invariant do cấu hình nullable ngoài ý muốn |
| Mã sai chuẩn, khác hoa thường hoặc thêm khoảng trắng | Hành vi đúng hợp đồng biểu diễn, không tạo hai danh tính ngoài ý muốn |
| Transaction thắng giành record nhưng rollback ở bước áp dụng | Không để tác động nội bộ hoặc claim đã commit một nửa |
| Request còn lại đang chờ khi transaction trước rollback | Có thể tiếp tục theo cơ chế database mà vẫn chỉ có kết quả hợp lệ |
| Conflict xảy ra rồi application cố đọc record cũ | Dùng transaction còn hợp lệ hoặc đường rollback/savepoint đúng |
| Hai campaign hợp lệ cùng áp dụng vào một order | Tổng giảm giá và state machine vẫn đúng, dù uniqueness riêng đều thỏa |
| Tạo hai membership PENDING đồng thời | Partial unique theo trạng thái chiếm suất chặn đúng |
| Record đang UNKNOWN hoặc CANCEL_PENDING | Không mở suất mới trước khi có kết quả chắc chắn theo chính sách |
| Nhiều record lịch sử không còn chiếm suất | Được phép nếu mô hình trạng thái quy định như vậy |
| Xóa mềm redemption rồi thử dùng lại | Không vô tình cấp lại nếu chính sách một lần trọn campaign |
| Cùng business key được gửi đến hai shard hoặc region | Nơi có thẩm quyền chung ngăn hai tác động nếu cam kết toàn hệ thống |
| Worker giao lại cùng command downstream | Không tạo thêm tác động bên ngoài |
| Dọn hoặc archive record cũ rồi thử nhận lại | Invariant vẫn giữ theo retention và dấu vết đã thiết kế |

Để kiểm tra cạnh tranh, dùng connection độc lập và điểm đồng bộ để các transaction cùng tới bước INSERT. Gửi lần lượt nhiều request không chứng minh hệ thống chịu được race condition.

Cần quan sát số record đã commit, số lần giảm giá, số command downstream và kết quả cuối của tài nguyên. Một unique violation xuất hiện trong log không chứng minh tác động trùng chưa xảy ra trước đó.

## 15. Quan sát vận hành và các điểm cần nhớ

Những tín hiệu đáng theo dõi:

- Số conflict theo constraint nghiệp vụ và loại thao tác.
- Tỷ lệ gửi lại cùng command so với xung đột command khác trên cùng business key.
- Sự gia tăng conflict sau thay đổi client, import hoặc triển khai mới.
- Thời gian chờ khi nhiều transaction tranh chấp cùng identity.
- Lỗi constraint ngoài dự kiến, transaction bị lỗi rồi tiếp tục dùng sai và các lần đối soát tác động ngoài.
- Các thay đổi schema, vòng đời dữ liệu hoặc routing có thể làm mất phạm vi uniqueness.

Không đặt từng customer, order hay business key thành metric label không giới hạn. Log nên dùng tham chiếu nội bộ tối thiểu và quyền truy cập phù hợp; tránh ghi payload hoặc thông báo database chứa dữ liệu nhạy cảm ra kênh không được phép.

Trước khi chốt một unique business constraint, cần trả lời được:

```text
Điều chỉ được phép tồn tại một lần là gì?
Phạm vi tenant, chủ thể, tài nguyên và vòng đời nào áp dụng?
Những cột nào thực sự tạo business identity?
NULL và quy tắc so sánh có mở khoảng trống không?
Mọi đường ghi có đi qua cùng hàng rào không?
Conflict là retry của command cũ hay một ý định mới bị từ chối?
Record và tác động nội bộ có cùng transaction không?
Tác động ngoài, xóa dữ liệu và phân tán qua shard được bảo vệ thế nào?
```

Nguyên tắc cốt lõi: **định danh kỹ thuật duy nhất không đồng nghĩa với hành vi nghiệp vụ chỉ xảy ra một lần**. Hãy ràng buộc đúng business identity ở database, giữ transaction nhất quán và kiểm tra quyền cùng các invariant còn lại để thao tác trùng bị chặn tại nơi có thẩm quyền, kể cả khi caller đổi request key hoặc cố tạo cạnh tranh.
