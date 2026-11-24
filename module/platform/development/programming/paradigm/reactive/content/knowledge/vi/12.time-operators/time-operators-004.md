# debounce: chờ khoảng yên lặng trước khi phát giá trị

Trong một luồng sự kiện, nhiều giá trị có thể đến liên tiếp trong thời gian ngắn. Người dùng gõ từng ký tự vào ô tìm kiếm, kéo thanh trượt, thay đổi kích thước cửa sổ hoặc cập nhật một bộ lọc. Nếu mỗi thay đổi đều kích hoạt một truy vấn hoặc một lần tính toán tốn kém, ứng dụng có thể tạo ra nhiều công việc mà kết quả trung gian không còn cần thiết.

**Debounce** giải quyết tình huống đó bằng cách chờ một khoảng yên lặng sau mỗi giá trị. Mỗi giá trị mới đến trong khoảng chờ sẽ đặt lại bộ đếm thời gian. Chỉ giá trị mới nhất được phát khi không có giá trị tiếp theo xuất hiện trước khi khoảng chờ kết thúc. Cách này hữu ích khi ta quan tâm trạng thái cuối cùng sau một đợt thay đổi hơn là mọi bước trung gian.

Trong Project Reactor, `Flux.sampleTimeout` biểu diễn mẫu xử lý này bằng một publisher thời gian đi kèm cho từng phần tử. API `Flux` hiện hành mô tả toán tử này là phát giá trị mới nhất khi không có phần tử tiếp theo trong cửa sổ được publisher đi kèm xác định. Khi nguồn hoàn tất, phần tử cuối cùng đang chờ cũng được phát cùng tín hiệu hoàn tất. Vì vậy, khi viết code Reactor, hãy dùng `sampleTimeout` cho hành vi debounce thay vì giả định có phương thức `debounce(Duration)`.

## 1. Khoảng yên lặng hoạt động như thế nào?

Giả sử khoảng yên lặng được đặt là 300 mili giây. Khi một giá trị đến, bộ đếm 300 mili giây bắt đầu. Nếu giá trị khác đến trước khi bộ đếm kết thúc, bộ đếm cũ bị hủy và một bộ đếm mới bắt đầu từ giá trị mới nhất. Khi bộ đếm của giá trị cuối cùng kết thúc mà không có giá trị mới, giá trị đó được phát xuống downstream.

```text
Thời gian:       0      100    180                 480       780
Sự kiện vào:     --A-----B------C-------------------D---------|
                  |      |      |                   |
                  timer  timer  timer               timer
                  reset  reset  reset               chờ đủ 300 ms

Sự kiện ra:      ----------------C-------------------D---------|
```

Trong đợt đầu, A và B bị thay thế bởi các giá trị mới hơn trước khi khoảng chờ kết thúc. C được phát sau khi không có giá trị mới trong 300 mili giây. D cũng được phát sau khoảng yên lặng của chính nó. Nếu nguồn hoàn tất trong lúc giá trị cuối cùng vẫn đang chờ, `sampleTimeout` phát giá trị cuối đó khi hoàn tất.

Debounce thường được gọi là *trailing-edge debounce*: nó giữ giá trị cuối của một đợt thay đổi. Điều kiện phát không dựa vào số lượng phần tử mà dựa vào thời gian kể từ phần tử gần nhất.

## 2. Dùng sampleTimeout trong Reactor

Một ví dụ đơn giản là giảm số truy vấn tìm kiếm khi người dùng nhập liên tiếp:

```java
Duration quietPeriod = Duration.ofMillis(300);

Flux<String> debouncedQueries = queryChanges
    .map(String::trim)
    .sampleTimeout(query -> Mono.delay(quietPeriod));
```

Mỗi query tạo một `Mono.delay(quietPeriod)` làm publisher thời gian. Nếu một query mới đến trước khi publisher thời gian hiện tại phát tín hiệu, cửa sổ cũ không còn hợp lệ và giá trị cũ không được phát. Khi publisher thời gian của query mới kết thúc mà không có query tiếp theo, query đó được phát ra.

Để gọi dịch vụ tìm kiếm sau khi đã debounce, có thể nối pipeline như sau:

```java
Flux<SearchResult> results = queryChanges
    .map(String::trim)
    .sampleTimeout(query -> Mono.delay(Duration.ofMillis(300)))
    .distinctUntilChanged()
    .switchMap(query -> query.isBlank()
        ? Flux.empty()
        : searchService.search(query));
```

`sampleTimeout` giảm số query được đưa tới dịch vụ. `distinctUntilChanged` bỏ qua giá trị liên tiếp không đổi. `switchMap` chuyển sang publisher tìm kiếm mới khi query đã debounce mới xuất hiện; publisher tìm kiếm cũ đang hoạt động sẽ bị hủy theo khả năng cancellation của nguồn. Khi người dùng xóa hết nội dung, query rỗng vẫn đi qua bước debounce rồi `switchMap` trả `Flux.empty()`, đồng thời hủy lần tìm kiếm trước đó.

Debounce trì hoãn thời điểm phát chứ không làm thay đổi giá trị. Hãy chọn khoảng chờ theo trải nghiệm mong muốn: quá ngắn có thể vẫn tạo nhiều truy vấn; quá dài khiến giao diện phản hồi chậm sau khi người dùng ngừng thao tác.

## 3. Phân biệt debounce với sample và throttle

Các toán tử theo thời gian đều giảm số phần tử đầu ra, nhưng chúng trả lời những câu hỏi khác nhau:

| Cơ chế | Giá trị được giữ | Khi nào phát | Ví dụ sử dụng |
| --- | --- | --- | --- |
| Debounce (`sampleTimeout`) | Giá trị mới nhất trong một đợt liên tục | Sau khi không có giá trị mới trong khoảng yên lặng | Tìm kiếm sau khi người dùng ngừng gõ |
| `sample(Duration)` | Giá trị mới nhất trong mỗi cửa sổ lấy mẫu cố định | Theo nhịp thời gian định kỳ | Cập nhật biểu đồ theo chu kỳ |
| `sampleFirst(Duration)` | Giá trị đầu tiên trong mỗi cửa sổ | Ngay khi nhận giá trị đầu, rồi bỏ qua các giá trị trong cửa sổ | Giới hạn thao tác đầu tiên trong một khoảng |
| `delayElements(Duration)` | Mọi giá trị | Giữ nguyên tất cả, nhưng trì hoãn từng giá trị | Làm chậm tốc độ phát ra |

Ví dụ, `sample(Duration.ofSeconds(1))` có thể phát một giá trị mỗi giây nếu có giá trị mới trong cửa sổ. Nó không chờ một giây yên lặng sau mỗi sự kiện; các mốc lấy mẫu vẫn chạy theo chu kỳ cố định. `sampleFirst` giữ phần tử đầu tiên rồi bỏ qua các phần tử tiếp theo trong cửa sổ. Debounce thì liên tục đặt lại thời điểm phát khi có giá trị mới.

```text
Đầu vào:          --A-B-C------D-E----------F----|

Debounce:         --------C----------E----------F|
sample (chu kỳ):  -----C----------E----------F----|
sampleFirst:      --A------------D----------F----|
```

Sơ đồ minh họa sự khác nhau về ý tưởng; thời điểm cụ thể của `sample(Duration)` phụ thuộc mốc bắt đầu của scheduler và cửa sổ lấy mẫu. Không nên thay một toán tử bằng toán tử khác chỉ vì cả hai đều làm giảm số phần tử.

## 4. Debounce không phải timeout

`timeout` theo dõi việc nguồn có phát tín hiệu trong thời gian cho phép hay không. Nếu quá thời gian mà không có tín hiệu, pipeline timeout và thường kết thúc bằng lỗi hoặc chuyển sang publisher dự phòng. Debounce làm điều ngược lại về mục đích: nó chủ động chờ khoảng yên lặng để quyết định khi nào phát giá trị mới nhất.

| Câu hỏi | Toán tử phù hợp |
| --- | --- |
| Không có tín hiệu trong thời gian cho phép thì phải báo lỗi? | `timeout` |
| Có nhiều giá trị liên tiếp thì chỉ phát giá trị cuối sau khoảng yên lặng? | `sampleTimeout` |
| Muốn phát giá trị mới nhất theo nhịp đều đặn? | `sample(Duration)` |
| Muốn phát ngay giá trị đầu rồi bỏ qua các giá trị trong một khoảng? | `sampleFirst(Duration)` |

Không dùng debounce để phát hiện kết nối im lặng hoặc dịch vụ không phản hồi. Trường hợp đó cần `timeout`, heartbeat hoặc cơ chế giám sát phù hợp.

## 5. Chọn khoảng yên lặng và đơn vị thời gian

Khoảng debounce là một tham số nghiệp vụ. Với ô tìm kiếm, 200–400 mili giây thường là điểm bắt đầu để thử nghiệm; với thao tác kéo thanh trượt, có thể chọn khoảng ngắn hơn hoặc kết hợp một sự kiện kết thúc thao tác; với lưu tự động, khoảng chờ có thể dài hơn để tránh ghi dữ liệu sau mỗi lần gõ.

```java
Duration searchQuietPeriod = Duration.ofMillis(300);
Duration autosaveQuietPeriod = Duration.ofSeconds(2);

Flux<String> searchTerms = searchInput
    .sampleTimeout(value -> Mono.delay(searchQuietPeriod));

Flux<Document> documentsToSave = documentChanges
    .sampleTimeout(change -> Mono.delay(autosaveQuietPeriod));
```

Không có một giá trị phù hợp cho mọi nguồn. Hãy cân nhắc:

- Tần suất sự kiện trung bình và mức độ dồn dập trong một đợt.
- Chi phí của công việc downstream và giới hạn của dịch vụ được gọi.
- Độ trễ người dùng có thể chấp nhận sau khi dừng thao tác.
- Việc bỏ qua các trạng thái trung gian có an toàn với nghiệp vụ hay không.

Debounce chỉ phát khi đã có ít nhất một phần tử. Nếu nguồn hoàn tất mà chưa từng phát phần tử, kết quả vẫn rỗng. Nếu nguồn hoàn tất sau một phần tử đang chờ, `sampleTimeout` phát phần tử cuối cùng cùng với `onComplete`; vì thế một nguồn ngắn hữu hạn có thể phát giá trị cuối ngay khi hoàn tất thay vì chờ đủ toàn bộ khoảng debounce.

## 6. Scheduler quyết định bộ đếm thời gian chạy ở đâu

`Mono.delay` dùng scheduler thời gian mặc định của Reactor. Nếu cần kiểm soát scheduler, có thể truyền scheduler vào `Mono.delay`:

```java
Scheduler timer = Schedulers.parallel();
Duration quietPeriod = Duration.ofMillis(300);

Flux<String> debounced = queryChanges
    .sampleTimeout(value -> Mono.delay(quietPeriod, timer));
```

Scheduler ở đây phục vụ việc đo khoảng thời gian. Nó không tự động chuyển mọi xử lý downstream sang một thread khác theo ý muốn. Nếu cần chuyển công việc phía sau sang scheduler khác, dùng `publishOn` tại vị trí phù hợp; nếu cần điều khiển nơi subscription của nguồn bắt đầu, xem xét `subscribeOn`.

Không tạo scheduler mới cho từng sự kiện. Nếu ứng dụng tự tạo scheduler, cần quản lý và dispose nó theo lifecycle của ứng dụng. Với scheduler mặc định của Reactor, không cần tự đóng scheduler dùng chung.

Thời gian debounce là thời gian tương đối được đo bằng scheduler. Nó không phải cam kết rằng callback sẽ chạy chính xác tại mili giây thứ 300: tải CPU, độ trễ lập lịch và cách thread được phân bổ có thể làm thời điểm quan sát muộn hơn. Hãy dùng nó để gom sự kiện theo khoảng yên lặng, không dùng như đồng hồ thời gian thực có độ chính xác cứng.

## 7. Giới hạn và hệ quả của việc bỏ qua giá trị trung gian

Debounce là phép biến đổi có chủ đích loại bỏ phần tử. Nếu một đợt có 20 giá trị đến trong 200 mili giây và khoảng yên lặng là 300 mili giây, downstream thường chỉ nhận giá trị cuối cùng của đợt đó. Các giá trị trước đó không được lưu để phát lần lượt về sau.

Điều này phù hợp với trạng thái tìm kiếm, lựa chọn bộ lọc hoặc vị trí con trỏ khi chỉ trạng thái mới nhất có ý nghĩa. Nó không phù hợp khi mọi sự kiện đều phải được xử lý, ví dụ giao dịch tài chính, lệnh thanh toán, sự kiện kiểm toán hoặc thay đổi tồn kho. Với các luồng đó, hãy dùng hàng đợi, buffer, batch hoặc broker bền vững theo hợp đồng dữ liệu.

`sampleTimeout` có overload nhận `maxConcurrency` để giới hạn số publisher thời gian hoạt động đồng thời. Tuy nhiên, khi đạt giới hạn này, Reactor có thể bỏ qua phần tử mới cho tới khi có timeout kết thúc. Điều đó thay đổi hành vi lấy mẫu và có thể làm mất giá trị mới nhất mà ứng dụng kỳ vọng. Chỉ dùng overload này sau khi đã đánh giá tốc độ nguồn và chính sách bỏ phần tử; không xem nó là một cách đặt giới hạn bộ nhớ miễn phí.

Nếu payload giữ tài nguyên cần giải phóng khi bị loại bỏ, hãy xem xét discard hook phù hợp của Reactor để dọn tài nguyên. Không nên giữ tài nguyên bên ngoài trong payload rồi giả định mọi phần tử đều được subscriber nhận.

## 8. Kết hợp debounce với xử lý lỗi và hủy

Debounce không tự phục hồi lỗi. Nếu nguồn phát `onError`, lỗi được chuyển theo pipeline; nếu publisher thời gian gặp lỗi, pipeline cũng không thể coi cửa sổ đó là một lần chờ thành công. Có thể đặt xử lý lỗi ở vị trí phù hợp với phạm vi mong muốn:

```java
Flux<String> queries = queryChanges
    .sampleTimeout(value -> Mono.delay(Duration.ofMillis(300)))
    .onErrorResume(error -> {
        log.warn("Không xử lý được luồng nhập tìm kiếm", error);
        return Flux.empty();
    });
```

Đoạn mã trên chuyển lỗi của cả pipeline debounce thành hoàn tất rỗng. Nếu nghiệp vụ cần báo lỗi cho caller, hãy giữ tín hiệu lỗi hoặc chuyển thành lỗi miền nghiệp vụ thay vì âm thầm bỏ qua.

Khi downstream hủy subscription, Reactor hủy subscription tới nguồn và các publisher thời gian còn hoạt động theo khả năng của từng publisher. Nếu người dùng rời trang hoặc request kết thúc, điều này giúp tránh tiếp tục chờ timer và thực hiện công việc không còn cần thiết. Nếu downstream dùng `switchMap`, publisher xử lý truy vấn cũ cũng có thể bị hủy khi một query debounce mới xuất hiện.

## 9. Kiểm thử debounce bằng virtual time

Không cần chờ thật hàng trăm mili giây trong unit test. `StepVerifier.withVirtualTime` cho phép tiến đồng hồ ảo để kiểm tra thời điểm phát:

```java
StepVerifier.withVirtualTime(() ->
        Flux.concat(
            Flux.just("r", "re", "rea"),
            Mono.delay(Duration.ofMillis(400))
                .thenMany(Flux.just("react"))
        ).sampleTimeout(value -> Mono.delay(Duration.ofMillis(300)))
    )
    .thenAwait(Duration.ofMillis(300))
    .expectNext("rea")
    .thenAwait(Duration.ofMillis(100))
    .expectNext("react")
    .verifyComplete();
```

Ba giá trị đầu đến ngay tại thời điểm bắt đầu, nên `r` và `re` bị thay thế; `rea` được phát sau 300 mili giây yên lặng. Giá trị `react` đến ở mốc 400 mili giây. Nguồn hoàn tất ngay sau đó, nên giá trị cuối được phát cùng hoàn tất theo hành vi của `sampleTimeout`.

Khi kiểm thử, nên bao phủ thêm các trường hợp:

1. Nhiều phần tử đến trước khi timer kết thúc: chỉ phần tử cuối được phát.
2. Khoảng cách giữa hai phần tử lớn hơn quiet period: cả hai đều được phát.
3. Nguồn hoàn tất khi một phần tử còn chờ: phần tử cuối được phát khi hoàn tất.
4. Nguồn rỗng: không có phần tử nào được phát.
5. Nguồn lỗi hoặc downstream hủy: xác minh terminal signal và việc dừng công việc liên quan.

## 10. Chọn debounce khi trạng thái cuối quan trọng hơn lịch sử thay đổi

Hãy dùng debounce khi các sự kiện liên tiếp biểu diễn những phiên bản mới của cùng một ý định và công việc downstream chỉ cần phiên bản mới nhất sau khi người dùng hoặc nguồn ngừng thay đổi trong một khoảng thời gian. Trong Reactor, `sampleTimeout(value -> Mono.delay(quietPeriod))` là cách diễn đạt trực tiếp cho quy tắc này. Chọn khoảng chờ theo trải nghiệm và chi phí hệ thống, kết hợp `distinctUntilChanged` để bỏ giá trị lặp và `switchMap` khi cần chuyển sang công việc mới nhất.

Trước khi áp dụng, hãy xác nhận rằng bỏ các giá trị trung gian là an toàn. Debounce không làm chậm producer để xử lý đủ mọi phần tử và không thay thế backpressure hoặc lưu trữ bền vững. Khi mọi sự kiện đều có ý nghĩa, hãy giữ toàn bộ luồng và chọn chiến lược điều tiết khác. Khi chỉ trạng thái sau khoảng yên lặng mới quan trọng, debounce giúp giảm công việc dư thừa và giữ pipeline reactive gọn hơn.
