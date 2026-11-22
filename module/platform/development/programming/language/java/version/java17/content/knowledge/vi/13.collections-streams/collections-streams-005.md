# Biến đổi một phần tử thành nhiều phần tử bằng mapMulti trong Java 17

> **Chủ đề:** Java 17
> **Chương:** Collection và Stream

## 1. Bài toán

Một phần tử đầu vào đôi khi cần tạo ra không, một hoặc nhiều phần tử đầu ra: một đơn hàng có nhiều dòng chi tiết, một câu có nhiều từ, một Optional có thể rỗng, hoặc một bản ghi có thể tạo nhiều sự kiện.

Stream API có các thao tác:

| Thao tác | Ý nghĩa |
|---|---|
| `map` | Một phần tử thành đúng một phần tử |
| `filter` | Giữ lại hoặc loại bỏ phần tử |
| `flatMap` | Một phần tử thành Stream con, sau đó làm phẳng |
| `mapMulti` | Phát ra không, một hoặc nhiều phần tử qua consumer |

`mapMulti` được bổ sung từ Java 16 và là API ổn định trong Java 17. Nó hữu ích khi logic biến đổi có thể viết tự nhiên bằng vòng lặp hoặc điều kiện.

## 2. mapMulti hoạt động như thế nào?

Với Stream đối tượng, chữ ký phương thức trong Java 17 có dạng:

```java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper)
```

Trong đó:

- `T` là kiểu phần tử của Stream nguồn.
- `R` là kiểu phần tử của Stream kết quả.
- `mapper` được gọi cho từng phần tử nguồn.
- Tham số thứ hai của mapper là một `Consumer<R>` dùng để phát ra phần tử đầu ra.
- Có thể gọi `consumer.accept(value)` không lần nào, một lần hoặc nhiều lần.

Mapper **đẩy trực tiếp** kết quả qua consumer. Mapper không trả về một Stream con như `flatMap`.

### 2.1. Ví dụ: Một chuỗi tạo ra các ký tự

```java
import java.util.List;

public class MapMultiIntro {
    public static void main(String[] args) {
        List<String> words = List.of("cat", "dog");

        List<Character> characters = words.stream()
                .<Character>mapMulti((word, output) -> {
                    for (char ch : word.toCharArray()) {
                        output.accept(ch);
                    }
                })
                .toList();

        System.out.println(characters);
    }
}
```

Kết quả là `[c, a, t, d, o, g]`. Với mỗi chuỗi, mapper phát từng ký tự theo thứ tự. `<Character>` là **type witness** chỉ rõ kiểu `R` của Stream kết quả. Khi lambda chỉ gọi `accept` hoặc không phát ra giá trị, viết tường minh giúp mã dễ hiểu và tránh lỗi suy luận kiểu.

### 2.2. Không phát ra phần tử nào

Nếu mapper không gọi consumer, phần tử nguồn tạo ra không có phần tử kết quả:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> evenNumbers = numbers.stream()
        .<Integer>mapMulti((number, output) -> {
            if (number % 2 == 0) {
                output.accept(number);
            }
        })
        .toList();

System.out.println(evenNumbers); // [2, 4]
```

Nếu chỉ muốn lọc rồi giữ nguyên giá trị, `filter` diễn đạt ý định tốt hơn:

```java
List<Integer> evenNumbers = numbers.stream()
        .filter(number -> number % 2 == 0)
        .toList();
```

### 2.3. Phát ra nhiều phần tử

```java
List<Integer> values = List.of(2, 3, 1);

List<Integer> expanded = values.stream()
        .<Integer>mapMulti((value, output) -> {
            for (int i = 0; i < value; i++) {
                output.accept(value);
            }
        })
        .toList();

System.out.println(expanded); // [2, 2, 3, 3, 3, 1]
```

Số lần gọi `accept` phụ thuộc giá trị đầu vào. Mỗi số `n` tạo ra `n` bản sao của chính nó.

## 3. So sánh mapMulti với flatMap

`flatMap` là thao tác quen thuộc để biến mỗi phần tử thành một Stream con rồi làm phẳng các Stream con thành một Stream duy nhất.

### 3.1. Cùng một bài toán viết bằng flatMap

Giả sử mỗi câu cần được tách thành các từ:

```java
import java.util.Arrays;
import java.util.List;

List<String> sentences = List.of(
        "Java Stream",
        "mapMulti example");

List<String> words = sentences.stream()
        .flatMap(sentence -> Arrays.stream(sentence.split(" ")))
        .toList();

System.out.println(words);
```

Kết quả:

```text
[Java, Stream, mapMulti, example]
```

Mỗi phần tử nguồn được ánh xạ thành một `Stream<String>`. `flatMap` đưa các phần tử của những Stream con vào một Stream kết quả.

### 3.2. Viết cùng logic bằng mapMulti

```java
import java.util.List;

List<String> sentences = List.of(
        "Java Stream",
        "mapMulti example");

List<String> words = sentences.stream()
        .<String>mapMulti((sentence, output) -> {
            for (String word : sentence.split(" ")) {
                output.accept(word);
            }
        })
        .toList();
```

Trong cách này, không cần tạo Stream con cho từng câu. Mapper duyệt mảng kết quả của `split` rồi phát từng từ.

### 3.3. So sánh cách tư duy

| Nội dung | `flatMap` | `mapMulti` |
|---|---|---|
| Mapper trả về | Một Stream cho mỗi phần tử | Không trả về Stream; phát kết quả qua consumer |
| Cách biểu diễn | Mỗi phần tử nguồn tạo một nguồn con | Mỗi phần tử nguồn thực hiện một thủ tục phát kết quả |
| Hợp với | Logic vốn đã có API trả Stream | Logic vòng lặp, điều kiện, có thể phát ít phần tử |
| Zero output | Trả về `Stream.empty()` | Không gọi consumer |
| One output | Trả về `Stream.of(value)` | Gọi `accept(value)` một lần |
| Many outputs | Trả về Stream chứa nhiều giá trị | Gọi `accept` nhiều lần |
| Tài nguyên Stream con | `flatMap` quản lý việc đóng Stream con sau khi tiêu thụ | Không cần tạo Stream con trong mapper |
| Hiệu năng | Có thể phát sinh Stream con và chi phí điều phối | Có thể giảm chi phí tạo Stream con trong một số trường hợp |

**Không nên kết luận `mapMulti` luôn nhanh hơn `flatMap`.** API được thiết kế để hỗ trợ cách phát kết quả trực tiếp, có thể giảm allocation trong một số workload. Tuy nhiên, hiệu năng phụ thuộc implementation, số lượng kết quả, logic mapper và pipeline. Hãy benchmark trên dữ liệu đại diện nếu hiệu năng là tiêu chí quan trọng.

### 3.4. Trường hợp nên dùng flatMap

Nếu phương thức xử lý đã tự nhiên trả về Stream, `flatMap` thường rõ ràng hơn:

```java
Stream<String> readWords(Path path) {
    // Ví dụ minh họa: một API trả về Stream<String>.
    return Stream.of("Java", "Stream");
}

List<String> allWords = paths.stream()
        .flatMap(this::readWords)
        .toList();
```

`flatMap` cũng có quy tắc đóng các Stream con sau khi nội dung được đưa vào pipeline. Nếu các Stream con quản lý tài nguyên, chẳng hạn Stream đọc file, quy tắc này rất quan trọng.

`mapMulti` không phải một API thay thế cơ chế quản lý tài nguyên của `flatMap`. Nếu mapper mở file hoặc tài nguyên khác, phải tự quản lý bằng `try-with-resources` và phát các giá trị trong thời gian tài nguyên còn mở.

## 4. Các ví dụ thực tế với Collection và Stream

### 4.1. Một đơn hàng tạo ra nhiều dòng sản phẩm

Mô hình:

```java
import java.util.List;

record OrderLine(String productCode, int quantity) { }
record Order(String orderId, List<OrderLine> lines) { }
```

Mỗi `Order` có nhiều `OrderLine`. Nếu cần danh sách tất cả dòng sản phẩm của nhiều đơn:

```java
List<Order> orders = List.of(
        new Order("ORD-1", List.of(
                new OrderLine("P-01", 2),
                new OrderLine("P-02", 1))),
        new Order("ORD-2", List.of(
                new OrderLine("P-03", 4))));

List<OrderLine> allLines = orders.stream()
        .<OrderLine>mapMulti((order, output) -> {
            for (OrderLine line : order.lines()) {
                output.accept(line);
            }
        })
        .toList();

System.out.println(allLines);
```

Kết quả:

```text
[OrderLine[productCode=P-01, quantity=2],
 OrderLine[productCode=P-02, quantity=1],
 OrderLine[productCode=P-03, quantity=4]]
```

Đây là trường hợp một phần tử nguồn (`Order`) tạo ra nhiều phần tử kết quả (`OrderLine`).

Nếu model đã có `order.lines()` trả về `List<OrderLine>`, cách `flatMap` cũng rất tự nhiên:

```java
List<OrderLine> allLines = orders.stream()
        .flatMap(order -> order.lines().stream())
        .toList();
```

Nên chọn theo phong cách và yêu cầu của mapper. `flatMap` ngắn gọn khi đã có collection/Stream con; `mapMulti` thuận tiện khi cần lọc, kiểm tra hoặc chuyển đổi trong vòng lặp trước khi phát kết quả.

### 4.2. Một giá trị tùy chọn tạo ra zero hoặc one output

`Optional` có thể chứa giá trị hoặc rỗng. Có thể chuyển một Stream các Optional thành Stream các giá trị có mặt:

```java
import java.util.List;
import java.util.Optional;

List<Optional<String>> inputs = List.of(
        Optional.of("Java"),
        Optional.empty(),
        Optional.of("Stream"));

List<String> values = inputs.stream()
        .<String>mapMulti((optional, output) ->
                optional.ifPresent(output))
        .toList();

System.out.println(values); // [Java, Stream]
```

Mỗi Optional có thể phát một chuỗi hoặc không phát gì. Trong trường hợp đơn giản này, có thể dùng:

```java
List<String> values = inputs.stream()
        .flatMap(Optional::stream)
        .toList();
```

`Optional.stream()` là API từ Java 9, vẫn dùng ổn định trong Java 17. Nếu chỉ cần loại bỏ Optional rỗng, cách `flatMap(Optional::stream)` rất dễ đọc.

### 4.3. Một bản ghi có thể tạo ra nhiều sự kiện

Giả sử một thay đổi tồn kho tạo ra các thông báo cho những ngưỡng cần theo dõi:

```java
import java.util.List;

record StockChange(String product, int before, int after) { }
record StockEvent(String product, String type, int quantity) { }

static List<StockEvent> events(List<StockChange> changes) {
    return changes.stream()
            .<StockEvent>mapMulti((change, output) -> {
                if (change.after() == 0) {
                    output.accept(new StockEvent(
                            change.product(), "OUT_OF_STOCK", 0));
                }

                if (change.before() > 10 && change.after() <= 10) {
                    output.accept(new StockEvent(
                            change.product(), "LOW_STOCK", change.after()));
                }

                if (change.after() > change.before()) {
                    output.accept(new StockEvent(
                            change.product(), "RESTOCKED", change.after()));
                }
            })
            .toList();
}
```

Một `StockChange` có thể phát không sự kiện nào, một sự kiện hoặc nhiều sự kiện. Mapper thể hiện trực tiếp quy tắc nghiệp vụ và thứ tự phát sự kiện.

Thứ tự `accept` trong một lần gọi mapper chính là thứ tự các sự kiện của bản ghi đó được đưa vào kết quả. Nếu thứ tự sự kiện có ý nghĩa nghiệp vụ, hãy giữ thứ tự phát rõ ràng và không dùng trạng thái dùng chung không xác định.

### 4.4. Mở rộng một dòng dữ liệu thành nhiều giá trị theo điều kiện

```java
record Product(String code, int stock, boolean active) { }

List<Product> products = List.of(
        new Product("A", 5, true),
        new Product("B", 0, true),
        new Product("C", 10, false));

List<String> availableCodes = products.stream()
        .<String>mapMulti((product, output) -> {
            if (product.active() && product.stock() > 0) {
                output.accept(product.code());
                if (product.stock() >= 10) {
                    output.accept(product.code() + "-BULK");
                }
            }
        })
        .toList();
```

Kết quả là `[A, C-BULK]`. Một sản phẩm có thể không tạo kết quả, tạo một mã hoặc tạo cả mã thường và mã bulk. Nếu chỉ muốn trả lại mã sản phẩm đủ điều kiện một lần, `filter` rồi `map` sẽ dễ hiểu hơn.

## 5. Dùng mapMulti với primitive streams

Java cung cấp các Stream chuyên biệt cho kiểu nguyên thủy:

- `IntStream`
- `LongStream`
- `DoubleStream`

Các API này tránh boxing/unboxing không cần thiết trong những pipeline số học.

### 5.1. IntStream.mapMulti

`IntStream` có phương thức `mapMulti` nhận `IntStream.IntMapMultiConsumer`, với tham số đầu ra là `IntConsumer`.

Ví dụ mỗi số nguyên `n` phát ra các số từ `1` đến `n`:

```java
import java.util.stream.IntStream;

int[] values = IntStream.of(2, 3, 1)
        .mapMulti((number, output) -> {
            for (int i = 1; i <= number; i++) {
                output.accept(i);
            }
        })
        .toArray();

System.out.println(java.util.Arrays.toString(values));
```

Kết quả:

```text
[1, 2, 1, 2, 3, 1]
```

Đầu vào là `IntStream`, đầu ra vẫn là `IntStream`. Các giá trị được phát qua `IntConsumer`, nên không cần chuyển từng số thành `Integer` rồi unbox lại.

### 5.2. Từ Stream<String> sang IntStream bằng mapMultiToInt

Khi Stream nguồn là Stream đối tượng nhưng kết quả là số nguyên, dùng `mapMultiToInt`:

```java
import java.util.List;

int[] codePoints = List.of("Java", "17").stream()
        .mapMultiToInt((text, output) ->
                text.codePoints().forEach(output))
        .toArray();
```

`String.codePoints()` trả về `IntStream` chứa Unicode code point. Consumer của `mapMultiToInt` nhận `int`, nên có thể truyền trực tiếp vào `forEach`.

Không nên nhầm `String.chars()` với `String.codePoints()`:

- `chars()` phát các giá trị UTF-16 code unit.
- `codePoints()` phát Unicode code point, có thể cần ghép cặp surrogate.

Nếu mục tiêu là xử lý ký tự Unicode ở mức code point, `codePoints()` thường phù hợp hơn.

### 5.3. mapMultiToLong và mapMultiToDouble

Từ Stream đối tượng có thể phát ra số `long` hoặc `double`:

```java
import java.util.List;

record Measurement(String sensor, double[] samples) { }

List<Measurement> measurements = List.of(
        new Measurement("S1", new double[] { 10.5, 11.0 }),
        new Measurement("S2", new double[] { 8.0, 9.5 }));

double[] allSamples = measurements.stream()
        .mapMultiToDouble((measurement, output) -> {
            for (double sample : measurement.samples()) {
                output.accept(sample);
            }
        })
        .toArray();
```

Tương tự, `mapMultiToLong` dùng `LongConsumer` để phát các giá trị `long`.

### 5.4. Các biến thể trên primitive streams

Các phương thức chính trong Java 17:

| Stream nguồn | Phương thức | Kiểu consumer đầu ra | Kiểu kết quả |
|---|---|---|---|
| `Stream<T>` | `mapMulti` | `Consumer<R>` | `Stream<R>` |
| `Stream<T>` | `mapMultiToInt` | `IntConsumer` | `IntStream` |
| `Stream<T>` | `mapMultiToLong` | `LongConsumer` | `LongStream` |
| `Stream<T>` | `mapMultiToDouble` | `DoubleConsumer` | `DoubleStream` |
| `IntStream` | `mapMulti` | `IntConsumer` | `IntStream` |
| `IntStream` | `mapMultiToObj` | `Consumer<R>` | `Stream<R>` |
| `LongStream` | `mapMulti` | `LongConsumer` | `LongStream` |
| `LongStream` | `mapMultiToObj` | `Consumer<R>` | `Stream<R>` |
| `DoubleStream` | `mapMulti` | `DoubleConsumer` | `DoubleStream` |
| `DoubleStream` | `mapMultiToObj` | `Consumer<R>` | `Stream<R>` |

Các interface consumer chuyên biệt được định nghĩa trong các primitive stream tương ứng, chẳng hạn `IntStream.IntMapMultiConsumer`.

## 6. Dùng mapMulti trong pipeline lớn

`mapMulti` là **intermediate operation**: nó không tự tiêu thụ Stream ngay tại chỗ. Các thao tác phía sau quyết định lúc nào dữ liệu được xử lý.

Ví dụ:

```java
List<String> result = orders.stream()
        .<OrderLine>mapMulti((order, output) -> {
            for (OrderLine line : order.lines()) {
                if (line.quantity() > 0) {
                    output.accept(line);
                }
            }
        })
        .filter(line -> line.productCode().startsWith("P-"))
        .map(line -> line.productCode() + ":" + line.quantity())
        .distinct()
        .sorted()
        .toList();
```

Pipeline:

```text
Stream<Order>
      |
      v
mapMulti: mỗi đơn phát các OrderLine có quantity > 0
      |
      v
filter: chỉ giữ mã bắt đầu bằng P-
      |
      v
map: chuyển OrderLine thành String
      |
      v
distinct
      |
      v
sorted
      |
      v
toList()
```

Trong pipeline này, `mapMulti` thực hiện việc mở rộng dữ liệu; các thao tác sau tiếp tục xử lý Stream kết quả. Không cần thu thập vào một danh sách trung gian rồi gọi `stream()` lần nữa.

### 6.1. Kết quả vẫn tuân theo encounter order của Stream có thứ tự

Với một Stream có encounter order, `mapMulti` giữ quan hệ thứ tự của các phần tử đầu vào và thứ tự mà mapper phát ra các phần tử cho mỗi đầu vào. Ví dụ:

```java
List<Integer> values = List.of(1, 2, 3).stream()
        .<Integer>mapMulti((number, output) -> {
            output.accept(number);
            output.accept(number * 10);
        })
        .toList();

System.out.println(values); // [1, 10, 2, 20, 3, 30]
```

Với Stream unordered, hoặc khi pipeline chủ động bỏ encounter order, không nên dựa vào một thứ tự mà nguồn không cam kết. `forEach` trên parallel stream cũng không đảm bảo thứ tự hiển thị; nếu cần thu kết quả theo encounter order, dùng terminal operation phù hợp như `toList()` hoặc `forEachOrdered()` tùy bài toán.

### 6.2. mapMulti không phải terminal operation

Đoạn này chưa thực thi pipeline:

```java
Stream<String> result = source
        .<String>mapMulti((value, output) -> output.accept(value));
```

Chỉ khi có terminal operation như `toList()`, `count()`, `reduce()` hoặc `forEach()` thì Stream mới được tiêu thụ:

```java
List<String> values = result.toList();
```

Stream chỉ được tiêu thụ một lần. Không dùng lại `result` cho một terminal operation thứ hai.

## 7. Những quy tắc và giới hạn cần hiểu

### 7.1. Consumer chỉ được sử dụng trong thời gian mapper đang chạy

Consumer được truyền vào mapper thuộc về pipeline. Hãy gọi `accept` **ngay trong lời gọi mapper**, không lưu consumer vào field, collection hoặc dùng sau khi mapper đã trả về.

Không nên giữ consumer để gọi bất đồng bộ hoặc sau khi mapper đã kết thúc. `mapMulti` được thiết kế để mapper phát dữ liệu đồng bộ trong phạm vi lần gọi của nó; dùng consumer ngoài thời gian đó nằm ngoài cách sử dụng được hỗ trợ.

### 7.2. Không thay đổi nguồn Stream trong mapper

Mapper nên là hàm không can thiệp vào nguồn dữ liệu (*non-interfering*). Ví dụ, nếu Stream được tạo từ một `ArrayList`, không thêm hoặc xóa phần tử của chính danh sách đó trong mapper:

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));

// Không nên sửa values trong khi stream của values đang được xử lý.
values.stream()
        .<Integer>mapMulti((value, output) -> {
            output.accept(value);
            // values.add(99); // Can thiệp nguồn Stream
        })
        .toList();
```

Việc sửa nguồn trong khi pipeline đang duyệt có thể gây lỗi, kết quả không mong đợi hoặc vi phạm hợp đồng Stream.

### 7.3. Tránh side effect phụ thuộc số lần mapper được gọi

Không nên dựa vào thứ tự hoặc số lần gọi side effect để tạo logic nghiệp vụ:

```java
int[] counter = { 0 };

List<Integer> values = source.stream()
        .<Integer>mapMulti((value, output) -> {
            counter[0]++;
            output.accept(value);
        })
        .toList();
```

Trong ví dụ tuần tự, có thể quan sát counter. Nhưng nếu đổi sang parallel stream, mapper có thể chạy đồng thời trên nhiều phần tử; mảng `counter` không thread-safe và kết quả có race condition.

Hãy giữ mapper stateless, không can thiệp dữ liệu nguồn và tránh side effect. Nếu cần thống kê, dùng terminal reduction phù hợp hoặc collector.

### 7.4. Parallel stream và consumer

Trong parallel stream, các lần gọi mapper cho các phần tử nguồn khác nhau có thể chạy trên các thread khác nhau. Consumer của từng lần gọi được dùng để phát kết quả của lần gọi đó; không nên gom các consumer vào một biến dùng chung.

Ví dụ:

```java
List<Integer> expanded = values.parallelStream()
        .<Integer>mapMulti((value, output) -> {
            output.accept(value);
            if (value % 2 == 0) {
                output.accept(value * 10);
            }
        })
        .toList();
```

Mapper không thay đổi state chung và chỉ phát giá trị dựa trên phần tử hiện tại. Với nguồn có encounter order, `toList()` thu kết quả theo thứ tự gặp của Stream, dù các phần xử lý có thể chạy song song.

Không nên sử dụng chung một `ArrayList` mutable để nhận kết quả bên trong mapper. Hãy để Stream quản lý việc truyền phần tử qua pipeline và dùng terminal operation/collector để thu thập.

### 7.5. Ngoại lệ trong mapper

Nếu mapper hoặc một lần gọi `consumer.accept` phát sinh exception, quá trình xử lý pipeline sẽ kết thúc bằng exception đó (hoặc exception phát sinh từ thao tác downstream). Không nên nuốt lỗi dữ liệu một cách âm thầm:

```java
List<String> values = records.stream()
        .<String>mapMulti((record, output) -> {
            if (record == null) {
                throw new IllegalArgumentException("record không được null");
            }
            output.accept(record.trim());
        })
        .toList();
```

Nếu nghiệp vụ muốn bỏ qua dữ liệu không hợp lệ, hãy thể hiện rõ bằng điều kiện không phát phần tử hoặc một kênh thu thập lỗi riêng.

## 8. Hiệu năng: khi nào mapMulti có thể hữu ích?

Một lý do chính để bổ sung `mapMulti` là giảm chi phí biểu diễn từng kết quả trung gian thành một Stream con. Hãy so sánh:

**Cách flatMap:**

```java
List<String> tokens = lines.stream()
        .flatMap(line -> Arrays.stream(line.split(",")))
        .toList();
```

**Cách mapMulti:**

```java
List<String> tokens = lines.stream()
        .<String>mapMulti((line, output) -> {
            for (String token : line.split(",")) {
                output.accept(token);
            }
        })
        .toList();
```

Ở cách `flatMap`, mỗi dòng tạo một Stream con. Ở cách `mapMulti`, mapper phát token trực tiếp. Khi mỗi đầu vào chỉ tạo một vài đầu ra và thao tác phát kết quả đơn giản, cách thứ hai có thể tránh một số đối tượng/chi phí điều phối Stream con.

Tuy nhiên:

- `split()` vẫn tạo mảng chuỗi; `mapMulti` không loại bỏ chi phí đó.
- Số lượng đầu ra rất lớn vẫn cần xử lý và lưu các phần tử tương ứng.
- Một implementation có thể dùng buffer nội bộ; đặc tả API không bảo đảm mọi implementation đều có cùng chiến lược allocation.
- Một mapper phức tạp hoặc dùng nhiều thao tác imperative có thể khó đọc hơn biểu thức `flatMap`.
- JIT có thể tối ưu một số pipeline theo cách khác nhau; chỉ benchmark mới cho biết workload cụ thể.

### 8.1. Benchmark đúng cách

Nếu cần quyết định giữa `flatMap` và `mapMulti` vì hiệu năng:

1. Dùng dữ liệu đại diện cho kích thước và phân bố thực tế.
2. Đo cả trường hợp zero, one và many outputs.
3. Chạy warm-up và đo nhiều lần; không kết luận từ một lần chạy `System.nanoTime()` đơn giản.
4. Đo allocation/GC nếu mục tiêu là giảm đối tượng Stream trung gian.
5. Dùng JMH (Java Microbenchmark Harness) cho benchmark vi mô thay vì tự viết vòng lặp đo thời gian.
6. Đảm bảo hai cách triển khai tạo cùng kết quả và thực hiện cùng công việc.

Không có một ngưỡng số phần tử chung để nói `mapMulti` luôn thắng. Hãy ưu tiên khả năng đọc và chỉ tối ưu khi có số liệu.

## 9. Các lỗi thường gặp khi dùng mapMulti

| Lỗi/hiểu nhầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ mapper phải trả về một giá trị | Viết sai chữ ký hoặc cố return kết quả | Gọi `output.accept(value)` để phát phần tử |
| Không gọi `accept` và mong giữ phần tử nguồn | Phần tử nguồn biến mất khỏi Stream kết quả | Gọi `accept` khi muốn phát lại hoặc dùng `map` |
| Dùng `mapMulti` cho phép biến đổi một-một đơn giản | Mã dài hơn `map` | Dùng `map` |
| Dùng `mapMulti` chỉ để lọc | Ý định khó đọc hơn `filter` | Dùng `filter` |
| Trả về Stream con từ mapper | Nhầm với `flatMap` | Dùng `flatMap` nếu đã có Stream con |
| Giữ consumer để gọi sau | Dùng consumer ngoài thời gian mapper | Phát đồng bộ ngay trong mapper |
| Chia sẻ collection mutable trong parallel mapper | Race condition hoặc lỗi dữ liệu | Dùng pipeline/collector, tránh side effect |
| Cho rằng `mapMulti` luôn nhanh hơn | Tối ưu không có số liệu | Benchmark workload thực tế |
| Quên chỉ rõ kiểu đầu ra khi compiler không suy luận được | Lỗi generic inference | Dùng type witness như `.<String>mapMulti(...)` |
| Dùng `Stream<Integer>` khi kết quả chỉ là số nguyên | Có thể phát sinh boxing | Cân nhắc `mapMultiToInt`/primitive stream |
| Bỏ qua thứ tự phát kết quả | Thứ tự nghiệp vụ có thể bị sai | Phát theo thứ tự xác định; giữ encounter order khi cần |
| Dùng `mapMulti` để mở tài nguyên nhưng không đóng | Rò rỉ file/socket/stream | Quản lý tài nguyên bằng try-with-resources hoặc API phù hợp |

## 10. Bài tập thực hành

### Bài 1 — Tách câu thành từ

Cho danh sách:

```java
List<String> sentences = List.of(
        "Java is useful",
        "Stream API",
        "mapMulti in Java 17");
```

Hãy dùng `mapMulti` để tạo một `List<String>` chứa tất cả từ theo đúng thứ tự xuất hiện. Không dùng `flatMap`.

**Gợi ý đáp án:**

```java
List<String> words = sentences.stream()
        .<String>mapMulti((sentence, output) -> {
            for (String word : sentence.split(" ")) {
                output.accept(word);
            }
        })
        .toList();
```

### Bài 2 — Chỉ phát số nguyên tố

Cho Stream số nguyên từ 1 đến 30. Dùng `mapMulti` để không phát số nhỏ hơn 2, phát một lần mỗi số nguyên tố và không phát số hợp số.

**Gợi ý đáp án:**

```java
static boolean isPrime(int n) {
    if (n < 2) return false;
    for (int divisor = 2; divisor * divisor <= n; divisor++) {
        if (n % divisor == 0) return false;
    }
    return true;
}

List<Integer> primes = java.util.stream.IntStream.rangeClosed(1, 30)
        .<Integer>mapMultiToObj((number, output) -> {
            if (isPrime(number)) {
                output.accept(number);
            }
        })
        .toList();
```

Trong bài này, nguồn là `IntStream`, nên `mapMultiToObj` phát các đối tượng `Integer` vào `Stream<Integer>`. Nếu muốn giữ kết quả là `IntStream`, hãy dùng `IntStream.mapMulti`.

### Bài 3 — Mở rộng đơn hàng thành dòng chi tiết

Định nghĩa:

```java
record Item(String sku, int quantity) { }
record Order(String id, List<Item> items) { }
```

Hãy dùng `mapMulti` để chỉ phát item có `quantity > 0` và tạo `List<Item>` kết quả.

**Gợi ý đáp án:**

```java
List<Item> items = orders.stream()
        .<Item>mapMulti((order, output) -> {
            for (Item item : order.items()) {
                if (item.quantity() > 0) {
                    output.accept(item);
                }
            }
        })
        .toList();
```

### Bài 4 — Chuyển Optional thành Stream

Cho `List<Optional<Integer>>`. Dùng `mapMulti` để tạo danh sách các số có mặt, sau đó viết lại bằng `flatMap(Optional::stream)`. So sánh độ dễ đọc của hai cách.

**Gợi ý:**

```java
List<Integer> first = optionals.stream()
        .<Integer>mapMulti((optional, output) ->
                optional.ifPresent(output))
        .toList();

List<Integer> second = optionals.stream()
        .flatMap(Optional::stream)
        .toList();
```

### Bài 5 — Phân biệt mapMulti và mapMultiToInt

Từ `List<String>`, hãy phát ra độ dài của từng chuỗi bằng `mapMultiToInt`. Sau đó thu kết quả bằng `sum()`.

**Gợi ý đáp án:**

```java
int totalLength = words.stream()
        .mapMultiToInt((word, output) -> output.accept(word.length()))
        .sum();
```

### Bài 6 — Phát ra nhiều kết quả theo điều kiện

Với mỗi số nguyên `n`, phát `n` nếu chẵn; phát `n` và `-n` nếu lẻ; không phát gì nếu `n == 0`. Xác định thứ tự kết quả với nguồn `[1, 2, 0, 3]`.

**Gợi ý đáp án:**

```java
List<Integer> result = List.of(1, 2, 0, 3).stream()
        .<Integer>mapMulti((n, output) -> {
            if (n == 0) {
                return;
            }
            output.accept(n);
            if (n % 2 != 0) {
                output.accept(-n);
            }
        })
        .toList();
```

Kết quả: `[1, -1, 2, 3, -3]`.

## 11. Tài liệu chính thức của Java 17

- [Java SE 17 API — Stream.mapMulti](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#mapMulti(java.util.function.BiConsumer)): chữ ký, mô tả mapper phát zero hoặc nhiều phần tử và ví dụ API.
- [Java SE 17 API — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): `mapMulti`, `mapMultiToObj` và `IntMapMultiConsumer`.
- [Java SE 17 API — LongStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html) và [DoubleStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html): các biến thể cho primitive streams.
- [Java SE 17 API — Optional.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html#stream()): chuyển Optional thành Stream chứa zero hoặc một phần tử.
- [Java SE 17 API — Stream.flatMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#flatMap(java.util.function.Function)): quy tắc làm phẳng và đóng Stream con.

**Ghi nhớ:** `mapMulti` cho phép một phần tử nguồn phát ra không, một hoặc nhiều phần tử qua consumer. Dùng `map` cho chuyển đổi một-một, `filter` cho giữ/bỏ, `flatMap` khi mapper tự nhiên trả về Stream con và `mapMulti` khi muốn phát kết quả trực tiếp bằng vòng lặp hoặc điều kiện. Trong Java 17, API này đã ổn định và có cả biến thể cho primitive streams.
