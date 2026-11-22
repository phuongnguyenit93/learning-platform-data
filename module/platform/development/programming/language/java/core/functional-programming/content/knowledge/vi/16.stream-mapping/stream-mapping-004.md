# `mapMulti()`: biến đổi một phần tử thành không, một hoặc nhiều phần tử trong Java Stream

Trong Java Stream, `map()` chuyển **mỗi phần tử đầu vào thành đúng một kết quả**, còn `flatMap()` chuyển mỗi phần tử thành một stream kết quả rồi nối các stream lại. Kể từ **Java 16**, `Stream.mapMulti()` cung cấp một cách diễn đạt khác: với mỗi phần tử, lambda được quyền **phát ra 0, 1 hoặc nhiều kết quả** qua một hàm `Consumer` được cung cấp sẵn.

Nhờ đó, ta có thể lọc và biến đổi cùng lúc, trải phẳng dữ liệu nhiều cấp, hoặc bỏ những giá trị không phù hợp mà không phải tạo một `Stream` trung gian cho từng phần tử. Trọng tâm của bài là hợp đồng của `mapMulti()`, kiểu dữ liệu, thứ tự kết quả, cách viết lambda đúng và khi nào nên chọn `flatMap()`.

## 1. Tư duy về số lượng kết quả

Với cùng một phần tử đầu vào `x`:

| Operation | Lambda nhận gì và trả gì? | Số phần tử đầu ra của mỗi `x` |
| --- | --- | --- |
| `map(f)` | `Function<T,R>`: trả **một `R`** | Đúng 1 (kể cả khi giá trị đó là `null`) |
| `filter(p)` | `Predicate<T>`: quyết định giữ hay bỏ chính `T` | 0 hoặc 1, không đổi kiểu phần tử |
| `flatMap(f)` | `Function<T,Stream<R>>`: trả một stream rồi được trải phẳng | 0, 1 hoặc nhiều |
| `mapMulti(mapper)` | `BiConsumer<T,Consumer<R>>`: gọi `accept(result)` cho từng kết quả muốn phát | 0, 1 hoặc nhiều |

Một callback `mapMulti()` được gọi với **hai đối số**: phần tử nguồn và “đầu ra” (`downstream`, `emit` hoặc `out` tùy tên do người viết đặt). Đầu ra này có phương thức `accept(R)`. Bạn gọi `accept` bao nhiêu lần thì có bấy nhiêu kết quả cho phần tử nguồn đó.

```text
Nguồn:               -2       0        3          5
                         |       |        |          |
mapMulti:            (bỏ)    emit(0)  emit(3,9)  emit(5,25)
                         |       |        |          |
Kết quả:                       [0,       3, 9,     5, 25]
                         0 kết quả   1       2          2
```

Đây là ví dụ minh họa logic, không phải sơ đồ lập lịch thread. `mapMulti()` là **intermediate operation, lazy**: callback chỉ được đánh giá khi một terminal operation (ví dụ `toList()`, `count()`, `sum()`) tiêu thụ pipeline, và các tối ưu hóa có thể ảnh hưởng số lần gọi trong những pipeline cụ thể.

## 2. Chữ ký và vòng đời của `downstream`

Chữ ký tổng quát trên `Stream<T>`:

```java
<R> Stream<R> mapMulti(
        BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Đây là chữ ký API rút gọn từ `java.util.stream.Stream`, **không phải chương trình Java độc lập**. Ý nghĩa:

- `T`: kiểu phần tử hiện có của stream.
- `R`: kiểu phần tử đầu ra mong muốn.
- `mapper`: nhận một `T` và một `Consumer<R>`.
- `downstream.accept(r)`: đẩy một giá trị `R` vào stream kết quả; gọi 0 lần là loại phần tử, gọi 1 lần là ánh xạ một-một, gọi nhiều lần là mở rộng.
- Bản thân `mapper` trả `void`. `return;` trong lambda chỉ **kết thúc lượt xử lý phần tử hiện tại**, không trả về một stream hoặc một phần tử.

`downstream` là callback do Stream cung cấp trong lượt xử lý. Theo hợp đồng API, kết quả phải được phát **trong lúc lambda đang được gọi**. **Không lưu `downstream` vào field/list để gọi sau**, không chuyển nó sang tác vụ bất đồng bộ rồi trả về ngay; vòng đời đó không được hỗ trợ và có thể tạo hành vi sai.

Mẫu cơ bản:

```java
Stream<Integer> source = Stream.of(-1, 0, 3);
List<Integer> result = source.<Integer>mapMulti((n, out) -> {
    if (n < 0) {
        return;             // Phát 0 kết quả cho -1.
    }

    out.accept(n);          // Phát ít nhất 1 kết quả.
    if (n > 0) {
        out.accept(n * n);  // Phát thêm kết quả.
    }
}).toList();
// result == [0, 3, 9]
```

Đoạn minh họa đặt trong phương thức, cần `import java.util.List;` và `import java.util.stream.Stream;`. Tại `n = -1`, không gọi `out.accept`; `n = 0` phát đúng một kết quả; `n = 3` phát hai kết quả `3` và `9`.

## 3. Ví dụ Java 17+ chạy đầy đủ

Lưu thành `MapMultiDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public class MapMultiDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(-2, 0, 3, 5);

        List<Integer> expanded = numbers.stream()
                .<Integer>mapMulti((n, out) -> {
                    if (n < 0) {
                        return;            // 0 kết quả.
                    }
                    out.accept(n);        // 1 kết quả.
                    if (n % 2 != 0) {
                        out.accept(n * n); // Thêm 1 kết quả.
                    }
                })
                .toList();
        System.out.println("expanded = " + expanded);

        List<String> lines = List.of(" Java 17 ", "", "map multi");

        List<String> words = lines.stream()
                .<String>mapMulti((line, out) -> {
                    for (String word : line.trim().split("\\s+")) {
                        if (!word.isBlank()) {
                            out.accept(word.toLowerCase(Locale.ROOT));
                        }
                    }
                })
                .toList();
        System.out.println("words = " + words);

        List<Object> mixed = List.of("text", 12, 3.5, 7, true);
        List<Integer> integers = mixed.stream()
                .<Integer>mapMulti((value, out) -> {
                    if (value instanceof Integer n) {
                        out.accept(n);
                    }
                })
                .toList();
        System.out.println("integers = " + integers);

        int sum = Stream.of("2,3", "7", "")
                .mapMultiToInt((field, out) -> {
                    if (field.isBlank()) {
                        return;
                    }
                    for (String token : field.split(",")) {
                        out.accept(Integer.parseInt(token));
                    }
                })
                .sum();
        System.out.println("sum = " + sum);
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 MapMultiDemo.java
java MapMultiDemo
```

Stdout mong đợi:

```text
expanded = [0, 3, 9, 5, 25]
words = [java, 17, map, multi]
integers = [12, 7]
sum = 12
```

Giải thích theo thứ tự:

1. Dãy `[-2, 0, 3, 5]`: `-2` không phát gì; `0` phát `0`; `3` phát `3` và `9`; `5` phát `5` và `25`.
2. Với mỗi dòng văn bản, vòng `for` tách các từ theo khoảng trắng; dòng rỗng không phát giá trị nào. Mỗi từ hợp lệ được đổi sang chữ thường rồi phát ra. Vì nguồn là `List` có thứ tự và các lần `accept` cũng có thứ tự, kết quả là `[java, 17, map, multi]`.
3. `instanceof Integer n` dùng *pattern matching for instanceof* (đã hỗ trợ trong Java 16). Các phần tử kiểu khác `Integer` bị bỏ qua; `mapMulti()` đồng thời **lọc kiểu** và **biến đổi sang `Stream<Integer>`**.
4. `mapMultiToInt` phát số nguyên trực tiếp vào `IntStream`; `sum()` nhận tổng `2 + 3 + 7 = 12`. Không cần boxing thành `Integer` để tính tổng.

Ví dụ không dùng tác dụng phụ trong mapper: các lambda chỉ chuyển dữ liệu đầu vào thành những giá trị được phát ra. `System.out.println` được thực hiện **sau** khi stream đã tạo kết quả.

## 4. Phân biệt `map()`, `filter()`, `flatMap()` và `mapMulti()`

### `map()`: một đầu vào thành đúng một đầu ra

```java
List<String> result = List.of("a", "bb").stream()
        .map(String::toUpperCase)
        .toList();
// [A, BB]
```

`map()` phù hợp khi mọi phần tử đều tạo ra **một kết quả**. Không cần `mapMulti()` chỉ để viết hoa từng chuỗi: cách này sẽ làm mã khó đọc hơn.

### `filter().map()`: lọc rồi ánh xạ

```java
List<Integer> result = List.of(-1, 2, -3, 4).stream()
        .filter(n -> n > 0)
        .map(n -> n * 10)
        .toList();
// [20, 40]
```

Với một điều kiện lọc đơn giản, `filter().map()` thường sáng rõ nhất. Có thể viết bằng `mapMulti()` nhưng không bắt buộc:

```java
List<Integer> result = List.of(-1, 2, -3, 4).stream()
        .<Integer>mapMulti((n, out) -> {
            if (n > 0) {
                out.accept(n * 10);
            }
        })
        .toList();
// [20, 40]
```

Các đoạn minh họa trong mục này cần `import java.util.List;` và đặt trong phương thức; chúng không phải chương trình Java độc lập.

### `flatMap()`: tạo stream con rồi trải phẳng

```java
List<String> result = List.of(
        List.of("a", "b"),
        List.of(),
        List.of("c")
).stream()
        .flatMap(List::stream)
        .toList();
// [a, b, c]
```

`flatMap` nhận hàm trả về `Stream<R>` cho mỗi phần tử. Nó phù hợp khi đã có stream con hoặc API tự nhiên trả về `Stream`, hoặc khi muốn biểu diễn một phép biến đổi phức tạp bằng những pipeline con độc lập.

Cùng bài toán với `mapMulti`:

```java
List<String> result = List.of(
        List.of("a", "b"),
        List.of(),
        List.of("c")
).stream()
        .<String>mapMulti((group, out) -> group.forEach(out))
        .toList();
// [a, b, c]
```

Đối với từng `group`, mapper duyệt các phần tử và phát chúng trực tiếp. Không cần gọi `group.stream()` để tạo một stream con cho mỗi nhóm. Tuy vậy, **không khẳng định `mapMulti` luôn nhanh hơn `flatMap`**: lợi ích phụ thuộc JDK, implementation của nguồn, kích thước dữ liệu, các operation tiếp theo và cách tối ưu JVM. Chỉ benchmark khi hiệu năng thật sự quan trọng.

### Khi nào nên ưu tiên `mapMulti()`?

- Mỗi đầu vào có **0 hoặc một vài kết quả** và cách phát kết quả rất tự nhiên trong một vòng `for`/điều kiện.
- Cần kết hợp kiểm tra kiểu bằng `instanceof` với việc phát đúng kiểu đầu ra.
- Muốn mở rộng phần tử thành nhiều giá trị mà không phải biểu diễn một `Stream` con cho từng đầu vào.
- Cần phiên bản primitive như `mapMultiToInt` để tránh boxing khi tạo `IntStream`.

Nếu điều kiện quá rối hoặc callback phát rất nhiều kết quả từ một phần tử, cân nhắc tách logic vào hàm riêng hoặc dùng `flatMap()` để giữ cấu trúc mã dễ hiểu.

## 5. Chú ý đến suy luận kiểu của Java

Khác với `map` trả về một giá trị `R` mà compiler có thể nhìn thấy trực tiếp, `mapMulti` nhận một callback được dùng để **đẩy giá trị ra**. Trong một số cách viết, đặc biệt khi nối ngay với `toList()`, Java có thể suy luận `R` thành `Object` thay vì kiểu mong muốn.

Đây là cách rõ ràng và ổn định:

```java
List<String> names = List.of("An", "", "Chi").stream()
        .<String>mapMulti((name, out) -> {
            if (!name.isBlank()) {
                out.accept(name);
            }
        })
        .toList();
// [An, Chi]
```

Biểu thức `.<String>mapMulti(...)` là **type witness**: yêu cầu kiểu phần tử đầu ra `R` là `String`. Nếu callback phát `Integer` thì trình biên dịch sẽ báo không tương thích, đúng như mong đợi.

Một hướng khác là viết lambda với kiểu tham số tường minh, ví dụ:

```java
Stream<Integer> stream = Stream.of(1, -1, 3)
        .mapMulti((Integer n, java.util.function.Consumer<Integer> out) -> {
            if (n > 0) {
                out.accept(n);
            }
        });
```

Đây là đoạn minh họa cần `import java.util.stream.Stream;`. Với `BiConsumer`, nếu khai báo kiểu tường minh cho một tham số lambda thì cũng phải khai báo cho tham số còn lại. Thông thường cách dùng `.<Integer>mapMulti(...)` ngắn và dễ đọc hơn.

## 6. Primitive specializations: tránh boxing khi có thể

Ngoài `Stream<T>.mapMulti(...)`, API Stream hỗ trợ tạo primitive stream:

| API gọi từ `Stream<T>` | Mapper nhận | Kết quả |
| --- | --- | --- |
| `mapMultiToInt` | `T` và `IntConsumer` | `IntStream` |
| `mapMultiToLong` | `T` và `LongConsumer` | `LongStream` |
| `mapMultiToDouble` | `T` và `DoubleConsumer` | `DoubleStream` |

Các primitive stream cũng có API liên quan. Chẳng hạn `IntStream.mapMulti(IntStream.IntMapMultiConsumer)` nhận `int` và `IntConsumer`, phát 0, 1 hoặc nhiều giá trị `int`.

Ví dụ:

```java
int[] values = java.util.stream.IntStream.of(2, -1, 4)
        .mapMulti((n, out) -> {
            if (n > 0) {
                out.accept(n);
                out.accept(n * 2);
            }
        })
        .toArray();
// [2, 4, 4, 8]
```

Đây là đoạn minh họa bên trong phương thức. Giá trị âm bị bỏ; số dương phát chính nó và gấp đôi nó. Phiên bản `IntStream.mapMulti` dùng mapper chuyên biệt, **không** dùng generic `BiConsumer<T,Consumer<R>>`.

Với các phép tổng hợp như `sum()`, `average()`, `max()`, `mapMultiToInt` và các kiểu primitive stream giúp tránh một phần chi phí boxing/unboxing so với `Stream<Integer>`.

## 7. Thứ tự kết quả, parallel stream và side effect

Nếu nguồn có encounter order (chẳng hạn `List.stream()`) và mỗi mapper phát kết quả lần lượt qua `out.accept`, kết quả được xem theo thứ tự logic: **thứ tự phần tử nguồn, rồi thứ tự phát kết quả của mỗi phần tử**.

```java
List<String> result = List.of("A", "B").parallelStream()
        .<String>mapMulti((value, out) -> {
            out.accept(value + "1");
            out.accept(value + "2");
        })
        .toList();
// [A1, A2, B1, B2]
```

Đây là đoạn minh họa cần `java.util.List`. `parallelStream` có thể gọi mapper trên các luồng và lịch thực thi khác nhau, nhưng `toList()` của ordered stream vẫn giữ encounter order. Điều đó **không** có nghĩa các lần mapper chạy theo thứ tự A rồi B trong thời gian thực.

Nguyên tắc cho callback:

- **Non-interfering:** không thay đổi nguồn stream đang được duyệt, ví dụ không gọi `list.add(...)` từ mapper trên chính list nguồn.
- **Stateless:** không dựa vào trạng thái chia sẻ có thể thay đổi giữa các lần callback, nhất là trong parallel stream.
- Không dùng `out.accept` từ một luồng nền sau khi mapper đã trả về; việc phát kết quả phải nằm trong vòng đời callback.
- Không dựa vào số lần chạy mapper để thực hiện hành động bắt buộc (ghi DB, gửi email, tăng bộ đếm nghiệp vụ). Các operation trong Stream có thể short-circuit hoặc tối ưu hóa việc duyệt.
- Nếu một mapper ném exception, terminal operation có thể kết thúc với lỗi. Stream không rollback các tác dụng phụ đã xảy ra trong những callback trước đó.

Nếu cần ghi các kết quả ra hệ thống ngoài, thường nên **biến đổi dữ liệu trước** rồi để lớp điều phối xử lý I/O và lỗi với chính sách rõ ràng, thay vì trộn I/O vào `mapMulti`.

## 8. Lưu ý về `null`, collection rỗng và lỗi dữ liệu

`mapMulti` cho phép bỏ một phần tử bằng cách **không gọi `accept`**. Đây thường là cách rõ ràng để loại `null` hoặc giá trị không hợp lệ:

```java
List<String> result = Stream.of("A", null, "B")
        .<String>mapMulti((s, out) -> {
            if (s != null) {
                out.accept(s.toLowerCase(java.util.Locale.ROOT));
            }
        })
        .toList();
// [a, b]
```

Đây là đoạn minh họa cần `import java.util.List;` và `import java.util.stream.Stream;`. Không dùng `List.of("A", null, "B")` vì `List.of` **không cho phép phần tử null**.

Về kỹ thuật, một `Stream` object có thể chứa `null` và một số terminal operation chấp nhận phần tử null; nhưng điều này phụ thuộc operation ở downstream. Ví dụ `findFirst` hoặc `findAny` có thể ném `NullPointerException` khi phần tử được chọn là null. Tốt nhất hãy quyết định chính sách với null từ sớm và thể hiện rõ trong mapper.

Nếu dữ liệu không hợp lệ cần được **báo lỗi**, đừng âm thầm loại nó bằng cách không gọi `accept`. Ví dụ xử lý đơn hàng sai số lượng có thể cần `IllegalArgumentException` hoặc một kiểu kết quả biểu diễn lỗi; việc “phát 0 kết quả” phù hợp khi đúng nghiệp vụ là **bỏ qua**.

## 9. Lỗi thường gặp

1. **Nhầm `mapMulti` với `map`:** callback của `mapMulti` không trả kết quả, mà gọi `downstream.accept`. Viết `return n * 2;` trong lambda `mapMulti` là sai; hãy gọi `out.accept(n * 2)`.
2. **Quên phát kết quả:** mapper không gọi `out.accept` sẽ xóa hoàn toàn phần tử nguồn đó khỏi kết quả, kể cả khi lambda tự tính ra giá trị nhưng không phát.
3. **Phát nhiều lần khi chỉ muốn một:** mỗi lần `accept` tạo thêm một phần tử. Cần bảo đảm điều kiện và số lần phát khớp yêu cầu.
4. **Suy luận kiểu thành `Object`:** nếu compiler báo `List<Object> cannot be converted to List<String>`, thử `.<String>mapMulti(...)`.
5. **Lưu hoặc truyền `downstream` ra ngoài:** không giữ reference để phát dữ liệu sau khi mapper trả về; hợp đồng chỉ cho phép phát trong lượt xử lý mapper.
6. **Dựa vào side effect trong mapper:** không dùng số lần callback hoặc lịch chạy song song làm hợp đồng nghiệp vụ; chọn terminal operation thích hợp.
7. **Lầm tưởng `mapMulti` luôn nhanh hơn `flatMap`:** không có bảo đảm chung. Hãy chọn biểu thức rõ ràng và dùng benchmark với dữ liệu thực nếu cần tối ưu.
8. **Không xem xét checked exception:** `BiConsumer` chuẩn không khai báo `throws IOException` hay checked exception khác. Nếu có I/O, xử lý có chủ đích tại adapter hoặc boundary; tránh giấu logic ghi file trong callback.
9. **Quên Java version:** `mapMulti` được thêm vào Java 16; mã Java 8–15 không có API này. Với các bản đó, `flatMap` hoặc `filter().map()` là lựa chọn thay thế.
10. **Không phân biệt phần tử input/output:** callback cho phép phát kiểu `R` khác `T`, vì vậy `mapMulti` không chỉ là `filter`; nó còn có thể biến đổi kiểu và mở rộng số lượng phần tử.

## 10. Khi nào nên dùng cách nào?

| Bài toán | Cách thường phù hợp |
| --- | --- |
| Mỗi `T` biến thành đúng một `R` | `map(f)` |
| Chỉ giữ các `T` thỏa điều kiện | `filter(predicate)` |
| Lọc rồi biến đổi đơn giản | `filter(predicate).map(f)` |
| Mỗi đầu vào phát 0, 1 hoặc vài kết quả theo điều kiện/vòng lặp | `mapMulti((item,out) -> ...)` |
| Mỗi đầu vào đã có hoặc tự nhiên tạo một `Stream<R>` | `flatMap(item -> streamOfResults)` |
| Mỗi đầu vào phát nhiều số nguyên và cần tổng hợp số học | `mapMultiToInt(...).sum()` |
| Cần phân tích nhiều tầng và tách rõ các bước con | Chọn hàm riêng hoặc `flatMap` để giữ tính dễ đọc |

## Tự kiểm tra

**Câu 1.** `Stream.of(1, 2, 3).<Integer>mapMulti((n, out) -> { if (n % 2 == 1) { out.accept(n); out.accept(-n); } }).toList()` trả về gì?

**Đáp án:** `[1, -1, 3, -3]`. Số chẵn `2` không phát phần tử nào, hai số lẻ mỗi số phát hai kết quả.

**Câu 2.** Khác biệt cốt lõi giữa `flatMap` và `mapMulti` là gì?

**Đáp án:** `flatMap` nhận hàm trả về **một stream cho mỗi phần tử**; `mapMulti` nhận mapper gọi **`Consumer.accept` 0 hoặc nhiều lần** trong chính lượt callback. Cả hai đều có thể tạo 0, 1 hoặc nhiều phần tử kết quả.

**Câu 3.** Nếu `parallelStream().<String>mapMulti(...).toList()` trên một `List`, kết quả có thể vẫn giữ thứ tự logic không?

**Đáp án:** Có. Với ordered stream, `toList` giữ encounter order, nhưng mapper có thể thực thi trên các luồng khác nhau và theo lịch không cố định.

## Ghi nhớ

- `mapMulti()` phát **0, 1 hoặc nhiều phần tử** bằng `out.accept(value)`.
- Không cần tạo `Stream` con cho mỗi phần tử như `flatMap()`; đây là lựa chọn hữu ích khi số đầu ra thường nhỏ hoặc phát bằng điều kiện/vòng lặp.
- Với generic `mapMulti`, có thể chỉ định kiểu bằng `.<R>mapMulti(...)` để tránh suy luận thành `Object`.
- Có `mapMultiToInt`, `mapMultiToLong`, `mapMultiToDouble` và các biến thể trên primitive streams.
- Giữ mapper không can thiệp nguồn, không phụ thuộc trạng thái chia sẻ; không giữ `downstream` để gọi ngoài vòng đời mapper.
