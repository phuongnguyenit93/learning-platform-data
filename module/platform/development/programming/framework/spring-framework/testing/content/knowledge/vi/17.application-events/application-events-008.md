# Giới hạn phạm vi ghi nhận khi context hoặc luồng được dùng chung

## Vấn đề cần giải quyết

Trong Spring, các bean thường cùng sử dụng một `ApplicationContext`. Khi một bean gọi `ApplicationEventPublisher.publishEvent(...)`, các listener phù hợp trong context nhận được sự kiện đó. Đây là cơ chế giao tiếp trong phạm vi ứng dụng, vì vậy một sự kiện có thể được nhiều thành phần quan sát.

Trong kiểm thử, `ApplicationContext` còn có thể được Spring TestContext Framework tái sử dụng giữa nhiều test class nhờ context cache. Việc dùng chung context giúp bộ test chạy nhanh hơn, nhưng khiến việc ghi nhận sự kiện cần có ranh giới rõ ràng. Nếu một bộ thu sự kiện lưu dữ liệu như trạng thái singleton hoặc biến `static`, sự kiện của test trước có thể xuất hiện trong kết quả của test sau. Khi test chạy song song hoặc phát sự kiện qua executor, ranh giới theo test method cũng cần được xem xét cẩn thận.

Có ba phạm vi cần phân biệt:

| Phạm vi | Ý nghĩa | Rủi ro khi dùng chung |
| --- | --- | --- |
| `ApplicationContext` | Vòng đời của các bean và listener trong context | Listener hoặc bộ thu dạng singleton có thể sống qua nhiều test method |
| Test method | Khoảng thời gian một test method đang chạy | Các sự kiện phát sinh trong cùng method đều có thể được ghi nhận, kể cả sự kiện từ bước chuẩn bị hoặc thành phần khác |
| Luồng thực thi | Thread thực hiện lời gọi đồng bộ hoặc tác vụ bất đồng bộ | Sự kiện phát ra muộn hoặc từ thread khác có thể nằm ngoài phiên ghi nhận của test |

Mục tiêu của bài kiểm thử là xác nhận sự kiện do hành động đang kiểm tra tạo ra, trong đúng phạm vi cần quan sát. Không nên xem mọi sự kiện từng xuất hiện trong context là kết quả của riêng một thao tác.

## Dùng bộ ghi nhận dành riêng cho test method

Spring TestContext Framework cung cấp `@RecordApplicationEvents` và `ApplicationEvents` để ghi nhận application event trong quá trình thực thi test method. Đây là lựa chọn phù hợp khi cần kiểm tra sự kiện được publish bởi service hoặc thành phần trong `ApplicationContext` của bài test.

- Đặt `@RecordApplicationEvents` trên test class để bật khả năng ghi nhận.
- Inject `ApplicationEvents` vào test bằng `@Autowired`.
- Dùng `stream(EventType.class)` để lấy các sự kiện theo kiểu cần kiểm tra; dùng `stream()` nếu thực sự cần duyệt toàn bộ.
- Bộ ghi nhận được quản lý theo vòng đời test method và được làm mới giữa các method. Vì thế, các test có thể dùng chung cached `ApplicationContext` mà không cần tự tạo một danh sách sự kiện toàn cục.

Ví dụ dưới đây giả định `OrderService.place(...)` publish một payload event có kiểu `OrderPlaced`:

```java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(OrderTestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Autowired
    private ApplicationEvents applicationEvents;

    @Test
    void publishesEventForTheRequestedOrder() {
        UUID orderId = UUID.randomUUID();

        orderService.place(orderId);

        List<OrderPlaced> recorded = applicationEvents
                .stream(OrderPlaced.class)
                .filter(event -> orderId.equals(event.orderId()))
                .toList();

        assertThat(recorded).hasSize(1);
        assertThat(recorded.get(0).orderId()).isEqualTo(orderId);
    }
}
```

Ví dụ sử dụng `UUID` mới cho mỗi lần chạy và lọc theo `orderId`. Nếu context còn phát sinh một `OrderPlaced` cho đơn hàng khác, sự kiện đó không làm sai kết quả của test hiện tại. Kiểm tra cả số lượng lẫn dữ liệu định danh giúp phát hiện hai lỗi khác nhau: không publish sự kiện và publish sai hoặc lặp sự kiện cho đối tượng đang kiểm tra.

`ApplicationEvents` ghi nhận theo test method, không tự chia nhỏ một method thành từng lần gọi service. Nếu một test method gọi hai nghiệp vụ độc lập, cả hai nhóm sự kiện vẫn nằm trong cùng phiên ghi nhận. Khi cần phân biệt, hãy dùng correlation id hoặc khóa nghiệp vụ riêng cho từng thao tác rồi lọc theo khóa đó. Nếu hai hành vi không phụ thuộc nhau, tách chúng thành hai test method sẽ tạo ranh giới rõ ràng hơn.

## Khi nhiều test dùng chung `ApplicationContext`

Spring có thể cache context và tái sử dụng nó cho nhiều test class có cấu hình tương thích. Đây là hành vi bình thường, không phải dấu hiệu cho thấy dữ liệu ghi nhận của các test phải dùng chung. Với `@RecordApplicationEvents`, phần ghi nhận gắn với vòng đời test method; không cần đóng context sau mỗi test chỉ để xóa danh sách sự kiện.

Để tránh ghi nhận nhầm sự kiện trong context dùng chung, hãy áp dụng các nguyên tắc sau:

1. **Lọc theo kiểu sự kiện.** Ưu tiên `stream(OrderPlaced.class)` thay vì đếm toàn bộ `stream()`. Các event khác trong cùng context không nên ảnh hưởng đến assertion của nghiệp vụ đang kiểm tra.
2. **Lọc theo định danh của thao tác.** Dùng id hoặc correlation id được tạo riêng trong test. Điều này hữu ích khi nhiều bean cùng publish một kiểu event hoặc một test method thực hiện nhiều thao tác.
3. **Giữ bước chuẩn bị có kiểm soát.** Nếu `@BeforeEach`, fixture hoặc helper gọi service và phát sinh domain event, những event đó có thể nằm trong khoảng ghi nhận của test. Tránh tạo sự kiện không liên quan trong setup; nếu không thể tránh, hãy phân biệt chúng bằng định danh hoặc dữ liệu của event.
4. **Không dùng bộ sưu tập toàn cục.** Tránh `static List<ApplicationEvent>`, singleton recorder tích lũy sự kiện qua nhiều test, hoặc một biến mutable dùng chung giữa các test class. Chúng khiến kết quả phụ thuộc thứ tự chạy và khó kiểm soát khi chạy song song.
5. **Không assert tổng số event của context nếu không có lý do rõ ràng.** Hãy assert đúng kiểu, đúng định danh, số lượng và nội dung mà nghiệp vụ cam kết.

Ví dụ, assertion sau thường quá rộng:

```java
assertThat(applicationEvents.stream().count()).isEqualTo(1);
```

Nó giả định không có bất kỳ event nào khác trong phiên test. Assertion theo kiểu và định danh nghiệp vụ cụ thể thường bền vững hơn:

```java
assertThat(applicationEvents.stream(OrderPlaced.class)
        .filter(event -> orderId.equals(event.orderId())))
        .hasSize(1);
```

Nếu một test class tự khai báo `@TestExecutionListeners` với chế độ thay thế toàn bộ listener mặc định, cần bảo đảm `ApplicationEventsTestExecutionListener` vẫn được đăng ký. Nếu listener này bị loại khỏi danh sách, annotation ghi nhận sự kiện sẽ không có cơ chế TestContext cần thiết để hoạt động.

## Khi luồng thực thi được dùng chung hoặc chuyển sang bất đồng bộ

Với lời gọi đồng bộ, service publish event trong lúc test method đang chạy nên test có thể đọc kết quả sau khi lời gọi hoàn tất. Tình huống khác xuất hiện khi service gửi công việc sang `@Async`, `Executor`, scheduler hoặc message consumer.

Có hai vấn đề cần xử lý riêng:

- **Thời điểm:** test method có thể kết thúc trước khi tác vụ nền publish event. Khi đó phiên ghi nhận của test đã kết thúc và assertion có thể chạy quá sớm.
- **Thread:** tác vụ nền chạy trên thread khác với thread đang thực hiện test. Không nên mặc định trạng thái ghi nhận gắn với test thread sẽ tự động được truyền sang mọi thread do ứng dụng tạo ra. Hành vi cụ thể phụ thuộc cơ chế ghi nhận và cách ứng dụng chuyển giao công việc.

Khi kiểm tra luồng bất đồng bộ:

- Chờ tín hiệu hoàn tất bằng `CountDownLatch`, `CompletableFuture` hoặc thư viện chờ điều kiện như Awaitility; tránh `Thread.sleep(...)` vì thời gian chờ cố định không chứng minh tác vụ đã hoàn tất.
- Bảo đảm event được publish trước khi test method kết thúc nếu đang dùng bộ ghi nhận theo vòng đời method.
- Dùng correlation id để liên kết event với yêu cầu đã khởi tạo tác vụ. Không dựa riêng vào thời điểm hoặc thứ tự toàn cục khi có nhiều tác vụ chạy đồng thời.
- Nếu cần quan sát event được publish trên thread nền, kiểm tra rõ giới hạn thread của bộ ghi nhận trong phiên bản Spring đang dùng. Khi cơ chế có sẵn không đáp ứng trường hợp đó, hãy tạo test listener chuyên biệt có vòng đời đăng ký/hủy đăng ký rõ ràng và bộ lưu trữ an toàn khi nhiều thread cùng truy cập.
- Phân biệt việc **event đã được publish** với việc **listener bất đồng bộ đã xử lý xong**. Ghi nhận event chỉ chứng minh event đã đi qua điểm publish; muốn xác nhận kết quả xử lý, hãy chờ và assert trạng thái hoặc tín hiệu hoàn tất của listener.

Một bộ sưu tập thread-safe như `CopyOnWriteArrayList` chỉ giúp giảm lỗi truy cập đồng thời. Nó không tự tạo cách ly giữa các test. Nếu nhiều test cùng ghi vào một list, chúng vẫn có thể nhìn thấy dữ liệu của nhau dù list không bị hỏng do race condition.

## Khi event phụ thuộc transaction

Event thông thường được publish ngay khi code gọi `publishEvent(...)`. Tuy nhiên, listener dùng `@TransactionalEventListener` có thể trì hoãn xử lý đến một transaction phase như `BEFORE_COMMIT` hoặc `AFTER_COMMIT`.

Test được đánh dấu `@Transactional` trong Spring Test thường kết thúc bằng rollback. Vì vậy, listener chờ `AFTER_COMMIT` có thể không chạy trong test đó. Cần phân biệt hai mục tiêu:

- Nếu chỉ kiểm tra service đã publish event, có thể ghi nhận event tại thời điểm publish và assert kiểu/nội dung của nó.
- Nếu kiểm tra side effect của listener sau commit, test phải tạo được commit thật, chẳng hạn dùng `@Commit` hoặc chủ động điều khiển transaction bằng `TestTransaction` theo cấu hình phù hợp.

Không nên kết luận listener bị lỗi chỉ vì test transaction đã rollback trước phase mà listener đang chờ. Ngược lại, ghi nhận được event cũng không chứng minh listener `AFTER_COMMIT` đã thực thi.

## Khi phải tự viết event recorder

`@RecordApplicationEvents` nên là lựa chọn đầu tiên cho kiểm thử tích hợp dựa trên TestContext. Chỉ nên tự viết recorder khi cần quan sát ngoài phạm vi mà cơ chế này hỗ trợ, chẳng hạn một luồng nền đặc thù hoặc một ranh giới context riêng.

Nếu dùng `ApplicationListener` hoặc `@EventListener` để thu thập event, hãy xác định rõ:

- Recorder thuộc context nào và nhận event từ context nào.
- Khi nào bắt đầu thu thập và khi nào dừng.
- Dữ liệu được xóa hoặc hủy ở đâu sau mỗi test.
- Nhiều thread có thể ghi đồng thời hay không.
- Event được phân biệt theo test hoặc correlation id nào.

Một listener singleton được đăng ký trong context cache sẽ tồn tại cùng context. Vì vậy, chỉ thêm một list vào listener rồi kiểm tra list trong từng test là chưa đủ: list cần được cô lập và dọn đúng vòng đời. Việc dùng collection thread-safe không thay thế bước dọn dữ liệu hoặc tách phiên ghi nhận.

`@DirtiesContext` cũng không phải công cụ mặc định để xóa event recorder. Annotation này đánh dấu context cần bị loại khỏi cache và tạo lại, phù hợp khi trạng thái của chính context đã bị thay đổi hoặc hỏng đến mức không thể tái sử dụng. Dùng nó chỉ để tránh một list event dùng chung sẽ làm tăng chi phí khởi tạo context và che giấu vấn đề quản lý vòng đời của recorder.

## Cách chọn phạm vi phù hợp

| Tình huống | Cách xử lý nên dùng |
| --- | --- |
| Nhiều test method dùng chung cached context | `@RecordApplicationEvents` và `ApplicationEvents` cho từng test method |
| Một method gọi nhiều nghiệp vụ | Tạo correlation id riêng và lọc theo id; hoặc tách thành các test method độc lập |
| Setup phát sinh event không liên quan | Loại event khỏi setup nếu có thể; nếu không, lọc bằng kiểu và định danh |
| Nhiều test chạy song song | Không dùng list mutable toàn cục; bảo đảm mỗi test có phiên ghi nhận riêng |
| Event được publish từ executor hoặc `@Async` | Đồng bộ thời điểm hoàn tất, kiểm tra giới hạn thread và dùng recorder phù hợp nếu cần |
| Listener chỉ chạy sau transaction commit | Commit transaction trong test khi mục tiêu là kiểm tra side effect sau commit |
| Recorder tự viết sống cùng context | Đăng ký/hủy đăng ký và dọn dữ liệu theo từng test; bảo đảm an toàn đa luồng |

## Những lỗi thường gặp

- **Đếm tất cả event rồi giả định chỉ có một event:** assertion phụ thuộc các event phụ trợ trong cùng context. Hãy lọc theo event type và khóa nghiệp vụ.
- **Lưu event trong biến `static`:** dữ liệu tồn tại qua test method và có thể rò giữa test class. Hãy dùng bộ ghi nhận theo test hoặc recorder có lifecycle riêng.
- **Cho rằng một test method tương đương một lần gọi nghiệp vụ:** method có thể phát sinh nhiều event từ setup, nhiều service hoặc nhiều lần gọi. Dùng correlation id để phân tách.
- **Assert ngay sau khi gửi tác vụ nền:** lệnh gửi task hoàn tất không đồng nghĩa event đã được publish. Hãy chờ điều kiện hoàn tất có ý nghĩa.
- **Dùng `@DirtiesContext` cho mọi lỗi ghi nhận:** việc tạo lại context tốn thời gian và không sửa được recorder có trạng thái toàn cục sai thiết kế.
- **Nhầm event publication với listener completion:** event được publish không bảo đảm mọi listener đồng bộ hoặc bất đồng bộ đã xử lý xong.
- **Quên listener TestExecution khi thay thế cấu hình mặc định:** `@RecordApplicationEvents` cần listener của Spring TestContext để quản lý phiên ghi nhận.

## Quy trình kiểm tra trong một test

1. Xác định event nghiệp vụ cần quan sát và trường định danh giúp phân biệt event của thao tác hiện tại.
2. Bật `@RecordApplicationEvents` trên test class và inject `ApplicationEvents`.
3. Tạo dữ liệu hoặc correlation id riêng cho test.
4. Thực hiện đúng hành động cần kiểm tra.
5. Nếu hành động bất đồng bộ hoặc phụ thuộc commit, chờ đúng mốc hoàn tất trước khi đọc kết quả.
6. Lọc event theo kiểu và định danh; assert số lượng cùng dữ liệu quan trọng.
7. Để Spring quản lý vòng đời ghi nhận giữa các test method; nếu dùng recorder riêng, chủ động hủy đăng ký và dọn dữ liệu sau test.

Khi context hoặc luồng thực thi được dùng chung, độ tin cậy của kiểm thử phụ thuộc vào việc xác định đúng ranh giới ghi nhận. Bộ ghi nhận theo test method xử lý tốt trường hợp thông thường; bộ lọc theo kiểu và correlation id giới hạn kết quả theo nghiệp vụ; còn tác vụ bất đồng bộ và transaction cần có tín hiệu hoàn tất phù hợp. Ba lớp kiểm soát này giúp test xác nhận đúng event do hành động mục tiêu tạo ra mà không phụ thuộc thứ tự chạy hoặc trạng thái còn sót lại từ test khác.
