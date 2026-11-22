# Kết quả đơn trả nhiều hàng hoặc truy vấn không có kết quả

Trong **Spring Data Relational JDBC**, repository method có thể trả về một entity, một `Optional<T>` hoặc một collection. Kiểu trả về thể hiện số lượng kết quả mà ứng dụng mong đợi. Nếu một query được khai báo trả về một entity nhưng database tìm thấy nhiều hàng, Spring Data không tự chọn ngẫu nhiên một hàng: thao tác thường thất bại với `IncorrectResultSizeDataAccessException`. Nếu không tìm thấy hàng nào, kết quả phụ thuộc kiểu trả về: `Optional` sẽ là empty, collection sẽ rỗng, còn kiểu entity đơn có thể trả về `null`.

Đây là vấn đề thường gặp khi query theo email, mã đơn hàng, số điện thoại hoặc một khóa nghiệp vụ mà dữ liệu thực tế không còn duy nhất. Nó cũng có thể xuất hiện khi join tạo ra nhiều hàng cho cùng một entity. Để xử lý đúng, cần xác định query thực sự có ý nghĩa “không quá một hàng”, “lấy một hàng phù hợp nhất” hay “lấy tất cả hàng phù hợp”.

## 1. Ba trường hợp cardinality của query

Một query có thể trả về ba trạng thái:

| Số hàng khớp | Ý nghĩa | Kết quả mong đợi |
| ---: | --- | --- |
| 0 | Không có dữ liệu phù hợp | Empty, null hoặc collection rỗng tùy kiểu trả về |
| 1 | Có đúng một hàng | Entity/value tương ứng |
| 2 trở lên | Có nhiều hàng phù hợp | Collection nếu query được thiết kế để lấy nhiều; lỗi nếu khai báo kết quả đơn |

Ví dụ tìm đơn hàng theo mã:

```sql
SELECT id, order_number, customer_id, status
FROM purchase_order
WHERE order_number = 'PO-2026-001';
```

Nếu order_number là khóa duy nhất, query phải trả về 0 hoặc 1 hàng. Nếu database có hai hàng cùng order_number do schema không có unique constraint hoặc dữ liệu cũ bị lỗi, method trả về một entity đơn không còn đáp ứng giả định cardinality.

Trước khi chọn kiểu trả về, hãy trả lời câu hỏi nghiệp vụ:

- Có thể không tồn tại bản ghi không?
- Nếu tồn tại, có tối đa một bản ghi theo invariant dữ liệu không?
- Nếu có nhiều bản ghi hợp lệ, ứng dụng cần tất cả hay chỉ bản ghi mới nhất/cũ nhất?
- Nếu có nhiều bản ghi ngoài dự kiến, đó là dữ liệu sai cần phát hiện hay là trường hợp hợp lệ cần xử lý?

## 2. Kiểu trả về đơn: entity hoặc value

Một query method có thể trả về một entity:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    PurchaseOrder findByOrderNumber(String orderNumber);
}
```

Với query method dạng này:

- Nếu có đúng một hàng, repository trả về entity.
- Nếu không có hàng, kết quả có thể là `null`.
- Nếu có nhiều hàng, Spring Data báo lỗi kích thước kết quả thay vì tự lấy một hàng bất kỳ.

Do trường hợp không tìm thấy có thể xảy ra, caller phải kiểm tra null trước khi sử dụng:

```java
PurchaseOrder order =
        repository.findByOrderNumber("PO-2026-001");

if (order == null) {
    throw new OrderNotFoundException("Order does not exist");
}

order.confirm();
```

Nếu domain cho phép “không tìm thấy” là kết quả bình thường, `Optional<PurchaseOrder>` thường diễn đạt ý định rõ hơn.

Không dùng kiểu trả về entity đơn chỉ vì ứng dụng tin rằng dữ liệu “chắc chắn có”. Query vẫn có thể không tìm thấy do ID sai, dữ liệu bị xóa, tenant filter, soft-delete condition hoặc trạng thái dữ liệu thay đổi.

## 3. Optional: không có hàng là Optional.empty()

`Optional<T>` là lựa chọn phù hợp cho một query có thể không tìm thấy entity:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
```

Sử dụng:

```java
Optional<PurchaseOrder> result =
        repository.findByOrderNumber("PO-2026-001");

if (result.isEmpty()) {
    // Xử lý trường hợp không tìm thấy.
}

PurchaseOrder order = result.orElseThrow(
        () -> new OrderNotFoundException("Order does not exist")
);
```

Với Spring Data repository, các phương thức như `CrudRepository.findById(id)` cũng trả `Optional<T>`:

```java
Optional<PurchaseOrder> result = repository.findById(123L);
```

Nếu ID không tồn tại, kết quả là `Optional.empty()`. Caller có thể quyết định trả HTTP 404, bỏ qua thao tác hoặc dùng một giá trị mặc định tùy use case.

### 3.1. Optional không giới hạn số hàng trong SQL

Điểm quan trọng: `Optional<T>` có nghĩa là kết quả mong đợi tối đa một entity. Nó không tự thêm `LIMIT 1` vào SQL và cũng không tự chọn hàng đầu tiên.

Nếu query:

```sql
SELECT id, email, display_name
FROM customer
WHERE email = 'alex@example.com';
```

trả về hai hàng, method:

```java
Optional<Customer> findByEmail(String email);
```

không trả một trong hai kết quả. Spring Data ném `IncorrectResultSizeDataAccessException` vì query đã vi phạm kỳ vọng kết quả đơn.

Đừng dùng Optional như một cách che giấu dữ liệu trùng. Nếu email phải duy nhất, hãy bảo đảm invariant đó ở database bằng unique constraint/index.

## 4. Collection: không có hàng là collection rỗng

Nếu nhiều kết quả là hợp lệ, khai báo collection:

```java
List<PurchaseOrder> findByCustomerId(Long customerId);
```

Kết quả:

- Không có đơn hàng: danh sách rỗng.
- Có một đơn hàng: danh sách một phần tử.
- Có nhiều đơn hàng: danh sách chứa các hàng phù hợp.

Ví dụ:

```java
List<PurchaseOrder> orders =
        repository.findByCustomerId(customerId);

if (orders.isEmpty()) {
    // Khách hàng chưa có đơn hàng.
}
```

Không cần dùng null để biểu diễn collection không có phần tử. Repository collection thường trả collection rỗng, vì vậy code có thể gọi `isEmpty()` trực tiếp.

Tùy use case, collection return type có thể là `List<T>`, `Collection<T>` hoặc một kiểu collection phù hợp. Nếu cần duyệt dữ liệu lớn, xem xét streaming/scrolling theo khả năng và contract của phiên bản Spring Data đang dùng; phải quản lý transaction và resource lifetime đúng cách.

## 5. Query không có kết quả với từng kiểu trả về

Các kiểu trả về phổ biến có semantics khác nhau khi không tìm thấy:

| Kiểu trả về | Khi không có hàng | Khi có nhiều hàng |
| --- | --- | --- |
| Entity đơn, ví dụ `PurchaseOrder` | `null` | `IncorrectResultSizeDataAccessException` |
| `Optional<PurchaseOrder>` | `Optional.empty()` | `IncorrectResultSizeDataAccessException` |
| `List<PurchaseOrder>` | List rỗng | Danh sách chứa tất cả kết quả |
| `Collection<PurchaseOrder>` | Collection rỗng | Collection chứa tất cả kết quả |
| `Set<PurchaseOrder>` | Set rỗng | Kết quả theo semantics của Set và equality |
| `Stream<PurchaseOrder>` | Stream không có phần tử | Stream các kết quả; cần đóng/quản lý resource theo contract |

Đừng nhầm query method trả entity đơn với các phương thức CRUD có contract riêng. Ví dụ:

- `findById(id)` trả `Optional<T>`.
- `findAll()` trả iterable/collection các entity.
- `findAllById(ids)` chỉ trả những entity tìm thấy; ID không tồn tại không tạo placeholder null trong kết quả.

## 6. IncorrectResultSizeDataAccessException

Khi một query được khai báo trả một kết quả đơn nhưng thực tế trả nhiều hàng, Spring Data thường ném:

```java
org.springframework.dao.IncorrectResultSizeDataAccessException
```

Exception này thuộc Spring DAO exception hierarchy. Nó cho biết số lượng kết quả thực tế không phù hợp với số lượng mà thao tác yêu cầu.

Ví dụ:

```java
Optional<Customer> customer =
        customerRepository.findByEmail("alex@example.com");
```

Nếu dữ liệu chứa hai customer cùng email, việc gọi repository có thể thất bại ngay ở tầng persistence. Service không nên bắt exception rồi tùy tiện lấy một hàng, vì như vậy sẽ che giấu vi phạm dữ liệu.

### 6.1. Vì sao exception xuất hiện?

Nguyên nhân phổ biến:

- Cột được xem là duy nhất nhưng database không có unique constraint.
- Dữ liệu import/migration tạo ra bản ghi trùng.
- Query filter chưa đủ điều kiện, ví dụ chỉ lọc tên thay vì tenant ID và mã.
- Join một-nhiều làm query trả nhiều hàng cho một entity gốc.
- Query custom có UNION hoặc join tạo duplicate rows.
- Một query trước đây có dữ liệu duy nhất nhưng sau đó quy tắc nghiệp vụ thay đổi.

### 6.2. Không nên bắt lỗi để chọn ngẫu nhiên một hàng

Không nên:

```java
try {
    return repository.findByEmail(email);
} catch (IncorrectResultSizeDataAccessException ex) {
    // Không nên lấy đại một customer để tiếp tục xử lý.
    return Optional.empty();
}
```

Đoạn code này biến lỗi dữ liệu thành “không tìm thấy”, khiến hệ thống có thể gắn dữ liệu hoặc hành động vào sai người dùng. Nếu nhiều hàng là lỗi invariant, hãy báo lỗi rõ, ghi log đủ ngữ cảnh an toàn và sửa dữ liệu/schema.

Nếu nhiều hàng là hợp lệ, thay đổi query contract thành collection hoặc một query “first/top” có thứ tự xác định.

## 7. Enforce uniqueness ở database

Nếu một giá trị phải duy nhất, database nên bảo vệ invariant đó. Ví dụ email đăng nhập duy nhất:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email);
```

Hoặc mã đơn hàng duy nhất:

```sql
ALTER TABLE purchase_order
ADD CONSTRAINT uk_purchase_order_number UNIQUE (order_number);
```

Unique constraint giúp:

- Ngăn hai transaction đồng thời tạo cùng giá trị duy nhất.
- Giữ invariant kể cả khi có nhiều application instance.
- Bảo vệ dữ liệu khi có script/import hoặc ứng dụng khác ghi vào database.
- Làm rõ giả định của query method trả về một kết quả.

### 7.1. Kiểm tra và xử lý dữ liệu trùng trước khi thêm constraint

Trước khi thêm unique constraint, tìm các giá trị bị trùng:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

Với khóa nghiệp vụ kết hợp:

```sql
SELECT tenant_id, external_code, COUNT(*) AS duplicate_count
FROM customer
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

Trước khi chạy migration:

1. Xác định quy tắc nào quyết định bản ghi giữ lại.
2. Hợp nhất/chuyển dữ liệu tham chiếu nếu có foreign key.
3. Xóa hoặc sửa các hàng trùng theo chính sách được duyệt.
4. Kiểm tra lại truy vấn duplicate.
5. Tạo unique constraint/index qua migration.
6. Kiểm thử hành vi khi insert giá trị trùng.

Không tự động xóa một hàng trùng chỉ dựa trên ID lớn hơn/nhỏ hơn nếu nghiệp vụ chưa xác định bản ghi nào là đúng.

### 7.2. Composite unique constraint

Một giá trị có thể chỉ duy nhất trong phạm vi tenant hoặc một loại đối tượng. Ví dụ external_code chỉ duy nhất trong từng tenant:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_tenant_external_code
UNIQUE (tenant_id, external_code);
```

Repository query phải dùng đủ các cột thuộc khóa nghiệp vụ:

```java
Optional<Customer> findByTenantIdAndExternalCode(
        Long tenantId,
        String externalCode
);
```

Chỉ lọc externalCode mà bỏ tenantId có thể trả nhiều hàng hợp lệ. Khi đó vấn đề không nằm ở repository; query chưa biểu diễn đầy đủ khóa nghiệp vụ.

### 7.3. Unique và NULL phụ thuộc database

Semantics của unique constraint với giá trị NULL khác nhau giữa các database và có thể có tùy chọn riêng. PostgreSQL mặc định xem các NULL là distinct trong unique constraint thông thường, nên có thể có nhiều hàng có NULL ở cột unique. PostgreSQL còn có tùy chọn `NULLS NOT DISTINCT` ở các phiên bản hỗ trợ.

Nếu quy tắc nghiệp vụ yêu cầu mọi hàng đều phải có giá trị duy nhất, thường cần kết hợp `NOT NULL` với `UNIQUE`:

```sql
ALTER TABLE customer
ALTER COLUMN email SET NOT NULL;

ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email);
```

Hãy xác nhận semantics của database đang dùng trước khi dựa vào unique constraint để bảo vệ query.

## 8. Khi nghiệp vụ chỉ cần một hàng: First hoặc Top

Đôi khi nhiều hàng là hợp lệ, nhưng use case chỉ cần bản ghi mới nhất hoặc ưu tiên cao nhất. Khi đó, dùng query giới hạn rõ ràng thay vì method trả một entity không giới hạn.

Spring Data hỗ trợ keyword `First` và `Top` trong derived query:

```java
Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);
```

Method này diễn đạt ý định lấy tối đa một đơn hàng mới nhất của customer. `IdDesc` là tie-breaker để thứ tự vẫn xác định khi hai đơn có cùng createdAt.

Các biến thể:

```java
Optional<PurchaseOrder> findTopByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);

List<PurchaseOrder> findTop5ByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);
```

Với `First`/`Top`:

- Không có hàng: Optional empty nếu return type là Optional.
- Có một hàng: trả hàng đó.
- Có nhiều hàng: database/repository giới hạn theo số lượng được chỉ định.

### 8.1. Luôn dùng thứ tự ổn định

Không nên:

```java
Optional<PurchaseOrder> findFirstByCustomerId(Long customerId);
```

Nếu không có `ORDER BY`, database không cam kết hàng nào được xem là “first”. Kết quả có thể đổi sau khi thêm index, vacuum, thay đổi plan hoặc cập nhật dữ liệu.

Nên:

```java
Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDescIdDesc(
        Long customerId
);
```

Một thứ tự ổn định cần đủ cột để phân biệt các hàng có cùng giá trị sort. Thường thêm primary key làm tie-breaker.

### 8.2. First/Top khác với kiểm tra uniqueness

Nếu email phải duy nhất, dùng FirstByEmail để tránh exception là che giấu dữ liệu trùng. First/Top phù hợp khi “chọn một hàng theo thứ tự ưu tiên” là yêu cầu nghiệp vụ thật sự, ví dụ bản ghi mới nhất hoặc sự kiện gần nhất.

## 9. Giới hạn kết quả bằng SQL trong @Query

Với query tùy biến, có thể dùng cú pháp giới hạn theo database. Ví dụ PostgreSQL:

```java
@Query("""
    SELECT id, customer_id, order_number, status, created_at
    FROM purchase_order
    WHERE customer_id = :customerId
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """)
Optional<PurchaseOrder> findLatestOrder(
        @Param("customerId") Long customerId
);
```

SQL có `LIMIT 1` nên chỉ trả tối đa một hàng. Tuy nhiên, `LIMIT 1` không thay thế unique constraint và cũng không tự xác định hàng nào nên được chọn nếu thiếu `ORDER BY`.

Ví dụ không ổn định:

```sql
SELECT *
FROM purchase_order
WHERE customer_id = 42
LIMIT 1;
```

Database có thể trả về bất kỳ hàng nào thỏa predicate. Nếu cần mới nhất, sắp xếp rõ:

```sql
SELECT *
FROM purchase_order
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 1;
```

SQL giới hạn hàng có thể phụ thuộc dialect. PostgreSQL/MySQL thường dùng `LIMIT`; SQL Server có thể dùng `TOP` hoặc `OFFSET/FETCH`; Oracle có cú pháp theo phiên bản. Nếu ứng dụng cần portable SQL, cân nhắc derived query First/Top hoặc dialect-aware query phù hợp.

## 10. Join có thể tạo nhiều hàng cho một entity

Một nguyên nhân tinh vi là query join một bảng cha với nhiều bảng con. Ví dụ:

```sql
SELECT o.id, o.order_number, o.status
FROM purchase_order o
JOIN order_line l
  ON l.purchase_order_id = o.id
WHERE o.order_number = 'PO-2026-001';
```

Nếu đơn hàng có ba dòng hàng, SQL trả ba hàng cho cùng order root. Một repository method khai báo trả về một `PurchaseOrder` có thể gặp lỗi nhiều kết quả, dù chỉ có một order trong bảng purchase_order.

### 10.1. Dùng EXISTS nếu chỉ cần kiểm tra có child phù hợp

Nếu mục đích là tìm order có ít nhất một line thuộc SKU cụ thể, dùng EXISTS:

```sql
SELECT o.id, o.order_number, o.status
FROM purchase_order o
WHERE o.order_number = 'PO-2026-001'
  AND EXISTS (
      SELECT 1
      FROM order_line l
      WHERE l.purchase_order_id = o.id
        AND l.sku = 'SKU-CHAIR'
  );
```

EXISTS kiểm tra sự tồn tại của child mà không nhân bản hàng root theo số child match.

### 10.2. Dùng DISTINCT khi semantics thực sự cần loại duplicate

Có thể dùng:

```sql
SELECT DISTINCT o.id, o.order_number, o.status
FROM purchase_order o
JOIN order_line l
  ON l.purchase_order_id = o.id
WHERE o.order_number = 'PO-2026-001';
```

Nhưng DISTINCT chỉ loại các hàng có cùng toàn bộ cột được chọn. Nếu projection chứa cột của child, các hàng vẫn khác nhau. Đừng dùng DISTINCT như một cách che giấu join sai hoặc dữ liệu sai.

### 10.3. Spring Data JDBC không tự khử trùng theo persistence context như ORM

Spring Data JDBC không duy trì persistence context/identity map kiểu JPA để tự hợp nhất mọi hàng join thành một aggregate object duy nhất. Custom query cần trả result set phù hợp với mapping contract của method. Nếu query cần aggregate có child, ưu tiên thiết kế query/repository theo mô hình Spring Data JDBC hoặc tách truy vấn root và child phù hợp.

## 11. Aggregate query và scalar result

Không phải mọi query trả về một giá trị đơn đều có semantics giống query entity.

Ví dụ `COUNT(*)` không có hàng phù hợp vẫn trả về một hàng chứa số 0:

```sql
SELECT COUNT(*)
FROM purchase_order
WHERE customer_id = 42;
```

Vì vậy method:

```java
long countByCustomerId(Long customerId);
```

có thể trả 0 nếu customer chưa có đơn hàng. Đây không phải trường hợp “không có result row”.

Ngược lại, các aggregate function như `SUM` hoặc `AVG` có thể trả NULL khi không có hàng đầu vào (tùy expression/query). Nếu cần giá trị mặc định, dùng `COALESCE`:

```sql
SELECT COALESCE(SUM(quantity), 0)
FROM order_line
WHERE purchase_order_id = 999;
```

Với query có `GROUP BY`, có thể không có group nào và do đó không trả result row. Hãy phân biệt giá trị aggregate NULL/0 với việc query không có hàng kết quả.

## 12. Scalar query không có kết quả và kiểu Java primitive

Nếu custom query trả một scalar như số lượng, tên hoặc giá trị tổng, kiểu trả về phải thể hiện đúng khả năng không có kết quả.

Ví dụ:

```java
@Query("""
    SELECT MAX(created_at)
    FROM purchase_order
    WHERE customer_id = :customerId
    """)
Instant findLatestCreatedAt(@Param("customerId") Long customerId);
```

MAX trên tập rỗng có thể trả SQL NULL. Kiểu Java reference có thể biểu diễn null; kiểu primitive như `long` hoặc `int` không thể biểu diễn null. Nếu giá trị có thể vắng mặt, cân nhắc wrapper hoặc Optional phù hợp:

```java
@Query("""
    SELECT MAX(created_at)
    FROM purchase_order
    WHERE customer_id = :customerId
    """)
Optional<Instant> findLatestCreatedAt(
        @Param("customerId") Long customerId
);
```

Hãy kiểm tra khả năng mapping scalar của phiên bản Spring Data JDBC đang dùng. Với aggregate query luôn trả một hàng như COUNT, kiểu primitive có thể phù hợp nếu database luôn trả giá trị không null.

## 13. Chẩn đoán khi query trả nhiều hàng ngoài dự kiến

Khi gặp `IncorrectResultSizeDataAccessException`, đừng chỉ tăng kiểu trả về thành List ngay lập tức. Trước hết xác định nguyên nhân:

1. Ghi nhận repository method và query SQL thực tế.
2. Xác nhận điều kiện lọc có bao gồm đủ khóa nghiệp vụ không.
3. Chạy query trực tiếp để đếm số hàng khớp.
4. Kiểm tra join có nhân bản hàng root không.
5. Kiểm tra dữ liệu trùng theo key dự kiến duy nhất.
6. Kiểm tra tenant, soft-delete hoặc trạng thái có bị bỏ sót không.
7. Xác định nhiều hàng là lỗi dữ liệu hay một use case hợp lệ.
8. Chọn sửa query, thêm unique constraint hoặc đổi return type.

Truy vấn chẩn đoán:

```sql
SELECT order_number, COUNT(*) AS row_count
FROM purchase_order
GROUP BY order_number
HAVING COUNT(*) > 1;
```

Với tenant-aware key:

```sql
SELECT tenant_id, external_code, COUNT(*) AS row_count
FROM customer
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

Nếu query repository có thêm điều kiện status/tenant, tái tạo đúng predicate để tìm chính xác các hàng gây lỗi.

## 14. Kiểm thử trường hợp 0, 1 và nhiều kết quả

Test nên xác nhận cả ba cardinality. Ví dụ repository:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findAllByRegion(String region);

    Optional<Customer> findFirstByRegionOrderByCreatedAtDescIdDesc(
            String region
    );
}
```

### 14.1. Không có kết quả

```java
@Test
void returnsEmptyWhenEmailDoesNotExist() {
    assertThat(repository.findByEmail("missing@example.com"))
            .isEmpty();
}
```

### 14.2. Một kết quả

```java
@Test
void returnsCustomerWhenEmailMatchesOneRow() {
    repository.save(new Customer(null, "alex@example.com", "NORTH"));

    Optional<Customer> result =
            repository.findByEmail("alex@example.com");

    assertThat(result).isPresent();
    assertThat(result.orElseThrow().email())
            .isEqualTo("alex@example.com");
}
```

### 14.3. Nhiều kết quả với return type đơn

Nếu schema test không có unique constraint trên email, có thể tạo hai hàng trùng để xác nhận repository báo lỗi:

```java
@Test
void throwsWhenSingleResultQueryMatchesMultipleRows() {
    repository.save(new Customer(null, "duplicate@example.com", "NORTH"));
    repository.save(new Customer(null, "duplicate@example.com", "SOUTH"));

    assertThatThrownBy(() ->
            repository.findByEmail("duplicate@example.com")
    ).isInstanceOf(IncorrectResultSizeDataAccessException.class);
}
```

Test này cần schema fixture cho phép duplicate. Nếu production có unique constraint đúng, duplicate insert sẽ thất bại ngay ở database và test uniqueness nên xác nhận constraint đó riêng. Có thể dùng một query khác không có unique invariant để kiểm tra lỗi result size.

### 14.4. Nhiều kết quả hợp lệ với collection

```java
@Test
void returnsAllCustomersInRegion() {
    repository.save(new Customer(null, "a@example.com", "NORTH"));
    repository.save(new Customer(null, "b@example.com", "NORTH"));

    assertThat(repository.findAllByRegion("NORTH"))
            .hasSize(2);
}
```

### 14.5. Chọn một hàng theo thứ tự

```java
@Test
void returnsLatestCustomerForRegion() {
    repository.save(new Customer(
            null, "older@example.com", "NORTH", T0));
    repository.save(new Customer(
            null, "newer@example.com", "NORTH", T1));

    Optional<Customer> result =
            repository.findFirstByRegionOrderByCreatedAtDescIdDesc(
                    "NORTH");

    assertThat(result.orElseThrow().email())
            .isEqualTo("newer@example.com");
}
```

Test nên dùng timestamp khác nhau hoặc kiểm tra tie-breaker ID để chứng minh thứ tự được xác định.

## 15. Database constraint và race condition

Một cách làm không an toàn là kiểm tra trước khi insert:

```java
if (!repository.existsByEmail(email)) {
    repository.save(new Customer(email));
}
```

Hai transaction đồng thời có thể cùng kiểm tra và đều thấy email chưa tồn tại, sau đó cùng insert. Đây là race condition:

```text
Transaction A                 Transaction B
      │                             │
      ├── exists(email)? false      │
      │                             ├── exists(email)? false
      ├── insert(email)             │
      │                             ├── insert(email)
      ▼                             ▼
   Duplicate nếu không có unique constraint
```

Ứng dụng có thể kiểm tra trước để đưa ra thông báo thân thiện, nhưng unique constraint ở database mới là lớp bảo vệ cuối cùng. Khi hai transaction cạnh tranh, một insert thành công; insert còn lại nhận lỗi duplicate key/unique violation.

Xử lý lỗi đó ở service và chuyển thành lỗi nghiệp vụ phù hợp, ví dụ EmailAlreadyRegisteredException. Không dựa vào pre-check làm bảo đảm tính duy nhất.

## 16. Transaction và dữ liệu thay đổi giữa lúc đọc

Một query có thể trả một hàng ở thời điểm đầu, nhưng dữ liệu có thể thay đổi sau đó. Ví dụ service đọc customer theo email rồi thực hiện thao tác khác. Nếu một transaction khác sửa email hoặc tạo duplicate trong schema không có unique constraint, lần đọc sau có thể cho kết quả khác.

Nếu tính duy nhất là invariant, dùng database constraint. Nếu cần đảm bảo một chuỗi thao tác đọc/ghi nhất quán, thiết kế transaction isolation và locking phù hợp. Đổi return type sang Optional không giải quyết race condition hay bảo đảm uniqueness.

Với query “lấy bản ghi mới nhất”, cần xác định sort key ổn định và transaction semantics phù hợp với use case. Nếu dữ liệu có thể thêm mới liên tục, kết quả của hai lần gọi query có thể khác nhau một cách hợp lệ.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| IncorrectResultSizeDataAccessException | Method đơn khớp nhiều hàng | Kiểm tra duplicate, predicate, join và invariant |
| Optional empty dù caller nghĩ dữ liệu tồn tại | Query filter không đủ hoặc dữ liệu đã bị xóa/ẩn | Kiểm tra SQL, tenant/status/soft-delete và fixture |
| NullPointerException sau query | Method entity đơn trả null khi không có hàng | Dùng Optional hoặc kiểm tra null |
| Dùng Optional nhưng vẫn gặp lỗi nhiều hàng | Optional không thêm LIMIT và không khử duplicate | Thêm unique constraint, đổi collection hoặc First/Top đúng nghiệp vụ |
| findFirst trả hàng khác giữa các lần chạy | Không có ORDER BY hoặc sort key không duy nhất | Thêm thứ tự ổn định và tie-breaker |
| Query join trả nhiều hàng cho một root | Quan hệ one-to-many nhân bản result row | Dùng EXISTS, query root riêng hoặc projection phù hợp |
| Duplicate chỉ xuất hiện khi chạy đồng thời | Pre-check không chống race condition | Thêm unique constraint và xử lý unique violation |
| COUNT trả 0 nhưng code coi là không có result row | COUNT aggregate vẫn trả một hàng | Xử lý giá trị 0 như kết quả hợp lệ |
| SUM trả null trên tập rỗng | SQL aggregate không có giá trị đầu vào | Dùng Optional/wrapper hoặc COALESCE |
| Unique constraint không chặn nhiều NULL | Semantics NULL của database | Kết hợp NOT NULL hoặc tùy chọn unique phù hợp |

## 18. Quy trình chọn kiểu trả về

Khi khai báo repository query, có thể dùng quy trình:

1. Query có thể trả nhiều hàng hợp lệ không?
   - Có: dùng List/Collection/Stream phù hợp.
   - Không: tiếp tục.
2. Không tìm thấy có phải trường hợp bình thường không?
   - Có: ưu tiên Optional.
   - Không: dùng Optional và chuyển empty thành lỗi nghiệp vụ ở service, hoặc dùng contract rõ ràng khác.
3. Tính duy nhất có được database bảo vệ không?
   - Có: xác nhận unique constraint/index khớp predicate.
   - Không: nếu phải duy nhất, tạo migration và xử lý dữ liệu trùng.
4. Nhiều hàng có hợp lệ nhưng chỉ cần một hàng ưu tiên không?
   - Có: dùng First/Top hoặc SQL giới hạn với ORDER BY ổn định.
   - Không: trả collection hoặc sửa query/invariant.
5. Query có join khiến root bị lặp không?
   - Có: sửa query/projection hoặc dùng EXISTS/DISTINCT khi semantics phù hợp.
6. Viết test cho 0, 1 và nhiều hàng để xác nhận contract.

## 19. Bài tập thực hành

**Bài 1 — Optional không có kết quả.** Viết findByEmail trả Optional<Customer>. Truy vấn một email không tồn tại và xác nhận Optional.empty().

**Bài 2 — Entity đơn trả null.** Tạo một finder trả Customer trực tiếp. Quan sát trường hợp không tìm thấy và xử lý null; sau đó đổi sang Optional.

**Bài 3 — Nhiều hàng cho Optional.** Tạo hai hàng trùng email trong schema test không có unique constraint. Gọi finder Optional và xác nhận IncorrectResultSizeDataAccessException.

**Bài 4 — Collection.** Đổi finder thành List<Customer>, tạo hai hàng cùng region và xác nhận cả hai được trả về; không có hàng thì danh sách rỗng.

**Bài 5 — First/Top.** Viết findFirstByCustomerIdOrderByCreatedAtDescIdDesc. Tạo nhiều đơn hàng và xác nhận bản ghi mới nhất được chọn ổn định.

**Bài 6 — Unique constraint.** Tìm dữ liệu duplicate, xử lý bằng migration rồi thêm unique constraint. Kiểm thử insert trùng và chuyển lỗi database thành lỗi nghiệp vụ.

**Bài 7 — Composite key.** Tạo unique constraint trên tenant_id và external_code. Viết repository method dùng cả hai cột; so sánh với method chỉ lọc external_code.

**Bài 8 — Join nhân bản hàng.** Viết query join purchase_order và order_line. Tạo order có nhiều line, quan sát số result row và sửa bằng EXISTS hoặc query phù hợp.

**Bài 9 — Aggregate scalar.** So sánh COUNT(*) và SUM() trên tập rỗng. Thử COALESCE và kiểu trả về wrapper/Optional.

**Bài 10 — Race condition.** Tạo hai transaction đồng thời cùng đăng ký một email. Xác nhận unique constraint chỉ cho một transaction thành công.

**Bài 11 — Test cardinality.** Viết test cho ba trường hợp 0, 1 và nhiều kết quả trên repository. Dùng database mục tiêu nếu test phụ thuộc unique/NULL semantics.

### Tài liệu tham khảo

- [Spring Data Commons — Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html): semantics của entity đơn, Optional, collection và các kiểu kết quả.
- [Spring Data JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository query, mapping và persistence trong Spring Data JDBC.
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html): exception abstraction và xử lý lỗi truy cập dữ liệu.
- [Spring Framework — DataAccessUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/support/DataAccessUtils.html): tiện ích xử lý kết quả đơn và nhiều kết quả.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): unique, primary key, foreign key, NOT NULL và semantics của NULL.
- [MySQL — InnoDB Constraints](https://dev.mysql.com/doc/refman/8.4/en/constraints.html): constraint và kiểm soát tính duy nhất trong MySQL.
