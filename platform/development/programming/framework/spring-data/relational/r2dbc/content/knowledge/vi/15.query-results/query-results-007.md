# Giữ đúng hợp đồng một kết quả và xử lý nhiều kết quả ngoài dự kiến

Trong Spring Data R2DBC, kiểu trả về reactive thể hiện số lượng kết quả mà tầng ứng dụng mong đợi. `Mono<T>` biểu diễn tối đa một phần tử, còn `Flux<T>` biểu diễn một chuỗi có thể chứa từ 0 đến nhiều phần tử. Khi truy vấn được thiết kế để tìm đúng một bản ghi, ứng dụng cần bảo vệ hợp đồng đó: không có kết quả phải được xử lý rõ ràng, một kết quả phải được trả về đúng cách, và nhiều kết quả ngoài dự kiến phải được phát hiện thay vì âm thầm chọn một bản ghi bất kỳ.

Đây không chỉ là vấn đề chọn kiểu trả về. Nó còn liên quan đến unique constraint trong database, điều kiện truy vấn, cách dùng các operator của Reactor, thứ tự kết quả SQL và cách ánh xạ join. Nếu dùng `first()` để che một truy vấn vốn phải duy nhất, dữ liệu trùng lặp có thể tồn tại lâu mà không ai nhận ra.

## 1. Hợp đồng số lượng của Mono và Flux

Reactive Streams không truyền `null` như một phần tử. Một `Mono<T>` có thể phát một giá trị rồi hoàn tất, hoàn tất rỗng hoặc phát lỗi. Một `Flux<T>` có thể phát 0, 1 hoặc nhiều giá trị rồi hoàn tất hoặc phát lỗi.

| Kiểu trả về | Số phần tử hợp lệ | Ý nghĩa thường gặp |
|---|---:|---|
| `Mono<Customer>` | 0 hoặc 1 | Tìm một khách hàng theo ID, email duy nhất hoặc khóa nghiệp vụ. |
| `Flux<Customer>` | 0 đến nhiều | Tìm danh sách khách hàng theo trạng thái hoặc tiêu chí lọc. |
| `Mono<Long>` | 1 giá trị hoặc rỗng tùy API | Số hàng bị ảnh hưởng, số lượng hoặc giá trị tổng hợp. |
| `Mono<Boolean>` | 1 giá trị hoặc rỗng tùy API | Kết quả kiểm tra tồn tại nếu service chủ động trả về boolean. |
| `Mono<Void>` | Không phát phần tử | Chỉ quan tâm thao tác hoàn tất hay lỗi, ví dụ xóa hoặc ghi audit. |

`Mono<Customer>` không có nghĩa database chắc chắn có đúng một hàng. Nó thể hiện rằng consumer nhận tối đa một `Customer`. Truy vấn vẫn có thể không tìm thấy hàng nào; trường hợp này được biểu diễn bằng `Mono.empty()`. Nếu database trả về nhiều hàng trong một API yêu cầu tối đa một kết quả, hành vi phụ thuộc abstraction thực thi: các API kiểm tra cardinality sẽ phát lỗi kích thước kết quả, trong khi API lấy phần tử đầu tiên có thể bỏ qua phần còn lại.

## 2. Khai báo repository theo đúng số lượng kết quả

Với repository, hãy chọn kiểu trả về theo ý nghĩa nghiệp vụ của truy vấn:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByTenantIdAndEmail(UUID tenantId, String email);

    Flux<Customer> findByTenantIdAndStatus(UUID tenantId, CustomerStatus status);
}
```

Phương thức thứ nhất biểu diễn một khách hàng trong một tenant theo email. Nếu email phải duy nhất trong tenant, schema cần có unique constraint tương ứng. Phương thức thứ hai có thể trả về nhiều khách hàng nên dùng `Flux<Customer>`.

Ví dụ với truy vấn khai báo:

```java
@Query("""
    SELECT *
    FROM customer
    WHERE tenant_id = :tenantId
      AND email = :email
    """)
Mono<Customer> findByTenantAndEmail(
    @Param("tenantId") UUID tenantId,
    @Param("email") String email
);
```

Khi khai báo truy vấn đơn kết quả bằng `Mono<T>`, Spring Data R2DBC kỳ vọng truy vấn trả về không quá một hàng. Nếu truy vấn trả về nhiều hàng, thao tác có thể phát `IncorrectResultSizeDataAccessException` thay vì chọn một hàng tùy ý. Đây là tín hiệu cho thấy điều kiện truy vấn, dữ liệu hoặc constraint chưa đáp ứng hợp đồng đơn kết quả.

Ngược lại, nếu nghiệp vụ thực sự cần tất cả kết quả, hãy khai báo `Flux<T>`. Không nên dùng `Mono<T>` chỉ vì service hiện tại chỉ muốn đọc một phần tử trong khi truy vấn có thể trả về nhiều hàng hợp lệ.

## 3. Phân biệt one(), first() và all() của DatabaseClient

`DatabaseClient` cung cấp các cách lấy kết quả với cardinality khác nhau. Sau khi gọi `fetch()`, có thể chọn:

- `one()`: trả về `Mono<T>`, chấp nhận 0 hoặc 1 hàng; nếu có nhiều hơn một hàng thì phát lỗi kích thước kết quả.
- `first()`: trả về `Mono<T>` chứa hàng đầu tiên nếu có; các hàng còn lại không được chuyển đến consumer.
- `all()`: trả về `Flux<T>` chứa tất cả hàng.

Ví dụ truy vấn theo email được kỳ vọng là duy nhất:

```java
Mono<Customer> customer = databaseClient.sql("""
        SELECT id, tenant_id, email, display_name
        FROM customer
        WHERE tenant_id = :tenantId
          AND email = :email
        """)
    .bind("tenantId", tenantId)
    .bind("email", email)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("tenant_id", UUID.class),
        row.get("email", String.class),
        row.get("display_name", String.class)
    ))
    .one();
```

`one()` phù hợp khi nhiều hàng là lỗi dữ liệu hoặc lỗi điều kiện truy vấn. Nếu mục tiêu chỉ là lấy bản ghi đứng đầu theo một thứ tự xác định, dùng `first()` hoặc query có giới hạn sau khi thêm `ORDER BY` rõ ràng.

Không nhầm `first()` với kiểm tra tính duy nhất. `first()` chỉ đáp ứng nhu cầu lấy một hàng; nó không xác nhận rằng chỉ có một hàng thỏa điều kiện.

## 4. Các operator Reactor và ý nghĩa cardinality

Khi có một `Flux<T>` nhưng service cần trả về `Mono<T>`, Reactor cung cấp nhiều operator. Chúng có semantics khác nhau:

| Operator | Kết quả | Hành vi khi có nhiều phần tử |
|---|---|---|
| `next()` | `Mono<T>` | Lấy phần tử đầu tiên rồi hoàn tất; phần tử sau bị bỏ qua. |
| `take(1)` | `Flux<T>` | Chỉ giữ tối đa phần tử đầu tiên. |
| `single()` | `Mono<T>` | Yêu cầu đúng một phần tử; rỗng hoặc nhiều hơn một đều là lỗi. |
| `singleOrEmpty()` | `Mono<T>` | Cho phép 0 hoặc 1; nhiều hơn một là lỗi. |
| `collectList()` | `Mono<List<T>>` | Thu thập tất cả phần tử vào bộ nhớ thành một danh sách. |

Ví dụ:

```java
Flux<Customer> matches = repository.findByEmail(email);

Mono<Customer> firstMatch = matches.next();
```

Đoạn mã này chỉ lấy một kết quả đầu tiên. Nó không phát hiện dữ liệu trùng.

Nếu hợp đồng yêu cầu không quá một kết quả:

```java
Mono<Customer> zeroOrOne = repository.findByEmail(email)
    .singleOrEmpty();
```

`singleOrEmpty()` hoàn tất rỗng nếu không có phần tử và phát lỗi nếu có từ hai phần tử trở lên. Nếu nghiệp vụ yêu cầu bắt buộc có đúng một phần tử, có thể dùng `single()`, nhưng cần xử lý riêng trường hợp không có dữ liệu.

`collectList()` hữu ích khi danh sách có giới hạn và service cần xử lý toàn bộ kết quả. Không nên thu thập một tập kết quả không giới hạn vào bộ nhớ chỉ để lấy một phần tử hoặc để kiểm tra trùng lặp. Có thể giới hạn luồng ở hai phần tử đầu tiên để phát hiện trường hợp vượt cardinality mà không tải toàn bộ kết quả.

## 5. Phát hiện nhiều kết quả ngoài dự kiến

Giả sử truy vấn tìm khách hàng theo tenant và email nhưng dữ liệu hiện có hai hàng khớp. Nếu service dùng `.next()`, nó trả về một hàng và che giấu lỗi dữ liệu. Nếu dùng `singleOrEmpty()`, service phát lỗi khi có nhiều hơn một hàng.

Một cách kiểm tra có giới hạn rõ ràng là lấy tối đa hai kết quả:

```java
public Mono<Customer> findUniqueCustomer(UUID tenantId, String email) {
    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("email").is(email)
    );

    return template.select(query, Customer.class)
        .take(2)
        .collectList()
        .flatMap(matches -> {
            if (matches.isEmpty()) {
                return Mono.empty();
            }
            if (matches.size() == 1) {
                return Mono.just(matches.get(0));
            }
            return Mono.error(
                new IncorrectResultSizeDataAccessException(1, 2));
        });
}
```

Ví dụ trên giới hạn số phần tử được thu thập ở hai. Kết quả 0 được biểu diễn bằng `Mono.empty()`, kết quả 1 được trả về, còn từ 2 trở lên được xem là vi phạm hợp đồng. Cần import `Query`, `Criteria`, `R2dbcEntityTemplate` và `IncorrectResultSizeDataAccessException` tương ứng.

Một cách ngắn hơn là dùng `singleOrEmpty()` trực tiếp trên `Flux` nếu kiểu lỗi cardinality của Reactor phù hợp với tầng ứng dụng. Nếu cần phát một lỗi persistence có ý nghĩa thống nhất, có thể chuyển lỗi cardinality sang exception nghiệp vụ hoặc `DataAccessException` tại service boundary.

Không nên bắt mọi exception rồi chuyển thành `Mono.empty()`. Làm vậy có thể khiến lỗi nhiều hàng, lỗi codec, lỗi kết nối hoặc lỗi SQL bị hiểu nhầm thành “không tìm thấy”. Chỉ chuyển đổi những lỗi đã xác định rõ và giữ nguyên lỗi hệ thống cần được xử lý ở tầng cao hơn.

## 6. Bảo đảm tính duy nhất ở database

Kiểm tra trong ứng dụng giúp phát hiện dữ liệu bất thường, nhưng không thay thế unique constraint. Hai request có thể cùng kiểm tra rằng email chưa tồn tại rồi đồng thời chèn hai hàng giống nhau. Nếu không có ràng buộc ở database, cả hai thao tác có thể thành công.

Nếu email phải duy nhất trong từng tenant, hãy tạo unique constraint ghép:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_tenant_email
UNIQUE (tenant_id, email);
```

Constraint ở database là nơi bảo đảm tính duy nhất dưới cạnh tranh đồng thời. Ứng dụng vẫn nên xử lý lỗi vi phạm unique constraint để trả phản hồi phù hợp, ví dụ báo email đã được sử dụng.

Không nên chỉ chạy `SELECT COUNT(*)` trước khi insert rồi tin rằng dữ liệu sẽ duy nhất. Giữa bước kiểm tra và bước ghi có thể có transaction khác chèn cùng giá trị. Unique constraint cùng xử lý lỗi ghi là cơ chế bảo vệ cuối cùng.

Nếu truy vấn đơn kết quả dựa trên một điều kiện không được unique constraint bảo vệ, cần quyết định rõ: nhiều hàng là lỗi nghiệp vụ, hay truy vấn thực ra cần chọn bản ghi mới nhất/ưu tiên nhất. Nếu nhiều hàng hợp lệ, kiểu trả về nên là `Flux<T>` hoặc `Mono<List<T>>` với giới hạn phù hợp.

## 7. Khi không có kết quả: Mono.empty() và xử lý not found

`Mono.empty()` là trạng thái hoàn tất không có giá trị. Nó không giống một hàng có cột SQL `NULL`. Ví dụ:

- Không có hàng nào thỏa `WHERE id = :id`: repository trả `Mono.empty()`.
- Có hàng nhưng cột `nickname` là SQL `NULL`: `Mono<Customer>` vẫn phát một `Customer`, trong đó thuộc tính `nickname` có thể là `null` nếu mapping cho phép.
- Một phương thức trả `Mono<Void>` hoàn tất thành công: không phát giá trị là semantics bình thường, không có nghĩa thao tác thất bại.

Ở service, có thể chuyển trường hợp rỗng thành lỗi nghiệp vụ:

```java
public Mono<Customer> getRequiredCustomer(Long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)));
}
```

Hoặc cung cấp giá trị mặc định nếu nghiệp vụ cho phép:

```java
return repository.findById(id)
    .defaultIfEmpty(Customer.guest());
```

`switchIfEmpty` hữu ích khi cần thực hiện một publisher khác hoặc phát lỗi; `defaultIfEmpty` dùng khi đã có một giá trị thay thế. Không dùng giá trị mặc định để che trường hợp dữ liệu bắt buộc bị thiếu.

## 8. Khi nào nên lấy phần tử đầu tiên?

Có những use case thực sự muốn chọn một hàng trong nhiều hàng, chẳng hạn bản ghi mới nhất, trạng thái gần nhất hoặc ưu tiên cao nhất. Trong trường hợp này, lấy phần tử đầu tiên là đúng nếu thứ tự được định nghĩa rõ.

Ví dụ dùng `ORDER BY` và `LIMIT 1`:

```java
@Query("""
    SELECT *
    FROM customer_session
    WHERE customer_id = :customerId
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """)
Mono<CustomerSession> findLatestSession(Long customerId);
```

`created_at DESC` chọn session mới nhất. `id DESC` là tie-breaker để thứ tự xác định nếu nhiều hàng có cùng thời điểm. Cú pháp `LIMIT` có thể cần điều chỉnh theo database/dialect.

Nếu dùng `first()` trên kết quả không có `ORDER BY`, database không bảo đảm hàng nào được xem là đầu tiên. Kết quả có thể thay đổi theo execution plan, index, dữ liệu hoặc phiên bản database. Vì vậy, `first()` không có nghĩa là “mới nhất”, “cũ nhất” hay “quan trọng nhất” nếu SQL không xác định thứ tự.

Có thể dùng derived query như `findFirstBy...OrderByCreatedAtDesc` hoặc `findTopBy...` nếu phương thức được Spring Data hỗ trợ theo cú pháp và phiên bản dự án. Cần kiểm tra cách tạo query thực tế và bổ sung tie-breaker khi có thể.

## 9. Nguyên nhân một truy vấn dự kiến duy nhất lại trả nhiều hàng

Khi gặp `IncorrectResultSizeDataAccessException` hoặc lỗi cardinality từ Reactor, hãy xem xét các nguyên nhân sau:

1. **Thiếu unique constraint:** dữ liệu có thể chứa nhiều hàng cùng giá trị nghiệp vụ dù code giả định duy nhất.
2. **Điều kiện WHERE chưa đủ:** query quên tenant, loại bản ghi, trạng thái hoặc một phần của khóa ghép.
3. **Dữ liệu trùng do migration/import:** quy trình nạp dữ liệu không giữ constraint hoặc trước đây schema chưa có ràng buộc.
4. **JOIN một-nhiều:** một hàng cha được kết hợp với nhiều hàng con, làm kết quả SQL có nhiều hàng dù chỉ có một entity cha.
5. **Mapping projection không đúng:** query trả về nhiều dòng cho một logical object nhưng code xử lý từng dòng như một object duy nhất.
6. **Dùng API lấy một hàng sai mục đích:** `.first()` hoặc `.next()` che các kết quả bổ sung thay vì báo lỗi.

Hãy xem SQL được thực thi, bind parameter, số hàng thực tế và constraint của schema. Không sửa bằng cách thêm `LIMIT 1` nếu nghiệp vụ yêu cầu tính duy nhất; làm vậy chỉ che nguyên nhân.

## 10. Join một-nhiều và kết quả trùng entity cha

Một truy vấn join có thể tạo nhiều hàng cho một entity cha:

```sql
SELECT o.id, o.order_number, l.id AS line_id, l.product_code
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE o.id = :orderId;
```

Nếu đơn hàng có ba dòng, kết quả SQL có ba hàng. Nếu ánh xạ từng hàng thành `PurchaseOrder` rồi khai báo `Mono<PurchaseOrder>`, query có thể vi phạm cardinality dù chỉ có một đơn hàng logic.

Có một số cách xử lý:

- Nếu chỉ cần thông tin đơn hàng, truy vấn riêng bảng cha hoặc dùng `SELECT DISTINCT` trên tập cột của entity cha khi phù hợp.
- Nếu cần thông tin từng dòng hàng, trả về DTO phẳng như `OrderLineView` bằng `Flux`.
- Nếu cần một object lồng nhau, nhóm các dòng theo ID cha trong tầng mapping hoặc dùng truy vấn/projection được thiết kế để tổng hợp rõ ràng.
- Nếu chỉ cần biết có dòng hàng hay không, dùng `EXISTS` thay vì join trả nhiều hàng.

Ví dụ kiểm tra sự tồn tại:

```sql
SELECT EXISTS (
    SELECT 1
    FROM order_line
    WHERE order_id = :orderId
);
```

Kết quả boolean tránh việc lấy nhiều hàng con khi service chỉ cần câu trả lời có/không.

Spring Data R2DBC không có persistence context/identity map kiểu JPA để tự động hợp nhất nhiều hàng join thành một object graph. Trách nhiệm xác định hình dạng kết quả và gom nhóm dữ liệu thuộc về query/projection hoặc code mapping của ứng dụng.

## 11. Kiểm soát lỗi cardinality trong reactive chain

Không nên dùng `onErrorResume` quá rộng để xử lý lỗi truy vấn đơn kết quả:

```java
// Không nên: mọi lỗi đều bị biến thành không tìm thấy.
repository.findByEmail(email)
    .onErrorResume(error -> Mono.empty());
```

Đoạn code trên biến cả lỗi kết nối, lỗi SQL, lỗi mapping và lỗi nhiều kết quả thành `Mono.empty()`. Consumer không thể phân biệt dữ liệu không tồn tại với lỗi hệ thống.

Thay vào đó, xử lý trường hợp rỗng và lỗi đã biết riêng biệt:

```java
repository.findByEmail(email)
    .switchIfEmpty(Mono.error(new CustomerNotFoundException(email)))
    .onErrorMap(
        IncorrectResultSizeDataAccessException.class,
        error -> new DuplicateCustomerDataException(email, error)
    );
```

`onErrorMap` chỉ chuyển đổi loại lỗi được chỉ định. Lỗi kết nối và các lỗi persistence khác tiếp tục được truyền lên để hệ thống logging, retry policy hoặc exception handler xử lý đúng cách.

Không tự động retry lỗi cardinality. Nếu truy vấn trả nhiều hàng do dữ liệu trùng, retry cùng câu lệnh thường cho cùng kết quả và chỉ tăng tải database. Retry chỉ phù hợp với lỗi tạm thời đã được xác định, chẳng hạn một số lỗi kết nối hoặc deadlock, và phải xem xét tính idempotent của thao tác.

## 12. Không dùng collectList() tùy tiện

`collectList()` chuyển toàn bộ các phần tử của `Flux` thành một `List` trong một `Mono`. Điều này tiện cho xử lý danh sách nhỏ, nhưng tiêu thụ bộ nhớ tỷ lệ với số kết quả.

Không nên viết:

```java
repository.findAll()
    .collectList()
    .map(customers -> customers.get(0));
```

Đoạn code tải toàn bộ bảng vào bộ nhớ chỉ để lấy một phần tử, có thể lỗi khi danh sách rỗng và che các kết quả trùng. Nếu cần phần tử đầu tiên, dùng truy vấn có thứ tự và giới hạn. Nếu cần kiểm tra tối đa một kết quả, dùng `singleOrEmpty()` hoặc giới hạn tối đa hai hàng rồi xác thực cardinality.

Với danh sách lớn, xử lý theo luồng `Flux`, dùng pagination/keyset pagination hoặc batch phù hợp. Chỉ gom danh sách khi kích thước có giới hạn và nhu cầu bộ nhớ đã được cân nhắc.

## 13. Kiểm thử hợp đồng số lượng kết quả

Với một query đơn kết quả, nên kiểm thử ít nhất ba tình huống:

| Dữ liệu phù hợp | Hành vi mong đợi |
|---|---|
| Không có hàng | `Mono.empty()` hoặc lỗi not found do service chuyển đổi. |
| Chính xác một hàng | Phát đúng một entity/DTO. |
| Hai hoặc nhiều hàng | Phát lỗi cardinality hoặc xử lý theo quy tắc chọn bản ghi được định nghĩa rõ. |

Nếu query có join, thêm tình huống một hàng cha có nhiều hàng con để xác nhận kết quả SQL có được ánh xạ đúng. Nếu tính duy nhất dựa trên tenant và email, kiểm tra unique constraint với hai request cạnh tranh hoặc hai insert cùng giá trị.

Kiểm thử nên chạy trên database/driver tương thích với môi trường thực tế khi hành vi phụ thuộc SQL dialect, unique constraint hoặc codec. Unit test với mock repository có thể kiểm tra service xử lý `Mono.empty()` và lỗi cardinality, nhưng không chứng minh schema database thực sự ngăn dữ liệu trùng.

## 14. Chọn API theo ý định nghiệp vụ

| Ý định | Cách triển khai |
|---|---|
| Tìm một bản ghi theo khóa chính | `findById`, trả `Mono<T>`. |
| Tìm một bản ghi theo khóa nghiệp vụ duy nhất | `Mono<T>` cùng unique constraint và điều kiện đầy đủ. |
| Tìm 0 hoặc 1 hàng từ `DatabaseClient` | `fetch().one()`. |
| Lấy hàng đầu tiên theo ưu tiên | `ORDER BY` xác định, giới hạn một hàng hoặc `first()` sau khi đã sắp thứ tự. |
| Yêu cầu đúng một phần tử từ `Flux` | `single()`; xử lý cả trường hợp rỗng và nhiều phần tử. |
| Cho phép 0 hoặc 1 phần tử từ `Flux` | `singleOrEmpty()`. |
| Tìm danh sách | `Flux<T>` hoặc thu thập thành danh sách có giới hạn. |
| Kiểm tra tồn tại | `existsBy...` hoặc SQL `EXISTS`, không tải toàn bộ entity. |

Hợp đồng cardinality cần được thể hiện xuyên suốt từ SQL, kiểu trả về repository đến service và API. `Mono` biểu diễn tối đa một phần tử; nó không tự tạo ra tính duy nhất cho dữ liệu. Khi nghiệp vụ yêu cầu duy nhất, hãy bảo vệ bằng constraint ở database, dùng API phát hiện nhiều hàng và xử lý `Mono.empty()` riêng. Chỉ chọn phần tử đầu tiên khi nghiệp vụ thực sự có quy tắc ưu tiên và truy vấn xác định thứ tự rõ ràng.
