# Độ phức tạp của thêm, lấy, tìm kiếm và xóa theo giá trị

## 1. Cùng là thao tác trên ArrayDeque nhưng chi phí khác nhau

`ArrayDeque` thích hợp cho công việc tập trung vào hai đầu của một dãy phần tử: thêm đầu hoặc cuối, lấy đầu hoặc cuối. Khi chuyển sang tìm một giá trị bất kỳ hoặc xóa một phần tử ở giữa, chương trình phải làm thêm công việc.

Ví dụ, với deque:

```text
First -> [ A ] [ B ] [ C ] [ D ] [ E ] <- Last
```

- Lấy A ở đầu: đã biết vị trí cần đọc.
- Lấy E ở cuối: đã biết vị trí biên cần đọc.
- Hỏi có D không: phải tìm theo giá trị.
- Xóa C: phải tìm C rồi duy trì thứ tự của phần còn lại.

Vì vậy, không nên suy luận “dùng ArrayDeque thì mọi thao tác đều O(1)”. Phải đọc **đúng phương thức, đúng chữ ký và đúng loại phân tích**.

Bài dùng API hiện vẫn áp dụng trên Java hiện đại. Chương trình minh họa chạy được với JDK 17 trở lên; không yêu cầu môi trường Java 6.

## 2. Đặt giả định trước khi đọc Big O

Trong bài:

- `n` là số phần tử đang có trước một thao tác.
- O(1) nghĩa chi phí không tăng theo `n` trong mô hình phân tích đang xét.
- O(n) nghĩa trường hợp cần xét có thể làm lượng công việc tăng tuyến tính theo `n`.
- Chi phí so sánh bằng nhau được giả định là O(1), trừ khi nói khác.
- Chi phí in màn hình, công việc nghiệp vụ và hoạt động khác bên ngoài collection không được gộp vào một phép thao tác deque.

Big O không cho biết một lời gọi mất chính xác bao nhiêu mili giây. Hai thao tác cùng O(n) vẫn có thể có hệ số, cách cấp phát và đặc điểm truy cập bộ nhớ khác nhau.

Cũng cần phân biệt ba khái niệm:

| Cách xét | Câu hỏi |
| --- | --- |
| Trường hợp tốt nhất | Một lần gọi thuận lợi nhất phải làm bao nhiêu việc? |
| Trường hợp xấu nhất | Một lần gọi có thể phải làm nhiều nhất bao nhiêu việc theo quy mô dữ liệu? |
| Khấu hao | Trên cả chuỗi thao tác, những lần tốn kém được phân bổ thế nào? |

**Khấu hao không phải trung bình do may rủi.** Nó phân tích tổng chi phí của một chuỗi thao tác, không cần giả định rằng việc mở rộng xảy ra với một xác suất nào đó.

## 3. Bảng chi phí cần nhớ

Với `ArrayDeque`, đầu vào hợp lệ và một luồng sử dụng đúng hợp đồng:

| Nhóm | Ví dụ phương thức | Chi phí theo số phần tử | Lý do chính |
| --- | --- | --- | --- |
| Thêm đầu hoặc cuối | `addFirst`, `addLast`, `offerFirst`, `offerLast`, `push` | O(1) khấu hao; một lần phải mở rộng có thể O(n) | Thường chỉ cập nhật biên, đôi khi chuyển nhiều tham chiếu |
| Lấy đầu hoặc cuối | `pollFirst`, `pollLast`, `removeFirst`, `removeLast`, `pop` | O(1) | Dùng trực tiếp vị trí biên |
| Xem đầu hoặc cuối | `peekFirst`, `peekLast`, `getFirst`, `getLast` | O(1) | Không phải tìm theo giá trị |
| Tìm theo giá trị | `contains(value)` | O(n) trong trường hợp xấu nhất | Có thể kiểm tra toàn bộ phần tử |
| Xóa theo giá trị | `remove(Object)`, `removeFirstOccurrence`, `removeLastOccurrence` | O(n) trong trường hợp xấu nhất | Tìm phần tử, rồi sửa bộ chứa để giữ đúng dãy |
| Duyệt toàn bộ | Vòng lặp iterator | O(n), chưa tính công việc cho từng phần tử | Mỗi phần tử phải được quan sát |
| Xóa toàn bộ | `clear()` | O(n) | Phải bỏ các tham chiếu phần tử đang giữ |

Tài liệu API xác định phần lớn thao tác của `ArrayDeque` có chi phí hằng số khấu hao, đồng thời nêu các ngoại lệ tuyến tính như tìm kiếm, xóa theo giá trị và thao tác hàng loạt. [Tài liệu hiệu năng ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html)

Không dùng bảng này như một cam kết về độ trễ tuyệt đối của JVM. Cấp phát, thu gom rác, phần tử và môi trường chạy vẫn ảnh hưởng thời gian thực tế.

## 4. Vì sao thêm hai đầu là O(1) khấu hao?

`ArrayDeque` dựa trên mảng có thể mở rộng, với vị trí đầu và cuối được quản lý theo vòng. Khi còn chỗ, thêm một phần tử không cần dồn cả dãy để mở một vị trí ở đầu.

Một lần thêm thông thường chỉ cần công việc có phạm vi nhỏ:

```text
Chọn vị trí biên
    -> lưu tham chiếu phần tử
    -> cập nhật vị trí biên
```

Nhưng khi cần mở rộng:

```text
Cấp mảng lớn hơn
    -> chuyển hoặc sắp lại nhiều tham chiếu
    -> cập nhật các vị trí
    -> hoàn tất lần thêm
```

Lần mở rộng có thể liên quan đến lượng dữ liệu tỷ lệ với số phần tử hiện có. Vì vậy, khẳng định “mọi lần add đều O(1) ở trường hợp xấu nhất” là quá mạnh.

Mô hình mảng tăng theo cấp số nhân giúp giải thích khấu hao: sau một lần tăng, có thêm chỗ cho nhiều lần thêm thông thường. Tổng chi phí các lần chuyển dữ liệu trên một chuỗi thêm dài được phân bổ cho cả chuỗi, tạo chi phí O(1) khấu hao mỗi lần thêm.

Mô hình này không yêu cầu người dùng phụ thuộc một hệ số tăng cố định hay một kích thước mảng cụ thể. Những con số ấy là chi tiết triển khai.

### Dung lượng khởi tạo ảnh hưởng thực tế, không đổi bản chất thao tác

`new ArrayDeque<>(1000)` có thể giúp giảm việc tăng trưởng khi nhu cầu ban đầu đã biết. Nhưng số 1000 không phải giới hạn tối đa của deque và cũng không biến O(1) khấu hao thành lời cam kết mọi lời gọi có cùng thời gian.

Ngược lại, khởi tạo quá lớn có thể giữ một vùng chứa không cần thiết. Cần cân đối nhu cầu thực tế thay vì luôn chọn số rất lớn để tránh một chi phí chưa được đo.

## 5. Vì sao lấy ở hai đầu không cần tìm?

Ở đầu trước và đầu sau, cấu trúc đã biết vị trí cần thao tác. Lấy phần tử gồm đọc tham chiếu, bỏ tham chiếu tại ô đã dùng và cập nhật vị trí biên.

Điều này khác với mảng được sử dụng theo cách phải luôn giữ phần tử đầu tại chỉ số 0. Mảng vòng không phải dời cả dãy sang trái chỉ vì lấy một phần tử đầu.

Các cặp phương thức có thể khác cách báo rỗng nhưng cùng lấy ở một vị trí biên:

| Cặp | Khi có dữ liệu | Khi rỗng |
| --- | --- | --- |
| `pollFirst()` / `removeFirst()` | Lấy đầu trước | `null` / `NoSuchElementException` |
| `pollLast()` / `removeLast()` | Lấy đầu sau | `null` / `NoSuchElementException` |
| `peekFirst()` / `getFirst()` | Chỉ xem đầu trước | `null` / `NoSuchElementException` |

Chọn cách báo rỗng theo hợp đồng thuật toán. Không nên cố dùng ngoại lệ như một “tối ưu” thay cho việc hiểu rỗng là bình thường hay là vi phạm điều kiện.

`pop()` lấy đầu trước; `push(e)` thêm đầu trước. Nếu tên phương thức không ghi đầu được chọn, cần nhớ ánh xạ của nó, không suy đoán rằng đây là một thuật toán tìm kiếm riêng.

## 6. contains phải tìm như thế nào?

`ArrayDeque` không duy trì một bảng băm để trả lời có phần tử bằng một giá trị bất kỳ hay không. Để tìm theo giá trị, nó phải kiểm tra các phần tử theo cách duyệt của triển khai.

Các tình huống có thể khác nhau:

- Phần tử phù hợp được tìm ngay: công việc tìm kiếm có thể rất nhỏ.
- Phần tử nằm xa vị trí bắt đầu tìm: phải kiểm tra nhiều phần tử.
- Không có phần tử phù hợp: có thể phải kiểm tra toàn bộ deque.

Vì vậy, trường hợp tốt có thể O(1), nhưng trường hợp xấu nhất của `contains` là O(n).

Một lời gọi trả `false` không phải là một đường đi “rẻ hơn” chỉ vì không có kết quả để trả. Không tìm thấy thường là tình huống buộc phải kiểm tra hết các ứng viên.

### Nếu equals không có chi phí hằng số

Khi phần tử có phép so sánh bằng nhau tốn chi phí `c`, một phép tìm kiếm có thể cần xét cả số lần so sánh lẫn chi phí mỗi lần. Mô hình thô lúc này là O(n × c).

Ví dụ, so sánh các đối tượng chứa một dãy dữ liệu dài có thể tốn nhiều công việc hơn so sánh hai số nguyên nhỏ. Đây là lý do cần nêu giả định khi đọc một bảng Big O.

Không nên thay `equals` bằng so sánh tham chiếu chỉ để mong thao tác nhanh hơn nếu điều đó làm thay đổi ý nghĩa bằng nhau của bài toán.

## 7. Xóa theo giá trị gồm tìm và duy trì dãy

`remove(Object)` không được cung cấp sẵn vị trí phần tử. Nó phải tìm một phần tử bằng giá trị được yêu cầu, rồi loại phần tử đó.

Hợp đồng hướng tìm cũng quan trọng:

- `remove(Object)` tương ứng với xóa lần xuất hiện đầu tiên theo thứ tự deque.
- `removeFirstOccurrence` xóa lần xuất hiện đầu tiên.
- `removeLastOccurrence` xóa lần xuất hiện cuối cùng.

Với A, B, A, C, xóa lần xuất hiện đầu của A và xóa lần xuất hiện cuối của A cho hai kết quả khác nhau. Cả hai dạng theo giá trị vẫn có thể cần O(n). Từ “Last” trong `removeLastOccurrence` không làm nó tương đương `removeLast()`. [Ngữ nghĩa xóa theo giá trị của Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html)

### Tìm thấy rồi vẫn có thể phải dời tham chiếu

Một lỗ trống ở giữa dãy phải được xử lý để duy trì thứ tự và cách quản lý bộ chứa.

Trong mã OpenJDK 25 đã đối chiếu, thao tác xóa nội bộ chọn phía cần di chuyển ít phần tử hơn. Cách tối ưu này giảm lượng dịch chuyển trong nhiều tình huống, nhưng không làm cận xấu nhất trở thành O(1): xóa gần giữa vẫn có thể liên quan đến một số lượng phần tử tỷ lệ với n. [Mã nguồn xử lý xóa của OpenJDK 25](https://raw.githubusercontent.com/openjdk/jdk/jdk-25%2B36/src/java.base/share/classes/java/util/ArrayDeque.java)

Có thể hình dung:

```text
Trước: A, B, C, D, E, F, G
Xóa:           D

Cần duy trì dãy logic:
       A, B, C, E, F, G
```

Công việc không chỉ là đánh dấu “D đã mất”. Lớp triển khai còn phải bảo toàn các điều kiện quản lý dãy.

### Không tìm thấy thì không đổi dữ liệu, nhưng vẫn có chi phí

`remove(target)` trả `false` nếu không có phần tử được xóa. Dữ liệu giữ nguyên không có nghĩa lời gọi không làm việc: phần tìm kiếm có thể đã kiểm tra toàn bộ deque.

## 8. Đọc đúng overload: remove() khác remove(Object)

Với biến kiểu `Deque<Integer>`:

```java
Integer head = deque.remove(); // Lấy đầu và trả Integer.
boolean removed = deque.remove(3); // Xóa giá trị Integer 3, không phải chỉ số 3.
```

Deque không có thao tác xóa theo chỉ số như `List.remove(int)`. Trong lời gọi `deque.remove(3)`, số nguyên được dùng làm đối tượng giá trị để tìm.

Có thể viết `Integer.valueOf(3)` để làm ý định xóa theo giá trị rõ hơn với người đọc.

Đây là khác biệt vừa về ý nghĩa vừa về chi phí:

- Không đối số: thao tác ở đầu đã biết.
- Có đối tượng giá trị: phải xác định phần tử phù hợp trong dãy.

Chỉ nhìn tên “remove” rồi ghi O(1) cho cả hai là sai.

## 9. Chương trình hoàn chỉnh: kiểm chứng đúng thao tác trước khi phân tích

Lưu tệp `ArrayDequeCostDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class ArrayDequeCostDemo {
    public static void main(String[] args) {
        Deque<Integer> values = new ArrayDeque<>(1);
        for (int i = 1; i <= 5; i++) {
            values.addLast(i);
        }
        System.out.println("initial=" + values);
        System.out.println("contains3=" + values.contains(3));
        System.out.println("contains99=" + values.contains(99));

        System.out.println("removeValue3=" + values.remove(Integer.valueOf(3)));
        System.out.println("afterValueRemoval=" + values);

        values.addLast(2);
        System.out.println("withDuplicate=" + values);
        System.out.println("removeLast2=" + values.removeLastOccurrence(2));
        System.out.println("afterLastOccurrence=" + values);
        System.out.println("removeFirst2=" + values.removeFirstOccurrence(2));
        System.out.println("afterFirstOccurrence=" + values);

        System.out.println("takeEnds=" + values.removeFirst()
                + "," + values.removeLast());
        System.out.println("remaining=" + values);
        System.out.println("removeMissing=" + values.remove(Integer.valueOf(99)));
        System.out.println("afterMissing=" + values);
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac --release 17 ArrayDequeCostDemo.java
java ArrayDequeCostDemo
```

Stdout:

```text
initial=[1, 2, 3, 4, 5]
contains3=true
contains99=false
removeValue3=true
afterValueRemoval=[1, 2, 4, 5]
withDuplicate=[1, 2, 4, 5, 2]
removeLast2=true
afterLastOccurrence=[1, 2, 4, 5]
removeFirst2=true
afterFirstOccurrence=[1, 4, 5]
takeEnds=1,5
remaining=[4]
removeMissing=false
afterMissing=[4]
```

### Đọc ví dụ theo loại công việc

Vòng lặp đầu thêm năm phần tử, dù dung lượng khởi tạo là 1. Nó cho thấy dung lượng ban đầu không đặt giới hạn số phần tử được nhận.

Hai lần `contains` kiểm tra giá trị có và không có. Chúng không thay đổi dữ liệu.

`remove(Integer.valueOf(3))` xóa giá trị 3, nên dãy còn 1, 2, 4, 5.

Khi thêm một giá trị 2 vào cuối, deque có hai lần xuất hiện của 2. Xóa lần cuối loại 2 mới thêm; xóa lần đầu tiếp theo loại 2 còn lại. Hướng tìm là một phần của hành vi, không chỉ là lựa chọn đặt tên.

`removeFirst()` và `removeLast()` lấy trực tiếp hai đầu hiện tại là 1 và 5. Chúng không tìm một số 1 hoặc 5 tùy ý trong dãy.

Cuối cùng, xóa 99 trả `false` và deque vẫn chứa 4.

Chương trình kiểm chứng giá trị và trạng thái để tránh phân tích nhầm phương thức. Nó không đo thời gian và không tự chứng minh Big O chỉ bằng vài phần tử. Độ phức tạp phải được giải thích từ hợp đồng và lượng công việc của cơ chế triển khai.

## 10. Ghép nhiều thao tác có thể làm chi phí tăng mạnh

### Thêm n phần tử rồi lấy hết ở đầu

Nếu bắt đầu từ deque rỗng:

```text
Thêm n lần ở cuối: O(n) tổng khấu hao
Lấy n lần ở đầu:   O(n) tổng
Toàn bộ chuỗi:     O(n), chưa tính xử lý từng phần tử
```

Cách đọc này không phủ nhận việc một lần thêm có thể tốn O(n) khi mở rộng. Nó xét tổng chi phí cả chuỗi.

### Tìm nhiều giá trị

Nếu có `k` ứng viên và với mỗi ứng viên gọi `contains` trên một deque có tối đa `n` phần tử, cận tổng có thể là O(k × n).

Chẳng hạn, có n giá trị đều không tồn tại và lần lượt tìm chúng trong một deque vẫn giữ n phần tử: mỗi lần có thể phải duyệt n phần tử, tạo tổng O(n²).

Không có vòng lặp lồng nhau trong một hàm tự viết không có nghĩa không thể có chi phí bậc hai. Vòng lặp tìm kiếm đã nằm bên trong `contains`.

### contains rồi remove có thể lặp lại phần tìm

Mẫu sau thường không cần thiết nếu chỉ muốn biết có xóa được hay không:

```java
// Minh họa: pending là ArrayDeque hoặc Deque dùng ArrayDeque.
if (pending.contains(target)) {
    pending.remove(target);
}
```

Có thể dùng trực tiếp kết quả:

```java
boolean removed = pending.remove(target);
if (removed) {
    System.out.println("Da xoa");
}
```

Điều này có thể tránh một lượt tìm kiếm, nhưng không đổi cận O(n) của lần xóa theo giá trị. Đây là giảm công việc lặp, không phải chuyển thuật toán thành O(1).

### Có nên thêm Set hoặc Map để tìm nhanh?

Có thể cân nhắc một cấu trúc tra cứu riêng nếu nhu cầu tìm rất thường xuyên. Tuy nhiên, nó tạo thêm nghĩa vụ giữ dữ liệu nhất quán.

Đặc biệt, deque cho phép giá trị trùng. Một `Set` đơn giản không biểu diễn số lần xuất hiện; nếu xóa một bản sao rồi bỏ luôn giá trị khỏi set, chỉ mục sẽ sai khi deque còn bản sao khác.

Chỉ chọn cấu trúc bổ sung sau khi xác định ý nghĩa danh tính, giá trị trùng, thứ tự và cách cập nhật. Một phép tìm nhanh hơn không bù được việc mô hình dữ liệu thay đổi ngoài ý muốn.

## 11. Chi phí bộ nhớ và thời gian thực tế

Deque giữ tham chiếu phần tử trong một mảng. Nếu gọi `c` là độ dài vùng mảng đã cấp, bộ nhớ của bộ chứa phụ thuộc `c`, không chỉ số phần tử n đang còn.

Sau một đợt có nhiều dữ liệu rồi xóa bớt, không nên tự suy ra vùng mảng sẽ thu nhỏ ngay theo n. Trong lúc mở rộng, việc cấp và chuyển dữ liệu cũng có thể tạo nhu cầu bộ nhớ tạm thời.

Mặt khác, các đối tượng được tham chiếu có bộ nhớ riêng. Việc có n tham chiếu không cho biết toàn bộ đồ thị dữ liệu bên trong chiếm bao nhiêu.

Khi đánh giá thực tế, cần tách:

- Thời gian thao tác collection.
- Chi phí tạo hoặc so sánh phần tử.
- Tần suất mở rộng và cấp phát.
- Công việc nghiệp vụ sau khi lấy phần tử.
- Việc in kết quả, ghi log và các hoạt động vào/ra.

Một lần đo ngắn không đủ kết luận “cách xóa này luôn nhanh hơn”. Cần chuỗi thao tác đại diện, quy mô dữ liệu phù hợp và môi trường đo có kiểm soát. Big O giúp nhận diện cách chi phí tăng; phép đo bổ sung các yếu tố thực tế của trường hợp sử dụng.

## 12. Tự kiểm tra cách phân tích

### Bài 1: Sửa nhận định quá mạnh

“Thêm vào ArrayDeque luôn O(1), nên không có lần thêm nào phải chuyển nhiều dữ liệu.”

Nhận định đúng hơn: thêm hai đầu có O(1) khấu hao; một lần phải mở rộng có thể làm công việc O(n).

### Bài 2: Phân biệt hai phương thức có chữ Last

So sánh `removeLast()` với `removeLastOccurrence(target)`.

Phương thức thứ nhất dùng vị trí cuối đã biết. Phương thức thứ hai phải tìm lần xuất hiện cuối của một giá trị, nên trường hợp xấu nhất vẫn O(n).

### Bài 3: Không có kết quả có thể là đường đi tốn kém

Deque có n phần tử, không phần tử nào bằng X. `contains(X)` và `remove(X)` có nhất thiết O(1) vì trả `false` không?

Không. Chúng có thể phải kiểm tra đủ n phần tử để xác định không tồn tại.

### Bài 4: Nhìn công việc ẩn trong lời gọi API

Có n ứng viên đều không có trong một deque n phần tử. Một vòng lặp gọi `contains` cho từng ứng viên có cận tổng nào?

O(n²) với giả định so sánh bằng nhau O(1). Một vòng lặp tường minh vẫn có thể gọi một phép tìm tuyến tính ở mỗi lượt.

### Bài 5: Nêu đủ giả định

Khi nói “xóa theo giá trị là O(n)”, hãy bổ sung:

1. Đang xét `ArrayDeque`, không phải mọi collection.
2. Đang xét cận xấu nhất theo số phần tử.
3. Phép so sánh bằng nhau được giả định O(1).
4. Không nhầm `remove(Object)` với `remove()`.
5. Thời gian thực tế còn phụ thuộc dữ liệu và môi trường.

Cách phân tích đáng tin cậy bắt đầu từ đúng hành vi cần làm: **đã biết vị trí biên hay phải tìm giá trị, có cần di chuyển dữ liệu không, và đang xét một lần gọi hay cả chuỗi thao tác**.
