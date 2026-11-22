# descendingIterator và duyệt theo hướng ngược

## 1. Duyệt ngược một deque để làm gì?

Một hàng đợi hai đầu (deque) có thứ tự từ **First** đến **Last**. Đôi khi ta muốn quan sát các phần tử theo hướng ngược lại mà vẫn giữ nguyên nội dung và thứ tự của deque.

Ví dụ, một deque ghi các bước đã thực hiện:

```text
First                                      Last
  |                                          |
  v                                          v
[ START ] ----- [ A ] ----- [ B ] ----- [ END ]

Duyệt thông thường: START -> A -> B -> END
Duyệt ngược:        END -> B -> A -> START
```

`descendingIterator()` tạo một `Iterator<E>` để đi từ Last về First. Đây là hướng của **thứ tự hiện tại trong deque**, không nhất thiết là thứ tự ngược thời gian thêm phần tử.

Phương thức hữu ích khi muốn:

- Hiển thị một dãy bước từ cuối về đầu.
- Tìm từ đầu sau mà không lấy các phần tử ra.
- Kiểm tra trạng thái cuối dãy trước.
- Tạo một danh sách kết quả theo hướng ngược.

Điểm cần nhớ ngay từ đầu: **đổi hướng duyệt không phải đổi thứ tự lưu trữ**. Nếu chỉ gọi `hasNext()` và `next()`, mã không xóa phần tử khỏi deque. [Hướng duyệt của Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html)

Ví dụ trong bài dùng Java 17 trở lên và các API hiện vẫn áp dụng. Không cần cài một môi trường Java 6 để sử dụng cơ chế này.

## 2. Iterator là trạng thái của một lượt duyệt

Kết quả của `descendingIterator()` là một đối tượng `Iterator<E>`. Nó giữ trạng thái để biết vị trí tiếp theo của lượt duyệt.

Mẫu cơ bản:

```java
// Minh họa trong phương thức; steps là Deque<String>.
Iterator<String> it = steps.descendingIterator();
while (it.hasNext()) {
    String step = it.next();
    System.out.println(step);
}
```

Hai phương thức có vai trò khác nhau:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `hasNext()` | Còn phần tử tiếp theo trong lượt duyệt không? |
| `next()` | Trả phần tử tiếp theo và tiến trạng thái iterator |

`hasNext()` không lấy phần tử kế tiếp ra cho người gọi. Nếu có dữ liệu nhưng vòng lặp không gọi `next()`, iterator không tiến qua dữ liệu đó.

`next()` cũng không có nghĩa “lấy và xóa khỏi deque”. Nó chỉ tiến vị trí của lượt duyệt. Đây là khác biệt quan trọng so với `pollLast()`.

Khi iterator hết phần tử:

- `hasNext()` trả `false`.
- Gọi tiếp `next()` ném `NoSuchElementException`.
- Iterator không tự quay về cuối để bắt đầu lại.

Muốn duyệt lại, tạo một iterator mới. Nó bắt đầu một lượt duyệt mới trên deque, theo chính sách của triển khai và trạng thái phù hợp tại thời điểm đó. [Hợp đồng Iterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html)

### Vì sao vẫn dùng next khi đang đi ngược?

Tên `next()` nói về phần tử kế tiếp **trong lượt duyệt**, không nói rằng luôn đi từ First đến Last.

Với iterator thông thường của deque, phần tử kế tiếp đi về phía Last. Với descending iterator, phần tử kế tiếp đi về phía First. Không cần một phương thức `previous()` để dùng hướng ngược này.

`descendingIterator()` không trả `ListIterator`; nó không cung cấp toàn bộ khả năng đi tới rồi đi lui tùy ý của một trình duyệt danh sách hai chiều.

## 3. Hướng ngược dựa trên thứ tự hiện tại, không phải lịch sử thao tác

Giả sử lần lượt thực hiện:

```text
addLast("A")    -> [ A ]
addLast("B")    -> [ A, B ]
addFirst("X")   -> [ X, A, B ]
```

Thứ tự thêm theo thời gian là A, B, X. Nhưng descending iterator sẽ duyệt B, A, X, bởi Last hiện là B và First hiện là X.

Nếu muốn hiển thị “mới nhất trước”, chỉ dùng descending iterator là đủ khi quy ước của chương trình luôn thêm phần tử mới vào Last và không thay đổi ý nghĩa thứ tự ấy bằng các thao tác khác.

Trước khi chọn hướng duyệt, hãy hỏi: thứ tự của deque đang biểu diễn điều gì?

- Thứ tự tiếp nhận?
- Thứ tự xử lý?
- Thứ tự một thuật toán tự sắp xếp bằng các thao tác hai đầu?
- Một dãy bước mà đầu sau là bước sau cùng?

Deque giữ vị trí tương đối do mã thao tác tạo ra. Nó không tự gắn hay so sánh thời gian phát sinh sự kiện.

## 4. Phân biệt duyệt ngược, lấy ngược và đảo dữ liệu

Ba thao tác sau có thể in cùng thứ tự nhưng có tác động khác nhau:

| Cách làm | Dữ liệu được quan sát theo hướng nào? | Có xóa phần tử? | Có đổi thứ tự của deque gốc? |
| --- | --- | --- | --- |
| `descendingIterator()` rồi `next()` | Last về First | Không, nếu không gọi xóa | Không |
| Lặp `pollLast()` | Từ phần tử cuối đang còn lại | Có | Không đảo; nhưng dữ liệu bị lấy dần |
| Tạo danh sách riêng theo hướng ngược | Theo thứ tự được thêm vào danh sách mới | Không tự xóa ở nguồn | Không tự đổi deque gốc |

Ví dụ, đọc một lịch sử để hiển thị thường không nên xóa lịch sử. Ngược lại, một thuật toán hoàn tác có thể chủ động tiêu thụ các bước từ cuối.

Nếu thay descending iterator bằng một vòng lặp `pollLast()` chỉ vì cùng in END, B, A, START, chương trình sẽ làm rỗng deque. Kết quả hiển thị giống nhau không chứng minh tác dụng phụ giống nhau.

Tên “descending” cũng không có nghĩa dữ liệu được sắp xếp giảm dần theo giá trị. Với deque chứa 10, 3, 8 từ First đến Last, descending iterator trả 8, 3, 10; nó không so sánh để tạo 10, 8, 3.

## 5. Chương trình hoàn chỉnh

Ví dụ sau kiểm chứng năm điều:

1. Hướng thông thường khác hướng ngược.
2. Duyệt không xóa dữ liệu.
3. Iterator đã hết không tự khởi động lại.
4. Có thể xóa qua chính iterator của `ArrayDeque` khi tuân thủ hợp đồng.
5. Muốn có một danh sách kết quả riêng, phải chủ động tạo nó.

Lưu tệp `DescendingIteratorDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.StringJoiner;

public class DescendingIteratorDemo {
    public static void main(String[] args) {
        Deque<String> steps = new ArrayDeque<>();
        steps.addLast("A");
        steps.addLast("B");
        steps.addFirst("START");
        steps.addLast("END");

        System.out.println("forward=" + String.join(" -> ", steps));

        Iterator<String> reverse = steps.descendingIterator();
        StringJoiner order = new StringJoiner(" -> ");
        while (reverse.hasNext()) {
            order.add(reverse.next());
        }
        System.out.println("reverse=" + order);
        System.out.println("unchanged=" + steps);
        System.out.println("exhausted=" + reverse.hasNext());

        Iterator<String> filter = steps.descendingIterator();
        while (filter.hasNext()) {
            if (filter.next().equals("B")) {
                filter.remove();
            }
        }
        System.out.println("afterRemove=" + steps);

        List<String> snapshot = new ArrayList<>();
        steps.descendingIterator().forEachRemaining(snapshot::add);
        steps.addLast("LATE");
        System.out.println("snapshot=" + snapshot);
        System.out.println("current=" + steps);

        Iterator<String> empty =
                new ArrayDeque<String>().descendingIterator();
        System.out.println("emptyHasNext=" + empty.hasNext());
        try {
            empty.next();
        } catch (java.util.NoSuchElementException e) {
            System.out.println("emptyNext=" + e.getClass().getSimpleName());
        }
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac --release 17 DescendingIteratorDemo.java
java DescendingIteratorDemo
```

Stdout:

```text
forward=START -> A -> B -> END
reverse=END -> B -> A -> START
unchanged=[START, A, B, END]
exhausted=false
afterRemove=[START, A, END]
snapshot=[END, A, START]
current=[START, A, END, LATE]
emptyHasNext=false
emptyNext=NoSuchElementException
```

### Vì sao có START trước A dù được thêm sau?

Hai lời gọi `addLast` tạo A, B. `addFirst("START")` chèn vào đầu trước, rồi `addLast("END")` thêm vào đầu sau. Vì thế thứ tự hiện tại là START, A, B, END.

### Vì sao unchanged vẫn còn đủ bốn phần tử?

Vòng lặp chỉ gọi `hasNext` và `next`, rồi ghép các chuỗi vào `StringJoiner`. Không có thao tác xóa deque. Việc iterator đã đi hết dữ liệu chỉ làm iterator hết phần tử, không làm deque rỗng.

Tên `exhausted` trên stdout là nhãn minh họa; giá trị được in là kết quả `hasNext()`, nên `false` nghĩa iterator không còn phần tử.

### Vì sao sau remove chỉ mất B?

Iterator `filter` đi theo thứ tự END, B, A, START. Khi `next()` vừa trả B, mã gọi `filter.remove()`, xóa chính B khỏi deque.

“Xóa trong lúc duyệt ngược” không có nghĩa tự xóa Last hoặc First. Đối tượng bị xóa là phần tử mà iterator vừa trả về.

### Vì sao snapshot không có LATE?

Danh sách `snapshot` được tạo và nạp xong trước khi thêm LATE vào deque. Danh sách riêng không tự nhận phần tử được thêm sau đó vào nguồn.

Đây là kết quả của thao tác sao chép chủ động trong ví dụ, không phải thuộc tính mặc định của descending iterator.

## 6. Xóa đúng cách trong lúc duyệt ngược

`Iterator.remove()` là thao tác tùy chọn trong hợp đồng `Iterator`; không nên giả định mọi iterator đều hỗ trợ nó. Iterator của `ArrayDeque` trong ví dụ có hỗ trợ.

Đối với cách sử dụng trong vòng lặp thông thường:

- Phải có một lần `next()` thành công trước khi gọi `remove()`.
- Mỗi lần `next()` chỉ cho phép một lần `remove()`.
- Gọi `remove()` trước lần `next()` đầu tiên, hoặc gọi hai lần cho cùng một phần tử, vi phạm trạng thái sử dụng và có thể gây `IllegalStateException` ở iterator hỗ trợ xóa.
- Một iterator không hỗ trợ thao tác xóa có thể ném `UnsupportedOperationException`.

Ví dụ trong bài dùng chính `filter.remove()`. Không thay nó bằng `steps.remove(...)` ngay trong lượt duyệt rồi mong iterator tự điều chỉnh theo cách giống hệt.

Việc xóa bằng giá trị còn có thể chọn một phần tử khác nếu deque chứa nhiều giá trị bằng nhau. Xóa qua iterator gắn với vị trí vừa được trả về trong lượt duyệt, nên thể hiện đúng ý định loại phần tử đang xét.

Nếu chỉ cần hiển thị hoặc tìm kiếm, không gọi `remove`. Cần nhìn rõ ranh giới giữa một lượt quan sát dữ liệu và một lượt lọc có thay đổi nguồn.

## 7. Không sửa trực tiếp deque trong lúc iterator của ArrayDeque đang hoạt động

`ArrayDeque` không tự an toàn khi nhiều luồng truy cập. Các iterator của nó có cơ chế phát hiện một số thay đổi không phù hợp trong khi duyệt, thường được gọi là **fail-fast**.

Điểm cần hiểu là cơ chế này chỉ cố gắng phát hiện lỗi sử dụng. Không được dựa vào việc chắc chắn có `ConcurrentModificationException` để đồng bộ chương trình hoặc chứng minh lượt đọc nhất quán. Không thấy ngoại lệ cũng không chứng minh việc thay đổi xen kẽ là hợp lệ. [Chính sách iterator của ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html)

Ví dụ về ý tưởng cần tránh:

```java
// Minh họa cách dùng không hợp lệ với ArrayDeque; không dùng để kiểm thử
// rằng một ngoại lệ nhất định luôn phải xuất hiện tại một dòng nhất định.
Iterator<String> it = steps.descendingIterator();
steps.addLast("NEW");
while (it.hasNext()) {
    System.out.println(it.next());
}
```

Cách thiết kế phù hợp tùy mục tiêu:

- Hoàn tất thay đổi trước khi tạo iterator.
- Nếu cần lọc ngay trong lượt duyệt và iterator hỗ trợ, dùng `iterator.remove()` đúng hợp đồng.
- Nếu cần tách việc đọc khỏi thay đổi, thu kết quả cần thiết vào cấu trúc riêng rồi thực hiện thay đổi ở giai đoạn sau.
- Nếu nhiều luồng cùng thao tác, chọn cơ chế đồng thời và yêu cầu nhất quán rõ ràng.

Một bản sao cũng phải được tạo trong điều kiện truy cập nguồn hợp lệ. Tạo bản sao từ `ArrayDeque` đang bị một luồng khác sửa mà không phối hợp không tự trở thành an toàn chỉ vì kết quả cuối là một `List`.

## 8. Descending iterator không phải bản chụp bất biến

Đừng hiểu việc tạo iterator như một thao tác đóng băng toàn bộ deque tại thời điểm gọi. Khả năng quan sát khi nguồn thay đổi phụ thuộc triển khai.

Ví dụ, iterator của `ConcurrentLinkedDeque` có tính nhất quán yếu (weakly consistent). Nó được thiết kế cho môi trường đồng thời nhưng không phải một bản chụp nguyên tử của toàn bộ deque. Việc chọn lớp an toàn đa luồng không tự làm một lượt duyệt trở thành một giao dịch đọc. [Chính sách ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html)

Nếu yêu cầu là “báo cáo phải thể hiện đúng cùng một thời điểm”, cần thiết kế cách chụp dữ liệu hoặc phối hợp truy cập phù hợp, thay vì chỉ đổi iterator thông thường thành descending iterator.

### Bản sao trong ví dụ sao chép những gì?

`snapshot` là danh sách riêng, nên việc thêm LATE vào deque sau khi sao chép xong không thêm LATE vào danh sách.

Nhưng thao tác ấy chỉ sao chép các tham chiếu phần tử, không tự tạo bản sao sâu của từng đối tượng. Trong ví dụ, phần tử là `String`, một kiểu bất biến, nên dễ quan sát.

Nếu phần tử là đối tượng có trường có thể thay đổi, deque và danh sách có thể cùng tham chiếu tới đối tượng ấy. Sửa nội dung đối tượng vẫn có thể được nhìn thấy từ cả hai nơi. “Danh sách riêng” và “mọi đối tượng bên trong đều độc lập” là hai điều kiện khác nhau.

Danh sách `ArrayList` trong ví dụ cũng chưa phải danh sách bất biến: mã giữ tham chiếu tới nó vẫn có thể sửa nó. Tên biến `snapshot` diễn đạt mục đích sử dụng, không tạo thêm bảo đảm từ ngôn ngữ.

## 9. Dùng forEachRemaining đúng phạm vi

Có thể xử lý các phần tử còn lại của một descending iterator bằng `forEachRemaining`. Ví dụ trong chương trình:

```java
steps.descendingIterator().forEachRemaining(snapshot::add);
```

Hướng vẫn là Last về First vì iterator đã được tạo với hướng đó. `forEachRemaining` không tự chọn lại hướng.

Nếu iterator đã đi qua một số phần tử bằng `next()`, lời gọi này chỉ xử lý **phần còn lại**, không quay về đầu lượt duyệt. Nếu hàm xử lý ném ngoại lệ, không nên giả định toàn bộ phần còn lại đã được xử lý thành công.

Để làm thay đổi nguồn bằng `iterator.remove()`, nên dùng vòng lặp `next`/`remove` rõ ràng như ví dụ lọc B. Không kết hợp một cách tùy tiện việc sửa deque gốc hoặc gọi xóa iterator bên trong hàm xử lý của `forEachRemaining`; phải tuân thủ đúng các giới hạn được hợp đồng iterator quy định.

## 10. Những lỗi thường gặp

### Tạo iterator mới trong mỗi vòng lặp

```java
// Minh họa sai nếu mục đích là đi qua toàn bộ deque:
while (steps.descendingIterator().hasNext()) {
    System.out.println(steps.descendingIterator().next());
}
```

Mỗi lần lại tạo một lượt duyệt mới từ Last. Với deque không rỗng và không bị thay đổi, mã cứ đọc phần tử cuối.

Cần tạo iterator một lần trước vòng lặp, rồi tiến chính iterator đó.

### Gọi next để kiểm tra rồi gọi next lần nữa để xử lý

Lời gọi `next()` đã tiến iterator. Hai lần liên tiếp đọc hai vị trí khác nhau; phần tử đầu có thể bị bỏ qua và lần sau có thể vượt cuối.

Hãy lưu giá trị từ một lần `next()` vào biến và dùng biến đó.

### Cho rằng đã duyệt hết thì deque rỗng

Iterator hết phần tử chỉ có nghĩa lượt duyệt đã hoàn thành. Muốn xóa dữ liệu phải có thao tác thay đổi riêng.

### Dựa vào thứ tự thêm thay vì thứ tự hai đầu

Khi có `addFirst`, `push`, hoặc các thao tác thay đổi hai đầu, thứ tự thời gian và thứ tự trong deque có thể khác nhau. Hãy vẽ First đến Last trước khi dự đoán kết quả.

### Dùng iterator đã hết để chạy một vòng nữa

Một iterator không có lệnh tự khởi động lại. Tạo một iterator mới cho lượt duyệt mới, trong điều kiện truy cập nguồn phù hợp.

### Dùng fail-fast như một khóa đồng bộ

Ngoại lệ phát hiện thay đổi là công cụ hỗ trợ tìm lỗi, không thay thế cơ chế phối hợp giữa các luồng.

## 11. Thực hành dự đoán hướng duyệt và tác động

### Bài 1: Không sắp xếp theo giá trị

Deque có các số 4, 1, 9 từ First đến Last. Descending iterator trả gì?

Kết quả là 9, 1, 4. Nó không sắp xếp để tạo thứ tự giảm dần 9, 4, 1.

### Bài 2: Duyệt sau khi thêm ở cả hai đầu

Thực hiện `addLast("A")`, `addFirst("B")`, `addLast("C")`.

Thứ tự hiện tại là B, A, C. Hướng ngược trả C, A, B. Hãy so sánh với lịch sử thêm A, B, C để thấy chúng khác nhau.

### Bài 3: Phân biệt đọc và lấy

Tạo hai deque có cùng dữ liệu A, B, C.

- Với deque thứ nhất, in bằng descending iterator.
- Với deque thứ hai, in bằng cách lặp `pollLast()` đến khi rỗng.

Thứ tự in có thể giống C, B, A. Sau đó kiểm tra nội dung: deque thứ nhất vẫn có dữ liệu, deque thứ hai đã rỗng.

### Bài 4: Chọn đúng phần tử để xóa

Deque có A, B, C, D. Duyệt ngược và gọi `iterator.remove()` ngay sau khi `next()` trả C.

Deque còn A, B, D. Phần tử bị xóa là C, không phải D chỉ vì D nằm ở Last.

### Bài 5: Chọn bảo đảm cho báo cáo

Một báo cáo cần đọc lịch sử từ mới đến cũ trong khi nơi khác tiếp tục thêm dữ liệu.

Trước khi viết vòng lặp, hãy xác định:

1. Có thực sự cần một bản chụp tại cùng một thời điểm không?
2. Triển khai deque cho phép thay đổi đồng thời theo chính sách nào?
3. Nếu sao chép, giai đoạn đọc nguồn được bảo vệ như thế nào?
4. Các phần tử bên trong có thể bị sửa sau khi được sao chép không?

Đáp án không thể chỉ là “dùng descendingIterator”. Phương thức giải quyết **hướng duyệt**; yêu cầu về tính nhất quán, quyền thay đổi và thời điểm quan sát phải được thiết kế thêm.
