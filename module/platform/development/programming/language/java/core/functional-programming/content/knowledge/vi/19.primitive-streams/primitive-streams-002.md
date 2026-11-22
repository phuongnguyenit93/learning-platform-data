# `range()` và `rangeClosed()` trong Java Primitive Streams

## 1. Bài toán và mục tiêu

Khi lập trình Java, ta thường cần một dãy số nguyên liên tiếp để đánh số thứ tự, duyệt chỉ số mảng, tạo mã thử nghiệm, lặp qua các ngày/giá trị nguyên hoặc tính tổng một khoảng. Viết vòng lặp `for` là cách quen thuộc, nhưng từ Java 8, **`IntStream` và `LongStream`** cung cấp các factory method chuyên tạo dãy số: `range()` và `rangeClosed()`.

Sự khác biệt cốt lõi nằm ở **cận trên**:

- `range(startInclusive, endExclusive)`: gồm điểm bắt đầu, **không gồm** điểm kết thúc, tương ứng khoảng **[start, end)**.
- `rangeClosed(startInclusive, endInclusive)`: gồm **cả hai** đầu mút khi start không lớn hơn end, tương ứng khoảng **[start, end]**.

Ví dụ:

~~~java
IntStream.range(2, 6);       // 2, 3, 4, 5
IntStream.rangeClosed(2, 6); // 2, 3, 4, 5, 6
~~~

Đây là hai biểu thức trả Stream, **chưa phải chương trình độc lập**. Chúng chưa in gì ra console; cần terminal operation như `toArray()`, `sum()`, `count()`, `forEach(...)` hoặc `boxed().toList()` để thu hoặc quan sát kết quả.

Sau bài học, người học cần:

1. Đọc đúng tham số `startInclusive`, `endExclusive` và `endInclusive`.
2. Phân biệt `IntStream.range`, `IntStream.rangeClosed`, `LongStream.range` và `LongStream.rangeClosed`.
3. Dự đoán chính xác các trường hợp cận bằng nhau, cận ngược và số âm.
4. Chọn dãy **nửa mở** để duyệt index `0` đến `length - 1`, chọn dãy **đóng** khi nghiệp vụ bao gồm giá trị cuối.
5. Kết hợp với `map`, `filter`, `mapToObj`, `sum`, `count`, `boxed`, `parallel`.
6. Phân biệt dãy có **bước 1** với dãy cần bước nhảy khác 1.
7. Tránh lỗi off-by-one, giả định range tự đếm ngược, integer overflow, thu dãy quá lớn vào bộ nhớ và dựa vào thứ tự `parallel().forEach`.
8. Biên dịch và chạy ví dụ độc lập bằng JDK 17.

## 2. Thuộc package và kiểu trả về

Cả hai phương thức là **static factory methods** nằm trên hai primitive stream interface:

| API | Kiểu tham số | Kiểu trả về | Ý nghĩa |
| --- | --- | --- | --- |
| `IntStream.range(int startInclusive, int endExclusive)` | `int, int` | `IntStream` | `start <= n < end` |
| `IntStream.rangeClosed(int startInclusive, int endInclusive)` | `int, int` | `IntStream` | `start <= n <= end` |
| `LongStream.range(long startInclusive, long endExclusive)` | `long, long` | `LongStream` | `start <= n < end` |
| `LongStream.rangeClosed(long startInclusive, long endInclusive)` | `long, long` | `LongStream` | `start <= n <= end` |

Import thường dùng:

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
~~~

Không có `DoubleStream.range(...)` hoặc `DoubleStream.rangeClosed(...)` tương đương trong API chuẩn Java 17. Với dãy giá trị `double` có bước rõ ràng, có thể tạo số thứ tự bằng `IntStream.range(...)` rồi `mapToDouble(...)`; với số thực, cần chú ý sai số biểu diễn và không nên kiểm soát điều kiện kết thúc bằng cộng dồn floating-point tùy tiện.

### Vì sao là primitive Stream?

`IntStream` giữ phần tử dạng primitive `int`, `LongStream` giữ `long`. Khác `Stream<Integer>`/`Stream<Long>`, những pipeline nguyên thủy có thể giảm boxing/unboxing và cung cấp các terminal operations số học như `sum()`, `average()`, `summaryStatistics()`.

Khi API cần object, chuyển từ primitive sang object có chủ đích:

~~~java
List<Integer> numbers = IntStream.range(1, 5)
        .boxed()
        .toList(); // [1, 2, 3, 4]
~~~

Đoạn mã đặt trong phương thức có import `java.util.List`. `boxed()` chuyển từng `int` thành `Integer` và trả `Stream<Integer>`; không cần boxing nếu pipeline chỉ tính toán tổng hoặc đếm.

## 3. `range()` — khoảng nửa mở `[start, end)`

### 3.1. Cận đầu được lấy, cận cuối bị loại

~~~java
int[] values = IntStream.range(2, 6).toArray();
System.out.println(java.util.Arrays.toString(values));
~~~

Kết quả:

~~~text
[2, 3, 4, 5]
~~~

Số `2` xuất hiện vì `startInclusive = 2`. Số `6` không xuất hiện vì `endExclusive = 6`. Có thể hiểu bằng vòng lặp truyền thống:

~~~java
for (int n = 2; n < 6; n++) {
    System.out.println(n);
}
~~~

Hai cách biểu diễn tạo cùng dãy giá trị `2, 3, 4, 5` theo chiều tăng. Với vòng `for`, từng lệnh in chạy trực tiếp; với `IntStream.range`, ta tạo nguồn rồi tùy ý xử lý bằng pipeline. Hai mảnh mã trên minh họa cùng điều kiện biên, không phải tuyên bố mọi cách thực thi đều có chi phí như nhau.

### 3.2. Vì sao khoảng nửa mở thuận tiện?

Trong Java, mảng, `List`, `String` và nhiều API xử lý đoạn chỉ số dùng **đầu bao gồm, cuối loại trừ**:

~~~text
array length = 4
index hợp lệ: 0, 1, 2, 3
IntStream.range(0, 4) --> 0, 1, 2, 3
~~~

Dùng `range(0, array.length)` giúp viết đúng ranh giới mà không phải trừ 1. Với dãy từ 0 đến `n - 1`, số phần tử là `n` nếu `n >= 0`.

Nếu `start < end` và hiệu `end - start` được tính toán không bị overflow trong miền số đang xét, số phần tử về mặt toán học là `end - start`. Nếu `start >= end`, kết quả rỗng. **Không tự tính kích thước bằng phép trừ `int` khi hai cận có thể nằm ở giới hạn cực trị** vì hiệu có thể overflow; `count()` trả `long` và tránh nhiều lỗi tính kích thước thủ công.

### 3.3. Ví dụ với số âm

~~~java
int[] values = IntStream.range(-2, 3).toArray();
System.out.println(java.util.Arrays.toString(values));
~~~

Kết quả:

~~~text
[-2, -1, 0, 1, 2]
~~~

`range` không bị giới hạn ở số dương hoặc bắt đầu bằng 0. Điều kiện là một dãy **tăng từng 1** từ cận dưới, không lấy cận trên. Dùng khi cần duyệt các độ lệch tương đối, chỉ số được điều chỉnh hoặc một miền số toán học.

## 4. `rangeClosed()` — khoảng đóng `[start, end]`

### 4.1. Cả hai cận đều có mặt

~~~java
int[] values = IntStream.rangeClosed(2, 6).toArray();
System.out.println(java.util.Arrays.toString(values));
~~~

Kết quả:

~~~text
[2, 3, 4, 5, 6]
~~~

Đây là tương đương ngữ nghĩa với:

~~~java
for (int n = 2; n <= 6; n++) {
    System.out.println(n);
}
~~~

Lưu ý rằng vòng `for` với điều kiện `<=` trên kiểu `int` **có thể overflow** nếu cận trên là `Integer.MAX_VALUE` và thân lặp cho phép biến tăng vượt giới hạn. `IntStream.rangeClosed` đã được thiết kế theo hợp đồng API để bao gồm giá trị cuối mà không yêu cầu người gọi viết phép `end + 1`. Vì vậy **không** thay `rangeClosed(a,b)` bằng `range(a,b+1)` một cách máy móc.

### 4.2. Khi nào nên dùng cận trên bao gồm?

- Lặp qua các số thứ tự từ `1` đến `n`, kể cả `n`.
- Tính tổng các số nguyên từ `1` đến `10`: `IntStream.rangeClosed(1,10).sum()` trả `55`.
- Thử nghiệm toàn bộ giá trị nguyên từ ngưỡng thấp đến ngưỡng cao, cả hai đầu mút.
- Tạo một số bảng cửu chương, mức độ hay bộ đếm với quy ước "từ A **đến** B, bao gồm B".

Ví dụ:

~~~java
int sum = IntStream.rangeClosed(1, 5).sum();
System.out.println(sum); // 15
~~~

Số phần tử trong khoảng đóng với `start <= end` là `end - start + 1` **theo toán học**. Cũng như khoảng nửa mở, tính công thức trực tiếp bằng `int` có thể overflow đối với cận rất lớn hoặc rất nhỏ.

## 5. Trường hợp cận bằng nhau, cận ngược và khoảng rỗng

Bảng đối chiếu này áp dụng cho `IntStream` và `LongStream` (với giá trị cận thích hợp):

| Lời gọi | Dãy kết quả | Vì sao |
| --- | --- | --- |
| `range(2, 6)` | `2, 3, 4, 5` | Không lấy `6` |
| `rangeClosed(2, 6)` | `2, 3, 4, 5, 6` | Có lấy `6` |
| `range(3, 3)` | Rỗng | `3 <= n < 3` không có nghiệm |
| `rangeClosed(3, 3)` | `3` | Hai cận trùng nhau và cùng được lấy |
| `range(6, 2)` | Rỗng | Cận dưới lớn hơn cận trên |
| `rangeClosed(6, 2)` | Rỗng | Không tự đếm ngược |
| `range(-2, 3)` | `-2, -1, 0, 1, 2` | Chứa số âm, 0 và số dương dưới `3` |
| `rangeClosed(-2, 3)` | `-2, -1, 0, 1, 2, 3` | Bao gồm `3` |
| `range(0, 0)` | Rỗng | Hữu ích khi kích thước đầu vào bằng 0 |
| `rangeClosed(0, 0)` | `0` | Không phù hợp nếu muốn biểu diễn 0 lần lặp |

Đặc biệt chú ý: `range(0, n)` chạy **n lần nếu n không âm**, còn `rangeClosed(0, n)` chạy **n + 1 lần** khi `n >= 0`. Đối với duyệt chỉ số mảng, dùng `rangeClosed(0, array.length)` thường tạo lỗi truy cập phần tử cuối vượt phạm vi.

### Không có bước âm

Hai factory method trên đều tạo **dãy tăng thêm 1** theo thứ tự tự nhiên. Gọi `rangeClosed(5, 1)` không tạo `5, 4, 3, 2, 1`; nó tạo Stream rỗng. Nếu cần đếm giảm, phải mô tả biến đổi hoặc dùng `IntStream.iterate` thích hợp (xem phần 10).

## 6. Chương trình Java 17 hoàn chỉnh

Chương trình minh họa khoảng nửa mở, khoảng đóng, biên bằng nhau/đảo chiều, duyệt mảng, tính tổng, bước nhảy khác 1 và việc thu kết quả từ Stream song song.

Tạo tệp **`RangeDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class RangeDemo {

    static void show(String label, IntStream values) {
        System.out.println(
                label + "=" + Arrays.toString(values.toArray()));
    }

    public static void main(String[] args) {
        show("range", IntStream.range(2, 6));
        show("rangeClosed", IntStream.rangeClosed(2, 6));
        show("same-open", IntStream.range(3, 3));
        show("same-closed", IntStream.rangeClosed(3, 3));
        show("reverse", IntStream.rangeClosed(6, 2));

        int[] scores = {4, 7, 9};
        List<String> indexed = IntStream
                .range(0, scores.length)
                .mapToObj(i -> i + ":" + scores[i])
                .toList();

        System.out.println("indexed=" + indexed);
        System.out.println(
                "sum=" + LongStream.rangeClosed(1, 10).sum());

        show("step2", IntStream.iterate(
                1, n -> n < 9, n -> n + 2));

        List<Integer> parallel = IntStream.range(0, 6)
                .parallel()
                .boxed()
                .toList();
        System.out.println("parallel=" + parallel);
    }
}
~~~

Chạy từ thư mục chứa `RangeDemo.java` với JDK 17+:

~~~bash
javac -encoding UTF-8 RangeDemo.java
java RangeDemo
~~~

**Stdout chính xác:**

~~~text
range=[2, 3, 4, 5]
rangeClosed=[2, 3, 4, 5, 6]
same-open=[]
same-closed=[3]
reverse=[]
indexed=[0:4, 1:7, 2:9]
sum=55
step2=[1, 3, 5, 7]
parallel=[0, 1, 2, 3, 4, 5]
~~~

### Diễn giải từng dòng

1. `range(2,6)` loại `6`, còn `rangeClosed(2,6)` lấy cả `6`.
2. Khi hai cận bằng `3`, khoảng nửa mở rỗng; khoảng đóng có đúng một phần tử `3`.
3. Với cận bắt đầu `6` lớn hơn cận cuối `2`, `rangeClosed` trả rỗng, không đếm lùi.
4. `range(0, scores.length)` tạo chỉ số `0,1,2`, rồi `mapToObj` dùng chỉ số để lấy giá trị và tạo chuỗi `0:4`, `1:7`, `2:9`.
5. `LongStream.rangeClosed(1,10).sum()` trả `long` với giá trị `55`.
6. `IntStream.iterate(1, n -> n < 9, n -> n+2)` tạo `1,3,5,7`: dùng khi bước nhảy khác `1`.
7. `parallel()` cho phép pipeline được thực thi song song nhưng nguồn `range(0,6)` vẫn có **encounter order**. `boxed().toList()` giữ thứ tự này trong kết quả, nên in từ `0` tới `5`.

Chương trình dùng dãy nhỏ để không tạo áp lực bộ nhớ. Các cách gọi `show` tiêu thụ Stream đúng một lần bằng `toArray()`; không dùng lại cùng Stream đã được tiêu thụ.

## 7. Duyệt chỉ số mảng và danh sách bằng `range()`

### 7.1. Đọc phần tử theo chỉ số mảng

~~~java
String[] names = {"An", "Binh", "Chi"};

List<String> numbered = IntStream.range(0, names.length)
        .mapToObj(i -> i + " - " + names[i])
        .toList();

System.out.println(numbered);
~~~

Kết quả:

~~~text
[0 - An, 1 - Binh, 2 - Chi]
~~~

Đây là **mảnh mã trong phương thức** có import `java.util.List` và `IntStream`. Đầu vào `names.length = 3`, nên `range(0,3)` tạo đúng `0,1,2`. Không có chỉ số `3`; vì vậy không gây `ArrayIndexOutOfBoundsException` từ cận tạo dãy.

Nếu mảng rỗng, `range(0,0)` trả Stream rỗng và `toList()` trả danh sách rỗng. Đây là một ưu điểm của khoảng nửa mở trong xử lý collections.

### 7.2. Duyệt List khi thực sự cần chỉ số

~~~java
List<String> items = List.of("red", "green", "blue");

List<String> labels = IntStream.range(0, items.size())
        .mapToObj(i -> i + "=" + items.get(i))
        .toList();

System.out.println(labels);
~~~

Kết quả:

~~~text
[0=red, 1=green, 2=blue]
~~~

Nếu chỉ cần giá trị, `items.stream().map(...)` thường rõ hơn; dùng `IntStream.range` khi **chỉ số có ý nghĩa** (đánh số thứ tự, ghép hai cấu trúc cùng kích thước, kiểm tra vị trí). Với một số `List` không có truy cập ngẫu nhiên hiệu quả như `LinkedList`, lặp lại `get(i)` có thể tốn chi phí lớn hơn duyệt tuần tự. Đừng coi kiểu viết Stream là nhanh hơn vòng lặp theo mặc định.

### 7.3. Những trường hợp có giá trị của `mapToObj`

Với `IntStream`, `mapToObj` biến mỗi `int` thành một đối tượng; `boxed()` chỉ chuyển `int` thành `Integer`. So sánh:

~~~java
List<Integer> indices = IntStream.range(0, 3)
        .boxed()
        .toList();

List<String> tags = IntStream.range(0, 3)
        .mapToObj(i -> "item-" + i)
        .toList();
~~~

`indices` nhận `[0,1,2]`, còn `tags` nhận `["item-0","item-1","item-2"]`. Nếu mục tiêu chỉ là tính toán số, dùng trực tiếp `IntStream` để tránh tạo object không cần thiết.

## 8. Khi chọn `rangeClosed()` thay vì `range()`

### 8.1. Tính tổng nguyên trong một khoảng bao gồm cận cuối

~~~java
int total = IntStream.rangeClosed(1, 10).sum();
System.out.println(total); // 55
~~~

Cách này hợp lý khi yêu cầu toán học là tổng từ `1` đến **cả `10`**. Nếu dùng `range(1,10)` sẽ chỉ cộng `1..9` và trả `45`, sai do off-by-one.

### 8.2. Bảng cửu chương

~~~java
int multiplier = 7;
List<String> table = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> multiplier + " x " + n
                + " = " + (multiplier * n))
        .toList();

table.forEach(System.out::println);
~~~

Kết quả:

~~~text
7 x 1 = 7
7 x 2 = 14
7 x 3 = 21
~~~

Đây là đoạn code trong method. `multiplier` là local effectively final nên lambda được phép sử dụng. Nếu muốn đến `10`, đổi cận `3` thành `10`.

### 8.3. Khi cần cả cận cuối nhưng muốn dùng khoảng nửa mở

Trong nhiều thuật toán chia đoạn, khoảng nửa mở hợp lý hơn: hai đoạn liên tiếp `[0,5)` và `[5,10)` không chồng nhau, dễ hợp nhất và tính kích thước. Không nhất thiết phải dùng `rangeClosed` chỉ vì câu mô tả có chữ "đến"; phải hiểu dữ liệu **có bao gồm điểm cuối hay không**.

Ví dụ, "các chỉ số hợp lệ của mảng có length = 10" nên dùng `range(0,10)`, dù thường nói "từ 0 đến 9". Ngược lại, "các số nguyên từ 1 đến 10, bao gồm 10" nên dùng `rangeClosed(1,10)`.

## 9. `LongStream` và các giới hạn kiểu số

### 9.1. Dãy `long`

~~~java
long[] ids = LongStream.range(100L, 104L).toArray();
System.out.println(java.util.Arrays.toString(ids));
~~~

Kết quả:

~~~text
[100, 101, 102, 103]
~~~

`LongStream.rangeClosed(100L,104L)` còn có `104`. Dùng `LongStream` khi giá trị cần biểu diễn vượt miền `int` (−2^31 đến 2^31−1) hoặc nghiệp vụ sử dụng `long` cho ID/offset/timestamp theo đơn vị nguyên. Chỉ đổi `IntStream` thành `LongStream` không thay đổi ngữ nghĩa cận bao gồm/loại trừ.

### 9.2. `rangeClosed` an toàn về điểm cuối, không phải về độ lớn pipeline

~~~java
long max = Long.MAX_VALUE;
long[] tail = LongStream.rangeClosed(max - 1, max)
        .toArray();

System.out.println(java.util.Arrays.toString(tail));
~~~

Kết quả:

~~~text
[9223372036854775806, 9223372036854775807]
~~~

`rangeClosed` không yêu cầu viết `max + 1`, vốn sẽ overflow về `Long.MIN_VALUE`. Tuy nhiên, **không bao giờ** gọi `toArray()`, `boxed().toList()` hoặc `forEach(...)` một cách tùy tiện trên một miền khổng lồ: Stream chỉ giúp biểu diễn dãy, không làm biến mất chi phí xử lý và lưu trữ.

### 9.3. Đếm phần tử và overflow

`count()` trả `long`, không phải `int`:

~~~java
long count = IntStream.rangeClosed(1, 5).count();
System.out.println(count); // 5
~~~

Một khoảng `int` có thể có hơn `Integer.MAX_VALUE` phần tử. Ví dụ về mặt toán học `rangeClosed(Integer.MIN_VALUE,Integer.MAX_VALUE)` chứa **2^32 phần tử**, không thể đếm đúng bằng biến `int`. Dùng kết quả kiểu `long` khi cần số lượng phần tử. Tuy nhiên, đừng tạo những collection vật hóa hàng tỷ giá trị chỉ để minh họa công thức.

Với `LongStream` có cận cực đại, ngay cả số phần tử lý thuyết cũng có thể vượt phạm vi biểu diễn của `long`. Không suy luận rằng `count()`, `sum()` hoặc mọi thuật toán đều thể hiện chính xác một miền `long` rộng tùy ý; cần xác định miền hợp lệ của ứng dụng và có thể dùng `BigInteger` hoặc chia nhỏ phạm vi nếu bài toán đòi đếm chính xác số lượng cực lớn.

### 9.4. `sum()` và overflow

`IntStream.sum()` trả `int`; `LongStream.sum()` trả `long`. Không có bảo đảm toán học “không tràn số”. Ví dụ tổng `1..100000` vượt giới hạn `int`:

~~~java
long sum = IntStream.rangeClosed(1, 100_000)
        .mapToLong(n -> n)
        .sum();

System.out.println(sum); // 5000050000
~~~

Ở đây `mapToLong` giúp tính bằng `long`; kết quả `5,000,050,000` không vừa kiểu `int`. Với các tổng `long` rất lớn, vẫn phải nghĩ đến overflow của `long` hoặc dùng `BigInteger`/phép toán chính xác theo miền nghiệp vụ.

## 10. Dãy bước nhảy khác 1 hoặc đếm ngược

`range` và `rangeClosed` luôn tiến **mỗi lần 1 đơn vị**. Chúng không nhận đối số `step`. Nếu cần số chẵn, số lẻ hoặc dãy giảm, có hai phương án cơ bản.

### 10.1. Biến đổi hoặc lọc một khoảng

~~~java
int[] evens = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .toArray();

System.out.println(java.util.Arrays.toString(evens));
~~~

Kết quả:

~~~text
[2, 4, 6, 8, 10]
~~~

Cách này dễ hiểu và hợp lý với miền nhỏ. Tuy nhiên, nó tạo/xét các phần tử của dãy gốc rồi loại những giá trị không cần thiết. Với bước nhảy lớn hoặc miền rộng, có thể hiệu quả hơn khi tạo đúng giá trị mong muốn.

### 10.2. `IntStream.iterate` có predicate và bước nhảy

Từ Java 9, `IntStream.iterate(seed, hasNext, next)` có thể tạo dãy với điều kiện và quy luật cập nhật:

~~~java
int[] odds = IntStream.iterate(1,
        n -> n < 9,
        n -> n + 2)
        .toArray();

System.out.println(java.util.Arrays.toString(odds));
~~~

Kết quả:

~~~text
[1, 3, 5, 7]
~~~

Dãy giảm:

~~~java
int[] backward = IntStream.iterate(5,
        n -> n >= 1,
        n -> n - 1)
        .toArray();

System.out.println(java.util.Arrays.toString(backward));
~~~

Kết quả:

~~~text
[5, 4, 3, 2, 1]
~~~

Cần **bảo đảm predicate cuối cùng dừng lại**. Nếu bước cập nhật gặp overflow, điều kiện có thể thay đổi ngoài dự kiến hoặc không dừng như mong muốn; kiểm soát các giới hạn cực trị. Đối với bài toán giảm tuyến tính đơn giản, vòng `for` nhiều khi vẫn dễ đọc và an toàn hơn.

### 10.3. Tạo dãy có bước `k` bằng ánh xạ chỉ số

~~~java
int start = 10;
int step = 3;
int count = 4;

int[] values = IntStream.range(0, count)
        .map(i -> start + i * step)
        .toArray();

System.out.println(java.util.Arrays.toString(values));
~~~

Kết quả:

~~~text
[10, 13, 16, 19]
~~~

Mã này biểu diễn `count` vị trí rồi ánh xạ thành giá trị nghiệp vụ; thuận tiện khi số lượng phần tử biết trước. Nhưng phép `start + i * step` có thể overflow kiểu `int`; với số lớn cần dùng `long`, `Math.multiplyExact`/`Math.addExact` hoặc giới hạn đầu vào phù hợp.

## 11. Kết hợp `range` với các thao tác của primitive Stream

### 11.1. `filter` và `map`

~~~java
int[] squares = IntStream.rangeClosed(1, 6)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toArray();

System.out.println(java.util.Arrays.toString(squares));
~~~

Kết quả:

~~~text
[4, 16, 36]
~~~

Thứ tự: tạo `1..6`, giữ `2,4,6`, bình phương thành `4,16,36`. Các phép toán `filter`/`map` trong ví dụ xử lý kiểu `int`, chưa cần boxing.

### 11.2. `sum`, `average`, `min`, `max`

~~~java
int sum = IntStream.range(1, 5).sum();      // 10
long n = IntStream.range(1, 5).count();     // 4
double average = IntStream.range(1, 5)
        .average().orElse(0.0);             // 2.5
~~~

Đây là các **pipeline độc lập**, mỗi dòng tạo Stream mới. `average()` trả `OptionalDouble` vì Stream rỗng không có giá trị trung bình. Việc chọn `orElse(0.0)` chỉ là chính sách của ví dụ; không có nghĩa trung bình một tập rỗng về toán học bằng `0`.

Với `min()`/`max()`, kết quả là `OptionalInt` hoặc `OptionalLong`; phải xử lý đúng trường hợp khoảng rỗng.

### 11.3. `summaryStatistics`

~~~java
IntSummaryStatistics stats =
        IntStream.rangeClosed(1, 5).summaryStatistics();

System.out.println(stats.getCount()); // 5
System.out.println(stats.getMin());   // 1
System.out.println(stats.getMax());   // 5
~~~

Mảnh mã cần import `java.util.IntSummaryStatistics`. `summaryStatistics` hữu ích khi cần nhiều thống kê trên cùng pipeline; không phải dùng lại một Stream đã tiêu thụ để lần lượt gọi `sum()` rồi `max()`.

### 11.4. Không tái sử dụng Stream đã tiêu thụ

~~~java
IntStream stream = IntStream.range(1, 5);
long count = stream.count();
// int sum = stream.sum(); // Sai: stream đã được tiêu thụ.
~~~

Muốn tính hai kết quả, tạo hai nguồn Stream mới hoặc lấy `summaryStatistics()`. Sau khi terminal operation chạy, không gọi thêm terminal/intermediate operation trên cùng một Stream như thể nó là danh sách có thể duyệt nhiều lần.

### 11.5. Lazy execution và `count()`

`range` tạo nguồn Stream có thể được xử lý theo pipeline lazy. Các intermediate operations như `map` và `filter` không nhất thiết chạy ngay lúc khai báo. `count()` hoặc `toArray()` là terminal operations.

Tuy nhiên, `count()` có thể được tối ưu hóa để tính số phần tử trực tiếp khi kích thước nguồn đã biết và các bước trung gian không thay đổi số lượng phần tử. **Không dựa vào side effect trong `map` để đếm lần gọi lambda**; đây là anti-pattern vì tối ưu hóa có thể bỏ việc thực thi những phép biến đổi không cần để tính kết quả.

## 12. `parallel()` và thứ tự

`IntStream.range` và `LongStream.range` tạo dãy có thứ tự tăng tự nhiên. Có thể gọi `parallel()`:

~~~java
List<Integer> numbers = IntStream.range(0, 6)
        .parallel()
        .boxed()
        .toList();

System.out.println(numbers); // [0, 1, 2, 3, 4, 5]
~~~

`parallel()` thay đổi chiến lược thực thi, **không xóa encounter order** vốn có của nguồn. `toList()` thu kết quả theo encounter order khi Stream có thứ tự.

Nhưng:

~~~java
IntStream.range(0, 6)
        .parallel()
        .forEach(System.out::println);
~~~

**Không ghi một stdout cố định cho đoạn này.** Với Stream song song, `forEach` không bảo đảm thứ tự thực hiện side effect; các số có thể in khác thứ tự dãy. Nếu nhất thiết phải thực hiện hành động theo encounter order, dùng `forEachOrdered`, đồng thời cân nhắc chi phí áp đặt thứ tự.

Dùng Stream song song chỉ khi có bằng chứng lợi ích; với khoảng ngắn, chi phí chia việc có thể lớn hơn lợi ích. Tránh mutate một `ArrayList` chung trong `parallel().forEach(list::add)`; nếu muốn thu kết quả, dùng collector hoặc `toList()` phù hợp.

## 13. Những lỗi phổ biến cần tránh

| Lỗi | Hệ quả | Cách đúng |
| --- | --- | --- |
| Dùng `range(1,10)` để tính tổng 1 đến 10 gồm 10 | Bỏ sót số 10 | Dùng `rangeClosed(1,10)` |
| Dùng `rangeClosed(0,array.length)` để truy cập mảng | Phần tử cuối có index ngoài phạm vi | `range(0,array.length)` |
| Tưởng `rangeClosed(5,1)` đếm ngược | Dãy rỗng | Dùng `iterate` hoặc vòng `for` phù hợp |
| Dùng `range(0,0)` rồi kỳ vọng một giá trị 0 | Stream rỗng | `rangeClosed(0,0)` nếu muốn một số 0 |
| Tự viết `range(start,end+1)` để bao gồm end | Có thể overflow khi end cực đại | Dùng `rangeClosed(start,end)` |
| Tính độ dài bằng `int length = end-start+1` với cận cực trị | Tràn `int` | `count()` kiểu `long` khi miền phù hợp, hoặc tính bằng kiểu đủ rộng |
| Gọi `toArray()` cho miền hàng tỷ phần tử | Dùng quá nhiều bộ nhớ | Giới hạn kích thước hoặc xử lý tổng hợp |
| Giả định `IntStream.sum()` không overflow | Tổng có thể sai | Chuyển sang `long` hoặc kiểu số thích hợp |
| Muốn bước 2 nhưng nghĩ `range(start,end,2)` tồn tại | Không có overload step | `iterate` hoặc `map` chỉ số |
| Sử dụng lại một Stream sau `count()` | Lỗi lifecycle Stream | Tạo nguồn mới hoặc dùng thống kê |
| Dựa vào `parallel().forEach` để in theo thứ tự | Thứ tự side effect không được bảo đảm | `forEachOrdered` hoặc `toList()` |
| Dùng index trên `LinkedList` bằng `get(i)` liên tục | Có thể chậm | Duyệt trực tiếp bằng Iterator/Stream |
| Dùng `boxed()` không cần thiết trong tính toán số | Tạo object trung gian | Giữ primitive pipeline |
| Nghĩ `range` tự thực hiện ngay khi khai báo | Stream pipeline lazy | Gọi terminal operation khi cần |
| Dùng local biến đổi trong lambda để cộng tổng | Vi phạm effectively final hoặc side effect | Dùng `sum()`/`reduce` |

### Cảnh báo đặc biệt với cận cực trị

Ví dụ:

~~~java
int last = Integer.MAX_VALUE;
int[] tail = IntStream.rangeClosed(last - 1, last)
        .toArray();
~~~

Đây là dãy hợp lệ chỉ gồm hai số cuối của miền `int`. Còn `IntStream.range(last - 1, last + 1)` **không tương đương** vì `last + 1` overflow.

Tương tự, `LongStream.rangeClosed(Long.MAX_VALUE - 1, Long.MAX_VALUE)` có hai phần tử cuối của miền `long`; đừng thay bằng `range(..., Long.MAX_VALUE + 1)`. Với các khoảng có số phần tử cực lớn, việc tính tổng/đếm/vật hóa vẫn cần xem xét giới hạn dữ liệu, không nên nhầm “factory hợp lệ” với “mọi terminal operation đều đủ tài nguyên”.

## 14. Bài tập có hướng dẫn

### Bài 1 — Đọc cận trên

Dự đoán:

~~~java
System.out.println(
    java.util.Arrays.toString(IntStream.range(4, 8).toArray())
);
System.out.println(
    java.util.Arrays.toString(IntStream.rangeClosed(4, 8).toArray())
);
~~~

**Đáp án:** `[4, 5, 6, 7]` và `[4, 5, 6, 7, 8]`. Giải thích bằng điều kiện `n < 8` đối với `range` và `n <= 8` đối với `rangeClosed`.

### Bài 2 — Khoảng rỗng

Kiểm tra `range(5,5)`, `rangeClosed(5,5)`, `range(7,2)` và `rangeClosed(7,2)`. Trình bày số phần tử mỗi Stream và giải thích tại sao kết quả không phải một dãy đếm ngược.

**Đáp án:** lần lượt `0, 1, 0, 0` phần tử.

### Bài 3 — Lấy index an toàn

Cho `int[] data = {9, 3, 5, 8};`. Dùng `IntStream.range(0, data.length).mapToObj(i -> i + ":" + data[i]).toList()` để tạo `[0:9,1:3,2:5,3:8]`. Thử mảng rỗng và giải thích vì sao không xảy ra truy cập index sai.

### Bài 4 — Tổng số nguyên bao gồm cận cuối

Viết một pipeline tính `1 + 2 + ... + 100` bằng `rangeClosed(1,100)`. Kết quả `5050`. Thử chuyển thành `range(1,100)` và chỉ ra số `100` bị bỏ.

### Bài 5 — Bước nhảy

Tạo dãy `3,6,9,12` bằng `IntStream.rangeClosed(1,4).map(n -> n*3)` và bằng `IntStream.iterate(3, n -> n <= 12, n -> n+3)`. So sánh cách diễn đạt khi biết số phần tử và khi biết điều kiện dừng.

### Bài 6 — `LongStream`

Tạo các giá trị `1_000_000_000_000L` đến `1_000_000_000_003L` bằng `LongStream.rangeClosed`. Dùng `count()` để kiểm tra có 4 phần tử. Giải thích vì sao giá trị này không vừa `int`.

### Bài 7 — Overflow khi cộng

Tính tổng `1..100_000` bằng `IntStream.rangeClosed(1,100_000).sum()` và bằng `mapToLong(n -> n).sum()`. Giải thích vì sao chỉ bản `long` cho kết quả toán học `5_000_050_000`.

### Bài 8 — Song song và thứ tự

So sánh `IntStream.range(0,10).parallel().boxed().toList()` với `IntStream.range(0,10).parallel().forEach(System.out::println)`. Giải thích vì sao List có thứ tự đáng tin, còn các dòng in từ `forEach` không có thứ tự bắt buộc.

### Bài 9 — Duyệt số âm

Tạo `[-3,-2,-1,0,1]` bằng `range(-3,2)` và `[-3,-2,-1,0,1,2]` bằng `rangeClosed(-3,2)`. Kiểm tra số phần tử và giá trị cuối.

### Bài 10 — Từ bài toán sang lựa chọn API

Cho ba yêu cầu: (a) duyệt toàn bộ index mảng độ dài `n`, (b) đánh số thứ tự người chơi từ `1` đến `n`, (c) tạo các số lẻ từ `1` đến `19`. Hãy chọn một trong `range`, `rangeClosed`, `iterate` hoặc `map` chỉ số; giải thích cận cuối và lý do.

## 15. Checklist trước khi dùng `range`

1. Cần giá trị cận cuối hay không? Nếu **không**, `range`; nếu **có**, `rangeClosed`.
2. Cận bắt đầu và cận cuối có bằng nhau hay bị đảo không? Dự đoán kết quả rỗng/một phần tử.
3. Có đang duyệt index mảng/List không? Thông thường `range(0,length)` đúng hơn.
4. Dãy có phải tăng từng `1` không? Nếu không, cân nhắc `iterate` hoặc `map`.
5. Dữ liệu cần `int` hay `long`? Có nguy cơ cận hoặc phép tính vượt miền không?
6. Có đang tính kích thước bằng công thức `int` có thể overflow không? Kiểm tra kiểu số của kết quả.
7. Terminal operation có thể tạo lượng dữ liệu khổng lồ trong bộ nhớ không?
8. Có cần giá trị kết quả hay chỉ cần side effect? Ưu tiên các phép `sum`/`map`/`toList` khi có dữ liệu đầu ra.
9. Có dùng `parallel` không? Đừng dựa vào thứ tự gọi `forEach` song song.
10. Có dùng lại Stream đã tiêu thụ hay tính toán quá nhiều lần trên cùng nguồn không?
11. Các ca biên `0`, cận bằng nhau, cận âm, `Integer.MAX_VALUE` và `Long.MAX_VALUE` đã được kiểm tra phù hợp chưa?

## 16. Tổng kết và tài liệu tham khảo

**`range(startInclusive,endExclusive)` tạo dãy tăng từng 1 với cận trái bao gồm và cận phải loại trừ. `rangeClosed(startInclusive,endInclusive)` tạo dãy tăng từng 1 có cả hai cận.** Khi hai cận bằng nhau, `range` rỗng còn `rangeClosed` gồm một phần tử; khi cận bắt đầu lớn hơn cận cuối, cả hai rỗng và không tự đếm ngược.

Dùng `IntStream.range(0,array.length)` cho index; dùng `IntStream.rangeClosed(1,n)` cho các số từ 1 đến n có cả n. Khi giá trị nguyên vượt `int`, dùng `LongStream` phù hợp, nhưng vẫn phải kiểm soát kích thước, khả năng tràn số khi cộng và bộ nhớ khi materialize dữ liệu. Với bước nhảy khác 1, dùng `iterate` hoặc biến đổi chỉ số; không có overload `range(start,end,step)`.

**Tài liệu chính thức:** Javadoc Java SE 17 `java.util.stream.IntStream` và `java.util.stream.LongStream` (các phương thức `range`, `rangeClosed`, `iterate`, `mapToObj`, `sum`, `count`), `java.util.stream.BaseStream` và `java.util.stream.Stream` (thứ tự, pipeline và terminal operations).
