# Dùng danh tính khi duyệt và theo dõi đồ thị đối tượng

Trong Java, một đồ thị đối tượng gồm các **instance** (đỉnh) và các tham chiếu nối chúng (cạnh). Khi duyệt đồ thị để xuất dữ liệu, phân tích liên kết, sao chép cấu trúc, đánh dấu đã thăm hoặc phát hiện chu kỳ, ta thường cần trả lời: **“Đúng instance này đã xuất hiện trước đó chưa?”** Đây là câu hỏi về **danh tính đối tượng (object identity)**.

Bài học phân biệt danh tính với sự bằng nhau về giá trị, hướng dẫn dùng `IdentityHashMap` để quản lý tập đã thăm và trạng thái theo từng instance, đồng thời chỉ rõ sự khác nhau giữa tham chiếu được dùng chung và chu kỳ.

## 1. Vì sao `equals()` không đủ để duyệt đồ thị đối tượng?

Xem mô hình sau:

```text
          root
          /  \
         v    v
       left  right        Hai instance khác nhau,
         \    /           nhưng có thể equals() == true.
          v  v
         shared           Hai nhánh trỏ đúng cùng instance.
            |
            +---> root    Cạnh tạo chu kỳ.
```

Ba trường hợp phải được xử lý riêng:

1. **Khác instance, bằng nhau về dữ liệu.** `left == right` là `false` nhưng `left.equals(right)` có thể là `true`, ví dụ hai nút cùng trường `value`. Nếu mục tiêu là xử lý từng instance, không được bỏ một nút vì dữ liệu của nó giống nút khác.
2. **Cùng instance theo nhiều đường.** `left.next` và `right.next` cùng trỏ đến `shared`; thuật toán chỉ nên xử lý `shared` một lần dù có hai đường đi đến nó.
3. **Chu kỳ.** Nếu `shared` trỏ ngược `root`, việc duyệt không kiểm soát có thể lặp vô hạn hoặc gây `StackOverflowError`.

Bài toán “xử lý **mỗi instance** một lần” cần danh tính; bài toán “gộp các đối tượng có **giá trị tương đương**” thường cần `equals()` và `hashCode()`. Hai bài toán có tiêu chí khác nhau, nên không thể hoán đổi tập visited một cách tùy ý.

## 2. Công cụ so sánh đúng tiêu chí

| Công cụ | Cơ chế | Dùng khi nào |
| --- | --- | --- |
| `a == b` | Hai biến trỏ đúng cùng instance, hoặc đều `null` | So sánh danh tính |
| `a.equals(b)` | Kiểm tra quan hệ tương đương do kiểu đối tượng định nghĩa | So sánh giá trị/ngữ nghĩa |
| `HashSet` / `HashMap` | Sử dụng `hashCode()` và `equals()` | Gộp các key được coi là bằng nhau |
| `IdentityHashMap` | So key bằng `==` và dùng `System.identityHashCode()` cho cơ chế băm | Theo dõi từng instance |
| `System.identityHashCode(x)` | Trả về mã băm theo danh tính, không phụ thuộc `hashCode()` được override | Hỗ trợ cơ chế băm/chẩn đoán; **không phải ID duy nhất** |

`System.identityHashCode()` **có thể trùng nhau ở hai instance khác nhau**; không dùng kết quả như một khóa định danh độc nhất hay thay thế cho phép so sánh `==`. Cũng không coi số ấy là địa chỉ bộ nhớ ổn định hoặc ID giữ nguyên giữa các lần chạy Java.

`IdentityHashMap` là cấu trúc chuyên dụng: nó chủ ý có ngữ nghĩa khóa khác `Map` thông thường. Không thay `HashMap` bằng `IdentityHashMap` cho các bài toán nghiệp vụ mà key thực sự cần được xem là bằng nhau theo `equals()`.

## 3. Tạo tập visited theo danh tính

Khi chỉ cần biết một instance đã được duyệt hay chưa, tạo `Set` dựa trên một `IdentityHashMap` còn trống:

```java
Set<Node> visited =
        Collections.newSetFromMap(new IdentityHashMap<Node, Boolean>());
```

Cần import `java.util.Set`, `java.util.Collections` và `java.util.IdentityHashMap`. Map truyền cho `Collections.newSetFromMap(...)` phải trống ngay lúc tạo set.

Sau đó, mẫu duyệt đơn giản là:

```java
if (!visited.add(node)) {
    continue; // Chính instance này đã được ghi nhận trước đó.
}
// Xử lý node, rồi đưa những nút liên kết vào danh sách chờ.
```

`add` trả về `true` đúng lần đầu ghi nhận một instance, ngay cả khi set đã có một instance khác với `equals()` tương đương. Đánh dấu trước khi mở rộng cạnh ngăn xử lý lặp khi gặp chu kỳ. Không cần `contains` rồi `add` nếu một lời gọi `add` đã trả lại thông tin cần dùng.

## 4. Ví dụ Java 17+: hai nút bằng nhau, một tham chiếu dùng chung và một chu kỳ

Chương trình sau cố ý định nghĩa `equals()` chỉ theo `value`: hai nút `left` và `right` khác instance nhưng đều có `value = "same"`. Trường `id` khác nhau giúp quan sát rõ việc duyệt có bỏ sót node nào không.

Lưu dưới tên **`IdentityGraphDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class IdentityGraphDemo {
    static final class Node {
        final int id;
        final String value;
        final List<Node> next = new ArrayList<>();

        Node(int id, String value) {
            this.id = id;
            this.value = value;
        }

        Node link(Node... targets) {
            Collections.addAll(next, targets);
            return this;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node that
                    && Objects.equals(value, that.value);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(value);
        }
    }

    static List<Integer> dfs(Node root, Set<Node> visited) {
        List<Integer> order = new ArrayList<>();
        if (root == null) {
            return order;
        }

        Deque<Node> stack = new ArrayDeque<>();
        stack.push(root);
        while (!stack.isEmpty()) {
            Node node = stack.pop();
            if (!visited.add(node)) {
                continue;
            }

            order.add(node.id);
            // Đẩy theo thứ tự ngược để nhánh trái được duyệt trước.
            for (int i = node.next.size() - 1; i >= 0; i--) {
                stack.push(node.next.get(i));
            }
        }
        return order;
    }

    enum Mark { ACTIVE, DONE }

    static boolean hasCycle(
            Node node, IdentityHashMap<Node, Mark> marks) {
        Mark mark = marks.get(node);
        if (mark == Mark.ACTIVE) {
            return true; // Quay lại node trong nhánh DFS hiện tại.
        }
        if (mark == Mark.DONE) {
            return false; // Node đã kết thúc ở nhánh trước.
        }

        marks.put(node, Mark.ACTIVE);
        boolean cycle = false;
        for (Node child : node.next) {
            if (hasCycle(child, marks)) {
                cycle = true;
            }
        }
        marks.put(node, Mark.DONE);
        return cycle;
    }

    public static void main(String[] args) {
        Node root = new Node(0, "root");
        Node left = new Node(1, "same");
        Node right = new Node(2, "same");
        Node shared = new Node(3, "shared");

        root.link(left, right);
        left.link(shared);
        right.link(shared);
        shared.link(root); // Tạo chu kỳ.

        Set<Node> identityVisited =
                Collections.newSetFromMap(
                        new IdentityHashMap<Node, Boolean>());

        System.out.println("left == right: " + (left == right));
        System.out.println(
                "left.equals(right): " + left.equals(right));
        System.out.println(
                "DFS theo identity: " + dfs(root, identityVisited));
        System.out.println(
                "DFS theo equals:   " + dfs(root, new HashSet<>()));
        System.out.println(
                "Co chu ky: " + hasCycle(root, new IdentityHashMap<>()));

        shared.next.clear(); // Xóa cạnh shared -> root.
        System.out.println(
                "Co chu ky sau khi bo canh: "
                        + hasCycle(root, new IdentityHashMap<>()));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac IdentityGraphDemo.java
java IdentityGraphDemo
```

Kết quả xác định:

```text
left == right: false
left.equals(right): true
DFS theo identity: [0, 1, 3, 2]
DFS theo equals:   [0, 1, 3]
Co chu ky: true
Co chu ky sau khi bo canh: false
```

**Diễn giải:**

- `left` và `right` tạo bởi hai lần `new` nên không trùng danh tính. `equals()` trả về `true` vì cả hai có chuỗi `"same"`.
- DFS theo danh tính đi qua `root (0) → left (1) → shared (3) → right (2)`. Khi gặp lại root từ shared, tập visited chặn xử lý lặp; shared cũng không bị xử lý lần thứ hai từ right.
- DFS với `HashSet` theo `equals()` chỉ cho `[0, 1, 3]`, vì right bị gộp với left. Với một bài toán yêu cầu ghé từng instance, đây là lỗi bỏ sót đỉnh.
- Phương thức `hasCycle` đánh dấu node đang trên nhánh DFS là `ACTIVE`, hoàn tất là `DONE`. Cạnh `shared → root` trở lại node `ACTIVE` nên chu kỳ được phát hiện. Xóa cạnh ấy làm kết quả thành `false`, dù shared vẫn có hai tham chiếu đi đến.

`equals()` trong ví dụ được đơn giản hóa có chủ đích để thấy rõ sự khác nhau giữa value và identity; trong hệ thống thực tế, hợp đồng `equals()`/`hashCode()` cần được thiết kế theo ngữ nghĩa của kiểu dữ liệu.

## 5. Gặp lại cùng instance không nhất thiết là chu kỳ

Phải phân biệt **visited** với **nhánh DFS hiện hành**:

| Quan sát | Kết luận đúng |
| --- | --- |
| `visited.add(node)` trả về `false` | Instance này đã gặp. Có thể chỉ là liên kết dùng chung. |
| Đi từ nút hiện tại tới nút `ACTIVE` trong DFS có hướng | Có cạnh quay lại một nút tổ tiên trên nhánh DFS: tồn tại chu kỳ. |
| Đi tới nút `DONE` | Nút đã được xử lý ở nhánh trước; bản thân cạnh này không chứng minh chu kỳ. |

Trong sơ đồ, root→left→shared và root→right→shared cùng hội tụ về shared. Nếu bỏ cạnh shared→root thì đó là đồ thị có hướng **không chu kỳ**, dù DFS vẫn gặp lại một instance. Vì vậy, không dùng quy tắc “đã thăm thì có chu kỳ”.

Set identity đủ cho công việc **duyệt mỗi instance một lần**. Để tìm chu kỳ trong đồ thị có hướng, dùng ba trạng thái ngầm: chưa thấy, `ACTIVE` và `DONE`, cũng phải được gắn **theo identity**. Có thể dùng `IdentityHashMap<Node, Mark>` như phương thức ở ví dụ. Khi có nhiều đỉnh gốc rời nhau, giữ cùng một map trạng thái cho cả lượt kiểm tra để không xử lý trùng.

Đệ quy của `hasCycle` có thể gặp `StackOverflowError` khi đồ thị rất sâu. Trường hợp đó nên triển khai DFS với stack tường minh, mỗi frame ghi node và chỉ số cạnh đang xét, rồi chuyển `ACTIVE → DONE` lúc frame kết thúc. Dùng `visited` đơn thuần không thay được thông tin về stack đang hoạt động.

## 6. Lưu dữ liệu riêng cho từng instance

Một `Set` chỉ lưu có/chưa. Khi cần trạng thái, kết quả phân tích hay đối tượng bản sao gắn với từng node, dùng `IdentityHashMap` trực tiếp:

```java
IdentityHashMap<Node, Integer> depthByInstance =
        new IdentityHashMap<>();

depthByInstance.put(left, 1);
depthByInstance.put(right, 1); // Hai key riêng dù equals() == true.
```

Các tình huống phổ biến:

- **Đánh dấu hai trạng thái DFS**: `IdentityHashMap<Node, Mark>` lưu `ACTIVE`/`DONE`.
- **Sao chép đồ thị có chu kỳ**: lưu `sourceInstance → cloneInstance` ngay sau khi tạo bản sao rỗng, *trước khi* duyệt các cạnh; lần gặp lại source sẽ trả bản sao đã đăng ký. Nhờ thế một đối tượng dùng chung trong nguồn vẫn dùng chung trong bản sao và chu kỳ không khiến thuật toán tạo vô hạn bản sao.
- **Tuần tự hóa đồ thị bảo toàn chia sẻ tham chiếu**: lưu `instance → id` do thuật toán tự cấp, rồi các cạnh có thể tham chiếu ID cũ thay vì mở rộng lại cùng instance.
- **Phân tích/caching trong một lượt duyệt**: gắn kết quả tạm cho từng instance mà không gộp những node bằng nhau về giá trị.

Đối với map, `get(key) == null` không đủ phân biệt “không có key” và “key tồn tại nhưng value bằng `null`”. Dùng `containsKey(key)` khi cần phân biệt; `IdentityHashMap.containsKey` vẫn kiểm tra theo danh tính.

Không dùng `IdentityHashMap` làm nơi ghi lâu dài những trạng thái vốn phải được chia sẻ theo key nghiệp vụ; mỗi lần tạo instance mới biểu diễn cùng một thực thể nghiệp vụ sẽ là một key khác.

## 7. Kỹ thuật DFS/BFS và chi phí

**DFS lặp** có thể dùng `ArrayDeque<Node>` với `push`/`pop`; **BFS** có thể dùng `addLast`/`removeFirst`. Với cả hai, tập visited theo identity quyết định node nào cần xử lý.

Trong ví dụ, node được thêm vào visited khi **lấy khỏi stack**. Nếu nhiều cạnh trỏ cùng node, stack có thể chứa bản tham chiếu ấy nhiều lần, nhưng phần xử lý chính chỉ chạy một lần. Một biến thể khác đánh dấu ngay khi **đưa vào stack/queue** để giảm phần tử chờ trùng; khi đổi thời điểm đánh dấu, phải đảm bảo thứ tự và quy tắc duyệt vẫn đúng.

Với `V` instance có thể tới được và `E` cạnh được đọc, thời gian kỳ vọng là `O(V + E)`; visited giữ `O(V)` tham chiếu. Khi cho phép nhiều mục chờ trùng, stack có thể tốn tới `O(E)` bộ nhớ trong trường hợp xấu. Đồ thị sâu nên dùng vòng lặp với stack tường minh để tránh giới hạn ngăn xếp đệ quy.

**Dữ liệu `null`:** `ArrayDeque` không chấp nhận phần tử `null`. Nếu danh sách liên kết có thể chứa `null`, chỉ đẩy `child` khi `child != null`. Việc map identity chấp nhận key `null` không làm nó trở thành một đỉnh hợp lệ của đồ thị.

**Thay đổi đồng thời:** `IdentityHashMap` không tự bảo đảm an toàn luồng khi nhiều luồng cập nhật. Nếu cấu trúc cạnh cũng bị sửa lúc duyệt, kết quả có thể phản ánh những thời điểm khác nhau. Cần xác định mô hình đồng bộ, snapshot hoặc giới hạn quyền sửa phù hợp; một map riêng cho mỗi lượt duyệt là mặc định dễ kiểm soát.

**Vòng đời bộ nhớ:** `IdentityHashMap` giữ tham chiếu mạnh tới key. Dùng map cục bộ trong một lượt duyệt và giải phóng sau khi hoàn tất để không vô tình giữ cả đồ thị trong bộ nhớ. `WeakHashMap` không phải map weak-identity tương đương: nó vẫn dùng `equals()`/`hashCode()`; thiết kế key yếu theo identity đòi hỏi cơ chế riêng.

## 8. Lỗi dễ gặp

| Sai lầm | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Dùng `HashSet<Node>` cho visited trong bài toán theo instance | Hai node bằng nhau về giá trị bị gộp | Dùng set dựa trên `IdentityHashMap` |
| Coi mọi lần gặp lại node là chu kỳ | Liên kết hội tụ bị báo nhầm | Theo dõi `ACTIVE` và `DONE` khi tìm chu kỳ |
| Chỉ đánh dấu node sau khi đã duyệt tất cả nhánh | Chu kỳ có thể khiến đệ quy không dừng | Đăng ký instance trước khi mở rộng nhánh |
| Tạo visited mới cho từng nhánh | Không biết nhánh khác đã gặp cùng instance | Dùng chung visited của cả lượt duyệt |
| Dùng lại visited qua các lần duyệt độc lập | Lượt sau bỏ sót instance | Tạo visited mới cho lượt mới, trừ khi chủ đích khác |
| Dùng `identityHashCode` làm định danh duy nhất | Có thể trùng mã băm giữa hai object | So danh tính bằng `==` hoặc key identity |
| Coi ID theo identity là địa chỉ bộ nhớ | Giả định sai về JVM | Không suy ra địa chỉ từ API chuẩn |
| Dùng đệ quy cho đồ thị không giới hạn độ sâu | `StackOverflowError` | Dùng stack frame tường minh |
| Lưu identity map toàn cục không dọn | Giữ instance sống lâu không cần thiết | Giới hạn vòng đời, xóa map khi xong |

## 9. Cách chọn giải pháp cho một bài toán thực tế

1. Xác định **đơn vị cần xử lý**: một instance cụ thể hay một giá trị/thực thể nghiệp vụ? Chỉ chọn identity cho trường hợp thứ nhất.
2. Xác định đồ thị có thể có **chia sẻ, chu kỳ, nút rỗng** hay không. Nếu có, thiết kế đánh dấu từ đầu; không giả định dữ liệu luôn là cây.
3. Nếu chỉ cần “duyệt một lần”, dùng `Set` trên `IdentityHashMap`; nếu cần trạng thái per-instance, dùng `IdentityHashMap<Instance, State>`.
4. Nếu phải **phát hiện chu kỳ có hướng**, theo dõi trạng thái nhánh hiện hành `ACTIVE` và hoàn tất `DONE` bằng identity.
5. Chọn DFS/BFS, thời điểm đánh dấu, cách xử lý `null`, độ sâu và bộ nhớ theo quy mô dữ liệu.
6. Tạo vùng trạng thái riêng cho mỗi lần duyệt, và kết thúc vòng đời map đúng lúc.

**Ghi nhớ:** hai đối tượng `equals()` nhau có thể vẫn là hai đỉnh riêng trong đồ thị Java. `IdentityHashMap` giúp theo dõi chính xác từng instance, còn trạng thái `ACTIVE`/`DONE` cho phép phân biệt một chu kỳ thực sự với tham chiếu được chia sẻ.
