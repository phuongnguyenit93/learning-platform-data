# Đếm tham chiếu và quyền sở hữu Payload qua từng lời gọi

RSocket Java truyền payload bằng các buffer của Netty. Những buffer này có thể nằm ngoài heap và được tái sử dụng qua cơ chế pooling. Vì vậy, vòng đời của `Payload` không chỉ phụ thuộc vào garbage collector của Java: ứng dụng cần hiểu ai đang sở hữu payload, khi nào được giữ thêm một tham chiếu và khi nào phải giải phóng tham chiếu.

Trong module `INTEGRATION_REALTIME_RSOCKET`, quản lý đúng `Payload` đặc biệt quan trọng khi dùng zero-copy, xử lý bất đồng bộ hoặc truyền dữ liệu qua nhiều tầng. Một lần `release()` quá sớm có thể làm code khác đọc buffer đã bị giải phóng; thiếu `release()` có thể giữ bộ nhớ native lâu hơn cần thiết. Bài viết này lần theo quyền sở hữu qua các lời gọi RSocket và chỉ ra cách quản lý `retain()`/`release()` an toàn.

## 1. Vì sao Payload cần đếm tham chiếu?

`io.rsocket.Payload` chứa phần data và metadata của một thông điệp RSocket. Trong RSocket Java, payload thường được xây dựng trên các buffer có cơ chế đếm tham chiếu của Netty. `Payload` cung cấp các thao tác như:

- `refCnt()` đọc số tham chiếu hiện tại.
- `retain()` tăng số tham chiếu lên một.
- `retain(n)` tăng thêm `n` tham chiếu.
- `release()` giảm số tham chiếu đi một.
- `release(n)` giảm số tham chiếu đi `n`.
- `touch(hint)` ghi thêm thông tin hỗ trợ phát hiện buffer bị rò rỉ.

Một payload mới thường bắt đầu với một tham chiếu. Khi bộ đếm về `0`, tài nguyên backing buffer có thể được giải phóng hoặc trả lại allocator để tái sử dụng.

```text
Tạo Payload
  refCnt = 1
      |
      | retain()
      v
  refCnt = 2
      |
      | release()  (chủ sở hữu thứ nhất kết thúc)
      v
  refCnt = 1
      |
      | release()  (chủ sở hữu thứ hai kết thúc)
      v
  refCnt = 0  ---> giải phóng tài nguyên
```

Đếm tham chiếu hữu ích khi buffer được truyền qua nhiều tầng mà không cần sao chép dữ liệu. Garbage collector không tự biết lúc nào một buffer pooled/direct có thể được trả về allocator; `release()` cung cấp tín hiệu vòng đời rõ ràng.

## 2. Quy tắc retain và release

Hãy gắn mỗi tham chiếu với một chủ sở hữu cụ thể. Chủ sở hữu phải đảm bảo tham chiếu của mình được giải phóng đúng một lần khi không còn dùng payload.

| Thao tác | Thay đổi refCnt | Trách nhiệm |
|---|---:|---|
| Tạo payload mới | Thường bắt đầu ở `1` | Bên tạo sở hữu tham chiếu ban đầu. |
| `retain()` | `+1` | Bên gọi nhận thêm một trách nhiệm release. |
| `release()` | `-1` | Bên sở hữu kết thúc việc sử dụng tham chiếu của mình. |
| Chuyển quyền sở hữu | Không nhất thiết đổi refCnt | Bên nhận tiếp quản trách nhiệm; bên gửi không tiếp tục truy cập hoặc release tham chiếu đã chuyển. |
| Sao chép dữ liệu | Tạo vùng nhớ độc lập | Bên tạo bản sao quản lý vòng đời vùng nhớ mới. |

Ví dụ, một payload có `refCnt = 1`. Nếu một tầng gọi `retain()`, bộ đếm thành `2`. Hai chủ sở hữu phải giải phóng hai tham chiếu tương ứng. Nếu chỉ release một lần, buffer vẫn còn một tham chiếu và chưa được giải phóng. Nếu release ba lần, lần release cuối vượt quá số tham chiếu còn lại và có thể gây `IllegalReferenceCountException`.

`refCnt()` hữu ích để debug và viết kiểm thử, nhưng không nên dùng nó làm cơ chế đồng bộ hoặc quyết định xem một thread khác có còn quyền truy cập hay không. Các lời gọi `retain()`/`release()` cũng không làm cho toàn bộ đối tượng `Payload` trở nên an toàn khi nhiều thread cùng đọc/ghi. Riêng `DefaultPayload` trong RSocket Java 1.1.5 được tài liệu hóa là không thread-safe.

## 3. PayloadDecoder quyết định cách quản lý inbound payload

Đây là điểm quan trọng nhất khi làm việc với RSocket Java. `RSocketConnector` phía client và `RSocketServer` phía server đều cho phép cấu hình `PayloadDecoder` để tạo `Payload` từ frame inbound.

| Decoder | Cách tạo payload | Ứng dụng cần release inbound Payload? |
|---|---|---|
| `PayloadDecoder.DEFAULT` | Data và metadata được copy độc lập từ frame buffer. | Không cần theo dõi/release payload inbound theo hợp đồng của decoder mặc định. |
| `PayloadDecoder.ZERO_COPY` | Data và metadata là các retained slice của frame buffer gốc. | Có. Ứng dụng phải release payload khi đã dùng xong. |

Decoder mặc định ưu tiên sự đơn giản. Zero-copy tránh sao chép dữ liệu và có thể giảm allocation/latency, nhưng trách nhiệm vòng đời buffer được đưa tới code ứng dụng. Không bật zero-copy chỉ vì muốn tối ưu; trước hết cần có quy ước ownership rõ ràng và kiểm thử leak.

Ví dụ bật zero-copy ở client:

```java
RSocketConnector connector = RSocketConnector.create()
    .payloadDecoder(PayloadDecoder.ZERO_COPY);

Mono<RSocket> socket = connector.connect(transport);
```

Ví dụ bật zero-copy ở server:

```java
RSocketServer server = RSocketServer.create(socketAcceptor)
    .payloadDecoder(PayloadDecoder.ZERO_COPY);

Mono<CloseableChannel> bound = server.bind(transport);
```

Hai phía cấu hình decoder độc lập. Bật zero-copy ở client không tự động bật zero-copy ở server. Nếu chỉ một phía dùng zero-copy, code phía đó phải quản lý inbound payload của mình theo quy tắc tương ứng.

## 4. Quyền sở hữu qua các ranh giới RSocket

Với API RSocket mức thấp, cần phân biệt payload ứng dụng gửi đi và payload ứng dụng nhận được:

| Vị trí | Vai trò của Payload | Cách quản lý |
|---|---|---|
| Client truyền request vào `requestResponse`, `fireAndForget`, `requestStream` hoặc `requestChannel` | Outbound request payload | Xem lời gọi RSocket là điểm chuyển payload cho implementation gửi đi; không tiếp tục sửa, đọc hoặc release cùng tham chiếu sau khi đã chuyển. |
| Server nhận `Payload` trong responder method | Inbound request payload | Với `ZERO_COPY`, handler release sau khi xử lý hoặc chuyển quyền sở hữu; với `DEFAULT`, decoder đã tạo bản copy và không yêu cầu release thủ công. |
| Server trả `Payload` trong publisher response | Outbound response payload | Khi trả payload cho RSocket runtime, chuyển quyền sở hữu cho tầng gửi; không release thêm sau khi đã trả. |
| Client nhận `Payload` từ `Mono<Payload>` hoặc `Flux<Payload>` | Inbound response payload | Với `ZERO_COPY`, subscriber release mỗi payload sau khi xử lý; với `DEFAULT`, không cần release thủ công. |
| Spring chuyển payload thành DTO qua codec | Dữ liệu đã giải mã ở tầng ứng dụng | Để Spring quản lý buffer nội bộ; không gọi `release()` trên DTO thông thường. |

Quy tắc chuyển quyền sở hữu ở API mức thấp cần được áp dụng nhất quán theo phiên bản RSocket Java đang dùng. Không giữ lại tham chiếu outbound để sử dụng sau khi gọi RSocket; nếu cần dữ liệu ở nhiều nơi, hãy tạo bản sao hoặc `retain()` trước khi chuyển một tham chiếu.

## 5. Client nhận response: release sau khi đọc

Khi client dùng API mức thấp và bật `PayloadDecoder.ZERO_COPY`, mỗi response payload nhận được cần được release sau khi đã trích xuất dữ liệu.

```java
Mono<String> reply = socket
    .requestResponse(DefaultPayload.create("ping"))
    .map(response -> {
        try {
            return response.getDataUtf8();
        } finally {
            response.release();
        }
    });
```

`getDataUtf8()` tạo ra một `String` độc lập với buffer payload, vì vậy có thể trả string ra khỏi callback rồi release payload. Nếu code chỉ lấy `ByteBuf` hoặc `ByteBuffer` view từ payload, cần kiểm tra phần tiếp theo về view và thời gian sống của buffer.

Với Request-Stream, cần release từng phần tử:

```java
Flux<String> messages = socket
    .requestStream(DefaultPayload.create("watch"))
    .map(payload -> {
        try {
            return payload.getDataUtf8();
        } finally {
            payload.release();
        }
    });
```

Đoạn code trên minh họa trường hợp inbound decoder là `ZERO_COPY`. Mỗi payload trong `Flux` có vòng đời riêng; không được chỉ release phần tử cuối hoặc chờ toàn bộ stream kết thúc mới release tất cả payload nếu chúng đã được xử lý xong.

Nếu cần dùng cùng một payload cho nhiều consumer bất đồng bộ, phải tạo ownership riêng cho mỗi consumer bằng `retain()` hoặc copy dữ liệu. Không phát cùng một instance `Payload` cho nhiều nơi rồi để nhiều nơi cùng release một tham chiếu.

## 6. Server nhận request và trả response

Với raw responder API, khi dùng `ZERO_COPY`, handler nhận inbound `Payload` và phải release sau khi đọc xong. Payload response được tạo mới và chuyển cho RSocket runtime khi publisher phát nó.

```java
@Override
public Mono<Payload> requestResponse(Payload request) {
    return Mono.fromSupplier(request::getDataUtf8)
        .map(text -> DefaultPayload.create("echo: " + text))
        .doFinally(signal -> request.release());
}
```

`doFinally` chạy khi publisher kết thúc bằng complete, error hoặc cancel, vì vậy request được release cả khi xử lý lỗi hoặc requester hủy. Ví dụ này giả định server đang dùng `PayloadDecoder.ZERO_COPY`. Với `PayloadDecoder.DEFAULT`, việc release inbound request không bắt buộc.

Response `DefaultPayload` được trả ra từ handler. Không thêm `doFinally(response::release)` ở phía server sau khi đã phát response, vì quyền sở hữu outbound response đã được chuyển cho RSocket runtime để mã hóa và gửi frame.

Với Fire-and-Forget, handler cũng phải giữ inbound payload đủ lâu để xử lý:

```java
@Override
public Mono<Void> fireAndForget(Payload request) {
    return Mono.fromRunnable(() -> telemetryService.accept(
            request.getDataUtf8()
        ))
        .doFinally(signal -> request.release());
}
```

Ở ví dụ này, service nhận `String` đã được copy ra khỏi payload. Nếu service cần giữ nguyên `Payload` để xử lý bất đồng bộ, phải giữ ownership bằng `retain()` hoặc chuyển quyền sở hữu cho publisher/service theo một hợp đồng rõ ràng.

## 7. Request-Channel: mỗi payload có vòng đời riêng

Request-Channel nhận một publisher payload từ requester và trả một publisher payload ngược lại. Khi server bật zero-copy, mỗi payload inbound phát ra từ publisher đầu vào cần được release sau khi decode. Mỗi payload response mới được chuyển cho RSocket runtime.

```java
@Override
public Flux<Payload> requestChannel(Publisher<Payload> inbound) {
    Flux<ClientCommand> commands = Flux.from(inbound)
        .map(payload -> {
            try {
                return decodeCommand(payload.getDataUtf8());
            } finally {
                payload.release();
            }
        });

    return commands
        .concatMap(command -> deviceService.apply(command))
        .map(state -> DefaultPayload.create(encodeState(state)));
}
```

Ví dụ này giả định inbound decoder là `ZERO_COPY`. `map` chuyển dữ liệu thành `ClientCommand` độc lập rồi release payload ngay sau khi decode. `concatMap` giữ thứ tự xử lý lệnh; payload kết quả được tạo mới và chuyển tới RSocket runtime. Nếu `decodeCommand` trả về một đối tượng vẫn tham chiếu trực tiếp tới `ByteBuf` của payload, không thể release ngay tại đây; cần copy dữ liệu hoặc giữ một retained reference tới khi đối tượng không còn sử dụng.

Ở client, publisher request nên tạo payload mới cho mỗi lệnh:

```java
Flux<Payload> outbound = commandSource.commands()
    .map(command -> DefaultPayload.create(encodeCommand(command)));

Flux<String> updates = socket.requestChannel(outbound)
    .map(payload -> {
        try {
            return payload.getDataUtf8();
        } finally {
            payload.release(); // inbound ZERO_COPY response
        }
    });
```

Không tái sử dụng cùng một `Payload` cho nhiều lần phát. Khi payload đã được phát cho RSocket, hãy xem tham chiếu đó đã được chuyển cho implementation. Nếu cần replay cùng dữ liệu cho một subscriber khác, tạo payload mới từ dữ liệu đã copy hoặc giữ một tham chiếu riêng bằng `retain()` theo đúng vòng đời.

### 7.1. Payload bị loại khỏi queue khi hủy hoặc overflow

Một số toán tử Reactor có thể prefetch, buffer hoặc loại bỏ phần tử khi downstream hủy, khi có lỗi hoặc khi áp dụng chính sách overflow. Với inbound `ZERO_COPY`, những payload đã được đưa vào queue nhưng chưa đi qua `map` xử lý cũng cần được release nếu bị discard.

Có thể đăng ký discard hook ở phía downstream của toán tử có khả năng giữ/bỏ phần tử:

```java
Flux<Payload> queued = Flux.from(inbound)
    .publishOn(Schedulers.parallel(), 32)
    .doOnDiscard(Payload.class, Payload::release);

Flux<ClientCommand> commands = queued.map(payload -> {
    try {
        return decodeCommand(payload.getDataUtf8());
    } finally {
        payload.release();
    }
});
```

`map` release payload đã được xử lý; `doOnDiscard` xử lý phần tử bị toán tử upstream loại bỏ trước khi tới `map`. Chỉ cài discard hook khi pipeline có operator hỗ trợ discard và payload vẫn thuộc ownership của pipeline tại thời điểm bị loại bỏ. Không thêm hook trùng lặp khiến cùng một payload bị release hai lần. Kiểm tra semantics discard của từng operator Reactor đang sử dụng.

## 8. ByteBuf và ByteBuffer lấy ra từ Payload

`Payload` có thể cung cấp data/metadata dưới dạng `ByteBuf` hoặc `ByteBuffer`. Những giá trị này có thể là view trên vùng nhớ do payload quản lý, không nhất thiết là bản sao độc lập.

| API | Đặc điểm | Lưu ý ownership |
|---|---|---|
| `getDataUtf8()` / `getMetadataUtf8()` | Chuyển nội dung thành `String`. | String độc lập, có thể dùng sau khi payload được release. |
| `getData()` / `getMetadata()` | Trả `ByteBuffer` view. | Không mặc định là bản copy; chỉ dùng khi payload còn sống hoặc copy nếu cần giữ lâu hơn. |
| `data()` / `metadata()` | Trả `ByteBuf` backing data/metadata khi có thể. | Javadoc khuyến nghị dùng `sliceData()`/`sliceMetadata()`; không sửa nội dung gốc tùy tiện. |
| `sliceData()` / `sliceMetadata()` | Trả slice trên dữ liệu payload. | Slice chia sẻ vùng nhớ/ref count; không tự tạo một ownership độc lập. |
| `copy()` trên `ByteBuf` | Tạo vùng nhớ độc lập. | Bên tạo copy quản lý và release buffer mới nếu nó reference-counted. |
| `retainedSlice()` | Tạo slice và tăng reference count của vùng nhớ dùng chung. | Phải release retained slice riêng sau khi sử dụng. |

Ví dụ, nếu cần chuyển bytes sang tầng khác mà không muốn tầng đó phụ thuộc vòng đời `Payload`, có thể copy thành `byte[]`:

```java
byte[] detached;
try {
    detached = ByteBufUtil.getBytes(payload.sliceData());
} finally {
    payload.release();
}

return asyncStorage.write(detached);
```

Nếu muốn giữ một `ByteBuf` slice qua thời điểm payload gốc được release, cần retained slice:

```java
ByteBuf retainedData = payload.sliceData().retainedSlice();
payload.release();

return asyncStorage.write(retainedData)
    .doFinally(signal -> retainedData.release());
```

Trong ví dụ thứ hai, retained slice giữ vùng nhớ sống sau khi payload gốc được release. Khi thao tác bất đồng bộ kết thúc, slice phải được release. Nếu API `asyncStorage.write` nhận ownership của buffer, hãy thay đổi quy ước để chỉ một bên release; không để cả caller và callee cùng giải phóng cùng một tham chiếu.

## 9. retain khi chuyển qua ranh giới bất đồng bộ

Giả sử một callback nhận payload nhưng công việc thực tế chạy sau trên scheduler khác. Nếu callback hiện tại sẽ release payload khi kết thúc, tác vụ nền cần có một tham chiếu riêng trước khi callback trả về.

```java
Mono<Result> processAsync(Payload payload) {
    Payload asyncReference = payload.retain();

    return Mono.fromCallable(() -> parseAndProcess(asyncReference))
        .subscribeOn(Schedulers.boundedElastic())
        .doFinally(signal -> asyncReference.release());
}
```

`retain()` tạo thêm một tham chiếu cho publisher bất đồng bộ. Publisher release tham chiếu của nó khi complete, error hoặc cancel. Chủ sở hữu ban đầu vẫn chịu trách nhiệm release tham chiếu ban đầu theo hợp đồng của mình. Không dùng `retain()` chỉ để trì hoãn release mà không xác định ai sẽ release phần tham chiếu được thêm.

Nếu chỉ cần một giá trị nhỏ như ID, timestamp hoặc chuỗi, hãy trích xuất/copy giá trị đó trước khi chuyển qua scheduler. Copy dữ liệu thường dễ quản lý hơn việc giữ một buffer native sống lâu.

## 10. Spring RSocket và quyền sở hữu do codec quản lý

Trong ứng dụng Spring, `RSocketRequester` và `@MessageMapping` thường làm việc với kiểu dữ liệu nghiệp vụ thông qua `RSocketStrategies` và codec. Ví dụ:

```java
@MessageMapping("orders.status")
public Mono<OrderStatus> status(OrderQuery query) {
    return orderService.findStatus(query.orderId());
}

Mono<OrderStatus> result = requester
    .route("orders.status")
    .data(new OrderQuery(orderId))
    .retrieveMono(OrderStatus.class);
```

Ở mức DTO như `OrderQuery` hoặc `OrderStatus`, ứng dụng không gọi `Payload.release()` vì codec quản lý payload/buffer nội bộ và chuyển đổi thành đối tượng Java. Quy tắc ownership ở API raw `Payload` không được áp dụng máy móc lên DTO, `String` hoặc object thông thường.

Nếu chọn nhận/trả `Payload`, `ByteBuf` hoặc `DataBuffer` thô, cần xem hợp đồng của API Spring và codec cụ thể đang dùng. `DataBuffer` của Spring cũng có thể reference-counted khi được backed bởi Netty; khi giữ hoặc chuyển DataBuffer qua nhiều tầng, dùng các API retain/release tương ứng như `DataBufferUtils.retain` và `DataBufferUtils.release` theo đúng ownership contract. Không release một buffer đã được framework chuyển quyền sở hữu cho component khác.

## 11. Các lỗi ownership thường gặp

| Lỗi | Nguyên nhân | Hậu quả |
|---|---|---|
| Memory leak | Không release inbound zero-copy payload hoặc retained slice. | Direct memory tăng, Netty báo leak, ứng dụng có thể cạn native memory. |
| Double release | Hai tầng cùng nghĩ mình sở hữu một tham chiếu và đều release. | `IllegalReferenceCountException` hoặc buffer bị giải phóng quá sớm. |
| Use-after-release | Async task đọc payload sau khi chủ sở hữu trước đã release. | Lỗi truy cập buffer đã giải phóng, thường là `IllegalReferenceCountException`. |
| Retain không release | Tăng refCnt nhưng không có cleanup tương ứng. | Buffer vẫn sống dù không còn consumer. |
| Release khi publisher chưa xử lý xong | Release payload ngay sau khi tạo publisher bất đồng bộ. | Tác vụ đọc payload lỗi vì backing memory đã được trả lại. |
| Dùng chung một Payload cho nhiều lần gửi | Một instance được phát nhiều lần hoặc nhiều subscriber cùng release. | Race condition, double release hoặc dữ liệu không còn hợp lệ. |
| Release mọi Payload bất kể decoder | Áp dụng quy tắc zero-copy cho cả decoder mặc định và tầng codec cao. | Làm sai ownership contract của implementation/framework. |

Một nguyên tắc hữu ích: ở mỗi ranh giới, hãy ghi rõ một trong ba trạng thái — **giữ quyền sở hữu**, **mượn để đọc trong thời gian giới hạn**, hoặc **chuyển quyền sở hữu**. Nếu cần chia sẻ đồng thời, hãy tạo thêm tham chiếu hoặc bản sao và gán rõ người chịu trách nhiệm release từng phần.

## 12. Kiểm thử và phát hiện memory leak

Các bài kiểm thử nên bao phủ cả đường thành công và đường lỗi:

1. Tạo payload, kiểm tra `refCnt()` ban đầu và xác nhận release cuối cùng đưa bộ đếm về `0`.
2. Với zero-copy, nhận response rồi xác nhận mỗi payload được release sau khi decode.
3. Làm handler phát sinh exception; xác nhận `doFinally`/cleanup vẫn release inbound payload.
4. Hủy Request-Stream hoặc Request-Channel giữa chừng; xác nhận các payload đã nhận được release và retained references được dọn.
5. Giữ một retained slice qua tác vụ bất đồng bộ; xác nhận slice còn đọc được trước cleanup và được release sau cleanup.
6. Thử nhiều consumer; xác nhận mỗi consumer có ownership riêng hoặc nhận bản copy.
7. Chạy kiểm thử tải với Netty leak detection để phát hiện buffer không được release.

Có thể bật leak detector chi tiết trong môi trường kiểm thử:

```text
-Dio.netty.leakDetection.level=advanced
```

Khi cần truy vết sâu hơn, có thể thử `paranoid` trong một bài test ngắn, vì mức này tốn chi phí hơn. `touch("route=telemetry.live")` có thể bổ sung gợi ý vào báo cáo leak. Không nên bật chế độ nặng nhất liên tục trong production nếu chưa đánh giá overhead.

Ví dụ kiểm thử đơn giản cho một payload do test tự tạo:

```java
Payload payload = DefaultPayload.create("hello");
assertThat(payload.refCnt()).isEqualTo(1);

payload.release();

assertThat(payload.refCnt()).isZero();
```

Test này kiểm tra vòng đời của payload đơn lẻ; nó không thay thế integration test qua RSocket transport, nơi decoder, fragmentation, cancellation và các publisher bất đồng bộ cùng tham gia quản lý buffer.

## 13. Checklist trước khi bật ZERO_COPY

- Xác định rõ decoder nào được bật ở client và server.
- Ghi rõ ai release payload inbound trong từng handler.
- Với `Flux<Payload>`, release từng phần tử sau khi xử lý.
- Với outbound payload, chuyển ownership đúng một lần và không tái sử dụng cùng instance.
- Nếu cần dùng sau callback, chọn `retain()` hoặc copy dữ liệu.
- Mọi nhánh complete, error và cancel đều có cleanup.
- Không giữ `ByteBuf`/`ByteBuffer` view sau khi payload gốc đã release, trừ khi đã retained hoặc copy.
- Bật Netty leak detection trong kiểm thử và theo dõi direct memory khi chạy tải.
- Với Spring codec, phân biệt object đã decode với raw `Payload`/`DataBuffer`.

## 14. Kết luận

`Payload` có vòng đời gắn với reference count của buffer bên dưới. `retain()` tạo thêm một quyền sở hữu; mỗi quyền sở hữu phải được release đúng một lần. Trong RSocket Java, decoder mặc định copy inbound data và không yêu cầu ứng dụng release thủ công, còn `PayloadDecoder.ZERO_COPY` dùng retained slices nên ứng dụng phải giải phóng payload khi đã dùng xong. Hãy xác định ownership tại từng lời gọi, chuyển quyền sở hữu rõ ràng khi gửi/nhận, copy hoặc retain khi vượt qua ranh giới bất đồng bộ, và kiểm thử cả lỗi lẫn cancellation để tránh leak và double release.

Tài liệu tham khảo:

- [RSocket Java 1.1.5 — RSocketConnector và PayloadDecoder](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5 — RSocketServer và PayloadDecoder](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 — DefaultPayload](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/util/DefaultPayload.html)
- [RSocket Java — README và hướng dẫn Zero Copy](https://github.com/rsocket/rsocket-java)
- [Netty — ReferenceCounted API](https://netty.io/4.1/api/io/netty/util/ReferenceCounted.html)
