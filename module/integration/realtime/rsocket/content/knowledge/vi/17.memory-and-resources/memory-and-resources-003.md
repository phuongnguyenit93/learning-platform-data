# Quy tắc retain, release và thời điểm không còn được truy cập payload

Trong RSocket Java, `Payload` thường được xây dựng trên các `ByteBuf` của Netty. Những buffer này sử dụng **reference counting** để quản lý bộ nhớ, đặc biệt là vùng nhớ direct/off-heap. Vì vậy, vòng đời của payload không chỉ phụ thuộc vào garbage collector: ứng dụng phải hiểu ai đang sở hữu reference, khi nào cần `retain()`, khi nào phải `release()` và thời điểm dữ liệu không còn được phép truy cập.

Quy tắc quan trọng nhất là giải phóng đúng reference mà mình sở hữu. Một payload được chuyển cho RSocket runtime để gửi sẽ do runtime quản lý theo hợp đồng API; payload được giao cho code responder hoặc subscriber để xử lý phải được giải phóng sau khi dùng xong. Nếu cần giữ dữ liệu lâu hơn vòng đời hiện tại, hãy sao chép dữ liệu sang kiểu độc lập hoặc giữ thêm một reference và giải phóng reference đó ở đúng điểm kết thúc.

## 1. Vì sao Payload cần retain/release?

RSocket hướng đến giao tiếp bất đồng bộ và thông lượng cao. Netty có thể tái sử dụng các vùng nhớ direct để tránh cấp phát và sao chép dữ liệu liên tục. `ByteBuf` vì thế không nhất thiết được thu hồi khi một biến Java mất tham chiếu.

Một `Payload` có thể chứa vùng data và metadata. Các vùng này thường chia sẻ cơ chế reference counting của buffer bên dưới. Khi reference count về `0`, buffer được giải phóng hoặc trả lại pool; mọi thao tác đọc/ghi tiếp theo trên buffer đã giải phóng đều không hợp lệ.

| Cơ chế | Tác dụng |
|---|---|
| `refCnt()` | Xem số reference hiện tại của đối tượng reference-counted. |
| `retain()` | Tăng reference count để giữ tài nguyên lâu hơn hoặc tạo thêm một quyền sở hữu. |
| `release()` | Giảm reference count; khi về `0`, tài nguyên được giải phóng. |
| `touch()` | Ghi dấu gợi ý cho công cụ phát hiện rò rỉ, hữu ích khi lần theo nơi tài nguyên được sử dụng. |

Ví dụ đơn giản:

```java
Payload payload = DefaultPayload.create("hello");

int count = payload.refCnt();       // thường bắt đầu từ 1
payload.retain();                   // tăng thêm một reference

payload.release();                  // giảm về 1
payload.release();                  // giảm về 0, tài nguyên được giải phóng
```

Ví dụ này minh họa phép đếm reference. Trong code ứng dụng, không nên gọi `retain()` hoặc `release()` theo cảm tính; mỗi lần tăng reference phải có một nơi chịu trách nhiệm giảm reference tương ứng.

## 2. Quy tắc ownership: ai phải release?

Ownership là yếu tố quyết định khi gọi API. Ở tầng `RSocket`, một payload có thể được chuyển vào runtime để gửi, được giao cho implementation responder để xử lý, hoặc được trả về cho subscriber. Mỗi điểm chuyển giao có trách nhiệm riêng.

| Tình huống | Ai sở hữu payload sau điểm chuyển giao? | Việc cần làm |
|---|---|---|
| Ứng dụng truyền request `Payload` vào `socket.fireAndForget(...)`, `requestResponse(...)` hoặc `requestStream(...)`. | RSocket runtime nhận ownership để gửi request. | Không tự release hoặc truy cập payload sau khi đã chuyển giao. |
| Ứng dụng phát từng `Payload` từ publisher đầu vào của `requestChannel(...)`. | RSocket runtime nhận ownership của từng payload được phát. | Tạo payload đúng lúc phát; không release lần nữa sau khi runtime nhận. |
| Custom responder nhận payload request trong method `RSocket`. | Code responder sở hữu payload đầu vào được giao để xử lý. | Release sau khi đã đọc/giải mã xong; nếu cần dùng bất đồng bộ thì giữ reference hoặc sao chép dữ liệu. |
| Responder trả `Payload` trong `Mono` hoặc `Flux` response. | RSocket runtime nhận ownership để gửi response. | Không release payload response sau khi trả cho runtime. |
| Client nhận `Payload` từ `Mono<Payload>` hoặc `Flux<Payload>`. | Subscriber/caller nhận ownership của payload được phát. | Giải mã xong thì release; nếu chuyển cho component khác, chuyển giao ownership rõ ràng. |
| Responder nhận từng payload từ publisher đầu vào của request-channel. | Code xử lý channel sở hữu payload đã nhận. | Release từng phần tử sau khi giải mã hoặc xử lý xong. |

Quy tắc trên mô tả ranh giới ownership của API RSocket mức thấp. Khi dùng Spring `RSocketRequester` và message codecs, framework có thể tự giải mã và quản lý payload nội bộ; hãy làm theo hợp đồng của abstraction đang dùng, tránh tự release một buffer mà framework vẫn đang sở hữu.

## 3. Outbound request: chuyển ownership cho RSocket

Khi gọi một phương thức tương tác, payload đầu vào được chuyển cho RSocket runtime để encode và gửi. Caller không được giữ lại rồi đọc hoặc release payload như thể mình vẫn còn sở hữu nó.

```java
Mono<Quote> findQuote(RSocket socket, String symbol) {
    return Mono.defer(() -> {
        Payload request = DefaultPayload.create(symbol);

        // Khi gọi API, ownership của request được chuyển cho RSocket.
        return socket.requestResponse(request)
            .map(response -> {
                try {
                    return decodeQuote(response.data());
                } finally {
                    response.release();
                }
            });
    });
}
```

`Mono.defer(...)` tạo payload khi có subscription. Nếu tạo `Payload` ngay ở thời điểm lắp ráp pipeline rồi publisher không bao giờ được subscribe, payload có thể chưa được chuyển cho runtime và vẫn bị giữ lại. Tạo payload bên trong `defer` giúp vòng đời tạo và chuyển giao gắn với lần thực thi.

Sau khi gọi `socket.requestResponse(request)`, không làm như sau:

```java
Payload request = DefaultPayload.create("ACME");
Mono<Payload> response = socket.requestResponse(request);

request.release(); // Sai: runtime có thể vẫn đang dùng payload để gửi.
```

Việc release sớm có thể khiến runtime đọc một buffer đã bị giải phóng, dẫn đến `IllegalReferenceCountException`, lỗi gửi hoặc dữ liệu không hợp lệ.

Với `requestStream`, nguyên tắc tương tự áp dụng cho payload request duy nhất. Với `requestChannel`, mỗi payload được phát từ publisher đầu vào được chuyển ownership cho runtime khi nó được phát; tránh tạo sẵn một danh sách payload lớn ở thời điểm assembly nếu có thể tạo payload theo nhu cầu.

## 4. Inbound request: giải phóng payload trong responder

Khi tự triển khai responder bằng `RSocket`, các method nhận `Payload` đầu vào. Code responder cần giải phóng payload sau khi đã đọc hoặc sao chép dữ liệu cần thiết.

```java
@Override
public Mono<Payload> requestResponse(Payload request) {
    QuoteQuery query;
    try {
        query = decodeQuery(request.data());
    } finally {
        request.release();
    }

    return quoteService.find(query)
        .map(quote -> DefaultPayload.create(encodeQuote(quote)));
}
```

Ở ví dụ này, `decodeQuery(...)` tạo một object Java độc lập trước khi payload được release. Service chỉ giữ `QuoteQuery`, không giữ `ByteBuf` bên trong payload. Payload response được tạo mới và trả cho runtime; responder không release payload response đó.

Nếu xử lý request-stream, hãy giải phóng payload request sau khi đã lấy đủ thông tin để tạo stream:

```java
@Override
public Flux<Payload> requestStream(Payload request) {
    QuoteQuery query;
    try {
        query = decodeQuery(request.data());
    } finally {
        request.release();
    }

    return quoteService.stream(query)
        .map(quote -> DefaultPayload.create(encodeQuote(quote)));
}
```

Không cần giữ payload request trong suốt thời gian stream nếu service đã có `QuoteQuery` độc lập. Điều này giúp giải phóng buffer sớm, đặc biệt khi stream kéo dài hoặc có nhiều subscriber đồng thời.

## 5. Inbound response: giải phóng từng Payload đã nhận

Ở phía requester, `requestResponse` trả về `Mono<Payload>` và `requestStream` trả về `Flux<Payload>`. Khi subscriber nhận payload, subscriber phải giải phóng nó sau khi đã giải mã.

```java
Flux<Quote> quotes = socket
    .requestStream(DefaultPayload.create("ACME"))
    .map(payload -> {
        try {
            return decodeQuote(payload.data());
        } finally {
            payload.release();
        }
    });
```

`finally` bảo đảm payload được release ngay cả khi decoder ném exception. Sau `map`, downstream chỉ nhận `Quote` là object độc lập nên không còn phụ thuộc vào vòng đời của payload.

Với request-response, cùng quy tắc áp dụng cho một phần tử:

```java
Mono<Quote> quote = socket
    .requestResponse(DefaultPayload.create("ACME"))
    .map(payload -> {
        try {
            return decodeQuote(payload.data());
        } finally {
            payload.release();
        }
    });
```

Không nên chỉ gọi `release()` trong `doOnNext` rồi giả định mọi trường hợp đều được xử lý. Nếu decoder ném lỗi trước hook hoặc payload bị loại bỏ bởi operator, cần có chiến lược cleanup phù hợp cho cả đường lỗi và đường discard.

## 6. Payload trong request-channel

`requestChannel(Publisher<Payload>)` có hai ranh giới ownership:

- Các payload do requester phát lên được chuyển cho RSocket runtime.
- Các payload do responder phát về được subscriber phía requester nhận và phải release sau khi dùng.

Ở phía responder, mỗi payload nhận từ publisher đầu vào của channel cũng phải được giải phóng sau khi giải mã:

```java
@Override
public Flux<Payload> requestChannel(Publisher<Payload> inbound) {
    Flux<Command> commands = Flux.from(inbound)
        .map(payload -> {
            try {
                return decodeCommand(payload.data());
            } finally {
                payload.release();
            }
        });

    return commandService.handle(commands)
        .map(update -> DefaultPayload.create(encodeUpdate(update)));
}
```

Mỗi phần tử được giải phóng ngay sau khi chuyển thành `Command`. Response payload được tạo riêng và chuyển ownership cho runtime. Nếu channel bị hủy, các payload đã được nhận phải được xử lý đúng; với payload đang nằm trong hàng đợi hoặc bị discard bởi operator, cần thêm cleanup hook phù hợp.

Ở phía requester, có thể tạo payload theo từng command:

```java
Flux<Payload> outbound = commands
    .map(command -> DefaultPayload.create(encodeCommand(command)));

Flux<Payload> inbound = socket.requestChannel(outbound);
```

Mỗi payload outbound được tạo ngay khi `map` phát phần tử và chuyển cho RSocket. Các payload inbound do subscriber nhận cần được giải mã rồi release tương tự `requestStream`.

## 7. Khi nào Payload không còn được truy cập?

Payload không còn hợp lệ để truy cập khi reference count của tài nguyên nền đã về `0`. Điều này có thể xảy ra sau một lần `release()` cuối cùng hoặc sau khi component sở hữu payload hoàn tất việc gửi và giải phóng nó.

Các dấu hiệu thường gặp:

- Gọi `payload.data()` hoặc đọc `ByteBuf` sau khi payload đã release.
- Truy cập một retained slice sau khi chính slice đó đã release.
- Dùng payload trong callback bất đồng bộ chạy sau khi scope xử lý ban đầu đã kết thúc.
- Giữ payload trong field/cache rồi component sở hữu ban đầu đã release.

Netty thường phát sinh `IllegalReferenceCountException` khi truy cập buffer đã giải phóng. Tuy nhiên, không phải mọi lỗi vòng đời đều biểu hiện ngay; dữ liệu bị tái sử dụng hoặc lỗi chỉ xuất hiện dưới tải đồng thời cũng có thể làm việc debug khó hơn.

```java
Payload payload = DefaultPayload.create("hello");
payload.release();

String value = payload.data().toString(StandardCharsets.UTF_8);
// Sai: payload và ByteBuf nền có thể đã được giải phóng.
```

Không dựa vào `refCnt()` để giữ payload sống bằng cách kiểm tra rồi đọc. Giữa lần kiểm tra và lần truy cập, một component khác vẫn có thể release reference. Ownership phải được quản lý bằng hợp đồng rõ ràng, không phải bằng kiểm tra thời điểm.

## 8. Không giữ ByteBuf view vượt quá vòng đời Payload

Các accessor như `payload.data()` và `payload.metadata()` trả về `ByteBuf` để đọc nội dung. Một view/slice thông thường có thể chia sẻ vùng nhớ và reference count với payload. Vì vậy, việc lưu `ByteBuf` vào biến hoặc field không tự động kéo dài vòng đời của payload.

Nếu cần giữ dữ liệu sau khi release payload, có hai lựa chọn:

1. **Sao chép sang kiểu độc lập:** chuyển bytes thành `byte[]`, `String` hoặc object Java đã giải mã. Đây thường là lựa chọn đơn giản và an toàn nhất.
2. **Giữ một reference riêng:** dùng thao tác retain phù hợp, chẳng hạn `retainedSlice()`, rồi release view đó khi xử lý xong.

Ví dụ sao chép sang `byte[]`:

```java
byte[] body;
try {
    body = ByteBufUtil.getBytes(payload.data());
} finally {
    payload.release();
}

return asyncService.process(body);
```

`byte[]` không phụ thuộc vào vòng đời `Payload` nên có thể được chuyển cho tác vụ bất đồng bộ sau đó.

Ví dụ giữ một slice có reference riêng:

```java
ByteBuf retainedData = payload.data().retainedSlice();
payload.release();

return asyncService.process(retainedData)
    .doFinally(signal -> retainedData.release());
```

`retainedSlice()` tăng reference count của vùng nhớ được chia sẻ. Vì vậy, sau khi release payload gốc, slice vẫn hợp lệ. Khi tác vụ kết thúc, phải release slice đúng một lần. Không gọi `retainedData.release()` ở nhiều nhánh nếu chưa phối hợp ownership.

## 9. Giữ Payload qua ranh giới bất đồng bộ

Nếu một tác vụ bất đồng bộ thực sự cần đọc payload gốc, ứng dụng phải giữ thêm reference trước khi quyền sở hữu ban đầu kết thúc. Sau đó phải release reference đã giữ trong mọi đường kết thúc: thành công, lỗi và cancellation.

```java
Mono<Result> processAsync(Payload payload) {
    payload.retain();
    payload.release(); // kết thúc reference ban đầu của handler

    try {
        return asyncProcessor.process(payload.data())
            .doFinally(signal -> payload.release());
    } catch (RuntimeException error) {
        payload.release();
        return Mono.error(error);
    }
}
```

Ví dụ trên minh họa việc chuyển phần sở hữu còn lại cho pipeline async: `retain()` tạo thêm một reference, `release()` kết thúc reference ban đầu, còn `doFinally` kết thúc reference được giữ cho tác vụ. Nhánh `catch` giải phóng reference nếu việc tạo publisher ném lỗi đồng bộ. Trong code production, cần bảo đảm `asyncProcessor.process(...)` không giữ `ByteBuf` sau khi publisher kết thúc. Nếu có thể, hãy decode/copy thành object độc lập trước khi gọi tác vụ async; cách đó dễ kiểm soát hơn.

Không dùng `retain()` để che một ownership không rõ ràng. Mỗi reference bổ sung làm tài nguyên sống lâu hơn và phải có một nơi release xác định. Nếu không có nơi release, việc retain chỉ biến use-after-release thành memory leak.

## 10. Xử lý payload bị discard trong Reactor

Trong pipeline reactive, một phần tử có thể không đến được `map` cuối cùng do `filter`, `take`, `flatMap`, cancellation, lỗi hoặc operator có hàng đợi. Nếu phần tử đó là `Payload` reference-counted, cần đảm bảo payload bị discard cũng được release.

Với các operator Reactor hỗ trợ discard hook, có thể dùng `doOnDiscard`:

```java
Flux<Quote> quotes = socket
    .requestStream(DefaultPayload.create("ACME"))
    .filter(this::isRelevantPayload)
    .doOnDiscard(Payload.class, Payload::release)
    .map(payload -> {
        try {
            return decodeQuote(payload.data());
        } finally {
            payload.release();
        }
    });
```

`doOnDiscard` chỉ áp dụng cho các operator có hỗ trợ discard và phải được đặt trong phạm vi pipeline phù hợp. Nó không thay thế việc release payload đã được xử lý trong `map`. Không cấu hình discard hook trùng với một cơ chế cleanup khác đang release cùng reference, nếu không sẽ dẫn đến double-release.

Nếu dùng operator tự viết hoặc một thư viện không có discard support, cần xác định rõ ai nhận ownership của phần tử khi cancellation/error xảy ra và bổ sung cleanup tại đúng ranh giới đó.

## 11. Release trong mọi đường kết thúc

Một payload cần được release dù xử lý thành công, lỗi hay bị hủy. Với xử lý đồng bộ, `try/finally` là mẫu rõ ràng:

```java
Quote decodeAndRelease(Payload payload) {
    try {
        return decodeQuote(payload.data());
    } finally {
        payload.release();
    }
}
```

Với một publisher được tạo từ payload đầu vào, có thể gắn cleanup vào vòng đời reactive:

```java
Mono<Quote> handle(Payload request) {
    QuoteQuery query;
    try {
        query = decodeQuery(request.data());
    } finally {
        request.release();
    }

    return quoteService.find(query);
}
```

Trong ví dụ này, payload được giải phóng trước khi trả publisher vì `QuoteQuery` đã độc lập. Nếu publisher còn cần đọc payload, hãy retain/copy trước và gắn release vào `doFinally` hoặc cơ chế quản lý resource phù hợp.

`doFinally` chạy khi publisher kết thúc bằng complete, error hoặc cancel. Nó phù hợp để giải phóng reference mà pipeline sở hữu. Tuy nhiên, nó chỉ chạy sau khi có subscription; đừng tạo và retain tài nguyên trước subscription rồi kỳ vọng `doFinally` xử lý trường hợp publisher không bao giờ được subscribe. Hãy tạo tài nguyên bên trong `defer` hoặc dùng resource operator có vòng đời phù hợp.

## 12. Phân biệt memory leak và double-release

Hai lỗi phổ biến có nguyên nhân ngược nhau:

| Lỗi | Điều gì xảy ra? | Dấu hiệu |
|---|---|---|
| Memory leak | Một hoặc nhiều reference không được release. Buffer direct/pooled tiếp tục bị giữ. | Direct memory tăng, Netty leak detector cảnh báo, tải tăng khiến bộ nhớ không giảm. |
| Double-release | Một reference bị release nhiều hơn số lần retain/ownership cho phép. | `IllegalReferenceCountException`, refCnt âm hoặc lỗi truy cập buffer. |
| Use-after-release | Code đọc/ghi sau khi reference count về `0`. | `IllegalReferenceCountException` hoặc dữ liệu không hợp lệ. |
| Premature release | Release trước khi runtime hoặc async task hoàn tất sử dụng. | Lỗi xảy ra ngẫu nhiên khi tải cao hoặc có race condition. |

Không khắc phục memory leak bằng cách thêm `release()` ở mọi nơi. Trước tiên hãy xác định ai sở hữu reference. Một payload outbound đã chuyển cho runtime không nên bị caller release; một payload inbound do handler sở hữu phải có một đường release duy nhất.

## 13. Công cụ phát hiện và quan sát rò rỉ

Netty cung cấp `ResourceLeakDetector` để phát hiện các buffer được cấp phát nhưng không được release đúng cách. Trong môi trường phát triển hoặc kiểm thử, có thể tăng mức kiểm tra bằng JVM property:

```text
-Dio.netty.leakDetection.level=advanced
```

Các mức phổ biến gồm `disabled`, `simple`, `advanced` và `paranoid`. Mức kiểm tra càng cao thì overhead càng lớn; `paranoid` phù hợp với một số test cô lập, không nên bật tùy tiện cho production có tải cao.

Khi điều tra memory leak, nên quan sát:

- Direct memory và pooled allocator usage.
- Số lượng payload được tạo, nhận, phát và giải phóng theo loại tương tác.
- Các cảnh báo Netty leak detector và stack trace nơi buffer được cấp phát.
- Các nhánh lỗi, timeout và cancellation có chạy cleanup không.
- Những publisher bị discard hoặc hàng đợi bị bỏ khi shutdown.

Không ghi toàn bộ data/metadata payload vào log chỉ để debug memory. Payload có thể chứa token, dữ liệu cá nhân hoặc thông tin nhạy cảm; log kích thước, route và correlation ID đã được phép ghi nhận thường đủ để khoanh vùng.

## 14. Kiểm thử vòng đời Payload

Kiểm thử nên bao phủ cả đường thành công và các đường kết thúc bất thường. Với payload do test tạo, hãy xác định rõ test giữ ownership hay đã chuyển payload cho runtime/handler.

Các trường hợp cần kiểm tra:

1. Decode thành công rồi release đúng một lần.
2. Decoder ném exception nhưng payload vẫn được release nhờ `finally`.
3. Publisher bị cancel trước khi hoàn tất và reference do pipeline giữ vẫn được release.
4. Payload bị discard bởi filter/operator có cleanup hook phù hợp.
5. Retained slice còn đọc được sau khi payload gốc release và được release sau khi async task kết thúc.
6. Payload outbound được chuyển cho runtime, caller không release lần thứ hai.
7. Request-channel nhận nhiều payload; mỗi payload inbound được release độc lập.
8. Không có payload hoặc ByteBuf nào bị truy cập sau khi reference count về `0`.

Ví dụ kiểm tra một hàm decode có release trong `finally`:

```java
Payload payload = DefaultPayload.create("ACME");
int initialRefCount = payload.refCnt();

Quote quote = decodeAndRelease(payload);

assertThat(quote.symbol()).isEqualTo("ACME");
assertThat(payload.refCnt()).isEqualTo(initialRefCount - 1);
```

Trong test tích hợp, không nên kiểm tra một số `refCnt` nội bộ tùy implementation nếu ownership đã được chuyển cho RSocket runtime. Thay vào đó, kiểm tra hành vi, bật leak detector và xác minh các đường complete/error/cancel đều kết thúc mà không để lại cảnh báo.

## 15. Checklist khi làm việc với Payload

Trước khi merge code dùng `Payload` hoặc `ByteBuf`, hãy trả lời các câu hỏi sau:

- Payload này được tạo bởi ai và đang thuộc ownership của component nào?
- Nếu truyền vào API RSocket outbound, đã chuyển quyền sở hữu cho runtime chưa?
- Nếu nhận payload ở responder hoặc subscriber, release nằm ở đâu?
- Nếu decode ném lỗi, `finally` hoặc cleanup hook có chạy không?
- Nếu publisher bị cancel hoặc phần tử bị discard, reference có được release không?
- Có `ByteBuf` view nào bị giữ qua thời điểm payload gốc release không?
- Nếu cần giữ dữ liệu bất đồng bộ, đã copy hoặc retain đúng cách chưa?
- Mỗi lần retain có đúng một lần release tương ứng không?
- Có nhánh nào release cùng reference hai lần không?
- Leak detector và kiểm thử cancellation/error có được dùng trong môi trường phù hợp không?

## Kết luận

`Payload` trong RSocket Java thường dựa trên reference-counted `ByteBuf`, nên garbage collector không thay thế trách nhiệm retain/release. Khi gửi request hoặc response, ownership của payload được chuyển cho RSocket runtime; khi code ứng dụng nhận payload để xử lý, cần release sau khi dùng xong. Nếu dữ liệu phải sống lâu hơn payload, hãy copy sang object độc lập hoặc giữ một reference riêng và release khi tác vụ kết thúc. Quản lý ownership rõ ràng ở mọi đường complete, error, cancel và discard sẽ ngăn memory leak, double-release và use-after-release trong các ứng dụng RSocket realtime.
