# Giảm boxing khi chọn đúng biến thể primitive

Trong Java hiện đại, Stream API cung cấp các kiểu Stream chuyên biệt cho ba kiểu số nguyên thủy thường dùng: `int`, `long` và `double`. Khi mapper phát dữ liệu số, chọn đúng biến thể primitive của `mapMulti` giúp giữ kết quả ở dạng nguyên thủy trong pipeline, tránh việc đóng gói từng giá trị thành `Integer`, `Long` hoặc `Double` ở ranh giới đầu ra.

Có hai trường hợp cần phân biệt:

- Nguồn là Stream đối tượng nhưng kết quả là số nguyên thủy: dùng `Stream<T>.mapMultiToInt`, `mapMultiToLong` hoặc `mapMultiToDouble`.
- Nguồn đã là primitive Stream và kết quả cùng kiểu nguyên thủy: dùng `IntStream.mapMulti`, `LongStream.mapMulti` hoặc `DoubleStream.mapMulti`.

Chọn primitive specialization có ích khi các bước tiếp theo tiếp tục tính toán trên số nguyên thủy. Nếu API hoặc mô hình dữ liệu cần object, việc chuyển đổi sang wrapper vẫn có thể cần thiết.

## 1. Boxing và unboxing trong Stream pipeline

Java có các kiểu nguyên thủy như `int`, `long` và `double` cùng các kiểu wrapper tương ứng là `Integer`, `Long` và `Double`.

- **Boxing** là chuyển giá trị nguyên thủy thành object wrapper, ví dụ `int` thành `Integer`.
- **Unboxing** là lấy giá trị nguyên thủy từ wrapper, ví dụ `Integer` thành `int`.

Một ví dụ boxing tường minh:

```java
int count = 12;
Integer boxedCount = count;
```

Trong Stream API, boxing và unboxing có thể được chèn tự động khi kiểu tham số hoặc kiểu kết quả yêu cầu wrapper:

```java
import java.util.List;

List<Integer> values = List.of(10, 20, 30);

List<Integer> doubled = values.stream()
    .map(value -> value * 2)
    .toList();
```

`Stream<Integer>` chứa phần tử tham chiếu kiểu `Integer`. Biểu thức `value * 2` unbox `value` để thực hiện phép nhân, sau đó kết quả `int` được box thành `Integer` để trở thành phần tử đầu ra của Stream.

Boxing không đồng nghĩa chắc chắn mỗi lần đều tạo một object mới; JVM có thể tối ưu một số trường hợp. Tuy vậy, kiểu dữ liệu của pipeline vẫn là kiểu tham chiếu, và chương trình phải tuân theo hợp đồng `Stream<Integer>`.

## 2. Primitive Stream giúp giữ kiểu số nguyên thủy

Java cung cấp ba primitive Stream chính:

| Primitive Stream | Kiểu phần tử | Wrapper tương ứng |
|---|---|---|
| `IntStream` | `int` | `Integer` |
| `LongStream` | `long` | `Long` |
| `DoubleStream` | `double` | `Double` |

Các kiểu này có những phép toán số học chuyên biệt như `sum()`, `average()`, `min()`, `max()` và `summaryStatistics()`. Khi pipeline vẫn làm việc với primitive Stream, mỗi phần tử không cần mang kiểu wrapper ở giao diện Stream.

Ví dụ:

```java
import java.util.stream.IntStream;

int total = IntStream.of(10, 20, 30)
    .map(value -> value * 2)
    .sum();
```

Nguồn và kết quả đều là `IntStream`. Phép nhân và phép cộng làm việc với `int`; không cần tạo `Stream<Integer>` chỉ để tính tổng.

Primitive specialization không phải một bảo đảm rằng toàn bộ pipeline không có bất kỳ allocation nào. Nó xác định kiểu phần tử và các functional interface primitive ở API; việc cấp phát nội bộ và tối ưu hóa phụ thuộc implementation và JVM.

## 3. Vì sao mapMulti generic có thể gây boxing?

`Stream<T>.mapMulti` trả về `Stream<R>` và nhận một `Consumer<R>` để phát kết quả. Khi `R` là wrapper số, giá trị nguyên thủy được phát có thể phải boxing để phù hợp với `Consumer<Integer>`, `Consumer<Long>` hoặc `Consumer<Double>`.

Ví dụ tạo `Stream<Integer>`:

```java
import java.util.List;

List<String> codes = List.of("A12", "B305", "X9");

List<Integer> digits = codes.stream()
    .<Integer>mapMulti((code, emit) -> {
        for (int index = 0; index < code.length(); index++) {
            char ch = code.charAt(index);

            if (Character.isDigit(ch)) {
                emit.accept(Character.digit(ch, 10));
            }
        }
    })
    .toList();
```

`Character.digit` trả về `int`, nhưng `emit` có kiểu `Consumer<Integer>`. Java chuyển giá trị nguyên thủy thành `Integer` để gọi `accept(Integer)`. Kết quả là `Stream<Integer>` và danh sách thu được chứa wrapper.

Nếu bước tiếp theo chỉ cần tính toán trên chữ số, việc tạo các giá trị wrapper không cần thiết cho mục tiêu đó.

## 4. Dùng mapMultiToInt khi nguồn là object và kết quả là int

`Stream<T>.mapMultiToInt` nhận phần tử nguồn kiểu `T` và một `IntConsumer` để phát giá trị `int`. Kết quả là `IntStream`.

Chữ ký tổng quát:

```java
IntStream mapMultiToInt(
    BiConsumer<? super T, ? super IntConsumer> mapper
)
```

Có thể viết lại ví dụ trích chữ số:

```java
import java.util.List;

List<String> codes = List.of("A12", "B305", "X9");

int[] digits = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int index = 0; index < code.length(); index++) {
            char ch = code.charAt(index);

            if (Character.isDigit(ch)) {
                emit.accept(Character.digit(ch, 10));
            }
        }
    })
    .toArray();
```

Kết quả:

```text
[1, 2, 3, 0, 5, 9]
```

`emit` có kiểu `IntConsumer`, vì vậy `Character.digit` truyền giá trị `int` trực tiếp vào `accept(int)`. Kết quả là `IntStream` và được thu vào `int[]`.

Nguồn vẫn là `Stream<String>` vì các mã là object. Primitive specialization áp dụng ở đầu ra: các chữ số được phát thành `int` mà không cần chuyển từng chữ số thành `Integer` trong kiểu phần tử của Stream kết quả.

## 5. So sánh generic mapMulti và mapMultiToInt

Hai cách viết có thể phát cùng dữ liệu, nhưng kiểu đầu ra khác nhau:

```java
import java.util.List;

List<String> codes = List.of("A12", "B305", "X9");

// Stream<Integer>: emit nhận Consumer<Integer>
List<Integer> boxedDigits = codes.stream()
    .<Integer>mapMulti((code, emit) -> {
        for (int i = 0; i < code.length(); i++) {
            char ch = code.charAt(i);
            if (Character.isDigit(ch)) {
                emit.accept(Character.digit(ch, 10));
            }
        }
    })
    .toList();

// IntStream: emit nhận IntConsumer
int digitSum = codes.stream()
    .mapMultiToInt((code, emit) -> {
        for (int i = 0; i < code.length(); i++) {
            char ch = code.charAt(i);
            if (Character.isDigit(ch)) {
                emit.accept(Character.digit(ch, 10));
            }
        }
    })
    .sum();
```

| Tiêu chí | `mapMulti` với `R = Integer` | `mapMultiToInt` |
|---|---|---|
| Kiểu kết quả | `Stream<Integer>` | `IntStream` |
| Consumer mapper | `Consumer<Integer>` | `IntConsumer` |
| Giá trị phát | Wrapper `Integer` | Primitive `int` |
| Thu thập thành mảng | Cần chuyển đổi hoặc collector phù hợp | `toArray()` trả về `int[]` |
| Phép tính tổng | Thường unbox qua mapper hoặc collector | Có sẵn `sum()` |
| Dùng khi | API phía sau cần object `Integer` | Các bước tiếp theo xử lý số nguyên thủy |

Nếu kết quả cần là danh sách wrapper, `mapMulti` có thể là lựa chọn tự nhiên. Nếu kết quả được cộng, thống kê, lọc hoặc lưu trong mảng primitive, `mapMultiToInt` thường phù hợp hơn.

## 6. Chọn mapMultiToLong cho dữ liệu long

Khi kết quả là số nguyên dài, dùng `mapMultiToLong`. Mapper nhận `LongConsumer` và Stream kết quả là `LongStream`.

```java
LongStream mapMultiToLong(
    BiConsumer<? super T, ? super LongConsumer> mapper
)
```

Ví dụ, mỗi giao dịch có thể phát số tiền và phí theo đơn vị xu. Dùng `long` để biểu diễn số tiền nguyên theo đơn vị nhỏ nhất:

```java
import java.util.List;

record Transfer(String reference, long amountCents, long feeCents) {}

List<Transfer> transfers = List.of(
    new Transfer("TX-01", 125_000_000L, 2_500L),
    new Transfer("TX-02", 80_000_000L, 1_500L)
);

long totalCents = transfers.stream()
    .mapMultiToLong((transfer, emit) -> {
        emit.accept(transfer.amountCents());
        emit.accept(transfer.feeCents());
    })
    .sum();
```

Mỗi giao dịch phát hai giá trị `long`. `LongConsumer.accept(long)` nhận giá trị nguyên thủy và `LongStream.sum()` cộng chúng mà không cần tạo `Long` cho từng giá trị đầu ra.

Ví dụ dùng đơn vị xu để tránh sai số thập phân của `double`. Trong hệ thống tài chính, cần xác định rõ đơn vị tiền, quy tắc làm tròn và miền giá trị; nếu phép tính có thể vượt phạm vi `long`, cần kiểu số lớn hơn như `BigInteger` hoặc mô hình số thập phân phù hợp như `BigDecimal`.

## 7. Chọn mapMultiToDouble cho dữ liệu double

Khi kết quả là số dấu phẩy động, dùng `mapMultiToDouble`. Mapper nhận `DoubleConsumer` và trả về `DoubleStream`.

```java
DoubleStream mapMultiToDouble(
    BiConsumer<? super T, ? super DoubleConsumer> mapper
)
```

Ví dụ, một thiết bị có hai cảm biến dự phòng đo cùng đại lượng nhiệt độ. Ta phát các giá trị hữu hạn để tính trung bình:

```java
import java.util.List;

record TemperaturePair(String deviceId, double primary, double backup) {}

List<TemperaturePair> devices = List.of(
    new TemperaturePair("D-01", 24.5, 24.7),
    new TemperaturePair("D-02", 28.0, Double.NaN),
    new TemperaturePair("D-03", 26.5, 26.4)
);

double average = devices.stream()
    .mapMultiToDouble((device, emit) -> {
        if (Double.isFinite(device.primary())) {
            emit.accept(device.primary());
        }

        if (Double.isFinite(device.backup())) {
            emit.accept(device.backup());
        }
    })
    .average()
    .orElse(0.0);
```

Các giá trị được phát dưới dạng `double` qua `DoubleConsumer`. `DoubleStream.average()` trả về `OptionalDouble` vì Stream có thể rỗng; ví dụ dùng `orElse(0.0)` để minh họa cách chọn giá trị thay thế. Trong nghiệp vụ, cần quyết định rõ có nên xem không có phép đo là trung bình bằng không hay phải báo trạng thái thiếu dữ liệu.

`double` phù hợp với nhiều phép đo và tính toán khoa học, nhưng không biểu diễn chính xác mọi số thập phân. Với tiền tệ hoặc quy tắc thập phân chính xác, dùng `BigDecimal`; primitive specialization không thay đổi đặc tính biểu diễn của kiểu số.

## 8. Khi nguồn đã là primitive Stream, dùng mapMulti cùng kiểu

Nếu dữ liệu nguồn đã là `IntStream`, `LongStream` hoặc `DoubleStream`, không cần chuyển về `Stream<Integer>`, `Stream<Long>` hay `Stream<Double>` chỉ để dùng mapper.

| Kiểu nguồn | Phương thức | Mapper chuyên biệt | Kiểu kết quả |
|---|---|---|---|
| `IntStream` | `IntStream.mapMulti` | `IntMapMultiConsumer` và `IntConsumer` | `IntStream` |
| `LongStream` | `LongStream.mapMulti` | `LongMapMultiConsumer` và `LongConsumer` | `LongStream` |
| `DoubleStream` | `DoubleStream.mapMulti` | `DoubleMapMultiConsumer` và `DoubleConsumer` | `DoubleStream` |

Ví dụ với `IntStream`:

```java
import java.util.stream.IntStream;

int total = IntStream.of(1, 2, 3)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value * 10);
    })
    .sum();
```

Mỗi số nguồn phát chính nó và giá trị gấp mười. Toàn bộ pipeline vẫn là `IntStream`.

Ví dụ với `LongStream`:

```java
import java.util.stream.LongStream;

long total = LongStream.of(1_000_000_000L, 2_000_000_000L)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value / 2L);
    })
    .sum();
```

Ví dụ với `DoubleStream`:

```java
import java.util.stream.DoubleStream;

double total = DoubleStream.of(1.5, 2.5)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value / 2.0);
    })
    .sum();
```

Các ví dụ đều phát trực tiếp primitive cùng kiểu. Không cần wrapper trung gian trong hợp đồng phần tử của Stream.

## 9. Bảng chọn biến thể theo kiểu nguồn và kiểu đầu ra

Chọn phương thức dựa trên kiểu phần tử nguồn và kiểu đầu ra mong muốn:

| Kiểu nguồn | Kết quả object | Kết quả int | Kết quả long | Kết quả double |
|---|---|---|---|---|
| `Stream<T>` | `mapMulti` | `mapMultiToInt` | `mapMultiToLong` | `mapMultiToDouble` |
| `IntStream` | `mapToObj` (sau đó có thể dùng `Stream.mapMulti`) | `mapMulti` | `asLongStream().mapMulti` | `asDoubleStream().mapMulti` |
| `LongStream` | `mapToObj` (sau đó có thể dùng `Stream.mapMulti`) | `mapToInt(...).mapMulti` | `mapMulti` | `asDoubleStream().mapMulti` |
| `DoubleStream` | `mapToObj` (sau đó có thể dùng `Stream.mapMulti`) | `mapToInt(...).mapMulti` | `mapToLong(...).mapMulti` | `mapMulti` |

Các phương thức `mapMultiToInt`, `mapMultiToLong` và `mapMultiToDouble` thuộc `Stream<T>`. Primitive Stream có phương thức `mapMulti` cho đầu vào và đầu ra cùng primitive type. Khi cần đổi primitive type, hãy dùng phép chuyển đổi tương ứng như `mapToLong`, `asLongStream` hoặc `mapToDouble` trước khi tiếp tục pipeline.

Ví dụ chuyển `IntStream` thành `LongStream` rồi phát nhiều giá trị `long`:

```java
import java.util.stream.IntStream;

long total = IntStream.of(2, 3)
    .asLongStream()
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value * 10L);
    })
    .sum();
```

Không có phương thức `IntStream.mapMultiToLong`. Chuyển kiểu Stream trước, sau đó dùng `LongStream.mapMulti`.

## 10. Boxing có thể xuất hiện ở đầu vào

Primitive output không có nghĩa toàn bộ pipeline không boxing. Nếu nguồn là `Stream<Integer>`, phần tử nguồn vẫn là object `Integer`. Khi mapper dùng phép toán số học hoặc truyền phần tử vào `IntConsumer`, Java có thể unbox wrapper thành `int`.

Ví dụ:

```java
import java.util.List;

List<Integer> values = List.of(10, 20, 30);

int total = values.stream()
    .mapMultiToInt((value, emit) -> {
        emit.accept(value);
        emit.accept(value * 2);
    })
    .sum();
```

Ở đây:

- Nguồn là `Stream<Integer>` nên phần tử đọc từ nguồn là wrapper.
- Phép tính `value * 2` unbox `value` thành `int`.
- `IntConsumer.accept(int)` nhận giá trị nguyên thủy.
- Kết quả là `IntStream` và `sum()` trả về `int`.

Nếu dữ liệu ban đầu là collection wrapper và pipeline thực hiện nhiều phép toán số, có thể chuyển sang primitive Stream sớm:

```java
import java.util.List;

List<Integer> values = List.of(10, 20, 30);

int total = values.stream()
    .mapToInt(Integer::intValue)
    .mapMulti((value, emit) -> {
        emit.accept(value);
        emit.accept(value * 2);
    })
    .sum();
```

Sau `mapToInt(Integer::intValue)`, pipeline là `IntStream`. Các thao tác phía sau tiếp tục làm việc với `int`. Việc chuyển từ collection wrapper sang primitive vẫn cần đọc và unbox từng phần tử một lần; lợi ích là không tiếp tục mang wrapper qua các bước số học tiếp theo.

## 11. Xử lý null trước khi unbox

Wrapper có thể là `null`, còn primitive không có giá trị null. Nếu nguồn là `Stream<Integer>` hoặc collection chứa `Integer` nullable, phải kiểm tra null trước khi thực hiện unboxing.

```java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(10, null, 30);

int[] validValues = values.stream()
    .mapMultiToInt((value, emit) -> {
        if (value != null) {
            emit.accept(value);
        }
    })
    .toArray();
```

Nhánh kiểm tra null bảo đảm không unbox một tham chiếu null. Nếu bỏ kiểm tra rồi gọi `emit.accept(value)` với `value == null`, Java sẽ ném `NullPointerException` trong quá trình unboxing.

Nếu miền dữ liệu không cho phép null, hãy xác thực ở ranh giới đầu vào. Primitive Stream thích hợp sau khi dữ liệu đã được chuyển thành các giá trị primitive hợp lệ.

## 12. Khi nào cần chuyển ngược sang wrapper?

Primitive Stream không phải lúc nào cũng là kết quả cuối phù hợp. Nếu API nhận `List<Integer>`, `List<Long>` hoặc `List<Double>`, cần chuyển primitive về wrapper bằng `boxed()` hoặc tạo object bằng `mapToObj`.

Ví dụ thu thành `List<Integer>`:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.of(1, 2, 3)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number * 2);
    })
    .boxed()
    .toList();
```

Ví dụ tạo nhãn String mà không cần boxing thành wrapper trước:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.of(10, 20, 30)
    .mapMulti((number, emit) -> {
        emit.accept(number);
        emit.accept(number + 1);
    })
    .mapToObj(number -> "value=" + number)
    .toList();
```

`mapToObj` chuyển trực tiếp mỗi `int` thành String. Cách này tránh một bước trung gian `Integer` nếu mục tiêu cuối là object kiểu String.

Nếu hợp đồng API bắt buộc trả về `List<Integer>`, boxing là một phần cần thiết của chuyển đổi. Không nên né wrapper bằng mọi giá rồi làm mã phức tạp hơn.

## 13. Không phải mọi kiểu nguyên thủy đều có primitive Stream riêng

Java Stream API có primitive specialization cho `int`, `long` và `double`. Không có các kiểu Stream chuyên biệt tương ứng cho `byte`, `short`, `char` hoặc `boolean`.

Nếu dữ liệu là byte hoặc short và cần xử lý bằng Stream, thường phải chuyển sang `IntStream` sau khi mở rộng giá trị. Với dữ liệu boolean hoặc kiểu object khác, dùng `Stream<T>` phù hợp.

Không nên ép kiểu dữ liệu sang `int`, `long` hoặc `double` chỉ để tránh boxing nếu phép chuyển đổi làm mất ngữ nghĩa hoặc độ chính xác. Chọn kiểu biểu diễn theo miền dữ liệu trước, rồi mới chọn Stream operation tương ứng.

## 14. Primitive specialization không bảo đảm nhanh hơn trong mọi trường hợp

Dùng `IntStream`, `LongStream` hoặc `DoubleStream` có thể giảm boxing ở các ranh giới kiểu phần tử và cho phép dùng trực tiếp phép toán primitive. Tuy nhiên, không thể kết luận một pipeline luôn nhanh hơn chỉ từ việc đổi `mapMulti` sang biến thể primitive.

Hiệu năng còn phụ thuộc:

- Nguồn dữ liệu đã là primitive hay wrapper.
- Số phần tử được phát từ mỗi lần mapper.
- Chi phí logic trong mapper.
- Các thao tác phía sau và kiểu kết quả terminal.
- JDK, JVM, dữ liệu thực tế và khả năng tối ưu của JIT.

Nếu mỗi phần tử phát rất nhiều kết quả, cần cân nhắc liệu `mapMulti` có còn là cách biểu diễn phù hợp hay `flatMapToInt`, `flatMapToLong` hoặc `flatMapToDouble` với primitive Stream con sẽ rõ hơn. Không dựa vào `limit()` phía sau để giả định vòng lặp phát dữ liệu bên trong mapper tự dừng ngay giữa callback.

Khi tối ưu hiệu năng, hãy đo pipeline đại diện với dữ liệu và môi trường triển khai thực tế. Primitive specialization là lựa chọn kiểu dữ liệu rõ ràng; nó không phải cam kết hiệu năng tuyệt đối hay cam kết không cấp phát.

## 15. Checklist chọn đúng biến thể

Trước khi viết mapper, hãy xác định:

1. **Nguồn là gì?** `Stream<T>` hay `IntStream`, `LongStream`, `DoubleStream`?
2. **Kết quả cần kiểu nào?** Object, `int`, `long` hay `double`?
3. **Có cần phát nhiều phần tử không?** Nếu chỉ một kết quả, `map` hoặc `mapToInt`, `mapToLong`, `mapToDouble` thường rõ hơn.
4. **Pipeline phía sau làm gì?** Nếu cần phép toán số học, giữ primitive Stream; nếu API cần object, chuyển đổi ở ranh giới phù hợp.
5. **Nguồn wrapper có thể null không?** Kiểm tra trước khi unbox.
6. **Có đổi kiểu primitive không?** Dùng thao tác chuyển kiểu trước khi gọi `mapMulti` trên primitive Stream.
7. **Fan-out có lớn không?** Nếu mỗi phần tử có thể tạo rất nhiều giá trị, cân nhắc Stream con và `flatMap`.
8. **Hiệu năng có thực sự là vấn đề không?** Đo workload đại diện thay vì suy luận chỉ từ tên API.

## 16. Lỗi thường gặp

**Dùng `mapMulti` generic để phát Integer trong pipeline số học.** Nếu kết quả cần là `int`, `mapMultiToInt` giúp giữ đầu ra trong `IntStream` và dùng `IntConsumer`.

**Nghĩ rằng primitive output loại bỏ boxing ở đầu vào.** Với `Stream<Integer>`, phần tử nguồn vẫn là wrapper và có thể cần unbox. Primitive specialization chỉ đảm bảo kiểu đầu ra của phương thức là primitive Stream.

**Dùng `boxed()` quá sớm.** Chuyển primitive Stream thành `Stream<Integer>`, `Stream<Long>` hoặc `Stream<Double>` sẽ đưa wrapper trở lại pipeline. Chỉ boxing khi bước sau cần object.

**Cố giữ primitive Stream dù API yêu cầu object.** Nếu cần `List<Integer>`, dùng `boxed()` là hợp lý. Mục tiêu là chọn đúng kiểu theo từng giai đoạn, không phải loại bỏ wrapper trong mọi trường hợp.

**Bỏ qua null trong nguồn wrapper.** Unboxing một tham chiếu null gây `NullPointerException`. Kiểm tra null hoặc xác thực dữ liệu trước khi chuyển sang primitive.

**Nhầm phương thức chuyển kiểu.** `Stream<T>.mapMultiToInt` nhận nguồn object; `IntStream.mapMulti` nhận nguồn int. Chọn theo kiểu Stream đang có.

**Cho rằng primitive specialization bảo đảm không allocation hoặc luôn nhanh hơn.** API quy định kiểu dữ liệu và functional interface; hiệu năng thực tế phụ thuộc implementation, JVM và workload.

**Dùng double cho giá trị cần độ chính xác thập phân.** Primitive specialization không sửa sai số IEEE 754. Với tiền tệ hoặc số thập phân chính xác, chọn `BigDecimal` hoặc biểu diễn số nguyên theo đơn vị nhỏ nhất khi phù hợp.

## 17. Ghi nhớ

- `Stream<T>.mapMulti` phát object qua `Consumer<R>`; nếu `R` là wrapper số, giá trị primitive có thể phải boxing.
- `mapMultiToInt`, `mapMultiToLong` và `mapMultiToDouble` phát primitive qua `IntConsumer`, `LongConsumer` và `DoubleConsumer`.
- `IntStream.mapMulti`, `LongStream.mapMulti` và `DoubleStream.mapMulti` nhận primitive nguồn và phát kết quả cùng kiểu.
- Primitive Stream hỗ trợ phép toán chuyên biệt như `sum()`, `average()`, `min()`, `max()` và `summaryStatistics()`.
- Nguồn wrapper vẫn có thể cần unbox; kiểm tra null trước khi chuyển wrapper thành primitive.
- Dùng `boxed()` hoặc `mapToObj` khi bước tiếp theo cần object.
- Primitive specialization giảm boxing ở các ranh giới thích hợp nhưng không bảo đảm toàn bộ pipeline không cấp phát hoặc luôn nhanh hơn.
- Chọn biến thể theo kiểu nguồn, kiểu kết quả và các thao tác phía sau.

Khi dữ liệu đầu ra là số và các bước tiếp theo tiếp tục tính toán số học, chọn đúng biến thể primitive của `mapMulti` giúp pipeline thể hiện rõ kiểu dữ liệu, hạn chế boxing không cần thiết và tận dụng các thao tác chuyên biệt của `IntStream`, `LongStream` hoặc `DoubleStream`.

