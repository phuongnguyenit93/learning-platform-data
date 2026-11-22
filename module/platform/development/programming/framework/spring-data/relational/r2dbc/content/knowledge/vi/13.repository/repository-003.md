# Kiểu trả về Mono, Flux và hợp đồng không có kết quả

Trong Spring Data Relational R2DBC, repository truy cập database theo kiểu reactive. Vì vậy, phương thức repository thường trả về một publisher thay vì trả ngay một entity, một danh sách hoặc null. Kiểu trả về là một phần của hợp đồng API: nó cho biết phương thức có thể phát ra bao nhiêu kết quả, trường hợp không có kết quả được biểu diễn thế nào và lỗi được truyền tới tầng gọi ra sao.

Hai kiểu Reactor thường dùng là `Mono<T>` và `Flux<T>`:

- `Mono<T>` biểu diễn từ không đến một phần tử.
- `Flux<T>` biểu diễn từ không đến nhiều phần tử.

Cả hai đều có thể hoàn tất bình thường mà không phát ra dữ liệu. Publisher rỗng không đồng nghĩa với lỗi database. Một truy vấn không tìm thấy hàng phù hợp thường là kết quả hợp lệ; lỗi kết nối, lỗi SQL hoặc lỗi ánh xạ được truyền bằng tín hiệu lỗi riêng.

Bài học này giải thích cách chọn kiểu trả về cho repository, cách định nghĩa hợp đồng khi không có dữ liệu, sự khác nhau giữa truy vấn một kết quả và nhiều kết quả, vai trò của `Mono<Void>`, cũng như cách giữ reactive chain từ repository tới service và API.

## 1. Hợp đồng kết quả của một phương thức repository

Khi thiết kế phương thức đọc dữ liệu, trước hết cần xác định cardinality — số phần tử mà phương thức có thể trả về.

| Nhu cầu nghiệp vụ | Kiểu trả về thường dùng | Hợp đồng |
|---|---|---|
| Tìm một entity theo khóa, có thể không tồn tại | `Mono<T>` | Không có hoặc có đúng một entity |
| Tìm nhiều entity theo điều kiện | `Flux<T>` | Có thể không có, có một hoặc nhiều entity |
| Chỉ kiểm tra tồn tại | `Mono<Boolean>` | Phát `true` hoặc `false` |
| Đếm số hàng | `Mono<Long>` | Phát số lượng, kể cả `0` |
| Thực hiện lệnh không cần dữ liệu trả về | `Mono<Void>` | Hoàn tất thành công hoặc kết thúc bằng lỗi |
| Lấy danh sách nhỏ đã thu thập | `Mono<List<T>>` ở tầng xử lý | Phát một list, có thể là list rỗng |

Kiểu trả về không chỉ phục vụ cú pháp Java. Nó thông báo cho người gọi biết cần xử lý trường hợp không có dữ liệu như thế nào.

Ví dụ, `findById` trả `Mono<Customer>` vì một khóa chính chỉ xác định tối đa một hàng. `findByCity` trả `Flux<Customer>` vì một thành phố có thể có nhiều khách hàng. Nếu hai phương thức đổi kiểu trả về cho nhau, hợp đồng của chúng sẽ không còn thể hiện đúng nghiệp vụ.

## 2. Mono: từ không đến một phần tử

`Mono<T>` là publisher có thể phát tối đa một phần tử kiểu `T`, sau đó hoàn tất. Nó có ba kết quả cơ bản:

1. Phát một phần tử rồi hoàn tất.
2. Hoàn tất rỗng, không phát phần tử.
3. Kết thúc bằng lỗi.

Sơ đồ:

~~~text
Mono<Customer>
    |
    +---- onNext(Customer) ---- onComplete
    |
    +------------------------- onComplete (empty)
    |
    +------------------------- onError(exception)
~~~

Ví dụ repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);
}
~~~

`findByEmail` thể hiện ý định tìm tối đa một khách hàng theo email. Nếu email không tồn tại, kết quả là `Mono.empty()`. Nếu email được kỳ vọng duy nhất, database cũng cần có unique constraint để bảo vệ quy tắc đó.

### 2.1. Mono không có nghĩa là chắc chắn có một kết quả

Một hiểu lầm thường gặp là thấy `Mono<Customer>` rồi cho rằng phương thức luôn trả về một `Customer`. Thực tế, `Mono<T>` cho phép không có phần tử. Nó không phải cam kết "luôn đúng một".

Ví dụ:

~~~java
Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Nếu ID không tồn tại, publisher hoàn tất rỗng. Người gọi phải quyết định trường hợp đó là bình thường, cần dùng giá trị mặc định hay cần báo lỗi nghiệp vụ.

Nếu use case yêu cầu entity bắt buộc phải có, có thể chuyển kết quả rỗng thành lỗi:

~~~java
Mono<Customer> requireCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Tách hợp đồng này ở tầng service giúp repository tiếp tục mô tả đúng trạng thái database: có hàng hoặc không có hàng. Service mới quyết định rằng thiếu khách hàng là điều không được chấp nhận trong use case cụ thể.

### 2.2. Mono cho truy vấn kỳ vọng một hàng

Các phương thức tìm theo khóa chính thường trả `Mono<T>`. Derived query cũng có thể dùng `Mono<T>` khi điều kiện được kỳ vọng khớp tối đa một hàng:

~~~java
Mono<Customer> findByEmail(String email);

Mono<Order> findByOrderNumber(String orderNumber);
~~~

Nếu điều kiện không được database bảo đảm duy nhất và có nhiều hàng phù hợp, truy vấn đơn có thể thất bại vì số lượng kết quả vượt quá một. Không nên trông chờ framework tự chọn một hàng tùy ý.

Khi tính duy nhất là quy tắc dữ liệu, hãy thể hiện nó bằng `PRIMARY KEY` hoặc `UNIQUE` constraint. Kiểu trả về `Mono<T>` mô tả kỳ vọng của ứng dụng; constraint bảo vệ dữ liệu trước mọi request đồng thời và mọi đường ghi.

### 2.3. Mono cho giá trị đơn không phải entity

`Mono` cũng phù hợp cho kết quả đơn giản như boolean, số lượng hoặc projection:

~~~java
Mono<Boolean> existsByEmail(String email);

Mono<Long> countByActiveTrue();

Mono<BigDecimal> findTotalAmountByCustomerId(Long customerId);
~~~

Một phép đếm không có hàng phù hợp thường phát `0L`, chứ không hoàn tất rỗng. Một phép kiểm tra tồn tại phát `false` nếu không có hàng. Cần chọn kiểu trả về phản ánh chính xác kết quả của câu truy vấn.

## 3. Flux: từ không đến nhiều phần tử

`Flux<T>` có thể phát ra không, một hoặc nhiều phần tử, rồi hoàn tất; hoặc kết thúc bằng lỗi. Nó phù hợp với truy vấn tập hợp:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByCity(String city);

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByLastNameContaining(String keyword);
}
~~~

Một truy vấn theo thành phố có thể trả về nhiều khách hàng. Nếu không có ai ở thành phố đó, `Flux<Customer>` hoàn tất rỗng.

### 3.1. Flux rỗng là một kết quả hợp lệ

Ví dụ:

~~~java
Flux<Customer> customers =
        customerRepository.findByCity("Hue");
~~~

Nếu database không có khách hàng nào ở Huế, `customers` không phát `Customer` nào nhưng vẫn hoàn tất bình thường. Tầng gọi có thể trả danh sách rỗng hoặc tiếp tục một luồng xử lý không cần dữ liệu.

Không cần biến mọi `Flux` rỗng thành lỗi. Với tìm kiếm, lọc hoặc danh sách, không có kết quả thường là trạng thái bình thường.

### 3.2. Flux phát từng phần tử

`Flux` cho phép xử lý từng hàng khi hàng đó sẵn sàng, thay vì phải chờ gom toàn bộ kết quả thành một danh sách. Ví dụ:

~~~java
Flux<CustomerSummary> summaries =
        customerRepository.findByCity("Hue")
                .map(CustomerSummary::from);
~~~

Nếu cần gọi một publisher khác cho từng entity, nối publisher bằng toán tử reactive:

~~~java
Flux<CustomerReport> reports =
        customerRepository.findByCity("Hue")
                .flatMap(reportService::createReport);
~~~

`flatMap` có thể chạy nhiều publisher con đồng thời và không bảo đảm thứ tự phát giống thứ tự nguồn. Nếu cần xử lý tuần tự và giữ thứ tự, cân nhắc `concatMap`. Nếu cần giới hạn số thao tác đồng thời, dùng overload có tham số concurrency phù hợp.

Không gọi `subscribe()` bên trong `map` hoặc `flatMap`. Callback cần trả về publisher để Reactor quản lý toàn bộ chuỗi, lỗi và quá trình hủy.

### 3.3. Thu thập Flux thành danh sách khi thật sự cần

Nếu tầng gọi cần một list hữu hạn và tập kết quả đã được giới hạn hợp lý, có thể dùng `collectList()`:

~~~java
Mono<List<Customer>> findCustomersAsList(String city) {
    return customerRepository.findByCity(city)
            .collectList();
}
~~~

Khi nguồn không phát phần tử nào, `collectList()` vẫn phát một list rỗng:

~~~text
Flux<Customer> rỗng
       |
       | collectList()
       v
Mono<List<Customer>>
       |
       v
List<Customer> = []
~~~

Đây là khác biệt giữa `Mono<Customer>` và `Mono<List<Customer>>`:

- `Mono<Customer>` có thể hoàn tất rỗng nếu không có khách hàng.
- `Mono<List<Customer>>` sau `collectList()` phát một list; list đó có thể rỗng.

Không thu thập một `Flux` không giới hạn hoặc rất lớn thành list. Toàn bộ phần tử sẽ được giữ trong bộ nhớ cho tới khi nguồn hoàn tất. Với dữ liệu lớn, hãy xử lý từng phần tử hoặc giới hạn kết quả ở database.

## 4. Các kiểu trả về trong ReactiveCrudRepository

`ReactiveCrudRepository<T, ID>` định nghĩa các thao tác CRUD với kiểu reactive. Những kiểu trả về thường gặp gồm:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `save(entity)` | `Mono<S>` | Lưu entity và phát entity đã lưu |
| `saveAll(entities)` | `Flux<S>` | Lưu nhiều entity và phát các entity đã lưu |
| `findById(id)` | `Mono<T>` | Tìm tối đa một entity theo ID |
| `findAll()` | `Flux<T>` | Phát tất cả entity |
| `findAllById(ids)` | `Flux<T>` | Phát các entity có ID nằm trong tập đầu vào |
| `existsById(id)` | `Mono<Boolean>` | Kiểm tra sự tồn tại |
| `count()` | `Mono<Long>` | Phát số lượng entity |
| `deleteById(id)` | `Mono<Void>` | Xóa theo ID và chỉ báo hoàn tất |
| `delete(entity)` | `Mono<Void>` | Xóa entity và chỉ báo hoàn tất |

Một số điểm cần hiểu:

- `findById` có thể hoàn tất rỗng nếu không có hàng.
- `findAll` có thể hoàn tất rỗng nếu bảng không có hàng.
- `existsById` phát boolean; không tìm thấy được thể hiện bằng `false`.
- `count` phát số lượng; tập rỗng được thể hiện bằng `0`.
- Các phương thức xóa thường trả `Mono<Void>` vì người gọi cần biết thao tác hoàn tất hay lỗi, không cần nhận entity đã xóa.

Tên và overload cụ thể phụ thuộc interface, nhưng nguyên tắc là repository reactive trả về publisher để việc truy cập database được thực hiện trong reactive pipeline.

## 5. Mono<Void> và hợp đồng không trả dữ liệu

`Mono<Void>` thường được dùng cho thao tác có tác dụng phụ nhưng không cần trả entity hoặc giá trị. Ví dụ:

~~~java
Mono<Void> deleteCustomer(Long id) {
    return customerRepository.deleteById(id);
}
~~~

`Mono<Void>` không phát `onNext` với một đối tượng `Void`. Nó hoàn tất bằng `onComplete` nếu thành công hoặc `onError` nếu thất bại.

Đây là hợp đồng khác với `Mono<Customer>` rỗng:

| Kiểu | Ý nghĩa khi hoàn tất rỗng |
|---|---|
| `Mono<Customer>` | Không có customer để trả về |
| `Mono<Void>` | Thao tác hoàn tất mà không có payload |
| `Mono<Boolean>` | Thông thường phát một giá trị boolean rồi hoàn tất |
| `Mono<Long>` | Thông thường phát một số lượng rồi hoàn tất |

Ví dụ lệnh cập nhật trạng thái không cần entity trả về:

~~~java
Mono<Void> archiveOldOrders(LocalDate cutoffDate) {
    return orderRepository.archiveBefore(cutoffDate);
}
~~~

Nếu cần biết số hàng bị ảnh hưởng, hợp đồng nên là `Mono<Integer>` hoặc một kiểu kết quả tương ứng, thay vì `Mono<Void>`:

~~~java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = 'ARCHIVED'
    WHERE created_at < :cutoffDate
    """)
Mono<Integer> archiveBefore(LocalDate cutoffDate);
~~~

Khi dùng câu lệnh sửa dữ liệu tùy chỉnh, kiểu trả về cần phù hợp với thông tin driver và Spring Data cung cấp cho thao tác đó. Ví dụ trên minh họa hợp đồng đếm số hàng được cập nhật.

### 5.1. Toán tử then chuyển kết quả thành Mono<Void>

Có thể bỏ qua dữ liệu của một publisher và chỉ quan tâm việc hoàn tất:

~~~java
Mono<Void> processAndDiscardResult(Long id) {
    return customerRepository.findById(id)
            .doOnNext(this::recordAccess)
            .then();
}
~~~

`then()` tạo publisher hoàn tất sau khi nguồn hoàn tất thành công. Nếu nguồn lỗi, lỗi vẫn được truyền. Nếu nguồn rỗng, publisher kết quả cũng hoàn tất bình thường.

Đừng dùng `then()` nếu tầng gọi vẫn cần entity hoặc giá trị mà publisher ban đầu phát ra.

### 5.2. Ghép các thao tác không cần payload

`then` cũng giúp nối các lệnh theo thứ tự:

~~~java
Mono<Void> closeAccount(Long id) {
    return accountRepository.markAsClosed(id)
            .then(transactionRepository.disableNewTransactions(id))
            .then();
}
~~~

Các thao tác cần cùng tính nguyên tử phải được đặt trong một transaction phù hợp. `then` chỉ điều khiển thứ tự trong reactive pipeline; nó không tự tạo transaction.

## 6. Hợp đồng khi không có kết quả

Không có hàng phù hợp có thể mang ý nghĩa khác nhau tùy use case. Hãy quyết định rõ ở tầng phù hợp.

### 6.1. Không tìm thấy là bình thường

Một truy vấn tìm kiếm có thể không trả kết quả:

~~~java
Flux<Product> searchProducts(String keyword) {
    return productRepository.findByNameContaining(keyword);
}
~~~

Nếu không có sản phẩm phù hợp, trả một tập kết quả rỗng là hợp lý. Repository không cần phát sinh exception.

### 6.2. Entity bắt buộc phải tồn tại

Một thao tác cập nhật đơn hàng cần entity hiện hữu:

~~~java
Mono<Order> requireOrder(Long id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
~~~

Chuyển publisher rỗng thành lỗi ở service giúp thể hiện quy tắc của use case. Các use case khác có thể vẫn coi việc không tìm thấy cùng một loại entity là bình thường.

### 6.3. Dùng giá trị mặc định

Một số cấu hình có thể dùng giá trị mặc định khi database chưa có bản ghi:

~~~java
Mono<AppPreference> loadPreference(String key) {
    return preferenceRepository.findById(key)
            .defaultIfEmpty(AppPreference.defaultFor(key));
}
~~~

Chỉ dùng mặc định nếu nghiệp vụ định nghĩa rõ giá trị đó. Không nên tạo entity giả cho tài khoản, đơn hàng hoặc quyền truy cập để che giấu dữ liệu thiếu.

### 6.4. Kiểm tra publisher có phần tử hay không

Nếu đã có publisher và chỉ cần biết nó có phát phần tử không:

~~~java
Mono<Boolean> hasCustomer =
        customerRepository.findById(customerId)
                .hasElement();
~~~

`hasElement()` phát `true` khi nguồn có ít nhất một phần tử, và `false` nếu nguồn hoàn tất rỗng. Nếu repository có phương thức `existsById` hoặc `existsBy...` phù hợp, ưu tiên phương thức đó vì nó thể hiện trực tiếp ý định kiểm tra tồn tại.

## 7. Phân biệt empty, null và error

Ba khái niệm này không thể thay thế cho nhau.

### 7.1. Empty publisher

`Mono.empty()` là publisher hoàn tất bình thường mà không phát phần tử. `Flux.empty()` cũng hoàn tất mà không phát phần tử nào.

~~~java
Mono<Customer> result = customerRepository.findById(999L);
~~~

Nếu ID 999 không tồn tại, kết quả có thể là `Mono.empty()`.

### 7.2. Null trong dữ liệu

Reactor không cho phép publisher phát ra `null`. `Mono.just(null)` là không hợp lệ. Tuy nhiên, một entity được phát ra có thể có property Java null nếu cột database cho phép NULL và mapping tương ứng hỗ trợ giá trị đó.

Ví dụ: một khách hàng tồn tại nhưng chưa khai báo số điện thoại. Khi đó `Mono<Customer>` vẫn phát entity; property `phoneNumber` có thể là `null`.

Đây là khác biệt quan trọng:

- Không có hàng: publisher không phát entity.
- Có hàng, một cột là SQL NULL: publisher phát entity có property tương ứng null.
- Có lỗi truy vấn: publisher phát tín hiệu lỗi.

Không dùng `defaultIfEmpty` để xử lý property null bên trong entity. `defaultIfEmpty` chỉ xử lý publisher không phát phần tử.

### 7.3. Error signal

Lỗi kết nối, lỗi cú pháp SQL, vi phạm constraint hoặc lỗi ánh xạ được phát dưới dạng `onError`. Lỗi có thể xuất hiện khi publisher được subscribe, không nhất thiết ngay lúc gọi phương thức repository.

Không chuyển mọi lỗi thành publisher rỗng:

~~~java
// Không nên: che cả lỗi database và lỗi lập trình thành "không tìm thấy".
return repository.findById(id)
        .onErrorResume(error -> Mono.empty());
~~~

Chỉ xử lý những lỗi mà nghiệp vụ hiểu được:

~~~java
return repository.findById(id)
        .onErrorMap(
                DataAccessException.class,
                DatabaseOperationException::new);
~~~

Nếu cần xử lý lỗi không tìm thấy, hãy dùng `switchIfEmpty`. Nếu cần xử lý lỗi database, dùng các toán tử error phù hợp. Giữ sự khác biệt này giúp logging, monitoring và API phản hồi chính xác.

## 8. Derived query và kiểu trả về

Spring Data có thể tạo truy vấn từ tên phương thức repository. Kiểu trả về phải phù hợp với số lượng hàng mà điều kiện có thể tìm thấy.

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Mono<Order> findByOrderNumber(String orderNumber);

    Flux<Order> findByCustomerId(Long customerId);

    Mono<Order> findFirstByCustomerIdOrderByCreatedAtDesc(
            Long customerId);

    Flux<Order> findTop20ByStatusOrderByCreatedAtDesc(
            OrderStatus status);

    Mono<Boolean> existsByOrderNumber(String orderNumber);

    Mono<Long> countByCustomerId(Long customerId);
}
~~~

Ý nghĩa:

- `findByOrderNumber` dùng `Mono<Order>` nếu order number là duy nhất.
- `findByCustomerId` dùng `Flux<Order>` vì một khách hàng có thể có nhiều đơn hàng.
- `findFirst...OrderBy...` giới hạn kết quả ở một hàng theo thứ tự chỉ định.
- `findTop20...` giới hạn tập kết quả ở tối đa 20 hàng.
- `existsBy...` chỉ trả lời câu hỏi tồn tại.
- `countBy...` trả số lượng, kể cả khi số lượng bằng 0.

### 8.1. First và Top phải có ý nghĩa nghiệp vụ

Nếu cần bản ghi mới nhất, hãy xác định thứ tự:

~~~java
Mono<Order> findNewestOrder(Long customerId) {
    return orderRepository
            .findFirstByCustomerIdOrderByCreatedAtDesc(customerId);
}
~~~

Không dựa vào thứ tự ngẫu nhiên của hàng trong database. SQL chỉ bảo đảm thứ tự khi có `ORDER BY`.

`First` hoặc `Top` biểu diễn việc giới hạn số kết quả. Nếu cần xác nhận dữ liệu thực sự duy nhất, không dùng `First` để âm thầm bỏ qua các hàng trùng; hãy bảo vệ tính duy nhất bằng constraint.

### 8.2. Mono không thay thế unique constraint

Giả sử email phải duy nhất. Một phương thức:

~~~java
Mono<Customer> findByEmail(String email);
~~~

không tự bảo vệ database khỏi hai hàng có cùng email. Nếu nhiều hàng cùng khớp, truy vấn đơn có thể phát sinh lỗi kích thước kết quả. Cách bảo vệ đúng là thêm unique constraint và xử lý lỗi khi ghi.

Kiểu trả về phản ánh hợp đồng mong đợi của phương thức; database constraint bảo vệ bất biến dữ liệu kể cả khi có nhiều request đồng thời.

## 9. Kiểu trả về cho @Query và DatabaseClient

Với SQL tùy chỉnh, hợp đồng reactive vẫn cần thể hiện rõ cardinality.

Repository method trả một entity:

~~~java
@Query("""
    SELECT id, order_number, status
    FROM purchase_order
    WHERE order_number = :number
    """)
Mono<Order> findOneByNumber(@Param("number") String number);
~~~

Repository method trả nhiều entity:

~~~java
@Query("""
    SELECT id, order_number, status
    FROM purchase_order
    WHERE customer_id = :customerId
    ORDER BY created_at DESC
    """)
Flux<Order> findOrdersByCustomer(
        @Param("customerId") Long customerId);
~~~

Với `DatabaseClient`, API fetch cho phép chọn cách lấy kết quả:

~~~java
Mono<Map<String, Object>> one =
        databaseClient.sql("""
                SELECT id, order_number
                FROM purchase_order
                WHERE id = :id
                """)
                .bind("id", id)
                .fetch()
                .one();
~~~

~~~java
Mono<Map<String, Object>> first =
        databaseClient.sql("""
                SELECT id, order_number
                FROM purchase_order
                WHERE status = :status
                ORDER BY created_at DESC
                """)
                .bind("status", status)
                .fetch()
                .first();
~~~

~~~java
Flux<Map<String, Object>> all =
        databaseClient.sql("""
                SELECT id, order_number
                FROM purchase_order
                WHERE status = :status
                ORDER BY created_at DESC
                """)
                .bind("status", status)
                .fetch()
                .all();
~~~

Các API này có hợp đồng khác nhau:

| API | Hợp đồng |
|---|---|
| `one()` | Không có hoặc một hàng; nhiều hơn một hàng là lỗi |
| `first()` | Lấy hàng đầu tiên nếu có; không xác nhận tính duy nhất |
| `all()` | Phát tất cả hàng phù hợp |

Nếu thứ tự có ý nghĩa, SQL dùng `first()` cần có `ORDER BY`. Nếu dữ liệu phải duy nhất, `one()` hoặc query method trả `Mono<T>` giúp phát hiện trường hợp nhiều hàng, nhưng constraint vẫn là lớp bảo vệ dữ liệu cần thiết.

## 10. Publisher là lazy: lời gọi repository chưa chạy truy vấn

Phương thức reactive repository thường trả về publisher. Việc gọi phương thức chỉ xây dựng chuỗi xử lý; truy vấn được thực thi khi publisher được subscribe.

~~~java
Mono<Customer> customer = customerRepository.findById(10L);
~~~

Dòng lệnh trên chưa đồng nghĩa database đã được truy vấn ngay. Khi framework web, một subscriber hoặc một test subscribe vào publisher, quá trình thực thi mới diễn ra.

Vì vậy, không gọi `subscribe()` bên trong service chỉ để "chạy" repository:

~~~java
// Không nên: tách truy vấn thành subscription độc lập.
public Mono<Void> updateCustomer(Long id) {
    customerRepository.findById(id).subscribe();
    return auditRepository.recordUpdate(id);
}
~~~

Subscription độc lập có thể chạy ngoài transaction context và ngoài vòng đời của request. Service nên nối publisher rồi trả chuỗi hoàn chỉnh:

~~~java
public Mono<Void> updateCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setActive(false);
                return customerRepository.save(customer);
            })
            .then(auditRepository.recordUpdate(id));
}
~~~

Khi trả publisher, tầng gọi có thể xử lý dữ liệu, lỗi và hủy subscription theo cùng một luồng. Nếu thao tác cần transaction, đặt transaction boundary phù hợp bao quanh reactive chain.

## 11. Hợp đồng của Flux và backpressure

`Flux<T>` không chỉ là một danh sách được bọc trong reactive type. Nó hỗ trợ phát dữ liệu theo luồng và cơ chế backpressure của Reactive Streams. Subscriber có thể yêu cầu số phần tử theo nhu cầu thông qua subscription.

Điều này hữu ích khi truy vấn có nhiều hàng. Thay vì tải tất cả vào một `List`, ứng dụng có thể xử lý từng phần tử:

~~~java
return customerRepository.findAll()
        .map(CustomerSummary::from)
        .doOnNext(this::sendToDownstream);
~~~

Không nên gọi `collectList()` trên nguồn rất lớn chỉ để làm code dễ viết hơn. Việc thu thập toàn bộ dữ liệu sẽ tiêu thụ bộ nhớ tương ứng với số lượng phần tử và làm mất lợi ích xử lý streaming.

Nếu nghiệp vụ cần một danh sách hữu hạn, hãy giới hạn kết quả trong truy vấn hoặc phân trang. Backpressure cũng không thay thế giới hạn tải database: truy vấn, connection và transaction vẫn cần được quản lý theo khả năng hệ thống.

### 11.1. Cancellation và tài nguyên

Subscriber có thể hủy subscription trước khi `Flux` phát hết dữ liệu. Driver và Spring quản lý tài nguyên theo vòng đời reactive operation; ứng dụng nên giữ publisher trong cùng chuỗi để việc hủy được truyền đúng cách.

Tránh giữ connection hoặc transaction trong field để dùng lại giữa các subscription. Không chia sẻ một publisher đã gắn trạng thái hoặc tài nguyên mutable giữa các request nếu chưa hiểu rõ ngữ nghĩa của nó.

## 12. Chuyển hợp đồng repository thành phản hồi API

Repository không nên phụ thuộc vào HTTP. Nó thể hiện trạng thái dữ liệu bằng publisher; service/controller quyết định cách chuyển trạng thái đó thành phản hồi API.

| Hợp đồng repository | Cách xử lý ở API thường gặp |
|---|---|
| `Mono<T>` phát entity | Trả nội dung entity |
| `Mono<T>` hoàn tất rỗng | Có thể trả 404 nếu tài nguyên bắt buộc tồn tại; cần ánh xạ tường minh |
| `Flux<T>` có phần tử | Trả danh sách hoặc stream theo API contract |
| `Flux<T>` rỗng | Thường trả tập kết quả rỗng cho endpoint tìm kiếm |
| `Mono<Void>` hoàn tất | Có thể dùng phản hồi không có body, chẳng hạn HTTP 204 |
| Publisher phát lỗi domain | Ánh xạ qua exception handler thành mã lỗi phù hợp |
| Publisher phát lỗi database | Xử lý như lỗi hệ thống, không giả làm dữ liệu không tồn tại |

Một `Mono<T>` rỗng không tự động có nghĩa HTTP 404. Nếu endpoint cần 404, hãy chuyển trường hợp rỗng thành exception hoặc tạo `ResponseEntity` phù hợp trong tầng web.

Với endpoint tìm kiếm, `Flux<T>` rỗng thường là một danh sách rỗng hợp lệ. Không nên trả 404 chỉ vì không có kết quả nếu hợp đồng API định nghĩa đây là một truy vấn tìm kiếm.

Với lệnh xóa hoặc cập nhật không cần body, `Mono<Void>` biểu diễn hoàn tất mà không có payload. Controller có thể ánh xạ nó sang status phù hợp theo API contract.

## 13. Kiểm thử hợp đồng Mono và Flux

`StepVerifier` của Reactor Test cho phép kiểm tra tín hiệu mà publisher phát ra. Kiểm thử nên xác nhận cả dữ liệu, hoàn tất rỗng và lỗi.

Kiểm tra `Mono` có dữ liệu:

~~~java
StepVerifier.create(customerRepository.findById(existingId))
        .expectNextMatches(customer ->
                customer.getId().equals(existingId))
        .verifyComplete();
~~~

Kiểm tra `Mono` rỗng:

~~~java
StepVerifier.create(customerRepository.findById(missingId))
        .verifyComplete();
~~~

Không có `expectNext` nghĩa là test mong publisher hoàn tất mà không phát dữ liệu.

Kiểm tra service chuyển empty thành lỗi domain:

~~~java
StepVerifier.create(customerService.requireCustomer(missingId))
        .expectError(CustomerNotFoundException.class)
        .verify();
~~~

Kiểm tra `Flux` có nhiều phần tử:

~~~java
StepVerifier.create(customerRepository.findByCity("Hue"))
        .expectNextCount(2)
        .verifyComplete();
~~~

Kiểm tra `Flux` rỗng:

~~~java
StepVerifier.create(customerRepository.findByCity("NoSuchCity"))
        .verifyComplete();
~~~

Kiểm tra `Mono<Void>` hoàn tất:

~~~java
StepVerifier.create(customerRepository.deleteById(existingId))
        .verifyComplete();
~~~

Các ví dụ cần dữ liệu test tương ứng. Với repository R2DBC, integration test trên database thực tế hoặc Testcontainers giúp xác nhận hành vi truy vấn và mapping. Unit test với publisher giả chỉ xác nhận cách service xử lý tín hiệu, không chứng minh SQL hoặc driver hoạt động đúng.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `Mono<T>` luôn có một entity | Không xử lý trường hợp không tìm thấy | Xem `Mono` là không hoặc một phần tử |
| Dùng `Mono<T>` cho truy vấn có nhiều kết quả | Có thể gặp lỗi kích thước kết quả | Dùng `Flux<T>` hoặc giới hạn truy vấn có chủ đích |
| Dùng `Flux<T>` cho dữ liệu bắt buộc duy nhất mà không kiểm tra | Có thể bỏ qua dữ liệu trùng | Dùng `Mono<T>` và unique constraint |
| Coi empty publisher là lỗi database | Phản hồi sai với truy vấn không có hàng | Phân biệt `onComplete` rỗng và `onError` |
| Chuyển mọi lỗi thành `Mono.empty()` | Che lỗi SQL, kết nối và mapping | Chỉ xử lý lỗi theo đúng loại |
| Dùng `Mono.just(null)` | Reactor không chấp nhận null emission | Dùng `Mono.empty()` hoặc một giá trị không null |
| Dùng `Mono<Void>` khi cần số hàng bị ảnh hưởng | Mất thông tin kết quả thao tác | Dùng kiểu kết quả phù hợp như `Mono<Integer>` |
| Dùng `List<T>` hoặc `Optional<T>` như hợp đồng đồng bộ trong reactive repository | Làm mất ngữ nghĩa reactive | Dùng `Mono<T>` hoặc `Flux<T>` |
| Thu thập `Flux` lớn thành list | Tăng bộ nhớ và độ trễ | Xử lý streaming hoặc giới hạn/phân trang |
| Gọi `subscribe()` bên trong service | Tách luồng thực thi khỏi caller và transaction context | Nối publisher rồi trả về |
| Cho rằng `Mono<T>` bảo đảm dữ liệu duy nhất | Database vẫn có thể chứa hàng trùng | Dùng khóa hoặc unique constraint |
| Dùng `first` mà không có thứ tự | Hàng được chọn không ổn định | Thêm `ORDER BY` hoặc derived query có sort |
| Mong `Mono` rỗng tự trở thành HTTP 404 | API có thể trả phản hồi khác mong đợi | Ánh xạ empty thành status/exception rõ ràng ở tầng web |

## 15. Quy trình chọn kiểu trả về

Khi khai báo một phương thức repository, hãy xác định:

1. Điều kiện truy vấn có thể khớp tối đa một hàng hay nhiều hàng?
2. Nếu không có hàng, đó là trạng thái bình thường hay lỗi nghiệp vụ?
3. Nếu kỳ vọng một hàng, database có khóa hoặc unique constraint bảo vệ điều đó không?
4. Phương thức có trả entity, giá trị đơn, danh sách hay chỉ báo hoàn tất?
5. Nếu dùng `Flux`, người gọi có thể xử lý streaming hay cần list hữu hạn?
6. Nếu dùng `Mono<Void>`, người gọi có cần biết số hàng bị ảnh hưởng hay không?
7. Tầng service/API có ánh xạ empty và error theo đúng hợp đồng không?
8. Publisher có được nối và trả về đầy đủ thay vì tự subscribe trong service không?

Có thể dùng quy tắc tham khảo:

| Ý định | Kiểu trả về |
|---|---|
| Tìm một entity, có thể không tồn tại | `Mono<T>` |
| Tìm nhiều entity | `Flux<T>` |
| Tìm kiếm không có kết quả là bình thường | `Flux<T>` rỗng |
| Bắt buộc phải có một entity | `Mono<T>` kết hợp `switchIfEmpty` ở service |
| Kiểm tra tồn tại | `Mono<Boolean>` |
| Đếm bản ghi | `Mono<Long>` |
| Lệnh không cần payload | `Mono<Void>` |
| Lệnh cần số hàng bị ảnh hưởng | `Mono<Integer>` hoặc kiểu kết quả phù hợp |
| Danh sách nhỏ cần thu thập | `Flux<T>.collectList()` ở tầng xử lý |
| Truy vấn cần xác nhận tối đa một hàng | `Mono<T>` hoặc API `one()` phù hợp |

## 16. Ghi nhớ

- Kiểu trả về là một phần của hợp đồng repository: nó mô tả cardinality và cách biểu diễn kết quả.
- `Mono<T>` biểu diễn từ không đến một phần tử; `Flux<T>` biểu diễn từ không đến nhiều phần tử.
- Publisher rỗng hoàn tất bình thường; lỗi database được truyền bằng `onError`.
- `Mono<T>` không cam kết luôn có entity và cũng không thay thế unique constraint.
- `Flux<T>` phù hợp với tập kết quả và cho phép xử lý streaming; chỉ thu thập thành list khi dữ liệu có giới hạn hợp lý.
- `Mono<Void>` thể hiện thao tác hoàn tất mà không có payload; nếu cần số hàng bị ảnh hưởng, hãy chọn kiểu trả về có dữ liệu.
- SQL NULL trong một property khác với việc truy vấn không trả về hàng.
- Dùng `switchIfEmpty` cho quy tắc nghiệp vụ yêu cầu dữ liệu; không biến mọi lỗi thành empty.
- Reactive repository trả publisher; nối publisher và trả chuỗi hoàn chỉnh thay vì tự gọi `subscribe()` trong service.
- Tầng service và API quyết định cách chuyển empty thành mặc định, lỗi domain, danh sách rỗng hoặc phản hồi HTTP.

