# Tránh gom toàn bộ Flux lớn vào bộ nhớ

Trong Spring Data Relational R2DBC, repository, `R2dbcEntityTemplate` và `DatabaseClient` thường trả về `Flux<T>` cho truy vấn nhiều hàng. `Flux` cho phép ứng dụng xử lý dữ liệu theo luồng và truyền backpressure giữa các tầng. Tuy nhiên, dùng `Flux` không tự động bảo đảm bộ nhớ luôn ổn định. Chỉ một toán tử như `collectList()`, `sort()`, `cache()` hoặc một buffer không giới hạn cũng có thể buộc ứng dụng giữ toàn bộ kết quả trong heap.

Với bảng lớn, gom tất cả hàng vào một `List` có thể làm heap tăng theo số lượng bản ghi, tạo nhiều object tạm, tăng thời gian garbage collection và cuối cùng gây `OutOfMemoryError`. Giải pháp là giữ dữ liệu ở dạng streaming khi phù hợp, giới hạn rõ ràng mọi buffer, xử lý theo batch hữu hạn hoặc đẩy phép lọc/tổng hợp xuống database. Nếu cần tải toàn bộ dữ liệu, hãy thiết kế export theo page hoặc job nền thay vì mặc định materialize toàn bộ tập kết quả trong một request.

## 1. Flux không đồng nghĩa với bộ nhớ không giới hạn

Một truy vấn R2DBC có thể trả `Flux<Customer>`:

```java
Flux<Customer> customers = customerRepository.findAll();
```

Publisher này mô tả một luồng dữ liệu. Nếu downstream tiêu thụ từng phần tử và các toán tử trong pipeline giữ lượng dữ liệu đang chờ ở mức hữu hạn, ứng dụng có thể xử lý tập dữ liệu lớn mà không cần giữ tất cả hàng cùng lúc.

Nhưng đoạn sau materialize toàn bộ kết quả:

```java
Mono<List<Customer>> customers = customerRepository.findAll()
    .collectList();
```

`collectList()` phải đợi nguồn hoàn tất và lưu tất cả phần tử vào một `List` trước khi phát danh sách. Nếu truy vấn trả một triệu hàng, danh sách và toàn bộ object `Customer` tương ứng có thể cùng tồn tại trong heap.

Do đó, cần phân biệt:

- **Streaming:** phần tử được xử lý khi nó đến, với lượng dữ liệu đang giữ có giới hạn.
- **Materialization:** tiêu thụ nguồn rồi giữ kết quả trong một cấu trúc dữ liệu như `List`, `Map` hoặc mảng.
- **Buffering:** giữ một số phần tử chờ xử lý; buffer có thể hữu hạn hoặc không giới hạn.
- **Aggregation:** tính kết quả tổng hợp. Có thể thực hiện tại database hoặc trong ứng dụng; cách thực hiện ảnh hưởng lớn tới bộ nhớ.

## 2. Vì sao gom toàn bộ Flux lớn gây áp lực bộ nhớ?

Giả sử mỗi hàng sau mapping chiếm trung bình một lượng bộ nhớ gồm entity, chuỗi, collection và object phụ trợ. Tổng bộ nhớ không chỉ bằng kích thước dữ liệu lưu trong database. Khi đọc vào JVM, mỗi hàng trở thành các object có header, reference và cấu trúc nội bộ.

Các yếu tố làm mức sử dụng heap tăng:

- Số hàng được materialize.
- Kích thước mỗi hàng và số cột được đọc.
- Số lượng object con, chuỗi và collection trong entity.
- Buffer của Reactor, driver và HTTP server.
- Số request đồng thời cùng materialize dữ liệu.
- Các bản sao trung gian khi mapping, sorting, grouping hoặc serialize.
- Thời gian giữ reference khiến garbage collector không thể thu hồi object.

Ví dụ, một request tải toàn bộ bảng tạo một `List<Customer>`. Nếu có nhiều request như vậy cùng lúc, heap tăng theo tổng số hàng của tất cả request, không chỉ một request.

Một phép ước lượng hữu ích:

\[
\text{Heap đang giữ} \approx
\text{Số phần tử đang giữ} \times
\text{Kích thước object trung bình}
\]

Đây chỉ là ước lượng ban đầu. Kích thước thực tế phụ thuộc JVM, object graph, string encoding, collection capacity, buffer và các bản sao. Hãy đo bằng profiler hoặc heap dump trên dữ liệu đại diện.

### 2.1. Nhiều request đồng thời khuếch đại vấn đề

Nếu một request giữ 100 MB dữ liệu và mười request cùng chạy, ứng dụng có thể phải giữ khoảng một GB chỉ cho phần kết quả materialize, chưa tính heap nền của ứng dụng. Điều này có thể tạo GC pressure, tăng latency và làm các request không liên quan cũng bị ảnh hưởng.

Không nên đánh giá an toàn chỉ bằng cách chạy một request trên máy phát triển. Cần xét kích thước dữ liệu production và mức đồng thời dự kiến.

## 3. collectList() là điểm materialize thường gặp nhất

`collectList()` chuyển `Flux<T>` thành `Mono<List<T>>`:

```java
Mono<List<Customer>> loadAllCustomers() {
    return customerRepository.findAll()
        .collectList();
}
```

Publisher chỉ phát `List` sau khi nguồn hoàn tất. Trong suốt quá trình, danh sách tăng dần và giữ reference tới mọi phần tử đã nhận.

### 3.1. Không dùng collectList() cho bảng không có giới hạn

Không nên:

```java
public Mono<List<Order>> findAllOrders() {
    return orderRepository.findAll()
        .collectList();
}
```

Nếu bảng `orders` tăng theo thời gian mà API không có giới hạn, mức tiêu thụ bộ nhớ cũng tăng theo dữ liệu. Một endpoint từng hoạt động tốt với vài nghìn hàng có thể thất bại khi dữ liệu tăng lên hàng triệu hàng.

Nên trả `Flux<Order>` nếu caller có thể xử lý từng hàng:

```java
public Flux<Order> streamOrders() {
    return orderRepository.findAll();
}
```

Hoặc cung cấp API phân trang với giới hạn tối đa rõ ràng nếu caller cần một tập kết quả hữu hạn.

### 3.2. collectList() vẫn phù hợp với tập dữ liệu nhỏ có giới hạn

Không cần loại bỏ `collectList()` hoàn toàn. Nó phù hợp khi:

- Kết quả đã bị giới hạn bởi `LIMIT` hoặc page size.
- Tập dữ liệu có kích thước nhỏ và được kiểm soát bằng hợp đồng API.
- Thuật toán thực sự cần toàn bộ phần tử của một nhóm nhỏ.
- Một transaction/query đã hoàn tất trước khi danh sách được dùng ở tầng tiếp theo.

Ví dụ:

```java
public Mono<List<CustomerSummary>> findCustomerPage(int pageSize) {
    int boundedSize = Math.min(Math.max(pageSize, 1), 100);

    return databaseClient.sql("""
            SELECT id, name
            FROM customer
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("pageSize", boundedSize)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all()
        .collectList();
}
```

Ở đây danh sách bị giới hạn tối đa 100 phần tử. Giới hạn cần phù hợp với kích thước mỗi DTO và ngân sách response thực tế.

### 3.3. Đừng giới hạn chỉ ở tầng Flux nếu SQL vẫn đọc quá nhiều

Ví dụ:

```java
return customerRepository.findAll()
    .take(100);
```

`take(100)` hủy upstream sau 100 phần tử, nhưng driver có thể đã prefetch thêm dữ liệu tùy implementation. Database cũng có thể vẫn phải thực hiện một query không giới hạn. Khi use case chỉ cần tối đa 100 hàng, nên đưa giới hạn vào SQL:

```sql
SELECT id, name
FROM customer
ORDER BY id
LIMIT 100;
```

Có thể giữ `take(100)` như lớp bảo vệ bổ sung, nhưng `LIMIT` diễn đạt rõ mục tiêu ở database và giúp giảm lượng dữ liệu cần tạo/đọc.

## 4. Các toán tử khác cũng có thể giữ toàn bộ dữ liệu

Không chỉ `collectList()` mới gây vấn đề. Hãy hiểu semantics bộ nhớ của các toán tử trong pipeline.

| Toán tử | Hành vi bộ nhớ | Lưu ý |
|---|---|---|
| `collectList()` | Giữ tất cả phần tử trong `List` | Không dùng với nguồn lớn không giới hạn |
| `collectMap()` | Giữ tất cả entry trong `Map` | Số key có thể tăng theo số hàng |
| `collectMultimap()` | Giữ mọi giá trị theo key | Có thể giữ nhiều object hơn `collectMap()` |
| `sort()` | Phải thu thập đủ phần tử trước khi sắp xếp | Dùng `ORDER BY` tại database khi có thể |
| `cache()` | Lưu các tín hiệu đã phát để subscriber sau phát lại | Cache Flux lớn có thể giữ dữ liệu lâu dài |
| `replay()` | Lưu tín hiệu để phát lại theo cấu hình | Cần giới hạn size/time nếu dùng |
| `distinct()` | Duy trì tập các giá trị đã thấy | Set có thể tăng không giới hạn |
| `buffer()` | Gom phần tử thành collection | Phải giới hạn kích thước hoặc thời gian |
| `groupBy()` | Tạo nhiều group và giữ state/queue cho group | Cardinality cao có thể tốn bộ nhớ |
| `window()` | Tạo các Flux con theo ranh giới window | Phải tiêu thụ window đúng cách; không giữ vô hạn window |
| `reduce()` | Giữ accumulator | Bộ nhớ có thể nhỏ nếu accumulator có kích thước cố định |

### 4.1. sort() thường cần toàn bộ nguồn

Không nên:

```java
return customerRepository.findAll()
    .sort(Comparator.comparing(Customer::getName));
```

Để sắp xếp toàn bộ hàng, Reactor cần thu thập dữ liệu rồi mới phát theo thứ tự. Nếu database có thể sắp xếp, hãy dùng `ORDER BY` và index phù hợp:

```sql
SELECT id, name
FROM customer
ORDER BY name, id
LIMIT :pageSize;
```

Database có thể dùng index hoặc thuật toán sort riêng. Dù database cũng cần tài nguyên để sort, ứng dụng tránh phải giữ toàn bộ object Java trong heap.

### 4.2. cache() có thể giữ dữ liệu sau khi request kết thúc

`Flux.cache()` mặc định có thể giữ các tín hiệu đã phát để subscriber tiếp theo nhận lại. Nếu nguồn là toàn bộ bảng, cache có thể giữ toàn bộ kết quả trong bộ nhớ trong suốt vòng đời của publisher.

Không nên:

```java
private final Flux<Customer> allCustomers = customerRepository.findAll()
    .cache();
```

Nếu dữ liệu cần cache, hãy giới hạn tập dữ liệu, dùng cache có TTL/size phù hợp hoặc một cache chuyên dụng có eviction policy. Cần xác định invalidation khi database thay đổi.

### 4.3. distinct() có thể tăng state theo số giá trị khác nhau

```java
return eventRepository.findAll()
    .distinct(Event::getExternalId);
```

`distinct` cần nhớ các khóa đã thấy để loại trùng. Nếu nguồn lớn và gần như mọi key đều khác nhau, tập state có thể lớn tương đương số hàng. Nếu database có thể chọn distinct:

```sql
SELECT DISTINCT external_id
FROM event
ORDER BY external_id;
```

hãy cân nhắc đẩy phép loại trùng xuống database, kiểm tra execution plan và index.

## 5. Buffer phải có giới hạn

Buffer hữu ích khi cần gom dữ liệu thành batch, nhưng phải giới hạn số phần tử hoặc thời gian.

### 5.1. buffer(n)

```java
return customerRepository.findAll()
    .buffer(200)
    .concatMap(customerBatch -> processBatch(customerBatch));
```

Mỗi list có tối đa 200 phần tử. `concatMap` xử lý từng batch tuần tự, vì vậy số batch được xử lý đồng thời ở nhánh này được giới hạn. Tuy nhiên, vẫn cần chú ý prefetch của toán tử và các buffer ở upstream/driver.

### 5.2. bufferTimeout(maxSize, maxTime)

Nếu batch cần phát khi đủ số phần tử hoặc hết thời gian:

```java
return source.bufferTimeout(
        200,
        Duration.ofSeconds(1)
    )
    .concatMap(this::processBatch);
```

Batch được phát khi đạt tối đa 200 phần tử hoặc khi hết một giây theo semantics của operator. Điều này tránh giữ một batch nhỏ vô thời hạn khi nguồn phát chậm.

### 5.3. Tránh buffer không giới hạn

Không nên:

```java
return source.onBackpressureBuffer();
```

Nếu producer nhanh hơn consumer trong thời gian dài, buffer có thể tăng cho tới khi hết heap. Hãy ưu tiên để backpressure truyền ngược. Nếu phải buffer vì một yêu cầu cụ thể, đặt capacity và xác định rõ hành vi khi đầy: fail, drop hoặc xử lý theo cơ chế khác.

Không được chọn drop dữ liệu một cách tùy tiện cho nghiệp vụ ghi database, thanh toán hoặc event cần bảo đảm đầy đủ. Overflow policy phải phản ánh semantics của dữ liệu.

## 6. Giữ backpressure xuyên suốt pipeline

Reactive Streams cho phép downstream yêu cầu số lượng phần tử theo demand. Khi consumer chậm, upstream có thể giảm tốc độ phát nếu mọi tầng trong pipeline hỗ trợ backpressure.

Ví dụ xử lý tuần tự:

```java
return customerRepository.findAll()
    .concatMap(customer -> processCustomer(customer));
```

`concatMap` chỉ xử lý inner publisher hiện tại trước khi chuyển sang phần tử tiếp theo. Điều này giúp giới hạn số công việc đang chạy, nhưng prefetch của toán tử vẫn có thể giữ một số phần tử chờ.

Với `flatMap`, hãy đặt concurrency hữu hạn:

```java
return customerRepository.findAll()
    .flatMap(customer -> processCustomer(customer), 8);
```

Con số 8 giới hạn số inner publisher đang hoạt động theo overload được dùng. Nó không có nghĩa tổng bộ nhớ chỉ giữ đúng tám hàng: mỗi inner publisher, prefetch, driver và downstream có thể có buffer riêng.

### 6.1. flatMapSequential cũng có thể giữ kết quả chờ

`flatMapSequential` chạy inner publisher đồng thời nhưng giữ thứ tự phát theo thứ tự nguồn. Nếu inner publisher đầu tiên chậm trong khi các publisher sau hoàn tất nhanh, kết quả sau có thể phải chờ trong hàng đợi. Đặt concurrency và prefetch hợp lý, hoặc dùng `concatMap` nếu thứ tự tuần tự quan trọng hơn throughput.

### 6.2. publishOn có queue prefetch

`publishOn` chuyển xử lý downstream sang scheduler khác và có prefetch queue:

```java
return customerRepository.findAll()
    .publishOn(Schedulers.parallel(), 32)
    .map(this::calculateView);
```

Queue giúp tách nhịp xử lý giữa các scheduler, nhưng cũng giữ phần tử trong bộ nhớ. Chọn prefetch theo chi phí object và throughput; không tăng prefetch chỉ để che giấu consumer chậm.

### 6.3. Backpressure không loại bỏ buffer của driver

R2DBC driver và giao thức database có thể prefetch hoặc buffer một số hàng. Một subscriber yêu cầu một phần tử không nhất thiết tương ứng với một network round trip hoặc đúng một row được database gửi. Hãy kiểm tra hành vi fetch/cursor của driver và cấu hình `fetchSize` nếu driver hỗ trợ.

`Statement.fetchSize(int)` trong R2DBC SPI là gợi ý cho driver; một số driver có thể bỏ qua hoặc triển khai khác nhau. Nó không thay thế việc giới hạn kết quả hoặc phân trang và không bảo đảm bộ nhớ của toàn ứng dụng được giới hạn nếu pipeline phía sau materialize toàn bộ nguồn.

## 7. Dùng reduce() khi accumulator có kích thước cố định

Nếu chỉ cần một kết quả tổng hợp, đừng gom mọi hàng rồi tính trong Java.

Không nên:

```java
return orderRepository.findAll()
    .collectList()
    .map(orders -> orders.stream()
        .map(Order::getTotal)
        .reduce(BigDecimal.ZERO, BigDecimal::add));
```

Đoạn code giữ toàn bộ `Order` trong heap dù kết quả cuối chỉ là một số tiền.

Có thể dùng `reduce` với accumulator cố định:

```java
return orderRepository.findAll()
    .map(Order::getTotal)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Ở đây accumulator chỉ giữ một `BigDecimal` tại một thời điểm. Nhưng nếu phép tổng hợp có thể thực hiện tại database, thường nên đẩy xuống SQL:

```sql
SELECT COALESCE(SUM(total), 0) AS total_amount
FROM orders
WHERE status = :status;
```

Database trả một hàng thay vì truyền mọi order qua mạng và tạo object Java.

### 7.1. reduce() vẫn có thể tăng bộ nhớ

Accumulator không tự động nhỏ. Ví dụ:

```java
return source.reduce(
    new ArrayList<Customer>(),
    (list, customer) -> {
        list.add(customer);
        return list;
    }
);
```

Đoạn code này về bản chất vẫn gom toàn bộ dữ liệu vào list. Hãy đánh giá kích thước accumulator, không chỉ tên toán tử.

### 7.2. Chọn aggregate ở database

Một số phép tính nên thực hiện trong SQL:

| Nhu cầu | SQL |
|---|---|
| Đếm hàng | `COUNT(*)` |
| Tổng | `SUM(amount)` |
| Trung bình | `AVG(amount)` |
| Min/max | `MIN(value)`, `MAX(value)` |
| Nhóm theo trạng thái | `GROUP BY status` |
| Loại trùng | `DISTINCT` |
| Kiểm tra tồn tại | `EXISTS (...)` |
| Lấy top N | `ORDER BY ... LIMIT N` |

Ví dụ dùng `DatabaseClient`:

```java
Mono<Long> countPendingOrders() {
    return databaseClient.sql("""
            SELECT COUNT(*) AS total
            FROM orders
            WHERE status = :status
            """)
        .bind("status", "PENDING")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();
}
```

Database vẫn cần tài nguyên để tính aggregate, nhưng ứng dụng chỉ nhận kết quả nhỏ. Kiểm tra execution plan và index nếu aggregate trên bảng lớn.

## 8. Dùng projection thay vì tải toàn bộ entity

Nếu chỉ cần vài cột, đừng đọc mọi cột của entity lớn.

Không cần thiết:

```java
return customerRepository.findAll()
    .map(customer -> customer.getEmail());
```

Nếu entity có nhiều cột, JSON lớn hoặc dữ liệu LOB, việc mapping toàn bộ entity làm tăng network traffic và object allocation dù cuối cùng chỉ dùng email.

Dùng query projection:

```java
Flux<String> findAllEmails() {
    return databaseClient.sql("SELECT email FROM customer ORDER BY id")
        .map((row, metadata) -> row.get("email", String.class))
        .all();
}
```

Hoặc DTO nhỏ:

```java
Flux<CustomerSummary> findSummaries() {
    return databaseClient.sql("""
            SELECT id, name
            FROM customer
            ORDER BY id
            """)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all();
}
```

Projection giảm kích thước mỗi phần tử, lượng dữ liệu qua network và chi phí mapping. Nó không giới hạn số hàng; vẫn cần streaming hoặc page khi tập kết quả lớn.

## 9. Phân trang để giữ tập dữ liệu mỗi lần truy vấn hữu hạn

Khi caller cần duyệt toàn bộ dữ liệu, phân trang giúp mỗi truy vấn trả một lượng hàng giới hạn. Hai cách phổ biến là offset pagination và keyset pagination.

### 9.1. Offset pagination

```sql
SELECT id, name
FROM customer
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

Offset đơn giản và phù hợp cho giao diện cần nhảy tới trang cụ thể. Nhưng offset lớn có thể khiến database phải đọc/bỏ qua nhiều hàng trước khi trả page, và dữ liệu có thể dịch chuyển giữa các trang khi có INSERT/DELETE.

### 9.2. Keyset pagination

```sql
SELECT id, name
FROM customer
WHERE id > :afterId
ORDER BY id
LIMIT :pageSize;
```

Keyset dùng khóa cuối cùng của page trước làm cursor. Nó thường hiệu quả hơn khi đi sâu vào tập dữ liệu lớn và ổn định hơn trước việc thêm hàng ở phía trước cursor.

Cursor cần thứ tự duy nhất. Nếu sắp xếp theo `created_at`, dùng thêm `id` làm tie-breaker:

```sql
SELECT id, created_at, name
FROM customer
WHERE (created_at, id) > (:afterCreatedAt, :afterId)
ORDER BY created_at, id
LIMIT :pageSize;
```

Row-value comparison này là cú pháp phù hợp PostgreSQL và một số hệ quản trị khác; hãy kiểm tra dialect khi chuyển database.

### 9.3. Thu thập một page nhỏ rồi xử lý

```java
private Mono<List<CustomerSummary>> fetchPage(long afterId, int size) {
    return databaseClient.sql("""
            SELECT id, name
            FROM customer
            WHERE id > :afterId
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("afterId", afterId)
        .bind("pageSize", size)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .all()
        .collectList();
}
```

`collectList()` ở đây an toàn hơn vì `size` có giới hạn. Query page hoàn tất trước khi list được xử lý tiếp; bộ nhớ tối đa của page có thể ước lượng từ page size và kích thước DTO.

### 9.4. Xử lý page tuần tự

```java
private Flux<CustomerSummary> fetchPages(long afterId, int pageSize) {
    return Flux.defer(() -> fetchPage(afterId, pageSize))
        .flatMapMany(page -> {
            if (page.isEmpty()) {
                return Flux.empty();
            }

            long nextAfterId = page.get(page.size() - 1).id();

            return Flux.fromIterable(page)
                .concatWith(Flux.defer(() ->
                    fetchPages(nextAfterId, pageSize)
                ));
        });
}
```

Ví dụ giả định `CustomerSummary` có accessor `id()` và ID là khóa tăng có thứ tự. `Flux.defer` trì hoãn query page kế tiếp cho tới khi cần; `concatWith` giữ thứ tự và chỉ chuyển sang page tiếp theo sau page hiện tại.

Mỗi page là một query riêng. Khi `.all().collectList()` hoàn tất, result của query đó đã được tiêu thụ; connection có thể được trả về pool trước khi bắt đầu page tiếp theo. Điều này khác `findAll().buffer(pageSize)`, vốn chỉ chia một result stream thành các nhóm và không nhất thiết release connection giữa các nhóm.

### 9.5. Pagination không tự tạo snapshot nhất quán

Giữa hai page, dữ liệu có thể thay đổi. Nếu cần tập dữ liệu ổn định, hãy xác định cutoff/version hoặc snapshot theo yêu cầu. Giữ một transaction snapshot xuyên toàn bộ export có thể làm connection bị giữ lâu; cần cân nhắc trade-off.

## 10. Xử lý batch với bộ nhớ có giới hạn

Với tác vụ cập nhật/import, có thể đọc và xử lý theo batch:

```java
public Mono<Void> processAllCustomers() {
    return customerRepository.findAll()
        .buffer(200)
        .concatMap(batch -> customerService.processBatch(batch))
        .then();
}
```

Mỗi batch tối đa 200 customer. `concatMap` xử lý tuần tự để tránh nhiều batch cùng nằm trong flight. Tuy nhiên, nếu nguồn là một truy vấn `findAll()` duy nhất, connection của result có thể vẫn được giữ cho tới khi toàn nguồn hoàn tất. `buffer` giới hạn batch trong heap, nhưng không tự release connection giữa batch.

Nếu mục tiêu là vừa giới hạn bộ nhớ vừa release connection định kỳ, dùng query page riêng như phần trước, rồi xử lý xong page mới lấy page tiếp theo.

### 10.1. Chọn batch size

Batch size quá nhỏ làm tăng số round trip và overhead. Batch quá lớn làm tăng bộ nhớ, thời gian xử lý và phạm vi rollback nếu mỗi batch nằm trong transaction riêng.

Chọn dựa trên:

- Kích thước object trung bình.
- Số cột/LOB được đọc.
- Số lượng thao tác ghi mỗi batch.
- Connection pool và database capacity.
- Latency và thời gian transaction.
- Số worker/batch chạy đồng thời.

Nếu một batch chứa 500 entity, mỗi entity giữ một JSON document lớn, bộ nhớ có thể cao hơn nhiều so với 500 DTO nhỏ. Đo bằng dữ liệu thực tế.

### 10.2. Giới hạn số batch chạy đồng thời

Nếu batch độc lập và cần chạy song song, có thể dùng:

```java
return pageSource
    .flatMap(this::processBatch, 4)
    .then();
```

Concurrency 4 cho phép tối đa bốn batch inner publisher hoạt động theo toán tử này. Tổng bộ nhớ cần tính cả batch đang chạy, batch đã đọc trước, queue và trạng thái mỗi inner publisher.

Với thao tác database, concurrency cao còn có thể cạnh tranh connection pool và lock. Bắt đầu với giới hạn nhỏ, đo throughput/pool metrics rồi điều chỉnh.

## 11. groupBy() và cardinality cao

`groupBy` tạo một `GroupedFlux` cho từng key:

```java
return eventRepository.findAll()
    .groupBy(Event::getTenantId)
    .flatMap(group -> group.count());
```

Nếu số tenant nhỏ và giới hạn rõ, cách này có thể phù hợp. Nếu hàng triệu hàng có gần như hàng triệu key khác nhau, số group và state có thể tăng lớn. Ngoài ra, mỗi group cần được tiêu thụ; nếu một group không được subscribe/consume phù hợp, upstream có thể bị giữ hoặc tắc.

Nếu chỉ cần đếm theo tenant, database thường làm tốt hơn:

```sql
SELECT tenant_id, COUNT(*) AS total
FROM event
GROUP BY tenant_id;
```

Kết quả trả về một hàng cho mỗi tenant thay vì đưa mọi event vào JVM. Nếu số tenant cũng rất lớn, vẫn cần page/stream kết quả aggregate theo cách có giới hạn.

## 12. distinct() và deduplication

`distinct()` giữ state của những giá trị đã gặp. Khi nguồn lớn, state có thể tăng tương ứng với số key khác nhau:

```java
return eventRepository.findAll()
    .distinct(Event::getExternalId);
```

Nếu mục tiêu là lấy danh sách external ID duy nhất, hãy cân nhắc:

```sql
SELECT DISTINCT external_id
FROM event
ORDER BY external_id;
```

Database có thể sử dụng sort/hash aggregate và index phù hợp. Nó vẫn cần tài nguyên, nhưng ứng dụng không cần giữ toàn bộ key trong một Java `Set`.

Nếu deduplication cần dựa trên logic phức tạp không thể đẩy xuống SQL, hãy xử lý theo partition/batch hoặc dùng một kho trạng thái có giới hạn và chính sách eviction. Không giả định `distinct()` trên Flux vô hạn sẽ giữ bộ nhớ ổn định.

## 13. Cache dữ liệu lớn một cách có kiểm soát

Cache có thể giảm truy vấn lặp, nhưng cache toàn bộ Flux lớn thường tạo một bản sao dữ liệu dài hạn trong heap:

```java
Flux<Product> products = productRepository.findAll().cache();
```

Publisher cache có thể giữ các phần tử đã phát để phát lại cho subscriber sau. Nếu số lượng sản phẩm tăng liên tục, heap cache cũng tăng.

Các lựa chọn an toàn hơn:

- Cache một page nhỏ hoặc một truy vấn có giới hạn.
- Cache các giá trị tổng hợp nhỏ thay vì entity đầy đủ.
- Dùng cache ngoài heap/remote cache có max size và TTL.
- Thiết kế invalidation khi dữ liệu thay đổi.
- Không cache stream không giới hạn hoặc dữ liệu thay đổi liên tục mà không có eviction.

Nếu dùng Caffeine hoặc cache khác, đặt maximum size/weight và expiry rõ ràng. Cần tính kích thước object chứ không chỉ số entry.

## 14. Tránh tạo bản sao dữ liệu trong mapping

Ngay cả khi không gọi `collectList()`, mapping có thể tạo nhiều object trung gian:

```java
return customerRepository.findAll()
    .map(customer -> objectMapper.convertValue(
        customer,
        CustomerDto.class
    ));
```

Một phép convert có thể tạo object graph lớn, copy string hoặc collection. Nếu chỉ cần vài field, projection trực tiếp từ SQL thường tiết kiệm hơn.

Không nên serialize từng entity thành JSON string rồi giữ trong list nếu có thể để WebFlux encode DTO từng phần tử. Nếu cần ghi file, hãy ghi từng chunk với buffer hữu hạn và quản lý backpressure.

### 14.1. Cẩn thận với LOB và trường lớn

Các cột `TEXT`, `BYTEA`, JSONB lớn hoặc dữ liệu LOB có thể chiếm phần lớn heap. Nếu chỉ cần metadata, không SELECT cột payload. Nếu cần truyền file lớn, dùng API streaming phù hợp và kiểm tra cách driver/codec đọc dữ liệu; không chuyển toàn bộ binary thành `byte[]` lớn cho mọi request.

## 15. Streaming HTTP không phải lúc nào cũng là giải pháp hoàn chỉnh

WebFlux có thể ghi `Flux<T>` từng phần tử cho media type streaming như NDJSON hoặc SSE. Cách này tránh materialize toàn bộ response ở application layer, nhưng query result và connection có thể vẫn tồn tại trong suốt thời gian client đọc.

Ví dụ:

```java
@GetMapping(value = "/customers/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<CustomerSummary> streamCustomers() {
    return customerService.streamSummaries();
}
```

Streaming phù hợp khi:

- Tập dữ liệu có giới hạn thực tế hoặc thời gian stream được kiểm soát.
- Client có khả năng tiêu thụ theo luồng.
- Số stream đồng thời được giới hạn.
- Thời gian giữ connection và transaction chấp nhận được.

Với export rất lớn hoặc client có thể tải chậm nhiều phút, page query hoặc export job thường phù hợp hơn. Streaming tránh heap tăng theo toàn bộ kết quả nhưng có thể giữ connection lâu.

## 16. Export dữ liệu lớn bằng job và file

Với yêu cầu tải hàng triệu hàng, có thể tách quá trình chuẩn bị file khỏi request HTTP:

1. API tạo export job và trả job ID.
2. Worker đọc theo keyset page có kích thước hữu hạn.
3. Mỗi page được đọc xong và connection được release.
4. Worker serialize từng hàng hoặc từng batch vào file/object storage.
5. Worker ghi checkpoint và tiến độ.
6. Khi hoàn tất, API cung cấp link hoặc endpoint tải file.
7. File được xóa theo TTL/chính sách retention.

Worker cần backpressure, giới hạn concurrency, dung lượng file tối đa, timeout và khả năng resume. Nếu cần dữ liệu nhất quán tại một thời điểm, dùng cutoff/version hoặc snapshot được thiết kế rõ ràng.

Không nên dùng `collectList()` rồi serialize toàn bộ file trong bộ nhớ. Có thể dùng writer streaming với buffer hữu hạn, nhưng phải bảo đảm writer không tích lũy toàn bộ output trước khi flush.

## 17. Giới hạn kích thước request và page size

Không cho client điều khiển page size hoặc batch size không giới hạn. Validate input:

```java
int normalizePageSize(Integer requested) {
    if (requested == null) {
        return 50;
    }

    return Math.min(Math.max(requested, 1), 200);
}
```

Giá trị tối đa cần dựa trên kích thước response, heap budget và SLA. Nếu DTO có payload JSON lớn, giới hạn 200 có thể vẫn quá cao.

Đối với API export, nên dùng quota riêng theo user/tenant và giới hạn số job đồng thời. Không cho một client tạo nhiều request lớn để làm cạn bộ nhớ hoặc connection pool.

## 18. Ước lượng bộ nhớ cho batch và concurrency

Khi xử lý theo batch, có thể dùng mô hình đơn giản:

\[
\text{Heap cho dữ liệu batch} \approx
\text{Batch size} \times
\text{Kích thước phần tử trung bình} \times
\text{Số batch đồng thời}
\]

Ví dụ giả định mỗi DTO chiếm trung bình 4 KB, batch size 200 và concurrency 4:

\[
200 \times 4\text{ KB} \times 4
= 3.2\text{ MB}
\]

Đây chỉ là phần dữ liệu batch ước tính, không bao gồm object graph, queue prefetch, driver buffers, serialization buffers, thread stacks hoặc heap nền. Kích thước object trung bình cần đo bằng profiler hoặc heap dump.

Hãy dành headroom cho các request khác và GC. Không cấu hình batch/concurrency để sử dụng hết heap tối đa theo phép tính lý thuyết.

## 19. Quan sát bộ nhớ và phát hiện materialization không mong muốn

Các chỉ số cần theo dõi:

- Heap used và heap after GC.
- Allocation rate và object allocation theo endpoint/job.
- GC pause và GC frequency.
- Số request đang materialize hoặc export đồng thời.
- Số phần tử trong batch/queue nếu instrumentation hỗ trợ.
- Response size và số hàng trả về.
- Thời gian query và thời gian xử lý downstream.
- OOM count, container memory và process RSS.
- Số cache entry/weight và eviction count.

Tên metric cụ thể phụ thuộc Micrometer, JVM và deployment platform. Dùng JFR, heap dump hoặc profiler để xác định object type nào đang giữ heap khi metric cho thấy tăng bất thường.

### 19.1. Dấu hiệu collectList hoặc cache đang giữ dữ liệu

- Heap tăng theo số hàng của một request.
- Memory không giảm sau khi query hoàn tất vì cache/static reference vẫn giữ list.
- GC liên tục nhưng heap sau GC vẫn cao.
- Endpoint chỉ trả phần tử đầu tiên sau khi truy vấn hoàn tất.
- Một số request export đồng thời làm heap tăng đột biến.
- Heap dump cho thấy `ArrayList`, `HashMap`, Reactor cache state hoặc object DTO chiếm tỷ trọng lớn.

Không kết luận leak chỉ từ heap tăng trong lúc xử lý. Một list có thể được giữ hợp lệ cho tới khi request hoàn tất; cần xem object có còn reachable sau khi workflow kết thúc hay không.

## 20. Kiểm thử để phát hiện gom dữ liệu quá lớn

Unit test có thể xác nhận service không yêu cầu toàn bộ nguồn trước khi phát phần tử đầu tiên:

```java
@Test
void streamsItemsWithoutWaitingForSourceCompletion() {
    TestPublisher<Integer> source = TestPublisher.create();

    Flux<Integer> result = source.flux()
        .map(value -> value * 2);

    StepVerifier.create(result)
        .then(() -> source.next(1))
        .expectNext(2)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
}
```

Test này xác nhận mapping phát phần tử trước khi source complete. Nếu pipeline có `collectList()`, phần tử sẽ chưa được phát cho tới khi nguồn hoàn tất.

### 20.1. Kiểm thử batch size có giới hạn

```java
@Test
void emitsBatchesWithConfiguredMaximumSize() {
    StepVerifier.create(
            Flux.range(1, 10).buffer(3)
        )
        .expectNext(List.of(1, 2, 3))
        .expectNext(List.of(4, 5, 6))
        .expectNext(List.of(7, 8, 9))
        .expectNext(List.of(10))
        .verifyComplete();
}
```

Test minh họa semantics của `buffer(3)`. Với pipeline production, kiểm tra batch size, concurrency và số query thực tế.

### 20.2. Kiểm thử không gọi collectList trên nguồn không giới hạn

Có thể dùng `Flux.never()` hoặc `Flux.interval()` để xác nhận pipeline có thể phát phần tử theo demand mà không đợi complete. Test cần giới hạn thời gian và hủy subscription để không để nguồn chạy nền.

### 20.3. Integration test với lượng dữ liệu lớn

Với database thật:

- Seed dữ liệu đủ lớn và có kích thước hàng gần production.
- Chạy query streaming hoặc page query.
- Đo heap/allocation và thời gian first item.
- Chạy nhiều request đồng thời theo tải mục tiêu.
- So sánh streaming, page materialization và `collectList()` trên tập có giới hạn.
- Xác nhận connection được trả về pool sau mỗi query/page.
- Kiểm tra cancellation và cleanup.

Không cần seed hàng triệu hàng trong mọi CI test. Có thể có integration test vừa phải trong CI và performance/load test riêng với dữ liệu lớn hơn.

## 21. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| `findAll().collectList()` trên bảng lớn | Giữ toàn bộ entity trong heap | Trả `Flux`, dùng page hoặc aggregate ở database |
| `collectMap()`/`collectMultimap()` trên nguồn lớn | Map tăng theo số key/value | Dùng query group/aggregate hoặc xử lý từng page |
| `sort()` trên toàn Flux | Materialize tất cả phần tử để sắp xếp | Dùng SQL `ORDER BY` và index phù hợp |
| `cache()` Flux toàn bảng | Giữ dữ liệu lâu dài trong publisher cache | Cache page/kết quả nhỏ, đặt TTL và max size |
| `distinct()` với cardinality lớn | Tập key đã thấy tăng không giới hạn | Dùng SQL `DISTINCT` hoặc dedup theo partition |
| `onBackpressureBuffer()` không giới hạn | Heap tăng khi consumer chậm | Giữ backpressure hoặc buffer bounded |
| `buffer(n)` rồi nghĩ connection release mỗi batch | Result stream gốc vẫn có thể giữ connection | Dùng query page riêng nếu cần release giữa batch |
| `flatMap()` không giới hạn | Nhiều inner publisher và kết quả chờ | Đặt concurrency hữu hạn |
| `flatMapSequential()` với inner đầu chậm | Kết quả sau bị queue chờ thứ tự | Giảm concurrency/prefetch hoặc dùng `concatMap` |
| `groupBy()` với nhiều key | Nhiều group và queue/state | Group/aggregate ở database hoặc phân vùng hữu hạn |
| `reduce()` với List accumulator | Vẫn gom toàn bộ nguồn | Dùng accumulator kích thước cố định hoặc SQL aggregate |
| Chỉ dùng `.take(n)` sau query không giới hạn | Database/driver có thể đã prefetch; query vẫn không diễn đạt limit | Đặt `LIMIT` trong SQL |
| SELECT toàn bộ entity dù chỉ cần vài cột | Network và object allocation lớn | Projection/DTO nhỏ |
| `collectList()` cho toàn bộ export rồi serialize | Heap tăng theo toàn bộ file | Export job theo page và writer streaming |
| Page size/concurrency do client tùy ý | Một request có thể làm cạn heap | Validate max page size và quota |
| Không đo heap sau GC | Nhầm allocation tạm với leak hoặc bỏ sót retained objects | Dùng JFR/heap dump/profiler |

## 22. Quy trình thiết kế pipeline có bộ nhớ hữu hạn

Khi xử lý một tập dữ liệu lớn, hãy đi theo các bước:

1. **Xác định kích thước:** ước lượng số hàng, kích thước row/DTO và số request đồng thời.
2. **Chọn projection:** chỉ SELECT các cột cần thiết; tránh tải LOB/JSON lớn nếu không dùng.
3. **Đẩy phép tính xuống database:** dùng `COUNT`, `SUM`, `GROUP BY`, `DISTINCT`, `EXISTS`, `ORDER BY` khi phù hợp.
4. **Giới hạn kết quả:** dùng SQL `LIMIT` và validate page size.
5. **Chọn streaming hoặc page:** streaming cho consumer nhanh và tập được kiểm soát; page cho dữ liệu lớn cần giải phóng query giữa các phần.
6. **Giới hạn buffer:** dùng `buffer(n)` hoặc `bufferTimeout` với capacity rõ ràng; tránh buffer không giới hạn.
7. **Giới hạn concurrency:** đặt max concurrency và prefetch theo heap/pool budget.
8. **Kiểm tra operator state:** tránh `collectList`, `sort`, `cache`, `distinct` hoặc `groupBy` trên nguồn lớn nếu không có giới hạn.
9. **Tách công việc chậm:** hoàn tất query page trước khi gọi service ngoài hoặc ghi file nếu có thể.
10. **Đo và kiểm thử:** dùng profiler, heap dump, load test và integration test với driver thật.

## 23. Nguyên tắc cần nhớ

- `Flux` không tự bảo đảm memory bounded; operator phía sau quyết định dữ liệu được giữ bao nhiêu.
- `collectList`, `collectMap`, `collectMultimap`, `sort`, `cache` và `replay` có thể giữ toàn bộ hoặc phần lớn nguồn.
- `distinct` và `groupBy` duy trì state theo cardinality; nguồn nhiều key có thể làm heap tăng.
- `reduce` chỉ tiết kiệm bộ nhớ khi accumulator có kích thước cố định.
- Dùng `buffer(n)` hoặc `bufferTimeout(maxSize, maxTime)` với giới hạn rõ ràng.
- Tránh `onBackpressureBuffer()` không giới hạn; ưu tiên backpressure và overflow policy phù hợp nghiệp vụ.
- Đặt concurrency/prefetch hữu hạn cho `flatMap`, `flatMapSequential` và `publishOn`.
- Đẩy filter, sort, aggregate và distinct xuống database khi phù hợp.
- Dùng projection để giảm kích thước mỗi hàng; chỉ đọc cột cần thiết.
- Dùng SQL `LIMIT` thay vì chỉ `.take(n)` sau một query không giới hạn.
- Dùng keyset pagination với cursor ổn định cho tập dữ liệu lớn.
- `buffer(n)` chia một result stream thành batch nhưng không tự tạo query mới hoặc release connection giữa batch.
- Thu thập một page nhỏ bằng `collectList()` có thể an toàn nếu page size bị giới hạn.
- Với export lớn, cân nhắc job nền, page query và writer streaming.
- Cache phải có giới hạn size/weight, TTL và invalidation; không cache Flux lớn vô thời hạn.
- Ước lượng bộ nhớ theo batch size, object size và concurrency; xác nhận bằng profiler.
- Kiểm thử downstream chậm, lượng dữ liệu lớn và nhiều request đồng thời.

Tránh gom toàn bộ Flux lớn vào bộ nhớ là vấn đề thiết kế toàn pipeline, không chỉ là xóa một lời gọi `collectList()`. Hãy giới hạn mọi nơi có thể tích lũy dữ liệu, giữ backpressure, dùng projection và aggregate ở database, rồi chia tập lớn thành page hoặc batch hữu hạn. Với các use case cần tải toàn bộ dữ liệu, export job và writer streaming giúp tách tốc độ database khỏi tốc độ client. Khi kết hợp giới hạn page/concurrency với đo heap và kiểm thử tải, ứng dụng R2DBC có thể xử lý tập dữ liệu lớn mà không để bộ nhớ tăng tỷ lệ thuận với toàn bộ kết quả.
