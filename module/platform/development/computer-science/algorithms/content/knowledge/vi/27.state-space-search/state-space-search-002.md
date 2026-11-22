# Biểu diễn trạng thái và kiểm tra đã gặp

Trong **tìm kiếm trạng thái** (*state-space search*), câu hỏi quan trọng nhất là: **một trạng thái cần lưu những thông tin gì** để quyết định chính xác những bước tiếp theo, và **khi nào hai trạng thái được coi là giống nhau**? Nếu biểu diễn thiếu thông tin, thuật toán có thể bỏ sót nghiệm. Nếu biểu diễn thừa thông tin, số lượng trạng thái phình to. Nếu dùng `visited` sai, BFS/DFS có thể lặp lại công việc hoặc tìm sai kết quả.

Bài thuộc nhóm **Tìm kiếm trạng thái** trong Computer Science Algorithms. Ta sẽ xây dựng cách định nghĩa state, khóa nhận dạng và tập đã gặp, phân biệt BFS/DFS/Dijkstra, xử lý các lỗi Java về `equals/hashCode`, rồi giải một **mê cung có chìa khóa và cửa khóa** bằng Java 17 với kiểm thử độc lập trên **17.680 bản đồ nhỏ**.

## 1. Một trạng thái không nhất thiết chỉ là vị trí

Một bài toán tìm kiếm có:
- Tập các cấu hình hợp lệ `S`; mỗi cấu hình là **một đỉnh trong đồ thị trạng thái**.
- Trạng thái ban đầu `s_0`.
- Hàm `neighbors(s)` sinh những cấu hình đạt được sau **một thao tác hợp lệ**.
- Điều kiện `goal(s)` xác định khi nào hoàn thành.
- Chi phí `cost(s,s')` nếu đề yêu cầu tối ưu tổng chi phí.

Đồ thị trạng thái thường được **sinh động**, không cần tạo trước mọi đỉnh/cạnh. Khi đang xét s, ta sinh các trạng thái kế tiếp theo đúng luật.

**Tiêu chuẩn đầy đủ:** hai lịch sử dẫn tới **cùng khóa trạng thái** phải có **cùng các hành động hợp lệ từ đó về sau**, cùng ý nghĩa đạt đích và chi phí các bước tương lai. Đây là cách hiểu “thông tin hiện tại đủ quyết định tương lai”.

Ví dụ:

| Bài toán | Khóa trạng thái thường cần |
| --- | --- |
| Mê cung chỉ có tường tĩnh | `(row,col)` |
| Mê cung có khóa/cửa | `(row,col,keysMask)` |
| Robot có hướng nhìn, quay tốn bước | `(row,col,direction)` |
| Robot tiêu thụ pin khi di chuyển | `(row,col,remainingEnergy)` |
| Trò chơi theo lượt | `(board,whoseTurn)` |
| Vật cản lặp đúng chu kỳ L | `(row,col,time mod L)`, nếu không có phụ thuộc thời gian tuyệt đối |
| Xếp hình trượt | Toàn bộ cấu hình các ô, không chỉ vị trí ô trống |

Không cần ghi lại **toàn bộ lịch sử** nếu nó không thay đổi tương lai. Với BFS mỗi bước giá 1, số bước đã đi thường được lưu ở `dist[state]` hoặc suy ra từ parent, **không dùng làm thành phần đồng nhất state**. Nếu bài có deadline hoặc số lượt còn lại, phải lưu thông tin đó vì nó có thể làm thay đổi những bước hợp lệ.

## 2. Mê cung có chìa khóa: phản ví dụ cho visited chỉ theo ô

Quy tắc:
- `#` là tường, `.` là ô trống, `S` là điểm đầu, `T` là đích.
- Chữ thường `a..z` là chìa khóa, nhặt rồi giữ mãi.
- Chữ hoa `A..Z` (trừ S,T được dành cho điểm đầu/đích) là cửa, qua được nếu có chìa tương ứng.
- Mỗi bước sang ô kề trên/dưới/trái/phải có chi phí đúng 1.

Mê cung:

~~~text
#########
#S..A..T#
#.#.###.#
#a..#...#
#########
~~~

S ở (1,1), chìa a ở (3,1), cửa A ở (1,4), T ở (1,7), dùng tọa độ 0-based. Để tới T, phải nhặt a, quay lại vùng đã đi qua rồi mới qua A.

Nếu chỉ lưu `visited[row][col]`, ô S được đánh dấu ở bước đầu. Khi quay về S sau khi nhặt a, thuật toán tưởng đây là trạng thái đã gặp và **không cho phép mở rộng tiếp**, dù lúc này có chìa để mở cửa A. Cách sai có thể kết luận `−1` (không có đường) trong khi nghiệm thật có **10 bước**.

**Trạng thái đúng:**

\[
state=(row,\ col,\ keyMask).
\]

Với bit 0 dành cho chìa a:
- `(1,1,0)`: ở S, chưa có chìa.
- `(1,1,1)`: ở S, đã có chìa.

Hai state cùng ô nhưng khác quyền hành động, nên **không được gộp**.

Với hai chìa a,b, mask nhị phân:
- 0: chưa có chìa nào;
- 1: chỉ a;
- 2: chỉ b;
- 3: có cả a,b.

Tập chìa là **không có thứ tự**: nhặt a rồi b và nhặt b rồi a đều cho mask=3; không cần nhớ thứ tự nhặt. Nếu chìa bị **tiêu hao** khi mở cửa, mô hình này phải bổ sung thông tin chìa còn lại/tình trạng cửa — bitmask đã từng nhặt không còn đủ.

## 3. Sinh trạng thái kế tiếp đúng quy tắc

Từ `(r,c,mask)`, đi theo một hướng:
1. Tính ô đích `(nr,nc)`. Ra ngoài bảng hoặc gặp tường → không có bước hợp lệ.
2. Gặp cửa K: phải có bit của chìa k trong mask **hiện tại**, nếu không → bỏ bước.
3. Gặp chìa k: tính `newMask = mask OR (1 << index[k])`.
4. Các ô khác giữ mask.
5. Tạo khóa state mới `(nr,nc,newMask)`, rồi **mới kiểm tra visited**.

Biểu thức:

\[
newMask=mask\ \mathrm{OR}\ (1\ll k).
\]

Kiểm tra bit chìa:

\[
(mask\ \mathrm{AND}\ (1\ll k))\ne0.
\]

Nếu cập nhật mask **sau khi** thêm state vào visited, tập đã gặp chứa trạng thái sai. Nếu xem cửa là ô trống, ta cho phép đường không hợp lệ. Nếu chỉ đánh dấu theo tọa độ, ta đánh đồng hai tình huống khác quyền mở cửa.

### Nén bit cho chìa xuất hiện

Quét bảng để tìm những chữ thường có mặt, gán mỗi **loại chìa** một bit từ 0 tới k−1. Nếu chỉ có a và q, ta có thể gán a→bit0, q→bit1, không cần cấp phát 2^26 mask. Nếu có cửa X mà không có chìa x, nó không thể mở trong mô hình.

Có tối đa 26 loại a..z, nên một `int` có thể chứa bitmask này. Tuy nhiên số cấu hình lý thuyết có thể tới `rows×cols×2^k`; dù bitmask gọn, **không gian trạng thái vẫn có thể rất lớn**.

## 4. Equality, hashCode và khóa bất biến

Đối với mê cung này, hai state bằng nhau khi và chỉ khi **cả row, col, keyMask cùng bằng nhau**.

Trong Java 17, có thể viết:

~~~text
record State(int row, int col, int keyMask) {}
~~~

Record có `equals` và `hashCode` đúng theo ba trường nguyên thủy, các trường không thể sửa sau khi tạo. Dùng làm khóa `HashSet<State>` và `HashMap<State,Previous>` là hợp lý.

Các lỗi phổ biến:

1. **Dùng mảng làm khóa:** hai mảng `new int[]{1,2}` khác đối tượng dù cùng nội dung; `HashSet<int[]>` không tự so từng phần tử.
2. **Record chứa mảng:** `record Board(int[] tiles) {}` vẫn so trường mảng theo reference, không tự tạo deep equality; cần tự cài `Arrays.equals/Arrays.hashCode` trên snapshot bất biến hoặc dùng dạng lưu thích hợp.
3. **Sửa khóa mutable sau khi thêm vào HashSet:** thay đổi giá trị tham gia hashCode có thể khiến tìm lại thất bại. Dùng khóa bất biến.
4. **equals không khớp hashCode:** nếu hai đối tượng bằng nhau, hashCode bắt buộc bằng nhau.
5. **Dùng `==` để so nội dung String:** phải dùng `equals` hoặc phương pháp so nội dung phù hợp.
6. **Nối chuỗi khóa nhập nhằng:** `(1,23)` và `(12,3)` đều thành `"123"` nếu nối thô; dùng tuple hoặc delimiter rõ ràng.

### Cách lưu visited

| Cách | Phù hợp | Hạn chế |
| --- | --- | --- |
| `boolean[R][C]` | Chỉ vị trí quyết định tương lai | **Sai** khi có keys/energy/direction |
| `boolean[R][C][1<<k]` | k nhỏ, miền trạng thái dày | Bộ nhớ O(RC2^k) và overhead mảng |
| `HashSet<State>` | State nhiều trường, chỉ lưu reachable | Tốn overhead hash/object, cần equals/hashCode đúng |

Có thể mã hóa duy nhất `id=((mask*R)+row)*C+col` để dùng `BitSet`/mảng một chiều khi tích `R*C*2^k` không tràn số và có thể cấp phát. Nhớ giữ nhất quán thứ tự mã hóa/giải mã.

## 5. Kiểm tra đã gặp trong BFS

Với **mỗi cạnh có chi phí bằng 1**, BFS duyệt theo lớp khoảng cách tăng dần. Trạng thái đầu ở lớp 0, các state đạt được sau một bước ở lớp 1, v.v.

**Đánh dấu visited ngay khi đưa trạng thái vào hàng đợi (enqueue).**

~~~text
queue.add(start)
visited.add(start)
distance[start] = 0

while queue không rỗng:
    current = queue.removeFirst()
    if goal(current): return distance[current]

    for next trong nextStates(current):
        if visited.add(next):
            distance[next] = distance[current] + 1
            parent[next] = current
            queue.addLast(next)
~~~

Vì FIFO xử lý lớp d trước lớp d+1, **lần đầu phát hiện** một state đã có đường ngắn nhất theo số bước. Nếu một đường khác tới cùng state xuất hiện sau, nó không thể ngắn hơn. Do đó chặn lần enqueue lặp là đúng và tiết kiệm bộ nhớ.

Nếu chỉ đánh dấu khi dequeue, nhiều parent có thể enqueue cùng state trước khi state được pop; vẫn có thể cài đúng nếu kiểm tra trùng kỹ, nhưng dễ lãng phí. Nếu ghi đè parent của state đã visited bằng một đường dài hơn, chứng cứ đường đi có thể sai.

**Parent phải lưu theo state đầy đủ**, không chỉ theo ô địa lý. Cùng ô với mask khác có đường đi và trạng thái cha khác nhau.

### Phân biệt BFS, DFS và Dijkstra

- **DFS** thích hợp tìm một nghiệm/kiểm tra có thể tới, không bảo đảm ít bước nhất. Với bài duyệt reachable, visited toàn cục ngăn vòng.
- **BFS** thích hợp tìm ít bước nhất khi mỗi cạnh giá 1; visited-on-enqueue chốt lần phát hiện đầu.
- **0–1 BFS** dùng deque và `dist[state]` khi mỗi cạnh giá 0 hoặc 1; phải relax khi tìm khoảng cách tốt hơn.
- **Dijkstra** khi chi phí không âm: lưu `dist[state]`, priority queue và xử lý lại nếu thấy khoảng cách tốt hơn trước khi chốt; **không** dùng Boolean visited-on-enqueue như BFS đều bước.
- **Bellman–Ford** khi có cạnh âm, cần kiểm soát chu trình âm và relax nhiều lượt.
- **A*** dùng heuristic phù hợp, `gScore` và quy tắc reopen/finalize nhất quán với tính chất heuristic.

Nếu bài yêu cầu **liệt kê mọi đường đơn**, visited toàn cục có thể loại nhiều lời giải khác nhau đi qua cùng đỉnh. Khi đó dùng backtracking với tập những đỉnh trên **đường hiện tại** và bỏ đánh dấu khi quay lui, không dùng mô hình BFS chỉ cần một nghiệm.

## 6. Chuẩn hóa và dominance

**Chuẩn hóa** giúp tránh state trùng:
- Tập chìa không có thứ tự → bitmask.
- Hai tác nhân thực sự **không phân biệt** → đôi khi sort vị trí để gộp (x,y) và (y,x).
- Bẫy lặp chu kỳ L → có thể lưu `time mod L` thay vì thời gian tuyệt đối.

**Chỉ được chuẩn hóa nếu chứng minh tương lai không đổi.** Nếu hai tác nhân có chức năng khác nhau, sort vị trí có thể gộp sai. Nếu có deadline, chỉ lưu pha thời gian có thể mất điều kiện hoàn thành.

**Dominance** là tối ưu nâng cao khác với equality. Trong mê cung chìa **không bị tiêu hao**, state tại cùng ô có **siêu tập chìa** có thể mạnh hơn, nhưng để loại state ít chìa còn phải đảm bảo nó được tới với khoảng cách **không nhỏ hơn** state nhiều chìa. Ví dụ giữ {a,b} sau 10 bước không tự động thắng giữ {a} sau 4 bước. Mã bài này chỉ dùng equality đầy đủ, không dùng dominance.

## 7. Ví dụ đi từ S tới T

Mê cung:

~~~text
#########
#S..A..T#
#.#.###.#
#a..#...#
#########
~~~

Với thứ tự thử hướng **D, U, R, L**, một đường ngắn nhất là:

~~~text
DDUURRRRRR
~~~

| Bước | Vị trí | Mask | Sự kiện |
| ---: | --- | ---: | --- |
| 0 | (1,1) | 0 | Đứng ở S, chưa có a |
| 1 | (2,1) | 0 | Đi xuống |
| 2 | (3,1) | 1 | Nhặt a |
| 3 | (2,1) | 1 | Quay lên với a |
| 4 | (1,1) | 1 | Lại tới S, nhưng **state khác** |
| 5 | (1,2) | 1 | Sang phải |
| 6 | (1,3) | 1 | Sang phải |
| 7 | (1,4) | 1 | Qua cửa A |
| 8 | (1,5) | 1 | Sang phải |
| 9 | (1,6) | 1 | Sang phải |
| 10 | (1,7) | 1 | Tới T |

Một đường khác cùng số bước có thể tồn tại; BFS theo thứ tự hướng xác định sẽ trả một nghiệm cụ thể. **Số bước không bằng số ô khác nhau** vì có thể quay lại ô cũ với tài nguyên khác.

Mê cung hai khóa:

~~~text
############
#S.a.A.b.BT#
############
~~~

Chìa a rồi cửa A, chìa b rồi cửa B. Mask tiến 0→1→3. Đường ngắn nhất là **9 bước** đi sang phải: `RRRRRRRRR`.

Mê cung có cửa A mà **không có a**:

~~~text
#######
#S.A.T#
#######
~~~

Không đi qua được A, nên kết quả **−1**.

## 8. Java 17: BFS với record State

Chương trình chạy độc lập, không cần thư viện ngoài JDK:
- `State(row,col,keyMask)` bất biến, tự có equals/hashCode.
- `Grid` kiểm tra bảng chữ nhật, đúng một S và T, ký hiệu hợp lệ; gán bit cho chìa xuất hiện.
- BFS đúng lưu `HashSet<State>`, đánh dấu khi enqueue; `HashMap<State,Previous>` lưu parent và hướng.
- `wrongCellOnly()` được **cố ý viết sai** để so sánh.
- `oracle()` dùng Dijkstra quét tuyến tính trên **đồ thị trạng thái mã hóa theo số**, kiểm tra bước trực tiếp mà không gọi `Grid.move`.
- `verifyTinyGrids()` duyệt 17.680 bảng nhỏ để đối chiếu kết quả.

~~~java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StateIdentityVisitedDemo {
    static final int[] DR = {1, -1, 0, 0};
    static final int[] DC = {0, 0, 1, -1};
    static final char[] DIRECTIONS = {'D', 'U', 'R', 'L'};

    record State(int row, int col, int keyMask) {}
    record Previous(State from, char direction) {}
    record Item(State state, int distance) {}
    record Answer(int distance, String moves,
                  int discovered, int expanded) {}
    record Stats(int worlds, int reachable, int unreachable,
                 int wrongPositionOnly, int longest) {}

    static final class Grid {
        final String[] lines;
        final int h, w, sr, sc, tr, tc, keyCount;
        final int[] keyBit = new int[26];

        Grid(String... input) {
            if (input == null || input.length == 0
                    || input[0] == null || input[0].isEmpty())
                throw new IllegalArgumentException("Invalid grid");

            lines = Arrays.copyOf(input, input.length);
            h = lines.length;
            w = lines[0].length();
            Arrays.fill(keyBit, -1);
            boolean[] present = new boolean[26];
            int sRow = -1, sCol = -1, tRow = -1, tCol = -1;
            int sCount = 0, tCount = 0;

            for (int r = 0; r < h; r++) {
                if (lines[r] == null || lines[r].length() != w)
                    throw new IllegalArgumentException(
                            "Nonrectangular grid");
                for (int c = 0; c < w; c++) {
                    char ch = lines[r].charAt(c);
                    if (ch == 'S') {
                        sRow = r; sCol = c; sCount++;
                    } else if (ch == 'T') {
                        tRow = r; tCol = c; tCount++;
                    } else if (ch >= 'a' && ch <= 'z') {
                        present[ch - 'a'] = true;
                    } else if (ch != '#' && ch != '.'
                            && !(ch >= 'A' && ch <= 'Z')) {
                        throw new IllegalArgumentException(
                                "Invalid symbol");
                    }
                }
            }
            if (sCount != 1 || tCount != 1)
                throw new IllegalArgumentException(
                        "Exactly one S and T required");

            sr = sRow; sc = sCol; tr = tRow; tc = tCol;
            int count = 0;
            for (int i = 0; i < 26; i++)
                if (present[i]) keyBit[i] = count++;
            keyCount = count;
        }

        State start() {
            return new State(sr, sc, 0);
        }

        boolean goal(State s) {
            return s.row() == tr && s.col() == tc;
        }

        State move(State cur, int dir) {
            int r = cur.row() + DR[dir];
            int c = cur.col() + DC[dir];
            if (r < 0 || r >= h || c < 0 || c >= w)
                return null;
            char ch = lines[r].charAt(c);
            if (ch == '#') return null;

            int mask = cur.keyMask();
            if (ch >= 'A' && ch <= 'Z'
                    && ch != 'S' && ch != 'T') {
                int bit = keyBit[ch - 'A'];
                if (bit < 0 || (mask & (1 << bit)) == 0)
                    return null;
            }
            if (ch >= 'a' && ch <= 'z')
                mask |= 1 << keyBit[ch - 'a'];
            return new State(r, c, mask);
        }

        Answer solve() {
            State start = start();
            Set<State> seen = new HashSet<>();
            Map<State, Previous> parent = new HashMap<>();
            ArrayDeque<State> queue = new ArrayDeque<>();
            seen.add(start);
            queue.addLast(start);
            int expanded = 0;

            while (!queue.isEmpty()) {
                State u = queue.removeFirst();
                expanded++;
                if (goal(u)) {
                    StringBuilder rev = new StringBuilder();
                    State at = u;
                    while (!at.equals(start)) {
                        Previous p = parent.get(at);
                        if (p == null)
                            throw new IllegalStateException(
                                    "Broken parent chain");
                        rev.append(p.direction());
                        at = p.from();
                    }
                    String moves = rev.reverse().toString();
                    return new Answer(
                            moves.length(), moves,
                            seen.size(), expanded);
                }

                for (int d = 0; d < 4; d++) {
                    State v = move(u, d);
                    if (v != null && seen.add(v)) {
                        parent.put(v,
                                new Previous(u, DIRECTIONS[d]));
                        queue.addLast(v);
                    }
                }
            }
            return new Answer(-1, "",
                    seen.size(), expanded);
        }

        // PHAN SAI CO Y: visited chi theo row,col.
        int wrongCellOnly() {
            boolean[][] seen = new boolean[h][w];
            ArrayDeque<Item> queue = new ArrayDeque<>();
            seen[sr][sc] = true;
            queue.addLast(new Item(start(), 0));

            while (!queue.isEmpty()) {
                Item x = queue.removeFirst();
                if (goal(x.state())) return x.distance();
                for (int d = 0; d < 4; d++) {
                    State v = move(x.state(), d);
                    if (v == null || seen[v.row()][v.col()])
                        continue;
                    seen[v.row()][v.col()] = true;
                    queue.addLast(
                            new Item(v, x.distance() + 1));
                }
            }
            return -1;
        }

        boolean validMoves(Answer a) {
            if (a.distance() == -1)
                return a.moves().isEmpty();
            if (a.distance() != a.moves().length())
                return false;
            State cur = start();
            for (int i = 0; i < a.moves().length(); i++) {
                int d = -1;
                for (int j = 0; j < 4; j++)
                    if (DIRECTIONS[j] == a.moves().charAt(i))
                        d = j;
                if (d < 0) return false;
                cur = move(cur, d);
                if (cur == null) return false;
            }
            return goal(cur);
        }

        // Oracle Dijkstra khong dung solve()/move().
        // Chi cho bang nho voi <=4 loai khoa.
        int oracle() {
            if (keyCount > 4)
                throw new IllegalArgumentException(
                        "Oracle too many keys");
            int stride = h * w;
            int count = stride * (1 << keyCount);
            int INF = 1_000_000;
            int[] dist = new int[count];
            boolean[] used = new boolean[count];
            Arrays.fill(dist, INF);
            dist[sr * w + sc] = 0;

            for (int round = 0; round < count; round++) {
                int u = -1;
                for (int i = 0; i < count; i++)
                    if (!used[i]
                            && (u < 0 || dist[i] < dist[u]))
                        u = i;
                if (u < 0 || dist[u] == INF) break;

                int mask = u / stride;
                int pos = u % stride;
                int row = pos / w, col = pos % w;
                if (row == tr && col == tc) return dist[u];
                used[u] = true;

                for (int d = 0; d < 4; d++) {
                    int nr = row + DR[d], nc = col + DC[d];
                    if (nr < 0 || nr >= h || nc < 0 || nc >= w)
                        continue;
                    char ch = lines[nr].charAt(nc);
                    if (ch == '#') continue;
                    int newMask = mask;
                    if (ch >= 'A' && ch <= 'Z'
                            && ch != 'S' && ch != 'T') {
                        int bit = keyBit[ch - 'A'];
                        if (bit < 0
                                || (mask & (1 << bit)) == 0)
                            continue;
                    }
                    if (ch >= 'a' && ch <= 'z')
                        newMask |= 1 << keyBit[ch - 'a'];

                    int v = newMask * stride + nr * w + nc;
                    if (dist[v] > dist[u] + 1)
                        dist[v] = dist[u] + 1;
                }
            }
            return -1;
        }
    }

    static final class Counter {
        int worlds, reachable, unreachable;
        int wrong, longest;
    }

    static void enumerate(
            int h, int w, char[] alphabet, Counter c) {
        int total = 1;
        for (int i = 0; i < h * w - 2; i++)
            total *= alphabet.length;

        for (int code = 0; code < total; code++) {
            char[] cells = new char[h * w];
            Arrays.fill(cells, '.');
            cells[0] = 'S';
            cells[cells.length - 1] = 'T';
            int number = code;

            for (int i = 1; i < cells.length - 1; i++) {
                cells[i] = alphabet[number % alphabet.length];
                number /= alphabet.length;
            }
            String[] rows = new String[h];
            for (int r = 0; r < h; r++)
                rows[r] = new String(cells, r * w, w);

            Grid g = new Grid(rows);
            Answer actual = g.solve();
            int expected = g.oracle();
            if (actual.distance() != expected
                    || !g.validMoves(actual))
                throw new AssertionError(
                        "Mismatch " + Arrays.toString(rows));

            int wrong = g.wrongCellOnly();
            c.worlds++;
            if (actual.distance() >= 0) {
                c.reachable++;
                c.longest = Math.max(
                        c.longest, actual.distance());
            } else {
                c.unreachable++;
            }
            if (wrong != actual.distance()) c.wrong++;
        }
    }

    static Stats verifyTinyGrids() {
        Counter c = new Counter();
        enumerate(2, 3,
                new char[]{'.', '#', 'a', 'A', 'b', 'B'}, c);
        enumerate(3, 3,
                new char[]{'.', '#', 'a', 'A'}, c);

        if (c.worlds != 17680 || c.reachable != 10366
                || c.unreachable != 7314 || c.wrong != 333
                || c.longest != 8)
            throw new AssertionError("Unexpected counts");

        return new Stats(c.worlds, c.reachable,
                c.unreachable, c.wrong, c.longest);
    }

    public static void main(String[] args) {
        Grid maze = new Grid(
                "#########",
                "#S..A..T#",
                "#.#.###.#",
                "#a..#...#",
                "#########");
        Answer m = maze.solve();
        System.out.println("mazeSteps=" + m.distance());
        System.out.println("mazeMoves=" + m.moves());
        System.out.println("mazeVisitedStates=" + m.discovered());
        System.out.println("mazeExpandedStates=" + m.expanded());
        System.out.println("mazeValidPath=" + maze.validMoves(m));
        System.out.println("wrongCellOnlyMaze="
                + maze.wrongCellOnly());

        State before = new State(1, 1, 0);
        State after = new State(1, 1, 1);
        System.out.println("sameCellDifferentState="
                + !before.equals(after));
        System.out.println("equalRecordKeys="
                + new State(1, 1, 1).equals(after));

        Answer simple = new Grid(
                "#######", "#S..T.#", "#######").solve();
        System.out.println("simpleSteps=" + simple.distance()
                + " moves=" + simple.moves());

        Answer twoKeys = new Grid(
                "############", "#S.a.A.b.BT#",
                "############").solve();
        System.out.println("twoKeysSteps=" + twoKeys.distance()
                + " moves=" + twoKeys.moves());

        System.out.println("lockedWithoutKey="
                + new Grid("#######", "#S.A.T#",
                           "#######").solve().distance());
        System.out.println("wallBlocked="
                + new Grid("#####", "#S#T#",
                           "#####").solve().distance());

        try {
            new Grid("S..", "..T#");
            throw new AssertionError("Bad grid accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("badGridRejected="
                    + ex.getMessage());
        }

        Stats s = verifyTinyGrids();
        System.out.println("testedGrids=" + s.worlds());
        System.out.println("reachableGrids=" + s.reachable());
        System.out.println("unreachableGrids=" + s.unreachable());
        System.out.println("positionOnlyWrong="
                + s.wrongPositionOnly());
        System.out.println("maxShortestDistance="
                + s.longest());
    }
}
~~~

Lưu vào tệp **StateIdentityVisitedDemo.java** và chạy với **JDK 17 trở lên**:

~~~bash
javac StateIdentityVisitedDemo.java
java StateIdentityVisitedDemo
~~~

**Đầu ra dự kiến:**

~~~text
mazeSteps=10
mazeMoves=DDUURRRRRR
mazeVisitedStates=19
mazeExpandedStates=19
mazeValidPath=true
wrongCellOnlyMaze=-1
sameCellDifferentState=true
equalRecordKeys=true
simpleSteps=3 moves=RRR
twoKeysSteps=9 moves=RRRRRRRRR
lockedWithoutKey=-1
wallBlocked=-1
badGridRejected=Nonrectangular grid
testedGrids=17680
reachableGrids=10366
unreachableGrids=7314
positionOnlyWrong=333
maxShortestDistance=8
~~~

Bốn dòng đầu cho thấy BFS tìm được đường 10 bước, và có 19 **trạng thái đầy đủ** đã được đưa vào visited. `sameCellDifferentState=true` chứng minh cùng tọa độ với mask khác được phân biệt; `wrongCellOnlyMaze=-1` là phản ví dụ cho cài đặt sai.

## 9. Kiểm chứng độc lập 17.680 bảng

Chương trình duyệt:
- **2×3**: S đầu, T cuối, bốn ô còn lại mỗi ô có 6 lựa chọn `. # a A b B`, tổng `6^4=1.296`.
- **3×3**: S đầu, T cuối, bảy ô còn lại có 4 lựa chọn `. # a A`, tổng `4^7=16.384`.

Với mỗi bảng, BFS đúng được so với **Dijkstra tường minh trên các state id**. Chuỗi hướng được phát lại bằng luật chuyển, kiểm tra không đi qua tường/cửa khóa. BFS sai chỉ visited tọa độ cũng được chạy để đếm số bảng có kết quả khác.

| Kết quả | Số lượng |
| --- | ---: |
| Tổng bảng | 17.680 |
| Bảng tới được T | 10.366 |
| Bảng không tới được | 7.314 |
| Bảng mà visited chỉ theo ô trả sai | **333** |
| Khoảng cách ngắn nhất lớn nhất trong tập | 8 |

Phản ví dụ rất nhỏ:

~~~text
SA.
a#T
~~~

BFS trạng thái đầy đủ tìm đường dài **5 bước** bằng việc lấy a rồi quay lên mở A. Chỉ visited tọa độ báo **không tới được**. Đây là lỗi **biểu diễn state**, không phải lỗi FIFO hay thứ tự duyệt.

Oracle Dijkstra quét O(N²), chỉ phù hợp với **bảng nhỏ** và không phải thuật toán dùng trong bài sản xuất. Việc đối chiếu hữu hạn hữu ích để phát hiện sai sót, nhưng không thay thế chứng minh BFS.

## 10. Chứng minh tính đúng

**Tính đầy đủ của state.** Từ `(row,col,keyMask)`, bảng tĩnh và các quy tắc cho biết mọi bước kề hợp lệ, cửa nào mở được, việc nhặt chìa có thay đổi mask hay không, và đã tới T hay chưa. Hai lịch sử có cùng ba trường có cùng tương lai nên gộp an toàn. Chỉ lưu `(row,col)` là không đủ vì quyền mở cửa khác nhau.

**BFS chốt khoảng cách lần phát hiện đầu.** Giả sử state v lần đầu được sinh từ u ở lớp d. Có một đường dài d+1 tới v. Nếu tồn tại đường ngắn hơn, state ngay trước v trên đường đó nằm ở lớp nhỏ hơn d và phải được BFS xử lý trước u, mâu thuẫn với lần phát hiện đầu. Do đó đánh dấu khi enqueue không làm mất đường ngắn hơn.

**Hoàn thành hoặc kết luận không có đường.** Số khóa trạng thái hữu hạn (tối đa `RC·2^k`) và mỗi khóa chỉ enqueue một lần. BFS hoặc gặp T theo lớp khoảng cách tăng dần, cho số bước ít nhất, hoặc queue rỗng và không có đường hợp lệ.

**Khôi phục đúng đường.** Khi sinh state mới, parent và direction ghi lại bước hợp lệ từ state trước. Mỗi parent nằm ở lớp khoảng cách nhỏ hơn một đơn vị, nên chuỗi parent không có vòng. Đảo các hướng thu được đường từ nguồn tới đích có đúng độ dài BFS; `validMoves` kiểm tra thực nghiệm từng bước.

## 11. Độ phức tạp và giới hạn

Nếu bảng R×C và có k loại chìa, số trạng thái tối đa:

\[
N=R\cdot C\cdot2^k.
\]

Mỗi trạng thái có tối đa 4 bước đi. Với phép hash trung bình O(1):
- Tiền xử lý bảng: **O(RC)**.
- BFS trường hợp xấu: **O(RC·2^k)** thời gian.
- visited/parent/queue: **O(RC·2^k)** bộ nhớ.
- Khôi phục đường cuối: O(L) với L là độ dài đường trả về.

Với k=0, giới hạn trở về O(RC). Khi k tăng, số state có thể tăng hàm mũ. HashSet chỉ lưu những state thực sự phát hiện, nhưng cũng có thể gần chạm giới hạn trên và tốn overhead lớn. Khi k nhỏ và miền state dày, dùng BitSet hoặc mảng visited mã hóa ID thường tiết kiệm bộ nhớ.

Nếu state là cả bàn cờ String dài M, mỗi lần tạo/hash/copy state có thể tốn O(M), nên cần tính thêm chi phí theo kích thước biểu diễn; không mặc định mọi state key đều được hash O(1).

## 12. Bài tập kèm đáp án

**Bài 1.** Robot có hướng nhìn, chỉ tiến theo hướng hiện tại và quay tốn bước. Lưu `(r,c)` đủ chưa?

*Đáp án:* Chưa; cần `(r,c,direction)`.

**Bài 2.** Hai state cùng ô (2,3) nhưng mask1 (a) và mask3 (a,b) có bằng nhau không?

*Đáp án:* Không; khả năng qua cửa B có thể khác.

**Bài 3.** Mask5 (nhị phân101), bit a=0,b=1,c=2 có những chìa nào?

*Đáp án:* a và c, không có b.

**Bài 4.** Mask1 nhặt thêm b với bit1 thành mấy?

*Đáp án:* `1 OR (1<<1)=3`.

**Bài 5.** Hai mảng Java `new int[]{1,2}` được tạo riêng có equals nội dung không?

*Đáp án:* Không; array equals theo reference.

**Bài 6.** Vì sao BFS đều bước có thể visited ngay khi enqueue?

*Đáp án:* Lần phát hiện đầu qua FIFO đã tối ưu theo số bước.

**Bài 7.** Cạnh có giá khác nhau, có thể dùng visited-on-enqueue để tìm chi phí ngắn nhất không?

*Đáp án:* Không nói chung; phải dùng dist và thuật toán có relax như Dijkstra với trọng số không âm.

**Bài 8.** Có cửa A mà không có chìa a; có đi qua A được không?

*Đáp án:* Không, trong luật của bài.

**Bài 9.** Nhặt a rồi b hoặc b rồi a có phải hai state khác nhau khi chìa không tiêu hao?

*Đáp án:* Không, cùng tập chìa và cùng mask.

**Bài 10.** Vì sao ô S xuất hiện ở bước 0 và 4 không bị gộp?

*Đáp án:* Trước khi nhặt chìa mask0, sau khi nhặt chìa mask1.

**Bài 11.** Lưới 10×20, có 4 loại chìa. Giới hạn tối đa số state?

*Đáp án:* `10×20×2^4=3.200`.

**Bài 12.** Hai robot có nhiệm vụ khác nhau có được chuẩn hóa bằng cách sort vị trí không?

*Đáp án:* Không nếu đổi nhãn làm thay đổi thao tác hoặc điều kiện đích.

**Bài 13.** DFS liệt kê mọi đường đơn có nên visited toàn cục không?

*Đáp án:* Không; cần tập trên đường hiện tại và backtrack.

**Bài 14.** Bẫy đúng chu kỳ 2 có thể lưu `time mod2` khi nào?

*Đáp án:* Khi tương lai chỉ phụ thuộc parity, không có hạn chót phụ thuộc thời gian tuyệt đối.

**Bài 15.** Tại cùng ô, có a,b sau 10 bước và chỉ a sau 4 bước. Có bỏ state ít chìa vì bị state nhiều chìa thống trị không?

*Đáp án:* Không tự động. Cần xét cả khoảng cách; state nhiều chìa đến muộn có thể không tốt hơn.

## 13. Checklist và lỗi phổ biến

1. Định nghĩa **toàn bộ thông tin quyết định tương lai**, không mặc định vị trí là state đầy đủ.
2. Dùng khóa **bất biến**, equals/hashCode nhất quán; cẩn thận mảng, String và object mutable.
3. Chuẩn hóa chỉ khi chứng minh hai cấu hình tương đương.
4. Tính giới hạn số state, đặc biệt thừa số `2^k`.
5. Sinh bước theo thứ tự kiểm tra tường/cửa → cập nhật mask → tạo state → kiểm tra visited.
6. Chỉ dùng BFS với trọng số đều nhau nếu cần ít bước nhất.
7. Đánh dấu visited **khi enqueue**, parent chỉ ghi cho state phát hiện đầu.
8. Khôi phục đường theo state **đầy đủ**; phát lại chứng cứ để kiểm tra.
9. Thử cửa không chìa, nhiều loại chìa, quay lại ô cũ với mask mới, bảng không hợp lệ và đích không tới được.
10. So với oracle độc lập trên đồ thị nhỏ thay vì chỉ dựa vào một ví dụ.

Các lỗi thực tế hay gặp: gộp hai state cùng ô nhưng khác tài nguyên; dùng array làm HashSet key; sửa key sau insert; so String bằng `==`; dùng dấu nối tuple không rõ; quên cập nhật mask khi nhặt chìa; sai dấu so cửa; dùng visited-on-enqueue kiểu BFS cho Dijkstra; ghi đè parent của state cũ; không phân biệt DFS tìm một nghiệm với DFS liệt kê mọi đường; và đánh giá thiếu chi phí bộ nhớ.

## Ghi nhớ

- **State identity quyết định tính đúng của search.** Một state cần đủ dữ liệu mô tả tương lai.
- Trong mê cung có khóa, dùng `(row,col,keyMask)`; visited chỉ theo ô là thiếu và có thể trả sai.
- Record với trường primitive là khóa HashSet/HashMap thuận tiện trong Java 17; record có mảng vẫn cần equality nội dung riêng.
- BFS mọi cạnh giá 1: đánh dấu visited **khi enqueue**, lần phát hiện đầu đã cho khoảng cách ngắn nhất.
- Bài có trọng số hoặc nhiệm vụ liệt kê lời giải cần quy tắc visited khác.
- Kiểm thử 17.680 bản đồ nhỏ đã thấy 333 trường hợp visited chỉ theo vị trí không đúng: **trước khi tối ưu thuật toán duyệt, hãy mô hình hóa chính xác đồ thị trạng thái**.
