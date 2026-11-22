# Chọn bảng đích và kiểu kết quả cho từng thao tác

## 1. Hai quyết định khi xây dựng thao tác dữ liệu

Khi làm việc với cơ sở dữ liệu quan hệ bằng Spring Data R2DBC, một thao tác dữ liệu cần xác định rõ hai điều:

1. **Thao tác tác động đến bảng nào?** Bảng có thể được suy ra từ entity mapping, được chỉ định bằng kiểu entity trong template, hoặc được viết tường minh trong SQL.
2. **Ứng dụng cần nhận kết quả ở dạng nào?** Kết quả có thể là một entity, nhiều entity, một giá trị đơn như số dòng bị ảnh hưởng, một cờ boolean hoặc chỉ là tín hiệu hoàn tất.

Hai quyết định này liên quan với nhau nhưng không đồng nhất. Kiểu entity thường quyết định bảng và cách ánh xạ dữ liệu; kiểu trả về quyết định cách tầng gọi tiêu thụ kết quả trong reactive pipeline.

Ví dụ:

- Tạo một Customer mới: bảng đích là `customers`, kết quả hữu ích là `Mono<Customer>` để nhận entity sau khi database sinh ID.
- Tìm danh sách Customer đang hoạt động: bảng đích vẫn là `customers`, kết quả là `Flux<Customer>`.
- Cập nhật trạng thái: bảng đích là `customers`, kết quả thường là `Mono<Long>` biểu diễn số dòng bị ảnh hưởng.
- Kiểm tra email đã tồn tại: bảng đích là `customers`, kết quả là `Mono<Boolean>`.
- Xóa một bản ghi qua repository CRUD: kết quả tiêu chuẩn thường là `Mono<Void>`, chỉ biểu thị thao tác hoàn tất.

Spring Data R2DBC cung cấp nhiều mức API để diễn đạt các lựa chọn đó: repository, `R2dbcEntityTemplate` và `DatabaseClient`.

## 2. Chọn bảng đích qua entity mapping

### 2.1. @Table xác định bảng của entity

Với repository hoặc template mapping entity, Spring Data cần biết entity tương ứng với bảng nào. Có thể khai báo tên bảng bằng annotation `@Table`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @Column("email_address") String email,
        String status
) {}
~~~

Trong ví dụ:

- `Customer` là kiểu domain được ánh xạ.
- `@Table("customers")` xác định bảng đích.
- `@Id` đánh dấu khóa chính.
- `@Column("email_address")` ánh xạ property `email` sang cột có tên `email_address`.

Nếu không chỉ định tên bảng tường minh, Spring Data có thể suy ra tên từ kiểu entity theo naming strategy. Với schema có sẵn, nên kiểm tra tên bảng/cột thực tế và dùng `@Table`, `@Column` khi cần.

### 2.2. Repository gắn với một kiểu entity

Repository khai báo kiểu entity và kiểu ID:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Long> countByStatus(String status);
}
~~~

Vì repository được khai báo cho `Customer`, các thao tác CRUD và derived query của nó làm việc với bảng được mapping từ Customer. Tên phương thức xác định điều kiện truy vấn; kiểu entity generic xác định mô hình dữ liệu cần đọc/ghi.

Không thể chỉ đổi kiểu trả về của một phương thức để chuyển repository sang một bảng khác. Nếu cần thao tác với bảng khác, hãy dùng repository tương ứng với entity khác, chọn kiểu domain khác khi dùng template, hoặc viết SQL rõ ràng qua DatabaseClient.

### 2.3. Kiểu entity và bảng là hai khái niệm mapping

Một bảng không nhất thiết phải có tên giống class Java. Ví dụ class `PurchaseOrder` có thể ánh xạ vào bảng `purchase_orders`. Ngược lại, một truy vấn báo cáo có thể đọc dữ liệu từ nhiều bảng nhưng trả về DTO như `OrderSummary`.

Trong trường hợp thứ hai, DTO chỉ mô tả hình dạng kết quả; nó không tự xác định bảng. SQL hoặc query mapping mới quyết định dữ liệu được lấy từ đâu.

## 3. Chọn bảng đích với R2dbcEntityTemplate

`R2dbcEntityTemplate` cung cấp API hướng entity cho thao tác insert, select, update, delete, count và exists. Với những thao tác này, kiểu entity được truyền vào template giúp Spring Data tra metadata mapping để xác định bảng và cách ánh xạ.

### 3.1. Insert vào bảng của entity

~~~java
Mono<Customer> inserted =
        template.insert(Customer.class)
                .using(new Customer(
                        null,
                        "An Nguyen",
                        "an@example.test",
                        "ACTIVE"
                ));
~~~

`Customer.class` cho template biết entity type và bảng được mapping. `using(...)` cung cấp object cần insert. Kết quả là `Mono<Customer>`, có thể phát ra entity sau khi lưu với generated ID hoặc giá trị được persistence layer cập nhật nếu database/driver hỗ trợ trả về.

### 3.2. Select từ bảng của entity

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"));

Flux<Customer> activeCustomers =
        template.select(query, Customer.class);
~~~

Ở đây, `Customer.class` xác định bảng và mapping kết quả; `Query` xác định điều kiện lọc. Kết quả là `Flux<Customer>` vì truy vấn có thể trả về nhiều khách hàng.

Nếu chỉ cần một kết quả:

~~~java
Mono<Customer> customer =
        template.selectOne(
                Query.query(Criteria.where("email").is("an@example.test")),
                Customer.class
        );
~~~

Dùng `selectOne` khi điều kiện nghiệp vụ hoặc constraint database bảo đảm tối đa một hàng. Nếu truy vấn có thể trả nhiều hàng, hãy dùng `select` và `Flux`, hoặc chọn rõ cách lấy phần tử đầu tiên theo thứ tự đã định nghĩa.

### 3.3. Update vào bảng của entity

~~~java
Query query = Query.query(Criteria.where("id").is(customerId));

Mono<Long> updatedRows =
        template.update(Customer.class)
                .matching(query)
                .apply(Update.update("status", "INACTIVE"));
~~~

`Customer.class` xác định bảng cần cập nhật. `matching(query)` chọn các hàng thỏa điều kiện. `apply(update)` mô tả các cột cần thay đổi. Kết quả là `Mono<Long>` biểu diễn số hàng được cập nhật.

Nếu điều kiện dùng khóa chính, kết quả thường là 0 hoặc 1. Giá trị 0 có thể nghĩa là bản ghi không tồn tại hoặc không còn thỏa điều kiện; không nên mặc định đó là lỗi database.

### 3.4. Delete khỏi bảng của entity

~~~java
Query query = Query.query(Criteria.where("id").is(customerId));

Mono<Long> deletedRows =
        template.delete(Customer.class)
                .matching(query)
                .all();
~~~

Kiểu `Customer.class` xác định bảng bị xóa. Kết quả `Mono<Long>` cho biết số hàng đã bị xóa. Nếu chỉ cần thao tác xóa theo khóa chính, điều kiện cần đủ cụ thể để không xóa nhầm nhiều hàng.

### 3.5. Count và exists

Hai thao tác này không cần trả entity:

~~~java
Mono<Long> customerCount =
        template.count(
                Query.query(Criteria.where("status").is("ACTIVE")),
                Customer.class
        );

Mono<Boolean> customerExists =
        template.exists(
                Query.query(Criteria.where("email").is("an@example.test")),
                Customer.class
        );
~~~

Cả hai vẫn sử dụng entity type để xác định bảng. Nhưng kiểu kết quả được chọn theo câu hỏi nghiệp vụ: số lượng là `Mono<Long>`, còn tồn tại hay không là `Mono<Boolean>`.

## 4. Chọn kiểu kết quả theo số lượng hàng

Reactor cung cấp hai kiểu phổ biến để biểu diễn kết quả dữ liệu:

- **Mono<T>:** publisher phát tối đa một giá trị T, hoặc hoàn tất rỗng nếu không có giá trị.
- **Flux<T>:** publisher phát không, một hoặc nhiều giá trị T.

Chọn kiểu dựa trên cardinality (số lượng kết quả) mà nghiệp vụ mong đợi:

| Nhu cầu | Kiểu kết quả thường dùng | Ý nghĩa |
|---|---|---|
| Đọc theo khóa chính | `Mono<Customer>` | Không có hoặc một entity |
| Đọc theo unique key | `Mono<Customer>` | Không có hoặc một entity nếu unique constraint được bảo đảm |
| Đọc danh sách | `Flux<Customer>` | Không hoặc nhiều entity |
| Đếm số hàng | `Mono<Long>` | Một giá trị số lượng |
| Kiểm tra tồn tại | `Mono<Boolean>` | Một giá trị true/false |
| Chờ thao tác hoàn tất, không cần dữ liệu | `Mono<Void>` | Chỉ tín hiệu hoàn tất hoặc lỗi |
| Cập nhật/xóa và cần biết số hàng | `Mono<Long>` | Số hàng bị ảnh hưởng |
| Trả một DTO tổng hợp | `Mono<OrderSummary>` hoặc `Flux<OrderSummary>` | Một hoặc nhiều projection |

### 4.1. Mono không phải là một object có thể null

Reactive Streams không phát ra giá trị null. Nếu truy vấn không tìm thấy hàng, `Mono<Customer>` thường hoàn tất mà không phát giá trị. Có thể xử lý trường hợp này bằng các toán tử như:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(id)
        ));
~~~

Không nên dùng null để biểu diễn kết quả không tìm thấy. `Mono.empty()` và error signal là hai trạng thái khác nhau: empty nghĩa là không có kết quả; error nghĩa là thao tác thất bại.

### 4.2. Chọn Mono khi thực sự có tối đa một hàng

Các truy vấn theo khóa chính hoặc cột có unique constraint phù hợp với `Mono<T>`. Nếu điều kiện không duy nhất nhưng phương thức khai báo `Mono<T>`, nhiều hàng có thể gây lỗi cardinality thay vì tự chọn một hàng tùy ý.

Nếu nghiệp vụ muốn lấy một bản ghi đầu tiên, phải xác định thứ tự:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :status
    ORDER BY id
    LIMIT 1
    """)
Mono<Customer> findFirstByStatus(String status);
~~~

Ví dụ SQL dùng cú pháp PostgreSQL. Với derived query, có thể dùng các tiền tố như `findFirst...` hoặc `findTop...` theo khả năng query derivation của Spring Data. Khi dùng SQL tùy chỉnh, thêm `ORDER BY` để kết quả có thứ tự xác định.

### 4.3. Chọn Flux cho tập kết quả

~~~java
Flux<Customer> customers = customerRepository.findByStatus("ACTIVE");
~~~

`Flux` phù hợp khi số kết quả không cố định hoặc có thể nhiều hàng. Tuy nhiên, Flux không bảo đảm database tự trả dữ liệu theo thứ tự mong muốn. Nếu cần thứ tự, phải thêm `ORDER BY` trong query.

Với tập dữ liệu lớn, cần cân nhắc phân trang, giới hạn số hàng và backpressure. Không nên chuyển một Flux rất lớn thành List trong bộ nhớ nếu không thực sự cần.

## 5. Kiểu kết quả cho từng thao tác CRUD

### 5.1. Insert: trả entity đã lưu

Repository:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Template:

~~~java
Mono<Customer> inserted =
        template.insert(Customer.class).using(customer);
~~~

Kết quả entity hữu ích khi ứng dụng cần ID sinh tự động, version hoặc giá trị được persistence layer cập nhật. Hãy dùng entity được phát ra từ publisher, đặc biệt khi entity immutable như Java record.

Nếu chỉ cần biết thao tác đã hoàn tất mà không cần entity, có thể chuyển kết quả thành completion signal:

~~~java
Mono<Void> completed =
        customerRepository.save(customer).then();
~~~

Sau khi gọi `then()`, ID và entity đã lưu không còn được phát ra ở downstream. Chỉ chọn `Mono<Void>` khi thực sự không cần những giá trị đó.

### 5.2. Select: trả một entity hoặc nhiều entity

~~~java
Mono<Customer> one = customerRepository.findById(id);

Flux<Customer> many = customerRepository.findByStatus("ACTIVE");
~~~

Chọn kiểu theo cardinality và constraint của dữ liệu. Với truy vấn một hàng, nên dùng khóa chính hoặc unique key. Với truy vấn danh sách, dùng Flux và bổ sung thứ tự/phân trang khi cần.

### 5.3. Update: trả số hàng bị ảnh hưởng

Repository có thể cung cấp phương thức cập nhật tùy chỉnh theo khả năng của query method và câu SQL:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET status = :status
    WHERE id = :id
    """)
Mono<Integer> updateStatus(Long id, String status);
~~~

Với modifying query, kiểu kết quả thường được chọn để nhận số hàng bị ảnh hưởng theo hỗ trợ của Spring Data/driver. Ví dụ dùng `Mono<Integer>` hoặc `Mono<Long>` tùy API và kiểu số mà method khai báo được hỗ trợ trong phiên bản đang dùng. Khi muốn rõ ràng về kết quả, `R2dbcEntityTemplate.update(...).apply(...)` trả về `Mono<Long>`.

Nếu cần kiểm tra chính xác một hàng đã được cập nhật, có thể xử lý count:

~~~java
return template.update(Customer.class)
        .matching(Query.query(Criteria.where("id").is(id)))
        .apply(Update.update("status", "INACTIVE"))
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(new CustomerNotFoundException(id));
            }
            return Mono.just(rows);
        });
~~~

Số hàng bằng 0 có thể do không tìm thấy bản ghi hoặc điều kiện không còn đúng. Nếu cập nhật theo version để chống ghi đè, 0 hàng cũng có thể là dấu hiệu xung đột tùy cơ chế thực thi.

### 5.4. Delete: trả số hàng hoặc chỉ completion

Các phương thức CRUD tiêu chuẩn như `deleteById(id)` trả về `Mono<Void>`, phù hợp khi chỉ cần biết thao tác đã hoàn tất.

Nếu cần số hàng bị xóa, dùng template:

~~~java
Mono<Long> deleted =
        template.delete(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .all();
~~~

Hoặc dùng DatabaseClient để chạy SQL và lấy số hàng cập nhật:

~~~java
Mono<Long> deletedRows =
        databaseClient.sql("DELETE FROM customers WHERE id = :id")
                .bind("id", id)
                .fetch()
                .rowsUpdated();
~~~

### 5.5. Count và exists: trả kiểu scalar

Không cần tải toàn bộ entity chỉ để đếm hoặc kiểm tra tồn tại:

~~~java
Mono<Long> count = customerRepository.count();

Mono<Boolean> exists = customerRepository.existsById(id);
~~~

Dùng API scalar giúp giảm dữ liệu truyền từ database và tránh mapping entity không cần thiết.

## 6. Chọn kết quả khi dùng DatabaseClient

`DatabaseClient` cho phép viết SQL tường minh. Vì SQL đã xác định bảng trong mệnh đề FROM, INSERT, UPDATE hoặc DELETE, kiểu entity không còn tự quyết định bảng như khi dùng repository/template mapping.

### 6.1. Chọn bảng qua SQL

~~~java
databaseClient.sql("""
        SELECT id, name, email_address, status
        FROM customers
        WHERE status = :status
        """)
    .bind("status", "ACTIVE")
    .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email_address", String.class),
            row.get("status", String.class)
    ))
    .all();
~~~

Mệnh đề `FROM customers` chọn bảng. Callback `map` chọn kiểu kết quả bằng cách tạo `Customer`. Phương thức `all()` trả về `Flux<Customer>`.

### 6.2. Chọn một kết quả

~~~java
Mono<Customer> customer =
        databaseClient.sql("""
                SELECT id, name, email_address, status
                FROM customers
                WHERE id = :id
                """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email_address", String.class),
                    row.get("status", String.class)
            ))
            .one();
~~~

`one()` phù hợp khi query được kỳ vọng trả tối đa một hàng. Nếu cần lấy hàng đầu tiên trong một tập có nhiều hàng, dùng API first phù hợp và luôn xác định `ORDER BY` trong SQL.

### 6.3. Chọn kiểu kết quả là DTO/projection

Không phải mọi truy vấn đều cần khôi phục entity đầy đủ. Một màn hình danh sách có thể chỉ cần ID, tên và trạng thái:

~~~java
public record CustomerSummary(Long id, String name, String status) {}
~~~

SQL chỉ lấy các cột cần thiết và callback ánh xạ thành DTO:

~~~java
Flux<CustomerSummary> summaries =
        databaseClient.sql("""
                SELECT id, name, status
                FROM customers
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .all();
~~~

DTO/projection giúp giảm số cột đọc và tách hình dạng kết quả khỏi entity ghi. Khi dùng repository query method, Spring Data cũng hỗ trợ projection trong những trường hợp phù hợp; với SQL tùy chỉnh hoặc phép tổng hợp, DatabaseClient cho phép kiểm soát mapping rõ ràng.

### 6.4. DML không trả hàng: rowsUpdated()

Khi chạy UPDATE hoặc DELETE mà chỉ cần số hàng bị ảnh hưởng:

~~~java
Mono<Long> affected =
        databaseClient.sql("""
                UPDATE customers
                SET status = :status
                WHERE id = :id
                """)
            .bind("status", "INACTIVE")
            .bind("id", id)
            .fetch()
            .rowsUpdated();
~~~

`rowsUpdated()` trả số hàng được tác động theo kết quả mà driver cung cấp. Nếu cần trả lại dữ liệu sau thao tác, hãy dùng khả năng returning của database và map result rows thay vì chỉ lấy số hàng.

### 6.5. DML có RETURNING

PostgreSQL hỗ trợ `RETURNING` cho INSERT, UPDATE và DELETE. Ví dụ:

~~~java
Mono<Customer> inserted =
        databaseClient.sql("""
                INSERT INTO customers (name, email_address, status)
                VALUES (:name, :email, :status)
                RETURNING id, name, email_address, status
                """)
            .bind("name", name)
            .bind("email", email)
            .bind("status", status)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email_address", String.class),
                    row.get("status", String.class)
            ))
            .one();
~~~

Ở đây, SQL chọn bảng `customers`; `RETURNING` yêu cầu PostgreSQL phát ra hàng kết quả; callback chọn kiểu `Customer`; `one()` biểu diễn kết quả một hàng. Đây là tính năng theo dialect, không nên giả định mọi database đều hỗ trợ cùng cú pháp.

## 7. Chọn bảng đích khác nhau trong cùng ứng dụng

Một ứng dụng có thể có nhiều entity và repository:

~~~java
@Table("customers")
public record Customer(@Id Long id, String name) {}

@Table("orders")
public record Order(@Id Long id, Long customerId, String status) {}
~~~

Mỗi repository gắn với một entity:

~~~java
interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {}

interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {}
~~~

Hoặc dùng template với target class tương ứng:

~~~java
Mono<Customer> customer =
        template.selectOne(customerQuery, Customer.class);

Flux<Order> orders =
        template.select(orderQuery, Order.class);
~~~

Cùng một `R2dbcEntityTemplate` có thể thao tác với nhiều bảng vì mỗi lời gọi chỉ rõ kiểu entity đích. Metadata của kiểu đó quyết định bảng và mapping.

Nếu có bảng không ánh xạ thành entity độc lập, hoặc một truy vấn kết hợp nhiều bảng, hãy dùng DatabaseClient và chỉ định SQL. Đừng tạo một entity giả chỉ để ép truy vấn báo cáo vào một mapping không phù hợp.

## 8. Chọn bảng động: giới hạn và cách làm an toàn

Trong một số hệ thống, bảng đích có thể phụ thuộc vào một loại tài nguyên được chọn. Tuy nhiên, tên bảng là SQL identifier; không thể bind như giá trị thông thường.

Ví dụ này không hợp lệ theo ý định bind identifier:

~~~java
databaseClient.sql("SELECT * FROM :tableName")
        .bind("tableName", tableName);
~~~

Bind parameter chỉ dành cho giá trị dữ liệu. Nếu thật sự cần chọn bảng động, dùng allowlist do ứng dụng kiểm soát:

~~~java
Map<String, String> tableNames = Map.of(
        "customers", "customers",
        "orders", "orders"
);

String table = tableNames.get(resourceType);
if (table == null) {
    return Mono.error(new IllegalArgumentException("Unsupported resource"));
}

String sql = "SELECT id FROM " + table + " WHERE status = :status";

return databaseClient.sql(sql)
        .bind("status", status)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
~~~

Giá trị được nối vào SQL ở đây chỉ được lấy từ allowlist tĩnh. Không sử dụng trực tiếp tên bảng do người dùng gửi lên, vì có thể tạo SQL injection qua identifier.

Nếu tập bảng hữu hạn và mỗi bảng có mô hình riêng, cách rõ ràng hơn thường là dùng repository hoặc template với entity type tương ứng, thay vì dynamic SQL.

## 9. Đảm bảo kiểu kết quả phù hợp với thao tác

Chọn kiểu trả về không chỉ là vấn đề cú pháp. Nó ảnh hưởng đến cách ứng dụng phát hiện trạng thái nghiệp vụ.

### 9.1. 0 hàng và 1 hàng

Với update/delete theo ID, số hàng ảnh hưởng có thể là:

- 0: không có hàng thỏa điều kiện.
- 1: một hàng được thay đổi.
- Lớn hơn 1: điều kiện không đủ chặt hoặc nghiệp vụ cho phép thay đổi nhiều hàng.

Nếu thao tác được kỳ vọng chỉ ảnh hưởng đúng một hàng, có thể kiểm tra count:

~~~java
return updatedRows.flatMap(rows -> {
    if (rows != 1) {
        return Mono.error(new IllegalStateException(
                "Expected exactly one updated row, got " + rows
        ));
    }
    return Mono.just(rows);
});
~~~

Không phải mọi trường hợp 0 hàng đều là lỗi. Ví dụ delete idempotent có thể xem việc bản ghi không tồn tại là trạng thái hoàn tất bình thường. Quyết định cần dựa vào hợp đồng nghiệp vụ.

### 9.2. Mono<Void> không cung cấp số hàng

`Mono<Void>` chỉ phát tín hiệu hoàn tất hoặc lỗi. Nó không cho biết có bao nhiêu hàng được cập nhật hoặc xóa.

Nếu API cần trả về 404 khi không có bản ghi, hoặc cần báo số hàng thay đổi, hãy dùng API có kết quả count hoặc truy vấn kiểm tra phù hợp. Đừng chuyển sang `then()` quá sớm nếu tầng gọi vẫn cần giá trị kết quả.

### 9.3. Mono<Boolean> và Mono<Long> không thay thế entity

Nếu chỉ cần kiểm tra tồn tại, `Mono<Boolean>` tiết kiệm hơn tải entity. Nếu chỉ cần đếm, `Mono<Long>` phù hợp hơn tải toàn bộ tập kết quả rồi đếm trong ứng dụng.

Ngược lại, nếu sau thao tác cần ID, version hoặc các field đã được database sinh, hãy giữ kết quả entity thay vì chỉ lấy cờ hoặc count.

## 10. Lựa chọn API theo nhu cầu

| Nhu cầu | API nên cân nhắc | Cách xác định bảng | Kiểu kết quả |
|---|---|---|---|
| CRUD chuẩn cho một entity | ReactiveCrudRepository | Entity generic và @Table | Mono<Entity>, Flux<Entity>, Mono<Void> |
| Insert tường minh | R2dbcEntityTemplate | Target class | Mono<Entity> |
| Select có Criteria | R2dbcEntityTemplate | Target class | Mono<Entity> hoặc Flux<Entity> |
| Update/delete có điều kiện | R2dbcEntityTemplate | Target class | Mono<Long> số hàng ảnh hưởng |
| Count/exists theo điều kiện | R2dbcEntityTemplate | Target class | Mono<Long> / Mono<Boolean> |
| SQL JOIN hoặc báo cáo | DatabaseClient | Bảng được ghi trong SQL | Mono<DTO> / Flux<DTO> |
| SQL DML cần số hàng | DatabaseClient | Bảng được ghi trong SQL | Mono<Long> qua rowsUpdated |
| SQL DML trả lại bản ghi | DatabaseClient và RETURNING nếu database hỗ trợ | Bảng được ghi trong SQL | Mono<DTO> / Flux<DTO> |
| Chọn bảng từ tập lựa chọn hữu hạn | Repository/template riêng hoặc DatabaseClient với allowlist | Entity type hoặc allowlist identifier | Theo kết quả nghiệp vụ |

Repository thường là lựa chọn đơn giản cho CRUD và query method gắn với entity. Template phù hợp khi muốn xây dựng query/update theo metadata mapping. DatabaseClient phù hợp khi cần SQL cụ thể, nhiều bảng, projection hoặc tính năng riêng của database.

## 11. Ví dụ service phối hợp nhiều kiểu kết quả

Một service có thể dùng các kiểu kết quả khác nhau tùy nghiệp vụ:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final R2dbcEntityTemplate template;

    public CustomerService(
            CustomerRepository repository,
            R2dbcEntityTemplate template) {
        this.repository = repository;
        this.template = template;
    }

    public Mono<Customer> create(Customer customer) {
        return repository.save(customer);
    }

    public Mono<Customer> findById(Long id) {
        return repository.findById(id);
    }

    public Flux<Customer> findActive() {
        return repository.findByStatus("ACTIVE");
    }

    public Mono<Long> deactivate(Long id) {
        return template.update(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .apply(Update.update("status", "INACTIVE"));
    }

    public Mono<Boolean> existsByEmail(String email) {
        return repository.existsByEmail(email);
    }

    public Mono<Long> countActive() {
        return template.count(
                Query.query(Criteria.where("status").is("ACTIVE")),
                Customer.class
        );
    }

    public Mono<Long> deleteByIdAndCount(Long id) {
        return template.delete(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .all();
    }
}
~~~

Service không cần dùng cùng một kiểu trả về cho mọi phương thức. Kiểu trả về được chọn theo điều mà caller cần biết:

- create cần entity đã lưu.
- findById có thể không tìm thấy nên trả Mono.
- findActive có thể có nhiều kết quả nên trả Flux.
- deactivate cần số hàng cập nhật nên trả Mono<Long>.
- existsByEmail cần boolean.
- countActive cần số lượng.
- deleteByIdAndCount cần biết số hàng bị xóa.

Các import cho template query có thể dùng:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.relational.core.query.Update;
~~~

Khi dùng phiên bản Spring Data khác nhau, hãy đối chiếu chữ ký API cụ thể trong phiên bản dự án. Nguyên tắc chọn entity type và kiểu kết quả vẫn giữ nguyên.

## 12. Transaction và kết quả của nhiều thao tác

Một nghiệp vụ có thể gồm nhiều thao tác với nhiều kiểu kết quả:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    Order order = new Order(null, request.customerId(), "NEW");

    return orderRepository.save(order)
            .flatMap(saved ->
                    orderLineRepository.saveAll(
                            toOrderLines(saved.id(), request.lines())
                    ).thenReturn(saved)
            );
}
~~~

- Lệnh đầu trả `Mono<Order>`, chứa ID của đơn hàng mới.
- Lệnh thứ hai trả `Flux<OrderLine>`, phát ra các dòng hàng được lưu.
- `thenReturn(saved)` bỏ qua các phần tử OrderLine và phát lại Order đã lưu khi publisher hoàn tất.

Nếu mọi thao tác phải atomic, transaction reactive cần bao quanh toàn bộ pipeline. Không tự gọi `subscribe()` bên trong phương thức transactional vì sẽ tạo subscription độc lập có thể nằm ngoài transaction context.

Nếu chỉ cần biết tất cả thao tác đã hoàn tất, `then()` có thể chuyển kết quả cuối thành `Mono<Void>`. Nếu cần trả Order, dùng `thenReturn(saved)`. Việc chọn operator quyết định dữ liệu nào còn được giữ ở downstream.

## 13. Những lỗi thường gặp khi chọn bảng và kiểu kết quả

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Truy vấn vào sai bảng | Entity mapping hoặc @Table không khớp schema | Kiểm tra target class và metadata mapping |
| Repository trả entity nhưng SQL cần DTO | Dùng entity type cho một read model khác | Dùng projection hoặc DatabaseClient mapping |
| Mono báo nhiều kết quả | Điều kiện truy vấn không duy nhất | Dùng Flux hoặc bảo đảm unique constraint; nếu lấy đầu tiên thì ORDER BY |
| Flux phát dữ liệu không theo thứ tự mong đợi | Không có ORDER BY | Thêm thứ tự vào query |
| Update/delete không biết có hàng nào bị tác động | API trả Mono<Void> hoặc kết quả đã bị bỏ qua | Dùng template hoặc rowsUpdated để nhận count |
| ID sinh ra không có ở tầng gọi | Dùng object đầu vào thay vì entity được trả về | Dùng entity phát ra từ save/insert |
| Dynamic table query lỗi hoặc không an toàn | Cố bind table name hoặc nối input trực tiếp | Dùng entity type cố định hoặc allowlist identifier |
| Chỉ nhận count nhưng cần dữ liệu sau DML | Chọn rowsUpdated trong khi cần generated/returned row | Dùng RETURNING hoặc API trả entity nếu database hỗ trợ |
| Đếm dữ liệu bằng cách tải toàn bộ danh sách | Chọn Flux<Entity> cho nhu cầu count | Dùng count query trả Mono<Long> |
| Delete hoàn tất nhưng caller tưởng bản ghi chắc chắn tồn tại | Dùng Mono<Void> và bỏ qua số hàng | Chọn semantics idempotent hoặc kiểm tra count |

## 14. Nguyên tắc lựa chọn trong thực tế

Có thể áp dụng trình tự sau cho mỗi thao tác:

1. Xác định dữ liệu thuộc entity hoặc bảng nào.
2. Nếu dùng repository/template mapping, xác định target entity class và kiểm tra `@Table`.
3. Nếu truy vấn nhiều bảng hoặc cần projection đặc thù, xác định bảng bằng SQL trong DatabaseClient.
4. Xác định số hàng nghiệp vụ mong đợi: không có hoặc một, hay nhiều hàng.
5. Chọn `Mono<T>` hoặc `Flux<T>` cho entity/DTO.
6. Chọn `Mono<Long>` cho count hoặc số hàng bị ảnh hưởng.
7. Chọn `Mono<Boolean>` cho câu hỏi tồn tại.
8. Chọn `Mono<Void>` chỉ khi caller không cần dữ liệu kết quả.
9. Nếu cần giá trị database sinh ra, trả entity hoặc row được database trả về.
10. Kiểm tra 0 hàng, nhiều hàng, thứ tự, constraint và transaction theo hợp đồng nghiệp vụ.

Một nguyên tắc dễ nhớ là: **entity type hoặc SQL xác định dữ liệu nguồn; kiểu publisher xác định hình dạng kết quả mà tầng gọi nhận được.** Đừng dùng kiểu trả về để suy đoán bảng đích, và đừng tải entity đầy đủ khi chỉ cần một con số hoặc một cờ.

## 15. Kết luận

Trong Spring Data R2DBC, bảng đích thường được xác định từ entity mapping qua `@Table` và kiểu entity của repository hoặc `R2dbcEntityTemplate`. Khi dùng `DatabaseClient`, bảng được chỉ định trực tiếp trong SQL. Những truy vấn kết hợp nhiều bảng hoặc trả DTO có thể dùng DatabaseClient để kiểm soát nguồn dữ liệu và hình dạng kết quả.

Kiểu kết quả cần phản ánh cardinality và thông tin mà nghiệp vụ cần: `Mono<T>` cho tối đa một giá trị, `Flux<T>` cho nhiều giá trị, `Mono<Long>` cho count hoặc số hàng bị ảnh hưởng, `Mono<Boolean>` cho exists và `Mono<Void>` khi chỉ cần tín hiệu hoàn tất. Insert thường nên trả entity để caller nhận ID hoặc version; update/delete nên giữ count nếu cần biết có bao nhiêu hàng được thay đổi.

Chọn đúng bảng và đúng kiểu kết quả giúp code thể hiện rõ ý định, tránh tải dữ liệu thừa, xử lý đúng trường hợp không có kết quả và làm cho reactive pipeline dễ kết hợp hơn.

