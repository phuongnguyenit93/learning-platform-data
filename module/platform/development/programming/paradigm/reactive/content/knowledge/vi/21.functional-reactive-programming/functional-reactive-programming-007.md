# Phụ thuộc động, chuyển nguồn và vòng phản hồi

Trong một hệ thống reactive, dữ liệu mới có thể làm thay đổi nguồn mà pipeline cần theo dõi. Người dùng đổi từ tài khoản này sang tài khoản khác, bộ lọc tìm kiếm thay đổi theo từng ký tự, hoặc trạng thái hiện tại quyết định bước xử lý tiếp theo. Khi đó, pipeline cần chuyển sang Publisher mới và ngừng quan sát nguồn cũ. Ở chiều ngược lại, một số hệ thống cần tạo sự kiện mới từ trạng thái vừa tính để tiếp tục xử lý. Đây là dạng vòng phản hồi (feedback loop).

Bài học thuộc chương **Phản ứng hàm** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là mô hình hóa phụ thuộc thay đổi theo dữ liệu, chuyển nguồn bằng `switchMap` và xây dựng vòng phản hồi có giới hạn, có điểm dừng và có kiểm soát tài nguyên.

Sau bài học, bạn có thể:

- Biểu diễn một phụ thuộc động bằng luồng lựa chọn và Publisher con.
- Chọn `switchMap`, `flatMap` hoặc `concatMap` theo chính sách xử lý nguồn cũ.
- Phân biệt chuyển nguồn với fallback khi nguồn empty hoặc lỗi.
- Giải thích cancellation khi một Publisher mới thay thế Publisher đang hoạt động.
- Thiết kế feedback loop từ sự kiện, state và effect mà không tạo vòng lặp vô hạn ngoài ý muốn.
- Dùng `scan`, `Sinks.Many` và scheduler để xây dựng một vòng phản hồi minh họa.
- Kiểm thử việc chuyển nguồn, loại bỏ kết quả cũ, điều kiện dừng và cancellation.

## 1. Phụ thuộc động là gì?

Một pipeline tĩnh có thể được mô tả bằng chuỗi operator cố định: đọc nguồn, biến đổi, lọc và phát kết quả. Nhưng nhiều ứng dụng có một giá trị điều khiển thay đổi trong lúc chạy. Giá trị đó quyết định Publisher nào đang là nguồn dữ liệu cần quan sát.

Ví dụ:

- Người dùng nhập từ khóa mới; kết quả tìm kiếm cần chuyển sang request tương ứng với từ khóa mới nhất.
- Người dùng chọn một tài khoản; dashboard cần ngừng nghe tài khoản cũ và nghe tài khoản mới.
- Thiết bị thay đổi chế độ hoạt động; pipeline cần chuyển sang nguồn telemetry của chế độ hiện tại.
- Một luồng trạng thái chọn endpoint; các request tiếp theo phải đi qua endpoint đang được chọn.

Trong một số thư viện FRP, hệ thống có thể theo dõi đồ thị phụ thuộc và tự cập nhật các node liên quan. Reactor là thư viện reactive streams, vì vậy ta biểu diễn sự thay đổi đó tường minh bằng một Publisher phát các lựa chọn và một toán tử chuyển sang Publisher con tương ứng. Đây là mô hình phụ thuộc động ở cấp pipeline.

```text
luồng lựa chọn:   A -------- B -------- C -------->
                  |          |          |
                  v          v          v
Publisher con:  source-A   source-B   source-C
                  |          |          |
                  +----X     +----X     +---------->
                       hủy        hủy       nguồn hiện tại
```

Khi lựa chọn mới xuất hiện, pipeline có thể hủy subscription tới nguồn con cũ và chuyển sang nguồn con mới. `switchMap` là toán tử thường dùng cho chính sách này.

## 2. `switchMap`: chỉ giữ Publisher con mới nhất

`switchMap` nhận mỗi phần tử từ nguồn điều khiển, tạo một Publisher con rồi chuyển tiếp tín hiệu từ Publisher con đang hoạt động mới nhất. Khi phần tử điều khiển tiếp theo đến, subscription tới Publisher con trước đó bị hủy và pipeline chuyển sang Publisher con mới.

Ví dụ tìm kiếm theo từ khóa:

```java
Flux<String> queries = queryInput
    .map(String::trim)
    .filter(query -> !query.isEmpty())
    .distinctUntilChanged();

Flux<SearchResult> results = queries
    .switchMap(query -> searchClient.search(query));
```

Giả sử người dùng nhập `rea`, sau đó `reac`, rồi `react`. Pipeline bắt đầu request cho `rea`. Khi `reac` đến, request `rea` bị cancel và request `reac` được subscribe. Khi `react` đến, request `reac` bị cancel và request `react` trở thành nguồn hiện tại.

Đây là lựa chọn phù hợp khi kết quả cũ không còn giá trị sau khi lựa chọn mới xuất hiện, ví dụ tìm kiếm trực tiếp, xem chi tiết theo mục đang chọn hoặc theo dõi thiết bị hiện tại.

### Cancellation không đảm bảo tác dụng bên ngoài bị đảo ngược

`switchMap` hủy subscription tới Publisher con cũ. Nếu Publisher con tôn trọng cancellation, nó có thể dừng việc đọc dữ liệu hoặc hủy request đang chờ. Tuy nhiên, cancellation không thể bảo đảm một side effect đã được hệ thống bên ngoài chấp nhận sẽ bị hoàn tác.

Ví dụ, một HTTP request ghi dữ liệu có thể đã tới server trước khi subscription bị hủy. `switchMap` không biến thao tác ghi đó thành rollback. Vì vậy:

- Dùng `switchMap` cho tác vụ đọc hoặc tính toán mà kết quả cũ có thể bỏ.
- Với lệnh ghi, thanh toán hoặc thao tác không thể đảo ngược, cân nhắc `concatMap`, idempotency key hoặc một giao thức xác nhận riêng.
- Nếu Publisher con không hỗ trợ cancellation tốt, hãy kiểm tra thêm sequence/version để bỏ kết quả cũ khi nó hoàn tất muộn.

## 3. Chọn giữa `switchMap`, `flatMap` và `concatMap`

Ba toán tử đều ánh xạ phần tử thành Publisher con, nhưng chính sách đối với các Publisher con đang hoạt động khác nhau.

| Toán tử | Khi nguồn điều khiển phát lựa chọn mới | Thứ tự kết quả | Trường hợp phù hợp |
|---|---|---|---|
| `switchMap` | Hủy Publisher con cũ, chuyển sang Publisher con mới nhất | Chỉ phát từ inner hiện tại; kết quả cũ bị bỏ sau khi chuyển | Tìm kiếm, lựa chọn hiện tại, dữ liệu đọc có thể thay thế. |
| `flatMap` | Giữ các inner đang hoạt động và subscribe inner mới | Có thể xen kẽ theo thời điểm hoàn tất | Mọi request đều có giá trị và có thể chạy đồng thời. |
| `concatMap` | Đưa lựa chọn mới vào hàng đợi, đợi inner trước hoàn tất | Giữ thứ tự nguồn | Lệnh ghi hoặc tác vụ cần xử lý tuần tự. |

Ví dụ cùng một nguồn điều khiển:

```java
// Chỉ kết quả của lựa chọn mới nhất còn được quan sát.
Flux<Result> latest = selections
    .switchMap(this::loadResult);

// Tất cả lựa chọn được xử lý; các inner có thể chạy đồng thời.
Flux<Result> concurrent = selections
    .flatMap(this::loadResult, 8);

// Tất cả lựa chọn được xử lý tuần tự theo thứ tự nhận.
Flux<Result> sequential = selections
    .concatMap(this::loadResult);
```

Đừng chọn `switchMap` chỉ vì muốn pipeline “nhanh hơn”. Nó thay đổi semantics bằng cách bỏ việc quan sát kết quả của các inner cũ. Nếu mọi lựa chọn đều là lệnh nghiệp vụ cần thực hiện, việc chuyển nguồn mới nhất có thể làm mất công việc.

### Giảm số lần chuyển nguồn

Nguồn điều khiển có thể phát nhiều giá trị giống nhau hoặc phát quá nhanh. Có thể giảm các lần tạo Publisher con bằng các operator đặt trước `switchMap`:

```java
Flux<SearchResult> results = queryInput
    .map(String::trim)
    .filter(query -> query.length() >= 2)
    .distinctUntilChanged()
    .debounce(Duration.ofMillis(250))
    .switchMap(searchClient::search);
```

`distinctUntilChanged` bỏ lựa chọn trùng liên tiếp. `debounce` chỉ phát giá trị sau khi không có giá trị mới trong khoảng thời gian quy định, phù hợp với ô tìm kiếm để tránh request cho từng phím. `debounce` thay đổi thời điểm lựa chọn được phát; không dùng nó nếu mọi sự kiện điều khiển đều phải được xử lý.

## 4. Chuyển một luồng Publisher con bằng `switchOnNext`

Đôi khi nguồn điều khiển đã phát ra Publisher thay vì chỉ phát một khóa để mapper tạo Publisher. Có thể dùng `Flux.switchOnNext` để chuyển sang Publisher con mới nhất:

```java
Flux<Publisher<Reading>> selectedSources = deviceSelections
    .map(device -> telemetryClient.readings(device.id()));

Flux<Reading> activeReadings = Flux.switchOnNext(selectedSources);
```

Khi `selectedSources` phát Publisher mới, `switchOnNext` chuyển sang Publisher đó và hủy subscription inner trước. Mô hình này hữu ích khi một bước upstream đã chịu trách nhiệm chọn và tạo nguồn con.

Nếu chỉ có một giá trị lựa chọn và cần ánh xạ nó thành Publisher, `switchMap` thường dễ đọc hơn. `switchOnNext` phù hợp khi chính luồng điều khiển đã chứa các Publisher con.

## 5. Chuyển nguồn khác với fallback

Chuyển nguồn theo lựa chọn mới và fallback khi nguồn thất bại là hai chính sách khác nhau.

| Tình huống | Toán tử | Điều kiện kích hoạt |
|---|---|---|
| Lựa chọn điều khiển mới xuất hiện | `switchMap` | Có phần tử mới từ nguồn điều khiển. |
| Nguồn hiện tại hoàn tất empty | `switchIfEmpty` | Nguồn hoàn tất mà không phát phần tử. |
| Nguồn hiện tại báo lỗi | `onErrorResume` | Nhận tín hiệu `onError`. |
| Nguồn hiện tại không phát tín hiệu | `timeout` | Không có tín hiệu trong thời hạn. |

Ví dụ, mỗi tài khoản được chọn có thể dùng cache nếu nguồn chính empty, nhưng khi tài khoản khác được chọn thì toàn bộ nhánh cũ vẫn phải bị thay thế:

```java
Flux<AccountView> views = selectedAccountIds
    .distinctUntilChanged()
    .switchMap(accountId ->
        accountClient.load(accountId)
            .switchIfEmpty(accountCache.load(accountId))
            .onErrorResume(TemporaryAccountServiceException.class,
                error -> accountCache.load(accountId))
    );
```

Trong mỗi inner Publisher:

- `switchIfEmpty` xử lý trường hợp nguồn chính hoàn tất không có dữ liệu.
- `onErrorResume` xử lý lỗi tạm thời được chỉ định.
- `switchMap` ở ngoài thay toàn bộ nhánh tài khoản cũ khi ID mới xuất hiện.

Nếu nguồn cache cũng lỗi, lỗi đó vẫn truyền xuống trừ khi có chính sách phục hồi khác. Không nên biến mọi lỗi thành empty vì điều đó có thể che giấu sự cố vận hành.

## 6. Lỗi của inner Publisher và phạm vi phục hồi

Một inner Publisher lỗi có thể làm toàn bộ chuỗi `switchMap` kết thúc bằng lỗi. Nếu chỉ muốn bỏ qua hoặc phục hồi lỗi của lựa chọn hiện tại rồi tiếp tục nhận lựa chọn mới, đặt xử lý lỗi bên trong mapper:

```java
Flux<SearchResult> results = queries
    .switchMap(query -> searchClient.search(query)
        .onErrorResume(SearchUnavailableException.class, error -> {
            log.warn("Search tạm thời không khả dụng cho query={}", query, error);
            return Flux.empty();
        })
    );
```

Lỗi phù hợp được xử lý trong inner Publisher; nguồn `queries` bên ngoài vẫn tiếp tục nhận lựa chọn mới. Nếu đặt `onErrorResume` bên ngoài `switchMap`, lỗi inner có thể kết thúc toàn bộ chuỗi trước khi fallback bên ngoài chạy. Khi đó, nguồn điều khiển gốc có thể đã bị hủy và không còn lựa chọn mới nào được xử lý.

Hãy xác định phạm vi lỗi cần phục hồi:

- Lỗi của một lần tải dữ liệu: xử lý bên trong mapper nếu các lựa chọn tiếp theo vẫn có ý nghĩa.
- Lỗi của chính nguồn điều khiển: xử lý ở ngoài `switchMap`.
- Lỗi nghiêm trọng hoặc lỗi lập trình: thường nên truyền tiếp thay vì âm thầm chuyển thành empty.

## 7. Vòng phản hồi là gì?

Một feedback loop hình thành khi trạng thái được tính từ sự kiện, rồi một effect dựa trên trạng thái đó phát ra sự kiện mới quay lại đầu vào. Mô hình này xuất hiện trong bộ điều khiển, hệ thống điều chỉnh tải, quy trình nhiều bước hoặc ứng dụng cần tự tạo lệnh tiếp theo sau khi cập nhật state.

```text
       Command / Event
              |
              v
        State reducer
              |
              v
         New State
              |
              v
       Effect / Decision
              |
              +--------> Command mới
                            |
                            +------> đầu vào
```

Trong mô hình hàm, reducer nên là phép biến đổi thuần: nhận state cũ và event mới, trả về state mới. Side effect được tách ra khỏi reducer. Effect có thể phát command mới, nhưng cần có điều kiện dừng, giới hạn tốc độ và chính sách lỗi rõ ràng.

Một vòng phản hồi không có điều kiện dừng có thể tạo luồng sự kiện vô hạn. Nếu mỗi state đều phát lại một command khiến state tiếp tục thay đổi, pipeline có thể tiêu thụ CPU, tăng queue và giữ tài nguyên liên tục.

## 8. Tạo state từ sự kiện bằng `scan`

`scan` là cách tự nhiên để biểu diễn state được cập nhật theo từng event:

```java
record CounterState(int value) {
    static CounterState initial() {
        return new CounterState(0);
    }
}

sealed interface CounterCommand permits Increment, Decrement {}
record Increment(int amount) implements CounterCommand {}
record Decrement(int amount) implements CounterCommand {}

CounterState reduce(CounterState state, CounterCommand command) {
    return switch (command) {
        case Increment increment ->
            new CounterState(state.value() + increment.amount());
        case Decrement decrement ->
            new CounterState(state.value() - decrement.amount());
    };
}

Flux<CounterState> states = commands
    .scan(CounterState.initial(), this::reduce)
    .distinctUntilChanged();
```

Reducer không ghi database, không gọi HTTP và không phát command mới. Nó chỉ tính state tiếp theo. Cách tách này giúp kiểm thử reducer bằng unit test thuần và kiểm soát side effect ở một ranh giới riêng.

Với Java phiên bản chưa hỗ trợ sealed interface hoặc pattern matching cho switch, có thể dùng interface/class thông thường và `instanceof`. Ý tưởng kiến trúc không phụ thuộc cú pháp Java cụ thể.

## 9. Vòng phản hồi có kiểm soát bằng Sinks

Reactor `Sinks.Many` cho phép ứng dụng đưa sự kiện vào một luồng. Có thể dùng sink làm ingress cho command, sau đó tính state bằng `scan`. Ví dụ sau tạo bộ đếm tự tăng đến một ngưỡng để minh họa feedback có điều kiện dừng:

```java
Sinks.Many<Integer> commands = Sinks.many()
    .unicast()
    .onBackpressureBuffer(new ArrayBlockingQueue<>(128))
    .asSerialized();

Flux<Integer> states = commands.asFlux()
    .scan(0, Integer::sum)
    .replay(1)
    .autoConnect(1);

Disposable feedback = states
    .filter(total -> total < 5)
    .publishOn(Schedulers.single())
    .subscribe(total -> {
        Sinks.EmitResult result = commands.tryEmitNext(1);
        if (result != Sinks.EmitResult.OK) {
            log.warn("Không thể phát feedback command: {}", result);
        }
    });
```

Khi `feedback` subscribe, `autoConnect(1)` kết nối luồng state với sink. `scan` phát seed `0`; effect phát command `1`. State lần lượt thành `1`, `2`, `3`, `4`, `5`. Khi state bằng `5`, filter không phát tiếp cho effect nên vòng phản hồi dừng.

Các chi tiết trong ví dụ có ý nghĩa:

- `unicast()` cho phép một subscriber trực tiếp đọc ingress; `replay(1).autoConnect(1)` chia sẻ state đã tính và giữ state gần nhất cho các subscriber phía sau.
- `ArrayBlockingQueue<>(128)` giới hạn số command đang chờ; khi queue đầy, `tryEmitNext` có thể trả về `FAIL_OVERFLOW`.
- `asSerialized()` bảo vệ sink trước nhiều lời gọi phát đồng thời hoặc tái nhập theo hợp đồng serialized của sink.
- `publishOn(Schedulers.single())` tách effect khỏi đường phát đồng bộ của sink, tránh phát feedback lồng trực tiếp trong cùng call stack xử lý state.
- Kết quả `tryEmitNext` luôn được kiểm tra; không được bỏ qua lỗi phát vì command có thể đã bị từ chối.

Đây là ví dụ minh họa một feedback loop nhỏ. Ứng dụng thực tế cần quản lý `Disposable`, hoàn tất sink khi vòng đời kết thúc, quyết định xử lý overflow, và đảm bảo effect không tạo thêm command vô hạn. Nếu có nhiều nguồn phát command, hãy dùng sink serialized hoặc một ingress duy nhất có quyền sở hữu rõ ràng.

### Tránh vòng lặp không có điểm dừng

Nếu bỏ điều kiện `total < 5`, mỗi state lại phát một command, khiến state tiếp tục tăng mãi. Hệ thống có thể không bao giờ idle và có thể tích lũy queue nếu tốc độ phát lớn hơn tốc độ xử lý.

Một feedback loop production cần ít nhất:

- Điều kiện kết thúc hoặc tiêu chí hội tụ.
- Giới hạn số lần lặp hoặc deadline khi không thể chứng minh hội tụ.
- Queue có giới hạn và chính sách overflow.
- Kiểm soát tốc độ phát feedback.
- Idempotency hoặc deduplication nếu command có thể được phát lại.
- Quan sát số vòng lặp, độ dài queue, lỗi effect và thời gian hội tụ.

## 10. Không trộn reducer với side effect

Một cách viết khó kiểm soát là gọi dịch vụ hoặc phát command trực tiếp bên trong accumulator của `scan`:

```java
// Không nên: accumulator có side effect và có thể chạy lại.
Flux<State> states = commands.scan(initialState, (state, command) -> {
    State next = reduce(state, command);
    commandSink.tryEmitNext(createFollowUp(next));
    return next;
});
```

Accumulator có thể được thực thi lại khi có subscription mới hoặc khi pipeline được retry. Side effect bên trong reducer làm cho việc tính state không còn thuần và khó dự đoán. Nó cũng có thể tạo phát tín hiệu lồng nhau, race hoặc lỗi phát bị bỏ qua.

Hãy tách thành hai phần:

1. Reducer thuần tính state mới từ state cũ và event.
2. Effect quan sát state mới, quyết định có cần hành động hay không, rồi phát command qua ingress có kiểm soát.

Khi cần effect chỉ chạy một lần cho mỗi state, hãy xác định rõ semantics của subscription và sharing. Một pipeline cold được subscribe hai lần có thể chạy effect hai lần. Dùng `share`, `publish`, `replay` hoặc một service sở hữu duy nhất tùy theo vòng đời mong muốn; các operator chia sẻ có hành vi connect/disconnect khác nhau nên cần được kiểm thử.

## 11. Khi feedback chỉ là phép mở rộng luồng, cân nhắc `expand`

Không phải mọi quá trình lặp đều cần một sink và một feedback loop. Nếu mỗi giá trị tạo ra các giá trị kế tiếp theo một quy tắc đệ quy hữu hạn, Reactor có `expand` và `expandDeep`.

Ví dụ duyệt cây theo từng lớp:

```java
Flux<Node> breadthFirst = Mono.just(root)
    .expand(Node::children);
```

`expand` mở rộng theo chiều rộng: phát node hiện tại rồi lần lượt mở rộng các node con. `expandDeep` đi sâu theo nhánh trước. Các toán tử này phù hợp với việc duyệt đồ thị hoặc sinh chuỗi giá trị đệ quy có cấu trúc; chúng không thay thế một feedback loop tương tác liên tục với nguồn event bên ngoài.

Nếu đồ thị có chu trình, cần có cơ chế phát hiện node đã thăm hoặc giới hạn số lần mở rộng. Nếu không, quá trình mở rộng có thể không kết thúc.

## 12. Kiểm thử chuyển nguồn và feedback loop

### Kiểm thử `switchMap` chỉ giữ nguồn mới nhất

`TestPublisher` cho phép điều khiển thời điểm phát dữ liệu của từng nguồn trong kiểm thử:

```java
TestPublisher<TestPublisher<String>> selections = TestPublisher.create();
TestPublisher<String> first = TestPublisher.create();
TestPublisher<String> second = TestPublisher.create();

Flux<String> selected = selections.flux()
    .switchMap(TestPublisher::flux);

StepVerifier.create(selected)
    .then(() -> selections.next(first))
    .then(() -> first.next("old"))
    .expectNext("old")
    .then(() -> selections.next(second))
    .then(first::assertCancelled)
    .then(() -> second.next("new"))
    .expectNext("new")
    .then(() -> second.complete())
    .then(() -> selections.complete())
    .verifyComplete();
```

Ví dụ điều khiển riêng luồng lựa chọn để inner thứ nhất có thời gian phát `old` trước khi inner thứ hai được chọn. Khi lựa chọn mới đến, `switchMap` hủy inner đầu tiên; `assertCancelled()` xác nhận cancellation đã được gửi. Sau đó inner thứ hai phát `new` và hoàn tất. Cách điều khiển này tránh việc `Flux.just(first, second)` phát cả hai lựa chọn ngay khi subscribe, khiến inner đầu tiên bị hủy trước khi kiểm thử kịp phát dữ liệu.

### Kiểm thử điều kiện dừng của reducer

```java
StepVerifier.create(
        Flux.just(1, 1, 1)
            .scan(0, Integer::sum)
            .takeWhile(total -> total <= 3)
    )
    .expectNext(0, 1, 2, 3)
    .verifyComplete();
```

Kiểm thử xác nhận state được tích lũy theo thứ tự và luồng bị giới hạn theo điều kiện. `takeWhile` ở đây dừng khi điều kiện không còn đúng; nếu dùng với nguồn vô hạn, đây là một cách đặt giới hạn phát dựa trên state.

### Kiểm thử effect không phát vượt ngưỡng

Với feedback loop dùng sink, hãy kiểm thử reducer riêng, sau đó kiểm thử tích hợp với sink bằng queue nhỏ và điều kiện dừng xác định. Xác nhận:

- State khởi tạo đúng.
- Mỗi command hợp lệ tạo đúng một state mới.
- Effect chỉ phát command khi điều kiện cho phép.
- Khi đạt ngưỡng, không có command mới được phát.
- Queue overflow hoặc `EmitResult` thất bại được quan sát.
- Cancellation/dispose dừng effect và giải phóng subscription.

Không dùng `Thread.sleep` để chờ feedback loop trong test. Ưu tiên `StepVerifier`, scheduler ảo khi phù hợp, hoặc latch/barrier có timeout để đồng bộ rõ ràng.

## 13. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `flatMap` khi chỉ cần nguồn mới nhất | Các inner cũ vẫn chạy và có thể phát kết quả lỗi thời. | Dùng `switchMap` khi lựa chọn mới thay thế lựa chọn cũ. |
| Dùng `switchMap` cho mọi lệnh ghi | Lệnh cũ có thể bị cancel dù side effect đã bắt đầu. | Dùng `concatMap`, idempotency hoặc giao thức ghi phù hợp. |
| Nhầm `switchMap` với `switchIfEmpty` | Fallback empty không phản ứng với lựa chọn điều khiển mới. | Dùng `switchMap` cho thay nguồn, `switchIfEmpty` cho completion empty. |
| Đặt `onErrorResume` sai phạm vi | Một inner lỗi có thể kết thúc toàn bộ nguồn điều khiển. | Phục hồi trong mapper nếu chỉ muốn xử lý lỗi của inner hiện tại. |
| Phát feedback trực tiếp trong accumulator | Reducer có side effect, dễ tái nhập và khó kiểm thử. | Tách reducer thuần khỏi effect. |
| Tạo feedback không có điều kiện dừng | Luồng chạy vô hạn, tiêu thụ CPU và tài nguyên. | Xác định điều kiện dừng, giới hạn vòng lặp hoặc deadline. |
| Bỏ qua kết quả `tryEmitNext` | Command có thể bị mất khi sink overflow, terminated hoặc không có subscriber. | Kiểm tra `EmitResult` và xử lý từng trạng thái thất bại. |
| Dùng queue không giới hạn | Tải tăng có thể làm bộ nhớ tăng không kiểm soát. | Dùng queue có giới hạn và chính sách overflow. |
| Giả định cancellation hoàn tác side effect | Tác động bên ngoài có thể đã được thực hiện. | Dùng idempotency, bù trừ hoặc transaction nếu cần. |

## 14. Checklist thiết kế phụ thuộc động và feedback

Trước khi đưa pipeline vào production, hãy xác nhận:

- Giá trị nào điều khiển việc chọn Publisher con?
- Khi lựa chọn mới xuất hiện, inner cũ cần bị hủy, chạy tiếp hay đợi hoàn tất?
- Kết quả cũ có thể bị bỏ không; nguồn con có tôn trọng cancellation không?
- Lỗi của inner có làm dừng nguồn điều khiển hay chỉ ảnh hưởng lựa chọn hiện tại?
- Empty, error và timeout có chính sách riêng chưa?
- Reducer có thuần và không thực hiện I/O hoặc phát command không?
- Feedback có điều kiện dừng, giới hạn queue và chính sách overflow chưa?
- Các effect có idempotent hoặc có cơ chế chống phát trùng chưa?
- Subscription chia sẻ có vòng đời connect/disconnect rõ ràng không?
- Kiểm thử đã bao gồm chuyển nguồn, kết quả cũ đến muộn, lỗi, cancellation và điều kiện dừng chưa?

Phụ thuộc động giúp pipeline phản ứng với lựa chọn mới bằng cách chuyển sang nguồn dữ liệu phù hợp. `switchMap` thích hợp khi nguồn mới thay thế nguồn cũ; `flatMap` và `concatMap` phù hợp với các chính sách giữ hoặc tuần tự hóa công việc khác. Feedback loop mở rộng mô hình đó bằng cách đưa command mới trở lại đầu vào, nhưng cần reducer thuần, effect tách biệt, điều kiện dừng và giới hạn tài nguyên để hệ thống luôn kiểm soát được.
