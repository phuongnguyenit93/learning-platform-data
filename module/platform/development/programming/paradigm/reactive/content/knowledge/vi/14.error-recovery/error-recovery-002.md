# Lỗi kết thúc một chuỗi và phạm vi lỗi của luồng con

Trong Reactive Streams, lỗi là một tín hiệu kết thúc của subscription. Khi publisher phát onError, nó không tiếp tục phát onNext hoặc onComplete trên subscription đó. Quy tắc này vẫn đúng khi pipeline có nhiều toán tử hoặc nhiều luồng con được ghép bằng flatMap.

Điểm dễ gây nhầm lẫn là một pipeline có thể chứa nhiều publisher con. Một publisher con gặp lỗi có thể làm toàn bộ chuỗi bên ngoài kết thúc, hoặc lỗi có thể được xử lý ngay trong phạm vi luồng con để các phần tử khác tiếp tục. Kết quả phụ thuộc vào vị trí đặt toán tử phục hồi và cách ghép luồng.

Bài học này tập trung vào ngữ nghĩa lỗi trong Reactor: lỗi terminal, phạm vi lỗi của inner publisher, cách onErrorResume và onErrorMap tác động lên pipeline, cũng như lựa chọn giữa dừng ngay và trì hoãn truyền lỗi.

## 1. Lỗi là tín hiệu terminal của một subscription

Một publisher có thể phát nhiều onNext, rồi kết thúc bằng đúng một trong hai tín hiệu:

- onComplete() khi luồng kết thúc bình thường.
- onError(Throwable) khi luồng kết thúc do lỗi.

Sau onError, publisher không được phát thêm dữ liệu trên subscription đó. Subscriber cũng không thể yêu cầu publisher tiếp tục từ vị trí lỗi bằng cách gọi request thêm.

Ví dụ:

    Flux<Integer> source = Flux.just(1, 2)
        .concatWith(Flux.error(
            new IllegalStateException("source failed")
        ))
        .concatWith(Flux.just(3, 4));

    source.subscribe(
        value -> System.out.println("next: " + value),
        error -> System.out.println("error: " + error.getMessage()),
        () -> System.out.println("complete")
    );

Subscriber nhận 1, 2, rồi nhận onError. Các giá trị 3 và 4 không được phát, bởi lỗi đã kết thúc chuỗi trước khi phần publisher nối tiếp được đăng ký và tiêu thụ.

Điều này không có nghĩa mọi publisher trong ứng dụng đều bị hỏng vĩnh viễn. Terminal signal thuộc về subscription đang quan sát. Một subscription khác có thể hoạt động độc lập, và một toán tử phục hồi có thể thay publisher bị lỗi bằng publisher khác.

## 2. Phục hồi tạo đường đi mới sau lỗi

Khi một toán tử như onErrorResume xử lý lỗi, nó không làm publisher nguồn quay lại trạng thái trước khi lỗi xảy ra. Thay vào đó, toán tử chuyển sang một publisher thay thế và nối các tín hiệu của publisher thay thế vào downstream.

Ví dụ:

    Flux<Integer> recovered =
        Flux.just(1, 2)
            .concatWith(Flux.error(
                new IllegalStateException("source failed")
            ))
            .onErrorResume(error -> Flux.just(10, 20));

    // Kết quả: 1, 2, 10, 20 rồi onComplete.

Downstream đã nhận 1 và 2 trước khi lỗi xuất hiện. Sau đó nó nhận 10 và 20 từ publisher thay thế. Các giá trị này không phải phần tiếp nối của nguồn ban đầu; chúng là kết quả của nhánh phục hồi.

Nếu publisher thay thế cũng lỗi, lỗi mới được truyền tiếp. Vì vậy, phục hồi không bảo đảm pipeline chắc chắn thành công; nó chỉ định nghĩa cách xử lý cho một loại lỗi cụ thể.

## 3. Phạm vi lỗi khi dùng flatMap

flatMap biến mỗi phần tử của nguồn ngoài thành một publisher con (inner publisher), rồi ghép các publisher con để phát kết quả downstream. Các publisher con có thể hoạt động đồng thời.

Ví dụ:

    Flux<Order> orders = orderSource();

    Flux<Receipt> receipts =
        orders.flatMap(order -> paymentService.charge(order));

Nếu một paymentService.charge(order) phát onError, mặc định lỗi đó được truyền ra chuỗi flatMap. Chuỗi kết quả kết thúc bằng lỗi; các publisher con đang hoạt động khác và nguồn ngoài sẽ được yêu cầu hủy khi lỗi được truyền đi.

Đây là hành vi fail-fast: một lỗi trong nhánh con có thể làm kết thúc toàn bộ pipeline ghép. Nó phù hợp khi mọi kết quả đều cần thiết để hoàn thành một đơn vị công việc, hoặc khi không thể tiếp tục an toàn sau một lỗi.

Một điều cần nhớ: lỗi xảy ra trong inner publisher và lỗi phát sinh ngay trong hàm mapper không hoàn toàn cùng phạm vi. onErrorResume đặt trên publisher được trả về từ mapper xử lý lỗi tín hiệu của publisher đó. Nếu chính hàm mapper ném exception trước khi trả publisher, lỗi được flatMap xem như lỗi của phép biến đổi bên ngoài; toán tử phục hồi nằm bên trong publisher chưa được tạo nên không bắt được lỗi đó.

## 4. Phục hồi riêng từng luồng con

Nếu mỗi phần tử có thể được xử lý độc lập, ta có thể đặt onErrorResume bên trong mapper của flatMap. Khi một inner publisher gặp lỗi thuộc loại có thể phục hồi, chỉ nhánh đó được thay bằng kết quả dự phòng. Những inner publisher khác vẫn tiếp tục.

Ví dụ xử lý thanh toán:

    Flux<PaymentResult> results =
        orders.flatMap(order ->
            paymentService.charge(order)
                .map(receipt ->
                    PaymentResult.paid(order.id(), receipt)
                )
                .onErrorResume(
                    PaymentDeclinedException.class,
                    error -> Mono.just(
                        PaymentResult.declined(
                            order.id(),
                            error.getMessage()
                        )
                    )
                ),
            8
        );

Trong ví dụ này:

- Mỗi order tạo một inner Mono độc lập.
- Nếu thanh toán bị từ chối, inner publisher đó phát một PaymentResult.declined rồi hoàn tất bình thường.
- Các order khác vẫn được xử lý theo luồng của chúng.
- Lỗi ngoài nhóm PaymentDeclinedException vẫn thoát khỏi inner publisher và có thể kết thúc toàn bộ flatMap.
- Tham số 8 giới hạn số inner publisher được xử lý đồng thời.

Đây là cách thích hợp khi lỗi có ý nghĩa cục bộ đối với từng phần tử và nghiệp vụ cho phép tạo kết quả riêng cho phần tử thất bại.

### 4.1. Phạm vi của toán tử phục hồi

Vị trí của onErrorResume quyết định lỗi nào nó quan sát:

    orders.flatMap(order ->
        paymentService.charge(order)
            .onErrorResume(
                PaymentDeclinedException.class,
                error -> Mono.just(fallbackReceipt(order))
            )
    );

Toán tử ở bên trong mapper chỉ quan sát lỗi phát ra từ publisher thanh toán của order tương ứng. Nó không tự bắt lỗi từ nguồn orders, lỗi do mapper ném ra trước khi trả publisher, hoặc lỗi từ các bước đặt sau flatMap.

Ngược lại:

    orders
        .flatMap(paymentService::charge)
        .onErrorResume(
            PaymentGatewayUnavailableException.class,
            error -> loadAlternativeResults()
        );

Toán tử ở bên ngoài quan sát lỗi của toàn chuỗi đã ghép. Nó có thể bắt lỗi từ nguồn ngoài hoặc bất kỳ inner publisher nào đã truyền lỗi ra flatMap. Khi nhánh này phục hồi, publisher thay thế đại diện cho phần còn lại của chuỗi kết quả.

| Vị trí đặt phục hồi | Phạm vi lỗi được xử lý | Hệ quả |
|---|---|---|
| Trong mapper, sau publisher con | Lỗi của inner publisher đó | Chỉ nhánh con được thay thế |
| Sau flatMap | Lỗi thoát ra khỏi toàn bộ flatMap | Thay thế phần còn lại của chuỗi đã ghép |
| Trước flatMap | Lỗi của nguồn ngoài trước khi tạo inner publisher | Không bắt lỗi phát sinh bên trong publisher con |

## 5. Lỗi ở nguồn ngoài và lỗi ở luồng con

Hãy phân biệt hai đường lỗi:

1. **Outer publisher lỗi:** nguồn cung cấp các phần tử cho flatMap phát onError. Chuỗi ngoài kết thúc và các inner publisher đang chạy bị yêu cầu hủy.
2. **Inner publisher lỗi:** một publisher được tạo từ mapper phát onError. Mặc định flatMap truyền lỗi ra downstream và hủy các nhánh còn lại.

Có thể hình dung:

    Outer:  order-A ---- order-B ---- order-C ---- onComplete
               |            |            |
               v            v            v
    Inner:   charge-A     charge-B     charge-C
                 |            |
              onNext       onError
                              |
                              v
    flatMap:              onError

Nếu lỗi của charge-B không được phục hồi bên trong nhánh B, lỗi đi ra flatMap. charge-A hoặc charge-C có thể đang thực thi đồng thời; Reactor sẽ truyền yêu cầu hủy tới các nhánh còn lại khi xử lý lỗi fail-fast. Không nên giả định side effect đã hoàn tất ở nhánh khác sẽ tự động được hoàn tác.

Nếu mỗi order cần kết quả độc lập, hãy phục hồi lỗi cục bộ hoặc biểu diễn lỗi như một phần của kiểu kết quả. Nếu cả lô phải thành công cùng nhau, để lỗi lan ra ngoài có thể là hành vi đúng.

## 6. Phân biệt onErrorResume, onErrorMap và doOnError

Ba toán tử thường xuất hiện gần nhau nhưng có mục đích khác nhau:

| Toán tử | Tác dụng | Có thay lỗi bằng kết quả khác? |
|---|---|---|
| onErrorResume | Chuyển sang publisher dự phòng | Có |
| onErrorMap | Chuyển Throwable hiện tại thành Throwable khác | Không |
| doOnError | Thực hiện side effect khi quan sát lỗi | Không |

### 6.1. onErrorResume: chuyển sang publisher thay thế

    Mono<Profile> profile =
        profileService.load(userId)
            .onErrorResume(
                ProfileServiceUnavailable.class,
                error -> profileCache.find(userId)
            );

Nếu dịch vụ hồ sơ tạm thời không khả dụng, pipeline chuyển sang cache. Nếu cache cũng lỗi, lỗi đó được truyền downstream.

### 6.2. onErrorMap: đổi loại lỗi

    Mono<Profile> profile =
        profileService.load(userId)
            .onErrorMap(
                RemoteCallException.class,
                error -> new ProfileLookupException(
                    "Không thể tải hồ sơ",
                    error
                )
            );

onErrorMap giữ lỗi ở trạng thái terminal nhưng đổi loại hoặc bổ sung ngữ cảnh. Giữ exception gốc làm cause để phục vụ điều tra.

### 6.3. doOnError: quan sát mà không phục hồi

    Mono<Profile> profile =
        profileService.load(userId)
            .doOnError(error ->
                metrics.incrementProfileFailures()
            );

doOnError thích hợp để ghi log, metric hoặc trace. Sau callback, lỗi vẫn tiếp tục truyền xuống downstream. Không dùng nó như thể đã xử lý xong lỗi.

## 7. Fallback bên ngoài không quay lại xử lý các phần tử trước đó

Khi đặt onErrorResume sau một pipeline flatMap, các phần tử đã phát thành công trước lỗi vẫn được giữ lại. Publisher thay thế chỉ cung cấp tín hiệu sau thời điểm lỗi.

Ví dụ:

    Flux<String> values =
        Flux.just("A", "B", "C")
            .flatMap(value -> {
                if (value.equals("B")) {
                    return Mono.error(
                        new IllegalStateException("failed at B")
                    );
                }
                return Mono.just(value);
            })
            .onErrorResume(error -> Flux.just("FALLBACK"));

Với flatMap, các nhánh có thể chạy đồng thời nên không nên dựa vào thứ tự tuyệt đối của các giá trị đã phát. Khi lỗi xảy ra, nhánh dự phòng phát FALLBACK; pipeline không tự chạy lại A, B hoặc C.

Nếu yêu cầu là thử lại một phần tử cụ thể, đặt retry hoặc fallback bên trong publisher con. Nếu cần chạy lại toàn bộ thao tác, đặt chính sách retry ở phạm vi publisher đại diện cho toàn bộ thao tác và cân nhắc side effect đã xảy ra trước đó.

## 8. Khi nào nên dừng ngay và khi nào nên trì hoãn lỗi?

Các toán tử ghép luồng mặc định thường truyền lỗi ngay khi nhận được. Với flatMap, một lỗi inner có thể kết thúc chuỗi dù những inner khác chưa xong.

Trong một số nghiệp vụ xử lý lô, ta muốn thu thập kết quả từ những nhánh vẫn thành công trước khi báo lỗi. Reactor cung cấp biến thể delay-error, chẳng hạn flatMapDelayError, để trì hoãn việc truyền lỗi cho đến khi các publisher liên quan có cơ hội hoàn tất theo chính sách của toán tử.

Ví dụ:

    Flux<Result> results =
        requests.flatMapDelayError(
            request -> remoteService.execute(request),
            8,
            32
        );

8 là concurrency tối đa và 32 là prefetch trong ví dụ. Với biến thể delay-error, lỗi được giữ lại để truyền xuống sau khi các nhánh liên quan đã được xử lý theo semantics của operator. Cần đọc rõ overload đang dùng và cân nhắc rằng nguồn ngoài vô hạn hoặc không hoàn tất có thể khiến lỗi bị trì hoãn rất lâu.

Chọn chính sách theo mục tiêu:

- Dùng fail-fast khi lỗi làm cho kết quả chung không còn đáng tin cậy hoặc cần dừng sớm để tiết kiệm tài nguyên.
- Dùng phục hồi cục bộ khi từng phần tử độc lập và có kết quả thay thế hợp lệ.
- Dùng delay-error khi muốn thu thập thêm kết quả thành công trước khi báo lỗi.
- Dùng broker hoặc cơ chế lưu trữ bền vững nếu cần tiếp tục xử lý các phần tử lỗi sau này.

Delay-error không tự sửa lỗi, không biến lỗi thành thành công và không bảo đảm mọi phần tử đều có kết quả. Nó chỉ thay đổi thời điểm lỗi được truyền xuống.

## 9. onErrorContinue không phải lựa chọn mặc định cho mọi luồng con

Reactor có onErrorContinue cho một số toán tử upstream hỗ trợ tiếp tục sau lỗi xử lý một phần tử. Tuy nhiên, đây là chính sách có phạm vi và semantics riêng; không phải cơ chế tổng quát để bắt mọi lỗi trong flatMap.

Một số điểm cần thận trọng:

- Chỉ những operator hỗ trợ chiến lược này mới có thể tiếp tục sau lỗi.
- Chiến lược thường áp dụng cho lỗi phát sinh khi xử lý một phần tử upstream, không tự động bắt mọi lỗi từ publisher con bất đồng bộ.
- Phạm vi ảnh hưởng ngược về các operator upstream có thể khó đọc nếu đặt ở vị trí không phù hợp.
- Bỏ qua phần tử lỗi có thể làm mất dữ liệu nghiệp vụ mà không có fallback rõ ràng.

Với lỗi trong inner publisher, ưu tiên đặt onErrorResume ngay trên publisher con để người đọc thấy rõ phần tử nào được phục hồi và kết quả thay thế là gì. Chỉ dùng onErrorContinue khi đã hiểu operator hỗ trợ, phạm vi áp dụng và chấp nhận việc bỏ qua phần tử.

## 10. Retry và phục hồi trong phạm vi luồng con

Retry cũng là một chính sách xử lý lỗi. Đặt retry bên trong mapper nghĩa là chỉ thử lại thao tác của phần tử đó:

    Flux<Receipt> receipts =
        orders.flatMap(order ->
            paymentService.charge(order)
                .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                        .filter(TemporaryGatewayException.class::isInstance)
                ),
            8
        );

Trong ví dụ, lỗi tạm thời có thể khiến thao tác thanh toán của một order được thử lại tối đa hai lần theo backoff. Lỗi khác không khớp bộ lọc sẽ truyền ra ngoài. Retry có thể gọi lại side effect, vì vậy thao tác thanh toán cần idempotency key hoặc cơ chế chống ghi nhận trùng.

Nếu đặt retry sau flatMap, cả chuỗi ghép có thể được subscribe lại khi lỗi xảy ra. Với nguồn cold, điều đó có thể tạo lại nhiều thao tác đã thành công trước đó. Với nguồn hot, lần subscribe mới có thể không nhận lại các sự kiện đã phát. Hãy đặt retry tại phạm vi nhỏ nhất có thể thực hiện an toàn và xác định rõ hành vi của nguồn.

## 11. Kiểm thử phạm vi lỗi bằng StepVerifier

StepVerifier cho phép xác nhận lỗi được phục hồi trong inner publisher hay truyền ra ngoài toàn bộ chuỗi.

### 11.1. Phục hồi cục bộ: các phần tử khác tiếp tục

    Flux<String> result =
        Flux.just("A", "B", "C")
            .flatMap(value -> {
                if (value.equals("B")) {
                    return Mono.<String>error(
                        new IllegalStateException("B failed")
                    ).onErrorResume(error ->
                        Mono.just("B-FALLBACK")
                    );
                }
                return Mono.just(value);
            });

    StepVerifier.create(result)
        .expectNext("A", "B-FALLBACK", "C")
        .verifyComplete();

Vì lỗi của B được phục hồi bên trong publisher con, nhánh B phát giá trị dự phòng và hoàn tất. Nhánh A và C vẫn có kết quả bình thường. Trong ví dụ dùng các Mono đồng bộ nên thứ tự đầu ra được xác định; với các inner publisher bất đồng bộ, flatMap không bảo đảm thứ tự theo phần tử nguồn.

### 11.2. Không phục hồi: lỗi inner kết thúc flatMap

    Flux<String> result =
        Flux.just("A", "B", "C")
            .flatMap(value -> {
                if (value.equals("B")) {
                    return Mono.error(
                        new IllegalStateException("B failed")
                    );
                }
                return Mono.just(value);
            });

    StepVerifier.create(result)
        .expectErrorMessage("B failed")
        .verify();

Lỗi của publisher con truyền ra flatMap; subscriber nhận onError. Không có kỳ vọng rằng nhánh C sẽ luôn hoàn tất hoặc phát giá trị, bởi các nhánh còn lại có thể bị hủy.

### 11.3. Fallback bên ngoài: thay phần còn lại của pipeline

    Flux<String> result =
        Flux.just("A", "B", "C")
            .flatMap(value -> {
                if (value.equals("B")) {
                    return Mono.error(
                        new IllegalStateException("B failed")
                    );
                }
                return Mono.just(value);
            })
            .onErrorResume(error -> Flux.just("RECOVERED"));

    StepVerifier.create(result)
        .expectNext("A", "RECOVERED")
        .verifyComplete();

Trong trường hợp các Mono phát đồng bộ như ví dụ, A đã được phát trước khi B gây lỗi. Nhánh fallback sau flatMap phát RECOVERED. C không được xử lý tiếp sau lỗi. Với các publisher chạy đồng thời, tập phần tử đã phát trước khi lỗi được truyền có thể khác; hãy tránh dựa vào thứ tự không được bảo đảm.

## 12. Những lỗi thiết kế thường gặp

**Đặt onErrorResume quá xa nguồn lỗi.** Fallback ở ngoài flatMap có thể thay thế cả chuỗi đã ghép. Nếu chỉ muốn phục hồi một order, đặt nó trên inner publisher tương ứng.

**Cho rằng lỗi inner chỉ ảnh hưởng inner đó.** Mặc định flatMap truyền lỗi inner ra ngoài và hủy các nhánh còn lại. Cần phục hồi cục bộ hoặc chọn delay-error nếu nghiệp vụ yêu cầu.

**Cho rằng onErrorResume làm publisher gốc tiếp tục.** Nó chuyển sang publisher thay thế. Các phần tử đã phát vẫn giữ nguyên, nhưng phần còn lại của nguồn lỗi không tự chạy lại.

**Nuốt mọi lỗi bằng dữ liệu mặc định.** Chỉ fallback cho loại lỗi có thể xử lý và dữ liệu thay thế có ý nghĩa nghiệp vụ. Lỗi lập trình hoặc dữ liệu sai có thể cần truyền tiếp.

**Retry một side effect mà không chống trùng.** Một request có thể đã được xử lý ở phía xa nhưng phản hồi bị mất. Retry cần idempotency hoặc một giao thức bảo đảm phù hợp.

**Dùng onErrorContinue như try/catch chung.** Operator này có phạm vi hỗ trợ cụ thể và có thể khiến phần tử lỗi bị bỏ qua. Ưu tiên phục hồi rõ ràng tại publisher con.

**Dùng delay-error cho nguồn không bao giờ kết thúc.** Lỗi có thể bị giữ lại trong khi pipeline tiếp tục chờ nguồn. Hãy xác định deadline và điều kiện hoàn tất.

## 13. Checklist xác định phạm vi lỗi

Khi một pipeline có publisher con, hãy lần theo các câu hỏi:

1. Lỗi phát sinh từ nguồn ngoài, hàm mapper hay publisher con?
2. Toán tử phục hồi nằm bên trong mapper hay sau operator ghép luồng?
3. Lỗi có thể phục hồi cục bộ cho một phần tử hay làm mất tính hợp lệ của toàn bộ kết quả?
4. Những inner publisher nào có thể đang chạy đồng thời khi lỗi xuất hiện?
5. Hành vi mặc định có hủy nguồn ngoài và các nhánh còn lại không?
6. Cần fail-fast, fallback cục bộ hay delay-error?
7. Retry có thể lặp side effect không và cơ chế idempotency nằm ở đâu?
8. StepVerifier đã kiểm tra cả nhánh phục hồi và nhánh lỗi terminal chưa?

Khi hiểu lỗi là tín hiệu terminal và đặt chính sách phục hồi đúng phạm vi, ta có thể quyết định một lỗi nên dừng toàn bộ pipeline hay chỉ thay thế một luồng con. Đây là nền tảng để xây dựng các pipeline Mono và Flux có hành vi lỗi rõ ràng, giữ được tính nhất quán của nghiệp vụ và dễ kiểm thử trong hệ sinh thái Java reactive.
