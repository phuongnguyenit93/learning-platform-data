# Quy tắc phần tử null và ý nghĩa của giá trị trả về

## 1. Vì sao Deque dùng null làm tín hiệu?

Khi lấy phần tử ở đầu hàng đợi, chương trình cần biết hai việc: có phần tử nào để lấy không, và nếu có thì phần tử đó là gì.

Với `Deque<E>`, `pollFirst()` lấy và loại bỏ phần tử đầu; nếu rỗng, phương thức trả `null`. `peekFirst()` xem phần tử đầu mà không loại bỏ; nếu rỗng, nó cũng trả `null`.

Thiết kế này rõ ràng khi phần tử trong cấu trúc luôn khác null:

```text
có dữ liệu: pollFirst() → một đối tượng E
rỗng:       pollFirst() → null
```

Nếu cho phép lưu null, hai trường hợp có thể cùng trả null: “không có phần tử” và “phần tử vừa lấy chính là null”. Vì vậy, hiểu **quy tắc phần tử của lớp triển khai** là điều kiện để diễn giải đúng giá trị trả về. Hợp đồng Deque khuyến khích tránh thêm null ngay cả khi lớp triển khai cho phép. [Tài liệu Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html).

Bài này dùng các API còn áp dụng trên Java 17+, tập trung vào đọc đúng kết quả và chọn cách xử lý rỗng. Không cần chạy JDK 6.

## 2. Deque là giao diện; quy tắc chấp nhận null phụ thuộc triển khai

| Triển khai | Có lưu phần tử null không? | Hệ quả khi dùng poll/peek |
|---|---|---|
| ArrayDeque | Không | null là tín hiệu không có phần tử ở đầu được hỏi |
| LinkedList khi dùng như Deque | Có | null có thể là dữ liệu hoặc tín hiệu rỗng |
| LinkedBlockingDeque | Không | null là tín hiệu không có phần tử với các phép poll/peek không chờ |

`ArrayDeque` từ chối phần tử null; thêm null bằng `addFirst`, `addLast`, `offerFirst`, `offerLast` hoặc `push` gây `NullPointerException`. `offer` không đổi dữ liệu đầu vào không hợp lệ thành `false`. [ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

`LinkedList` cho phép null theo hợp đồng hiện hành. Việc khai báo biến là `Deque<String>` không tự cấm null khi đối tượng bên trong là `LinkedList`. [LinkedList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedList.html).

`LinkedBlockingDeque` cũng từ chối null; tham số dung lượng trong ví dụ bên dưới là giới hạn thật của số phần tử. [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

Các đoạn mã ngắn trong phần giải thích là trích đoạn minh họa. Chương trình độc lập với import, hàm main, lệnh chạy và stdout nằm ở phần 6.

## 3. Đọc kết quả theo từng nhóm thao tác

### 3.1. Lấy và xem: E hoặc null

| Phương thức | Khi có phần tử | Khi rỗng | Có loại bỏ phần tử không? |
|---|---|---|---|
| pollFirst() | Trả phần tử đầu | null | Có |
| pollLast() | Trả phần tử cuối | null | Có |
| peekFirst() | Trả phần tử đầu | null | Không |
| peekLast() | Trả phần tử cuối | null | Không |

`poll()` tương đương `pollFirst()`; `peek()` tương đương `peekFirst()`. Giá trị được trả về là **phần tử**, không phải cờ thành công.

Với một Deque không lưu null, giá trị khác null của `pollFirst` cho biết thao tác đã lấy được một phần tử. Với `peekFirst`, giá trị khác null chỉ cho biết đã xem thấy một phần tử tại thời điểm thao tác; nó không nói phần tử đã được tiêu thụ.

### 3.2. Lấy và xem bằng biến thể ném ngoại lệ

| Phương thức | Khi có phần tử | Khi rỗng |
|---|---|---|
| removeFirst(), removeLast() | Trả và loại bỏ phần tử | NoSuchElementException |
| getFirst(), getLast() | Trả phần tử, không loại bỏ | NoSuchElementException |
| pop() | Trả và loại bỏ phần tử đầu | NoSuchElementException |

`remove()` không đối số tương đương `removeFirst()`; `element()` tương đương `getFirst()`.

**“Ném ngoại lệ khi rỗng” không đồng nghĩa “giá trị trả về luôn khác null”.** Nếu một `LinkedList` thực sự đang lưu null ở đầu, `removeFirst()` lấy phần tử đó thành công và trả null. Ngoại lệ chỉ phát sinh khi không có phần tử để lấy. Ví dụ này được kiểm chứng trong chương trình đầy đủ.

Các quan hệ tên gọi và cách xử lý rỗng được quy định trong [hợp đồng Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html).

### 3.3. Thêm: true, false, void và ngoại lệ

Với cấu trúc có giới hạn dung lượng:

- `offerFirst(e)`/`offerLast(e)`: trả `true` nếu thêm thành công, `false` nếu không còn chỗ.
- `addFirst(e)`/`addLast(e)`/`push(e)`: trả `void`; nếu đầy thì ném `IllegalStateException`.
- `add(e)`: trả `boolean`, nhưng khi không thể thêm vì đầy thì ném ngoại lệ thay vì trả false.

“Không còn chỗ” là trạng thái dung lượng. “Đưa null vào cấu trúc cấm null” là vi phạm đầu vào. Không nên nhập hai tình huống này vào cùng một nhánh xử lý.

`false` của `offerLast` cũng không có nghĩa cấu trúc rỗng. Trong ví dụ dung lượng 1, sau khi chứa A, thêm B thất bại trả false; A vẫn nằm trong cấu trúc. [LinkedBlockingDeque.offerLast](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html#offerLast(E)), [LinkedBlockingDeque.addLast](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html#addLast(E)).

## 4. Trường hợp null làm mất thông tin

Xét Deque được triển khai bởi LinkedList:

```text
trạng thái ban đầu: [null, "tail"]
peekFirst() → null; trạng thái vẫn [null, "tail"]
pollFirst() → null; trạng thái còn ["tail"]
```

Nếu chỉ nhìn giá trị null mà kết luận “hàng đợi không có công việc”, chương trình sẽ diễn giải sai.

Một vòng lặp dễ mắc lỗi:

```java
Deque<String> messages = new LinkedList<>();
messages.addLast(null);
messages.addLast("tail");

String message;
while ((message = messages.pollFirst()) != null) {
    System.out.println(message);
}
```

Vòng lặp dừng ngay ở phần tử null đầu tiên. Nó đã loại bỏ phần tử null, nhưng chưa xử lý `"tail"`. Vấn đề không nằm ở cú pháp vòng lặp; điều kiện dừng không phù hợp với miền giá trị được lưu.

Ba hướng thiết kế có ý nghĩa khác nhau:

1. **Cấm null ngay tại nơi nhận dữ liệu.** Chọn ArrayDeque hoặc xác thực đầu vào để null chỉ còn mang nghĩa “không có phần tử”.
2. **Biểu diễn trạng thái nghiệp vụ bằng một đối tượng rõ ràng.** Ví dụ công việc loại “dừng”, “bỏ qua” hoặc “chưa có nội dung”; chúng vẫn là đối tượng khác null.
3. **Nếu buộc phải xử lý cấu trúc có null trong một luồng,** có thể kiểm tra rỗng rồi lấy bằng `removeFirst`, xử lý null như một phần tử hợp lệ. Quy trình hai bước này cần giả định không có nơi khác thay đổi cấu trúc xen vào.

Bọc `Optional.ofNullable(messages.pollFirst())` sau khi lấy không khôi phục thông tin đã mất: cả phần tử null và trạng thái rỗng đều thành `Optional.empty()`. Cần sửa mô hình dữ liệu hoặc giao thức lấy phần tử.

## 5. null phần tử, null tham chiếu và null thuộc tính là ba việc khác nhau

### Tham chiếu Deque là null

```java
Deque<String> messages = null;
messages.pollFirst();
```

Lời gọi gây `NullPointerException` vì không có đối tượng Deque để thực hiện thao tác. Nó chưa đi tới logic “nếu rỗng trả null”. Một Deque rỗng vẫn là một đối tượng hợp lệ, được tạo bằng `new ArrayDeque<>()`.

### Phần tử được đưa vào là null

```java
Deque<String> messages = new ArrayDeque<>();
messages.offerLast(null);
```

Ở đây có đối tượng Deque; lỗi là phần tử vi phạm quy tắc cấm null của ArrayDeque.

### Đối tượng phần tử có một thuộc tính null

```java
record Message(String id, String note) {
}

Deque<Message> messages = new ArrayDeque<>();
messages.addLast(new Message("m1", null));
```

Tham chiếu tới `Message` khác null, nên ArrayDeque chấp nhận. Nó không tự kiểm tra mọi thuộc tính bên trong phần tử. Nếu `note` bắt buộc có giá trị, ứng dụng phải xác thực theo hợp đồng của `Message`.

Tương tự, phần tử `""`, `0` hoặc `false` không đồng nghĩa null. Một chuỗi rỗng hay số zero vẫn có thể là dữ liệu hợp lệ; cách xử lý do miền nghiệp vụ quyết định.

## 6. Chương trình Java 17+ chạy đầy đủ

Lưu thành `DequeResultLab.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.LinkedList;
import java.util.NoSuchElementException;
import java.util.concurrent.LinkedBlockingDeque;

public final class DequeResultLab {
    private DequeResultLab() {
    }

    public static void main(String[] args) {
        Deque<String> safe = new ArrayDeque<>();
        System.out.println("empty peek=" + safe.peekFirst());
        System.out.println("empty poll=" + safe.pollFirst());
        System.out.println("offer=" + safe.offerLast("ready"));
        System.out.println("peek=" + safe.peekFirst());
        System.out.println("size after peek=" + safe.size());
        System.out.println("poll=" + safe.pollFirst());
        System.out.println("size after poll=" + safe.size());

        try {
            safe.removeFirst();
        } catch (NoSuchElementException ex) {
            System.out.println("empty remove=" + ex.getClass().getSimpleName());
        }
        try {
            safe.getLast();
        } catch (NoSuchElementException ex) {
            System.out.println("empty get=" + ex.getClass().getSimpleName());
        }
        try {
            safe.offerLast(null);
        } catch (NullPointerException ex) {
            System.out.println("null offer=" + ex.getClass().getSimpleName());
        }
        System.out.println("size after null failure=" + safe.size());

        Deque<String> permissive = new LinkedList<>();
        permissive.addLast(null);
        permissive.addLast("tail");
        System.out.println("nullable peek=" + permissive.peekFirst());
        System.out.println("nullable size=" + permissive.size());
        System.out.println("nullable poll=" + permissive.pollFirst());
        System.out.println("remaining=" + permissive);
        permissive.addFirst(null);
        System.out.println("remove stored null=" + permissive.removeFirst());
        System.out.println("still remaining=" + permissive);

        Deque<String> bounded = new LinkedBlockingDeque<>(1);
        System.out.println("bounded offer A=" + bounded.offerLast("A"));
        System.out.println("bounded offer B=" + bounded.offerLast("B"));
        try {
            bounded.addLast("B");
        } catch (IllegalStateException ex) {
            System.out.println("full add=" + ex.getClass().getSimpleName());
        }
        System.out.println("bounded contents=" + bounded);
        System.out.println("bounded poll=" + bounded.pollFirst());
        System.out.println("remove missing=" + bounded.remove("missing"));
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror DequeResultLab.java
java DequeResultLab
```

Stdout:

```text
empty peek=null
empty poll=null
offer=true
peek=ready
size after peek=1
poll=ready
size after poll=0
empty remove=NoSuchElementException
empty get=NoSuchElementException
null offer=NullPointerException
size after null failure=0
nullable peek=null
nullable size=2
nullable poll=null
remaining=[tail]
remove stored null=null
still remaining=[tail]
bounded offer A=true
bounded offer B=false
full add=IllegalStateException
bounded contents=[A]
bounded poll=A
remove missing=false
```

### Vì sao các kết quả có ý nghĩa khác nhau?

**ArrayDeque rỗng:** `peek`/`poll` trả null; `remove`/`get` ném ngoại lệ. Với dữ liệu `"ready"`, peek không đổi kích thước, còn poll làm kích thước giảm từ 1 xuống 0.

**Thêm null vào ArrayDeque:** `offerLast(null)` ném ngoại lệ. Kích thước sau lời gọi thất bại vẫn là 0; không có phần tử null được thêm vào.

**LinkedList có null:** `nullable peek=null` đi kèm kích thước 2. Sau poll, phần tử `"tail"` vẫn còn. Sau khi thêm lại null ở đầu, `removeFirst` trả null thành công và vẫn để lại tail. Dòng này phân biệt “phần tử trả về là null” với “không tồn tại phần tử”.

**Deque giới hạn:** lần thêm A thành công, thêm B bằng offer trả false, thêm B bằng addLast ném ngoại lệ. Các lần thêm thất bại không làm mất A.

**remove có đối số:** `remove("missing")` trả false vì không tìm thấy phần tử khớp để xóa. Đây không phải `remove()` không đối số. Đọc cả chữ ký phương thức trước khi diễn giải giá trị boolean. [LinkedBlockingDeque.remove(Object)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html#remove(java.lang.Object)).

Các khối catch trong ví dụ giúp quan sát hợp đồng API. Trong mã ứng dụng, rỗng hoặc đầy thường xuyên xảy ra có thể được xử lý bằng poll/offer và nhánh điều kiện rõ ràng, thay vì cố tình gây ngoại lệ để điều khiển luồng.

## 7. Viết mã xử lý kết quả đúng hợp đồng

### Lấy phần tử có thể không tồn tại

Nếu đã bảo đảm cấu trúc không chứa null:

```java
String next = messages.pollFirst();
if (next == null) {
    System.out.println("no message available");
} else {
    System.out.println("process " + next);
}
```

Điều kiện dựa trên **kết quả của chính thao tác lấy**. Nó không cần kiểm tra kích thước trước rồi mới lấy.

### Cẩn thận với tự tháo hộp

```java
Deque<Integer> counts = new ArrayDeque<>();
int next = counts.pollFirst();
```

Mã biên dịch được nhưng gây `NullPointerException` lúc chạy: poll trả null vì rỗng, rồi Java cố chuyển tham chiếu `Integer` đó thành `int`. Ngoại lệ này phát sinh ở việc tự tháo hộp (unboxing), không phải vì poll ném ngoại lệ khi rỗng. [JLS §5.1.8](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8).

Cách xử lý có nhánh rõ ràng:

```java
Integer next = counts.pollFirst();
if (next != null) {
    int value = next;
    System.out.println(value);
}
```

Nếu nghiệp vụ có giá trị mặc định khi rỗng, chỉ áp dụng giá trị đó sau khi đã phân biệt trạng thái rỗng với dữ liệu thật. Không mặc định số zero là “không có dữ liệu”.

### Khi luôn phải có phần tử

Nếu chương trình đã thiết lập một bất biến yêu cầu Deque không rỗng, `removeFirst` có thể phù hợp: ngoại lệ làm lộ lỗi vi phạm bất biến. Điều kiện đó phải được chứng minh từ logic chương trình, không chỉ dựa trên một kiểm tra cũ có thể hết hiệu lực.

Đừng bắt mọi `NullPointerException` rồi coi là “rỗng”. Cùng loại ngoại lệ có thể đến từ tham chiếu Deque null, thêm phần tử null, tháo hộp hoặc lỗi trong xử lý phần tử. Bắt quá rộng che lấp nguyên nhân thực tế.

## 8. Giới hạn của các tín hiệu trong xử lý đồng thời

null từ một phép poll không chờ chỉ phản ánh không lấy được phần tử ở thao tác đó. Nó không tự cho biết:

- Nhà sản xuất đã kết thúc hay chưa.
- Trong tương lai còn công việc mới hay không.
- Một luồng khác có vừa lấy mất công việc hay không.
- Toàn bộ hệ thống đã hoàn tất xử lý hay chưa.

ArrayDeque và LinkedList không tự cung cấp đồng bộ để chia sẻ cấu trúc đang thay đổi giữa nhiều luồng. Việc kiểm tra `isEmpty()` rồi lấy là hai thao tác; cần một hợp đồng đồng bộ phù hợp nếu muốn kết quả kiểm tra bảo vệ bước lấy sau đó.

Nếu cần chờ phần tử, `LinkedBlockingDeque` có `takeFirst()`; nếu cần chờ chỗ trống, có `putLast(e)`. Các biến thể có thời gian chờ có thể báo không lấy/thêm được khi hết thời gian. Đây là hợp đồng khác với poll/offer không chờ trong chương trình mẫu. [LinkedBlockingDeque.takeFirst](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html#takeFirst()), [LinkedBlockingDeque.putLast](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html#putLast(E)).

Tín hiệu kết thúc một quy trình phải được thiết kế riêng. Với cấu trúc cấm null, không thể chèn null để làm “dấu kết thúc”; có thể dùng một thông điệp khác null có loại rõ ràng, với quy tắc dừng được thống nhất giữa các bên.

## 9. Bài tập tự kiểm chứng

1. Với `LinkedList` đang chứa `[null, "A"]`, dự đoán giá trị và kích thước sau mỗi lần `peekFirst`, `pollFirst`, `removeFirst`. Tách rõ xem và lấy.
2. Sửa ví dụ nullable thành vòng lặp dừng khi poll trả null. Xác định phần tử nào còn lại và viết điều kiện đầu vào cần có để vòng lặp ấy đúng.
3. Chạy đoạn tự tháo hộp với Deque<Integer> rỗng; sau đó thêm phần tử 0. Giải thích vì sao 0 là dữ liệu còn null là không có phần tử trong ArrayDeque.
4. Với dung lượng 1 đang chứa A, gọi `offerLast("B")`, `peekFirst()` và `pollFirst()`. Dự đoán lần lượt boolean, phần tử được xem và phần tử được lấy.
5. Thiết kế một hợp đồng hàm nhận Deque để tiêu thụ toàn bộ dữ liệu: ghi rõ có cho phép null không, có thay đổi đầu vào không và có nơi nào sửa cấu trúc đồng thời không.

Một giá trị trả về chỉ có nghĩa khi đi cùng **chữ ký phương thức, trạng thái cấu trúc và chính sách phần tử**. Xác định đủ ba yếu tố đó giúp xử lý null/false đúng mục đích và giữ lỗi lập trình khác biệt với trạng thái rỗng hoặc đầy bình thường.
