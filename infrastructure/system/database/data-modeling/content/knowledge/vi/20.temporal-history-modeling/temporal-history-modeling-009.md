# Xóa mềm, trạng thái ngừng hiệu lực và chính sách lưu lịch sử

## 1. Vấn đề: “không còn dùng” không đồng nghĩa “không còn tồn tại”

Trong một hệ thống thuê thiết bị, người vận hành có thể nói “xóa khách hàng cũ”, “đóng hợp đồng”, “ngừng hiệu lực mức giá” hoặc “hủy dữ liệu sau thời hạn lưu”. Bốn câu nói đều liên quan đến vòng đời dữ liệu, nhưng **không thể quy về một lệnh `DELETE` hoặc một cột `is_deleted`**.

Ví dụ, khách hàng có tài khoản `CUS-108`, từng ký hợp đồng `RENT-204`, thanh toán tiền cọc và đã hoàn tất trả thiết bị. Sau đó khách yêu cầu ngừng sử dụng tài khoản:

- **Tài khoản có thể ngừng hoạt động** và không đăng nhập được nữa.
- **Hợp đồng đã kết thúc hiệu lực** nhưng vẫn là chứng cứ về nghĩa vụ từng phát sinh.
- **Hồ sơ tài khoản có thể được xóa mềm** để không xuất hiện trên giao diện thường ngày.
- **Dữ liệu liên quan có thời hạn lưu và căn cứ giữ khác nhau**, nên không thể mặc định xóa mọi bản ghi ngay lập tức.
- **Khi đủ điều kiện**, một số dữ liệu cần bị xóa vật lý, ẩn danh hoặc chuyển lưu trữ theo chính sách được phê duyệt; xóa mềm không hoàn thành những tác vụ đó.

Trong thiết kế cơ sở dữ liệu, cần tách **trạng thái nghiệp vụ**, **thời gian có hiệu lực**, **khả năng hiển thị**, **lịch sử thay đổi** và **vòng đời lưu trữ**. Tách đúng giúp khóa và ràng buộc giữ được tính nhất quán, truy vấn thời gian chính xác, người dùng không thấy dữ liệu đáng lẽ đã ẩn, còn công tác kiểm toán và xử lý dữ liệu cá nhân có căn cứ rõ ràng.

## 2. Bản đồ khái niệm: sáu việc khác nhau

| Khái niệm | Câu hỏi trả lời | Hành động dữ liệu điển hình | Có xóa bản ghi vật lý ngay? |
| --- | --- | --- | --- |
| **Vô hiệu hóa (disable/suspend)** | Đối tượng có được phép thực hiện hành động nữa không? | Đổi `account_status` sang `DISABLED`, lưu lý do. | Không. |
| **Ngừng hiệu lực nghiệp vụ (expire/end)** | Quyền/hợp đồng/giá trị còn áp dụng tại thời điểm T không? | Chốt `valid_to` hoặc `effective_to`, chuyển trạng thái `ENDED`. | Không. |
| **Xóa mềm (soft delete)** | Bản ghi có còn xuất hiện trong phạm vi hoạt động bình thường không? | Điền `deleted_at` và metadata xóa. | Không. |
| **Lưu trữ lạnh (archive)** | Có thể chuyển bản ghi khỏi đường đọc nóng mà vẫn giữ theo chính sách? | Đưa dữ liệu sang kho lưu trữ với metadata, kiểm soát truy xuất. | Có thể chuyển/xóa bản nóng sau xác minh, nhưng dữ liệu vẫn còn ở kho lưu trữ. |
| **Xóa vật lý/ẩn danh (purge/erase/anonymize)** | Khi nào và làm sao chấm dứt việc giữ dữ liệu định danh? | Xóa bản ghi, tệp, bản dẫn xuất hoặc biến đổi dữ liệu có kiểm soát. | Tùy cơ chế; phải phân biệt xóa với ẩn danh thực sự. |
| **Lưu lịch sử (history/temporal record)** | Trước đây đối tượng mang giá trị gì, khi nào và hệ thống biết từ lúc nào? | Bảng phiên bản theo thời gian, audit trail, event hoặc temporal model. | Không mặc định; lịch sử cũng chịu retention. |

`is_deleted = true` không cho biết bản ghi bị ẩn lúc nào, vì sao và khi nào phải purge. Một cột `status = INACTIVE` cũng không cho biết khoảng thời gian hợp đồng thực sự có hiệu lực. Ngược lại, `valid_to < now()` không chứng minh người dùng từng yêu cầu xóa hồ sơ khỏi hệ thống.

**Câu hỏi thiết kế nên được đặt riêng:**

1. **Ngừng hiệu lực:** sau ngày X, đối tượng còn tạo nghĩa vụ mới không?
2. **Ẩn khỏi nghiệp vụ thường ngày:** ai có thể đọc, sửa hoặc khôi phục đối tượng?
3. **Giữ lại lịch sử:** giữ dữ liệu gì để chứng minh quyết định nào?
4. **Kết thúc lưu giữ:** lúc nào và dưới điều kiện nào dữ liệu được xóa/ẩn danh?
5. **Khôi phục sau lỗi hoặc yêu cầu hoàn tác:** được phép khôi phục nội dung nào và trong khoảng thời gian nào?

## 3. Mô hình trạng thái theo các chiều độc lập

Một thiết kế thường dễ hiểu hơn khi không dùng một enum duy nhất để gói mọi trạng thái.

Ví dụ một tài khoản khách hàng có thể có:

- `account_status`: `ACTIVE`, `SUSPENDED` hoặc `CLOSED` — khả năng sử dụng tài khoản theo nghiệp vụ.
- `deleted_at`: thời điểm tài khoản được đánh dấu xóa mềm để ẩn khỏi luồng bình thường.
- `retention_review_at` hoặc chính sách lưu tương ứng: mốc cần đánh giá xóa/giữ.
- `legal_hold` hoặc một bản ghi hold độc lập: dữ liệu đang bị ngăn purge theo quy trình có thẩm quyền hay không.

Một hợp đồng thuê có các chiều khác:

- `rental_status`: `DRAFT`, `ACTIVE`, `RETURNED`, `ENDED`, `CANCELLED`.
- `effective_from` và `effective_to`: khoảng hợp đồng có hiệu lực.
- `archived_at`: mốc chuyển khỏi đường xử lý nóng nếu được lưu trữ.
- Lịch sử điều chỉnh điều khoản: nhiều phiên bản giá/hạn trả có các khoảng hiệu lực riêng.

Một tình huống hợp lệ là **hợp đồng `ENDED`, khách hàng `ACTIVE`, hợp đồng đã `archived_at`, nhưng chưa được phép purge vì vẫn nằm trong thời hạn giữ chứng từ**. Đặt tất cả vào một cột `status` sẽ khiến nhiều trường hợp khó hoặc không thể biểu diễn.

### Trạng thái chuyển tiếp cần chính sách

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Suspended: Tạm khóa
    Suspended --> Active: Khôi phục quyền
    Active --> Closed: Đóng tài khoản
    Suspended --> Closed: Đóng tài khoản
    Closed --> SoftDeleted: Xóa mềm hợp lệ
    SoftDeleted --> Closed: Khôi phục nếu được phép
    SoftDeleted --> Purged: Đủ điều kiện purge
    Purged --> [*]
~~~

Sơ đồ là **một ví dụ**, không phải quy trình bắt buộc cho mọi hệ thống. Không nên cho phép `Purged -> Active` như một thao tác thông thường: dữ liệu đã xóa vật lý không thể được “bật lại” từ chính bản ghi đó. Nếu có bản sao lưu hợp lệ hoặc tái đăng ký, đó là một quy trình có kiểm soát với định danh và nghĩa vụ riêng.

### Invariant nên viết rõ

- Tài khoản có `deleted_at IS NOT NULL` không được dùng để đăng nhập thông thường.
- Hợp đồng đã `ENDED` không tự phát sinh phí thuê mới, trừ quy tắc hậu kỳ được định nghĩa riêng.
- Một mức giá có hiệu lực tại thời điểm T phải được chọn từ **một** phiên bản điều khoản hợp lệ trong phạm vi ràng buộc.
- Chưa hết thời hạn giữ hoặc đang có hold hợp lệ thì purge phải bị chặn.
- Xóa mềm tài khoản **không tự làm mất** các bản ghi tài chính phải giữ và không được phá khóa tham chiếu.

## 4. Thiết kế xóa mềm: cột thời điểm, khóa và hành vi truy vấn

Mô hình đơn giản nhất là bổ sung `deleted_at TIMESTAMPTZ NULL`. `NULL` nghĩa là chưa bị xóa mềm; giá trị thời gian ghi nhận lúc bị ẩn.

Một schema minh họa bằng PostgreSQL:

~~~sql
CREATE TABLE customer_account (
    tenant_id       UUID NOT NULL,
    account_id      UUID NOT NULL,
    login_email     TEXT NOT NULL,
    account_status  VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    deleted_at      TIMESTAMPTZ,
    deletion_reason VARCHAR(80),
    deleted_by      UUID,
    version         BIGINT NOT NULL DEFAULT 0
                    CHECK (version >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, account_id),
    CHECK (
        account_status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')
    ),
    CHECK (
        deleted_at IS NOT NULL OR
        (deletion_reason IS NULL AND deleted_by IS NULL)
    )
);
~~~

Đây là schema dạy học: hệ thống thực tế cần quản lý chuẩn hóa email, quyền actor, phạm vi tenant, loại dữ liệu cá nhân và yêu cầu xác minh tài khoản. Không coi `deleted_by` luôn là người dùng: tác nhân có thể là tác vụ tự động hoặc quy trình quản trị, khi đó cần một định danh tác nhân và kiểu actor phù hợp.

### Khóa định danh không được tái sử dụng

`account_id` là định danh bền vững. Khi một tài khoản bị xóa mềm, không nên tái sử dụng ID đó cho người khác: hợp đồng, giao dịch và audit cũ vẫn có thể trỏ đến cùng ID. Với hệ đa tenant, khóa `(tenant_id, account_id)` giữ ranh giới rõ ràng.

### Khóa duy nhất cho bản ghi đang còn “sống”

Giả sử mỗi tenant chỉ cho phép **một tài khoản chưa xóa mềm** dùng cùng email đã được chuẩn hóa:

~~~sql
CREATE UNIQUE INDEX ux_customer_live_email
    ON customer_account (tenant_id, lower(login_email))
    WHERE deleted_at IS NULL;
~~~

Chỉ mục một phần này cho phép một email xuất hiện ở một bản ghi đã xóa mềm và một bản ghi hoạt động khác. Đây chỉ là **một chính sách sản phẩm**:

- Nếu email vẫn phải dành riêng trong thời gian chờ khôi phục, điều kiện unique có thể cần chặt hơn hoặc dùng bảng giữ chỗ tên đăng nhập.
- Nếu tài khoản cũ được khôi phục sau khi người khác đã đăng ký email đó, thao tác khôi phục phải **bị chặn hoặc trải qua xử lý xung đột**; không tự chiếm email của tài khoản mới.
- Nếu cần unique trên email được chuẩn hóa ở cấp toàn hệ thống thay vì tenant, thay đổi khóa tương ứng; cần thống nhất chính sách chuẩn hóa và so sánh Unicode/email.
- Một unique index trên `lower(login_email)` không tự xử lý mọi quy tắc canonicalization của email. Nên có hàm/chiến lược chuẩn hóa được quy định nhất quán khi ghi và tra cứu.

### Truy vấn mặc định phải có bộ lọc

~~~sql
SELECT account_id, login_email, account_status
FROM customer_account
WHERE tenant_id = :tenant_id
  AND deleted_at IS NULL
  AND account_status = 'ACTIVE';
~~~

Cần bảo đảm các code path như API list, tìm kiếm, autocomplete, export, báo cáo, job nền và JOIN cũng áp dụng chính sách hiển thị. **Một bản ghi đã xóa mềm vẫn tồn tại trong database và có thể bị lộ** qua truy vấn bỏ quên điều kiện.

Có thể tạo view dành cho nghiệp vụ:

~~~sql
CREATE VIEW customer_account_live AS
SELECT tenant_id, account_id, login_email, account_status,
       version, created_at, updated_at
FROM customer_account
WHERE deleted_at IS NULL;
~~~

View giúp chuẩn hóa đường đọc nhưng **không tự là ranh giới bảo mật** nếu tài khoản ứng dụng vẫn có quyền đọc trực tiếp bảng gốc. Muốn hạn chế truy cập thực sự, phối hợp quyền DB, API, chính sách row-level security nếu phù hợp và kiểm thử quyền truy cập theo tenant.

## 5. Xóa mềm trong transaction, chống gửi lặp và phục hồi

Xóa mềm không chỉ là `UPDATE deleted_at = now()`. Trước khi ẩn dữ liệu, hệ thống cần kiểm tra quyền, trạng thái, nghĩa vụ và cách phát thông báo tới hệ thống phụ thuộc.

Ví dụ cập nhật có kiểm tra phiên bản:

~~~sql
UPDATE customer_account
SET account_status = 'CLOSED',
    deleted_at = now(),
    deletion_reason = :reason_code,
    deleted_by = :actor_id,
    version = version + 1,
    updated_at = now()
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND deleted_at IS NULL
  AND version = :expected_version
RETURNING account_id, version, deleted_at;
~~~

Nếu không có dòng trả về, có thể tài khoản đã bị xóa mềm, version đã đổi hoặc tài khoản không tồn tại trong tenant này. **Không mặc nhiên coi mọi trường hợp là thành công**: dùng định danh lệnh hoặc `idempotency_key` để phân biệt retry của yêu cầu đã hoàn tất với yêu cầu khác cạnh tranh.

Một quy trình đầy đủ nên:

1. Xác minh actor và căn cứ; nếu có dữ liệu tài chính/hợp đồng liên quan, quyết định thông tin nào chỉ **ẩn**, thông tin nào phải **giữ**.
2. Khóa/cập nhật có điều kiện theo version; ghi audit/correction nếu yêu cầu.
3. Trong cùng transaction, lưu **outbox** nếu cần thông báo downstream về thay đổi quyền hiển thị hoặc trạng thái tài khoản.
4. Commit; chỉ sau đó relay mới phát thông điệp. Consumer phải xử lý retry idempotent.
5. Lên lịch đánh giá retention/purge riêng, không nhầm xóa mềm với erasure hoàn tất.

**Khôi phục** (restore) cần kiểm tra: còn trong cửa sổ được phép khôi phục không, trạng thái nghiệp vụ nào được đặt lại, khóa unique có xung đột không, tài khoản có cần xác minh lại thông tin liên hệ không, và có dữ liệu đã bị xóa vật lý không còn khôi phục được hay không.

~~~sql
UPDATE customer_account
SET deleted_at = NULL,
    deletion_reason = NULL,
    deleted_by = NULL,
    account_status = 'SUSPENDED',
    version = version + 1,
    updated_at = now()
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND deleted_at IS NOT NULL
  AND version = :expected_version
RETURNING account_id, version;
~~~

Ví dụ khôi phục đặt `SUSPENDED` để yêu cầu xác minh trước khi cấp quyền. Nếu unique index của email bị xung đột, transaction sẽ thất bại; ứng dụng phải giải quyết chính sách tài khoản trùng thay vì bỏ ràng buộc.

## 6. Ngừng hiệu lực theo khoảng thời gian: khác với xóa mềm

Đối với mức giá, hợp đồng, quyền truy cập hoặc điều khoản, câu hỏi thường là:

> Bản ghi nào **có hiệu lực tại thời điểm T**?

Đây là **valid time** (thời gian hiệu lực nghiệp vụ), khác với việc bản ghi có đang hiển thị hay chưa. Có thể biểu diễn khoảng hiệu lực dạng **nửa mở** `[valid_from, valid_to)`: gồm điểm bắt đầu, không gồm điểm kết thúc.

Ví dụ lịch sử giá thuê cùng thiết bị:

| Phiên bản | valid_from | valid_to | Đơn giá/ngày |
| --- | --- | --- | ---: |
| P1 | 2026-01-01 00:00 UTC | 2026-04-01 00:00 UTC | 70.000 VND |
| P2 | 2026-04-01 00:00 UTC | 2026-09-01 00:00 UTC | 80.000 VND |
| P3 | 2026-09-01 00:00 UTC | Không giới hạn | 85.000 VND |

Ở đúng mốc `2026-04-01 00:00 UTC`, P2 có hiệu lực và P1 không còn. Cách đặt khoảng `[)` tránh việc hai phiên bản cùng hợp lệ tại đúng ranh giới.

### Mô hình bảng phiên bản

~~~sql
CREATE TABLE rental_agreement (
    tenant_id       UUID NOT NULL,
    agreement_id    UUID NOT NULL,
    account_id      UUID NOT NULL,
    agreement_status VARCHAR(20) NOT NULL,
    effective_from  TIMESTAMPTZ NOT NULL,
    effective_to    TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    version         BIGINT NOT NULL DEFAULT 0
                    CHECK (version >= 0),
    PRIMARY KEY (tenant_id, agreement_id),
    FOREIGN KEY (tenant_id, account_id)
        REFERENCES customer_account (tenant_id, account_id),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK (agreement_status IN
           ('DRAFT', 'ACTIVE', 'RETURNED', 'ENDED', 'CANCELLED'))
);

CREATE INDEX ix_rental_active_by_tenant
    ON rental_agreement
       (tenant_id, agreement_status, effective_from)
    WHERE deleted_at IS NULL;
~~~

`effective_to` ở đây biểu diễn kết thúc hiệu lực của **hợp đồng**; nó không nói hợp đồng đã được phép purge. `archived_at` cũng không nói dữ liệu đã bị xóa. Tùy nghiệp vụ, hợp đồng có thể hết hạn theo thời gian dù `agreement_status` chưa được job chuyển thành `ENDED`; cần quy định **nguồn xác định hiệu lực** là khoảng thời gian, trạng thái được tính, hay cả hai trong những điều kiện khác nhau.

Truy vấn hợp đồng có hiệu lực tại `:as_of`:

~~~sql
SELECT tenant_id, agreement_id, account_id, agreement_status
FROM rental_agreement
WHERE tenant_id = :tenant_id
  AND effective_from <= :as_of
  AND (effective_to IS NULL OR :as_of < effective_to)
  AND deleted_at IS NULL;
~~~

Đây là truy vấn cho **góc nhìn hiện hành về dữ liệu đang được phép hiển thị** và khoảng hiệu lực. Nếu muốn tra cứu hợp đồng đã bị xóa mềm trong phạm vi điều tra được cấp quyền, điều kiện `deleted_at IS NULL` cần được thay bằng chính sách truy cập lịch sử riêng. Đừng gọi việc bỏ điều kiện soft-delete trong mọi truy vấn “as-of” là luôn đúng hoặc luôn sai: phải định nghĩa mục đích đọc.

### Giữ nhiều phiên bản điều khoản, tránh ghi đè lịch sử

Khi giá thay đổi, nếu chỉ `UPDATE current_price` thì không thể biết giá có hiệu lực ở ngày ký trước đây. Một bảng phiên bản điều khoản giữ được các khoảng hiệu lực:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE rental_term_version (
    tenant_id        UUID NOT NULL,
    agreement_id     UUID NOT NULL,
    term_version_id  UUID NOT NULL,
    valid_from       TIMESTAMPTZ NOT NULL,
    valid_to         TIMESTAMPTZ,
    daily_fee_minor  BIGINT NOT NULL CHECK (daily_fee_minor >= 0),
    currency         CHAR(3) NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    voided_at        TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, term_version_id),
    FOREIGN KEY (tenant_id, agreement_id)
        REFERENCES rental_agreement (tenant_id, agreement_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    EXCLUDE USING gist (
        tenant_id WITH =,
        agreement_id WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    ) WHERE (voided_at IS NULL)
);
~~~

Ràng buộc loại trừ `EXCLUDE ... WITH &&` ngăn hai phiên bản **chưa bị void** của cùng hợp đồng có khoảng hiệu lực chồng nhau. `btree_gist` cung cấp khả năng dùng phép so sánh bằng của khóa thông thường trong chỉ mục GiST; việc bật extension cần quyền và cấu hình DB phù hợp.

**Giới hạn quan trọng:** `voided_at` là một kỹ thuật loại phiên bản khỏi tập đang có thẩm quyền; bản thân việc cập nhật nó làm thay đổi thông tin hiện tại. Nếu yêu cầu trả lời chính xác “hệ thống biết phiên bản nào vào ngày X”, cần **recorded-time history** hoặc mô hình bitemporal có kiểm soát, không chỉ dựa vào bảng này rồi giả định mọi thay đổi đều bất biến.

## 7. Thời gian hiệu lực, thời gian ghi nhận và truy vấn lịch sử

Có hai trục thời gian thường gặp:

- **Valid time:** dữ liệu được công nhận có hiệu lực trong thế giới nghiệp vụ vào khoảng nào?
- **Transaction/system time:** hệ thống đã lưu/biết phiên bản đó trong khoảng nào?

Giả sử điều khoản hợp đồng từng được ghi là hạn trả 10:00. Đến 12:00, nhân viên cung cấp chứng từ rằng gia hạn đến 11:00 đã được duyệt từ hôm trước. Hệ thống có thể cần trả lời:

1. **Lúc 11:30, hệ thống đang tin điều gì?** Giá trị đang ghi khi ấy là hạn 10:00.
2. **Theo chứng cứ mới, hạn hợp lệ tại 11:30 là gì?** Giá trị được công nhận là 11:00.

Hai câu hỏi không mâu thuẫn; chúng hỏi về hai chiều thời gian khác nhau.

Một mô hình bitemporal có thể giữ `valid_from/valid_to` và `recorded_from/recorded_to` (hoặc metadata tương đương). Khi có correction, nó **đóng khoảng ghi nhận cũ và tạo phiên bản mới**, không giả vờ rằng hệ thống đã luôn biết giá trị mới. Truy vấn thời gian cần lấy đúng cả hai trục và xử lý khoảng nửa mở:

~~~sql
-- Mã giả SQL cho bảng temporal_version có bốn mốc thời gian.
SELECT *
FROM temporal_version
WHERE entity_id = :entity_id
  AND valid_from <= :business_at
  AND (valid_to IS NULL OR :business_at < valid_to)
  AND recorded_from <= :known_at
  AND (recorded_to IS NULL OR :known_at < recorded_to);
~~~

Đây là ví dụ mô hình **nếu có bảng temporal_version được thiết kế riêng**, không phải truy vấn trực tiếp vào các bảng đã khai báo ở phần trước. Để dữ liệu bitemporal đúng, hệ thống phải kiểm soát ranh giới phiên bản, transaction ghi và các ràng buộc không chồng khoảng theo cả ngữ nghĩa valid-time và recorded-time.

**Không dùng `updated_at` một mình để mô phỏng lịch sử.** Mốc cập nhật cuối không nói trạng thái trước đó là gì; `deleted_at` cũng không chứng minh dữ kiện nghiệp vụ từng có hiệu lực hoặc bị hủy vào thời điểm nào.

### Múi giờ và ranh giới thời gian

Lưu mốc sự kiện bằng `TIMESTAMPTZ` (thời điểm tuyệt đối) khi cần; xác định múi giờ nghiệp vụ khi hiển thị hoặc tính ngày. Không mặc định “ngày 01/04” luôn tương đương cùng một giờ UTC cho mọi tenant. Đối với kỳ hạn được diễn đạt theo ngày địa phương, cần lưu rõ chính sách múi giờ/lịch và cách giải quyết ngày chuyển giờ mùa hè nếu áp dụng.

Một bản ghi hết hiệu lực khi `valid_to <= :as_of` theo quy tắc `[)`. Điều này khác với job định kỳ cập nhật `status = 'EXPIRED'`: job có thể chạy muộn; truy vấn quy tắc thời gian không nên phụ thuộc hoàn toàn vào thời điểm job chạy nếu nghiệp vụ yêu cầu đúng tuyệt đối theo giờ.

## 8. Chính sách lưu lịch sử: mỗi nhóm dữ liệu có căn cứ và đồng hồ riêng

**Retention policy** là quyết định **dữ liệu nào phải/được giữ, trong bao lâu, tính từ mốc nào, ai phê duyệt và làm gì khi hết hạn**. Không nên áp dụng một con số chung cho mọi bảng chỉ vì chúng liên quan cùng khách hàng.

Một phiếu chính sách cần có ít nhất:

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Data category** | Dữ liệu thuộc nhóm nào: hồ sơ tài khoản, hợp đồng, giao dịch, audit, log truy cập, tệp đính kèm? |
| **Purpose/legal basis** | Vì sao cần lưu và có căn cứ cho thời hạn đó không? |
| **Trigger** | Bắt đầu tính thời hạn từ khi tạo bản ghi, đóng hợp đồng, hoàn tất thanh toán, chấm dứt dịch vụ hay sự kiện khác? |
| **Retention rule** | Thời hạn bắt buộc/tối đa, các ngoại lệ và cách tính ngày/giờ theo quy định áp dụng. |
| **Action at expiry** | Purge, ẩn danh, tổng hợp số liệu, archive hoặc đánh giá thủ công? |
| **Hold/exception** | Khi nào được tạm dừng purge và ai chịu trách nhiệm xem xét lại? |
| **Coverage** | CSDL chính, bản dẫn xuất, file đính kèm, search index, cache, audit, backup, đối tác? |
| **Evidence** | Cần giữ bằng chứng tối thiểu nào để chứng minh việc thực thi chính sách? |
| **Policy version** | Phiên bản quyết định đã áp dụng tại thời điểm tính hạn và lý do thay đổi. |

Ví dụ phân loại (thời hạn là **tham số phải lấy từ chính sách thực tế**, không phải thời hạn pháp luật mặc định):

| Nhóm dữ liệu | Mốc bắt đầu có thể áp dụng | Hành động khi đủ điều kiện |
| --- | --- | --- |
| Hồ sơ tài khoản không còn cần thiết | Yêu cầu đóng/xóa đã được xác minh và các nghĩa vụ liên quan được phân loại. | Xóa/ẩn danh thuộc tính cá nhân được phép xử lý. |
| Hợp đồng thuê và chứng từ | Ngày kết thúc hợp đồng hoặc kết thúc tranh chấp theo quy tắc áp dụng. | Archive/purge theo chính sách chứng từ đã duyệt. |
| Giao dịch thanh toán/sổ cái | Ngày giao dịch được quyết toán hoặc mốc theo nghĩa vụ lưu tương ứng. | Giữ hoặc xử lý theo thời hạn riêng; không tùy tiện xóa theo tài khoản. |
| Nhật ký truy cập kỹ thuật | Thời điểm ghi log. | Xóa theo chu kỳ sau khi xét yêu cầu bảo mật/điều tra. |
| Read model và search index | Phụ thuộc mục đích và nguồn dữ liệu. | Đồng bộ ẩn/xóa, xây lại có kiểm soát. |
| Backup/snapshot hệ thống | Thời điểm sao lưu và chính sách backup. | Hết vòng quay lưu trữ; xử lý phục hồi từ backup cũ để không tái lộ dữ liệu. |

**Không tự chọn “7 năm”, “90 ngày” hay mốc khác rồi coi là nghĩa vụ pháp lý.** Các mốc đó phụ thuộc loại dữ liệu, khu vực, hợp đồng, quyền người dùng và chính sách tổ chức. Khi áp dụng thực tế, cần người có thẩm quyền về pháp lý/chính sách xác nhận.

### Mốc hết hạn và thời điểm thực thi là hai giá trị khác nhau

- `retention_until`: **mốc sớm nhất hoặc mốc phải đánh giá** hành động cuối vòng đời theo chính sách; cần mô tả chính xác ý nghĩa.
- `purge_scheduled_at`: thời điểm job được lên lịch.
- `purged_at`: thời điểm một tác vụ xác nhận xử lý xong trong phạm vi dữ liệu đã định nghĩa.
- `hold_until` hoặc trạng thái hold: ngoại lệ có căn cứ; có thể chưa xác định ngày kết thúc và cần rà soát định kỳ.

Không dùng một cột `deleted_at` cho cả bốn ý nghĩa. Nếu dữ liệu đã bị xóa vật lý, không thể cập nhật `purged_at` **trên chính hàng đã xóa**; cần hồ sơ tác vụ hoặc tombstone tối thiểu ở nơi riêng, theo chính sách.

## 9. Thiết kế tác vụ purge: quyết định, thực thi và chứng cứ

Một quy trình purge có trách nhiệm không chỉ chạy:

~~~sql
DELETE FROM customer_account
WHERE deleted_at IS NOT NULL;
~~~

Lệnh đó bỏ qua retention, hợp đồng chưa kết thúc, dữ liệu downstream, legal hold và quyền hạn. Thay vào đó, có thể quản lý tác vụ xóa/ẩn danh bằng bảng điều phối riêng:

~~~sql
CREATE TABLE data_retention_action (
    action_id          UUID PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    subject_ref        VARCHAR(120) NOT NULL,
    data_category      VARCHAR(80) NOT NULL,
    policy_version     VARCHAR(60) NOT NULL,
    eligible_at        TIMESTAMPTZ NOT NULL,
    action_type        VARCHAR(24) NOT NULL
                       CHECK (action_type IN ('ERASE', 'ANONYMIZE', 'ARCHIVE')),
    action_status      VARCHAR(24) NOT NULL
                       CHECK (action_status IN
                          ('PENDING', 'BLOCKED', 'RUNNING',
                           'COMPLETED', 'FAILED')),
    completed_at       TIMESTAMPTZ,
    last_error_code    VARCHAR(80),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_retention_due
    ON data_retention_action (eligible_at, action_id)
    WHERE action_status IN ('PENDING', 'FAILED');
~~~

Đây là **metadata điều phối**; `subject_ref` cần là tham chiếu tối thiểu theo đúng quyền truy cập và chính sách giữ chứng cứ, không phải nơi sao chép toàn bộ dữ liệu cá nhân. Trạng thái `COMPLETED` phải có định nghĩa phạm vi: hoàn tất ở DB nguồn, cả bản dẫn xuất hay bao gồm xác nhận từ đối tác? Nếu một số bước còn chờ, không nên tuyên bố xóa toàn bộ đã hoàn tất.

### Một quy trình purge an toàn

~~~mermaid
flowchart TD
    A["Đối tượng được xóa mềm/đóng"] --> B["Tính điều kiện theo policy version"]
    B --> C{"Đủ thời hạn và không bị hold?"}
    C -->|"Chưa"| D["Giữ, rà soát lại vào mốc tiếp theo"]
    C -->|"Có"| E["Khóa/đối chiếu dữ liệu và nghĩa vụ"]
    E --> F["Xóa/ẩn danh tại nguồn theo phạm vi"]
    F --> G["Thông báo xử lý read model, search, file, cache"]
    G --> H{"Các bước đã được xác nhận?"}
    H -->|"Không"| I["Retry/đối soát, giữ trạng thái chưa hoàn tất"]
    H -->|"Có"| J["Ghi chứng cứ tối thiểu và đóng tác vụ"]
~~~

Các bước cần thực hiện **idempotent**, vì job có thể retry sau timeout. Xóa vật lý không thể luôn nằm trong một transaction trải qua database, object storage, search index và bên thứ ba. Hãy có trạng thái từng bước, cơ chế kiểm tra lại, giới hạn quyền và đối soát, thay vì coi một lệnh SQL thành công là tất cả nơi lưu dữ liệu đã sạch.

**Hold phải được kiểm tra ngay trước thao tác không thể đảo ngược**, không chỉ lúc job lần đầu lên lịch. Nếu hold mới được áp sau khi tác vụ được đưa vào hàng đợi, worker phải tôn trọng trạng thái mới. Quy tắc khóa hoặc kiểm tra phiên bản chính sách giúp hạn chế cuộc đua giữa “thêm hold” và “purge”.

### Bằng chứng không nên trở thành bản sao dữ liệu đã xóa

Hồ sơ hoàn tất có thể ghi mã tác vụ, thời điểm, policy version, phạm vi hệ thống, kết quả và mã lỗi. Không nên lưu lại email, số giấy tờ hoặc nội dung dữ liệu đã bị xóa trong log chứng minh xóa. Kể cả hash hoặc identifier vẫn có thể nhận diện được khi kết hợp dữ liệu khác; phải đánh giá tính cần thiết và chính sách giữ riêng cho hồ sơ này.

## 10. Khóa ngoại, quan hệ phụ thuộc và “xóa dây chuyền”

Một lỗi thường gặp là bật `ON DELETE CASCADE` rồi dùng xóa vật lý tài khoản để xóa luôn hợp đồng, hóa đơn và lịch sử thanh toán. Điều này có thể phá chứng từ, quan hệ kế toán hoặc khả năng đối soát.

### Soft delete không kích hoạt FK cascade

Khi chỉ cập nhật `deleted_at`, hàng vẫn tồn tại nên foreign key không làm gì. Vì vậy:

- Bản ghi hợp đồng còn trỏ tới khách hàng hợp lệ ở mức khóa.
- Không được mặc định hợp đồng cũng bị ẩn trên giao diện người dùng; chính sách hiển thị phải được áp dụng ở truy vấn/domain.
- Việc giữ hợp đồng không đồng nghĩa được phép tiếp tục giữ mọi thuộc tính cá nhân của hồ sơ.
- Khi thực sự purge hàng tài khoản, các FK từ hợp đồng sẽ **ngăn DELETE** nếu không có thiết kế tiếp tục tham chiếu hoặc xử lý mối quan hệ đúng chính sách.

### Ba chiến lược cho dữ liệu phụ thuộc

| Chiến lược | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| **Giữ surrogate ID, ẩn danh thuộc tính** | Cần lưu giao dịch/hợp đồng nhưng không còn cần danh tính đầy đủ. | Phải đánh giá khả năng tái định danh qua các bảng khác và chính sách cho phép. |
| **Tách identity vault và business record** | Danh tính có vòng đời khác nghĩa vụ. | Khóa tham chiếu và quyền truy cập cần được phân tách; có quy trình xóa identity. |
| **Xóa có kiểm soát cả đồ thị phụ thuộc** | Toàn bộ nhóm bản ghi được phép và cần xóa. | Xác định thứ tự, transaction cục bộ, xử lý file/search/backup và audit chứng cứ. |

`SET NULL` ở foreign key chỉ thích hợp nếu quan hệ có thể thật sự vắng mặt mà không phá ý nghĩa dữ liệu. Không biến `account_id` của giao dịch thành NULL chỉ để làm lệnh DELETE chạy được khi nghiệp vụ cần định danh đối soát.

### Vì sao không tái sử dụng khóa?

Một account đã purge nhưng các giao dịch lịch sử chỉ giữ surrogate ID để đối chiếu **không được gán ID đó cho người mới**. Khi tái sử dụng, hợp đồng cũ có thể bị hiểu thuộc người khác. Dù dữ liệu PII được xóa, chiến lược nhận diện/tombstone tối thiểu có thể vẫn cần bảo vệ sự không trùng lặp theo chính sách.

## 11. Query, index và hiệu năng khi dữ liệu cũ ngày càng nhiều

Soft delete làm bảng có cả bản ghi hiện hành và bản ghi đã ẩn. Khi phần đã ẩn lớn, truy vấn và chỉ mục phải thiết kế đúng workload.

### Chỉ mục cho đường đọc nóng

~~~sql
CREATE INDEX ix_customer_active
    ON customer_account (tenant_id, account_status, account_id)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_customer_deleted
    ON customer_account (tenant_id, deleted_at)
    WHERE deleted_at IS NOT NULL;
~~~

Chỉ mục thứ nhất phục vụ lọc khách chưa xóa; chỉ mục thứ hai hỗ trợ tác vụ rà soát những bản ghi đã xóa mềm. Tuy nhiên, **không tự thêm mọi index** vào production: dữ liệu, selectivity, bộ lọc, kế hoạch thực thi và chi phí ghi phải được đo. Một partial index chỉ được planner dùng khi điều kiện truy vấn cho phép chứng minh tương thích với predicate chỉ mục; hãy thử với truy vấn/parameterization thực tế bằng `EXPLAIN (ANALYZE, BUFFERS)` ở môi trường phù hợp.

### Dữ liệu lịch sử nên tách thế nào?

Một số lựa chọn:

- **Cùng bảng + deleted_at:** đơn giản, hỗ trợ restore; hợp khi dung lượng và quyền truy cập còn kiểm soát tốt.
- **Bảng lịch sử riêng:** giúp giảm kích thước đường đọc nóng, nhưng tăng công việc di chuyển, quản lý khóa, schema và tra cứu xuyên bảng.
- **Partition theo thời gian:** phù hợp khi dữ liệu lớn và có truy vấn/lưu giữ theo thời gian; cần kiểm tra constraint unique/FK và cách partition pruning thực tế.
- **Kho archive/object storage:** phù hợp dữ liệu ít truy vấn, giá trị lưu giữ cao; phải kiểm chứng tính toàn vẹn, quyền truy cập, tra cứu và khả năng xóa khi hết hạn.

Chuyển dữ liệu sang archive **không xóa nghĩa vụ** quản lý retention, phân quyền và yêu cầu truy cập/xóa hợp lệ. Một bản sao search index, cache hoặc export có thể tiếp tục làm lộ dữ liệu dù hàng database đã bị ẩn.

### Mô hình document, đồ thị và phân tích

Trong document store, `deleted_at` hoặc `lifecycle_status` vẫn phải được đưa vào mọi query/index thích hợp; cơ chế TTL có thể xóa document vật lý nhưng **không thay thế đánh giá chính sách và downstream**. Trong graph, việc vô hiệu một nút phải xét các cạnh quan hệ: ẩn nút mà để các cạnh vẫn hiển thị có thể làm lộ định danh. Trong kho phân tích, cần chính sách với fact, dimension, bản snapshot và số liệu tổng hợp sau khi dữ liệu nguồn được erasure/ẩn danh.

## 12. Đồng bộ xóa mềm và ngừng hiệu lực sang các hệ thống khác

Một lệnh `UPDATE customer_account SET deleted_at = now()` chỉ làm thay đổi nguồn local. Downstream có thể tiếp tục hiển thị tài khoản trong tìm kiếm, CRM hoặc cache nếu không nhận và áp dụng sự thay đổi đúng.

Cần phân biệt thông điệp:

- **AccountDisabled:** không được phép sử dụng tài khoản nữa; dữ liệu có thể vẫn hiển thị cho người có quyền.
- **AccountSoftDeleted:** đối tượng bị ẩn khỏi phạm vi nghiệp vụ thường ngày, nhưng chưa chắc đã bị xóa vật lý.
- **AgreementExpired/AgreementEnded:** hiệu lực hợp đồng đã kết thúc theo quy tắc nghiệp vụ.
- **AccountErasureCompleted:** chỉ nên công bố nếu phạm vi “đã xóa” thực sự được xác nhận; không gửi thông điệp thành công khi còn hệ thống chưa xử lý.
- **CDC UPDATE:** bản ghi database đã thay đổi cột `deleted_at`; đó là sự kiện lưu trữ, không tự mang toàn bộ ý nghĩa quyền riêng tư/retention.

Một transactional outbox có thể ghi trong cùng transaction với thay đổi trạng thái nguồn:

~~~sql
CREATE TABLE lifecycle_outbox (
    message_id       UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    aggregate_id     UUID NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at     TIMESTAMPTZ
);
~~~

Relay có thể gửi message lặp sau retry. Consumer cần khóa dedup (ví dụ `message_id` cùng nguồn) và quy tắc về thứ tự/version để không **khôi phục bản ghi đã xóa mềm** bằng một thông điệp trạng thái cũ đến muộn. Với việc erasure xuyên nhiều hệ thống, còn cần xác nhận bước thực thi hoặc đối soát theo phạm vi, không chỉ “đã phát message”.

**Tránh chuyển nguyên email/số điện thoại vào message “hãy xóa người này”** nếu có thể dùng opaque ID đã thống nhất và kênh tin cậy. Một thông điệp xóa lại mang theo toàn bộ PII có thể trở thành bản sao dữ liệu rất khó kiểm soát.

## 13. Quyền riêng tư, bảo mật, pháp lý và bản sao lưu

Xóa mềm **không phải xóa dữ liệu cá nhân**. Dữ liệu vẫn nằm trong hàng nguồn, bản sao lưu, log, projection, search index và có thể cả hệ thống bên ngoài. Khi xử lý yêu cầu xóa hoặc lưu giữ, phải kiểm tra phạm vi và căn cứ áp dụng với người chịu trách nhiệm chuyên môn.

### Những điểm cần xác nhận

1. **Mục đích và căn cứ giữ:** dữ liệu nào không còn cần, dữ liệu nào có nghĩa vụ giữ độc lập?
2. **Minimization:** chỉ lưu các thuộc tính cần thiết; hợp đồng/giao dịch có thể giữ surrogate ID mà không giữ email ở mọi bảng.
3. **Phân quyền:** truy cập dữ liệu đã xóa mềm chỉ cho actor có nhiệm vụ phù hợp; log truy cập cần kiểm soát riêng.
4. **Retention:** khi nào dữ liệu được chuyển archive, ẩn danh hay purge? Chạy lại điều kiện nếu chính sách thay đổi.
5. **Backup:** dữ liệu đã erasure có thể vẫn trong backup chưa hết vòng quay. Cần chính sách xử lý backup, bảo mật và quy trình **không tái kích hoạt dữ liệu đã xóa** khi restore.
6. **Dữ liệu bất biến:** append-only event, audit và WORM có thể mâu thuẫn yêu cầu xóa; cần thiết kế tách PII, quyền truy cập, retention và cơ chế xử lý ngoại lệ phù hợp.
7. **Bằng chứng thực thi:** có thể cần giữ nhật ký chứng minh công việc xóa nhưng không nên biến nó thành kho PII mới.

**Ẩn danh và bút danh hóa khác nhau:** thay tên bằng `account_id` thường chỉ là **pseudonymization**, vì còn có thể liên kết và tái nhận diện qua dữ liệu khác. Không tuyên bố dữ liệu đã “anonymous” chỉ vì đã xóa một cột email. Việc hủy khóa mã hóa đôi khi được đề xuất như giải pháp giảm khả năng truy cập, nhưng cần đánh giá sao lưu khóa, khóa chia sẻ, tính không thể khôi phục và yêu cầu pháp lý; không thể mặc định hủy khóa luôn đáp ứng mọi nghĩa vụ xóa.

### Kịch bản restore từ backup

Giả sử thứ Hai tài khoản đã được erasure theo quy trình. Thứ Tư hệ thống khôi phục backup tạo từ Chủ Nhật. Backup cũ có thể chứa dữ liệu đã xóa. Vì vậy cần một **danh sách/quy trình áp dụng lại quyết định erasure** phù hợp lên môi trường khôi phục, trong phạm vi quyền và retention của hồ sơ quyết định. Cần kiểm thử định kỳ khả năng restore mà không làm dữ liệu bị xóa xuất hiện lại trên giao diện hoặc gửi sang consumer.

## 14. Lựa chọn mô hình dữ liệu theo nhu cầu thật

Không phải mọi dữ liệu cần đủ cả soft delete, valid-time và bitemporal history. Hãy chọn mức phức tạp nhỏ nhất vẫn bảo đảm yêu cầu:

| Bài toán | Phương án khởi đầu | Khi nào cần mở rộng |
| --- | --- | --- |
| Danh mục thiết bị không còn bán | `status = INACTIVE`, lưu thời điểm và lý do. | Nếu cần xem danh mục từng có hiệu lực trong quá khứ, thêm version/valid-time. |
| Khách muốn ẩn/xóa tài khoản | Soft delete với quy trình retention/erasure. | Khi có nghĩa vụ lưu chứng từ, tách identity và business records, audit/hold. |
| Hợp đồng có ngày bắt đầu/kết thúc | `effective_from/to`, trạng thái hợp đồng. | Khi có nhiều phiên bản điều khoản, dùng bảng lịch sử khoảng hiệu lực. |
| Báo giá được sửa hồi tố | Valid-time + recorded-time (bitemporal hoặc history tương đương). | Khi cần truy vấn cả “hệ thống đã biết gì” và “giá trị có hiệu lực khi nào”. |
| Nhật ký kỹ thuật dung lượng lớn | Partition/TTL theo policy đã phê duyệt. | Khi có legal hold, truy vết yêu cầu xóa, archive hay nhiều hệ lưu. |
| Giao dịch tài chính cần đối soát | Ledger/history có nguồn rõ và retention riêng. | Khi cần nhiều projection lịch sử, correction và đối soát liên hệ nhiều dịch vụ. |

**Chọn theo bounded context**, không áp một cờ `is_deleted` lên tất cả bảng chỉ vì framework có sẵn tính năng. Ví dụ, `OrderCancelled` là sự kiện nghiệp vụ, không nhất thiết là “xóa mềm” đơn hàng. “Ngừng hiệu lực bảng giá” cũng không đồng nghĩa “xóa hóa đơn đã dùng bảng giá đó”.

### Bảng quyết định thiết kế

Trước khi triển khai, trả lời rõ:

- Đối tượng có thể *tạm dừng* rồi hoạt động lại, hay trạng thái kết thúc là vĩnh viễn?
- “Xóa” là ẩn giao diện, khóa quyền xử lý, xóa vật lý hay đáp ứng yêu cầu erasure?
- Có bao nhiêu loại lịch sử: trước/sau sửa, mốc nghiệp vụ, các khoảng hiệu lực hay cả bitemporal?
- Có cần trả lời truy vấn as-of theo múi giờ/định nghĩa nào?
- Khóa unique có được tái sử dụng sau soft delete không; restore xử lý xung đột ra sao?
- Dữ liệu phụ thuộc nào phải giữ và khóa ngoại được thiết kế thế nào?
- Ai có quyền đặt hold, và hold được kiểm tra ra sao ngay trước purge?
- Có những bản sao downstream nào cần ẩn/xóa cùng dữ liệu gốc?
- Thời hạn lưu lấy từ chính sách nào, bắt đầu từ sự kiện nào, khi đổi policy thì dữ liệu cũ xử lý ra sao?
- Kế hoạch kiểm chứng, monitoring, backup/restore và sự cố thất bại giữa các bước là gì?

## 15. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `is_deleted` đại diện cả ngừng hiệu lực, ẩn và erasure | Không phân biệt được nghĩa vụ/hành động thực tế. | Tách trạng thái nghiệp vụ, mốc hiệu lực, soft delete, retention action. |
| Cho rằng soft delete đủ đáp ứng yêu cầu xóa dữ liệu | PII vẫn nằm trong nhiều hệ. | Quy trình erasure đầy đủ, kiểm tra downstream và backup. |
| Xem `updated_at` là lịch sử | Mất giá trị cũ và lý do thay đổi. | Audit, bảng version, event hoặc bitemporal tùy yêu cầu. |
| Dùng `valid_to <= now()` làm căn cứ purge ngay | Xóa chứng từ còn nghĩa vụ lưu. | Tách business validity với retention policy và hold. |
| Chỉ lọc `deleted_at` ở một API | Các đường đọc khác vẫn lộ dữ liệu. | Tập trung chính sách đọc, quyền và kiểm thử đầy đủ. |
| Cho phép khôi phục mà không kiểm tra unique | Email/identifier va chạm với người mới. | Restore có kiểm tra, giao dịch và xử lý xung đột có chủ đích. |
| Dùng `ON DELETE CASCADE` cho mọi quan hệ | Xóa nhầm hóa đơn, audit hoặc chứng từ. | Phân loại phụ thuộc; giữ surrogate ID/tách danh tính đúng chính sách. |
| Không xử lý race giữa legal hold và purge | Xóa dữ liệu vừa được yêu cầu giữ. | Kiểm tra hold ngay trước commit và điều phối khóa/phiên bản. |
| Ngừng hiệu lực bằng đổi `status` nhưng không có khoảng thời gian | Không truy vấn được phiên bản áp dụng ở mốc T. | Lưu valid-time và ràng buộc khoảng. |
| Để hai khoảng giá hiệu lực chồng nhau | Truy vấn as-of trả nhiều giá. | Exclusion constraint hoặc quy tắc transaction có cùng hiệu quả. |
| Dùng `recorded_at` thay `effective_at` | Sai mốc hiệu lực khi điều chỉnh hồi tố. | Mô hình hóa hai chiều thời gian khi cần. |
| Xóa hàng nguồn nhưng bỏ sót search/cache | Dữ liệu đã ẩn vẫn được tìm thấy. | Sự kiện lifecycle, idempotent consumer, đối soát hoàn tất. |
| Sau restore backup xuất hiện lại dữ liệu đã erasure | Vi phạm mục đích xóa và gây rò rỉ. | Quy trình áp dụng lại quyết định erasure khi phục hồi. |
| Tự gán thời hạn lưu cố định không có căn cứ | Có thể xóa quá sớm hoặc giữ quá lâu. | Chính sách theo nhóm dữ liệu, trigger, phê duyệt và version. |
| Giữ chứng cứ xóa bằng cách copy toàn bộ PII | Tạo kho dữ liệu nhạy cảm mới. | Hồ sơ xác nhận tối thiểu, hạn giữ và quyền rõ. |

## 16. Bài tập thực hành: một hệ thống với ba vòng đời dữ liệu

**Bối cảnh:** nền tảng đặt phòng cho thuê thiết bị có ba nhóm dữ liệu:

1. **Tài khoản:** khách đăng ký bằng email, có thể tạm khóa, đóng và yêu cầu xóa thông tin cá nhân.
2. **Hợp đồng:** có hiệu lực trong một khoảng, có thể gia hạn hoặc kết thúc, và chứng từ thanh toán phải được giữ theo chính sách riêng.
3. **Bảng giá:** mức giá thay đổi theo ngày, đôi khi có điều chỉnh hồi tố sau khi phát hiện nhập nhầm.

Nền tảng có PostgreSQL, hệ tìm kiếm, cache, object storage lưu biên bản và kho báo cáo. Một số nhân viên cần xem lịch sử để giải quyết tranh chấp.

### Yêu cầu thiết kế

1. **Tách ngữ nghĩa:** với từng nhóm dữ liệu, nêu lúc nào dùng `status`, `deleted_at`, `valid_from/to`, `recorded_from/to` và chính sách purge. Giải thích vì sao không dùng một trường chung.
2. **Thiết kế khóa:** xác định khóa chính tài khoản/hợp đồng/phiên bản giá và foreign key; giải thích vì sao account ID không được tái sử dụng.
3. **Unique và restore:** một email đã xóa mềm được tái đăng ký; sau đó chủ tài khoản cũ muốn restore. Nêu ràng buộc và quy trình xử lý xung đột.
4. **As-of:** giá P1 có hiệu lực đến 00:00 ngày 1/4, giá P2 từ chính mốc đó. Viết điều kiện SQL để thời điểm 00:00 chỉ chọn P2.
5. **Bitemporal:** ngày 10/4 nhân viên sửa hồi tố giá đã có hiệu lực từ 1/4. Trả lời riêng “ngày 5/4 hệ thống đang biết giá nào?” và “hiện nay công nhận giá nào có hiệu lực ngày 5/4?”.
6. **Retention:** thiết kế phiếu policy cho hồ sơ tài khoản, hợp đồng, giao dịch và log truy cập, ghi trigger và bước xử lý khi hết hạn; không tự đặt thời hạn pháp lý.
7. **Hold:** tác vụ purge được xếp hàng, nhưng trước khi chạy đã có yêu cầu giữ chứng cứ tranh chấp. Mô tả cách worker tránh xóa nhầm.
8. **Xóa xuyên hệ thống:** liệt kê các bước với DB, search, cache, file, báo cáo và backup; phân biệt `PENDING`, `BLOCKED` và `COMPLETED`.
9. **Kiểm thử đồng thời:** hai yêu cầu xóa/khôi phục hoặc thay đổi email đến cùng lúc. Nêu version/transaction và idempotency.
10. **Kiểm thử an toàn:** chứng minh API thường không trả tài khoản đã xóa mềm; API điều tra chỉ cho người có quyền; tenant này không đọc được tài khoản tenant khác.
11. **Khôi phục backup:** giả lập restore từ bản sao có chứa một tài khoản đã erasure; mô tả cách không làm nó lộ lại.
12. **ADR:** chọn cách triển khai tối thiểu cho mỗi nhóm và nêu điều kiện khiến bạn mở rộng sang bitemporal hoặc kho archive.

### Bảng kiểm tự đánh giá

| Kiểm tra | Dấu hiệu đạt |
| --- | --- |
| **Ngữ nghĩa vòng đời** | Không nhầm ngừng hiệu lực với soft delete, archive hay erasure. |
| **Truy vấn lịch sử** | As-of dùng khoảng nửa mở chính xác; bitemporal phân biệt valid-time và recorded-time khi cần. |
| **Ràng buộc** | Khóa chính/FK/unique/exclusion phù hợp ranh giới nghiệp vụ, kể cả xung đột restore. |
| **Nhất quán** | Thay đổi trạng thái có transaction, optimistic locking và idempotency phù hợp. |
| **Retention** | Mốc tính hạn, policy version, ngoại lệ và hold rõ; không purge chỉ vì status hết hiệu lực. |
| **Dữ liệu phụ thuộc** | Không xóa nhầm giao dịch/chứng từ do cascade vô tội vạ. |
| **Bảo vệ PII** | Soft delete không bị coi là erasure; hệ ngoài, backup và hồ sơ chứng cứ được kiểm soát. |
| **Khôi phục và kiểm chứng** | Có thể audit quyết định xử lý, retry không tạo sai lệch, và đối chiếu kết quả xuyên hệ thống. |

**Kết luận:** xóa mềm chỉ là một cơ chế **ẩn và quản lý khả năng khôi phục** của bản ghi; ngừng hiệu lực là quy tắc **giá trị nghiệp vụ áp dụng vào lúc nào**; chính sách lưu lịch sử quyết định **cần giữ điều gì, theo căn cứ nào và kết thúc vòng đời dữ liệu ra sao**. Thiết kế tốt tách những chiều này ngay từ yêu cầu, dùng khóa/ràng buộc và bảng thời gian phù hợp, kiểm soát truy cập và xóa đa hệ thống, để vừa trả lời đúng câu hỏi lịch sử vừa bảo vệ dữ liệu theo nghĩa vụ thực tế.
