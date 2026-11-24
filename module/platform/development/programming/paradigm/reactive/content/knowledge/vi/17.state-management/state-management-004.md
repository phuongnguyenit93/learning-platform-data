# Thứ tự tín hiệu không thay thế an toàn truy cập giữa nhiều luồng

Reactive Streams yêu cầu các tín hiệu gửi đến cùng một subscriber phải được tuần tự hóa: hai callback của cùng subscription không được chồng lấn và tín hiệu sau phải có thứ tự quan sát phù hợp với tín hiệu trước. Quy tắc này giúp subscriber đọc được một chuỗi tín hiệu có trật tự. Tuy nhiên, nó không làm cho mọi dữ liệu mà ứng dụng chia sẻ giữa các thread trở nên an toàn.

Trong Reactor, một pipeline có thể chuyển việc thực thi qua nhiều scheduler, chạy nhiều publisher con đồng thời bằng flatMap, hoặc chia dữ liệu thành nhiều rail bằng parallel(). Mỗi subscriber vẫn phải nhận tín hiệu theo hợp đồng, nhưng các tác vụ bên trong những nhánh khác nhau, những subscription khác nhau hoặc các callback tự tạo có thể chạy đồng thời. Nếu chúng cùng đọc và ghi một đối tượng mutable, race condition vẫn có thể xảy ra.

Bài học này giải thích ranh giới giữa thứ tự tín hiệu và thread safety, cách nhận diện trạng thái dùng chung, và cách chọn dữ liệu bất biến, operator tuần tự, atomic variable hoặc cơ chế đồng bộ phù hợp.

## 1. Tuần tự hóa tín hiệu có ý nghĩa gì?

Một subscriber Reactive Streams nhận tín hiệu qua các callback onSubscribe, onNext, onError và onComplete. Theo hợp đồng, các lời gọi tín hiệu tới cùng subscriber phải được tuần tự hóa. Nói cách khác, một callback không được chạy chồng lên callback khác của cùng subscriber; quan hệ thứ tự giữa các tín hiệu phải được duy trì.

Trong định nghĩa của Reactive Streams, tín hiệu được xem là tuần tự khi các lời gọi không chồng lấn và có quan hệ happens-before. Vì vậy, nếu một subscriber cập nhật state chỉ được truy cập trong các callback tín hiệu của chính subscription đó, callback tiếp theo có thể quan sát các cập nhật trước. Bảo đảm này không tự mở rộng sang thread bên ngoài, subscription khác hoặc các inner task đang chạy đồng thời.

Ví dụ một subscription có thể quan sát:

    onSubscribe
       |
       v
    onNext(A)
       |
       v
    onNext(B)
       |
       v
    onComplete

Subscriber không phải xử lý đồng thời onNext(A) và onNext(B) của cùng subscription. Publisher có thể dùng nhiều thread nội bộ, nhưng phải bảo đảm các tín hiệu đi đến subscriber tuân thủ hợp đồng tuần tự.

Quy tắc này rất quan trọng cho logic nằm ngay trong callback của một subscriber. Nếu callback cập nhật một biến thuộc riêng subscription và không có tác vụ khác truy cập biến đó đồng thời, việc xử lý tuần tự giúp trạng thái tiến triển theo thứ tự tín hiệu.

Nhưng quy tắc chỉ nói về tín hiệu được gửi đến một subscriber. Nó không khẳng định rằng:

- Tất cả operator trong pipeline luôn chạy trên một thread duy nhất.
- Các inner publisher của flatMap thực thi tuần tự.
- Nhiều subscriber cùng đăng ký một publisher sẽ dùng chung một thread.
- Callback hoặc task do ứng dụng tự tạo sẽ được tuần tự hóa cùng tín hiệu.
- Một đối tượng mutable được chia sẻ ra ngoài pipeline sẽ tự động an toàn.

Đây là ranh giới cần giữ rõ khi thiết kế trạng thái trong ứng dụng reactive.

## 2. Thứ tự tín hiệu và thread safety là hai thuộc tính khác nhau

Thứ tự tín hiệu mô tả thứ tự và tính không chồng lấn của các callback mà một subscriber quan sát. Thread safety mô tả việc nhiều thread truy cập dữ liệu dùng chung mà không làm hỏng invariant hoặc tạo ra kết quả không nhất quán.

Một đoạn mã có thể nhận tín hiệu tuần tự nhưng vẫn không thread-safe nếu thread khác cùng sửa dữ liệu:

    List<String> sharedNames = new ArrayList<>();

    Flux<String> names = nameSource
        .doOnNext(sharedNames::add);

    names.subscribe();

    // Một thread khác cũng có thể sửa sharedNames tại đây.
    sharedNames.add("external");

Các callback của subscription có thể được tuần tự hóa, nhưng thread thực thi đoạn sharedNames.add("external") không thuộc hợp đồng tín hiệu của subscription. Hai thao tác có thể xảy ra đồng thời trên ArrayList, dẫn đến race condition hoặc trạng thái không mong muốn.

Ngay cả khi không có thread bên ngoài, nhiều subscription vào cùng publisher có thể chạy đồng thời:

    Flux<String> source = nameSource
        .doOnNext(sharedNames::add);

    source.subscribe();
    source.subscribe();

Hai subscription có vòng đời độc lập. Tín hiệu trong từng subscription được tuần tự hóa riêng, nhưng callback của subscriber thứ nhất có thể chạy đồng thời với callback của subscriber thứ hai. Cả hai cùng ghi vào một ArrayList nên cấu trúc này không an toàn.

| Phạm vi truy cập | Điều hợp đồng bảo đảm | Rủi ro còn lại |
|---|---|---|
| Callback của cùng subscriber | Tín hiệu được tuần tự hóa | Thread khác ngoài subscription vẫn có thể truy cập cùng state |
| Hai subscription khác nhau | Mỗi subscription có thứ tự tín hiệu riêng | Callback giữa hai subscription có thể chạy đồng thời |
| Hai inner publisher trong flatMap | Tín hiệu downstream được điều phối theo hợp đồng | Công việc và side effect trong các inner publisher có thể chạy đồng thời |
| Các rail của parallel() | Mỗi rail xử lý phần việc của nó | Nhiều rail có thể truy cập cùng đối tượng mutable |
| Task tự tạo bằng executor hoặc scheduler | Không tự động thuộc chuỗi tín hiệu | Phải quản lý đồng bộ và vòng đời riêng |

## 3. Backpressure không phải cơ chế khóa dữ liệu

Backpressure giới hạn số phần tử publisher được phép phát theo nhu cầu request(n) của subscriber. Nó giúp điều tiết tốc độ truyền dữ liệu và giới hạn lượng công việc được đưa xuống một ranh giới subscription.

Backpressure không khóa đối tượng, không bảo vệ cấu trúc dữ liệu và không làm thao tác read-modify-write trở thành nguyên tử.

Ví dụ, dù subscriber chỉ yêu cầu một phần tử mỗi lần, hai subscription vẫn có thể cùng tăng một bộ đếm dùng chung:

    AtomicInteger total = new AtomicInteger();

    Flux<Integer> counted =
        source.doOnNext(value -> total.incrementAndGet());

    counted.subscribe();
    counted.subscribe();

Ở đây AtomicInteger làm phép tăng an toàn giữa các thread. Điều đó đến từ semantics của atomic variable, không phải từ backpressure. Nếu thay nó bằng int hoặc ArrayList dùng chung, việc giới hạn demand không tự sửa được race condition.

Hãy chọn riêng hai cơ chế:

- Dùng backpressure để điều tiết số lượng và nhịp dữ liệu.
- Dùng dữ liệu bất biến, ownership rõ ràng, atomic hoặc synchronization để bảo vệ trạng thái dùng chung.

## 4. Scheduler có thể thay đổi thread thực thi

Reactor dùng Scheduler để điều khiển nơi và thời điểm thực thi. Một pipeline có thể bắt đầu trên thread gọi subscribe, chuyển sang scheduler khác bằng publishOn, hoặc chuyển quá trình subscribe vào nguồn bằng subscribeOn.

Ví dụ:

    Flux<Result> results =
        source
            .map(this::decode)
            .publishOn(Schedulers.parallel())
            .map(this::calculate);

Các toán tử trước publishOn xử lý theo thread thực thi upstream. Các toán tử sau publishOn xử lý tín hiệu downstream trên scheduler đã chọn. Với một subscription, Reactor vẫn bảo đảm tín hiệu downstream được tuần tự hóa, nhưng thread thực thi có thể khác thread phát nguồn.

subscribeOn có tác động khác:

    Mono<Document> document =
        Mono.fromCallable(() -> blockingClient.load(id))
            .subscribeOn(Schedulers.boundedElastic());

Nó điều khiển nơi subscription và nguồn bắt đầu thực thi. Nó không có nghĩa mọi operator ở mọi vị trí trong pipeline đều được chuyển sang một thread cố định.

Một scheduler có pool nhiều thread không đồng nghĩa một subscription được xử lý đồng thời tại cùng một callback. Nhưng các subscription khác nhau và các tác vụ độc lập có thể dùng những thread khác nhau. Vì vậy, không dùng tên scheduler để suy ra rằng một đối tượng chia sẻ đã an toàn.

## 5. flatMap có thể chạy nhiều công việc con đồng thời

flatMap chuyển mỗi phần tử nguồn thành một publisher con và cho phép các publisher con hoạt động đồng thời. Đây là cách hữu ích để tăng thông lượng khi gọi nhiều dịch vụ hoặc thực hiện I/O bất đồng bộ.

Ví dụ:

    AtomicInteger completed = new AtomicInteger();

    Flux<Result> results =
        requests.flatMap(request ->
            remoteService.execute(request)
                .doOnNext(result ->
                    completed.incrementAndGet()
                ),
            8
        );

Tham số 8 giới hạn số inner publisher được subscribe đồng thời. Các lời gọi remoteService.execute có thể hoàn tất trên những thread khác nhau. Mỗi nhánh có thể thực hiện callback doOnNext ở thread riêng.

Nếu thay AtomicInteger bằng một biến int dùng chung:

    int completed = 0;

    // Không an toàn nếu nhiều inner publisher cập nhật đồng thời.
    Flux<Result> results =
        requests.flatMap(request ->
            remoteService.execute(request)
                .doOnNext(result -> completed++)
        );

thì thao tác completed++ không nguyên tử. Nó gồm đọc giá trị, cộng một và ghi lại. Hai thread có thể cùng đọc một giá trị rồi ghi cùng kết quả, làm mất một lần tăng.

Giới hạn concurrency thấp hơn chỉ giảm số nhánh hoạt động đồng thời; nó không biến biến mutable thành thread-safe. Ngay cả concurrency bằng một cũng không bảo vệ state nếu một thread bên ngoài hoặc subscription khác cùng truy cập.

## 6. flatMap, flatMapSequential và concatMap

Các operator ghép publisher con có chính sách concurrency và thứ tự đầu ra khác nhau:

| Operator | Thực thi inner publisher | Thứ tự đầu ra | Side effect trong inner |
|---|---|---|---|
| flatMap | Có thể đồng thời | Theo thời điểm inner phát | Có thể chạy đồng thời |
| flatMapSequential | Có thể đồng thời | Giữ thứ tự theo phần tử nguồn | Vẫn có thể chạy đồng thời |
| concatMap | Tuần tự, chờ inner trước hoàn tất | Theo thứ tự nguồn | Không chồng lấn giữa các inner do operator này điều phối |

Nếu nghiệp vụ yêu cầu cập nhật một state tuần tự theo từng phần tử, concatMap thường là lựa chọn rõ ràng:

    Mono<Void> updateInOrder =
        events.concatMap(event ->
            stateRepository.apply(event)
        ).then();

flatMapSequential giữ thứ tự phát kết quả downstream, nhưng các inner publisher vẫn có thể thực thi đồng thời. Không dùng nó như một khóa bảo vệ state mutable mà các inner publisher cùng sửa.

concatMap cũng không bảo vệ state khỏi thread khác, subscription khác hoặc callback tự tạo. Nó chỉ tuần tự hóa việc xử lý inner publisher trong chuỗi mà operator quản lý.

## 7. parallel() tạo nhiều rail thực thi

Reactor có thể chia một Flux thành nhiều rail để xử lý song song:

    Flux<Integer> values =
        Flux.range(1, 100);

    Flux<Integer> processed =
        values
            .parallel(4)
            .runOn(Schedulers.parallel())
            .map(this::cpuIntensiveWork)
            .sequential();

Các phần tử được phân phối qua nhiều rail; mỗi rail có thể chạy trên một worker khác nhau. Khi operator map thực hiện side effect lên một đối tượng dùng chung, các rail có thể truy cập đối tượng đó đồng thời.

Ví dụ không an toàn:

    List<Integer> shared = new ArrayList<>();

    Flux.range(1, 100)
        .parallel(4)
        .runOn(Schedulers.parallel())
        .doOnNext(shared::add)
        .sequential()
        .then()
        .subscribe();

ArrayList không hỗ trợ nhiều thread thêm phần tử đồng thời. Việc gọi sequential() phía sau không thể làm cho các lần add đã xảy ra song song trở thành an toàn; operator này ghép các rail về một Flux ở phía sau nó.

Có thể tránh side effect dùng chung bằng cách giữ phép biến đổi thuần rồi thu thập kết quả sau khi đã ghép rail:

    Mono<List<Integer>> collected =
        Flux.range(1, 100)
            .parallel(4)
            .runOn(Schedulers.parallel())
            .map(this::cpuIntensiveWork)
            .sequential()
            .collectList();

Trong ví dụ này, các phép tính trên từng phần tử chạy song song, còn việc thu thập vào danh sách được thực hiện ở downstream sau khi các rail đã được ghép. Nếu cần giữ thứ tự đầu vào, hãy chọn operator và chiến lược ghép phù hợp; parallel() không mặc định bảo toàn thứ tự phát ban đầu.

## 8. Dùng dữ liệu bất biến và phép biến đổi thuần

Cách đơn giản nhất để giảm rủi ro chia sẻ state là không sửa đối tượng dùng chung. Thay vì cập nhật một object mutable, hãy tạo giá trị mới từ giá trị cũ:

    record AccountState(
        String accountId,
        long balanceCents,
        long version
    ) {}

    AccountState apply(
        AccountState current,
        long deltaCents
    ) {
        return new AccountState(
            current.accountId(),
            current.balanceCents() + deltaCents,
            current.version() + 1
        );
    }

Hàm apply nhận state và delta rồi trả về state mới. Nếu không có side effect và đầu vào không bị thay đổi, cùng một cặp đầu vào luôn tạo cùng kết quả. Ta có thể kiểm thử hàm độc lập và ghép nó vào pipeline.

Với event stream cần tính trạng thái tích lũy, scan biểu diễn phép chuyển state theo từng tín hiệu:

    Flux<AccountState> states =
        accountEvents.scan(
            initialState,
            (state, event) -> apply(state, event.deltaCents())
        );

Accumulator của scan được cập nhật theo thứ tự tín hiệu mà operator quan sát trong subscription. Nếu đặt scan sau một flatMap có inner publisher đồng thời, thứ tự state sẽ dựa trên thứ tự phần tử đi ra từ flatMap, không nhất thiết là thứ tự event ban đầu. Nếu nghiệp vụ yêu cầu thứ tự nguồn, cần giữ thứ tự trước khi cập nhật state, chẳng hạn dùng concatMap hoặc sắp xếp theo sequence có quy tắc rõ ràng.

## 9. State riêng cho mỗi subscription

Một publisher có thể được subscribe nhiều lần. Nếu mỗi subscriber cần bộ đếm, accumulator hoặc buffer riêng, hãy tạo state trong phạm vi subscription thay vì giữ nó ở biến dùng chung lúc assembly.

Ví dụ:

    Flux<Long> perSubscriberSequence =
        Flux.defer(() -> {
            AtomicLong sequence = new AtomicLong();
            return source.map(value ->
                sequence.incrementAndGet()
            );
        });

Mỗi lần subscribe, defer tạo một AtomicLong mới. Các subscription không dùng chung bộ đếm.

Nếu state chỉ được cập nhật theo tín hiệu tuần tự trong một subscription, có thể dùng state local trong defer và phép biến đổi thuần mà không cần atomic. Atomic chỉ cần thiết khi state đó thực sự được truy cập từ nhiều thread đồng thời.

Một cách khác là dùng Flux.generate khi mỗi subscription cần một bộ sinh state đồng bộ, hoặc scan khi state được suy ra từ chuỗi sự kiện. Chọn operator theo ngữ nghĩa của nguồn; đừng dùng một biến toàn cục chỉ để lưu state của một subscriber.

## 10. Khi nào cần Atomic, synchronized hoặc concurrent collection?

Nếu state thật sự được chia sẻ giữa nhiều thread hoặc nhiều subscription, hãy chọn công cụ theo invariant cần bảo vệ.

### 10.1. Atomic variable cho một giá trị độc lập

AtomicInteger, AtomicLong và các lớp atomic khác cung cấp thao tác nguyên tử cho một biến:

    AtomicLong processed = new AtomicLong();

    Flux<Result> results =
        source.doOnNext(result ->
            processed.incrementAndGet()
        );

Phép tăng được phối hợp an toàn giữa các thread. Atomic phù hợp với bộ đếm, sequence đơn giản hoặc cập nhật một tham chiếu bằng compare-and-set.

Atomic trên một field không tự bảo vệ invariant gồm nhiều field. Nếu cần cập nhật balance và version như một đơn vị nhất quán, hai atomic riêng biệt không bảo đảm cả cặp thay đổi cùng lúc.

### 10.2. synchronized hoặc Lock cho invariant nhiều thao tác

Khi nhiều thao tác phải được thực hiện như một đơn vị, dùng khóa:

    class SharedAccount {
        private long balanceCents;
        private long version;

        synchronized void apply(long deltaCents) {
            balanceCents += deltaCents;
            version++;
        }

        synchronized AccountState snapshot(String accountId) {
            return new AccountState(
                accountId,
                balanceCents,
                version
            );
        }
    }

Khóa bảo đảm cập nhật và đọc snapshot dùng cùng một vùng đồng bộ. Tuy nhiên, không giữ khóa trong lúc gọi I/O blocking hoặc chờ một publisher hoàn tất; điều đó có thể làm nghẽn thread và gây deadlock.

### 10.3. Concurrent collection cho cấu trúc dùng chung

Nếu nhiều thread cần thêm hoặc đọc phần tử, dùng cấu trúc phù hợp như ConcurrentHashMap, ConcurrentLinkedQueue hoặc một collection concurrent khác:

    Queue<Event> observed = new ConcurrentLinkedQueue<>();

    Flux<Event> events =
        source.doOnNext(observed::offer);

Concurrent collection bảo vệ thao tác cấu trúc của collection. Nếu giá trị bên trong map hoặc queue là object mutable, việc cập nhật object đó vẫn cần cơ chế an toàn riêng. Ví dụ, ConcurrentHashMap<String, AccountState> không tự làm cho một AccountState mutable trở nên thread-safe.

### 10.4. volatile chỉ bảo đảm visibility

volatile giúp thread đọc nhìn thấy giá trị mới nhất được ghi theo quy tắc Java Memory Model. Nó không biến phép count++ thành nguyên tử và không bảo vệ invariant nhiều field.

    private volatile boolean stopped;

    void stop() {
        stopped = true;
    }

Một cờ dừng đơn giản có thể dùng volatile. Nhưng nếu nhiều thread đồng thời tăng một counter, hãy dùng atomic hoặc khóa.

## 11. Tránh chia sẻ side effect giữa các subscriber

Các operator side effect như doOnNext, doOnError và doFinally hữu ích để quan sát pipeline. Nhưng callback của chúng vẫn chạy trong ngữ cảnh thread và subscription nơi tín hiệu đi qua.

Ví dụ:

    List<String> audit = new ArrayList<>();

    Flux<String> pipeline =
        source.doOnNext(audit::add);

Nếu pipeline được subscribe từ nhiều nơi, nhiều subscription có thể ghi vào audit đồng thời. Có thể thay collection bằng concurrent collection nếu audit chỉ là quan sát trong bộ nhớ:

    Queue<String> audit = new ConcurrentLinkedQueue<>();

Tuy nhiên, nếu audit là dữ liệu nghiệp vụ phải được lưu bền vững, nên ghép thao tác ghi vào pipeline:

    Flux<Event> persisted =
        source.concatMap(event ->
            auditRepository.save(event).thenReturn(event)
        );

concatMap tuần tự hóa các thao tác lưu trong subscription này. Nếu nhiều subscription cùng ghi vào kho dữ liệu, tính nhất quán vẫn cần được bảo vệ ở database bằng transaction, constraint hoặc khóa phù hợp.

Đừng gọi subscribe() bên trong doOnNext để khởi chạy một side effect khác. Điều đó tạo subscription tách rời, làm mất khả năng phối hợp lỗi, cancellation và backpressure với pipeline chính.

## 12. Chia sẻ publisher không có nghĩa chia sẻ state an toàn

Các operator như share() hoặc publish().refCount() cho phép nhiều subscriber dùng chung một subscription upstream. Chúng giúp tránh tạo nhiều lần kết nối nguồn, nhưng không tự bảo vệ mọi object mà downstream dùng chung.

Ví dụ:

    Flux<Event> sharedEvents =
        eventSource.events().share();

    sharedEvents
        .subscribe(this::updateDashboard);

    sharedEvents
        .subscribe(this::writeMetrics);

Mỗi subscriber có chuỗi callback riêng. Các subscriber khác nhau có thể được gọi trên thread khác nhau hoặc tại các thời điểm chồng lấn. Nếu cả hai cập nhật cùng một object mutable, object đó cần cơ chế bảo vệ riêng.

Ngoài ra, một subscriber chậm hoặc hủy không nhất thiết có cùng tác động lên subscriber khác; hành vi cụ thể phụ thuộc operator chia sẻ và chính sách backpressure. Đừng dùng share() như một cơ chế đồng bộ state.

## 13. Cancellation và race condition

Cancellation có thể xảy ra đồng thời với một callback hoặc thao tác đang chạy. Khi subscriber gọi cancel() hoặc Reactor gọi dispose(), yêu cầu hủy được truyền ngược qua pipeline, nhưng một thao tác đã bắt đầu có thể vẫn hoàn tất.

Ví dụ, một callback đang cập nhật trạng thái trong lúc một thread khác yêu cầu dừng component. Nếu cờ dừng được đọc và ghi từ nhiều thread, cần bảo đảm visibility bằng volatile, atomic hoặc khóa. Nếu callback còn ghi vào tài nguyên đã bị đóng, có thể tạo lỗi hoặc trạng thái không nhất quán.

Một mẫu đơn giản:

    class EventHandler {
        private final AtomicBoolean stopped =
            new AtomicBoolean();

        void handle(Event event) {
            if (stopped.get()) {
                return;
            }
            process(event);
        }

        void stop() {
            stopped.set(true);
        }
    }

AtomicBoolean bảo đảm việc đọc/ghi cờ an toàn giữa các thread. Nếu cần bảo đảm không có process nào bắt đầu sau khi stop hoàn tất, kiểm tra cờ đơn thuần có thể chưa đủ vì race có thể xảy ra giữa lần đọc và lúc bắt đầu xử lý. Khi đó cần khóa hoặc một giao thức lifecycle chặt chẽ hơn để phối hợp việc bắt đầu và dừng.

Không dựa vào cancellation để thay thế quản lý tài nguyên. Hãy dùng using hoặc usingWhen cho tài nguyên gắn với subscription và thiết kế shutdown riêng cho component sở hữu state dùng chung.

## 14. Kiểm thử hành vi đa luồng

Kiểm thử concurrency nên tập trung vào invariant có ý nghĩa, thay vì chỉ kiểm tra một thứ tự log có thể thay đổi giữa các lần chạy.

Ví dụ kiểm tra bộ đếm atomic sau nhiều nhánh:

    AtomicInteger count = new AtomicInteger();

    Mono<Integer> counted =
        Flux.range(1, 1_000)
            .parallel(4)
            .runOn(Schedulers.parallel())
            .doOnNext(value -> count.incrementAndGet())
            .sequential()
            .then(Mono.fromSupplier(count::get));

    StepVerifier.create(counted)
        .expectNext(1_000)
        .verifyComplete();

AtomicInteger bảo vệ phép tăng khi nhiều rail chạy đồng thời. sequential() ghép rail trước khi tạo Mono đọc kết quả. Trong kiểm thử thực tế, hãy tránh đọc state trước khi pipeline hoàn tất.

Nếu thay AtomicInteger bằng int[] hoặc một biến mutable không đồng bộ, test có thể đôi khi vẫn qua do lịch thực thi; điều đó không chứng minh mã an toàn. Race condition phụ thuộc thời điểm thread và có thể chỉ xuất hiện dưới tải hoặc trên máy khác.

Để kiểm thử state tuần tự, dùng concatMap và xác nhận thứ tự kết quả:

    StepVerifier.create(
            Flux.range(1, 3)
                .concatMap(value ->
                    Mono.just(value * 10)
                )
        )
        .expectNext(10, 20, 30)
        .verifyComplete();

Với logic nhiều thread phức tạp, bổ sung test lặp, stress test hoặc công cụ kiểm tra concurrency chuyên dụng. Tuy nhiên, trước hết hãy thiết kế state và ownership rõ ràng; test không thể biến một cấu trúc dữ liệu không an toàn thành an toàn.

## 15. Những nhầm lẫn thường gặp

**Cho rằng callback tuần tự đồng nghĩa toàn pipeline chỉ có một thread.** Scheduler, inner publisher và subscription khác có thể thực thi trên thread khác nhau.

**Cho rằng backpressure bảo vệ biến mutable.** Backpressure điều tiết số phần tử, không khóa hoặc đồng bộ bộ nhớ.

**Cho rằng flatMapSequential tuần tự hóa side effect.** Inner publisher vẫn có thể chạy đồng thời; operator chủ yếu giữ thứ tự phát kết quả.

**Cho rằng sequential() sửa race đã xảy ra trong parallel().** Nó ghép rail ở vị trí được đặt; side effect phía trước vẫn có thể đã chạy đồng thời.

**Dùng Atomic cho invariant nhiều field.** Atomic variable chỉ bảo vệ các thao tác được cung cấp trên biến đó. Dùng khóa hoặc một state immutable được thay thế nguyên tử khi cần cập nhật nhất quán nhiều giá trị.

**Dùng ConcurrentHashMap nhưng lưu value mutable.** Map bảo vệ cấu trúc map, không tự đồng bộ các thao tác trên object được lưu.

**Chia sẻ một accumulator giữa nhiều subscriber.** Mỗi subscription có thể chạy đồng thời với subscription khác. Tạo state trong defer hoặc dùng một state store có cơ chế đồng bộ rõ ràng.

**Giả định cancel làm callback đang chạy biến mất ngay.** Cancellation là yêu cầu dừng; tác vụ đã bắt đầu cần hợp tác và quản lý tài nguyên an toàn.

## 16. Checklist thiết kế state an toàn

Trước khi thêm state hoặc side effect vào pipeline, hãy xác định:

1. Đối tượng này thuộc một subscription, một rail, một component hay toàn ứng dụng?
2. Có bao nhiêu thread hoặc subscription có thể đọc/ghi nó cùng lúc?
3. Tín hiệu tuần tự của cùng subscriber có đủ bảo vệ state hay còn truy cập từ bên ngoài?
4. flatMap, parallel() hoặc nhiều subscription có tạo concurrency ở vị trí cập nhật không?
5. Có thể thay state mutable bằng dữ liệu bất biến và phép biến đổi thuần không?
6. Nếu state được chia sẻ, invariant cần atomic, khóa hay concurrent collection?
7. Operator tuần tự nào phù hợp: concatMap, scan hay một state store riêng?
8. Cancellation và shutdown có thể đua với callback đang chạy không?
9. Test có xác nhận invariant cuối cùng thay vì dựa vào thứ tự thread ngẫu nhiên không?

Thứ tự tín hiệu là một phần quan trọng của hợp đồng Reactive Streams, nhưng chỉ bảo đảm cách một subscriber quan sát tín hiệu trong subscription của nó. An toàn truy cập dữ liệu vẫn phụ thuộc vào phạm vi sở hữu state, số thread có thể truy cập và cơ chế đồng bộ được chọn. Khi kết hợp publisher tuần tự với state riêng, dữ liệu bất biến hoặc công cụ đồng bộ phù hợp, pipeline Reactor có thể tận dụng concurrency mà không làm sai lệch trạng thái nghiệp vụ.
