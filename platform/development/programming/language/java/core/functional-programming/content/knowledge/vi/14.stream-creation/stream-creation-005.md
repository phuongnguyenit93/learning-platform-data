# `Stream.iterate()` có hoặc không có điều kiện dừng trong Java

## 1. Bản chất của `Stream.iterate`

`Stream.iterate` tạo một **luồng phần tử theo quy luật lặp**: bắt đầu từ một giá trị (*seed*), rồi liên tục dùng hàm chuyển trạng thái để tính giá trị kế tiếp. Đây là một *stream source*, thường dùng khi phần tử sau được suy ra từ phần tử trước, chẳng hạn dãy số, ngày lịch, trạng thái xử lý hoặc mô phỏng một quá trình tăng dần.

Java hỗ trợ hai overload quan trọng:

```java
// Có từ Java 8: nguồn về nguyên tắc không giới hạn.
static <T> Stream<T> iterate(T seed, UnaryOperator<T> next);

// Có từ Java 9: thêm điều kiện để kết thúc.
static <T> Stream<T> iterate(
        T seed,
        Predicate<? super T> hasNext,
        UnaryOperator<T> next);
```

Hai chữ ký trên là bản **rút gọn để học**, thuộc `java.util.stream.Stream`; phương thức thực trong JDK còn có khai báo đầy đủ theo API. Ý nghĩa:

- `seed`: giá trị đầu tiên được xem xét.
- `next`: hàm lấy giá trị hiện tại để tính giá trị tiếp theo; cùng kiểu `T → T` (`UnaryOperator<T>`).
- `hasNext`: điều kiện tiếp tục, nhận giá trị hiện tại và trả `boolean` (`Predicate<? super T>`). Nó chỉ có trong overload ba tham số.

**Không có `hasNext`:** nguồn là một quá trình lặp không có điều kiện dừng được khai báo bên trong `iterate`. Muốn thu được kết quả hữu hạn, thường dùng terminal operation short-circuit hoặc intermediate operation giới hạn như `limit` và `takeWhile`.

**Có `hasNext`:** trước khi đưa **một giá trị hiện tại** vào stream, Java kiểm tra điều kiện. Nếu `hasNext.test(current)` là `false`, giá trị ấy **không xuất hiện** và quá trình lặp kết thúc. Nếu điều kiện luôn đúng, overload ba tham số vẫn có thể tạo một quá trình không kết thúc.

`Stream.iterate` tạo một stream **tuần tự, có thứ tự encounter order** theo mặc định. Các phần tử phát ra giữ đúng trình tự tính từ seed theo quy luật next, dù cách xử lý có thể khác khi người dùng chủ động chuyển sang `parallel()`.

## 2. Overload hai tham số: `Stream.iterate(seed, next)`

Ví dụ tạo các số nguyên từ 1 trở lên:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
```

Ở đây:

1. `seed = 1`.
2. `next = n -> n + 1`.
3. Stream cung cấp 1, 2, 3, 4, 5, ... khi downstream yêu cầu.
4. `limit(5)` chỉ lấy **tối đa 5 phần tử**, khiến terminal operation `toList()` có thể hoàn tất.

Đoạn trên đặt trong một phương thức hoặc `jshell`. Nếu bỏ `limit(5)` rồi gọi `toList()` lên stream nguồn không giới hạn, chương trình không có điểm kết thúc bình thường khi xử lý dãy không giới hạn; nó có thể tiếp tục tiêu tốn CPU/bộ nhớ hoặc gặp sự cố tài nguyên.

**Quan trọng:** “không giới hạn” nói về **số lần lặp do API cho phép**, không có nghĩa phép tính luôn cho một dãy toán học vô hạn các giá trị phân biệt. Với `int`, `n + 1` có thể **overflow** nếu chạy quá lâu; khi đó giá trị vẫn được tạo nhưng không còn tăng theo nghĩa toán học thông thường.

### Cú pháp dùng method reference

Nếu có sẵn hàm biến đổi kiểu `T → T`, ta có thể truyền tham chiếu phương thức:

```java
static int stepByTwo(int current) {
    return current + 2;
}

// Đặt trong một method của lớp đang có stepByTwo:
List<Integer> values = Stream.iterate(0, MyClass::stepByTwo)
        .limit(4)
        .toList();
// values = [0, 2, 4, 6]
```

Đây là **mã minh họa**: cần đổi `MyClass` thành tên lớp khai báo phương thức `static stepByTwo`, hoặc dùng lambda `n -> n + 2`. Mục tiêu là hiểu rằng `next` có thể là lambda hay method reference miễn tương thích với `UnaryOperator<T>`.

## 3. Overload ba tham số: `Stream.iterate(seed, hasNext, next)`

Cú pháp này mô tả quá trình lặp gần giống vòng `for` truyền thống:

```java
Stream.iterate(1, n -> n <= 5, n -> n + 1)
        .forEach(System.out::println);
```

Output:

```text
1
2
3
4
5
```

Tương ứng về ý tưởng với:

```java
for (int n = 1; n <= 5; n++) {
    System.out.println(n);
}
```

Cách diễn giải:

- Xét `1`: `1 <= 5` đúng, phát 1.
- Tính phần tử tiếp theo `2`: điều kiện đúng, phát 2.
- Tiếp tục tới `5`: điều kiện vẫn đúng, phát 5.
- Xét `6`: `6 <= 5` sai, **không phát 6** và kết thúc.

Đây là điểm dễ nhầm: điều kiện `hasNext` áp dụng lên **phần tử dự định phát ra**, không phải điều kiện “phát trước rồi mới xem có nên dừng không”.

### Điểm kết thúc là độc quyền (*exclusive*) nếu dùng `<`

```java
List<Integer> lessThanFive =
        Stream.iterate(1, n -> n < 5, n -> n + 1)
                .toList();

List<Integer> atMostFive =
        Stream.iterate(1, n -> n <= 5, n -> n + 1)
                .toList();

System.out.println(lessThanFive); // [1, 2, 3, 4]
System.out.println(atMostFive);   // [1, 2, 3, 4, 5]
```

Sự khác biệt nằm ở `<` và `<=`, giống một vòng `for`. Hãy quyết định quy tắc biên **trước khi viết** và kiểm tra các điểm bắt đầu/kết thúc.

### Seed không thỏa điều kiện: stream rỗng

```java
List<Integer> empty =
        Stream.iterate(8, n -> n < 5, n -> n + 1)
                .toList();

System.out.println(empty); // []
```

`hasNext.test(8)` là false, nên **ngay cả seed cũng không xuất hiện**. Không có chuyện stream luôn bắt buộc chứa một phần tử chỉ vì seed được truyền vào.

## 4. Chương trình Java 17 hoàn chỉnh có thể biên dịch và chạy

Ví dụ này so sánh các cách tạo stream và cho thấy tại sao một overload thường cần giới hạn từ downstream, còn overload kia có điều kiện dừng tại nguồn.

Tạo tệp **`StreamIterateDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.Collectors;

public class StreamIterateDemo {
    record Day(int number, int balance) {}

    public static void main(String[] args) {
        // 1. iterate 2 tham số: nguồn không giới hạn, limit số phần tử.
        List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
                .limit(5)
                .toList();
        System.out.println("Two args + limit: " + firstFive);

        // 2. iterate 3 tham số: dừng ở điều kiện n <= 5.
        List<Integer> bounded = Stream.iterate(
                        1,
                        n -> n <= 5,
                        n -> n + 1)
                .toList();
        System.out.println("Three args: " + bounded);

        // 3. Chỉ lấy số chẵn chưa tới 10.
        List<Integer> evens = Stream.iterate(
                        0,
                        n -> n < 10,
                        n -> n + 2)
                .toList();
        System.out.println("Evens: " + evens);

        // 4. Seed không thỏa điều kiện => rỗng.
        List<Integer> empty = Stream.iterate(
                        8,
                        n -> n < 5,
                        n -> n + 1)
                .toList();
        System.out.println("Rejected seed: " + empty);

        // 5. iterate 2 tham số + takeWhile (Java 9+).
        List<Integer> taken = Stream.iterate(1, n -> n + 1)
                .takeWhile(n -> n < 6)
                .toList();
        System.out.println("Take while: " + taken);

        // 6. limit theo số phần tử, không theo giá trị.
        List<Integer> multiples = Stream.iterate(3, n -> n + 3)
                .limit(4)
                .toList();
        System.out.println("Four multiples: " + multiples);

        // 7. Mỗi phần tử có thể là một trạng thái bất biến.
        List<Day> days = Stream.iterate(
                        new Day(1, 100),
                        day -> day.number() <= 4,
                        day -> new Day(day.number() + 1,
                                       day.balance() + 25))
                .toList();
        String dailyReport = days.stream()
                .map(day -> "D" + day.number()
                            + "=" + day.balance())
                .collect(Collectors.joining(", "));
        System.out.println("Balances: " + dailyReport);

        // 8. Trường hợp chỉ cần số nguyên primitive.
        int sum = IntStream.iterate(1, n -> n <= 5, n -> n + 1)
                .sum();
        System.out.println("IntStream sum: " + sum);

        // 9. Lọc trước, dừng theo số phần tử cần lấy.
        List<Integer> evenFour = Stream.iterate(0, n -> n + 1)
                .filter(n -> n % 2 == 0)
                .limit(4)
                .toList();
        System.out.println("First four even: " + evenFour);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StreamIterateDemo.java
java StreamIterateDemo
```

**Stdout dự kiến chính xác:**

```text
Two args + limit: [1, 2, 3, 4, 5]
Three args: [1, 2, 3, 4, 5]
Evens: [0, 2, 4, 6, 8]
Rejected seed: []
Take while: [1, 2, 3, 4, 5]
Four multiples: [3, 6, 9, 12]
Balances: D1=100, D2=125, D3=150, D4=175
IntStream sum: 15
First four even: [0, 2, 4, 6]
```

Đối chiếu từng kết quả:

1. `firstFive` và `bounded` cùng có [1, 2, 3, 4, 5] nhưng **khác cơ chế dừng**: `limit(5)` lấy năm phần tử; `n <= 5` kiểm soát giá trị được phép phát.
2. `evens` bắt đầu 0 và tăng 2: 0, 2, 4, 6, 8. Phần tử tiếp theo 10 không thỏa `n < 10`.
3. `empty` là danh sách rỗng vì `8 < 5` sai ngay từ seed.
4. `takeWhile(n -> n < 6)` chỉ phát những phần tử đầu liên tiếp còn thỏa điều kiện, nên dừng ở trước số 6.
5. `multiples` có bốn phần tử: 3, 6, 9, 12. `limit(4)` không đồng nghĩa “dừng khi giá trị bằng 4”.
6. `days` mô hình hóa bốn trạng thái bất biến. Khởi đầu `Day(1,100)`; sau mỗi lần, số ngày +1 và số dư +25. Kết thúc trước ngày 5: D1=100, D2=125, D3=150, D4=175.
7. `IntStream.iterate(...).sum()` tính `1+2+3+4+5 = 15` mà không boxing mỗi giá trị thành `Integer`.
8. `evenFour` lọc các số chia hết cho 2 rồi `limit(4)`, nên lấy 0, 2, 4, 6; pipeline không cần duyệt mãi mãi.

Chương trình sử dụng stream tuần tự có encounter order, vì vậy `List.toString()` của các danh sách trong demo cho thứ tự như trên. `List` trả từ `Stream.toList()` không cho sửa qua `add`/`remove`; nếu cần một danh sách mutable, hãy chủ động tạo `new ArrayList<>(...)`.

## 5. So sánh chi tiết hai overload

| Tiêu chí | `iterate(seed, next)` | `iterate(seed, hasNext, next)` |
| --- | --- | --- |
| Có từ phiên bản | Java 8 | Java 9 |
| Số tham số | 2 | 3 |
| Nguồn có điều kiện kết thúc nội bộ | Không | Có |
| Seed có thể bị từ chối | Không vì không có `hasNext` | Có, nếu `hasNext(seed)` là false |
| Cách dừng thường dùng | `limit`, `takeWhile`, terminal operation short-circuit | `hasNext`, có thể kết hợp `limit` |
| Số phần tử | Về nguyên tắc không giới hạn | Phụ thuộc logic `hasNext` và `next`; có thể vẫn không kết thúc |
| Ví dụ | `iterate(1, n -> n + 1).limit(5)` | `iterate(1, n -> n <= 5, n -> n + 1)` |
| Tương đương gần gũi | Quy luật sinh dãy liên tục | Vòng `for(init; condition; update)` |
| Đánh giá | Lazy khi terminal operation duyệt | Lazy khi terminal operation duyệt |

“Có điều kiện dừng” ở đây **không bảo đảm** stream hữu hạn: nếu `hasNext` luôn true hoặc `next` không đưa trạng thái ra khỏi vùng thỏa điều kiện, stream không kết thúc. Ví dụ:

```java
// Sai nếu mong toList() hoàn tất:
Stream.iterate(1, n -> n > 0, n -> n)
        .limit(5)
        .forEach(System.out::println); // In 1 năm lần rồi kết thúc.
```

Đoạn minh họa chỉ kết thúc nhờ `limit(5)`. Nếu **bỏ `limit(5)`** và dùng `toList()`, predicate `n > 0` luôn true vì `next` trả chính `n`; nguồn không có điểm dừng. Ví dụ này chứng minh điều kiện phải đi cùng **quy luật tiến trạng thái** đúng.

## 6. `limit` và `takeWhile` khác nhau như thế nào?

### `limit(n)` dừng theo số lượng

`limit(n)` lấy **tối đa n phần tử** của stream. Với stream có encounter order, đó là **n phần tử đầu**.

```java
System.out.println(
    Stream.iterate(10, n -> n - 1)
            .limit(4)
            .toList()
); // [10, 9, 8, 7]
```

`limit(0)` cho stream rỗng. `limit` với số âm sẽ ném `IllegalArgumentException`. Nó không quan tâm các phần tử có giá trị bao nhiêu.

### `takeWhile(predicate)` dừng theo điều kiện trên phần tử

`takeWhile` (Java 9+) lấy **đoạn đầu dài nhất liên tiếp** gồm các phần tử còn thỏa predicate khi stream có encounter order. Ngay khi gặp phần tử đầu tiên không thỏa, quá trình thu thập đoạn đầu dừng.

```java
List<Integer> values = Stream.iterate(1, n -> n + 1)
        .takeWhile(n -> n < 5)
        .toList();

System.out.println(values); // [1, 2, 3, 4]
```

**Không nhầm `takeWhile` với `filter`**:

- `filter(n -> n < 5)` loại các phần tử không thỏa nhưng không tự kết thúc nguồn vô hạn chỉ vì đã gặp phần tử 5.
- `takeWhile(n -> n < 5)` dừng đoạn đầu tại phần tử 5, nên có thể kết thúc nếu phần tử vi phạm xuất hiện sau hữu hạn bước.

Một ví dụ phân biệt trên nguồn hữu hạn:

```java
List<Integer> items = List.of(1, 2, 8, 3);

System.out.println(items.stream()
        .filter(n -> n < 5)
        .toList()); // [1, 2, 3]

System.out.println(items.stream()
        .takeWhile(n -> n < 5)
        .toList()); // [1, 2]
```

Vì `takeWhile` không tự thu thập các phần tử phù hợp sau một phần tử không phù hợp, nó không phải là cách thay thế tùy ý cho `filter`.

### Kết hợp `filter` và `limit` trên nguồn vô hạn

```java
List<Integer> firstThreeMultiplesOfSeven =
        Stream.iterate(1, n -> n + 1)
              .filter(n -> n % 7 == 0)
              .limit(3)
              .toList();

System.out.println(firstThreeMultiplesOfSeven); // [7, 14, 21]
```

`filter` một mình không tạo điểm dừng; `limit(3)` đặt mục tiêu lấy ba giá trị *đã lọc*, không phải ba giá trị ban đầu. Đảm bảo có đủ phần tử thỏa điều kiện; nếu không, pipeline với nguồn vô hạn có thể tìm kiếm mãi.

## 7. Lazy evaluation: `iterate` không tính hết ngay khi tạo

Stream là chuỗi phép toán **lười** (*lazy*): gọi `Stream.iterate(...)` tạo mô tả nguồn, chưa tạo sẵn vô hạn object. Các phần tử được yêu cầu khi một terminal operation bắt đầu tiêu thụ pipeline.

```java
Stream<Integer> numbers = Stream.iterate(1, n -> n + 1);
// Chưa tiêu thụ số 1, 2, 3... để xây một danh sách ở đây.

List<Integer> firstThree = numbers.limit(3).toList();
// Đến terminal operation, kết quả là [1, 2, 3].
```

Một stream không được thiết kế để tái sử dụng sau khi đã tiêu thụ. Nếu muốn lấy thêm một tập giá trị, tạo **stream mới**:

```java
List<Integer> firstTwo =
        Stream.iterate(1, n -> n + 1).limit(2).toList();

List<Integer> firstFour =
        Stream.iterate(1, n -> n + 1).limit(4).toList();
```

Đừng viết:

```java
Stream<Integer> s = Stream.iterate(1, n -> n + 1);
s.limit(2).toList();
// s.limit(4).toList(); // Sai: dùng lại stream đã được thao tác/tiêu thụ.
```

Ngay cả thao tác intermediate như `limit` cũng là một phần của pipeline đã gắn với stream, vì thế không nên cố “rẽ nhánh” từ cùng một stream object. Tạo nguồn mới qua supplier nếu cần nhiều lần sử dụng.

### Không lạm dụng side effect trong `next` và `hasNext`

`next` nên mô tả **quy luật chuyển đổi trạng thái**. `hasNext` nên mô tả **điều kiện dừng**. Chẳng hạn `next` gọi API, ghi log hoặc sửa biến dùng chung thì việc thực thi lười, short-circuit hoặc song song hóa có thể làm số lần gọi và thứ tự side effect khó dự đoán.

Không nên viết nghiệp vụ phụ thuộc chính xác vào số lần `next` hoặc `hasNext` được gọi chỉ để sinh ra phần tử. Muốn thực hiện side effect có kiểm soát, tách bước tạo dữ liệu và bước lưu/hiển thị ra các ranh giới rõ ràng.

## 8. Dùng `iterate` để mô hình hóa trạng thái, không chỉ số nguyên

`iterate` hữu ích khi **phần tử sau là một trạng thái mới** tính từ trạng thái trước. Ví dụ một lịch nộp tiền mỗi ngày:

```java
record PaymentDay(int day, int saved) {}

List<PaymentDay> schedule = Stream.iterate(
        new PaymentDay(1, 100),
        state -> state.day() <= 3,
        state -> new PaymentDay(state.day() + 1,
                                state.saved() + 50))
        .toList();
```

Đây là đoạn minh họa; `PaymentDay` cần được đặt trong một lớp hoặc tệp hợp lệ với import `Stream`/`List`. Kết quả là ba trạng thái: (1,100), (2,150), (3,200). Trạng thái cũ không bị sửa, hàm `next` trả **một record mới**. Đây là cách phù hợp với phong cách functional: dữ liệu bất biến và biến đổi rõ ràng.

Nếu thay bằng object mutable rồi để `next` sửa **chính cùng object** và trả lại nó, các phần tử trong kết quả có thể cùng tham chiếu một đối tượng và cuối cùng trông như cùng một trạng thái. Với pipeline dùng để lưu lịch sử, hãy tạo giá trị mới hoặc sao chép phòng vệ theo yêu cầu.

Ví dụ lỗi khái niệm:

```java
// Giả sử MutableState có setDay(int) và getDay().
MutableState state = new MutableState(1);

List<MutableState> snapshots = Stream.iterate(
        state,
        s -> s.getDay() <= 3,
        s -> {
            s.setDay(s.getDay() + 1);
            return s; // Trả lại CHÍNH object đã sửa!
        })
        .toList();
```

Đây là **pseudocode minh họa** vì `MutableState` chưa được định nghĩa. Đừng dùng cách này để lưu snapshot; kể cả khi stream kết thúc, danh sách có thể chứa nhiều lần cùng một tham chiếu.

## 9. Tránh vòng lặp không kết thúc và tràn số

Một số lỗi liên quan trực tiếp tới điều kiện dừng:

### Điều kiện không bao giờ trở thành false

```java
// Có điều kiện nhưng không tiến triển; không dùng terminal toList().
Stream.iterate(1, n -> n > 0, n -> n);
```

`n` mãi bằng 1; `hasNext` mãi true. Dùng `limit` như biện pháp phòng vệ hoặc thiết kế lại `next` sao cho giá trị tiến tới trạng thái kết thúc.

### Điều kiện không tương ứng với chiều thay đổi

```java
// Khởi đầu 5, giảm dần, nhưng điều kiện lại n < 10:
// các giá trị có thể tiếp tục giảm và không vượt ngưỡng 10.
Stream.iterate(5, n -> n < 10, n -> n - 1);
```

Nếu mục tiêu là lấy `5,4,3,2,1`, viết:

```java
List<Integer> countdown =
        Stream.iterate(5, n -> n > 0, n -> n - 1)
              .toList();
// [5, 4, 3, 2, 1]
```

### Tràn số khi dùng `int`

`int` là số nguyên 32-bit có giới hạn. Nếu `n` tăng liên tục gần `Integer.MAX_VALUE`, `n + 1` có thể overflow và đổi sang số âm. Điều kiện `n <= Integer.MAX_VALUE` luôn đúng đối với mọi `int`, nên **không phải điều kiện dừng hữu ích** cho thao tác tăng `int`.

Để xử lý phạm vi lớn, cân nhắc `long`, `BigInteger` hoặc cách kiểm tra trước khi tăng. Ví dụ finite `BigInteger`:

```java
java.math.BigInteger one = java.math.BigInteger.ONE;

List<java.math.BigInteger> values = Stream.iterate(
        one,
        n -> n.compareTo(java.math.BigInteger.valueOf(4)) <= 0,
        n -> n.add(one))
        .toList();
// [1, 2, 3, 4]
```

`BigInteger` không overflow theo giới hạn primitive thông thường, nhưng vẫn cần tránh một vòng lặp không kết thúc, vấn đề cấp phát và giới hạn tài nguyên.

### Nguồn vô hạn với terminal cần tất cả phần tử

`count()`, `toList()`, `collect(...)` hoặc `reduce(...)` thường cần duyệt hết nguồn. Trên nguồn iterate không giới hạn mà không có điểm dừng downstream, chúng có thể không hoàn tất. `anyMatch`, `findFirst` và các terminal short-circuit có thể dừng nếu điều kiện tìm kiếm có lời giải sau hữu hạn phần tử, nhưng **không được đảm bảo** kết thúc nếu điều kiện không bao giờ đúng.

## 10. `IntStream.iterate` và `LongStream.iterate`

Khi phần tử là số nguyên primitive, JDK cung cấp các overload tương ứng trên `IntStream`/`LongStream`. Ví dụ:

```java
import java.util.stream.IntStream;

int total = IntStream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1)
        .sum();

System.out.println(total); // 15
```

`IntStream` xử lý `int` trực tiếp, tránh boxing từng phần tử thành `Integer` như `Stream<Integer>`. Nó hữu ích khi thực hiện phép toán số lượng lớn.

Tuy nhiên, nếu chỉ cần một khoảng số tăng đều, `IntStream.range(startInclusive, endExclusive)` hoặc `IntStream.rangeClosed(startInclusive, endInclusive)` có thể **đơn giản hơn**:

```java
System.out.println(
        IntStream.range(1, 6).boxed().toList()
); // [1, 2, 3, 4, 5]

System.out.println(
        IntStream.rangeClosed(1, 5).sum()
); // 15
```

Hãy chọn `iterate` khi **quy luật của phần tử kế tiếp không đơn thuần là tăng 1 theo một khoảng** hoặc khi cần mô hình hóa một trạng thái phức tạp; chọn `range`/`rangeClosed` khi chúng đủ diễn đạt mục đích.

### So sánh với `Stream.generate`

`Stream.generate(Supplier<T>)` tạo phần tử bằng cách gọi supplier, không trực tiếp nhận *giá trị trước đó* làm đầu vào:

```java
Stream<String> same = Stream.generate(() -> "A").limit(3);
System.out.println(same.toList()); // [A, A, A]
```

Nếu có nhu cầu tính `next` từ phần tử trước, `iterate` thường rõ hơn. `generate` có thể dùng supplier có trạng thái, nhưng khi đó cần cẩn thận về side effect và thread safety, đặc biệt với parallel stream. Một nguồn generate có thể không có thứ tự encounter order như nguồn iterate tuần tự có thứ tự.

## 11. Có nên chuyển `Stream.iterate` sang parallel?

`Stream.iterate` tạo nguồn **ordered, sequential** theo mặc định. Nếu gọi `parallel()`, các bước downstream có thể được xử lý song song, nhưng vì phần tử kế tiếp **phụ thuộc vào phần tử trước**, việc tạo/splitting dữ liệu không đơn giản như với `ArrayList` hoặc `IntStream.range`.

```java
List<Integer> values = Stream.iterate(1, n -> n <= 100, n -> n + 1)
        .parallel()
        .map(n -> n * 2)
        .toList();
```

Với stream có encounter order và `toList()`, thứ tự kết quả vẫn theo encounter order, nhưng điều đó **không có nghĩa** mỗi lambda `map` được gọi trên thread theo thứ tự 1,2,3,... hoặc việc song song luôn nhanh hơn. Không dùng side effect trong `next`/`map` và suy luận rằng `parallel()` sẽ giữ thứ tự cập nhật trạng thái ngoài.

Đối với thao tác đơn giản trên dãy số liên tiếp, `IntStream.range(...).parallel()` có thể dễ chia công việc hơn; dù vậy, quyết định tối ưu phải dựa trên đo đạc với tải thực tế.

Nếu có side effect in/log trong parallel stream, `forEach` không bảo đảm thứ tự. `forEachOrdered` bảo toàn encounter order của hành động nhưng có thể làm mất lợi thế song song. Cách tốt hơn trong nhiều trường hợp là **thu thập kết quả**, rồi thực hiện side effect theo thứ tự mong muốn ở tầng ngoài.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai/nguy hiểm | Cách sửa |
| --- | --- | --- |
| `Stream.iterate(1, n -> n + 1).toList()` | Nguồn không giới hạn, terminal cố lấy hết | Thêm `limit`/`takeWhile` hoặc overload có `hasNext` |
| Nhầm `limit(5)` là “giá trị tối đa 5” | `limit` chỉ giới hạn **số phần tử** | Dùng `hasNext`/`takeWhile` khi dừng theo giá trị |
| Nghĩ overload ba tham số luôn hữu hạn | Predicate có thể luôn đúng | Kiểm tra `next` có tiến tới vùng false không |
| Đặt điều kiện sai hướng | `next` đi xa khỏi ngưỡng dừng | Đối chiếu chiều tăng/giảm với điều kiện |
| Mong seed luôn xuất hiện | `hasNext(seed)` có thể false | Test ngay điều kiện ở seed |
| Dùng `filter` để “dừng” stream vô hạn | `filter` chỉ loại phần tử, không kết thúc nguồn | `takeWhile`/`limit` |
| Nhầm `takeWhile` với `filter` | `takeWhile` chỉ lấy đoạn đầu thỏa điều kiện | Dùng đúng mục đích |
| Gọi `toList()` trên stream đã tiêu thụ | Stream không tái sử dụng | Tạo một stream mới |
| `next` sửa và trả lại cùng object | Mọi phần tử có thể cùng tham chiếu object mutable | Dùng dữ liệu bất biến, trả trạng thái mới |
| `int` overflow nhưng điều kiện luôn true | Có thể sinh dãy sai hoặc vòng không kết thúc | Dùng giới hạn an toàn/kiểu số thích hợp |
| Side effect trong `next`, `hasNext` | Khó dự đoán thứ tự/số lần thực thi | Giữ lambdas thuần và tách I/O |
| Chuyển sang `parallel` và kỳ vọng nhanh hơn | Nguồn có quan hệ phụ thuộc giữa phần tử | Đo benchmark, cân nhắc `range` |
| Dùng `iterate` cho dãy `1..N` đơn giản | Mã dài hơn, dễ sai biên | `IntStream.range`/`rangeClosed` |

## 13. Bài tập thực hành

1. Với `Stream.iterate(2, n -> n * 2).limit(5)`, dự đoán danh sách kết quả. **Đáp án:** [2, 4, 8, 16, 32].
2. Viết overload ba tham số tạo các số lẻ từ 1 đến 9 (bao gồm 9). **Gợi ý:** seed 1, `n <= 9`, `n + 2`.
3. Viết hai phiên bản tạo [1, 2, 3, 4, 5] bằng `limit` và bằng `hasNext`. Giải thích khác biệt về ngữ nghĩa dừng.
4. Tại sao `Stream.iterate(10, n -> n < 10, n -> n + 1)` rỗng? Đổi điều kiện để lấy đúng số 10.
5. So sánh `Stream.iterate(1, n -> n + 1).filter(n -> n < 5).toList()` với `takeWhile(n -> n < 5).toList()`. Trong trường hợp nào chương trình có thể không kết thúc?
6. Tạo countdown từ 5 đến 1, dùng overload ba tham số. Dự đoán điều gì xảy ra nếu dùng `n < 5` làm predicate thay vì `n > 0`.
7. Tạo record `BalanceStep(int day, int amount)`, bắt đầu (1,100), tăng 20 mỗi ngày, dừng ở ngày 4. Tại sao trả record mới ở `next` an toàn hơn sửa cùng một object?
8. Dùng `IntStream.iterate` tính tổng các số chẵn nhỏ hơn 12. **Đáp án:** `0+2+4+6+8+10 = 30`.
9. Viết `Stream.iterate(1, n -> n + 1).filter(n -> n % 7 == 0).limit(3).toList()`. Dự đoán đầu ra và giải thích tại sao thứ tự `filter` trước `limit` quan trọng.
10. Thử `Stream.iterate(1, n -> n > 0, n -> n)` với `limit(3)`. Sau đó **không chạy phiên bản không có giới hạn**, mà giải thích bằng lý luận vì sao nó không thể tự kết thúc.
11. Khi xử lý tới gần `Integer.MAX_VALUE`, tại sao `n + 1` có thể phá logic predicate? Đề xuất một biểu diễn khác.
12. Khi một công việc chỉ cần tạo các số trong khoảng `[1,1000]`, chọn `iterate` hay `IntStream.rangeClosed`? Nêu lý do về tính rõ ràng và khả năng chia việc.

## 14. Checklist trước khi áp dụng `Stream.iterate`

- Quy luật “**giá trị kế tiếp từ giá trị hiện tại**” có thực sự phù hợp với `iterate` không?
- Chọn overload **hai tham số** hay **ba tham số**? Nếu không có `hasNext`, downstream có điểm dừng không?
- Predicate kiểm tra **seed** có đúng kết quả mong muốn không? Biên trên `<` hay `<=`?
- `next` có đưa trạng thái tới khi predicate false không? Có chu kỳ hay trạng thái đứng yên không?
- Có khả năng overflow số hoặc cấp phát dữ liệu vô hạn không?
- Có đang nhầm `limit` (theo **số lượng**) với `takeWhile` (theo **điều kiện**) không?
- Có đặt side effect trong `next`/`hasNext` hoặc dùng chung object mutable không?
- Với dãy số đơn giản, `IntStream.range` có diễn đạt rõ hơn không?
- Có thử cả các trường hợp **seed bị từ chối**, **giới hạn bằng 0**, **dừng đúng biên**, **không có giá trị thỏa bộ lọc** chưa?

**Ghi nhớ:** `Stream.iterate(seed, next)` tạo nguồn về nguyên tắc **không giới hạn** và thường cần `limit`/`takeWhile`; `Stream.iterate(seed, hasNext, next)` cho phép điều kiện dừng nằm ngay trong nguồn, kiểm tra **trước khi phát mỗi phần tử**. Dù chọn overload nào, hãy bảo đảm pipeline có đường kết thúc rõ ràng, trạng thái chuyển tiếp đúng và chi phí xử lý nằm trong giới hạn cho phép.
