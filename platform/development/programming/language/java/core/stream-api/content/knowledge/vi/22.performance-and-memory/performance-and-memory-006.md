# Chọn flatMap hoặc mapMulti theo dữ liệu và phép đo

Trong chương **Hiệu năng và bộ nhớ** của **Java Stream API**, sau khi nắm được pipeline lazy, `filter`, `map`, `reduce`, `collect` và cách dùng Spliterator, một câu hỏi thực tế là: **khi một phần tử đầu vào có thể tạo ra không, một hoặc nhiều phần tử đầu ra, nên dùng `flatMap` hay `mapMulti`?**

Hai phương thức đều diễn đạt được phép biến đổi **một–nhiều** (*one-to-many transformation*). Khác biệt chính nằm ở cách mapper cung cấp kết quả:

- `flatMap` yêu cầu mapper tạo **một Stream con** cho mỗi phần tử đầu vào; Stream API làm phẳng các Stream con.
- `mapMulti` cung cấp **một Consumer đầu ra** cho mapper; mapper gọi `accept` không, một hoặc nhiều lần để phát phần tử.

`mapMulti` có thể giảm mã khởi tạo những Stream con rất nhỏ và đôi khi có lợi về hiệu năng. Nhưng **không có quy tắc phổ quát rằng `mapMulti` luôn nhanh hơn hoặc dùng ít bộ nhớ hơn `flatMap`**. Javadoc cho phép triển khai mặc định `mapMulti` bằng bộ đệm trung gian và `flatMap`; hiệu quả thực tế phụ thuộc JDK, dữ liệu, số phần tử được phát, phép biến đổi và terminal operation.

Bài này trình bày hợp đồng của từng API, các trường hợp dùng điển hình, ví dụ Java có kết quả tương đương, rủi ro dừng sớm và tài nguyên I/O, phép đo JMH, cũng như một **ma trận quyết định dựa trên ngữ nghĩa trước, số đo sau**.

> **Phiên bản:** `Stream.flatMap` và các biến thể primitive có từ Java 8. `Stream.mapMulti`, `mapMultiToInt`, `mapMultiToLong`, `mapMultiToDouble` có từ **Java 16**. Các ví dụ đầy đủ sử dụng Java 17+; `record` và `Stream.toList()` có từ Java 16. Nếu phải hỗ trợ Java 8 hoặc Java 11, không gọi trực tiếp `mapMulti`.

## 1. Nhận diện đúng bài toán một–nhiều

Giả sử có danh sách đơn hàng, mỗi đơn chứa danh sách dòng hàng:

~~~text
Order #10: [PEN x2, BOOK x0]
Order #11: []
Order #12: [PAD x3, PEN x1]
~~~

Yêu cầu: sinh danh sách mã `"orderId:sku"` chỉ với những dòng có số lượng **lớn hơn 0**.

~~~text
10:PEN
12:PAD
12:PEN
~~~

Ở đây mỗi đơn có thể phát:

| Đầu vào | Số phần tử đầu ra | Lý do |
| --- | ---: | --- |
| Đơn 10 | 1 | Có một dòng có quantity > 0 |
| Đơn 11 | 0 | Không có dòng hàng |
| Đơn 12 | 2 | Hai dòng có quantity > 0 |

Một phép `map` đơn thuần luôn biến **một phần tử thành đúng một kết quả**, trừ khi kết quả đó chứa collection hoặc được biểu diễn bằng đối tượng tùy chọn. `flatMap` và `mapMulti` phù hợp khi cần **trải phẳng** những kết quả con thành một luồng duy nhất.

Trước khi so hiệu năng, xác định **hợp đồng đầu ra**:

1. Giữ lại những phần tử nào?
2. Mỗi đầu vào có thể phát bao nhiêu kết quả?
3. Có phải giữ encounter order không?
4. Kết quả có thể là `null` không?
5. Nguồn con đã là Stream hay chỉ là dữ liệu cần duyệt?
6. Downstream có thể dừng sớm không?
7. Có tài nguyên cần đóng không?

Nếu đáp án thay đổi, phương thức phù hợp cũng có thể thay đổi.

## 2. flatMap: mỗi đầu vào trả một Stream con

Chữ ký tổng quát của `flatMap`:

~~~java
<R> Stream<R> flatMap(
        Function<? super T, ? extends Stream<? extends R>> mapper);
~~~

Mapper nhận một phần tử kiểu `T`, trả về một `Stream<? extends R>` chứa những kết quả con. Stream API đưa các phần tử của Stream con vào pipeline chính.

Ví dụ Java 17:

~~~java
List<String> codes = orders.stream()
        .flatMap(order -> order.items().stream()
                .filter(item -> item.quantity() > 0)
                .map(item -> order.id() + ":" + item.sku()))
        .toList();
~~~

Có thể đọc từ trái sang phải:

1. Duyệt một `Order`.
2. Lấy Stream con từ `order.items().stream()`.
3. Lọc dòng có `quantity > 0`.
4. Biến từng dòng thành `"orderId:sku"`.
5. `flatMap` làm phẳng những Stream con thành `Stream<String>`.
6. `toList()` thu kết quả cuối cùng.

### Ưu điểm của flatMap

- Dễ đọc khi **nguồn con đã có Stream** hoặc quá trình con tự nhiên biểu diễn bằng pipeline.
- Tái sử dụng được những thao tác `filter`, `map`, `limit`, `takeWhile`, `distinct` và nhiều thao tác Stream khác trong mỗi nguồn con.
- Thể hiện rõ một bước biến đổi thành **Stream con**, thuận lợi khi nguồn con có thể lazy hoặc chứa nhiều phần tử.
- Có hợp đồng đóng những Stream con do mapper trả về sau khi nội dung được đưa vào pipeline.

### Chi phí cần cân nhắc

Với nhiều phần tử đầu vào mà mỗi phần tử tạo một Stream con rỗng hoặc chỉ có một kết quả, cách viết với `Stream.empty()`/`Stream.of(...)` có thể phát sinh nhiều đối tượng trung gian hoặc công việc khởi tạo Stream con. Trên một số JDK, JIT có thể tối ưu được một phần hoặc phần lớn chi phí này; **không được suy ra số cấp phát thực tế chỉ từ số lần gọi phương thức trong mã nguồn**.

Với đầu vào có sẵn một `Stream` con, chi phí tạo Stream có thể là **bản chất nguồn** chứ không phải do `flatMap` gây thêm.

## 3. mapMulti: mapper phát kết quả qua Consumer

Chữ ký của `Stream.mapMulti`:

~~~java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper);
~~~

Trong mapper:

- Tham số thứ nhất là phần tử đầu vào `T`.
- Tham số thứ hai là `Consumer<R>` do Stream API cung cấp.
- Gọi `downstream.accept(value)` để đưa một kết quả `R` vào quá trình làm phẳng.
- Không gọi `accept` nếu đầu vào không tạo kết quả.
- Gọi nhiều lần `accept` nếu đầu vào tạo nhiều kết quả.

Với cùng bài toán đơn hàng:

~~~java
List<String> codes = orders.stream()
        .<String>mapMulti((order, emit) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    emit.accept(order.id() + ":" + item.sku());
                }
            }
        })
        .toList();
~~~

Không có bước tạo `Stream.empty()` hay `Stream.of(...)` cho từng đơn. Mapper duyệt danh sách con bằng vòng lặp và **phát các giá trị**.

Dòng `.<String>mapMulti(...)` chỉ định kiểu đầu ra một cách tường minh. Trong một số ngữ cảnh, đặc biệt với lambda và kết quả chưa có kiểu đích rõ, suy luận kiểu generic có thể chọn kiểu quá rộng như `Object`. Type witness `<String>` giúp compiler và người đọc hiểu mục đích.

### mapMulti không phải push có tín hiệu từ chối

Consumer trong `mapMulti` có phương thức:

~~~java
void accept(R value);
~~~

Nó **không trả boolean**, nên mapper không có một tín hiệu như `Gatherer.Downstream.push(...)` để biết downstream đã từ chối nhận thêm. Đây là khác biệt quan trọng nếu đầu vào có thể tạo hàng triệu phần tử hoặc downstream gọi `limit(1)`.

`mapMulti` được thiết kế để phát nhiều kết quả qua Consumer **đồng bộ trong lần gọi mapper**; không giữ Consumer lại để gọi sau khi mapper đã trả về và không chuyển Consumer sang task bất đồng bộ tự quản.

## 4. Ví dụ đầy đủ: hai pipeline tạo kết quả giống nhau

Đặt đoạn mã sau trong `FlatMapOrMapMultiDemo.java`:

~~~java
import java.util.List;

public class FlatMapOrMapMultiDemo {

    record Item(String sku, int quantity) {}
    record Order(int id, List<Item> items) {}

    static List<String> usingFlatMap(List<Order> orders) {
        return orders.stream()
                .flatMap(order -> order.items().stream()
                        .filter(item -> item.quantity() > 0)
                        .map(item -> order.id() + ":" + item.sku()))
                .toList();
    }

    static List<String> usingMapMulti(List<Order> orders) {
        return orders.stream()
                .<String>mapMulti((order, emit) -> {
                    for (Item item : order.items()) {
                        if (item.quantity() > 0) {
                            emit.accept(
                                    order.id() + ":" + item.sku());
                        }
                    }
                })
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order(10, List.of(
                        new Item("PEN", 2),
                        new Item("BOOK", 0)
                )),
                new Order(11, List.of()),
                new Order(12, List.of(
                        new Item("PAD", 3),
                        new Item("PEN", 1)
                ))
        );

        List<String> flat = usingFlatMap(orders);
        List<String> multi = usingMapMulti(orders);

        System.out.println(flat);
        System.out.println(multi);
        System.out.println(flat.equals(multi));
    }
}
~~~

Đầu ra:

~~~text
[10:PEN, 12:PAD, 12:PEN]
[10:PEN, 12:PAD, 12:PEN]
true
~~~

Chạy trên JDK 17+:

~~~bash
javac --release 17 FlatMapOrMapMultiDemo.java
java FlatMapOrMapMultiDemo
~~~

Ví dụ cố ý sử dụng một `List` có encounter order, không sửa dữ liệu đầu vào trong khi xử lý, và mapper chỉ tạo chuỗi kết quả. Nhờ đó, **cả nội dung lẫn thứ tự** của hai danh sách có thể được so trực tiếp.

Nếu nguồn `orders` được lấy từ collection không có thứ tự, hoặc có lời gọi `unordered()`, không nên tự yêu cầu danh sách theo đúng thứ tự của ví dụ. Việc chọn phương thức làm phẳng không thay thế hợp đồng thứ tự của nguồn.

## 5. Một đầu vào sinh 0, 1, vài hoặc rất nhiều đầu ra

Số kết quả con cho một phần tử, còn gọi là **fan-out**, là một biến đo hiệu năng quan trọng.

| Fan-out thường gặp | Ví dụ | Gợi ý ban đầu |
| --- | --- | --- |
| **0 hoặc 1** | Giá trị tùy chọn, parse thành công/thất bại, thuộc tính có thể null | `mapMulti` đáng thử nếu đang tạo nhiều `Stream.empty`/`Stream.of` rất nhỏ; `filter` + `map` cũng có thể đơn giản hơn |
| **0 đến vài phần tử** | Một đơn có vài dòng, một sự kiện sinh vài nhãn | So `flatMap` và `mapMulti` trên dữ liệu thật |
| **Đã có Stream con** | API trả `Stream<Line>`, nguồn con lazy | `flatMap` thường tự nhiên và dễ giữ tính lazy |
| **Nhiều phần tử cho mỗi đầu vào** | Một bản ghi nở ra hàng trăm nghìn phần tử | Cần xem xét buffering, `limit`, bộ nhớ; không mặc định `mapMulti` có lợi |
| **Nguồn con có tài nguyên** | Mỗi đường dẫn mở tệp, truy vấn sinh Stream I/O | Ưu tiên cách thể hiện quyền sở hữu/đóng nguồn rõ ràng |
| **Cần chia kết quả có trạng thái, dừng sớm chủ động** | Window, batching, điều kiện stop nhiều tầng | Cân nhắc công cụ đúng hợp đồng như iterator, Spliterator hoặc Gatherer tùy JDK, không ép mọi bài toán vào `mapMulti` |

Mẫu mã đẹp và nhanh nhất có thể khác nhau khi fan-out thay đổi từ `0` sang `1` hoặc `100`. Một benchmark chỉ thử "mỗi phần tử sinh một giá trị" không đủ để kết luận cho trường hợp flatten danh sách dài.

## 6. Trường hợp 0 hoặc 1 kết quả: null, Optional và parser

Ví dụ một đơn hàng có thể có mã tracking hoặc không:

~~~java
record Shipment(String id, String trackingCode) {}
~~~

### Cách dùng flatMap

~~~java
List<String> codes = shipments.stream()
        .flatMap(shipment ->
                java.util.stream.Stream.ofNullable(
                        shipment.trackingCode()))
        .toList();
~~~

`Stream.ofNullable` có từ Java 9. Với `trackingCode == null`, nó tạo một Stream rỗng; ngược lại, tạo Stream một phần tử.

### Cách dùng mapMulti

~~~java
List<String> codes = shipments.stream()
        .<String>mapMulti((shipment, emit) -> {
            String tracking = shipment.trackingCode();
            if (tracking != null) {
                emit.accept(tracking);
            }
        })
        .toList();
~~~

Hai pipeline có cùng nội dung đầu ra nếu yêu cầu là **bỏ giá trị null**. Nhưng không cần giới hạn lựa chọn vào đúng hai cách này:

~~~java
List<String> codes = shipments.stream()
        .map(Shipment::trackingCode)
        .filter(java.util.Objects::nonNull)
        .toList();
~~~

Cách `map` + `filter` có thể gọn và dễ hiểu hơn với phép biến đổi 1–1 rồi loại null; benchmark vẫn cần nếu chênh lệch hiệu năng đáng quan tâm.

### Optional khác null thế nào?

Nếu đầu vào có `Optional<T>`, Java 9+ hỗ trợ:

~~~java
List<String> codes = optionalCodes.stream()
        .flatMap(java.util.Optional::stream)
        .toList();
~~~

Với `mapMulti`:

~~~java
List<String> codes = optionalCodes.stream()
        .<String>mapMulti((opt, emit) ->
                opt.ifPresent(emit))
        .toList();
~~~

Cả hai cách đều phát **0 hoặc 1** giá trị cho mỗi Optional. Đối số `emit` chỉ hợp lệ trong lời gọi mapper, vì vậy không giữ tham chiếu để sử dụng về sau.

**Lưu ý nghiệp vụ:** Loại bỏ null hoặc Optional rỗng làm giảm số phần tử. Nếu hệ thống phải giữ vị trí tương ứng với từng bản ghi, đừng loại phần tử rồi cho rằng danh sách đầu ra vẫn có cùng số lượng/phân bố.

## 7. Khi flatMap đáng ưu tiên vì Stream con đã tồn tại

Giả sử một lớp nghiệp vụ đã cung cấp một Stream con:

~~~java
interface EventSource {
    java.util.stream.Stream<Event> events();
}
~~~

Nếu cần nối các nguồn:

~~~java
Stream<Event> all = sources.stream()
        .flatMap(EventSource::events);
~~~

`flatMap` thể hiện trực tiếp "mỗi nguồn cung cấp một Stream sự kiện". Nó cũng sử dụng hợp đồng Stream để xử lý Stream con; theo API, **mỗi Stream được mapper trả về sẽ được đóng sau khi nội dung của nó được đưa vào pipeline**.

Viết lại bằng `mapMulti` có thể buộc bạn chủ động duyệt Stream con:

~~~java
Stream<Event> all = sources.stream()
        .<Event>mapMulti((source, emit) -> {
            try (Stream<Event> events = source.events()) {
                events.forEach(emit);
            }
        });
~~~

Đoạn này phải dùng `try-with-resources` để đóng Stream con. Nó cũng chủ động thực hiện việc duyệt tất cả phần tử con **trong callback mapper**, nên không thể suy ra khả năng dừng sớm tương đương với `flatMap`. Việc viết vòng lặp chủ động như vậy thường **không có lợi** nếu API nguồn đã cung cấp Stream lazy.

**Nguyên tắc:** Nếu nguồn con bản thân là Stream hoặc có tài nguyên, `flatMap` là lựa chọn khởi đầu dễ hiểu. Chỉ chuyển sang `mapMulti` nếu kiểm chứng được cùng ngữ nghĩa, vòng đời và lợi ích thực tế.

## 8. Đặc biệt lưu ý vòng đời tài nguyên I/O

Một Stream tạo từ `Files.lines(path)` có tài nguyên I/O phải đóng. Nếu đọc nhiều tệp, `flatMap` có thể biểu diễn việc mở từng tệp:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static long countErrorLines(List<Path> paths) {
    return paths.stream()
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
~~~

Ở đây Stream ngoài là `paths.stream()` từ danh sách trong bộ nhớ. `flatMap` quản lý việc đóng các Stream con do `Files.lines` trả về theo hợp đồng của nó. Nếu Stream **ngoài** cũng sở hữu tài nguyên, phải đặt chính Stream đó trong `try-with-resources`.

Nếu dùng `mapMulti`, người viết mapper tự chịu trách nhiệm đóng tệp:

~~~java
static long countErrorLinesMulti(List<Path> paths) {
    return paths.stream()
            .<String>mapMulti((path, emit) -> {
                try (Stream<String> lines =
                        Files.lines(path, StandardCharsets.UTF_8)) {

                    lines.forEach(emit);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
~~~

Đây là cách đóng nguồn con **đúng phạm vi**, nhưng không mặc nhiên là thiết kế tốt hơn: callback có thể phải đọc hết một tệp con, kể cả khi downstream chỉ cần ít phần tử. Nếu xử lý tệp rất lớn hoặc có khả năng short-circuit, `flatMap` thường thuận lợi hơn để biểu đạt luồng con lazy.

**Tránh tuyệt đối** mở `Files.lines` bên trong callback rồi `forEach(emit)` mà không đóng Stream. Terminal operation không tự gọi `close` trên một Stream I/O tùy ý.

## 9. mapMulti không tự cam kết loại bỏ mọi bộ đệm

Một ý tưởng thường gặp:

> “`mapMulti` không tạo Stream con, nên chắc chắn không cấp phát bộ đệm và luôn dùng O(1) bộ nhớ.”

Kết luận đó **không được bảo đảm bởi API**.

Theo phần API Note của `Stream.mapMulti`, triển khai mặc định có thể được mô tả như sau:

1. Tạo một **bộ đệm nội bộ** cho những phần tử được mapper phát ra.
2. Gọi mapper với Consumer đưa kết quả vào bộ đệm.
3. Sau khi mapper trả về, tạo Stream từ bộ đệm.
4. Dùng `flatMap` để đưa các kết quả vào pipeline.

Triển khai JDK cụ thể có thể tối ưu khác đi, và JIT có thể thay đổi số object thực sự được cấp phát. Nhưng **code gọi `mapMulti` không được dựa vào một bảo đảm "không bao giờ buffer"**.

Hệ quả:

- Với **fan-out nhỏ**, `mapMulti` có thể có lợi khi tránh nhiều Stream con nhỏ, tùy JDK.
- Với **fan-out rất lớn từ một đầu vào**, có nguy cơ phải giữ nhiều kết quả trung gian theo cách triển khai; cần đo heap và cấp phát.
- Nếu downstream dừng sớm, không được giả định mapper có thể dừng ngay bên trong vòng lặp chỉ vì đã đủ kết quả.
- Với đầu ra lớn hoặc vô hạn từ một input, `mapMulti` không phải cơ chế streaming/backpressure được bảo đảm theo từng phần tử.

Vì vậy, ngoài thời gian chạy, phải đo **allocation rate, GC và peak memory** trước khi quyết định cho bài toán dữ liệu lớn.

## 10. Short-circuit: limit và findFirst có thể làm hai cách khác chi phí

Một tình huống quan trọng là downstream chỉ cần kết quả đầu tiên:

~~~java
List<Integer> first = rows.stream()
        .flatMap(row -> row.values().stream())
        .limit(1)
        .toList();
~~~

Với `flatMap`, Stream con là nguồn lazy. Việc tiêu thụ downstream có thể dừng sau khi lấy đủ số phần tử, tùy hợp đồng và cách thực thi.

Biểu đạt tương ứng bằng `mapMulti`:

~~~java
List<Integer> first = rows.stream()
        .<Integer>mapMulti((row, emit) -> {
            for (Integer value : row.values()) {
                emit.accept(value);
            }
        })
        .limit(1)
        .toList();
~~~

Mapper nhận `Consumer<Integer>` **không trả tín hiệu** rằng downstream đã đủ. Nếu `row.values()` có hàng triệu phần tử, không thể viết:

~~~java
if (!emit.accept(value)) {
    break;
}
~~~

vì `Consumer.accept` trả về `void`. Một triển khai có thể buffer toàn bộ những giá trị mà mapper phát cho **một** input trước khi downstream xử lý tiếp.

Điều cần ghi nhớ:

- Hai pipeline có thể **cùng kết quả** nhưng khác đáng kể về số phần tử con đã được tạo/duyệt.
- Đừng dùng tác dụng phụ trong mapper rồi khẳng định `limit(1)` chỉ khiến mapper thao tác đúng một phần tử con.
- Nếu việc phát kết quả tốn chi phí hoặc nguồn con rất dài, thử `flatMap` với Stream con lazy trước.
- Nếu dùng `mapMulti` vì chủ động xử lý toàn bộ nhóm ngắn, chi phí callback và memory có thể vẫn phù hợp.

### Vì sao không dùng Gatherer để thay mọi mapMulti?

`Gatherer.Downstream.push` (API chuẩn từ Java 24) có tín hiệu `boolean` cho biết downstream còn muốn nhận thêm không; còn Consumer của `mapMulti` **không có** giao thức này. Gatherer phù hợp với một số bài toán cần dừng sớm/chia trạng thái phức tạp, nhưng yêu cầu JDK mới hơn và không phải lựa chọn bắt buộc cho phép làm phẳng đơn giản.

Đừng thay đổi kiến trúc hoặc phiên bản JDK chỉ vì một benchmark nhỏ; hãy chọn API theo **hợp đồng kết quả và vòng đời**, rồi đo.

## 11. mapMultiToInt, mapMultiToLong, mapMultiToDouble: tránh boxing không cần thiết

Khi đầu ra là số primitive, so sánh các cặp API tương ứng:

| Đầu ra | flatMap | mapMulti |
| --- | --- | --- |
| `Stream<R>` | `flatMap(...)` | `mapMulti(...)` |
| `IntStream` | `flatMapToInt(...)` | `mapMultiToInt(...)` |
| `LongStream` | `flatMapToLong(...)` | `mapMultiToLong(...)` |
| `DoubleStream` | `flatMapToDouble(...)` | `mapMultiToDouble(...)` |

Ví dụ tính tổng số lượng các dòng hợp lệ:

~~~java
long totalUnitsFlat = orders.stream()
        .flatMapToInt(order -> order.items().stream()
                .filter(item -> item.quantity() > 0)
                .mapToInt(Item::quantity))
        .asLongStream()
        .sum();

long totalUnitsMulti = orders.stream()
        .mapMultiToInt((order, emit) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    emit.accept(item.quantity());
                }
            }
        })
        .asLongStream()
        .sum();
~~~

Hai phép tính cho ra cùng tổng khi quantity không âm và số lượng không vượt miền `long`. `asLongStream().sum()` dùng tổng kiểu `long` thay vì `IntStream.sum()` kiểu `int`, giảm nguy cơ tràn khi dữ liệu nhiều (nhưng không loại bỏ mọi khả năng tràn `long`).

Điểm đáng so là **`flatMapToInt` với `mapMultiToInt`**. So `Stream<Integer>` boxing nhiều lần với `mapMultiToInt` có thể cho kết quả benchmark thiên lệch vì thay đổi **hai yếu tố cùng lúc**: cách làm phẳng và boxing. Khi benchmark, hãy giữ kiểu pipeline đầu ra tương đương.

### Type inference trong mapMulti

Khi kiểu đầu ra không được xác định rõ:

~~~java
List<String> result = orders.stream()
        .<String>mapMulti((order, emit) -> {
            for (Item item : order.items()) {
                emit.accept(item.sku());
            }
        })
        .toList();
~~~

Type witness `<String>` giúp tránh trường hợp compiler suy luận `Object` và không gán được cho `List<String>`. Nếu đầu ra là số primitive, những overload `mapMultiToInt/Long/Double` có loại Stream xác định sẵn nên tránh được nhiều vấn đề suy luận kiểu và boxing.

## 12. Tính đúng trước khi tối ưu: các bất biến cần giữ

Một phép thay `flatMap` bằng `mapMulti` phải giữ **ngữ nghĩa**:

1. **Số phần tử đầu ra:** mỗi input phát đúng số giá trị cần thiết.
2. **Giá trị:** các kết quả được biến đổi/lọc theo cùng điều kiện.
3. **Thứ tự:** khi nguồn có encounter order, các giá trị được phát trong đúng thứ tự cần giữ.
4. **Null:** các phần tử null được giữ hoặc loại theo đúng quy tắc, không tự suy diễn.
5. **Ngoại lệ:** lỗi parser và I/O không bị biến thành kết quả thiếu dữ liệu.
6. **Vòng đời tài nguyên:** Stream con hoặc reader phải được đóng.
7. **Xử lý song song:** mapper không can thiệp nguồn, không chia sẻ state mutable ngoài hợp đồng.
8. **Dừng sớm:** không dựa vào số lần gọi mapper/side effect như một kết quả nghiệp vụ.
9. **Loại đầu ra:** `Stream<R>` và primitive stream có miền kiểu phù hợp.

### Bất biến cho ví dụ đơn hàng

Với mỗi `Order`, đặt:

~~~text
valid(order) = các dòng item có quantity > 0
~~~

Khi đó:

~~~text
flatten(orders).size()
    == tổng số valid(item) của mọi order

flatten(orders) giữ thứ tự order và item nếu nguồn có thứ tự
mọi chuỗi đầu ra dùng đúng order.id và item.sku
~~~

Ví dụ kiểm tra:

~~~java
List<String> expected = usingFlatMap(orders);
List<String> actual = usingMapMulti(orders);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "flatMap/mapMulti mismatch\n"
            + "expected=" + expected
            + "\nactual=" + actual
    );
}
~~~

**So một cách triển khai với cách triển khai khác không chứng minh cả hai đúng.** Hãy kết hợp thêm oracle bằng vòng lặp để tránh trường hợp hai pipeline cùng sai một điều kiện nghiệp vụ.

## 13. Oracle đơn giản để kiểm tra fan-out và encounter order

Một vòng lặp thủ tục, không dùng hai API đang so sánh:

~~~java
static List<String> reference(List<Order> orders) {
    List<String> result = new java.util.ArrayList<>();

    for (Order order : orders) {
        for (Item item : order.items()) {
            if (item.quantity() > 0) {
                result.add(
                        order.id() + ":" + item.sku());
            }
        }
    }

    return result;
}
~~~

Có thể kiểm tra:

~~~java
List<String> expected = reference(orders);

if (!expected.equals(usingFlatMap(orders))
        || !expected.equals(usingMapMulti(orders))) {
    throw new AssertionError("Incorrect flatten result");
}
~~~

Bộ kiểm thử nên có những trường hợp:

| Ca thử | Điều quan trọng |
| --- | --- |
| Danh sách đơn rỗng | Kết quả rỗng |
| Một đơn không có dòng | Không phát giá trị |
| Một đơn chỉ có dòng quantity = 0 | Không phát giá trị |
| Một đơn có một dòng hợp lệ | Phát một phần tử |
| Một đơn có nhiều dòng | Phát nhiều phần tử và giữ thứ tự |
| Nhiều đơn có cùng SKU | Không tự loại trùng nếu không có `distinct` |
| SKU rỗng hoặc null | Theo chính sách validation đầu vào đã định |
| Số lượng âm | Bị loại nếu điều kiện là `quantity > 0` |
| Fan-out tăng dần | So tính đúng, thời gian và cấp phát |
| Ngừng sớm bằng `limit(1)` | Cùng kết quả nhưng kiểm tra chi phí thực thi riêng |
| Chuyển sang parallel | So kết quả theo hợp đồng, không so lịch mapper |

Đừng chỉ thử một đơn chứa đúng một phần tử: đó chính là trường hợp dễ khiến mọi cách viết có vẻ tương đương về cả ngữ nghĩa lẫn hiệu năng.

## 14. Song song hóa và stateless mapper

Cả `flatMap` và `mapMulti` là **intermediate operations** của Stream. Mapper của chúng phải tránh sửa nguồn và phụ thuộc trạng thái mutable dùng chung.

**Mẫu không an toàn:**

~~~java
List<String> shared = new java.util.ArrayList<>();

orders.parallelStream()
        .forEach(order -> {
            for (Item item : order.items()) {
                shared.add(item.sku());
            }
        });
~~~

`ArrayList` không an toàn khi nhiều tác vụ cùng ghi. Việc thay thành `synchronizedList` có thể tránh một số race condition, nhưng không tự bảo đảm thứ tự đầu ra đúng encounter order, đồng thời thêm contention.

**Mẫu phù hợp hơn:**

~~~java
List<String> result = orders.parallelStream()
        .<String>mapMulti((order, emit) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    emit.accept(item.sku());
                }
            }
        })
        .toList();
~~~

Mỗi mapper chỉ đọc `order.items()`, phát giá trị vào Consumer được Stream API cung cấp. Với một `List` ordered và terminal `toList()`, đầu ra giữ encounter order theo hợp đồng. Nhưng **không** có bảo đảm mapper được thực thi tuần tự hoặc bởi một thread cụ thể.

Đừng giữ Consumer `emit` bên ngoài callback để gọi từ thread khác hoặc thêm tác dụng phụ vào mapper rồi đòi nó chạy đúng một lần trên mọi nhánh short-circuit.

### Parallel không đồng nghĩa nhanh hơn

Khi tính toán trên mỗi phần tử chỉ là một vòng lặp ngắn và một phép cộng, chi phí chia Spliterator, phân phối tác vụ và ghép kết quả có thể vượt lợi ích song song. Khi benchmark `flatMap` và `mapMulti`, mặc định nên so **tuần tự với tuần tự**, sau đó làm một đợt benchmark riêng **song song với song song**, không trộn hai trục thay đổi vào một phép so.

## 15. Thiết kế benchmark công bằng

Muốn đưa ra quyết định dựa trên số liệu, cần kiểm soát các biến độc lập.

### 15.1. Những biến cần cố định

- **Cùng dữ liệu đầu vào:** số lượng bản ghi, kích thước danh sách con, số kết quả được phát và thứ tự.
- **Cùng phép lọc/biến đổi:** một bản ghi sinh ra các số giống nhau trên hai pipeline.
- **Cùng kiểu đầu ra:** so `flatMapToInt` với `mapMultiToInt` hoặc `flatMap` với `mapMulti`.
- **Cùng terminal operation:** ví dụ cả hai cùng tính `asLongStream().sum()`.
- **Cùng mức song song:** không so sequential `flatMap` với parallel `mapMulti`.
- **Cùng trạng thái JIT/GC:** có warm-up, nhiều lần đo và nhiều fork khi cần.
- **Không đưa bước sinh dữ liệu vào phép đo** trừ khi muốn đo cả bước đó.
- **Không loại bỏ công việc do compiler tối ưu:** kết quả benchmark phải được quan sát bởi harness hoặc Blackhole.

Nếu benchmark chỉ đo thời gian tạo một `Stream` mà **không có terminal operation**, phần lớn pipeline có thể chưa thực thi do tính lazy. Phép đo như vậy không phản ánh chi phí thực tế của `flatMap`/`mapMulti`.

### 15.2. Những nhóm dữ liệu nên thử

| Tham số | Giá trị gợi ý | Mục đích |
| --- | --- | --- |
| Số input | 1.000; 100.000; lớn hơn nếu phù hợp | Xem overhead theo số phần tử nguồn |
| Fan-out | 0; 1; 4; 16; 100+ | Phân biệt trường hợp rỗng/nhỏ/lớn |
| Độ lệch fan-out | Đều; đa số rỗng; vài bản ghi rất lớn | Gần dữ liệu thực tế |
| Kiểu dữ liệu | `int`, `long`, object | Xem ảnh hưởng boxing |
| Downstream | `sum`, `toList`, `limit(1)` | Xem khác biệt tổng hợp và short-circuit |
| Nguồn | `ArrayList`, nguồn từ Iterator, Stream I/O | Xem ảnh hưởng Spliterator và tài nguyên |
| Chế độ | Sequential; parallel tách riêng | Không đánh đồng thuật toán với concurrency |

**Quan trọng:** Không chọn một cấu hình fan-out có lợi cho API mình muốn dùng rồi xem đó là bằng chứng chung. Cấu hình benchmark phải phản ánh **phân bố dữ liệu sản xuất**.

## 16. Ví dụ JMH: flatMapToInt so với mapMultiToInt

**JMH** (*Java Microbenchmark Harness*) là công cụ phổ biến để đo microbenchmark trong JVM. Ví dụ sau minh họa cách tổ chức phép đo; JMH là thư viện ngoài JDK, vì vậy cần cấu hình dependency và annotation processor phù hợp trong dự án trước khi chạy. Bài này **không khẳng định** kết quả tốc độ nào khi chưa thực thi benchmark.

Lưu ý chương trình benchmark độc lập sau đây cần Java 17+ và JMH đã được cấu hình:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.IntStream;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 4)
@Measurement(iterations = 6)
@Fork(2)
public class FlatMapMapMultiBenchmark {

    record Row(List<Integer> values) {}

    @State(Scope.Thread)
    public static class Data {
        @Param({"1000", "100000"})
        public int rows;

        @Param({"0", "1", "4", "16"})
        public int fanOut;

        List<Row> input;

        @Setup(Level.Trial)
        public void setup() {
            List<Row> rowsData = new ArrayList<>(rows);

            for (int i = 0; i < rows; i++) {
                List<Integer> values =
                        new ArrayList<>(fanOut);

                for (int j = 0; j < fanOut; j++) {
                    values.add((i + j) & 1023);
                }

                rowsData.add(new Row(List.copyOf(values)));
            }

            input = List.copyOf(rowsData);
        }
    }

    @Benchmark
    public long usingFlatMapToInt(Data data) {
        return data.input.stream()
                .flatMapToInt(row ->
                        row.values().stream()
                                .mapToInt(Integer::intValue))
                .asLongStream()
                .sum();
    }

    @Benchmark
    public long usingMapMultiToInt(Data data) {
        return data.input.stream()
                .mapMultiToInt((row, emit) -> {
                    for (int value : row.values()) {
                        emit.accept(value);
                    }
                })
                .asLongStream()
                .sum();
    }
}
~~~

Cả hai benchmark:

- Dùng đúng **cùng dữ liệu** từ `Data.input`.
- Phát đúng **cùng dãy số nguyên** cho từng `Row`.
- Đều tạo `IntStream`, chuyển thành `LongStream` rồi cộng để tránh tràn `int` trong bộ dữ liệu lớn.
- Có terminal operation `sum()`, nên không chỉ đo việc xây một pipeline chưa chạy.
- Không tính chi phí sinh input trong phương thức `@Benchmark`.
- Dùng nhiều cấu hình fan-out, có warm-up, nhiều lần đo và nhiều fork.

Khi chạy JMH thật, cần kiểm tra cả **giá trị checksum** của hai nhánh bằng một bài test độc lập; phép đo nhanh không có ý nghĩa nếu hai benchmark tạo kết quả khác nhau.

### Đọc kết quả JMH

Một bảng kết quả minh họa **không phải số đo thực tế**:

| Cấu hình | Điều cần quan sát | Kết luận được phép |
| --- | --- | --- |
| Fan-out = 0 | Chi phí xử lý phần tử không phát đầu ra | Một cách có thể ít overhead hơn ở trường hợp rỗng |
| Fan-out = 1 | Chi phí Stream con nhỏ và Consumer | Một cách có thể ít object hơn trên JDK cụ thể |
| Fan-out = 16 | Chi phí duyệt nhiều phần tử con | Kết quả có thể đảo chiều |
| Fan-out = rất lớn | Cấp phát, GC, memory peak và cancellation | Không chỉ nhìn thời gian trung bình |
| `limit(1)` sau phép làm phẳng | Có thực sự dừng sinh output con sớm? | Ngữ nghĩa giống nhau không đồng nghĩa chi phí giống nhau |

Không suy ra con số phần trăm tăng tốc khi chưa chạy phép đo. Những kết quả tốt trên laptop phát triển có thể không lặp lại trên server khác về JDK, heap, CPU hoặc dữ liệu.

### Đo cấp phát và GC

Tùy cấu hình JMH, sử dụng profiler thích hợp (chẳng hạn các chế độ thống kê GC/allocation của JMH) để tìm:

- Số byte cấp phát trên mỗi operation.
- Số lần và chi phí garbage collection.
- Thời gian trung bình, độ biến thiên và trường hợp xấu.
- Heap peak nếu fan-out tạo nhiều phần tử.
- Độ ổn định khi chạy nhiều fork và dữ liệu khác nhau.

**Giảm cấp phát** không luôn đồng nghĩa **giảm thời gian xử lý**, và giảm thời gian trung bình không luôn đồng nghĩa giảm độ trễ đuôi hoặc cải thiện throughput toàn hệ thống.

## 17. Đo hiệu năng toàn pipeline, không chỉ thao tác làm phẳng

Đôi khi sự khác biệt giữa `flatMap` và `mapMulti` rất nhỏ so với các bước khác:

~~~text
Nguồn dữ liệu -> parse JSON -> validate -> flatMap/mapMulti
             -> groupingBy -> ghi database
~~~

Nếu phần đọc tệp, parse JSON hoặc truy cập database chiếm phần lớn thời gian, tối ưu chi phí tạo Stream con có thể không đáng kể đối với tổng latency.

Hãy tách **hai mức đo**:

1. **Microbenchmark:** cô lập thao tác làm phẳng, hiểu ảnh hưởng fan-out và allocation.
2. **Benchmark tích hợp:** đo end-to-end trên dữ liệu sát thực tế, bao gồm parse, filter, collector, I/O, GC và thời gian phản hồi.

Một phép đo có thể cho thấy `mapMulti` nhanh hơn trong microbenchmark, nhưng pipeline ứng dụng thực tế lại không cải thiện có ý nghĩa. Khi đó, giữ `flatMap` dễ đọc có thể là quyết định tốt hơn.

Ngược lại, nếu một pipeline xử lý hàng chục triệu phần tử với rất nhiều Stream con 0/1 phần tử và bước làm phẳng chiếm nhiều CPU/allocation, kết quả đo nhất quán có thể biện minh cho `mapMulti`.

## 18. Ma trận quyết định thực tế

| Điều kiện | Lựa chọn nên thử trước | Lý do |
| --- | --- | --- |
| Chỉ biến đổi 1 đầu vào thành 1 đầu ra | `map` | Đúng mô hình, đơn giản nhất |
| Chỉ lọc bỏ phần tử | `filter` | Không cần one-to-many |
| Có giá trị nullable cần loại bỏ | `map + filter`, `ofNullable + flatMap` hoặc `mapMulti` | Chọn dễ đọc, đo nếu xử lý nhiều |
| Optional đã tồn tại | `flatMap(Optional::stream)` hoặc `mapMulti` | Cả hai diễn đạt 0/1 |
| Con là `Stream` lazy đã có | `flatMap` | Giữ phép nối Stream con tự nhiên |
| Con là một collection nhỏ, rất nhiều input | `mapMulti` là ứng viên đáng thử | Có thể tránh tạo Stream con nhỏ; cần đo |
| Một input phát rất nhiều phần tử | `flatMap` với Stream con lazy đáng thử | Xem buffering, short-circuit và bộ nhớ |
| Downstream thường `limit`/`findFirst` | Thử `flatMap` trước và benchmark cancellation | `mapMulti` không nhận tín hiệu từ chối qua Consumer |
| Nguồn con sở hữu I/O | `flatMap` hoặc mã quản lý `try-with-resources` rõ | Phải kiểm soát `close()` |
| Đầu ra primitive | So `flatMapToInt` với `mapMultiToInt` | Đúng kiểu, tránh so lệch boxing |
| Codebase hỗ trợ Java 8/11 | `flatMap` | `mapMulti` chưa có trong API đích |
| Yêu cầu giữ encounter order | Cả hai, nếu mapper phát đúng thứ tự | Không dựa vào thứ tự thread thực thi |
| Chỉ cần kết quả, không lưu hết output | Terminal `sum`, `reduce`, `collect` phù hợp | Tránh `toList` không cần thiết |

**Quy tắc ưu tiên:**

- **Đúng ngữ nghĩa trước.**
- **Đơn giản, dễ bảo trì tiếp theo.**
- **Hiệu năng theo phép đo cuối cùng.**

Không có nghĩa vụ phải chuyển mọi `flatMap` sang `mapMulti` khi nâng JDK. Mã đang đúng, dễ đọc và không phải nút thắt hiệu năng thì có thể giữ nguyên.

## 19. Bẫy thường gặp

| Bẫy | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tưởng `mapMulti` luôn "zero allocation" | Đánh giá sai bộ nhớ và GC | Kiểm tra JDK, JIT, profiler và dữ liệu |
| Tưởng `Consumer.accept` trả tín hiệu dừng | Viết logic short-circuit không hợp lệ | Hiểu `accept` trả `void`, cân nhắc `flatMap`/Gatherer phù hợp |
| Tạo Stream con ngay trong `mapMulti` rồi duyệt hết | Mã phức tạp, có thể mất laziness | Dùng `flatMap` nếu nguồn con đã là Stream |
| Bỏ quên `close` của `Files.lines` | Rò rỉ tài nguyên | Dùng `try-with-resources` và/hoặc `flatMap` đúng hợp đồng |
| Chỉ benchmark một phần tử | Không đại diện fan-out thực tế | Đo nhiều phân bố và kích thước |
| Dùng `count()` rồi cho rằng mọi mapper chắc chắn đã chạy | Có thể có tối ưu hóa phụ thuộc đặc tính nguồn/pipeline | Benchmark cần thực thi phép biến đổi và xác nhận tính đúng; `sum` là một lựa chọn |
| So Stream boxed với primitive | Kết luận sai về API làm phẳng | So cùng kiểu và cùng công việc |
| Dựa vào thứ tự thực thi trên `parallel()` | Test chập chờn, side effect sai | Chỉ kiểm tra encounter order/kết quả được đặc tả |
| Giữ `emit` để gọi sau callback | Vi phạm phạm vi sử dụng Consumer | Chỉ gọi trong mapper được cung cấp |
| Đưa mapper có side effect vào phép đo | Khó suy luận và khó tái lập | Dùng hàm thuần và fixture bất biến |
| Kết quả `toList` quá lớn | Tăng memory theo toàn bộ output | Dùng phép tổng hợp/ghi có kiểm soát nếu phù hợp |
| Thấy một phép đo nhanh hơn và sửa tất cả | Tăng rủi ro mà không có lợi ích hệ thống | Profile nút thắt, đo lại trước/sau trên pipeline thật |

## 20. Bài tập thực hành

### Bài 1 — Dự đoán kết quả

~~~java
List<Integer> result = List.of(
        List.of(1, 2),
        List.<Integer>of(),
        List.of(3)
).stream().<Integer>mapMulti((list, emit) -> {
    for (Integer n : list) {
        emit.accept(n * 2);
    }
}).toList();
~~~

**Đáp án:** `[2, 4, 6]`. Danh sách con rỗng phát 0 phần tử; những danh sách khác phát lần lượt 2 và 1 phần tử.

### Bài 2 — Viết flatMap tương đương

Cho `mapMulti` ở bài 1, hãy viết bằng `flatMap`.

**Gợi ý/đáp án:**

~~~java
List<Integer> result = List.of(
        List.of(1, 2),
        List.<Integer>of(),
        List.of(3)
).stream()
        .flatMap(list -> list.stream().map(n -> n * 2))
        .toList();
~~~

Với các danh sách có encounter order, hai cách cho cùng kết quả và thứ tự.

### Bài 3 — Chọn API cho nguồn con đã là Stream

Một service trả `Stream<LogLine>` lazy cho mỗi ngày. Downstream chỉ cần một dòng thỏa điều kiện. Nên thử API nào đầu tiên?

**Đáp án:** `flatMap` thường phù hợp hơn vì có thể làm phẳng Stream con lazy và đóng các Stream con theo hợp đồng, thuận lợi cho short-circuit. Dù vậy vẫn cần `try-with-resources` cho mọi nguồn I/O sở hữu riêng và đo chi phí thực tế.

### Bài 4 — Vì sao mapMulti không có callback dừng?

Có thể viết `if (!emit.accept(value)) break;` không?

**Đáp án:** Không. `emit` là `Consumer<R>`, nên `accept` trả `void`. `mapMulti` không có boolean từ chối downstream; khi một mapper có thể tạo rất nhiều đầu ra, cần chú ý buffering/short-circuit.

### Bài 5 — Trường hợp một–một

Pipeline đổi `name` sang chữ hoa và luôn trả đúng một tên. Có nên dùng `flatMap` hay `mapMulti`?

**Đáp án:** Dùng `map(String::toUpperCase)`. Không cần mô hình một–nhiều, nên đừng thêm chi phí và độ phức tạp của API làm phẳng.

### Bài 6 — Kiểm tra bộ nhớ

Vì sao `mapMulti` với một input phát một triệu giá trị không được cam kết dùng O(1) bộ nhớ?

**Đáp án:** Đặc tả cho phép triển khai mặc định tích lũy output của mapper trong buffer nội bộ trước khi tạo Stream cho downstream. Cần kiểm tra implementation/JDK và số đo allocation/peak heap, nhất là khi downstream dùng `limit`.

### Bài 7 — Tạo phép đo công bằng

Một benchmark so `Stream<Integer>.flatMap(...)` với `Stream<T>.mapMultiToInt(...)` và kết luận `mapMulti` nhanh gấp nhiều lần. Điểm không công bằng là gì?

**Đáp án:** Hai nhánh không cùng kiểu đầu ra: một nhánh boxing object còn nhánh kia dùng primitive. Phải so `flatMapToInt` với `mapMultiToInt`, giữ giống dữ liệu, phép biến đổi và terminal operation trước khi kết luận.

### Bài 8 — Fan-out và số phần tử

Có 100 đơn hàng, mỗi đơn trung bình bốn dòng hợp lệ và mọi đơn đã có dữ liệu đầy đủ. `flatMap` và `mapMulti` tạo bao nhiêu output?

**Đáp án:** Theo giả định, khoảng 400 đầu ra nếu trung bình bốn dòng hợp lệ được tính chính xác trên toàn bộ 100 đơn. Hai API phải cho cùng số phần tử nếu cùng logic phát; chênh lệch kết quả là lỗi ngữ nghĩa chứ không phải tối ưu hợp lệ.

### Bài 9 — Parallel và consumer

Có thể giữ `emit` trong một danh sách rồi dùng executor tự gọi nó sau khi `mapMulti` kết thúc không?

**Đáp án:** Không. Consumer được cung cấp chỉ dành cho phạm vi lời gọi mapper, không phải một kênh push bất đồng bộ do ứng dụng sở hữu. Cần thiết kế khác nếu yêu cầu concurrency.

### Bài 10 — Đánh giá khi benchmark không khác biệt

Nếu `flatMap` và `mapMulti` có kết quả giống nhau, thời gian/chỉ số GC không khác biệt đáng kể trên workload thật, nên chọn gì?

**Đáp án:** Chọn phiên bản dễ đọc, bảo trì và đúng hợp đồng với nguồn. Nếu nguồn con vốn là Stream, `flatMap` thường rõ ràng; nếu nguồn con là vài giá trị phát theo điều kiện, `mapMulti` có thể gọn hơn. Không cần tối ưu dựa trên một giả định chưa được dữ liệu xác nhận.

## 21. Ghi nhớ

- `flatMap` yêu cầu mapper trả **Stream con**; `mapMulti` cho mapper phát **0, 1 hoặc nhiều** phần tử qua `Consumer.accept`.
- `mapMulti` và các biến thể primitive xuất hiện từ **Java 16**; `flatMap` có từ Java 8.
- Với nhiều input mà mỗi input sinh rất ít output, `mapMulti` **có thể** giảm overhead nhưng **không được bảo đảm** nhanh hơn `flatMap`.
- Javadoc cho phép `mapMulti` được triển khai qua **bộ đệm nội bộ và `flatMap`**; đừng khẳng định bộ nhớ O(1) hoặc zero allocation.
- Consumer của `mapMulti` trả `void`, **không truyền tín hiệu dừng** như `Gatherer.Downstream.push`. Với nguồn con dài hoặc downstream dừng sớm, cân nhắc `flatMap` lazy và đo thực tế.
- Khi nguồn con đã là Stream hoặc sở hữu tài nguyên I/O, **quyền sở hữu và đóng nguồn** là yếu tố quyết định, không chỉ độ ngắn của mã.
- Dùng `mapMultiToInt/Long/Double` và `flatMapToInt/Long/Double` để so đúng loại primitive, tránh chênh lệch do boxing.
- Mapper nên stateless, non-interfering và không giữ Consumer để dùng sau callback; song song không mặc định tăng tốc.
- **Kiểm tra tính tương đương bằng oracle và ca biên**, sau đó benchmark cùng dữ liệu, fan-out, terminal operation và JVM bằng JMH hoặc công cụ phù hợp.
- Khi chênh lệch không có ý nghĩa trong pipeline thực, **ưu tiên cách dễ hiểu và dễ bảo trì**.

**Ý chính:** Chọn giữa `flatMap` và `mapMulti` không phải một mẹo thay tên phương thức. Hãy xem **dữ liệu con có hình dạng nào, số đầu ra trên mỗi input là bao nhiêu, có cần dừng sớm hoặc đóng nguồn không**, rồi kiểm tra kết quả trước và đo hiệu năng trên workload đại diện. Một tối ưu đáng dùng là tối ưu **vừa đúng ngữ nghĩa, vừa có lợi ích đo được**.
