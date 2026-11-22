# Duyệt lưới và đồ thị được sinh ngầm

> **Chủ đề:** Computer Science Algorithms → Duyệt đồ thị.  
> **Mục tiêu:** Nhìn một lưới hoặc bài toán trạng thái như một **đồ thị không cần liệt kê sẵn cạnh**; tự sinh hàng xóm hợp lệ, chọn đúng BFS, DFS, BFS nhiều nguồn hoặc 0-1 BFS; đánh dấu đã thăm, tìm đường ngắn nhất và khôi phục đường đi; tránh nhầm quan hệ kề 4/8 hướng, nhầm trọng số, bùng nổ không gian trạng thái và các lỗi chỉ số. Mã hoàn chỉnh dùng **Java 17+**.

## 1. Đồ thị không nhất thiết được cho bằng danh sách cạnh

Một đồ thị có các đỉnh `V` và các cạnh `E`. Trong bài quen thuộc, đầu vào liệt kê các cạnh hoặc một danh sách kề. Nhưng trong nhiều bài, các đỉnh và cạnh **được định nghĩa bằng quy tắc**:

- Trong lưới, mỗi ô đi được là một đỉnh. Từ ô `(r,c)`, ta có thể thử đi lên, xuống, trái, phải.
- Trong trò chơi khóa số, mỗi cấu hình bốn bánh xe là một đỉnh. Một thao tác xoay một bánh tạo một cạnh.
- Trong puzzle trượt ô, mỗi cách sắp xếp hợp lệ của các ô là một đỉnh. Đổi chỗ ô trống với một ô kề tạo một cạnh.
- Trong đường đi cần thu thập chìa khóa, một trạng thái có thể gồm **tọa độ và tập chìa khóa đang có**, không chỉ tọa độ.
- Trong bài chuyển đổi chuỗi, một chuỗi là một đỉnh. Thay một ký tự theo luật cho trước tạo hàng xóm.

Các bài này gọi là **đồ thị được sinh ngầm** (*implicit graph*): ta biết cách tạo cạnh từ một đỉnh nhưng không cần dựng toàn bộ tập cạnh trước khi duyệt.

**Nguyên tắc cốt lõi:** thuật toán BFS/DFS vẫn là duyệt đồ thị; điều thay đổi là cách cài `neighbors(state)`.

### 1.1. Vì sao không tạo danh sách kề cho mọi ô?

Với lưới `R×C`, có tối đa `R·C` ô; nếu mỗi ô có không quá bốn hàng xóm thì số cạnh có hướng để kiểm tra là tối đa `4RC`. Có thể tạo danh sách kề, nhưng thường không cần:

```text
for mỗi hướng trong {xuống, phải, lên, trái}:
    nr = r + dr[hướng]
    nc = c + dc[hướng]
    if tọa độ nằm trong lưới và ô có thể đi:
        xử lý hàng xóm (nr, nc)
```

Không lưu danh sách cạnh có thể giảm bộ nhớ và tránh khởi tạo một cấu trúc trung gian rất lớn. Đổi lại, mỗi khi mở rộng một trạng thái, ta phải **tính lại hàng xóm**.

### 1.2. Hình dung nút và cạnh cho đúng

Với quy tắc di chuyển bốn hướng, từ ô `S`:

```text
      ↑
      |
  ←   S   →
      |
      ↓
```

Mỗi mũi tên chỉ trở thành **cạnh hợp lệ** khi điểm đến nằm trong biên lưới và không bị cản. Nếu luật yêu cầu chỉ được di chuyển theo một chiều, đi xuống dốc, mở cửa bằng chìa khóa hoặc tốn năng lượng, đồ thị có thể **có hướng** hoặc cần trạng thái nhiều thành phần.

**Đừng đồng nhất “kề về tọa độ” với “có cạnh trong bài”.** Cạnh chỉ tồn tại khi **toàn bộ điều kiện di chuyển** được thỏa.

## 2. Biểu diễn lưới và sinh hàng xóm

Một lưới `R` hàng, `C` cột thường đánh chỉ số:

`0 <= r < R`, `0 <= c < C`.

Với bốn hướng:

```text
dr = [ 1,  0, -1,  0]
dc = [ 0,  1,  0, -1]
```

Tức là: **xuống, phải, lên, trái**. Thứ tự hướng không đổi độ dài đường ngắn nhất khi tất cả cạnh cùng chi phí, nhưng có thể thay đổi **đường đi tối ưu cụ thể** được khôi phục nếu có nhiều đường dài bằng nhau.

### 2.1. Kiểm tra biên và điều kiện ô

Với một hàng xóm `(nr,nc)`, phải kiểm tra:

1. `0 <= nr < R`.
2. `0 <= nc < C`.
3. Ô đích không phải chướng ngại (`#` trong các ví dụ ASCII).
4. Điều kiện bổ sung của bài: ô có thể đi vào, có chìa khóa, thời điểm hợp lệ, chưa bị chặn bởi vật thể khác, v.v.
5. Nếu cần tránh thăm lại, trạng thái đích chưa được xử lý theo chính sách của thuật toán.

Kiểm tra biên **trước khi truy cập** `grid[nr][nc]` hoặc `grid[nr].charAt(nc)`, vì Java sẽ ném `ArrayIndexOutOfBoundsException`/`StringIndexOutOfBoundsException` nếu chỉ số sai.

### 2.2. Quan hệ kề bốn hướng và tám hướng

**4-neighbor** chỉ gồm các ô có khoảng cách Manhattan bằng 1:

`(r+1,c), (r-1,c), (r,c+1), (r,c-1)`.

**8-neighbor** còn gồm bốn đường chéo:

`(r±1,c±1)`.

Hai bài có thể cùng đầu vào lưới nhưng **đáp án khác hẳn** chỉ vì định nghĩa hàng xóm. Ví dụ:

```text
.#.
#.#
.#.
```

Nếu `.` là ô đất và `#` là vật cản:

- Theo **4 hướng**, có **5 thành phần liên thông** độc lập.
- Theo **8 hướng**, mọi góc đều nối chéo vào ô chính giữa, nên chỉ có **1 thành phần**.

### 2.3. Đường chéo có được “cắt góc” không?

Trong một số trò chơi/robot, cho đi chéo từ `(r,c)` đến `(r+1,c+1)` **chỉ khi cả hai ô kề bên** `(r+1,c)` và `(r,c+1)` không bị chặn. Quy tắc này gọi nôm na là **không cắt góc**.

Trong các bài đếm vùng nối tám hướng thông thường, cạnh chéo thường được phép **ngay cả khi hai ô kề trục bị chặn**. Phải đọc đề để chọn chính xác mô hình.

Không có một tập `dr/dc` duy nhất đúng cho mọi bài lưới.

### 2.4. Mã hóa tọa độ thành một số nguyên

Khi lưới hình chữ nhật có `C` cột, có thể mã hóa:

`id = r*C + c`.

Giải mã:

`r = id / C`, `c = id % C`.

Điều kiện là `0<=id<R*C` và phép nhân `R*C` **không tràn kiểu chỉ số**. Mã hóa giúp dùng `int[] distance`, `int[] parent`, `boolean[] visited`, `ArrayDeque<Integer>` thay vì tạo nhiều đối tượng `Cell`.

Nếu lưới có **hàng dài ngắn khác nhau** (*jagged grid*), công thức dùng C cố định không còn đúng nếu chưa chuẩn hóa dữ liệu. Các chương trình Java dưới đây yêu cầu lưới hình chữ nhật và kiểm tra điều đó.

## 3. BFS: đường đi ít bước nhất khi mọi cạnh cùng giá

**BFS — Breadth-First Search** thăm các đỉnh theo lớp khoảng cách từ nguồn. Nếu mỗi bước di chuyển có chi phí bằng **1**, lần đầu một đỉnh được đưa vào hàng đợi, độ dài đường đi tìm được tới đó là ngắn nhất.

Cần sử dụng **FIFO queue**, không phải stack.

### 3.1. Bất biến của BFS

Đặt `dist[s]=0` cho nguồn s. Khi xét một đỉnh u có `dist[u]=d`, mỗi hàng xóm chưa phát hiện v nhận:

`dist[v] = d + 1`.

Do các đỉnh ở lớp d được xử lý trước các đỉnh ở lớp d+1, không có đường đi ngắn hơn tới v có thể xuất hiện sau lần phát hiện đầu tiên.

**Điều kiện:** mọi cạnh có **cùng chi phí dương** (trong code là 1). Nếu chi phí khác nhau, BFS ít cạnh nhất không chắc tối ưu tổng chi phí.

### 3.2. Khi nào đánh dấu visited?

**Đánh dấu ngay khi đưa vào queue**, không chờ tới lúc lấy ra.

```text
dist[source] = 0
queue.add(source)

while queue không rỗng:
    u = queue.removeFirst()
    for v trong neighbors(u):
        if dist[v] chưa có:
            dist[v] = dist[u] + 1
            parent[v] = u
            queue.addLast(v)
```

Nếu đợi đến lúc pop rồi mới đánh dấu, cùng một đỉnh có thể bị **nhiều đỉnh cha cùng đưa vào queue**, làm bộ nhớ phình to và khiến `parent` bị ghi đè, nhất là trên lưới có nhiều chu trình.

Ta có thể dùng `dist==-1` để vừa biểu diễn **chưa thăm**, vừa biểu diễn **chưa tìm thấy đường**.

### 3.3. Khôi phục đường đi bằng parent

Khi lần đầu phát hiện v qua u, lưu `parent[v]=u`.

Nếu đích t được phát hiện:

1. Bắt đầu từ t, đi lần lượt `t, parent[t], parent[parent[t]], ...` cho tới nguồn.
2. Đảo thứ tự để có đường đi nguồn → đích.
3. Số bước bằng `dist[t]`.
4. Số ô trong đường đi bằng `dist[t]+1`, kể cả nguồn và đích.

**Nếu t không tới được:** trả `-1` hoặc một trạng thái “không có đường”, không đọc `parent[t]` như thể nó hợp lệ.

Khi **nguồn cũng là đích**, đáp án lý thuyết là 0 bước và đường đi chỉ có một đỉnh, miễn nguồn hợp lệ. Bài có hai ký hiệu S/E riêng vẫn có thể tách hai vị trí nên không trực tiếp minh họa trường hợp trùng.

## 4. Java 17: BFS mê cung và khôi phục đường ngắn nhất

Bài mẫu dùng:

- `#`: tường, không đi được.
- `.`: ô trống.
- `S`: nguồn duy nhất.
- `E`: đích duy nhất.
- Chỉ di chuyển **4 hướng**, mỗi bước tốn 1.

Lưu thành **GridShortestPathBfsDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class GridShortestPathBfsDemo {
    record Cell(int row, int col) {}
    record Result(int steps, List<Cell> path) {}

    static final int[] DR = {1, 0, -1, 0};
    static final int[] DC = {0, 1, 0, -1};

    static Result shortestPath(String[] grid) {
        Objects.requireNonNull(grid, "grid");
        if (grid.length == 0 || grid[0] == null
                || grid[0].isEmpty()) {
            throw new IllegalArgumentException("Empty grid");
        }

        int rows = grid.length;
        int cols = grid[0].length();

        if ((long) rows * cols > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Grid too large");
        }

        int source = -1;
        int target = -1;

        for (int r = 0; r < rows; r++) {
            if (grid[r] == null || grid[r].length() != cols) {
                throw new IllegalArgumentException("Ragged grid");
            }
            for (int c = 0; c < cols; c++) {
                char ch = grid[r].charAt(c);
                if (ch == 'S') {
                    if (source != -1) {
                        throw new IllegalArgumentException("Multiple S");
                    }
                    source = r * cols + c;
                } else if (ch == 'E') {
                    if (target != -1) {
                        throw new IllegalArgumentException("Multiple E");
                    }
                    target = r * cols + c;
                } else if (ch != '.' && ch != '#') {
                    throw new IllegalArgumentException("Invalid cell");
                }
            }
        }

        if (source < 0 || target < 0) {
            throw new IllegalArgumentException("Need S and E");
        }

        int cells = rows * cols;
        int[] dist = new int[cells];
        int[] parent = new int[cells];
        Arrays.fill(dist, -1);
        Arrays.fill(parent, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        dist[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int id = queue.removeFirst();
            if (id == target) {
                break;
            }

            int r = id / cols;
            int c = id % cols;

            for (int d = 0; d < 4; d++) {
                int nr = r + DR[d];
                int nc = c + DC[d];

                if (nr < 0 || nr >= rows || nc < 0 || nc >= cols
                        || grid[nr].charAt(nc) == '#') {
                    continue;
                }

                int next = nr * cols + nc;
                if (dist[next] == -1) {
                    dist[next] = dist[id] + 1;
                    parent[next] = id;
                    queue.addLast(next);
                }
            }
        }

        if (dist[target] == -1) {
            return new Result(-1, List.of());
        }

        List<Cell> path = new ArrayList<>();
        for (int id = target; id != -1; id = parent[id]) {
            path.add(new Cell(id / cols, id % cols));
        }
        Collections.reverse(path);

        return new Result(dist[target], List.copyOf(path));
    }

    static String showPath(List<Cell> path) {
        StringJoiner joiner = new StringJoiner(" -> ");
        for (Cell cell : path) {
            joiner.add("(" + cell.row() + "," + cell.col() + ")");
        }
        return joiner.toString();
    }

    public static void main(String[] args) {
        String[] maze = {
            "#######",
            "#S...##",
            "#.#.#E#",
            "#...#.#",
            "#.....#",
            "#######"
        };

        Result answer = shortestPath(maze);
        System.out.println("Steps: " + answer.steps());
        System.out.println("Cells: " + answer.path().size());
        System.out.println("Path: " + showPath(answer.path()));

        String[] blocked = {
            "#####",
            "#S#E#",
            "#####"
        };
        System.out.println("Unreachable: "
                + shortestPath(blocked).steps());

        String[] adjacent = {
            "#####",
            "#SE.#",
            "#####"
        };
        System.out.println("Adjacent: "
                + shortestPath(adjacent).steps());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 GridShortestPathBfsDemo.java
java GridShortestPathBfsDemo
```

Stdout chính xác:

```text
Steps: 9
Cells: 10
Path: (1,1) -> (2,1) -> (3,1) -> (4,1) -> (4,2) -> (4,3) -> (4,4) -> (4,5) -> (3,5) -> (2,5)
Unreachable: -1
Adjacent: 1
```

### 4.1. Đọc đường đi

Tọa độ bắt đầu từ **0**. Từ S ở `(1,1)`, đường đi đi xuống qua `(2,1),(3,1),(4,1)`, đi ngang hàng 4 tới `(4,5)`, rồi lên `(3,5),(2,5)` đến E.

Đường đi gồm **10 ô** và **9 cạnh**, đúng với `Steps: 9`. Một đường khác có thể cùng 9 bước, nhưng `DR/DC` xác định cách phá hòa giữa những đường có độ dài bằng nhau.

### 4.2. Tính đúng

BFS đặt `dist[source]=0`, phát hiện mỗi ô không bị chặn tối đa một lần, rồi phát hiện các ô theo lớp số bước. Mỗi cạnh giữa các ô di chuyển hợp lệ có độ dài 1. Do đó khi E được phát hiện lần đầu, `dist[E]` là số bước nhỏ nhất. `parent` được ghi ở cùng thời điểm, nên chuỗi parent chính là một đường đi hợp lệ dài `dist[E]`.

### 4.3. Độ phức tạp

Lưới hình chữ nhật có `V<=R*C` đỉnh hợp lệ. Mỗi ô được đưa vào queue tối đa một lần; mỗi lần kiểm không quá 4 hướng:

- Thời gian: **`O(R*C)`**, bao gồm quét tìm S/E.
- Bộ nhớ: **`O(R*C)`** cho dist, parent và hàng đợi, cộng tối đa `O(R*C)` ô trong đường đi.

Không cần tạo danh sách kề chiếm thêm bộ nhớ.

**Lưu ý:** code kiểm tra tích `rows*cols` không vượt `Integer.MAX_VALUE`, nhưng Java có thể hết RAM với số ô nhỏ hơn rất nhiều. Một hệ thống thực phải có hạn mức cấp phát theo cấu hình máy.

## 5. DFS và flood fill: tìm vùng liên thông

Nếu mục tiêu là “bao nhiêu **vùng đất** tách biệt?” hoặc “đánh dấu toàn bộ ô trong một vùng”, **DFS** là lựa chọn tự nhiên.

Định nghĩa thành phần liên thông trên lưới vô hướng:

> Một tập ô đi được là một **thành phần liên thông** nếu từ bất kỳ ô nào trong tập có thể tới các ô còn lại bằng các cạnh di chuyển được phép, và không có cạnh từ tập đó sang một ô đi được nằm ngoài tập.

**Thuật toán:**

1. Duyệt mọi ô.
2. Nếu ô là đất và **chưa thăm**, tăng số thành phần.
3. Từ ô đó, chạy DFS để đánh dấu **toàn bộ ô đất trong cùng thành phần**.
4. Tiếp tục quét; ô nào đã thăm thì không tạo thành phần mới.

### 5.1. DFS đệ quy hay DFS dùng stack?

DFS đệ quy rất gọn, nhưng trên một vùng lớn gồm hàng triệu ô nối thành một đường dài, stack đệ quy Java có thể **tràn** (`StackOverflowError`).

Với lưới lớn, DFS **lặp bằng `ArrayDeque` như stack** thường an toàn hơn:

```text
visited[start] = true
stack.push(start)

while stack chưa rỗng:
    u = stack.pop()
    for v trong neighbors(u):
        if v hợp lệ và chưa thăm:
            visited[v] = true
            stack.push(v)
```

**Đánh dấu ngay khi push** giúp một ô không bị thêm vào stack nhiều lần do nhiều đường đi khác nhau.

### 5.2. BFS cũng đếm vùng được không?

Có. Để đánh dấu một thành phần, BFS và DFS đều duyệt toàn bộ những ô đi được từ nguồn; **số thành phần giống nhau** nếu dùng **cùng định nghĩa cạnh** và không có lỗi visited. Lựa chọn stack/queue ảnh hưởng thứ tự, không ảnh hưởng tập ô tới được.

## 6. Java 17: đếm thành phần theo 4 hoặc 8 hướng bằng DFS lặp

Lưu thành **GridComponentsDfsDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Objects;

public class GridComponentsDfsDemo {
    static final int[][] FOUR = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1}
    };

    static final int[][] EIGHT = {
        {1, 0}, {-1, 0}, {0, 1}, {0, -1},
        {1, 1}, {1, -1}, {-1, 1}, {-1, -1}
    };

    static int countComponents(String[] grid, boolean diagonal) {
        Objects.requireNonNull(grid, "grid");
        if (grid.length == 0 || grid[0] == null
                || grid[0].isEmpty()) {
            throw new IllegalArgumentException("Empty grid");
        }

        int rows = grid.length;
        int cols = grid[0].length();
        if ((long) rows * cols > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Grid too large");
        }

        for (String row : grid) {
            if (row == null || row.length() != cols) {
                throw new IllegalArgumentException("Ragged grid");
            }
            for (int c = 0; c < cols; c++) {
                if (row.charAt(c) != '.' && row.charAt(c) != '#') {
                    throw new IllegalArgumentException("Invalid cell");
                }
            }
        }

        boolean[] seen = new boolean[rows * cols];
        int[][] directions = diagonal ? EIGHT : FOUR;
        ArrayDeque<Integer> stack = new ArrayDeque<>();
        int components = 0;

        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                int start = r * cols + c;
                if (grid[r].charAt(c) != '.' || seen[start]) {
                    continue;
                }

                components++;
                seen[start] = true;
                stack.push(start);

                while (!stack.isEmpty()) {
                    int id = stack.pop();
                    int cr = id / cols;
                    int cc = id % cols;

                    for (int[] dir : directions) {
                        int nr = cr + dir[0];
                        int nc = cc + dir[1];

                        if (nr < 0 || nr >= rows
                                || nc < 0 || nc >= cols
                                || grid[nr].charAt(nc) != '.') {
                            continue;
                        }

                        int next = nr * cols + nc;
                        if (!seen[next]) {
                            seen[next] = true;
                            stack.push(next);
                        }
                    }
                }
            }
        }

        return components;
    }

    public static void main(String[] args) {
        String[] islands = {
            ".#.",
            "#.#",
            ".#."
        };

        System.out.println("Four-way: "
                + countComponents(islands, false));
        System.out.println("Eight-way: "
                + countComponents(islands, true));
        System.out.println("All blocked: "
                + countComponents(new String[]{"##", "##"}, false));
        System.out.println("One land cell: "
                + countComponents(new String[]{"."}, false));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 GridComponentsDfsDemo.java
java GridComponentsDfsDemo
```

Stdout:

```text
Four-way: 5
Eight-way: 1
All blocked: 0
One land cell: 1
```

### 6.1. Chứng minh số vùng là đúng

Mỗi lần vòng quét thấy một ô đất chưa thăm, ô đó **không** nằm trong bất kỳ thành phần nào đã duyệt trước; nếu có, DFS của thành phần cũ đã thăm nó. Vì vậy ta tăng bộ đếm **đúng một lần** cho thành phần mới.

DFS từ ô đó đánh dấu **mọi ô đất tới được** theo những hướng được phép, không đánh dấu ô tường hoặc ô ngoài lưới. Do đó không bỏ sót ô nào của thành phần và không đi sang thành phần khác.

Lặp lại cho tới hết lưới ⇒ số lần bắt đầu DFS là số thành phần liên thông.

### 6.2. Độ phức tạp

- Thời gian: **`O(R*C)`** vì mỗi ô được đánh dấu tối đa một lần, mỗi ô kiểm tối đa 8 hàng xóm (một hằng số).
- Bộ nhớ: **`O(R*C)`** trong trường hợp xấu cho `seen` và stack.

Nếu chỉ cần số vùng, **không cần** lưu danh sách ô của từng vùng. Nếu cần diện tích mỗi vùng, có thể tăng `area` khi pop mỗi ô, rồi lưu diện tích sau khi DFS kết thúc.

## 7. BFS nhiều nguồn: khoảng cách đến nguồn gần nhất

**Multi-source BFS** là BFS bắt đầu đồng thời từ **nhiều đỉnh nguồn**.

Ví dụ: với lưới nhị phân, mọi ô chứa `0` được coi là nguồn. Với mỗi ô chứa `1`, tìm số bước 4 hướng ít nhất tới **ô 0 gần nhất**.

Thay vì chạy BFS riêng từ **từng ô 1** hoặc **từng ô 0**, ta:

1. Đặt `dist=0` cho **tất cả ô nguồn 0**.
2. Đưa **tất cả nguồn** vào cùng queue ban đầu.
3. Chạy BFS một lần như thường.
4. Lần đầu một ô chưa được thăm, gán `dist[neighbor]=dist[current]+1`.

**Vì sao đúng?** Có thể tưởng tượng thêm một **siêu nguồn** nối với tất cả nguồn gốc bằng cạnh chi phí 0. BFS đồng thời từ mọi nguồn tương đương lan tỏa từng lớp khoảng cách từ **tập nguồn**; mỗi ô nhận khoảng cách nhỏ nhất tới một nguồn bất kỳ.

### 7.1. Ví dụ

```text
Lưới:
0 0 0
0 1 0
1 1 1

Khoảng cách gần ô 0 nhất:
0 0 0
0 1 0
1 2 1
```

Ô giữa hàng cuối (chỉ số `(2,1)`) cách ô 0 gần nhất **2 bước**; các ô `(2,0)` và `(2,2)` cách 1 bước.

### 7.2. Nếu không có nguồn?

Nếu lưới **không có ô 0**, queue ban đầu rỗng. Không ô nào có thể có khoảng cách đến nguồn 0, nên có thể trả **`-1` ở mọi ô** (theo hợp đồng lựa chọn).

Điều này khác với việc trả 0 vì “không cần di chuyển”: 0 chỉ phù hợp nếu **đỉnh đã là nguồn**. Không tồn tại nguồn nghĩa là truy vấn khoảng cách **không có đích hợp lệ**.

## 8. Java 17: Multi-source BFS trên lưới nhị phân

Lưu thành **MultiSourceGridBfsDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Objects;

public class MultiSourceGridBfsDemo {
    static final int[] DR = {1, -1, 0, 0};
    static final int[] DC = {0, 0, 1, -1};

    static int[][] nearestZero(int[][] grid) {
        Objects.requireNonNull(grid, "grid");

        if (grid.length == 0 || grid[0] == null
                || grid[0].length == 0) {
            throw new IllegalArgumentException("Empty grid");
        }

        int rows = grid.length;
        int cols = grid[0].length;
        if ((long) rows * cols > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Grid too large");
        }

        int[][] dist = new int[rows][cols];
        ArrayDeque<Integer> queue = new ArrayDeque<>();

        for (int r = 0; r < rows; r++) {
            if (grid[r] == null || grid[r].length != cols) {
                throw new IllegalArgumentException("Ragged grid");
            }

            Arrays.fill(dist[r], -1);

            for (int c = 0; c < cols; c++) {
                if (grid[r][c] == 0) {
                    dist[r][c] = 0;
                    queue.addLast(r * cols + c);
                } else if (grid[r][c] != 1) {
                    throw new IllegalArgumentException("Only 0 and 1");
                }
            }
        }

        while (!queue.isEmpty()) {
            int id = queue.removeFirst();
            int r = id / cols;
            int c = id % cols;

            for (int d = 0; d < 4; d++) {
                int nr = r + DR[d];
                int nc = c + DC[d];

                if (nr < 0 || nr >= rows || nc < 0 || nc >= cols
                        || dist[nr][nc] != -1) {
                    continue;
                }

                dist[nr][nc] = dist[r][c] + 1;
                queue.addLast(nr * cols + nc);
            }
        }

        return dist;
    }

    public static void main(String[] args) {
        int[][] grid = {
            {0, 0, 0},
            {0, 1, 0},
            {1, 1, 1}
        };

        for (int[] row : nearestZero(grid)) {
            System.out.println(Arrays.toString(row));
        }

        int[][] noSources = {
            {1, 1},
            {1, 1}
        };
        System.out.println("No sources: "
                + nearestZero(noSources)[1][1]);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MultiSourceGridBfsDemo.java
java MultiSourceGridBfsDemo
```

Stdout:

```text
[0, 0, 0]
[0, 1, 0]
[1, 2, 1]
No sources: -1
```

**Tính đúng:** mọi ô nguồn có khoảng cách 0 và được đưa vào queue trước các ô không phải nguồn; các lần mở rộng sau đó đi theo số bước tăng dần. Một ô được gán khi được phát hiện đầu tiên, đúng khoảng cách nhỏ nhất tới tập nguồn.

**Độ phức tạp:** `O(R*C)` thời gian và `O(R*C)` bộ nhớ. So với chạy nhiều BFS độc lập, multi-source BFS loại bỏ phần việc lặp của những vùng gần nhau.

**Phân biệt với lưới tường:** demo này cho phép đi qua cả ô `0` và `1`, bởi `1` không phải tường mà là ô cần tính khoảng cách. Nếu bài là **lửa lan qua các ô trống nhưng không qua tường**, phải thêm điều kiện ô đi được vào bước sinh hàng xóm.

## 9. Đồ thị được sinh ngầm: không gian trạng thái không phải tọa độ

Bây giờ xét một ổ khóa bốn bánh, mỗi bánh là chữ số `0..9`. Trạng thái ban đầu `"0000"`, muốn tới trạng thái đích, nhưng một số mã bị khóa (*deadends*) không được đi qua.

Mỗi thao tác hợp lệ:

- Chọn **một** trong bốn bánh.
- Tăng hoặc giảm **1**, tính vòng `0↔9`.
- Mỗi lần xoay chỉ tốn **một bước**.

Một trạng thái `"1234"` có tối đa **8 hàng xóm**: hai hướng cho mỗi bánh, miễn trạng thái mới không bị cấm.

### 9.1. Mô hình đồ thị

- Đỉnh: mọi chuỗi 4 ký tự chữ số, có tối đa `10^4 = 10.000` trạng thái.
- Cạnh: hai trạng thái khác nhau do xoay đúng **một bánh** đúng một đơn vị, theo modulo 10.
- Các mã bị cấm không được tới, kể cả mã bắt đầu hoặc mã đích.
- Trọng số mọi cạnh là 1.

Cần tìm số lần xoay ít nhất từ `"0000"` đến đích ⇒ **BFS trên đồ thị sinh ngầm** là lựa chọn đúng.

Không cần tạo danh sách gồm 10.000 đỉnh và 80.000 cạnh trước. Từ một mã, sinh 8 mã hàng xóm ngay trong lúc duyệt.

### 9.2. Mã hóa trạng thái

Vì luôn có **bốn chữ số**, ta có thể dùng số nguyên `0..9999`. Mã `"0007"` được lưu là số nguyên `7`; khi sinh hàng xóm, ta vẫn coi nó là cấu hình bốn bánh có các chữ số hàng nghìn, trăm, chục, đơn vị.

Với trọng số vị trí `place ∈ {1,10,100,1000}`:

`digit = (state / place) % 10`.

Tăng một bánh:

`newDigit = (digit+1)%10`.

Giảm một bánh:

`newDigit = (digit+9)%10`.

Mã mới:

`next = state + (newDigit-digit)*place`.

Tất cả các phép tính trên nằm trong miền số nguyên 0..9999. **Không dùng `String.valueOf(state)` làm mã bốn ký tự** nếu muốn so sánh trực tiếp với các chuỗi có số 0 đầu; cần định dạng đủ bốn chữ số hoặc giữ quy ước số nguyên nội bộ nhất quán.

## 10. Java 17: BFS cho ổ khóa bốn bánh

Lưu thành **ImplicitLockBfsDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Objects;

public class ImplicitLockBfsDemo {
    static final int[] PLACES = {1, 10, 100, 1000};

    static int parseCode(String code) {
        Objects.requireNonNull(code, "code");
        if (code.length() != 4) {
            throw new IllegalArgumentException("Need four digits");
        }

        for (int i = 0; i < 4; i++) {
            if (code.charAt(i) < '0' || code.charAt(i) > '9') {
                throw new IllegalArgumentException("Only 0..9");
            }
        }
        return Integer.parseInt(code);
    }

    static int minTurns(String[] deadends, String target) {
        Objects.requireNonNull(deadends, "deadends");
        int goal = parseCode(target);

        boolean[] forbidden = new boolean[10000];
        for (String code : deadends) {
            forbidden[parseCode(code)] = true;
        }

        int start = 0;  // "0000"
        if (forbidden[start] || forbidden[goal]) {
            return -1;
        }

        int[] dist = new int[10000];
        Arrays.fill(dist, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        dist[start] = 0;
        queue.addLast(start);

        while (!queue.isEmpty()) {
            int state = queue.removeFirst();
            if (state == goal) {
                return dist[state];
            }

            for (int place : PLACES) {
                int digit = (state / place) % 10;

                for (int shift : new int[]{-1, 1}) {
                    int newDigit = (digit + shift + 10) % 10;
                    int next = state + (newDigit - digit) * place;

                    if (!forbidden[next] && dist[next] == -1) {
                        dist[next] = dist[state] + 1;
                        queue.addLast(next);
                    }
                }
            }
        }

        return -1;
    }

    public static void main(String[] args) {
        String[] deadends = {
            "0201", "0101", "0102", "1212", "2002"
        };

        System.out.println("Turns: "
                + minTurns(deadends, "0202"));
        System.out.println("Already open: "
                + minTurns(new String[0], "0000"));
        System.out.println("Blocked start: "
                + minTurns(new String[]{"0000"}, "8888"));

        String[] sealed = {
            "1000", "9000", "0100", "0900",
            "0010", "0090", "0001", "0009"
        };
        System.out.println("Sealed start: "
                + minTurns(sealed, "8888"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ImplicitLockBfsDemo.java
java ImplicitLockBfsDemo
```

Stdout:

```text
Turns: 6
Already open: 0
Blocked start: -1
Sealed start: -1
```

### 10.1. Giải thích

Trong ví dụ thứ nhất, BFS tìm đường dài **6 lượt xoay** từ `"0000"` đến `"0202"` mà không đi vào năm mã cấm.

Nếu đích chính là `"0000"` và `"0000"` không bị cấm, đáp án là **0**. Nếu `"0000"` bị cấm, không có trạng thái xuất phát hợp lệ, trả **-1**.

Ở ví dụ `sealed`, **toàn bộ 8 hàng xóm** của `"0000"` đều nằm trong danh sách cấm; BFS không thể đi đâu, trả **-1**.

### 10.2. Độ phức tạp và visited

Có tối đa `V=10^4` trạng thái, mỗi trạng thái sinh đúng 8 ứng viên, nên:

- Thời gian `O(V+E)`, với `E<=8V` cạnh có hướng ⇒ cỡ `O(8×10^4)` thao tác sinh hàng xóm ở mức mô hình.
- Bộ nhớ `O(V)` cho `dist`, `forbidden` và queue.

BFS chỉ đánh dấu mã khi **enqueuing**, nên mỗi mã hợp lệ được đưa vào queue tối đa một lần.

Với khóa b bánh và a chữ số mỗi bánh, không gian có **`a^b`** cấu hình; mỗi cấu hình có tối đa `2b` hàng xóm. Khi b tăng, lưu mảng trực tiếp theo mã có thể không còn khả thi, cần `HashSet` visited, mã hóa phù hợp hoặc thuật toán tìm kiếm khác.

## 11. Khi tọa độ không đủ làm trạng thái

Nhiều bài lưới có quy tắc phụ thuộc **lịch sử hợp lệ đã tích lũy**. Khi đó cùng một ô `(r,c)` có thể phải được thăm **nhiều lần với trạng thái phụ khác nhau**.

### 11.1. Lưới có cửa và chìa khóa

Giả sử:

- `a` là chìa khóa A.
- `A` là cửa chỉ đi qua khi đã nhặt chìa khóa A.
- Có k loại chìa khóa.

Trạng thái nên là:

`(r,c,mask)`,

trong đó bit thứ j của `mask` nói đã có chìa khóa j hay chưa.

Khi vào ô chứa chìa khóa j:

`newMask = mask | (1 << j)`.

Khi xét ô chứa cửa j, chỉ cho đi nếu:

`(mask & (1 << j)) != 0`.

**Sai lầm:** dùng `visited[r][c]` một lần cho mọi mask. Có thể đến ô đó **trước khi nhặt chìa khóa**, rồi sau khi nhặt chìa khóa quay lại nhưng bị visited cũ chặn, khiến không mở được cửa.

Phải dùng `visited[r][c][mask]` hoặc tập trạng thái đã thăm chứa **cả tọa độ và mask**.

Với R hàng, C cột và k chìa khóa, số trạng thái khả dĩ tối đa khoảng:

`R*C*2^k`.

BFS trên mỗi cạnh một bước có thời gian và bộ nhớ `O(R*C*2^k)` với 4 hướng và không gian trạng thái đầy đủ, trong điều kiện thao tác mask hằng số. Đây là một trường hợp **bùng nổ không gian trạng thái**.

### 11.2. Lưới có thời điểm chẵn/lẻ

Nếu cửa đổi trạng thái theo **chẵn/lẻ của thời gian**, điều kiện đi từ cùng một ô có thể khác ở thời điểm t chẵn và t lẻ. Nếu quy tắc chỉ phụ thuộc t mod 2, trạng thái cần:

`(r,c,parity)` với `parity ∈ {0,1}`.

Một ô có thể cần được thăm ở **cả hai parity**, và BFS đánh dấu theo cả `(r,c,parity)`.

Nếu có thao tác **đợi một lượt**, nó cũng là một cạnh trạng thái cần được sinh đúng cách. Không thêm hành động đợi nếu đề không cho phép.

### 11.3. Vị trí và hướng nhìn

Robot có thể đi thẳng hoặc quay trái/phải; từ cùng ô nhưng đang hướng Bắc khác với đang hướng Đông. Trạng thái:

`(r,c,direction)`.

Nếu mỗi hành động tốn một đơn vị, dùng BFS. Nếu đi thẳng, quay hoặc phá tường có chi phí khác nhau, cần thuật toán đường ngắn nhất phù hợp.

### 11.4. Quy tắc đủ thông tin

Một trạng thái phải chứa **đủ thông tin để xác định tập hành động hợp lệ và chi phí chuyển tiếp**, không cần biết toàn bộ lịch sử nếu phần lịch sử đó không còn ảnh hưởng tương lai.

Đây là nguyên tắc *Markov/state sufficiency*: hai lịch sử có thể gộp thành một trạng thái nếu từ đó chúng có cùng những lựa chọn tương lai **liên quan đến mục tiêu** và cùng trạng thái chi phí cần thiết.

Gộp quá mạnh làm mất nghiệm; giữ quá nhiều thông tin làm nổ không gian trạng thái.

## 12. Khi BFS thường không còn đúng: trọng số trên cạnh

BFS bằng FIFO tìm đường có **ít cạnh nhất**, đúng với bài mọi bước chi phí 1. Nếu đi vào ô có phí khác nhau, số bước và tổng chi phí có thể không cùng tối ưu.

Ví dụ từ S đến E có hai đường:

- Đường ngắn 2 bước nhưng tổng phí 10.
- Đường dài 5 bước nhưng tổng phí 3.

BFS thường có thể chọn đường 2 bước, **không tối ưu chi phí 3**.

Chọn thuật toán dựa trên trọng số:

| Quy tắc chi phí cạnh | Thuật toán phù hợp |
|---|---|
| Mọi cạnh bằng 1 | BFS |
| Mọi cạnh cùng chi phí dương cố định | BFS theo số bước, nhân chi phí nếu cần |
| Chi phí chỉ **0 hoặc 1** | **0-1 BFS** bằng deque |
| Trọng số không âm bất kỳ | **Dijkstra** với priority queue |
| Có cạnh âm và không có chu trình âm tới đích | Cần thuật toán khác như Bellman–Ford hoặc cấu trúc đặc biệt; Dijkstra không đảm bảo |
| Đồ thị có thứ tự topo / DAG | DP đường đi theo topo có thể phù hợp, kể cả trọng số âm nếu DAG |

**DFS không tự đảm bảo đường ngắn nhất**, ngay cả khi mọi cạnh giá 1, vì nó có thể đi sâu theo một đường dài trước đường ngắn.

### 12.1. Chi phí theo ô hay theo cạnh?

Trong ví dụ 0-1 BFS dưới đây, **chi phí của cạnh u→v bằng giá trị ô v**: đi vào ô 0 tốn 0, đi vào ô 1 tốn 1. Chi phí ô bắt đầu **không** được tính vì không có bước đi **vào** nó.

Đề khác có thể quy định phí khi **rời ô**, phí cho cả ô nguồn, hoặc phí cho hành động thay vì ô; phải thay quan hệ chuyển cho đúng hợp đồng.

## 13. 0-1 BFS: dùng deque thay cho priority queue

Khi mọi cạnh có trọng số **0 hoặc 1**, thuật toán **0-1 BFS** dùng một `Deque` hai đầu:

1. `dist[source]=0`, đưa source vào deque.
2. Lấy trạng thái ở **đầu deque**.
3. Với cạnh `u→v` có phí `w∈{0,1}`, thử `candidate=dist[u]+w`.
4. Nếu candidate nhỏ hơn `dist[v]`, cập nhật dist:
   - Nếu `w=0`, đưa v vào **đầu deque**.
   - Nếu `w=1`, đưa v vào **cuối deque**.

**Trực giác:** một cạnh phí 0 không làm tăng khoảng cách nên cần ưu tiên xử lý ngay; cạnh phí 1 nằm sau những trạng thái có khoảng cách hiện tại thấp hơn.

Đây không phải BFS thường vì **một đỉnh có thể được cải thiện khoảng cách sau lần phát hiện đầu**. Vì thế không được khóa visited vĩnh viễn ngay ở lần enqueue đầu tiên như BFS không trọng số. Dùng điều kiện **relax nếu tìm được khoảng cách nhỏ hơn**, kết hợp bỏ entry cũ nếu muốn.

### 13.1. Ví dụ chỉ ra khác biệt

Lưới phí khi bước **vào** ô:

```text
0 1 1
0 1 0
0 0 0
```

Nguồn `(0,0)`, đích `(0,2)`.

Đường ít bước nhất đi ngang hàng đầu:

`(0,0)→(0,1)→(0,2)`

chỉ **2 bước**, nhưng tổng phí `1+1=2`.

Một đường nhiều bước hơn:

`(0,0)→(1,0)→(2,0)→(2,1)→(2,2)→(1,2)→(0,2)`

gồm 6 bước nhưng chỉ đi vào **một ô phí 1** là đích `(0,2)`, nên tổng phí **1**. Đáp án tối ưu theo chi phí là **1**.

BFS thường theo số bước và 0-1 BFS **trả lời hai câu hỏi khác nhau**.

## 14. Java 17: 0-1 BFS trên lưới chi phí 0/1

Lưu thành **ZeroOneGridBfsDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Objects;

public class ZeroOneGridBfsDemo {
    record State(int id, int distance) {}

    static final int[] DR = {1, -1, 0, 0};
    static final int[] DC = {0, 0, 1, -1};

    static int minEntryCost(int[][] cost, int targetRow, int targetCol) {
        Objects.requireNonNull(cost, "cost");

        if (cost.length == 0 || cost[0] == null
                || cost[0].length == 0) {
            throw new IllegalArgumentException("Empty grid");
        }

        int rows = cost.length;
        int cols = cost[0].length;

        if ((long) rows * cols > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Grid too large");
        }

        if (targetRow < 0 || targetRow >= rows
                || targetCol < 0 || targetCol >= cols) {
            throw new IllegalArgumentException("Target out of grid");
        }

        for (int[] row : cost) {
            if (row == null || row.length != cols) {
                throw new IllegalArgumentException("Ragged grid");
            }
            for (int x : row) {
                if (x != 0 && x != 1) {
                    throw new IllegalArgumentException("Only 0/1 cost");
                }
            }
        }

        int[] dist = new int[rows * cols];
        Arrays.fill(dist, Integer.MAX_VALUE);

        ArrayDeque<State> deque = new ArrayDeque<>();
        dist[0] = 0; // Bắt đầu tại (0,0), không tính phí ô nguồn.
        deque.addFirst(new State(0, 0));

        while (!deque.isEmpty()) {
            State state = deque.removeFirst();
            int id = state.id();

            // Bỏ entry cũ nếu đã tìm được khoảng cách tốt hơn.
            if (state.distance() != dist[id]) {
                continue;
            }

            int r = id / cols;
            int c = id % cols;

            for (int d = 0; d < 4; d++) {
                int nr = r + DR[d];
                int nc = c + DC[d];

                if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) {
                    continue;
                }

                int next = nr * cols + nc;
                int weight = cost[nr][nc];
                int candidate = state.distance() + weight;

                if (candidate < dist[next]) {
                    dist[next] = candidate;
                    State updated = new State(next, candidate);

                    if (weight == 0) {
                        deque.addFirst(updated);
                    } else {
                        deque.addLast(updated);
                    }
                }
            }
        }

        return dist[targetRow * cols + targetCol];
    }

    public static void main(String[] args) {
        int[][] grid = {
            {0, 1, 1},
            {0, 1, 0},
            {0, 0, 0}
        };

        System.out.println("Minimum cost: "
                + minEntryCost(grid, 0, 2));
        System.out.println("Single row: "
                + minEntryCost(new int[][]{{0, 1, 1}}, 0, 2));
        System.out.println("Start equals target: "
                + minEntryCost(new int[][]{{0}}, 0, 0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ZeroOneGridBfsDemo.java
java ZeroOneGridBfsDemo
```

Stdout:

```text
Minimum cost: 1
Single row: 2
Start equals target: 0
```

### 14.1. Vì sao dùng record `State(id,distance)`?

Khi `dist[v]` được cải thiện, một entry cũ của v có thể vẫn nằm trong deque. Record giữ **snapshot khoảng cách khi enqueue**. Khi lấy ra, nếu `state.distance()!=dist[id]`, entry đã lỗi thời và bị bỏ.

Đây là kỹ thuật giúp dễ lập luận về các lần relax; khác với BFS trọng số 1 nơi mỗi ô chỉ được enqueue **một lần**.

### 14.2. Tính đúng và độ phức tạp

Với trọng số chỉ 0/1, deque tổ chức các ứng viên theo mức khoảng cách tăng không quá 1 ở lân cận, tương tự Dijkstra nhưng không cần heap so khóa tổng quát. Mỗi phép relax đặt đỉnh theo đúng đầu/cuối dựa trên trọng số; khi không còn relax có lợi, `dist` thỏa điều kiện đường ngắn nhất.

Trong mô hình chuẩn 0-1 BFS, tổng thời gian **`O(V+E)`** và bộ nhớ `O(V+E)` theo cách lưu queue snapshot trong trường hợp xấu; trên lưới bốn hướng có `V=RC`, `E<=4RC`, nên thường viết **`O(RC)`** thời gian và không gian phụ tuyến tính theo số ô. Bộ nhớ riêng `dist` là `O(RC)`.

**Giới hạn:** code dùng `int` cho khoảng cách, phù hợp lưới nhỏ/thông thường. Một ứng dụng hỗ trợ lưới cực lớn phải kiểm tra nguy cơ tràn chỉ số, chi phí và thiếu RAM. Giá trị chỉ **0/1** mới cho phép dùng deque theo quy tắc này; nếu phí có giá trị 2, 7, ... thì dùng Dijkstra hoặc kỹ thuật riêng được chứng minh.

## 15. Sinh hàng xóm ngầm một cách an toàn

Một hàm sinh hàng xóm tốt phải thỏa ba đặc tính:

1. **Không bỏ sót:** mọi chuyển hợp lệ theo đề đều được sinh.
2. **Không sinh sai:** mọi chuyển được xử lý thực sự phù hợp điều kiện biên và luật.
3. **Nhất quán với state:** nếu chi phí hoặc hành động phụ thuộc chìa khóa, thời gian, hướng, v.v., trạng thái đầu vào phải chứa dữ liệu đó.

### 15.1. Không cần lưu edges nhưng vẫn phải tránh trùng state

Một trạng thái có thể được đạt qua nhiều đường, ví dụ một ô lưới có bốn hàng xóm đều có thể tiến vào. Không dựng danh sách kề không đồng nghĩa tránh được chu trình. Cần:

- `visited` hoặc `dist==-1` trong BFS không trọng số.
- `visited` khi push trong DFS đánh dấu vùng.
- `dist` và relax theo chi phí khi cạnh có trọng số.
- `Set<State>` nếu không có mã hóa mảng nhỏ, với `equals/hashCode` ổn định.

Nếu đồ thị trạng thái có hàng triệu/không giới hạn cấu hình, cần phân tích xem việc duyệt có **kết thúc** hay không trước khi dùng BFS/DFS một cách mù quáng.

### 15.2. Không dùng `HashMap` với khóa bị sửa

Với trạng thái chứa mảng, nếu đưa một đối tượng có nội dung thay đổi vào `HashSet/HashMap` mà `equals/hashCode` phụ thuộc nội dung đó, rồi sửa mảng, việc tìm lại khóa có thể thất bại.

Có thể dùng:

- Một `record State(int row,int col,int mask)` bất biến.
- Số nguyên mã hóa state.
- Chuỗi chuẩn hóa không bị sửa.
- Một đối tượng key bất biến có triển khai `equals/hashCode` đúng.

**Cùng cấu hình phải có cùng key**; hai cấu hình ảnh hưởng tương lai khác nhau không được dùng cùng key.

### 15.3. Sinh chuyển trong đồ thị có hướng

Nếu từ A có thể sang B nhưng B **không thể** quay lại A, chỉ thêm cạnh A→B trong `neighbors(A)`. Không tự động thêm cạnh ngược vì “trông giống một lưới”, trừ khi đề xác nhận chuyển ngược cũng hợp lệ.

Ví dụ một ô mũi tên `>` chỉ cho đi sang phải, hoặc đường trượt dốc chỉ cho đi xuống, sẽ tạo đồ thị có hướng ngay trên lưới hình học.

## 16. Độ phức tạp: tính theo trạng thái thật, không chỉ kích thước hình

Với lưới thường và số hướng cố định:

- Có tối đa `RC` đỉnh.
- Mỗi đỉnh thử tối đa 4/8 hàng xóm.
- BFS/DFS chạy **`O(RC)`** khi tất cả ô có thể tới được.

Nhưng với lưới có trạng thái bổ sung:

| Trạng thái | Số trạng thái có thể có |
|---|---:|
| `(r,c)` | `R*C` |
| `(r,c,parity)` | `2*R*C` |
| `(r,c,direction)` với 4 hướng | `4*R*C` |
| `(r,c,mask)` với k chìa khóa | `R*C*2^k` |
| `(r,c,remainingEnergy)` với E mức | `R*C*(E+1)` |
| Khóa b bánh a chữ số | `a^b` |

Các con số là **chặn trên kích thước không gian**, không nhất thiết là số trạng thái thực sự đạt được từ nguồn.

**Cảnh báo:** nếu `mask` có k lớn, `1<<k` có thể tràn số nguyên Java. Với k vượt kích thước bit sử dụng được, cần kiểu dữ liệu khác hoặc biểu diễn tập trạng thái thưa. Không cấp phát mảng `R*C*2^k` khi chưa ước lượng RAM và kiểm tra tràn.

### 16.1. Tại sao đôi khi dùng map thay vì mảng?

Nếu phạm vi mã hóa nhỏ và dày (như 10.000 mã khóa), mảng `int[] dist` nhanh, đơn giản và tiết kiệm overhead.

Nếu trạng thái là chuỗi dài, cặp số lớn hoặc chỉ phần rất nhỏ của không gian có thể đạt, `HashMap<State,Integer>`/`HashSet<State>` có thể hợp lý hơn. Thời gian trung bình thao tác hash thường coi `O(1)` nhưng vẫn phụ thuộc chiều dài key, chất lượng hash và overhead bộ nhớ.

### 16.2. Khi một tìm kiếm trên đồ thị vô hạn không dừng

Ví dụ phép chuyển từ số nguyên x được phép sang `x+1` và `x-1`, không có giới hạn miền và không có đích có thể đạt do ràng buộc khác. Một BFS không bị giới hạn có thể liên tục sinh trạng thái mới mãi mãi.

Muốn dùng tìm kiếm toàn diện, cần chứng minh:

- Không gian trạng thái hữu hạn; **hoặc**
- Có chặn tìm kiếm an toàn; **hoặc**
- Có điều kiện dừng phù hợp với yêu cầu và tính đúng.

Một giới hạn `maxSteps` tự đặt có thể làm mất nghiệm nếu không được chứng minh hợp lệ.

## 17. BFS hai chiều và tìm kiếm từ cả hai đầu

Nếu bài tìm **đường ngắn nhất giữa đúng hai đỉnh** trong một đồ thị **không trọng số, cạnh đảo chiều được**, có thể dùng **bidirectional BFS**:

- Một BFS từ nguồn s.
- Một BFS từ đích t theo **cạnh ngược**.
- Khi hai vùng đã duyệt gặp nhau, ghép độ dài đường đi.

Trên đồ thị vô hướng (lưới di chuyển đối xứng, khóa xoay lên/xuống đối xứng), điều này có thể giảm mạnh số trạng thái phải mở khi khoảng cách lớn và hệ số phân nhánh cao.

### 17.1. Điều kiện quan trọng

- Nếu đồ thị có hướng, tìm từ đích phải dùng **các cạnh ngược** chứ không chạy cùng luật thuận tùy tiện.
- Nếu một bên chạm một đỉnh của bên kia, cần biết khoảng cách BFS hai bên và kiểm soát thứ tự mở rộng/lớp để kết luận đúng đường ngắn nhất.
- Nếu bài có trọng số, không thể lấy bản bidirectional BFS thường áp nguyên xi.
- Nếu các hành động có điều kiện phụ thuộc lịch sử, state của hai phía và cách ghép cần được chứng minh hợp lệ.

Bidirectional BFS không phải lúc nào nhanh hơn: khi đích có vùng tiền nhiệm rất lớn hoặc sinh cạnh ngược khó, chi phí có thể cao hơn BFS một chiều.

## 18. Tối ưu bộ nhớ và thời gian trên lưới lớn

### 18.1. BitSet cho visited

`boolean[][]` hoặc `boolean[]` dễ đọc; `BitSet` có thể giảm bộ nhớ khi số ô lớn và mỗi trạng thái chỉ cần một bit. Dùng `id=r*C+c` làm chỉ số.

Nhưng BitSet không tự lưu khoảng cách hay parent; nếu cần đường đi ngắn nhất và truy vết, vẫn phải có cấu trúc tương ứng.

### 18.2. Dùng queue số nguyên thay vì tạo nhiều đối tượng

`ArrayDeque<Integer>` có boxing và overhead. Khi kích thước lưới lớn và biết số trạng thái không vượt một giới hạn, có thể dùng `int[] queue` cùng hai con trỏ `head/tail` để giảm object allocations.

BFS không trọng số với visited-on-enqueue đưa mỗi state vào queue tối đa một lần nên mảng queue kích thước V thường đủ. 0-1 BFS với cập nhật khoảng cách có thể có entry lặp, nên không tự dùng mảng queue V phần tử nếu chưa chứng minh giới hạn.

### 18.3. Không tạo cạnh trước khi duyệt

Thay vì `List<Integer>[] adjacency` cho mọi ô, sinh tối đa 4 hoặc 8 cạnh từ tọa độ lúc cần. Điều này thường tiết kiệm bộ nhớ và ít công cấp phát, đặc biệt khi phần lớn lưới bị chặn hoặc không đạt được từ nguồn.

### 18.4. Chọn đúng cấu trúc frontier

- **Queue** FIFO cho BFS.
- **Stack** LIFO hoặc đệ quy cho DFS.
- **Deque** hai đầu cho 0-1 BFS.
- **PriorityQueue** theo khoảng cách cho Dijkstra.

Nhầm stack và queue có thể khiến câu trả lời **đường ngắn nhất** sai ngay cả khi visited và sinh hàng xóm đúng.

## 19. Những lỗi thường gặp

### Lỗi 1 — Đổi DFS thành BFS mà không đổi cấu trúc

Dùng `stack.pop()` cho bài ít bước nhất rồi dừng khi gặp đích sẽ trả đường đầu tiên theo DFS, **không nhất thiết ngắn nhất**. Dùng queue FIFO và BFS theo lớp.

### Lỗi 2 — Đánh dấu khi dequeue

Với BFS thường, đánh dấu ngay khi **enqueue** để tránh nhiều đường cùng đưa một đỉnh vào queue. Mark quá trễ có thể tạo nhiều entry và làm parent không ổn định.

### Lỗi 3 — Quên kiểm tra chỉ số âm

Từ `(0,0)` thử lên/trái tạo chỉ số `-1`. Phải kiểm tra biên trước khi truy cập mảng/chuỗi.

### Lỗi 4 — Quên kiểm tra tường

Một ô nằm trong biên không có nghĩa được đi qua. Cần điều kiện `grid[nr][nc] != '#'` hoặc luật tương ứng.

### Lỗi 5 — Dùng 8 hướng khi đề chỉ cho 4 hướng

Thêm cạnh chéo có thể rút ngắn đường đi hoặc nối các vùng vốn rời nhau, trả đáp án sai.

### Lỗi 6 — Bỏ quy tắc không cắt góc

Trong bài cấm đi chéo qua góc bị chặn, chỉ kiểm tra ô đích chéo là chưa đủ. Cần kiểm cả hai ô kề trục theo luật.

### Lỗi 7 — Dùng visited chỉ theo tọa độ khi state có chìa khóa

Nếu hai lần tới cùng `(r,c)` có `mask` khác nhau, khả năng mở cửa khác nhau. Gộp chúng bằng một `visited[r][c]` có thể bỏ sót lời giải.

### Lỗi 8 — Không gán visited/dist trước khi enqueue

Nếu thêm nguồn vào queue nhưng để `dist[source]=-1`, các hàng xóm có thể thêm nguồn trở lại và tạo chu trình vô ích.

### Lỗi 9 — Tính sai số bước và số ô

Đường đi có k cạnh chứa **k+1 đỉnh**, nếu nguồn và đích giống nhau thì 0 cạnh và 1 đỉnh. Không in số ô như số bước.

### Lỗi 10 — Quên reset visited giữa các truy vấn

Nếu giải nhiều bộ test độc lập, phải tạo mảng `visited/dist` mới hoặc dùng cơ chế đánh dấu theo lượt được thiết kế đúng. Tái sử dụng visited cũ làm những ô cần thăm bị bỏ qua.

### Lỗi 11 — Multi-source BFS nhưng cho mỗi nguồn một lượt BFS riêng

Chạy một BFS từ từng nguồn rồi lấy min có thể đúng nhưng thừa việc lớn; đẩy **mọi nguồn vào queue lúc đầu** và duyệt một lần.

### Lỗi 12 — Không xử lý nguồn/đích bị cấm

Ở khóa số, kiểm tra deadends trước khi kết luận `start==target`; nếu start đã cấm thì không có trạng thái xuất phát hợp lệ theo hợp đồng demo.

### Lỗi 13 — Mất số 0 đầu mã khóa

`"0007"` và `"7"` không phải hai chuỗi bốn ký tự giống nhau; khi lưu state bằng int 7, phải giữ **mô hình cố định bốn bánh**. Không dùng string length của số nguyên để sinh vòng quay.

### Lỗi 14 — Dùng BFS thường cho trọng số 0/1

Đường đi ít bước chưa chắc ít chi phí. Với cạnh phí 0/1, dùng **0-1 BFS**; với trọng số không âm tổng quát, dùng Dijkstra.

### Lỗi 15 — Khóa visited trong 0-1 BFS ở lần gặp đầu

Một đỉnh có thể được phát hiện lần đầu qua cạnh phí 1 rồi sau đó được cải thiện bằng một chuỗi cạnh 0. Phải dùng **relax khi candidate < dist[v]**, không chặn mọi lần đến tiếp theo bằng visited vĩnh viễn.

### Lỗi 16 — Cho phép cạnh trọng số âm trong Dijkstra

Dijkstra dựa trên trọng số không âm để chốt khoảng cách. Có cạnh âm thì không được áp nguyên thuật toán mà không chứng minh thêm tính chất đặc biệt của bài.

### Lỗi 17 — DFS đệ quy trên lưới cực lớn

Một vùng dài có thể khiến độ sâu đệ quy lên tới O(RC), gây `StackOverflowError`. Dùng DFS lặp với stack hoặc BFS.

### Lỗi 18 — Tạo mảng visited có kích thước tích bị tràn

`rows*cols` hoặc `R*C*2^k` có thể tràn `int`, gây `NegativeArraySizeException` hoặc tạo mảng sai kích thước. Dùng kiểu rộng để kiểm tra kích thước trước khi cấp phát.

### Lỗi 19 — Dùng `HashSet` với key không ổn định

Nếu thay đổi nội dung key sau khi thêm vào hash set, truy vấn `contains` có thể thất bại. Tạo state bất biến hoặc mã hóa số nguyên ổn định.

### Lỗi 20 — Kết luận không tới được khi tìm chưa hết

Nếu BFS chưa lấy tới đích và queue vẫn còn state, không được trả -1 chỉ vì chưa thấy đích ở một lớp nào đó. Kết luận vô nghiệm khi **frontier cạn** (hoặc có chứng minh cắt an toàn).

### Lỗi 21 — Xem đồ thị có hướng như vô hướng

Trong lưới chỉ được đi theo mũi tên hoặc một chiều, mỗi cạnh có hướng; không tự thêm chuyển ngược.

### Lỗi 22 — Đo độ phức tạp chỉ theo RC dù state mở rộng

Với chìa khóa, hướng, thời gian hoặc năng lượng, cùng ô có thể chứa nhiều state. Phải ước lượng số state thật (`RC2^k`, `4RC`, ...), không nói mọi bài lưới đều O(RC).

## 20. Kiểm thử và đối chiếu với oracle

### 20.1. Các chỉ tiêu cần kiểm tra

- **Hợp lệ:** mọi bước trên đường đi là một cạnh được phép; không có bước xuyên tường.
- **Nguồn/đích:** bắt đầu đúng S, kết thúc đúng E.
- **Chi phí:** tổng số bước, số ô hoặc tổng trọng số phải đúng định nghĩa.
- **Optimality:** đường đi không dài/đắt hơn một lời giải khác có thể tìm bằng oracle trên test nhỏ.
- **Visited:** không tái thêm state ở BFS thường; trong 0-1 BFS chỉ relax khi cải thiện.
- **Đường không tồn tại:** trả sentinel đúng (`-1`, danh sách trống, v.v.).
- **Input xấu:** lưới rỗng, jagged, ký tự lạ, thiếu S/E, mã khóa sai độ dài.
- **Nhiều bộ test:** không lây visited từ test trước sang test sau.

### 20.2. Bộ test quan trọng

| Dữ liệu / tình huống | Kết quả kỳ vọng |
|---|---|
| Mê cung ở phần 4 | **9 bước**, đường có 10 ô |
| `#S#E#` với S/E bị tường chia cắt | **-1** |
| `#SE.#` S sát E | **1 bước** |
| Lưới `.#. / #.# / .#.` theo 4 hướng | **5 vùng** |
| Cùng lưới theo 8 hướng | **1 vùng** |
| Lưới toàn `#` | **0 vùng** |
| Lưới chỉ một `.` | **1 vùng** |
| Multi-source ma trận 3×3 ở phần 7 | Khoảng cách hàng cuối `1,2,1` |
| Multi-source không có ô 0 | Mọi dist **-1** |
| Khóa `"0000"→"0202"` và năm deadends mẫu | **6 lượt xoay** |
| Khóa mục tiêu `"0000"`, không deadends | **0** |
| Khóa cấm trạng thái xuất phát | **-1** |
| Khóa cấm cả 8 trạng thái kề `"0000"` | **-1** với đích khác nguồn |
| Lưới phí 0/1 ở phần 13 đến `(0,2)` | **Tổng phí 1**, không phải 2 |
| Một hàng chi phí `[0,1,1]` đến ô cuối | **2** |
| Lưới một ô 0 và đích chính nó | **0** |

### 20.3. Oracle BFS trên đồ thị nhỏ

Với một lưới rất nhỏ (ví dụ 3×3), có thể **xây danh sách cạnh tường minh** của những ô hợp lệ theo đúng luật 4 hoặc 8 hướng, rồi chạy BFS trên danh sách kề. So kết quả với BFS **sinh hàng xóm ngầm**.

Hai chương trình dùng **biểu diễn đồ thị khác nhau**, nên có khả năng phát hiện lỗi tính tọa độ, sai số cột hoặc điều kiện cản.

### 20.4. Oracle Dijkstra cho 0-1 BFS

Với lưới có chi phí chỉ 0/1, có thể chạy Dijkstra dùng priority queue, phí cạnh bằng phí ô đích. Kết quả phải bằng 0-1 BFS cho mọi ô đích.

Dijkstra chậm hơn về hệ số và `log V` trên đồ thị nhỏ, nhưng thích hợp làm **oracle độc lập** để kiểm tra kỹ thuật deque.

### 20.5. Oracle cho lưới có nhiều nguồn

Từng ô nguồn 0 có thể chạy BFS riêng (chậm trên lưới lớn). Với test nhỏ, lấy min khoảng cách từ các nguồn tới mỗi ô, so với kết quả multi-source BFS. Khi không có nguồn, giữ sentinel -1 cho mọi ô.

### 20.6. Xác minh đường đi chứ không chỉ độ dài

Một chương trình có thể in đúng độ dài 9 nhưng khôi phục đường chứa bước nhảy qua tường do lỗi parent. Với mỗi cặp ô liên tiếp trên đường:

- Cả hai ô nằm trong biên.
- Cả hai là ô đi được.
- Với bốn hướng: `abs(r1-r2)+abs(c1-c2)==1`.
- Tổng số cạnh đúng bằng `path.size()-1`.
- Đầu đường là S, cuối đường là E.

Đó là kiểm tra **đúng về cấu trúc**, độc lập với phép so khoảng cách.

## 21. Bài tập tự luyện có đáp án

### Bài 1 — Sinh hàng xóm

Từ `(2,3)` trên lưới có R=5, C=7, nếu cho đi bốn hướng và không có tường, các ô kề là gì?

**Đáp án:** `(3,3)`, `(2,4)`, `(1,3)`, `(2,2)`; tất cả đều trong biên.

### Bài 2 — Ô góc

Từ ô `(0,0)` của lưới 3×3, tối đa bao nhiêu ô kề theo bốn hướng?

**Đáp án:** 2: `(1,0)` và `(0,1)`. Hai hướng còn lại ra ngoài biên.

### Bài 3 — Đếm vùng theo bốn và tám hướng

Với lưới `.#. / #.# / .#.` gồm năm dấu `.`, có bao nhiêu thành phần liên thông theo hai quy tắc?

**Đáp án:** 4 hướng có **5**, 8 hướng có **1** nếu cho phép nối chéo qua góc cản.

### Bài 4 — BFS và DFS

Cần tìm số bước ít nhất từ S tới E với mọi cạnh giá 1. Chọn BFS hay DFS?

**Đáp án:** **BFS**. DFS có thể tìm một đường hợp lệ nhưng không đảm bảo ít bước nhất.

### Bài 5 — Số ô so với số bước

Một đường đi ngắn nhất có 12 cạnh. Nó chứa bao nhiêu đỉnh kể cả nguồn và đích?

**Đáp án:** **13 đỉnh**.

### Bài 6 — Multi-source BFS

Ba nguồn cùng có khoảng cách 0 và được đưa hết vào queue. Một ô cách các nguồn lần lượt 4,2,5 bước sẽ nhận dist bao nhiêu?

**Đáp án:** **2**, vì multi-source BFS tìm min khoảng cách tới **một trong các nguồn**.

### Bài 7 — Khóa số

Khóa có 4 bánh, mỗi bánh 10 chữ số. Có tối đa bao nhiêu trạng thái và bao nhiêu hàng xóm khi mỗi lượt chỉ xoay một bánh ±1?

**Đáp án:** **10.000 trạng thái** và tối đa **8 hàng xóm** mỗi trạng thái, chưa loại deadends.

### Bài 8 — Số 0 đầu trong khóa

Có thể lưu `"0007"` thành int 7 không? Điều kiện nào bắt buộc?

**Đáp án:** được, nếu các phép toán luôn coi đây là **bốn vị trí chữ số**, không dựa vào `String.valueOf(7)` như mã bốn ký tự. Mã hóa và giải mã nhất quán.

### Bài 9 — Chìa khóa và visited

Tại sao `visited[r][c]` có thể sai nếu cửa chỉ mở sau khi lấy chìa?

**Đáp án:** cùng tọa độ nhưng tập chìa khóa khác nhau có **những chuyển tiếp hợp lệ khác nhau**. Dùng `visited[r][c][mask]`.

### Bài 10 — Bùng nổ state

Lưới R×C có 6 loại chìa khóa. Số trạng thái tối đa của `(r,c,mask)` là bao nhiêu?

**Đáp án:** `R*C*2^6 = 64RC`. Không mặc định mọi state đều đạt được.

### Bài 11 — 0-1 BFS

Khi relax cạnh có phí 0, đỉnh được đưa vào đầu hay cuối deque?

**Đáp án:** **đầu deque**; với cạnh phí 1 đưa vào **cuối**.

### Bài 12 — BFS và chi phí

Một đường 2 bước tốn 10, một đường 5 bước tốn 3. BFS không trọng số ưu tiên tiêu chí nào?

**Đáp án:** **2 bước** vì BFS đếm số cạnh; nếu cần tối thiểu tổng chi phí, phải dùng thuật toán trọng số phù hợp.

### Bài 13 — Lưới 0-1 minh họa

Trên lưới `0 1 1 / 0 1 0 / 0 0 0`, từ góc trên trái đến góc trên phải, phí nhỏ nhất (phí khi bước vào ô) là bao nhiêu?

**Đáp án:** **1**, theo đường vòng phía dưới; đường thẳng hai bước tốn phí 2.

### Bài 14 — visited-on-enqueue

Vì sao BFS thường nên đánh dấu visited khi đưa vào queue?

**Đáp án:** tránh một đỉnh bị nhiều cha **đưa vào queue lặp**, và giữ parent/khoảng cách ở lần phát hiện đầu tiên, vốn là ngắn nhất khi mọi cạnh giá 1.

### Bài 15 — DFS lặp

Một vùng nối thành chuỗi dài 1 triệu ô nên duyệt DFS bằng đệ quy Java hay bằng stack lặp?

**Đáp án:** **stack lặp** thường an toàn hơn, tránh stack đệ quy sâu dẫn tới `StackOverflowError`.

### Bài 16 — Sinh cạnh có hướng

Từ ô mũi tên `>` chỉ được sang phải. Có được tự động thêm cạnh đi ngược từ ô bên phải về ô đó không?

**Đáp án:** **không** trừ khi luật tại ô bên phải cũng cho phép. Đồ thị có thể có hướng.

### Bài 17 — Không có nguồn

Multi-source BFS trên lưới chỉ gồm các ô 1, không có ô 0. Khoảng cách đến ô 0 gần nhất là bao nhiêu?

**Đáp án:** **không xác định/không có nguồn**; theo hợp đồng demo, trả **-1** cho mọi ô.

### Bài 18 — Kiểm tra parent

Với đường 4 hướng, nếu có hai ô liên tiếp `(1,1)` và `(2,3)`, chúng có phải hai đỉnh kề trực tiếp không?

**Đáp án:** **không**, vì khoảng cách Manhattan `|1-2|+|1-3|=3`, khác 1. Parent đã tạo một bước không hợp lệ.

## 22. Checklist áp dụng cho bài lưới và đồ thị sinh ngầm

1. **Đỉnh thật sự là gì?** Ô `(r,c)`, mã khóa hay `(r,c,mask)`?
2. **Cạnh hợp lệ sinh ra bằng luật gì?** 4/8 hướng, xoay bánh, đổi chỗ, cửa/chìa khóa?
3. **Đồ thị có hướng không?** Chỉ thêm chuyển tiếp đề cho phép.
4. **Mỗi cạnh có phí bao nhiêu?** Giá 1 ⇒ BFS; 0/1 ⇒ deque 0-1 BFS; phí không âm tổng quát ⇒ Dijkstra.
5. **Nguồn và đích là gì?** Có nhiều nguồn, nguồn trùng đích hay nguồn bị cấm không?
6. **Grid có hình chữ nhật không?** Kiểm tra R,C, hàng rỗng hoặc jagged trước khi dùng `r*C+c`.
7. **Đã kiểm tra biên trước khi truy cập?** Không để chỉ số âm hoặc vượt R,C.
8. **Ô được đi là những loại nào?** `#` có phải tường không, `1` là tường hay phí?
9. **Có quy tắc chéo/cắt góc không?** Chọn 4/8 hướng đúng theo đề.
10. **Visited đủ thông tin chưa?** Tọa độ, key mask, parity, hướng và các thành phần quyết định tương lai.
11. **Với BFS thường, đã đánh dấu khi enqueue chưa?**
12. **Với DFS vùng, đã đánh dấu khi push chưa?** Tránh duyệt lặp.
13. **Với 0-1 BFS, có relax khi tốt hơn không?** Không khóa visited quá sớm.
14. **Nếu cần đường đi, parent lưu ở lần phát hiện/cập nhật đúng chưa?**
15. **Nếu không có đường, trả sentinel và đường trống đúng chưa?**
16. **Nếu nhiều nguồn, đã khởi tạo cả tập nguồn dist 0 ngay đầu?**
17. **Nếu đồ thị ngầm lớn, số trạng thái tiềm năng là bao nhiêu?** Tính cả bitmask/hướng/thời gian.
18. **Có tràn số trong id hoặc cấp phát không?** Dùng kiểm tra kiểu rộng trước khi nhân.
19. **Dùng queue/stack/deque/heap đúng chưa?** Không chọn cấu trúc chỉ vì “đều là hàng đợi”.
20. **Đã test input biên và so oracle cho lưới nhỏ chưa?** Đường đi, tính hợp lệ, optimum, thành phần và unreachable.
21. **Nếu chạy nhiều bộ test, visited/dist có được reset đúng không?**
22. **Nếu trạng thái có hash key, key có bất biến và equals/hashCode ổn định không?**

**Ghi nhớ:** lưới là một cách mô tả đồ thị, không phải một thuật toán riêng. Đỉnh có thể là **ô** hoặc một **cấu hình trạng thái phức tạp**; cạnh được **sinh tại chỗ** bằng quy tắc. BFS cho khoảng cách ít bước nhất khi mọi cạnh có cùng chi phí; DFS/BFS đều có thể flood fill vùng; multi-source BFS tìm khoảng cách gần nhất tới **tập nguồn**; 0-1 BFS giải đường đi tối ưu trên cạnh phí 0/1. Tính đúng phụ thuộc **định nghĩa state đủ thông tin, sinh đủ các chuyển hợp lệ, chọn đúng thuật toán theo trọng số và đánh dấu/relax/rollback thích hợp**.
