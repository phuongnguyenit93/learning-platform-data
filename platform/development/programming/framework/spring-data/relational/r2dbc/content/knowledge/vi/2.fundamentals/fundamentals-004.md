# Mono và Flux khi biểu diễn kết quả truy vấn

Trong Spring Data Relational R2DBC, các thao tác truy vấn được biểu diễn bằng những kiểu reactive của Project Reactor. Hai kiểu xuất hiện thường xuyên nhất là `Mono<T>` và `Flux<T>`. Chọn đúng kiểu trả về giúp thể hiện số lượng bản ghi mà truy vấn có thể tạo ra, đồng thời cho phép các tầng repository, service và web tiếp tục xử lý dữ liệu theo mô hình reactive, không phải chặn luồng để chờ kết quả.

Điểm cần nhớ là `Mono` và `Flux` mô tả một luồng tín hiệu sẽ được tiêu thụ trong tương lai. Chúng không phải là đối tượng chứa kết quả đã được lấy sẵn tại thời điểm gọi phương thức.

## 1. Vì sao Spring Data R2DBC sử dụng Mono và Flux?

R2DBC cung cấp API truy cập cơ sở dữ liệu quan hệ theo hướng reactive. Spring Data R2DBC xây dựng các repository và cơ chế ánh xạ hàng dữ liệu thành entity trên nền API đó. Vì vậy, phương thức truy vấn thường trả về một publisher thay vì trả về entity hoặc collection theo cách đồng bộ.

Project Reactor cung cấp hai kiểu publisher chính:

- `Mono<T>`: biểu diễn một luồng có thể phát ra tối đa một phần tử kiểu `T`.
- `Flux<T>`: biểu diễn một luồng có thể phát ra không phần tử, một phần tử hoặc nhiều phần tử kiểu `T`.

Cả hai đều tuân theo Reactive Streams. Một publisher có thể phát ra các tín hiệu dữ liệu, sau đó kết thúc bằng tín hiệu hoàn tất hoặc tín hiệu lỗi. Khi làm việc với repository, ứng dụng thường nhận publisher, kết hợp các bước xử lý rồi trả publisher cho thành phần tiếp theo đăng ký tiêu thụ.

Ví dụ, lời gọi `repository.findById(id)` tạo ra một `Mono<Customer>`. Ứng dụng có thể ánh xạ entity sang DTO, bổ sung xử lý khi không tìm thấy dữ liệu hoặc kết hợp với một truy vấn khác trước khi publisher được subscribe.

## 2. Mono: kết quả có tối đa một phần tử

`Mono<T>` phù hợp khi truy vấn được kỳ vọng trả về không quá một bản ghi. Có hai trường hợp kết quả thông thường:

1. Truy vấn không tìm thấy bản ghi: publisher hoàn tất mà không phát ra phần tử nào, thường được gọi là `Mono.empty()`.
2. Truy vấn tìm thấy một bản ghi: publisher phát ra một phần tử rồi hoàn tất.

Một `Mono` cũng có thể kết thúc bằng lỗi, chẳng hạn lỗi kết nối cơ sở dữ liệu hoặc lỗi khi ánh xạ dữ liệu. Do đó, `Mono<T>` không có nghĩa là chắc chắn sẽ có một giá trị.

Ví dụ tạo publisher:

```java
Mono<Customer> customer = customerRepository.findById(42L);
```

Nếu mã định danh `42` tồn tại, publisher phát ra một `Customer`. Nếu không tồn tại, publisher hoàn tất rỗng. Không có giá trị `null` được phát ra để biểu diễn trường hợp không tìm thấy.

### Các trường hợp thường dùng Mono

- Tìm một entity theo khóa chính, ví dụ `findById(id)`.
- Tìm theo một thuộc tính được bảo đảm duy nhất, ví dụ email hoặc mã sản phẩm.
- Trả về một giá trị tổng hợp như số lượng bản ghi hoặc kết quả kiểm tra tồn tại.
- Biểu diễn việc hoàn thành một thao tác không cần trả entity, thường dùng `Mono<Void>`.

Một số phương thức kế thừa từ `ReactiveCrudRepository` minh họa rõ cách dùng:

```java
Mono<Customer> findById(Long id);
Mono<Customer> save(Customer customer);
Mono<Void> deleteById(Long id);
```

`Mono<Void>` vẫn là một publisher. Nó không phát ra entity hay giá trị dữ liệu; tín hiệu hoàn tất cho biết thao tác đã kết thúc, còn tín hiệu lỗi cho biết thao tác thất bại.

## 3. Flux: kết quả có thể gồm nhiều phần tử

`Flux<T>` phù hợp khi truy vấn có thể trả về nhiều bản ghi. Mỗi hàng dữ liệu được ánh xạ thành một phần tử và được phát ra trong luồng. Một `Flux` có thể:

- Hoàn tất ngay mà không phát phần tử nào nếu không có hàng phù hợp.
- Phát một phần tử rồi hoàn tất.
- Phát nhiều phần tử rồi hoàn tất.
- Kết thúc bằng lỗi nếu truy vấn hoặc quá trình xử lý gặp sự cố.

Ví dụ:

```java
Flux<Customer> customers = customerRepository.findAll();
```

Publisher này đại diện cho tập khách hàng mà truy vấn trả về. Khi tiêu thụ, ứng dụng có thể xử lý từng khách hàng bằng các toán tử như `map`, `filter` hoặc `flatMap`.

Các phương thức phổ biến của `ReactiveCrudRepository` thể hiện quy tắc này:

```java
Flux<Customer> findAll();
Flux<Customer> findAllById(Iterable<Long> ids);
Flux<Customer> saveAll(Iterable<Customer> customers);
```

Với truy vấn có khả năng trả về nhiều hàng, dùng `Flux<T>` giúp giữ kết quả ở dạng luồng. Ứng dụng có thể xử lý phần tử khi chúng được phát ra, thay vì bắt buộc gom toàn bộ kết quả thành một collection trước khi bắt đầu xử lý.

## 4. Chọn kiểu trả về theo số lượng kết quả

Kiểu trả về nên phản ánh số lượng kết quả mà nghiệp vụ và câu truy vấn cho phép. Không nên chọn kiểu chỉ vì muốn dùng một API nào đó ở tầng gọi.

| Nhu cầu truy vấn | Kiểu trả về thường dùng | Ý nghĩa |
| --- | --- | --- |
| Tìm theo khóa chính | `Mono<Customer>` | Không có hoặc có một entity |
| Tìm theo email đã được bảo đảm duy nhất | `Mono<Customer>` | Không có hoặc có một entity |
| Tìm tất cả khách hàng theo trạng thái | `Flux<Customer>` | Có thể có nhiều entity |
| Đếm số khách hàng | `Mono<Long>` | Một giá trị đếm |
| Kiểm tra một email đã tồn tại chưa | `Mono<Boolean>` | Một giá trị đúng/sai |
| Xóa một entity theo mã | `Mono<Void>` | Chỉ quan tâm thao tác hoàn tất hay lỗi |
| Lưu nhiều entity | `Flux<Customer>` | Có thể phát ra từng entity đã lưu |

Ví dụ một repository có cả truy vấn đơn và truy vấn nhiều kết quả:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatusOrderByCreatedAtDesc(String status);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsByEmail(String email);
}
```

Trong ví dụ này, `findByEmail` chỉ nên trả về `Mono<Customer>` khi email thực sự là duy nhất theo quy tắc dữ liệu. Nên có ràng buộc unique tương ứng trong cơ sở dữ liệu để bảo vệ quy tắc đó, kể cả khi dữ liệu được ghi từ một ứng dụng hoặc tiến trình khác.

Nếu một phương thức trả về `Mono<Customer>` nhưng câu truy vấn thực tế có thể tìm thấy nhiều hàng, quá trình thực thi có thể báo lỗi sai số lượng kết quả, chẳng hạn `IncorrectResultSizeDataAccessException`. Không nên dùng kiểu `Mono` để che giấu khả năng trùng dữ liệu. Hãy xác định đúng quy tắc nghiệp vụ, bảo đảm tính duy nhất ở cơ sở dữ liệu hoặc đổi phương thức sang `Flux` nếu nhiều kết quả là hợp lệ.

## 5. Dùng Mono và Flux với derived query và @Query

Spring Data R2DBC có thể tạo truy vấn từ tên phương thức repository. Kiểu trả về cho biết phương thức đó dự kiến có một kết quả hay nhiều kết quả:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByCategoryIdOrderByNameAsc(Long categoryId);
}
```

Phương thức thứ nhất phù hợp nếu SKU là duy nhất. Phương thức thứ hai có thể trả về nhiều sản phẩm thuộc cùng danh mục.

Với truy vấn SQL tự khai báo bằng `@Query`, quy tắc chọn kiểu trả về vẫn giống như vậy:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    @Query("SELECT * FROM product WHERE sku = :sku")
    Mono<Product> findOneBySku(String sku);

    @Query("SELECT * FROM product WHERE category_id = :categoryId ORDER BY name")
    Flux<Product> findAllByCategory(Long categoryId);
}
```

SQL của truy vấn thứ nhất được thiết kế để tìm một sản phẩm theo SKU duy nhất. Truy vấn thứ hai có thể trả về nhiều hàng nên dùng `Flux<Product>`. Mệnh đề `ORDER BY` làm thứ tự kết quả rõ ràng; nếu SQL không chỉ định thứ tự, ứng dụng không nên giả định cơ sở dữ liệu luôn trả các hàng theo một thứ tự cố định.

## 6. Xử lý kết quả rỗng và kết hợp publisher

Trong reactive programming, không tìm thấy dữ liệu thường được biểu diễn bằng publisher rỗng, không phải bằng `null`. Cách xử lý phụ thuộc vào nghiệp vụ.

### Chuyển kết quả rỗng thành lỗi nghiệp vụ

```java
public Mono<Customer> getRequiredCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ));
}
```

`switchIfEmpty` đăng ký một publisher thay thế khi publisher ban đầu hoàn tất mà không phát phần tử. Cách này hữu ích khi tầng service yêu cầu entity phải tồn tại.

### Cung cấp giá trị mặc định

```java
public Mono<String> getCustomerName(Long id) {
    return customerRepository.findById(id)
            .map(Customer::getName)
            .defaultIfEmpty("Unknown customer");
}
```

`defaultIfEmpty` phát ra giá trị mặc định nếu publisher rỗng. Giá trị mặc định phải phù hợp với nghiệp vụ; không nên dùng nó để che khuất lỗi truy vấn hoặc lỗi kết nối.

### Biến đổi từng phần tử trong Flux

```java
public Flux<CustomerView> findActiveCustomers() {
    return customerRepository.findByStatusOrderByCreatedAtDesc("ACTIVE")
            .map(customerMapper::toView);
}
```

`map` được áp dụng cho từng phần tử mà `Flux` phát ra. Nếu không có khách hàng phù hợp, kết quả vẫn là một `Flux` rỗng và thao tác ánh xạ không được gọi.

Khi cần gọi một thao tác reactive khác cho từng phần tử, có thể dùng `flatMap`:

```java
return customerRepository.findAll()
        .flatMap(customer ->
                addressRepository.findByCustomerId(customer.getId())
                        .map(address -> customerMapper.toView(customer, address))
        );
```

`flatMap` kết hợp các publisher con thành một luồng kết quả. Nếu thứ tự phát kết quả là yêu cầu nghiệp vụ, cần chọn toán tử phù hợp với yêu cầu thứ tự và cân nhắc chi phí xử lý tuần tự; không nên mặc định rằng mọi cách dùng `flatMap` đều giữ thứ tự nguồn.

## 7. Mono<List<T>> và Flux<T> khác nhau thế nào?

Đôi khi ứng dụng cần một danh sách hoàn chỉnh. Khi đó có thể gom một `Flux<T>` thành `Mono<List<T>>` bằng `collectList()`:

```java
Mono<List<Customer>> allCustomers =
        customerRepository.findAll().collectList();
```

Hai kiểu này có ý nghĩa khác nhau:

| Kiểu | Cách phát kết quả | Hệ quả khi tiêu thụ |
| --- | --- | --- |
| `Flux<Customer>` | Phát từng khách hàng | Có thể xử lý từng phần tử khi luồng tiếp tục |
| `Mono<List<Customer>>` | Phát một danh sách sau khi thu thập xong | Phải giữ các phần tử đã thu thập trong bộ nhớ cho đến khi danh sách hoàn tất |

Nếu không có khách hàng, `Flux<Customer>` hoàn tất mà không phát phần tử; `collectList()` chuyển trường hợp đó thành một `Mono` phát ra danh sách rỗng. Nếu có dữ liệu, danh sách chỉ được phát sau khi quá trình thu thập hoàn tất.

Chỉ nên dùng `collectList()` khi tầng gọi thực sự cần một collection hoàn chỉnh và số lượng kết quả được kiểm soát hợp lý. Với truy vấn có thể trả về lượng dữ liệu lớn, gom tất cả vào một danh sách có thể tiêu tốn nhiều bộ nhớ và làm mất lợi ích xử lý theo luồng của `Flux`.

## 8. Chuyển Flux thành Mono: cần hiểu rõ ý nghĩa

Reactor có một số toán tử chuyển từ `Flux<T>` sang `Mono<T>`. Chúng không tương đương nhau:

```java
Mono<Customer> firstCustomer =
        customerRepository.findAll().next();

Mono<Customer> zeroOrOneCustomer =
        customerRepository.findAll().singleOrEmpty();
```

- `next()` lấy phần tử đầu tiên được phát ra rồi kết thúc việc tiêu thụ luồng. Nó không kiểm tra rằng truy vấn chỉ có một kết quả.
- `singleOrEmpty()` cho phép luồng có không hoặc một phần tử; nếu luồng phát ra nhiều hơn một phần tử, nó báo lỗi.
- `single()` yêu cầu đúng một phần tử; nó báo lỗi nếu luồng rỗng hoặc có nhiều hơn một phần tử.

Vì vậy, nếu nghiệp vụ yêu cầu xác nhận rằng kết quả là duy nhất, `singleOrEmpty()` thể hiện ý định rõ hơn `next()`. Dùng `next()` chỉ phù hợp khi yêu cầu thực sự là lấy phần tử đầu tiên, ví dụ một truy vấn có `ORDER BY` và giới hạn kết quả theo đúng mục đích.

## 9. Publisher được thực thi khi nào?

Khi gọi một phương thức repository và nhận về `Mono` hoặc `Flux`, ứng dụng đang nhận một mô tả công việc reactive. Với publisher truy vấn do Spring Data R2DBC tạo ra, thao tác cơ sở dữ liệu thường bắt đầu khi có subscriber tiêu thụ publisher.

Ví dụ:

```java
Mono<Customer> customerPublisher =
        customerRepository.findById(42L);

Mono<String> namePublisher =
        customerPublisher.map(Customer::getName);
```

Hai dòng trên xây dựng publisher và nối các bước xử lý. Trong một ứng dụng Spring WebFlux, controller có thể trả publisher cho framework; framework sẽ đăng ký tiêu thụ và xử lý kết quả theo vòng đời request.

Publisher không phải một biến chứa kết quả đã truy vấn. Nếu một publisher dạng cold được subscribe nhiều lần, mỗi lần subscribe có thể thực hiện lại thao tác truy vấn. Vì thế, không nên giả định rằng lưu một `Mono` vào biến đồng nghĩa với việc đã lưu kết quả của lần truy vấn trước.

## 10. Trả Mono và Flux từ tầng service hoặc WebFlux

Tầng service có thể giữ nguyên kiểu reactive để các tầng tiếp theo tiếp tục kết hợp publisher:

```java
public Mono<CustomerView> findCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .map(customerMapper::toView);
}

public Flux<CustomerView> findCustomersByStatus(String status) {
    return customerRepository.findByStatusOrderByCreatedAtDesc(status)
            .map(customerMapper::toView);
}
```

Một controller Spring WebFlux có thể trả trực tiếp các kiểu này:

```java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerRepository customerRepository;

    public CustomerController(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Customer>> findById(@PathVariable Long id) {
        return customerRepository.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.<Customer>notFound().build());
    }

    @GetMapping
    public Flux<Customer> findAll() {
        return customerRepository.findAll();
    }
}
```

Ở endpoint chi tiết, `Mono<Customer>` cho phép ánh xạ bản ghi tìm được thành phản hồi thành công hoặc tạo phản hồi không tìm thấy khi publisher rỗng. Ở endpoint danh sách, `Flux<Customer>` biểu diễn tập kết quả có thể gồm nhiều khách hàng. WebFlux chịu trách nhiệm subscribe publisher trong quá trình xử lý request.

## 11. Tránh block() và subscribe() trong luồng xử lý reactive

Không nên gọi `block()` trong một chuỗi xử lý reactive của ứng dụng:

```java
Customer customer = customerRepository.findById(id).block();
```

`block()` chờ kết quả bằng cách chặn thread hiện tại. Việc này làm mất lợi ích không chặn của R2DBC và có thể gây nghẽn thread khi nhiều request cùng chờ cơ sở dữ liệu. Trong service hoặc controller reactive, hãy trả về và kết hợp `Mono` hoặc `Flux` thay vì lấy kết quả đồng bộ.

Cũng không nên tự gọi `subscribe()` bên trong service chỉ để bắt đầu truy vấn:

```java
public void updateSomething(Long id) {
    customerRepository.findById(id).subscribe(customer -> {
        // Xử lý tách khỏi luồng mà caller đang quản lý
    });
}
```

Khi tự subscribe, service tách việc xử lý khỏi publisher mà caller nhận được. Caller khó phối hợp thời điểm hoàn tất, xử lý lỗi và ngữ cảnh giao dịch. Hãy trả publisher từ phương thức:

```java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
```

`block()` vẫn có thể xuất hiện ở ranh giới imperative được kiểm soát hoặc trong một số bài kiểm thử, nhưng không nên đưa nó vào đường đi xử lý request reactive.

## 12. Backpressure và truy vấn trả về nhiều hàng

`Flux` hỗ trợ cơ chế backpressure của Reactive Streams: subscriber có thể điều tiết số phần tử muốn nhận. Điều này giúp các thành phần trong pipeline phối hợp tốc độ xử lý khi làm việc với luồng nhiều phần tử.

Tuy nhiên, dùng `Flux` không tự động bảo đảm rằng toàn bộ đường đi dữ liệu không có buffering hoặc luôn sử dụng bộ nhớ cố định. Hành vi đọc theo lô, buffering và fetch phụ thuộc vào driver R2DBC, cơ sở dữ liệu và cách truy vấn được thực thi. Ứng dụng vẫn cần cân nhắc kích thước kết quả, giới hạn truy vấn và cách xử lý từng phần tử.

Ví dụ, với danh sách khách hàng lớn, giữ kết quả ở dạng `Flux<Customer>` và xử lý theo từng phần tử thường phù hợp hơn việc gọi `collectList()` rồi giữ toàn bộ danh sách trong bộ nhớ. Nếu giao diện chỉ cần một phần dữ liệu, hãy thiết kế truy vấn có giới hạn hoặc phân trang phù hợp thay vì tải toàn bộ bảng.

## 13. Kiểm thử hành vi Mono và Flux

Có thể dùng Reactor Test với `StepVerifier` để kiểm tra các tín hiệu mà publisher phát ra. Ví dụ kiểm tra truy vấn đơn:

```java
StepVerifier.create(customerRepository.findById(42L))
        .expectNextMatches(customer -> customer.getId().equals(42L))
        .verifyComplete();
```

Và kiểm tra truy vấn nhiều kết quả:

```java
StepVerifier.create(customerRepository.findByStatus("ACTIVE"))
        .expectNextCount(2)
        .verifyComplete();
```

Ngoài giá trị phát ra, kiểm thử reactive nên chú ý cả trường hợp publisher rỗng và trường hợp kết thúc bằng lỗi. Chẳng hạn, truy vấn theo khóa chính cần có kiểm thử cho ID không tồn tại; truy vấn dự kiến duy nhất cần kiểm tra cách hệ thống phản ứng nếu dữ liệu vi phạm giả định duy nhất.

## 14. Những nhầm lẫn thường gặp

1. **Cho rằng Mono luôn có một kết quả.** `Mono<T>` cho phép không có kết quả; trường hợp không tìm thấy thường là `Mono.empty()`.
2. **Dùng Mono cho truy vấn có thể trả về nhiều hàng.** Kiểu trả về cần khớp với cardinality của truy vấn và quy tắc dữ liệu.
3. **Dùng next() để giả vờ kết quả là duy nhất.** `next()` chỉ lấy phần tử đầu tiên; nó không phát hiện dữ liệu trùng.
4. **Coi Flux như một List đã có sẵn.** `Flux<T>` là publisher phát các phần tử theo thời gian tiêu thụ; muốn có list hoàn chỉnh phải chủ động thu thập.
5. **Gọi collectList() cho mọi truy vấn.** Việc thu thập toàn bộ có thể tốn bộ nhớ và làm mất lợi ích xử lý từng phần tử.
6. **Dùng block() hoặc subscribe() tùy tiện.** Hai cách này có thể phá vỡ việc phối hợp reactive giữa repository, service và framework.
7. **Giả định Flux luôn có thứ tự cố định.** Nếu nghiệp vụ phụ thuộc thứ tự hàng trong kết quả SQL, hãy chỉ định `ORDER BY`.
8. **Nhầm kết quả rỗng với lỗi truy vấn.** Không có hàng phù hợp là một kết quả hợp lệ; lỗi kết nối hoặc lỗi SQL được truyền bằng tín hiệu `onError`.

## Quy tắc chọn nhanh

- Chọn `Mono<T>` khi truy vấn trả về không hoặc một giá trị, ví dụ tìm theo khóa chính hoặc thuộc tính duy nhất.
- Chọn `Flux<T>` khi truy vấn có thể trả về nhiều entity, ví dụ tìm tất cả bản ghi theo trạng thái.
- Chọn `Mono<Long>` hoặc `Mono<Boolean>` cho các kết quả đơn như đếm hoặc kiểm tra tồn tại.
- Chọn `Mono<Void>` khi chỉ cần biết thao tác đã hoàn tất hay gặp lỗi.
- Chỉ chuyển `Flux<T>` thành `Mono<List<T>>` khi cần danh sách hoàn chỉnh và lượng dữ liệu có thể kiểm soát.

Khi thiết kế repository Spring Data R2DBC, hãy bắt đầu từ câu hỏi truy vấn có thể trả về bao nhiêu hàng. Sau đó chọn `Mono` hoặc `Flux` phù hợp và giữ kiểu reactive xuyên suốt các tầng xử lý. Cách này làm rõ hợp đồng dữ liệu của phương thức, xử lý đúng trường hợp không có kết quả và duy trì mô hình truy cập cơ sở dữ liệu không chặn.
