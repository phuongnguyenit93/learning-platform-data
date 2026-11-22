# Mô hình hóa trạng thái và các phép chuyển trong thuật toán

## 1. Vì sao cần mô hình hóa trạng thái?

Nhiều bài toán không thể giải chỉ bằng cách nhìn vào một giá trị hiện tại: robot phải nhớ đã nhặt chìa khóa hay chưa; trò chơi phải nhớ quân cờ ở đâu; hệ thống đặt hàng phải biết đơn đang chờ, đã thanh toán hay đã hủy. Để thiết kế thuật toán, ta cần biểu diễn **trạng thái** của hệ thống và những **phép chuyển** hợp lệ từ trạng thái này sang trạng thái khác.

- **Trạng thái (state)** là tập thông tin đủ để xác định các hành động có thể thực hiện tiếp theo và kết quả của chúng.
- **Phép chuyển (transition)** là sự thay đổi trạng thái sau một hành động hoặc sự kiện, với điều kiện áp dụng rõ ràng.
- **Không gian trạng thái (state space)** là tập tất cả trạng thái có thể xét; **đồ thị trạng thái** có đỉnh là trạng thái và cạnh có hướng là phép chuyển.
- **Đường đi** là chuỗi trạng thái nối bởi các phép chuyển hợp lệ. Tìm lời giải thường là tìm đường từ trạng thái ban đầu tới một trạng thái đích.

Mục đích của mô hình không phải mô tả mọi chi tiết vật lý mà là giữ đúng những thông tin có thể làm thay đổi quyết định trong tương lai. Một trạng thái tốt phải **đủ thông tin**, **không mơ hồ** và **tránh biến dư thừa**.

## 2. Mô hình toán học cơ bản

Một hệ chuyển trạng thái hữu hạn có thể ký hiệu:

**M = (S, I, A, T, G, c)**

| Thành phần | Ý nghĩa |
| --- | --- |
| **S** | Tập trạng thái có thể biểu diễn. |
| **I ⊆ S** | Tập trạng thái ban đầu; nhiều bài toán chỉ có một trạng thái đầu. |
| **A** | Tập hành động hoặc sự kiện. |
| **T ⊆ S × A × S** | Quan hệ chuyển. Bộ (s, a, s′) ∈ T nghĩa là từ s có thể làm hành động a để đến s′. |
| **G ⊆ S** | Tập trạng thái thỏa điều kiện đích. |
| **c** (tùy chọn) | Chi phí của một phép chuyển, ví dụ thời gian, năng lượng hoặc số tiền. |

Viết **s —a→ s′** khi hành động a đưa s đến s′. Với mỗi hành động a, có thể mô tả bằng:

1. **Guard / tiền điều kiện** gₐ(s): hành động chỉ được phép nếu điều kiện đúng.
2. **Effect / hậu trạng thái** fₐ(s): trạng thái sau khi thực hiện hành động.
3. **Bất biến** Inv(s): tính chất cần đúng ở mọi trạng thái có thể đạt tới.

Với mô hình xác định, khi gₐ(s) đúng thì fₐ(s) trả về duy nhất một trạng thái. Với mô hình **không xác định**, cùng trạng thái và hành động có thể dẫn đến nhiều trạng thái kế tiếp, ví dụ sự kiện nhận phản hồi từ mạng có thể thành công hoặc thất bại. Không xác định không có nghĩa là mô hình sai: nó có thể phản ánh đầu vào, môi trường hoặc sự lựa chọn chưa biết.

Đặt **Succ(s) = {s′ ∈ S | tồn tại a ∈ A: (s, a, s′) ∈ T}**. Từ đây, bài toán **reachability** hỏi có đường đi từ I đến G hay không; bài toán **shortest path** còn tối ưu số bước hoặc tổng chi phí. Một trạng thái đích không nhất thiết là trạng thái kết thúc không có cạnh đi ra: thuật toán có thể chủ động dừng ngay khi đạt đích.

## 3. Cách chọn trạng thái đúng

### 3.1. Thông tin phải đủ cho quyết định tương lai

Xét robot đi trên lưới có một cửa khóa và một chìa khóa. Nếu chỉ lưu vị trí **(hàng, cột)**, ta không biết robot có thể đi qua cửa khi quay lại cùng ô đó hay không. Trạng thái phù hợp là **(hàng, cột, đãCóChìaKhóa)**. Hai lần robot ở cùng tọa độ nhưng khác giá trị đãCóChìaKhóa là **hai trạng thái khác nhau**, vì các phép chuyển hợp lệ về sau khác nhau.

Nguyên tắc thực hành: nếu hai lịch sử dẫn đến cùng một trạng thái được lưu, thì mọi lựa chọn và kết quả tương lai liên quan đến bài toán phải giống nhau. Nếu không, mô hình đang thiếu biến trạng thái.

### 3.2. Không lưu dữ liệu suy ra được hoặc không ảnh hưởng tương lai

Nếu đang tìm ít bước nhất bằng BFS, **số bước đã đi** thường được lưu riêng trong mảng khoảng cách hoặc cấu trúc truy vết, không cần đưa vào khóa định danh trạng thái nếu nó không ảnh hưởng các hành động tiếp theo. Ngược lại, nếu bài toán đặt giới hạn tối đa 10 lượt, số lượt còn lại có thể là một phần của trạng thái vì nó quyết định hành động nào còn hợp lệ.

Ví dụ: vị trí của quân mã trên bàn cờ 8 × 8 có thể mã hóa bằng cặp (r, c), với 0 ≤ r, c < 8. Không cần lưu toàn bộ chuỗi nước đi trước đó khi luật chỉ phụ thuộc ô hiện tại.

### 3.3. Định nghĩa phạm vi và tính hợp lệ

Cần ghi rõ kiểu dữ liệu, miền giá trị và ràng buộc. Với cặp bình dung tích 4 lít và 3 lít, trạng thái (a, b) thỏa **0 ≤ a ≤ 4** và **0 ≤ b ≤ 3**. Vì lượng nước được xét theo số lít nguyên, tập ứng viên có tối đa **5 × 4 = 20** trạng thái. Đây là số trạng thái có thể biểu diễn; số trạng thái **thực sự đạt được** còn phụ thuộc luật chuyển.

Nếu trạng thái có nhiều trường, cân nhắc một kiểu bất biến (immutable) như Java **record** để việc so sánh, băm và đưa vào tập visited an toàn. Tránh dùng khóa chứa đối tượng bị sửa sau khi thêm vào HashSet hoặc HashMap.

## 4. Thiết kế các phép chuyển

Quy trình hợp lý:

1. Xác định **đơn vị bước**: một lần rót nước, một nước cờ, một sự kiện mạng hay một lần xử lý lệnh?
2. Liệt kê tất cả hành động có ý nghĩa, kèm **guard** kiểm tra khi nào được thực hiện.
3. Viết hiệu ứng trên **tất cả biến bị thay đổi**; giữ nguyên các biến còn lại.
4. Bảo đảm mọi kết quả vẫn nằm trong miền trạng thái hợp lệ.
5. Xác định chi phí mỗi bước, điều kiện đích, và có cần biểu diễn lựa chọn của môi trường hay không.
6. Thử các ca biên và kiểm tra có thiếu/nhân đôi hành động không.

Hai cách mô tả thường gặp:

- **Hàm chuyển:** next = f(state, action), có thể dùng khi mọi hành động tạo tối đa một kết quả. Trước khi gọi f phải kiểm tra guard.
- **Quan hệ hoặc bộ sinh kế tiếp:** successors(state) trả về danh sách các cặp (action, nextState); phù hợp cho BFS, DFS, Dijkstra và các mô hình có nhiều nhánh.

Một phép chuyển phải có ranh giới **nguyên tử** rõ ràng: thuật toán xem hành động là một bước hoàn chỉnh. Nếu cần mô phỏng các giai đoạn trung gian của thao tác, hãy bổ sung trạng thái trung gian thay vì ngầm giả định các thay đổi diễn ra cùng lúc.

## 5. Ví dụ đầy đủ: hai bình nước 4 lít và 3 lít

**Đề bài:** Có hai bình A, B có dung tích lần lượt 4 và 3 lít; được phép đổ đầy, đổ hết hoặc rót từ bình này sang bình kia cho tới khi bình nguồn cạn hay bình đích đầy. Bắt đầu với hai bình rỗng. Hãy tìm số thao tác ít nhất để một bình chứa đúng **2 lít**.

**Trạng thái:** s = (a, b), trong đó a là lượng nước ở A và b là lượng nước ở B.

**Khởi tạo:** I = {(0, 0)}.

**Đích:** G = {(a, b) | a = 2 hoặc b = 2}.

**Tập hành động** được mô tả chính xác như sau:

| Hành động | Điều kiện cho phép | Trạng thái kế tiếp |
| --- | --- | --- |
| Đổ đầy A | a < 4 | (4, b) |
| Đổ đầy B | b < 3 | (a, 3) |
| Đổ hết A | a > 0 | (0, b) |
| Đổ hết B | b > 0 | (a, 0) |
| Rót A sang B | a > 0 và b < 3 | t = min(a, 3 − b); (a − t, b + t) |
| Rót B sang A | b > 0 và a < 4 | t = min(b, 4 − a); (a + t, b − t) |

Lưu ý: đổ đầy và đổ hết trao đổi nước với bên ngoài. **Tổng a + b không phải bất biến của toàn bộ hệ.** Chỉ trong một thao tác rót giữa hai bình thì tổng lượng nước được bảo toàn.

Một đường đi đạt đích:

1. (0, 0) —Đổ đầy B→ (0, 3)
2. (0, 3) —Rót B sang A→ (3, 0)
3. (3, 0) —Đổ đầy B→ (3, 3)
4. (3, 3) —Rót B sang A→ (4, 2)

Có **4 phép chuyển**. Vì mọi hành động đều có chi phí 1, duyệt BFS trên đồ thị trạng thái sẽ kiểm chứng đây là một lời giải ngắn nhất.

### 5.1. Bất biến và kiểm tra chuyển

Bất biến cốt lõi là **Inv(a, b) ≡ 0 ≤ a ≤ 4 và 0 ≤ b ≤ 3**. Ban đầu (0, 0) thỏa Inv. Đổ đầy hoặc đổ hết đặt một lượng nước bằng 0 hay đúng dung tích, nên không vượt biên. Khi rót A → B, lượng chuyển t = min(a, 3 − b) bảo đảm 0 ≤ a − t và b + t ≤ 3; rót ngược lại tương tự. Theo quy nạp số bước, mọi trạng thái tạo bởi các phép chuyển hợp lệ đều thỏa Inv.

Guard cũng giúp tránh **self-loop vô nghĩa**, như đổ đầy một bình đã đầy hoặc rót vào bình đã kín. Tuy nhiên, visited vẫn cần thiết: nhiều chuỗi hành động khác nhau có thể dẫn tới cùng một trạng thái.

## 6. Tìm đường bằng BFS trên đồ thị trạng thái

Với mỗi trạng thái lấy ra từ hàng đợi, BFS sinh các trạng thái kế tiếp thông qua đúng sáu luật chuyển. Một tập **visited** bảo đảm mỗi trạng thái chỉ đưa vào hàng đợi một lần. Hai bảng **parent** và **via** lưu trạng thái trước và tên hành động, từ đó dựng lại đường đi.

Thuật toán:

1. Đưa trạng thái ban đầu vào hàng đợi và visited.
2. Lấy trạng thái đầu hàng đợi. Nếu thỏa đích thì dừng.
3. Sinh toàn bộ phép chuyển hợp lệ; với mỗi trạng thái mới chưa thăm, đánh dấu visited **ngay khi đưa vào hàng đợi**, ghi parent/via.
4. Lặp đến khi tìm được đích hoặc hàng đợi rỗng.
5. Truy ngược parent từ đích về trạng thái đầu, rồi đảo danh sách thao tác.

Với đồ thị hữu hạn, BFS duyệt mỗi đỉnh và cạnh tối đa một số lần hằng số: **O(|S| + |E|)** thời gian và **O(|S|)** bộ nhớ (gồm hàng đợi, visited và truy vết). Với bài toán hai bình nước, |S| ≤ 20 và mỗi trạng thái có tối đa sáu hành động. Khi mọi cạnh có chi phí bằng nhau, BFS tìm số bước tối thiểu. Nếu chi phí không âm nhưng khác nhau, dùng **Dijkstra**; nếu chỉ cần kiểm tra có đạt đích hay không, DFS cũng có thể đủ nhưng không bảo đảm ít bước nhất.

## 7. Java 17: cài đặt mô hình và truy vết lời giải

Ví dụ dưới đây là chương trình độc lập. Mỗi **State** là một record bất biến; **Move** mang tên hành động và trạng thái kế tiếp. Thứ tự sinh hành động được cố định để ví dụ có đầu ra tái lập.

Lưu mã vào tệp **StateTransitionBfs.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util HashSet;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.Set;

public class StateTransitionBfs {
    private static final int CAP_A = 4;
    private static final int CAP_B = 3;

    record State(int a, int b) {}
    record Move(String name, State next) {}

    static List<Move> successors(State state) {
        int a = state.a();
        int b = state.b();
        List<Move> result = new ArrayList<>();

        if (a < CAP_A) result.add(new Move("Đổ đầy A", new State(CAP_A, b)));
        if (b < CAP_B) result.add(new Move("Đổ đầy B", new State(a, CAP_B)));
        if (a > 0) result.add(new Move("Đổ hết A", new State(0, b)));
        if (b > 0) result.add(new Move("Đổ hết B", new State(a, 0)));

        if (a > 0 && b < CAP_B) {
            int t = Math.min(a, CAP_B - b);
            result.add(new Move("Rót A sang B", new State(a - t, b + t)));
        }
        if (b > 0 && a < CAP_A) {
            int t = Math.min(b, CAP_A - a);
            result.add(new Move("Rót B sang A", new State(a + t, b - t)));
        }
        return result;
    }

    static boolean isGoal(State state) {
        return state.a() == 2 || state.b() == 2;
    }

    public static void main(String[] args) {
        State start = new State(0, 0);
        Queue<State> queue = new ArrayDeque<>();
        Set<State> visited = new HashSet<>();
        Map<State, State> parent = new HashMap<>();
        Map<State, String> via = new HashMap<>();

        queue.add(start);
        visited.add(start);
        State goal = null;

        while (!queue.isEmpty()) {
            State current = queue.remove();
            if (isGoal(current)) {
                goal = current;
                break;
            }
            for (Move move : successors(current)) {
                State next = move.next();
                if (visited.add(next)) {
                    parent.put(next, current);
                    via.put(next, move.name());
                    queue.add(next);
                }
            }
        }

        if (goal == null) {
            System.out.println("Không có lời giải.");
            return;
        }

        List<String> steps = new ArrayList<>();
        for (State s = goal; !s.equals(start); s = parent.get(s)) {
            steps.add(via.get(s) + " -> " + s);
        }
        Collections.reverse(steps);

        System.out.println("Bắt đầu: " + start);
        for (int i = 0; i < steps.size(); i++) {
            System.out.println((i + 1) + ". " + steps.get(i));
        }
        System.out.println("Số phép chuyển: " + steps.size());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên, lưu tệp ở UTF-8:

~~~text
javac -encoding UTF-8 StateTransitionBfs.java
java StateTransitionBfs
~~~

Đầu ra của chương trình:

~~~text
Bắt đầu: State[a=0, b=0]
1. Đổ đầy B -> State[a=0, b=3]
2. Rót B sang A -> State[a=3, b=0]
3. Đổ đầy B -> State[a=3, b=3]
4. Rót B sang A -> State[a=4, b=2]
Số phép chuyển: 4
~~~

**Giải thích:** phương thức successors cài đặt duy nhất bộ luật chuyển; điều kiện trong từng nhánh chính là guard. record tự cung cấp equals và hashCode theo hai trường a, b, nên HashSet nhận biết đúng trạng thái đã thăm. Việc đánh dấu visited lúc thêm vào hàng đợi tránh cùng trạng thái xuất hiện nhiều lần. parent và via lưu riêng thông tin truy vết, không làm phình to định nghĩa State.

## 8. Lập luận đúng đắn của mô hình và thuật toán

Một lời giải dựa trên mô hình trạng thái nên trả lời được ba câu hỏi:

**(1) Mô hình có an toàn không?** Trạng thái đầu thỏa bất biến; từng phép chuyển đều bảo toàn bất biến. Ví dụ hai bình đã chứng minh lượng nước luôn trong sức chứa. Nếu tồn tại chuyển tạo trạng thái ngoài miền, mô hình hoặc guard đang sai.

**(2) Mô hình có bao phủ mọi thao tác được phép không?** Bộ sinh successors phải liệt kê đủ mọi thao tác hợp lệ theo đề bài, và không thêm thao tác cấm. Nếu bỏ thiếu luật chuyển, thuật toán có thể kết luận “không có lời giải” sai; nếu thêm thao tác không thực tế, đường đi tìm được có thể không thi hành được.

**(3) Thuật toán tìm kiếm có bảo đảm yêu cầu không?** BFS xét các trạng thái theo số bước không giảm. Khi tất cả cạnh có cùng chi phí, trạng thái đích đầu tiên được lấy ra khỏi hàng đợi có số bước nhỏ nhất. Do không gian hữu hạn và mỗi trạng thái được thăm tối đa một lần, BFS sẽ kết thúc. Kết luận tối ưu theo **số thao tác**, không suy ra tối ưu theo lượng nước tiêu hao hay thời gian nếu các thao tác có chi phí khác nhau.

Phân biệt các thuộc tính thường dùng:

- **Reachability:** có tồn tại đường đi từ trạng thái đầu đến đích?
- **Safety:** trạng thái “xấu” có bao giờ đạt tới không? Ví dụ lượng nước vượt dung tích.
- **Liveness:** một sự kiện mong muốn cuối cùng có xảy ra không? Trong hệ có lựa chọn không xác định, kết luận liveness cần làm rõ giả thiết về lịch thực thi và tính công bằng.
- **Termination:** thuật toán hoặc tiến trình có dừng không? Một trạng thái có chu trình đi về chính nó có thể khiến mô phỏng dừng không được nếu thiếu điều kiện kiểm soát.

## 9. Cùng một tư duy cho các loại thuật toán khác

**Quy hoạch động (DP):** trạng thái là các tham số xác định một bài toán con, chẳng hạn (i, remainingCapacity) trong bài toán ba lô. Phép chuyển tương ứng chọn hoặc không chọn vật i; công thức truy hồi tổng hợp giá trị tối ưu của các trạng thái kế tiếp. Cần xác định hướng phụ thuộc và điều kiện biên để tránh phụ thuộc vòng không có lời giải rõ ràng.

**Đường đi trên lưới:** trạng thái (r, c) đủ khi khả năng di chuyển chỉ phụ thuộc vị trí; cần thêm hasKey, số nhiên liệu hoặc mặt nạ bit các công tắc khi các yếu tố đó thay đổi tính hợp lệ của bước tiếp theo. Phép chuyển là đi lên/xuống/trái/phải với guard kiểm tra biên, vật cản và điều kiện cửa.

**Giao thức hoặc workflow:** trạng thái có thể là (phase, retryCount), với phase thuộc {IDLE, WAITING, DONE, FAILED}. Sự kiện Send chuyển IDLE → WAITING; Ack chuyển WAITING → DONE; Timeout có thể tăng retryCount hoặc chuyển FAILED khi quá giới hạn. Cần chỉ rõ sự kiện ngoài hệ thống có thể đến vào thời điểm nào.

**Hệ đồng thời:** trạng thái toàn cục là tổ hợp trạng thái của các tác vụ và tài nguyên dùng chung. Phép chuyển phải mô tả thao tác nguyên tử; nếu hai thao tác có thể xen kẽ, không được tự gộp thành một bước không thể bị ngắt. Điều này quan trọng khi tìm deadlock, race condition và vi phạm bất biến.

## 10. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Thiếu biến quyết định tương lai | Hai tình huống khác nhau bị nhập làm một; visited bỏ sót lời giải. | Đặt câu hỏi: “cùng state lưu nhưng lịch sử khác thì bước kế tiếp có khác không?” |
| Thừa lịch sử, sao chép cả đường đi vào state | Không gian trạng thái phình to, khó so sánh trùng. | Chỉ lưu thông tin ảnh hưởng tương lai; đường đi lưu bằng parent. |
| Không kiểm tra guard hoặc điều kiện biên | Sinh trạng thái không hợp lệ, tràn dung tích, vượt lưới. | Viết điều kiện trước hiệu ứng và thử ca biên. |
| Quên visited ở đồ thị có chu trình | Duyệt lặp vô hạn hoặc tốn bộ nhớ. | Đánh dấu lúc enqueue; dùng khóa trạng thái bất biến. |
| Gộp hai hành động thành một “bước” không được đề cho phép | Kết quả số bước tối ưu bị sai. | Định nghĩa rõ đơn vị cạnh từ quy tắc của đề. |
| Dùng BFS cho cạnh có chi phí khác nhau | Ít cạnh chưa chắc ít tổng chi phí. | Dùng Dijkstra cho trọng số không âm; thiết kế lại mô hình chi phí khi cần. |
| Chỉ kiểm tra vài ví dụ và cho rằng đã chứng minh đúng | Có thể bỏ sót trường hợp biên hoặc nhánh không xác định. | Kết hợp thử nghiệm với bất biến, kiểm tra độ bao phủ luật và lập luận thuật toán. |

**Bùng nổ trạng thái:** nếu có n công tắc độc lập thì riêng tổ hợp bật/tắt đã có thể tạo 2ⁿ trạng thái. Giảm kích thước bằng cách bỏ biến không liên quan, chuẩn hóa trạng thái tương đương, nén bitmask, duyệt theo nhu cầu hoặc dùng tìm kiếm có heuristic. Chỉ gộp hai trạng thái khi việc gộp **bảo toàn các hành động và kết quả liên quan tới mục tiêu**; nếu không sẽ làm sai lời giải.

## 11. Checklist tự kiểm tra mô hình

- Có viết rõ trạng thái gồm những trường nào, miền giá trị và ý nghĩa của từng trường?
- Có định nghĩa đúng tập trạng thái đầu, đích và các trạng thái lỗi cần tránh?
- Có liệt kê đủ các hành động và guard, bảo đảm hiệu ứng không ra ngoài miền?
- Hai lịch sử cùng được mã hóa thành một trạng thái có thật sự có tương lai tương đương?
- Có nêu bất biến, chi phí cạnh, tiêu chí tối ưu và điều kiện dừng?
- Thuật toán tìm kiếm/DP có phù hợp với tính chất đồ thị và chi phí?
- Có kiểm thử trạng thái đầu, biên, chu trình, trạng thái không đạt được và trường hợp vô nghiệm?

**Bài tập vận dụng:** (1) Với robot trên lưới có chìa khóa và cửa khóa, đề xuất state, guard khi qua cửa và guard khi nhặt chìa khóa; giải thích vì sao (r, c) không đủ. (2) Với máy bán hàng có số dư và sản phẩm còn lại, định nghĩa một state và hai transition “nạp tiền” và “mua”, bảo đảm không bán khi thiếu tiền hoặc hết hàng. (3) Sửa bài toán hai bình thành “mỗi lần đổ đầy tốn 5, mỗi lần rót tốn 1”; nêu vì sao BFS có thể không còn tìm chi phí nhỏ nhất và chọn thuật toán thích hợp.

**Gợi ý đáp án ngắn:** (1) state = (r, c, hasKey); qua cửa chỉ hợp lệ khi hasKey = true; gặp ô chìa khóa đặt hasKey = true. (2) state = (balance, stock), nạp tiền tăng balance với lượng hợp lệ; mua chỉ khi stock > 0 và balance ≥ price, rồi trừ price và giảm stock. (3) Gán trọng số theo thao tác và dùng Dijkstra vì các chi phí không âm.

Mô hình hóa trạng thái tốt tạo ra một “hợp đồng” rõ ràng giữa **đề bài**, **bộ luật chuyển** và **thuật toán**. Khi hợp đồng này đúng, việc chọn BFS, DFS, Dijkstra, DP hay kiểm chứng bất biến trở nên có cơ sở và có thể giải thích, kiểm thử được.
