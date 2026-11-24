# Phân biệt kết quả rỗng với tài nguyên không tồn tại

Trong ứng dụng RSocket, một truy vấn có thể hoàn tất mà không phát ra giá trị. Điều đó không tự động có nghĩa tài nguyên được hỏi không tồn tại. `Mono.empty()` diễn tả một publisher không phát phần tử nào rồi hoàn tất; `NOT_FOUND` là kết luận nghiệp vụ rằng tài nguyên được định danh không tồn tại hoặc không thể được tìm thấy theo phạm vi truy vấn. Hai ý nghĩa này có thể trùng nhau trong một contract đơn giản, nhưng không nên mặc định chúng luôn giống nhau.

Sự phân biệt này quan trọng khi thiết kế API realtime bằng Java và Spring Boot. Client cần biết mình đang nhận một kết quả hợp lệ nhưng không có dữ liệu, một danh sách rỗng, một tài nguyên không tồn tại, hay một lỗi kỹ thuật khiến kết quả chưa xác định. Nếu server dùng một tín hiệu rỗng cho tất cả tình huống, client khó quyết định có hiển thị trạng thái “không có dữ liệu”, báo “không tìm thấy”, thử lại hay yêu cầu người dùng kiểm tra đầu vào.

## 1. `Mono.empty()` biểu diễn điều gì?

Trong Project Reactor, `Mono<T>` có thể phát tối đa một phần tử. Một `Mono` có ba kết quả kết thúc thường gặp:

- **Có giá trị:** phát một phần tử bằng `onNext(value)`, sau đó hoàn tất bằng `onComplete()`.
- **Rỗng:** không phát `onNext`, chỉ phát `onComplete()`.
- **Lỗi:** phát `onError(error)` và kết thúc.

`Mono.empty()` thuộc trường hợp thứ hai. Nó nói rằng publisher đã hoàn tất mà không có giá trị để chuyển xuống. Nó không tự giải thích lý do vì sao không có giá trị. Nguồn có thể không tìm thấy bản ghi, bộ lọc không khớp, dữ liệu tùy chọn chưa được thiết lập hoặc một nhánh xử lý chủ động không phát kết quả.

```java
Mono<Device> device = repository.findById(deviceId);

device.subscribe(
    value -> display(value),
    error -> showFailure(error),
    () -> finishWithoutValue()
);
```

Trong ví dụ, callback hoàn tất không có giá trị chỉ cho biết `Mono` đã kết thúc rỗng. Client hoặc service gọi nó không thể suy ra lý do nghiệp vụ nếu contract không định nghĩa rõ.

Một điểm khác cần nhớ: Reactor không cho phép `null` là phần tử phát ra. Các API như `Mono.justOrEmpty(nullableValue)` chuyển giá trị `null` thành `Mono.empty()`. Vì vậy, một lỗi lập trình như trả về `null` ngoài ý muốn có thể bị hiểu thành kết quả rỗng. Hãy xác định rõ nguồn nào được phép rỗng và kiểm thử trường hợp này.

## 2. Rỗng ở tầng Reactive Streams và RSocket

Ở tầng Reactive Streams, publisher rỗng hoàn tất mà không phát `onNext`. RSocket có thể biểu diễn việc hoàn tất một stream mà không có payload bằng frame `PAYLOAD` chỉ đặt cờ `COMPLETE` và không đặt cờ `NEXT`.

Với request-response, responder kết thúc tương tác bằng một frame `PAYLOAD` có cờ `COMPLETE`. Nếu response có giá trị, frame mang cả `NEXT` và `COMPLETE`. Nếu response hoàn tất rỗng, frame chỉ mang `COMPLETE`, không có sự kiện `onNext` ở tầng ứng dụng. Adapter Spring/RSocket ánh xạ các tín hiệu này vào kiểu reactive mà client sử dụng.

Không nên nhầm hai trường hợp sau:

| Trường hợp | Ý nghĩa ở tầng Reactive Streams | Cách hiểu ở ứng dụng |
|---|---|---|
| Empty completion | `onComplete()` không có `onNext` | Không có giá trị kết quả |
| Empty data payload | Có `onNext(payload)` nhưng data bytes có độ dài 0; có thể hoàn tất cùng frame | Có một payload hợp lệ, nhưng phần data rỗng |
| Giá trị nghiệp vụ “không tìm thấy” | Một phần tử response hoặc một lỗi theo contract | Server xác nhận resource không tồn tại trong phạm vi truy vấn |

RSocket phân biệt cờ `NEXT` với độ dài data. Vì thế, một payload có data rỗng vẫn có thể là một phần tử hợp lệ. Empty completion lại không phát phần tử nào. Đây là khác biệt ở tầng protocol, không chỉ là cách đặt tên trong Java.

## 3. Tài nguyên không tồn tại là kết quả nghiệp vụ

`NOT_FOUND` trả lời một câu hỏi cụ thể: tài nguyên được định danh không tồn tại hoặc không được tìm thấy trong phạm vi mà server có quyền truy vấn. Đây là kết luận nghiệp vụ, có thể cần được hiển thị, ghi nhận hoặc xử lý khác với trường hợp không có kết quả.

Ví dụ:

- `device.status` hỏi trạng thái thiết bị có ID `device-42`; server xác nhận ID đó không tồn tại.
- `orders.search` tìm đơn hàng theo bộ lọc; không có đơn hàng nào khớp bộ lọc.
- `profile.preferences` đọc một tùy chọn có thể chưa từng được thiết lập.
- `cache.lookup` không có bản sao trong cache, nhưng dữ liệu vẫn có thể tồn tại ở database.

Các ví dụ này không có cùng semantics. Một thiết bị không tồn tại khác với một truy vấn tìm kiếm hợp lệ nhưng không có kết quả. Cache miss cũng không có nghĩa resource không tồn tại. Contract cần nêu rõ điều server đã xác nhận.

Một cách thiết kế là trả về response có trạng thái rõ ràng:

```java
public enum LookupStatus {
    FOUND,
    NOT_FOUND
}

public record DeviceLookupResult(
    LookupStatus status,
    String deviceId,
    Device device
) {
    public static DeviceLookupResult found(Device device) {
        return new DeviceLookupResult(
            LookupStatus.FOUND, device.id(), device);
    }

    public static DeviceLookupResult notFound(String deviceId) {
        return new DeviceLookupResult(
            LookupStatus.NOT_FOUND, deviceId, null);
    }
}
```

Response này luôn có một giá trị. Client phân biệt được tài nguyên đã tìm thấy với trường hợp server xác nhận không tồn tại. Trong code production, có thể dùng một kiểu dữ liệu phân nhánh rõ hơn để tránh trường `device` bị `null` khi `NOT_FOUND`, chẳng hạn sealed interface với hai record `Found` và `NotFound`.

## 4. Khi nào nên trả kết quả rỗng, khi nào nên trả NOT_FOUND?

Hãy chọn theo ý nghĩa mà API muốn cam kết:

| Tình huống | Biểu diễn phù hợp | Lý do |
|---|---|---|
| Truy vấn tùy chọn: không có cấu hình thì bỏ qua | `Mono.empty()` | Không có giá trị là một kết quả bình thường đã được định nghĩa |
| Tìm một resource theo ID và cần thông báo rõ | Response `FOUND` / `NOT_FOUND` hoặc application error theo contract | Client cần biết resource không tồn tại |
| Tìm danh sách nhưng không có phần tử khớp | `Mono.just(List.of())` hoặc `Flux.empty()` | Kết quả là một tập hợp rỗng, không phải thiếu response |
| Cache miss, có thể đọc từ nguồn khác | Kết quả cache miss riêng hoặc `Mono.empty()` nội bộ | Cache không phải nguồn dữ liệu cuối cùng |
| Dependency lỗi hoặc timeout | `onError` | Không thể kết luận resource không tồn tại |
| Client không đủ quyền | Lỗi authorization hoặc kết quả từ chối theo chính sách | Không tiết lộ sự tồn tại của resource nếu chính sách yêu cầu che giấu |

Với truy vấn danh sách, hãy trả một collection rỗng nếu contract nói rằng request thành công và chỉ không có phần tử nào khớp. Ví dụ `Mono<List<Order>>` có thể phát `List.of()`; `Flux<Order>` có thể hoàn tất mà không phát phần tử. Cả hai đều khác với một request không có response do lỗi transport.

Đối với một truy vấn đơn lẻ, `Mono.empty()` có thể là lựa chọn hợp lý nếu contract nói rõ “không có giá trị là kết quả bình thường”. Nếu client phải phân biệt “không tồn tại”, “bị ẩn do quyền truy cập” và “chưa được tạo”, hãy dùng response DTO hoặc lỗi nghiệp vụ có mã riêng.

## 5. Triển khai truy vấn đơn với Spring RSocket

Giả sử ứng dụng có route `devices.get` để lấy thiết bị theo ID. Service repository trả `Mono<Device>` và hoàn tất rỗng khi không có bản ghi:

```java
public interface DeviceRepository {
    Mono<Device> findById(String deviceId);
}
```

Nếu contract cho phép empty completion có nghĩa là “không có kết quả”, handler có thể chuyển tiếp `Mono` đó:

```java
@Controller
public class DeviceController {
    private final DeviceRepository repository;

    public DeviceController(DeviceRepository repository) {
        this.repository = repository;
    }

    @MessageMapping("devices.get")
    public Mono<Device> get(@Payload DeviceQuery query) {
        return repository.findById(query.deviceId());
    }
}
```

Client cần xử lý cả trường hợp publisher hoàn tất mà không có giá trị:

```java
Mono<Device> device = requester
    .route("devices.get")
    .data(new DeviceQuery("device-42"))
    .retrieveMono(Device.class)
    .switchIfEmpty(Mono.error(
        new DeviceMissingResultException("No device result")));
```

Trong ví dụ này, client chọn coi empty completion là bất thường đối với contract của route và chuyển nó thành lỗi ứng dụng ở phía client. Nếu contract quy định empty completion chính là “không tìm thấy”, client có thể xử lý bằng `switchIfEmpty` để tạo trạng thái giao diện tương ứng. Điều quan trọng là hai phía phải thống nhất ý nghĩa.

Nếu cần trả `NOT_FOUND` một cách tường minh, handler có thể chuyển kết quả repository thành response DTO:

```java
@MessageMapping("devices.lookup")
public Mono<DeviceLookupResult> lookup(@Payload DeviceQuery query) {
    return repository.findById(query.deviceId())
        .map(DeviceLookupResult::found)
        .defaultIfEmpty(DeviceLookupResult.notFound(query.deviceId()));
}
```

Client lúc này luôn nhận một `DeviceLookupResult` khi xử lý thành công. Không cần suy luận trạng thái từ việc `Mono` có phát phần tử hay không.

## 6. `switchIfEmpty`, `defaultIfEmpty` và `onErrorResume`

Ba operator này xử lý ba tình huống khác nhau:

- `switchIfEmpty(alternative)` đăng ký publisher thay thế nếu nguồn hoàn tất mà không phát phần tử.
- `defaultIfEmpty(value)` phát giá trị mặc định nếu nguồn hoàn tất rỗng.
- `onErrorResume(error -> fallback)` xử lý khi nguồn phát lỗi.

Ví dụ kết hợp:

```java
Mono<DeviceLookupResult> result = repository.findById(deviceId)
    .map(DeviceLookupResult::found)
    .defaultIfEmpty(DeviceLookupResult.notFound(deviceId))
    .onErrorResume(DatabaseUnavailableException.class, error ->
        Mono.error(new DeviceQueryUnavailableException(error))
    );
```

Ở đây `defaultIfEmpty` chuyển trường hợp không có bản ghi thành kết quả nghiệp vụ `NOT_FOUND`. `onErrorResume` xử lý lỗi database riêng và vẫn phát lỗi đã được ánh xạ. Không dùng `onErrorResume` để biến mọi lỗi thành `NOT_FOUND`, vì timeout hoặc database outage không chứng minh resource không tồn tại.

Nếu repository có thể trả về `null` thay vì `Mono`, hãy sửa ranh giới đó. `Mono.just(null)` là không hợp lệ; `Mono.justOrEmpty(value)` sẽ chuyển `null` thành empty completion và có thể che giấu lỗi dữ liệu. Đừng dùng việc chuyển `null` thành rỗng để né kiểm tra contract.

## 7. Danh sách rỗng khác với một phần tử bị thiếu

Truy vấn danh sách và truy vấn một resource có semantics khác nhau.

```java
Mono<List<Device>> devices = deviceRepository.findAllByGroup(groupId)
    .collectList();
```

Nếu không có thiết bị nào trong nhóm, `collectList()` phát một `List` rỗng. `Mono<List<Device>>` vẫn phát một phần tử là collection rỗng. Ngược lại, truy vấn `findById(id)` có thể hoàn tất rỗng nếu không có một device tương ứng.

| API | Không có bản ghi | Kết quả reactive |
|---|---|---|
| `Mono<Device> findById(id)` | Không có resource | Có thể `Mono.empty()` nếu contract cho phép |
| `Mono<List<Device>> findAll(group)` | Không có phần tử trong nhóm | `Mono.just(List.of())` qua `collectList()` |
| `Flux<Device> findAll(group)` | Không có phần tử | `Flux.empty()` |
| `Mono<LookupResult> lookup(id)` | Resource không tồn tại | `Mono.just(LookupResult.notFound(id))` |

Không nên trả `Mono.empty()` cho một endpoint tìm danh sách nếu client cần nhận một response DTO chứa tổng số kết quả, cursor hoặc thông tin phân trang. Hãy trả một page rỗng có cấu trúc.

## 8. NOT_FOUND dưới dạng lỗi ứng dụng

Một lựa chọn khác là chuyển resource không tồn tại thành exception và phát `onError`. Ví dụ:

```java
@MessageMapping("devices.get-required")
public Mono<Device> getRequired(@Payload DeviceQuery query) {
    return repository.findById(query.deviceId())
        .switchIfEmpty(Mono.error(
            new DeviceNotFoundException(query.deviceId())));
}
```

Ở phía RSocket, lỗi của một request có thể được gửi bằng frame `ERROR` với mã lỗi ứng dụng. Spring có thể ánh xạ exception qua handler xử lý lỗi, chẳng hạn `@MessageExceptionHandler`, để tạo thông tin lỗi phù hợp. Client nhận lỗi trong reactive pipeline và xử lý bằng `onErrorResume` hoặc các cơ chế lỗi tương ứng.

Chọn cách này khi việc không tồn tại được xem là điều kiện thất bại của thao tác. Ví dụ lệnh `devices.configure` yêu cầu một thiết bị đã đăng ký; không tìm thấy thiết bị khiến lệnh không thể thực hiện. Với truy vấn tùy chọn hoặc tìm kiếm không có kết quả là chuyện bình thường, response DTO hoặc empty completion thường dễ sử dụng hơn.

Không nên để exception message chứa thông tin nội bộ như câu SQL, tên bảng, token hoặc chi tiết hạ tầng. Mã lỗi cần ổn định; thông điệp hiển thị cho người dùng có thể được client bản địa hóa.

## 9. Phân biệt NOT_FOUND với lỗi kỹ thuật

Một truy vấn trả empty hoặc `NOT_FOUND` chỉ nên xảy ra khi server có đủ cơ sở để kết luận theo contract. Các lỗi hạ tầng phải giữ nguyên bản chất:

| Tình huống | Có thể kết luận NOT_FOUND? | Xử lý |
|---|---|---|
| Database truy vấn thành công, không có row | Có, nếu database là nguồn có thẩm quyền và contract xác định như vậy | Empty hoặc `NOT_FOUND` |
| Cache không có key | Không | Cache miss; đọc nguồn chính hoặc trả trạng thái cache miss nội bộ |
| Database timeout | Không | Timeout / dependency unavailable |
| Kết nối RSocket bị ngắt | Không | Transport error; kết quả có thể chưa xác định |
| Client gửi ID sai định dạng | Không | Validation error |
| User không có quyền xem resource | Không nhất thiết | Authorization error hoặc che giấu resource theo chính sách |
| Bản ghi đã bị xóa mềm | Phụ thuộc contract | Có thể `NOT_FOUND`, `DELETED` hoặc trạng thái riêng |

Đặc biệt, không được biến mọi exception thành `Mono.empty()`. Cách làm đó khiến lỗi database, lỗi deserialize hoặc bug trong service bị báo thành “không tìm thấy”, làm sai số liệu quan sát và khiến client đưa ra quyết định sai.

## 10. Timeout, cancellation và kết quả chưa xác định

Timeout phía client chỉ cho biết client không nhận được kết quả trong thời hạn đã đặt. Nó không chứng minh server đã kiểm tra resource và xác nhận không tồn tại. Tương tự, cancellation chỉ dừng nhu cầu nhận kết quả hoặc yêu cầu server dừng công việc nếu có thể; nó không tự rollback transaction.

Với truy vấn đọc, client có thể thử lại nếu lỗi tạm thời và chính sách cho phép. Với lệnh ghi, cần xem xét khả năng server đã commit trước khi kết nối mất. Hãy dùng idempotency key hoặc mã tham chiếu để client truy vấn trạng thái thay vì tự suy diễn rằng thao tác thất bại.

Ví dụ client áp dụng timeout và phân biệt lỗi:

```java
Mono<DeviceLookupResult> lookup = requester
    .route("devices.lookup")
    .data(new DeviceQuery(deviceId))
    .retrieveMono(DeviceLookupResult.class)
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(TimeoutException.class, error ->
        Mono.error(new DeviceLookupUnavailableException(error))
    );
```

Timeout được ánh xạ thành “không thể xác định kết quả trong thời hạn”, không phải `NOT_FOUND`. Đây là khác biệt quan trọng đối với các hệ thống realtime có kết nối không ổn định.

## 11. Thiết kế response contract rõ ràng

Trước khi chọn empty completion hay `NOT_FOUND`, hãy trả lời các câu hỏi sau:

1. Không có giá trị có phải là một kết quả thành công được dự kiến không?
2. Client có cần phân biệt “không tồn tại”, “chưa được tạo”, “bị ẩn” và “không có phần tử khớp” không?
3. Resource được kiểm tra từ nguồn dữ liệu có thẩm quyền hay chỉ từ cache?
4. Empty completion có thể bị client hoặc middleware hiểu nhầm thành server không trả response không?
5. Có cần trả thêm ID, trạng thái, cursor, version hoặc thời điểm kiểm tra không?
6. Những tình huống nào phải phát lỗi ứng dụng, lỗi authorization hoặc lỗi hạ tầng?

Với route public hoặc được nhiều client sử dụng, response DTO có status enum thường dễ mở rộng hơn việc dựa vào empty completion. Nếu contract rất đơn giản và empty completion có ý nghĩa rõ ràng, có thể dùng `Mono.empty()` nhưng phải ghi rõ trong tài liệu và kiểm thử cả hai phía.

## 12. Kiểm thử và quan sát

Kiểm thử nên bao gồm các nhánh sau:

- **Có kết quả:** `Mono` phát đúng một response và hoàn tất.
- **Empty completion:** không phát giá trị, hoàn tất thành công; client xử lý đúng theo contract.
- **Empty data payload:** một payload có data bytes bằng 0 vẫn được nhận như một phần tử nếu ứng dụng cho phép.
- **NOT_FOUND:** response DTO hoặc application error có mã đúng và không bị nhầm với empty completion.
- **Danh sách rỗng:** client nhận collection/page rỗng, không phải thiếu response.
- **Lỗi kỹ thuật:** timeout hoặc database outage không bị biến thành `NOT_FOUND`.
- **Authorization:** resource bị từ chối truy cập được xử lý theo chính sách, không làm lộ dữ liệu.
- **Tương thích:** client cũ xử lý được status mới hoặc trường response được bổ sung theo quy tắc tương thích.

`StepVerifier` có thể xác minh semantics của publisher:

```java
StepVerifier.create(Mono.<Device>empty())
    .expectComplete()
    .verify();

StepVerifier.create(Mono.error(new DeviceNotFoundException("device-42")))
    .expectError(DeviceNotFoundException.class)
    .verify();
```

Kiểm thử tích hợp RSocket nên xác minh cách framework ánh xạ empty completion, empty payload và lỗi qua transport. Theo dõi metric riêng cho số response rỗng, `NOT_FOUND`, authorization failure, timeout, lỗi transport và dependency unavailable. Nếu tất cả đều được đếm chung thành “không có dữ liệu”, nhóm vận hành sẽ khó tìm nguyên nhân khi hệ thống gặp sự cố.

## 13. Quy tắc thiết kế

1. Dùng `Mono.empty()` khi contract xác định không phát giá trị là một kết quả bình thường.
2. Dùng `NOT_FOUND` khi server cần xác nhận rõ tài nguyên không tồn tại trong phạm vi truy vấn.
3. Dùng collection/page rỗng cho truy vấn danh sách không có phần tử.
4. Dùng lỗi ứng dụng cho thao tác không thể tiếp tục vì resource bắt buộc không tồn tại.
5. Không chuyển timeout, lỗi database hoặc lỗi transport thành empty completion hay `NOT_FOUND`.
6. Phân biệt empty completion với một payload có data bytes bằng 0.
7. Xử lý `null` ở ranh giới dữ liệu; tránh để `justOrEmpty` che giấu bug ngoài ý muốn.
8. Ghi rõ semantics trong route contract và kiểm thử cả server lẫn client.

Kết quả rỗng là một trạng thái của luồng reactive: không có phần tử nào được phát trước khi hoàn tất. `NOT_FOUND` là kết luận của nghiệp vụ về một tài nguyên cụ thể. Khi API nói rõ sự khác biệt này, client có thể hiển thị đúng trạng thái, chọn retry phù hợp và tránh nhầm lỗi hạ tầng với việc dữ liệu không tồn tại.
