# Kiểm chứng phép rút gọn trên nguồn rỗng và pipeline song song

## 1. Mục tiêu bài học

Trong **Java Stream API**, phép rút gọn (*reduction*) gộp nhiều phần tử thành một kết quả: tổng tiền, tích số lượng, điểm lớn nhất, chuỗi ghép hoặc một giá trị thống kê. Phương thức `reduce` là một **terminal operation**, kết thúc pipeline có thể gồm các bước lazy như `filter` và `map`.

Viết được một phép `reduce` cho stream tuần tự **chưa đủ** để khẳng định nó đúng. Có hai trường hợp dễ lộ lỗi:

- **Nguồn rỗng:** kết quả phải được xác định hợp lý khi không có phần tử nào, kể cả khi dữ liệu bị `filter` loại hết.
- **Pipeline song song:** Java có thể chia nguồn thành nhiều phần, rút gọn từng phần rồi dùng `combiner` ghép các kết quả. Một phép tính phụ thuộc thứ tự đặt ngoặc hoặc dùng `identity` sai có thể cho kết quả khác.

Bài thuộc chương **Phép rút gọn với reduce** của module **`JAVA_STREAM_API`**. Đây là kiến thức nền để học `collect`, grouping, collector tùy chỉnh, `Spliterator` và xử lý song song, đồng thời nhận diện giới hạn về trạng thái, tài nguyên và hiệu năng.

Sau bài học, bạn có thể:

1. Phân biệt ba overload của `Stream.reduce` và các dạng `reduce` của primitive stream.
2. Kiểm tra kết quả trên stream rỗng và stream còn một phần tử.
3. Xác định **identity** (phần tử đơn vị), tính **kết hợp** (*associativity*) và điều kiện tương thích của `accumulator` với `combiner`.
4. Giải thích vì sao tổng hoặc phép max đúng khi chạy song song, còn phép trừ hay phép cộng với identity sai thì không.
5. Viết kiểm chứng có thể chạy được với Java 8, so sánh kết quả tuần tự và song song mà không dựa vào thứ tự log hoặc số lần gọi lambda.

## 2. Cơ chế rút gọn: từ dãy phần tử đến một giá trị

Xét bài toán cộng các số nguyên:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(2, 4, 6, 8);

int tong = so.stream()
    .reduce(0, Integer::sum);

System.out.println(tong); // 20
```

Trong pipeline trên:

- `0` là **identity**, giá trị bắt đầu và phần tử đơn vị của phép cộng.
- `Integer::sum` là **accumulator**, cộng kết quả hiện tại với phần tử tiếp theo.
- `reduce` là terminal operation, trả về `int` sau khi hoàn thành phép gộp.

Trên stream tuần tự, có thể hình dung phép tính:

```text
seed = 0
0 + 2 = 2
2 + 4 = 6
6 + 6 = 12
12 + 8 = 20
```

Nhưng với stream song song, triển khai có thể làm tương đương:

```text
          [2, 4, 6, 8]
            /       \
         [2, 4]    [6, 8]
           │          │
          6          14
            \        /
             6 + 14
                │
               20
```

**Không có bảo đảm JVM luôn chọn cách chia cụ thể như sơ đồ.** Điều cần bảo đảm là khi phép toán đáp ứng hợp đồng của `reduce`, cách nhóm các phần tử không làm thay đổi kết quả logic.

## 3. Ba overload của `Stream.reduce`

### 3.1. Không cung cấp identity: trả về `Optional<T>`

Chữ ký rút gọn:

```java
Optional<T> reduce(BinaryOperator<T> accumulator);
```

Ví dụ:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> tong = Stream.of(2, 4, 6)
    .reduce(Integer::sum);

System.out.println(tong.orElse(-1)); // 12
```

Phép toán dùng phần tử đầu tiên làm giá trị tích lũy ban đầu. Nếu stream **rỗng**, không có phần tử để bắt đầu, nên kết quả là `Optional.empty()`.

### 3.2. Có identity cùng kiểu phần tử: trả về `T`

Chữ ký:

```java
T reduce(T identity, BinaryOperator<T> accumulator);
```

Ví dụ:

```java
int tong = Stream.of(2, 4, 6)
    .reduce(0, Integer::sum);

System.out.println(tong); // 12
```

Khi không có phần tử, phép rút gọn trả về **identity**. Identity phải phù hợp với phép toán và khi xử lý song song phải là phần tử đơn vị thực sự.

### 3.3. Có identity với kiểu kết quả khác: trả về `U`

Chữ ký:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Ở đây:

- `T` là kiểu phần tử của stream.
- `U` là kiểu kết quả tích lũy, có thể khác `T`.
- `accumulator` gộp một kết quả `U` với một phần tử `T` để tạo `U` mới.
- `combiner` gộp **hai** kết quả tích lũy `U`, đặc biệt quan trọng khi xử lý song song.

Ví dụ tổng số ký tự của nhiều chuỗi:

```java
import java.util.Arrays;
import java.util.List;

List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tongKyTu = ten.stream()
    .reduce(
        0,
        (soKyTu, chuoi) -> soKyTu + chuoi.length(),
        Integer::sum
    );

System.out.println(tongKyTu); // 12
```

Nguồn có kiểu `Stream<String>` nhưng kết quả là `Integer`. Trong ví dụ này, các kết quả tích lũy là số ký tự, nên combiner cộng chúng lại.

Với nhu cầu chỉ tính tổng độ dài, cách chuyên biệt `ten.stream().mapToInt(String::length).sum()` thường dễ đọc hơn. Overload ba tham số có ích để hiểu hợp đồng khi kiểu đầu vào và kiểu tích lũy khác nhau.

### 3.4. `reduce` trên primitive stream

`IntStream`, `LongStream` và `DoubleStream` có hai dạng thông dụng:

```java
// IntStream
int reduce(int identity, IntBinaryOperator op);
OptionalInt reduce(IntBinaryOperator op);

// Tương tự: LongStream → long / OptionalLong
//           DoubleStream → double / OptionalDouble
```

Ví dụ:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

int tongCoIdentity = IntStream.of(2, 4, 6)
    .reduce(0, Integer::sum);

OptionalInt tongKhongIdentity = IntStream.of(2, 4, 6)
    .reduce(Integer::sum);

System.out.println(tongCoIdentity);              // 12
System.out.println(tongKhongIdentity.orElse(-1)); // 12
```

Dùng primitive stream tránh boxing `int` thành `Integer` khi tính toán số học thông thường. Nó không làm thay đổi các yêu cầu đại số của phép rút gọn.

## 4. Kiểm chứng trên nguồn rỗng

**Nguồn rỗng là ca kiểm tra bắt buộc.** Nguồn có thể vốn rỗng hoặc trở nên rỗng sau `filter`:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> khongIdentity = Stream.<Integer>empty()
    .reduce(Integer::sum);

int coIdentity = Stream.<Integer>empty()
    .reduce(0, Integer::sum);

System.out.println(khongIdentity.isPresent()); // false
System.out.println(coIdentity);                 // 0
```

Bảng kết quả:

| Pipeline trên nguồn rỗng | Kiểu trả về | Kết quả |
| --- | --- | --- |
| `Stream.<Integer>empty().reduce(Integer::sum)` | `Optional<Integer>` | `Optional.empty()` |
| `Stream.<Integer>empty().reduce(0, Integer::sum)` | `Integer` | `0` |
| `IntStream.empty().reduce(Integer::sum)` | `OptionalInt` | `OptionalInt.empty()` |
| `IntStream.empty().reduce(0, Integer::sum)` | `int` | `0` |
| `LongStream.empty().reduce(1L, (a, b) -> a * b)` | `long` | `1L` |
| `Stream.<String>empty().reduce("", String::concat)` | `String` | `""` |
| `Stream.<String>empty().reduce(0, (n, s) -> n + s.length(), Integer::sum)` | `Integer` | `0` |

**Không được tự động hiểu kết quả `0` là "có dữ liệu".** Với phép cộng, `0` là phần tử đơn vị hợp lệ, nên không đủ thông tin để phân biệt rỗng với tổng thật sự bằng 0.

Nếu nghiệp vụ cần phân biệt hai trạng thái, dùng overload trả `Optional` hoặc kiểm tra dữ liệu theo cách phù hợp:

```java
Optional<Integer> tong = Stream.<Integer>empty()
    .reduce(Integer::sum);

if (tong.isPresent()) {
    System.out.println("Có dữ liệu, tổng = " + tong.get());
} else {
    System.out.println("Chưa có dữ liệu");
}
```

Có thể thay `get()` bằng `orElse` hoặc `orElseThrow` tùy hợp đồng ứng dụng.

### 4.1. Ca rỗng sau bộ lọc

```java
List<Integer> diem = Arrays.asList(3, 4, 5);

Optional<Integer> tongDiemDat = diem.stream()
    .filter(d -> d >= 6)
    .reduce(Integer::sum);

System.out.println(tongDiemDat.isPresent()); // false
```

Dù nguồn ban đầu không rỗng, sau bộ lọc không có phần tử nào. Do vậy, cần kiểm tra đầu ra **sau toàn bộ pipeline**, không chỉ `list.isEmpty()` của nguồn.

## 5. Phần tử đơn vị (identity) phải đúng phép toán

Với phép toán nhị phân `op`, một identity `e` phải thỏa mãn:

```text
op(e, x) == x
op(x, e) == x
```

cho mọi giá trị hợp lệ `x` thuộc miền thao tác. Đây là phần tử đơn vị **hai phía**, giúp các kết quả từ những nhóm được ghép chính xác.

| Phép rút gọn | Identity hợp lý | Vì sao |
| --- | --- | --- |
| Cộng số nguyên | `0` | `0 + x = x + 0 = x` |
| Nhân số nguyên | `1` | `1 * x = x * 1 = x` |
| Ghép chuỗi | `""` | `"" + x = x + "" = x` |
| Giá trị lớn nhất trên mọi `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Giá trị nhỏ nhất trên mọi `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |
| AND boolean | `true` | `true && x = x` |
| OR boolean | `false` | `false || x = x` |

Lựa chọn identity đúng **phải phù hợp miền dữ liệu và hợp đồng kết quả**. Với phép max, nếu nguồn rỗng và cần biết "không có giá trị lớn nhất", `IntStream.max()` trả `OptionalInt` thường hợp lý hơn `reduce(Integer.MIN_VALUE, Math::max)`.

### 5.1. Identity sai: lỗi có thể chỉ lộ khi chạy song song

```java
List<Integer> so = Arrays.asList(1, 2, 3);

// SAI: 10 không phải identity của phép cộng.
int sai = so.stream().reduce(10, Integer::sum);

System.out.println(sai); // 16, thay vì tổng đúng 6
```

Với một stream song song, identity có thể được dùng cho nhiều nhóm. Nếu mỗi nhóm cộng thêm `10`, kết quả cuối có thể sai theo cách khác. **Không dựa vào số nhóm cụ thể** vì chiến lược chia nguồn tùy triển khai.

Đúng:

```java
int tong = so.parallelStream()
    .reduce(0, Integer::sum);

System.out.println(tong); // 6
```

Ví dụ khác: nếu cố tìm số lớn nhất trong toàn bộ miền số nguyên bằng `reduce(0, Math::max)` thì dữ liệu toàn số âm cho kết quả sai:

```java
int sai = java.util.stream.IntStream.of(-9, -4, -7)
    .reduce(0, Math::max);

System.out.println(sai); // 0; không phải -4

int dung = java.util.stream.IntStream.of(-9, -4, -7)
    .max()
    .orElseThrow(() -> new IllegalStateException("Nguồn rỗng"));

System.out.println(dung); // -4
```

Dạng `max()` vừa có ngữ nghĩa rõ ràng vừa xử lý nguồn rỗng một cách tường minh.

## 6. Tính kết hợp (associativity) quyết định khả năng song song

Một phép toán `op` có tính kết hợp khi:

```text
op(op(a, b), c) == op(a, op(b, c))
```

Trong ví dụ cộng số nguyên **không tràn**, việc thay đổi cách đặt ngoặc không làm đổi kết quả:

```text
(2 + 4) + 6 = 2 + (4 + 6) = 12
```

Vì vậy, phép cộng cùng identity `0` thích hợp với `reduce` song song trong miền số học có kết quả xác định.

### 6.1. Phép trừ không kết hợp

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Do đó, đây là phép giảm không an toàn khi kỳ vọng cùng kết quả giữa tuần tự và song song:

```java
List<Integer> so = Arrays.asList(1, 2, 3, 4);

int tuanTu = so.stream()
    .reduce(0, (a, b) -> a - b);

int songSong = so.parallelStream()
    .reduce(0, (a, b) -> a - b);

System.out.println(tuanTu); // -10
System.out.println(songSong); // Không có kết quả chung được bảo đảm
```

Một lần chạy có thể tình cờ giống mong đợi; điều đó **không chứng minh** phép giảm đúng. Cần xét luật kết hợp thay vì chỉ quan sát vài đầu ra.

### 6.2. Tính kết hợp không đồng nghĩa với tính giao hoán

Phép ghép chuỗi có tính kết hợp:

```text
("A" + "B") + "C" == "A" + ("B" + "C") == "ABC"
```

Nhưng không giao hoán: `"A" + "B"` khác `"B" + "A"`. Với **nguồn có thứ tự**, một phép `reduce` hợp lệ dùng ghép chuỗi vẫn bảo toàn kết quả theo thứ tự gặp phần tử, kể cả khi triển khai xử lý song song.

```java
import java.util.Arrays;

List<String> chu = Arrays.asList("A", "B", "C");

String tuanTu = chu.stream().reduce("", String::concat);
String songSong = chu.parallelStream().reduce("", String::concat);

System.out.println(tuanTu);  // ABC
System.out.println(songSong); // ABC
```

Phép ghép chuỗi lặp lại thường không hiệu quả do tạo nhiều đối tượng `String`. Với yêu cầu thu chuỗi, `Collectors.joining()` thường thích hợp hơn. Không nên dựa vào thứ tự ghi log hoặc thứ tự thực thi các lambda để suy ra thứ tự kết quả.

## 7. Overload ba tham số: kiểm chứng accumulator và combiner

Với `Stream<T>.reduce(U identity, accumulator, combiner)`, phải thỏa **cả ba** điều kiện:

1. **Identity trung hòa với combiner:** `combiner(identity, u) == u` (và chiều còn lại, nếu phép kết hợp cần identity hai phía).
2. **Combiner có tính kết hợp:** có thể ghép các nhóm theo nhiều cách mà vẫn được kết quả tương đương.
3. **Accumulator tương thích combiner:** với mọi tích lũy hợp lệ `u` và phần tử `t`:

```text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
```

Ví dụ đúng — tính tổng độ dài chuỗi:

```java
import java.util.Arrays;
import java.util.List;

List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tongTuanTu = ten.stream()
    .reduce(
        0,
        (n, s) -> n + s.length(),
        Integer::sum
    );

int tongSongSong = ten.parallelStream()
    .reduce(
        0,
        (n, s) -> n + s.length(),
        Integer::sum
    );

System.out.println(tongTuanTu);  // 12
System.out.println(tongSongSong); // 12
```

Vì `accumulator(0, "Go") = 2`, rồi `combiner(u, 2) = u + 2`, đúng với `accumulator(u, "Go") = u + 2`. Tương tự với mọi chuỗi khác.

### 7.1. Combiner sai có thể bị che ở chế độ tuần tự

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

// SAI: combiner trừ hai tổng con.
int sai = ten.parallelStream()
    .reduce(
        0,
        (n, s) -> n + s.length(),
        (a, b) -> a - b
    );
```

Ở chế độ tuần tự, combiner có thể không được dùng, nên thử riêng `ten.stream()` không đủ để lộ lỗi. Trong chế độ song song, combiner có thể được dùng để gộp các kết quả; phép trừ không đáp ứng hợp đồng.

Sửa bằng `Integer::sum` hoặc, khi chỉ cần đếm ký tự, dùng:

```java
int tong = ten.parallelStream()
    .mapToInt(String::length)
    .sum();
```

## 8. Vì sao identity chứa tiền tố dễ cho kết quả sai?

Giả sử muốn ghép các nhãn với tiền tố "Mã: ":

```java
List<String> ma = Arrays.asList("A", "B", "C");

// SAI với reduce song song: "Mã: " không phải identity của concat.
String ketQua = ma.parallelStream()
    .reduce("Mã: ", String::concat);
```

Ở chế độ tuần tự, ta có thể thấy `"Mã: ABC"`. Trong xử lý song song, nếu mỗi nhánh được bắt đầu với `"Mã: "`, tiền tố có thể xuất hiện nhiều lần. Cách làm đúng: dùng identity `""` rồi thêm tiền tố **một lần** sau phép giảm.

```java
String maGhep = ma.parallelStream()
    .reduce("", String::concat);

String ketQua = "Mã: " + maGhep;
System.out.println(ketQua); // Mã: ABC
```

Khi xử lý nhiều chuỗi, dùng collector chuyên dụng thường hợp lý hơn:

```java
import java.util.stream.Collectors;

String ketQua = ma.parallelStream()
    .collect(Collectors.joining("", "Mã: ", ""));

System.out.println(ketQua); // Mã: ABC
```

Đây là một ví dụ về ranh giới giữa `reduce` và `collect`: collector được thiết kế để tích lũy vào cấu trúc phù hợp, trong khi `reduce` yêu cầu các giá trị tích lũy đáp ứng các luật kết hợp và identity.

## 9. Không sửa đối tượng tích lũy dùng chung trong `reduce`

Một anti-pattern là dùng một đối tượng có thể sửa như `ArrayList` làm identity rồi thêm phần tử vào chính nó:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

// KHÔNG NÊN DÙNG, nhất là với parallelStream().
List<Integer> sai = Arrays.asList(1, 2, 3, 4)
    .parallelStream()
    .reduce(
        new ArrayList<Integer>(),
        (list, n) -> {
            list.add(n); // Thay đổi chính đối tượng tích lũy.
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

Vấn đề: identity là cùng một tham chiếu có thể được sử dụng ở nhiều nhánh; thao tác `add` và `addAll` thay đổi trạng thái, có thể gây race condition, lặp phần tử, sai kết quả hoặc lỗi lúc chạy. Phép rút gọn không bảo đảm tạo một bản sao identity mới cho mỗi nhánh.

Nếu cần thu nhiều phần tử thành danh sách, sử dụng `collect`:

```java
import java.util.stream.Collectors;

List<Integer> dung = Arrays.asList(1, 2, 3, 4)
    .parallelStream()
    .collect(Collectors.toList());

System.out.println(dung); // [1, 2, 3, 4]
```

Collector có cơ chế `supplier` tạo vùng tích lũy phù hợp cho từng phần khi cần và `combiner` để ghép chúng. Việc dùng collector đúng hợp đồng giúp giảm nguy cơ chia sẻ trạng thái ngoài ý muốn.

Cũng tránh tăng biến đếm ngoài pipeline trong `accumulator`:

```java
// KHÔNG NÊN: tác dụng phụ trên trạng thái bên ngoài.
java.util.concurrent.atomic.AtomicInteger soLanGoi =
    new java.util.concurrent.atomic.AtomicInteger();

int tong = Arrays.asList(1, 2, 3).parallelStream()
    .reduce(0, (a, b) -> {
        soLanGoi.incrementAndGet();
        return a + b;
    });
```

Dù `AtomicInteger` có thể cập nhật an toàn về mặt đồng thời, số lần gọi lambda là chi tiết thực thi, không phải định nghĩa nghiệp vụ của tổng. Hãy tính số lượng bằng `count()` nếu thực sự cần đếm phần tử.

## 10. Kiểm chứng tính đúng bằng các phép thử có chủ đích

Một số trường hợp đơn giản rất hữu ích:

| Ca thử | Dữ liệu | Điều cần kiểm chứng |
| --- | --- | --- |
| Rỗng | `[]` | Overload có identity trả identity; không identity trả Optional rỗng. |
| Một phần tử | `[7]` | Phép giảm trả giá trị phù hợp, identity không làm sai. |
| Nhiều phần tử | `[1, 2, 3, 4]` | Kết quả đúng theo phép toán. |
| Có số âm và 0 | `[-3, 0, 7, -2]` | Không dùng identity thiếu trung lập như `0` cho max trên miền âm. |
| Bị lọc hết | `[2, 4, 6]` với `filter(n -> n < 0)` | Pipeline rỗng được xử lý đúng. |
| Nguồn có thứ tự | `["A", "B", "C"]` | Phép kết hợp phù hợp với kỳ vọng thứ tự. |
| Song song | Cùng tập dữ liệu ở chế độ `parallelStream()` | Kết quả logic nhất quán khi phép toán đáp ứng các luật. |
| Chia nhóm khác nhau | `(a op b) op c` so với `a op (b op c)` | Kiểm tra tính kết hợp trước khi tin phép rút gọn song song. |

**Lưu ý:** chạy `parallelStream()` vài lần và thấy kết quả giống nhau **không chứng minh** phép toán thỏa luật kết hợp. Kích thước dữ liệu, số nhân CPU và chiến lược chia nguồn có thể khiến lỗi chưa xuất hiện. Phép kiểm tra đại số và các ca biên cần đi cùng kiểm thử thực thi.

### 10.1. Chọn một “oracle” độc lập

Với phép cộng, có thể tính tổng mong đợi bằng vòng lặp đơn giản để đối chiếu; không nên dùng lại chính cùng một biểu thức `reduce` rồi coi đó là bằng chứng độc lập.

```java
long mongDoi = 0L;
for (int so : Arrays.asList(-3, 0, 7, -2)) {
    mongDoi += so;
}
System.out.println(mongDoi); // 2
```

Ở ví dụ này, dùng `long` và dữ liệu nhỏ để tránh tràn số khi kiểm chứng. Với sản phẩm thực tế, phải xác định rõ yêu cầu về miền số và cách xử lý tràn.

### 10.2. So sánh hai cách nhóm mà không cần chạy song song

Tính kết hợp là thuộc tính toán học. Có thể kiểm tra một số bộ giá trị cụ thể trước:

```java
import java.util.function.IntBinaryOperator;

IntBinaryOperator cong = Integer::sum;
IntBinaryOperator tru = (a, b) -> a - b;

boolean congKetHop =
    cong.applyAsInt(cong.applyAsInt(10, 3), 2)
    == cong.applyAsInt(10, cong.applyAsInt(3, 2));

boolean truKetHop =
    tru.applyAsInt(tru.applyAsInt(10, 3), 2)
    == tru.applyAsInt(10, tru.applyAsInt(3, 2));

System.out.println(congKetHop); // true
System.out.println(truKetHop);  // false
```

Một ví dụ thành công không chứng minh luật đúng **cho mọi giá trị**, nhưng một phản ví dụ thất bại đã đủ bác bỏ luật.

## 11. Chương trình kiểm chứng hoàn chỉnh (Java 8+)

Đoạn sau không cần thư viện kiểm thử. Nó kiểm tra nguồn rỗng, nguồn một phần tử, nhiều phần tử, tổng độc lập, pipeline tuần tự/song song và overload ba tham số.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class KiemChungReduce {
    private static void yeuCau(boolean dung, String thongBao) {
        if (!dung) {
            throw new AssertionError(thongBao);
        }
    }

    private static long tinhTong(List<Integer> so, boolean songSong) {
        LongStream stream = so.stream()
            .mapToLong(Integer::longValue);

        if (songSong) {
            stream = stream.parallel();
        }

        return stream.reduce(0L, Long::sum);
    }

    public static void main(String[] args) {
        Optional<Integer> khongIdentity =
            Stream.<Integer>empty().reduce(Integer::sum);

        int coIdentity = Stream.<Integer>empty()
            .reduce(0, Integer::sum);

        yeuCau(!khongIdentity.isPresent(),
            "Nguồn rỗng phải trả Optional.empty()");
        yeuCau(coIdentity == 0,
            "Nguồn rỗng phải trả về identity 0");

        List<List<Integer>> cacCa = Arrays.asList(
            Collections.<Integer>emptyList(),
            Collections.singletonList(7),
            Arrays.asList(1, 2, 3, 4),
            Arrays.asList(-3, 0, 7, -2),
            Arrays.asList(0, 0, 0)
        );

        for (List<Integer> ca : cacCa) {
            long mongDoi = 0L;
            for (int n : ca) {
                mongDoi += n;
            }

            yeuCau(tinhTong(ca, false) == mongDoi,
                "Sai kết quả tuần tự cho " + ca);
            yeuCau(tinhTong(ca, true) == mongDoi,
                "Sai kết quả song song cho " + ca);
        }

        List<String> ten = Arrays.asList(
            "Java", "Go", "Kotlin"
        );

        int tuanTu = ten.stream().reduce(
            0, (n, s) -> n + s.length(), Integer::sum);

        int songSong = ten.parallelStream().reduce(
            0, (n, s) -> n + s.length(), Integer::sum);

        yeuCau(tuanTu == 12 && songSong == 12,
            "Sai tổng độ dài");

        System.out.println("PASS: các ca reduce hợp lệ");
    }
}
```

Khi chạy trên môi trường Java 8+, chương trình đúng sẽ in:

```text
PASS: các ca reduce hợp lệ
```

Việc kiểm tra cả nguồn rỗng và nhiều cách thực thi giúp phát hiện lỗi phổ biến. Nó không thay thế cho việc chứng minh identity, associativity và tính tương thích của combiner đối với **toàn miền dữ liệu thực tế**.

## 12. Số thực, tràn số và độ chính xác

### 12.1. Phép cộng `double` không kết hợp chính xác theo bit

Dấu phẩy động có sai số làm tròn. Ví dụ:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double trai = (a + b) + c;
double phai = a + (b + c);

System.out.println(trai); // 1.0
System.out.println(phai); // 0.0
```

Vì vậy, với `DoubleStream.reduce(0.0, Double::sum)`, cách nhóm phần tử có thể ảnh hưởng đến những bit cuối của kết quả. Đối với tính toán xấp xỉ, xác định **dung sai** (tolerance) hoặc mức sai số chấp nhận được. Khi cần số thập phân chính xác cho tiền tệ, cân nhắc `BigDecimal` và quy tắc làm tròn rõ ràng.

Lưu ý: `DoubleStream.sum()` có thể dùng kỹ thuật cộng bù để giảm sai số, nên không suy diễn rằng nó có đúng từng bước cộng như `reduce(0.0, Double::sum)`.

### 12.2. Tràn số nguyên

`IntStream.reduce(0, Integer::sum)` hoặc `IntStream.sum()` có thể tràn `int` nếu tổng vượt miền 32-bit. Chuyển thành `long` **trước khi cộng**:

```java
import java.util.stream.IntStream;

long tong = IntStream.of(
        1_500_000_000, 1_500_000_000
    )
    .asLongStream()
    .reduce(0L, Long::sum);

System.out.println(tong); // 3000000000
```

`long` vẫn có giới hạn. Khi yêu cầu miền giá trị vượt `long`, có thể dùng `BigInteger`:

```java
import java.math.BigInteger;
import java.util.stream.Stream;

BigInteger tong = Stream.of(
        BigInteger.valueOf(Long.MAX_VALUE),
        BigInteger.ONE
    )
    .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(tong); // 9223372036854775808
```

Mỗi phép cộng `BigInteger` tạo kết quả mới, không sửa `identity`, nên phù hợp với tư duy reduction không thay đổi trạng thái.

## 13. Khi nào dùng `reduce`, khi nào dùng `collect`?

`reduce` phù hợp khi có thể **gộp các giá trị thành một giá trị mới** bằng phép toán thỏa các luật:

- Tổng, tích, min, max trên miền hợp lệ.
- Ghép chuỗi đơn giản nếu hiệu năng không phải vấn đề.
- Rút gọn đối tượng bất biến với một phép kết hợp đúng.

`collect` phù hợp khi cần **tích lũy vào một vùng kết quả có thể sửa** hoặc cấu trúc phức tạp:

- Danh sách, tập hợp, bản đồ.
- `groupingBy`, `partitioningBy`, `joining`.
- Collector tùy chỉnh có `supplier`, `accumulator` và `combiner` được thiết kế cho kết quả có thể thay đổi.

Ví dụ cùng một tổng độ dài có thể viết:

```java
int dungReduce = ten.stream()
    .reduce(0, (n, s) -> n + s.length(), Integer::sum);

int deDocHon = ten.stream()
    .mapToInt(String::length)
    .sum();

System.out.println(dungReduce == deDocHon); // true
```

Không phải bài toán nào cũng cần tự viết `reduce`. Khi API đã có `sum`, `min`, `max`, `count` hoặc collector thích hợp, dùng chúng sẽ làm ý định rõ hơn và hạn chế cơ hội viết sai combiner.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Nguồn rỗng nhưng nhận một giá trị giả định không có ý nghĩa | Chọn identity tùy tiện | Xác định identity thực sự, hoặc dùng overload trả `Optional` |
| Kết quả tuần tự đúng, song song sai | Phép toán không kết hợp, combiner sai hoặc identity không trung hòa | Kiểm tra ba luật của `reduce` |
| Tiền tố xuất hiện nhiều lần khi `parallelStream()` | Đưa tiền tố vào identity của phép ghép chuỗi | Dùng `""` làm identity rồi thêm tiền tố sau reduction, hoặc `Collectors.joining` |
| `reduce(0, Math::max)` trả 0 khi mọi số âm | 0 không trung hòa cho max trên toàn miền `int` | Dùng `max()` trả `OptionalInt`, hoặc identity đúng miền |
| Danh sách bị nhân đôi / lỗi đồng thời khi reduce song song | Sửa chung `ArrayList` trong accumulator | Dùng `collect(toList())` |
| Chỉ thử với 1 phần tử nên không thấy lỗi | Không kiểm tra phép kết hợp trên nhiều nhánh | Thêm ca nhiều phần tử, kiểm tra nhóm khác nhau |
| So sánh bằng tuyệt đối giữa kết quả `double` tuần tự và song song | Sai số dấu phẩy động phụ thuộc thứ tự gộp | Dùng kiểm tra dung sai theo nghiệp vụ |
| Tổng `int` bị âm bất ngờ | Tràn số | Chọn miền `long` hoặc `BigInteger` phù hợp |
| Giả định số lần gọi lambda bằng số phần tử | Triển khai có thể chia nhóm/đánh giá khác nhau | Kiểm tra kết quả, tránh phụ thuộc tác dụng phụ |

## 15. Bài tập thực hành

### Bài 1 — Nguồn rỗng

Dự đoán kết quả và kiểu trả về:

```java
Optional<Integer> a = Stream.<Integer>empty()
    .reduce(Integer::sum);

int b = Stream.<Integer>empty()
    .reduce(0, Integer::sum);

int c = java.util.stream.IntStream.empty()
    .reduce(1, (x, y) -> x * y);
```

Khi nào nên dùng `Optional` thay vì gán một identity?

### Bài 2 — Xác định identity

Cho các phép giảm trên `IntStream`: cộng, nhân, lấy max của mọi `int`. Hãy chọn identity đúng cho từng phép và giải thích vì sao `0` không phù hợp với max khi nguồn có số âm.

### Bài 3 — Chứng minh phép toán sai khi chạy song song

Giải thích tại sao `(a - b) - c` khác `a - (b - c)`. Viết một bộ ba số làm phản ví dụ. Có thể kết luận phép trừ là combiner hợp lệ chỉ nhờ một lần chạy `parallelStream()` không?

### Bài 4 — Sửa combiner

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int ketQua = ten.parallelStream().reduce(
    0,
    (n, s) -> n + s.length(),
    (a, b) -> a - b
);
```

Sửa thành phép giảm đúng và giải thích bằng công thức tương thích với accumulator.

### Bài 5 — Tính tổng an toàn hơn

Cho `int[] giaoDich = {1_500_000_000, 1_500_000_000};`. Viết pipeline giảm để kết quả chính xác là `3_000_000_000L`. Vì sao gọi `IntStream.sum()` trước khi chuyển sang `long` không thể khôi phục kết quả?

### Đáp án tham khảo

**Bài 1:** `a` là `Optional.empty()`, `b == 0`, `c == 1`. Dùng `Optional` khi nghiệp vụ cần nhận biết không có dữ liệu, chẳng hạn không có điểm lớn nhất trong tập rỗng.

**Bài 2:** cộng dùng `0`, nhân dùng `1`, max trên toàn miền `int` dùng `Integer.MIN_VALUE`. Với một nguồn có thể rỗng, `IntStream.max()` trả `OptionalInt` thường rõ nghĩa hơn vì phân biệt vắng dữ liệu.

**Bài 3:** chọn `a = 10`, `b = 3`, `c = 2`: `(10 - 3) - 2 = 5` còn `10 - (3 - 2) = 9`. Không thể chứng minh bằng một lần chạy; luật kết hợp đã bị phản ví dụ bác bỏ.

**Bài 4:**

```java
int ketQua = ten.parallelStream().reduce(
    0,
    (n, s) -> n + s.length(),
    Integer::sum
);

System.out.println(ketQua); // 12
```

Vì `Integer.sum(u, 0 + s.length()) == u + s.length()`, combiner tương thích với accumulator; `0` trung hòa phép cộng.

**Bài 5:**

```java
long tong = java.util.Arrays.stream(giaoDich)
    .asLongStream()
    .reduce(0L, Long::sum);

System.out.println(tong); // 3000000000
```

Phải chuyển từng phần tử sang `long` trước phép cộng; chuyển sau khi `IntStream.sum()` đã bị tràn không sửa được dữ liệu.

## 16. Ghi nhớ

Một phép `reduce` đáng tin cậy phải đúng với **nguồn rỗng** và **mọi cách nhóm phần tử hợp lệ**:

- Không có identity → kết quả có thể là `Optional.empty()`.
- Có identity → nguồn rỗng trả identity; identity phải thực sự trung hòa phép toán.
- Phép kết hợp phải có tính **associativity**; overload ba tham số còn đòi hỏi accumulator tương thích với combiner.
- Không sửa trạng thái dùng chung trong `reduce`; khi cần tích lũy cấu trúc thay đổi được, ưu tiên `collect`.
- Kiểm thử nguồn rỗng, một phần tử, nhiều phần tử, dữ liệu âm/0 và pipeline song song; kiểm tra các luật đại số thay vì chỉ nhìn kết quả một lần chạy.
- Với số thực và số nguyên lớn, xét yêu cầu về sai số và tràn số trước khi khẳng định kết quả chính xác.

Hiểu được các điều kiện này giúp bạn dùng `reduce` đúng trong pipeline Java Stream API, kể cả khi quá trình thực thi chuyển từ tuần tự sang song song.
