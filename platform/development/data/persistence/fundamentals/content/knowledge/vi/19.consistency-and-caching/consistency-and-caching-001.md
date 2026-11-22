# Phân biệt nguồn dữ liệu chuẩn với dữ liệu được lưu đệm

Một ứng dụng Java đọc thông tin sản phẩm từ Redis nhanh hơn nhiều so với truy vấn PostgreSQL. Nhưng nếu giá sản phẩm vừa được cập nhật trong database còn Redis vẫn giữ giá cũ, ứng dụng nên tin vào bên nào? Nếu số lượng tồn kho trên cache là 5 nhưng database chỉ còn 1, có được phép xác nhận bán 5 sản phẩm không?

Câu trả lời phụ thuộc vào **nguồn dữ liệu chuẩn** (*source of truth*, hoặc *system of record*) và **hợp đồng nhất quán** của từng nghiệp vụ. Cache là bản sao được duy trì để giảm độ trễ và tải; nó có thể chính xác, cũ, thiếu hoặc bị xóa. Sự tiện lợi của cache không khiến nó tự trở thành nơi có quyền quyết định trạng thái cuối cùng.

Bài học thuộc chương **Nhất quán và cache** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung kết nối tư duy về mô hình dữ liệu, transaction, chỉ mục, lỗi kết nối và ranh giới persistence của ứng dụng Java với việc tổ chức dữ liệu chuẩn, cache, bản đọc và các bảo đảm sau cập nhật.

> **Nguyên tắc:** trước khi chọn Redis, Caffeine hay annotation cache của Spring, cần trả lời: *dữ liệu nào là chuẩn, ai được ghi, cách phát hiện dữ liệu cũ, và khi các bản sao không nhất quán thì hệ thống hành xử thế nào?*

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt nguồn dữ liệu chuẩn, cache, read replica, read model và dữ liệu được tính toán từ nguồn chuẩn.
- Xác định bên chịu trách nhiệm xác thực và ghi trạng thái nghiệp vụ.
- Giải thích cache hit, cache miss, TTL, invalidation, stale read và cache stampede.
- So sánh cache-aside, read-through, write-through, write-behind/write-back và cơ chế làm mới có chủ đích.
- Nhận diện race condition khi đọc cache rồi ghi DB, hoặc commit DB rồi xóa cache.
- Thiết kế khóa cache theo tenant và đối tượng, gắn version, bảo vệ khỏi bản ghi cũ ghi đè bản mới.
- Dùng Spring/Java ở mức phù hợp, không coi **@Cacheable** hay **@CacheEvict** là transaction phân tán.
- Chọn chính sách nhất quán khác nhau cho tồn kho, thanh toán, cấu hình quyền hạn và dữ liệu chỉ hiển thị.
- Đặt metric, bài kiểm thử và cơ chế phục hồi khi cache hoặc kênh invalidation gặp lỗi.

## 2. Định nghĩa: nguồn chuẩn, cache và bản sao

**Nguồn dữ liệu chuẩn** là nơi hoặc hệ thống được nghiệp vụ thừa nhận có quyền quyết định trạng thái đúng ở một thời điểm và theo một phạm vi nhất định. Nơi đó thường thực thi ràng buộc, kiểm soát concurrency và cung cấp quy trình ghi có thể kiểm chứng.

Ví dụ:

- Với đơn hàng trong Order Service, bảng orders trên primary database có thể là nguồn chuẩn của trạng thái đơn.
- Với khoản tiền đã capture, hệ thống thanh toán hoặc ledger được phân quyền có thể là nguồn chuẩn; một bảng cache trạng thái thanh toán ở Order Service không tự thay thế được nó.
- Với cấu hình phân quyền, cơ sở dữ liệu hoặc dịch vụ quản lý danh tính có thể là nguồn chuẩn; cache quyền truy cập cần quy định rõ thời gian chấp nhận stale.
- Với trang danh sách sản phẩm, cache có thể đủ tốt cho hiển thị; nhưng giá áp dụng khi checkout cần tuân theo quy tắc xác nhận giá tại điểm chốt đơn.

**Cache** là dữ liệu có thể được tái tạo hoặc đối chiếu từ nguồn chuẩn; thường chấp nhận bị xóa, hết hạn hoặc khởi tạo lại. Tuy nhiên nếu hệ thống cố tình dùng cache để nhận ghi hoặc giữ trạng thái duy nhất, nó không còn đơn thuần là bản sao tùy ý: phải thiết kế durability và ownership cho đường ghi ấy.

### 2.1. Vai trò không được suy ra từ tên công nghệ

| Thành phần | Vai trò có thể đảm nhận | Câu hỏi phải xác nhận |
|---|---|---|
| PostgreSQL primary | Nguồn chuẩn cho orders, inventory hoặc ledger | Có đúng là nơi mọi writer đều commit, cưỡng chế invariant không? |
| Redis | Cache giá, session hoặc dữ liệu tạm; đôi khi có thể là kho dữ liệu chính theo thiết kế riêng | Có cho phép mất dữ liệu và tái tạo không? Ghi ở đâu? |
| Caffeine/local memory | Cache trong một JVM, phạm vi một instance | Khi instance khác cập nhật DB, instance này biết bằng cách nào? |
| Read replica | Bản sao DB giúp mở rộng lượt đọc | Replica có thể trễ; đọc quyết định nghiệp vụ có bắt buộc cập nhật mới nhất không? |
| Elasticsearch/search index | Read model phục vụ tìm kiếm và xếp hạng | Nguồn nào tạo/chỉnh sửa tài liệu gốc? Mất index có rebuild được không? |
| Materialized view | Kết quả tiền xử lý/tổng hợp | Khi nào refresh, snapshot đang phản ánh mốc nào? |
| Browser/CDN cache | Bản sao ở xa server | Khi người dùng cập nhật dữ liệu, làm sao biết thiết bị/CDN còn bản cũ? |

Cùng một công nghệ có thể đóng nhiều vai trò. Ví dụ Redis có thể được dùng như kho dữ liệu chính trong một bài toán nhất định nếu người thiết kế chấp nhận và cấu hình độ bền phù hợp. **Không định nghĩa source of truth chỉ bằng tên PostgreSQL hay Redis.**

### 2.2. Một nguồn chuẩn theo từng loại dữ liệu, không nhất thiết một DB cho toàn hệ thống

Hệ thống phân tán có thể có các chủ sở hữu dữ liệu khác nhau:

~~~mermaid
flowchart LR
    O["Order Service"] --> OD[("Orders DB / nguồn chuẩn đơn hàng")]
    P["Payment Service"] --> PD[("Payment Ledger / nguồn chuẩn thanh toán")]
    I["Inventory Service"] --> ID[("Inventory DB / nguồn chuẩn tồn kho")]
    OD --> C[("Redis: bản đọc đơn hàng")]
    ID --> IC[("Redis: cache tồn kho hiển thị")]
    OD --> R[("Search / read model")]
~~~

Mỗi dịch vụ có thể là nơi quyết định đối với dữ liệu mình sở hữu. Một service khác giữ bản sao để truy vấn nhanh không có quyền tự xác nhận rằng thông tin đó là trạng thái cuối cùng. Khi nghiệp vụ cần kết hợp nhiều nguồn chuẩn, phải có protocol phối hợp, trạng thái trung gian và đối soát thích hợp.

## 3. Hai câu hỏi khác nhau: “đang thấy gì” và “được quyết định gì”

Giả sử:

~~~text
PostgreSQL (authoritative):
  product_id = P1
  price      = 120000
  version    = 8

Redis (cached):
  product_id = P1
  price      = 100000
  version    = 7
~~~

Cùng một request có thể được xử lý khác nhau:

- **Trang giới thiệu sản phẩm:** có thể chấp nhận thấy giá cũ ngắn hạn nếu giao diện/hợp đồng cho phép và giá được xác nhận lại tại checkout.
- **Chốt đơn/tính tiền:** không được mặc định lấy giá cũ version 7 làm quyết định cuối khi quy tắc yêu cầu giá hiệu lực hiện tại.
- **Báo cáo tổng hợp không theo thời gian thực:** có thể chấp nhận độ trễ vài phút nếu mốc cập nhật được công bố rõ.
- **Kiểm soát quyền truy cập:** dữ liệu stale sau khi thu hồi quyền có thể tạo lỗ hổng; cần chính sách freshness nghiêm ngặt và fail-closed khi cần.

**Cache không sai chỉ vì nó cũ** nếu hợp đồng rõ ràng cho phép stale. Cache trở nên nguy hiểm khi một use case cần tính đúng đắn cao nhưng lại coi giá trị stale là căn cứ cuối cùng.

### 3.1. Viết rõ yêu cầu nhất quán theo use case

| Use case | Yêu cầu gợi ý | Nguồn dữ liệu quyết định |
|---|---|---|
| Hiển thị ảnh đại diện | Chấp nhận stale trong giới hạn TTL | Profile service/DB gốc |
| Hiển thị số lượt xem | Chấp nhận trễ, hội tụ sau | Bộ đếm hoặc pipeline có contract rõ |
| Đọc trạng thái đơn vừa cập nhật | Cần read-your-writes hoặc cơ chế tra cứu xác nhận | Order DB/source authoritative |
| Xác nhận trừ hàng | Không chấp nhận bán vượt tồn | Inventory transaction/constraint |
| Chuyển tiền | Không tạo ghi sổ hai lần, đối soát được | Ledger + idempotency bền vững |
| Kiểm tra quyền đã bị thu hồi | Hạn chế tối đa stale hoặc fail-closed tùy mức nhạy cảm | Identity/authorization authoritative |
| Search sản phẩm | Chấp nhận index cập nhật bất đồng bộ | Product catalog gốc |

Đừng chọn một mức consistency cho tất cả màn hình. Quyết định theo mức nguy hiểm khi dữ liệu cũ và mức trễ mà người dùng chấp nhận.

## 4. Các trạng thái của một cache entry

Một cache key có thể ở những trạng thái khác nhau:

- **Hit, fresh:** có bản ghi và vẫn trong giới hạn freshness đã định.
- **Hit, stale:** có bản ghi nhưng phiên bản đã cũ so với nguồn chuẩn, dù TTL có thể chưa hết.
- **Miss:** không có bản ghi, phải lấy nguồn khác hoặc chờ làm mới.
- **Expired:** bản ghi hết hạn theo cơ chế TTL; lần đọc tiếp theo thường là miss hoặc kích hoạt refresh tùy cache.
- **Negative cache:** lưu kết quả “không tồn tại” hoặc một trạng thái vắng mặt trong thời gian ngắn.
- **Poisoned/wrong-scope:** key/giá trị thuộc tenant khác, sai schema hay chứa dữ liệu không nên cache.

### 4.1. TTL là giới hạn thời gian lưu, không phải bằng chứng dữ liệu còn mới

TTL 60 giây không nói rằng trong 60 giây ấy database không thay đổi. Nếu người khác cập nhật ở giây thứ nhất và không có invalidation, ứng dụng có thể đọc bản cũ gần một phút.

Một entry vừa được cache lúc 10:00:00 có thể stale ngay 10:00:01. TTL cho biết **khi nào cache tự coi entry hết hạn**, không xác nhận trạng thái của nguồn chuẩn.

Nếu sử dụng stale-while-revalidate, entry có thể được phục vụ **sau** thời điểm hết freshness để giảm độ trễ; thời gian chấp nhận stale phải là quyết định có chủ ý.

### 4.2. Cache miss không chứng minh entity không tồn tại

Cache không có key P1 có thể do mới khởi động, bị evict, hết TTL hoặc lỗi kết nối tới cache. Nếu API dùng miss để kết luận “đơn không tồn tại” mà không tra nguồn chuẩn, nó nhầm lẫn trạng thái cache với trạng thái nghiệp vụ.

Negative cache chỉ nên được tạo sau khi đọc nguồn dữ liệu phù hợp và có chính sách hết hạn; phải xem xét nguy cơ record được tạo mới trong lúc negative entry còn sống.

## 5. Cache-aside: mô hình thường gặp trong Java

Ở cache-aside, ứng dụng kiểm tra cache trước. Khi miss, nó đọc từ database rồi đưa kết quả vào cache.

~~~mermaid
flowchart TD
    A["Request GET product P1"] --> B{"Cache có P1?"}
    B -->|Hit| C["Trả cached DTO theo freshness policy"]
    B -->|Miss| D["Đọc Product DB"]
    D --> E["Map DTO / version"]
    E --> F["Cache SET có TTL"]
    F --> G["Trả DTO"]
    D -->|DB error| H["Áp dụng chính sách lỗi, không coi miss là not found"]
~~~

Pseudocode:

~~~java
public ProductView getProduct(long tenantId, UUID productId) {
    String key = "product:v1:" + tenantId + ":" + productId;

    ProductView cached = cache.get(key);
    if (cached != null) {
        return cached;
    }

    ProductView fresh = productRepository.findView(tenantId, productId)
        .orElseThrow(() -> new NoSuchElementException("Product not found"));

    cache.put(key, fresh, Duration.ofSeconds(60));
    return fresh;
}
~~~

Đây chỉ là minh họa luồng; code thật cần xử lý miss khác với cache unavailable, serialization/version, dữ liệu không tồn tại và đồng thời giữa các request. Nếu trường hợp cần strong freshness, trả ngay cached value mà không có kiểm chứng là **không đủ**.

### 5.1. Ưu điểm và giới hạn

Ưu điểm:

- Đơn giản, chỉ cache dữ liệu được yêu cầu.
- Cache hỏng có thể cho phép fallback về database với những use case phù hợp.
- TTL/eviction có thể giới hạn tăng trưởng.
- Dữ liệu có thể được tái tạo từ nguồn chuẩn.

Giới hạn:

- Lần đọc đầu tiên sau miss đi qua database và có thể chậm.
- Nhiều request cùng miss có thể dồn tải vào database (*cache stampede*).
- Cache có thể stale cho tới khi TTL hết hoặc bị invalidated.
- Giữa thao tác đọc database và SET cache có thể có writer khác commit, khiến **bản cũ được đưa trở lại cache**.

## 6. Các mẫu cache phổ biến và việc ai được quyền ghi

| Mẫu | Luồng cơ bản | Lưu ý về tính đúng đắn |
|---|---|---|
| Cache-aside | App đọc cache, miss thì đọc DB và SET | App phải xử lý stale/invalidation và race |
| Read-through | Cache/library tự load từ nguồn khi miss | Freshness vẫn phụ thuộc loader, TTL và thời điểm update |
| Write-through | Ghi đi qua lớp cache tới nguồn chuẩn theo cơ chế đồng bộ mà hệ thống cung cấp | Cần kiểm tra thứ tự và kết quả ghi ở cả hai bên; không tự có transaction chung |
| Write-behind/write-back | Nhận ghi ở cache/queue, ghi DB sau | Nếu cache giữ bản ghi duy nhất chưa được làm bền vững, đây là một ranh giới durability riêng; không phù hợp khi không được mất tác động |
| Refresh-ahead | Làm mới entry sắp hết hạn | Có thể tăng tải nền; stale vẫn có thể xảy ra |
| Invalidation + cache-aside | DB commit xong, xóa entry để lần đọc sau nạp lại | Mất invalidation và race SET là vấn đề phải giải quyết |
| Versioned cache | Giá trị mang version hoặc generation tăng đơn điệu | Giúp ngăn một phiên bản cũ ghi đè bản mới khi mọi writer tuân thủ |

Không chọn write-behind cho tồn kho/ledger chỉ vì latency ghi thấp: nếu database chưa có giao dịch đã commit mà cache hoặc tiến trình chết, nguy cơ mất tác động phải được tính thành một quyết định durability chính thức.

### 6.1. “Write-through” không mặc định nguyên tử hai hệ thống

Giả sử phương thức ghi DB thành công rồi cập nhật Redis bị lỗi. Không có transaction coordinator, hai hệ thống có thể lệch. Nếu cập nhật Redis trước DB, lỗi commit DB có thể khiến cache chứa trạng thái chưa từng là dữ liệu đã commit.

Cần xác định hệ thống nào là chuẩn và điều gì xảy ra khi thao tác thứ hai thất bại. Chỉ dùng tên “write-through” không đủ chứng minh cả hai commit nguyên tử.

## 7. Đọc source of truth khi đưa ra quyết định quan trọng

Bài toán tồn kho:

~~~sql
CREATE TABLE inventory (
    tenant_id bigint NOT NULL,
    sku text NOT NULL,
    available integer NOT NULL CHECK (available >= 0),
    version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, sku)
);
~~~

Một cache Redis có thể lưu available để hiển thị. Nhưng request mua hàng phải thực hiện ghi có điều kiện lên nguồn chuẩn:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE tenant_id = :tenantId
  AND sku = :sku
  AND available >= :quantity
RETURNING available, version;
~~~

Điều kiện kiểm tra và phép trừ được thực thi nguyên tử trên một hàng tại database trong transaction phù hợp. Khi không có hàng trả về, request không thể mặc định đã giữ được hàng. Cần xử lý SKU không tồn tại hoặc không đủ hàng theo contract.

**Không làm quyết định cuối bằng cache:**

~~~java
// Sai: kiểm tra cached available rồi tin chắc còn hàng.
int available = redis.getAvailable(sku);
if (available >= requested) {
    orderRepository.markConfirmed(orderId);
}
~~~

Hai request có thể cùng thấy available=1 trong cache và đều đánh dấu confirmed dù DB chỉ có một đơn vị. Cache tồn kho nên được xem là thông tin **gợi ý** khi hiển thị; invariant bán hàng phải được bảo vệ bằng transaction và constraint tại nguồn chuẩn hoặc một hệ thống reservation được thiết kế thực sự là authoritative.

Nếu nguồn chuẩn không sẵn sàng, một API cần tính đúng đắn cao thường phải từ chối, chuyển sang PENDING hoặc cho người dùng thử lại, thay vì tự chuyển vai trò quyết định sang bản cache stale.

## 8. Vì sao xóa cache sau UPDATE vẫn có thể đọc dữ liệu cũ?

Một cách phổ biến là “ghi database trước, sau đó xóa cache”. Cách này hợp lý hơn việc cập nhật cache trước commit, nhưng **không tự đảm bảo mọi lần đọc đều thấy dữ liệu mới nhất**.

### 8.1. Cửa sổ lỗi: DB commit rồi tiến trình chết trước khi xóa cache

~~~text
Writer                           PostgreSQL                 Redis
   |                                |                        |
   |-- UPDATE price=120000 -------->|                        |
   |-- COMMIT --------------------->|                        |
   |<-- COMMIT OK ------------------|                        |
   X  JVM crash                                             |
                                                       price=100000
~~~

Nếu invalidation chỉ được lên lịch trong RAM sau commit, JVM có thể chết trước khi lệnh DEL tới Redis. Entry giá cũ còn tồn tại đến khi TTL hết hoặc có một cơ chế khác sửa nó.

Một callback chạy afterCommit cũng có cửa sổ lỗi tương tự: transaction đã commit nhưng tiến trình có thể chết trước callback hoặc trước khi Redis xử lý xong.

### 8.2. Race giữa cache miss và invalidation

Giả sử giá đang ở version 7, T1 đang nạp cache, trong khi T2 cập nhật thành version 8:

~~~text
T1: GET cache -> MISS
T1: SELECT từ DB -> price=100000, version=7
                                          T2: UPDATE DB -> version=8
                                          T2: COMMIT
                                          T2: DEL cache key
T1: SET cache(price=100000, version=7)
T3: GET cache -> HIT version=7 dù DB đang version=8
~~~

Đây là race phổ biến: T2 đã xóa cache nhưng **T1 nạp lại dữ liệu cũ sau khi xóa**. Ngay cả khi không có lỗi mạng hoặc process crash, cách “DB commit rồi DEL cache” không tự bảo đảm tính tuyến tính của mọi lượt đọc.

### 8.3. Vì sao xóa trước khi ghi DB cũng chưa giải quyết?

~~~text
T2: DEL cache
T1: cache MISS
T1: đọc DB -> version=7
T1: SET cache version=7
T2: UPDATE DB version=8 rồi COMMIT
~~~

Cache lại chứa phiên bản cũ. Nếu cập nhật cache trực tiếp trước khi commit, một transaction rollback có thể để cache mang dữ liệu chưa từng được commit. Không nên chỉ đổi thứ tự ghi/xóa và tuyên bố đã có tính nguyên tử giữa PostgreSQL và Redis.

**Kết luận:** invalidation là một chiến lược giảm độ stale, không phải một transaction phân tán. Phải chỉ rõ cửa sổ stale chấp nhận được và cách phục hồi.

## 9. Chiến lược giảm stale và xử lý race

Không có một biện pháp phù hợp mọi workload. Có thể phối hợp các lớp bảo vệ.

### 9.1. TTL hữu hạn làm giới hạn tồn tại của entry cũ

TTL giúp stale data cuối cùng biến mất nếu không còn cơ chế nào khác sửa. Ví dụ danh sách sản phẩm có thể cache 30–60 giây khi chấp nhận hiển thị chậm cập nhật.

Giới hạn:

- TTL không bảo đảm dữ liệu vẫn fresh trước lúc hết hạn.
- TTL trên một cache layer không đủ nếu CDN hoặc cache trong JVM có TTL khác.
- TTL dài làm stale kéo dài; TTL rất ngắn tăng cache miss và tải database.
- TTL không giải quyết yêu cầu phải xác nhận quyền hoặc số dư mới nhất ngay lập tức.

### 9.2. Invalidation chủ động sau commit

Khi DB commit một thay đổi, phát tín hiệu để xóa hoặc làm mới các key liên quan. Cần biết rõ **tập key phụ thuộc**: thay đổi giá P1 có thể ảnh hưởng product detail, category listing, search result, aggregate count và cache tại CDN.

Nếu chỉ xóa key chi tiết, bản danh sách đã materialize vẫn có thể hiển thị giá cũ. Đây là vấn đề **dependency graph của dữ liệu**, không chỉ lời gọi DEL.

### 9.3. Gắn version đơn điệu

Mỗi entity có version tăng sau cập nhật:

~~~sql
CREATE TABLE products (
    tenant_id bigint NOT NULL,
    id uuid NOT NULL,
    name text NOT NULL,
    price numeric(18, 2) NOT NULL CHECK (price >= 0),
    version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id)
);

UPDATE products
SET price = :price,
    version = version + 1
WHERE tenant_id = :tenantId
  AND id = :id
  AND version = :expectedVersion
RETURNING price, version;
~~~

Giá trị cache cũng mang version:

~~~json
{
  "tenantId": 42,
  "productId": "a24c6f09-0c40-4a39-8895-447296f61018",
  "price": 120000,
  "version": 8
}
~~~

Nếu cache đã có version=8, một request nạp chậm version=7 **không được ghi đè** bản mới. Việc so sánh và SET phải nguyên tử ở tầng cache (ví dụ Redis script hoặc primitive CAS thích hợp), không làm GET rồi SET tách rời vì giữa hai bước có thể chen một writer khác.

Nhưng lưu ý: **so sánh với version của giá trị đang có chưa đủ** nếu invalidation vừa xóa key! Sau DEL, version cũ có thể được SET lại vì cache không còn thông tin version mới hơn. Nếu yêu cầu chống race này, cần duy trì một **generation/version floor** hoặc tombstone còn sống đủ lâu, có cập nhật và so sánh nguyên tử, hoặc thiết kế đường đọc không tin cache khi cần freshness mạnh.

Đây là lý do không nên tuyên bố “thêm version là đảm bảo linearizable” nếu chưa xét thứ tự đọc DB, commit, invalidate, SET và key vắng mặt.

### 9.4. Chỉ một chủ ghi đối với cùng khóa, khi phù hợp

Một số hệ thống dùng luồng xử lý event được phân vùng theo entityId để các bản cập nhật cache của một entity được áp dụng theo thứ tự. Điều này giảm out-of-order update nhưng vẫn phải xử lý retry, duplicate, replay, consumer restart và nguồn event khác.

Nếu nhiều writer có thể cập nhật cùng entity ở nhiều dịch vụ, cần xác định **ai cấp số version** và làm sao version được so sánh nhất quán. Timestamp của từng máy không phải một version đơn điệu đáng tin khi đồng hồ lệch hoặc các sự kiện đến sai thứ tự.

### 9.5. Đọc nguồn chuẩn cho yêu cầu consistency cao

Nếu không thể chấp nhận stale trong luồng quyết định, **đừng chọn cache như nơi ra quyết định cuối cùng**. Dùng SQL nguyên tử có điều kiện, khóa/transaction hoặc truy vấn nguồn authoritative với consistency phù hợp. Cache có thể phục vụ UI trước đó, nhưng hành động chốt cần kiểm tra lại.

## 10. Outbox: không mất ý định invalidation sau commit

Để hạn chế cửa sổ “DB commit rồi process chết trước khi gửi tín hiệu”, có thể ghi dữ liệu nghiệp vụ và một **outbox event** trong cùng transaction DB.

~~~sql
CREATE TABLE cache_outbox (
    event_id uuid PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    tenant_id bigint NOT NULL,
    event_type text NOT NULL,
    aggregate_version bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
~~~

Ví dụ luồng:

~~~mermaid
sequenceDiagram
    participant API as Product Service
    participant DB as PostgreSQL
    participant O as Outbox Dispatcher
    participant M as Event Bus
    participant C as Cache Invalidator
    participant R as Redis
    API->>DB: BEGIN
    API->>DB: UPDATE product version=8
    API->>DB: INSERT outbox(ProductPriceChanged, v8)
    API->>DB: COMMIT
    O->>DB: Đọc sự kiện chưa phát
    O->>M: Publish eventId + version
    M->>C: Giao sự kiện
    C->>R: Invalidate / advance version floor
    C-->>M: ACK xử lý
~~~

Bản ghi thay đổi và ý định phát event cùng tồn tại hoặc cùng rollback. Nếu worker chết, outbox còn để thử lại. Nhưng cơ chế này **không làm invalidation tức thời**: dispatcher và consumer có độ trễ, event có thể đến trùng hoặc sai thứ tự. Chỉ xóa entry qua event mà không quản lý race cache miss vẫn có thể để entry cũ được nạp lại.

### 10.1. At-least-once và idempotent invalidation

Một event có eventId ổn định, aggregateId và version cho phép invalidator phát hiện duplicate hoặc event đến trễ. Gọi DEL cùng key nhiều lần thường không gây tác động nghiệp vụ nguy hiểm, nhưng nếu dùng logic “đặt cache thành giá trị trong event” thì **event cũ có thể ghi đè event mới**. Cần kiểm tra version nguyên tử.

Một hệ thống có read model phức tạp phải quản lý cả phiên bản/schema event, trạng thái consumer và khả năng replay. Không được suy broker bảo đảm exactly-once toàn bộ DB + Redis chỉ vì event có ID.

### 10.2. Cần đặt điểm bảo đảm nào?

| Cam kết mong muốn | Outbox có giúp không? | Cần bổ sung gì? |
|---|---|---|
| Không mất ý định invalidation khi DB commit | Có, nếu outbox cùng local transaction và được xử lý bền vững | Dispatcher phục hồi, retry, giám sát backlog |
| Invalidation xuất hiện ngay khi COMMIT trả về | Không tự đảm bảo | Đồng bộ hóa khác hoặc đọc source authoritative cho use case yêu cầu mạnh |
| Không áp dụng event cũ sau event mới | Không tự đảm bảo | Version và so sánh nguyên tử/ordering |
| Không nạp lại phiên bản cũ sau DEL | Không tự đảm bảo | Generation/tombstone, protocol nạp cache hoặc yêu cầu freshness khác |
| Cache lỗi không khiến mất dữ liệu gốc | Có thể đạt nếu DB là nguồn chuẩn | Fallback, backpressure và phân loại use case |
| Có thể rebuild cache | Có thể nếu nguồn và dữ liệu cần thiết còn | Quy trình rebuild, kiểm soát tải, version/schema |

## 11. Spring Cache trong ranh giới transaction

Spring cung cấp các annotation để gọi cache qua abstraction, chẳng hạn @Cacheable và @CacheEvict. Chúng giúp giảm mã lặp nhưng **không biến Redis hoặc Caffeine thành thành viên của database transaction**.

Ví dụ cache riêng cho DTO chỉ đọc:

~~~java
@Service
public class ProductReadService {
    private final ProductQueryRepository products;

    public ProductReadService(ProductQueryRepository products) {
        this.products = products;
    }

    @Cacheable(
        cacheNames = "productViews",
        key = "#tenantId + ':' + #productId",
        unless = "#result == null"
    )
    public ProductView getProduct(long tenantId, UUID productId) {
        return products.findView(tenantId, productId)
            .orElse(null);
    }
}
~~~

Ví dụ dùng SpEL tạo key có tenantId và productId, ngăn lấy nhầm cùng UUID giữa các tenant. Trong production cần kiểm tra chuẩn hóa key, schema version, serializer, TTL và cơ chế cache lỗi. Với dữ liệu chứa thông tin nhạy cảm theo người dùng, key có thể phải bổ sung scope phân quyền chứ không chỉ tenantId.

### 11.1. @Cacheable không hứa kết quả mới nhất

Method được gọi qua proxy có thể trả ngay ProductView từ cache mà không chạy query. Nếu DB cập nhật giữa hai lần đọc, giá trị cached vẫn có thể cũ.

- Không sử dụng @Cacheable cho một method mà contract bắt buộc fresh sau mọi commit nếu chưa thiết kế cơ chế đồng bộ tương ứng.
- Self-invocation (gọi qua this.getProduct()) trong cơ chế proxy thông thường có thể không đi qua interceptor cache.
- Cần hiểu null caching, ngoại lệ, TTL và serializer của cache provider thực tế.
- Nếu method trả kiểu lazy phụ thuộc persistence context thì object lấy từ cache có thể chứa proxy hoặc dữ liệu chưa materialize; nên cache DTO immutable hoặc dữ liệu đã ánh xạ hoàn chỉnh.

### 11.2. @CacheEvict kết hợp @Transactional vẫn cần kiểm chứng thứ tự

Ví dụ có vẻ thuận tiện:

~~~java
@Transactional
@CacheEvict(cacheNames = "productViews", key = "#tenantId + ':' + #productId")
public void updatePrice(long tenantId, UUID productId, BigDecimal newPrice) {
    productRepository.updatePrice(tenantId, productId, newPrice);
}
~~~

Không nên tự kết luận eviction **chắc chắn diễn ra sau khi DB commit bền vững** chỉ vì hai annotation xuất hiện cạnh nhau. Thứ tự các interceptor/advice, transaction propagation và cấu hình cache manager ảnh hưởng thời điểm thao tác. Nếu updatePrice tham gia transaction bên ngoài, method return chưa chắc là lúc outer transaction commit.

Nếu DB rollback sau khi cache bị xóa, cache có thể bị miss rồi nạp lại dữ liệu cũ. Nếu cache được cập nhật trước COMMIT, thậm chí có thể mang trạng thái chưa commit. Nếu process chết sau COMMIT nhưng trước eviction, tín hiệu không còn trong RAM có thể mất.

Với cập nhật quan trọng, để service giao cho DB và outbox nằm cùng transaction; **dispatcher thực hiện invalidation sau commit**, có cơ chế phục hồi. Khi ứng dụng cần read-your-writes mạnh, API vừa ghi xong có thể lấy và trả kết quả authoritative của transaction thay vì lập tức đi qua cache chung.

### 11.3. Ví dụ luồng ghi không coi cache là transaction member

~~~java
@Service
public class ChangeProductPriceService {
    private final ProductWriteRepository products;
    private final OutboxRepository outbox;

    public ChangeProductPriceService(
            ProductWriteRepository products,
            OutboxRepository outbox) {
        this.products = products;
        this.outbox = outbox;
    }

    @Transactional
    public long changePrice(
            long tenantId,
            UUID productId,
            BigDecimal newPrice,
            long expectedVersion) {
        long nextVersion = products.updatePriceIfVersionMatches(
            tenantId, productId, newPrice, expectedVersion
        );

        // Giả định method trên ném lỗi khi UPDATE không có hàng.
        outbox.appendPriceChanged(
            tenantId, productId, nextVersion
        );

        return nextVersion;
    }
}
~~~

Ví dụ giả định cả hai repository dùng cùng DataSource/transaction manager và phương thức được gọi qua proxy @Transactional. ProductWriteRepository thực thi một UPDATE có điều kiện và trả version mới; outbox được commit nguyên tử với thay đổi giá. Việc xóa/cache refresh diễn ra ở worker khác; điều này chấp nhận **eventual consistency** của cache trong cửa sổ propagation.

Không dùng callback afterCommit chỉ sống trong bộ nhớ như thay thế cho outbox khi bắt buộc phải có khả năng phục hồi sau crash.

## 12. Read replica khác với cache nhưng vẫn có thể stale

Read replica lưu bản sao của database để tăng khả năng phục vụ truy vấn hoặc hỗ trợ failover. Tùy cơ chế replication, replica có thể chứa dữ liệu có cấu trúc giao dịch và chỉ mục gần với primary, nhưng không nhất thiết bắt kịp mọi transaction mới.

~~~text
T1: UPDATE orders SET status='CONFIRMED' ... ở primary
T1: COMMIT -> client nhận thành công
T2: SELECT order từ replica đang trễ -> PENDING
~~~

Một request nhìn thấy PENDING **không chứng minh COMMIT trên primary thất bại**. Nếu ứng dụng cần read-your-writes, có thể chọn đọc primary cho một khoảng sau ghi hoặc sử dụng cơ chế replica consistency/read position mà hạ tầng hỗ trợ.

### 12.1. Replica lag và cache TTL là hai vấn đề khác nhau

- Cache có thể stale vì entry chưa được invalidated hoặc TTL chưa hết.
- Replica có thể stale vì WAL/log chưa được truyền hoặc apply.
- Search index có thể stale vì consumer chưa xử lý event.
- CDN có thể stale vì cơ chế phân phối invalidation còn trễ.

Gọi tất cả là “cache stale” có thể che nguyên nhân vận hành. Đo **replication lag**, **event backlog** và **cache entry age** bằng chỉ số khác nhau.

### 12.2. Replication không đồng nghĩa backup

Primary và replica có thể cùng sao chép một lệnh xóa nhầm hoặc trạng thái sai. Backup lịch sử và kiểm thử restore bảo vệ một loại rủi ro khác. Nếu muốn dựng lại cache sau khi mất Redis, phải chắc nguồn dữ liệu chuẩn và công cụ tái tạo còn truy cập được.

## 13. Hai tầng cache và vấn đề invalidation lan truyền

Một hệ thống Java có thể dùng đồng thời:

- **L1:** cache local trong JVM, ví dụ Caffeine.
- **L2:** cache phân tán trong Redis.
- **DB:** nguồn chuẩn.
- **CDN/browser:** bản sao xa hơn cho dữ liệu có thể phân phối công khai.

~~~text
HTTP -> JVM L1 -> Redis L2 -> PostgreSQL authoritative
             \
              -> mỗi application instance có L1 riêng
~~~

Nếu update chỉ DEL Redis L2, L1 trên các instance khác vẫn có thể giữ bản cũ. Một event invalidation gửi tới Redis chưa chắc được mọi instance xử lý nếu kênh thông báo không bền vững hoặc có instance đang offline.

Có thể dùng TTL ngắn ở L1, event invalidation tới tất cả instance, versioned entries hoặc chiến lược bypass L1 trong use case nhạy cảm. Cần làm rõ **thời gian stale tối đa của từng tầng** và trạng thái khi listener không kết nối.

Không cache response chứa dữ liệu riêng của người dùng qua CDN/public cache nếu chưa có khóa phân biệt người dùng và chính sách HTTP Cache-Control phù hợp.

## 14. Cache key, identity, schema version và quyền truy cập

Một cache key tốt phải bao gồm đủ yếu tố quyết định dữ liệu trả về.

Ví dụ:

~~~text
product-view:v2:tenant=42:product=P1:currency=VND
order-summary:v3:tenant=42:order=O7:locale=vi-VN
permissions:v4:tenant=42:user=U9:scope=admin
~~~

Không dùng chỉ productId nếu dữ liệu phụ thuộc tenant. Không dùng chỉ URL nếu response khác nhau theo actor, role hoặc ngôn ngữ.

### 14.1. Những yếu tố nên xem xét

| Yếu tố | Vì sao quan trọng |
|---|---|
| Tenant/organization | Ngăn lấy dữ liệu của tenant khác |
| Identity hoặc authorization scope | Quyền xem có thể thay đổi nội dung |
| Locale/currency | Cùng entity nhưng cách biểu diễn khác |
| Bộ lọc, phân trang, sort | Danh sách khác điều kiện là giá trị khác |
| Schema/cache format version | Tránh code mới đọc nhầm payload cũ |
| Business version | Giúp nhận ra bản cũ so với nguồn chuẩn |
| TTL và loại dữ liệu | Bảo vệ bộ nhớ và giới hạn stale |
| Không chứa thông tin bí mật trong key | Key có thể xuất hiện ở log/metrics; mã hóa hoặc băm có kiểm soát khi cần |

Nếu lưu object serializable trong Redis, cần có quy tắc nâng version payload khi deploy. Dữ liệu cache có thể tồn tại lâu hơn version code đã tạo ra nó; lỗi deserialize cần được xử lý như **cache miss có kiểm soát** khi phù hợp, không làm hỏng trạng thái DB gốc.

### 14.2. Cẩn thận với quyền đã bị thu hồi

Giả sử cache quyền ghi trả true trong 10 phút. Quản trị viên vừa thu hồi quyền, nhưng API vẫn tin vào cache cũ. Đây không chỉ là vấn đề UI hiển thị chậm mà có thể là **lỗ hổng bảo mật**.

Đối với quyền nhạy cảm cần thiết kế chính sách không cho sử dụng token/quyền đã thu hồi trong quá thời gian chấp nhận. Có thể dùng token ngắn hạn, kiểm tra version quyền hoặc đọc nguồn authoritative theo từng hành động quan trọng. Khi nguồn kiểm tra quyền mất kết nối, thường nên **fail-closed** cho hành động nhạy cảm thay vì cho phép dựa trên bản cũ không được xác nhận.

Không có một TTL “an toàn” chung cho mọi phân quyền; nó phụ thuộc mức rủi ro và hợp đồng hệ thống.

## 15. Cache stampede, hot key và negative caching

### 15.1. Stampede khi nhiều request cùng miss

Một sản phẩm nổi bật có 2.000 request cùng lúc đúng khi TTL hết. Nếu mỗi request tự SELECT database, cache không còn giảm tải mà có thể tạo đợt truy vấn đột biến.

Cách giảm:

- **Request coalescing/single-flight** cho cùng key trong một instance.
- **Distributed lock hoặc lease** để một worker nạp lại; người khác đợi ngắn hoặc dùng stale trong giới hạn cho phép.
- **TTL jitter** để các key không đồng loạt hết hạn.
- **Refresh-ahead** cho hot key, với giới hạn lượng công việc nền.
- **Rate limiting/bulkhead** để cache failure không kéo sập DB.

Nếu dùng lock/lease, cần xét worker chết, lease hết hạn, nạp quá lâu và concurrent loader. Lock không thay thế giao thức kiểm tra version; một loader chậm có thể SET dữ liệu cũ sau khi giá mới đã commit.

### 15.2. Negative caching

Cache kết quả “không tìm thấy” có thể ngăn nhiều request lặp truy vấn một ID không tồn tại:

~~~text
get product P9 -> DB không có P9
cache "NOT_FOUND" trong 10 giây
request khác P9 -> trả not found từ cache
~~~

Nếu P9 được tạo mới ngay sau đó, bản negative cache có thể che P9 cho tới lúc hết hạn. Đặt TTL ngắn hơn, xóa negative key khi tạo entity, hoặc tránh negative cache cho các nghiệp vụ cần thấy record mới ngay.

Phân biệt **DB trả not found đã xác nhận** với **DB timeout**. Không lưu “NOT_FOUND” vào cache khi thực chất truy vấn nguồn chuẩn bị lỗi.

### 15.3. Hot key và phân tán tải

Một key có quá nhiều lượt đọc có thể làm nghẽn một nút Redis, CPU serialization hoặc network. L1 cache và replica read có thể giúp, nhưng càng nhiều lớp càng khó invalidation. Chọn theo access pattern, quan sát hit rate, latency và cửa sổ stale thay vì nhân cache layer vô hạn.

## 16. Chọn chính sách khi cache hoặc database lỗi

Không phải mọi use case đều nên fallback giống nhau.

### 16.1. Cache không truy cập được

Nếu Redis timeout nhưng DB authoritative vẫn hoạt động, nhiều use case đọc có thể:

1. Đo lỗi cache riêng, tránh retry Redis quá nhiều lần.
2. Bypass Redis và đọc trực tiếp DB trong một giới hạn concurrency phù hợp.
3. Trả dữ liệu authoritative hoặc lỗi có kiểm soát nếu DB không chịu được tải bổ sung.
4. Áp dụng circuit breaker và bulkhead để bảo vệ DB trước cache stampede.
5. Khi cache phục hồi, làm ấm lại dần theo nhu cầu, tránh quét nạp toàn bộ không giới hạn.

**Không nên mặc định:** “Cache hỏng thì 100% request cùng đổ vào DB ngay lập tức.” Một cache chia sẻ thường hấp thụ lượng đọc rất lớn; fallback cần điều tiết tải.

### 16.2. Database nguồn chuẩn không truy cập được

Lúc này phải phân loại nghiệp vụ:

| Nghiệp vụ | Có thể trả cached data không? | Gợi ý |
|---|---|---|
| Danh sách bài viết công khai | Có thể, nếu đã công bố chấp nhận stale | Hiển thị dữ liệu cũ có nhãn phù hợp |
| Gợi ý sản phẩm | Có thể nếu chỉ phục vụ khám phá | Không chốt tồn kho bằng giá trị gợi ý |
| Xác nhận mua hàng | Không nên xác nhận bằng cached inventory | PENDING, 503 hoặc workflow phù hợp |
| Chuyển tiền | Không quyết định ghi sổ từ cache | Từ chối/tạm hoãn, đối soát sau khi nguồn phục hồi |
| Phân quyền quan trọng | Thường không cho phép dựa vào trạng thái cũ chưa xác minh | Fail-closed hoặc cơ chế auth có bảo đảm riêng |
| Đọc số liệu báo cáo lịch sử | Có thể nếu yêu cầu cho phép mốc cũ | Công bố thời điểm cập nhật dữ liệu |

Phương án fail-open hay fail-closed là **quyết định nghiệp vụ và an ninh**, không chỉ cấu hình kỹ thuật của cache library.

### 16.3. Dữ liệu có thể bị sai nhưng chưa hề hết hạn

Nếu cache key đặt thiếu tenantId, cache hit vẫn “thành công” về kỹ thuật nhưng trả dữ liệu của người khác. Nếu serializer thay đổi schema giữa hai phiên bản ứng dụng, bản cached payload có thể bị hiểu sai. Nếu cập nhật quyền chưa được invalidated, TTL còn hiệu lực không khiến quyền cũ hợp lệ.

Đừng xem cache hit rate cao là chỉ số chất lượng duy nhất. Kiểm tra **độ đúng của key, tuổi dữ liệu, version mismatch và khả năng phát hiện sai lệch**.

## 17. Quan sát: đo hiệu năng và đo độ nhất quán

Một hệ thống cache tốt cần giảm tải mà vẫn đáp ứng hợp đồng freshness. Theo dõi cả hai nhóm metric.

| Metric | Giải thích | Tín hiệu đáng điều tra |
|---|---|---|
| Cache hit/miss ratio | Phần trăm request được phục vụ từ cache | Miss tăng đột biến, cold start, key churn |
| Cache get/set latency | Độ trễ Redis/Caffeine và network | Cache chậm hơn DB đối với truy vấn đơn giản |
| Cache error/timeout | Số lần cache không phản hồi | Fallback khiến DB chịu tải tăng |
| Entry age và TTL còn lại | Tuổi dữ liệu cached khi được phục vụ | Entry cũ hơn hợp đồng cho phép |
| Version mismatch | So sánh mẫu với nguồn authoritative | Bản cache cũ tồn tại quá lâu |
| Invalidation lag | Từ lúc DB commit đến lúc cache xử lý tín hiệu | Backlog của outbox/broker/consumer |
| Outbox backlog oldest age | Ý định invalidation lâu nhất chưa phát | Worker dừng hoặc retry lỗi kéo dài |
| DB QPS/CPU/lock wait | Tải lên nguồn chuẩn | Stampede hoặc fallback không giới hạn |
| p50/p95/p99 API latency | Trải nghiệm người dùng | Miss hoặc chờ distributed lock kéo dài |
| Load failure/duplicate loader | Nhiều worker cùng nạp một key | Single-flight/lease cần xem lại |
| Security-sensitive stale count | Quyền đã thu hồi nhưng cache còn dùng | Vấn đề an toàn nghiêm trọng |

### 17.1. Shadow read để đo sai lệch

Với một tỷ lệ nhỏ request đọc và có kinh phí truy vấn cho phép, có thể lấy cached value rồi **đọc đối chiếu DB** mà không ảnh hưởng đến quyết định API hiện tại, sau đó so version hoặc hash dữ liệu:

~~~text
Request sample
   |
   +-- cache.get(P1) -> v7
   |
   +-- DB authoritative -> v8
   |
   +-- metric cache_version_lag = 1
   +-- log correlationId và metadata không nhạy cảm
~~~

Chỉ làm shadow read ở tần suất kiểm soát, tránh biến cơ chế đo thành tải lớn trên DB. Với dữ liệu có cập nhật liên tục, phải hiểu rằng cache và DB có thể được đọc ở hai thời điểm khác nhau; kết quả mismatch không nhất thiết là lỗi vi phạm hợp đồng nếu ứng dụng chấp nhận stale.

### 17.2. Chỉ số “mới” cần được định nghĩa

Những câu nói như “cache cập nhật gần như ngay lập tức” khó kiểm chứng. Tốt hơn nên có một mục tiêu đo được:

- 99% tín hiệu invalidation được áp dụng trong một khoảng thời gian đã định.
- Entry public catalog không bị phục vụ quá tuổi freshness được công bố.
- Luồng checkout luôn đối chiếu giá và tồn kho ở nguồn authoritative trước khi chốt.
- API kiểm soát quyền không dùng bản sao vượt chính sách thu hồi quyền.

Đừng hứa “mọi request đọc thấy dữ liệu mới ngay sau commit” khi thiết kế có cache-aside và asynchronous invalidation. Nếu hợp đồng cần **linearizable read-after-write**, phải dùng giao thức và nguồn đọc phù hợp chứ không chỉ giảm TTL.

## 18. Thiết kế kiểm thử đúng các cửa sổ race

### 18.1. Test stale re-population

Tạo hai thread hoặc hai tiến trình điều phối bằng barrier:

~~~text
Ban đầu DB version=7, cache MISS.

Thread T1: cache get -> MISS
Thread T1: DB select -> version=7
            [pause trước cache SET]
Thread T2: DB update -> version=8 và COMMIT
Thread T2: DEL cache
Thread T1: SET cache version=7
Thread T3: GET cache -> version=7 (stale)
~~~

**Mục tiêu:** chứng minh invalidation đơn giản không cung cấp strong consistency. Sau đó kiểm tra giải pháp version/generation hoặc chính sách TTL có giới hạn stale đúng kỳ vọng.

### 18.2. Test crash sau commit

~~~text
Writer:
  DB UPDATE + INSERT outbox
  COMMIT
  [process crash trước khi publish]

Dispatcher sau restart:
  Đọc outbox chưa phát
  Publish event
  Consumer invalidation
~~~

Kiểm tra rằng intent không biến mất, event có thể được retry, duplicate không phá trạng thái và backlog được xử lý. **Không dùng test này làm bằng chứng cache đã có dữ liệu mới ngay tại commit**: đó là mục tiêu khác.

### 18.3. Test out-of-order event

Gửi sự kiện thay đổi cùng productId:

~~~text
PriceChanged version=10
PriceChanged version=9 (đến muộn)
PriceChanged version=10 (duplicate)
~~~

Nếu consumer dùng event để SET cache, version 9 không được ghi đè v10. Nếu consumer chỉ DEL, phải kiểm tra lại race loader và version floor chứ không chỉ kiểm tra DEL có thể gọi lặp.

### 18.4. Test key isolation và invalidation phụ thuộc

- Hai tenant có cùng productId nhưng giá khác nhau phải có hai key độc lập.
- Hai người có quyền khác nhau không được nhận cùng cached response nhạy cảm nếu contract khác nhau.
- Khi đổi giá, cache chi tiết, danh sách, search và CDN có lộ giá cũ ngoài khoảng cho phép không?
- Khi cập nhật schema payload, code phiên bản mới có giải mã được entry cũ hoặc fallback an toàn không?
- Khi Redis ngắt kết nối, DB có bị stampede từ mọi instance không?
- Khi Caffeine L1 trên một node không nhận event, TTL hoặc versioning có giúp phục hồi không?
- Khi read replica trễ, request xác minh commit có vô tình đọc dữ liệu cũ không?

### 18.5. Integration test và môi trường thật

Unit test fake cache giúp kiểm tra luồng cache hit/miss, nhưng không mô phỏng được TTL, eviction, mạng, cache failover, Redis atomic operation hoặc transaction DB. Cần integration test với PostgreSQL/Redis tương ứng khi kết quả phụ thuộc semantics cụ thể, cùng test concurrent request/fault injection có kiểm soát.

Không dùng Thread.sleep ngẫu nhiên như một chiến lược kiểm thử race chính; dùng latch/barrier để dừng ở mốc xác định. Kiểm tra các invariant nghiệp vụ, không chỉ assert số lượt gọi cache.

## 19. Case study: cập nhật giá trong hệ thống bán hàng

### 19.1. Yêu cầu

Một sản phẩm có:

- Giá chuẩn lưu ở Product DB.
- Giá hiển thị trong Redis và CDN được phép cũ ngắn hạn.
- Giá checkout **phải được xác nhận tại thời điểm đặt hàng**.
- Khi quản trị viên đổi giá, các bản đọc phải hội tụ về giá mới.
- Nếu hệ thống cache mất kết nối, quản trị viên vẫn phải biết lần cập nhật đã commit DB hay chưa.

### 19.2. Thiết kế

~~~mermaid
flowchart TD
    A["Admin đổi giá"] --> B["Product Service transaction"]
    B --> C[("Products DB: price + version")]
    B --> D[("Outbox: PriceChanged")]
    D --> E["Dispatcher + Broker"]
    E --> F["Invalidate Redis/CDN/L1"]
    G["Product page GET"] --> H{"Cached view đủ mới theo policy?"}
    H -->|Có| I["Hiển thị giá cached"]
    H -->|Không| J["Đọc DB và cache với giới hạn stale"]
    K["Checkout"] --> L["Kiểm tra giá, tồn kho tại nguồn chuẩn"]
    L --> M["Commit order theo luật nghiệp vụ"]
~~~

Luồng chính:

1. Admin gửi giá mới kèm expectedVersion.
2. Product Service dùng UPDATE có điều kiện version và ghi outbox cùng transaction.
3. Sau commit, dispatcher phát sự kiện; các lớp cache invalidated hoặc làm mới theo version.
4. GET product page có thể phục vụ cached value trong giới hạn stale được công bố.
5. Checkout **không tin cache giá/tồn kho là quyết định cuối**; xác thực giá hiệu lực và reserve số lượng bằng transaction có điều kiện theo chính sách.
6. Nếu checkout phát hiện giá đã đổi, API trả phản hồi cho người dùng xác nhận giá mới, không âm thầm tính phí theo giá cached.
7. Mọi event/worker có metrics lag và đường phục hồi khi crash.

### 19.3. Những lỗi cần đặt câu hỏi

| Sự cố | Hệ quả nếu thiết kế sơ sài | Bảo vệ |
|---|---|---|
| DB commit thành công nhưng JVM chết trước DEL | Cache giữ giá cũ | Outbox phục hồi + TTL giới hạn |
| Loader lấy v7 rồi SET sau invalidation v8 | Bản cũ quay trở lại | Version/generation hoặc chấp nhận stale có giới hạn |
| Redis không trả kết quả | Trang sản phẩm không phục vụ được dù DB khỏe | Fallback có giới hạn và circuit breaker |
| Redis trả tồn kho=5, DB chỉ còn 1 | Bán vượt tồn nếu tin cache | Atomic UPDATE/constraint ở nguồn chuẩn |
| Event v8 đến sau v9 | Cache bị ghi đè nếu xử lý không xét version | Monotonic version/CAS |
| CDN cache response theo productId mà thiếu tenant | Rò giá hoặc thông tin giữa tenant | Key scoping và chính sách cache HTTP |
| Đọc replica lag sau khi admin commit | Admin không thấy giá vừa cập nhật | Read-your-writes qua primary hoặc cơ chế replica consistency phù hợp |

## 20. Bài tập tự kiểm tra

### Bài A — Cache có số lượng lớn hơn DB

Redis chứa available=5, PostgreSQL có available=1. Hai người cùng muốn mua 1 đơn vị.

**Câu hỏi:** Dữ liệu nào có quyền quyết định còn hàng? Nêu cách cập nhật an toàn.

**Gợi ý:** Inventory nguồn chuẩn hoặc hệ reservation authoritative phải quyết định. Với mô hình một hàng PostgreSQL, dùng UPDATE ... SET available = available - 1 WHERE available >= 1 trong transaction; không dựa vào cached value để xác nhận cả hai đơn.

### Bài B — TTL có bảo đảm fresh?

Cache chi tiết sản phẩm có TTL=5 phút. Admin đổi giá sau 10 giây.

**Câu hỏi:** Trong 4 phút 50 giây tiếp theo, cache có thể stale không? TTL giúp gì?

**Gợi ý:** Có. TTL hạn chế thời gian tồn tại của entry mà không được invalidated; nó không bảo đảm cache luôn đúng trước thời điểm hết hạn. Dùng invalidation để giảm độ stale, nhưng phải thiết kế race và lost event.

### Bài C — Evict sau commit nhưng vẫn sai

T1 cache miss, đọc v7. T2 cập nhật DB v8, commit và DEL. Sau đó T1 SET v7.

**Câu hỏi:** Vì sao DB commit trước DEL chưa đủ? Hướng xử lý?

**Gợi ý:** Race nạp bản cũ sau invalidation. Có thể dùng version/generation floor, giao thức đồng bộ loader hoặc chỉ dùng cache cho use case chấp nhận stale. Kiểm tra cả tình huống key đã bị xóa.

### Bài D — Cùng key cho hai tenant

Hai tenant có productId P1 trùng nhau nhưng khác giá. Cache key chỉ là product:P1.

**Câu hỏi:** Lỗi kỹ thuật và bảo mật nào có thể xảy ra?

**Gợi ý:** Cache collision dẫn tới phục vụ sai giá hoặc rò dữ liệu giữa tenant. Key phải bao gồm tenant và mọi yếu tố quyết định representation/quyền truy cập.

### Bài E — Xóa Redis trước UPDATE

Service DEL key rồi UPDATE giá trong DB, nhưng giao dịch DB cuối cùng rollback.

**Câu hỏi:** Có phải mất dữ liệu gốc không? Vấn đề nhất quán là gì?

**Gợi ý:** Không nhất thiết mất dữ liệu gốc; Redis bị miss và có thể nạp lại giá cũ. Vấn đề chính là khó phối hợp thứ tự, tăng tải và race nạp cache; không có atomicity tự động giữa hai hệ.

### Bài F — Read replica sau ghi

API ghi đơn đã COMMIT trên primary, sau đó GET trên replica trả trạng thái cũ.

**Câu hỏi:** Có chứng minh COMMIT thất bại không?

**Gợi ý:** Không. Replica có thể trễ. Read-your-writes cần đọc nguồn authoritative hoặc cơ chế đồng bộ replica theo hợp đồng.

### Bài G — Khi quyền bị thu hồi

Hệ thống cache quyền truy cập 10 phút; quản trị viên vừa thu hồi quyền, nhưng cache vẫn báo true.

**Câu hỏi:** Vì sao không thể đánh đồng với cache trang sản phẩm?

**Gợi ý:** Quyền stale có thể gây sự cố bảo mật. Cần chính sách freshness nghiêm ngặt hoặc fail-closed, không chỉ tối ưu hit rate.

### Bài H — Outbox bảo đảm gì?

DB commit giá mới và outbox event. Dispatcher chết, rồi restart phát event hai lần.

**Câu hỏi:** Outbox giải quyết vấn đề gì, và những vấn đề nào còn lại?

**Gợi ý:** Intent không mất sau commit; consumer cần idempotency. Cache vẫn có cửa sổ stale, event có thể đến trùng/sai thứ tự, loader có thể tái tạo entry cũ sau DEL. Cần version/TTL/monitoring theo hợp đồng.

## 21. Checklist trước khi đưa cache vào production

- [ ] Mỗi loại dữ liệu có chủ sở hữu/nguồn chuẩn được xác định rõ.
- [ ] Đã phân biệt cache, read replica, materialized view và search index theo mốc cập nhật.
- [ ] Đã xác định use case được chấp nhận stale và use case phải kiểm tra nguồn chuẩn.
- [ ] Cache key bao gồm tenant, identity/scope, schema version và biến thể dữ liệu khi cần.
- [ ] Không dùng giá trị tồn kho/số dư/permission stale làm quyết định nghiệp vụ cuối cùng.
- [ ] Có TTL và chính sách eviction phù hợp, không coi TTL là bảo đảm fresh.
- [ ] Đã xác định đường ghi DB, thứ tự invalidate và race cache miss nạp lại bản cũ.
- [ ] Nếu dùng version/CAS, đã kiểm tra tình huống cache key bị xóa và sự kiện sai thứ tự.
- [ ] Nếu invalidation bắt buộc phục hồi sau crash, có outbox/worker và theo dõi backlog.
- [ ] Không coi @CacheEvict hoặc callback afterCommit là một transaction phân tán.
- [ ] Có fallback/backpressure khi cache lỗi, không làm source DB bị stampede.
- [ ] Nếu dùng L1/L2/CDN, đã xét invalidation và TTL trên từng tầng.
- [ ] Negative cache chỉ được tạo sau kết quả not-found xác nhận, với TTL hợp lý.
- [ ] Tất cả thay đổi nghiệp vụ quan trọng được xác nhận ở nguồn authoritative.
- [ ] Có metrics hit/miss, entry age, invalidation lag, version mismatch và DB load.
- [ ] Có kiểm thử crash, concurrent loader, duplicate/out-of-order event và cách xử lý stale.
- [ ] Có đường rebuild cache từ nguồn chuẩn khi cache bị xóa/mất/hỏng.

**Ghi nhớ:** cache giúp tăng tốc **đọc dữ liệu**, nhưng không tự trở thành nguồn quyết định **dữ liệu nào là đúng**. Người thiết kế persistence trong Java phải phân biệt commit của nguồn chuẩn với việc bản sao đã cập nhật, chỉ rõ mức stale được phép, giải quyết invalidation race và đặt những bất biến quan trọng tại ranh giới giao dịch được bảo vệ. Một cache có thể bị xóa và xây lại an toàn chính là dấu hiệu tốt cho thấy vai trò nguồn chuẩn và dữ liệu lưu đệm đã được phân định đúng.
