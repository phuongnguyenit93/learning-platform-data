# Xử lý tràn và quan sát dữ liệu bị loại bỏ trong Reactor

## 1. Mục tiêu: điều gì xảy ra khi nguồn nhanh hơn bên nhận?

Trong **Spring WebFlux** và **Project Reactor**, một **Flux<T>** có thể nhận sự kiện từ thiết bị, WebSocket, message broker hoặc một luồng tính toán nhanh hơn tốc độ xử lý của Subscriber. Reactive Streams giải quyết chênh lệch này bằng **backpressure**: Subscriber gửi **request(n)**, còn Publisher chỉ được phát **onNext** trong phạm vi nhu cầu chưa được đáp ứng.

Tuy nhiên, không phải nguồn nào cũng có thể tự giảm tốc độ. Cảm biến, callback API hoặc hệ thống đẩy sự kiện có thể tiếp tục tạo dữ liệu khi downstream đang bận. Lúc đó cần **quyết định có chủ đích**: giữ dữ liệu trong bộ đệm, bỏ dữ liệu dư, chỉ giữ dữ liệu mới nhất, hoặc báo lỗi khi tràn. Đồng thời phải **quan sát và dọn dẹp dữ liệu bị loại bỏ**, đặc biệt nếu phần tử chứa tài nguyên như buffer, file handle hay kết nối.

Bài học này tập trung vào:

- **onBackpressureBuffer**, **onBackpressureDrop**, **onBackpressureLatest**, **onBackpressureError**.
- Giới hạn buffer và các chiến lược **BufferOverflowStrategy.ERROR**, **DROP_LATEST**, **DROP_OLDEST**.
- Callback **onOverflow/onDropped**, **doOnDiscard** và sự khác biệt với **Hooks.onNextDropped**.
- Cách phân biệt **overflow**, **discard thông thường**, **tín hiệu đến quá muộn** và **cancellation**.
- Ví dụ Java 17+ có thể biên dịch/chạy được, cách đọc output và nguyên tắc dùng trong Spring WebFlux.

## 2. Ôn cơ chế demand trước khi chọn chính sách tràn

Một subscription gồm hai chiều giao tiếp:

~~~text
Subscriber                                      Publisher
    | --------- subscribe(...) -----------------> |
    | <-------- onSubscribe(subscription) ------- |
    | --------- request(2) ---------------------> |
    | <-------- onNext(A) ----------------------- |
    | <-------- onNext(B) ----------------------- |
    |           (hết demand hiện tại)              |
    | --------- request(1) ---------------------> |
    | <-------- onNext(C) ----------------------- |
    | <-------- onComplete / onError ------------ |
~~~

- **request(2)** cấp quyền phát tối đa hai phần tử bổ sung, không bắt buộc Publisher phải phát đủ hai.
- Những yêu cầu hợp lệ có thể cộng dồn; **request(0)** hoặc giá trị âm vi phạm hợp đồng Reactive Streams.
- **onComplete** và **onError** là tín hiệu kết thúc, không cần một request mới để được gửi.
- **cancel()** yêu cầu hủy; nó không phải tín hiệu thành công **onComplete**.
- Một Publisher **tuân thủ giao thức** không phát quá lượng dữ liệu downstream đã request. Tuy nhiên, những operator đệm hoặc loại bỏ dữ liệu có thể chủ động **request(Long.MAX_VALUE)** từ upstream rồi quản lý nhu cầu nhỏ hơn ở downstream.

Chính điểm cuối giải thích vì sao ví dụ với **Flux.range(1, 5)**, vốn tuân thủ demand, vẫn minh họa được việc drop hoặc overflow: khi đặt **onBackpressureDrop** hoặc **onBackpressureBuffer** ở giữa, operator đó yêu cầu không giới hạn từ **Flux.range**, nhưng Subscriber phía sau chỉ yêu cầu một phần tử. Sự chênh lệch nằm **giữa operator và Subscriber cuối**, không có nghĩa Flux.range đã vi phạm Reactive Streams.

## 3. Ba khái niệm phải phân biệt: overflow, discard và dropped signal

| Hiện tượng | Bối cảnh | Ví dụ | Cơ chế quan sát phù hợp |
| --- | --- | --- | --- |
| **Backpressure overflow** | Nguồn vẫn phát trong khi downstream thiếu demand hoặc hàng đợi đã đầy | Buffer tối đa 100 item, item thứ 101 đến | **onOverflow**, **onBackpressureDrop(callback)**, **onBackpressureError**, metrics |
| **Discard** | Operator chủ động loại phần tử theo logic bình thường hoặc dọn hàng đợi khi hủy/lỗi | **filter**, **skip**, **onBackpressureLatest**, buffer bị hủy | **doOnDiscard(Class, Consumer)** nếu operator hỗ trợ |
| **Dropped signal** ngoài luồng bình thường | Một signal đến khi không còn nơi hợp lệ để chuyển xuống downstream, thường do nguồn lỗi giao thức hoặc đua trạng thái sau kết thúc | Publisher gửi **onNext** sau **onComplete** | **Hooks.onNextDropped**; tương tự **Hooks.onErrorDropped** với lỗi quá muộn |

Ba tình huống này không đồng nhất. Từ tiếng Anh **drop** trong tên **onBackpressureDrop** chỉ chính sách xử lý áp lực thông thường. Nó **không có nghĩa** mọi phần tử mà operator bỏ đi sẽ đi qua global hook **Hooks.onNextDropped**. Đây là lỗi giám sát rất phổ biến: cài mỗi Hooks.onNextDropped rồi nhận thấy không đếm được các phần tử bị onBackpressureDrop loại bỏ.

**Discard** là khái niệm rộng: một phần tử đã tồn tại trong pipeline nhưng không còn được chuyển tới người tiêu thụ dự kiến. Vì vậy một giá trị bị tràn bộ đệm có thể được báo qua **callback overflow** *và* qua **doOnDiscard** nếu operator hỗ trợ. Hai callback quan sát cùng một phần tử không tự động có nghĩa là hai phần tử đã mất.

## 4. Bốn lựa chọn chính khi downstream chậm

| Operator | Hành vi khi thiếu demand | Có mất dữ liệu? | Có lỗi do quá tải? | Phù hợp |
| --- | --- | --- | --- | --- |
| **onBackpressureBuffer()** | Giữ tạm dữ liệu; bản không giới hạn không có ngưỡng dung lượng ứng dụng đặt ra | Không do chính sách buffer khi còn đủ bộ nhớ; có thể bị discard lúc cancel/error | Có rủi ro cạn bộ nhớ | Dòng hữu hạn, backlog được kiểm soát rõ từ nơi khác |
| **onBackpressureBuffer(maxSize, ...)** | Giữ tối đa maxSize phần tử chờ; đầy thì dùng overflow policy | Tùy policy | Có với policy ERROR | Chấp nhận backlog hữu hạn và xác định rõ khi đầy |
| **onBackpressureDrop(...)** | Bỏ ngay phần tử đến lúc downstream không có demand | **Có** | Thông thường không vì overflow | Sự kiện có thể bỏ mà không phá nghiệp vụ |
| **onBackpressureLatest()** | Chỉ giữ một phần tử mới nhất đang chờ; thay phần tử cũ khi có mới | **Có** | Thông thường không vì overflow | Trạng thái hiện tại, tiến độ, vị trí, telemetry tức thời |
| **onBackpressureError()** | Không đệm phần tử dư; báo overflow qua onError | Không tiếp tục chuỗi, nên mất dữ liệu chưa xử lý | **Có** | Khi không được phép âm thầm bỏ bản ghi |

**Không có chiến lược hoàn hảo cho mọi nghiệp vụ.** Với giao dịch tài chính, thông điệp cần xử lý chính xác một lần hoặc audit bắt buộc, việc bỏ dữ liệu có thể sai về mặt nghiệp vụ. Khi đó ưu tiên nguồn hỗ trợ demand, giới hạn tốc độ đầu vào, hàng đợi bền vững hoặc điều chỉnh concurrency. Với biểu đồ realtime, trạng thái mới nhất có thể quan trọng hơn mọi trạng thái trung gian.

Các operator này **không biến downstream thành nhanh hơn**. Chúng quyết định điểm nào sẽ chịu rủi ro: dung lượng bộ nhớ, độ mất mát dữ liệu, hoặc việc thất bại sớm.

## 5. onBackpressureBuffer: giữ backlog và xử lý khi đầy

### 5.1. Bản không giới hạn

~~~java
Flux<Event> adapted = events.onBackpressureBuffer();
~~~

Đây là snippet trong ứng dụng có kiểu **Event** và nguồn **events**. Operator yêu cầu unbounded từ upstream và giữ những phần tử chưa thể chuyển cho downstream. Nếu upstream chạy nhanh liên tục, dữ liệu có thể tích lũy lâu dài. **Không dùng dạng này một cách vô thức cho nguồn vô hạn tốc độ cao** vì có nguy cơ tăng heap, GC pressure và **OutOfMemoryError**. Nó cũng không cung cấp chính sách nghiệp vụ cho trường hợp backlog vượt khả năng bộ nhớ.

### 5.2. Buffer giới hạn: tràn thành lỗi

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(256);
~~~

Buffer có sức chứa tối đa 256 item chờ downstream (bên cạnh item đang được xử lý). Khi dữ liệu mới không thể được nhận vì đã đầy, Reactor **báo overflow**, yêu cầu hủy upstream. Theo tài liệu API, lỗi overflow có thể được **trì hoãn chuyển xuống downstream cho đến khi dữ liệu tồn đọng trong buffer được yêu cầu và xử lý**. Đừng nhầm "overflow xảy ra ngay" với "Subscriber chắc chắn nhận onError ngay lập tức" khi vẫn còn phần tử đệm cần drain.

Phiên bản có callback:

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(
    256,
    discarded -> recordOverflow(discarded)
);
~~~

Callback **recordOverflow** (hàm ứng dụng giả định) nhận phần tử gây tràn; dạng overload này vẫn có chính sách lỗi khi hết chỗ. Callback chỉ là nơi quan sát/cleanup, **không làm mất lỗi** và không tự cấp thêm dung lượng.

### 5.3. Chọn chiến lược tràn trên buffer hữu hạn

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(
    256,
    removed -> recordEviction(removed),
    BufferOverflowStrategy.DROP_OLDEST
);
~~~

Cần import **reactor.core.publisher.BufferOverflowStrategy**. Ba lựa chọn của enum:

- **ERROR**: khi buffer đầy, phát sinh lỗi tràn; lỗi có thể được báo sau khi lượng dữ liệu đang đệm đã drain.
- **DROP_LATEST**: bỏ **phần tử mới đến** khi buffer đầy; giữ lại backlog đã có.
- **DROP_OLDEST**: bỏ **phần tử cũ nhất trong buffer**, đưa phần tử mới vào cuối hàng đợi; ưu tiên dữ liệu gần hiện tại hơn.

| Buffer đang có | Phần tử mới | Chiến lược | Buffer sau xử lý | Phần tử bị bỏ |
| --- | --- | --- | --- | --- |
| [A, B] | C | **DROP_LATEST** | [A, B] | C |
| [A, B] | C | **DROP_OLDEST** | [B, C] | A |
| [A, B] | C | **ERROR** | Chuyển sang trạng thái tràn/lỗi | C và có thể dọn dữ liệu theo vòng đời |

Tên **DROP_LATEST** đôi khi gây nhầm: trong ngữ cảnh **BufferOverflowStrategy**, nó bỏ **item vừa đến khi buffer đầy**. **onBackpressureLatest()** là operator khác, chủ động giữ **item mới nhất** và thay giá trị cũ đang chờ.

Với overload **onBackpressureBuffer(maxSize, callback, strategy)**, callback được gọi khi tràn, nhận phần tử **thực sự bị loại bỏ**. Với **DROP_OLDEST**, đó có thể là item cũ trong buffer, **không phải** item mới vừa được Publisher phát. Điều này quan trọng khi ghi log id sự kiện, thống kê hoặc giải phóng tài nguyên.

### 5.4. Buffer có TTL

Reactor còn cung cấp những overload đặt **TTL (time to live)** và giới hạn số lượng phần tử, ví dụ dạng:

~~~java
Flux<Event> ttlBuffer = events.onBackpressureBuffer(
    Duration.ofSeconds(2),
    256,
    expiredOrEvicted -> recordEviction(expiredOrEvicted)
);
~~~

Ở đây **Duration** đến từ **java.time.Duration**. Bản này giúp loại dữ liệu quá cũ hoặc dữ liệu bị đẩy khỏi buffer vì dung lượng. TTL hữu ích với telemetry có thời hạn; với sự kiện nghiệp vụ không được mất, expiration **không an toàn** nếu chưa có cơ chế bù/khôi phục.

Đừng diễn giải TTL là việc giới hạn mọi bộ đệm trong toàn bộ pipeline: các operator khác, client HTTP, network buffers và nguồn phát vẫn có thể có vùng đệm riêng.

## 6. onBackpressureDrop: bỏ phần tử dư ngay và quan sát trực tiếp

~~~java
Flux<Event> tolerant = events
    .onBackpressureDrop(event -> countDropped(event));
~~~

Khi downstream hết nhu cầu, operator bỏ item đi và gọi callback **countDropped** (hàm ứng dụng giả định). Một request mới **không làm hồi sinh** các item đã bỏ; nó chỉ cho phép các item tiếp theo đến sau đó được truyền xuống, nếu còn nguồn.

Đây là lựa chọn hợp lý với các frame hiển thị tạm thời hoặc đo đạc dày đặc không cần giữ mọi điểm. Không phù hợp với lịch sử giao dịch, lệnh thanh toán, thay đổi trạng thái bắt buộc hoặc bất kỳ sự kiện nào mà mất một item làm sai kết quả.

**Cơ chế demand cần nhớ:** onBackpressureDrop có thể yêu cầu **unbounded từ upstream**, rồi quyết định tại chính nó có truyền item xuống downstream hay bỏ không. Đây là một **điểm quyết định mất dữ liệu**. Dù Publisher upstream là nguồn tôn trọng backpressure, việc đặt operator này có thể làm upstream phát nhiều hơn số item Subscriber cuối request.

Ví dụ ý tưởng:

~~~text
upstream phát: 1 2 3 4 5
downstream đã request: 1 phần tử
onBackpressureDrop:
  deliver: 1
  drop:    2 3 4 5
~~~

Đây là tình huống được dựng có chủ đích ở ví dụ thực hành phần 10. Với nhiều request được cấp trong lúc nguồn tiếp tục phát, các item được nhận và bị bỏ sẽ phụ thuộc thời điểm nhu cầu xuất hiện; không nên gắn cứng những con số trên vào mọi runtime.

### Quan sát theo item hay chỉ theo số lượng?

Callback nhận từng phần tử có thể dùng để đếm, ghi loại sự kiện hoặc giải phóng tài nguyên. Trong luồng tốc độ cao, **không nên ghi một dòng log đồng bộ cho từng phần tử rơi** vì việc log có thể trở thành nút nghẽn mới. Thường dùng **counter**, log sampling hoặc metrics theo nhóm phân loại, rồi cảnh báo khi tỷ lệ mất dữ liệu vượt ngưỡng.

## 7. onBackpressureLatest: cập nhật trạng thái mới nhất

~~~java
Flux<State> updates = stateChanges
    .onBackpressureLatest();
~~~

Nếu downstream đang bận, operator có thể giữ **một item đang chờ**. Khi item mới xuất hiện, item cũ đang chờ được **thay thế và bị discard**. Khi downstream request thêm, nó nhận trạng thái mới nhất còn được giữ.

~~~text
Subscriber nhận: A         [tạm hết demand]           request(1)
Nguồn phát tiếp:          B       C       D
Giá trị đang chờ:         B  ->   C  ->   D
Discard:                      B       C
Subscriber nhận cuối:                                  D
~~~

**onBackpressureLatest** hợp với vị trí GPS hiện tại, phần trăm tiến độ, nhiệt độ hiển thị hoặc trạng thái màn hình. Không hợp nếu downstream phải xử lý **mọi thay đổi trung gian**. Nếu cần tích lũy phép cộng, số dư hoặc state transition, chỉ giữ snapshot cuối có thể không đủ trừ khi mỗi snapshot **đã là trạng thái hoàn chỉnh**.

Phân biệt:

- **onBackpressureDrop**: khi thiếu demand, item mới bị bỏ ngay.
- **onBackpressureLatest**: khi thiếu demand, item mới **thay** item cũ đang chờ.
- **BufferOverflowStrategy.DROP_LATEST**: khi **buffer hữu hạn đã đầy**, bỏ item mới, giữ các item cũ trong buffer.
- **BufferOverflowStrategy.DROP_OLDEST**: khi buffer đầy, đẩy item cũ nhất ra để nhận item mới, nhưng vẫn có thể giữ **nhiều item** khác nhau tùy dung lượng buffer.

## 8. onBackpressureError: chọn thất bại thay cho mất dữ liệu âm thầm

~~~java
Flux<Event> strict = events
    .onBackpressureError();
~~~

Nếu một item đến mà downstream chưa cấp đủ demand, operator báo **onError** dạng overflow và hủy upstream. Đây là lựa chọn khi yêu cầu nghiệp vụ cho phép **báo lỗi và thử lại có kiểm soát**, nhưng không cho phép im lặng bỏ dữ liệu. Cần thiết kế phù hợp để xử lý lỗi mà không nhân đôi side effect.

Ví dụ xử lý lỗi:

~~~java
Flux<Event> monitored = events
    .onBackpressureError()
    .doOnError(error -> reportFailure(error));
~~~

**reportFailure** là hàm giả định. **doOnError** chỉ quan sát, không tiêu thụ hoặc thay thế lỗi. Nếu xử lý bằng **onErrorResume**, phải có chính sách rõ ràng: có được bỏ phần còn lại của stream, chuyển sang queue khác, hay cần báo yêu cầu HTTP thất bại?

Không dùng **onErrorComplete()** hay **onErrorResume(error -> Flux.empty())** một cách máy móc để “chữa” overflow nếu thực chất nó làm biến mất dữ liệu quan trọng. Overflow là tín hiệu hệ thống không chịu nổi tốc độ hiện tại; việc biến nó thành complete thành công có thể che giấu mất dữ liệu.

## 9. Theo dõi dữ liệu bị loại bỏ: callback cục bộ, doOnDiscard và Hooks

### 9.1. Callback trực tiếp của chính sách tràn

Khi nguyên nhân loại bỏ là **chính sách cụ thể**, callback trực tiếp thường là điểm quan sát rõ nhất:

~~~java
Flux<Event> dropAware = events
    .onBackpressureDrop(event -> {
        metrics.incrementDrop();
        cleanupIfNeeded(event);
    });
~~~

Hoặc:

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(
    128,
    discarded -> metrics.incrementBufferEviction(),
    BufferOverflowStrategy.DROP_OLDEST
);
~~~

Các kiểu **Event**, đối tượng **metrics** và hàm **cleanupIfNeeded** là ví dụ ứng dụng. Đầu vào callback chính là phần tử bị chính sách tràn loại bỏ. Với buffer có chiến lược **ERROR**, callback vẫn quan sát phần tử gây tràn, còn pipeline báo lỗi theo chính sách.

### 9.2. doOnDiscard: dọn phần tử bị operator bỏ trong đường đi bình thường

~~~java
Flux<Integer> observed = Flux.range(1, 5)
    .filter(n -> n % 2 == 0)
    .doOnDiscard(Integer.class,
        n -> System.out.println("discarded " + n));
~~~

Tại đây **filter** loại các số lẻ. **doOnDiscard** đặt **phía downstream** so với operator cần quan sát; handler có thể được áp dụng cho các operator upstream có hỗ trợ discard. Callback chạy trên giá trị có kiểu khớp **Integer.class**.

Đặc trưng quan trọng:

1. **doOnDiscard** là hook **cục bộ cho pipeline**, không phải cấu hình toàn cục.
2. Nó chỉ hoạt động với những operator có tài liệu ghi rõ **Discard Support**; không phải mọi operator hay mọi thư viện Publisher đều phát discard event theo cách này.
3. Nó còn hữu ích khi operator có hàng đợi/prefetch **dọn phần tử còn lại sau cancel/error**, không chỉ với **filter**.
4. Một phần tử có thể bị quan sát nhiều lần khi có nhiều hook hoặc nhiều điểm cleanup trong pipeline. Hàm giải phóng tài nguyên nên **idempotent** và an toàn khi được gọi lại.
5. **doOnDiscard không phát item bị loại về downstream**; nó là callback phụ để quan sát/dọn dẹp.

Ví dụ cleanup tài nguyên:

~~~java
Flux<Payload> flow = source
    .onBackpressureLatest()
    .doOnDiscard(Payload.class, Payload::release);
~~~

**Payload** và **release()** là kiểu/phương thức ứng dụng giả định, cần có cơ chế release idempotent và đúng vòng đời. Callback **doOnDiscard** được dùng để trả tài nguyên của item cũ đã bị thay. Với tài nguyên reference-counted như **DataBuffer/ByteBuf**, phải tuân thủ đúng hợp đồng retain/release của thư viện tương ứng; không gọi release bừa trên đối tượng không thuộc quyền sở hữu.

**Cảnh báo về thống kê:** nếu vừa đặt **onBackpressureDrop(onDropped)** vừa đặt **doOnDiscard** cho cùng kiểu phần tử, một item có thể được báo tại cả hai nơi. Cần xác định **một nguồn thống kê chính** để không đếm đôi tỷ lệ mất dữ liệu.

### 9.3. Hooks.onNextDropped: tín hiệu bất thường, không thay cho onBackpressureDrop

~~~java
Hooks.onNextDropped(value -> {
    reportProtocolDrop(value);
});
~~~

Snippet này cần import **reactor.core.publisher.Hooks** và hàm ứng dụng **reportProtocolDrop**. Đây là **hook toàn cục**, nhằm quan sát những tín hiệu **onNext không còn hợp lệ để truyền tiếp**, thường từ Publisher sai giao thức hoặc signal đến sau khi luồng đã kết thúc/cancel. **Hooks.onErrorDropped** dành cho một tín hiệu lỗi bị bỏ vì không còn Subscriber phù hợp để nhận.

Điều phải nhớ:

- **Hooks.onNextDropped** không phải counter chính xác cho item bị loại do **onBackpressureDrop** hay **filter**.
- Đặt global hook có thể ảnh hưởng **mọi pipeline trong JVM**, kể cả thư viện khác; cần quản trị, bảo mật thông tin log và hiểu tác động hiệu năng.
- Trong môi trường test, nếu đã thay đổi hook, phải **khôi phục/reset** trong vòng đời test tương ứng, ví dụ **Hooks.resetOnNextDropped()**. Không đặt/reset global hook giữa chừng trong ứng dụng production đang chạy mà chưa có chiến lược quản trị thống nhất.
- **Hooks.onErrorDropped** ghi nhận lỗi không có đường chuyển tiếp hợp lệ; nó không thay cho **doOnError** trong luồng bình thường.
- Dùng **doOnDiscard** và callback overflow cho đường loại bỏ bình thường; dùng global dropped hooks để tìm hành vi bất thường, không coi chúng là cùng một nhóm sự kiện.

## 10. Ví dụ Java 17+ chạy được: DROP, BUFFER, LATEST, DISCARD

Ví dụ sau chọn **Flux.range** đồng bộ để chứng minh chính sách overflow mà **không phụ thuộc sleep hoặc lịch scheduler**. Một **BaseSubscriber** chỉ request một item lúc đầu; operator backpressure ở giữa request unbounded từ nguồn, tạo đúng tình huống downstream chậm hơn upstream. Mỗi luồng tạo một BaseSubscriber mới, không tái sử dụng Subscriber cũ.

Cấu trúc:

~~~text
overflow-discard-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── OverflowDiscardDemo.java
~~~

Tệp **pom.xml** (Reactor Core 3.6.6, Java 17):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>overflow-discard-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Tệp **src/main/java/OverflowDiscardDemo.java**:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;

public class OverflowDiscardDemo {

    private static BaseSubscriber<Integer> receiveOneInitially() {
        return new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received " + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("complete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println(
                    "error " + error.getClass().getSimpleName()
                );
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("=== DROP ===");

        Flux.range(1, 5)
            .onBackpressureDrop(n ->
                System.out.println("dropped " + n)
            )
            .subscribe(receiveOneInitially());

        System.out.println("=== BUFFER DROP_OLDEST ===");

        BaseSubscriber<Integer> buffered = receiveOneInitially();
        Flux.range(1, 5)
            .onBackpressureBuffer(
                2,
                n -> System.out.println("evicted " + n),
                BufferOverflowStrategy.DROP_OLDEST
            )
            .subscribe(buffered);

        // Lúc này upstream đồng bộ đã phát 1..5.
        // Subscriber chỉ nhận 1; buffer giữ 4,5.
        buffered.request(2);

        System.out.println("=== LATEST ===");

        BaseSubscriber<Integer> latest = receiveOneInitially();
        Flux.range(1, 5)
            .onBackpressureLatest()
            .subscribe(latest);

        // Giá trị 5 là trạng thái mới nhất còn chờ.
        latest.request(1);

        System.out.println("=== DISCARD (filter) ===");

        Flux.range(1, 5)
            .filter(n -> n % 2 == 0)
            .doOnDiscard(Integer.class,
                n -> System.out.println("discarded " + n)
            )
            .subscribe(
                n -> System.out.println("received " + n),
                error -> System.out.println("error " + error),
                () -> System.out.println("complete")
            );
    }
}
~~~

Chạy trong thư mục chứa **pom.xml**, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=OverflowDiscardDemo
~~~

Stdout mong đợi:

~~~text
=== DROP ===
received 1
dropped 2
dropped 3
dropped 4
dropped 5
complete
=== BUFFER DROP_OLDEST ===
received 1
evicted 2
evicted 3
received 4
received 5
complete
=== LATEST ===
received 1
received 5
complete
=== DISCARD (filter) ===
discarded 1
received 2
discarded 3
received 4
discarded 5
complete
~~~

### Vì sao output như vậy?

**DROP:** Subscriber chỉ request(1), nên phần tử 1 được nhận. **onBackpressureDrop** vẫn request unbounded từ upstream; khi 2–5 đến mà downstream chưa xin thêm, chúng đi vào callback dropped. Sau đó nguồn đã hết nên phát **onComplete**; terminal signal không yêu cầu demand mới.

**BUFFER DROP_OLDEST:** Subscriber nhận 1; hàng đợi tối đa hai phần tử giữ **2,3**. Khi 4 đến, phần tử cũ nhất **2** bị loại; buffer thành **3,4**. Khi 5 đến, **3** bị loại; buffer thành **4,5**. Sau khi subscribe trả về, lệnh **buffered.request(2)** cho phép nhận 4 và 5, rồi completion được phát xuống.

**LATEST:** Subscriber nhận 1, rồi không còn demand; các giá trị đang chờ lần lượt bị thay thế cho tới **5**. Lệnh **latest.request(1)** sau khi nguồn đồng bộ đã phát xong nhận 5 và completion.

**DISCARD:** **filter** chỉ nhận số chẵn; các số lẻ bị loại và gọi **doOnDiscard**. Chúng **không phải** phần tử mất do overflow. Subscriber lambda cuối nhận 2 và 4.

Để ví dụ có output xác định, tất cả nguồn đều đồng bộ. Với nguồn WebSocket, message broker hoặc Flux chạy trên scheduler, các mốc request và phát item có thể xen kẽ khác nhau, nên **không sao chép các con số của ví dụ thành kỳ vọng tuyệt đối** cho môi trường production.

## 11. Dự đoán tình huống ERROR và vì sao lỗi có thể đến sau

Giả sử dùng:

~~~java
BaseSubscriber<Integer> slow = new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer n) {
        System.out.println("received " + n);
    }

    @Override
    protected void hookOnError(Throwable error) {
        System.out.println("overflow detected");
    }
};

Flux.range(1, 5)
    .onBackpressureBuffer(1)
    .subscribe(slow);

// Cấp thêm demand để drain phần tử còn nằm trong buffer.
slow.request(1);
~~~

Đây là một snippet Java trong ngữ cảnh đã import **BaseSubscriber**, **Subscription**, **Flux**. Diễn biến dự kiến với nguồn đồng bộ:

1. Item 1 được phát ngay theo demand ban đầu.
2. Item 2 nằm trong buffer sức chứa 1.
3. Item 3 đến làm đầy/tràn; upstream bị hủy và luồng được đánh dấu lỗi overflow.
4. Downstream chưa nhận item 2, nên việc chuyển **onError** có thể chờ; sau **slow.request(1)**, item 2 được chuyển rồi tới lỗi.

**Không nên khẳng định rằng chỉ cần source báo overflow là Subscriber đã nhận onError ngay tức thì** trong mọi cấu hình buffer. Nhu cầu drain dữ liệu đang chờ có thể ảnh hưởng thời điểm downstream quan sát lỗi.

Với **onBackpressureError()** không có phần backlog cần drain theo cách trên: khi nguồn phát vượt demand ngay tại operator, kết quả được báo lỗi overflow. Đây là khác biệt giữa **chính sách fail-fast trực tiếp** và **overflow trên buffer đã giữ dữ liệu chờ**.

## 12. Cancellation, discard và vòng đời tài nguyên

Khi một Subscriber hủy subscription, các operator có prefetch hoặc hàng đợi có thể đang giữ các item chưa được chuyển xuống. Đó là dữ liệu cần dọn, dù không có sự kiện overflow.

Ví dụ:

~~~java
Flux<Payload> transformed = source
    .publishOn(scheduler, 32)
    .onBackpressureBuffer(
        64,
        removed -> recordEviction(removed),
        BufferOverflowStrategy.DROP_OLDEST
    )
    .doOnDiscard(Payload.class, Payload::release);
~~~

Đoạn trên mang tính minh họa với kiểu **Payload**, scheduler, source và hàm cleanup giả định. **publishOn** có cơ chế prefetch/hàng đợi riêng, còn buffer sau đó có giới hạn 64. Khi hủy, phần tử còn trong hàng đợi của operator hỗ trợ discard có thể được chuyển vào **doOnDiscard** để giải phóng tài nguyên.

Lưu ý việc đặt hook ở đâu:

- **doOnDiscard** có tác dụng với các operator **upstream** hỗ trợ discard tại vị trí hook.
- Nếu chỉ đặt hook **trước** operator đang làm rơi phần tử, có thể không quan sát được discard của operator ở downstream.
- Nếu hook chỉ nhận **Payload.class**, các kiểu khác không khớp sẽ không chạy cleanup này.
- Nếu phần tử đã được downstream tiêu thụ thành công, việc release thuộc trách nhiệm luồng xử lý bình thường. **doOnDiscard** chỉ hỗ trợ đường bị loại bỏ, không thay toàn bộ quy tắc sở hữu tài nguyên.
- Cleanup cần idempotent vì cùng một object có thể bị quan sát từ nhiều đường dọn dẹp nếu thiết kế hook chồng lấn.

Trong Netty và WebFlux, các loại dữ liệu reference-counted cần quy tắc retain/release đúng chuẩn. Giải phóng quá sớm có thể dẫn đến use-after-release; không giải phóng có thể gây memory leak. Thiết kế đường lifecycle trước, rồi mới dùng hook để xử lý các nhánh bị loại.

## 13. Giám sát production: đếm đúng nguyên nhân mất dữ liệu

Một hệ thống quan sát tốt nên phân biệt **đã nhận**, **đã xử lý thành công**, **bị loại theo policy**, **bị loại khi cancel**, **bị overflow lỗi**, và **tín hiệu bất thường đến muộn**.

Đề xuất nhóm chỉ số:

| Metric | Nguồn dữ liệu hợp lý | Cần tránh |
| --- | --- | --- |
| **event_received_total** | Điểm nhận dữ liệu trước chính sách mất mát | Không đếm từ downstream đã qua drop rồi gọi là "tổng đầu vào" |
| **event_processed_total** | Điểm xử lý thành công cuối cùng | Không tăng chỉ vì đã gọi onNext |
| **backpressure_drop_total** | Callback **onBackpressureDrop** | Không cộng thêm cùng item từ doOnDiscard |
| **buffer_eviction_total** | Callback overflow/eviction có strategy rõ ràng | Không nhầm evicted cũ thành item mới đến |
| **backpressure_overflow_error_total** | Lỗi overflow được nhận tại ranh giới operator | Không đếm mọi lỗi nghiệp vụ thành overflow |
| **discard_total_by_reason** | doOnDiscard tại điểm cần cleanup, có phân loại phù hợp | Không mặc định mọi discard đều do backpressure |
| **late_signal_dropped_total** | Hooks.onNextDropped/Hooks.onErrorDropped khi cần chẩn đoán | Không coi là metric số phần tử bị onBackpressureDrop |

Đối với rate hoặc tỷ lệ rơi, phải định nghĩa rõ **mẫu số** và ranh giới đo: item nhận từ nguồn hay item đã đến operator? Một pipeline có nhiều operator có thể bỏ cùng item hoặc chuyển đổi số lượng phần tử, nên phép cộng mù quáng những counter độc lập không phản ánh chính xác số item nghiệp vụ bị mất.

Những thông tin log/tracing có ích: tên pipeline, nguồn, loại event, chiến lược overflow, giới hạn buffer, thời gian, consumer group, request/correlation id và trạng thái cancellation. Tránh log toàn bộ payload nhạy cảm hoặc dữ liệu lớn mỗi lần drop.

Một callback metrics nên **nhanh, non-blocking** và không có side effect nghiệp vụ phức tạp. Với workload tốc độ cao, nên dùng counter hoặc queue metrics phù hợp; đừng gọi dịch vụ HTTP hoặc ghi database đồng bộ từ callback overflow.

## 14. Ứng dụng trong Spring WebFlux

Giả sử một endpoint tạo stream sự kiện liên tục (ví dụ server-sent events). Nếu chỉ cần snapshot trạng thái mới nhất:

~~~java
@GetMapping(
    value = "/status/stream",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Status>> statusStream() {
    return statusFeed()
        .onBackpressureLatest()
        .doOnDiscard(Status.class, this::cleanupDroppedStatus)
        .map(status -> ServerSentEvent.builder(status).build());
}
~~~

Đây là snippet trong controller Spring với **Status**, **statusFeed()** và **cleanupDroppedStatus** là thành phần ứng dụng giả định. Đầu ra vẫn là **Flux<ServerSentEvent<Status>>**; Spring WebFlux sẽ subscribe khi xử lý request. Không tự gọi **subscribe()** trong controller chỉ để kích hoạt luồng, vì sẽ tách tác vụ khỏi vòng đời HTTP request.

**Cẩn thận:** ví dụ chỉ phù hợp khi **Status** là snapshot thay thế được và loại bỏ snapshot trung gian không gây sai. Nếu **Status** là thay đổi gia tăng (delta), bỏ một item có thể làm client mất đồng bộ. Cần phát snapshot đầy đủ hoặc triển khai cơ chế replay/resync.

Với dữ liệu bắt buộc giữ đủ, một pipeline như:

~~~java
Flux<Event> critical = eventSource()
    .onBackpressureBuffer(256);
~~~

chưa giải quyết được bài toán độ tin cậy. Buffer 256 trong bộ nhớ vẫn có thể tràn; cancel, lỗi process và crash có thể làm mất dữ liệu. Cần suy nghĩ đến **broker/queue bền vững**, acknowledgement, lưu offset, retry có kiểm soát và idempotent processing. Không thay thế các cơ chế đó bằng việc tăng maxSize vô hạn.

### Điều chỉnh hệ thống trước khi chủ động bỏ dữ liệu

Các lựa chọn thường cần kiểm tra:

1. **Nguồn có tôn trọng demand không?** Nếu có, giữ backpressure end-to-end thay vì thêm operator yêu cầu unbounded không cần thiết.
2. **Concurrency downstream đã hợp lý chưa?** Với tác vụ I/O độc lập, **flatMap(mapper, concurrency)** có thể cải thiện throughput nhưng phải bảo đảm giới hạn kết nối/tài nguyên.
3. **Có chỗ blocking trên event-loop?** Chặn thread I/O khiến downstream chậm giả tạo; xem xét thiết kế non-blocking hoặc scheduler dành cho tác vụ blocking.
4. **Có prefetch/queue trung gian quá lớn?** Các operator như **publishOn**, **flatMap**, **buffer** có thể tạo hàng đợi riêng. Đánh giá toàn pipeline chứ không chỉ một maxSize.
5. **Chính sách nghiệp vụ khi mất một item là gì?** Nếu không thể chấp nhận mất, cần fail hoặc lưu bền vững, không dùng DROP/LATEST chỉ để làm metrics đẹp.

## 15. Các lỗi phổ biến và cách khắc phục

| Hiện tượng hoặc hiểu nhầm | Nguyên nhân / cách hiểu đúng |
| --- | --- |
| "Source tuân thủ request nên onBackpressureDrop không bao giờ drop" | Operator có thể chủ động request unbounded từ source rồi kiểm soát downstream demand, vì thế vẫn có drop tại operator. |
| "onBackpressureBuffer() mặc định an toàn" | Dạng không giới hạn có thể làm tăng bộ nhớ vô hạn với nguồn nhanh; nên đặt giới hạn phù hợp và policy rõ ràng. |
| "BufferOverflowStrategy.DROP_LATEST giữ item mới nhất" | Với buffer đã đầy, nó **bỏ item mới**; muốn chỉ giữ item mới nhất chờ downstream, dùng **onBackpressureLatest()**. |
| "BufferOverflowStrategy.DROP_OLDEST luôn báo item vừa đến" | Callback overflow nhận **item bị loại thực tế**, có thể là item cũ trong buffer. |
| "onBackpressureBuffer đầy thì Subscriber luôn thấy lỗi ngay" | Một số overload trì hoãn chuyển onError cho đến khi backlog được drain. |
| "onBackpressureLatest dùng được cho mọi event" | Nó làm mất event trung gian. Chỉ phù hợp khi mỗi item mới có thể thay thế item cũ về mặt nghiệp vụ. |
| "Hooks.onNextDropped sẽ đếm được onBackpressureDrop" | Global hook cho tín hiệu bất thường; dùng callback operator và **doOnDiscard** cho discard bình thường. |
| "doOnDiscard luôn chạy với mọi toán tử" | Chỉ những operator có **Discard Support** được tài liệu hóa; hook cục bộ ảnh hưởng operator upstream. |
| "Mỗi lần doOnDiscard là một event nghiệp vụ khác nhau" | Có thể quan sát cùng object ở nhiều điểm; cần tránh đếm đôi và cleanup phải idempotent. |
| "drop callback là nơi tốt để gọi dịch vụ logging chặn" | Callback có thể chạy trên đường tín hiệu nóng. Dùng metrics/log sampling nhanh, hạn chế blocking. |
| "cancel đồng nghĩa đã xử lý hết phần tử đang đệm" | Cancel có thể loại bỏ item còn chờ, làm phát sinh discard; không phải onComplete thành công. |
| "Đặt onErrorComplete sau onBackpressureError là an toàn" | Nó có thể che giấu overflow, làm nguồn quan trọng mất dữ liệu mà caller không biết. |
| "Một buffer lớn sửa được producer quá nhanh" | Nó chỉ hấp thụ backlog tạm thời; nếu tốc độ đầu vào dài hạn lớn hơn đầu ra, hàng đợi sẽ đầy hoặc gây áp lực bộ nhớ. |

## 16. Tự kiểm tra và bài tập

**Câu 1.** Downstream request một phần tử, upstream phát đồng bộ 1,2,3,4 qua **onBackpressureDrop**. Kết quả có thể là gì?  
**Đáp án:** nhận 1, bỏ 2–4, sau đó hoàn thành. Điểm cần nhận ra: operator drop chủ động yêu cầu nhiều dữ liệu hơn downstream.

**Câu 2.** Buffer dung lượng 2 đang chứa [A,B], C đến khi downstream không có demand. **DROP_LATEST** và **DROP_OLDEST** khác nhau ra sao?  
**Đáp án:** DROP_LATEST bỏ C, giữ [A,B]; DROP_OLDEST bỏ A, giữ [B,C].

**Câu 3.** Với stream GPS chỉ cần vị trí hiện tại, chọn gì?  
**Đáp án:** **onBackpressureLatest()** có thể phù hợp nếu mỗi giá trị là vị trí đầy đủ, có thể thay thế vị trí cũ.

**Câu 4.** Với luồng giao dịch bắt buộc xử lý đủ, có nên dùng onBackpressureDrop?  
**Đáp án:** không. Cần bảo toàn dữ liệu bằng điều tiết nguồn, hàng đợi bền vững hoặc fail rõ ràng và retry theo hợp đồng nghiệp vụ.

**Câu 5.** Sự khác biệt cốt lõi giữa **doOnDiscard** và **Hooks.onNextDropped** là gì?  
**Đáp án:** doOnDiscard quan sát việc operator hỗ trợ chủ động loại dữ liệu trong luồng bình thường/cancel/error; Hooks.onNextDropped là global hook cho những tín hiệu onNext bất thường không thể chuyển tiếp, thường do vi phạm giao thức hoặc đến muộn.

**Câu 6.** Khi vừa dùng callback **onBackpressureDrop** vừa dùng **doOnDiscard** cho cùng item, có nên cộng cả hai vào một counter "event mất"?  
**Đáp án:** không nên đếm đôi; cần một nguồn thống kê chính và một nguồn cleanup riêng khi cần.

**Bài thực hành A:** Trong chương trình ở phần 10, đổi **DROP_OLDEST** thành **DROP_LATEST**. Dự đoán hai item còn chờ sau khi phát 1–5 với buffer 2 và downstream request(1) ban đầu. **Đáp án:** buffer giữ 2,3; item 4 và 5 bị bỏ. Sau **request(2)**, Subscriber nhận 2,3 rồi complete.

**Bài thực hành B:** Đổi phần **LATEST** thành **onBackpressureError()**, giữ Subscriber ban đầu chỉ request(1). Quan sát luồng dừng bằng callback **hookOnError** khi có phần tử vượt demand; kiểm tra không có onComplete.

**Bài thực hành C:** Bổ sung **doOnDiscard** sau **onBackpressureLatest** và đếm các item trung gian bị thay thế. So sánh counter đó với callback của **onBackpressureDrop** ở ví dụ khác. Kết luận vì sao không nên trộn hai số đếm mà không nêu chiến lược.

## 17. Nguyên tắc triển khai

Chọn chính sách theo câu hỏi **"khi không thể xử lý kịp, item nào được phép mất và làm sao biết nó đã mất?"**:

- **Không chấp nhận mất**: ưu tiên nguồn demand-aware, hàng đợi bền vững; nếu phải kết thúc, dùng **onBackpressureError** hoặc buffer hữu hạn với chính sách lỗi có xử lý rõ.
- **Chấp nhận bỏ từng sự kiện dư**: **onBackpressureDrop** và callback đếm/chẩn đoán.
- **Chỉ cần trạng thái mới nhất**: **onBackpressureLatest** kèm **doOnDiscard** để xử lý tài nguyên bị thay.
- **Muốn giữ backlog hữu hạn**: **onBackpressureBuffer(maxSize, ...)**, xác định rõ **DROP_LATEST**, **DROP_OLDEST** hoặc **ERROR** và đo eviction.
- **Cần dọn các item operator đã loại**: **doOnDiscard** tại đúng vị trí và đúng kiểu, kiểm tra tài liệu Discard Support.
- **Cần chẩn đoán tín hiệu bất thường**: **Hooks.onNextDropped/Hooks.onErrorDropped** dưới quản lý tập trung, không dùng như bộ đếm drop bình thường.

Cuối cùng, phải xem **backpressure, bộ nhớ, độ trễ, tỷ lệ mất dữ liệu, lỗi và cancellation** là những chỉ số liên quan. Một pipeline không báo lỗi vẫn có thể đang mất item; một pipeline không làm rơi item có thể đang tích tụ bộ nhớ. Chỉ khi chính sách dữ liệu và quan sát được thiết kế cùng nhau mới có thể đánh giá hệ thống đang hoạt động đúng.

## 18. Tài liệu tham khảo

- Project Reactor **Flux API**, nhóm **onBackpressureBuffer / onBackpressureDrop / onBackpressureLatest / onBackpressureError**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor **BufferOverflowStrategy API**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BufferOverflowStrategy.html
- Project Reactor **Hooks API**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Hooks.html
- Reactor Reference Guide, **Operator Choice**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Reference Guide, **Using Global Hooks and doOnDiscard**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/hooks.html
- Reactive Streams Specification for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
