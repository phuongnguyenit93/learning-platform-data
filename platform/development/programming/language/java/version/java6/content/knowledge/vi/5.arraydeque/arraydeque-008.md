# Ứng dụng ArrayDeque: duyệt cây, xử lý biểu thức và lịch sử thao tác

## 1. Một cấu trúc, ba cách quản lý công việc

Khi duyệt cây, ta phải nhớ các nút sẽ xử lý tiếp. Khi tính biểu thức, ta phải giữ các kết quả trung gian. Khi hỗ trợ hoàn tác, ta phải lưu các trạng thái trước đó. Cả ba bài toán đều cần một vùng lưu tạm có **thứ tự lấy ra rõ ràng**.

`ArrayDeque<E>` là một cách cài đặt hàng đợi hai đầu (`Deque<E>`). Điểm quyết định thuật toán không nằm ở tên lớp mà ở cách dùng hai đầu:

| Bài toán | Quy tắc lấy phần tử | Thao tác chính |
| --- | --- | --- |
| Duyệt cây theo chiều rộng, BFS | Vào trước, ra trước — FIFO | `addLast` và `removeFirst` |
| Duyệt cây theo chiều sâu, DFS | Vào sau, ra trước — LIFO | `push` và `pop` |
| Tính biểu thức hậu tố | Dùng kết quả gần nhất trước | `push` và `pop` |
| Hoàn tác/làm lại | Thay đổi gần nhất được xử lý trước | Hai ngăn xếp với `push` và `pop` |

Trong bài này, **đầu** là phía `First`; `push` thêm vào đầu và `pop` lấy khỏi đầu. Khi dùng làm hàng đợi, thêm vào cuối và lấy ở đầu. Không trộn các quy ước giữa chừng.

Các ví dụ dùng cú pháp Java 17 trở lên, áp dụng được trên JDK hiện đại. Chúng tập trung vào thuật toán trong một luồng, không phụ thuộc vào môi trường web hoặc framework.

## 2. Duyệt cây: hàng đợi cho BFS, ngăn xếp cho DFS

Xét cây có thứ tự các nút con từ trái sang phải:

```text
        A
      /   \
     B     C
    / \     \
   D   E     F
```

### 2.1. BFS: xử lý theo từng tầng

BFS (breadth-first search) xử lý nút gốc, rồi các nút cách gốc một cạnh, rồi hai cạnh, v.v.

Quy trình:

1. Đưa gốc vào cuối hàng đợi.
2. Lấy một nút khỏi đầu hàng đợi và xử lý.
3. Đưa lần lượt các con của nút đó vào cuối.
4. Lặp đến khi hàng đợi rỗng.

Bất biến cần giữ: **nút được phát hiện trước phải được xử lý trước**.

| Nút vừa xử lý | Hàng đợi sau khi thêm các con, đầu → cuối | Kết quả |
| --- | --- | --- |
| Chưa xử lý | `[A]` | `[]` |
| A | `[B, C]` | `[A]` |
| B | `[C, D, E]` | `[A, B]` |
| C | `[D, E, F]` | `[A, B, C]` |
| D, rồi E, rồi F | Cuối cùng `[]` | `[A, B, C, D, E, F]` |

BFS phù hợp khi tìm đối tượng ở tầng gần gốc nhất, duyệt cây theo cấp hoặc tìm số bước ít nhất trên đồ thị mà mỗi cạnh có cùng chi phí. Nếu tìm đường trên đồ thị có trọng số khác nhau, thứ tự FIFO đơn thuần không bảo đảm đường đi có tổng chi phí nhỏ nhất.

Muốn xuất riêng từng tầng, chụp `int levelSize = pending.size()` trước vòng lặp xử lý tầng, rồi lấy đúng `levelSize` nút. Các con thêm trong vòng lặp thuộc tầng tiếp theo; không dùng kích thước đang thay đổi làm giới hạn của vòng lặp tầng hiện tại.

### 2.2. DFS: đi sâu theo một nhánh trước

DFS (depth-first search) dùng ngăn xếp để ghi nhớ các nhánh còn chờ. Ví dụ này là **tiền thứ tự**: xử lý nút hiện tại trước các cây con.

Quy trình:

1. Đẩy gốc lên ngăn xếp.
2. Lấy nút trên đỉnh ra và xử lý.
3. Đẩy các con vào ngăn xếp.
4. Lặp đến khi ngăn xếp rỗng.

Với quy ước muốn đi từ trái sang phải, phải **đẩy con từ phải sang trái**. Ở nút A, đẩy C trước rồi B; B nằm trên đỉnh và được lấy ra trước.

```text
Đỉnh ở bên trái:
[A]
pop A, push C, push B  -> [B, C]
pop B, push E, push D  -> [D, E, C]
pop D                 -> [E, C]
pop E                 -> [C]
pop C, push F         -> [F]
pop F                 -> []
Kết quả: A, B, D, E, C, F
```

Nếu đẩy B rồi C, chương trình vẫn là DFS nhưng đi nhánh C trước. Đây là thay đổi thứ tự duyệt, không phải lỗi của `ArrayDeque`.

Ngăn xếp tường minh giúp tránh việc mỗi nút của một cây rất sâu tạo thêm một lần gọi đệ quy. Tuy nhiên, nó vẫn dùng bộ nhớ và không tự giải quyết mọi vấn đề của cây lớn. Hậu thứ tự, chẳng hạn tính kích thước thư mục sau khi biết kích thước các con, cần lưu thêm trạng thái “đã quay lại nút” hoặc dùng một cách tổ chức khác; đổi tên hàm tiền thứ tự thành hậu thứ tự không làm thay đổi thuật toán.

### 2.3. Điều kiện đầu vào và chi phí

Ví dụ bên dưới giả định đầu vào là **cây đúng nghĩa**: không có chu trình và mỗi nút ngoài gốc có đúng một cha. `Node` có danh sách con không chứa `null`; gốc `null` được xem là cây rỗng.

Nếu dữ liệu là đồ thị, nút có thể được gặp lại từ nhiều đường. Phải bổ sung tập `visited` với khóa nhận diện ổn định. Với BFS, thường đánh dấu ngay khi đưa nút vào hàng đợi để không xếp cùng nút nhiều lần. Không dùng tên hiển thị làm khóa nếu tên có thể trùng. Không nên dùng so sánh cấu trúc đệ quy của một nút có chu trình làm cơ chế nhận diện đồ thị.

Với n nút cây, mỗi nút được thêm và lấy ra một lần, nên thời gian là O(n) theo chi phí khấu hao của thao tác hai đầu. BFS giữ phần biên đang chờ, có kích thước O(w) theo bậc lớn, với w là độ rộng lớn nhất của cây. DFS tiền thứ tự dưới đây đẩy toàn bộ các con nên có thể giữ O(n) nút chờ trong trường hợp xấu nhất của cây nhiều nhánh; không khẳng định bộ nhớ O(h) cho mọi cây. Riêng cây nhị phân, số nút chờ của cách DFS này là O(h), với h là chiều cao.

Cả hai hàm còn tạo danh sách kết quả O(n). Khi chỉ cần xử lý từng nút, có thể gọi một hàm xử lý tại chỗ và bỏ danh sách kết quả để giảm bộ nhớ đầu ra.

## 3. Xử lý biểu thức: ngăn xếp giữ các kết quả trung gian

### 3.1. Vì sao chọn biểu thức hậu tố?

Biểu thức trung tố quen thuộc đặt toán tử ở giữa, ví dụ `20 - 3 * 2`. Biểu thức hậu tố (postfix) tương ứng là:

```text
20 3 2 * -
```

Mỗi toán tử đứng sau hai toán hạng. Thứ tự tính đã được mã hóa trong thứ tự token, nên bộ tính hậu tố không cần tự xét ưu tiên nhân trước trừ hoặc đọc dấu ngoặc.

**Phạm vi bộ tính trong bài:** số nguyên `int`, token cách nhau bằng khoảng trắng, bốn toán tử nhị phân `+`, `-`, `*`, `/`. Số âm như `-7` là một token số; token `-` đứng riêng là phép trừ hai toán hạng. Đây không phải bộ phân tích trung tố: không nhận `20-3*2`, dấu ngoặc, biến, số thập phân hoặc toán tử một ngôi viết thành token riêng.

### 3.2. Quy tắc tính và thứ tự toán hạng

- Gặp số: đẩy số lên ngăn xếp.
- Gặp toán tử: cần ít nhất hai giá trị; lấy **phải trước, trái sau**.
- Tính `left operator right`, rồi đẩy kết quả trở lại.
- Hết token: phải còn đúng một giá trị.

Theo quy ước đỉnh ở bên trái:

| Token | Hành động | Ngăn xếp |
| --- | --- | --- |
| `20` | Đẩy 20 | `[20]` |
| `3` | Đẩy 3 | `[3, 20]` |
| `2` | Đẩy 2 | `[2, 3, 20]` |
| `*` | `left=3`, `right=2`, đẩy 6 | `[6, 20]` |
| `-` | `left=20`, `right=6`, đẩy 14 | `[14]` |

Đảo hai lần `pop` sẽ làm `20 - 6` thành `6 - 20`. Lỗi có thể bị che khuất nếu chỉ thử phép cộng và phép nhân; nên luôn có ví dụ phép trừ và phép chia.

Bất biến: ngăn xếp lưu kết quả của những biểu thức con đã hoàn thành nhưng chưa được toán tử tiếp theo sử dụng. Mỗi toán tử nhị phân làm số phần tử giảm một sau khi tính xong.

### 3.3. Kiểm tra dữ liệu và số học

Bộ tính phải phân biệt:

| Đầu vào | Vấn đề |
| --- | --- |
| Chuỗi rỗng | Không có biểu thức |
| `2 +` | Thiếu toán hạng |
| `1 2` | Dư toán hạng khi kết thúc |
| `2 x +` | Token không thuộc ngữ pháp |
| `4 0 /` | Chia cho 0 |
| `2147483647 1 +` | Kết quả vượt miền `int` |

Trong chương trình, `Math.addExact`, `subtractExact`, `multiplyExact` phát hiện tràn số bằng `ArithmeticException`. Phép chia kiểm tra riêng mẫu số 0 và trường hợp `Integer.MIN_VALUE / -1`. `Integer.parseInt` cũng từ chối token số nằm ngoài miền `int` bằng `NumberFormatException`, là một lớp con của `IllegalArgumentException`. Xem [tài liệu Math](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html) cho hợp đồng các phép toán có kiểm tra.

Phép chia `int` bỏ phần thập phân theo hướng về 0: `-7 / 2` là `-3`. Khi nghiệp vụ cần số thập phân hoặc độ chính xác khác, phải chọn kiểu số và quy tắc làm tròn phù hợp; thay kiểu ngăn xếp đơn thuần chưa đủ.

Với t token, đánh giá hậu tố cần O(t) thao tác ngăn xếp và O(t) bộ nhớ trong trường hợp xấu nhất. Nếu tính cả việc tách và đọc chuỗi đầu vào, phải xét thêm tổng số ký tự. Chương trình dùng ngăn xếp cục bộ, nên biểu thức lỗi không để lại một ngăn xếp dùng chung ở trạng thái dở dang.

Nếu muốn nhận trung tố, cần một bước phân tích riêng, chẳng hạn dùng ngăn xếp toán tử để chuyển thành hậu tố, xử lý ưu tiên, tính kết hợp và dấu ngoặc trước khi gọi bộ tính này.

## 4. Lịch sử thao tác: hai ngăn xếp cho Undo/Redo

### 4.1. Mô hình trạng thái

Ví dụ là một trình soạn thảo văn bản nhỏ, có:

- `text`: nội dung hiện tại.
- `undo`: các trạng thái trước đó; gần nhất ở đỉnh.
- `redo`: các trạng thái có thể khôi phục sau khi hoàn tác; trạng thái sẽ làm lại tiếp theo ở đỉnh.

Ta lưu **ảnh chụp trạng thái** bằng `String` bất biến. Đây là lựa chọn dễ kiểm chứng: phần tử đã lưu không bị chỉnh sửa thông qua một tham chiếu khác.

Các phép chuyển:

| Thao tác | Chuyển trạng thái |
| --- | --- |
| Sửa văn bản | Đẩy hiện tại vào `undo`, đặt văn bản mới, xóa `redo` |
| Undo | Nếu có `undo`: đẩy hiện tại vào `redo`, lấy đỉnh `undo` làm hiện tại |
| Redo | Nếu có `redo`: đẩy hiện tại vào `undo`, lấy đỉnh `redo` làm hiện tại |
| Undo/Redo khi rỗng | Trả `false`, giữ nguyên trạng thái |

Sửa thành đúng nội dung hiện tại được xem là không có thay đổi; ví dụ không thêm lịch sử và không xóa `redo`.

### 4.2. Vì sao chỉnh sửa mới phải xóa Redo?

Giả sử đã đi qua:

```text
"" -> "a" -> "ab" -> "abc"
```

Undo đưa hiện tại về `"ab"`, còn `"abc"` nằm trên đỉnh `redo`. Nếu người dùng sửa thành `"abX"`, họ đã tạo một nhánh mới. Bản `"abc"` thuộc nhánh cũ, nên cơ chế lịch sử tuyến tính phải xóa `redo`.

Nếu giữ `redo`, nút “làm lại” sẽ nhảy sang một trạng thái không còn nối tiếp thao tác vừa thực hiện. Hệ thống lịch sử dạng cây có thể giữ các nhánh, nhưng cần mô hình dữ liệu khác; hai ngăn xếp này mô tả lịch sử tuyến tính.

### 4.3. Giới hạn bộ nhớ và tính đúng đắn

`History(3)` giữ tối đa ba bước lịch sử được lưu, không tính trạng thái hiện tại. Khi sửa mới làm `undo` vượt giới hạn, xóa phần tử ở **cuối** ngăn xếp — trạng thái cũ nhất.

Undo/Redo chỉ chuyển một trạng thái giữa hai phía, nên tổng số mục `undo.size() + redo.size()` không tăng. Sửa mới xóa `redo`, thêm một trạng thái vào `undo` và cắt phần cũ nếu cần; tổng số mục vẫn không vượt giới hạn.

Giới hạn số bước không đồng nghĩa giới hạn số byte. Với tối đa k ảnh chụp và mỗi văn bản có độ dài tối đa s, bộ nhớ lịch sử có thể lên đến O(k × s), chưa tính trạng thái hiện tại và chi tiết lưu trữ chuỗi. `ArrayDeque` chỉ giữ tham chiếu; nó không nén văn bản hoặc tự sao chép đối tượng.

Nếu trạng thái là đối tượng có thể thay đổi, phải sao chép đủ sâu hoặc dùng trạng thái bất biến. Đẩy cùng một đối tượng mutable nhiều lần thường làm toàn bộ lịch sử cùng trỏ tới trạng thái mới nhất.

Với tài liệu lớn, có thể lưu lệnh hoặc phần thay đổi thay vì toàn bộ văn bản. Khi đó cần thiết kế phép đảo, nhóm các thao tác nhỏ và xử lý trường hợp lệnh thất bại. Hoàn tác trong bộ nhớ cũng không tự đảo được việc đã gửi thư, gọi dịch vụ hoặc ghi ra hệ thống khác; những hành động ấy cần hợp đồng nghiệp vụ riêng.

## 5. Chương trình hoàn chỉnh

Lưu đúng tên **ArrayDequeApplications.java**. Chương trình gom ba ví dụ độc lập về mặt thuật toán; `main` chỉ tạo dữ liệu và in kết quả để kiểm chứng.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

public class ArrayDequeApplications {
    record Node(String name, List<Node> children) {
        Node {
            Objects.requireNonNull(name);
            children = List.copyOf(children);
        }
    }

    static List<String> bfs(Node root) {
        List<String> order = new ArrayList<>();
        if (root == null) return order;
        Deque<Node> pending = new ArrayDeque<>();
        pending.addLast(root);
        while (!pending.isEmpty()) {
            Node current = pending.removeFirst();
            order.add(current.name());
            for (Node child : current.children()) {
                pending.addLast(child);
            }
        }
        return order;
    }

    static List<String> dfsPreorder(Node root) {
        List<String> order = new ArrayList<>();
        if (root == null) return order;
        Deque<Node> pending = new ArrayDeque<>();
        pending.push(root);
        while (!pending.isEmpty()) {
            Node current = pending.pop();
            order.add(current.name());
            List<Node> children = current.children();
            for (int i = children.size() - 1; i >= 0; i--) {
                pending.push(children.get(i));
            }
        }
        return order;
    }

    static int divideChecked(int left, int right) {
        if (right == 0) throw new ArithmeticException("Division by zero");
        if (left == Integer.MIN_VALUE && right == -1) {
            throw new ArithmeticException("Integer overflow");
        }
        return left / right;
    }

    static int evaluatePostfix(String expression) {
        Objects.requireNonNull(expression);
        String input = expression.strip();
        if (input.isEmpty()) {
            throw new IllegalArgumentException("Empty expression");
        }
        Deque<Integer> values = new ArrayDeque<>();
        for (String token : input.split("\\s+")) {
            boolean operator = switch (token) {
                case "+", "-", "*", "/" -> true;
                default -> false;
            };
            if (!operator) {
                if (!token.matches("[+-]?[0-9]+")) {
                    throw new IllegalArgumentException("Invalid token: " + token);
                }
                values.push(Integer.parseInt(token));
                continue;
            }
            if (values.size() < 2) {
                throw new IllegalArgumentException("Missing operands");
            }
            int right = values.pop();
            int left = values.pop();
            int result = switch (token) {
                case "+" -> Math.addExact(left, right);
                case "-" -> Math.subtractExact(left, right);
                case "*" -> Math.multiplyExact(left, right);
                case "/" -> divideChecked(left, right);
                default -> throw new AssertionError(token);
            };
            values.push(result);
        }
        if (values.size() != 1) {
            throw new IllegalArgumentException("Extra operands");
        }
        return values.pop();
    }

    static final class History {
        private final int limit;
        private final Deque<String> undo = new ArrayDeque<>();
        private final Deque<String> redo = new ArrayDeque<>();
        private String text = "";

        History(int limit) {
            if (limit < 1) throw new IllegalArgumentException("Invalid limit");
            this.limit = limit;
        }

        String text() {
            return text;
        }

        void setText(String next) {
            Objects.requireNonNull(next);
            if (next.equals(text)) return;
            undo.push(text);
            if (undo.size() > limit) undo.removeLast();
            text = next;
            redo.clear();
        }

        boolean undo() {
            if (undo.isEmpty()) return false;
            redo.push(text);
            text = undo.pop();
            return true;
        }

        boolean redo() {
            if (redo.isEmpty()) return false;
            undo.push(text);
            text = redo.pop();
            return true;
        }
    }

    static void showRejected(String expression) {
        try {
            evaluatePostfix(expression);
            throw new AssertionError("Expression should have failed");
        } catch (IllegalArgumentException | ArithmeticException ex) {
            System.out.println(expression + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Node root = new Node("A", List.of(
                new Node("B", List.of(
                        new Node("D", List.of()),
                        new Node("E", List.of()))),
                new Node("C", List.of(new Node("F", List.of())))));
        System.out.println("BFS: " + bfs(root));
        System.out.println("DFS: " + dfsPreorder(root));
        System.out.println("Postfix: " + evaluatePostfix("20 3 2 * -"));
        System.out.println("Division: " + evaluatePostfix("-7 2 /"));
        showRejected("2 +");
        showRejected("1 2");
        showRejected("4 0 /");
        showRejected("2147483647 1 +");

        History history = new History(3);
        history.setText("a");
        history.setText("ab");
        history.setText("abc");
        System.out.println("Current: " + history.text());
        history.undo();
        System.out.println("Undo: " + history.text());
        history.redo();
        System.out.println("Redo: " + history.text());
        history.undo();
        history.setText("abX");
        System.out.println("New edit: " + history.text());
        System.out.println("Redo available: " + history.redo());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ArrayDequeApplications.java
java ArrayDequeApplications
```

Kết quả chuẩn:

```text
BFS: [A, B, C, D, E, F]
DFS: [A, B, D, E, C, F]
Postfix: 14
Division: -3
2 + -> IllegalArgumentException
1 2 -> IllegalArgumentException
4 0 / -> ArithmeticException
2147483647 1 + -> ArithmeticException
Current: abc
Undo: ab
Redo: abc
New edit: abX
Redo available: false
```

`record Node` và `List.copyOf` giúp ví dụ cây có dữ liệu ổn định. Các hàm nhận gốc rỗng trước khi đưa vào deque. `History` giữ trạng thái và hai ngăn xếp ở bên trong, nên bên gọi không thể tự sửa một phía lịch sử rồi phá quan hệ giữa chúng.

## 6. Lỗi thường gặp và cách tự kiểm tra

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| BFS dùng `push/pop` | Chuyển sang thứ tự LIFO | Chốt cặp `addLast/removeFirst` |
| DFS đẩy con trái trước | Nhánh phải được duyệt trước | Đẩy con theo thứ tự ngược |
| Thêm `null` để đánh dấu tầng | `NullPointerException` | Dùng `levelSize` hoặc đối tượng đánh dấu hợp lệ |
| Dùng `pop` khi rỗng | `NoSuchElementException` | Kiểm tra bất biến hoặc kiểm tra rỗng trước |
| Trừ/chia đảo toán hạng | Kết quả sai dù cộng/nhân đúng | Lấy phải trước, trái sau |
| Không kiểm tra kích thước cuối biểu thức | Bỏ qua toán hạng thừa | Yêu cầu đúng một kết quả |
| Undo chỉ đổi `text` | Không còn trạng thái để Redo | Chuyển hiện tại sang ngăn xếp đối diện |
| Sửa mới nhưng giữ `redo` | Làm lại sang nhánh lịch sử cũ | Xóa `redo` sau một thay đổi mới |
| Cho rằng constructor dung lượng là giới hạn | Lịch sử tăng ngoài dự tính | Tự áp dụng giới hạn nghiệp vụ |
| Dùng chung deque giữa nhiều luồng không đồng bộ | Mất tính đúng đắn của thuật toán | Giữ một luồng sở hữu hoặc đồng bộ cả phép chuyển |

`ArrayDeque` tự tăng dung lượng, cấm `null` và không an toàn khi nhiều luồng cùng truy cập mà thiếu đồng bộ. Thêm/lấy ở hai đầu có chi phí hằng số khấu hao; tìm phần tử hoặc xóa theo giá trị có chi phí tuyến tính. Không dựa vào iterator fail-fast để bảo đảm đồng bộ. Xem [ArrayDeque API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html) và [Deque API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html) cho các cặp thao tác đầu/cuối.

Thay deque bằng một cấu trúc đồng thời cũng không tự làm toàn bộ Undo/Redo nguyên tử: thao tác ấy còn chuyển trạng thái giữa hai deque và một biến `text`. Phải bảo vệ cả phép chuyển, hoặc để một luồng duy nhất sở hữu lịch sử.

## 7. Thực hành có tiêu chí kiểm chứng

1. **Thêm nút G làm con thứ hai của C.** BFS phải cho `[A, B, C, D, E, F, G]`; DFS tiền thứ tự trái sang phải phải cho `[A, B, D, E, C, F, G]`.
2. **Tách kết quả BFS thành từng tầng.** Với cây ban đầu, kết quả phải là `[[A], [B, C], [D, E, F]]`. Kích thước tầng phải được lấy trước khi thêm các con.
3. **Kiểm tra bộ tính hậu tố.** `8 3 -` cho 5, `3 8 -` cho -5, `8 3 /` cho 2; chuỗi trắng, `1 2 + +`, `1 2 3 +`, `2 x +` phải bị từ chối. `-2147483648 -1 /` phải báo tràn số.
4. **Kiểm tra lịch sử có giới hạn.** Tạo `History(2)`, sửa lần lượt `"a"`, `"ab"`, `"abc"`. Hai lần Undo đưa về `"ab"` rồi `"a"`; lần thứ ba trả `false`, không về chuỗi rỗng vì ảnh chụp đó đã bị loại.
5. **Kiểm tra nhánh mới và thao tác không đổi.** Sau Undo, gọi `setText` với đúng nội dung hiện tại thì Redo vẫn còn; gọi với nội dung mới thì Redo phải trả `false`.

Khi giải một bài toán mới, hãy viết rõ **phần tử nào được thêm vào, ở đầu nào, khi nào được lấy ra và bất biến nào phải giữ** trước khi chọn các phương thức deque. Đó là cơ sở để dùng cùng một `ArrayDeque` cho nhiều thuật toán mà vẫn kiểm soát được thứ tự và trạng thái.
