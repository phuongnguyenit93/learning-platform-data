# takeWhile và tiền tố thỏa điều kiện

Từ Java 9, Stream API có hai stateful intermediate operation là `takeWhile(Predicate)` và `dropWhile(Predicate)`. Chúng xử lý phần đầu liên tiếp của một stream dựa trên điều kiện. Với stream có encounter order:

- `takeWhile` giữ tiền tố dài nhất mà mọi phần tử đều thỏa predicate.
- `dropWhile` bỏ tiền tố dài nhất mà mọi phần tử đều thỏa predicate, rồi giữ phần tử đầu tiên không thỏa và toàn bộ phần còn lại.

Hai phương thức này làm việc theo ranh giới đầu tiên không thỏa điều kiện; chúng không tìm mọi phần tử phù hợp ở bất kỳ vị trí nào như `filter`.

## 1. API và kiểu trả về

Trên `Stream<T>`, chữ ký là:

~~~java
Stream<T> takeWhile(Predicate<? super T> predicate)
Stream<T> dropWhile(Predicate<? super T> predicate)
~~~

Các primitive stream cũng có phiên bản tương ứng:

- `IntStream.takeWhile(IntPredicate)` và `IntStream.dropWhile(IntPredicate)`
- `LongStream.takeWhile(LongPredicate)` và `LongStream.dropWhile(LongPredicate)`
- `DoubleStream.takeWhile(DoublePredicate)` và `DoubleStream.dropWhile(DoublePredicate)`

Kết quả vẫn là một stream cùng loại, nên có thể nối với `map`, `filter`, `distinct`, `sorted` hoặc các operation khác, rồi kết thúc bằng terminal operation như `collect`, `count`, `forEach`.

Hai phương thức là intermediate operation và được thực thi lazy: pipeline chỉ bắt đầu xử lý khi có terminal operation.

## 2. takeWhile: giữ tiền tố thỏa điều kiện

Với stream có encounter order, `takeWhile(predicate)` lấy các phần tử liên tiếp từ đầu cho đến ngay trước phần tử đầu tiên khiến predicate trả về `false`.

Ví dụ dữ liệu:

~~~text
[2, 4, 6, 7, 8, 10]
~~~

Với predicate `n -> n % 2 == 0`, kết quả là:

~~~text
[2, 4, 6]
~~~

Phần tử `7` là ranh giới đầu tiên không thỏa điều kiện. Các phần tử `8` và `10` dù là số chẵn vẫn bị bỏ khỏi kết quả vì chúng nằm sau ranh giới đó.

Các trường hợp biên:

- Phần tử đầu tiên không thỏa: kết quả rỗng.
- Mọi phần tử đều thỏa: kết quả chứa toàn bộ stream.
- Stream rỗng: kết quả rỗng.

`takeWhile` là short-circuiting stateful intermediate operation. Trên pipeline tuần tự có thứ tự, nó có thể dừng khi tìm thấy ranh giới. Với pipeline song song, implementation có thể đánh giá phần tử đồng thời; không nên dựa vào số lần hoặc thứ tự gọi predicate.

## 3. dropWhile: bỏ tiền tố thỏa điều kiện

Với stream có encounter order, `dropWhile(predicate)` bỏ các phần tử liên tiếp từ đầu cho đến ngay trước phần tử đầu tiên khiến predicate trả về `false`. Phần tử ranh giới đó và mọi phần tử sau nó được giữ lại.

Với cùng dữ liệu và predicate số chẵn:

~~~text
[2, 4, 6, 7, 8, 10]
~~~

Kết quả là:

~~~text
[7, 8, 10]
~~~

Phần tử `7` được giữ lại vì nó là phần tử đầu tiên không thỏa predicate. Các phần tử `8` và `10` cũng được giữ dù chúng thỏa điều kiện.

Các trường hợp biên:

- Phần tử đầu tiên không thỏa: không có phần tử nào bị bỏ, kết quả là toàn bộ stream.
- Mọi phần tử đều thỏa: kết quả rỗng.
- Stream rỗng: kết quả rỗng.

`dropWhile` phải tìm ranh giới kết thúc tiền tố trước khi phát ra phần còn lại. Vì thế, với stream vô hạn mà mọi phần tử đều thỏa predicate, operation này không thể tìm thấy ranh giới để phát ra phần tử đầu tiên.

## 4. Phân biệt với filter

| Operation | Ngữ nghĩa trên stream có thứ tự | Kết quả với [2, 4, 6, 7, 8, 10], điều kiện số chẵn |
|---|---|---|
| `takeWhile` | Giữ tiền tố liên tiếp thỏa điều kiện | `[2, 4, 6]` |
| `dropWhile` | Bỏ tiền tố liên tiếp thỏa điều kiện | `[7, 8, 10]` |
| `filter` | Giữ mọi phần tử thỏa điều kiện ở mọi vị trí | `[2, 4, 6, 8, 10]` |

`filter` tiếp tục kiểm tra các phần tử sau một phần tử không phù hợp và vẫn giữ những phần tử phù hợp phía sau. `takeWhile` và `dropWhile` xác định một ranh giới duy nhất ở lần không phù hợp đầu tiên.

Chọn theo yêu cầu:

- "Lấy tất cả số chẵn trong dữ liệu": dùng `filter`.
- "Lấy phần đầu cho đến khi gặp giá trị không còn hợp lệ": dùng `takeWhile`.
- "Bỏ phần đầu không còn cần xử lý và giữ phần còn lại": dùng `dropWhile`.

## 5. Ví dụ chạy được với Java 17+

Tạo file **TakeWhileDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class TakeWhileDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 4, 6, 7, 8, 10);

        List<Integer> prefix = numbers.stream()
                .takeWhile(n -> n % 2 == 0)
                .collect(Collectors.toList());

        List<Integer> remainder = numbers.stream()
                .dropWhile(n -> n % 2 == 0)
                .collect(Collectors.toList());

        List<Integer> allEven = numbers.stream()
                .filter(n -> n % 2 == 0)
                .collect(Collectors.toList());

        System.out.println("takeWhile: " + prefix);
        System.out.println("dropWhile: " + remainder);
        System.out.println("filter: " + allEven);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TakeWhileDemo.java
java TakeWhileDemo
~~~

Kết quả stdout:

~~~text
takeWhile: [2, 4, 6]
dropWhile: [7, 8, 10]
filter: [2, 4, 6, 8, 10]
~~~

Nguồn List có encounter order xác định. `Collectors.toList()` thu kết quả thành List nên thứ tự phần tử trong kết quả giữ theo encounter order của pipeline.

## 6. Encounter order và stream không có thứ tự

Khái niệm tiền tố chỉ có ý nghĩa khi stream có encounter order. List, mảng và `Stream.of(...)` là những nguồn thường có thứ tự xác định. Với chúng, ranh giới được tính theo thứ tự phần tử.

Với stream không có encounter order, nếu predicate đúng với mọi phần tử thì `takeWhile` giữ tất cả và `dropWhile` bỏ tất cả. Nếu predicate sai với mọi phần tử thì `takeWhile` trả rỗng và `dropWhile` giữ tất cả. Nếu có cả phần tử đúng lẫn sai, đặc tả cho phép kết quả không xác định theo vị trí:

- `takeWhile` có thể lấy bất kỳ tập con nào gồm các phần tử thỏa predicate, kể cả tập rỗng.
- `dropWhile` có thể bỏ bất kỳ tập con nào gồm các phần tử thỏa predicate, kể cả không bỏ phần tử nào.

Không dựa vào tiền tố cố định khi nguồn không có thứ tự.

Gọi `unordered()` loại bỏ ràng buộc encounter order. Điều này có thể giúp một pipeline song song trong một số trường hợp, nhưng cũng thay đổi ngữ nghĩa kết quả. Chỉ dùng khi nghiệp vụ không cần ranh giới theo thứ tự ban đầu.

## 7. Dùng với parallel stream

`parallel()` thay đổi cách thực thi, không tự loại bỏ encounter order. Nếu nguồn có thứ tự, `takeWhile` và `dropWhile` vẫn phải giữ ngữ nghĩa tiền tố theo thứ tự đó. Việc tìm phần tử đầu tiên không thỏa có thể hạn chế khả năng xử lý song song và làm operation tốn chi phí hơn.

~~~java
List<Integer> prefix = numbers.parallelStream()
        .takeWhile(n -> n < 100)
        .collect(Collectors.toList());
~~~

Kết quả vẫn tương ứng với tiền tố dài nhất theo encounter order của List.

Nếu thứ tự không quan trọng và ứng dụng chấp nhận ngữ nghĩa của unordered stream, có thể cân nhắc `unordered().takeWhile(...)` hoặc `unordered().dropWhile(...)`. Không bỏ thứ tự chỉ để tối ưu nếu kết quả cần giữ chính xác tiền tố ban đầu; hãy đo hiệu năng bằng dữ liệu đại diện.

## 8. Predicate và lỗi thường gặp

Predicate nên stateless và non-interfering: không cập nhật biến dùng chung, không sửa nguồn dữ liệu đang được stream xử lý và không phụ thuộc số lần được gọi. Stream có thể tối ưu pipeline; parallel stream có thể đánh giá nhiều phần tử đồng thời. Hãy dựa vào kết quả được đặc tả thay vì số lần gọi predicate.

Những lỗi thường gặp:

- **Nhầm `takeWhile` với `filter`:** phần tử phù hợp sau ranh giới đầu tiên không được `takeWhile` giữ lại.
- **Nhầm phần tử ranh giới của `dropWhile`:** phần tử đầu tiên không thỏa predicate được giữ trong kết quả.
- **Giả định stream nào cũng có thứ tự:** không dựa vào tiền tố với nguồn không có encounter order.
- **Cho rằng `parallel()` xóa thứ tự:** muốn bỏ ràng buộc thứ tự phải gọi `unordered()`, và chỉ khi nghiệp vụ cho phép.
- **Dùng lại stream đã tiêu thụ:** mỗi terminal operation cần một pipeline mới từ nguồn dữ liệu, như ví dụ gọi `numbers.stream()` riêng cho từng kết quả.

## 9. Checklist lựa chọn

- Lấy tiền tố liên tiếp thỏa điều kiện: `takeWhile`.
- Bỏ tiền tố liên tiếp thỏa điều kiện và giữ phần tử ranh giới: `dropWhile`.
- Lấy mọi phần tử thỏa điều kiện ở bất kỳ vị trí nào: `filter`.
- Cần kết quả theo vị trí đầu tiên không thỏa: dùng stream có encounter order.
- Dùng parallel stream: đánh giá chi phí duy trì thứ tự; chỉ dùng `unordered()` khi chấp nhận thay đổi ngữ nghĩa.
- Viết predicate stateless, non-interfering.

`takeWhile` và `dropWhile` là các operation hiện hành của Stream API từ Java 9. Chúng phù hợp khi dữ liệu có thứ tự và logic xử lý phụ thuộc vào ranh giới đầu tiên không còn thỏa một điều kiện.
