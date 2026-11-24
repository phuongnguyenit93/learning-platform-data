# Loại bỏ phần tử trùng lặp toàn luồng hoặc liền kề

Trong một luồng sự kiện, cùng một thông tin có thể xuất hiện nhiều lần. Một hệ thống nhận thông báo đơn hàng có thể nhận lại cùng `eventId` do cơ chế retry; cảm biến có thể gửi liên tiếp nhiều lần cùng một trạng thái; một nguồn hợp nhất dữ liệu có thể phát lại bản ghi đã gặp trước đó. Loại bỏ phần tử trùng lặp giúp pipeline giảm xử lý dư thừa, nhưng cần xác định rõ “trùng” nghĩa là gì và phạm vi so sánh kéo dài bao lâu.

Trong Project Reactor, hai toán tử thường dùng cho mục đích này là `distinct()` và `distinctUntilChanged()`. `distinct()` loại bỏ một khóa đã xuất hiện ở bất kỳ vị trí nào trước đó trong subscription. `distinctUntilChanged()` chỉ loại bỏ phần tử có khóa giống phần tử liền trước. Hai toán tử có kết quả khác nhau khi một giá trị xuất hiện lại sau một giá trị khác.

Chủ đề này thuộc chương **Biến đổi dữ liệu** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi biến đổi dữ liệu, hãy chọn khóa định danh phù hợp, hiểu chi phí trạng thái mà toán tử giữ lại và kiểm thử cả dữ liệu lẫn thứ tự phát.

## Trùng lặp toàn luồng và trùng lặp liền kề

Xét luồng đầu vào sau:

```text
Input:  A ── B ── A ── C ── C ── B ── A ──|
```

Nếu loại bỏ trùng lặp trên toàn luồng, lần xuất hiện đầu tiên của mỗi giá trị được giữ lại:

```text
distinct():
        A ── B ───────── C ───────────────|
```

Nếu chỉ loại bỏ phần tử trùng với phần tử đứng ngay trước, một giá trị xuất hiện lại sau giá trị khác vẫn được phát:

```text
distinctUntilChanged():
        A ── B ── A ── C ───── B ── A ────|
```

Trong ví dụ, hai `C` liên tiếp được gộp thành một. `A` thứ hai vẫn được giữ vì phần tử ngay trước nó là `B`; `B` ở gần cuối cũng được giữ vì ngay trước nó là `C`.

| Tiêu chí | `distinct()` | `distinctUntilChanged()` |
|---|---|---|
| Phạm vi so sánh | Tất cả khóa đã gặp trong subscription | Chỉ khóa của phần tử trước đó |
| `A, B, A` | `A, B` | `A, B, A` |
| Trạng thái cần giữ | Tập hợp các khóa đã gặp | Một khóa gần nhất |
| Bộ nhớ | Tăng theo số khóa duy nhất | Thường là hằng số theo số phần tử |
| Phù hợp với | Khử sự kiện hoặc định danh đã xử lý trong toàn bộ phạm vi subscription | Gộp các lần phát liên tiếp cùng trạng thái hoặc cùng giá trị |

## `distinct()` loại bỏ khóa đã xuất hiện ở bất kỳ vị trí nào

`Flux.distinct()` so sánh các phần tử theo `equals()` và `hashCode()` của đối tượng. Phần tử đầu tiên được phát; những phần tử bằng một phần tử đã gặp trước đó sẽ bị loại bỏ.

```java
import reactor.core.publisher.Flux;

Flux<String> values = Flux.just("A", "B", "A", "C", "B", "D");

values
    .distinct()
    .subscribe(System.out::println);
```

Kết quả:

```text
A
B
C
D
```

`distinct()` không sắp xếp lại dữ liệu. Nó giữ lần xuất hiện đầu tiên theo thứ tự nguồn và bỏ các lần xuất hiện tiếp theo của cùng một giá trị. Nếu nguồn phát `A, B, A`, kết quả là `A, B`, không phải `A, B, A`.

### Xác định trùng lặp bằng khóa

Trong ứng dụng thực tế, hai object khác nhau có thể biểu diễn cùng một sự kiện nghiệp vụ. Ta thường muốn so sánh theo một khóa ổn định thay vì toàn bộ object. `distinct(keySelector)` nhận hàm trích xuất khóa:

```java
import reactor.core.publisher.Flux;

record OrderEvent(String eventId, String orderId, String status) {}

Flux<OrderEvent> uniqueEvents = incomingEvents()
    .distinct(OrderEvent::eventId);
```

Ở đây, hai `OrderEvent` được xem là trùng nếu có cùng `eventId`, dù `orderId` hoặc `status` khác nhau. Đây là lựa chọn phù hợp khi `eventId` là định danh duy nhất của sự kiện và nguồn có thể gửi lại cùng sự kiện.

Khóa phải phản ánh đúng quy tắc nghiệp vụ. Nếu dùng `orderId` thay cho `eventId`, mọi sự kiện của cùng một đơn hàng sẽ bị xem là trùng, kể cả `ORDER_CREATED`, `PAYMENT_CONFIRMED` và `ORDER_SHIPPED`. Hãy phân biệt định danh sự kiện với định danh thực thể.

Có thể chuẩn hóa khóa trước khi so sánh. Ví dụ, nếu mã thiết bị không phân biệt chữ hoa/chữ thường:

```java
Flux<DeviceEvent> uniqueByDeviceCode = deviceEvents()
    .distinct(event -> event.deviceCode().toUpperCase(Locale.ROOT));
```

`Locale.ROOT` giúp chuẩn hóa theo quy tắc ổn định, không phụ thuộc locale của máy chạy. Chỉ chuẩn hóa khi hợp đồng dữ liệu xác nhận các dạng chữ đó đại diện cho cùng một khóa.

## `distinctUntilChanged()` chỉ so sánh phần tử liền trước

`distinctUntilChanged()` giữ phần tử đầu tiên, sau đó chỉ phát phần tử nếu nó khác phần tử ngay trước theo quy tắc so sánh:

```java
Flux<String> states = Flux.just(
    "IDLE", "IDLE", "RUNNING", "RUNNING", "IDLE", "IDLE"
);

states
    .distinctUntilChanged()
    .subscribe(System.out::println);
```

Kết quả:

```text
IDLE
RUNNING
IDLE
```

Khi trạng thái chuyển từ `RUNNING` về `IDLE`, giá trị `IDLE` được phát lại vì nó khác trạng thái liền trước. Toán tử này phù hợp cho luồng trạng thái giao diện, tín hiệu cảm biến hoặc các cập nhật lặp liên tiếp không làm thay đổi trạng thái.

### So sánh theo khóa với `distinctUntilChanged(keySelector)`

`distinctUntilChanged(keySelector)` cho phép xác định phần nào của object quyết định tính liên tiếp:

```java
record SensorReading(String sensorId, double temperature) {}

Flux<SensorReading> readings = sensorReadings()
    .distinctUntilChanged(SensorReading::temperature);
```

Ví dụ này chỉ phát một số đo nếu nhiệt độ khác số đo liền trước. Nếu cảm biến gửi `21.5, 21.5, 21.7, 21.5`, kết quả giữ `21.5, 21.7, 21.5`. Nó không loại bỏ lần quay lại `21.5` vì giữa hai lần đó có `21.7`.

Đối với sự kiện có nhiều thuộc tính, hãy chọn khóa hoặc giá trị tổng hợp phù hợp. Ví dụ, nếu chỉ quan tâm trạng thái đơn hàng thay đổi liên tiếp:

```java
Flux<OrderEvent> stateChanges = orderEvents()
    .distinctUntilChanged(OrderEvent::status);
```

Lưu ý: đoạn mã này so sánh trạng thái giữa mọi sự kiện liền kề trong một subscription. Nếu luồng chứa sự kiện của nhiều đơn hàng xen kẽ, một trạng thái `PAID` của đơn hàng A có thể được phát lại sau `CREATED` của đơn hàng B. Khi cần so sánh riêng theo từng đơn hàng, phải phân nhóm theo `orderId` hoặc xây dựng trạng thái gần nhất cho từng khóa; `distinctUntilChanged(status)` đơn thuần không duy trì một giá trị gần nhất cho từng thực thể.

### Tùy chỉnh cách xác định hai khóa bằng nhau

Có thể truyền comparator cho `distinctUntilChanged` khi phép so sánh không phải `equals()` mặc định:

```java
Flux<String> normalized = Flux.just("ready", "READY", "Ready", "busy", "BUSY")
    .distinctUntilChanged(String::equalsIgnoreCase);
```

Kết quả là `ready`, `busy`. Comparator nhận khóa trước và khóa hiện tại; trả về `true` nghĩa là hai khóa được xem như giống nhau nên phần tử hiện tại bị bỏ. Nếu cần quy tắc phức tạp, hãy cân nhắc trích xuất khóa đã chuẩn hóa để biểu đạt ý định rõ ràng hơn.

## So sánh object: `equals()` và `hashCode()` phải nhất quán

Khi gọi `distinct()` không truyền key selector, Reactor dựa vào hợp đồng bằng nhau của Java. Nếu một class không override `equals()` và `hashCode()`, hai object có cùng nội dung vẫn có thể bị xem là khác nhau vì phép so sánh mặc định thường dựa trên identity.

Ví dụ dùng `record`:

```java
record ProductCode(String value) {}

Flux<ProductCode> codes = Flux.just(
    new ProductCode("P-01"),
    new ProductCode("P-02"),
    new ProductCode("P-01")
);

codes.distinct().subscribe(System.out::println);
```

`record` tự sinh `equals()` và `hashCode()` dựa trên các thành phần record, nên hai `ProductCode("P-01")` được xem là bằng nhau. Với class thông thường, cần triển khai hai phương thức này nhất quán: nếu `equals()` trả về `true`, `hashCode()` phải trả về cùng giá trị.

Không nên dùng object mutable làm khóa nếu các thuộc tính tham gia `equals()`/`hashCode()` có thể thay đổi sau khi phần tử được đưa vào tập hợp. Thay đổi khóa có thể làm phép tra cứu trong hash set không còn hoạt động như mong muốn. Khóa bất biến như UUID, mã sự kiện hoặc record chỉ chứa dữ liệu bất biến thường an toàn hơn.

## Vòng đời trạng thái và chi phí bộ nhớ

`distinct()` cần nhớ những khóa đã xuất hiện trong suốt subscription hiện tại. Với luồng hữu hạn có kích thước nhỏ, chi phí này thường chấp nhận được. Với luồng vô hạn, tập khóa có thể tăng không giới hạn nếu liên tục có khóa mới:

```text
Nguồn liên tục:  id-1, id-2, id-3, id-4, ...
Trạng thái distinct: {id-1, id-2, id-3, id-4, ...}
```

Nếu mỗi sự kiện có một ID mới, `distinct()` sẽ giữ gần như tất cả ID đã gặp cho đến khi subscription kết thúc. Vì vậy, dùng `distinct()` trên stream dài hạn có thể trở thành nguồn giữ heap. Trước khi chọn toán tử, hãy xác định phạm vi khử trùng lặp: toàn bộ phiên, một cửa sổ thời gian, một batch hay chỉ các phần tử liên tiếp.

Ngược lại, `distinctUntilChanged()` chỉ cần lưu khóa của phần tử gần nhất để so sánh với phần tử kế tiếp. Trạng thái phụ trợ của nó thường có kích thước hằng số theo số phần tử, phù hợp hơn cho stream vô hạn nếu yêu cầu nghiệp vụ chỉ là bỏ các lần phát liên tiếp giống nhau.

### Tùy chỉnh kho khóa của `distinct`

Reactor cho phép tùy chỉnh kho dùng để lưu khóa thông qua overload `distinct` nhận `keySelector`, `storeSupplier`, `distinctPredicate` và `cleanup`. Điều này hữu ích khi cần chọn cấu trúc lưu trữ hoặc cách kiểm tra riêng:

```java
Flux<OrderEvent> unique = orderEvents()
    .distinct(
        OrderEvent::eventId,
        HashSet::new,
        Set::add,
        Set::clear
    );
```

Trong ví dụ, `HashSet` lưu các `eventId`; `Set::add` trả về `true` nếu khóa mới được thêm và `false` nếu khóa đã tồn tại; `Set::clear` dọn kho khi subscription kết thúc. Cần import `java.util.HashSet` và `java.util.Set`. Cấu trúc này vẫn phải lưu mọi khóa duy nhất trong phạm vi subscription, nên không tự giải quyết nguy cơ tăng bộ nhớ. Overload tùy chỉnh chỉ cho phép thay đổi cách lưu và kiểm tra; giới hạn phạm vi dedup vẫn cần được thiết kế riêng.

## Phạm vi theo subscription và vị trí trong pipeline

Trạng thái của các toán tử dedup được tạo cho subscription. Hai Subscriber độc lập đăng ký vào cùng một pipeline có thể có hai tập khóa riêng; mỗi bên thực hiện dedup trên dữ liệu mà subscription của nó quan sát.

Vị trí đặt toán tử cũng làm thay đổi phạm vi chia sẻ. Nếu dedup trước khi multicast, các Subscriber cùng nhận một kết quả đã khử trùng lặp ở upstream. Nếu dedup sau khi chia sẻ, mỗi Subscriber có trạng thái dedup riêng:

```java
Flux<Event> source = eventSource();

// Một lần dedup ở upstream trước khi chia sẻ kết quả
Flux<Event> sharedUnique = source
    .distinct(Event::eventId)
    .publish()
    .refCount(1);

// Mỗi Subscriber tự giữ trạng thái dedup riêng ở downstream
Flux<Event> sharedThenUnique = source
    .publish()
    .refCount(1)
    .distinct(Event::eventId);
```

Trong trường hợp đầu, một subscription upstream thực hiện dedup rồi phân phối kết quả. Trong trường hợp sau, mỗi subscription downstream có thể duy trì tập khóa riêng. Nếu số Subscriber lớn, điều này có thể làm tổng bộ nhớ dedup tăng theo số bên nhận. Hãy đặt toán tử ở ranh giới phù hợp với ý nghĩa nghiệp vụ và vòng đời chia sẻ.

## Dedup trong cửa sổ hoặc theo thời gian

`distinct()` mặc định có phạm vi toàn subscription, không tự xóa khóa sau một khoảng thời gian. Nếu chỉ muốn loại bỏ sự kiện lặp trong một khoảng thời gian hoặc một batch, hãy biểu diễn phạm vi đó rõ ràng. Một cách đơn giản với luồng hữu hạn là chia thành cửa sổ rồi áp dụng `distinct` trong từng cửa sổ:

```java
Flux<Event> perBatchUnique = eventSource()
    .buffer(100)
    .flatMap(batch -> Flux.fromIterable(batch)
        .distinct(Event::eventId));
```

Ví dụ chia nguồn thành batch tối đa 100 phần tử và khử trùng lặp trong từng batch. Cùng một `eventId` có thể xuất hiện lại ở batch kế tiếp. `flatMap` có thể làm thay đổi thứ tự tương đối giữa các batch nếu xử lý bất đồng bộ; nếu cần giữ thứ tự batch, cân nhắc `concatMap`.

Với phạm vi thời gian, có thể kết hợp `window(Duration)` và dedup bên trong từng cửa sổ:

```java
Flux<Event> uniquePerMinute = eventSource()
    .window(Duration.ofMinutes(1))
    .flatMap(window -> window.distinct(Event::eventId));
```

Mỗi cửa sổ có tập khóa riêng, vì vậy khóa cũ không bị giữ mãi sau khi cửa sổ kết thúc. Cần xem xét cách cửa sổ được mở, đóng và phát dữ liệu; `flatMap` cho phép các cửa sổ xử lý xen kẽ, nên nếu thứ tự đầu ra là yêu cầu bắt buộc, dùng cách kết hợp bảo toàn thứ tự phù hợp. Cũng cần quyết định event time hay processing time được dùng để xác định cửa sổ nếu dữ liệu có thể đến muộn.

## Kết hợp với các toán tử khác

Dedup thường được đặt gần bước chuẩn hóa dữ liệu hoặc trước các side effect tốn kém. Ví dụ, chuẩn hóa mã sự kiện rồi loại bỏ ID trùng trước khi ghi database:

```java
Flux<Event> persisted = eventSource()
    .map(this::normalize)
    .distinct(Event::eventId)
    .concatMap(repository::save);
```

`map` chuẩn hóa dữ liệu; `distinct` loại bỏ các ID đã gặp trong subscription; `concatMap` ghi lần lượt để giữ thứ tự xử lý. Tuy nhiên, `distinct` chỉ có phạm vi subscription hiện tại. Nếu ứng dụng khởi động lại hoặc có nhiều instance cùng xử lý sự kiện, dedup trong bộ nhớ không bảo đảm tính duy nhất toàn hệ thống. Với yêu cầu chống xử lý trùng bền vững, cần idempotency key, unique constraint hoặc kho dedup dùng chung ở tầng lưu trữ.

Nếu chỉ muốn bỏ các lần phát liên tiếp cùng trạng thái trước khi cập nhật UI:

```java
Flux<Status> visibleChanges = statusSource()
    .map(this::normalizeStatus)
    .distinctUntilChanged();
```

Đặt `distinctUntilChanged` sau chuẩn hóa giúp các biểu diễn tương đương như `"ready"` và `"READY"` được xem là cùng trạng thái nếu `normalizeStatus` đưa chúng về cùng một dạng.

## Kiểm thử bằng `StepVerifier`

Kiểm thử cần xác nhận phần tử được giữ, phần tử bị loại và tín hiệu kết thúc. Với `distinct()`, kiểm tra trùng lặp ở nhiều vị trí; với `distinctUntilChanged()`, kiểm tra giá trị lặp lại sau một giá trị khác vẫn được phát:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DistinctOperatorsTest {
    @Test
    void distinctRemovesDuplicatesAcrossTheWholeSequence() {
        Flux<String> result = Flux.just("A", "B", "A", "C", "B")
            .distinct();

        StepVerifier.create(result)
            .expectNext("A", "B", "C")
            .verifyComplete();
    }

    @Test
    void distinctUntilChangedRemovesOnlyAdjacentDuplicates() {
        Flux<String> result = Flux.just("A", "A", "B", "A", "A")
            .distinctUntilChanged();

        StepVerifier.create(result)
            .expectNext("A", "B", "A")
            .verifyComplete();
    }
}
```

Có thể kiểm tra khóa tùy chỉnh bằng một test khác để chắc rằng hai object có cùng `eventId` chỉ tạo một đầu ra, kể cả khi các trường khác khác nhau. Nếu dùng comparator, hãy thêm trường hợp biên như chữ hoa/chữ thường hoặc giá trị gần bằng nhau để kiểm chứng quy tắc nghiệp vụ.

Với dedup theo cửa sổ, cần kiểm thử cả hai phía ranh giới: cùng một ID lặp trong một cửa sổ phải bị loại, còn cùng ID ở cửa sổ tiếp theo có được phát lại hay không phải đúng với yêu cầu. Dùng virtual time cho cửa sổ dựa trên thời gian để test nhanh và ổn định.

## Những lỗi thiết kế thường gặp

**Dùng `distinct()` cho luồng vô hạn mà không xét bộ nhớ.** Tập khóa đã gặp tăng theo số giá trị duy nhất. Nếu phạm vi nghiệp vụ chỉ là các phần tử liền kề, `distinctUntilChanged()` thường phù hợp hơn.

**Dùng `distinctUntilChanged()` khi cần khử trùng lặp toàn luồng.** Với `A, B, A`, toán tử này vẫn phát cả hai `A`. Hãy chọn `distinct()` hoặc phạm vi dedup khác nếu cần loại bỏ lần xuất hiện sau.

**Chọn sai khóa.** Dùng `orderId` để khử trùng lặp `OrderEvent` có thể làm mất các chuyển trạng thái hợp lệ của cùng đơn hàng. Chọn `eventId` nếu mục tiêu là loại bỏ bản gửi lại của cùng sự kiện.

**Dựa vào identity của object.** Hai object cùng dữ liệu không nhất thiết bằng nhau nếu class không định nghĩa `equals()`/`hashCode()`. Dùng record bất biến hoặc key selector rõ ràng.

**Dùng khóa mutable.** Thay đổi trường tham gia `hashCode()` sau khi đã lưu vào tập khóa có thể làm hành vi tra cứu sai lệch. Ưu tiên khóa bất biến.

**Cho rằng dedup trong Reactor bảo đảm duy nhất xuyên nhiều instance.** Trạng thái toán tử chỉ tồn tại trong subscription và bộ nhớ của tiến trình. Yêu cầu chống trùng bền vững cần idempotency hoặc ràng buộc ở tầng lưu trữ.

**Đặt dedup sai phía ranh giới chia sẻ.** Đặt trước hay sau `publish()` ảnh hưởng số lần xử lý và số tập khóa được giữ. Hãy chọn vị trí theo phạm vi chia sẻ mong muốn.

## Tự kiểm tra

1. Với đầu vào `A, B, A, C, C, B`, kết quả của `distinct()` và `distinctUntilChanged()` khác nhau thế nào?
2. Vì sao `distinct()` có thể làm tăng heap khi áp dụng cho một Flux vô hạn có nhiều khóa mới?
3. Một luồng sự kiện đơn hàng cần loại bỏ bản gửi lại của cùng sự kiện nhưng vẫn giữ các trạng thái khác nhau của một đơn hàng. Nên chọn khóa nào?
4. Khi nào `distinctUntilChanged(keySelector)` phù hợp hơn `distinct(keySelector)`?
5. Nếu dedup được đặt trước `publish()` thay vì sau `publish()`, trạng thái dedup được chia sẻ ra sao?
6. Vì sao dedup trong một subscription không thay thế unique constraint hoặc idempotency ở database?
7. Làm thế nào kiểm thử rằng một ID có thể xuất hiện lại ở cửa sổ kế tiếp nhưng chỉ một lần trong mỗi cửa sổ?

Khi xác định đúng phạm vi so sánh, khóa nghiệp vụ và vòng đời trạng thái, bạn có thể chọn `distinct()` để loại bỏ khóa đã gặp toàn luồng hoặc `distinctUntilChanged()` để gộp các lần phát liền kề, đồng thời kiểm soát chi phí bộ nhớ và tránh loại bỏ nhầm sự kiện hợp lệ.
