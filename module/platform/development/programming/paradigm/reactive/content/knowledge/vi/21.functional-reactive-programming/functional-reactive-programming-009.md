# Mô hình hóa giao diện phản ứng mà không đồng nhất FRP với bất đồng bộ

Một giao diện phản ứng thường thay đổi theo thao tác người dùng, dữ liệu mới, trạng thái tải và thời gian. Ta có thể viết mã để cập nhật từng thành phần giao diện mỗi khi một sự kiện xảy ra, nhưng cách đó dễ khiến trạng thái bị phân tán: một callback đổi nội dung, callback khác bật chỉ báo tải, còn callback thứ ba lại cập nhật thông báo lỗi. Khi các thay đổi đến gần nhau, giao diện có thể hiển thị một tổ hợp trạng thái không nhất quán.

Functional Reactive Programming (FRP) cung cấp một cách tư duy khác: mô hình hóa giá trị thay đổi theo thời gian và các sự kiện xảy ra tại những thời điểm cụ thể, rồi mô tả giao diện như kết quả được suy ra từ mô hình đó. FRP có thể sử dụng các thao tác bất đồng bộ, nhưng hai khái niệm không đồng nghĩa. Một thao tác có thể bất đồng bộ mà không được mô hình hóa theo FRP; ngược lại, một giá trị phản ứng có thể thay đổi đồng bộ khi một sự kiện mới được xử lý.

Bài học thuộc chương **Phản ứng hàm** của module **REACTIVE_PROGRAMMING**. Module tập trung vào tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Ta sẽ dùng các khái niệm FRP để thiết kế mô hình giao diện, sau đó dùng Reactor như một công cụ xử lý luồng sự kiện rời rạc. Cần nhận biết giới hạn của công cụ: **Flux** là Publisher phát chuỗi phần tử, không tự nó là một kiểu Behavior của FRP.

## FRP mô hình hóa điều gì?

FRP thường phân biệt hai khái niệm nền tảng:

- **Behavior** (còn gọi là Signal trong một số hệ thống): một giá trị có thể thay đổi theo thời gian. Ví dụ: nội dung ô tìm kiếm hiện tại, trạng thái đăng nhập, vị trí con trỏ hoặc trạng thái hiển thị của một nút.
- **Event**: một sự kiện xảy ra tại một thời điểm. Ví dụ: người dùng nhấn nút, nhận được kết quả tìm kiếm, bộ định thời phát tín hiệu hoặc kết nối bị mất.

Một Behavior trả lời câu hỏi “giá trị hiện tại là gì?”. Một Event trả lời câu hỏi “điều gì vừa xảy ra?”. Giao diện thường cần cả hai: sự kiện đầu vào làm thay đổi trạng thái, còn trạng thái hiện tại quyết định nội dung cần hiển thị.

Ví dụ với màn hình tìm kiếm:

| Thành phần | Cách nhìn theo FRP | Ví dụ |
|---|---|---|
| Nội dung truy vấn | Behavior | Chuỗi hiện tại trong ô tìm kiếm |
| Người dùng thay đổi truy vấn | Event | Một lần nhập hoặc xóa ký tự |
| Trạng thái đang tải | Behavior | **true** trong lúc chờ kết quả |
| Yêu cầu tìm kiếm được gửi | Event hoặc hiệu ứng phát sinh từ Event | Một lần gọi dịch vụ |
| Kết quả tìm kiếm hiện tại | Behavior | Danh sách kết quả đang được hiển thị |
| Người dùng chọn một kết quả | Event | Một lần nhấn vào dòng kết quả |

Behavior không nhất thiết là một biến Java được cập nhật thủ công. Trong một hệ thống FRP, nó có thể là một đối tượng phản ứng giữ giá trị hiện tại và mô tả quan hệ phụ thuộc với những giá trị khác. Khi một đầu vào thay đổi, các giá trị dẫn xuất được cập nhật theo mô hình thời gian của hệ thống.

## FRP không đồng nghĩa với bất đồng bộ

Hai trục này trả lời những câu hỏi khác nhau:

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| FRP | Giá trị và sự kiện thay đổi theo thời gian được mô hình hóa như thế nào? | Trạng thái nút được suy ra từ trạng thái biểu mẫu |
| Bất đồng bộ | Công việc hoàn tất vào thời điểm nào và thread nào có thể tiếp tục làm việc? | Gọi HTTP mà không chặn thread giao diện |
| Reactive Streams | Publisher và Subscriber trao đổi phần tử, demand và tín hiệu kết thúc ra sao? | **Flux** phát các bản cập nhật có backpressure |
| Lập trình hướng sự kiện | Thành phần nào phát và xử lý sự kiện? | Callback khi người dùng nhấn nút |

Một callback gọi HTTP bằng API bất đồng bộ là mã bất đồng bộ, nhưng chưa chắc là FRP. Nếu callback tự sửa nhiều biến giao diện ở nhiều nơi, mô hình thời gian và quan hệ phụ thuộc vẫn có thể bị ẩn trong mã mệnh lệnh.

Ngược lại, một biểu thức phản ứng có thể được đánh giá ngay trong cùng thread khi giá trị đầu vào thay đổi. Nó vẫn mô tả quan hệ giữa các giá trị theo thời gian dù không cần tạo thread mới hay chờ I/O.

FRP cũng không đồng nghĩa với việc dùng mọi API có tên reactive. Reactive Streams chuẩn hóa giao thức trao đổi phần tử và backpressure. Một pipeline Reactor có thể là thành phần của kiến trúc FRP, nhưng bản thân **Mono** và **Flux** không cung cấp đầy đủ ngữ nghĩa Behavior liên tục hoặc đồ thị phụ thuộc thời gian của mọi mô hình FRP.

## Mô hình giao diện bằng trạng thái bất biến

Một cách thực hành phù hợp trong Java là tập trung các giá trị giao diện vào một đối tượng trạng thái bất biến. Các thao tác người dùng và kết quả từ dịch vụ được biểu diễn thành Event. Một hàm reducer thuần nhận trạng thái hiện tại cùng một Event và trả về trạng thái mới.

Ví dụ, màn hình tìm kiếm có thể có mô hình:

~~~java
record SearchState(
    String query,
    boolean loading,
    List<SearchItem> results,
    String error
) {
    static SearchState initial() {
        return new SearchState("", false, List.of(), null);
    }

    SearchState reduce(SearchEvent event) {
        if (event instanceof QueryChanged changed) {
            return new SearchState(
                changed.query(), false, List.of(), null);
        }
        if (event instanceof SearchRequested requested) {
            return new SearchState(
                requested.query(), true, results, null);
        }
        if (event instanceof SearchSucceeded succeeded) {
            if (!succeeded.query().equals(query)) return this;
            return new SearchState(
                query, false, succeeded.items(), null);
        }
        if (event instanceof SearchFailed failed) {
            if (!failed.query().equals(query)) return this;
            return new SearchState(query, false, results, failed.message());
        }
        return this;
    }
}
~~~

Các kiểu Event có thể được định nghĩa bằng record:

~~~java
sealed interface SearchEvent
    permits QueryChanged, SearchRequested, SearchSucceeded, SearchFailed {}

record QueryChanged(String query) implements SearchEvent {}
record SearchRequested(String query) implements SearchEvent {}
record SearchSucceeded(String query, List<SearchItem> items)
    implements SearchEvent {}
record SearchFailed(String query, String message) implements SearchEvent {}
~~~

Ví dụ dùng record và sealed interface của Java 17 trở lên. Các danh sách đưa vào trạng thái nên được sao chép hoặc dùng cấu trúc bất biến để không bị thay đổi từ bên ngoài sau khi phát. Reducer không gọi HTTP, không ghi cơ sở dữ liệu và không sửa đối tượng trạng thái cũ. Nó chỉ tính trạng thái tiếp theo từ hai đầu vào.

Reducer cũng kiểm tra truy vấn trong kết quả. Nếu một phản hồi cũ đến sau khi người dùng đã nhập truy vấn mới, nó không được ghi đè trạng thái hiện tại. **switchMap** có thể gửi cancellation cho Publisher cũ, nhưng kiểm tra định danh truy vấn vẫn hữu ích khi API bên dưới không hủy được công việc đúng lúc.

Khi dùng reducer thuần, có thể kiểm thử các chuyển đổi trạng thái mà không cần khởi tạo giao diện, thread hoặc dịch vụ mạng. Đây là phần chức năng cốt lõi của mô hình.

## Dùng Flux để biểu diễn chuỗi Event và trạng thái dẫn xuất

Reactor có thể xử lý các Event rời rạc và tạo ra chuỗi snapshot trạng thái bằng **scan**:

~~~java
SearchState initial = SearchState.initial();

Flux<SearchState> states = allSearchEvents
    .scan(initial, SearchState::reduce)
    .startWith(initial)
    .distinctUntilChanged();
~~~

Ý nghĩa của pipeline:

1. **allSearchEvents** phát các Event từ giao diện và các nguồn khác.
2. **scan(initial, reducer)** áp dụng từng Event lên trạng thái trước đó và phát trạng thái mới.
3. **startWith(initial)** phát trạng thái ban đầu để giao diện có thể render ngay cả khi chưa có Event.
4. **distinctUntilChanged()** bỏ snapshot liên tiếp bằng nhau, tránh render lại khi mô hình không thay đổi.

Giao diện chỉ cần quan sát trạng thái và render:

~~~java
states
    .publishOn(uiScheduler)
    .subscribe(view::render);
~~~

**uiScheduler** đại diện cho scheduler do nền tảng giao diện cung cấp để cập nhật component trên đúng thread giao diện. Không nên giả định **Schedulers.parallel()** hoặc **Schedulers.boundedElastic()** là scheduler giao diện. Trong ứng dụng thực tế, adapter UI cần cung cấp scheduler phù hợp với framework đang dùng.

Đây là một cách tổ chức event-to-state hữu ích trong ứng dụng Java. Nó mô hình hóa chuỗi snapshot rời rạc bằng Reactor; nó không tự biến **Flux<SearchState>** thành Behavior liên tục. Nếu cần ngữ nghĩa Behavior thực thụ, cần một abstraction FRP hoặc lớp trạng thái có hợp đồng rõ ràng về giá trị hiện tại, thời điểm cập nhật và đăng ký quan sát.

## Tách hiệu ứng bất đồng bộ khỏi phép tính trạng thái

Một yêu cầu tìm kiếm cần gọi dịch vụ bên ngoài. Việc gọi dịch vụ là hiệu ứng bất đồng bộ; trạng thái giao diện là mô hình giá trị được cập nhật khi hiệu ứng bắt đầu và khi có kết quả.

Có thể biểu diễn quy trình bằng các Event:

~~~mermaid
flowchart TD
    A["Người dùng nhập truy vấn"] --> B["QueryChanged"]
    B --> C["Reducer tạo trạng thái mới"]
    C --> D["Phát SearchRequested"]
    D --> E["Gọi dịch vụ bất đồng bộ"]
    E --> F{"Kết quả"}
    F -->|"Thành công"| G["SearchSucceeded"]
    F -->|"Lỗi"| H["SearchFailed"]
    G --> C
    H --> C
    C --> I["Render giao diện từ trạng thái"]
~~~

Trong thiết kế này, reducer không tự gọi dịch vụ. Một thành phần điều phối hiệu ứng quan sát Event yêu cầu tìm kiếm, gọi dịch vụ và chuyển kết quả trở lại thành Event. Kết quả bất đồng bộ trở thành đầu vào mới của mô hình trạng thái.

Với Reactor, một luồng yêu cầu tìm kiếm có thể dùng **switchMap** để chỉ tiếp tục quan sát yêu cầu mới nhất:

~~~java
Flux<SearchEvent> searchOutcomes = searchRequests
    .switchMap(request ->
        searchService.search(request.query())
            .map(items -> (SearchEvent)
                new SearchSucceeded(request.query(), items))
            .onErrorResume(error ->
                Mono.just(new SearchFailed(
                    request.query(), error.getMessage()))
            )
    );
~~~

**switchMap** gửi cancellation đến Publisher con cũ khi yêu cầu mới đến. Cơ chế này phù hợp với tìm kiếm gợi ý, nơi kết quả của truy vấn trước thường đã lỗi thời. Nó không bảo đảm một HTTP server hoặc tác vụ blocking bên dưới dừng ngay lập tức, và không thể rollback side effect đã xảy ra.

Nếu ghép luồng yêu cầu từ UI với kết quả tìm kiếm, cần bảo đảm các nguồn được chia sẻ hoặc multicast đúng cách. Không nên vô tình subscribe hai lần vào một nguồn Event lạnh nếu việc đó khiến adapter đăng ký hai listener hoặc tạo hai lần đọc dữ liệu. Có thể dùng **publish** để chia sẻ một subscription trong phạm vi pipeline:

~~~java
Flux<SearchEvent> allSearchEvents = uiEvents.publish(sharedUiEvents -> {
    Flux<SearchEvent> outcomes = sharedUiEvents
        .ofType(SearchRequested.class)
        .switchMap(request ->
            searchService.search(request.query())
                .map(items -> (SearchEvent)
                    new SearchSucceeded(request.query(), items))
                .onErrorResume(error ->
                    Mono.just(new SearchFailed(
                        request.query(), error.getMessage()))
                )
        );

    return Flux.merge(sharedUiEvents, outcomes);
});
~~~

Đây là khung minh họa cho việc kết hợp Event giao diện và Event kết quả. Ứng dụng cần định nghĩa đầy đủ cách tạo **uiEvents** và chính sách lỗi. Khi nhiều yêu cầu có thể hoàn tất không theo thứ tự, nên đưa mã định danh yêu cầu vào Event và reducer để bỏ qua kết quả cũ nếu nghiệp vụ yêu cầu.

## Giữ tính nhất quán khi nhiều giá trị cùng phụ thuộc một sự kiện

Một giao diện có thể có nhiều giá trị dẫn xuất từ cùng một trạng thái:

- Nút tìm kiếm bật hay tắt.
- Chỉ báo tải có hiển thị hay không.
- Danh sách kết quả nào được trình bày.
- Thông báo lỗi nào được hiển thị.

Nếu cập nhật từng giá trị trong những callback riêng biệt, giao diện có thể quan sát trạng thái trung gian không nhất quán. Ví dụ, danh sách mới đã xuất hiện nhưng chỉ báo tải vẫn bật, hoặc truy vấn mới đã hiển thị trong khi kết quả cũ vẫn được xem là kết quả hiện hành.

Hãy tính các giá trị dẫn xuất từ cùng một snapshot:

~~~java
record SearchViewModel(
    String queryText,
    boolean searchEnabled,
    boolean showSpinner,
    List<SearchItem> visibleItems,
    String errorMessage
) {
    static SearchViewModel from(SearchState state) {
        return new SearchViewModel(
            state.query(),
            !state.query().isBlank(),
            state.loading(),
            state.results(),
            state.error()
        );
    }
}
~~~

Sau đó, tạo một ViewModel cho mỗi **SearchState** và render như một đơn vị. Khi một Event được xử lý, tất cả giá trị liên quan được suy ra từ cùng trạng thái mới. Cách này giảm nguy cơ giao diện hiển thị tổ hợp giá trị đến từ những thời điểm khác nhau.

Trong FRP, vấn đề cập nhật không nhất quán giữa các giá trị phụ thuộc thường được thảo luận dưới khái niệm **glitch**. Một hệ thống FRP có ngữ nghĩa cập nhật và đồng bộ phụ thuộc để tránh quan sát các tổ hợp trung gian không hợp lệ. Với mô hình reducer và snapshot bất biến, ứng dụng đạt được mục tiêu tương tự ở ranh giới trạng thái: downstream nhận một đối tượng trạng thái hoàn chỉnh cho mỗi bước chuyển.

## Xử lý thời gian mà không nhầm với bất đồng bộ

Thời gian là một phần của mô hình phản ứng. Ví dụ, giao diện có thể hiển thị thời lượng đã trôi qua, trạng thái phiên đăng nhập hoặc giá trị mới nhất của cảm biến. Có thể mô hình hóa các mốc thời gian như Event và suy ra trạng thái hiện tại từ chúng.

**Flux.interval** phát một chuỗi tick theo khoảng thời gian:

~~~java
Flux<Long> clockTicks = Flux.interval(Duration.ofSeconds(1));
~~~

Tick là Event. Từ tick và mốc bắt đầu, ứng dụng có thể suy ra thời lượng đang hiển thị. Việc scheduler phát tick bất đồng bộ là một chi tiết thực thi; ý nghĩa FRP nằm ở việc mô hình hóa giá trị thời gian thay đổi và quan hệ của nó với trạng thái giao diện.

Tương tự, **debounce** là một toán tử thời gian trên luồng Event:

~~~java
Flux<String> settledQueries = queryChanges
    .map(String::trim)
    .debounce(Duration.ofMillis(250))
    .distinctUntilChanged();
~~~

Toán tử này chỉ phát truy vấn sau một khoảng không có Event mới. Nó hữu ích để giảm số yêu cầu tìm kiếm, nhưng không phải định nghĩa của FRP. Một mô hình FRP vẫn có thể mô tả nội dung truy vấn thay đổi mà không cần debounce hoặc không cần thực hiện bất kỳ I/O bất đồng bộ nào.

## Kiểm thử reducer và luồng trạng thái

Vì reducer là hàm thuần, hãy kiểm thử trực tiếp các chuyển đổi quan trọng:

~~~java
SearchState initial = SearchState.initial();
SearchState loading = initial.reduce(new SearchRequested("reactor"));

assertTrue(loading.loading());
assertEquals("reactor", loading.query());

SearchState loaded = loading.reduce(
    new SearchSucceeded("reactor", List.of(itemA, itemB))
);

assertFalse(loaded.loading());
assertEquals(2, loaded.results().size());
assertNull(loaded.error());
~~~

Có thể kiểm thử chuỗi trạng thái bằng **StepVerifier** và một nguồn Event điều khiển được:

~~~java
TestPublisher<SearchEvent> events = TestPublisher.create();
SearchState initial = SearchState.initial();

Flux<SearchState> states = events.flux()
    .scan(initial, SearchState::reduce)
    .startWith(initial);

StepVerifier.create(states)
    .expectNext(initial)
    .then(() -> events.next(new QueryChanged("reactor")))
    .expectNextMatches(state ->
        state.query().equals("reactor") && !state.loading())
    .then(() -> events.next(new SearchRequested("reactor")))
    .expectNextMatches(SearchState::loading)
    .then(() -> events.complete())
    .verifyComplete();
~~~

Kiểm thử này xác nhận trạng thái ban đầu và hai bước chuyển do Event gây ra. Có thể bổ sung trường hợp thành công, lỗi, truy vấn mới đến khi yêu cầu cũ đang chạy và cancellation của Publisher con. Kiểm thử reducer riêng giúp phân biệt lỗi mô hình trạng thái với lỗi thực thi bất đồng bộ.

## Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao không chính xác | Cách nhìn phù hợp |
|---|---|---|
| FRP chỉ là gọi API bất đồng bộ | Bất đồng bộ nói về thời điểm hoàn tất và cách chờ; FRP nói về mô hình giá trị và sự kiện theo thời gian | Tách mô hình trạng thái khỏi adapter I/O |
| Mọi **Flux** đều là Behavior | **Flux** phát phần tử theo subscription và có thể không lưu giá trị hiện tại cho người đăng ký muộn | Xác định rõ Event stream và abstraction giữ giá trị hiện tại |
| Callback là FRP | Callback có thể cập nhật trạng thái mệnh lệnh và phân tán | Dùng Event rõ ràng, reducer thuần và trạng thái dẫn xuất |
| **switchMap** làm tác vụ cũ chắc chắn dừng | Cancellation là tín hiệu hợp tác, thư viện bên dưới có thể không hủy được công việc | Thiết kế API có khả năng hủy và xử lý side effect an toàn |
| Mỗi component tự giữ một bản trạng thái | Các giá trị có thể lệch thời điểm và tạo giao diện không nhất quán | Suy ra ViewModel từ một snapshot bất biến |
| Có scheduler là đã có FRP | Scheduler điều khiển thread thực thi, không định nghĩa quan hệ giá trị theo thời gian | Phân biệt ngữ nghĩa mô hình và cơ chế thực thi |

## Nguyên tắc thiết kế giao diện phản ứng

Khi mô hình hóa một giao diện theo tư duy FRP, hãy xác định:

1. Giá trị nào là trạng thái hiện tại cần quan sát liên tục?
2. Những sự kiện nào làm trạng thái thay đổi?
3. Giá trị hiển thị nào có thể được suy ra từ một snapshot trạng thái?
4. Hiệu ứng bất đồng bộ nào cần phát sinh từ Event và kết quả của nó quay lại mô hình bằng cách nào?
5. Nếu Event mới làm kết quả cũ lỗi thời, chính sách cancellation và nhận diện kết quả cũ là gì?
6. Các giá trị phụ thuộc có được render từ cùng một trạng thái nhất quán không?
7. Có thể kiểm thử reducer độc lập và kiểm thử chuỗi Event bằng **StepVerifier** không?

FRP giúp mô tả giao diện như một mô hình giá trị và sự kiện thay đổi theo thời gian. Bất đồng bộ là một cơ chế thực thi có thể tham gia vào mô hình đó, còn Reactive Streams cung cấp giao thức để truyền chuỗi phần tử và kiểm soát demand. Khi tách rõ ba khía cạnh, ứng dụng Java có thể tổ chức trạng thái giao diện dễ hiểu, xử lý các hiệu ứng I/O có kiểm soát và kiểm thử được từng bước chuyển trạng thái.
