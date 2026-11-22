# push, pop và biểu diễn ngăn xếp bằng Deque

## 1. Ngăn xếp cần một đỉnh duy nhất

Ngăn xếp (stack) xử lý theo nguyên tắc **vào sau, ra trước** — LIFO (Last-In-First-Out).

Nếu lần lượt đưa A, B, C lên ngăn xếp:

```text
Đỉnh (top)
   C   ← được lấy trước
   B
   A   ← được đưa vào sớm nhất
Đáy
```

Ta không chọn ngẫu nhiên một phần tử ở giữa để lấy. Giao diện của mô hình stack tập trung vào đỉnh:

- `push(e)`: đưa e lên đỉnh.
- `pop()`: lấy và loại phần tử trên đỉnh.
- `peek()`: xem phần tử trên đỉnh mà không loại bỏ.

Trong Java, có thể biểu diễn mô hình này bằng `Deque<E>`. Khi dùng các tên stack của Deque, **đỉnh là đầu deque**. Tài liệu hiện hành ánh xạ push sang addFirst, pop sang removeFirst và peek sang peekFirst. Xem [Deque: sử dụng như ngăn xếp](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Deque.html).

## 2. Quy ước đầu deque là đỉnh

Ta vẽ deque theo chiều đầu → cuối:

```text
top/head
   ↓
 [C, B, A]
        ↑
       đáy
```

Ánh xạ API:

| Thao tác stack | Thao tác tương đương trên Deque | Tác động |
| --- | --- | --- |
| `push(e)` | `addFirst(e)` | Thêm vào đầu |
| `pop()` | `removeFirst()` | Trả và loại phần tử đầu |
| `peek()` | `peekFirst()` | Trả phần tử đầu, không loại |
| `isEmpty()` | Kiểm tra rỗng | Không thay đổi nội dung |
| `size()` | Đếm phần tử | Không lấy phần tử |

Từ deque rỗng:

| Lệnh | Trạng thái từ đỉnh tới đáy | Giá trị trả về đáng chú ý |
| --- | --- | --- |
| `push("A")` | `[A]` | push trả void |
| `push("B")` | `[B, A]` | |
| `push("C")` | `[C, B, A]` | |
| `peek()` | `[C, B, A]` | C |
| `pop()` | `[B, A]` | C |
| `pop()` | `[A]` | B |

Thêm và lấy ở cùng một đầu tạo LIFO. Nếu đổi một phía thành cuối deque mà không đổi quy ước, thuật toán có thể vô tình chuyển sang FIFO.

Không nghĩ phần tử ở bên phải khi in ra luôn là đỉnh. Với các tên push/pop chuẩn của Deque, phần tử đầu mới là đỉnh.

## 3. Chọn kiểu khai báo và triển khai

Một khai báo thông dụng trong chương trình một luồng:

```java
Deque<String> stack = new ArrayDeque<>();
```

Đoạn này cần import `java.util.Deque` và `java.util.ArrayDeque`.

- `Deque` diễn tả các thao tác công khai cần dùng.
- `ArrayDeque` là triển khai có thể tăng dung lượng, phù hợp cho nhiều tình huống stack trong bộ nhớ.
- Đối tượng không tự an toàn khi nhiều luồng cùng sửa.
- ArrayDeque không cho chứa null.
- Độ rộng mảng nội bộ hay cách tăng mảng không phải một phần của mô hình đỉnh/đáy mà thuật toán cần phụ thuộc.

Các đặc điểm công khai của triển khai nằm trong [ArrayDeque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html).

Nếu một lớp cần bảo đảm nơi gọi chỉ dùng push/pop/peek, có thể bọc Deque sau một API stack nhỏ thay vì trả trực tiếp toàn bộ Deque ra ngoài. Kiểu Deque vẫn cho phép các thao tác ở cuối hoặc giữa thông qua API khác; chính lớp quản lý phải giữ quy ước dùng như stack.

Không cần kế thừa một collection chỉ để có hành vi ngăn xếp.

## 4. Rỗng, null và giới hạn dung lượng

Với deque rỗng:

```text
pop()  → ném NoSuchElementException
peek() → trả null
```

Vì ArrayDeque không chứa null, giá trị null từ peek được dùng để nhận biết hiện không có phần tử trên đỉnh.

Nếu muốn “thử lấy đỉnh, không có thì trả null”, dùng `pollFirst()`. Nó có cùng phía lấy với pop nhưng khác cách báo rỗng.

Không tự động unbox một kết quả peek có thể null:

```java
Integer top = numbers.peek();
```

Đây là đoạn tích hợp với `Deque<Integer> numbers`; cần kiểm tra null trước khi dùng như `int`. Viết `int top = numbers.peek()` khi rỗng có thể gây NullPointerException do unboxing, không phải NoSuchElementException từ pop.

`push(null)` trên ArrayDeque là lỗi phần tử, không phải dấu hiệu ngăn xếp rỗng hay đầy.

Với một triển khai có giới hạn dung lượng, push có thể ném IllegalStateException khi không thêm được vì đầy, tương tự addFirst. ArrayDeque không có giới hạn tối đa do tham số constructor đặt; không dùng `new ArrayDeque<>(n)` như stack tối đa n phần tử.

## 5. Chương trình minh họa push/pop và một thuật toán dùng stack

Ví dụ có hai phần:

1. Lưu tên thao tác để quan sát thứ tự đỉnh/đáy.
2. Kiểm tra các cặp dấu ngoặc lồng nhau bằng stack chứa dấu mở.

Phần lưu tên chỉ minh họa thứ tự; nó không tự hoàn tác tác động của những thao tác mang tên “open”, “edit”, “save”.

Hàm kiểm tra ngoặc chỉ nhận `( ) [ ] { }` và khoảng trắng. Ký tự khác gây IllegalArgumentException; đây không phải parser cho mã Java, chuỗi có dấu nháy hoặc một ngôn ngữ biểu thức đầy đủ.

Lưu thành `StackModelDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.NoSuchElementException;

public class StackModelDemo {
    static boolean balanced(String text) {
        Deque<Character> openings = new ArrayDeque<>();
        for (int i = 0; i < text.length(); i++) {
            char current = text.charAt(i);
            if (current == '(' || current == '[' || current == '{') {
                openings.push(current);
            } else if (current == ')' || current == ']' || current == '}') {
                if (openings.isEmpty()) {
                    return false;
                }
                char opening = openings.pop();
                boolean matches =
                        (opening == '(' && current == ')')
                        || (opening == '[' && current == ']')
                        || (opening == '{' && current == '}');
                if (!matches) {
                    return false;
                }
            } else if (!Character.isWhitespace(current)) {
                throw new IllegalArgumentException(
                        "Only brackets and whitespace are supported");
            }
        }
        return openings.isEmpty();
    }

    public static void main(String[] args) {
        Deque<String> history = new ArrayDeque<>();
        history.push("open");
        history.push("edit");
        history.push("save");
        System.out.println("stack=" + history);
        System.out.println("top=" + history.peek());
        System.out.println("sizeAfterPeek=" + history.size());
        System.out.println("firstPop=" + history.pop());

        List<String> rest = new ArrayList<>();
        while (!history.isEmpty()) {
            rest.add(history.pop());
        }
        System.out.println("remainingPops=" + rest);
        System.out.println("emptyPeek=" + history.peek());
        try {
            history.pop();
        } catch (NoSuchElementException ex) {
            System.out.println("emptyPop=NoSuchElementException");
        }

        for (String text : List.of("({[]})", "([)]", "(()", ")(", "")) {
            System.out.println("text=\"" + text
                    + "\" balanced=" + balanced(text));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 StackModelDemo.java
java StackModelDemo
```

Output dự kiến theo đường đi của chương trình và hợp đồng API:

```text
stack=[save, edit, open]
top=save
sizeAfterPeek=3
firstPop=save
remainingPops=[edit, open]
emptyPeek=null
emptyPop=NoSuchElementException
text="({[]})" balanced=true
text="([)]" balanced=false
text="(()" balanced=false
text=")(" balanced=false
text="" balanced=true
```

Trạng thái stack đầu tiên được in theo thứ tự đầu tới cuối, tức đỉnh tới đáy của quy ước push/pop.

Sau peek, size vẫn là 3. Sau pop đầu tiên, save không còn trong stack. Vòng lặp tiếp theo lấy edit rồi open và làm stack rỗng.

## 6. Vì sao stack giải đúng cấu trúc ngoặc lồng?

Khi gặp dấu đóng, ta phải ghép nó với **dấu mở gần nhất chưa được ghép**, không phải dấu mở xuất hiện sớm nhất.

Với `({[]})`:

| Ký tự đọc | Hành động | Dấu mở đang chờ, từ đỉnh xuống đáy |
| --- | --- | --- |
| `(` | push dấu mở | `(` |
| `{` | push dấu mở | `{ (` |
| `[` | push dấu mở | `[ { (` |
| `]` | pop [, khớp ] | `{ (` |
| `}` | pop {, khớp } | `(` |
| `)` | pop (, khớp ) | Rỗng |

Bất biến của thuật toán:

> Sau mỗi ký tự đã xử lý hợp lệ, stack chứa đúng các dấu mở chưa được đóng, với dấu mở gần nhất nằm ở đỉnh.

Ba trường hợp thất bại:

1. Gặp dấu đóng nhưng stack rỗng: không có dấu mở tương ứng.
2. Dấu đóng không khớp loại của dấu mở trên đỉnh.
3. Đọc hết đầu vào nhưng stack còn dấu mở.

Ví dụ `([)]` có số lượng dấu mở/đóng bằng nhau nhưng vẫn sai. Khi gặp `)`, đỉnh là `[`, nên cấu trúc lồng bị vi phạm. Chỉ đếm số lượng không kiểm tra được điều này.

Chuỗi rỗng được coi là cân bằng: không có dấu đóng thừa và không còn dấu mở chờ.

Với n ký tự đầu vào, mỗi dấu mở được push nhiều nhất một lần và được pop nhiều nhất một lần. Thuật toán có thời gian O(n) khấu hao với các thao tác ở đầu của ArrayDeque; bộ nhớ phụ tối đa O(n) khi nhiều dấu mở cùng chưa được đóng.

## 7. Kiểm tra rỗng rồi pop đúng trong ngữ cảnh nào?

Trong `balanced()`, stack là biến cục bộ và chỉ một luồng dùng nó. Không có nơi khác lấy phần tử xen vào giữa:

```java
if (openings.isEmpty()) {
    return false;
}
char opening = openings.pop();
```

Do đó điều kiện đủ để biết lần pop tiếp theo có phần tử.

Không mở rộng lập luận này sang một stack được nhiều consumer dùng chung. Nếu luồng khác có thể lấy phần tử ở giữa hai lời gọi, kiểm tra isEmpty trước đó không bảo đảm pop còn thành công.

Đổi sang một triển khai đồng thời chỉ bảo vệ theo hợp đồng từng thao tác. Khi cần kiểm tra–lấy nguyên tử, dùng thao tác thích hợp như pollFirst và xử lý trường hợp không còn phần tử, hoặc cơ chế bảo vệ bao trùm toàn bộ điều kiện.

Bắt ngoại lệ rỗng không biến một ArrayDeque dùng sai quy tắc đồng thời thành cấu trúc an toàn.

## 8. Duyệt stack và lấy khỏi stack là hai hành động khác nhau

Với trạng thái:

```text
[save, edit, open]
```

- Iterator thông thường đi từ đầu tới cuối: save, edit, open.
- Duyệt chiều ngược đi từ đáy tới đỉnh: open, edit, save.
- Pop liên tiếp lấy theo đỉnh: save, edit, open, đồng thời làm mất phần tử khỏi stack.

Một vòng for-each chỉ đọc phần tử không phải là “pop ngầm”. Nếu cần xử lý và loại từng phần tử, phải thực hiện thao tác lấy theo chính sách.

Không gọi các phương thức sửa cấu trúc tùy ý trong khi duyệt rồi trông chờ iterator luôn phản ứng giống nhau. Với ArrayDeque, hành vi fail-fast chỉ hỗ trợ phát hiện lỗi theo best effort, không phải cơ chế đồng bộ hay bảo đảm rollback.

Nếu cần xem nội dung để chẩn đoán mà vẫn giữ stack, tạo dữ liệu quan sát theo chiều phù hợp. Nếu cần tiêu thụ stack, nêu rõ rằng sau thao tác nó sẽ rỗng.

## 9. Ứng dụng và giới hạn của mô hình stack

Stack phù hợp khi công việc cần xử lý theo thứ tự ngược hoặc cấu trúc lồng:

| Tình huống | Vì sao LIFO phù hợp |
| --- | --- |
| Ghép dấu ngoặc | Dấu mở gần nhất cần được đóng trước |
| Undo theo chuỗi thao tác | Thao tác mới nhất thường được xét hoàn tác trước |
| Duyệt sâu dùng stack tường minh | Trạng thái mới được đưa lên có thể được xử lý trước |
| Quay lui | Lưu các lựa chọn/trạng thái còn chờ và lấy lựa chọn gần nhất |
| Xử lý biểu thức với stack toán tử/toán hạng | Thứ tự giảm biểu thức được mô hình hóa bằng các stack theo thuật toán cụ thể |

Nhưng đẩy một chuỗi tên lên stack không tự tạo undo. Muốn hoàn tác, cần dữ liệu trước thay đổi hoặc một thao tác đảo ngược hợp lệ, cùng chính sách lỗi khi undo thất bại.

Tương tự, Deque làm stack tường minh trong heap không phải chính call stack của JVM. Pop một phần tử của Deque không tự kết thúc lời gọi phương thức hay khôi phục frame thực thi.

Khi dùng stack cho thuật toán duyệt, thứ tự push các phần tử con quyết định thứ tự chúng được pop. Nếu cần thăm con trái trước nhưng push trái rồi phải, con phải sẽ ở đỉnh và có thể được thăm trước. Cần suy từ LIFO thay vì chỉ nhìn thứ tự vòng lặp thêm.

## 10. Lỗi phổ biến và ca tự kiểm tra

| Lỗi | Hậu quả |
| --- | --- |
| addLast nhưng pop ở đầu rồi gọi đó là stack | Thứ tự có thể thành FIFO |
| peek trong vòng lặp mà không bao giờ pop | Lặp xử lý cùng đỉnh |
| pop khi rỗng | NoSuchElementException |
| Lưu null trong ArrayDeque | NullPointerException |
| Nghĩ push trả phần tử/boolean | Sai chữ ký: push trả void |
| Dùng đếm ngoặc thay cho ghép theo đỉnh | Bỏ sót lỗi lồng như ([)] |
| Chỉ kiểm tra cuối cùng stack rỗng | Có thể bỏ qua dấu đóng thừa hoặc sai loại xuất hiện trước đó |
| Sửa stack dùng chung mà không đồng bộ | Vi phạm hợp đồng đồng thời |
| Nghĩ iterator đảo chiều làm pop đổi đầu | Iterator không thay quy ước push/pop |

Các ca quan trọng cho hàm kiểm tra ngoặc:

- Chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- Một cặp đúng, nhiều cặp kế tiếp và nhiều mức lồng đúng.
- Dấu đóng xuất hiện trước mọi dấu mở.
- Dấu mở còn dư khi hết chuỗi.
- Số lượng bằng nhau nhưng loại/lồng sai.
- Ký tự không nằm trong định dạng mà hàm đã công bố.

Bài tập:

1. Push A, B, A rồi pop một lần. Vì sao vẫn còn một A trong stack?
2. Thêm khả năng trả vị trí lỗi của hàm kiểm tra ngoặc. Stack cần giữ thêm thông tin gì ngoài ký tự?
3. Đổi stack dấu mở sang một Queue FIFO rồi phân tích vì sao cấu trúc lồng không còn được kiểm tra đúng.
4. Với một cây có con trái và con phải, muốn pop con trái trước thì phải push theo thứ tự nào?
5. Thiết kế một API stack nhỏ chỉ lộ push/pop/peek/isEmpty. Vì sao việc giấu các thao tác cuối deque có thể giúp giữ quy ước?

Khi biểu diễn ngăn xếp bằng Deque, hãy giữ một quy ước nhất quán: **đỉnh ở đầu; push thêm đầu; pop lấy đầu; peek chỉ xem đầu**. Từ quy ước đó, thứ tự LIFO và các điều kiện rỗng có thể được kiểm tra trực tiếp trong từng bước của thuật toán.
