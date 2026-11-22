# API Composition và tổng hợp kết quả khi đang xử lý yêu cầu

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Truy vấn liên dịch vụ  
> **Trọng tâm:** Thiết kế một API trả dữ liệu tổng hợp từ nhiều service tại thời điểm nhận request, bảo toàn quyền sở hữu dữ liệu, quản lý độ trễ, lỗi từng phần và ngữ nghĩa nhất quán.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích **API Composition** là mẫu truy vấn liên dịch vụ dạng fan-out/fan-in: nhận một request, lấy dữ liệu từ nhiều service có quyền sở hữu riêng, ghép thành một response dành cho consumer.
- Phân biệt composition theo yêu cầu với truy vấn cơ sở dữ liệu chung, **CQRS/materialized read model**, Backend for Frontend (BFF), GraphQL federation và quy trình điều phối lệnh nghiệp vụ.
- Xác định dữ liệu nào thuộc domain nào; không để tầng tổng hợp trở thành một service tự ý ghi hoặc đọc trực tiếp database của các service khác.
- Thiết kế chuỗi gọi song song hay tuần tự dựa trên **phụ thuộc dữ liệu**, **latency budget**, **fan-out**, **timeout**, giới hạn đồng thời và tài nguyên.
- Định nghĩa khi nào lỗi của một service làm cả request thất bại; khi nào có thể dùng partial response, cache hoặc stale data mà không làm sai nghiệp vụ.
- Xử lý khác biệt giữa **ảnh chụp trạng thái của nhiều service tại nhiều thời điểm**, phiên bản dữ liệu, loại tiền, danh tính, tenant và trường hợp không có kết quả.
- Triển khai ví dụ Java/Spring Boot với WebClient theo hướng không chặn event loop, có timeout theo dependency, fallback có ngữ nghĩa và bảo vệ dữ liệu.
- Lập kế hoạch kiểm thử contract, fault injection, performance, authorization và khả năng quan sát để chọn giữa API Composition và read model được cập nhật bất đồng bộ.

## 2. Tình huống mở đầu: màn hình chi tiết sản phẩm

Một ứng dụng thương mại điện tử hiển thị màn hình chi tiết sản phẩm. Client cần nhiều thông tin:

- Tên, mô tả, hình ảnh: do **Catalog Service** sở hữu.
- Giá áp dụng theo khách, vùng và chương trình: do **Pricing Service** sở hữu.
- Có thể bán/giao ngay hay không: do **Inventory Service** sở hữu.
- Điểm đánh giá và số lượng đánh giá: do **Review Service** sở hữu.
- Ưu đãi cho khách: do **Promotion/Eligibility Service** sở hữu.

Cách đầu tiên là client gọi năm API:

~~~text
Mobile / Browser
     |---- GET /catalog/products/p-101 ----> Catalog
     |---- GET /prices?sku=p-101 ----------> Pricing
     |---- GET /inventory?sku=p-101 -------> Inventory
     |---- GET /reviews/summary?p=p-101 ---> Review
     +---- GET /promotions/eligible --------> Promotion
~~~

Nhược điểm: client phải hiểu topology logic, phối hợp nhiều contract, quản lý năm timeout, xử lý các trạng thái lỗi khác nhau và có thể thực hiện quá nhiều lần round-trip ở môi trường mạng di động.

Một hướng là cho client gọi **một API composition**:

~~~text
Client
  |
  | GET /v1/product-details/p-101
  v
+-------------------------------+
| Product Detail Composer/BFF   |
| - authenticate/context        |
| - fan out                     |
| - normalize representations   |
| - build response              |
| - handle partial failures     |
+-----+-------+------+----------+
      |       |      |
      v       v      v
   Catalog  Pricing Inventory -----+
      |       |      |             |
      +-------+------+---- Review -+
                  |
                  v
         ProductDetailView
                  |
                  v
                Client
~~~

Composer gọi các API do service khác **công bố**, chứ không chạy JOIN trực tiếp qua database của chúng. Nó tạo biểu diễn dành cho giao diện, không trở thành nguồn sự thật của giá, tồn kho hoặc đánh giá.

Ví dụ response:

~~~json
{
  "productId": "p-101",
  "name": "Bàn phím cơ",
  "price": {
    "amountMinorUnits": "1290000",
    "currency": "VND"
  },
  "availability": {
    "state": "IN_STOCK",
    "observedAt": "2026-11-11T09:00:03Z"
  },
  "rating": {
    "average": 4.6,
    "count": 218
  },
  "sections": {
    "catalog": "AVAILABLE",
    "pricing": "AVAILABLE",
    "inventory": "AVAILABLE",
    "reviews": "AVAILABLE"
  }
}
~~~

Đây là ví dụ minh họa contract. Giá có thể phụ thuộc identity, tenant và thời điểm; inventory “đang có hàng” chỉ là một snapshot, **không tự bảo đảm giữ hàng khi checkout**.

## 3. Định nghĩa và phạm vi API Composition

**API Composition** là mẫu triển khai truy vấn mà một thành phần phía trước gọi một hay nhiều service sở hữu dữ liệu, kết hợp response và trả về một view phù hợp với caller **ngay khi request đang được xử lý**.

Những bước logic:

1. Nhận request và xác định caller, tenant, quyền và tham số.
2. Quyết định dữ liệu cần lấy, chia thành các upstream calls.
3. Gọi các service phụ thuộc, song song khi độc lập, tuần tự khi có đầu ra làm đầu vào.
4. Diễn giải kết quả theo contract, xác thực quyền và ràng buộc.
5. Ghép/biến đổi dữ liệu phục vụ **read view**, kèm metadata khi cần.
6. Trả response trong ngân sách thời gian; xử lý timeout, dữ liệu thiếu và các lỗi phụ thuộc theo chính sách.

### 3.1. Không phải distributed SQL JOIN

Một cross-service JOIN trực tiếp thường khiến Composer biết bảng nội bộ của nhiều service, làm yếu database ownership và làm cho một migration schema có thể phá vỡ API bên ngoài.

~~~text
Không nên:
Composer -> Catalog DB
         -> Pricing DB
         -> Inventory DB
         -> Review DB

Nên:
Composer -> Catalog API
         -> Pricing API
         -> Inventory API
         -> Review API
~~~

Có ngoại lệ như dữ liệu analytics hoặc một shared database được tổ chức có chủ đích, nhưng đó **không còn là ví dụ cơ bản của API Composition qua ranh giới dịch vụ**. Muốn dùng shared read model, hãy xác định ownership và hợp đồng cập nhật rõ, thay vì để nhiều service tùy ý truy cập bảng của nhau.

### 3.2. Composition là truy vấn, không phải orchestration giao dịch

Một request **GET /product-details** có thể đọc Catalog/Pricing/Inventory. Nhưng một request **POST /checkout** cần quyết định giữ hàng, thanh toán, tạo đơn và xử lý rollback/compensation; nó là workflow nghiệp vụ có invariant và side effect.

Không nên biến Composer phục vụ giao diện thành coordinator của toàn bộ checkout chỉ vì nó đã biết gọi nhiều service. Các thao tác ghi cần owner và mô hình transaction/saga phù hợp.

### 3.3. Không phải mọi dữ liệu đều cần lấy đồng bộ

Dữ liệu ít thay đổi như rating summary, category metadata có thể lấy từ cache/read model. Giá cá nhân hóa có thể cần phản hồi mới nhất từ Pricing hoặc một giá trị đã được chốt trong nghiệp vụ. Tồn kho cũng cần phân biệt thông tin hiển thị và cam kết reservation.

API Composition hợp lý khi **lợi ích của dữ liệu theo yêu cầu lớn hơn chi phí fan-out và ràng buộc liên kết**.

## 4. So sánh với những cách tiếp cận gần nhau

| Cách tiếp cận | Tư tưởng | Phù hợp | Đánh đổi |
| --- | --- | --- | --- |
| **Client-side composition** | Client gọi nhiều service rồi ghép | UI cần linh hoạt và số call ít, mạng tốt | Nhiều round-trip; client quản lý timeout/security |
| **Server-side API Composition** | Một composer gọi upstream khi nhận request | Màn hình cần dữ liệu từ vài boundary, yêu cầu freshness cao | Tail latency, fan-out, partial failure |
| **BFF** | API adapter theo web/mobile/partner, thường có composition | Khác biệt rõ giữa các loại client | Thêm runtime và contract cần vận hành |
| **GraphQL gateway/federation** | Client chọn fields, nhiều resolver/subgraph | Nhiều màn hình cần dữ liệu linh hoạt | N+1, query complexity, security, field ownership |
| **CQRS materialized read model** | Tạo projection từ event/change trước khi query | Query phức tạp/lưu lượng cao, cần sort/filter liên domain | Eventual consistency, data pipeline, backfill |
| **API Gateway routing thuần** | Chuyển request đến một upstream theo route | Auth/traffic/routing chung | Không tự ghép nhiều dữ liệu |
| **Business orchestrator/saga** | Điều phối các lệnh có side effect và state | Đặt hàng/thanh toán/quy trình dài | Recovery, idempotency, compensation |

Composer có thể nằm trong BFF; gateway chung có thể route vào BFF. **Không nhất thiết nhồi composition vào API Gateway** nếu nó tạo các phụ thuộc nghiệp vụ/triển khai khó quản lý.

### 4.1. Vị trí triển khai

Một kiến trúc thường gặp:

~~~text
Web / Mobile
     |
     v
  API Gateway
     |
     v
Product Detail BFF / Composer
     |        |        |
     v        v        v
  Catalog   Pricing  Inventory
     |
     +--------> Review (optional)
~~~

Gateway quản lý edge policy (routing, coarse authentication, rate limiting); BFF/Composer thực hiện view mapping; domain services sở hữu dữ liệu và quyền truy cập chi tiết.

Một hệ thống nhỏ có thể gộp BFF và gateway nếu trách nhiệm được kiểm soát. Khi số composite endpoints tăng và các domain liên quan thay đổi độc lập, tách runtime hoặc module có thể giúp giữ rõ ownership.

## 5. Bắt đầu từ contract của response tổng hợp

Trước khi viết các cuộc gọi, cần xác định **response thực sự cam kết điều gì**.

Ví dụ hợp đồng đề xuất:

~~~http
GET /v1/product-details/p-101?include=reviews,availability
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~json
{
  "product": {
    "id": "p-101",
    "name": "Bàn phím cơ",
    "brand": "Example"
  },
  "price": {
    "amountMinorUnits": "1290000",
    "currency": "VND",
    "priceListVersion": "PL-42"
  },
  "availability": {
    "state": "UNKNOWN",
    "observedAt": null
  },
  "reviews": {
    "average": 4.6,
    "count": 218
  },
  "completeness": {
    "product": "COMPLETE",
    "price": "COMPLETE",
    "availability": "UNAVAILABLE",
    "reviews": "COMPLETE"
  },
  "generatedAt": "2026-11-11T09:00:04Z"
}
~~~

Điểm cần quy định:

- Trường nào **bắt buộc** để response vẫn có ý nghĩa?
- Khi một section không thể lấy, trả **null**, bỏ hẳn section hay kèm trạng thái?
- **UNKNOWN** có nghĩa là không biết, chứ không phải không có hàng.
- Giá nào được áp dụng: giá niêm yết, giá cá nhân hóa hay giá đã chốt?
- ObservedAt của từng service nói lên thời điểm dữ liệu được đo, không phải một global transaction timestamp.
- Có cho phép stale data hay không? Nếu có, trong bao lâu và cách hiển thị?
- Response có cache được không, theo user/tenant/locale/currency nào?
- Khi client cần thanh toán, đâu là API có quyền xác nhận giá/tồn kho tại thời điểm commit?

Tầng composition nên có **một API contract độc lập** được công bố rõ, không chỉ nối nguyên các JSON fragment của downstream và mong client tự xử lý.

### 5.1. Một view không nên làm lộ schema nội bộ

Nếu Catalog đổi field title thành displayName, Composer có thể giữ contract public name trong giai đoạn migration. Tuy nhiên mapper phải có owner và test, không âm thầm đổi ngữ nghĩa.

Tránh trả một object chứa quá nhiều trường nội bộ như vendorId, internalCost, secretFlag chỉ vì upstream DTO có chúng. Dùng DTO/mapper riêng và **data minimization**.

## 6. Xác định quyền sở hữu dữ liệu và phép JOIN

Bảng đầu vào cần được xác lập:

| Dữ liệu | Source of truth | Truy vấn/khóa liên kết | Ai quyết định nghiệp vụ |
| --- | --- | --- | --- |
| Product metadata | Catalog | productId/SKU | Catalog |
| Giá theo thị trường/khách | Pricing | productId + currency + customer context | Pricing |
| Tồn kho có thể bán | Inventory | SKU + fulfillment location | Inventory |
| Tổng hợp đánh giá | Review | productId | Review |
| Ưu đãi cá nhân | Promotion/Eligibility | principal + cart/product context | Promotion |
| Đơn đã đặt | Order | orderId/customerId | Order |
| Quyền xem dữ liệu | Service sở hữu, theo identity context | tenantId + resourceId | Domain owner |

### 6.1. Khóa liên kết cần có contract

ProductId của Catalog không nhất thiết đồng nhất với SKU của Inventory. Nếu là hai ID khác nhau, cần mapping được sở hữu chính thức:

~~~text
Catalog product p-101
   |-- variant v-11 → inventory sku-87
   +-- variant v-12 → inventory sku-88
~~~

Nếu Composer tự giả định p-101 = sku-101, kết quả sai có thể không gây lỗi HTTP. Có thể dùng một API mapping do Catalog sở hữu, hoặc một view được cung cấp sẵn với variant/SKU, thay vì đoán từ chuỗi ID.

### 6.2. Giá và tiền tệ không được ghép tùy tiện

Một response Catalog ở VND, Pricing ở USD và Promotion áp dụng chiết khấu theo VND không thể chỉ cộng/trừ raw number. Phải có quy tắc về loại tiền, đơn vị nhỏ nhất, rounding và thời điểm áp giá do Pricing/Order công bố.

Composer chỉ nên map **giá đã được domain service tính hợp lệ**, không tự tính lại toàn bộ quy tắc thuế/giảm giá.

### 6.3. Authorization là điều kiện của phép JOIN

Nếu một Order thuộc tenant A, Composer không được lấy thêm Customer Profile của tenant B rồi ghép vào cùng response. Đầu vào lấy từ request (orderId, customerId) **không phải bằng chứng quyền truy cập**. Mỗi service phải kiểm principal/tenant/resource ownership phù hợp; Composer không được trở thành đường bypass.

## 7. Fan-out/fan-in: song song hay tuần tự?

### 7.1. Các lời gọi độc lập nên cân nhắc song song

Với Product Detail, Catalog, Pricing và Review có thể độc lập nếu caller đã có productId hợp lệ và mỗi service hiểu cùng identifier.

~~~text
t=0ms  Composer receives request
       |--- Catalog (120ms) ----|
       |--- Pricing (180ms) ----------|
       |--- Review (90ms) ---|
       |--- Inventory (140ms) ------|
                                  |
                             Compose + respond
~~~

Nếu gọi **tuần tự** 120 + 180 + 90 + 140 = 530 ms chỉ cho thời gian upstream. Nếu gọi song song và không có phụ thuộc, phần chờ upstream lý tưởng gần **max(120, 180, 90, 140) = 180 ms** cộng overhead, queueing, network và mapping. Đây là số minh họa, không phải metric thực tế.

Nhưng gọi song song nhiều phụ thuộc sẽ tạo **nhiều request downstream đồng thời** và tăng xác suất ít nhất một thành phần chậm.

### 7.2. Phụ thuộc dữ liệu buộc một phần tuần tự

Ví dụ Inventory cần variantSku được lấy từ Catalog:

~~~text
Request
  |
  v
Catalog.lookupProduct(productId)
  |
  +----> inventory.getAvailability(variantSku)
  +----> pricing.getPrice(variantSku, principal)
          |
          +---- parallel after catalog -------------------+
                                                           |
                                                    Compose response
~~~

Không thể gọi Inventory đúng khi chưa biết variantSku, trừ khi có key được contract đảm bảo từ client hoặc store dùng chung. Cố gọi song song bằng ID đoán được là lỗi business mapping.

### 7.3. Critical path

Với các dependency:

- Catalog cần 100 ms.
- Sau Catalog, Pricing cần 150 ms và Inventory cần 220 ms.
- Review chạy song song từ đầu mất 180 ms.

Critical path theo cấu trúc giả định xấp xỉ **100 + max(150, 220) = 320 ms**, chưa tính overhead. Độ trễ không đơn giản là tổng tất cả calls, cũng không đơn giản là max khi có nhánh tuần tự.

**Thiết kế tốt:** vẽ DAG phụ thuộc của request, đánh dấu các calls bắt buộc, chi phí, timeout và điểm có thể chuyển sang cache/read model.

## 8. Tail latency và xác suất lỗi của fan-out

Giả sử mỗi upstream riêng lẻ có độ tin cậy 99,9% trong một cửa sổ đo và giả sử **độc lập** chỉ để minh họa. Nếu composer cần cả 5 upstream thành công, xác suất thành công đồng thời lý tưởng là:

~~~text
0.999 ^ 5 ≈ 0.9950 = 99.50%
~~~

Con số này thấp hơn 99,9% của từng upstream. Trong thực tế, lỗi thường **tương quan** (chung DB, network, identity provider, overload), nên không được suy SLO bằng một phép nhân đơn giản cho production.

### 8.1. Một lời gọi chậm có thể kéo dài toàn response

Với fan-out bắt buộc, thời gian phản hồi thường phụ thuộc vào **nhánh chậm nhất** trong critical path. Ngay cả nếu median mỗi service tốt, P99 của request tổng hợp có thể xấu hơn nhiều.

Các yếu tố tạo tail latency:

- Queueing ở HTTP connection pool.
- Thread pool/event loop bị nghẽn.
- Database lock hoặc query tốn chi phí.
- Garbage collection và CPU saturation.
- Retry thêm các lượt gọi.
- Dependency không có timeout hoặc timeout quá lớn.
- N+1 query do gọi từng item riêng.
- Shared resource contention khi nhiều composite requests chạy cùng lúc.

### 8.2. Fan-out amplification

Một request client có thể tạo 5 calls. Với 1.000 request/giây, service tổng hợp có thể sinh khoảng 5.000 calls/giây ở backend trong mô hình đơn giản, chưa tính retry và cache.

Nếu mỗi dependency được gọi cho từng item trong danh sách, tải có thể tăng mạnh hơn. Ví dụ trả 20 products, mỗi product gọi Price và Inventory riêng, sẽ có khoảng **40 upstream calls** cộng catalog call. Khi client gửi nhiều request song song, saturation xảy ra nhanh.

Cần thiết kế batching, aggregation endpoint, giới hạn pageSize/fan-out, concurrency budget và cache thích hợp.

## 9. Ngân sách thời gian end-to-end

Không nên cài mỗi downstream timeout 5 giây rồi để client deadline 2 giây. Những call còn chờ sau khi client đã từ bỏ chỉ tiêu tốn tài nguyên.

Một ví dụ ngân sách minh họa:

~~~text
Client deadline: 800ms
  |
  | Gateway auth/routing: ~40ms budget
  |
  | Composer decode/serialize: ~40ms
  |
  | Upstream critical-path budget: ~600ms
  |
  | Safety margin, network, queueing: phần còn lại
~~~

Các giá trị chỉ để minh họa; deadline thật phải dựa trên SLO và phép đo. Cần phân biệt **connect timeout**, **response/read timeout**, **overall request timeout** và **idle timeout** cho stream.

### 9.1. Thời hạn còn lại cần được truyền hoặc tính

Nếu request đến Composer khi chỉ còn 250 ms theo deadline của client, không nên gọi Pricing với timeout mới 2 giây. Có thể dùng deadline context tương thích trên các hop hoặc tính thời gian còn lại theo chính sách.

Duy trì cùng một ngân sách giúp tránh request orphan sau khi caller đã timeout, nhất là khi một service khác lại gọi tiếp dependency tầng sau.

### 9.2. Timeout không đồng nghĩa nguồn dữ liệu không tồn tại

Nếu Inventory timeout, trạng thái đúng có thể là UNKNOWN hoặc TEMPORARILY_UNAVAILABLE. Không tự đổi thành OUT_OF_STOCK; việc này có thể làm giảm doanh số và sai báo cáo.

Nếu Pricing timeout, không tự trả giá 0 hoặc giá cũ chưa được phép chỉ để giữ HTTP 200. Mỗi loại dữ liệu phải có fallback được **business owner** cho phép.

## 10. Required và optional dependencies: quyết định chính sách lỗi từng phần

Một composer cần phân biệt:

- **Required:** nếu không có dữ liệu này thì response không an toàn/không còn ý nghĩa theo contract.
- **Optional:** nếu thiếu, vẫn có thể trả một view hợp lệ với biểu diễn thiếu rõ.
- **Conditional:** bắt buộc trong một ngữ cảnh nhưng không bắt buộc ở ngữ cảnh khác, ví dụ địa chỉ giao hàng khi client chỉ xem sản phẩm.

Ví dụ Product Detail:

| Dependency | Chính sách giả định | Khi lỗi | Vì sao |
| --- | --- | --- | --- |
| Catalog | Required | Trả lỗi upstream hoặc not found theo nguyên nhân | Không có danh tính sản phẩm để trình bày |
| Pricing | Required nếu đang đưa nút mua với giá | Không trả giá không xác minh; có thể báo 503 | Không được hiển thị/chốt giá sai |
| Inventory | Optional để xem, required để cam kết mua nếu policy yêu cầu | UNKNOWN/disable buy hoặc trả lỗi khi checkout | Snapshot tồn kho không phải reservation |
| Review | Optional | Ẩn rating hoặc đánh dấu unavailable | Không thay invariant giao dịch |
| Recommendation | Optional | Không hiện đề xuất | UX suy giảm nhưng phần chính vẫn có nghĩa |

Chính sách này là **ví dụ để suy luận**, không áp đặt cho mọi doanh nghiệp. Có sản phẩm cho phép đặt trước hàng hết; có sản phẩm bắt buộc kiểm tồn trước khi hiển thị giá. Chọn required/optional dựa trên consumer contract và invariants.

### 10.1. Partial response phải tường minh

Một response HTTP 200 có thể chứa các section unavailable nếu contract công bố việc thiếu dữ liệu như một kết quả hợp lệ:

~~~json
{
  "product": {
    "id": "p-101",
    "name": "Bàn phím cơ"
  },
  "price": {
    "amountMinorUnits": "1290000",
    "currency": "VND"
  },
  "availability": {
    "state": "UNKNOWN"
  },
  "reviews": null,
  "completeness": {
    "product": "COMPLETE",
    "price": "COMPLETE",
    "availability": "TIMED_OUT",
    "reviews": "UNAVAILABLE"
  }
}
~~~

Không dùng 206 Partial Content như một mã mặc định cho mọi partial business response: trong HTTP, 206 gắn với range request semantics. Một số ứng dụng cân nhắc 207 Multi-Status theo ngữ cảnh riêng, nhưng không phải tiêu chuẩn thay thế cho contract tổng hợp thông thường. **Điều quan trọng là body/status của public API được định nghĩa rõ**.

### 10.2. Không biến lỗi phân quyền thành “mất dữ liệu tùy chọn”

Nếu Review trả 403 vì caller không có quyền xem một loại dữ liệu, Composer không nên tự lấy lại bằng service credential rộng và ghép vào response. Nếu một service trả 401/403, cần phân biệt credential propagation/configuration failure với quyền không được cấp. Không nên nuốt lỗi bảo mật như một timeout bình thường.

### 10.3. Fallback và stale data phải có thông tin nguồn

Nếu dùng cache:

~~~json
{
  "rating": {
    "average": 4.6,
    "count": 218
  },
  "freshness": {
    "rating": {
      "source": "CACHE",
      "asOf": "2026-11-11T08:58:00Z",
      "stale": true
    }
  }
}
~~~

Không phải mọi API cần trả chi tiết freshness cho client, nhưng hệ thống cần có chính sách/telemetry biết dữ liệu nào stale. Với dữ liệu tiền và authorization, stale fallback phải được hạn chế hoặc cấm theo invariant.

## 11. Nhất quán dữ liệu: không có “ảnh chụp chung” tự động

Composer gọi nhiều service ở các thời điểm khác nhau:

~~~text
09:00:00.100 Catalog trả product ACTIVE
09:00:00.130 Pricing trả giá 1.290.000 VND
09:00:00.210 Inventory trả available=true
09:00:00.240 Catalog thay trạng thái DISCONTINUED
09:00:00.260 Composer trả response
~~~

Response có thể ghép các giá trị **mỗi giá trị đúng ở thời điểm nó được đọc**, nhưng chưa chắc từng tồn tại đồng thời như một snapshot toàn cục. Đó là giới hạn tự nhiên của query-time composition khi các service có transaction độc lập.

### 11.1. Các mức yêu cầu cần phân biệt

- **Best-effort current view:** dữ liệu gần thời điểm request, chấp nhận lệch nhỏ.
- **Bounded staleness:** dữ liệu không được cũ quá ngưỡng công bố.
- **Read-your-writes:** sau khi client sửa một resource, lần đọc tiếp theo phải thấy thay đổi trong phạm vi contract.
- **Monotonic reads:** caller không quan sát dữ liệu “quay ngược” theo một cách bị cấm.
- **Snapshot consistency:** tất cả dữ liệu phải tương ứng cùng logical version/time theo một mô hình phối hợp.
- **Transactional correctness:** tại thời điểm commit lệnh nghiệp vụ, invariant phải được bảo vệ bởi service owner.

Không nên gán “strongly consistent” cho một composite response chỉ vì các HTTP calls chạy song song.

### 11.2. Version và correlation dữ liệu

Khi cần liên hệ, có thể các services trả metadata như productVersion, priceListVersion, inventorySnapshotTime hoặc event sequence. Composer dùng nó để phát hiện một số cặp giá trị không tương thích hoặc hiển thị độ mới.

Nhưng chỉ có observedAt từ các đồng hồ khác nhau không tạo transaction snapshot. Muốn snapshot thực sự, cần cơ chế thiết kế đặc biệt như version barrier, shared logical timestamp, query coordinator có hỗ trợ hoặc read model phù hợp; chi phí có thể cao.

### 11.3. Checkout phải xác nhận lại invariant

Product Detail có thể hiển thị “còn hàng” lúc 09:00. Người dùng bấm mua lúc 09:02. Inventory có thể đã hết. **Order/Inventory phải kiểm tra và reserve tại thời điểm nghiệp vụ yêu cầu**, không tin nguyên kết quả composition cũ để commit.

Tương tự, Pricing/Order phải quyết định giá cuối được chốt theo contract, thay vì tin price field do client gửi lại.

## 12. N+1 calls và batching

Một trang danh sách có 30 sản phẩm. Cách naïve:

~~~text
GET /catalog/products?pageSize=30
  |
  +-- for each product:
       GET /pricing/{id}
       GET /inventory/{id}
       GET /review/{id}
~~~

Tổng có thể là **1 + 30 × 3 = 91 upstream requests** cho một trang. Dù gọi song song, hệ thống tiêu tốn kết nối, CPU, headers, auth validation và dễ đánh vào rate limit.

### 12.1. Batch endpoints

Một thiết kế thích hợp hơn:

~~~http
POST /internal/prices:batch
Content-Type: application/json

{
  "productIds": ["p-101", "p-102", "p-103"],
  "currency": "VND"
}
~~~

~~~json
{
  "items": [
    {
      "productId": "p-101",
      "amountMinorUnits": "1290000",
      "currency": "VND"
    },
    {
      "productId": "p-102",
      "amountMinorUnits": "990000",
      "currency": "VND"
    }
  ],
  "errors": [
    {
      "productId": "p-103",
      "code": "PRICE_UNAVAILABLE"
    }
  ]
}
~~~

Cú pháp POST được dùng để truyền tập khóa lớn, nhưng contract vẫn có thể là query/read-only. Phải xác định limit batch size, thứ tự trả, missing item, lỗi từng item, authorization và caching.

### 12.2. Chiến lược khác

- Chỉ lấy dữ liệu thật sự cần trên trang hiện tại.
- Cung cấp endpoint search/list đã có summary do service owner quản lý.
- Dùng DataLoader/batching nếu là GraphQL để tránh N+1 resolver.
- Caching phần ít thay đổi với key và TTL đúng.
- Materialized read model cho các màn hình có fan-out lớn, filter/sort phức tạp hoặc traffic cao.
- Truy vấn từng section khi người dùng mở một tab thay vì tải mọi thứ ngay.
- Giới hạn số productIds/client pageSize và quy tắc fan-out amplification.

Không nên tăng thread pool vô hạn để che một query plan không hiệu quả.

## 13. Giới hạn số upstream calls và tài nguyên

Một query có thể được mở rộng theo request:

~~~text
GET /v1/product-details?ids=1000-items
~~~

Nếu composer gọi một service cho mỗi item, một request user có thể tạo hàng nghìn kết nối. Do đó cần giới hạn đầu vào:

- Max item count/page size.
- Max fan-out calls trên mỗi request.
- Max nested depth hoặc query cost với GraphQL.
- Giới hạn concurrency đang gọi một downstream.
- Queue length và thời gian chờ connection pool.
- Payload size và giới hạn body của response tổng hợp.
- Per-tenant/user quota và abuse controls.
- Cancellation khi client disconnect để không tiêu tốn tài nguyên vô ích.

### 13.1. Bulkhead

Bulkhead chia tài nguyên theo dependency hoặc route để Inventory chậm không làm nghẽn mọi request Catalog. Có thể giới hạn số call đồng thời đến Review riêng, sử dụng semaphore/connection pool có mức trần và trả fallback khi bão hòa.

Nếu giới hạn quá thấp sẽ làm tăng lỗi giả; nếu quá cao sẽ làm downstream overload. Chọn mức dựa trên capacity measurement, SLO và load test.

### 13.2. Chống queue vô hạn

Nếu mỗi request xếp thêm vào một hàng chờ không giới hạn, độ trễ tăng và request sẽ hết hạn trước khi được xử lý. Thường nên có admission control/load shedding và response lỗi rõ khi vượt budget, thay vì tiếp tục nhận công việc không thể hoàn tất.

## 14. Ví dụ Spring Boot WebClient: composition song song

Ví dụ giả định ứng dụng sử dụng Spring Boot WebFlux hoặc Reactor, các service clients trả Mono và DTO có contract rõ.

### 14.1. DTO và trạng thái tổng hợp

~~~java
public record ProductDto(
    String id,
    String name,
    String defaultSku
) {}

public record PriceDto(
    String amountMinorUnits,
    String currency
) {}

public record AvailabilityDto(
    String state,
    Instant observedAt
) {}

public record ReviewSummaryDto(
    Double average,
    Integer count
) {}

public record ProductDetailView(
    ProductDto product,
    PriceDto price,
    AvailabilityDto availability,
    ReviewSummaryDto reviews,
    Map<String, String> completeness
) {}
~~~

Đây là representation minh họa; code production còn cần validation, domain mapping, handling null, error model và authorization.

### 14.2. Các client chuyên trách

~~~java
public interface CatalogClient {
    Mono<ProductDto> getProduct(String productId);
}

public interface PricingClient {
    Mono<PriceDto> getPrice(String sku, String customerId);
}

public interface InventoryClient {
    Mono<AvailabilityDto> getAvailability(String sku);
}

public interface ReviewClient {
    Mono<ReviewSummaryDto> getSummary(String productId);
}
~~~

Mỗi client nên chịu trách nhiệm URI, auth context, mapping, error classification, connection pool và telemetry cho downstream của mình. Composer không nên chứa chuỗi URL rải rác khắp nghiệp vụ.

### 14.3. Phần bắt buộc và tùy chọn

Một ví dụ:

~~~java
@Service
public class ProductDetailComposer {

    private final CatalogClient catalog;
    private final PricingClient pricing;
    private final InventoryClient inventory;
    private final ReviewClient reviews;

    public ProductDetailComposer(
            CatalogClient catalog,
            PricingClient pricing,
            InventoryClient inventory,
            ReviewClient reviews) {
        this.catalog = catalog;
        this.pricing = pricing;
        this.inventory = inventory;
        this.reviews = reviews;
    }

    public Mono<ProductDetailView> getDetail(
            String productId, String customerId) {

        // Catalog bắt buộc và trả SKU để gọi downstream.
        return catalog.getProduct(productId)
            .flatMap(product -> {

                Mono<PriceDto> price = pricing
                    .getPrice(product.defaultSku())
                    .timeout(Duration.ofMillis(250));

                Mono<AvailabilityDto> availability = inventory
                    .getAvailability(product.defaultSku())
                    .timeout(Duration.ofMillis(160))
                    .onErrorResume(ex ->
                        Mono.just(new AvailabilityDto("UNKNOWN", null)));

                Mono<ReviewSummaryDto> reviewSummary = reviews
                    .getSummary(product.id())
                    .timeout(Duration.ofMillis(120))
                    .onErrorResume(ex ->
                        Mono.just(new ReviewSummaryDto(null, null)));

                return Mono.zip(price, availability, reviewSummary)
                    .map(tuple -> {
                        Map<String, String> status = new LinkedHashMap<>();
                        status.put("catalog", "COMPLETE");
                        status.put("price", "COMPLETE");
                        status.put("availability",
                            "UNKNOWN".equals(tuple.getT2().state())
                                ? "UNAVAILABLE" : "COMPLETE");
                        status.put("reviews",
                            tuple.getT3().average() == null
                                ? "UNAVAILABLE" : "COMPLETE");

                        return new ProductDetailView(
                            product,
                            tuple.getT1(),
                            tuple.getT2(),
                            tuple.getT3(),
                            status);
                    });
            });
    }
}
~~~

**Chú ý kỹ thuật:** hàm PricingClient ở interface có hai tham số trong ví dụ; ở implementation thật, khi gọi phải truyền đủ customerId để lấy giá theo người dùng. Trong đoạn code trên cần sử dụng chính xác chữ ký phương thức đã định nghĩa; một phiên bản nhất quán là:

~~~java
Mono<PriceDto> price = pricing
    .getPrice(product.defaultSku(), customerId)
    .timeout(Duration.ofMillis(250));
~~~

Mẫu ở đây tập trung làm rõ luồng dữ liệu. Không nên lấy đoạn code mà không thống nhất DTO/call signature và security context. Đặc biệt, việc onErrorResume với mọi lỗi là quá rộng nếu bao gồm 401/403, lỗi parsing hoặc cấu hình; phần dưới đưa ra policy cụ thể hơn.

### 14.4. Phân loại lỗi trước khi fallback

Thay vì nuốt mọi exception, thiết kế một bộ phân loại:

~~~java
private Mono<AvailabilityDto> safeAvailability(String sku) {
    return inventory.getAvailability(sku)
        .timeout(Duration.ofMillis(160))
        .onErrorResume(TimeoutException.class,
            ex -> Mono.just(new AvailabilityDto("UNKNOWN", null)))
        .onErrorResume(InventoryTemporarilyUnavailable.class,
            ex -> Mono.just(new AvailabilityDto("UNKNOWN", null)));
}
~~~

Không fallback tương tự cho ForbiddenException hoặc UnauthenticatedException. Chúng cần được xử lý thành lỗi quyền/credential theo contract; nếu không, hệ thống có thể vô tình che security misconfiguration thành “không có tồn kho”.

### 14.5. Mono.zip và xử lý kết quả rỗng

Mono.zip cần các nguồn phát ra item. Nếu một Mono hoàn thành rỗng, zip có thể không phát giá trị kết hợp. Vì vậy phải phân biệt **not found** với **empty success**, và quyết định:

- Catalog not found: public 404 nếu tài nguyên không tồn tại và caller có quyền biết.
- Pricing not found: không tự giá bằng 0; trả lỗi domain thích hợp.
- Review không có đánh giá: trả count=0 theo contract.
- Review service lỗi: trả trạng thái UNAVAILABLE, khác với “chưa có review”.

Cách dùng placeholder/null/Optional cần nhất quán với DTO và serializer. Dữ liệu “không tồn tại” và “tạm không truy xuất được” không nên trộn lẫn.

### 14.6. Không gọi block() trong reactive request pipeline

Đối với Spring WebFlux, việc gọi block() trong event-loop request handler có thể gây nghẽn, giảm throughput và làm tăng tail latency. Mono/Flux cho phép ghép và xử lý tín hiệu bất đồng bộ theo cơ chế reactive.

Điều đó không có nghĩa WebFlux luôn tốt hơn Spring MVC. Một ứng dụng MVC với client có timeout/concurrency control phù hợp cũng triển khai composition được. Quan trọng là **không làm nghẽn tài nguyên** và **định nghĩa số cuộc gọi đồng thời tối đa** theo runtime đã chọn.

### 14.7. Controller đơn giản

~~~java
@RestController
@RequestMapping("/v1/product-details")
public class ProductDetailController {

    private final ProductDetailComposer composer;

    public ProductDetailController(ProductDetailComposer composer) {
        this.composer = composer;
    }

    @GetMapping("/{id}")
    public Mono<ProductDetailView> get(
            @PathVariable String id,
            Authentication authentication) {
        String customerId = authentication.getName();
        return composer.getDetail(id, customerId);
    }
}
~~~

Đây là ví dụ định hướng. Hệ thống thật phải kiểm tra null auth cho public endpoints, mapping identity sang customerId theo identity provider, yêu cầu tenant, principal rights và chỉ trả đúng data mà caller được phép xem.

## 15. Cách triển khai cùng WebClient và deadline

Một downstream client minh họa:

~~~java
@Component
public class InventoryWebClient {

    private final WebClient webClient;

    public InventoryWebClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("http://inventory-service")
            .build();
    }

    public Mono<AvailabilityDto> getAvailability(String sku) {
        return webClient.get()
            .uri(uri -> uri.path("/internal/availability/{sku}")
                .build(sku))
            .retrieve()
            .bodyToMono(AvailabilityDto.class);
    }
}
~~~

Các điểm chưa được minh họa trong đoạn code này nhưng cần có khi triển khai:

- Authentication của service-to-service call.
- Config connect/response timeout và pool ở HTTP client.
- Error mapping theo HTTP status và domain error code.
- Truyền traceparent/request ID và các thông tin context phù hợp.
- Retry có điều kiện và giới hạn.
- Micrometer/OpenTelemetry metrics/traces.
- DNS/service discovery và readiness ở môi trường thật.
- Bảo vệ header và tránh chuyển raw user token qua nơi không tin cậy.

### 15.1. Deadline tổng còn lại

Một cách tổ chức là CompositionContext mang deadline tổng được xác lập ở đầu request, và từng client tính remainingTime. Đoạn pseudo-code:

~~~text
remaining = requestDeadline - now

if remaining <= 0:
    stop and return timeout

subcallTimeout = min(configuredDependencyBudget, remaining)
call dependency with subcallTimeout
~~~

Không nên mỗi upstream tự dùng timeout lớn hơn thời gian caller còn chờ. Cancellation nên được truyền để giải phóng kết nối và tài nguyên khi downstream request không còn giá trị.

### 15.2. Không retry mutation qua Composer

Query-time composition thường thực hiện read-only operations. Không nên vô tình gắn side effect như “ghi nhận coupon”, “reserve inventory” hoặc “tạo payment” vào GET /product-details. Một GET có thể bị cache, prefetch, retry hoặc bot crawler gọi, dẫn đến tác dụng phụ ngoài ý định.

Với GET an toàn và client idempotent, retry một lỗi mạng ngắn có thể hợp lý; nhưng phải tránh retry storm và luôn tôn trọng deadline/concurrency budget.

## 16. Bảo mật: identity propagation và trust boundary

Composer là một service trung gian, nhưng nó không nên có toàn quyền đọc mọi tenant theo mặc định.

~~~text
User U
  |
  | Bearer token (scope, tenant)
  v
Gateway
  |
  v
Composer
  |
  +--> Catalog API (resource policy)
  +--> Pricing API (price visibility/tenant policy)
  +--> Order API (object ownership)
~~~

Các câu hỏi cần trả lời:

1. Composer xác thực caller bằng cách nào?
2. Nó chuyển identity vào upstream qua token relay, token exchange hay workload identity?
3. Upstream phân biệt **người dùng cuối** và **service caller** như thế nào?
4. Quyền xem giá/coupon/đơn có được kiểm ở service sở hữu không?
5. Nếu dữ liệu bị thiếu do 403, có được trả section UNAVAILABLE hay phải trả lỗi quyền?
6. Có ngăn client tự gửi X-User-Id/X-Tenant-Id giả mạo không?
7. Cache key có tách đúng tenant/user/scope/currency không?
8. Logs/traces có tránh lộ token và PII không?

### 16.1. Identity header giả mạo

Nếu Composer tin một header như X-Customer-Id do client tự gửi, caller có thể ghép dữ liệu của khách khác. Không nên coi một header tùy ý là bằng chứng identity. Gateway có thể strip và thay bằng signed/verified context qua kết nối đáng tin, hoặc upstream xác minh token theo trust policy.

### 16.2. Service credential quá rộng

Composer dùng client credentials có quyền “read all orders” có thể tạo đường vòng lộ dữ liệu nếu bất kỳ client nào được yêu cầu orderId tùy ý. Cần hoặc truyền quyền user, hoặc service domain kiểm ownership theo user/tenant được chứng minh, hoặc dùng endpoint chuyên biệt đủ hẹp.

### 16.3. Tấn công suy diễn dữ liệu qua lỗi từng phần

Một endpoint có thể rò sự tồn tại của resource nếu trả khác nhau giữa 403, 404 và section missing. Chính sách che thông tin cũng là một phần public contract. Không cho client đoán order của người khác qua một composite endpoint.

## 17. Cache và dữ liệu stale

API Composition có thể tạo gánh nặng tải cao. Caching có thể giúp, nhưng phải phân loại.

| Loại dữ liệu | Khả năng cache | Lưu ý |
| --- | --- | --- |
| Catalog public | Thường có thể dùng TTL/ETag | Thay tên/hình ảnh cần invalidation |
| Rating summary | Có thể chấp nhận chậm vài phút nếu product cho phép | Phải biết asOf/stale semantics |
| Giá niêm yết | Tùy theo version/price list | Không dùng sai currency/region |
| Giá cá nhân hóa | Rất thận trọng | Cache key phải có principal/tenant/campaign |
| Inventory availability | Có thể cache cực ngắn nếu chỉ hiển thị | Không dùng snapshot để cam kết reservation |
| Profile/Order cá nhân | Thường không dùng shared cache thiếu security key | Quyền riêng tư, compliance, access control |
| Access decision | Chỉ cache theo policy chặt | Revocation và quyền thay đổi |

### 17.1. Cache ở đâu?

- **Upstream service cache:** giữ ownership gần nguồn dữ liệu.
- **Composer cache theo section:** tái sử dụng dữ liệu ít thay đổi giữa các request.
- **Whole response cache:** chỉ an toàn nếu key bao quát mọi chiều phân biệt, consistency và authorization.
- **CDN/browser cache:** phù hợp nội dung public; dữ liệu cá nhân cần kiểm chính sách cẩn thận.

### 17.2. Cache key gồm những gì?

Một product detail view có thể phụ thuộc:

~~~text
productId
+ tenantId
+ customer segment / principal
+ locale
+ currency
+ sales channel
+ region
+ promotion context
+ contract version
~~~

Không phải mọi chiều đều cần trong tất cả endpoint, nhưng bỏ sót chiều ảnh hưởng giá/quyền là lỗi nghiêm trọng. Nếu không thể xác định cache key an toàn, có thể **không cache whole response** và chỉ cache public sections.

### 17.3. Negative caching

Nếu Catalog trả 404, cache “not found” có thể giảm tải. Nhưng nếu resource vừa được tạo, một 404 quá lâu có thể làm client không thấy sản phẩm mới. Đặc biệt không cache nhầm 403 do thiếu quyền thành global 404 cho mọi user.

### 17.4. Cache stampede

Nhiều request cùng hết hạn cache key khiến Composer gọi downstream đồng loạt. Có thể dùng single-flight, jittered TTL, stale-while-revalidate theo loại dữ liệu, prewarming hoặc rate limit. Đảm bảo stale fallback không phá business invariant.

## 18. GraphQL aggregation: khi nào nên cân nhắc?

GraphQL có thể giúp client lấy đúng những field cần dùng:

~~~graphql
query ProductScreen($id: ID!) {
  product(id: $id) {
    id
    name
    price {
      amountMinorUnits
      currency
    }
    availability {
      state
    }
    reviewSummary {
      average
      count
    }
  }
}
~~~

Các field có thể được phục vụ bởi những subgraph/service khác nhau, tùy thiết kế federation/resolver. Tư tưởng composition vẫn tồn tại nhưng fan-out nằm sau query executor.

Ưu điểm có thể là client linh hoạt và tránh nhiều endpoint tùy biến. Đánh đổi:

- N+1 resolver khi danh sách lớn.
- Query depth/complexity khiến một request tạo tải quá lớn.
- Authorization ở field/object; nguy cơ dữ liệu nhạy cảm rò qua resolver.
- Partial response/error propagation phức tạp.
- Caching khó với dữ liệu cá nhân hóa.
- Ownership schema và thay đổi field liên domain.
- Batch/loaders, concurrency và timeout cần đo.

GraphQL không tự giải quyết tail latency hoặc consistency. Nó là một hình thức **triển khai contract và query composition**, không thay thế thiết kế resilience.

## 19. Phân trang và sắp xếp khi dữ liệu đến từ nhiều service

Giả sử cần màn hình “Đơn hàng của tôi” kèm trạng thái thanh toán và vận chuyển. Lấy 20 Order và gọi Payment/Fulfillment theo batch là một composition phổ biến.

Nhưng nếu muốn lọc/sắp xếp theo trường của nhiều service, ví dụ:

> Cho 20 đơn gần nhất đã thanh toán và giao chậm, sắp theo mức độ ưu tiên hậu mãi.

Chỉ lấy 20 Order đầu rồi ghép Payment/Fulfillment và lọc có thể **không trả 20 kết quả đúng toàn cục**. Lý do là các order không nằm trong trang đầu có thể thỏa bộ lọc liên domain.

### 19.1. Các lựa chọn

1. **Một service sở hữu query** và có projection của các trường cần filter/sort.
2. **Materialized read model/CQRS** cập nhật từ event cho truy vấn liên domain phức tạp.
3. **Query federation có khả năng push down** điều kiện với contract rõ, nếu hệ thống hỗ trợ.
4. **Over-fetch có giới hạn** cho trường hợp nhỏ, chấp nhận approximate result theo contract; không dùng khi cần trang chính xác.
5. **Tách UX**: phân trang theo Order, hiển thị status của từng order mà không khẳng định kết quả đã được lọc toàn cục.

### 19.2. Cursor và snapshot

Cursor lấy từ Order không đồng nghĩa là cursor hợp lệ cho Payment/Fulfillment. Nếu tổng hợp nhiều nguồn có thay đổi liên tục, cần thiết kế semantics pagination, duplicate/skip handling và thời điểm quan sát. Đừng tự kết luận kết quả đầy đủ nếu thực tế chỉ ghép subset.

## 20. Khi nào API Composition là lựa chọn phù hợp?

Một tập điều kiện thuận lợi:

- Số dependency nhỏ, có thể kiểm soát.
- Queries chủ yếu cần ghép theo khóa rõ (productId/orderId).
- Dữ liệu cần tương đối mới và có thể chấp nhận không phải global snapshot.
- Client cần một view riêng, giảm round trips rõ ràng.
- Upstream có batch APIs/latency phù hợp.
- Có thể định nghĩa optional/required và fallback an toàn.
- Load/traffic và chi phí fan-out vẫn nằm trong ngân sách.
- Mỗi service giữ data ownership và authorization.
- Tính đúng nghiệp vụ không phụ thuộc vào việc Composer quyết định side effect.

### 20.1. Khi nào nên chuyển sang read model?

Tín hiệu:

- Một request thường phải gọi quá nhiều service hoặc từng item.
- High traffic làm backend chịu request amplification lớn.
- Query yêu cầu filter, sort, search, paginate dựa trên trường của nhiều domain.
- Dữ liệu dùng cho báo cáo có yêu cầu truy vấn phức tạp và aggregate lớn.
- Latency mục tiêu quá thấp so với critical path các service.
- Shared partial failures khiến SLA sản phẩm thấp.
- Dữ liệu có thể chấp nhận eventual consistency với asOf/lag minh bạch.

Read model cũng có chi phí: event reliability, deduplication, ordering, backfill, replay, consistency lag và ownership. Chuyển sang CQRS không phải “miễn phí latency”.

### 20.2. Hybrid

Một thiết kế có thể dùng:

~~~text
Client
  |
  v
Composer/BFF
  |---- Catalog summary read model
  |---- Fresh Price API
  |---- Inventory availability API
  +---- Cached Review summary
~~~

Tầng composition vẫn tồn tại, nhưng chỉ gọi đồng bộ những dependency cần dữ liệu mới nhất; phần còn lại được phục vụ bởi projection/cache theo chính sách.

## 21. Quan sát, đo lường và SLO

Cần đo cả public API và từng downstream call:

| Nhóm | Chỉ số nên có | Công dụng |
| --- | --- | --- |
| Public response | RPS, error rate, P50/P95/P99 | Xem trải nghiệm người dùng cuối |
| Dependency latency | P50/P95/P99 từng service/route | Tìm critical path và tail latency |
| Fan-out | Calls per incoming request, max fan-out | Phát hiện request amplification |
| Timeout | Timeout count theo dependency | Tìm budget không phù hợp |
| Partial response | Tỷ lệ thiếu section, fallback use | Phân biệt HTTP 200 với dữ liệu chưa hoàn chỉnh |
| Retry | Retry attempts, amplification, budget exhaustion | Phát hiện retry storm |
| Capacity | In-flight requests, pool saturation, queue length | Ngăn overload |
| Cache | Hit/miss/stale, TTL, key cardinality | Đánh giá hiệu quả và rủi ro |
| Data freshness | As-of lag, version mismatch | Biết độ trễ dữ liệu |
| Business correctness | Giá sai, lộ dữ liệu, checkout invalid | Không để API nhanh nhưng sai |
| Deploy | Version, canary, contract incompatibility | Gắn lỗi với rollout |

### 21.1. Distributed tracing

Mỗi request có một trace, ví dụ:

~~~text
Trace: GET /product-details/p-101
  |
  +-- Span: authenticate/authorize
  +-- Span: Catalog.GET /products/p-101
  +-- Span: Pricing.GET /prices/p-101
  +-- Span: Inventory.GET /availability
  +-- Span: Review.GET /summary
  +-- Span: compose/serialize
~~~

Trace giúp phân biệt thời gian chờ upstream, mapping và queueing. Nếu các spans chạy song song, không cộng thời lượng tất cả span để kết luận wall-clock latency.

### 21.2. Log an toàn

Log có thể chứa requestId, traceId, route, dependency, outcome, budget và elapsedTime. Không log raw Authorization, session cookie, địa chỉ giao hàng hay thông tin thanh toán nhạy cảm. Tùy hệ thống có thể dùng operationId được mã hóa/ẩn danh thay vì PII.

### 21.3. Tỷ lệ HTTP 200 không đủ

Một Composer có thể trả 200 dù Review liên tục unavailable. Nếu dashboard chỉ đếm 5xx, người vận hành tưởng hệ thống khỏe trong khi UX xuống cấp. Vì vậy cần metrics riêng cho **completeness**, partial rate và business-impact.

## 22. Kiểm thử API Composition

### 22.1. Contract tests

- Catalog v1/v2 còn trả đủ productId/sku cần thiết.
- Pricing trả đúng amount unit/currency, kể cả khi phiên bản thay đổi field.
- Inventory có thể trả UNKNOWN và Composer không tự coi là IN_STOCK.
- Review phân biệt 0 đánh giá với service unavailable.
- Public API giữ shape, nullable semantics và error codes đã cam kết.
- Mỗi service áp dụng quyền đúng cho caller/tenant.

### 22.2. Đường thành công

~~~text
Given:
  Catalog, Pricing, Inventory, Review đều khỏe.
  Product p-101 tồn tại; caller có quyền xem.

When:
  GET /v1/product-details/p-101

Then:
  Public response có product/price/availability/review đúng contract.
  Không có cross-service DB query trái ownership.
  Trace cho thấy fan-out và kết quả từng upstream.
~~~

### 22.3. Optional dependency lỗi

~~~text
Given:
  Review Service timeout.
  Catalog và Pricing khỏe.

When:
  Client gọi Product Detail.

Then:
  Nếu contract cho phép, response vẫn thành công.
  Rating được đánh dấu UNAVAILABLE, không gán 0 sao.
  Có metric partial_result và trace/span timeout.
  Tổng response không vượt deadline cam kết.
~~~

### 22.4. Required dependency lỗi

~~~text
Given:
  Pricing unavailable.
  Nghiệp vụ không cho hiển thị giá không xác minh.

When:
  Client gọi Product Detail.

Then:
  Composer trả lỗi thích hợp (ví dụ 503 theo API contract).
  Không dùng giá 0 và không trả mức giá stale chưa được phép.
  Trace cho biết Pricing là dependency gây thất bại.
~~~

### 22.5. Security/tenant isolation

- User tenant A gọi product/order của tenant B.
- Client tự gửi X-User-Id/X-Tenant-Id.
- Service credential của Composer có quyền rộng hơn end user.
- Cache được warm bởi user A, request tiếp theo của user B cùng productId.
- Dữ liệu có scope thay đổi trong khi request tổng hợp đang chạy.

Kỳ vọng: không rò thông tin; các domain services kiểm quyền phù hợp; cache phân biệt tenant và quyền theo contract.

### 22.6. Performance và fault injection

- 1, 10, 100, 1.000 concurrent client requests (mức theo capacity thực tế).
- Một upstream tăng P99 latency gấp nhiều lần.
- Review trả 429; Inventory trả 503; Pricing chậm.
- Connection pool bão hòa.
- Client hủy request khi upstream vẫn đang xử lý.
- Một HTTP call có DNS/connect timeout.
- Một endpoint pagination yêu cầu 1.000 items bất thường.
- Burst retry từ client SDK và từ upstream.

Cần kiểm tra kết quả cả **độ trễ**, **tải xuống downstream**, **tỷ lệ partial** và **mức độ đúng nghiệp vụ**, không chỉ số request hoàn thành.

### 22.7. Mixed-version

Composer mới gọi Catalog cũ và Pricing mới, hoặc ngược lại trong rolling deploy. Contract phải tương thích schema, enum, currency, optional field, error code và identity propagation. Nếu không, canary có thể tạo lỗi chỉ cho một phần request.

## 23. Các phản mẫu thường gặp

**“Cứ lấy tất cả service rồi merge JSON là được.”**  
Sai. Cần xác định owner, join keys, quyền, kiểu dữ liệu, ngữ nghĩa, freshness và required/optional policy.

**“Gọi song song thì API luôn nhanh hơn.”**  
Không luôn. Song song giúp giảm thời gian chờ trong một request khi các call độc lập, nhưng tạo tải đồng thời và có thể làm P99 xấu khi dependency bão hòa.

**“Nếu có 10 service thì 10 call là bình thường.”**  
Có thể là dấu hiệu quá fan-out. Một số UI thực sự cần nhiều dữ liệu, nhưng phải phân tích batch, cache, aggregation owner hoặc read model.

**“Partial response chỉ cần trả HTTP 200.”**  
Không đủ. Consumer phải biết phần nào thiếu, có được dùng cho quyết định nghiệp vụ không và lỗi được quan sát ở đâu.

**“Inventory timeout nghĩa là hết hàng.”**  
Sai. Không truy xuất được số liệu khác với thực sự không còn hàng. Unknown phải được bảo toàn.

**“Giá cũ luôn tốt hơn không có giá.”**  
Không an toàn. Giá stale có thể vi phạm pricing/consumer protection rules hoặc gây giao dịch sai; fallback cần owner cho phép.

**“Composer có thể truy vấn trực tiếp tất cả database để giảm latency.”**  
Làm yếu autonomy và data ownership; thay đổi DB schema nội bộ sẽ làm Composer vỡ. Nếu cần read model, thiết kế và quản lý nó như một boundary rõ ràng.

**“GET luôn nhất quán vì chỉ đọc.”**  
Không. Read từ nhiều service không có global snapshot tự động.

**“Một 404 từ mọi upstream đều có cùng nghĩa.”**  
Không. Catalog không có product khác Review chưa có rating hoặc Pricing chưa có giá. Phải phân biệt absence vs error.

**“Có timeout ở từng client là đủ.”**  
Chưa đủ. Cần end-to-end deadline, hủy công việc và kiểm retry budgets.

**“BFF có thể tin mọi client ID truyền đến.”**  
Sai. Identity/tenant phải xác minh và authorization theo tài nguyên phải được thực hiện tại nơi sở hữu dữ liệu.

**“GraphQL tự động giải quyết N+1 và rate limiting.”**  
Không. Resolvers có thể tạo fan-out rất lớn; phải có batching, query complexity, concurrency và security.

**“CQRS read model luôn tốt hơn composition.”**  
Không. Nó thêm pipeline event, lag, backfill, consistency và chi phí vận hành. Chọn theo nhu cầu truy vấn và SLO.

## 24. Bài tập thực hành

### Bài 1 — Thiết kế response Product Detail

Cho Catalog, Pricing, Inventory, Review. Catalog và Pricing bắt buộc; Review tùy chọn; Inventory chỉ được phép trả UNKNOWN khi không truy xuất.

**Yêu cầu:** vẽ sơ đồ các calls, thiết kế JSON response cho đủ dữ liệu và khi Review timeout. Chỉ ra ai được quyền quyết định giá cuối của Order.

**Gợi ý:** Composer trả một view; Pricing/Order sở hữu quy tắc giá chốt, Inventory sở hữu reservation. Không dùng giá zero hoặc đánh giá zero khi dependency unavailable.

### Bài 2 — Tính critical path

Catalog mất 120 ms. Pricing và Inventory chỉ được gọi sau Catalog; chúng lần lượt mất 200 ms và 150 ms. Review độc lập mất 180 ms. Giả định mọi call chạy ngay khi đủ dữ liệu, không có queue/overhead.

**Yêu cầu:** so sánh thời gian gọi tuần tự với DAG có song song. Phân biệt wall-clock và tổng duration của spans.

**Gợi ý:** tuần tự là tổng bốn thời lượng; song song có critical path qua Catalog + Pricing, so với Review độc lập.

### Bài 3 — N+1 trong danh sách sản phẩm

Trang kết quả trả 40 sản phẩm. Sau danh sách, Composer gọi Price và Inventory một lần cho mỗi product.

**Yêu cầu:** tính số upstream calls, thiết kế batch API, giới hạn page size và xử lý lỗi trên từng item.

**Gợi ý:** có 1 catalog call và tối đa 80 item calls, chưa tính retry; batch theo tập keys sẽ giảm round trips.

### Bài 4 — Định nghĩa partial failure

Giả sử Pricing timeout; Review vẫn trả 4,7 sao; Inventory trả có hàng.

**Yêu cầu:** có được trả HTTP 200 kèm giá null không? Trong trường hợp nào có thể? Ai quyết định? Dữ liệu nào không nên cache?

**Gợi ý:** phải dựa contract và UI use case. Nếu nút mua yêu cầu giá đáng tin, Pricing là required và lỗi phải được hiển thị thay vì kết luận giá bằng 0.

### Bài 5 — Tính đúng của cross-service filter/sort

Màn hình muốn 20 đơn mới nhất được thanh toán nhưng giao chậm. Composer lấy 20 đơn mới nhất từ Order, rồi lọc theo Payment và Fulfillment.

**Yêu cầu:** chứng minh cách này có thể thiếu bản ghi hợp lệ; đề xuất read model hoặc query owner phù hợp.

### Bài 6 — Security review

Composer nhận orderId và customerId từ query string, rồi gọi Order với service credential read-all. Cache whole response chỉ theo orderId.

**Yêu cầu:** liệt kê ít nhất bốn rủi ro, đề xuất cách truyền identity, kiểm ownership và cache key an toàn.

### Bài 7 — Mô phỏng lỗi và độ trễ

Inventory Service có P99 tăng từ 100 ms lên 2 giây. Composer có 500 ms deadline; 30% requests thiếu section Review và Inventory.

**Yêu cầu:** quyết định optional/required, timeout cho từng service, ngưỡng bulkhead, hình thức phản hồi và metrics cần theo dõi.

**Gợi ý:** không chỉ đo HTTP 5xx; đo partial/completeness ratio và business impact.

### Bài 8 — Chọn composition hay read model

Ba lựa chọn:

1. Product Detail lấy bốn sections theo productId, 50 RPS.
2. Dashboard hàng triệu đơn filter/sort theo field của bốn domain, 3.000 RPS.
3. Màn hình tracking đơn kết hợp Order với Shipping Status, chấp nhận trễ 30 giây.

**Yêu cầu:** chọn composition/read model/hybrid cho từng trường hợp, nêu yêu cầu freshness và chi phí vận hành.

### Bài 9 — Viết contract tests

Viết test cho Catalog 404, Pricing 401, Inventory UNKNOWN, Review không có đánh giá, Review timeout và một client khác tenant.

**Gợi ý:** phân biệt từng trạng thái và định nghĩa public status/error body tương ứng.

## 25. Checklist thiết kế trước khi triển khai

- [ ] Mỗi field của composite response có owner và API contract nguồn rõ.
- [ ] Không JOIN trực tiếp database nội bộ của các service khác nếu chưa có thiết kế quyền sở hữu riêng.
- [ ] Join keys/ID mapping được định nghĩa; không tự đoán productId = SKU.
- [ ] Quy tắc currency, rounding, timezone, units và nullable semantics được công bố.
- [ ] Required/optional/conditional dependencies được xác nhận theo nghiệp vụ.
- [ ] Thời hạn end-to-end và từng dependency có ngân sách hợp lý.
- [ ] Các call độc lập chạy song song khi có lợi; call phụ thuộc được sắp thành DAG.
- [ ] Giới hạn fan-out, concurrency, page size, connection pool và queue.
- [ ] Có batch calls hoặc phương án khác cho danh sách để tránh N+1.
- [ ] Timeout/503 khác với not-found; unknown khác với zero hoặc out-of-stock.
- [ ] Partial response có contract cho completeness/freshness/fallback.
- [ ] Data stale/cache được phép theo từng field và không phá invariant.
- [ ] Giao dịch thực tế xác minh lại giá/tồn kho khi commit nếu cần.
- [ ] Composer không tự giữ business workflow side effects của các service khác.
- [ ] Identity/tenant/rights không lấy từ header/ID tự khai thiếu xác thực.
- [ ] Upstream owner thực hiện object-level authorization theo mô hình tin cậy.
- [ ] Cache key không làm rò thông tin giữa người dùng/tenant.
- [ ] Contract test có mixed-version và unknown/partial/error cases.
- [ ] SLO/metrics có latency, fan-out, dependency errors và partial-result ratio.
- [ ] Tracing theo spans cho từng upstream, tránh log token/PII.
- [ ] Có phương án giảm tải, degradation và rollback rõ.
- [ ] Nếu filter/sort liên domain phức tạp, đã đánh giá materialized read model/CQRS.

## 26. Mẫu ghi lại quyết định kiến trúc

~~~markdown
# ADR: Product Detail Composition

## Bối cảnh
- Client/use case:
- Fields/sections cần hiển thị:
- Upstream service owners:
- SLO latency/availability:
- Freshness requirement:
- Expected RPS and fan-out:

## Lựa chọn
- Đặt Composer ở BFF/module/service nào?
- Các dependency required và optional:
- DAG các cuộc gọi:
- Tổng deadline và ngân sách từng call:
- Batch, caching, pagination:
- AuthN/AuthZ và identity propagation:
- Partial response contract:
- Version/compatibility:
- Operational ownership:

## Các lựa chọn khác
- Client-side fan-out:
- GraphQL/federation:
- Read model/CQRS:
- Hybrid:
- Không tổng hợp ở giai đoạn này:

## Rủi ro và xử lý
- Tail latency:
- Availability compound:
- Shared dependency:
- N+1:
- Consistency/freshness:
- Data leakage:
- Retry amplification:
- Rollback:

## Bằng chứng xác nhận
- Contract tests:
- Fault injection:
- Load tests:
- Authorization tests:
- Dashboard/SLO:
- Tín hiệu chuyển sang read model:
~~~

Mẫu giúp thảo luận composition như một quyết định kỹ thuật có đo lường và giới hạn, thay vì chỉ lựa chọn “một endpoint trả nhiều JSON”.

## 27. Tổng kết

**API Composition** là cách xây một read view theo yêu cầu bằng cách gọi nhiều service và tổng hợp kết quả tại thời điểm request. Nó giảm sự phức tạp của client và tận dụng dữ liệu trực tiếp từ các domain owner, nhưng đánh đổi bằng fan-out, tail latency, coupling ở thời điểm chạy và khả năng thất bại từng phần.

Những nguyên tắc quan trọng nhất:

1. **Giữ rõ dữ liệu thuộc ai.** Composer chỉ tổng hợp/mapping qua API; nó không tự sở hữu giá, tồn kho, đơn hàng hay dữ liệu của dịch vụ khác.
2. **Thiết kế DAG và ngân sách độ trễ.** Gọi song song khi độc lập; bảo vệ backend bằng batching, giới hạn fan-out, concurrency và deadline.
3. **Phân biệt không có dữ liệu và không lấy được dữ liệu.** UNKNOWN/UNAVAILABLE không đồng nghĩa EMPTY, ZERO, FAILED hoặc OUT_OF_STOCK.
4. **Không giả định có snapshot chung.** Giá, tồn kho, review có thể được quan sát ở những thời điểm khác nhau. Invariant khi commit phải được service nghiệp vụ xác nhận.
5. **Không hy sinh bảo mật cho tiện tổng hợp.** Identity, tenant và quyền tài nguyên cần được kiểm ở trust boundary phù hợp; cache phải an toàn.
6. **Đo được trải nghiệm thật.** HTTP 200 có thể chứa dữ liệu thiếu; cần metrics về completeness, staleness, critical path và business correctness.
7. **Biết khi nào không nên dùng composition.** Khi query phức tạp, fan-out quá lớn hoặc SLO không thể đạt, cân nhắc read model/CQRS hoặc giải pháp hybrid.

Câu hỏi thiết kế cần tự trả lời là: **“Nếu một downstream chậm, trả dữ liệu lệch thời điểm, không có item, hoặc từ chối quyền, composite response còn đúng về ý nghĩa và an toàn cho quyết định tiếp theo của client hay không?”** Khả năng trả lời bằng contract, phép thử và metric là dấu hiệu của một API Composition được thiết kế có chủ đích.
