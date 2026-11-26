# Thiết kế kích thước tài liệu và tránh cấu trúc tăng không giới hạn trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **giới hạn kích thước tối đa của Couchbase** với **ngân sách kích thước document** nên đặt ở tầng ứng dụng.
2. Nhận diện các cấu trúc tăng không giới hạn như lịch sử giao dịch, `reviews`, `events`, `notifications`, danh sách người theo dõi và `Map` có key động.
3. Chọn **nhúng hữu hạn**, **tham chiếu bằng document key**, **tách collection** hoặc **chia nhỏ theo phân đoạn (bucketed/chunked documents)** theo mẫu truy cập.
4. Thiết kế entity Spring Data Couchbase, repository, `CouchbaseTemplate` và SQL++ để đọc nhanh dữ liệu cốt lõi, phân trang dữ liệu tăng trưởng.
5. Hiểu giới hạn của **sub-document operations**, array index, CAS, TTL, transaction và reactive API đối với kích thước document và cạnh tranh ghi.
6. Thiết lập chỉ số theo dõi, quy trình migration và kiểm thử tải để tránh phát hiện lỗi “document quá lớn” khi hệ thống đã vận hành.

Bài thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**. Spring Data Couchbase ánh xạ Java object thành JSON trong bucket/scope/collection và cho phép truy cập qua repository, `CouchbaseTemplate`, Key-Value (KV) và SQL++. Khả năng nhúng object, list, set và map rất tiện, nhưng sự tiện lợi đó không đồng nghĩa với việc mọi dữ liệu liên quan nên được đưa mãi vào **một document**.

## 1. Kích thước document: ngưỡng kỹ thuật không phải mục tiêu thiết kế

Theo tài liệu Couchbase Server hiện hành, **giá trị của một item (document JSON hoặc binary) có kích thước tối đa 20 MiB**, tương đương **20.971.520 byte**. Giới hạn này áp dụng cho giá trị document, không có nghĩa ứng dụng nên thường xuyên ghi document gần 20 MiB. Trong các cấu hình nén SDK/Server, giới hạn vẫn phải được thỏa mãn theo quy định đối với nội dung trước/sau nén; **nén không phải cách vượt giới hạn document**.

Nguồn: [Couchbase Server — Items, Keys and Values](https://docs.couchbase.com/server/current/learn/data/data.html), [Java SDK — Compression](https://docs.couchbase.com/java-sdk/current/concept-docs/compression.html).

Với ứng dụng thực tế, **ngân sách nội bộ** nên nhỏ hơn nhiều và được kiểm chứng bằng đo đạc. Ví dụ một API catalog có thể thử đặt mục tiêu p95 document dưới 64 KiB, cảnh báo khi vượt 256 KiB và rà soát thiết kế khi document vượt 1 MiB. **Đây là ví dụ SLO do nhóm tự chọn, không phải giới hạn mặc định hoặc khuyến cáo tuyệt đối của Couchbase.** Nội dung chứa dữ liệu hình ảnh/base64 hay payload chuyên biệt có thể cần ngân sách khác.

### 1.1. Tại sao chưa đạt 20 MiB vẫn có thể quá lớn?

| Tác động | Một document nhỏ, ổn định | Một document lớn và tiếp tục tăng |
| --- | --- | --- |
| **KV get** | Truyền ít byte và ít đối tượng để decode | Đọc cả document dù màn hình chỉ cần vài field |
| **KV replace/save** | Serialize và truyền payload vừa phải | Ghi lại body lớn khi chỉ đổi một thuộc tính |
| **Java mapping** | Tạo số lượng object có kiểm soát | Dùng nhiều heap, CPU, GC khi dựng list/map lớn |
| **Network** | Ít băng thông và độ trễ thấp hơn | Phụ thuộc băng thông, nén, timeout, kích thước frame |
| **Replica/persistence** | Chi phí xử lý theo khối lượng vừa phải | Mutation lớn tăng áp lực sao chép và lưu trữ |
| **Index** | Ít field/array entry cần duy trì | Array index có thể phát sinh nhiều index entries |
| **CAS** | Cập nhật root ít xung đột nếu số writer thấp | Nhiều writer sửa các phần khác nhau vẫn đụng cùng root |
| **Client/UI** | Pagination đơn giản khi dữ liệu ít | Chỉ để hiển thị 20 phần tử mà tải hàng nghìn phần tử |

**Không nhầm kích thước JSON với số lượng phần tử**. Một mảng 100 object có thể lớn hơn mảng 10.000 số nguyên; cùng một số ký tự Java cũng không nhất thiết cùng số byte UTF-8. Các ký tự tiếng Việt, chuỗi dài và tên field lặp lại đều đóng góp vào kích thước sau serialize.

### 1.2. Document key, JSON body và index là các loại chi phí khác nhau

- **Document key:** định danh một document trong collection; không phải một field JSON bắt buộc.
- **JSON body:** phần value có giới hạn 20 MiB.
- **CAS/expiry:** metadata của document, không tự tạo giới hạn riêng cho từng object con.
- **Index entries:** cấu trúc phụ do Index Service quản lý, không được “trừ” khỏi 20 MiB body; tuy nhiên chúng làm tăng tổng lưu trữ và chi phí mutation.

Kích thước file JSON từ hệ thống xuất dữ liệu không phải luôn bằng payload thực tế do converter Spring Data gửi đi; cần đo trên biểu diễn JSON đã serialize hoặc đọc lại bằng SDK phù hợp.

## 2. Tại sao một cấu trúc tăng không giới hạn là lỗi thiết kế?

Một danh sách là **tăng không giới hạn** khi số phần tử không có giới hạn tin cậy dựa trên nghiệp vụ hoặc retention. Dù hôm nay mới có vài phần tử, hệ thống không biết đâu là kích thước lớn nhất sau một năm.

Ví dụ một Product:

~~~json
{
  "display_name": "Cà phê hạt 250 g",
  "price_vnd": 150000,
  "reviews": [
    {"reviewerId":"u100","rating":5,"comment":"Sản phẩm tốt"},
    {"reviewerId":"u101","rating":4,"comment":"Giao nhanh"}
  ]
}
~~~

Mỗi khi có đánh giá mới, code gọi `product.getReviews().add(...)` rồi `repository.save(product)`. Cách viết ban đầu đơn giản, nhưng review là dữ liệu **nhiều người cùng tạo**, tăng theo thời gian và thường cần phân trang, kiểm duyệt, xóa riêng.

Vấn đề không chỉ là document lớn lên: mọi writer cập nhật cùng Product sẽ cùng tranh chấp **một document key/CAS** và việc đọc thông tin giá hiện tại phải xử lý cả các review không cần thiết.

~~~mermaid
flowchart TB
    P["Product"] --> R["reviews[] tiếp tục tăng"]
    R --> S["Document body tăng"]
    S --> N["Đọc/ghi truyền nhiều byte"]
    S --> H["Mapping / heap / GC tăng"]
    S --> I["Array index nhiều phần tử"]
    R --> C["Nhiều writer cùng một CAS"]
    N --> L["Latency tăng"]
    H --> L
    I --> L
    C --> L
~~~

### 2.1. Ước lượng tăng trưởng bằng số liệu, không bằng cảm giác

Một mô hình sơ bộ:

`documentBytes ≈ baseBytes + count × averageEntryBytes + JSONOverheadBytes`

Giả sử:

- Root Product trung bình 2.000 byte.
- Mỗi review sau serialize trung bình **500 byte**, gồm tên field, chuỗi và dấu phân cách.
- Sau 10.000 review, riêng review chiếm khoảng 5.000.000 byte (~4,77 MiB), chưa tính metadata khác, nhiều review dài bất thường và index.

Đây là **phép ước lượng minh họa**. Kích thước thật phân phối không đều; cần đo **p50, p95, p99 và max** cho từng loại document. Ngay cả ở mức chưa tới giới hạn 20 MiB, một document vài MiB đã có thể không phù hợp với API chỉ cần tên và giá.

### 2.2. Các trường hợp dễ tăng âm thầm

| Cấu trúc nhúng | Vì sao tăng? | Hướng thiết kế nên đánh giá |
| --- | --- | --- |
| `Product.reviews[]` | Mỗi lượt khách đánh giá | Review thành document độc lập, index theo `product_id` |
| `Customer.orders[]` | Đơn hàng tích lũy suốt vòng đời | Order độc lập, field `customer_id`, query phân trang |
| `User.notifications[]` | Hệ thống gửi thông báo liên tục | Notification riêng hoặc phân đoạn theo thời gian |
| `Device.telemetry[]` | Mỗi giây thêm số đo | Event/chuỗi thời gian riêng, phân vùng và retention |
| `Account.transactions[]` | Giao dịch không ngừng phát sinh | Transaction/ledger document riêng, không nhúng vào tài khoản |
| `Product.stockMovements[]` | Nhập/xuất kho liên tục | Movement riêng; tổng tồn là state nhỏ được kiểm soát |
| `Order.events[]` | Nhiều workflow/event phát sinh | Chỉ nhúng nếu workflow có số bước **thực sự hữu hạn** |
| `Map<String,Object> properties` | Mọi tác nhân tạo key mới | Đặt whitelist, giới hạn số key, chuẩn hóa hoặc tách document |
| `Cart.lines[]` | Người dùng thêm hàng | Có thể nhúng, **nhưng phải có giới hạn số dòng và payload** |

Một mảng nhỏ hôm nay không chứng minh nó sẽ mãi nhỏ. Tiêu chí đúng là **đặc tính tăng trưởng theo miền nghiệp vụ**, không phải kích thước dữ liệu thử nghiệm.

## 3. Quyết định nhúng hay tách document theo workload

Nhúng vẫn là lựa chọn tốt khi phần dữ liệu:

1. Được **đọc cùng root** trong phần lớn request.
2. Có **vòng đời gắn với root**, không cần quyền sửa/xóa riêng.
3. Có **giới hạn cardinality** đáng tin cậy và giới hạn byte.
4. Có invariant phải cập nhật cùng root, phù hợp một mutation/CAS.

Ngược lại, tách document khi phần dữ liệu có thể tăng dài hạn, được phân trang, có TTL khác, nhiều writer độc lập hoặc được truy cập riêng.

| Tiêu chí | Nhúng hữu hạn | Reference/document riêng |
| --- | --- | --- |
| Đọc chi tiết root | Một KV get lấy đủ | Có thể cần thêm KV hoặc SQL++ |
| Phân trang con | Thường không cần, mảng nhỏ | Tự nhiên và hiệu quả hơn |
| Sửa nhiều phần con độc lập | Tranh chấp root CAS | Các document độc lập giảm tranh chấp |
| Dung lượng tối đa | Phụ thuộc mảng lồng | Root ít tăng, mỗi child có kích thước riêng |
| TTL riêng cho child | Không có TTL riêng trong body | Mỗi document có thể có expiry riêng |
| Index theo con | Có thể cần array index | Field/index đơn giản trên child |
| Số lần đọc | Ít hơn khi luôn cần tất cả con | Nhiều hơn nếu phải tải nhiều child |
| Consistency | Một mutation root nguyên tử | Cần xử lý consistency giữa nhiều document |

**Bài toán không phải “nhúng hay tham chiếu tuyệt đối”**. Một Product thường hợp lý với **thông tin tóm tắt nhúng** + **khóa của vài review nổi bật** + **toàn bộ Review độc lập**.

## 4. Mô hình đề xuất: Product nhỏ, Review độc lập và read summary

### 4.1. Phân tách data model

Thiết kế ba lớp thông tin:

- **Product root** trong `shop.catalog.products`: tên, giá, trạng thái bán, một vài URL ảnh, tối đa 5 khóa review nổi bật và dữ liệu tổng hợp nhỏ.
- **Review** trong `shop.engagement.reviews`: mỗi đánh giá có key, `product_id`, người viết, điểm đánh giá, nội dung, thời gian và trạng thái kiểm duyệt.
- **ReviewSummary** nhúng trong Product: `count`, `average_rating` hoặc giá trị tổng hợp phù hợp, có chính sách cập nhật lại khi Review thay đổi.

~~~mermaid
flowchart LR
    A["Product document<br/>nhỏ, đọc KV"] --> B["review_summary"]
    A --> C["highlight_review_ids<br/>tối đa 5"]
    C -.->|"reference"| D["Review documents"]
    E["Reviews theo product_id<br/>SQL++ + index"] --> D
~~~

JSON Product minh họa:

~~~json
{
  "display_name": "Cà phê hạt 250 g",
  "price_vnd": 150000,
  "active": true,
  "highlight_review_ids": [
    "review::a001",
    "review::a120"
  ],
  "review_summary": {
    "count": 12580,
    "average_rating": 4.7
  }
}
~~~

Review `review::a120`:

~~~json
{
  "product_id": "product::coffee250",
  "reviewer_id": "customer::u100",
  "rating": 5,
  "body": "Đóng gói cẩn thận, hương thơm rõ",
  "status": "PUBLISHED",
  "created_at": "2026-11-25T08:00:00Z"
}
~~~

`review_summary.count` là **số lượng Review được tổng hợp**, không phải số phần tử trong mảng JSON. Khi nhiều Review được thêm, **Product không phải phình theo số Review**.

### 4.2. Mối quan hệ với tính nhất quán

Nếu Review được lưu trước rồi Product summary cập nhật sau:

- Có một khoảng thời gian `count` chưa phản ánh Review mới.
- Một lỗi cập nhật summary có thể làm số đếm chênh lệch.
- Hai writer sửa summary đồng thời có thể xung đột CAS hoặc ghi đè số đếm.

Vì vậy phải định nghĩa **nguồn sự thật** (Review documents), mức chấp nhận độ trễ của summary, cách retry/idempotency, và công việc **rebuild summary** nếu lệch. Chỉ dùng transaction đa document khi bất biến nghiệp vụ thực sự đòi hỏi đồng bộ nguyên tử.

Không giữ hàng nghìn khóa Review trong `highlight_review_ids`; nếu cần mọi ID, chính Review collection + index đã là công cụ truy cập phù hợp.

## 5. Entity Spring Data Couchbase: giới hạn tại aggregate root

Ví dụ Java 17+, tên package và collection minh họa.

### 5.1. Product.java

~~~java
package com.example.shop.catalog;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public class Product {

    private static final int MAX_HIGHLIGHTED_REVIEWS = 5;

    @Id
    private String id;

    @Version
    private Long version;

    @Field("display_name")
    private String displayName;

    @Field("price_vnd")
    private long priceVnd;

    @Field("highlight_review_ids")
    private List<String> highlightReviewIds = new ArrayList<>();

    protected Product() {}

    public Product(String id, String displayName, long priceVnd) {
        if (id == null || id.isBlank()
                || displayName == null || displayName.isBlank()
                || priceVnd < 0) {
            throw new IllegalArgumentException("Product không hợp lệ");
        }
        this.id = id;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
    }

    public void highlightReview(String reviewId) {
        if (reviewId == null || reviewId.isBlank()) {
            throw new IllegalArgumentException("Review ID không hợp lệ");
        }
        if (highlightReviewIds.contains(reviewId)) {
            return; // idempotent nếu ID đã có.
        }
        if (highlightReviewIds.size() >= MAX_HIGHLIGHTED_REVIEWS) {
            throw new IllegalStateException("Đạt giới hạn review nổi bật");
        }
        highlightReviewIds.add(reviewId);
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }
    public List<String> getHighlightReviewIds() {
        return List.copyOf(highlightReviewIds);
    }
}
~~~

Cấu trúc này **không có `List<Review> reviews`**. Nó cố tình chỉ giữ tối đa 5 khóa, làm trường nhúng có cardinality hữu hạn. Các ràng buộc trong phương thức miền phục vụ **đường ghi của ứng dụng**; dữ liệu do SDK/SQL++ khác ghi vẫn cần được kiểm tra khi đọc hoặc qua quy trình validation riêng.

`@Version` dùng CAS của root để ngăn ghi đè khi hai request cùng thay đổi danh sách nổi bật. Một lần `save(product)` là mutation document Product, không tạo transaction với document Review tương ứng.

### 5.2. ProductReview.java

~~~java
package com.example.shop.engagement;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("engagement")
@Collection("reviews")
public class ProductReview {

    @Id
    private String id;

    @Field("product_id")
    private String productId;

    @Field("reviewer_id")
    private String reviewerId;

    @Field
    private int rating;

    @Field
    private String body;

    @Field("created_at")
    private Instant createdAt;

    protected ProductReview() {}

    public ProductReview(
            String id, String productId, String reviewerId,
            int rating, String body, Instant createdAt) {
        if (id == null || id.isBlank() ||
                productId == null || productId.isBlank() ||
                reviewerId == null || reviewerId.isBlank() ||
                rating < 1 || rating > 5 ||
                body == null || body.length() > 2000 ||
                createdAt == null) {
            throw new IllegalArgumentException("Review không hợp lệ");
        }
        this.id = id;
        this.productId = productId;
        this.reviewerId = reviewerId;
        this.rating = rating;
        this.body = body;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getProductId() { return productId; }
    public Instant getCreatedAt() { return createdAt; }
    public int getRating() { return rating; }
    public String getBody() { return body; }
}
~~~

Giới hạn 2.000 ký tự là **quy tắc minh họa**, không phải giới hạn của Couchbase. Nếu cần kiểm soát kích thước **theo byte**, hãy tính UTF-8 sau serialize hoặc áp ngân sách byte riêng, vì `String.length()` đo đơn vị UTF-16 chứ không phải số byte JSON.

### 5.3. Repository và service

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {
}

public interface ProductReviewRepository
        extends CouchbaseRepository<ProductReview, String> {
}
~~~

Ví dụ tạo Review với key phát sinh ở service:

~~~java
import java.time.Instant;
import java.util.UUID;

public ProductReview createReview(
        String productId, String reviewerId, int rating, String body) {
    ProductReview review = new ProductReview(
        "review::" + UUID.randomUUID(),
        productId,
        reviewerId,
        rating,
        body,
        Instant.now()
    );
    return reviewRepository.save(review);
}
~~~

**Lưu ý:** `save` ở ví dụ chỉ diễn tả ghi entity; với event/review phải có ngữ nghĩa chống tạo trùng, kiểm tra quyền người viết, chống spam và idempotency. Nếu một request HTTP được retry, sinh UUID mới mỗi lần sẽ có thể tạo hai Review giống nhau. Thiết kế key theo yêu cầu duy nhất hoặc idempotency token phù hợp.

Nếu cần chắc chắn Product tồn tại, đọc Product theo ID trước khi tạo Review; nhưng kiểm tra và ghi là hai bước khác nhau, không tự tạo foreign key. Nếu nghiệp vụ yêu cầu nhất quán mạnh giữa nhiều document, chọn transaction/workflow phù hợp.

## 6. Truy vấn Review theo Product thay vì nhúng vào Product

Khi biết `productId`, trang chi tiết Product có thể:

1. Đọc Product bằng `findById(productId)`: thường là **KV**, không cần secondary index.
2. Đọc một trang Review từ collection `shop.engagement.reviews`, lọc theo `product_id`.
3. Lấy Review nổi bật theo một số ID đã biết nếu giao diện cần.
4. Render hai luồng dữ liệu riêng; không phải trả cả danh sách review từ Product JSON.

SQL++:

~~~sql
SELECT META(r).id AS reviewKey,
       r.rating,
       r.body,
       r.created_at AS createdAt
FROM `shop`.`engagement`.`reviews` AS r
WHERE r.product_id = $productId
ORDER BY r.created_at DESC, META(r).id DESC
LIMIT 20;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_reviews_product_time
ON `shop`.`engagement`.`reviews`(
    product_id,
    created_at DESC,
    META().id DESC
);
~~~

`META(r).id` dùng làm **tie-breaker** khi nhiều Review có cùng timestamp; điều này giúp thứ tự nhất quán khi phân trang. Không coi index trên là công thức tối ưu trong mọi môi trường: hãy dùng `EXPLAIN`, kiểm tra planner và workload, quyền truy cập, kích thước và chi phí index. Nếu query phải lọc `status="PUBLISHED"`, cân nhắc đưa điều kiện này vào thiết kế index phù hợp.

### 6.1. Pagination: OFFSET dễ tốn chi phí với trang sâu

~~~sql
SELECT META(r).id AS reviewKey, r.created_at
FROM `shop`.`engagement`.`reviews` AS r
WHERE r.product_id = $productId
ORDER BY r.created_at DESC, META(r).id DESC
LIMIT 20 OFFSET 10000;
~~~

Truy vấn trang sâu với `OFFSET` có thể yêu cầu xử lý nhiều hàng trước khi bỏ 10.000 hàng. Khi dữ liệu lớn, chọn **keyset/cursor pagination** dựa trên khóa sắp xếp ổn định:

~~~sql
SELECT META(r).id AS reviewKey,
       r.rating, r.body, r.created_at AS createdAt
FROM `shop`.`engagement`.`reviews` AS r
WHERE r.product_id = $productId
  AND (
        r.created_at < $cursorCreatedAt
        OR (
            r.created_at = $cursorCreatedAt
            AND META(r).id < $cursorId
        )
      )
ORDER BY r.created_at DESC, META(r).id DESC
LIMIT 20;
~~~

Đối với **trang đầu**, bỏ điều kiện cursor. Đối với trang sau, lưu timestamp và key của mục cuối đã trả. Cách này giảm tác động của OFFSET sâu, nhưng khi Review mới được thêm/xóa giữa các trang vẫn cần hợp đồng pagination rõ ràng. Phân trang không thay thế yêu cầu phân quyền và giới hạn `LIMIT` do server định nghĩa.

### 6.2. SQL++ và consistency

SQL++ thường sử dụng index để lọc/sắp xếp. Sau khi tạo Review mới, một query theo `product_id` có thể chưa thấy Review ngay nếu index chưa cập nhật và bạn dùng mức scan consistency mặc định. Nếu cần read-your-own-write, cân nhắc lấy theo document key vừa tạo hoặc cấu hình query consistency phù hợp; đo tác động latency.

**Không đặt toàn bộ Review trở lại Product chỉ để che độ trễ query.** Thay vào đó xác định UX, consistency và mục tiêu cập nhật chỉ mục.

## 7. Một số dữ liệu vẫn nên nhúng, nhưng phải có giới hạn

Nhúng không phải anti-pattern. Ví dụ:

- `Order.lines` khi nghiệp vụ giới hạn tối đa 50 dòng và mọi dòng được chốt cùng Order.
- `Product.imageUrls` với tối đa 8 URL, không nhúng ảnh nhị phân/base64 vào JSON.
- `Catalog.tags` với tối đa 20 tag đã chuẩn hóa.
- `Cart.lines` với số dòng và TTL có trần rõ ràng.
- `ShippingAddress` là một value object kích thước nhỏ, đọc cùng đơn hàng.

Nhưng giới hạn phải được thực hiện **đúng điểm ghi dữ liệu**, không chỉ ghi trong tài liệu thiết kế.

### 7.1. Giới hạn số phần tử và tổng số byte

Ví dụ chính sách domain:

~~~java
public void addImageUrl(String url) {
    if (url == null || url.isBlank() || url.length() > 300) {
        throw new IllegalArgumentException("URL không hợp lệ");
    }
    if (imageUrls.size() >= 8) {
        throw new IllegalStateException("Tối đa 8 ảnh");
    }
    imageUrls.add(url);
}
~~~

Đây là kiểm tra cơ bản nhưng chưa đủ nếu object khác chứa chuỗi rất dài. Một API có thể đặt **giới hạn body byte** trước khi ghi, sau khi tính cả field names và các object lồng nhau. Vì JSON encoding, escape và `_class` do mapper thêm có thể làm tăng byte, dự toán phải có khoảng dự phòng.

Không ghi logic `if (jsonBytes < 20 * 1024 * 1024)` rồi coi hệ thống đã an toàn. Thường cần ngưỡng ứng dụng nhỏ hơn nhiều, cảnh báo sớm và hành vi từ chối có thông báo rõ (HTTP 413 hoặc lỗi validation phù hợp với contract).

### 7.2. Giới hạn trên phải độc lập với số người dùng

Một Product có tối đa 8 ảnh **bất kể số khách** là bounded. Một Product có “tối đa một Review mỗi người dùng” vẫn **unbounded** khi lượng người dùng không có trần. Một User chứa “tối đa một notification mỗi ngày” vẫn tăng tuyến tính theo thời gian nếu không có retention.

**Đừng đánh đồng “mỗi người dùng một phần tử” với “mảng có kích thước tối đa hữu hạn ở cấp document”.**

## 8. Sub-document operations: giảm payload, không biến mảng vô hạn thành an toàn

Couchbase Java SDK hỗ trợ `lookupIn` và `mutateIn` để đọc/ghi **một phần document** mà không phải gửi toàn bộ body qua mạng. Ví dụ:

~~~java
import java.util.List;
import com.couchbase.client.java.Collection;
import static com.couchbase.client.java.kv.MutateInSpec.arrayAppend;

Collection products = cluster.bucket("shop")
    .scope("catalog").collection("products");

products.mutateIn(
    "product::coffee250",
    List.of(arrayAppend("highlight_review_ids", "review::a120"))
);
~~~

Lợi ích:

- Request có thể mang chỉ các thay đổi tại đường dẫn cụ thể.
- Nhiều mutation sub-document trong **một** `mutateIn` trên cùng document có tính nguyên tử chung; nếu một thành phần thất bại, document không bị áp các thay đổi còn lại.
- Với các thao tác mảng như `arrayAppend`, server có thể xử lý đồng thời mà không cần vòng đọc–ghi toàn bộ document và tránh kiểu mất update do ghi đè snapshot cũ.

Nhưng **không giải quyết** các vấn đề:

1. **Giới hạn 20 MiB vẫn áp dụng cho document sau mutation.**
2. `arrayAppend` không tự giới hạn 5 phần tử, 10.000 phần tử hay số byte; nếu thao tác nhiều lần, mảng vẫn tăng.
3. `arrayAppend` không thay thế invariant phức tạp của aggregate. Để giới hạn cứng hoặc duy nhất, cần thiết kế điều kiện/transaction/CAS hoặc mô hình lưu khác.
4. Các update sub-document vẫn làm **CAS document thay đổi**; entity Spring Data đã load trước đó có thể bị stale khi `save`.
5. Nếu root vẫn rất lớn, truy vấn toàn bộ/serialize toàn bộ/root hot key vẫn là vấn đề, dù một mutation tiết kiệm network.

**Trong ví dụ này, phương thức `highlightReview` trên entity có giới hạn 5 ID, nhưng `mutateIn(arrayAppend)` gọi trực tiếp sẽ vượt qua kiểm tra của entity.** Vì vậy không nên phối hợp hai đường ghi mà không có cơ chế cưỡng chế chung. Dùng sub-document cho thuộc tính giới hạn chỉ khi có kiểm soát đồng thời và bảo đảm giới hạn ở phía lưu trữ/ứng dụng.

Tham khảo: [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html).

### 8.1. Khi nào dùng sub-document hợp lý?

- Cập nhật một cờ `active`, bộ đếm, hoặc một nhánh JSON nhỏ trên document có cấu trúc **hữu hạn**.
- Cập nhật nhiều field lồng nhau trong một mutation nguyên tử mà không truyền body đầy đủ.
- Kiểm soát CAS hoặc sự cạnh tranh ghi bằng thao tác phù hợp với nghiệp vụ.

Khi cần ghi một nhật ký gồm hàng triệu phần tử, **sub-document không phải giải pháp chính**. Tách các event thành document riêng thường dễ vận hành hơn.

## 9. CAS và hot document khi nhiều writer cùng tăng một mảng

Giả sử 100 request thêm Review vào `product::coffee250`:

~~~text
Request A --- load Product CAS=10 --- append --- save CAS=10
Request B --- load Product CAS=10 --- append --- save CAS=10
Request C --- load Product CAS=10 --- append --- save CAS=10
...
~~~

Khi `@Version` được cấu hình đúng, chỉ một số cập nhật phù hợp phiên bản mới có thể thành công; các writer còn lại phải xử lý `OptimisticLockingFailureException` và đọc lại. Nếu không có kiểm tra CAS và các writer ghi nguyên document từ snapshot cũ, những Review mới có thể **bị ghi đè**.

Chuyển Review thành document riêng giúp phân tán thao tác ghi theo key Review khác nhau; tuy nhiên vẫn có thể có **điểm nóng** nếu mọi Review đều buộc cập nhật một counter/tổng hợp trong Product ngay lập tức.

Cách giảm hot spot:

- Viết Review độc lập với key được tạo có kiểm soát.
- Tính tổng hợp từ luồng event hoặc xử lý bất đồng bộ với idempotency.
- Nếu cần truy cập số liệu cập nhật thường xuyên, cân nhắc cơ chế counter hoặc phân đoạn theo key, đo độ chính xác/độ trễ.
- Nếu invariant yêu cầu chính xác mạnh, lựa chọn transaction/thiết kế aggregate phải phù hợp; không chấp nhận stale summary một cách im lặng.

**CAS giúp ngăn mất cập nhật, nhưng không khiến cấu trúc tăng vô hạn trở nên hiệu quả.**

## 10. Chia nhỏ thành document theo phân đoạn khi cần đọc theo nhóm

Đôi khi workload cần **một nhóm event gần nhau** mỗi lần đọc và có thể chấp nhận lưu nhiều event vào một document nhỏ, hữu hạn. Khi ấy có thể dùng **bucketed/chunked documents**.

Ví dụ telemetry của thiết bị:

~~~text
telemetry::device42::2026-11-25T08:00::part-000
telemetry::device42::2026-11-25T08:00::part-001
telemetry::device42::2026-11-25T08:01::part-000
~~~

Body một chunk:

~~~json
{
  "device_id": "device42",
  "window_start": "2026-11-25T08:00:00Z",
  "part": 0,
  "samples": [
    {"at":"2026-11-25T08:00:01Z","value":23.4},
    {"at":"2026-11-25T08:00:02Z","value":23.6}
  ],
  "sample_count": 2
}
~~~

Mỗi chunk phải có giới hạn **thời gian, số mẫu hoặc byte**; ví dụ tối đa 500 mẫu **và** 256 KiB body, tùy workload. Khi chunk đạt giới hạn, writer chuyển sang chunk tiếp theo thay vì tiếp tục append.

### 10.1. Đổi lại những khó khăn nào?

- Cần chọn `part` hoặc khóa chunk mới khi cạnh tranh ghi; nhiều writer có thể cùng nghĩ `part-000` đã đầy rồi tạo `part-001`.
- Cần bảo vệ idempotency để một mẫu không bị ghi hai lần sau retry.
- Cần index/truy vấn theo `device_id` và `window_start` hoặc cơ chế tra cứu chunk theo key, tùy lịch sử truy cập.
- TTL của chunk là **TTL toàn document**; dữ liệu trong chunk phải có cùng chính sách retention.
- Một hot chunk có thể vẫn trở thành hot key. Khi throughput quá cao, mô hình **một event một document** hoặc hệ thống event/time-series chuyên dụng có thể phù hợp hơn.

Chunking không có nghĩa kích thước được quản lý tự động. Tài liệu thiết kế phải quy định **điều kiện đóng chunk**, quyền tạo chunk mới và cách truy xuất đủ các chunk theo thứ tự.

## 11. TTL và retention: giới hạn tăng trưởng theo thời gian

Đặt TTL ở cấp document có thể giúp xóa dữ liệu tạm, nhưng không giải quyết một mảng lịch sử nằm **bên trong document lâu dài**.

Ví dụ:

- **Cart:** toàn giỏ có thể hết hạn sau một giờ; các dòng Cart có cùng vòng đời.
- **Notification:** từng thông báo có retention 30 ngày; nếu tất cả thông báo nằm trong User document không hết hạn, TTL của User không thể xóa từng thông báo.
- **Telemetry:** mỗi event/chunk có retention theo ngày; chia document riêng để áp expiry phù hợp.

~~~java
@Document(expiry = 3600)
@Scope("sales")
@Collection("carts")
public class Cart {
    @Id
    private String id;
    @Field
    private List<CartLine> lines;
}
~~~

`@Document(expiry = 3600)` là ví dụ TTL **ở document Cart** theo semantics/configuration của Spring Data Couchbase. Không có nghĩa mỗi `CartLine` hết hạn riêng; cập nhật document có thể liên hệ với chính sách expiry khác nhau tùy đường ghi và phiên bản SDK/Server, nên cần kiểm thử rõ.

### 11.1. TTL khác logic nghiệp vụ hết hạn

Nếu một coupon trong Cart chỉ có hiệu lực tới 10:00 còn Cart sống tới 11:00, bạn phải:

- Lưu thời gian hiệu lực trong dữ liệu và kiểm tra khi tính giá; hoặc
- Lưu thông tin coupon ở document có lifecycle độc lập với expiry phù hợp.

TTL làm document hết hạn ở tầng lưu trữ, **không thay cho kiểm tra điều kiện nghiệp vụ** vào thời điểm thanh toán.

### 11.2. Archive trước khi xóa

Đối với dữ liệu phải lưu giữ vì audit hoặc tuân thủ, xóa theo TTL chưa chắc được phép. Có thể cần:

1. Chuyển dữ liệu sang nơi lưu dài hạn được phê duyệt;
2. Đối chiếu đầy đủ, bảo toàn key/timestamp/metadata cần thiết;
3. Chỉ sau đó xóa khỏi collection phục vụ online hoặc đặt expiry.

Không đẩy dữ liệu sang archive bằng một công việc không có kiểm tra/đối chiếu rồi giả định dữ liệu đã an toàn.

## 12. Kích thước JSON và giới hạn tài nguyên trong Java

### 12.1. Đo theo byte UTF-8, không theo String.length()

Ví dụ một JSON object có text tiếng Việt:

~~~json
{"display_name":"Cà phê hạt"}
~~~

Số ký tự hiển thị và số byte UTF-8 khác nhau. `String.length()` ở Java đo số đơn vị UTF-16; không phải số byte mà Couchbase nhận.

Một phép **ước lượng** khi có JSON string:

~~~java
import java.nio.charset.StandardCharsets;

String json = objectMapper.writeValueAsString(productDto);
int approximateBytes = json.getBytes(StandardCharsets.UTF_8).length;

if (approximateBytes > 256 * 1024) {
    throw new IllegalArgumentException("Payload vượt ngân sách");
}
~~~

Đoạn này giả định service có `objectMapper` Jackson và DTO tương ứng. **Đây chỉ là ước lượng**: Jackson và Couchbase converter có thể sinh JSON body khác nhau (ví dụ `_class`, tên `@Field`, field bị bỏ qua). Để bảo đảm ngân sách ở đúng đường ghi, dùng codec/serialization path thực tế hoặc đo JSON body đã được ghi; để khoảng dự phòng.

Ngoài tổng byte, theo dõi **số node/độ sâu nesting** nếu đối tượng có thể do người dùng kiểm soát. JSON lồng sâu và collection phức tạp có thể tốn CPU/stack khi parse và gây rủi ro DoS ứng dụng ngay cả khi dưới 20 MiB.

### 12.2. Tránh base64 ảnh trong Product JSON

Không nên lưu ảnh 2 MiB dưới dạng chuỗi base64 trong `Product.image` nếu màn hình catalog chỉ cần URL/thumbnail. Base64 làm payload phình hơn dữ liệu nhị phân gốc, mọi lần đọc Product phải mang thêm dữ liệu ảnh và tăng áp lực memory.

Lưu ảnh trong object storage/CDN hoặc hệ thống phù hợp, rồi ghi **khóa/URL/tên asset** cùng metadata nhỏ trong Product. Nếu cần lưu binary trong Couchbase, thiết kế document binary riêng có key và lifecycle rõ; binary không được SQL++ parse như JSON.

### 12.3. Không dùng Map<String,Object> như kho dữ liệu vô hạn

~~~java
@Field
private Map<String, Object> customAttributes;
~~~

Không giới hạn key/value sẽ làm document tăng âm thầm, khó kiểm soát kiểu và index. Dùng whitelist key, trần entry, trần byte tổng hoặc tách sang document riêng nếu payload có vòng đời/owner khác nhau.

## 13. Truy vấn kích thước mảng và phát hiện dữ liệu có nguy cơ

SQL++ hỗ trợ `ARRAY_LENGTH()` để lấy số phần tử trong array. Ví dụ xác định Product có quá nhiều Review lồng (nếu schema cũ vẫn dùng mảng `reviews`):

~~~sql
SELECT META(p).id AS productKey,
       ARRAY_LENGTH(p.reviews) AS reviewCount
FROM `shop`.`catalog`.`products` AS p
WHERE p.reviews IS ARRAY
  AND ARRAY_LENGTH(p.reviews) > 1000
ORDER BY reviewCount DESC
LIMIT 100;
~~~

`ARRAY_LENGTH` trả về số phần tử, **không trả về byte size**. Câu trên có thể cần index hoặc scan đáng kể để đánh giá từng document; dùng thận trọng ở môi trường production.

Muốn quan sát các schema cũ có `reviews` thiếu, NULL hoặc sai kiểu, kiểm tra trước:

~~~sql
SELECT META(p).id AS productKey,
       CASE
         WHEN p.reviews IS MISSING THEN "MISSING"
         WHEN p.reviews IS NULL THEN "NULL"
         WHEN p.reviews IS ARRAY THEN "ARRAY"
         ELSE "OTHER"
       END AS reviewsKind
FROM `shop`.`catalog`.`products` AS p
LIMIT 100;
~~~

Đây là truy vấn đánh giá dữ liệu, **không** tự chuyển đổi schema hay bảo đảm index tối ưu. Đối với kích thước byte, SDK/tooling/metrics cho phép kiểm tra serialized value hoặc thông tin kích thước phù hợp phiên bản; không suy từ `ARRAY_LENGTH()`.

### 13.1. Truy vấn đường lồng sâu và index

Một array index có thể giúp lọc theo các phần tử mảng **có giới hạn**:

~~~sql
CREATE INDEX ix_products_tags
ON `shop`.`catalog`.`products`
(DISTINCT ARRAY tag FOR tag IN tags END);
~~~

~~~sql
SELECT META(p).id AS productKey, p.display_name
FROM `shop`.`catalog`.`products` AS p
WHERE ANY tag IN p.tags SATISFIES tag = "organic" END;
~~~

Nhưng nếu `tags` cũng tăng hàng triệu phần tử, array index không chữa lỗi mô hình; nó còn phải xử lý lượng entry lớn. Chọn array index khi mảng **phù hợp về cardinality** và truy vấn theo phần tử đủ thường xuyên, đo bằng `EXPLAIN`/latency.

## 14. Quy trình migration: tách mảng lớn đang tồn tại

Giả sử dữ liệu cũ:

~~~json
{
  "display_name": "Cà phê",
  "reviews": [
    {"reviewerId":"u100","rating":5,"body":"Tốt"},
    {"reviewerId":"u101","rating":4,"body":"Ổn"}
  ]
}
~~~

Mục tiêu mới:

- Product giữ trường nhỏ `review_summary`, không giữ mảng reviews vô hạn.
- Mỗi Review có key riêng, `product_id`, timestamp/sequence và status phù hợp.
- API đọc Review từ collection riêng có pagination.

**Đừng lập kế hoạch bằng một câu `UNSET reviews` duy nhất.** Dữ liệu đã có phải được chuyển, đối chiếu, rồi mới xóa.

### 14.1. Các pha có thể triển khai

1. **Khảo sát:** thống kê kích thước, số phần tử, document lớn nhất, review thiếu ID/time và writer nào đang thêm vào mảng cũ.
2. **Thiết kế schema mới:** quy ước key Review ổn định hoặc key idempotent; xác định Product reference, timestamp, thứ tự và metadata lịch sử.
3. **Chuyển writer:** ngừng ghi review mới vào mảng cũ; chuyển sang viết Review độc lập. Nếu phải hỗ trợ hai phiên bản ứng dụng, triển khai logic đồng bộ/dual-write có idempotency và monitor.
4. **Backfill:** đọc từng Product theo batch, tạo Review mới từng item với key chống trùng, ghi nhận checkpoint và lỗi.
5. **Đối chiếu:** kiểm tra số Review theo Product, tổng điểm/summary, danh sách ID và tỷ lệ lỗi; xử lý duplicate và khoảng thiếu.
6. **Chuyển reader:** API đọc Review collection, kiểm tra phân trang, latency, quyền truy cập và consistency.
7. **Dọn mảng cũ:** chỉ xóa `reviews` trong Product khi backfill và reader/writer mới đã ổn định; dùng điều kiện/CAS phù hợp để không xóa cập nhật mới.
8. **Quan sát/rollback:** giữ khả năng phục hồi trong giai đoạn chuyển tiếp, đặt thời hạn loại code tương thích và đánh giá tổng byte dữ liệu sau migration.

### 14.2. Bảo toàn dữ liệu khi có concurrent writers

Nếu bạn đọc Product với CAS A, backfill mảng rồi xóa mảng trong lúc writer khác thêm phần tử, có thể **mất review mới**. Một chiến lược là đóng băng đường ghi cũ trước khi backfill; nếu không thể, cần versioning, checkpoint hoặc reconciliation theo event, CAS và idempotency.

Không dùng việc “đếm phần tử bằng nhau tại một thời điểm” làm bằng chứng tuyệt đối nếu writer vẫn đang thay đổi nguồn dữ liệu. Cần thiết kế thời điểm cutover và cách biết đã xử lý hết phần dữ liệu được ghi trong giai đoạn chuyển tiếp.

### 14.3. Di chuyển dữ liệu không đồng nghĩa với transaction khổng lồ

Transaction đa document có thể giúp một nghiệp vụ yêu cầu commit nguyên tử trên ít document. Nhưng migration hàng triệu Review **không nên được coi là một transaction đơn lẻ**; phải dùng batch, checkpoint, retry có giới hạn, đối chiếu và kế hoạch rollback.

Mục tiêu là **tính đúng đắn trong chuyển đổi schema** và tránh yêu cầu giữ nhiều document/lock trong một transaction quá lớn.

## 15. Giám sát vận hành: từ sớm thay vì chờ lỗi

### 15.1. Chỉ số nên thu thập

| Nhóm chỉ số | Ví dụ cần theo dõi | Tại sao hữu ích |
| --- | --- | --- |
| **Kích thước document** | p50/p95/p99/max serialized bytes, theo entity/keyspace | Phát hiện tăng trưởng và outlier |
| **Cardinality** | Số item `tags`, `lines`, `reviews` cũ | Biết array có vượt hợp đồng |
| **I/O** | KV get/replace payload bytes, request/response size | Tìm chỗ tốn băng thông |
| **Latency** | p50/p95/p99 cho `findById`, `save`, query review | Thấy chi phí tăng trước khi lỗi |
| **Concurrency** | CAS conflicts, retries, hot keys | Phân biệt vấn đề data model với lỗi mạng |
| **Query/index** | `EXPLAIN`, index scans, mutations, index lag | Đánh giá SQL++ và chi phí array index |
| **Heap/GC** | Allocation rate, pause, heap peak khi đọc entity lớn | Xác định chi phí materialization |
| **Error** | Document too big, timeout, serialization, query OOM | Phát hiện sự cố do payload |
| **Retention** | Số document quá hạn, backlog archive, cleanup lag | Tránh tăng trưởng ngoài dự đoán |

Nếu hệ thống không có sẵn thống kê byte theo entity, có thể lấy mẫu có kiểm soát qua SDK/log metrics, **không ghi toàn bộ document vào log** vì có thể chứa dữ liệu cá nhân và làm phình log.

### 15.2. Ví dụ ngưỡng cảnh báo nội bộ

Giả sử nhóm catalog đặt SLO minh họa:

- **Mục tiêu:** p95 Product dưới 64 KiB.
- **Cảnh báo:** p99 Product vượt 256 KiB trong khoảng giám sát có đủ lưu lượng.
- **Điều tra ngay:** bất kỳ Product nào vượt 1 MiB, có `tags` vượt 20 hoặc `highlight_review_ids` vượt 5.
- **Hành động:** phân tích key/schema, xác nhận writer, quyết định giảm payload, migration hoặc tách document.

Các giá trị này **không phải ngưỡng do Couchbase yêu cầu**. Một ứng dụng chuyên về profile có thể chọn thấp hơn, một hệ thống cần lưu JSON khối lớn có thể chọn khác; điều quan trọng là có **ngưỡng, trách nhiệm và quy trình phản ứng**.

## 16. Những cách tối ưu giả tạo cần tránh

| Đề xuất thường gặp | Vì sao chưa đủ hoặc sai | Cách làm tốt hơn |
| --- | --- | --- |
| “Giới hạn Server 20 MiB nên 15 MiB vẫn ổn” | Không tính payload, index, heap, throughput và latency | Đặt ngân sách theo SLO workload, theo dõi p95/p99 |
| “Bật nén là hết vấn đề” | Không vượt được giới hạn value; vẫn phải xử lý document khi giải nén | Giảm/đổi cấu trúc dữ liệu |
| “Dùng sub-document append là mảng không còn lớn” | Document vẫn tăng theo mỗi phần tử | Giới hạn mảng hoặc tách child |
| “Chỉ đọc 20 Review rồi cắt list trên Java” | KV đã tải và materialize **toàn bộ** mảng | Query Review riêng và pagination tại nguồn |
| “Dùng reactive là không tốn RAM” | Mỗi payload lớn vẫn được giải mã/lưu trong bộ nhớ | Giới hạn kích thước, concurrency và backpressure |
| “Array index cho mọi mảng” | Index tốn chi phí ghi và entries tăng theo số phần tử | Index theo truy vấn thực, mảng có kiểm soát |
| “Đưa mọi thứ vào một Map” | Schema động, khó index, khó giới hạn và validation | Typed properties, whitelist, tách dữ liệu |
| “Tách mọi field ra document riêng” | Tăng KV calls, JOIN và orchestration/consistency | Nhúng value object nhỏ có cùng lifecycle |
| “TTL trên Product sẽ dọn Review lồng nhau” | TTL xóa toàn bộ Product, không xóa từng item | Review riêng có TTL/retention thích hợp |
| “Counter trong Product luôn chính xác sau Review save” | Hai mutation khác document không tự nguyên tử | Thiết kế đồng bộ/transaction hoặc summary eventual consistency |
| “Đổi key prefix là đổi vị trí dữ liệu” | Key không tự chọn collection; rename key không hỗ trợ tại chỗ | Thiết kế keyspace/ID ổn định, migration rõ |

## 17. Bài thực hành: từ User.notifications[] sang Notification documents

**Bối cảnh:** một ứng dụng lưu user profile và hàng nghìn thông báo trong cùng document:

~~~json
{
  "display_name": "Lan",
  "notification_settings": {
    "email": true,
    "push": true
  },
  "notifications": [
    {"type":"ORDER_STATUS","body":"Đơn đang giao","createdAt":"2026-11-20T08:00:00Z"},
    {"type":"PROMO","body":"Khuyến mãi mới","createdAt":"2026-11-21T08:00:00Z"}
  ]
}
~~~

Mỗi User có thể nhận nhiều thông báo mỗi ngày; màn hình thông báo cần phân trang 20 mục; profile chỉ cần settings. Thông báo được giữ 30 ngày. Hãy trả lời:

1. Dữ liệu nào nên giữ trong User, dữ liệu nào nên tách?
2. Khóa Notification nên được tạo theo quy tắc nào?
3. Câu SQL++ nào tìm 20 thông báo mới nhất của một user?
4. Cần index gì, có cần secondary index để tải User theo key không?
5. TTL 30 ngày nên được đặt ở đâu?
6. Làm thế nào bảo đảm không mất thông báo khi migration?

### 17.1. Lời giải gợi ý

**User** giữ `display_name`, `notification_settings` và có thể một `unread_count` nhỏ với chính sách cập nhật/đối chiếu riêng. **Notification** là document riêng trong `shop.messaging.notifications`:

~~~json
{
  "user_id": "user::u100",
  "type": "ORDER_STATUS",
  "body": "Đơn đang giao",
  "created_at": "2026-11-20T08:00:00Z",
  "read": false
}
~~~

Khóa ví dụ: `notification::01J...` (ID duy nhất, ổn định). Không chứa nguyên nội dung thông báo, email hoặc thông tin bí mật trong document key. Có thể dùng ULID/UUID do service phát sinh hoặc key idempotent theo event nguồn. Chọn key sao cho request retry không sinh bản sao ngoài ý muốn.

Query:

~~~sql
SELECT META(n).id AS notificationKey,
       n.type, n.body, n.created_at AS createdAt,
       n.`read` AS isRead
FROM `shop`.`messaging`.`notifications` AS n
WHERE n.user_id = $userId
ORDER BY n.created_at DESC, META(n).id DESC
LIMIT 20;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_notifications_user_time
ON `shop`.`messaging`.`notifications`(
    user_id,
    created_at DESC,
    META().id DESC
);
~~~

`get(User)` theo document key không cần secondary index. Tìm Notification theo `user_id`/thời gian thường cần index phù hợp; đo `EXPLAIN`.

TTL **30 ngày cho từng Notification**, không đặt TTL 30 ngày trên User profile và không dùng TTL cho từng phần tử lồng trong User. Nếu thông báo bắt buộc giữ vì audit, dùng retention/archive phù hợp thay vì tự xóa.

Migration: chuyển writer mới sang Notification documents, backfill từng item từ `notifications[]` với key idempotent, đối chiếu số lượng/thời gian, chuyển reader, sau đó mới xóa mảng cũ với CAS/điều kiện rõ. Theo dõi retry, lỗi import và notification được ghi trong giai đoạn cutover.

### 17.2. Câu hỏi tự kiểm tra

1. **Giới hạn value Couchbase Server hiện hành là bao nhiêu?** 20 MiB; không phải kích thước mục tiêu của mọi workload.
2. **Một `List<Review>` trong Product có tự tạo document riêng không?** Không; các phần tử nằm trong body Product.
3. **Tại sao “mỗi khách một Review” vẫn không giới hạn?** Số khách có thể tiếp tục tăng.
4. **Sub-document `arrayAppend` có loại bỏ giới hạn kích thước document không?** Không.
5. **CAS giúp được gì?** Ngăn hoặc phát hiện xung đột cập nhật trên cùng document khi được sử dụng phù hợp; không làm document nhỏ hơn.
6. **Array index có chữa mô hình review vô hạn không?** Không; index cũng cần xử lý lượng phần tử lớn.
7. **Phân trang Review trong Java sau `findById(Product)` có tránh đọc toàn bộ không?** Không, root đã được tải đầy đủ.
8. **TTL có làm một phần tử trong mảng tự hết hạn riêng không?** Không, expiry thuộc document.
9. **Nếu Product và Review tách document, summary.count có tự được đồng bộ không?** Không; cần workflow/transaction hoặc cơ chế eventual consistency và reconciliation.
10. **Vì sao đo theo byte UTF-8 thay vì `String.length()`?** UTF-8 có số byte khác số đơn vị UTF-16 và JSON serializer có overhead.
11. **Cần index cho `findById(Product)` không?** Không cần secondary index cho KV theo key.
12. **Tách Review riêng có làm mất mọi chi phí không?** Không; phát sinh thêm đọc/query, phân trang, index và chính sách consistency cần thiết.

## 18. Checklist trước khi triển khai

- [ ] Ghi rõ **giới hạn server 20 MiB** và **ngân sách ứng dụng nhỏ hơn** theo workload thật.
- [ ] Đo serialized byte size theo p50/p95/p99/max và theo từng entity/keyspace.
- [ ] Xác định mọi `List`, `Set`, `Map` có thể tăng theo số người dùng, thời gian hoặc event.
- [ ] Dùng embeddable value object cho dữ liệu có vòng đời chung và giới hạn hữu hạn.
- [ ] Với dữ liệu tăng, chọn document riêng/reference, pagination hoặc chunked model có cơ chế đóng chunk.
- [ ] Ràng buộc số phần tử, độ dài field, tổng byte, độ sâu JSON và chính sách từ chối request.
- [ ] Không nhúng ảnh/base64/binary lớn vào document nghiệp vụ chỉ chứa metadata.
- [ ] Tách giá trị hiện hành và lịch sử: Product nhỏ, Review/Event/Transaction độc lập.
- [ ] Thiết kế index theo query lọc/sắp xếp và đo `EXPLAIN`; không tạo array index chỉ vì có array.
- [ ] Chú ý CAS/hot key khi nhiều writer cập nhật root hoặc summary.
- [ ] Hiểu giới hạn sub-document: ít payload, cùng CAS/document và không ngăn mảng tăng.
- [ ] Chọn TTL/retention **ở đúng đơn vị document**; có archive khi phải giữ dữ liệu.
- [ ] Dùng pagination tại nguồn thay vì tải toàn bộ rồi cắt list trong Java.
- [ ] Kiểm thử workload nhiều phần tử, text dài UTF-8, ghi đồng thời, retry, lỗi quá lớn và timeout.
- [ ] Nếu migration, chuyển writer, backfill idempotent, đối chiếu và chỉ dọn mảng cũ sau cutover.
- [ ] Theo dõi cảnh báo kích thước, tốc độ tăng, GC, latency, CAS conflicts và index lag.
- [ ] Đánh giá reactive API/backpressure nhưng không coi reactive là giải pháp thay đổi data model.

## Tài liệu tham khảo chính thức

- [Couchbase Server — Data: Items, Keys, and Values](https://docs.couchbase.com/server/current/learn/data/data.html): document key, value và giới hạn 20 MiB.
- [Couchbase Java SDK — Compression](https://docs.couchbase.com/java-sdk/current/concept-docs/compression.html): nén dữ liệu, giới hạn kích thước trước/sau nén và lưu ý vận hành.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): `lookupIn`, `mutateIn`, mảng, atomic mutation và concurrency.
- [Couchbase Server — SQL++ Array Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/arrayfun.html): `ARRAY_LENGTH()` và các hàm thao tác mảng.
- [Couchbase Server — SQL++ Array Indexing](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing-arrays.html): điều kiện `ANY`, index trên phần tử mảng và giới hạn sử dụng.
- [Couchbase Server — SQL++ CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): secondary index và cấu trúc index keys.
- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Field`, `@Id`, `@Version` và mapping JSON.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV theo ID, repository query và SQL++.
- [Spring Data Couchbase — Collections](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): chọn bucket/scope/collection cho các nhóm dữ liệu.
