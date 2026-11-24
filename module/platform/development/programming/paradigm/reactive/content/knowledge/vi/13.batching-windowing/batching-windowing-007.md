# groupBy: phân nhóm theo khóa và quản lý vòng đời nhóm

Trong một luồng sự kiện, các phần tử thường thuộc về nhiều thực thể hoặc loại nghiệp vụ khác nhau. Ví dụ, một hệ thống thanh toán nhận sự kiện của nhiều tài khoản xen kẽ nhau. Khi cần tính tổng theo từng tài khoản, xử lý riêng từng loại sự kiện hoặc duy trì trạng thái theo khóa, ta cần tách luồng thành các nhóm.

Project Reactor cung cấp toán tử **groupBy** để phân nhóm phần tử theo một khóa. Toán tử phát ra một **Flux<GroupedFlux<K, T>>**: mỗi **GroupedFlux** đại diện cho một nhóm có khóa **K** và chứa các phần tử **T** tương ứng.

Điểm cần hiểu không chỉ là cách tạo nhóm. Mỗi nhóm có vòng đời riêng gắn với luồng nguồn, và ứng dụng phải tiêu thụ các nhóm để backpressure hoạt động đúng. Nếu tạo quá nhiều nhóm hoặc bỏ quên một số nhóm, pipeline có thể tích lũy dữ liệu, giảm throughput hoặc bị đình trệ.

Các kiểu PaymentEvent, AccountTotal, AccountBalance và AccountResult trong ví dụ là kiểu miền do ứng dụng định nghĩa. Những đoạn mã minh họa giả định đã khai báo các import và dịch vụ cần thiết.

## 1. groupBy tạo các luồng con theo khóa

Giả sử nguồn phát sự kiện thanh toán của nhiều tài khoản theo thứ tự xen kẽ:

~~~java
Flux<PaymentEvent> payments = Flux.just(
    new PaymentEvent("ACC-01", new BigDecimal("100")),
    new PaymentEvent("ACC-02", new BigDecimal("50")),
    new PaymentEvent("ACC-01", new BigDecimal("25")),
    new PaymentEvent("ACC-03", new BigDecimal("80")),
    new PaymentEvent("ACC-02", new BigDecimal("10"))
);
~~~

Nếu muốn xử lý riêng sự kiện của từng tài khoản, có thể phân nhóm theo accountId:

~~~java
Flux<GroupedFlux<String, PaymentEvent>> groups =
    payments.groupBy(PaymentEvent::accountId);
~~~

Kết quả là một luồng bên ngoài chứa các đối tượng **GroupedFlux**. Khi nguồn gặp khóa ACC-01 lần đầu, groupBy phát ra nhóm mang khóa đó. Khi gặp ACC-02, nó phát nhóm thứ hai; khi gặp ACC-03, nó phát nhóm thứ ba. Những sự kiện tiếp theo có khóa đã xuất hiện sẽ được chuyển vào nhóm tương ứng.

~~~mermaid
flowchart LR
    S["PaymentEvent stream"] --> G["groupBy(accountId)"]
    G --> A["Group ACC-01"]
    G --> B["Group ACC-02"]
    G --> C["Group ACC-03"]
    A --> A1["100, 25"]
    B --> B1["50, 10"]
    C --> C1["80"]
~~~

groupBy không sắp xếp phần tử theo khóa. Các nhóm được phát ra khi khóa của chúng xuất hiện lần đầu trong nguồn. Bên trong mỗi nhóm, các phần tử giữ thứ tự tương đối theo thứ tự chúng xuất hiện ở nguồn. Thứ tự phát kết quả giữa các nhóm về sau còn phụ thuộc vào cách downstream tiêu thụ và kết hợp các nhóm.

## 2. GroupedFlux và khóa của nhóm

**GroupedFlux<K, T>** là một Publisher con mang khóa K và phát các phần tử kiểu T thuộc nhóm đó. Có thể lấy khóa bằng phương thức **key()**:

~~~java
payments
    .groupBy(PaymentEvent::accountId)
    .flatMap(group ->
        group.doOnNext(event ->
            log.info("Tài khoản {} nhận {}", group.key(), event.amount())
        )
    );
~~~

Trong ví dụ, mỗi nhóm được tiêu thụ một lần. group.key() cho biết tài khoản mà các sự kiện trong nhóm thuộc về.

Một số đặc điểm quan trọng:

- Mỗi khóa tạo một nhóm riêng khi khóa đó xuất hiện lần đầu.
- Các phần tử có cùng khóa được đưa vào cùng nhóm trong vòng đời của lần đăng ký đó.
- GroupedFlux cung cấp các toán tử Flux thông thường như map, filter, reduce, scan và flatMap.
- Nhóm là Publisher đơn người đăng ký (unicast); mỗi nhóm chỉ nên có một Subscriber.
- GroupedFlux không phải một danh sách đã gom sẵn. Nó là một luồng con có thể tiếp tục phát phần tử theo thời gian.

Khóa cần ổn định và có equals/hashCode nhất quán. Nên dùng khóa không null, chẳng hạn ID tài khoản, mã khách hàng hoặc enum loại sự kiện. Nếu dùng object mutable làm khóa rồi thay đổi các trường ảnh hưởng đến equals/hashCode, việc phân nhóm có thể không còn đúng như mong đợi.

## 3. Phân nhóm rồi tổng hợp dữ liệu

Một ứng dụng phổ biến là tính tổng số tiền theo tài khoản. Với mỗi nhóm, ta dùng reduce để cộng các khoản thanh toán:

~~~java
record AccountTotal(String accountId, BigDecimal total) {}

Flux<AccountTotal> totals = payments
    .groupBy(PaymentEvent::accountId)
    .flatMap(group ->
        group.map(PaymentEvent::amount)
            .reduce(BigDecimal.ZERO, BigDecimal::add)
            .map(total -> new AccountTotal(group.key(), total)),
        3
    );
~~~

Mỗi reduce tiêu thụ toàn bộ nhóm và phát một tổng khi nhóm hoàn tất. Tham số 3 của flatMap đặt giới hạn số nhóm được subscribe đồng thời. Ví dụ này giả định nguồn có tối đa ba tài khoản khác nhau; nếu có nhiều nhóm hơn, cần điều chỉnh concurrency để mọi nhóm có thể được tiêu thụ.

Khi nguồn hoàn tất, các nhóm hoàn tất, các phép reduce phát tổng của chúng và luồng totals hoàn tất sau khi các Publisher con hoàn tất. Thứ tự các tổng không được bảo đảm vì flatMap phát kết quả theo thời điểm các nhóm hoàn tất.

Nếu chỉ cần cập nhật trạng thái mỗi khi một sự kiện đến, có thể dùng scan thay vì chờ nhóm hoàn tất:

~~~java
record AccountBalance(String accountId, BigDecimal balance) {}

Flux<AccountBalance> runningBalances = payments
    .groupBy(PaymentEvent::accountId)
    .flatMap(group ->
        group.map(PaymentEvent::amount)
            .scan(BigDecimal.ZERO, BigDecimal::add)
            .map(balance -> new AccountBalance(group.key(), balance)),
        3
    );
~~~

scan phát giá trị tích lũy sau từng phần tử. Với một nguồn dài hạn không hoàn tất, reduce sẽ chưa phát tổng cuối cùng; scan phù hợp hơn nếu downstream cần trạng thái cập nhật liên tục.

## 4. Chọn khóa và biến đổi giá trị trong groupBy

Overload cơ bản nhận một hàm chọn khóa:

~~~java
Flux<GroupedFlux<K, T>> groups =
    source.groupBy(value -> keyOf(value));
~~~

Có thể đồng thời biến đổi phần tử trước khi đưa vào nhóm bằng overload có valueMapper:

~~~java
Flux<GroupedFlux<String, BigDecimal>> amountsByAccount =
    payments.groupBy(
        PaymentEvent::accountId,
        PaymentEvent::amount
    );
~~~

Trong ví dụ, nhóm vẫn được tạo theo accountId, nhưng phần tử bên trong nhóm là BigDecimal thay vì PaymentEvent. Điều này hữu ích khi các bước sau chỉ cần một phần dữ liệu và không cần giữ toàn bộ object nguồn.

Reactor cũng cung cấp overload nhận prefetch:

~~~java
Flux<GroupedFlux<String, PaymentEvent>> groups =
    payments.groupBy(PaymentEvent::accountId, 32);
~~~

prefetch điều khiển lượng phần tử mà groupBy yêu cầu trước từ Publisher nguồn để quản lý việc phân phối vào các nhóm. Nó không phải số lượng nhóm tối đa, cũng không phải giới hạn tổng số phần tử có thể nằm trong toàn bộ pipeline.

Có thể kết hợp cả khóa, value mapper và prefetch:

~~~java
Flux<GroupedFlux<String, BigDecimal>> amountsByAccount =
    payments.groupBy(
        PaymentEvent::accountId,
        PaymentEvent::amount,
        32
    );
~~~

Chọn prefetch dựa trên khả năng cung cấp của nguồn và khả năng tiêu thụ của các nhóm. Prefetch lớn có thể cải thiện throughput trong một số trường hợp, nhưng cũng làm tăng lượng dữ liệu đã được yêu cầu và có thể đang chờ trong pipeline.

## 5. Vòng đời của một nhóm

Một nhóm được tạo khi groupBy gặp phần tử đầu tiên có khóa tương ứng. Sau đó, những phần tử có cùng khóa được phát vào nhóm đó. Nhóm tồn tại trong vòng đời của nguồn và kết thúc khi nguồn kết thúc:

- Nếu Publisher nguồn phát onComplete, các nhóm đang hoạt động cũng hoàn tất.
- Nếu Publisher nguồn phát onError, các nhóm đang hoạt động kết thúc bằng lỗi.
- Nếu downstream hủy subscription bên ngoài, việc tiêu thụ nguồn và các nhóm liên quan bị hủy theo vòng đời subscription đó.
- Một nhóm không tự hoàn tất chỉ vì tạm thời không có phần tử mới mang khóa của nó.

Ví dụ, một nguồn sự kiện không giới hạn có thể tiếp tục phát các sự kiện cho ACC-01 và ACC-02. Hai nhóm tương ứng vẫn mở chừng nào nguồn chưa kết thúc. Việc một tài khoản không phát sự kiện trong vài phút không có nghĩa nhóm của tài khoản đó đã hoàn tất.

~~~mermaid
stateDiagram-v2
    [*] --> NotCreated
    NotCreated --> Active: phần tử đầu tiên của khóa xuất hiện
    Active --> Active: phần tử cùng khóa
    Active --> Completed: nguồn onComplete
    Active --> Failed: nguồn onError
    Active --> Cancelled: subscription bị hủy
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

Điều này ảnh hưởng trực tiếp đến toán tử dùng bên trong nhóm. reduce chỉ phát kết quả sau khi nhóm hoàn tất. Với nguồn liên tục, nếu cần kết quả định kỳ, hãy tạo cửa sổ thời gian bên trong từng nhóm hoặc chọn một mô hình xử lý trạng thái khác.

## 6. Phải tiêu thụ các nhóm đã được phát

Khi groupBy phát một GroupedFlux, downstream cần subscribe và tiêu thụ nhóm đó. Nếu nhóm được tạo nhưng không được tiêu thụ, các phần tử dành cho nhóm có thể phải chờ trong hàng đợi nội bộ. Khi các hàng đợi không được giải phóng, backpressure có thể truyền ngược về nguồn và làm toàn bộ pipeline chậm lại hoặc đình trệ.

Một cách tiêu thụ thường dùng là flatMap:

~~~java
Flux<PaymentEvent> allEvents = payments
    .groupBy(PaymentEvent::accountId)
    .flatMap(group -> group, 32);
~~~

Ví dụ này hợp nhất các nhóm thành một luồng sự kiện. Các nhóm được subscribe và tiêu thụ đồng thời, với giới hạn concurrency là 32. Vì flatMap hợp nhất theo thời điểm phần tử đến, thứ tự toàn cục giữa các tài khoản không được giữ; thứ tự tương đối trong từng nhóm vẫn được duy trì.

Nếu cần xử lý riêng từng nhóm:

~~~java
Flux<AccountTotal> totals = payments
    .groupBy(PaymentEvent::accountId)
    .flatMap(group ->
        group.reduce(BigDecimal.ZERO, (sum, event) -> sum.add(event.amount()))
            .map(total -> new AccountTotal(group.key(), total)),
        32
    );
~~~

Concurrency phải đủ để các nhóm có thể được tiêu thụ. Nếu nguồn có thể tạo nhiều nhóm đang hoạt động hơn số nhóm mà downstream cho phép subscribe, một số nhóm chưa được tiêu thụ có thể giữ dữ liệu và ngăn nguồn tiếp tục phát đủ để các nhóm đang được xử lý hoàn tất.

Tránh dùng concatMap một cách máy móc để tiêu thụ các nhóm của một nguồn dài hạn:

~~~java
// Có thể đình trệ nếu nhóm đầu tiên không bao giờ hoàn tất.
Flux<PaymentEvent> events = payments
    .groupBy(PaymentEvent::accountId)
    .concatMap(group -> group);
~~~

concatMap chờ nhóm hiện tại hoàn tất trước khi subscribe nhóm kế tiếp. Nếu nguồn là luồng liên tục và nhóm đầu tiên không hoàn tất, các nhóm khác không được tiêu thụ. Dữ liệu của chúng có thể tích lũy, khiến upstream bị backpressure. Chỉ dùng cách tuần tự này khi vòng đời nhóm hữu hạn và việc chờ từng nhóm là phù hợp.

## 7. Cardinality: số lượng khóa khác nhau

Cardinality là số lượng khóa khác nhau mà groupBy gặp trong một luồng. Đây là yếu tố quan trọng khi thiết kế:

- **Cardinality thấp và có giới hạn:** ví dụ nhóm theo một vài trạng thái đơn hàng hoặc loại sự kiện. groupBy thường phù hợp.
- **Cardinality trung bình, biết trước giới hạn:** ví dụ nhóm theo một tập tài khoản đang hoạt động có số lượng được kiểm soát. Có thể dùng groupBy và đặt concurrency đủ để tiêu thụ nhóm.
- **Cardinality cao hoặc không giới hạn:** ví dụ nhóm theo ID request ngẫu nhiên trên một nguồn dài hạn. Số nhóm có thể tăng liên tục, làm tăng bộ nhớ và chi phí quản lý.

groupBy giữ trạng thái để định tuyến phần tử đến nhóm theo khóa. Nếu nguồn tạo khóa mới liên tục, số nhóm có thể tăng theo thời gian. Trên một nguồn không hoàn tất, các nhóm cũng có thể không kết thúc để giải phóng vòng đời. Vì vậy, không nên dùng groupBy trên khóa có cardinality không giới hạn mà không có chiến lược giới hạn hoặc tái cấu trúc.

Các lựa chọn khi cardinality quá cao:

- Chuẩn hóa khóa về một tập hữu hạn, nếu nghiệp vụ cho phép.
- Chia dữ liệu thành partition cố định, rồi xử lý từng partition.
- Dùng window nếu mục tiêu thực sự là chia theo thời gian hoặc số lượng phần tử.
- Dùng kho trạng thái ngoài có TTL nếu cần lưu trạng thái theo khóa trong thời gian dài.
- Xử lý từng sự kiện với scan hoặc một mô hình stateful có giới hạn thay vì tạo một nhóm sống lâu cho mọi khóa.

Không nên xem prefetch là cách giới hạn cardinality. Prefetch chỉ điều khiển lượng request trước từ nguồn; nó không giới hạn số khóa khác nhau có thể xuất hiện.

## 8. groupBy và backpressure

Backpressure hoạt động qua ranh giới Publisher–Subscriber. Với groupBy, có thêm một tầng phân phối: Subscriber bên ngoài nhận các đối tượng nhóm, còn Subscriber của từng nhóm nhận phần tử thuộc khóa tương ứng.

Các tình huống cần chú ý:

- Nếu downstream không yêu cầu thêm nhóm, groupBy có thể không tiếp tục phát các nhóm mới.
- Nếu một nhóm đã được phát nhưng chưa được subscribe, phần tử của nhóm đó có thể bị giữ lại.
- Nếu một nhóm được subscribe nhưng tiêu thụ chậm, dữ liệu của nhóm có thể tích lũy trong hàng đợi.
- Nếu số nhóm đồng thời vượt khả năng tiêu thụ, các nhóm chưa được drain có thể làm upstream bị đình trệ.

Vì thế, groupBy cần một chiến lược tiêu thụ rõ ràng. Với tập khóa hữu hạn và biết trước, có thể đặt concurrency bằng hoặc lớn hơn số nhóm tối đa cần hoạt động đồng thời. Nếu cardinality lớn hoặc thay đổi không kiểm soát, hãy xem xét mô hình khác thay vì chỉ tăng concurrency.

Concurrency lớn hơn cũng không miễn phí. Nó có thể làm nhiều nhóm chạy cùng lúc, tăng số thao tác I/O, bộ nhớ và tải lên dịch vụ đích. Hãy chọn giới hạn dựa trên năng lực thực tế và đo số nhóm đang hoạt động, độ dài hàng đợi, độ trễ cũng như throughput.

## 9. Phân biệt groupBy, buffer và window

Ba toán tử đều chia luồng thành các phần nhỏ, nhưng tiêu chí chia khác nhau:

| Toán tử | Tiêu chí phân chia | Kiểu đầu ra | Vòng đời |
|---|---|---|---|
| groupBy | Khóa của từng phần tử | GroupedFlux<K, T> | Nhóm gắn với khóa và thường kết thúc khi nguồn kết thúc. |
| buffer(n) | Số lượng phần tử | List<T> | Phát danh sách khi đủ phần tử hoặc khi nguồn kết thúc. |
| bufferTimeout(n, duration) | Số lượng hoặc thời gian | List<T> | Phát batch khi đạt kích thước hoặc timeout. |
| window(n) | Số lượng phần tử | Flux<Flux<T>> | Mỗi window là một Publisher con có ranh giới xác định. |
| windowTimeout(n, duration) | Số lượng hoặc thời gian | Flux<Flux<T>> | Window đóng khi đạt kích thước hoặc timeout. |

Ví dụ:

~~~java
Flux<GroupedFlux<String, PaymentEvent>> byAccount =
    payments.groupBy(PaymentEvent::accountId);

Flux<List<PaymentEvent>> batches =
    payments.buffer(100);

Flux<Flux<PaymentEvent>> windows =
    payments.windowTimeout(100, Duration.ofSeconds(1));
~~~

Dùng groupBy khi cần xử lý theo thực thể hoặc khóa. Dùng buffer khi cần gửi một nhóm phần tử trong một lần gọi. Dùng window khi cần chia thành các Publisher con theo số lượng hoặc thời gian. Nếu mục tiêu là tính tổng theo tài khoản trong từng phút, có thể kết hợp nhóm theo tài khoản với window thời gian bên trong mỗi nhóm, nhưng cần cân nhắc số nhóm và vòng đời nguồn.

## 10. Xử lý lỗi trong nhóm

Lỗi từ Publisher nguồn được truyền đến các nhóm đang hoạt động và luồng bên ngoài. Các nhóm kết thúc do lỗi thay vì hoàn tất bình thường. Nếu lỗi phát sinh trong logic xử lý riêng của một nhóm, có thể xử lý tại Publisher con để xác định lỗi đó có làm ảnh hưởng các nhóm khác hay không.

Ví dụ, nếu chỉ muốn bỏ qua lỗi khi tính tổng cho một tài khoản cụ thể và ghi nhận tài khoản đó:

~~~java
Flux<AccountResult> results = payments
    .groupBy(PaymentEvent::accountId)
    .flatMap(group ->
        group.reduce(BigDecimal.ZERO, (sum, event) -> sum.add(event.amount()))
            .map(total -> AccountResult.success(group.key(), total))
            .onErrorResume(error ->
                Mono.just(AccountResult.failure(group.key(), error))
            ),
        32
    );
~~~

Cách xử lý này chỉ bắt lỗi phát sinh trong nhánh xử lý của nhóm. Nếu chính Publisher nguồn phát onError, các nhóm đều chịu ảnh hưởng từ lỗi nguồn; đặt onErrorResume bên trong mỗi nhóm không biến một nguồn đã kết thúc thành nguồn tiếp tục phát dữ liệu.

Nếu cần retry, hãy xác định retry áp dụng cho nguồn chung hay cho thao tác riêng của từng nhóm. Retry nguồn có thể tạo lại toàn bộ luồng và các nhóm; retry thao tác riêng trong nhóm chỉ lặp lại công việc tương ứng. Phạm vi retry phải phù hợp với tính idempotent của nghiệp vụ.

## 11. Kiểm thử phân nhóm bằng StepVerifier

Có thể kiểm tra nội dung các nhóm bằng cách thu thập từng nhóm thành một danh sách rồi tổng hợp kết quả:

~~~java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void groupByTachSoChanVaSoLe() {
    Mono<Map<Integer, List<Integer>>> grouped =
        Flux.range(1, 6)
            .groupBy(number -> number % 2)
            .flatMap(group ->
                group.collectList()
                    .map(values -> Map.entry(group.key(), values)),
                2
            )
            .collectMap(Map.Entry::getKey, Map.Entry::getValue);

    StepVerifier.create(grouped)
        .expectNext(Map.of(
            1, List.of(1, 3, 5),
            0, List.of(2, 4, 6)
        ))
        .verifyComplete();
}
~~~

Phép thử xác nhận nhóm khóa 1 chứa các số lẻ và nhóm khóa 0 chứa các số chẵn. Dùng Map để so sánh vì thứ tự hoàn tất các phép thu thập nhóm không được bảo đảm khi dùng flatMap.

Có thể kiểm tra việc lấy khóa và value mapper:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void groupByDungKhoaVaBienDoiGiaTri() {
    StepVerifier.create(
            Flux.just("ant", "apple", "bee")
                .groupBy(
                    word -> word.charAt(0),
                    String::length
                )
                .flatMap(group ->
                    group.map(length -> group.key() + ":" + length),
                    2
                )
                .collectList()
        )
        .expectNextMatches(values ->
            values.containsAll(List.of("a:3", "a:5", "b:3"))
                && values.size() == 3
        )
        .verifyComplete();
}
~~~

Các tình huống nên kiểm thử thêm:

- Nguồn rỗng không tạo nhóm và hoàn tất bình thường.
- Nhiều phần tử cùng khóa đi vào đúng một nhóm theo thứ tự nguồn.
- Khóa mới tạo một nhóm mới khi xuất hiện lần đầu.
- Nguồn hoàn tất làm tất cả nhóm hoàn tất.
- Lỗi nguồn làm các nhóm đang hoạt động kết thúc bằng lỗi.
- Cancellation downstream truyền lên nguồn và các nhóm đang được tiêu thụ.
- Concurrency đủ để tiêu thụ mọi nhóm trong giới hạn cardinality dự kiến.

## 12. Checklist thiết kế groupBy

Trước khi đưa groupBy vào pipeline, hãy trả lời các câu hỏi sau:

1. Khóa có ổn định, không null và có equals/hashCode đúng không?
2. Số lượng khóa khác nhau có giới hạn hoặc có thể dự đoán không?
3. Mỗi nhóm có được subscribe và tiêu thụ đúng một lần không?
4. Concurrency có đủ để drain các nhóm có thể hoạt động đồng thời không?
5. Nhóm có thể sống lâu vì nguồn không hoàn tất không?
6. Có cần tổng hợp cuối nhóm bằng reduce, hay cần cập nhật liên tục bằng scan?
7. Có cần giới hạn theo thời gian bằng window thay vì giữ nhóm theo khóa?
8. Chính sách lỗi và cancellation có giải phóng công việc đang chạy không?

groupBy hữu ích khi cần tách một luồng thành các luồng con theo khóa để xử lý trạng thái hoặc nghiệp vụ độc lập. Đổi lại, ứng dụng phải quản lý việc tiêu thụ nhóm, cardinality và vòng đời của chúng. Khi kết hợp GroupedFlux với flatMap, reduce, scan, backpressure và kiểm thử StepVerifier một cách có chủ đích, pipeline Reactor có thể xử lý nhiều thực thể song song mà vẫn giữ được ranh giới dữ liệu rõ ràng.

