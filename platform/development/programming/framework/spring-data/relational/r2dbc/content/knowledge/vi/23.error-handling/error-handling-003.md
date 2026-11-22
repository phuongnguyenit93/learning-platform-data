# Phân biệt không có dữ liệu với truy vấn thất bại

Trong Spring Data R2DBC, một truy vấn không tìm thấy hàng nào và một truy vấn thực thi thất bại là hai kết quả hoàn toàn khác nhau. Trường hợp không có hàng phù hợp thường được biểu diễn bằng `Mono.empty()` hoặc một `Flux` hoàn tất mà không phát phần tử. Trường hợp truy vấn thất bại được biểu diễn bằng tín hiệu lỗi (`onError`) của Reactor.

Phân biệt đúng hai trường hợp này rất quan trọng. Nếu chuyển mọi lỗi database thành `Mono.empty()`, ứng dụng có thể báo “không tìm thấy dữ liệu” khi thực tế database đang mất kết nối, SQL sai, quyền truy cập bị từ chối hoặc mapping thất bại. Ngược lại, nếu coi một kết quả rỗng là lỗi hệ thống, API có thể trả lỗi không cần thiết cho một truy vấn hợp lệ.

## 1. Hai loại kết quả trong reactive flow

Một `Mono<T>` có ba trạng thái kết thúc chính:

- **Có giá trị:** phát một phần tử `T`, sau đó hoàn tất.
- **Rỗng:** không phát phần tử nào và hoàn tất (`Mono.empty()`).
- **Lỗi:** phát một lỗi và kết thúc (`onError`).

Một `Flux<T>` cũng có thể hoàn tất bình thường sau khi phát 0 hoặc nhiều phần tử, hoặc kết thúc bằng lỗi. Không có phần tử không đồng nghĩa với lỗi.

| Tình huống | Kết quả reactive thường gặp | Ý nghĩa |
|---|---|---|
| `SELECT` không có hàng thỏa điều kiện | `Mono.empty()` hoặc `Flux` rỗng | Truy vấn thực thi thành công nhưng không có dữ liệu phù hợp. |
| `SELECT` tìm được một hàng | `Mono.just(value)` | Có một kết quả. |
| `SELECT` tìm được nhiều hàng | `Flux` phát nhiều phần tử; API đơn kết quả có thể báo lỗi cardinality | Số lượng kết quả không khớp hợp đồng nếu caller yêu cầu tối đa một hàng. |
| Database không truy cập được | `onError` | Lỗi hạ tầng hoặc kết nối. |
| SQL sai cú pháp hoặc sai tên cột | `onError` | Lỗi câu lệnh hoặc schema. |
| Không đủ quyền thực thi SQL | `onError` | Lỗi quyền truy cập. |
| Giá trị trả về không ánh xạ được sang kiểu Java | `onError` | Lỗi conversion/codec/mapping. |
| Câu `DELETE` hợp lệ nhưng không hàng nào bị xóa | Thường phát `rowsUpdated = 0` | Lệnh chạy thành công nhưng không có hàng bị ảnh hưởng. |

Điểm mấu chốt: `Mono.empty()` là một kết quả hợp lệ của publisher, còn `onError` là một đường kết thúc lỗi. Hai trạng thái cần được xử lý riêng.

## 2. Không có hàng không phải là cột SQL NULL

Có hai trường hợp khác nhau thường bị nhầm:

1. Không có hàng nào được trả về.
2. Có một hàng, nhưng một hoặc nhiều cột của hàng đó có giá trị SQL `NULL`.

Ví dụ, bảng `customer` có một hàng nhưng cột `nickname` là `NULL`. Truy vấn theo ID vẫn trả về một `Customer`; thuộc tính `nickname` có thể là `null` nếu kiểu Java và mapping cho phép.

Ngược lại, nếu không có hàng nào mang ID đó, repository `findById` trả về `Mono.empty()`.

```java
Mono<Customer> customer = customerRepository.findById(customerId);
```

- `Mono.just(customer)` có thể chứa object mà `customer.getNickname()` là `null`.
- `Mono.empty()` nghĩa là không có object `Customer` nào được phát ra.
- `onError` nghĩa là thao tác đọc không hoàn thành bình thường.

SQL dùng `IS NULL` để lọc cột null:

```sql
SELECT id, email
FROM customer
WHERE nickname IS NULL;
```

Biểu thức `nickname = NULL` không kiểm tra null theo logic SQL ba giá trị; kết quả của phép so sánh với `NULL` là unknown. Hãy dùng `IS NULL` hoặc `IS NOT NULL`.

## 3. Repository trả về Mono và Flux

Với repository reactive, kiểu trả về thể hiện số lượng kết quả mong đợi:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByTenantIdAndEmail(UUID tenantId, String email);

    Flux<Customer> findByTenantIdAndStatus(UUID tenantId, CustomerStatus status);
}
```

`findByTenantIdAndEmail` có thể hoàn tất rỗng nếu không có khách hàng phù hợp. `findByTenantIdAndStatus` có thể phát 0, 1 hoặc nhiều khách hàng; nếu không có hàng, `Flux` chỉ hoàn tất mà không phát phần tử.

Một lỗi kết nối hoặc lỗi SQL không biến thành publisher rỗng. Nó được phát dưới dạng lỗi để tầng gọi có thể ghi log, phân loại, retry khi phù hợp hoặc trả phản hồi lỗi cho client.

Nếu một truy vấn khai báo `Mono<T>` nhưng thực tế trả nhiều hàng, Spring Data có thể phát lỗi kích thước kết quả thay vì âm thầm chọn một hàng. Đừng dùng lỗi cardinality như một cách biểu diễn “không tìm thấy”; nó cho biết hợp đồng số lượng kết quả bị vi phạm.

## 4. Phân biệt bằng DatabaseClient

`DatabaseClient` cho phép quan sát trực tiếp cách truy vấn trả về dữ liệu:

```java
Mono<Customer> findCustomer(UUID tenantId, String email) {
    return databaseClient.sql("""
            SELECT id, tenant_id, email, nickname
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
            row.get("nickname", String.class)
        ))
        .one();
}
```

Với `.one()`:

- Không có hàng: publisher hoàn tất rỗng.
- Có một hàng: publisher phát một `Customer`.
- Có nhiều hơn một hàng: publisher phát lỗi kích thước kết quả.
- SQL hoặc kết nối thất bại: publisher phát lỗi database.

Nếu nghiệp vụ chỉ muốn lấy một hàng theo thứ tự ưu tiên, có thể dùng `.first()` nhưng cần `ORDER BY` rõ ràng trong SQL. `.first()` không xác nhận rằng chỉ có một hàng phù hợp; nó lấy hàng đầu tiên và bỏ qua các hàng còn lại. Không dùng `.first()` để che dữ liệu trùng khi query đáng lẽ phải duy nhất.

Nếu muốn đọc mọi hàng, dùng `.all()` để nhận `Flux<T>`:

```java
Flux<Customer> customers = databaseClient.sql("""
        SELECT id, email
        FROM customer
        WHERE tenant_id = :tenantId
        ORDER BY id
        """)
    .bind("tenantId", tenantId)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("email", String.class)))
    .all();
```

Nếu không có hàng phù hợp, `Flux` hoàn tất bình thường mà không phát phần tử. Consumer có thể dùng `switchIfEmpty` hoặc `hasElements` nếu cần một hành vi riêng cho trường hợp rỗng.

## 5. Dùng switchIfEmpty cho trường hợp không tìm thấy

`switchIfEmpty` chỉ chạy publisher thay thế khi publisher ban đầu hoàn tất mà không phát giá trị. Nó không bắt lỗi database.

Ví dụ chuyển kết quả rỗng thành lỗi nghiệp vụ `CustomerNotFoundException`:

```java
public Mono<Customer> getRequiredCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

Nếu `findById` trả về một customer, giá trị được chuyển tiếp. Nếu không có hàng, service phát lỗi not found. Nếu database mất kết nối, lỗi kết nối vẫn được truyền xuống consumer; `switchIfEmpty` không thay thế nó.

Có thể dùng `defaultIfEmpty` khi nghiệp vụ thực sự có giá trị mặc định:

```java
return settingsRepository.findById(userId)
    .defaultIfEmpty(UserSettings.defaultsFor(userId));
```

Chỉ dùng giá trị mặc định khi “không có cấu hình riêng” có ý nghĩa hợp lệ. Với dữ liệu bắt buộc như tài khoản, đơn hàng hoặc quyền truy cập, thay thế bằng object giả có thể che lỗi dữ liệu và gây hành vi sai.

## 6. Dùng onErrorResume có chọn lọc

`onErrorResume` xử lý đường lỗi. Chỉ nên dùng khi có thể xác định loại lỗi và có một cách phục hồi hợp lệ.

Ví dụ xử lý lỗi một cách có chọn lọc:

```java
return customerRepository.findById(id)
    .onErrorResume(CustomerReadUnavailableException.class, error ->
        cacheRepository.findCustomer(id)
    );
```

Ví dụ này giả định tầng persistence đã chuyển một loại lỗi cụ thể thành `CustomerReadUnavailableException`, và cache có thể cung cấp dữ liệu thay thế theo chính sách của hệ thống. Không nên fallback sang cache khi lỗi là SQL sai, mapping sai hoặc dữ liệu không tồn tại nếu các tình huống đó không được phép.

Không nên viết:

```java
return customerRepository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

Đoạn code trên biến mọi lỗi thành “không tìm thấy”. Các lỗi kết nối, timeout, quyền truy cập, lỗi schema, lỗi codec và lỗi cardinality đều bị che giấu. Caller không thể biết database đã thất bại.

Tương tự, `onErrorComplete()` biến lỗi thành hoàn tất bình thường mà không phát dữ liệu. Chỉ dùng khi nghiệp vụ cho phép bỏ qua lỗi cụ thể và đã có log/metric phù hợp; không dùng như một cách tổng quát để làm pipeline “không bao giờ lỗi”.

## 7. Phân loại lỗi ở tầng Spring và R2DBC SPI

Khi dùng `DatabaseClient`, Spring thường áp dụng exception translation để chuyển lỗi truy cập dữ liệu thành các kiểu `DataAccessException` phù hợp. Khi gọi R2DBC SPI trực tiếp, ứng dụng có thể nhận các exception thuộc `io.r2dbc.spi`, thường là `R2dbcException` hoặc lớp con.

Các nhóm lỗi thường gặp:

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Kết nối/tài nguyên tạm thời | Database restart, connection bị ngắt, pool không cấp được connection | Ghi log/metric, có thể retry giới hạn nếu thao tác an toàn. |
| Timeout | Query vượt thời gian, acquire connection timeout | Xác định timeout ở pool, driver hay database; không coi là không có dữ liệu. |
| SQL/schema | Sai cú pháp, thiếu bảng/cột, kiểu không tương thích | Sửa SQL hoặc migration; retry thường không giúp. |
| Quyền truy cập | Tài khoản database không có quyền | Sửa cấu hình quyền hoặc credentials; không fallback thành rỗng. |
| Constraint | Vi phạm unique, foreign key hoặc check constraint | Chuyển thành lỗi nghiệp vụ phù hợp nếu xác định được constraint. |
| Conversion/codec | Không đọc/ghi được kiểu Java hoặc kiểu cột | Kiểm tra mapping, converter và driver codec. |
| Cardinality | Truy vấn đơn kết quả trả nhiều hàng | Sửa điều kiện/constraint hoặc chọn API nhiều kết quả đúng ý nghĩa. |

Không nên phụ thuộc vào chuỗi message của exception để phân loại lỗi vì message có thể thay đổi theo driver, database và phiên bản. Khi cần phân loại chi tiết, xem exception type, SQL state, vendor error code và nguyên nhân gốc (`getCause()`) theo API thực tế.

## 8. Phân biệt không tìm thấy với không có hàng bị ảnh hưởng

Các thao tác ghi có semantics khác truy vấn đọc.

### 8.1 UPDATE hoặc DELETE không khớp hàng nào

Với `DatabaseClient`, `.fetch().rowsUpdated()` trả số hàng được cập nhật hoặc xóa:

```java
Mono<Long> updated = databaseClient.sql("""
        UPDATE customer
        SET display_name = :name
        WHERE id = :id
        """)
    .bind("name", name)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

Nếu câu lệnh chạy thành công nhưng không có hàng khớp, kết quả thường là `0`. Đây là một giá trị số bình thường, không phải `Mono.empty()` và không phải lỗi truy vấn. Nếu driver/database trả lỗi khi thực thi, publisher phát `onError`.

Service có thể diễn giải số hàng bị ảnh hưởng:

```java
return updated.flatMap(count -> {
    if (count == 0) {
        return Mono.error(new CustomerNotFoundException(id));
    }
    if (count != 1) {
        return Mono.error(new UnexpectedUpdateCountException(count));
    }
    return Mono.empty();
});
```

Với update theo ID, `count == 1` thường là kết quả mong đợi. Với update hàng loạt, số lượng lớn hơn một có thể hợp lệ và cần được xử lý theo nghiệp vụ.

### 8.2 Mono<Void> hoàn tất rỗng là thành công

Một phương thức trả `Mono<Void>` không phát phần tử khi hoàn tất thành công. Vì vậy, không thể suy ra “không có dữ liệu” từ việc một `Mono<Void>` không phát giá trị. Cần xem publisher đại diện cho thao tác gì và liệu lỗi có được phát hay không.

Ví dụ:

```java
Mono<Void> deleteCustomer(Long id) {
    return customerRepository.deleteById(id);
}
```

`deleteById` có thể hoàn tất thành công mà không phát giá trị. Nếu cần biết có hàng nào bị xóa, dùng API trả số hàng bị ảnh hưởng hoặc thực hiện truy vấn phù hợp; đừng diễn giải việc `Mono<Void>` rỗng là lỗi not found.

## 9. Aggregate query vẫn có hàng khi số lượng bằng 0

Một truy vấn `COUNT(*)` không giống truy vấn chọn entity. Ngay cả khi bảng không có hàng phù hợp, truy vấn aggregate không có `GROUP BY` vẫn trả một hàng với giá trị đếm bằng 0:

```sql
SELECT COUNT(*) AS total
FROM customer
WHERE tenant_id = :tenantId;
```

Do đó, `DatabaseClient.one()` cho truy vấn này thường phát một kết quả chứa `total = 0`, không phải `Mono.empty()`. Tương tự, `SUM` hoặc `AVG` có thể trả `NULL` khi không có giá trị đầu vào phù hợp, tùy biểu thức và database; đó là một hàng có cột null, không nhất thiết là không có hàng.

Nếu dùng `GROUP BY`, không có nhóm phù hợp thì kết quả có thể không có hàng. Cần hiểu semantics SQL của câu truy vấn thay vì chỉ dựa vào tên aggregate function.

## 10. LEFT JOIN và hàng có cột liên quan NULL

`LEFT JOIN` có thể trả một hàng bên trái dù không có hàng tương ứng bên phải. Các cột phía phải khi đó có giá trị SQL `NULL`:

```sql
SELECT c.id, c.email, p.id AS profile_id, p.bio
FROM customer c
LEFT JOIN customer_profile p ON p.customer_id = c.id
WHERE c.id = :id;
```

Nếu khách hàng tồn tại nhưng chưa có profile, truy vấn vẫn trả một hàng; `profile_id` và `bio` là null. Đây không phải `Mono.empty()`.

Nếu không có khách hàng với ID đó, toàn bộ truy vấn không trả hàng và `.one()` hoàn tất rỗng. Khi mapping DTO lồng nhau, cần kiểm tra `profile_id` trước khi tạo object profile, nếu không có thể tạo một profile giả với mọi thuộc tính null.

## 11. Retry không phải cách xử lý kết quả rỗng

Retry phù hợp với một số lỗi tạm thời đã xác định, chẳng hạn lỗi kết nối hoặc serialization conflict. Không retry một truy vấn chỉ vì không có hàng: database đã thực thi thành công và không tìm thấy dữ liệu tại thời điểm đó.

Ví dụ:

```java
return repository.findById(id)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientDatabaseFailure));
```

`isTransientDatabaseFailure` cần phân loại lỗi tạm thời theo exception type hoặc mã lỗi của driver/database. Không retry mọi exception và không dùng retry để che lỗi SQL hoặc dữ liệu không tồn tại.

Với truy vấn đọc, retry có thể cho kết quả khác nếu dữ liệu được tạo trong lúc chờ; hãy cân nhắc semantics nghiệp vụ. Với thao tác ghi, retry còn cần xem tính idempotent để tránh ghi trùng nếu server đã thực hiện lệnh nhưng client mất phản hồi.

## 12. Chuyển kết quả thành HTTP response

Ở tầng API, có thể ánh xạ các trường hợp theo quy tắc rõ ràng:

| Trạng thái persistence/service | Phản hồi API thường dùng |
|---|---|
| Tìm thấy tài nguyên | `200 OK` cùng representation, hoặc `204 No Content` cho thao tác không cần body. |
| Không có tài nguyên theo ID | `404 Not Found` nếu semantics endpoint là đọc tài nguyên bắt buộc. |
| Request hợp lệ nhưng không có kết quả tìm kiếm | `200 OK` với danh sách rỗng, nếu endpoint là tìm kiếm danh sách. |
| Xung đột nghiệp vụ/unique constraint | `409 Conflict` khi phù hợp với hợp đồng API. |
| Database tạm thời không khả dụng | Thường là `503 Service Unavailable` hoặc lỗi server phù hợp. |
| SQL/mapping/configuration bị lỗi | `500 Internal Server Error`; không trả `404`. |

Không phải mọi `Mono.empty()` đều phải chuyển thành HTTP 404. Với endpoint tìm kiếm nhiều kết quả, danh sách rỗng thường là phản hồi thành công. Với endpoint đọc một tài nguyên theo ID, `switchIfEmpty` có thể chuyển thành exception not found để exception handler ánh xạ sang 404.

Không gửi thông tin chi tiết như SQL, tên bảng, credentials hoặc stack trace cho client. Ghi log nội bộ với correlation ID và thông tin đủ để điều tra, đồng thời tránh ghi dữ liệu nhạy cảm.

## 13. Thiết kế service tách biệt empty và error

Một service có thể định nghĩa rõ hợp đồng trả về:

```java
public Mono<CustomerView> getCustomer(Long id) {
    return customerRepository.findById(id)
        .map(CustomerView::from)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorMap(
            DataAccessResourceFailureException.class,
            error -> new CustomerStoreUnavailableException(error)
        );
}
```

Trong ví dụ, trường hợp không có hàng trở thành lỗi nghiệp vụ not found. Một loại lỗi tài nguyên database cụ thể được chuyển thành lỗi service có ý nghĩa. Các lỗi khác tiếp tục truyền lên để được xử lý ở tầng exception handler phù hợp.

Trong thực tế, exception translation có thể khác theo cách gọi `DatabaseClient`, repository hoặc R2DBC SPI trực tiếp. Hãy dùng đúng exception type của phiên bản Spring đang chạy; không sao chép một class exception nếu dependency không cung cấp class đó. Nếu muốn có một abstraction ổn định, có thể định nghĩa exception riêng ở tầng persistence adapter và chỉ chuyển đổi các lỗi đã nhận diện.

## 14. Kiểm thử từng trạng thái riêng biệt

Một truy vấn đọc đơn kết quả nên có ít nhất ba kịch bản:

| Kịch bản | Dữ liệu/điều kiện | Kết quả cần xác nhận |
|---|---|---|
| Không tìm thấy | Không có hàng khớp điều kiện | `Mono.empty()` hoặc lỗi not found do service chủ động chuyển đổi. |
| Tìm thấy | Có đúng một hàng | Phát entity/DTO mong đợi. |
| Truy vấn thất bại | Database ngắt kết nối, SQL lỗi hoặc quyền bị từ chối | Publisher phát lỗi; không bị chuyển thành rỗng. |
| Nhiều hàng ngoài dự kiến | Query đơn kết quả trả hai hàng | Lỗi cardinality hoặc quy tắc chọn hàng được xác định rõ. |
| Cột null | Có hàng nhưng một cột là SQL `NULL` | Entity vẫn được phát, thuộc tính nullable được ánh xạ đúng. |

Với update/delete, kiểm tra thêm:

- `rowsUpdated = 0` khi không có hàng khớp.
- Số hàng dương khi có thay đổi.
- `onError` khi câu lệnh thất bại.
- `Mono<Void>` hoàn tất bình thường khi thao tác thành công nếu API được thiết kế như vậy.

Unit test có thể dùng `StepVerifier` để kiểm tra tín hiệu reactive:

```java
StepVerifier.create(service.getCustomer(404L))
    .expectError(CustomerNotFoundException.class)
    .verify();
```

Với lỗi database, có thể mô phỏng publisher lỗi để kiểm tra service không biến nó thành empty. Tuy nhiên, integration test trên database/driver thực tế vẫn cần thiết để xác nhận lỗi kết nối, SQL, constraint và mapping được phát ra như mong đợi.

## 15. Những anti-pattern cần tránh

| Anti-pattern | Vấn đề |
|---|---|
| `onErrorResume(error -> Mono.empty())` | Che tất cả lỗi database thành không tìm thấy. |
| `onErrorComplete()` trên toàn repository chain | Làm mất tín hiệu lỗi và có thể báo thành công giả. |
| Dùng `first()` cho query phải duy nhất | Che dữ liệu trùng hoặc điều kiện query thiếu. |
| Coi SQL `NULL` là `Mono.empty()` | Nhầm cột null trong một hàng với không có hàng. |
| Coi `rowsUpdated = 0` là lỗi kết nối | Nhầm thao tác thành công không ảnh hưởng hàng nào với lỗi thực thi. |
| Retry khi `Mono.empty()` | Lặp truy vấn không có cơ sở và có thể tạo tải không cần thiết. |
| Retry mọi exception | Lặp lỗi không thể phục hồi và có thể tạo side effect trùng. |
| Trả 404 cho mọi lỗi database | Che sự cố hạ tầng và làm sai hợp đồng HTTP. |

## 16. Quy trình xử lý kết quả truy vấn

Khi xây dựng một service truy cập dữ liệu, hãy xác định theo thứ tự:

1. Truy vấn được kỳ vọng trả về một hàng, nhiều hàng hay chỉ số liệu tổng hợp?
2. Không có hàng có phải là trạng thái nghiệp vụ hợp lệ hay phải chuyển thành not found?
3. Các cột có thể là SQL `NULL` không, và kiểu Java có biểu diễn được không?
4. API đang dùng (`one`, `first`, `all`, repository `Mono`/`Flux`) có semantics cardinality phù hợp không?
5. Lỗi kết nối, SQL, quyền, constraint, codec và cardinality được truyền hoặc chuyển đổi ở tầng nào?
6. Có retry được không, và điều kiện idempotency là gì?
7. Với thao tác ghi, cần phân biệt `rowsUpdated = 0`, số hàng dương và `onError` như thế nào?
8. API bên ngoài sẽ trả 404, danh sách rỗng, 409 hay lỗi server theo hợp đồng nào?

Không có dữ liệu và truy vấn thất bại là hai trạng thái độc lập. Hãy dùng `Mono.empty()`/`Flux` rỗng cho kết quả không có hàng, giữ `onError` cho lỗi thực thi, và dùng `rowsUpdated` để diễn giải tác động của lệnh ghi. Xử lý `switchIfEmpty` cho trường hợp not found và `onErrorResume` có chọn lọc cho lỗi có thể phục hồi sẽ giúp ứng dụng giữ đúng ý nghĩa dữ liệu, không che giấu sự cố database và trả phản hồi nhất quán cho tầng gọi.
