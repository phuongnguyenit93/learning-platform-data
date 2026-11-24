# Nguồn không tuân thủ hợp đồng và hệ quả cho bên tiêu thụ

Trong Reactive Streams, Publisher và Subscriber phối hợp qua một hợp đồng tín hiệu và nhu cầu dữ liệu. Hợp đồng này giúp các thành phần được viết độc lập vẫn có thể nối thành một pipeline: Subscriber yêu cầu số phần tử nó sẵn sàng nhận, Publisher phát dữ liệu theo nhu cầu đó, rồi kết thúc bằng hoàn tất hoặc lỗi. Nếu một nguồn không tuân thủ hợp đồng, các toán tử downstream có thể nhận dữ liệu sai nhịp, tín hiệu sai thứ tự hoặc trạng thái kết thúc không hợp lệ. Hậu quả có thể xuất hiện dưới dạng mất dữ liệu, xử lý trùng, lỗi khó truy vết, treo pipeline hoặc cạn tài nguyên.

Chủ đề này thuộc chương **Hợp đồng tín hiệu** của REACTIVE_PROGRAMMING. Module tập trung vào tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; sau đó thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Hiểu cách nhận diện nguồn vi phạm hợp đồng giúp ta đánh giá đúng độ tin cậy của adapter, thư viện tích hợp và Publisher tự triển khai.

## Hợp đồng tồn tại để bảo vệ bên tiêu thụ

Một Subscriber không cần biết Publisher dùng socket, callback, hàng đợi, luồng riêng hay bộ đếm thời gian để tạo dữ liệu. Subscriber chỉ dựa vào các quy tắc giao tiếp đã thống nhất:

- Publisher gọi `onSubscribe` trước các tín hiệu khác và cung cấp một `Subscription` để Subscriber điều khiển nhu cầu hoặc hủy.
- Subscriber gọi `request(n)` để yêu cầu tối đa `n` phần tử bổ sung; nhu cầu tích lũy quyết định số `onNext` Publisher được phép phát.
- Publisher phát các tín hiệu tuần tự cho một subscription. Các tín hiệu không được gọi chồng lấn theo cách làm mất quan hệ thứ tự.
- Publisher kết thúc bằng tối đa một tín hiệu kết thúc: `onComplete` hoặc `onError`. Sau tín hiệu kết thúc, không được phát thêm `onNext` hay một tín hiệu kết thúc khác.
- Phần tử `onNext` không được là `null`; lỗi được truyền qua `onError` phải là một đối tượng lỗi hợp lệ.
- Khi Subscriber gọi `cancel`, Publisher phải dừng phát dữ liệu cho subscription đó sau khi xử lý các tín hiệu đang diễn ra theo cách phù hợp với hợp đồng.

Đây là những quy tắc cốt lõi để hiểu các ví dụ trong bài. Reactive Streams còn quy định chi tiết về tính an toàn luồng và hành vi của `request`/`cancel`. Khi triển khai Publisher, cần đối chiếu đầy đủ đặc tả thay vì chỉ mô phỏng các callback nhìn thấy trong một ví dụ đơn giản.

### Nhu cầu là giới hạn của lượng dữ liệu được phát

Giả sử Subscriber chỉ yêu cầu một phần tử:

```text
Subscriber                 Publisher
    |                          |
    |------ request(1) ------->|
    |<------- onNext(A) -------|
    |                          |  Không được tự phát B
```

Publisher có thể phát ít hơn số phần tử được yêu cầu, ví dụ phát một phần tử rồi hoàn tất. Nhưng nếu nhu cầu hiện tại chỉ là một, Publisher không được phát hai phần tử. `request(n)` là số phần tử bổ sung mà Subscriber cho phép phát, không phải gợi ý tùy chọn để Publisher bỏ qua khi nguồn đang có nhiều dữ liệu.

Khi `request` nhận giá trị không dương, đó là yêu cầu không hợp lệ theo Reactive Streams. Publisher tuân thủ đặc tả phải báo lỗi cho subscription thay vì coi số âm hoặc số không là nhu cầu hợp lệ. Nhu cầu có thể được gọi nhiều lần; Publisher cần tính đúng tổng nhu cầu còn lại và không phát vượt quá giới hạn đó.

## Những dạng vi phạm thường gặp

Các nguồn dễ gây vi phạm thường nằm ở ranh giới tích hợp: adapter từ thư viện callback, wrapper quanh API cũ, Publisher tự viết, hoặc cầu nối giữa event bus và Reactor. Các Publisher và toán tử chuẩn trong Reactor được xây dựng để tuân thủ hợp đồng; lỗi thường xuất hiện khi mã tích hợp tự quản lý callback, luồng và hàng đợi.

| Vi phạm | Biểu hiện | Hệ quả với Subscriber |
|---|---|---|
| Phát vượt nhu cầu | Subscriber chỉ request một nhưng nhận nhiều `onNext` | Hỏng giả định backpressure; hàng đợi hoặc bộ đệm downstream có thể tăng, dữ liệu có thể bị loại bỏ hoặc lỗi phát sinh tùy adapter |
| Phát tín hiệu đồng thời | Nhiều luồng cùng gọi `onNext` cho một subscription mà không tuần tự hóa | Callback có thể chạy chồng lấn, trạng thái dùng chung bị race, thứ tự quan sát không còn đáng tin cậy |
| Gọi `onSubscribe` sai | Gọi nhiều lần hoặc phát `onNext` trước khi gọi `onSubscribe` | Subscriber có thể không quản lý được subscription, request hoặc cancel; nguồn có thể tạo đăng ký trùng |
| Kết thúc sai | Gọi cả `onComplete` và `onError`, gọi kết thúc nhiều lần, hoặc tiếp tục `onNext` sau khi kết thúc | Downstream nhận tín hiệu ngoài giao thức; lỗi đến muộn có thể bị bỏ hoặc ghi nhận như lỗi bị drop |
| Phát `null` | Gọi `onNext(null)` | Vi phạm hợp đồng; thường dẫn đến `NullPointerException` tại ranh giới kiểm tra hoặc trong xử lý |
| Không tôn trọng hủy | Tiếp tục tạo và gửi dữ liệu sau khi Subscriber cancel | Tốn CPU, kết nối và bộ nhớ; callback hoặc side effect không còn cần thiết vẫn tiếp tục |
| Không bao giờ kết thúc ngoài dự kiến | Nguồn hữu hạn không gửi `onComplete`/`onError` khi công việc đã xong | Subscriber chờ mãi, tài nguyên gắn với subscription có thể bị giữ lại |

Không phải mọi luồng chưa kết thúc đều vi phạm. Một Publisher có thể hợp lệ khi phát vô hạn hoặc không phát tín hiệu nào, miễn hành vi đó đúng với ý nghĩa nguồn và hợp đồng. Ví dụ `Flux.never()` chủ ý không phát `onNext`, `onComplete` hay `onError`. Vi phạm chỉ được xác định khi hành vi thực tế trái với giao thức hoặc cam kết của nguồn.

## Hệ quả khi Publisher phát vượt nhu cầu

Backpressure cho phép Subscriber điều tiết lượng dữ liệu được yêu cầu. Nếu Publisher bỏ qua nhu cầu và tiếp tục phát, các thành phần downstream không còn có thể dựa vào giới hạn đó để kiểm soát tải. Một operator có thể phải xếp dữ liệu vào hàng đợi trong lúc consumer chưa sẵn sàng; nếu tốc độ phát cao hơn tốc độ xử lý trong thời gian dài, hàng đợi có thể tăng đến mức tốn nhiều bộ nhớ hoặc gây `OutOfMemoryError`.

Tùy adapter và operator ở ranh giới, phần tử vượt nhu cầu có thể bị phát hiện và chuyển thành lỗi, bị loại bỏ, bị lưu đệm hoặc làm lộ ra hành vi ngoài dự kiến. Không nên dựa vào một kết quả tình cờ như “consumer vẫn nhận đủ dữ liệu” để kết luận Publisher tuân thủ. Khi nguồn đã vi phạm giao thức, hành vi của những thành phần dựa trên giao thức có thể không còn được bảo đảm.

Ví dụ về cách đọc tình huống:

```text
Nhu cầu ban đầu: request(1)

Subscriber  ---------------- request(1) ----------------> Publisher
Subscriber  <---------------- onNext(A) ----------------- Publisher
Subscriber  <---------------- onNext(B) ----------------- Publisher
                                      ^
                                      Vi phạm: B vượt nhu cầu
```

Nếu `A` và `B` đều được đưa vào một hàng đợi, độ trễ xử lý có thể tăng. Nếu adapter chọn báo lỗi, pipeline kết thúc ngoài dự đoán nghiệp vụ. Nếu adapter loại bỏ `B`, ứng dụng có thể mất một sự kiện quan trọng. Do đó, giải pháp đúng bắt đầu từ việc sửa nguồn hoặc định nghĩa chính sách rõ ràng tại adapter, không phải giả định downstream sẽ tự khôi phục mọi vi phạm.

## Hệ quả khi tín hiệu không được tuần tự hóa

Reactive Streams yêu cầu các tín hiệu tới một Subscriber phải được tuần tự hóa. Điều này không có nghĩa mọi tín hiệu phải chạy trên cùng một thread; tín hiệu có thể được phát từ các thread khác nhau, nhưng thứ tự gọi phải có quan hệ tuần tự phù hợp và không chồng lấn.

Hãy xét một event bus gọi listener từ hai thread. Nếu adapter trực tiếp chuyển từng callback thành `sink.next(event)` mà không bảo đảm tuần tự hóa theo mô hình nguồn, hai callback có thể cạnh tranh. Consumer đang cộng dồn trạng thái hoặc ghi một đối tượng mutable có thể quan sát race condition. Log có thể hiển thị thứ tự khác nhau giữa các lần chạy, khiến lỗi khó tái hiện.

```text
Thread A:  ---- onNext(A) bắt đầu -------- kết thúc
Thread B:       ---- onNext(B) bắt đầu -------- kết thúc
                         ^
                         Hai callback chồng lấn
```

Vấn đề không được giải quyết chỉ bằng cách chuyển downstream sang scheduler khác. Ranh giới nhận callback cần bảo đảm tín hiệu được tuần tự hóa trước khi phát vào pipeline. Nếu nguồn có thể gọi đồng thời, hãy dùng cơ chế sink/adapter được thiết kế cho nhiều producer hoặc một hàng đợi tuần tự hóa; nếu nguồn chỉ cho phép một producer, ghi rõ và bảo vệ giả định đó.

## Hệ quả khi tín hiệu kết thúc sai

`onComplete` và `onError` là hai cách kết thúc thay thế nhau cho một subscription. Khi đã gửi một trong hai, Publisher không được gửi thêm dữ liệu hoặc tín hiệu kết thúc khác. Nếu Publisher phát `onComplete` rồi mới gửi `onError`, Subscriber có thể đã giải phóng tài nguyên sau khi hoàn tất; lỗi đến sau không còn vị trí hợp lệ trong luồng. Framework có thể ghi nhận lỗi đó là lỗi bị drop để tránh làm hỏng một luồng đã kết thúc.

Tương tự, `onNext` sau `onComplete` là tín hiệu ngoài giao thức. Một consumer có thể đã chốt giao dịch, đóng file hoặc trả response cho client; dữ liệu đến muộn có thể không được xử lý, hoặc gây side effect ngoài dự kiến nếu adapter cho phép callback đi tiếp.

Nếu `onSubscribe` bị gọi hai lần, Subscriber có thể nhận hai subscription cho một lần đăng ký logic. Nếu cả hai đều được request, nguồn có nguy cơ tạo dữ liệu hoặc side effect trùng. Nếu Publisher phát dữ liệu trước `onSubscribe`, Subscriber chưa có cơ hội thiết lập demand và cơ chế hủy. Đây là lỗi ở ranh giới giao thức, không phải lỗi có thể sửa bằng một `map` phía sau.

## Hủy là một phần của vòng đời tài nguyên

Subscriber thường hủy khi người dùng rời màn hình, request HTTP bị đóng, timeout xảy ra hoặc kết quả đã đủ. Publisher cần tôn trọng việc hủy và dừng công việc càng sớm càng tốt. Với nguồn có callback, adapter cần tháo listener; với nguồn polling, cần dừng tác vụ định kỳ; với nguồn đọc file hoặc socket, cần đóng tài nguyên phù hợp.

Việc hủy không nhất thiết là một ranh giới đồng bộ tức thời. Một callback đã bắt đầu hoặc một tín hiệu đang được phát có thể cạnh tranh với thao tác cancel. Thiết kế consumer nên chịu được tình huống tín hiệu đang bay tới tại thời điểm hủy, còn Publisher phải ngừng tiếp tục tạo và phát dữ liệu sau khi xử lý hủy. Không nên coi cancel như tín hiệu `onComplete`; Subscriber không cần chờ một terminal signal để xác nhận rằng nó đã hủy.

Một adapter tốt gắn vòng đời listener với vòng đời subscription. Ví dụ khái niệm:

```java
Flux<Event> events = Flux.create(sink -> {
    EventListener listener = sink::next;
    eventSource.addListener(listener);

    sink.onDispose(() -> eventSource.removeListener(listener));
});
```

Khi subscription bị dispose/cancel, callback `onDispose` tháo listener để nguồn không tiếp tục giữ tham chiếu tới consumer. Ví dụ này giả định `eventSource` có API đăng ký và gỡ listener tương ứng; hệ thống thực tế cần chọn overflow strategy phù hợp nếu tốc độ callback vượt khả năng tiêu thụ. Nếu nguồn gọi listener từ nhiều thread, adapter cũng phải bảo đảm cách phát tín hiệu phù hợp với đặc tính producer.

## Phân biệt nguồn vi phạm với consumer xử lý chậm

Một Subscriber xử lý chậm không tự động là vi phạm hợp đồng. Đó là tình huống backpressure được thiết kế để xử lý: Subscriber yêu cầu dữ liệu theo khả năng của mình. Publisher tuân thủ có thể phát chậm lại, chờ demand, hoặc chỉ phát khi dữ liệu sẵn sàng.

Tương tự, một nguồn có thể phát nhanh theo nhịp bên ngoài và vẫn hợp lệ nếu adapter có chính sách tiếp nhận phù hợp với giao thức. Vấn đề xảy ra khi adapter phát vượt demand, tích lũy dữ liệu không giới hạn, hoặc âm thầm loại bỏ dữ liệu mà nghiệp vụ yêu cầu phải giữ. Cần phân biệt:

| Tình huống | Có phải tự thân là vi phạm? | Cách xử lý |
|---|---|---|
| Subscriber request ít vì xử lý chậm | Không | Để Publisher tuân thủ demand; đo độ trễ và throughput |
| Nguồn hợp lệ phát ít hơn demand rồi hoàn tất | Không | Xử lý terminal signal bình thường |
| Nguồn liên tục không gửi terminal signal | Không, nếu đó là ngữ nghĩa đã công bố | Quản lý timeout, cancel và vòng đời subscription |
| Adapter phát nhiều `onNext` hơn demand | Có | Sửa adapter hoặc Publisher; kiểm thử giao thức |
| Callback đồng thời được chuyển thành tín hiệu chồng lấn | Có, nếu phá vỡ tuần tự hóa | Tuần tự hóa ở ranh giới producer |
| Buffer tăng liên tục vì consumer chậm | Chưa đủ để kết luận nguồn vi phạm | Đặt giới hạn, chính sách overflow và quan sát tải |

## Cách xây dựng adapter an toàn

Khi chuyển một API callback hoặc event listener thành `Flux`, cần quyết định rõ các điểm sau:

1. **Số producer:** nguồn gọi callback từ một thread hay nhiều thread? Nếu nhiều thread, adapter phải xử lý việc phát đồng thời.
2. **Chính sách khi consumer chậm:** buffer có giới hạn, bỏ phần tử cũ, bỏ phần tử mới hay báo lỗi? Chính sách phải phù hợp với ý nghĩa nghiệp vụ.
3. **Vòng đời:** khi subscription bị hủy, listener, timer, socket hoặc tác vụ nền nào cần được tháo dỡ?
4. **Lỗi nguồn:** exception từ callback hoặc lỗi kết nối được chuyển thành `sink.error` như thế nào? Có bảo đảm chỉ kết thúc một lần không?
5. **Giá trị phát:** payload có thể null không? Nếu API cũ dùng null để biểu diễn “không có dữ liệu”, adapter cần chuyển nó thành kiểu biểu diễn rõ ràng như `Optional`, một sự kiện trạng thái riêng hoặc bỏ qua theo quy tắc nghiệp vụ.
6. **Nhu cầu:** nguồn có hỗ trợ pull/demand thật sự không? Nếu nguồn là push-only, adapter cần chính sách buffer/overflow có giới hạn thay vì giả vờ rằng `request(n)` đã điều khiển được thiết bị bên ngoài.

Trong Reactor, `Flux.create` thường phù hợp khi callback có thể đến từ nhiều thread; `Flux.push` dành cho trường hợp một producer phát tín hiệu. Chọn đúng loại sink giúp thể hiện đặc tính nguồn. Các overflow strategy như `BUFFER`, `DROP`, `LATEST` hoặc `ERROR` là chính sách tiếp nhận dữ liệu của adapter; chúng không làm cho một Publisher vốn vi phạm giao thức trở thành tuân thủ. `BUFFER` không giới hạn có thể tiêu thụ hết bộ nhớ, còn `DROP`/`LATEST` chỉ phù hợp nếu nghiệp vụ chấp nhận mất hoặc thay thế sự kiện.

## Kiểm thử để phát hiện giả định sai

Kiểm thử pipeline nên xác nhận cả dữ liệu và vòng đời: số phần tử nhận được, thứ tự, tín hiệu kết thúc, hành vi khi hủy và chính sách khi nguồn phát nhanh. `StepVerifier` giúp viết các kỳ vọng rõ ràng về demand và terminal signal. `TestPublisher` của Reactor Test có thể tạo nguồn kiểm thử, bao gồm chế độ không tuân thủ cho một số loại vi phạm, để kiểm tra adapter và consumer có phụ thuộc vào hành vi sai hay không.

Ví dụ kiểm thử demand bình thường:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DemandContractTest {
    @Test
    void emitsOnlyAsRequestedAndThenCompletes() {
        Flux<Integer> source = Flux.range(1, 3);

        StepVerifier.create(source, 0)
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }
}
```

Verifier bắt đầu với demand bằng không, yêu cầu một phần tử rồi yêu cầu thêm hai phần tử. Bài kiểm thử xác nhận nguồn hữu hạn chỉ phát theo demand và gửi `onComplete` sau phần tử cuối. Đây là kiểm thử hành vi của một nguồn tuân thủ; khi cần kiểm tra adapter chống lại nguồn lỗi, hãy tạo test case riêng với `TestPublisher` không tuân thủ và xác định rõ kết quả ứng dụng cần bảo đảm, chẳng hạn không xử lý trùng side effect hoặc không giữ listener sau cancel.

Không nên viết kiểm thử dựa trên giả định rằng mọi vi phạm đều được Reactor tự động sửa hoặc luôn biến thành cùng một exception. Kết quả phụ thuộc điểm vi phạm, adapter, operator và cách consumer được triển khai. Mục tiêu của test là phát hiện nguồn/adapter không đúng giao thức và xác nhận chính sách phòng vệ đã chọn.

## Quy trình điều tra khi nghi ngờ Publisher vi phạm

Khi thấy phần tử bị lặp, tín hiệu đến sau khi pipeline đã kết thúc hoặc bộ nhớ tăng bất thường, hãy khoanh vùng theo thứ tự:

1. Xác định Publisher gốc và các adapter nằm giữa nguồn với pipeline.
2. Ghi lại `onSubscribe`, các lần `request(n)`, `onNext`, terminal signal và `cancel` tại ranh giới nguồn.
3. Kiểm tra số phần tử phát so với tổng demand đã nhận.
4. Kiểm tra callback có thể chạy đồng thời hoặc gọi terminal nhiều lần không.
5. Kiểm tra listener/tác vụ nền có được tháo khi cancel hoặc dispose không.
6. Tạo test nhỏ tái hiện vi phạm bằng Publisher hoặc `TestPublisher` kiểm thử, rồi xác nhận cách sửa ở nguồn.

Log nên bao gồm subscription/request ID, tên thread, số thứ tự phần tử và trạng thái kết thúc. Tránh ghi payload nhạy cảm hoặc log toàn bộ dữ liệu tốc độ cao; một bộ đếm và dấu thời gian thường đủ để xác định nguồn phát vượt nhu cầu hay phát đồng thời.

## Những nhầm lẫn thường gặp

**Cho rằng `Flux.from(publisher)` sửa mọi Publisher sai giao thức.** `Flux.from` chuyển một Publisher sang kiểu Reactor để dùng operator; nó không thể tự biết ý nghĩa nghiệp vụ để sửa mọi lỗi giao thức của nguồn.

**Dùng buffer để che giấu nguồn phát vượt demand.** Buffer có thể hấp thụ chênh lệch tốc độ trong một giới hạn, nhưng buffer không giới hạn có nguy cơ cạn bộ nhớ. Nếu nguồn vi phạm giao thức, cần sửa nguồn hoặc adapter và chọn chính sách overflow có chủ đích.

**Cho rằng cancel đồng nghĩa với complete.** Cancel là yêu cầu từ Subscriber; complete là terminal signal từ Publisher. Hủy không cần phát `onComplete` để xác nhận.

**Coi mọi callback muộn là vi phạm.** Callback đã bắt đầu trước khi cancel có thể đang trong quá trình hoàn tất. Cần phân biệt tín hiệu đang bay tới với nguồn tiếp tục tạo dữ liệu sau khi đã xử lý hủy.

**Coi consumer chậm là lỗi Publisher.** Consumer chậm là tình huống bình thường. Chỉ khi nguồn phát vượt demand hoặc phá vỡ quy tắc tín hiệu mới là vi phạm hợp đồng.

## Tự kiểm tra

1. Subscriber chỉ gọi `request(1)` nhưng Publisher phát hai `onNext`. Quy tắc nào bị vi phạm và downstream có thể gặp những hậu quả gì?
2. Vì sao hai thread cùng gọi `onNext` cho một Subscriber có thể làm hỏng trạng thái dùng chung dù mỗi phần tử đều hợp lệ?
3. Publisher đã gọi `onComplete` rồi tiếp tục gọi `onNext`. Vì sao Subscriber không thể coi phần tử đến sau là dữ liệu bình thường?
4. Một Subscriber cancel nhưng nguồn callback vẫn tiếp tục giữ listener và tạo sự kiện. Adapter cần bổ sung cơ chế vòng đời nào?
5. Khi nào `BUFFER`, `DROP` hoặc `LATEST` là chính sách hợp lý cho nguồn push-only? Vì sao chúng không thay thế việc tuân thủ Reactive Streams?
6. Một Publisher không bao giờ kết thúc có nhất thiết vi phạm hợp đồng không? Nêu một trường hợp hợp lệ và một trường hợp ứng dụng cần điều tra.

Khi kiểm tra được demand, thứ tự tín hiệu, terminal signal và vòng đời cancel tại ranh giới nguồn, bạn có thể xác định Publisher nào đang vi phạm hợp đồng, đánh giá đúng tác động tới consumer và xây dựng adapter có chính sách tải, lỗi và dọn dẹp tài nguyên rõ ràng.
