# Bắt mọi lỗi hoặc tiếp tục sau lỗi khiến mất dữ liệu âm thầm

Trong pipeline reactive, lỗi là một tín hiệu kết thúc. Khi một `Flux` phát `onError`, subscription đó kết thúc và không thể tiếp tục phát các phần tử tiếp theo. Vì muốn hệ thống “chịu lỗi tốt hơn”, lập trình viên đôi khi dùng `onErrorResume` trả về `Mono.empty()`, `onErrorComplete()` hoặc `onErrorContinue()` ở phạm vi quá rộng. Những cách này có thể làm request trông như thành công trong khi một phần dữ liệu đã bị bỏ qua mà không ai biết.

Bài học thuộc chương **Lỗi thường gặp** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là phân biệt lỗi kết thúc luồng với lỗi của một bản ghi, tránh bắt mọi exception, và thiết kế chính sách tiếp tục có thể kiểm toán thay vì âm thầm loại bỏ dữ liệu.

Sau bài học, bạn có thể:

- Giải thích vì sao `onError` kết thúc subscription và không thể tự tiếp tục nguồn cũ.
- Phân biệt `doOnError`, `onErrorMap`, `onErrorResume`, `onErrorReturn` và `onErrorComplete`.
- Nhận diện cách dùng `onErrorContinue` có thể làm mất phần tử hoặc che giấu lỗi.
- Đặt phục hồi bên trong từng Publisher con khi muốn cô lập lỗi theo bản ghi.
- Giữ lại kết quả thành công, lỗi từng phần tử và thông tin dead-letter trong mô hình dữ liệu rõ ràng.
- Chỉ retry lỗi tạm thời và hiểu nguy cơ phát lại side effect.
- Kiểm thử lỗi terminal, fallback, dữ liệu bị bỏ qua và số lượng bản ghi bằng `StepVerifier`.

## 1. `onError` là tín hiệu kết thúc, không phải một phần tử dữ liệu

Reactive Streams định nghĩa ba loại tín hiệu chính từ Publisher xuống Subscriber:

- `onNext(value)`: phát một phần tử.
- `onComplete()`: kết thúc bình thường.
- `onError(error)`: kết thúc do lỗi.

Sau `onError` hoặc `onComplete`, Publisher không được phát thêm `onNext` hay một terminal signal thứ hai cho cùng subscription. Đây là hợp đồng của stream. Vì vậy, “bắt lỗi rồi tiếp tục” không thể có nghĩa là yêu cầu một Publisher đã phát `onError` quay lại phát phần tử tiếp theo.

```text
Publisher
   |
   +---- onNext(A) ----> downstream
   |
   +---- onNext(B) ----> downstream
   |
   +---- onError(E) ---> downstream
                           |
                           +-- subscription kết thúc
                           +-- không còn onNext(C)
```

Các toán tử phục hồi tạo ra một nhánh Publisher mới hoặc thay đổi cách biểu diễn terminal signal. Chúng không làm cho nguồn ban đầu tiếp tục sau vị trí lỗi.

### Ví dụ: fallback thay phần còn lại của nguồn

```java
Flux<Integer> values = Flux.concat(
        Flux.just(1, 2),
        Flux.error(new IllegalStateException("source failed")),
        Flux.just(3, 4)
    )
    .onErrorResume(error -> Flux.just(99));
```

Downstream nhận `1`, `2`, `99` rồi hoàn tất. Khi nguồn lỗi, phần còn lại của Publisher ban đầu bị hủy; `3` và `4` không được phát. `onErrorResume` thay nhánh lỗi bằng Publisher `Flux.just(99)`.

Điều này khác với việc bỏ qua một bản ghi lỗi trong một tập dữ liệu. Nếu yêu cầu nghiệp vụ là xử lý độc lập từng bản ghi và vẫn xử lý các bản ghi còn lại, cần đặt ranh giới xử lý lỗi quanh từng bản ghi, không đặt một fallback chung sau toàn bộ `Flux`.

## 2. Các toán tử xử lý lỗi không có cùng ý nghĩa

| Toán tử | Hành vi | Nguy cơ nếu dùng sai |
|---|---|---|
| `doOnError` | Quan sát lỗi để log, metric hoặc audit; lỗi vẫn truyền xuống. | Tưởng rằng log lỗi nghĩa là đã xử lý lỗi. |
| `onErrorMap` | Đổi exception thành exception khác rồi tiếp tục phát `onError`. | Làm mất loại lỗi hoặc nguyên nhân gốc nếu mapping sai. |
| `onErrorResume` | Thay nhánh lỗi bằng một Publisher khác. | Fallback empty hoặc mặc định có thể che giấu dữ liệu thất bại. |
| `onErrorReturn` | Phát một giá trị thay thế rồi hoàn tất. | Giá trị giả có thể bị hiểu là dữ liệu thật. |
| `onErrorComplete` | Biến lỗi thành completion bình thường. | Downstream không còn biết luồng đã thất bại. |
| `onErrorContinue` | Với operator upstream có hỗ trợ, bỏ phần tử gây lỗi và tiếp tục xử lý phần tử khác. | Phần tử bị bỏ có thể biến mất mà không có kết quả lỗi rõ ràng. |

Chọn toán tử dựa trên hợp đồng nghiệp vụ:

- Nếu thao tác thất bại thì request phải thất bại, giữ `onError` và ánh xạ ở ranh giới phù hợp.
- Nếu cần đổi loại exception nhưng vẫn báo lỗi, dùng `onErrorMap`.
- Nếu có nguồn thay thế đáng tin cậy, dùng `onErrorResume` và ghi nhận việc fallback.
- Nếu có giá trị mặc định hợp lệ, dùng `onErrorReturn` nhưng biểu diễn rõ nguồn gốc mặc định.
- Chỉ biến lỗi thành completion khi hợp đồng cho phép bỏ qua lỗi đó và việc bỏ qua được quan sát.
- Chỉ dùng `onErrorContinue` khi đã xác minh operator upstream hỗ trợ semantics này và có chính sách ghi nhận phần tử bị loại.

## 3. `doOnError` chỉ quan sát, không phục hồi

Một đoạn code thường gây hiểu nhầm:

```java
Flux<Order> orders = orderSource
    .doOnError(error -> log.error("Không đọc được đơn hàng", error));
```

`doOnError` không biến lỗi thành dữ liệu hoặc completion. Subscriber vẫn nhận `onError`; controller WebFlux hoặc caller vẫn phải xử lý lỗi. Đây là hành vi thường mong muốn khi lỗi cần được báo lên tầng gọi.

Có thể kết hợp quan sát với phục hồi:

```java
Mono<Profile> profile = profileClient.find(userId)
    .doOnError(error -> metrics.increment("profile.primary.failed"))
    .onErrorResume(TemporaryProfileException.class,
        error -> profileCache.find(userId));
```

Đặt `doOnError` trước `onErrorResume` giúp ghi nhận lỗi nguồn chính trước khi nó được thay thế. Nếu chỉ đặt `doOnError` sau `onErrorResume`, hook đó sẽ quan sát lỗi còn thoát ra từ fallback hoặc các lỗi không được phục hồi; nó không nhìn thấy lỗi chính đã được thay thế thành công.

Không log cùng một exception ở mọi tầng. Hãy chọn một ranh giới chịu trách nhiệm ghi log, đồng thời phát metric riêng cho số lần fallback và tỷ lệ fallback thành công. Không ghi payload nhạy cảm hoặc thông tin xác thực vào log.

## 4. `onErrorResume(error -> Mono.empty())` có thể làm mất dữ liệu

Đoạn code sau nhìn có vẻ giúp pipeline không bị dừng:

```java
Flux<Receipt> receipts = inputRecords
    .flatMap(this::createReceipt)
    .onErrorResume(error -> Mono.empty());
```

Nhưng `onErrorResume` nằm sau `flatMap`, nên nó xử lý lỗi của toàn bộ pipeline. Khi một inner Publisher lỗi, lỗi đi ra ngoài `flatMap`; fallback empty thay phần còn lại của chuỗi bằng một Publisher hoàn tất rỗng. Các record chưa được xử lý có thể không được tiếp tục, trong khi downstream chỉ thấy completion bình thường.

Nếu mục tiêu là cô lập lỗi theo từng record, hãy đặt phục hồi bên trong mapper của `flatMap`:

```java
Flux<Receipt> receipts = inputRecords
    .flatMap(record -> createReceipt(record)
        .onErrorResume(RecoverableRecordException.class, error -> {
            log.warn("Bỏ qua record id={}", record.id(), error);
            return Mono.empty();
        }), 8);
```

Ở đây, lỗi thuộc loại `RecoverableRecordException` chỉ kết thúc inner Publisher của record hiện tại. `flatMap` bên ngoài vẫn có thể tiếp tục nhận và xử lý record khác. Tuy nhiên, record lỗi không tạo `Receipt`; nếu chỉ log rồi bỏ qua, dữ liệu vẫn không được xử lý thành công. Với import, thanh toán, audit hoặc xử lý dữ liệu cần kiểm toán, nên phát ra một kết quả lỗi có cấu trúc hoặc lưu record vào dead-letter store.

### Vị trí phục hồi quyết định phạm vi lỗi

```text
Phục hồi ngoài flatMap:

records -> flatMap(process) -> onErrorResume(empty)
                                  |
                                  +-- một lỗi có thể thay toàn bộ phần còn lại

Phục hồi trong từng inner:

records -> flatMap(record -> process(record)
                              -> onErrorResume(per-record policy))
                                  |
                                  +-- lỗi được xử lý trong phạm vi record
```

Đặt operator sau vùng cần bảo vệ. Nếu cần tiếp tục từng phần tử, phạm vi phục hồi phải tương ứng với một phần tử hoặc một đơn vị công việc độc lập.

## 5. Không bắt mọi exception rồi giả vờ thành công

Một anti-pattern khác là bắt tất cả lỗi rồi trả giá trị mặc định:

```java
Mono<Account> account = accountClient.load(accountId)
    .onErrorResume(error -> Mono.just(Account.empty()));
```

Code này có thể biến các tình huống rất khác nhau thành cùng một kết quả:

- Timeout do upstream chậm.
- Lỗi xác thực hoặc phân quyền.
- Dữ liệu không hợp lệ.
- Lỗi lập trình như `NullPointerException`.
- Lỗi cấu hình hoặc lỗi hệ thống không thể phục hồi.

Caller không còn phân biệt được tài khoản thật với giá trị giả. Nếu giá trị mặc định được dùng cho quyết định tiếp theo, ứng dụng có thể ghi dữ liệu sai hoặc cấp quyền sai.

Hãy lọc loại lỗi được phép phục hồi:

```java
Mono<Account> account = accountClient.load(accountId)
    .onErrorResume(TemporaryDependencyException.class, error ->
        accountCache.load(accountId)
    );
```

Các lỗi không khớp loại exception tiếp tục truyền xuống. Nếu fallback cũng lỗi, lỗi của fallback tiếp tục được phát; không được giả định nguồn dự phòng chắc chắn thành công.

### Không bắt `Throwable` để tiếp tục

Không nên dùng `onErrorResume(Throwable.class, ...)` hoặc catch mọi `Throwable` để biến mọi tình huống thành dữ liệu hợp lệ. `Throwable` bao gồm cả các lỗi nghiêm trọng của JVM mà ứng dụng thường không thể phục hồi an toàn. Hãy bắt các exception thuộc phạm vi nghiệp vụ/hạ tầng đã xác định, và để lỗi không mong đợi truyền đến error boundary của ứng dụng.

## 6. `onErrorComplete` có thể che giấu thất bại

`onErrorComplete()` thay `onError` bằng `onComplete`. Downstream thấy stream hoàn tất bình thường dù nguồn đã thất bại:

```java
Flux<AuditEvent> events = auditSource
    .onErrorComplete();
```

Nếu audit là bắt buộc, cách này rất nguy hiểm: ứng dụng có thể tiếp tục request mà không có bản ghi audit. Nếu nghiệp vụ thực sự cho phép bỏ qua một nguồn phụ không quan trọng, cần ghi nhận rõ việc nguồn phụ thất bại:

```java
Flux<Recommendation> recommendations = recommendationClient.load(userId)
    .doOnError(error -> metrics.increment("recommendation.omitted"))
    .onErrorComplete(TemporaryRecommendationException.class);
```

Trong ví dụ, chỉ lỗi tạm thời được chọn mới bị chuyển thành completion; lỗi khác vẫn truyền xuống. Metric cho biết dữ liệu recommendation đã bị bỏ qua. Hãy cân nhắc trả trạng thái rõ ràng trong response nếu người dùng hoặc hệ thống phụ thuộc cần biết kết quả không đầy đủ.

`onErrorComplete` không tiếp tục đọc nguồn sau phần tử gây lỗi. Nó chỉ kết thúc luồng bằng completion thay cho error.

## 7. `onErrorContinue` không phải chế độ “bỏ qua mọi lỗi” an toàn

`onErrorContinue` có semantics đặc biệt. Nó yêu cầu các operator upstream có hỗ trợ tiếp tục khi một phần tử gây lỗi thì loại bỏ phần tử đó và tiếp tục xử lý các phần tử khác. Nó không phải handler tổng quát cho mọi exception từ mọi nguồn.

Ví dụ đơn giản:

```java
Flux<Integer> parsed = Flux.just("10", "bad", "20")
    .map(Integer::parseInt)
    .onErrorContinue((error, value) ->
        log.warn("Không parse được value={}", value, error)
    );
```

Với operator `map` hỗ trợ semantics này, giá trị `bad` gây `NumberFormatException` bị bỏ qua và luồng tiếp tục với `20`. Kết quả phát là `10`, `20`.

Nhưng có một số giới hạn quan trọng:

- Không phải mọi operator hoặc nguồn đều hỗ trợ `onErrorContinue`.
- Nó tác động đến operator upstream hỗ trợ cơ chế này; vị trí đặt trong chuỗi có thể làm phạm vi ảnh hưởng khó nhìn thấy.
- Nó bỏ phần tử gây lỗi khỏi luồng, không tự tạo một kết quả lỗi có cấu trúc.
- Lỗi phát trực tiếp từ nguồn hoặc lỗi không nằm trong callback xử lý một phần tử không nhất thiết được tiếp tục.
- Callback ghi nhận lỗi cũng có thể phát sinh lỗi mới.

Vì phạm vi và khả năng hỗ trợ phụ thuộc operator, không nên thêm `onErrorContinue` ở cuối một pipeline lớn với kỳ vọng mọi lỗi sẽ được bỏ qua an toàn. Ưu tiên cô lập lỗi ngay tại đơn vị xử lý bằng `flatMap` và một chính sách lỗi tường minh.

## 8. Biểu diễn kết quả thành công và thất bại theo từng record

Khi cần tiếp tục xử lý các record độc lập nhưng không được mất thông tin thất bại, hãy biến mỗi record thành một outcome rõ ràng.

```java
enum ImportStatus {
    IMPORTED,
    REJECTED
}

record ImportOutcome(
    String recordId,
    ImportStatus status,
    String errorCode
) {}

Flux<ImportOutcome> importRecords(Flux<InputRecord> records) {
    return records.flatMap(record ->
        validateAndSave(record)
            .thenReturn(new ImportOutcome(
                record.id(), ImportStatus.IMPORTED, null
            ))
            .onErrorResume(RecoverableRecordException.class, error ->
                deadLetterStore.store(record, error)
                    .thenReturn(new ImportOutcome(
                        record.id(), ImportStatus.REJECTED,
                        classify(error)
                    ))
            ),
        8
    );
}
```

Mỗi record tạo một `ImportOutcome`:

- Thành công: `IMPORTED`.
- Lỗi record được phép từ chối: ghi vào dead-letter store rồi phát `REJECTED` với error code.
- Lỗi không thuộc nhóm có thể phục hồi: tiếp tục phát lỗi và có thể kết thúc pipeline.
- Nếu ghi dead-letter thất bại: lỗi dead-letter tiếp tục truyền xuống, vì hệ thống chưa bảo đảm lưu được record thất bại.

Đây là cách tiếp tục có thể kiểm toán: số lượng đầu vào có thể đối chiếu với số outcome thành công và thất bại. Không đưa nguyên văn exception hoặc dữ liệu nhạy cảm vào `errorCode`; dùng mã phân loại ổn định.

### Bảo toàn thứ tự nếu nghiệp vụ yêu cầu

`flatMap(..., 8)` cho phép tối đa tám inner Publisher hoạt động đồng thời. Outcome có thể phát theo thứ tự hoàn tất thay vì thứ tự đầu vào. Nếu thứ tự phải được giữ, dùng `concatMap` hoặc `flatMapSequential` với concurrency phù hợp:

```java
Flux<ImportOutcome> ordered = records
    .concatMap(this::importOne);
```

Không đổi sang `concatMap` chỉ để tránh lỗi; đây là lựa chọn về thứ tự và concurrency. Hãy xác định rõ hợp đồng của luồng kết quả.

## 9. Phân biệt lỗi record với lỗi toàn hệ thống

Không phải lỗi nào cũng nên biến thành outcome `REJECTED`. Hãy phân loại theo phạm vi:

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi dữ liệu của một record | Sai định dạng, trường bắt buộc thiếu | Đánh dấu record rejected, ghi lý do và tiếp tục record khác nếu nghiệp vụ cho phép. |
| Lỗi nghiệp vụ không thể xử lý | Trạng thái đơn hàng không cho phép chuyển bước | Trả kết quả từ chối nghiệp vụ hoặc lỗi miền rõ ràng. |
| Lỗi dependency tạm thời | Timeout mạng, kết nối reset | Retry có giới hạn hoặc fallback đã xác minh. |
| Lỗi hạ tầng kéo dài | Database unavailable, pool cạn | Dừng/giảm tải, phát lỗi lên caller; không biến thành hàng loạt record rejected. |
| Lỗi lập trình hoặc invariant | `NullPointerException`, vi phạm giả định nội bộ | Để lỗi nổi lên, sửa bug và cảnh báo. |
| Lỗi ghi dead-letter | Không lưu được record lỗi | Không báo record đã được cách ly thành công; phát lỗi để xử lý. |

Nếu database ngừng hoạt động, việc đánh dấu hàng nghìn record là rejected sẽ làm sai dữ liệu nghiệp vụ. Đây là lỗi của hạ tầng xử lý, không phải lỗi của từng record đầu vào.

## 10. Retry không phải cách tiếp tục sau lỗi

Retry subscribe lại Publisher upstream theo chính sách. Với nguồn cold, công việc upstream thường được chạy lại từ đầu. Nếu `Flux` đã phát một số phần tử trước khi lỗi, những phần tử đó không bị thu hồi; lần retry có thể phát lại chúng.

```java
Flux<String> events = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IOException("connection lost"))
    )
    .retry(1);
```

Downstream có thể nhận `A`, `B`, `A`, `B` rồi mới nhận lỗi cuối cùng. Nếu mỗi phần tử đã kích hoạt ghi database hoặc gửi message, retry có thể tạo side effect trùng.

Chỉ retry lỗi tạm thời, giới hạn số lần thử và dùng backoff/jitter khi phù hợp. Với thao tác ghi, cần idempotency key, deduplication hoặc transaction ở ranh giới nghiệp vụ. Không retry lỗi validate, authorization hoặc lỗi do bulkhead/circuit breaker từ chối.

### Đặt retry đúng phạm vi

Nếu một record có thể retry độc lập, đặt retry bên trong Publisher xử lý record:

```java
Flux<ImportOutcome> outcomes = records.flatMap(record ->
    saveRecord(record)
        .retryWhen(Retry.max(2)
            .filter(TransientDatabaseException.class::isInstance))
        .thenReturn(ImportOutcome.imported(record.id()))
        .onErrorResume(RecoverableRecordException.class, error ->
            deadLetterStore.store(record, error)
                .thenReturn(ImportOutcome.rejected(record.id(), classify(error)))
        ),
    8
);
```

Retry được giới hạn trong record hiện tại. Nếu retry cạn và lỗi thuộc nhóm có thể từ chối, record được đưa vào dead-letter store. Lỗi hạ tầng không được phân loại là lỗi record tiếp tục truyền xuống.

## 11. Ghi nhận dữ liệu bị bỏ qua và kết quả không đầy đủ

Nếu nghiệp vụ cho phép tiếp tục mà không có dữ liệu của một nhánh, hãy thể hiện điều đó ở metric hoặc trong kết quả trả về. Chỉ ghi log là chưa đủ nếu downstream cần biết kết quả thiếu.

Ví dụ kết quả API có trạng thái nguồn:

```java
enum DataOrigin {
    PRIMARY,
    CACHE,
    UNAVAILABLE
}

record ProfileResult(Profile profile, DataOrigin origin) {}

Mono<ProfileResult> loadProfile(String id) {
    return primaryClient.find(id)
        .map(profile -> new ProfileResult(profile, DataOrigin.PRIMARY))
        .onErrorResume(TemporaryDependencyException.class, error ->
            cache.find(id)
                .map(profile -> new ProfileResult(profile, DataOrigin.CACHE))
                .switchIfEmpty(Mono.just(
                    new ProfileResult(Profile.unavailable(id), DataOrigin.UNAVAILABLE)
                ))
        );
}
```

Caller có thể phân biệt dữ liệu từ nguồn chính, cache hoặc trạng thái unavailable. Cần bảo đảm `Profile.unavailable` không bị hiểu là hồ sơ thật; kiểu kết quả có thể được thiết kế rõ hơn bằng sealed result hoặc `Either` tùy chuẩn codebase.

Với luồng import, outcome per-record thường tốt hơn việc chỉ trả số lượng thành công. Hãy lưu record ID, mã lỗi, thời điểm, correlation ID và trạng thái dead-letter để có thể điều tra và phát lại có kiểm soát.

## 12. Kiểm thử để phát hiện mất dữ liệu âm thầm

### Xác nhận fallback thay phần còn lại của nguồn

```java
Flux<Integer> source = Flux.concat(
    Flux.just(1, 2),
    Flux.<Integer>error(new IllegalStateException("broken")),
    Flux.just(3, 4)
).onErrorResume(error -> Flux.just(99));

StepVerifier.create(source)
    .expectNext(1, 2, 99)
    .verifyComplete();
```

Test xác nhận `3` và `4` không được phát sau lỗi; fallback thay phần còn lại của nguồn.

### Xác nhận cô lập lỗi theo từng record

```java
Flux<String> raw = Flux.just("10", "bad", "20");

Flux<ParseOutcome> outcomes = raw.flatMap(value ->
    Mono.fromCallable(() -> Integer.parseInt(value))
        .map(number -> ParseOutcome.success(value, number))
        .onErrorResume(NumberFormatException.class, error ->
            Mono.just(ParseOutcome.failure(value, "INVALID_NUMBER"))
        ),
    4
);

StepVerifier.create(outcomes)
    .expectNextMatches(outcome -> outcome.isSuccess() && outcome.value() == 10)
    .expectNextMatches(outcome -> !outcome.isSuccess()
        && outcome.errorCode().equals("INVALID_NUMBER"))
    .expectNextMatches(outcome -> outcome.isSuccess() && outcome.value() == 20)
    .verifyComplete();
```

Ở đây mỗi phần tử được xử lý trong inner Publisher riêng. Record `bad` tạo một outcome lỗi có cấu trúc; hai record hợp lệ vẫn được xử lý. Ví dụ dùng `flatMap` với nguồn đồng bộ nên thứ tự thường được quan sát như đầu vào, nhưng nếu inner Publisher bất đồng bộ có thời gian hoàn tất khác nhau, hãy dùng `concatMap` hoặc `flatMapSequential` khi cần bảo đảm thứ tự.

### Xác nhận `onErrorContinue` thực sự loại phần tử

```java
List<Object> skipped = new ArrayList<>();

Flux<Integer> values = Flux.just("1", "bad", "2")
    .map(Integer::parseInt)
    .onErrorContinue((error, value) -> skipped.add(value));

StepVerifier.create(values)
    .expectNext(1, 2)
    .verifyComplete();

assertThat(skipped).containsExactly("bad");
```

Test làm rõ rằng luồng hoàn tất nhưng phần tử lỗi đã bị bỏ. Nếu nghiệp vụ cần audit, hãy kiểm tra cả danh sách lỗi/đầu ra dead-letter; không chỉ assert các giá trị thành công.

### Xác nhận lỗi không được phục hồi vẫn truyền xuống

```java
StepVerifier.create(
        Mono.<String>error(new SecurityException("denied"))
            .onErrorResume(TemporaryDependencyException.class,
                error -> Mono.just("fallback"))
    )
    .expectError(SecurityException.class)
    .verify();
```

Lỗi bảo mật không khớp loại exception được phục hồi nên tiếp tục đi xuống. Đây là kiểm thử quan trọng để bảo đảm fallback không che giấu lỗi ngoài phạm vi.

### Kiểm tra số lượng đầu vào và outcome

Với một batch import, hãy đối chiếu:

```text
số record nhận vào
  = số outcome thành công
  + số outcome bị từ chối có lưu dead-letter
  + số record còn pending được theo dõi riêng
```

Nếu số lượng không khớp, cần có trạng thái giải thích như pipeline thất bại, batch chưa hoàn tất hoặc record đang chờ retry. Không coi completion bình thường là bằng chứng mọi record đã được xử lý.

## 13. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Đặt `onErrorResume` sau toàn bộ `flatMap` để bỏ lỗi | Một lỗi inner có thể thay phần còn lại của cả luồng. | Đặt phục hồi trong mapper nếu cần cô lập từng record. |
| Trả `Mono.empty()` cho mọi lỗi | Record thất bại biến mất, downstream không biết đã mất dữ liệu. | Phát outcome lỗi hoặc ghi dead-letter trước khi tiếp tục. |
| Dùng `onErrorComplete()` cho nguồn bắt buộc | Pipeline báo hoàn tất bình thường dù dữ liệu thiếu. | Giữ lỗi hoặc trả trạng thái kết quả không đầy đủ có thể quan sát. |
| Nghĩ `doOnError` đã xử lý lỗi | `onError` vẫn truyền xuống downstream. | Dùng `onErrorMap` hoặc `onErrorResume` nếu cần thay đổi hành vi. |
| Bắt mọi `Throwable` | Lỗi nghiêm trọng và lỗi lập trình bị che giấu. | Chỉ phục hồi exception đã phân loại và có chính sách rõ. |
| Dùng `onErrorContinue` ở cuối pipeline lớn | Operator upstream không hỗ trợ có thể vẫn lỗi; phần tử bị bỏ khó truy vết. | Ưu tiên phục hồi theo từng inner Publisher và outcome tường minh. |
| Retry cả pipeline có side effect | Dữ liệu hoặc giao dịch có thể bị thực hiện nhiều lần. | Retry đúng ranh giới, dùng idempotency và deduplication. |
| Không ghi nhận fallback hoặc dữ liệu bị bỏ | Hệ thống có vẻ khỏe trong khi chất lượng dữ liệu giảm. | Metric, log có cấu trúc và trạng thái nguồn/outcome. |
| Coi lỗi database là lỗi của từng record | Hàng loạt record bị đánh dấu rejected dù nguyên nhân là hạ tầng. | Phân biệt lỗi dữ liệu với lỗi dependency/toàn hệ thống. |

## 14. Checklist thiết kế chính sách lỗi không mất dữ liệu

Trước khi đưa pipeline vào production, hãy xác nhận:

- Lỗi nào làm kết thúc toàn request và lỗi nào chỉ ảnh hưởng một record?
- Operator phục hồi có nằm sau đúng vị trí tạo lỗi không?
- Fallback có thể empty hoặc lỗi; các trường hợp đó được xử lý thế nào?
- Có đang dùng `onErrorResume`, `onErrorComplete` hoặc `onErrorReturn` để che giấu thất bại không?
- Nếu bỏ một phần tử, hệ thống có lưu ID và lý do để audit hoặc phát lại không?
- `onErrorContinue` có thực sự cần thiết và mọi operator upstream liên quan có hỗ trợ không?
- Lỗi hạ tầng có bị nhầm thành lỗi dữ liệu của từng record không?
- Retry có lọc lỗi, giới hạn số lần và backoff không?
- Side effect có idempotent hoặc có cơ chế chống trùng không?
- Kết quả cuối có đối chiếu được số đầu vào với success, rejected và pending không?
- Metric có thể hiện số lỗi, fallback, record bị bỏ, dead-letter và retry exhaustion không?
- Kiểm thử đã bao gồm lỗi terminal, lỗi từng record, lỗi fallback và cancellation chưa?

Một pipeline chịu lỗi tốt không phải pipeline biến mọi exception thành completion. Nó phải giữ đúng ranh giới giữa lỗi toàn luồng và lỗi từng phần tử, chỉ phục hồi trường hợp có chính sách rõ ràng, và lưu lại dấu vết của mọi dữ liệu bị từ chối hoặc thay thế. Khi đặt phục hồi trong đúng phạm vi, biểu diễn outcome tường minh và kiểm thử số lượng dữ liệu, ứng dụng `Mono`/`Flux` có thể tiếp tục xử lý phần việc hợp lệ mà không đánh đổi tính toàn vẹn dữ liệu bằng sự thành công giả tạo.
