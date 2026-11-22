# Truy vấn IN, tập tham số rỗng và giới hạn số tham số

Trong Spring Data Relational R2DBC, điều kiện `IN` thường được dùng khi cần tìm các hàng có khóa hoặc thuộc tính nằm trong một tập giá trị, ví dụ danh sách ID được chọn, các trạng thái được phép hoặc nhóm mã sản phẩm. Spring Data hỗ trợ biểu diễn điều kiện này qua derived query như `findByIdIn(...)`, qua `@Query` và qua `Criteria.in(...)` khi dùng `R2dbcEntityTemplate`.

Điểm cần chú ý là danh sách truyền vào có thể rỗng, chứa `null`, có phần tử trùng lặp hoặc quá lớn. Khi collection được mở rộng thành nhiều bind parameter, số tham số thực tế của câu SQL tăng theo số phần tử. Database và driver có giới hạn riêng về số bind marker, kích thước câu lệnh và số phần tử trong một biểu thức `IN`. Vì vậy, ứng dụng cần xác định ngữ nghĩa của tập rỗng, chuẩn hóa dữ liệu đầu vào và chọn chiến lược phù hợp khi danh sách lớn.

## 1. Ý nghĩa của điều kiện IN

`IN` kiểm tra một giá trị có thuộc một tập giá trị hay không. Ví dụ SQL:

```sql
SELECT id, name, status
FROM product
WHERE status IN ('ACTIVE', 'PENDING');
```

Kết quả gồm các sản phẩm có `status` là `ACTIVE` hoặc `PENDING`. Về logic, điều kiện này tương đương nhiều phép so sánh bằng nối bằng OR:

```sql
WHERE status = 'ACTIVE' OR status = 'PENDING'
```

`NOT IN` biểu diễn điều kiện ngược lại: giá trị không thuộc tập được liệt kê.

```sql
SELECT id, name, status
FROM product
WHERE status NOT IN ('DELETED', 'ARCHIVED');
```

Điều kiện `IN` rất phù hợp với tập ID hoặc mã đã được ứng dụng thu thập. Tuy nhiên, cần hiểu cách Spring Data chuyển collection thành tham số SQL và cách SQL xử lý tập rỗng, `NULL`.

## 2. Derived query với In và NotIn

Spring Data R2DBC hỗ trợ từ khóa `In` và `NotIn` trong tên phương thức repository. Ví dụ:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByIdIn(Collection<Long> ids);

    Flux<Product> findByStatusIn(Collection<String> statuses);

    Flux<Product> findByStatusNotIn(Collection<String> excludedStatuses);
}
```

Các phương thức trên có ý nghĩa:

- `findByIdIn(ids)`: lấy các sản phẩm có ID thuộc collection `ids`.
- `findByStatusIn(statuses)`: lấy các sản phẩm có trạng thái thuộc collection `statuses`.
- `findByStatusNotIn(excludedStatuses)`: lấy các sản phẩm có trạng thái không thuộc tập loại trừ.

Spring Data tạo truy vấn và bind các giá trị theo cơ chế của R2DBC. Không cần nối từng ID vào chuỗi SQL. Collection có thể được biểu diễn bằng `Collection`, mảng hoặc varargs tùy chữ ký và khả năng parser của phiên bản Spring Data.

Ví dụ sử dụng:

```java
Flux<Product> findSelectedProducts(Collection<Long> selectedIds) {
    return productRepository.findByIdIn(selectedIds);
}
```

Đối với danh sách ID lấy từ request, nên xác thực collection trước khi gọi repository. Không để một collection bất thường hoặc quá lớn được chuyển thẳng xuống database.

## 3. Dùng IN trong @Query

Với truy vấn khai báo, có thể đặt named parameter trong biểu thức `IN`:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    @Query("""
        SELECT id, name, status
        FROM product
        WHERE id IN (:ids)
        ORDER BY id
        """)
    Flux<Product> findProductsByIds(@Param("ids") Collection<Long> ids);
}
```

Trong các API Spring hỗ trợ named parameter expansion, collection được mở rộng thành các bind marker phù hợp với số phần tử. Ví dụ, collection có ba ID có thể tạo ra SQL có dạng khái niệm:

```sql
WHERE id IN ($1, $2, $3)
```

Tên marker thực tế phụ thuộc driver. Đây là minh họa về việc mở rộng collection, không phải chuỗi SQL mà ứng dụng cần tự tạo.

Khả năng mở rộng collection và cú pháp cụ thể phụ thuộc API Spring Data/DatabaseClient và phiên bản đang sử dụng. Hãy kiểm tra tài liệu phiên bản dự án và chạy integration test trên driver thực tế. Không giả định rằng có thể bind một `List` như một giá trị scalar vào mọi API R2DBC.

## 4. Dùng Criteria.in với R2dbcEntityTemplate

Khi điều kiện được tạo động, `Criteria.in(...)` là cách biểu diễn tập giá trị:

```java
Criteria criteria = Criteria.where("id").in(ids);
Query query = Query.query(criteria);

Flux<Product> products = template.select(query, Product.class);
```

Có thể kết hợp với các điều kiện khác:

```java
Criteria criteria = Criteria.where("id").in(ids)
    .and("status").is("ACTIVE");

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Order.asc("id")))
    .limit(100);

Flux<Product> products = template.select(query, Product.class);
```

Ví dụ này lấy các sản phẩm có ID thuộc tập đã cho, đồng thời có trạng thái `ACTIVE`, sắp xếp theo ID và giới hạn tối đa 100 hàng.

`Criteria.in(...)` vẫn cần xử lý trường hợp collection rỗng và `null` trước khi tạo query. Không nên để một request không có ID vô tình biến thành truy vấn không có điều kiện.

## 5. Tập rỗng: vấn đề quan trọng nhất

Một collection có thể rỗng vì client không chọn mục nào, kết quả của bước lọc trước không có phần tử hoặc dữ liệu đầu vào bị thiếu.

Ví dụ:

```java
List<Long> ids = List.of();
```

Về logic tập hợp:

- `x IN empty-set` luôn sai: không có giá trị nào thuộc tập rỗng.
- `x NOT IN empty-set` luôn đúng: mọi giá trị đều không thuộc tập rỗng.

Tuy nhiên, không nên dựa vào việc database chấp nhận cú pháp `IN ()` hoặc `NOT IN ()`. Nhiều dialect không cho phép danh sách rỗng trong ngoặc; cách Spring mở rộng collection rỗng cũng có thể khác theo API và phiên bản. Nếu để câu lệnh được tạo thành `IN ()`, truy vấn có thể lỗi cú pháp.

**Ứng dụng cần định nghĩa rõ ý nghĩa của collection rỗng trước khi gọi repository.**

### 5.1. IN rỗng thường có nghĩa là không có kết quả

Nếu người dùng yêu cầu tìm các ID trong một danh sách nhưng danh sách không có ID, kết quả hợp lý thường là rỗng:

```java
Flux<Product> findSelectedProducts(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return Flux.empty();
    }

    return productRepository.findByIdIn(ids);
}
```

Cách này có các lợi ích:

- Không phát sinh SQL không cần thiết.
- Không phụ thuộc cách dialect xử lý `IN ()`.
- Không có nguy cơ vô tình bỏ điều kiện lọc và trả về toàn bộ bảng.
- Hợp đồng service thể hiện rõ rằng không chọn ID nào thì không có sản phẩm nào được trả về.

### 5.2. IN rỗng có thể có nghĩa là bỏ qua filter

Một số API tìm kiếm định nghĩa collection rỗng là “không lọc theo trường này”. Ví dụ người dùng không chọn trạng thái nào nghĩa là tìm mọi trạng thái. Trong trường hợp đó, service nên bỏ predicate và chạy truy vấn theo các điều kiện còn lại:

```java
Flux<Product> search(Collection<String> statuses, String category) {
    if (statuses == null || statuses.isEmpty()) {
        return productRepository.findByCategory(category);
    }

    return productRepository.findByStatusInAndCategory(statuses, category);
}
```

Đây là quy tắc nghiệp vụ của API, không phải ý nghĩa tự động của SQL `IN`. Hãy ghi rõ trong hợp đồng API rằng danh sách không gửi, danh sách rỗng và danh sách có phần tử được diễn giải như thế nào.

### 5.3. Phân biệt null collection và empty collection

Hai trạng thái có thể mang ý nghĩa khác nhau:

| Đầu vào | Ý nghĩa có thể chọn | Cách xử lý ví dụ |
|---|---|---|
| `null` | Client không cung cấp filter | Bỏ qua điều kiện |
| Collection rỗng | Client đã cung cấp filter nhưng không chọn giá trị nào | Trả kết quả rỗng |
| Collection có phần tử | Lọc theo các giá trị đã chọn | Thực hiện `IN` |

Một API khác có thể chọn quy ước khác, nhưng phải nhất quán giữa controller, service và repository. Đừng dùng một nhánh `if (ids == null || ids.isEmpty())` nếu nghiệp vụ cần phân biệt hai trường hợp.

## 6. Tập rỗng với NOT IN

`NOT IN` cần được xử lý theo ý nghĩa nghiệp vụ riêng. Theo logic tập hợp, `x NOT IN empty-set` là đúng với mọi giá trị `x`. Nếu danh sách loại trừ rỗng có nghĩa “không loại trừ gì”, ứng dụng có thể bỏ điều kiện `NOT IN`:

```java
Flux<Product> findNotExcluded(Collection<Long> excludedIds) {
    if (excludedIds == null || excludedIds.isEmpty()) {
        return productRepository.findAll();
    }

    return productRepository.findByIdNotIn(excludedIds);
}
```

Ví dụ này chỉ phù hợp khi nghiệp vụ thực sự cho phép lấy mọi sản phẩm khi không có ID bị loại trừ. Với dữ liệu lớn, vẫn cần phân trang hoặc giới hạn kết quả; không nên dùng `findAll()` trên bảng lớn chỉ vì collection rỗng.

Nếu collection rỗng có nghĩa request không hợp lệ, hãy trả lỗi validation thay vì tự suy diễn.

## 7. NULL trong collection và logic ba giá trị của SQL

SQL sử dụng logic ba giá trị: một biểu thức có thể là TRUE, FALSE hoặc UNKNOWN. So sánh với `NULL` thường tạo kết quả UNKNOWN, không phải TRUE hoặc FALSE.

Ví dụ:

```sql
WHERE status IN ('ACTIVE', NULL)
```

Nếu `status = 'ACTIVE'`, điều kiện là TRUE. Nếu `status = 'PENDING'`, không có giá trị khớp nhưng có phần tử NULL trong danh sách, kết quả có thể là UNKNOWN. Nếu `status` của hàng là NULL, phép so sánh cũng không trở thành TRUE. Trong mệnh đề `WHERE`, chỉ hàng có điều kiện TRUE mới được giữ lại.

### 7.1. Vì sao NOT IN có NULL rất nguy hiểm?

Xét:

```sql
WHERE id NOT IN (10, 20, NULL)
```

Với một ID khác 10 và 20, database phải xác định ID đó có khác cả 10, 20 và NULL hay không. So sánh với NULL là UNKNOWN, vì vậy toàn bộ biểu thức có thể trở thành UNKNOWN. Kết quả thường là không hàng nào được chọn, kể cả những ID tưởng như không thuộc danh sách loại trừ.

Do đó, không nên truyền collection chứa `null` vào `NOT IN`.

### 7.2. Chuẩn hóa và loại bỏ null trước khi truy vấn

Nếu null không có ý nghĩa hợp lệ trong tập ID, hãy lọc bỏ hoặc từ chối đầu vào:

```java
List<Long> normalizedIds = ids.stream()
    .filter(Objects::nonNull)
    .distinct()
    .toList();
```

Với API yêu cầu dữ liệu nghiêm ngặt, từ chối collection chứa null thường tốt hơn âm thầm loại bỏ:

```java
if (ids.stream().anyMatch(Objects::isNull)) {
    return Flux.error(new IllegalArgumentException(
        "Danh sách ID không được chứa null"));
}
```

Việc lựa chọn từ chối hay chuẩn hóa phụ thuộc hợp đồng API. Quan trọng là không để SQL three-valued logic tạo kết quả bất ngờ.

### 7.3. Nếu cần bao gồm các hàng có cột NULL

`IN` không tự bao gồm các hàng có giá trị cột là SQL NULL. Nếu nghiệp vụ muốn lấy các hàng có trạng thái thuộc tập hoặc trạng thái chưa được gán, hãy viết hai nhánh rõ ràng:

```sql
WHERE status IN ('ACTIVE', 'PENDING')
   OR status IS NULL
```

Với `NOT IN`, nếu muốn lấy các giá trị không nằm trong danh sách và cả hàng NULL, có thể dùng:

```sql
WHERE (status NOT IN ('DELETED', 'ARCHIVED') OR status IS NULL)
```

Nếu không muốn lấy hàng NULL, biểu diễn rõ điều kiện:

```sql
WHERE status IS NOT NULL
  AND status NOT IN ('DELETED', 'ARCHIVED')
```

Hãy chọn biểu thức theo nghiệp vụ, không dựa vào giả định rằng `NOT IN` luôn bao gồm các giá trị null.

## 8. Loại bỏ phần tử trùng lặp

Một collection có thể chứa ID trùng nhau:

```java
List<Long> ids = List.of(10L, 20L, 10L, 30L, 20L);
```

Với phép `IN`, trùng lặp thường không làm thay đổi tập hàng kết quả. Tuy nhiên, chúng vẫn có thể làm tăng số bind parameter, kích thước SQL và chi phí parse câu lệnh. Vì vậy, nên chuẩn hóa bằng `distinct()` nếu thứ tự và tính duy nhất của tập không mang ý nghĩa khác:

```java
List<Long> uniqueIds = ids.stream()
    .filter(Objects::nonNull)
    .distinct()
    .toList();
```

Với collection lớn, việc deduplicate cũng có chi phí bộ nhớ. Hãy cân nhắc dùng `Set` từ đầu nếu hợp đồng dữ liệu là một tập duy nhất và kích thước phù hợp.

## 9. Giới hạn số bind parameter

Khi Spring mở rộng một collection thành các bind marker, mỗi phần tử thường tạo thêm một tham số trong câu SQL. Một truy vấn có nhiều điều kiện có thể dùng nhiều tham số hơn số phần tử của collection.

Ví dụ:

```sql
SELECT id, name
FROM product
WHERE tenant_id = ?
  AND status = ?
  AND id IN (?, ?, ?, ...);
```

Nếu có 2 tham số cố định và 5.000 ID, tổng số bind parameter có thể là 5.002. Nếu truy vấn còn có điều kiện thời gian, phân quyền hoặc các tập `IN` khác, số lượng tiếp tục tăng.

Database, giao thức và driver có thể giới hạn:

- Số bind parameter tối đa trong một prepared statement.
- Số phần tử trong một biểu thức `IN`.
- Độ dài câu SQL hoặc kích thước packet/request.
- Số lượng biểu thức hoặc tài nguyên parse trong một câu lệnh.

Các giới hạn này không giống nhau giữa các hệ quản trị và có thể thay đổi theo phiên bản, cấu hình hoặc driver. Ví dụ, SQL Server có giới hạn số parameter cho một stored procedure/batch; Oracle có giới hạn số biểu thức trong một danh sách `IN` ở nhiều phiên bản; SQLite có giới hạn biến host parameter phụ thuộc phiên bản và cấu hình. Không nên lấy một con số chung để áp dụng cho mọi database.

Hãy kiểm tra tài liệu chính thức của database, R2DBC driver và giao thức mà ứng dụng triển khai. Sau đó đặt một giới hạn ứng dụng thấp hơn giới hạn tối đa thực tế để dành chỗ cho các tham số cố định khác và tránh câu lệnh quá lớn.

## 10. Tính số tham số thực tế

Giả sử truy vấn có:

- 1 tham số `tenantId`.
- 1 tham số `status`.
- 1 tham số `createdAfter`.
- Một collection gồm `n` ID.

Nếu collection được mở rộng thành một marker cho mỗi ID, tổng số bind parameter là:

\[
P = 3 + n
\]

Nếu có thêm một collection gồm `m` category ID:

\[
P = 3 + n + m
\]

Đây là cách ước lượng khi mỗi phần tử được bind riêng. Driver có thể hỗ trợ array parameter hoặc kiểu dữ liệu đặc thù để biểu diễn cả tập bằng một tham số, nhưng đó là khả năng riêng của driver/database chứ không phải hành vi mặc định của mọi API `IN`.

Khi thiết kế giới hạn, đừng chỉ kiểm tra số ID. Hãy tính cả tham số cố định và mọi collection được mở rộng trong câu lệnh.

## 11. Giới hạn kích thước đầu vào ở service

Một endpoint không nên chấp nhận một collection không giới hạn. Có thể áp dụng giới hạn tối đa:

```java
private static final int MAX_IDS = 500;

Flux<Product> findProducts(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return Flux.empty();
    }

    if (ids.size() > MAX_IDS) {
        return Flux.error(new IllegalArgumentException(
            "Chỉ được truy vấn tối đa " + MAX_IDS + " ID mỗi lần"));
    }

    if (ids.stream().anyMatch(Objects::isNull)) {
        return Flux.error(new IllegalArgumentException(
            "Danh sách ID không được chứa null"));
    }

    List<Long> uniqueIds = ids.stream().distinct().toList();
    return productRepository.findByIdIn(uniqueIds);
}
```

Giá trị `500` chỉ là ví dụ. Giới hạn thực tế cần dựa trên:

- Giới hạn parameter của database và driver.
- Số tham số cố định của truy vấn.
- Kích thước SQL sau khi mở rộng collection.
- Độ trễ và execution plan.
- Số request đồng thời.
- Bộ nhớ và chi phí xử lý kết quả.

Nếu API cần xử lý nhiều ID hơn, hãy thiết kế batch hoặc cơ chế truyền tập dữ liệu chuyên dụng thay vì tăng giới hạn một cách tùy tiện.

## 12. Chia collection lớn thành nhiều batch

Khi danh sách vượt giới hạn hợp lý của một truy vấn, có thể chia thành các batch nhỏ. Ví dụ mỗi batch chứa tối đa 500 ID:

```java
Flux<Product> findInBatches(List<Long> ids) {
    int batchSize = 500;

    return Flux.fromIterable(ids)
        .buffer(batchSize)
        .concatMap(productRepository::findByIdIn);
}
```

`buffer(batchSize)` tạo từng nhóm ID. `concatMap` thực hiện truy vấn tuần tự, tránh tạo quá nhiều truy vấn đồng thời và giữ thứ tự xử lý theo batch.

Nếu database và pool có đủ khả năng, có thể dùng concurrency hữu hạn:

```java
Flux<Product> findInBatches(List<Long> ids) {
    int batchSize = 500;
    int concurrency = 4;

    return Flux.fromIterable(ids)
        .buffer(batchSize)
        .flatMap(productRepository::findByIdIn, concurrency);
}
```

Concurrency bằng 4 có nghĩa tối đa bốn truy vấn batch được xử lý đồng thời trong phần `flatMap` này. Hãy cân đối với pool size, tải database và các request khác trong ứng dụng. Tăng concurrency có thể tăng throughput nhưng cũng có thể gây tranh chấp connection và CPU.

### 12.1. Kết quả batch không nhất thiết theo thứ tự ID đầu vào

SQL `IN` không bảo đảm thứ tự kết quả giống thứ tự các giá trị trong collection. Ngay cả khi các batch được xử lý tuần tự, database vẫn có thể trả hàng theo thứ tự execution plan.

Nếu cần thứ tự xác định, hãy:

- Thêm `ORDER BY` phù hợp trong truy vấn.
- Hoặc giữ map vị trí của ID đầu vào rồi sắp xếp kết quả ở ứng dụng.
- Xử lý các ID không tồn tại theo quy tắc rõ ràng.

Nếu dùng `flatMap`, thứ tự giữa các batch cũng không được bảo đảm. Dùng `concatMap` khi cần phát kết quả theo thứ tự batch hoặc dùng bước sắp xếp cuối khi tập kết quả đã được giới hạn.

### 12.2. Batch query không tự bảo đảm một snapshot dữ liệu

Nhiều batch là nhiều câu SQL riêng. Nếu dữ liệu thay đổi trong khi xử lý, các batch có thể quan sát trạng thái database ở những thời điểm khác nhau. Nếu nghiệp vụ cần một snapshot nhất quán, hãy xác định isolation level và transaction phù hợp. Một transaction dài qua nhiều batch có thể giữ connection lâu và gây áp lực khóa; cần cân nhắc trade-off giữa nhất quán và tài nguyên.

### 12.3. Loại bỏ ID trùng trước khi chia batch

Nếu cùng một ID xuất hiện trong nhiều batch, cùng một hàng có thể được phát ra nhiều lần. Hãy deduplicate trước khi chia lô nếu kết quả cần là tập duy nhất:

```java
List<Long> uniqueIds = ids.stream()
    .filter(Objects::nonNull)
    .distinct()
    .toList();

return Flux.fromIterable(uniqueIds)
    .buffer(500)
    .concatMap(productRepository::findByIdIn);
```

## 13. Khi nào không nên chia batch ở ứng dụng?

Chia batch là một giải pháp thực tế nhưng không phải lúc nào cũng tối ưu. Mỗi batch tạo thêm một round trip và một câu lệnh SQL. Với danh sách rất lớn, hàng trăm hoặc hàng nghìn batch có thể làm tăng latency và tải database.

Các lựa chọn khác tùy hệ quản trị:

### 13.1. Dùng bảng tạm hoặc bảng staging

Nếu tập ID rất lớn và được sử dụng trong nhiều truy vấn, có thể đưa ID vào bảng tạm hoặc bảng staging rồi join:

```sql
SELECT p.id, p.name
FROM product p
JOIN requested_ids r ON r.id = p.id;
```

Ưu điểm:

- Không cần tạo hàng nghìn bind marker trong một câu `IN`.
- Database có thể tối ưu join theo index và thống kê.
- Có thể tái sử dụng tập ID trong nhiều truy vấn trong cùng một workflow.

Điểm cần cân nhắc:

- Cách tạo/populate bảng staging phụ thuộc database.
- Bảng tạm có vòng đời gắn với session hoặc transaction tùy hệ quản trị.
- Cần bảo đảm các thao tác dùng đúng connection/session.
- Cần cleanup dữ liệu staging và tránh xung đột giữa các request.

### 13.2. Dùng array parameter hoặc tính năng đặc thù driver

Một số database hỗ trợ truyền cả mảng như một tham số và dùng toán tử hoặc hàm riêng. Ví dụ PostgreSQL có thể dùng `= ANY(array)` với kiểu array phù hợp:

```sql
SELECT id, name
FROM product
WHERE id = ANY(:ids);
```

Đây là ví dụ theo PostgreSQL; cách bind array bằng R2DBC phụ thuộc driver và kiểu phần tử. Không thể giả định `Collection<Long>` sẽ tự động trở thành SQL array trong mọi API. Cần dùng kiểu Java và API bind array mà driver PostgreSQL hỗ trợ.

SQL Server có table-valued parameters; một số database khác có collection/table types hoặc cơ chế tương đương. Các tính năng này không portable và cần cấu hình riêng.

### 13.3. Dùng join thay cho danh sách IN

Nếu các giá trị đầu vào vốn tồn tại trong một bảng quan hệ, truy vấn bằng join thường tự nhiên hơn việc tải danh sách ID về ứng dụng rồi gửi lại:

```sql
SELECT p.id, p.name
FROM product p
JOIN category_product cp ON cp.product_id = p.id
WHERE cp.category_id = :categoryId;
```

Join giữ việc lọc dữ liệu ở database và tránh tạo một collection lớn trong application heap. Cần có index phù hợp trên các khóa join.

## 14. IN và NOT IN với dữ liệu nullable

Ngoài `null` trong collection, cần xem xét cột được lọc có thể chứa SQL NULL hay không.

Ví dụ:

```sql
SELECT id
FROM customer
WHERE external_code IN ('A', 'B');
```

Hàng có `external_code IS NULL` không được trả về. Nếu nghiệp vụ cần cả hàng null, thêm nhánh `OR external_code IS NULL`.

Với `NOT IN`, cột null cũng không thỏa điều kiện vì phép so sánh tạo UNKNOWN. Nếu muốn loại trừ một số mã nhưng vẫn lấy hàng chưa có mã, phải viết rõ:

```sql
WHERE external_code NOT IN ('A', 'B')
   OR external_code IS NULL
```

Nếu muốn chỉ lấy các mã đã có giá trị và không thuộc tập loại trừ:

```sql
WHERE external_code IS NOT NULL
  AND external_code NOT IN ('A', 'B')
```

Đây là ngữ nghĩa SQL phổ quát của NULL trong điều kiện so sánh. Hãy viết test cho cả cột null và phần tử null trong collection để tránh lỗi nghiệp vụ khó phát hiện.

## 15. Kiểm soát hiệu năng và index

`IN` không tự động chậm hoặc nhanh. Hiệu năng phụ thuộc số phần tử, phân bố dữ liệu, index, thống kê và cách database lập execution plan.

Các điểm cần xem xét:

- Cột được dùng trong `IN` có index phù hợp không?
- Collection có chứa quá nhiều phần tử hoặc nhiều phần tử trùng không?
- Tập giá trị có chọn lọc tốt không, hay gần như bao phủ toàn bộ bảng?
- Có thể dùng join hoặc bảng staging thay cho `IN` không?
- Câu truy vấn còn bao nhiêu tham số cố định khác?
- Số request đồng thời có làm tăng tải database đáng kể không?
- Có cần trả tất cả cột hay chỉ cần projection nhỏ?

Với tập ID rất nhỏ, index trên khóa thường giúp database tìm hàng hiệu quả. Với tập chiếm phần lớn bảng, database có thể chọn scan vì đó là phương án rẻ hơn. Không nên bắt buộc database dùng index mà không xem execution plan và số liệu thực tế.

## 16. Kiểm thử truy vấn IN và giới hạn tham số

Kiểm thử cần bao gồm ngữ nghĩa đầu vào, SQL thực tế và hành vi ở gần giới hạn.

Các tình huống quan trọng:

- Collection có một phần tử.
- Collection có nhiều phần tử.
- Collection rỗng.
- Collection null.
- Collection chứa phần tử null.
- Collection có ID trùng lặp.
- `NOT IN` với giá trị null và tập loại trừ rỗng.
- Cột database chứa SQL NULL.
- Collection có kích thước ở dưới, bằng và trên giới hạn ứng dụng.
- Tổng bind parameter khi truy vấn còn nhiều điều kiện khác.
- Hành vi khi chia batch và thứ tự kết quả.
- Database timeout hoặc từ chối câu lệnh quá lớn.

Ví dụ kiểm thử service với `StepVerifier`:

```java
StepVerifier.create(productService.findSelectedProducts(List.of()))
    .verifyComplete();
```

Test này xác nhận tập rỗng được xử lý thành publisher rỗng theo hợp đồng ví dụ, không phát sinh truy vấn repository.

Kiểm thử collection có dữ liệu:

```java
StepVerifier.create(
        productService.findSelectedProducts(List.of(10L, 20L))
    )
    .expectNextCount(2)
    .verifyComplete();
```

Ví dụ giả định database có đúng hai hàng tương ứng. Integration test cần tạo dữ liệu rõ ràng, bao gồm ID không tồn tại và ID trùng nếu service có deduplicate.

Đối với giới hạn parameter, nên có integration test ở kích thước gần maximum đã chọn trên đúng database/driver. Không cần chạy sát giới hạn tối đa của hệ quản trị trong mọi test; điều quan trọng là xác nhận giới hạn ứng dụng có khoảng an toàn và lỗi vượt giới hạn được trả về rõ ràng.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi `findByIdIn(emptyList)` mà không xác định semantics | Có thể lỗi `IN ()` hoặc hành vi phụ thuộc phiên bản | Xử lý collection rỗng ở service |
| Xem null collection và empty collection là một | Không thể phân biệt bỏ filter với không có kết quả | Định nghĩa hợp đồng API rõ ràng |
| Truyền phần tử null vào `NOT IN` | SQL UNKNOWN có thể khiến không hàng nào được trả về | Từ chối hoặc lọc null trước khi query |
| Không loại phần tử trùng lặp | Tăng bind parameter và kích thước SQL | Deduplicate nếu phù hợp |
| Gửi collection rất lớn trong một câu lệnh | Vượt giới hạn driver/database hoặc query quá nặng | Đặt maximum và chia batch/đổi chiến lược |
| Chỉ tính số phần tử IN, bỏ qua parameter khác | Tổng bind marker vượt giới hạn | Tính cả tham số cố định và collection khác |
| Giả định Collection luôn là một bind value | Driver có thể không hỗ trợ bind List như scalar | Dùng collection expansion được Spring hỗ trợ hoặc API array đặc thù |
| Dùng batch `flatMap` không giới hạn | Tạo quá nhiều truy vấn đồng thời | Đặt concurrency hoặc dùng `concatMap` |
| Giả định IN giữ thứ tự input | Kết quả có thứ tự không xác định | Dùng `ORDER BY` hoặc sắp xếp theo vị trí input |
| Chia batch nhưng không deduplicate | Có thể phát cùng hàng nhiều lần | Chuẩn hóa ID trước khi chia lô |
| Dùng IN thay cho join dữ liệu đã có trong bảng | Tốn round trip và truyền tập ID lớn | Đưa điều kiện vào SQL join |
| Không kiểm thử trên driver thực tế | Khác biệt expansion, array và giới hạn chỉ xuất hiện lúc chạy | Integration test theo database mục tiêu |

## 18. Quy trình xử lý collection trước khi truy vấn

Một service nhận danh sách ID có thể thực hiện các bước sau:

1. Xác định collection bị bỏ qua, rỗng hay có phần tử theo hợp đồng API.
2. Từ chối hoặc loại bỏ `null` theo quy tắc nghiệp vụ.
3. Loại phần tử trùng nếu tập giá trị không cần giữ duplicates.
4. Kiểm tra kích thước tối đa và tổng bind parameter dự kiến.
5. Nếu collection rỗng, trả rỗng, bỏ filter hoặc trả lỗi theo semantics đã chọn.
6. Nếu collection nằm trong giới hạn, thực hiện một truy vấn `IN`.
7. Nếu collection quá lớn, chia batch có giới hạn hoặc dùng bảng staging/array/join phù hợp database.
8. Xác định thứ tự kết quả, xử lý ID không tồn tại và tính nhất quán giữa các batch.
9. Theo dõi query latency, lỗi parameter limit và số batch trong production.

## 19. Nguyên tắc cần nhớ

- Dùng `In`/`NotIn` trong derived query, `IN (:values)` trong `@Query` hoặc `Criteria.in(...)` trong template khi cần lọc theo tập.
- Kiểm tra cách collection được mở rộng và bind trong phiên bản Spring Data/driver cụ thể.
- Định nghĩa rõ semantics cho null collection và collection rỗng; không dựa vào `IN ()`.
- Theo logic tập hợp, `IN` với tập rỗng không có kết quả và `NOT IN` với tập rỗng không loại trừ giá trị nào; triển khai bằng nhánh ứng dụng rõ ràng.
- Không truyền phần tử null vào `NOT IN`; hiểu SQL three-valued logic và điều kiện `IS NULL`.
- Deduplicate và chuẩn hóa collection khi phù hợp.
- Tính tổng bind parameter sau khi mở rộng mọi collection, kể cả các tham số cố định.
- Đặt maximum ở API/service dựa trên giới hạn thực tế của database, driver và workload.
- Chia batch với concurrency hữu hạn khi cần; cân nhắc thứ tự và snapshot giữa các batch.
- Dùng array parameter, bảng staging hoặc join khi tập quá lớn và database hỗ trợ.
- Kiểm thử collection rỗng, null, trùng lặp và kích thước lớn trên database/driver mục tiêu.

Truy vấn `IN` là cách tự nhiên để lọc dữ liệu theo một tập giá trị, nhưng collection đầu vào phải được xử lý như một phần của hợp đồng truy vấn. Khi ứng dụng quy định rõ semantics cho tập rỗng và null, loại bỏ dữ liệu trùng, kiểm soát tổng bind parameter và chuyển sang batch hoặc cơ chế truyền tập dữ liệu phù hợp khi cần, truy vấn sẽ ổn định hơn và tránh lỗi chỉ xuất hiện khi dữ liệu tăng trong production.
