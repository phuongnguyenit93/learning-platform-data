# Xác định khóa, quan hệ, thuộc tính và bất biến của từng phần

Thiết kế dữ liệu bắt đầu từ những câu tưởng như đơn giản: **“Một hàng biểu diễn điều gì?”**, **“Điều gì làm cho đối tượng này duy nhất?”**, **“Những đối tượng nào có thể liên quan với nhau?”** và **“Điều gì tuyệt đối không được xảy ra?”**. Nếu trả lời thiếu một câu, hệ thống có thể chấp nhận đơn hàng thuộc nhầm khách, nhân đôi tiền khi JOIN, thay đổi giá lịch sử khi sản phẩm được sửa, hoàn tiền vượt số đã thu hoặc giao nhiều hơn số lượng đặt.

Bài **thực hành tổng hợp** của mô-đun **DATABASE_DATA_MODELING** tập trung chuyển yêu cầu nghiệp vụ thành **mô hình quan hệ có thể kiểm chứng**, rồi đối chiếu những lựa chọn với document, graph và mô hình phân tích. Mỗi phần yêu cầu người học xác định đủ **grain, khóa ứng viên/khóa chính, khóa ngoại, quan hệ và cardinality, thuộc tính, ràng buộc và bất biến xuyên bản ghi**; tiếp theo kiểm tra bằng SQL PostgreSQL và các phản ví dụ. Đây là **một bài thực hành tự chứa**, không giả định có các bài khác đang mở.

## 1. Mục tiêu và cách thực hiện bài tổng hợp

Sau bài này, người học có thể:

1. Phân tách một mô tả nghiệp vụ thành các **thực thể, sự kiện và giá trị snapshot** mà không nhầm chúng với nhau.
2. Phát biểu **grain một hàng** trước khi chọn khóa hoặc tạo bảng.
3. Phân biệt **khóa nghiệp vụ, khóa ứng viên, khóa chính, khóa thay thế, khóa ngoại** và phạm vi duy nhất theo tenant.
4. Viết rõ **quan hệ 1–N, N–M, tùy chọn/bắt buộc** và xử lý quan hệ N–M bằng thực thể liên kết có thuộc tính riêng.
5. Phân loại thuộc tính **bắt buộc/tùy chọn, biến đổi theo thời gian, snapshot lúc giao dịch, dẫn xuất** và dữ liệu cần lịch sử.
6. Chuyển bất biến thành **PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK**, đồng thời nhận diện bất biến cần **transaction, locking, event/idempotency hoặc kiểm thử đối soát**.
7. Kiểm tra thiết kế bằng **fixture có trùng ID giữa các tenant, thanh toán từng phần, hoàn tiền nhiều lần, giao hàng nhiều đợt và thay đổi thuộc tính lịch sử**.
8. Đánh giá khi nào nên dùng mô hình quan hệ, document hoặc graph; xác định tác động của chỉ mục, phân vùng và thay đổi schema.

**Quy tắc làm bài:** ở mỗi phần, trước hết tự trả lời những câu hỏi *Grain? Key? Relation? Attribute? Invariant?* rồi mới xem gợi ý. Phần SQL là **ví dụ để người học tự chạy trên PostgreSQL trong schema thực hành trống**; bài không khẳng định đã chạy các câu lệnh trên cơ sở dữ liệu thực tế.

## 2. Đề bài xuyên suốt: nền tảng đặt hàng B2B nhiều doanh nghiệp

Một nền tảng tên giả định **OrderHub** phục vụ nhiều doanh nghiệp (**tenant**). Mỗi doanh nghiệp quản lý khách hàng và danh mục sản phẩm của riêng mình. Khách đặt đơn có nhiều dòng hàng, thanh toán có thể chia thành nhiều lần, hoàn tiền có thể thực hiện từng phần và hàng có thể giao trong nhiều chuyến.

Những yêu cầu dưới đây được coi là **hợp đồng nghiệp vụ của bài tập**, không phải quy tắc áp dụng cho mọi hệ thống thương mại điện tử:

| Mã | Yêu cầu nghiệp vụ |
| --- | --- |
| R01 | Mỗi **tenant** có định danh nội bộ ổn định và mã hiển thị riêng, không trùng toàn nền tảng. |
| R02 | **customer_id**, **product_id**, **order_id** và các ID con có thể **trùng giữa hai tenant** nhưng không trùng trong phạm vi tenant tương ứng. |
| R03 | Mỗi customer có **external_customer_code** duy nhất trong tenant; email hoặc tên hiển thị **không dùng làm khóa** vì có thể đổi và không nhất thiết duy nhất. |
| R04 | Mỗi product có **SKU duy nhất trong tenant**. Giá niêm yết hiện tại có thể thay đổi; đơn đã chốt phải giữ nguyên **giá tại thời điểm đặt**. |
| R05 | Một đơn thuộc đúng **một tenant và một customer** của tenant đó; một customer có thể có nhiều đơn. |
| R06 | Một đơn có thể là **DRAFT**, **PLACED** hoặc **CANCELLED**. Chỉ đơn **PLACED/CANCELLED** đã từng được chốt mới có **placed_at**. Một đơn được chốt phải có ít nhất một dòng. |
| R07 | Một dòng đơn có **line_no duy nhất trong đơn**, thuộc đúng một product cùng tenant, số lượng nguyên dương, đơn giá và giảm giá được chốt. |
| R08 | Thanh toán có thể theo nhiều **payment attempt**; mỗi attempt thuộc một đơn, có khóa idempotency riêng trong tenant và số tiền dương. Chỉ attempt **CAPTURED** được tính là đã thu. |
| R09 | Một attempt đã CAPTURED có thể có nhiều **refund**, mỗi refund có trạng thái. Tổng refund **SETTLED** của một attempt không vượt số tiền CAPTURED của attempt đó. |
| R10 | Một đơn có thể được giao bằng nhiều **shipment**. Mỗi shipment có nhiều dòng hàng; tổng số lượng **đã gửi** theo một dòng đơn không vượt số lượng đã đặt. |
| R11 | Họ tên/địa chỉ của customer có thể thay đổi. Đơn đã chốt lưu **ảnh chụp thông tin giao hàng** không tự đổi theo customer hiện tại. |
| R12 | Báo cáo phải bảo toàn số tiền và số lượng khi JOIN; có thể phân loại đơn theo **hạng khách có hiệu lực tại thời điểm đặt** nếu bổ sung lịch sử. |
| R13 | Ví dụ chỉ dùng **VND**, lưu số tiền theo đơn vị VND nguyên; không mô hình hóa tỷ giá, thuế, phí hoặc hoàn tiền theo từng dòng hàng. |

Một số quy tắc chưa được nêu, chẳng hạn đơn có thể thanh toán trước khi chốt hay một shipment có được sửa sau dispatch. **Không tự đoán là đã có yêu cầu.** Trong bài ta chọn quy ước cụ thể để minh họa và đánh dấu rõ quy tắc nào cần xác nhận thêm trước khi triển khai production.

### 2.1. Các trường hợp khó cố ý đặt vào bài

- Tenant 1 và tenant 2 đều có **customer_id = 10**, **product_id = 100**, **order_id = 500**.
- Đơn của tenant 1 với order_id 500 có **hai dòng hàng** và **hai lần thanh toán thành công**.
- Một lần thanh toán được hoàn **hai khoản riêng**, cùng tham chiếu về một payment attempt.
- Đơn có thể được giao **từng phần** nên một order có thể gắn nhiều shipment.
- Khách hàng đổi hạng từ **BRONZE** sang **GOLD**; báo cáo lịch sử phải chọn hạng **tại thời điểm chốt đơn**, không chọn hạng hiện tại.

Những dữ kiện ấy tạo ra các **negative case** thực tế: JOIN thiếu tenant, JOIN trực tiếp hai quan hệ 1–N, nhầm một lần refund với trạng thái thanh toán, hay JOIN dimension lịch sử thiếu khoảng thời gian.

## 3. Bước 1 — Từ danh từ nghiệp vụ đến thực thể và grain

Không phải mọi danh từ đều trở thành bảng. **Địa chỉ giao hàng lúc đặt** có thể là một giá trị snapshot trên order; **tổng tiền đơn** là một phép tính dẫn xuất; **sự kiện hoàn tiền** lại có định danh và vòng đời riêng, nên cần thực thể riêng.

| Phần | Thực thể/dataset đề xuất | Một hàng đại diện cho | Vì sao không gộp bừa vào bảng khác? |
| --- | --- | --- | --- |
| Doanh nghiệp | **tenants** | Một doanh nghiệp sử dụng nền tảng | Là ranh giới định danh và dữ liệu |
| Khách hàng | **customers** | Một khách trong một tenant | Một khách đặt nhiều đơn; thuộc tính có thể thay đổi |
| Sản phẩm | **products** | Một SKU/product trong một tenant | Giá/tên hiện tại không phải snapshot dòng đơn |
| Đơn hàng | **orders** | Một đơn của một tenant | Có trạng thái, khách sở hữu và thời điểm chốt |
| Dòng đơn | **order_lines** | Một dòng đã thêm vào một đơn | Một đơn chứa nhiều sản phẩm/số lượng, có giá chốt riêng |
| Thanh toán | **payment_attempts** | Một lần thử thu tiền của một đơn | Có retry, idempotency và trạng thái độc lập |
| Hoàn tiền | **refunds** | Một yêu cầu/sự kiện hoàn tiền của một attempt | Có nhiều khoản hoàn cho một lần thu |
| Giao hàng | **shipments** | Một chuyến giao của một đơn | Một đơn có nhiều chuyến, mỗi chuyến có trạng thái |
| Dòng giao | **shipment_lines** | Lượng của một dòng đơn nằm trong một chuyến giao | Biểu diễn quan hệ nhiều–nhiều kèm số lượng |
| Lịch sử hạng | **customer_tier_history** | Một phiên bản hạng khách có hiệu lực trong một khoảng | Hỗ trợ phân loại đơn theo quá khứ |

### 3.1. Grain là hợp đồng mạnh hơn tên bảng

Ví dụ:

~~~text
orders:
  một hàng = một đơn trong một tenant
  (tenant_id, order_id) -> customer_id, order_number, status, placed_at...

order_lines:
  một hàng = một dòng của một đơn
  (tenant_id, order_id, line_no) -> product_id, quantity, unit_price_vnd...

refunds:
  một hàng = một khoản hoàn tiền có refund_id riêng
  (tenant_id, refund_id) -> payment_attempt_id, amount_vnd, status...

shipment_lines:
  một hàng = một dòng đơn được phân bổ vào một shipment
  (tenant_id, shipment_id, line_no)
    -> order_id, shipped_qty...
~~~

Ký hiệu mũi tên ở đây biểu thị **phụ thuộc hàm do khóa xác định**, không phải luồng dữ liệu theo thời gian.

**Bài kiểm tra tự luận:** nếu không giải thích được một hàng **payment_attempts** là *một lần thử thu*, *một giao dịch capture* hay *một tổng đã thanh toán của đơn*, chưa nên tạo khóa và viết SUM.

### 3.2. Thực thể, thuộc tính, snapshot và số đo dẫn xuất

| Dữ kiện | Lựa chọn | Lý do |
| --- | --- | --- |
| Email customer hiện hành | Thuộc tính customer, có thể NULL/đổi | Không đủ ổn định làm PK |
| Địa chỉ giao khi chốt đơn | Snapshot thuộc order | Giữ sự thật giao dịch dù customer sửa địa chỉ |
| Giá niêm yết hiện tại | Thuộc tính product | Phục vụ đặt đơn mới |
| Đơn giá trên order line | Snapshot bất biến khi chốt | Dùng tính giá trị lịch sử |
| Giá trị dòng | Dẫn xuất: số lượng × đơn giá − giảm giá | Tránh hai nguồn sự thật về số tiền dòng |
| Tổng đơn | Dẫn xuất từ các dòng đủ điều kiện | Không tự thêm cột writable nếu chưa có chính sách đồng bộ |
| Tổng đã thu | Dẫn xuất từ payment CAPTURED | Nhiều attempt và retry |
| Tổng hoàn | Dẫn xuất từ refund SETTLED | Nhiều refund có thể thuộc một capture |
| Số lượng đã giao | Dẫn xuất từ shipment_lines thuộc chuyến đã gửi | Phân bổ nhiều chuyến, có chuyển trạng thái |
| Hạng khách lúc chốt | AS-OF từ bảng lịch sử hoặc snapshot xác định | Không lấy hạng hiện tại khi xem lịch sử |

Không có cách chia bảng “đúng tuyệt đối” cho mọi hệ thống. Quyết định phụ thuộc vào **grain, ràng buộc và câu hỏi truy vấn** được hợp đồng yêu cầu, nhưng nhất thiết phải diễn đạt những điều kiện ấy một cách có thể kiểm thử.

## 4. Bước 2 — Xác định khóa và phạm vi duy nhất

### 4.1. Khóa tự nhiên và khóa thay thế

- **Khóa ứng viên (candidate key):** tập cột tối thiểu đủ phân biệt hàng theo bất biến nghiệp vụ.
- **Khóa chính (primary key):** một khóa ứng viên được chọn làm định danh chính ở schema.
- **Khóa thay thế (surrogate key):** mã kỹ thuật được cấp, chẳng hạn customer_id; nó chỉ có ý nghĩa đúng khi chính sách cấp phát/duy nhất được bảo đảm.
- **Khóa nghiệp vụ (business key):** mã có ý nghĩa ngoài hệ thống như SKU hoặc order_number; có thể thay đổi tùy hợp đồng.
- **Khóa ngoại (foreign key):** tham chiếu từ khóa con tới khóa duy nhất phù hợp của cha, bảo vệ sự tồn tại và phạm vi quan hệ.

### 4.2. Ma trận khóa đề xuất

| Bảng | PK | Khóa nghiệp vụ/UNIQUE bổ sung | FK quan trọng |
| --- | --- | --- | --- |
| tenants | tenant_id | tenant_code | — |
| customers | (tenant_id, customer_id) | (tenant_id, external_customer_code) | tenant_id → tenants |
| products | (tenant_id, product_id) | (tenant_id, sku) | tenant_id → tenants |
| orders | (tenant_id, order_id) | (tenant_id, order_number) | (tenant_id, customer_id) → customers |
| order_lines | (tenant_id, order_id, line_no) | — | (tenant_id, order_id) → orders; (tenant_id, product_id) → products |
| payment_attempts | (tenant_id, attempt_id) | (tenant_id, idempotency_key); (tenant_id, provider, provider_ref) khi có ref | (tenant_id, order_id) → orders |
| refunds | (tenant_id, refund_id) | Tùy nguồn: provider_ref/idempotency | (tenant_id, attempt_id) → payment_attempts |
| shipments | (tenant_id, shipment_id) | (tenant_id, shipment_code) | (tenant_id, order_id) → orders |
| shipment_lines | (tenant_id, shipment_id, line_no) | — | Shipment đúng order và order_line cùng tenant/order |
| customer_tier_history | customer_tier_sk | Không-overlap theo (tenant, customer, valid-time) | (tenant_id, customer_id) → customers |

**Vì sao composite FK cần tenant_id?** Nếu customers có khóa (tenant_id, customer_id), dòng orders chỉ tham chiếu customer_id = 10 sẽ không phân biệt khách của tenant 1 với tenant 2. Đưa tenant_id vào FK khiến quan hệ cross-tenant không thể xảy ra bằng một insert hợp lệ.

### 4.3. Khóa đủ nhưng không dư

Khóa **(tenant_id, order_id, line_no)** xác định một order line vì cùng order có nhiều line_no. Nếu dòng đã có khóa ấy thì thêm product_id vào PK thường không làm nó “an toàn hơn”, chỉ làm quan hệ tham chiếu phức tạp và cho phép hiểu sai rằng product_id là một phần định danh dòng.

Ngược lại, đặt **UNIQUE(product_id)** lên products sẽ sai khi cùng product_id được tái sử dụng ở hai tenant. Đặt **UNIQUE(order_number)** toàn cục cũng sai với yêu cầu R02 nếu mã đơn chỉ phải duy nhất trong tenant.

### 4.4. Các khóa không nên chọn tùy tiện

Không dùng **email** làm customer PK, vì khách có thể thay email, dùng email chung hoặc chưa khai báo. Không dùng **giá sản phẩm** làm một phần khóa vì giá đổi theo thời gian. Không dùng **(tenant_id, order_id, product_id)** làm order line PK nếu nghiệp vụ có thể cho **cùng product xuất hiện hai dòng** với chương trình giảm giá khác nhau; line_no mới là định danh dòng ổn định.

Một số hệ thống có ID toàn cục dạng UUID/ULID. Dù có ID toàn cục, vẫn cần **ràng buộc cùng tenant** cho quan hệ nếu yêu cầu dữ liệu không được trộn; định danh toàn cục không tự bảo đảm quyền sở hữu hay phân quyền.

## 5. Bước 3 — Phát biểu quan hệ và bội số trước khi chọn JOIN

### 5.1. Sơ đồ thực thể khái niệm

~~~mermaid
erDiagram
    TENANT ||--o{ CUSTOMER : owns
    TENANT ||--o{ PRODUCT : sells
    TENANT ||--o{ ORDER : hosts
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : referenced_by
    ORDER ||--o{ PAYMENT_ATTEMPT : has
    PAYMENT_ATTEMPT ||--o{ REFUND : refunded_by
    ORDER ||--o{ SHIPMENT : ships_in
    SHIPMENT ||--o{ SHIPMENT_LINE : includes
    ORDER_LINE ||--o{ SHIPMENT_LINE : allocated_to
    CUSTOMER ||--o{ CUSTOMER_TIER_HISTORY : classified_as
    TENANT {
        bigint tenant_id PK
        text tenant_code UK
    }
    CUSTOMER {
        bigint tenant_id PK
        bigint customer_id PK
        text external_customer_code UK
    }
    PRODUCT {
        bigint tenant_id PK
        bigint product_id PK
        text sku UK
    }
    ORDER {
        bigint tenant_id PK
        bigint order_id PK
        bigint customer_id FK
        text order_number UK
    }
    ORDER_LINE {
        bigint tenant_id PK
        bigint order_id PK
        integer line_no PK
        bigint product_id FK
    }
    PAYMENT_ATTEMPT {
        bigint tenant_id PK
        bigint attempt_id PK
        bigint order_id FK
    }
    REFUND {
        bigint tenant_id PK
        bigint refund_id PK
        bigint attempt_id FK
    }
    SHIPMENT {
        bigint tenant_id PK
        bigint shipment_id PK
        bigint order_id FK
    }
    SHIPMENT_LINE {
        bigint tenant_id PK
        bigint shipment_id PK
        integer line_no PK
        bigint order_id FK
    }
    CUSTOMER_TIER_HISTORY {
        bigint customer_tier_sk PK
        bigint tenant_id FK
        bigint customer_id FK
    }
~~~

Sơ đồ mô tả **các quan hệ được phép về mặt cấu trúc**. Nét **o{** ở phía order_lines cho phép đơn DRAFT chưa có dòng; bất biến **PLACED phải có ít nhất một dòng** không thể hiện đầy đủ chỉ bằng ký hiệu cardinality tĩnh. Tương tự, sơ đồ không biểu diễn điều kiện tổng refund hay tổng shipped_qty.

### 5.2. Đọc đúng chiều và tính tùy chọn

| Quan hệ | Ở phía cha | Ở phía con | Ràng buộc bổ sung |
| --- | --- | --- | --- |
| Tenant → Customer | Một tenant có 0..N customer | Mỗi customer thuộc đúng 1 tenant | Không thể tham chiếu tenant khác |
| Customer → Order | Một customer có 0..N order | Mỗi order có đúng 1 customer | Customer không được bị xóa làm orphan order |
| Order → OrderLine | Order DRAFT có 0..N line; PLACED ít nhất 1 | Một line thuộc đúng 1 order | line_no duy nhất trong order |
| Product → OrderLine | Một product được đặt 0..N lần | Một line tham chiếu 1 product | Unit price vẫn là snapshot tại lúc đặt |
| Order → PaymentAttempt | Một order có 0..N attempt | Một attempt thuộc 1 order | Chỉ CAPTURED được tính là đã thu |
| PaymentAttempt → Refund | Một attempt có 0..N refund | Một refund thuộc 1 attempt | Tổng SETTLED không vượt CAPTURED |
| Order → Shipment | Một order có 0..N shipment | Một shipment thuộc 1 order | Quy trình giao do business rule quyết định |
| Shipment ↔ OrderLine | N–M qua shipment_lines | Một allocation thuộc đúng 1 shipment và 1 order line | Shipment và line phải cùng order/tenant |
| Customer → TierHistory | Một customer có 0..N phiên bản lịch sử | Một phiên bản thuộc 1 customer | Không-overlap valid-time nếu chỉ một hạng ở mỗi thời điểm |

### 5.3. Phân giải N–M cần thuộc tính của quan hệ

Một shipment có thể gồm nhiều order line; một order line có thể được gửi ở nhiều shipment. Nếu thiết kế trực tiếp:

~~~text
shipment.order_line_ids = [1, 2, 3]
order_line.shipment_ids = [700, 701]
~~~

thì khó bảo vệ số lượng giao từng phần và tính nhất quán giữa hai danh sách. Thực thể liên kết:

~~~text
shipment_lines(
    tenant_id,
    shipment_id,
    order_id,
    line_no,
    shipped_qty
)
~~~

không chỉ nối hai đầu mà còn lưu **thuộc tính của quan hệ: shipped_qty**. Không đặt shipped_qty trên product hoặc order_line nếu một dòng có thể được giao nhiều đợt.

### 5.4. JOIN không xác định grain của kết quả thay cho người thiết kế

Nếu một order có hai lines và hai payment attempts, JOIN theo order_id trả **bốn cặp**, không phải hai dòng đơn hoặc hai payment. Đếm hoặc SUM sau JOIN phải được giải thích ở **grain các cặp**, hoặc phải tổng hợp từng phía về grain order trước khi JOIN. Nội dung này sẽ được kiểm tra bằng số liệu cụ thể ở mục 11.

## 6. Bước 4 — Phân loại thuộc tính, thời gian và dữ liệu dẫn xuất

### 6.1. Dữ liệu hiện hành so với snapshot

| Đối tượng | Thuộc tính hiện hành | Snapshot phải giữ trên giao dịch | Hệ quả nếu thiết kế sai |
| --- | --- | --- | --- |
| Customer | display_name, email, địa chỉ mặc định | shipping_name, shipping_address lúc chốt | Sửa customer làm đổi lịch sử giao hàng |
| Product | sku, product_name, list_price_vnd | product_id, unit_price_vnd trên line | Tăng giá sản phẩm làm tăng doanh số cũ |
| Order | status hiện tại, cancellation metadata | placed_at, line prices/discounts đã chốt | Không phân biệt draft và đơn đã chốt |
| Payment | trạng thái attempt và provider ID | Sự kiện CAPTURED/reversal có định danh | Retry bị hiểu là thu tiền lần thứ hai |
| Customer tier | Hạng hiện hành | Phiên bản tier tại placed_at hoặc lịch sử có hiệu lực | Thống kê kỳ trước bị chuyển sang hạng mới |

**Lưu thông tin snapshot không phải luôn là phi chuẩn hóa xấu.** Nó có ý nghĩa nghiệp vụ độc lập: **địa chỉ khách hiện tại** và **địa chỉ đã xác nhận để giao đơn** là hai sự thật khác nhau.

### 6.2. Attribute domain và NULL phải có ý nghĩa

- **quantity > 0**: dùng integer có CHECK.
- **unit_price_vnd >= 0**, **discount_vnd >= 0**: giá có thể bằng 0 cho hàng tặng.
- **discount_vnd <= quantity × unit_price_vnd**: tránh giá trị dòng âm trong ví dụ.
- **placed_at = NULL** với DRAFT: chưa chốt, khác việc timestamp bị thiếu do lỗi import.
- **provider_ref = NULL** trước khi cổng thanh toán trả mã: khác chuỗi rỗng hoặc giá trị tự bịa.
- **currency_code = VND**: giả định bài học; nếu sau này hỗ trợ nhiều tiền tệ, phải sửa lược đồ và quy tắc cộng tiền.
- **refund.status = REQUESTED** không được xem như đã chuyển tiền hoàn cho khách.

Đừng mặc định **NULL = 0** trong dữ liệu tài chính hoặc dùng chuỗi **UNKNOWN** cho mọi trường còn thiếu. Số tiền 0 có thể là giá hợp lệ; số tiền chưa xác định cần trạng thái/nullable tương ứng theo hợp đồng.

### 6.3. Các giá trị tính được nên có một nguồn sự thật

Với một dòng:

\[
\text{line\_net\_vnd}
= \text{quantity}\times\text{unit\_price\_vnd}
-\text{discount\_vnd}.
\]

Với một đơn:

\[
\text{order\_total\_vnd}
= \sum_{\text{line thuộc đơn}}\text{line\_net\_vnd}.
\]

Nếu lưu tổng đơn như cột có thể sửa tự do, ta tạo hai cách đọc cùng một sự thật: từ các dòng và từ cột tổng. Nếu yêu cầu hiệu năng phải materialize tổng, cần quy trình cập nhật **cùng transaction hoặc tái tính/đối soát** và xác định nguồn chuẩn. Với bài này, tổng đơn được tính từ lines.

### 6.4. Tiêu chí chọn loại thời gian

| Trường | Ý nghĩa | Không nên đồng nhất với |
| --- | --- | --- |
| created_at | Khi bản ghi được tạo trong hệ thống | Khi đơn được chốt |
| placed_at | Thời điểm đơn có hiệu lực là đã đặt | Khi dữ liệu được ingest sang warehouse |
| captured_at | Thời điểm cổng/nguồn ghi nhận capture hợp lệ | Khi webhook được nhận lần cuối |
| settled_at | Thời điểm hoàn tiền được xác nhận đã quyết toán | Khi refund được yêu cầu |
| valid_from / valid_to | Khoảng hiệu lực của hạng khách | Khoảng thời gian database biết correction |
| ingested_at | Khi bản sao được nhận vào hệ khác | Event time nghiệp vụ |

Trong báo cáo lịch sử, cần tách **valid time** và **system/knowledge time** khi có cập nhật hồi tố. Một bản báo cáo theo dữ liệu **đã biết ngày 20/11** khác bản **được restate ngày 23/11** dù cùng tính doanh số ngày 20/11.

## 7. Bước 5 — Liệt kê bất biến theo mức thực thi

Không phải bất biến nào cũng triển khai được bằng một CHECK trên một hàng. Phân loại đúng nơi thực thi quan trọng không kém việc viết phát biểu bất biến.

| ID | Bất biến | Cách bảo vệ chính | Cách kiểm thử |
| --- | --- | --- | --- |
| I01 | Mã tenant không trùng | UNIQUE(tenant_code) | Chèn hai tenant cùng code phải lỗi |
| I02 | Mã customer/SKU/order_number duy nhất **trong tenant** | UNIQUE composite | Trùng tenant lỗi, khác tenant hợp lệ |
| I03 | Không có order tham chiếu customer tenant khác | Composite FK | Chèn FK sai tenant phải lỗi |
| I04 | Không có line tham chiếu order/product không cùng tenant | Composite FK | Negative insert |
| I05 | quantity dương, discount không vượt tiền trước giảm | CHECK trên order_lines | Chèn qty 0 hoặc discount quá mức |
| I06 | DRAFT không có placed_at; PLACED/CANCELLED có placed_at | CHECK theo trạng thái | Test chuyển trạng thái |
| I07 | PLACED phải có ít nhất một dòng | Transaction/trigger hoặc service command đồng bộ | Từ chối chốt order rỗng |
| I08 | Giá và địa chỉ đã chốt không đổi khi product/customer sửa | Chính sách bất biến, trigger/quy trình version | Sửa product/customer rồi so snapshot |
| I09 | Retry cùng idempotency key không tạo thêm payment attempt | UNIQUE + idempotent command | Replay request trùng |
| I10 | Chỉ CAPTURED góp vào tổng đã thu | Query/ledger semantic contract | Test attempt FAILED không tăng paid |
| I11 | Tổng CAPTURED của order không vượt tổng phải trả (giả định bài) | Transaction với khóa order và tính tổng | Hai captures đồng thời |
| I12 | Refund SETTLED chỉ gắn với CAPTURED và không vượt số thu của attempt | Transaction + locking + trạng thái | Hai refunds song song |
| I13 | Shipment line thuộc đúng order của shipment | Composite FK gồm order_id | Test liên kết sai order |
| I14 | Tổng shipped_qty của dòng theo chuyến đã gửi không vượt quantity đặt | Transaction khi dispatch + khóa order/line | Hai shipments cùng lúc |
| I15 | Một khách có tối đa một hạng có hiệu lực ở mỗi thời điểm | Non-overlap range, constraint/locking | Test hai khoảng chồng |
| I16 | JOIN không nhân số tiền từ hai fact khác grain | Truy vấn đúng grain + reconciliation | Fixture 2 lines × 2 payments |
| I17 | Tenant chỉ thấy dữ liệu có quyền | Authorization/RLS/tenant scope | Thử request chéo tenant |
| I18 | Báo cáo lịch sử dùng hạng có hiệu lực lúc placed_at | AS-OF JOIN + versioned metadata | Test trước/sau mốc đổi hạng |

### 7.1. Ba nhóm thực thi cần tách

**Nhóm A — Khai báo trực tiếp trong database:** PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL, CHECK; có thể ngăn trạng thái sai ngay khi INSERT/UPDATE.

**Nhóm B — Nhiều hàng hoặc nhiều bảng:** tổng tiền CAPTURED/REFUND, giới hạn giao hàng, đơn có ít nhất một dòng; thường cần một **transaction có phạm vi khóa/chặn cạnh tranh được thiết kế rõ**, hoặc logic trigger/procedure có đủ cách ngăn race condition.

**Nhóm C — Theo thời gian hoặc xuyên hệ thống:** cùng source event không được xử lý hai lần, ghi nhận correction, chọn version as-of, đảm bảo tenant isolation trong API, đồng bộ dữ liệu dẫn xuất. Các quy tắc này cần thiết kế **event ID, checkpoint, transaction boundary, authorization, reconciliation và monitoring**, không chỉ vài cột trong schema.

### 7.2. Bất biến “chỉ khi chuyển trạng thái” khác “bất biến mọi thời điểm”

Một shipment ở trạng thái **CREATED** có thể đang được soạn và chứa các dòng dự kiến. Giới hạn **đã giao** chỉ tính khi shipment chuyển sang **DISPATCHED/DELIVERED**. Một đơn **DRAFT** có thể chưa có dòng; bất biến “đơn phải có dòng” chỉ áp dụng trước chuyển sang **PLACED**.

Nếu không gắn bất biến với **trạng thái và thời điểm thực thi**, hệ thống có thể chặn một thao tác hợp lệ khi người dùng còn nhập dở, hoặc ngược lại chấp nhận thao tác cuối gây sai sót.

### 7.3. Ràng buộc là quy tắc dữ liệu, phân quyền là quy tắc truy cập

Composite FK bảo đảm một order line tham chiếu product **cùng tenant**, nhưng không ngăn API của tenant khác **đọc dữ liệu** nếu query không lọc tenant hoặc policy sai. Phải kiểm thử quyền ở tầng phục vụ và cân nhắc **PostgreSQL Row-Level Security** nếu kiến trúc phù hợp; không dùng FK như cơ chế xác thực.

## 8. Bước 6 — DDL PostgreSQL cho các phần dữ liệu cốt lõi

Các lệnh dưới đây được thiết kế để chạy **theo thứ tự trong một schema thử nghiệm trống**. Chúng cố ý minh họa ràng buộc khai báo và điểm giới hạn của SQL; một số bất biến **xuyên nhiều hàng** sẽ được xử lý sau bằng transaction/kiểm thử.

### 8.1. Tenant, customer và product

~~~sql
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_code TEXT NOT NULL UNIQUE
);

CREATE TABLE customers (
    tenant_id BIGINT NOT NULL
        REFERENCES tenants(tenant_id),
    customer_id BIGINT NOT NULL,
    external_customer_code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, external_customer_code)
);

CREATE TABLE products (
    tenant_id BIGINT NOT NULL
        REFERENCES tenants(tenant_id),
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    list_price_vnd NUMERIC(18, 0) NOT NULL
        CHECK (list_price_vnd >= 0),
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Giải thích:** customer_id hoặc product_id không nhất thiết duy nhất toàn hệ thống. Composite PK và UNIQUE theo tenant bảo vệ phạm vi đã mô tả ở R02–R04. email không phải UNIQUE vì đề bài không khẳng định mỗi email chỉ có thể thuộc một customer.

### 8.2. Order và order line

~~~sql
CREATE TABLE orders (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    order_number TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PLACED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL,
    placed_at TIMESTAMPTZ,
    shipping_name TEXT,
    shipping_address TEXT,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_number),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id),
    CHECK (
        (status = 'DRAFT' AND placed_at IS NULL)
        OR
        (
            status IN ('PLACED', 'CANCELLED')
            AND placed_at IS NOT NULL
            AND shipping_name IS NOT NULL
            AND shipping_address IS NOT NULL
        )
    )
);

CREATE TABLE order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd NUMERIC(18, 0) NOT NULL
        CHECK (unit_price_vnd >= 0),
    discount_vnd NUMERIC(18, 0) NOT NULL DEFAULT 0
        CHECK (discount_vnd >= 0),
    line_net_vnd NUMERIC
        GENERATED ALWAYS AS
            (quantity * unit_price_vnd - discount_vnd) STORED,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id),
    CHECK (discount_vnd <= quantity * unit_price_vnd)
);
~~~

**Những điều được DDL bảo vệ:** customer và product cùng tenant; không trùng line_no trong order; giá trị dòng không âm; đặt đúng currency; quan hệ order line tới order tồn tại.

**Những điều DDL chưa bảo vệ:** một order PLACED có ít nhất một line; không thay đổi line sau khi chốt; không chuyển trạng thái CANCELLED quay lại DRAFT. Chúng liên quan **nhiều hàng hoặc lịch sử chuyển trạng thái**, phải có giao thức ghi và test riêng.

Nếu sử dụng ràng buộc status của bài, thao tác chốt đơn phải thực hiện **trong một transaction**: khóa order, kiểm tra có line và dữ liệu chốt, sau đó cập nhật status/placed_at/shipping snapshot. Tất cả writer sửa lines hoặc chốt order phải tuân thủ cùng quy tắc khóa để không có race condition.

### 8.3. Payment attempt và refund

~~~sql
CREATE TABLE payment_attempts (
    tenant_id BIGINT NOT NULL,
    attempt_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    provider TEXT NOT NULL,
    provider_ref TEXT,
    idempotency_key TEXT NOT NULL,
    amount_vnd NUMERIC(18, 0) NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL CHECK (
        status IN (
            'INITIATED', 'AUTHORIZED', 'CAPTURED', 'FAILED'
        )
    ),
    captured_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, attempt_id),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, provider, provider_ref),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    CHECK (
        (status = 'CAPTURED' AND captured_at IS NOT NULL)
        OR
        (status <> 'CAPTURED' AND captured_at IS NULL)
    )
);

CREATE TABLE refunds (
    tenant_id BIGINT NOT NULL,
    refund_id BIGINT NOT NULL,
    attempt_id BIGINT NOT NULL,
    amount_vnd NUMERIC(18, 0) NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL
        CHECK (status IN ('REQUESTED', 'SETTLED', 'FAILED')),
    settled_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, refund_id),
    FOREIGN KEY (tenant_id, attempt_id)
        REFERENCES payment_attempts(tenant_id, attempt_id),
    CHECK (
        (status = 'SETTLED' AND settled_at IS NOT NULL)
        OR
        (status <> 'SETTLED' AND settled_at IS NULL)
    )
);
~~~

Trong PostgreSQL, ràng buộc **UNIQUE(tenant_id, provider, provider_ref)** cho phép nhiều hàng có **provider_ref = NULL** theo hành vi mặc định của UNIQUE với NULL. Đó là hợp lý trước khi cổng trả mã. Khi provider_ref có giá trị, một tenant không được dùng lại cùng mã của cùng provider cho hai attempt. Ứng dụng cũng cần xác minh webhook và đối chiếu idempotency payload, không chỉ dựa vào một dòng UNIQUE.

**Refund** không có order_id riêng vì order có thể truy từ attempt. Điều này tránh tình trạng refund ghi **order_id khác** với attempt. Nếu vì lý do truy vấn phải lưu thêm order_id trong refund, cần FK composite đúng với attempt hoặc ràng buộc tương đương để không tạo hai sự thật trái nhau.

Không có CHECK một hàng nào ở bảng refunds tự tính được **tổng tất cả refund SETTLED của cùng attempt**. Bất biến tổng hạn mức phải được bảo vệ khi chuyển trạng thái hoặc ghi ledger.

### 8.4. Shipment và shipment line

~~~sql
CREATE TABLE shipments (
    tenant_id BIGINT NOT NULL,
    shipment_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    shipment_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'CREATED', 'DISPATCHED', 'DELIVERED', 'CANCELLED'
        )
    ),
    dispatched_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, shipment_id),
    UNIQUE (tenant_id, shipment_code),
    UNIQUE (tenant_id, shipment_id, order_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    CHECK (
        (status IN ('DISPATCHED', 'DELIVERED')
            AND dispatched_at IS NOT NULL)
        OR
        (status IN ('CREATED', 'CANCELLED')
            AND dispatched_at IS NULL)
    )
);

CREATE TABLE shipment_lines (
    tenant_id BIGINT NOT NULL,
    shipment_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    shipped_qty INTEGER NOT NULL CHECK (shipped_qty > 0),
    PRIMARY KEY (tenant_id, shipment_id, line_no),
    FOREIGN KEY (tenant_id, shipment_id, order_id)
        REFERENCES shipments(tenant_id, shipment_id, order_id),
    FOREIGN KEY (tenant_id, order_id, line_no)
        REFERENCES order_lines(tenant_id, order_id, line_no)
);
~~~

Ràng buộc **UNIQUE(tenant_id, shipment_id, order_id)** dù có phần dư so với PK vẫn hữu ích làm **đích FK composite** cho shipment_lines, giúp bảo đảm allocation cùng order của shipment. Nếu chỉ FK theo **(tenant_id, shipment_id)** và một FK khác tới order_lines theo **(tenant_id, order_id, line_no)**, shipment_line có thể hợp lệ với từng bảng riêng nhưng **tham chiếu hai order khác nhau**.

Trường hợp một shipment đã DISPATCHED rồi bị trả hàng, không nên chỉ chuyển về CANCELLED và đặt dispatched_at = NULL nếu nghiệp vụ yêu cầu lưu dấu vết giao thực tế. Bài giản lược chỉ chấp nhận các trạng thái như dữ liệu mẫu; production cần mô hình **return/reversal, shipment events và quy tắc cập nhật trạng thái** rõ.

### 8.5. Chỉ mục phục vụ truy vấn thường gặp

~~~sql
CREATE INDEX idx_orders_customer
    ON orders (tenant_id, customer_id, placed_at);

CREATE INDEX idx_order_lines_product
    ON order_lines (tenant_id, product_id);

CREATE INDEX idx_payments_order_status
    ON payment_attempts (tenant_id, order_id, status);

CREATE INDEX idx_refunds_attempt_status
    ON refunds (tenant_id, attempt_id, status);

CREATE INDEX idx_shipments_order_status
    ON shipments (tenant_id, order_id, status);

CREATE INDEX idx_shipment_lines_order_line
    ON shipment_lines (tenant_id, order_id, line_no);
~~~

Đây là những **ứng viên chỉ mục**, không phải danh sách bắt buộc trong mọi workload. PK/UNIQUE đã tạo các index tương ứng; chỉ thêm index hỗ trợ **đường lọc/JOIN cụ thể** khi đánh giá EXPLAIN, tỷ lệ đọc/ghi và kích thước bảng.

## 9. Bước 7 — Nạp fixture có các trường hợp cần kiểm thử

Tạo dữ liệu nhỏ nhưng có đủ **trùng ID giữa tenant, đơn nhiều line, nhiều payment, nhiều refund và giao từng phần**. Các giá trị tiền là VND nguyên, không phụ thuộc nguồn bên ngoài.

### 9.1. Doanh nghiệp, khách và sản phẩm

~~~sql
INSERT INTO tenants (tenant_id, tenant_code) VALUES
    (1, 'SHOP_A'),
    (2, 'SHOP_B');

INSERT INTO customers (
    tenant_id, customer_id, external_customer_code,
    display_name, email
) VALUES
    (1, 10, 'C-001', 'Khách A', 'a@example.test'),
    (2, 10, 'C-001', 'Khách B', 'b@example.test'),
    (2, 20, 'C-020', 'Khách phụ B', NULL);

INSERT INTO products (
    tenant_id, product_id, sku, product_name, list_price_vnd
) VALUES
    (1, 100, 'SKU-A', 'Bộ dụng cụ A', 120000),
    (1, 101, 'SKU-B', 'Phụ kiện B', 90000),
    (2, 100, 'SKU-A', 'Bộ dụng cụ A - tenant B', 100000);
~~~

Hai product có cùng **product_id = 100** và **SKU-A**, nhưng ở **hai tenant khác nhau** nên hợp lệ theo hợp đồng. Tương tự, customer_id 10 và external_customer_code C-001 được dùng lại ở tenant 2; điều này buộc mọi JOIN phải dùng tenant_id.

### 9.2. Ba đơn, bốn dòng

~~~sql
INSERT INTO orders (
    tenant_id, order_id, order_number, customer_id, status,
    created_at, placed_at, shipping_name, shipping_address,
    currency_code
) VALUES
    (
        1, 500, 'ORD-001', 10, 'PLACED',
        TIMESTAMPTZ '2026-11-20 08:30:00+07',
        TIMESTAMPTZ '2026-11-20 09:00:00+07',
        'Người nhận A', 'Địa chỉ đã chốt A', 'VND'
    ),
    (
        1, 501, 'ORD-002', 10, 'PLACED',
        TIMESTAMPTZ '2026-11-21 08:30:00+07',
        TIMESTAMPTZ '2026-11-21 09:00:00+07',
        'Người nhận A', 'Địa chỉ đã chốt A - lần 2', 'VND'
    ),
    (
        2, 500, 'ORD-001', 10, 'PLACED',
        TIMESTAMPTZ '2026-11-20 09:30:00+07',
        TIMESTAMPTZ '2026-11-20 10:00:00+07',
        'Người nhận B', 'Địa chỉ đã chốt B', 'VND'
    );

INSERT INTO order_lines (
    tenant_id, order_id, line_no, product_id,
    quantity, unit_price_vnd, discount_vnd
) VALUES
    (1, 500, 1, 100, 2, 120000, 20000),
    (1, 500, 2, 101, 1, 90000, 0),
    (1, 501, 1, 101, 2, 90000, 10000),
    (2, 500, 1, 100, 1, 100000, 0);
~~~

Kiểm tra giá trị dòng:

| Tenant / đơn / dòng | Phép tính | line_net_vnd |
| --- | --- | ---: |
| 1 / 500 / 1 | 2 × 120.000 − 20.000 | 220.000 |
| 1 / 500 / 2 | 1 × 90.000 | 90.000 |
| 1 / 501 / 1 | 2 × 90.000 − 10.000 | 170.000 |
| 2 / 500 / 1 | 1 × 100.000 | 100.000 |
| **Tổng** | | **580.000** |

Như vậy: **tenant 1/order 500 = 310.000 VND**, **tenant 1/order 501 = 170.000 VND**, **tenant 2/order 500 = 100.000 VND**. Tổng số lượng đã đặt là **6 đơn vị**, nhưng số dòng chỉ là **4** và số đơn là **3**.

### 9.3. Bốn lần thu và hai khoản hoàn

~~~sql
INSERT INTO payment_attempts (
    tenant_id, attempt_id, order_id, provider,
    provider_ref, idempotency_key,
    amount_vnd, status, captured_at
) VALUES
    (
        1, 900, 500, 'DEMO_GATEWAY',
        'TX-900', 'pay-A-900',
        200000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-20 09:05:00+07'
    ),
    (
        1, 901, 500, 'DEMO_GATEWAY',
        'TX-901', 'pay-A-901',
        110000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-20 09:06:00+07'
    ),
    (
        1, 902, 501, 'DEMO_GATEWAY',
        'TX-902', 'pay-A-902',
        170000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-21 09:05:00+07'
    ),
    (
        2, 900, 500, 'DEMO_GATEWAY',
        'TX-900', 'pay-B-900',
        100000, 'CAPTURED',
        TIMESTAMPTZ '2026-11-20 10:05:00+07'
    );

INSERT INTO refunds (
    tenant_id, refund_id, attempt_id,
    amount_vnd, status, settled_at
) VALUES
    (
        1, 800, 900, 30000, 'SETTLED',
        TIMESTAMPTZ '2026-11-21 10:00:00+07'
    ),
    (
        1, 801, 900, 20000, 'SETTLED',
        TIMESTAMPTZ '2026-11-21 11:00:00+07'
    );
~~~

Cả hai refund đều gắn với **attempt 900 của tenant 1**, có tổng 50.000 VND, nhỏ hơn 200.000 VND đã thu trong attempt đó. Payment **attempt_id = 900** và provider_ref **TX-900** cũng xuất hiện ở tenant 2 nhưng là giao dịch khác; thêm tenant_id vào FK và phép JOIN là bắt buộc.

| Chỉ số | Tổng VND |
| --- | ---: |
| Giá trị dòng đơn hợp lệ | 580.000 |
| Tổng CAPTURED | 580.000 |
| Tổng refund SETTLED | 50.000 |
| CAPTURED trừ refund SETTLED | 530.000 |

**Lưu ý:** chỉ số **CAPTURED − SETTLED refunds** là *net cash captured* theo quy tắc minh họa, không được tự gọi là “doanh thu kế toán”. Một refund có ngày quyết toán sau ngày đặt cũng không tự làm giảm chỉ số **gross ordered value của ngày đặt** nếu hợp đồng chỉ số không yêu cầu restatement.

### 9.4. Giao hàng từng phần

~~~sql
INSERT INTO shipments (
    tenant_id, shipment_id, order_id,
    shipment_code, status, dispatched_at
) VALUES
    (
        1, 700, 500, 'SHP-700', 'DISPATCHED',
        TIMESTAMPTZ '2026-11-21 08:00:00+07'
    ),
    (1, 701, 500, 'SHP-701', 'CREATED', NULL),
    (
        1, 702, 501, 'SHP-702', 'DISPATCHED',
        TIMESTAMPTZ '2026-11-22 08:00:00+07'
    ),
    (
        2, 700, 500, 'SHP-700', 'DELIVERED',
        TIMESTAMPTZ '2026-11-21 08:30:00+07'
    );

INSERT INTO shipment_lines (
    tenant_id, shipment_id, order_id, line_no, shipped_qty
) VALUES
    (1, 700, 500, 1, 1),
    (1, 700, 500, 2, 1),
    (1, 701, 500, 1, 1),
    (1, 702, 501, 1, 2),
    (2, 700, 500, 1, 1);
~~~

Những dòng có shipment trạng thái **CREATED** chỉ là **dự kiến phân bổ**, chưa tính là đã giao. Theo quy tắc của bài:

| Đơn | Số lượng đặt | Đã DISPATCHED/DELIVERED | Dự kiến ở CREATED |
| --- | ---: | ---: | ---: |
| Tenant 1 / 500 | 3 | 2 | 1 |
| Tenant 1 / 501 | 2 | 2 | 0 |
| Tenant 2 / 500 | 1 | 1 | 0 |
| **Tổng** | **6** | **5** | **1** |

Số lượng đã gửi có thể thấp hơn số lượng đặt mà không phải lỗi. Bất biến quan trọng là **không vượt** và các chuyến phải gắn đúng order/line.

## 10. Bước 8 — Kiểm chứng khóa và quan hệ bằng negative test

Các test thất bại sau phải được chạy **riêng từng trường hợp** trong schema thử nghiệm; chúng **được kỳ vọng bị database từ chối**. Không gom nhiều câu INSERT lỗi trong một transaction rồi kỳ vọng các lệnh sau vẫn chạy.

### 10.1. Không cho order của tenant 1 tham chiếu customer chỉ thuộc tenant 2

~~~sql
-- Mong đợi lỗi FOREIGN KEY:
-- customer_id 20 chỉ tồn tại ở tenant 2.
INSERT INTO orders (
    tenant_id, order_id, order_number, customer_id, status,
    created_at, placed_at, shipping_name, shipping_address
) VALUES (
    1, 599, 'ORD-599', 20, 'DRAFT',
    TIMESTAMPTZ '2026-11-22 09:00:00+07',
    NULL, NULL, NULL
);
~~~

Nếu FK chỉ tham chiếu customer_id mà không mang tenant_id, thiết kế có thể cho phép dữ liệu sai ranh giới khách hàng. Composite FK hiện tại sẽ từ chối.

### 10.2. Không cho giảm giá vượt tiền dòng

~~~sql
-- Mong đợi lỗi CHECK: 150000 > 1 * 100000.
INSERT INTO order_lines (
    tenant_id, order_id, line_no, product_id,
    quantity, unit_price_vnd, discount_vnd
) VALUES (1, 500, 99, 100, 1, 100000, 150000);
~~~

### 10.3. Không cho dòng giao của order 501 nằm trong shipment order 500

~~~sql
-- Mong đợi lỗi FK (tenant_id, shipment_id, order_id):
-- shipment 700 của tenant 1 thuộc order 500, không phải 501.
INSERT INTO shipment_lines (
    tenant_id, shipment_id, order_id, line_no, shipped_qty
) VALUES (1, 700, 501, 1, 1);
~~~

Lưu ý: order 501 thật sự có line_no = 1. Vì thế nếu chỉ có FK tới order_line và FK tới shipment **riêng rẽ**, từng tham chiếu có thể đều hợp lệ nhưng **mối quan hệ giữa chúng sai**. Đây là ca kiểm thử chứng minh lý do cần FK composite chứa order_id.

### 10.4. Không cho trùng idempotency key trong cùng tenant

~~~sql
-- Mong đợi lỗi UNIQUE(tenant_id, idempotency_key).
INSERT INTO payment_attempts (
    tenant_id, attempt_id, order_id, provider,
    provider_ref, idempotency_key,
    amount_vnd, status, captured_at
) VALUES (
    1, 999, 500, 'DEMO_GATEWAY',
    'TX-999', 'pay-A-900',
    200000, 'INITIATED', NULL
);
~~~

**UNIQUE** ngăn thêm một hàng mới với cùng idempotency key, nhưng hệ thống vẫn phải quyết định retry có **cùng payload** thì trả kết quả cũ, retry với **payload khác** thì báo xung đột; không chỉ trả lỗi 500 hoặc chặn yêu cầu mà không giải thích.

### 10.5. Test nào không thể mong đợi lỗi CHECK?

Nếu thêm refund **SETTLED 180.000** cho attempt 900 của tenant 1, tổng refund sẽ là **230.000 > 200.000**. Với DDL minh họa, INSERT đó **có thể vẫn hợp lệ ở mức hàng đơn lẻ**. Đây là **bất biến nhiều hàng**; không nên ghi test “CHECK sẽ chặn” khi chưa có trigger/giao thức thanh toán kiểm soát cạnh tranh. Mục 12 sẽ chỉ cách phát hiện và ngăn sai bằng transaction.

## 11. Bước 9 — Đối soát phép nối và số đo theo đúng grain

### 11.1. Phản ví dụ: JOIN order lines và payment attempts trực tiếp

~~~sql
-- PHẢN MẪU: không dùng để tính doanh số hoặc tổng đã thu.
SELECT
    COUNT(*) AS joined_pairs,
    SUM(l.line_net_vnd) AS duplicated_sales_vnd,
    SUM(p.amount_vnd) AS duplicated_captured_vnd
FROM order_lines AS l
JOIN payment_attempts AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_id = l.order_id
WHERE p.status = 'CAPTURED';
~~~

Kỳ vọng trên fixture:

| Chỉ số | Kết quả JOIN sai | Kết quả từ nguồn độc lập |
| --- | ---: | ---: |
| Số hàng kết quả JOIN | 6 cặp | 4 lines và 4 attempts |
| SUM(line_net_vnd) | 890.000 | 580.000 |
| SUM(CAPTURED amount_vnd) | 890.000 | 580.000 |

Ở **tenant 1/order 500**, có **2 lines × 2 attempts = 4 cặp**. Hai dòng trị giá 220.000 và 90.000 bị nhân đôi, khiến phần doanh số của order này từ **310.000** thành **620.000**. Hai attempts 200.000 và 110.000 cũng bị nhân đôi. Hai order còn lại mỗi bên có một line và một attempt nên không bị nhân tại bước này; tổng sai toàn bộ thành **890.000**.

Điều nguy hiểm là **hai tổng sai bằng nhau**, khiến phép đối chiếu hời hợt “bán bằng thu” vẫn PASS. Một thiết kế tốt phải kiểm tra **tổng nguồn độc lập trước JOIN**, không dùng hai số sai từ cùng phép nối để xác nhận lẫn nhau.

### 11.2. Cách đúng: tổng hợp từng phía về grain đơn hàng

~~~sql
WITH line_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity) AS ordered_qty,
        SUM(line_net_vnd) AS order_total_vnd
    FROM order_lines
    GROUP BY tenant_id, order_id
),
capture_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS captured_attempts,
        SUM(amount_vnd) AS captured_vnd
    FROM payment_attempts
    WHERE status = 'CAPTURED'
    GROUP BY tenant_id, order_id
),
refund_totals AS (
    SELECT
        p.tenant_id,
        p.order_id,
        SUM(r.amount_vnd) AS refunded_vnd
    FROM refunds AS r
    JOIN payment_attempts AS p
      ON p.tenant_id = r.tenant_id
     AND p.attempt_id = r.attempt_id
    WHERE r.status = 'SETTLED'
    GROUP BY p.tenant_id, p.order_id
),
shipped_totals AS (
    SELECT
        s.tenant_id,
        s.order_id,
        SUM(sl.shipped_qty) AS dispatched_qty
    FROM shipments AS s
    JOIN shipment_lines AS sl
      ON sl.tenant_id = s.tenant_id
     AND sl.shipment_id = s.shipment_id
     AND sl.order_id = s.order_id
    WHERE s.status IN ('DISPATCHED', 'DELIVERED')
    GROUP BY s.tenant_id, s.order_id
)
SELECT
    o.tenant_id,
    o.order_id,
    COALESCE(l.line_count, 0) AS line_count,
    COALESCE(l.ordered_qty, 0) AS ordered_qty,
    COALESCE(l.order_total_vnd, 0) AS order_total_vnd,
    COALESCE(c.captured_vnd, 0) AS captured_vnd,
    COALESCE(r.refunded_vnd, 0) AS refunded_vnd,
    COALESCE(c.captured_vnd, 0)
      - COALESCE(r.refunded_vnd, 0) AS net_captured_vnd,
    COALESCE(s.dispatched_qty, 0) AS dispatched_qty
FROM orders AS o
LEFT JOIN line_totals AS l
  ON l.tenant_id = o.tenant_id AND l.order_id = o.order_id
LEFT JOIN capture_totals AS c
  ON c.tenant_id = o.tenant_id AND c.order_id = o.order_id
LEFT JOIN refund_totals AS r
  ON r.tenant_id = o.tenant_id AND r.order_id = o.order_id
LEFT JOIN shipped_totals AS s
  ON s.tenant_id = o.tenant_id AND s.order_id = o.order_id
ORDER BY o.tenant_id, o.order_id;
~~~

Kết quả dự kiến:

| Tenant / đơn | Lines | Đặt (qty) | Tổng đơn (VND) | CAPTURED (VND) | Refund (VND) | Đã gửi (qty) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 / 500 | 2 | 3 | 310.000 | 310.000 | 50.000 | 2 |
| 1 / 501 | 1 | 2 | 170.000 | 170.000 | 0 | 2 |
| 2 / 500 | 1 | 1 | 100.000 | 100.000 | 0 | 1 |
| **Tổng** | **4** | **6** | **580.000** | **580.000** | **50.000** | **5** |

Các CTE được **GROUP BY cùng khóa (tenant_id, order_id)** trước khi nối, nên mỗi tập có tối đa **một hàng trên mỗi đơn**. Đây là cách kiểm soát fanout trong phép tổng hợp nhiều fact. Nếu có bản ghi payment-only mà không có order hợp lệ, FK sẽ từ chối trong cùng PostgreSQL; trong hệ tích hợp không có FK xuyên dịch vụ vẫn phải kiểm tra orphan.

### 11.3. Đếm đúng đơn, khách, dòng và sự kiện

~~~sql
SELECT
    COUNT(*) AS order_rows,
    COUNT(DISTINCT (tenant_id, order_id)) AS distinct_orders,
    COUNT(DISTINCT (tenant_id, customer_id))
        AS distinct_customers_with_orders
FROM orders;
-- order_rows = 3; distinct_orders = 3;
-- distinct_customers_with_orders = 2.

SELECT COUNT(*) AS line_rows, SUM(quantity) AS units
FROM order_lines;
-- line_rows = 4; units = 6.

SELECT COUNT(*) AS captured_attempt_rows,
       SUM(amount_vnd) AS captured_vnd
FROM payment_attempts
WHERE status = 'CAPTURED';
-- 4; 580000.
~~~

**Hai customers có đơn** là (1,10) và (2,10), dù **customer_id = 10** giống nhau. Nếu COUNT(DISTINCT customer_id) mà bỏ tenant_id thì kết quả sai thành **1**.

### 11.4. Kiểm tra “đơn đã chốt phải có dòng”

~~~sql
SELECT o.tenant_id, o.order_id
FROM orders AS o
WHERE o.status IN ('PLACED', 'CANCELLED')
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

Kỳ vọng **không có hàng**. Đây là phép phát hiện dữ liệu sai; nếu hai transaction có thể vừa chốt đơn vừa xóa dòng, chạy truy vấn sau khi lỗi xảy ra không thay thế việc **khóa order trước chuyển trạng thái và sửa line**.

### 11.5. Kiểm tra CAPTURED vượt tổng đơn

~~~sql
WITH ordered AS (
    SELECT
        tenant_id, order_id,
        SUM(line_net_vnd) AS order_total_vnd
    FROM order_lines
    GROUP BY tenant_id, order_id
),
captured AS (
    SELECT
        tenant_id, order_id,
        SUM(amount_vnd) AS captured_vnd
    FROM payment_attempts
    WHERE status = 'CAPTURED'
    GROUP BY tenant_id, order_id
)
SELECT
    c.tenant_id, c.order_id,
    c.captured_vnd, o.order_total_vnd
FROM captured AS c
LEFT JOIN ordered AS o
  ON o.tenant_id = c.tenant_id
 AND o.order_id = c.order_id
WHERE o.order_id IS NULL
   OR c.captured_vnd > o.order_total_vnd;
~~~

Kỳ vọng rỗng với giả định **đơn giá trị dương/không âm và tổng CAPTURED không vượt giá trị đơn**. Nếu hệ thống cho thu tiền đặt cọc cho phí dịch vụ ngoài dòng đơn hoặc cho phép thu vượt để giữ bảo đảm, bất biến này **phải được sửa** theo hợp đồng mới, không dùng truy vấn trên như một quy tắc phổ quát.

### 11.6. Kiểm tra refund đã quyết toán theo từng attempt

~~~sql
WITH per_attempt AS (
    SELECT
        p.tenant_id,
        p.attempt_id,
        p.status AS payment_status,
        p.amount_vnd AS captured_amount_when_success,
        COALESCE(
            SUM(r.amount_vnd)
                FILTER (WHERE r.status = 'SETTLED'),
            0
        ) AS settled_refund_vnd
    FROM payment_attempts AS p
    LEFT JOIN refunds AS r
      ON r.tenant_id = p.tenant_id
     AND r.attempt_id = p.attempt_id
    GROUP BY
        p.tenant_id, p.attempt_id,
        p.status, p.amount_vnd
)
SELECT *
FROM per_attempt
WHERE settled_refund_vnd > captured_amount_when_success
   OR (
       payment_status <> 'CAPTURED'
       AND settled_refund_vnd > 0
   );
~~~

Kỳ vọng **không có hàng**. Với attempt 900 của tenant 1: 200.000 đã thu, 50.000 đã hoàn. Với tenant 2/attempt 900: 100.000 đã thu, 0 hoàn. Test phải giữ **tenant_id**; chỉ JOIN refunds.attempt_id = payment_attempts.attempt_id sẽ nhầm hai attempt 900.

### 11.7. Kiểm tra số lượng đã giao theo từng dòng đơn

~~~sql
WITH dispatched AS (
    SELECT
        sl.tenant_id,
        sl.order_id,
        sl.line_no,
        SUM(sl.shipped_qty) AS dispatched_qty
    FROM shipment_lines AS sl
    JOIN shipments AS s
      ON s.tenant_id = sl.tenant_id
     AND s.shipment_id = sl.shipment_id
     AND s.order_id = sl.order_id
    WHERE s.status IN ('DISPATCHED', 'DELIVERED')
    GROUP BY sl.tenant_id, sl.order_id, sl.line_no
)
SELECT
    l.tenant_id,
    l.order_id,
    l.line_no,
    l.quantity AS ordered_qty,
    d.dispatched_qty
FROM dispatched AS d
JOIN order_lines AS l
  ON l.tenant_id = d.tenant_id
 AND l.order_id = d.order_id
 AND l.line_no = d.line_no
WHERE d.dispatched_qty > l.quantity;
~~~

Kỳ vọng **không có hàng**. Với tenant 1/order 500/line 1, mới **DISPATCHED 1 trên 2**; shipment 701 còn **CREATED** nên không tính vào số đã giao. Khi shipment 701 được dispatch, tổng sẽ thành **2 trên 2** và vẫn hợp lệ.

## 12. Bước 10 — Giữ bất biến khi có giao dịch đồng thời

Các câu SELECT ở mục 11 hữu ích để phát hiện sai lệch, nhưng **phát hiện sau khi ghi không tự ngăn ghi sai**. Bất biến tổng tiền và số lượng cần được bảo vệ ngay tại đường thay đổi trạng thái.

### 12.1. Hai refund đồng thời có thể cùng vượt hạn mức

Giả sử một attempt đã CAPTURED **200.000**, đã có refund SETTLED **50.000**. Hai worker cùng nhận yêu cầu hoàn **100.000**:

~~~text
Worker A đọc: còn 150.000 -> 100.000 hợp lệ.
Worker B đọc: còn 150.000 -> 100.000 hợp lệ.
Worker A ghi SETTLED 100.000.
Worker B ghi SETTLED 100.000.
Tổng = 250.000 > 200.000: sai bất biến.
~~~

Cách thiết kế bảo vệ trong một PostgreSQL database là **tuần tự hóa các thao tác quyết định hạn mức trên cùng payment attempt**:

~~~sql
BEGIN;

-- Tất cả writer quyết định refund phải khóa cùng parent.
SELECT tenant_id, attempt_id, status, amount_vnd
FROM payment_attempts
WHERE tenant_id = 1 AND attempt_id = 900
FOR UPDATE;

SELECT COALESCE(SUM(amount_vnd), 0) AS already_settled_vnd
FROM refunds
WHERE tenant_id = 1
  AND attempt_id = 900
  AND status = 'SETTLED';

-- Ứng dụng hoặc stored procedure kiểm tra:
-- 1. payment.status = CAPTURED.
-- 2. refund đang REQUESTED và chưa SETTLED.
-- 3. already_settled + requested_amount <= captured amount.
-- 4. idempotency/nguồn webhook của refund đã được xác thực.
-- Chỉ sau khi PASS mới UPDATE refund thành SETTLED
-- trong cùng transaction này.

COMMIT;
~~~

**Đây là mẫu giao thức, không phải procedure hoàn chỉnh**: các điều kiện ghi bằng comment phải được code thực thi, nếu bỏ qua thì SQL không tự chặn oversettlement. Mọi writer liên quan phải khóa cùng payment_attempts theo quy tắc nhất quán; nếu có đường ghi trực tiếp bỏ qua khóa, race vẫn tồn tại.

Ở isolation READ COMMITTED, worker thứ hai sau khi lấy được khóa parent cần **đọc lại tổng refund đã commit mới nhất** trước khi quyết định. Khi nguồn tiền ở **cổng thanh toán bên ngoài**, một transaction trong database nội bộ không bảo đảm refund thực tế đã quyết toán; còn cần **provider reference, webhook idempotency, trạng thái đối soát và xử lý thất bại**.

### 12.2. Hai CAPTURED đồng thời trên cùng order

Giả sử đơn trị giá 310.000, đã CAPTURED 200.000. Hai attempts khác nhau muốn CAPTURED thêm mỗi lần 80.000. Mỗi worker riêng có thể thấy còn 110.000 nên đều cho phép, dẫn tới **360.000 > 310.000**.

Với hợp đồng hạn mức đơn, mọi writer CAPTURED cần **khóa cùng hàng orders(tenant_id,order_id)**, tính lại tổng dòng và tổng attempts CAPTURED, rồi chỉ chốt attempt khi tổng mới không vượt. Nếu có thể sửa line khi đang thanh toán, **đường sửa line cũng phải phối hợp cùng khóa order** và trạng thái chốt.

Nếu hệ thống phân tán nhiều database, **SELECT FOR UPDATE tại một node không khóa được những node khác**; cần thiết kế ownership/consistency boundary, ledger hoặc cơ chế phối hợp phù hợp thay vì ngầm giả định transaction toàn hệ thống.

### 12.3. Hai shipment dispatch cùng một dòng

Với order line đặt **2 đơn vị** và đã gửi **1**, hai shipment CREATED độc lập mỗi chuyến muốn gửi thêm **1**. Nếu hai worker cùng đọc còn 1 mà không đồng bộ, cả hai có thể dispatch, khiến tổng giao **3 > 2**.

Một giao thức an toàn trong một database:

1. Khóa **orders(tenant_id,order_id)** hoặc những hàng **order_lines** liên quan theo một thứ tự cố định.
2. Đọc lại tổng shipped_qty ở shipment trạng thái DISPATCHED/DELIVERED.
3. Cộng các shipment_lines sắp chuyển trạng thái và kiểm tra **không vượt quantity**.
4. Đổi trạng thái và thời điểm dispatch trong **cùng transaction**.
5. Mọi thao tác sửa shipment_lines, hủy giao hoặc thay quantity sau khi chốt phải dùng cùng giao thức/kiểm toán.

Nếu muốn quản lý cả **giữ chỗ trước khi dispatch**, nên có thực thể reservation/stock allocation riêng hoặc đổi bất biến để bao gồm lượng **được giữ**, không đánh đồng CREATED với đã giao.

### 12.4. Giới hạn của CHECK và của ứng dụng

CHECK chỉ nhìn được giá trị của hàng đang ghi, còn các quy tắc **SUM của nhiều hàng** đòi cơ chế phối hợp. Ngược lại, chỉ viết validation ở HTTP handler là chưa đủ nếu còn batch job, consumer webhook hay script admin có thể ghi thẳng vào database. Hãy xác định **một hoặc nhiều write path được kiểm soát** (stored procedure, service command, trigger phù hợp), ghi test cạnh tranh và kiểm tra tất cả đường cập nhật đều tuân thủ.

## 13. Phần mở rộng — Hạng khách có lịch sử và AS-OF JOIN

Giả sử khách đổi từ BRONZE sang GOLD. Nếu report đơn cũ JOIN vào **hạng hiện tại**, những đơn đã đặt khi còn BRONZE sẽ bị gán GOLD và thay đổi phân bố lịch sử. Ta thêm một bảng có **grain: một phiên bản hạng của một customer trong khoảng thời gian hiệu lực**.

### 13.1. DDL, khóa và khoảng thời gian

~~~sql
CREATE TABLE customer_tier_history (
    customer_tier_sk BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    tier TEXT NOT NULL
        CHECK (tier IN ('BRONZE', 'SILVER', 'GOLD')),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX idx_customer_tier_lookup
    ON customer_tier_history (
        tenant_id, customer_id, valid_from
    );
~~~

**Khóa customer_tier_sk** xác định một phiên bản. **Khóa (tenant_id,customer_id)** xác định một khách nghiệp vụ nhưng **không duy nhất** trong bảng lịch sử, bởi khách có nhiều phiên bản. Cần tránh **overlap** của các khoảng cho cùng khách nếu hợp đồng nói mỗi thời điểm có tối đa một hạng.

Trên PostgreSQL có khả năng và quyền dùng **btree_gist**, có thể bổ sung:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE customer_tier_history
ADD CONSTRAINT customer_tier_no_overlap
EXCLUDE USING gist (
    tenant_id WITH =,
    customer_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~

Khoảng **[valid_from, valid_to)** là nửa mở: bao gồm đầu, không bao gồm cuối. valid_to NULL được biểu diễn bằng khoảng không có biên trên. Ràng buộc exclusion chỉ phù hợp khi một customer **không thể có hai tier đồng thời**; nếu nghiệp vụ cho phép nhiều hạng theo chương trình khác nhau, phải thêm chiều **program_id** hoặc thiết kế grain tương ứng, không ép các mối quan hệ hợp lệ thành lỗi.

### 13.2. Nạp lịch sử và truy vấn theo thời điểm chốt

~~~sql
INSERT INTO customer_tier_history (
    customer_tier_sk, tenant_id, customer_id,
    tier, valid_from, valid_to
) VALUES
    (
        1001, 1, 10, 'BRONZE',
        TIMESTAMPTZ '2026-01-01 00:00:00+07',
        TIMESTAMPTZ '2026-11-21 00:00:00+07'
    ),
    (
        1002, 1, 10, 'GOLD',
        TIMESTAMPTZ '2026-11-21 00:00:00+07',
        NULL
    ),
    (
        1003, 2, 10, 'SILVER',
        TIMESTAMPTZ '2026-01-01 00:00:00+07',
        NULL
    );

SELECT
    h.tier,
    COUNT(DISTINCT (o.tenant_id, o.order_id)) AS order_count,
    SUM(l.line_net_vnd) AS ordered_value_vnd
FROM orders AS o
JOIN order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
JOIN customer_tier_history AS h
  ON h.tenant_id = o.tenant_id
 AND h.customer_id = o.customer_id
 AND o.placed_at >= h.valid_from
 AND (o.placed_at < h.valid_to OR h.valid_to IS NULL)
WHERE o.status = 'PLACED'
GROUP BY h.tier
ORDER BY h.tier;
~~~

| Tier tại thời điểm đặt | Số đơn | Tổng tiền dòng (VND) |
| --- | ---: | ---: |
| BRONZE | 1 | 310.000 |
| GOLD | 1 | 170.000 |
| SILVER | 1 | 100.000 |

Nếu JOIN theo **customer_id** nhưng bỏ **tenant_id**, các bản hạng T01 và T02 có thể bị trộn. Nếu JOIN theo tenant/customer nhưng bỏ **điều kiện thời gian**, cả đơn T01/500 và 501 đều khớp hai phiên bản BRONZE/GOLD, khiến tổng bị nhân đôi.

### 13.3. Test mỗi đơn PLACED khớp đúng một phiên bản

~~~sql
SELECT
    o.tenant_id,
    o.order_id,
    COUNT(h.customer_tier_sk) AS tier_versions_matched
FROM orders AS o
LEFT JOIN customer_tier_history AS h
  ON h.tenant_id = o.tenant_id
 AND h.customer_id = o.customer_id
 AND o.placed_at >= h.valid_from
 AND (o.placed_at < h.valid_to OR h.valid_to IS NULL)
WHERE o.status = 'PLACED'
GROUP BY o.tenant_id, o.order_id
HAVING COUNT(h.customer_tier_sk) <> 1;
~~~

Kỳ vọng **rỗng**. **0 match** có thể do tier lịch sử chưa được nạp hoặc có gap; **nhiều hơn 1** có thể do overlap hoặc thiếu khóa trong điều kiện JOIN. UNIQUE(customer_tier_sk) **không đủ** để bảo đảm điều này.

### 13.4. Tách sửa hồi tố với tái hiện dữ liệu từng công bố

Nếu ngày 23/11 hệ thống mới biết thực tế khách đã lên GOLD từ ngày 20/11, cần phân biệt:

- **Valid time:** tier có hiệu lực nghiệp vụ vào ngày nào?
- **System/knowledge time:** hệ thống ghi nhận thay đổi ấy vào ngày nào?

Đổi trực tiếp valid_from trong một bảng chỉ giữ phiên bản hiện hành của lịch sử sẽ làm mất khả năng tái hiện những báo cáo đã công bố dựa trên lịch sử cũ. Khi yêu cầu kiểm toán, nên giữ **snapshot dimension theo run**, hoặc mô hình **bitemporal** có cả hai trục thời gian. Một báo cáo restate theo sự thật mới có thể đổi phân bố BRONZE/GOLD, nhưng **tổng line_net_vnd toàn bộ đơn không đổi**.

## 14. Phần mở rộng — Chọn mô hình vật lý và kiểu dữ liệu phù hợp

### 14.1. Khi nào mô hình quan hệ có lợi?

Trong tình huống này, OrderHub cần:

- Composite FK ngăn tham chiếu sai tenant.
- Khóa duy nhất bảo vệ đơn, dòng, attempt và shipment.
- Transaction bảo vệ việc chốt đơn, capture/settle refund và dispatch.
- JOIN có thể kiểm thử giữa orders, lines, payments, refunds và shipments.

Một RDBMS như PostgreSQL là lựa chọn thuận lợi để **thực thi quan hệ và bất biến trong một database**. Nhưng việc dùng RDBMS không bảo đảm mô hình tự đúng: CHECK không tự kiểm SUM xuyên hàng và không có chỉ mục nào tự chữa JOIN sai grain.

### 14.2. Nếu lưu đơn dưới dạng document

Một document có thể chứa order và lines:

~~~json
{
  "tenant_id": 1,
  "order_id": 500,
  "status": "PLACED",
  "lines": [
    {"line_no": 1, "product_id": 100,
     "quantity": 2, "unit_price_vnd": 120000,
     "discount_vnd": 20000},
    {"line_no": 2, "product_id": 101,
     "quantity": 1, "unit_price_vnd": 90000,
     "discount_vnd": 0}
  ]
}
~~~

Đọc toàn bộ order có thể thuận tiện, nhưng vẫn phải bảo vệ:

- (tenant_id, order_id) duy nhất.
- line_no không trùng **trong mảng lines**.
- product_id tham chiếu product cùng tenant, nếu không có FK native thì phải kiểm tra tại đường ghi hoặc qua quy trình đối soát.
- Giá lịch sử không bị ghi đè khi document hoặc product catalog thay đổi.
- Payment/refund/shipments có nhiều thao tác bất đồng bộ, thường không nên nhúng tất cả trạng thái vào **một document được nhiều service ghi tùy ý**.

Nếu pipeline **unwind** đồng thời mảng lines và payments, nó vẫn tạo các cặp tích Descartes và nhân tiền như SQL JOIN sai. **Đổi mô hình lưu trữ không xóa được vấn đề grain.**

### 14.3. Khi nào graph hữu ích?

Nếu mục tiêu là tìm **mạng quan hệ khách–công ty–đại diện–nhà cung cấp–đơn hàng** hoặc truy vấn nhiều bước qua các cạnh, graph có thể phù hợp. Nhưng một truy vấn graph đếm **số đường đi** không tự bằng **số đơn duy nhất**; một order có thể được đến qua nhiều path.

Phải định nghĩa **khóa node/edge, cardinality của quan hệ, tenant boundary và valid-time của cạnh**. Với ledger thanh toán có giới hạn tiền và giao dịch nguyên tử, graph không tự thay thế những bất biến tài chính đã mô tả.

### 14.4. Phân vùng/sharding theo tenant có đánh đổi gì?

Đặt **tenant_id** làm khóa phân phối giúp giữ phần lớn order, lines, payment và customer của một tenant gần nhau. Tuy nhiên:

- Một **whale tenant** có thể làm nóng một shard dù số tenant được hash đều.
- Các truy vấn trên nhiều tenant có thể cần fan-out/tổng hợp từ nhiều shard.
- Unique/FK **xuyên shard** tùy engine, không tự có giống trong một PostgreSQL instance.
- Khi một tenant cần nhiều shard, phân phối theo **(tenant_id, order_id hoặc bucket)** có thể giúp mở rộng nhưng làm truy vấn toàn tenant phức tạp hơn.

Trong bài, composite PK **(tenant_id, order_id)** bảo vệ **định danh logic**, không tự biến PostgreSQL thành một hệ sharding nhiều máy. Chọn partition key phải dựa trên **workload, locality giao dịch, phân bố tải và giới hạn vận hành**.

### 14.5. Thiết kế cho tiến hóa schema

Nếu muốn thêm bảng lịch sử tier sau khi ứng dụng đã chạy:

1. **Expand:** tạo bảng mới, trường tham chiếu bổ sung nếu cần; không xóa cột cũ vội.
2. **Backfill:** lấy các phiên bản tier có nguồn thời gian tin cậy; nếu chỉ có hạng hiện tại, **không bịa lịch sử BRONZE** cho những ngày trước.
3. **Validate:** kiểm tra no-overlap, coverage theo giao dịch, match-count = 1, tổng doanh số theo tier.
4. **Catch-up:** áp thay đổi tier mới/correction theo version hoặc CDC, có idempotency.
5. **Cutover:** cho báo cáo đọc AS-OF history, giám sát khác biệt với bản cũ theo định nghĩa.
6. **Contract:** bỏ đường đọc cũ khi consumer đã xác nhận và có cách rollback.

Một lược đồ vật lý có thể tối ưu dần theo thống kê truy vấn; ngược lại, **grain, khóa và bất biến nghiệp vụ** cần được kiểm chứng trước khi “tối ưu hóa” bằng cách bỏ quan hệ hay nhân bản dữ liệu.

## 15. Bộ bài tập tổng hợp: tự xác định mô hình cho từng phần

Các bài dưới đây dùng **hợp đồng R01–R13 và fixture ở mục 9**. Trước mỗi lời giải, hãy ghi ít nhất:

~~~text
PART / ENTITY:
GRAIN:
PRIMARY KEY:
CANDIDATE/BUSINESS KEYS:
FOREIGN KEYS:
RELATION + CARDINALITY:
ATTRIBUTES: required / nullable / snapshot / derived
INVARIANTS: database / transaction / asynchronous
TESTS: positive / negative / reconciliation
~~~

### Bài 1 — Phân định customer và order trong môi trường nhiều tenant

Hai tenant cùng có customer_id = 10 và order_number = ORD-001. Tenant 1 có order_id = 500 của customer 10; tenant 2 cũng có order_id = 500 của customer 10.

**Yêu cầu:**

1. Đề xuất PK/UNIQUE của customers và orders.
2. Viết FK từ orders tới customers để không tham chiếu sai tenant.
3. Nêu cardinality customer–order và trường hợp order bị xóa/customer bị đổi tên.
4. Vì sao không dùng **customer_id**, **email** hay **order_number đơn lẻ** làm PK toàn hệ thống?
5. Đề xuất hai negative tests.

<details>
<summary>Hướng giải bài 1</summary>

- **customers:** grain một customer trong tenant; PK **(tenant_id,customer_id)**, UNIQUE **(tenant_id,external_customer_code)**, FK tenant_id → tenants.
- **orders:** grain một order trong tenant; PK **(tenant_id,order_id)**, UNIQUE **(tenant_id,order_number)**, FK **(tenant_id,customer_id)** → customers.
- Một customer có thể có nhiều order, nhưng mỗi order thuộc một customer. Đổi display_name không làm thay đổi định danh customer và không được tự sửa **shipping snapshot đã chốt**.
- Email là thông tin liên hệ có thể đổi/trùng; customer_id và order_number chỉ được bảo đảm duy nhất trong tenant.
- Negative test A: order tenant 1 tham chiếu customer_id 20 chỉ tồn tại ở tenant 2 → **FK từ chối**. Negative test B: hai orders của tenant 1 cùng order_number → **UNIQUE từ chối**; nhưng cùng order_number ở hai tenant là hợp lệ.

</details>

### Bài 2 — Một product xuất hiện nhiều lần trong cùng order

Đơn 501 có hai dòng cùng product_id = 101 nhưng thuộc hai chương trình giảm giá khác nhau; các dòng được gán **line_no = 1, 2**.

**Yêu cầu:**

1. Vì sao **(tenant_id,order_id,product_id)** không phải khóa phù hợp?
2. Chọn PK của order_lines, các FK và bất biến quantity/discount.
3. Giá niêm yết product đổi từ 90.000 thành 100.000 sau khi chốt; giá đơn cũ có được thay không?
4. Tính line_net_vnd cho quantity = 2, unit_price = 90.000, discount = 10.000.

<details>
<summary>Hướng giải bài 2</summary>

- Hai dòng có thể cùng product_id, nên PK **(tenant_id,order_id,product_id)** sẽ từ chối dòng hợp lệ. Dùng **(tenant_id,order_id,line_no)**.
- Composite FK tới orders và products đều có tenant_id. **quantity > 0**, **unit_price >= 0**, **0 <= discount <= quantity × unit_price**.
- **unit_price_vnd trên line là snapshot giao dịch**, không thay theo product.list_price_vnd.
- line_net_vnd = **2 × 90.000 − 10.000 = 170.000 VND**.
- Bất biến **không sửa dòng sau PLACED** cần logic chuyển trạng thái/giao dịch hoặc cơ chế bất biến có kiểm toán; CHECK giá trị đơn lẻ không đủ.

</details>

### Bài 3 — Nhiều khoản thanh toán, refund một phần và idempotency

Order tenant 1/order 500 có tổng 310.000. Hai payment attempts CAPTURED là 200.000 và 110.000. Attempt 900 có hai refunds SETTLED 30.000 và 20.000. Một webhook cho refund 800 được gửi lại ba lần.

**Yêu cầu:**

1. Xác định grain/khóa của attempts và refunds.
2. Chọn UNIQUE để không tạo attempt trùng do retry.
3. Tính captured, refunded, net captured.
4. Refund 180.000 mới cho attempt 900 có được SETTLED không? Vì sao?
5. Những ràng buộc nào nằm trong DDL, quy tắc nào cần transaction/đối soát?

<details>
<summary>Hướng giải bài 3</summary>

- **payment_attempts:** một lần thử thu, PK **(tenant_id,attempt_id)**, FK cùng tenant tới order; UNIQUE **(tenant_id,idempotency_key)**, UNIQUE mã provider có giá trị trong đúng phạm vi.
- **refunds:** một khoản refund, PK **(tenant_id,refund_id)**, FK **(tenant_id,attempt_id)**; webhook retry phải nhận ra cùng refund ID/provider reference, không tạo ba refunds mới.
- CAPTURED = **310.000**, refund SETTLED = **50.000**, net captured = **260.000 VND** cho order 500.
- Attempt 900 thu **200.000**. Refund mới **180.000** làm tổng **230.000**, nên **không được SETTLED**.
- CHECK có thể bảo vệ amount > 0 và status; UNIQUE bảo vệ ID/idempotency; FK bảo vệ attempt tồn tại/cùng tenant. **Tổng refund** và **tổng CAPTURED của đơn** cần transaction có khóa/serialization phù hợp, kiểm thử race và đối soát provider.

</details>

### Bài 4 — Giao hàng nhiều chuyến cho một dòng đơn

Tenant 1/order 500/line 1 có quantity = 2. Shipment 700 đã DISPATCHED 1 đơn vị; shipment 701 còn CREATED với 1 đơn vị dự kiến.

**Yêu cầu:**

1. Mô tả quan hệ shipment–order_line và thực thể liên kết.
2. Chọn PK, FK của shipment_lines để không gắn nhầm dòng sang shipment của order khác.
3. Hiện tại đã giao bao nhiêu? Nếu dispatch 701 thì còn bao nhiêu chưa giao?
4. Nếu một shipment mới 703 cũng muốn dispatch thêm 1 đơn vị trước khi 701 dispatch, cần kiểm tra cạnh tranh thế nào?

<details>
<summary>Hướng giải bài 4</summary>

- Một shipment chứa nhiều order_lines và một order_line có thể được chia qua nhiều shipment: **N–M** qua shipment_lines, với thuộc tính **shipped_qty**.
- PK có thể là **(tenant_id,shipment_id,line_no)** vì một line xuất hiện tối đa một lần trong một shipment. FK **(tenant_id,shipment_id,order_id)** → shipments, và **(tenant_id,order_id,line_no)** → order_lines.
- Hiện tại **đã gửi 1/2**; CREATED chưa tính. Nếu dispatch 701 thành công thì **đã gửi 2/2**, còn **0**.
- Với hai shipment cạnh tranh, mọi giao thức dispatch phải khóa cùng order/order_line, tính tổng lượng **đã gửi** cộng lượng **sắp chuyển sang DISPATCHED**, rồi chỉ commit khi không vượt quantity. Nếu một chuyến đã dùng chỗ còn lại thì chuyến kia không được dispatch thêm theo cùng quy tắc.

</details>

### Bài 5 — JOIN cùng một order giữa lines và payments

Order 500 của tenant 1 có hai lines với line_net 220.000 và 90.000; hai CAPTURED attempts với amount 200.000 và 110.000.

**Yêu cầu:**

1. JOIN trực tiếp lines và attempts theo (tenant_id,order_id) sinh bao nhiêu dòng?
2. SUM(line_net_vnd) sau JOIN và SUM(amount_vnd) sau JOIN đều bằng bao nhiêu?
3. Vì sao hai tổng bằng nhau **không** chứng minh đã đối soát?
4. Viết chiến lược SQL tránh fanout.

<details>
<summary>Hướng giải bài 5</summary>

JOIN sinh **2 × 2 = 4 cặp**. Mỗi phía bị nhân đôi: SUM(lines) = **620.000**, SUM(CAPTURED) = **620.000**, trong khi tổng nguồn độc lập đúng là **310.000**.

Phải **tổng hợp lines về (tenant_id,order_id)** và **tổng hợp attempts CAPTURED về (tenant_id,order_id)** riêng, rồi mới JOIN hai tập có tối đa một hàng trên một đơn. Hoặc nếu chỉ cần kiểm tra đơn có ít nhất một payment, dùng **EXISTS** để không nhân rows.

</details>

### Bài 6 — Hạng khách theo thời gian

Khách tenant 1/customer 10:

~~~text
BRONZE: [2026-01-01 00:00 +07, 2026-11-21 00:00 +07)
GOLD:   [2026-11-21 00:00 +07, +infinity)
~~~

Order 500 đặt ngày 20/11 09:00 +07; order 501 đặt ngày 21/11 09:00 +07.

**Yêu cầu:**

1. Hai order thuộc hạng nào tại thời điểm chốt?
2. Vì sao chỉ JOIN bằng customer_id là không đủ?
3. Viết điều kiện AS-OF đúng ở biên đổi hạng.
4. Đề xuất hai bài kiểm thử cho lịch sử.
5. Nếu ngày 23/11 có correction hiệu lực từ 20/11, cần giữ thông tin gì để tái hiện báo cáo cũ?

<details>
<summary>Hướng giải bài 6</summary>

- Order 500 = **BRONZE**, order 501 = **GOLD**.
- JOIN cần **tenant_id + customer_id + placed_at nằm trong [valid_from,valid_to)**. Thiếu tenant làm trộn khách, thiếu thời gian làm fanout hai version.
- Điều kiện: **placed_at >= valid_from AND (placed_at < valid_to OR valid_to IS NULL)**.
- Test 1: không có hai khoảng hiệu lực của cùng khách overlap. Test 2: mọi order PLACED khớp **đúng một** tier tại placed_at, bao gồm trường hợp timestamp đúng biên.
- Khi correction hồi tố, cần snapshot/version dimension của report run đã công bố hoặc **bitemporal system-time** để phân biệt dữ liệu đã biết lúc cũ với sự thật được cập nhật.

</details>

### Bài 7 — Chọn thuộc tính nào cần lưu snapshot?

Product SKU-A của tenant 1 hiện có list_price_vnd 120.000. Sau khi đơn 500 đã chốt, công ty tăng giá sản phẩm lên 150.000 và customer đổi tên/địa chỉ giao mặc định.

**Yêu cầu:**

1. Những thông tin nào trên order/line tuyệt đối không được tự cập nhật từ product/customer?
2. Product và customer vẫn cần lưu giá/địa chỉ hiện tại không?
3. Nếu order_total_vnd được materialize để tăng tốc, cần bảo vệ invariant nào?
4. Đề xuất một negative test và một reconciliation test.

<details>
<summary>Hướng giải bài 7</summary>

- **unit_price_vnd, discount_vnd, quantity đã chốt, shipping_name và shipping_address snapshot** không tự thay đổi theo catalog hoặc customer hiện tại.
- Product vẫn cần **list_price_vnd hiện hành** để báo giá đơn mới; customer vẫn cần hồ sơ liên hệ hiện tại.
- Tổng đơn materialized phải bằng **SUM(line_net_vnd)** của các dòng thuộc đúng đơn/snapshot theo hợp đồng; mọi write path phải cập nhật đồng bộ hoặc hỗ trợ rebuild/đối soát.
- Negative test: sau khi đổi product.list_price_vnd, kiểm tra line_net_vnd của đơn 500 **không đổi**. Reconciliation: so materialized order total (nếu có) với SUM(line_net_vnd) theo (tenant_id,order_id) và liệt kê group lệch.

</details>

### Bài 8 — Đổi một quan hệ từ 1–N thành N–M

Phiên bản đầu yêu cầu **một shipment chỉ giao toàn bộ một order**, không chia theo dòng. Bản mới cho phép tách dòng giữa nhiều shipment và gom nhiều dòng vào một shipment.

**Yêu cầu:**

1. Grain nào mới xuất hiện?
2. Vì sao chỉ thêm một mảng line_no vào shipments có thể khó kiểm chứng?
3. Những khóa và bất biến mới cần được xác lập?
4. Nêu kế hoạch migration không mất những shipment lịch sử.

<details>
<summary>Hướng giải bài 8</summary>

- Thực thể mới là **shipment_lines**, grain một line của một order được phân bổ trong một shipment.
- Mỗi allocation có **shipped_qty**, trạng thái có thể nằm ở shipment; nếu lưu mảng, khó bảo vệ FK/trùng line_no/tổng lượng giao trong một RDBMS thông thường.
- PK theo tenant/shipment/line_no, FK tới shipment cùng order và order_line, CHECK shipped_qty > 0; giao thức dispatch đảm bảo tổng đã giao không vượt quantity.
- Migration: expand schema mới; backfill shipment lịch sử thành các allocation có nguồn chứng cứ đáng tin; đối soát lượng giao theo order line; chuyển writer/readers theo phiên bản; giữ rollback/lineage; **không tự chia số lượng cũ theo phỏng đoán** khi nguồn không có chi tiết line.

</details>

### Bài 9 — Kiểm thử mô hình sau khi tích hợp thêm một nguồn

Hệ thống nhận refund webhook từ một dịch vụ ngoài. Một webhook có thể được gửi lại; bản ghi hoàn tiền có thể đến trước khi snapshot của payment attempt được đồng bộ vào kho phân tích. Nhóm đề xuất nối hai nguồn bằng **attempt_id** rồi lập tức SUM mọi khoản hoàn.

**Yêu cầu:**

1. Chỉ ra ít nhất ba rủi ro trong thiết kế.
2. Xác định source identity, grain và trạng thái cần lưu.
3. Phân biệt **orphan thật** với **dữ liệu đến trễ**.
4. Đề xuất những kiểm tra chất lượng trước khi công bố báo cáo.

<details>
<summary>Hướng giải bài 9</summary>

- **attempt_id có thể trùng giữa tenant** hoặc giữa các provider; JOIN phải kèm namespace/tenant.
- Webhook retry có thể nhân refund nếu thiếu **refund event ID/provider reference và idempotency**.
- Event REQUESTED/FAILED không được cộng như SETTLED; hợp đồng nghiệp vụ phải phân biệt trạng thái.
- Payment snapshot đến trễ có thể tạo **unmatched refund tạm thời**, không nhất thiết là không có attempt. Nên quarantine/defer hoặc đánh dấu pending để retry khi nguồn bắt kịp.
- Trước công bố, kiểm tra tập refund unique theo source ID; attempt tồn tại và CAPTURED trong cùng tenant; tổng SETTLED <= CAPTURED; checkpoint/watermark cả hai nguồn đạt chính sách; đối soát provider và phiên bản run/cutoff.

</details>

### Bài 10 — Trình bày ADR cho lựa chọn mô hình

Bạn phải chọn một thiết kế cho hai nhu cầu:

- API tra cứu **toàn bộ một order với các lines** được gọi liên tục.
- Báo cáo tài chính **theo tenant/ngày**, cần đối soát từng payment/refund và lưu lịch sử.

**Yêu cầu:** so sánh mô hình quan hệ với document, nêu điểm đặt source of truth, cơ chế xây read model, ba bất biến bắt buộc, chỉ mục trọng yếu và một phương án triển khai tiến hóa dần.

<details>
<summary>Hướng giải bài 10</summary>

Một ADR hợp lý có thể chọn **PostgreSQL quan hệ làm nguồn chuẩn** cho orders, lines, payment/refund và shipment vì cần FK, transaction và khả năng đối soát. API đọc order có thể dùng **read model dạng document** chứa snapshot của order/lines, được tái dựng từ nguồn chuẩn với version/checkpoint. Data mart doanh số theo ngày được tạo từ **fact/sự kiện có khóa nguồn và thời gian rõ**, không SUM trực tiếp trên một JOIN nhân dòng.

Ba bất biến tối thiểu: (1) line thuộc đúng order/tenant và có khóa duy nhất; (2) refund SETTLED không vượt CAPTURED, bảo vệ khi cạnh tranh; (3) báo cáo bảo toàn số đo theo đúng grain/cutoff. Index có thể gồm **orders(tenant_id,order_id)** từ PK, **order_lines(tenant_id,order_id,line_no)** từ PK và **payment_attempts(tenant_id,order_id,status)** cho tổng hợp.

Tiến hóa bằng **expand → backfill/read model → đối soát → shadow read → cutover → contract**, có idempotency và rollback. Lựa chọn cụ thể phụ thuộc workload, không khẳng định relational hay document luôn thắng.

</details>

## 16. Bộ kiểm tra tự động và thang tự đánh giá

### 16.1. Assertion dữ liệu cơ sở trên fixture

Sau khi nạp dữ liệu ở mục 9, có thể chạy một khối **DO** để xác nhận số lượng/tổng tiền kỳ vọng:

~~~sql
DO $$
DECLARE
    v_order_count BIGINT;
    v_line_count BIGINT;
    v_line_sum NUMERIC;
    v_captured_sum NUMERIC;
    v_refund_sum NUMERIC;
    v_dispatched_qty BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_order_count FROM orders;

    SELECT COUNT(*), COALESCE(SUM(line_net_vnd), 0)
    INTO v_line_count, v_line_sum
    FROM order_lines;

    SELECT COALESCE(SUM(amount_vnd), 0)
    INTO v_captured_sum
    FROM payment_attempts
    WHERE status = 'CAPTURED';

    SELECT COALESCE(SUM(amount_vnd), 0)
    INTO v_refund_sum
    FROM refunds
    WHERE status = 'SETTLED';

    SELECT COALESCE(SUM(sl.shipped_qty), 0)
    INTO v_dispatched_qty
    FROM shipment_lines AS sl
    JOIN shipments AS s
      ON s.tenant_id = sl.tenant_id
     AND s.shipment_id = sl.shipment_id
     AND s.order_id = sl.order_id
    WHERE s.status IN ('DISPATCHED', 'DELIVERED');

    IF v_order_count <> 3
       OR v_line_count <> 4
       OR v_line_sum <> 580000
       OR v_captured_sum <> 580000
       OR v_refund_sum <> 50000
       OR v_dispatched_qty <> 5
    THEN
        RAISE EXCEPTION
            'Fixture mismatch: orders=%, lines=%, line_vnd=%, captured=%, refund=%, shipped=%',
            v_order_count, v_line_count, v_line_sum,
            v_captured_sum, v_refund_sum, v_dispatched_qty;
    END IF;

    RAISE NOTICE
        'PASS: fixture tổng hợp đạt các giá trị kỳ vọng';
END $$;
~~~

Nếu chạy lại INSERT fixture vào cùng schema mà không dọn dữ liệu, primary key có thể báo trùng; đây là **dữ liệu thử cố định**, không phải ETL idempotent hoàn chỉnh. Để tự thực hành nhiều lần, dùng schema riêng rồi dựng lại có kiểm soát; **không chạy DROP CASCADE trên database có dữ liệu quan trọng**.

### 16.2. Checklist theo từng phần

| Phần | Khóa/thuộc tính | Quan hệ | Bất biến cần chứng minh |
| --- | --- | --- | --- |
| Tenant/customer | PK và UNIQUE đúng phạm vi; email không phải ID | Customer → tenant | Hai tenant trùng mã local không giao thoa |
| Product/catalog | SKU theo tenant; giá hiện hành | Product → lines | Giá niêm yết đổi không sửa line snapshot |
| Order | PK composite; placed_at; snapshot địa chỉ | Customer 1–N Order | PLACED có lines, không sửa snapshot tùy ý |
| Order line | PK (tenant,order,line_no); giá/qty | Order 1–N Lines | Qty dương, discount hợp lệ, product cùng tenant |
| Payment attempt | attempt PK, provider/idempotency key | Order 1–N Attempts | Retry không nhân capture, tổng thu không vượt quy tắc |
| Refund | refund PK, status, số tiền | Attempt 1–N Refunds | Chỉ SETTLED được tính, tổng hoàn <= số thu |
| Shipment | shipment PK, trạng thái | Order 1–N Shipments | Chuyển dispatch theo transaction |
| Shipment allocation | line PK theo shipment, shipped_qty | N–M Shipment–OrderLine | Cùng order/tenant; tổng giao <= đặt |
| Customer tier history | version key, khoảng hiệu lực | Customer 1–N versions | Không overlap, AS-OF match = 1 |
| Báo cáo | Grain group và metric version | JOIN các nguồn đã tổng hợp | Không fanout, không thiếu group, không trộn tenant |

### 16.3. Thang đánh giá bài làm (gợi ý 100 điểm)

| Tiêu chí | Điểm |
| --- | ---: |
| Xác định đúng **grain** và phân biệt entity/snapshot/derived | 15 |
| Khóa ứng viên, PK/UNIQUE có **phạm vi tenant** chính xác | 15 |
| FK, bội số quan hệ và thực thể liên kết N–M | 15 |
| Thuộc tính, domain, thời gian, giá trị NULL, lịch sử | 15 |
| Bất biến khai báo và bất biến giao dịch có cạnh tranh | 20 |
| SQL đối soát, JOIN đúng grain và negative tests | 15 |
| Giải thích đánh đổi và kế hoạch tiến hóa mô hình | 5 |
| **Tổng** | **100** |

Một bài đạt điểm cao phải có **bằng chứng** cho những kết luận quan trọng, không chỉ liệt kê tên các bảng. Ví dụ, phát biểu “refund không vượt captured” cần chỉ ra **nó được kiểm ở đâu và race condition được ngăn thế nào**; phát biểu “dữ liệu không lẫn tenant” cần PK/FK, truy vấn và quyền đọc phù hợp.

### 16.4. Test biến đổi đầu vào để bắt lỗi tiềm ẩn

Ngoài fixture cố định, thử các biến đổi có kiểm soát:

1. Thêm product mới ở tenant 2 có cùng SKU với tenant 1: **hợp lệ**.
2. Thêm product cùng SKU vào tenant 1: **UNIQUE từ chối**.
3. Thêm một payment attempt FAILED cho order 500: **tổng CAPTURED không đổi**.
4. Thêm một refund REQUESTED nhưng chưa SETTLED: **net captured không đổi**.
5. Sửa tên customer hiện tại: **shipping snapshot trên orders không đổi**.
6. Đổi list_price_vnd hiện tại: **line_net_vnd trên đơn cũ không đổi**.
7. Thêm shipment CREATED: **dispatched_qty không đổi**.
8. Thêm tier lịch sử có khoảng overlap: **exclusion constraint hoặc test overlap báo lỗi**.
9. Thêm một attempt CAPTURED mới cho order 500: **doanh số dòng đơn vẫn 310.000**, không bị nhân dù số attempt tăng.
10. Thử JOIN mà bỏ tenant_id: dữ liệu trùng ID giữa các tenant phải giúp test **phát hiện kết quả sai hoặc leakage**.

Mỗi negative/metamorphic test cần chạy ở nơi được phép và có cách rollback/khôi phục fixture; không dùng production làm sân thử các ràng buộc có chủ đích vi phạm.

## 17. Những sai lầm cần tránh khi xác định từng phần

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Mọi ID đều phải duy nhất toàn hệ thống.” | Nhiều mã chỉ duy nhất trong tenant hoặc nguồn. | Ghi rõ phạm vi unique, chọn composite key đúng. |
| “Email hoặc tên khách đủ làm khóa.” | Có thể đổi, thiếu hoặc trùng. | Dùng customer identity ổn định; email là thuộc tính. |
| “Product đã có giá, order line không cần lưu giá.” | Giá hiện tại thay đổi, làm mất giá trị lúc mua. | Giữ unit_price/discount snapshot khi chốt. |
| “Một đơn chứa nhiều product thì order_id là PK dòng.” | Sẽ không lưu được nhiều dòng của cùng đơn. | PK gồm line_no hoặc line_id đúng grain. |
| “Cùng product chỉ xuất hiện một lần trong order.” | Có thể nhiều chương trình giá/đợt fulfillment. | Không dùng product_id làm khóa dòng nếu không được hợp đồng bảo đảm. |
| “Đặt FK customer_id là đủ cho đa tenant.” | Dễ ghép nhầm customer cùng ID ở tenant khác. | FK và JOIN cùng tenant, kiểm tra authorization. |
| “Có FK là bảo vệ tất cả quan hệ.” | Có thể nối shipment với order_line khác order nếu khóa không chứa order_id. | FK composite đến cặp quan hệ được phép. |
| “CHECK có thể kiểm SUM các refunds.” | CHECK trên hàng không tự biết tổng các hàng khác. | Transaction/locking, ledger và đối soát. |
| “Chỉ cần validate ở API.” | Webhook, batch, admin hoặc service khác cũng có thể ghi. | Chốt write paths, bảo vệ DB khi khả thi. |
| “UNIQUE idempotency tự bảo đảm exactly-once toàn hệ thống.” | Giao dịch ngoài, webhook/retry vẫn có thể lặp. | Source ID, response replay, trạng thái và reconciliation. |
| “Refund REQUESTED đã là tiền hoàn.” | Có thể thất bại hoặc chưa quyết toán. | Tách trạng thái, chỉ cộng SETTLED theo contract. |
| “Shipment CREATED là đã giao.” | Có thể còn soạn hoặc bị hủy. | Tổng shipped chỉ dựa trên trạng thái có hiệu lực. |
| “JOIN hai bảng rồi SUM có vẻ đúng là đủ.” | 2 lines × 2 payments làm nhân tiền. | Tổng hợp đúng grain trước JOIN và đối soát nguồn. |
| “COUNT(DISTINCT order_id) luôn đúng.” | Order ID có thể lặp giữa tenant. | COUNT DISTINCT theo (tenant_id,order_id). |
| “Địa chỉ customer hiện tại là lịch sử giao hàng.” | Người dùng có thể sửa địa chỉ sau đặt. | Snapshot tại chốt đơn, version khi cần. |
| “SCD có customer_sk nên không cần điều kiện AS-OF.” | Việc gán surrogate key có thể sai thời điểm. | Kiểm match theo business key + valid-time. |
| “Không-overlap nghĩa là lúc nào cũng có bản lịch sử.” | Vẫn có gap hoặc bản đến trễ. | Kiểm coverage của fact, phân biệt missing/unknown. |
| “Tổng tiền bằng nhau chứng tỏ không sai.” | Hai lỗi có thể bù trừ; hai bên JOIN có thể cùng bị nhân. | So ID, per-order/per-tenant groups và giá trị. |
| “Thêm partition là tự chia tải whale tenant.” | Hash theo tenant vẫn để một tenant ở một nơi. | Đo workload; cân nhắc bucket/dedicated tenant. |
| “Đổi schema là có thể xóa dữ liệu cũ ngay.” | Chưa backfill/catch-up hoặc còn consumer. | Expand → backfill → validate → cutover → contract. |

### 17.1. Phân biệt lỗi dữ liệu và ngoại lệ nghiệp vụ hợp lệ

Không phải mọi điều trông bất thường đều sai:

- **Một order chưa có payment** có thể hợp lệ nếu còn chờ thanh toán.
- **Một shipment giao chưa đủ số lượng** có thể hợp lệ vì giao nhiều đợt.
- **Một refund REQUESTED nhưng chưa SETTLED** không phải số tiền đã chuyển.
- **Một customer không có tier tại một mốc** có thể cần trạng thái Unknown hoặc chờ dimension đến trễ, tùy contract.
- **Một sản phẩm có giá 0** có thể là hàng tặng theo chương trình hợp lệ.
- **Hai tenant cùng order_id** là hợp lệ trong phạm vi đã định nghĩa.

Việc đánh dấu dữ liệu “lỗi” phải xuất phát từ **bất biến đã xác nhận với nghiệp vụ**, không chỉ từ trực giác hoặc một tập dữ liệu mẫu quá sạch.

### 17.2. Mẫu câu trả lời ngắn cho buổi review thiết kế

Một nhóm có thể trình bày mỗi phần bằng năm câu:

> **Grain:** một hàng của bảng này biểu diễn ...  
> **Key:** PK là ...; mã nghiệp vụ duy nhất trong phạm vi ...  
> **Relation:** bảng này liên hệ ... theo ...; FK bảo vệ ...  
> **Attributes:** các thuộc tính snapshot là ...; các số đo dẫn xuất là ...  
> **Invariant:** database chặn ...; transaction bảo vệ ...; đối soát phát hiện ...

Nếu thiếu một trong năm câu, phần ấy nên được đánh giá lại trước khi triển khai API, viết ETL hoặc chọn chiến lược sharding.

## 18. Ghi nhớ

Bài tập này xoay quanh **một phương pháp thống nhất**: từ yêu cầu nghiệp vụ, xác định **thực thể và grain**, sau đó chọn **khóa và phạm vi duy nhất**, phát biểu **quan hệ/cardinality**, phân loại **thuộc tính hiện hành, snapshot, dẫn xuất, lịch sử**, cuối cùng viết thành **bất biến có nơi thực thi và phép kiểm chứng rõ**.

Trong tình huống OrderHub, composite keys bảo vệ tenant; order_lines giữ giá chốt thay vì đọc giá catalog hiện hành; payment/refund và shipment có grain riêng nên cần tổng hợp **trước khi JOIN**; giao dịch đồng thời đòi hỏi khóa và kiểm tra số dư/số lượng trên cùng phạm vi; customer tier lịch sử cần **AS-OF JOIN theo khoảng [from,to)**. Một bảng mới, một chỉ mục mới hoặc một lựa chọn lưu dữ liệu khác không thay thế các quy tắc ấy.

Khi làm dự án thật, thứ tự hữu ích là **chốt hợp đồng và các giả định → vẽ thực thể/quan hệ → thiết kế khóa và DDL → xây fixture có tình huống khó → chạy negative/reconciliation tests → bảo vệ cạnh tranh → kiểm thử lịch sử và tenant isolation → đánh giá hiệu năng → triển khai có backfill, cutover và rollback**. Mô hình tốt không chỉ lưu được những bản ghi hợp lệ; nó phải **ngăn được những trạng thái bất hợp lệ, giải thích được dữ liệu lịch sử và có thể tiến hóa an toàn**.
