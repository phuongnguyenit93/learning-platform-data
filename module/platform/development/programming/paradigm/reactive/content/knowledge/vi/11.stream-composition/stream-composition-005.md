# switchMap: chuyển sang nguồn mới và hủy nguồn trước

Trong một pipeline reactive, mỗi phần tử của luồng đầu vào có thể khởi tạo một luồng con bất đồng bộ. Khi phần tử đầu vào mới xuất hiện, đôi khi kết quả của luồng con cũ không còn phù hợp nữa. `switchMap` giải quyết trường hợp này bằng cách chuyển sang Publisher con mới nhất và gửi tín hiệu hủy tới Publisher con trước đó. Các phần tử đến từ luồng con cũ sau khi đã chuyển đổi sẽ không còn được chuyển tiếp như kết quả hiện hành.

Bài học thuộc chương **Ghép luồng** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trong Project Reactor, `switchMap` đặc biệt hữu ích khi đầu vào mới làm cho công việc đang chạy trở nên lỗi thời, chẳng hạn tìm kiếm gợi ý theo từng lần người dùng nhập.

## Cách switchMap chuyển đổi giữa các Publisher con

`switchMap` nhận một hàm biến đổi mỗi phần tử upstream thành một Publisher. Khi nhận phần tử đầu tiên, toán tử gọi hàm biến đổi và đăng ký vào Publisher con tương ứng. Khi upstream phát phần tử tiếp theo, `switchMap` hủy subscription của Publisher con hiện tại rồi đăng ký Publisher con mới.

Ví dụ, luồng truy vấn tìm kiếm có thể phát lần lượt các từ khóa `ja`, `jav`, `java`. Mỗi từ khóa tạo ra một yêu cầu tìm kiếm bất đồng bộ:

~~~mermaid
sequenceDiagram
    participant Q as Luồng truy vấn
    participant S as switchMap
    participant A as Tìm kiếm "ja"
    participant B as Tìm kiếm "jav"
    participant C as Tìm kiếm "java"
    Q->>S: "ja"
    S->>A: subscribe
    Q->>S: "jav"
    S--xA: cancel
    S->>B: subscribe
    Q->>S: "java"
    S--xB: cancel
    S->>C: subscribe
    C-->>S: Kết quả "java"
    S-->>Q: Chuyển kết quả mới nhất
~~~

Sau khi chuyển sang tìm kiếm `jav`, kết quả của yêu cầu `ja` không còn là kết quả được chọn. Khi `java` xuất hiện, yêu cầu `jav` cũng bị hủy. Subscriber downstream chỉ nhận kết quả từ Publisher con hiện hành, theo thứ tự tín hiệu mà toán tử xử lý.

Ví dụ đơn giản với Reactor:

~~~java
Flux<SearchResult> results = queries
    .switchMap(query -> searchService.search(query));
~~~

Nếu `searchService.search` trả về `Mono<SearchResult>`, `switchMap` vẫn dùng được; mỗi Publisher con chỉ phát tối đa một kết quả. Nếu nó trả về `Flux<SearchResult>`, toán tử chuyển tiếp các kết quả của luồng con đang hiện hành cho đến khi có truy vấn mới hoặc luồng con kết thúc.

## Tình huống điển hình: tìm kiếm gợi ý khi người dùng nhập

Trong giao diện tìm kiếm, người dùng có thể nhập nhanh nhiều ký tự. Mỗi lần thay đổi truy vấn tạo một sự kiện mới, nhưng ứng dụng thường chỉ cần kết quả cho truy vấn mới nhất. Nếu dùng `flatMap`, nhiều yêu cầu có thể chạy đồng thời và phản hồi chậm của truy vấn cũ có thể đến sau phản hồi mới.

`switchMap` kết hợp với `debounce` và `distinctUntilChanged` tạo thành một pipeline phù hợp:

~~~java
Flux<SearchResult> suggestions = queryChanges
    .map(String::trim)
    .filter(query -> !query.isEmpty())
    .debounce(Duration.ofMillis(250))
    .distinctUntilChanged()
    .switchMap(query -> searchService.search(query));
~~~

Các toán tử trước `switchMap` giảm số lần khởi chạy công việc:

- `map(String::trim)` chuẩn hóa khoảng trắng đầu và cuối.
- `filter` bỏ truy vấn rỗng.
- `debounce` chỉ phát truy vấn sau một khoảng yên lặng, giúp tránh gọi dịch vụ cho từng phím được nhấn liên tiếp.
- `distinctUntilChanged` bỏ truy vấn giống hệt truy vấn ngay trước đó.
- `switchMap` chuyển sang yêu cầu tìm kiếm mới nhất và hủy yêu cầu cũ.

`debounce` và `switchMap` giải quyết hai vấn đề khác nhau. `debounce` quyết định khi nào một truy vấn đủ ổn định để được phát. `switchMap` quyết định Publisher con nào còn được quan sát khi có truy vấn mới. Dùng `switchMap` không tự tạo khoảng chờ; nếu mọi thay đổi đầu vào đều cần khởi chạy công việc ngay, có thể bỏ `debounce`.

Một phương thức dịch vụ được dùng trong pipeline nên trả về Publisher lazy, nghĩa là lời gọi I/O thực sự chỉ bắt đầu khi Publisher được subscribe. Nếu phương thức thực hiện blocking I/O ngay khi được gọi, việc đặt nó trong lambda của `switchMap` không tự chuyển thao tác đó sang thread phù hợp. Hãy chuyển adapter blocking thành `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` tại ranh giới tích hợp.

## switchMap khác flatMap và concatMap như thế nào?

Ba toán tử đều biến đổi phần tử upstream thành Publisher con, nhưng chính sách ghép luồng khác nhau:

| Toán tử | Khi phần tử upstream mới đến | Kết quả downstream |
|---|---|---|
| `flatMap` | Có thể đăng ký nhiều Publisher con đồng thời | Nhận kết quả từ các Publisher con theo thời điểm chúng phát; thứ tự giữa các luồng con không được bảo toàn |
| `concatMap` | Chờ Publisher con hiện tại hoàn tất rồi mới đăng ký Publisher con kế tiếp | Giữ thứ tự theo phần tử upstream |
| `switchMap` | Hủy Publisher con hiện tại và chuyển sang Publisher con mới | Chỉ tiếp tục nhận kết quả từ Publisher con mới nhất |

Chọn toán tử dựa trên ý nghĩa của công việc:

- Dùng `flatMap` khi cần xử lý nhiều yêu cầu độc lập đồng thời và chấp nhận kết quả về không theo thứ tự đầu vào.
- Dùng `concatMap` khi mọi công việc phải được thực hiện theo thứ tự và không được bỏ qua phần tử trước.
- Dùng `switchMap` khi đầu vào mới khiến kết quả của công việc trước trở nên lỗi thời.

Ví dụ, tìm kiếm gợi ý thường phù hợp với `switchMap`, còn ghi nhận tuần tự các giao dịch thường cần `concatMap` hoặc một cơ chế xử lý bền vững phù hợp. Không nên thay `concatMap` bằng `switchMap` chỉ để giảm độ trễ nếu mỗi lệnh đều phải được thực hiện.

## Hủy subscription có ý nghĩa gì?

Khi `switchMap` chuyển sang Publisher con mới, nó gửi tín hiệu `cancel` qua subscription của Publisher con cũ. Đây là một phần của hợp đồng Reactive Streams: Subscriber có thể hủy việc tiêu thụ để báo rằng nó không còn quan tâm đến các tín hiệu tiếp theo.

Hủy subscription có thể giúp tiết kiệm tài nguyên:

- Một HTTP client reactive có thể hủy request đang chờ hoặc đóng kết nối theo khả năng của implementation.
- Một Publisher dựa trên timer có thể dừng lịch phát.
- Một pipeline đọc dữ liệu có thể đóng tài nguyên khi nhận biết cancellation.
- Một tác vụ được thiết kế hợp tác có thể kiểm tra trạng thái hủy và dừng tính toán.

Tuy nhiên, `cancel` là tín hiệu yêu cầu dừng, không phải bảo đảm mọi công việc bên dưới đã bị dừng tức thì. Một API blocking hoặc thư viện bên ngoài có thể không hỗ trợ hủy. Nếu side effect đã được gửi tới hệ thống khác, cancellation cũng không tự hoàn tác side effect đó.

Ví dụ, nếu một yêu cầu thanh toán đã được gửi đến ngân hàng, việc Subscriber hủy Publisher không có nghĩa giao dịch đã bị rollback. Tương tự, `switchMap` không phải cơ chế hủy giao dịch cơ sở dữ liệu hay bảo đảm một lệnh cũ chưa được thực hiện.

Do đó, chỉ dùng `switchMap` cho công việc mà kết quả cũ có thể bỏ qua và thao tác có thể chịu được việc bị hủy hoặc tiếp tục chạy ngoài ý muốn. Với side effect quan trọng, cần thiết kế idempotency key, cơ chế xác nhận, trạng thái giao dịch và khả năng đối soát riêng.

## Xử lý lỗi bên trong Publisher con

Một Publisher con có thể kết thúc bằng `onError`. Vị trí đặt toán tử xử lý lỗi ảnh hưởng đến việc luồng đầu vào có tiếp tục xử lý các phần tử sau đó hay không.

Nếu xử lý lỗi bên trong lambda của `switchMap`, lỗi của một yêu cầu có thể được chuyển thành kết quả thay thế hoặc luồng rỗng, trong khi luồng truy vấn bên ngoài vẫn tiếp tục:

~~~java
Flux<SearchResult> suggestions = queryChanges
    .filter(query -> !query.isBlank())
    .switchMap(query ->
        searchService.search(query)
            .onErrorResume(SearchUnavailableException.class, error -> {
                metrics.recordSearchFailure(query);
                return Flux.empty();
            })
    );
~~~

Ở đây, lỗi `SearchUnavailableException` của một lần tìm kiếm được xử lý trong Publisher con. `switchMap` có thể tiếp tục nhận truy vấn tiếp theo từ `queryChanges`.

Nếu đặt `onErrorResume` sau `switchMap`, lỗi đã thoát khỏi Publisher con và trở thành lỗi của pipeline ghép:

~~~java
Flux<SearchResult> suggestions = queryChanges
    .switchMap(query -> searchService.search(query))
    .onErrorResume(error -> fallbackSearchResults());
~~~

Trong trường hợp này, lỗi có thể kết thúc luồng truy vấn gốc và chuyển toàn bộ pipeline sang Publisher dự phòng. Cách xử lý phù hợp hay không tùy vào yêu cầu: một lần tìm kiếm thất bại có nên ảnh hưởng đến các truy vấn tiếp theo hay không.

Không nên mặc định chuyển mọi lỗi thành `Flux.empty()` nếu giao diện cần phân biệt “không tìm thấy kết quả” với “dịch vụ tìm kiếm gặp sự cố”. Khi hai trạng thái có ý nghĩa khác nhau, hãy phát một kiểu kết quả miền tường minh, chẳng hạn `SearchState.Success`, `SearchState.Empty` và `SearchState.Failed`.

## Hành vi khi luồng ngoài kết thúc

Khi Publisher ngoài phát phần tử mới, Publisher con hiện tại bị hủy và Publisher con mới được đăng ký. Nếu Publisher ngoài hoàn tất bình thường, `switchMap` vẫn cho Publisher con hiện hành cơ hội phát nốt và hoàn tất; sau khi luồng con đó hoàn tất, pipeline ghép mới hoàn tất. Nếu Publisher ngoài kết thúc bằng lỗi, pipeline kết thúc bằng lỗi và Publisher con đang hoạt động bị hủy.

Hành vi này quan trọng khi nguồn ngoài là một luồng sự kiện sống lâu, chẳng hạn truy vấn giao diện hoặc luồng thay đổi cấu hình. Khi nguồn ngoài hoàn tất, kết quả cuối của Publisher con đang hoạt động vẫn có thể được phát trước khi pipeline hoàn tất.

## Kiểm thử việc chuyển nguồn và hủy nguồn cũ

Có thể dùng `TestPublisher` để kiểm soát từng Publisher con và kiểm tra rằng subscription cũ bị hủy khi đầu vào mới xuất hiện:

~~~java
TestPublisher<String> queries = TestPublisher.create();
TestPublisher<Integer> firstSearch = TestPublisher.create();
TestPublisher<Integer> secondSearch = TestPublisher.create();

Flux<Integer> results = queries.flux()
    .switchMap(query ->
        query.equals("java")
            ? firstSearch.flux()
            : secondSearch.flux()
    );

StepVerifier.create(results)
    .then(() -> queries.next("java"))
    .then(() -> firstSearch.next(1))
    .expectNext(1)
    .then(() -> queries.next("reactor"))
    .then(() -> firstSearch.assertCancelled())
    .then(() -> secondSearch.next(2))
    .expectNext(2)
    .thenCancel()
    .verify();
~~~

Kiểm thử xác nhận các điểm sau:

1. Truy vấn đầu tiên đăng ký vào `firstSearch`.
2. Kết quả `1` từ Publisher con đầu tiên được chuyển tiếp khi nó còn hiện hành.
3. Truy vấn mới khiến `switchMap` hủy `firstSearch` và đăng ký `secondSearch`.
4. Kết quả `2` từ Publisher con mới được chuyển tiếp.

`assertCancelled()` kiểm tra Publisher con cũ đã nhận tín hiệu hủy. Đây là kiểm tra quan trọng vì chỉ xác nhận kết quả cuối cùng chưa đủ chứng minh công việc cũ đã được yêu cầu dừng.

Một kiểm thử khác có thể xác nhận lỗi bên trong Publisher con không làm dừng luồng truy vấn khi lỗi đã được xử lý tại đúng vị trí:

~~~java
Flux<String> queries = Flux.just("first", "second");

Flux<String> results = queries.switchMap(query -> {
    if (query.equals("first")) {
        return Mono.<String>error(new IllegalStateException("temporary"))
            .onErrorResume(error -> Mono.empty());
    }
    return Mono.just("result for second");
});

StepVerifier.create(results)
    .expectNext("result for second")
    .verifyComplete();
~~~

Publisher con của truy vấn đầu tiên phát lỗi nhưng xử lý lỗi thành luồng rỗng. Truy vấn thứ hai vẫn được xử lý và phát kết quả. Nếu bỏ `onErrorResume` bên trong, lỗi có thể kết thúc pipeline ghép trước khi truy vấn thứ hai được xử lý.

## Những trường hợp không nên dùng switchMap

`switchMap` rất hữu ích khi công việc mới thay thế công việc cũ, nhưng không phù hợp với mọi luồng bất đồng bộ.

| Nhu cầu | Lựa chọn thường phù hợp hơn | Lý do |
|---|---|---|
| Phải xử lý mọi lệnh theo thứ tự | `concatMap` | Chờ từng Publisher con hoàn tất |
| Muốn chạy nhiều yêu cầu độc lập đồng thời | `flatMap` | Cho phép nhiều Publisher con hoạt động |
| Cần kết quả từ truy vấn mới nhất | `switchMap` | Hủy subscription cũ khi có truy vấn mới |
| Cần hủy tác vụ nhưng vẫn bảo đảm side effect được đối soát | Thiết kế cancellation và giao dịch riêng | Hủy reactive không rollback side effect |
| Nguồn blocking không hỗ trợ interruption/cancel | Adapter có giới hạn concurrency và chính sách tài nguyên riêng | Tín hiệu hủy không bảo đảm dừng lời gọi blocking |

Một lỗi thiết kế thường gặp là dùng `switchMap` cho chuỗi lệnh ghi dữ liệu vì muốn chỉ giữ công việc cuối cùng. Nếu các lệnh trước đã tạo side effect hoặc bắt buộc phải được lưu, chuyển sang lệnh mới không làm cho các lệnh cũ biến mất khỏi hệ thống. Hãy chọn toán tử theo hợp đồng nghiệp vụ của dữ liệu.

## Nguyên tắc áp dụng

Trước khi dùng `switchMap`, hãy xác định:

1. Một phần tử đầu vào mới có làm cho kết quả của Publisher con cũ trở nên lỗi thời không?
2. Publisher con có hỗ trợ cancellation và giải phóng tài nguyên khi bị hủy không?
3. Nếu công việc cũ đã tạo side effect, ứng dụng có cách xử lý hoặc đối soát không?
4. Lỗi của một Publisher con có nên ảnh hưởng đến luồng đầu vào và các lần xử lý tiếp theo không?
5. Có cần `debounce` để giảm số Publisher con được khởi chạy hay không?
6. Kiểm thử có xác nhận được cả kết quả mới nhất lẫn tín hiệu hủy của Publisher con cũ không?

`switchMap` thể hiện chính sách “chỉ quan tâm đến nguồn con mới nhất”. Nó rất phù hợp với tìm kiếm tương tác, tải chi tiết theo lựa chọn hiện tại hoặc cập nhật dữ liệu phụ thuộc vào trạng thái mới. Khi hiểu rõ cancellation, lỗi và side effect, ta có thể dùng toán tử này để giữ cho pipeline reactive phản ánh đúng trạng thái mà người dùng đang quan tâm.
