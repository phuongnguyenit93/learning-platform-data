# So sánh nhúng/tham chiếu hoặc lưu quan hệ theo cách truy cập

Khi thiết kế cơ sở dữ liệu NoSQL, một quyết định tưởng đơn giản có thể ảnh hưởng cả hiệu năng, độ lớn dữ liệu và tính đúng: **nên nhúng đối tượng con vào tài liệu cha, lưu thành tài liệu riêng rồi tham chiếu, hay biểu diễn mối quan hệ bằng một bản ghi/edge riêng?** Không có một đáp án cho mọi ứng dụng. Một trang chi tiết listing cần tiện nghi và vài ảnh ở cùng lượt đọc, trong khi một màn kiểm duyệt phải tìm hàng chục nghìn review theo ngày, tác giả, trạng thái. Cả hai cùng là dữ liệu liên quan tới listing, nhưng **cách truy cập và thay đổi** hoàn toàn khác.

Trong chương **Thực hành tổng hợp** của module **Database No SQL**, bài học này sử dụng một hệ thống cho thuê phòng để thực hành thiết kế theo *access patterns*. Chúng ta sẽ so sánh **embedding (nhúng)**, **referencing (tham chiếu)** và **relationship/edge records (lưu quan hệ riêng)**; tính đến cardinality, kích thước, vòng đời, chủ sở hữu dữ liệu, độ thường xuyên đọc/ghi, atomicity, truy vấn hai chiều, indexes, chi phí và consistency. Các ví dụ bao gồm MongoDB, DynamoDB, Cassandra, graph database và Java 17; kết thúc bằng quy trình thử nghiệm, di chuyển mô hình và bài tập thực hành.

> **Nguyên tắc cốt lõi:** **Nhúng dữ liệu nhỏ, có giới hạn và thường được đọc/ghi cùng nhau; tham chiếu các thực thể có vòng đời hoặc truy vấn riêng; lưu quan hệ riêng khi quan hệ có thuộc tính, cần truy vấn hai chiều hoặc tăng trưởng độc lập.** Có thể kết hợp cả ba trong một hệ thống, miễn nguồn thẩm quyền và quy trình đồng bộ được xác định rõ.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Thu thập **read/write access patterns** trước khi lựa chọn mô hình.
2. Phân biệt embedding, referencing, edge records và materialized projections.
3. Nhận diện quan hệ 1–1, 1–ít, 1–nhiều và nhiều–nhiều theo số lượng thực tế.
4. Đánh giá **tốc độ tăng trưởng**, không chỉ số con hiện tại.
5. Xác định aggregate/atomicity boundaries và quyền sở hữu dữ liệu.
6. Thiết kế listing detail, review pagination, my bookings, favorites và payment reconciliation.
7. Giảm N+1 queries mà không cần nhúng mọi thứ.
8. Ước lượng bytes đọc, round trips, hot-key contention và write amplification.
9. Sử dụng những access primitives điển hình của MongoDB, DynamoDB, Cassandra và graph.
10. Viết bài thử, đối soát và kế hoạch migration khi access pattern thay đổi.

## 2. Tình huống xuyên suốt: ứng dụng cho thuê phòng

Các thực thể nghiệp vụ:

| Thực thể | Ví dụ | Đặc tính |
| --- | --- | --- |
| Tenant | T1 | Ranh giới cô lập khách hàng |
| User/Host | U101 | Có owner, profile và quyền |
| Listing | L101 | Tên, vị trí, tiện nghi, ảnh |
| Room/Unit | R101 | Đơn vị có thể đặt |
| Review | V101 | Đánh giá, nội dung, tác giả |
| Booking | B101 | Người đặt, kỳ lưu trú, trạng thái |
| Payment | PAY101 | Capture/refund/ledger |
| Favorite | U101 thích L101 | Quan hệ giữa user và listing |
| Availability | R101 + ngày | Tồn kho và hold |

Sơ đồ khái niệm:

~~~text
Tenant
  |---- Users ---------------------------+
  |       |                              |
  |       +---- Favorites ---- Listings  |
  |                             |        |
  +---- Listings ---- Rooms      +-- Photos
           |          |
           |          +-- Availability
           +-- Reviews
           +-- Bookings ---- Payments
~~~

Sơ đồ này **chưa xác định nơi lưu**. Một liên kết trong mô hình nghiệp vụ có thể trở thành field nhúng, reference ID, edge record, bảng theo query hoặc derived projection.

## 3. Bắt đầu từ thao tác, không từ tên database

Hãy liệt kê những câu hỏi thực sự được đặt ra:

1. Tìm 20 listings phù hợp thành phố, ngày ở, mức giá và tiện nghi.
2. Xem một listing cùng tên, mô tả, amenities, vài ảnh và điểm review trung bình.
3. Phân trang reviews, 20 bình luận mới nhất mỗi lần.
4. Chủ nhà sửa tiêu đề/ảnh/tiện nghi.
5. Khách xác nhận booking cho một phòng còn trống.
6. Khách xem lịch sử bookings của mình theo ngày.
7. Chủ nhà xem bookings của một listing.
8. Khách thêm/bỏ favorite; xem danh sách favorites.
9. Thống kê số favorite hoặc tìm mối quan hệ quản lý listing.
10. Đối soát payments/refunds theo transaction ID.

Nếu chỉ nhìn quan hệ Listing–Review rồi hỏi “nhúng hay tham chiếu?”, chúng ta đã bỏ qua một nửa yêu cầu quan trọng: **đọc review tách riêng, theo thứ tự và có phân trang**.

## 4. Bảng access patterns có thông số

Đây là workload **giả định để thực hành**, không phải benchmark:

| Mã | Thao tác | Số lượt/ngày | Output | Đặc điểm |
| --- | --- | ---: | --- | --- |
| Q1 | Search listings | 30.000 | 20–50 cards | Filter, sort, search index |
| Q2 | Listing detail | 80.000 | 1 listing + metadata | Ít round trips |
| Q3 | Review page | 15.000 | 20 reviews | Ordered pagination |
| Q4 | Update listing | 300 | Một aggregate | Owner/version |
| Q5 | Create booking | 8.000 | Booking + allocation | Không oversell |
| Q6 | My bookings | 25.000 | 10–30 bookings | Sort theo thời gian |
| Q7 | Host bookings | 4.000 | 20–50 bookings | Truy vấn ngược theo listing |
| Q8 | Add/remove favorite | 12.000 | Một quan hệ | Idempotent, unique |
| Q9 | My favorites | 18.000 | 20–50 listings | Tránh N+1 |
| Q10 | Payment reconciliation | 1.000 | Payment ledger | Tính đúng cao |

Ngoài tần suất, phải thu số liệu:

- Input keys, filters, sort, cursor, output fields.
- Latency SLO và peak QPS.
- Cardinality trung bình **và p95/p99**.
- Child growth rate theo ngày/tháng/năm.
- Tỷ lệ read/write, mức độ ghi đồng thời cùng key.
- Tần suất truy cập hai chiều của quan hệ.
- Yêu cầu transaction/freshness/retention/security.

**Mô hình được tối ưu theo workload có trọng số**, không phải một truy vấn hiếm được tối ưu bằng mọi giá.

## 5. Ba phương án lưu trữ cơ bản

### Nhúng (embedding)

Đặt dữ liệu liên quan trong một document/item:

~~~json
{
  "listingId": "L101",
  "title": "Studio gần trung tâm",
  "amenities": ["WIFI", "AIRCON", "KITCHEN"]
}
~~~

### Tham chiếu (referencing)

Lưu đối tượng riêng và dùng identity:

~~~json
{
  "bookingId": "B101",
  "listingId": "L101",
  "customerId": "U101"
}
~~~

### Bản ghi quan hệ (relationship/edge record)

Lưu chính mối liên kết thành dữ liệu có identity:

~~~json
{
  "tenantId": "T1",
  "userId": "U101",
  "listingId": "L101",
  "kind": "FAVORITED",
  "createdAt": "2026-11-14T03:00:00Z"
}
~~~

Edge record có thể ở document/key-value/wide-column database hoặc là native edge trong property graph. **Many-to-many không mặc nhiên đòi graph database**.

## 6. Có thể kết hợp cả ba

~~~text
Listing document
  |-- title, address, amenities[]          [embedded]
  |-- photoPreview[]                       [embedded/bounded]
  |-- reviewSummary {count,avg}            [derived]
  |-- hostId                               [reference]
  |
  +-- Review documents by listingId        [reference]
  +-- Booking documents by listingId       [reference]
  +-- Favorite edge records                [relationship]
  +-- Search index                         [derived projection]
~~~

Quan trọng: **reviewSummary được sao chép để phục vụ đọc**, không thay authoritative review records. Booking-time price snapshot có thể được nhúng nhưng **cố ý không cập nhật** theo giá listing mới.

## 7. Khi nào nhúng là lựa chọn tốt?

Các dấu hiệu:

- Số phần tử nhỏ và **có giới hạn thực**.
- Parent và child thường được đọc cùng nhau.
- Có chung owner và vòng đời.
- Các fields cần atomic update trong cùng document.
- Child hiếm khi được query/search độc lập.
- Child không phải đối tượng được tham chiếu từ nhiều parents.
- Data size, update frequency và index overhead ở mức kiểm soát được.

Ví dụ amenities, vài photo previews, contact preferences hoặc price snapshot tại thời điểm booking.

### Nhúng cũng có đánh đổi

Một document lớn khiến write contention, index maintenance, replication, backup và truyền dữ liệu tốn hơn. Query projection có thể cắt fields trả về nhưng chi phí backend phụ thuộc storage engine. **Nhúng nhiều không tự đồng nghĩa nhanh.**

## 8. Khi nào tham chiếu tốt hơn?

Ưu tiên tách ra khi:

- Child tăng không giới hạn.
- Child có lifecycle, owner, retention hoặc ACL riêng.
- Child cần filter, sort, pagination độc lập.
- Nhiều parents cùng tham chiếu một child.
- Ghi child thường xuyên khiến parent trở thành hot document.
- Child có thể vẫn tồn tại sau khi parent thay trạng thái.
- Có nhiều truy vấn xuất phát từ phía child.

Ví dụ reviews, bookings, payments và lịch sử sự kiện.

### Hạn chế cần giải quyết

Tham chiếu có thể tạo N+1 reads, yêu cầu secondary indexes hoặc join/lookup, và không tự có referential integrity. Phải xác định cơ chế transaction/validation/CDC khi nhiều records cần đồng bộ.

## 9. Khi nào lưu quan hệ riêng?

Khi quan hệ:

- Có identity để tránh duplicate.
- Có thuộc tính như thời gian, vai trò, nguồn, hiệu lực.
- Có trạng thái tạo/hủy độc lập.
- Được query từ **cả hai đầu**.
- Có cardinality nhiều–nhiều.
- Cần audit hoặc authorization riêng.

Ví dụ:

~~~text
User U101
   |
   +-- FAVORITED since 2026-11-14 --> Listing L101
   |
   +-- MANAGES role=EDITOR -------> Listing L202
~~~

Nếu chỉ lưu mảng user IDs trong listing, thông tin `since`, `role`, `revokedAt`, uniqueness và truy vấn ngược dễ trở nên phức tạp.

## 10. Quan hệ 1–1 chưa chắc phải nhúng

Ví dụ User và Settings:

~~~json
{
  "userId": "U101",
  "settings": {
    "locale": "vi-VN",
    "currency": "VND",
    "notifications": true
  }
}
~~~

Nhúng thuận lợi khi settings nhỏ, cùng owner và thường đọc cùng profile.

Tách settings ra hợp lý nếu:

- Một service khác độc quyền cập nhật settings.
- Settings có access control hoặc retention khác PII của profile.
- Settings lớn hoặc ghi rất thường xuyên.
- Profile read path không cần settings.
- Có contention do nhiều writers độc lập.

**Cardinality 1–1 chỉ là một tín hiệu, không phải quy tắc bất biến.**

## 11. Quan hệ 1–ít: amenities

Một listing có tối đa vài chục amenities:

~~~json
{
  "listingId": "L101",
  "amenities": [
    {"code": "WIFI", "included": true},
    {"code": "AIRCON", "included": true},
    {"code": "KITCHEN", "included": false}
  ]
}
~~~

Trang chi tiết gần như luôn cần các tiện nghi. Nhúng giúp một lần đọc và có thể cập nhật toàn bộ cấu hình trong một atomic document operation.

Khi sản phẩm thêm “tìm mọi listing có WIFI”, điều đó **không tự buộc amenities tách riêng**: các hệ document/search có thể index array/nested fields. Nhưng nếu tiện nghi có taxonomy, translations, versions, legal standards hoặc owners riêng, cần `AmenityDefinition` authority và listing lưu codes/reference.

## 12. Quan hệ 1–nhiều không giới hạn: reviews

Một listing có thể nhận hàng chục nghìn bình luận:

~~~json
{
  "listingId": "L101",
  "reviews": [
    {"reviewId": "V101", "rating": 5, "text": "..."},
    {"reviewId": "V102", "rating": 4, "text": "..."}
  ]
}
~~~

Nhúng toàn bộ reviews có rủi ro:

- Document phình to và có thể vượt item/document limits.
- Mỗi review mới phải cập nhật parent hot document.
- Pagination, moderation, filter rating/author khó tổ chức.
- Nested-array indexes có thể lớn.
- Replication/backup, concurrency và migrations tốn chi phí.

### Mô hình thay thế

~~~text
Listings:
  L101 {title, amenities, reviewSummary}

Reviews:
  V101 {listingId:L101, authorId:U201, rating:5, text:...}
  V102 {listingId:L101, authorId:U202, rating:4, text:...}
~~~

Trang chi tiết đọc summary nhỏ, endpoint reviews phân trang độc lập.

## 13. Review summary là projection

Ví dụ:

~~~json
{
  "listingId": "L101",
  "reviewSummary": {
    "count": 103,
    "ratingSum": 462,
    "average": 4.4854368932,
    "sourceVersion": 221
  }
}
~~~

Invariant:

\[
reviewCount=|\{r:r.listingId=L101 \land r.active\}|
\]

\[
ratingSum=\sum_{r\in ActiveReviews(L101)}r.rating
\]

Nếu summary được cập nhật theo CDC/outbox bất đồng bộ, hãy định nghĩa freshness SLO và kiểm reconciliation. Không lấy `reviewSummary` làm nguồn authoritative để moderation hay hoàn tác review đã xóa.

## 14. Ảnh: nhúng preview, không nhúng tùy tiện binary

Trang listing cần vài ảnh preview, nhưng full ảnh có thể nặng:

~~~json
{
  "listingId": "L101",
  "photoPreview": [
    {
      "photoId": "P1",
      "url": "https://cdn.example.test/p1.jpg",
      "order": 1
    }
  ]
}
~~~

Có thể:

- Nhúng vài metadata previews có giới hạn.
- Lưu toàn bộ photo metadata trong collection riêng nếu cần.
- Lưu binary lớn trong object storage và phục vụ qua CDN.

Phải xử lý signed URLs/permissions, upload failures, orphaned objects và deletion lifecycle. Object storage **không tự nằm chung transaction** với listing document.

## 15. Booking: thực thể có vòng đời riêng

Không nhúng toàn bộ bookings vào listing:

- Số booking tăng theo thời gian.
- Khách xem theo user; host xem theo listing.
- Booking cập nhật/cancel/refund độc lập.
- Booking cần tồn tại khi listing ngừng hoạt động.
- Booking có audit/retention khác listing.

~~~json
{
  "tenantId": "T1",
  "bookingId": "B101",
  "customerId": "U101",
  "listingId": "L101",
  "roomId": "R101",
  "checkIn": "2026-11-20",
  "checkOut": "2026-11-24",
  "status": "CONFIRMED",
  "version": 4
}
~~~

Booking tham chiếu các entity IDs nhưng cũng có thể **nhúng snapshot bất biến** từ listing hoặc price policy.

## 16. Vì sao booking cần price snapshot?

Nếu booking lịch sử tham chiếu *giá hiện tại* của listing, chủ nhà đổi giá có thể làm người dùng thấy hóa đơn cũ thay đổi.

~~~json
{
  "bookingId": "B101",
  "listingId": "L101",
  "priceSnapshot": {
    "nightlyAmountMinor": 800000,
    "nights": 4,
    "currency": "VND",
    "policyVersion": "policy-2026-11"
  }
}
~~~

Đây là một dạng **nhúng dữ liệu theo thời điểm nghiệp vụ**, không phải current projection. Nó thường không cập nhật theo listing price mới. Các refund/adjustments phải có ledger/correction rules, không sửa lịch sử mù quáng.

**Một field cùng mang tên title/price có thể có semantics khác nhau ở authority, current projection và historical snapshot.**

## 17. Payment và ledger nên được sở hữu riêng

Payment có:

- Provider intent/transaction ID.
- Capture/refund/chargeback events.
- Amount/currency cần decimal precision.
- Idempotency keys, audit và retention riêng.
- Một booking có thể liên quan nhiều payment actions.

Booking có thể tham chiếu `paymentIntentId` và lưu `paymentStatusSnapshot` để hiển thị, nhưng payment ledger/provider integration phải có authority rõ. Không nhúng toàn bộ payment events trong booking chỉ để tránh lookup nếu ledger cần truy vấn, đối soát, security và vòng đời riêng.

**Status PAID trong booking không tự chứng minh provider đã capture đúng một lần.**

## 18. Favorite: edge với business key ghép

Mỗi cặp user–listing có một quan hệ:

\[
FavoriteKey=(tenantId,userId,listingId)
\]

~~~json
{
  "tenantId": "T1",
  "userId": "U101",
  "listingId": "L101",
  "createdAt": "2026-11-14T03:00:00Z"
}
~~~

Những truy vấn cần hỗ trợ:

1. User U101 đã favorite L101 chưa?
2. Tất cả favorites của U101 theo createdAt desc?
3. Số users đã favorite L101?
4. User bỏ favorite rồi favorite lại: thời điểm nào là current?

Một edge record có unique key/conditional insert giúp tránh duplicate khi retry. Nếu cần reverse query, thêm index/derived view; cần xem authorization khi đọc danh sách người dùng.

## 19. Không dùng một mảng ID vô hạn làm quan hệ toàn năng

Ví dụ:

~~~json
{
  "userId": "U101",
  "favoriteListingIds": ["L101", "L102", "L103"]
}
~~~

Mảng nhúng có thể hợp lý nếu có **hard cap nhỏ thực sự**, truy vấn chỉ từ user và update rate thấp. Nhưng nếu favorites tăng không giới hạn:

- User document có thể thành hot key.
- Thao tác thêm/xóa tranh chấp.
- Khó đính kèm metadata/audit.
- Reverse query listing→users không tự được tối ưu.
- Kích thước document tăng.

Nếu sản phẩm thay cap 20 thành unlimited, cần đánh giá lại model, không kéo dài cách nhúng cũ không kiểm soát.

## 20. Quan hệ có thuộc tính và phân quyền

Một user quản lý listing:

~~~json
{
  "tenantId": "T1",
  "listingId": "L101",
  "userId": "U301",
  "role": "EDITOR",
  "grantedBy": "U100",
  "effectiveFrom": "2026-11-01T00:00:00Z",
  "revokedAt": null
}
~~~

Đây không chỉ là liên kết giữa hai ID: nó có owner, quyền, audit và hiệu lực. Edge/membership record thường thuận lợi hơn một mảng `managerIds`.

Trong kiểm tra authorization quan trọng, không dựa vào một projection có thể stale để cấp quyền; chọn authoritative read/consistency theo policy.

## 21. Aggregate và ranh giới atomicity

Một aggregate gom các dữ liệu cần duy trì invariant chặt trong một phạm vi transaction hoặc operation phù hợp.

~~~text
Listing aggregate:
  title, amenities, current metadata

Booking aggregate:
  booking state, price snapshot

Inventory authority:
  room/date allocations

Payment aggregate:
  intent/capture/refund ledger
~~~

Nhúng nhiều fields trong **một document** có thể giúp atomic update fields theo guarantee của DB. Nhưng nếu booking creation cần cập nhật inventory và booking **ở hai documents/stores**, single-document atomicity không bao phủ cả hai. Cần transaction đúng scope hoặc state machine/conditional reservation/compensation.

**Một method Java gọi hai DB APIs liên tiếp không tự biến chúng thành transaction.**

## 22. Nhúng không tự chống lost update

Lịch:

~~~text
Host reads listing version=7
Admin reads listing version=7
Host updates amenities
Admin blindly replaces full listing from old snapshot
~~~

Amenities mới có thể mất dù mỗi lệnh replace là atomic.

Cách phòng ngừa:

- Update đúng fields thay vì replace toàn document khi phù hợp.
- Optimistic concurrency: `WHERE version=expected`.
- Khi CAS conflict, re-read và re-evaluate.
- Tách quyền ghi theo owner/aggregate.
- Tránh đưa nhiều writers không liên quan vào cùng hot document.

Embedding giải quyết **tính cục bộ của operation**, không tự giải mọi concurrency issue.

## 23. N+1 queries khi tham chiếu

Màn favorite list hiển thị 20 listings:

~~~text
1 request: list favorite edges for user
20 requests: fetch each listing by ID

Total = 21 logical requests
~~~

Đây là N+1. Có thể:

- Batch-get 20 listing IDs.
- Dùng lookup/join được engine hỗ trợ và index đúng.
- Tạo denormalized favorite display projection.
- Cache title/preview với version và invalidation policy.

**Tham chiếu không bắt buộc có N+1 nếu tầng truy cập dữ liệu được thiết kế tốt.** Đừng nhúng vô hạn chỉ để sửa một vòng lặp truy vấn kém hiệu quả.

## 24. Đọc nhiều bytes không cần thiết

Giả định:

~~~text
Listing core:        2 KiB
Amenities:           0.5 KiB
Photo previews:      1 KiB
All reviews:       200 KiB
Booking history:   50 KiB
~~~

Trang chi tiết chỉ cần listing + amenities + previews + review summary. Nếu tất cả nhúng chung, logical document có thể khoảng 253,5 KiB; còn model bounded chỉ cần khoảng 3,5 KiB cộng summary nhỏ.

Projection ở query layer có thể giảm payload trả về, nhưng storage/index/backend costs phụ thuộc DB. Kết luận hợp lý là **tránh phát triển document không giới hạn khi đường đọc chỉ cần một phần nhỏ**.

## 25. Viết nhiều bản sao: write amplification

Một title có thể xuất hiện:

~~~text
Listing authority title
Search index title
Favorite display projection title
Host dashboard projection title
Booking-time title snapshot
~~~

Khi đổi title:

- Authority phải thay đổi.
- Current read projections cần catch-up theo freshness contract.
- **Booking-time snapshot không nên tự đổi**, vì nó mô tả quá khứ.

Đặt sơ bộ:

\[
TotalLogicalWrites = AuthorityWrite + ProjectionWrites
\]

Con số còn phụ thuộc retries, index updates, event fan-out và batches. Denormalization **đổi ít lần đọc lấy thêm ghi và trách nhiệm đồng bộ**.

## 26. Ước lượng size và growth

Nếu review trung bình 1 KiB:

| Số reviews | Dung lượng logical của reviews |
| ---: | ---: |
| 10 | Khoảng 10 KiB |
| 1.000 | Khoảng 1 MiB |
| 10.000 | Khoảng 10 MiB |
| 100.000 | Khoảng 100 MiB |

Giới hạn BSON document của MongoDB thông thường là 16 MiB; item size của DynamoDB thường tối đa 400 KB. Các giới hạn thực tế cần xác minh theo product/deployment, chưa kể overhead của field names và indexes.

Trong Cassandra/wide-column, một partition có thể chứa nhiều rows nhưng partition quá lớn/hot vẫn có rủi ro vận hành. Không có một ngưỡng độ lớn an toàn duy nhất cho mọi cluster.

### Dự báo tăng trưởng

\[
ProjectedChildren = CurrentChildren + DailyGrowth \times Days
\]

Hãy xem p95/p99 và outliers, không chỉ average. Một listing mới chỉ có 2 reviews không có nghĩa mọi listing sẽ mãi có ít reviews.

## 27. Hot keys và hot partitions

Một listing nổi tiếng có thể nhận 1.000 reviews/phút và 10.000 favorite actions/phút. Nếu mọi event append vào `Listing:L101`, có thể gây:

- Contention và retries.
- Write throughput bottleneck.
- Document/index update overhead.
- Replication lag trên item nóng.
- TTL/deletion cleanup khó.

Giải pháp có thể gồm:

- Tách child/edge records.
- Summary/aggregate counters bất đồng bộ có reconciliation.
- Sharded counters nếu nghiệp vụ cho phép.
- Time/hash bucketing theo access pattern.
- Chọn authority/protocol đủ mạnh nếu là inventory hard-cap.

**Phân tán ghi cho scale không được phép biến no-double-booking thành best-effort**.

## 28. Xác định chính xác index/query path

Review record:

~~~json
{
  "tenantId": "T1",
  "reviewId": "V101",
  "listingId": "L101",
  "authorId": "U201",
  "rating": 5,
  "createdAt": "2026-11-14T03:00:00Z",
  "status": "PUBLISHED"
}
~~~

Query:

~~~text
WHERE tenantId=T1 AND listingId=L101
      AND status=PUBLISHED
ORDER BY createdAt DESC
LIMIT 20
~~~

Một compound index tương ứng các filter/sort có thể hiệu quả trên document store. Nếu moderation cần query theo author, đó là **access pattern khác**, có thể cần index hoặc bảng riêng. Không coi index mới là miễn phí: nó tốn bộ nhớ/disk và thêm write amplification.

## 29. MongoDB: nhúng listing metadata

~~~javascript
db.listings.insertOne({
  _id: "L101",
  tenantId: "T1",
  title: "Studio trung tâm",
  hostId: "U100",
  amenities: ["WIFI", "AIRCON"],
  photoPreview: [
    {id: "P1", order: 1, url: "https://cdn.example.test/p1.jpg"}
  ],
  reviewSummary: {count: 0, ratingSum: 0},
  version: 1
});
~~~

Một detail read:

~~~javascript
db.listings.findOne(
  {_id: "L101", tenantId: "T1"},
  {title: 1, amenities: 1, photoPreview: 1,
   reviewSummary: 1}
);
~~~

Một update có version guard:

~~~javascript
db.listings.updateOne(
  {_id: "L101", tenantId: "T1", version: 1},
  {
    $set: {amenities: ["WIFI", "AIRCON", "KITCHEN"]},
    $inc: {version: 1}
  }
);
~~~

MongoDB atomicity của một document không tự bao phủ reviews hoặc booking collections. Version guard chỉ hiệu quả nếu **tất cả writers tuân protocol**.

## 30. MongoDB: tham chiếu reviews và phân trang

~~~javascript
db.reviews.insertOne({
  _id: "V101",
  tenantId: "T1",
  listingId: "L101",
  authorId: "U201",
  rating: 5,
  text: "Rất sạch sẽ",
  status: "PUBLISHED",
  createdAt: ISODate("2026-11-14T03:00:00Z")
});
~~~

Index/truy vấn:

~~~javascript
db.reviews.createIndex({
  tenantId: 1, listingId: 1, status: 1,
  createdAt: -1, _id: -1
});

db.reviews.find({
  tenantId: "T1",
  listingId: "L101",
  status: "PUBLISHED"
}).sort({createdAt: -1, _id: -1}).limit(20);
~~~

Mục tiêu là lấy một page chứ không đọc 100.000 reviews vào JVM rồi cắt 20 phần tử. Với trang sâu, dùng keyset/cursor pagination và kiểm index bằng `explain()` trên dữ liệu đại diện.

## 31. MongoDB: $lookup khi thật sự cần

Màn my bookings muốn current title của listing:

~~~javascript
db.bookings.aggregate([
  {$match: {tenantId: "T1", customerId: "U101"}},
  {$sort: {createdAt: -1}},
  {$limit: 20},
  {$lookup: {
    from: "listings",
    localField: "listingId",
    foreignField: "_id",
    as: "listing"
  }},
  {$project: {
    bookingId: 1, status: 1, priceSnapshot: 1,
    "listing.title": 1
  }}
]);
~~~

Tradeoffs:

- `$lookup` hỗ trợ truy vấn nhưng cost phụ thuộc indexes/cardinality/topology/version.
- `$limit` trước lookup có thể giảm số joins.
- Current title khác **booking-time snapshot**.
- Với tenant-scoped IDs, cần xác minh unique/authorization filter cả hai phía.
- Batch-get hoặc denormalized display projection có thể phù hợp nếu path rất nóng.

Không kết luận “NoSQL không có joins”; cũng không giả định joins rẻ trên mọi hệ.

## 32. MongoDB: favorite edge

~~~javascript
db.favorites.insertOne({
  _id: "T1#U101#L101",
  tenantId: "T1",
  userId: "U101",
  listingId: "L101",
  createdAt: ISODate("2026-11-14T03:00:00Z")
});

db.favorites.createIndex({
  tenantId: 1, userId: 1, createdAt: -1
});

db.favorites.createIndex({
  tenantId: 1, listingId: 1
});
~~~

Composite identity giúp ngăn duplicate khi retry cùng favorite. Nếu dùng unique index thay deterministic `_id`, phải xác định index đầy đủ trên `(tenantId,userId,listingId)`. Reverse query phục vụ analytics/permissions cần kiểm quyền, không chỉ query performance.

## 33. DynamoDB: single-table không có nghĩa single-document

Một single-table design có nhiều item types:

| Entity | PK | SK | Đường đọc |
| --- | --- | --- | --- |
| Listing | `LISTING#L101` | `META` | Detail |
| Photo | `LISTING#L101` | `PHOTO#P1` | Photos |
| Review | `LISTING#L101` | `REVIEW#20261114#V101` | Review page |
| Favorite | `USER#U101` | `FAV#L101` | User favorites |
| Booking | `BOOKING#B101` | `META` | Booking by ID |
| Availability | `ROOM#R101` | `DATE#20261120` | Room/date |

Các key prefixes minh họa ý tưởng. Nhiều items cùng `PK` có thể được `Query` theo sort key, nhưng **không tự trở thành một item atomic**. Đừng xem co-location trong table là multi-record transaction.

### Cần kiểm

- Item size limit và Query pagination.
- Hot partition key throughput.
- Conditional writes/transaction scope.
- GSI propagation và eventual reads.
- BatchGet limits/unprocessed keys.
- Full tenant/business identity.

## 34. DynamoDB: reverse query qua GSI

Favorite base item:

~~~text
PK=USER#U101
SK=FAV#L101

GSI1PK=LISTING#L101
GSI1SK=USER#U101
~~~

Base table cho query favorites của user; GSI hỗ trợ truy vấn theo listing. GSI tốn write/compute/storage và có eventual propagation semantics. Nếu business yêu cầu favorite uniqueness, condition nên kiểm trên **base item có identity ổn định**, không lấy một GSI read stale làm trọng tài.

Nếu một tenant có millions favorites, cần đánh giá skew/hot key và cách tính aggregate count.

## 35. Cassandra: model theo partition key và query

Ví dụ một bảng reviews theo listing:

~~~sql
CREATE TABLE reviews_by_listing (
  tenant_id text,
  listing_id text,
  created_at timestamp,
  review_id text,
  author_id text,
  rating int,
  content text,
  PRIMARY KEY ((tenant_id, listing_id), created_at, review_id)
) WITH CLUSTERING ORDER BY
      (created_at DESC, review_id ASC);
~~~

Query:

~~~sql
SELECT review_id, rating, content, created_at
FROM reviews_by_listing
WHERE tenant_id = 'T1'
  AND listing_id = 'L101'
LIMIT 20;
~~~

Một listing cực lớn có thể cần bucket thêm tháng/hash trong partition key, tùy patterns. Cassandra không phải hệ join tổng quát; nếu cần `reviews_by_author`, có thể tạo bảng theo access pattern ấy và đồng bộ bằng workflow/version/CDC. **Nhiều denormalized tables không tự được ghi nguyên tử như một SQL transaction đa partition.**

## 36. Graph database: khi traversal là truy vấn chính

Một property graph:

~~~text
(:User U101)-[:FAVORITED {since:...}]->(:Listing L101)
(:User U301)-[:MANAGES {role:"EDITOR"}]->(:Listing L101)
(:User U101)-[:FOLLOWS]->(:User U301)
~~~

Cypher:

~~~cypher
MATCH (u:User {tenantId: 'T1', id: 'U101'})
      -[:FAVORITED]->(l:Listing)
RETURN l.id, l.title
ORDER BY l.title
LIMIT 20;
~~~

Native graph database có thể có lợi khi use cases yêu cầu nhiều bước quan hệ: recommendations, fraud rings, permissions hoặc đường đi. Nhưng một cặp favorite user–listing đơn giản hoàn toàn có thể được lưu làm edge document trong key-value/document store. **Chọn graph vì traversal workload, không chỉ vì schema có đường nối**.

## 37. Search và Redis: derived stores

Search projection có thể chứa:

~~~json
{
  "listingId": "L101",
  "city": "Hồ Chí Minh",
  "amenityCodes": ["WIFI", "AIRCON"],
  "minPriceMinor": 800000,
  "ratingAvg": 4.6
}
~~~

Redis có thể cache một listing summary hoặc favorite count. Những dữ liệu này thường được **dẫn xuất từ authority**:

~~~text
Listing/Review Authority
  → Outbox/CDC
  → Search, Redis, favorite display projection
~~~

Mỗi projection cần:

- Mapping/fields được phép expose.
- Source version và idempotent consumer.
- Freshness SLO.
- Delete propagation và TTL.
- Rebuild/reconciliation.
- Lỗi out-of-order và retry handling.

Không dùng cache/search làm booking/payment authority nếu hệ chưa được thiết kế để chúng có vai trò đó.

## 38. Decision matrix

| Tiêu chí | Embedding | Referencing | Edge record |
| --- | --- | --- | --- |
| Parent+child luôn đọc cùng | Tốt | Cần lookup/batch | Thường cần traversal |
| Child tăng vô hạn | Rủi ro | Tốt | Tốt |
| Child có lifecycle riêng | Khó | Tốt | Tốt nếu quan hệ có lifecycle |
| Child được nhiều parents chia sẻ | Copy dư | Tốt | Tốt |
| Truy vấn hai chiều | Có thể khó | Index ngược | Tự nhiên theo endpoints/index |
| Atomic parent+child write | Có thể trong một document | Tùy transaction | Tùy transaction |
| Parent hot-key contention | Có nguy cơ | Dễ tách tải | Dễ tách tải |
| Pagination child | Bất lợi với array lớn | Tốt | Tốt với access index |
| ACL/retention độc lập | Khó hơn | Tốt | Tốt |
| N+1 risk | Ít | Có nếu code không batch | Có nếu traversal không tối ưu |

Ma trận mang tính định hướng. Trong hệ thực, một indexed lookup có thể nhanh hơn nhúng một document khổng lồ.

## 39. Cách ước lượng read/write cost

Một mô hình thảo luận:

\[
ReadCost\approx
ReadFrequency\times(RoundTrips+Bytes+IndexWork)
\]

\[
WriteCost\approx
WriteFrequency\times(WriteFanout+Contention+IndexUpdates)
\]

Các đại lượng không cùng đơn vị; khi ra quyết định thực tế phải **quy đổi theo latency, request units, bytes transfer, IOPS, giá tiền hoặc SLO violations**, không cộng thẳng số bytes và milliseconds.

Đặt thêm hard constraints trước khi chấm điểm:

- Document/item không được vượt limits.
- Không vi phạm tenant isolation.
- Không được oversell inventory.
- Không làm sai payment ledger.
- Có retention/deletion policy.

Một phương án đạt read latency tốt nhưng vi phạm correctness phải bị loại, không chỉ bị trừ vài điểm.

## 40. Java 17: mô phỏng ba đường truy cập

Lab tự chạy, không cần database hay thư viện ngoài. Ta giữ amenities **nhúng** trong Listing, Reviews **tham chiếu theo listing** để phân trang, Favorite **lưu thành edge**. Chương trình so N+1 lookups và batch-get logical calls. Tạo file `AccessPatternModelLab.java`:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class AccessPatternModelLab {
    record Listing(
            String id, String title,
            List<String> amenities,
            int reviewCount) {}

    record Review(
            String id, String listingId,
            int rating, String text) {}

    record Favorite(String userId, String listingId) {}

    static final class Meter {
        int trips;
        int itemsRead;

        void recordRead(int items) {
            trips++;
            itemsRead += items;
        }
    }

    static final class FakeStore {
        final Map<String, Listing> listings = new HashMap<>();
        final Map<String, List<Review>> reviews = new HashMap<>();
        final List<Favorite> favorites = new ArrayList<>();

        Listing listing(String id, Meter meter) {
            meter.recordRead(1);
            return listings.get(id);
        }

        List<String> favoriteIds(String userId, Meter meter) {
            List<String> result = new ArrayList<>();
            for (Favorite edge : favorites) {
                if (edge.userId().equals(userId)) {
                    result.add(edge.listingId());
                }
            }
            meter.recordRead(result.size());
            return result;
        }

        List<Listing> batchListings(
                Collection<String> ids, Meter meter) {
            List<Listing> result = new ArrayList<>();
            for (String id : ids) {
                Listing listing = listings.get(id);
                if (listing != null) {
                    result.add(listing);
                }
            }
            // Idealized one-batch call. Real services
            // have limits and may return unprocessed keys.
            meter.recordRead(result.size());
            return result;
        }

        List<Review> reviewPage(
                String listingId, int limit, Meter meter) {
            List<Review> all = reviews
                    .getOrDefault(listingId, List.of());
            List<Review> page = all.subList(
                    0, Math.min(limit, all.size()));
            meter.recordRead(page.size());
            return page;
        }
    }

    static List<Listing> favoriteDetailsNPlusOne(
            FakeStore db, String userId, Meter meter) {
        List<String> ids = db.favoriteIds(userId, meter);
        List<Listing> result = new ArrayList<>();
        for (String id : ids) {
            Listing item = db.listing(id, meter);
            if (item != null) {
                result.add(item);
            }
        }
        return result;
    }

    static List<Listing> favoriteDetailsBatch(
            FakeStore db, String userId, Meter meter) {
        List<String> ids = db.favoriteIds(userId, meter);
        return db.batchListings(ids, meter);
    }

    public static void main(String[] args) {
        FakeStore db = new FakeStore();
        db.listings.put("L1", new Listing(
                "L1", "Studio",
                List.of("WIFI", "AIRCON"), 1000));
        db.listings.put("L2", new Listing(
                "L2", "Apartment",
                List.of("KITCHEN"), 200));
        db.listings.put("L3", new Listing(
                "L3", "House",
                List.of("WIFI"), 10));

        db.favorites.add(new Favorite("U1", "L1"));
        db.favorites.add(new Favorite("U1", "L2"));
        db.favorites.add(new Favorite("U1", "L3"));

        db.reviews.put("L1", List.of(
                new Review("V1", "L1", 5, "Nice"),
                new Review("V2", "L1", 4, "Clean")));

        Meter detail = new Meter();
        Listing listing = db.listing("L1", detail);
        System.out.println(
                "Detail amenities=" + listing.amenities());
        System.out.println(
                "Detail trips=" + detail.trips);

        Meter page = new Meter();
        System.out.println(
                "Review page size="
                    + db.reviewPage("L1", 20, page).size());
        System.out.println(
                "Review trips=" + page.trips);

        Meter nPlusOne = new Meter();
        List<Listing> naive = favoriteDetailsNPlusOne(
                db, "U1", nPlusOne);
        Meter batched = new Meter();
        List<Listing> optimized = favoriteDetailsBatch(
                db, "U1", batched);

        System.out.println(
                "N+1 listings=" + naive.size()
                + " trips=" + nPlusOne.trips);
        System.out.println(
                "Batch listings=" + optimized.size()
                + " trips=" + batched.trips);
    }
}
~~~

Chạy với Java 17:

~~~bash
javac AccessPatternModelLab.java
java AccessPatternModelLab
~~~

Kết quả minh họa:

~~~text
Detail amenities=[WIFI, AIRCON]
Detail trips=1
Review page size=2
Review trips=1
N+1 listings=3 trips=4
Batch listings=3 trips=2
~~~

### Kết quả cho thấy gì?

- Listing detail nhúng amenities để lấy cùng document.
- Reviews được truy cập riêng theo listing; số lượng lớn có thể phân trang ở DB.
- Favorite edge cung cấp danh sách listing IDs.
- Fetch từng listing tạo N+1, còn batch fetch giảm số logical calls.

### Giới hạn

- `FakeStore` là in-memory model, không đo network, index, disk, serialization hay p99.
- Batch-get thật có size limits, pagination và unprocessed keys.
- Không có transaction, persistence, cache freshness hoặc distributed concurrency.
- Không dùng số trips ở lab như benchmark hiệu năng của một sản phẩm NoSQL.

## 41. Query pagination và sort key

Một endpoint:

~~~text
GET /listings/L101/reviews?limit=20&cursor=...
~~~

Cần:

- Stable sort theo `(createdAt DESC, reviewId DESC)` hoặc tương đương.
- Index/partition hỗ trợ ordered reads.
- Cursor đủ thông tin tiếp tục trang.
- Không đọc hết reviews rồi cắt 20 phần tử trong ứng dụng.
- Chính sách khi reviews được thêm/xóa giữa hai trang.
- Tenant scoping và cursor integrity.

Trong DynamoDB/Cassandra dùng paginated Query semantics; MongoDB có thể dùng indexed keyset/range query. Deep `skip/offset` có thể tốn hơn cursor theo key, tùy query engine.

## 42. Dual-direction access quyết định thêm index

Một dữ liệu favorites có thể được truy vấn:

~~~text
From user → list favorited listings
From listing → count/list interested users
~~~

Nếu chỉ tối ưu `PK=USER#...`, query ngược có thể phải scan. Những lựa chọn:

- Secondary index/reverse GSI.
- Một bảng theo listing được đồng bộ.
- Edge collection với compound indexes hai chiều.
- Graph traversal nếu workload nhiều bước quan hệ.

Mỗi reverse view có chi phí ghi/lag. Đừng xây projection nhạy cảm chứa full user details khi chỉ cần **aggregate count**.

## 43. Source of truth và historical snapshot

Một field title có thể tồn tại ở:

| Vị trí | Semantics |
| --- | --- |
| Listing authority | Giá trị hiện tại được cập nhật |
| Booking title snapshot | Giá trị tại thời điểm xác nhận |
| Favorite display projection | Current title, có lag SLO |
| Search index | Current searchable title, có index lag |

Nếu title đổi, các nơi **không cần cùng bytes**. Booking snapshot cố ý giữ giá trị cũ; favorite/search cần cập nhật eventual theo chính sách.

Một invariant đúng là “current projections bắt kịp source version trong SLO”, không phải “mọi record lịch sử phải bằng title hiện tại”.

## 44. Đồng bộ denormalization bằng CDC/outbox

~~~text
Listing Authority
  |
  +-- transactional outbox / change feed
             |
             v
         Event consumer
          /         \
         v           v
  Search index    Favorite feed view
~~~

Thiết kế:

1. Stable event ID và aggregate ID.
2. Version/sequence để ngăn out-of-order overwrite.
3. Consumer idempotency khi delivery lặp.
4. Snapshot+CDC watermark khi rebuild.
5. Delete propagation.
6. Retry, DLQ và reconciliation.
7. Freshness SLO.

Không tuyên bố exactly-once effects xuyên database, broker và search nếu không chỉ ra transaction boundary thực sự. **Một event có thể được deliver nhiều lần nhưng business effect phải được dedupe.**

## 45. TTL, retention, deletion và security

Booking history, payment ledger, short-lived inventory hold và favorite edge có vòng đời khác nhau. Nếu nhúng tất cả vào một listing:

- TTL trở nên khó cô lập.
- Parent deletion có thể xóa nhầm child phải giữ.
- Backup có thể hồi sinh dữ liệu đã xóa hợp lệ.
- Access controls khó chia tách.
- Quá nhiều PII bị truyền trong một document.

Mô hình cần tách **business ownership, retention và privilege boundaries**. Edge queries phải dùng full tenant key; đừng truy vấn favorites của tenant T2 bằng identity chỉ có `userId` vốn có thể trùng.

## 46. Migration từ embedded reviews sang references

Khi review count phát triển:

1. Xác định authoritative source và stable review IDs.
2. Tạo collection/table mới cùng indexes.
3. Backfill embedded reviews theo snapshot/checkpoint.
4. Giữ/tiếp nhận những writes mới sau mốc backfill bằng CDC hoặc protocol phù hợp.
5. Dedupe theo review ID/version.
6. Shadow-read/reconcile theo full keys, values và deletes.
7. Chuyển read path sang paginated review queries.
8. Xác nhận review summaries/counters đúng.
9. Chuyển authoritative write path theo cutover plan.
10. Chỉ dọn legacy embedded arrays sau signoff và retention policy.

Không thực hiện copy một lần rồi coi xong khi users vẫn đang tạo reviews trong thời gian migration.

## 47. Đối soát khi thay representation

Trước:

~~~text
Listing embedded reviews: V1, V2, V3
~~~

Sau:

~~~text
Review collection keys: V1, V2, V4
~~~

Counts đều bằng 3 nhưng:

- V3 missing.
- V4 extra.

Cần so full keyset, canonical values, versions, TTL/deletes và tenant. Nếu summary ratingCount bằng nhau, vẫn có thể có review mất/nhân đôi. Cần xác minh query behavior, moderation và pagination sau migration.

## 48. Benchmark theo workload đại diện

Tạo dataset:

- 1 triệu listings, nhiều tenants.
- 90% listing ít reviews; 1% cực nhiều reviews.
- Một số hot listings nhận spike writes.
- Favorites skew theo active users.
- Booking history dài, query theo date/status.
- Có soft-deleted reviews và TTL holds.
- Có concurrent updates vào cùng listing.

Đo:

| Use case | Thước đo |
| --- | --- |
| Listing detail | p50/p95/p99, bytes, round trips |
| Review page | Index scanned/returned, cursor stability |
| Favorite list | N+1 vs batch, requests |
| Favorite add/remove | Conflict/idempotency, p99 |
| Host bookings | Access path/index selectivity |
| Listing updates | Hot-document contention |
| Booking confirm | Inventory invariant, write latency |
| CDC/search | Freshness, applied watermark |
| Migration backfill | Catch-up time, missing/duplicate keys |

Một mẫu dữ liệu dev chỉ có vài listings không phát hiện hot partitions hoặc kích thước child outlier.

## 49. Đọc query plan/metrics

Theo engine:

- MongoDB: `explain()`, keys/documents examined, index scans.
- DynamoDB: consumed capacity, Query pages, unprocessed keys.
- Cassandra: partition size, tracing, read/write latency.
- Graph: query plan và expansion cardinality.
- Search: index/query profiling, refresh/freshness lag.

Đánh giá latency/cost **end-to-end** theo use case: số requests, payload bytes, reads per action, read/write amplification, CPU/IOPS và lỗi dưới peak. Một query tối ưu với index có thể tốt hơn đọc một document quá lớn; cần đo, không suy đoán.

## 50. ADR ghi quyết định mô hình

~~~yaml
decision:
  title: "Listing and Review relationship"
  workload:
    hotReads: ["listing detail", "review pagination"]
    writes: ["create review", "moderate review"]
    childGrowth: "unbounded"
  alternatives:
    - "embed all reviews"
    - "reference review documents"
    - "graph edges"
  chosen: "reference reviews + embedded review summary"
  rationale:
    - "reviews need independent pagination and lifecycle"
    - "listing detail needs a bounded summary"
    - "avoid listing document growth and write contention"
  consistency:
    - "authoritative review record"
    - "eventual summary with freshness SLO"
  tests:
    - "pagination latency under peak"
    - "review id uniqueness"
    - "source/summary reconciliation"
  revisitWhen:
    - "access pattern changes"
    - "hot listing p99 cardinality grows"
~~~

Đây là mẫu mô tả một ADR, không phải cú pháp bắt buộc của công cụ cụ thể. Quan trọng là ghi **giả định, lý do và điều kiện xem lại**.

## 51. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Nhúng mọi review | Document phình to | Review docs + summary |
| Nhúng mọi booking trong listing | Vòng đời/hot key sai | Booking authority riêng |
| Favorite IDs tăng vô hạn | Size/contended updates | Edge records |
| Reference mọi field nhỏ | N+1 | Embed bounded data |
| Lookup từng favorite | Latency nhiều requests | Batch/lookup/projection |
| Copy owner fields không có policy | Stale versions | Authority + CDC |
| Thay historical booking snapshot theo listing | Sai lịch sử | Immutable snapshot |
| Dùng search/cache làm booking authority | Sai consistency | Domain authority |
| Không có reverse index | Full scans | GSI/index/bảng theo query |
| Partition mọi events theo một hot listing | Hot partition | Bucket/shard đúng semantics |
| Bỏ tenant khỏi key | Trộn/rò dữ liệu | Full composite key |
| Blind document replacement | Lost concurrent updates | Field patch/CAS |
| Không xử lý CDC duplicates | Double side effects | Stable event IDs |
| So raw physical counts sau denormalization | False mismatch | Logical contract |
| Không test delete/TTL | Data resurrection | Lifecycle reconciliation |
| Copy dữ liệu trong migration không watermark | Bỏ writes mới | Snapshot+CDC |

## 52. Bài tập thực hành

### Bài 1 — Chọn embedding

Listing detail được đọc 100.000 lần/ngày, amenities tối đa 25 codes, ít thay đổi. Đề xuất mô hình và giải thích.

### Bài 2 — Reviews tăng vô hạn

Một listing có 50.000 reviews. Nêu ít nhất bốn rủi ro nếu nhúng toàn bộ vào listing.

### Bài 3 — Access pattern

Viết bảng filter/sort/limit/frequency/freshness cho Q1–Q10.

### Bài 4 — Atomicity

Một document inventory có `available` và `reserved`; so với việc lưu chúng ở hai documents, phạm vi atomic khác nhau ra sao?

### Bài 5 — Price snapshot

Chủ nhà đổi giá sau booking. Vì sao booking nên nhúng price snapshot thay vì chỉ tham chiếu current listing price?

### Bài 6 — Payment ledger

Tại sao một field `paymentStatus="PAID"` trong booking không đủ cho reconciliation?

### Bài 7 — Review index

Thiết kế compound index cho 20 reviews mới nhất theo tenant, listing và status.

### Bài 8 — Review summary

Một listing có 100 active reviews, ratingSum=430. Tính average. Nếu xóa một review rating=5, summary cần thay gì?

### Bài 9 — Media

So nhúng photo metadata với nhúng binary ảnh. Khi nào object storage phù hợp?

### Bài 10 — Many-to-many

Thiết kế full business key favorite và mô tả idempotent insert-if-absent.

### Bài 11 — Edge metadata

Quan hệ manager có `role`, `grantedBy`, `revokedAt`. Vì sao mảng manager IDs không đủ cho audit?

### Bài 12 — N+1

Một favorite list có 30 listings; một edges query + 30 listing queries. Có bao nhiêu logical round trips? Batch-get làm giảm thế nào?

### Bài 13 — Reverse query

Ứng dụng muốn đếm users thích L101. Đề xuất GSI/index hoặc projection.

### Bài 14 — Size

Mỗi review 1 KiB, 20.000 reviews xấp xỉ bao nhiêu MiB? Vì sao phải biết engine item limits?

### Bài 15 — Hot key

Listing nổi tiếng nhận 10.000 favorite actions/phút. Vì sao append vào listing array có thể tắc?

### Bài 16 — MongoDB

Viết `updateOne` để cập nhật amenities với `version` guard và tăng version.

### Bài 17 — MongoDB $lookup

So lookup current listing title với booking-time snapshot khi hiển thị lịch sử booking.

### Bài 18 — MongoDB indexes

Thiết kế hai compound indexes để query favorites từ user và listing.

### Bài 19 — DynamoDB keys

Viết PK/SK cho listing, review, favorite, booking trong single-table design.

### Bài 20 — DynamoDB GSI

Muốn truy vấn favorite theo listing, đề xuất GSI và nêu eventual consistency caveat.

### Bài 21 — Cassandra

Tạo `reviews_by_listing` có clustering mới nhất trước. Hot listing cần bucket theo yếu tố nào?

### Bài 22 — Cassandra reverse table

Thêm truy vấn reviews theo author. Khi có hai denormalized tables, phải xử lý partial writes và reconciliation thế nào?

### Bài 23 — Graph

Với truy vấn user→followed hosts→listings→shared amenities, khi nào graph traversal có ích?

### Bài 24 — Search

Listing DRAFT không được index. Vì sao source count có thể khác search count mà không là lỗi?

### Bài 25 — Cache freshness

Host sửa listing title, cache còn title cũ. Đề xuất invalidation/version/freshness policy.

### Bài 26 — Write amplification

Listing title ở authority và ba current projections. Một lần update có thể kéo theo bao nhiêu logical updates? Booking historical snapshot có phải update không?

### Bài 27 — Java lab

Chạy `AccessPatternModelLab.java`, giải thích N+1 4 trips và batch 2 trips trong dataset mẫu.

### Bài 28 — Java extension

Thêm 100 favorite listings và batch-get size tối đa 25. Thiết kế pagination/batching và xử lý unprocessed keys.

### Bài 29 — Deletion

Listing bị soft-delete nhưng booking vẫn phải giữ theo retention. Thiết kế lifecycle cho hai authorities.

### Bài 30 — Tenant isolation

Hai tenants có cùng listingId=L101. Vì sao edge cần tenantId và full key?

### Bài 31 — Migration

Chuyển reviews nhúng sang collection riêng khi user vẫn ghi mới. Thiết kế backfill+CDC+cutoff.

### Bài 32 — Reconciliation

Embedded IDs V1,V2,V3 còn target IDs V1,V2,V4. Counts bằng nhau; xác định missing/extra.

### Bài 33 — Benchmark

Thiết kế thử nghiệm p95/p99 cho listing detail, review page, favorites dưới hot-key skew.

### Bài 34 — Invariants

Tại sao nhúng toàn bộ bookings trong listing không tự bảo vệ no-double-booking khi inventory được ghi ở hệ khác?

### Bài 35 — Bài tổng hợp

Ứng dụng cho thuê dùng MongoDB cho listing/booking, DynamoDB cho inventory, Cassandra cho review history, Redis cache và search index:

1. Lập ma trận access patterns.
2. Chọn dữ liệu bounded để nhúng trong listing.
3. Tách reviews và thiết kế pagination.
4. Định nghĩa booking authority với references/price snapshot.
5. Thiết kế favorite edge/index hai chiều.
6. Giữ inventory invariant tại authority phù hợp.
7. Xác định payment ledger ownership.
8. Thiết kế CDC/current projections và freshness.
9. Đo read calls, bytes, write fan-out và contention.
10. Đưa ra migration plan, reconciliation checks và acceptance criteria.

**Gợi ý:** Phương án mạnh thường là **mô hình hỗn hợp có ranh giới rõ ràng**, không cố ép mọi entity vào một document hoặc mọi quan hệ thành JOIN.

## 53. Checklist quyết định

1. Đã liệt kê hot read/write queries?
2. Đã xác định filters, sort, limit, output fields?
3. Đã đo cardinality average và p95/p99?
4. Có forecast growth/retention?
5. Child có chung owner và lifecycle với parent?
6. Child có query/pagination riêng?
7. Có truy vấn quan hệ theo cả hai hướng?
8. Edge có metadata, role, status hoặc audit riêng?
9. Full business key có tenant scope?
10. Có kiểm document/item/partition size limits?
11. Có đo hot-key write contention?
12. Có hiểu single-document atomicity vs multi-record transaction?
13. Có source of truth cho từng entity?
14. Có phân biệt immutable snapshot và current projection?
15. Có PK/index/GSI tương ứng từng access path?
16. Có xử lý N+1 bằng batch/lookup/projection?
17. Có ước lượng write amplification?
18. Có event ID/version/CDC để chống duplicate/out-of-order?
19. Có TTL/retention/privacy deletion policy?
20. Có tenant access checks trên joins/edges?
21. Có metrics latency, request units, bytes và IOPS?
22. Có benchmark với representative skew và data size?
23. Có business invariant tests cho booking/payment?
24. Có keyset/value reconciliation khi migration?
25. Có ADR và mốc đánh giá lại model?

## 54. Tổng kết

1. **Access patterns quyết định NoSQL physical model**, không phải chỉ tên các thực thể trong ERD.
2. **Embedding** phù hợp dữ liệu nhỏ, bounded, cùng ownership và thường đọc/ghi cùng.
3. **Referencing** phù hợp thực thể độc lập, tăng không giới hạn hoặc cần query/pagination riêng.
4. **Edge records** phù hợp many-to-many, quan hệ có thuộc tính và truy vấn hai chiều.
5. **Mô hình hỗn hợp** thường hợp lý: listing nhúng amenities/preview, review/booking riêng, favorite edges, booking nhúng immutable price snapshot.
6. **N+1 là vấn đề của cách truy vấn**, có thể khắc phục bằng batch-get, indexed lookup hoặc projection.
7. **Document size/hot partition là giới hạn thực**, không thể giải chỉ bằng thêm index.
8. **Denormalization tạo write amplification và consistency responsibilities**, cần authority, CDC, version và reconciliation.
9. **Atomicity đúng phạm vi API**: một document update không tự giải quyết transaction booking/inventory/payment.
10. **MongoDB, DynamoDB, Cassandra, graph và search có những access primitives khác nhau**, cần thiết kế theo engine thực tế.
11. **Business correctness quan trọng hơn việc mọi bản copy giống nhau**, đặc biệt với historical snapshots, payments, deletes và tenant privacy.
12. **Model phải được đo đạc và có đường thay đổi**, vì cardinality, traffic và product features sẽ phát triển.

**Nguyên tắc thực hành:** Với mỗi quan hệ NoSQL, hãy hỏi **“có đọc cùng parent thường xuyên không?”, “có giới hạn số phần tử thật không?”, “ai sở hữu và cập nhật?”, “có cần phân trang/truy vấn ngược không?”, “atomicity và freshness cần tới đâu?”**. Trả lời năm câu hỏi ấy bằng truy vấn thật, số liệu và bất biến nghiệp vụ sẽ giúp quyết định hợp lý **nhúng, tham chiếu hoặc lưu quan hệ theo cách truy cập**.
