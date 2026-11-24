# Tránh giữ tham chiếu qua bộ nhớ đệm, nhóm và nguồn dùng chung

Trong ứng dụng reactive, một pipeline có thể giữ dữ liệu trong bộ nhớ lâu hơn thời gian xử lý một phần tử. Điều này thường xảy ra khi dùng bộ nhớ đệm để phát lại dữ liệu, phân nhóm sự kiện theo khóa, chia sẻ một nguồn cho nhiều Subscriber hoặc giữ một subscription sau khi thành phần sử dụng nó đã kết thúc.

Vấn đề không chỉ nằm ở số lượng phần tử. Một phần tử có thể giữ tham chiếu đến cả object graph lớn như request, session, entity có nhiều quan hệ hoặc buffer chứa payload. Khi một cache, nhóm hoặc callback còn tham chiếu đến phần tử đó, garbage collector không thể thu hồi các object còn reachable từ nó.

Trong Project Reactor, quản lý bộ nhớ vì vậy cần xem xét cả dữ liệu được phát và các đối tượng giữ dữ liệu: `Flux`, `GroupedFlux`, cache, replay buffer, queue, Subscriber, closure và subscription. Mục tiêu là xác định rõ dữ liệu nào cần được giữ, giữ trong bao lâu, giới hạn bao nhiêu phần tử và thành phần nào chịu trách nhiệm kết thúc việc tiêu thụ.

Các kiểu như `AuditEvent`, `Customer`, `Quote`, `Notification`, `UserEvent` và các service trong ví dụ là kiểu miền minh họa do ứng dụng định nghĩa; những đoạn mã rút gọn giả định đã khai báo các import cần thiết.

## 1. Vì sao một pipeline có thể giữ tham chiếu?

Java chỉ thu hồi một object khi object đó không còn reachable từ các GC root. Một object có thể đã được xử lý xong ở một bước nhưng vẫn còn được tham chiếu bởi một thành phần khác.

Ví dụ, một sự kiện đã được gửi đến giao diện nhưng vẫn nằm trong cache phát lại. Hoặc một nhóm theo `customerId` vẫn tồn tại vì nguồn sự kiện chưa kết thúc. Hoặc callback đăng ký với nguồn dùng chung vẫn giữ tham chiếu đến controller đã đóng.

Một số vị trí thường giữ tham chiếu:

| Vị trí | Vì sao dữ liệu còn được giữ? | Dấu hiệu cần quan sát |
|---|---|---|
| `cache()` hoặc replay buffer | Giữ tín hiệu để phát lại cho Subscriber đến sau. | Số phần tử hoặc retained heap tăng theo thời gian. |
| `groupBy()` | Duy trì nhóm theo khóa và luồng phần tử của từng nhóm. | Số khóa khác nhau tăng hoặc nhóm không được tiêu thụ. |
| Nguồn dùng chung | Giữ upstream và các Subscriber đang kết nối. | Subscription sống lâu hơn vòng đời màn hình hoặc request. |
| Queue của toán tử | Giữ phần tử đang chờ scheduler hoặc Publisher con xử lý. | Queue tăng khi downstream chậm. |
| Closure và callback | Lambda có thể giữ object bên ngoài mà nó tham chiếu. | Controller, request hoặc session vẫn reachable sau khi đóng. |
| `collectList()` và `buffer()` | Giữ nhiều phần tử cho đến khi batch hoặc nguồn hoàn tất. | Bộ nhớ tăng theo kích thước luồng hoặc batch. |

Không phải mọi tham chiếu tồn tại lâu đều là rò rỉ bộ nhớ. Cache giữ dữ liệu theo chính sách là hành vi có chủ đích. Nó trở thành vấn đề khi thời gian giữ, số lượng phần tử hoặc phạm vi dữ liệu vượt quá yêu cầu nghiệp vụ và năng lực bộ nhớ.

## 2. Cache và replay có thể giữ toàn bộ lịch sử

`cache()` biến một Publisher thành nguồn có khả năng phát lại tín hiệu đã lưu cho Subscriber đăng ký sau. Với `Flux`, overload không giới hạn lịch sử có thể giữ tất cả phần tử đã phát cho đến khi nguồn kết thúc và giữ các tín hiệu terminal để phát lại.

Ví dụ:

~~~java
Flux<AuditEvent> cachedEvents = auditClient.stream()
    .cache();
~~~

Nếu `auditClient.stream()` là một nguồn dài hạn, số sự kiện được giữ có thể tăng liên tục. Một luồng sự kiện có hàng triệu phần tử sẽ khiến cache giữ một lượng lớn object và các object mà chúng tham chiếu.

Khi chỉ cần phát lại một phần lịch sử gần nhất, hãy dùng giới hạn số phần tử:

~~~java
Flux<AuditEvent> recentEvents = auditClient.stream()
    .cache(200);
~~~

`cache(200)` giới hạn lịch sử được giữ ở 200 phần tử gần nhất. Đây là giới hạn theo số phần tử, không phải theo tổng byte. Nếu mỗi `AuditEvent` chứa payload lớn, 200 phần tử vẫn có thể chiếm nhiều bộ nhớ.

Với một kết quả đơn như thông tin khách hàng, có thể dùng TTL:

~~~java
Mono<Customer> customer = customerRepository.findById(customerId)
    .cache(Duration.ofMinutes(2));
~~~

Kết quả của `Mono` được chia sẻ và cache theo thời gian sống đã cấu hình. TTL phù hợp khi dữ liệu có thể tái sử dụng trong một khoảng ngắn và chấp nhận độ mới tương ứng. Nếu dữ liệu thay đổi cần được phản ánh ngay, phải có chiến lược invalidation hoặc không cache ở tầng này.

Cache này gắn với chính instance `Mono` được tạo ra. Nếu mỗi lần gọi phương thức lại tạo một pipeline `Mono` mới, các lần gọi đó không tự động dùng chung một cache; muốn cache theo ID giữa nhiều lần gọi, ứng dụng cần giữ và quản lý các entry theo khóa với chính sách eviction phù hợp.

Một số nguyên tắc khi dùng cache:

- Chọn rõ giới hạn lịch sử hoặc TTL thay vì mặc định giữ vô hạn.
- Đánh giá kích thước object, không chỉ số phần tử.
- Không cache toàn bộ event stream dài hạn chỉ để tránh đăng ký lại.
- Xác định khi nào dữ liệu cũ cần được invalidated.
- Không giữ cache theo từng request nếu không có giới hạn về số request và thời gian sống.
- Theo dõi số entry, hit/miss, eviction và retained heap.

`cache(200)` giới hạn số phần tử replay, nhưng không thay thế một cache nghiệp vụ có chính sách TTL, kích thước byte, invalidation và eviction theo khóa. Khi cần cache theo ID, hãy chọn một cơ chế có giới hạn rõ ràng và quản lý vòng đời entry ở tầng phù hợp.

## 3. Phân biệt cache với chia sẻ nguồn

`cache` và `share` đều có thể giúp nhiều Subscriber dùng chung một nguồn, nhưng mục đích và hành vi lưu dữ liệu khác nhau.

~~~java
Flux<Quote> cachedQuotes = quoteClient.stream()
    .cache(100);

Flux<Quote> sharedQuotes = quoteClient.stream()
    .share();
~~~

| Cơ chế | Subscriber đến sau | Lịch sử được giữ | Vòng đời nguồn |
|---|---|---|---|
| `cache(100)` | Nhận tối đa 100 phần tử gần nhất đã cache rồi tiếp tục theo nguồn. | Có, giới hạn theo số phần tử. | Cache giữ và phát lại dữ liệu theo chính sách của toán tử. |
| `share()` | Tham gia luồng đang chia sẻ; không nhận lại toàn bộ lịch sử trước khi đăng ký. | Không dùng làm replay cache. | Kết nối được chia sẻ theo Subscriber đang tham gia; khi không còn Subscriber, nguồn đang hoạt động có thể bị hủy theo semantics của `share`. |

`share()` phù hợp khi nhiều thành phần cần cùng quan sát một luồng sự kiện đang diễn ra và không cần phát lại toàn bộ lịch sử. Nó không thay thế cache nếu Subscriber đến sau cần dữ liệu cũ.

Có thể đặt ngưỡng Subscriber trước khi kết nối nguồn bằng `publish().refCount(n)`:

~~~java
Flux<Quote> quotesForDashboard = quoteClient.stream()
    .publish()
    .refCount(2);
~~~

Trong ví dụ, nguồn được kết nối khi có đủ hai Subscriber. Chính sách `refCount` quản lý kết nối dựa trên số Subscriber; khi số Subscriber giảm dưới ngưỡng, kết nối upstream có thể bị hủy. Cần chọn ngưỡng phù hợp với vòng đời các thành phần tiêu thụ và kiểm thử tình huống Subscriber đến muộn hoặc rời đi.

Đừng chọn `cache()` chỉ vì muốn tránh tạo nhiều subscription. Nếu mục tiêu chỉ là chia sẻ một luồng trực tiếp giữa các Subscriber đang hoạt động, `share()` có thể phù hợp hơn. Nếu cần phát lại lịch sử, dùng cache hoặc replay có giới hạn.

## 4. Replay buffer của Sinks cũng là một nơi giữ dữ liệu

Reactor Sinks có thể phát sự kiện đến nhiều Subscriber. Với replay sink, dữ liệu cũ được giữ để Subscriber đăng ký sau có thể nhận lại.

~~~java
Sinks.Many<Notification> notifications =
    Sinks.many().replay().limit(100);
~~~

Sink này giữ một lịch sử giới hạn 100 notification gần nhất. Nếu dùng:

~~~java
Sinks.Many<Notification> notifications =
    Sinks.many().replay().all();
~~~

toàn bộ lịch sử được giữ để phát lại. Với nguồn hoạt động lâu dài, replay không giới hạn có thể làm bộ nhớ tăng liên tục.

Chọn loại sink theo yêu cầu:

- Dùng multicast khi các Subscriber hiện tại cần nhận sự kiện mới và không cần phát lại toàn bộ lịch sử.
- Dùng replay giới hạn khi Subscriber mới cần một số sự kiện gần nhất.
- Chỉ dùng replay toàn bộ khi lịch sử thực sự hữu hạn và có giới hạn tài nguyên rõ ràng.

Sinks có thể sống lâu hơn một request hoặc một màn hình, chẳng hạn được giữ trong singleton service. Khi đó, cần đánh giá kích thước replay buffer và object graph của từng payload. Không nên đưa vào sink những object chứa request context, security context hoặc session có vòng đời ngắn nếu Subscriber không cần chúng.

Nếu chỉ cần phát thông báo nhỏ, hãy chuyển object nghiệp vụ lớn thành một event bất biến, chỉ chứa ID và các trường cần thiết. Subscriber có thể tải phần dữ liệu chi tiết khi cần thay vì giữ cả entity graph trong replay buffer.

## 5. groupBy giữ trạng thái theo khóa

`groupBy` tạo một `GroupedFlux` cho mỗi khóa xuất hiện trong nguồn. Các nhóm được duy trì để phân phối phần tử về đúng khóa trong vòng đời của subscription nguồn.

~~~java
Flux<GroupedFlux<String, UserEvent>> groups =
    eventSource.events()
        .groupBy(UserEvent::userId);
~~~

Nếu nguồn chỉ có vài khóa cố định, việc tạo nhóm thường có thể dự đoán. Nhưng nếu nhóm theo ID request, session hoặc user có cardinality rất cao, số nhóm có thể tăng theo thời gian.

Với nguồn dài hạn, một nhóm không tự hoàn tất chỉ vì tạm thời không có sự kiện. Các nhóm thường kết thúc khi nguồn hoàn tất, lỗi hoặc bị hủy. Vì thế, nếu nguồn không bao giờ kết thúc và liên tục xuất hiện khóa mới, cấu trúc nhóm có thể giữ trạng thái lâu dài.

Nên tiêu thụ các nhóm ngay khi chúng được phát:

~~~java
Flux<UserEvent> allEvents = eventSource.events()
    .groupBy(UserEvent::userId)
    .flatMap(group -> group, 64);
~~~

Không nên tạo nhóm rồi lưu tất cả `GroupedFlux` vào một collection toàn cục để xử lý sau. Việc giữ các đối tượng nhóm đồng nghĩa giữ các tham chiếu đến trạng thái và queue liên quan. Hãy dùng `groupBy` khi số lượng khóa có thể kiểm soát và downstream có chiến lược tiêu thụ mọi nhóm.

Nếu chỉ cần xử lý theo từng khoảng thời gian hoặc số lượng phần tử, `window` có thể phù hợp hơn. Nếu cần trạng thái theo ID tồn tại lâu dài, một state store có TTL và eviction thường dễ quản lý hơn việc tạo một `GroupedFlux` vĩnh viễn cho mọi ID.

## 6. Tiêu thụ mọi nhóm và giới hạn concurrency

Một nhóm được phát nhưng không được subscribe có thể giữ phần tử chờ tiêu thụ. Vì vậy, downstream cần tiêu thụ các nhóm với concurrency đủ để tránh nhóm chưa được drain làm đình trệ nguồn.

~~~java
Flux<AccountSummary> summaries = payments
    .groupBy(PaymentEvent::accountId)
    .flatMap(group ->
        group.reduce(BigDecimal.ZERO,
                (sum, event) -> sum.add(event.amount()))
            .map(total -> new AccountSummary(group.key(), total)),
        32
    );
~~~

Giới hạn `32` chỉ là ví dụ. Nếu có nhiều hơn 32 nhóm đồng thời và một số nhóm đang được xử lý không hoàn tất, những nhóm chưa được subscribe có thể tích lũy dữ liệu. Với nguồn dài hạn, `reduce` cũng chờ nhóm hoàn tất mới phát tổng cuối cùng.

Trước khi dùng `groupBy`, cần biết:

- Cardinality tối đa hoặc phạm vi khóa có thể xuất hiện.
- Nhóm có thể sống bao lâu.
- Mọi nhóm có được tiêu thụ không.
- Concurrency có đủ để drain các nhóm đang hoạt động không.
- Dữ liệu trong nhóm có được giữ trong queue quá lâu không.

Không nên tăng concurrency vô hạn để chữa tình trạng đình trệ. Concurrency lớn hơn có thể làm tăng số request đồng thời và lượng dữ liệu đang hoạt động. Hãy giới hạn số khóa, chọn partition hữu hạn hoặc thay đổi mô hình xử lý nếu cardinality không thể kiểm soát.

## 7. Nguồn dùng chung có thể giữ Subscriber và callback

Một nguồn dùng chung thường được giữ trong service sống lâu hơn các request riêng lẻ. Khi một màn hình đăng ký nguồn, callback có thể giữ tham chiếu đến controller hoặc view:

~~~java
final class DashboardController {
    private Disposable subscription;

    void open(Flux<DashboardEvent> events) {
        subscription = events
            .subscribe(this::render);
    }

    void close() {
        if (subscription != null) {
            subscription.dispose();
            subscription = null;
        }
    }

    private void render(DashboardEvent event) {
        // Cập nhật giao diện.
    }
}
~~~

Lambda `this::render` giữ tham chiếu đến instance `DashboardController`. Nếu subscription vẫn sống sau khi màn hình đóng, nguồn dùng chung có thể tiếp tục giữ controller và các object mà controller tham chiếu.

Hãy gắn subscription với đúng vòng đời của thành phần:

- Lưu handle do `subscribe` trả về.
- Dispose khi màn hình, request hoặc tác vụ kết thúc.
- Đặt handle về `null` sau khi hủy nếu thành phần còn sống.
- Tránh đăng ký nhiều lần khi mở lại cùng một thành phần mà không hủy đăng ký cũ.
- Không lưu callback hoặc Subscriber vào registry toàn cục nếu không có cơ chế unregister.

Closure cũng có thể vô tình giữ cả object graph lớn:

~~~java
RequestContext context = currentRequestContext();

Flux<Result> result = source
    .map(value -> transform(value, context));
~~~

Nếu pipeline được lưu trong một cache hoặc service lâu dài, lambda có thể giữ `context` lâu hơn request. Nếu chỉ cần `tenantId` hoặc `locale`, hãy trích xuất giá trị nhỏ, bất biến và truyền giá trị đó thay vì giữ toàn bộ request context.

## 8. Queue và toán tử cũng giữ dữ liệu đang chờ

Ngay cả khi không dùng cache tường minh, các toán tử bất đồng bộ vẫn có thể giữ phần tử trong queue. Ví dụ `publishOn` có prefetch, `flatMap` có nhiều Publisher con và mỗi nhánh có thể có dữ liệu đang chờ.

~~~java
Flux<EnrichedEvent> enriched = source
    .publishOn(Schedulers.parallel(), 32)
    .flatMap(this::enrich, 8, 16);
~~~

Trong ví dụ, dữ liệu có thể được giữ ở queue của `publishOn` và ở các nhánh `flatMap`. Một ước lượng đơn giản về số phần tử đang chờ không thể chỉ nhìn vào một tham số; cần tính đến queue của từng tầng, số nhánh đang hoạt động và kích thước payload.

Các thao tác như `collectList()` giữ tất cả phần tử cho đến khi nguồn hoàn tất:

~~~java
Mono<List<AuditEvent>> allEvents = auditClient.stream()
    .collectList();
~~~

Với nguồn không giới hạn, `collectList()` không thể phát danh sách cuối cùng và danh sách có thể tăng mãi. Chỉ dùng khi nguồn có giới hạn hoặc có một ranh giới batch rõ ràng.

`buffer(n)` giới hạn số phần tử trong mỗi batch, nhưng nếu downstream xử lý batch chậm và có nhiều batch đang chờ thì tổng bộ nhớ vẫn có thể tăng. Cần kết hợp giới hạn demand, concurrency và hàng đợi của tầng tích hợp.

## 9. Giảm kích thước object được giữ

Một cách hiệu quả để giảm retained heap là tránh lưu payload lớn khi chỉ cần một vài trường.

Thay vì cache cả entity có nhiều quan hệ:

~~~java
Flux<CustomerEntity> cachedCustomers = repository.findAll()
    .cache(100);
~~~

có thể chuyển thành DTO nhỏ trước khi cache:

~~~java
record CustomerCard(String id, String displayName) {}

Flux<CustomerCard> recentCustomerCards = repository.findAll()
    .map(customer -> new CustomerCard(
        customer.id(),
        customer.displayName()
    ))
    .cache(100);
~~~

DTO nhỏ giảm số object mà cache giữ lại. Tuy nhiên, nếu `CustomerCard` vẫn giữ tham chiếu đến entity hoặc collection gốc thì lợi ích này không còn. Hãy tạo giá trị độc lập, bất biến và chỉ chứa dữ liệu cần thiết.

Với event stream, ưu tiên event nhỏ như `userId`, `eventType`, `occurredAt` và một vài trường cần thiết. Subscriber có thể truy xuất payload chi tiết theo ID nếu cần.

## 10. Quản lý tài nguyên gắn với subscription

Một số phần tử mang tài nguyên cần được đóng, chẳng hạn file handle, cursor hoặc kết nối. Việc chỉ bỏ tham chiếu đến Publisher không phải lúc nào cũng đủ để đóng tài nguyên đúng cách.

Với tài nguyên đồng bộ, dùng `Flux.using` hoặc `Mono.using` để gắn cleanup với vòng đời subscription:

~~~java
Flux<String> lines = Flux.using(
    () -> openReader(path),
    reader -> readLines(reader),
    reader -> closeQuietly(reader)
);
~~~

Với cleanup bất đồng bộ, có thể dùng `usingWhen`:

~~~java
Mono<Result> result = Mono.usingWhen(
    connectionFactory.create(),
    connection -> query(connection),
    connection -> connection.close(),
    (connection, error) ->
        connection.rollback().then(connection.close()),
    connection -> connection.close()
);
~~~

Cơ chế này gắn việc giải phóng tài nguyên với hoàn tất, lỗi và cancellation. Nó hữu ích khi subscription có thể bị hủy trước khi công việc hoàn tất.

Với phần tử bị loại hoặc bị bỏ khỏi queue, một số toán tử Reactor hỗ trợ discard hook. Có thể dùng `doOnDiscard` khi kiểu dữ liệu cần cleanup và toán tử upstream có hỗ trợ discard:

~~~java
source
    .filter(this::isRequired)
    .doOnDiscard(ReferenceCountedBuffer.class, ReferenceCountedBuffer::release);
~~~

Đặt hook ở vị trí phù hợp theo hướng dẫn của toán tử và kiểu tài nguyên. `doOnDiscard` không phải cơ chế cleanup tổng quát cho mọi object và không thay thế `using`/`usingWhen` đối với tài nguyên có vòng đời rõ ràng.

## 11. Quan sát và chẩn đoán retention

Khi bộ nhớ tăng, trước tiên hãy xác định đó là tăng tạm thời do tải hay retention kéo dài do tham chiếu không được giải phóng.

Các bước điều tra thường hữu ích:

1. Quan sát heap usage, số lượng Subscriber, số nhóm, queue depth và số entry cache.
2. So sánh heap sau khi tải giảm và sau khi các request hoặc màn hình đã kết thúc.
3. Chụp heap dump khi bộ nhớ vẫn cao.
4. Dùng dominator tree và retained size để tìm object giữ nhiều bộ nhớ nhất.
5. Theo đường tham chiếu đến GC root để xác định cache, sink, group, callback hoặc subscription đang giữ object.
6. Kiểm tra object đó có còn thuộc vòng đời nghiệp vụ hay đã bị giữ quá lâu.

Một vài dấu hiệu gợi ý:

| Dấu hiệu | Nơi nên kiểm tra |
|---|---|
| Số lượng event trong heap tăng theo thời gian | `cache()`, replay sink, `collectList()` |
| Số `GroupedFlux` hoặc khóa tăng liên tục | `groupBy()` và cardinality |
| Controller cũ vẫn còn trong heap | Subscriber callback, closure, Disposable chưa dispose |
| Queue tăng khi downstream chậm | `publishOn`, `flatMap`, buffer và nguồn tích hợp |
| Heap không giảm sau khi request kết thúc | Cache theo request, static collection, registry hoặc subscription bị giữ |

Không nên kết luận có memory leak chỉ từ một lần heap tăng. Hãy xem object nào còn reachable, ai giữ tham chiếu và thời gian giữ có phù hợp với chính sách hay không.

## 12. Kiểm thử chính sách giới hạn và vòng đời

Kiểm thử nên xác nhận hành vi có thể quan sát được: cache chỉ phát lại số phần tử đã giới hạn, subscription được hủy khi thành phần đóng và nhóm được tiêu thụ đầy đủ.

Ví dụ kiểm tra giới hạn lịch sử cache:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void cacheChiPhatLaiLichSuDaGioiHan() {
    Flux<Integer> cached = Flux.range(1, 5).cache(2);

    StepVerifier.create(cached)
        .expectNext(1, 2, 3, 4, 5)
        .verifyComplete();

    StepVerifier.create(cached)
        .expectNext(4, 5)
        .verifyComplete();
}
~~~

Subscriber đầu tiên nhận toàn bộ nguồn. Subscriber thứ hai chỉ nhận hai phần tử gần nhất được giữ trong cache, sau đó nhận terminal signal đã cache.

Kiểm thử việc hủy subscription của thành phần:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void dongThanhPhanHuyNguonDangTheoDoi() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Disposable subscription = Flux.<Long>never()
        .doOnCancel(() -> cancelled.set(true))
        .subscribe();

    subscription.dispose();

    assertTrue(cancelled.get());
}
~~~

Với `groupBy`, hãy kiểm thử nguồn có số khóa hữu hạn, xác nhận mọi nhóm được tiêu thụ và luồng hoàn tất. Với nguồn dài hạn, cần kiểm tra chính sách giới hạn cardinality, thời gian sống và cancellation thay vì chỉ xác nhận kết quả của một nguồn nhỏ.

Không nên dùng kiểm thử dựa trên `System.gc()` để chứng minh object đã được thu hồi. Garbage collection không có bảo đảm chạy đúng thời điểm. Để chẩn đoán retention, dùng heap dump, retained size và đường tham chiếu đến GC root.

## 13. Checklist trước khi đưa pipeline vào production

- Cache có giới hạn số phần tử, TTL hoặc chính sách invalidation rõ ràng không?
- Replay sink có giữ lịch sử vô hạn không?
- `share()` hay `cache()` phù hợp với nhu cầu của Subscriber đến sau?
- `groupBy` có cardinality dự đoán được và mọi nhóm đều được tiêu thụ không?
- Subscription có được dispose khi request hoặc màn hình kết thúc không?
- Lambda có giữ request context, session hoặc entity graph lớn không?
- Queue, prefetch, concurrency và buffer có giới hạn phù hợp không?
- Có `collectList()` trên nguồn không giới hạn không?
- Tài nguyên được đóng khi hoàn tất, lỗi và cancellation không?
- Có metric hoặc cách chụp heap dump để xác định retention khi tải tăng không?

Tránh giữ tham chiếu trong pipeline reactive là việc quản lý vòng đời của dữ liệu và Subscriber. Cache cần có giới hạn; replay cần đúng phạm vi; nhóm cần cardinality có thể kiểm soát và phải được tiêu thụ; nguồn dùng chung cần gắn với vòng đời Subscriber; callback cần tránh giữ object graph không cần thiết. Khi các giới hạn này được thiết kế rõ, ứng dụng Java có thể tận dụng Mono, Flux và các cơ chế chia sẻ dữ liệu mà không để bộ nhớ tăng ngoài dự kiến.

