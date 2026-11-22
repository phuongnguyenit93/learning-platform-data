# Tìm từ hoặc đường đi trên lưới

**Quay lui (backtracking) trên lưới** là cách thử từng bước di chuyển hợp lệ, đánh dấu các ô đã dùng trên **đường đi hiện tại**, đi sâu bằng DFS rồi **hoàn tác** dấu đó khi một nhánh không đưa đến kết quả. Kỹ thuật này giúp giải các bài **tìm từ trên ma trận ký tự**, **tìm một đường đi đơn từ S tới T**, **đếm hoặc liệt kê tất cả đường đi đơn**. Dù cùng dùng DFS, mục tiêu “tìm một”, “đếm mọi” và “ngắn nhất” không đồng nghĩa.

Bài thuộc nhóm **Quay lui** trong Computer Science Algorithms. Người học cần hiểu rõ luật kề bốn/tám hướng, trạng thái visited và path, điều kiện dừng, bất biến không lặp ô, cách cắt nhánh, phân tích độ phức tạp và khi nào phải dùng BFS thay cho backtracking.

## 1. Mô hình lưới và luật di chuyển

Một lưới hình chữ nhật có R hàng, C cột. Ô `(r,c)` dùng chỉ số từ 0, hợp lệ khi:

\[
0 \le r < R,\qquad 0 \le c < C.
\]

Trong bài này, mọi bước chỉ đi theo **bốn hướng chung cạnh**:

| Hướng | dr | dc |
| --- | ---: | ---: |
| Lên | −1 | 0 |
| Phải | 0 | +1 |
| Xuống | +1 | 0 |
| Trái | 0 | −1 |

Có thể biểu diễn `DR={-1,0,1,0}`, `DC={0,1,0,-1}`; khi thử hướng d thì ô kế tiếp là `(r+DR[d],c+DC[d])`.

Mỗi bước phải được kiểm tra: ô mới nằm trong lưới, không phải tường (nếu có), chưa bị dùng trên đường hiện tại, và có ký tự thích hợp (nếu tìm từ). **Kiểm tra biên trước khi đọc** `board[r][c]`.

**Không tự cho phép đi chéo.** Nếu đề nói đi tám hướng, phải bổ sung `(-1,-1),(-1,1),(1,-1),(1,1)`. Kết quả, số nhánh và độ phức tạp thay đổi. Những biến thể đi vòng mép, nhảy qua ô, trọng số hoặc được lặp ô cũng phải có đặc tả riêng.

Hai dạng lưới dùng trong ví dụ:
- **Lưới ký tự:** mọi ô mang một `char`; hàm tìm từ chỉ kiểm tra ký tự đúng theo thứ tự.
- **Lưới đường đi:** `'#'` là tường; mọi ký tự khác, kể cả `'.'`, `'S'`, `'T'`, đều được xem là ô đi được. Điểm đầu và đích được truyền bằng tọa độ.

Các hàng phải có cùng số cột. Lưới không hình chữ nhật có thể gây lỗi khi dùng chung một bảng visited hoặc tính giới hạn cột.

## 2. Tư duy chọn – thử – hoàn tác

Bất biến chính của DFS backtracking là:

> `visited[r][c]=true` nếu và chỉ nếu ô `(r,c)` nằm trên **nhánh đang thử**; `path` chứa dãy tọa độ của chính nhánh ấy.

Mẫu cơ bản:

~~~text
dfs(current):
    nếu current ngoài biên / là tường / đã visited:
        return thất bại

    đánh dấu visited[current] = true
    thêm current vào path

    nếu đã tới điều kiện hoàn thành:
        found = true
    ngược lại:
        thử các ô kề hợp lệ, cập nhật found

    bỏ đánh dấu visited[current]
    nếu nhánh không thành công:
        bỏ current khỏi path
    return found
~~~

**Phải hoàn tác visited khi quay lui.** Nếu một nhánh đã dùng ô X rồi thất bại, một nhánh khác vẫn có thể đi qua X với tập ô đã dùng khác. Đánh dấu X vĩnh viễn sẽ làm mất nghiệm.

**Không hoàn tác quá sớm.** Nếu bỏ visited trước khi thử ô kế, bước tiếp theo có thể quay về ngay ô trước và tạo đường lặp.

**Giữ đường thành công:** nếu cần trả danh sách tọa độ, giữ path khi found=true, chỉ xóa phần tử khỏi path nếu nhánh thất bại. Có thể dọn visited ở mọi lối thoát mà không ảnh hưởng danh sách path.

### Vì sao khác visited của BFS?

Trong bài **đường đi ngắn nhất không trọng số**, BFS đánh dấu một ô khi đã phát hiện lần đầu, vì lần ấy đã cho số bước ngắn nhất tới ô. Không cần xét lại ô qua đường dài hơn nên visited có thể giữ vĩnh viễn.

Trong bài **đếm mọi đường đơn**, hai đường khác nhau đến cùng một ô có thể có tập visited khác nhau, dẫn tới các đường tiếp diễn khác nhau. Vì vậy visited vĩnh viễn không phù hợp. Memo theo `(r,c)` hay `(r,c,index)` cũng có thể sai nếu bỏ thông tin tập ô đã dùng.

## 3. Bài toán A: tìm từ trên ma trận

Cho ma trận ký tự và chuỗi `word` dài L. Cần tìm một dãy L ô khác nhau, ký tự lần lượt tạo đúng từ, hai ô liên tiếp kề bốn hướng.

Ví dụ:

~~~text
      c0 c1 c2 c3
r0     A  B  C  E
r1     S  F  C  S
r2     A  D  E  E
~~~

Từ `ABCCED` có đường:

~~~text
(0,0)->(0,1)->(0,2)->(1,2)->(2,2)->(2,1)
  A      B      C      C      E      D
~~~

Từ `SEE` có đường:

~~~text
(1,3)->(2,3)->(2,2)
  S      E      E
~~~

Nhưng từ `ABCB` **không có đường hợp lệ**. Nếu lấy lại B ở `(0,1)` sau khi đã dùng nó trước đó, ta đã **lặp một ô**, vi phạm đề bài.

### Trạng thái DFS

Một lời gọi có thể là `dfsWord(r,c,index)`:
- `(r,c)`: tọa độ ô đang định dùng.
- `index`: vị trí trong từ cần ghép.
- `visited`: các ô đã dùng trong tiền tố đường.
- `path`: đường tọa độ làm chứng cứ.

Bất biến: trước khi xử lý `word[index]`, các ô đang có trong path khác nhau, kề nhau theo luật, và ký tự trên chúng tạo đúng `word[0..index-1]`.

Thuật toán:
1. Duyệt từng ô bắt đầu theo thứ tự hàng rồi cột.
2. Nếu ô ngoài biên, đã dùng, hoặc ký tự không khớp `word[index]`, trả false.
3. Nếu khớp, đánh dấu visited, thêm ô vào path.
4. Nếu đã ghép **ký tự cuối**, found=true.
5. Nếu chưa, thử bốn ô kề với `index+1`.
6. Dọn visited; nếu thất bại thì bỏ ô cuối khỏi path.
7. Dừng ở nghiệm đầu nếu chỉ cần một đường; nếu không có nghiệm thì trả null.

**Từ rỗng:** chương trình trong bài quy ước từ rỗng có đường rỗng `[]`; trả `null` mới mang nghĩa không có nghiệm. Nếu đề không cho từ rỗng, hãy từ chối thay vì ngầm dùng quy ước khác.

**Lưới rỗng:** không thể ghép từ không rỗng. Với lưới chỉ có một ô A, từ A có nghiệm một ô, còn AA không có nghiệm vì không được lặp tọa độ. Nhiều ô khác nhau có cùng chữ A vẫn có thể cùng tham gia một đường.

### Cắt nhánh có chứng minh

- Nếu `L>R*C`, từ dài hơn số ô nên không thể ghép khi mỗi ô dùng tối đa một lần.
- Nếu từ cần nhiều bản sao một ký tự hơn tổng số ô chứa ký tự đó, không có nghiệm.
- Nếu ô kề không mang ký tự tiếp theo, bỏ qua nhánh ấy.
- Nếu ký tự cuối rất hiếm, có thể thử từ đảo ngược để giảm số điểm bắt đầu; trên lưới vô hướng, đường có thể đảo ngược, nhưng quy tắc ưu tiên đường trả về có thể thay đổi.

Không được cắt nhánh chỉ vì “đường này có vẻ không hợp lý”. Mọi phép cắt phải loại một điều kiện **không thể dẫn đến nghiệm**.

### Phức tạp

Gọi `N=R*C`. Có tối đa N điểm bắt đầu. Từ mỗi điểm, bước đầu có tối đa bốn hướng, những bước sau không được quay lại ô trước nên số hướng có thể tiếp tục thường không quá ba. Một cận thô là **O(N·4^L)**; với L≥2 có thể xét dạng `O(N·4·3^(L−2))` cho số nhánh. Trường hợp thực tế có thể nhanh nhờ kiểm tra ký tự, nhưng không bảo đảm O(N).

Bảng visited chiếm O(N); stack đệ quy và path dài tối đa L nên thêm O(L), tổng **O(N+L)** bộ nhớ phụ.

## 4. Bài toán B: tìm một đường đơn từ S đến T

Đường đơn là dãy ô:

\[
v_0=S,\ v_1,\ldots,v_k=T
\]

thỏa: mọi ô đi được, hai ô liên tiếp kề cạnh, không ô nào xuất hiện hai lần. **Số bước** là k; **số ô** là k+1.

Lưới có tường ở tâm:

~~~text
S . .
. # .
. . T
~~~

S=(0,0), T=(2,2). Theo thứ tự hướng **lên → phải → xuống → trái**, DFS tìm đường đầu:

~~~text
(0,0)->(0,1)->(0,2)->(1,2)->(2,2)
~~~

Có 5 ô, **4 bước**. Đường khác đi bên trái và phía dưới:

~~~text
(0,0)->(1,0)->(2,0)->(2,1)->(2,2)
~~~

Có đúng **2 đường đơn** trong lưới này.

**S=T:** nếu cùng là ô đi được, có một đường một ô, **0 bước**. Nếu ô đó là tường thì không có đường.

### Tìm một đường

DFS chọn ô mới nếu không phải tường và chưa visited. Nếu đã đến T, thành công. Nếu chưa, thử bốn ô kề. Khi nhánh thất bại, xóa ô cuối path; luôn dọn visited khi thoát lời gọi. Với bài tồn tại một đường, **dừng ở nghiệm đầu** là đúng.

### Đếm mọi đường

Nếu hỏi số đường đơn, đổi hàm DFS thành số lượng:

~~~text
count(r,c):
    nếu ngoài biên / tường / visited: return 0
    nếu đang ở T: return 1

    visited[r][c] = true
    total = 0
    với mỗi ô kề:
        total += count(next)
    visited[r][c] = false
    return total
~~~

**Gặp T phải dừng ngay** trong nhánh đó, vì đường hoàn thành khi tới đích. Khi thoát nhánh chưa tới T, undo visited cho các nhánh khác. Không return toàn bộ ngay khi gặp nghiệm đầu tiên nếu cần **đếm hết**.

Khi liệt kê đường, thay phép cộng bằng **lưu bản sao path** lúc gặp T. Không lưu cùng một đối tượng `ArrayList` mutable rồi tiếp tục quay lui, vì kết quả đã lưu có thể thay đổi.

### Độ phức tạp

Với V ô đi được, một đường đơn có tối đa V ô, cần O(RC) cho visited và stack/path. Nhưng số đường đơn có thể tăng theo **hàm mũ** theo kích thước lưới, nên bài đếm/liệt kê đường đơn không được hứa chạy O(RC). Nếu cho phép lặp ô mà không có giới hạn bước, việc đếm còn có thể **vô hạn** khi tồn tại chu trình phù hợp.

## 5. DFS đầu tiên không bảo đảm ngắn nhất

Xét lưới mở:

~~~text
S . .
. . .
T . .
~~~

S=(0,0), T=(2,0). DFS ưu tiên lên, phải, xuống, trái có thể tìm đường đầu:

~~~text
(0,0)->(0,1)->(0,2)->(1,2)->(2,2)->(2,1)->(1,1)->(1,0)->(2,0)
~~~

Đường này dài **8 bước**. Nhưng đường:

~~~text
(0,0)->(1,0)->(2,0)
~~~

chỉ dài **2 bước**.

DFS vẫn đúng khi yêu cầu **tìm một đường hợp lệ**, nhưng sai nếu tuyên bố đó là **đường ngắn nhất**.

### BFS khi yêu cầu số bước tối thiểu

Với lưới không trọng số:
1. Đặt `dist[S]=0`, các ô khác chưa phát hiện là −1.
2. Đưa S vào hàng đợi.
3. Lấy ô đầu, xét các ô kề không phải tường và chưa phát hiện.
4. Gán `dist[next]=dist[current]+1` và thêm next vào hàng đợi.
5. Khi lấy T ra, `dist[T]` là số bước ngắn nhất; nếu không tới được, trả −1.

BFS đi theo các lớp khoảng cách tăng dần; một ô được phát hiện lần đầu đã có khoảng cách ngắn nhất, nên visited có thể giữ nguyên. Thời gian và bộ nhớ **O(RC)** trên lưới bốn hướng.

Nếu cạnh có **trọng số không âm không đồng đều**, có thể phải dùng Dijkstra thay cho BFS. Nếu cần **đếm tất cả đường đơn**, BFS shortest không giải thay được.

## 6. Chứng minh tính đúng

**Bất biến:** path chỉ chứa các ô hợp lệ, khác nhau, kề nhau; với bài tìm từ, ký tự trên chúng tạo đúng tiền tố đã ghép.

**Bước chọn:** chỉ thêm ô nằm trong lưới, thỏa ký tự/tường và chưa visited. Do đó bất biến được bảo toàn.

**Đủ hướng:** mọi đường hợp lệ tiếp diễn bằng một trong những ô kề mà DFS sẽ thử. Nếu tồn tại nghiệm, chuỗi hướng của nó nằm trong cây tìm kiếm; DFS không bỏ sót khi đã thử mọi nhánh hoặc có thể dừng sớm vì đã tìm một nghiệm khác.

**Hoàn tác:** sau nhánh thất bại, xóa tọa độ đã thêm và bỏ dấu visited, đưa trạng thái về đúng lúc trước lựa chọn. Vì thế những nhánh độc lập được đánh giá công bằng.

**Dừng:** mỗi bước chọn một ô mới; không thể có đường dài hơn tổng số ô nếu cấm lặp. Điều kiện cuối từ hoặc đến T là trạng thái hoàn chỉnh. Với bài đếm, mỗi đường đơn được cộng đúng một lần tại lá gặp T.

Đây là chứng minh cho tính **hợp lệ và đầy đủ** của thuật toán, không phải chứng minh rằng đường đầu tiên ngắn nhất.

## 7. Chương trình Java 17 độc lập

Chương trình gồm tìm từ, tìm một đường đơn, đếm đường đơn và BFS. Kết quả dùng `List<Cell>`; `null` biểu diễn không có đường, còn `[]` với từ rỗng mang nghĩa đường ghép rỗng hợp lệ. Lưới ký tự không bị sửa khi tìm kiếm.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.StringJoiner;

public class GridBacktrackingDemo {
    record Cell(int r, int c) {}

    static final int[] DR = {-1, 0, 1, 0};
    static final int[] DC = {0, 1, 0, -1};

    static int columns(char[][] grid) {
        if (grid == null) throw new IllegalArgumentException("Null grid");
        int cols = grid.length == 0 ? 0
                : (grid[0] == null ? -1 : grid[0].length);
        for (char[] row : grid) {
            if (row == null || row.length != cols) {
                throw new IllegalArgumentException("Ragged grid");
            }
        }
        return cols;
    }

    static boolean inside(char[][] grid, int r, int c) {
        return r >= 0 && r < grid.length
                && c >= 0 && c < grid[r].length;
    }

    static boolean open(char[][] grid, int r, int c) {
        return inside(grid, r, c) && grid[r][c] != '#';
    }

    static String show(List<Cell> path) {
        if (path == null) return "none";
        if (path.isEmpty()) return "[]";
        StringJoiner out = new StringJoiner("->");
        for (Cell p : path) {
            out.add("(" + p.r() + "," + p.c() + ")");
        }
        return out.toString();
    }

    static List<Cell> findWord(char[][] board, String word) {
        int cols = columns(board);
        if (word == null) throw new IllegalArgumentException("Null word");
        if (word.isEmpty()) return List.of();
        int rows = board.length;
        if (rows == 0 || cols == 0
                || word.length() > (long) rows * cols) return null;

        boolean[][] visited = new boolean[rows][cols];
        List<Cell> path = new ArrayList<>();
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (dfsWord(board, word, r, c, 0, visited, path)) {
                    return List.copyOf(path);
                }
            }
        }
        return null;
    }

    static boolean dfsWord(
            char[][] board, String word, int r, int c, int index,
            boolean[][] visited, List<Cell> path) {
        if (!inside(board, r, c) || visited[r][c]
                || board[r][c] != word.charAt(index)) return false;

        visited[r][c] = true;
        path.add(new Cell(r, c));
        boolean found = index == word.length() - 1;

        if (!found) {
            for (int d = 0; d < 4; d++) {
                if (dfsWord(board, word, r + DR[d], c + DC[d],
                        index + 1, visited, path)) {
                    found = true;
                    break;
                }
            }
        }

        visited[r][c] = false;
        if (!found) path.remove(path.size() - 1);
        return found;
    }

    static void endpoints(char[][] grid, Cell start, Cell goal) {
        columns(grid);
        if (start == null || goal == null
                || !inside(grid, start.r(), start.c())
                || !inside(grid, goal.r(), goal.c())) {
            throw new IllegalArgumentException("Invalid endpoints");
        }
    }

    static List<Cell> firstPath(
            char[][] grid, Cell start, Cell goal) {
        endpoints(grid, start, goal);
        if (!open(grid, start.r(), start.c())
                || !open(grid, goal.r(), goal.c())) return null;

        boolean[][] visited =
                new boolean[grid.length][grid[0].length];
        List<Cell> path = new ArrayList<>();
        if (dfsPath(grid, start.r(), start.c(),
                goal, visited, path)) {
            return List.copyOf(path);
        }
        return null;
    }

    static boolean dfsPath(
            char[][] grid, int r, int c, Cell goal,
            boolean[][] visited, List<Cell> path) {
        if (!open(grid, r, c) || visited[r][c]) return false;

        visited[r][c] = true;
        path.add(new Cell(r, c));
        boolean found = r == goal.r() && c == goal.c();

        if (!found) {
            for (int d = 0; d < 4; d++) {
                if (dfsPath(grid, r + DR[d], c + DC[d],
                        goal, visited, path)) {
                    found = true;
                    break;
                }
            }
        }
        visited[r][c] = false;
        if (!found) path.remove(path.size() - 1);
        return found;
    }

    static long countPaths(
            char[][] grid, Cell start, Cell goal) {
        endpoints(grid, start, goal);
        if (!open(grid, start.r(), start.c())
                || !open(grid, goal.r(), goal.c())) return 0;

        boolean[][] visited =
                new boolean[grid.length][grid[0].length];
        return dfsCount(grid, start.r(), start.c(), goal, visited);
    }

    static long dfsCount(
            char[][] grid, int r, int c, Cell goal,
            boolean[][] visited) {
        if (!open(grid, r, c) || visited[r][c]) return 0;
        if (r == goal.r() && c == goal.c()) return 1;

        visited[r][c] = true;
        long total = 0;
        for (int d = 0; d < 4; d++) {
            total = Math.addExact(total, dfsCount(
                    grid, r + DR[d], c + DC[d], goal, visited));
        }
        visited[r][c] = false;
        return total;
    }

    static int shortestSteps(
            char[][] grid, Cell start, Cell goal) {
        endpoints(grid, start, goal);
        if (!open(grid, start.r(), start.c())
                || !open(grid, goal.r(), goal.c())) return -1;

        int[][] dist = new int[grid.length][grid[0].length];
        for (int[] row : dist) Arrays.fill(row, -1);
        ArrayDeque<Cell> queue = new ArrayDeque<>();
        queue.add(start);
        dist[start.r()][start.c()] = 0;

        while (!queue.isEmpty()) {
            Cell cur = queue.remove();
            if (cur.equals(goal)) return dist[cur.r()][cur.c()];
            for (int d = 0; d < 4; d++) {
                int r = cur.r() + DR[d];
                int c = cur.c() + DC[d];
                if (open(grid, r, c) && dist[r][c] < 0) {
                    dist[r][c] = dist[cur.r()][cur.c()] + 1;
                    queue.add(new Cell(r, c));
                }
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        char[][] letters = {
            {'A', 'B', 'C', 'E'},
            {'S', 'F', 'C', 'S'},
            {'A', 'D', 'E', 'E'}
        };
        System.out.println("wordABCCED="
                + show(findWord(letters, "ABCCED")));
        System.out.println("wordSEE="
                + show(findWord(letters, "SEE")));
        System.out.println("wordABCB="
                + show(findWord(letters, "ABCB")));
        System.out.println("emptyWord="
                + show(findWord(letters, "")));

        char[][] ring = {
            {'S', '.', '.'},
            {'.', '#', '.'},
            {'.', '.', 'T'}
        };
        Cell ringStart = new Cell(0, 0);
        Cell ringGoal = new Cell(2, 2);
        List<Cell> rpath = firstPath(ring, ringStart, ringGoal);
        System.out.println("ringPath=" + show(rpath)
                + " steps=" + (rpath.size() - 1));
        System.out.println("ringCount="
                + countPaths(ring, ringStart, ringGoal));
        System.out.println("ringBFS="
                + shortestSteps(ring, ringStart, ringGoal));

        char[][] openGrid = {
            {'S', '.', '.'},
            {'.', '.', '.'},
            {'T', '.', '.'}
        };
        Cell openStart = new Cell(0, 0);
        Cell openGoal = new Cell(2, 0);
        List<Cell> opath = firstPath(openGrid, openStart, openGoal);
        System.out.println("openPath=" + show(opath)
                + " steps=" + (opath.size() - 1));
        System.out.println("openCount="
                + countPaths(openGrid, openStart, openGoal));
        System.out.println("openBFS="
                + shortestSteps(openGrid, openStart, openGoal));

        char[][] blocked = {{'S', '#', 'T'}};
        Cell blockedStart = new Cell(0, 0);
        Cell blockedGoal = new Cell(0, 2);
        System.out.println("blockedPath="
                + show(firstPath(blocked, blockedStart, blockedGoal)));
        System.out.println("blockedCount="
                + countPaths(blocked, blockedStart, blockedGoal));
        System.out.println("blockedBFS="
                + shortestSteps(blocked, blockedStart, blockedGoal));
    }
}
~~~

Lưu tệp **GridBacktrackingDemo.java**. Với **JDK 17 trở lên**, chạy:

~~~bash
javac GridBacktrackingDemo.java
java GridBacktrackingDemo
~~~

**Đầu ra:**

~~~text
wordABCCED=(0,0)->(0,1)->(0,2)->(1,2)->(2,2)->(2,1)
wordSEE=(1,3)->(2,3)->(2,2)
wordABCB=none
emptyWord=[]
ringPath=(0,0)->(0,1)->(0,2)->(1,2)->(2,2) steps=4
ringCount=2
ringBFS=4
openPath=(0,0)->(0,1)->(0,2)->(1,2)->(2,2)->(2,1)->(1,1)->(1,0)->(2,0) steps=8
openCount=11
openBFS=2
blockedPath=none
blockedCount=0
blockedBFS=-1
~~~

### Giải thích cách cài

- **`findWord`:** trả một `List<Cell>` khi có đường khớp, hoặc `null` khi không có. `[]` nghĩa là **khớp từ rỗng** theo quy ước, nên khi kiểm tra tồn tại phải dùng `result != null`.
- **`dfsWord` và `dfsPath`:** luôn bỏ dấu visited trước khi thoát lời gọi; nếu found, giữ path làm chứng cứ, nếu thất bại thì xóa phần tử cuối.
- **`List.copyOf(path)`:** tạo danh sách kết quả độc lập với `ArrayList` mutable nội bộ, tránh thay đổi kết quả sau khi đã trả về.
- **`countPaths`:** không lưu tất cả đường, chỉ cộng số nghiệm. `Math.addExact` báo lỗi khi vượt miền long, nhưng không ngăn bùng nổ số nhánh.
- **`shortestSteps`:** dùng `ArrayDeque` và mảng dist, lần đầu tới T theo BFS là khoảng cách ngắn nhất trong mô hình không trọng số.
- **`Cell`:** record Java 17 so sánh theo tọa độ, vì vậy `cur.equals(goal)` đúng.
- **`columns`:** từ chối lưới null hoặc không chữ nhật; `endpoints` từ chối tọa độ ngoài biên. S/T là tường được xem là **không có đường**, không phải điểm đi được.
- **Đường ghép từ** không có khái niệm tường trong code; ký tự `'#'` cũng có thể được tìm nếu có trong từ.

Chương trình dùng `char` và `String.charAt`, tức **đơn vị UTF-16**. Nếu đề định nghĩa mỗi ô chứa một code point ngoài BMP hoặc một grapheme nhiều code point, cần mô hình rộng hơn `char[][]` và cách duyệt `String` tương ứng.

## 8. Kiểm thử và xác minh đường chứng cứ

Một đường mà thuật toán trả về phải được **kiểm tra riêng**, không chỉ tin vào boolean:
- Các tọa độ nằm trong lưới.
- Ô đầu đúng S/đúng ký tự đầu.
- Ô cuối đúng T/đúng ký tự cuối.
- Mọi bước kề cạnh, khoảng cách Manhattan giữa hai ô liên tiếp bằng 1.
- Không tọa độ nào lặp lại.
- Không có ô tường trên đường đi.
- Với bài tìm từ, ký tự ở mỗi bước đúng `word[index]`.

Có thể làm oracle trên lưới rất nhỏ bằng **bitmask các ô đã sử dụng** thay cho `boolean[][] visited`. Mỗi lần gọi đệ quy, truyền bitmask mới; các đường có bitmask khác nhau là những lịch sử độc lập.

Một tập test minh họa:
- Mọi lưới 2×3 mà mỗi ô là A hoặc B: `2^6=64` lưới.
- Mọi từ độ dài 0..4 trên {A,B}: `1+2+4+8+16=31` từ.
- Tổng **64×31=1.984** cặp lưới/từ để đối chiếu tồn tại và tính hợp lệ đường ghép.
- Mọi 64 cấu hình tường trên lưới 2×3, với S=(0,0), T=(1,2), để đối chiếu số đường đơn, đường DFS hợp lệ và số bước BFS với oracle vét cạn.

Các phép kiểm thử này hữu ích để phát hiện lỗi visited, đếm sai hoặc ký tự/biên không hợp lệ. Nhưng **kiểm thử không thay chứng minh** trên mọi lưới hợp lệ; phần chứng minh phải dựa vào bất biến và tính đầy đủ của việc duyệt các lựa chọn.

## 9. Trường hợp biên

| Trường hợp | Kết quả hoặc quy ước |
| --- | --- |
| Lưới rỗng, từ không rỗng | Không có đường khớp |
| Từ rỗng | Ví dụ trả `[]` |
| Từ dài hơn số ô | Không có nghiệm khi cấm lặp ô |
| Một ô A, từ A | Có đường một ô |
| Một ô A, từ AA | Không có vì phải dùng lại ô |
| Hai ô A kề nhau, từ AA | Có đường hai tọa độ khác nhau |
| Chỉ kề chéo | Không hợp lệ theo bốn hướng |
| S và T trùng trên ô mở | Một đường đơn, 0 bước |
| S và T trùng trên ô tường | Không có đường |
| S/T ngoài lưới | Input không hợp lệ |
| Lưới `S#T` một hàng | Không có đường |
| Không có đường | DFS trả null, count=0, BFS=−1 |
| Có nhiều đường | DFS tìm một, count phải duyệt đủ |
| Lưới mở lớn | Đếm đường có thể hàm mũ và vượt long |
| Lưới có hàng độ dài khác nhau | Cần xử lý riêng; code từ chối |

Với đề khác, cách xử lý từ rỗng, tường, dấu đặc biệt, chỉ số hay cho phép đường đi độ dài 0 có thể thay đổi; phải công bố quy ước trước.

## 10. Những lỗi thường gặp

1. **Không kiểm tra tọa độ trước khi đọc ô**, gây lỗi ngoài mảng.
2. **Không undo visited** sau một nhánh không thành công, làm mất những đường hợp lệ trong nhánh khác.
3. **Undo quá sớm**, khiến bước con quay về ô cha và lặp ô.
4. **Không undo path** trên nhánh thất bại, tạo đường có ô dư.
5. **Xóa path cả khi đã thành công**, làm mất đường chứng cứ.
6. **Không tăng index** khi tìm ký tự kế tiếp, hoặc không có base case ký tự cuối.
7. **Cấm lặp ký tự thay vì tọa độ**, loại sai từ chứa ký tự trùng.
8. **Tự ý đi chéo** trong bài bốn hướng, tạo nghiệm ảo.
9. **Dừng tại đường đầu** trong bài đếm/liệt kê mọi đường.
10. **Lưu tham chiếu path mutable** khi liệt kê, khiến các đường lưu bị thay đổi sau backtracking.
11. **Nhầm số ô với số bước**: một đường có k+1 ô nhưng chỉ k bước.
12. **Coi DFS đầu là ngắn nhất**, bị phản bác bởi lưới mở 3×3.
13. **Dùng visited BFS vĩnh viễn để đếm đường đơn**, làm mất những lịch sử khác nhau.
14. **Memo chỉ theo ô hoặc ô+index** mà không xét tập visited, gộp sai trạng thái.
15. **Tới T vẫn đi tiếp để đếm thêm**, không đúng định nghĩa đường kết thúc tại đích.
16. **Dùng kiểu đếm nhỏ** khi số đường quá lớn, dẫn tới tràn.
17. **Gọi mọi bài trên lưới là O(RC)** dù đang liệt kê số lượng đường theo hàm mũ.
18. **Cắt nhánh theo trực giác không chứng minh**, có thể bỏ mất nghiệm.
19. **Không phân biệt lưới ký tự và lưới tường**, xử lý sai dấu đặc biệt.
20. **Đồng nhất `char` với một grapheme Unicode tùy ý**, không đúng ngoài phạm vi mô hình ví dụ.

## 11. Khi nào chọn phương pháp nào?

| Yêu cầu | Giải pháp | Ghi chú |
| --- | --- | --- |
| Có từ xuất hiện theo một đường không lặp ô? | DFS backtracking + index | Tồn tại nghiệm |
| Trả một đường ghép từ | DFS + path | Dừng ở nghiệm đầu |
| Đếm/liệt kê mọi đường ghép từ | DFS không dừng sớm | Sao chép path ở mỗi nghiệm |
| Có đường S→T không lặp ô? | DFS hoặc BFS | Một đường là đủ |
| Trả một đường đơn S→T | DFS backtracking | Không bảo đảm ngắn nhất |
| Đếm mọi đường đơn S→T | DFS backtracking đếm nhánh | Có thể hàm mũ |
| Ít bước nhất trên lưới không trọng số | BFS | O(RC) |
| Ít chi phí nhất với cạnh trọng số không âm | Dijkstra | Không dùng BFS thường khi chi phí khác nhau |

Trước khi code, hãy xác định **luật kề**, **điều kiện lặp ô**, **định nghĩa nghiệm**, **được dừng sớm không**, và **visited mang nghĩa theo đường hay toàn cục**.

## 12. Bài tập tự luyện có đáp án

**Bài 1.** Trên lưới:

~~~text
A B
C D
~~~

Có ghép được `ABDC` bằng bốn hướng không?

*Đáp án:* Có, theo `(0,0)A→(0,1)B→(1,1)D→(1,0)C`.

**Bài 2.** Một ô A có ghép được từ AA không? Nếu có hai ô A kề nhau thì sao?

*Đáp án:* Một ô A không đủ vì không được lặp tọa độ; hai ô A kề nhau thì có thể.

**Bài 3.** Hai ô A=(0,0), B=(1,1) chỉ kề chéo. Có ghép AB theo bốn hướng không?

*Đáp án:* Không; nếu bài cho tám hướng thì được.

**Bài 4.** Vì sao phải bỏ visited khi một nhánh không có nghiệm?

*Đáp án:* Vì nhánh khác có thể dùng cùng ô với tập ô đã đi qua khác; visited chỉ cấm lặp trên đường hiện tại.

**Bài 5.** Lưới `S../.#./..T` có bao nhiêu đường đơn S→T?

*Đáp án:* Có 2 đường theo hai phía vòng ngoài, mỗi đường dài 4 bước.

**Bài 6.** Lưới mở 3×3 với S=(0,0), T=(2,0), DFS ưu tiên lên/phải/xuống/trái có thể tìm đường đầu dài bao nhiêu? BFS cho số bước ngắn nhất là bao nhiêu?

*Đáp án:* DFS đầu 8 bước; BFS chỉ 2 bước.

**Bài 7.** Nếu S=T tại một ô đi được, có bao nhiêu đường đơn và bao nhiêu bước?

*Đáp án:* Một đường chỉ gồm ô đó, 0 bước.

**Bài 8.** Từ dài 10 ký tự trên lưới 3×3 (9 ô), không được lặp ô, có cần chạy DFS không?

*Đáp án:* Không. Số ô nhỏ hơn độ dài từ nên vô nghiệm ngay.

**Bài 9.** Bài yêu cầu đếm toàn bộ đường đơn. Tại sao không thể return ngay khi gặp đường đầu?

*Đáp án:* Vì vẫn còn những đường khác ở các nhánh chưa duyệt; gặp T chỉ đóng góp 1 cho nhánh hiện tại.

**Bài 10.** Vì sao không thể khẳng định đếm đường đơn trên lưới là O(RC)?

*Đáp án:* Số đường có thể tăng theo hàm mũ; nhiều đường chia sẻ ô nhưng có visited theo lịch sử khác nhau.

**Bài 11.** Nếu cho phép đi lại ô và không giới hạn bước, điều gì có thể xảy ra với bài đếm đường?

*Đáp án:* Có thể có vô hạn đường từ S tới T khi có một chu trình có thể lặp trước khi đến T; cần giới hạn hoặc mô hình khác.

**Bài 12.** Muốn liệt kê mọi đường ghép từ, cần thay gì trong code tìm một từ?

*Đáp án:* Không return sớm, sao chép path mỗi khi đã ghép đủ từ, tiếp tục thử các nhánh và undo visited/path đúng.

## Tổng kết

**Tìm từ hoặc đường đi trên lưới bằng quay lui** xoay quanh bất biến đơn giản nhưng quan trọng: path là đường hiện tại, visited chỉ đánh dấu những ô trên đường đó, và sau mỗi nhánh phải **hoàn tác**. Với tìm từ, cần thêm chỉ số ký tự; với đếm đường, cần khám phá toàn bộ nhánh; với đường ngắn nhất trên lưới không trọng số, nên dùng **BFS**.

Tính đúng đến từ việc chỉ chọn bước hợp lệ, thử đầy đủ các hướng, không lặp ô và khôi phục trạng thái. Tính hiệu quả đến từ phát hiện trường hợp vô nghiệm sớm, cắt nhánh có chứng minh và lựa chọn đúng thuật toán theo **mục tiêu của đề bài**.
