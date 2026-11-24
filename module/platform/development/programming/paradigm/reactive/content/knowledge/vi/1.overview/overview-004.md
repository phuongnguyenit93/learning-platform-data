# Một ví dụ xuyên suốt: tìm kiếm gợi ý khi người dùng nhập

Hãy hình dung một ô tìm kiếm sản phẩm. Người dùng gõ `c`, rồi `ca`, `cat` và tiếp tục sửa từ khóa. Ứng dụng cần hiển thị gợi ý nhanh, tránh gửi một truy vấn cho từng phím bấm, không để kết quả của từ khóa cũ ghi đè kết quả mới, và vẫn hoạt động khi dịch vụ tìm kiếm chậm hoặc gặp lỗi.

Đây là một ví dụ phù hợp để học lập trình phản ứng trong Java. Ta xem mỗi thay đổi của ô nhập là một sự kiện, đưa các sự kiện vào một luồng, rồi mô tả cách chuẩn hóa, trì hoãn, loại bỏ truy vấn trùng, gọi dịch vụ tìm kiếm và phát kết quả. Ví dụ cũng cho thấy vai trò riêng của `Mono`, `Flux`, các toán tử Reactor, scheduler, Reactive Streams và kiểm thử.

## 1. Bài toán và luồng sự kiện

Một cách xử lý tuần tự đơn giản là gọi tìm kiếm ngay sau mỗi lần người dùng nhập. Cách này có hai vấn đề thường gặp:

- Nhiều truy vấn gần giống nhau được gửi liên tiếp trong lúc người dùng vẫn đang gõ.
- Truy vấn cũ có thể hoàn tất sau truy vấn mới. Nếu ứng dụng hiển thị mọi kết quả ngay khi nhận được, gợi ý của từ khóa cũ có thể xuất hiện sau gợi ý mới.

Ta muốn hành vi sau:

1. Nhận sự kiện thay đổi nội dung ô tìm kiếm.
2. Chuẩn hóa chuỗi, chẳng hạn bỏ khoảng trắng ở hai đầu.
3. Chờ một khoảng ngắn sau lần nhập gần nhất, ví dụ 250 ms.
4. Bỏ qua từ khóa trùng với từ khóa đã xử lý.
5. Nếu từ khóa quá ngắn, phát trạng thái rỗng và dừng truy vấn đang chạy.
6. Nếu từ khóa hợp lệ, tìm tối đa 10 gợi ý.
7. Chỉ hiển thị trạng thái và kết quả của từ khóa hiện hành.
8. Chuyển lỗi dịch vụ đã biết thành trạng thái có thể hiển thị cho người dùng.

Sơ đồ tổng quát:

~~~mermaid
flowchart LR
    A["Sự kiện nhập"] --> B["Flux<String>"]
    B --> C["Chuẩn hóa"]
    C --> D["debounce 250 ms"]
    D --> E["distinctUntilChanged"]
    E --> F["switchMap"]
    F --> G{"Từ khóa đủ dài?"}
    G -- "Chưa" --> H["Trạng thái rỗng"]
    G -- "Đủ" --> I["Flux<Suggestion>"]
    I --> J["take(10), collectList"]
    J --> K["Mono<List<Suggestion>>"]
    K --> L["SearchView"]
    H --> M["Subscriber / giao diện"]
    L --> M
~~~

Trong ví dụ này, `Flux<String>` đại diện cho chuỗi sự kiện từ ô nhập. Nguồn sự kiện có thể là một kênh WebSocket hoặc RSocket mà adapter chuyển thành Publisher. Nếu ứng dụng chỉ dùng REST thông thường, mỗi HTTP request thường mang một từ khóa riêng; trình duyệt cần debounce hoặc hủy request ở phía client để tạo hành vi tương tự. Một endpoint REST đơn lẻ không tự nhìn thấy toàn bộ lịch sử phím bấm.

Publisher tuân theo Reactive Streams không phát `null`. Khi người dùng xóa ô tìm kiếm, adapter gửi chuỗi rỗng để biểu diễn thay đổi đó.

## 2. Chọn Mono và Flux cho từng loại dữ liệu

Trong Project Reactor:

- `Flux<T>` biểu diễn một Publisher có thể phát không, một hoặc nhiều phần tử. Chuỗi sự kiện nhập là `Flux<String>`; kết quả tìm kiếm cũng có thể là `Flux<Suggestion>`.
- `Mono<T>` biểu diễn một Publisher có thể phát không hoặc một phần tử. Khi cần trả một danh sách gợi ý đã gom lại, `Mono<List<Suggestion>>` là kiểu phù hợp.

Hai kiểu này đều tuân theo hợp đồng Publisher của Reactive Streams. Chúng mô tả dữ liệu sẽ được phát khi có subscriber đăng ký; việc tạo pipeline thường chưa thực hiện truy vấn ngay lập tức.

Ta dùng các kiểu dữ liệu nhỏ để biểu diễn kết quả:

~~~java
record Suggestion(String id, String title) {}

enum SearchStatus {
    EMPTY, LOADING, READY, UNAVAILABLE
}

record SearchView(
    String query,
    SearchStatus status,
    List<Suggestion> items
) {
    static SearchView empty(String query) {
        return new SearchView(query, SearchStatus.EMPTY, List.of());
    }

    static SearchView loading(String query) {
        return new SearchView(query, SearchStatus.LOADING, List.of());
    }

    static SearchView ready(String query, List<Suggestion> items) {
        return new SearchView(query, SearchStatus.READY, List.copyOf(items));
    }

    static SearchView unavailable(String query) {
        return new SearchView(query, SearchStatus.UNAVAILABLE, List.of());
    }
}
~~~

Hợp đồng của dịch vụ tìm kiếm trả về một luồng gợi ý:

~~~java
interface CatalogSearch {
    Flux<Suggestion> find(String query);
}
~~~

Nguồn tìm kiếm có thể là repository reactive, một HTTP client reactive hoặc một dịch vụ khác có khả năng phát kết quả theo luồng. Nếu tầng dữ liệu chỉ có API đồng bộ, cần xử lý riêng việc gọi mã chặn; phần scheduler ở dưới sẽ giải thích cách đó.

## 3. Xây dựng pipeline tìm kiếm

Đây là phần chính của ví dụ. Ta nhận một `Flux<String>` các thay đổi của ô nhập và trả về `Flux<SearchView>` gồm trạng thái đang tìm, kết quả hoặc trạng thái lỗi có thể xử lý.

~~~java
import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

final class SuggestionService {
    private final CatalogSearch catalog;

    SuggestionService(CatalogSearch catalog) {
        this.catalog = catalog;
    }

    Flux<SearchView> suggestions(Flux<String> queryChanges) {
        return queryChanges
            .map(String::trim)
            .debounce(Duration.ofMillis(250))
            .distinctUntilChanged()
            .switchMap(this::search);
    }

    private Flux<SearchView> search(String query) {
        if (query.length() < 2) {
            return Flux.just(SearchView.empty(query));
        }

        Mono<SearchView> result = catalog.find(query)
            .take(10)
            .collectList()
            .map(items -> SearchView.ready(query, items))
            .onErrorResume(
                SearchUnavailableException.class,
                error -> Mono.just(SearchView.unavailable(query))
            );

        return Flux.concat(
            Mono.just(SearchView.loading(query)),
            result
        );
    }
}
~~~

`SearchUnavailableException` là ngoại lệ nghiệp vụ do tầng tìm kiếm định nghĩa khi dịch vụ không thể phục vụ truy vấn. Trong dự án thực tế, cần thay bằng kiểu lỗi và quy tắc xử lý phù hợp với hệ thống.

Pipeline được ghép từ các bước có trách nhiệm riêng:

**`map` — chuẩn hóa đầu vào.** Adapter biểu diễn thao tác xóa ô bằng chuỗi rỗng; `trim()` bỏ khoảng trắng ở hai đầu. Việc chuẩn hóa trước khi so sánh giúp các giá trị như `"cat"` và `" cat "` được xem là cùng một từ khóa.

**`debounce` — chờ người dùng tạm ngừng nhập.** Với khoảng 250 ms, toán tử chỉ phát giá trị mới nhất sau khi không có sự kiện tiếp theo trong khoảng thời gian đó. Khi người dùng gõ nhanh, nhiều giá trị trung gian được gộp lại thành một truy vấn. Thời gian này là lựa chọn trải nghiệm người dùng; có thể điều chỉnh theo độ trễ mạng và đặc điểm tìm kiếm.

**`distinctUntilChanged` — bỏ từ khóa liên tiếp bị lặp.** Nếu nội dung sau chuẩn hóa giống hệt giá trị vừa xử lý, pipeline không phát lại truy vấn. Toán tử mặc định so sánh bằng `equals`; với kiểu dữ liệu phức tạp, có thể cần cung cấp cách so sánh riêng.

**`switchMap` — chuyển sang truy vấn mới nhất.** Khi từ khóa mới đã qua debounce, `switchMap` hủy subscription của luồng tìm kiếm trước đó và đăng ký luồng mới. Nhờ vậy, kết quả phát muộn từ truy vấn cũ không tiếp tục đi ra downstream. Đây là lựa chọn phù hợp với tìm kiếm gợi ý vì giá trị mới nhất thường thay thế giá trị cũ.

**Kiểm tra độ dài bên trong `search`.** Nếu chuỗi ngắn hơn hai ký tự, hàm trả trạng thái rỗng. Bước này được đặt bên trong hàm mà `switchMap` gọi. Vì thế, khi người dùng xóa bớt ký tự và từ khóa mới quá ngắn, subscription tìm kiếm trước đó cũng bị hủy. Nếu dùng `filter` để loại từ khóa ngắn trước `switchMap`, sự kiện bị lọc sẽ không đến được `switchMap`; truy vấn cũ có thể tiếp tục chạy.

**`take(10)` và `collectList`.** `take(10)` giới hạn tối đa mười gợi ý cho một truy vấn và hủy upstream khi đã nhận đủ mười phần tử. `collectList()` gom các phần tử thành một `Mono<List<Suggestion>>`; nếu không có gợi ý, nó vẫn phát một danh sách rỗng khi upstream hoàn tất.

**`Flux.concat` — phát trạng thái theo thứ tự.** Giao diện nhận `LOADING` trước, rồi nhận `READY` hoặc `UNAVAILABLE` sau khi truy vấn kết thúc. Cả hai trạng thái đều gắn với cùng từ khóa để giao diện biết kết quả thuộc truy vấn nào.

## 4. Vì sao cần switchMap để tránh kết quả cũ?

Giả sử người dùng nhập `"ca"` rồi nhanh chóng nhập `"cat"`. Truy vấn `"ca"` có thể mất 600 ms, còn truy vấn `"cat"` chỉ mất 120 ms. Nếu dùng `flatMap`, cả hai truy vấn có thể chạy đồng thời và kết quả của `"ca"` có thể đến sau `"cat"`.

Với `switchMap`, khi sự kiện `"cat"` vượt qua debounce, subscription của truy vấn `"ca"` bị hủy. Luồng kết quả mới được theo dõi. Như vậy, pipeline ưu tiên kết quả thuộc từ khóa mới nhất.

Các toán tử kết hợp luồng có ngữ nghĩa khác nhau:

| Toán tử | Hành vi | Khi nào phù hợp |
|---|---|---|
| `flatMap` | Đăng ký nhiều Publisher con; kết quả có thể xen kẽ theo thời điểm hoàn tất. | Cần xử lý nhiều yêu cầu độc lập cùng lúc. |
| `concatMap` | Chờ Publisher con trước hoàn tất rồi mới xử lý phần tử tiếp theo. | Cần giữ thứ tự xử lý tuần tự. |
| `switchMap` | Hủy Publisher con cũ khi có phần tử mới. | Kết quả cũ mất giá trị khi đầu vào thay đổi, như tìm kiếm gợi ý. |

Hủy subscription là tín hiệu hợp tác. Một HTTP client hoặc driver reactive có thể dừng request đang chạy khi nhận cancel. Nếu tầng bên dưới không hỗ trợ hủy, công việc tốn tài nguyên có thể vẫn tiếp tục ở đó; tuy vậy, `switchMap` vẫn ngăn kết quả cũ được phát tiếp qua nhánh đã bị thay thế. Vì vậy, nên chọn client và driver có hỗ trợ cancellation khi có thể.

## 5. Publisher, Subscriber và backpressure trong ví dụ

Một pipeline Reactor là một Publisher. Khi adapter của giao diện hoặc một thành phần khác đăng ký, nó trở thành Subscriber của Publisher đó. Publisher gửi Subscription qua `onSubscribe`; Subscriber dùng Subscription để báo nhu cầu bằng `request(n)` hoặc hủy bằng `cancel()`.

Có thể hình dung quan hệ như sau:

~~~mermaid
sequenceDiagram
    participant UI as Subscriber / UI
    participant P as Publisher pipeline
    participant C as Catalog Publisher
    UI->>P: subscribe()
    P->>UI: onSubscribe(subscription)
    UI->>P: request(1)
    P-->>UI: onNext(LOADING)
    UI->>P: request(1)
    P->>C: subscribe(query)
    C-->>P: onNext(suggestion)
    C-->>P: onComplete()
    P-->>UI: onNext(READY)
    UI->>P: request(1)
    UI->>P: cancel() khi đóng kênh
~~~

Nếu cần điều khiển demand thủ công trong một adapter, Reactor cung cấp `BaseSubscriber`. Ví dụ dưới đây yêu cầu một trạng thái mỗi lần và chỉ yêu cầu phần tử kế tiếp sau khi xử lý phần tử hiện tại:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

output.subscribe(new BaseSubscriber<SearchView>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(SearchView view) {
        render(view);
        request(1);
    }
});
~~~

`output` là `Flux<SearchView>` do `SuggestionService` trả về; `render` là thao tác cập nhật giao diện nhanh, không chặn. Khi kênh giao tiếp đóng, adapter cần hủy subscription. Trong ứng dụng WebFlux hoặc RSocket thông thường, framework thường quản lý demand và cancellation thay cho mã `BaseSubscriber` tự viết.

Cần phân biệt ba cơ chế trong pipeline:

- **Backpressure** là giao thức để Subscriber báo lượng phần tử mình sẵn sàng nhận. Publisher phải tôn trọng nhu cầu đã được yêu cầu.
- **Debounce** giảm số truy vấn bằng cách bỏ qua những thay đổi nhập quá sát nhau.
- **SwitchMap** hủy công việc cũ khi đã có từ khóa mới.

Ba cơ chế hỗ trợ các mục tiêu khác nhau. Debounce không thay thế backpressure; backpressure cũng không tự quyết định truy vấn nào đã lỗi thời. `take(10)` là giới hạn số gợi ý của một truy vấn và còn hủy Publisher con khi đủ số lượng.

## 6. Điều khiển scheduler khi tầng tìm kiếm có thao tác chặn

Một pipeline reactive không tự động chạy trên nhiều thread. Reactor thường thực thi các toán tử theo thread phát tín hiệu, trừ khi có scheduler hoặc nguồn dữ liệu tạo ranh giới thực thi khác.

Nếu tầng tìm kiếm dùng driver reactive, hãy giữ luồng xử lý không chặn và không chuyển scheduler chỉ vì thấy mã reactive. Nếu phải gọi thư viện cũ có phương thức chặn, có thể bọc lời gọi đó bằng `Mono.fromCallable` và chuyển sang `boundedElastic`:

~~~java
import reactor.core.scheduler.Schedulers;

Mono<List<Suggestion>> findWithLegacyClient(String query) {
    return Mono.fromCallable(() -> legacyCatalog.search(query))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`subscribeOn` chỉ định scheduler cho quá trình subscription và nguồn của Publisher. `boundedElastic` phù hợp để cô lập các tác vụ có khả năng chặn, với số lượng thread được quản lý theo giới hạn của scheduler.

`publishOn` chuyển việc thực thi của các toán tử phía sau nó sang scheduler đã chọn. Ví dụ, nếu bước xếp hạng kết quả tiêu tốn CPU, có thể đặt ranh giới phù hợp:

~~~java
return catalog.find(query)
    .publishOn(Schedulers.parallel())
    .map(this::calculateScore);
~~~

`parallel` phù hợp cho công việc tính toán ngắn và không chặn. Không dùng nó để chạy mã I/O chặn. Cũng không gọi `block()` bên trong request handler hoặc event loop của WebFlux; việc đó có thể chiếm thread cần phục vụ nhiều request khác.

## 7. Xử lý lỗi để luồng nhập vẫn tiếp tục

Trong ví dụ, lỗi `SearchUnavailableException` được xử lý bên trong Publisher con của từng từ khóa:

~~~java
.onErrorResume(
    SearchUnavailableException.class,
    error -> Mono.just(SearchView.unavailable(query))
)
~~~

Vị trí xử lý này quan trọng. Một truy vấn gặp lỗi được chuyển thành trạng thái `UNAVAILABLE`, còn Publisher của chuỗi sự kiện nhập vẫn có thể nhận từ khóa tiếp theo. Nếu lỗi thoát khỏi toàn bộ pipeline và kết thúc luồng ngoài, các lần nhập sau có thể không còn được xử lý.

Không nên biến mọi lỗi thành danh sách rỗng. Trạng thái không có kết quả (`READY` với danh sách rỗng) khác với dịch vụ không khả dụng (`UNAVAILABLE`). Việc phân biệt giúp giao diện thông báo đúng và giúp hệ thống quan sát lỗi chính xác hơn.

Với lỗi tạm thời, có thể thêm timeout và retry có giới hạn ở ranh giới gọi dịch vụ, trước khi ánh xạ lỗi cuối cùng thành trạng thái giao diện:

~~~java
import reactor.util.retry.Retry;

catalog.find(query)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransient))
    .take(10)
    .collectList();
~~~

`isTransient` là chính sách do ứng dụng định nghĩa. Chỉ retry các lỗi có khả năng hồi phục; không retry lỗi xác thực, lỗi dữ liệu đầu vào hoặc mọi lỗi một cách vô điều kiện. Retry cũng làm tăng số lần gọi, vì vậy cần giới hạn số lần thử và thời gian chờ.

Cancellation do `switchMap` phát ra khi có truy vấn mới là một phần bình thường của luồng, không nên xem đó là lỗi nghiệp vụ để retry.

## 8. Kiểm thử pipeline bằng StepVerifier

Không cần dựa vào thao tác bàn phím thật để kiểm thử logic. Ta có thể tạo Publisher đầu vào bằng `Flux.just`, `Flux.concat` hoặc các Publisher giả lập, sau đó dùng `StepVerifier` để xác minh thứ tự và nội dung tín hiệu.

Ví dụ, khi nguồn phát nhanh hai từ khóa rồi hoàn tất, debounce chỉ phát từ khóa cuối cùng. Publisher kết quả vì vậy chỉ có trạng thái của `"cat"`:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void chiTimKiemTuKhoaCuoiCung() {
    CatalogSearch catalog = query ->
        Flux.just(new Suggestion("1", query + " food"));

    SuggestionService service = new SuggestionService(catalog);

    StepVerifier.create(service.suggestions(Flux.just("ca", "cat")))
        .expectNextMatches(view ->
            view.query().equals("cat")
                && view.status() == SearchStatus.LOADING)
        .expectNextMatches(view ->
            view.query().equals("cat")
                && view.status() == SearchStatus.READY
                && view.items().size() == 1)
        .verifyComplete();
}
~~~

Có thể dùng virtual time để kiểm tra khoảng debounce mà không phải chờ thật 250 ms. Nguồn dưới đây phát `"ca"` ngay, phát `"cat"` sau 100 ms rồi giữ luồng mở. `"ca"` không được phát sau 250 ms vì đã có sự kiện mới; `"cat"` xuất hiện khi đủ 250 ms yên lặng tính từ lần nhập thứ hai:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void debounceChiPhatGiaTriSauCung() {
    CatalogSearch catalog = query ->
        Flux.just(new Suggestion("1", query + " food"));

    SuggestionService service = new SuggestionService(catalog);

    StepVerifier.withVirtualTime(() -> service.suggestions(
            Flux.concat(
                Flux.just("ca"),
                Mono.delay(Duration.ofMillis(100)).thenReturn("cat"),
                Flux.never()
            )))
        .thenAwait(Duration.ofMillis(350))
        .expectNextMatches(view ->
            view.query().equals("cat")
                && view.status() == SearchStatus.LOADING)
        .thenCancel()
        .verify();
}
~~~

Supplier truyền vào `withVirtualTime` giúp pipeline được tạo sau khi virtual scheduler được cài đặt. Các toán tử thời gian trong pipeline vì thế dùng đồng hồ ảo của StepVerifier. `thenCancel()` kết thúc phép thử vì Publisher đầu vào vẫn mở.

Ngoài hai trường hợp trên, nên kiểm thử riêng:

- Từ khóa ngắn hơn hai ký tự phát `EMPTY` và hủy truy vấn đang chạy.
- Từ khóa sau chuẩn hóa giống từ khóa trước không gọi dịch vụ lần nữa.
- Publisher tìm kiếm phát lỗi đã biết thì trả `UNAVAILABLE`, và một từ khóa tiếp theo vẫn được xử lý.
- Publisher tìm kiếm phát hơn mười phần tử thì đầu ra chỉ chứa tối đa mười gợi ý.
- Subscriber hủy subscription thì pipeline ngừng phát dữ liệu cho subscriber đó.

Với trường hợp hủy truy vấn cũ, có thể dùng `TestPublisher` hoặc Publisher không hoàn tất để giữ request cũ đang hoạt động, phát từ khóa mới rồi xác minh request cũ đã nhận cancellation. Đây là kiểm thử có giá trị vì nó xác nhận hành vi của `switchMap`, thay vì chỉ kiểm tra kết quả cuối cùng.

## 9. Đưa ví dụ vào ứng dụng thực tế

Khi triển khai, cần xác định ranh giới giữa giao diện, kênh truyền và dịch vụ tìm kiếm:

- Giao diện chuyển các lần thay đổi nội dung thành sự kiện và hiển thị `SearchView`.
- Adapter WebSocket hoặc RSocket chuyển thông điệp đầu vào thành Publisher. Nó cũng chịu trách nhiệm hủy subscription khi phiên kết nối đóng.
- `SuggestionService` chứa logic chuẩn hóa, debounce, loại truy vấn trùng và chuyển sang Publisher tìm kiếm mới nhất.
- `CatalogSearch` truy cập repository hoặc dịch vụ bên ngoài bằng API reactive nếu có thể.
- Các lỗi nghiệp vụ được chuyển thành trạng thái phù hợp; lỗi không dự kiến cần được ghi log và xử lý ở ranh giới của ứng dụng.

Một ứng dụng dùng REST vẫn có thể áp dụng cùng nguyên tắc. Trình duyệt debounce các lần gõ, gửi request với từ khóa mới nhất và hủy request cũ khi có thể; endpoint Java nhận một từ khóa và trả `Mono<List<Suggestion>>`. Khi cần truyền liên tục cả chuỗi sự kiện qua một kết nối, WebSocket hoặc RSocket có thể cung cấp ranh giới Publisher phù hợp hơn.

Ví dụ tìm kiếm gợi ý cho thấy cách các phần của hệ sinh thái Java phối hợp: `Flux` biểu diễn các sự kiện nhập và luồng gợi ý, `Mono` biểu diễn một kết quả gom lại, toán tử mô tả biến đổi và thay thế truy vấn, scheduler cô lập mã chặn, cơ chế lỗi giữ cho luồng có thể tiếp tục, còn Reactive Streams cung cấp hợp đồng demand và cancellation giữa Publisher với Subscriber. Kiểm thử bằng StepVerifier giúp xác nhận pipeline theo thời gian và theo từng tín hiệu.

