# Observable, Flowable, Single, Maybe và Completable

RxJava cung cấp nhiều kiểu nguồn reactive để mô tả số lượng giá trị mà một tác vụ có thể phát. Chọn đúng kiểu giúp chữ ký API thể hiện rõ hợp đồng dữ liệu: một luồng có thể phát nhiều phần tử, một kết quả bắt buộc phải có, một kết quả có thể vắng mặt hoặc một thao tác chỉ báo hoàn tất. Việc chọn kiểu cũng ảnh hưởng đến cách ứng dụng xử lý backpressure, ghép nối tác vụ và kiểm thử.

Năm kiểu thường gặp là Observable, Flowable, Single, Maybe và Completable. Observable và Flowable phát từ không đến nhiều phần tử; khác biệt chính là Flowable hỗ trợ backpressure theo Reactive Streams. Single phát đúng một giá trị hoặc lỗi. Maybe phát tối đa một giá trị hoặc hoàn tất rỗng. Completable chỉ biểu diễn hoàn tất hoặc lỗi, không phát giá trị dữ liệu.

Bài học thuộc chương **RxJava** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java. Nắm được các kiểu RxJava giúp lựa chọn đúng hợp đồng khi tích hợp thư viện reactive khác trong hệ sinh thái Java.

Các ví dụ dùng API RxJava 3. Những tên như orderRepository, cache hoặc notificationService đại diện cho thành phần của ứng dụng; hãy bổ sung import và kiểu miền tương ứng khi áp dụng vào dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt hợp đồng số lượng phần tử của Observable, Flowable, Single, Maybe và Completable.
- Chọn kiểu phù hợp với nguồn dữ liệu và yêu cầu của API.
- Giải thích vai trò của backpressure trong Flowable và giới hạn của Observable.
- Chuyển đổi giữa các kiểu mà vẫn giữ đúng ngữ nghĩa dữ liệu.
- Kết hợp các kiểu trong pipeline bằng flatMap, zip, andThen và các toán tử liên quan.
- Kiểm thử giá trị, hoàn tất, lỗi và demand bằng TestObserver và TestSubscriber.

## 1. Nhìn năm kiểu qua hợp đồng dữ liệu

Điểm bắt đầu khi chọn kiểu là hỏi: một subscription có thể phát bao nhiêu giá trị?

| Kiểu | Số giá trị thành công | Kết thúc thành công | Backpressure |
|---|---:|---|---|
| Observable<T> | 0 đến nhiều | onComplete | Không hỗ trợ request(n) |
| Flowable<T> | 0 đến nhiều | onComplete | Có, theo Reactive Streams |
| Single<T> | Đúng một | onSuccess(value) | Không dùng hợp đồng demand của Flowable |
| Maybe<T> | 0 hoặc một | onSuccess(value) hoặc onComplete rỗng | Không dùng hợp đồng demand của Flowable |
| Completable | Không có giá trị | onComplete | Không dùng hợp đồng demand của Flowable |

Observable và Flowable đều phù hợp với nhiều phần tử nhưng dùng hợp đồng nguồn khác nhau. Observable triển khai ObservableSource của RxJava và phát theo tốc độ nguồn; nó không phải Reactive Streams Publisher. Flowable triển khai org.reactivestreams.Publisher, vì vậy downstream có thể yêu cầu số phần tử bằng request(n). Khi nguồn có thể phát nhanh hơn consumer, Flowable cung cấp cơ chế để xử lý chênh lệch đó.

Single, Maybe và Completable diễn tả cardinality cụ thể hơn. Chúng triển khai các source contract riêng của RxJava, không trực tiếp triển khai Reactive Streams Publisher như Flowable. Khi cần đưa chúng vào một API nhận Flowable hoặc Observable, có thể chuyển đổi rõ ràng.

Có thể hình dung:

~~~text
Nguồn reactive RxJava
|
+-- Nhiều phần tử
|   |-- Observable: push, không có request(n)
|   `-- Flowable: Reactive Streams, có backpressure
|
`-- Tác vụ đơn
    |-- Single: đúng một giá trị
    |-- Maybe: không hoặc một giá trị
    `-- Completable: không có giá trị
~~~

Sơ đồ phân loại theo số giá trị thành công. Observable và Flowable khác nhau ở backpressure; Maybe có thể hoàn tất rỗng, còn Completable luôn không phát dữ liệu.

## 2. Observable: luồng nhiều phần tử không có backpressure

Observable biểu diễn một nguồn có thể phát không, một hoặc nhiều phần tử, sau đó hoàn tất hoặc phát lỗi:

~~~java
Observable<String> names =
    Observable.just("An", "Bình", "Chi");

Observable<Integer> numbers =
    Observable.range(1, 5);
~~~

Observable thường phù hợp với các luồng sự kiện có tốc độ được kiểm soát ở tầng ứng dụng, dữ liệu giao diện hoặc các nguồn hữu hạn nhỏ. Nó cũng hữu ích khi tích hợp API callback không cung cấp cơ chế demand.

Subscriber của Observable không gửi request(n). Nếu nguồn phát nhanh hơn bước xử lý, Observable không tự điều tiết nguồn theo Reactive Streams. Các toán tử như buffer, sample, debounce hoặc observeOn có thể thay đổi cách xử lý và lưu dữ liệu, nhưng không biến Observable thành một nguồn có backpressure.

Ví dụ:

~~~java
Observable<UiEvent> uiEvents =
    view.clickEvents()
        .observeOn(Schedulers.computation())
        .map(this::toUiEvent);
~~~

observeOn chuyển các tín hiệu phía sau nó sang scheduler khác. Nó không tự giới hạn số sự kiện mà nguồn có thể phát; nếu producer liên tục nhanh hơn consumer, hàng đợi giữa các scheduler có thể tăng.

Hãy dùng Observable khi hợp đồng nguồn và tải cho phép xử lý theo kiểu push, hoặc khi chính sách bỏ/gom sự kiện đã được xác định rõ. Nếu cần phối hợp demand với nguồn theo Reactive Streams, cân nhắc Flowable.

## 3. Flowable: luồng nhiều phần tử có backpressure

Flowable biểu diễn một Publisher có thể phát nhiều phần tử và tuân theo cơ chế demand của Reactive Streams. Subscriber yêu cầu số phần tử mà nó sẵn sàng nhận. Nguồn chỉ được phát trong giới hạn demand đã được yêu cầu.

~~~java
Flowable<Integer> values =
    Flowable.range(1, 1_000)
        .map(value -> value * 2);
~~~

Flowable phù hợp với nguồn dữ liệu có thể điều tiết theo request hoặc pipeline cần kiểm soát lượng dữ liệu đang được tiêu thụ. Các nguồn như range, iterable và nhiều reactive client có thể hỗ trợ demand trực tiếp.

### Quan sát demand bằng TestSubscriber

~~~java
TestSubscriber<Integer> subscriber =
    new TestSubscriber<>(0L);

Flowable.range(1, 5).subscribe(subscriber);

subscriber.assertNoValues();

subscriber.request(2);
subscriber.assertValues(1, 2);

subscriber.cancel();
~~~

TestSubscriber bắt đầu với demand bằng không nên chưa nhận phần tử. Sau request(2), subscriber nhận đúng hai giá trị đầu. Việc hủy kết thúc nhu cầu tiêu thụ của subscription.

Trong ứng dụng, demand thường được quản lý bởi các toán tử và subscriber cuối. Khi tự triển khai Subscriber, cần tuân thủ quy tắc Reactive Streams: request số dương, không phát quá demand và không phát thêm sau cancel hoặc terminal signal.

### Nguồn không hỗ trợ backpressure

Một callback hoặc thiết bị có thể phát dữ liệu theo tốc độ riêng, không thể chờ request. Khi chuyển nguồn đó thành Flowable, cần chọn BackpressureStrategy:

~~~java
Flowable<SensorReading> readings =
    Flowable.create(emitter -> {
        SensorRegistration registration =
            sensor.register(emitter::onNext);

        emitter.setCancellable(registration::dispose);
    }, BackpressureStrategy.LATEST);
~~~

Ví dụ dùng LATEST để giữ giá trị mới nhất khi downstream chưa theo kịp. Registration và API sensor là kiểu minh họa của ứng dụng; cần xử lý thêm lỗi đăng ký và việc dừng sensor theo hợp đồng SDK thực tế.

Nếu SDK có thể gọi callback từ nhiều thread đồng thời, hãy tuần tự hóa các tín hiệu trước khi phát, chẳng hạn dùng emitter đã gọi serialize(). Việc gắn setCancellable cũng rất quan trọng: khi subscriber hủy, đăng ký với sensor phải được dispose để ngừng callback và tránh giữ tài nguyên.

Các chiến lược thường dùng:

| BackpressureStrategy | Hành vi | Khi phù hợp |
|---|---|---|
| BUFFER | Đệm phần tử chờ demand | Cần giữ dữ liệu và có giới hạn tải rõ; buffer mặc định có thể tăng lớn |
| DROP | Bỏ phần tử đến khi không có demand | Dữ liệu dư có thể bị loại bỏ |
| LATEST | Giữ giá trị mới nhất, thay thế giá trị chờ cũ | Chỉ cần trạng thái gần nhất |
| ERROR | Phát lỗi khi không thể chuyển tiếp do thiếu demand | Muốn phát hiện consumer không theo kịp |
| MISSING | Không áp dụng chính sách tại nguồn | Ứng dụng sẽ xử lý backpressure ở bước sau |

BUFFER không phải giải pháp bộ nhớ vô hạn an toàn. Nếu tốc độ đến trung bình cao hơn tốc độ xử lý trong thời gian dài, hàng đợi vẫn có thể tăng cho đến khi cạn bộ nhớ. DROP và LATEST làm mất dữ liệu theo chủ đích; chỉ dùng khi nghiệp vụ chấp nhận. ERROR biến tình trạng không theo kịp thành tín hiệu lỗi để tầng gọi quyết định tiếp theo.

Flowable không tự làm một thiết bị hoặc callback bên ngoài chậm lại. Khi nguồn không hỗ trợ demand, chiến lược backpressure quyết định dữ liệu nào được giữ, bỏ hoặc chuyển thành lỗi.

## 4. Single: một giá trị bắt buộc

Single biểu diễn một tác vụ thành công bằng đúng một giá trị hoặc kết thúc bằng lỗi. Nó không phát onComplete sau onSuccess; onSuccess chính là tín hiệu kết thúc thành công.

~~~java
Single<Customer> customer =
    Single.fromCallable(() ->
        customerRepository.findRequired(customerId)
    );
~~~

Single phù hợp với truy vấn bắt buộc phải có kết quả, tính toán trả về một giá trị hoặc một lời gọi dịch vụ trả về đúng một phản hồi. Nếu không tìm thấy dữ liệu, tầng repository cần biểu diễn tình huống đó thành lỗi phù hợp, hoặc API nên dùng Maybe nếu vắng mặt là kết quả bình thường.

Single.fromCallable yêu cầu hàm trả về một giá trị khác null. Nếu hàm trả null, Single phát lỗi NullPointerException; khi null có nghĩa là “không có kết quả”, hãy dùng Maybe.fromCallable để biểu diễn nhánh rỗng.

Ví dụ kết hợp hai kết quả đơn:

~~~java
Single<CustomerView> view =
    Single.zip(
        customerRepository.findRequired(customerId),
        accountRepository.loadBalance(customerId),
        CustomerView::new
    );
~~~

zip chờ cả hai Single phát thành công rồi kết hợp hai giá trị. Nếu một nguồn lỗi, kết quả kết hợp phát lỗi. Hàm kết hợp nên nhanh và không thực hiện I/O chặn.

Một số toán tử thường gặp:

- map biến đổi một giá trị thành một giá trị khác.
- flatMap nối sang một Single khác khi bước tiếp theo cũng trả một giá trị.
- onErrorReturn hoặc onErrorResume cung cấp giá trị thay thế hoặc nguồn thay thế khi lỗi.
- toMaybe chuyển hợp đồng một giá trị bắt buộc thành hợp đồng có thể rỗng.
- ignoreElement bỏ giá trị và giữ lại kết quả hoàn tất dạng Completable.

Nếu hàm bên trong Single.fromCallable thực hiện I/O chặn, hãy chỉ định scheduler phù hợp:

~~~java
Single<Customer> customer =
    Single.fromCallable(() ->
        blockingRepository.findRequired(customerId)
    )
    .subscribeOn(Schedulers.io());
~~~

subscribeOn điều phối nơi subscription và công việc nguồn bắt đầu chạy. Việc chuyển scheduler không làm một API chặn trở thành non-blocking; nó chỉ cô lập công việc chặn khỏi thread không phù hợp.

## 5. Maybe: không hoặc một giá trị

Maybe biểu diễn một kết quả có thể tồn tại hoặc vắng mặt. Khi có dữ liệu, nó phát onSuccess(value). Khi không có dữ liệu, nó phát onComplete mà không có onNext. Nó cũng có thể phát onError.

~~~java
Maybe<Customer> cachedCustomer =
    Maybe.fromCallable(() ->
        customerCache.find(customerId)
    );
~~~

Trong ví dụ, nếu hàm trả về null, Maybe.fromCallable hoàn tất rỗng. Nếu có Customer, nó phát đúng một giá trị. Nếu hàm ném lỗi, Maybe phát onError.

Maybe phù hợp với:

- Tìm một bản ghi có thể không tồn tại.
- Đọc giá trị cache có thể chưa được nạp.
- Tìm phần tử đầu tiên trong một nguồn có thể rỗng.
- Thao tác tùy chọn mà không cần dùng null làm tín hiệu dữ liệu.

Ví dụ fallback khi cache không có dữ liệu:

~~~java
Maybe<Customer> customer =
    customerCache.find(customerId)
        .switchIfEmpty(
            customerRepository.findOptional(customerId)
        );
~~~

switchIfEmpty đăng ký nguồn thay thế khi Maybe hoàn tất mà không phát giá trị. Nếu nguồn đầu tiên phát Customer, nguồn thay thế không được sử dụng.

Có thể chuyển Maybe thành Single khi cần cung cấp giá trị mặc định hoặc lỗi nếu rỗng:

~~~java
Single<Customer> requiredCustomer =
    customer
        .switchIfEmpty(Maybe.error(
            new CustomerNotFoundException(customerId)
        ))
        .toSingle();
~~~

Hãy phân biệt trường hợp “không tìm thấy” là bình thường hay là lỗi nghiệp vụ. Nếu API gọi cần bắt buộc có kết quả, Single hoặc lỗi cụ thể có thể diễn đạt hợp đồng rõ hơn. Nếu vắng mặt là bình thường, giữ Maybe giúp caller phải xử lý nhánh rỗng.

## 6. Completable: chỉ quan tâm thao tác hoàn tất

Completable biểu diễn một thao tác không cần trả giá trị dữ liệu. Nó kết thúc bằng onComplete hoặc onError:

~~~java
Completable saveOrder =
    Completable.fromAction(() ->
        orderRepository.save(order)
    );
~~~

Ví dụ dùng fromAction để bọc một hành động đồng bộ. Nếu repository có API reactive, nên giữ nguyên Publisher của repository thay vì gọi một phương thức blocking bên trong fromAction.

Completable thường phù hợp với:

- Lưu hoặc cập nhật dữ liệu khi caller chỉ cần biết thành công hay thất bại.
- Gửi một lệnh điều khiển không trả payload.
- Xóa cache hoặc hủy một tài nguyên.
- Hoàn tất một quy trình cleanup.

Có thể nối nhiều thao tác theo thứ tự:

~~~java
Completable workflow =
    orderRepository.save(order)
        .andThen(notificationService.sendOrderCreated(order))
        .andThen(auditService.record(order));
~~~

andThen chỉ đăng ký bước tiếp theo sau khi bước trước hoàn tất thành công. Nếu bước trước phát lỗi, các bước sau không chạy và lỗi được chuyển xuống downstream.

Nếu cần lấy giá trị sau một Completable, dùng andThen với Single hoặc Maybe:

~~~java
Single<OrderReceipt> receipt =
    orderRepository.save(order)
        .andThen(receiptRepository.createFor(order));
~~~

Completable không có onNext. Vì vậy, không nên dùng nó nếu caller cần nhận ID, trạng thái hoặc kết quả tính toán; hãy dùng Single hoặc Maybe theo cardinality của kết quả.

## 7. Chọn kiểu theo yêu cầu nghiệp vụ

| Yêu cầu | Kiểu nên cân nhắc | Lý do |
|---|---|---|
| Một luồng sự kiện push, không cần demand | Observable | API đơn giản cho nguồn không hỗ trợ backpressure |
| Một luồng dữ liệu có thể điều tiết theo request | Flowable | Hỗ trợ Reactive Streams và backpressure |
| Truy vấn phải trả đúng một bản ghi | Single | Hợp đồng bắt buộc một giá trị |
| Truy vấn có thể không tìm thấy bản ghi | Maybe | Biểu diễn rõ kết quả rỗng |
| Lệnh chỉ cần báo thành công hoặc lỗi | Completable | Không phát payload không cần thiết |
| Nguồn nóng phát nhanh hơn consumer | Flowable với chiến lược backpressure phù hợp | Chọn cách buffer, drop, latest hoặc error |
| Cần giữ mọi sự kiện nghiệp vụ | Flowable hoặc cơ chế lưu trữ bền vững phù hợp | Không dùng chiến lược bỏ dữ liệu |

Đừng chọn kiểu chỉ theo số phần tử hiện tại. Hãy chọn theo hợp đồng mà caller cần dựa vào. Nếu API trả Single nhưng thực tế có thể không có dữ liệu, caller sẽ phải xử lý lỗi thay cho nhánh rỗng. Nếu API trả Observable cho nguồn có thể phát rất nhanh, ứng dụng phải tự chịu trách nhiệm về tốc độ và bộ nhớ.

## 8. Chuyển đổi giữa các kiểu

RxJava cho phép chuyển đổi kiểu để ghép các thành phần có hợp đồng khác nhau. Khi chuyển, hãy chú ý liệu thao tác có thay đổi cardinality hoặc backpressure hay không.

### Liên hệ với Mono và Flux trong Reactor

Khi tích hợp RxJava với Project Reactor, có thể dùng bảng sau để đối chiếu hợp đồng. Đây là so sánh về cardinality và backpressure, không có nghĩa hai API có cùng mọi toán tử hoặc cùng cách phát tín hiệu:

| RxJava | Kiểu gần tương ứng trong Reactor | Điểm cần nhớ |
|---|---|---|
| Flowable<T> | Flux<T> | Cả hai là luồng nhiều phần tử hỗ trợ Reactive Streams backpressure |
| Observable<T> | Không có tương đương trực tiếp | Observable không truyền demand; khi chuyển sang Flux cần chọn cách xử lý nguồn push |
| Single<T> | Mono<T> | Single bắt buộc một giá trị; Mono có thể hoàn tất rỗng |
| Maybe<T> | Mono<T> | Cả hai biểu diễn không hoặc một giá trị |
| Completable | Mono<Void> | Cả hai có thể chỉ biểu diễn complete/error mà không phát payload |

Khi chuyển giữa thư viện, hãy xác định rõ cách ánh xạ empty, error, cancellation và backpressure. Đặc biệt, không được giả định một Single có thể hoàn tất rỗng như Mono.

### Observable và Flowable

~~~java
Observable<Event> observable =
    legacyEventSource();

Flowable<Event> buffered =
    observable.toFlowable(BackpressureStrategy.BUFFER);

Observable<Event> withoutDemand =
    buffered.toObservable();
~~~

toFlowable yêu cầu chọn chiến lược backpressure vì Observable nguồn không nhận demand. Chọn BUFFER, DROP, LATEST, ERROR hoặc MISSING theo đặc tính dữ liệu. Chuyển Flowable trở lại Observable làm mất khả năng truyền demand qua giao diện Observable.

### Single và Maybe

~~~java
Single<Customer> required =
    customerRepository.findRequired(customerId);

Maybe<Customer> optional =
    required.toMaybe();
~~~

toMaybe nới lỏng hợp đồng thành có thể rỗng, dù một Single thành công vốn luôn có giá trị. Chiều ngược lại cần quyết định trường hợp Maybe rỗng:

~~~java
Single<Customer> required =
    optional.toSingle(defaultCustomer);
~~~

Có thể dùng giá trị mặc định hoặc chuyển empty thành lỗi bằng các toán tử tương ứng. Không nên tự động thay bằng null vì null không phải giá trị onNext hợp lệ trong RxJava.

### Bỏ giá trị và giữ tín hiệu hoàn tất

Single hoặc Maybe có thể được chuyển thành Completable khi caller chỉ cần biết thao tác hoàn tất:

~~~java
Completable saved =
    orderRepository.saveAndReturnOrder(order)
        .ignoreElement();
~~~

ignoreElement bỏ payload và giữ tín hiệu complete/error. Dùng cách này khi giá trị trả về không còn cần thiết ở bước sau.

### Kết hợp Completable với nguồn có giá trị

~~~java
Single<Order> savedOrder =
    orderRepository.save(order)
        .andThen(Single.fromCallable(() ->
            orderRepository.findRequired(order.id())
        ));
~~~

andThen đảm bảo bước đọc chỉ chạy sau khi bước lưu hoàn tất. Nếu save lỗi, bước đọc không được đăng ký.

## 9. Kết hợp các kiểu trong một pipeline

Một ứng dụng thường có nhiều cardinality khác nhau. Ví dụ, luồng đơn hàng phát nhiều đơn; mỗi đơn cần một Single để tra cứu khách hàng; thao tác gửi thông báo trả Completable.

~~~java
Flowable<Order> orders =
    orderEventSource();

Flowable<NotificationResult> notifications =
    orders.flatMapSingle(order ->
        customerRepository.findRequired(order.customerId())
            .flatMap(customer ->
                notificationService.send(customer, order)
                    .andThen(Single.just(
                        NotificationResult.sent(order.id())
                    ))
            ),
        false,
        8
    );
~~~

Ví dụ minh họa việc chuyển một Flowable<Order> thành Flowable<NotificationResult>. flatMapSingle kết hợp mỗi phần tử nguồn với một Single; tham số concurrency giới hạn tối đa tám tác vụ con đồng thời. Tham số thứ hai là delayErrors: false có nghĩa lỗi được chuyển xuống ngay theo chính sách toán tử thay vì đợi các nguồn con còn lại hoàn tất.

Nếu thứ tự đầu ra phải giữ theo thứ tự đơn hàng, cân nhắc concatMapSingle. Nó xử lý từng Single con theo thứ tự nguồn, đổi lại giảm mức đồng thời.

Khi một bước chỉ cần báo hoàn tất, có thể dùng Completable trong chuỗi andThen. Khi cần giá trị, dùng Single hoặc Maybe. Hãy giữ kiểu cụ thể càng lâu càng tốt để chữ ký pipeline diễn đạt đúng điều mà từng bước bảo đảm.

## 10. Xử lý lỗi và tín hiệu kết thúc

Các kiểu RxJava đều có thể phát onError, nhưng tín hiệu thành công khác nhau:

| Kiểu | Thành công | Lỗi |
|---|---|---|
| Observable | 0..N onNext rồi onComplete | onError |
| Flowable | 0..N onNext theo demand rồi onComplete | onError |
| Single | Một onSuccess | onError |
| Maybe | Một onSuccess hoặc onComplete rỗng | onError |
| Completable | onComplete | onError |

Một số toán tử xử lý lỗi:

- onErrorReturn thay lỗi bằng giá trị dự phòng, phù hợp với Observable, Flowable hoặc Single.
- onErrorResumeNext chuyển sang nguồn thay thế khi lỗi.
- onErrorComplete biến lỗi thành hoàn tất rỗng đối với các kiểu hỗ trợ thao tác này, thường dùng khi lỗi được chấp nhận theo chính sách.
- retry thử đăng ký lại nguồn; cần bảo đảm tác dụng phụ có thể lặp lại an toàn hoặc có cơ chế idempotency.

Ví dụ với Maybe:

~~~java
Maybe<Customer> customer =
    customerCache.find(customerId)
        .onErrorResumeNext(error -> {
            log.warn("Cache lỗi, đọc nguồn chính", error);
            return customerRepository.findOptional(customerId);
        });
~~~

Ví dụ với Completable:

~~~java
Completable cleanup =
    resource.close()
        .onErrorComplete(error -> {
            log.error("Không thể đóng tài nguyên", error);
            return false;
        });
~~~

Ở ví dụ thứ hai, predicate false giữ lỗi lại; chỉ khi predicate trả true thì lỗi mới được chuyển thành complete. Không nên nuốt mọi lỗi cleanup nếu điều đó khiến tài nguyên vẫn bị giữ mà hệ thống không có cảnh báo.

Với Single, một trường hợp “không tìm thấy” không thể biểu diễn bằng complete rỗng; hãy dùng Maybe hoặc chuyển thành lỗi miền cụ thể. Với Completable, không có giá trị để mang mã kết quả; nếu caller cần chi tiết thành công, hãy trả Single hoặc một kiểu có dữ liệu.

## 11. Kiểm thử bằng TestObserver và TestSubscriber

RxJava cung cấp TestObserver cho Observable, Single, Maybe và Completable; TestSubscriber dùng cho Flowable. Các công cụ này giúp xác nhận dữ liệu, terminal signal, lỗi và demand mà không cần subscribe thủ công trong hầu hết unit test.

### Observable

~~~java
Observable.just("A", "B", "C")
    .test()
    .assertResult("A", "B", "C");
~~~

assertResult xác nhận đúng các giá trị theo thứ tự, không có lỗi và nguồn hoàn tất.

### Flowable và demand

~~~java
TestSubscriber<Integer> subscriber =
    new TestSubscriber<>(0L);

Flowable.range(1, 4).subscribe(subscriber);

subscriber.assertNoValues();

subscriber.request(2);
subscriber.assertValues(1, 2);

subscriber.cancel();
~~~

Kiểm thử xác nhận nguồn tôn trọng demand ban đầu bằng không và chỉ phát hai phần tử sau request(2).

### Single

~~~java
Single.just("saved")
    .test()
    .assertValue("saved")
    .assertNoErrors();
~~~

Single phát đúng một giá trị. Có thể kiểm thử lỗi bằng assertError hoặc assertFailure tùy yêu cầu.

### Maybe

~~~java
Maybe.<String>empty()
    .test()
    .assertNoValues()
    .assertComplete();
~~~

Kiểm thử xác nhận Maybe hoàn tất mà không phát giá trị. Với Maybe.just, dùng assertValue để xác nhận nhánh có dữ liệu.

### Completable

~~~java
Completable.complete()
    .test()
    .assertComplete()
    .assertNoErrors();
~~~

Completable không phát onNext; kiểm thử tập trung vào complete hoặc error.

Khi kiểm thử scheduler và timer, dùng TestScheduler hoặc các công cụ thời gian của RxJava để điều khiển thời điểm phát. Tránh Thread.sleep vì test có thể chậm và không ổn định theo tải máy. Với nguồn bất đồng bộ thật, đặt timeout cho test và dọn subscription sau khi xác nhận kết quả.

## 12. Những lỗi lựa chọn kiểu thường gặp

**Dùng Observable cho nguồn có tốc độ không kiểm soát.** Observable không có request(n). Nếu nguồn phát nhanh, queue ở các ranh giới bất đồng bộ có thể tăng. Chuyển sang Flowable khi cần backpressure hoặc chọn chính sách lấy mẫu/bỏ dữ liệu phù hợp.

**Dùng Flowable cho một kết quả đơn.** Nếu tác vụ chỉ trả một giá trị, Single thể hiện hợp đồng rõ hơn và giúp caller biết không có nhiều phần tử để tiêu thụ.

**Dùng Single cho dữ liệu có thể vắng mặt.** Đừng biến “không tìm thấy” thành lỗi kỹ thuật nếu đó là kết quả bình thường. Dùng Maybe hoặc một kiểu kết quả miền phù hợp.

**Dùng Completable rồi tìm cách lấy payload.** Completable chỉ biểu diễn hoàn tất hoặc lỗi. Nếu caller cần ID hoặc kết quả, trả Single<T>.

**Dùng BUFFER không giới hạn cho nguồn nóng.** Buffer có thể tích lũy vô hạn khi consumer chậm lâu dài. Chọn capacity, overflow policy và metrics theo yêu cầu dữ liệu.

**Chuyển Flowable thành Observable mà quên mất demand.** Khi chuyển đổi, downstream Observable không còn gửi request. Đánh giá lại tốc độ nguồn và hàng đợi phía sau.

**Bỏ qua nhánh empty của Maybe.** Nếu caller cần một kết quả bắt buộc, phải xử lý empty bằng giá trị mặc định, fallback hoặc lỗi miền.

## 13. Bài tập vận dụng

Một dịch vụ thương mại điện tử có các API sau:

- Luồng sự kiện đơn hàng mới phát liên tục.
- Truy vấn chi tiết một khách hàng phải trả đúng một bản ghi hoặc lỗi nếu không tồn tại.
- Truy vấn ảnh đại diện có thể không có dữ liệu.
- Gửi email xác nhận chỉ cần biết hoàn tất hay thất bại.
- Một SDK cũ phát callback nhanh và không hỗ trợ request(n).

Hãy chọn kiểu RxJava cho từng API và giải thích:

1. Vì sao luồng đơn hàng nên dùng Flowable nếu downstream cần điều tiết demand?
2. Khi nào Observable vẫn là lựa chọn chấp nhận được cho sự kiện giao diện?
3. Vì sao Single phù hợp với truy vấn khách hàng bắt buộc?
4. Vì sao Maybe diễn đạt tốt hơn null cho ảnh đại diện không tồn tại?
5. Vì sao gửi email có thể trả Completable?
6. Khi chuyển callback SDK thành Flowable, nên chọn BUFFER, DROP, LATEST hay ERROR? Nêu rõ yêu cầu nghiệp vụ quyết định lựa chọn.
7. Nếu mỗi đơn hàng cần tra cứu khách hàng bằng Single rồi gửi email bằng Completable, hãy phác thảo pipeline dùng flatMapSingle và andThen.
8. Viết kiểm thử cho một Flowable tôn trọng request, một Maybe empty và một Completable phát lỗi.

Một thiết kế tốt phải làm rõ cardinality, chính sách backpressure, ý nghĩa của kết quả rỗng và ai chịu trách nhiệm xử lý lỗi. Không có một kiểu duy nhất phù hợp với mọi nguồn; hãy để hợp đồng dữ liệu dẫn dắt lựa chọn.

## Kết luận

Observable và Flowable phát không hoặc nhiều phần tử; Flowable hỗ trợ backpressure theo Reactive Streams còn Observable thì không. Single diễn đạt một giá trị bắt buộc, Maybe diễn đạt không hoặc một giá trị, và Completable chỉ báo hoàn tất hoặc lỗi. Chọn đúng kiểu giúp API thể hiện rõ cardinality, cách xử lý dữ liệu vắng mặt và khả năng điều tiết nguồn. Khi ghép các kiểu trong pipeline, hãy giữ hợp đồng cụ thể, xử lý lỗi và kiểm thử cả dữ liệu lẫn demand bằng TestObserver hoặc TestSubscriber.
