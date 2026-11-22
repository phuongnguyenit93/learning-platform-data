# Vì sao Stream.peek() không phù hợp cho thao tác nghiệp vụ bắt buộc?

## 1. Vấn đề: “đã viết peek” không có nghĩa “đã thực hiện nghiệp vụ”

Trong Java Stream, `peek(Consumer<? super T> action)` là **thao tác trung gian** (*intermediate operation*) chủ yếu hữu ích khi **quan sát** các phần tử đi qua pipeline, thường để gỡ lỗi. Nó không phải một lệnh buộc chương trình thực hiện hành động nghiệp vụ trên từng phần tử.

Ví dụ có vẻ hợp lý nhưng nguy hiểm:

```java
long count = orders.stream()
        .peek(order -> sendInvoice(order))
        .count();
```

Đây là **đoạn minh họa sai về thiết kế**; `orders` và `sendInvoice` là các thành phần giả định của ứng dụng, không phải chương trình độc lập. Ý định là “đếm đơn hàng và gửi hóa đơn cho từng đơn”. Tuy nhiên, **`count()` có thể tính kết quả mà không duyệt các phần tử** khi nguồn biết được kích thước và các bước trong pipeline không thay đổi số phần tử. Khi đó hành động trong `peek` có thể **không được gọi dù `count()` vẫn cho kết quả đúng**.

Đây không phải lỗi ngẫu nhiên của một bản Java; nó phù hợp với **hợp đồng Stream API**. Javadoc nói những side effects trong các behavioral parameters có thể không được thực thi cho mọi phần tử, thậm chí không chạy ở một số giai đoạn, nếu việc thực thi không ảnh hưởng đến kết quả của pipeline. `peek` không phải cơ chế xác nhận đã gửi hóa đơn, cập nhật tồn kho, ghi dữ liệu hay thanh toán.

**Thông điệp cốt lõi:** nếu một hành động là **bắt buộc để nghiệp vụ đúng**, đừng ẩn nó trong `peek()`. Hãy đặt nó vào bước xử lý có chủ đích và cơ chế lỗi/transaction phù hợp.

## 2. peek() thực sự có hợp đồng gì?

Chữ ký của API trong Java 17:

```java
Stream<T> peek(Consumer<? super T> action);
```

Đây là **chữ ký trích để đọc API**, không phải một phương thức cần tự định nghĩa.

`peek`:

- Nhận một `Consumer` (hành động không trả giá trị).
- Trả về một `Stream<T>` để tiếp tục ghép pipeline.
- Về mặt logic, cho phép quan sát các phần tử khi chúng được pipeline xử lý.
- Là một **intermediate operation**, vì vậy riêng việc gọi `peek(...)` không bắt đầu duyệt dữ liệu.
- Không thay đổi phần tử đầu ra theo hợp đồng của chính `peek`; nếu muốn **biến đổi dữ liệu**, dùng `map`.
- Không cung cấp cam kết mọi phần tử đều kích hoạt `action`, cũng không bảo đảm thứ tự hay luồng chạy side effect khi pipeline chạy song song.

Ví dụ quan sát trong giai đoạn phát triển:

```java
List<String> normalized = names.stream()
        .map(String::trim)
        .peek(s -> System.out.println("normalized=" + s))
        .filter(s -> !s.isEmpty())
        .toList();
```

Đây là **đoạn minh họa nằm trong phương thức**, giả sử `names` là một `List<String>` và đã import `List`. Phần `peek` giúp người phát triển quan sát trạng thái trung gian của phần tử khi action được thực thi. Nhưng mã ứng dụng **không nên phụ thuộc** vào việc mỗi dòng log được xuất chính xác một lần và theo đúng thứ tự trong mọi kiểu pipeline.

Cần phân biệt **logging để debug** với **audit log bắt buộc theo pháp lý/nghiệp vụ**. Một bản ghi audit cần được thực hiện có kiểm soát, kiểm tra lỗi và lưu bền vững theo hợp đồng ứng dụng; đó không phải vai trò của `peek`.

## 3. Lý do thứ nhất: Stream lazy, chỉ tạo pipeline chưa chạy gì

Một pipeline Stream thường được mô tả bằng chuỗi các thao tác trung gian. Ví dụ:

```java
List<String> traces = new ArrayList<>();
var pipeline = List.of("An", "Binh", "Chi").stream()
        .peek(traces::add)
        .filter(s -> s.length() > 2);
```

Đây là một đoạn đặt trong phương thức đã import `List`, `ArrayList`. Ngay sau khi tạo `pipeline`, `traces` **vẫn rỗng**: `peek` và `filter` là các bước trung gian lazy.

Khi chạy terminal operation:

```java
List<String> result = pipeline.toList();
```

Trên trường hợp tuần tự cụ thể này, các phần tử được đi qua `peek` trước `filter`, tạo `traces = [An, Binh, Chi]` và `result = [Binh, Chi]`. Nhưng việc thấy action chạy ở tình huống này **không tạo ra bảo đảm tổng quát** rằng nó chạy ở mọi terminal operation, trên mọi nguồn hoặc sau khi pipeline được tối ưu.

Vì thế, câu lệnh `orders.stream().peek(this::persist)` **không làm `persist` chạy ngay**. Nếu ứng dụng không gọi terminal operation, hành động đó có thể không xảy ra lần nào.

## 4. Lý do thứ hai: count() có thể bỏ qua peek() hoàn toàn

Đây là ví dụ quyết định:

```java
List<String> names = List.of("An", "Binh", "Chi");
List<String> observed = new ArrayList<>();

long count = names.stream()
        .peek(observed::add)
        .count();

System.out.println(count);     // 3
System.out.println(observed);  // []
```

Đây là các lệnh thuộc một phương thức đã import `List`, `ArrayList`; kết quả `observed = []` đã được kiểm thử trên Java 17.

Vì sao?

1. `List` cung cấp số lượng phần tử một cách xác định.
2. `peek` không thay đổi số lượng phần tử của stream.
3. `count()` có thể lấy số phần tử từ thông tin kích thước nguồn thay vì duyệt từng phần tử.
4. Nếu không có quá trình duyệt, action của `peek` không chạy.

**Quan trọng:** không phải **mọi** `count()` đều bỏ qua `peek`. Khi pipeline có bước ảnh hưởng đến số phần tử (ví dụ `filter` tùy điều kiện), triển khai có thể cần duyệt để tính count. Nhưng **bất kỳ hành động nghiệp vụ nào bắt buộc chạy không được phụ thuộc vào điều kiện tối ưu này**.

Đặc biệt nguy hiểm:

```text
long total = invoices.stream()
        .peek(invoice -> chargeCustomer(invoice))
        .count();
```

Đây là **mã giả minh họa điều cần tránh**. Nếu `chargeCustomer` là thao tác thanh toán bắt buộc, một terminal operation vẫn có thể thành công khi chưa thanh toán đơn nào. Hơn nữa nếu có lỗi hoặc retry, đặt thanh toán trong pipeline không tự giải quyết được vấn đề giao dịch.

**Không sửa bằng cách thêm một thao tác phụ “để ép peek chạy”**. Chiến lược này vẫn dựa vào side effect không được bảo đảm và rất dễ bị phá khi tối ưu hoặc thay đổi cấu trúc pipeline.

## 5. Lý do thứ ba: short-circuit không xử lý tất cả phần tử

Nhiều terminal operations được phép kết thúc sau khi đã có đủ thông tin:

- `findFirst()`, `findAny()`: tìm được phần tử phù hợp thì không cần đọc hết.
- `anyMatch()`: có một phần tử thỏa thì có thể dừng.
- `allMatch()`: gặp phần tử không thỏa thì có thể dừng.
- `noneMatch()`: gặp phần tử thỏa thì có thể dừng.

Các bước trung gian `limit()` hoặc `takeWhile()` cũng có thể làm số phần tử cần xử lý giảm hoặc dừng sớm theo điều kiện.

Ví dụ:

```java
List<Integer> visited = new ArrayList<>();
int first = List.of(1, 2, 3, 4).stream()
        .peek(visited::add)
        .filter(n -> n > 1)
        .findFirst()
        .orElse(-1);
```

Đây là các lệnh trong thân phương thức đã import `List`, `ArrayList`. Trong ví dụ **sequential ordered** được kiểm thử bằng Java 17, `first = 2` và `visited = [1, 2]`. `3` và `4` không đi qua action của `peek`, vì `findFirst` đã có câu trả lời.

Giả sử `peek` gửi thông báo cho mọi người dùng, nhưng terminal operation bên dưới chỉ cần kiểm tra xem **có ít nhất một** người dùng hay không. Pipeline có thể thành công **trước khi** tất cả thông báo được gửi. Đó là sai về nghiệp vụ.

Điểm then chốt: **terminal operation thành công không đồng nghĩa mọi phần tử đã chạy qua peek**. Điều này càng quan trọng khi pipeline có nguồn vô hạn hoặc phép toán cho phép dừng sớm.

## 6. Lý do thứ tư: song song, thứ tự và tác dụng phụ

Với `parallelStream()`, các stage có thể thực hiện trên nhiều luồng, và thứ tự thực tế của side effects trong `peek` **không phải lúc nào cũng theo encounter order**. Ngay cả khi kết quả cuối tôn trọng thứ tự ở nơi cần thiết, việc in log hoặc cập nhật trạng thái dùng chung bên trong `peek` có thể quan sát được theo thứ tự khác.

Ví dụ **không nên dùng làm nghiệp vụ**:

```text
List<String> audit = new ArrayList<>();
orders.parallelStream()
        .peek(o -> audit.add("AUDIT:" + o.id()))
        .forEach(o -> doWork(o));
```

Đây là mã giả minh họa với `orders` và `doWork` giả định. `ArrayList` không được bảo vệ khi nhiều luồng ghi đồng thời; chương trình có thể gặp race condition hoặc kết quả không đầy đủ. Việc dùng `Collections.synchronizedList` hoặc cấu trúc đồng bộ chỉ giải quyết **một phần** vấn đề data race, **không sửa** sai lầm là đặt hành động audit bắt buộc vào `peek`.

Trong các thao tác song song:

- **Thứ tự gọi side effect không được mặc nhiên bảo đảm**, kể cả với nguồn có encounter order.
- Các `Consumer` đụng tới trạng thái dùng chung có thể cần đồng bộ hóa; nhưng đồng bộ hóa không tự bảo đảm exactly-once ở hệ thống ngoài.
- Exception ở một luồng có thể làm terminal operation thất bại; không được suy luận rằng mọi side effect khác đã hoàn tất hoặc đã được rollback.
- Một phần tử có thể chưa được xử lý khi pipeline short-circuit. Không nên dùng `peek` làm nơi duy nhất thực hiện hành động cần chứng cứ hoàn thành.

`forEachOrdered` là một lựa chọn terminal operation khi phải **thực hiện action theo encounter order**, nhưng nếu action là ghi DB, gửi email hoặc thanh toán, **vẫn cần quản lý retry, idempotency, transaction và lỗi** riêng.

## 7. Phân biệt peek(), map(), filter(), forEach() và forEachOrdered()

| API | Loại thao tác | Vai trò | Có nên chứa thao tác nghiệp vụ bắt buộc? |
| --- | --- | --- | --- |
| `peek(action)` | Trung gian | Quan sát phần tử, chủ yếu debug | **Không** |
| `map(transform)` | Trung gian | Chuyển phần tử `T → R` | **Không** nên nhúng side effects bắt buộc; dùng cho phép biến đổi dữ liệu |
| `filter(predicate)` | Trung gian | Giữ phần tử thỏa điều kiện | **Không** dùng predicate để thực hiện side effects |
| `forEach(action)` | Kết thúc | Thực hiện action trên các phần tử của stream | Có thể dùng khi action là mục tiêu xử lý, nhưng không tự bảo đảm giao dịch/đúng một lần |
| `forEachOrdered(action)` | Kết thúc | Thực hiện action theo encounter order nếu stream có thứ tự | Hữu ích khi thứ tự quan trọng; vẫn cần thiết kế nghiệp vụ |
| `toList()` | Kết thúc | Thu kết quả tính toán thành List | Thích hợp để tách bước chuẩn bị và bước thực thi nghiệp vụ |
| Vòng lặp `for` | Không phải Stream | Thực thi tường minh theo thứ tự lập trình | Thường rõ ràng nhất khi mỗi hành động cần xử lý lỗi và trạng thái riêng |

`map` có thể chạy zero hoặc nhiều lần tùy terminal operation; ngay cả khi nó thường được thực thi trong `toList()`, bạn không nên biến nó thành nơi thanh toán. `map` phù hợp để **tạo dữ liệu** chuẩn bị cho thao tác tiếp theo. Nếu code cần làm điều bắt buộc, nên viết ra một bước riêng có tên và hợp đồng rõ ràng.

`forEach`/`forEachOrdered` là terminal operations thể hiện ý định **thực hiện hành động**, không phải “biến side effects thành transaction”. Với các thao tác có tác động ngoài hệ thống, caller cần xác định cách xử lý khi action thứ ba ném exception sau khi hai action trước đã thành công.

## 8. Chương trình Java 17: quan sát hành vi và phương án thay thế

Tạo tệp `PeekBusinessSafetyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class PeekBusinessSafetyDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        List<String> observed = new ArrayList<>();
        long count = names.stream().peek(observed::add).count();
        System.out.println("count=" + count);
        System.out.println("observedByPeek=" + observed);

        List<String> lazyObserved = new ArrayList<>();
        var pipeline = names.stream()
                .peek(lazyObserved::add)
                .filter(s -> s.length() > 2);
        System.out.println("beforeTerminal=" + lazyObserved);
        System.out.println("filtered=" + pipeline.toList());
        System.out.println("afterTerminal=" + lazyObserved);

        List<Integer> visited = new ArrayList<>();
        int first = List.of(1, 2, 3, 4).stream()
                .peek(visited::add)
                .filter(n -> n > 1)
                .findFirst()
                .orElse(-1);
        System.out.println("findFirst=" + first);
        System.out.println("visited=" + visited);

        List<String> events = names.stream()
                .map(String::toUpperCase)
                .toList();
        System.out.println("events=" + events);

        List<String> saved = new ArrayList<>();
        for (String event : events) {
            saved.add("saved:" + event);
        }
        System.out.println("saved=" + saved);

        AtomicInteger total = new AtomicInteger();
        names.parallelStream()
                .forEachOrdered(name -> total.incrementAndGet());
        System.out.println("forEachOrderedCount=" + total.get());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 PeekBusinessSafetyDemo.java
java PeekBusinessSafetyDemo
```

Đầu ra **đã kiểm chứng**:

```text
count=3
observedByPeek=[]
beforeTerminal=[]
filtered=[Binh, Chi]
afterTerminal=[An, Binh, Chi]
findFirst=2
visited=[1, 2]
events=[AN, BINH, CHI]
saved=[saved:AN, saved:BINH, saved:CHI]
forEachOrderedCount=3
```

Phân tích:

1. **`count=3`, `observedByPeek=[]`:** đây là ví dụ rõ nhất cho việc `peek` không phải hành động được bảo đảm thực thi.
2. **`beforeTerminal=[]`:** khi chỉ tạo pipeline `peek(...).filter(...)` thì chưa có hành động.
3. **`filtered=[Binh, Chi]` và `afterTerminal=[An, Binh, Chi]`:** ở lần chạy tuần tự này, `toList()` đã kích hoạt việc duyệt và `peek` quan sát từng phần tử trước `filter`.
4. **`findFirst=2`, `visited=[1, 2]`:** terminal operation tìm phần tử đầu đã cho phép kết thúc sớm.
5. **`events` → `saved`:** tạo **dữ liệu biến đổi** bằng `map(...).toList()`, rồi thực hiện một vòng lặp **tường minh**. Nếu đây là thao tác lưu thật, vòng lặp chính là nơi đặt `try/catch`, transaction, logging và policy xử lý lỗi.
6. **`forEachOrderedCount=3`:** terminal `forEachOrdered` được gọi trên stream song song từ List có thứ tự; `AtomicInteger` được dùng minh họa bộ đếm an toàn luồng. Điều này không biến toàn bộ thao tác nghiệp vụ thành exactly-once giữa nhiều lần chạy chương trình.

Trong ví dụ, `ArrayList` dùng để quan sát `peek` chỉ nằm trong các pipeline **tuần tự và có kiểm soát**. Không nên lấy đoạn `observed::add` rồi chuyển sang `parallelStream()` như một cách thu thập kết quả.

## 9. Bài toán nghiệp vụ: lọc/biến đổi trước, sau đó thực thi rõ ràng

Giả sử một chương trình có danh sách đơn hàng. Mục tiêu là chuẩn bị phiếu xử lý cho đơn có số lượng hợp lệ, sau đó thực hiện các lệnh cần thiết. Ta nên tách **bước tính toán** và **bước có side effects**.

Tệp `ExplicitBusinessActionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ExplicitBusinessActionsDemo {
    record Order(int id, int amount) { }
    record Receipt(int id, String status) { }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order(101, 20),
                new Order(102, 0),
                new Order(103, 35));

        List<Receipt> planned = orders.stream()
                .filter(order -> order.amount() > 0)
                .map(order -> new Receipt(order.id(), "READY"))
                .toList();
        System.out.println("planned=" + planned);

        List<String> effects = new ArrayList<>();
        for (Receipt receipt : planned) {
            effects.add("persist:" + receipt.id());
        }
        System.out.println("effects=" + effects);

        List<String> ordered = new ArrayList<>();
        planned.parallelStream()
                .forEachOrdered(receipt -> ordered.add("send:" + receipt.id()));
        System.out.println("ordered=" + ordered);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ExplicitBusinessActionsDemo.java
java ExplicitBusinessActionsDemo
```

Đầu ra:

```text
planned=[Receipt[id=101, status=READY], Receipt[id=103, status=READY]]
effects=[persist:101, persist:103]
ordered=[send:101, send:103]
```

Giải thích:

- Dùng `filter` để chọn các đơn có `amount > 0`; dùng `map` tạo **giá trị** `Receipt`. Không gửi hóa đơn hoặc ghi cơ sở dữ liệu bên trong `peek`.
- `toList()` tạo danh sách `planned` có thể xem, kiểm tra và chuyển cho giai đoạn sau. Vì dữ liệu đầu vào hữu hạn và nhỏ trong ví dụ, materialization phù hợp.
- Vòng `for (Receipt receipt : planned)` là nơi mô hình hóa hành động `persist`, trong ví dụ chỉ thêm chuỗi vào List nên không cần dịch vụ ngoài.
- `forEachOrdered` minh họa thao tác terminal theo encounter order, ngay cả với `parallelStream()`. Mã chỉ ghi chuỗi vào List dùng cho minh họa; **không có kết nối DB hoặc email thật**.

Trong sản phẩm thực, nên thay `effects.add(...)` bằng dịch vụ nghiệp vụ và thiết kế **rõ ràng khi một thao tác thất bại**. Tránh hiểu ví dụ này bảo đảm được tính nguyên tử, bền vững hay exactly-once; nó chủ yếu cho thấy **nơi đặt hành động** hợp lý.

## 10. Vì sao không nên dùng peek() để audit, ghi DB, gửi email hoặc thanh toán?

Xem một hệ thống giả định phải ghi audit cho mỗi đơn đã xử lý. Nếu dùng:

```text
orders.stream()
      .peek(auditService::record)
      .filter(Order::isValid)
      .count();
```

Đây là **mã giả minh họa**, không biên dịch độc lập vì các kiểu/dịch vụ giả định. Ngoài khả năng `peek` bị bỏ qua khi tối ưu, còn có một số câu hỏi nghiệp vụ chưa được giải quyết:

1. **Thời điểm:** `peek` chạy trước `filter`, có thể ghi audit cả đơn bị loại. Nếu đặt sau `filter`, logic đếm và tối ưu hóa vẫn khiến side effect không được bảo đảm.
2. **Phạm vi:** pipeline có thể short-circuit, làm hành động chỉ chạy trên một phần dữ liệu.
3. **Thứ tự:** parallel stream có thể thực thi không theo thứ tự mong muốn.
4. **Lỗi giữa chừng:** nếu đã ghi một số audit rồi bước tiếp theo lỗi, không có rollback tự động.
5. **Thử lại:** nếu caller retry toàn bộ xử lý, thao tác bên ngoài có thể bị thực hiện lại; `peek` không cung cấp idempotency key.
6. **Giám sát:** terminal `count()` thành công không phải chứng cứ các bản ghi audit đã được lưu bền vững.

Ngay cả khi chuyển sang `forEach`, vẫn cần câu trả lời cho các câu hỏi về transaction và retry. Tuy nhiên, `forEach` ít nhất **diễn đạt đúng ý định terminal action**, thay vì giấu nghiệp vụ trong bước quan sát trung gian.

Đối với giao dịch tiền, email, lịch sử chỉnh sửa, hệ thống cần thêm các cơ chế phù hợp như **idempotency key**, transaction của cơ sở dữ liệu, **outbox pattern**, trạng thái đã xử lý và retry có kiểm soát; đây là quyết định kiến trúc riêng, **không phải khả năng của Stream API**.

## 11. Sắp xếp và quan sát: peek() không biến Stream thành công cụ log đáng tin cậy

Trong nhóm thao tác sắp xếp và quan sát, `peek` thường xuất hiện cùng `sorted`:

```java
List<Integer> values = List.of(3, 1, 2);
var sortedValues = values.stream()
        .sorted()
        .peek(n -> System.out.println("after sort: " + n))
        .toList();
```

Đây là các câu lệnh minh họa trong phương thức đã import `List`. Trên pipeline tuần tự này, thông điệp `after sort` có thể giúp người học **quan sát phần tử sau bước sắp xếp**. Nhưng logging ở đây chỉ là **chẩn đoán**, không phải hành động phải được thực thi cho mọi giá trị ở mọi loại terminal operation.

Đừng dựa vào `peek` để “bắt buộc kiểm thử việc sắp xếp đã chạy” hoặc “đếm mọi phần tử được xử lý”. Bản thân `sorted` cũng có thể được pipeline tối ưu trong những ngữ cảnh không cần quan sát nội dung; các side effects của `peek` không trở thành một phần kết quả đã được hợp đồng bảo đảm.

Nếu cần kiểm tra kết quả sắp xếp trong kiểm thử, hãy **thu dữ liệu rồi assert nội dung**:

```java
List<Integer> sorted = values.stream().sorted().toList();
// Kiểm tra sorted.equals(List.of(1, 2, 3)) trong test.
```

Cách này kiểm tra **giá trị đầu ra** thay vì phụ thuộc số lần hoặc thứ tự gọi side effects trung gian.

## 12. Ngoại lệ, retry và tính nhất quán

Nếu `peek` gọi API bên ngoài có thể ném `RuntimeException`, exception đó **có thể lan ra khi action thực sự được thực thi**. Nhưng không thể dựa vào việc nó chắc chắn phát sinh: nếu stage bị bỏ qua do tối ưu hoặc short-circuit, action không chạy và exception cũng không được ném.

Ví dụ thiết kế rủi ro:

```text
stream.peek(item -> {
    charge(item);
    audit(item);
}).count();
```

Đây là mã giả không chạy độc lập; nó minh họa **hai tác dụng ngoài** được gắn vào `peek`. Có thể không có lệnh `charge` nào chạy; hoặc một số lệnh đã chạy rồi ngoại lệ xảy ra; không có hợp đồng rollback.

Cách tiếp cận tốt hơn:

- Tách pipeline thuần cho **lọc/biến đổi/xác định danh sách công việc**.
- Tạo **command/task** rõ ràng có ID ổn định, bảo đảm tính hợp lệ trước khi phát động hành động.
- Thực hiện hành động bằng một **service** hay vòng lặp minh bạch, có xử lý lỗi và dữ liệu trạng thái theo từng phần tử.
- Với tác động ngoài, cân nhắc **transaction và idempotent retry** dựa vào đặc thù kho dữ liệu/dịch vụ.
- Lưu các tín hiệu kiểm toán thành công/thất bại từ **chính bước thực thi** và hệ thống lưu trữ phù hợp, không suy diễn từ terminal result của một pipeline.

Đặc biệt, **không hứa exactly-once** chỉ vì dùng `forEachOrdered` hay vòng lặp. Chúng giúp code rõ thứ tự thực hiện trong một lượt xử lý thành công, còn exactly-once trong hệ thống phân tán đòi hỏi thiết kế khác.

## 13. Các lựa chọn thay thế theo mục tiêu

**Muốn xem phần tử đi qua pipeline khi debug:** dùng `peek(System.out::println)` có chủ đích, biết rằng side effect có thể bị lược bỏ và thứ tự có thể khác trong parallel. Có thể tháo bỏ `peek` sau khi debug.

**Muốn biến đổi phần tử:** dùng `map`, tốt nhất là biểu thức thuần:

```java
List<String> normalized = names.stream()
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();
```

Các lệnh minh họa trong phương thức có `names: List<String>`, import `List`. Danh sách kết quả là dữ liệu được trả về, không phụ thuộc vào debug logging.

**Muốn chọn phần tử:** dùng `filter` và kiểm tra kết quả, không dùng side effect để làm “filter ngầm”.

**Muốn thực thi một hành động với mỗi phần tử:** khi phù hợp, dùng terminal `forEach` hoặc `forEachOrdered` với policy lỗi rõ ràng, hoặc một vòng lặp `for`:

```java
for (String item : names) {
    System.out.println("process:" + item);
}
```

Đoạn minh họa trong phương thức có `names` phù hợp. Trong sản phẩm thực, thay in chữ bằng service phù hợp và thiết kế lỗi/transaction.

**Muốn tạo số liệu:** dùng terminal `count`, `sum`, `collect`, `reduce` hoặc collector thích hợp, không đếm bằng `peek(x -> counter.incrementAndGet())`. Số liệu phải dựa vào **kết quả terminal operation**, không dựa vào stage quan sát có thể bị bỏ qua.

**Muốn audit bền vững:** dùng một bước audit riêng trong giao dịch hoặc quy trình có kiểm soát, không nhầm `peek` với event log có hợp đồng giao hàng.

## 14. Những lỗi/hiểu lầm phổ biến

| Hiểu lầm | Vì sao không đúng | Cách làm tốt hơn |
| --- | --- | --- |
| `peek` sẽ luôn chạy với từng phần tử | Pipeline lazy, có tối ưu hóa, có short-circuit | Không đặt nghiệp vụ bắt buộc trong `peek` |
| Có terminal operation thì chắc chắn mọi `peek` chạy | `count()` có thể lấy kích thước nguồn; `findFirst()` có thể dừng sớm | Chọn cách xử lý dựa trên hợp đồng đúng của terminal operation |
| `peek` phù hợp để gửi email hay lưu DB | Không có bảo đảm thực thi, rollback, idempotency | Tách giai đoạn nghiệp vụ tường minh |
| Thêm `filter(x -> true)` để ép `peek` chạy | Dựa vào hành vi tối ưu và sửa pipeline không vì nghiệp vụ | Dùng vòng lặp, service hoặc terminal action đúng mục đích |
| Trả ra `count=100` chứng tỏ 100 thao tác hoàn tất | Count chỉ nói về số phần tử được tính, không chứng minh side effects | Theo dõi kết quả hành động trực tiếp |
| `peek` sẽ chạy trên cùng thread gọi terminal | Parallel pipeline có thể chạy trên nhiều thread | Tránh stateful side effects; đồng bộ hóa khi thực sự cần |
| `peek` luôn giữ thứ tự log | Action có thể được gọi không theo encounter order | Dùng cách quan sát phù hợp, không đưa log làm thứ tự nghiệp vụ |
| `map` có thể thay `peek` để bắt buộc ghi DB | `map` vẫn là intermediate operation | Để `map` tạo dữ liệu, bước ngoài chịu trách nhiệm ghi DB |
| `forEachOrdered` đồng nghĩa exactly-once bền vững | Nó chỉ đặt quy tắc action theo encounter order trong một lần traversal | Thiết kế retry/idempotency và lưu trạng thái |
| `ArrayList.add` trong `parallelStream().peek` là an toàn | Dễ gặp race và kết quả không đầy đủ | Tránh side effects; dùng collector hoặc cấu trúc thread-safe đúng mục đích |

## 15. Bài tập và đáp án

**Bài 1 — Kết quả và tác dụng phụ.** Đoạn mã sau có thể cho `count=4` trong khi `counter=0` không?

```java
AtomicInteger counter = new AtomicInteger();
long count = List.of("A", "B", "C", "D").stream()
        .peek(s -> counter.incrementAndGet())
        .count();
```

Đáp án: **Có**. Trên nguồn List biết kích thước, `count()` có thể tính trực tiếp và bỏ qua stage `peek`. Đoạn là các lệnh minh họa trong phương thức đã import `AtomicInteger`, `List`. Ngay cả `AtomicInteger` an toàn luồng cũng không làm `peek` có hợp đồng chạy bắt buộc.

**Bài 2 — Lazy.** `List<String> logs = new ArrayList<>(); var p = data.stream().peek(logs::add);` vừa được gán. Có thể khẳng định `logs` đã chứa mọi phần tử chưa?

Đáp án: **Không**. Chưa có terminal operation, nên việc mô tả pipeline không tự duyệt nguồn; `logs` chưa được lấp đầy bởi `peek`.

**Bài 3 — Kết thúc sớm.** `stream.peek(this::sendEmail).findFirst()` có đáp ứng yêu cầu gửi email cho **mọi** phần tử không?

Đáp án: **Không**. `findFirst()` chỉ cần phần tử đầu tiên của stream có encounter order. Không được đặt gửi email cho tất cả đối tượng vào `peek` của pipeline đó.

**Bài 4 — Đề xuất sửa.** Có `List<Order> orders` và yêu cầu lọc đơn hợp lệ, lập phiếu và lưu từng phiếu. Nên đặt bước lưu ở đâu?

Đáp án: dùng `orders.stream().filter(...).map(...).toList()` để tạo danh sách phiếu; sau đó dùng vòng lặp hoặc service xử lý từng phiếu, quản lý lỗi và transaction. Nếu dữ liệu quá lớn, có thể thiết kế terminal action rõ ràng để tránh materialize toàn bộ; vẫn không dùng `peek` cho lưu bắt buộc.

**Bài 5 — Thứ tự.** Có thể dùng `parallelStream().peek(x -> audit(x))` và tin rằng audit được ghi theo đúng thứ tự List không?

Đáp án: **Không**. Side effects trong parallel pipeline có thể diễn ra không theo encounter order và không được bảo đảm thực thi trên mọi phần tử. Khi cần thứ tự, dùng giải pháp có hợp đồng thứ tự và lưu bền vững phù hợp.

**Bài 6 — map thay peek?** Nếu đổi `peek(x -> charge(x))` thành `map(x -> {charge(x); return x;})` thì đã có cam kết thanh toán bắt buộc chưa?

Đáp án: **Chưa**. `map` cũng là intermediate operation; các thao tác có thể không được thực thi nếu terminal không cần giá trị. Nên tách `charge` ra bước nghiệp vụ độc lập, với transaction/idempotency.

**Bài 7 — Mục đích đúng.** Khi nào `peek` vẫn hữu ích?

Đáp án: khi cần **quan sát và gỡ lỗi** các giá trị đi qua pipeline (đặc biệt giữa các `map`/`filter`/`sorted`), với nhận thức rằng log chỉ có tính hỗ trợ chẩn đoán, không phải chứng cứ bắt buộc đã xử lý mọi dữ liệu.

## 16. Kết luận

- **`peek()` là intermediate operation để quan sát**, thường dùng gỡ lỗi, không phải công cụ thực hiện nghiệp vụ bắt buộc.
- **Lazy evaluation** làm `peek` không chạy khi chưa có traversal; **tối ưu hóa** có thể bỏ qua action, điển hình là `count()` trên nguồn biết kích thước.
- **Short-circuit** như `findFirst()` khiến chỉ một phần dữ liệu được xử lý; **parallel** làm thứ tự và trạng thái dùng chung phức tạp.
- Kết quả terminal operation **không chứng minh** các side effects trung gian đã được thực thi.
- Dùng **`map`/`filter` cho biến đổi dữ liệu**, `toList`/collector để lấy kết quả, và **terminal action hoặc vòng lặp/service** để thực thi hành động có kiểm soát.
- **`forEach`/`forEachOrdered` không tự cung cấp transaction hay exactly-once**: nghiệp vụ quan trọng cần cơ chế lỗi, idempotency và bền vững riêng.
- Khi thấy `.peek(sendEmail)`, `.peek(saveToDatabase)`, `.peek(chargeCustomer)` trong code review, nên xem đó là dấu hiệu cần kiểm tra và thiết kế lại.

Tham khảo: [Java 17 Stream.peek](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#peek(java.util.function.Consumer)), [Java 17 Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()), [Java 17 Stream — Side-effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#SideEffects).
