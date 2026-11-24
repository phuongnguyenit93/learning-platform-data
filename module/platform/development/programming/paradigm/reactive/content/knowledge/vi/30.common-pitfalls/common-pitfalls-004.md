# Lỗi thường gặp

## Dùng map cho tác vụ trả về Publisher và tạo luồng lồng nhau

Trong Project Reactor, **map** biến đổi một phần tử thành một giá trị khác. Nếu hàm ánh xạ lại trả về **Mono** hoặc **Flux**, giá trị mới chính là Publisher đó. Reactor không tự đăng ký vào Publisher bên trong. Kết quả vì thế trở thành một luồng chứa Publisher, chẳng hạn **Mono<Mono<Profile>>** hoặc **Flux<Mono<Profile>>**, thay vì một luồng chứa **Profile**.

Đây là lỗi thường gặp khi gọi repository, HTTP client hoặc một service reactive bên trong map. Pipeline bên ngoài có thể hoàn tất bình thường trong khi các Publisher bên trong chưa được subscribe, chưa thực hiện I/O và chưa phát dữ liệu. Cách kết hợp đúng thường là **flatMap**, hoặc một toán tử khác thể hiện rõ yêu cầu tuần tự và thứ tự kết quả.

### 1. map giữ nguyên kiểu lồng nhau

Giả sử một service tra cứu hồ sơ theo ID và trả về **Mono<Profile>**:

~~~java
Mono<Profile> findProfile(String id) {
    return profileRepository.findById(id);
}
~~~

Nếu gọi phương thức này bên trong map:

~~~java
Mono<Mono<Profile>> nested =
    Mono.just("user-42")
        .map(this::findProfile);
~~~

Kiểu kết quả là **Mono<Mono<Profile>>**. Publisher bên ngoài phát ra một phần tử, và phần tử đó là một **Mono<Profile>**. map không mở Publisher bên trong để lấy **Profile**.

Với một nguồn nhiều phần tử, hình dạng tương tự là **Flux<Mono<Profile>>**:

~~~java
Flux<Mono<Profile>> nestedProfiles =
    Flux.just("user-1", "user-2", "user-3")
        .map(this::findProfile);
~~~

Mỗi phần tử của Flux là một Mono. Subscriber của Flux nhận các đối tượng Mono, không nhận các Profile mà những Mono đó có thể phát ra.

### 2. Vì sao Publisher bên trong không tự chạy?

Publisher mô tả một quá trình có thể được đăng ký và tiêu thụ. Với các nguồn cold phổ biến như **Mono.fromCallable**, **Mono.defer** hoặc repository reactive, công việc thường bắt đầu khi có subscription. Tạo một Publisher không đồng nghĩa với việc đã đăng ký vào nó.

~~~text
map:
  ID
  |
  v
findProfile(ID)
  |
  v
Mono<Profile>  --------------------+
                                  |
Outer Publisher phát Mono object |
                                  v
Subscriber nhận Mono<Profile>
                                  |
                                  X
                     Inner Mono chưa được subscribe
~~~

Khi outer Publisher phát một inner Publisher, Reactor coi inner Publisher là giá trị của phần tử. Subscriber có thể nhận nó, lưu nó hoặc tự subscribe sau đó. Nếu không có thành phần nào subscribe vào inner Publisher, công việc lazy mà nó mô tả sẽ không chạy.

Có một chi tiết cần phân biệt: phương thức được gọi bên trong mapper vẫn có thể thực hiện công việc eager trước khi trả về Publisher. Ví dụ, nó có thể tạo object, kiểm tra tham số hoặc vô tình gọi một API blocking. map không trì hoãn những side effect đã xảy ra trong lúc gọi phương thức. Nó chỉ không tự subscribe vào Publisher được trả về.

### 3. Dùng flatMap để làm phẳng một Mono

**flatMap** nhận một phần tử, gọi hàm tạo Publisher mới và nối tín hiệu từ Publisher đó vào luồng bên ngoài:

~~~java
import reactor.core.publisher.Mono;

Mono<Profile> profile =
    Mono.just("user-42")
        .flatMap(this::findProfile);
~~~

Kiểu kết quả là **Mono<Profile>**. Khi outer Mono phát ID, flatMap subscribe vào Mono được findProfile trả về. Các tín hiệu onNext, onError và onComplete của Publisher bên trong được kết hợp vào subscription đầu ra.

Với một hàm trả về Mono, đây thường là cách nối các bước I/O:

~~~java
Mono<OrderView> findOrderView(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer ->
                    new OrderView(order.id(), customer.name(), order.total())
                )
        );
}
~~~

Ở đây, flatMap được dùng khi cần tra cứu customer bất đồng bộ. Sau khi có customer, map tạo OrderView bằng phép biến đổi đồng bộ. Kiểu kết quả cuối vẫn là **Mono<OrderView>**, không phải **Mono<Mono<OrderView>>**.

### 4. Dùng flatMap để làm phẳng một Flux

Khi mỗi phần tử của Flux tạo ra một Publisher, flatMap nối các Publisher con thành một Flux duy nhất:

~~~java
import reactor.core.publisher.Flux;

Flux<Profile> profiles =
    Flux.just("user-1", "user-2", "user-3")
        .flatMap(this::findProfile);
~~~

Mỗi ID được chuyển thành một Publisher tra cứu. flatMap đăng ký các Publisher con và chuyển các Profile mà chúng phát ra vào Flux kết quả.

Nếu mỗi lần tra cứu có thể hoàn tất rỗng, ID tương ứng không tạo phần tử Profile trong luồng kết quả. Nếu một Publisher con phát lỗi, lỗi được truyền xuống và kết thúc luồng theo ngữ nghĩa lỗi của Reactor, trừ khi có toán tử phục hồi được đặt ở vị trí phù hợp.

### 5. Chọn giữa flatMap, concatMap và flatMapSequential

Ba toán tử đều làm phẳng Publisher con, nhưng có chính sách concurrency và thứ tự khác nhau:

| Toán tử | Cách đăng ký Publisher con | Thứ tự phần tử đầu ra | Khi phù hợp |
| --- | --- | --- | --- |
| **flatMap** | Có thể chạy nhiều nhánh đồng thời | Theo thời điểm nhánh phát tín hiệu; không bảo đảm thứ tự nguồn | Các tác vụ độc lập, ưu tiên thông lượng |
| **concatMap** | Đăng ký và chờ từng nhánh hoàn tất rồi mới chuyển sang nhánh tiếp | Giữ thứ tự nguồn | Tác vụ cần tuần tự hoặc phụ thuộc thứ tự |
| **flatMapSequential** | Có thể đăng ký nhiều nhánh đồng thời | Phát kết quả theo thứ tự nguồn; có thể phải đệm nhánh hoàn tất sớm | Cần concurrency nhưng vẫn giữ thứ tự |

Ví dụ, tra cứu hồ sơ độc lập có thể dùng flatMap:

~~~java
Flux<Profile> profiles =
    Flux.fromIterable(userIds)
        .flatMap(this::findProfile, 8);
~~~

Tham số 8 giới hạn số Publisher con được đăng ký đồng thời trong subscription này. Kết quả có thể đến theo thứ tự khác với userIds vì mỗi yêu cầu có thời gian phản hồi riêng.

Nếu thứ tự là một phần của hợp đồng:

~~~java
Flux<Profile> orderedProfiles =
    Flux.fromIterable(userIds)
        .concatMap(this::findProfile);
~~~

concatMap chỉ chuyển sang ID tiếp theo sau khi Publisher con hiện tại kết thúc. Điều này dễ dự đoán thứ tự nhưng giảm mức concurrency.

Nếu muốn chạy đồng thời nhưng phát theo thứ tự đầu vào:

~~~java
Flux<Profile> orderedConcurrentProfiles =
    Flux.fromIterable(userIds)
        .flatMapSequential(this::findProfile, 8);
~~~

Các nhánh có thể hoàn tất không theo thứ tự, nhưng kết quả được giữ lại khi cần để phát theo thứ tự nguồn. Vì vậy, một nhánh chậm ở đầu có thể khiến kết quả từ nhánh sau phải chờ trong buffer.

### 6. Không dùng flatMap nếu thứ tự nghiệp vụ quan trọng

Ví dụ xử lý các bước cập nhật trạng thái theo thứ tự sự kiện:

~~~java
Flux<UpdateResult> results =
    Flux.fromIterable(events)
        .flatMap(event -> orderService.apply(event));
~~~

Nếu các cập nhật cùng tác động đến một đơn hàng, các Publisher con có thể chạy đồng thời và hoàn tất theo thứ tự khác đầu vào. Điều này có thể làm trạng thái cuối cùng không đúng với thứ tự sự kiện nghiệp vụ.

Khi mỗi sự kiện cần được áp dụng tuần tự:

~~~java
Flux<UpdateResult> results =
    Flux.fromIterable(events)
        .concatMap(orderService::apply);
~~~

Nếu các sự kiện thuộc nhiều đơn hàng độc lập, có thể phân nhóm theo khóa rồi xử lý tuần tự trong từng nhóm và song song giữa các nhóm. Cần chọn toán tử và cấu trúc phân vùng theo yêu cầu nhất quán cụ thể; không dùng flatMap chỉ vì nó thường cho thông lượng cao hơn.

### 7. Đặt concurrency có chủ đích

flatMap có các overload cho phép giới hạn số nhánh con đồng thời và prefetch. Giới hạn concurrency có ý nghĩa khi Publisher con gọi database, HTTP client hoặc một tài nguyên có dung lượng hữu hạn:

~~~java
Flux<EnrichedOrder> enriched =
    Flux.fromIterable(orderIds)
        .flatMap(
            id -> orderService.findById(id)
                .flatMap(this::enrichOrder),
            6
        );
~~~

Ở đây tối đa sáu nhánh được đăng ký đồng thời trong một subscription. Concurrency không phải giới hạn toàn ứng dụng: nhiều request HTTP có thể tạo nhiều subscription riêng. Nếu cần giới hạn tải toàn cục, cần thêm giới hạn ở pool, bulkhead hoặc admission control.

Không nên tăng concurrency mà không quan sát hệ thống phụ thuộc. Nhiều yêu cầu đồng thời hơn có thể tăng thông lượng khi database còn dư tài nguyên, nhưng cũng có thể làm tăng hàng đợi, lock contention và timeout.

### 8. Khi chỉ cần đợi một tác vụ hoàn tất: dùng then

Không phải Publisher con nào cũng phát giá trị cần giữ lại. Nếu một bước trả về **Mono<Void>** và chỉ cần chờ nó hoàn tất trước khi chạy bước tiếp theo, then thể hiện ý định rõ ràng:

~~~java
Mono<Order> saveAndNotify(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            notificationService.sendCreated(saved)
                .thenReturn(saved)
        );
}
~~~

sendCreated trả về Mono<Void>. thenReturn(saved) đợi notification hoàn tất rồi phát lại Order đã lưu. Nếu notification lỗi, lỗi truyền xuống và Order không được phát như kết quả thành công của pipeline này.

Nếu cần bỏ qua giá trị của Publisher trước và chỉ quan tâm completion rồi chạy một Mono khác, dùng then:

~~~java
Mono<Receipt> receipt =
    auditRepository.write(order)
        .then(receiptService.create(order));
~~~

then không giữ phần tử mà Publisher trước phát ra. Nó chỉ subscribe Publisher tiếp theo sau khi Publisher trước hoàn tất thành công.

### 9. Dùng thenMany khi bước tiếp theo là Flux

Nếu tác vụ đầu tiên chỉ cần hoàn tất rồi mới bắt đầu một luồng nhiều phần tử, dùng thenMany:

~~~java
Flux<InventoryItem> inventory =
    inventoryService.refreshIndex()
        .thenMany(inventoryRepository.findAll());
~~~

refreshIndex() hoàn tất trước khi findAll() được subscribe. Nếu refresh phát lỗi, luồng đọc inventory không bắt đầu và lỗi được truyền xuống.

Không dùng map để trả về Flux trong tình huống này. thenMany diễn đạt trực tiếp rằng giá trị trước không quan trọng; chỉ cần chờ completion rồi chuyển sang Publisher nhiều phần tử.

### 10. Kết hợp nhiều Publisher độc lập bằng zip hoặc when

Khi cần kết hợp giá trị từ nhiều nguồn độc lập, không nên lồng Publisher bằng map:

~~~java
Mono<Mono<Tuple2<Customer, Address>>> customerAndAddress =
    customerRepository.findById(customerId)
        .map(customer ->
            addressRepository.findPrimaryByCustomerId(customer.id())
                .map(address -> Tuples.of(customer, address))
        );
~~~

Đoạn trên tạo **Mono<Mono<Tuple2<Customer, Address>>>**. Có thể dùng flatMap để nối bước phụ thuộc:

~~~java
Mono<CustomerProfile> customerProfile =
    customerRepository.findById(customerId)
        .flatMap(customer ->
            addressRepository.findPrimaryByCustomerId(customer.id())
                .map(address ->
                    new CustomerProfile(customer, address)
                )
        );
~~~

Nếu hai truy vấn độc lập và cần chạy cùng nhau, Mono.zip thể hiện rõ việc kết hợp:

~~~java
Mono<CustomerProfile> customerProfile =
    Mono.zip(
        customerRepository.findById(customerId),
        preferenceRepository.findByCustomerId(customerId)
    )
    .map(tuple ->
        new CustomerProfile(tuple.getT1(), tuple.getT2())
    );
~~~

zip ghép các giá trị phát ra từ các nguồn. Nếu một nguồn hoàn tất rỗng, kết quả zip có thể hoàn tất rỗng vì không đủ giá trị để tạo tuple. Nếu các Publisher chỉ biểu diễn completion như Mono<Void>, dùng Mono.when(...) thay vì zip:

~~~java
Mono<Void> completed =
    Mono.when(
        auditRepository.write(event),
        metricsRepository.record(event)
    );
~~~

### 11. Lỗi và cancellation trong Publisher đã được làm phẳng

Khi dùng flatMap, inner Publisher trở thành một phần của pipeline. Vì vậy:

- Lỗi từ inner Publisher được truyền vào luồng lỗi downstream.
- Cancellation từ downstream được truyền đến các nhánh con đang hoạt động theo khả năng của nguồn.
- Completion của nhánh con góp phần quyết định khi nào outer Flux hoàn tất.
- Backpressure và concurrency được quản lý qua toán tử kết hợp.

~~~java
Mono<Profile> profile =
    Mono.just(userId)
        .flatMap(this::findProfile)
        .onErrorResume(ProfileUnavailableException.class,
            error -> cachedProfile(userId)
        );
~~~

onErrorResume được đặt sau flatMap, nên có thể quan sát lỗi từ thao tác tra cứu bên trong. Nếu giữ cấu trúc **Mono<Mono<Profile>>**, lỗi của inner Mono chỉ xuất hiện khi một thành phần khác subscribe vào inner đó; toán tử xử lý lỗi trên outer Mono không tự nhận lỗi từ Publisher chưa được subscribe.

### 12. Tránh subscribe lồng bên trong map

Một cách sửa sai khác là gọi subscribe() ngay trong map:

~~~java
// Không nên: tạo một subscription tách rời.
Mono<String> result =
    Mono.just(userId)
        .map(id -> {
            profileService.findProfile(id)
                .subscribe(this::sendWelcomeMessage);
            return id;
        });
~~~

Subscription bên trong không được kết nối với vòng đời của Publisher bên ngoài. Outer Mono có thể hoàn tất trước khi tra cứu và gửi thông báo xong. Lỗi của inner subscription cũng không đi theo kênh lỗi mà caller của result đang quản lý. Cancellation từ caller không nhất thiết hủy được công việc tách rời đó.

Hãy nối công việc vào cùng pipeline:

~~~java
Mono<String> result =
    Mono.just(userId)
        .flatMap(id ->
            profileService.findProfile(id)
                .flatMap(profile ->
                    notificationService.sendWelcome(profile)
                        .thenReturn(id)
                )
        );
~~~

Caller nhận một Publisher đại diện cho toàn bộ chuỗi công việc. Khi subscribe, pipeline thực hiện tra cứu rồi gửi thông báo; lỗi và completion được kết hợp; cancellation có thể lan đến các bước còn hoạt động.

### 13. Dùng map cho phép biến đổi đồng bộ

map vẫn là toán tử đúng khi hàm trả về một giá trị thông thường, không phải Publisher:

~~~java
Mono<OrderView> view =
    orderRepository.findById(orderId)
        .map(order ->
            new OrderView(
                order.id(),
                order.status(),
                order.total()
            )
        );
~~~

Phép tạo OrderView đồng bộ và không tạo thêm luồng bất đồng bộ, nên map là phù hợp. Dùng flatMap trong trường hợp này sẽ tạo thêm Publisher không cần thiết và làm ý định khó đọc hơn.

Một hàm được dùng với map cũng không được trả null. Reactive Streams không cho phép phát null như một phần tử. Nếu hàm có thể trả null từ API cũ, hãy chuyển giá trị nullable thành kiểu reactive phù hợp bằng Mono.justOrEmpty hoặc xử lý null trước khi phát.

### 14. Kiểm thử để phát hiện luồng lồng nhau

Kiểu khai báo của biến thường đã cho thấy vấn đề:

~~~java
Flux<Mono<Profile>> nested =
    Flux.fromIterable(userIds)
        .map(this::findProfile);
~~~

Nếu mục tiêu là phát Profile, kiểu cần có là **Flux<Profile>**:

~~~java
Flux<Profile> flattened =
    Flux.fromIterable(userIds)
        .flatMap(this::findProfile);
~~~

Có thể dùng StepVerifier để xác minh phần tử thực sự được phát:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(
        Flux.just("user-1", "user-2")
            .flatMap(this::findProfile)
    )
    .expectNextCount(2)
    .verifyComplete();
~~~

Nếu thứ tự là một phần hợp đồng, hãy dùng concatMap hoặc flatMapSequential và kiểm tra thứ tự cụ thể:

~~~java
StepVerifier.create(
        Flux.just("user-1", "user-2")
            .concatMap(this::findProfile)
    )
    .expectNextMatches(profile -> profile.id().equals("user-1"))
    .expectNextMatches(profile -> profile.id().equals("user-2"))
    .verifyComplete();
~~~

### 15. Chứng minh inner Publisher chưa được subscribe

Một test nhỏ có thể làm rõ sự khác nhau giữa map và flatMap. Dùng Mono.fromCallable để theo dõi thời điểm công việc bên trong thực sự chạy:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import static org.junit.jupiter.api.Assertions.assertEquals;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

AtomicInteger executions = new AtomicInteger();

Function<Integer, Mono<Integer>> loadValue =
    id -> Mono.fromCallable(() -> executions.incrementAndGet() + id);

Flux<Mono<Integer>> nested =
    Flux.just(1, 2)
        .map(loadValue);

StepVerifier.create(nested)
    .expectNextCount(2)
    .verifyComplete();

assertEquals(0, executions.get());
~~~

Outer Flux phát hai Mono, nhưng callable chưa chạy vì không có ai subscribe vào chúng. Khi thay map bằng flatMap, các inner Mono được đăng ký và callable thực thi:

~~~java
Flux<Integer> flattened =
    Flux.just(1, 2)
        .flatMap(loadValue);

StepVerifier.create(flattened)
    .expectNextCount(2)
    .verifyComplete();

assertEquals(2, executions.get());
~~~

Trong test hoàn chỉnh, đặt hai trường hợp trong các test riêng hoặc tạo lại AtomicInteger cho từng test. Cần import static assertEquals từ JUnit Jupiter. Ví dụ dùng bộ đếm để minh họa subscription; không nên đưa biến đếm mutable như vậy vào logic production.

### 16. Các lỗi thường gặp và cách sửa

| Cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| map với hàm trả về Mono | Tạo Mono lồng nhau | Dùng flatMap |
| map với hàm trả về Publisher trong Flux | Tạo Flux chứa Publisher | Dùng flatMap hoặc biến thể theo thứ tự |
| subscribe() trong map | Tạo subscription tách rời, khó quản lý lỗi và cancellation | Trả Publisher và nối bằng flatMap |
| flatMap cho cập nhật cần tuần tự | Nhánh có thể chạy đồng thời và đổi thứ tự hoàn tất | Dùng concatMap |
| Cần concurrency nhưng giữ thứ tự | flatMap không bảo đảm thứ tự nguồn | Dùng flatMapSequential |
| Dùng zip cho các Mono<Void> | Không có giá trị để tạo tuple | Dùng Mono.when |
| Dùng map cho hàm có thể trả null | Có thể gây lỗi vì Publisher không phát null | Dùng Mono.justOrEmpty hoặc biểu diễn kết quả rõ ràng |

### 17. Quy trình chọn toán tử

Trước khi thêm một bước vào pipeline, hãy xác định hàm của bước đó trả về gì:

1. Nếu trả về một giá trị đồng bộ, dùng map.
2. Nếu trả về Mono hoặc Publisher và cần nối kết quả vào luồng, dùng flatMap hoặc biến thể phù hợp.
3. Nếu phải chạy từng tác vụ con tuần tự, dùng concatMap.
4. Nếu muốn chạy đồng thời nhưng phát theo thứ tự nguồn, dùng flatMapSequential.
5. Nếu chỉ cần chờ một tác vụ hoàn tất rồi tiếp tục, dùng then hoặc thenMany.
6. Nếu cần kết hợp giá trị từ nhiều nguồn độc lập, dùng zip.
7. Nếu nhiều tác vụ chỉ cần hoàn tất, dùng Mono.when.
8. Kiểm tra concurrency, thứ tự, lỗi và cancellation có đúng hợp đồng nghiệp vụ không.

Trong module REACTIVE_PROGRAMMING, tránh luồng lồng nhau bằng cách chọn toán tử theo kiểu kết quả của từng bước. map biến đổi giá trị đồng bộ; flatMap nối Publisher bất đồng bộ; concatMap và flatMapSequential bổ sung chính sách thứ tự; then, thenMany, zip và when diễn đạt các kiểu phối hợp khác. Khi toàn bộ công việc nằm trong một pipeline, subscriber có thể quản lý đúng dữ liệu, lỗi, backpressure và cancellation từ đầu đến cuối.
