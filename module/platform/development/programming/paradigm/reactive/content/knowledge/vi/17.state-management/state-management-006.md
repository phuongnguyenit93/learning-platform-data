# Lựa chọn phạm vi đồng bộ hóa khi có tài nguyên dùng chung

Trong ứng dụng reactive, một pipeline có thể được đăng ký nhiều lần, nhiều subscriber có thể cùng quan sát một nguồn, và các nhánh xử lý có thể chạy đồng thời trên nhiều scheduler. Khi các nhánh đó cùng đọc hoặc cập nhật một tài nguyên như bộ đếm, cache, bản đồ trạng thái, connection hay listener, câu hỏi quan trọng là: trạng thái thuộc về một subscription, thuộc về toàn bộ pipeline hay được chia sẻ giữa nhiều thành phần?

Chọn đúng phạm vi đồng bộ hóa giúp tránh race condition, dữ liệu bị ghi đè và giải phóng tài nguyên quá sớm. Đồng bộ hóa quá rộng lại có thể tạo điểm nghẽn, giữ event loop trong lúc chờ khóa hoặc làm giảm khả năng xử lý đồng thời. Vì vậy, trước khi thêm `synchronized` hay một cấu trúc dữ liệu concurrent, hãy xác định ai sở hữu trạng thái và những luồng nào thực sự có thể truy cập nó cùng lúc.

Bài học thuộc chương **Trạng thái** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; nội dung này áp dụng các nguyên tắc đó khi dùng Mono, Flux, toán tử, scheduler, xử lý lỗi và quản lý tài nguyên trong ứng dụng Java.

Các ví dụ sử dụng Project Reactor. Những tên như eventSource, AccountState, repository hoặc logger đại diện cho thành phần của ứng dụng; hãy bổ sung import và kiểu miền tương ứng khi áp dụng vào dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt trạng thái riêng của từng subscription với trạng thái được chia sẻ giữa nhiều subscriber.
- Xác định những đoạn pipeline có thể chạy đồng thời và có khả năng truy cập cùng một tài nguyên.
- Chọn biến cục bộ, immutable state, atomic, concurrent collection, lock hoặc scheduler tuần tự hóa theo đúng phạm vi.
- Hiểu giới hạn của `concatMap`, `flatMap`, `publishOn` và `share` khi bảo vệ trạng thái dùng chung.
- Quản lý vòng đời tài nguyên chia sẻ mà không đóng tài nguyên khi subscriber khác vẫn đang sử dụng.
- Kiểm thử cập nhật đồng thời và xác nhận trạng thái không bị mất hoặc rò rỉ.

## 1. Bắt đầu từ quyền sở hữu trạng thái

Đồng bộ hóa chỉ cần thiết khi nhiều luồng thực thi có thể truy cập cùng một trạng thái mutable và ít nhất một bên có thể ghi. Nếu một trạng thái chỉ được tạo và sử dụng bên trong một subscription với tín hiệu tuần tự, thường không cần khóa toàn cục.

Có thể chia phạm vi sở hữu thành ba loại:

| Phạm vi | Ví dụ | Cách quản lý thường phù hợp |
|---|---|---|
| Theo subscription | Bộ đếm của một lần xử lý, accumulator trong một pipeline riêng | Tạo trạng thái mới khi subscribe; ưu tiên dữ liệu immutable |
| Theo instance/service trong một JVM | Cache dùng chung, metrics, trạng thái của nhiều request | Atomic, concurrent collection, lock hoặc một luồng sở hữu trạng thái |
| Ngoài tiến trình hoặc dùng chung giữa nhiều node | Bản ghi trong database, trạng thái đơn hàng giữa nhiều instance | Transaction, optimistic/pessimistic locking hoặc cơ chế phối hợp phân tán |

Một biến được khai báo là `final` chỉ có nghĩa tham chiếu không đổi; đối tượng mà nó trỏ đến vẫn có thể mutable. Ví dụ, `final Map<String, Long> counts` không tự làm Map an toàn khi nhiều thread cập nhật.

Cũng cần phân biệt **phạm vi dữ liệu** với **phạm vi tài nguyên**. Một cache có thể được chia sẻ toàn service, nhưng một connection đang được mượn từ pool thường nên thuộc về một thao tác hoặc transaction cụ thể. Chia sẻ một connection mutable cho nhiều subscription đồng thời có thể vi phạm giả định của driver và làm lẫn transaction.

## 2. Tín hiệu tuần tự không bảo vệ mọi trạng thái dùng chung

Reactive Streams yêu cầu các tín hiệu gửi đến cùng một Subscriber được tuần tự hóa: một subscription không nhận các callback `onNext`, `onError` hoặc `onComplete` chồng lấn nhau. Điều này giúp xử lý một luồng tín hiệu theo thứ tự, nhưng không có nghĩa toàn bộ ứng dụng chỉ chạy trên một thread.

Có nhiều tình huống tạo truy cập đồng thời:

- Hai request HTTP tạo hai subscription độc lập và cùng cập nhật một cache.
- `flatMap` đăng ký nhiều Publisher con, khiến các hàm tạo tác dụng phụ hoặc công việc bên trong chạy đồng thời.
- `parallel()` chia dữ liệu thành nhiều rail chạy trên nhiều worker.
- Một callback từ SDK gọi vào ứng dụng trên thread riêng, đồng thời pipeline đang đọc trạng thái.
- Nhiều subscriber cùng nhận dữ liệu từ một nguồn chia sẻ và cùng cập nhật một đối tượng mutable.

Ví dụ:

~~~java
AtomicInteger completed = new AtomicInteger();

Flux<Result> results =
    Flux.fromIterable(requests)
        .flatMap(request ->
            service.call(request)
                .doOnSuccess(value -> completed.incrementAndGet()),
            16
        );
~~~

Ở đây, tối đa 16 lời gọi con có thể hoạt động đồng thời. AtomicInteger phù hợp cho bộ đếm được cập nhật từ nhiều nhánh. Nếu thay nó bằng một biến `int` dùng chung rồi tăng trực tiếp, các lần đọc-sửa-ghi có thể đè lên nhau và kết quả cuối nhỏ hơn số thao tác thực tế.

Ngay cả khi downstream nhận tín hiệu đã được tuần tự hóa, các hàm bên trong những Publisher con vẫn có thể thực thi đồng thời. Hãy đặt bảo vệ ở đúng nơi trạng thái được truy cập, không suy ra thread-safety chỉ từ việc kết quả cuối đi qua một Subscriber.

## 3. Trạng thái riêng cho từng subscription

Nếu mỗi subscriber cần một accumulator độc lập, hãy tạo trạng thái tại thời điểm subscribe. Reactor cung cấp `defer` để tạo Publisher mới cho mỗi subscription:

~~~java
Flux<NumberedEvent> numberedEvents(Flux<Event> source) {
    return Flux.defer(() -> {
        AtomicLong sequence = new AtomicLong();

        return source.map(event ->
            new NumberedEvent(
                sequence.incrementAndGet(),
                event
            )
        );
    });
}
~~~

Mỗi lần subscribe, supplier của `defer` tạo một AtomicLong mới. Các subscription không dùng chung bộ đếm nên không cần khóa để bảo vệ bộ đếm giữa chúng. AtomicLong trong ví dụ cũng bảo vệ trường hợp hàm map được gọi từ một nguồn có thể phát đồng thời; với một nguồn tuân thủ tín hiệu tuần tự, một biến cục bộ đơn giản cũng có thể đủ.

Nếu trạng thái là phép tích lũy dữ liệu, hãy ưu tiên toán tử `scan`:

~~~java
Flux<AccountState> states =
    accountEvents
        .scan(AccountState.empty(), AccountState::apply)
        .skip(1);
~~~

Mỗi subscription có accumulator riêng của toán tử scan. Nếu `AccountState` là immutable, mỗi lần cập nhật tạo trạng thái mới và không có đối tượng cũ bị sửa tại chỗ. Cách này giúp nhiều subscriber độc lập xử lý cùng một nguồn mà không tranh chấp trên accumulator.

Tuy nhiên, nếu nguồn được chia sẻ, mỗi subscriber vẫn có thể có một accumulator riêng ở phía sau điểm chia sẻ. Điều đó có thể là điều mong muốn hoặc không, tùy nghiệp vụ. Hãy xác định trạng thái cần riêng theo người tiêu thụ hay cần một kết quả chung cho toàn pipeline.

## 4. Vị trí share quyết định trạng thái được tính một lần hay nhiều lần

`share()` cho phép nhiều subscriber dùng chung một subscription upstream trong khoảng thời gian có subscriber đang hoạt động. Vị trí đặt toán tử có ảnh hưởng đến việc một tác dụng phụ chạy một lần cho luồng chung hay một lần cho mỗi subscriber.

### Đếm một lần ở phía nguồn chung

~~~java
AtomicLong sourceCount = new AtomicLong();

Flux<Event> sharedEvents =
    eventSource()
        .doOnNext(event -> sourceCount.incrementAndGet())
        .share();
~~~

`doOnNext` nằm trước `share()`. Khi nhiều subscriber cùng tham gia một lượt chia sẻ, sự kiện đi qua upstream một lần và bộ đếm tăng một lần cho mỗi sự kiện nguồn.

### Đếm riêng cho từng subscriber

~~~java
AtomicLong downstreamCount = new AtomicLong();

Flux<Event> sharedEvents =
    eventSource()
        .share()
        .doOnNext(event -> downstreamCount.incrementAndGet());
~~~

Ở đây, `doOnNext` nằm sau `share()`. Mỗi subscriber nhận sự kiện sẽ thực hiện hook của riêng mình. Nếu có ba subscriber cùng nhận một sự kiện, bộ đếm có thể tăng ba lần.

Hai cách đặt đều hợp lệ nhưng đo hai khái niệm khác nhau: số sự kiện nguồn và tổng số lượt subscriber quan sát sự kiện. Đừng đặt hook hoặc cập nhật trạng thái dùng chung trước/sau `share()` mà không xác định rõ muốn đếm theo nguồn hay theo người tiêu thụ.

`share()` cũng không phải một khóa bảo vệ mọi truy cập đến đối tượng bên ngoài. Nó chia sẻ subscription upstream; nếu code khác hoặc subscription khác vẫn sửa cùng cache, cache vẫn cần cơ chế đồng bộ riêng.

## 5. Atomic và concurrent collection cho cập nhật dùng chung

Với trạng thái nhỏ và thao tác đơn giản, các lớp atomic thường phù hợp.

### AtomicInteger và AtomicLong

~~~java
AtomicLong total = new AtomicLong();

Flux<Void> writes =
    events.flatMap(event ->
        Mono.fromRunnable(() ->
            total.addAndGet(event.amount())
        )
    );
~~~

`addAndGet` thực hiện cập nhật nguyên tử. Nhiều nhánh có thể cộng đồng thời mà không làm mất phép cộng. Với một bộ đếm chỉ cần tăng/giảm, các thao tác `incrementAndGet`, `decrementAndGet` hoặc `getAndAdd` thường dễ hiểu.

### AtomicReference cho trạng thái nhiều trường

Khi một trạng thái gồm nhiều trường phải thay đổi nhất quán, có thể giữ một đối tượng immutable trong AtomicReference:

~~~java
AtomicReference<AccountState> state =
    new AtomicReference<>(AccountState.empty());

void apply(Event event) {
    state.updateAndGet(current ->
        current.apply(event)
    );
}
~~~

`updateAndGet` dùng cơ chế compare-and-set để cập nhật tham chiếu. Hàm cập nhật có thể được gọi lại khi có tranh chấp, vì vậy nó cần thuần (pure): không gửi email, không ghi database và không tăng metrics bên trong hàm. Hãy đặt tác dụng phụ sau khi đã xác định được kết quả cập nhật hoặc trong một pipeline riêng có chính sách rõ ràng.

Nếu invariant cần cập nhật nhiều đối tượng hoặc nhiều hệ thống cùng lúc, một AtomicReference không thay thế transaction. Ví dụ trừ tiền một tài khoản và cộng tiền tài khoản khác cần một cơ chế bảo đảm tính nguyên tử ở phạm vi nghiệp vụ tương ứng.

### ConcurrentHashMap và LongAdder

Với thống kê theo khóa:

~~~java
ConcurrentHashMap<String, LongAdder> counts =
    new ConcurrentHashMap<>();

void record(String category) {
    counts.computeIfAbsent(
        category,
        key -> new LongAdder()
    ).increment();
}
~~~

ConcurrentHashMap bảo vệ cấu trúc Map khi nhiều thread thêm hoặc tra cứu khóa. LongAdder phù hợp với bộ đếm có nhiều cập nhật đồng thời và thường giảm tranh chấp so với một biến atomic đơn khi tải ghi cao. Giá trị `sum()` là ảnh chụp tổng tại thời điểm đọc, không phải một phép đồng bộ transaction với các cập nhật đang diễn ra.

Nếu mỗi khóa cần cập nhật một trạng thái nhiều trường, có thể dùng `compute` để thay thế giá trị cho khóa đó:

~~~java
ConcurrentHashMap<String, AccountState> accounts =
    new ConcurrentHashMap<>();

void apply(String accountId, Event event) {
    accounts.compute(accountId, (key, current) -> {
        AccountState previous =
            current == null ? AccountState.empty() : current;

        return previous.apply(event);
    });
}
~~~

Hàm remapping trong `compute` được thực hiện nguyên tử đối với khóa tương ứng. Giữ hàm này ngắn và không gọi I/O, chờ khóa khác hoặc thực hiện tác dụng phụ lâu dài bên trong. Nếu cần thay đổi nhiều khóa như một giao dịch, phải dùng cơ chế khác.

## 6. Khi nào cần lock hoặc synchronized?

Atomic phù hợp với cập nhật đơn lẻ hoặc thay thế một tham chiếu. Concurrent collection phù hợp với thao tác trên cấu trúc dữ liệu được hỗ trợ. Nhưng đôi khi một invariant liên quan đến nhiều bước cần được bảo vệ như một đơn vị.

Ví dụ, một giới hạn dung lượng cần kiểm tra số chỗ còn trống rồi mới tăng số chỗ đã dùng. Nếu hai thread cùng kiểm tra trước khi một thread cập nhật, cả hai có thể cùng thấy còn chỗ và vượt giới hạn. Có thể dùng một vùng khóa nhỏ:

~~~java
private final Object capacityLock = new Object();
private int used;
private final int capacity = 100;

boolean tryAcquireSlot() {
    synchronized (capacityLock) {
        if (used >= capacity) {
            return false;
        }

        used++;
        return true;
    }
}

void releaseSlot() {
    synchronized (capacityLock) {
        if (used > 0) {
            used--;
        }
    }
}
~~~

Việc kiểm tra và tăng nằm trong cùng critical section, nên không có thread khác chen vào giữa hai thao tác. Trong ứng dụng thực, có thể dùng Semaphore nếu bài toán đúng là giới hạn số tác vụ đồng thời; ví dụ này nhằm minh họa invariant nhiều bước.

Một số nguyên tắc khi dùng lock trong pipeline reactive:

- Giữ vùng khóa càng ngắn càng tốt.
- Không gọi HTTP, database hoặc chờ Publisher bên trong khối synchronized.
- Không giữ khóa qua một ranh giới bất đồng bộ hoặc trong lúc chờ một Future.
- Tránh lấy nhiều khóa theo thứ tự không nhất quán để giảm nguy cơ deadlock.
- Không dùng lock JVM để bảo vệ trạng thái được nhiều tiến trình hoặc nhiều pod cùng truy cập.

Lời gọi chặn khi chờ lock có thể giữ thread của scheduler. Nếu contention cao trên event loop, các request khác dùng chung event loop có thể bị chậm. Hãy cân nhắc thay đổi mô hình sở hữu hoặc tuần tự hóa cập nhật thay vì thêm khóa lớn quanh toàn bộ pipeline.

## 7. Tuần tự hóa cập nhật bằng scheduler hoặc toán tử

Một cách tránh nhiều thread cùng sửa trạng thái là đưa mọi cập nhật qua một luồng thực thi tuần tự. Trong Reactor, có thể dùng scheduler single chuyên biệt:

~~~java
Scheduler stateScheduler =
    Schedulers.newSingle("account-state");

Flux<AccountState> states =
    accountEvents
        .publishOn(stateScheduler)
        .scan(AccountState.empty(), AccountState::apply);
~~~

Các tín hiệu phía sau `publishOn` được xử lý trên scheduler đó. Nếu mọi thao tác đọc/ghi trạng thái liên quan đều đi qua cùng scheduler, chúng có thể được thực hiện tuần tự trên một worker thay vì tranh chấp trên nhiều thread.

Scheduler đơn không tự bảo vệ trạng thái khỏi code bên ngoài. Nếu một thread khác cập nhật trực tiếp cùng đối tượng, hoặc một pipeline khác không dùng scheduler đó, race condition vẫn có thể xảy ra. Hãy quy định một điểm sở hữu duy nhất và đưa mọi lệnh cập nhật qua điểm đó.

Scheduler do ứng dụng tạo cần được giải phóng khi thành phần sở hữu dừng hoạt động:

~~~java
stateScheduler.dispose();
~~~

Chỉ dispose scheduler do thành phần của bạn tạo và sở hữu. Không tùy tiện dispose các scheduler dùng chung toàn cục như `Schedulers.parallel()` hoặc `Schedulers.single()`.

### concatMap và flatMap không có cùng mức tuần tự

~~~java
Flux<WriteResult> orderedWrites =
    events.concatMap(repository::save);

Flux<WriteResult> concurrentWrites =
    events.flatMap(repository::save, 8);
~~~

`concatMap` chỉ đăng ký Publisher con tiếp theo sau khi Publisher hiện tại hoàn tất, nên các thao tác save trong một subscription được thực hiện tuần tự theo thứ tự nguồn. `flatMap` cho phép tối đa tám Publisher con hoạt động đồng thời trong ví dụ và kết quả có thể xen kẽ.

Điều đó không có nghĩa `concatMap` tạo khóa toàn cục. Hai subscription độc lập cùng dùng `concatMap` vẫn có thể gọi repository đồng thời. Nếu cần tuần tự hóa giữa nhiều request, hãy đưa chúng qua một điểm điều phối chung hoặc dùng cơ chế bảo vệ tại tài nguyên sở hữu.

`flatMapSequential` có thể giữ thứ tự phát kết quả theo nguồn trong khi các Publisher con vẫn được thực thi đồng thời. Vì vậy, giữ thứ tự đầu ra không đồng nghĩa với việc tác dụng phụ bên trong đã được tuần tự hóa.

## 8. Nguồn phát đồng thời và Sinks

Khi nhiều callback phát vào cùng một sink, cần phân biệt việc sink hỗ trợ nhiều subscriber với việc sink chấp nhận nhiều producer đồng thời. Một sink có thể phát hiện các lần emit chồng lấn và trả về `FAIL_NON_SERIALIZED`.

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Sinks.EmitResult result = sink.tryEmitNext(event);

if (result == Sinks.EmitResult.FAIL_NON_SERIALIZED) {
    // Đưa sự kiện qua hàng đợi tuần tự hoặc áp dụng retry có giới hạn.
}
~~~

Nếu nhiều thread có thể gọi `tryEmitNext`, hãy chọn một chiến lược rõ ràng:

- Đưa lệnh phát vào một executor hoặc scheduler sở hữu duy nhất.
- Tuần tự hóa tại adapter callback trước khi gọi sink.
- Dùng EmitFailureHandler có retry cho tranh chấp phát nếu retry phù hợp với latency và chính sách dữ liệu.

Không nên bỏ qua `EmitResult`. Với sự kiện quan trọng, thất bại phát có thể đồng nghĩa dữ liệu không vào pipeline. Hãy quyết định liệu cần retry, ghi vào hàng đợi bền vững hay báo lỗi về producer. Không dùng biến thể sink unsafe trừ khi ứng dụng đã bảo đảm việc tuần tự hóa ở bên ngoài.

## 9. Tài nguyên dùng chung và vòng đời subscription

Một tài nguyên chia sẻ không nên được đóng chỉ vì một subscriber kết thúc. Ví dụ, nếu một listener được tạo ở cấp service và phục vụ nhiều subscriber, một subscriber hủy không được tự ý gọi dispose listener chung khi các subscriber khác vẫn cần nó.

Có hai mô hình sở hữu thường gặp:

### Tài nguyên riêng theo subscription

Dùng `using` hoặc `usingWhen` để cấp phát và giải phóng một tài nguyên cho mỗi subscription:

~~~java
Flux<String> records =
    Flux.using(
        this::openReader,
        reader -> Flux.fromStream(reader.lines()),
        BufferedReader::close
    );
~~~

Mỗi subscription nhận một Reader riêng. Khi subscription hoàn tất, lỗi hoặc bị hủy, cleanup đóng Reader tương ứng. Mô hình này dễ hiểu khi tài nguyên không được chia sẻ giữa các subscriber.

### Tài nguyên sống cùng service

Nếu một listener hoặc kết nối được chia sẻ, service sở hữu việc đăng ký và hủy đăng ký. Subscriber chỉ đăng ký nhận dữ liệu từ Publisher chia sẻ; việc một subscriber hủy chỉ kết thúc lượt tiêu thụ của subscriber đó.

Cần có quy tắc dừng tài nguyên khi service đóng hoặc khi không còn subscriber nếu đó là chính sách mong muốn. Có thể dùng ref-counting hoặc lifecycle của component, nhưng phải xử lý race giữa subscriber đến mới và subscriber cuối cùng rời đi. Đừng gắn cleanup của tài nguyên toàn service vào `doFinally` của một subscriber riêng lẻ.

Với connection pool, thường nên mượn connection theo thao tác hoặc transaction và trả lại khi thao tác đó kết thúc. Pool là thành phần quản lý tập connection dùng chung; một connection đang được mượn vẫn có một chủ sở hữu cụ thể. Tránh dùng cùng một connection mutable cho nhiều pipeline đồng thời nếu driver không hỗ trợ.

## 10. Trạng thái trong một JVM và trạng thái phân tán

`AtomicLong`, `ConcurrentHashMap`, `synchronized` và scheduler đơn chỉ phối hợp các thread trong cùng tiến trình JVM. Nếu ứng dụng chạy nhiều instance, mỗi instance có một bản sao riêng của các đối tượng đó.

Ví dụ, hai pod cùng dùng một AtomicLong để đếm số đơn sẽ có hai bộ đếm khác nhau. Không thể dùng atomic trong bộ nhớ để bảo đảm tổng số đơn trên toàn cụm hoặc giới hạn tồn kho chung.

Với trạng thái cần nhất quán giữa nhiều node, hãy đặt cơ chế đồng bộ ở nơi có quyền sở hữu chung:

- Dùng transaction database để cập nhật nhiều bản ghi cần tính nguyên tử.
- Dùng optimistic locking với version để phát hiện cập nhật xung đột.
- Dùng điều kiện cập nhật nguyên tử ở database, ví dụ chỉ trừ tồn kho khi số lượng còn đủ.
- Dùng distributed lock khi thật sự cần một chủ sở hữu độc quyền và đã có chính sách timeout, lease, fencing token.
- Dùng message partition theo khóa để các sự kiện cùng một thực thể được xử lý tuần tự bởi một consumer tại một thời điểm.

Không nên dùng distributed lock như giải pháp mặc định cho mọi cập nhật. Một câu lệnh cập nhật có điều kiện hoặc transaction thường đơn giản và đáng tin cậy hơn nếu nó đáp ứng invariant nghiệp vụ.

## 11. Cách chọn phạm vi đồng bộ hóa

Có thể dùng bảng sau để đưa ra lựa chọn ban đầu:

| Tình huống | Phạm vi sở hữu | Cơ chế gợi ý |
|---|---|---|
| Mỗi request có accumulator riêng | Subscription | `defer`, `scan`, immutable state |
| Một counter được cập nhật từ nhiều nhánh | Service/JVM | `AtomicLong` hoặc `LongAdder` |
| Cache theo khóa với cập nhật độc lập từng khóa | Service/JVM | `ConcurrentHashMap`, `compute` |
| Nhiều trường phải đổi cùng nhau trong một invariant | Service/JVM | Immutable aggregate trong `AtomicReference` hoặc lock ngắn |
| Mọi lệnh cập nhật phải đi theo một thứ tự | Một điểm sở hữu | Scheduler đơn hoặc queue/actor |
| Nhiều Publisher con cần ghi tuần tự trong một subscription | Subscription | `concatMap` |
| Một listener phục vụ nhiều subscriber | Service | Service sở hữu listener; subscriber chỉ hủy lượt đăng ký riêng |
| Tồn kho hoặc số dư dùng chung nhiều pod | Toàn hệ thống | Transaction hoặc cập nhật nguyên tử ở database |
| Nhiều callback phát vào cùng sink | Ranh giới producer | Tuần tự hóa emit và kiểm tra `EmitResult` |

Bảng là gợi ý, không phải quy tắc thay thế phân tích. Một cache trong JVM có thể chỉ là bản sao của dữ liệu chuẩn ở database; khi đó cần xác định độ trễ đồng bộ và chính sách khi hai node cập nhật cùng lúc.

## 12. Kiểm thử trạng thái riêng và cập nhật đồng thời

Kiểm thử nên xác nhận cả kết quả dữ liệu lẫn phạm vi sở hữu mà thiết kế mong muốn.

### Mỗi subscription có accumulator riêng

~~~java
Flux<Integer> numbered =
    Flux.defer(() -> {
        AtomicInteger sequence = new AtomicInteger();
        return Flux.range(1, 3)
            .map(value -> sequence.incrementAndGet());
    });

StepVerifier.create(numbered)
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(numbered)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

Hai subscription đều bắt đầu lại từ một vì `defer` tạo bộ đếm mới cho mỗi lượt đăng ký.

### Cập nhật an toàn khi flatMap chạy đồng thời

~~~java
AtomicInteger processed = new AtomicInteger();

Mono<Void> work =
    Flux.range(1, 1_000)
        .flatMap(value ->
            Mono.fromRunnable(processed::incrementAndGet)
                .subscribeOn(Schedulers.parallel()),
            16
        )
        .then();

StepVerifier.create(work)
    .verifyComplete();

assertEquals(1_000, processed.get());
~~~

Nhiều tác vụ có thể chạy trên parallel scheduler, nhưng AtomicInteger bảo đảm mỗi lần tăng được ghi nhận. Kiểm thử này minh họa một counter chia sẻ an toàn trong cùng JVM. Với logic nghiệp vụ phức tạp hơn, cần kiểm thử invariant chứ không chỉ tổng số lần gọi.

### Kiểm thử một invariant với ConcurrentHashMap

~~~java
ConcurrentHashMap<String, AtomicInteger> inventory =
    new ConcurrentHashMap<>();

Mono<Void> updates =
    Flux.range(1, 500)
        .flatMap(value ->
            Mono.fromRunnable(() ->
                inventory.computeIfAbsent(
                    "SKU-1",
                    key -> new AtomicInteger()
                ).incrementAndGet()
            ).subscribeOn(Schedulers.parallel()),
            12
        )
        .then();

StepVerifier.create(updates)
    .verifyComplete();

assertEquals(500, inventory.get("SKU-1").get());
~~~

StepVerifier xác nhận mọi tác vụ đã hoàn tất trước khi kiểm tra tổng. ConcurrentHashMap bảo vệ thao tác lấy hoặc tạo counter cho khóa, AtomicInteger bảo vệ cập nhật giá trị. Nếu cần kiểm tra giới hạn tồn kho thay vì đếm số lần xử lý, hãy kiểm thử thao tác kiểm tra-và-cập nhật như một đơn vị nguyên tử.

Khi test code có scheduler hoặc callback ngoài, tránh dùng `Thread.sleep`. Dùng StepVerifier, TestPublisher, scheduler ảo hoặc latch có timeout rõ ràng để đồng bộ kiểm thử.

## 13. Những lỗi thiết kế thường gặp

**Dùng biến mutable dùng chung mà không có bảo vệ.** Hai subscription hoặc nhiều Publisher con có thể ghi đè cập nhật. Xác định scope trước, sau đó dùng immutable state, atomic hoặc cơ chế tuần tự hóa.

**Cho rằng một Subscriber nhận tín hiệu tuần tự nghĩa là mọi callback trong pipeline đều chạy tuần tự.** `flatMap`, `parallel` và callback ngoài có thể thực thi đồng thời. Bảo vệ state tại điểm truy cập thực tế.

**Dùng concatMap như khóa toàn cục.** concatMap tuần tự hóa Publisher con trong một subscription. Hai subscription vẫn có thể hoạt động cùng lúc.

**Đặt share ở sai phía của tác dụng phụ.** Hook trước share chạy theo sự kiện nguồn chung; hook sau share có thể chạy theo từng subscriber. Chọn vị trí theo ý nghĩa metrics hoặc cập nhật mong muốn.

**Giữ synchronized trong lúc gọi I/O.** Việc chờ trong critical section có thể chặn thread và tạo điểm nghẽn. Tách phần quyết định trạng thái khỏi phần I/O.

**Chia sẻ connection hoặc reader mutable cho nhiều subscriber.** Tài nguyên thường có vòng đời và quy tắc truy cập riêng. Mượn theo thao tác hoặc quản lý ở service sở hữu với hợp đồng rõ ràng.

**Dùng atomic trong bộ nhớ để bảo vệ dữ liệu nhiều node.** Atomic và lock JVM không phối hợp các tiến trình khác. Dùng transaction hoặc cơ chế đồng bộ ở tầng dữ liệu chung.

**Không kiểm tra EmitResult của sink.** Một lần phát thất bại có thể làm mất sự kiện. Hãy xác định cách retry, buffer hoặc từ chối.

## 14. Quy trình quyết định trước khi thêm đồng bộ hóa

Trước khi dùng lock, atomic hoặc scheduler đơn, hãy trả lời các câu hỏi sau:

1. **Ai sở hữu trạng thái?** Một subscription, một service, một JVM hay toàn hệ thống?
2. **Có bao nhiêu người ghi?** Một nhánh tuần tự, nhiều inner Publisher, nhiều subscriber hay callback ngoài?
3. **Có invariant nào phải giữ?** Một bộ đếm độc lập hay nhiều trường phải đổi cùng nhau?
4. **Có thể tránh mutable state không?** Dùng scan, map và immutable object để giảm nhu cầu khóa.
5. **Có thể đưa cập nhật về một điểm sở hữu không?** Một scheduler hoặc queue tuần tự có thể đơn giản hóa đồng bộ hóa.
6. **Tác dụng phụ có chặn không?** Không giữ lock hoặc event loop trong lúc chờ I/O.
7. **Tài nguyên sống bao lâu?** Theo subscription hay theo service; ai chịu trách nhiệm cleanup?
8. **Có nhiều node không?** Nếu có, cơ chế đồng bộ trong JVM không đủ.
9. **Đã kiểm thử tranh chấp chưa?** Xác nhận số lần cập nhật, invariant, cancellation và cleanup dưới tải đồng thời.

Chỉ thêm cơ chế đồng bộ sau khi xác định phạm vi và invariant. Khóa toàn pipeline thường làm giảm khả năng xử lý mà vẫn có thể bỏ sót đường truy cập từ code bên ngoài.

## 15. Bài tập vận dụng

Một dịch vụ quản lý hạn mức tài khoản nhận nhiều yêu cầu đồng thời. Mỗi yêu cầu kiểm tra hạn mức còn lại rồi trừ số tiền tương ứng. Nhiều subscription có thể cùng cập nhật một tài khoản; ứng dụng chạy trên ba instance.

Hãy thiết kế cách quản lý trạng thái và trả lời:

1. Vì sao một biến `AtomicLong` trong mỗi instance không thể bảo vệ hạn mức chung của tài khoản?
2. Nếu chỉ xử lý trong một subscription, `scan` với immutable state có thể giúp gì?
3. Nếu nhiều request trong cùng JVM cùng cập nhật một cache, nên dùng AtomicReference, ConcurrentHashMap hay lock? Invariant nào quyết định lựa chọn?
4. Vì sao `concatMap` trong mỗi request không bảo đảm hai request khác nhau được xử lý tuần tự?
5. Cơ chế transaction hoặc cập nhật có điều kiện ở database cần bảo đảm điều gì để không cho phép tổng tiền vượt hạn mức?
6. Nếu service phát sự kiện hạn mức qua Sinks.Many, ai sở hữu sink và xử lý ra sao khi nhiều callback emit đồng thời?
7. Khi client hủy request sau khi transaction đã commit, trạng thái nghiệp vụ cần được xử lý thế nào để không nhầm cancellation với rollback?

Hãy viết kiểm thử cho hai cập nhật đồng thời trên cùng tài khoản, xác nhận tổng số tiền sau cập nhật không vượt hạn mức. Bổ sung một kiểm thử cho nhiều subscription có accumulator riêng và một kiểm thử xác nhận việc hủy subscriber không đóng tài nguyên service vẫn đang chia sẻ.

## Kết luận

Phạm vi đồng bộ hóa phải theo đúng phạm vi sở hữu của trạng thái. Dữ liệu riêng theo subscription thường có thể dùng accumulator độc lập và immutable state; trạng thái chia sẻ trong một JVM cần atomic, concurrent collection, lock ngắn hoặc một điểm cập nhật tuần tự; trạng thái giữa nhiều node cần transaction hay cơ chế phối hợp ở tầng dữ liệu chung. Các toán tử reactive giúp điều phối luồng công việc nhưng không tự biến mọi đối tượng mutable thành thread-safe. Khi xác định rõ subscriber, producer, scheduler và chủ sở hữu tài nguyên, bạn có thể bảo vệ invariant mà vẫn giữ được khả năng xử lý đồng thời của pipeline.
