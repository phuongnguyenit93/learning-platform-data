# Đánh đổi giữa join lớn, batch fetch và nhiều truy vấn nhỏ trong Hibernate ORM

## 1. Vì sao một câu SQL lớn chưa chắc nhanh hơn nhiều câu SQL nhỏ?

Một trang quản trị hiển thị 30 đơn hàng. Mỗi đơn có Customer, các OrderItem, Product của từng item và Shipment. Một cách viết truy vấn là JOIN tất cả bảng trong một câu SQL:

~~~sql
SELECT ...
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_items i ON i.order_id = o.id
LEFT JOIN products p ON p.id = i.product_id
LEFT JOIN shipments s ON s.order_id = o.id
WHERE o.organization_id = ?
ORDER BY o.created_at DESC
LIMIT 30;
~~~

Nhìn qua, chỉ có một round trip đến database nên có vẻ tối ưu. Nhưng nếu mỗi Order có 5 Items và 2 Shipments, kết quả JOIN có thể chứa nhiều dòng lặp lại cho cùng một Order, Customer, Item hoặc Shipment. Database phải join, sắp xếp và truyền dữ liệu; JDBC phải đọc các dòng lặp; Hibernate phải nhận diện identity và dựng object graph.

Ở hướng ngược lại, nếu code gọi repository trong vòng lặp:

~~~java
List<PurchaseOrder> orders = orderRepository.findRecent();

for (PurchaseOrder order : orders) {
    order.getCustomer().getName();
    order.getItems().size();
}
~~~

ứng dụng có thể phát sinh N+1 queries: một query lấy danh sách Orders, rồi thêm query cho từng Customer và từng collection Items.

Giữa hai thái cực đó có các chiến lược:

- JOIN FETCH hoặc EntityGraph để lấy dữ liệu cần thiết trong một số query.
- Batch fetching để gom nhiều lazy loads thành các query theo lô.
- SUBSELECT fetching để tải một nhóm collection bằng một truy vấn phụ.
- Nhiều truy vấn nhỏ có chủ đích, mỗi truy vấn trả đúng loại dữ liệu cần cho DTO.

Không có chiến lược luôn nhanh nhất. Cần cân nhắc **round trips, số dòng SQL trả về, kích thước dữ liệu truyền, chi phí join/sort, hydration của Hibernate, bộ nhớ, pagination, cardinality và workload thực tế**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện N+1 và phân biệt nó với nhiều truy vấn có chủ đích.
2. Hiểu khi nào JOIN FETCH tốt cho to-one và khi nào join to-many gây row multiplication.
3. Tính sơ bộ số dòng JOIN và dữ liệu lặp trong kết quả.
4. Sử dụng `@BatchSize` và `hibernate.default_batch_fetch_size` cho lazy entities/collections.
5. Hiểu `FetchMode.SUBSELECT`, ưu điểm và phạm vi tác động.
6. Chọn fetch plan theo use case bằng JPQL/HQL, EntityGraph hoặc DTO projection.
7. Tránh pagination sai khi fetch collection.
8. Phân biệt batch fetching đọc dữ liệu với JDBC batching ghi dữ liệu.
9. Đo query count, rows, bytes, latency, heap và execution plan thay vì chỉ đếm câu SQL.
10. Thiết kế integration test và benchmark phản ánh kích thước dữ liệu thực.

Ví dụ sử dụng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA và PostgreSQL. Tên property/API cụ thể cần căn đúng Hibernate version của dự án; các con số trong bài là minh họa để giải thích trade-off, không phải benchmark phổ quát.

## 2. Ba chiến lược và câu hỏi cần trả lời

| Chiến lược | Cách hoạt động | Điểm mạnh | Chi phí/rủi ro |
|---|---|---|---|
| Join lớn | Một query join nhiều bảng/association | Ít round trips; tốt cho dữ liệu to-one và graph nhỏ | Row multiplication, dữ liệu lặp, sort/join nặng, pagination to-many khó |
| Batch fetch | Khi cần lazy data, Hibernate gom nhiều proxy/collection vào một query theo lô | Giảm N+1 mà vẫn giữ lazy loading | Vẫn có nhiều query; phụ thuộc batch size, số owners và access pattern |
| Nhiều query nhỏ có chủ đích | Query root, query child theo tập IDs hoặc projection riêng | Kết quả gọn, dễ phân trang/đo; kiểm soát dữ liệu chính xác | Nhiều round trips hơn; cần ghép kết quả hoặc quản lý thứ tự |

### 2.1. Đừng chỉ hỏi “bao nhiêu query?”

Một query trả 100.000 rows có thể tốn hơn 10 query mỗi query trả 20 rows. Ngược lại, 100 query tuần tự qua mạng có thể chậm hơn một query JOIN được index tốt.

Đánh giá tối thiểu:

- Số lần round trip ứng dụng ↔ database.
- Số rows database thực sự trả về.
- Số cột và bytes truyền qua JDBC.
- Thời gian execution ở database.
- Thời gian đọc result set và hydrate entities.
- Số object/collection được giữ trong persistence context.
- Thời gian chờ connection, lock và network.
- Số request đồng thời và mức độ tải khi traffic tăng.

### 2.2. Chiến lược có thể phối hợp

Một use case tốt có thể:

1. JOIN FETCH Customer (to-one) cùng trang Orders.
2. Tải OrderItems bằng batch fetching.
3. Lấy Product labels bằng một DTO query theo tập product IDs.
4. Tải Shipment summary bằng query riêng có phân trang/aggregate.

Đây không phải “làm phức tạp để tối ưu”; mỗi association có cardinality và mục tiêu dữ liệu khác nhau.

## 3. N+1 queries là gì?

N+1 xảy ra khi:

1. Một query lấy N entity gốc.
2. Khi code truy cập association của mỗi entity, Hibernate phát thêm một query riêng.

Ví dụ:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select o
    from PurchaseOrder o
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .setMaxResults(50)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu Customer là LAZY và chưa có trong persistence context/cache, có thể thấy:

~~~text
1. SELECT 50 purchase_orders
2. SELECT customer WHERE id = ?
3. SELECT customer WHERE id = ?
...
51. SELECT customer WHERE id = ?
~~~

Nếu mỗi Order có một Customer khác nhau, tổng có thể gần 1 + 50. Nếu nhiều Orders cùng tham chiếu một Customer, first-level cache có thể giảm số lần load, nên không nhất thiết đúng bằng N+1 trong mọi dữ liệu.

### 3.1. N+1 với collection thường dễ gây đau hơn

~~~java
for (PurchaseOrder order : orders) {
    int itemCount = order.getItems().size();
}
~~~

Với collection LAZY, Hibernate có thể chạy:

~~~text
1 query lấy 50 Orders
50 query lấy items của từng Order
~~~

Nếu mỗi collection chứa nhiều rows, tổng số rows/bytes còn lớn hơn. Đây là một nguyên nhân phổ biến khiến endpoint chậm khi dữ liệu thật tăng lên.

### 3.2. N+1 không luôn lộ trong test nhỏ

Với 2 Orders và 2 Customers, 3 query có thể không đáng kể. Khi production có 500 Orders mỗi trang hoặc association được truy cập sâu qua serializer, số query tăng nhanh.

### 3.3. N+1 có thể phát sinh ở serializer

Service trả entity:

~~~java
return orderRepository.findRecent();
~~~

JSON serializer đọc:

~~~text
order.customer.name
order.items[*].product.name
~~~

Nếu persistence context còn mở (ví dụ OSIV), serializer có thể kích hoạt lazy loading sau khi service đã kết thúc. SQL phát sinh ngoài nơi code truy vấn được viết, khiến profiling khó hiểu và query count tăng.

**Map sang DTO trong service transaction** giúp fetch plan và thời điểm truy cập dữ liệu hiển thị rõ.

### 3.4. Nhiều query không tự động là N+1

Một quy trình:

1. Query 50 Orders.
2. Query tất cả Items của 50 Order IDs bằng một IN list.
3. Query tất cả Product summaries của tập Product IDs.

là ba query có chủ đích, số query không tăng tuyến tính theo số Orders. Đây có thể là thiết kế tốt hơn một JOIN lớn.

## 4. JOIN FETCH: giảm round trips bằng cách lấy association cùng query

Với quan hệ to-one:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

JPQL/HQL:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.organizationId = :organizationId
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .setParameter("organizationId", organizationId)
    .getResultList();
~~~

Hibernate có thể tạo một SQL JOIN lấy Order và Customer trong cùng result set. Khi code gọi `getCustomer()`, association đã được fetch.

### 4.1. To-one thường là ứng viên tốt cho JOIN FETCH

Với mỗi Order chỉ có một Customer, join không nhân số dòng root theo số Customers con. Một Order có thể join tới tối đa một Customer qua FK đơn/unique phù hợp. Nếu Customer đã được load bởi nhiều Orders, dữ liệu Customer vẫn có thể lặp trong từng row nhưng số rows không tăng theo số lượng child collection.

To-one không có nghĩa miễn phí: bảng Customer rộng, join nhiều to-one hoặc dữ liệu lặp lớn vẫn có chi phí. Tuy nhiên đây thường là điểm bắt đầu hợp lý.

### 4.2. INNER JOIN hay LEFT JOIN?

`join fetch o.customer` là inner join; nó loại Order không có Customer (hoặc association không khớp) khỏi kết quả.

`left join fetch o.customer` giữ Order kể cả khi không có Customer tương ứng:

~~~hql
select o
from PurchaseOrder o
left join fetch o.customer
where o.organizationId = :organizationId
~~~

Chọn theo nullability/domain semantics. Đừng đổi inner thành left chỉ để “an toàn” nếu association bắt buộc phải có; điều đó có thể che dữ liệu lỗi.

### 4.3. JOIN FETCH không phải projection

JOIN FETCH vẫn hydrate entity graph và đặt association vào persistence context. Nếu API chỉ cần `orderNumber`, `customerName`, `totalAmount`, DTO projection có thể truyền ít cột hơn và tránh quản lý entity không cần thiết.

## 5. Row multiplication khi JOIN to-many

Giả sử một trang có 20 Orders. Mỗi Order có trung bình 8 Items. JOIN FETCH Items tạo khoảng:

[
20 \times 8 = 160
\]

rows trong result set (giả định mỗi Order có 8 Items và không có join khác làm nhân thêm).

Mỗi row lặp lại các cột của Order; Hibernate phải nhận diện cùng root ID để dựng một entity Order và collection Items.

### 5.1. Một collection to-many

~~~hql
select o
from PurchaseOrder o
left join fetch o.items
where o.organizationId = :organizationId
~~~

Đây có thể là lựa chọn hợp lý nếu:

- Số root nhỏ.
- Số child mỗi root bị giới hạn.
- Không cần pagination root phức tạp.
- Kết quả thực tế không quá rộng.

### 5.2. Hai collection to-many nhân với nhau

Giả sử mỗi Order có:

- 8 Items.
- 3 Shipments.

JOIN cả hai collection có thể tạo:

[
8 \times 3 = 24
\]

rows cho một Order, vì mỗi Item kết hợp với mỗi Shipment trong result set. Với 20 Orders:

[
20 \times 8 \times 3 = 480
\]

rows, dù object graph chỉ có 20 Orders, 160 Items và 60 Shipments.

Nếu mỗi Order có 20 Items và 10 Payments, result set có thể lên tới 200 rows cho mỗi Order. Đây là **cartesian multiplication theo cardinality**, không phải dữ liệu bị nhân bản trong database.

### 5.3. Hình minh họa

~~~mermaid
flowchart TD
    O[Order 101] --> I1[Item A]
    O --> I2[Item B]
    O --> S1[Shipment X]
    O --> S2[Shipment Y]
    I1 -. join result .-> R1[Item A + Shipment X]
    I1 -. join result .-> R2[Item A + Shipment Y]
    I2 -. join result .-> R3[Item B + Shipment X]
    I2 -. join result .-> R4[Item B + Shipment Y]
~~~

Hai Items và hai Shipments tạo bốn tổ hợp row. Hibernate có thể khử trùng entity theo identity khi dựng graph, nhưng database/JDBC vẫn phải xử lý và truyền các rows đó.

### 5.4. DISTINCT có thể khử duplicate root, không xóa chi phí row ở database

~~~hql
select distinct o
from PurchaseOrder o
left join fetch o.items
~~~

`distinct` có thể giúp semantics kết quả root không lặp; Hibernate 6 cũng có cơ chế xử lý duplicate root entities từ fetch joins. Nhưng nó không biến result set 160 rows thành 20 rows nếu vẫn cần hydrate 160 Items. SQL DISTINCT còn có thể buộc database sort/hash để khử duplicates, tăng chi phí.

Không thêm DISTINCT một cách máy móc và cho rằng row multiplication đã được giải quyết.

## 6. MultipleBagFetchException và nhiều collection

Trong Hibernate, một bag thường là collection không có index/unique semantics rõ, ví dụ `List` không có `@OrderColumn` hoặc một mapping bag phù hợp. Fetch join đồng thời nhiều bag collection có thể gây:

~~~text
MultipleBagFetchException:
cannot simultaneously fetch multiple bags
~~~

Lý do là Hibernate khó phân biệt các tổ hợp row lặp để dựng chính xác nhiều bags, ngoài chi phí cartesian multiplication.

### 6.1. Đổi List thành Set không phải giải pháp hiệu năng tổng quát

Một số hướng dẫn đề xuất đổi `List` thành `Set` để tránh exception. Nhưng:

- Set yêu cầu equals/hashCode đúng và ổn định.
- Nó không xóa cartesian row multiplication.
- Thứ tự không được bảo đảm như List.
- Duplicate semantics có thể là một phần của domain.

Đổi collection type chỉ để query chạy được có thể thay đổi semantics domain và tạo bug khác.

### 6.2. @OrderColumn cũng không làm join rẻ hơn

List có index được mapping bằng @OrderColumn có semantics khác bag. Hibernate có thể xử lý fetch khác, nhưng hai to-many joins vẫn nhân rows theo cardinality. Không dùng @OrderColumn như mẹo để ép một query khổng lồ.

### 6.3. Thường tách các collection ra nhiều query

Ví dụ:

1. Query Orders cùng Customer (to-one).
2. Query Items của tập Order IDs.
3. Query Shipments của tập Order IDs.

Tổng ba round trips, nhưng không tạo 8 × 3 rows cho mỗi Order. Khi root page có kích thước cố định, đây thường là một trade-off tốt.

## 7. Pagination và collection fetch join

Một truy vấn có vẻ hợp lý:

~~~java
Page<PurchaseOrder> page =
    repository.findOrdersWithItems(
        organizationId, PageRequest.of(0, 20));
~~~

với:

~~~hql
select o
from PurchaseOrder o
left join fetch o.items
where o.organizationId = :organizationId
~~~

Khi kết hợp pagination với collection fetch, database phân trang **rows sau JOIN**, trong khi ứng dụng muốn phân trang **root Orders**. Một Order có 10 Items chiếm 10 rows; LIMIT 20 có thể cắt giữa các Order hoặc không thể đại diện đúng 20 root.

Hibernate có thể cảnh báo và thực hiện pagination in memory trong một số trường hợp, làm ứng dụng tải quá nhiều rows trước khi cắt kết quả. Cấu hình:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

có thể được dùng để fail fast thay vì âm thầm chấp nhận pagination collection fetch nguy hiểm, tùy Hibernate version.

### 7.1. Cách hai bước: page IDs rồi fetch graph

Bước 1: lấy IDs theo đúng điều kiện và thứ tự:

~~~java
List<Long> ids = entityManager.createQuery("""
    select o.id
    from PurchaseOrder o
    where o.organizationId = :organizationId
      and o.deletedAt is null
    order by o.createdAt desc, o.id desc
    """, Long.class)
    .setParameter("organizationId", organizationId)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Bước 2: fetch to-one hoặc graph nhỏ:

~~~java
List<PurchaseOrder> loaded = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    where o.id in :ids
      and o.organizationId = :organizationId
    """, PurchaseOrder.class)
    .setParameter("ids", ids)
    .setParameter("organizationId", organizationId)
    .getResultList();
~~~

SQL `IN` không bảo đảm thứ tự giống danh sách IDs. Nếu cần thứ tự trang gốc, dựng map theo ID rồi sắp xếp theo `ids`:

~~~java
Map<Long, PurchaseOrder> byId = loaded.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
~~~

### 7.2. Bước ba: lấy Items theo batch IDs

~~~hql
select i
from OrderItem i
join fetch i.product
where i.order.id in :orderIds
order by i.order.id, i.lineNumber
~~~

Kết quả được Hibernate gắn vào collection nếu entity/collection state và query mapping phù hợp; hoặc có thể map thẳng DTO theo orderId. Cần kiểm thử không tạo duplicate collection state hoặc làm mất thứ tự.

### 7.3. Count query độc lập

Spring Data Page thường cần count query. Với fetch join collection, count query phải được viết riêng, không fetch association:

~~~hql
select count(o)
from PurchaseOrder o
where o.organizationId = :organizationId
  and o.deletedAt is null
~~~

Không count trên join to-many mà quên DISTINCT, vì một Order có nhiều Items sẽ làm count tăng.

### 7.4. Keyset pagination cho tập dữ liệu lớn

OFFSET lớn có thể tốn chi phí vì database phải bỏ qua nhiều rows. Với sort ổn định `created_at DESC, id DESC`, keyset:

~~~sql
SELECT id, created_at
FROM purchase_orders
WHERE organization_id = :orgId
  AND deleted_at IS NULL
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Index cần phù hợp với điều kiện organization và sort. Keyset không tự xử lý mọi thay đổi dữ liệu giữa các trang; cần xác định snapshot/consistency semantics.

## 8. Batch fetching: giảm N+1 mà vẫn giữ LAZY

Batch fetching là một chiến lược khác với JOIN FETCH. Hibernate giữ association lazy, nhưng khi một proxy hoặc collection được khởi tạo, nó có thể tải **một nhóm các proxies/collections cùng loại** trong một query.

Ví dụ 50 Orders có 50 Customer proxies chưa khởi tạo. Khi code truy cập Customer đầu tiên, Hibernate có thể phát:

~~~sql
SELECT *
FROM customers
WHERE id IN (?, ?, ..., ?);
~~~

thay vì 50 SELECT riêng.

### 8.1. @BatchSize trên entity

~~~java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    @Id
    private Long id;

    private String name;
}
~~~

Khi nhiều Customer proxies thuộc cùng persistence context đang chưa được initialize, Hibernate có thể gom tối đa một batch theo cấu hình để load.

### 8.2. @BatchSize trên collection

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderItem> items;
~~~

Khi một collection được initialize, Hibernate có thể tải items cho một nhóm Order owners có collection cùng role đang chờ load, thay vì một query cho từng Order.

### 8.3. Cấu hình toàn cục

~~~properties
hibernate.default_batch_fetch_size=32
~~~

Trong Spring Boot:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 32
~~~

Đây là giá trị minh họa. Batch size phải được đo theo số IDs, giới hạn bind parameters của database/driver, độ rộng row và workload. Đừng đặt 1000 chỉ vì muốn “ít query nhất”.

### 8.4. Batch fetching không phải eager loading toàn bộ

Hibernate chỉ tải các proxies/collections cần thiết theo behavior batch fetch. Nếu code chỉ truy cập 2 trong 50 collections, batch query có thể tải thêm một số collections cùng batch; nó không nhất thiết tải toàn bộ association của mọi entity trong context ngay khi query root chạy.

### 8.5. Batch fetch size là số lượng tối đa theo batch, không phải số query cố định

Nếu có 100 proxies và batch size 32, số query load có thể xấp xỉ 4, nhưng còn phụ thuộc:

- Bao nhiêu proxies thực sự cần initialize.
- Các entity đã có trong L1/L2 hay chưa.
- Truy cập theo thứ tự nào.
- Các association có cùng entity type/collection role không.
- Database parameter limits và provider strategy.

Không viết test đòi chính xác luôn 4 query nếu cache và fixture không được kiểm soát.

## 9. Batch fetch cho to-one proxies

Mapping:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Có thể đặt `@BatchSize` trên Customer hoặc dùng global default:

~~~java
@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
~~~

Khi truy cập Customer của một Order, Hibernate có thể load một nhóm Customer IDs đang chờ. Điều này giảm N+1 nhưng vẫn cho phép application chỉ truy cập association khi cần.

### 9.1. Điều kiện để batch có ích

- Có nhiều proxy cùng entity type trong cùng persistence context.
- Code truy cập một số proxy khiến Hibernate có cơ hội gom nhóm.
- Batch size đủ lớn so với số proxy được dùng.
- Những proxies không bị load trước bởi JOIN FETCH hoặc cache.

Nếu mỗi request chỉ dùng một Order và một Customer, batch size 32 không đem lại lợi ích rõ rệt.

### 9.2. Nhiều Orders cùng một Customer

Nếu 50 Orders cùng trỏ một Customer ID, first-level cache thường chỉ cần một Customer managed instance/query load (nếu chưa có trong cache). Batch fetch không thể giảm dưới một query cần thiết trong tình huống này; lợi ích lớn hơn khi có nhiều IDs khác nhau.

### 9.3. Lazy to-one cần proxy-compatible mapping

Hibernate có thể dùng proxy/subclass hoặc bytecode enhancement để hỗ trợ lazy loading. Final classes/final methods, mapping không tương thích hoặc bytecode enhancement configuration có thể ảnh hưởng khả năng lazy. Không giả định mọi `FetchType.LAZY` trên to-one luôn được thực hiện đúng như mong muốn nếu chưa kiểm tra provider và enhancement.

## 10. Batch fetch cho collection

Với 50 Orders, mỗi Order có collection Items:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 16)
private List<OrderItem> items;
~~~

Khi code truy cập:

~~~java
for (PurchaseOrder order : orders) {
    process(order.getItems().size());
}
~~~

Hibernate có thể tải Items cho một nhóm Order IDs bằng SQL dạng:

~~~sql
SELECT *
FROM order_items
WHERE order_id IN (?, ?, ..., ?);
~~~

Nếu 50 Orders và batch size 16, thường cần khoảng 4 collection-loading queries thay vì 50, nếu tất cả collections cần initialize và không có cache hit/điều kiện khác.

### 10.1. Batch fetch không tự giảm số child rows

Nếu 50 Orders có tổng 400 Items, batch fetch vẫn tải khoảng 400 Item rows cần thiết. Nó giảm round trips, không loại bỏ dữ liệu child.

### 10.2. Không truy cập collection nếu không cần

Nếu API chỉ cần itemCount, tải toàn bộ Items rồi gọi size() có thể rất tốn. Một DTO query:

~~~hql
select o.id, count(i.id)
from PurchaseOrder o
left join o.items i
where o.organizationId = :orgId
group by o.id
~~~

có thể chỉ trả một count cho mỗi Order. Đây thường là lựa chọn tốt hơn batch fetch 400 child rows khi chỉ cần số lượng.

### 10.3. Collection filter/soft delete

Nếu collection có filter hoặc restriction, SQL batch load cần áp dụng điều kiện mapping tương ứng theo Hibernate version và association path. Test batch fetch với soft-delete/tenant filter đang dùng; không suy ra query IN tự động giữ mọi visibility policy nếu cấu hình/load path khác.

## 11. FetchMode.SUBSELECT cho collection

Hibernate cung cấp:

~~~java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderItem> items;
~~~

Ý tưởng: sau khi một nhóm Order đã được load trong cùng persistence context bằng một query phù hợp, khi một collection Items được initialize, Hibernate có thể tải collection cùng role của các owners trong nhóm bằng một truy vấn phụ dùng subselect.

SQL minh họa:

~~~sql
SELECT i.*
FROM order_items i
WHERE i.order_id IN (
    SELECT o.id
    FROM purchase_orders o
    WHERE o.organization_id = ?
      AND o.status = ?
);
~~~

SQL thực tế phụ thuộc query root, dialect và Hibernate version.

### 11.1. Khi SUBSELECT phù hợp

- Một truy vấn root tải một nhóm Orders tương đối gọn.
- Phần lớn Orders trong nhóm sẽ cần collection cùng role.
- Muốn tránh một query cho mỗi collection.
- Không muốn JOIN nhân rows trong root query.

### 11.2. Chi phí và giới hạn

- Có thể tải collection của nhiều owners hơn số collection code thực sự cần.
- Query phụ có thể lặp lại subquery root phức tạp.
- Tập owners được ảnh hưởng phụ thuộc cách root entities được load/persistence context.
- Một truy vấn root quá rộng có thể làm subselect rất nặng.
- Không giải quyết pagination/fetch graph theo mọi trường hợp.

### 11.3. SUBSELECT khác batch IN

| Đặc điểm | Batch fetch | SUBSELECT |
|---|---|---|
| Cách chọn owners | Một nhóm IDs/proxies đang chờ | Nhóm owners gắn với query/load context theo semantics Hibernate |
| SQL điển hình | `WHERE owner_id IN (?, ?, ...)` | `WHERE owner_id IN (subquery)` |
| Kiểm soát kích thước | Batch size | Phụ thuộc root result/subselect |
| Phù hợp | Nhiều proxies, nhóm vừa, access một phần | Một query root và phần lớn collection được dùng |
| Rủi ro | Nhiều batch queries nếu tập lớn | Subquery/root scope quá rộng |

### 11.4. Không dùng SUBSELECT cho mọi collection

Một trang có 20 Orders nhưng user chỉ mở một Order; SUBSELECT có thể tải Items cho nhiều Orders hơn cần thiết. Batch size nhỏ hoặc query DTO cho Order đang mở có thể tiết kiệm hơn.

## 12. Nhiều query nhỏ có chủ đích

Một chiến lược thường rất hiệu quả cho read API:

1. Query page of Orders + Customer to-one.
2. Query Item DTOs cho toàn bộ Order IDs của trang.
3. Query Shipment summaries cho cùng IDs.
4. Ghép theo orderId trong memory.

### 12.1. Query root

~~~java
List<OrderHeaderRow> headers = entityManager.createQuery("""
    select new com.example.app.dto.OrderHeaderRow(
        o.id,
        o.orderNumber,
        o.createdAt,
        c.name
    )
    from PurchaseOrder o
    join o.customer c
    where o.organizationId = :organizationId
    order by o.createdAt desc, o.id desc
    """, OrderHeaderRow.class)
    .setParameter("organizationId", organizationId)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

### 12.2. Query Items cho tập IDs

~~~java
List<OrderItemRow> itemRows = entityManager.createQuery("""
    select new com.example.app.dto.OrderItemRow(
        i.order.id,
        i.id,
        i.sku,
        i.quantity
    )
    from OrderItem i
    where i.organizationId = :organizationId
      and i.order.id in :orderIds
    order by i.order.id, i.id
    """, OrderItemRow.class)
    .setParameter("organizationId", organizationId)
    .setParameter("orderIds", orderIds)
    .getResultList();
~~~

Nếu orderIds rỗng, bỏ qua query Items và trả danh sách rỗng; không gửi `IN ()` hoặc thay bằng query không có điều kiện. Điều kiện tenant được truyền rõ cho query child.

### 12.3. Ghép DTO

~~~java
Map<Long, List<OrderItemRow>> itemsByOrder =
    itemRows.stream().collect(Collectors.groupingBy(
        OrderItemRow::orderId
    ));

List<OrderDetailRow> result = headers.stream()
    .map(h -> new OrderDetailRow(
        h.id(),
        h.orderNumber(),
        h.createdAt(),
        h.customerName(),
        itemsByOrder.getOrDefault(h.id(), List.of())
    ))
    .toList();
~~~

Ví dụ DTO records:

~~~java
public record OrderHeaderRow(
    Long id, String orderNumber,
    Instant createdAt, String customerName
) {}

public record OrderItemRow(
    Long orderId, Long itemId,
    String sku, int quantity
) {}

public record OrderDetailRow(
    Long id, String orderNumber,
    Instant createdAt, String customerName,
    List<OrderItemRow> items
) {}
~~~

### 12.4. Vì sao đây có thể nhanh hơn một JOIN lớn?

- Root page được phân trang chính xác.
- Customer to-one được join một lần.
- Item query chỉ trả các cột DTO cần thiết.
- Không lặp lại các cột Order cho từng Item.
- Không nhân Items × Shipments nếu mỗi loại child có query riêng.
- Dữ liệu ghép trong memory theo ID, không cần Hibernate quản lý toàn graph.

Chi phí là thêm round trip và code mapping. Với 3 query cố định cho trang 20 Orders, đây có thể là lựa chọn tốt hơn 1 query tạo hàng nghìn rows.

### 12.5. Giới hạn IN list

Nếu một batch có hàng chục nghìn IDs, IN list có thể vượt giới hạn bind parameters/SQL size hoặc tạo plan kém. Chia thành các chunks, dùng array/table-valued parameter theo DB hoặc join với temporary/staging table phù hợp. Đối với một trang 20–100 IDs, IN list thường đơn giản.

## 13. DTO projection so với entity fetch

Entity fetch:

~~~hql
select o
from PurchaseOrder o
left join fetch o.customer
~~~

DTO projection:

~~~hql
select new com.example.OrderRow(
    o.id, o.orderNumber, c.name, o.totalAmount
)
from PurchaseOrder o
join o.customer c
where o.organizationId = :orgId
~~~

### 13.1. Entity fetch phù hợp khi

- Cần thay đổi aggregate trong transaction.
- Cần dirty checking/cascade.
- Cần domain methods và invariants.
- Graph nhỏ và fetch plan đã được kiểm soát.
- Cần dùng entity identity/persistence context.

### 13.2. DTO projection phù hợp khi

- Read-only API/reporting.
- Chỉ cần một tập cột cụ thể.
- Cần phân trang root ổn định.
- Không cần dirty checking hoặc cascade.
- Muốn tránh lazy loads ngoài service.
- Muốn trả kết quả không phụ thuộc lifecycle EntityManager.

### 13.3. Projection không tự đảm bảo query nhanh

DTO query vẫn có thể JOIN quá nhiều bảng, aggregate nặng hoặc thiếu index. Nó chỉ giúp kiểm soát cột/object graph và thường tránh hydrate entity không cần thiết. Cần xem execution plan và số rows.

### 13.4. Spring Data interface projection

~~~java
public interface OrderHeaderView {
    Long getId();
    String getOrderNumber();
    BigDecimal getTotalAmount();
}
~~~

~~~java
Page<OrderHeaderView> findByOrganizationId(
    Long organizationId, Pageable pageable);
~~~

Projection behavior phụ thuộc cách Spring Data tạo query/projection. Với query phức tạp, explicit constructor projection/JPQL hoặc native DTO mapping có thể dễ dự đoán hơn.

## 14. EntityGraph: khai báo fetch plan theo use case

JPA EntityGraph có thể yêu cầu load các association cần thiết mà không phải viết join fetch trực tiếp trong query:

~~~java
@EntityGraph(attributePaths = {"customer"})
Page<PurchaseOrder> findByOrganizationId(
    Long organizationId, Pageable pageable);
~~~

### 14.1. EntityGraph không phải lời hứa về một SQL duy nhất

Provider quyết định cách thực hiện fetch plan; có thể dùng JOIN hoặc secondary selects theo mapping/provider. Không suy ra EntityGraph luôn tương đương một câu JOIN FETCH hoặc luôn tránh N+1.

### 14.2. To-many graph vẫn có pagination/cardinality risk

~~~java
@EntityGraph(attributePaths = {"items"})
Page<PurchaseOrder> findByOrganizationId(...);
~~~

Nếu graph fetch collection, các vấn đề row multiplication và pagination collection fetch vẫn cần xem xét. EntityGraph không tự giải quyết chúng.

### 14.3. Graph nhỏ theo màn hình

Một Order detail page có thể cần customer, items và payment summary. Nhưng Order list page chỉ cần customer name và total amount. Tạo hai fetch plans/use cases khác nhau thường tốt hơn một entity graph mặc định tải mọi association.

## 15. So sánh bằng một ví dụ số

Giả sử trang có 30 Orders, mỗi Order có 6 Items và 2 Shipments. Mỗi Item thuộc một Product khác nhau.

### 15.1. Một query JOIN tất cả

Rows ước tính:

[
30 \times 6 \times 2 = 360
\]

Trong 360 rows:

- Các cột Order lặp khoảng 12 lần/Order.
- Customer có thể lặp nhiều lần.
- Mỗi Item lặp theo số Shipments.
- Mỗi Shipment lặp theo số Items.

Nếu Product cũng được join, nó thường lặp theo từng Item × Shipment row.

### 15.2. Join root + Customer, rồi 2 query child

| Query | Rows ước tính |
|---|---:|
| Orders + Customer | 30 |
| Items + Product cho trang | 180 |
| Shipments | 60 |
| Tổng | 270 |

Có 3 round trips, tổng rows thấp hơn và ít dữ liệu Order/Customer lặp lại. Tùy kích thước cột, bytes truyền có thể giảm đáng kể.

### 15.3. Batch fetch

Giả sử batch size 16:

| Query | Số query ước tính |
|---|---:|
| Root Orders | 1 |
| Customers (nếu 30 distinct proxies) | 2 |
| Items collections (30 owners) | 2 |
| Shipments collections (30 owners) | 2 |
| Tổng | 7 |

Batch fetch có thể tạo nhiều query hơn phương án 3-query DTO, nhưng giữ entity graph và lazy semantics. Nếu chỉ 5 Orders cần items, nó có thể không tải hết child collections tùy access/queue state.

### 15.4. Nhiều query nhỏ theo từng entity

Nếu code chạy:

~~~java
for (PurchaseOrder o : orders) {
    loadItems(o.getId());
    loadShipments(o.getId());
}
~~~

thì số query là 1 + 30 + 30 = 61, trước cả Product/Customer. Đây là N+1 theo hai associations.

### 15.5. Không kết luận chỉ bằng rows

Query 360 rows có thể vẫn nhanh hơn 7 queries nếu:

- Database và app cùng vùng mạng, round trip rất thấp.
- Rows nhỏ và indexes tốt.
- DB tối ưu join tốt.
- Hibernate hydration graph không quá nặng.

Ngược lại 360 rows rất rộng có thể chậm hơn nhiều. Cần đo bytes, DB time, app time và tải đồng thời.

## 16. Kích thước row và dữ liệu lặp

Giả sử mỗi Order có 20 cột với tổng 500 bytes, mỗi Item 8 cột/150 bytes và mỗi Shipment 6 cột/120 bytes.

Một Order có 10 Items và 4 Shipments, JOIN cả hai collection tạo 40 rows. Phần cột Order lặp:

[
40 \times 500 = 20{,}000\text{ bytes}
\]

trong khi object Order chỉ cần khoảng 500 bytes dữ liệu scalar cho lần hydrate.

Đây là phép tính ước lượng, chưa gồm protocol overhead, NULL bitmap, type encodings và network framing. Nó minh họa vì sao **một SQL statement có thể truyền nhiều bytes thừa**.

### 16.1. Chỉ select các cột cần thiết

Nếu API chỉ cần orderNumber và customerName, một DTO projection không cần lấy 20 cột Order, toàn bộ Item state hoặc lazy fields khác.

### 16.2. Cột lớn làm JOIN lặp càng tốn

Nếu entity chứa JSON/text/blob lớn, join to-many có thể lặp payload ở nhiều rows tùy query/result. Tránh fetch những cột lớn khi use case không cần; cân nhắc tách attachment/content hoặc dùng projection.

### 16.3. Database có thể phải sort/hash trên rowset lớn

JOIN nhiều collection rồi DISTINCT/ORDER BY có thể tạo sort/hash memory và temporary disk spill. Kiểm tra EXPLAIN ANALYZE, buffers, sort method và actual rows, không chỉ xem SQL có LIMIT.

## 17. Database execution plan và index

Một fetch strategy tốt ở ORM vẫn có thể chậm vì database plan kém.

Query:

~~~sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE organization_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Một index ứng viên:

~~~sql
CREATE INDEX idx_orders_org_status_created
ON purchase_orders(
    organization_id,
    status,
    created_at DESC,
    id DESC
);
~~~

### 17.1. Index cho child batch fetch

~~~sql
CREATE INDEX idx_items_order
ON order_items(order_id);

CREATE INDEX idx_shipments_order
ON shipments(order_id);
~~~

Batch query dùng `WHERE order_id IN (...)` cần index hỗ trợ ở child FK. PostgreSQL không tự tạo index trên referencing FK columns chỉ vì có FOREIGN KEY.

### 17.2. Composite index theo thứ tự predicate/sort

Nếu query lọc organization rồi sort created_at, index (organization_id,created_at) có thể hữu ích. Nếu lọc thêm status equality, (organization_id,status,created_at) có thể phù hợp hơn. Index không phải checklist “có WHERE nào thì tạo index cột đó”; cardinality, selectivity, sort và workload ghi đều quan trọng.

### 17.3. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.organization_id = 7;
~~~

Quan sát:

- Estimated rows so với actual rows.
- Join type (Nested Loop, Hash Join, Merge Join).
- Scan type (Index Scan, Bitmap Heap Scan, Seq Scan).
- Rows removed by filter.
- Sort/hash memory và spill.
- Shared hit/read blocks.
- Execution time và planning time.

Không chạy `EXPLAIN ANALYZE` cho câu DML có side effects trên production nếu chưa kiểm soát; nó thực thi statement.

## 18. Round trips và latency mạng

Nếu mỗi round trip ứng dụng ↔ DB mất trung bình 2 ms:

- 1 query: khoảng 2 ms network overhead.
- 50 query tuần tự: khoảng 100 ms overhead.
- 5 query: khoảng 10 ms overhead.

Đây chỉ là phép tính minh họa; thời gian thực còn execution, queue, pool, TLS, packet size và concurrency.

### 18.1. Nhiều query song song có thể giảm wall-clock nhưng tăng tải

Một số ứng dụng chạy các query độc lập song song qua nhiều connections. Điều đó có thể giảm latency của một request nhưng:

- Tăng số connections và DB concurrency.
- Tăng áp lực CPU/I/O.
- Làm phức tạp transaction consistency.
- Có thể gây pool starvation khi traffic tăng.

Không giải quyết N+1 bằng cách bắn 100 query song song trong một request.

### 18.2. Batch fetch là giảm round trips tuần tự

Batch fetch thường giữ một persistence context và gom proxy/collection IDs vào IN query. Nó không nhất thiết chạy query song song; mục tiêu là giảm số lần phải chờ DB.

### 18.3. Database cùng vùng mạng

Trong môi trường app và DB cùng datacenter, round trip có thể rất thấp; join lớn có thể tốt. Với DB managed qua vùng mạng xa, mỗi round trip đắt hơn và batch/join có lợi rõ. Hãy đo latency thực từ application runtime.

## 19. Hibernate persistence context và chi phí hydration

Khi query entity, Hibernate không chỉ nhận bytes:

1. Đọc từng row.
2. Xác định entity type/identifier.
3. Kiểm tra first-level cache/identity map.
4. Tạo hoặc tái sử dụng managed instance.
5. Hydrate scalar fields và association keys.
6. Quản lý collection snapshots/proxies.
7. Theo dõi dirty checking và lifecycle state.

Một query join lớn có thể làm Hibernate xử lý hàng trăm/hàng nghìn rows để dựng một object graph nhỏ hơn nhiều.

### 19.1. Persistence context phình to

Một transaction đọc 50.000 Orders và fetch Items có thể giữ hàng trăm nghìn entities/collection entries trong L1. Heap tăng, garbage collection và dirty checking/flush snapshots tốn thời gian.

### 19.2. Read-only use case không nhất thiết cần entity

DTO projection tránh đưa mọi row vào persistence context. Với reporting/list pages, đây có thể là lợi ích lớn hơn số round trips.

### 19.3. readOnly transaction

`@Transactional(readOnly = true)` có thể giúp Spring/provider áp dụng tối ưu read-only/flush mode tùy cấu hình. Nó không tự giảm số rows hoặc làm query join tốt hơn. Fetch plan và projection vẫn quan trọng.

### 19.4. clear trong batch read

Nếu một job stream hàng trăm nghìn entity, có thể dùng StatelessSession, cursor/stream hoặc chia transaction/context. Với Session stateful, flush/clear có tác động đến mọi managed entities; đừng clear giữa lúc caller còn cần dirty checking.

## 20. JDBC batching ghi dữ liệu khác batch fetching đọc dữ liệu

Hai khái niệm tên gần nhau:

| Khái niệm | Hướng | Mục đích |
|---|---|---|
| Batch fetching | Read | Gom lazy proxy/collection loads vào ít SELECT hơn |
| JDBC statement batching | Write | Gửi nhiều INSERT/UPDATE/DELETE qua JDBC batch |

Property:

~~~properties
hibernate.default_batch_fetch_size=32
~~~

liên quan batch fetch.

Property:

~~~properties
hibernate.jdbc.batch_size=50
~~~

liên quan JDBC batching.

Không đặt một property rồi mong cả hai loại batch cùng hoạt động.

### 20.1. JDBC insert batching

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Đây là cấu hình ứng viên cho write workload. IDENTITY generation có thể hạn chế insert batching vì Hibernate cần INSERT để lấy ID; SEQUENCE/pooled generators thường thuận lợi hơn tùy DB/provider.

### 20.2. Batch fetch không gộp UPDATE

Nếu 50 Orders được sửa, `@BatchSize` trên entity không tự gom 50 UPDATE thành JDBC batch. Cần cấu hình JDBC batch, generator và transaction đúng.

### 20.3. saveAll không đồng nghĩa JDBC batch

Spring Data saveAll thường lặp gọi save cho từng entity. Hibernate có thể batch SQL nếu cấu hình/conditions cho phép, nhưng saveAll không phải một câu INSERT nhiều rows và không tự đảm bảo batching.

## 21. EntityGraph và fetch type mặc định

Jakarta Persistence có default:

- `@ManyToOne` và `@OneToOne`: EAGER theo mặc định.
- `@OneToMany` và `@ManyToMany`: LAZY theo mặc định.

### 21.1. EAGER không đồng nghĩa một JOIN

Một to-one EAGER có thể được Hibernate tải bằng secondary SELECT thay vì join trong query root, tùy query path/provider. Điều này có thể tạo N+1 khi load nhiều root entity mà query không fetch join association.

### 21.2. Ưu tiên mapping LAZY và fetch plan theo use case

Đặt association to-one LAZY một cách chủ động:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

rồi chọn JOIN FETCH/EntityGraph/batch fetch ở query cụ thể. Điều này tránh mọi use case vô tình tải toàn bộ graph.

### 21.3. EAGER graph có thể lan sâu

Một association EAGER trỏ tới entity khác có nhiều EAGER associations có thể khiến graph tải rộng ngoài dự định. Không dùng EAGER làm cách chữa lazy exception hoặc N+1.

### 21.4. Fetch type là một phần mapping, query fetch plan vẫn quan trọng

LAZY là yêu cầu/provider hint tùy association và enhancement; EAGER là yêu cầu eager semantics nhưng không quy định một SQL duy nhất. Đo SQL thực tế thay vì chỉ đọc annotation.

## 22. Nhiều truy vấn nhỏ có thể gặp consistency issue

Giả sử phương án DTO chạy:

1. Query Orders page.
2. Query Items theo Order IDs.
3. Query Shipments theo Order IDs.

Giữa query 1 và 2, một transaction khác có thể thêm Item hoặc xóa Shipment.

### 22.1. READ COMMITTED

PostgreSQL READ COMMITTED tạo snapshot mới cho từng statement. Ba query có thể nhìn ba thời điểm committed khác nhau. DTO có thể chứa Order header ở thời điểm T1 và Items ở T2.

### 22.2. REPEATABLE READ

REPEATABLE READ trong một transaction có thể cung cấp snapshot ổn định cho các SELECT (theo semantics PostgreSQL). Điều đó tăng consistency nhưng transaction dài hơn có thể ảnh hưởng MVCC/vacuum và conflict behavior.

### 22.3. Khi nào consistency quan trọng?

- Báo cáo cần một snapshot nhất quán.
- Hóa đơn/tổng tiền phải khớp từng dòng.
- Trạng thái thanh toán/fulfillment thay đổi đồng thời.
- UI dashboard có thể chấp nhận dữ liệu hơi lệch thời điểm.

Chọn isolation/business semantics trước, rồi chọn số query. Không hy sinh consistency chỉ để giảm một round trip.

### 22.4. Snapshot read model

Với reporting phức tạp, có thể tạo một projection/materialized view/read model cập nhật riêng. Đó là quyết định kiến trúc eventual consistency, không chỉ là một mẹo Hibernate fetch.

## 23. Một query join lớn có thể được database tối ưu tốt

Không nên kết luận JOIN luôn xấu. Một query:

~~~sql
SELECT o.id, o.order_number, c.name
FROM purchase_orders o
JOIN customers c
  ON c.id = o.customer_id
WHERE o.organization_id = ?
ORDER BY o.created_at DESC
LIMIT 50;
~~~

có thể rất hiệu quả:

- Một round trip.
- Join theo PK/FK.
- Chỉ trả 50 rows.
- Index phù hợp.
- To-one cardinality giới hạn.

Một query DTO join một vài to-one associations thường là thiết kế tốt.

### 23.1. Đừng tách query nhỏ chỉ vì “JOIN tốn”

Nếu một query lấy Orders và Customer chỉ trả 50 rows, tách thành 1 query Orders + 50 query Customer sẽ tạo N+1 không cần thiết. JOIN/DTO projection có thể tốt hơn.

### 23.2. Tách khi cardinality to-many làm rowset nở

Khi join nhiều collections, rows có thể tăng theo tích cardinality. Tách collection ra query batch/projection thường có lợi.

### 23.3. Đo query ở production-like dataset

Một JOIN chạy tốt với 20 rows trong dev không chứng minh chạy tốt với 2 triệu Orders. Dữ liệu phân bố, statistics và cache ảnh hưởng execution plan.

## 24. Kết hợp JOIN FETCH và batch fetch

Một chiến lược thường hữu ích:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.organizationId = :organizationId
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .setParameter("organizationId", organizationId)
    .getResultList();
~~~

Customer được JOIN FETCH. Items vẫn LAZY với:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderItem> items;
~~~

Khi service thật sự truy cập Items, Hibernate batch load collections. Kết quả:

- Một query root + customer.
- Một hoặc vài query batch Items.
- Không cần JOIN đồng thời Customer, Items, Shipments, Payments.

Đây là ví dụ tốt của **fetch plan hỗn hợp theo cardinality**.

## 25. SUBSELECT kết hợp pagination và query scope

SUBSELECT có thể dùng query root làm cơ sở tải collections cho một nhóm owners. Nhưng nếu query root được phân trang, chỉ những owners trong tập phù hợp nên được tải theo semantics của Hibernate/session.

Kiểm thử:

1. Tạo 100 Orders.
2. Query page 20 Orders.
3. Initialize Items của một Order.
4. Xem SQL subselect có giới hạn đúng tập owners và không vô tình tải toàn bộ 100 Orders không.
5. Đo số rows và bytes.

Không giả định mọi Hibernate version tạo subselect giống nhau trong mọi query form. Nếu yêu cầu scope/pagination rất nghiêm ngặt, query child theo explicit ID list thường dễ dự đoán hơn.

## 26. Lọc tenant/soft delete phải giữ nguyên trong mọi fetch strategy

Một query:

~~~hql
select o
from PurchaseOrder o
left join fetch o.items
where o.organizationId = :orgId
  and o.deletedAt is null
~~~

giới hạn root Order, nhưng **chưa chắc đủ** để đảm bảo Items cũng thuộc đúng organization/đang active nếu mapping và database không enforce quan hệ. Child query, filter và composite FK cần được thiết kế riêng.

### 26.1. JOIN không tự thay authorization

Fetch join Customer không xác minh caller có quyền đọc Customer ngoài organization nếu schema/association cho phép cross-org link. Query predicate, service authorization và FK ghép vẫn quan trọng.

### 26.2. Batch fetch cũng phải có filter scope đúng

Filter Session có thể tác động các collection/entity loads phù hợp khi batch fetch. Nhưng entity/collection đã initialized hoặc direct load-by-key có những giới hạn khác. Không đổi tenant filter giữa một Session có nhiều managed objects.

### 26.3. DTO child query phải có organization predicate

~~~hql
select new com.example.OrderItemRow(
    i.order.id, i.id, i.sku
)
from OrderItem i
where i.organizationId = :trustedOrgId
  and i.order.id in :orderIds
~~~

Không bỏ organization predicate chỉ vì orderIds vừa được lấy từ một query đã scoped; kiểm soát cả child path và integrity database.

## 27. Fetch plan cho màn hình list và detail nên khác nhau

### 27.1. List page

Chỉ cần:

- Order ID/number.
- CreatedAt/status/total.
- Customer name.
- Item count.

Một DTO projection với JOIN to-one và COUNT/SUBQUERY có thể tốt hơn load entity graph toàn bộ Items.

~~~hql
select new com.example.OrderListRow(
    o.id, o.orderNumber, o.status,
    c.name, count(i.id)
)
from PurchaseOrder o
join o.customer c
left join o.items i
where o.organizationId = :orgId
group by o.id, o.orderNumber, o.status, c.name
order by o.id desc
~~~

Query minh họa cần thêm sort/pagination và các điều kiện thực tế; nếu join nhiều collections cùng lúc, aggregate có thể bị nhân bản. COUNT(DISTINCT i.id) hoặc subquery/projection riêng có thể cần tùy join shape.

### 27.2. Detail page

Một Order cụ thể có thể có:

- Customer.
- Items và Product names.
- Shipments.
- Payment summary.

Vì root chỉ có một Order, join fetch một collection nhỏ có thể ổn. Nếu mỗi association có nhiều rows hoặc graph sâu, tách 2–4 queries rõ ràng có thể dễ kiểm soát hơn.

### 27.3. Export

Export 100.000 Orders thường không nên hydrate tất cả entities cùng graph trong một persistence context. Cân nhắc DTO projection/streaming/cursor, chia chunk, transaction ngắn và backpressure.

### 27.4. Dashboard

Dashboard thường cần aggregate counts/sums, không cần mọi entity. Query projection/aggregate hoặc read model phù hợp hơn batch fetch collection chỉ để tính số lượng.

## 28. Batch size nên chọn thế nào?

Không có con số chung. Các giá trị 16, 32, 64 thường là điểm bắt đầu để benchmark, không phải luật.

### 28.1. Batch quá nhỏ

- Nhiều round trips.
- N+1 chưa được giảm đủ.
- Overhead query/statement vẫn cao.

### 28.2. Batch quá lớn

- IN list dài và nhiều bind parameters.
- Query plan/parse overhead tăng.
- Mỗi query trả nhiều rows hơn cần thiết.
- Driver/database limits có thể bị vượt.
- Một lần truy cập lazy có thể tải thêm dữ liệu chưa cần.

### 28.3. Batch size phụ thuộc số proxy cần truy cập

Nếu một request chỉ cần 5 Customers, batch 64 có thể tải thêm những proxy khác trong context. Nếu luôn cần 100 collections, batch 32 có thể hợp lý. Đo theo pattern thực tế.

### 28.4. Chia batch theo database

Database có giới hạn số bind parameters/SQL statement size khác nhau. Hibernate có thể xử lý batch size theo dialect/provider, nhưng không nên đặt batch size lớn hơn khả năng vận hành mà không test. Nếu dùng composite IDs hoặc filter parameters, mỗi entity ID có thể tiêu tốn nhiều bind parameters.

## 29. Lưu ý về query cache và second-level cache

Cache có thể làm số SQL giảm, nhưng không tự sửa fetch plan kém.

### 29.1. First-level cache

Trong một persistence context, cùng entity ID có thể được tái sử dụng. Nếu test N+1 với cùng Customer ID nhiều lần, L1 có thể làm số query thấp hơn thực tế production nơi mỗi request có context mới.

### 29.2. Second-level cache

Entity/collection cache có thể tránh một số SELECT khi cache hit. Nhưng:

- Cache miss vẫn cần query.
- Cache invalidation và concurrency cần thiết kế.
- Cache có thể làm benchmark quá lạc quan nếu warm cache.
- Không dùng cache để che một query pattern N+1.

### 29.3. Query cache

Query cache thường cache kết quả định danh/keys theo provider semantics, không phải lúc nào cũng lưu nguyên toàn bộ row data. Nó có overhead invalidation và phụ thuộc query/region. Với truy vấn có cardinality lớn hoặc dữ liệu đổi thường xuyên, query cache có thể không có lợi.

### 29.4. Benchmark cold và warm

Đo ít nhất:

- Cold L1/L2/query cache.
- Warm cache sau vài lượt.
- Cache invalidation khi write.
- Nhiều tenants/organizations.
- Traffic concurrent.

Không báo cáo chỉ một con số warm cache rồi kết luận fetch strategy tối ưu.

## 30. Streaming và xử lý tập dữ liệu lớn

Spring Data repository có thể trả Stream cho một số query:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.organizationId = :orgId
    order by o.id
    """)
Stream<PurchaseOrder> streamForExport(
    @Param("orgId") Long organizationId);
~~~

Sử dụng:

~~~java
@Transactional(readOnly = true)
public void export(Long organizationId) {
    try (Stream<PurchaseOrder> stream =
             repository.streamForExport(organizationId)) {
        stream.forEach(this::writeRow);
    }
}
~~~

### 30.1. Stream không có nghĩa không dùng bộ nhớ

Provider/driver có thể buffer result set, persistence context vẫn giữ managed entities và serializer có thể load associations. Cần kiểm tra fetch size, cursor behavior, driver/database và transaction lifecycle.

### 30.2. Không stream entity rồi truy cập nhiều lazy collections tùy tiện

Nếu mỗi row stream load Items riêng, N+1 vẫn tồn tại. Batch fetch có thể giảm nhưng persistence context và stream iteration order ảnh hưởng batch. DTO query hoặc export theo chunk có thể dễ kiểm soát hơn.

### 30.3. Clear theo chunk

Nếu xử lý entity read-only trong chunk, có thể clear persistence context theo chu kỳ sau khi chắc chắn không còn cần entity cũ. Nhưng clear detach mọi entity; không làm khi caller giữ references cần lazy load.

## 31. Query plan và join order không hoàn toàn do Hibernate quyết định

Hibernate tạo SQL dựa trên query/mapping/dialect; database optimizer quyết định execution plan.

Một JOIN có thể:

- Bắt đầu từ bảng nhỏ có index tốt.
- Hash join với bảng lớn.
- Nested loop qua index.
- Chọn seq scan khi phần lớn rows cần thiết.

Một SQL ngắn không bảo đảm plan rẻ. Ngược lại SQL dài có thể được optimizer thực thi tốt.

### 31.1. Estimated vs actual rows

Nếu optimizer ước tính 10 rows nhưng thực tế 100.000, join order có thể kém. Cập nhật statistics và xem data skew/tenant cardinality.

### 31.2. Filter selectivity

Tenant 7 có 50 rows, tenant 8 có 5 triệu rows. Cùng một query shape có thể có plan tốt ở một tenant và chậm ở tenant khác. Benchmark theo tenant lớn nhất/đại diện.

### 31.3. Bind parameters và generic plans

Prepared statements/driver/database có thể dùng custom/generic plans tùy cấu hình. Query có parameter selectivity lệch có thể có plan khác nhau. Đừng chỉ EXPLAIN với literal cố định; xem behavior qua prepared statements của ứng dụng khi vấn đề xuất hiện.

## 32. Một chiến lược đọc hoàn chỉnh cho Order list

Yêu cầu:

- Page 30 Orders thuộc organization hiện tại.
- Hiển thị customerName.
- Hiển thị itemCount.
- Hiển thị shipmentCount.
- Không cần từng Item/Shipment object.

### 32.1. Không fetch toàn graph

Không cần:

~~~hql
select o
from PurchaseOrder o
left join fetch o.customer
left join fetch o.items
left join fetch o.shipments
~~~

vì API chỉ cần hai số đếm.

### 32.2. Một DTO query aggregate

Có thể dùng scalar subqueries:

~~~hql
select new com.example.OrderSummaryRow(
    o.id,
    o.orderNumber,
    c.name,
    (select count(i.id)
       from OrderItem i
      where i.order.id = o.id),
    (select count(s.id)
       from Shipment s
      where s.order.id = o.id)
)
from PurchaseOrder o
join o.customer c
where o.organizationId = :orgId
order by o.createdAt desc, o.id desc
~~~

Scalar subquery có thể được optimizer xử lý tốt nếu FK indexes phù hợp; cũng có thể tốn nếu planner chạy lặp theo root. Phải EXPLAIN trên database thật.

### 32.3. Hoặc ba query page + grouped counts

1. Page root Orders + Customer.
2. Query `SELECT order_id, COUNT(*) FROM order_items WHERE order_id IN (...) GROUP BY order_id`.
3. Query grouped shipment counts.

Cách này có 3 round trips nhưng mỗi child query xử lý cả tập page IDs và trả tối đa 30 rows. Với page size nhỏ, nó thường dễ đo.

### 32.4. Map counts mặc định bằng 0

Khi ghép DTO, Order không có Item/Shipment sẽ không xuất hiện trong grouped result. Map thiếu key thành 0; không bỏ Order khỏi trang.

## 33. Một chiến lược detail page cho một Order

Với một Order ID:

1. Query Order + Customer.
2. Query Items + Product.
3. Query Shipments.
4. Query Payment summary.

Nếu mỗi collection nhỏ và tất cả luôn cần, một join fetch Items có thể là lựa chọn tốt; Shipments/Payments vẫn query riêng để tránh tích cardinalities.

### 33.1. Nếu detail chỉ cần một collection

Một JOIN FETCH cho Order + Items có thể đơn giản và nhanh. Vì root chỉ có một Order, pagination root không phải vấn đề.

### 33.2. Nếu một Order có 10.000 Items

Không fetch cả collection chỉ để hiển thị 20 dòng đầu. Query riêng Items theo orderId có pagination/keyset:

~~~sql
SELECT id, line_number, sku, quantity
FROM order_items
WHERE organization_id = :orgId
  AND order_id = :orderId
  AND (
      line_number > :lastLine
      OR (line_number = :lastLine AND id > :lastId)
  )
ORDER BY line_number, id
LIMIT 50;
~~~

Đây là child resource pagination; không cần initialize toàn bộ entity collection của Order.

## 34. Kiểm thử N+1 và fetch plan

### 34.1. Dữ liệu test phải đủ lớn

Seed ít nhất:

- 30–100 Orders.
- Mỗi Order có nhiều Items.
- Nhiều Customer khác nhau.
- Một số Orders cùng Customer để kiểm tra L1 reuse.
- Shipment cardinality khác nhau.
- Dữ liệu active/deleted/tenant phù hợp.

Hai Orders không đủ để nhận ra row explosion hoặc batch size behavior.

### 34.2. SQL statement count

Hibernate Statistics:

~~~java
SessionFactory sf =
    entityManagerFactory.unwrap(SessionFactory.class);
Statistics statistics = sf.getStatistics();
statistics.clear();

// Gọi use case đã cô lập.

long queryCount = statistics.getPrepareStatementCount();
~~~

Statistics là bộ đếm cấp SessionFactory; test phải tránh query từ thread khác và reset/capture đúng thời điểm. Nó có thể đếm prepared statements rộng hơn query SELECT tùy hoạt động; dùng datasource proxy/SQL capture nếu cần phân loại.

### 34.3. Assert không có N+1 bằng ngưỡng hợp lý

Không nhất thiết assert chính xác 3 query nếu provider version hoặc count query thay đổi. Có thể:

- Assert query count nhỏ hơn ngưỡng theo page size.
- Assert số query không tăng tuyến tính từ 10 lên 50 Orders.
- Assert SQL pattern có IN batch.
- Assert không có SELECT lặp theo từng Order ID.

### 34.4. Đo rows và bytes

Statement count không cho biết row count/bytes. Dùng:

- PostgreSQL EXPLAIN ANALYZE/BUFFERS.
- Driver/database metrics.
- Datasource proxy hoặc JDBC instrumentation.
- APM spans.
- Network/response size metrics.

### 34.5. Test collection pagination warning

Bật:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Rồi chạy query collection fetch với Pageable. Test nên fail nếu code vô tình dùng collection fetch pagination thay vì âm thầm tải toàn bộ result set rồi cắt trong memory.

### 34.6. Test cold persistence context

Mỗi test fetch strategy nên mở transaction/EntityManager mới hoặc clear context trước khi đo, tránh L1 cache làm số query thấp giả tạo. Kiểm soát L2/query cache khi cần đo cold path.

## 35. Benchmark: so sánh ba chiến lược công bằng

Giả sử cùng một API, cùng dataset, cùng organization và cùng response DTO.

### 35.1. Chiến lược A — JOIN lớn

Đo:

- Một query SQL.
- Actual rows.
- Bytes/result width.
- DB execution time.
- Hibernate hydration time.
- Heap allocations.

### 35.2. Chiến lược B — batch fetch

Đo:

- Root query + số batch child queries.
- Tổng child rows.
- Số proxies/collections được initialize.
- Persistence context size.
- Thời gian lazy traversal.

### 35.3. Chiến lược C — nhiều DTO queries

Đo:

- Số round trips cố định.
- Tổng rows và bytes.
- CPU/heap cho grouping.
- Thời gian ghép DTO.
- Consistency/isolation giữa statements.

### 35.4. Chạy cold và warm

Chạy nhiều vòng sau warm-up JVM/JIT, nhưng reset database/cache state phù hợp. Ghi p50, p95, p99 thay vì chỉ một lượt. Không dùng dữ liệu ngẫu nhiên quá nhỏ làm đại diện.

### 35.5. Tăng concurrency

Một query nhanh ở một request có thể gây contention khi 100 requests đồng thời. Đo:

- DB CPU/I/O.
- Active/idle pool connections.
- Lock waits.
- Queue time.
- Request latency distribution.
- Throughput và error rate.

## 36. Cấu hình Hibernate thường liên quan

Các property minh họa:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 32
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
        query:
          fail_on_pagination_over_collection_fetch: true
~~~

Lưu ý:

- `default_batch_fetch_size`: batch fetch cho lazy entity/collection loads.
- `jdbc.batch_size`: JDBC statement batching cho writes.
- `order_inserts`, `order_updates`: có thể hỗ trợ gom statements theo entity/table để batch.
- `fail_on_pagination_over_collection_fetch`: chặn pagination collection fetch nguy hiểm trong các phiên bản hỗ trợ.

Đây là cấu hình ví dụ, không phải cấu hình tối ưu mặc định. Kiểm tra Hibernate property names và support theo version đang dùng.

## 37. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| 1 query root rồi nhiều SELECT giống nhau | N+1 từ lazy to-one/to-many | JOIN FETCH to-one, batch fetch hoặc query child theo IDs |
| Một SQL duy nhất nhưng endpoint vẫn chậm | Row multiplication, row width, sort/hash nặng | Đo actual rows/bytes; tách to-many collections |
| Hibernate ném MultipleBagFetchException | Fetch đồng thời nhiều bag collections | Tách queries/batch; không đổi List thành Set chỉ để né |
| Page 20 Orders tải hàng nghìn rows | Pagination collection fetch | Page IDs trước, fetch graph/query child sau |
| Page query cảnh báo in-memory pagination | Hibernate phải cắt root sau collection fetch | Bật fail_on_pagination_over_collection_fetch |
| Thêm DISTINCT nhưng vẫn chậm | Database vẫn join và xử lý rows lặp | Giảm collection joins, DTO/multi-query |
| Batch size lớn hơn nhưng không nhanh | Ít proxies được truy cập hoặc IN query nặng | Đo batch hit rate và batch size |
| Batch fetch vẫn có nhiều query | Association khác role/type, batch queue nhỏ, context/cache | Phân tích từng association và SQL |
| SUBSELECT tải quá nhiều collection | Root set rộng, mọi owner trong nhóm bị ảnh hưởng | Batch fetch hoặc query child theo IDs |
| EntityGraph vẫn có N+1 | Provider dùng secondary selects hoặc graph chưa đúng | SQL logging và batch fetch/query plan |
| EAGER gây N+1 | EAGER không đồng nghĩa JOIN | LAZY + fetch plan theo use case |
| DTO query vẫn chậm | Join/aggregate/index kém | EXPLAIN ANALYZE, selectivity, index |
| Stream vẫn ăn nhiều heap | Persistence context/driver buffer giữ dữ liệu | Cursor/fetch size/chunk/clear/DTO |
| saveAll không batch INSERT | JDBC batch chưa cấu hình hoặc IDENTITY | jdbc.batch_size, generator, transaction |
| Test query count thấp hơn production | L1/L2 cache warm, fixture nhỏ | Context mới, cold cache, dataset lớn |
| Query count ít nhưng network lớn | Result set quá rộng | Projection, bỏ cột/collection không cần |
| Batch fetch vượt bind limit | Batch size/ID composite quá lớn | Giảm size, chunk hoặc DB-specific strategy |
| Join query chậm chỉ với tenant lớn | Data skew/cardinality/plan | Benchmark tenant lớn, statistics và plan |
| DTO child query trả thiếu rows | IN list rỗng/scope/filter sai | Xử lý empty IDs và predicate rõ |
| Nhiều query không nhất quán | READ COMMITTED snapshots khác nhau | Xác định isolation/business consistency |

## 38. Bài thực hành

### Bài A — Tạo N+1 có chủ đích

1. Tạo 50 Orders và 50 Customers.
2. Load Orders bằng một query.
3. Duyệt `getCustomer().getName()`.
4. Bật SQL log và Hibernate Statistics.
5. Xác định số SELECT và L1 cache reuse.
6. Giải thích vì sao số query thay đổi theo số Customer distinct.

### Bài B — JOIN FETCH to-one

1. Viết query join fetch Customer.
2. Chạy lại cùng fixture trong persistence context mới.
3. So sánh số query và rows.
4. Thử inner join với Customer null và left join.
5. Kiểm tra SQL không load association ngoài yêu cầu.

### Bài C — JOIN to-many và row multiplication

1. Mỗi Order tạo 8 Items và 3 Shipments.
2. Fetch join cả hai collections.
3. Tính rows dự kiến 24 mỗi Order.
4. So sánh SQL rows với số entity/collection thực tế.
5. Thử DISTINCT và quan sát execution plan.
6. Thử nhiều bag collections và nhận diện MultipleBagFetchException nếu mapping thuộc trường hợp đó.

### Bài D — Batch fetch

1. Đặt @BatchSize(16) trên Customer.
2. Đặt @BatchSize(16) trên Order.items.
3. Load 50 Orders.
4. Truy cập Customer và Items.
5. Quan sát SQL IN queries và số batches.
6. Thay batch size 8, 16, 32, 64 và đo.
7. Thử cache cold/warm.

### Bài E — SUBSELECT

1. Gắn @Fetch(FetchMode.SUBSELECT) cho Items.
2. Load page Orders.
3. Initialize Items của một Order.
4. Quan sát subselect scope.
5. So sánh với batch fetch.
6. Thử page size lớn và chỉ truy cập một collection.

### Bài F — Pagination an toàn

1. Tạo page IDs theo createdAt/id.
2. Fetch Customer cho IDs.
3. Query Items theo orderIds.
4. Query Shipments theo orderIds.
5. Ghép DTO và giữ thứ tự page IDs.
6. Kiểm tra count query và empty page.
7. Bật fail_on_pagination_over_collection_fetch.

### Bài G — DTO projection và aggregate

1. Viết OrderListRow projection chỉ gồm các cột API cần.
2. Thêm itemCount/shipmentCount bằng grouped queries hoặc scalar subquery.
3. So sánh với entity graph toàn bộ.
4. Đo bytes, rows, heap và latency.
5. Dùng EXPLAIN ANALYZE để xem index/plan.

### Bài H — Consistency và concurrency

1. Query root page trong transaction T1.
2. Transaction T2 thêm Item rồi commit.
3. T1 query Items.
4. So sánh READ COMMITTED và REPEATABLE READ trên PostgreSQL.
5. Quyết định consistency contract cho list/detail/report.

### Bài I — Benchmark production-like

1. Seed 100.000 Orders, cardinality Items/Shipments phân bố lệch.
2. Chạy ba chiến lược JOIN, batch fetch, nhiều DTO queries.
3. Đo cold/warm cache.
4. Tăng concurrency.
5. Ghi p50/p95/p99, DB time, rows, bytes, heap, pool waits.
6. Chọn chiến lược dựa trên workload và SLA.

## 39. Checklist chọn fetch strategy

1. Use case cần **entity để thay đổi** hay chỉ cần **DTO để đọc**?
2. Root query trả bao nhiêu rows/page?
3. Association là to-one hay to-many?
4. Cardinality trung bình và p95/p99 của child collection là bao nhiêu?
5. Có JOIN nhiều collections làm nhân rows không?
6. Có fetch nhiều bag collections gây MultipleBagFetchException không?
7. Có pagination root cùng collection fetch không?
8. Có thể JOIN FETCH to-one và batch fetch to-many không?
9. Batch fetch size có phù hợp bind limits và access pattern không?
10. SUBSELECT có tải collections của quá nhiều owners không?
11. DTO projection có giảm cột/heap tốt hơn entity graph không?
12. Nhiều query nhỏ có làm round trips quá đắt không?
13. Query root/child có index đúng theo WHERE/JOIN/ORDER BY không?
14. SQL execution plan có estimate/actual rows lệch lớn không?
15. Có dữ liệu lớn, tenant skew hoặc row width cao không?
16. Persistence context có giữ quá nhiều managed entities không?
17. L1/L2/query/application cache có làm benchmark sai lệch không?
18. Multi-query có consistency requirement giữa các statements không?
19. Có filter/soft-delete/tenant scope cần áp dụng ở child queries không?
20. Có native SQL/bulk DML/cache path không chịu fetch plan/filter như entity query không?
21. Query count có tăng tuyến tính theo số root entities không?
22. Đã đo rows/bytes/latency/heap và DB plan chưa?
23. Đã kiểm thử cold/warm và concurrent workload chưa?
24. Có kiểm tra SQL phát sinh trong JSON serialization ngoài service không?
25. Fetch strategy có thể giải thích và bảo trì theo từng màn hình/use case không?

## 40. Tổng kết: tối ưu theo cardinality và dữ liệu thực

~~~mermaid
flowchart TD
    A[Chọn dữ liệu cần cho use case] --> B{To-one nhỏ và cần ngay?}
    B -->|Có| C[JOIN FETCH / EntityGraph]
    B -->|Không| D{To-many cần toàn bộ?}
    D -->|Không| E[DTO/projection/aggregate query]
    D -->|Có| F{Root set nhỏ, collection nhỏ?}
    F -->|Có| G[Fetch join một collection có kiểm soát]
    F -->|Không| H{Nhiều owners lazy cùng role?}
    H -->|Có| I[Batch fetch hoặc SUBSELECT]
    H -->|Không| J[Query child riêng theo tập root IDs]
    C --> K[Đo rows, bytes, latency, heap, plan]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

Những nguyên tắc cần nhớ:

1. **N+1 là vấn đề round trips tăng theo số root rows**, thường xuất hiện khi lazy associations được truy cập trong vòng lặp hoặc serializer.
2. **JOIN FETCH to-one thường là lựa chọn tốt** khi cần association ngay và cardinality được giới hạn.
3. **JOIN to-many làm nhân rows**; join hai collection có thể nhân cardinalities với nhau dù Hibernate cuối cùng chỉ dựng một object graph.
4. **DISTINCT không xóa chi phí join/result rows**; nó chủ yếu xử lý semantics duplicate root và có thể thêm sort/hash.
5. **Không pagination trực tiếp trên collection fetch join** nếu muốn phân trang root chính xác. Page IDs trước, rồi fetch associations/DTOs sau.
6. **Batch fetch giảm N+1 bằng cách gom lazy loads**, nhưng không loại bỏ child rows và vẫn cần chọn batch size theo workload.
7. **SUBSELECT phù hợp khi nhiều owners từ một root query đều cần collection cùng role**, nhưng có thể tải rộng hơn cần thiết.
8. **Nhiều query nhỏ có chủ đích có thể nhanh hơn một JOIN khổng lồ**, nhất là khi lấy nhiều to-many associations hoặc DTO list/report.
9. **DTO projection giảm entity hydration và cột thừa**, nhưng query/aggregate vẫn phải có plan và indexes tốt.
10. **Batch fetching đọc khác JDBC batching ghi**; hai cơ chế có property và mục tiêu riêng.
11. **Query count không đủ để đánh giá**: đo actual rows, bytes, DB execution, hydration, heap, latency và concurrency.
12. **L1/L2 cache có thể che N+1 trong test**; benchmark phải có cold/warm scenarios và persistence context được kiểm soát.
13. **Nhiều query có consistency trade-off**; xác định isolation/snapshot requirement của nghiệp vụ trước.
14. **Fetch plan nên theo use case**: list, detail, export và dashboard thường cần những tập dữ liệu khác nhau.

Điểm cốt lõi: tối ưu Hibernate không phải cuộc thi giảm số câu SQL xuống một. Hãy chọn cách lấy dữ liệu sao cho **ít round trips hợp lý, ít rows và bytes thừa, không dựng graph không cần thiết, giữ pagination đúng và phù hợp consistency của nghiệp vụ**. JOIN lớn, batch fetch và nhiều query nhỏ đều là công cụ; chiến lược tốt nhất là chiến lược đã được đo trên dữ liệu và tải gần với production.
