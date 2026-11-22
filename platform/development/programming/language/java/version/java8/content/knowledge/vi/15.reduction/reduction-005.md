# Reduction bất biến và mutable reduction trong Java Stream

## 1. Mục tiêu và phạm vi

Reduction (phép thu gọn/tổng hợp) kết hợp các phần tử của Stream để tạo một kết quả, ví dụ tổng số, giá trị lớn nhất, chuỗi ghép, danh sách hoặc bảng thống kê. Hai cách tiếp cận chính còn được dùng trong Java hiện đại là:

- **Reduction theo giá trị (thường gọi là immutable reduction):** dùng `reduce(...)`. Mỗi lần kết hợp tạo ra giá trị tổng hợp mới về mặt logic; hàm tích lũy không sửa đối tượng tích lũy được chia sẻ.
- **Mutable reduction:** dùng `collect(...)`. Kết quả trung gian là một **container** có thể thay đổi, chẳng hạn `ArrayList`, `StringBuilder` hoặc `Map`. Accumulator đưa dữ liệu vào container, còn combiner ghép các container trung gian khi cần.

Sau bài học, bạn có thể đọc chính xác các overload `reduce`/`collect`, chọn đúng API, giải thích `identity`, `accumulator`, `combiner` và các quy tắc để xử lý song song an toàn. Đây là các API xuất hiện từ Java 8 và vẫn có trong JDK hiện hành. Các chương trình hoàn chỉnh bên dưới biên dịch bằng **Java 8 trở lên**, bao gồm JDK 17/21.

## 2. Một ví dụ cho thấy hai kiểu reduction

Cho dãy số `[2, 3, 4]`.

**Thu gọn theo giá trị:** tính tổng có thể biểu diễn là:

```text
identity = 0
0 + 2  → 2
2 + 3  → 5
5 + 4  → 9
Kết quả: 9
```

Mỗi trạng thái trung gian biểu diễn một giá trị số; không cần biến `sum` dùng chung để từng thread tăng lên.

**Thu gọn bằng container có thể thay đổi:** chuyển các số chẵn thành danh sách:

```text
supplier    → tạo ArrayList mới: []
accumulator → thêm 2: [2]
accumulator → xét 3 nhưng không thêm (nếu đã lọc trước)
accumulator → thêm 4: [2, 4]
Kết quả: [2, 4]
```

Trong Stream thực tế, nên lọc trước bằng `filter` rồi `collect`. Khác biệt nằm ở **cách tích lũy**, không nhất thiết ở khả năng chỉnh sửa của **kết quả cuối**: một phép mutable reduction có thể có bước `finisher` tạo kết quả bất biến.

Cả `reduce` lẫn `collect` đều là **terminal operations**. Chúng khởi chạy các thao tác trung gian lazy trước đó và tiêu thụ Stream; không tái sử dụng chính Stream đã chạy terminal operation.

## 3. Immutable reduction với `Stream.reduce`

Ba dạng tổng quát còn đang áp dụng:

```java
// 1. Không truyền identity; Stream có thể rỗng.
Optional<T> reduce(BinaryOperator<T> accumulator);

// 2. Có identity cùng kiểu với phần tử.
T reduce(T identity, BinaryOperator<T> accumulator);

// 3. Kết quả tổng hợp kiểu U có thể khác kiểu phần tử T.
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
```

Các khai báo trên là **chữ ký API minh họa** (dùng generic `T` và `U`), không phải chương trình Java độc lập.

`BinaryOperator<T>` nhận hai đối số `T` và trả về `T`; `BiFunction<U,T,U>` nhận trạng thái tổng hợp `U` và phần tử `T` rồi trả về trạng thái tổng hợp `U`. Lambda trong `reduce` nên **stateless**, **non-interfering** và không thay đổi đối tượng identity/partial result.

### 3.1. Hai dạng `reduce` cơ bản và Stream rỗng

Lưu tệp `ReduceBasicDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class ReduceBasicDemo {
    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(2, 3, 4, 5);

        int sum = values.stream().reduce(0, Integer::sum);
        int product = values.stream().reduce(1, (a, b) -> a * b);
        Optional<Integer> maximum = values.stream().reduce(Integer::max);

        int emptySum = Stream.<Integer>empty().reduce(0, Integer::sum);
        Optional<Integer> emptyMax =
                Stream.<Integer>empty().reduce(Integer::max);

        System.out.println("sum = " + sum);
        System.out.println("product = " + product);
        System.out.println("maximum = " + maximum);
        System.out.println("emptySum = " + emptySum);
        System.out.println("emptyMax = " + emptyMax);
    }
}
```

Chạy:

```bash
javac ReduceBasicDemo.java
java ReduceBasicDemo
```

Stdout chính xác:

```text
sum = 14
product = 120
maximum = Optional[5]
emptySum = 0
emptyMax = Optional.empty
```

**Vì sao lại có `Optional`?** Nếu không cấp identity, một Stream rỗng không có phần tử nào để thu gọn. API trả về `Optional.empty()` thay vì giả định giá trị mặc định cho mọi loại phép toán. Hãy xử lý `Optional` bằng `orElse`, `orElseGet` hoặc logic khác phù hợp, không gọi `get()` khi chưa xác định có giá trị.

**Identity** là phần tử trung hòa của phép kết hợp: với cộng là `0`, với nhân là `1`. Không dùng `0` cho phép nhân vì nó sẽ làm mọi kết quả thành `0`. Với overload có identity, Stream rỗng trả về identity; với overload không identity, Stream rỗng trả `Optional.empty()`.

### 3.2. Overload ba đối số: phần tử `T`, kết quả `U`

Ví dụ Stream chứa `String` nhưng muốn tính tổng độ dài dạng `Integer`. Lưu `ReduceTypesDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class ReduceTypesDemo {
    public static void main(String[] args) {
        List<String> words = Arrays.asList("Java", "Stream", "API");

        int lengthByReduce = words.parallelStream().reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum);

        int lengthByPrimitive = words.parallelStream()
                .mapToInt(String::length)
                .sum();

        System.out.println("reduce = " + lengthByReduce);
        System.out.println("mapToInt = " + lengthByPrimitive);
    }
}
```

```bash
javac ReduceTypesDemo.java
java ReduceTypesDemo
```

```text
reduce = 13
mapToInt = 13
```

Ở đây `identity` = `0`, `accumulator` cộng độ dài của một `String` vào tổng kiểu `Integer`, còn `combiner` cộng hai tổng bộ phận. Trong parallel stream, Java có thể chia nguồn thành nhiều phần để tính tổng bộ phận và dùng `combiner` ghép lại. Đối với tổng độ dài như trên, `mapToInt(String::length).sum()` thường rõ ràng hơn và tránh boxing trung gian; dùng nó khi bài toán chỉ là tổng số nguyên.

## 4. Ba hợp đồng phải đúng: identity, associativity, compatibility

### 4.1. Associativity: kết hợp theo nhóm nào cũng đúng

Hàm kết hợp phải **có tính kết hợp** (associative):

```text
(a ⊕ b) ⊕ c  =  a ⊕ (b ⊕ c)
```

Phép cộng số nguyên (trong ngữ nghĩa số nguyên Java, kể cả overflow theo phép toán `+`) có tính kết hợp; phép trừ thì không: `(10 - 5) - 2 = 3` nhưng `10 - (5 - 2) = 7`. Khi chạy parallel, Stream có quyền chia và ghép các phần theo nhóm khác nhau; dùng phép toán không associative sẽ làm kết quả không còn đáng tin. Với số thực `double`, phép cộng trong máy tính **không hoàn toàn associative** do làm tròn, vì vậy các thứ tự nhóm khác nhau có thể tạo sai số khác nhau.

### 4.2. Identity là phần tử trung hòa

Với toán tử `op`, cần `op(identity, x) = x` (đồng thời identity phù hợp với cách ghép các phần). Ví dụ `reduce(0, Integer::sum)` hợp lệ; `reduce(10, Integer::sum)` không phải phép tính tổng thông thường, vì mỗi nhánh parallel có thể áp dụng identity riêng rồi kết hợp, làm `10` được cộng nhiều lần. Nếu nghiệp vụ muốn “tổng + 10”, hãy tính reduction với identity `0` rồi cộng `10` bên ngoài.

Đừng nhầm identity với “giá trị khởi tạo tùy ý”. Trong reduction song song, nó còn là giá trị trung hòa cho các kết quả con.

### 4.3. Compatibility của overload ba đối số

Với `reduce(U identity, accumulator, combiner)`, `combiner` phải kết hợp được các partial result do `accumulator` tạo. Về mặt hợp đồng API, với mọi `u` và phần tử `t`:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

Dấu `==` ở dòng này biểu diễn **tương đương giá trị** (xét bằng `equals` theo hợp đồng), không yêu cầu hai object phải cùng tham chiếu Java. Ngoài ra `combiner(identity, u)` phải tương đương `u`; `combiner` cần associative. Ví dụ `(total, word) -> total + word.length()` hoàn toàn tương thích với `Integer::sum`.

### 4.4. Stateless và non-interfering

- Lambda không nên đọc/ghi **trạng thái mutable bên ngoài** đang được nhiều lần gọi cập nhật.
- Không thay đổi collection nguồn trong khi Stream tiêu thụ nó, trừ trường hợp API nguồn concurrency có quy định riêng.
- Với `reduce`, không mutate partial result rồi trả về chính object đó để giả lập `collect`. Hợp đồng phù hợp là tạo ra giá trị tổng hợp, còn việc mutate container thuộc `collect`.
- Không dựa vào thứ tự thực thi, thread xử lý từng phần tử hay số lần một lambda được gọi trong parallel stream.

Các quy tắc này giữ cho phép giảm có cùng ý nghĩa dù triển khai chạy tuần tự hay song song.

## 5. Mutable reduction với `Stream.collect`

Hai dạng thường dùng:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);

<R, A> R collect(Collector<? super T, A, R> collector);
```

Đây là **chữ ký API minh họa**. Trong dạng ba hàm:

1. **Supplier:** tạo container kết quả **mới** khi được gọi, ví dụ `ArrayList::new`. Không trả cùng một instance dùng chung cho mọi nhánh.
2. **Accumulator:** thêm một phần tử vào container, ví dụ `list.add(value)`; thường có side effect **lên container của chính phép collect**.
3. **Combiner:** trộn dữ liệu của hai container kết quả trung gian, ví dụ `left.addAll(right)`. Hàm không được làm mất phần tử hoặc ghép sai ngữ nghĩa.

Khác với `reduce`, accumulator của `collect` **được phép mutate container** mà nó nhận. Điều này không cho phép mutate tuỳ tiện dữ liệu nguồn hay biến chia sẻ bên ngoài.

### 5.1. Các collector có sẵn — ưu tiên trong ứng dụng

Lưu `CollectorsDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;

public class CollectorsDemo {
    public static void main(String[] args) {
        List<String> words = Arrays.asList("java", "stream", "reduce");

        List<String> upper = words.parallelStream()
                .map(String::toUpperCase)
                .collect(Collectors.toList());

        String joined = words.stream()
                .collect(Collectors.joining(" / "));

        Map<String, Long> counts =
                Arrays.asList("java", "stream", "java").stream()
                        .collect(Collectors.groupingBy(
                                Function.identity(),
                                TreeMap::new,
                                Collectors.counting()));

        System.out.println("upper = " + upper);
        System.out.println("joined = " + joined);
        System.out.println("counts = " + counts);
    }
}
```

```bash
javac CollectorsDemo.java
java CollectorsDemo
```

```text
upper = [JAVA, STREAM, REDUCE]
joined = java / stream / reduce
counts = {java=2, stream=1}
```

- `toList()` tập hợp phần tử thành danh sách. Với nguồn có encounter order và collector có thứ tự, trình tự phần tử được giữ, kể cả dùng `parallelStream()`.
- `joining(" / ")` ghép chuỗi hiệu quả hơn cách lặp lại `String` concatenation trong `reduce` ở bài toán nối nhiều chuỗi.
- `groupingBy(Function.identity(), TreeMap::new, counting())` nhóm theo chính giá trị chuỗi và đếm số lần xuất hiện. `TreeMap` giúp thứ tự hiển thị theo key rõ ràng, nên ví dụ có stdout xác định.

**Lưu ý hợp đồng:** `Collectors.toList()` không cam kết lớp triển khai cụ thể, khả năng chỉnh sửa hay tính thread-safe của danh sách kết quả. Nếu chắc chắn cần `ArrayList` có thể chỉnh sửa, dùng `Collectors.toCollection(ArrayList::new)`. Nếu cần danh sách không thể sửa: `Collectors.toUnmodifiableList()` có từ Java 10 (không nhận phần tử null), còn `Stream.toList()` có từ Java 16 và trả danh sách không thể chỉnh sửa. Đây là các API hiện hành, nhưng **không** có trong Java 8; các ví dụ chạy được ở đây dùng API Java 8.

### 5.2. Tự định nghĩa supplier, accumulator và combiner

Lưu `ManualCollectDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class ManualCollectDemo {
    public static void main(String[] args) {
        List<String> letters = Stream.of("A", "B", "C")
                .parallel()
                .collect(
                        ArrayList::new,
                        (list, item) -> list.add(item),
                        (left, right) -> left.addAll(right));

        System.out.println("letters = " + letters);
    }
}
```

```bash
javac ManualCollectDemo.java
java ManualCollectDemo
```

```text
letters = [A, B, C]
```

Ví dụ có **ordered source** là `Stream.of("A", "B", "C")`. Dù thực thi song song, phép `collect` đúng hợp đồng duy trì encounter order cho kết quả này. `supplier` có thể được gọi nhiều lần tạo các danh sách con riêng. `accumulator` thêm phần tử vào từng danh sách. `combiner` ghép các danh sách con thành kết quả. `ArrayList` bản thân không thread-safe; ví dụ vẫn an toàn vì phép thu gom tổ chức các partial container thay vì cho tất cả thread gọi `add` trên cùng một danh sách chia sẻ.

Trong ứng dụng, nếu chỉ cần danh sách, hãy ưu tiên:

```java
List<String> letters = Stream.of("A", "B", "C")
        .parallel()
        .collect(java.util.stream.Collectors.toList());
```

Dạng ba hàm hữu ích khi bạn thật sự cần cấu trúc kết quả và quy tắc ghép riêng.

## 6. Vì sao mutable reduction không nên dùng `reduce`?

Đây là **mẫu sai để nhận diện, không chạy trong ứng dụng**:

```java
// SAI: mutate cùng một identity/partial result trong reduce.
StringBuilder broken = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                (builder, item) -> builder.append(item),
                (left, right) -> left.append(right));
```

*Đoạn mã trên là snippet minh họa và cần import `java.util.stream.Stream` nếu đặt vào chương trình.* Sai ở chỗ `StringBuilder` là object có thể thay đổi: các nhánh reduction có thể dùng cùng identity, accumulator mutate object đó, rồi combiner tiếp tục mutate và ghép nội dung. Kết quả có thể nhân đôi, sai thứ tự hoặc xảy ra data race. Chạy tuần tự có thể tình cờ cho kết quả mong đợi nhưng vẫn không đáp ứng hợp đồng để chạy parallel đúng.

Cách **đúng** với mutable container là `collect`. Lưu `StringBuilderCollectDemo.java`:

```java
import java.util.stream.Stream;

public class StringBuilderCollectDemo {
    public static void main(String[] args) {
        String joined = Stream.of("A", "B", "C")
                .parallel()
                .collect(
                        StringBuilder::new,
                        (builder, item) -> builder.append(item),
                        (left, right) -> left.append(right))
                .toString();

        System.out.println("joined = " + joined);
    }
}
```

```bash
javac StringBuilderCollectDemo.java
java StringBuilderCollectDemo
```

```text
joined = ABC
```

Mỗi phần kết quả tích lũy vào builder của chính nó và được ghép theo encounter order khi cần. Trong công việc ghép chuỗi đơn thuần, `Stream.of("A", "B", "C").collect(Collectors.joining())` còn ngắn gọn hơn.

**Không giải quyết vấn đề bằng cách đổi từ `StringBuilder` sang `StringBuffer` hoặc `Collections.synchronizedList(...)` trong `reduce`.** Dù container có đồng bộ, việc mutate identity và kết hợp các partial result vẫn vi phạm mô hình reduction; đồng bộ cũng có thể gây tranh chấp và mất lợi thế song song.

## 7. Custom `Collector` và ba kiểu tham số `T`, `A`, `R`

Nếu collector có sẵn không diễn đạt được mục tiêu, Java cung cấp:

```java
Collector<T, A, R>
```

- `T`: kiểu phần tử trong Stream.
- `A`: kiểu **container trung gian** có thể mutate.
- `R`: kiểu **kết quả cuối cùng** sau bước `finisher`; có thể khác `A`.

Collector thông thường gồm `supplier`, `accumulator`, `combiner`, `finisher` và tập `characteristics`. Ví dụ `Collector.of(...)` dùng một `StringJoiner` mutable để tạo kết quả cuối là `String` immutable.

Lưu `CustomCollectorDemo.java`:

```java
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CustomCollectorDemo {
    public static void main(String[] args) {
        Collector<String, StringJoiner, String> joiner =
                Collector.of(
                        () -> new StringJoiner(", "),
                        (parts, value) -> parts.add(value),
                        (left, right) -> left.merge(right),
                        StringJoiner::toString);

        String result = Stream.of("An", "Binh", "Chi")
                .parallel()
                .collect(joiner);

        System.out.println(result);
    }
}
```

```bash
javac CustomCollectorDemo.java
java CustomCollectorDemo
```

```text
An, Binh, Chi
```

Trong ví dụ, `StringJoiner` (kiểu `A`) được cập nhật khi tích lũy, sau cùng `toString` tạo `String` (kiểu `R`). Điều này làm rõ: **mutable reduction nói về cách xây dựng kết quả, không bắt buộc kết quả cuối phải mutable**. Với bài toán này, `Collectors.joining(", ")` vẫn là lựa chọn đơn giản và dễ bảo trì hơn custom collector.

Ba `Collector.Characteristics` thường thấy:

| Đặc tính | Ý nghĩa |
| --- | --- |
| `CONCURRENT` | Cho phép gọi accumulator đồng thời trên cùng result container khi điều kiện thực thi phù hợp |
| `UNORDERED` | Collector không cam kết giữ encounter order |
| `IDENTITY_FINISH` | Finisher là identity và có thể được bỏ qua |

Đừng tự gắn `CONCURRENT` chỉ vì kết quả chứa một `ConcurrentHashMap`: accumulator, combiner và hợp đồng Collector vẫn phải thực sự an toàn. Một phép **concurrent reduction** được Stream sử dụng khi Stream là parallel, Collector có `CONCURRENT` và Stream unordered hoặc Collector có `UNORDERED`. Nếu dữ liệu cần đúng encounter order, không được tự bỏ ràng buộc thứ tự để lấy hiệu năng.

## 8. So sánh nhanh cách viết cho cùng bài toán

| Tiêu chí | `reduce` (theo giá trị) | `collect` (mutable reduction) |
| --- | --- | --- |
| Đầu ra tiêu biểu | `Integer`, `Long`, `Optional<T>`, giá trị tổng hợp mới | `List`, `Map`, builder, kết quả do `Collector` tạo |
| Cách cập nhật | Hàm kết hợp **trả giá trị kết quả**, tránh mutate partial result | Accumulator **mutate container do supplier tạo** |
| Identity / khởi tạo | Identity trung hòa phép kết hợp | Supplier tạo container mới theo nhu cầu |
| Nối partial results | BinaryOperator trả về giá trị đã ghép | Combiner ghép nội dung container (dạng `collect` ba hàm trả `void`) |
| Parallel | Cần associative, stateless, non-interfering và identity đúng | Cần supplier/accumulator/combiner đúng, độc lập kết quả con và tính tương đương khi ghép |
| API thường nên chọn | `reduce`, `sum`, `max`, `min`, `count` | `collect(Collectors.toList())`, `toMap`, `groupingBy`, `joining` |

**Quy tắc chọn thực tế:**

- Tính tổng số nguyên: `mapToInt(...).sum()` thường rõ hơn `reduce(0, Integer::sum)`.
- Tìm min/max: ưu tiên `min`/`max` hoặc `reduce(BinaryOperator)` khi logic kết hợp riêng, nhớ xử lý `Optional`.
- Thu phần tử thành danh sách: dùng `collect(Collectors.toList())` hoặc collector phù hợp, không dùng `forEach(list::add)` với danh sách chia sẻ.
- Gom nhóm, đếm theo khóa, tạo map: dùng `groupingBy`, `counting`, `toMap` và collector tích hợp.
- Ghép chuỗi: dùng `Collectors.joining`, không lặp lại `String` concatenation để tạo chuỗi dài trong `reduce`.
- Gộp đối tượng nghiệp vụ **bất biến**: `reduce` phù hợp nếu phép kết hợp associative và có identity đúng; khi mỗi bước phải copy một tập dữ liệu rất lớn thì cân nhắc hiệu năng và có thể dùng `collect`.

## 9. Parallel stream: tại sao phải thận trọng?

Ví dụ **không an toàn**:

```java
// SAI: ArrayList dùng chung bị nhiều thread mutate.
List<Integer> shared = new ArrayList<>();
numbers.parallelStream().forEach(shared::add);
```

*Đây là snippet lỗi (cần khai báo `numbers` và imports), không phải ví dụ nên chạy.* `ArrayList` không có cơ chế đồng bộ cho các lần `add` concurrent. Kết quả có thể mất phần tử hoặc gây lỗi. Phương án phù hợp là:

```java
List<Integer> safe = numbers.parallelStream()
        .collect(java.util.stream.Collectors.toList());
```

Lúc này thư viện quản lý phép gom và kết hợp các kết quả trung gian. Nếu cần cụ thể một danh sách mutable, dùng `Collectors.toCollection(ArrayList::new)`.

Ngay cả với collector đúng, **parallel không mặc nhiên nhanh hơn**. Chi phí chia Stream, tạo container, ghép kết quả và đồng bộ (nếu có) có thể lớn hơn lợi ích. Với `groupingBy`, việc ghép nhiều Map có thể tốn kém; `groupingByConcurrent` có thể phù hợp khi yêu cầu thứ tự cho mỗi nhóm không quan trọng, nhưng cần cân nhắc hợp đồng thứ tự và hiệu năng thực tế. Kiểm tra correctness trước, benchmark theo dữ liệu và môi trường thật sau.

Chú ý ba dạng rủi ro riêng biệt:

1. **Shared mutable state:** ghi vào biến/object nằm ngoài pipeline khiến nhiều nhánh can thiệp lẫn nhau.
2. **Sai đại số:** identity không trung hòa, combiner không associative hoặc không tương thích accumulator.
3. **Đổi ngữ nghĩa thứ tự:** sử dụng collector unordered/concurrent khi nghiệp vụ thực sự yêu cầu thứ tự xuất hiện.

Các lỗi này có thể không lộ ra khi chỉ thử Stream tuần tự với vài phần tử.

## 10. Edge cases: dữ liệu rỗng, null, lỗi và tài nguyên

**Stream rỗng:** `reduce(identity, op)` trả identity; `reduce(op)` trả `Optional.empty()`. `collect(toList())` cho danh sách rỗng. Một custom collector cũng phải có hành vi hợp lệ khi supplier tạo container nhưng không có phần tử để tích lũy.

**Giá trị `null`:** đừng giả định mọi collector đều nhận null. Ví dụ `Collectors.toUnmodifiableList()` từ Java 10 không cho null; `Stream.toList()` từ Java 16 cho phép null trong kết quả nhưng trả danh sách không thể sửa. Với `reduce(BinaryOperator)`, trả ra null có thể khiến API ném `NullPointerException`; thiết kế hàm kết hợp không tạo null khi điều đó vi phạm hợp đồng.

**Overflow và độ chính xác:** phép cộng `int` có thể tràn; sử dụng `long`, `BigInteger` hoặc phép toán kiểm tra overflow tùy bài toán. Tổng `double` song song có thể không bằng bit tuyệt đối với tổng tuần tự do thứ tự cộng thay đổi.

**Ngoại lệ:** nếu accumulator/combiner ném exception, phép tổng hợp có thể dừng và không trả kết quả đầy đủ. Không coi `collect` là transaction hay cơ chế rollback cho hành động ra ngoài (I/O, database). Không nuốt lỗi để tạo ra số liệu “thành công” giả.

**Stream vô hạn:** `reduce` và `collect` thông thường cần thấy hết nguồn; nếu không có bước giới hạn thích hợp, phép tính có thể không kết thúc. Ví dụ `Stream.iterate(0, n -> n + 1).limit(100).reduce(0, Integer::sum)` có giới hạn rõ ràng.

**Tài nguyên:** nếu nguồn Stream giữ tài nguyên (như `Files.lines(...)`), hãy bọc `try-with-resources`. Terminal operation không tự thay thế trách nhiệm đóng tài nguyên của Stream.

## 11. Bài tập thực hành kèm lời giải

**Bài 1:** Tính tổng `[3, 4, 5, 6]` bằng `reduce`, sau đó tạo danh sách bình phương của các số chẵn bằng `collect`. Kết quả phải hoạt động khi chuyển sang `parallelStream()`.

**Bài 2:** Giải thích tại sao `reduce(10, Integer::sum)` không phải cách đúng để “tính tổng rồi cộng thêm 10” khi chạy parallel.

**Bài 3:** Với Stream các chuỗi `["cat", "blue", "sun"]`, tính tổng độ dài bằng overload `reduce(identity, accumulator, combiner)`. Chỉ rõ kiểu `T` và `U`.

Chương trình đáp án hoàn chỉnh `ReductionExercise.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class ReductionExercise {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(3, 4, 5, 6);

        int sum = numbers.parallelStream().reduce(0, Integer::sum);
        List<Integer> squares = numbers.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .collect(Collectors.toList());

        List<String> words = Arrays.asList("cat", "blue", "sun");
        int totalLength = words.parallelStream().reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum);

        System.out.println("sum = " + sum);
        System.out.println("squares = " + squares);
        System.out.println("length = " + totalLength);
        System.out.println("sumPlus10 = " + (sum + 10));
    }
}
```

```bash
javac ReductionExercise.java
java ReductionExercise
```

```text
sum = 18
squares = [16, 36]
length = 10
sumPlus10 = 28
```

Lời giải bài 2: vì `10` không phải identity của phép cộng, nhiều partial result có thể bị khởi tạo thêm `10`. Cách đúng là `reduce(0, Integer::sum) + 10`. Lời giải bài 3: `T = String` và `U = Integer`; accumulator cộng độ dài của từng String, combiner `Integer::sum` ghép các tổng con.

## 12. Checklist khi review code

- Bài toán đang tính **một giá trị** hay đang xây dựng **một container**? Tôi đã chọn `reduce` hay `collect` phù hợp chưa?
- Identity có thật sự trung hòa? Accumulator/combiner có associative và tương thích không?
- Tôi có mutate identity/partial result trong `reduce` hay vô tình chia sẻ container giữa các thread không?
- Supplier của `collect` có tạo đối tượng mới mỗi lần được gọi không?
- Collector có cần giữ encounter order? Có nên dùng `CONCURRENT`/`UNORDERED` không?
- Có thể chọn collector chuẩn thay cho tự viết combiner không?
- Tôi đã xử lý Stream rỗng, dữ liệu null, overflow, lỗi và tài nguyên cần đóng chưa?
- Phần mềm có thực sự cần parallel và đã được kiểm thử/đo hiệu năng với dữ liệu đủ lớn chưa?

## 13. Tài liệu API hiện hành

- Oracle Java SE 26, `Stream.reduce` và `Stream.collect`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- Oracle Java SE 26, `java.util.stream` — Reduction operations, Mutable reduction, Associativity, Non-interference: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- Oracle Java SE 26, `Collectors`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html
- Oracle Java SE 26, `Collector.Characteristics`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html

**Ghi nhớ:** `reduce` diễn đạt phép kết hợp theo **giá trị** và đòi hỏi identity/associativity đúng; `collect` cho phép mutate **container trung gian** do chính cơ chế thu gom quản lý. Hai cơ chế đều đang được sử dụng; tính đúng đắn của parallel reduction dựa trên hợp đồng của hàm kết hợp, không dựa vào thứ tự chạy hoặc đồng bộ một biến dùng chung.