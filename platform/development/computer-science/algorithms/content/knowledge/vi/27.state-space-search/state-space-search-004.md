# Tìm kiếm sâu dần (iterative deepening)

## Mục tiêu

**Tìm kiếm sâu dần** (*iterative deepening depth-first search*, **IDDFS/IDS**) thuộc nhóm **Tìm kiếm trạng thái**. Nó chạy **DFS có giới hạn độ sâu** (*depth-limited search, DLS*) nhiều lần với giới hạn lần lượt **0, 1, 2, 3, ...**, mỗi lần bắt đầu lại từ trạng thái đầu. Vòng đầu tìm thấy đích cho ta lời giải **ít bước nhất**, với giả thiết mọi thao tác có cùng chi phí nếu muốn kết luận tối ưu về tổng chi phí.

Ý tưởng quan trọng: **BFS** tìm lời giải ít cạnh nhất nhưng có thể tốn rất nhiều RAM để chứa frontier; **DFS** dùng ít RAM nhưng có thể đi quá sâu vào một nhánh và trả lời giải dài. **IDDFS** duyệt các độ sâu theo thứ tự tăng như BFS nhưng chỉ giữ **đường hiện tại như DFS**.

Sau bài này, bạn sẽ biết:

- Xác định state, start, goal, successor, depth và hệ số phân nhánh.
- Viết DLS, xử lý chính xác goal ở **đúng giới hạn** và xây path.
- Dùng vòng lặp giới hạn tăng dần để dựng IDDFS.
- Hiểu vì sao visited toàn cục có thể **làm sai** DLS trên đồ thị có nhiều đường đến cùng trạng thái.
- Chứng minh tính đầy đủ, tính tối ưu **theo số cạnh** và giới hạn khi có trọng số.
- Tính thời gian `O(b^d)` khi b>1, bộ nhớ phụ `O(d)`, ngoại lệ b=1.
- Phân biệt IDDFS với IDA*, BFS, DFS và uniform-cost search.
- Chạy mã **Java 17+** có thống kê từng lượt, truy xuất path và kiểm tra ngoại lệ.
- Kiểm thử graph có chu trình, đích ở đúng giới hạn, graph vô nghiệm trong cap và start==goal.

---

## 1. Mô hình tìm kiếm trạng thái

Bài toán gồm bốn yếu tố:

1. **Tập trạng thái:** ví dụ ô trên lưới, cấu hình robot, bàn cờ, cách xếp ô.
2. **Trạng thái bắt đầu s:** nơi tìm kiếm khởi hành.
3. **Successors(v):** những trạng thái có thể tới từ v bằng một thao tác.
4. **Goal predicate:** điều kiện xác định trạng thái đích.

Một đường:

```text
S -> A -> C -> G
```

có **ba cạnh**, tức độ sâu G trên đường là **3**. Quy ước `depth(start)=0`. Không được đếm số trạng thái trên đường thành số bước; bốn trạng thái ứng với ba bước chuyển.

### Cây tìm kiếm và đồ thị trạng thái khác nhau

Trên đồ thị, một trạng thái có thể đạt qua **nhiều đường khác nhau** và graph có thể chứa chu trình. Ví dụ S→A→X và S→X đều đến X, nhưng một đường dài hai cạnh, đường kia chỉ một cạnh.

Khi chạy tìm kiếm trên một graph, hai lần tới cùng state thông qua hai **đường khác nhau** tương ứng với hai nút khác nhau trong **cây đường đi**. Việc gộp chúng có thể hữu ích, nhưng phải dựa trên điều kiện thuật toán; DLS có **ngân sách độ sâu** nên không thể chỉ biết rằng một state “đã từng thấy”.

### Độ sâu khác chi phí

Nếu một bước có trọng số, độ sâu vẫn chỉ đếm số thao tác. Đường một cạnh cost 20 nông hơn đường hai cạnh cost 2. IDDFS cơ bản tối ưu **số cạnh**, không tối ưu tổng trọng số khi chi phí mỗi cạnh khác nhau.

### Hệ số phân nhánh

Giả sử mỗi nút có tối đa b successor; một cây đầy đủ có thể có:

\[
1,b,b^2,\ldots,b^d
\]

nút ở các độ sâu 0..d. Với b>1, tầng sâu nhất chiếm phần lớn số nút. Điều này giải thích vì sao duyệt lại tầng nông trong IDDFS thường ít tốn hơn vẻ ngoài.

---

## 2. DFS, BFS và động cơ của IDDFS

| Thuật toán | Ưu tiên | Tìm lời giải ít cạnh nhất? | Bộ nhớ phụ điển hình |
| --- | --- | --- | --- |
| DFS | Đi sâu một nhánh trước | Không | Theo độ sâu stack |
| BFS | Duyệt tầng 0,1,2,... | Có nếu các bước đồng chi phí | Có thể `O(b^d)` |
| **IDDFS** | Lặp DLS ở 0,1,2,... | Có nếu duyệt đầy đủ | **O(d)** cho stack/path |

**DFS thường:** Nếu một nhánh rất dài hoặc vô hạn, DFS có thể mắc ở nhánh ấy và bỏ lỡ một goal nông ở nhánh khác. Trên graph có chu trình, nếu không kiểm soát lặp, DFS có thể quay lại cùng trạng thái mãi.

**BFS:** Xét toàn bộ depth 0 trước depth 1, rồi 2, nên tìm đường ít bước nhất khi mọi bước có chi phí bằng nhau. Tuy nhiên hàng đợi frontier có thể chứa gần như toàn bộ tầng sâu d với kích thước lên tới b^d.

**IDDFS:** Giữ thứ tự ưu tiên độ sâu nhỏ của BFS bằng **các lượt DFS riêng biệt**. Đổi lại, nó không giữ toàn bộ frontier và sẵn sàng xét lại các tầng nông khi giới hạn tăng.

Nếu chỉ cần một đường bất kỳ và bộ nhớ ít, DFS có thể đơn giản hơn. Nếu graph nhỏ, có thể lưu frontier, BFS thường tránh được các lần thăm lặp của IDDFS.

---

## 3. DFS giới hạn độ sâu — DLS

**DLS** được gọi với tham số remaining: số cạnh tối đa còn được phép đi từ state hiện tại.

- `DLS(s,0)` chỉ kiểm tra s.
- `DLS(s,1)` có thể kiểm tra những state cách s một cạnh.
- `DLS(s,2)` có thể đi tối đa hai cạnh.

### Thứ tự hai điều kiện biên

```text
if isGoal(state):
    return true

if remaining == 0:
    return false
```

**Goal phải được kiểm tra trước cutoff.** Nếu goal nằm đúng depth limit, remaining bằng 0 tại goal; kiểm tra cutoff trước sẽ **bỏ sót lời giải hợp lệ**.

### Giả mã DLS

```text
DLS(v, goal, remaining, path, onPath):
    đếm một lượt truy cập v

    nếu v là goal:
        return true

    nếu remaining == 0:
        return false

    for next trong successors(v):
        nếu next thuộc onPath:
            continue

        thêm next vào path và onPath

        nếu DLS(next, goal, remaining-1, path, onPath):
            return true

        xóa next khỏi path và onPath

    return false
```

Tập `onPath` chỉ giữ những state **trên nhánh hiện tại**. Khi một nhánh thất bại và quay lui, phải **xóa next khỏi cả path lẫn onPath**. Nhờ vậy cùng state có thể được xét lại trên một đường khác với độ sâu khác.

Nếu một lời gọi con thành công, các lời gọi cha trả true mà **không backtrack đường thành công**; path cuối cùng giữ đúng dãy state đến goal.

### DLS false có ý nghĩa gì?

DLS không tìm thấy đích ở limit L chỉ nói rằng không có lời giải trong những đường hợp lệ **dài không quá L** đã được duyệt đầy đủ. Không thể suy ra đích không tồn tại ở độ sâu lớn hơn.

Một phiên bản DLS nâng cao có thể phân biệt **FOUND / CUTOFF / FAILURE**; trong bài này chúng ta dùng `maxDepth` để đặt phạm vi tìm kiếm rõ ràng.

---

## 4. IDDFS: tăng giới hạn từng lượt

```text
IDDFS(start, goal, maxDepth):
    for limit = 0..maxDepth:
        path = [start]
        onPath = {start}
        reset thông tin duyệt của vòng

        nếu DLS(start,goal,limit,path,onPath):
            return path, limit, found=true

    return found=false trong giới hạn maxDepth
```

IDDFS **phải thử từ limit=0**, vì start có thể đã là goal. Mỗi lần tăng giới hạn, cần **bắt đầu DFS lại tại start**; không tiếp tục từ nút sâu nhất của lượt trước.

Những thứ nên tạo lại cho mỗi lượt: path, onPath, các frame DFS và counter visits theo lượt. Graph và goal không thay đổi. Nếu muốn đếm tổng lượt thăm, có thể cộng visits của mọi vòng.

### Khi nào dừng?

- Thành công khi tìm ra goal.
- Thất bại trong phạm vi maxDepth khi đã thử tới giới hạn đó.

Với một không gian trạng thái **vô hạn** mà goal không tồn tại, nếu không có giới hạn tối đa hoặc ngân sách tài nguyên, IDDFS có thể chạy mãi. Do đó một API thực tế cần `maxDepth` hoặc điều kiện dừng tương đương.

Trên **graph hữu hạn có V state**, mọi đích reachable đều có một **đường đơn** dài tối đa V−1. Nếu đã khám phá đầy đủ các đường đơn tới giới hạn V−1 và không có goal, có thể kết luận không reachable. Điều này không đúng nguyên xi khi không gian trạng thái vô hạn hoặc khóa state chưa mã hóa đủ lịch sử.

---

## 5. Mô phỏng bốn lượt IDDFS

Dùng đồ thị có hướng sau, duyệt successor theo đúng thứ tự liệt kê:

```text
S -> A, B
A -> C, S
B -> D, E
C -> F
D -> F
E -> G
F -> A
G -> (không có successor)
```

Start=S, goal=G. Các cạnh A→S và F→A tạo chu trình. Trạng thái F có thể được đạt từ C hoặc D.

Một đường tới goal là:

```text
S -> B -> E -> G
```

gồm **3 cạnh**.

### Limit 0

```text
Visited: S
Số lần gọi DLS: 1
Goal: chưa tìm thấy
```

### Limit 1

```text
Visited: S, A, B
Số lần gọi DLS: 3
Goal: chưa tìm thấy
```

### Limit 2

```text
Visited: S, A, C, B, D, E
Số lần gọi DLS: 6
Goal: chưa tìm thấy
```

Ở nhánh S→B→E, E có độ sâu 2 nên remaining=0; không được đi E→G.

### Limit 3

```text
Visited: S, A, C, F, B, D, F, E, G
Số lần gọi DLS: 9
Goal: tìm thấy
```

F xuất hiện hai lần vì DLS tới cùng state qua hai đường khác nhau, một lần từ C và một lần từ D. Tập onPath chỉ loại lặp **trong cùng một đường** nên điều này hợp lệ.

Kết quả:

| Limit | Visits | Found |
| ---: | ---: | --- |
| 0 | 1 | false |
| 1 | 3 | false |
| 2 | 6 | false |
| 3 | 9 | true |

Tổng số lời gọi DLS:

\[
1+3+6+9=\boxed{19}.
\]

Path cuối là `[S,B,E,G]`, depth=3. Graph có 8 state phân biệt nhưng tổng lượt visits là 19 do xét lại ở nhiều limit và nhiều nhánh.

Nếu `maxDepth=2`, IDDFS không tìm được goal và có tổng 1+3+6=10 visits; kết luận đúng là “**không tìm thấy ở độ sâu ≤2**”.

---

## 6. Phản ví dụ visited toàn cục gây sai

Graph khác:

```text
S -> A, X
A -> X
X -> G
```

Có đường ngắn nhất `S→X→G` với depth 2.

Giả sử DLS limit=2, thử A trước X và dùng một `globalVisited` cho **toàn bộ lượt DFS**.

1. S→A: A ở depth 1.
2. A→X: X ở depth 2, bị đánh dấu visited.
3. X không được đi tiếp tới G vì đã hết ngân sách.
4. Quay lại S, thử S→X: X ở depth 1.
5. GlobalVisited thấy X “đã thăm” nên bỏ nhánh này.
6. DLS trả false dù **có đường S→X→G dài hai cạnh**.

Sai ở chỗ **cùng X nhưng ngân sách còn lại khác nhau**. Đường tới X ở depth 2 còn 0 bước, đường tới X ở depth 1 còn 1 bước.

### Giải pháp an toàn cơ bản

Chỉ sử dụng onPath, tức một state bị bỏ qua **khi nó đã xuất hiện trên đường hiện tại**. Sau khi nhánh S→A→X thất bại, xóa X khỏi onPath; S→X được phép xét lại và dẫn tới G.

Thống kê đúng cho graph này khi limit 0,1,2:

```text
1, 3, 5
Path: [S, X, G]
```

**Không tái sử dụng visited giữa các lượt limit**: ở vòng mới một state từng bị cắt vì depth limit cũ phải được phép mở rộng thêm.

### Vì sao onPath không bỏ lời giải ngắn nhất?

Một đường tới goal lặp lại cùng state tạo thành **chu trình**. Nếu state mã hóa đủ thông tin cần thiết và các chuyển trạng thái phụ thuộc vào state hiện tại, loại chu trình tạo một đường **không dài hơn** tới goal. Vì vậy luôn có thể chọn lời giải ít cạnh nhất là **đường đơn**, không lặp state trong một đường.

Nhưng nếu cùng tọa độ mà có bộ chìa khóa khác nhau, state phải là `(x,y,keyMask)` chứ không chỉ `(x,y)`. Nếu khóa state thiếu thông tin, chống lặp có thể bỏ một trạng thái thực chất khác.

---

## 7. Chứng minh tính đầy đủ và tối ưu

### 7.1. Tính đầy đủ

Giả sử:

- Hệ số phân nhánh hữu hạn.
- Có một lời giải ở độ sâu hữu hạn d.
- DLS xét hết successor hợp lệ tới giới hạn và không prune sai.
- IDDFS được chạy tới ít nhất d.
- Tài nguyên thực tế cho phép hoàn thành các vòng.

Khi limit<d, không thể có lời giải theo định nghĩa d là độ sâu nhỏ nhất. Ở limit=d, DLS duyệt đầy đủ các đường đơn dài tối đa d; một đường lời giải nông nhất là đường đơn nên không bị onPath loại. Goal được kiểm tra kể cả khi remaining=0, nên DLS tìm thấy lời giải.

**Kết luận:** dưới các điều kiện này, IDDFS là **complete**.

### 7.2. Tối ưu theo số bước

Giả sử IDDFS thành công đầu tiên ở limit=d. Nếu có đường tới goal dài d'<d, DLS ở vòng d' đã phải nhận goal, mâu thuẫn. Vậy d là **số cạnh nhỏ nhất** của một lời giải.

Không suy ra điều này tối ưu chi phí khi các cạnh có trọng số khác nhau. Ví dụ:

```text
S -> G    cost 20
S -> A    cost 1
A -> G    cost 1
```

IDDFS trả đường một cạnh S→G, cost 20; đường hai cạnh S→A→G có cost 2 mới rẻ nhất.

Khi mọi thao tác có **cùng một chi phí dương**, tối ưu số bước cũng tối ưu tổng chi phí.

### 7.3. Bất biến của DLS

Khi vào DLS(state,remaining), path là một đường hợp lệ từ start tới state; onPath gồm đúng các state trên path, và:

\[
remaining = limit - (path.size()-1).
\]

Đi thêm một cạnh làm path dài thêm một, remaining giảm một. Khi quay lui, cả path và onPath được phục hồi. Vì vậy DLS không vượt limit, không tạo chu trình trên path, và path trả về khi thành công luôn hợp lệ.

---

## 8. Độ phức tạp thời gian

Gọi b là hệ số phân nhánh, d là độ sâu lời giải đầu tiên.

Một nút ở depth i có thể được thăm ở mọi lượt limit từ i đến d, tức nhiều nhất **d−i+1 lượt**. Nếu cây tìm kiếm đầy đủ có b nhánh:

\[
T(d)\le\sum_{i=0}^{d}(d-i+1)b^i.
\]

Với `b>1` cố định, các tầng sâu chiếm phần lớn công việc:

\[
\boxed{T_{\mathrm{IDDFS}}=O(b^d).}
\]

### Ví dụ b=3, d=4

Các tầng chứa 1,3,9,27,81 nút.

BFS nếu duyệt toàn bộ các mức tới 4 sẽ thăm:

\[
1+3+9+27+81=121.
\]

IDDFS nếu mỗi lượt quét hết trong mức giới hạn:

\[
5(1)+4(3)+3(9)+2(27)+81
=179.
\]

IDDFS thăm nhiều hơn BFS ở ví dụ này (179 so với 121), nhưng tổng vẫn cùng bậc với tầng cuối 81; đổi lại không phải giữ toàn bộ frontier.

### Ngoại lệ b=1

Nếu chỉ có một đường duy nhất và goal ở depth d, IDDFS thăm:

\[
1+2+\cdots+(d+1)
=\frac{(d+1)(d+2)}2
=O(d^2).
\]

Không được thay b=1 vào `O(b^d)` để nói thời gian O(1). Trên cây gần như chỉ một nhánh sâu, việc duyệt lại có thể rất tốn thời gian.

Nếu không tìm thấy tới `maxDepth=H`, dùng H thay d trong tổng trên. Số lần thăm phản ánh **cây các đường đi** nên có thể vượt đáng kể số state phân biệt của graph.

---

## 9. Độ phức tạp bộ nhớ

Một DLS chỉ cần lưu:

- Stack DFS hoặc các frame đệ quy.
- Path hiện tại.
- onPath chống chu trình của đường hiện tại.
- Bộ đếm và thông tin successor tại mỗi frame.

Nếu mỗi frame chỉ giữ con trỏ/iterator có kích thước hằng số, bộ nhớ phụ là:

\[
\boxed{O(d)}.
\]

Nếu mỗi frame sinh ra và giữ tối đa b successor cùng lúc, có thể là `O(bd)`. Cả hai thường ít hơn frontier BFS `O(b^d)` khi b lớn.

**Phân biệt bộ nhớ thuật toán với dữ liệu đầu vào:** nếu lưu graph trong `Map<String,List<String>>`, graph đã cần thêm `O(V+E)` RAM. Ưu điểm O(d) rõ nhất khi successor có thể được sinh **theo yêu cầu** mà không giữ cả graph.

### Đệ quy sâu trong Java

Nếu đường tìm kiếm sâu hàng trăm nghìn trạng thái, DLS đệ quy có thể gây `StackOverflowError` dù lý thuyết chỉ dùng bộ nhớ theo chiều sâu. Trong trường hợp đó nên thay bằng **DFS lặp với stack frame tường minh**, giữ đúng thao tác thêm/xóa path và onPath.

---

## 10. Java 17+ chạy độc lập

Chương trình dùng graph có hướng, duyệt successor theo thứ tự List, dùng **HashSet onPath** thay vì globalVisited, ghi thống kê từng limit và trả path khi tìm thấy.

Tên file: **`IterativeDeepeningDemo.java`**.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class IterativeDeepeningDemo {

    public record Attempt(
            int limit, long visited, boolean found) {
    }

    public record SearchResult(
            boolean found,
            int depth,
            List<String> path,
            List<Attempt> attempts,
            long totalVisits) {
    }

    private static final class Counter {
        long visited;
    }

    private static boolean depthLimited(
            Map<String, List<String>> graph,
            String state,
            String goal,
            int remaining,
            List<String> path,
            Set<String> onPath,
            Counter counter) {

        counter.visited++;

        // Goal first: a goal at the depth limit is valid.
        if (state.equals(goal)) {
            return true;
        }

        if (remaining == 0) {
            return false;
        }

        for (String next :
                graph.getOrDefault(state, List.of())) {

            if (onPath.contains(next)) {
                continue;
            }

            onPath.add(next);
            path.add(next);

            if (depthLimited(
                    graph, next, goal, remaining - 1,
                    path, onPath, counter)) {
                return true;
            }

            // Backtrack after a failed branch.
            path.remove(path.size() - 1);
            onPath.remove(next);
        }

        return false;
    }

    public static SearchResult iterativeDeepening(
            Map<String, List<String>> graph,
            String start,
            String goal,
            int maxDepth) {

        Objects.requireNonNull(graph, "graph");
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(goal, "goal");

        if (maxDepth < 0) {
            throw new IllegalArgumentException(
                    "maxDepth must be nonnegative");
        }

        for (Map.Entry<String, List<String>> entry
                : graph.entrySet()) {

            Objects.requireNonNull(
                    entry.getKey(), "null state");
            Objects.requireNonNull(
                    entry.getValue(), "null successors");

            for (String next : entry.getValue()) {
                Objects.requireNonNull(
                        next, "null successor");
            }
        }

        List<Attempt> attempts = new ArrayList<>();
        long totalVisits = 0;
        int limit = 0;

        while (true) {
            List<String> path = new ArrayList<>();
            path.add(start);

            Set<String> onPath = new HashSet<>();
            onPath.add(start);

            Counter counter = new Counter();

            boolean found = depthLimited(
                    graph, start, goal, limit,
                    path, onPath, counter);

            totalVisits = Math.addExact(
                    totalVisits, counter.visited);

            attempts.add(
                    new Attempt(limit, counter.visited, found));

            if (found) {
                return new SearchResult(
                        true,
                        path.size() - 1,
                        List.copyOf(path),
                        List.copyOf(attempts),
                        totalVisits);
            }

            if (limit == maxDepth) {
                return new SearchResult(
                        false,
                        -1,
                        List.of(),
                        List.copyOf(attempts),
                        totalVisits);
            }

            limit++;
        }
    }

    public static void main(String[] args) {
        Map<String, List<String>> graph =
                new LinkedHashMap<>();

        graph.put("S", List.of("A", "B"));
        graph.put("A", List.of("C", "S"));
        graph.put("B", List.of("D", "E"));
        graph.put("C", List.of("F"));
        graph.put("D", List.of("F"));
        graph.put("E", List.of("G"));
        graph.put("F", List.of("A"));
        graph.put("G", List.of());

        SearchResult result = iterativeDeepening(
                graph, "S", "G", 3);

        for (Attempt a : result.attempts()) {
            System.out.println(
                    "Depth " + a.limit()
                            + ": visited=" + a.visited()
                            + ", found=" + a.found());
        }

        System.out.println("Path: " + result.path());
        System.out.println(
                "Solution depth: " + result.depth());
        System.out.println(
                "Total visits: " + result.totalVisits());

        SearchResult limited = iterativeDeepening(
                graph, "S", "G", 2);

        System.out.println(
                "Bound 2 found: " + limited.found());

        SearchResult zero = iterativeDeepening(
                graph, "S", "S", 0);

        System.out.println(
                "Start equals goal: " + zero.path()
                        + " depth " + zero.depth());

        // Two paths reach X at different depths.
        Map<String, List<String>> counterexample =
                new LinkedHashMap<>();

        counterexample.put("S", List.of("A", "X"));
        counterexample.put("A", List.of("X"));
        counterexample.put("X", List.of("G"));
        counterexample.put("G", List.of());

        SearchResult safe = iterativeDeepening(
                counterexample, "S", "G", 2);

        System.out.println(
                "Global-visited counterexample path: "
                        + safe.path());

        Map<String, List<String>> isolated =
                Map.of("Q", List.<String>of());

        SearchResult missing = iterativeDeepening(
                isolated, "Q", "Z", 0);

        System.out.println(
                "Isolated start found: " + missing.found());

        boolean negativeBoundRejected = false;

        try {
            iterativeDeepening(graph, "S", "G", -1);
        } catch (IllegalArgumentException ex) {
            negativeBoundRejected = true;
        }

        System.out.println(
                "Negative bound rejected: "
                        + negativeBoundRejected);
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac IterativeDeepeningDemo.java
java IterativeDeepeningDemo
```

**Đầu ra chuẩn:**

```text
Depth 0: visited=1, found=false
Depth 1: visited=3, found=false
Depth 2: visited=6, found=false
Depth 3: visited=9, found=true
Path: [S, B, E, G]
Solution depth: 3
Total visits: 19
Bound 2 found: false
Start equals goal: [S] depth 0
Global-visited counterexample path: [S, X, G]
Isolated start found: false
Negative bound rejected: true
```

### Tại sao code đúng?

- `depthLimited` tăng visited ở **mọi lần gọi**, kể cả state ở đúng giới hạn không được sinh con. Vì vậy số visits 1,3,6,9 kiểm chứng được.
- Hàm kiểm tra goal **trước** remaining==0, không bỏ goal đúng giới hạn.
- Khi một nhánh thất bại, path và onPath đều được hoàn tác; khi thành công, path được giữ và `List.copyOf` đưa vào kết quả.
- Mỗi limit tạo lại path và onPath, nên không có visited giữ từ vòng trước.
- `maxDepth<0` bị từ chối; state không có key trong Map được coi là lá thông qua `getOrDefault`.
- `Math.addExact` phát hiện tràn số trong thống kê totalVisits thay vì im lặng quay vòng.
- `LinkedHashMap` dùng cho ví dụ; thứ tự DFS thực tế do `List.of(...)` của từng state quyết định.

---

## 11. Kiểm thử độc lập

### BFS làm oracle

Với graph hữu hạn không trọng số, BFS trả độ sâu ngắn nhất:

```text
BFS(start,goal):
    queue = [(start,0)]
    visited = {start}

    while queue chưa rỗng:
        (state,depth) = popFront(queue)
        nếu state là goal:
            return depth

        for next trong successors(state):
            nếu next không thuộc visited:
                visited.add(next)
                pushBack(queue,(next,depth+1))

    return -1
```

Nếu BFS tìm goal ở độ sâu d và maxDepth≥d, IDDFS phải trả **depth=d**. Không nhất thiết trả cùng path khi có nhiều đường ngắn nhất.

### Kiểm tra path và kết quả

- Path bắt đầu bằng start, kết thúc ở goal.
- Mọi cặp state liên tiếp là một cạnh hợp lệ.
- `path.size()-1==depth`.
- Không có state lặp trên path khi có onPath.
- Độ sâu bằng kết quả BFS khi cap đủ.
- Khi found=false, không tuyên bố vô nghiệm ngoài cap nếu chưa có bằng chứng.

### Bộ test bắt buộc

| Trường hợp | Kỳ vọng |
| --- | --- |
| start==goal, maxDepth=0 | Path=[start], depth 0 |
| Goal ở depth=1 | Thành công tại limit 1 |
| Goal đúng giới hạn L | Vẫn thành công |
| Goal ở depth L+1, cap L | found=false |
| Graph có self-loop và chu trình | Không lặp state trên path |
| Hai đường tới state X ở độ sâu khác nhau | Không bỏ nhánh nông |
| Graph không có cạnh | Không thể tới goal khác |
| maxDepth âm | Báo lỗi |
| State/successor null | Báo lỗi |
| Đường rất sâu | Cân nhắc tràn stack JVM |
| Các cạnh có chi phí khác nhau | Không nhầm depth với cost |

Với graph ngẫu nhiên nhỏ V≤8, có thể sinh nhiều cạnh, chu trình, rồi đối chiếu IDDFS với BFS ở cap=V−1. Đây là phép kiểm thử hiệu quả cho cả goal, giới hạn độ sâu và chống lặp.

---

## 12. IDDFS và IDA* khác nhau

**IDA*** (*Iterative Deepening A***) dùng ý tưởng lặp DFS với ngưỡng tăng dần nhưng ngưỡng là **ước lượng tổng chi phí**:

\[
f(n)=g(n)+h(n),
\]

trong đó:

- `g(n)` là chi phí thật đã đi từ start đến n.
- `h(n)` là ước lượng chi phí còn lại tới goal.
- `f(n)` là cận ước lượng tổng chi phí.

IDA* cắt một nhánh khi `f(n)>threshold`. Ngưỡng mới thường là **giá trị f nhỏ nhất vượt ngưỡng cũ**, thay vì tăng đơn vị độ sâu 0,1,2,...

Để được bảo đảm tối ưu về cost, cần giả thiết phù hợp về chi phí bước, heuristic admissible và xử lý trùng state. Không thể khẳng định IDA* luôn tối ưu trong mọi điều kiện.

**Khi chọn:**

- **IDDFS:** mọi thao tác đồng chi phí, cần ít bước và RAM hạn chế.
- **BFS:** graph không trọng số vừa đủ nhỏ để giữ queue/visited.
- **Dijkstra/uniform-cost search:** cạnh có cost không âm, cần tối thiểu tổng cost.
- **A*:** có heuristic tốt và đủ RAM cho frontier.
- **IDA*:** cần tiết kiệm RAM trong tìm kiếm cost với heuristic phù hợp.

---

## 13. Những lỗi thường gặp

1. Bắt đầu limit=1 thay vì 0, bỏ start==goal.
2. Kiểm tra cutoff trước goal, mất đích ở đúng limit.
3. Đếm limit theo số đỉnh thay vì số cạnh.
4. Không giảm remaining khi đi một cạnh.
5. Giữ visited toàn cục giữa nhiều limit, khiến vòng sau không mở rộng state.
6. Giữ visited toàn cục trong DLS, prune sai trạng thái tới ở độ sâu nông.
7. Quên xóa next khỏi onPath khi backtrack.
8. Quên xóa next khỏi path khi backtrack.
9. Xóa cả đường lời giải sau khi đã tìm thấy goal.
10. Không kiểm tra chu trình trên đường hiện tại, lãng phí nhánh.
11. Nhầm DLS một lần với IDDFS nhiều vòng.
12. Tuyên bố “không có lời giải” khi chỉ thử cap quá thấp.
13. Dùng IDDFS để tối ưu tổng trọng số không đồng nhất.
14. Coi số visits là số state phân biệt.
15. Nói IDDFS luôn nhanh hơn BFS; nó thường phải duyệt lặp.
16. Quên ngoại lệ b=1 có thể mất O(d²).
17. Nói RAM toàn bộ là O(d) dù input graph đã lưu.
18. Dùng khóa state thiếu thông tin chìa khóa/nguồn lực cần thiết.
19. Dùng object state mutable trong HashSet làm hash thay đổi.
20. Dùng đệ quy sâu mà không chú ý StackOverflowError.
21. Nhầm IDA* với IDDFS vì tên gần giống.
22. Phụ thuộc thứ tự HashSet khiến stdout không ổn định.
23. Không kiểm tra path, chỉ tin biến found.
24. Không đối chiếu BFS trên graph nhỏ.
25. Không giới hạn tìm kiếm trên không gian vô hạn vô nghiệm.

---

## 14. Bài tập tự kiểm tra

1. Nêu các thành phần của bài toán tìm kiếm trạng thái. Depth(start) là bao nhiêu?
2. DLS limit=0 có được phép đi qua cạnh nào không? Nếu start=goal thì sao?
3. Vì sao phải kiểm tra goal trước `remaining==0`?
4. Phân biệt DFS, BFS và IDDFS về thứ tự duyệt và RAM.
5. Với graph ví dụ chính, nêu các visits ở limit 0,1,2,3.
6. Tính tổng visits và đường đến G trong ví dụ chính.
7. Nếu cap=2 nhưng goal ở depth=3, kết luận đúng là gì?
8. Trên graph S→A,X; A→X; X→G, giải thích lỗi globalVisited ở limit 2.
9. Vì sao onPath cho phép X được xét lại trong nhánh S→X?
10. Nêu các điều kiện để IDDFS tìm được lời giải ở độ sâu d.
11. Chứng minh kết quả IDDFS đầu tiên có số cạnh nhỏ nhất.
12. Với cost S→G=20, S→A=1, A→G=1, IDDFS và đường ít cost chọn gì?
13. Với b=3,d=4, tính số visits tối đa của BFS và IDDFS khi quét hết mỗi mức.
14. Với b=1, tại sao tổng visits có thể là O(d²)?
15. Bộ nhớ phụ O(d) của IDDFS gồm những cấu trúc nào?
16. Vì sao graph đầu vào lưu trong Map vẫn tốn O(V+E)?
17. Khi nào có thể kết luận không reachable trên graph hữu hạn?
18. Dùng BFS kiểm thử kết quả IDDFS theo những thuộc tính nào?
19. Tại sao đường có chu trình không cần cho lời giải ít bước nhất?
20. Vì sao phải đưa keyMask vào state của mê cung có chìa khóa?
21. IDA* dùng ngưỡng gì khác với IDDFS?
22. DLS đệ quy rất sâu trong Java có thể gây lỗi gì?
23. Thứ tự successor có ảnh hưởng tính tối ưu độ sâu không?
24. Nếu bài cần tối ưu cost không đồng nhất, nên cân nhắc những thuật toán nào?

### Đáp án gợi ý

1. State, start, successor, goal; depth(start)=0.
2. Không được đi cạnh nào; vẫn kiểm tra start và trả thành công nếu start là goal.
3. Đích có thể nằm đúng giới hạn khi remaining=0.
4. DFS đi sâu; BFS theo tầng nhưng giữ frontier lớn; IDDFS lặp DLS tăng giới hạn, RAM theo đường.
5. `1,3,6,9`.
6. Tổng 19, path `[S,B,E,G]`, depth=3.
7. found=false **trong cap≤2**, không chứng minh vô nghiệm.
8. X ở depth2 bị đánh dấu, rồi X ở depth1 bị bỏ dù còn một bước tới G.
9. X được xóa khỏi onPath sau khi nhánh qua A thất bại.
10. Phân nhánh hữu hạn, lời giải ở d hữu hạn, cap≥d, DLS duyệt đầy đủ và không prune sai.
11. Nếu có lời giải nông hơn d, vòng ở giới hạn nông đó đã phải thành công, mâu thuẫn.
12. IDDFS chọn S→G (depth1,cost20); ít cost là S→A→G (cost2).
13. BFS 121, IDDFS 179 nếu quét đủ toàn bộ tầng mỗi lượt.
14. Tổng 1+2+...+(d+1) là O(d²).
15. Stack DFS, path, onPath, biến đếm.
16. RAM của adjacency input vẫn tồn tại, dù DFS không giữ frontier.
17. Khi đã xét hết đường đơn tới độ sâu V−1 trong graph hữu hạn đầy đủ mà không thấy goal.
18. So found, shortestDepth, đầu/cuối path, mọi cạnh liền nhau và độ dài path.
19. Loại chu trình tạo đường không dài hơn với state đầy đủ.
20. Cùng ô nhưng trạng thái có khóa khác nhau có successor khác nhau.
21. Ngưỡng `f=g+h` theo cost và heuristic, không phải số cạnh.
22. `StackOverflowError`; chuyển sang stack frame lặp.
23. Ảnh hưởng path cụ thể và visits, không đổi độ sâu nhỏ nhất nếu DLS đầy đủ.
24. Dijkstra, uniform-cost, A* hoặc IDA* khi giả thiết tương ứng thỏa.

---

## Ghi nhớ

**IDDFS = DLS với limit 0,1,2,...**. Kiểm tra goal trước khi cắt ở depth limit. Mỗi vòng tạo mới path và onPath; chống chu trình chỉ trong **đường hiện hành**, không dùng visited toàn cục thiếu thông tin ngân sách độ sâu. Nếu phân nhánh hữu hạn và có lời giải ở d hữu hạn trong giới hạn cho phép, IDDFS tìm được **lời giải ít cạnh nhất**. Với b>1 cố định, thời gian `O(b^d)`; bộ nhớ phụ `O(d)`, còn b=1 có thể tốn `O(d²)`. “Không thấy trong maxDepth” khác với “không có lời giải”, và ít bước không đồng nghĩa với ít tổng trọng số.
