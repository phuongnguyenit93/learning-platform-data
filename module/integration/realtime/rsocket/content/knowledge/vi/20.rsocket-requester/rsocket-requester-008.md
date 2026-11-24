# Truyền thông tin kiểu dữ liệu cho generic và Publisher

## Bối cảnh: codec cần biết kiểu của từng giá trị được trao đổi

RSocketRequester cho phép ứng dụng gửi và nhận DTO Java thay vì tự thao tác với byte buffer. Khi gọi một route, client cung cấp dữ liệu đầu vào bằng data(...) và khai báo kiểu response bằng retrieveMono(...) hoặc retrieveFlux(...). Spring dùng các codec trong RSocketStrategies để chuyển đổi giữa đối tượng Java và payload RSocket.

Với kiểu đơn giản như String, byte[] hoặc một DTO không generic, Spring thường có thể chọn codec dựa trên kiểu cụ thể. Nhưng Java dùng type erasure: thông tin tham số generic như Reading trong Envelope<Reading> không luôn còn sẵn ở runtime nếu chỉ truyền Class<?>. Với Publisher phát nhiều phần tử, Spring cũng cần biết kiểu của từng phần tử để chọn encoder và mã hóa đúng cách.

RSocketRequester cung cấp hai cách truyền gợi ý kiểu:

- **Class<?>** cho kiểu phần tử cụ thể, không cần giữ tham số generic.
- **ParameterizedTypeReference<?>** khi kiểu phần tử có chứa generic như Envelope<Reading>, List<DeviceEvent> hoặc Map<String, Reading>.

Các overload tương ứng có ở cả phía gửi dữ liệu Publisher và phía khai báo kiểu response. Dùng đúng gợi ý kiểu giúp codec chọn đúng cách encode/decode, tránh mất thông tin generic và giảm việc dò encoder lặp lại cho từng phần tử trong một luồng.

## 1. Vì sao generic type bị mất ở runtime?

Java giữ kiểu generic chủ yếu ở thời điểm biên dịch. Ví dụ, hai biến sau có kiểu khai báo khác nhau:

~~~java
List<Reading> readings;
List<DeviceEvent> events;
~~~

Nhưng ở runtime, cả hai đều có class là List. Nếu chỉ truyền List.class, codec không thể suy ra phần tử bên trong là Reading hay DeviceEvent từ Class đó.

Tình huống tương tự xảy ra với một DTO generic:

~~~java
record ApiEnvelope<T>(
    String requestId,
    String status,
    T data
) {}

record Reading(
    String sensorId,
    long sequence,
    double temperature
) {}
~~~

Kiểu ApiEnvelope<Reading> chứa nhiều thông tin hơn ApiEnvelope.class. Khi decode response, nếu chỉ cung cấp class raw, decoder không có đủ thông tin tĩnh để biết data phải được chuyển thành Reading. Tùy codec và cấu hình, trường này có thể được giải mã thành Map hoặc một kiểu tổng quát khác.

ParameterizedTypeReference cho phép giữ lại cả kiểu generic trong một đối tượng Type mà Spring có thể truyền cho codec.

## 2. Các overload kiểu dữ liệu của RSocketRequester

### Phía gửi: data(...)

RSocketRequester.RequestSpec có ba dạng chính:

| Cách gọi | Dùng khi nào | Gợi ý kiểu |
|---|---|---|
| data(Object data) | Gửi một giá trị hoặc một Publisher | Spring suy luận từ giá trị/producer và codec |
| data(Object producer, Class<?> elementClass) | Gửi Publisher có phần tử thuộc một class cụ thể | Kiểu của mỗi phần tử |
| data(Object producer, ParameterizedTypeReference<?> elementTypeRef) | Gửi Publisher có phần tử mang generic type | Kiểu đầy đủ của mỗi phần tử, gồm generic |

Hai overload có producer yêu cầu đầu vào là Reactive Streams Publisher hoặc một kiểu producer có thể được Spring ReactiveAdapterRegistry chuyển thành Publisher, chẳng hạn Mono hoặc Flux.

Ví dụ với phần tử không generic:

~~~java
Flux<Reading> readings = sensorService.readings("sensor-01");

Flux<IngestAck> acknowledgements = requester
    .route("sensor.readings.ingest")
    .data(readings, Reading.class)
    .retrieveFlux(IngestAck.class);
~~~

Reading.class là kiểu của từng giá trị do Publisher phát ra. Không truyền Flux.class hoặc Publisher.class, vì đó là kiểu container chứ không phải kiểu phần tử cần encode.

Gợi ý elementClass giúp Spring tìm encoder tương thích một lần trước khi xử lý luồng, thay vì phải kiểm tra kiểu và tìm encoder cho từng phần tử.

### Phía nhận: retrieveMono(...) và retrieveFlux(...)

Khi nhận response, client cũng cần khai báo kiểu đích:

| Cách gọi | Interaction response | Kiểu response |
|---|---|---|
| retrieveMono(Class<T>) | Request-response | Một giá trị T |
| retrieveMono(ParameterizedTypeReference<T>) | Request-response | Một giá trị generic T |
| retrieveFlux(Class<T>) | Request-stream hoặc request-channel | Nhiều giá trị T |
| retrieveFlux(ParameterizedTypeReference<T>) | Request-stream hoặc request-channel | Nhiều giá trị generic T |

Ví dụ nhận response có wrapper generic:

~~~java
Mono<ApiEnvelope<DeviceStatus>> status = requester
    .route("device.status")
    .data(new DeviceQuery("device-01"))
    .retrieveMono(
        new ParameterizedTypeReference<ApiEnvelope<DeviceStatus>>() {}
    );
~~~

Ở đây, ApiEnvelope<DeviceStatus> là kiểu của một response. ParameterizedTypeReference giúp decoder biết trường data phải được chuyển thành DeviceStatus.

Với response stream:

~~~java
Flux<ApiEnvelope<Reading>> readings = requester
    .route("device.readings")
    .data(new DeviceQuery("device-01"))
    .retrieveFlux(
        new ParameterizedTypeReference<ApiEnvelope<Reading>>() {}
    );
~~~

Mỗi payload response được decode thành một ApiEnvelope<Reading>.

## 3. ParameterizedTypeReference giữ generic type như thế nào?

ParameterizedTypeReference<T> dùng kỹ thuật super type token. Ta tạo một anonymous subclass với kiểu generic cụ thể:

~~~java
ParameterizedTypeReference<ApiEnvelope<Reading>> readingEnvelopeType =
    new ParameterizedTypeReference<ApiEnvelope<Reading>>() {};
~~~

Spring đọc kiểu generic được khai báo trên lớp con và giữ lại thông tin ApiEnvelope<Reading> dưới dạng Type. Đối tượng type reference có thể được tái sử dụng:

~~~java
Flux<ApiEnvelope<Reading>> readings = requester
    .route("device.readings")
    .data(new DeviceQuery("device-01"))
    .retrieveFlux(readingEnvelopeType);
~~~

Một số kiểu tham chiếu thường gặp:

~~~java
// Wrapper chứa một DTO.
new ParameterizedTypeReference<ApiEnvelope<Reading>>() {};

// Một phần tử là danh sách Reading.
new ParameterizedTypeReference<List<Reading>>() {};

// Map có key String và value là Reading.
new ParameterizedTypeReference<Map<String, Reading>>() {};

// Wrapper lồng nhiều cấp.
new ParameterizedTypeReference<ApiEnvelope<List<Reading>>>() {};
~~~

### Vì sao không dùng ApiEnvelope.class?

Đoạn sau chỉ giữ class raw:

~~~java
Mono<ApiEnvelope> result = requester
    .route("device.status")
    .retrieveMono(ApiEnvelope.class);
~~~

Khai báo này không giữ được kiểu của T. Nếu server trả ApiEnvelope<Reading>, decoder chỉ được cung cấp ApiEnvelope.class; nó không có thông tin generic cụ thể để chuyển data thành Reading một cách an toàn về kiểu.

Dùng type reference:

~~~java
Mono<ApiEnvelope<Reading>> result = requester
    .route("device.status")
    .retrieveMono(
        new ParameterizedTypeReference<ApiEnvelope<Reading>>() {}
    );
~~~

### Đừng tạo type reference từ một type variable chưa được giải quyết

Một phương thức generic như sau không tự động giữ được kiểu cụ thể của T:

~~~java
static <T> ParameterizedTypeReference<ApiEnvelope<T>> envelopeType() {
    return new ParameterizedTypeReference<ApiEnvelope<T>>() {};
}
~~~

Nếu T chỉ là type variable ở thời điểm gọi, type reference có thể vẫn chứa type variable thay vì kiểu thực tế. Với các route đã biết schema, nên tạo type reference tại nơi có kiểu cụ thể, ví dụ ApiEnvelope<Reading>. Nếu phải xây dựng type động từ reflection, cần cung cấp một Type đã được resolve rồi mới tạo ParameterizedTypeReference bằng forType(Type).

## 4. Truyền một giá trị generic

Khi gửi một DTO đơn giản không chứa generic, có thể dùng trực tiếp data(value). Với payload generic cần gợi ý kiểu rõ ràng, có thể bọc giá trị trong Mono một phần tử và truyền ParameterizedTypeReference.

Ví dụ client gửi một envelope chứa Reading và nhận envelope chứa DeviceStatus:

~~~java
ApiEnvelope<Reading> command = new ApiEnvelope<>(
    "req-1001",
    "NEW",
    new Reading("sensor-01", 1042, 28.4)
);

Mono<ApiEnvelope<DeviceStatus>> result = requester
    .route("device.process-reading")
    .data(
        Mono.just(command),
        new ParameterizedTypeReference<ApiEnvelope<Reading>>() {}
    )
    .retrieveMono(
        new ParameterizedTypeReference<ApiEnvelope<DeviceStatus>>() {}
    );
~~~

Ở đây có hai kiểu độc lập:

- Type reference truyền vào data(...) mô tả kiểu của request value được phát bởi Mono.
- Type reference truyền vào retrieveMono(...) mô tả kiểu response mà client mong nhận.

Server có thể khai báo handler với kiểu cụ thể:

~~~java
@MessageMapping("device.process-reading")
Mono<ApiEnvelope<DeviceStatus>> process(
        @Payload ApiEnvelope<Reading> command) {
    return deviceService.process(command.data())
        .map(status -> new ApiEnvelope<>(
            command.requestId(),
            "PROCESSED",
            status
        ));
}
~~~

Chữ ký handler cho Spring biết payload đầu vào là ApiEnvelope<Reading> và response là ApiEnvelope<DeviceStatus>. Tránh dùng raw ApiEnvelope nếu nghiệp vụ cần kiểu cụ thể ở trường data.

Nếu payload đầu vào không generic, ví dụ DeviceQuery, có thể tiếp tục dùng .data(new DeviceQuery(...)) như thông thường.

## 5. Truyền Publisher có phần tử generic

Một điểm quan trọng của RSocketRequester là data(...) chấp nhận Publisher. Nếu đầu vào là một Publisher nhiều phần tử, RSocketRequester có thể sử dụng request-channel khi kết hợp với response. Mỗi phần tử được phát sẽ trở thành một request payload trên channel.

Ví dụ client gửi luồng envelope chứa Reading:

~~~java
Flux<ApiEnvelope<Reading>> readings = sensorService.readings("sensor-01")
    .map(reading -> new ApiEnvelope<>(
        "reading-" + reading.sequence(),
        "NEW",
        reading
    ));

Flux<ApiEnvelope<IngestAck>> acknowledgements = requester
    .route("sensor.readings.ingest")
    .data(
        readings,
        new ParameterizedTypeReference<ApiEnvelope<Reading>>() {}
    )
    .retrieveFlux(
        new ParameterizedTypeReference<ApiEnvelope<IngestAck>>() {}
    );
~~~

Type reference trong data(...) mô tả một phần tử ApiEnvelope<Reading>, không phải toàn bộ Flux. Type reference trong retrieveFlux(...) mô tả một phần tử response ApiEnvelope<IngestAck>.

Server có thể nhận Publisher cùng kiểu generic:

~~~java
@MessageMapping("sensor.readings.ingest")
Flux<ApiEnvelope<IngestAck>> ingest(
        @Payload Flux<ApiEnvelope<Reading>> readings) {
    return readings.concatMap(envelope ->
        ingestService.store(envelope.data())
            .map(ack -> new ApiEnvelope<>(
                envelope.requestId(),
                "ACCEPTED",
                ack
            ))
    );
}
~~~

Spring có thể đọc generic signature của tham số Flux<ApiEnvelope<Reading>> trong method handler và dùng nó làm kiểu đích cho từng payload đầu vào. concatMap trong ví dụ xử lý tuần tự và giữ thứ tự acknowledgement theo thứ tự Reading nhận được.

### Khi phần tử Publisher là một collection

Cần phân biệt hai trường hợp:

~~~java
Flux<Reading> readings;
Flux<List<Reading>> batches;
~~~

Flux<Reading> phát một Reading trong mỗi payload. Flux<List<Reading>> phát một danh sách Reading trong mỗi payload. Nếu dùng Flux<List<Reading>>, hãy cung cấp kiểu phần tử đầy đủ:

~~~java
Flux<List<Reading>> batches = batchService.readingBatches();

Flux<BatchAck> acknowledgements = requester
    .route("sensor.reading-batches")
    .data(
        batches,
        new ParameterizedTypeReference<List<Reading>>() {}
    )
    .retrieveFlux(BatchAck.class);
~~~

Không nhầm generic bên trong phần tử với generic của Publisher. Publisher là nguồn phát; type reference mô tả giá trị mà nguồn phát ra ở mỗi lần onNext.

## 6. Chọn interaction model theo cardinality của input và output

Kiểu dữ liệu và cardinality là hai vấn đề riêng:

- Type hint xác định cách encode/decode từng giá trị.
- Cardinality xác định interaction model RSocket phù hợp.

Spring RSocketRequester xác định interaction dựa trên số lượng giá trị đầu vào và đầu ra:

| Input | Output | Interaction |
|---|---|---|
| Một giá trị hoặc Mono | Một giá trị hoặc Mono | Request-response |
| Một giá trị hoặc Mono | Flux | Request-stream |
| Flux hoặc Publisher nhiều giá trị | Không, một hoặc nhiều response | Request-channel; phía requester dùng retrieveFlux |

Ví dụ request-stream: một query và nhiều response:

~~~java
Flux<Reading> readings = requester
    .route("sensor.readings")
    .data(new DeviceQuery("sensor-01"))
    .retrieveFlux(Reading.class);
~~~

Ví dụ request-channel: nhiều command và nhiều acknowledgement:

~~~java
Flux<Command> commands = commandSource();

Flux<Ack> acknowledgements = requester
    .route("device.commands")
    .data(commands, Command.class)
    .retrieveFlux(Ack.class);
~~~

retrieveFlux(...) có thể thực hiện request-stream hoặc request-channel tùy cardinality của input. Với request-channel, responder có thể phát không response, một response hoặc nhiều response; requester vẫn dùng retrieveFlux để nhận kết quả của channel. Ngược lại, retrieveMono(...) dùng cho request-response và không hợp lệ nếu request input là Publisher nhiều phần tử, vì API requester không hỗ trợ kết hợp many-to-one. Nếu channel chỉ tiêu thụ input mà không phát payload response, có thể dùng kiểu response Void và để Flux hoàn tất sau khi dữ liệu được tiêu thụ.

Với fire-and-forget, dùng một request value và send(). send() xác nhận việc gửi message hoàn tất ở phía client; nó không xác nhận server đã xử lý nghiệp vụ thành công.

## 7. Kết hợp generic type với các overload Class và ParameterizedTypeReference

Có thể dùng quy tắc đơn giản sau để chọn overload:

| Kiểu phần tử cần gửi/nhận | Overload nên dùng |
|---|---|
| Reading | Reading.class |
| ApiEnvelope<Reading> | new ParameterizedTypeReference<ApiEnvelope<Reading>>() {} |
| List<Reading> | new ParameterizedTypeReference<List<Reading>>() {} |
| Map<String, DeviceStatus> | new ParameterizedTypeReference<Map<String, DeviceStatus>>() {} |
| ApiEnvelope<List<Reading>> | new ParameterizedTypeReference<ApiEnvelope<List<Reading>>>() {} |

Ví dụ một stream đơn giản có thể dùng Class hint:

~~~java
Flux<Reading> input = sensorService.readings(sensorId);

Flux<IngestAck> output = requester
    .route("sensor.ingest")
    .data(input, Reading.class)
    .retrieveFlux(IngestAck.class);
~~~

Ví dụ một stream có wrapper generic dùng ParameterizedTypeReference:

~~~java
Flux<ApiEnvelope<Reading>> input = sensorService.readings(sensorId)
    .map(reading -> ApiEnvelopeFactory.wrap(reading));

Flux<ApiEnvelope<IngestAck>> output = requester
    .route("sensor.ingest")
    .data(
        input,
        new ParameterizedTypeReference<ApiEnvelope<Reading>>() {}
    )
    .retrieveFlux(
        new ParameterizedTypeReference<ApiEnvelope<IngestAck>>() {}
    );
~~~

Nếu không có generic type, không cần tạo ParameterizedTypeReference chỉ để thay cho một Class đơn giản.

## 8. Codec và MIME type vẫn phải khớp

Type hint không thay thế codec. ParameterizedTypeReference cung cấp thông tin Java type cho Spring khi chọn encoder hoặc decoder. Codec thực tế vẫn phải hỗ trợ định dạng data đã thỏa thuận.

Ví dụ nếu payload là JSON, ứng dụng cần có JSON encoder và decoder trong RSocketStrategies, đồng thời client và server phải thống nhất data MIME type. Nếu dùng protobuf hoặc CBOR, cần codec tương ứng.

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
    .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
    .build();
~~~

Một ParameterizedTypeReference<ApiEnvelope<Reading>> không tự gửi tên class Java hoặc generic signature qua mạng. Nó là gợi ý kiểu ở phía đang encode hoặc decode. Peer bên kia phải có schema và kiểu handler tương thích của riêng nó.

Ví dụ, client decode ApiEnvelope<Reading> còn server encode một cấu trúc có trường khác hoặc data không phải Reading thì type reference không thể tự sửa hợp đồng. Hai phía cần thống nhất cấu trúc payload, tên field, định dạng và version schema.

## 9. Những lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng ApiEnvelope.class cho ApiEnvelope<Reading> | Mất thông tin kiểu của T | Dùng ParameterizedTypeReference |
| Truyền Flux.class làm elementClass | Codec nhận kiểu container thay vì kiểu phần tử | Truyền Reading.class hoặc type reference của phần tử |
| Dùng data(publisher) cho stream generic mà không có type hint | Encoder có thể phải kiểm tra kiểu và tìm encoder cho từng phần tử | Dùng overload Class hoặc ParameterizedTypeReference |
| Dùng new ParameterizedTypeReference<T>() {} khi T chưa resolve | Type reference có thể giữ type variable thay vì kiểu cụ thể | Tạo reference với kiểu concrete tại call site |
| Nhầm Publisher với payload đơn | Gửi nhiều giá trị nhưng mong request-response | Kiểm tra cardinality và chọn request-channel |
| Gửi Flux rồi gọi retrieveMono | Kết hợp many-to-one không được hỗ trợ | Dùng retrieveFlux hoặc thay input bằng một giá trị/Mono |
| Dùng Class cho collection generic | Không biết kiểu phần tử trong collection | Dùng ParameterizedTypeReference<List<...>> |
| Type hint client và handler server không tương thích | Decode sai hoặc lỗi codec | Đồng bộ schema và generic signature |
| Nghĩ type reference được gửi như metadata giao thức | Nhầm gợi ý local với dữ liệu trên wire | Coi type reference là thông tin cho codec cục bộ |
| Codec không hỗ trợ MIME type đã chọn | Không encode/decode được dù type hint đúng | Cấu hình encoder, decoder và MIME type tương ứng |
| Dùng raw Publisher hoặc Flux trong handler | Spring thiếu generic signature rõ ràng | Khai báo Flux<ConcreteGenericType> |

## 10. Kiểm thử generic payload và Publisher

Nên kiểm tra cả request và response generic. Unit test cho mapper hoặc DTO không đủ để xác nhận RSocket codec đã giải mã đúng nested type.

### Kiểm thử request-response với wrapper generic

~~~java
StepVerifier.create(
    requester.route("device.status")
        .data(new DeviceQuery("device-01"))
        .retrieveMono(
            new ParameterizedTypeReference<ApiEnvelope<DeviceStatus>>() {}
        )
)
.expectNextMatches(envelope ->
    envelope.data() instanceof DeviceStatus
        && envelope.data().deviceId().equals("device-01")
)
.verifyComplete();
~~~

Test này xác nhận response được decode thành kiểu cụ thể thay vì chỉ kiểm tra một JSON string.

### Kiểm thử request-channel với Publisher generic

~~~java
Flux<ApiEnvelope<Reading>> input = Flux.just(
    new ApiEnvelope<>("event-1", "NEW",
        new Reading("sensor-01", 1, 25.5)),
    new ApiEnvelope<>("event-2", "NEW",
        new Reading("sensor-01", 2, 26.0))
);

StepVerifier.create(
    requester.route("sensor.readings.ingest")
        .data(
            input,
            new ParameterizedTypeReference<ApiEnvelope<Reading>>() {}
        )
        .retrieveFlux(
            new ParameterizedTypeReference<ApiEnvelope<IngestAck>>() {}
        )
)
.expectNextMatches(ack -> ack.data().accepted())
.expectNextMatches(ack -> ack.data().accepted())
.verifyComplete();
~~~

Đây là integration test cần một responder route tương ứng. Ngoài kiểu generic, nên xác nhận:

- Số payload đầu vào và đầu ra.
- Thứ tự phần tử nếu nghiệp vụ yêu cầu.
- Lỗi khi payload không đúng schema.
- Cancellation khi client ngừng nhận.
- Backpressure khi consumer xử lý chậm.
- Hành vi với stream rỗng hoặc hoàn tất sớm.

### Kiểm tra ở server

Handler server nên dùng generic signature cụ thể:

~~~java
@MessageMapping("sensor.readings.ingest")
Flux<ApiEnvelope<IngestAck>> ingest(
        @Payload Flux<ApiEnvelope<Reading>> input) {
    return input.map(envelope -> {
        Reading reading = envelope.data();
        return new ApiEnvelope<>(
            envelope.requestId(),
            "ACCEPTED",
            new IngestAck(reading.sequence(), true)
        );
    });
}
~~~

Nếu server chỉ khai báo Flux raw, codec không có đầy đủ thông tin kiểu phần tử từ method signature. Giữ generic type trong chữ ký method giúp Spring xây dựng metadata kiểu cho từng payload.

## Kết luận

Khi dùng RSocketRequester với generic và Publisher, hãy phân biệt kiểu của một phần tử với kiểu của Publisher phát phần tử đó. data(Object) phù hợp cho giá trị thông thường hoặc producer khi Spring có thể suy luận; data(Object, Class<?>) cung cấp class hint cho phần tử; data(Object, ParameterizedTypeReference<?>) giữ đầy đủ generic type của phần tử. Ở chiều nhận, dùng retrieveMono hoặc retrieveFlux với ParameterizedTypeReference khi response có generic.

Type hint chỉ quyết định cách codec encode/decode; cardinality của input và output mới quyết định request-response, request-stream hay request-channel. Hãy khai báo generic cụ thể ở cả client và handler, đồng bộ schema/MIME type, tránh raw type và kiểm thử bằng RSocket integration test để xác nhận nested object được giải mã đúng.

## Tài liệu tham khảo

- [Spring Framework RSocket reference](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.RequestSpec API, Spring Framework 6.2.7](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html)
- [RSocketRequester.RetrieveSpec API, Spring Framework 6.2.7](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [ParameterizedTypeReference API, Spring Framework 6.2.8](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/core/ParameterizedTypeReference.html)
