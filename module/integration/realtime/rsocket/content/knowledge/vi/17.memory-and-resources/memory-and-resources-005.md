# Giải phóng payload khi lỗi, hủy hoặc loại bỏ phần tử

Trong RSocket Java, một payload có thể chứa dữ liệu nằm ngoài heap của JVM thông qua Netty `ByteBuf`. Cách này giảm sao chép và tăng hiệu suất, nhưng bộ nhớ không được thu hồi chỉ bằng garbage collector. Ứng dụng phải quản lý vòng đời của payload đúng cách: giải phóng khi đã dùng xong, giữ tham chiếu khi xử lý bất đồng bộ và dọn những phần tử bị loại bỏ trước khi tới consumer.

Các lỗi thường gặp có hai dạng đối lập. Nếu quên `release()`, bộ nhớ direct/off-heap bị giữ lại và có thể dẫn tới memory leak hoặc hết direct memory. Nếu gọi `release()` quá sớm hoặc nhiều lần, ứng dụng có thể gặp `IllegalReferenceCountException`, đọc dữ liệu sau khi buffer đã được giải phóng hoặc làm hỏng xử lý đang chạy.

## 1. Vì sao Payload cần được giải phóng?

`io.rsocket.Payload` trong RSocket Java triển khai `ReferenceCounted`. Một payload có thể giữ các vùng nhớ cho data và metadata. Bộ đếm tham chiếu cho biết còn bao nhiêu quyền sở hữu đang giữ vùng nhớ đó.

Ba thao tác quan trọng:

- `retain()`: tăng reference count khi cần giữ thêm một quyền sở hữu.
- `release()`: giảm reference count khi một quyền sở hữu đã dùng xong. Khi bộ đếm về 0, vùng nhớ được thu hồi hoặc trả về pool.
- `refCnt()`: quan sát reference count để chẩn đoán trong test hoặc debug; không dùng nó làm cơ chế đồng bộ ownership giữa nhiều thread.

Ví dụ đơn giản:

```java
Payload payload = DefaultPayload.create("sensor=temperature;value=28.5");

try {
    System.out.println(payload.getDataUtf8());
} finally {
    payload.release();
}
```

`finally` bảo đảm payload được giải phóng cả khi việc đọc hoặc xử lý phát sinh exception. Không truy cập `payload`, `payload.data()` hoặc `payload.getData()` sau khi đã release hết quyền sở hữu.

## 2. Phân biệt PayloadDecoder.DEFAULT và ZERO_COPY

Đây là khác biệt quan trọng nhất khi quyết định có cần tự release payload nhận từ RSocket hay không.

| Decoder | Cách tạo payload nhận | Trách nhiệm giải phóng |
| --- | --- | --- |
| `PayloadDecoder.DEFAULT` | Sao chép data và metadata thành vùng nhớ độc lập với frame đầu vào | RSocket Java ghi rõ không cần theo dõi và release các payload nhận theo chế độ mặc định |
| `PayloadDecoder.ZERO_COPY` | Data và metadata là các retained slice của `ByteBuf` gốc | Ứng dụng phải release payload khi hoàn tất sử dụng |

Ví dụ bật zero-copy ở client:

```java
RSocketConnector connector = RSocketConnector.create()
        .payloadDecoder(PayloadDecoder.ZERO_COPY);
```

Và ở server:

```java
RSocketServer server = RSocketServer.create(acceptor)
        .payloadDecoder(PayloadDecoder.ZERO_COPY);
```

Zero-copy giúp giảm cấp phát và sao chép dữ liệu, nhưng chuyển trách nhiệm quản lý vòng đời buffer sang code tiêu thụ payload. Nếu ứng dụng chưa có quy tắc ownership rõ ràng cho mọi đường đi thành công, lỗi, hủy và discard, hãy dùng decoder mặc định.

Lưu ý: `Payload` vẫn có API `retain()` và `release()` kể cả khi dùng decoder mặc định. Khác biệt ở đây là payload nhận bởi decoder mặc định đã được copy và RSocket Java không yêu cầu ứng dụng theo dõi, release chúng như các retained slice của `ZERO_COPY`.

## 3. Xác định ai sở hữu payload

Trước khi thêm `release()`, hãy xác định payload đang thuộc quyền sở hữu của thành phần nào. Một quy tắc dễ áp dụng là mỗi quyền sở hữu được tạo ra phải có đúng một lần release tương ứng.

| Tình huống | Quy tắc thực hành |
| --- | --- |
| Nhận `Payload` raw với `ZERO_COPY` | Consumer chịu trách nhiệm release sau khi xử lý xong |
| Nhận `Payload` raw với `DEFAULT` | Không cần release để thu hồi frame buffer theo hướng dẫn của RSocket Java |
| Tạo payload rồi truyền vào API gửi của `RSocket` | Để RSocket runtime tiêu thụ payload; không release cạnh tranh trong lúc runtime còn encode/send |
| Payload bị filter hoặc drop trước khi gửi/tiêu thụ | Thành phần đã sở hữu payload phải giải phóng nó |
| Cần giữ payload qua một ranh giới bất đồng bộ | Giữ quyền sở hữu đến khi tác vụ thực sự không còn đọc buffer; dùng `retain()` nếu tạo thêm một quyền sở hữu độc lập |
| Dùng `ByteBuf` slice hoặc `ByteBuffer` view từ payload | View không tự tạo bản sao; không dùng sau khi payload hoặc buffer gốc đã được release |

Với payload outbound, hãy tạo payload mới cho mỗi request hoặc mỗi lần subscribe. Không dùng chung một `DefaultPayload` cho nhiều request đồng thời; implementation `DefaultPayload` không thread-safe. Khi đã chuyển payload cho API gửi, không tự release nó ngay sau lời gọi hoặc trong một callback chạy song song với quá trình encode.

Với API mức cao như Spring `RSocketRequester` và codec ánh xạ object Java sang payload, hãy để framework quản lý payload nội bộ. Ứng dụng chỉ cần tự quản lý khi trực tiếp nhận hoặc tạo raw `Payload`/`ByteBuf` và ownership thuộc về code của mình.

## 4. Giải phóng ngay sau khi xử lý đồng bộ

Nếu chỉ cần đọc nội dung rồi chuyển thành kiểu dữ liệu heap như `String`, `byte[]` hoặc DTO độc lập, hãy đọc/copy dữ liệu và release payload trong cùng một khối `try/finally`.

```java
private static String decodeAndRelease(Payload payload) {
    try {
        return payload.getDataUtf8();
    } finally {
        payload.release();
    }
}
```

Áp dụng trong một stream nhận raw payload ở chế độ `ZERO_COPY`:

```java
Flux<String> messages = socket
        .requestStream(DefaultPayload.create("subscribe:sensors"))
        .map(MyPayloadDecoder::decodeAndRelease);
```

`getDataUtf8()` tạo `String` độc lập, vì vậy sau khi phương thức trả về, chuỗi không còn phụ thuộc vào buffer của payload. Nếu cần đọc cả data và metadata, hãy đọc/copy cả hai trước khi release.

Ví dụ copy sang `byte[]`:

```java
private static byte[] copyDataAndRelease(Payload payload) {
    try {
        ByteBuffer source = payload.getData();
        byte[] copy = new byte[source.remaining()];
        source.get(copy);
        return copy;
    } finally {
        payload.release();
    }
}
```

Không trả `ByteBuffer` view hoặc `ByteBuf` slice ra khỏi phương thức này rồi release payload ngay. View có thể vẫn trỏ tới vùng nhớ đã được thu hồi. Nếu consumer phía sau cần buffer gốc, hãy chuyển giao ownership hoặc retain đúng cách thay vì chỉ trả view.

## 5. Giữ payload trong lúc xử lý bất đồng bộ

Một lỗi phổ biến là release payload ngay khi callback `onNext` kết thúc, trong khi một tác vụ database, file I/O hoặc scheduler khác vẫn đang đọc `ByteBuf`.

Nếu publisher xử lý bất đồng bộ có thể biểu diễn toàn bộ thời gian sử dụng payload, dùng `Mono.using` để gắn cleanup với vòng đời của tác vụ:

```java
Flux<StoredReading> stored = socket
        .requestStream(DefaultPayload.create("subscribe:sensors"))
        .map(OwnedPayload::new)
        .flatMap(owned -> Mono.using(
                () -> owned,
                resource -> Mono.defer(() -> sensorService.store(resource.payload())),
                OwnedPayload::releaseOnce
        ), 8)
        .doOnDiscard(OwnedPayload.class, OwnedPayload::releaseOnce);
```

Ví dụ này áp dụng khi đang dùng `PayloadDecoder.ZERO_COPY` và `sensorService.store` chỉ hoàn tất sau khi đã đọc xong data/metadata cần thiết. Trong ví dụ, service mượn payload để đọc và không tự release; `Mono.using` giữ quyền sở hữu và gọi cleanup khi publisher con hoàn tất, phát lỗi hoặc bị hủy. `doOnDiscard` xử lý các wrapper còn nằm trong queue và bị bỏ trước khi inner publisher bắt đầu. Concurrency được giới hạn ở 8 để tránh giữ quá nhiều payload đồng thời. `OwnedPayload` được định nghĩa ở phần tiếp theo.

Nếu tác vụ bên dưới không dừng đọc buffer ngay khi bị cancel, không được release buffer trong khi tác vụ đó vẫn có thể truy cập nó. Hãy phối hợp hủy tác vụ nền và chỉ release khi tác vụ đã ngừng sử dụng dữ liệu. Nếu tác vụ cần một quyền sở hữu độc lập, gọi `retain()` trước khi chuyển giao và release đúng một lần ở callback hoàn tất hoặc callback hủy của tác vụ đó.

Khi một worker bên ngoài pipeline cần giữ payload riêng, hãy `retain()` trước khi chuyển giao và để worker release quyền sở hữu đó bằng callback chỉ chạy sau lần đọc cuối cùng. Ví dụ hợp đồng minh họa:

```java
Payload backgroundReference = payload.retain();
try {
    backgroundWorker.submit(
            backgroundReference,
            backgroundReference::release
    ); // Worker gọi callback sau khi dừng đọc buffer, kể cả khi task lỗi/hủy.
} catch (RuntimeException error) {
    backgroundReference.release(); // submit thất bại trước khi nhận ownership.
    throw error;
} finally {
    payload.release(); // Kết thúc quyền sở hữu ban đầu của handler.
}
```

`submit` ở đây là API giả định của worker: khi nhận thành công, nó chịu trách nhiệm gọi callback đúng một lần sau khi không còn truy cập payload; nếu từ chối đồng bộ, nó không nhận ownership. Không thay callback này bằng `doFinally` của subscriber nếu cancellation không bảo đảm worker đã dừng đọc buffer. Nếu worker không thể dừng hoặc báo thời điểm dừng thực tế, hãy copy dữ liệu sang heap trước khi gửi nó đi.

## 6. Release payload bị filter hoặc loại bỏ

Trong Reactor, một phần tử có thể bị loại bỏ mà không tới subscriber cuối cùng. Ví dụ:

- `filter` loại phần tử không thỏa điều kiện.
- `skip` bỏ các phần tử đầu.
- `onBackpressureDrop` loại phần tử khi consumer không theo kịp.
- Operator có prefetch giữ phần tử trong queue rồi phải bỏ chúng khi downstream cancel hoặc upstream lỗi.

Với object cần cleanup như retained `Payload`, Reactor cung cấp `doOnDiscard`. Hook này có phạm vi cục bộ và chỉ được các operator hỗ trợ discard ở phía upstream nhìn thấy. Vì vậy cần đặt hook sau các operator có thể discard phần tử cần dọn. Reactor yêu cầu discard hook phải idempotent vì cùng một object có thể đi qua nhiều đường cleanup; `release()` trực tiếp không tự idempotent, nên ví dụ dưới đây bọc ownership bằng `AtomicBoolean`.

Một lớp ownership nhỏ giúp release an toàn đúng một lần:

```java
final class OwnedPayload {
    private final Payload payload;
    private final AtomicBoolean released = new AtomicBoolean();

    OwnedPayload(Payload payload) {
        this.payload = payload;
    }

    Payload payload() {
        // Chỉ truy cập trong lúc wrapper vẫn đang giữ ownership.
        return payload;
    }

    String readUtf8AndRelease() {
        try {
            return payload.getDataUtf8();
        } finally {
            releaseOnce();
        }
    }

    void releaseOnce() {
        if (released.compareAndSet(false, true)) {
            payload.release();
        }
    }
}
```

Sử dụng wrapper trong pipeline:

```java
Flux<String> messages = socket
        .requestStream(DefaultPayload.create("subscribe:sensors"))
        .map(OwnedPayload::new)
        .filter(item -> isRelevant(item.payload()))
        .publishOn(Schedulers.parallel(), 16)
        .map(OwnedPayload::readUtf8AndRelease)
        .doOnDiscard(OwnedPayload.class, OwnedPayload::releaseOnce);
```

Nếu `filter` loại một phần tử, `doOnDiscard` release wrapper đó. Nếu `publishOn` đã prefetch payload nhưng bị hủy trước khi phát xuống, operator có hỗ trợ discard có thể chuyển phần tử đang giữ tới hook. Nếu `readUtf8AndRelease` phát sinh lỗi khi đọc, `finally` giải phóng phần tử đang được xử lý. `releaseOnce()` ngăn cùng wrapper bị release hai lần khi có nhiều đường cleanup.

Đừng mặc định mọi operator đều hỗ trợ discard. Kiểm tra mục *Discard Support* trong Javadoc của operator đang dùng. Một số operator có callback drop riêng; trong trường hợp đó, dùng callback đó để giải phóng phần tử bị drop.

Ví dụ với `onBackpressureDrop`:

```java
Flux<OwnedPayload> bounded = source
        .map(OwnedPayload::new)
        .onBackpressureDrop(OwnedPayload::releaseOnce);
```

Callback drop được gọi cho phần tử bị loại theo chính sách của operator. Nếu pipeline còn các operator prefetch/filter khác, vẫn cần `doOnDiscard` đặt đúng vị trí cho những operator có hỗ trợ discard.

## 7. Cleanup khi pipeline phát lỗi

Khi một operator phát sinh lỗi trong lúc xử lý `onNext`, có hai nhóm tài nguyên cần nghĩ tới:

1. Phần tử hiện tại đang được operator xử lý.
2. Các phần tử khác đang nằm trong queue hoặc buffer chờ xử lý.

`doOnDiscard` chủ yếu xử lý nhóm thứ hai khi operator upstream hỗ trợ discard. Nó không thay thế cleanup cho phần tử hiện tại nếu hàm `map`, predicate hoặc callback đang xử lý phần tử đó ném exception.

Với phần tử hiện tại, dùng `try/finally` như `readUtf8AndRelease()` ở trên, hoặc dùng một scope như `Mono.using` để cleanup khi inner publisher kết thúc. Với các phần tử đang chờ trong queue, kết hợp `doOnDiscard` để operator có thể release chúng khi lỗi làm pipeline dừng.

Reactor còn có các hook toàn cục:

- `Hooks.onOperatorError`: xử lý lỗi phát sinh trong operator; nếu phần tử gây lỗi cần cleanup, hook có thể nhận phần tử đó.
- `Hooks.onNextDropped`: xử lý phần tử đến muộn từ một Publisher vi phạm tín hiệu, ví dụ phát `onNext` sau `onError` hoặc `onComplete`.

Hai hook này có phạm vi toàn cục, vì vậy chỉ cài đặt ở cấp ứng dụng khi thật sự cần và phải lọc đúng kiểu tài nguyên. Không dùng `onNextDropped` để thay cho `doOnDiscard`: phần tử bị `filter` loại là discard bình thường, không phải tín hiệu bất hợp lệ.

## 8. Cleanup khi subscriber hủy

Khi downstream gọi `cancel()`, upstream ngừng phát thêm dữ liệu theo hợp đồng Reactive Streams. Tuy nhiên, operator có prefetch có thể đang giữ các payload chưa phát trong queue. Nếu các payload đó là retained slice, chúng cần được release.

`doOnDiscard` có thể dọn các phần tử trong queue khi operator hỗ trợ discard. Đối với payload hiện đang được xử lý trong một tác vụ bất đồng bộ, tác vụ phải có cơ chế hủy và cleanup riêng. Đừng cho rằng `doFinally` ở cuối pipeline tự động release mọi payload đã từng đi qua stream.

Phân biệt các callback:

| Callback / operator | Mục đích | Không thay thế cho |
| --- | --- | --- |
| `doOnDiscard` | Cleanup phần tử bị operator upstream loại hoặc bỏ khỏi queue | Cleanup phần tử hiện tại đang xử lý và ném lỗi |
| `doOnCancel` | Phản ứng khi subscription bị hủy | Release từng payload đang nằm trong buffer |
| `doFinally` | Chạy một hành động khi complete, error hoặc cancel | Theo dõi ownership của từng phần tử |
| `onOperatorError` | Hook toàn cục cho lỗi trong operator, có thể cleanup phần tử gây lỗi | Discard bình thường do filter/skip |
| `onNextDropped` | Hook toàn cục cho tín hiệu onNext đến sai thời điểm | Cleanup các phần tử bị loại có chủ đích |

Ví dụ hủy một nguồn stream khi view đóng:

```java
Disposable subscription = messages
        .subscribe(this::render, this::showError);

// Khi view đóng:
subscription.dispose();
```

Lệnh `dispose()` hủy subscription. Các payload đang nằm trong queue cần được xử lý qua discard hook mà operator hỗ trợ; payload đang được xử lý phải được cleanup trong scope của tác vụ đó.

## 9. Tránh double-release và use-after-release

Những lỗi ownership thường gặp:

**Release hai lần:** hai callback cùng nghĩ mình sở hữu payload và cùng gọi `release()`. Reference count giảm quá mức và có thể phát sinh `IllegalReferenceCountException`.

**Release quá sớm:** payload được release ngay sau khi tạo `ByteBuffer` view, nhưng một tác vụ khác vẫn đọc view đó.

**Quên release khi filter:** phần tử không được phát xuống consumer nên đoạn `doOnNext` ở phía sau không bao giờ chạy.

**Chỉ cleanup khi complete:** pipeline kết thúc bằng error hoặc cancel, nên cleanup nằm trong `doOnComplete` không được gọi.

**Dùng chung payload giữa nhiều subscription:** một subscription release payload trong khi subscription khác vẫn đang sử dụng nó.

Để tránh các lỗi này:

- Ghi rõ ai nhận ownership và ai chịu trách nhiệm release ở mỗi ranh giới API.
- Mỗi quyền sở hữu có một cleanup path duy nhất; nếu chia sẻ tài nguyên, `retain()` cho quyền sở hữu bổ sung và release từng quyền đúng một lần.
- Dùng `try/finally`, `Mono.using` hoặc wrapper có `AtomicBoolean` để gắn cleanup với vòng đời thật.
- Không truy cập `ByteBuf`, `ByteBuffer` view hoặc `Payload` sau khi quyền sở hữu tương ứng đã release.
- Không đặt nhiều hook độc lập cùng release trực tiếp một `Payload` mà không có cơ chế phối hợp idempotent.
- Không dùng `refCnt() > 0` như một khóa đồng bộ; kiểm tra rồi release có thể race với thread khác.

`AtomicBoolean` trong `OwnedPayload` chỉ ngăn cleanup gọi `release()` lặp lại. Nó không làm cho việc đọc `ByteBuf` đồng thời với release trở nên an toàn; pipeline vẫn phải bảo đảm không còn tác vụ nào đọc buffer khi `releaseOnce()` chạy.

## 10. Khi dùng Spring RSocket và codec

Với cách dùng thông thường:

```java
Mono<SensorReading> reading = requester
        .route("sensors.latest")
        .retrieveMono(SensorReading.class);
```

Spring sử dụng encoder/decoder để chuyển giữa payload và object nghiệp vụ. Consumer nhận `SensorReading`, không trực tiếp sở hữu raw `Payload`, vì vậy không gọi `release()` trên DTO.

Nếu controller hoặc custom codec làm việc trực tiếp với `Payload`, `ByteBuf` hoặc decoder zero-copy, cần xác định rõ ai sở hữu tài nguyên và cleanup ở đâu. Đặc biệt, không giữ `ByteBuffer` view từ payload rồi đưa vào executor khác mà không giữ reference count của buffer gốc.

## 11. Kiểm thử và phát hiện memory leak

Một bài kiểm thử chỉ xác nhận kết quả dữ liệu là chưa đủ. Cần kiểm tra các nhánh cleanup:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Xử lý thành công | Payload zero-copy được release sau khi đọc xong |
| Decode ném exception | Payload hiện tại vẫn được release nhờ `finally` |
| `filter` loại phần tử | Discard hook release payload bị loại |
| Downstream cancel khi queue còn phần tử | Các phần tử được operator hỗ trợ discard được release |
| Inner async publisher lỗi | `Mono.using` chạy cleanup |
| Inner async publisher bị cancel | Cleanup chạy sau khi tác vụ không còn truy cập buffer |
| `onBackpressureDrop` loại phần tử | Callback drop release payload |
| Hai nhánh cleanup cùng thấy một wrapper | `releaseOnce()` chỉ release một lần |
| DEFAULT decoder | Không thêm release thủ công không cần thiết |

Có thể bật Netty leak detector ở mức nghiêm ngặt trong test:

```java
ResourceLeakDetector.setLevel(ResourceLeakDetector.Level.PARANOID);
```

Mức `PARANOID` có overhead lớn, phù hợp với test hoặc môi trường điều tra leak hơn là cấu hình production lâu dài. Kết hợp với test cancel/error có payload được prefetch để tìm đường cleanup bị thiếu.

Ví dụ kiểm tra phần tử bị `filter` loại đã được release:

```java
Payload raw = DefaultPayload.create("discard-me");
OwnedPayload owned = new OwnedPayload(raw);

StepVerifier.create(Flux.just(owned)
        .filter(item -> false)
        .doOnDiscard(OwnedPayload.class, OwnedPayload::releaseOnce))
        .verifyComplete();

assertThat(raw.refCnt()).isZero();
```

Test cần static import `Assertions.assertThat`. Có thể tạo thêm test với `publishOn` có prefetch, rồi cancel trước khi queue được drain để xác nhận các phần tử còn lại cũng được dọn.

Khi test trực tiếp một payload do test tạo và tự sở hữu, có thể kiểm tra `refCnt()` sau cleanup. Không gọi `getData()`, `data()` hoặc `getMetadata()` sau khi reference count đã về 0.

## 12. Checklist triển khai

- [ ] Xác định decoder đang dùng là `DEFAULT` hay `ZERO_COPY`.
- [ ] Với `ZERO_COPY`, ghi rõ ownership của từng raw `Payload`.
- [ ] Release payload sau xử lý đồng bộ bằng `try/finally`.
- [ ] Với xử lý bất đồng bộ, giữ payload đến khi tác vụ ngừng truy cập buffer.
- [ ] Dùng `retain()` khi chuyển giao một quyền sở hữu bổ sung và release quyền đó đúng một lần.
- [ ] Đặt `doOnDiscard` sau các operator upstream có thể discard payload.
- [ ] Dùng callback drop riêng cho operator như `onBackpressureDrop`.
- [ ] Cleanup phần tử hiện tại khi transform ném lỗi; không chỉ dựa vào discard hook.
- [ ] Dọn các phần tử đã prefetch khi cancel/error nếu operator hỗ trợ discard.
- [ ] Không nhầm `doFinally` hoặc `doOnCancel` với cleanup cho từng payload.
- [ ] Tránh double-release, use-after-release và chia sẻ payload không an toàn giữa subscriptions.
- [ ] Kiểm thử thành công, lỗi, cancel, filter, overflow và zero-copy leak.

Quản lý payload đúng cách là quản lý ownership, không phải thêm `release()` ở mọi nơi. Hãy xác định rõ ai đang giữ buffer, khi nào công việc cuối cùng đọc xong và những operator nào có thể loại bỏ phần tử. Khi các quy tắc đó được thể hiện bằng `try/finally`, `retain/release`, `using` và discard hook đúng vị trí, RSocket có thể tận dụng zero-copy mà vẫn giải phóng tài nguyên an toàn khi lỗi, hủy hoặc drop.

## Tài liệu tham khảo

- [RSocket Java — Zero Copy](https://github.com/rsocket/rsocket-java#zero-copy)
- [RSocket Java 1.1.5 — RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5 — RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 — DefaultPayload](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/util/DefaultPayload.html)
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html)
