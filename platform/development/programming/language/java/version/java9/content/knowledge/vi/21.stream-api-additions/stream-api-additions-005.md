# `Stream.iterate()` với điều kiện kết thúc

`Stream.iterate()` tạo một stream bằng cách bắt đầu từ một giá trị seed rồi liên tục áp dụng hàm tạo phần tử kế tiếp. Từ Java 9, overload nhận thêm predicate `hasNext` cho phép mô tả điều kiện dừng ngay trong lời gọi. Stream kết thúc khi predicate trả về `false`, vì vậy không cần tự tạo một vòng lặp hoặc dựa vào `limit()` nếu điểm dừng phụ thuộc vào giá trị hiện tại.

Overload này vẫn được hỗ trợ trong các phiên bản Java hiện đại. Nó phù hợp với dãy có quy luật rõ ràng như số thứ tự, ngày tháng, phiên bản hoặc các trạng thái được tạo tuần tự cho đến khi đạt điều kiện.

## 1. Chữ ký của overload có điều kiện

```java
static <T> Stream<T> iterate(
        T seed,
        Predicate<? super T> hasNext,
        UnaryOperator<T> next
);
```

Ba tham số có vai trò riêng:

- `seed`: phần tử bắt đầu của stream.
- `hasNext`: predicate kiểm tra phần tử hiện tại có được đưa vào stream hay không.
- `next`: hàm nhận phần tử hiện tại và tạo ra phần tử kế tiếp.

Stream bắt đầu bằng việc kiểm tra `hasNext` trên `seed`. Nếu predicate trả về `true`, phần tử hiện tại được phát ra; sau đó `next` tạo ứng viên tiếp theo và predicate được kiểm tra lại. Khi predicate trả về `false`, phần tử hiện tại không được phát ra và stream kết thúc.

Vì vậy, điều kiện trong `hasNext` được kiểm tra *trước khi* phần tử tương ứng được đưa vào stream. Đây là điểm quan trọng để tránh lỗi lệch một phần tử ở biên.

## 2. Ví dụ cơ bản: tạo dãy từ 1 đến 5

```java
List<Integer> values = Stream.iterate(
        1,
        number -> number <= 5,
        number -> number + 1
).toList();

System.out.println(values);
```

Kết quả:

```text
[1, 2, 3, 4, 5]
```

Diễn tiến:

| Giá trị được kiểm tra | `number <= 5` | Kết quả |
| ---: | --- | --- |
| 1 | `true` | Phát ra 1, tạo tiếp 2 |
| 2 | `true` | Phát ra 2, tạo tiếp 3 |
| 3 | `true` | Phát ra 3, tạo tiếp 4 |
| 4 | `true` | Phát ra 4, tạo tiếp 5 |
| 5 | `true` | Phát ra 5, tạo tiếp 6 |
| 6 | `false` | Dừng, không phát ra 6 |

Giá trị `5` vẫn xuất hiện vì predicate kiểm tra `<= 5`. Nếu muốn dừng trước `5`, dùng điều kiện `< 5`; khi đó stream phát ra `1, 2, 3, 4`.

## 3. Điều kiện sai ngay từ seed

Predicate cũng được kiểm tra với seed. Nếu seed không thỏa điều kiện, stream không có phần tử nào và hàm `next` không cần tạo phần tử tiếp theo:

```java
List<Integer> empty = Stream.iterate(
        6,
        number -> number <= 5,
        number -> number + 1
).toList();

System.out.println(empty);
```

Kết quả:

```text
[]
```

Không nên hiểu rằng `iterate` luôn phát ra seed rồi mới kiểm tra điều kiện. Với overload có predicate, seed cũng phải vượt qua `hasNext` trước khi được phát ra.

## 4. Ví dụ hoàn chỉnh có thể chạy

Chương trình sau minh họa dãy có điều kiện, trường hợp rỗng ngay từ đầu và việc kết hợp với `map()` để biến đổi phần tử:

```java
import java.util.List;
import java.util.stream.Stream;

public class IterateWithPredicate {
    public static void main(String[] args) {
        List<Integer> values = Stream.iterate(
                1,
                number -> number <= 5,
                number -> number + 1
        ).toList();
        System.out.println("Values: " + values);

        List<Integer> empty = Stream.iterate(
                6,
                number -> number <= 5,
                number -> number + 1
        ).toList();
        System.out.println("Empty: " + empty);

        List<Integer> squares = Stream.iterate(
                1,
                number -> number <= 4,
                number -> number + 1
        ).map(number -> number * number).toList();
        System.out.println("Squares: " + squares);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 IterateWithPredicate.java
java IterateWithPredicate
```

Kết quả stdout:

```text
Values: [1, 2, 3, 4, 5]
Empty: []
Squares: [1, 4, 9, 16]
```

`Stream.toList()` được dùng trong ví dụ để thu kết quả thành list không sửa được. Nếu kết quả cần mutable, có thể dùng `collect(Collectors.toCollection(ArrayList::new))`.

## 5. So sánh với overload không có điều kiện

Overload hai tham số đã có từ Java 8:

```java
Stream.iterate(seed, next)
```

Overload này tiếp tục tạo phần tử kế tiếp vô hạn theo quy luật `next`, trừ khi quá trình duyệt bị giới hạn bởi terminal operation hoặc một intermediate operation như `limit()`.

Ví dụ tạo đúng năm số đầu tiên:

```java
List<Integer> values = Stream.iterate(1, number -> number + 1)
        .limit(5)
        .toList();
```

Khi số lượng phần tử cần lấy đã biết trước, `limit(count)` diễn đạt trực tiếp số lượng mong muốn. Khi điểm dừng phụ thuộc vào giá trị đang được tạo, overload Java 9 có predicate thường rõ ràng hơn:

```java
Stream.iterate(1, number -> number <= 5, number -> number + 1)
```

Không cần thêm `limit()` chỉ để lặp lại cùng một điều kiện dừng. Có thể kết hợp `limit()` nếu nghiệp vụ thực sự có cả hai giới hạn, ví dụ dừng khi đạt một giá trị hoặc khi đã lấy đủ số phần tử tối đa.

## 6. So sánh với `takeWhile()` và `filter()`

`takeWhile()` cũng có từ Java 9, nhưng áp dụng lên một stream đã tồn tại. Với stream có thứ tự, nó giữ phần tử liên tiếp từ đầu khi predicate còn đúng và dừng tại phần tử đầu tiên không thỏa điều kiện:

```java
List<Integer> values = Stream.of(1, 2, 3, 6, 4, 5)
        .takeWhile(number -> number <= 5)
        .toList();
```

Kết quả là `[1, 2, 3]`. Khi gặp `6`, `takeWhile()` dừng và không xét phần tử `4`, `5` ở phía sau.

`filter()` có semantics khác: nó bỏ từng phần tử không thỏa predicate nhưng tiếp tục xét các phần tử còn lại. Với cùng nguồn ở trên:

```java
List<Integer> values = Stream.of(1, 2, 3, 6, 4, 5)
        .filter(number -> number <= 5)
        .toList();
```

Kết quả là `[1, 2, 3, 4, 5]`, vì `filter()` vẫn xét các phần tử sau `6`.

Có thể chọn theo mục đích:

- `iterate(seed, hasNext, next)`: tạo một dãy mới từ seed và dừng theo predicate trên giá trị hiện tại.
- `takeWhile(predicate)`: lấy phần đầu liên tiếp của một stream có sẵn cho đến khi predicate sai.
- `filter(predicate)`: lọc từng phần tử trên toàn bộ stream; phần tử sai không làm stream dừng.

## 7. Dùng với ngày tháng hoặc trạng thái có quy luật

Predicate không chỉ dùng với số. Ví dụ, tạo các ngày từ ngày bắt đầu đến hết ngày kết thúc:

```java
LocalDate start = LocalDate.of(2026, 11, 1);
LocalDate end = LocalDate.of(2026, 11, 5);

List<LocalDate> days = Stream.iterate(
        start,
        day -> !day.isAfter(end),
        day -> day.plusDays(1)
).toList();
```

Điều kiện `!day.isAfter(end)` bao gồm cả ngày kết thúc. Nếu dùng `day.isBefore(end)`, ngày kết thúc sẽ không được phát ra. Khi làm việc với thời gian, cần xác định rõ biên bao gồm hay loại trừ để tránh sai lệch ngày.

Với dãy số, hãy bảo đảm phép tính `next` tiến về phía điều kiện dừng. Ví dụ tăng một số nguyên có giới hạn cần tính đến khả năng tràn số; nếu giá trị bị tràn và predicate lại trở thành `true`, stream có thể tiếp tục lâu hơn dự kiến hoặc không kết thúc. Chọn kiểu số và giới hạn phù hợp với miền dữ liệu.

## 8. Lazy evaluation và giới hạn khi thực thi

Stream là lazy: các phần tử không nhất thiết được tạo ngay khi gọi `Stream.iterate()`. Việc xử lý bắt đầu khi có terminal operation như `toList()`, `forEach()`, `count()` hoặc `findFirst()`.

Một terminal operation ngắn mạch như `findFirst()` có thể dừng duyệt sớm khi đã tìm thấy kết quả. Khi đó không nhất thiết predicate phải được gọi đến phần tử cuối cùng làm điều kiện dừng tự nhiên. Vì vậy, không dựa vào số lần gọi chính xác của `hasNext` hoặc `next` để thực hiện tác dụng phụ nghiệp vụ.

Giữ `hasNext` và `next` stateless, non-interfering: không sửa nguồn stream hoặc cập nhật biến mutable dùng chung từ bên trong các lambda này. Mỗi lần gọi nên dựa trên đối số hiện tại và trả về kết quả theo quy tắc rõ ràng. Cách viết này giúp pipeline dễ kiểm tra và tránh phụ thuộc vào thứ tự thực thi.

Overload có predicate tạo một stream tuần tự và có thứ tự. Có thể thay đổi execution mode của stream bằng các operation tương ứng, nhưng chuỗi sinh phần tử phụ thuộc tuần tự vào phần tử trước; chuyển sang parallel không tự làm quá trình sinh nhanh hơn.

## 9. Các lỗi thường gặp

- **Dùng nhầm dấu so sánh:** `<= end` bao gồm giá trị cuối; `< end` loại giá trị cuối.
- **Nghĩ seed luôn được phát ra:** seed chỉ xuất hiện nếu `hasNext.test(seed)` trả về `true`.
- **Nhầm predicate với filter:** predicate của overload này là điều kiện kết thúc; phần tử đầu tiên không thỏa làm stream dừng hoàn toàn.
- **Viết `next` không tiến tới điều kiện dừng:** nếu giá trị không thay đổi hoặc đi sai hướng, stream có thể không kết thúc.
- **Bỏ qua tràn số:** phép tăng trên `int` hoặc `long` có thể tràn và làm điều kiện dừng không còn đúng như dự kiến.
- **Dựa vào side effect trong predicate hoặc next:** terminal operation có thể dừng sớm; không dùng số lần gọi lambda làm logic nghiệp vụ.
- **Dùng overload hai tham số mà quên giới hạn:** `iterate(seed, next)` tự nó mô tả dãy không giới hạn; cần một điều kiện dừng như `limit()` hoặc một operation ngắn mạch khi duyệt.

`Stream.iterate(seed, hasNext, next)` giúp mô tả dãy có điểm dừng gắn với chính giá trị đang tạo. Hãy nhớ predicate được kiểm tra trước khi phát mỗi phần tử, giữ hàm tạo phần tử kế tiếp tiến về điều kiện dừng và chọn `limit`, `takeWhile` hoặc `filter` theo đúng semantics mà bài toán yêu cầu.