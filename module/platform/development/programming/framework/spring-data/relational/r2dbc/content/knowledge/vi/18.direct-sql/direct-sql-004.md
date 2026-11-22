# Phân biệt one, first, all và kết quả rỗng

Khi dùng Spring Framework DatabaseClient để chạy SQL trực tiếp trong ứng dụng Spring Data R2DBC, cần chọn đúng cách lấy kết quả theo số hàng mà câu query có thể trả về. Ba lựa chọn thường gặp là one(), first() và all(). Chúng đều đọc dữ liệu từ cùng một câu SQL nhưng có hợp đồng cardinality khác nhau:

- one(): chấp nhận tối đa một hàng; nếu không có hàng thì Mono hoàn tất rỗng, nếu có nhiều hơn một hàng thì phát lỗi sai số lượng kết quả.
- first(): lấy hàng đầu tiên được phát ra; không có hàng thì Mono hoàn tất rỗng. Nếu query trả nhiều hàng, các hàng sau không được trả cho caller.
- all(): lấy tất cả hàng dưới dạng Flux; không có hàng thì Flux hoàn tất mà không phát phần tử.

**Chọn API dựa trên cardinality mà nghiệp vụ mong đợi, không chọn chỉ vì muốn nhận Mono hay Flux.** one() giúp phát hiện query lẽ ra chỉ có một hàng nhưng lại trả nhiều hàng. first() phù hợp khi nghiệp vụ thật sự cần một hàng đầu tiên theo thứ tự đã định. all() dùng cho danh sách hoặc luồng nhiều hàng.

Một điểm quan trọng khác: kết quả rỗng không phải lỗi database. Mono.empty() và Flux.empty() biểu diễn query thành công nhưng không có hàng phù hợp. Chúng khác SQL NULL, khác lỗi SQL và khác trường hợp DML cập nhật 0 hàng.

## 1. DatabaseClient và FetchSpec

DatabaseClient cung cấp API reactive để chạy SQL trực tiếp mà không cần khai báo repository method cho từng câu lệnh. Sau khi bind tham số và ánh xạ Row, ứng dụng chọn cách lấy dữ liệu qua các phương thức trong RowsFetchSpec/FetchSpec.

Ví dụ query một khách hàng:

~~~java
Mono<CustomerView> customer = databaseClient
        .sql("""
             SELECT id, display_name, email_address
             FROM customers
             WHERE id = :id
             """)
        .bind("id", customerId)
        .map((row, metadata) -> new CustomerView(
                row.get("id", Long.class),
                row.get("display_name", String.class),
                row.get("email_address", String.class)))
        .one();
~~~

Đoạn code trên tạo một publisher; query chỉ được thực thi khi có subscription. one() quyết định cách xử lý số hàng được trả về.

### 1.1. Các lựa chọn cơ bản

| Phương thức | Kiểu trả về | Không có hàng | Có nhiều hàng |
| --- | --- | --- | --- |
| one() | Mono<T> | Mono hoàn tất rỗng | Phát lỗi sai số lượng kết quả |
| first() | Mono<T> | Mono hoàn tất rỗng | Chỉ trả hàng đầu tiên |
| all() | Flux<T> | Flux hoàn tất rỗng | Trả tất cả hàng |

Ở đây T là kiểu mà mapper tạo ra. Nếu không dùng map(), FetchSpec có thể trả dữ liệu dạng Map<String, Object>.

### 1.2. FetchSpec không thay đổi SQL

one(), first() và all() là lựa chọn tiêu thụ kết quả ở phía API. Chúng không tự viết lại câu SQL để thêm điều kiện WHERE, ORDER BY hoặc LIMIT.

Nếu query có thể trả hàng triệu bản ghi, gọi first() không thay thế thiết kế SQL phù hợp. Nếu chỉ cần một hàng mới nhất, hãy đưa ORDER BY và LIMIT vào SQL để database có thể chọn đúng hàng và giảm công việc.

## 2. one(): yêu cầu query trả tối đa một hàng

one() phù hợp khi câu query có hợp đồng tối đa một hàng. Ví dụ:

- Tìm theo primary key.
- Tìm theo cột có unique constraint.
- Đọc một cấu hình duy nhất theo tenant và key.
- Lấy một bản ghi theo ID và tenant.

Ví dụ:

~~~java
public Mono<CustomerView> findCustomer(Long id) {
    return databaseClient
            .sql("""
                 SELECT id, display_name, email_address
                 FROM customers
                 WHERE id = :id
                 """)
            .bind("id", id)
            .map((row, metadata) -> new CustomerView(
                    row.get("id", Long.class),
                    row.get("display_name", String.class),
                    row.get("email_address", String.class)))
            .one();
}
~~~

Vì id là primary key, database bảo đảm query không trả nhiều hơn một hàng. Nếu không có ID đó, publisher hoàn tất rỗng.

### 2.1. one() phát lỗi khi có nhiều hơn một hàng

Giả sử query tìm theo email nhưng database không có unique constraint:

~~~sql
SELECT id, email_address
FROM customers
WHERE email_address = :email
~~~

Nếu dữ liệu hiện có hai khách hàng dùng cùng email, one() không âm thầm chọn một hàng. Nó phát lỗi sai số lượng kết quả, thường được Spring chuyển thành IncorrectResultSizeDataAccessException.

Đây là một tín hiệu hữu ích: query hoặc dữ liệu không đáp ứng hợp đồng tối đa một hàng mà code đang yêu cầu.

Không nên bắt lỗi này rồi chuyển thành Mono.empty(), vì như vậy ứng dụng che giấu lỗi dữ liệu trùng lặp.

### 2.2. one() không có nghĩa là bắt buộc phải có đúng một hàng

Trong FetchSpec của DatabaseClient, one() cho phép không có hàng và biểu diễn trường hợp đó bằng Mono.empty(). Nó kiểm soát trường hợp có nhiều hàng bằng lỗi.

Nếu use case yêu cầu đúng một khách hàng phải tồn tại, hãy xử lý empty rõ ràng:

~~~java
public Mono<CustomerView> requireCustomer(Long id) {
    return findCustomer(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Như vậy có hai quy tắc độc lập:

- one() bảo vệ cardinality tối đa một hàng.
- switchIfEmpty() biến trường hợp không có hàng thành lỗi nghiệp vụ nếu use case yêu cầu resource phải tồn tại.

### 2.3. Bảo vệ tính duy nhất ở database

Nếu nghiệp vụ yêu cầu email duy nhất trong toàn hệ thống:

~~~sql
CREATE UNIQUE INDEX uk_customers_email
ON customers (email_address);
~~~

Nếu email chỉ cần duy nhất trong từng tenant:

~~~sql
CREATE UNIQUE INDEX uk_customers_tenant_email
ON customers (tenant_id, email_address);
~~~

one() là lớp kiểm tra cardinality khi đọc. Unique constraint mới là cơ chế database bảo vệ tính duy nhất trước các request đồng thời và dữ liệu ghi từ nhiều nguồn.

## 3. first(): lấy hàng đầu tiên trong kết quả

first() phù hợp khi query có thể trả nhiều hàng nhưng use case chỉ cần một hàng đầu tiên theo một thứ tự xác định.

Ví dụ lấy sự kiện gần nhất của một khách hàng:

~~~java
public Mono<CustomerEvent> findLatestEvent(Long customerId) {
    return databaseClient
            .sql("""
                 SELECT id, customer_id, event_type, created_at
                 FROM customer_events
                 WHERE customer_id = :customerId
                 ORDER BY created_at DESC, id DESC
                 LIMIT 1
                 """)
            .bind("customerId", customerId)
            .map((row, metadata) -> new CustomerEvent(
                    row.get("id", Long.class),
                    row.get("customer_id", Long.class),
                    row.get("event_type", String.class),
                    row.get("created_at", LocalDateTime.class)))
            .first();
}
~~~

ORDER BY created_at DESC chọn sự kiện mới nhất. id DESC là tie-breaker để thứ tự vẫn xác định khi hai sự kiện có cùng timestamp. LIMIT 1 yêu cầu database chỉ cần trả tối đa một hàng.

### 3.1. first() không bảo đảm thứ tự nghiệp vụ

Nếu query không có ORDER BY, database không bảo đảm hàng nào sẽ xuất hiện đầu tiên. Kết quả có thể thay đổi theo execution plan, index, dữ liệu, vacuum, phân vùng hoặc phiên bản database.

Không nên viết:

~~~sql
SELECT id, status
FROM orders
WHERE customer_id = :customerId
~~~

rồi dùng first() với ý định lấy order mới nhất. Query không chỉ định “mới nhất” là gì.

Hãy viết:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT 1
~~~

### 3.2. first() không thay thế LIMIT

first() chọn phần tử đầu tiên từ result publisher. Nó không tự thêm LIMIT 1 vào câu SQL. Driver có thể hủy việc đọc phần còn lại sau khi lấy được hàng đầu tiên, nhưng điều đó không đồng nghĩa database đã tránh được toàn bộ công việc để tạo kết quả.

Với query có thể trả nhiều hàng, hãy dùng LIMIT/FETCH FIRST/TOP theo dialect khi nghiệp vụ chỉ cần một hàng. Cú pháp giới hạn hàng khác nhau giữa database.

### 3.3. first() có thể che giấu dữ liệu trùng

Nếu query lẽ ra chỉ có một hàng nhưng dữ liệu trùng do thiếu constraint, first() vẫn trả một hàng và bỏ qua phần còn lại. Điều này có thể che giấu lỗi dữ liệu.

Ví dụ tìm cấu hình theo tenant và key:

~~~sql
SELECT config_value
FROM tenant_settings
WHERE tenant_id = :tenantId
  AND setting_key = :key
~~~

Nếu mỗi tenant chỉ được có một setting cho một key, hãy dùng one() và unique constraint trên (tenant_id, setting_key). Dùng first() ở đây có thể làm ứng dụng tiếp tục chạy với một giá trị tùy ý.

## 4. all(): lấy toàn bộ hàng dưới dạng Flux

all() phù hợp với query danh sách:

~~~java
public Flux<CustomerView> findActiveCustomers() {
    return databaseClient
            .sql("""
                 SELECT id, display_name, email_address
                 FROM customers
                 WHERE active = :active
                 ORDER BY display_name, id
                 """)
            .bind("active", true)
            .map((row, metadata) -> new CustomerView(
                    row.get("id", Long.class),
                    row.get("display_name", String.class),
                    row.get("email_address", String.class)))
            .all();
}
~~~

all() phát từng hàng theo reactive stream. Nếu query không tìm thấy hàng nào, Flux hoàn tất rỗng.

### 4.1. Flux rỗng là kết quả danh sách hợp lệ

Một endpoint danh sách khách hàng đang hoạt động có thể trả về collection rỗng khi không có khách hàng nào thỏa điều kiện. Điều đó thường là kết quả thành công, không phải 404.

Ví dụ:

~~~java
return customerService.findActiveCustomers()
        .collectList()
        .map(ResponseEntity::ok);
~~~

Nếu Flux không có phần tử, collectList() phát một Mono chứa List rỗng. Mono đó vẫn phát một giá trị List và hoàn tất, không phải Mono.empty().

### 4.2. Không collect toàn bộ dữ liệu lớn một cách tùy tiện

Đoạn code:

~~~java
return databaseClient.sql("SELECT * FROM audit_events")
        .map((row, metadata) -> mapEvent(row))
        .all()
        .collectList();
~~~

giữ toàn bộ kết quả trong memory. Với bảng lớn, heap có thể tăng mạnh, gây garbage collection và làm chậm toàn hệ thống.

Hãy cân nhắc:

- Pagination với ORDER BY ổn định.
- Giới hạn thời gian/phạm vi dữ liệu.
- Streaming response nếu API và client hỗ trợ.
- Xử lý từng batch.
- Backpressure và concurrency giới hạn.

all() tạo Flux nhưng không tự bảo đảm ứng dụng sử dụng memory hữu hạn nếu downstream gọi collectList() hoặc giữ mọi phần tử.

### 4.3. all() không có thứ tự nếu SQL không chỉ định

Flux phát các hàng theo thứ tự result stream của database. Nếu nghiệp vụ cần thứ tự cụ thể, phải thêm ORDER BY. Không dựa vào thứ tự vật lý của bảng hoặc thứ tự insert.

## 5. Kết quả rỗng: Mono.empty() và Flux.empty()

Trong reactive programming, publisher có thể hoàn tất theo ba cách chính:

- Phát một hoặc nhiều giá trị rồi complete.
- Complete mà không phát giá trị.
- Phát error.

Với query SQL:

| SQL result | API thường biểu diễn |
| --- | --- |
| Query one() tìm thấy một hàng | Mono phát một object rồi complete |
| Query one() không tìm thấy hàng | Mono.empty() |
| Query one() trả nhiều hơn một hàng | Error do sai cardinality |
| Query first() tìm thấy hàng | Mono phát hàng đầu tiên |
| Query first() không có hàng | Mono.empty() |
| Query all() có nhiều hàng | Flux phát từng hàng |
| Query all() không có hàng | Flux.empty() |
| Database/SQL gặp lỗi | Publisher phát error |

### 5.1. Empty không phải null

Reactor không cho phép Mono phát một giá trị Java null. Mono.empty() là publisher không phát giá trị nào.

Một hàng database có thể tồn tại nhưng một cột nullable chứa SQL NULL. Khi đó mapper nên tạo một object có property tương ứng là null:

~~~java
public record CustomerView(
        Long id,
        String displayName,
        String nickname) {
}

Mono<CustomerView> result = databaseClient
        .sql("""
             SELECT id, display_name, nickname
             FROM customers
             WHERE id = :id
             """)
        .bind("id", id)
        .map((row, metadata) -> new CustomerView(
                row.get("id", Long.class),
                row.get("display_name", String.class),
                row.get("nickname", String.class)))
        .one();
~~~

Nếu hàng tồn tại nhưng nickname là SQL NULL, Mono vẫn phát CustomerView; field nickname của object là null. Nếu không có hàng, Mono hoàn tất rỗng.

### 5.2. Đừng biến SQL NULL thành empty một cách vô tình

Tránh map một cột nullable trực tiếp thành publisher rỗng:

~~~java
.flatMap(row -> Mono.justOrEmpty(
        row.get("nickname", String.class)))
~~~

Nếu nickname là SQL NULL, Mono.justOrEmpty() tạo Mono.empty(). Điều đó làm mất phân biệt giữa “không có hàng” và “có hàng nhưng cột nickname null”.

Nếu cần giữ cả hai ý nghĩa, map thành DTO hoặc record chứa field nullable:

~~~java
.map((row, metadata) -> new CustomerNickname(
        row.get("id", Long.class),
        row.get("nickname", String.class)))
~~~

Mapper phải trả một object không null. Các field bên trong object có thể nullable theo schema/domain.

### 5.3. Empty không kích hoạt onErrorResume

Đoạn code:

~~~java
return findCustomer(id)
        .onErrorResume(error -> Mono.just(fallbackCustomer));
~~~

chỉ chạy fallback khi publisher phát error. Nếu query không tìm thấy hàng và trả Mono.empty(), onErrorResume không chạy.

Dùng switchIfEmpty() hoặc defaultIfEmpty() cho trường hợp không có giá trị.

## 6. Xử lý empty bằng switchIfEmpty và defaultIfEmpty

switchIfEmpty() thay publisher rỗng bằng một publisher khác:

~~~java
public Mono<CustomerView> requireCustomer(Long id) {
    return findCustomer(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

defaultIfEmpty() phát một giá trị mặc định:

~~~java
public Mono<CustomerView> findOrFallback(Long id) {
    return findCustomer(id)
            .defaultIfEmpty(CustomerView.notFound());
}
~~~

Chọn cách nào phụ thuộc hợp đồng:

- Resource bắt buộc phải tồn tại: thường dùng switchIfEmpty(Mono.error(...)).
- Có giá trị fallback nghiệp vụ hợp lệ: dùng defaultIfEmpty(...).
- API danh sách: thường giữ Flux rỗng hoặc collectList() thành list rỗng.

### 6.1. Dùng switchIfEmpty cho Flux

~~~java
public Flux<CustomerView> findActiveOrDefaults() {
    return findActiveCustomers()
            .switchIfEmpty(Flux.just(defaultCustomer()));
}
~~~

Đoạn code trên chỉ phát defaultCustomer khi không có bất kỳ hàng nào. Nếu có một hoặc nhiều hàng, fallback không chạy.

Không nên tự động chèn một phần tử giả vào mọi danh sách rỗng nếu API có quy ước collection rỗng rõ ràng.

### 6.2. Dùng defer khi tạo fallback có side effect

Nếu fallback cần gọi service khác hoặc ghi metric, dùng publisher lazy:

~~~java
return findCustomer(id)
        .switchIfEmpty(Mono.defer(() -> {
            metrics.incrementCustomerNotFound();
            return Mono.error(new CustomerNotFoundException(id));
        }));
~~~

Mono.defer() bảo đảm publisher fallback chỉ được tạo khi nguồn thực sự hoàn tất rỗng. Tránh gọi service/side effect ngay khi xây dựng pipeline nếu nó chỉ nên xảy ra trong trường hợp empty.

## 7. Chọn one(), first() hay all() theo hợp đồng dữ liệu

Một cách quyết định:

| Nhu cầu nghiệp vụ | Lựa chọn | Điều kiện SQL/schema |
| --- | --- | --- |
| Đọc theo primary key | one() | Predicate trên PK |
| Đọc theo unique business key | one() | Unique constraint bảo đảm tối đa một hàng |
| Đọc bản ghi mới nhất | first() | ORDER BY rõ ràng và LIMIT 1 |
| Lấy một mẫu bất kỳ có chủ đích | first() | Chấp nhận quy tắc chọn và có ORDER BY nếu cần ổn định |
| Danh sách tìm kiếm | all() | Có filter, sort và pagination/limit phù hợp |
| Báo cáo nhiều hàng | all() | Streaming hoặc batch, tránh collect không giới hạn |
| Đọc một resource bắt buộc | one() + switchIfEmpty(error) | PK/unique predicate và not-found contract |
| Chỉ cần biết có bản ghi hay không | Query EXISTS hoặc one() | Chọn query nhẹ theo database |

### 7.1. Đọc theo ID

~~~java
Mono<Order> findById(Long id) {
    return databaseClient.sql("""
            SELECT id, status, total_amount
            FROM orders
            WHERE id = :id
            """)
            .bind("id", id)
            .map((row, metadata) -> mapOrder(row))
            .one();
}
~~~

Primary key làm query có tối đa một hàng. Nếu không có ID, publisher empty; service hoặc controller quyết định trả 404 hay một kết quả absence theo API contract.

### 7.2. Đọc bản ghi mới nhất

~~~java
Mono<OrderEvent> latestEvent(Long orderId) {
    return databaseClient.sql("""
            SELECT id, event_type, created_at
            FROM order_events
            WHERE order_id = :orderId
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """)
            .bind("orderId", orderId)
            .map((row, metadata) -> mapOrderEvent(row))
            .first();
}
~~~

Query này có thể trả 0 hoặc 1 hàng do LIMIT. first() biểu diễn ý định lấy hàng đầu tiên. one() cũng có thể dùng khi SQL đã bảo đảm tối đa một hàng; chọn một cách và giữ nhất quán.

### 7.3. Lấy danh sách có giới hạn

~~~java
Flux<OrderSummary> findRecentOrders(Long customerId, int pageSize) {
    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE customer_id = :customerId
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
            .bind("customerId", customerId)
            .bind("pageSize", pageSize)
            .map((row, metadata) -> mapOrderSummary(row))
            .all();
}
~~~

pageSize cần được validate ở application layer để không cho client yêu cầu một giới hạn quá lớn. Với pagination nhiều trang, nên dùng cursor/keyset pagination nếu offset lớn hoặc dữ liệu thay đổi liên tục.

## 8. Hành vi khi query trả nhiều hàng ngoài dự kiến

Đây là khác biệt quan trọng giữa one() và first():

~~~text
Query result: [row A, row B, row C]

one():
  phát lỗi cardinality vì có hơn một hàng

first():
  phát row A rồi hoàn tất

all():
  phát row A, row B, row C rồi hoàn tất
~~~

### 8.1. one() phát hiện lỗi dữ liệu/query

Nếu query tìm user theo email mà email được kỳ vọng unique, one() giúp phát hiện khi database có duplicate. Cần xử lý lỗi như một lỗi integrity/query contract và điều tra constraint/migration.

Không đổi sang first() chỉ để làm lỗi biến mất. Việc đó có thể khiến ứng dụng lấy nhầm user, cấu hình hoặc resource.

### 8.2. first() là lựa chọn có chủ đích

first() hợp lý khi nghiệp vụ yêu cầu một phần tử đại diện từ nhiều kết quả, chẳng hạn sự kiện mới nhất, giá tốt nhất hoặc một candidate theo thứ tự ưu tiên.

Thứ tự phải được định nghĩa trong SQL. Nếu hai hàng có cùng giá trị sort, thêm tie-breaker để kết quả ổn định.

### 8.3. all() giữ toàn bộ cardinality

all() phù hợp khi caller cần toàn bộ tập kết quả của query. Nếu chỉ cần kiểm tra tồn tại, không cần lấy mọi hàng rồi đếm. Hãy dùng EXISTS hoặc COUNT tùy mục đích.

## 9. DML và kết quả 0 hàng: rowsUpdated() khác all()/one()

INSERT, UPDATE và DELETE thường không trả row data. Với câu lệnh DML không có result set, dùng rowsUpdated() để nhận số hàng bị tác động:

~~~java
Mono<Integer> updateOrderStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE orders
            SET status = :status
            WHERE id = :id
            """)
            .bind("status", status)
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
~~~

Nếu không có hàng nào được cập nhật, publisher vẫn phát số 0 rồi complete. Đây không phải Mono.empty().

### 9.1. Phân biệt ba kết quả

| Tình huống | Publisher |
| --- | --- |
| UPDATE tác động 3 hàng | Mono phát 3 |
| UPDATE không khớp hàng nào | Mono phát 0 |
| Database phát lỗi constraint/connection | Mono phát error |

Service có thể diễn giải số hàng:

~~~java
return updateOrderStatus(id, status)
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.just(UpdateResult.updated());
            }
            if (rows == 0) {
                return Mono.just(UpdateResult.notFound());
            }
            return Mono.error(new UnexpectedUpdateCountException(rows));
        });
~~~

Nếu câu UPDATE có thể tác động nhiều hàng theo thiết kế, hãy đặt ngưỡng và semantics phù hợp thay vì giả định luôn bằng 1.

### 9.2. UPDATE có điều kiện

Một câu lệnh có thể dùng predicate version hoặc trạng thái:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND status = 'DRAFT'
~~~

rowsUpdated() bằng 0 có thể có nghĩa order không tồn tại, version đã thay đổi hoặc trạng thái không còn là DRAFT. Cần xác định API có phân biệt các trường hợp đó hay trả một kết quả conflict chung.

### 9.3. SQL có RETURNING

Một số database hỗ trợ DML trả về hàng, ví dụ PostgreSQL INSERT/UPDATE ... RETURNING. Khi đó dùng row mapping và one()/first()/all() theo cardinality của result set:

~~~java
Mono<Order> updateAndReturn(Long id, String status) {
    return databaseClient.sql("""
            UPDATE orders
            SET status = :status
            WHERE id = :id
            RETURNING id, status
            """)
            .bind("status", status)
            .bind("id", id)
            .map((row, metadata) -> mapOrder(row))
            .one();
}
~~~

Nếu không có hàng phù hợp, result publisher rỗng. Cú pháp RETURNING và khả năng hỗ trợ phụ thuộc database/driver; không giả định mọi hệ quản trị có cùng cú pháp.

## 10. Đếm hàng và kiểm tra tồn tại

Nếu chỉ cần biết có hàng phù hợp hay không, có thể dùng EXISTS:

~~~java
Mono<Boolean> customerExists(Long id) {
    return databaseClient.sql("""
            SELECT EXISTS (
                SELECT 1
                FROM customers
                WHERE id = :id
            ) AS present
            """)
            .bind("id", id)
            .map((row, metadata) -> Boolean.TRUE.equals(
                    row.get("present", Boolean.class)))
            .one();
}
~~~

Với aggregate không có GROUP BY, COUNT thường trả đúng một hàng kể cả khi không có bản ghi phù hợp:

~~~sql
SELECT COUNT(*) AS total
FROM orders
WHERE status = :status
~~~

Khi không có order phù hợp, hàng aggregate vẫn tồn tại và total là 0. Vì vậy one() sẽ phát một object/count có giá trị 0, không phải Mono.empty().

### 10.1. EXISTS và COUNT có mục đích khác nhau

- EXISTS trả lời có ít nhất một hàng hay không; database có thể dừng khi tìm thấy hàng phù hợp.
- COUNT trả tổng số hàng; database thường cần xác định toàn bộ số lượng phù hợp theo query plan.

Nếu chỉ cần boolean, EXISTS thường diễn đạt đúng ý định hơn COUNT > 0. Tuy nhiên hiệu năng cuối cùng phụ thuộc optimizer, index và database.

## 11. Mapping hàng và xử lý cột nullable

DatabaseClient có thể trả Map hoặc map Row sang DTO/domain object. Chọn mapping rõ ràng giúp tránh nhầm empty result với SQL NULL.

### 11.1. Map sang DTO

~~~java
public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        String description) {
}

Mono<ProductView> findProduct(Long id) {
    return databaseClient.sql("""
            SELECT id, name, price, description
            FROM products
            WHERE id = :id
            """)
            .bind("id", id)
            .map((row, metadata) -> new ProductView(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("price", BigDecimal.class),
                    row.get("description", String.class)))
            .one();
}
~~~

description có thể null nếu schema cho phép. ProductView vẫn là object hợp lệ.

### 11.2. Cột không tồn tại khác cột có giá trị null

Nếu SQL SELECT không đưa cột vào projection, mapper không nên cố đọc cột đó. Nếu cột có trong result set nhưng giá trị SQL NULL, row.get() trả null cho property tương ứng. Cần phân biệt lỗi mapping do tên cột sai với dữ liệu nullable.

### 11.3. Tên cột và alias

Khi dùng aggregate, expression hoặc tên cột trùng nhau trong JOIN, đặt alias rõ:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       COUNT(o.id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.id = :id
GROUP BY c.id, c.name
~~~

Mapper dùng đúng alias để đọc. Tên column label có thể phụ thuộc database/dialect nếu không đặt alias rõ ràng.

## 12. Phân trang và thứ tự ổn định với all()

all() phát mọi hàng mà câu SQL trả về. Đối với API list, câu SQL nên có giới hạn và thứ tự rõ ràng.

### 12.1. Offset pagination

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset
~~~

Cách này dễ hiểu nhưng offset lớn có thể khiến database phải bỏ qua nhiều hàng. Dữ liệu thay đổi giữa các trang cũng có thể làm trùng hoặc thiếu phần tử.

### 12.2. Keyset pagination

Với sort giảm dần theo created_at và id:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
~~~

Client gửi cursor của hàng cuối trang trước. Cặp sort key phải tạo thứ tự ổn định và có index phù hợp.

### 12.3. Không dùng first() để giả lập pagination

first() chỉ trả một hàng đầu tiên. Nó không cung cấp cursor, page boundary hoặc tổng số hàng. Nếu nghiệp vụ là danh sách có phân trang, dùng all() với SQL limit/cursor và trả metadata pagination riêng.

## 13. Kết hợp one()/first()/all() với HTTP API

Hợp đồng HTTP thường tương ứng:

| Endpoint | Kiểu truy vấn | Kết quả rỗng thường gặp |
| --- | --- | --- |
| GET /customers/{id} | one() | 404 nếu resource bắt buộc phải tồn tại |
| GET /customers?active=true | all() | 200 với mảng rỗng |
| GET /orders/latest | first() | 404 hoặc 204 theo API contract |
| GET /customers/exists/{id} | EXISTS + one() | 200 với false |
| PATCH /orders/{id} | DML + rowsUpdated() hoặc RETURNING | 404/409 theo điều kiện cập nhật |

### 13.1. Resource đơn

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<CustomerView>> getCustomer(
        @PathVariable Long id) {

    return customerService.findCustomer(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

### 13.2. Collection

~~~java
@GetMapping
public Mono<ResponseEntity<List<CustomerView>>> listCustomers() {
    return customerService.findActiveCustomers()
            .collectList()
            .map(ResponseEntity::ok);
}
~~~

Nếu không có hàng, endpoint trả 200 với list rỗng. Với collection rất lớn, không collect toàn bộ; dùng pagination hoặc streaming response phù hợp.

### 13.3. 204 No Content

204 có thể phù hợp khi endpoint thành công nhưng không cần response body, ví dụ một lệnh DELETE thành công. Đừng dùng 204 chỉ vì SELECT không tìm thấy hàng nếu API contract quy định 404.

## 14. Các lỗi thường gặp khi chọn sai phương thức

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query trả duplicate nhưng không thấy lỗi | Dùng first() cho query cần duy nhất | Dùng one() và unique constraint |
| one() phát IncorrectResultSizeDataAccessException | Query trả hơn một hàng | Kiểm tra predicate, JOIN và constraint |
| Không tìm thấy resource nhưng API không vào onErrorResume | Empty không phải error | Dùng switchIfEmpty/defaultIfEmpty |
| SQL NULL bị coi là không có hàng | Map nullable column thành Mono.empty() | Map thành DTO có field nullable |
| Danh sách rỗng bị trả 404 | Nhầm Flux.empty() với resource đơn | Trả 200 và collection rỗng |
| first() trả hàng khác nhau giữa các lần | Query không có ORDER BY ổn định | Thêm ORDER BY và tie-breaker |
| first() vẫn tốn query lớn | Nghĩ first() tự thêm LIMIT | Thêm LIMIT/FETCH FIRST/TOP trong SQL |
| all() làm heap tăng mạnh | collectList() dữ liệu không giới hạn | Pagination, batch hoặc streaming |
| UPDATE không tìm thấy hàng bị hiểu là empty | Dùng nhầm row fetch thay vì rowsUpdated | Kiểm tra số hàng bị tác động |
| COUNT bằng 0 nhưng publisher không empty | Aggregate vẫn trả một hàng | Đọc count = 0 như kết quả hợp lệ |
| JOIN làm one() báo nhiều hàng | Một entity có nhiều row con | Dùng aggregate, projection phù hợp hoặc all() |
| Thứ tự danh sách không ổn định | Dựa vào thứ tự vật lý của database | Thêm ORDER BY rõ ràng |

## 15. Kiểm thử cardinality và kết quả rỗng bằng StepVerifier

StepVerifier giúp xác nhận publisher phát bao nhiêu phần tử, complete hay error.

### 15.1. one() không tìm thấy hàng

~~~java
StepVerifier.create(repositoryClient.findCustomer(999L))
        .verifyComplete();
~~~

Test xác nhận Mono hoàn tất mà không phát phần tử.

### 15.2. one() có một hàng

~~~java
StepVerifier.create(repositoryClient.findCustomer(10L))
        .assertNext(customer ->
                assertThat(customer.id()).isEqualTo(10L))
        .verifyComplete();
~~~

### 15.3. one() có nhiều hàng

Chuẩn bị dữ liệu khiến query trả hai hàng và xác nhận publisher phát lỗi cardinality. Tùy phiên bản Spring và đường exception translation, hãy kiểm tra đúng exception contract mà ứng dụng expose; thường là IncorrectResultSizeDataAccessException.

Không viết test chỉ kiểm tra có bất kỳ error nào nếu mục tiêu là bảo vệ duplicate-row behavior.

### 15.4. first() lấy hàng theo thứ tự

Chuẩn bị ba hàng có timestamp khác nhau. Gọi query có ORDER BY created_at DESC, id DESC và first(). Xác nhận hàng mới nhất được phát.

Sau đó thêm hai hàng cùng timestamp để xác nhận tie-breaker id làm kết quả ổn định.

### 15.5. all() rỗng

~~~java
StepVerifier.create(repositoryClient.findCustomersByStatus("UNKNOWN"))
        .verifyComplete();
~~~

Flux rỗng hoàn tất ngay và không phát phần tử.

### 15.6. collectList() trên Flux rỗng

~~~java
StepVerifier.create(repositoryClient
                .findCustomersByStatus("UNKNOWN")
                .collectList())
        .assertNext(list -> assertThat(list).isEmpty())
        .verifyComplete();
~~~

Test này chứng minh collectList() phát một List rỗng, không phải Mono.empty().

### 15.7. SQL NULL và không có hàng

Tạo hai trường hợp:

1. Một hàng tồn tại với nickname SQL NULL.
2. Không có hàng nào thỏa ID.

Với trường hợp đầu, xác nhận Mono phát DTO và DTO.nickname là null. Với trường hợp thứ hai, xác nhận Mono hoàn tất rỗng.

### 15.8. rowsUpdated() bằng 0

~~~java
StepVerifier.create(repositoryClient.updateStatus(999L, "CLOSED"))
        .expectNext(0)
        .verifyComplete();
~~~

Kiểu số cụ thể phụ thuộc API/version; ý nghĩa cần kiểm tra là publisher phát số hàng bị tác động bằng 0.

## 16. Integration test nên chạy trên database thật

Mock DatabaseClient có thể kiểm tra cách service nối publisher, nhưng không xác nhận:

- Driver thực sự trả số hàng như mong đợi.
- Database xử lý LIMIT/ORDER BY đúng.
- JOIN tạo cardinality như dự kiến.
- Unique constraint ngăn duplicate.
- SQL NULL được map đúng.
- DML trả đúng rows updated.

Với query quan trọng, dùng Testcontainers hoặc database test cùng loại production. Chuẩn bị dữ liệu fixture rõ ràng, chạy query thật và kiểm tra publisher bằng StepVerifier.

### 16.1. Kiểm tra duplicate bằng unique constraint

Thử insert hai customer có cùng email. Xác nhận database từ chối insert thứ hai. Sau đó query bằng one() vẫn chỉ trả tối đa một hàng.

### 16.2. Kiểm tra JOIN

Một customer có nhiều order sẽ tạo nhiều hàng nếu query join customer và order. Nếu dùng one() để map CustomerView, query có thể phát lỗi cardinality dù chỉ có một customer.

Các lựa chọn:

- Query riêng customer và query riêng order.
- Dùng aggregate để gom các order.
- Dùng all() và group/assemble kết quả có kiểm soát.
- Chỉ select một row đại diện nếu nghiệp vụ thực sự cần một row.

Không dùng first() để che việc JOIN đang tạo nhiều hàng ngoài ý muốn.

## 17. JOIN và cardinality: một entity có thể tạo nhiều hàng

Ví dụ:

~~~sql
SELECT c.id AS customer_id,
       c.display_name,
       o.id AS order_id
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE c.id = :customerId
~~~

Nếu customer có ba order, result set có ba hàng. one() sẽ thấy ba hàng và phát lỗi, dù mục tiêu của lập trình viên có thể là lấy một customer.

### 17.1. Chỉ đọc parent nếu không cần child

~~~sql
SELECT c.id, c.display_name
FROM customers c
WHERE c.id = :customerId
~~~

Query không join bảng con nên có cardinality theo primary key.

### 17.2. Dùng aggregate cho child collection

Tùy database, có thể dùng JSON/array aggregation hoặc query riêng cho collection con. Hãy kiểm tra native type mapping và tránh làm query khó bảo trì nếu chỉ cần hai query đơn giản.

### 17.3. Dùng all() khi mỗi hàng là một kết quả cần xử lý

Nếu mục tiêu là liệt kê order của customer, all() đúng semantics:

~~~java
Flux<OrderView> findOrders(Long customerId) {
    return databaseClient.sql("""
            SELECT id, status, total_amount
            FROM orders
            WHERE customer_id = :customerId
            ORDER BY id
            """)
            .bind("customerId", customerId)
            .map((row, metadata) -> mapOrderView(row))
            .all();
}
~~~

## 18. Chú ý khi kết hợp với Optional và kiểu trả về của service

Mono.empty() và Optional.empty() có thể diễn đạt absence ở hai tầng khác nhau. Không cần bọc Optional trong Mono nếu service đã dùng Mono để biểu diễn không có kết quả.

Ví dụ:

~~~java
Mono<CustomerView> findCustomer(Long id);
~~~

đã đủ để biểu diễn một hoặc không có customer. Nếu muốn đưa absence thành giá trị tường minh:

~~~java
Mono<Optional<CustomerView>> findCustomerOptional(Long id) {
    return findCustomer(id)
            .map(Optional::of)
            .defaultIfEmpty(Optional.empty());
}
~~~

Cách này có thể hữu ích ở ranh giới API nội bộ imperative, nhưng thường không cần thiết trong reactive service vì nó tạo hai lớp biểu diễn absence.

Không bao giờ phát null qua Mono.just(null). Dùng Mono.empty() khi publisher không có giá trị, hoặc phát một object hợp lệ có field nullable.

## 19. Checklist chọn phương thức

- [ ] Query có thể trả tối đa một hàng? Dùng one().
- [ ] Database có primary key hoặc unique constraint bảo đảm cardinality?
- [ ] Nếu query trả nhiều hàng là lỗi, có giữ lỗi one() để phát hiện không?
- [ ] Chỉ cần hàng đầu tiên theo thứ tự nghiệp vụ? Dùng first().
- [ ] SQL có ORDER BY ổn định và tie-breaker chưa?
- [ ] Đã thêm LIMIT/FETCH FIRST/TOP để giới hạn công việc phía database chưa?
- [ ] Cần toàn bộ tập kết quả? Dùng all().
- [ ] Danh sách có giới hạn/pagination hoặc streaming phù hợp không?
- [ ] Empty Mono/Flux được xử lý theo API contract chưa?
- [ ] SQL NULL được phân biệt với không có hàng chưa?
- [ ] onErrorResume có đang bị dùng nhầm để xử lý empty không?
- [ ] DML dùng rowsUpdated() nếu chỉ cần số hàng bị tác động?
- [ ] UPDATE 0 hàng được phân biệt với query rỗng chưa?
- [ ] JOIN có thể làm tăng cardinality ngoài dự kiến không?
- [ ] Integration test đã xác nhận hành vi bằng database thật chưa?

## 20. Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    A[Chạy SQL và nhận result set] --> B{Nghiệp vụ cần bao nhiêu hàng?}
    B -->|Tối đa một hàng| C[one()]
    C --> D{Có hàng?}
    D -->|Không| E[Mono.empty()]
    D -->|Một hàng| F[Mono phát object]
    D -->|Nhiều hàng| G[Cardinality error]
    B -->|Một hàng đầu tiên có chủ đích| H[ORDER BY + LIMIT 1 + first()]
    H --> I{Có hàng?}
    I -->|Không| E
    I -->|Có| F
    B -->|Tất cả hàng| J[all()]
    J --> K{Có hàng?}
    K -->|Không| L[Flux.empty()]
    K -->|Có| M[Flux phát từng hàng]
    N[DML không trả row] --> O[rowsUpdated()]
    O --> P[Mono phát số hàng bị tác động, kể cả 0]
~~~

## 21. Kết luận

one(), first() và all() mô tả ba hợp đồng cardinality khác nhau khi đọc SQL bằng DatabaseClient. one() phù hợp với query tối đa một hàng và giúp phát hiện duplicate; first() lấy hàng đầu tiên theo result order nên cần ORDER BY ổn định và thường cần LIMIT 1 trong SQL; all() trả toàn bộ hàng dưới dạng Flux và cần pagination hoặc streaming phù hợp với tập dữ liệu lớn.

Kết quả không có hàng được biểu diễn bằng Mono.empty() hoặc Flux.empty(), không phải lỗi SQL. SQL NULL là một giá trị của hàng đã tồn tại; hãy map nó thành field nullable trong object thay vì biến nó thành publisher rỗng. switchIfEmpty/defaultIfEmpty xử lý absence, còn onErrorResume xử lý error signal. Với DML, rowsUpdated() phát số hàng bị tác động, và giá trị 0 là một kết quả cụ thể chứ không phải empty.

Hãy để query SQL và schema bảo đảm cardinality: primary key/unique constraint cho one(), ORDER BY/LIMIT cho first(), filter/pagination cho all(). Kiểm thử cả hàng không tồn tại, hàng có cột NULL, duplicate, JOIN nhiều hàng và UPDATE 0 hàng bằng StepVerifier cùng database thật. Khi hợp đồng dữ liệu được chọn đúng, reactive pipeline sẽ biểu diễn rõ ràng cả kết quả thành công, absence và lỗi.
