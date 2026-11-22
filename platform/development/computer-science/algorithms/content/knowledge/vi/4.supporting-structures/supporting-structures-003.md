# Ngăn xếp cho trạng thái xử lý chưa hoàn tất

Trong nhiều thuật toán, công việc hiện tại **chưa thể kết thúc** vì phải giải quyết một hoặc nhiều công việc con trước. Thuật toán cần ghi nhớ vị trí đang xử lý, bước đã thực hiện và việc cần làm khi quay lại. **Ngăn xếp (stack)** là một cấu trúc hỗ trợ để lưu những trạng thái còn dang dở này; nó được dùng trong duyệt cây và đồ thị, mô phỏng đệ quy, quay lui, xử lý biểu thức và tìm kiếm theo chiều sâu.

Tư tưởng cốt lõi không chỉ là đưa đối tượng lên stack rồi lấy xuống. Mỗi phần tử trong stack phải mô tả đủ **công việc hoặc điểm tiếp tục** để sau khi xử lý các bước phụ, chương trình biết chính xác phải làm gì tiếp và khi nào có thể xem trạng thái là hoàn tất.

## 1. Trạng thái chưa hoàn tất là gì?

Giả sử một nút của cây cần được xử lý **sau** khi cả hai cây con đã xử lý xong. Khi gặp nút đó, ta chưa thể đưa kết quả của nó ra ngay. Ta phải giữ lại “lời nhắc” rằng *sau hai cây con, quay về nút này để thực hiện bước cuối*. Lời nhắc ấy là một **continuation** (điểm tiếp tục).

Tùy bài toán, một phần tử stack có thể đại diện cho một trong các vai trò:

- **Công việc chưa bắt đầu:** ví dụ đỉnh đồ thị đang chờ được thăm hoặc đoạn mảng cần chia.
- **Lời gọi tạm dừng:** ví dụ hàm đệ quy đang chờ kết quả của một nhánh.
- **Khung trạng thái (frame):** ngoài đối tượng hiện tại còn chứa bước tiếp theo cần làm, như pha ENTER/EXIT hoặc chỉ số hàng xóm kế tiếp.
- **Trạng thái cần hoàn tác:** trong thuật toán quay lui, frame cần ghi nhớ lựa chọn đã thử, thay đổi đã thực hiện và dữ liệu cần khôi phục trước khi thử nhánh khác.

Một frame tổng quát có thể được mô tả bằng \((u, nextIndex, phase, partial)\):

| Thành phần | Ý nghĩa |
|---|---|
| \(u\) | Nút, trạng thái, đoạn hay bài toán con đang xử lý |
| nextIndex | Vị trí của hàng xóm/nhánh/lựa chọn chưa xét |
| phase | Đang bắt đầu, đang chờ con, hay đã đủ điều kiện kết thúc |
| partial | Kết quả trung gian hoặc thông tin cần hoàn tác nếu có |

Không bắt buộc mọi frame đều có đủ các trường này. Chỉ giữ dữ liệu mà thuật toán cần để **tiếp tục chính xác**. Nếu chỉ muốn tìm tập đỉnh có thể tới được, một mã đỉnh trên stack có thể là đủ; nếu cần ghi nhận kết quả sau khi các con hoàn tất, mã đỉnh đơn lẻ thường không đủ.

## 2. Vì sao ngăn xếp có tính LIFO lại hữu ích?

Stack theo nguyên tắc **LIFO — Last In, First Out**: trạng thái được đưa vào sau cùng sẽ được lấy ra trước. Vì vậy công việc vừa phát sinh được ưu tiên xử lý, còn các việc trước đó tạm chờ.

| Thao tác | Mục đích | Chi phí điển hình với Java ArrayDeque |
|---|---|---|
| push(x) | Đưa công việc hoặc frame lên đầu stack | \(O(1)\) khấu hao |
| pop() | Lấy và bỏ frame trên cùng | \(O(1)\) |
| peek() | Xem frame trên cùng nhưng giữ nó ở stack | \(O(1)\) |
| isEmpty() | Kiểm tra còn công việc nào chưa xử lý không | \(O(1)\) |

LIFO rất hợp với **tìm kiếm theo chiều sâu (depth-first)**: khi sinh một công việc con, thuật toán giải quyết nó trước khi trở về các việc đã chờ. Tuy vậy, stack **không tự bảo đảm** thứ tự duyệt cây hay tính đúng; phải thiết kế thứ tự push/pop, dấu đã thăm và nội dung frame đúng với đặc tả.

**Quy tắc đảo thứ tự:** nếu cần xử lý con trái trước con phải, với stack LIFO thường phải **push con phải trước, con trái sau**. Con trái nằm trên đỉnh nên được pop trước. Ngược lại, hàng đợi FIFO thường hợp với duyệt theo từng lớp, vì công việc đưa vào trước sẽ được xử lý trước.

Trong Java 17+, có thể dùng **Deque** với **ArrayDeque**, gọi push, pop và peek để mô phỏng stack. ArrayDeque không chấp nhận null. Khi stack có thể rỗng, hãy kiểm tra isEmpty để tránh lấy phần tử không tồn tại.

## 3. Hai mẫu sử dụng stack khác nhau

### 3.1. Stack chứa công việc đang chờ (worklist)

Mỗi phần tử chỉ đại diện cho công việc **sẽ được xử lý**. Cấu trúc vòng lặp thường là:

~~~text
push(trạng thái ban đầu)
while stack không rỗng:
    công_việc = pop()
    xử lý công_việc
    tìm các công_việc_con hợp lệ
    push các công_việc_con theo thứ tự mong muốn
~~~

Mẫu này thích hợp để thăm các đỉnh có thể đến được hoặc duyệt các trạng thái tìm kiếm. Cha có thể được pop khỏi stack trước khi các con được xử lý: **không còn frame của cha chờ bước kết thúc**. Điều đó không sao khi yêu cầu chỉ là thăm hoặc phát sinh công việc tiếp theo.

Với đồ thị có chu trình, cần quản lý việc **đã lên lịch/đã thăm** để không sinh cùng công việc lặp vô hạn. Một chính sách đơn giản là đánh dấu đỉnh đã được lên lịch **ngay khi push lần đầu**, bảo đảm mỗi đỉnh được push tối đa một lần.

Mẫu worklist kiểu này tìm đúng tập đỉnh tới được, nhưng không nhất thiết cho cùng **cây khám phá** hoặc sự kiện ENTER/EXIT như DFS đệ quy. Vì thế không nên dùng nó thay cho mô phỏng lời gọi đệ quy khi thuật toán cần thứ tự kết thúc chính xác.

### 3.2. Stack chứa điểm tiếp tục (continuation frames)

Ở mẫu thứ hai, một công việc cha **vẫn đang hoạt động** trong khi xử lý con. Ta phải biết lúc nào trở lại cha và tiếp tục từ đâu.

Có hai cách thông dụng:

- **Frame hai pha ENTER/EXIT.** Khi pop ENTER(u), đẩy EXIT(u) làm lời nhắc cho bước kết thúc, rồi đẩy các công việc con ở phía trên. Chỉ khi pop EXIT(u), thuật toán mới hoàn tất nút \(u\).
- **Frame có nextIndex.** Giữ frame của nút \(u\) trên stack, theo dõi vị trí hàng xóm hoặc lựa chọn tiếp theo. Mỗi khi khám phá một con, tăng nextIndex rồi push frame của con. Khi con hoàn tất và pop, frame cha lại ở đỉnh với vị trí tiếp tục đã được lưu.

Mẫu đầu gọn cho những bài toán chỉ cần hành động **trước/sau** các con. Mẫu thứ hai phù hợp khi tiến trình của cha là một vòng lặp với nhiều hàng xóm/lựa chọn cần tiếp tục theo từng bước.

## 4. Ví dụ: duyệt hậu tự một cây nhị phân

Xét cây sau:

~~~text
        1
       / \
      2   3
     / \   \
    4   5   6
~~~

**Duyệt hậu tự (postorder)** xử lý *cây con trái → cây con phải → nút cha*. Kết quả mong muốn là:

~~~text
4 5 2 6 3 1
~~~

Nếu chỉ pop nút 1 và ghi ngay giá trị 1, kết quả sai vì cha được ghi trước các con. Thay vào đó, dùng hai loại frame:

- **ENTER(u):** còn phải xử lý các con của \(u\).
- **EXIT(u):** đã xử lý xong các con; bây giờ mới ghi \(u\).

Khi gặp ENTER(u), lần lượt push **EXIT(u)**, **ENTER(con phải)** rồi **ENTER(con trái)** nếu có. Vì LIFO, các frame của cây con trái được xử lý trước cây con phải; EXIT(u) nằm dưới cùng, nên chỉ được lấy ra khi hai cây con đã xử lý xong.

Bảng mô tả các bước đầu, với đỉnh stack nằm về bên phải:

| Bước | Pop | Push thêm theo thứ tự | Kết quả đã ghi |
|---|---|---|---|
| Khởi tạo | — | ENTER(1) | Rỗng |
| 1 | ENTER(1) | EXIT(1), ENTER(3), ENTER(2) | Rỗng |
| 2 | ENTER(2) | EXIT(2), ENTER(5), ENTER(4) | Rỗng |
| 3 | ENTER(4) | EXIT(4) | Rỗng |
| 4 | EXIT(4) | Không có | 4 |
| 5 | ENTER(5) | EXIT(5) | 4 |
| 6 | EXIT(5) | Không có | 4, 5 |
| 7 | EXIT(2) | Không có | 4, 5, 2 |

Sau đó nhánh của 3 cho ra 6, rồi 3; cuối cùng EXIT(1) tạo 1. Frame EXIT(1) **lưu trạng thái công việc cha chưa hoàn tất** trong suốt quá trình con được duyệt.

Phải phân biệt **nút đang chờ ghi kết quả** với **nút đã ghi kết quả**. Nếu thêm giá trị vào danh sách ở cả ENTER và EXIT, hoặc thêm ở ENTER trong khi yêu cầu hậu tự, thứ tự và số lượng kết quả sẽ sai.

## 5. Java 17+: frame ENTER/EXIT và stack công việc

Chương trình hoàn chỉnh dưới đây hiện thực hai mẫu:

1. **postorder**: dùng frame của nút cây với cờ afterChildren để biết khi nào cần ghi nút.
2. **reachableOrder**: dùng stack các đỉnh của đồ thị có hướng, đánh dấu ngay khi đưa đỉnh vào stack để xử lý được cả chu trình.

Tạo tệp **PendingStackDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

public class PendingStackDemo {
    record Node(int value, Node left, Node right) {}
    record Frame(Node node, boolean afterChildren) {}

    static List<Integer> postorder(Node root) {
        List<Integer> result = new ArrayList<>();
        if (root == null) {
            return result;
        }

        Deque<Frame> stack = new ArrayDeque<>();
        stack.push(new Frame(root, false));

        while (!stack.isEmpty()) {
            Frame frame = stack.pop();
            Node node = frame.node();

            if (frame.afterChildren()) {
                result.add(node.value());
                continue;
            }

            stack.push(new Frame(node, true));
            if (node.right() != null) {
                stack.push(new Frame(node.right(), false));
            }
            if (node.left() != null) {
                stack.push(new Frame(node.left(), false));
            }
        }

        return result;
    }

    static List<Integer> reachableOrder(
            List<List<Integer>> adjacency, int start) {
        if (start < 0 || start >= adjacency.size()) {
            throw new IllegalArgumentException("Invalid start vertex");
        }

        boolean[] scheduled = new boolean[adjacency.size()];
        Deque<Integer> pending = new ArrayDeque<>();
        List<Integer> order = new ArrayList<>();

        scheduled[start] = true;
        pending.push(start);

        while (!pending.isEmpty()) {
            int vertex = pending.pop();
            order.add(vertex);

            List<Integer> neighbors = adjacency.get(vertex);
            for (int i = neighbors.size() - 1; i >= 0; i--) {
                int next = neighbors.get(i);
                if (!scheduled[next]) {
                    scheduled[next] = true;
                    pending.push(next);
                }
            }
        }

        return order;
    }

    public static void main(String[] args) {
        Node root = new Node(
                1,
                new Node(2,
                        new Node(4, null, null),
                        new Node(5, null, null)),
                new Node(3, null,
                        new Node(6, null, null)));

        System.out.println("Postorder: " + postorder(root));
        System.out.println("Empty tree: " + postorder(null));

        List<List<Integer>> graph = List.of(
                List.of(1, 2),
                List.of(2, 3),
                List.of(0, 3),
                List.of());

        System.out.println("Reachable: " + reachableOrder(graph, 0));
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc cao hơn:

~~~bash
javac PendingStackDemo.java
java PendingStackDemo
~~~

Stdout chính xác:

~~~text
Postorder: [4, 5, 2, 6, 3, 1]
Empty tree: []
Reachable: [0, 1, 3, 2]
~~~

**Diễn giải kết quả:**

- Mỗi nút cây được gặp ở pha ENTER trước; sau khi ENTER được pop, thuật toán tạo một EXIT cùng nút và đặt các nút con phía trên. Khi gặp EXIT, mới thêm giá trị vào result.
- Đối với đồ thị, từ 0 ta push 2 rồi 1 nên pop 1 trước. Từ 1, đỉnh 3 được push, còn đỉnh 2 đã được đánh dấu khi push từ 0. Do đó thứ tự pop là 0, 1, 3, 2.
- Đồ thị có chu trình **2 → 0**, nhưng scheduled[0] đã là true nên chương trình không đẩy 0 lần nữa.
- Node và Frame dùng cú pháp record có sẵn trong Java 17. Boolean afterChildren thể hiện **pha xử lý**, tương đương cặp trạng thái ENTER/EXIT. Danh sách result là kết quả được lưu riêng, không phải chính ngăn xếp hỗ trợ.

**Giả thiết quan trọng:** postorder nhận một **cây nhị phân hữu hạn** đúng nghĩa (không có chu trình; mỗi nút có một vị trí trong cấu trúc cây). Nếu dùng chung một Node ở hai nhánh thì nó có thể được ghi nhiều lần; nếu tạo chu trình thì có thể lặp vô hạn. reachableOrder nhận đồ thị có đỉnh đánh số 0 đến \(V-1\), chỉ số hàng xóm hợp lệ, không có null; phiên bản dùng truy cập neighbors.get(i) hiệu quả nhất với danh sách kề cho phép truy cập theo chỉ số trong \(O(1)\).

## 6. Bất biến và lập luận tính đúng

Một **bất biến vòng lặp** là tính chất đúng trước và sau mỗi vòng lặp, giúp chứng minh rằng thuật toán không bỏ sót, xử lý sai thứ tự hoặc lặp vô hạn.

### Với hậu tự cây

Ta có ba tính chất:

1. **Một nút chỉ được ghi khi EXIT của nó được lấy ra.** Mã kiểm tra afterChildren trước khi thêm vào result.
2. **Khi EXIT(u) nằm trên đỉnh, hai cây con của u đã xử lý xong.** Lúc ENTER(u), EXIT(u) được push trước các con; LIFO bắt buộc các frame con phía trên phải được xử lý hết trước EXIT(u).
3. **Mỗi nút xuất hiện đúng một lần ở mỗi pha ENTER và EXIT.** Với cây hữu hạn không chia sẻ nút, không có thao tác push ngược lại ENTER của tổ tiên. Vì thế mỗi nút được ghi đúng một lần và stack cuối cùng rỗng.

Hai tính chất đầu chứng minh thứ tự **trái → phải → cha**, tính chất thứ ba chứng minh bao phủ toàn bộ nút và kết thúc. Trường hợp root null trả danh sách rỗng, đúng với cây rỗng.

### Với worklist đồ thị

- Mọi đỉnh được push đều **tới được** từ start: start là trường hợp đầu tiên; đỉnh mới chỉ được push khi là hàng xóm của đỉnh đã tới được.
- Đặt scheduled[v] = true **ngay khi push**, nên không đỉnh nào được push lần thứ hai; chu trình không tạo vòng lặp vô hạn.
- Khi pending rỗng, mọi cạnh đi ra từ các đỉnh đã pop đều đã được xem xét. Một đỉnh tới được mà chưa hề push sẽ mâu thuẫn với việc đã xử lý đường đi từ start đến đỉnh đó.

Do đó danh sách chứa đúng các đỉnh có thể đến được, mỗi đỉnh một lần. **Thứ tự kết thúc các lời gọi**, phân loại cạnh hay cây DFS đệ quy là những yêu cầu mạnh hơn; không suy ra chỉ từ mảng scheduled và thứ tự pop của worklist.

## 7. Mô phỏng sát DFS đệ quy bằng chỉ số nextNeighbor

Một DFS đệ quy điển hình làm như sau:

~~~text
dfs(u):
    đánh dấu u đã bắt đầu
    for từng hàng xóm v của u theo thứ tự:
        nếu v chưa bắt đầu:
            dfs(v)
    đánh dấu u đã hoàn tất
~~~

Trong lúc đang chạy dfs(v), lời gọi dfs(u) vẫn tồn tại và phải nhớ **đã xét tới hàng xóm nào**. Khi v kết thúc, u tiếp tục từ hàng xóm kế tiếp thay vì duyệt lại từ đầu.

Một stack tường minh có thể sử dụng frame **(u, nextIndex)**, giữ frame cha trên stack bằng peek:

~~~text
đánh dấu s đã bắt đầu
push Frame(s, 0)

while stack không rỗng:
    f = peek()
    if f.nextIndex == số hàng xóm của f.u:
        đánh dấu f.u đã hoàn tất
        pop()
    else:
        v = hàng xóm thứ f.nextIndex của f.u
        tăng f.nextIndex trước khi đi sâu
        if v chưa bắt đầu:
            đánh dấu v đã bắt đầu
            push Frame(v, 0)
~~~

Đây là **mã giả** mô tả cách tổ chức trạng thái, không phải chương trình Java độc lập. Trong Java, cần class frame có trường nextIndex thay đổi được, hoặc thay frame bằng phiên bản mới có chỉ số tăng. Khi đẩy con v, frame cha vẫn nằm dưới và **đã ghi vị trí cần tiếp tục**. Khi v kết thúc và bị pop, cha lại ở đỉnh và duyệt hàng xóm tiếp theo.

Kỹ thuật này giúp mô phỏng thứ tự vào/ra của DFS đệ quy khi cần thời gian khám phá, thời gian kết thúc, phát hiện chu trình có hướng hoặc phân loại cạnh. Trong những bài toán đó, trạng thái thường còn gồm màu WHITE/GRAY/BLACK: chưa bắt đầu, đang trên đường duyệt, đã hoàn tất. Việc chỉ lưu một boolean visited mà không phân biệt “đang hoạt động” và “đã xong” có thể không đủ.

## 8. Đánh giá chi phí thời gian và bộ nhớ

Chi phí push/pop nhỏ không có nghĩa toàn bộ thuật toán chạy trong \(O(1)\). Cần đếm **bao nhiêu frame được tạo**, mỗi frame làm bao nhiêu việc và có bao nhiêu frame chờ cùng lúc.

| Thuật toán hoặc cách dùng | Thời gian | Bộ nhớ phụ | Bộ nhớ lưu kết quả |
|---|---|---|---|
| Postorder cây nhị phân \(N\) nút cao \(h\) với ENTER/EXIT | \(\Theta(N)\) | \(O(h)\) frame | \(\Theta(N)\) số nếu trả List |
| Duyệt reachable trên đồ thị \(V\) đỉnh, \(E\) cạnh bằng danh sách kề | \(O(V+E)\) khi truy cập hàng xóm hiệu quả | \(O(V)\) cho stack và scheduled | \(O(V)\) nếu giữ thứ tự thăm |
| DFS với frame (u, nextIndex) | \(O(V+E)\) | \(O(V)\) frame/trạng thái thăm trong trường hợp xấu nhất | Tùy dữ liệu cần trả |
| Quay lui độ sâu tối đa \(d\), mỗi frame chỉ giữ lựa chọn kế tiếp | Phụ thuộc số nhánh được xét, có thể tăng theo hàm mũ | \(O(d)\) frame nếu mỗi frame có kích thước hằng số | Phụ thuộc số nghiệm có cần lưu lại không |

Với postorder, mỗi nút tạo một ENTER và một EXIT, nên số lần pop là \(2N\). Stack chứa những nút đang trên đường xử lý và các nhánh chờ; ở **cây nhị phân** số frame đồng thời là \(O(h)\). Cây cân bằng có thể có \(h=O(\log N)\), cây rất lệch có \(h=O(N)\).

Với worklist đồ thị, scheduled ngăn push trùng nên có nhiều nhất \(V\) lần push và pop. Tất cả danh sách kề được duyệt tổng cộng không quá \(E\) cạnh, dẫn tới \(O(V+E)\) nếu truy cập hàng xóm bằng chỉ số có chi phí \(O(1)\). Stack và mảng scheduled đều có cận \(O(V)\); danh sách order được tính riêng là **đầu ra**.

Quay lui với frame lưu nextChoice và chỉ xét một nhánh con mỗi lần có thể dùng \(O(d)\) frame. Nhưng nếu mỗi mức **push tất cả \(b\) nhánh con cùng lúc**, số việc đang chờ có thể lên đến \(O(bd)\); không được mặc nhiên gán mọi thuật toán có stack là \(O(d)\) bộ nhớ.

**Đệ quy so với stack tường minh:** thay ngăn xếp lời gọi của JVM bằng ArrayDeque thường vẫn giữ bậc độ phức tạp theo độ sâu. Lợi ích là chủ động lưu frame và điều khiển quá trình, không phụ thuộc trực tiếp giới hạn call stack cho những đầu vào sâu. Điều đó không loại trừ khả năng hết heap nếu số frame hoặc kết quả rất lớn.

## 9. Quay lui: lưu cả bước tiếp theo và việc cần hoàn tác

Trong bài toán chọn tổ hợp, đi mê cung hay giải câu đố, một trạng thái có thể chứa:

- Độ sâu hoặc chỉ số của biến đang quyết định.
- Lựa chọn tiếp theo chưa thử (nextChoice).
- Phương án đang xây dựng; thông tin cần kiểm tra ràng buộc.
- Các thay đổi cần hoàn tác khi nhánh kết thúc.

Chu trình xử lý thường là **chọn → cập nhật trạng thái → khám phá con → hoàn tác → thử lựa chọn tiếp theo**. Nếu quên hoàn tác, lựa chọn ở một nhánh sẽ làm ảnh hưởng nhánh khác. Nếu hoàn tác quá sớm, con không còn nhìn thấy trạng thái mà nó cần. Do vậy frame không thể chỉ ghi một mã nút khi thuật toán còn phải biết **đang ở giai đoạn nào và những thay đổi nào đang có hiệu lực**.

Với bài toán liệt kê **tất cả đường đi đơn** của một đồ thị, visited dùng để ngăn một đỉnh xuất hiện hai lần **trên đường đi hiện tại**. Không nên đánh dấu visited toàn cục rồi cấm mọi nhánh sau dùng lại đỉnh, vì điều đó có thể làm mất đường đi hợp lệ. Đây là ví dụ cho thấy ngữ nghĩa của trạng thái đã thăm và cách hoàn tác phải xuất phát từ đề bài, không từ việc đang dùng stack.

Nếu cần trả *tất cả nghiệm*, bộ nhớ lưu kết quả có thể lớn hơn nhiều so với bộ nhớ stack; nếu chỉ đếm hoặc phát nghiệm cho consumer, có thể không giữ toàn bộ kết quả. Chi phí thời gian khám phá các nhánh vẫn phụ thuộc số trạng thái thực sự phải xét.

## 10. Các lỗi thường gặp

- **Chỉ push mã nút khi cần điểm tiếp tục.** Nếu có việc phải làm *sau khi* con hoàn tất, hãy dùng EXIT/ENTER hoặc frame nextIndex; nếu không, thuật toán mất bước kết thúc của cha.
- **Đảo sai thứ tự push.** LIFO lấy phần tử cuối cùng trước. Nếu muốn trái rồi phải, hãy push phải rồi trái.
- **Pop cha quá sớm trong mô phỏng đệ quy.** Nếu cần trở lại cha để duyệt lựa chọn tiếp theo, phải giữ frame cha ở stack hoặc đẩy continuation tương đương.
- **Quên tăng nextIndex trước khi đi sâu.** Khi con kết thúc, frame cha có thể lại chọn đúng con đó, tạo vòng lặp.
- **Đánh dấu visited không đúng thời điểm.** Chu trình có thể làm công việc lặp, hoặc đánh dấu toàn cục có thể loại nghiệm hợp lệ trong bài toán nhiều đường đi.
- **Ghi kết quả ở pha sai.** Với hậu tự, ghi ở ENTER sẽ cho thứ tự sai; ghi ở cả ENTER và EXIT gây trùng nút.
- **Dùng frame chia sẻ trạng thái mutable mà không kiểm soát.** Một nhánh sửa mảng/danh sách dùng chung, nhánh kế tiếp đọc dữ liệu còn sót; cần cô lập, sao chép có chủ đích hoặc hoàn tác chính xác.
- **Không xử lý đầu vào rỗng và chỉ số sai.** Với Java ArrayDeque, pop trên stack rỗng gây lỗi; start ngoài miền đỉnh cũng phải được kiểm tra.
- **Đánh giá sai độ phức tạp bộ nhớ.** Stack tường minh vẫn chứa \(O(h)\) hoặc \(O(V)\) frame, chưa kể đầu vào, mảng visited và danh sách kết quả.
- **Cho rằng worklist tương đương hoàn toàn DFS đệ quy.** Cùng tìm tập đỉnh tới được không đồng nghĩa cùng thứ tự phát hiện, cạnh cây duyệt hay thời điểm kết thúc.

## 11. Quy trình thiết kế và kiểm tra

Khi cần dùng stack cho một thuật toán nhiều giai đoạn, có thể thực hiện theo trình tự:

1. **Xác định đơn vị công việc.** Stack chứa đỉnh, bài toán con, khung lời gọi hay lựa chọn cần hoàn tác?
2. **Xác định tiêu chí hoàn tất.** Khi nào một trạng thái mới thật sự xử lý xong: ngay sau lần thăm đầu hay sau các con?
3. **Thiết kế frame tối thiểu.** Cần lưu đối tượng hiện tại, phase, nextIndex, giá trị trung gian hoặc lịch sử hoàn tác nào?
4. **Lập thứ tự push và pop.** Thử cây có hai con hoặc đồ thị có hai hàng xóm để phát hiện thao tác đảo thứ tự.
5. **Nêu bất biến.** Khi frame được lấy ra, những điều gì chắc chắn đã xảy ra? Mỗi trạng thái được lên lịch bao nhiêu lần?
6. **Chứng minh kết thúc.** Các nhánh có hữu hạn không? nextIndex có tăng? visited có ngăn lặp khi có chu trình?
7. **Đếm chi phí.** Số lần push/pop, công việc khi xử lý từng frame, số frame đồng thời và dung lượng lưu kết quả.
8. **Thử biên.** Cây rỗng, một nút, cây lệch sâu, nhiều nhánh, đồ thị có chu trình, dữ liệu trùng, trường hợp không có nghiệm.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một thuật toán cần in nút cha sau hai cây con. Vì sao chỉ pop cha rồi push hai con là chưa đủ?

**Đáp án:** nếu pop cha mà không lưu continuation, chương trình sẽ không biết khi nào và bằng cách nào quay lại ghi cha sau khi cả hai con hoàn tất. Cần giữ EXIT frame hoặc frame cha có tiến độ xử lý.

**Câu 2.** Với stack LIFO, muốn duyệt con trái trước con phải thì push con nào trước?

**Đáp án:** push con phải, sau đó push con trái, để con trái nằm trên đỉnh và được pop trước.

**Câu 3.** Worklist lưu mã đỉnh và visited có giải quyết được đồ thị chứa chu trình không? Có tự động tạo đúng mọi thời điểm ENTER/EXIT của DFS đệ quy không?

**Đáp án:** có thể tìm tập đỉnh tới được và kết thúc nếu đánh dấu nhất quán (chẳng hạn ngay lúc push). Nhưng worklist đơn giản không tự bảo đảm cây khám phá và thứ tự kết thúc của DFS đệ quy; các yêu cầu đó cần frame tiếp tục.

**Câu 4.** Nếu cây nhị phân có \(N\) nút, cao \(h\), thuật toán hậu tự ENTER/EXIT trả List có thời gian và bộ nhớ gì?

**Đáp án:** thời gian \(\Theta(N)\); bộ nhớ phụ stack \(O(h)\); danh sách kết quả \(\Theta(N)\). Nếu tính tổng RAM chứa kết quả, không được chỉ ghi \(O(h)\).

**Ghi nhớ:** ngăn xếp trong bài toán này chính là **bộ nhớ của các công việc còn dang dở**. Muốn dùng đúng, phải mô hình hóa rõ trạng thái nào đang chờ, thông tin nào cần lưu để quay lại và điều kiện nào cho phép đánh dấu công việc đã hoàn tất.