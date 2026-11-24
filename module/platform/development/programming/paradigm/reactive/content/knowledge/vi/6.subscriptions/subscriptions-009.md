# Đăng ký nhận

## Theo dõi quan hệ giữa đăng ký, nguồn và các nhánh xử lý

Trong một pipeline reactive, nguồn dữ liệu (source) mô tả nơi các phần tử xuất phát, các toán tử mô tả cách dữ liệu được biến đổi, còn subscription đại diện cho một lần tiêu thụ cụ thể. Hiểu quan hệ giữa ba thành phần này giúp trả lời những câu hỏi thực tế: một pipeline chạy bao nhiêu lần, nhiều subscriber có dùng chung một lần đọc dữ liệu không, một nguồn có thể cấp dữ liệu cho nhiều nhánh xử lý như thế nào và khi một nhánh dừng thì nguồn có tiếp tục chạy không.

Với Project Reactor, lời gọi các toán tử như **map**, **filter** hay **flatMap** thường chỉ lắp ghép mô tả pipeline. Khi có subscription, tín hiệu mới đi qua nguồn và các toán tử. Mỗi subscription có thể tạo một lần thực thi độc lập hoặc tham gia một nguồn được chia sẻ, tùy cách publisher được xây dựng.

### 1. Một subscription nối nguồn với một lần tiêu thụ

Quan hệ cơ bản có thể hình dung như sau:

~~~text
Source
  |
  v
Publisher + các toán tử
  |
  v
Subscription <---- Subscriber
  |
  v
Các tín hiệu onNext / onError / onComplete
~~~

Subscriber đăng ký với Publisher. Publisher cung cấp Subscription để Subscriber yêu cầu dữ liệu hoặc hủy đăng ký. Khi dữ liệu được phát, nó đi qua các toán tử upstream và downstream theo cấu trúc đã khai báo. Subscription giữ trạng thái nhu cầu và vòng đời của lần tiêu thụ đó.

Một biến Java chứa **Flux<OrderEvent>** chưa đồng nghĩa với việc đã có subscriber đang nhận sự kiện. Nó chỉ tham chiếu đến một publisher. Việc gọi **subscribe** tạo subscription và bắt đầu quá trình tiêu thụ theo ngữ nghĩa của nguồn. Với nguồn lạnh (cold publisher), mỗi subscription thường khởi động một lần thực thi mới. Với nguồn nóng (hot publisher), việc phát có thể diễn ra độc lập với từng subscriber.

### 2. Assembly và subscription là hai thời điểm khác nhau

Reactor phân biệt thời điểm lắp ghép pipeline (assembly time) với thời điểm đăng ký (subscription time). Ở assembly time, ta kết hợp nguồn và toán tử để tạo một publisher mới. Ở subscription time, subscriber kết nối vào publisher và kích hoạt quá trình tiêu thụ.

Ví dụ:

~~~java
Flux<Integer> numbers =
    Flux.range(1, 3)
        .map(number -> number * 10);

// Chưa có subscriber; pipeline mới được lắp ghép.

numbers.subscribe(System.out::println);
~~~

Lệnh **Flux.range** và **map** tạo mô tả luồng. Khi gọi **subscribe**, các giá trị 1, 2, 3 mới được phát và chuyển thành 10, 20, 30.

Toán tử **defer** giúp tạo nguồn mới tại mỗi lần đăng ký:

~~~java
import java.time.Instant;

Flux<Instant> timestamps =
    Flux.defer(() -> Flux.just(Instant.now()));

timestamps.subscribe(System.out::println);
timestamps.subscribe(System.out::println);
~~~

Mỗi subscription gọi lại supplier bên trong **defer**, vì vậy hai subscriber có thể nhận hai thời điểm khác nhau. Nếu viết **Flux.just(Instant.now())**, lời gọi **Instant.now()** xảy ra khi lắp ghép pipeline; hai subscriber sau đó có thể nhận cùng một giá trị đã được tạo từ trước. Phân biệt này quan trọng khi nguồn đọc cơ sở dữ liệu, gọi dịch vụ ngoài hoặc khởi tạo tài nguyên.

### 3. Nhiều subscription trên một nguồn lạnh tạo nhiều lần thực thi

Một publisher lạnh thường tạo dữ liệu riêng cho từng subscriber. Ví dụ:

~~~java
Flux<OrderEvent> events =
    Flux.defer(() -> {
        log.info("Bắt đầu đọc sự kiện đơn hàng");
        return repository.loadRecentEvents();
    });

events.subscribe(this::updateDashboard);
events.subscribe(this::writeAuditLog);
~~~

Hai lời gọi **subscribe** tạo hai subscription. Với nguồn lạnh ở ví dụ này, supplier chạy hai lần và repository có thể được gọi hai lần. Đây có thể là hành vi mong muốn nếu hai consumer cần các lần đọc độc lập. Nhưng nếu việc đọc tốn kém hoặc cả hai consumer cần cùng một chuỗi sự kiện, thực thi trùng lặp có thể tạo tải không cần thiết.

Các hook giúp quan sát số lần subscription và vòng đời:

~~~java
Flux<OrderEvent> observed =
    repository.loadRecentEvents()
        .doOnSubscribe(subscription ->
            metrics.incrementSourceSubscriptions()
        )
        .doFinally(signalType ->
            metrics.recordSourceTermination(signalType)
        );
~~~

**doOnSubscribe** chạy cho mỗi subscription đi qua vị trí đặt hook. **doFinally** quan sát cách mỗi subscription kết thúc, chẳng hạn hoàn tất, lỗi hoặc bị hủy. Đặt hook trước hay sau một toán tử chia sẻ sẽ làm thay đổi ý nghĩa số liệu được ghi nhận.

### 4. Nguồn nóng có thể phát độc lập với subscriber

Nguồn nóng (hot publisher) có thể phát dữ liệu theo đồng hồ, callback, message broker hoặc một luồng sự kiện đang hoạt động. Subscriber đăng ký vào nguồn chỉ nhận những tín hiệu mà nguồn phát trong thời gian subscription của nó có hiệu lực, trừ khi nguồn có cơ chế lưu và phát lại.

Ví dụ một nguồn giá đang phát liên tục:

~~~java
Flux<PriceUpdate> livePrices = priceFeed.liveUpdates();

livePrices.subscribe(this::updateChart);

// Subscriber thứ hai có thể đăng ký muộn hơn.
livePrices.subscribe(this::checkPriceAlert);
~~~

Nếu **liveUpdates()** trả về một hot publisher không replay, subscriber thứ hai có thể bỏ lỡ những cập nhật đã phát trước lúc đăng ký. Vì vậy, việc hai biến cùng tham chiếu một publisher không tự bảo đảm hai subscriber nhìn thấy cùng toàn bộ lịch sử dữ liệu.

Khi thiết kế consumer cho nguồn nóng, cần xác định rõ có cần snapshot ban đầu, lưu giữ sự kiện, replay theo offset hay chỉ cần nhận dữ liệu mới từ thời điểm đăng ký. Đây là một phần của hợp đồng nguồn dữ liệu, không thể suy ra chỉ từ kiểu **Flux<T>**.

### 5. Một nguồn cấp dữ liệu cho nhiều nhánh xử lý

Một sự kiện có thể cần kích hoạt nhiều công việc. Ví dụ, khi nhận sự kiện đơn hàng đã thanh toán, hệ thống cần tạo dữ liệu cho hóa đơn và đồng thời ghi audit. Nếu mỗi nhánh tự subscribe vào một publisher lạnh, nguồn có thể bị đọc hai lần.

Toán tử **publish(Function)** cho phép tạo một phạm vi chia sẻ: Reactor đăng ký một lần vào nguồn upstream rồi cung cấp publisher được chia sẻ cho các nhánh bên trong hàm:

~~~java
record OrderEvent(String orderId, boolean paid) {}

record ProcessingResult(String branch, String orderId) {}

Flux<ProcessingResult> results =
    repository.orderEvents()
        .doOnSubscribe(subscription ->
            log.info("Đăng ký nguồn đơn hàng")
        )
        .doOnNext(metrics::recordReceived)
        .publish(shared ->
            Flux.merge(
                shared
                    .filter(OrderEvent::paid)
                    .map(event ->
                        new ProcessingResult("BILLING", event.orderId())
                    ),
                shared
                    .map(event ->
                        new ProcessingResult("AUDIT", event.orderId())
                    )
            )
        );

results.subscribe(this::handleResult);
~~~

Trong ví dụ, **shared** là luồng được chia sẻ cho hai nhánh. Nhánh **BILLING** chỉ giữ sự kiện đã thanh toán; nhánh **AUDIT** nhận mọi sự kiện. **Flux.merge** hợp nhất kết quả của hai nhánh thành một luồng đầu ra. Nguồn repository chỉ có một subscription trong phạm vi **publish(Function)**, nên việc đọc và hook đặt trước điểm chia sẻ chạy một lần cho mỗi sự kiện nguồn. Các phép biến đổi nằm trong từng nhánh chạy theo dữ liệu mà nhánh đó nhận được.

**merge** phát kết quả theo thời điểm các nhánh phát ra, vì vậy thứ tự xen kẽ giữa kết quả BILLING và AUDIT không nhất thiết cố định. Nếu nghiệp vụ yêu cầu thứ tự toàn cục hoặc một nhánh phải hoàn thành trước nhánh khác, cần chọn toán tử điều phối phù hợp thay vì giả định **merge** giữ thứ tự giữa các nhánh.

Vì các nhánh cùng tham gia một luồng multicast, nhu cầu của downstream cũng ảnh hưởng đến nguồn chung. Toán tử **publish(Function)** điều phối demand giữa các nhánh; nếu một nhánh chưa có nhu cầu nhận thêm, việc phát upstream có thể tạm dừng cho đến khi nhánh đó sẵn sàng. Một nhánh xử lý chậm vì thế có thể ảnh hưởng tốc độ của các nhánh còn lại. Cần thiết kế buffer hoặc chính sách xử lý riêng khi các nhánh có yêu cầu tốc độ rất khác nhau.

### 6. Phân biệt chia nhánh với flatMap

Chia một nguồn cho nhiều nhánh xử lý và ánh xạ mỗi phần tử sang một publisher là hai cấu trúc khác nhau.

| Cấu trúc | Quan hệ được mô tả | Toán tử thường dùng |
| --- | --- | --- |
| Fan-out từ một nguồn | Một sự kiện có thể đi qua nhiều nhánh xử lý độc lập | **publish(Function)**, **share()**, **ConnectableFlux** |
| Ánh xạ bất đồng bộ từng phần tử | Mỗi phần tử khởi tạo một publisher con, các kết quả được hợp nhất | **flatMap** |
| Xử lý tuần tự từng phần tử bất đồng bộ | Chờ publisher con hiện tại hoàn tất rồi xử lý phần tử kế tiếp | **concatMap** |

Ví dụ **flatMap**:

~~~java
Flux<Invoice> invoices =
    repository.orderEvents()
        .filter(OrderEvent::paid)
        .flatMap(event -> invoiceService.createInvoice(event));
~~~

Ở đây, mỗi sự kiện đã thanh toán tạo một publisher con từ **createInvoice**. **flatMap** đăng ký các publisher con và hợp nhất kết quả; nó không có nghĩa là ta đã tạo hai nhánh độc lập cùng quan sát một nguồn. Có thể giới hạn số publisher con hoạt động đồng thời bằng tham số concurrency của **flatMap** khi cần kiểm soát tải.

### 7. Chia sẻ subscription giữa nhiều subscriber

Khi nhiều thành phần độc lập cần cùng tiêu thụ một nguồn, có thể dùng **share()**:

~~~java
Flux<OrderEvent> sharedEvents =
    repository.orderEvents()
        .doOnSubscribe(subscription ->
            log.info("Upstream được đăng ký")
        )
        .share();

sharedEvents
    .filter(OrderEvent::paid)
    .subscribe(this::createBillingTask);

sharedEvents
    .subscribe(this::writeAuditRecord);
~~~

**share()** cho phép các subscriber đang cùng tham gia nhận dữ liệu từ một subscription upstream được chia sẻ. Nguồn bắt đầu khi subscriber đầu tiên tham gia. Với ngữ nghĩa ref-count mặc định, khi subscriber cuối cùng hủy, kết nối upstream có thể bị hủy. Vì đây là chia sẻ luồng đang chạy, subscriber đến muộn không tự động nhận lại các phần tử đã phát trước đó.

Hai lời gọi subscribe trong ví dụ cần tham gia cùng thời gian để cùng quan sát một luồng. Nếu nguồn đồng bộ phát và hoàn tất ngay trong subscriber đầu tiên trước khi subscriber thứ hai đăng ký, subscriber thứ hai có thể không tham gia được luồng đó. Với nguồn bất đồng bộ kéo dài, hãy quản lý thời điểm đăng ký của các consumer để chúng cùng tham gia trước khi dữ liệu cần chia sẻ được phát.

Nếu cần replay lịch sử cho subscriber đến muộn, có thể cân nhắc **cache()** hoặc các biến thể replay có giới hạn. Cache có thể giữ phần tử trong bộ nhớ; cần chọn giới hạn số lượng hoặc thời gian lưu phù hợp với kích thước dữ liệu và vòng đời ứng dụng. Chia sẻ trực tiếp và replay là hai chính sách khác nhau.

### 8. Điều khiển thời điểm kết nối với ConnectableFlux

Khi cần quyết định rõ thời điểm nguồn bắt đầu phát, Reactor cung cấp **ConnectableFlux**. Toán tử **publish()** tạo publisher có thể chờ lệnh **connect()**:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.ConnectableFlux;

ConnectableFlux<OrderEvent> connectable =
    repository.orderEvents().publish();

connectable
    .filter(OrderEvent::paid)
    .subscribe(this::createBillingTask);

connectable
    .subscribe(this::writeAuditRecord);

// Chỉ bắt đầu kết nối với nguồn sau khi các nhánh đã đăng ký.
Disposable connection = connectable.connect();
~~~

Cách này hữu ích khi cần bảo đảm các nhánh đã đăng ký trước khi nguồn bắt đầu phát. Đối tượng trả về từ **connect()** cho phép quản lý kết nối. Nếu ứng dụng cần tự động kết nối sau khi đủ subscriber hoặc tự ngắt khi số subscriber giảm, có thể xem xét **autoConnect(n)** hoặc **refCount(n)** theo vòng đời mong muốn.

**autoConnect(n)** kết nối sau khi có đủ số subscriber và thường giữ kết nối cho đến khi nguồn kết thúc hoặc kết nối được quản lý riêng. **refCount(n)** cũng đợi đủ subscriber nhưng quản lý kết nối dựa trên số subscriber đang tham gia; khi số lượng giảm dưới ngưỡng, upstream có thể bị ngắt. Hãy chọn theo yêu cầu về khởi động, chia sẻ và dừng nguồn.

### 9. Cancellation lan truyền qua đồ thị subscription

Khi subscriber cuối gọi **dispose()** hoặc hủy subscription, yêu cầu cancellation được truyền ngược về upstream. Tuy nhiên, kết quả cụ thể phụ thuộc cấu trúc chia sẻ:

- Với một pipeline tuyến tính, cancellation thường đi ngược qua các toán tử để nguồn dừng việc phát cho subscription đó.
- Với một nguồn được chia sẻ cho nhiều nhánh còn hoạt động, một nhánh dừng không nhất thiết làm nguồn upstream dừng ngay; các nhánh còn lại vẫn cần dữ liệu.
- Với **share()** hoặc **refCount**, upstream thường chỉ bị hủy khi số subscriber còn lại giảm xuống dưới ngưỡng kết nối.
- Với **publish(Function)**, khi publisher kết quả của hàm kết thúc hoặc bị hủy, phạm vi chia sẻ được dọn dẹp; một nhánh hoàn tất riêng không nhất thiết kết thúc các nhánh còn lại.

Vì vậy, không nên gắn vòng đời nguồn với một nhánh riêng nếu các nhánh khác còn phụ thuộc vào nguồn. Hãy xác định thành phần nào sở hữu subscription chung và thành phần nào chỉ sở hữu nhánh xử lý của mình.

### 10. Vị trí đặt side effect và hook quan sát

Vị trí đặt side effect trong đồ thị có ảnh hưởng đến số lần thực thi:

~~~java
Flux<OrderEvent> source =
    repository.orderEvents()
        .doOnNext(event -> metrics.recordSourceEvent(event));

Flux<ProcessingResult> sharedResults =
    source.publish(shared ->
        Flux.merge(
            shared.map(this::toBillingResult),
            shared.map(this::toAuditResult)
        )
    );
~~~

Hook **doOnNext** nằm trước điểm chia sẻ nên ghi nhận một lần cho mỗi phần tử nguồn. Nếu đặt một hook riêng trong mỗi nhánh, nó chạy theo số phần tử mà từng nhánh nhận. Tương tự, **doOnSubscribe** trước điểm chia sẻ quan sát subscription upstream; đặt sau điểm chia sẻ sẽ quan sát subscription của từng nhánh hoặc subscriber downstream.

Các hook như **doOnSubscribe**, **doOnCancel** và **doFinally** hữu ích để ghi log và metric về vòng đời. Chúng không nên thay thế việc quản lý subscription rõ ràng. Đặc biệt, tránh gọi **subscribe()** lồng bên trong một dịch vụ chỉ để khởi động nhánh phụ; cách làm đó tạo subscription tách rời, khiến lỗi, cancellation và tài nguyên khó được điều phối cùng pipeline chính.

### 11. Kiểm thử số lần đăng ký nguồn và các nhánh

Có thể dùng **defer** cùng bộ đếm để xác nhận nguồn chỉ được đăng ký một lần trong phạm vi chia sẻ:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

AtomicInteger sourceSubscriptions = new AtomicInteger();

Flux<Integer> source =
    Flux.defer(() -> {
        sourceSubscriptions.incrementAndGet();
        return Flux.range(1, 3);
    });

Flux<Integer> branched =
    source.publish(shared ->
        Flux.merge(
            shared.map(value -> value * 10),
            shared.map(value -> value * 100)
        )
    );

StepVerifier.create(branched)
    .expectNextCount(6)
    .verifyComplete();

assertEquals(1, sourceSubscriptions.get());
~~~

Hai nhánh cùng nhận ba phần tử từ một subscription nguồn; **merge** tạo sáu kết quả. Bộ đếm xác nhận supplier của **defer** chỉ chạy một lần trong lần đăng ký vào **branched** đó. Nếu thay cấu trúc bằng hai pipeline lạnh độc lập rồi subscribe riêng, nguồn có thể được đăng ký hai lần.

Khi kiểm thử nguồn nóng hoặc **share()**, cần điều khiển thời điểm đăng ký và phát dữ liệu. Nếu không, bài kiểm thử có thể phụ thuộc vào thứ tự lập lịch và subscriber nào tham gia trước. Có thể dùng **Sinks.Many** trong kiểm thử để chủ động phát sự kiện sau khi đã thiết lập các subscriber.

### 12. Nguyên tắc thiết kế

Khi theo dõi quan hệ giữa subscription, nguồn và các nhánh, hãy trả lời các câu hỏi:

- Nguồn là cold hay hot? Mỗi subscription có tạo lần đọc hoặc tác vụ mới không?
- Có bao nhiêu subscriber độc lập, và chúng có cần cùng một lần thực thi upstream không?
- Nhiều nhánh có cần nhận cùng một sự kiện hay mỗi phần tử cần tạo publisher con?
- Subscriber đến muộn có cần nhận lịch sử hay chỉ nhận dữ liệu mới?
- Khi một nhánh hủy, các nhánh khác và nguồn chung cần tiếp tục hay dừng?
- Side effect và hook quan sát được đặt trước hay sau điểm chia sẻ?
- Thành phần nào sở hữu subscription và chịu trách nhiệm dispose khi dừng?

Trong Project Reactor, subscription là lần tiêu thụ cụ thể, source quyết định dữ liệu được tạo và vòng đời phát, còn các toán tử chia sẻ hoặc phân nhánh xác định cách nhiều consumer phối hợp. Nắm được đồ thị này giúp tránh đọc nguồn trùng lặp, không bỏ lỡ sự kiện từ hot publisher, quản lý cancellation đúng phạm vi và kiểm soát side effect trong các pipeline Java bất đồng bộ.
