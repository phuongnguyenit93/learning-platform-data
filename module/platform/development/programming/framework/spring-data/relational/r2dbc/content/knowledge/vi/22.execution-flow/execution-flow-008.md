# Ảnh hưởng của cache, share và đăng ký nhiều lần đến truy vấn

## 1. Publisher reactive không đồng nghĩa với một lần truy vấn

Trong Spring Data R2DBC, repository method thường trả về `Mono<T>` hoặc `Flux<T>`. Các kiểu này mô tả một luồng dữ liệu sẽ được thực thi khi có subscription. Một lời gọi repository tạo publisher; mỗi lần publisher nguồn được subscribe có thể tạo một lần thực thi SQL mới.

Ví dụ:

~~~java
Mono<Customer> customerQuery = customerRepository.findById(42L);
~~~

Dòng lệnh trên tạo publisher mô tả truy vấn tìm khách hàng có ID 42. Nếu publisher này được subscribe hai lần, repository thường thực hiện truy vấn hai lần:

~~~java
StepVerifier.create(customerQuery)
        .expectNextCount(1)
        .verifyComplete();

StepVerifier.create(customerQuery)
        .expectNextCount(1)
        .verifyComplete();
~~~

Hai subscription độc lập có thể lấy dữ liệu ở hai thời điểm khác nhau, dùng hai lần lấy connection khác nhau và quan sát hai trạng thái database khác nhau.

Đây là hành vi bình thường của publisher cold mà Spring Data R2DBC trả về. Cold publisher bắt đầu công việc cho mỗi subscriber. Nó giúp mỗi lần tiêu thụ có một lần thực thi riêng, nhưng cũng có nghĩa một publisher được dùng ở nhiều nhánh pipeline có thể vô tình phát sinh nhiều câu SQL.

Ba cơ chế thường được nhắc đến khi cần kiểm soát điều này là:

- **Đăng ký nhiều lần (multiple subscriptions):** mỗi subscriber có thể kích hoạt lại nguồn dữ liệu.
- **cache():** chia sẻ một lần subscribe nguồn và lưu tín hiệu/kết quả để phát lại cho subscriber sau.
- **share():** chia sẻ một subscription nguồn cho các subscriber cùng tham gia, theo semantics multicast của Reactor.

Hiểu đúng sự khác nhau giúp tránh truy vấn lặp, dữ liệu cũ, tiêu thụ bộ nhớ quá mức và lỗi transaction khi dùng R2DBC.

## 2. Cold publisher và vòng đời truy vấn R2DBC

Một truy vấn repository thường là cold publisher. Khi được subscribe, publisher bắt đầu tương tác với database:

~~~text
Repository method được gọi
          |
          v
    Mono / Flux được tạo
          |
          v
       subscribe()
          |
          v
 Lấy connection từ ConnectionFactory
          |
          v
 Gửi SQL qua R2DBC driver
          |
          v
 Nhận và ánh xạ kết quả
          |
          v
 Complete / Error / Cancel
          |
          v
 Trả connection về pool
~~~

Với `Mono<Customer>`, một subscription có thể phát tối đa một Customer hoặc hoàn tất rỗng. Với `Flux<Customer>`, một subscription có thể phát nhiều hàng.

Khi subscriber tiêu thụ một Flux từ database, connection có thể được giữ trong thời gian stream còn đọc kết quả. Connection thường được giải phóng khi publisher hoàn tất, phát lỗi hoặc bị hủy theo lifecycle của driver/framework.

Nếu cùng một Flux được subscribe nhiều lần, mỗi subscription có thể thực hiện lại SQL và sử dụng một connection riêng. Với pool có giới hạn, việc vô tình tạo nhiều subscription đồng thời có thể làm tăng số connection đang được mượn và gây chờ pool.

Không nên giả định một publisher repository tự động lưu kết quả chỉ vì nó đã được gán vào một biến. Việc lưu biến chỉ giữ tham chiếu đến publisher; nó không biến nguồn cold thành cache.

## 3. Đăng ký nhiều lần có thể làm truy vấn chạy nhiều lần

### 3.1. Subscribe hai lần

~~~java
Mono<Customer> query = customerRepository.findById(42L);

query.subscribe(customer -> log.info("First: {}", customer));
query.subscribe(customer -> log.info("Second: {}", customer));
~~~

Hai lệnh `subscribe()` tạo hai subscription. Với publisher repository cold, mỗi subscription có thể thực thi một câu SELECT riêng.

Ngoài việc truy vấn database hai lần, code trên còn tự tạo hai luồng xử lý độc lập. Lỗi được gửi tới hai subscriber riêng và không được trả về caller dưới dạng một publisher duy nhất. Trong service WebFlux, không nên tự subscribe để xử lý kết quả; hãy trả publisher hoặc nối các bước bằng Reactor operator.

### 3.2. Cùng một publisher được dùng ở hai nhánh

Một lỗi khó nhận ra hơn là dùng cùng publisher trong nhiều nhánh:

~~~java
Mono<Customer> customer = customerRepository.findById(customerId);

return Mono.zip(
        customer.map(Customer::name),
        customer.map(Customer::email)
);
~~~

`Mono.zip` subscribe vào từng nguồn thành phần. Hai nhánh ở đây cùng tham chiếu một publisher cold, nên truy vấn có thể được thực thi hai lần.

Nếu mục đích là lấy một Customer rồi tạo cả name và email từ cùng một kết quả, hãy đọc một lần và biến đổi object:

~~~java
return customerRepository.findById(customerId)
        .map(found -> new CustomerContact(
                found.name(),
                found.email()
        ));
~~~

Nếu thực sự cần nhiều nhánh downstream cùng tiêu thụ một kết quả, có thể tạo một publisher đã được cache trong phạm vi thích hợp:

~~~java
Mono<Customer> sharedCustomer =
        customerRepository.findById(customerId).cache();

return Mono.zip(
        sharedCustomer.map(Customer::name),
        sharedCustomer.map(Customer::email)
);
~~~

Với cách này, các nhánh cùng subscribe vào publisher cache; nguồn repository được subscribe một lần và tín hiệu được phát lại. Tuy nhiên, chỉ dùng cache khi việc tái sử dụng cùng một kết quả là đúng về nghiệp vụ và phạm vi sống của publisher được kiểm soát.

### 3.3. Những thao tác thường tạo subscription mới

Các trường hợp có thể kích hoạt subscription gồm:

- Gọi `subscribe()` nhiều lần.
- Gọi `block()` nhiều lần trên cùng publisher.
- Trả cùng publisher cho nhiều caller độc lập.
- Dùng một publisher cold ở nhiều nhánh như `zip`.
- Dùng `retry` hoặc `repeat` khiến upstream được subscribe lại.
- Framework hoặc adapter tiêu thụ publisher ở nhiều lifecycle khác nhau.
- Test gọi cùng publisher trong nhiều StepVerifier.

Cần đọc pipeline để xác định chính xác subscription nào chạm tới nguồn database. Không phải mọi operator đều tạo subscription riêng; operator thông thường thường nối vào cùng một subscription. Nhưng các operator kết hợp nhiều publisher hoặc cơ chế resubscribe có thể kích hoạt nguồn nhiều lần.

## 4. cache() biến nguồn thành publisher có replay

Reactor cung cấp operator `cache()` cho Mono và Flux. Sau subscription đầu tiên, cache giữ tín hiệu từ nguồn và phát lại cho subscriber sau theo chính sách cache đã chọn.

Với Mono:

~~~java
Mono<Customer> cachedCustomer =
        customerRepository.findById(42L).cache();
~~~

Khi subscriber đầu tiên subscribe, nguồn repository được thực thi. Kết quả hoặc tín hiệu terminal được cache. Những subscriber sau nhận lại tín hiệu đã lưu mà không cần chạy lại truy vấn nguồn trong vòng đời của cache đó.

~~~text
                    Subscriber A
                         |
                         v
                +----------------+
                |  Mono.cache()  |
                +----------------+
                         |
                 subscribe nguồn
                         |
                         v
                Repository SELECT
                         |
                         v
                  Customer / Empty
                         |
                 Lưu tín hiệu cache
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Subscriber B            Subscriber C
       nhận tín hiệu            nhận tín hiệu
       đã cache                 đã cache
~~~

Điểm khác biệt quan trọng: cache lưu **tín hiệu reactive**, không chỉ lưu giá trị thành công. Với Mono, tín hiệu được cache có thể là:

- Một giá trị onNext rồi complete.
- Complete rỗng, tức không tìm thấy kết quả.
- Error signal.

Vì vậy, lỗi hoặc kết quả rỗng cũng có thể được phát lại cho subscriber sau. Không nên giả định cache chỉ giữ kết quả thành công.

### 4.1. cache() không tự biết dữ liệu đã thay đổi

~~~java
Mono<Customer> customer = customerRepository.findById(id).cache();
~~~

Sau khi nguồn phát Customer, các subscriber sau nhận cùng object/kết quả đã cache. Nếu một thao tác khác cập nhật bản ghi, publisher cache không tự truy vấn lại để lấy dữ liệu mới.

Cache không tự đồng bộ với database, không theo dõi UPDATE/DELETE và không tự vô hiệu hóa khi repository lưu entity khác. Nếu cần dữ liệu mới, phải tạo publisher mới hoặc có chính sách invalidation/TTL rõ ràng.

### 4.2. Cache gắn với instance publisher

`cache()` không phải cache phân tán hoặc cache ứng dụng tự động. Nó gắn với instance publisher được tạo và giữ tham chiếu.

Ví dụ:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id).cache();
}
~~~

Mỗi lần gọi method này tạo một publisher cache mới. Nếu hai request gọi method riêng, chúng thường nhận hai instance cache khác nhau và có thể chạy hai truy vấn riêng.

Ngược lại, nếu lưu một cached publisher trong field singleton, cache có thể sống suốt vòng đời bean và giữ dữ liệu cũ rất lâu. Không nên dùng một field cache không giới hạn cho dữ liệu phụ thuộc ID, tenant hoặc user nếu không có keying, eviction và invalidation phù hợp.

## 5. Cache có TTL và giới hạn lịch sử

Cache vô thời hạn có thể phù hợp cho một kết quả bất biến trong một phạm vi rất ngắn, nhưng thường không phù hợp với dữ liệu database có thể thay đổi.

Reactor hỗ trợ cache với TTL:

~~~java
Mono<Customer> cachedCustomer =
        customerRepository.findById(id)
                .cache(Duration.ofSeconds(30));
~~~

Sau khoảng thời gian TTL, tín hiệu cache có thể hết hạn và lần subscription tiếp theo sẽ kích hoạt nguồn theo semantics của operator. TTL giúp giới hạn độ cũ tối đa theo thời gian, nhưng không bảo đảm dữ liệu được cập nhật ngay khi database thay đổi.

Với Flux, có thể cache lịch sử hữu hạn:

~~~java
Flux<CustomerSummary> cachedSummaries =
        customerRepository.findAll()
                .map(CustomerSummary::from)
                .cache(100);
~~~

Cache history hữu hạn giới hạn số phần tử được giữ để replay. Cần đọc đúng semantics của Reactor version đang dùng và xác định có thực sự cần replay một stream dài hay không.

### 5.1. Cache toàn bộ Flux có thể giữ rất nhiều dữ liệu

~~~java
Flux<Customer> allCustomers =
        customerRepository.findAll().cache();
~~~

Nếu bảng có hàng triệu bản ghi, cache không giới hạn có thể giữ toàn bộ kết quả trong heap. Điều này tạo áp lực memory lớn, tăng thời gian GC và có thể gây OutOfMemoryError.

Không dùng cache toàn bộ một truy vấn lớn chỉ để tránh chạy SQL lần thứ hai. Hãy cân nhắc pagination, giới hạn lịch sử, cache DTO nhỏ, TTL hoặc một cache chuyên dụng có eviction theo key và dung lượng.

### 5.2. TTL không phải cơ chế invalidation nghiệp vụ

Giả sử cache có TTL 30 giây. Một request cập nhật Customer ngay sau khi cache được tạo. Các subscriber tiếp theo trong 30 giây vẫn có thể nhận dữ liệu cũ.

Nếu cần invalidation ngay sau write, phải thiết kế rõ cơ chế xóa/thay cache khi cập nhật, hoặc dùng một cache abstraction có key và eviction phù hợp. Chỉ đặt TTL là một chính sách chấp nhận stale data trong một khoảng thời gian.

## 6. cache() ảnh hưởng đến cả lỗi và kết quả rỗng

Với Mono, cache giữ tín hiệu terminal. Ví dụ:

~~~java
Mono<Customer> cached =
        customerRepository.findById(id).cache();
~~~

Nếu ID không tồn tại, nguồn có thể hoàn tất rỗng. Cache giữ tín hiệu empty, nên subscriber sau cũng nhận empty thay vì chạy lại SELECT.

Nếu lần đầu truy vấn gặp lỗi kết nối, error signal có thể được cache. Subscriber sau nhận lại cùng lỗi đã cache và không nhất thiết tạo lần thử database mới.

Điều này có thể không mong muốn với lỗi tạm thời. Nếu muốn retry nguồn trước rồi cache kết quả cuối, hãy đặt operator theo đúng thứ tự:

~~~java
Mono<Customer> result =
        customerRepository.findById(id)
                .retryWhen(retryPolicy)
                .cache(Duration.ofSeconds(20));
~~~

Nguồn được retry theo policy; kết quả terminal sau retry mới được cache.

Ngược lại:

~~~java
Mono<Customer> result =
        customerRepository.findById(id)
                .cache()
                .retryWhen(retryPolicy);
~~~

Nếu cache đã lưu error, retry downstream có thể chỉ subscribe lại cache và nhận cùng error, thay vì thực thi lại repository query. Vì vậy, vị trí của `cache()` so với `retryWhen()` làm thay đổi hành vi.

Không cache lỗi vô thời hạn nếu mục tiêu là tự phục hồi khi database trở lại hoạt động. Hãy chọn retry, TTL và invalidation theo loại lỗi và semantics dữ liệu.

## 7. share() chia sẻ một subscription nguồn giữa các subscriber

`share()` là toán tử multicast. Với Flux, nó cho phép nhiều subscriber cùng nhận các phần tử được phát ra từ một subscription nguồn trong thời gian họ cùng tham gia.

Ví dụ:

~~~java
Flux<Customer> sharedCustomers =
        customerRepository.findAll().share();

Flux<String> names =
        sharedCustomers.map(Customer::name);

Flux<String> emails =
        sharedCustomers.map(Customer::email);

return Flux.merge(names, emails);
~~~

Khi hai nhánh subscribe gần nhau vào cùng shared Flux, chúng có thể dùng chung một lần subscribe nguồn thay vì mỗi nhánh chạy một query riêng.

Điều này hữu ích khi nhiều consumer cần quan sát cùng một luồng đang phát. Tuy nhiên, share không có cùng semantics với cache.

### 7.1. share không replay lịch sử như cache

Với Flux share, subscriber tham gia sau khi một số phần tử đã phát sẽ không nhận lại các phần tử trước đó. Subscriber nhận những phần tử được phát trong khoảng thời gian nó tham gia, cùng terminal signal theo semantics của source/operator.

Ví dụ nguồn lần lượt phát A, B, C:

~~~text
Thời gian  -------------------------------------->

Nguồn       A -------- B -------- C -------- complete

Subscriber 1  subscribe ------------------------>
Nhận         A -------- B -------- C

Subscriber 2             subscribe ------------>
Nhận                    B -------- C

Subscriber 3                         subscribe ->
Nhận                                C
~~~

Đây là mô hình live multicast. Nếu subscriber cần nhận lại toàn bộ kết quả từ đầu, share không phải lựa chọn phù hợp; cần replay/cache hoặc một truy vấn mới.

Với publisher hữu hạn từ database, subscriber đến muộn có thể bỏ lỡ những hàng đã phát. Không dùng share như một cách cache kết quả truy vấn.

### 7.2. share không phải cache bền vững

`share()` không tạo cache key, không có TTL nghiệp vụ, không có eviction theo entity và không tồn tại qua process restart. Nó không thay thế Redis, Caffeine hoặc một cache ứng dụng có quản lý.

Nó cũng không phải cơ chế deduplication toàn hệ thống. Hai instance ứng dụng có hai publisher share riêng vẫn có thể chạy hai truy vấn độc lập.

### 7.3. Subscriber cancellation ảnh hưởng nguồn

Với semantics multicast/refCount, nguồn được kết nối khi subscriber đầu tiên tham gia. Khi các subscriber rời đi, kết nối nguồn có thể bị hủy theo quy tắc của operator. Nếu một subscriber vẫn còn, nguồn thường tiếp tục phục vụ subscriber đó.

Với truy vấn R2DBC dạng Flux, việc cancel upstream có thể kết thúc việc đọc result set và giải phóng connection sớm. Hành vi cụ thể phụ thuộc Reactor version và driver. Cần kiểm thử khi stream dài hoặc subscriber có thể hủy.

Không dùng share để che giấu việc subscriber không tiêu thụ dữ liệu. Một subscriber chậm hoặc không hủy có thể kéo dài vòng đời của nguồn và giữ connection lâu hơn mong đợi.

## 8. So sánh cache(), share() và publisher cold

| Đặc điểm | Cold repository publisher | cache() | share() |
|---|---|---|---|
| Subscription nguồn | Mỗi subscription có thể chạy lại query | Thường chỉ một lần cho cache instance | Chia sẻ subscription nguồn cho nhóm subscriber đang kết nối |
| Phát lại dữ liệu cũ | Không | Có, theo cache history/TTL | Không replay lịch sử Flux |
| Subscriber đến muộn | Bắt đầu query mới | Nhận tín hiệu/kết quả đã cache | Chỉ nhận phần phát sau khi tham gia |
| Dữ liệu mới từ DB | Query mới có thể thấy dữ liệu mới | Có thể stale cho đến khi hết hạn/invalidate | Subscriber mới sau khi nguồn reset có thể dẫn tới subscription mới theo semantics operator |
| Bộ nhớ | Không giữ toàn bộ kết quả chỉ vì publisher được tạo | Có thể giữ tín hiệu và nhiều phần tử | Không giữ replay history như cache |
| Mục đích chính | Mỗi lần tiêu thụ thực thi độc lập | Reuse và replay kết quả | Multicast luồng đang phát |
| Rủi ro chính | Truy vấn lặp, connection tăng | Stale data, memory retention, cache error/empty | Subscriber bỏ lỡ dữ liệu, lifecycle/cancellation phức tạp |

Chọn operator theo câu hỏi nghiệp vụ:

- Mỗi request cần dữ liệu mới? Dùng publisher cold và để mỗi request thực hiện query.
- Nhiều nhánh trong cùng một tác vụ cần cùng kết quả đã đọc? Có thể cache trong phạm vi publisher ngắn.
- Nhiều subscriber đồng thời cần quan sát cùng một luồng đang phát? Cân nhắc share.
- Cần cache theo ID, tenant, TTL, invalidation và giới hạn bộ nhớ? Dùng cache abstraction phù hợp thay vì một publisher cache không quản lý.

## 9. Nhiều subscription và transaction reactive

Đây là điểm đặc biệt quan trọng với Spring Data R2DBC. Reactive transaction được gắn với subscription và Reactor Context. Một phương thức transactional trả publisher; khi publisher được subscribe qua proxy, transaction manager mở transaction cho subscription đó.

Nếu một cold publisher được subscribe hai lần, hai lần thực thi có thể chạy trong hai transaction khác nhau nếu mỗi lần được bao bởi transaction boundary tương ứng.

Ví dụ:

~~~java
@Transactional
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Nếu caller gọi phương thức qua Spring proxy hai lần và subscribe cả hai publisher, mỗi lời gọi có thể có transaction lifecycle riêng theo cấu hình propagation và transaction manager.

### 9.1. Không cache dữ liệu gắn với transaction rồi tái sử dụng ở transaction khác

Giả sử một publisher được cache và tái sử dụng qua nhiều request:

~~~java
Mono<Account> cachedAccount =
        transactionalService.loadAccount(accountId).cache();
~~~

Lần đầu subscribe có thể thực hiện truy vấn trong transaction/context đầu tiên. Subscriber sau có thể nhận kết quả đã cache mà không chạy truy vấn trong transaction mới của chính nó. Kết quả có thể không phản ánh trạng thái mới và không còn được đọc dưới isolation/security context của subscriber sau.

Với dữ liệu phụ thuộc tenant, user, quyền truy cập hoặc transaction snapshot, đây là rủi ro nghiêm trọng. Không chia sẻ một publisher cache toàn cục giữa những caller có context khác nhau.

Nếu cần cache dữ liệu ứng dụng, hãy xác định key bao gồm mọi chiều ảnh hưởng đến kết quả (ví dụ tenant và ID), kiểm soát quyền trước khi đọc cache, đặt TTL/invalidation rõ ràng và tránh giữ một connection/transaction trong cache.

### 9.2. Cache nằm trong phương thức @Transactional cần được hiểu đúng

Ví dụ:

~~~java
@Transactional
public Mono<Customer> loadAndCache(Long id) {
    return customerRepository.findById(id).cache();
}
~~~

Transaction interceptor bao publisher mà method trả về. Subscription đầu tiên kích hoạt transaction và nguồn cache. Khi kết quả được cache, những subscription sau có thể nhận lại dữ liệu mà không thực hiện query mới. Không nên giả định mỗi subscriber sau đều có một lần đọc database mới chỉ vì method có @Transactional.

Khi dữ liệu phải được đọc mới theo transaction của từng caller, không đặt cache lên publisher đó. Hãy tạo publisher query mới cho từng subscription hoặc đặt cache ở một tầng khác với semantics và phạm vi rõ ràng.

## 10. Connection pool và chi phí truy vấn lặp

Mỗi lần subscription vào publisher cold có thể tạo một lần lấy connection và thực thi SQL. Khi nhiều subscriber cùng kích hoạt truy vấn, connection pool có thể chịu áp lực.

Ví dụ một request tạo nhiều nhánh độc lập:

~~~java
Mono<Customer> customer = customerRepository.findById(id);

Mono<String> name = customer.map(Customer::name);
Mono<String> status = customer.map(Customer::status);
Mono<String> email = customer.map(Customer::email);

return Mono.zip(name, status, email);
~~~

Ba nhánh có thể khiến cùng query được subscribe ba lần. Với lưu lượng cao, mẫu này tạo nhiều truy vấn giống nhau và tăng tải database.

Cách đơn giản là biến đổi một lần:

~~~java
return customerRepository.findById(id)
        .map(found -> new CustomerView(
                found.name(),
                found.status(),
                found.email()
        ));
~~~

Nếu có lý do cần nhiều nhánh độc lập, có thể cache kết quả trong scope của tác vụ:

~~~java
Mono<Customer> customer = customerRepository.findById(id).cache();

Mono<String> name = customer.map(Customer::name);
Mono<String> status = customer.map(Customer::status);
Mono<String> email = customer.map(Customer::email);

return Mono.zip(name, status, email);
~~~

Cache publisher này chỉ nên được tạo cho một request/tác vụ cụ thể và không lưu trong singleton field nếu không có chính sách quản lý key và invalidation.

Đối với Flux streaming, một subscription duy nhất có thể giữ connection trong suốt quá trình đọc. Share có thể cho nhiều subscriber cùng tiêu thụ một stream, còn cache có thể phải đọc và lưu nhiều phần tử. Cả hai đều ảnh hưởng đến backpressure, memory và thời gian giữ connection.

## 11. Retry và repeat cũng có thể chạy lại SQL

Reactor có operator resubscribe như `retry`, `retryWhen` và `repeat`.

Ví dụ:

~~~java
Mono<Customer> customer =
        customerRepository.findById(id)
                .retryWhen(retryPolicy);
~~~

Khi lỗi phù hợp policy xảy ra, retry subscribe lại nguồn. Với repository cold, câu SELECT có thể được thực thi lại.

`repeat` có thể subscribe lại sau khi publisher complete:

~~~java
Flux<Customer> polling =
        customerRepository.findByStatus("PENDING")
                .repeat(3);
~~~

Điều này có thể tạo nhiều lần query. Cần phân biệt retry sau lỗi với repeat sau complete: retry thường dùng để thử lại khi thất bại; repeat dùng để chạy lại sau khi hoàn tất.

### 11.1. Thứ tự retry và cache làm thay đổi kết quả

Retry trước cache:

~~~java
Mono<Customer> cached =
        customerRepository.findById(id)
                .retryWhen(retryPolicy)
                .cache(Duration.ofSeconds(10));
~~~

Nguồn có thể được retry theo policy; tín hiệu cuối cùng sau retry được cache.

Cache trước retry:

~~~java
Mono<Customer> result =
        customerRepository.findById(id)
                .cache()
                .retryWhen(retryPolicy);
~~~

Nếu cache đã giữ error, retry có thể chỉ nhận lại cùng error từ cache thay vì thực hiện truy vấn database mới. Đặt cache trước retry có thể làm retry không đạt mục đích.

Với retry một lệnh ghi, cần đánh giá liệu lần thực thi trước có thể đã commit nhưng phản hồi bị mất hay không. Retry một phép cộng dồn có thể áp dụng thay đổi hai lần. Dùng idempotency key, unique constraint hoặc câu lệnh idempotent phù hợp khi kết quả commit không chắc chắn.

## 12. Đăng ký nhiều lần với thao tác ghi

Multiple subscriptions không chỉ làm SELECT chạy lặp. Với INSERT, UPDATE hoặc DELETE, subscription mới có thể thực hiện lại side effect.

Ví dụ:

~~~java
Mono<Customer> create =
        customerRepository.save(new Customer(
                null,
                "An Nguyen",
                "an@example.test"
        ));

create.subscribe();
create.subscribe();
~~~

Hai subscription có thể tạo hai lần insert. Nếu ID do database sinh và không có business key unique, database có thể lưu hai hàng khác nhau. Nếu có unique constraint, subscription thứ hai có thể lỗi.

Với update cộng dồn:

~~~java
Mono<Long> increment =
        databaseClient.sql("""
                UPDATE inventory
                SET quantity = quantity + 1
                WHERE sku = :sku
                """)
            .bind("sku", sku)
            .fetch()
            .rowsUpdated();
~~~

Subscribe hai lần làm quantity tăng hai lần. Cùng một publisher không có nghĩa cùng một lần thực thi.

### 12.1. Không dùng cache() làm cơ chế idempotency cho write

Có thể một Mono cache ngăn cùng publisher instance chạy nguồn nhiều lần:

~~~java
Mono<Customer> cachedWrite =
        customerRepository.save(customer).cache();
~~~

Nhưng đây không phải cơ chế idempotency đáng tin cậy cho API:

- Cache chỉ tồn tại trong bộ nhớ và vòng đời publisher.
- Instance khác hoặc process khác không chia sẻ cache.
- Process restart làm mất cache.
- Cache có thể giữ lỗi hoặc kết quả cũ.
- Một request mới có thể tạo publisher mới và chạy lại write.
- Cache không bảo vệ các side effect bên ngoài publisher.

Với nghiệp vụ cần chống request lặp, dùng idempotency key được lưu ở database với unique constraint và transaction phù hợp. Không dựa vào cache publisher để bảo đảm ghi đúng một lần.

### 12.2. Retry write cần semantics lũy đẳng

Nếu database đã commit nhưng kết nối bị ngắt trước khi ứng dụng nhận kết quả, caller có thể không biết thao tác thành công hay chưa. Retry có thể thực hiện lại SQL.

Với thao tác đặt giá trị tuyệt đối, lặp lại có thể tạo cùng trạng thái. Với cộng dồn, tạo mới hoặc phát event, cần khóa idempotency, event ID, unique constraint hoặc outbox/deduplication để tránh tác động lặp.

## 13. Dùng cache ở đúng tầng

Có nhiều loại cache và mỗi loại có phạm vi khác nhau.

### 13.1. Cache cục bộ cho một pipeline

Dùng `Mono.cache()` khi nhiều nhánh trong cùng một tác vụ cần cùng kết quả và việc đọc lại database là không cần thiết:

~~~java
public Mono<CustomerView> buildView(Long id) {
    Mono<Customer> customerOnce =
            customerRepository.findById(id).cache();

    return Mono.zip(
            customerOnce.map(Customer::name),
            customerOnce.map(Customer::status)
    ).map(tuple -> new CustomerView(tuple.getT1(), tuple.getT2()));
}
~~~

Tốt hơn nữa là đọc một lần rồi map thành DTO nếu các phép biến đổi có thể thực hiện trong cùng callback. Cache hữu ích khi cần nhiều subscriber độc lập cùng nhận kết quả của một publisher.

### 13.2. Cache ứng dụng theo key

Nếu muốn cache kết quả qua nhiều request, cần một abstraction quản lý key, TTL, eviction, dung lượng và concurrency. Key cần phản ánh mọi yếu tố làm thay đổi kết quả:

~~~text
customer-summary:{tenantId}:{customerId}
~~~

Không dùng duy nhất customerId nếu dữ liệu phụ thuộc tenant hoặc quyền truy cập. Cần quyết định cache có lưu empty/error hay chỉ lưu kết quả thành công; cache framework thường cho phép cấu hình semantics này rõ hơn publisher cache thô.

### 13.3. Cache ở tầng HTTP hoặc service

Một response DTO bất biến có thể phù hợp với cache tầng ứng dụng hoặc HTTP. Nhưng cache response không được bỏ qua authorization. Nếu nội dung khác nhau theo người dùng, tenant, locale hoặc quyền, những chiều đó phải được xử lý trong cache key hoặc không cache chung.

### 13.4. Khi không nên cache

Không nên cache publisher khi:

- Kết quả phải phản ánh database mới nhất ở mỗi request.
- Kết quả phụ thuộc transaction snapshot hoặc security context.
- Publisher phát Flux rất lớn và không có giới hạn memory.
- Publisher đại diện cho một write cần thực hiện mỗi lần được gọi.
- Error tạm thời không nên được giữ lại.
- TTL/invalidation không được xác định.
- Publisher được lưu trong singleton và chứa dữ liệu riêng của caller.

## 14. Cách quan sát số lần query thực tế

Khi nghi ngờ một publisher chạy nhiều lần, hãy đo số lần thực thi thay vì suy luận chỉ từ số dòng code.

Có thể bật SQL logging phù hợp với driver hoặc quan sát statement qua test database. Một cách minh họa trong unit test là đếm subscription nguồn:

~~~java
AtomicInteger subscriptions = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    subscriptions.incrementAndGet();
    return Mono.just("value");
});
~~~

Hai lần subscribe:

~~~java
StepVerifier.create(source).expectNext("value").verifyComplete();
StepVerifier.create(source).expectNext("value").verifyComplete();

assertThat(subscriptions.get()).isEqualTo(2);
~~~

Với cache:

~~~java
AtomicInteger cachedSubscriptions = new AtomicInteger();

Mono<String> cachedSource = Mono.defer(() -> {
    cachedSubscriptions.incrementAndGet();
    return Mono.just("value");
}).cache();

StepVerifier.create(cachedSource).expectNext("value").verifyComplete();
StepVerifier.create(cachedSource).expectNext("value").verifyComplete();

assertThat(cachedSubscriptions.get()).isEqualTo(1);
~~~

Ví dụ này xác nhận semantics subscription của Reactor, không chứng minh SQL của R2DBC. Để xác nhận query thực tế, dùng integration test với database tương thích, SQL logging hoặc công cụ quan sát statement.

Cần đo thêm:

- Số statement mỗi request.
- Số lần lấy connection từ pool.
- Thời gian chờ connection.
- Thời gian thực thi và số hàng trả về.
- Số subscriber và thời điểm họ tham gia/hủy.
- Heap usage khi dùng cache Flux.
- Tỷ lệ retry và số lần statement được thử lại.

Không bật log bind parameter nhạy cảm trong production nếu chưa có cơ chế bảo vệ.

## 15. Kiểm thử cache và share

### 15.1. Kiểm tra cold source chạy lại

~~~java
@Test
void coldPublisherExecutesForEachSubscription() {
    AtomicInteger executions = new AtomicInteger();

    Mono<Integer> source = Mono.defer(() ->
            Mono.just(executions.incrementAndGet())
    );

    StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

    StepVerifier.create(source)
            .expectNext(2)
            .verifyComplete();
}
~~~

Test xác nhận mỗi subscription tạo một lần thực thi mới.

### 15.2. Kiểm tra cache chỉ subscribe nguồn một lần

~~~java
@Test
void cacheReplaysTheSourceSignal() {
    AtomicInteger executions = new AtomicInteger();

    Mono<Integer> cached = Mono.defer(() ->
            Mono.just(executions.incrementAndGet())
    ).cache();

    StepVerifier.create(cached)
            .expectNext(1)
            .verifyComplete();

    StepVerifier.create(cached)
            .expectNext(1)
            .verifyComplete();

    assertThat(executions.get()).isEqualTo(1);
}
~~~

Test này cũng cho thấy subscriber thứ hai nhận lại giá trị cũ thay vì tạo giá trị mới.

### 15.3. Kiểm tra share với subscriber đồng thời

Với Flux share, cần tạo hai subscriber tham gia trong lúc nguồn đang phát. Có thể dùng nguồn test có điều khiển thời gian hoặc sink để xác nhận hai subscriber nhận cùng phần tử phát sau khi cả hai đã đăng ký.

Không nên viết test dựa vào sleep tùy tiện. Dùng StepVerifier, TestPublisher hoặc Sinks để điều phối thời điểm subscribe và emit một cách xác định.

### 15.4. Kiểm tra subscriber đến muộn

Với share, kiểm tra subscriber tham gia sau khi một số phần tử đã phát sẽ không nhận lại lịch sử như cache. Đây là khác biệt quan trọng cần thể hiện trong test.

Với cache, kiểm tra subscriber đến sau nhận lại các giá trị đã được cache theo history/TTL đã cấu hình.

### 15.5. Kiểm tra lỗi và empty signal

Test cả trường hợp:

- Mono phát một giá trị.
- Mono hoàn tất rỗng.
- Mono phát lỗi.
- Flux hoàn tất bình thường.
- Flux phát lỗi giữa stream.
- TTL hết hạn.
- Subscriber cancel trước khi nguồn hoàn tất.

Những trường hợp này giúp xác nhận cache/share có giữ, phát lại hoặc hủy nguồn theo semantics mong muốn.

### 15.6. Kiểm thử trên database thực tế

Dùng Testcontainers hoặc database test cùng loại để kiểm tra:

- Hai subscription vào repository có tạo hai SELECT không.
- Cache có ngăn query nguồn chạy lại trong cùng publisher instance không.
- Share có thực sự multicast một result stream trong tình huống concurrent subscriber không.
- Cancellation có giải phóng connection như mong đợi không.
- Transaction context không bị chia sẻ sai giữa các subscriber.
- Retry có tạo lại SQL và write có an toàn khi retry không.

Mock repository chỉ xác nhận code gọi method; nó không chứng minh số statement thực thi, connection lifecycle hoặc transaction behavior của driver.

## 16. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cùng một SELECT xuất hiện nhiều lần | Publisher cold được subscribe ở nhiều nhánh | Đọc một lần rồi map; hoặc cache trong scope phù hợp |
| Dùng Mono.zip nhưng query chạy hai lần | Cùng source cold được truyền vào nhiều nhánh | Tạo một publisher cache hoặc cấu trúc lại pipeline |
| Dữ liệu trả về cũ | Cache giữ kết quả sau khi database đã thay đổi | TTL, invalidation hoặc query mới |
| Subscriber sau không nhận đủ hàng | Dùng share cho Flux nhưng mong replay | Dùng cache/replay hoặc truy vấn mới |
| Heap tăng mạnh | Cache Flux không giới hạn toàn bộ kết quả | Giới hạn lịch sử, page dữ liệu hoặc dùng cache có eviction |
| Lỗi database lặp lại dù có retry | Error đã được cache trước retry | Đặt retry trước cache hoặc bỏ cache error |
| Update cộng dồn bị nhân đôi | Publisher write được subscribe/retry nhiều lần | Idempotency key, event deduplication hoặc phép ghi idempotent |
| Connection pool cạn | Nhiều subscription/stream đồng thời | Loại bỏ subscription thừa, giới hạn concurrency và stream lifetime |
| Cache dùng nhầm tenant/user | Dùng chung publisher/cache không có key context | Phân vùng cache theo identity/tenant và kiểm tra authorization |
| Transaction khác nhau nhận cùng kết quả cache | Cache publisher qua transaction boundary | Không cache dữ liệu transaction-scoped; cache ở tầng phù hợp |
| Subscriber share bỏ lỡ dữ liệu đầu | Subscriber tham gia sau khi Flux đã phát | Dùng replay/cache nếu cần lịch sử |
| Request mới không tạo truy vấn mới | Tái sử dụng publisher cache sống lâu | Tạo publisher theo request hoặc quản lý cache key/TTL rõ ràng |

## 17. Quy trình quyết định có nên cache hoặc share

Trước khi thêm operator, hãy trả lời:

1. Nguồn repository là cold publisher hay đã được chia sẻ ở tầng khác?
2. Publisher được subscribe bao nhiêu lần trong một request?
3. Các nhánh thực sự cần cùng một kết quả hay cần dữ liệu mới độc lập?
4. Subscriber có tham gia đồng thời hay đến lệch thời điểm?
5. Subscriber đến muộn có cần nhận lại các phần tử đã phát không?
6. Kết quả có thể stale trong bao lâu?
7. Cache có giữ empty/error signal không?
8. Flux có thể rất lớn và gây giữ bộ nhớ không?
9. Publisher có phụ thuộc tenant, user, quyền hoặc transaction context không?
10. Có thao tác ghi, retry hoặc side effect nào có thể bị lặp không?
11. TTL, invalidation và cache key đã được xác định chưa?
12. Đã đo số SQL, connection và memory trên workload thực tế chưa?

Một lựa chọn thường phù hợp:

- **Không cache:** mỗi request cần đọc dữ liệu mới hoặc publisher đại diện cho một thao tác cần thực thi riêng.
- **Mono.cache() ngắn hạn:** nhiều nhánh trong cùng một tác vụ cần cùng một giá trị.
- **Flux.cache(history/TTL):** cần replay một stream đã phát và đã kiểm soát kích thước/lifetime.
- **share():** nhiều subscriber đồng thời cần nhận cùng luồng đang phát, không cần replay lịch sử.
- **Cache abstraction theo key:** cần reuse dữ liệu qua nhiều request với TTL, eviction và invalidation nghiệp vụ.

## 18. Kết luận

Publisher repository của Spring Data R2DBC thường là cold: mỗi subscription độc lập có thể thực thi lại SQL và lấy connection mới. Vì vậy, cùng một Mono hoặc Flux được dùng ở nhiều nhánh, subscribe nhiều lần, block nhiều lần hoặc retry/repeat có thể tạo thêm truy vấn. Với thao tác ghi, việc thực thi lặp còn có thể tạo dữ liệu trùng hoặc áp dụng side effect nhiều lần.

`cache()` chia sẻ subscription nguồn và replay tín hiệu/kết quả đã lưu cho subscriber sau. Nó có thể giữ cả giá trị, empty signal và error; cache vô thời hạn hoặc cache toàn bộ Flux có thể gây dữ liệu cũ và tiêu thụ nhiều bộ nhớ. TTL giới hạn thời gian lưu nhưng không thay thế invalidation nghiệp vụ.

`share()` phù hợp với multicast cho các subscriber cùng tham gia một luồng đang phát. Với Flux, subscriber đến muộn không nhận lại lịch sử đã phát như cache. Nó không phải cache theo key hoặc cơ chế deduplication bền vững.

Hãy kiểm soát số subscription trước khi thêm operator, giữ publisher cache trong phạm vi phù hợp, không chia sẻ dữ liệu phụ thuộc transaction/security context giữa các caller và không dùng cache để làm cho write trở nên idempotent. Với retry hoặc message có thể giao lại, dùng unique constraint, idempotency key và transaction phù hợp. Kiểm tra số SQL, connection lifecycle, memory và transaction behavior bằng integration test trên database/driver thực tế.

