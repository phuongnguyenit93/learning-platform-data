# `Iterable` và `Iterator`: hợp đồng duyệt dữ liệu

`Iterable` và `Iterator` là hai interface nền tảng trong Java giúp duyệt qua một chuỗi phần tử mà không cần biết dữ liệu được lưu trữ hoặc tạo ra như thế nào. `Iterable<T>` biểu thị một đối tượng có thể cung cấp một iterator để duyệt các phần tử kiểu `T`; `Iterator<T>` đại diện cho trạng thái và thao tác của một lượt duyệt cụ thể.

Hai interface này có vai trò liên quan nhưng khác nhau: `Iterable` cung cấp điểm bắt đầu để lấy iterator, còn `Iterator` điều khiển việc kiểm tra phần tử kế tiếp và lấy phần tử đó. Hiểu đúng hợp đồng giúp dùng vòng lặp `for-each`, tự viết kiểu dữ liệu có thể duyệt, và tránh lỗi khi iterator đã đi đến cuối.

## 1. Hợp đồng của `Iterable<T>`

`Iterable<T>` nằm trong `java.lang`, vì vậy không cần import riêng. Hợp đồng quan trọng nhất là phương thức:

```java
Iterator<T> iterator();
```

Phương thức `iterator()` trả về một đối tượng dùng để duyệt các phần tử. Một lớp muốn dùng được với vòng lặp `for-each` theo dạng collection có thể triển khai `Iterable<T>` và cung cấp phương thức này. Ví dụ, `List<T>` kế thừa hợp đồng `Iterable<T>` thông qua `Collection<T>`.

`Iterable` không bắt buộc đối tượng phải lưu tất cả phần tử trong bộ nhớ hoặc phải là một collection. Một đối tượng có thể tạo giá trị khi được duyệt, đọc từ nguồn dữ liệu, hoặc tính toán các phần tử theo nhu cầu. Chi tiết về thứ tự, khả năng lặp lại nhiều lần và việc dữ liệu có thay đổi hay không phụ thuộc vào kiểu cụ thể.

Ngoài `iterator()`, `Iterable` có các phương thức mặc định hữu ích như `forEach(Consumer<? super T>)` và `spliterator()`. `forEach` áp dụng hành động cho các phần tử theo thứ tự duyệt được cung cấp; `spliterator` cung cấp một cơ chế duyệt có thể hỗ trợ phân tách công việc cho các API như Stream.

## 2. Hợp đồng của `Iterator<T>`

Một iterator quản lý một lượt duyệt. Hai phương thức cốt lõi là:

```java
boolean hasNext();
T next();
```

- `hasNext()` trả về `true` nếu lượt duyệt còn ít nhất một phần tử; phương thức này không lấy hoặc tiêu thụ phần tử kế tiếp.
- `next()` trả về phần tử kế tiếp và tiến trạng thái duyệt. Nếu không còn phần tử, `next()` phải ném `NoSuchElementException`.

`Iterator` còn có `remove()`, một thao tác tùy chọn để xóa phần tử gần nhất được trả về bởi `next()`. Một iterator không hỗ trợ xóa có thể ném `UnsupportedOperationException`. Không nên giả định mọi iterator đều cho phép sửa collection trong lúc duyệt. Phương thức mặc định `forEachRemaining(Consumer<? super T>)` thực hiện hành động cho các phần tử còn lại.

Thông thường, hãy gọi `hasNext()` để kiểm tra trước khi gọi `next()` trong vòng lặp. Không gọi `next()` thêm một lần sau khi đã hết phần tử. Một iterator thường là con trỏ tiến về phía trước; muốn duyệt lại, hãy lấy iterator khác từ `Iterable` nếu kiểu dữ liệu hỗ trợ lặp lại.

## 3. Ví dụ Java 17+ có thể chạy

Ví dụ dưới đây định nghĩa `IntRange`, một dãy số nguyên từ `startInclusive` đến trước `endExclusive`. Lớp này triển khai `Iterable<Integer>` và mỗi lời gọi `iterator()` tạo một iterator có trạng thái riêng.

Lưu vào tệp `IterableIteratorDemo.java`:

```java
import java.util.Iterator;
import java.util.NoSuchElementException;

public class IterableIteratorDemo {
    static final class IntRange implements Iterable<Integer> {
        private final int startInclusive;
        private final int endExclusive;

        IntRange(int startInclusive, int endExclusive) {
            if (endExclusive < startInclusive) {
                throw new IllegalArgumentException("endExclusive must be >= startInclusive");
            }
            this.startInclusive = startInclusive;
            this.endExclusive = endExclusive;
        }

        @Override
        public Iterator<Integer> iterator() {
            return new Iterator<>() {
                private int current = startInclusive;

                @Override
                public boolean hasNext() {
                    return current < endExclusive;
                }

                @Override
                public Integer next() {
                    if (!hasNext()) {
                        throw new NoSuchElementException();
                    }
                    return current++;
                }
            };
        }
    }

    public static void main(String[] args) {
        Iterable<Integer> numbers = new IntRange(1, 5);

        System.out.println("for-each:");
        for (int number : numbers) {
            System.out.println(number);
        }

        System.out.println("manual iterator:");
        Iterator<Integer> iterator = numbers.iterator();
        while (iterator.hasNext()) {
            System.out.println(iterator.next());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```text
javac IterableIteratorDemo.java
java IterableIteratorDemo
```

Đầu ra chính xác:

```text
for-each:
1
2
3
4
manual iterator:
1
2
3
4
```

## 4. Cách đọc ví dụ

`IntRange` lưu hai giới hạn. Điều kiện `current < endExclusive` khiến giá trị cuối không được đưa vào dãy; với `new IntRange(1, 5)`, các phần tử là `1`, `2`, `3`, `4`. Constructor từ chối giới hạn cuối nhỏ hơn giới hạn đầu để tránh một phạm vi không hợp lệ theo hợp đồng đã chọn.

Trong `iterator()`, lớp ẩn danh giữ biến `current`. `hasNext()` chỉ kiểm tra điều kiện, còn `next()` kiểm tra lại điều kiện, ném `NoSuchElementException` nếu đã hết, rồi trả về giá trị hiện tại và tăng biến đếm. Kiểm tra trong `next()` vẫn cần thiết vì người gọi có thể gọi `next()` mà không gọi `hasNext()` trước.

Vòng `for (int number : numbers)` là cú pháp duyệt thuận tiện cho một đối tượng `Iterable`. Về ý tưởng, compiler lấy iterator rồi lặp khi `hasNext()` còn đúng, mỗi vòng gọi `next()` để nhận giá trị. Vòng `while` phía sau thể hiện trực tiếp hợp đồng đó. Vì ví dụ `IntRange.iterator()` tạo trạng thái mới mỗi lần được gọi, hai lượt duyệt đều bắt đầu từ `1`.

## 5. So sánh nhanh

| Thành phần | Trách nhiệm | Ví dụ sử dụng |
| --- | --- | --- |
| `Iterable<T>` | Cung cấp iterator cho một đối tượng có thể duyệt. | `for (String s : names)` |
| `Iterator<T>` | Theo dõi vị trí của một lượt duyệt, kiểm tra và trả về phần tử kế tiếp. | `while (it.hasNext()) { use(it.next()); }` |
| `Collection<T>` | Đại diện cho một nhóm phần tử và kế thừa `Iterable<T>`. | `List<String> names = new ArrayList<>();` |

Chọn `Iterable` khi muốn người dùng có thể duyệt kiểu dữ liệu bằng `for-each`. Làm việc trực tiếp với `Iterator` khi cần kiểm soát tiến trình duyệt, gọi `remove()` nếu được hỗ trợ, hoặc dừng tại một điều kiện cụ thể.

## 6. Các lỗi và lưu ý thường gặp

1. **Gọi `next()` sau khi hết phần tử.** Luôn kiểm tra `hasNext()` hoặc dùng `for-each`; nếu không còn phần tử, `next()` ném `NoSuchElementException`.
2. **Nhầm `hasNext()` với thao tác lấy phần tử.** `hasNext()` chỉ kiểm tra xem còn phần tử hay không; `next()` mới trả về phần tử và chuyển iterator tiến lên.
3. **Giả định `remove()` luôn được hỗ trợ.** Đây là thao tác tùy chọn. Đọc tài liệu của kiểu iterator cụ thể và xử lý `UnsupportedOperationException` nếu thiết kế cần tính đến trường hợp đó.
4. **Sửa collection bên ngoài trong lúc duyệt.** Một số iterator của JDK là fail-fast và có thể ném `ConcurrentModificationException` khi phát hiện sửa đổi không được phép. Cơ chế fail-fast chỉ nhằm phát hiện lỗi theo best-effort; không phải bảo đảm đồng bộ hay bảo đảm phát hiện mọi sửa đổi. Hãy dùng API sửa đổi được iterator hỗ trợ hoặc cơ chế đồng bộ phù hợp.
5. **Giả định mọi `Iterable` có thể duyệt lại.** Hợp đồng `Iterable` cung cấp `iterator()`, nhưng khả năng lặp lại và trạng thái của nguồn phụ thuộc vào cách triển khai. Nếu cần nhiều lượt duyệt, hãy xác nhận kiểu cụ thể hỗ trợ điều đó.
6. **Bỏ qua thứ tự duyệt.** Thứ tự phần tử do implementation quy định. Một `List` giữ thứ tự theo chỉ số, trong khi một kiểu collection khác có thể có quy tắc thứ tự khác.

## 7. Ghi nhớ

- `Iterable<T>` cung cấp `iterator()`; `Iterator<T>` cung cấp `hasNext()` và `next()`.
- `hasNext()` kiểm tra, `next()` trả về phần tử kế tiếp và ném `NoSuchElementException` khi đã hết.
- Vòng `for-each` làm mã duyệt `Iterable` gọn hơn; iterator tường minh hữu ích khi cần kiểm soát lượt duyệt.
- `remove()` là thao tác tùy chọn, còn fail-fast không phải cơ chế đồng bộ.
- Khi tự triển khai `Iterable`, xác định rõ thứ tự, điều kiện kết thúc, hành vi khi hết phần tử và khả năng tạo iterator mới.