# Dùng flatMap khi nghiệp vụ cần thứ tự nghiêm ngặt

## Vì sao flatMap có thể làm sai thứ tự nghiệp vụ?

`flatMap` là toán tử rất hữu ích khi mỗi phần tử đầu vào cần gọi một publisher khác, chẳng hạn tải thêm dữ liệu từ HTTP hoặc database. Nó cho phép nhiều publisher con hoạt động đồng thời và hợp nhất kết quả của chúng. Cách này tăng khả năng tận dụng thời gian chờ I/O, nhưng kết quả không nhất thiết được phát theo thứ tự của nguồn ban đầu.

Vấn đề xuất hiện khi thứ tự là một phần của quy tắc nghiệp vụ. Ví dụ, một tài khoản nhận các lệnh ghi số dư theo trình tự; một đơn hàng phải trải qua các bước cập nhật trạng thái; hoặc một thiết bị nhận lệnh điều khiển mà lệnh sau chỉ được thực hiện sau lệnh trước. Nếu dùng `flatMap` cho các thao tác này, publisher con có thể hoàn tất theo thứ tự khác với thứ tự lệnh được nhận. Một lệnh đến sau có thể được xử lý trước, tạo ra trạng thái trung gian hoặc kết quả cuối không đúng.

Trong Project Reactor, cần phân biệt ba khái niệm: thứ tự phần tử từ nguồn, thứ tự đăng ký/thực thi publisher con và thứ tự phát kết quả xuống downstream. `flatMap`, `flatMapSequential` và `concatMap` có chính sách khác nhau cho ba khía cạnh này. Chọn đúng toán tử là một quyết định về semantics của ứng dụng, không chỉ là tối ưu hiệu năng.

## flatMap ưu tiên concurrency, không bảo đảm thứ tự giữa các nhánh

Với `Flux<T>.flatMap(mapper)`, mỗi phần tử nguồn được ánh xạ thành một publisher con. Reactor có thể subscribe nhiều publisher con cùng lúc và hợp nhất các tín hiệu của chúng. Các tín hiệu downstream vẫn tuân thủ quy tắc Reactive Streams, nhưng phần tử từ những publisher con khác nhau có thể xen kẽ theo thời điểm chúng sẵn sàng phát.

Giả sử nguồn phát các công việc A, B, C theo thứ tự. A cần 30 ms, B cần 20 ms và C cần 10 ms. `flatMap` có thể phát kết quả C, B, A vì C hoàn tất trước, dù A được nhận đầu tiên.

Trong các ví dụ minh họa và kiểm thử phía dưới, hàm chọn độ trễ được định nghĩa như sau:

```java
import java.time.Duration;

Duration latency(String key) {
    return switch (key) {
        case "A" -> Duration.ofMillis(30);
        case "B" -> Duration.ofMillis(20);
        default -> Duration.ofMillis(10);
    };
}
```

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> results = Flux.just("A", "B", "C")
    .flatMap(key -> Mono.delay(latency(key)).thenReturn(key));

// Nếu latency(A)=30ms, latency(B)=20ms, latency(C)=10ms,
// kết quả có thể đến theo thứ tự C, B, A.
```

`flatMap` không làm các callback `onNext` chạy đồng thời trên cùng subscriber. Reactive Streams yêu cầu tín hiệu được tuần tự hóa ở một subscription. Điều có thể thay đổi là thứ tự các giá trị được hợp nhất từ nhiều publisher con: nhánh hoàn tất hoặc phát phần tử trước có thể đóng góp dữ liệu trước nhánh khác.

Đối với các publisher con phát nhiều phần tử, thứ tự bên trong từng nhánh thường được giữ, nhưng các nhánh có thể xen kẽ với nhau. Ví dụ, nhánh A có thể phát `A1`, nhánh B phát `B1`, rồi A phát `A2`. Không nên dựa vào thứ tự phát của nguồn để suy ra thứ tự toàn bộ kết quả sau `flatMap`.

### Khi flatMap là lựa chọn đúng

`flatMap` phù hợp khi các công việc độc lập và kết quả có thể được xử lý theo thứ tự hoàn tất:

- Gọi nhiều dịch vụ để lấy thông tin độc lập, chẳng hạn tải ảnh đại diện cho nhiều người dùng.
- Gửi nhiều truy vấn không phụ thuộc nhau và ghép kết quả theo ID.
- Xử lý các sự kiện độc lập, trong đó thứ tự hoàn tất không ảnh hưởng trạng thái nghiệp vụ.
- Tạo nhiều tác vụ I/O đồng thời với giới hạn concurrency rõ ràng.

Ví dụ tải thông tin tồn kho cho các SKU độc lập:

```java
Flux<StockView> stocks = skus.flatMap(
    sku -> inventoryClient.findBySku(sku)
        .map(stock -> new StockView(sku, stock.quantity())),
    16
);
```

Ở đây, tối đa 16 publisher con được subscribe đồng thời trong subscription này. Nếu chỉ cần tập hợp kết quả và mỗi SKU độc lập, thứ tự phát không quan trọng. Nếu giao diện cần sắp xếp theo thứ tự SKU đầu vào, có thể chọn `flatMapSequential` hoặc sắp xếp theo khóa sau khi đã thu thập một tập hữu hạn.

Giới hạn `16` chỉ áp dụng cho lần đăng ký pipeline này. Nếu 20 request HTTP cùng chạy đoạn code trên, tổng số publisher con đang hoạt động có thể lớn hơn 16. Muốn giới hạn toàn ứng dụng, cần bulkhead, connection pool hoặc quota ở phạm vi rộng hơn.

## Ba toán tử cần phân biệt

| Toán tử | Đăng ký publisher con | Thứ tự phát kết quả | Trường hợp phù hợp |
|---|---|---|---|
| `flatMap` | Có thể đăng ký nhiều nhánh cùng lúc | Theo tín hiệu sẵn sàng từ các nhánh; có thể xen kẽ | Công việc độc lập, ưu tiên thông lượng |
| `flatMapSequential` | Đăng ký nhiều nhánh cùng lúc trong giới hạn concurrency | Theo thứ tự phần tử nguồn; nhánh sau có thể phải chờ trong buffer | Cần thứ tự đầu ra nhưng vẫn muốn chạy trước nhiều I/O độc lập |
| `concatMap` | Chỉ đăng ký nhánh tiếp theo sau khi nhánh hiện tại hoàn tất | Theo thứ tự nguồn, hoàn tất toàn bộ nhánh này rồi đến nhánh kế tiếp | Công việc phụ thuộc thứ tự hoặc side effect phải chạy tuần tự |

Sự khác biệt quan trọng nhất nằm giữa `flatMapSequential` và `concatMap`: cả hai có thể phát kết quả theo thứ tự nguồn, nhưng chỉ `concatMap` tuần tự hóa việc subscribe và thực thi publisher con. `flatMapSequential` vẫn cho các nhánh chạy đồng thời; nó chỉ giữ thứ tự khi phát kết quả.

## flatMapSequential giữ thứ tự đầu ra nhưng vẫn chạy đồng thời

`flatMapSequential` subscribe các publisher con theo thứ tự nguồn và cho phép nhiều nhánh hoạt động cùng lúc. Tuy nhiên, kết quả của nhánh sau được giữ lại cho đến khi các nhánh trước đó phát xong. Vì vậy, downstream quan sát kết quả theo thứ tự nguồn dù thời điểm hoàn tất của các nhánh khác nhau.

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> orderedResults = Flux.just("A", "B", "C")
    .flatMapSequential(
        key -> Mono.delay(latency(key)).thenReturn(key),
        3, // Tối đa ba nhánh hoạt động đồng thời.
        1  // Prefetch cho mỗi nhánh.
    );
```

Nếu C và B hoàn tất trước A, kết quả của chúng được giữ lại. Khi A hoàn tất, downstream nhận A rồi B và C theo thứ tự nguồn. Điều này có thể tạo **head-of-line blocking**: một nhánh đầu tiên chậm làm các kết quả đã sẵn sàng của những nhánh sau phải chờ.

`flatMapSequential` thích hợp khi các thao tác có thể chạy đồng thời và không gây xung đột, nhưng API hoặc người dùng cần kết quả theo thứ tự đầu vào. Ví dụ, tải nội dung của nhiều mục độc lập song song rồi hiển thị theo vị trí ban đầu. Nó không phù hợp để bảo đảm thứ tự thực thi các lệnh ghi có phụ thuộc lẫn nhau.

## concatMap tuần tự hóa từng publisher con

`concatMap` chỉ subscribe publisher con kế tiếp sau khi publisher con hiện tại hoàn tất. Nhờ vậy, nhánh sau không bắt đầu trước khi nhánh trước kết thúc. Đây là lựa chọn phù hợp khi thao tác sau phụ thuộc trạng thái do thao tác trước tạo ra.

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Receipt> receipts = commands.concatMap(command ->
    Mono.defer(() -> paymentClient.execute(command))
);
```

`Mono.defer` trì hoãn lời gọi `paymentClient.execute` đến lúc publisher con được subscribe. `concatMap` chỉ subscribe lệnh tiếp theo sau khi publisher của lệnh hiện tại hoàn tất. Nếu publisher chỉ hoàn tất sau khi hệ thống thanh toán xác nhận thao tác, các lệnh được gửi và xác nhận tuần tự theo thứ tự nguồn.

Điều kiện cuối rất quan trọng: publisher con phải đại diện cho toàn bộ thời gian thao tác cần tuần tự hóa. Nếu `paymentClient.execute` chỉ gửi lệnh vào một queue rồi hoàn tất ngay, `concatMap` chỉ tuần tự hóa việc enqueue; nó không bảo đảm hệ thống phía sau xử lý hoặc commit từng lệnh theo thứ tự. Muốn bảo đảm thứ tự ở tầng ngoài, cần acknowledgement hoặc kết quả hoàn tất phản ánh đúng thời điểm nghiệp vụ đã xử lý.

### Điều gì xảy ra khi một nhánh concatMap không hoàn tất?

Vì `concatMap` chờ nhánh hiện tại, nếu publisher con không bao giờ hoàn tất thì các phần tử phía sau không được xử lý. Với I/O có thể treo, hãy đặt timeout phù hợp và quyết định rõ có retry, ghi nhận lỗi rồi tiếp tục hay dừng toàn bộ chuỗi.

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<CommandResult> results = commands.concatMap(command ->
    Mono.defer(() -> commandClient.execute(command))
        .timeout(Duration.ofSeconds(3))
        .map(CommandResult::success)
        .onErrorResume(error ->
            Mono.just(CommandResult.failure(command.id(), error)))
);
```

Trong ví dụ, lỗi của một lệnh được chuyển thành `CommandResult.failure`, nên publisher con hoàn tất bình thường sau khi phát kết quả lỗi và `concatMap` có thể xử lý lệnh kế tiếp. Nếu bỏ `onErrorResume`, lỗi sẽ kết thúc chuỗi và các lệnh chưa xử lý sẽ không được subscribe. Chọn chính sách theo nghiệp vụ: chuỗi lệnh có thể tiếp tục sau lỗi hay phải dừng ngay.

## Thứ tự đầu ra không đồng nghĩa thứ tự side effect

Đây là nhầm lẫn nguy hiểm nhất khi chọn toán tử. `flatMapSequential` có thể phát kết quả theo thứ tự đầu vào, nhưng các publisher con vẫn được subscribe đồng thời. Nếu mapper thực hiện ghi database hoặc gửi lệnh đến dịch vụ từ xa, side effect của nhánh sau có thể bắt đầu hoặc hoàn tất trước nhánh trước.

```java
// Đầu ra có thứ tự, nhưng thao tác ghi vẫn có thể chạy đồng thời.
Flux<Receipt> orderedReceipts = commands.flatMapSequential(
    command -> paymentClient.execute(command),
    8
);
```

Nếu nghiệp vụ yêu cầu lệnh số 2 chỉ được gửi sau khi lệnh số 1 đã hoàn tất, dùng `concatMap`:

```java
Flux<Receipt> serializedReceipts = commands.concatMap(
    command -> Mono.defer(() -> paymentClient.execute(command))
);
```

Đừng chọn `flatMapSequential` chỉ vì test đầu ra thấy A, B, C đúng thứ tự. Hãy xác định side effect bắt đầu ở thời điểm nào và publisher con hoàn tất khi nào. Nếu hệ thống đích xử lý bất đồng bộ sau khi nhận lệnh, cần hợp đồng xác nhận phù hợp hoặc cơ chế tuần tự hóa tại chính hệ thống đích.

## Thứ tự chỉ có ý nghĩa trong phạm vi nguồn đã định nghĩa

`concatMap` bảo toàn thứ tự mà upstream phát đến nó. Nó không tự khôi phục thứ tự nghiệp vụ đã bị mất trước đó. Nếu nguồn được tạo từ nhiều producer, nhiều partition hoặc một `flatMap` khác, thứ tự đầu vào có thể đã khác thứ tự phát sinh ban đầu.

Ví dụ, nếu các lệnh được lấy từ message broker nhiều partition, broker có thể chỉ bảo đảm thứ tự trong từng partition. Một `concatMap` ở phía sau vẫn tuần tự hóa theo thứ tự mà consumer đưa ra, nhưng không thể tạo ra một thứ tự toàn cục mà nguồn chưa cung cấp.

Khi nghiệp vụ có sequence number, version hoặc timestamp đáng tin cậy, hãy xác định rõ khóa sắp xếp và ranh giới thứ tự. Không dùng timestamp không đồng nhất giữa các máy để suy ra thứ tự tuyệt đối nếu hệ thống không bảo đảm đồng bộ thời gian. Với giao dịch trên cùng aggregate, sequence/version do hệ thống sở hữu thường là lựa chọn rõ hơn.

## Tuần tự hóa toàn bộ luồng hay chỉ theo khóa?

Không phải lúc nào toàn bộ lệnh cũng cần chạy tuần tự. Ví dụ, lệnh của cùng một tài khoản phải theo thứ tự, nhưng lệnh của hai tài khoản khác nhau có thể chạy đồng thời. Dùng `concatMap` trực tiếp trên toàn nguồn sẽ tuần tự hóa mọi tài khoản và có thể giảm thông lượng không cần thiết.

Một mẫu có thể dùng là phân nhóm theo khóa rồi tuần tự hóa bên trong từng nhóm:

```java
import reactor.core.publisher.Flux;

Flux<AccountResult> results = accountCommands
    .groupBy(AccountCommand::accountId)
    .flatMap(group -> group.concatMap(accountService::apply));
```

Mỗi group có một chuỗi riêng; `concatMap` xử lý tuần tự các lệnh của cùng `accountId`, trong khi các group khác nhau có thể tiến triển đồng thời. Mẫu này chỉ phù hợp khi số group đang hoạt động được kiểm soát và mọi group được subscribe, tiêu thụ. `groupBy` giữ group cho đến khi nguồn/group kết thúc; số khóa có cardinality rất lớn hoặc không giới hạn có thể tạo nhiều group và gây áp lực bộ nhớ. Với tải lớn, cân nhắc partition có giới hạn, keyed queue, broker partition theo aggregate hoặc cơ chế xử lý tuần tự tại tầng lưu trữ.

Nếu cần giới hạn số tài khoản xử lý đồng thời, có thể đặt concurrency cho `flatMap` ngoài:

```java
Flux<AccountResult> results = accountCommands
    .groupBy(AccountCommand::accountId)
    .flatMap(
        group -> group.concatMap(accountService::apply),
        MAX_ACTIVE_ACCOUNTS
    );
```

Giới hạn này là số group được subscribe đồng thời. Khi số group vượt giới hạn, các group còn lại có thể phải chờ được tiêu thụ; cần kiểm tra đặc tính `groupBy`, prefetch và số khóa thực tế để tránh upstream bị giữ do các group chưa được đọc. Không đặt một giới hạn nhỏ tùy tiện nếu nguồn có thể tạo nhiều khóa khác nhau trong thời gian ngắn.

## Vì sao collectList rồi sort không thay thế concatMap?

Một cách sửa thường thấy là thu toàn bộ kết quả vào danh sách rồi sắp xếp theo thứ tự đầu vào. Cách này có thể phù hợp với một tập dữ liệu hữu hạn, nhỏ và chỉ cần thứ tự hiển thị:

```java
import java.util.Comparator;
import java.util.List;
import reactor.core.publisher.Mono;

Mono<List<Result>> sortedResults = source
    .flatMap(this::loadIndependentResult)
    .collectList()
    .map(results -> results.stream()
        .sorted(Comparator.comparing(Result::sequence))
        .toList());
```

Nhưng nó không bảo đảm side effect được thực hiện tuần tự. Tất cả lời gọi `loadIndependentResult` vẫn có thể chạy đồng thời; chỉ kết quả cuối được sắp xếp. Ngoài ra, `collectList()` phải giữ toàn bộ phần tử trong bộ nhớ và không phát kết quả cho downstream cho đến khi nguồn hoàn tất. Với nguồn vô hạn hoặc rất lớn, cách này không phù hợp.

Nếu yêu cầu là thứ tự thực thi, dùng `concatMap`. Nếu chỉ yêu cầu thứ tự hiển thị sau khi đã tải độc lập, có thể giữ sequence number rồi sắp xếp khi tập dữ liệu có giới hạn. Hai mục tiêu này cần được phân biệt ngay trong thiết kế.

## Vì sao switchMap không phù hợp cho chuỗi lệnh phải xử lý đủ?

`switchMap` hủy publisher con trước đó khi nhận phần tử nguồn mới và chuyển sang publisher con mới nhất. Đây là hành vi phù hợp với tìm kiếm theo từ khóa: kết quả truy vấn cũ không còn cần thiết khi người dùng nhập từ khóa mới.

```java
Flux<SearchResult> searchResults = searchTerms
    .switchMap(term -> searchClient.search(term));
```

Nhưng với chuỗi lệnh thanh toán, cập nhật kho hoặc ghi audit, hủy publisher con cũ khi lệnh mới đến có thể khiến một thao tác bị bỏ dở. Cancellation ở Reactor không nhất thiết đảo ngược side effect đã bắt đầu ở hệ thống bên ngoài. Không dùng `switchMap` cho công việc bắt buộc phải xử lý đầy đủ và theo thứ tự.

## Retry và lỗi có thể làm thay đổi chuỗi lệnh

Khi dùng `concatMap`, một publisher con phát lỗi thường kết thúc toàn bộ chuỗi; các phần tử sau không được xử lý. Nếu lỗi được phục hồi bên trong mapper để trả một kết quả bình thường, `concatMap` có thể tiếp tục lệnh tiếp theo. Nếu retry nằm trong publisher con, nhánh đó giữ vị trí đầu chuỗi cho đến khi retry thành công hoặc cạn số lần thử.

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Flux<CommandResult> results = commands.concatMap(command ->
    Mono.defer(() -> commandClient.execute(command))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .filter(this::isTransientFailure))
        .map(CommandResult::success)
        .onErrorResume(error ->
            Mono.just(CommandResult.failure(command.id(), error)))
);
```

Retry có giới hạn giữ thứ tự vì lệnh kế tiếp chưa được subscribe cho đến khi publisher hiện tại kết thúc. Tuy nhiên, retry thao tác ghi có thể tạo side effect trùng nếu dịch vụ đã xử lý lệnh nhưng phản hồi bị mất. Dùng idempotency key hoặc version check ở hệ thống đích; tuần tự hóa không tự giải quyết tính lặp an toàn.

Nếu cần dừng cả chuỗi ngay khi một lệnh thất bại, để lỗi truyền ra ngoài. Nếu cần tiếp tục và ghi nhận từng lỗi, chuyển lỗi thành kết quả miền bên trong nhánh. Tránh `onErrorContinue` như một cách mặc định để bỏ qua mọi lỗi, vì nó có thể làm luồng lệnh tiếp tục trong trạng thái nghiệp vụ không nhất quán.

## Kiểm thử thứ tự bằng StepVerifier và virtual time

Kiểm thử nên chứng minh rõ sự khác nhau giữa thứ tự hoàn tất và thứ tự nguồn. Dùng `StepVerifier.withVirtualTime` để mô phỏng các publisher con có thời gian hoàn tất khác nhau mà không phải chờ đồng hồ thật:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() -> Flux.just("A", "B", "C")
        .flatMap(key -> Mono.delay(latency(key)).thenReturn(key)))
    .thenAwait(Duration.ofMillis(30))
    .expectNext("C", "B", "A")
    .verifyComplete();
```

Publisher được tạo bên trong supplier của `withVirtualTime` để các toán tử thời gian dùng virtual scheduler. Kết quả cho thấy `flatMap` phát theo thứ tự các nhánh hoàn tất trong ví dụ này.

Kiểm tra `flatMapSequential` với cùng độ trễ:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() -> Flux.just("A", "B", "C")
        .flatMapSequential(
            key -> Mono.delay(latency(key)).thenReturn(key),
            3,
            1))
    .thenAwait(Duration.ofMillis(30))
    .expectNext("A", "B", "C")
    .verifyComplete();
```

Ba nhánh được đăng ký cùng lúc nhưng kết quả được phát theo thứ tự nguồn. Để kiểm tra `concatMap`, tổng thời gian là tổng độ trễ của từng nhánh vì nhánh sau chỉ bắt đầu sau khi nhánh trước hoàn tất:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() -> Flux.just("A", "B", "C")
        .concatMap(key -> Mono.delay(latency(key)).thenReturn(key)))
    .thenAwait(Duration.ofMillis(60))
    .expectNext("A", "B", "C")
    .verifyComplete();
```

Ngoài thứ tự kết quả, test cho side effect nên kiểm tra thời điểm gọi mapper hoặc số tác vụ đang hoạt động. Ví dụ, dùng `AtomicInteger` theo dõi số nhánh đồng thời và xác nhận `concatMap` không có hơn một nhánh active trong cùng subscription. Với `flatMapSequential`, có thể xác nhận nhiều nhánh được subscribe trước khi nhánh đầu hoàn tất.

## Những lỗi thường gặp

- **Dùng `flatMap` cho các lệnh phụ thuộc thứ tự:** nhánh hoàn tất nhanh có thể phát kết quả trước nhánh được nhận trước. Dùng `concatMap` nếu cần tuần tự hóa.
- **Dùng `flatMapSequential` để bảo vệ side effect:** toán tử giữ thứ tự phát kết quả nhưng vẫn subscribe nhánh đồng thời. Dùng `concatMap` khi side effect phải chạy lần lượt.
- **Nhầm thứ tự đầu ra với thứ tự commit:** publisher con có thể hoàn tất khi request mới được gửi hoặc enqueue, không phải khi hệ thống đích commit. Xác định chính xác terminal signal đại diện cho điều gì.
- **Dùng `concatMap` cho mọi công việc:** tuần tự hóa cả những tác vụ độc lập làm giảm throughput. Chỉ tuần tự hóa trong phạm vi thật sự có phụ thuộc.
- **Dùng `switchMap` cho lệnh phải xử lý đủ:** publisher cũ bị cancel khi có lệnh mới; side effect bên ngoài có thể đã bắt đầu.
- **Sắp xếp sau `collectList()` để sửa thứ tự thực thi:** chỉ sắp xếp kết quả cuối và giữ toàn bộ dữ liệu trong bộ nhớ; không tuần tự hóa side effect.
- **Quên giới hạn concurrency của `flatMap`:** số publisher con hoạt động có thể vượt năng lực dịch vụ đích, nhất là khi nhiều request cùng chạy pipeline.
- **Để một nhánh concatMap treo vô thời hạn:** các lệnh sau bị chặn. Đặt timeout và chính sách lỗi/retry có giới hạn.
- **Retry thao tác ghi không idempotent:** phản hồi mất có thể khiến lệnh được thực hiện hai lần. Dùng idempotency key hoặc kiểm tra version ở hệ thống đích.
- **Cho rằng concatMap khôi phục thứ tự đã mất upstream:** nó chỉ giữ thứ tự phần tử mà chính nó nhận được. Xác định sequence/partition ở nguồn nếu cần thứ tự nghiệp vụ toàn cục.
- **Không kiểm thử thời điểm subscribe:** test chỉ kiểm tra danh sách cuối có thể bỏ sót việc side effect đã chạy đồng thời. Kiểm tra subscription và concurrency bên cạnh output.

## Quy trình chọn toán tử theo yêu cầu thứ tự

Trước khi dùng `flatMap`, hãy xác định mỗi phần tử nguồn tạo ra thao tác độc lập hay thao tác phụ thuộc vào kết quả/trạng thái của phần tử trước. Nếu thứ tự chỉ quan trọng khi hiển thị kết quả, có thể dùng `flatMapSequential` để chạy I/O đồng thời rồi phát theo thứ tự nguồn. Nếu side effect hoặc trạng thái đích phải được cập nhật tuần tự, dùng `concatMap` và bảo đảm publisher con chỉ hoàn tất sau khi thao tác cần bảo vệ đã được xác nhận.

Tiếp theo, xác định phạm vi thứ tự: toàn bộ luồng hay chỉ theo một khóa như account ID, order ID hoặc aggregate ID. Tránh tuần tự hóa toàn hệ thống nếu chỉ các phần tử cùng khóa mới phụ thuộc nhau. Giới hạn concurrency giữa các khóa, quản lý số group và kiểm tra thứ tự đã được bảo đảm ở nguồn hay chưa.

Cuối cùng, quyết định cách xử lý lỗi, timeout, retry và cancellation. Retry phải có giới hạn và thao tác ghi phải idempotent; lỗi có thể dừng toàn chuỗi hoặc được chuyển thành kết quả lỗi theo chính sách nghiệp vụ. Dùng `StepVerifier` cùng virtual time để chứng minh thứ tự đầu ra, thời điểm đăng ký và số nhánh đang hoạt động. `flatMap` tối ưu cho công việc độc lập; khi nghiệp vụ cần thứ tự nghiêm ngặt, chọn toán tử thể hiện đúng mức tuần tự hóa thay vì chỉ sắp xếp kết quả sau cùng.
