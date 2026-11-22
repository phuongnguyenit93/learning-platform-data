# Tạo dãy có điều kiện dừng bằng Stream.iterate ba tham số

Trong Java Stream API, `Stream.iterate(seed, hasNext, next)` tạo một dãy phần tử bằng cách **bắt đầu từ giá trị ban đầu**, **kiểm tra điều kiện được phép tiếp tục**, rồi **tính phần tử kế tiếp**. Đây là cách diễn đạt khai báo cho nhiều vòng lặp có điều kiện dừng mà không cần tự duy trì danh sách kết quả. Phương thức ba tham số được bổ sung từ **Java 9**.

Bài nằm trong chương **Dãy số và Stream vô hạn** của module **JAVA_STREAM_API**. Mục tiêu là kết hợp kiểu nguồn sinh dãy này với các pipeline lazy như `filter`, `map`, `reduce` và `collect`; hiểu thời điểm thực thi, trạng thái, chi phí tài nguyên và lý do không nên mặc định biến dãy phụ thuộc tuần tự thành parallel stream. Những kiến thức nền cũng giúp đọc các chủ đề nâng cao như `Spliterator`, grouping, collector tùy chỉnh và Stream Gatherers.

## 1. Cú pháp và ý nghĩa của ba tham số

Khai báo đầy đủ trong `java.util.stream.Stream`:

```java
public static <T> Stream<T> iterate(
        T seed,
        Predicate<? super T> hasNext,
        UnaryOperator<T> next)
```

| Tham số | Vai trò | Ví dụ |
|---|---|---|
| `seed` | Phần tử đầu tiên **ứng viên** được phát | `0` |
| `hasNext` | Hàm nhận một phần tử ứng viên, trả `true` nếu được đưa vào Stream | `i -> i < 5` |
| `next` | Hàm tính phần tử ứng viên sau từ phần tử hiện tại | `i -> i + 1` |

`Predicate<T>` và `UnaryOperator<T>` đều là functional interface trong `java.util.function`. `Predicate` đưa ra câu trả lời đúng/sai; `UnaryOperator` là một hàm nhận và trả về **cùng kiểu T**. Vì thế, `iterate` phù hợp cả với dãy số, ngày tháng và trạng thái bất biến của thuật toán.

Ý nghĩa cơ bản giống vòng `for`:

```java
// Dạng vòng lặp:
for (int i = 0; i < 5; i++) {
    System.out.println(i);
}

// Dạng Stream, từ Java 9:
Stream.iterate(0, i -> i < 5, i -> i + 1)
        .forEach(System.out::println);
```

Hai đoạn cùng in ra `0`, `1`, `2`, `3`, `4` (mỗi số một dòng), nếu chạy tuần tự như ví dụ.

### 1.1. Thứ tự đánh giá

Về mặt logic, các phần tử được quyết định như sau:

```text
seed = 0
  |
  v
hasNext(0)? -- false --> KẾT THÚC
  | true
  v
phát 0 --> next(0) = 1
                 |
                 v
             hasNext(1)? -- false --> KẾT THÚC
                 | true
                 v
             phát 1 --> next(1) = 2 --> ...
```

Với lời gọi `Stream.iterate(0, i -> i < 5, i -> i + 1)`, ta có dãy `0, 1, 2, 3, 4`. Giá trị `5` được dùng để **kiểm tra điều kiện dừng**, nhưng **không xuất hiện trong kết quả**.

Những tính chất cần nhớ:

1. `hasNext` được kiểm tra **trước khi** phần tử ứng viên được phát. Nếu `hasNext.test(seed)` là `false` ngay lần đầu, Stream rỗng.
2. `next` mô tả cách tính ứng viên tiếp theo; những phần tử phát ra theo chuỗi kết quả áp dụng `next` lặp lại.
3. Khi gặp ứng viên đầu tiên không thỏa `hasNext`, dãy dừng; ứng viên đó không được phát.
4. Stream tạo từ `iterate` là **có thứ tự gặp phần tử** (*encounter order*) và ban đầu là **tuần tự**. Không nên coi nó là tập phần tử độc lập có thể lấy theo vị trí tùy ý.
5. Cả `hasNext` lẫn `next` nên không can thiệp vào nguồn/biến trạng thái dùng chung (*non-interfering*) và không dựa vào tác dụng phụ (*stateless* theo nghĩa của hành vi lambda trong Stream).

Điều kiện dừng phụ thuộc vào **giá trị ứng viên**, chứ không phải “chạy đúng N vòng” như một bộ đếm ẩn. Muốn đúng N phần tử, hãy thiết kế seed, predicate và next sao cho giới hạn đó được biểu diễn rõ ràng.

## 2. Bắt đầu với dãy số nguyên hữu hạn

### 2.1. Cận trên không bao gồm giá trị cuối

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class IterateNumbers {
    public static void main(String[] args) {
        List<Integer> numbers = Stream.iterate(
                        0,          // seed
                        i -> i < 6, // hasNext: kiểm tra trước khi phát
                        i -> i + 2) // next: tăng 2
                .collect(Collectors.toList());

        System.out.println(numbers); // [0, 2, 4]
    }
}
```

Ở đây `6` là ranh giới **loại trừ**: `0`, `2`, `4` được nhận, còn `6` bị kiểm tra và loại bỏ. Khi viết `i -> i < endExclusive`, tên `endExclusive` làm rõ quy ước cận.

### 2.2. Bao gồm cận trên

```java
List<Integer> numbers = Stream.iterate(
                1,
                i -> i <= 5, // bao gồm 5
                i -> i + 1)
        .collect(Collectors.toList());

System.out.println(numbers); // [1, 2, 3, 4, 5]
```

Nếu `seed` đã nằm ngoài miền được chấp nhận:

```java
long count = Stream.iterate(
                10,
                i -> i < 5,
                i -> i + 1)
        .count();

System.out.println(count); // 0
```

Khi đó `hasNext(10)` là `false`, không có phần tử nào được phát; không cần gọi hàm `next` để tạo phần tử thuộc dãy.

### 2.3. Dãy giảm và bước nhảy tùy ý

```java
List<Integer> countdown = Stream.iterate(
                10,
                n -> n >= 0,
                n -> n - 3)
        .collect(Collectors.toList());

System.out.println(countdown); // [10, 7, 4, 1]
```

`next` không bắt buộc cộng một. Nó có thể trừ một số, nhân một hằng số hoặc tính trạng thái mới. Tuy nhiên, **predicate phải phù hợp với chiều thay đổi**. Với dãy giảm, điều kiện kiểu `n -> n <= 10` sẽ không bảo đảm dừng vì mỗi giá trị nhỏ hơn vẫn thỏa nó.

## 3. Kết hợp nguồn iterate với pipeline lazy

`iterate` tạo **nguồn** của pipeline. Các thao tác trung gian như `filter`, `map` không cần tạo danh sách tạm; pipeline chỉ thực sự đi vào quá trình duyệt khi chạy thao tác kết thúc như `collect`, `sum`, `count` hoặc `findFirst`.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> cubesOfEvenNumbers = Stream.iterate(
                1,
                i -> i <= 10,
                i -> i + 1)
        .filter(i -> i % 2 == 0)
        .map(i -> i * i * i)
        .collect(Collectors.toList());

System.out.println(cubesOfEvenNumbers);
// [8, 64, 216, 512, 1000]
```

Ở đây:

- `iterate` lần lượt tạo các ứng viên từ 1 đến 10;
- `filter` chỉ giữ số chẵn;
- `map` lập phương từng số giữ lại;
- `collect` là thao tác kết thúc tạo `List`.

**Điều kiện dừng đặt ở đâu?** Predicate trong `iterate` kiểm tra từng phần tử **trước** các bước `filter` và `map`. Ví dụ, dù `filter` bỏ đi toàn bộ số lẻ, `hasNext` vẫn xét cả các số lẻ để biết khi nào dừng. Do đó, không thể thay đổi điều kiện sinh dãy bằng cách mong `filter` “ngăn nguồn sinh tiếp”.

### 3.1. Thao tác kết thúc có thể dừng sớm

`findFirst`, `anyMatch` và `limit` có thể làm pipeline không cần duyệt hết nguồn:

```java
Optional<Integer> firstMultipleOfSeven =
        Stream.iterate(1, n -> n <= 1000, n -> n + 1)
                .filter(n -> n % 7 == 0)
                .findFirst();

System.out.println(firstMultipleOfSeven.orElse(-1)); // 7
```

Ví dụ cần `import java.util.Optional;`. Sau khi tìm thấy phần tử phù hợp đầu tiên, xử lý có thể kết thúc sớm; chương trình không cần gom tất cả 1.000 phần tử. Không gắn tác dụng phụ như ghi log bắt buộc trong `hasNext` hay `next` rồi giả định số lần thực thi chính xác: Stream API có quyền tối ưu và các toán tử ngắn mạch có thể thay đổi số phần tử thực sự được yêu cầu.

## 4. Ví dụ thực tế: tạo lịch ngày theo quy tắc dừng

Không phải dãy nào cũng là số nguyên. `LocalDate` là kiểu giá trị bất biến, có `plusDays` trả về đối tượng ngày mới, rất phù hợp với cách dùng `iterate`.

```java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DailySchedule {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2026, 11, 16);
        LocalDate endInclusive = LocalDate.of(2026, 11, 20);

        List<LocalDate> days = Stream.iterate(
                        start,
                        date -> !date.isAfter(endInclusive),
                        date -> date.plusDays(1))
                .collect(Collectors.toList());

        System.out.println(days);
        // [2026-11-16, 2026-11-17, 2026-11-18,
        //  2026-11-19, 2026-11-20]
    }
}
```

Diễn giải: bắt đầu từ `start`, tiếp tục khi ngày ứng viên **không sau** `endInclusive`, và tăng một ngày sau mỗi bước. Nếu `start` sau `endInclusive`, kết quả là danh sách rỗng.

Đổi bước nhảy thành `date.plusWeeks(1)` sẽ tạo lịch theo tuần. Có thể nối `filter(date -> date.getDayOfWeek().getValue() <= 5)` để chỉ giữ ngày làm việc từ thứ Hai đến thứ Sáu. Lưu ý `filter` loại ngày cuối tuần khỏi **kết quả**, nhưng việc duyệt ứng viên vẫn tăng từng ngày nếu `next` là `plusDays(1)`.

## 5. So sánh ba cách tạo dãy

### 5.1. iterate hai tham số và ba tham số

`Stream.iterate(seed, next)` có từ Java 8 và **tự nó tạo nguồn vô hạn**, trừ trường hợp pipeline dùng các toán tử dừng sớm hoặc gặp lỗi. `Stream.iterate(seed, hasNext, next)` từ Java 9 có thêm predicate để ràng buộc việc sinh phần tử.

```java
// Java 8+: nguồn vô hạn, giới hạn đầu ra bằng limit.
List<Integer> firstFiveA = Stream.iterate(0, i -> i + 1)
        .limit(5)
        .collect(Collectors.toList());

// Java 9+: nguồn hữu hạn dựa trên giá trị ứng viên.
List<Integer> firstFiveB = Stream.iterate(
                0,
                i -> i < 5,
                i -> i + 1)
        .collect(Collectors.toList());

System.out.println(firstFiveA); // [0, 1, 2, 3, 4]
System.out.println(firstFiveB); // [0, 1, 2, 3, 4]
```

Hai kết quả trên giống nhau nhưng ý định khác nhau:

- `limit(5)` trả **tối đa 5 phần tử** bất kể giá trị của chúng; hữu ích khi cần một số lượng cố định từ một nguồn về bản chất có thể sinh mãi.
- `hasNext` dừng ở **ứng viên đầu tiên không thỏa điều kiện**; phù hợp khi miền giá trị hay trạng thái nghiệp vụ quyết định điểm dừng.

Chẳng hạn, với bước nhảy `i -> i + 2`, `iterate(0, i -> i < 5, i -> i + 2)` cho `[0, 2, 4]`, còn `iterate(0, i -> i + 2).limit(5)` cho `[0, 2, 4, 6, 8]`.

### 5.2. iterate ba tham số và takeWhile

Java 9 cũng bổ sung `takeWhile` để lấy tiền tố liên tục thỏa một predicate từ Stream có thứ tự:

```java
// Kiểm tra ngay tại nguồn.
Stream<Integer> a = Stream.iterate(
        0, i -> i < 5, i -> i + 1);

// Lấy tiền tố từ nguồn được tạo bởi iterate hai tham số.
Stream<Integer> b = Stream.iterate(0, i -> i + 1)
        .takeWhile(i -> i < 5);
```

Với ví dụ này, cả hai cho cùng `0, 1, 2, 3, 4`. Tuy nhiên, `takeWhile` là **thao tác trung gian**, dùng được với các nguồn Stream khác và hoạt động theo encounter order khi nguồn có thứ tự. `hasNext` thuộc **cách xây dựng nguồn** `iterate`.

Đặc biệt, `takeWhile` trên Stream **không có encounter order** không bảo đảm trả về “tiền tố” có ý nghĩa như trên một danh sách có thứ tự. Đừng dựa vào kết quả ổn định trong trường hợp đó.

### 5.3. iterate và IntStream.range / rangeClosed

Khi chỉ cần các số nguyên liên tiếp, `IntStream.range` hoặc `rangeClosed` thường ngắn gọn và hiệu quả hơn:

```java
import java.util.stream.IntStream;

int sumExclusive = IntStream.range(1, 6).sum();       // 1+2+3+4+5 = 15
int sumInclusive = IntStream.rangeClosed(1, 5).sum(); // 15
```

| Bài toán | Cách diễn đạt ưu tiên |
|---|---|
| Số nguyên liên tiếp từ 0 đến 99 | `IntStream.range(0, 100)` |
| Số nguyên liên tiếp từ 1 đến 100, gồm 100 | `IntStream.rangeClosed(1, 100)` |
| Số tăng cách 3, dừng trước 50 | `IntStream.iterate(0, n -> n < 50, n -> n + 3)` |
| Các ngày từ ngày A đến B | `Stream.iterate(start, day -> !day.isAfter(end), day -> day.plusDays(1))` |
| Lấy 10 phần tử đầu của dãy có thể chạy mãi | `Stream.iterate(seed, next).limit(10)` |

`IntStream.iterate(seed, hasNext, next)`, `LongStream.iterate(...)` và `DoubleStream.iterate(...)` cũng có biến thể ba tham số từ Java 9. Chúng dùng kiểu nguyên thủy, tránh boxing của `Stream<Integer>`/`Stream<Long>`/`Stream<Double>` khi xử lý số lượng lớn.

```java
import java.util.stream.IntStream;

int squaresSum = IntStream.iterate(1, i -> i <= 4, i -> i + 1)
        .map(i -> i * i)
        .sum();

System.out.println(squaresSum); // 30 (1 + 4 + 9 + 16)
```

## 6. Dãy trạng thái: một ví dụ không thể thay bằng range đơn giản

Một trường hợp có ích của `iterate` là mỗi trạng thái chứa nhiều thông tin, và trạng thái tiếp theo phụ thuộc vào trạng thái trước. Chẳng hạn, ta tạo các số Fibonacci dưới 100 bằng **trạng thái bất biến** gồm hai số kề nhau:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FibonacciSequence {
    static final class Pair {
        final long current;
        final long next;

        Pair(long current, long next) {
            this.current = current;
            this.next = next;
        }
    }

    public static void main(String[] args) {
        List<Long> fibonacci = Stream.iterate(
                        new Pair(0, 1),
                        p -> p.current < 100,
                        p -> new Pair(p.next, p.current + p.next))
                .map(p -> p.current)
                .collect(Collectors.toList());

        System.out.println(fibonacci);
        // [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
    }
}
```

`Pair` là kiểu hỗ trợ được tạo riêng cho ví dụ: mỗi bước sinh **đối tượng mới**, không sửa cặp cũ. `hasNext` xét `current < 100` nên số Fibonacci 144 không được phát. Với giới hạn nhỏ này phép cộng `long` không tràn; với dãy Fibonacci dài, cần cân nhắc `BigInteger` hoặc giới hạn an toàn.

Ví dụ cho thấy `iterate` không chỉ tương đương “vòng `for` có biến đếm”: nó còn diễn đạt **quy tắc chuyển trạng thái**. Tuy nhiên, nếu thuật toán đòi dừng dựa vào một biến toàn cục bị cập nhật ở nơi khác, hãy cân nhắc mô hình vòng lặp hoặc nguồn sự kiện thích hợp thay vì giấu trạng thái dùng chung trong lambda.

## 7. Điều kiện dừng sai: nguồn có thể chạy vô hạn

Tham số `hasNext` **không tự bảo đảm** Stream hữu hạn. Nếu predicate luôn trả `true` trên những giá trị mà `next` tạo ra, Stream vẫn vô hạn.

```java
// NGUY HIỂM nếu dùng count()/collect(): điều kiện không bao giờ sai.
Stream<Integer> endless = Stream.iterate(
        0,
        i -> i >= 0,
        i -> i + 0);
```

Stream trên cứ lặp lại `0`. Lệnh `count()` hoặc `collect(toList())` trên nguồn này có thể không kết thúc hoặc tiêu tốn tài nguyên. Với những dãy có rủi ro, hãy chứng minh điều kiện dừng bằng cách xác định:

1. **Miền giá trị** của trạng thái;
2. **Bước tiến** của `next` có thật sự tiến về biên hay không;
3. **Predicate** có trở thành `false` sau hữu hạn bước hay không;
4. **Overflow/underflow** hoặc dữ liệu bất thường có làm hỏng logic hay không.

### 7.1. Tràn số khiến điều kiện dừng không còn đúng

```java
// SAI: mọi số int đều <= Integer.MAX_VALUE.
// Sau khi tăng từ MAX_VALUE, int sẽ tràn về MIN_VALUE,
// nên điều kiện này vẫn luôn true.
Stream<Integer> broken = Stream.iterate(
        Integer.MAX_VALUE - 1,
        n -> n <= Integer.MAX_VALUE,
        n -> n + 1);
```

Để tạo dãy nhỏ hơn `Integer.MAX_VALUE`, dùng `n -> n < Integer.MAX_VALUE`; hoặc chuyển sang kiểu `long` khi có nguy cơ cộng vượt miền của `int`. Nếu cần cận trên bao gồm `Integer.MAX_VALUE`, phải xây dựng bước dừng không dựa vào phép cộng `int` có thể tràn, chẳng hạn dùng `LongStream` với cận `long` thích hợp.

### 7.2. Dữ liệu null và hàm lấy khóa

Với Stream đối tượng, `hasNext` và `next` có thể phải xử lý một giá trị `null` nếu seed hoặc phép biến đổi trả null. Đừng viết `value -> value.length() > 0` rồi truyền seed có thể null. Có thể thiết kế hợp đồng “không tạo null” cho trạng thái hoặc có điều kiện rõ ràng như `value -> value != null`, tùy bài toán.

`Stream.iterate` không tự bắt và chuyển ngoại lệ thành cơ chế retry. Nếu `hasNext`/`next` ném ngoại lệ khi pipeline chạy, thao tác kết thúc có thể thất bại. Các lambda thuần, đầu vào hợp lệ và giới hạn được kiểm soát sẽ giúp pipeline dễ kiểm chứng.

## 8. Hiệu năng, thứ tự và xử lý song song

### 8.1. Tính lazy và tài nguyên

Việc tạo nguồn `Stream.iterate(...)` không đồng nghĩa tạo sẵn mọi phần tử trong bộ nhớ. Các ứng viên được tính khi terminal operation thực sự cần duyệt. Nhưng nếu dùng `collect(toList())` để lấy **toàn bộ** một dãy rất lớn, danh sách kết quả vẫn tiêu tốn bộ nhớ tương ứng; nếu nguồn vô hạn, thao tác này không phù hợp.

Một pipeline ngắn mạch có thể giới hạn xử lý:

```java
List<Integer> firstThree = Stream.iterate(
                1,
                n -> n < 1_000_000,
                n -> n + 1)
        .limit(3)
        .collect(Collectors.toList());

System.out.println(firstThree); // [1, 2, 3]
```

`limit(3)` giới hạn **số phần tử đầu ra** được yêu cầu. Nhưng nếu có `filter` trước `limit`, pipeline có thể phải xét nhiều ứng viên hơn để tìm đủ ba phần tử đạt điều kiện lọc.

### 8.2. Phân tách công việc để chạy song song

Dãy `iterate` phụ thuộc phần tử trước để tính phần tử sau. Đây là đặc điểm khác các nguồn có thể chia ngẫu nhiên thành các đoạn độc lập, chẳng hạn `IntStream.range` hoặc mảng. Vì vậy, gọi `parallel()` trên một dãy `iterate` **không mặc nhiên tăng hiệu năng**: việc sinh giá trị có thể phải xử lý tuần tự một phần, trong khi chia/gom công việc vẫn có chi phí.

```java
long total = java.util.stream.LongStream
        .iterate(1L, n -> n <= 100_000L, n -> n + 1)
        .parallel()
        .sum();
```

Ví dụ trên hợp lệ về mặt sử dụng API, nhưng không chứng minh xử lý song song nhanh. Khi cần tính tổng một khoảng số nguyên, `LongStream.rangeClosed(1, 100_000)` rõ ý hơn và thường dễ chia cho các worker.

Ngoài ra, `forEach` trên parallel stream không bảo đảm thứ tự gọi hành động, dù nguồn `iterate` có encounter order. Nếu cần quan sát theo thứ tự, dùng `forEachOrdered` và chấp nhận khả năng chi phí tăng. Tránh ghi vào `ArrayList` chung hoặc thay đổi biến đếm dùng chung trong các lambda của pipeline song song.

## 9. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `i <= end` khi muốn không gồm `end` | Thừa một phần tử | Viết `i < end` và đặt tên `endExclusive` |
| Dùng `i < end` khi muốn gồm `end` | Thiếu phần tử biên | Dùng `i <= end` nếu phép cập nhật không gây tràn |
| Seed không thỏa `hasNext` | Stream rỗng | Kiểm tra quy tắc xử lý khoảng rỗng; điều chỉnh seed nếu có yêu cầu |
| `next` không tiến về biên dừng | Pipeline có thể vô hạn | Chứng minh điều kiện kết thúc; kiểm soát giá trị bước nhảy |
| Tính toán trên `int` vượt miền giá trị | Tràn số, sai dãy hoặc không dừng | Dùng `long`/`BigInteger`, ràng buộc cận an toàn |
| Gọi `collect` trên dãy không có điểm dừng | Có thể cạn bộ nhớ | Bổ sung điều kiện dừng hoặc giới hạn đầu ra |
| Dùng `Stream<Integer>` cho tính toán số lượng rất lớn mà không cần object | Boxing/unboxing gây chi phí | Cân nhắc `IntStream`, `LongStream` |
| Đặt side effect trong `hasNext`/`next` | Khó dự đoán khi lazy hoặc ngắn mạch | Viết hàm thuần, trạng thái bất biến |
| Nghĩ `parallel()` luôn tăng tốc | Có thể chậm hơn | Đo với dữ liệu thật, ưu tiên nguồn chia được khi phù hợp |

## 10. Bài tập tự kiểm tra

**Bài 1.** Viết `IntStream.iterate` ba tham số tạo các bội số của 4 trong khoảng từ 4 đến 20, **bao gồm 20**.

```java
int[] multiples = java.util.stream.IntStream
        .iterate(4, n -> n <= 20, n -> n + 4)
        .toArray();
// [4, 8, 12, 16, 20]
```

**Bài 2.** Với `Stream.iterate(8, n -> n > 0, n -> n / 2)` trên số nguyên, dãy phát ra là gì?

Đáp án: `[8, 4, 2, 1]`. Giá trị ứng viên tiếp theo là `0`, không thỏa `n > 0` nên không được phát.

**Bài 3.** Vì sao `Stream.iterate(1, n -> n < 20, n -> n * 2).count()` trả `5`?

Các phần tử là `1, 2, 4, 8, 16`; số `32` không qua được điều kiện. Không có số `20` trong dãy.

**Bài 4.** Có lịch kiểm tra mỗi 7 ngày từ 01/12/2026 đến hết 31/12/2026. Hãy chọn các tham số cho `iterate`.

```java
LocalDate start = LocalDate.of(2026, 12, 1);
LocalDate end = LocalDate.of(2026, 12, 31);

List<LocalDate> dates = Stream.iterate(
                start,
                d -> !d.isAfter(end),
                d -> d.plusDays(7))
        .collect(Collectors.toList());
// [2026-12-01, 2026-12-08, 2026-12-15, 2026-12-22, 2026-12-29]
```

Đoạn mã dùng các import `java.time.LocalDate`, `java.util.List`, `java.util.stream.Stream` và `java.util.stream.Collectors`.

**Bài 5.** Khi chỉ cần các số nguyên liên tiếp từ 1 đến 1.000, nên bắt đầu với `IntStream.rangeClosed(1, 1000)` hay `Stream.iterate(1, n -> n <= 1000, n -> n + 1)`?

Đáp án: `IntStream.rangeClosed` trực tiếp mô tả khoảng liên tiếp, tránh boxing và dễ chia hơn khi có xử lý song song. `iterate` hữu ích khi quy tắc chuyển trạng thái phức tạp hoặc phụ thuộc vào giá trị trước.

## 11. Nguyên tắc ghi nhớ

`Stream.iterate(seed, hasNext, next)` biểu diễn một dãy **theo trạng thái**: kiểm tra ứng viên, phát ứng viên nếu hợp lệ, rồi sinh ứng viên mới. Nó cung cấp điều kiện dừng ngay tại nguồn từ Java 9, có thể kết hợp với mọi bước biến đổi Stream API và đặc biệt hữu ích cho dãy số theo công thức, ngày tháng hoặc trạng thái bất biến. Hãy chọn đúng cận, bảo đảm bước tiến khiến điều kiện sẽ sai, tránh tràn số và xử lý tài nguyên phù hợp với terminal operation. Với khoảng số nguyên đơn giản, ưu tiên `IntStream.range`/`rangeClosed`; với nhu cầu lấy đúng N phần tử của một nguồn không có cận giá trị rõ ràng, cân nhắc `limit(N)`.
