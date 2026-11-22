# Phân trang offset và chi phí khi vị trí bắt đầu lớn

Phân trang offset là cách chia kết quả truy vấn thành các đoạn có kích thước cố định bằng hai thành phần: số hàng cần lấy (`LIMIT`) và số hàng cần bỏ qua trước khi lấy (`OFFSET`). Đây là cách phổ biến để xây dựng danh sách có số trang, nút chuyển trang trước/sau hoặc cho phép người dùng nhảy tới một trang cụ thể.

Trong Spring Data Relational R2DBC, có thể biểu diễn phân trang bằng `Pageable` ở các query method được phiên bản hỗ trợ, bằng `R2dbcEntityTemplate`, hoặc viết trực tiếp `LIMIT`/`OFFSET` qua `DatabaseClient`. Điểm cần chú ý là offset càng lớn thường khiến database phải xử lý và bỏ qua nhiều hàng trước khi trả phần dữ liệu cần thiết. R2DBC giúp ứng dụng tiêu thụ kết quả theo kiểu reactive, nhưng không loại bỏ chi phí tìm và bỏ qua hàng ở phía database.

Khi dữ liệu còn nhỏ, offset pagination thường đơn giản và đủ nhanh. Khi bảng tăng lên hàng triệu hàng, người dùng thường xuyên mở các trang sâu hoặc truy vấn có join/sort nặng, cần hiểu chi phí của offset và cân nhắc keyset (seek) pagination.

## 1. LIMIT và OFFSET hoạt động như thế nào?

Giả sử cần lấy danh sách customer, mỗi trang có 20 hàng. Trang đầu bắt đầu từ offset 0; trang thứ hai bắt đầu từ offset 20; trang thứ ba bắt đầu từ offset 40.

```sql
SELECT id, name, email
FROM customer
ORDER BY id
LIMIT 20 OFFSET 0;
```

Truy vấn trên lấy tối đa 20 hàng sau khi sắp xếp. Trang thứ ba:

```sql
SELECT id, name, email
FROM customer
ORDER BY id
LIMIT 20 OFFSET 40;
```

Database bỏ qua 40 hàng đầu theo thứ tự đã xác định rồi trả tối đa 20 hàng tiếp theo.

Hai tham số có ý nghĩa:

| Thành phần | Ý nghĩa |
| --- | --- |
| `LIMIT n` | Số hàng tối đa muốn nhận |
| `OFFSET m` | Số hàng đứng trước cần bỏ qua |

Offset bắt đầu từ 0, không phải 1. Nếu người dùng chọn trang có số thứ tự bắt đầu từ 1, công thức thông dụng là:

\[
\text{offset} = (\text{pageNumber} - 1) \times \text{pageSize}
\]

Ví dụ `pageNumber = 4`, `pageSize = 25` thì offset bằng 75. Trong API Java dùng `PageRequest.of(3, 25)` vì chỉ số trang của `PageRequest` bắt đầu từ 0.

## 2. Tính toán offset trong Java

Một API thường nhận page number và page size từ request. Cần xác thực hai giá trị này trước khi đưa vào query:

```java
public record PageRequestInput(int page, int size) {
}

private static PageRequestInput validatePage(int page, int size) {
    if (page < 0) {
        throw new IllegalArgumentException("page phải >= 0");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("size phải nằm trong khoảng 1..100");
    }
    return new PageRequestInput(page, size);
}
```

Khi tính offset thủ công, dùng số nguyên đủ rộng và tránh tràn số:

```java
long offset = Math.multiplyExact((long) page, size);
```

`Math.multiplyExact` ném lỗi nếu phép nhân vượt giới hạn `long`, thay vì âm thầm tạo offset sai. Nếu dùng `Pageable`, `getOffset()` trả về `long`, còn page size thường là `int`.

Không nên cho client gửi một `size` tùy ý rất lớn. Page size lớn làm tăng số hàng database phải đọc, dữ liệu truyền qua mạng, bộ nhớ và thời gian serialize response. Nên đặt giới hạn tối đa phù hợp với màn hình và tải hệ thống.

## 3. OFFSET cần một thứ tự xác định

Phân trang phải có `ORDER BY`. Nếu không có thứ tự, database không bảo đảm hàng nào nằm trước hoặc sau trong mỗi lần thực thi. Cùng một truy vấn với cùng `LIMIT`/`OFFSET` có thể trả về các hàng theo thứ tự khác nhau do execution plan, index hoặc trạng thái dữ liệu.

Ví dụ:

```sql
-- Không đủ ổn định cho phân trang.
SELECT id, name
FROM customer
LIMIT 20 OFFSET 40;
```

Nên xác định thứ tự:

```sql
SELECT id, name
FROM customer
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
```

`created_at` có thể trùng giữa nhiều hàng. Thêm `id` làm tie-breaker để tạo thứ tự toàn phần ổn định hơn. Nếu chỉ sắp xếp theo cột không duy nhất, các hàng có cùng giá trị có thể đổi vị trí giữa các lần truy vấn.

Một thứ tự tốt cho pagination cần:

- Có ý nghĩa đối với màn hình hoặc nghiệp vụ.
- Xác định rõ chiều `ASC`/`DESC`.
- Có thêm khóa duy nhất làm tie-breaker.
- Có cách xử lý nhất quán đối với giá trị `NULL` nếu cột sort nullable.
- Phù hợp với index nếu truy vấn cần chạy thường xuyên trên tập dữ liệu lớn.

Thứ tự xác định giúp giảm việc một hàng bị lặp hoặc bị bỏ sót chỉ vì thứ tự không rõ. Tuy nhiên, nó không ngăn được mọi thay đổi vị trí khi dữ liệu được chèn/xóa giữa các lần lấy trang; vấn đề đó cần được xem xét riêng.

## 4. OFFSET pagination trong Spring Data R2DBC

Có một số cách triển khai tùy API và phiên bản Spring Data đang sử dụng. Với reactive repository, không nên mặc định rằng mọi kiểu `Page<T>` của repository đồng nghĩa với một thao tác reactive không chặn. `Page` thường cần tổng số hàng để tính `totalElements` và `totalPages`; việc lấy count là một truy vấn bổ sung. Reactive query methods thường trả `Flux<T>`/`Mono<T>`, và khả năng dùng `Pageable` làm tham số phụ thuộc module cùng phiên bản.

### Dùng `Pageable` khi query method hỗ trợ

Một derived query method có thể nhận `Pageable` ở những phiên bản/module hỗ trợ tham số này:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status, Pageable pageable);
}
```

Caller tạo `Pageable`:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
);

Flux<Customer> customers = customerRepository.findByStatus("ACTIVE", pageable);
```

Đoạn code minh họa query method có hỗ trợ `Pageable`. Hãy kiểm tra phiên bản Spring Data Relational R2DBC của dự án để xác nhận khả năng hỗ trợ tham số và cách áp dụng sort. Nếu query method không hỗ trợ hoặc cần kiểm soát SQL rõ hơn, có thể tính offset và dùng `DatabaseClient` như ví dụ tiếp theo.

Không nên nhầm tham số `Pageable` với việc framework luôn trả một `Page<T>`. Trong reactive repository, `Flux<T>` thường là kiểu kết quả phù hợp cho tập hàng; nếu cần total count, hãy thực hiện count query riêng và kết hợp publisher một cách tường minh.

### Dùng `DatabaseClient` với LIMIT/OFFSET

Với SQL tùy chỉnh, có thể bind giới hạn và offset:

```java
public Flux<Customer> findPage(int page, int size) {
    if (page < 0 || size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("Trang không hợp lệ"));
    }

    long offset = Math.multiplyExact((long) page, size);

    return databaseClient.sql("""
                SELECT id, name, email, created_at
                FROM customer
                WHERE status = :status
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """)
            .bind("status", "ACTIVE")
            .bind("limit", size)
            .bind("offset", offset)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email", String.class),
                    row.get("created_at", LocalDateTime.class)
            ))
            .all();
}
```

Đây là ví dụ SQL có cú pháp `LIMIT`/`OFFSET` phổ biến ở PostgreSQL và một số database khác. Cú pháp phân trang, kiểu tham số và việc bind limit/offset phụ thuộc dialect/driver. Với database dùng cú pháp khác, hãy điều chỉnh SQL theo hệ quản trị thực tế. `DatabaseClient` không tự biến mọi câu SQL thành cú pháp portable.

### Dùng `R2dbcEntityTemplate`

`R2dbcEntityTemplate` có API query dựa trên metadata và `Query`. Có thể xây dựng điều kiện, sort, limit/offset theo API được phiên bản hỗ trợ, rồi ánh xạ kết quả thành entity:

```java
Query query = Query.query(where("status").is("ACTIVE"))
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        ))
        .limit(size)
        .offset(offset);

Flux<Customer> customers = template.select(Customer.class)
        .matching(query)
        .all();
```

Các method builder cụ thể có thể khác theo phiên bản Spring Data Relational; cần đối chiếu API mà dự án đang dùng. Lợi ích của template là điều kiện và sort tham chiếu property của entity, để mapping/dialect xử lý tên cột. Với SQL join, CTE hoặc biểu thức riêng database, `DatabaseClient` thường phù hợp hơn.

## 5. Vì sao offset lớn thường tốn kém?

Giả sử truy vấn:

```sql
SELECT id, created_at, title
FROM article
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 500000;
```

Ứng dụng chỉ nhận 20 hàng, nhưng database thường vẫn phải xác định thứ tự và đi qua khoảng 500.020 hàng đầu tiên theo thứ tự truy vấn để bỏ 500.000 hàng rồi trả 20 hàng tiếp theo. Cách database thực hiện phụ thuộc execution plan, index, predicate và engine; không phải mọi trường hợp đều có cùng chi phí tuyến tính. Tuy nhiên, offset càng lớn thường đồng nghĩa database phải làm nhiều công việc hơn để đến được vị trí bắt đầu.

Các chi phí có thể xuất hiện:

1. **Đọc hoặc duyệt nhiều entry:** database phải đi qua các hàng/index entry đứng trước offset.
2. **Sort:** nếu không có index hỗ trợ thứ tự, database có thể phải sort một tập dữ liệu lớn trước khi bỏ qua các hàng đầu.
3. **Truy cập heap/table:** index có thể tìm thứ tự nhanh hơn, nhưng nếu cần nhiều cột không nằm trong index, database còn phải đọc hàng dữ liệu tương ứng.
4. **Join:** nếu offset áp dụng sau join, database có thể phải tạo/duyệt nhiều hàng trung gian trước khi trả trang.
5. **Truyền và xử lý nội bộ:** database có thể không gửi các hàng bị bỏ qua qua mạng, nhưng vẫn phải xử lý chúng trong execution plan.

Vì vậy, response chỉ có 20 hàng không có nghĩa database chỉ làm việc với 20 hàng. Page sâu có thể chậm hơn nhiều so với page đầu dù kích thước trang giống nhau.

### OFFSET không giống Flux.skip()

Hai cách sau khác nhau:

```java
// Database chỉ được yêu cầu trả tất cả hàng; ứng dụng bỏ qua ở phía client.
return databaseClient.sql("SELECT id, name FROM customer ORDER BY id")
        .map((row, metadata) -> mapCustomer(row))
        .all()
        .skip(500_000)
        .take(20);
```

```sql
-- Database được yêu cầu thực hiện offset/limit.
SELECT id, name
FROM customer
ORDER BY id
LIMIT 20 OFFSET 500000;
```

`Flux.skip(n)` bỏ phần tử sau khi publisher đã phát chúng vào pipeline; database/driver có thể phải đọc và truyền qua ứng dụng số hàng bị bỏ, tùy cách tiêu thụ. `LIMIT/OFFSET` trong SQL cho database biết chỉ cần trả phần kết quả thuộc trang. SQL offset vẫn tốn chi phí duyệt ở phía database, nhưng thường tránh chuyển hàng bị bỏ qua qua mạng và vào pipeline Java.

Không nên dùng `.skip(offset).take(size)` như một cách thay thế mặc định cho phân trang SQL trên truy vấn lớn.

## 6. Vai trò của index trong OFFSET pagination

Index phù hợp có thể giảm chi phí tìm và sắp xếp. Giả sử truy vấn thường xuyên là:

```sql
SELECT id, created_at, title
FROM article
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 10000;
```

Một index có thứ tự cột phù hợp với predicate và sort có thể giúp database duyệt theo thứ tự cần thiết:

```sql
CREATE INDEX idx_article_status_created_id
ON article (status, created_at DESC, id DESC);
```

Index cụ thể cần dựa trên selectivity, tần suất truy vấn, thứ tự sort, kiểu database và workload ghi. Không nên tạo index chỉ bằng cách sao chép ví dụ mà không xem query plan.

### Index giúp gì và không giúp gì?

- Có thể giúp lọc theo `status` và đọc theo thứ tự `created_at`, `id`.
- Có thể tránh hoặc giảm bước sort riêng nếu optimizer chọn index phù hợp.
- Có thể giảm số lần truy cập bảng nếu index bao phủ các cột cần trả về và database hỗ trợ index-only/covering access.
- Không tự làm cho việc bỏ qua hàng trăm nghìn vị trí biến mất. Database vẫn cần tiến qua các entry trước vị trí offset trong nhiều execution plan.
- Không bảo đảm optimizer sẽ chọn index đó; thống kê, selectivity và chi phí thực tế ảnh hưởng quyết định.

Nếu truy vấn cần nhiều cột lớn hoặc cột không có trong index, việc đọc heap/table vẫn có thể tốn kém. Cũng cần cân nhắc chi phí ghi và dung lượng của index bổ sung.

### Kiểm tra bằng EXPLAIN

Hãy xem execution plan cho cả trang đầu và trang sâu:

```sql
EXPLAIN
SELECT id, created_at, title
FROM article
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 10000;
```

Với PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` có thể cung cấp thời gian thực thi và thông tin buffer khi chạy truy vấn thật. `ANALYZE` thực sự thực thi câu lệnh, nên cần dùng thận trọng trên môi trường production, nhất là với truy vấn nặng hoặc câu lệnh ghi.

Khi đọc plan, quan sát:

- Số hàng ước tính và số hàng thực tế tại từng node.
- Có `Sort` hay không và số hàng phải sort.
- Loại scan được chọn: sequential scan, index scan, index-only scan hoặc bitmap scan.
- Số buffer đọc/đụng tới và thời gian tại node.
- Chi phí thay đổi thế nào khi offset tăng từ 0 lên 10.000, 100.000 hoặc lớn hơn.

Đừng chỉ nhìn `LIMIT 20` rồi kết luận truy vấn rẻ. Hãy đo đúng query với dữ liệu và điều kiện lọc gần môi trường thực tế.

## 7. COUNT(*) và chi phí tạo Page đầy đủ

Một giao diện phân trang thường cần cả danh sách hàng lẫn thông tin tổng số hàng để hiển thị tổng số trang. Điều này thường đòi hỏi hai truy vấn:

```sql
SELECT id, name
FROM customer
WHERE status = :status
ORDER BY id
LIMIT :limit OFFSET :offset;
```

```sql
SELECT COUNT(*)
FROM customer
WHERE status = :status;
```

Count query có thể tốn kém nếu predicate phức tạp, join nhiều bảng hoặc bảng rất lớn. Database có thể cần duyệt nhiều hàng phù hợp để tính chính xác count. Index và optimizer có thể hỗ trợ nhưng không nên mặc định `COUNT(*)` luôn miễn phí.

### Không nhất thiết response nào cũng cần total count

Nếu UI chỉ cần nút “Trang tiếp theo”, có thể lấy `size + 1` hàng:

```sql
SELECT id, name
FROM customer
WHERE status = :status
ORDER BY id
LIMIT :sizePlusOne OFFSET :offset;
```

Nếu nhận được nhiều hơn `size` hàng, biết rằng còn trang tiếp theo. Sau đó bỏ hàng dư và trả `hasNext = true`. Cách này tránh count query ở mỗi request.

Với reactive repository, không nên giả định `Page<T>` được tạo miễn phí. `Page` thường chứa `totalElements`, vì thế cần count. Nếu muốn chỉ lấy nội dung và trạng thái còn trang, có thể tự định nghĩa response kiểu `Slice`/cursor hoặc DTO có `hasNext`, tùy API mà dự án sử dụng.

### Kết hợp data query và count query

Nếu cần total count, hai publisher có thể được kết hợp:

```java
public Mono<PageResult<Customer>> findCustomerPage(
        String status,
        int page,
        int size
) {
    long offset = Math.multiplyExact((long) page, size);

    Flux<Customer> content = findCustomers(status, size, offset);
    Mono<Long> total = countCustomers(status);

    return Mono.zip(content.collectList(), total)
            .map(tuple -> new PageResult<>(
                    tuple.getT1(),
                    page,
                    size,
                    tuple.getT2()
            ));
}
```

Ví dụ response DTO:

```java
public record PageResult<T>(
        List<T> content,
        int page,
        int size,
        long totalElements
) {
    public long totalPages() {
        return totalElements == 0
                ? 0
                : (totalElements + size - 1) / size;
    }
}
```

`findCustomers` và `countCustomers` đại diện cho hai query riêng. `Mono.zip` đăng ký và kết hợp kết quả khi publisher kết hợp được subscribe. Nếu count và data query phải quan sát cùng một snapshot dữ liệu, hãy đặt chúng trong reactive transaction với isolation level phù hợp. Nếu không, dữ liệu có thể thay đổi giữa hai truy vấn khiến `content` và `totalElements` không phản ánh cùng một thời điểm.

## 8. Dữ liệu thay đổi giữa các lần lấy trang

Ngay cả khi `ORDER BY` có tie-breaker duy nhất, offset pagination vẫn có thể bỏ sót hoặc lặp hàng khi dữ liệu thay đổi giữa hai request.

Ví dụ page size là 3 và thứ tự theo ID tăng dần:

```text
Trang 0: 10, 20, 30
Trang 1: 40, 50, 60
```

Sau khi người dùng đọc trang 0, một hàng mới có ID 15 được chèn:

```text
Thứ tự mới: 10, 15, 20, 30, 40, 50, 60
```

Trang 1 với `OFFSET 3` giờ trả `30, 40, 50`. Hàng 30 bị lặp vì vị trí của nó đã dịch chuyển. Tương tự, nếu một hàng trước offset bị xóa, một hàng phía sau có thể dịch lên và bị bỏ qua ở request tiếp theo.

Đây không phải lỗi R2DBC; đó là hệ quả của việc mỗi trang được xác định bằng vị trí tương đối trong một tập kết quả có thể thay đổi.

### Transaction có giải quyết được không?

Một transaction có isolation level phù hợp có thể giữ snapshot nhất quán trong phạm vi một lần xử lý gồm nhiều query. Nhưng giao diện thường gọi API trang 0 và trang 1 trong hai HTTP request riêng, mỗi request có transaction riêng. Transaction của request trước không thể tự giữ snapshot cho request sau.

Nếu yêu cầu người dùng duyệt một snapshot cố định qua nhiều request, cần thiết kế rõ hơn, ví dụ snapshot/version của tập dữ liệu, thời điểm cutoff hoặc cursor dựa trên một mốc ổn định. Việc giữ một transaction mở qua thời gian người dùng đọc từng trang thường không phù hợp vì giữ connection và snapshot lâu.

## 9. Vì sao keyset pagination phù hợp với trang sâu?

Keyset pagination (còn gọi là seek pagination) xác định trang tiếp theo dựa trên giá trị của hàng cuối trang trước, thay vì đếm số hàng cần bỏ qua.

Giả sử danh sách sắp xếp theo `created_at DESC, id DESC`. Trang trước kết thúc ở:

```text
created_at = 2026-10-10T10:30:00
id = 9000
```

Trang tiếp theo lấy các hàng đứng sau cặp giá trị đó trong thứ tự giảm dần:

```sql
SELECT id, created_at, title
FROM article
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Điều kiện này tương đương với việc tìm hàng sau cursor `(lastCreatedAt, lastId)` theo thứ tự đã chọn. Không cần bỏ qua 500.000 hàng trước đó. Nếu có index phù hợp, database có thể seek tới vùng giá trị cần đọc rồi lấy số hàng giới hạn.

### Điều kiện để keyset hoạt động đúng

- Thứ tự sort phải xác định và có tie-breaker duy nhất.
- Cursor phải chứa đủ giá trị của tất cả cột sort.
- Điều kiện so sánh phải phản ánh đúng chiều tăng/giảm của từng cột.
- Xử lý `NULL` rõ ràng vì phép so sánh với SQL NULL không cho kết quả true/false thông thường.
- Nếu sort theo cột có thể thay đổi trong lúc duyệt, hàng có thể di chuyển qua cursor; nên ưu tiên khóa/thời điểm ổn định.
- Index nên bắt đầu bằng các cột equality filter rồi đến các cột sort/cursor phù hợp với query.

Keyset pagination phù hợp với nút “tiếp theo/trước đó”, cuộn vô hạn, feed và tập dữ liệu lớn. Nó không thuận tiện khi người dùng cần nhảy thẳng tới trang 500 mà không có cursor trung gian.

## 10. Keyset với khóa duy nhất đơn giản

Nếu danh sách chỉ sắp xếp theo ID tăng dần, cursor rất đơn giản:

```sql
SELECT id, name
FROM customer
WHERE id > :lastSeenId
ORDER BY id ASC
LIMIT :size;
```

Lần đầu không có `lastSeenId`, nên dùng một query khởi đầu riêng hoặc một điều kiện được xây dựng phù hợp. Sau khi trả trang, lưu ID cuối cùng làm cursor cho request tiếp theo.

Ví dụ dùng `DatabaseClient`:

```java
public Flux<Customer> findNextCustomers(Long lastSeenId, int size) {
    if (size < 1 || size > 100) {
        return Flux.error(new IllegalArgumentException("size không hợp lệ"));
    }

    if (lastSeenId == null) {
        return databaseClient.sql("""
                    SELECT id, name
                    FROM customer
                    ORDER BY id ASC
                    LIMIT :limit
                    """)
                .bind("limit", size)
                .map((row, metadata) -> new Customer(
                        row.get("id", Long.class),
                        row.get("name", String.class)
                ))
                .all();
    }

    return databaseClient.sql("""
                SELECT id, name
                FROM customer
                WHERE id > :lastId
                ORDER BY id ASC
                LIMIT :limit
                """)
            .bind("lastId", lastSeenId)
            .bind("limit", size)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class)
            ))
            .all();
}
```

Đây là dạng seek đơn giản. Cursor cần được trả về cho client, thường dựa trên ID cuối cùng của trang. Trong API thực tế, có thể đóng gói cursor cùng dữ liệu trang trong DTO thay vì yêu cầu client tự suy luận.

## 11. Keyset với nhiều cột sort

Nếu sort theo `created_at DESC, id DESC`, chỉ lưu `id` là không đủ để mô tả vị trí nếu thứ tự chính dùng `created_at`. Cursor phải chứa cả hai giá trị.

Điều kiện trang tiếp theo:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
```

Đối với các cột đều cùng chiều sort, một số database hỗ trợ so sánh tuple:

```sql
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
```

Tuple comparison không có cú pháp/hành vi giống nhau trên mọi database. Dạng biểu thức mở rộng với `OR` thường dễ điều chỉnh theo dialect hơn. Nếu sort có nhiều chiều khác nhau, ví dụ `score DESC, name ASC, id ASC`, phải xây dựng điều kiện lexicographic theo đúng chiều từng cột:

```sql
WHERE score < :lastScore
   OR (score = :lastScore AND name > :lastName)
   OR (score = :lastScore AND name = :lastName AND id > :lastId)
```

Không thể đảo toàn bộ toán tử một cách máy móc nếu các cột sort có chiều khác nhau. Hãy viết điều kiện sao cho nó biểu diễn đúng thứ tự mà `ORDER BY` tạo ra.

### Xử lý NULL trong sort key

Nếu cột sort nullable, database có quy tắc đặt NULL khác nhau theo dialect hoặc `NULLS FIRST`/`NULLS LAST`. Các phép `<`, `>` và `=` với NULL cho kết quả unknown. Vì vậy, cursor có giá trị NULL cần điều kiện riêng để xác định hàng kế tiếp.

Một cách đơn giản là chọn cột sort không nullable. Nếu không thể, hãy xác định rõ `NULLS FIRST` hoặc `NULLS LAST`, bổ sung biểu thức sort/flag và viết predicate cursor tương ứng. Cần kiểm thử riêng nhóm NULL và non-NULL.

## 12. Thiết kế index cho keyset

Với truy vấn:

```sql
SELECT id, created_at, title
FROM article
WHERE status = 'PUBLISHED'
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Một index có thể phù hợp:

```sql
CREATE INDEX idx_article_status_created_id
ON article (status, created_at DESC, id DESC);
```

Các cột equality filter thường được đặt trước các cột dùng để seek/sort trong composite index. Thứ tự cột chính xác cần dựa trên query thực tế, selectivity và quy tắc optimizer của database.

Keyset không tự động nhanh nếu không có index hoặc predicate không thể sử dụng index. Nếu database phải scan/sort phần lớn bảng, lợi ích có thể nhỏ hơn dự kiến. Hãy dùng `EXPLAIN` và dữ liệu gần production để xác nhận.

## 13. Offset và keyset: so sánh

| Tiêu chí | Offset pagination | Keyset pagination |
| --- | --- | --- |
| Vị trí trang | Số hàng cần bỏ qua | Giá trị của hàng cuối trang trước |
| Nhảy tới trang bất kỳ | Thuận tiện | Khó nếu chưa có cursor của vị trí đó |
| Trang sâu | Thường chậm dần khi offset tăng | Thường ổn định hơn nếu có index phù hợp |
| Dữ liệu thay đổi trước vị trí | Có thể gây lặp hoặc bỏ sót hàng giữa các request | Ít bị dịch vị trí do insert/delete trước cursor, nhưng vẫn phụ thuộc sort key và dữ liệu thay đổi |
| Tổng số trang | Dễ kết hợp count query | Thường không cần total count |
| Cursor | Không cần | Cần lưu và truyền cursor |
| Sort | Có thể hỗ trợ sort động tương đối dễ | Sort phải được mã hóa đầy đủ trong cursor và predicate |
| Trang trước | Dễ tính offset | Cần cursor/điều kiện đảo chiều riêng |
| Use case | Admin table, tìm kiếm có nhảy trang, dữ liệu vừa phải | Feed, infinite scroll, log, dữ liệu lớn và duyệt tuần tự |

Keyset thường tránh được chi phí bỏ qua hàng ở page sâu, nhưng không thay thế offset trong mọi tình huống. Nếu người dùng cần nhảy trực tiếp tới trang 100, offset có trải nghiệm đơn giản hơn. Nếu người dùng chỉ duyệt tiếp từ vị trí hiện tại, cursor thường phù hợp hơn.

## 14. Response cho offset pagination

Nếu UI cần tổng số trang, có thể định nghĩa response rõ ràng:

```java
public record OffsetPage<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        long totalPages,
        boolean hasNext
) {
}
```

Khi đã có `content`, `page`, `size` và `totalElements`, tính số trang:

```java
long totalPages = totalElements == 0
        ? 0
        : (totalElements + size - 1) / size;

boolean hasNext = page + 1L < totalPages;
```

Nếu không chạy count query, có thể dùng `size + 1` hàng để tính `hasNext` và bỏ hàng dư trước khi trả response. Khi đó không có `totalElements` chính xác và response nên thể hiện điều đó thay vì giả định tổng số trang.

Với bảng rất lớn, việc luôn tính `totalPages` có thể là chi phí đáng kể. Một UI cuộn vô hạn thường chỉ cần cursor và `hasNext`, không cần tổng số trang.

## 15. Pagination kết hợp JOIN one-to-many

Một lỗi phổ biến là đặt `LIMIT`/`OFFSET` trực tiếp lên result set của join one-to-many trong khi mục tiêu là phân trang entity cha.

Giả sử một customer có 10 order. Join customer với orders tạo 10 hàng cho customer đó. Nếu truy vấn có `LIMIT 10`, database có thể trả 10 hàng của cùng một customer, dù page size được hiểu là 10 customer.

Nếu mục tiêu là phân trang customer, hãy phân trang tập root trước:

```sql
WITH page_customer AS (
    SELECT id, name
    FROM customer
    WHERE status = :status
    ORDER BY id
    LIMIT :limit OFFSET :offset
)
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    o.id AS order_id,
    o.order_number AS order_number
FROM page_customer c
LEFT JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id;
```

CTE `page_customer` xác định đúng số customer của trang. Sau đó join lấy toàn bộ order của các customer trong trang. Kết quả có thể nhiều hơn `limit` hàng vì một customer có nhiều order, nhưng số parent vẫn đúng page size.

Count query cũng phải đếm customer ở tập root, không đếm hàng join. Nếu cần count sau join, dùng `COUNT(DISTINCT c.id)` khi phù hợp.

## 16. OFFSET lớn và các lựa chọn tối ưu

Khi đo thấy page sâu chậm, có thể xem xét theo thứ tự:

1. **Giảm kích thước page:** tránh trả hàng trăm hoặc hàng nghìn bản ghi mỗi request nếu UI không cần.
2. **Chỉ select cột cần dùng:** tránh đọc payload lớn, JSON hoặc blob khi danh sách chỉ hiển thị vài trường.
3. **Tạo index phù hợp:** hỗ trợ điều kiện lọc và `ORDER BY`.
4. **Đưa predicate xuống database:** lọc ở SQL thay vì tải nhiều hàng rồi dùng Reactor `filter`.
5. **Đánh giá count query:** không tính tổng nếu UI không cần; nếu cần, tối ưu query count riêng.
6. **Phân trang root trước join child:** tránh limit trên hàng join làm sai số lượng entity cha.
7. **Chuyển sang keyset:** nếu người dùng duyệt tuần tự và offset sâu là nút thắt.
8. **Kiểm tra query plan:** xác nhận database thực sự dùng index và số hàng phải xử lý.

Không nên chỉ tăng connection pool hoặc tăng concurrency để chữa truy vấn offset chậm. Nếu database cần duyệt hàng trăm nghìn entry cho mỗi page, thêm nhiều connection có thể làm database chịu tải nặng hơn mà không giảm lượng công việc cho từng truy vấn.

## 17. Chọn offset hay keyset theo yêu cầu giao diện

### Offset phù hợp khi

- Người dùng cần nhảy tới một số trang cụ thể.
- Dữ liệu có kích thước vừa phải hoặc offset tối đa được giới hạn.
- Giao diện cần tổng số trang và số hàng.
- Các truy vấn có index tốt và thời gian phản hồi vẫn ổn ở trang sâu.
- Việc dữ liệu thay đổi nhẹ giữa các request có thể chấp nhận.

### Keyset phù hợp khi

- Người dùng chủ yếu bấm “xem thêm” hoặc cuộn vô hạn.
- Dữ liệu lớn và thường xuyên truy cập vị trí sâu.
- Thứ tự có thể biểu diễn bằng cursor ổn định, chẳng hạn `(createdAt, id)`.
- Muốn tránh việc bỏ qua một lượng lớn hàng ở database.
- Không bắt buộc nhảy trực tiếp tới một page number tùy ý.

### Có thể kết hợp cả hai

Một ứng dụng có thể dùng offset cho màn hình quản trị cần nhảy trang và keyset cho feed hoặc log có lượng dữ liệu lớn. Không nhất thiết toàn hệ thống phải chọn một chiến lược duy nhất. Mỗi endpoint nên chọn theo cách người dùng duyệt dữ liệu và đặc điểm query.

## 18. Kiểm thử và đo hiệu năng

Kiểm thử pagination cần xác nhận cả tính đúng của dữ liệu lẫn chi phí truy vấn.

### Kiểm thử tính đúng

- Trang đầu dùng offset 0 và trả đúng số hàng tối đa.
- Trang tiếp theo dùng offset tăng theo page size.
- Hàng cuối trang trước không xuất hiện lại ở trang kế tiếp khi dữ liệu không đổi.
- Thứ tự có tie-breaker duy nhất.
- Trang vượt quá cuối tập dữ liệu trả rỗng.
- Page size 0, âm hoặc vượt giới hạn bị từ chối.
- Offset tính toán không tràn số.
- Count query và data query dùng cùng predicate.
- LEFT JOIN và phân trang root không làm mất parent hoặc tạo parent trùng.

Ví dụ với `StepVerifier`:

```java
StepVerifier.create(repository.findPage(0, 20))
        .expectNextCount(20)
        .verifyComplete();

StepVerifier.create(repository.findPage(1, 20))
        .expectNextCount(20)
        .verifyComplete();
```

Test này giả định có ít nhất 40 hàng phù hợp. Cần thêm fixture để kiểm tra trang cuối có ít hơn page size và trang ngoài phạm vi.

### Đo hiệu năng

Tạo dữ liệu đủ lớn và đo cùng một query với offset 0, 10.000, 100.000 và một vị trí sâu hơn. Ghi nhận:

- Latency p50/p95/p99.
- Số hàng thực tế database phải duyệt theo execution plan.
- Buffer/page đọc.
- Có sort hay không.
- Thời gian count query riêng.
- CPU và I/O database.
- Số connection và thời gian chờ connection trong pool.

So sánh offset và keyset với cùng filter, sort, page size và dữ liệu. Không kết luận chỉ từ một lần chạy; cache nóng/lạnh, thống kê và tải đồng thời có thể làm kết quả khác nhau.

## 19. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Các trang có hàng trùng hoặc thiếu | Không có `ORDER BY` ổn định hoặc dữ liệu thay đổi giữa request | Thêm tie-breaker duy nhất; cân nhắc keyset |
| Trang sâu chậm hơn nhiều | Database phải đi qua nhiều hàng trước offset | Dùng index phù hợp hoặc chuyển sang keyset |
| Response chỉ có ít parent dù page size lớn | LIMIT áp dụng lên hàng join one-to-many | Phân trang root trước rồi join child |
| Count query chậm | Predicate/join count nặng hoặc bảng lớn | Tối ưu count, index hoặc bỏ total nếu UI không cần |
| Tổng số trang không khớp nội dung | Data query và count query dùng điều kiện khác nhau hoặc dữ liệu thay đổi | Đồng bộ predicate; cân nhắc transaction/isolation |
| SQL trả quá nhiều dữ liệu | Dùng `.skip()` ở pipeline thay cho SQL pagination | Đẩy LIMIT/OFFSET xuống database |
| Offset âm hoặc sai | Page number bắt đầu từ 1 nhưng công thức/ API dùng 0-based | Chuẩn hóa quy ước page index và validate |
| Offset bị tràn số | Nhân page và size bằng kiểu số quá nhỏ | Tính bằng `long` và dùng `Math.multiplyExact` |
| Sort không dùng được index | Thứ tự cột index không phù hợp filter/sort | Xem EXPLAIN và thiết kế composite index theo query |
| Keyset bỏ sót hàng có cùng sort value | Cursor chỉ chứa một phần sort key | Lưu đủ mọi cột sort và tie-breaker |
| Keyset xử lý sai giá trị NULL | Predicate không phản ánh `NULLS FIRST/LAST` | Quy định null ordering và viết predicate riêng |

## 20. Ghi nhớ

- Offset pagination dùng `LIMIT` để giới hạn số hàng và `OFFSET` để bỏ qua số hàng đứng trước; offset bắt đầu từ 0.
- Công thức offset là `pageIndex * pageSize`; dùng `long`, validate đầu vào và tránh tràn số.
- Luôn có `ORDER BY` ổn định, thường bổ sung khóa duy nhất làm tie-breaker.
- Offset lớn thường làm database phải duyệt/bỏ qua nhiều hàng trước khi trả page; R2DBC reactive không loại bỏ chi phí đó.
- `Flux.skip()` bỏ hàng ở phía ứng dụng và có thể khiến nhiều dữ liệu phải đi qua driver/network; ưu tiên pagination trong SQL.
- Index phù hợp có thể giảm sort và truy cập dữ liệu, nhưng không làm chi phí bỏ qua offset lớn biến mất trong mọi execution plan.
- Count query là một chi phí riêng; chỉ lấy total count khi giao diện hoặc nghiệp vụ thực sự cần.
- Dữ liệu được chèn/xóa giữa các request có thể làm offset page lặp hoặc bỏ sót hàng dù thứ tự đã ổn định.
- Với join one-to-many, phân trang tập root trước rồi mới join child để page size đếm đúng entity cha.
- Keyset pagination dùng giá trị hàng cuối làm cursor, thường phù hợp hơn cho page sâu và duyệt tuần tự khi có index đúng.
- Cursor phải chứa đủ sort key, có tie-breaker duy nhất và xử lý rõ chiều sort cùng giá trị NULL.
- Dùng `EXPLAIN`/`EXPLAIN ANALYZE` và benchmark với dữ liệu thực tế để quyết định tối ưu hoặc chuyển chiến lược.

Khi thiết kế phân trang R2DBC, hãy bắt đầu từ cách người dùng di chuyển trong danh sách. Nếu cần nhảy tới trang bất kỳ và tập dữ liệu vừa phải, offset dễ triển khai. Nếu cần duyệt liên tục trên tập dữ liệu lớn, hãy cân nhắc cursor/keyset để database tìm từ vị trí của hàng cuối trang trước thay vì phải bỏ qua một lượng lớn hàng.
