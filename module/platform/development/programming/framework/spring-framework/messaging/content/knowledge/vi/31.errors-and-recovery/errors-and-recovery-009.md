# Thử nghiệm mất kết nối, hết tài nguyên và thông điệp không hợp lệ

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt lỗi transport, lỗi của một message stream, lỗi nghiệp vụ và lỗi do hệ thống quá tải.
- Thiết kế test tái hiện mất kết nối có kiểm soát, bao gồm đóng bình thường và ngắt đột ngột.
- Kiểm tra giới hạn concurrency, buffer, kích thước payload và khả năng từ chối công việc khi hết tài nguyên.
- Kiểm tra message sai định dạng, thiếu dữ liệu hoặc vi phạm quy tắc validation.
- Xác nhận publisher kết thúc đúng tín hiệu, tài nguyên được giải phóng và chính sách phục hồi không tạo request trùng lặp.

## 1. Xác định đúng loại lỗi trước khi viết test

Trong Spring Messaging, một message đi qua nhiều lớp: transport, giao thức, chuyển đổi payload, định tuyến đến handler và xử lý nghiệp vụ. Một lỗi ở mỗi lớp có phạm vi ảnh hưởng khác nhau. Test cần xác định rõ lớp đang được kiểm tra để tránh kết luận rằng mọi lỗi đều là mất kết nối.

| Loại lỗi | Ví dụ | Phạm vi thường gặp | Điều cần xác nhận |
| --- | --- | --- | --- |
| Transport | TCP reset, WebSocket đóng, peer mất phản hồi | Connection hoặc session | Publisher kết thúc, trạng thái connection đổi và tài nguyên được giải phóng |
| Protocol | Frame không hợp lệ, frame sai cấu trúc hoặc sai trạng thái | Có thể ảnh hưởng toàn connection | Peer từ chối theo quy tắc giao thức và không tiếp tục xử lý dữ liệu hỏng |
| Message/payload | JSON sai, thiếu trường, sai kiểu dữ liệu | Thường là một message hoặc stream | Có lỗi giải mã rõ ràng, không gọi handler nghiệp vụ |
| Validation/nghiệp vụ | ID rỗng, số lượng âm, trạng thái không được phép | Một message/request | Trả lỗi có thể hiểu được và không ghi dữ liệu |
| Resource exhaustion | Buffer đầy, quá nhiều request đồng thời, payload quá lớn | Một stream, connection hoặc toàn service | Từ chối có giới hạn, không tăng bộ nhớ vô hạn và không làm treo hệ thống |

Với RSocket, cần phân biệt lỗi stream và lỗi connection. Frame ERROR có Stream ID khác 0 biểu thị lỗi của stream tương ứng; lỗi connection sử dụng Stream ID 0. Một request sai dữ liệu không nên vô tình làm sập mọi stream. Ngược lại, transport bị mất có thể làm nhiều stream đang dùng chung connection cùng kết thúc.

Với STOMP qua WebSocket, hãy phân biệt việc đóng WebSocket, lỗi STOMP frame, lỗi chuyển đổi message và lỗi trong handler. Mỗi tầng có cơ chế báo lỗi và cách khôi phục riêng.

## 2. Chiến lược kiểm thử theo từng lớp

Một bộ test tốt thường có ba mức:

1. **Unit test:** kiểm tra validator, handler, chính sách retry, giới hạn concurrency và quy tắc giải phóng tài nguyên. Test chạy nhanh, không cần socket thật.
2. **Integration test:** khởi động Spring context và transport thật trên cổng ngẫu nhiên. Gửi message qua RSocket hoặc STOMP, sau đó chủ động đóng hoặc làm hỏng kết nối để quan sát hành vi của toàn luồng.
3. **Resilience/load test:** tạo nhiều client, request đồng thời, payload lớn và độ trễ có kiểm soát để kiểm tra ngưỡng chịu tải. Chạy tách khỏi unit test vì thời gian và mức tài nguyên cao hơn.

Hãy dùng timeout hữu hạn trong test để một publisher không kết thúc không thể làm treo toàn bộ build. Với Reactor, **StepVerifier** giúp kiểm tra thứ tự message, tín hiệu complete/error/cancel và thời gian chờ. Không dùng **Thread.sleep** để đoán rằng một sự kiện mạng đã xảy ra; hãy chờ tín hiệu hoặc dùng latch có timeout.

Mỗi test nên có một giả thuyết cụ thể. Ví dụ: “Khi server đóng connection, request đang chờ nhận lỗi trong thời gian giới hạn và cleanup chạy đúng một lần”. Sau đó kiểm tra cả tín hiệu quan sát được lẫn trạng thái tài nguyên.

## 3. Thử nghiệm mất kết nối

### Các tình huống cần bao phủ

- **Đóng có trật tự:** peer gửi tín hiệu đóng hợp lệ. Client nhận biết connection đã kết thúc và không gửi thêm request qua connection đó.
- **Ngắt đột ngột:** socket bị reset hoặc tiến trình peer dừng. Client nhận lỗi transport thay vì chờ vô hạn.
- **Mất mạng im lặng:** không có FIN/RST và không có phản hồi. Cơ chế keepalive hoặc timeout phát hiện peer không còn phản hồi.
- **Đóng khi đang xử lý:** một hoặc nhiều request đang chạy thì connection bị đóng. Publisher kết thúc đúng cách và tác vụ downstream được cancel nếu không còn cần thiết.
- **Đóng khi đang rảnh:** không có request nghiệp vụ nhưng connection vẫn cần được giám sát và giải phóng khi peer mất.
- **Kết nối lại:** connection mới được tạo sau lỗi tạm thời; trạng thái cũ không được dùng nhầm cho request mới.

### Unit test cho tín hiệu lỗi và cleanup

Đoạn test dưới đây mô phỏng một publisher nhận được một message rồi gặp lỗi tương đương transport bị reset. Đây là unit test cho hợp đồng xử lý lỗi và cleanup; nó không thay thế integration test với socket thật.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ConnectionFailureTest {

    @Test
    void propagatesDisconnectAndRunsCleanup() {
        AtomicBoolean cleanedUp = new AtomicBoolean();

        Flux<String> inbound = Flux.concat(
                Flux.just("accepted"),
                Flux.error(new IOException("connection reset")))
            .doFinally(signal -> cleanedUp.set(true));

        StepVerifier.create(inbound)
                .expectNext("accepted")
                .expectError(IOException.class)
                .verify(Duration.ofSeconds(2));

        assertTrue(cleanedUp.get());
    }
}
~~~

Test xác nhận ba điều: message đã nhận được trước khi lỗi vẫn được phát đúng thứ tự; lỗi không bị nuốt hoặc chuyển thành completion giả; cleanup được gọi khi publisher kết thúc. Trong hệ thống thật, cleanup có thể đóng subscription, giải phóng permit, xóa connection khỏi registry hoặc hủy tác vụ phụ thuộc.

### Integration test với transport thật

Với RSocket, tạo server và client trên TCP loopback, dùng cổng ngẫu nhiên để tránh xung đột. Giữ handle của connection phía server trong test fixture để có thể đóng nó trong lúc client đang chờ response. Sau khi đóng, kiểm tra:

1. Publisher của request đang chạy kết thúc bằng lỗi phù hợp.
2. Tín hiệu connection close của client kết thúc trong timeout đã đặt.
3. Request mới không tiếp tục được gửi trên connection đã đóng.
4. Tài nguyên phía server được giải phóng và connection mới có thể được thiết lập nếu chính sách cho phép.

Với requester do Spring tạo, có thể quan sát vòng đời client qua **requester.rsocketClient().onClose()**. Đăng ký theo dõi một lần cho mỗi connection/client, không tạo listener mới cho từng request. Nếu kiểm tra đóng bình thường, kỳ vọng publisher hoàn tất; nếu cố tình reset transport, kỳ vọng lỗi. Không ép hai trường hợp thành cùng một kết quả.

Với STOMP/WebSocket, khởi động WebSocket server thật và client test, sau đó đóng session hoặc transport ở giữa một subscription. Kiểm tra callback đóng session, subscription dừng, broker không còn giữ session cũ và client có thể kết nối lại. Nếu test dùng broker ngoài tiến trình, chuẩn bị fixture và timeout riêng để tránh phụ thuộc thứ tự khởi động không ổn định.

**Lưu ý:** đóng listener/server socket không phải lúc nào cũng tương đương đóng một connection đã được chấp nhận. Test phải đóng đúng connection đang được quan sát hoặc chủ động ngắt transport của client.

## 4. Thử nghiệm hết tài nguyên và backpressure

Hết tài nguyên không chỉ là hết RAM. Trong ứng dụng messaging, các giới hạn quan trọng gồm:

- Số connection/session đồng thời.
- Số stream hoặc request đang xử lý.
- Số tác vụ chờ trong executor.
- Dung lượng queue/buffer.
- Kích thước payload sau giải mã.
- Số phần tử được giữ trong memory khi downstream xử lý chậm.
- Kết nối tới database hoặc dịch vụ phụ thuộc.

Một hệ thống ổn định phải có giới hạn rõ ràng. Khi vượt ngưỡng, nó nên từ chối hoặc làm chậm producer theo chính sách có chủ đích. Queue không giới hạn chỉ trì hoãn sự cố và thường khiến bộ nhớ tăng đến khi process bị OOM.

### Kiểm tra buffer có giới hạn

Ví dụ sau tạo một producer phát nhanh trong khi downstream chưa yêu cầu phần tử nào. Buffer chỉ có một chỗ trống, vì vậy phần tử vượt giới hạn làm publisher kết thúc bằng lỗi overflow.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.test.StepVerifier;

class BackpressureTest {

    @Test
    void failsWhenBoundedBufferOverflows() {
        Flux<Integer> fastProducer = Flux.create(sink -> {
            sink.next(1);
            sink.next(2);
            sink.next(3);
            sink.complete();
        }, FluxSink.OverflowStrategy.IGNORE);

        Flux<Integer> guarded = fastProducer.onBackpressureBuffer(
                1, BufferOverflowStrategy.ERROR);

        StepVerifier.create(guarded, 0)
                .expectErrorMatches(Exceptions::isOverflow)
                .verify(Duration.ofSeconds(2));
    }
}
~~~

Producer trong test cố tình bỏ qua demand để tạo tình huống quá tải. Trong production, hãy ưu tiên backpressure xuyên suốt pipeline; chỉ dùng buffer khi có lý do và giới hạn dung lượng. Nếu chọn chiến lược drop, phải xác định message nào được phép bỏ và ghi metric tương ứng. Nếu message không được phép mất, hãy trả lỗi hoặc từ chối sớm thay vì âm thầm drop.

### Kiểm tra concurrency và executor

Với Reactor, tham số concurrency của **flatMap** giới hạn số inner publisher được subscribe đồng thời trong một pipeline. Đây là giới hạn cục bộ của pipeline đó, không tự động tạo quota toàn hệ thống. Nếu nhiều connection cùng chạy pipeline, tổng concurrency có thể lớn hơn nhiều lần.

Test cần tạo nhiều request đồng thời và đo số tác vụ đang chạy cực đại bằng **AtomicInteger**. Xác nhận số đó không vượt cấu hình. Nếu dùng **ThreadPoolTaskExecutor**, đặt rõ core pool, max pool và queue capacity; sau đó kiểm tra task vượt giới hạn bị từ chối theo rejection policy đã chọn. Không để task bị giữ vô hạn trong queue.

Các điểm cần kiểm tra:

- Permit hoặc semaphore được trả lại khi success, error và cancel.
- Request bị từ chối không làm tăng số tác vụ đang chạy.
- Queue đạt giới hạn thì hệ thống phát lỗi/response overload rõ ràng.
- Sau khi tải giảm, hệ thống tiếp nhận request mới bình thường.
- Một client quá tải không chiếm hết tài nguyên của các client khác nếu hệ thống có quota theo client.

### Kiểm tra payload lớn

Gửi payload ở các kích thước: nhỏ hơn giới hạn, đúng giới hạn và lớn hơn giới hạn. Xác nhận payload quá lớn bị từ chối trước khi chiếm lượng memory không kiểm soát. Kiểm tra cả kích thước byte trên wire và kích thước sau giải mã; chuỗi JSON hoặc object sau giải mã có thể chiếm nhiều bộ nhớ hơn dữ liệu truyền đi.

Với codec của Spring, cấu hình giới hạn bộ nhớ cho việc giải mã và kiểm tra lỗi khi vượt giới hạn. Đừng chỉ kiểm tra controller sau khi payload đã được giải mã hoàn chỉnh, vì lúc đó chi phí bộ nhớ đã phát sinh.

## 5. Thử nghiệm message không hợp lệ

Hãy chia message không hợp lệ thành các nhóm riêng:

1. **Không giải mã được:** JSON/XML sai cú pháp, content type không hỗ trợ hoặc bytes không phù hợp decoder.
2. **Sai cấu trúc:** thiếu trường bắt buộc, sai kiểu, version schema không tương thích hoặc trường vượt giới hạn.
3. **Sai validation:** chuỗi rỗng, số âm, giá trị ngoài miền cho phép.
4. **Sai định tuyến:** route/destination không tồn tại hoặc không được phép.
5. **Sai nghiệp vụ:** dữ liệu đúng cấu trúc nhưng vi phạm trạng thái hoặc quyền thực hiện.

Không nên chỉ kiểm tra rằng “có exception”. Test tốt cần xác nhận handler nghiệp vụ không được gọi khi message chưa hợp lệ, không có dữ liệu được ghi, lỗi được phân loại đúng và connection vẫn hoạt động nếu lỗi chỉ thuộc message/stream.

### Unit test với Jakarta Bean Validation

Đây là test độc lập cho quy tắc dữ liệu. Nó cần Jakarta Validation API cùng một provider như Hibernate Validator.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.junit.jupiter.api.Test;

class MessageValidationTest {

    record CreateOrder(
            @NotBlank String customerId,
            @Positive long quantity) {
    }

    @Test
    void rejectsBlankCustomerAndNonPositiveQuantity() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<String> invalidFields = validator
                    .validate(new CreateOrder("", 0))
                    .stream()
                    .map(error -> error.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertEquals(Set.of("customerId", "quantity"), invalidFields);
        }
    }
}
~~~

Kết quả mong đợi là hai trường vi phạm: **customerId** và **quantity**. Ở message handler, áp dụng validation trước khi gọi service có side effect. Nếu dùng **@Valid** trên method nhận message, hãy xác nhận validation provider và cơ chế validation của message handler đã được cấu hình trong Spring context; không giả định rằng mọi adapter messaging tự động áp dụng cùng quy tắc như Spring MVC.

### Integration test cho payload sai

Trong test RSocket, gửi một request qua route thật với payload thiếu trường hoặc sai giá trị. Dùng **StepVerifier** kiểm tra request kết thúc bằng lỗi trong timeout giới hạn. Đồng thời dùng spy/mock cho service để xác nhận service không được gọi.

Với payload sai cú pháp hoặc frame sai giao thức, tạo test riêng ở tầng codec/transport. Không gộp payload JSON không hợp lệ với frame RSocket hỏng: trường hợp thứ nhất thường là lỗi giải mã message/stream, còn vi phạm cấu trúc frame có thể làm connection bị đóng theo giao thức.

Với STOMP, gửi frame thiếu header bắt buộc, destination không tồn tại hoặc payload không giải mã được. Xác nhận ERROR frame/close behavior theo cấu hình broker và application. Nếu message hợp lệ nhưng không có quyền truy cập destination, kiểm tra lỗi authorization riêng với lỗi cú pháp.

## 6. Kiểm tra phục hồi sau lỗi

Phục hồi cần được kiểm thử như một quy trình có trạng thái:

1. Phát hiện lỗi và phân loại lỗi là tạm thời hay vĩnh viễn.
2. Dừng công việc phụ thuộc connection đã mất.
3. Giải phóng tài nguyên cũ.
4. Kết nối lại với backoff có giới hạn nếu lỗi có thể phục hồi.
5. Khôi phục subscription/session nếu giao thức và ứng dụng hỗ trợ.
6. Đảm bảo request có side effect không bị thực hiện lặp ngoài ý muốn.

Không retry mọi lỗi. Lỗi network tạm thời có thể retry; message sai validation, route không tồn tại hoặc lỗi authorization thường cần sửa input/quyền trước. Lỗi overload cần giảm tải hoặc từ chối; retry ngay lập tức từ mọi client có thể tạo retry storm.

Ví dụ chính sách retry cho lỗi tạm thời trong Reactor:

~~~java
import java.time.Duration;

import reactor.util.retry.Retry;

return sendRequest()
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isTransientFailure));
~~~

**isTransientFailure** là hàm phân loại do ứng dụng định nghĩa. Giới hạn số lần retry, dùng backoff và cân nhắc jitter khi có nhiều client. Không retry lỗi validation hoặc lỗi nghiệp vụ không thể tự hết.

Nếu server có thể đã xử lý request nhưng response bị mất, retry có thể tạo giao dịch hoặc message trùng. Dùng idempotency key, message ID duy nhất, deduplication hoặc transactional outbox/inbox tùy kiến trúc. Với stream liên tục, phải xác định rõ offset/acknowledgement nào đã được xác nhận trước khi resume.

## 7. Ma trận test gợi ý

| Tình huống | Cách tạo lỗi | Kết quả cần xác nhận |
| --- | --- | --- |
| Peer đóng bình thường | Đóng session/socket theo giao thức | Close signal hoàn tất, cleanup chạy một lần |
| Transport reset | Đóng connection đột ngột | Request đang chờ nhận lỗi, không treo |
| Mất mạng im lặng | Chặn traffic hoặc bỏ phản hồi trong test môi trường | Keepalive/timeout phát hiện trong ngưỡng cấu hình |
| Downstream chậm | Tạo consumer chậm hoặc không request | Backpressure được giữ, buffer không vượt giới hạn |
| Buffer đầy | Producer vượt capacity | Overflow/error/drop đúng policy |
| Quá concurrency | Gửi nhiều request đồng thời | Số tác vụ không vượt quota |
| Payload quá lớn | Gửi payload vượt giới hạn | Bị từ chối, không làm tăng memory vô hạn |
| JSON sai cú pháp | Gửi bytes không giải mã được | Decoder báo lỗi, handler không chạy |
| Thiếu trường | Gửi object thiếu dữ liệu bắt buộc | Validation thất bại, không ghi dữ liệu |
| Route không tồn tại | Gửi destination/route lạ | Lỗi định tuyến được trả rõ ràng |
| Retry sau disconnect | Ngắt kết nối sau khi server xử lý | Không tạo side effect trùng |
| Hết tải | Ngừng producer và giải phóng request | Hệ thống nhận request mới trở lại bình thường |

## 8. Những sai lầm thường gặp

- **Chỉ test happy path:** lỗi mạng và quá tải thường xuất hiện ở trạng thái chuyển tiếp, khi request đang chạy hoặc buffer đang đầy.
- **Dùng mock để kết luận transport đã hoạt động đúng:** mock publisher hữu ích cho unit test, nhưng không chứng minh TCP/WebSocket đóng và phát hiện lỗi chính xác.
- **Dùng Thread.sleep:** test phụ thuộc thời gian máy chạy và dễ flaky. Hãy đồng bộ bằng tín hiệu, latch hoặc StepVerifier với timeout.
- **Dùng queue không giới hạn:** che giấu tốc độ producer vượt consumer và có thể gây OOM.
- **Retry ngay khi gặp lỗi:** làm tăng tải đúng lúc service đang quá tải và có thể tạo duplicate side effect.
- **Chỉ assert exception:** bỏ qua việc handler đã chạy, dữ liệu đã ghi hoặc tài nguyên có được giải phóng hay không.
- **Gộp lỗi stream với lỗi connection:** một message lỗi không nên mặc định làm hỏng mọi stream; lỗi transport có thể ảnh hưởng toàn connection.
- **Chỉ test một lần đóng:** cần kiểm tra cả đóng bình thường, reset đột ngột, mất mạng im lặng và đóng trong lúc có request đang chạy.

## 9. Checklist trước khi hoàn thành

- [ ] Có unit test cho validation, phân loại lỗi và cleanup.
- [ ] Có integration test dùng transport thật cho đóng bình thường và ngắt đột ngột.
- [ ] Có test timeout/keepalive cho tình huống mất mạng im lặng.
- [ ] Có test buffer, concurrency, executor và payload size theo giới hạn cấu hình.
- [ ] Có test message sai cú pháp, sai cấu trúc và sai nghiệp vụ riêng biệt.
- [ ] Xác nhận handler không chạy và không ghi dữ liệu khi payload không hợp lệ.
- [ ] Xác nhận lỗi stream không làm đóng connection khi giao thức cho phép tiếp tục.
- [ ] Xác nhận connection lỗi làm dừng publisher và giải phóng tài nguyên.
- [ ] Retry có giới hạn, backoff và chỉ áp dụng cho lỗi tạm thời.
- [ ] Có kiểm tra idempotency hoặc deduplication cho request có side effect.
- [ ] Test có timeout hữu hạn và không dựa vào Thread.sleep.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [RSocket Protocol — Error frame](https://github.com/rsocket/rsocket/blob/master/Protocol.md#error-frame-0x0b)
