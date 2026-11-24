# Trạng thái

## Mô hình hóa trạng thái bằng sự kiện và phép tích lũy

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một cách tự nhiên để biểu diễn trạng thái trong mô hình này là xem trạng thái hiện tại như kết quả của việc áp dụng tuần tự các sự kiện lên một trạng thái ban đầu.

Thay vì chỉ lưu giá trị cuối cùng, hệ thống có thể lưu các sự kiện mô tả điều gì đã xảy ra: đơn hàng được tạo, một mặt hàng được thêm, thanh toán được xác nhận hoặc đơn hàng bị hủy. Một hàm reducer nhận trạng thái hiện tại và một sự kiện, rồi tạo ra trạng thái tiếp theo. Khi đưa chuỗi sự kiện qua reducer, ta thu được các phiên bản trạng thái trung gian và trạng thái cuối.

Trong Reactor, `scan` là toán tử quan trọng để phát ra từng trạng thái tích lũy khi sự kiện đến; `reduce` chỉ phát kết quả tích lũy cuối cùng sau khi nguồn hoàn tất. Kết hợp hai toán tử với dữ liệu bất biến, thứ tự sự kiện rõ ràng và chính sách xử lý sự kiện trùng, ta có thể xây dựng pipeline trạng thái dễ kiểm thử và quan sát.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả trạng thái hiện tại như kết quả tích lũy từ trạng thái ban đầu và chuỗi sự kiện.
- Thiết kế reducer thuần, bất biến và có thể kiểm thử độc lập.
- Dùng `scan` để phát trạng thái sau từng sự kiện và `reduce` để tính trạng thái cuối.
- Chọn `scanWith` hoặc `reduceWith` khi cần khởi tạo seed riêng cho mỗi subscription.
- Bảo đảm sự kiện được áp dụng đúng thứ tự và nhận diện sự kiện trùng hoặc đến muộn.
- Tách lỗi dữ liệu sự kiện khỏi lỗi hạ tầng khi dựng trạng thái.
- Kết hợp snapshot với event log để khôi phục trạng thái mà không phải phát lại toàn bộ lịch sử.
- Kiểm thử chuỗi trạng thái bằng `StepVerifier`.

## 1. Trạng thái là kết quả của một phép tích lũy

Giả sử một tài khoản bắt đầu với số dư 100. Sau đó hệ thống nhận ba sự kiện:

1. Nạp thêm 50.
2. Thanh toán 30.
3. Hoàn tiền 10.

Trạng thái thay đổi theo từng sự kiện:

~~~text
Trạng thái ban đầu: 100
AccountCredited(50)  -> 150
PaymentDebited(30)   -> 120
PaymentRefunded(10)  -> 130
~~~

Có thể mô hình hóa phép chuyển trạng thái bằng hàm:

\[
S_{n+1} = f(S_n, E_{n+1})
\]

Trong đó:

- \(S_n\) là trạng thái sau khi áp dụng n sự kiện.
- \(E_{n+1}\) là sự kiện tiếp theo.
- \(f\) là reducer, nhận trạng thái hiện tại và sự kiện để tạo trạng thái mới.
- \(S_0\) là trạng thái ban đầu hoặc snapshot dùng làm điểm bắt đầu.

Khi đã có trạng thái ban đầu và danh sách sự kiện theo đúng thứ tự, việc phát lại cùng reducer sẽ tạo lại cùng trạng thái, miễn là reducer mang tính xác định và không phụ thuộc dữ liệu bên ngoài thay đổi theo thời gian.

Đây là cách tư duy hữu ích cho hệ thống reactive: trạng thái không nhất thiết là một biến mutable được nhiều thread cập nhật trực tiếp. Nó có thể là một giá trị mới được tạo ra mỗi khi có sự kiện.

## 2. Thiết kế sự kiện và reducer bất biến

Trước tiên, xác định những sự kiện có thể làm thay đổi trạng thái. Ví dụ với tài khoản:

~~~java
sealed interface AccountEvent {
    long amount();

    record Credited(long amount) implements AccountEvent {}
    record Debited(long amount) implements AccountEvent {}
    record RefundIssued(long amount) implements AccountEvent {}
}

record VersionedEvent(
    String aggregateId,
    long version,
    AccountEvent event
) {}

record IdentifiedEvent(
    String id,
    long version,
    AccountEvent event
) {}
~~~

Các sự kiện mô tả điều đã xảy ra. Tên sự kiện nên phản ánh sự kiện trong miền nghiệp vụ, không chỉ mô tả một lệnh kỹ thuật chung chung.

Trạng thái tài khoản có thể là một record bất biến:

~~~java
record AccountState(long balance, long appliedEvents) {
    static AccountState empty() {
        return new AccountState(0, 0);
    }

    AccountState apply(AccountEvent event) {
        return switch (event) {
            case AccountEvent.Credited e ->
                new AccountState(balance + e.amount(), appliedEvents + 1);
            case AccountEvent.Debited e ->
                new AccountState(balance - e.amount(), appliedEvents + 1);
            case AccountEvent.RefundIssued e ->
                new AccountState(balance + e.amount(), appliedEvents + 1);
        };
    }
}
~~~

Ví dụ dùng switch pattern matching với sealed type, phù hợp với Java hỗ trợ pattern matching cho switch. Nếu dự án dùng phiên bản Java cũ hơn, có thể thay bằng chuỗi `instanceof` hoặc visitor.

Reducer có thể được tách thành hàm độc lập:

~~~java
AccountState reduce(AccountState current, AccountEvent event) {
    return current.apply(event);
}
~~~

Một reducer tốt thường có các đặc điểm:

- **Xác định:** cùng trạng thái và cùng sự kiện luôn tạo cùng trạng thái tiếp theo.
- **Không có tác dụng phụ:** không ghi database, gửi HTTP hoặc thay đổi biến bên ngoài.
- **Bất biến:** tạo trạng thái mới thay vì sửa đối tượng trạng thái đang được chia sẻ.
- **Có quy tắc rõ ràng:** xác định sự kiện hợp lệ và cách xử lý dữ liệu sai.
- **Dễ kiểm thử:** có thể gọi trực tiếp với một trạng thái và sự kiện cụ thể.

Reducer thuần giúp tách việc tính trạng thái khỏi việc tiếp nhận, lưu trữ và phát sự kiện. Các tác dụng phụ có thể được đặt ở những bước riêng của workflow, trong khi phép tích lũy vẫn có kết quả dự đoán được.

## 3. Dùng scan để phát trạng thái sau mỗi sự kiện

`Flux.scan(initial, accumulator)` áp dụng hàm tích lũy lần lượt lên các phần tử và phát các giá trị trung gian. Đây là toán tử phù hợp khi downstream cần quan sát trạng thái sau từng sự kiện.

~~~java
Flux<AccountEvent> events = Flux.just(
    new AccountEvent.Credited(50),
    new AccountEvent.Debited(30),
    new AccountEvent.RefundIssued(10)
);

Flux<AccountState> states =
    events.scan(AccountState.empty(), AccountState::apply);
~~~

Với seed ban đầu là số dư 0, chuỗi trạng thái tích lũy sẽ gồm seed và các trạng thái sau từng sự kiện:

| Thứ tự | Sự kiện | Số dư tích lũy |
|---:|---|---:|
| 0 | Seed ban đầu | 0 |
| 1 | Credited(50) | 50 |
| 2 | Debited(30) | 20 |
| 3 | RefundIssued(10) | 30 |

`scan` hữu ích cho:

- Cập nhật màn hình khi trạng thái thay đổi.
- Tạo số liệu tích lũy từ một luồng sự kiện.
- Theo dõi số lượng công việc đang mở.
- Dựng trạng thái một aggregate từ event log.
- Kiểm thử từng bước chuyển trạng thái, thay vì chỉ kiểm tra kết quả cuối.

### scan không thay thế việc lưu trạng thái

`scan` tính các giá trị tích lũy trong subscription hiện tại. Nó không tự lưu trạng thái vào database và không bảo đảm trạng thái sống qua lần khởi động lại. Nếu Subscriber mới đăng ký vào một cold Publisher đọc toàn bộ event log, nó có thể dựng lại trạng thái từ đầu. Nếu nguồn là hot và chỉ phát sự kiện mới, Subscriber mới cần snapshot hoặc cơ chế replay phù hợp để có trạng thái nền.

### scanWith khi cần seed riêng theo subscription

`scan(initial, accumulator)` nhận seed đã được tạo tại assembly. Nếu seed là một đối tượng mutable hoặc cần khởi tạo riêng cho từng subscription, hãy dùng `scanWith`:

~~~java
Flux<AccountState> states =
    events.scanWith(
        AccountState::empty,
        AccountState::apply
    );
~~~

Supplier tạo seed khi có subscription. Dù vậy, nên ưu tiên trạng thái bất biến để tránh việc nhiều subscription vô tình chia sẻ và sửa cùng một đối tượng seed.

## 4. Dùng reduce khi chỉ cần trạng thái cuối

Nếu downstream chỉ cần kết quả sau khi toàn bộ nguồn hoàn tất, `reduce` là lựa chọn phù hợp. Toán tử này tích lũy các phần tử và chỉ phát một kết quả cuối cùng khi nguồn hoàn tất.

~~~java
Mono<AccountState> finalState =
    events.reduce(AccountState.empty(), AccountState::apply);
~~~

Khác biệt chính:

| Toán tử | Giá trị phát ra | Khi phát |
|---|---|---|
| `scan(seed, reducer)` | Seed và các trạng thái trung gian | Mỗi khi tích lũy được trạng thái mới |
| `reduce(seed, reducer)` | Trạng thái cuối | Khi nguồn hoàn tất |
| `scanWith(seedSupplier, reducer)` | Seed và các trạng thái trung gian | Mỗi subscription tạo seed riêng |
| `reduceWith(seedSupplier, reducer)` | Trạng thái cuối | Mỗi subscription tạo seed riêng, kết quả khi nguồn hoàn tất |

Ví dụ, nếu một job đọc event log để dựng trạng thái ban đầu cho một aggregate, thường chỉ cần trạng thái cuối:

~~~java
Mono<AccountState> rebuild =
    eventStore.readForAccount(accountId)
        .reduce(AccountState.empty(), AccountState::apply);
~~~

Nếu event log rỗng, overload có seed vẫn có thể phát seed ban đầu rồi hoàn tất. Đây là khác biệt với `reduce(BiFunction)` không có seed, vốn cần phần tử đầu tiên để khởi tạo phép tích lũy và có thể hoàn tất rỗng khi nguồn không có phần tử.

Khi cần khởi tạo trạng thái theo từng subscription:

~~~java
Mono<AccountState> rebuild =
    eventStore.readForAccount(accountId)
        .reduceWith(AccountState::empty, AccountState::apply);
~~~

Dùng `reduce` cho trạng thái cuối cùng, `scan` cho trạng thái trung gian. Không nên dùng `collectList()` rồi tính lại toàn bộ nếu reducer có thể xử lý từng sự kiện trực tiếp, vì giữ toàn bộ danh sách có thể tiêu tốn nhiều bộ nhớ.

## 5. Giữ reducer thuần và tránh tác dụng phụ trong accumulator

Không nên sửa trực tiếp một đối tượng trạng thái dùng chung bên trong `scan` hoặc `reduce`:

~~~java
// Không nên: thay đổi đối tượng mutable được chia sẻ.
Flux<List<String>> history =
    events.scan(new ArrayList<>(), (list, event) -> {
        list.add(event.toString());
        return list;
    });
~~~

Mọi giá trị phát ra có thể cùng tham chiếu tới một danh sách bị sửa tiếp ở các bước sau. Subscriber giữ lại một trạng thái cũ có thể nhìn thấy nội dung đã thay đổi, khiến lịch sử trạng thái không còn ổn định. Nhiều subscription cũng có nguy cơ chia sẻ seed mutable.

Dùng trạng thái bất biến:

~~~java
Flux<List<String>> history =
    events.scan(
        List.<String>of(),
        (current, event) -> {
            List<String> next = new ArrayList<>(current);
            next.add(event.toString());
            return List.copyOf(next);
        }
    );
~~~

Mỗi bước tạo một danh sách mới và phát một giá trị không thể sửa. Với tập dữ liệu lớn, việc sao chép toàn bộ danh sách ở mỗi sự kiện có thể tốn kém; khi đó nên dùng cấu trúc dữ liệu persistent, trạng thái có cấu trúc phù hợp hoặc chỉ phát phần dữ liệu cần thiết.

Reducer cũng không nên thực hiện I/O:

~~~java
// Không nên đặt ghi database trong reducer.
Flux<AccountState> states =
    events.scan(initialState, (state, event) -> {
        repository.save(event).subscribe();
        return state.apply(event);
    });
~~~

Đoạn mã tạo nested subscription và tách tác dụng phụ khỏi vòng đời pipeline. Nếu cần lưu sự kiện hoặc trạng thái, hãy ghép thao tác lưu bằng `concatMap`, `flatMap` hoặc một workflow có thứ tự rõ ràng:

~~~java
Flux<AccountState> persistedStates =
    events.concatMap(event ->
        stateRepository.load(accountId)
            .map(state -> state.apply(event))
            .flatMap(next ->
                stateRepository.save(accountId, next)
                    .thenReturn(next)
            )
    );
~~~

Ví dụ này minh họa việc tuần tự hóa đọc, tính và lưu trạng thái. Với hệ thống nhiều writer, vẫn cần cơ chế đồng bộ hoặc optimistic concurrency ở kho lưu trữ; `concatMap` chỉ tuần tự hóa trong subscription hiện tại.

## 6. Thứ tự sự kiện quyết định trạng thái

Phép tích lũy thường phụ thuộc thứ tự. Hai sự kiện có thể cho kết quả khác nhau nếu đổi chỗ, đặc biệt khi một sự kiện kiểm tra điều kiện dựa trên trạng thái hiện tại.

Ví dụ:

~~~text
Initial balance: 100
Debited(80), Credited(50) -> 70
Credited(50), Debited(80) -> 70
~~~

Trong trường hợp phép cộng/trừ đơn giản, số dư cuối giống nhau. Nhưng nếu reducer từ chối số dư âm, thứ tự sẽ tạo ra kết quả khác:

~~~text
Initial balance: 100
Debited(120), Credited(50) -> debit bị từ chối
Credited(50), Debited(120) -> số dư cuối 30
~~~

Vì thế, hệ thống phải xác định thứ tự có ý nghĩa trong miền nghiệp vụ. Với event log theo aggregate, thường cần sequence number hoặc version tăng dần. Không nên dựa vào thứ tự ngẫu nhiên của các truy vấn hoặc việc các Publisher con hoàn tất.

### Kiểm tra version và sự kiện đến muộn

Có thể lưu version trong trạng thái:

~~~java
record VersionedAccountState(long balance, long version) {
    VersionedAccountState apply(VersionedEvent envelope) {
        if (envelope.version() != version + 1) {
            throw new EventSequenceException(
                "Expected version " + (version + 1)
                    + " but received " + envelope.version()
            );
        }

        long nextBalance = switch (envelope.event()) {
            case AccountEvent.Credited e -> balance + e.amount();
            case AccountEvent.Debited e -> balance - e.amount();
            case AccountEvent.RefundIssued e -> balance + e.amount();
        };

        return new VersionedAccountState(nextBalance, envelope.version());
    }
}
~~~

Nếu version bị thiếu hoặc lặp, reducer có thể báo lỗi để tầng xử lý quyết định đọc lại event log, bỏ sự kiện trùng đã xác nhận hoặc đưa sự kiện vào vùng cách ly. Không nên tự sắp xếp lại sự kiện chỉ theo timestamp nếu đồng hồ giữa các nguồn không đồng bộ hoặc timestamp không thể hiện thứ tự commit.

### Sự kiện trùng và tính idempotent

Message broker có thể giao lại một sự kiện sau timeout hoặc khi consumer khởi động lại. Nếu reducer áp dụng cùng một `Credited(50)` hai lần, số dư tăng gấp đôi. Có thể bảo vệ bằng event ID hoặc sequence number đã xử lý:

~~~java
record DeduplicatingAccountState(
    long balance,
    long version,
    Set<String> appliedEventIds
) {
    DeduplicatingAccountState apply(IdentifiedEvent envelope) {
        if (appliedEventIds.contains(envelope.id())) {
            return this;
        }

        if (envelope.version() != version + 1) {
            throw new EventSequenceException(
                "Expected version " + (version + 1)
                    + " but received " + envelope.version()
            );
        }

        AccountEvent event = envelope.event();
        long nextBalance = switch (event) {
            case AccountEvent.Credited e -> balance + e.amount();
            case AccountEvent.Debited e -> balance - e.amount();
            case AccountEvent.RefundIssued e -> balance + e.amount();
        };

        Set<String> nextIds = new HashSet<>(appliedEventIds);
        nextIds.add(envelope.id());

        return new DeduplicatingAccountState(
            nextBalance,
            envelope.version(),
            Set.copyOf(nextIds)
        );
    }
}
~~~

Đây là minh họa cho deduplication trong trạng thái. Giữ toàn bộ ID đã xử lý trong state có thể làm trạng thái tăng không giới hạn. Trong hệ thống lớn, thường dùng version liên tục, bảng inbox/dedup có retention hoặc cơ chế idempotency tại kho lưu trữ. Chính sách phải phù hợp với khả năng replay và yêu cầu không xử lý trùng của nghiệp vụ.

## 7. Tích lũy trạng thái theo từng khóa

Một luồng có thể chứa sự kiện của nhiều aggregate, ví dụ nhiều tài khoản hoặc nhiều đơn hàng. Không được áp dụng tất cả sự kiện lên cùng một trạng thái chung nếu mỗi tài khoản có trạng thái độc lập.

Với một tập nhỏ khóa đã biết, có thể lọc theo khóa rồi tích lũy riêng:

~~~java
Flux<AccountState> accountAStates =
    allEvents
        .filter(event -> event.aggregateId().equals("A"))
        .map(VersionedEvent::event)
        .scan(AccountState.empty(), AccountState::apply);
~~~

Nếu số khóa lớn hoặc động, có thể dùng `groupBy` để chia sự kiện theo khóa:

~~~java
Flux<AccountState> states =
    allEvents
        .groupBy(VersionedEvent::aggregateId)
        .flatMap(group ->
            group.scan(
                AccountState.empty(),
                AccountState::apply
            )
        );
~~~

Mỗi group có một phép tích lũy riêng. Tuy nhiên, `groupBy` có thể giữ nhiều group và có những yêu cầu tiêu thụ riêng; không nên dùng vô hạn với cardinality không kiểm soát. Cần giới hạn số khóa hoạt động, xử lý vòng đời group và bảo đảm sự kiện cùng aggregate đến đúng thứ tự.

Nếu cần giữ thứ tự giữa các aggregate không quan trọng nhưng trong cùng aggregate phải tuần tự, có thể xử lý từng group tuần tự và các group khác nhau đồng thời. Thiết kế concurrency phải xét đến số partition, kích thước hàng đợi và khả năng của kho lưu trữ.

## 8. Phát lại event log và snapshot

Nếu trạng thái được tính từ lịch sử sự kiện, khôi phục sau khi ứng dụng khởi động lại có thể cần phát lại nhiều sự kiện. Với event log dài, việc phát lại toàn bộ từ đầu tốn thời gian. Snapshot lưu một trạng thái tại version đã biết, rồi chỉ cần áp dụng các sự kiện sau snapshot đó.

~~~mermaid
flowchart LR
    A[Event log từ đầu] --> B[Phát lại nhiều sự kiện]
    B --> C[Trạng thái tại version N]
    D[Snapshot version N] --> E[Khôi phục trạng thái]
    E --> F[Phát lại sự kiện N+1 đến mới nhất]
    C --> G[Trạng thái hiện tại]
    F --> G
~~~

Ví dụ:

~~~java
Mono<AccountState> rebuildAccount(String accountId) {
    return snapshotStore.load(accountId)
        .defaultIfEmpty(AccountSnapshot.empty(accountId))
        .flatMap(snapshot ->
            eventStore.readAfter(accountId, snapshot.version())
                .reduce(
                    snapshot.state(),
                    AccountState::apply
                )
        );
}
~~~

Ví dụ giả định snapshot chứa trạng thái và version, còn event store chỉ trả các sự kiện sau version đó theo thứ tự. Khi snapshot không tồn tại, dùng trạng thái khởi tạo. Trong mã thực tế, reducer cần nhận envelope có version để kiểm tra sequence; ví dụ rút gọn dùng `AccountState::apply` để tập trung vào luồng khôi phục.

Snapshot là điểm tăng tốc khôi phục, không thay thế event log. Cần bảo đảm snapshot được lưu nhất quán với version tương ứng. Nếu snapshot ghi trạng thái nhưng version không khớp với event log, hệ thống có thể bỏ sót hoặc áp dụng trùng sự kiện.

Một quy trình tạo snapshot có thể:

1. Đọc snapshot hiện tại và version.
2. Phát lại các sự kiện tiếp theo để tính trạng thái mới.
3. Lưu trạng thái cùng version cuối đã áp dụng.
4. Chỉ công bố snapshot sau khi ghi thành công.
5. Khi khôi phục, đọc snapshot rồi tiếp tục từ version kế tiếp.

## 9. State stream và trạng thái mới nhất cho nhiều Subscriber

Sau khi tính trạng thái, nhiều thành phần có thể cần quan sát cập nhật. Có thể chia sẻ một luồng trạng thái đã tích lũy:

~~~java
Flux<AccountState> sharedStates =
    eventSource.eventsFor(accountId)
        .scan(AccountState.empty(), AccountState::apply)
        .share();
~~~

`share()` cho phép các Subscriber đang tham gia cùng quan sát một subscription upstream. Subscriber đến muộn không tự nhận lại toàn bộ lịch sử trạng thái đã phát. Nếu họ cần trạng thái hiện tại ngay khi tham gia, phải cung cấp snapshot hoặc chính sách replay phù hợp.

Với một trạng thái hiện tại cần phát lại giá trị mới nhất, có thể dùng sink replay latest ở tầng sở hữu trạng thái:

~~~java
Sinks.Many<AccountState> stateSink =
    Sinks.many().replay().latest();

Flux<AccountState> stateUpdates = stateSink.asFlux();
~~~

Khi reducer tạo trạng thái mới, thành phần sở hữu có thể phát trạng thái đó qua sink. Subscriber mới nhận giá trị gần nhất rồi tiếp tục theo dõi cập nhật. Cần kiểm tra kết quả `tryEmitNext`, quản lý vòng đời sink và bảo đảm chỉ có một chủ sở hữu cập nhật trạng thái hoặc có cơ chế đồng bộ phù hợp.

Không nên nhầm state stream với event log. Trạng thái là ảnh chụp kết quả tích lũy; event log là lịch sử các sự kiện đã xảy ra. Một Subscriber chỉ cần hiển thị số dư hiện tại có thể dùng state stream. Một hệ thống kiểm toán cần lưu các giao dịch cần event log bền vững.

## 10. Lỗi trong phép tích lũy

Reducer có thể phát hiện sự kiện không hợp lệ, ví dụ số tiền âm hoặc version sai. Nếu reducer ném exception trong `scan` hoặc `reduce`, Reactor chuyển exception thành `onError` và luồng kết thúc.

~~~java
Flux<AccountState> states =
    events.scan(AccountState.empty(), (state, event) -> {
        if (event.amount() <= 0) {
            throw new InvalidEventException("amount must be positive");
        }

        return state.apply(event);
    });
~~~

Không nên âm thầm bỏ một sự kiện không hợp lệ nếu nó có thể làm trạng thái sai. Có thể chọn một trong các chính sách:

- Dừng việc dựng trạng thái và báo lỗi để điều tra.
- Cách ly sự kiện lỗi vào dead-letter queue rồi tiếp tục nếu nghiệp vụ cho phép.
- Trả một kết quả `Applied` hoặc `Rejected` để biểu diễn rõ từng sự kiện.
- Đọc lại từ nguồn chuẩn hoặc snapshot khác nếu lỗi do thiếu dữ liệu.

Nếu muốn cách ly lỗi theo từng sự kiện, cần thiết kế reducer trả về kiểu kết quả thay vì ném lỗi và kết thúc toàn chuỗi:

~~~java
sealed interface ApplyResult {
    record Applied(AccountState state) implements ApplyResult {}
    record Rejected(String eventId, String reason) implements ApplyResult {}
}
~~~

Sau đó, một bước riêng có thể phân loại kết quả, phát trạng thái mới khi thành công và ghi nhận sự kiện bị từ chối. Không nên tiếp tục tích lũy từ trạng thái cũ mà không ghi nhận sự kiện bị bỏ qua, vì trạng thái cuối có thể không còn đại diện cho lịch sử đầy đủ.

Lỗi hạ tầng khi đọc event log cần được xử lý khác với lỗi reducer. Retry đọc dữ liệu có thể hợp lý nếu nguồn hỗ trợ; retry một sự kiện nghiệp vụ sai sẽ không làm nó hợp lệ.

## 11. Kiểm thử reducer và pipeline scan/reduce

Reducer thuần nên được kiểm thử độc lập trước:

~~~java
@Test
void appliesAccountEventsInOrder() {
    AccountState initial = AccountState.empty();

    AccountState afterCredit =
        initial.apply(new AccountEvent.Credited(50));

    AccountState afterDebit =
        afterCredit.apply(new AccountEvent.Debited(20));

    assertThat(afterDebit.balance()).isEqualTo(30);
    assertThat(afterDebit.appliedEvents()).isEqualTo(2);
}
~~~

Sau đó kiểm thử chuỗi bằng `StepVerifier`:

~~~java
Flux<AccountState> states =
    Flux.just(
        new AccountEvent.Credited(50),
        new AccountEvent.Debited(20),
        new AccountEvent.RefundIssued(5)
    )
    .scan(AccountState.empty(), AccountState::apply);

StepVerifier.create(states)
    .expectNext(new AccountState(0, 0))
    .expectNext(new AccountState(50, 1))
    .expectNext(new AccountState(30, 2))
    .expectNext(new AccountState(35, 3))
    .verifyComplete();
~~~

Test xác nhận seed ban đầu và từng trạng thái trung gian. Nếu hợp đồng đầu ra không muốn phát seed, có thể bỏ seed ở bước downstream theo cách rõ ràng hoặc thiết kế API phát chỉ các trạng thái sau sự kiện; cần kiểm thử đúng hợp đồng đã chọn.

Kiểm thử `reduce` chỉ phát trạng thái cuối:

~~~java
Mono<AccountState> finalState =
    Flux.just(
        new AccountEvent.Credited(50),
        new AccountEvent.Debited(20),
        new AccountEvent.RefundIssued(5)
    )
    .reduce(AccountState.empty(), AccountState::apply);

StepVerifier.create(finalState)
    .expectNext(new AccountState(35, 3))
    .verifyComplete();
~~~

Các trường hợp nên kiểm thử thêm:

- Event log rỗng; trạng thái cuối có phải seed không?
- Sự kiện đến sai version; pipeline phải báo lỗi hoặc cách ly theo chính sách.
- Sự kiện trùng; reducer có bỏ qua đúng event ID không?
- Hai sự kiện đổi thứ tự; trạng thái có thay đổi như mong đợi không?
- Nhiều aggregate; mỗi group có state độc lập không?
- Nguồn lỗi giữa chừng; downstream nhận lỗi hay trạng thái một phần theo hợp đồng nào?
- Subscriber hủy; nguồn event có dừng hoặc giải phóng tài nguyên không?
- Snapshot và event log có khôi phục đúng cùng một trạng thái không?

## 12. Những nhầm lẫn thường gặp

- **scan và reduce giống nhau:** scan phát các trạng thái trung gian; reduce chỉ phát kết quả tích lũy cuối cùng khi nguồn hoàn tất.
- **scan tự lưu trạng thái:** scan chỉ tính và phát giá trị trong subscription; lưu bền vững cần kho lưu trữ riêng.
- **Seed mutable có thể dùng chung an toàn:** nhiều subscription có thể vô tình chia sẻ và sửa cùng một đối tượng; dùng trạng thái bất biến hoặc seed riêng bằng `scanWith`.
- **Reducer có thể gọi database hoặc HTTP:** reducer nên thuần và xác định; ghép I/O bằng toán tử bên ngoài.
- **Thứ tự sự kiện không quan trọng:** nhiều quy tắc nghiệp vụ phụ thuộc thứ tự; cần version hoặc sequence rõ ràng.
- **Timestamp đủ để sắp xếp mọi event:** đồng hồ có thể lệch và timestamp không nhất thiết là thứ tự commit.
- **Retry event luôn an toàn:** phát lại sự kiện có thể áp dụng tác dụng phụ trùng; cần event ID, version và idempotency.
- **Snapshot thay thế event log:** snapshot tăng tốc khôi phục nhưng không lưu toàn bộ lịch sử cần kiểm toán.
- **share() cho Subscriber muộn trạng thái hiện tại:** share chỉ chia sẻ tín hiệu đang diễn ra; cần snapshot hoặc replay latest cho người đến muộn.
- **Lỗi một sự kiện có thể bỏ qua tùy ý:** bỏ sự kiện mà không ghi nhận có thể làm sai trạng thái và phá khả năng đối soát.

## 13. Bài tập vận dụng

Một hệ thống quản lý đơn hàng lưu các sự kiện:

- `OrderCreated(orderId, total)`
- `ItemAdded(orderId, itemId, price)`
- `PaymentConfirmed(orderId, paymentId)`
- `OrderCancelled(orderId, reason)`

Hãy thiết kế mô hình tích lũy trạng thái:

1. Xác định các trường cần có trong `OrderState`.
2. Viết reducer bất biến cho từng loại sự kiện.
3. Dùng `scan` để phát trạng thái sau từng sự kiện và `reduce` để lấy trạng thái cuối.
4. Nếu sự kiện `PaymentConfirmed` đến trước `OrderCreated`, hệ thống nên xử lý thế nào?
5. Làm sao phát hiện một `ItemAdded` bị giao lại hai lần?
6. Nếu có hàng triệu sự kiện, snapshot cần lưu trạng thái và version nào?
7. Một màn hình quản trị cần trạng thái mới nhất khi mở muộn; nên dùng event stream trực tiếp, snapshot hay replay latest?
8. Viết kiểm thử xác nhận sự kiện sai thứ tự và sự kiện trùng không làm sai số tiền đơn hàng.

**Gợi ý:** giữ aggregate ID và version trên mỗi event envelope. Reducer nên kiểm tra version kế tiếp và event ID đã áp dụng. Dùng trạng thái bất biến, tách việc đọc/lưu event khỏi phép tính reducer. Snapshot cần lưu state cùng version cuối đã áp dụng; khi khôi phục, phát lại từ version tiếp theo. Màn hình có thể đọc snapshot rồi subscribe luồng cập nhật, trong khi event log vẫn là lịch sử chuẩn.

## Kết luận

Mô hình hóa trạng thái bằng sự kiện và phép tích lũy xem trạng thái hiện tại là kết quả của việc áp dụng tuần tự các sự kiện lên một seed. Reducer thuần và bất biến giúp phép chuyển trạng thái xác định, dễ kiểm thử và có thể phát lại. Trong Reactor, `scan` phát trạng thái trung gian theo từng sự kiện, còn `reduce` tạo trạng thái cuối khi nguồn hoàn tất; `scanWith` và `reduceWith` hữu ích khi seed cần được tạo riêng cho mỗi subscription. Để trạng thái đáng tin cậy, cần giữ thứ tự theo aggregate, phát hiện sự kiện trùng hoặc sai version, tách I/O khỏi reducer và kết hợp snapshot với event log khi cần khôi phục nhanh. Khi những quy tắc này được kiểm thử bằng `StepVerifier`, pipeline trạng thái trở nên dễ dự đoán và vận hành hơn trong hệ sinh thái reactive.
