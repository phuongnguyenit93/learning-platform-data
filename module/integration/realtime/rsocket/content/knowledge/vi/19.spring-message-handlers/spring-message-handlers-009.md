# Kiểm tra dữ liệu đầu vào và xử lý lỗi giải mã

Một RSocket request chỉ nên đi vào logic nghiệp vụ sau khi server đã giải mã payload thành đúng kiểu dữ liệu và kiểm tra các điều kiện đầu vào. Với Spring RSocket, quá trình này thường diễn ra trước khi thân phương thức `@MessageMapping` được gọi: framework chọn decoder theo cấu hình MIME type, chuyển byte thành object Java, áp dụng Bean Validation nếu được khai báo, rồi mới chuyển object cho handler.

Vì vậy cần phân biệt lỗi giải mã, lỗi validation và lỗi nghiệp vụ. Mỗi loại xuất hiện ở một giai đoạn khác nhau, có cách xử lý và phản hồi khác nhau. Nếu gom tất cả thành một exception chung hoặc chỉ dùng `try/catch` trong thân handler, một số lỗi sẽ không được xử lý ở nơi dự kiến.

## 1. Đường đi của payload tới `@MessageMapping`

Một request RSocket có vùng data và có thể có metadata. Data MIME type và metadata MIME type được thống nhất khi thiết lập kết nối; Spring dùng `RSocketStrategies` để chọn encoder/decoder phù hợp.

Đường đi của một request điển hình:

```text
RSocket frame
     |
     v
Tách data và metadata
     |
     v
Đọc route / tìm @MessageMapping
     |
     v
Chọn Decoder theo MIME type và kiểu tham số
     |
     v
Chuyển byte thành DTO Java
     |
     v
Bean Validation (@Valid / @Validated)
     |
     v
Gọi thân phương thức @MessageMapping
     |
     v
Kiểm tra nghiệp vụ / gọi service
     |
     v
Mã hóa kết quả và gửi response
```

Các bước có thể phát sinh lỗi:

- Route hoặc metadata không hợp lệ khiến request không tìm được handler hoặc không trích xuất được metadata.
- MIME type không được hỗ trợ hoặc không có decoder phù hợp.
- JSON, CBOR hoặc Protobuf không hợp lệ, sai kiểu hoặc không thể ánh xạ sang DTO.
- Payload thiếu field bắt buộc, field có giá trị sai phạm vi hoặc vi phạm ràng buộc Bean Validation.
- Dữ liệu hợp lệ về cấu trúc nhưng vi phạm quy tắc nghiệp vụ, ví dụ thiết bị không thuộc tenant của requester.

Lỗi giải mã và lỗi validation xảy ra trong giai đoạn chuẩn bị tham số. Thân phương thức `@MessageMapping` có thể chưa được gọi, vì vậy `try/catch` bên trong thân phương thức không thể xử lý các lỗi này.

## 2. Cấu hình Decoder và MIME type nhất quán

`RSocketStrategies` tập hợp encoder, decoder và các thành phần liên quan đến metadata. Client và server cần thống nhất data MIME type, metadata MIME type và định dạng thực tế của byte được gửi.

Ví dụ cấu hình JSON bằng Jackson:

```java
@Configuration
public class RSocketCodecConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .build();
    }
}
```

Client có thể chọn data MIME type khi tạo requester:

```java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeType.valueOf("application/json"))
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
```

Server cũng phải có decoder tương thích trong `RSocketMessageHandler` hoặc cấu hình Spring Boot tương ứng. Data MIME type được khai báo trong `SETUP` áp dụng cho data trên kết nối đó; không nên gửi JSON nhưng khai báo CBOR, hoặc cấu hình hai phía dùng các định dạng không tương thích.

Spring Core có codec cơ bản cho `String`, `byte[]` và `ByteBuffer`. Các codec JSON, CBOR và Protobuf thường cần `spring-web` hoặc cấu hình starter phù hợp. Spring Boot có thể tự cấu hình một số codec theo dependency có mặt; hãy kiểm tra cấu hình thực tế của ứng dụng thay vì giả định mọi định dạng đều tự động được bật.

Metadata có MIME type và decoder riêng. Ví dụ route metadata được Spring hỗ trợ mặc định; nếu thêm metadata tùy chỉnh, cần đăng ký decoder và ánh xạ qua `MetadataExtractor`. Lỗi giải mã metadata không giống lỗi giải mã data của DTO.

## 3. Thiết kế DTO có ràng buộc đầu vào

DTO nên thể hiện rõ các điều kiện cơ bản của dữ liệu. Ví dụ một thiết bị gửi dữ liệu nhiệt độ:

```java
public record SensorReading(
        @NotBlank
        @Size(max = 64)
        String deviceId,

        @NotNull
        @DecimalMin("-40.0")
        @DecimalMax("125.0")
        BigDecimal temperatureC,

        @NotNull
        Instant measuredAt,

        @Size(max = 80)
        String source
) {}
```

Các annotation trên kiểm tra những điều kiện độc lập với database hoặc trạng thái hệ thống:

- `@NotBlank`: chuỗi không được null, rỗng hoặc chỉ chứa khoảng trắng.
- `@Size`: giới hạn độ dài chuỗi hoặc kích thước collection.
- `@NotNull`: giá trị phải tồn tại.
- `@DecimalMin` và `@DecimalMax`: giới hạn giá trị số thập phân.
- `@Valid`: kích hoạt kiểm tra đệ quy đối với object lồng nhau.

Nếu DTO chứa object con, hãy đánh dấu field đó bằng `@Valid` để các constraint bên trong cũng được kiểm tra:

```java
public record DeviceCommand(
        @NotBlank String commandId,
        @NotBlank String deviceId,
        @NotNull @Valid CommandOptions options
) {}

public record CommandOptions(
        @Min(1) @Max(10) int retryLimit,
        @NotNull Duration timeout
) {}
```

Với Spring Boot 3 / Spring Framework 6 trở lên, dùng annotation từ `jakarta.validation`. Dự án Spring Boot 2 cũ thường dùng namespace `javax.validation`; không trộn hai namespace trong cùng một ứng dụng. Thêm implementation Bean Validation, thường là dependency `spring-boot-starter-validation`, để validator thực sự được cung cấp.

## 4. Kích hoạt Bean Validation trong handler

Đặt `@Valid` hoặc `@Validated` trên tham số payload để Spring kiểm tra DTO trước khi gọi thân handler:

```java
@Controller
public class SensorController {

    private final SensorService sensorService;

    public SensorController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensors.reading")
    public Mono<ReadingAccepted> receive(
            @Valid @Payload SensorReading reading) {

        return sensorService.store(reading)
                .map(id -> new ReadingAccepted(id, "ACCEPTED"));
    }
}
```

Nếu payload không hợp lệ, Spring ném `MethodArgumentNotValidException` trong giai đoạn resolve argument. Service `sensorService.store` chưa được gọi. Điều này giúp chặn dữ liệu sai ngay tại biên giao tiếp.

`@Valid` thường phù hợp với validation theo annotation trên DTO. `@Validated` có thể dùng khi cần validation group. Đừng xem validation DTO là thay thế cho kiểm tra nghiệp vụ: một `deviceId` có thể đúng định dạng nhưng vẫn không tồn tại hoặc không thuộc quyền truy cập của requester.

## 5. Phân loại lỗi giải mã và lỗi validation

Hai loại lỗi này thường bị nhầm lẫn nhưng cần cách chẩn đoán khác nhau:

| Loại lỗi | Giai đoạn | Ví dụ | Handler nghiệp vụ đã chạy? |
| --- | --- | --- | --- |
| MIME type / decoder không hỗ trợ | Chọn decoder | Server không có decoder cho định dạng data được khai báo | Không |
| Decode / conversion | Chuyển byte thành object | JSON thiếu dấu ngoặc, CBOR hỏng, Protobuf không phân tích được | Không |
| Type mapping | Ánh xạ sang kiểu Java | Field có cấu trúc không tương thích với DTO | Không |
| Bean Validation | Kiểm tra constraint trên DTO | `deviceId` rỗng, nhiệt độ vượt giới hạn | Không |
| Business validation | Trong service hoặc handler | Thiết bị không tồn tại, requester không có quyền điều khiển | Có |

Các exception có thể gặp tùy codec và phiên bản Spring:

- `DecodingException` từ Spring Core codec khi decoder không thể giải mã byte.
- `MessageConversionException` khi lớp chuyển đổi message không thể chuyển payload sang kiểu đích.
- `MethodArgumentNotValidException` khi Bean Validation thất bại trong lúc resolve tham số.
- Exception nghiệp vụ do ứng dụng định nghĩa, ví dụ `DeviceNotFoundException` hoặc `DeviceAccessDeniedException`.

Exception thực tế có thể được bọc trong exception khác. Khi phân loại, hãy xem cause chain và log loại exception gốc; không dựa vào việc so sánh chuỗi `getMessage()`.

## 6. Chuẩn hóa phản hồi lỗi bằng `@MessageExceptionHandler`

Spring Messaging hỗ trợ `@MessageExceptionHandler` để xử lý exception phát sinh trong quá trình xử lý một mapped message. Có thể đặt handler trong cùng controller hoặc trong `@ControllerAdvice` để dùng chung giữa các controller.

Thiết kế một error DTO ổn định:

```java
public record ApiError(
        String code,
        String message,
        String correlationId,
        List<String> invalidFields
) {}
```

Ví dụ xử lý lỗi validation:

```java
@MessageExceptionHandler
public Mono<ApiError> handleValidation(MethodArgumentNotValidException ex) {
    List<String> fields = ex.getBindingResult() == null
            ? List.of()
            : ex.getBindingResult().getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .toList();

    return Mono.just(new ApiError(
            "INVALID_PAYLOAD",
            "Dữ liệu gửi lên không hợp lệ.",
            UUID.randomUUID().toString(),
            fields
    ));
}
```

Ví dụ xử lý lỗi decode:

```java
@MessageExceptionHandler({DecodingException.class, MessageConversionException.class})
public Mono<ApiError> handleDecode(Exception ex) {
    return Mono.just(new ApiError(
            "MALFORMED_PAYLOAD",
            "Không thể đọc dữ liệu gửi lên. Hãy kiểm tra định dạng payload.",
            UUID.randomUUID().toString(),
            List.of()
    ));
}
```

Ví dụ xử lý lỗi nghiệp vụ:

```java
@MessageExceptionHandler(DeviceNotFoundException.class)
public Mono<ApiError> handleDeviceNotFound(DeviceNotFoundException ex) {
    return Mono.just(new ApiError(
            "DEVICE_NOT_FOUND",
            "Không tìm thấy thiết bị được yêu cầu.",
            UUID.randomUUID().toString(),
            List.of("deviceId")
    ));
}
```

`@MessageExceptionHandler` có thể xử lý exception trong phạm vi một mapped handler, kể cả lỗi khi Spring chuẩn bị tham số. Tuy nhiên, lỗi transport, lỗi frame/protocol, lỗi thiết lập kết nối hoặc lỗi xảy ra trước khi xác định được mapped handler cần được quan sát và xử lý ở tầng RSocket/server phù hợp; không giả định controller advice có thể biến mọi lỗi kết nối thành response DTO.

## 7. Phân biệt error payload với lỗi kết thúc stream

Khi trả `ApiError` từ `@MessageExceptionHandler`, client có thể nhận một payload phản hồi theo hợp đồng ứng dụng. Đó là một cách biểu diễn lỗi ở tầng dữ liệu, không giống một terminal error signal của RSocket/Reactive Streams.

Chọn quy ước theo interaction:

| Interaction | Cách biểu diễn nên cân nhắc |
| --- | --- |
| Request-Response | Có thể trả `ApiError` như response payload nếu API định nghĩa rõ client phải kiểm tra `code` |
| Request-Stream | Nếu lỗi làm stream không thể tiếp tục, phát terminal error; nếu muốn stream tiếp tục, mô hình hóa lỗi thành một phần tử event có kiểu rõ ràng |
| Request-Channel | Phân biệt lỗi của một command với lỗi toàn channel; lỗi một command có thể là event `FAILED`, lỗi nghiêm trọng có thể kết thúc channel |
| Fire-and-Forget | Không có response payload để trả lỗi cho request đó; cần log/metric hoặc kênh xác minh riêng |

Đặc biệt, Fire-and-Forget không có đường response nghiệp vụ. `Mono<Void>` của client cho biết thao tác gửi hoàn tất theo API, không chứng minh server đã decode, validate hoặc xử lý thành công. Nếu caller cần biết dữ liệu bị từ chối, hãy dùng Request-Response hoặc thiết kế một route tra cứu/trạng thái riêng.

## 8. Không để lộ dữ liệu trong lỗi decode

Thông báo lỗi công khai cần đủ để client sửa request nhưng không tiết lộ nội dung nhạy cảm hoặc chi tiết triển khai.

Không trả trực tiếp:

- Stack trace, tên class nội bộ hoặc đường dẫn source code.
- Toàn bộ JSON/CBOR/Protobuf đầu vào.
- Giá trị field nhạy cảm như token, mật khẩu, thông tin định danh hoặc dữ liệu thiết bị riêng tư.
- Tên bảng, câu SQL, hostname hoặc chi tiết dịch vụ downstream.
- Nguyên văn exception message từ Jackson hoặc codec nếu chuỗi đó có thể chứa dữ liệu đầu vào.

Thay vào đó, trả mã lỗi ổn định như `MALFORMED_PAYLOAD`, `INVALID_PAYLOAD`, `UNSUPPORTED_DATA_FORMAT` hoặc `DEVICE_NOT_FOUND`. Có thể trả danh sách tên field không hợp lệ nếu những tên này an toàn để công khai; không trả `FieldError.getRejectedValue()`.

Ở phía server, ghi log có cấu trúc với route, interaction, correlation ID, loại exception gốc và error code. Chỉ ghi một phần payload đã được làm sạch khi thật sự cần điều tra. Đặt giới hạn kích thước log và escape ký tự điều khiển để tránh log injection.

## 9. Kiểm tra nghiệp vụ sau Bean Validation

Bean Validation kiểm tra cấu trúc và ràng buộc đơn giản. Các quy tắc cần truy vấn trạng thái hoặc quyền phải nằm trong service/domain layer.

Ví dụ:

```java
public Mono<ReadingAccepted> store(SensorReading reading) {
    return deviceRepository.findById(reading.deviceId())
            .switchIfEmpty(Mono.error(new DeviceNotFoundException()))
            .flatMap(device -> authorizationService
                    .canPublish(reading.deviceId())
                    .filter(Boolean::booleanValue)
                    .switchIfEmpty(Mono.error(new DeviceAccessDeniedException()))
                    .then(readingRepository.save(reading)))
            .map(saved -> new ReadingAccepted(saved.id(), "ACCEPTED"));
}
```

Handler chỉ điều phối:

```java
@MessageMapping("sensors.reading")
public Mono<ReadingAccepted> receive(@Valid SensorReading reading) {
    return sensorService.store(reading);
}
```

Không tin `deviceId`, tenant ID hoặc user ID do client tự khai trong data/metadata. Dùng danh tính đã xác thực từ security context để xác định quyền, rồi kiểm tra quyền truy cập với tài nguyên thực tế.

## 10. Xử lý dữ liệu stream và channel

Với Request-Stream hoặc Request-Channel, mỗi phần tử có thể được decode và validate riêng. Cần xác định chính sách khi một phần tử sai:

- **Dừng toàn bộ stream:** phù hợp khi phần tử lỗi làm trạng thái giao tiếp không còn đáng tin cậy.
- **Báo lỗi cho phần tử rồi tiếp tục:** phù hợp khi mỗi message độc lập và client cần tiếp tục gửi/nhận phần tử hợp lệ.
- **Cách ly phần tử lỗi:** ghi nhận event lỗi vào dead-letter hoặc kho riêng để điều tra, nhưng phải có giới hạn tài nguyên.

Ví dụ một channel điều khiển thiết bị có thể biểu diễn kết quả từng command:

```java
@MessageMapping("devices.commands")
public Flux<CommandResult> commands(Flux<DeviceCommand> input) {
    return input.concatMap(command -> deviceService.execute(command)
            .map(result -> CommandResult.completed(command.commandId(), result))
            .onErrorResume(DeviceCommandRejectedException.class, error ->
                    Mono.just(CommandResult.rejected(
                            command.commandId(), "COMMAND_REJECTED"))));
}
```

Đây là ví dụ về lỗi nghiệp vụ có thể tiếp tục channel. Cách áp dụng Bean Validation cho từng phần tử reactive phụ thuộc vào cách Spring resolve và decode publisher trong phiên bản đang dùng; hãy kiểm thử rõ ràng với một phần tử sai nằm giữa các phần tử hợp lệ. Nếu cần kiểm soát chắc chắn từng item, có thể decode thành DTO rồi gọi `Validator` trong pipeline trước khi chuyển sang service.

Ví dụ kiểm tra thủ công từng phần tử trong pipeline:

```java
public Flux<CommandResult> commands(Flux<DeviceCommand> input) {
    return input.concatMap(command -> Mono.defer(() -> {
        Set<ConstraintViolation<DeviceCommand>> violations =
                validator.validate(command);

        if (!violations.isEmpty()) {
            return Mono.just(CommandResult.invalid(
                    command.commandId(), "INVALID_COMMAND"));
        }

        return deviceService.execute(command)
                .map(result -> CommandResult.completed(command.commandId(), result));
    }));
}
```

Trong mã thực tế, cần xử lý trường hợp `commandId` cũng không hợp lệ hoặc null trước khi dùng nó để tạo error result. Không phản chiếu nguyên payload lỗi vào event phản hồi.

## 11. Kiểm thử decode, validation và error mapping

Nên tách các bài kiểm thử theo từng giai đoạn để biết lỗi xuất hiện ở đâu.

| Trường hợp | Cách kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| JSON hợp lệ | Gửi DTO bình thường | Handler được gọi và trả kết quả |
| JSON sai cú pháp | Gửi raw bytes với MIME type JSON | Nhận lỗi `MALFORMED_PAYLOAD` theo hợp đồng |
| MIME type không hỗ trợ | Dùng MIME type không có decoder | Request bị từ chối có kiểm soát; có log chẩn đoán |
| Thiếu field hoặc sai kiểu | Gửi JSON không ánh xạ được DTO | Lỗi decode/conversion, handler body không chạy |
| Bean Validation thất bại | Gửi DTO decode được nhưng vi phạm constraint | Nhận `INVALID_PAYLOAD`, service không được gọi |
| Lỗi nghiệp vụ | Gửi DTO hợp lệ nhưng device không tồn tại | Nhận `DEVICE_NOT_FOUND` |
| Dữ liệu nhạy cảm | Gửi token giả lập trong field sai | Response/log không làm lộ token |
| Stream có một item lỗi | Gửi item sai giữa các item hợp lệ | Hành vi tiếp tục/dừng đúng chính sách đã chọn |
| Fire-and-Forget | Gửi payload sai qua FNF | Không kỳ vọng response lỗi; kiểm tra log/metric phía server |

Ví dụ kiểm thử lỗi validation qua Request-Response:

```java
StepVerifier.create(requester
        .route("sensors.reading")
        .data(new SensorReading("", new BigDecimal("300"), Instant.now(), null))
        .retrieveMono(ApiError.class))
        .assertNext(error -> {
            assertThat(error.code()).isEqualTo("INVALID_PAYLOAD");
            assertThat(error.invalidFields()).contains("deviceId", "temperatureC");
        })
        .verifyComplete();
```

Ví dụ trên giả định API chọn trả `ApiError` như response payload thông qua `@MessageExceptionHandler`. Nếu hệ thống chọn terminal RSocket error thay cho error payload, bài test phải dùng `expectError...` và kiểm tra mã lỗi tương ứng.

Để kiểm tra decode lỗi, gửi `byte[]` không phải JSON hợp lệ trong khi connection khai báo data MIME type `application/json`, rồi xác minh error mapping. Việc dùng DTO bình thường qua `.data(dto)` không tạo được JSON sai cú pháp vì encoder sẽ tuần tự hóa object hợp lệ.

Ngoài kết quả phía client, hãy verify service mock không bị gọi khi decode hoặc Bean Validation thất bại. Điều này chứng minh request bị chặn trước khi đi vào nghiệp vụ.

## 12. Checklist triển khai

- [ ] Client và server thống nhất data MIME type, metadata MIME type và codec.
- [ ] `RSocketStrategies` có decoder cho mọi kiểu payload được hỗ trợ.
- [ ] DTO có constraint phù hợp và `@Valid` cho object lồng nhau.
- [ ] Dependency Bean Validation đã được thêm và validator hoạt động.
- [ ] Handler không chứa logic cố bắt lỗi decode xảy ra trước khi thân phương thức được gọi.
- [ ] `@MessageExceptionHandler` ánh xạ lỗi validation, decode và nghiệp vụ thành hợp đồng ổn định.
- [ ] Lỗi trước khi route/handler được xác định được quan sát ở tầng protocol/server.
- [ ] Không trả stack trace, raw payload, rejected value hoặc secret cho client.
- [ ] Kiểm tra quyền và trạng thái tài nguyên trong service/domain layer.
- [ ] Xác định rõ stream/channel tiếp tục với error event hay kết thúc bằng terminal error.
- [ ] Không kỳ vọng Fire-and-Forget trả lỗi nghiệp vụ về client.
- [ ] Integration test có payload sai cú pháp, MIME type sai, validation fail và business fail.

Kiểm tra đầu vào và xử lý lỗi giải mã là một phần của hợp đồng RSocket. Hãy để decoder chịu trách nhiệm chuyển byte thành kiểu dữ liệu, Bean Validation kiểm tra các ràng buộc cơ bản, service kiểm tra quy tắc nghiệp vụ và exception handler chuẩn hóa phản hồi. Khi phân biệt rõ từng giai đoạn, hệ thống sẽ từ chối dữ liệu sai sớm, cung cấp lỗi có ích cho client và giữ chi tiết kỹ thuật trong log nội bộ.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — `PayloadMethodArgumentResolver`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html)
- [Spring Framework — `MethodArgumentNotValidException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/MethodArgumentNotValidException.html)
- [Spring Framework — `MessageMapping`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
