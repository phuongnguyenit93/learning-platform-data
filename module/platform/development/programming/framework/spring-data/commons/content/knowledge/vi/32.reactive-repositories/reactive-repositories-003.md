# RxJava3CrudRepository và RxJava3SortingRepository theo mô-đun hỗ trợ

## 1. Mục tiêu và phạm vi

Trong chương **Repository reactive** của module **Spring Data Commons**, bài này giải thích cách khai báo repository dùng RxJava 3 cho CRUD và sắp xếp dữ liệu.

Sau bài học, bạn cần làm được các việc sau:

- Kết hợp đúng `RxJava3CrudRepository` và `RxJava3SortingRepository`.
- Đọc hợp đồng của `Single`, `Maybe`, `Flowable` và `Completable`.
- Chọn một mô-đun có hỗ trợ repository reactive tương ứng.
- Ghép thao tác đọc, sửa và lưu mà không tự tách subscription.
- Phân biệt sorting, giới hạn kết quả và phân trang.
- Kiểm tra cả giá trị, trường hợp rỗng và tín hiệu lỗi.

Ví dụ chính dùng MongoDB reactive. Phần đối chiếu Cassandra cho thấy một abstraction chung không xóa bỏ giới hạn truy vấn của từng kho dữ liệu.

## 2. Commons định nghĩa hợp đồng, mô-đun cung cấp triển khai

Hai interface có package:

~~~java
import org.springframework.data.repository.reactive.RxJava3CrudRepository;
import org.springframework.data.repository.reactive.RxJava3SortingRepository;
~~~

Chúng thuộc Spring Data Commons, nhưng Commons không tự tạo kết nối database hoặc triển khai truy vấn cho mọi store.

Có thể hình dung các tầng:

~~~text
Repository ứng dụng dùng kiểu RxJava 3
    -> repository factory của mô-đun reactive hỗ trợ
    -> mapping và thực thi truy vấn của mô-đun
    -> driver, kết nối và database
~~~

Việc biên dịch được một interface chỉ chứng minh kiểu Java hợp lệ. Để dùng được lúc chạy, còn cần đúng mô-đun, driver, hạ tầng repository và cấu hình kết nối.

Một thư viện có API reactive không tự đồng nghĩa nó cung cấp mọi loại repository reactive. Cần đọc tài liệu của mô-đun và phiên bản đang dùng.

### 2.1. Hai ví dụ mô-đun có hỗ trợ được công bố

| Mô-đun | Hỗ trợ được mô tả | Giới hạn cần giữ rõ |
| --- | --- | --- |
| Spring Data MongoDB reactive | Repository dùng các interface RxJava 3 và chuyển đổi wrapper qua hạ tầng reactive | Cần MongoDB Reactive Streams driver; truy vấn và index theo MongoDB |
| Spring Data Cassandra reactive | Repository có thể dùng các interface RxJava 3 | Truy vấn, ordering và cách phân trang chịu mô hình dữ liệu Cassandra |

Tài liệu MongoDB liệt kê hai interface RxJava 3 và mô tả việc chuyển đổi wrapper phía sau repository. Xem [Spring Data MongoDB: Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).

Tài liệu Cassandra cũng liệt kê chúng trong phần reactive repositories. Xem [Spring Data Cassandra: Reactive Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html#cassandra.reactive.repositories).

Không suy ra từ bảng rằng một câu truy vấn sắp xếp bất kỳ có cùng khả năng thực thi trên cả hai store.

### 2.2. Bọc lời gọi blocking không thay đổi driver

Ví dụ sau chỉ bọc một lời gọi đồng bộ:

~~~java
Single.fromCallable(() -> blockingRepository.findById(id));
~~~

Nó chưa biến `blockingRepository` thành repository RxJava 3 do mô-đun reactive cung cấp. Nếu thực thi trên một scheduler khác, lời gọi database bên trong vẫn có thể chiếm thread để chờ I/O.

Cần phân biệt việc đổi kiểu trả về hoặc chuyển thread với việc dùng một đường truy cập dữ liệu được mô-đun thiết kế cho reactive.

## 3. CRUD và sorting cần được kết hợp tường minh

Một repository có cả hai nhóm chức năng:

~~~java
public interface CustomerRepository
        extends RxJava3CrudRepository<Customer, String>,
                RxJava3SortingRepository<Customer, String> {
}
~~~

Từ Spring Data 3.0, các sorting repository không còn tự kế thừa CRUD repository tương ứng. Vì vậy, chỉ extends `RxJava3SortingRepository` không cung cấp sẵn toàn bộ `save`, `findById` hoặc `deleteById`.

Xem [Spring Data Commons: Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

Nếu muốn dùng lại tổ hợp này trong nhiều repository, có thể khai báo một base interface:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.reactive.RxJava3CrudRepository;
import org.springframework.data.repository.reactive.RxJava3SortingRepository;

@NoRepositoryBean
public interface RxCrudAndSortRepository<T, ID>
        extends RxJava3CrudRepository<T, ID>,
                RxJava3SortingRepository<T, ID> {
}
~~~

Sau đó repository cụ thể extends base này. `@NoRepositoryBean` cho biết đây là interface trung gian, chưa phải repository của một domain type cụ thể.

Không ghép thêm `CrudRepository` đồng bộ vào cùng interface chỉ để lấy CRUD: các method cùng tên và tham số có thể có kiểu trả về không tương thích.

## 4. Đọc đúng các kiểu RxJava 3

Các import dùng trong bài:

~~~java
import io.reactivex.rxjava3.core.Completable;
import io.reactivex.rxjava3.core.Flowable;
import io.reactivex.rxjava3.core.Maybe;
import io.reactivex.rxjava3.core.Single;
~~~

Chúng khác package với RxJava 2. Cần dependency RxJava 3 tương thích với bộ Spring Data đang dùng, thường được nhận diện bằng tọa độ `io.reactivex.rxjava3:rxjava`.

| Kiểu | Hợp đồng kết quả thành công | Ví dụ phù hợp |
| --- | --- | --- |
| `Single<T>` | Có đúng một giá trị | Entity sau lưu, số lượng, kết quả tồn tại |
| `Maybe<T>` | Có một giá trị hoặc hoàn tất rỗng | Tìm theo id có thể không thấy |
| `Flowable<T>` | Có từ không đến nhiều phần tử, hỗ trợ backpressure | Nhiều entity |
| `Completable` | Hoàn tất không có giá trị dữ liệu | Thao tác xóa |

Mỗi kiểu còn có thể kết thúc bằng lỗi. Không dùng một giá trị `null` để mô phỏng kết quả rỗng trong luồng RxJava.

Với `Maybe`, một lần không tìm thấy là nhánh hoàn tất rỗng. Với `Single`, hợp đồng thành công phải có một giá trị. Do đó, lựa chọn kiểu trả về quyết định cách caller phải xử lý kết quả.

Đối với custom query, kiểu trả về một phần tử không biến một điều kiện không duy nhất thành duy nhất. Nếu query có nhiều kết quả trong khi hợp đồng chỉ cho tối đa một, cần xử lý theo lỗi và quy tắc của mô-đun.

## 5. Những chữ ký CRUD cần nắm

Các method tiêu biểu của `RxJava3CrudRepository<T, ID>`:

| Method | Kiểu trả về |
| --- | --- |
| `save(S entity)`, với `S extends T` | `Single<S>` |
| `saveAll(Iterable<S> entities)` | `Flowable<S>` |
| `saveAll(Flowable<S> entityStream)` | `Flowable<S>` |
| `findById(ID id)` | `Maybe<T>` |
| `findById(Single<ID> id)` | `Maybe<T>` |
| `existsById(ID id)` | `Single<Boolean>` |
| `findAll()`, `findAllById(...)` | `Flowable<T>` |
| `count()` | `Single<Long>` |
| `deleteById(ID id)`, `delete(T entity)` | `Completable` |

Dùng entity trả về từ `save` cho bước tiếp theo; đường lưu có thể trả một instance đã được cập nhật khác với object đầu vào.

`findAllById` có thể trả ít phần tử hơn số id đầu vào nếu có id không tồn tại, và không bảo đảm giữ thứ tự các id được truyền vào.

`Completable` từ `deleteById` không mang số bản ghi bị xóa. Không tìm thấy id có thể được bỏ qua theo hợp đồng method.

Xem [RxJava3CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/reactive/RxJava3CrudRepository.html).

Các kiểu tham số reactive cũng cần đọc theo đúng overload. Ví dụ, `saveAll` trong bảng nhận `Flowable`, không phải mọi wrapper RxJava đều có thể truyền trực tiếp vào vị trí đó.

## 6. Ví dụ MongoDB: model, repository và hạ tầng

### 6.1. Model tối giản

Ví dụ dùng record bất biến với id do ứng dụng cấp:

~~~java
package com.example.rxcustomers;

import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("rx_customers")
public record Customer(
        @Id String id,
        String displayName,
        boolean active) {

    public Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(displayName, "displayName");

        if (id.isBlank() || displayName.isBlank()) {
            throw new IllegalArgumentException(
                    "id and displayName must not be blank");
        }
    }

    public Customer renameTo(String nextName) {
        return new Customer(id, nextName, active);
    }
}
~~~

Các public type trong ví dụ nằm trong các file Java riêng khi đưa vào project. Ví dụ giả định Java 17 trở lên và phiên bản Spring Data có hỗ trợ mapping record tương ứng.

### 6.2. Repository có CRUD, sorting và derived query

~~~java
package com.example.rxcustomers;

import io.reactivex.rxjava3.core.Flowable;

import org.springframework.data.domain.Sort;
import org.springframework.data.repository.reactive.RxJava3CrudRepository;
import org.springframework.data.repository.reactive.RxJava3SortingRepository;

public interface CustomerRepository
        extends RxJava3CrudRepository<Customer, String>,
                RxJava3SortingRepository<Customer, String> {

    Flowable<Customer> findByActive(
            boolean active,
            Sort sort);
}
~~~

Derived query ở đây dùng khả năng của MongoDB repository. Commons cung cấp abstraction chung, còn mô-đun phân tích và thực thi query theo store.

### 6.3. Cấu hình reactive MongoDB tường minh

Ứng dụng cần dependency mô-đun MongoDB reactive, MongoDB Reactive Streams driver và RxJava 3 tương thích. Cấu hình tối giản:

~~~java
package com.example.rxcustomers;

import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.repository.config.EnableReactiveMongoRepositories;

@Configuration
@EnableReactiveMongoRepositories(
        basePackageClasses = CustomerRepository.class)
public class MongoRxConfiguration {

    @Bean(destroyMethod = "close")
    public MongoClient mongoClient() {
        return MongoClients.create(
                "mongodb://localhost:27017");
    }

    @Bean
    public ReactiveMongoTemplate reactiveMongoTemplate(
            MongoClient mongoClient) {

        return new ReactiveMongoTemplate(
                mongoClient,
                "rx_repository_demo");
    }
}
~~~

Lưu ý import `MongoClient` từ package `com.mongodb.reactivestreams.client`. Một client đồng bộ có tên class tương tự không thay thế được hạ tầng reactive này.

Cấu hình dùng cơ sở dữ liệu minh họa cục bộ. Nếu project đã có auto-configuration hoặc cấu hình client riêng, cần tích hợp theo cấu trúc project thay vì tạo trùng các bean.

Khi có nhiều mô-đun Spring Data, dùng mapping và phạm vi scan rõ ràng để repository được gắn đúng factory.

## 7. Ghép thao tác đọc, sửa và lưu

### 7.1. Chuyển nhánh không tìm thấy thành lỗi nghiệp vụ

Một lỗi ứng dụng:

~~~java
package com.example.rxcustomers;

public class CustomerNotFoundException
        extends RuntimeException {

    public CustomerNotFoundException(String id) {
        super("Customer not found: " + id);
    }
}
~~~

Service trả lại chuỗi reactive cho caller:

~~~java
package com.example.rxcustomers;

import io.reactivex.rxjava3.core.Completable;
import io.reactivex.rxjava3.core.Flowable;
import io.reactivex.rxjava3.core.Single;

import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Single<Customer> requireById(String id) {
        return Single.defer(() ->
                repository.findById(id)
                        .switchIfEmpty(Single.error(
                                new CustomerNotFoundException(id))));
    }

    public Single<Customer> rename(
            String id,
            String nextName) {

        return requireById(id)
                .flatMap(customer ->
                        repository.save(
                                customer.renameTo(nextName)));
    }

    public Completable removeIfPresent(String id) {
        return repository.deleteById(id);
    }

    public Flowable<Customer> activeCustomers() {
        Sort sort = Sort.by(
                Sort.Order.asc("displayName"),
                Sort.Order.asc("id"));

        return repository.findByActive(true, sort);
    }
}
~~~

`requireById` chủ động đổi hợp đồng từ “không hoặc một khách hàng” sang “một khách hàng hoặc lỗi”. Không cần sửa chữ ký `findById` của repository từ `Maybe` sang `Single`.

`Single.defer` trì hoãn việc tạo nguồn bên trong đến lúc subscribe. Nếu việc gọi repository bên trong ném lỗi do tham số không hợp lệ, lỗi cũng được đưa vào quá trình thực thi nguồn đó.

`rename` tạo một Customer mới rồi ghép publisher lưu bằng `flatMap`. Caller nhận kết quả lưu thay vì object được tự dựng làm kết quả giả định.

### 7.2. Không tách subscription bên trong service

Một cách làm gây mất liên kết:

~~~java
repository.save(customer).subscribe();
return Single.just(customer);
~~~

Hai dòng này tạo một subscription riêng cho thao tác lưu rồi trả ngay một nguồn khác. Caller có thể nhận object trước khi việc lưu hoàn tất; lỗi lưu cũng không còn là lỗi của nguồn được trả về.

Cách ghép phù hợp trong tình huống này:

~~~java
return repository.save(customer);
~~~

Khi cần đọc rồi lưu, dùng chuỗi `flatMap` như service ở trên. Việc subscribe cuối cùng thuộc ranh giới thực thi được ứng dụng chọn.

### 7.3. Read-modify-write chưa mặc nhiên nguyên tử

Ví dụ đổi tên có một lần đọc và một lần lưu. Không thể kết luận toàn bộ thao tác có tính nguyên tử hoặc đã ngăn được hai request ghi đè nhau chỉ vì chúng nằm trong một chuỗi RxJava.

Nếu cần optimistic locking, transaction hoặc update có điều kiện, phải thiết kế theo khả năng của store. Một annotation transaction kiểu imperative cũng không tự bao phủ mọi tác vụ sẽ chạy sau đó khi subscribe.

## 8. Sorting không đồng nghĩa phân trang

`RxJava3SortingRepository` cung cấp:

~~~java
Flowable<T> findAll(Sort sort);
~~~

`sort` có thể là `Sort.unsorted()` nhưng không được là `null`. Xem [RxJava3SortingRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/reactive/RxJava3SortingRepository.html).

Ví dụ trong một thành phần đã inject `CustomerRepository repository`:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("displayName"),
        Sort.Order.asc("id"));

Flowable<Customer> ordered =
        repository.findAll(sort);
~~~

Tên trong `Sort` là tên property của model được mapping theo mô-đun. Trong ví dụ MongoDB, property id có mapping tương ứng với định danh document.

Thêm id làm tiêu chí phụ giúp có thứ tự xác định giữa các khách hàng có cùng tên, với điều kiện dữ liệu và quy tắc so sánh không thay đổi. Điều đó chưa tạo ra một snapshot bất biến nếu dữ liệu tiếp tục được sửa giữa các lần đọc.

### 8.1. Không có sẵn findAll(Pageable) từ interface sorting này

Không suy ra `Page<Customer>` hoặc một method `findAll(Pageable)` chỉ từ việc extends `RxJava3SortingRepository`.

Nếu cần giới hạn số kết quả, thiết kế query theo khả năng của mô-đun. Một ví dụ method giới hạn tĩnh có thể khai báo trong repository MongoDB ở trên:

~~~java
Flowable<Customer>
findTop20ByActiveTrueOrderByDisplayNameAscIdAsc();
~~~

Đây là query method dành cho ví dụ MongoDB, không phải method mà mọi sorting repository đều cung cấp sẵn.

### 8.2. take và sorted nằm ở tầng nào?

~~~java
repository.findAll(sort).take(20);
~~~

`take(20)` giới hạn số phần tử đi tiếp trong luồng và có thể hủy upstream sau khi đủ. Không từ đó suy ra query database đã được viết lại thành limit tối ưu đúng bằng 20.

Tương tự, `Flowable.sorted(comparator)` sắp xếp ở phía xử lý luồng, khác với yêu cầu store thực thi `Sort`. Với nguồn lớn, việc cần gom dữ liệu để sắp xếp tại ứng dụng có thể làm tăng bộ nhớ và độ trễ.

Nếu muốn tổng số phần tử cùng dữ liệu của một trang, thường cần thêm thiết kế query/count và quy tắc nhất quán. Hai kết quả đọc riêng có thể khác nhau khi dữ liệu đang thay đổi.

## 9. Lưu nhiều phần tử, backpressure và bộ nhớ

Có thể truyền một tập hữu hạn hoặc một nguồn `Flowable`:

~~~java
Flowable<Customer> saved = repository.saveAll(
        Flowable.fromIterable(customers));
~~~

Biến `customers` ở đây là một tập Customer không chứa null. Nguồn trả về phát các entity sau lưu.

Không suy ra `saveAll` luôn tạo đúng một lệnh bulk tại database. Cách triển khai, callback và khả năng tối ưu thuộc mô-đun.

Tương tự, lưu nhiều phần tử không mặc nhiên có một transaction chung. Nếu một phần tử thất bại, cần biết những thao tác nào đã xảy ra và chính sách ứng dụng cần áp dụng.

Backpressure của `Flowable` giúp downstream biểu đạt nhu cầu phần tử. Nó không tự chứng minh query rẻ, database không phải sort nhiều dữ liệu hoặc ứng dụng sẽ không gom toàn bộ kết quả.

Ví dụ:

~~~java
Single<java.util.List<Customer>> all =
        repository.findAll().toList();
~~~

Đây là yêu cầu tập hợp toàn bộ kết quả vào một List. Nó làm mất lợi ích xử lý từng phần tử nếu dữ liệu rất lớn.

Khi cần xử lý từng lần lưu theo thứ tự ở tầng ứng dụng, có thể chọn:

~~~java
Flowable<Customer> savedInSequence =
        input.concatMapSingle(repository::save);
~~~

`input` là một `Flowable<Customer>`. Cách ghép này tuần tự hóa các nguồn lưu bên trong theo luồng đó; nó không bổ sung transaction hoặc bảo đảm nghiệp vụ giữa các request khác nhau.

## 10. Subscription, lỗi và chuyển đổi thư viện

### 10.1. Tạo chuỗi chưa phải xác nhận thao tác đã hoàn tất

~~~java
Single<Customer> operation =
        repository.save(customer);
~~~

Với đường repository reactive, caller đang có một nguồn để thực thi. Chỉ giữ biến `operation` rồi bỏ đi không phải bằng chứng dữ liệu đã được lưu.

Không đồng nhất mọi kiểu RxJava với nguồn cold có cùng hành vi. Cache, nguồn hot hoặc nguồn được ứng dụng tự tạo có thể có vòng đời khác. Cần hiểu nguồn cụ thể và số lần subscribe.

Subscribe lại một chuỗi có ghi dữ liệu hoặc dùng `retry` có thể thực hiện lại tác vụ. Việc đó cần phù hợp với idempotency và các tác động phụ.

### 10.2. Không biến lỗi kỹ thuật thành kết quả rỗng ngoài ý muốn

Ví dụ cần cân nhắc:

~~~java
repository.findById(id)
        .onErrorComplete();
~~~

Nếu mọi lỗi bị chuyển thành hoàn tất rỗng, lỗi kết nối có thể bị nhìn giống một khách hàng không tồn tại.

Chỉ chuyển lỗi thành fallback khi hợp đồng ứng dụng thực sự cho phép. Cần giữ được khác biệt giữa “không có dữ liệu”, “dữ liệu không hợp lệ” và “không thực thi được thao tác”.

Ngoài tín hiệu lỗi trong luồng, một API cũng có thể kiểm tra tham số ngay lúc được gọi. Không mặc định mọi lỗi Java chỉ xuất hiện sau subscribe.

### 10.3. Chuyển sang Reactor tại ranh giới khi cần

Nếu một tầng khác dùng Reactor, có thể chuyển qua Reactive Streams mà không blocking:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Mono<Customer> one = Mono.from(
        repository.findById(id).toFlowable());

Flux<Customer> many = Flux.from(
        repository.findAll());
~~~

`Flowable` là một Reactive Streams publisher. `Single`, `Maybe` và `Completable` có các hợp đồng RxJava riêng; không truyền trực tiếp chúng vào mọi API nhận `Publisher` rồi giả định sẽ biên dịch.

Ví dụ chuyển `Maybe` thành `Flowable` trước khi đưa vào `Mono.from`, giữ được trường hợp không hoặc một kết quả.

Tránh rải chuyển đổi qua lại khắp logic nghiệp vụ. Chọn ranh giới rõ cho tầng dùng RxJava và tầng dùng Reactor.

`blockingGet` hoặc `blockingAwait` làm caller chờ theo cách blocking. Không chèn chúng vào service reactive chỉ để lấy giá trị cho dễ viết chuỗi lệnh đồng bộ.

## 11. Giới hạn cụ thể của mô-đun vẫn có hiệu lực

### 11.1. MongoDB

Trong ví dụ, sorting và derived query được thực thi theo mapping MongoDB. Cần xem index, chi phí truy vấn và quy tắc so sánh tên.

Nếu cùng ứng dụng có cả client blocking và reactive, cần cấu hình đúng hạ tầng cho từng đường truy cập. Việc một repository dùng RxJava không khiến một thao tác blocking khác trong callback trở nên non-blocking.

### 11.2. Cassandra

Tài liệu Cassandra có hỗ trợ các interface RxJava 3, nhưng điều đó không biến Cassandra thành nơi hỗ trợ offset và ordering tùy ý trên mọi cột.

Thiết kế query phải theo partition key, clustering columns và khả năng CQL. Một `Sort` hợp lệ về kiểu Java có thể không hợp lệ với schema hoặc điều kiện truy vấn cụ thể.

Cassandra có cách truy cập trang dựa trên khả năng phân trang của store; không sao chép nguyên giả định `PageRequest` offset của một store khác. Tài liệu repository Cassandra giải thích giới hạn của kiểu phân trang limit/offset cổ điển.

### 11.3. Checklist lựa chọn theo khả năng thực tế

Trước khi chọn repository, cần trả lời được:

1. Mô-đun và phiên bản đang dùng có công bố hỗ trợ repository RxJava 3 không?
2. Hạ tầng reactive nào tạo repository bean và dùng driver nào?
3. Model được mapping vào store nào?
4. Query cần dùng có được mô-đun hỗ trợ không?
5. Sorting, limit và phân trang có phù hợp schema và index không?
6. Có yêu cầu transaction hoặc kiểm soát cạnh tranh vượt quá hợp đồng CRUD không?

Không cần thêm mọi mô-đun reactive vào project. Chỉ cấu hình đường truy cập phục vụ kho dữ liệu đã chọn.

## 12. Kiểm tra tín hiệu và kết quả lưu

Ví dụ dưới dùng JUnit Jupiter và RxJava test consumer, với `repository` là repository thật của môi trường kiểm tra MongoDB. Các snippet đặt trong test class đã được cấu hình inject repository.

### 12.1. Id không tồn tại hoàn tất rỗng

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

@Test
void missingIdCompletesWithoutValue() {
    String id = "missing-" + UUID.randomUUID();

    repository.findById(id)
            .test()
            .awaitDone(5, TimeUnit.SECONDS)
            .assertResult();
}
~~~

Id ngẫu nhiên cần thuộc môi trường dữ liệu kiểm tra do test kiểm soát. `assertResult()` không có phần tử mong đợi diễn đạt nhánh hoàn tất rỗng thành công.

### 12.2. Lưu rồi đọc lại cùng id

~~~java
@Test
void savesAndReadsCustomer() {
    String id = "customer-" + UUID.randomUUID();
    Customer customer =
            new Customer(id, "An", true);

    repository.save(customer)
            .flatMap(saved ->
                    repository.findById(saved.id())
                            .switchIfEmpty(Single.error(
                                    new AssertionError(
                                            "Saved customer not found"))))
            .test()
            .awaitDone(5, TimeUnit.SECONDS)
            .assertValue(actual ->
                    actual.id().equals(id)
                            && actual.displayName().equals("An")
                            && actual.active())
            .assertComplete()
            .assertNoErrors();
}
~~~

Test dùng instance sau lưu để lấy id cho readback. Thời hạn năm giây chỉ là giá trị minh họa cho môi trường kiểm tra; cần chọn giới hạn phù hợp với hạ tầng thực tế.

Đây là các thao tác ghi vào dữ liệu test, nên test suite cần cơ chế cô lập và dọn fixture riêng.

### 12.3. Các tình huống cần bổ sung

| Tình huống | Điều cần xác minh |
| --- | --- |
| Chỉ kế thừa sorting | Không giả định có CRUD từ interface đó |
| `findById` không thấy | `Maybe` rỗng, không nhầm với lỗi kết nối |
| Service bắt buộc có khách hàng | Nhánh rỗng thành lỗi nghiệp vụ đã chọn |
| Nhiều tên trùng nhau | Sorting có tiêu chí phụ xác định theo yêu cầu |
| `findAllById` có id thiếu | Không giả định đủ số lượng hoặc đúng thứ tự đầu vào |
| Lỗi trong chuỗi lưu | Caller nhận lỗi qua nguồn được trả về |
| Query vượt giới hạn store | Có kiểm tra theo mô-đun, không chỉ kiểm tra kiểu Java |
| Luồng read-modify-write cạnh tranh | Chính sách version hoặc transaction đáp ứng yêu cầu |

Mock repository hữu ích cho logic service, nhưng không chứng minh repository factory chấp nhận RxJava 3, driver hoạt động hoặc query chạy đúng trên database.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Có class interface nhưng không tạo được bean | Thiếu mô-đun hỗ trợ, sai scanner, thiếu driver hoặc cấu hình kết nối |
| Không thấy method `save` | Chỉ extends `RxJava3SortingRepository` |
| Không khớp kiểu `Single` hoặc `Maybe` | Import RxJava khác thế hệ hoặc đổi sai hợp đồng trả về |
| Dữ liệu chưa lưu nhưng service đã trả thành công | Tự subscribe bên trong rồi trả một nguồn không liên kết |
| Không tìm thấy dữ liệu nhưng chờ một giá trị | Chưa xử lý nhánh `Maybe` rỗng |
| Giao diện không có `findAll(Pageable)` | Nhầm sorting fragment với repository phân trang đồng bộ |
| Tốn nhiều bộ nhớ khi đọc dữ liệu | Gom toàn bộ bằng `toList` hoặc sort ở phía ứng dụng |
| Sort bị database từ chối | Điều kiện truy vấn, property hoặc schema không hỗ trợ |
| Có tác vụ bị thực hiện lại | Nhiều subscription hoặc retry trên chuỗi có side effect |
| Luồng reactive vẫn chặn thread | Có `blockingGet`, lời gọi driver blocking hoặc tác vụ đồng bộ trong callback |

Bắt đầu chẩn đoán từ mô-đun và kiểu trả về, sau đó kiểm tra điểm subscribe và đường thực thi I/O. Chỉ đổi tên interface hoặc thêm scheduler chưa giải quyết được sai khác của các tầng này.

## 14. Bài thực hành

Thực hiện trên MongoDB reactive hoặc mô-đun khác đã xác minh hỗ trợ:

1. Khai báo model với id và các trường cần truy vấn.
2. Tạo repository kế thừa cả hai interface RxJava 3.
3. Lưu một entity và dùng kết quả lưu để đọc lại.
4. Kiểm tra trường hợp id không tồn tại bằng `Maybe`.
5. Viết service đổi tên với chuỗi đọc, chuyển đổi và lưu.
6. Truy vấn nhiều entity có sorting và tiêu chí phụ.
7. Phân biệt một query có giới hạn tại store với thao tác `take` trên luồng.
8. Ghi rõ khả năng và giới hạn query của mô-đun đã chọn.

Bài thực hành đạt yêu cầu khi bạn giải thích được **vì sao mô-đun tạo được repository**, **mỗi kiểu RxJava biểu đạt kết quả gì**, **ai subscribe**, và **sorting được thực thi ở tầng nào**, đồng thời đọc lại được dữ liệu đã lưu qua chính repository đó.
