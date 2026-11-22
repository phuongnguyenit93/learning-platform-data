# Iterator: hasNext, next và forEachRemaining

`Iterator<E>` là đối tượng giữ trạng thái của **một lượt duyệt** các phần tử kiểu `E`. Nó giúp mã sử dụng dữ liệu lấy lần lượt từng phần tử mà không cần biết nguồn được lưu bằng mảng, danh sách liên kết, tập hợp hay được tạo ra theo một cách khác.

Ba phương thức trọng tâm:

| Phương thức | Câu hỏi hoặc thao tác |
| --- | --- |
| `boolean hasNext()` | Còn phần tử để lấy không? |
| `E next()` | Lấy phần tử tiếp theo và tiến trạng thái duyệt. |
| `void forEachRemaining(Consumer<? super E> action)` | Áp dụng hành động cho toàn bộ phần còn lại của lượt duyệt. |

Một iterator không phải bản sao của tập hợp và không tự bắt đầu lại sau khi đã hết. Cần hiểu trạng thái duyệt trước khi chọn vòng lặp thủ công hay `forEachRemaining`.

## 1. Iterable cung cấp lượt duyệt, Iterator giữ trạng thái lượt đó

Với một danh sách:

~~~java
// Đoạn mã trong một phương thức; cần import java.util.List và java.util.Iterator.
List<String> values = List.of("A", "B", "C");
Iterator<String> iterator = values.iterator();
~~~

Có hai đối tượng với hai vai trò:

- `values` là danh sách chứa hoặc cung cấp dữ liệu theo hợp đồng `List`.
- `iterator` là bộ duyệt giữ thông tin lần lấy tiếp theo của lượt duyệt này.

`Iterable<E>` là hợp đồng cung cấp `iterator()`. `Collection<E>`, `List<E>` và `Set<E>` là những ví dụ thuộc nhóm có thể duyệt theo cách đó.

`Iterator<E>` thuộc gói `java.util`, không phải `java.lang`. Tạo iterator từ một danh sách không tự tạo danh sách mới.

### Hình dung vị trí phần tử tiếp theo

Với danh sách A, B, C:

~~~text
Mới tạo:
phần tiếp theo -> A, B, C

Sau next() trả A:
đã đi qua: A
phần tiếp theo -> B, C

Sau next() trả B:
đã đi qua: A, B
phần tiếp theo -> C

Sau next() trả C:
đã đi qua: A, B, C
phần còn lại: rỗng
~~~

Đây là mô hình để đọc chương trình. Không phải mọi lớp iterator đều dùng một biến chỉ số nội bộ. Với một danh sách liên kết, cấu trúc duyệt có thể dựa vào nút; với nguồn khác, trạng thái còn có thể khác.

## 2. hasNext: hỏi còn phần tử, không lấy phần tử

~~~java
Iterator<String> iterator = List.of("A", "B").iterator();

System.out.println(iterator.hasNext()); // true
System.out.println(iterator.hasNext()); // true
System.out.println(iterator.next());    // A
~~~

Trong lượt duyệt bình thường của nguồn không bị thay đổi, gọi `hasNext()` lặp lại không làm bỏ qua A. Phương thức hỏi liệu `next()` còn có thể trả một phần tử, thay vì lấy phần tử đó cho người gọi.

Không gọi `hasNext()` với kỳ vọng nhận được chính phần tử tiếp theo. Giá trị trả về là `boolean`, không phải `E`.

### hasNext không phải cơ chế chờ

Với một iterator thông thường trên collection, `hasNext()` không có nghĩa “chờ đến khi có dữ liệu mới”. Nó cũng không tạo một đảm bảo đồng bộ rằng một luồng khác không thể thay đổi nguồn sau lần kiểm tra.

Không suy ra mọi iterator đều có cùng chi phí `hasNext()`. Một nguồn được tính toán hoặc đọc lười có thể phải chuẩn bị dữ liệu bên trong. Ý nghĩa với người sử dụng vẫn là hỏi còn phần tử, không phải cam kết mọi triển khai chỉ đọc một biến và có chi phí cố định.

### Vòng lặp không tiến thì không kết thúc

~~~java
// Ví dụ sai về logic: nếu iterator đang có phần tử, trạng thái không tiến.
while (iterator.hasNext()) {
    System.out.println("still has data");
}
~~~

Điều kiện không tự tiêu thụ dữ liệu. Một vòng duyệt cần gọi `next()` hoặc một thao tác tiêu thụ thích hợp để tiến.

## 3. next: lấy một phần tử và tiến một bước

Dạng thường gặp:

~~~java
while (iterator.hasNext()) {
    String value = iterator.next();
    System.out.println(value);
}
~~~

Mỗi vòng:

1. Kiểm tra còn phần tử.
2. Lấy đúng một phần tử.
3. Xử lý giá trị đã lấy.

Không bắt buộc phải gọi `hasNext()` ngay trước mọi `next()`. Nếu mã có cơ sở chắc chắn còn phần tử, có thể gọi `next()` trực tiếp. Nhưng trách nhiệm xử lý trường hợp không còn dữ liệu vẫn thuộc về người gọi.

Khi đã hết, `next()` ném `NoSuchElementException`; nó không tự trả `null` làm dấu kết thúc. Các hợp đồng ngoại lệ và phần còn lại được mô tả trong [Iterator API của Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

### Không nhầm lấy phần tử với xóa khỏi nguồn

~~~java
List<String> values = List.of("A", "B");
Iterator<String> iterator = values.iterator();

String first = iterator.next();

System.out.println(first);  // A
System.out.println(values); // [A, B]
~~~

`next()` đã đi qua A trong lượt duyệt, nhưng không xóa A khỏi danh sách.

Trong bài này, “tiêu thụ lượt duyệt” nói về trạng thái iterator. Nó không có nghĩa nguồn collection bị xóa từng phần tử.

### Gọi next hai lần là đi hai bước

~~~java
// Ví dụ lỗi thường gặp nếu muốn xử lý mỗi phần tử đúng một lần.
while (iterator.hasNext()) {
    System.out.println(iterator.next());
    process(iterator.next());
}
~~~

`process` ở đây là tên một hàm minh họa của ứng dụng, không phải API có sẵn. Đoạn mã lấy một phần tử để in rồi lấy thêm phần tử khác để xử lý. Nó có thể bỏ qua phần tử theo ý định ban đầu, và lần `next()` thứ hai có thể gặp hết dữ liệu.

Lấy một lần rồi dùng lại biến:

~~~java
while (iterator.hasNext()) {
    String value = iterator.next();
    System.out.println(value);
    process(value);
}
~~~

Các đoạn có `process` chỉ minh họa cấu trúc trong phương thức, không phải chương trình độc lập.

## 4. Null có thể là dữ liệu, không phải tín hiệu đã hết

Nếu nguồn cho phép phần tử `null`, iterator có thể trả `null` như một phần tử hợp lệ:

~~~java
// Cần import java.util.Arrays.
Iterator<String> iterator = Arrays.asList("X", null, "Y").iterator();

while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
~~~

Stdout của đoạn này:

~~~text
X
null
Y
~~~

Viết điều kiện như sau là sai với nguồn có thể chứa `null`:

~~~java
// Không dùng null làm tín hiệu kết thúc Iterator.
while (iterator.next() != null) {
    // Không biểu đạt đúng việc còn phần tử.
}
~~~

Nó có thể dừng trước Y, hoặc ném ngoại lệ khi không gặp `null` trước lúc hết dữ liệu. Dùng `hasNext()` để kiểm tra kết thúc.

Phân biệt thêm:

- `List.of(...)` không chấp nhận phần tử `null`.
- `Arrays.asList(...)` có thể chứa phần tử `null`.
- Iterator không áp đặt một chính sách `null` chung cho mọi nguồn.

Vấn đề nằm ở nguồn dữ liệu và cách dùng giá trị trả về, không phải ở việc Java dùng `null` để đánh dấu hết iterator.

## 5. forEachRemaining: xử lý từ vị trí hiện tại đến hết

Ví dụ đã lấy một phần tử:

~~~java
Iterator<String> iterator = List.of("A", "B", "C", "D").iterator();

System.out.println(iterator.next()); // A
iterator.forEachRemaining(System.out::println);
~~~

Stdout:

~~~text
A
B
C
D
~~~

Dòng A đến từ `next()`. `forEachRemaining` chỉ xử lý B, C, D.

Nếu muốn xem riêng phần mà callback đã xử lý:

~~~java
Iterator<String> remainderIterator = List.of("A", "B", "C", "D").iterator();
remainderIterator.next(); // Đã lấy A.
List<String> remaining = new ArrayList<>();
remainderIterator.forEachRemaining(remaining::add);
System.out.println(remaining); // [B, C, D]
~~~

Danh sách `remaining` nhận phần chưa được lấy từ **iterator đó**. Nó không tự lấy lại các phần tử mà iterator đã đi qua.

### Ý tưởng của triển khai mặc định

Có thể đọc hành vi theo dạng vòng lặp:

~~~java
while (iterator.hasNext()) {
    action.accept(iterator.next());
}
~~~

`action` là hành động truyền vào, không phải một kết quả mới. Triển khai cụ thể có thể ghi đè phương thức để thực hiện phù hợp với cấu trúc nội bộ, nên không suy ra mọi iterator đều dùng đúng một đoạn bytecode giống vòng lặp trên.

Điều cần giữ là ý nghĩa xử lý phần còn lại và thứ tự duyệt đã được nguồn cam kết.

### Sau khi hoàn tất bình thường

Với một lượt duyệt hữu hạn trên nguồn ổn định, khi `forEachRemaining` hoàn tất bình thường:

- Phần còn lại đã được xử lý.
- `hasNext()` trả `false`.
- Gọi lại `forEachRemaining` với một hành động hợp lệ không có phần tử mới để xử lý.
- `next()` trên lượt duyệt đã hết ném `NoSuchElementException`.

Không dùng `forEachRemaining` nếu cần chỉ xử lý một phần giới hạn hoặc một nguồn có thể vô hạn. Nó không tự có điều kiện dừng nghiệp vụ ngoài việc hết dữ liệu hoặc phát sinh ngoại lệ.

## 6. Consumer: hành động trên phần tử, không phải phép biến đổi trả kết quả

Chữ ký:

~~~java
void forEachRemaining(Consumer<? super E> action)
~~~

Đây là chữ ký để đọc hiểu; không cần tự khai báo lại phương thức trong mã sử dụng iterator.

`Consumer` nhận một giá trị để thực hiện hành động và không trả về giá trị qua phương thức `accept`. Ví dụ:

~~~java
Iterator<String> iterator = List.of("A", "B").iterator();

iterator.forEachRemaining(value -> System.out.println(value));
~~~

Method reference tương đương trong ngữ cảnh này:

~~~java
iterator.forEachRemaining(System.out::println);
~~~

Nhưng nếu hai đoạn được gọi nối tiếp trên **cùng iterator**, đoạn thứ hai không tự chạy lại từ đầu. Tương đương nói về cách viết callback, không phải khả năng dùng lại dữ liệu đã đi qua.

### Consumer của kiểu cha

Vì có `? super E`, iterator của `String` có thể nhận một hành động phù hợp với `Object`:

~~~java
// Cần import java.util.function.Consumer.
Consumer<Object> print = value -> System.out.println(value);
Iterator<String> iterator = List.of("A", "B").iterator();

iterator.forEachRemaining(print);
~~~

Hành động nhận được mọi `String` vì `String` cũng là `Object`. Chiều ngược lại không an toàn: một hành động chỉ xử lý `String` không thể mặc nhiên nhận mọi phần tử từ `Iterator<Object>`.

### Không có List kết quả tự động

`forEachRemaining` trả `void`. Nếu cần tạo một danh sách mới, phải cung cấp nơi nhận:

~~~java
List<String> result = new ArrayList<>();
iterator.forEachRemaining(value -> result.add(value.toLowerCase()));
~~~

Đây là ví dụ cú pháp, giả định phần tử không `null`. Với việc chuẩn hóa chuỗi trong ứng dụng thực, cần chọn quy tắc ngôn ngữ và xử lý dữ liệu thiếu theo yêu cầu; không phải mọi phép chuyển chữ thường đều có cùng ý nghĩa nghiệp vụ.

Khi chỉ cần tích lũy hoặc biến đổi, vòng lặp thông thường cũng có thể là cách rõ ràng hơn. Không cần dùng callback cho mọi tác vụ.

## 7. Dừng sớm: vòng lặp có break, lambda return không dừng lượt duyệt

Nếu cần dừng tại B:

~~~java
Iterator<String> iterator = List.of("A", "B", "C", "D").iterator();

while (iterator.hasNext()) {
    String value = iterator.next();
    if (value.equals("B")) {
        break;
    }
    System.out.println(value);
}
~~~

A được in. B đã được lấy rồi mới làm vòng lặp dừng, nên phần còn lại của iterator là C, D.

Nếu sau đó gọi `iterator.forEachRemaining(...)`, nó bắt đầu từ C.

### Return trong lambda chỉ kết thúc lần gọi callback hiện tại

~~~java
List<String> accepted = new ArrayList<>();

List.of("A", "B", "C", "D").iterator().forEachRemaining(value -> {
    if (value.equals("B")) {
        return;
    }
    accepted.add(value);
});

System.out.println(accepted); // [A, C, D]
~~~

`return` không trả khỏi phương thức bên ngoài, không tự kết thúc `forEachRemaining`, và không mang nghĩa `break` của vòng lặp. Nó chỉ kết thúc xử lý callback cho B. Callback vẫn được gọi tiếp cho C và D.

Một lệnh `break` không thể nhảy từ bên trong lambda ra vòng lặp bên ngoài nó.

Có thể làm callback ném ngoại lệ, nhưng không nên dùng ngoại lệ giả làm lựa chọn mặc định cho điều kiện dừng bình thường. Với yêu cầu dừng sớm và tiếp tục quản lý trạng thái duyệt, vòng lặp thủ công diễn đạt mục đích trực tiếp hơn.

## 8. Ngoại lệ trong callback và công việc đã thực hiện

Ví dụ một hành động bị lỗi khi gặp B:

~~~java
List<String> completed = new ArrayList<>();
Iterator<String> iterator = List.of("A", "B", "C").iterator();

try {
    iterator.forEachRemaining(value -> {
        if (value.equals("B")) {
            throw new IllegalStateException("stop at B");
        }
        completed.add(value);
    });
} catch (IllegalStateException exception) {
    System.out.println(exception.getMessage());
}

System.out.println(completed); // [A]
~~~

Ngoại lệ của callback được đưa về cho người gọi. Hành động đã thực hiện với A không tự được hoàn tác. `forEachRemaining` không tạo một giao dịch cho toàn bộ dữ liệu.

Không nên sau đó suy đoán chắc chắn iterator đang đứng trước B, sau B hay tại C rồi tiếp tục xử lý theo giả định đó. Hợp đồng chung không bảo đảm hành vi tiếp theo của iterator sau khi callback ném ngoại lệ.

Nếu công việc cần retry:

- Xác định rõ phần nào đã thành công ở tầng nghiệp vụ.
- Không dùng vị trí nội bộ không được bảo đảm của iterator làm checkpoint.
- Thiết kế xử lý lặp an toàn hoặc lưu định danh/checkpoint theo yêu cầu.
- Tạo lại một lượt đọc phù hợp khi nguồn cho phép.

Đối với bài toán collection nhỏ trong bộ nhớ, có thể đơn giản chọn vòng lặp thủ công và xử lý lỗi rõ ở từng phần tử, thay vì cố tiếp tục một iterator vừa thất bại trong callback.

### Action không được null

~~~java
// Đoạn mã minh họa lỗi trên một iterator mới.
List.of("A").iterator().forEachRemaining(null);
~~~

Lời gọi ném `NullPointerException`. Phân biệt `action == null` với một phần tử nguồn là `null`: cái đầu là thiếu hành động, cái sau có thể là dữ liệu hợp lệ nếu nguồn cho phép.

## 9. Đừng thay đổi nguồn trong callback để “duyệt và sửa” tùy ý

Một hành động như sau không có ngữ nghĩa an toàn chung:

~~~java
// Ví dụ không nên dùng với một List thông thường.
iterator.forEachRemaining(value -> values.remove(value));
~~~

Việc thay đổi collection khi đang duyệt phải theo chính sách của iterator và nguồn cụ thể. Hợp đồng chung của `forEachRemaining` không bảo đảm hành vi nếu callback sửa collection, kể cả gọi thao tác thay đổi qua iterator, trừ khi một triển khai có quy định riêng.

Nếu mục tiêu là lọc phần tử, hãy xem một cơ chế phù hợp như:

- Vòng lặp iterator tường minh với `remove()` khi iterator thực sự hỗ trợ.
- `Collection.removeIf(...)` khi collection hỗ trợ thay đổi và điều kiện xử lý phù hợp.
- Tạo collection kết quả mới mà không sửa nguồn đang duyệt.

`Iterator.remove()` là thao tác tùy chọn. Không phải mọi iterator đều hỗ trợ, và việc gọi nó sau `forEachRemaining` không có bảo đảm chung để dùng làm cách xóa phần tử cuối đã xử lý.

Những iterator phát hiện thay đổi có thể ném `ConcurrentModificationException`, nhưng không dùng ngoại lệ đó như một cơ chế đồng bộ hoặc bằng chứng chắc chắn mọi thay đổi sai đều được phát hiện.

## 10. Một iterator dùng một lượt, tạo iterator mới không sao chép dữ liệu

~~~java
List<String> values = List.of("A", "B");

Iterator<String> first = values.iterator();
Iterator<String> second = values.iterator();

System.out.println(first.next());  // A
System.out.println(first.next());  // B
System.out.println(second.next()); // A
~~~

Hai iterator của danh sách này có trạng thái duyệt riêng. `second` chưa đi qua phần tử nào khi `first` đã đi đến cuối.

Tuy nhiên, cả hai cùng đọc nguồn `values`. Chúng không phải hai bản sao độc lập của các phần tử hay của collection.

### Gán biến khác không tạo iterator mới

~~~java
Iterator<String> first = values.iterator();
Iterator<String> alias = first;

System.out.println(first.next()); // A
System.out.println(alias.next()); // B
~~~

`alias` và `first` cùng tham chiếu một iterator. Việc một biến gọi `next` thay đổi trạng thái mà biến kia quan sát được.

Nếu cần hai lượt độc lập, tạo hai iterator từ nguồn có hỗ trợ. Không mặc nhiên mọi nguồn `Iterable` đều cung cấp một snapshot giống nhau qua nhiều lần duyệt; với ví dụ `List.of` không thay đổi ở đây, nội dung giữa các lượt là xác định.

### Bẫy tạo lại iterator trong vòng lặp

~~~java
// Ví dụ sai nếu values không rỗng và không bị thay đổi.
while (values.iterator().hasNext()) {
    System.out.println(values.iterator().next());
}
~~~

Mỗi lần lại tạo một iterator từ đầu. Vòng lặp không duy trì tiến độ, nên có thể in mãi phần tử đầu.

Tạo iterator một lần trước vòng lặp:

~~~java
Iterator<String> iterator = values.iterator();
while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
~~~

## 11. Quan hệ với for-each và forEach của nguồn

For-each trên một nguồn `Iterable` có ý tưởng duyệt tương ứng:

~~~java
for (String value : values) {
    System.out.println(value);
}
~~~

Có thể đọc gần với:

~~~java
for (Iterator<String> iterator = values.iterator(); iterator.hasNext(); ) {
    String value = iterator.next();
    System.out.println(value);
}
~~~

Đây là giải thích cho trường hợp nguồn `Iterable`; for-each còn hỗ trợ mảng bằng cơ chế ngôn ngữ riêng. Mảng không vì vậy mà triển khai `Iterable`. Quy tắc được nêu trong [JLS 17, enhanced for statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.14.2).

Điểm khác về phạm vi sử dụng:

| Cách duyệt | Điểm bắt đầu trong ví dụ List | Điều khiển dừng |
| --- | --- | --- |
| For-each trên `values` | Một lượt duyệt của danh sách | Có `break` và `continue`. |
| `values.forEach(action)` | Xử lý danh sách theo hợp đồng của nguồn | Callback, không có `break` thoát khỏi lời gọi. |
| `iterator.forEachRemaining(action)` | Vị trí hiện tại của iterator đã có | Callback cho đến hết hoặc có ngoại lệ. |
| `while (iterator.hasNext())` | Vị trí hiện tại của iterator đã có | Chủ động từng bước và dừng sớm bằng `break`. |

Nếu đã gọi `iterator.next()`, sau đó gọi `values.forEach(...)` trên danh sách nguồn, thao tác nguồn không tự dùng tiến độ của iterator riêng đó. Ngược lại, gọi `iterator.forEachRemaining(...)` sẽ dùng đúng tiến độ hiện tại.

Chọn cách viết dựa trên mức điều khiển cần thiết. Chỉ cần duyệt toàn bộ nguồn thì for-each thường gọn. Cần chia một lượt thành nhiều giai đoạn, dừng sớm hoặc truyền phần còn lại sang một hàm thì iterator tường minh có ý nghĩa hơn.

## 12. Chương trình hoàn chỉnh

Lưu thành **IteratorMethodsDemo.java**. Phần `Countdown` minh họa một iterator tự tạo có nguồn là trạng thái số đếm, không cần một collection chứa sẵn mọi phần tử.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

public class IteratorMethodsDemo {
    public static void main(String[] args) {
        List<String> letters = List.of("A", "B", "C", "D");
        Iterator<String> iterator = letters.iterator();

        System.out.println("hasNext first = " + iterator.hasNext());
        System.out.println("hasNext again = " + iterator.hasNext());
        System.out.println("next = " + iterator.next());

        List<String> remaining = new ArrayList<>();
        iterator.forEachRemaining(remaining::add);
        System.out.println("Remaining = " + remaining);
        System.out.println("hasNext after drain = " + iterator.hasNext());

        List<String> secondDrain = new ArrayList<>();
        iterator.forEachRemaining(secondDrain::add);
        System.out.println("Second drain = " + secondDrain);

        try {
            iterator.next();
        } catch (NoSuchElementException exception) {
            System.out.println("next when exhausted = "
                    + exception.getClass().getSimpleName());
        }

        Iterator<String> fresh = letters.iterator();
        System.out.println("Fresh iterator next = " + fresh.next());
        System.out.println("Original iterator still exhausted = "
                + !iterator.hasNext());

        Iterator<String> withNull = Arrays.asList("X", null, "Y").iterator();
        List<String> nullData = new ArrayList<>();
        while (withNull.hasNext()) {
            nullData.add(withNull.next());
        }
        System.out.println("Null is data = " + nullData);

        Iterator<String> partial = letters.iterator();
        while (partial.hasNext()) {
            String value = partial.next();
            if (value.equals("B")) {
                break;
            }
        }
        List<String> afterBreak = new ArrayList<>();
        partial.forEachRemaining(afterBreak::add);
        System.out.println("Remaining after break at B = " + afterBreak);

        List<String> accepted = new ArrayList<>();
        letters.iterator().forEachRemaining(value -> {
            if (value.equals("B")) {
                return;
            }
            accepted.add(value);
        });
        System.out.println("Lambda return skips B only = " + accepted);

        List<String> beforeFailure = new ArrayList<>();
        Iterator<String> failing = letters.iterator();
        try {
            failing.forEachRemaining(value -> {
                if (value.equals("B")) {
                    throw new IllegalStateException("stop at B");
                }
                beforeFailure.add(value);
            });
        } catch (IllegalStateException exception) {
            System.out.println("Consumer error = " + exception.getMessage());
        }
        System.out.println("Completed actions before error = " + beforeFailure);
        // Do not use the failing iterator again.

        try {
            letters.iterator().forEachRemaining(null);
        } catch (NullPointerException exception) {
            System.out.println("Null action = "
                    + exception.getClass().getSimpleName());
        }

        Iterator<Integer> countdown = new Countdown(3);
        System.out.println("Countdown next = " + countdown.next());
        List<Integer> tail = new ArrayList<>();
        countdown.forEachRemaining(tail::add);
        System.out.println("Countdown remaining = " + tail);
        System.out.println("Countdown exhausted = " + !countdown.hasNext());
        System.out.println("Source unchanged = " + letters);
    }

    private static final class Countdown implements Iterator<Integer> {
        private int remaining;

        private Countdown(int start) {
            if (start < 0) {
                throw new IllegalArgumentException("start must be non-negative");
            }
            remaining = start;
        }

        @Override
        public boolean hasNext() {
            return remaining > 0;
        }

        @Override
        public Integer next() {
            if (!hasNext()) {
                throw new NoSuchElementException();
            }
            return remaining--;
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 IteratorMethodsDemo.java
java IteratorMethodsDemo
~~~

Stdout:

~~~text
hasNext first = true
hasNext again = true
next = A
Remaining = [B, C, D]
hasNext after drain = false
Second drain = []
next when exhausted = NoSuchElementException
Fresh iterator next = A
Original iterator still exhausted = true
Null is data = [X, null, Y]
Remaining after break at B = [C, D]
Lambda return skips B only = [A, C, D]
Consumer error = stop at B
Completed actions before error = [A]
Null action = NullPointerException
Countdown next = 3
Countdown remaining = [2, 1]
Countdown exhausted = true
Source unchanged = [A, B, C, D]
~~~

### Giải thích từng nhóm kết quả

**Hai lần hasNext**

Cả hai trả `true`, và `next` vẫn lấy A. Việc hỏi còn dữ liệu không tự đi qua A.

**Remaining và Second drain**

A đã được lấy trước, nên `forEachRemaining` thu B, C, D. Lần xử lý tiếp theo có danh sách kết quả rỗng vì iterator đã hết.

**next khi hết**

Chương trình bắt đúng `NoSuchElementException` và in tên ngoại lệ. Không dùng ngoại lệ này làm cách điều khiển thông thường thay cho `hasNext`.

**Fresh iterator**

Iterator mới từ danh sách bắt đầu ở A; iterator cũ vẫn đã hết. Hai trạng thái riêng không làm danh sách nguồn bị sao chép hoặc thay đổi.

**Null is data**

Iterator đi qua X, `null`, Y. Điều kiện vòng lặp kiểm tra `hasNext`, nên không dừng nhầm ở phần tử `null`.

**Break và lambda return**

Vòng lặp lấy B rồi dừng, để lại C, D. Lambda chỉ bỏ hành động thêm B, vẫn thêm A, C, D khi các callback tương ứng chạy.

**Callback thất bại**

Hành động với A đã hoàn tất trước khi lỗi xảy ra ở B. Chương trình không sử dụng lại iterator `failing`, tránh dựa vào hành vi tiếp theo không được hợp đồng chung bảo đảm.

**Countdown**

`next()` lấy `3`, sau đó `forEachRemaining` nhận `2, 1`. Lớp chỉ cài `hasNext` và `next`, nên sử dụng phương thức mặc định cho phần còn lại. Khi không còn giá trị, `next` tự kiểm tra và ném đúng ngoại lệ thay vì trả một giá trị giả.

**Source unchanged**

Những lời gọi lấy hoặc duyệt phần tử không xóa nội dung danh sách. Các danh sách phụ được dùng để thu kết quả, còn nguồn vẫn là A, B, C, D.

## 13. Tự tạo iterator: những trách nhiệm tối thiểu

Một iterator tự cài đặt cần có mô hình trạng thái rõ:

- Phần tử tiếp theo là gì.
- Khi nào hết.
- `hasNext` xác định còn phần tử như thế nào.
- `next` chuyển trạng thái ra sao và xử lý khi đã hết.
- Nguồn có cho phép sửa trong khi duyệt hay không.

Ví dụ `Countdown` nhận số bắt đầu không âm. Trạng thái `remaining` vừa cho biết giá trị tiếp theo, vừa xác định đã hết khi bằng `0`. Không có phần tử số `0` trong miền của iterator mẫu này.

Không cần ghi đè `forEachRemaining` chỉ để có khả năng sử dụng nó. Nếu ghi đè để tối ưu, vẫn phải tôn trọng các hợp đồng liên quan của phương thức, bao gồm xử lý hành động `null` và thứ tự nếu iterator đã cam kết.

Một interface `Iterator` không tự cung cấp `reset()`, `previous()`, `size()` hoặc `close()`. Nhu cầu duyệt ngược, biết số lượng hay quản lý tài nguyên cần xem hợp đồng và lớp cụ thể. Chẳng hạn, `ListIterator` có thêm khả năng phù hợp với danh sách, nhưng không phải mọi iterator đều là `ListIterator`.

Đặc biệt, đừng giả định chỉ cần giữ một `Iterator` là đã quản lý đầy đủ vòng đời của tài nguyên bên ngoài như tệp hoặc kết nối. Hợp đồng tài nguyên phải được xử lý ở cấp API đã tạo ra nguồn đó.

## 14. Kiểm thử và lỗi thường gặp

Các ca kiểm thử cơ bản:

1. Nguồn rỗng: `hasNext` là `false`; callback hợp lệ không được gọi; `next` ném ngoại lệ.
2. Một phần tử: nhiều lần `hasNext` trước `next` không làm mất phần tử.
3. Nhiều phần tử: lấy một vài phần tử rồi `forEachRemaining` chỉ xử lý phần dư đúng thứ tự được cam kết.
4. Phần tử `null` khi nguồn cho phép: không nhầm với kết thúc.
5. Hành động `null`: bị từ chối bằng ngoại lệ.
6. Callback có lỗi: lỗi được chuyển về người gọi; không viết ca kiểm thử ép một vị trí tiếp tục mà hợp đồng không bảo đảm.
7. Hai iterator và hai biến cùng trỏ một iterator: phân biệt trạng thái riêng với trạng thái dùng chung.

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `hasNext` trong vòng lặp | Không tiến trạng thái, có thể lặp vô hạn | Lấy phần tử bằng `next` đúng vị trí. |
| Gọi `next` hai lần cho cùng một bước xử lý | Bỏ qua phần tử hoặc gặp hết dữ liệu bất ngờ | Lưu giá trị vào biến rồi dùng lại. |
| Dùng `null` làm dấu hết | Dừng sai với nguồn có phần tử `null` | Dùng `hasNext`. |
| Nghĩ `next` xóa phần tử khỏi collection | Nhầm trạng thái duyệt với dữ liệu nguồn | Phân biệt lấy qua iterator với thao tác thay đổi nguồn. |
| Nghĩ `forEachRemaining` chạy lại từ đầu | Bỏ qua phần đã tiêu thụ hoặc kỳ vọng sai kết quả | Xét vị trí hiện tại của đúng iterator. |
| Dùng `return` trong lambda để dừng toàn bộ | Các phần tử sau vẫn được xử lý | Dùng vòng lặp tường minh khi cần `break`. |
| Tạo lại iterator mỗi lần trong điều kiện hoặc thân vòng lặp | Không duy trì được tiến độ | Tạo một iterator cho một lượt. |
| Sửa collection trong callback mà không xét hợp đồng | Có thể có hành vi không được bảo đảm hoặc ngoại lệ | Chọn cơ chế sửa phù hợp với nguồn. |
| Tiếp tục iterator sau callback ném lỗi theo một vị trí tự đoán | Có thể lặp, bỏ sót hoặc xử lý sai dữ liệu | Thiết kế xử lý lỗi và checkpoint ở tầng thích hợp. |

## 15. Thực hành

1. Với nguồn A, B, C, D, E, gọi `next` hai lần rồi thu `forEachRemaining` vào danh sách mới. Dự đoán và chạy kiểm tra phần còn lại.
2. Viết vòng lặp xử lý tối đa hai phần tử nhưng giữ iterator để một đoạn mã sau xử lý phần dư.
3. Tạo nguồn có `null` ở đầu, giữa và cuối. Chứng minh vòng lặp dựa trên `hasNext` vẫn duyệt đúng số phần tử.
4. So sánh hai iterator độc lập với hai biến cùng trỏ một iterator bằng các lời gọi `next` xen kẽ.
5. Chạy một callback có `return` ở điều kiện cụ thể và chứng minh nó chỉ bỏ qua hành động hiện tại.
6. Viết một iterator đếm tăng trong một khoảng hữu hạn, kiểm tra nguồn rỗng và `next` sau khi hết. Dùng luôn `forEachRemaining` mặc định.
7. Với yêu cầu “dừng ở phần tử khớp điều kiện”, xác định phần tử khớp đã bị lấy khỏi lượt duyệt chưa và viết kiểm thử phần dư tương ứng.

Một lượt duyệt có một trạng thái tiến dần. `hasNext` kiểm tra, `next` lấy một bước, còn `forEachRemaining` xử lý phần dư. Khi giữ rõ ba vai trò này, các tình huống dừng sớm, dùng lại biến và nối nhiều giai đoạn xử lý sẽ dễ suy luận hơn.
