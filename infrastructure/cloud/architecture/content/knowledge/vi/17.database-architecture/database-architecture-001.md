# Lựa chọn quan hệ, key–value, tài liệu, đồ thị và chuỗi thời gian

Database là một quyết định kiến trúc có ảnh hưởng lâu dài. Một hệ thống đặt chỗ cần bảo đảm hai người không cùng giữ một phòng; giỏ hàng cần đọc và cập nhật nhanh theo người dùng; hồ sơ sản phẩm có thuộc tính thay đổi theo loại hàng; mạng lưới quan hệ cần tìm đường kết nối; hệ thống giám sát phải ghi và truy vấn hàng triệu điểm đo theo thời gian. Không có một mô hình dữ liệu duy nhất tối ưu cho tất cả các trường hợp này.

Các nhóm database phổ biến giải quyết những kiểu truy cập khác nhau:

- **Quan hệ (relational):** dữ liệu có cấu trúc, quan hệ rõ, truy vấn kết hợp và transaction.
- **Key–value:** truy cập trực tiếp một giá trị bằng khóa, thường tối ưu cho độ trễ thấp và thông lượng lớn.
- **Tài liệu (document):** lưu đối tượng gần với cấu trúc nghiệp vụ, linh hoạt về trường và lồng nhau.
- **Đồ thị (graph):** biểu diễn thực thể cùng quan hệ, hỗ trợ truy vấn theo đường đi và kết nối nhiều bước.
- **Chuỗi thời gian (time-series):** tối ưu cho dữ liệu đo đạc có timestamp, truy vấn theo cửa sổ thời gian và tổng hợp theo chu kỳ.

Đây là các **mô hình dữ liệu và kiểu workload**, không phải danh sách sản phẩm tương ứng một-một. Một database có thể hỗ trợ nhiều mô hình, nhưng mức độ tối ưu và giới hạn khác nhau. Thiết kế tốt bắt đầu từ yêu cầu nghiệp vụ, cách đọc/ghi, tính nhất quán, quy mô, bảo mật, vận hành và chi phí; sau đó mới chọn công nghệ.

Bài học thuộc chương **Kiến trúc cơ sở dữ liệu** của module **CLOUD_ARCHITECTURE**. Mục tiêu là hiểu cách lựa chọn database phù hợp với ứng dụng cloud, phân định quyền sở hữu dữ liệu và đánh giá đánh đổi giữa hiệu năng, độ tin cậy, khả năng mở rộng, bảo mật, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt mô hình quan hệ, key–value, tài liệu, đồ thị và chuỗi thời gian.
2. Chuyển yêu cầu nghiệp vụ thành entity, relationship, access pattern và workload.
3. Chọn mô hình dữ liệu dựa trên transaction, consistency, truy vấn, tốc độ ghi/đọc và cách mở rộng.
4. Giải thích khác biệt giữa schema linh hoạt và schema có kiểm soát; giữa normalize và denormalize.
5. Thiết kế khóa, index, partition/shard và TTL theo access pattern.
6. Nhận diện rủi ro khi dùng nhiều database, đồng bộ dữ liệu và xây dựng projection.
7. Đánh giá HA/DR, backup/restore, bảo mật, residency, quan sát và chi phí toàn vòng đời.
8. Đưa ra lựa chọn có căn cứ bằng decision matrix, prototype, benchmark và Architecture Decision Record (ADR).

## 2. Bắt đầu từ workload thay vì tên công nghệ

### 2.1. Mô tả cách ứng dụng sử dụng dữ liệu

Trước khi chọn database, trả lời các câu hỏi:

| Nhóm câu hỏi | Ví dụ cần làm rõ |
|---|---|
| Thực thể | Booking, Customer, Listing, Payment, Device, Relationship? |
| Quan hệ | Một-nhiều, nhiều-nhiều, phân cấp, đường đi nhiều bước? |
| Truy vấn | Tìm theo ID, filter nhiều trường, join, aggregate, traversal, range theo thời gian? |
| Tải | Read/write QPS, concurrency, burst, batch, dữ liệu tăng mỗi ngày? |
| Transaction | Cần cập nhật nhiều bản ghi cùng nguyên tử không? Phạm vi transaction ở đâu? |
| Consistency | Strong, read-your-writes, eventual, monotonic hay chấp nhận dữ liệu gần đúng? |
| Latency | p95/p99 mong muốn; đồng bộ hay bất đồng bộ? |
| Retention | Lưu bao lâu, xóa theo yêu cầu nào, có archive không? |
| Availability/DR | SLO, RTO, RPO, failure domain và quy trình phục hồi? |
| Bảo mật | Phân loại dữ liệu, tenant isolation, encryption, audit, residency? |
| Vận hành | Đội ngũ biết quản trị gì, công cụ backup/restore và migration nào? |

Một hệ thống có 10 triệu bản ghi chưa chắc cần distributed database. Một hệ thống có 100 nghìn bản ghi nhưng cần truy vấn đồ thị nhiều bước trong thời gian rất thấp có thể cần mô hình khác với relational.

### 2.2. Ma trận access pattern

Ví dụ một nền tảng đặt chỗ:

| Use case | Access pattern chính | Đặc tính |
|---|---|---|
| Tạo booking | Kiểm tra tồn chỗ rồi ghi booking/hold | Cần tính đúng đắn và transaction |
| Xem booking theo ID | Đọc một bản ghi theo khóa | Độ trễ thấp, thường xuyên |
| Hiển thị listing | Đọc hồ sơ có nhiều thuộc tính | Truy vấn theo ID và filter |
| Gợi ý chỗ tương tự | Duyệt quan hệ, đặc điểm và kết nối | Có thể cần graph hoặc search/index chuyên biệt |
| Phân tích conversion | Tổng hợp event theo khoảng thời gian | Batch/analytics hoặc time-series/warehouse |
| Theo dõi sức khỏe dịch vụ | Ghi metric liên tục, truy vấn time window | Time-series/metrics store |
| Giỏ hàng/session | Đọc/ghi theo user key, có TTL | Key–value/cache |

Từng access pattern có thể dùng một mô hình khác. Không nên đưa tất cả dữ liệu vào một database chỉ vì thuận tiện ban đầu, nhưng cũng không nên phân tán quá sớm khiến đội ngũ phải vận hành nhiều hệ thống.

### 2.3. Năm câu hỏi quyết định nhanh

1. **Dữ liệu có nhiều quan hệ và cần transaction giữa nhiều entity không?** Xem relational trước.
2. **Phần lớn thao tác là lấy/ghi một giá trị bằng key?** Xem key–value.
3. **Đối tượng có cấu trúc lồng nhau và trường biến động theo loại?** Xem document.
4. **Truy vấn cốt lõi đi qua nhiều quan hệ hoặc cần tìm đường?** Xem graph.
5. **Dữ liệu chủ yếu là measurement/event có timestamp và truy vấn theo thời gian?** Xem time-series.

Đây là bộ lọc đầu tiên, không phải luật tuyệt đối. Sau đó vẫn cần kiểm tra transaction, index, consistency, khả năng scale, quota, giới hạn truy vấn và chi phí của sản phẩm cụ thể.

## 3. Database quan hệ (Relational Database)

### 3.1. Mô hình bảng, hàng, cột và khóa

Relational database tổ chức dữ liệu thành bảng. Mỗi bảng biểu diễn một loại thực thể hoặc quan hệ; hàng là bản ghi; cột là thuộc tính. Primary key định danh hàng; foreign key liên kết bản ghi giữa các bảng.

Ví dụ mô hình đặt chỗ:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    full_name   VARCHAR(200) NOT NULL
);

CREATE TABLE listings (
    listing_id BIGINT PRIMARY KEY,
    title      VARCHAR(300) NOT NULL,
    city_code  VARCHAR(30) NOT NULL
);

CREATE TABLE bookings (
    booking_id  BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    listing_id  BIGINT NOT NULL REFERENCES listings(listing_id),
    check_in    DATE NOT NULL,
    check_out   DATE NOT NULL,
    status      VARCHAR(30) NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
~~~

Mô hình này thể hiện rõ booking thuộc khách hàng và listing nào. Database có thể kiểm tra một số ràng buộc bằng foreign key, unique constraint, check constraint và transaction.

### 3.2. ACID và transaction

Relational database thường cung cấp transaction với các thuộc tính ACID:

- **Atomicity:** các thao tác trong transaction cùng thành công hoặc cùng rollback.
- **Consistency:** transaction đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ theo các constraint và invariant được định nghĩa.
- **Isolation:** transaction đồng thời được kiểm soát theo isolation level; tránh các tương tác không mong muốn tùy mức đảm bảo.
- **Durability:** sau khi commit thành công theo cam kết của database, thay đổi được lưu bền vững trong các điều kiện lỗi mà hệ thống hỗ trợ.

ACID không tự đảm bảo code nghiệp vụ đúng. Ví dụ, hai transaction đều đọc thấy còn một phòng rồi cùng ghi booking có thể tạo đặt trùng nếu mô hình khóa/constraint và cách transaction không bảo vệ invariant. Cần thiết kế unique/exclusion constraint, lock, isolation hoặc một cơ chế reservation phù hợp.

### 3.3. JOIN và truy vấn quan hệ

SQL hỗ trợ truy vấn kết hợp dữ liệu:

~~~sql
SELECT
    b.booking_id,
    c.full_name,
    l.title,
    b.check_in,
    b.check_out,
    b.status
FROM bookings AS b
JOIN customers AS c
  ON c.customer_id = b.customer_id
JOIN listings AS l
  ON l.listing_id = b.listing_id
WHERE b.customer_id = 10042
ORDER BY b.created_at DESC;
~~~

JOIN giúp tránh sao chép toàn bộ thông tin khách hàng/listing vào mọi booking. Tuy nhiên, join nhiều bảng và truy vấn không có index phù hợp có thể tốn tài nguyên khi dữ liệu lớn.

### 3.4. Normalize và denormalize

**Normalization** tách dữ liệu để giảm trùng lặp và tránh anomaly khi insert/update/delete. **Denormalization** lưu thêm dữ liệu đã tổng hợp hoặc sao chép có chủ đích để tối ưu truy vấn đọc.

| Cách tiếp cận | Lợi ích | Đánh đổi |
|---|---|---|
| Normalize | Dữ liệu chuẩn hóa, cập nhật một nơi, constraint rõ | Nhiều JOIN, một số truy vấn phức tạp |
| Denormalize | Đọc nhanh, giảm số lần join, phù hợp read model | Cần đồng bộ bản sao, có thể eventual consistency, tăng storage |

Ví dụ, booking có thể lưu listing_title_at_booking để giữ tên hiển thị tại thời điểm đặt. Đây không nhất thiết là bản sao thừa; nó có thể là snapshot nghiệp vụ có chủ đích. Ngược lại, sao chép email hiện tại của customer vào mọi bảng chỉ để tránh join có thể làm dữ liệu lệch khi người dùng đổi email.

### 3.5. Khi nào relational phù hợp?

- Giao dịch nghiệp vụ có invariant và transaction rõ.
- Dữ liệu có quan hệ nhiều-nhiều hoặc truy vấn JOIN.
- Cần constraint, unique key, foreign key và SQL.
- Báo cáo/truy vấn linh hoạt trên dữ liệu có cấu trúc.
- Đội ngũ có năng lực schema migration, index, transaction và backup.

### 3.6. Giới hạn cần lưu ý

- Scale write ngang qua nhiều shard có thể làm transaction và join phức tạp.
- Connection, lock, hot row và index có thể thành bottleneck.
- Schema migration phải tương thích ứng dụng đang chạy.
- Replica đọc có thể có lag; đọc từ replica không luôn thỏa read-after-write.
- Một database đơn lẻ vẫn cần HA, backup và DR; ACID không thay thế các cơ chế đó.

## 4. Database key–value

### 4.1. Mô hình khóa và giá trị

Key–value store lưu một mapping giữa khóa duy nhất và giá trị. Ứng dụng truy xuất dữ liệu bằng key, thường không cần scan hay join theo nhiều thuộc tính.

~~~text
Key: session:user:10042
Value: {
  "cartId": "cart_913",
  "locale": "vi-VN",
  "lastActivity": "2026-11-18T09:30:00Z"
}
~~~

Một số hệ thống lưu value dạng chuỗi/bytes; một số hỗ trợ cấu trúc hash, list, set hoặc sorted set. Cần xem semantics và atomic operation của sản phẩm cụ thể.

### 4.2. Access pattern ưu tiên

Key–value phù hợp khi truy vấn chủ yếu là:

- GET(key) – đọc giá trị.
- PUT/SET(key, value) – tạo hoặc ghi đè.
- DELETE(key) – xóa.
- Cập nhật nguyên tử một phần giá trị hoặc counter nếu được hỗ trợ.
- TTL để tự hết hạn session/cache.

Không nên chọn key–value rồi mong đợi truy vấn JOIN linh hoạt hoặc filter tùy ý theo nhiều trường như relational database, trừ khi sản phẩm có khả năng query/index thích hợp và được benchmark.

### 4.3. Ví dụ giỏ hàng/session

~~~text
cart:user:10042 -> {
  items: [
    { listingId: "L-42", quantity: 1 },
    { listingId: "L-57", quantity: 2 }
  ],
  updatedAt: "2026-11-18T09:30:00Z"
}

TTL = thời gian không hoạt động được nghiệp vụ chấp nhận
~~~

Ứng dụng lấy giỏ hàng trong một lần truy cập theo key. Khi người dùng đăng nhập lại, hệ thống có thể tải giỏ hàng từ store. Tuy nhiên, giỏ hàng không phải nguồn xác nhận tồn kho hay booking; khi checkout vẫn phải kiểm tra và thực hiện transaction ở dịch vụ dữ liệu có thẩm quyền.

### 4.4. Cache hay database key–value?

Một cache key–value có thể lưu dữ liệu có thể tái tạo và dùng TTL/eviction. Một key–value database có thể được thiết kế cho độ bền, replication và trạng thái nghiệp vụ. Phải phân biệt:

- Cache miss có thể lấy lại từ nguồn chuẩn.
- Dữ liệu bền vững không thể mất chỉ vì eviction.
- Cache invalidation và write-through/write-behind có semantics khác nhau.
- Nếu dùng cache làm nguồn chuẩn, cần kiểm tra khả năng persistence, backup, consistency và recovery của đúng sản phẩm.

### 4.5. Partitioning và hot key

Key thường được hash hoặc phân phối vào partition/shard. Khóa tốt giúp phân bổ đều. Một key phổ biến bị truy cập quá nhiều (hot key) có thể làm một partition quá tải dù cluster còn capacity tổng thể.

Ví dụ, dùng một global homepage counter làm key cho mọi lượt truy cập có thể dồn tải vào một điểm. Có thể phân tán counter theo bucket/shard rồi tổng hợp, nếu nghiệp vụ không yêu cầu cập nhật một khóa toàn cục tức thời.

### 4.6. Khi nào key–value phù hợp?

- Session, token metadata, cart, preference truy cập theo ID.
- Cache, feature flag, counter hoặc rate limit.
- Lookup có khóa rõ, yêu cầu latency thấp và throughput lớn.
- Trạng thái thiết bị hoặc job được định danh bằng key.

Không phù hợp khi workload chủ yếu đòi hỏi truy vấn quan hệ phức tạp, transaction nhiều entity hoặc tìm kiếm tùy ý theo thuộc tính mà store không hỗ trợ.

## 5. Database tài liệu (Document Database)

### 5.1. Tổ chức dữ liệu theo document

Document database lưu bản ghi dưới dạng document, thường dùng JSON/BSON hoặc định dạng tương tự. Document có thể chứa object lồng nhau, array và trường tùy chọn.

~~~json
{
  "_id": "listing_42",
  "title": "Căn hộ gần trung tâm",
  "location": {
    "city": "Da Nang",
    "district": "Hai Chau"
  },
  "amenities": ["wifi", "parking", "kitchen"],
  "pricing": {
    "currency": "VND",
    "basePrice": 950000
  },
  "policies": {
    "smokingAllowed": false,
    "checkInFrom": "14:00"
  }
}
~~~

Document gần với object ứng dụng và có thể đọc/ghi theo aggregate. Nhiều document database hỗ trợ index trên trường lồng nhau, filter, aggregation và transaction trong một hoặc nhiều document tùy sản phẩm.

### 5.2. Embed hay reference?

**Embed** dữ liệu con trong cùng document khi nó thường được đọc cùng nhau, kích thước có giới hạn và vòng đời gắn với document cha.

**Reference** bằng ID khi dữ liệu con có vòng đời độc lập, có thể lớn không giới hạn, được nhiều đối tượng dùng chung hoặc cần cập nhật tách biệt.

| Trường hợp | Cách cân nhắc |
|---|---|
| Địa chỉ hiển thị snapshot của listing | Có thể embed |
| Danh sách tiện nghi nhỏ, thường đọc cùng listing | Có thể embed |
| Hàng triệu review có pagination | Lưu collection riêng, tham chiếu listingId |
| Customer được nhiều booking tham chiếu | Thường lưu riêng và reference |
| Chính sách nhỏ, chỉ thuộc một document | Embed có thể đơn giản hơn |

Embed quá nhiều có thể làm document lớn, tăng write amplification và cạnh tranh khi nhiều tiến trình cập nhật cùng document. Reference quá nhiều lại tạo nhiều round-trip hoặc yêu cầu join ở tầng ứng dụng.

### 5.3. Schema linh hoạt không có nghĩa không cần schema

Document database có thể cho phép các document cùng collection khác nhau về trường, nhưng ứng dụng vẫn cần quy ước:

- Trường bắt buộc, kiểu dữ liệu, default và format.
- Quy tắc version và migration document cũ.
- Index bắt buộc và cách truy vấn.
- Quy ước null, missing field và giá trị mặc định.
- Kiểm tra dữ liệu tại application hoặc schema validation của database.

Nếu không kiểm soát, cùng một khái niệm có thể lần lượt lưu price, basePrice, amount hoặc kiểu số/string khác nhau, khiến truy vấn và báo cáo khó tin cậy.

### 5.4. Index và truy vấn

Index hỗ trợ truy vấn theo field nhưng làm tăng storage và chi phí ghi. Compound index phụ thuộc thứ tự field và access pattern. Cần phân tích query plan, selectivity, sort, pagination và index coverage.

Tránh tạo index cho mọi trường “phòng khi cần”: mỗi lần ghi phải cập nhật thêm index và index lớn ảnh hưởng cache/backup. Thiết kế theo truy vấn thực tế.

### 5.5. Khi nào document phù hợp?

- Hồ sơ có cấu trúc phong phú, nested và thay đổi theo loại.
- Đọc/ghi thường xoay quanh một document hoặc aggregate.
- Cần mở rộng trường linh hoạt theo tốc độ phát triển sản phẩm.
- Truy vấn chủ yếu dựa trên ID, filter/index đã định nghĩa.

Không tự động phù hợp khi nhiều document phải cập nhật nguyên tử cùng nhau hoặc cần join và constraint quan hệ phức tạp. Kiểm tra transaction scope và giới hạn document của sản phẩm trước khi quyết định.

## 6. Database đồ thị (Graph Database)

### 6.1. Node và edge

Graph database biểu diễn dữ liệu bằng:

- **Node/vertex:** thực thể như Customer, Listing, Device hoặc Organization.
- **Edge/relationship:** kết nối giữa các node như BOOKED, FRIEND_OF, LOCATED_IN hoặc DEPENDS_ON.
- **Properties:** thuộc tính gắn với node hoặc edge.

~~~mermaid
flowchart LR
    C[Customer A] -->|BOOKED| B[Booking 913]
    B -->|FOR_LISTING| L[Listing 42]
    C -->|REFERRED| C2[Customer B]
    C2 -->|BOOKED| B2[Booking 821]
    B2 -->|FOR_LISTING| L2[Listing 57]
    L -->|NEAR| L2
~~~

Điểm mạnh của graph là truy vấn quan hệ và đường đi nhiều bước. Ví dụ: tìm khách hàng có quan hệ giới thiệu với người đã đặt listing trong một khu vực, hoặc phân tích dịch vụ phụ thuộc trực tiếp/gián tiếp vào một service lỗi.

### 6.2. Truy vấn traversal

Trong relational database, truy vấn nhiều bước có thể cần nhiều JOIN đệ quy hoặc recursive CTE. Graph database có thể biểu diễn việc đi qua edge bằng ngôn ngữ truy vấn riêng (ví dụ Cypher ở một số sản phẩm).

~~~cypher
MATCH (c:Customer {id: "customer_100"})
      -[:REFERRED*1..3]->(other:Customer)
      -[:BOOKED]->(b:Booking)
      -[:FOR_LISTING]->(l:Listing)
WHERE l.city = "Da Nang"
RETURN DISTINCT other, b, l;
~~~

Đây là ví dụ cú pháp Cypher; cú pháp, khả năng và hiệu năng phụ thuộc graph engine. Phải giới hạn độ sâu và số kết quả, bởi traversal mở rộng không kiểm soát có thể tăng chi phí rất nhanh.

### 6.3. Khi nào graph phù hợp?

- Mạng lưới quan hệ xã hội, giới thiệu hoặc tổ chức.
- Phát hiện gian lận qua chuỗi tài khoản/thiết bị/giao dịch.
- Knowledge graph và tìm kiếm dựa trên liên kết ngữ nghĩa.
- Dependency graph, impact analysis và topology.
- Truy vấn đường đi, kết nối nhiều bước là workload cốt lõi.

Graph không mặc nhiên tốt hơn relational cho mọi dữ liệu có quan hệ. Nếu truy vấn chỉ là lấy một booking theo ID hoặc join hai bảng ổn định, relational có thể đơn giản và hiệu quả hơn.

### 6.4. Mô hình graph cần kiểm soát

Xác định node label, edge type, direction, cardinality và property. Tránh tạo nhiều loại quan hệ gần trùng nghĩa hoặc cho phép traversal không giới hạn. Cần xem index theo node property, uniqueness, transaction, partitioning và khả năng HA của graph engine.

## 7. Database chuỗi thời gian (Time-series Database)

### 7.1. Đặc tính dữ liệu

Time-series database tối ưu cho các điểm dữ liệu gắn với thời gian: timestamp, metric name, tags/dimensions và value.

Ví dụ:

~~~text
timestamp             metric             service       value
2026-11-18T09:00:00Z  api_latency_ms     booking-api   42
2026-11-18T09:00:05Z  api_latency_ms     booking-api   51
2026-11-18T09:00:10Z  api_latency_ms     booking-api   47
2026-11-18T09:00:15Z  cpu_utilization    worker-2      68.2
~~~

Workload thường có lượng ghi liên tục, append-heavy, truy vấn theo time window và tổng hợp theo chu kỳ. Database có thể tối ưu compression, retention, downsampling và partition theo thời gian.

### 7.2. Time, tags và cardinality

Một điểm dữ liệu có thể gồm:

- Timestamp với độ chính xác và timezone được thống nhất.
- Measurement/metric name.
- Tags/dimensions như service, region, environment.
- Numeric value hoặc field data.

Tags có cardinality cao như requestId, userId hoặc bookingId có thể tạo rất nhiều series và làm tăng memory, index và chi phí. Chọn dimensions phục vụ truy vấn tổng hợp, không đưa mọi ID duy nhất thành tag.

### 7.3. Retention, downsampling và rollup

Không phải mọi dữ liệu đo lường phải lưu ở độ phân giải cao mãi mãi. Có thể:

- Giữ dữ liệu thô trong thời gian ngắn để điều tra.
- Tổng hợp phút/giờ/ngày để phân tích xu hướng dài hạn.
- Áp dụng retention khác nhau theo loại metric và yêu cầu audit.
- Lưu archive lâu dài ở object storage/warehouse khi cần.

Downsampling làm giảm dung lượng nhưng có thể mất chi tiết spike ngắn. Chọn phép tổng hợp phù hợp: average có thể che giấu outlier; max/p95/count có thể cần thiết cho mục tiêu giám sát.

### 7.4. Khi nào time-series phù hợp?

- Metrics hạ tầng và ứng dụng.
- Telemetry thiết bị/IoT.
- Giá, tỷ giá hoặc số đo thay đổi theo thời gian.
- Theo dõi hành vi/tải theo time window.
- Phân tích trend, alert, rollup và retention.

Time-series store không phải lựa chọn mặc định cho transaction booking/customer. Nếu cần cập nhật một trạng thái nghiệp vụ hiện tại và constraint quan hệ, relational hoặc key-value thường phù hợp hơn.

## 8. So sánh tổng hợp năm mô hình

| Tiêu chí | Relational | Key–value | Document | Graph | Time-series |
|---|---|---|---|---|---|
| Cấu trúc | Bảng, schema rõ | Key → value | Document lồng nhau | Node và edge | Timestamp + measurement/tags |
| Truy vấn nổi bật | SQL, JOIN, aggregate | Lookup theo key | Filter/index theo field | Traversal và path | Time range, rollup |
| Transaction | Thường mạnh, ACID | Tùy sản phẩm/phạm vi key | Tùy engine và phạm vi | Tùy engine | Thường tối ưu ingest/query time hơn transaction liên thực thể |
| Schema | Khai báo rõ | Value linh hoạt | Linh hoạt nhưng cần validation | Schema/label/relationship tùy engine | Measurement/tag/field |
| Scale | Vertical, read replica, sharding | Partition/hash, distributed | Shard/partition theo key | Phụ thuộc graph engine, traversal locality | Partition theo time/tag/shard |
| Phù hợp | Giao dịch và quan hệ | Session, cache, lookup | Hồ sơ, catalog, aggregate | Quan hệ nhiều bước | Metrics, telemetry, measurement |
| Rủi ro | Lock, join, connection, shard transaction | Hot key, query hạn chế | Document lớn, schema drift | Traversal bùng nổ, phân vùng graph | Cardinality, retention, ingest burst |

Không có cột nào là tiêu chí đủ để chọn database. Cần đánh giá sản phẩm cụ thể về durability, HA, backup, consistency, encryption, region, quota, SLA và khả năng vận hành.

## 9. Schema, khóa và index

### 9.1. Chọn khóa định danh

Khóa cần ổn định, duy nhất trong phạm vi yêu cầu và hỗ trợ access pattern. Một số lựa chọn:

- **Natural key:** email hoặc mã nghiệp vụ; có thể thay đổi và chứa thông tin nhạy cảm.
- **Surrogate key:** ID do hệ thống tạo; ít phụ thuộc nội dung nghiệp vụ.
- **Composite key:** kết hợp tenantId và entityId hoặc partition key + sort key.

Nếu hệ thống đa tenant, phải cân nhắc tenant ID trong khóa/index/partition để ngăn đọc nhầm giữa tenant và tránh một tenant lớn tạo hotspot. Khóa không phải cơ chế authorization; service vẫn cần kiểm tra quyền với tenant và tài nguyên.

### 9.2. Index có chi phí

Index tăng tốc đọc nhưng dùng storage và làm chậm một số thao tác ghi. Cần:

- Tạo index theo truy vấn thực tế.
- Phân tích selectivity và query plan.
- Kiểm tra sort/pagination, composite index order.
- Xem index maintenance và build trên bảng lớn.
- Loại bỏ index không dùng sau khi có số liệu.

### 9.3. Partitioning và sharding

**Partitioning** chia dữ liệu thành phần để quản lý hoặc truy vấn hiệu quả; có thể theo range, list, hash hoặc time. **Sharding** phân phối dữ liệu trên nhiều node/database để mở rộng dung lượng và thông lượng.

Chọn partition/shard key cần cân bằng:

- Phân phối đều tải và dung lượng.
- Giữ các truy vấn thường gặp trong ít partition.
- Hỗ trợ transaction và ordering cần thiết.
- Hạn chế hot partition/hot tenant.
- Có thể thay đổi hoặc rebalance khi tăng quy mô.

Partition theo ngày giúp quản lý time-series nhưng một truy vấn không có điều kiện thời gian có thể phải quét nhiều partition. Shard theo customerId thuận cho truy vấn từng customer nhưng báo cáo toàn hệ thống có thể cần fan-out.

### 9.4. Pagination và truy vấn không giới hạn

OFFSET sâu có thể đắt ở bảng lớn. Keyset pagination dựa trên khóa sắp xếp ổn định có thể hiệu quả hơn:

~~~sql
SELECT booking_id, created_at, status
FROM bookings
WHERE customer_id = 10042
  AND (created_at, booking_id) < (:last_created_at, :last_booking_id)
ORDER BY created_at DESC, booking_id DESC
LIMIT 50;
~~~

Cú pháp tuple comparison tùy database. Cần có index phù hợp và xác định cách xử lý bản ghi mới trong khi client tiếp tục phân trang.

## 10. Consistency và transaction boundary

### 10.1. Strong consistency và eventual consistency

Một số nghiệp vụ cần đọc thấy ngay thay đổi vừa commit; một số read model có thể cập nhật trễ trong vài giây. Chọn database phải gắn với yêu cầu:

- **Strong/read-after-write consistency:** phù hợp xác nhận booking, trừ tồn kho hoặc thao tác cần invariant.
- **Eventual consistency:** có thể phù hợp search projection, analytics hoặc cache.
- **Monotonic/read-your-writes:** cần khi client không được quay lại trạng thái cũ sau cập nhật.
- **Bounded staleness:** có thể chấp nhận trễ tối đa đã định nghĩa nếu database/ứng dụng hỗ trợ và kiểm chứng.

Không dùng nhãn eventual để bỏ qua thiết kế đối soát hoặc dữ liệu có thể bị mất.

### 10.2. Transaction trong một service

Một service nên sở hữu transaction và invariant của dữ liệu mình quản lý. Ví dụ Booking Service có thể commit booking và outbox record trong cùng database transaction. Service khác nhận event và cập nhật projection riêng.

Không nên giả định transaction của một database tự bao phủ key–value store, event broker, graph store và time-series database. Khi cần phối hợp nhiều hệ thống, cân nhắc Saga, outbox/inbox, idempotency và reconciliation.

### 10.3. Read model và CQRS

Có thể dùng relational làm nguồn chuẩn cho giao dịch nhưng xây dựng document/search/graph/time-series projection cho truy vấn chuyên biệt. Đây là cách tách write model và read model (CQRS) khi lợi ích đáng kể.

Đánh đổi:

- Dữ liệu được sao chép và có độ trễ đồng bộ.
- Có nhiều schema, index, consumer và quy trình rebuild.
- Cần theo dõi freshness, lag, duplicate và lỗi projection.
- Client cần biết nguồn nào có thẩm quyền cho câu hỏi đang hỏi.

Không nên dùng CQRS chỉ để áp dụng nhiều công nghệ. Bắt đầu từ một database đơn giản nếu nó đáp ứng được workload và SLO.

## 11. Multi-database và polyglot persistence

### 11.1. Chọn store theo access pattern

Polyglot persistence là sử dụng nhiều loại database trong cùng một hệ thống, mỗi store phục vụ một workload phù hợp. Ví dụ:

~~~mermaid
flowchart TB
    APP[Application services]
    APP --> SQL[(Relational: booking / payment)]
    APP --> KV[(Key-value: session / cache)]
    APP --> DOC[(Document: listing profile)]
    APP --> GRAPH[(Graph: recommendation relations)]
    APP --> TS[(Time-series: metrics / telemetry)]
    SQL --> OUT[Outbox / event pipeline]
    OUT --> PROJ[Projection consumers]
    PROJ --> DOC
    PROJ --> GRAPH
    PROJ --> TS
~~~

### 11.2. Lợi ích và chi phí

**Lợi ích:** store được tối ưu theo workload, giảm truy vấn không phù hợp, scale từng thành phần độc lập và chọn tính năng chuyên biệt.

**Chi phí:** thêm hệ thống cần backup, security patch, monitoring, capacity planning, schema/version, failover, on-call và quản lý credential. Đồng bộ giữa các store có thể eventually consistent và có thể sai lệch.

### 11.3. Xác định system of record

Mỗi loại dữ liệu cần một owner rõ:

| Dữ liệu | System of record có thể là | Các bản sao |
|---|---|---|
| Booking status | Booking relational database | Search index, analytics |
| Payment status | Payment database/provider reconciliation record | Booking projection, ledger/report |
| Listing profile | Listing database/document store | Cache, search, graph features |
| Session | Key–value store hoặc identity/session service | Có thể không cần bản sao lâu dài |
| Service metrics | Metrics/time-series backend | Archive/warehouse |
| Quan hệ gợi ý | Graph/feature store tùy nghiệp vụ | Cache/model input |

Không nên để hai database cùng được xem là nguồn chuẩn cho cùng một trường trạng thái mà không có quy tắc phân quyền ghi và đồng bộ. Khi có tranh chấp, phải biết owner nào có quyền quyết định.

### 11.4. Data synchronization

Outbox/CDC, event stream hoặc batch ETL có thể đồng bộ từ system of record sang projection. Cần quy định:

- Schema và version event.
- Deduplication và ordering.
- Retry, DLQ và replay.
- Xử lý delete và dữ liệu hết hạn.
- Backfill/rebuild.
- SLO freshness và đối soát.

## 12. Bảo mật, tenancy và quản trị dữ liệu

### 12.1. Bảo mật theo lớp

- Network: private endpoint, subnet, firewall/security group và egress policy.
- Identity: workload identity, IAM/DB role và least privilege.
- Data: encryption at rest/in transit, key management và rotation.
- Query: parameterized query, tránh SQL/NoSQL injection.
- Audit: ghi nhận truy cập và thay đổi cấu hình nhạy cảm.
- Backup: mã hóa, quyền truy cập riêng và kiểm thử khôi phục.

### 12.2. Tenant isolation

Các mô hình phổ biến:

| Mô hình | Cách cô lập | Đánh đổi |
|---|---|---|
| Shared database/shared schema | tenantId trong row/key | Chi phí thấp, yêu cầu mọi query/rule lọc tenant chính xác |
| Shared database/separate schema | Mỗi tenant một schema | Cô lập logic hơn, migration/connection phức tạp |
| Database per tenant | Mỗi tenant database riêng | Cô lập mạnh hơn, chi phí và vận hành cao |
| Hybrid | Tenant lớn dùng riêng, tenant nhỏ dùng chung | Linh hoạt nhưng cần routing và quản lý phân lớp |

Tenant isolation cần được thực thi tại server-side authorization và database policy phù hợp. Không tin tenantId từ request nếu chưa xác thực với danh tính.

### 12.3. Data residency và lifecycle

Phân loại dữ liệu, xác định region xử lý/lưu trữ, replica, backup, archive và log. Một database nằm trong region được duyệt nhưng replica, export, CDC hoặc analytics chuyển dữ liệu sang khu vực khác vẫn có thể vi phạm policy.

Xác định retention theo loại dữ liệu, xóa dữ liệu, legal hold, backup expiry và cách xử lý bản sao trong cache/index. Không mặc định TTL của cache thay thế nghĩa vụ xóa ở system of record và projection.

## 13. HA, backup và disaster recovery

### 13.1. High availability khác backup

HA giúp tiếp tục phục vụ khi thành phần gặp lỗi trong failure domain được hỗ trợ. Backup giúp phục hồi dữ liệu từ một thời điểm hoặc bản sao; nó bảo vệ cả một số tình huống xóa nhầm hoặc hỏng logic mà replication có thể sao chép sang replica.

Replication không phải backup. Nếu ứng dụng xóa nhầm hàng triệu bản ghi và thay đổi được replicate, replica cũng có thể mất dữ liệu.

### 13.2. RPO và RTO

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận, tính theo thời gian dữ liệu.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

Chọn HA/DR dựa trên mức quan trọng nghiệp vụ. Database đa zone có thể xử lý lỗi zone nhưng không nhất thiết bảo vệ khỏi lỗi region, account compromise hoặc corruption logic. Multi-region có thể giảm một số rủi ro nhưng thêm replication lag, conflict và chi phí.

### 13.3. Backup/restore phải được thử

Kế hoạch cần xác minh:

- Backup tự động, retention, point-in-time recovery.
- Snapshot consistency và transaction log coverage.
- Encryption key còn khả dụng khi restore.
- Restore sang tài khoản/region dự phòng nếu kịch bản yêu cầu.
- Quy trình kiểm tra dữ liệu sau restore.
- RTO/RPO đo thực tế trong diễn tập.

Một backup job báo SUCCESS không chứng minh ứng dụng có thể khởi động từ bản backup đó. Chỉ restore test mới kiểm tra được khả năng dùng dữ liệu.

## 14. Hiệu năng và capacity của database

### 14.1. Những giới hạn cần đo

| Tài nguyên | Chỉ số |
|---|---|
| Compute | CPU, memory, cache, connection pool |
| Storage | Dung lượng, IOPS, throughput, disk latency |
| Query | p50/p95/p99 latency, slow query, scan rows |
| Concurrency | Active connections, locks, waits, transaction duration |
| Replication | Lag, apply rate, failover time |
| Network | Throughput, round trip, cross-zone/region traffic |
| Workload | Read/write QPS, transaction rate, payload size, burst |

### 14.2. Connection pooling

Ứng dụng serverless có thể tạo nhiều function instance đồng thời, mỗi instance mở nhiều connection đến database. Connection count có thể tăng đột biến dù mỗi function nhẹ. Dùng connection pool/proxy phù hợp, giới hạn concurrency và kiểm thử cold start/fan-out.

Pool quá lớn có thể làm database bão hòa; pool quá nhỏ làm request chờ. Cần sizing theo concurrency, thời gian giữ connection và giới hạn database.

### 14.3. Read replica và cache

Read replica có thể phân tải truy vấn đọc nhưng có lag. Cache giảm số lần query nguồn nhưng phát sinh invalidation, staleness và rủi ro dữ liệu riêng tư. Cần xác định use case có thể đọc dữ liệu cũ, TTL, cache key và read-after-write fallback.

### 14.4. Query plan và benchmark

Đo bằng workload thực tế, dữ liệu đủ lớn và phân bố gần production. Kiểm tra query plan, index, lock, cache hit, connection, concurrency và tail latency. Một query chạy nhanh trên bảng nhỏ không chứng minh scale được ở dữ liệu lớn.

## 15. Migration và tiến hóa schema

### 15.1. Schema migration

Thay đổi schema có thể tác động ứng dụng đang chạy. Dùng chiến lược expand–migrate–contract:

1. Expand: thêm cột/bảng/index mới theo cách tương thích.
2. Deploy ứng dụng có thể đọc/ghi cấu trúc cũ và mới trong giai đoạn chuyển tiếp.
3. Backfill dữ liệu theo batch có giới hạn tải.
4. Chuyển đọc sang cấu trúc mới và xác minh.
5. Contract: bỏ cấu trúc cũ khi mọi phiên bản ứng dụng đã ngừng dùng.

### 15.2. Document schema evolution

Với document store, tài liệu cũ có thể thiếu trường mới hoặc dùng kiểu cũ. Có thể migration lúc đọc, batch backfill hoặc dual-read/dual-write trong giai đoạn chuyển đổi. Cần theo dõi phần trăm dữ liệu đã migrate và deadline retire code tương thích cũ.

### 15.3. Graph và time-series evolution

Graph schema cần quản lý node label, relationship type và property; thay đổi tên edge có thể làm hỏng query traversal. Time-series cần quản lý measurement/tag, cardinality và retention; thay đổi tag dimension có thể tạo series mới và làm tăng index/storage.

## 16. Ví dụ quyết định kiến trúc cho nền tảng đặt chỗ

Giả sử nền tảng cần:

- Không xác nhận hai booking cho cùng inventory/time slot.
- Đọc booking theo ID và danh sách booking của customer.
- Hiển thị listing với nhiều thuộc tính thay đổi theo loại.
- Tìm kiếm listing theo địa điểm/tiện nghi.
- Gợi ý liên quan qua quan hệ.
- Quan sát metrics ứng dụng và phân tích lịch sử.

### 16.1. Mô hình đề xuất

| Workload | Mô hình có thể chọn | Vì sao |
|---|---|---|
| Booking và payment ledger | Relational | Transaction, constraint và truy vấn quan hệ |
| Session/cart/cache | Key–value | Lookup theo key, TTL, latency thấp |
| Listing profile | Document hoặc relational tùy access pattern | Thuộc tính đa dạng, đọc aggregate |
| Search theo địa điểm/tiện nghi | Search index chuyên biệt hoặc read projection | Truy vấn full-text/filter/geospatial |
| Recommendation relationships | Graph khi traversal là yêu cầu chính | Truy vấn đường đi/quan hệ nhiều bước |
| API/infra metrics | Time-series/metrics store | Ingest liên tục và time-window aggregation |

Đây là một phương án minh họa, không phải yêu cầu bắt buộc phải dùng sáu database. Nếu relational database và search service đáp ứng tốt, có thể trì hoãn graph hoặc document store để giảm chi phí vận hành.

### 16.2. Luồng ghi booking

~~~mermaid
sequenceDiagram
    participant API as Booking API
    participant SQL as Relational DB
    participant OUT as Outbox
    participant BUS as Event broker
    participant SEARCH as Search projection
    API->>SQL: Begin transaction
    API->>SQL: Validate inventory / create booking
    API->>OUT: Insert BookingConfirmed
    API->>SQL: Commit
    OUT->>BUS: Publish via CDC/publisher
    BUS->>SEARCH: Deliver event
    SEARCH->>SEARCH: Idempotent projection update
~~~

Relational database giữ dữ liệu có thẩm quyền cho booking. Search index được cập nhật bất đồng bộ; nếu người dùng cần đọc trạng thái ngay sau ghi, API đọc từ nguồn chuẩn hoặc dùng read-your-writes strategy.

### 16.3. Rủi ro phải ghi trong ADR

- Hệ thống nào là system of record cho từng entity/field?
- Làm sao tránh booking trùng khi request đồng thời?
- Search lag tối đa bao lâu là chấp nhận được?
- Document/graph projection được rebuild từ nguồn nào?
- Cache invalidation diễn ra khi booking/listing thay đổi ra sao?
- Tenant isolation, backup, encryption và residency áp dụng ở từng store thế nào?
- Ai trực và phục hồi khi một store/broker/CDC connector lỗi?
- Chi phí vận hành thêm database có tương xứng lợi ích truy vấn?

## 17. Decision matrix và quy trình lựa chọn

### 17.1. Ma trận có trọng số

Nhóm kiến trúc có thể chấm điểm từng mô hình theo tiêu chí từ 1–5. Trọng số tùy mức quan trọng của dự án.

| Tiêu chí | Trọng số ví dụ | Relational | Key–value | Document | Graph | Time-series |
|---|---:|---:|---:|---:|---:|---:|
| Transaction nhiều entity | 5 | 5 | 2 | 3 | 3 | 1 |
| Lookup theo key | 3 | 4 | 5 | 4 | 3 | 2 |
| Flexible nested document | 3 | 3 | 2 | 5 | 2 | 1 |
| Multi-hop relationship traversal | 4 | 2 | 1 | 2 | 5 | 1 |
| Time-window analytics | 4 | 3 | 1 | 2 | 1 | 5 |
| Workload telemetry ingest | 3 | 2 | 2 | 3 | 1 | 5 |
| SQL/reporting flexibility | 3 | 5 | 1 | 3 | 2 | 3 |

Điểm trên chỉ là minh họa khái quát, không phải benchmark sản phẩm. Trong decision record cần thay bằng kết quả prototype và kiểm chứng theo sản phẩm/phiên bản/region dự kiến.

### 17.2. Quy trình lựa chọn

1. Thu thập access pattern, volume, latency, consistency, retention, security và SLO.
2. Xác định system of record và ranh giới transaction.
3. Loại bỏ mô hình không đáp ứng yêu cầu bắt buộc.
4. Tạo prototype với dữ liệu và truy vấn đại diện.
5. Benchmark peak/burst, concurrency, data growth và recovery.
6. Đánh giá backup/restore, replication, failover, quota, encryption và region.
7. Tính tổng chi phí sở hữu (TCO), gồm license/managed service, storage, I/O, network, backup và nhân lực.
8. Ghi ADR với phương án chọn, phương án bị loại và điều kiện xem xét lại.

### 17.3. Nội dung ADR tham khảo

~~~markdown
# ADR: Chọn relational database làm system of record cho Booking

## Context
- Booking cần kiểm tra invariant và cập nhật trạng thái giao dịch.
- Read pattern gồm lookup theo ID và danh sách theo customer.
- Search và analytics có thể eventual consistent.

## Decision
- Relational database sở hữu booking và transaction nghiệp vụ.
- Event/outbox dùng để cập nhật read projection.
- Cache chỉ lưu dữ liệu có thể tái tạo.

## Alternatives
- Document database làm nguồn chuẩn.
- Key-value store làm nguồn booking.

## Consequences
- Cần thiết kế index/transaction/connection pool.
- Search projection có lag và cần reconciliation.
- Cần đánh giá HA, backup, restore và quota theo region.

## Revisit when
- Workload write/scale vượt capacity được benchmark.
- Access pattern hoặc consistency requirement thay đổi đáng kể.
~~~

## 18. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chọn database theo xu hướng | Không phù hợp access pattern | Benchmark truy vấn và workload thật |
| Dùng một store cho mọi loại dữ liệu | Một số truy vấn kém hiệu quả, schema khó quản lý | Phân loại workload, chỉ polyglot khi có lợi ích rõ |
| Nghĩ document database không cần schema | Dữ liệu drift, consumer khó tương thích | Validation, versioning và migration |
| Dùng key–value cho truy vấn JOIN phức tạp | Logic query chuyển lên ứng dụng, nhiều round-trip | Xem relational hoặc projection phù hợp |
| Dùng graph cho quan hệ đơn giản | Tăng độ phức tạp và chi phí | Chọn graph khi traversal nhiều bước là workload chính |
| Dùng time-series làm system of record giao dịch | Khó bảo vệ invariant và cập nhật entity | Tách metrics khỏi transaction nghiệp vụ |
| Tạo quá nhiều index | Ghi chậm và storage tăng | Index theo access pattern và đo query plan |
| Shard quá sớm | Transaction, join, migration và vận hành phức tạp | Scale dọc/read replica/partition trước khi cần shard |
| Xem replica là backup | Xóa nhầm/corruption lan sang replica | Backup độc lập và restore test |
| Coi cache là nguồn chuẩn | Mất dữ liệu hoặc stale state | Phân định source of truth và cache invalidation |
| Không phân định owner dữ liệu | Nhiều store ghi cùng một trạng thái, conflict | System of record và quyền ghi rõ |
| Không tính chi phí vận hành nhiều store | Nợ vận hành và rủi ro sự cố tăng | Tính TCO và năng lực on-call |

## 19. Bài tập áp dụng

### Bài tập A — Booking và transaction

Một booking cần kiểm tra tồn kho, tạo booking và ghi nhận khoản thanh toán trong một luồng có invariant. Nhóm đề xuất key–value vì lookup theo bookingId nhanh.

**Câu hỏi:** Vì sao lookup nhanh chưa đủ để chọn key–value?

**Gợi ý:** Cần xem transaction, constraint, truy vấn quan hệ, concurrency và nguồn có thẩm quyền. Key–value có thể dùng cho cache/lookup, còn transaction booking/payment có thể cần relational hoặc thiết kế khác hỗ trợ invariant tương đương.

### Bài tập B — Hồ sơ nhiều loại

Listing có loại căn hộ, khách sạn và homestay; mỗi loại có một số thuộc tính riêng nhưng đều được đọc theo listingId.

**Câu hỏi:** Document model mang lại lợi ích gì và rủi ro nào?

**Gợi ý:** Nested field và schema linh hoạt giúp lưu aggregate gần access pattern. Cần validation/versioning, giới hạn kích thước, index, quy tắc embed/reference và migration document cũ.

### Bài tập C — Quan hệ nhiều bước

Hệ thống cần tìm tất cả listing cách một listing tối đa ba bước qua các quan hệ khu vực/đối tác và gợi ý liên quan.

**Câu hỏi:** Khi nào graph database đáng cân nhắc?

**Gợi ý:** Khi traversal nhiều bước là truy vấn cốt lõi, thường xuyên và có benchmark chứng minh lợi ích so với relational/search. Cần giới hạn độ sâu, cardinality, index và chi phí traversal.

### Bài tập D — Metrics có cardinality cao

Hệ thống ghi metric với tag service, region, environment và requestId duy nhất cho mỗi request.

**Câu hỏi:** Vấn đề khi đưa requestId thành tag là gì?

**Gợi ý:** Cardinality tăng rất lớn, làm index, memory và chi phí tăng. Dùng requestId trong trace/log; giữ dimensions có số lượng giá trị được kiểm soát trong metric.

### Bài tập E — Multi-database consistency

Booking relational database commit thành công; Search document projection chưa cập nhật vì CDC lag.

**Câu hỏi:** API tra booking ngay sau ghi nên đọc ở đâu?

**Gợi ý:** Đọc Booking system of record hoặc áp dụng read-your-writes bằng version. Search là projection eventual consistent và không nên được dùng để kết luận booking chưa tồn tại.

### Bài tập F — Chọn database theo TCO

Nhóm có thể dùng relational managed database duy nhất hoặc bổ sung key–value, document và graph store. Ba store bổ sung làm truy vấn một số use case nhanh hơn nhưng tăng on-call, backup, schema và sync.

**Câu hỏi:** Cần bằng chứng nào trước khi chọn polyglot persistence?

**Gợi ý:** Prototype/benchmark, yêu cầu latency/throughput, chi phí toàn vòng đời, khả năng vận hành, lợi ích truy vấn và kế hoạch consistency/rebuild. Không chỉ so giá compute.

## 20. Checklist trước khi phê duyệt kiến trúc database

- [ ] Access pattern và workload read/write/transaction đã được mô tả bằng số liệu.
- [ ] Entity, relationship, key, schema và system of record đã có owner.
- [ ] Mô hình dữ liệu đáp ứng query, constraint, consistency và transaction cần thiết.
- [ ] Index, partition/shard key và pagination được thiết kế theo truy vấn thực tế.
- [ ] Dự báo volume, growth, burst, connection, IOPS, throughput và hot key.
- [ ] Có prototype/load test với dữ liệu và phân bố truy vấn đại diện.
- [ ] HA, replication, backup/restore, RTO/RPO và DR đã được đánh giá.
- [ ] Schema migration, versioning, backfill và rollback có kế hoạch.
- [ ] Multi-database có nguồn chuẩn rõ, outbox/CDC/inbox và reconciliation khi cần.
- [ ] Tenant isolation, IAM, encryption, secret rotation và audit được thiết kế.
- [ ] Region của primary, replica, backup, log, CDC và analytics tuân thủ policy dữ liệu.
- [ ] Retention, TTL, delete propagation, archive và legal hold được xác định.
- [ ] Monitoring có slow query, latency p95/p99, connection, lock, lag, storage và quota.
- [ ] TCO bao gồm database, I/O, storage, egress, backup, license, nhân lực và on-call.
- [ ] Có ADR nêu lựa chọn, phương án thay thế, đánh đổi và điều kiện xem xét lại.

**Điểm cốt lõi:** relational mạnh về dữ liệu có quan hệ và transaction; key–value tối ưu truy cập theo khóa; document phù hợp hồ sơ linh hoạt; graph mạnh ở truy vấn quan hệ nhiều bước; time-series phù hợp dữ liệu đo lường theo thời gian. Chọn đúng database nghĩa là chọn mô hình phù hợp với workload, consistency và trách nhiệm dữ liệu, đồng thời có bằng chứng về khả năng vận hành, phục hồi và chi phí trong môi trường cloud.
