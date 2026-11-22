# Tham chiếu dùng chung và chu trình trong đồ thị đối tượng (Java)

**Bối cảnh:** Sao chép và độc lập. Khi sao chép một đối tượng Java, cần nhìn toàn bộ mạng lưới đối tượng mà nó trỏ tới, vì bản sao của đối tượng gốc chưa chắc đã độc lập với bản gốc.

## 1. Đồ thị đối tượng là gì?

Một **đồ thị đối tượng (object graph)** có thể được hình dung như sau:

- **Đỉnh (node)**: một đối tượng trong bộ nhớ.
- **Cạnh (edge)**: một trường tham chiếu, phần tử mảng hay phần tử collection trỏ tới đối tượng khác.
- **Gốc (root)**: tham chiếu từ đó ta bắt đầu duyệt, ví dụ biến `customer` hoặc `head`.
- **Danh tính (identity)**: hai tham chiếu trỏ đến *chính cùng một đối tượng*, được kiểm tra bằng `==`; khác với `equals()`, vốn có thể kiểm tra giá trị theo quy ước của lớp.

Một đồ thị không bắt buộc là cây: nhiều cạnh có thể tới cùng một đỉnh, một đỉnh có thể quay lại chính nó hoặc trở về đỉnh đã thăm.

~~~text
A.next --------> B
^                 |
|                 |
+------ B.next ---+

A.shared ---+
            +----> S
B.shared ---+
~~~

Trong ví dụ, `A` và `B` tạo **chu trình** (`A → B → A`); đồng thời cả `A.shared` và `B.shared` cùng trỏ tới **một** đối tượng `S`. Hai đặc tính này tồn tại độc lập: có thể có chia sẻ mà không có chu trình, hoặc có chu trình mà không có nút chia sẻ phụ.

### Tham chiếu dùng chung (aliasing)

~~~java
StringBuilder shared = new StringBuilder("x");
StringBuilder left = shared;
StringBuilder right = shared;
left.append("y");
System.out.println(right); // xy
System.out.println(left == right); // true
~~~

`left` và `right` là hai biến tham chiếu nhưng chỉ có **một** `StringBuilder`. Thao tác thay đổi qua một đường truy cập sẽ hiện ra ở đường còn lại. Đối tượng vẫn chỉ được cấp phát một lần.

Điều này khác với hai đối tượng có nội dung bằng nhau nhưng danh tính khác nhau, chẳng hạn `new StringBuilder("x")` và `new StringBuilder("x")`. Không được dựa vào `toString()`, `equals()` hoặc nội dung giống nhau để kết luận hai đỉnh là một.

## 2. Vì sao sao chép một đối tượng có thể chưa độc lập?

**Sao chép nông (shallow copy)** tạo một đối tượng vỏ mới rồi sao chép giá trị các trường. Với trường primitive, giá trị được sao chép. Với trường tham chiếu, *địa chỉ tham chiếu logic* được sao chép: đối tượng con vẫn là đối tượng cũ.

Ví dụ, nếu tạo `A'` bằng cách sao chép nông `A`:

~~~text
A  --next--> B --next--> A
|            |
shared       shared
|            |
+----> S <---+

A' --next--> B     (vẫn là B cũ)
 |
 shared-----> S     (vẫn là S cũ)
~~~

`A' != A` đúng, nhưng `A'.next == A.next` và `A'.shared == A.shared` cũng đúng. Nếu đi `A'.next.next`, ta về **`A` gốc**, không về `A'`. Đổi dữ liệu trong `S` bằng `A'` có thể làm dữ liệu mà `A` thấy thay đổi.

Các thao tác quen thuộc cũng thường chỉ sao chép nông đối với phần tử tham chiếu:

- `Object.clone()` mặc định thực hiện bản sao theo trường; cần tự xử lý trường mutable nếu muốn độc lập sâu. Việc gọi `clone()` còn phụ thuộc vào hợp đồng `Cloneable` và cách lớp triển khai.
- `array.clone()` tạo mảng mới, nhưng với mảng đối tượng, từng phần tử vẫn là tham chiếu đến đối tượng cũ.
- `new ArrayList<>(oldList)` tạo cấu trúc danh sách mới, không nhân bản từng đối tượng phần tử.
- `List.copyOf(oldList)` tạo danh sách không cho sửa cấu trúc qua API đó, **không biến các phần tử mutable thành immutable**. Danh sách kết quả còn có thể dùng lại danh sách đầu vào nếu đủ điều kiện.

Ngược lại, **sao chép sâu (deep copy)** theo phạm vi đã xác định phải sao chép các đối tượng mutable cần sở hữu độc lập trong đồ thị. Chữ “sâu” phải đi kèm hợp đồng rõ ràng: những nút nào được sao chép, những nút bất biến nào được phép dùng chung, các tài nguyên bên ngoài được xử lý thế nào.

## 3. Hợp đồng đúng khi sao chép đồ thị

Giả sử `f(x)` là bản sao của đối tượng gốc `x`. Với mọi nút thuộc phạm vi cần sao chép, mục tiêu là:

1. **Tách danh tính:** `f(x) != x` cho những nút mutable cần độc lập.
2. **Giữ các cạnh:** nếu `x.next == y` thì `f(x).next == f(y)` (kể cả `null`).
3. **Giữ tham chiếu dùng chung:** nếu `x.left == x.right` thì `f(x).left == f(x).right`. Một nút gốc có nhiều đường trỏ tới chỉ tạo **một** nút sao chép.
4. **Giữ chu trình:** nếu `A.next.next == A` thì `A'.next.next == A'`.
5. **Không gộp nhầm nút:** hai nút gốc *khác danh tính*, dù `equals()` trả về `true`, vẫn phải có hai bản sao khác danh tính nếu cả hai thuộc phạm vi sao chép.

Nếu tạo hai bản sao mới mỗi lần đi tới `S`, ta làm mất tính chia sẻ (`A'.shared != B'.shared`). Nếu cứ đệ quy qua `A → B → A` mà không nhớ các nút đã xử lý, chương trình có thể đệ quy vô hạn và gây `StackOverflowError`.

Vì thế, **một lần sao chép đồ thị cần bảng ánh xạ theo danh tính**: `đối tượng gốc → đối tượng sao chép`.

## 4. Thuật toán: tạo vỏ, ghi nhớ, rồi nối các cạnh

Với một nút `source`:

1. Nếu `source == null`, trả về `null`.
2. Nếu bảng đã có `source`, trả về **bản sao đã tạo**, không tạo nút mới.
3. Tạo đối tượng sao chép ban đầu với các trường dữ liệu không tham chiếu.
4. **Đưa cặp `source → copy` vào bảng ngay lập tức**, trước khi duyệt bất kỳ cạnh nào.
5. Sao chép lần lượt các cạnh bằng cùng một bảng; trả về `copy`.

Bước 4 là trọng tâm. Khi đi từ `A` qua `B` rồi quay lại `A`, bảng đã có `A'` để nối cạnh quay về. Khi đi tới `S` lần thứ hai, bảng trả về cùng `S'` đã tạo.

### Vì sao dùng `IdentityHashMap`?

`IdentityHashMap<K,V>` so sánh khóa bằng `==` và dùng hàm băm theo danh tính, phù hợp với yêu cầu “một nút gốc chỉ ánh xạ tới một nút sao chép”.

`HashMap` thông thường dựa vào `equals()` và `hashCode()`; hai đối tượng khác nhau nhưng bằng nhau về giá trị có thể bị gộp thành một khóa. Tệ hơn, `equals()`/`hashCode()` do lập trình viên viết có thể duyệt tham chiếu vòng hoặc phụ thuộc vào các trường đang thay đổi. `IdentityHashMap` tránh nhầm lẫn giữa *bằng giá trị* và *cùng danh tính*.

## 5. Ví dụ Java 17 chạy được: sao chép nông, chia sẻ và chu trình

Lưu toàn bộ chương trình dưới tên **`GraphCopyDemo.java`**:

~~~java
import java.util.IdentityHashMap;

public class GraphCopyDemo {
    static final class Node {
        final String label;  // String bất biến nên có thể dùng chung
        int count;           // trạng thái có thể thay đổi
        Node next;           // cạnh có thể tạo chu trình
        Node shared;         // cạnh có thể có nhiều nguồn trỏ tới

        Node(String label, int count) {
            this.label = label;
            this.count = count;
        }
    }

    static Node shallowCopyRoot(Node original) {
        if (original == null) {
            return null;
        }
        Node result = new Node(original.label, original.count);
        result.next = original.next;
        result.shared = original.shared;
        return result;
    }

    static Node deepCopy(Node root) {
        return copy(root, new IdentityHashMap<>());
    }

    private static Node copy(
            Node original,
            IdentityHashMap<Node, Node> visited) {
        if (original == null) {
            return null;
        }

        Node existing = visited.get(original);
        if (existing != null) {
            return existing;
        }

        Node result = new Node(original.label, original.count);
        visited.put(original, result); // Ghi nhớ TRƯỚC khi duyệt cạnh

        result.next = copy(original.next, visited);
        result.shared = copy(original.shared, visited);
        return result;
    }

    public static void main(String[] args) {
        Node a = new Node("A", 1);
        Node b = new Node("B", 2);
        Node s = new Node("S", 7);

        a.next = b;
        b.next = a;       // chu trình A -> B -> A
        a.shared = s;
        b.shared = s;     // cùng một S

        Node shallow = shallowCopyRoot(a);
        Node deep = deepCopy(a);

        System.out.println("shallow root new: " + (shallow != a));
        System.out.println("shallow B is original: " + (shallow.next == b));
        System.out.println("shallow back edge to original A: "
                + (shallow.next.next == a));

        System.out.println("deep root new: " + (deep != a));
        System.out.println("deep B new: " + (deep.next != b));
        System.out.println("deep cycle closes on copy: "
                + (deep.next.next == deep));
        System.out.println("deep sharing preserved: "
                + (deep.shared == deep.next.shared));
        System.out.println("deep S separate: " + (deep.shared != s));

        deep.shared.count = 99;
        System.out.println("S counts original/copy: "
                + s.count + "/" + deep.shared.count);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac GraphCopyDemo.java
java GraphCopyDemo
~~~

Kết quả chuẩn:

~~~text
shallow root new: true
shallow B is original: true
shallow back edge to original A: true
deep root new: true
deep B new: true
deep cycle closes on copy: true
deep sharing preserved: true
deep S separate: true
S counts original/copy: 7/99
~~~

**Đọc kết quả:**

- `shallow` có danh tính mới, nhưng `shallow.next` vẫn là `b` cũ và đường vòng vẫn quay về `a` cũ.
- `deep.next.next == deep` xác nhận chu trình đã được dựng lại *bên trong* đồ thị mới.
- `deep.shared == deep.next.shared` xác nhận hai cạnh ở đồ thị mới vẫn chia sẻ cùng một nút; `deep.shared != s` xác nhận đó là nút mới.
- Thay `deep.shared.count` thành `99` không làm thay đổi `s.count` của bản gốc (`7`). Đây là bằng chứng độc lập đối với trạng thái mutable được sao chép trong ví dụ.

Chương trình chỉ dùng `String` (bất biến), `int` và liên kết tới `Node`. Với trường chứa `List`, `Map`, mảng, hoặc một lớp mutable khác, phải áp dụng tiếp chính sách sao chép cho các đối tượng tương ứng; không thể chỉ gán lại tham chiếu và gọi đó là sao chép sâu hoàn chỉnh.

## 6. Những trường hợp dễ bỏ sót

### Nhiều gốc nhưng chung một đồ thị

Nếu hai biến gốc `root1` và `root2` cùng trỏ tới `S`, gọi `deepCopy(root1)` và `deepCopy(root2)` **riêng biệt** sẽ tạo hai bảng ánh xạ và có thể tạo hai bản sao khác nhau của `S`. Nếu hợp đồng yêu cầu giữ chia sẻ *giữa các gốc*, phải sao chép cả tập gốc trong **cùng một phiên** với một `IdentityHashMap` duy nhất. Khởi tạo bảng trước vòng lặp các gốc rồi dùng lại ở mọi lời gọi `copy(root, visited)`.

### Tự tham chiếu và chu trình dài

`node.next = node` là chu trình độ dài một. Chu trình `A → B → C → A` có độ dài ba. Cùng thuật toán trên xử lý cả hai vì mỗi nút được ghi nhớ trước khi đi tới nút tiếp theo. Đừng chỉ kiểm tra chu trình hai nút.

### Hai đối tượng “bằng nhau” nhưng không phải một

Giả sử hai đối tượng mutable `p` và `q` có cùng dữ liệu và `p.equals(q) == true`, nhưng `p != q`. Sao chép đúng cấu trúc danh tính vẫn cần `copy(p) != copy(q)`. Đây là lý do cần bản đồ danh tính, nhất là khi sao chép đồ thị các entity có `equals()` dựa trên mã định danh.

### Dữ liệu bất biến và chia sẻ có chủ đích

Các giá trị bất biến như `String` trong ví dụ có thể dùng chung an toàn; sao chép chúng không làm tăng tính độc lập của phần trạng thái mutable. Đồ thị “deep copy” không nhất thiết phải nhân bản *mọi* đối tượng vật lý nếu hợp đồng cho phép chia sẻ nút bất biến. Tương tự, thiết kế **immutable graph** hoặc **copy-on-write** có thể chia sẻ cấu trúc để tiết kiệm bộ nhớ, với điều kiện các đường dùng chung không bị sửa ngoài kiểm soát.

### Collection, mảng và đồ thị hỗn hợp kiểu

Một `List<Node>` có thể chứa cùng `Node` hai lần, hoặc collection có thể tự tham chiếu qua kiểu phần tử phù hợp. Bản sao collection cần đăng ký container vào bảng trước khi duyệt phần tử nếu muốn xử lý chu trình. Đồ thị gồm nhiều lớp đối tượng cần cơ chế ánh xạ chung theo danh tính (chẳng hạn `IdentityHashMap<Object, Object>`), rồi xử lý từng kiểu theo hợp đồng. Chỉ gọi `new ArrayList<>(oldList)` hoặc `array.clone()` sẽ giữ nguyên tham chiếu phần tử.

### Trường `final`, constructor và bất biến của lớp

Thuật toán trên khởi tạo nút trước, rồi gán cạnh; cách này thuận tiện vì `next` và `shared` không phải `final`. Với mô hình có trường tham chiếu `final` hoặc constructor yêu cầu toàn bộ liên kết hợp lệ ngay khi tạo, không thể tùy tiện gán cạnh sau xây dựng. Có thể cần thiết kế lại API copy/builder hai giai đoạn, một mô hình immutable riêng hoặc cơ chế chuyên dụng bảo toàn invariant. Không dùng reflection để phá vỡ `final` chỉ nhằm ép thuật toán này hoạt động.

### Tài nguyên ngoài bộ nhớ và trạng thái đặc biệt

Không nên sao chép mù quáng `Thread`, socket, file handle, khóa đồng bộ, kết nối cơ sở dữ liệu hay tài nguyên hệ thống. Một entity có ID từ cơ sở dữ liệu có thể cần chính sách ID mới, giữ ID, hoặc không được nhân bản. `transient`, cache và quan hệ tới dịch vụ ngoài đồ thị cũng cần quyết định rõ. **Sao chép đối tượng** và **tạo bản ghi nghiệp vụ mới** là hai hợp đồng khác nhau.

### Chu trình và garbage collector

Chu trình không tự nó gây rò rỉ bộ nhớ trong Java: garbage collector dựa trên tính *có thể truy cập từ GC roots*, nên cả một nhóm đối tượng tham chiếu vòng vẫn có thể được thu gom nếu không còn đường truy cập từ các gốc đang sống. Rò rỉ giữ tham chiếu thường xảy ra khi cache, static field, listener hoặc collection còn giữ đường tới đồ thị không cần thiết.

## 7. Chi phí, giới hạn và cách kiểm thử

Với `V` nút khác danh tính và `E` cạnh được sao chép, thuật toán duyệt mỗi nút một lần và mỗi cạnh một lần: thời gian kỳ vọng **`O(V + E)`**, bộ nhớ bảng ánh xạ và các bản sao **`O(V)`** (không kể dữ liệu tùy kích thước bên trong mỗi nút). Đệ quy còn sử dụng stack tối đa theo độ sâu đường duyệt; một chuỗi cực dài có thể gây `StackOverflowError`. Nếu đồ thị rất sâu, thay đệ quy bằng stack/queue tường minh và vẫn phải lưu `visited` **trước** khi đưa cạnh vào hàng đợi.

Khi dữ liệu đang được nhiều thread sửa đồng thời, không có gì bảo đảm bản sao phản ánh một thời điểm nhất quán. Cần snapshot bất biến, đồng bộ hóa hoặc chính sách versioning phù hợp. `IdentityHashMap` tự thân không thread-safe.

Kiểm thử nên bao gồm:

1. `null`, một nút độc lập và các trường tham chiếu `null`.
2. Tự tham chiếu (`node.next == node`) và chu trình nhiều nút.
3. Hai cạnh tới cùng một nút (hình thoi) và hai nút có nội dung bằng nhau nhưng khác danh tính.
4. Nhiều root dùng chung nút nếu API hỗ trợ sao chép nhiều gốc.
5. Đổi trạng thái mutable của bản sao và kiểm tra bản gốc không đổi; đổi bản gốc và kiểm tra bản sao không đổi.
6. Bảo toàn đúng các cạnh với `==`; đồng thời bảo đảm mọi nút mutable cần độc lập đều khác nút gốc tương ứng.
7. Dữ liệu lớn hoặc rất sâu nếu dùng trong hệ thống thực tế.

Một số lỗi thường gặp và dấu hiệu nhận biết:

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tạo root mới rồi gán tham chiếu con cũ | Bản sao và bản gốc còn sửa chung trạng thái | Sao chép tiếp các đối tượng mutable trong phạm vi |
| Gặp cạnh nào cũng tạo nút mới | Mất quan hệ dùng chung; với cycle có thể đệ quy vô hạn | Dùng bảng `original → copy` theo danh tính |
| Thêm vào bảng **sau** khi sao chép hết con | Chu trình quay lại nút chưa được ghi nhớ | Đăng ký bản sao ngay sau khi khởi tạo |
| Dùng `HashMap` khi `equals()` gộp các nút khác nhau | Sai topology, có thể mất nút | Dùng `IdentityHashMap` |
| Mỗi root có một bảng riêng dù cùng phiên sao chép | Mất chia sẻ giữa các root mới | Dùng chung một bảng xuyên suốt phiên |
| Sao chép container nhưng giữ nguyên các phần tử mutable | Chỉ sao chép nông lớp container | Sao chép phần tử theo cùng bảng ánh xạ |
| Nghĩ `List.copyOf` là deep copy | Container khó sửa nhưng phần tử vẫn mutable | Tách hợp đồng bất biến container và phần tử |
| Đệ quy trên đồ thị cực sâu | `StackOverflowError` | Duyệt lặp với stack/queue tường minh |

## 8. Tự kiểm tra

**Tình huống 1:** `A.left == A.right` trước khi sao chép. Sau deep copy đúng, `A'.left == A'.right` phải là `true`; đồng thời `A'.left != A.left` nếu đứa con đó mutable và nằm trong phạm vi cần sao chép.

**Tình huống 2:** `A.next = B; B.next = A`. Nếu bản sao của `A` là `A'` thì `A'.next.next` phải là `A'`, không phải `A`. Một bản sao root mới nhưng cạnh ngược tới nút cũ là bằng chứng sao chép nông.

**Tình huống 3:** Có hai nút `X`, `Y` khác danh tính nhưng `X.equals(Y)` trả `true`. Bảng ánh xạ sao chép phải xem đây là hai khóa riêng; dùng `IdentityHashMap` vì đích là giữ danh tính của đồ thị.

**Ghi nhớ:** Khi sao chép đồ thị đối tượng, cần giữ đúng **ai trỏ tới ai**, **những đường nào cùng trỏ một đối tượng** và **chu trình nào quay về điểm đã có**. Mẫu cốt lõi là **tạo bản sao → đăng ký theo identity → nối các cạnh bằng cùng một bảng**; sau đó kiểm tra độc lập của toàn bộ trạng thái mutable thuộc phạm vi sao chép.