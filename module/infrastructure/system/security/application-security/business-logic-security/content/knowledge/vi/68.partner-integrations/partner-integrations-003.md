# Partner data ownership — Quyền sở hữu dữ liệu đối tác

Trong tích hợp đối tác, một API key hợp lệ chỉ giúp hệ thống xác định bên gửi yêu cầu. Quyết định cho phép đọc hoặc sửa dữ liệu còn phụ thuộc vào tenant, quan hệ với từng đối tượng, từng trường dữ liệu, trạng thái nghiệp vụ và hiệu lực của quyền tại lúc thực hiện thao tác.

Bài học thuộc chương **Partner Integrations**, trong phạm vi bảo vệ logic nghiệp vụ của module **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**. Trọng tâm là biến khái niệm “dữ liệu của đối tác” thành các business invariant có thể thực thi, để ngăn đọc chéo dữ liệu, sửa giá, tự phê duyệt, chiếm quyền sở hữu và áp dụng yêu cầu trùng.

Sau bài học, người học có thể:

- Phân biệt bên cung cấp dữ liệu, bên có thẩm quyền xác nhận dữ liệu và bên được cấp quyền sử dụng dữ liệu.
- Thiết kế ranh giới quyền theo tenant, đối tác, đối tượng và thuộc tính.
- Kết hợp state machine, transaction, kiểm soát đồng thời và idempotency để giữ ranh giới đó.
- Xác định các tình huống tấn công logic cần kiểm thử trên API, webhook và tác vụ nền.

## 1. “Ownership” cần được diễn giải thành quyền cụ thể

Trong bài này, **ownership là quan hệ kiểm soát kỹ thuật đối với dữ liệu**. Tên trường `owner_partner_id` không tự quyết định mọi vấn đề về quyền sở hữu thương mại hoặc cách sử dụng dữ liệu. Những nội dung đó cần được xác định riêng trong chính sách và thỏa thuận tích hợp.

Một bản ghi có thể chứa dữ liệu từ nhiều bên và chịu nhiều loại quyền khác nhau:

| Khía cạnh | Câu hỏi phải trả lời | Ví dụ |
|---|---|---|
| Nguồn dữ liệu | Ai đã gửi hoặc tạo giá trị này? | Đối tác gửi số lượng hàng có thể cung cấp |
| Bên có thẩm quyền | Ai được xác nhận giá trị chính thức? | Nền tảng duyệt giá bán |
| Ranh giới tenant | Dữ liệu thuộc phạm vi tổ chức nào? | Cùng đối tác tích hợp với hai nhà bán hàng khác nhau |
| Quan hệ sở hữu kỹ thuật | Đối tác nào được thao tác với bản ghi? | Đối tác A quản lý chào bán A-01 |
| Quyền đọc và ghi trường | Những thuộc tính nào được xem hoặc sửa? | Được sửa tồn kho, không được sửa trạng thái phê duyệt |
| Ủy quyền | Bên nào được thao tác thay, trong bao lâu? | Đối tác vận hành chỉ được đọc một tập thuộc tính |
| Vòng đời dữ liệu | Khi ngừng hợp tác, quyền và bản sao thay đổi thế nào? | Dừng xuất dữ liệu mới, xử lý dữ liệu đã lưu theo chính sách |

Ba suy luận nguy hiểm là:

1. “Đối tác tạo bản ghi nên được sửa mọi trường.”
2. “Có quyền đọc thì có quyền xuất, chia sẻ hoặc xóa.”
3. “Từng có quyền truy cập nên tác vụ đã đưa vào hàng đợi luôn được phép chạy.”

Mỗi quyền phải được mô tả bằng **chủ thể, hành động, tài nguyên, thuộc tính và điều kiện**, thay vì gói vào một cờ `isOwner`.

## 2. Ví dụ xuyên suốt: chào bán của nhà cung cấp

Giả sử nền tảng phục vụ nhiều tenant là các nhà bán hàng. Mỗi tenant có thể tích hợp với nhiều nhà cung cấp, và một nhà cung cấp có thể phục vụ nhiều tenant.

Đối tượng `partner_offer` biểu diễn chào bán của một nhà cung cấp trong một tenant:

~~~text
tenant_id             = T1
owner_partner_id      = PARTNER_A
external_offer_id     = SKU-42
partner_sku           = A-RED-42
available_quantity    = 120
proposed_unit_price   = 150000
approved_unit_price   = 159000
state                 = ACTIVE
version               = 7
owner_epoch           = 1
~~~

Quy ước nghiệp vụ của ví dụ:

- A được cập nhật tồn kho của chào bán thuộc A trong T1 khi tích hợp và chào bán đều đang hoạt động.
- A được đề xuất giá bằng một luồng riêng; giá đề xuất chưa phải giá đã duyệt.
- Nền tảng kiểm soát `approved_unit_price` và các chuyển trạng thái phê duyệt.
- A không được tự đổi `tenant_id`, `owner_partner_id`, `owner_epoch` hoặc giá đã duyệt.
- B có thể dùng cùng `external_offer_id = SKU-42` nhưng đó là một bản ghi khác.
- Quyền của A trong T1 không mở rộng sang T2.

Ma trận quyền cần được định nghĩa trước khi triển khai endpoint:

| Dữ liệu hoặc thao tác | Đối tác sở hữu | Đối tác được chia sẻ | Nền tảng có quyền phù hợp |
|---|---|---|---|
| Mã hàng đối tác | Đọc; sửa bằng luồng cho phép | Đọc nếu grant có trường này | Quản lý theo chính sách |
| Tồn kho | Đọc; cập nhật khi đủ điều kiện | Mặc định không ghi | Điều chỉnh qua luồng nghiệp vụ riêng |
| Giá đề xuất | Gửi đề xuất | Mặc định không đọc | Đọc và xử lý đề xuất |
| Giá đã duyệt | Đọc nếu được công bố | Đọc nếu được cấp | Thay đổi qua luồng phê duyệt |
| Trạng thái phê duyệt | Đọc phần được công bố | Không có quyền mặc định | Chuyển trạng thái theo state machine |
| Tenant, chủ sở hữu | Không được đổi trực tiếp | Không được đổi | Chỉ qua luồng chuyển giao được kiểm soát |
| Đánh giá rủi ro nội bộ | Không được đọc | Không được đọc | Chỉ chủ thể nội bộ có quyền |

“Nền tảng có quyền” cũng là một điều kiện phân quyền, không có nghĩa mọi tài khoản nhân viên hoặc mọi service nội bộ đều được truy cập.

## 3. Các đường lạm dụng cần nhìn thấy

### 3.1. Đổi định danh để truy cập dữ liệu của bên khác

Endpoint sau vẫn có thể sai dù đã yêu cầu token có scope `offers:write`:

~~~http
PATCH /partner/offers/8ca4d121-67b0-4d21-a168-f51c31f2f010/inventory
Authorization: Bearer <token-cua-A>
Content-Type: application/json

{
  "availableQuantity": 50,
  "expectedVersion": 7
}
~~~

Nếu server chỉ gọi `findById(offerId)` rồi cập nhật, A có thể thay ID bằng ID của B. UUID khó đoán không thay thế kiểm tra quyền.

OWASP gọi việc cho phép thao tác lên đối tượng không thuộc phạm vi được cấp là **Broken Object Level Authorization**; kiểm tra phải gắn với hành động và đối tượng cụ thể. [OWASP API1:2023](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

### 3.2. Sửa trường nhạy cảm trên đúng đối tượng

A gửi ID đúng của mình, nhưng thêm các trường:

~~~json
{
  "availableQuantity": 50,
  "expectedVersion": 7,
  "ownerPartnerId": "PARTNER_B",
  "approvedUnitPrice": 1,
  "state": "ACTIVE"
}
~~~

Kiểm tra ownership ở mức bản ghi vẫn chưa đủ nếu server tự động ánh xạ toàn bộ body vào entity.

OWASP phân biệt lỗi ở mức thuộc tính là **Broken Object Property Level Authorization**: ứng dụng phải kiểm soát cả trường được đọc lẫn trường được sửa. [OWASP API3:2023](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

### 3.3. Lạm dụng định danh ngoài

Hai đối tác đều dùng mã `SKU-42`. Consumer tìm bản ghi bằng:

~~~sql
SELECT *
FROM partner_offer
WHERE external_offer_id = :externalOfferId;
~~~

Một webhook có chữ ký hợp lệ của A vẫn có thể ghi nhầm dữ liệu B nếu truy vấn ánh xạ thiếu phạm vi.

Khóa tra cứu đúng phải bao gồm ít nhất:

~~~text
(tenant_id, partner_id, external_offer_id)
~~~

Nếu một đối tác có nhiều tài khoản tích hợp và mã ngoài chỉ duy nhất trong từng tài khoản, phải thêm `partner_account_id` hoặc `integration_id` vào phạm vi. Phạm vi phải phản ánh namespace thực tế của bên phát hành mã.

### 3.4. Dùng quyền cũ hoặc chia sẻ để chiếm quyền

Một job được tạo khi A còn quyền, nhưng chạy sau khi tích hợp bị thu hồi. Hoặc B có grant đọc dữ liệu và gửi request thay `owner_partner_id` thành B.

Cả hai trường hợp đều không thể giải quyết chỉ bằng việc xác thực request đầu tiên. Hệ thống cần quản lý vòng đời quyền và kiểm tra lại ở nơi tác dụng nghiệp vụ được áp dụng.

## 4. Viết business invariant trước khi viết controller

Với luồng cập nhật tồn kho trong ví dụ, có thể đặt các invariant sau:

| Mã | Invariant |
|---|---|
| INV-01 | Mọi lần đọc, ghi và ánh xạ mã ngoài phải nằm trong đúng tenant đã được server xác nhận |
| INV-02 | Cập nhật tồn kho trực tiếp chỉ được áp dụng cho bản ghi thuộc đối tác đang gọi |
| INV-03 | Tích hợp phải còn hiệu lực tại điểm quyết định ghi dữ liệu |
| INV-04 | Body cập nhật tồn kho không được thay đổi chủ sở hữu, tenant, giá đã duyệt hoặc trạng thái phê duyệt |
| INV-05 | Chào bán chỉ được cập nhật tồn kho trong các trạng thái được chính sách cho phép |
| INV-06 | Cập nhật phải dựa trên phiên bản hợp lệ; hai yêu cầu đồng thời không được âm thầm ghi đè nhau |
| INV-07 | Một sự kiện nghiệp vụ được nhận lại không được tạo tác dụng phụ lần thứ hai |
| INV-08 | Grant đọc hoặc quyền gửi webhook không tự sinh quyền chuyển giao, xóa hoặc chia sẻ tiếp |
| INV-09 | Sau chuyển giao hoặc thu hồi, quyền cũ không được dùng để áp dụng công việc còn trong hàng đợi |

Một mô hình quyết định quyền cho trường hợp tổng quát:

~~~text
allow =
  authenticated_principal
  AND verified_tenant_context
  AND active_integration
  AND required_scope
  AND (direct_owner_relation OR matching_active_grant)
  AND allowed_action
  AND allowed_fields
  AND allowed_business_state
  AND current_authorization_generation
~~~

Trong endpoint cập nhật tồn kho trực tiếp của bài này, nhánh `matching_active_grant` không được hỗ trợ: bên gọi phải là chủ sở hữu kỹ thuật. Nếu sau này hỗ trợ ghi qua ủy quyền, cần chính sách riêng cho hành động đó; không nới toàn bộ kiểm tra ownership.

Scope mô tả nhóm khả năng của credential. Quan hệ ownership hoặc grant mô tả tài nguyên cụ thể. State machine mô tả thời điểm một hành động có ý nghĩa hợp lệ. Ba lớp này cùng tham gia quyết định.

## 5. Tách vòng đời tích hợp khỏi vòng đời dữ liệu

Tích hợp và chào bán có hai state machine độc lập.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> ACTIVE: Xác minh và cấp quyền
    ACTIVE --> SUSPENDED: Tạm khóa
    SUSPENDED --> ACTIVE: Đánh giá và mở lại
    PENDING --> REVOKED: Hủy đăng ký
    ACTIVE --> REVOKED: Chấm dứt quyền
    SUSPENDED --> REVOKED: Chấm dứt quyền
    REVOKED --> [*]
~~~

Trong mô hình này, tích hợp đã `REVOKED` không được mở lại trực tiếp. Nếu hợp tác trở lại, quy trình cấp quyền tạo thế hệ quyền mới.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_REVIEW: Đối tác gửi duyệt
    PENDING_REVIEW --> ACTIVE: Nền tảng phê duyệt
    PENDING_REVIEW --> DRAFT: Yêu cầu chỉnh sửa
    ACTIVE --> SUSPENDED: Nền tảng tạm dừng
    SUSPENDED --> ACTIVE: Nền tảng cho phép hoạt động
    ACTIVE --> ARCHIVED: Kết thúc chào bán
    SUSPENDED --> ARCHIVED: Kết thúc chào bán
    ARCHIVED --> [*]
~~~

Đối tác không được dùng endpoint cập nhật tồn kho để chuyển `DRAFT` thành `ACTIVE`. Một chào bán vẫn `ACTIVE` cũng không cho phép cập nhật nếu tích hợp của chủ sở hữu đã `SUSPENDED`.

Thay đổi giá cần luồng đề xuất và phê duyệt riêng. Nếu đề xuất mới không được phép ảnh hưởng giá đang có hiệu lực, lưu đề xuất tách khỏi giá đã duyệt và ghi rõ phiên bản đề xuất được phê duyệt. Không dùng phép merge JSON chung cho cả hai loại dữ liệu.

## 6. Mô hình dữ liệu giữ ranh giới ownership

Ví dụ PostgreSQL dưới đây chỉ mô tả các bảng liên quan. Danh mục tenant, đối tác, tài khoản xác thực và các ràng buộc đến chúng thuộc phần nền tảng của hệ thống.

~~~sql
CREATE TABLE partner_integration (
    tenant_id      UUID NOT NULL,
    partner_id     UUID NOT NULL,
    status         VARCHAR(16) NOT NULL,
    authz_epoch    BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY (tenant_id, partner_id),
    CHECK (status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'REVOKED')),
    CHECK (authz_epoch > 0)
);

CREATE TABLE partner_offer (
    id                    UUID PRIMARY KEY,
    tenant_id             UUID NOT NULL,
    owner_partner_id      UUID NOT NULL,
    external_offer_id     VARCHAR(128) NOT NULL,
    partner_sku           VARCHAR(128) NOT NULL,
    available_quantity    INTEGER NOT NULL,
    proposed_unit_price   NUMERIC(19, 2),
    approved_unit_price   NUMERIC(19, 2),
    state                 VARCHAR(24) NOT NULL,
    version               BIGINT NOT NULL DEFAULT 0,
    owner_epoch           BIGINT NOT NULL DEFAULT 1,

    FOREIGN KEY (tenant_id, owner_partner_id)
        REFERENCES partner_integration (tenant_id, partner_id),

    UNIQUE (tenant_id, owner_partner_id, external_offer_id),
    UNIQUE (tenant_id, id),

    CHECK (available_quantity >= 0),
    CHECK (proposed_unit_price IS NULL OR proposed_unit_price >= 0),
    CHECK (approved_unit_price IS NULL OR approved_unit_price >= 0),
    CHECK (version >= 0),
    CHECK (owner_epoch > 0),
    CHECK (state IN (
        'DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'SUSPENDED', 'ARCHIVED'
    ))
);
~~~

Ý nghĩa của các lựa chọn:

- `tenant_id` giữ ranh giới tổ chức; `owner_partner_id` giữ quan hệ đối tác trong tenant đó.
- Khóa ngoại ghép tránh liên kết một chào bán với một cặp tenant–đối tác chưa đăng ký.
- Unique constraint theo namespace cho phép A và B có mã ngoài giống nhau mà không nhận nhầm bản ghi.
- `version` phát hiện cạnh tranh cập nhật dữ liệu.
- `authz_epoch` đánh dấu thế hệ cấp quyền của tích hợp.
- `owner_epoch` đánh dấu thế hệ ownership của bản ghi, hữu ích khi chuyển giao hoặc xử lý công việc cũ.

Các cột epoch chỉ có tác dụng khi được tăng tại đúng chuyển đổi và được so sánh ở nơi áp dụng thao tác. Chúng không tự động thu hồi credential hoặc job.

Khóa ngoại không kiểm tra tích hợp đang `ACTIVE`. Check constraint không biết ai đang gọi API. Những điều kiện này vẫn cần được thực thi ở tầng nghiệp vụ hoặc bằng cơ chế cơ sở dữ liệu được thiết kế riêng.

Với bảng con, nên dùng khóa ngoại ghép như `(tenant_id, offer_id)` tham chiếu `(tenant_id, id)`, thay vì chỉ liên kết bằng `offer_id` rồi mặc định tenant luôn đúng.

### 6.1. Truy vấn phải thể hiện phạm vi quyền

Đối với cập nhật trực tiếp bởi chủ sở hữu:

~~~sql
SELECT id, available_quantity, state, version, owner_epoch
FROM partner_offer
WHERE tenant_id = :verifiedTenantId
  AND owner_partner_id = :authenticatedPartnerId
  AND id = :offerId
FOR UPDATE;
~~~

Không để body quyết định hai tham số đầu. Nếu URL cho phép chọn tenant, server phải xác nhận chủ thể có quan hệ tích hợp còn hiệu lực với tenant đó.

Phạm vi này cũng phải xuất hiện trong truy vấn danh sách, tìm kiếm, đếm, export, tải tệp đính kèm và xử lý hàng loạt. Việc endpoint chi tiết đúng không đảm bảo endpoint tìm kiếm đã đúng.

### 6.2. Row-level security là lớp bổ sung

Có thể dùng PostgreSQL Row-Level Security để bổ sung giới hạn hàng. Cần kiểm tra role chạy ứng dụng: superuser và role có `BYPASSRLS` vượt qua RLS; chủ bảng thường cũng vượt qua nếu chưa áp dụng `FORCE ROW LEVEL SECURITY`. [PostgreSQL 16 — Row Security Policies](https://www.postgresql.org/docs/16/ddl-rowsecurity.html).

Nếu policy dựa trên context của kết nối, context phải do server đặt an toàn, gắn với transaction và không rò sang request khác trong connection pool. RLS cũng không thay thế kiểm tra trường được ghi, trạng thái phê duyệt hoặc idempotency.

## 7. Minh họa Java: cập nhật tồn kho trong một transaction

Đoạn mã sau minh họa cấu trúc service theo phong cách Spring, không phải chương trình độc lập. Các repository, exception, policy, audit và outbox là thành phần cần triển khai của ứng dụng.

Giả định:

- `PartnerPrincipal` được tạo sau khi credential đã được xác thực và ánh xạ với tenant, đối tác, scope và thế hệ quyền do server quản lý.
- Endpoint dùng DTO riêng và được cấu hình từ chối thuộc tính JSON không được khai báo. Không bind request trực tiếp vào entity.
- Phương thức `@Transactional` được gọi qua cơ chế transaction của ứng dụng; các exception từ chối bên dưới làm rollback.
- Các repository dùng cùng transaction cơ sở dữ liệu và khóa hàng bằng `SELECT ... FOR UPDATE`.

~~~java
public record StockChange(
        int availableQuantity,
        long expectedVersion
) {}

public record PartnerStockView(
        UUID offerId,
        int availableQuantity,
        long version
) {}

@Transactional
public PartnerStockView changeStock(
        PartnerPrincipal principal,
        UUID offerId,
        StockChange command
) {
    policy.requireScope(principal, "offers:inventory:write");

    if (command.availableQuantity() < 0
            || command.expectedVersion() < 0) {
        throw new InvalidCommandException();
    }

    UUID tenantId = principal.verifiedTenantId();
    UUID partnerId = principal.partnerId();

    // Luôn khóa tích hợp trước khi khóa chào bán.
    Integration integration = integrations
            .lockByTenantAndPartner(tenantId, partnerId)
            .orElseThrow(AccessDeniedException::new);

    if (integration.status() != IntegrationStatus.ACTIVE
            || integration.authzEpoch() != principal.authzEpoch()) {
        throw new AccessDeniedException();
    }

    Offer offer = offers
            .lockOwnedOffer(tenantId, partnerId, offerId)
            .orElseThrow(ResourceNotFoundException::new);

    if (offer.state() != OfferState.ACTIVE) {
        throw new InvalidBusinessStateException();
    }

    if (offer.version() != command.expectedVersion()) {
        throw new VersionConflictException();
    }

    long previousVersion = offer.version();
    offer.changeAvailableQuantity(command.availableQuantity());

    // Thực thi UPDATE có scope; tăng version đúng một lần.
    int affected = offers.updateStock(
            tenantId,
            partnerId,
            offer.id(),
            offer.ownerEpoch(),
            previousVersion,
            offer.availableQuantity()
    );

    if (affected != 1) {
        throw new VersionConflictException();
    }

    long newVersion = previousVersion + 1;

    audit.appendStockChanged(
            principal, offer.id(), previousVersion, newVersion
    );

    outbox.appendStockChanged(
            tenantId, partnerId, offer.id(), newVersion
    );

    return new PartnerStockView(
            offer.id(), offer.availableQuantity(), newVersion
    );
}
~~~

Hợp đồng của `updateStock` có thể được hiện thực bằng SQL tham số hóa:

~~~sql
UPDATE partner_offer
SET available_quantity = :quantity,
    version = version + 1
WHERE tenant_id = :tenantId
  AND owner_partner_id = :partnerId
  AND id = :offerId
  AND owner_epoch = :ownerEpoch
  AND version = :expectedVersion
  AND state = 'ACTIVE';
~~~

Ví dụ giữ khóa hàng để kiểm tra trạng thái và ghi trong cùng transaction. Điều kiện phiên bản và ownership trong câu `UPDATE` tiếp tục thể hiện rõ hợp đồng ghi dữ liệu; không được bỏ qua số hàng cập nhật.

Audit thành công và outbox được ghi cùng thay đổi tồn kho. Outbox publisher có thể phát lại sự kiện, nên consumer nhận sự kiện đó vẫn cần chống áp dụng trùng. Không gọi API đối tác bên ngoài khi đang giữ khóa transaction.

Response chỉ chứa ba trường được phép công bố. Trả nguyên entity sẽ làm quyền đọc phụ thuộc vào các cột được thêm trong tương lai.

Đoạn mã tập trung vào ownership và kiểm soát đồng thời. Nó chưa triển khai lưu kết quả theo idempotency key; yêu cầu thử lại với phiên bản cũ có thể nhận lỗi xung đột. Nếu hợp đồng API yêu cầu trả lại kết quả lần trước khi retry, cần bổ sung cơ chế ở phần 9.

## 8. Thu hồi quyền và khoảng trống giữa kiểm tra với ghi

Tình huống dễ bỏ sót:

~~~text
t1: Request đọc trạng thái tích hợp là ACTIVE.
t2: Quản trị viên thu hồi tích hợp.
t3: Request tiếp tục ghi tồn kho bằng kết quả kiểm tra ở t1.
~~~

Chỉ thêm `@Transactional` không tự ngăn được tình huống này. Phải có cơ chế đồng bộ giữa luồng thu hồi và luồng ghi.

Trong ví dụ, cả hai luồng khóa cùng hàng `partner_integration` trước khi thay đổi:

| Luồng | Các bước trong transaction |
|---|---|
| Cập nhật tồn kho | Khóa tích hợp → xác nhận trạng thái và epoch → khóa chào bán → kiểm tra và ghi → commit |
| Thu hồi tích hợp | Khóa tích hợp → đổi sang REVOKED và tăng authz_epoch → ghi audit/outbox → commit |

Với cùng cơ sở dữ liệu và mọi đường ghi đều tuân thủ quy tắc này:

- Nếu thu hồi commit trước, cập nhật tiếp theo thấy tích hợp đã bị thu hồi và bị từ chối.
- Nếu cập nhật giữ khóa trước, thu hồi phải đợi; cập nhật đó hoàn thành trước thời điểm thu hồi có hiệu lực tại commit.

Đây là một định nghĩa cụ thể về thứ tự hiệu lực. Nếu sản phẩm yêu cầu ngừng thao tác ngay khi người dùng bấm thu hồi, cần cơ chế khác và hợp đồng vận hành tương ứng; không được tuyên bố khóa hàng đáp ứng điều kiện đó.

Khóa một hàng tích hợp cho mọi lần ghi có thể tạo điểm nghẽn. Đây là phương án minh họa dễ kiểm chứng; hệ thống lưu lượng lớn có thể dùng thiết kế khác nhưng vẫn phải chứng minh được thứ tự giữa thu hồi và tác dụng nghiệp vụ.

Đối với hệ thống phân tán, khóa hàng ở service nhận HTTP không bảo vệ cơ sở dữ liệu của service khác. Consumer áp dụng thay đổi phải kiểm tra quyền hoặc fencing token tại nơi ghi. Cần quy định rõ tác dụng nào đã commit trước thu hồi được giữ lại và tác dụng nào chưa thực hiện phải bị hủy.

## 9. Webhook, idempotency và thứ tự sự kiện

Chữ ký webhook hợp lệ chứng minh thông điệp phù hợp với credential được xác minh. Nó không chứng minh rằng bên gửi được sửa mọi tài nguyên hoặc rằng sự kiện còn phù hợp với trạng thái hiện tại.

### 9.1. Pipeline xử lý một sự kiện

~~~mermaid
flowchart TD
    A[Nhận thông điệp] --> B[Xác minh credential hoặc chữ ký]
    B --> C[Ánh xạ tenant và đối tác từ cấu hình tin cậy]
    C --> D[Kiểm tra tích hợp và thế hệ quyền]
    D --> E[Tra tài nguyên trong đúng namespace]
    E --> F[Kiểm tra owner hoặc grant phù hợp]
    F --> G[Kiểm tra trường, trạng thái và phiên bản nguồn]
    G --> H[Trong transaction: inbox, thay đổi dữ liệu, audit, outbox]
    H --> I[Commit và trả kết quả]
~~~

Các kiểm tra có thể thực hiện sớm để loại request sai, nhưng kiểm tra quyền có khả năng thay đổi và phiên bản tài nguyên phải được xác nhận lại trong transaction áp dụng dữ liệu.

Body có thể chứa `partnerId` để đối chiếu tính nhất quán. Giá trị đó không được dùng để chọn bên sở hữu credential. Trường hợp định tuyến qua header cũng phải được đối chiếu với cấu hình xác thực của server.

Nếu chưa có ánh xạ mã ngoài, không tự nhận một bản ghi khác là của bên gửi. Endpoint tạo dữ liệu, nếu được hỗ trợ, phải có quyền tạo riêng và tự gắn tenant, chủ sở hữu từ context tin cậy.

### 9.2. Khóa chống trùng cần có phạm vi

Một khóa inbox trong ví dụ có thể là:

~~~text
(tenant_id, partner_id, event_id)
~~~

Nếu `event_id` chỉ duy nhất trong từng tài khoản hoặc từng nguồn, phải thêm định danh nguồn đó. Lưu kèm:

~~~text
event_type
resource_binding
payload_fingerprint
received_at
applied_at
authorization_epoch_at_acceptance
owner_epoch_at_acceptance
result_reference
~~~

Các epoch “at acceptance” do server ghi sau xác minh, không lấy quyền quyết định từ giá trị tự khai của bên gửi.

`payload_fingerprint` được tính từ biểu diễn chuẩn hóa của dữ liệu có ý nghĩa nghiệp vụ, bao gồm loại thao tác và tài nguyên đích. Không mặc định hai JSON khác khoảng trắng là hai thao tác khác nhau; cũng không bỏ qua trường có thể làm thay đổi kết quả nghiệp vụ.

Quy tắc xử lý:

| Trường hợp | Kết quả mong muốn |
|---|---|
| Khóa mới, quyền và trạng thái hợp lệ | Áp dụng một lần và lưu kết quả |
| Cùng khóa, cùng fingerprint | Không tạo tác dụng phụ mới; trả kết quả cũ nếu hiện vẫn được phép xem |
| Cùng khóa, fingerprint khác | Từ chối xung đột, ghi tín hiệu điều tra |
| Hai request đồng thời cùng khóa | Unique constraint phân xử; chỉ một transaction áp dụng |
| Cùng event_id nhưng khác tenant hoặc đối tác | Là các namespace khác nhau, không được trả nhầm kết quả |
| Quyền đã bị thu hồi | Không dùng bản ghi idempotency để vượt kiểm tra quyền hiện tại |

Một cách triển khai là chèn inbox, áp dụng nghiệp vụ, ghi kết quả và outbox trong cùng transaction. Khi gặp xung đột unique, transaction thua cuộc phải xử lý theo cơ chế của thư viện và cơ sở dữ liệu, rồi đọc kết quả đã commit; không tiếp tục ghi nghiệp vụ. Nếu transaction đầu rollback thì lần sau vẫn có thể xử lý.

Không lưu “đã xử lý” thành công ở một transaction riêng trước khi cập nhật dữ liệu. Crash giữa hai transaction có thể làm sự kiện bị đánh dấu xong trong khi nghiệp vụ chưa xảy ra.

Thời gian giữ inbox hoặc idempotency record phải bao phủ cửa sổ retry/replay đã cam kết. Nếu xóa dấu vết chống trùng, một sự kiện cũ có thể được nhận như mới; với thao tác quan trọng cần định danh nghiệp vụ duy nhất hoặc watermark bền vững bổ sung.

### 9.3. Idempotency không giải quyết sự kiện sai thứ tự

Giả sử hai sự kiện snapshot của cùng chào bán là:

~~~text
source_version = 21, available_quantity = 40
source_version = 20, available_quantity = 90
~~~

Nếu sự kiện 20 đến sau, nó không được ghi đè snapshot 21 chỉ vì có event ID mới.

Cần phân biệt:

- **Snapshot đầy đủ:** có thể chấp nhận phiên bản mới hơn và bỏ qua phiên bản cũ; việc bỏ qua khoảng trống chỉ hợp lệ nếu hợp đồng nguồn cho phép.
- **Delta:** sự kiện “trừ 5” không tương đương snapshot. Nếu cần đủ thứ tự, khi thiếu phiên bản phải chờ, lấy lại dữ liệu hoặc đối soát; không bỏ qua sự kiện thiếu rồi coi kết quả là đúng.
- **Timestamp:** không tự bảo đảm thứ tự khi đồng hồ lệch hoặc hai sự kiện trùng thời gian.

`source_version` của đối tác và `version` nội bộ là hai khái niệm khác nhau. Phiên bản nguồn phải gắn đúng tài nguyên và thế hệ binding; một số lớn không cấp quyền sửa bản ghi của bên khác.

## 10. Chia sẻ có giới hạn và chuyển giao ownership

### 10.1. Grant không phải đổi chủ sở hữu

Một grant đọc cho B nên thể hiện rõ:

~~~text
tenant             = T1
resource           = offer-01
grantee            = PARTNER_B
actions            = [READ]
readable_fields    = [partner_sku, available_quantity]
valid_until        = thời điểm hết hạn
grant_epoch        = thế hệ hiện tại
status             = ACTIVE
~~~

Server kiểm tra quyền của bên tạo grant, trạng thái tích hợp của bên nhận, hạn dùng và tập thuộc tính được phép. B không được mở rộng grant hoặc chia sẻ tiếp nếu không có quyền ủy quyền tương ứng.

Một grant đọc không được dùng cho endpoint sửa tồn kho. Khi API nhận filter hoặc danh sách field động, server phải xác nhận toàn bộ field yêu cầu nằm trong tập cho phép. Cũng cần kiểm soát filter và sort để tránh suy luận giá trị của trường bị ẩn qua kết quả tìm kiếm.

### 10.2. Chuyển giao là một nghiệp vụ riêng

Không cung cấp lối tắt như:

~~~http
PATCH /partner/offers/offer-01

{"ownerPartnerId": "PARTNER_B"}
~~~

Một quy trình chuyển giao có thể gồm:

1. Tạo yêu cầu nêu tenant, tài nguyên, chủ hiện tại, chủ đích, lý do và phiên bản kỳ vọng.
2. Thu thập phê duyệt theo chính sách; nếu yêu cầu tách nhiệm vụ thì bên đề nghị không tự phê duyệt.
3. Trong transaction, khóa các tích hợp liên quan theo thứ tự ổn định, rồi khóa tài nguyên.
4. Kiểm tra lại phê duyệt, trạng thái, phiên bản, chủ hiện tại và khả năng nhận dữ liệu của bên đích.
5. Xử lý xung đột namespace mã ngoài, cập nhật quan hệ sở hữu, tăng `owner_epoch` và `version`.
6. Vô hiệu hoặc xét lại grant cũ; ghi audit và outbox cùng transaction.
7. Sau commit, xử lý cache, search index và tác vụ đang chờ; nơi áp dụng tác vụ vẫn phải so sánh epoch.

Không lấy số lượng phê duyệt cố định làm quy tắc chung cho mọi hệ thống; đó là chính sách cần xác định theo tác động nghiệp vụ.

Nếu B đã có mã `SKU-42` trong cùng tenant, cần quy tắc ánh xạ mới trước khi chuyển. Không ghi đè bản ghi cũ hoặc “upsert cho tiện”.

Cần xác định riêng dữ liệu nào đi theo tài nguyên và dữ liệu nào tiếp tục gắn với A, chẳng hạn lịch sử nguồn hoặc đề xuất thương mại chưa công bố. Chuyển chủ sở hữu kỹ thuật không tự cấp cho B quyền đọc mọi lịch sử của A.

Đổi chủ và chuyển tenant cũng là hai nghiệp vụ khác nhau. Ví dụ này chỉ cho phép chuyển giữa các đối tác trong cùng tenant; chuyển sang tenant khác cần thiết kế và phê duyệt riêng.

## 11. Ownership phải theo dữ liệu ra khỏi database

### 11.1. Cache và search index

Cache key chỉ có `offerId` không đủ cho response phụ thuộc quyền. Key hoặc cơ chế kiểm tra khi phục vụ phải xét tenant, đối tác hoặc grant, tập trường và thế hệ quyền phù hợp.

Một khóa cache có thể có dạng:

~~~text
partner-offer:{tenantId}:{partnerId}:{offerId}:{authzEpoch}:{viewPolicyVersion}
~~~

Đây chỉ là ví dụ cho view của chủ sở hữu. View dựa trên grant phải xét cả grant và thế hệ ownership. Nếu quyền bị thu hồi nhưng cache vẫn phục vụ theo context cũ mà không xác nhận hiệu lực, thêm epoch vào key cũng chưa giải quyết vấn đề.

Search index cần giữ nhãn tenant và quan hệ quyền đủ để lọc trước khi trả kết quả. Tổng số kết quả, đoạn trích và gợi ý tìm kiếm cũng có thể tiết lộ dữ liệu.

### 11.2. Export, batch và download

- Job export phải gắn chủ thể yêu cầu, tenant, phạm vi dữ liệu và phiên bản quyền; kiểm tra lại khi chạy và khi tải.
- Tệp export không được đưa vào vị trí dùng chung rồi chỉ bảo vệ bằng URL khó đoán.
- URL ký sẵn đã phát hành có thể còn dùng được đến khi hết hạn, tùy cơ chế lưu trữ. Nếu yêu cầu thu hồi tức thời, cần cổng tải kiểm tra quyền hoặc cơ chế vô hiệu phù hợp.
- Endpoint batch phải định nghĩa rõ toàn bộ thành công hoặc kết quả riêng từng phần tử. Không cập nhật một số bản ghi trái phép rồi mới trả lỗi chung.
- Metadata của tệp đính kèm phải có ranh giới tenant và tài nguyên; biết object key của kho tệp không phải bằng chứng được phép tải.

### 11.3. Khi ngừng hợp tác

Quy trình offboarding cần xác định ít nhất:

- Dừng quyền đọc, ghi, webhook và việc phát hành dữ liệu mới.
- Thu hồi hoặc xoay credential theo thiết kế; tăng thế hệ quyền khi cần vô hiệu công việc cũ.
- Dừng hoặc tái đánh giá job, retry, lịch đồng bộ và grant liên quan.
- Xử lý cache, bản sao, export và dữ liệu lưu giữ theo chính sách đã xác định.
- Ghi nhận dữ liệu đã chia sẻ và các bước xử lý với bản sao bên ngoài hệ thống.

Thu hồi quyền truy cập không đồng nghĩa với xóa toàn bộ dữ liệu. Hệ thống cũng không nên hứa rằng đổi trạng thái tích hợp sẽ tự xóa được bản sao đối tác đã tải về.

## 12. Audit để tái dựng quyết định quyền

Audit thành công cần đủ thông tin để trả lời: ai đã làm gì, dưới quyền nào, với bản ghi nào, ở phiên bản nào?

~~~text
request_id / correlation_id
actor_type và actor_id
tenant_id và partner_id
resource_type và resource_id
action
authorization_basis: DIRECT_OWNER hoặc grant_id
authz_epoch và owner_epoch
previous_version và new_version
changed_field_names
outcome và reason_code
event_id hoặc idempotency_reference nếu có
~~~

Không ghi token, khóa bí mật hoặc toàn bộ payload nhạy cảm vào log. Nếu cần giữ dữ liệu trước và sau thay đổi, xác định trường nào được lưu, ai được đọc và thời gian giữ.

Audit thành công nên commit cùng thay đổi nghiệp vụ. Log cho thao tác bị từ chối cần cơ chế riêng nếu transaction nghiệp vụ sẽ rollback; không giả định bản ghi audit nằm trong transaction thất bại vẫn còn.

Tín hiệu đáng theo dõi gồm:

- Một credential thử nhiều ID không thuộc phạm vi.
- Nhiều body chứa `ownerPartnerId`, `approvedUnitPrice` hoặc `state` trong endpoint tồn kho.
- Cùng idempotency key nhưng fingerprint khác.
- Job hoặc webhook liên tục dùng epoch cũ sau thu hồi hoặc chuyển giao.
- Lượng export hoặc số lần thử truy cập dữ liệu tăng khác thường.

Log là chứng cứ hỗ trợ điều tra; nó không thay thế điều kiện chặn tại nơi đọc và ghi.

## 13. Ma trận kiểm thử tình huống tấn công logic

Bảng dưới đây là đặc tả kiểm thử cần xây dựng khi triển khai. Không chỉ kiểm tra HTTP status; cần quan sát cả dữ liệu, audit thành công, outbox và tác dụng phụ.

| Tình huống | Kết quả bắt buộc |
|---|---|
| A cập nhật tồn kho của A trong T1, đúng phiên bản | Thành công; tăng version một lần; không đổi giá và ownership |
| A dùng ID chào bán của B trong T1 | Bị từ chối; không thay đổi dữ liệu hoặc phát sự kiện thành công |
| A trong T1 dùng ID thuộc T2 | Không đọc hoặc ghi chéo tenant |
| Body tự khai tenant hoặc partner khác | Không đổi context xác thực; từ chối nếu trái hợp đồng request |
| A thêm trường giá đã duyệt hoặc chủ sở hữu | Request bị từ chối theo schema; các trường được bảo vệ không đổi |
| A sửa tồn kho khi chào bán đang chờ duyệt | Bị từ chối theo state machine |
| Scope hợp lệ nhưng tích hợp SUSPENDED | Bị từ chối |
| A và B có cùng mã ngoài | Webhook của mỗi bên chỉ ánh xạ bản ghi trong namespace của bên đó |
| B có grant READ nhưng gọi cập nhật tồn kho | Bị từ chối |
| Grant chỉ cho hai trường nhưng yêu cầu trường nội bộ | Không trả dữ liệu ngoài grant |
| Hai request có cùng expectedVersion | Chỉ một request thành công; request còn lại xung đột |
| Gửi lại cùng event và payload | Không có tác dụng phụ lần hai |
| Gửi lại cùng event nhưng payload khác | Xung đột; không sửa nghiệp vụ |
| Gửi cùng event_id từ đối tác khác | Không nhận kết quả hoặc tài nguyên của đối tác đầu |
| Snapshot cũ đến sau snapshot mới | Không làm dữ liệu quay về phiên bản nguồn cũ |
| Thu hồi commit trước transaction cập nhật | Transaction cập nhật bị từ chối |
| Cập nhật giữ khóa trước yêu cầu thu hồi | Cập nhật commit trước; thu hồi có hiệu lực sau theo hợp đồng đã mô tả |
| Job chờ từ trước chuyển giao | Không ghi bằng ownership epoch cũ |
| Lỗi giữa ghi nghiệp vụ và ghi outbox | Transaction rollback; retry có thể xử lý lại an toàn |
| Gọi lại sau khi quyền bị thu hồi | Idempotency record không làm lộ kết quả hiện không được phép xem |
| Export tạo trước nhưng tải sau thu hồi | Cơ chế tải tuân thủ chính sách thu hồi đã công bố |
| Batch chứa cả ID được phép và ID trái phép | Thực hiện đúng hợp đồng atomic hoặc từng phần; không ghi trái phép |

Các ca đồng thời cần dùng ít nhất hai transaction thực, điều khiển thứ tự bằng barrier hoặc latch. Gọi hai hàm tuần tự hoặc chèn thời gian chờ ngẫu nhiên không chứng minh được việc khóa và thứ tự commit.

Nếu dùng RLS, thực hiện kiểm thử bằng đúng role mà ứng dụng dùng, không chỉ bằng tài khoản quản trị cơ sở dữ liệu.

## 14. Những quyết định cần chốt trước khi triển khai

Một thiết kế ownership có thể triển khai khi trả lời rõ các câu hỏi sau:

1. Namespace chính xác của từng mã ngoài là gì?
2. Ai có thẩm quyền trên mỗi trường; trường nào chỉ là đề xuất?
3. Mỗi hành động yêu cầu ownership trực tiếp hay cho phép grant?
4. Điều kiện trạng thái và phiên bản được xác nhận ở đâu, trong transaction nào?
5. Thu hồi có hiệu lực tại thời điểm nào; tác vụ đang chạy được xử lý ra sao?
6. Dấu vết chống trùng được giữ bao lâu, và sự kiện sai thứ tự được xử lý thế nào?
7. Chuyển giao ảnh hưởng tới lịch sử, grant, namespace và công việc tồn đọng như thế nào?
8. Cache, export và bản sao nào có thể tiếp tục tồn tại sau khi quyền thay đổi?

Với ví dụ trong bài, kết quả mong muốn rất cụ thể: A chỉ cập nhật được tồn kho của chào bán thuộc A trong tenant đã xác minh, khi tích hợp và bản ghi còn cho phép; A không thể dùng cùng request để đổi giá đã duyệt, tự phê duyệt hoặc chuyển chủ sở hữu. Những ràng buộc đó phải tiếp tục đúng khi có retry, tranh chấp transaction, webhook đến muộn và thay đổi quan hệ đối tác.
