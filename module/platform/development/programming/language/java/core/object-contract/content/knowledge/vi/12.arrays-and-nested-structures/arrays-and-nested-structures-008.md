# Giới hạn khi cấu trúc có tham chiếu vòng trong Java

## 1. Vấn đề: cấu trúc lồng nhau không nhất thiết là cây

Trong Java, một mảng hoặc đồ thị đối tượng có thể chứa **tham chiếu trở lại chính nó**. Khi chuỗi tham chiếu dẫn về đối tượng đã gặp, ta có **chu trình tham chiếu** (*reference cycle*). Điều này khác với cấu trúc lồng nhau thông thường, nơi mỗi nhánh cuối cùng kết thúc ở giá trị hoặc `null`.

Ví dụ với mảng tham chiếu:

~~~java
Object[] direct = new Object[1];
direct[0] = direct; // Mảng chứa trực tiếp chính nó.

Object[] outer = new Object[1];
Object[] inner = new Object[1];
outer[0] = inner;
inner[0] = outer; // Chu trình gián tiếp: outer -> inner -> outer.
~~~

Đây là **đoạn minh họa**, không phải tệp chạy độc lập. Cả hai trường hợp đều hợp lệ về mặt kiểu dữ liệu: mảng `Object[]` có thể chứa tham chiếu đến các mảng `Object[]` khác, kể cả chính mình.

Một cấu trúc **không có chu trình** cũng có thể chia sẻ phần tử:

~~~java
Object[] shared = {"leaf"};
Object[] acyclic = {shared, shared};
~~~

Hai vị trí trong `acyclic` trỏ đến cùng `shared`. Việc **dùng lại tham chiếu** không tự động tạo chu trình, vì không có đường đi từ `shared` quay về `acyclic`. Phân biệt hai trường hợp này rất quan trọng khi thực hiện so sánh sâu, tính hash, in nội dung và duyệt đồ thị.

## 2. Giới hạn chính thức của các API `Arrays`

Các phương thức trong `java.util.Arrays` có hành vi khác nhau khi gặp mảng lồng nhau hoặc mảng có chu trình:

| API | Với mảng lồng nhau không có chu trình | Với mảng chứa chu trình |
| --- | --- | --- |
| `Arrays.equals(Object[], Object[])` | So sánh các phần tử theo `Objects.equals` ở mức trực tiếp; mảng con mặc định so sánh theo tham chiếu | Không chủ động đi sâu qua mảng con nên không tự đệ quy vì cấu trúc mảng; kết quả không phải so sánh sâu |
| `Arrays.hashCode(Object[])` | Băm các phần tử trực tiếp; mảng con dùng `hashCode()` của đối tượng mảng | Không chủ động băm sâu các mảng con; vẫn phải cẩn trọng nếu phần tử khác có `hashCode()` tự đệ quy |
| `Arrays.toString(Object[])` | In phần tử trực tiếp; mảng con thường hiện dạng tên kiểu + mã băm theo danh tính | Không tạo biểu diễn sâu hay mô tả liên kết vòng đầy đủ |
| `Arrays.deepEquals(Object[], Object[])` | So sánh đệ quy mảng tham chiếu và so sánh nội dung mảng nguyên thủy tương ứng | **Hành vi không được xác định** (*undefined*) nếu một trong hai mảng chứa chính nó trực tiếp hoặc gián tiếp |
| `Arrays.deepHashCode(Object[])` | Tính mã băm từ nội dung lồng nhau | **Hành vi không được xác định** với mảng tự tham chiếu trực tiếp hoặc gián tiếp |
| `Arrays.deepToString(Object[])` | In nội dung mảng lồng nhau | **Có xử lý vòng giữa các mảng**: thay nhánh tham chiếu vòng bằng `[...]` để tránh đệ quy vô hạn trong trường hợp này |

**Điểm quan trọng nhất:** `deepEquals` và `deepHashCode` có phạm vi được đặc tả cho cấu trúc mảng lồng nhau **không có chu trình**. Tên “deep” không có nghĩa các phương thức này là thuật toán tổng quát xử lý mọi đồ thị đối tượng có tham chiếu vòng.

Theo tài liệu API Java, việc gọi `Arrays.deepHashCode` trên một mảng chứa chính nó qua một hoặc nhiều cấp là *unacceptable* và có hành vi không xác định; tài liệu `Arrays.deepEquals` cũng quy định tương tự. Vì thế **không dựa vào kết quả trả về hay một loại ngoại lệ cụ thể** nếu truyền cấu trúc có vòng.

## 3. Vì sao `deepEquals` và `deepHashCode` gặp giới hạn?

Với dữ liệu **không có vòng**, định nghĩa sâu có thể triển khai bằng việc đi theo các mảng con cho tới phần tử lá:

- `deepEquals(a, b)` so sánh các vị trí tương ứng; nếu cùng là mảng tham chiếu, nó tiếp tục so sánh sâu; nếu là hai mảng nguyên thủy cùng loại, nó dùng cách so sánh tương ứng như `Arrays.equals(int[], int[])`.
- `deepHashCode(a)` tính toán mã băm dựa trên từng phần tử; khi gặp mảng tham chiếu bên trong, nó tiếp tục băm sâu.
- Với mảng không có vòng, `Arrays.deepEquals(a, b) == true` kéo theo `Arrays.deepHashCode(a) == Arrays.deepHashCode(b)`.

Một quá trình duyệt đệ quy không theo dõi các đối tượng đã ghé thăm có thể đi theo đường:

~~~text
A -> B -> C -> A -> B -> C -> ...
~~~

Đường đi không kết thúc ở lá. Triển khai có thể rơi vào đệ quy vô hạn rồi gây `StackOverflowError`; trong một số trường hợp khác, so sánh tham chiếu có thể khiến một nhánh dừng sớm. Tuy nhiên, **chuẩn API không quy định hành vi có chu trình**, nên không được dựa vào hiện tượng quan sát được của một JDK để kết luận phương thức hỗ trợ vòng.

Đặc biệt, đừng dùng `Arrays.deepEquals(cycle, cycle)` làm bài kiểm tra “API chịu được vòng”. Nếu cùng tham chiếu được nhận biết sớm thì một lời gọi cụ thể có thể trả về `true`, nhưng điều đó không biến lời gọi trên cấu trúc cyclic thành hợp lệ theo đặc tả.

### Không tự thử mã nguy hiểm trong chương trình ví dụ

Các lệnh sau chỉ minh họa **những lời gọi cần tránh**, không chạy chúng trong ứng dụng hay ví dụ thực hành:

~~~java
Object[] cycle = new Object[1];
cycle[0] = cycle;

// KHÔNG GỌI trên dữ liệu có vòng:
// Arrays.deepHashCode(cycle);
// Arrays.deepEquals(cycle, anotherCyclicArray);
~~~

Không nên bắt `StackOverflowError` rồi xem đó là cách xử lý chu trình bình thường. Đó là lỗi cạn tài nguyên stack; thuật toán đúng phải nhận diện và xử lý cấu trúc vòng **trước khi đệ quy không kiểm soát**.

## 4. Trường hợp riêng: `Arrays.deepToString` có xử lý vòng mảng

`Arrays.deepToString(Object[])` được thiết kế để tạo biểu diễn chuỗi của mảng nhiều chiều. Đối với **mảng tham chiếu lồng nhau có đường dẫn quay lại mảng đã nằm trên đường đệ quy**, nó thay nhánh tự tham chiếu bằng chuỗi `[...]`.

Ví dụ một mảng chỉ chứa chính nó sẽ được in thành `[[...]]`. Nếu mảng chứa phần tử `"root"` rồi một tham chiếu quay lại chính nó, kết quả là `[root, [...]]`. Chu trình gián tiếp cũng được xử lý; ví dụ `outer -> inner -> outer` tạo `[[[...]]]`.

Các dấu `[...]` là **ký hiệu hiển thị**, không có nghĩa đối tượng thực sự chứa chuỗi ký tự đó. `deepToString` không cung cấp một biểu diễn chuẩn duy nhất cho mọi đồ thị, không đánh số danh tính đối tượng và không tự quyết định hai đồ thị cyclic có bằng nhau hay không.

Giới hạn cần nhớ: việc phòng vòng được mô tả cho **mảng lồng nhau**. Nếu phần tử là đối tượng tùy biến mà `toString()` của nó tự duyệt qua một đồ thị cyclic không kiểm soát, `deepToString` không thể tự sửa thuật toán `toString()` đó. Tương tự, một `List` hoặc `Map` có chu trình vẫn cần xem xét hợp đồng riêng của lớp và các phần tử của nó.

## 5. Ví dụ hoàn chỉnh chạy với Java 17+

Chương trình sau minh họa ba nhóm kết quả an toàn: so sánh sâu trên mảng không có vòng, hiển thị mảng có vòng, và tự duyệt đồ thị liên kết đơn với khả năng ghi nhận đối tượng đã gặp.

Tạo tệp **`CyclicStructureDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;

public class CyclicStructureDemo {
    static final class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    static String describe(Node start) {
        Map<Node, Integer> seen = new IdentityHashMap<>();
        StringBuilder out = new StringBuilder();
        Node current = start;

        while (current != null) {
            if (out.length() > 0) {
                out.append(" -> ");
            }

            Integer oldId = seen.get(current);
            if (oldId != null) {
                out.append("#").append(oldId).append("(cycle)");
                break;
            }

            int id = seen.size() + 1;
            seen.put(current, id);
            out.append("#").append(id)
               .append("(").append(current.label).append(")");
            current = current.next;
        }

        return out.toString();
    }

    // Chỉ so sánh đồ thị Node có một cạnh "next" cho mỗi nút,
    // yêu cầu bảo toàn tên và đúng mẫu tham chiếu/vòng.
    static boolean sameShape(Node left, Node right) {
        Map<Node, Node> leftToRight = new IdentityHashMap<>();
        Map<Node, Node> rightToLeft = new IdentityHashMap<>();

        while (left != null && right != null) {
            if (leftToRight.containsKey(left)
                    || rightToLeft.containsKey(right)) {
                return leftToRight.get(left) == right
                        && rightToLeft.get(right) == left;
            }

            if (!Objects.equals(left.label, right.label)) {
                return false;
            }

            leftToRight.put(left, right);
            rightToLeft.put(right, left);
            left = left.next;
            right = right.next;
        }

        return left == null && right == null;
    }

    public static void main(String[] args) {
        Object[] first = {
            new int[] {1, 2},
            new Object[] {"x", new int[] {3}}
        };
        Object[] equivalent = {
            new int[] {1, 2},
            new Object[] {"x", new int[] {3}}
        };

        System.out.println("shallow equals: "
                + Arrays.equals(first, equivalent));
        System.out.println("deep equals: "
                + Arrays.deepEquals(first, equivalent));
        System.out.println("deep hash equal: "
                + (Arrays.deepHashCode(first)
                   == Arrays.deepHashCode(equivalent)));
        System.out.println("deep text: " + Arrays.deepToString(first));

        Object[] direct = new Object[2];
        direct[0] = "root";
        direct[1] = direct;
        System.out.println("direct cycle: "
                + Arrays.deepToString(direct));

        Object[] outer = new Object[1];
        Object[] inner = new Object[1];
        outer[0] = inner;
        inner[0] = outer;
        System.out.println("indirect cycle: "
                + Arrays.deepToString(outer));

        // Ba đồ thị có cấu trúc lặp; không dùng deepEquals/deepHashCode.
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        Node c = new Node("A");
        Node d = new Node("B");
        c.next = d;
        d.next = c;

        Node e = new Node("A");
        Node f = new Node("B");
        e.next = f;
        f.next = f; // Khác mẫu vòng của a -> b -> a.

        System.out.println("graph walk: " + describe(a));
        System.out.println("same graph shape: " + sameShape(a, c));
        System.out.println("different graph shape: " + sameShape(a, e));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac CyclicStructureDemo.java
java CyclicStructureDemo
~~~

Đầu ra xác định:

~~~text
shallow equals: false
deep equals: true
deep hash equal: true
deep text: [[1, 2], [x, [3]]]
direct cycle: [root, [...]]
indirect cycle: [[[...]]]
graph walk: #1(A) -> #2(B) -> #1(cycle)
same graph shape: true
different graph shape: false
~~~

### Giải thích đầu ra

1. Hai mảng `first` và `equivalent` có những mảng con được tạo riêng. `Arrays.equals` so sánh phần tử trực tiếp, nên không xem các mảng con mới là bằng nhau theo nội dung và cho `false`.
2. `Arrays.deepEquals` duyệt mảng con và phần tử lá. Cả hai cấu trúc **không có vòng** và tương đương nội dung, nên trả về `true`; mã băm sâu cũng bằng nhau.
3. `Arrays.deepToString(first)` trình bày dữ liệu lồng nhau thành `[[1, 2], [x, [3]]]`.
4. Hai mảng cyclic chỉ được truyền cho `Arrays.deepToString`. Hàm này đánh dấu tham chiếu quay vòng bằng `[...]` thay vì đi sâu mãi.
5. Hàm `describe` sử dụng `IdentityHashMap` ghi nhận đúng từng **tham chiếu Node** đã gặp. Khi quay về nút `a`, nó phát hiện ID `#1` và dừng.
6. Hàm `sameShape` duy trì ánh xạ hai chiều giữa các Node theo danh tính, đối chiếu `label` và quan hệ `next`; hai chu trình `A -> B -> A` khớp nhau, còn `A -> B -> B` khác mẫu vòng.

**Phạm vi ví dụ:** `sameShape` chỉ là thuật toán minh họa cho đồ thị mà mỗi Node có **tối đa một liên kết `next`**. Nó kiểm tra sự tương ứng từng nút và vòng tham chiếu của chính mô hình đó. Không coi nó là thuật toán tổng quát cho đồ thị có nhiều cạnh, collection lồng nhau hoặc mọi cấu trúc Java.

## 6. Vì sao dùng `IdentityHashMap` để theo dõi đối tượng đã thăm?

Khi kiểm tra vòng trong **đồ thị đối tượng**, câu hỏi cần trả lời trước tiên là: “Ta đã gặp **chính thể hiện này** chưa?”, nghĩa là dùng `==` đối với tham chiếu.

`IdentityHashMap` thực hiện so sánh khóa bằng `==`, thay cho `equals()` theo nội dung. Điều đó hữu ích vì:

- Hai Node khác tham chiếu nhưng `equals()` bằng nhau theo nghiệp vụ vẫn được phân biệt.
- Việc thêm Node vào tập đã thăm không gọi `equals()` hoặc `hashCode()` do người dùng định nghĩa, vốn có thể tự duyệt qua cấu trúc vòng.
- Duyệt dựa vào danh tính đối tượng, đúng mục tiêu phát hiện tham chiếu lặp.

Có thể tạo một `Set` theo danh tính bằng:

~~~java
Set<Object> seen =
        java.util.Collections.newSetFromMap(
                new java.util.IdentityHashMap<>());
~~~

Đây là **đoạn mã minh họa** cần đặt trong ngữ cảnh có `import java.util.Set;` hoặc dùng tên đầy đủ. Lưu ý `IdentityHashMap` không có cùng ngữ nghĩa khóa như `HashMap`: nên chỉ chọn nó khi thực sự cần bình đẳng theo **danh tính**.

Trong đồ thị có nhiều nhánh, cần phân biệt ít nhất hai tình huống:

- **Đã thăm toàn cục**: một Node xuất hiện ở hai nhánh nhưng không tạo vòng. Nó là phần tử được chia sẻ (*shared reference*), không mặc nhiên là chu trình.
- **Đang nằm trên đường duyệt hiện tại**: gặp lại Node đang nằm trong ngăn xếp đường đi hiện tại là dấu hiệu có cạnh quay về tổ tiên, tạo chu trình trong một lượt duyệt theo chiều sâu.

Với một danh sách liên kết đơn `next` như ví dụ, gặp lại cùng tham chiếu khi đi tuyến tính là đủ để xác định một vòng. Với đồ thị có nhiều cạnh, thuật toán DFS dùng các trạng thái *chưa thăm / đang thăm / hoàn tất* hoặc tập `visiting` và `visited` riêng theo mục tiêu phát hiện vòng.

## 7. So sánh hai cấu trúc có vòng cần định nghĩa “bằng nhau”

Không tồn tại một nghĩa duy nhất cho “hai đồ thị cyclic bằng nhau”. Ví dụ:

- **Bằng nhau theo danh tính:** hai biến phải trỏ cùng đối tượng (kiểm tra bằng `==`).
- **Bằng nhau theo giá trị nút:** có thể coi các nút có cùng mã nghiệp vụ là bằng nhau dù nối cạnh khác.
- **Bằng nhau theo cấu trúc (topology):** bảo toàn một ánh xạ giữa các nút, các nhãn và các cạnh; nhánh dùng chung hay chu trình khác nhau phải được phân biệt.
- **Bằng nhau theo cách triển khai nghiệp vụ:** ứng dụng có thể chỉ quan tâm một tập thuộc tính chọn lọc.

`sameShape` trong ví dụ thực thi **một định nghĩa cụ thể**: nhãn tương ứng giống nhau và quan hệ tham chiếu `next` có cấu trúc tương ứng một-một. Khi hai đường duyệt quay về cùng cặp Node đã ánh xạ, thuật toán dừng thành công; nếu một bên quay về Node khác cấu trúc, nó trả về `false`.

Đối với đồ thị tổng quát, cần kiểm soát ánh xạ hai chiều (*one-to-one mapping*), thứ tự cạnh nếu thứ tự có ý nghĩa, alias chung và chu trình. Một tập các cặp đã so sánh đôi khi tránh được đệ quy vô hạn nhưng **chưa tự động chứng minh** hai đồ thị có cùng cấu trúc theo mọi định nghĩa. Hãy xác định ngữ nghĩa trước khi lựa chọn thuật toán.

## 8. `equals()`, `hashCode()`, `toString()` tự viết cũng có thể lặp vô hạn

Rủi ro không chỉ xuất hiện trong `Arrays.deepEquals` hoặc `Arrays.deepHashCode`. Nếu lớp tự ghi đè phương thức rồi đi qua các liên kết mà không kiểm soát vòng, sự đệ quy có thể chạy mãi.

Ví dụ minh họa **không chạy độc lập**:

~~~java
@Override
public String toString() {
    return "Node(" + label + ", next=" + next + ")";
}
~~~

Nếu `next` quay lại Node hiện tại hoặc nằm trong một chu trình, việc nối chuỗi gọi `next.toString()` rồi lại quay về đối tượng cũ. Với cách triển khai này, ta có thể gặp `StackOverflowError`.

Một cách an toàn hơn cho log là chỉ in **thông tin không đệ quy**:

~~~java
@Override
public String toString() {
    return "Node(" + label + ")";
}
~~~

Nếu thật sự cần in **đồ thị đầy đủ**, nên có hàm hiển thị riêng nhận trạng thái đã thăm, như `describe`. Cách tiếp cận tương tự áp dụng cho `equals()`/`hashCode()`: không để chúng tự đệ quy không hạn chế qua mọi cạnh, đặc biệt khi đối tượng dự định làm khóa `HashMap`.

Một hàm băm dành cho **đồ thị cyclic** cần được thiết kế theo một quy ước xác định (chẳng hạn định danh nút bất biến, thứ tự duyệt và đánh dấu alias nhất quán). Phải bảo đảm điều kiện bắt buộc: nếu hai giá trị bằng nhau theo `equals()` đã chọn thì chúng có cùng mã băm. Chỉ chọn mã băm ngẫu nhiên hoặc `System.identityHashCode()` sẽ không tương thích nếu `equals()` coi các đồ thị khác tham chiếu là bằng nhau theo cấu trúc.

## 9. Phân biệt mảng, collection và tham chiếu vòng

Một số trường hợp thường bị nhập nhằng:

- **Mảng nguyên thủy** như `int[]` không thể tự chứa chính nó theo kiểu phần tử nguyên thủy. Vòng chỉ hình thành từ các tham chiếu, chẳng hạn trong `Object[]`, Node hoặc collection.
- **Mảng nhiều chiều kiểu `int[][]`** có các mảng con nguyên thủy; bản thân mảng `int[][]` không thể chứa chính nó làm phần tử `int[]` vì kiểu không khớp. Tuy nhiên một `Object[]` có thể chứa `int[]` và tham chiếu quay vòng tới các mảng `Object[]`.
- **`List`, `Set`, `Map`** có thể tổ chức dữ liệu chứa tham chiếu qua lại. Hợp đồng và cách xử lý của từng API không đồng nhất với `Arrays.deepToString`. Đừng mặc định chúng đều tự chống vòng ở `equals()`, `hashCode()` hoặc `toString()`.
- **Mảng lồng nhau rất sâu nhưng không có vòng** vẫn có thể gây cạn stack nếu một thuật toán dùng đệ quy quá sâu. Không có vòng chưa có nghĩa mọi thao tác đệ quy đều an toàn với mọi độ sâu.
- **`record` chứa mảng** không tự tạo so sánh sâu các phần tử. `equals()`/`hashCode()` được sinh cho record xử lý thành phần mảng theo ngữ nghĩa của chính đối tượng mảng (thường là danh tính), không tự thay bằng `Arrays.deepEquals`/`deepHashCode`.

Đặc biệt, `Objects.deepEquals(a, b)` cũng **không phải lời giải cho mảng có vòng**: khi cả hai đối số là mảng, phương thức này dựa vào `Arrays.deepEquals`; hạn chế về cấu trúc cyclic vẫn còn.

## 10. Chiến lược xử lý thực tế

1. **Nếu dữ liệu là mảng lồng nhau không có vòng và muốn so sánh nội dung:** dùng `Arrays.deepEquals` cùng `Arrays.deepHashCode`, khi cần biểu diễn dùng `Arrays.deepToString`.
2. **Nếu chỉ cần ghi log một mảng có tham chiếu vòng:** `Arrays.deepToString` có xử lý vòng của mảng; không dùng kết quả in làm khóa duy nhất hoặc định nghĩa cấu trúc bằng nhau.
3. **Nếu cần phát hiện vòng trong đồ thị:** duyệt theo danh tính; theo dõi trạng thái đang thăm, đã thăm bằng `IdentityHashMap` hoặc `Set` xây từ nó.
4. **Nếu cần so sánh hai đồ thị cyclic:** trước tiên định nghĩa tính bằng nhau, sau đó dùng ánh xạ cặp Node hoặc thuật toán đồ thị tương ứng, có cơ chế dừng và bảo toàn alias khi cần.
5. **Nếu cần dùng cấu trúc làm khóa băm:** ưu tiên khóa bất biến theo mã nghiệp vụ hoặc một đại diện bất biến đã chuẩn hóa. Tránh tính `equals()`/`hashCode()` bằng cách đi sâu không hạn chế trong đồ thị có vòng.
6. **Nếu dữ liệu đến từ nguồn ngoài:** kiểm tra trước tính hợp lệ và khả năng có vòng, giới hạn số nút, số cạnh hoặc độ sâu theo yêu cầu bảo vệ tài nguyên của ứng dụng.

### Checklist nhanh

- Có **tham chiếu quay về cùng đối tượng** trực tiếp hoặc qua nhiều lớp không?
- Đang sử dụng `Arrays.deepEquals` hoặc `deepHashCode` với mảng có vòng chứ?
- Có nhầm `deepToString` xử lý vòng trong mảng với một cơ chế chống vòng cho mọi đối tượng Java không?
- Tập đối tượng đã thăm có dựa vào **danh tính tham chiếu** khi mục tiêu là theo dõi cùng thể hiện không?
- Thuật toán có phân biệt **chia sẻ tham chiếu** và **chu trình thực sự**?
- Có xác định trước nghĩa của “bằng nhau” khi so sánh cấu trúc cyclic?
- Có giới hạn tài nguyên và trường hợp cấu trúc lồng quá sâu?

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một `Object[]` chứa chính nó. Có thể yên tâm gọi `Arrays.deepHashCode(array)` không?

**Đáp án:** Không. Java API quy định hành vi không xác định cho mảng tự tham chiếu trực tiếp hoặc gián tiếp.

**Câu 2.** `Arrays.deepToString(array)` có gặp vấn đề giống `Arrays.deepHashCode(array)` khi chính mảng xuất hiện lại trong cấu trúc không?

**Đáp án:** `deepToString` có cơ chế biểu diễn các nhánh mảng quay vòng bằng `[...]`. Đây là cơ chế in nội dung, không tự cung cấp khả năng so sánh hoặc băm sâu trên cấu trúc cyclic.

**Câu 3.** Hai nhánh cùng trỏ đến một mảng con, nhưng mảng con không trỏ ngược về cha. Đó có phải vòng?

**Đáp án:** Không. Đó là *shared reference*. Có cạnh dùng chung không đồng nghĩa có đường quay về điểm xuất phát.

**Câu 4.** Vì sao `IdentityHashMap` có ích khi phát hiện đối tượng đã thăm?

**Đáp án:** Nó phân biệt khóa bằng `==` thay vì gọi `equals()`/`hashCode()` của đối tượng, nhờ đó theo dõi chính xác từng thể hiện và tránh kích hoạt logic so sánh đệ quy tự viết.

**Câu 5.** Có thể dùng cùng một thuật toán băm cho mọi định nghĩa bằng nhau của đồ thị cyclic không?

**Đáp án:** Không. Cần chọn ngữ nghĩa bằng nhau, rồi thiết kế thuật toán băm tương thích; đặc biệt phải duy trì “`equals()` bằng nhau ⇒ `hashCode()` bằng nhau”.

**Ghi nhớ:** `Arrays.deepEquals` và `Arrays.deepHashCode` dành cho so sánh/băm sâu mảng **không có vòng**; việc dùng chúng với mảng cyclic có hành vi không xác định. `Arrays.deepToString` xử lý các nhánh quay vòng giữa mảng để hiển thị. Với đồ thị tham chiếu tổng quát, hãy chủ động phát hiện danh tính đã thăm và định nghĩa rõ ngữ nghĩa so sánh.

## Tham khảo API

- [Java `Arrays` API — deepEquals, deepHashCode, deepToString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)
- [Java `IdentityHashMap` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)
