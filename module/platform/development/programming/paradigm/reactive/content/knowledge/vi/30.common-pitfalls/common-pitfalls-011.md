# Nhầm hoàn thành rỗng, Mono<Void> và giá trị cần để phối hợp

Trong Reactor, một Publisher có thể hoàn tất thành công mà không phát ra phần tử nào. Đây là hành vi bình thường, không phải lỗi. Tuy nhiên, nếu nhầm tín hiệu hoàn tất rỗng với một kết quả có giá trị, pipeline có thể bỏ qua callback trong `flatMap`, không chạy hàm kết hợp của `zip`, hoặc kích hoạt nhánh `switchIfEmpty` ngoài dự kiến.

`Mono<Void>` là kiểu thường gặp ở thao tác chỉ báo hoàn tất như xóa dữ liệu, gửi lệnh hoặc ghi audit. Nó có thể báo thao tác đã hoàn tất hay thất bại, nhưng không phát một giá trị `Void` để downstream sử dụng. Khi cần phối hợp nhiều thao tác hoặc cần trả lại dữ liệu sau một thao tác `Mono<Void>`, phải chọn toán tử theo đúng ý nghĩa: `then` để nối theo thứ tự, `thenReturn` để phát giá trị sau khi hoàn tất, `when` để chờ nhiều thao tác hoàn tất, và `zip` để kết hợp các giá trị thực sự được phát.

Bài học thuộc chương **Lỗi thường gặp** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài này tập trung vào khác biệt giữa complete rỗng, `Mono<Void>` và một phần tử có giá trị khi phối hợp các Publisher.

## Ba kết quả khác nhau: có giá trị, rỗng và lỗi

Một `Mono<T>` có thể kết thúc theo ba cách:

| Kết quả | Tín hiệu | Ý nghĩa |
|---|---|---|
| Có giá trị | `onNext(value)` rồi `onComplete()` | Một kết quả đã được phát thành công |
| Hoàn tất rỗng | `onComplete()` mà không có `onNext` | Không có phần tử để phát, nhưng luồng hoàn tất bình thường |
| Thất bại | `onError(error)` | Luồng kết thúc bằng lỗi |

Ví dụ:

~~~java
Mono<String> found = Mono.just("customer-42");
Mono<String> missing = Mono.empty();
Mono<String> failed = Mono.error(
    new IllegalStateException("database unavailable")
);
~~~

`missing` không có nghĩa database đã gặp lỗi. Nó có thể biểu diễn việc không tìm thấy bản ghi hoặc một thao tác hợp lệ không tạo ra kết quả. `failed` mới là nhánh lỗi. Không nên biến mọi trường hợp rỗng thành lỗi nếu nghiệp vụ coi “không có dữ liệu” là một kết quả bình thường.

Trong Reactive Streams, `onComplete` là tín hiệu kết thúc thành công và không mang payload. `onError` là tín hiệu kết thúc lỗi và mang exception. `onNext` mới mang phần tử dữ liệu. Vì vậy, “Publisher hoàn tất” và “Publisher phát một giá trị” là hai điều kiện riêng.

## Mono<Void> biểu diễn thao tác không phát dữ liệu

`Void` trong Java là kiểu tham chiếu không có instance thông thường để phát làm kết quả. Một `Mono<Void>` thường chỉ phát tín hiệu hoàn tất hoặc lỗi:

~~~java
Mono<Void> deleteCustomer(String customerId) {
    return customerRepository.deleteById(customerId);
}
~~~

Hợp đồng của phương thức nói rằng caller có thể chờ thao tác xóa kết thúc và xử lý lỗi nếu có. Caller không nhận được một `Customer` hoặc một giá trị `Void` qua `onNext`.

Đây là cách khai báo hợp lý cho các thao tác như:

- Xóa bản ghi.
- Gửi một thông báo mà caller chỉ cần biết thao tác đã hoàn tất.
- Ghi audit hoặc cập nhật một trạng thái không cần trả payload.
- Thực thi một command mà kết quả nghiệp vụ không có phần tử đầu ra.

Không nên tạo `Mono<Void>` chỉ vì muốn bỏ qua một kết quả đang có ích. Nếu caller cần biết bản ghi nào đã xóa, số hàng được cập nhật hoặc mã giao dịch, hãy giữ kiểu kết quả đó trong hợp đồng:

~~~java
Mono<Long> deleteCustomer(String customerId) {
    return database.sql("delete from customer where id = :id")
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Ở ví dụ này, `Mono<Long>` phát số hàng bị ảnh hưởng. Nếu đổi thành `Mono<Void>`, thông tin đó sẽ bị loại bỏ.

## Vì sao flatMap không chạy với Mono<Void>?

`flatMap` cần một phần tử `onNext` để gọi hàm ánh xạ. Khi nguồn hoàn tất rỗng, không có giá trị để truyền vào lambda:

~~~java
Mono<Void> deleted = deleteCustomer(customerId);

Mono<String> result = deleted.flatMap(ignored ->
    Mono.just("deleted")
);
~~~

Lambda trong `flatMap` không được gọi vì `deleted` chỉ phát `onComplete`. `result` cũng hoàn tất rỗng. Đây là hành vi đúng theo hợp đồng của `flatMap`, không phải lỗi scheduler hay lỗi subscription.

Nếu chỉ cần chạy bước kế tiếp sau khi thao tác hoàn tất, dùng `then`:

~~~java
Mono<String> result = deleted.then(
    Mono.just("delete-request-finished")
);
~~~

Nếu cần phát một giá trị cố định sau khi thao tác hoàn tất, dùng `thenReturn`:

~~~java
Mono<String> result = deleted.thenReturn("deleted");
~~~

`then` và `thenReturn` bỏ qua các phần tử của Publisher trước đó, chờ Publisher đó hoàn tất bình thường rồi mới tiếp tục. Nếu Publisher trước phát lỗi, lỗi được truyền xuống và Publisher kế tiếp không được chạy. Nếu subscription bị hủy trước khi hoàn tất, bước kế tiếp cũng không được khởi chạy.

## Phân biệt then, thenReturn và flatMap

Ba toán tử thường bị dùng nhầm khi viết chuỗi thao tác:

| Toán tử | Điều kiện chạy bước tiếp theo | Kết quả |
|---|---|---|
| `flatMap(value -> next(value))` | Nguồn phát một giá trị | Phát kết quả của Publisher được tạo từ giá trị đó |
| `then(nextPublisher)` | Nguồn hoàn tất bình thường, có hoặc không có giá trị | Phát kết quả của Publisher kế tiếp |
| `thenReturn(value)` | Nguồn hoàn tất bình thường | Phát giá trị cố định rồi hoàn tất |

Ví dụ với một đơn hàng:

~~~java
Mono<Order> order = orderRepository.findById(orderId);

// Cần giá trị Order để quyết định bước kế tiếp.
Mono<Invoice> invoice = order.flatMap(
    foundOrder -> invoiceService.create(foundOrder)
);

// Chỉ cần đợi thao tác xóa hoàn tất, rồi phát thông báo cố định.
Mono<String> deleteMessage = orderRepository.deleteById(orderId)
    .thenReturn("delete completed");
~~~

`flatMap` phù hợp khi bước tiếp theo phụ thuộc vào dữ liệu được phát. `then` phù hợp khi quan hệ chỉ là thứ tự hoàn tất. Dùng `thenReturn` khi sau thao tác không có payload, nhưng tầng gọi vẫn cần một giá trị xác nhận do ứng dụng định nghĩa.

Nếu cần giữ lại giá trị ban đầu qua một thao tác `Mono<Void>`, hãy giữ nó trong lambda và phát lại sau khi thao tác hoàn tất:

~~~java
Mono<Order> reserveAndKeepOrder(Order order) {
    return inventoryService.reserve(order)
        .thenReturn(order);
}
~~~

Ở đây `reserve` chỉ báo hoàn tất. `thenReturn(order)` phát lại đối tượng `order` sau khi reserve thành công. Nếu reserve lỗi, `order` không được phát xuống như thể thao tác đã thành công.

## then không chạy song song

`then` tạo thứ tự: Publisher đầu tiên phải hoàn tất trước khi Publisher kế tiếp được subscribe. Ví dụ:

~~~java
Mono<Void> sequential = writeOrder(order)
    .then(writeAudit(order));
~~~

`writeAudit` chỉ bắt đầu sau khi `writeOrder` hoàn tất bình thường. Đây là lựa chọn phù hợp nếu audit cần ghi sau khi lệnh ghi đơn hàng đã hoàn tất hoặc nếu bước sau phụ thuộc vào side effect của bước trước.

Nếu hai thao tác độc lập và có thể chạy đồng thời, dùng `Mono.when`:

~~~java
Mono<Void> bothCompleted = Mono.when(
    refreshSearchIndex(order),
    publishMetrics(order),
    writeAudit(order)
);
~~~

`Mono.when` subscribe các nguồn và hoàn tất khi tất cả hoàn tất bình thường. Nó trả về `Mono<Void>` vì mục tiêu là phối hợp tín hiệu hoàn tất, không kết hợp payload. Nếu một nguồn phát lỗi, `when` có thể kết thúc lỗi và hủy các nguồn còn lại; dùng `whenDelayError` nếu cần chờ các nguồn kết thúc rồi mới tổng hợp lỗi theo hợp đồng của toán tử.

Muốn phát một kết quả sau khi tất cả thao tác độc lập hoàn tất:

~~~java
Mono<Receipt> result = Mono.when(
        writeAudit(order),
        refreshSearchIndex(order)
    )
    .thenReturn(receipt);
~~~

`receipt` chỉ được phát sau khi tất cả Publisher trong `when` hoàn tất bình thường. Không dùng `when` nếu các thao tác cần chạy tuần tự hoặc phụ thuộc dữ liệu đầu ra của nhau.

## Vì sao zip không kết hợp được Mono<Void>?

`zip` cần mỗi nguồn phát một phần tử để tạo tuple hoặc gọi hàm kết hợp. `Mono<Void>` hoàn tất mà không phát phần tử, vì vậy nó không cung cấp giá trị cho `zip`:

~~~java
Mono<Tuple2<Customer, Void>> combined = Mono.zip(
    customerRepository.findById(customerId),
    writeAudit(customerId)
);
~~~

Publisher audit không phát `onNext`. Do đó, `zip` không thể tạo `Tuple2` và kết quả kết hợp hoàn tất rỗng (hoặc kết thúc theo lỗi nếu một nguồn lỗi). Lambda kết hợp không chạy.

Không nên dùng `zip` để diễn đạt “đợi cả hai thao tác xong”. Hãy dùng `Mono.when` cho yêu cầu đó:

~~~java
Mono<Void> completed = Mono.when(
    customerRepository.updateStatus(customerId, "ACTIVE"),
    writeAudit(customerId)
);
~~~

`zip` dành cho việc kết hợp các giá trị; `when` dành cho việc phối hợp các tín hiệu hoàn tất. Đây là khác biệt quan trọng nhất khi một trong các nguồn có kiểu `Mono<Void>`.

Một điểm cần lưu ý: khi một nguồn trong `zip` hoàn tất rỗng, toán tử có thể kết thúc sớm và hủy các nguồn khác. Với các cấu trúc `zip` lồng nhau, việc short-circuit còn có thể khiến một số Publisher không được subscribe. Không đặt side effect bắt buộc vào một nguồn chỉ với giả định rằng `zip` chắc chắn sẽ subscribe và chạy mọi nguồn. Nếu mọi thao tác cần được thực thi, hãy phối hợp bằng `when` hoặc tạo một pipeline tuần tự tường minh.

## Khi cần cả giá trị và thao tác không phát giá trị

Một trường hợp phổ biến là cần tải khách hàng, đồng thời ghi audit, rồi trả khách hàng:

~~~java
Mono<Customer> customerWithAudit(String customerId) {
    return customerRepository.findById(customerId)
        .flatMap(customer ->
            writeAudit(customer.id())
                .thenReturn(customer)
        );
}
~~~

`flatMap` bên ngoài cần một `Customer` để bắt đầu audit. `writeAudit` trả `Mono<Void>`, vì vậy `thenReturn(customer)` giữ lại dữ liệu đã có sau khi audit hoàn tất.

Nếu hai nguồn phát giá trị và cả hai giá trị đều cần cho bước sau, dùng `zip`:

~~~java
Mono<CustomerView> view = Mono.zip(
        customerRepository.findById(customerId),
        preferenceRepository.findByCustomerId(customerId)
    )
    .map(tuple -> CustomerView.from(
        tuple.getT1(),
        tuple.getT2()
    ));
~~~

Nếu một nguồn có thể không có dữ liệu, `zip` thông thường sẽ hoàn tất rỗng khi không thể tạo đủ giá trị. Cần quyết định rõ nghiệp vụ muốn bỏ kết quả, dùng giá trị mặc định hay giữ trạng thái “không có”.

## Kết hợp các giá trị tùy chọn mà không làm mất trạng thái rỗng

Giả sử khách hàng có thể không có cấu hình tùy chọn. Nếu thay giá trị rỗng bằng một đối tượng mặc định, downstream có thể nhầm “không có cấu hình” với “có cấu hình mặc định”. Có thể dùng `singleOptional()` để biến cả trường hợp có và không có phần tử thành một phần tử `Optional`:

~~~java
Mono<CustomerView> view = Mono.zip(
        customerRepository.findById(customerId).singleOptional(),
        preferenceRepository.findByCustomerId(customerId).singleOptional()
    )
    .map(tuple -> CustomerView.from(
        tuple.getT1(),
        tuple.getT2()
    ));
~~~

Khi repository không tìm thấy dữ liệu, `singleOptional()` phát `Optional.empty()` thay vì hoàn tất rỗng. Vì mỗi nguồn lúc này phát một `Optional`, `zip` có thể tạo tuple. Hàm `CustomerView.from` có thể phân biệt rõ có dữ liệu và không có dữ liệu.

Một cách khác là `defaultIfEmpty` hoặc `switchIfEmpty`, nhưng chỉ dùng giá trị mặc định khi nghiệp vụ xác định rõ ý nghĩa của nó. Không dùng một giá trị sentinel có thể trùng với dữ liệu hợp lệ.

`singleOptional()` phù hợp với `Mono<T>` có thể rỗng. Nó không tạo một giá trị `Void` cho `Mono<Void>`; với thao tác chỉ báo hoàn tất, hãy dùng `when`, `then` hoặc `thenReturn` tùy mục tiêu.

## switchIfEmpty không kiểm tra thành công của Mono<Void>

Đây là một lỗi dễ gây side effect ngoài ý muốn:

~~~java
Mono<Void> saved = repository.saveAudit(event);

Mono<Void> pipeline = saved.switchIfEmpty(
    writeFallbackAudit(event)
);
~~~

Nếu `saved` hoàn tất thành công, nó vẫn không phát phần tử nào. Vì vậy, `switchIfEmpty` xem đó là hoàn tất rỗng và subscribe `writeFallbackAudit`. Fallback có thể chạy sau một thao tác đã thành công.

`switchIfEmpty` có ý nghĩa với `Mono<T>` mà việc có hoặc không có giá trị mang ý nghĩa nghiệp vụ, chẳng hạn tìm kiếm bản ghi:

~~~java
Mono<Customer> customer = customerRepository.findById(customerId)
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(customerId)
    ));
~~~

Với `Mono<Void>`, nếu cần hành động sau khi thành công, dùng `then`. Nếu cần giá trị xác nhận, dùng `thenReturn`. Nếu cần xử lý lỗi, dùng `onErrorResume` hoặc `onErrorMap`; không dùng `switchIfEmpty` để nhận diện thành công của một thao tác không phát payload.

## doOnSuccess có thể nhận null khi Mono rỗng

`Mono.doOnSuccess` được gọi khi Mono hoàn tất thành công. Nếu Mono có giá trị, callback nhận giá trị đó; nếu Mono hoàn tất rỗng, callback nhận `null`. Trong khi đó, `doOnNext` chỉ chạy khi có phần tử:

~~~java
Mono<Void> delete = repository.deleteById(customerId)
    .doOnSuccess(ignored ->
        log.info("delete completed"));
~~~

Với `Mono<Void>`, tham số `ignored` sẽ là `null` khi hoàn tất thành công. Đừng gọi phương thức trên tham số này:

~~~java
// Sai: ignored là null với Mono<Void>.
delete.doOnSuccess(value -> log.info("result={}", value.toString()));
~~~

Nếu chỉ cần ghi log rằng thao tác đã hoàn tất, dùng `doOnSuccess(ignored -> ...)` mà không đọc giá trị. `doOnTerminate` quan sát complete hoặc error, còn `doFinally` quan sát cả complete, error và cancel. Hãy nhớ `doOnSuccess` không chạy khi Publisher phát lỗi.

## Chọn hợp đồng trả về cho service

Kiểu trả về nên mô tả đúng thứ mà caller cần:

| Nhu cầu | Kiểu trả về phù hợp | Lý do |
|---|---|---|
| Chỉ cần biết thao tác hoàn tất hoặc lỗi | `Mono<Void>` | Không có payload nghiệp vụ |
| Cần trả lại bản ghi đã lưu | `Mono<Entity>` | Caller cần dữ liệu sau thao tác |
| Cần số hàng bị ảnh hưởng | `Mono<Long>` hoặc kiểu số phù hợp | Kết quả có ý nghĩa nghiệp vụ |
| Cần biểu diễn có/không có một kết quả | `Mono<T>` rỗng hoặc `Mono<Optional<T>>` | Phân biệt không có dữ liệu với một giá trị |
| Cần đợi nhiều thao tác độc lập hoàn tất | `Mono.when(...)` | Chỉ phối hợp complete/error |
| Cần kết hợp nhiều kết quả | `Mono.zip(...)` | Mỗi nguồn phải phát một giá trị |
| Cần chạy bước sau sau khi thao tác hoàn tất | `then(...)` | Quan hệ theo thứ tự, không cần payload trước |

Đừng đổi `Mono<Entity>` thành `Mono<Void>` chỉ để tránh ánh xạ dữ liệu nếu tầng gọi đang cần entity. Ngược lại, đừng phát một đối tượng giả chỉ để `zip` hoạt động nếu nghiệp vụ thực chất chỉ cần chờ hoàn tất.

## Kiểm thử khác biệt bằng StepVerifier

Kiểm thử nên xác nhận rõ một Mono phát giá trị hay hoàn tất rỗng:

~~~java
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();

StepVerifier.create(Mono.just("saved"))
    .expectNext("saved")
    .verifyComplete();

StepVerifier.create(Mono.<String>error(
        new IllegalStateException("failed")))
    .expectErrorMessage("failed")
    .verify();
~~~

Kiểm tra `flatMap` không chạy với `Mono<Void>`:

~~~java
AtomicBoolean called = new AtomicBoolean();

Mono<String> result = Mono.<Void>empty()
    .flatMap(ignored -> {
        called.set(true);
        return Mono.just("next");
    });

StepVerifier.create(result)
    .verifyComplete();

assertFalse(called.get());
~~~

Kiểm tra `thenReturn` phát giá trị sau khi thao tác hoàn tất:

~~~java
Mono<String> result = Mono.<Void>empty()
    .thenReturn("completed");

StepVerifier.create(result)
    .expectNext("completed")
    .verifyComplete();
~~~

Kiểm tra `when` chờ các thao tác hoàn tất:

~~~java
Mono<Void> both = Mono.when(
    Mono.delay(Duration.ofMillis(10)).then(),
    Mono.delay(Duration.ofMillis(20)).then()
);

StepVerifier.create(both)
    .verifyComplete();
~~~

Kiểm tra `zip` với nguồn rỗng không gọi hàm kết hợp:

~~~java
AtomicBoolean combinatorCalled = new AtomicBoolean();

Mono<String> zipped = Mono.zip(
    Mono.<String>empty(),
    Mono.just("value"),
    (left, right) -> {
        combinatorCalled.set(true);
        return left + right;
    }
);

StepVerifier.create(zipped)
    .verifyComplete();

assertFalse(combinatorCalled.get());
~~~

Các test này không cần `block()` hoặc `Thread.sleep`. Với trường hợp cần kiểm tra thời gian, dùng `StepVerifier.withVirtualTime` và nguồn thời gian tương thích để điều khiển đồng hồ ảo.

## Những lỗi thường gặp

| Cách làm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `flatMap` sau `Mono<Void>` | Lambda không chạy vì không có `onNext` | Dùng `then` hoặc `thenReturn` |
| Dùng `zip` để đợi `Mono<Void>` | Không tạo được tuple vì thiếu giá trị | Dùng `Mono.when` |
| Dùng `switchIfEmpty` để kiểm tra thao tác void thành công | Fallback cũng chạy sau complete rỗng bình thường | Dùng `then` hoặc `thenReturn` |
| Gọi `toString()` trong `doOnSuccess` của `Mono<Void>` | Callback nhận `null` và có thể ném NPE | Không đọc payload; dùng hook phù hợp |
| Dùng `then` khi cần dữ liệu nguồn | Giá trị upstream bị bỏ | Dùng `flatMap`, `map` hoặc giữ lại giá trị bằng `thenReturn` |
| Dùng `when` cho các bước phụ thuộc nhau | Các thao tác được subscribe độc lập, có thể chạy đồng thời | Nối tuần tự bằng `then` hoặc `flatMap` |
| Phát giá trị sentinel để ép `zip` | Downstream có thể nhầm sentinel với dữ liệu thật | Dùng `Optional` hoặc thiết kế kiểu kết quả rõ ràng |
| Gọi `subscribe()` bên trong service để “chạy cho xong” | Tách side effect khỏi pipeline và mất điều phối lỗi/cancel | Trả Publisher để tầng sở hữu subscription điều khiển |

## Nguyên tắc phối hợp Publisher

Trước khi ghép các thao tác `Mono`, hãy hỏi:

1. Mỗi nguồn có phát một giá trị hay chỉ hoàn tất?
2. Bước tiếp theo cần dữ liệu từ `onNext` hay chỉ cần chờ complete?
3. Các thao tác phải chạy tuần tự hay có thể chạy đồng thời?
4. Khi một nguồn rỗng, nghiệp vụ muốn bỏ kết quả, dùng Optional, hay phát giá trị mặc định?
5. Nếu một thao tác lỗi hoặc bị cancel, các thao tác còn lại cần được xử lý thế nào?
6. Kiểu trả về của service có thể hiện đúng dữ liệu mà caller cần không?
7. Kiểm thử đã phân biệt complete rỗng, complete có giá trị, error và cancel chưa?

Hoàn tất rỗng là một kết quả hợp lệ của reactive stream. `Mono<Void>` biểu diễn thao tác không phát payload; `then` và `when` phối hợp tín hiệu hoàn tất, còn `thenReturn` tạo một giá trị sau khi hoàn tất thành công. `flatMap` và `zip` cần giá trị thực sự được phát. Chọn toán tử theo hợp đồng này giúp tránh bỏ qua bước xử lý, kích hoạt fallback sai và làm mất dữ liệu cần thiết cho nghiệp vụ.
