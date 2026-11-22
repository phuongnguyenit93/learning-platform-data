# IDA* và đánh đổi giữa bộ nhớ với duyệt lặp

**IDA* (Iterative Deepening A*)** là một thuật toán tìm kiếm trạng thái dùng **DFS có giới hạn f=g+h** rồi lặp lại với những giới hạn lớn dần. Nó kết hợp **đánh giá heuristic của A*** với **bộ nhớ thấp của iterative deepening**. Thay vì lưu một hàng đợi ưu tiên và một tập trạng thái đã khám phá lớn, IDA* chủ yếu giữ **đường DFS đang xét**, đổi lại có thể duyệt lại nhiều trạng thái ở những vòng sau.

Đây là một chủ đề quan trọng trong nhóm **Tìm kiếm trạng thái**. IDA* đặc biệt hữu ích cho các bài toán như 8-puzzle, 15-puzzle hoặc không gian trạng thái tổ hợp, khi một heuristic đủ tốt đã có sẵn nhưng RAM không đủ chứa frontier của A*.

Nội dung bài gồm định nghĩa g/h/f, cơ chế contour, cập nhật ngưỡng, tính tối ưu, xử lý chu trình, lựa chọn heuristic và chi phí bộ nhớ, ví dụ 8-puzzle, chương trình **Java 17+ độc lập**, kiểm thử BFS và các biến thể cần chú ý.

**Câu ghi nhớ:** A* thường trả giá bằng RAM để tránh mở lại trạng thái; IDA* thường trả giá bằng việc **tính lại nhiều lần** để tiết kiệm RAM.

## 1. Bài toán tìm kiếm trạng thái

Một bài toán tìm kiếm trạng thái xác định:

- **Trạng thái xuất phát** s.
- **Điều kiện đích** isGoal(state).
- **Các hành động hợp lệ** sinh ra những trạng thái kế tiếp.
- **Chi phí** c(state,action) của từng hành động.
- **Mục tiêu tối ưu**, thường là tổng chi phí nhỏ nhất từ s tới bất kỳ đích nào.

Ví dụ 8-puzzle: một bảng 3×3 có 8 quân số và ô trống số 0, mỗi bước di chuyển ô trống sang một ô kề theo bốn hướng hợp lệ. Mỗi bước có cost=1.

~~~text
Start (minh hoa):
1 2 3
4 5 6
0 7 8

Goal:
1 2 3
4 5 6
7 8 0
~~~

Trạng thái start này cần hai bước R,R để đưa ô trống về đích.

Nếu chỉ cần tìm **một lời giải bất kỳ**, DFS có thể đủ. Nhưng DFS bình thường có thể tìm đường rất dài trước khi tìm đường ngắn. Bài này hỏi đường giải **tối ưu**, nên thứ tự giới hạn và heuristic cần được sử dụng đúng.

## 2. Ba đại lượng g, h và f

Tại nút tìm kiếm n:

- **g(n)**: chi phí từ s tới n theo đường hiện tại.
- **h(n)**: ước lượng chi phí tối thiểu còn lại từ n tới một trạng thái đích.
- **f(n)=g(n)+h(n)**: cận dưới của tổng chi phí một lời giải đi qua n, **nếu h admissible**.

Một heuristic **admissible** khi nó **không bao giờ đánh giá cao hơn chi phí tối ưu còn lại**:

**0 ≤ h(n) ≤ h*(n)**, với h*(n) là chi phí tối ưu thật sự từ n tới đích.

Thường yêu cầu h(goal)=0. Trên bài 8-puzzle, h là **tổng Manhattan distance của các quân 1..8**, không tính ô trống.

Ví dụ: đã đi g=5 bước và còn tối thiểu 7 bước theo Manhattan h=7, thì f=12. Nếu ngưỡng hiện tại bound=10, nhánh ấy **không thể** cho một lời giải có tổng cost≤10, nên có thể cắt.

### Consistency mạnh hơn admissibility

Heuristic **consistent** nếu mọi phép chuyển n→n' có chi phí c≥0 thỏa:

**h(n) ≤ c+h(n')**.

Điều này làm **f không giảm dọc đường đi**, vì g tăng thêm c. Manhattan trên 8-puzzle có mỗi bước cost1 là consistent: khi trượt một quân đúng một ô, tổng Manhattan thay đổi nhiều nhất 1.

IDA* với heuristic admissible có nền tảng tối ưu dạng tree search; consistency giúp phân tích cắt nhánh đơn giản hơn. Nếu h đánh giá quá cao thì không được khẳng định tìm lời giải tối ưu.

## 3. IDDFS, A* và IDA*: ba cách quản lý frontier

**BFS** trên graph không trọng số mở rộng theo số bước đã đi. Nó dễ đảm bảo lời giải ngắn nhất nhưng frontier có thể rất rộng.

**IDDFS** lặp DFS theo độ sâu:

~~~text
depthLimit = 0, 1, 2, 3, ...
DFS chi mo node neu depth <= depthLimit
~~~

IDDFS giữ stack tìm kiếm nhỏ, nhưng không có hướng dẫn heuristic nào để ưu tiên những nhánh gần đích.

**A*** thường chọn nút có **f nhỏ nhất** từ priority queue (open set), dùng thêm dữ liệu bestG/closed để quản lý đường đi trùng nhau. Nó có thể nhanh nhờ tái sử dụng kết quả nhưng thường lưu rất nhiều trạng thái.

**IDA*** dùng cùng f=g+h nhưng không duy trì toàn bộ open set. Thay vào đó, ở một vòng chỉ duyệt các nút có **f≤bound** bằng DFS; sau đó bắt đầu lại với bound cao hơn.

| Tiêu chí | A* | IDDFS | IDA* |
| --- | --- | --- | --- |
| Tiêu chí ưu tiên | f nhỏ nhất trong open set | Depth limit | f-bound |
| Heuristic | Có | Không bắt buộc | Có |
| Frontier | Priority queue | DFS stack | DFS stack |
| Lưu dữ liệu nhiều nút | Thường có | Ít | Ít, nếu không thêm transposition table |
| Duyệt lặp từ đầu | Không theo contour | Có | Có |
| Bộ nhớ tìm kiếm | Có thể rất lớn | O(d) | O(d) trong bản DFS/onPath |
| Tối ưu | Nếu điều kiện A* được thỏa | Theo số bước, cost1 | Nếu heuristic/chi phí/pruning thỏa điều kiện |

**IDA* không đơn giản là A* chạy bằng DFS một lần.** Một DFS duy nhất có thể không tìm được lời giải trong contour đầu tiên; vòng lặp tăng bound là thành phần bắt buộc.

## 4. Một contour của IDA* hoạt động thế nào?

Gọi **contour** là một lần DFS từ start với cùng một ngưỡng bound.

Trong mỗi lời gọi DFS:

1. Tính f=g+h.
2. Nếu **f>bound**, không mở rộng; **trả giá trị f** để góp phần tìm ngưỡng kế tiếp.
3. Nếu state là đích và f≤bound, trả **FOUND**.
4. Nếu chưa phải đích, thử các hành động hợp lệ và DFS sâu hơn.
5. Quay lui sau mỗi nhánh thất bại.
6. Trả về **giá trị f nhỏ nhất vượt bound** đã thấy từ tất cả các nhánh.

Vòng ngoài bắt đầu với:

**bound=h(start)**, vì g(start)=0.

Nếu contour chưa tìm thấy đích, bound tiếp theo không phải một con số tùy ý; nó là **min f đã vượt giới hạn**.

Pseudocode:

~~~text
IDA_STAR(start):
    bound = h(start)

    repeat:
        result = SEARCH(start, g=0, bound)

        if result == FOUND:
            return solutionPath

        if result == NO_NEXT_BOUND:
            return NO_SOLUTION

        bound = result

SEARCH(node, g, bound):
    f = g + h(node)

    if f > bound:
        return f

    if isGoal(node):
        return FOUND

    nextBound = +INFINITY

    for each legal successor child with cost c:
        if child is already on current DFS path:
            continue

        append move to current path
        result = SEARCH(child, g+c, bound)

        if result == FOUND:
            return FOUND

        undo move and state change
        nextBound = min(nextBound, result)

    return nextBound
~~~

Đây là mô hình tổng quát; phiên bản Java phía dưới giải 8-puzzle với mỗi bước cost1.

## 5. Vì sao ngưỡng kế tiếp phải là min f bị cắt?

Giả sử bound=10 và các nhánh DFS trả các f vượt ngưỡng là 13, 17, 12, 20, 15.

Ngưỡng mới nên là:

**nextBound=min(13,17,12,20,15)=12**.

Không cần thử bound=11 nếu không có nút bị cắt với f=11. Cũng không nên lấy max=20, vì nhảy quá xa có thể mở nhiều nhánh hơn cần thiết.

Với bài có trọng số hành động không đồng nhất hoặc chi phí số thực, cách **bound+1** có thể rất lãng phí, thậm chí không khớp các mốc chi phí hợp lệ.

### Ngưỡng phải tăng thật sự

Một nút chỉ trả về giá trị f khi **f>bound**, nên nextBound hợp lệ nếu hữu hạn phải **lớn hơn bound**. Nếu code cập nhật ra nextBound≤bound, lỗi logic có thể khiến vòng ngoài chạy mãi.

### Không phải lúc nào cũng tăng 1 hoặc 2

Trong 8-puzzle dùng Manhattan, có cấu trúc chẵn lẻ khiến các ngưỡng thường tăng 2. Nhưng với bài khác, các ngưỡng có thể 4,5,9,12.5,... IDA* dựa trên **giá trị f thực tế**, không dựa trên một bước nhảy cố định.

## 6. Ví dụ contour thực tế với 8-puzzle

Xét trạng thái:

~~~text
1 6 2
4 5 3
7 8 0

Ma hoa: 162453780
Goal:   123456780
~~~

Manhattan ban đầu **h(start)=4**, nhưng đường giải tối ưu cần **8 bước**.

Kết quả IDA*:

~~~text
Contour 1: bound=4, khong tim duoc goal
Contour 2: bound=6, khong tim duoc goal
Contour 3: bound=8, tim duoc goal

Moves cua o trong: L U U R D L D R
~~~

Chuỗi liền **LUURDLDR** đưa đúng trạng thái đầu đến goal và dài 8 bước.

Dòng output minh họa:

~~~text
Iterative contours: steps=8, path=LUURDLDR, bounds=[4, 6, 8]
~~~

Dù phải duyệt lại các nhánh ở bound=6 và bound=8, thuật toán không giữ toàn bộ những trạng thái đã mở ở bound=4 trong bộ nhớ.

Đây chính là **đánh đổi giữa RAM và thời gian**: duyệt lặp nhiều hơn để không cần frontier rộng của A*.

## 7. Manhattan distance cho 8-puzzle

Biểu diễn board bằng chuỗi dài 9, ký tự '0' là ô trống. Goal là:

~~~text
Vi tri chi so 0-based:
0 1 2
3 4 5
6 7 8

Goal:
1 2 3
4 5 6
7 8 0
~~~

Mỗi quân số t trong 1..8 có vị trí đích **target=t−1**.

Nếu quân đang ở chỉ số i:

- Hàng hiện tại: i/3.
- Cột hiện tại: i%3.
- Hàng đích: (t−1)/3.
- Cột đích: (t−1)%3.

Khoảng cách quân t:

**|i/3−(t−1)/3| + |i%3−(t−1)%3|**, dùng chia nguyên ở các hàng/cột.

Heuristic của board:

**h(board)=Σ Manhattan(t)**, cộng trên t=1..8.

### Chứng minh admissible

Mỗi thao tác di chuyển ô trống chỉ dịch **một quân số đúng một ô**. Để mọi quân về vị trí đích, số bước thực tế không thể ít hơn tổng số bước cần dịch từng quân theo Manhattan. Vì thế:

**h(board)≤số bước tối ưu còn lại**.

### Chứng minh consistent

Một thao tác cost1 chỉ thay đổi vị trí một quân số một ô; Manhattan của quân ấy thay đổi đúng 1, các quân khác không đổi.

Vậy h(current)≤1+h(next). Điều này giúp f không giảm dọc đường.

### Tại sao không tính quân 0?

Mỗi thao tác đồng thời đổi vị trí 0 và một quân số. Nếu cộng cả Manhattan của 0, có thể đếm chồng cùng một thao tác và đánh giá quá cao số bước còn lại. Công thức chuẩn cho 8-puzzle **không tính ô trống**.

## 8. Cắt chu trình và lưu đường đi hiện tại

Các thao tác R,L và D,U là những cặp đối nghịch. Đi R rồi L khi hợp lệ thường quay lại đúng board ban đầu, mất thêm 2 bước mà không có ích.

IDA* có thể cắt:

- **Bước đi ngược ngay lập tức**: nếu vừa R thì không thử L; vừa D thì không thử U.
- **Bất kỳ trạng thái đã xuất hiện trên đường DFS hiện tại**: lưu bằng HashSet **onPath**.

Vì tất cả thao tác trong 8-puzzle có cost dương, một đường đi tối ưu không cần lặp trạng thái. Bỏ vòng lặp trở lại cùng board là an toàn.

### Phân biệt onPath với visited toàn cục

**onPath** chỉ chứa trạng thái từ gốc tới nút hiện tại. Khi một nhánh kết thúc, phải xóa state khỏi onPath để những nhánh khác có thể thử lại.

Một **visited global** giữ mọi state qua các contour rồi chặn chúng vô điều kiện là sai: contour mới cho phép những phần cây bị cắt trong contour trước; cùng state có thể được tới bằng một đường ngắn hơn.

Nếu muốn dùng bảng transposition để tiết kiệm thời gian, phải quản lý g tốt nhất, ngưỡng và điều kiện cắt nhánh một cách có chứng minh. Bản đơn giản chỉ dùng onPath, giữ đúng mục tiêu bộ nhớ thấp.

### Memory thực tế

Bản DFS lưu:

- Board hiện tại.
- Stack đệ quy theo độ sâu d.
- Chuỗi thao tác hiện tại.
- onPath tối đa O(d) trạng thái.
- Một ít mảng hướng và danh sách bound.

Vì board 8-puzzle có kích thước cố định, bộ nhớ tìm kiếm **O(d)** theo độ sâu, không phải O(số trạng thái đã từng mở).

## 9. Khi nào IDA* cho lời giải tối ưu?

Giả sử:

1. Không gian trạng thái hữu hạn hoặc có điều kiện kết thúc thích hợp.
2. Chi phí hành động **dương**, hoặc các vòng cost0 được xử lý an toàn.
3. Heuristic admissible và h(goal)=0.
4. DFS xét mọi hành động hợp lệ không bị pruning sai.
5. Bound được tăng từ h(start) theo **minimum f vượt ngưỡng**.
6. Việc loại chu trình không xóa mất một đường tối ưu.

Khi f(n)>bound, mọi lời giải qua n có cost ít nhất f(n)>bound; do đó cắt an toàn.

Gọi C* là chi phí tối ưu. Trên một đường tối ưu, tại mọi nút n, g(n)+h(n)≤C*. Vì vậy khi bound=C*, toàn bộ đường tối ưu được phép duyệt.

Với bound<C*, không thể có một đích chi phí ≤bound, vì h(goal)=0. Tăng các ngưỡng đúng thứ tự không nhảy qua C*; contour đầu tìm được đích sẽ cho lời giải tối ưu.

Trong 8-puzzle, mỗi bước cost1, Manhattan admissible/consistent và số trạng thái hữu hạn. Vì vậy code ví dụ trả **số bước tối thiểu** cho mọi board giải được.

### Những trường hợp không được khẳng định tương tự

Nếu có chi phí âm và chu trình âm, tối ưu có thể không hữu hạn. Nếu heuristic overestimate, ta có thể cắt nhầm đường tốt nhất. Với graph vô hạn hoặc hành động cost0 tạo vòng, cần phân tích tính kết thúc riêng.

**IDA* không thay thế Bellman–Ford** cho bài đường đi ngắn nhất có chu trình âm.

## 10. Complexity: thời gian có thể tốn, RAM tương đối nhỏ

Gọi b là hệ số phân nhánh hiệu dụng, d là độ sâu lời giải tối ưu với cost1.

Trong một contour, DFS có thể xét nhiều nút ở các độ sâu lên tới d hoặc các độ sâu do bound cho phép. Với branching cao, số nút có thể **tăng theo cấp số mũ**.

Tổng thời gian IDA* là:

**T = Σ N(boundᵢ)**,

trong đó N(boundᵢ) là số nút được xử lý ở contour thứ i.

Không nên tuyên bố IDA* có thời gian O(d), chỉ vì bộ nhớ là O(d). Số contour và việc **xét lại cùng các nhánh** có thể khiến thời gian rất lớn nếu heuristic yếu.

### Bộ nhớ

Một DFS không lưu global visited có bộ nhớ theo số trạng thái trên stack hiện tại: **O(d)** trạng thái, cộng chi phí lưu mỗi state và bảng heuristic cố định.

A* với open/closed có thể cần giữ một số lượng trạng thái rất lớn, trong tình huống xấu tăng theo cấp số mũ. Đó là lý do IDA* hấp dẫn khi **RAM ít**.

### Java và kích thước object

HashSet<String> tạo thêm đối tượng String và cấu trúc hash. O(d) không có nghĩa chính xác d byte. Với bài cực sâu, stack đệ quy có thể vượt giới hạn JVM. Demo 8-puzzle 3×3 phù hợp với recursion; trên bài lớn nên cân nhắc DFS stack tường minh.

### Khi nào A* thực tế nhanh hơn?

Nếu RAM đủ, A* thường tận dụng bestG để tránh mở lại nhiều trạng thái, có thể nhanh hơn IDA*. Bài toán có rất nhiều nhánh nhưng heuristic yếu thường làm IDA* phải duyệt lặp nhiều contour.

Không có thuật toán thắng mọi đầu vào: **cấu trúc state space, heuristic, RAM và mục tiêu** quyết định cách chọn.

## 11. Chọn heuristic mạnh hơn

Heuristic càng gần chi phí thật mà vẫn không overestimate thì càng có cơ hội cắt được nhiều nút.

### h=0

IDA* với h=0 gần IDDFS theo g/depth trên bài cost1. Bộ nhớ thấp nhưng không hướng được DFS về đích.

### Misplaced tiles

Đếm quân số 1..8 đang sai vị trí. Heuristic này admissible nhưng khá yếu: một quân cách vị trí đích 3 ô vẫn chỉ đóng góp 1.

### Manhattan

Tổng dịch chuyển tối thiểu theo hàng/cột của các quân. Admissible, consistent và rẻ để tính. Thường hiệu quả hơn misplaced tiles.

### Linear conflict và pattern database

Linear conflict xét xung đột vị trí tương đối của các quân trong cùng hàng/cột. Pattern database tiền xử lý khoảng cách cho các tập con quân để có heuristic mạnh hơn.

Cần chú ý:

- **max(h1,h2)** của hai heuristic admissible vẫn admissible.
- **h1+h2** không tự động admissible vì có thể đếm trùng chi phí.
- Các pattern database có thể cộng khi cách chia pattern/cost bảo đảm không đếm trùng.
- Heuristic lớn hơn có thể giảm số node duyệt nhưng **tốn thời gian tính** hoặc **tốn RAM cho bảng**.

Một pattern database quá lớn có thể làm giảm ưu thế tiết kiệm bộ nhớ của IDA*.

## 12. Kiểm tra board 8-puzzle có giải được không?

Không phải mọi hoán vị 0..8 trên bảng 3×3 đều có thể biến thành goal.

Với **chiều rộng lẻ 3**, bỏ ô trống 0 ra khỏi dãy, đếm số **nghịch thế**:

**inversions = số cặp i<j có tile[i]>tile[j], đều khác 0**.

Board solvable tới goal 123456780 khi và chỉ khi **inversions chẵn**.

Ví dụ:

~~~text
Goal:
1 2 3
4 5 6
7 8 0
Inversions = 0, solvable.

Bad board:
1 2 3
4 5 6
8 7 0
Inversions = 1, UNSOLVABLE.
~~~

Board thứ hai mã hóa **123456870**. Không nên chạy IDA* mãi để chứng minh vô nghiệm khi đã có một bất biến parity đơn giản.

**Cảnh báo:** trên 15-puzzle 4×4, parity còn phụ thuộc vị trí **hàng của ô trống tính từ dưới**. Không sử dụng nguyên quy tắc “inversions chẵn” của 3×3 cho mọi kích thước bảng.

### Input hợp lệ khác với input solvable

Một chuỗi có ký tự lặp, thiếu quân, độ dài khác 9 là **input không hợp lệ** và nên ném IllegalArgumentException. Một chuỗi đúng 9 quân nhưng parity lẻ là **trạng thái hợp lệ nhưng vô nghiệm**.

Hai trường hợp này không nên trả cùng một loại lỗi.

## 13. Java 17+ độc lập: IDA* giải 8-puzzle

Chương trình nhận board dưới dạng chuỗi 9 ký tự '0'..'8', mỗi quân xuất hiện đúng một lần. Blank là số 0, goal cố định **123456780**.

Nó sử dụng:

- Manhattan distance.
- Tìm kiếm DFS theo f-bound.
- Ngưỡng kế tiếp bằng min f vượt bound.
- Swap và swap ngược trên char[].
- Bỏ move ngược ngay và onPath HashSet.
- Chuỗi **R,D,L,U** biểu thị hướng **ô trống** di chuyển.
- In dãy bounds của từng lượt, giúp quan sát duyệt lặp.

**Lưu tên tệp: IdaStarEightPuzzleDemo.java**

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class IdaStarEightPuzzleDemo {

    static final char[] MOVES = {'R', 'D', 'L', 'U'};
    static final int[] DR = {0, 1, 0, -1};
    static final int[] DC = {1, 0, -1, 0};
    static final int FOUND = -1;

    record Answer(boolean solvable,
                  String moves,
                  List<Integer> bounds) {
        String describe() {
            if (!solvable) return "UNSOLVABLE";
            String path = moves.isEmpty() ? "(empty)" : moves;
            return "steps=" + moves.length()
                    + ", path=" + path
                    + ", bounds=" + bounds;
        }
    }

    static final class Solver {
        final char[] board;
        final int startBlank;
        final StringBuilder moves = new StringBuilder();
        final Set<String> onPath = new HashSet<>();

        Solver(String input) {
            if (input == null || input.length() != 9) {
                throw new IllegalArgumentException(
                        "Board needs exactly 9 characters");
            }

            board = input.toCharArray();
            boolean[] seen = new boolean[9];
            int blank = -1;

            for (int i = 0; i < board.length; i++) {
                char c = board[i];
                if (c < '0' || c > '8' || seen[c - '0']) {
                    throw new IllegalArgumentException(
                            "Every tile 0..8 must appear once");
                }
                seen[c - '0'] = true;
                if (c == '0') blank = i;
            }

            startBlank = blank;
        }

        boolean solvable() {
            int inversions = 0;
            for (int i = 0; i < board.length; i++) {
                if (board[i] == '0') continue;
                for (int j = i + 1; j < board.length; j++) {
                    if (board[j] != '0' && board[i] > board[j]) {
                        inversions++;
                    }
                }
            }
            return (inversions & 1) == 0;
        }

        int manhattan() {
            int sum = 0;
            for (int i = 0; i < board.length; i++) {
                int tile = board[i] - '0';
                if (tile == 0) continue;

                int target = tile - 1;
                sum += Math.abs(i / 3 - target / 3);
                sum += Math.abs(i % 3 - target % 3);
            }
            return sum;
        }

        void swap(int i, int j) {
            char temp = board[i];
            board[i] = board[j];
            board[j] = temp;
        }

        int search(int blank, int g, int bound, int prev) {
            int h = manhattan();
            int f = g + h;
            if (f > bound) return f;
            if (h == 0) return FOUND;

            int nextBound = Integer.MAX_VALUE;
            int row = blank / 3;
            int col = blank % 3;

            for (int k = 0; k < 4; k++) {
                // R and L, D and U are inverse directions.
                if (prev != -1 && k == (prev + 2) % 4) {
                    continue;
                }

                int nr = row + DR[k];
                int nc = col + DC[k];
                if (nr < 0 || nr >= 3 || nc < 0 || nc >= 3) {
                    continue;
                }

                int nextBlank = nr * 3 + nc;
                swap(blank, nextBlank);
                String state = new String(board);

                if (onPath.add(state)) {
                    moves.append(MOVES[k]);
                    int result = search(
                            nextBlank, g + 1, bound, k);

                    if (result == FOUND) {
                        onPath.remove(state);
                        swap(blank, nextBlank);
                        return FOUND;
                    }

                    moves.setLength(moves.length() - 1);
                    onPath.remove(state);
                    nextBound = Math.min(nextBound, result);
                }

                swap(blank, nextBlank);
            }
            return nextBound;
        }

        Answer solve() {
            if (!solvable()) {
                return new Answer(false, "", List.of());
            }

            int bound = manhattan();
            List<Integer> bounds = new ArrayList<>();
            onPath.add(new String(board));

            while (true) {
                bounds.add(bound);
                int result = search(startBlank, 0, bound, -1);

                if (result == FOUND) {
                    return new Answer(true, moves.toString(),
                            List.copyOf(bounds));
                }
                if (result == Integer.MAX_VALUE) {
                    throw new IllegalStateException(
                            "No further contour for solvable board");
                }

                bound = result;
            }
        }
    }

    static void show(String label, String board) {
        Answer a = new Solver(board).solve();
        System.out.println(label + ": " + a.describe());
    }

    public static void main(String[] args) {
        show("Solved", "123456780");
        show("One step", "123456708");
        show("Two steps", "123456078");
        show("Four steps", "123468750");
        show("Six steps", "123568470");
        show("Iterative contours", "162453780");
        show("Another four", "123485760");
        show("Parity impossible", "123456870");
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 IdaStarEightPuzzleDemo.java
java IdaStarEightPuzzleDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
Solved: steps=0, path=(empty), bounds=[0]
One step: steps=1, path=R, bounds=[1]
Two steps: steps=2, path=RR, bounds=[2]
Four steps: steps=4, path=ULDR, bounds=[4]
Six steps: steps=6, path=ULLDRR, bounds=[6]
Iterative contours: steps=8, path=LUURDLDR, bounds=[4, 6, 8]
Another four: steps=4, path=LURD, bounds=[4]
Parity impossible: UNSOLVABLE
~~~

### Từng phần code làm gì?

**Validation:** Kiểm tra độ dài và mỗi quân 0..8 xuất hiện đúng một lần. Tránh việc một board sai dữ liệu bị nhận là trạng thái vô nghiệm bình thường.

**Manhattan:** Với tile=t, target=t−1; bỏ qua quân 0. Manhattan bằng 0 khi và chỉ khi board đúng goal.

**search:** Nếu f vượt bound, trả f. Nếu h=0, trả FOUND. Nếu không, duyệt tối đa bốn thao tác trượt hợp lệ, rồi tìm minimum f bị cắt.

**Swap và phục hồi:** Từ board hiện tại, swap blank với ô kề để mở rộng. Sau nhánh thất bại, swap ngược. Ngay cả khi tìm thấy lời giải, code cũng swap ngược trên quá trình trả về nhưng **giữ nguyên chuỗi moves thắng**.

**onPath:** Nếu một successor đã nằm trên đường hiện tại, không gọi DFS cho nó. Khi quay lui phải remove state của nhánh vừa đi, nếu không các contour hoặc nhánh khác sẽ bị cấm sai.

**Không xóa moves khi FOUND:** Các ký tự đường thắng phải tồn tại trong StringBuilder sau khi các lời gọi quay lui kết thúc.

**Threshold sequence:** solve bắt đầu bound=h(start), gọi search, thêm ngưỡng mới từ min f bị cắt nếu chưa thấy goal. Danh sách bounds được in chỉ để minh họa.

### Hạn chế của chương trình

- Chỉ áp dụng cho **8-puzzle 3×3**, không tự mở rộng logic parity sang 15-puzzle.
- Mỗi thao tác cost1.
- DFS dùng recursion; với những bài có độ sâu rất lớn cần xem xét stack JVM.
- onPath lưu String nên có overhead; biểu diễn state bằng mã số bit/long có thể nhanh hơn khi tối ưu.
- Chương trình là demo thuật toán, không cung cấp giao diện stdin hoặc visualizer cho mọi input.

## 14. Kiểm thử độc lập bằng BFS

Không nên chỉ chạy các ví dụ rồi kết luận IDA* tối ưu. Với 8-puzzle nhỏ, một **BFS từ goal** có thể làm oracle độc lập.

BFS xây khoảng cách theo số bước:

~~~text
queue = [GOAL]
dist[GOAL] = 0

while queue not empty:
    state = pop_front(queue)
    for each legal nextState:
        if nextState not in dist:
            dist[nextState] = dist[state] + 1
            push_back(queue, nextState)
~~~

Vì mọi hành động trượt có cost1 và các thao tác có thể đảo ngược, BFS từ goal cho **độ dài lời giải tối ưu** của các state đạt được.

Có thể chỉ BFS tới độ sâu 14 để tạo **nhiều nghìn trạng thái** đủ kiểm chứng mà không cần liệt kê toàn bộ 9! cấu hình.

Với mỗi state thử:

1. Chạy IDA* và kiểm tra **solvable=true**.
2. So **moves.length = dist_BFS(state)**.
3. Áp dụng từng chữ R,D,L,U theo luật di chuyển ô trống, xác minh không có bước ra ngoài bảng.
4. Xác minh board cuối **đúng goal**.
5. Xác minh ngưỡng đầu bằng Manhattan start.
6. Xác minh các ngưỡng **tăng nghiêm ngặt** và ngưỡng cuối bằng chi phí tối ưu.
7. Với board parity lẻ, phải trả **UNSOLVABLE**.

### Vì sao BFS là oracle tốt?

BFS không dùng heuristic, không dùng f-bound và không cần tính next threshold. Nếu code IDA* có lỗi về swap, path, ngưỡng hoặc cắt nhánh, BFS có khả năng phát hiện qua độ dài lời giải hoặc trạng thái cuối.

### Scramble không phải đáp án tối ưu

Nếu từ goal thực hiện 20 bước trượt ngẫu nhiên, board tạo ra có thể chỉ cách goal 4 bước do nhiều thao tác quay lại. Không được lấy số bước scramble làm ground truth của đường ngắn nhất. Phải dùng BFS hoặc một thuật toán tham chiếu đúng.

### Kiểm tra trạng thái chưa gặp trong BFS giới hạn

Nếu một state không nằm trong bảng BFS tới độ sâu 14, chỉ có thể kết luận **BFS giới hạn chưa biết khoảng cách**, không được coi đó là UNSOLVABLE. Cần BFS sâu hơn, thử oracle khác hoặc dùng invariant parity để chứng minh không giải được.

## 15. Những tối ưu có thể thêm

### Move ordering

Thử trước successor có h nhỏ hơn có thể giúp tìm goal sớm khi contour đủ lớn, nhất là trong bài có nhiều hướng đi. Nhưng việc tính h và sort các successor cũng có chi phí, nên cần benchmark.

**Thứ tự duyệt không thay đổi tập lời giải hợp lệ** nếu vẫn xét đầy đủ các hành động được phép và pruning vẫn an toàn. Đường thắng có thể khác khi có nhiều lời giải tối ưu cùng độ dài.

### Incremental Manhattan

Thay vì tính Manhattan từ đầu cho mọi trạng thái, cập nhật delta h khi chỉ một quân số trượt một ô:

**h(next)=h(current)−oldDistance(tile)+newDistance(tile)**.

Với 8-puzzle chỉ có 9 ô nên lợi ích nhỏ; ở puzzle lớn, cách cập nhật tăng/giảm có thể tiết kiệm nhiều phép toán.

### Pattern database

Tiền xử lý khoảng cách tối ưu trên các nhóm quân số; kết hợp có chứng minh để tạo heuristic admissible mạnh hơn. Điều này có thể giảm số node duyệt đáng kể nhưng tốn RAM cho bảng.

### Transposition table có giới hạn

Một cache nhỏ có thể ghi các state đã xử lý theo g và thông tin bound, giúp giảm trùng lặp trong contour. Tuy nhiên, cần quy tắc đúng về **đường đi, ngưỡng và trạng thái**. Không được lưu visited vĩnh viễn rồi cấm mọi lần mở lại.

### Tránh recursion quá sâu

Dùng stack tường minh với trường state/blank/g/next-action và undo information khi lời giải có thể rất sâu. Stack tường minh vẫn có O(d) bộ nhớ nhưng tránh lỗi giới hạn recursion của Java.

## 16. Mở rộng sang chi phí không đồng nhất

IDA* tổng quát không chỉ áp dụng khi mỗi bước cost1.

Nếu cost giữa n và n' là c(n,n')≥0:

**g(n')=g(n)+c(n,n')**.

Heuristic h phải là cận dưới của **tổng cost còn lại**, không phải mặc định số hành động.

Ví dụ một robot di chuyển qua ô thường cost1 và ô khó cost4. Manhattan nhân chi phí di chuyển **thấp nhất hợp lệ** có thể là một heuristic admissible nếu mọi dịch chuyển cần trả ít nhất cost1. Nhưng các thao tác rẽ, trượt xa hoặc teleporter có thể làm công thức ấy không còn đúng; phải xét mô hình thật.

Nếu cost là số thực, nextBound có thể mang giá trị không nguyên. Không dùng bound+1 tùy tiện.

### Zero-cost cycle và negative-cost cycle

Vòng cost0 không tăng g, nên có thể gây lặp vô hạn nếu không có kiểm soát trạng thái. Với graph hữu hạn, onPath giúp bỏ những chu trình trên đường hiện tại, nhưng điều kiện completeness vẫn cần phân tích rõ.

Chu trình âm có thể làm tổng cost giảm không có cận dưới; IDA* tiêu chuẩn với giả thiết cost không âm không phù hợp. Nếu bài có negative cycle ảnh hưởng tới goal, đôi khi không tồn tại lời giải tối ưu hữu hạn.

## 17. Khi nào nên chọn IDA* thay vì A*?

**Nên cân nhắc IDA*** nếu:

- RAM thiếu để giữ open/closed.
- Không gian trạng thái có successor sinh nhanh.
- Heuristic admissible và khá mạnh.
- Độ sâu lời giải không vượt mức stack/bộ nhớ hiện tại.
- Chấp nhận mở lại trạng thái qua nhiều contour.

**Nên cân nhắc A*** nếu:

- Có đủ RAM và ưu tiên thời gian.
- Nhiều đường tới cùng một state, lưu bestG giúp giảm trùng lặp.
- Heuristic hiệu quả, frontier vẫn ở mức quản lý được.

**Nên cân nhắc BFS** khi trạng thái nhỏ và mọi hành động cost1. **Dijkstra** phù hợp graph cost không âm khi không có heuristic phù hợp. **IDDFS** phù hợp khi cần tối ưu số bước nhưng không có heuristic hữu ích.

### So sánh độ phức tạp đúng cách

Bậc bộ nhớ O(d) của IDA* nói về **đường DFS và dữ liệu phụ**. Thời gian phụ thuộc tổng số nút đã xét qua tất cả contour. A* có thể cần bộ nhớ lớn tỉ lệ số state trong open/closed.

Không nên viết một bảng “IDA* luôn O(b^d) thời gian, A* luôn O(b^d) bộ nhớ” mà không nói rõ assumptions; chi phí thực phụ thuộc branching, heuristic, duplicate states, cách lưu dữ liệu và điều kiện dừng.

## 18. Những lỗi phổ biến

1. **Cắt theo g mà không xét h** nhưng vẫn gọi đó là IDA*.
2. **Không lặp lại DFS** sau khi contour đầu không có lời giải.
3. **Tăng bound tùy ý**, bỏ qua giá trị min f đã vượt.
4. **Lấy max f thay min f** làm ngưỡng mới.
5. **Không trả giá trị f khi bị cắt**, khiến không xác định được contour sau.
6. **Dùng heuristic overestimate** nhưng vẫn khẳng định tối ưu.
7. **Tính Manhattan của quân 0**, đếm chồng thao tác.
8. **Dùng target index bằng tile thay vì tile−1** trong goal 123456780.
9. **Không kiểm tra move ra ngoài biên**, tạo trạng thái không hợp lệ.
10. **Không phục hồi board sau DFS thất bại**, làm nhánh tiếp theo bắt đầu sai trạng thái.
11. **Không xóa ký tự moves khi backtrack**, dẫn tới chuỗi thắng thừa bước.
12. **Xóa luôn moves của đường thắng**, làm mất lời giải.
13. **Không xóa onPath key sau backtrack**, cấm nhầm nhánh khác.
14. **Giữ visited toàn cục qua mọi contour**, ngăn duyệt lại vùng cần thiết.
15. **Không kiểm tra parity 8-puzzle**, duyệt lâu dù board vô nghiệm.
16. **Dùng parity 3×3 cho 4×4**, phân loại solvability sai.
17. **Đếm số bước scramble thành đáp án tối ưu**, dù scramble có thể đi vòng.
18. **Chỉ kiểm tra moves dẫn tới goal mà không so độ dài tối ưu**.
19. **Khẳng định IDA* luôn nhanh hơn A*** vì ít RAM.
20. **Không tính overhead của HashSet/String** khi đánh giá Java memory.
21. **Dùng recursive DFS rất sâu mà không quan tâm stack**.
22. **Cộng hai heuristic admissible không chứng minh**, có thể overestimate.
23. **Dùng heuristic số bước cho bài tối ưu cost khác nhau**, khiến đơn vị g/h không khớp.
24. **Áp dụng nguyên IDA* cho graph có chu trình âm**, có thể không có optimum.
25. **Không phân biệt onPath và global closed set**, làm pruning sai.
26. **Không xét trường hợp start đã là goal**, bỏ lời giải độ dài 0.
27. **Coi board hợp lệ nhưng parity lẻ như input sai cú pháp**, nhầm hai tình huống.
28. **Cho rằng mọi trạng thái không được BFS độ sâu 14 thăm là vô nghiệm**, nhầm chưa khám phá với không đạt được.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** IDA* sử dụng f nào?  
**Đáp án:** f(n)=g(n)+h(n), với g là cost đã đi và h là cận dưới chi phí còn lại.

**Câu 2.** IDA* khác IDDFS ở giới hạn nào?  
**Đáp án:** IDDFS theo độ sâu/g, còn IDA* theo ngưỡng f=g+h.

**Câu 3.** Trong một contour bound=10, node có f=12 xử lý thế nào?  
**Đáp án:** Cắt nhánh và trả 12 làm ứng viên ngưỡng mới.

**Câu 4.** Các giá trị vượt bound là 14,11,17. Ngưỡng sau?  
**Đáp án:** 11.

**Câu 5.** Heuristic admissible là gì?  
**Đáp án:** Không overestimate chi phí tối ưu còn lại.

**Câu 6.** Vì sao Manhattan 8-puzzle admissible?  
**Đáp án:** Mỗi bước di chuyển đúng một quân số một ô; tổng số dịch chuyển không thể nhỏ hơn tổng Manhattan của các quân.

**Câu 7.** IDA* và A* đánh đổi bộ nhớ ra sao?  
**Đáp án:** IDA* giữ chủ yếu đường DFS; A* thường giữ frontier/bestG lớn hơn nhưng giảm duyệt lặp.

**Câu 8.** OnPath được xóa vào lúc nào?  
**Đáp án:** Khi quay lui từ nhánh thất bại; nhờ đó các nhánh khác có thể gặp state ấy hợp lệ.

**Câu 9.** Trạng thái 162453780 có h ban đầu và lời giải dài bao nhiêu?  
**Đáp án:** h=4, lời giải tối ưu dài 8 bước, các bound 4,6,8.

**Câu 10.** Bỏ h và đặt h=0 thì IDA* gần thuật toán nào?  
**Đáp án:** IDDFS khi mỗi bước cost1.

**Câu 11.** Board 123456870 có giải được không?  
**Đáp án:** Không, số nghịch thế lẻ trên puzzle 3×3 goal cố định.

**Câu 12.** Có được cộng tùy ý hai heuristic admissible không?  
**Đáp án:** Không, có thể đếm trùng; max của hai heuristic admissible vẫn admissible.

**Câu 13.** Vì sao BFS là oracle tốt trên 8-puzzle?  
**Đáp án:** Mọi bước cost1; BFS cho số bước tối ưu độc lập h và contour.

**Câu 14.** IDA* có thể xử lý các cost không bằng nhau không?  
**Đáp án:** Có nếu g cộng đúng cost, heuristic phù hợp và next bound theo f, không đơn giản bound+1.

**Câu 15.** Khi nào không nên dùng recursion trong IDA*?  
**Đáp án:** Khi đường đi có thể rất sâu, vượt khả năng stack của JVM.

## 20. Tổng kết

**IDA* = DFS lặp theo ngưỡng f=g+h, không phải DFS theo một depth limit duy nhất.**

Một triển khai đúng nên:

1. Xác định trạng thái, goal, thao tác và cost.
2. Chọn heuristic admissible, ưu tiên consistent.
3. Khởi tạo bound=h(start) nếu g(start)=0.
4. DFS và **cắt khi f>bound**.
5. Tìm **min f vượt bound** để làm ngưỡng kế tiếp.
6. Hoàn nguyên board/path chính xác khi backtrack.
7. Chặn chu trình trên đường hiện tại, tránh visited global sai.
8. Trả lời giải đầu tiên khi contour đủ điều kiện tối ưu.
9. Với 8-puzzle, dùng Manhattan không tính blank và parity để phát hiện vô nghiệm.
10. QA bằng BFS độc lập, kiểm tra cả **độ dài tối ưu và chuỗi thao tác**.
11. Chọn IDA* khi **RAM quan trọng hơn việc duyệt lặp**; so với A* nếu RAM đủ.

**Thông điệp quan trọng:** IDA* tiết kiệm bộ nhớ bằng cách *không giữ frontier toàn cục*, nhưng phải *quay lại xét nhiều trạng thái* ở các ngưỡng f tăng dần. Heuristic tốt quyết định mức độ hiệu quả của sự đánh đổi đó.
