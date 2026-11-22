# Quản lý mô hình trong kiểm soát phiên bản và rà soát cùng thay đổi mã

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Xem tài liệu mô hình dữ liệu như **một phần của thay đổi phần mềm được kiểm soát phiên bản**, không phải sơ đồ lưu rời rạc sau khi code đã merge.
- Phân biệt các tài liệu **khái niệm, logic, vật lý, mô hình miền, hợp đồng tích hợp và mô hình phân tích**; xác định nguồn có thẩm quyền cho từng loại.
- Lưu và liên kết **định nghĩa grain, thực thể, quan hệ, khóa, ràng buộc, vòng đời, dữ liệu nhạy cảm, chủ sở hữu và quyết định thiết kế** với Java, SQL migration, API/event và metric.
- Thiết kế pull request (PR) mà reviewer đọc được **thay đổi về ý nghĩa nghiệp vụ**, không chỉ diff các dòng DDL hoặc class.
- Tổ chức quy trình **propose → review → merge → deploy → verify** khi nhiều phiên bản ứng dụng, database và consumer cùng tồn tại.
- Kết hợp kiểm tra tự động (docs-as-code, schema migration, contract tests, data quality) với **rà soát chuyên môn của con người**.
- Quản lý ADR, sơ đồ Mermaid, data dictionary, thay đổi không tương thích, drift giữa tài liệu và môi trường thực, kế hoạch chuyển đổi/rollback.
- Áp dụng cách làm tương tự cho lược đồ quan hệ, document, đồ thị và kho phân tích; giải thích vì sao mô hình được duyệt không đồng nghĩa dữ liệu thực tế đã đúng.

Trong module **DATABASE_DATA_MODELING**, thiết kế dữ liệu phải đi từ yêu cầu nghiệp vụ đến thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; sau đó cần đủ rõ để kiểm chứng và tiến hóa. Chương **Tài liệu mô hình** bổ sung một câu hỏi vận hành quan trọng: **khi Java, database, sự kiện hoặc báo cáo thay đổi, làm sao biết tài liệu mô hình vẫn phản ánh đúng sự thật và mọi người đã rà soát cùng một thay đổi?**

Câu trả lời không phải chỉ là đưa ảnh ERD vào Git. Cần một **hợp đồng về cách quản lý các tạo tác mô hình**: tài liệu nào là nguồn có thẩm quyền, thay đổi nào phải đi cùng PR, ai có quyền phê duyệt, tiêu chí nào kiểm tra tự động, và cách biết phiên bản đã triển khai ở môi trường thật. Những thứ đó biến mô hình từ hình vẽ tham khảo thành **kiến thức thiết kế có lịch sử và có trách nhiệm**.

## 1. Vấn đề: code đã đổi nhưng hình vẽ chưa đổi

Giả sử hệ thống bán hàng trước đây giả định **mỗi đơn chỉ có một kiện giao**. Tài liệu cũ vẽ Order — 1:1 — Shipment; lớp Java Order có thể chứa một shipmentId; bảng lưu trữ có cột order_header.delivered_at; sự kiện OrderDelivered mang orderId. Khi doanh nghiệp bắt đầu chia đơn thành nhiều kiện, một thay đổi sơ sài chỉ thêm bảng shipment là chưa đủ:

- **Miền:** một Order có thể có nhiều lần giao, mỗi kiện có vòng đời riêng. Khi nào một Order được coi là giao hoàn tất?
- **Lưu trữ:** Shipment cần danh tính riêng, có quan hệ 1:N với Order. Mỗi ShipmentLine lấy số lượng từ OrderLine; phải tránh phân bổ vượt số đã đặt.
- **Tích hợp:** sự kiện ShipmentDelivered cần shipmentId. Sự kiện OrderDelivered cũ, nếu giữ, phải có nghĩa rõ và thời điểm phát phù hợp.
- **Báo cáo:** số kiện được giao và số đơn giao hoàn tất không còn là cùng một metric.
- **Vận hành:** dữ liệu đơn cũ chỉ có delivered_at có thể không đủ để khôi phục kiện nào đã giao; không được tùy ý bịa lịch sử.

Nếu PR thay đổi Java và SQL nhưng để ERD 1:1, một người viết report mới có thể dùng COUNT(shipment_id) làm số đơn. Nếu chỉ cập nhật ERD mà không có migration và test, ảnh đẹp không làm database chạy đúng.

**Nguyên tắc:** những thứ cùng thay đổi **ngữ nghĩa** cần được xem xét **trong một bối cảnh review thống nhất**, dù được phát hành ở nhiều bước và đôi khi nằm ở các repository khác nhau.

## 2. Mô hình nào cần có tài liệu và đâu là nguồn có thẩm quyền?

| Tầng tài liệu | Câu hỏi cốt lõi | Tạo tác có thể quản lý trong Git | Nguồn có thẩm quyền |
| --- | --- | --- | --- |
| **Khái niệm** | Order, Shipment, Reservation nghĩa gì? Ai sở hữu? | Bản đồ bounded context, thuật ngữ, business rules | Chủ nghiệp vụ/domain owner đã phê duyệt |
| **Logic** | Thực thể nào, quan hệ/cardinality nào, grain nào? | ERD dạng text, data dictionary, invariant | Thiết kế logic đã duyệt |
| **Vật lý** | PK/FK/UNIQUE/CHECK, index, partition, kiểu dữ liệu? | SQL migration, schema definition, physical design note | Migration đã triển khai cùng metadata schema thực tế |
| **Domain Java** | Command nào được phép đổi trạng thái và khi nào? | Aggregate/value object, unit tests, API ứng dụng | Code và quy tắc miền đã duyệt |
| **Trao đổi** | Consumer nhận ID, trạng thái, event và version nào? | OpenAPI/AsyncAPI/JSON schema, contract test | Hợp đồng đã công bố của producer |
| **Phân tích** | Một fact row là gì? Measure và thời gian nào? | Semantic model, metric definition, lineage | Metric owner + pipeline/model version đã công bố |
| **Quyết định** | Vì sao chọn 1:N, bỏ FK xuyên service hay dùng SCD2? | ADR (Architecture Decision Record) | Quyết định có trạng thái và người phê duyệt |

Không có nghĩa **mọi sự thật phải được nhập tay ở bảy nơi**. Nên chọn một nơi làm nguồn và sinh/tổng hợp các góc nhìn khi có thể. Ví dụ DDL migration quản lý cấu trúc cột thực thi; sơ đồ vật lý có thể được sinh từ schema. Nhưng việc một field là **PII**, trạng thái nào được phép chuyển, hoặc OrderDelivered có nghĩa gì thường **không suy ra được** từ DDL và phải được mô tả bằng lời.

### Ba trạng thái thường bị nhầm

1. **Thiết kế mong muốn (proposed/target):** nội dung của nhánh PR, có thể chưa được phê duyệt hoặc triển khai.
2. **Thiết kế đã chấp thuận (approved):** mô hình đã merge hoặc được duyệt, chưa chắc đang tồn tại ở production.
3. **Trạng thái đã triển khai (deployed/observed):** cấu trúc và hợp đồng thực sự chạy ở môi trường cụ thể, có thể khác giữa staging và production.

Không viết trong tài liệu rằng "đã thêm FK" chỉ vì migration nằm trong nhánh đã merge. Muốn biết đã áp dụng, cần metadata migration/deployment và kiểm tra schema thực. **Git commit không phải transaction của database**.

## 3. Cấu trúc tài liệu: tập trung vào tính truy vết, không theo tên công cụ

Một dự án có thể dùng tổ chức tham khảo sau. Đây là **minh họa cấu trúc** để thảo luận, không yêu cầu tạo thêm file ngoài bài hiện tại:

~~~text
repository/
  docs/
    data-model/
      context-map.md             # quyền sở hữu, danh mục ngữ cảnh
      sales/
        glossary.md              # định nghĩa nghiệp vụ
        logical-model.md         # grain, quan hệ, cardinality, bất biến
        physical-model.md        # mapping sang storage
        data-dictionary.md       # cột, NULL, nguồn, độ nhạy cảm
      fulfillment/
        logical-model.md
        data-dictionary.md
      analytics/
        delivery-metrics.md      # metric, grain, timezone, lineage
    adr/
      0042-split-shipments.md    # quyết định thiết kế
  src/main/java/...              # domain Java
  db/migration/...               # migration versioned
  contracts/...                  # API/event schema và test
  tests/...                      # kiểm thử domain, migration, contract
~~~

Không cần sao chép cấu trúc chính xác. Các thuộc tính cần có là:

- **Dễ tìm:** reviewer biết mô hình của bounded context nằm ở đâu, ai chịu trách nhiệm.
- **Dễ diff:** tài liệu ở định dạng text (Markdown, Mermaid, DDL, JSON Schema, YAML) thay đổi theo dòng; hình ảnh xuất ra chỉ là bản xem.
- **Dễ liên kết:** tài liệu mô hình trỏ đến ID quyết định, migration, contract, test và metric liên quan bằng đường dẫn/định danh ổn định.
- **Có lịch sử:** xem lại ai thay đổi ý nghĩa grain, vì sao, ngày nào và đi cùng phiên bản nào.
- **Không nhân đôi quyền quyết định:** nếu schema tool sinh DDL, ghi rõ tool/schema nào là nguồn, thay vì có cả file thiết kế, file SQL và tài liệu thủ công cùng được coi là nguồn gốc mà không có thứ tự ưu tiên.
- **Không trộn môi trường:** đường dẫn hoặc ảnh schema production không thể được dùng như thiết kế target khi bản mới chưa deploy.

### Một hồ sơ mô hình tối thiểu

Cho mỗi mô hình quan trọng, tài liệu nên trả lời được:

| Trường | Ví dụ | Lý do |
| --- | --- | --- |
| Model ID | fulfillment.shipment | Tra cứu và liên kết ổn định |
| Business owner | Nhóm điều hành giao hàng | Phê duyệt ý nghĩa |
| Technical owner | Nhóm Fulfillment | Chịu trách nhiệm triển khai |
| Status | proposed / approved / deployed | Không nhầm kế hoạch với hiện trạng |
| Grain | Một lần xử lý giao một kiện | Tránh đếm nhầm |
| Identity | (tenantId, shipmentId) | Retry, liên kết, phân vùng danh tính |
| Cardinality | Order 1:N Shipment | Kiểm tra đường nối |
| Invariants | Tổng số lượng phân bổ không vượt OrderLine | Xác định transaction/source-of-truth |
| Sensitive data | Địa chỉ nhận hàng, người nhận | ACL, retention, tối thiểu hóa dữ liệu |
| Temporal meaning | deliveredAt là khi giao thành công | Tránh nhầm với publishedAt |
| Related artifacts | ADR-0042, migration, event schema, test | Truy vết thay đổi |
| Compatibility | Có old writer và consumer v1 đến mốc X | Lập kế hoạch rollout |

**Version của tài liệu không phải số tăng tự do.** Có thể dùng commit hash, tag phát hành, migration version và event schemaVersion cho các mục đích khác nhau. Quan trọng hơn là chỉ ra được một cấu hình **đã dùng những phiên bản nào cùng nhau**.

## 4. Ví dụ mô hình logic: từ một kiện sang nhiều kiện

Yêu cầu đã được làm rõ với nghiệp vụ:

- Một Order có thể được xử lý thành nhiều Shipment.
- Một Shipment có các ShipmentLine; mỗi line trỏ tới OrderLine nguồn bằng định danh ổn định và mang quantity dương.
- Shipment có trạng thái REQUESTED, PACKED, DISPATCHED, DELIVERED hoặc CANCELLED theo vòng đời phù hợp.
- **Fulfillment** quản lý Shipment và phân bổ lượng hàng cho các Shipment; **Sales** quản lý Order. Hai ngữ cảnh trao đổi bằng ID và contract, không cho Fulfillment sửa tùy ý Order status.
- Tổng quantity được phân bổ vào các Shipment đang có hiệu lực cho một OrderLine **không vượt quantity đặt** theo chính sách phân bổ; cần một điểm cấp quyền/transaction có thẩm quyền.
- Order chỉ được gọi là **giao hoàn tất** theo điều kiện đã thống nhất (ví dụ mọi số lượng cần giao đã được giao thành công, không có yêu cầu còn mở). Không suy từ việc tồn tại một Shipment có deliveredAt.

### Sơ đồ logic cũ và mới trong PR

~~~mermaid
flowchart LR
    subgraph Old["Trước thay đổi"]
        O1["Order<br/>shipmentId? / deliveredAt?"]
        S1["Shipment<br/>tối đa một cho Order"]
        O1 ---|"0..1"| S1
    end
    subgraph New["Sau thay đổi"]
        O2["Order<br/>Sales context"]
        S2["Shipment<br/>Fulfillment context"]
        SL["ShipmentLine<br/>quantity, orderLineId"]
        O2 ---|"0..N"| S2
        S2 ---|"1..N"| SL
    end
~~~

**Chú ý cardinality:** ví dụ này cho phép Order chưa được tạo Shipment (0..N) và mỗi Shipment đang xử lý có ít nhất một dòng (1..N). Những quy tắc như Shipment DRAFT có thể tạm rỗng phải được hỏi lại; nếu có, chú thích 0..N cho giai đoạn DRAFT hoặc phân biệt trạng thái. Không vẽ 1..N khi domain thực tế cho phép chưa có dòng.

Đây là **mô hình logic**, không quyết định ngay rằng cần một FK xuyên database từ Shipment đến Sales.Order. Quan hệ 1:N được định nghĩa bằng ngữ nghĩa và ID; khả năng FK thực thi phụ thuộc ranh giới lưu trữ.

### Bảng từ điển cho mô hình mới

| Khái niệm/field | Ý nghĩa và grain | Ràng buộc / nguồn quyết định |
| --- | --- | --- |
| OrderId | Định danh đơn của Sales | Duy nhất trong tenant theo Sales |
| ShipmentId | Định danh một kiện/lần xử lý giao | Fulfillment cấp, không đồng nhất OrderId |
| Shipment.orderId | Tham chiếu Order nguồn | Không tự trao quyền sửa Order |
| ShipmentLine.orderLineId | Tham chiếu dòng mua nguồn | Phải tra mapping có thẩm quyền |
| ShipmentLine.quantity | Số lượng được phân bổ cho kiện | >0; tổng nhiều kiện được kiểm soát bởi allocation owner |
| Shipment.status | Vòng đời của kiện | Có tập transition hợp lệ |
| Shipment.deliveredAt | Mốc đã giao thành công một kiện | NULL nếu chưa giao; không thay bằng ingest time |
| OrderDeliveryComplete | Sự thật hoàn tất cấp Order | Chỉ công bố khi điều kiện hoàn tất *tất cả phần phải giao* đạt |
| ShipmentDelivered | Sự thật giao thành công một kiện | Có shipmentId, orderId, eventId, schemaVersion |

Từ điển giải thích **nghĩa** của dữ liệu. DDL sẽ bảo vệ một phần như NOT NULL, CHECK, FK nội bộ; quy tắc tổng phân bổ qua nhiều Shipment có thể cần transaction/aggregate hoặc ledger của Fulfillment, không biến mất chỉ vì ERD có đường nối đúng.

## 5. Tài liệu vật lý đi cùng migration: điều gì được database bảo vệ?

Giả sử Shipment được lưu riêng trong PostgreSQL của Fulfillment, còn Order thuộc Sales. Một migration **đề xuất** có thể là:

~~~sql
CREATE SCHEMA IF NOT EXISTS fulfillment;

CREATE TABLE fulfillment.shipment (
    tenant_id UUID NOT NULL,
    shipment_id UUID NOT NULL,
    order_id UUID NOT NULL,  -- external reference tới Sales
    status VARCHAR(16) NOT NULL
        CHECK (status IN (
            'REQUESTED', 'PACKED', 'DISPATCHED',
            'DELIVERED', 'CANCELLED'
        )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dispatched_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, shipment_id),
    CHECK (status <> 'DELIVERED' OR delivered_at IS NOT NULL),
    CHECK (delivered_at IS NULL OR delivered_at >= created_at)
);

CREATE TABLE fulfillment.shipment_line (
    tenant_id UUID NOT NULL,
    shipment_id UUID NOT NULL,
    shipment_line_no INTEGER NOT NULL CHECK (shipment_line_no > 0),
    order_line_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, shipment_id, shipment_line_no),
    FOREIGN KEY (tenant_id, shipment_id)
        REFERENCES fulfillment.shipment(tenant_id, shipment_id),
    UNIQUE (tenant_id, shipment_id, order_line_id)
);

CREATE INDEX shipment_by_order
    ON fulfillment.shipment (tenant_id, order_id, created_at DESC);

CREATE INDEX shipment_open_by_status
    ON fulfillment.shipment (tenant_id, status, created_at)
    WHERE status NOT IN ('DELIVERED', 'CANCELLED');
~~~

**Tài liệu review cần nói điều mà DDL không nói được:**

- DDL bảo vệ một Shipment có ID duy nhất và dòng con phải thuộc Shipment tồn tại trong cùng database.
- Không có FK từ Fulfillment sang Sales.Order, vì hai ngữ cảnh có thể ở hai database. Cần **hợp đồng xác minh orderId/orderLineId**, quyền tenant, xử lý Order bị xóa và event đến muộn.
- UNIQUE trên (tenant, shipment, orderLineId) ngăn lặp một OrderLine trong cùng Shipment theo chính sách ví dụ. Nó **không ngăn** cùng OrderLine xuất hiện ở hai Shipment với tổng quantity vượt số đặt.
- CHECK trạng thái và timestamp chưa bảo vệ mọi đường chuyển trạng thái, như DELIVERED không được quay lại PACKED. Root/domain và lệnh UPDATE có điều kiện/version phải bảo vệ.
- Nếu một ShipmentLine cần nhiều lô hàng cùng OrderLine trong **một Shipment**, UNIQUE nói trên có thể không phù hợp; phải làm rõ grain trước khi giữ constraint.
- Partial index cho shipment đang mở chỉ là một ứng viên theo truy vấn dự kiến; đo thực tế trước khi kết luận tối ưu.

### Bảo vệ phân bổ không vượt lượng đặt

Để chứng minh không phân bổ vượt OrderLine, mô hình cần ghi rõ **ai là điểm phân xử**. Ví dụ Fulfillment sở hữu một allocation ledger theo (tenantId, orderLineId), trong đó lượng đã phân bổ còn hiệu lực được kiểm tra/điều chỉnh nguyên tử khi tạo hoặc hủy Shipment. Một phương án SQL minh họa:

~~~sql
CREATE TABLE fulfillment.order_line_allocation (
    tenant_id UUID NOT NULL,
    order_line_id UUID NOT NULL,
    allowed_quantity INTEGER NOT NULL CHECK (allowed_quantity > 0),
    allocated_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (allocated_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, order_line_id),
    CHECK (allocated_quantity <= allowed_quantity)
);

-- Transaction của lệnh AllocateToShipment:
UPDATE fulfillment.order_line_allocation
SET allocated_quantity = allocated_quantity + :quantity,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND order_line_id = :order_line_id
  AND :quantity > 0
  AND allocated_quantity <= allowed_quantity - :quantity
RETURNING allocated_quantity;

-- Chỉ khi UPDATE trả đúng một hàng, trong cùng transaction mới
-- INSERT shipment_line. Nếu không, ROLLBACK toàn bộ lệnh.
~~~

**Giả định của ví dụ:** allowed_quantity được nhận từ snapshot/order contract đã được Sales xác nhận và do Fulfillment duy trì theo một giao thức sở hữu rõ. Khi Sales điều chỉnh/hủy OrderLine, hệ thống phải có quy trình reconcile/điều chỉnh phần đã phân bổ; kiểm tra cột này **không tự đồng bộ** với Sales ở database khác.

Tại thời điểm review, cần phân biệt:

1. **Bất biến:** tổng phân bổ không vượt mức cho phép.
2. **Chiến lược thực hiện:** một hàng allocation được UPDATE có điều kiện trong transaction nội bộ.
3. **Tiền đề:** allowed_quantity đúng, request có idempotency, các lệnh giải phóng không trừ hai lần.
4. **Bằng chứng:** integration test hai request cùng xin phần hàng cuối, test rollback khi INSERT ShipmentLine lỗi, test retry và test Sales giảm quantity.

Một sơ đồ có đường nối đẹp không thay được bốn câu trả lời trên.

## 6. Tạo semantic diff: review ý nghĩa, không chỉ câu ALTER TABLE

Git diff cho biết dòng văn bản nào thay đổi, nhưng **không tự diễn giải tác động nghiệp vụ**. Một PR đổi cardinality cần có bản tóm tắt:

| Khía cạnh | Trước | Sau | Tác động/khả năng tương thích |
| --- | --- | --- | --- |
| Quan hệ Order–Shipment | Tối đa một Shipment/Order | 0..N Shipment/Order | Client không được giả định một shipmentId |
| Định danh giao hàng | orderId đủ để tìm kiện | Cần shipmentId riêng | Event, URL, idempotency key đổi |
| Trạng thái giao | deliveredAt ở cấp Order | deliveredAt ở cấp Shipment, Order tổng hợp | Không thể dùng một timestamp cũ để diễn đạt mọi kiện |
| Phân bổ hàng | Ngầm toàn đơn một kiện | Nhiều ShipmentLine tham chiếu OrderLine | Thêm bất biến chống phân bổ vượt |
| REST response | shipment object đơn | shipments collection hoặc endpoint riêng | Có thể là breaking change |
| Event | OrderDelivered | ShipmentDelivered và/hoặc OrderDeliveryCompleted | Hai sự thật khác nhau, không đổi tên mù quáng |
| KPI | Số đơn đã giao | Số kiện đã giao và số đơn hoàn tất | Grain và phép đếm phải tách |
| Lịch sử dữ liệu | Một deliveredAt | Không biết chi tiết các kiện cũ | Chỉ backfill khi có chứng cứ |
| Quyền sở hữu | Sales có thể giữ deliveredAt | Fulfillment giữ state Shipment | Cấm shared write |

**Semantic diff** cũng cần cho thay đổi nhỏ hơn như:

- Đổi NULL từ "chưa biết" sang "không áp dụng".
- Đổi trạng thái PAID từ "ủy quyền" sang "đã thu tiền".
- Đổi tiền từ đồng sang nghìn đồng hoặc thay timezone nhóm ngày.
- Đổi tên cột nhưng đổi luôn phạm vi nghiệp vụ.
- Đổi grain fact từ "một đơn" sang "một kiện".
- Thêm UNIQUE có thể từ chối dữ liệu lịch sử hợp lệ.
- Đổi chiều document nhúng thành collection riêng với khác biệt về atomicity.

Một thay đổi chỉ thêm cột nullable có thể **phá hợp đồng** nếu tác dụng của nó khiến một field cũ đổi nghĩa. Ngược lại, đổi tên cột nội bộ có thể không ảnh hưởng API nếu repository và contract được tách đúng.

### Phân loại change để chọn mức review

| Loại thay đổi | Ví dụ | Reviewer chính |
| --- | --- | --- |
| Hiển thị/tài liệu không đổi nghĩa | Sửa lỗi chính tả field description | Chủ tài liệu/technical owner |
| Bổ sung tương thích | Thêm trường optional có nghĩa rõ, index mới | Domain owner + DB owner |
| Thay bất biến/cardinality | 1:N Shipment, đổi quy tắc allocation | Business owner + domain + data/DB |
| Thay contract công khai | Đổi payload, enum, đơn vị tiền | Producer + consumer representatives |
| Thay grain/KPI | Tách số kiện và số đơn | Data/BI owner + nghiệp vụ |
| Thay bảo mật/vòng đời dữ liệu | Thêm địa chỉ giao, đổi retention | Security/privacy + data owner |
| Breaking migration | Xóa field, đổi kiểu dữ liệu, sửa PK | DB/platform + mọi owner phụ thuộc |

Không phải mọi PR cần họp toàn công ty. Nhưng mỗi thay đổi **có tác động ngữ nghĩa** phải được người **chịu trách nhiệm về ý nghĩa đó** rà soát.

## 7. Pull request là gói bằng chứng thay đổi mô hình

Một PR tốt trả lời **vì sao thay**, **thay điều gì**, **ảnh hưởng ai**, **triển khai và kiểm chứng thế nào**. Mẫu minh họa:

~~~markdown
# PR: Cho phép một Order được chia nhiều Shipment

## Bối cảnh và quyết định
- Yêu cầu: giao một đơn theo nhiều kho/đợt.
- Business owner: Fulfillment.
- Quyết định: ADR-0042; Order 0..N Shipment.
- Out of scope: gộp đơn của nhiều khách vào một Shipment.

## Thay đổi mô hình
- Domain: ShipmentId riêng; quyền phân bổ thuộc Fulfillment.
- Logic: quan hệ 1:N; ShipmentLine tham chiếu OrderLine.
- Storage: thêm shipment, shipment_line, allocation.
- Exchange: ShipmentDeliveredV1, phiên bản API theo chính sách.
- Analytics: tách shipment_count và completed_order_count.

## Tương thích và dữ liệu cũ
- Old writer nào đang chạy?
- Old readers có đọc được dữ liệu nhiều kiện không?
- Có backfill được lịch sử không? Dữ liệu nào phải UNKNOWN?
- Khi nào mới được xóa field legacy?

## Triển khai và kiểm chứng
- Expand schema -> deploy readers/writers -> feature gate.
- Test concurrency, retry, migration, contract, KPI đối soát.
- Chỉ số giám sát và ngưỡng rollback/roll-forward.
- Chứng cứ môi trường thử: migration version, test run, query diff.

## Rà soát
- [ ] Business/domain owner
- [ ] DB/platform owner
- [ ] API/event consumer owners
- [ ] Analytics/metric owner
- [ ] Security/privacy nếu có thay đổi dữ liệu nhạy cảm
~~~

**Lưu ý:** các dấu checkbox trong PR không phải bằng chứng tự động rằng người có trách nhiệm thực sự đã duyệt. Hãy dùng CODEOWNERS, branch protection, review approvals và dấu vết quyết định theo quy trình của tổ chức. Một ô checkbox do tác giả tự tick không thay thế phê duyệt độc lập.

### Những file nên đi cùng nhau trong thay đổi

Khi thay đổi quan hệ và bất biến, thường cần các nhóm tạo tác tương ứng:

- **Thiết kế:** ERD/diagram dạng text, data dictionary, business glossary, ADR.
- **Thực thi:** class Java/domain behaviors, repository mapper, SQL migration hoặc document schema.
- **Giao tiếp:** request/response schema, integration event schema, versioning/changelog.
- **Phân tích:** fact grain, dim mapping, metric definition, view/semantic layer.
- **Kiểm thử:** domain unit test, DB integration test, contract test, migration test, dữ liệu chất lượng.
- **Triển khai:** kế hoạch feature flag, backfill, monitoring, rollback/roll-forward.

Không nhất thiết tất cả ở **một commit nguyên tử** nếu làm như vậy không thể triển khai an toàn. Một **initiative/issue chung** có thể liên kết nhiều PR tăng dần; mỗi PR phải an toàn đối với các phiên bản đang chạy và chỉ rõ bước tiếp theo.

## 8. ADR: lưu lý do, không chỉ kết quả

Một tài liệu sơ đồ trả lời **đã thiết kế thế nào**; ADR giải thích **vì sao chọn như vậy khi còn lựa chọn khác**. Ví dụ:

~~~markdown
# ADR-0042: Fulfillment sở hữu Shipment và phân bổ hàng
Status: Accepted
Date: 2026-11-22
Decision owners: Sales, Fulfillment, Data Platform

## Context
Một Order có thể chia nhiều kiện; Sales và Fulfillment
có database riêng. Cần không phân bổ quá lượng đã đặt.

## Decision
- Shipment có shipmentId riêng và orderId tham chiếu.
- Fulfillment sở hữu allocation ledger.
- Sales không ghi trực tiếp bảng Shipment.
- ShipmentDelivered là sự thật cấp kiện.
- OrderDeliveryCompleted có tiêu chí hoàn tất riêng.

## Alternatives
1. Gắn mảng shipments vào Order aggregate.
2. Shared database và FK/transaction xuyên hai context.
3. Fulfillment quản lý Shipment và giao tiếp bằng contract.

## Consequences
- Có trạng thái tạm/chờ, retry và eventual consistency.
- Phải xử lý Order đổi/hủy khi đang có Shipment.
- Báo cáo phải tách metric Order và Shipment.

## Validation
- Race test phần hàng cuối.
- Event contract tests và replay.
- Migration/backfill đối soát dữ liệu lịch sử.
~~~

Tài liệu ADR có thể có trạng thái **Proposed, Accepted, Superseded, Rejected**. Khi đổi quyết định, nên tạo ADR mới liên kết ADR cũ hoặc ghi quan hệ **Superseded by** theo quy trình; không sửa lặng lẽ phần bối cảnh rồi làm như quyết định mới đã tồn tại từ đầu.

ADR không thay mọi thông tin ở data dictionary. Một quyết định 1:N có thể chỉ cần ADR một lần; các cột, kiểu dữ liệu và index vẫn được bảo trì ở hồ sơ mô hình/schema phù hợp.

## 9. Git workflow: version của thiết kế không phải version của database

Một luồng thực hành:

1. Tạo issue và xác nhận phạm vi nghiệp vụ, owner, người tiêu thụ dữ liệu.
2. Viết **model change proposal** và semantic diff trên nhánh tính năng; thảo luận trước những thay đổi khó đảo ngược.
3. Bổ sung migration, Java, contract, tài liệu và kiểm thử cho **một bước triển khai an toàn**.
4. Chạy kiểm tra tự động, review theo owner, giải quyết bình luận ngay trong PR.
5. Merge sau khi đạt điều kiện review; đánh dấu bước nào vẫn **chưa triển khai**.
6. Deploy theo thứ tự tương thích, chạy migration có kiểm soát, đối soát kết quả.
7. Ghi lại migration version, artifact version, schema contract version và thời điểm triển khai.
8. Quan sát và xử lý sai khác; cập nhật trạng thái tài liệu theo bản thật sự đang chạy.

### Một bản thay đổi có nhiều đồng hồ phiên bản

| Định danh | Nó phiên bản hóa cái gì? | Ví dụ |
| --- | --- | --- |
| Git commit SHA | Nội dung source/docs tại một commit | Commit C123 |
| Application build/release | Binary triển khai | sales-service 4.2 |
| DB migration version | Bước biến đổi cấu trúc/dữ liệu | V0042_create_shipments |
| Database schema thực tế | Những constraint/table/index đã có | Kiểm tra qua catalog/migration history |
| API/event schemaVersion | Hợp đồng consumer đọc | ShipmentDelivered v1 |
| Analytics transformVersion | Logic nạp fact/metric | fulfillment-mart v3 |
| ADR ID/status | Quyết định và lịch sử thay thế | ADR-0042 Accepted |

**Không dùng một số version cho mọi lớp.** Một commit có thể chứa nhiều migration; một API v1 có thể sống qua nhiều release; một event v2 có thể được hỗ trợ đồng thời với v1; một data mart có thể rebuild bằng transform mới dù bảng nguồn không đổi.

Để tái lập một báo cáo hoặc điều tra incident, cần biết **bản ứng dụng, migration, event schema, pipeline và định nghĩa metric** đã có hiệu lực khi đó. Git history chỉ là một phần của bằng chứng ấy.

### Nguyên tắc với pull request lớn

Nếu PR gồm hàng trăm thay đổi không liên quan, khó chứng minh kết quả. Có thể tách thành chuỗi PR:

- **PR A — mở rộng tương thích:** thêm bảng/field, reader hỗ trợ cả hai dạng.
- **PR B — backfill và đối soát:** nạp dữ liệu cũ với quy tắc có căn cứ.
- **PR C — bật chức năng:** ghi dữ liệu mới, phát event/metric mới.
- **PR D — dọn cấu trúc cũ:** chỉ khi không còn dependency.

Các PR vẫn cùng liên kết một issue/ADR và có kế hoạch triển khai thống nhất. Không xóa constraint hoặc cột cũ trong PR A nếu old binary còn chạy.

## 10. Tài liệu như mã nguồn: những điều CI có thể kiểm tra

**Docs-as-code** nghĩa là tài liệu tham gia cùng vòng đời version control, review, build và phát hành với code. Nó không có nghĩa mọi tính đúng nghiệp vụ đều được kiểm chứng tự động.

Một pipeline kiểm tra tham khảo:

~~~mermaid
flowchart LR
    PR["Pull request"] --> L["Markdown + links + diagram lint"]
    PR --> M["SQL migration<br/>schema diff / dry run"]
    PR --> C["Java + contract tests"]
    PR --> T["Data/metric tests"]
    L --> G{"Automated gates PASS?"}
    M --> G
    C --> G
    T --> G
    G -->|"Có"| R["Owner review<br/>ngữ nghĩa + rủi ro"]
    G -->|"Không"| F["Sửa và chạy lại"]
    R --> A["Approval + merge"]
~~~

Các nhóm kiểm tra:

| Cổng | Có thể kiểm tra tự động | Phần vẫn cần reviewer |
| --- | --- | --- |
| Markdown/diagram | Link chết, cú pháp, heading ID, Mermaid render | Sơ đồ 1:N có đúng yêu cầu? |
| Metadata mô hình | Thiếu owner, status, grain, tham chiếu ADR | Owner có đúng trách nhiệm không? |
| SQL migration | Cú pháp, thứ tự migration, DDL chạy trên DB thử, diff schema | Backfill có làm mất lịch sử hoặc quá tải production không? |
| Schema constraints | Có PK/FK/UNIQUE/CHECK dự kiến; migration chống dữ liệu bẩn | Constraint có cấm tình huống hợp lệ? |
| Java tests | Bất biến, lỗi biên, optimistic lock với DB thật | Root sở hữu đúng quy tắc nghiệp vụ? |
| API/event contract | Field/type/schema compatibility, consumer tests | Event có còn cùng nghĩa? |
| Data pipeline | Grain uniqueness, NOT NULL, quan hệ, giá trị đối soát | KPI có cùng định nghĩa với bên nghiệp vụ? |
| Security check | Dữ liệu nhạy cảm bị công bố rõ trong schema/contract | Quyền truy cập và retention có phù hợp mục đích? |

### Mẫu khai báo cổng logic

Không cần phụ thuộc vào một công cụ CI cụ thể. Một mô tả có thể viết:

~~~yaml
# Ví dụ ý tưởng workflow; tên job/command cần ánh xạ vào dự án thực.
model_change_checks:
  required:
    - markdown_and_link_validation
    - diagram_render_validation
    - migration_on_disposable_database
    - migration_schema_diff
    - domain_unit_tests
    - database_concurrency_tests
    - api_event_contract_compatibility
    - analytical_grain_and_metric_tests
  human_approvals:
    - fulfillment_domain_owner
    - database_owner
    - integration_consumer_owner
    - analytics_metric_owner
~~~

Đây là **checklist minh họa**, không phải cú pháp của GitHub Actions/GitLab CI hoặc hệ thống pipeline bất kỳ. Khi triển khai thực, cần dùng đúng runner, xác thực, test database và artifact thực tế.

### Sơ đồ nên là source text hay file ảnh?

Ưu tiên lưu **sơ đồ dưới dạng text** như Mermaid/PlantUML/DBML khi phù hợp để:

- So sánh diff từng quan hệ/cardinality qua Git.
- Render lại khi thay chủ đề/giao diện.
- Kiểm tra cú pháp trong CI.
- Liên kết với data dictionary và PR.

Ảnh PNG có thể phục vụ người đọc, nhưng nếu nó là **nguồn duy nhất** thì reviewer khó nhận ra quan hệ nào vừa đổi; ảnh dễ không cập nhật khi code đổi. Ngược lại, một sơ đồ sinh tự động từ database chỉ thể hiện những gì database biết, không tự biết rule nghiệp vụ, bounded context và event contract.

**Vì vậy, không có "một diagram duy nhất thay tất cả tài liệu".** Giữ mô hình logic có ý nghĩa và sinh mô hình vật lý từ schema khi có công cụ tin cậy; chỉ rõ quan hệ giữa chúng.

## 11. Rà soát phải gắn với hành vi đồng thời và dữ liệu lịch sử

Trong ví dụ Shipment, reviewer không chỉ xác nhận bảng có khóa chính, mà còn hỏi điều gì xảy ra khi hai worker cùng phân bổ số lượng cuối.

### Kịch bản tranh chấp

OrderLine L có allowedQuantity=5, đã allocated=3. Hai request độc lập đồng thời xin phân bổ thêm quantity=2 cho hai Shipment khác nhau.

Nếu code làm:

~~~text
SELECT allocated_quantity  -- cả A và B đều thấy 3
IF 3 + 2 <= 5:
    INSERT shipment_line    -- A chèn 2, B cũng chèn 2
    UPDATE allocated_quantity ...
~~~

mà không có khóa/version/giao dịch đúng, có thể cấp tổng 7 đơn vị cho mức cho phép 5.

Một lệnh UPDATE có điều kiện trên **cùng hàng ledger** kết hợp INSERT dòng kiện trong **cùng transaction** cho phép chỉ một request vượt qua khi đã có cạnh tranh. Với cơ chế PostgreSQL phù hợp, request thứ hai phải đánh giá lại điều kiện sau khi request đầu commit; không chỉ dựa trên SELECT đọc cũ.

### Kết quả test cần đưa vào PR

| Test | Thiết lập | Điều kiện PASS |
| --- | --- | --- |
| Hai request tranh chấp | allocated=3, allowed=5, mỗi request xin 2 | Chỉ một phân bổ 2 thành công |
| Lỗi sau UPDATE ledger | Giả lập INSERT shipment_line thất bại | Rollback cập nhật ledger |
| Retry cùng requestId | Lặp command đã thành công | Không tạo ShipmentLine hoặc phân bổ thứ hai |
| Hủy một Shipment | Gửi Cancel hai lần | Ledger giải phóng đúng một lần |
| Sales giảm quantity | allowed_quantity từ 5 xuống 4 sau khi đã phân bổ 5 | Có workflow từ chối/điều chỉnh, không ép CHECK bằng cách xóa dữ liệu |
| Sai tenant | shipmentId của tenant A được dùng bởi B | Bị từ chối |
| OrderLine tham chiếu không tồn tại | Event/command đến trước dữ liệu nguồn | Đợi/đối soát hoặc lỗi hợp đồng, không tạo giả dữ liệu |

**Một mock repository tuần tự không chứng minh đã chống race condition.** Test đồng thời cần dùng DB thật hoặc môi trường có isolation/lock semantics tương đương và phải kiểm tra trạng thái sau commit, không chỉ status HTTP.

### Tài liệu mô hình phải giải thích ngoại lệ

Nếu OrderLine được phép phân bổ quá quantity một cách chủ ý trong nghiệp vụ đặt trước hàng sẽ về, constraint allocated≤allowed không còn hợp lệ. Reviewer cần xác định chính sách **over-allocation** trước khi áp CHECK; không sửa rule một cách bí mật để vượt test.

Nếu Shipment có thể bị mở lại hoặc chuyển ngược từ DELIVERED sang RETURNED, một state machine chỉ có DELIVERED là điểm kết thúc sẽ thiếu dữ liệu. Tài liệu nên ghi **trạng thái được hỗ trợ và trường hợp ngoại lệ**, rồi mới viết enum/constraint.

## 12. Version hợp đồng tích hợp và mô hình báo cáo trong cùng review

Giả sử event cũ **OrderDelivered** có payload:

~~~json
{
  "eventType": "sales.order-delivered",
  "schemaVersion": 1,
  "eventId": "0f9cd680-b371-4d67-95b3-2e6092814ced",
  "tenantId": "76cf77e5-a024-4e2d-8e2b-fb571b6416ad",
  "orderId": "e99b0311-3c0a-45f2-bb59-a2be1bb29f47",
  "deliveredAt": "2026-11-02T10:00:00Z"
}
~~~

Sau khi hỗ trợ nhiều kiện, một sự thật mới **ShipmentDelivered** có thể là:

~~~json
{
  "eventType": "fulfillment.shipment-delivered",
  "schemaVersion": 1,
  "eventId": "f4f5ed38-4a6d-4711-a9ae-2a868ad0baf6",
  "tenantId": "76cf77e5-a024-4e2d-8e2b-fb571b6416ad",
  "orderId": "e99b0311-3c0a-45f2-bb59-a2be1bb29f47",
  "shipmentId": "0e4ea4f8-dff9-4950-bc8c-388f219dce14",
  "deliveredAt": "2026-11-02T10:00:00Z"
}
~~~

Hai JSON không thể được coi là tương đương chỉ vì cùng có deliveredAt:

- **OrderDelivered** trước đây có thể được hiểu là **toàn bộ Order đã giao**.
- **ShipmentDelivered** chỉ chứng minh **một Shipment** đã được giao, không chứng minh phần hàng còn lại đã giao.
- Đổi eventType mà giữ payload giống nhau không giữ được nghĩa cũ.
- Nếu vẫn phục vụ consumer v1, một workflow riêng phải chỉ công bố **OrderDeliveryCompleted** sau khi điều kiện hoàn tất cấp Order thực sự đúng, hoặc có adapter với hợp đồng đúng, thay vì gửi OrderDelivered mỗi khi một Shipment thành công.
- **eventId** định danh một sự thật đã xảy ra, không được tạo mới cho mỗi lần broker redelivery; phải thiết kế dedup và thứ tự trong phạm vi stream.

### Mô hình phân tích không được đổi grain mà giữ nguyên tên metric

Một fact cho Shipment đã giao có grain **một Shipment delivered**. Một fact hoặc projection hoàn tất Order có grain **một Order delivery completed**. Truy vấn:

~~~sql
-- Giả định mart.fact_delivered_shipment có đúng một hàng mỗi Shipment.
SELECT delivery_business_date,
       COUNT(*) AS delivered_shipments,
       COUNT(DISTINCT order_id) AS orders_with_a_delivered_shipment
FROM mart.fact_delivered_shipment
WHERE tenant_id = :tenant_id
  AND delivery_business_date >= DATE '2026-11-01'
  AND delivery_business_date <  DATE '2026-12-01'
GROUP BY delivery_business_date
ORDER BY delivery_business_date;
~~~

**orders_with_a_delivered_shipment không phải số Order đã giao hoàn tất.** Một Order có hai kiện, mới giao một kiện, vẫn được đếm vào cột đó. Muốn số Order hoàn tất, cần nguồn có thẩm quyền xác định **toàn bộ số lượng cần giao đã hoàn thành** và ghi nhận sự kiện/trạng thái cấp Order riêng.

Nếu một Order có Shipment giao vào ngày 02/11 và kiện khác ngày 03/11, số Order có kiện giao được tính **ở cả hai ngày**; cộng COUNT(DISTINCT order_id) theo ngày không cho số Order duy nhất cả tháng. Reviewer phải thấy rõ cách tính này trong semantic diff để tránh dashboard sai.

### Chốt hợp đồng với consumer và BI

Trong PR hoặc issue liên kết, cần xác định:

- Consumer nào đang nhận OrderDelivered v1, còn phụ thuộc những field/trạng thái nào?
- Producer có tiếp tục gửi event v1 đúng nghĩa hay phải công bố hợp đồng mới?
- Khi tính lại lịch sử, có những event cũ nào không đủ shipmentId và phải giữ giá trị unknown?
- BI có thay denominator/cohort/đơn vị thời gian không?
- Khi nâng report, lưu metricVersion và ngày hiệu lực, có cần phát hành lại số liệu đã công bố không?

**Thêm một field trong JSON có thể tương thích về cú pháp nhưng không đảm bảo tương thích về ý nghĩa.** Tính đúng không dừng tại schema registry.

## 13. Kiểm chứng thay đổi trên cả bốn lớp

Một PR về mô hình tốt nên kèm **ma trận kiểm thử nối các lớp**:

| Lớp | Kiểm tra | Ví dụ bằng chứng |
| --- | --- | --- |
| **Domain Java** | Không tạo Shipment rỗng khi trạng thái không cho phép; transition hợp lệ | Unit/property tests |
| **Database** | PK/FK, CHECK, rollback, tranh chấp, hiệu năng index | Integration tests + query plan |
| **Mapper** | Đọc dữ liệu legacy và mới, giữ identity/tenant/NULL đúng | Round-trip tests |
| **API** | Một Order nhiều Shipment có response không mơ hồ | Consumer-driven contract tests |
| **Event** | ShipmentDelivered không bị hiểu là OrderDelivered | Contract + semantic scenarios |
| **Pipeline** | Event trùng/đến muộn không nhân fact | Replay/idempotency tests |
| **Analytics** | Số Shipment và Order hoàn tất đúng grain | Metric reconciliation |
| **Security** | Tenant A không đọc/ghi Shipment của tenant B | Authorization tests |
| **Migration** | Dữ liệu cũ giữ nguyên nghĩa, không mất lịch sử | Backfill report + diff |
| **Operations** | Schema mới vẫn chạy khi old/new binaries cùng tồn tại | Mixed-version integration |

Không phải mọi thay đổi cần triển khai đủ tất cả loại test. Nhưng **thay đổi có ảnh hưởng tới lớp nào thì phải có cách chứng minh lớp đó đúng**. Một bản mô hình được duyệt về khái niệm chưa chứng minh DDL chạy đúng trên PostgreSQL hay fact ETL không nhân dòng.

### Báo cáo kiểm tra bằng số liệu cụ thể

Một số cổng minh họa:

- **Định danh:** COUNT(DISTINCT (tenantId, shipmentId)) đúng số Shipment, không có duplicate business key.
- **Tính hợp lệ:** số ShipmentLine quantity≤0 bằng 0.
- **Giới hạn phân bổ:** không có OrderLine mà số phân bổ đang hiệu lực vượt allowedQuantity.
- **Đầy đủ migration:** số Order legacy được phân loại rõ thành backfilled, skipped có lý do hoặc cần đối soát; không biến skipped thành "không có dữ liệu".
- **Contract:** producer event v1/v2 được test với consumer hoặc schema fixture được hỗ trợ.
- **Độ tươi:** projection phục vụ BI có watermark và xử lý late data, không công bố số tạm như số đã chốt.
- **Tính không đổi tổng:** khi chuyển đổi cách nhóm, số kiện/đơn được đối soát theo đúng grain; không giả định phải bằng nhau.

Với hệ thống lớn, threshold cần được **chốt theo rủi ro**. Ví dụ chênh lệch một đồng ở dữ liệu thanh toán không nên được coi là chấp nhận được chỉ vì tỷ lệ so với tổng toàn tháng rất nhỏ; trong khi độ trễ nạp một sự kiện BI có thể được cho phép trong SLA đã công bố.

## 14. Phát hiện drift: tài liệu, migration và môi trường không phải một

**Model drift** xảy ra khi một hoặc nhiều biểu diễn không còn khớp ý nghĩa hoặc cấu trúc được duyệt:

- Một người tạo index trực tiếp trên production nhưng không có migration trong Git.
- DDL đã merge nhưng migration failed trên một môi trường.
- ORM tự thay schema lúc khởi động ngoài quy trình migration.
- Consumer vẫn hiểu status cũ, dù event producer đã đổi.
- Data dictionary nói một Order có một Shipment trong khi dữ liệu đã có nhiều kiện.
- Dashboard vẫn SUM số kiện và đặt tên "số đơn".

### Đối chiếu cấu trúc vật lý

PostgreSQL có thể được kiểm tra bằng metadata thực:

~~~sql
SELECT table_schema, table_name, column_name,
       data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'fulfillment'
  AND table_name IN ('shipment', 'shipment_line')
ORDER BY table_name, ordinal_position;
~~~

Thông tin metadata cho biết **cột thực có**, nhưng không chứng minh đủ index, CHECK, FK, partition hoặc quy tắc nghiệp vụ. Muốn schema diff đầy đủ cần xét catalog/migration metadata và công cụ so sánh có khả năng biểu diễn các đối tượng đó.

Một cơ chế phát hiện drift nên:

1. Xác định **expected schema** từ migration đã được duyệt.
2. Đọc **applied migration versions** và schema thực từ môi trường cần kiểm tra.
3. So sánh các khác biệt có ý nghĩa; phân loại migration chưa áp dụng với thay đổi ngoài quy trình.
4. Kết hợp các **kiểm tra ngữ nghĩa** từ model documentation, không chỉ so sánh tên cột.
5. Mở issue/incident cho sai khác, có owner và phương án reconcile; không tự sửa production khi chưa rõ nguồn/chủ sở hữu.

**Schema drift không luôn là lỗi cần rollback ngay.** Ví dụ một index được thêm để xử lý sự cố có thể đang giúp giảm tải; cần ghi nhận, chuẩn hóa vào migration hoặc hủy theo phê duyệt thay vì để tình trạng "Git không biết" kéo dài.

### Theo dõi trạng thái triển khai theo môi trường

| Môi trường | App release | Migration đã áp | Event contract | Fact transform | Tài liệu trạng thái |
| --- | --- | --- | --- | --- | --- |
| Development | Fulfillment 4.2 | V0042 | v1 | v3 | Proposed/Testing |
| Staging | Fulfillment 4.2 | V0042 | v1 | v3 | Verified staging |
| Production | Fulfillment 4.1 | V0041 | Legacy v1 | v2 | Legacy deployed |

Bảng là **ví dụ giả định**, không phản ánh một môi trường thật. Nó minh họa vì sao không thể đánh đồng merge PR với rollout hoàn tất. Môi trường có thể triển khai từng bước, consumer có thể nâng chậm và data mart còn độ trễ/backfill.

## 15. Quy trình review cùng code: ai nhận trách nhiệm cho từng câu hỏi?

Để tránh "ai cũng review nhưng không ai chịu trách nhiệm", nên phân ranh giới:

| Vai trò | Câu hỏi cần xác nhận | Dấu vết mong đợi |
| --- | --- | --- |
| **Business/domain owner** | Grain, cardinality, trạng thái và ngoại lệ có đúng đời sống nghiệp vụ? | Quyết định/ngữ nghĩa được duyệt |
| **Developer/aggregate owner** | Java root bảo vệ bất biến? Dữ liệu có thể nạp/phục hồi đúng? | Unit tests, command flow |
| **Database/data modeler** | Khóa, FK, CHECK, index, isolation, partition có phù hợp? | Schema review, migration test |
| **Integration/API owner** | Consumer hiểu field/event đúng nghĩa? Có version và idempotency? | Contract tests, consumer acknowledgments |
| **Analytics/metric owner** | Fact grain, dimension, KPI, lịch sử và độ tươi có đúng? | Metric specs và đối soát |
| **Security/privacy owner** | Dữ liệu nhạy cảm, quyền tenant, retention có phù hợp? | Review truy cập/vòng đời |
| **Operations/platform** | Deploy, backfill, rollback/roll-forward có an toàn và quan sát được? | Runbook, kế hoạch rollout |

Người viết mô hình có thể kiêm nhiều vai trò ở dự án nhỏ. Nhưng **ít nhất người có quyền định nghĩa nghiệp vụ và người bảo vệ tính đúng dữ liệu cần cùng hiểu sự thay đổi**. Một reviewer chỉ nhìn file migration có thể không biết sự kiện OrderDelivered cũ bị đổi nghĩa; một reviewer chỉ nhìn API không thể đánh giá lock trong database.

### Câu hỏi review mang tính kiểm chứng

Thay vì hỏi "ERD đẹp chưa?", hãy hỏi:

1. **Grain và danh tính:** một hàng/chủ thể mới là gì, ID có duy nhất và ổn định qua retry không?
2. **Cardinality:** 0..N hay 1..N? Trạng thái tạm, dữ liệu khuyết có làm sai giả định không?
3. **Bất biến:** rule nào phải đúng tại COMMIT và nguồn nào có quyền phân xử?
4. **Migration:** hàng cũ sẽ được đọc thế nào? Có thể biết chắc một Shipment cũ tương ứng dữ liệu nào không?
5. **Tương thích:** old binary, old client và consumer event v1 có còn hoạt động với dữ liệu mới không?
6. **Truy vết:** nếu có sai số liệu, từ metric có tìm được event, source record, migration và code version không?
7. **Privacy:** có thêm field cá nhân/địa chỉ vào event hoặc bản báo cáo không cần thiết không?
8. **Đo lường:** COUNT(*) đang đếm đơn, kiện, hay dòng ShipmentLine? Chỉ tiêu nào sẽ đổi sau rollout?
9. **Kiểm thử:** test nào sẽ thất bại nếu thiết kế đúng nhưng implementation sai?
10. **Rollout:** mốc nào có thể quay lại binary cũ, và mốc nào chỉ nên roll-forward?

Nếu một câu không có bằng chứng, PR nên ghi rõ **giả định và rủi ro còn mở**, người chịu trách nhiệm và điều kiện phải giải quyết trước khi bật tính năng. Không hợp thức hóa một ràng buộc chưa được hiểu chỉ vì CI đang xanh.

### Xử lý mâu thuẫn giữa reviewer

Ví dụ Sales cho rằng **một Order đã có một kiện giao thành công thì trạng thái có thể là DELIVERED**, còn Fulfillment cho rằng phải giao xong toàn bộ số lượng. Đây là **mâu thuẫn ngữ nghĩa**, không phải tranh luận về cách đặt tên enum. Các bên phải thống nhất:

- trạng thái cấp Shipment và trạng thái cấp Order;
- ý nghĩa partial delivery;
- ai là nguồn quyết định OrderDeliveryCompleted;
- những report cũ cần thay/đổi tên;
- cách chuyển những đơn đang dở dang.

Chỉ khi thống nhất mới viết contract/transition và test; không để hai đội lặng lẽ dùng hai cách diễn giải trong cùng một enum.

## 16. Tài liệu hóa theo kiểu lưu trữ: quan hệ, document, đồ thị, phân tích

Không có một mẫu ERD bắt buộc cho mọi công nghệ. **Các câu hỏi chung** là grain, identity, quan hệ, bất biến, vòng đời, truy vấn và phiên bản. **Biểu diễn vật lý** có thể khác:

| Mô hình vật lý | Tạo tác cần review | Những sai khác đặc thù |
| --- | --- | --- |
| **Quan hệ** | DDL/migration, ERD logic, PK/FK/UNIQUE/CHECK, index, transaction | Lock, isolation, constraint validation, dữ liệu vi phạm khi thêm UNIQUE/FK |
| **Document** | Document JSON Schema, embedded/reference decision, version/TTL policy | Old reader thiếu field, replace document làm mất field mới, atomicity một/nhiều document |
| **Đồ thị** | Node/edge types, hướng/cardinality, query traversal, constraint | Hướng cạnh sai, ranh giới quyền sở hữu, vòng lặp và cardinality rất lớn |
| **Chuỗi thời gian** | Series identity, event time, bucket, retention, rollup | Thay cadence/độ phân giải, dữ liệu đến muộn, mất lịch sử khi TTL |
| **Phân tích** | Fact grain, dimension/SCD, metric formula, lineage | Đếm trùng do JOIN, đổi ngày ghi nhận, chênh lệch version report |

### Với document: review cả khả năng đọc dữ liệu cũ

Ví dụ Order document cũ có một shipmentId. Document mới có shipments[]:

~~~json
{
  "orderId": "O-1001",
  "modelVersion": 2,
  "shipmentIds": ["S-11", "S-12"]
}
~~~

Nếu old writer chỉ hiểu shipmentId đơn, việc đọc document mới rồi **ghi đè toàn document** có thể làm mất Shipment thứ hai. PR cần giải thích **old writer bị chặn khi nào**, reader mới xử lý document v1 ra sao, và chuyển đổi dữ liệu cũ có được chứng thực không. Không coi một JSON schemaVersion là cơ chế bảo vệ ghi đồng thời nếu database chưa có conditional update/version control tương ứng.

### Với đồ thị: review hướng cạnh và ràng buộc

Mô hình Order → Shipment có thể lưu thành cạnh HAS_SHIPMENT. Một đường edge không đảm bảo tổng lượng phân bổ hoặc trạng thái giao hợp lệ. Nếu chuyển từ một cạnh sang nhiều cạnh, cần cập nhật:

- ngữ nghĩa và hướng cạnh;
- danh tính của cạnh/node, xử lý trùng khi ingest;
- truy vấn tìm "tất cả kiện của Order" và "các Order có ít nhất một kiện";
- các phép đếm/distinct sau traversal;
- thuộc tính thời gian và version của mối quan hệ;
- quyền ghi/truy cập node giữa các context.

### Với data warehouse: review semantic model cùng PR

Một thay đổi 1:N có thể khiến phép JOIN từ fact_order sang shipment nở số hàng. Nếu dashboard vẫn SUM(order_total) sau JOIN, giá trị đơn có thể bị nhân theo số kiện. Cần **tổng hợp ở đúng grain trước khi JOIN**, hoặc dùng fact Shipment và fact Order riêng theo yêu cầu. Kiểm thử cần chứa **một Order có hai Shipment**, vì dữ liệu test toàn một Shipment/Order sẽ không phát hiện lỗi.

## 17. Quản trị tài liệu, bảo mật và chính sách vòng đời

### 17.1. Không đưa dữ liệu thật nhạy cảm vào repo

Tài liệu mô hình cần mô tả loại dữ liệu, không cần chứa địa chỉ nhà, số thẻ, token hoặc dữ liệu khách hàng thật:

- Ví dụ dùng ID/địa chỉ giả hoặc dữ liệu tổng hợp không nhận diện cá nhân.
- Gắn nhãn field nhạy cảm trong data dictionary, quy định ai được đọc bảng/field.
- Event và DTO chỉ công bố dữ liệu tối thiểu theo consumer và use case.
- Thông tin kết nối production, bí mật và key không thuộc file Markdown mô hình.
- Nếu phải đính kèm ảnh/query plan từ production, cần loại dữ liệu nhận diện và kiểm tra quyền truy cập repository.

Một repository có kiểm soát phiên bản vẫn có lịch sử commit và bản sao; **xóa secret ở commit mới không làm nó tự biến mất khỏi toàn bộ lịch sử**. Chính sách dữ liệu thử và rà soát secret phải được áp dụng trước khi merge.

### 17.2. Chính sách cập nhật khi một PR không đổi schema

Không phải chỉ những PR chứa migration mới cần cập nhật model:

- Đổi **ý nghĩa enum** trong Java có thể đòi sửa glossary/contract dù schema DB không đổi.
- Đổi **cách tính net revenue** có thể chỉ sửa pipeline/semantic layer mà không thêm bảng.
- Đổi **retention/TTL** trên document hoặc time-series có thể không làm ERD đổi.
- Đổi **chủ sở hữu aggregate** có thể đòi đổi context map và ACL.
- Thêm **index** có thể chỉ cần ghi rationale/query workload, không cần sửa mô hình khái niệm.

Quy tắc hữu ích là: **mỗi PR phải rà xem tài liệu mô hình nào chịu tác động**, và khi không cần sửa thì nêu lý do ngắn gọn đối với những thay đổi đáng kể. Không áp nghĩa vụ "sửa tất cả sơ đồ trong mọi PR" một cách máy móc.

### 17.3. Tài liệu cũ: supersede, không xóa dấu quyết định

Một ERD target cũ có thể không còn đúng hiện tại nhưng vẫn cần để hiểu migration và incident lịch sử. Có thể:

- Đánh dấu **Superseded/Archived**, chỉ rõ bản thay thế và thời điểm hiệu lực.
- Giữ ADR cũ để truy vết lý do trong bối cảnh lúc đó.
- Duy trì tài liệu **current** rõ ràng, tránh người mới nhầm bản archived với thiết kế đang chạy.
- Đặt quy tắc retention cho data dictionary, schema snapshots và bản sao tài liệu theo chính sách tổ chức.

Nếu một quyết định đang được tranh luận lại, không sửa nội dung của ADR Accepted để trông như nó chưa từng tồn tại; tạo quyết định tiếp theo và liên kết tới quyết định trước.

### 17.4. Khi nhiều repository không thể merge một lúc

Sales, Fulfillment và Analytics có thể ở repo riêng. Một PR duy nhất là không khả thi; dùng **change initiative ID** chung:

~~~text
CHANGE-ID: DM-2026-042
ADR: ADR-0042
Sales PR:        tăng khả năng đọc trạng thái nhiều kiện
Fulfillment PR:  thêm Shipment và allocation ledger
Contracts PR:    ShipmentDeliveredV1, consumer compatibility
Analytics PR:    delivery metrics v3
Rollout plan:    expand -> readers -> writers -> feature -> cleanup
Evidence:        migration versions, tests, reconciliation report
~~~

Không merge đồng thời không có nghĩa các PR không được review cùng ngữ nghĩa. Quan trọng là ghi rõ **phụ thuộc, thứ tự deploy, old/new compatibility** và người quyết định bật feature. Khi producer đi trước consumer, phải có đường tương thích hoặc sự kiện mới không được phát cho consumer chưa hiểu.

## 18. Bài tập thực hành: từ một giảng viên sang nhiều giảng viên

**Bối cảnh:** Nền tảng học trực tuyến có Course, Instructor, Enrollment và Payment. Ban đầu mỗi Course có một instructorId. Từ học kỳ sau, một Course có thể có **nhiều giảng viên**, mỗi người phụ trách trong khoảng ngày và một số người chỉ dạy một phần nội dung. Bộ phận học thuật muốn xem giảng viên đang phụ trách; Analytics muốn so sánh học viên và doanh thu theo giảng viên trong các kỳ trước.

### Nhiệm vụ

1. **Mô hình khái niệm:** phát biểu quan hệ Course–Instructor mới, business owner và các câu hỏi còn mơ hồ cần làm rõ trước khi vẽ 1:N hay N:M.
2. **Logic và grain:** đề xuất một bảng/collection CourseInstructorAssignment. Một hàng đại diện cho gì? Có cần thời gian hiệu lực và vai trò không?
3. **Vật lý:** chọn PK/UNIQUE/FK, CHECK cho khoảng thời gian. Có nên cấm hai assignment cùng Instructor/Course chồng khoảng không? Nếu không, vì sao?
4. **Migration:** mô tả cách xử lý course.instructorId cũ nếu có Course thiếu giảng viên, Instructor đã nghỉ hoặc dữ liệu cũ chỉ phản ánh **người phụ trách hiện tại**.
5. **API/event:** response CourseDetail và event CourseInstructorAssigned nên chứa gì? Một consumer v1 đang kỳ vọng instructorId đơn có thể tiếp tục đọc thế nào?
6. **Báo cáo:** một Course có hai Instructor; JOIN Enrollment với assignment rồi SUM học phí có thể gây lỗi gì? Nêu một cách phân bổ hoặc định nghĩa metric an toàn.
7. **PR:** liệt kê những tạo tác cần đổi và những reviewer phải duyệt. Đề xuất hai cổng tự động và hai câu hỏi bắt buộc để con người review.
8. **Triển khai:** chia chuỗi thành các PR nhỏ theo expand–migrate–switch–contract; cách nhận biết schema đã deploy nhưng binary cũ còn chạy?

### Hướng giải tham khảo

**Mô hình:** Course và Instructor có thể là quan hệ **N:M theo thời gian** nếu mỗi người dạy nhiều Course và một Course có nhiều người dạy. Business owner phải giải thích "phụ trách" là quản lý môn, đứng lớp hay được chia doanh thu, và liệu một Course có thể tạm không có giảng viên.

**Grain:** một CourseInstructorAssignment biểu diễn **một lần phân công một Instructor vào một Course với vai trò và khoảng hiệu lực xác định**. Khóa có thể dùng assignmentId riêng để hỗ trợ cùng cặp Course–Instructor có nhiều đợt; UNIQUE(courseId,instructorId) tuyệt đối sẽ cấm những lần phân công lịch sử hợp lệ.

Một thiết kế ứng viên:

~~~sql
CREATE TABLE learning.course_instructor_assignment (
    tenant_id UUID NOT NULL,
    assignment_id UUID NOT NULL,
    course_id UUID NOT NULL,
    instructor_id UUID NOT NULL,
    role_code VARCHAR(24) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, assignment_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

DDL minh họa **giả định schema learning đã tồn tại**; chưa đưa FK tới Course/Instructor vì trong hệ thống thật cần biết hai bảng thuộc cùng database/context hay không. CHECK khoảng không âm không tự ngăn **hai phân công chồng thời gian**. Có cần ngăn hay không là câu hỏi nghiệp vụ: hai người có thể cùng dạy, hoặc cùng người được phân hai vai trò; không áp EXCLUDE/UNIQUE trước khi biết quy tắc.

**Migration:** từ instructorId cũ chỉ có thể backfill một assignment **đang có hiệu lực** nếu dữ liệu hiện tại được tin cậy và có mốc bắt đầu phù hợp. Không tự khẳng định instructorId cũ là người đã dạy Course ở mọi học kỳ trước; muốn lịch sử cần nguồn audit/assignment riêng. Nếu thiếu lịch sử thì công bố giới hạn.

**Exchange:** CourseDetail có thể cung cấp instructors[] ở API v2; consumer v1 cần adapter hoặc field principalInstructor có nghĩa được định nghĩa rõ, không tùy ý lấy phần tử đầu của mảng. Event CourseInstructorAssigned có assignmentId, courseId, instructorId, role, effective time, eventId, schemaVersion và tenant scope; không gửi dữ liệu cá nhân không cần thiết.

**Analytics:** JOIN một Enrollment có giá trị 1.000.000 VND với hai Instructor sẽ tạo **hai hàng**, làm SUM thành 2.000.000 nếu không có quy tắc. Cần định nghĩa metric như **số học viên có tham gia khóa cùng giảng viên** (có thể đếm ở hai nhóm nhưng không cộng lại để ra tổng duy nhất), hoặc **doanh thu phân bổ** theo trọng số có tổng bằng 100%, với nguồn và lịch sử phân bổ rõ ràng.

**PR và rollout:** cập nhật glossary, ERD, dictionary, migration, Java behavior/mapper, API/event contract, test và metric; được review bởi học thuật, developer/DB, consumer và BI owner. Triển khai mở rộng schema, nâng reader, backfill có căn cứ, bật ghi nhiều assignment, chuyển consumer/report rồi mới xóa field instructorId legacy. Theo dõi migration version và actual deployed app/consumer version, không suy từ trạng thái merge.

## 19. Checklist áp dụng và kết luận

Trước khi merge một thay đổi liên quan mô hình dữ liệu, hãy tự kiểm:

- **Bối cảnh:** user story, phạm vi bounded context, business owner và nguồn có thẩm quyền đã rõ?
- **Ngữ nghĩa:** thực thể, grain, ID, trạng thái, cardinality, thời gian, đơn vị tiền có cùng định nghĩa giữa tài liệu và code?
- **Tạo tác:** glossary, ERD, data dictionary, ADR, migration, Java, API/event và metric nào chịu tác động?
- **Lịch sử:** có giữ lại lý do thay đổi và mối liên hệ với phiên bản đã triển khai không?
- **Sơ đồ:** nguồn text dễ diff, chú thích cardinality/ngoại lệ; hình sinh có đồng bộ với schema không?
- **SQL/schema:** PK/FK/UNIQUE/CHECK, index và transaction bảo vệ đúng điều thực sự được cam kết?
- **Tương thích:** old writer/reader/consumer có xử lý dữ liệu mới, trường mới và trạng thái mới không?
- **Migration:** dữ liệu cũ có thể chuyển với bằng chứng, có xử lý NULL/unknown, không tự bịa lịch sử?
- **Rà soát:** người sở hữu nghiệp vụ, database, integration, analytics và security đã xem đúng phần mình phụ trách?
- **Tự động hóa:** docs lint, diagram render, migration test, contract test và data quality có đủ cho phạm vi?
- **Thử nghiệm:** có tình huống biên về concurrent writes, retry, late data, trùng bản ghi và lỗi tenant?
- **Báo cáo:** metric giữ đúng grain và ngày ghi nhận; số liệu trước/sau được đối soát theo cùng cutoff?
- **Triển khai:** PR đã merge nhưng migration/consumer có thể chưa deploy; trạng thái có được ghi rõ?
- **Khôi phục:** sau khi có dữ liệu mới, rollback binary cũ có thể xóa trường/ý nghĩa mới không? Có phương án roll-forward?
- **Drift:** có kiểm tra schema/hợp đồng thực so với thiết kế, và quy trình xử lý thay đổi ngoài Git?
- **Bảo mật:** tài liệu không chứa secret/PII thật; event/DTO và quyền repo phù hợp?

**Kết luận:** Quản lý mô hình dữ liệu trong kiểm soát phiên bản không đơn giản là **đưa ERD vào Git**. Cần đặt **ngữ nghĩa nghiệp vụ, bản thiết kế logic, ràng buộc vật lý, hành vi Java, hợp đồng trao đổi và định nghĩa báo cáo** trong cùng dòng truy vết thay đổi. Git và CI cung cấp lịch sử, diff và bằng chứng kiểm tra tự động; PR và người sở hữu nghiệp vụ xác nhận rằng những thay đổi đó **đúng về ý nghĩa**. Khi semantic diff, ADR, migration có thứ tự, contract test, đối soát và kiểm tra drift cùng hiện diện, mô hình không chỉ được mô tả đúng lúc thiết kế mà còn **có thể được rà soát, triển khai, truy vết và tiến hóa an toàn** cùng mã nguồn.
