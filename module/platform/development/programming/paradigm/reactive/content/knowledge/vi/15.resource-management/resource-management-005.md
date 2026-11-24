# Lỗi trong lúc dọn dẹp và quan hệ với lỗi nghiệp vụ

Một thao tác reactive có thể thất bại khi đang sử dụng tài nguyên, chẳng hạn truy vấn cơ sở dữ liệu, đọc tệp hoặc gọi dịch vụ bên ngoài. Sau khi thao tác kết thúc, ứng dụng còn phải đóng kết nối, trả buffer về pool hoặc giải phóng tài nguyên. Chính bước dọn dẹp cũng có thể thất bại. Khi cả thao tác chính và dọn dẹp đều phát sinh lỗi, pipeline cần một quy tắc rõ ràng để giữ lại nguyên nhân quan trọng và không làm mất thông tin chẩn đoán.

Bài học thuộc chương **Tài nguyên** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Với Project Reactor, các API **using**, **usingWhen** và **doFinally** có vai trò khác nhau trong việc quản lý tài nguyên và xử lý lỗi khi kết thúc subscription.

## Hai công việc có thể cùng thất bại

Hãy xem một thao tác cập nhật đơn hàng trong transaction:

1. Ứng dụng lấy kết nối và bắt đầu transaction.
2. Câu lệnh cập nhật thất bại do vi phạm ràng buộc dữ liệu.
3. Ứng dụng rollback transaction và đóng kết nối.
4. Rollback hoặc đóng kết nối cũng có thể thất bại, chẳng hạn do mất kết nối mạng.

Lúc này có ít nhất hai lỗi:

- **Lỗi nghiệp vụ hoặc lỗi thao tác chính:** nguyên nhân khiến công việc không hoàn thành, ví dụ **OrderUpdateException** hoặc lỗi constraint từ database.
- **Lỗi dọn dẹp:** lỗi xảy ra khi rollback, đóng kết nối hoặc giải phóng tài nguyên.

Nếu chỉ truyền lỗi dọn dẹp xuống downstream, người gọi có thể không còn thấy nguyên nhân khiến thao tác ban đầu thất bại. Nếu chỉ giữ lỗi nghiệp vụ và bỏ qua lỗi dọn dẹp, hệ thống có thể che giấu tình trạng rò rỉ kết nối hoặc tài nguyên. Một hợp đồng lỗi tốt cần xác định lỗi nào là nguyên nhân chính, lỗi nào là thông tin bổ sung và cách quan sát cả hai.

## Quan hệ giữa lỗi chính và lỗi dọn dẹp trong Java

Java try-with-resources có quy tắc cụ thể khi cả phần thân và thao tác đóng tài nguyên đều ném exception. Exception từ phần thân được giữ làm lỗi chính; exception phát sinh khi đóng tài nguyên được thêm vào danh sách **suppressed exceptions** của lỗi chính.

~~~java
try (Connection connection = dataSource.getConnection()) {
    updateOrder(connection);
}
~~~

Nếu **updateOrder** ném **OrderUpdateException** và **connection.close()** cũng thất bại, exception được ném ra vẫn là **OrderUpdateException**. Có thể truy cập lỗi đóng kết nối bằng **getSuppressed()**:

~~~java
try {
    updateOrderWithResource();
} catch (OrderUpdateException error) {
    for (Throwable cleanupError : error.getSuppressed()) {
        logger.warn("Dọn dẹp tài nguyên thất bại", cleanupError);
    }
}
~~~

Quy tắc này giữ lỗi làm thất bại nghiệp vụ ở vị trí chính, đồng thời không làm mất lỗi đóng tài nguyên. Tuy nhiên, đây là hành vi của try-with-resources trong Java. Khi chuyển sang Reactor, không nên giả định mọi API quản lý tài nguyên đều tự động áp dụng đúng quy tắc suppressed exception này. Cần hiểu chính sách của từng API và chủ động định nghĩa khi cần.

## Quản lý tài nguyên đồng bộ bằng using

**Mono.using** và **Flux.using** gắn vòng đời của một tài nguyên đồng bộ với subscription:

~~~java
Mono<Order> order = Mono.using(
    () -> resourceFactory.open(),
    resource -> orderRepository.load(resource, orderId),
    Resource::close,
    true
);
~~~

Ba hàm có trách nhiệm riêng:

1. Resource supplier tạo hoặc mở tài nguyên khi có subscription.
2. Source factory sử dụng tài nguyên và trả về **Mono** hoặc **Flux**.
3. Resource cleanup giải phóng tài nguyên khi quá trình sử dụng kết thúc hoặc bị hủy.

Tham số cuối **true** yêu cầu cleanup theo chế độ eager: dọn dẹp trước khi chuyển tín hiệu kết thúc xuống downstream. Với chế độ này, nếu cleanup ném exception, lỗi cleanup có thể thay thế tín hiệu kết thúc ban đầu. Điều này có nghĩa là lỗi từ thao tác chính có thể không còn là exception trực tiếp mà downstream nhận được.

Có thể truyền **false** để dùng chế độ non-eager:

~~~java
Mono<Order> order = Mono.using(
    () -> resourceFactory.open(),
    resource -> orderRepository.load(resource, orderId),
    Resource::close,
    false
);
~~~

Ở chế độ non-eager, tín hiệu kết thúc của nguồn được chuyển xuống trước, rồi cleanup mới được thực hiện. Vì downstream đã nhận tín hiệu kết thúc, lỗi phát sinh sau đó trong cleanup không thể thay thế tín hiệu đã gửi; lỗi cleanup có thể bị Reactor đưa vào cơ chế xử lý lỗi bị loại bỏ (dropped error). Cách này không phù hợp nếu ứng dụng cần báo cho người gọi rằng thao tác đóng tài nguyên thất bại.

Với cleanup có ý nghĩa vận hành, hãy chọn eager mode và xác định rõ cách kết hợp lỗi. Đừng chọn non-eager chỉ để tránh nhìn thấy lỗi dọn dẹp; hãy ghi nhận lỗi đó bằng cơ chế quan sát phù hợp nếu chính sách thực sự yêu cầu tín hiệu nghiệp vụ được gửi trước.

## Khi cleanup đồng bộ thất bại

Giả sử thao tác chính phát lỗi **OrderUpdateException**, còn **Resource.close()** ném **ResourceCloseException**. Với **using** ở chế độ eager, cleanup được thực hiện trước tín hiệu kết thúc nên lỗi cleanup có thể trở thành lỗi downstream. Nếu ứng dụng cần giữ lỗi nghiệp vụ làm lỗi chính, hãy bọc hoặc kết hợp hai lỗi theo chính sách đã chọn thay vì trông chờ **using** tự tạo suppressed exception.

Một kiểu exception có thể biểu diễn cả hai:

~~~java
public final class ResourceCleanupException extends RuntimeException {
    public ResourceCleanupException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Nếu quyết định ưu tiên lỗi cleanup, có thể giữ lỗi thao tác chính làm suppressed:

~~~java
RuntimeException cleanupError =
    new ResourceCleanupException("Không thể đóng tài nguyên", closeFailure);

cleanupError.addSuppressed(operationError);
~~~

Nếu nghiệp vụ yêu cầu lỗi thao tác chính vẫn là lỗi chính, hãy thêm lỗi cleanup làm suppressed:

~~~java
operationError.addSuppressed(cleanupError);
~~~

Hai cách biểu diễn mang ý nghĩa khác nhau. Chọn lỗi chính theo câu hỏi mà tầng gọi cần trả lời: “Thao tác thất bại vì điều gì?” hay “Tài nguyên không thể được giải phóng?”. Dù chọn cách nào, hãy giữ cả hai đối tượng exception để có thể chẩn đoán.

Không nên thêm cùng một đối tượng exception làm suppressed cho chính nó; Java sẽ ném **IllegalArgumentException** trong trường hợp tự suppression. Khi kết hợp lỗi động, kiểm tra danh tính exception trước khi gọi **addSuppressed**.

## Quản lý tài nguyên bất đồng bộ bằng usingWhen

Một số tài nguyên cần được giải phóng bằng thao tác bất đồng bộ, ví dụ transaction reactive, session hoặc connection có API trả về **Publisher**. Dùng **using** trong trường hợp này không đủ vì cleanup đồng bộ không thể chờ một Publisher hoàn tất. **Mono.usingWhen** và **Flux.usingWhen** cho phép định nghĩa cleanup bất đồng bộ riêng cho ba tình huống: hoàn tất, lỗi và cancellation.

~~~java
Mono<Order> order = Mono.usingWhen(
    connectionFactory.create(),
    connection -> orderRepository.load(connection, orderId),
    connection -> connection.commitAndClose(),
    (connection, operationError) -> connection.rollbackAndClose(),
    connection -> connection.rollbackAndClose()
);
~~~

Các nhánh cleanup tương ứng:

| Tình huống của Publisher sử dụng tài nguyên | Hàm cleanup | Mục đích thường gặp |
|---|---|---|
| Hoàn tất bình thường | **asyncComplete** | Commit transaction rồi đóng connection |
| Kết thúc bằng lỗi | **asyncError** | Rollback transaction rồi đóng connection |
| Bị hủy subscription | **asyncCancel** | Hủy hoặc rollback thao tác đang mở rồi giải phóng connection |

**usingWhen** chờ Publisher cleanup tương ứng hoàn tất trước khi phát tín hiệu kết thúc cho trường hợp complete hoặc error. Vì cleanup là một phần của đường kết thúc, lỗi trong Publisher cleanup cũng ảnh hưởng đến kết quả cuối. Nếu cleanup khi hoàn tất thất bại, downstream nhận lỗi cleanup thay vì **onComplete**. Nếu cleanup khi xử lý lỗi thất bại, lỗi cleanup có thể trở thành lỗi cuối cùng; hãy chủ động giữ lỗi thao tác ban đầu nếu đó là lỗi cần ưu tiên.

Với cancellation, downstream đã chủ động hủy và không còn nhận tín hiệu kết thúc. Cleanup vẫn cần được thực hiện, nhưng lỗi phát sinh trong nhánh cleanup này không thể gửi ngược thành **onError** cho Subscriber đã hủy. Hãy quan sát lỗi cleanup bằng log, metric hoặc cơ chế cảnh báo vận hành.

## Giữ lỗi nghiệp vụ làm lỗi chính khi cleanup bất đồng bộ thất bại

Nếu chính sách yêu cầu giữ lỗi thao tác chính và bổ sung lỗi rollback như suppressed, có thể xử lý lỗi cleanup ngay trong hàm **asyncError**:

~~~java
Mono<Order> order = Mono.usingWhen(
    connectionFactory.create(),
    connection -> orderRepository.update(connection, orderId),
    connection -> connection.commitAndClose(),
    (connection, operationError) ->
        connection.rollbackAndClose()
            .onErrorResume(cleanupError -> {
                if (cleanupError != operationError) {
                    operationError.addSuppressed(cleanupError);
                }
                return Mono.empty();
            }),
    connection -> connection.rollbackAndClose()
);
~~~

Trong ví dụ này:

1. Nếu thao tác thành công, nhánh **asyncComplete** commit và đóng tài nguyên. Nếu cleanup thành công, kết quả được phát bình thường; nếu cleanup thất bại, lỗi cleanup được phát xuống.
2. Nếu thao tác thất bại, nhánh **asyncError** thử rollback và đóng tài nguyên.
3. Nếu cleanup trong nhánh lỗi cũng thất bại, lỗi cleanup được gắn vào **operationError** bằng **addSuppressed**, sau đó cleanup Publisher hoàn tất bình thường để **usingWhen** truyền lỗi thao tác chính xuống.
4. Nếu bị cancel, nhánh **asyncCancel** chạy cleanup; cần thêm quan sát lỗi riêng vì Subscriber đã hủy.

Đây là một chính sách ưu tiên lỗi nghiệp vụ. Trong ứng dụng thực tế, nên tách rollback và close thành các bước có kiểm soát để việc rollback thất bại không ngăn nỗ lực đóng connection. Nếu cả rollback lẫn close đều có thể lỗi, cần thu thập cả hai lỗi, chọn lỗi chính và gắn các lỗi còn lại làm suppressed theo cùng nguyên tắc.

## doFinally không thay thế cơ chế quản lý tài nguyên

**doFinally** được gọi khi pipeline kết thúc bằng complete, error hoặc cancel. Nó phù hợp để ghi metric, giải phóng trạng thái quan sát nhẹ hoặc ghi nhận nguyên nhân kết thúc:

~~~java
Mono<Order> order = orderRepository.load(orderId)
    .doFinally(signalType ->
        metrics.recordOrderPipelineTermination(signalType)
    );
~~~

Callback của **doFinally** chạy sau khi tín hiệu kết thúc đã được chuyển xuống downstream. Vì vậy, nó không thể trì hoãn tín hiệu để chờ cleanup bất đồng bộ, cũng không thể thay thế **onComplete** hoặc **onError** bằng một lỗi cleanup. Nếu callback ném exception, lỗi đó không trở thành lỗi nghiệp vụ của pipeline; nó được xử lý như lỗi phát sinh trong tác vụ phụ.

Đối với tài nguyên cần được giải phóng chắc chắn, hãy dùng **using** hoặc **usingWhen**. Dùng **doFinally** để quan sát **SignalType.CANCEL**, **SignalType.ON_ERROR** và **SignalType.ON_COMPLETE**, không dùng nó làm nơi duy nhất đóng connection hoặc transaction.

## Kiểm thử thứ tự ưu tiên lỗi bằng StepVerifier

Kiểm thử cần bao gồm cả trường hợp thao tác chính thành công nhưng cleanup thất bại và trường hợp cả hai cùng thất bại. Ví dụ dưới đây dùng một resource đơn giản có cleanup ném lỗi:

~~~java
RuntimeException cleanupFailure =
    new IllegalStateException("close failed");

Mono<String> source = Mono.using(
    TestResource::new,
    resource -> Mono.just("saved"),
    resource -> {
        throw cleanupFailure;
    },
    true
);

StepVerifier.create(source)
    .expectNext("saved")
    .expectErrorSatisfies(error ->
        assertSame(cleanupFailure, error)
    )
    .verify();
~~~

Với eager cleanup, thao tác chính tạo ra giá trị nhưng cleanup thất bại trước khi tín hiệu hoàn tất được gửi xuống. Kiểm thử xác nhận lỗi cleanup trở thành lỗi downstream.

Để kiểm tra chính sách giữ lỗi nghiệp vụ và gắn lỗi cleanup làm suppressed, có thể kiểm thử hàm kết hợp lỗi riêng:

~~~java
RuntimeException operationFailure =
    new IllegalStateException("update failed");
RuntimeException cleanupFailure =
    new IllegalStateException("rollback failed");

Mono<String> source = Mono.<String>error(operationFailure)
    .onErrorResume(error -> {
        if (cleanupFailure != error) {
            error.addSuppressed(cleanupFailure);
        }
        return Mono.error(error);
    });

StepVerifier.create(source)
    .expectErrorSatisfies(error -> {
        assertSame(operationFailure, error);
        assertEquals(1, error.getSuppressed().length);
        assertSame(cleanupFailure, error.getSuppressed()[0]);
    })
    .verify();
~~~

Ví dụ thứ hai kiểm tra chính sách kết hợp lỗi: lỗi thao tác chính được giữ nguyên, lỗi cleanup được thêm vào suppressed. Trong pipeline dùng **usingWhen**, đặt logic tương tự trong nhánh **asyncError** như ví dụ trước.

Có thể kiểm tra cancellation cleanup bằng một cờ:

~~~java
AtomicBoolean released = new AtomicBoolean();

Mono<String> source = Mono.usingWhen(
    Mono.just(new TestResource()),
    resource -> Mono.<String>never(),
    resource -> Mono.fromRunnable(() -> released.set(true)),
    (resource, error) -> Mono.fromRunnable(() -> released.set(true)),
    resource -> Mono.fromRunnable(() -> released.set(true))
);

StepVerifier.create(source)
    .thenCancel()
    .verify();

assertTrue(released.get());
~~~

Kiểm thử này xác nhận cancellation kích hoạt nhánh cleanup dành riêng. Nếu cleanup có thể thất bại, hãy kiểm tra thêm rằng lỗi được ghi nhận qua metric hoặc log theo chính sách vận hành.

## Những lỗi thường gặp

| Cách làm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng cleanup không thể thất bại | Bỏ sót rò rỉ connection hoặc lỗi giải phóng tài nguyên | Mô hình hóa cleanup như một thao tác có thể phát lỗi |
| Dùng **using** cho cleanup bất đồng bộ | Không chờ Publisher cleanup hoàn tất | Dùng **usingWhen** |
| Dùng eager cleanup nhưng không xác định lỗi nào được ưu tiên | Lỗi cleanup có thể che khuất lỗi thao tác | Thiết kế chính sách cause/suppressed rõ ràng |
| Dùng non-eager cleanup để bỏ qua lỗi | Lỗi cleanup có thể bị dropped sau tín hiệu kết thúc | Quan sát lỗi hoặc dùng cleanup eager khi cần báo lỗi |
| Dùng **doFinally** để đóng tài nguyên quan trọng | Không chờ cleanup và không thể thay đổi tín hiệu kết thúc | Dùng **using** hoặc **usingWhen** |
| Bỏ qua cleanup khi cancel | Resource có thể bị giữ lại sau khi Subscriber ngừng chờ | Định nghĩa nhánh **asyncCancel** và kiểm thử cancellation |
| Chỉ giữ lỗi cleanup hoặc chỉ giữ lỗi nghiệp vụ | Mất một phần thông tin chẩn đoán | Chọn lỗi chính và lưu lỗi còn lại dưới dạng suppressed |

## Nguyên tắc thiết kế

Khi thiết kế vòng đời tài nguyên cho pipeline reactive, hãy xác định:

1. Tài nguyên được giải phóng bằng API đồng bộ hay Publisher bất đồng bộ?
2. Cleanup phải chạy khi complete, error và cancel như thế nào?
3. Nếu thao tác chính và cleanup cùng lỗi, lỗi nào là lỗi chính theo hợp đồng nghiệp vụ?
4. Lỗi phụ được lưu trong **cause**, **suppressed** hay một bản ghi vận hành riêng?
5. Nếu cleanup khi cancel thất bại, hệ thống quan sát sự cố bằng cách nào khi downstream không còn nhận tín hiệu?
6. Kiểm thử có bao phủ thành công, lỗi thao tác, lỗi cleanup và cancellation không?

Quản lý tài nguyên trong reactive không dừng ở việc gọi **close()** hoặc **rollback()**. Cleanup là một phần của vòng đời subscription và có thể ảnh hưởng trực tiếp đến tín hiệu kết thúc. Khi chọn đúng **using** hoặc **usingWhen**, xác định rõ thứ tự ưu tiên lỗi và kiểm thử cả các nhánh cleanup, pipeline sẽ giữ được thông tin nghiệp vụ lẫn dấu vết cần thiết để xử lý sự cố.
