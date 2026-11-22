# saveAll, deleteAll và các giới hạn khi xử lý nhiều bản ghi

Spring Data R2DBC cung cấp `saveAll` và `deleteAll` để thao tác với nhiều entity thông qua reactive repository. Các phương thức này giúp mã ứng dụng ngắn gọn và giữ luồng dữ liệu ở dạng `Flux` hoặc `Mono`. Tuy nhiên, tên phương thức không có nghĩa mọi thao tác đều được thực hiện bằng một câu SQL bulk duy nhất, cũng không bảo đảm rằng tải và ghi hàng triệu bản ghi sẽ tự động tiết kiệm bộ nhớ.

Khi xử lý số lượng lớn, cần hiểu rõ biến thể API đang dùng, cách publisher được tiêu thụ, số kết nối và truy vấn phát sinh, giới hạn của database, transaction, backpressure và hành vi khi một phần tử gặp lỗi. Lựa chọn đúng giữa `saveAll`, `deleteAll`, truy vấn theo điều kiện, batch SQL và xử lý theo lô giúp kiểm soát tải và tránh thao tác ngoài ý muốn.

## 1. Các phương thức saveAll trong ReactiveCrudRepository

Một repository reactive thường kế thừa `ReactiveCrudRepository`:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

Repository cung cấp hai dạng `saveAll` phổ biến:

```java
<S extends T> Flux<S> saveAll(Iterable<S> entities);

<S extends T> Flux<S> saveAll(Publisher<S> entityStream);
```

Khác biệt chính nằm ở nguồn dữ liệu:

- `Iterable` là một tập phần tử có sẵn, thường là `List` hoặc collection đã được tạo trong bộ nhớ.
- `Publisher` phát phần tử theo mô hình reactive; nguồn có thể là một `Flux` được tạo từ file, API, message stream hoặc truy vấn khác.

Ví dụ với danh sách đã có:

```java
public Flux<Customer> saveCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Ví dụ với nguồn reactive:

```java
public Flux<Customer> importCustomers(Flux<Customer> customerStream) {
    return customerRepository.saveAll(customerStream);
}
```

Trong cả hai trường hợp, kết quả là `Flux<Customer>` phát ra những entity đã được lưu. Publisher chỉ thực hiện công việc khi được subscribe; chỉ gọi `saveAll` và bỏ qua kết quả không có nghĩa dữ liệu đã được ghi.

## 2. saveAll không đồng nghĩa với một câu bulk INSERT

`saveAll` là hợp đồng lưu nhiều entity. Nó không cam kết driver sẽ gửi một câu SQL duy nhất kiểu:

```sql
INSERT INTO customer (name, email)
VALUES
    ('An', 'an@example.com'),
    ('Binh', 'binh@example.com'),
    ('Chi', 'chi@example.com');
```

Spring Data R2DBC cần áp dụng quy tắc mapping và trạng thái entity cho từng phần tử. Trong triển khai repository phổ biến, các entity được đưa qua đường `save` theo thứ tự, vì vậy có thể phát sinh một thao tác insert hoặc update cho từng entity. Cách thực thi nội bộ có thể thay đổi theo phiên bản; hợp đồng `saveAll` không bảo đảm một bulk statement hoặc một round trip cho toàn bộ collection.

Điều này quan trọng vì 10.000 entity có thể tạo ra nhiều thao tác database riêng. Reactive API giúp nối các thao tác và điều tiết việc tiêu thụ, nhưng không tự biến chúng thành một lệnh ghi bulk tối ưu.

Nếu yêu cầu là import số lượng rất lớn với throughput cao, cần cân nhắc:

- SQL multi-row insert nếu database hỗ trợ và giới hạn số tham số cho phép.
- Batch hoặc prepared statement phù hợp với R2DBC driver.
- Cơ chế bulk load riêng của database, chẳng hạn giao thức COPY của PostgreSQL.
- Chia dữ liệu thành các lô có kích thước giới hạn.

Lựa chọn nào phù hợp phụ thuộc database, driver, yêu cầu mapping, generated ID, auditing và optimistic locking.

## 3. saveAll vẫn áp dụng trạng thái mới/cũ của từng entity

Khi gọi `saveAll`, mỗi entity vẫn phải có trạng thái persistence phù hợp. Spring Data nhận diện entity mới hay đã tồn tại theo cơ chế của nó: thường dựa trên `@Version` nếu có, nếu không thì dựa trên `@Id`, hoặc theo `Persistable.isNew()`.

Ví dụ:

```java
List<Customer> customers = List.of(
        new Customer(null, "An", "an@example.com"),
        new Customer(null, "Binh", "binh@example.com"),
        new Customer(existingId, "Chi Nguyen", "chi@example.com")
);

Flux<Customer> saved = customerRepository.saveAll(customers);
```

Hai entity đầu có ID null nên thường được nhận diện là mới và đi theo nhánh insert. Entity cuối có ID khác null nên thường được nhận diện là đã tồn tại và đi theo nhánh update, nếu không có `@Version` hoặc `Persistable` thay đổi quy tắc.

ID khác null không chứng minh hàng đó đang tồn tại trong database. Nếu nghiệp vụ cần tạo mới với UUID được gán sẵn, hãy cấu hình trạng thái mới bằng `@Version`, `Persistable` hoặc thao tác insert tường minh. Không nên dùng `saveAll` như một lệnh upsert tự động.

Với entity có `@Version`, mỗi lần cập nhật có thể phát sinh kiểm tra optimistic locking. Một entity dùng version cũ có thể làm thao tác lưu thất bại nếu hàng đã được cập nhật bởi transaction khác.

## 4. Xử lý nguồn dữ liệu lớn bằng Publisher

Nếu dữ liệu đầu vào đã nằm trong một `List` rất lớn, chuyển nó sang `Flux.fromIterable(list)` không làm danh sách ban đầu biến mất khỏi bộ nhớ. Toàn bộ collection vẫn đã được nạp trước.

Ví dụ:

```java
List<Customer> allCustomers = loadAllCustomersIntoMemory();

return customerRepository.saveAll(Flux.fromIterable(allCustomers));
```

Đoạn mã này có publisher reactive nhưng nguồn dữ liệu vẫn là một danh sách đã materialize.

Nếu dữ liệu có thể đọc theo luồng, hãy tạo publisher từ nguồn streaming:

```java
Flux<Customer> parsedCustomers = customerFileReader.readRows();

return customerRepository.saveAll(parsedCustomers);
```

Nguồn `customerFileReader.readRows()` ở đây đại diện cho một publisher đọc dữ liệu tăng dần, không tạo toàn bộ danh sách trước. Cần bảo đảm chính thư viện đọc file cũng hỗ trợ streaming; nếu nó đọc toàn bộ file vào bộ nhớ rồi mới phát `Flux`, lợi ích này không đạt được.

Backpressure của Reactive Streams cho phép subscriber báo nhu cầu phần tử. Tuy nhiên, cách driver, parser và repository buffer dữ liệu còn phụ thuộc triển khai. Không nên coi việc dùng `Flux` là bảo đảm bộ nhớ luôn cố định. Hãy kiểm soát kích thước nguồn, prefetch, batch và lượng dữ liệu đang được giữ ở mỗi tầng.

## 5. Ví dụ import theo lô có giới hạn

Một cách phổ biến là chia nguồn thành từng lô nhỏ, rồi lưu mỗi lô:

```java
public Flux<Customer> importCustomers(Flux<Customer> source) {
    return source
            .buffer(500)
            .concatMap(customerRepository::saveAll);
}
```

Ở đây:

- `buffer(500)` gom tối đa 500 entity thành một danh sách.
- `concatMap` xử lý từng danh sách theo thứ tự, đợi publisher của lô hiện tại hoàn tất rồi mới chuyển sang lô kế tiếp.
- Mỗi lần chỉ giữ một lô đang xử lý ở cấp pipeline này, cộng với buffer/prefetch của nguồn và các thành phần bên dưới.

Kích thước 500 chỉ là ví dụ. Lô nhỏ làm giảm lượng dữ liệu giữ trong bộ nhớ và giới hạn phạm vi lỗi, nhưng tăng số lần khởi tạo batch. Lô lớn giảm số lần điều phối nhưng có thể tăng bộ nhớ, thời gian giữ transaction và số lượng tham số nếu dùng SQL bulk.

Nếu muốn xử lý các lô đồng thời, có thể dùng `flatMap` với giới hạn concurrency:

```java
public Flux<Customer> importCustomersConcurrently(Flux<Customer> source) {
    return source
            .buffer(500)
            .flatMap(customerRepository::saveAll, 2);
}
```

Ví dụ này cho phép tối đa hai publisher lưu lô chạy đồng thời. Cần đo tải database trước khi tăng concurrency. Xử lý đồng thời có thể thay đổi thứ tự kết quả, tăng số connection đang dùng và làm xung đột với transaction hoặc constraint. Nếu thứ tự ghi là yêu cầu nghiệp vụ, ưu tiên `concatMap` hoặc một chiến lược giữ thứ tự rõ ràng.

## 6. Transaction khi lưu nhiều entity

Một câu hỏi quan trọng là: nếu entity thứ 80 trong một lô 100 entity bị lỗi, 79 entity trước đó có được lưu không?

Điều đó phụ thuộc transaction boundary. Nếu các thao tác không nằm trong cùng một transaction, những thao tác đã commit có thể vẫn tồn tại khi một phần tử sau đó thất bại. Không nên mặc định toàn bộ `saveAll` là một transaction nguyên tử chỉ vì nó trả về một `Flux`.

Nếu nghiệp vụ yêu cầu toàn bộ một lô thành công hoặc thất bại cùng nhau, có thể đặt thao tác lưu trong reactive transaction:

```java
@Transactional
public Flux<Customer> saveBatch(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Spring cần transaction manager R2DBC phù hợp và publisher phải được trả về trong cùng luồng để transaction interceptor quản lý việc subscribe, commit hoặc rollback. Không tự gọi `subscribe()` bên trong phương thức vì như vậy công việc có thể tách khỏi transaction được quản lý.

Với dữ liệu lớn, không nhất thiết phải bọc toàn bộ import hàng triệu dòng trong một transaction dài. Transaction dài giữ connection và có thể giữ khóa, tăng log và gây áp lực lên database. Một chiến lược thường dùng là transaction theo từng lô: mỗi lô là một đơn vị commit/rollback độc lập. Khi một lô lỗi, các lô đã commit trước đó vẫn tồn tại và cần có quy trình tiếp tục hoặc đối soát.

## 7. Xử lý lỗi trong saveAll

Một lỗi có thể xuất hiện khi:

- Dữ liệu vi phạm `NOT NULL`, unique hoặc foreign key.
- Giá trị không tương thích kiểu cột.
- Entity có ID trùng khi insert.
- Optimistic locking phát hiện version đã thay đổi.
- Kết nối bị ngắt hoặc database timeout.
- Một converter hoặc callback mapping phát sinh lỗi.

Khi một publisher lưu entity phát lỗi, luồng `saveAll` thường kết thúc bằng lỗi và không tiếp tục phát các entity sau đó. Những entity đã được xử lý trước lỗi có thể đã được ghi nếu không có transaction bao trùm.

Có thể xử lý lỗi ở ranh giới service:

```java
public Flux<Customer> importCustomers(Flux<Customer> source) {
    return customerRepository.saveAll(source)
            .doOnError(error ->
                    log.error("Customer import failed", error)
            );
}
```

Không nên dùng `onErrorResume(error -> Flux.empty())` một cách máy móc để biến toàn bộ lỗi thành hoàn tất bình thường. Làm như vậy có thể che giấu việc import chỉ hoàn thành một phần.

Nếu muốn tiếp tục với phần tử hợp lệ và ghi nhận phần tử lỗi, cần thiết kế luồng xử lý từng phần tử riêng, phân loại lỗi có thể bỏ qua, lưu kết quả lỗi vào báo cáo và bảo đảm retry không tạo bản ghi trùng. Với thao tác ghi, retry cần tính đến việc lần ghi trước có thể đã thành công ở database nhưng phản hồi bị mất.

## 8. Các biến thể deleteAll của repository

`ReactiveCrudRepository` có nhiều phương thức xóa. Chúng không có cùng ý nghĩa:

```java
Mono<Void> deleteAll();

Mono<Void> deleteAll(Iterable<? extends T> entities);

Mono<Void> deleteAll(Publisher<? extends T> entityStream);

Mono<Void> deleteAllById(Iterable<? extends ID> ids);

Mono<Void> deleteAllById(Publisher<? extends ID> idStream);
```

Ý nghĩa:

| Phương thức | Phạm vi xóa |
| --- | --- |
| `deleteAll()` | Xóa toàn bộ hàng thuộc entity/table của repository |
| `deleteAll(Iterable)` | Xóa các entity được cung cấp |
| `deleteAll(Publisher)` | Tiêu thụ publisher và xóa các entity được phát ra |
| `deleteAllById(Iterable)` | Xóa các hàng có ID trong tập được cung cấp |
| `deleteAllById(Publisher)` | Tiêu thụ publisher ID và xóa các hàng tương ứng |

Đặc biệt, `deleteAll()` không có điều kiện có thể xóa toàn bộ dữ liệu của bảng được repository quản lý. Hãy kiểm tra đúng repository và môi trường trước khi gọi. Không dùng nó như một phương thức xóa một số bản ghi theo filter.

## 9. deleteAll() khác deleteAll(entities) và deleteAllById(ids)

### Xóa toàn bộ bảng qua repository

```java
public Mono<Void> clearAllCustomers() {
    return customerRepository.deleteAll();
}
```

Đây là thao tác xóa toàn bộ hàng của bảng tương ứng. Tùy implementation Spring Data R2DBC, thao tác này thường được chuyển thành lệnh delete không có điều kiện cho entity type. Nó không tương đương `TRUNCATE TABLE`: `TRUNCATE` là lệnh DDL/DML riêng với ngữ nghĩa về identity, khóa và foreign key khác nhau.

### Xóa các entity đã biết

```java
public Mono<Void> deleteCustomers(List<Customer> customers) {
    return customerRepository.deleteAll(customers);
}
```

Phương thức này chỉ nhắm đến các entity trong collection. Triển khai repository có thể xử lý từng entity theo đường delete tương ứng; không nên giả định một câu SQL `DELETE ... WHERE id IN (...)` được sinh ra.

### Xóa theo danh sách ID

```java
public Mono<Void> deleteCustomersById(List<Long> ids) {
    return customerRepository.deleteAllById(ids);
}
```

Biến thể này phù hợp khi ứng dụng chỉ có định danh, không cần tải entity trước. Nó tránh một lượt đọc để lấy entity rồi mới xóa. Tuy nhiên, cách thực thi và số câu SQL vẫn phụ thuộc implementation; API không hứa rằng mọi ID được gom thành một câu `IN` duy nhất.

## 10. Xóa theo Publisher để xử lý luồng ID lớn

Khi danh sách ID được tạo từ một nguồn reactive, có thể truyền trực tiếp publisher:

```java
public Mono<Void> deleteCustomers(Flux<Long> customerIds) {
    return customerRepository.deleteAllById(customerIds);
}
```

Ví dụ, ID có thể đến từ một truy vấn chọn các khách hàng hết hạn, một file import hoặc một stream sự kiện. Dùng publisher tránh yêu cầu tạo một `List<Long>` rất lớn trước khi bắt đầu.

Tuy nhiên, publisher đầu vào cần được thiết kế có giới hạn. Nếu nguồn phát vô hạn hoặc không có điều kiện kết thúc, thao tác xóa có thể tiếp tục chạy vô thời hạn. Hãy lọc và giới hạn nguồn, hoặc dùng một truy vấn xóa theo điều kiện ở database nếu mục tiêu là xóa tất cả hàng thỏa tiêu chí.

Với `deleteAll(Publisher<T>)`, publisher phát entity cần xóa. Nếu đã có ID, `deleteAllById(Publisher<ID>)` diễn đạt ý định rõ hơn và tránh phải tải entity.

## 11. Xóa hàng loạt theo điều kiện bằng template

Nếu yêu cầu là “xóa tất cả bản ghi có trạng thái EXPIRED”, không cần đọc từng entity thành Java rồi gọi `deleteAll`. Có thể dùng `R2dbcEntityTemplate` để tạo một câu delete theo điều kiện:

```java
public Mono<Long> deleteExpiredSessions() {
    Query query = Query.query(
            Criteria.where("status").is("EXPIRED")
    );

    return template.delete(Session.class)
            .matching(query)
            .all();
}
```

Template trả số hàng bị ảnh hưởng, hữu ích khi cần biết có bao nhiêu hàng đã bị xóa. Repository `deleteAll()` trả `Mono<Void>`, chỉ biểu diễn hoàn tất hoặc lỗi, không cung cấp số lượng hàng.

Một truy vấn xóa theo điều kiện có thể được database thực thi như một câu SQL duy nhất, ví dụ:

```sql
DELETE FROM session
WHERE status = 'EXPIRED';
```

Điều này thường hiệu quả hơn việc select tất cả session hết hạn rồi gửi từng entity về ứng dụng để xóa. Hãy cân nhắc foreign key, trigger và khối lượng transaction trước khi xóa một tập rất lớn.

## 12. Giới hạn khi xử lý nhiều bản ghi

### Bộ nhớ

Tải tất cả entity vào `List` trước khi lưu hoặc xóa có thể làm heap tăng mạnh. Dùng publisher streaming, phân trang hoặc buffer có kích thước giới hạn.

### Số lượng round trip

`saveAll` và các biến thể delete theo entity/ID không cam kết bulk statement. Nếu mỗi phần tử dẫn đến một thao tác riêng, thời gian mạng và chi phí database có thể đáng kể.

### Kích thước câu lệnh và tham số

Nếu tự tạo SQL dạng `IN (...)` hoặc multi-row insert, database và driver có giới hạn số tham số, độ dài câu lệnh và packet. Chia thành batch có kích thước phù hợp.

### Connection pool

Một import dài hoặc nhiều batch đồng thời có thể chiếm nhiều connection. Nếu xử lý song song vượt quá khả năng pool, request khác có thể phải chờ hoặc gặp acquire timeout. Điều chỉnh concurrency cùng với kích thước pool và giới hạn database.

### Transaction và khóa

Transaction dài có thể giữ connection, khóa hàng và làm tăng lượng transaction log. Chia thành transaction theo lô nếu nghiệp vụ cho phép commit từng phần.

### Foreign key và trigger

Delete nhiều hàng có thể bị ràng buộc bởi foreign key, trigger hoặc cascade. Database có thể từ chối xóa hoặc thực hiện thêm thao tác liên quan. Hãy hiểu schema trước khi gọi `deleteAll()`.

### Cancellation

Nếu subscriber hủy publisher, các thao tác chưa thực hiện có thể không tiếp tục, nhưng những thao tác đã commit vẫn có thể còn hiệu lực nếu không có transaction bao trùm. Hệ thống import cần lưu trạng thái tiến trình để có thể tiếp tục hoặc đối soát sau cancellation.

## 13. saveAll và batch SQL: khi nào dùng cách nào?

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Lưu một tập entity vừa phải, cần mapping/auditing/version | `repository.saveAll(...)` |
| Đọc nguồn đầu vào theo luồng | `saveAll(Publisher)` |
| Import lớn cần giới hạn bộ nhớ | Publisher + `buffer(n)` + xử lý theo lô |
| Cần concurrency có kiểm soát | Buffer + `flatMap(..., concurrency)`, sau khi đo tải |
| Bulk insert throughput cao | SQL multi-row, batch hoặc native bulk load |
| Xóa toàn bộ bảng | `repository.deleteAll()`, chỉ khi thực sự muốn xóa toàn bộ |
| Xóa một tập ID đã biết | `deleteAllById(...)` |
| Xóa hàng thỏa điều kiện | Derived delete query hoặc template delete theo Query |
| Cần số hàng đã xóa | Template delete trả số hàng bị ảnh hưởng |

### Ví dụ dùng SQL multi-row insert

Với database hỗ trợ, có thể ghi nhiều hàng trong một câu lệnh:

```sql
INSERT INTO customer (name, email)
VALUES
    (:name1, :email1),
    (:name2, :email2),
    (:name3, :email3);
```

Đây chỉ là hình dạng SQL minh họa; cách bind danh sách tham số động và cú pháp hỗ trợ phụ thuộc database/driver. Cần giới hạn kích thước batch để không vượt giới hạn tham số hoặc packet.

### Ví dụ dùng R2DBC Statement batch

R2DBC SPI có `Batch` để gom nhiều câu SQL độc lập, và `Statement` có thể hỗ trợ thêm nhiều lần thực thi cùng mẫu statement. Tuy nhiên, `Batch.add(String)` nhận chuỗi SQL, không phải cơ chế bind nhiều bộ tham số cho cùng một statement. Khi cần bind tham số, hãy xem API `Statement.add()` và khả năng driver cụ thể, hoặc dùng SQL multi-row phù hợp.

Batch không tự động bảo đảm tính nguyên tử. Nếu toàn bộ batch cần commit/rollback cùng nhau, hãy đặt nó trong transaction phù hợp.

## 14. Xóa và lưu theo lô an toàn

Một quy trình import có thể gồm các bước:

1. Đọc nguồn theo luồng.
2. Kiểm tra và chuẩn hóa dữ liệu theo lô nhỏ.
3. Ghi từng lô trong transaction ngắn.
4. Lưu tiến độ hoặc checkpoint sau mỗi lô.
5. Ghi nhận lỗi của phần tử không hợp lệ để xử lý lại.
6. Có cơ chế idempotency để chạy lại không tạo dữ liệu trùng.

Quy trình xóa dữ liệu cũ có thể tương tự:

1. Chọn phạm vi dữ liệu cần xóa bằng điều kiện xác định.
2. Nếu số lượng lớn, xác định kích thước lô và thứ tự xóa phù hợp với foreign key.
3. Xóa theo điều kiện hoặc theo lô ID.
4. Ghi nhận số lượng đã xóa và thời điểm xử lý.
5. Có thể chạy lại an toàn khi điều kiện và nghiệp vụ cho phép.

Nếu dùng `deleteAll()` toàn bảng, cần đặc biệt cẩn thận với môi trường production. Có thể yêu cầu quyền hạn riêng, xác nhận phạm vi tenant hoặc dùng một service method có tên thể hiện rõ ý định xóa toàn bộ. Không đưa thao tác xóa toàn bảng vào endpoint có thể bị gọi tùy tiện.

## 15. Kiểm thử saveAll và deleteAll

Integration test nên kiểm tra cả kết quả và trường hợp lỗi:

### Kiểm tra saveAll

```java
StepVerifier.create(customerRepository.saveAll(List.of(
                new Customer(null, "An", "an@example.com"),
                new Customer(null, "Binh", "binh@example.com")
        )))
        .expectNextCount(2)
        .verifyComplete();
```

Sau đó có thể truy vấn lại để xác nhận hai hàng đã được lưu. Không chỉ kiểm tra số phần tử publisher phát ra nếu mục tiêu test là xác nhận dữ liệu thực sự tồn tại trong database.

### Kiểm tra deleteAllById

```java
Mono<Void> deletion = customerRepository.deleteAllById(List.of(id1, id2));

StepVerifier.create(deletion)
        .verifyComplete();

StepVerifier.create(customerRepository.findAllById(List.of(id1, id2)))
        .verifyComplete();
```

Ví dụ giả định `id1` và `id2` tồn tại trước khi xóa. Test thứ hai xác nhận không còn entity tương ứng.

### Kiểm tra lỗi một phần tử

Tạo dữ liệu có một phần tử vi phạm unique constraint ở giữa lô và quan sát:

- Publisher kết thúc bằng lỗi hay tiếp tục theo chính sách đã thiết kế.
- Những phần tử trước lỗi có còn tồn tại khi không có transaction hay không.
- Khi có transaction bao trùm, các thay đổi có được rollback như mong đợi không.
- Việc retry có tạo bản ghi trùng hoặc làm sai tiến độ import không.

Test transaction cần chạy với transaction manager reactive và database tương thích. Mock repository không thể chứng minh hành vi rollback của database thật.

## 16. Các nhầm lẫn thường gặp

1. **Cho rằng saveAll là một bulk INSERT.** API không bảo đảm một SQL statement hoặc một round trip.
2. **Đưa List lớn vào saveAll rồi cho rằng đã streaming.** List đã nằm trong bộ nhớ trước khi publisher bắt đầu.
3. **Cho rằng saveAll luôn lưu song song.** Triển khai có thể xử lý tuần tự; concurrency cần được thiết kế và giới hạn rõ ràng.
4. **Giả định toàn bộ saveAll tự động nguyên tử.** Transaction boundary quyết định khả năng rollback toàn bộ.
5. **Dùng deleteAll() khi chỉ muốn xóa một số bản ghi.** Phương thức không điều kiện xóa toàn bộ hàng của entity/table.
6. **Cho rằng deleteAll(entities) dùng một câu DELETE IN.** Không có bảo đảm như vậy trong hợp đồng API.
7. **Gom mọi ID vào một câu IN rất lớn.** Có thể vượt giới hạn tham số hoặc làm truy vấn kém hiệu quả.
8. **Xóa hàng loạt mà không xét foreign key.** Database có thể từ chối hoặc cascade sang dữ liệu khác.
9. **Nuốt lỗi bằng onErrorResume rồi báo import thành công.** Có thể che giấu kết quả chỉ được ghi một phần.
10. **Retry ghi mà không có idempotency.** Một thao tác có thể đã thành công dù client chưa nhận được phản hồi.
11. **Tăng concurrency mà không theo dõi pool.** Có thể làm pool đầy và database quá tải.
12. **Dùng deleteAll để thay cho TRUNCATE.** Hai lệnh có ngữ nghĩa và ràng buộc khác nhau.

## Quy tắc lựa chọn nhanh

- Dùng `saveAll(Iterable)` cho tập entity vừa phải đã có trong bộ nhớ.
- Dùng `saveAll(Publisher)` khi nguồn dữ liệu có thể phát theo luồng.
- Dùng `buffer(n)` để giới hạn kích thước lô; chọn `concatMap` nếu cần xử lý tuần tự.
- Chỉ tăng concurrency sau khi đo throughput, connection pool và tải database.
- Dùng transaction theo lô nếu cần rollback các thao tác trong cùng lô.
- Dùng `deleteAll()` chỉ khi chủ đích xóa toàn bộ hàng của repository.
- Dùng `deleteAllById` khi đã có ID; dùng template delete theo Query khi cần xóa theo điều kiện và nhận số hàng bị ảnh hưởng.
- Dùng SQL batch hoặc native bulk load khi cần hiệu năng bulk thực sự và đã xác nhận giới hạn driver/database.
- Thiết kế logging, checkpoint, idempotency và retry để xử lý lỗi hoặc cancellation giữa chừng.

`saveAll` và `deleteAll` là các API thuận tiện để xử lý nhiều entity trong mô hình reactive, nhưng hiệu quả và tính nguyên tử phụ thuộc cách triển khai, transaction, nguồn dữ liệu và database. Hãy phân biệt rõ xóa toàn bảng với xóa theo danh sách hoặc điều kiện; phân biệt lưu nhiều entity với bulk SQL; và giới hạn kích thước lô, concurrency cùng thời gian transaction. Khi khối lượng dữ liệu lớn, một pipeline có backpressure, checkpoint và chiến lược lỗi rõ ràng sẽ dễ vận hành hơn việc nạp toàn bộ dữ liệu vào bộ nhớ rồi thực hiện một thao tác không giới hạn.
