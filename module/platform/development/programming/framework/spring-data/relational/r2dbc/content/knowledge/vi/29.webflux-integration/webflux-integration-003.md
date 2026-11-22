# Chọn Mono hoặc Flux theo hợp đồng API

Trong Spring Data R2DBC và Spring WebFlux, kiểu reactive trả về là một phần của hợp đồng API. **Mono<T>** biểu diễn một kết quả có thể không tồn tại hoặc chỉ có một phần tử; **Flux<T>** biểu diễn một luồng có thể không có phần tử, có một phần tử hoặc có nhiều phần tử. Chọn kiểu phù hợp giúp repository, service và controller nói cùng một ngôn ngữ về số lượng kết quả mà caller có thể nhận.

Không nên chọn Mono hay Flux chỉ theo thói quen hoặc theo kiểu dữ liệu đang có trong database. Hãy bắt đầu từ ý nghĩa nghiệp vụ: endpoint trả về một tài nguyên, một giá trị tổng hợp, một tập kết quả hữu hạn hay một luồng sự kiện kéo dài? Sau đó chọn kiểu publisher, cách xử lý trường hợp rỗng, định dạng HTTP và chính sách phân trang tương ứng.

## 1. Cardinality của Mono và Flux

Reactive Streams không phát giá trị null. Một publisher kết thúc bằng một trong các trạng thái: phát phần tử rồi hoàn tất, hoàn tất mà không phát phần tử, hoặc phát lỗi. Cancellation có thể được subscriber gửi để yêu cầu dừng subscription.

Hai kiểu cơ bản của Reactor:

| Kiểu | Cardinality | Ý nghĩa |
|---|---|---|
| Mono<T> | 0 hoặc 1 | Một kết quả tùy chọn |
| Flux<T> | 0 đến N | Một tập kết quả hoặc luồng phần tử |
| Mono<Void> | 0 giá trị | Chỉ quan tâm hoàn tất hoặc lỗi |
| Flux<Void> | Thường không cần dùng cho API dữ liệu | Luồng các tín hiệu hoàn tất không mang giá trị |

### 1.1. Mono<T>: một hoặc không có kết quả

Mono phù hợp khi hợp đồng nghiệp vụ nói rằng một thao tác trả về tối đa một đối tượng:

- Tìm khách hàng theo ID.
- Tìm tài khoản theo số định danh duy nhất.
- Tạo một đơn hàng.
- Cập nhật một bản ghi và trả về trạng thái mới.
- Tính một tổng số hoặc một kết quả tổng hợp.

Ví dụ:

~~~java
Mono<Customer> findById(Long id);

Mono<Customer> findByEmail(String email);

Mono<Order> createOrder(CreateOrderCommand command);
~~~

Mono có thể phát đúng một Customer rồi complete, hoặc complete mà không phát Customer. Trường hợp không có phần tử được biểu diễn bằng Mono.empty(), không phải Mono.just(null).

### 1.2. Flux<T>: không hoặc nhiều kết quả

Flux phù hợp khi truy vấn có thể trả về nhiều bản ghi:

- Danh sách khách hàng đang hoạt động.
- Các đơn hàng của một khách hàng.
- Các dòng dữ liệu trong báo cáo.
- Các sự kiện hoặc thông báo được phát theo thời gian.
- Kết quả tìm kiếm theo bộ lọc.

Ví dụ:

~~~java
Flux<Customer> findByActiveTrue();

Flux<Order> findByCustomerId(Long customerId);

Flux<OrderLine> findLinesByOrderId(Long orderId);
~~~

Flux có thể phát 0, 1 hoặc nhiều Order. Không cần đổi sang Mono chỉ vì một lần chạy cụ thể chỉ có một kết quả; kiểu trả về phải phản ánh cardinality mà hợp đồng cho phép.

### 1.3. Không dùng null làm tín hiệu không tìm thấy

Reactive Streams không cho phép publisher phát null. Những cách sau là sai hoặc không phù hợp:

~~~java
return Mono.just(null);
~~~

Thay vào đó, dùng:

~~~java
return Mono.empty();
~~~

Nếu đầu vào là giá trị nullable từ một API đồng bộ:

~~~java
return Mono.justOrEmpty(possiblyNullValue);
~~~

Ở tầng API, Mono.empty() là tín hiệu không có kết quả. Controller hoặc service phải quyết định ý nghĩa HTTP/nghiệp vụ của trường hợp đó.

## 2. Chọn kiểu trả về trong Spring Data R2DBC Repository

Spring Data R2DBC cung cấp reactive repository abstraction. Chữ ký phương thức nên dùng Mono hoặc Flux tùy theo số kết quả mà truy vấn có thể trả về.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    String fullName,
    String email,
    Boolean active
) {}
~~~

Repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByFullNameContainingIgnoreCase(String fragment);
}
~~~

Các phương thức CRUD cơ bản cũng phản ánh cardinality:

| Phương thức repository | Kiểu trả về thường gặp | Ý nghĩa |
|---|---|---|
| findById(id) | Mono<T> | Không hoặc một entity theo ID |
| findById(Publisher<ID>) | Mono<T> | Một ID được phát bất đồng bộ |
| findAll() | Flux<T> | Tập entity |
| findAllById(ids) | Flux<T> | Các entity khớp với nhiều ID |
| save(entity) | Mono<S> | Một entity được lưu |
| saveAll(entities) | Flux<S> | Nhiều entity được lưu |
| deleteById(id) | Mono<Void> | Hoàn tất hoặc lỗi |
| count() | Mono<Long> | Một giá trị đếm |
| existsById(id) | Mono<Boolean> | Một giá trị đúng/sai |

Không khai báo List, Optional hoặc Page đồng bộ làm kiểu trả về cho một reactive repository method như thể đó là một lời gọi blocking. Hãy dùng kiểu reactive được Spring Data hỗ trợ và để publisher được thực thi trong luồng reactive.

### 2.1. Truy vấn theo khóa duy nhất: Mono

Nếu id là primary key, findById phù hợp với Mono vì tối đa một hàng có thể khớp:

~~~java
Mono<Customer> customer = customerRepository.findById(id);
~~~

Tương tự, nếu email có unique constraint và nghiệp vụ bảo đảm mỗi email chỉ thuộc về một khách hàng:

~~~java
Mono<Customer> customer = customerRepository.findByEmail(email);
~~~

Nếu điều kiện truy vấn không thực sự duy nhất, việc chọn Mono cần thận trọng. Truy vấn có thể phát lỗi nếu có nhiều kết quả trong khi chữ ký yêu cầu tối đa một kết quả. Hãy dùng Flux nếu nhiều hàng là hợp lệ, hoặc bảo đảm uniqueness ở schema và nghiệp vụ.

### 2.2. Truy vấn danh sách: Flux

Nếu một khách hàng có nhiều đơn hàng:

~~~java
Flux<Order> orders =
    orderRepository.findByCustomerId(customerId);
~~~

Không dùng Mono<Order> chỉ vì UI hiện tại chỉ hiển thị một đơn gần nhất. Nếu nghiệp vụ thực sự cần đơn gần nhất, hãy diễn đạt thứ tự và giới hạn trong truy vấn, rồi trả về Mono<Order>:

~~~java
Mono<Order> findFirstByCustomerIdOrderByCreatedAtDesc(Long customerId);
~~~

Tên derived query phải phù hợp với property và cú pháp của Spring Data version đang dùng. Có thể dùng Query/Criteria hoặc @Query khi cần kiểm soát sort/limit rõ ràng.

## 3. Phân biệt không có kết quả với lỗi

Mono.empty() và onError là hai trạng thái khác nhau.

| Trạng thái | Ví dụ | Cách hiểu |
|---|---|---|
| Mono có giá trị | Tìm thấy Customer | Truy vấn thành công, có kết quả |
| Mono.empty() | ID không tồn tại | Truy vấn thành công, không có kết quả |
| onError | Database mất kết nối | Thao tác thất bại |
| Flux.empty() | Không có đơn hàng phù hợp | Truy vấn thành công, tập kết quả rỗng |
| Flux phát phần tử rồi onError | Đọc luồng bị lỗi giữa chừng | Có dữ liệu một phần nhưng luồng không hoàn tất |

Không chuyển mọi lỗi database thành Mono.empty(). Làm vậy khiến lỗi kết nối, lỗi SQL hoặc vi phạm constraint bị hiểu nhầm thành “không tìm thấy”.

Ví dụ xử lý kết quả tùy chọn ở service:

~~~java
public Mono<Customer> requireCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ));
}
~~~

Ở đây, chỉ trường hợp Mono.empty() mới được chuyển thành lỗi domain. Lỗi database vẫn truyền xuống downstream theo nhánh onError.

## 4. Ánh xạ Mono.empty() thành HTTP status trong WebFlux

Một endpoint tìm một tài nguyên thường cần trả 404 khi tài nguyên không tồn tại. Mono.empty() chỉ biểu diễn không có giá trị; nó không tự mang ý nghĩa HTTP 404 trong mọi controller contract.

Một cách rõ ràng là trả về Mono<ResponseEntity<T>> và quyết định status dựa trên kết quả:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping("/customers/{id}")
    public Mono<ResponseEntity<?>> getById(
            @PathVariable Long id) {

        return service.findById(id)
            .<ResponseEntity<?>>map(ResponseEntity::ok)
            .defaultIfEmpty(
                ResponseEntity.notFound().build()
            );
    }
}
~~~

Mẫu trên thể hiện hợp đồng: có Customer thì trả 200 cùng body; không có Customer thì trả 404. Kiểu ResponseEntity<?> cho phép hai nhánh trả về body có kiểu khác nhau trong khi cùng một publisher.

Một cách khác là chuyển empty thành exception:

~~~java
@GetMapping("/customers/{id}")
public Mono<CustomerDto> getById(@PathVariable Long id) {
    return service.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ));
}
~~~

Sau đó dùng @ExceptionHandler hoặc @RestControllerAdvice để ánh xạ CustomerNotFoundException thành 404.

Không nên giả định rằng mọi controller method trả Mono<T> và nhận Mono.empty() sẽ tự động tạo đúng status mà API mong muốn. Hãy định nghĩa rõ status và body cho trường hợp không có kết quả.

### 4.1. Khi nào trả 204 No Content?

204 phù hợp khi request được xử lý thành công nhưng API không trả representation trong response body, thường gặp ở thao tác xóa hoặc cập nhật không cần trả dữ liệu.

Ví dụ:

~~~java
@DeleteMapping("/customers/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable Long id) {
    return service.delete(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

Nếu nghiệp vụ cần phân biệt xóa thành công với không tồn tại, service phải kiểm tra kết quả hoặc dùng exception riêng. Một phương thức deleteById trả Mono<Void> chỉ biểu diễn hoàn tất/lỗi, không nhất thiết cung cấp số hàng bị xóa.

### 4.2. 404, 204 và 200 với body rỗng là các hợp đồng khác nhau

- 404: tài nguyên được yêu cầu không tồn tại.
- 204: thao tác thành công và không có nội dung response.
- 200 với body rỗng: response thành công nhưng không mang representation; thường không phải cách diễn đạt rõ nhất cho trường hợp tài nguyên không tồn tại.

Hãy chọn status theo semantics của endpoint và tài liệu API, không chỉ theo kiểu Mono.empty().

## 5. Flux trong WebFlux: JSON array hay streaming?

Flux<T> biểu diễn nhiều phần tử, nhưng điều đó không có nghĩa mọi HTTP response sẽ tự động truyền từng phần tử ngay khi có.

Cách WebFlux encode Flux phụ thuộc media type và codec.

### 5.1. application/json: response dạng JSON array

Một endpoint danh sách thường trả Flux<T>:

~~~java
@GetMapping(
    value = "/customers",
    produces = "application/json"
)
public Flux<CustomerDto> list() {
    return service.findAll();
}
~~~

Với media type không streaming như application/json, WebFlux thường gom các phần tử để encode thành một JSON array:

~~~json
[
  {"id": 1, "fullName": "An"},
  {"id": 2, "fullName": "Binh"}
]
~~~

Hợp đồng này phù hợp với danh sách hữu hạn và có giới hạn hợp lý. Client nhận một JSON document có thể parse như array.

Không nên giả định server luôn gửi từng JSON object ngay khi database phát ra một phần tử. Với kiểu media type không streaming, codec có thể cần thu thập dữ liệu trước khi ghi response hoàn chỉnh.

### 5.2. Streaming media type

Nếu endpoint cần truyền từng phần tử khi có dữ liệu, hãy chọn media type có semantics streaming mà codec hỗ trợ, ví dụ:

- application/x-ndjson: mỗi dòng là một JSON document.
- application/stream+json: luồng JSON theo định dạng streaming được hỗ trợ.
- text/event-stream: Server-Sent Events.

Ví dụ NDJSON:

~~~java
@GetMapping(
    value = "/customers/stream",
    produces = "application/x-ndjson"
)
public Flux<CustomerDto> streamCustomers() {
    return service.findAll();
}
~~~

Response có thể được truyền thành từng dòng:

~~~text
{"id":1,"fullName":"An"}
{"id":2,"fullName":"Binh"}
{"id":3,"fullName":"Chi"}
~~~

Với Server-Sent Events, có thể trả Flux<ServerSentEvent<T>>:

~~~java
@GetMapping(
    value = "/events",
    produces = "text/event-stream"
)
public Flux<ServerSentEvent<OrderEvent>> events() {
    return eventService.events()
        .map(event ->
            ServerSentEvent.builder(event)
                .event("order")
                .id(event.id())
                .build()
        );
}
~~~

SSE phù hợp với luồng server-to-client kéo dài. Nó có event ID và cơ chế reconnect của client; ứng dụng vẫn cần thiết kế replay/resume nếu không muốn mất sự kiện trong thời gian client ngắt kết nối.

### 5.3. Streaming không thay thế pagination

Một Flux đọc toàn bộ bảng rồi stream ra client vẫn có thể tạo tải lớn lên database, connection và network. Nếu client đọc chậm, query có thể giữ connection trong thời gian dài.

Với danh sách dữ liệu thông thường, pagination thường phù hợp hơn streaming toàn bảng. Streaming nên dành cho trường hợp hợp đồng thật sự yêu cầu một luồng dài hoặc dữ liệu lớn được tiêu thụ dần.

## 6. Mono<List<T>> hay Flux<T>?

Hai kiểu này biểu diễn hai hợp đồng khác nhau.

~~~java
Flux<CustomerDto> stream = service.findCustomers();

Mono<List<CustomerDto>> collected =
    service.findCustomers().collectList();
~~~

Flux phát từng CustomerDto. Mono<List<CustomerDto>> chỉ phát một danh sách sau khi toàn bộ nguồn hoàn tất.

| Tiêu chí | Flux<T> | Mono<List<T>> |
|---|---|---|
| Cardinality | 0..N phần tử | 0 hoặc 1 danh sách |
| Thời điểm nhận phần tử | Có thể nhận dần theo publisher | Chỉ nhận danh sách sau khi collect hoàn tất |
| Bộ nhớ | Có thể xử lý từng phần tử | Phải giữ danh sách đã thu thập trong bộ nhớ |
| Phù hợp | Luồng dữ liệu, xử lý tuần tự, streaming | Tập kết quả hữu hạn, có giới hạn |
| Empty | Flux.empty() | Mono phát List rỗng nếu collectList() từ Flux.empty() |
| Lỗi giữa luồng | Có thể đã phát phần tử trước lỗi | Danh sách không được phát nếu collectList kết thúc bằng lỗi |

Dùng collectList() khi caller thật sự cần một collection hoàn chỉnh, ví dụ tạo một response aggregate nhỏ. Không dùng collectList() trên một luồng không giới hạn hoặc bảng rất lớn vì có thể gây tăng bộ nhớ không kiểm soát.

### 6.1. Khi nào Mono<List<T>> hợp lý?

Ví dụ API cần trả một nhóm kết quả nhỏ, có giới hạn:

~~~java
public Mono<List<CustomerDto>> featuredCustomers() {
    return customerRepository.findTop10ByActiveTrueOrderByFullName()
        .map(CustomerDto::from)
        .collectList();
}
~~~

Đây là danh sách có giới hạn 10 phần tử, nên việc gom thành List có thể hợp lý nếu hợp đồng API cần một giá trị collection hoàn chỉnh.

### 6.2. Khi nào nên giữ Flux<T>?

Nếu truy vấn có thể trả hàng trăm nghìn dòng hoặc là luồng sự kiện kéo dài, giữ Flux để xử lý dần:

~~~java
public Flux<CustomerDto> exportCustomers() {
    return customerRepository.findAll()
        .map(CustomerDto::from);
}
~~~

Tuy nhiên, export toàn bộ bảng cần có chiến lược batch/keyset, giới hạn tài nguyên và timeout. Không nên giữ một connection database mở quá lâu chỉ để chờ client tải dữ liệu chậm.

## 7. Chọn Mono hoặc Flux ở tầng Service

Repository phản ánh cardinality của dữ liệu. Service phản ánh hợp đồng nghiệp vụ. Service có thể chuyển đổi kiểu publisher nếu logic nghiệp vụ thay đổi cardinality.

Ví dụ lấy một khách hàng và tính tổng đơn hàng:

~~~java
public Mono<CustomerSummary> summary(Long customerId) {
    return customerRepository.findById(customerId)
        .flatMap(customer ->
            orderRepository.findByCustomerId(customerId)
                .map(Order::totalAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                .map(total -> new CustomerSummary(
                    customer.id(),
                    customer.fullName(),
                    total
                ))
        );
}
~~~

Repository trả Mono<Customer> và Flux<Order>. Service tổng hợp nhiều Order thành một CustomerSummary, do đó trả Mono<CustomerSummary>.

Ví dụ kiểm tra tất cả đơn hàng có được phép đóng không:

~~~java
public Mono<Boolean> canCloseCustomer(Long customerId) {
    return orderRepository.findByCustomerId(customerId)
        .all(Order::isClosed);
}
~~~

all() tạo Mono<Boolean>. Flux rỗng trả true theo logic all: không có phần tử nào vi phạm điều kiện. Nếu nghiệp vụ yêu cầu phải có ít nhất một đơn hàng, cần kết hợp thêm hasElements() hoặc count() theo đúng ý nghĩa.

Ví dụ lấy phần tử đầu tiên từ Flux:

~~~java
public Mono<Order> latestOrder(Long customerId) {
    return orderRepository
        .findByCustomerIdOrderByCreatedAtDesc(customerId)
        .next();
}
~~~

next() chuyển Flux thành Mono và lấy phần tử đầu tiên. Truy vấn cần có thứ tự rõ ràng; không dựa vào thứ tự mặc định của database.

### 7.1. Chuyển Flux thành Mono bằng các toán tử tổng hợp

| Toán tử | Kết quả | Ý nghĩa |
|---|---|---|
| collectList() | Mono<List<T>> | Thu toàn bộ phần tử thành List |
| count() | Mono<Long> | Đếm số phần tử |
| hasElements() | Mono<Boolean> | Có ít nhất một phần tử |
| all(predicate) | Mono<Boolean> | Tất cả phần tử thỏa điều kiện |
| any(predicate) | Mono<Boolean> | Có ít nhất một phần tử thỏa điều kiện |
| reduce(...) | Mono<A> | Gộp các phần tử thành một giá trị |
| next() | Mono<T> | Lấy phần tử đầu tiên rồi hủy nguồn |
| singleOrEmpty() | Mono<T> | Yêu cầu tối đa một phần tử; lỗi nếu có nhiều hơn |

Chọn toán tử theo ý nghĩa nghiệp vụ. Đặc biệt, singleOrEmpty() khác next(): singleOrEmpty() xác nhận cardinality tối đa một, còn next() chủ động lấy phần tử đầu và không quan tâm phần tử tiếp theo.

## 8. Chọn kiểu kết quả khi dùng R2dbcEntityTemplate

R2dbcEntityTemplate cũng trả về kiểu reactive dựa trên cardinality.

Ví dụ select nhiều entity:

~~~java
Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Lấy một kết quả duy nhất:

~~~java
Mono<Customer> customer =
    template.select(Customer.class)
        .matching(query)
        .one();
~~~

Count và exists:

~~~java
Mono<Long> count =
    template.count(query, Customer.class);

Mono<Boolean> exists =
    template.exists(query, Customer.class);
~~~

Với thao tác update/delete, template thường trả Mono<Long> biểu diễn số hàng tác động:

~~~java
Mono<Long> updated =
    template.update(Customer.class)
        .matching(query)
        .apply(update);
~~~

Đừng đổi Flux thành Mono bằng cách lấy phần tử đầu chỉ để làm chữ ký method trông đơn giản hơn. Nếu điều kiện có thể khớp nhiều hàng, hãy giữ Flux hoặc định nghĩa một quy tắc giới hạn/sắp xếp rõ ràng.

## 9. Pagination: hợp đồng danh sách hữu hạn

Một endpoint danh sách thường nên có pagination thay vì trả toàn bộ bảng.

Ví dụ repository method nhận Pageable và trả Flux:

~~~java
Flux<Customer> findByActiveTrue(Pageable pageable);
~~~

Controller có thể nhận page và size, kiểm tra giới hạn rồi tạo Pageable:

~~~java
@GetMapping("/customers")
public Flux<CustomerDto> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    int safeSize = Math.min(Math.max(size, 1), 100);
    int safePage = Math.max(page, 0);

    Pageable pageable = PageRequest.of(
        safePage,
        safeSize,
        Sort.by("fullName").ascending()
    );

    return service.findActive(pageable);
}
~~~

Ví dụ minh họa; cần import Pageable, PageRequest, Sort và bảo đảm repository method hỗ trợ Pageable theo Spring Data version đang dùng.

Reactive repository thường không trả Page<T> theo cách đồng bộ truyền thống vì Page cần cả dữ liệu và thông tin tổng số phần tử. Thay vào đó, có thể trả Flux<T> cho trang dữ liệu và Mono<Long> cho count, rồi kết hợp ở service thành một DTO:

~~~java
public Mono<CustomerPage> findPage(Pageable pageable) {
    Flux<CustomerDto> content =
        repository.findByActiveTrue(pageable)
            .map(CustomerDto::from);

    Mono<Long> total =
        repository.countByActiveTrue();

    return Mono.zip(content.collectList(), total)
        .map(tuple -> new CustomerPage(
            tuple.getT1(),
            tuple.getT2(),
            pageable.getPageNumber(),
            pageable.getPageSize()
        ));
}
~~~

DTO ví dụ:

~~~java
public record CustomerPage(
    List<CustomerDto> content,
    long totalElements,
    int page,
    int size
) {}
~~~

Đây là hợp đồng một response trang hoàn chỉnh nên Mono<CustomerPage> phù hợp. Content được thu thập thành List chỉ trong phạm vi một trang đã giới hạn.

Count và select là hai câu truy vấn riêng. Nếu dữ liệu thay đổi giữa hai câu lệnh, total và content có thể phản ánh hai thời điểm khác nhau tùy isolation/transaction. Nếu cần snapshot nhất quán, phải thiết kế transaction/isolation phù hợp và hiểu tác động lên connection.

### 9.1. Keyset pagination

Offset pagination có thể tốn kém khi page rất sâu. Với tập dữ liệu lớn, keyset pagination dùng giá trị khóa cuối cùng của trang trước để tìm trang tiếp theo.

Ví dụ truy vấn theo ID tăng dần:

~~~sql
SELECT id, full_name, email
FROM customer
WHERE id > :lastSeenId
ORDER BY id
LIMIT :size
~~~

Repository/template có thể trả Flux<Customer> cho từng batch. API có thể trả Mono<CustomerCursorPage> gồm danh sách hữu hạn và nextCursor. Cách này tránh offset lớn nhưng yêu cầu thứ tự ổn định và cursor phù hợp với điều kiện lọc.

## 10. Backpressure và streaming API

Flux hỗ trợ backpressure ở mức Reactive Streams: subscriber có thể yêu cầu số phần tử mà nó sẵn sàng nhận. Điều này giúp các publisher phối hợp tốc độ xử lý và tránh phát dữ liệu không giới hạn trong bộ nhớ.

Tuy nhiên, không nên giả định backpressure được truyền nguyên vẹn từ HTTP client tới database trong mọi tình huống. Codec có thể buffer, driver có thể prefetch, và network layer có cơ chế buffering riêng. Hãy giới hạn kết quả, dùng batch và đo tài nguyên thực tế.

### 10.1. Xử lý tuần tự và đồng thời

Ví dụ xử lý từng hàng tuần tự:

~~~java
return repository.findAll()
    .concatMap(this::processCustomer);
~~~

concatMap chỉ xử lý một inner publisher tại một thời điểm và giữ thứ tự. Nếu dùng flatMap:

~~~java
return repository.findAll()
    .flatMap(this::processCustomer, 8);
~~~

các phần tử có thể được xử lý đồng thời với concurrency tối đa được chỉ định; thứ tự kết quả không được bảo đảm như concatMap.

Chọn concurrency theo khả năng database, giới hạn downstream và nghiệp vụ. Tăng concurrency quá mức có thể làm pool hết connection hoặc tạo tải lớn lên hệ thống đích.

### 10.2. Streaming có thể giữ connection lâu

Một Flux đọc database và truyền trực tiếp cho client chậm có thể kéo dài thời gian tiêu thụ kết quả. Tùy driver và cách fetch, connection có thể được giữ trong thời gian stream.

Với dữ liệu export lớn, cân nhắc:

- Đọc theo batch/keyset thay vì giữ một truy vấn không giới hạn.
- Ghi file tạm hoặc object storage rồi trả link nếu phù hợp.
- Giới hạn thời gian và số phần tử.
- Đóng tài nguyên khi client hủy.
- Không giữ transaction dài chỉ để truyền dữ liệu cho client.

## 11. Cancellation và client ngắt kết nối

Khi client HTTP ngắt kết nối, WebFlux có thể hủy subscription của publisher response. Cancellation truyền ngược qua reactive chain và các thao tác upstream được yêu cầu dừng nếu có thể.

Với R2DBC, driver có thể hỗ trợ hủy statement đang chạy; khả năng dừng thực tế phụ thuộc driver và database. Không được giả định cancellation luôn chứng minh SQL chưa thực thi hoặc đã rollback.

Nếu publisher nằm trong reactive transaction được Spring quản lý, cancellation trước commit có thể làm transaction đang mở rollback. Nếu transaction đã commit, cancellation đến sau không thể đảo ngược dữ liệu.

Điều này đặc biệt quan trọng với endpoint ghi dữ liệu: client timeout không đồng nghĩa server chưa tạo đơn hàng. Với request có thể được gửi lại, dùng idempotency key hoặc một định danh nghiệp vụ duy nhất để tránh tạo dữ liệu trùng.

## 12. Error handling cho Mono và Flux

Mono có tối đa một phần tử; Flux có thể đã phát nhiều phần tử trước khi gặp lỗi.

Ví dụ Mono:

~~~java
return repository.findById(id)
    .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
    .onErrorMap(
        DataAccessException.class,
        error -> new CustomerStorageException(error)
    );
~~~

Ví dụ Flux:

~~~java
return repository.findByActiveTrue()
    .onErrorMap(
        DataAccessException.class,
        error -> new CustomerStorageException(error)
    );
~~~

Không thay lỗi database bằng Flux.empty() nếu nghiệp vụ cần báo lỗi. Việc đó khiến client tưởng không có dữ liệu trong khi thực tế database đang lỗi.

### 12.1. Flux có thể phát một phần dữ liệu rồi lỗi

Ví dụ một Flux stream 100 phần tử, phát được 20 phần tử rồi connection bị mất. Subscriber có thể đã nhận 20 phần tử trước khi nhận onError.

Với response JSON array không streaming, WebFlux thường cần hoàn thành việc encode trước khi response body đầy đủ được ghi; lỗi có thể làm response không hoàn chỉnh và server không thể thay body một cách an toàn sau khi response đã commit.

Với NDJSON hoặc SSE, client có thể đã nhận và xử lý một số phần tử trước lỗi. API cần xác định cách client nhận biết stream kết thúc bất thường, retry hoặc tiếp tục từ cursor/event ID.

### 12.2. Exception handler tập trung

Có thể dùng @RestControllerAdvice để ánh xạ lỗi domain thành HTTP status:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            CustomerNotFoundException error) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.NOT_FOUND);

        problem.setDetail(error.getMessage());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(problem);
    }
}
~~~

Đây là ví dụ xử lý lỗi đồng bộ ở tầng exception handler; controller/service vẫn có thể phát Mono/Flux. Không để exception handler biến mọi DataAccessException thành 404.

## 13. Chọn hợp đồng API theo use case

| Use case | Kiểu service/controller phù hợp | Hợp đồng HTTP thường gặp |
|---|---|---|
| Lấy một resource theo ID | Mono<DTO> hoặc Mono<ResponseEntity<DTO>> | 200 hoặc 404 |
| Tạo một resource | Mono<DTO> hoặc Mono<ResponseEntity<DTO>> | 201 Created, có thể kèm Location |
| Cập nhật và trả resource mới | Mono<DTO> | 200 |
| Xóa và không trả body | Mono<Void> hoặc Mono<ResponseEntity<Void>> | 204 |
| Tìm kiếm danh sách hữu hạn | Flux<DTO> hoặc Mono<PageDto> | JSON array hoặc object phân trang |
| Trang kết quả có total count | Mono<PageDto> | Một JSON object chứa content và metadata |
| Export/stream dữ liệu | Flux<DTO> | NDJSON hoặc media type streaming |
| Server push event | Flux<ServerSentEvent<T>> | text/event-stream |
| Chỉ đếm | Mono<Long> | Một JSON number hoặc field trong DTO |
| Kiểm tra tồn tại | Mono<Boolean> | Một boolean hoặc status theo thiết kế API |

Đây là các lựa chọn phổ biến, không phải quy tắc bắt buộc cho mọi endpoint. Hợp đồng cuối cùng cần thống nhất với client và tài liệu API.

### 13.1. Tạo resource: Mono và 201 Created

Ví dụ:

~~~java
@PostMapping("/customers")
public Mono<ResponseEntity<CustomerDto>> create(
        @RequestBody CreateCustomerRequest request) {

    return service.create(request)
        .map(dto -> ResponseEntity
            .created(URI.create("/customers/" + dto.id()))
            .body(dto));
}
~~~

Một request tạo một customer nên service trả Mono<CustomerDto>. Controller trả một ResponseEntity với 201 Created và Location.

### 13.2. Xóa resource: Mono<Void>

~~~java
@DeleteMapping("/customers/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable Long id) {
    return service.delete(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

Mono<Void> thể hiện chỉ cần biết thao tác hoàn tất hoặc phát lỗi. Nếu cần trả 404 khi ID không tồn tại, service cần kiểm tra sự tồn tại hoặc dùng một delete query có count.

### 13.3. Tìm kiếm: Flux hoặc page DTO

Danh sách nhỏ có thể trả Flux<CustomerDto>:

~~~java
@GetMapping("/customers/active")
public Flux<CustomerDto> activeCustomers() {
    return service.findActive();
}
~~~

Danh sách cần total/page metadata nên trả Mono<CustomerPage>. Chọn theo nhu cầu của client: array đơn giản hay một object chứa content, total, page và size.

## 14. Kiểm thử hợp đồng Mono/Flux

Dùng StepVerifier để kiểm thử cardinality và tín hiệu reactive:

~~~java
StepVerifier.create(repository.findById(knownId))
    .expectNextMatches(customer ->
        customer.id().equals(knownId)
    )
    .verifyComplete();
~~~

Trường hợp không tìm thấy:

~~~java
StepVerifier.create(repository.findById(missingId))
    .verifyComplete();
~~~

Flux nhiều kết quả:

~~~java
StepVerifier.create(repository.findByActiveTrue())
    .expectNextCount(2)
    .verifyComplete();
~~~

Kiểm thử HTTP bằng WebTestClient:

~~~java
webTestClient.get()
    .uri("/customers/{id}", knownId)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(knownId);
~~~

Trường hợp không tồn tại:

~~~java
webTestClient.get()
    .uri("/customers/{id}", missingId)
    .exchange()
    .expectStatus().isNotFound();
~~~

Với endpoint NDJSON hoặc SSE, kiểm tra Content-Type, format từng event và hành vi khi stream kết thúc. Nếu kiểm thử cancellation, xác nhận publisher upstream được cancel và transaction/resource được giải phóng theo cấu hình.

Các kiểm thử nên bao gồm:

- Mono có một kết quả và Mono empty.
- Flux empty, một phần tử và nhiều phần tử.
- Truy vấn Mono không được phép trả nhiều hàng.
- 404 khi resource không tồn tại.
- 201 khi tạo resource và Location hợp lệ.
- 204 khi xóa thành công mà không có body.
- JSON array so với NDJSON/SSE streaming.
- Lỗi database không bị biến thành empty result.
- Client cancel và cleanup connection.
- Pagination giới hạn số hàng và count phù hợp.

## 15. Những lỗi thường gặp

**Dùng Mono cho truy vấn có thể trả nhiều hàng.** Hợp đồng sai cardinality có thể gây lỗi khi có nhiều kết quả. Dùng Flux hoặc giới hạn/sắp xếp truy vấn rõ ràng.

**Dùng Flux cho một resource theo ID.** Flux khiến caller phải tự xử lý trường hợp nhiều phần tử dù ID là duy nhất. Mono thể hiện đúng hợp đồng 0..1.

**Cho rằng Mono.empty() tự động là 404.** Empty chỉ là không có phần tử. Hãy ánh xạ thành ResponseEntity.notFound() hoặc exception được xử lý thành 404.

**Trả Mono.just(null).** Reactive Streams không cho phép null. Dùng Mono.empty() hoặc Mono.justOrEmpty().

**Dùng collectList() cho tập dữ liệu không giới hạn.** Việc thu thập toàn bộ có thể tiêu tốn nhiều bộ nhớ. Giới hạn trang hoặc giữ Flux và xử lý theo batch.

**Nghĩ Flux luôn streaming qua HTTP.** application/json thường được encode thành JSON array; streaming phụ thuộc media type và codec. Chọn NDJSON/SSE khi cần stream.

**Dùng Page<T> đồng bộ trong reactive repository.** Dùng Flux cho content và Mono<Long> cho total, rồi kết hợp thành DTO trang.

**Nuốt lỗi bằng onErrorResume thành empty.** Client sẽ hiểu nhầm lỗi database thành không có dữ liệu. Chỉ chuyển đổi các lỗi đã xác định theo chính sách.

**Dùng next() mà không có sort.** Phần tử đầu tiên không ổn định nếu database không có ORDER BY. Sắp xếp rõ ràng trước khi lấy.

**Giữ transaction trong lúc client stream dữ liệu rất lâu.** Transaction dài có thể giữ connection và lock. Dùng batch/cursor hoặc tách quá trình export khỏi response trực tiếp.

## 16. Nguyên tắc thiết kế

- Chọn Mono cho một kết quả tùy chọn và Flux cho không hoặc nhiều kết quả.
- Dùng Mono<Void> khi chỉ cần tín hiệu hoàn tất/lỗi.
- Dùng Mono.empty() cho không có kết quả; không phát null.
- Phân biệt empty result với lỗi database.
- Ánh xạ empty sang 404, 204 hoặc một response khác theo hợp đồng endpoint.
- Dùng Flux cho danh sách và chọn media type phù hợp với JSON array hay streaming.
- Dùng Mono<List<T>> khi tập kết quả hữu hạn, có giới hạn và caller cần collection hoàn chỉnh.
- Không collect toàn bộ dữ liệu lớn hoặc luồng không giới hạn.
- Dùng pagination/keyset cho danh sách lớn; kết hợp Flux content và Mono count nếu cần metadata.
- Đặt sort rõ ràng trước khi dùng next()/first().
- Giữ reactive chain xuyên repository, service và controller; không subscribe/block tùy tiện.
- Xem xét cancellation, backpressure và thời gian giữ connection khi stream.
- Kiểm thử cả cardinality, empty/error và HTTP status bằng StepVerifier/WebTestClient.

## 17. Ghi nhớ

Mono và Flux không chỉ là kiểu trả về kỹ thuật. Chúng thể hiện cardinality trong hợp đồng của API: Mono cho 0 hoặc 1 kết quả; Flux cho 0 đến nhiều kết quả. Repository phản ánh số hàng mà truy vấn có thể trả, service có thể tổng hợp nhiều giá trị thành một kết quả, còn controller quyết định status, body và media type.

Mono.empty() không tự mang nghĩa 404, Flux không tự động có nghĩa HTTP streaming, và collectList() biến một luồng thành một collection cần được giữ trong bộ nhớ. Với Spring WebFlux, hãy chọn JSON array cho danh sách hữu hạn, NDJSON/SSE cho luồng cần truyền từng phần tử, dùng pagination cho tập lớn và xử lý cancellation/timeout theo đúng ranh giới transaction. Hợp đồng rõ ràng giúp client biết chính xác khi nào có một tài nguyên, một danh sách, một response rỗng hay một lỗi.

