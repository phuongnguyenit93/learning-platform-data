# Xử lý lỗi, hủy chuỗi phản ứng và giới hạn của việc lưu phiên

Trong ứng dụng Spring WebFlux, thao tác với session thường được biểu diễn bằng Reactor `Mono` và `Flux`. Cách làm này cho phép framework phối hợp I/O bất đồng bộ, nhưng cũng đặt ra những câu hỏi quan trọng: điều gì xảy ra khi Redis không truy cập được, khi session không tồn tại, khi client ngắt kết nối hoặc khi timeout hủy publisher? Một publisher bị hủy có bảo đảm thao tác ghi session chưa xảy ra không? Và việc dùng `WebSession` có làm cho cập nhật đồng thời trở nên an toàn không?

Câu trả lời phụ thuộc vào tín hiệu reactive, thời điểm repository bắt đầu ghi và bảo đảm của datastore. `ReactiveSessionRepository` giúp biểu diễn thao tác session bất đồng bộ; nó không tạo transaction nghiệp vụ, không bảo đảm exactly-once và không biến các request đồng thời thành một chuỗi tuần tự. Ứng dụng cần phân biệt rõ `Mono.empty()` với `onError`, nối thao tác lưu vào publisher, xử lý cancellation như một tín hiệu best-effort và đặt dữ liệu quan trọng trong kho nghiệp vụ có transaction.

Trong phạm vi `SPRING_SESSION`, bài học này tập trung vào WebFlux với `WebSession`, `ReactiveSessionRepository` và kho chia sẻ như Redis reactive. Mục tiêu là xử lý lỗi có phân loại, hiểu cancellation, bảo đảm lỗi lưu phiên được quan sát và nhận diện giới hạn của session khi nhiều request hoặc nhiều instance cùng hoạt động.

## 1. Hợp đồng reactive của repository

Repository reactive của Spring Session có hợp đồng tổng quát như sau:

```java
public interface ReactiveSessionRepository<S extends Session> {
    Mono<S> createSession();
    Mono<Void> save(S session);
    Mono<S> findById(String id);
    Mono<Void> deleteById(String id);
}
```

Mỗi phương thức trả về publisher, không trả ngay kết quả đã được thực hiện:

| Phương thức | Kết quả | Ý nghĩa |
|---|---|---|
| `createSession()` | `Mono<S>` | Phát ra session mới khi thao tác tạo hoàn tất |
| `findById(id)` | `Mono<S>` | Phát session nếu tìm thấy; có thể hoàn tất rỗng nếu không tồn tại hoặc không còn hợp lệ |
| `save(session)` | `Mono<Void>` | Hoàn tất khi thao tác lưu kết thúc theo cam kết repository |
| `deleteById(id)` | `Mono<Void>` | Hoàn tất khi thao tác xóa kết thúc theo cam kết repository |

`Mono<Void>` thường không phát `onNext`; kết quả thành công được biểu diễn bằng `onComplete`. Nếu thao tác thất bại, publisher phát `onError`. Nếu caller không subscribe hoặc publisher bị hủy trước khi thao tác bắt đầu, thao tác có thể không chạy hoặc không hoàn tất. Vì vậy, việc tạo publisher không đồng nghĩa dữ liệu đã được ghi xuống Redis.

Ví dụ, đoạn sau chỉ tạo publisher:

```java
Mono<Void> saveOperation = repository.save(session);
```

Nếu không nối `saveOperation` vào chuỗi được subscribe, không có bảo đảm thao tác lưu được thực hiện. Trong controller WebFlux, hãy trả publisher cho framework hoặc kết hợp nó bằng `flatMap`, `then` và các toán tử phù hợp.

## 2. Phân biệt session không tồn tại với lỗi repository

Một trong những quy tắc quan trọng nhất là phân biệt hai tín hiệu:

- `Mono.empty()`: không có session phù hợp để phát ra. Đây thường là trường hợp session ID không tồn tại hoặc phiên đã hết hạn theo repository.
- `Mono.error(exception)`: thao tác không thể hoàn thành vì lỗi, ví dụ Redis timeout, lỗi xác thực, lỗi giải tuần tự hóa hoặc lỗi implementation.

Không chuyển mọi lỗi thành `Mono.empty()`. Nếu Redis đang ngừng hoạt động mà ứng dụng coi kết quả như session không tồn tại, request có thể bị chuyển thành luồng anonymous hoặc tạo session mới. Điều đó che giấu sự cố hạ tầng và có thể làm sai hành vi xác thực.

Ví dụ phân biệt hai trường hợp:

```java
public Mono<MapSession> loadSession(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new SessionNotFoundException("Session không tồn tại")));
}
```

`switchIfEmpty` chỉ chạy khi repository hoàn tất mà không phát session. Nếu Redis phát lỗi kết nối, lỗi vẫn truyền xuống downstream và không bị đổi thành `SessionNotFoundException`.

Trong ứng dụng thực tế, không phải endpoint nào cũng cần biến empty thành lỗi. Endpoint cho phép khách có thể tiếp tục mà không có session; endpoint yêu cầu đăng nhập cần trả về luồng xác thực lại. Hãy chọn hành vi theo chính sách endpoint, không áp dụng một fallback chung cho mọi request.

## 3. Các nhóm lỗi thường gặp

| Nhóm lỗi | Ví dụ | Ý nghĩa và phản ứng |
|---|---|---|
| Không tìm thấy session | `Mono.empty()` từ `findById` | Xử lý như phiên không tồn tại hoặc hết hạn |
| Kết nối datastore | Timeout, connection refused, DNS hoặc TLS handshake | Redis/JDBC không sẵn sàng; không coi là logout bình thường |
| Xác thực/phân quyền datastore | `NOAUTH`, `WRONGPASS`, `NOPERM` | Credentials hoặc ACL sai; cần sửa cấu hình và cảnh báo vận hành |
| Serialization | JSON mapping lỗi, class không tồn tại, payload không hợp lệ | Dữ liệu session không tương thích hoặc hỏng; cần phân loại riêng |
| Timeout ở Reactor | `TimeoutException` do toán tử `timeout` | Caller ngừng chờ; trạng thái side effect có thể chưa xác định |
| Lỗi ứng dụng | Validation, cast sai, null hoặc logic nghiệp vụ | Không phải lỗi Redis; xử lý theo quy tắc ứng dụng |
| Cancellation | Client ngắt kết nối hoặc downstream hủy subscription | Publisher nhận tín hiệu hủy; thao tác I/O có thể đã bắt đầu hoặc đã hoàn tất |

Không nên gom tất cả các nhóm trên vào một exception handler trả `401`. `401` biểu thị request chưa được xác thực hoặc credentials không hợp lệ ở lớp ứng dụng. Redis unavailable thường cần được xử lý như lỗi dịch vụ tạm thời, ví dụ `503`, hoặc theo chính sách resilience của hệ thống.

## 4. Xử lý lỗi bằng các toán tử Reactor

Reactor cung cấp một số toán tử hữu ích:

- `doOnError`: quan sát lỗi để ghi log/metric; không biến lỗi thành thành công.
- `onErrorMap`: chuyển lỗi kỹ thuật thành exception có ngữ nghĩa ứng dụng.
- `onErrorResume`: chọn publisher thay thế cho một loại lỗi đã xác định.
- `onErrorReturn`: trả giá trị fallback cho lỗi phù hợp; chỉ dùng khi giá trị mặc định có ý nghĩa an toàn.
- `onErrorComplete`: biến lỗi thành hoàn tất rỗng; dễ che giấu lỗi nếu dùng rộng.
- `switchIfEmpty`: xử lý trường hợp publisher hoàn tất mà không phát phần tử; không xử lý `onError`.

Ví dụ ánh xạ lỗi kết nối datastore:

```java
public Mono<MapSession> findSession(String id) {
    return repository.findById(id)
            .doOnError(error -> metrics.recordSessionReadFailure())
            .onErrorMap(
                    RedisConnectionFailureException.class,
                    SessionStoreUnavailableException::new
            );
}
```

Constructor của `SessionStoreUnavailableException` cần nhận exception gốc hoặc được định nghĩa phù hợp. Khi log, không ghi cookie, session ID đầy đủ, thuộc tính session hay password Redis. Có thể ghi loại lỗi, instance, operation, correlation ID và thời gian xử lý.

Ví dụ fallback có giới hạn:

```java
return repository.findById(id)
        .onErrorResume(SessionStoreUnavailableException.class,
                error -> Mono.error(
                        new ResponseStatusException(
                                HttpStatus.SERVICE_UNAVAILABLE,
                                "Session store tạm thời không khả dụng",
                                error)));
```

Đoạn code vẫn phát lỗi để WebFlux xử lý thành response phù hợp. Nếu endpoint có cơ chế dự phòng thật sự, chỉ fallback cho loại lỗi và dữ liệu đã được đánh giá an toàn. Ví dụ, một endpoint đọc tùy chọn giao diện có thể dùng giá trị mặc định khi session không tồn tại; điều đó không có nghĩa được dùng giá trị mặc định khi session store đang unavailable.

## 5. Timeout và retry

Có thể đặt timeout cho một thao tác repository:

```java
public Mono<MapSession> findSession(String id) {
    return repository.findById(id)
            .timeout(Duration.ofSeconds(2));
}
```

`timeout` giới hạn thời gian downstream chờ publisher. Khi hết thời gian, Reactor phát lỗi timeout và hủy subscription upstream theo cơ chế reactive. Tuy nhiên, hủy subscription không bảo đảm Redis đã hủy lệnh hoặc chưa thực hiện side effect. Cần cấu hình timeout ở cả client Redis và driver theo khả năng của chúng; timeout của Reactor không thay thế timeout của network/client.

Retry có thể hữu ích với lỗi tạm thời, nhưng phải phân loại:

```java
return repository.findById(id)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(this::isTransientReadFailure));
```

Ví dụ chỉ minh họa retry giới hạn cho thao tác đọc. `isTransientReadFailure` cần nhận diện các lỗi có thể phục hồi như một số lỗi kết nối tạm thời; không retry lỗi xác thực, ACL, serialization hoặc lỗi lập trình.

Đối với thao tác ghi, retry mù quáng nguy hiểm hơn. Nếu timeout xảy ra sau khi Redis đã nhận và thực hiện lệnh nhưng trước khi client nhận phản hồi, ứng dụng không biết thao tác đã commit hay chưa. Retry có thể lặp lại side effect. Các thao tác ghi session đơn giản thường có thể idempotent ở mức ghi cùng snapshot, nhưng điều đó không bảo đảm cả chuỗi nghiệp vụ là idempotent. Với side effect quan trọng, dùng idempotency key, versioning hoặc đọc lại trạng thái trước khi quyết định retry.

## 6. Cancellation là tín hiệu gì?

Trong Reactive Streams, subscriber có thể hủy subscription bằng `cancel()`. Tình huống thường gặp:

- Trình duyệt đóng tab hoặc ngắt kết nối.
- Reverse proxy đóng request vì timeout.
- Một publisher downstream không còn cần kết quả.
- Toán tử `timeout` hủy upstream sau khi quá thời gian.
- Một luồng lớn bị hủy khi người dùng rời trang.

Khi cancellation được truyền upstream, publisher và resource có thể dừng công việc nếu implementation hỗ trợ. Tuy nhiên, cancellation là yêu cầu ngừng tiếp tục xử lý, không phải lệnh rollback transaction. Nếu Redis đã nhận lệnh ghi, lệnh có thể vẫn hoàn tất dù caller không còn chờ kết quả.

Ví dụ về ba thời điểm khác nhau:

1. **Hủy trước khi thao tác bắt đầu:** publisher chưa được subscribe hoặc upstream có thể chưa dispatch lệnh; không có thay đổi nào được ghi.
2. **Hủy khi I/O đang chạy:** client có thể cố gắng hủy request; kết quả ở server có thể chưa xác định.
3. **Hủy sau khi datastore đã ghi:** dữ liệu đã được lưu dù caller không nhận được `onComplete`.

Vì vậy, không suy luận “request bị hủy thì session chắc chắn chưa lưu” hoặc “request bị hủy thì dữ liệu chắc chắn đã lưu”. Nếu cần xác định kết quả của một thao tác quan trọng, phải kiểm tra trạng thái ở nguồn dữ liệu chính hoặc dùng idempotency/version.

## 7. Quan sát cancellation bằng doOnCancel và doFinally

Có thể ghi nhận cancellation để đo lường:

```java
return repository.findById(sessionId)
        .doOnCancel(() -> metrics.recordSessionReadCancelled())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                metrics.recordSessionPipelineCancelled();
            }
        });
```

`doOnCancel` chạy khi subscription bị hủy. `doFinally` chạy khi chuỗi kết thúc bằng complete, error hoặc cancel; kiểm tra `SignalType` để phân biệt. Các callback này phù hợp cho metrics, tracing và cleanup đồng bộ nhỏ.

Không dùng `doOnCancel` hoặc `doFinally` để khởi chạy một thao tác lưu session bắt buộc:

```java
// Không dùng cho một lần lưu bắt buộc:
source.doFinally(signal -> repository.save(session).subscribe());
```

Đoạn code trên tạo một subscription tách rời, không gắn kết quả lưu với response hoặc lỗi của request. Framework không thể chờ publisher đó; lỗi có thể bị mất và tiến trình có thể kết thúc trước khi ghi xong. Hãy nối thao tác bắt buộc vào chuỗi chính bằng `flatMap` hoặc `then`.

Nếu cần quản lý tài nguyên bất đồng bộ có cleanup, Reactor có `usingWhen`. Cơ chế đó phù hợp cho resource có vòng đời rõ ràng, nhưng không biến việc lưu session trong callback cancellation thành một transaction được bảo đảm.

## 8. WebSession được lưu ở thời điểm nào?

Trong WebFlux, controller thường nhận `WebSession` và thay đổi attributes. `WebSessionManager` quản lý việc lấy session cho request và phối hợp lưu session theo vòng đời response, thường thông qua bước commit trước khi response được ghi ra. Ứng dụng không cần tự gọi `subscribe()` để lưu session.

Ví dụ controller:

```java
@RestController
public class DraftController {

    private static final String DRAFT_ID = "app.draft.id";

    private final DraftService draftService;

    public DraftController(DraftService draftService) {
        this.draftService = draftService;
    }

    @PostMapping("/draft")
    public Mono<ResponseEntity<Void>> saveDraft(
            @RequestBody DraftRequest request,
            WebSession session) {

        return draftService.validateAndSave(request)
                .map(savedDraft -> {
                    session.getAttributes().put(DRAFT_ID, savedDraft.id());
                    return ResponseEntity.noContent().build();
                });
    }
}
```

Ví dụ chỉ lưu mã tham chiếu của bản nháp vào session sau khi service nghiệp vụ hoàn tất. `WebSessionManager` và session store phối hợp persist thay đổi trong vòng đời response. Nếu `validateAndSave` phát lỗi, phần `map` không chạy nên session chưa nhận mã tham chiếu mới.

Lưu session ở giai đoạn commit có một hệ quả: lỗi persistence có thể xuất hiện muộn hơn thời điểm controller thay đổi thuộc tính. Tùy cách response được commit và server xử lý lỗi, lỗi có thể làm response commit thất bại. Khi response đã commit một phần hoặc client đã ngắt kết nối, ứng dụng có thể không còn khả năng gửi một response lỗi rõ ràng cho client.

Nếu có yêu cầu phải xác nhận việc lưu session trước khi tiếp tục một bước cụ thể, `WebSession` cung cấp `save()` trả về `Mono<Void>` để yêu cầu lưu tường minh khi cần. Hãy nối publisher này vào chuỗi:

```java
return session.save()
        .thenReturn(ResponseEntity.noContent().build());
```

Chỉ dùng cách này khi luồng cần ranh giới lưu tường minh và đã hiểu cách `WebSessionManager` tiếp tục commit ở cuối response. Không gọi `block()` hoặc `subscribe()` để ép lưu đồng bộ.

## 9. Thao tác trực tiếp với ReactiveSessionRepository

Trong một số service nền hoặc công cụ quản trị, có thể thao tác repository theo session ID mà không có `WebSession` gắn với request. Khi đó, caller phải nối `save` vào chuỗi reactive:

```java
public Mono<String> updateCartSession(
        String sessionId,
        String cartId) {
    return repository.findById(sessionId)
            .switchIfEmpty(Mono.error(
                    new SessionNotFoundException(sessionId)))
            .flatMap(session -> {
                session.setAttribute("app.cart.id", cartId);
                return repository.save(session)
                        .thenReturn(session.getId());
            });
}
```

Trong ví dụ, `flatMap` nối thao tác lưu; `thenReturn` chỉ phát session ID khi `save` hoàn tất. Nếu lưu thất bại, publisher kết thúc bằng lỗi. Không nên viết:

```java
repository.save(session).subscribe();
return Mono.just(session.getId());
```

Đoạn code thứ hai trả ID trước khi biết save có thành công hay không, tách lỗi khỏi luồng caller và tạo race giữa response với thao tác persistence.

Khi ứng dụng đã dùng `WebSession` tiêu chuẩn, ưu tiên để framework quản lý session trong request. Truy cập cùng session bằng cả `WebSession` và repository trực tiếp trong một request có thể tạo hai bản trạng thái khác nhau; nếu bắt buộc phải làm, cần định nghĩa rõ thứ tự đọc/ghi và tránh ghi đè snapshot cũ.

## 10. Lỗi xảy ra trong giai đoạn response commit

Một controller có thể hoàn tất publisher trả body, nhưng session store vẫn cần được lưu trong quá trình response commit. Vì vậy, kiểm thử chỉ gọi service hoặc chỉ xác minh controller publisher phát giá trị không đủ để chứng minh session đã persist.

Các tình huống cần xem xét:

- Controller thay đổi session rồi hoàn tất; repository save thành công: response commit bình thường.
- Controller thay đổi session; repository save phát lỗi: response commit có thể thất bại hoặc được xử lý bởi WebFlux error handling tùy thời điểm.
- Response đã được commit rồi mới có lỗi ở một tác vụ tách rời: không thể thay status/body đã gửi; cần log/metric và cơ chế xử lý hậu kỳ.
- Client ngắt kết nối trước commit: session save có thể chưa bắt đầu hoặc bị hủy theo lifecycle; không giả định kết quả.
- Client ngắt kết nối khi save đang chạy: trạng thái datastore có thể không xác định từ phía client.

Không nên bắt lỗi persistence muộn rồi trả về `200 OK` với nội dung mặc định. Nếu request cần lưu session để đảm bảo luồng xác thực, lỗi save phải được coi là lỗi thật và cần được quan sát. Cũng không nên tiết lộ chi tiết Redis, SQL hoặc serialized data trong response.

## 11. WebFlux error handling ở cấp ứng dụng

Có thể xử lý lỗi trong chuỗi reactive hoặc ở tầng WebFlux toàn cục. Ví dụ một `@RestControllerAdvice`:

```java
@RestControllerAdvice
public class SessionErrorHandler {

    @ExceptionHandler(SessionStoreUnavailableException.class)
    public Mono<ResponseEntity<ApiError>> handleStoreUnavailable(
            SessionStoreUnavailableException error) {

        ApiError body = new ApiError(
                "SESSION_STORE_UNAVAILABLE",
                "Dịch vụ phiên tạm thời không khả dụng"
        );

        return Mono.just(ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(body));
    }
}
```

`ApiError` là DTO do ứng dụng định nghĩa. Exception handler chỉ có thể tạo response nếu response chưa commit và WebFlux còn khả năng ghi response. Nếu lỗi xảy ra sau khi response đã được gửi, handler không thể thu hồi bytes đã gửi; cần dựa vào observability và xử lý nghiệp vụ idempotent.

Đối với lỗi session không tồn tại, endpoint có thể trả `401 Unauthorized` hoặc chuyển hướng đăng nhập theo chính sách bảo mật. Đối với lỗi datastore, cân nhắc `503 Service Unavailable`. Đối với lỗi serialization, ghi nhận riêng và có thể thu hồi session hỏng theo quy trình khi datastore sẵn sàng. Không trả lỗi nội bộ, host Redis hoặc thông tin kết nối cho client.

## 12. Cancellation không phải transaction rollback

Một request reactive có thể gồm nhiều thao tác:

1. Đọc session.
2. Gọi service nghiệp vụ.
3. Ghi dữ liệu nghiệp vụ.
4. Thay đổi `WebSession`.
5. Commit response và lưu session.

Nếu client ngắt kết nối ở giữa, cancellation có thể truyền qua các publisher đang chạy. Nhưng các thao tác ở những hệ thống khác nhau không tự rollback cùng nhau. Ví dụ database đơn hàng có thể đã commit, trong khi session save chưa chạy hoặc chưa nhận được xác nhận. Hoặc Redis đã lưu session nhưng response chưa tới trình duyệt.

Vì vậy:

- Không đặt side effect quan trọng trong `doOnCancel` hoặc `doFinally` rồi giả định nó sẽ hoàn tất.
- Dùng transaction cho dữ liệu nghiệp vụ trong một database có transaction.
- Dùng idempotency key cho request có thể được client retry sau khi mất response.
- Nếu cần phối hợp nhiều hệ thống, cân nhắc outbox, saga hoặc quy trình bù trừ thay vì kỳ vọng cancellation rollback.
- Đối với session, lưu mã tham chiếu tới trạng thái nghiệp vụ; không dùng session làm nơi duy nhất ghi nhận giao dịch.

## 13. Cập nhật đồng thời và giới hạn nhất quán của WebSession

Reactive không có nghĩa các request cùng session được thực thi tuần tự. Hai request đồng thời có thể tải hai snapshot riêng của cùng một session ID:

1. A và B cùng đọc `app.cart.count = 1`.
2. A tính và ghi `2`.
3. B cũng tính và ghi `2`.
4. B lưu sau A và ghi đè giá trị `2`.

Nếu nghiệp vụ mong số lượng là `3`, đã xảy ra lost update. Tương tự, một request có thể xóa thuộc tính trong khi request khác lưu snapshot cũ và tạo lại thuộc tính đó.

`ReactiveSessionRepository.save` không mặc định cung cấp optimistic locking hoặc compare-and-set cho toàn bộ session. Redis có thể thực hiện từng lệnh nguyên tử, nhưng chuỗi đọc–sửa–ghi gồm nhiều lệnh vẫn có race nếu repository không cung cấp cơ chế phối hợp cụ thể. `flatMap`, `concatMap` hoặc một scheduler không tự tuần tự hóa request trên nhiều instance.

Các cách xử lý:

- Với dữ liệu giao diện ít quan trọng, chấp nhận last-write-wins nếu đó là chính sách rõ ràng.
- Với giỏ hàng, hạn mức, bộ đếm hoặc trạng thái thanh toán, dùng database nghiệp vụ với transaction, version column hoặc thao tác nguyên tử.
- Nếu repository hỗ trợ versioning/compare-and-set, dùng đúng contract và kiểm thử conflict/retry.
- Tránh lưu object mutable lớn; tạo DTO bất biến hoặc thay thế thuộc tính bằng giá trị mới.
- Không retry một lần ghi có side effect khi chưa xác định thao tác trước đã commit hay chưa.

Nếu cần khóa phân tán theo session, phải thiết kế lease, thời hạn, xử lý node chết và deadlock. Khóa phân tán không nên được thêm chỉ để che một mô hình dữ liệu nghiệp vụ chưa phù hợp.

## 14. Session chỉ nên chứa trạng thái nhỏ, tạm thời

Session phù hợp với thông tin giúp duy trì trải nghiệm qua các request, chẳng hạn:

- Mã tham chiếu bản nháp hoặc giỏ hàng.
- Lựa chọn giao diện hoặc locale.
- Trạng thái một quy trình nhiều bước chưa hoàn tất.
- Một số dữ liệu ngắn hạn cần cho request tiếp theo.

Session không phù hợp làm nguồn dữ liệu duy nhất cho:

- Đơn hàng, giao dịch thanh toán hoặc lịch sử tài chính.
- Bộ đếm cần chính xác khi có request đồng thời.
- Hạn mức hoặc số dư cần bảo đảm không vượt ngưỡng.
- Quyền truy cập cần cập nhật tức thời sau khi tài khoản bị khóa.
- Dữ liệu lớn hoặc object graph phụ thuộc nhiều class/library.

Lưu trạng thái quan trọng trong kho nghiệp vụ; session chỉ giữ ID tham chiếu. Khi session hết hạn hoặc bị mất do datastore sự cố, dữ liệu nghiệp vụ vẫn còn và có thể được kiểm tra bằng quyền truy cập phù hợp.

## 15. Kiểm thử lỗi và cancellation

Kiểm thử cần phân biệt giá trị, lỗi, empty và cancellation. Với repository/service publisher, Reactor `StepVerifier` có thể kiểm tra các tín hiệu:

```java
StepVerifier.create(repository.findById("missing"))
        .verifyComplete();

StepVerifier.create(repository.findById("bad-store"))
        .expectError(SessionStoreUnavailableException.class)
        .verify();

StepVerifier.create(service.updateCartSession("S1", "CART-9"))
        .expectNext("S1")
        .verifyComplete();
```

Các ví dụ giả định repository/service test double được cấu hình trả về đúng publisher tương ứng. `verifyComplete()` với publisher rỗng xác minh không có phần tử và complete bình thường; nó khác `expectError`.

Có thể kiểm tra cancellation:

```java
StepVerifier.create(longRunningOperation())
        .thenCancel()
        .verify();
```

Test nên dùng một publisher có thể quan sát cancellation để xác minh upstream nhận được tín hiệu. Điều này không chứng minh một Redis command thật đã rollback. Để kiểm tra datastore, cần integration test với Redis thật, theo dõi trạng thái sau khi hủy và chấp nhận rằng thao tác đã gửi có thể hoàn tất.

### 15.1. Ma trận test cần có

| Trường hợp | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Session không tồn tại | Repository trả `Mono.empty()` | Endpoint xử lý như phiên không tồn tại |
| Redis unavailable | Repository phát lỗi kết nối | Không biến thành empty hoặc anonymous một cách âm thầm |
| Authentication/ACL failure | Dùng credential sai trong test | Lỗi cấu hình được phân loại, không retry vô hạn |
| Timeout khi đọc | Đặt timeout ngắn hoặc làm chậm datastore | Timeout được trả/ghi nhận theo chính sách |
| Timeout khi ghi | Làm chậm phản hồi save | Xác minh trạng thái thực tế; không giả định ghi chưa xảy ra |
| Cancellation trước save | Hủy publisher trước khi commit | Xác minh save không được khởi chạy nếu chưa subscribe tới bước đó |
| Cancellation khi save | Hủy trong lúc I/O đang chạy | Kiểm tra trạng thái Redis và ghi nhận tính không xác định từ phía client |
| Save lỗi ở response commit | Cho repository phát lỗi khi lưu WebSession | Response commit/error handling phản ánh lỗi nếu còn khả năng |
| Không subscribe | Tạo publisher save nhưng không nối vào luồng | Xác minh không có giả định rằng save đã chạy |
| Retry read | Mô phỏng lỗi transient rồi thành công | Retry giới hạn và có backoff |
| Retry write | Mô phỏng timeout sau khi lệnh có thể đã commit | Không nhân đôi side effect; dùng idempotency hoặc xác minh trạng thái |
| Hai request đồng thời | Cùng session ID, cập nhật cùng thuộc tính | Xung đột được xử lý theo chính sách đã chọn |
| Nhiều instance | Request A và B tới hai node | Cùng repository, nhưng không giả định tự tuần tự hóa |

Với WebFlux endpoint, dùng `WebTestClient` để kiểm tra response và cookie. Để kiểm tra client disconnect thực tế, cần test ở mức server/container hoặc công cụ HTTP có thể đóng kết nối; mock controller test không mô phỏng đầy đủ hành vi mạng.

## 16. Quan sát vận hành

Để phân biệt lỗi session với lỗi datastore, theo dõi riêng:

- Số lần `findById` trả empty và số lần phát lỗi.
- Lỗi Redis connection, timeout, ACL, TLS và serialization.
- Thời gian `createSession`, `save`, `findById`, `deleteById`.
- Số publisher bị cancel và thời điểm cancellation trong request lifecycle.
- Tỷ lệ timeout và retry; số lần retry cuối cùng thất bại.
- Lỗi xảy ra trước response commit hay trong giai đoạn commit nếu framework cho phép quan sát.
- Số session tạo mới bất thường sau khi datastore gặp lỗi.
- Xung đột cập nhật hoặc lỗi version ở kho nghiệp vụ.

Không dùng session ID, cookie hoặc principal nhạy cảm làm metric label. Cardinality cao và có thể làm lộ thông tin xác thực. Dùng operation name, loại lỗi, phiên bản ứng dụng, datastore cluster hoặc correlation ID không nhạy cảm.

Khi Redis mất kết nối, tránh retry dồn dập từ mọi instance. Dùng backoff có giới hạn, circuit breaker nếu phù hợp, connection pool được sizing và cảnh báo theo error rate. Phân biệt lỗi datastore kéo dài với một timeout request đơn lẻ.

## 17. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Redis outage bị hiểu thành session không tồn tại | `onErrorResume` quá rộng trả `Mono.empty()` | Chỉ xử lý empty riêng; giữ lỗi hạ tầng thành error |
| Session save không chạy | Publisher được tạo nhưng không subscribe/nối vào chuỗi | Trả publisher hoặc compose bằng `flatMap`/`then` |
| Response thành công trước khi save xong | Gọi `subscribe()` tách rời | Nối save vào luồng response hoặc để WebSessionManager commit |
| Timeout rồi retry làm lặp thao tác | Không biết lệnh ghi trước đã commit chưa | Dùng idempotency, version hoặc kiểm tra trạng thái |
| `doFinally` không lưu được session | Callback không chờ publisher bất đồng bộ | Không đặt persistence bắt buộc trong finally/cancel hook |
| Client disconnect nhưng dữ liệu vẫn được lưu | Redis đã nhận lệnh trước cancellation | Đây là trạng thái có thể xảy ra; thiết kế thao tác idempotent |
| Client disconnect làm mất thay đổi session | Request bị hủy trước giai đoạn commit/save | Không coi session là nơi lưu duy nhất cho dữ liệu quan trọng |
| Hai request cùng session ghi đè nhau | Reactive không tự khóa session | Dùng versioning/transaction ở kho nghiệp vụ |
| Lỗi save xuất hiện sau controller | Save diễn ra trong response commit | Kiểm thử integration và quan sát lỗi commit |
| Handler không đổi được response thành lỗi | Response đã commit hoặc client đã ngắt | Ghi log/metric; không thể thu hồi bytes đã gửi |

## 18. Quy trình thiết kế luồng session reactive

Khi viết service hoặc controller dùng WebSession, thực hiện theo thứ tự:

1. Xác định session không tồn tại là empty hay phải chuyển thành lỗi nghiệp vụ ở endpoint.
2. Phân loại lỗi repository: kết nối, xác thực, timeout, serialization và lỗi ứng dụng.
3. Kết hợp các thao tác bất đồng bộ bằng `flatMap`, `then` và trả publisher cho WebFlux; không tự `subscribe()` hoặc `block()`.
4. Chỉ cập nhật session sau khi bước nghiệp vụ cần thiết đã thành công.
5. Hiểu thời điểm `WebSessionManager` commit session và kiểm thử lỗi save ở giai đoạn đó.
6. Đặt timeout cho client/repository và chỉ retry lỗi transient, đặc biệt thận trọng với thao tác ghi.
7. Xem cancellation là tín hiệu best-effort; không coi nó là rollback.
8. Dùng `doOnCancel`/`doFinally` cho observability, không dùng để lưu dữ liệu bắt buộc.
9. Đưa dữ liệu quan trọng vào kho nghiệp vụ có transaction, idempotency hoặc versioning.
10. Kiểm thử empty, error, timeout, cancellation, concurrent requests và nhiều instance bằng datastore thực tế.

Reactive session giúp WebFlux phối hợp I/O bất đồng bộ và giữ trạng thái người dùng qua nhiều request. Tuy nhiên, lỗi, timeout và cancellation vẫn có thể xảy ra ở những thời điểm khác nhau của thao tác lưu. Khi phân biệt đúng empty với error, nối persistence vào chuỗi được quản lý, không coi cancellation là rollback và đặt dữ liệu nghiệp vụ trong kho có tính nhất quán phù hợp, ứng dụng có thể xử lý session ổn định hơn khi client ngắt kết nối, Redis gặp sự cố hoặc nhiều instance cùng phục vụ một người dùng.
