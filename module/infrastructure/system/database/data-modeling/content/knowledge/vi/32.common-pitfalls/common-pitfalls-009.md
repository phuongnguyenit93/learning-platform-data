# Dư thừa dữ liệu nhưng không có nguồn chuẩn hoặc quy tắc đồng bộ

## Mục tiêu học tập

Một ứng dụng bán hàng thường có nhiều bản sao của cùng một thông tin: tên sản phẩm nằm trong danh mục, kết quả tìm kiếm, dòng đơn đã bán và báo cáo; tên khách hàng có thể nằm ở hồ sơ, hóa đơn và địa chỉ nhận hàng. **Dư thừa dữ liệu không tự động là lỗi**. Lỗi xuất hiện khi các bản sao **được dùng như dữ liệu hiện hành nhưng không ai biết bản nào có thẩm quyền**, hoặc **không có quy tắc khi giá trị thay đổi, thông điệp đến trễ, cập nhật thất bại và dữ liệu mâu thuẫn**.

Ví dụ, sản phẩm P01 có giá niêm yết 100.000 đồng trong Catalog, 120.000 đồng trong Search và 90.000 đồng trên dòng đơn lịch sử. Ba số khác nhau có thể đều **đúng** nếu chúng lần lượt là **giá hiện hành trước đồng bộ, giá từ một bản sao lỗi hoặc mới hơn, và giá khách đã chấp nhận tại thời điểm mua**. Ngược lại, nếu cả Catalog và Search đều khẳng định mình lưu **giá niêm yết hiện hành** mà không có nguồn chuẩn, sự khác biệt trở thành lỗi tính nhất quán.

Bài thuộc chương **Lỗi thường gặp** của module **DATABASE_DATA_MODELING**. Theo mục tiêu module, người học rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu từ thực thể, quan hệ, ràng buộc tới chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; so sánh dữ liệu quan hệ, document, đồ thị và phân tích để lựa chọn cấu trúc dễ tiến hóa và kiểm chứng. Bài tập trung vào **cách nhận biết và sửa kiểu dư thừa dữ liệu không được quản trị**.

Sau bài học, bạn có thể:

1. Phân biệt **trùng lặp có chủ đích** (snapshot, cache, projection, read replica, materialized aggregate) với **dữ liệu bị sao chép nhưng quyền sở hữu mơ hồ**.
2. Xác định **nguồn có thẩm quyền theo thuộc tính, phạm vi, thời gian và trạng thái**, không chỉ chọn một database làm “nguồn chuẩn cho mọi thứ”.
3. Định nghĩa **hợp đồng đồng bộ** gồm sự kiện kích hoạt, khóa định danh, phiên bản, chính sách xung đột, độ trễ, retry, idempotency và đối soát.
4. Giải thích khi nào cần **nhất quán mạnh trong một giao dịch**, khi nào có thể chấp nhận **eventual consistency** và cách diễn đạt giới hạn độ mới của bản sao.
5. Minh họa PostgreSQL với **Catalog sở hữu sản phẩm**, **Search là bản đọc**, **Sales giữ snapshot giao dịch**, cùng outbox và một consumer cập nhật projection có kiểm tra phiên bản.
6. Viết truy vấn nhận diện **bản sao quá cũ, mâu thuẫn cùng phiên bản, thiếu ánh xạ và dữ liệu lịch sử bị ghi đè**.
7. Đánh giá các lỗi phổ biến như **dual-write không nguyên tử, CDC thiếu hợp đồng ngữ nghĩa, sự kiện gửi lặp, cập nhật đảo thứ tự và last-write-wins tùy tiện**.
8. Thiết kế lộ trình khắc phục, bộ kiểm thử và checklist vận hành khi hệ thống đã có nhiều bản sao đang được sử dụng.

> **Phạm vi:** Ví dụ và mã SQL là công cụ học tập trên PostgreSQL, không phải một hệ thống event broker hay ETL hoàn chỉnh. Những thao tác cố tình gây lệch chỉ được thực hiện trong môi trường thử nghiệm. Bài không giả định mọi hệ thống đều cần microservice hoặc một database riêng cho từng mô hình.

## 1. Nhận diện lỗi từ một tình huống cụ thể

### 1.1. Ba nơi cùng giữ giá sản phẩm

Giả sử cửa hàng có ba kho dữ liệu:

| Nơi lưu | Dòng dữ liệu | Ai sử dụng? |
| --- | --- | --- |
| **Catalog DB** | P01, list_price = 100.000 VND | Trang quản trị danh mục |
| **Search index** | P01, list_price = 120.000 VND | Trang tìm kiếm sản phẩm |
| **Sales DB** | Order O100, P01, accepted_price = 90.000 VND | Lịch sử đơn và hóa đơn |

Trước khi kết luận giá nào sai, cần hỏi **ba giá đang biểu diễn cùng một sự thật hay các sự thật khác nhau?**

- Catalog.list_price có thể là **giá niêm yết hiện tại**.
- Search.list_price có thể là **bản sao của giá niêm yết hiện tại**. Nếu vậy, nó phải có nguồn Catalog, quy tắc làm mới và một mức độ trễ cho phép.
- Sales.accepted_price là **giá chốt khi mua**. Đây là dữ kiện lịch sử có ngữ nghĩa riêng; **không nên đồng bộ đè thành giá Catalog hiện tại**.

Nếu đội Search tự cập nhật giá trực tiếp trong index, đồng thời đội Catalog sửa giá trong DB, hai bên đang có **hai nguồn ghi cạnh tranh** mà không có quy tắc hòa giải. Đó chính là anti-pattern của bài.

### 1.2. Hai sai lầm đối lập

**Sai lầm A — Coi mọi bản sao là nguồn sự thật:**

~~~~text
Catalog.updatePrice(P01, 110000)
Search.adminEditPrice(P01, 120000)
Sales.repriceHistoricalOrders(P01, 110000)
~~~~

Hậu quả: Search và Catalog mâu thuẫn; hóa đơn lịch sử mất giá chốt; không biết sửa nơi nào để hệ thống hội tụ.

**Sai lầm B — Cấm mọi dư thừa dữ liệu:**

~~~~text
Mỗi truy vấn tìm kiếm phải gọi Catalog DB.
Mỗi lần mở đơn lịch sử phải tra tên/giá hiện hành từ Catalog.
Mọi báo cáo phải JOIN trực tiếp toàn bộ database tác nghiệp.
~~~~

Hậu quả: tăng ghép nối, giảm khả năng phục vụ đọc, không giữ được snapshot lịch sử, có thể làm sai ngữ nghĩa của đơn. **Chuẩn hóa là công cụ bảo vệ phụ thuộc dữ liệu, không phải mệnh lệnh xóa mọi bản sao có mục đích khác nhau**.

### 1.3. Dấu hiệu cảnh báo

Một hệ thống có nguy cơ dư thừa không kiểm soát khi:

1. Hai hệ thống có thể **cùng sửa một thuộc tính hiện hành** mà không ai giải quyết xung đột.
2. Có nhiều bảng mang tên customer, product, order nhưng **không có hợp đồng ý nghĩa** của các trường lặp.
3. Một job “đồng bộ” chỉ sao chép tất cả hàng theo lịch, **không kiểm tra record nào mới hơn**.
4. Consumer có thể xử lý lại cùng một event và **cộng số tiền hoặc lượng tồn lần nữa**.
5. Không ai trả lời được “mất bao lâu thì bản sao phải cập nhật?”.
6. Một dữ liệu có vẻ lỗi bị “sửa” ở read model, nhưng **bên sở hữu vẫn phát giá trị cũ**.
7. Có cột updated_at ở mọi nơi nhưng **không có định nghĩa về đồng hồ, timezone, version và ai được ghi cột ấy**.
8. Những dữ liệu cần bất biến lịch sử bị job đồng bộ **ghi đè bằng giá trị hiện tại**.
9. Sau sự cố, nhóm vận hành không biết nên **backfill, replay, restore hay sửa thủ công**.

**Phép chẩn đoán ngắn:** Với mỗi thuộc tính bị lặp, hãy hỏi **nghĩa gì – ai quyết định – có hiệu lực khi nào – bản sao được cập nhật thế nào – lúc lệch xử lý ra sao?** Nếu không trả lời được, trước tiên phải thiết kế hợp đồng, không chỉ thêm một cron job.

## 2. Phân loại những dạng dư thừa cần đánh giá khác nhau

| Dạng lặp dữ liệu | Ví dụ | Có thể hợp lệ khi | Rủi ro chính |
| --- | --- | --- | --- |
| **Snapshot nghiệp vụ** | Tên/giá lúc đặt đơn | Cần bảo tồn điều kiện giao dịch đã chốt | Bị cập nhật theo giá hiện hành, mất lịch sử |
| **Cache** | Giá sản phẩm trên Redis | Tối ưu truy vấn; có TTL/invalidation | Trả kết quả quá hạn, cache stampede |
| **Read projection** | Sản phẩm trong Search index | Dùng để tìm kiếm với độ trễ có giới hạn | Sự kiện đến trễ hoặc lỗi transform |
| **Read replica** | Replica PostgreSQL | Cần mở rộng đọc, có giám sát lag | Đọc bản sao chưa bắt kịp primary |
| **Denormalization cục bộ** | customer_display_name trên bảng tổng quan đơn | Phục vụ access pattern cụ thể, có nguồn và quy tắc | Update anomaly nếu tên hiện tại cần nhất quán |
| **Materialized aggregate** | Tổng bán theo tháng–nhóm | Có định nghĩa grain, cách refresh/rebuild | Cộng trùng, sai watermark, không xử lý event sửa |
| **Warehouse/analytics** | Fact bán, dimension sản phẩm | Có ETL, lineage và định nghĩa lịch sử | Bản ghi muộn, SCD, sai đơn vị đo |
| **Master data / golden record** | Danh tính khách hợp nhất từ CRM và ERP | Có quy tắc matching, survivorship, steward | Gộp sai người, chọn giá trị không có thẩm quyền |
| **Hai nguồn ghi độc lập** | Catalog và Search cùng sửa list_price | Chỉ khi có giao thức hợp nhất rõ, được kiểm chứng | Xung đột, lost update, trạng thái không hội tụ |

**Cùng số byte không có nghĩa cùng dữ kiện:** Snapshot giá bán và giá niêm yết hiện hành là hai thuộc tính nghiệp vụ khác nhau. Ngược lại, cùng tên cột không có nghĩa dữ liệu có cùng nghĩa.

### 2.1. Snapshot và cache không dùng cùng quy tắc cập nhật

Khi Catalog đổi tên từ “Sổ tay A5” thành “Sổ tay bìa cứng A5”:

- **Search projection:** nên cập nhật theo hợp đồng Catalog nếu đang hiển thị tên hiện hành.
- **Cache giá hiện tại:** nên invalidation hoặc refresh theo chính sách.
- **SalesOrderLine.product_name_at_purchase:** thường **giữ nguyên** tên chốt ở giao dịch.
- **Báo cáo lịch sử:** dùng tên tại thời điểm bán hoặc tên hiện tại tùy chỉ số đã được định nghĩa.

Một job “UPDATE mọi bản sao cho bằng Catalog” có thể làm cache đúng hơn nhưng **phá snapshot**. Vì thế trước khi đồng bộ, phải phân loại **bản sao cần hội tụ** và **dữ liệu cần giữ bất biến**.

### 2.2. Dư thừa do phi chuẩn hóa có chủ đích

Giả sử một bảng ORDER_OVERVIEW lưu:

~~~~text
order_id
buyer_id
buyer_display_name
total_amount
payment_summary_status
shipment_summary_status
last_refreshed_at
~~~~

Nếu buyer_display_name là **tên hồ sơ hiện tại để hiển thị nhanh**, bảng này là projection và phải có quy tắc cập nhật. Nếu buyer_display_name là **tên người đặt tại thời điểm mua**, nó là snapshot và không tự đổi khi hồ sơ khách cập nhật.

Điều nguy hiểm không phải sự lặp mà là **một cột có hai cách hiểu** trong cùng ứng dụng. Để tránh điều đó, đặt tên có nghĩa: **buyer_name_at_purchase** và **current_buyer_display_name** thay vì hai cột cùng gọi name không có hợp đồng.

## 3. Nguồn chuẩn là khái niệm có phạm vi, không phải khẩu hiệu

### 3.1. Nguồn chuẩn, nguồn ghi và hệ thống đối soát

Cần phân biệt những khái niệm gần nhau:

- **System of record (SoR):** nơi được tổ chức công nhận là ghi nhận/duy trì một loại dữ liệu nghiệp vụ.
- **Authoritative source / source of truth:** nguồn có thẩm quyền quyết định **giá trị nào được coi là đúng trong một phạm vi và thời điểm**.
- **Golden record:** bản hợp nhất của nhiều nguồn theo quy tắc định danh, ưu tiên, xác minh và survivorship; không mặc định là nơi mọi bên được ghi tùy ý.
- **Read model / projection:** dữ liệu dẫn xuất để trả lời truy vấn; có thể tạm trễ nguồn.
- **Snapshot:** dữ kiện được chốt ở một sự kiện lịch sử, có nguồn/điều kiện riêng; không đơn giản là bản sao hiện tại.

Các từ có thể được tổ chức dùng khác nhau. Điều bắt buộc là **mô tả quyền sở hữu và quy tắc cập nhật**, không chỉ gắn nhãn “single source of truth” cho một database.

### 3.2. Chọn thẩm quyền theo từng thuộc tính

Ví dụ ma trận quyền sở hữu:

| Dữ kiện | Nguồn có thẩm quyền | Bản đọc/bản sao | Ai được thay đổi? |
| --- | --- | --- | --- |
| Tên sản phẩm hiện tại | Catalog | Search, trang danh sách, cache | Catalog theo quy trình công bố |
| Giá niêm yết hiện tại | Catalog/Pricing theo hợp đồng phân quyền cụ thể | Search, cache | Bên chịu trách nhiệm định giá |
| Giá đã chấp nhận trong đơn | SalesOrderLine | Hóa đơn, báo cáo giao dịch theo hợp đồng | Chỉ quy trình sửa/điều chỉnh đơn được phép |
| Số lượng còn khả dụng | Inventory | Trang sản phẩm, cache | Inventory trong transaction giữ/xuất hàng |
| Số tiền đã quyết toán | Payments/Billing | Order overview, dashboard | Payments/Billing theo kết quả có thẩm quyền |
| Trạng thái vận đơn | Fulfillment | Tracking UI, thông báo khách | Fulfillment theo sự kiện giao nhận |
| Email đăng nhập hiện tại | Identity | Projection có quyền sử dụng | Identity/người dùng qua luồng hợp lệ |
| Địa chỉ nhận của đơn đã chốt | Sales/Fulfillment theo điều kiện nghiệp vụ | Chứng từ giao nhận | Quy trình sửa địa chỉ giao cụ thể |

Trong ví dụ, **Catalog có thể sở hữu tên hiện tại, Sales sở hữu giá lịch sử, Inventory sở hữu tồn kho**. Không cần ép cả ba vào một thực thể UNIVERSAL_PRODUCT.

### 3.3. Trục thời gian của sự thật

Cùng một product_id nhưng:

~~~~text
Catalog:
  price_current = 120000 tại 2026-11-22

Sales:
  price_at_purchase = 90000 tại 2026-10-01

Analytics:
  price_as_of_sale = 100000 theo chính sách phân loại giá lúc bán
~~~~

Ba trường không buộc phải bằng nhau. Để kiểm tra:

1. Giá hiện tại cần được hỏi **ở thời điểm nào**?
2. Giá lịch sử có được **ghi chốt thành snapshot** không?
3. Event_time và processed_at có khác nhau không?
4. Báo cáo cần trạng thái **as-of** tại lúc bán hay **hiện hành**?
5. Có cần lưu **valid_from/valid_to** hoặc version để dựng lại lịch sử không?

**Không đối soát các trường khác nghĩa bằng điều kiện bằng nhau.** Phép đối soát đúng trước tiên phải khớp **ngữ nghĩa, phạm vi và thời điểm**.

### 3.4. Khóa định danh và phạm vi

Nếu SKU NOTE-A5 chỉ duy nhất trong mỗi tenant, đồng bộ bằng SKU mà không mang tenant có thể gộp sai sản phẩm:

~~~~text
tenant A / NOTE-A5 → Product P01
tenant B / NOTE-A5 → Product P99
~~~~

Hợp đồng định danh cần nêu rõ business key, chẳng hạn **(tenant_id, product_id)**, hoặc một UUID thật sự toàn cục có mapping xác thực. **Cùng chuỗi ID** không tự chứng minh cùng thực thể; đồng bộ sai khóa nguy hiểm hơn việc dữ liệu tạm cũ.

### 3.5. Quy tắc chủ sở hữu của mỗi bản sao

Một bản sao cần được mô tả ít nhất:

~~~~text
COPY: search_product_projection
Purpose: Tìm kiếm tên/giá niêm yết hiện hành.
Authority: Catalog product list state.
Key: (tenant_id, product_id) hoặc product_id globally unique.
Source version: catalog.version tăng đơn điệu cho mỗi product.
Refresh: Integration event chứa trạng thái đầy đủ hoặc pull snapshot.
Consistency: Eventual; có định nghĩa ngưỡng staleness và fallback.
Writes: Chỉ projection worker; admin không sửa giá trực tiếp.
Conflict: Version cũ/trùng thì không ghi đè phiên bản mới hơn.
Missing/gap: Có reconciliation và rebuild.
Expiry/deletion: Unpublish/tombstone theo chính sách.
Owner: Nhóm Catalog cho dữ kiện, nhóm Search cho projection.
~~~~

Một cron job “đẩy giá mỗi đêm” **không đủ** nếu không định nghĩa trường hợp **xóa sản phẩm, hai cập nhật liên tiếp, job chạy chồng, thất bại giữa chừng và truy vấn trước khi job chạy**.

## 4. Hợp đồng đồng bộ: phải viết rõ trước khi chọn công nghệ

Một **synchronization contract** là bộ quy tắc quy định bản sao **được tạo, cập nhật, nhận diện độ mới, xóa, phục hồi và kiểm chứng** như thế nào. Công nghệ API, CDC, broker hoặc batch chỉ là cách thực hiện một phần hợp đồng.

### 4.1. Mười câu hỏi của một hợp đồng đồng bộ

1. **Đích là gì?** Cache, search projection, snapshot hay một thực thể đồng sở hữu?
2. **Nguồn chuẩn ở đâu?** Theo thuộc tính nào, ở tenant/thị trường nào, với quyền sửa nào?
3. **Định danh nào dùng để nối?** PK nội bộ, business ID, tenant ID và version có nghĩa gì?
4. **Khi nào cần đồng bộ?** Sau khi commit sự kiện, theo lịch, lúc đọc hay khi có thay đổi chính sách?
5. **Payload thể hiện gì?** Trạng thái đầy đủ (*full state*) hay thay đổi gia tăng (*delta*)? Có schema version?
6. **Thứ tự được xử lý ra sao?** Có aggregate version tăng đơn điệu, partition ordering hoặc cơ chế phát hiện gap không?
7. **Gửi trùng được xử lý thế nào?** Event ID, request ID, inbox và transaction cục bộ?
8. **Lỗi và xung đột được giải quyết ra sao?** Retry, quarantine, replay, manual review hay áp chính sách hợp nhất rõ?
9. **Bản sao có được cũ đến mức nào?** Freshness SLO, cảnh báo, phương án fallback khi quá hạn?
10. **Kiểm chứng và xóa thế nào?** Đối soát theo phiên bản/giá trị, tombstone, chính sách retention, quyền riêng tư và rebuild?

Nếu không có câu trả lời cho ít nhất những điểm liên quan tới dữ liệu đó, việc thêm message queue chỉ **chuyển kiểu lỗi** từ “hai bảng lệch nhau” sang “hai hệ thống phát sự kiện nhưng không thể tin vào kết quả”.

### 4.2. So sánh các cơ chế đồng bộ

| Cơ chế | Ưu điểm | Giới hạn quan trọng |
| --- | --- | --- |
| **Đọc nguồn khi cần** | Ít bản sao, luôn hỏi nơi có thẩm quyền | Phụ thuộc khả năng phục vụ/độ trễ nguồn; không phù hợp mọi truy vấn |
| **Cache TTL** | Đơn giản cho dữ liệu đọc nhiều, chịu cũ tạm thời | TTL không bảo đảm chính xác ngay sau cập nhật; nguy cơ đọc stale |
| **Cache invalidation** | Có thể làm mới nhanh khi biết khóa thay đổi | Mất thông báo xóa/đổi có thể giữ giá cũ |
| **API polling** | Không cần broker; dễ soát snapshot | Tốn truy vấn; phải xử lý pagination, watermark và xóa |
| **Batch ETL/ELT** | Phù hợp dữ liệu lớn và báo cáo theo kỳ | Có độ trễ theo lịch, dễ thiếu thay đổi giữa hai lần quét |
| **CDC từ database log** | Bắt thay đổi commit ở mức bảng, ít sửa mã nguồn | Payload gắn với lược đồ vật lý; chưa có ngữ nghĩa nghiệp vụ |
| **Integration events** | Công bố sự kiện và trạng thái nghiệp vụ có nghĩa | Cần quản lý schema, delivery, idempotency, ordering |
| **Transactional outbox** | Ghi trạng thái nguồn và ý định phát event trong cùng transaction cục bộ | Vẫn cần relay, có thể gửi trùng; không tạo distributed transaction |
| **Read replica** | Sao chép trạng thái DB để mở rộng đọc | Không thay đổi quyền sở hữu; replica lag có thể xuất hiện |
| **Materialized view** | Định nghĩa phép tính đọc lại được trong DB | Refresh policy, tính mới và chi phí duy trì vẫn phải rõ |

Không có cơ chế tốt nhất trong mọi tình huống. **Cache giá hiện tại** và **dòng đơn lịch sử** không nên dùng chung cơ chế “cập nhật khi Catalog đổi giá”, vì mục đích dữ liệu khác nhau.

### 4.3. Hợp đồng version: full-state và delta

Giả sử nguồn Catalog thay đổi:

~~~~text
v1: list_price = 100000
v2: list_price = 110000
v3: list_price = 120000
~~~~

Nếu event v3 chứa **trạng thái đầy đủ**:

~~~~json
{
  "productId": "P01",
  "version": 3,
  "listPrice": "120000.00",
  "currency": "VND"
}
~~~~

consumer có thể cập nhật bản đọc trực tiếp lên giá 120.000 khi nhận v3, ngay cả nếu trước đó chưa nhận v2, **miễn là** hợp đồng bảo đảm payload v3 chứa tất cả trường cần thiết cho projection và consumer đã kiểm tra ý nghĩa/schema. Bản sao có thể hội tụ về trạng thái hiện tại với một snapshot đầy đủ.

Nếu event v3 chỉ là **delta**:

~~~~json
{
  "productId": "P01",
  "version": 3,
  "priceDelta": "10000.00",
  "currency": "VND"
}
~~~~

consumer **không được cộng delta v3 vào v1** nếu thiếu v2, vì sẽ cho 110.000 thay vì 120.000. Nó phải xử lý **chuỗi phiên bản liên tục**, phát hiện khoảng trống, đợi/phát lại hoặc tải snapshot đáng tin.

**Không gọi mọi event là “idempotent” chỉ vì có version**: full-state event có thể ghi có điều kiện theo version; delta thường cần xử lý một lần đúng thứ tự hoặc một chiến lược cộng dồn/phục hồi riêng.

### 4.4. Thứ tự và thời điểm

Cần phân biệt:

- **occurred_at:** thời điểm sự kiện xảy ra theo ngữ nghĩa nguồn.
- **committed_at:** thời điểm giao dịch nguồn được commit nếu được ghi nhận tin cậy.
- **published_at:** lúc relay công bố sự kiện.
- **received_at:** lúc broker/consumer nhận được.
- **applied_at:** lúc bản sao cập nhật thành công.
- **effective_from:** thời điểm giá trị có hiệu lực theo nghiệp vụ, có thể khác thời điểm ghi.

Một thông điệp được **nhận sau** không nhất thiết là phiên bản **mới hơn**. Không nên dùng received_at làm quy tắc cuối thắng nếu hai bản tin đảo thứ tự và source_version đã có thẩm quyền xác định thứ tự.

Nếu nguồn phải công bố “giá mới có hiệu lực từ ngày mai”, projection có thể cần **lịch hiệu lực** chứ không chỉ một cột giá mới nhất. Việc lấy giá theo **version cao nhất** không tự trả lời câu hỏi giá **có hiệu lực hiện tại** khi có dữ liệu hiệu lực trong tương lai.

### 4.5. Định nghĩa độ mới và hành động khi vượt ngưỡng

Một read model phục vụ Search có thể chấp nhận trễ một số giây, trong khi quyết định **chốt giá thanh toán** phải gọi Pricing hoặc xác nhận báo giá có hiệu lực trước khi tạo đơn. Đừng lấy Search index có thể stale làm nguồn giá bắt buộc để quyết toán.

Ví dụ hợp đồng cần nêu:

~~~~text
Search projection freshness:
  Mục tiêu nội bộ: 99% thay đổi Catalog hội tụ trong 60 giây
  trong điều kiện vận hành được xác định.

Khi quá hạn:
  Cảnh báo về consumer lag.
  Hiển thị độ mới nếu sản phẩm có rủi ro.
  Tránh dùng giá Search làm giá giao dịch cuối.

Đường chốt mua:
  Kiểm tra quote/price từ nguồn có thẩm quyền.
  Lưu accepted_unit_price thành snapshot tại thời điểm chốt.
~~~~

**60 giây/99% chỉ là ví dụ SLO**, không phải tiêu chuẩn phổ quát. SLO thực tế do nghiệp vụ, tải và mức rủi ro lựa chọn. Khi đo, phải nêu rõ **mốc thời gian bắt đầu/kết thúc**, phạm vi sự kiện, đồng hồ và xử lý những event không tới đích.

## 5. Vòng đời thay đổi: ai ghi, ai phát, ai dựng bản đọc?

Sơ đồ hợp đồng một chiều:

~~~~mermaid
flowchart LR
    A["Quản trị Catalog"] -->|"Đổi tên/giá"| B["Catalog write model"]
    B -->|"Commit state + outbox"| C["Catalog DB"]
    C -->|"Outbox relay"| D["Broker / Event channel"]
    D -->|"Event versioned"| E["Search projection worker"]
    E -->|"Versioned upsert"| F["Search read model"]
    F -->|"Tìm kiếm (có thể stale)"| G["Search UI"]
    B -->|"Quote có hiệu lực"| H["Sales"]
    H -->|"Snapshot đã chốt"| I["Sales order line"]
    I -->|"Sự kiện báo cáo"| J["Analytics read model"]
~~~~

**Đường ghi duy nhất** cho giá niêm yết hiện hành là Catalog. Search không tự ý sửa giá. Sales **không** sao chép giá niêm yết như một trường phải luôn khớp; Sales giữ **accepted_unit_price** của đơn theo hợp đồng quote tại thời điểm mua.

### 5.1. Ai chịu trách nhiệm mỗi mắt xích?

| Khâu | Bên sở hữu | Tiêu chí đúng |
| --- | --- | --- |
| Catalog.updatePrice | Catalog/Pricing | Giá hợp lệ theo quy tắc và quyền sửa |
| Catalog state + outbox | Catalog DB | Cùng commit hoặc cùng rollback |
| Outbox relay | Nhóm tích hợp/vận hành | Không làm mất ý định phát; chịu gửi lại |
| Event contract | Catalog + consumer | Khóa, version, currency và ngữ nghĩa được công bố |
| Search consumer | Search | Không ghi đè trạng thái mới bằng event cũ; idempotent |
| Search data | Search | Projection có thể được rebuild, biết version/nguồn |
| Sales snapshot | Sales | Giá chốt đúng quote, giữ nguyên khi Catalog đổi giá |
| Đối soát | Data owner + vận hành | Biết sai lệch thuộc stale, conflict hay mapping sai |

Một hệ thống có nhiều database **không tự nhiên giảm rủi ro** nếu vẫn thiếu những trách nhiệm này. Ngược lại, một modular monolith sử dụng cùng PostgreSQL có thể giữ ranh giới sở hữu rõ bằng các module, API và quyền truy cập riêng.

### 5.2. Bản sao được sửa trực tiếp khi nào?

Thông thường **không cho admin sửa trực tiếp Search projection**. Nếu doanh nghiệp cần thay nội dung hiển thị khác Catalog cho một kênh cụ thể, mô hình nên tách một **thuộc tính có quyền sở hữu riêng**, ví dụ:

~~~~text
Catalog.product_title: tên chuẩn sản phẩm.
SearchMerchandising.search_display_alias: nhãn được phép chỉnh cho tìm kiếm.
SearchProjection.display_title: chính sách ghép hai nguồn và precedence.
~~~~

Lúc đó SearchMerchandising **không tranh quyền sở hữu** catalog.product_title; nó sở hữu **alias** có ngữ nghĩa khác. Quy tắc lựa chọn alias hay tên chuẩn phải được công bố và test, thay vì sửa trực tiếp một bản sao rồi gọi đó là giá trị Catalog mới.

## 6. Ví dụ PostgreSQL: một nguồn Catalog, một bản đọc Search và một snapshot Sales

Phần này trình bày **một bộ lệnh SQL minh họa trên database thử nghiệm mới**. Để dễ quan sát và đối soát, cả ba ngữ cảnh được đặt trong **cùng PostgreSQL nhưng ở các schema riêng**. Trong triển khai thật, chúng có thể ở database hoặc hệ thống khác nhau; một lệnh JOIN xuyên schema trong bài **không phải đề xuất cho các service truy vấn trực tiếp bảng của nhau khi vận hành**.

### 6.1. Mô hình và bất biến

~~~~mermaid
erDiagram
    CATALOG_PRODUCT ||--o{ CATALOG_OUTBOX : publishes
    CATALOG_PRODUCT ||--o{ SEARCH_PRODUCT_PROJECTION : "logical identity"
    SALES_ORDER ||--|{ SALES_ORDER_LINE : contains

    CATALOG_PRODUCT {
        uuid product_id PK
        string sku UK
        string title
        decimal current_list_price
        bigint version
    }
    CATALOG_OUTBOX {
        uuid event_id PK
        uuid product_id FK
        bigint aggregate_version
        jsonb payload
    }
    SEARCH_PRODUCT_PROJECTION {
        uuid product_id PK
        decimal list_price
        bigint source_version
        uuid source_event_id
    }
    SALES_ORDER {
        uuid order_id PK
        timestamp ordered_at
    }
    SALES_ORDER_LINE {
        uuid line_id PK
        uuid order_id FK
        uuid catalog_product_ref
        decimal accepted_unit_price
    }
~~~~

Trong sơ đồ, quan hệ giữa Catalog và Search là **liên kết định danh logic**, không phải FK xuyên ngữ cảnh; quan hệ giữa SalesOrder và SalesOrderLine **là FK cục bộ** trong Sales.

Các quy tắc:

1. **Catalog là nơi ghi có thẩm quyền** với sku, title, current_list_price, currency và version.
2. **Catalog.version tăng đơn điệu mỗi lần thay đổi trạng thái sản phẩm được công bố**. Event v2 là trạng thái mới hơn v1 của chính sản phẩm ấy.
3. **Outbox event được ghi trong cùng transaction Catalog** với thay đổi state.
4. **Search chỉ nhận payload full-state** đã được xác minh, cập nhật projection khi source_version mới hơn.
5. **Mỗi eventId được xử lý idempotent trong DB Search**; event cũ không ghi đè version mới.
6. **Sales giữ accepted_unit_price và product_title_at_purchase** có ý nghĩa lịch sử riêng, không đổi theo giá hiện tại.
7. Bản sao Search có thể trễ có giới hạn; khi **chốt mua**, Sales phải xác nhận một quote hợp lệ từ nguồn có thẩm quyền.

### 6.2. DDL nguồn Catalog và transactional outbox

~~~~sql
CREATE SCHEMA cp_catalog;
CREATE SCHEMA cp_search;
CREATE SCHEMA cp_sales;

CREATE TABLE cp_catalog.product (
    product_id UUID PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE CHECK (BTRIM(sku) <> ''),
    title TEXT NOT NULL CHECK (BTRIM(title) <> ''),
    current_list_price NUMERIC(14, 2) NOT NULL
        CHECK (current_list_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    version BIGINT NOT NULL CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cp_catalog.outbox_event (
    event_id UUID PRIMARY KEY,
    product_id UUID NOT NULL
        REFERENCES cp_catalog.product(product_id),
    aggregate_version BIGINT NOT NULL
        CHECK (aggregate_version > 0),
    event_type TEXT NOT NULL
        CHECK (event_type = 'catalog.product-published'),
    schema_version INTEGER NOT NULL
        CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_outbox_product_version
        UNIQUE (product_id, aggregate_version)
);

CREATE INDEX ix_cp_outbox_unpublished
    ON cp_catalog.outbox_event(occurred_at, event_id)
    WHERE published_at IS NULL;
~~~~

**Ý nghĩa hai khóa của outbox:**

- event_id định danh một bản tin để consumer có thể chống xử lý trùng.
- (product_id, aggregate_version) ngăn hai sự kiện có cùng phiên bản sản phẩm trong ví dụ có **một event full-state cho mỗi lần thay đổi**.

Giả định “một event theo version” chỉ phù hợp với luồng này. Một nguồn khác có thể phát nhiều event nghiệp vụ cho cùng một version; khi ấy phải thiết kế khóa outbox khác. **Không tùy ý đưa ràng buộc ví dụ vào mọi hệ thống**.

### 6.3. DDL Search projection và inbox

~~~~sql
CREATE TABLE cp_search.product_projection (
    product_id UUID PRIMARY KEY,
    sku TEXT NOT NULL,
    title TEXT NOT NULL,
    list_price NUMERIC(14, 2) NOT NULL
        CHECK (list_price >= 0),
    currency_code CHAR(3) NOT NULL,
    source_version BIGINT NOT NULL
        CHECK (source_version > 0),
    source_event_id UUID NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cp_search.inbox_event (
    event_id UUID PRIMARY KEY,
    product_id UUID NOT NULL,
    source_version BIGINT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~~

**Đọc tên các trường:**

- list_price trong Search là **bản đọc của Catalog.current_list_price**, không có quyền được sửa độc lập.
- source_version là **version do Catalog cấp**, không phải phiên bản tùy ý của Search.
- source_event_id giúp truy vết bản tin đã áp dụng.
- synced_at là lúc **bản đọc được cập nhật tại Search**, không mặc định là thời điểm nguồn thay đổi.
- inbox_event là sổ xử lý **eventId**, không tự chứng minh payload đúng nghĩa hay mọi phiên bản đã đến.

Trong bài chỉ dùng một consumer logic duy nhất cho inbox. Nếu nhiều handler độc lập cùng sử dụng eventId nhưng cần xử lý khác nhau, khóa inbox phải bao gồm **consumer_name/handler_id** để một handler không chặn handler khác.

### 6.4. DDL Sales giữ lịch sử giao dịch

~~~~sql
CREATE TABLE cp_sales.sales_order (
    order_id UUID PRIMARY KEY,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
);

CREATE TABLE cp_sales.order_line (
    line_id UUID PRIMARY KEY,
    order_id UUID NOT NULL
        REFERENCES cp_sales.sales_order(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    catalog_product_ref UUID NOT NULL,
    product_title_at_purchase TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    accepted_unit_price NUMERIC(14, 2) NOT NULL
        CHECK (accepted_unit_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    line_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (quantity * accepted_unit_price) STORED,
    CONSTRAINT uq_sales_order_line UNIQUE (order_id, line_no)
);
~~~~

**catalog_product_ref không là FK SQL sang cp_catalog.product.** Đó là một định danh liên ngữ cảnh; trong ví dụ cùng DB có thể tạo FK về mặt kỹ thuật, nhưng mô hình Sales không cần buộc vòng đời đơn lịch sử phụ thuộc việc một sản phẩm còn tồn tại trong Catalog. Sales phải kiểm tra **báo giá và điều kiện bán** tại thời điểm chốt bằng hợp đồng thích hợp.

### 6.5. Ghi sản phẩm đầu tiên và sự kiện v1 cùng transaction

~~~~sql
BEGIN;

INSERT INTO cp_catalog.product
    (product_id, sku, title, current_list_price,
     currency_code, version, updated_at)
VALUES
    ('00000000-0000-0000-0000-000000000101',
     'NOTE-A5', 'Sổ tay A5', 100000.00,
     'VND', 1, TIMESTAMPTZ '2026-10-01 09:00:00+07');

INSERT INTO cp_catalog.outbox_event
    (event_id, product_id, aggregate_version,
     event_type, schema_version, occurred_at, payload)
SELECT
    '00000000-0000-0000-0000-000000000401',
    p.product_id,
    p.version,
    'catalog.product-published',
    1,
    p.updated_at,
    jsonb_build_object(
        'productId', p.product_id::TEXT,
        'sku', p.sku,
        'title', p.title,
        'listPrice', p.current_list_price::TEXT,
        'currency', p.currency_code,
        'version', p.version
    )
FROM cp_catalog.product AS p
WHERE p.product_id =
    '00000000-0000-0000-0000-000000000101';

COMMIT;
~~~~

Khi transaction thành công, **dữ liệu nguồn và bản ghi outbox cùng commit**. Nếu INSERT outbox thất bại và transaction bị rollback, sản phẩm chưa được ghi nhận như một thao tác thành công chỉ ở một phía.

Relay có thể đọc các hàng unpublished và gửi đến broker, nhưng **SQL trên chưa có relay thực sự**. Dữ liệu Search chưa tự cập nhật chỉ vì outbox tồn tại.

### 6.6. Tạo snapshot đơn đã chốt

Giả sử Sales xác nhận một đơn với giá chốt hợp lệ **90.000 VND** cho P01 (ví dụ có chiết khấu theo khách):

~~~~sql
INSERT INTO cp_sales.sales_order(order_id, ordered_at, status)
VALUES
    ('00000000-0000-0000-0000-000000000201',
     TIMESTAMPTZ '2026-10-01 10:00:00+07',
     'CONFIRMED');

INSERT INTO cp_sales.order_line
    (line_id, order_id, line_no, catalog_product_ref,
     product_title_at_purchase, quantity, accepted_unit_price)
VALUES
    ('00000000-0000-0000-0000-000000000202',
     '00000000-0000-0000-0000-000000000201',
     1,
     '00000000-0000-0000-0000-000000000101',
     'Sổ tay A5', 2, 90000.00);
~~~~

Sales lưu **accepted_unit_price = 90.000** và **line_amount = 180.000**. Giá này có thể khác giá Catalog vì hợp đồng quote, khuyến mại hoặc giao dịch riêng. Việc ví dụ INSERT trực tiếp là **fixture**, không phải bằng chứng đã có quy trình xác nhận giá, quyền mua, thanh toán và kho hàng đầy đủ.

**Bất biến quan trọng:** Một lần Catalog thay đổi giá **không được cập nhật giá chốt của đơn này**. Đơn lịch sử không phải một bản sao cần hội tụ với Catalog.current_list_price.

## 7. Consumer cập nhật Search: chặn event trùng và event cũ

### 7.1. Mục tiêu chính xác của consumer

Một consumer hợp lệ phải phân biệt:

- **Event mới của product chưa có trong projection:** tạo bản đọc mới.
- **Event có version lớn hơn version đang lưu:** cập nhật bản đọc.
- **Event cùng eventId đã xử lý:** không lặp tác dụng.
- **Event version cũ hơn:** không được ghi đè bản đọc mới hơn.
- **Event cùng version nhưng payload khác:** là **xung đột hợp đồng/nguồn**, cần cảnh báo và xử lý, không tự tùy tiện chọn một bên.
- **Event thiếu thông tin cần thiết, sai tenant/đơn vị hoặc sai schema:** từ chối hoặc cách ly có kiểm soát.

Trong ví dụ, event là **full-state** nên có thể bỏ qua những version trung gian nếu một bản mới hơn đã được áp dụng. Nếu event chỉ mang delta, phải **phát hiện gap** và xử lý theo thứ tự hoặc dựng lại snapshot.

### 7.2. Áp dụng event v1 và lưu dấu inbox trong một transaction

Giả sử relay đã công bố bản tin v1 tương ứng với hàng outbox. Đoạn SQL sau mô phỏng **logic của một consumer Search**:

~~~~sql
BEGIN;

WITH accepted AS (
    INSERT INTO cp_search.inbox_event
        (event_id, product_id, source_version)
    VALUES
        ('00000000-0000-0000-0000-000000000401',
         '00000000-0000-0000-0000-000000000101', 1)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
),
applied AS (
    INSERT INTO cp_search.product_projection
        (product_id, sku, title, list_price, currency_code,
         source_version, source_event_id, synced_at)
    SELECT
        '00000000-0000-0000-0000-000000000101',
        'NOTE-A5',
        'Sổ tay A5',
        100000.00,
        'VND',
        1,
        accepted.event_id,
        CURRENT_TIMESTAMP
    FROM accepted
    WHERE TRUE -- Phan dinh ON CONFLICT voi ON cua SELECT/JOIN.
    ON CONFLICT (product_id)
    DO UPDATE SET
        sku = EXCLUDED.sku,
        title = EXCLUDED.title,
        list_price = EXCLUDED.list_price,
        currency_code = EXCLUDED.currency_code,
        source_version = EXCLUDED.source_version,
        source_event_id = EXCLUDED.source_event_id,
        synced_at = EXCLUDED.synced_at
    WHERE cp_search.product_projection.source_version
        < EXCLUDED.source_version
    RETURNING product_id
)
SELECT
    (SELECT COUNT(*) FROM accepted) AS accepted_events,
    (SELECT COUNT(*) FROM applied) AS updated_products;

COMMIT;
-- Lần đầu: accepted_events=1, updated_products=1.
~~~~

**Tại sao hai thao tác phải cùng transaction?** Nếu lưu inbox rồi COMMIT, sau đó mới cập nhật projection và bị lỗi, lần giao lại có thể bị bỏ qua vì eventId đã được đánh dấu xử lý. Ở đây, **inbox và projection cùng commit hoặc cùng rollback** trong Search DB.

**Tại sao có WHERE trên source_version?** Một event cũ vẫn có thể đến sau event mới. Điều kiện đảm bảo event version 1 không ghi đè product đang ở version 2. Giao dịch UPSERT trên cùng product_id được PostgreSQL điều phối qua khóa/xử lý xung đột; điều kiện version giúp bảo vệ **quy tắc chỉ tiến lên phiên bản mới hơn**.

### 7.3. Catalog thay đổi giá: cập nhật nguồn và phát v2

Giả sử tên và giá niêm yết được thay đổi:

~~~~sql
BEGIN;

WITH changed AS (
    UPDATE cp_catalog.product
    SET title = 'Sổ tay bìa cứng A5',
        current_list_price = 120000.00,
        version = version + 1,
        updated_at = TIMESTAMPTZ '2026-11-01 09:00:00+07'
    WHERE product_id =
        '00000000-0000-0000-0000-000000000101'
      AND version = 1
    RETURNING product_id, sku, title, current_list_price,
              currency_code, version, updated_at
),
logged AS (
    INSERT INTO cp_catalog.outbox_event
        (event_id, product_id, aggregate_version, event_type,
         schema_version, occurred_at, payload)
    SELECT
        '00000000-0000-0000-0000-000000000402',
        c.product_id, c.version,
        'catalog.product-published',
        1, c.updated_at,
        jsonb_build_object(
            'productId', c.product_id::TEXT,
            'sku', c.sku,
            'title', c.title,
            'listPrice', c.current_list_price::TEXT,
            'currency', c.currency_code,
            'version', c.version
        )
    FROM changed AS c
    RETURNING event_id
)
SELECT COUNT(*) AS emitted_events
FROM logged;

COMMIT;
-- emitted_events = 1 nếu product ở version 1.
~~~~

Điều kiện **AND version = 1** là một dạng optimistic concurrency check. Nếu có transaction khác đã đưa sản phẩm lên version 2, UPDATE không thay đổi hàng nào, CTE changed rỗng và outbox **không phát sự kiện sai**. Ứng dụng cần kiểm tra emitted_events, xử lý conflict và không báo thay đổi thành công khi kết quả bằng 0.

**Không dùng phiên bản thời gian nhận làm quy tắc cuối thắng**: source_version là thứ tự nghiệp vụ do Catalog quản lý, tăng ở cùng transaction với thay đổi thuộc tính.

### 7.4. Search nhận v2

Consumer thực tế phải đọc JSON từ event, kiểm tra schema và chuyển dữ liệu sang kiểu phù hợp. Để tập trung vào ràng buộc phiên bản, ví dụ mô phỏng những giá trị v2 **đã được xác thực**:

~~~~sql
BEGIN;

WITH accepted AS (
    INSERT INTO cp_search.inbox_event
        (event_id, product_id, source_version)
    VALUES
        ('00000000-0000-0000-0000-000000000402',
         '00000000-0000-0000-0000-000000000101', 2)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
),
applied AS (
    INSERT INTO cp_search.product_projection
        (product_id, sku, title, list_price, currency_code,
         source_version, source_event_id, synced_at)
    SELECT
        '00000000-0000-0000-0000-000000000101',
        'NOTE-A5',
        'Sổ tay bìa cứng A5',
        120000.00,
        'VND',
        2,
        accepted.event_id,
        CURRENT_TIMESTAMP
    FROM accepted
    WHERE TRUE -- Phan dinh ON CONFLICT voi ON cua SELECT/JOIN.
    ON CONFLICT (product_id)
    DO UPDATE SET
        sku = EXCLUDED.sku,
        title = EXCLUDED.title,
        list_price = EXCLUDED.list_price,
        currency_code = EXCLUDED.currency_code,
        source_version = EXCLUDED.source_version,
        source_event_id = EXCLUDED.source_event_id,
        synced_at = EXCLUDED.synced_at
    WHERE cp_search.product_projection.source_version
        < EXCLUDED.source_version
    RETURNING product_id
)
SELECT
    (SELECT COUNT(*) FROM accepted) AS accepted_events,
    (SELECT COUNT(*) FROM applied) AS updated_products;

COMMIT;
-- Lần đầu nhận v2: 1, 1.
~~~~

Trạng thái kỳ vọng:

| Nguồn / bản đọc | Sản phẩm | Version | Giá VND |
| --- | --- | ---: | ---: |
| Catalog | P01 | 2 | 120.000 |
| Search projection | P01 | 2 | 120.000 |
| Sales order line đã chốt | P01 | Không cùng loại version | 90.000 |

Giá Sales vẫn **90.000** và dòng bán 2 chiếc vẫn **180.000**. Đây là kết quả **đúng theo ba ngữ nghĩa**, không phải dữ liệu lệch cần “sửa hết cho bằng nhau”.

### 7.5. Một event được giao lại

Chạy lại **đúng khối áp dụng event v2** với cùng eventId 000...402. Inbox đã có eventId ấy:

~~~~text
accepted_events = 0
updated_products = 0
~~~~

Không có cập nhật projection mới và synced_at không bị đẩy lên chỉ vì replay. Điều này tránh việc **bản tin cũ làm giả độ mới của dữ liệu**.

### 7.6. Một event cũ đến với eventId khác

Giả sử một nguồn sai cấu hình phát lại **nội dung v1** với một eventId chưa từng thấy. Inbox chỉ kiểm tra eventId nên vẫn nhận, nhưng điều kiện **version cao hơn** chặn ghi đè dữ liệu:

~~~~sql
BEGIN;

WITH accepted AS (
    INSERT INTO cp_search.inbox_event
        (event_id, product_id, source_version)
    VALUES
        ('00000000-0000-0000-0000-000000000499',
         '00000000-0000-0000-0000-000000000101', 1)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
),
applied AS (
    INSERT INTO cp_search.product_projection
        (product_id, sku, title, list_price, currency_code,
         source_version, source_event_id, synced_at)
    SELECT
        '00000000-0000-0000-0000-000000000101',
        'NOTE-A5',
        'Sổ tay A5',
        100000.00,
        'VND',
        1,
        accepted.event_id,
        CURRENT_TIMESTAMP
    FROM accepted
    WHERE TRUE -- Phan dinh ON CONFLICT voi ON cua SELECT/JOIN.
    ON CONFLICT (product_id)
    DO UPDATE SET
        sku = EXCLUDED.sku,
        title = EXCLUDED.title,
        list_price = EXCLUDED.list_price,
        currency_code = EXCLUDED.currency_code,
        source_version = EXCLUDED.source_version,
        source_event_id = EXCLUDED.source_event_id,
        synced_at = EXCLUDED.synced_at
    WHERE cp_search.product_projection.source_version
        < EXCLUDED.source_version
    RETURNING product_id
)
SELECT
    (SELECT COUNT(*) FROM accepted) AS accepted_events,
    (SELECT COUNT(*) FROM applied) AS updated_products;

COMMIT;
-- accepted_events = 1, updated_products = 0:
-- event mới về ID nhưng đã cũ về trạng thái nguồn.
~~~~

**Ý nghĩa:** Inbox chống **cùng event ID**, còn kiểm tra source_version chống **cập nhật lùi trạng thái**. Hai cơ chế bảo vệ khác nhau. Tuy nhiên, tình huống cùng version nhưng nội dung khác vẫn cần **quy tắc phát hiện conflict**; chỉ bỏ qua mọi event có version không lớn hơn chưa đủ chứng minh dữ liệu đúng.

### 7.7. Giới hạn của bản SQL minh họa

Đây là **mẫu logic consumer**, không phải production-ready message handler:

- Chưa xác thực quyền nguồn, chữ ký/nguồn phát hoặc quyền theo tenant.
- Chưa parse/validate JSON schema, mapping currency và phạm vi ID.
- Chưa phát hiện **eventId bị tái sử dụng với payload khác**; một inbox production có thể lưu payload hash/metadata và cách xử lý collision.
- Chưa cách ly event **cùng product/version nhưng nội dung mâu thuẫn**. Cần kiểm tra và báo lỗi/quarantine thay vì lặng lẽ chấp nhận.
- Chưa có broker ack/retry/dead-letter, outbox relay thực hay điều phối lỗi khi reconnect.
- Chưa xử lý unpublish/delete/tombstone và phiên bản hiệu lực trong tương lai.
- Chưa có hệ thống phân quyền riêng giữa Catalog/Search; dùng chung PostgreSQL chỉ để học.

**Nguyên tắc cốt lõi vẫn đúng:** Không phụ thuộc trật tự **đến nơi** khi nguồn đã cung cấp version, không nhân tác dụng khi message lặp và ghi inbox–projection trong cùng transaction cục bộ.

## 8. Đối soát: khi nào hai bản sao lệch là lỗi?

### 8.1. Không so sánh bừa các giá trị khác nghĩa

Để đối soát Search với Catalog, ta so **cùng product_id, cùng định nghĩa giá hiện hành và cùng version**. Để kiểm tra Sales, ta so **giá đã chốt với báo giá có thẩm quyền tại thời điểm đặt**, không so với giá niêm yết hôm nay.

Một phép đối soát sai:

~~~~sql
-- MINH HỌA PHÉP SO SÁNH SAI NGỮ NGHĨA:
SELECT l.line_id, l.accepted_unit_price, c.current_list_price
FROM cp_sales.order_line AS l
JOIN cp_catalog.product AS c
    ON c.product_id = l.catalog_product_ref
WHERE l.accepted_unit_price <> c.current_list_price;
~~~~

Truy vấn có thể trả dòng đơn có giá chốt 90.000 khác giá niêm yết 120.000. Điều đó **không tự chứng minh sai**, vì giá niêm yết và giá giao dịch là hai loại dữ liệu. Truy vấn chỉ hữu ích nếu được dùng để **khám phá chênh lệch** kèm đúng bối cảnh nghiệp vụ, không phải làm job “sửa dữ liệu lệch”.

### 8.2. Đối soát trạng thái Search với Catalog

Trên database thử nghiệm, truy vấn:

~~~~sql
SELECT
    c.product_id,
    c.sku,
    c.version AS catalog_version,
    s.source_version AS search_version,
    s.synced_at,
    CASE
        WHEN s.product_id IS NULL THEN 'MISSING_PROJECTION'
        WHEN s.source_version < c.version THEN 'LAGGING'
        WHEN s.source_version > c.version THEN 'AHEAD_OF_SOURCE'
        WHEN s.sku IS DISTINCT FROM c.sku
          OR s.title IS DISTINCT FROM c.title
          OR s.list_price IS DISTINCT FROM c.current_list_price
          OR s.currency_code IS DISTINCT FROM c.currency_code
          THEN 'DIVERGENT_SAME_VERSION'
        ELSE 'IN_SYNC'
    END AS sync_state
FROM cp_catalog.product AS c
LEFT JOIN cp_search.product_projection AS s
    ON s.product_id = c.product_id
ORDER BY c.sku;
~~~~

Các trạng thái có nghĩa khác nhau:

| Trạng thái | Diễn giải | Hướng xử lý |
| --- | --- | --- |
| **MISSING_PROJECTION** | Catalog có sản phẩm, Search chưa có | Kiểm tra filter xuất bản, tiến độ seed/replay, nguồn event |
| **LAGGING** | Search đang ở version thấp hơn | Nếu trong SLO: chờ; nếu quá hạn: báo động và replay/repair |
| **AHEAD_OF_SOURCE** | Search mang version lớn hơn nguồn đang được so | Kiểm tra nhầm môi trường, restore nguồn, mapping sai hoặc sự cố |
| **DIVERGENT_SAME_VERSION** | Cùng version nhưng thuộc tính khác | Vi phạm hợp đồng full-state/transform; không tự chọn bên nào để ghi đè |
| **IN_SYNC** | Các trường so sánh khớp theo version hiện tại | Đạt phép kiểm tra này, chưa chứng minh mọi invariant khác |

Sau khi đã áp v2, kết quả kỳ vọng cho P01 là **IN_SYNC**. Nếu Search chưa nhận v2, nó có thể là **LAGGING** chứ không nhất thiết dữ liệu nguồn sai.

**Giới hạn quan trọng:** Truy vấn này chỉ phù hợp với **thuộc tính thực sự có phép mapping 1:1**, cùng tenant và scope. Nếu Search cố ý có tiêu đề alias do bộ phận merchandising quản lý, không được so alias với Catalog.title rồi gọi đó là divergence. Hãy so trường **catalog_title_projection** với Catalog.title, còn alias có nguồn và chính sách riêng.

### 8.3. Kiểm tra bản ghi chỉ có ở Search

Một bản ghi đã bị ngừng xuất bản hoặc xóa khỏi Catalog có thể vẫn ở Search. Nếu hợp đồng quy định Search phải gỡ khỏi kết quả tìm kiếm, cần phát hiện.

~~~~sql
SELECT s.product_id, s.sku, s.source_version
FROM cp_search.product_projection AS s
LEFT JOIN cp_catalog.product AS c
    ON c.product_id = s.product_id
WHERE c.product_id IS NULL;
~~~~

**Nhưng đừng tự DELETE tất cả kết quả ngay**: có nguồn dữ liệu khác có quyền xuất bản, thay đổi partition, read replica chậm, hoặc chính sách lưu lịch sử. Quyết định xóa cần dựa trên hợp đồng **delete/tombstone** và trạng thái nguồn có thẩm quyền.

### 8.4. Version bằng nhau vẫn cần so giá trị

Giả sử Search chứa:

~~~~text
product_id=P01, source_version=2, list_price=110000
~~~~

trong khi Catalog v2 là 120000. Hai bên có version giống nhau, nên quy tắc “không có lag vì version bằng nhau” **bỏ sót lỗi**.

Nguyên nhân có thể:

- Payload mapping sai đơn vị hoặc sai cột.
- Consumer nhận một event khác có cùng version.
- Một admin sửa projection thủ công.
- Bản ghi event bị làm sai hoặc bị tái sử dụng ID.
- DB Search restore từ một snapshot không tương thích.

**Quy tắc version giúp xác định thứ tự, không chứng minh payload chính xác.** Đối soát định kỳ cần kiểm tra dữ liệu nguồn cùng version và dữ liệu chiếu theo những phép biến đổi đã công bố.

### 8.5. Đồng hồ và độ mới: không chỉ trừ hai timestamp

Nếu Search.synced_at mới hơn Catalog.updated_at 5 giây, chưa chắc Search đúng: một consumer có thể vừa replay event cũ. Ngược lại, nếu synced_at nhỏ hơn updated_at, projection có thể đang trễ nhưng vẫn trong mức được phép.

Một phép đo độ mới đáng tin cần:

1. Xác định **nguồn event và version nào đã được áp dụng**.
2. Theo dõi **bản tin chưa xử lý lâu nhất**, consumer offset/watermark hoặc backlog đáng tin.
3. Biết **độ lệch đồng hồ** và ý nghĩa occurred_at/committed_at.
4. Tách độ trễ do **phát event, broker, xử lý và truy vấn bản đọc**.
5. Đếm những thay đổi **chưa đến đích**; không chỉ đo các event xử lý thành công.

Ví dụ một chỉ số đơn giản:

~~~~text
product_version_gap = catalog.version - search.source_version
~~~~

có thể hữu ích khi version tăng đều theo sản phẩm, nhưng gap = 1 **không nói rõ đã trễ 1 giây hay 1 ngày**. Mặt khác, gap = 0 mà payload sai vẫn là lỗi. Nên dùng cả **version reconciliation và freshness monitoring**.

### 8.6. Khi nguồn và bản sao ở database riêng

Ở production, không nhất thiết được phép JOIN trực tiếp Catalog và Search DB. Có thể:

- Xuất **snapshot có timestamp/version/watermark** từ Catalog.
- Đối soát theo lô bằng một job có quyền truy cập phù hợp.
- Dùng API kiểm tra một mẫu hoặc tất cả bản ghi theo phân trang.
- Tính **hash có chuẩn hóa** trên tập trường có ý nghĩa chung, sau đó tìm các bản ghi lệch.
- So đối tượng theo **(tenant_id, business_id, source_version)**.

Không so hash của hai JSON có thứ tự trường/cách biểu diễn thập phân khác nhau rồi coi đó là dữ liệu mâu thuẫn. Cần **canonical representation** hoặc đối soát từng trường sau normalization có hợp đồng.

## 9. Xung đột cập nhật: đừng mặc định “người ghi sau thắng”

### 9.1. Lỗi có hai writer cùng thẩm quyền

Giả sử:

~~~~text
10:00 Catalog sửa P01.list_price = 110000.
10:01 Search admin sửa P01.list_price = 120000.
10:02 Job đồng bộ Catalog → Search chạy, ghi 110000.
10:03 Search admin hỏi vì sao giá vừa sửa biến mất.
~~~~

Đây không chỉ là lỗi trình tự cập nhật; hai bên đang sửa **cùng một thuộc tính nhưng không có quy tắc ai sở hữu**.

Phương án rõ ràng nhất nếu Search chỉ là read model: **không cho Search admin sửa list_price**. Mọi thay đổi giá niêm yết đi qua Catalog/Pricing; Search chỉ cập nhật theo event. Nếu Search cần giá ưu đãi riêng cho kênh, hãy tạo **search_promotional_price** hoặc rule riêng có chủ sở hữu và định nghĩa precedence rõ ràng.

### 9.2. Last-write-wins có thể làm mất ý định nghiệp vụ

Một số hệ thống sử dụng **last-write-wins (LWW)** theo timestamp để xử lý hai bản ghi mâu thuẫn. Cần hiểu LWW là **chính sách lựa chọn một giá trị**, không phải bảo đảm chọn sự thật đúng.

Vấn đề:

- Đồng hồ hai node có thể lệch.
- Event được gửi/nhận lại theo thứ tự khác thời điểm cập nhật.
- Hai trường có thể được sửa bởi hai bên với quyền khác nhau.
- Một bản cập nhật offline cũ được đồng bộ muộn có thể ghi đè một thay đổi quan trọng.
- Quyết định giá/chứng từ có thể không cho phép mất lịch sử sửa.

Nếu dùng LWW, phải nêu **mốc thời gian tin cậy, phạm vi conflict và chấp nhận mất cập nhật hay không**, đồng thời có test. Với dữ liệu giá, tiền, tồn kho hoặc quyền truy cập, không tự chấp nhận LWW chỉ vì dễ viết.

### 9.3. Version có thẩm quyền và optimistic concurrency

Nếu Catalog là nguồn ghi duy nhất, có thể dùng optimistic locking:

~~~~sql
UPDATE cp_catalog.product
SET current_list_price = 130000.00,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id =
    '00000000-0000-0000-0000-000000000101'
  AND version = 2
RETURNING product_id, version;
~~~~

Đây chỉ là **mẫu UPDATE phát hiện xung đột**, không phải đường ghi Catalog hoàn chỉnh: với kiến trúc outbox, không được commit thay đổi này mà **quên ghi sự kiện tương ứng trong cùng transaction**. Muốn chạy như một cập nhật sản phẩm thật, phải gói UPDATE và INSERT outbox có điều kiện trong một transaction như mục 7.3.

Khi có hai yêu cầu cùng dựa trên version=2, không nên mặc định cả hai đã được ghi: một yêu cầu có thể cập nhật lên version=3, yêu cầu còn lại phải nhận conflict và quyết định retry hoặc thông báo cho người dùng.

**Version phải tăng theo đối tượng có thẩm quyền**, không phải một số tự tăng riêng ở Search. Hai hệ thống độc lập cấp version=3 cho những giá trị khác nhau thì phép so source_version chỉ che xung đột, không giải quyết nó.

### 9.4. Có trường hợp cần nhiều writer không?

Có, chẳng hạn một hệ thống cộng tác offline, danh sách yêu thích có thể sửa trên nhiều thiết bị, hoặc một miền dữ liệu có **quy tắc hợp nhất chính thức**. Nhưng đây là **thiết kế nhiều nguồn ghi có chủ ý**, không phải tình trạng “ai cũng sửa được”.

Phải xác định:

- **Field ownership** hoặc phạm vi ghi của từng nguồn.
- Cách gộp (merge) dữ liệu có tính giao hoán hay không.
- Cách phát hiện/giải quyết xung đột cùng một trường.
- Version vector/causal metadata hoặc một cơ chế tương đương nếu có yêu cầu.
- Khi nào cần **người quản trị dữ liệu (steward)** xử lý mâu thuẫn.
- Điều kiện hội tụ và invariant sau merge.

**CRDT** có thể hữu ích cho một số kiểu dữ liệu và phép cập nhật, nhưng **không tự bảo đảm các invariant như tồn kho không âm, hóa đơn chỉ được quyết toán một lần hoặc giá chốt chính xác**. Không đưa công nghệ hợp nhất vào dữ liệu tài chính chỉ vì nó đồng bộ được một loại counter.

### 9.5. Trùng dữ liệu khác trùng danh tính

Hai nguồn CRM và ERP đều có người tên “Nguyễn Văn A” và email tương tự. Đưa cả hai vào một golden record không phải chỉ SELECT DISTINCT hoặc GROUP BY email.

Cần:

- Định nghĩa **business identity**: người, tổ chức, tài khoản hay địa chỉ nhận?
- Quy tắc matching deterministic/probabilistic và kiểm soát false merge.
- Ghi **source IDs**, provenance và kết quả xác minh.
- Quy tắc survivorship: nguồn nào có thẩm quyền với **từng trường**.
- Quy trình unmerge nếu đã gộp nhầm.
- Quyền truy cập thông tin cá nhân khi hợp nhất hồ sơ.

**Golden record là mô hình có quy tắc quản trị**, không phải một bảng chứa “giá trị mới nhất của tất cả nguồn”.

## 10. Xóa, ngừng xuất bản và quyền riêng tư: đồng bộ không chỉ là UPDATE

### 10.1. Xóa không giống hết hạn hiển thị

Một sản phẩm có thể:

- **Ngừng xuất bản:** không xuất hiện trên trang tìm kiếm nhưng vẫn có trong Catalog.
- **Ngừng kinh doanh:** không bán mới, nhưng đơn và chứng từ lịch sử phải giữ tham chiếu.
- **Bị hợp nhất mã:** định danh P01 được chuyển sang P99 theo quy tắc rõ, không đơn giản xóa P01.
- **Bị xóa thật theo chính sách:** có thể cần loại bỏ bản sao mà không còn cách dựng từ nguồn.

Nếu Search chỉ nhận **ProductPublished** mà không có thông báo **ProductUnpublished**, một sản phẩm ngừng bán có thể vẫn hiện trong Search mãi mãi. Nếu một batch chỉ nạp các hàng hiện có mà không so những hàng đã biến mất, dữ liệu cũ cũng có thể tồn tại vô hạn.

### 10.2. Tombstone theo version

Một hợp đồng có thể dùng event:

~~~~json
{
  "eventId": "e-p01-v4",
  "eventType": "catalog.product-unpublished",
  "schemaVersion": 1,
  "productId": "P01",
  "aggregateVersion": 4,
  "isPublished": false
}
~~~~

Consumer cần ghi nhận **phiên bản gỡ hiển thị**:

~~~~text
P01 v3: published = true
P01 v4: published = false
P01 v2 đến trễ: không được đưa P01 trở lại kết quả tìm kiếm.
~~~~

Nếu consumer chỉ DELETE hàng Search rồi **quên version cuối đã áp dụng**, một event v2 đến muộn có thể **INSERT lại** sản phẩm. Vì vậy có thể cần giữ **tombstone/version metadata** theo retention và chính sách tái đồng bộ, kể cả khi bản ghi không còn hiển thị.

Một số hệ thống dùng CDC delete marker hoặc snapshot reconciliation. Dù chọn cách nào, hợp đồng phải xác định **thời điểm xóa, thứ tự, bản ghi lịch sử và quyền tái dựng**.

### 10.3. Xóa dữ liệu cá nhân qua nhiều bản sao

Một dữ liệu cá nhân có thể xuất hiện trong:

~~~~text
Identity profile
Sales contact snapshot
Search/cache
Warehouse/report
Export hoặc hệ thống đối tác
Backup
~~~~

Khi có yêu cầu xóa/chỉnh sửa, không thể chỉ UPDATE bảng nguồn rồi tự coi mọi bản sao đã tuân thủ. Cần:

1. **Danh mục nơi dữ liệu được nhân bản**, mục đích, quyền và thời hạn lưu.
2. **Nguồn có thẩm quyền** quyết định thay đổi theo chính sách áp dụng.
3. Contract thông báo/xử lý việc xóa hoặc ẩn danh các bản sao thuộc phạm vi yêu cầu.
4. Quy tắc cho **snapshot giao dịch, nghĩa vụ lưu giữ chứng từ và backup** theo pháp luật/chính sách cụ thể; không xóa hoặc giữ tùy tiện.
5. Đối soát kết quả và xử lý hệ thống ngoài chưa phản hồi.
6. Tránh replay một event cũ khiến dữ liệu cá nhân vừa được xóa **xuất hiện trở lại**.

**Không đồng nghĩa “mọi dữ liệu lịch sử đều phải xóa ngay”**: quyền xóa, nghĩa vụ lưu hồ sơ và quyền sử dụng phụ thuộc ngữ cảnh/pháp luật. Bài học thiết kế là phải có **lineage, phạm vi và xử lý đồng bộ**, thay vì chỉ nói “dữ liệu đã bị xóa ở nguồn”.

## 11. Những kịch bản lỗi mà một sơ đồ đồng bộ đẹp chưa giải quyết

### 11.1. Dual-write giữa database và broker

Cách dễ sai:

~~~~text
1. Catalog DB COMMIT giá mới.
2. Ứng dụng publish ProductUpdated.

Nếu tiến trình chết giữa 1 và 2:
  Catalog ở giá mới, Search không nhận event.
~~~~

Nếu publish trước COMMIT, consumer có thể nhận thông điệp về một thay đổi sau đó bị rollback. **Không có nguyên tử giữa DB và broker chỉ bằng cách viết hai lời gọi liên tiếp**.

**Cách xử lý phổ biến:** ghi trạng thái Catalog và bản ghi outbox trong cùng transaction, rồi relay gửi có retry. Tuy nhiên, relay gửi xong có thể chết trước khi đánh dấu sent, nên event có thể **gửi lại**. Consumer phải idempotent.

### 11.2. Gửi lại bản tin bị cộng tiền hoặc tồn hai lần

Một event:

~~~~json
{
  "eventId": "payment-001",
  "type": "PaymentSettled",
  "amount": "100000.00",
  "currency": "VND"
}
~~~~

Nếu projection xử lý:

~~~~text
daily_total += amount
~~~~

mỗi lần nhận mà không chống lặp, một event gửi hai lần làm daily_total thành 200.000. Đây là lỗi **non-idempotent accumulator**.

Một số cách thiết kế:

- Lưu **payment_id/eventId duy nhất** trong fact rồi tổng hợp từ tập fact.
- Consumer đặt inbox và cập nhật projection trong cùng transaction.
- Dùng upsert theo định danh nguồn thay vì cộng dồn mù.
- Nếu dùng delta, xác định chính xác cách chống lặp và phát hiện gap.

**SUM(DISTINCT amount)** không phải cách sửa: hai khoản thanh toán hợp lệ có thể cùng số tiền 100.000 và phải được cộng đủ.

### 11.3. Xử lý sai thứ tự

~~~~text
Catalog v3: price = 120000
Search đã áp v3.
Event v2: price = 110000 đến muộn.
~~~~

Nếu consumer UPDATE không có điều kiện version, giá Search bị lùi xuống 110.000. Một thiết kế cần:

- Nguồn cấp **version có thẩm quyền tăng theo aggregate**.
- Consumer chỉ áp **version mới hơn**, hoặc xử lý version liên tục nếu là delta.
- Quy tắc phát hiện **version bằng nhưng payload không khớp**.
- Tài liệu về phạm vi ordering mà broker thực sự bảo đảm, không đoán.

### 11.4. Đồng bộ hai chiều lặp vô hạn

~~~~text
Catalog đổi title.
Search nhận event, cập nhật title và phát SearchTitleUpdated.
Catalog lại nhận, cập nhật title và phát CatalogTitleUpdated.
...
~~~~

Nếu Search chỉ là projection, **không được tự phát ngược một sự kiện nghiệp vụ cho cùng thuộc tính chỉ vì bản sao vừa được đồng bộ**. Nếu cần hai chiều có chủ ý, phải gắn **origin, causality, ownership và suppression rules** để không có loop và không che conflict.

### 11.5. Hai nguồn cùng làm chủ dữ liệu tiền

Billing ghi invoice_paid=true; Sales cũng có thể ghi paid=true trực tiếp mà không có PaymentSettled hợp lệ. Hai giá trị khác nhau nhưng không rõ bên nào đúng.

Thiết kế tốt hơn:

- Billing/Payments sở hữu **tình trạng tiền có thẩm quyền**.
- Sales có thể lưu **payment_summary_projection** có source_version/eventId.
- Sales không được sửa projection để “ép đã trả”; cần gửi command hợp lệ tới Payments.
- Các khoản refund/partial settlement có thể cần **một mô hình trạng thái phong phú hơn boolean paid**.

Một cột boolean sao chép từ một quy trình nhiều trạng thái có thể **làm mất thông tin**; đây là lỗi mapping ngữ nghĩa, không chỉ lỗi đồng bộ.

### 11.6. Quét bảng bằng updated_at mà bỏ mất thay đổi

Một job polling:

~~~~sql
SELECT *
FROM cp_catalog.product
WHERE updated_at > :last_watermark
ORDER BY updated_at;
~~~~

có thể gặp các vấn đề:

- Hai bản ghi có **cùng timestamp** ở biên, nhưng watermark đã tiến qua chúng.
- Một transaction cập nhật muộn commit sau, dù updated_at được gán sớm hơn watermark đã lưu.
- Pagination theo offset bị lệch khi hàng liên tục được cập nhật.
- Job gặp lỗi sau khi ghi đích nhưng trước khi checkpoint, rồi chạy lại.
- Một hàng **bị xóa** không còn xuất hiện để job nhận biết.
- Đồng hồ và múi giờ khác nhau giữa các hệ thống.

Một cơ chế đáng tin có thể dùng **change log/CDC với offset**, hoặc **cursor có thứ tự ổn định và phạm vi snapshot**, cùng cơ chế xử lý delete và resume. Nếu polling theo updated_at, phải có **tie-breaker, overlap window và dedup**, nhưng vẫn cần kiểm chứng khả năng mất thay đổi quanh thời điểm commit theo kiến trúc nguồn.

### 11.7. Snapshot ban đầu và dòng thay đổi bị hở khoảng

Khi tạo Search index mới, nhóm làm:

~~~~text
10:00 Bắt đầu quét toàn bộ Catalog.
10:05 Catalog đổi giá P01 và phát event.
10:10 Quét snapshot kết thúc.
10:11 Consumer mới bắt đầu đọc các event phát sau 10:10.
~~~~

Thay đổi lúc 10:05 **không chắc đã nằm trong snapshot được quét** và cũng có thể bị consumer bỏ qua nếu chỉ đọc từ sau 10:10. Đây là **khoảng trống giữa snapshot và stream**.

Một bootstrap đúng cần:

- Xác định snapshot và **log position/watermark nhất quán** theo cơ chế nguồn.
- Bắt đầu bắt thay đổi ở vị trí bảo đảm **không mất event trong lúc snapshot**.
- Cho phép event trùng nhưng dedup/idempotent.
- Đối soát số hàng, version và checksum/mapping sau dựng index.
- Có phương án rebuild toàn bộ khi tính đúng không thể chứng minh.

Không chỉ nói “dựng index xong thì bật consumer” mà không giải thích các sự kiện xảy ra **trong thời gian dựng**.

### 11.8. Replay sau khi đã gỡ dữ liệu

Search đã xử lý ProductUnpublished v4, nhưng một replay chỉ chứa các bản tin Published v1–v3. Nếu rebuild bằng cách áp dụng tất cả event có sẵn mà **thiếu tombstone v4**, index có thể hiển thị lại sản phẩm đã gỡ.

Kế hoạch replay cần:

- Retention đủ cho toàn bộ chuỗi cần tái dựng hoặc một snapshot hiện hành có thẩm quyền.
- Quy tắc xử lý sự kiện gỡ/xóa.
- Metadata version và checkpoint.
- Kiểm tra kết quả sau replay với nguồn chuẩn.

**Replay không tự chữa mọi lỗi** nếu log thiếu dữ liệu hoặc hợp đồng phiên bản cũ không còn giải mã được.

## 12. Quy trình sửa một hệ thống đang có dữ liệu lệch

Không nên bắt đầu bằng lệnh UPDATE tất cả các bản sao cho bằng bảng bất kỳ. Trước tiên phải **xác định ngữ nghĩa và thẩm quyền**; nếu không, một đợt sửa lệch có thể nhân rộng chính dữ liệu sai.

### Bước 1 — Kiểm kê các bản sao và đường ghi

Liệt kê theo thuộc tính:

~~~~text
Attribute: product.list_price (giá niêm yết hiện hành).

Existing copies:
  Catalog.product.current_list_price
  Search.product_projection.list_price
  Redis.product-price:P01
  BI.DIM_PRODUCT.list_price
  Sales.order_line.accepted_unit_price (khác nghĩa!)

Writers:
  Catalog Admin API
  Search Admin Direct Edit (đường ghi bất hợp lệ cần xử lý)
  Nightly ETL Job
  Cache refresh Worker

Readers:
  Search UI
  Checkout API
  BI Dashboard
  Support Tool
~~~~

**Mục đích của bước này là phân loại**: Sales.accepted_unit_price khác nghĩa nên không thuộc phạm vi “sửa bằng Catalog.current_list_price”, dù nhìn cùng là giá của P01.

### Bước 2 — Xác định nguồn chuẩn và quyền ghi

Ký một **data ownership contract**:

- Catalog/Pricing sở hữu danh mục và giá niêm yết theo phạm vi xác định.
- Search chỉ là read projection.
- Redis là cache có TTL/invalidation.
- BI giữ giá trị cần báo cáo theo định nghĩa và thời gian đã công bố.
- Sales giữ giá chốt riêng.

**Chặn các đường ghi cạnh tranh** hoặc đổi chúng thành lệnh đến nguồn chuẩn. Nếu để Search Admin sửa trực tiếp projection sau khi đã backfill, dữ liệu sẽ **lệch trở lại**.

### Bước 3 — Đặc tả định danh và phép biến đổi

Ví dụ:

~~~~text
Key:
  product_id UUID globally unique.

Catalog state:
  title TEXT
  price NUMERIC(14,2)
  currency = VND
  version BIGINT

Search projection:
  title = Catalog.title
  list_price = Catalog.current_list_price
  currency_code = Catalog.currency_code
  source_version = Catalog.version

Transformation:
  Exact decimal, no float rounding.
  No timezone conversion needed for price amount.
  Source event contains full state.
~~~~

Nếu đích cần chuẩn hóa tên, tìm kiếm không dấu, stemmer hoặc tokenization, các trường đó là **dẫn xuất** và nên được kiểm tra theo **quy tắc transform**, không so chuỗi từng byte với trường nguồn.

### Bước 4 — Bảo vệ đường thay đổi mới trước khi sửa dữ liệu cũ

Thiết kế luồng:

1. Ghi Catalog và outbox **trong cùng transaction cục bộ**.
2. Relay phát event versioned với khả năng retry.
3. Search xác thực và upsert khi version lớn hơn; inbox chống lặp.
4. Có event unpublish/tombstone khi cần.
5. Có monitoring lag/conflict và phương án rebuild.

Nếu chưa bảo vệ đường ghi mới mà đã chạy backfill, chỉ cần một lần cập nhật Catalog xảy ra sau backfill là dữ liệu lại có thể lệch.

### Bước 5 — Xây dựng snapshot nhất quán, bắt thay đổi không hở khoảng

Chọn chiến lược bootstrap có **vị trí bắt log hoặc mốc phiên bản nhất quán**. Trong giai đoạn dựng projection, có thể tạm dùng cả snapshot và event chồng nhau; consumer phải idempotent để **chấp nhận lặp nhưng không mất thay đổi**.

Sau dựng index:

- Kiểm tra số sản phẩm được phép xuất bản.
- Kiểm tra source_version theo sản phẩm.
- So title/price/currency đúng quy tắc.
- Kiểm tra dữ liệu không còn ở nguồn nhưng còn trong projection.
- Phân tích các hàng không map được hoặc dữ liệu ngoài miền.

### Bước 6 — Cutover có kiểm soát

Chuyển các reader sang bản sao mới, nhưng chỉ khi:

- Độ mới và tỷ lệ lỗi đạt SLO.
- Không còn đường sửa projection ngoài đồng bộ.
- Có thể tắt bản sao mới hoặc quay đọc nguồn trong trường hợp cần, nếu access pattern cho phép.
- Checkout không phụ thuộc giá Search stale để chốt mua.
- Có cơ chế hiển thị, fallback hoặc tạm từ chối thao tác yêu cầu nhất quán mạnh khi nguồn chuẩn không sẵn sàng.

**Không nên chuyển toàn bộ người dùng sang projection mới chỉ vì job backfill đã chạy xong một lần.**

### Bước 7 — Dọn cơ chế cũ, duy trì đối soát

Sau khi ổn định:

- Loại bỏ job ghi hai chiều hoặc bảng/trigger trung gian không còn cần.
- Thu hồi quyền viết trực tiếp của hệ thống đọc.
- Duy trì **reconciliation** theo lịch và cảnh báo.
- Quy định quy trình **repair từ nguồn chuẩn**, không sửa tay mất lineage.
- Đánh giá chi phí, retention, quyền dữ liệu và kế hoạch thay đổi schema/event sau này.

### Lộ trình mô tả bằng sơ đồ

~~~~mermaid
flowchart TD
    A["Phát hiện các bản sao lệch"] --> B["Phân loại cùng nghĩa hay khác nghĩa"]
    B --> C{"Cùng dữ kiện hiện hành?"}
    C -- "Không" --> D["Định nghĩa snapshot / field riêng"]
    C -- "Có" --> E["Chỉ rõ source of truth + owner"]
    E --> F["Thiết kế version/event/repair contract"]
    F --> G["Chặn writer cạnh tranh"]
    G --> H["Bootstrap + capture changes"]
    H --> I["Đối soát version, giá trị và deletion"]
    I --> J{"Đủ điều kiện cutover?"}
    J -- "Không" --> K["Quarantine, replay hoặc fix mapping"]
    K --> I
    J -- "Có" --> L["Cutover + monitor + cleanup"]
~~~~

## 13. Kiểm thử và giám sát dữ liệu đồng bộ

### 13.1. Ma trận kiểm thử cho luồng Catalog → Search

| Tình huống | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Tạo sản phẩm | v1, đầy đủ dữ liệu | Search có đúng một product ở v1 |
| Đổi tên/giá | v2, full-state | Search lên v2 và giá/tên mới |
| Replay cùng eventId | Gửi lại event v2 | Không cập nhật lần hai |
| Event cũ đến muộn | Đã v2, nhận v1 | Giữ nguyên v2 |
| Event tương lai đến trước | Chưa v2, nhận v3 full-state | Có thể lên v3 nếu đầy đủ/đúng contract |
| Delta bị thiếu version | Nhận delta v3 nhưng thiếu v2 | Phát hiện gap, không cộng mù |
| Cùng version, payload khác | Event v2 có giá khác nguồn v2 | Báo conflict/quarantine, không coi thành công |
| Sai currency | Payload USD khi contract yêu cầu VND | Từ chối hoặc chuyển theo phép chuẩn đã phê duyệt |
| Sai tenant/key | Product P01 của tenant B | Không ghi vào projection tenant A |
| Event bị mất | v2 không đến Search | Lag/reconciliation phát hiện và sửa |
| Ngừng xuất bản | ProductUnpublished v4 | Không hiển thị; event cũ không làm sống lại |
| Snapshot lúc có ghi | Backfill + event đồng thời | Không mất và không nhân bản hàng |
| Search mất dữ liệu | Rebuild projection | Hội tụ theo snapshot/log đáng tin |
| Catalog đổi giá sau đơn | Giá Catalog 120.000 | Sales accepted price 90.000 không đổi |
| Consumer chết giữa transaction | Đã ghi inbox nhưng chưa projection | ROLLBACK cả hai và retry thành công |
| Hai event khác ID cùng nghiệp vụ | Bản tin chứa same product/version | Không lặp hiệu ứng; phát hiện collision nếu payload khác |

**Không có một bài thử duy nhất chứng minh mọi điều kiện.** Test tuần tự đơn giản không thay thế kiểm thử concurrency và test khôi phục sau sự cố.

### 13.2. Bộ kiểm tra SQL tối thiểu

**Kiểm tra Search chưa bắt kịp Catalog:**

~~~~sql
SELECT
    c.product_id, c.version, s.source_version
FROM cp_catalog.product AS c
LEFT JOIN cp_search.product_projection AS s
    ON s.product_id = c.product_id
WHERE s.product_id IS NULL
   OR s.source_version < c.version;
~~~~

**Kiểm tra giá trị khác nhau khi version bằng:**

~~~~sql
SELECT c.product_id, c.version,
       c.current_list_price AS catalog_price,
       s.list_price AS search_price
FROM cp_catalog.product AS c
JOIN cp_search.product_projection AS s
    ON s.product_id = c.product_id
WHERE c.version = s.source_version
  AND (
       c.current_list_price IS DISTINCT FROM s.list_price
    OR c.title IS DISTINCT FROM s.title
    OR c.sku IS DISTINCT FROM s.sku
    OR c.currency_code IS DISTINCT FROM s.currency_code
  );
-- Kỳ vọng 0 dòng nếu mapping Search đúng 1:1.
~~~~

**Kiểm tra bản ghi outbox chưa được đánh dấu phát:**

~~~~sql
SELECT event_id, product_id, aggregate_version, occurred_at
FROM cp_catalog.outbox_event
WHERE published_at IS NULL
ORDER BY occurred_at, event_id;
~~~~

Một hàng chưa published **không chắc đã thất bại**: relay có thể chưa đến lượt hoặc đã publish rồi nhưng chết trước khi cập nhật trạng thái. Dựa vào **tuổi hàng, backlog, retry và trạng thái broker** để quyết định khi nào cảnh báo.

**Kiểm tra giá chốt vẫn giữ độc lập:**

~~~~sql
SELECT
    l.line_id,
    l.product_title_at_purchase,
    l.accepted_unit_price,
    l.line_amount,
    c.title AS current_catalog_title,
    c.current_list_price AS current_catalog_price
FROM cp_sales.order_line AS l
LEFT JOIN cp_catalog.product AS c
    ON c.product_id = l.catalog_product_ref;
~~~~

Phép JOIN cuối là **truy vấn giảng dạy trong cùng database**. Việc giá khác nhau không được coi là lỗi nếu giá chốt và giá hiện hành có ngữ nghĩa khác.

### 13.3. Các metric vận hành

| Metric | Phát hiện vấn đề |
| --- | --- |
| **Outbox pending count / oldest age** | Relay không theo kịp hoặc bị kẹt |
| **Consumer lag / last applied offset** | Message tồn đọng, bản đọc chậm |
| **Source-version gap** | Product copy đang tụt sau nguồn |
| **Divergence count theo trường và version** | Sai mapping hoặc sửa trực tiếp projection |
| **Duplicate-event count** | Retry bình thường hoặc upstream gửi trùng bất thường |
| **Version-conflict count** | Cùng version nhưng payload khác |
| **Dead-letter / quarantine count** | Payload lỗi hoặc không thể xử lý tự động |
| **Rebuild/replay duration** | Khả năng phục hồi index |
| **Missing or orphan projection count** | Bootstrap thiếu hoặc xóa không đồng bộ |
| **Correction latency** | Thời gian từ phát hiện đến khi hội tụ |
| **Checkout quote mismatch** | Rủi ro giá đọc từ Search không còn hợp lệ tại lúc chốt |

Phải có **mốc đo, ngưỡng và người xử lý**. Dashboard xanh chỉ vì số event nhận thành công nhiều không chứng minh hàng bị **mất vĩnh viễn** đã được phát hiện.

### 13.4. Phân loại sự cố để không “repair” sai

| Loại | Dấu hiệu | Hành động phù hợp |
| --- | --- | --- |
| **Stale within SLO** | Search version thấp hơn một chút, backlog đang xử lý | Chấp nhận độ trễ theo hợp đồng, quan sát |
| **Stale beyond SLO** | Version thấp lâu hơn giới hạn | Điều tra relay/consumer; replay hoặc rebuild |
| **Divergent same version** | Search và Catalog cùng version nhưng khác giá | Quarantine, kiểm tra transform/quyền ghi, sửa từ nguồn tin cậy |
| **Ambiguous identity** | SKU/tenant mapping không rõ | Dừng đồng bộ hàng liên quan, xác minh business key |
| **Conflicting authorities** | Hai hệ thống sửa cùng field | Chốt ownership hoặc quy tắc hòa giải trước khi ghi đè |
| **Legitimate snapshot difference** | Sales accepted price khác Catalog | Không sửa theo phép so bằng nhau; giữ nghĩa lịch sử |
| **Deletion not propagated** | Sản phẩm đã gỡ còn hiển thị | Xem tombstone/retention và thứ tự event |
| **Corrupted source** | Giá nguồn sai do nhập nhầm | Sửa nguồn theo quy trình nghiệp vụ rồi phát thay đổi mới |

### 13.5. Khả năng truy nguyên và dữ liệu nhạy cảm

Để điều tra một giá sai, nên tra được:

~~~~text
product_id
tenant_id / source scope
catalog_version
source_event_id
event schema_version
source occurred_at
Search applied_at
transform_version
reconciliation status
correction/replay ticket
~~~~

Nhưng **không ghi toàn bộ email, địa chỉ, token hoặc thông tin thanh toán nhạy cảm vào log chỉ để debug dễ hơn**. Metadata, hash hoặc dữ liệu rút gọn có thể đủ theo hợp đồng và chính sách riêng tư. Logs và dead-letter queues cũng là các **bản sao dữ liệu** cần được quản lý retention/quyền truy cập.

## 14. Chọn cấu trúc phù hợp thay vì luôn sao chép

### 14.1. Cây quyết định theo mục đích dữ liệu

Trước khi thêm một bản sao mới, thử lần lượt:

1. **Có cần giữ lịch sử bất biến của giao dịch không?** Nếu có, thiết kế snapshot có nghĩa riêng và ràng buộc sửa đổi; không đồng bộ đè theo nguồn hiện hành.
2. **Có phải bản đọc của trạng thái hiện hành không?** Nếu có, chọn nguồn chuẩn, độ mới cho phép, cơ chế cập nhật và quy tắc sửa lệch.
3. **Có cần kết quả nhất quán tại thời điểm quyết định quan trọng không?** Nếu có, cân nhắc hỏi nguồn có thẩm quyền, quote có hiệu lực, giao dịch cục bộ hoặc bước xác nhận riêng.
4. **Có thể chấp nhận độ trễ không?** Nếu có, cache/projection/replica có thể hợp lý nhưng cần freshness SLO.
5. **Có phải chỉ số tổng hợp theo thời gian?** Nếu có, định nghĩa grain, cách cộng, nguồn fact/dimension, lịch sử và làm mới dữ liệu.
6. **Có nhiều nguồn thực sự được phép sửa không?** Nếu có, phải thiết kế conflict resolution, provenance và quyền sở hữu trường; không mặc định “last record wins”.
7. **Có thể rebuild bản sao từ nguồn chuẩn không?** Nếu không, bản sao có thể đang chứa **dữ liệu gốc hoặc quyết định riêng**, cần xem lại phân loại/ownership.

### 14.2. Đánh đổi giữa chuẩn hóa và phi chuẩn hóa

| Tiêu chí | Chuẩn hóa quan hệ đúng mức | Phi chuẩn hóa/projection có kiểm soát | Dư thừa không có quy tắc |
| --- | --- | --- | --- |
| Quyền sở hữu | Thường rõ trong một write model | Nguồn và đích được xác định | Mơ hồ hoặc cạnh tranh |
| Chi phí cập nhật | Ghi nguồn và quan hệ chuẩn hóa | Cần đồng bộ, version và đối soát | Phát sinh update anomalies |
| Truy vấn | Có thể cần JOIN | Có thể đọc nhanh theo access pattern | Có thể nhanh nhưng không đáng tin |
| Lịch sử | Cần thiết kế snapshot/temporal riêng | Có thể lưu snapshot được định nghĩa | Dễ bị ghi đè hoặc sai thời điểm |
| Khả năng thay đổi | Ràng buộc FK/transaction rõ | Contract/version giúp tách biệt | Một thay đổi gây sai lệch dây chuyền |
| Vận hành | Giám sát DB constraints | Thêm relay, consumer, freshness metrics | Khó tìm gốc và phục hồi |
| Khi nào chọn | Dữ liệu có phụ thuộc và invariant cục bộ | Có lợi ích đọc/độ bền lịch sử rõ | Không nên chấp nhận như trạng thái thiết kế |

**Quyết định đúng không phải luôn xóa dữ liệu lặp**. Một projection có đủ hợp đồng có thể là thiết kế tốt hơn việc JOIN trực tiếp năm hệ thống tác nghiệp cho mỗi request. Ngược lại, nếu không có lý do hiệu năng, lịch sử hoặc tách ranh giới đáng kể, bỏ bản sao có thể **giảm chi phí và lỗi**.

### 14.3. Đặc tả tối thiểu trước khi tạo bản sao

Một tài liệu ngắn có thể là:

~~~~text
Replica/Projection name:
Business purpose:
Authoritative fields/source:
Business key and scope:
Snapshot or current-state semantics:
Writer permissions:
Event/API/CDC/batch contract:
Schema/transform version:
Source ordering/version and conflict behavior:
Freshness SLO and fallback:
Duplicate/late/delete handling:
Bootstrap and replay procedure:
Reconciliation rules:
Sensitive-data policy:
Owner and on-call:
Decommissioning conditions:
~~~~

Nếu tài liệu chưa trả lời **nguồn chuẩn, ai được sửa, cách cập nhật và cách phát hiện lệch**, hãy hoãn tạo thêm một bản sao cùng nghĩa. Đó thường là chi phí thiết kế nhỏ hơn nhiều so với sửa dữ liệu sai ở production.

## 15. Checklist kiểm chứng dư thừa dữ liệu có kiểm soát

### 15.1. Ngữ nghĩa và quyền sở hữu

- [ ] Mỗi bản sao có **mục đích** rõ: snapshot, cache, projection, replica hay phân tích.
- [ ] Các trường lặp đã được xác nhận **cùng nghĩa hay khác nghĩa**.
- [ ] Có nguồn có thẩm quyền theo **trường/phạm vi/thời điểm**; không mặc định một DB làm chủ mọi thuộc tính.
- [ ] Không có hai writer được sửa cùng thuộc tính hiện hành nếu chưa có **giao thức conflict**.
- [ ] Business key bao gồm đúng tenant/source/phiên bản nếu phạm vi yêu cầu.
- [ ] Snapshot lịch sử không bị job đồng bộ giá trị hiện tại ghi đè.
- [ ] Quyền truy cập bản sao không vượt quá mục đích và chính sách dữ liệu.

### 15.2. Hợp đồng thay đổi và đồng bộ

- [ ] Trigger phát thay đổi được xác định: API, event, CDC, batch, polling hay TTL.
- [ ] Payload có **schema version**, đơn vị, ID và ngữ nghĩa được công bố.
- [ ] Phân biệt **full-state** và **delta**; delta có quy tắc gap/ordering.
- [ ] Nguồn cấp version/sequence theo phạm vi thích hợp.
- [ ] Consumer chống event lặp và cập nhật lùi version.
- [ ] Consumer phát hiện **cùng version nhưng nội dung mâu thuẫn**.
- [ ] DB state và outbox nằm trong cùng transaction cục bộ khi dùng outbox.
- [ ] Inbox và cập nhật projection commit/rollback cùng nhau.
- [ ] Có retry, dead-letter/quarantine, replay và idempotency theo nghiệp vụ khi cần.
- [ ] Có hợp đồng **unpublish/delete/tombstone**, không làm dữ liệu đã gỡ sống lại khi replay.
- [ ] Bootstrap snapshot và change stream không có khoảng hở không được kiểm chứng.

### 15.3. Độ mới, đối soát và vận hành

- [ ] Có mức trễ cho phép và fallback cho các quyết định cần độ mới cao hơn.
- [ ] Có metric backlog, oldest unprocessed, consumer lag, version gap.
- [ ] Có đối soát **giá trị khi cùng version**, không chỉ so số hàng hoặc timestamp.
- [ ] Khi phát hiện lệch, có quy trình **repair từ nguồn chuẩn** hoặc quy trình xử lý conflict.
- [ ] Có kiểm tra missing/orphan, xóa, tenant ID không map được.
- [ ] Có thể dựng lại projection từ snapshot/log có thẩm quyền.
- [ ] Có kiểm thử lỗi sau COMMIT, gửi trùng, đến trễ, đảo thứ tự và khởi động lại.
- [ ] Có trace/lineage đủ điều tra nhưng không lạm dụng dữ liệu cá nhân trong log.
- [ ] Các bản sao không còn cần được thu hồi với đánh giá quyền và retention.

### 15.4. Điều kiện nghiệm thu của từng bản sao

| Mục tiêu | Bằng chứng cần có |
| --- | --- |
| **Đúng nguồn** | Ownership matrix và danh sách writer |
| **Đúng nghĩa** | Contract của trường, thời gian, đơn vị và phạm vi |
| **Đúng bản ghi** | Key/mapping xác thực và test khác tenant |
| **Không mất cập nhật** | Outbox/CDC/đường đồng bộ có kiểm thử lỗi |
| **Không lặp hiệu ứng** | Inbox/idempotency tests và business key |
| **Không cập nhật lùi** | Event v3 trước v2, replay v1 và cùng version conflict |
| **Bản đọc đủ mới** | SLO có mốc đo và cảnh báo |
| **Có thể sửa** | Reconciliation, replay, rebuild, delete handling |
| **Đúng lịch sử** | Snapshot Sales không đổi khi Catalog cập nhật |
| **Đúng quyền** | Owner, access controls và retention theo phạm vi |

**Một bản sao chỉ nên được coi là “đã kiểm chứng” trong phạm vi các thuộc tính và giao thức đã thử.** SQL chạy thành công hoặc broker gửi được một message không chứng minh mọi dữ liệu ở mọi consumer đã hội tụ.

## 16. Bài tập thực hành có đáp án

### Bài 1 — Giá khác nhau có chắc là dữ liệu sai?

P01 có Catalog.current_list_price = 120.000 VND, Search.list_price = 110.000 VND, Sales.accepted_unit_price của đơn tháng trước = 90.000 VND.

**Câu hỏi:** Giá nào cần hội tụ và giá nào không được tự động đồng bộ?

**Đáp án:** Nếu Search là projection của **giá niêm yết hiện hành** từ Catalog, nó phải hội tụ về **120.000** trong độ trễ cho phép; 110.000 thể hiện có thể đang stale hoặc sai mapping. Sales.accepted_unit_price = **90.000** là **snapshot giá chốt**, không cần bằng Catalog. Không UPDATE giá đơn lịch sử cho bằng giá hiện hành.

### Bài 2 — Có thật sự một nguồn chuẩn duy nhất cho mọi trường?

Catalog sở hữu tên/giá niêm yết, Inventory sở hữu số hàng có thể cấp phát, Billing sở hữu tiền đã quyết toán. Một nhóm đề nghị chuyển tất cả trường về Catalog để “có một source of truth”.

**Câu hỏi:** Đề xuất có đúng không?

**Đáp án:** Không. **Nguồn chuẩn phải được xác định theo thuộc tính, ngữ cảnh và thời điểm**. Catalog không nên tự ghi tồn kho hoặc giao dịch đã quyết toán vì những dữ kiện đó có invariant và chủ sở hữu riêng. Có thể có một trang tổng hợp nhưng đó là **read model**, không phải một write model toàn cục.

### Bài 3 — Snapshot hay projection?

Đơn O100 lưu product_title_at_purchase. Catalog đổi tên sản phẩm ngày hôm sau.

**Câu hỏi:** Có nên cập nhật product_title_at_purchase không?

**Đáp án:** Thông thường **không** nếu trường được định nghĩa là tên hiển thị tại lúc mua. Nó là dữ liệu lịch sử có ý nghĩa riêng. Search.current_title có thể cập nhật theo tên mới. Nếu cần sửa sai chứng từ lịch sử, phải có quy trình sửa/điều chỉnh theo nghiệp vụ, không dùng job đồng bộ định kỳ viết đè.

### Bài 4 — Hai nguồn cùng sửa một giá

Catalog Admin cập nhật giá P01 thành 110.000, Search Admin cập nhật P01 thành 120.000. Một job ban đêm copy Catalog → Search.

**Câu hỏi:** Vấn đề gốc và cách sửa là gì?

**Đáp án:** Có **hai writer cạnh tranh cho một thuộc tính** mà không có quy tắc ownership/conflict. Nếu giá niêm yết thuộc Catalog, Search Admin không nên sửa trực tiếp cùng trường. Có thể gửi yêu cầu cập nhật về Catalog hoặc tạo **giá khuyến mại riêng** với nghĩa, quyền sở hữu và precedence rõ.

### Bài 5 — TTL có bảo đảm đúng giá ngay khi chốt đơn không?

Redis cache giá trong 5 phút. Catalog đổi giá, khách thanh toán sau 20 giây dựa vào cache.

**Câu hỏi:** Cache TTL = 5 phút có bảo đảm giá đang đúng không?

**Đáp án:** Không. Trong tối đa 5 phút hoặc lâu hơn nếu cơ chế refresh lỗi, cache có thể stale. Nếu quy trình chốt giá yêu cầu nhất quán mạnh hoặc quote được chấp nhận, cần **xác minh nguồn định giá/quote có hiệu lực** trước khi ghi snapshot đơn. Cache có thể phục vụ hiển thị, nhưng không tự là thẩm quyền cho mọi giao dịch.

### Bài 6 — Event full-state đến sai thứ tự

Nguồn phát:

~~~~text
v1 = 100000
v2 = 110000
v3 = 120000
~~~~

Consumer nhận v3 rồi mới nhận v2, cả hai chứa giá trị full-state và version đúng.

**Câu hỏi:** Sau cả hai event, giá Search nên là bao nhiêu?

**Đáp án:** **120.000** ở source_version **3**. Consumer áp version mới hơn và **bỏ qua event cũ**; không lấy bản tin nhận sau làm sự thật mới. Đây là trường hợp có thể hội tụ với full-state event.

### Bài 7 — Event delta thiếu phiên bản

Giá ở v1 là 100.000. Event v2 và v3 lần lượt mang priceDelta = +10.000. Consumer chỉ nhận v3.

**Câu hỏi:** Có thể cộng +10.000 vào v1 rồi coi là giá v3 không?

**Đáp án:** **Không**, vì thiếu delta v2. Nếu chỉ cộng delta v3, giá thành 110.000 thay vì **120.000**. Cần phát hiện **version gap**, phát lại chuỗi thiếu hoặc tải snapshot full-state có thẩm quyền. Full-state và delta cần quy tắc xử lý khác nhau.

### Bài 8 — Cùng eventId gửi lại

Consumer đã xử lý event e-100 thành công nhưng relay gửi lại e-100 sau khi bị lỗi trước bước đánh dấu đã publish.

**Câu hỏi:** Inbox giúp gì? Có cần coi đây là lỗi relay nghiêm trọng ngay lập tức không?

**Đáp án:** Consumer thấy eventId đã xử lý và **không lặp tác dụng phụ**. Gửi lại có thể là tình huống bình thường của cơ chế at-least-once; cần monitoring tần suất và nguyên nhân nhưng không phải mặc định sửa bằng cách bỏ outbox. Inbox phải được commit cùng cập nhật projection.

### Bài 9 — Inbox ghi trước, projection ghi sau

Consumer lưu eventId vào inbox, COMMIT, rồi mới UPDATE Search. Tiến trình chết ở giữa.

**Câu hỏi:** Điều gì xảy ra khi event được gửi lại?

**Đáp án:** Consumer có thể bỏ qua event vì đã thấy inbox, trong khi Search chưa được cập nhật. Phải **ghi inbox và projection trong cùng transaction cục bộ**; nếu lỗi, cả hai rollback để retry an toàn.

### Bài 10 — Chỉ có source_version có đủ không?

Catalog và Search đều ghi source_version=2 nhưng Catalog giá 120.000 và Search giá 110.000.

**Câu hỏi:** Có thể coi bản sao đã hội tụ không?

**Đáp án:** **Không.** Cùng version nhưng giá khác là **DIVERGENT_SAME_VERSION** theo hợp đồng ánh xạ 1:1. Cần điều tra mapping, payload, quyền ghi, event collision hoặc restore không tương thích. Version cho thứ tự, không bảo đảm nội dung đúng.

### Bài 11 — Version thấp hơn có luôn là lỗi nghiêm trọng?

Catalog ở v3, Search ở v2 trong 3 giây. Hợp đồng cho phép độ trễ 60 giây trong điều kiện bình thường.

**Câu hỏi:** Có nên UPDATE thủ công Search ngay không?

**Đáp án:** Không nhất thiết. Đó có thể là **stale trong giới hạn SLO**, cần quan sát backlog và khả năng hội tụ. Nếu Search vẫn v2 sau nhiều phút, cần điều tra và sửa. Không dùng một lần đo version gap để kết luận sự cố mà bỏ qua **thời gian và độ mới được cam kết**.

### Bài 12 — Version bằng nhau nhưng dữ liệu dẫn xuất khác

Catalog.title = “Sổ tay A5”; Search có search_tokens = “so tay a5” do chuẩn hóa dấu, chữ hoa/thường.

**Câu hỏi:** search_tokens không bằng Catalog.title có phải lỗi không?

**Đáp án:** **Không tự là lỗi** vì search_tokens là trường **dẫn xuất theo phép biến đổi**. Phải kiểm tra theo **quy tắc tokenizer/normalization** và phiên bản transform, không so chuỗi nguyên văn. Nhưng Search.catalog_title_projection nếu được định nghĩa là bản sao 1:1 của Catalog.title thì phải so đúng giá trị.

### Bài 13 — Polling theo timestamp thiếu tie-breaker

Job dùng WHERE updated_at > last_timestamp. Hai hàng P01 và P02 có cùng updated_at; job xử lý P01 rồi dừng, checkpoint tại timestamp ấy.

**Câu hỏi:** P02 có thể bị bỏ sót không?

**Đáp án:** **Có.** Lần sau lọc > timestamp sẽ không lấy P02. Có thể dùng cursor tổng thứ tự **(updated_at, product_id)**, overlap window/dedup hoặc CDC/log offset, nhưng vẫn phải xét transaction commit muộn và xóa hàng. Chỉ thêm tie-breaker chưa tự xử lý mọi trường hợp phát sinh ở nguồn.

### Bài 14 — Đổi giá rồi ghi event trong hai transaction

Catalog COMMIT giá mới rồi mới gửi event; trước khi gửi, server chết.

**Câu hỏi:** Rủi ro gì và outbox giải quyết phần nào?

**Đáp án:** Catalog đã có giá mới nhưng Search có thể **không bao giờ nhận thay đổi** nếu không có cơ chế phát lại. Transactional outbox ghi **thay đổi nguồn + ý định phát event** cùng transaction; relay có thể retry. Nó không tự bảo đảm exactly-once delivery, nên consumer vẫn phải idempotent.

### Bài 15 — Rebuild index trong khi nguồn vẫn cập nhật

Một job quét Catalog từ 10:00 đến 10:10. Consumer chỉ bắt đầu nhận event mới từ sau 10:10. P01 đổi giá lúc 10:05.

**Câu hỏi:** Có thể mất thay đổi không? Khắc phục bằng gì?

**Đáp án:** **Có**, nếu bản snapshot quét không chứa đúng cập nhật lúc 10:05 và stream bắt đầu quá muộn. Cần bootstrap bằng **snapshot và change log/watermark nhất quán**, chấp nhận có thể replay/trùng nhưng không bỏ sót, sau đó đối soát với nguồn.

### Bài 16 — Xóa sản phẩm rồi nhận event cũ

Catalog phát ProductUnpublished v4; Search gỡ sản phẩm. Sau đó Search nhận ProductPublished v2 do replay.

**Câu hỏi:** Có nên INSERT lại sản phẩm theo v2 không?

**Đáp án:** **Không.** Event v2 cũ hơn quyết định gỡ ở v4. Consumer phải giữ metadata/tombstone **phiên bản đã áp dụng**, hoặc một cơ chế kiểm tra nguồn tương đương, để event cũ không làm bản ghi sống lại. Chỉ xóa hàng mà bỏ hết thông tin phiên bản có thể làm hệ thống tái xuất bản sai.

### Bài 17 — Một cột paid của hai hệ thống

Sales có paid=true do nhân viên tự bật; Billing ghi payment_status=PENDING vì cổng chưa quyết toán.

**Câu hỏi:** Bên nào nên là nguồn thẩm quyền cho tiền đã quyết toán?

**Đáp án:** Billing/Payments theo hợp đồng thanh toán đã công bố. Sales có thể giữ **projection** nhưng không được sửa nó để tự tuyên bố tiền đã thu. Cần xét cả các trạng thái **authorized, partially_paid, settled, refunded** nếu nghiệp vụ có; một boolean paid có thể làm mất ý nghĩa.

### Bài 18 — Dữ liệu khác tenant cùng SKU

Tenant A có sku NOTE-A5, giá 100.000. Tenant B cũng dùng NOTE-A5, giá 150.000. Job đồng bộ Search theo sku và bỏ qua tenant.

**Câu hỏi:** Kết quả có thể sai thế nào?

**Đáp án:** Hai sản phẩm có thể **bị gộp hoặc ghi đè** trên cùng bản ghi Search. Cần business key gồm **(tenant_id, sku)** hoặc product_id toàn hệ thống có mapping đúng; kiểm thử cả trường hợp cùng SKU khác tenant. Không chỉ thêm version nếu định danh nguồn đã sai.

### Bài 19 — Duplicate payment cùng số tiền

Hai giao dịch P100 và P101 đều có giá trị 100.000 VND, đều hợp lệ. Một báo cáo dùng SUM(DISTINCT amount) để tránh ghi trùng.

**Câu hỏi:** Tổng báo cáo là bao nhiêu và đúng ra phải bao nhiêu?

**Đáp án:** SUM(DISTINCT amount) cho **100.000**, trong khi tổng đúng là **200.000 VND**. DISTINCT trên giá trị không phân biệt **hai sự kiện hợp lệ**. Cần nhận diện bản ghi theo payment_id/eventId/business key và chống lặp ở ranh giới ingestion.

### Bài 20 — Tạo golden record chỉ bằng email

CRM và ERP đều có người dùng email shared@example.org nhưng thuộc hai tổ chức khác nhau. Một ETL gộp chúng thành một customer chỉ vì email trùng.

**Câu hỏi:** Đây là lỗi nào?

**Đáp án:** **Lỗi hợp nhất danh tính**: email không đủ chứng minh cùng người hoặc cùng tư cách pháp lý. Cần định nghĩa identity, nguồn, tenant/tổ chức và bằng chứng matching; có quy trình steward/khả năng **unmerge** khi gộp sai. Golden record phải có **quy tắc survivorship theo field**, không chỉ SELECT DISTINCT.

### Bài 21 — Vì sao Search không cần FK SQL đến Catalog trong mọi triển khai?

Catalog ở một DB, Search dùng công cụ chỉ mục riêng. Một kiến trúc sư muốn tạo FK vật lý từ mọi document Search về bảng Catalog.

**Câu hỏi:** Có bắt buộc và khả thi như một FK cùng PostgreSQL không?

**Đáp án:** Không. Cross-database/service không có **FK SQL thông thường** bảo vệ như cùng một DB. Search giữ **external product reference**, sử dụng event/API, version và đối soát. Khi một hệ thống dùng cùng DB có thể đặt FK được về mặt kỹ thuật, nhưng phải cân nhắc coupling và quyền sở hữu của từng context, đặc biệt với lịch sử.

### Bài 22 — Projection cùng version nhưng update timestamp rất mới

Search.source_version = 2, Catalog.version = 3. Một replay v2 khiến Search.synced_at được cập nhật thành “vừa xong”, nhưng giá Search vẫn ở v2.

**Câu hỏi:** Có thể báo “Search đồng bộ xong” vì synced_at mới không?

**Đáp án:** **Không.** synced_at mới có thể chỉ phản ánh một lần xử lý/replay, không chứng minh Search đã áp version 3. Cần theo dõi **source_version**, consumer lag và đối soát; thiết kế không nên cập nhật synced_at nếu event cũ không thực sự thay đổi projection.

### Bài 23 — Sửa bản sao sai bằng UPDATE thủ công

Đội vận hành phát hiện Search sai giá và UPDATE trực tiếp giá về 120.000, nhưng Catalog vẫn ở 110.000 và tiếp tục phát event cho P01.

**Câu hỏi:** Sửa như vậy có bền vững không?

**Đáp án:** **Không.** Lần đồng bộ tiếp theo có thể ghi lại giá 110.000. Phải xác định **nguồn nào đúng theo nghiệp vụ**, sửa thông qua nguồn có thẩm quyền và phát sự kiện/version hợp lệ; nếu mapping Search sai thì sửa transform/consumer rồi rebuild. Manual repair tại đích phải có kiểm soát và lineage, không tạo thêm nguồn ghi cạnh tranh.

### Bài 24 — Thiết kế hợp đồng bản sao mới

Nhóm muốn tạo một Search projection và được yêu cầu nêu **ít nhất tám thông tin** trước khi triển khai.

**Đáp án tham khảo:**

1. Mục đích và **ý nghĩa trường** được nhân bản.
2. **Nguồn có thẩm quyền** và người sở hữu.
3. **Business key/tenant scope**.
4. Quy tắc phát thay đổi và **event schema/version**.
5. Full-state hay delta, **ordering/gap policy**.
6. Cách chống event trùng và cập nhật lùi.
7. **Freshness SLO**, điều kiện quá hạn và fallback.
8. Quy tắc **delete/tombstone**.
9. Quy trình **snapshot bootstrap + replay**.
10. Truy vấn/logic **reconciliation và repair**.
11. Chính sách thông tin nhạy cảm, quyền và retention.
12. Owner vận hành, metric, cảnh báo và kế hoạch decommission.

Nếu thiếu nguồn chuẩn và quyền ghi, việc thêm version, trigger hay job đồng bộ chỉ làm hệ thống có nhiều **bản sao lỗi được làm mới đều đặn**.

### Bài 25 — Phân loại khi nào phải đối soát bằng nhau

Một hồ sơ Customer có current_phone. Một Order có recipient_phone_at_purchase. Một Search document có customer_current_phone. Người kiểm thử đề xuất yêu cầu cả ba luôn bằng nhau.

**Câu hỏi:** Bài test nào đúng, bài test nào sai về ngữ nghĩa?

**Đáp án:** Nếu Search.customer_current_phone là bản sao **được phép** của Customer.current_phone, có thể đối soát chúng sau khi xét version/freshness, quyền và phạm vi định danh. Nhưng **recipient_phone_at_purchase** là số dùng cho đơn tại lúc mua; có thể khác số hồ sơ hiện hành và khác người nhận. Không yêu cầu cả ba bằng nhau. Trước khi đối soát, phải xác định **đối tượng, vai trò, thời điểm và chính sách dữ liệu cá nhân**.

### Bài 26 — Kiểm thử sự cố của outbox và inbox

Catalog COMMIT state + outbox. Relay gửi event thành công nhưng chết trước khi đánh dấu published. Search nhận và xử lý event, rồi relay phát lại.

**Câu hỏi:** Cần chứng minh những bất biến nào để hệ thống vẫn đúng?

**Đáp án:** (1) State và outbox **commit cùng nhau** tại Catalog; (2) relay có thể **phát lại** mà không làm mất sự kiện; (3) Search dùng inbox/eventId và business version để **không ghi lại tác dụng**; (4) inbox và projection commit cùng nhau; (5) nếu consumer chết giữa transaction, retry hoàn tất an toàn; (6) monitoring phát hiện thông điệp kẹt hoặc dữ liệu không hội tụ.

### Bài 27 — Có nên dùng last-write-wins cho mọi trường?

Một bản cập nhật offline từ hôm qua đến muộn và ghi đè giá hiện hành vừa được Catalog chấp thuận.

**Câu hỏi:** LWW theo thời gian nhận có hợp lệ không?

**Đáp án:** Không mặc định. Thời gian **nhận muộn** không chứng minh **ý định mới hơn**, và đồng hồ có thể lệch. Nếu Catalog là nguồn có thẩm quyền, dùng version/concurrency contract của Catalog. Nếu thật sự có nhiều writer, cần **quy tắc conflict resolution được nghiệp vụ chấp thuận**; LWW có thể gây mất cập nhật và không phù hợp cho giá, tiền hoặc quyền.

### Bài 28 — Một kế hoạch sửa dữ liệu lệch hoàn chỉnh

Catalog có 50.000 sản phẩm, Search có 49.500 hàng, giá của 300 hàng lệch. Search vẫn cho phép admin chỉnh giá trực tiếp; một batch ban đêm copy toàn bộ Catalog nhưng thường bị dừng giữa chừng.

**Câu hỏi:** Nêu các bước ưu tiên để đưa hệ thống về trạng thái có thể kiểm chứng.

**Đáp án tham khảo:**

1. Xác định **Catalog có thẩm quyền** cho giá niêm yết hiện hành và các trường thật sự cùng nghĩa.
2. Kiểm kê mọi writer/reader, giới hạn hoặc gỡ quyền Search admin sửa trực tiếp.
3. Chốt business key, mapping, version, currency, chính sách ngừng xuất bản và thời gian hiệu lực.
4. Xây luồng thay đổi tin cậy (outbox/CDC hoặc cơ chế tương đương), consumer idempotent và xử lý version.
5. Bootstrap Search bằng snapshot có **log position/watermark** bảo đảm không bỏ sót thay đổi trong lúc dựng.
6. Đối soát **missing 500**, cùng version khác giá, bản ghi mồ côi, dữ liệu ngoài phạm vi.
7. Quarantine các hàng không thể map hoặc cùng version có payload conflict; **không chọn đại một bên**.
8. Chạy canary/cutover theo SLO, quan sát lag, outbox, lỗi và dữ liệu Search.
9. Bỏ batch cũ hoặc sửa vai trò của nó thành reconciliation/repair có quản trị.
10. Duy trì quy trình owner, replay, xóa/tombstone và quyền dữ liệu.

Không bắt đầu bằng việc UPDATE 300 hàng lệch cho bằng một bảng bất kỳ khi **các đường ghi cạnh tranh vẫn đang hoạt động**, vì độ lệch có thể tái xuất hiện ngay sau đó.

## 17. Tổng kết

| Chủ đề | Nguyên tắc cần nhớ |
| --- | --- |
| **Dư thừa dữ liệu** | Có thể hợp lệ nếu có ý nghĩa và mục đích rõ |
| **Anti-pattern cốt lõi** | Nhiều bản sao của cùng dữ kiện hiện hành nhưng không rõ nguồn chuẩn/quy tắc đồng bộ |
| **Source of truth** | Xác định theo trường, ngữ cảnh, ID, tenant và thời điểm |
| **Snapshot** | Giữ giá/tên đã chốt, không tự hội tụ về hiện tại |
| **Projection/cache** | Bản đọc của nguồn có thẩm quyền, cần freshness contract |
| **Denormalization** | Đánh đổi có chủ đích; phải kiểm soát update anomaly |
| **Full-state event** | Có thể hội tụ bằng version mới nhất nếu payload đủ |
| **Delta event** | Cần xử lý thứ tự, gap và lặp tác dụng |
| **Source version** | Thứ tự có thẩm quyền theo từng đối tượng; không là timestamp nhận |
| **Outbox** | State + ý định phát event commit cùng transaction nguồn |
| **Inbox/idempotency** | Không áp dụng lặp event ở consumer |
| **Version conflict** | Cùng version nhưng giá trị khác cần điều tra, không tự ghi đè |
| **Reconciliation** | Phân biệt missing, lagging, divergent, deleted và snapshot khác nghĩa |
| **Tombstone** | Ghi nhớ gỡ/xóa để replay cũ không làm sống lại dữ liệu |
| **CDC/batch** | Cần hợp đồng ngữ nghĩa, watermark, bootstrap và xử lý delete |
| **Multiple writers** | Chỉ hợp lý khi có field ownership/merge và xử lý conflict |
| **Freshness SLO** | Độ trễ phải được định nghĩa, đo và gắn fallback |
| **Data lineage** | Truy được nguồn, version, event, thời điểm và transform |
| **Repair** | Sửa từ nguồn có thẩm quyền hoặc theo quy trình hợp nhất được kiểm chứng |

**Kết luận:** Vấn đề không nằm ở việc cùng một giá trị xuất hiện trong nhiều bảng hoặc nhiều hệ thống; vấn đề là **một dữ kiện hiện hành bị sao chép mà không có ai chịu trách nhiệm xác định giá trị đúng và không có quy tắc để các bản sao hội tụ**. Hãy phân biệt rõ **snapshot lịch sử** với **projection cần làm mới**, xác định **nguồn chuẩn theo trường và thời điểm**, chốt **business key, version, event, idempotency, độ trễ, xóa và đối soát**, rồi mới chọn cơ chế đồng bộ phù hợp. Một thiết kế tốt không chỉ trả lời “dữ liệu ở đâu?” mà còn trả lời **“ai được sửa, bản sao khi nào đúng, lệch thì phát hiện và phục hồi thế nào?”**.
