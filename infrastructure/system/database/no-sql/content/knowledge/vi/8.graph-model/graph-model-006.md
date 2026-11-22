# Đường đi, chu trình và yêu cầu chống duyệt lặp trong mô hình đồ thị

Cơ sở dữ liệu đồ thị (*graph database*) tổ chức dữ liệu thành **đỉnh/nút** (*vertex/node*) và **cạnh/quan hệ** (*edge/relationship*). Sức mạnh của mô hình này nằm ở việc đi từ một nút sang các nút liên quan: tìm bạn chung, truy vết phụ thuộc, kiểm tra đường vận chuyển, gợi ý sản phẩm hay phát hiện giao dịch đáng ngờ. Thao tác đi theo cạnh như vậy gọi là **duyệt đồ thị** (*graph traversal*).

Một vấn đề nền tảng xuất hiện ngay khi dữ liệu có liên kết vòng: từ A có thể đi đến B, rồi C, sau đó **quay trở lại A**. Nếu thuật toán không ghi nhớ những gì đã xử lý hoặc không đặt giới hạn phù hợp, nó có thể duyệt mãi, lặp lại cùng nút, tạo kết quả trùng hoặc tiêu tốn bộ nhớ rất lớn.

Bài học này làm rõ **đường đi**, **chu trình**, các quy tắc **chống duyệt lặp** theo từng mục đích truy vấn, rồi áp dụng vào BFS, DFS và truy vấn graph database. Trọng tâm là phân biệt **ngăn một thuật toán bị lặp vô hạn** với **chủ động cho phép quay lại nút khi nghiệp vụ cần tìm chu trình hoặc nhiều đường đi**.

## 1. Đồ thị mẫu để dùng xuyên suốt bài

Giả sử mỗi nút là một thành viên và quan hệ `FOLLOWS` có hướng: `A → B` nghĩa là A theo dõi B. Đây là **đồ thị có hướng** (*directed graph*); cạnh A → B không tự tạo cạnh B → A.

~~~mermaid
flowchart LR
  A((A)) --> B((B))
  A --> C((C))
  B --> C
  B --> D((D))
  C --> A
  C --> D
  D --> E((E))
  E --> C
  F((F))
~~~

Có thể viết lại thành danh sách kề (*adjacency list*):

~~~text
A: B, C
B: C, D
C: A, D
D: E
E: C
F: (không có cạnh đi ra)
~~~

Từ ví dụ này, ta quan sát được:

- A có thể tới E bằng `A → B → D → E` hoặc `A → C → D → E`.
- `A → B → C → A` tạo thành một **chu trình**.
- `C → D → E → C` là một chu trình khác.
- F không tới được E bằng cách chỉ đi theo chiều mũi tên.
- A có thể đi qua một chu trình rồi trở lại A, sau đó tiếp tục đi đến E, nếu cách định nghĩa đường đi cho phép lặp nút.

**Hướng cạnh là một phần của bài toán.** Nếu đổi `FOLLOWS` thành quan hệ hai chiều, tập đường đi và quy tắc phát hiện chu trình sẽ khác. Một quan hệ có hướng vẫn có thể được truy vấn theo chiều ngược, nhưng đó là lựa chọn của truy vấn, không phải một cạnh ngược đã tồn tại.

## 2. Thuật ngữ: walk, trail, path và cycle

Trong sách, tài liệu sản phẩm và ngôn ngữ truy vấn, từ *path* đôi khi được dùng theo nghĩa rộng hoặc hẹp. Để tránh hiểu nhầm, bài này dùng các định nghĩa sau cho **đồ thị có hướng**:

| Thuật ngữ | Định nghĩa | Có thể lặp nút? | Có thể lặp cạnh? |
| --- | --- | --- | --- |
| **Walk** (*hành trình/chuỗi duyệt*) | Chuỗi nút và cạnh liên tiếp, mỗi cạnh nối đúng hai nút kề nhau theo hướng cho phép | Có | Có |
| **Trail** | Walk không sử dụng lại cùng **cạnh** | Có | Không |
| **Simple path** (*đường đi đơn*) | Walk không lặp lại **nút** | Không | Không |
| **Closed walk** | Walk có nút đầu bằng nút cuối | Có | Có |
| **Simple cycle** (*chu trình đơn*) | Closed walk có ít nhất một cạnh, trong đó các nút không lặp ngoại trừ nút đầu cũng là nút cuối | Chỉ lặp đầu/cuối | Không lặp cạnh trong chu trình đơn thông thường |

Một số giáo trình gọi mọi chuỗi duyệt hợp lệ là *walk* và dành *path* cho trường hợp không lặp đỉnh. Một số graph query engine dùng *path* rộng hơn, tức là kết quả chứa các nút/cạnh đi qua nhưng **có thể lặp một số nút**. Khi chuyển từ toán học sang truy vấn thực tế, hãy đọc ngữ nghĩa *path uniqueness* của sản phẩm.

### 2.1. Ví dụ trên đồ thị A–F

| Chuỗi duyệt | Nhận xét |
| --- | --- |
| `A → B → D → E` | Đường đi đơn; từ A tới E có 3 cạnh |
| `A → C → D → E` | Một đường đi đơn khác từ A tới E |
| `A → B → C → A` | Closed walk và chu trình đơn |
| `C → D → E → C` | Chu trình đơn |
| `A → B → C → A → B` | Walk hợp lệ nhưng cạnh A → B được dùng lại, nên không phải trail hay simple path |
| `A → C → A → B → D → E` | Walk từ A tới E có lặp nút A; không phải simple path |

**Độ dài đường đi** thường được tính bằng **số cạnh**, không phải số nút. `A → B → D → E` có 4 nút nhưng độ dài 3. Một đường đi từ A tới chính A mà không đi qua cạnh nào có độ dài 0, thường được xem là *trivial path*, **không phải chu trình**.

Với đồ thị có hướng, một **self-loop** `A → A` tạo chu trình độ dài 1. Hai cạnh `A → B` và `B → A` tạo chu trình có hướng độ dài 2. Với đồ thị vô hướng đơn không có cạnh song song, chu trình thường có ít nhất 3 cạnh.

### 2.2. Đường đi có trọng số

Nếu mỗi cạnh mang trọng số, ví dụ khoảng cách hoặc chi phí:

~~~text
A --(1)--> B --(10)--> E
 \                         ^
  --(2)--> C --(2)--------/
~~~

Hai khái niệm **ít cạnh nhất** và **tổng trọng số nhỏ nhất** không còn giống nhau. Đường A → B → E có 2 cạnh và chi phí 11; A → C → E cũng có 2 cạnh nhưng chi phí 4.

Do đó cần hỏi rõ **“đường đi ngắn nhất” theo tiêu chí nào?**

- Với **đồ thị không trọng số**, hoặc mọi cạnh có cùng chi phí, BFS tìm đường có **ít cạnh nhất**.
- Với **trọng số không âm**, có thể xem xét Dijkstra.
- Với **trọng số âm**, Dijkstra không còn là lựa chọn chung an toàn; các thuật toán thích hợp khác cần xét và một chu trình tổng trọng số âm có thể khiến bài toán đường đi chi phí thấp nhất của walk trở nên không có cận dưới nếu cho phép đi vòng lặp.

Quy tắc chống lặp phải phù hợp thuật toán. Không thể lấy một `visited` đơn giản của BFS không trọng số rồi áp dụng y nguyên cho mọi thuật toán đường đi có trọng số.

## 3. Vì sao chu trình có thể làm quá trình duyệt không kết thúc?

Xem ý tưởng “từ A, lấy mọi láng giềng; với mỗi láng giềng, lại lấy mọi láng giềng”:

~~~text
A
└── B
    └── C
        └── A
            └── B
                └── C
                    └── A
                        ...
~~~

Vì đồ thị có cạnh `C → A`, quá trình mở rộng có thể lặp cùng ba nút mãi. Với một đồ thị hữu hạn, số **nút** là hữu hạn nhưng số **walk** có thể là vô hạn nếu cho phép đi vòng qua chu trình nhiều lần.

Một đoạn giả mã dễ gây lỗi:

~~~text
function traverse(node):
    process(node)
    for neighbor in outgoing(node):
        traverse(neighbor)
~~~

Thiếu điều kiện dừng và cơ chế ghi nhớ, hàm có thể gọi đệ quy đến khi hết stack. Dạng lặp với queue cũng có thể liên tục thêm A, B, C vào hàng đợi. Bên cạnh lặp vô hạn, đồ thị nhiều nhánh còn gây **bùng nổ số đường duyệt** ngay cả khi đã đặt giới hạn độ sâu.

Trong ứng dụng, hậu quả có thể là:

- API duyệt quan hệ chạy quá lâu hoặc timeout.
- Cùng người dùng/thiết bị xuất hiện lặp trong kết quả.
- CPU, bộ nhớ và số lần đọc database tăng mạnh.
- Duyệt qua các quan hệ không được phép nếu thiếu ràng buộc phạm vi.
- Một request có thể ảnh hưởng nhiều request khác khi tài nguyên dùng chung bị chiếm dụng.

**Chống duyệt lặp** vì vậy gồm hai quyết định: **đối tượng nào phải coi là đã duyệt?** và **trong phạm vi nào trạng thái đã duyệt có hiệu lực?**

## 4. Bốn kiểu truy vấn cần quy tắc chống lặp khác nhau

| Yêu cầu | Cần chống lặp gì? | Ví dụ |
| --- | --- | --- |
| **Tìm tất cả nút có thể đến** (*reachability*) | Không mở rộng lại cùng một nút trong một lượt duyệt | “Từ A có thể tới những ai?” |
| **Tìm đường ít cạnh nhất** trong đồ thị không trọng số | BFS đánh dấu nút khi đưa vào queue; lưu nút cha để dựng đường | “A tới E qua ít nhất bao nhiêu bước?” |
| **Liệt kê các đường đi đơn** | Tránh lặp nút **trên đường đang xét**, nhưng cho phép khám phá lại nút theo đường khác | “Có những đường đi đơn nào từ A tới E?” |
| **Tìm chu trình** | Cho phép nhận ra việc quay về nút đang nằm trên đường duyệt, hoặc so đầu/cuối theo đúng ngữ nghĩa cycle | “Có vòng phụ thuộc không?” |

Một quy tắc `visited` toàn cục không phù hợp với mọi hàng trong bảng:

- Với **reachability**, bỏ qua nút đã thăm là đúng: mục tiêu chỉ cần mỗi nút xuất hiện một lần.
- Với **enumeration**, nếu bỏ qua nút đã thăm trên *bất kỳ nhánh nào*, ta có thể làm mất những đường đi hợp lệ khác.
- Với **cycle detection**, chỉ biết một nút “đã thăm” chưa đủ kết luận có chu trình trong đồ thị có hướng. Cần biết nút đó có đang nằm trên **ngăn xếp đệ quy hiện tại** hay không.

Phân biệt này là cốt lõi của thiết kế traversal.

## 5. BFS: tìm đường ít cạnh nhất và ngăn lặp nút

**Breadth-First Search (BFS)** duyệt theo từng lớp khoảng cách: từ nút đầu, thăm các láng giềng trực tiếp, rồi tới những nút cách hai cạnh, ba cạnh, v.v.

Với đồ thị A–F:

~~~text
Bắt đầu tại A:
Lớp 0: A
Lớp 1: B, C
Lớp 2: D        (A đã thấy lại từ C nên bỏ qua)
Lớp 3: E
~~~

Một đường đi ít cạnh nhất từ A tới E là `A → B → D → E`. Đường `A → C → D → E` cũng có cùng độ dài 3; BFS dùng một biến `parent` thường chỉ trả về **một** trong các đường đi ngắn nhất, tùy thứ tự láng giềng.

### 5.1. Vì sao đánh dấu visited khi đưa vào queue?

Giả sử cả B lẫn C đều trỏ tới D. Nếu chỉ đánh dấu D **khi lấy D ra khỏi queue**, B có thể thêm D, sau đó C lại thêm D trước khi D được xử lý. Kết quả queue chứa cùng một nút nhiều lần.

Thực hành phổ biến với BFS tìm reachability/shortest unweighted là:

~~~text
visited.add(start)
queue.push(start)

while queue not empty:
    u = queue.popFront()
    for each v in outgoing(u):
        if v not in visited:
            visited.add(v)       <-- đánh dấu NGAY KHI thêm
            parent[v] = u
            queue.pushBack(v)
~~~

Nhờ đó một nút được thêm vào queue tối đa một lần trong lượt duyệt. `parent` lưu đường đi phát hiện đầu tiên tới nút; trong BFS không trọng số, đó là một đường đi có số cạnh tối thiểu.

### 5.2. Truy vết queue bằng tay

Với thứ tự láng giềng như danh sách kề ở phần 1:

| Lượt | Lấy khỏi queue | Nút được thêm | Queue sau lượt | `visited` sau lượt |
| --- | --- | --- | --- | --- |
| Khởi tạo | — | A | [A] | {A} |
| 1 | A | B, C | [B, C] | {A, B, C} |
| 2 | B | D; C đã thấy | [C, D] | {A, B, C, D} |
| 3 | C | Không; A, D đã thấy | [D] | {A, B, C, D} |
| 4 | D | E | [E] | {A, B, C, D, E} |
| 5 | E | Không; C đã thấy | [] | {A, B, C, D, E} |

Khi phát hiện E từ D, lưu `parent[E] = D`. Trước đó `parent[D] = B` và `parent[B] = A`. Đi ngược theo parent rồi đảo thứ tự thu được `A → B → D → E`.

### 5.3. Độ phức tạp

Với danh sách kề và `visited` dạng hash set, BFS duyệt toàn bộ phần đồ thị có thể tới có độ phức tạp thường là:

- **Thời gian:** `O(V + E)`, với V là số nút và E là số cạnh được xét.
- **Bộ nhớ:** `O(V)` cho queue, visited, depth và parent trong trường hợp xấu.

Đây là giới hạn theo kích thước đồ thị được duyệt; nếu graph database phải tải láng giềng qua mạng, độ trễ thực tế còn phụ thuộc số lần truy vấn, index, cache, phân vùng và phân phối dữ liệu.

## 6. Ví dụ Java: BFS có visited, parent và giới hạn độ sâu

Đoạn Java sau làm việc trên **đồ thị có hướng biểu diễn bằng danh sách kề**. Nó trả về một đường đi có số cạnh ít nhất từ `start` tới `target` trong phạm vi `maxDepth`; nếu không tìm thấy thì trả danh sách rỗng.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class GraphTraversalDemo {

    public static List<String> shortestUnweightedPath(
            Map<String, List<String>> graph,
            String start,
            String target,
            int maxDepth
    ) {
        if (maxDepth < 0) {
            throw new IllegalArgumentException("maxDepth must be >= 0");
        }

        Deque<String> queue = new ArrayDeque<>();
        Set<String> visited = new HashSet<>();
        Map<String, Integer> depth = new HashMap<>();
        Map<String, String> parent = new HashMap<>();

        queue.addLast(start);
        visited.add(start);
        depth.put(start, 0);

        while (!queue.isEmpty()) {
            String current = queue.removeFirst();

            if (current.equals(target)) {
                List<String> path = new ArrayList<>();
                for (String node = current; node != null;
                     node = parent.get(node)) {
                    path.add(node);
                }
                Collections.reverse(path);
                return path;
            }

            // Không mở rộng nút đã đạt giới hạn số cạnh.
            if (depth.get(current) >= maxDepth) {
                continue;
            }

            for (String next : graph.getOrDefault(current, List.of())) {
                // add trả false khi nút đã xuất hiện.
                if (visited.add(next)) {
                    parent.put(next, current);
                    depth.put(next, depth.get(current) + 1);
                    queue.addLast(next);
                }
            }
        }

        return List.of();
    }

    public static void main(String[] args) {
        Map<String, List<String>> graph = Map.of(
                "A", List.of("B", "C"),
                "B", List.of("C", "D"),
                "C", List.of("A", "D"),
                "D", List.of("E"),
                "E", List.of("C"),
                "F", List.of()
        );

        System.out.println(
                shortestUnweightedPath(graph, "A", "E", 3)
        ); // [A, B, D, E]

        System.out.println(
                shortestUnweightedPath(graph, "A", "E", 2)
        ); // []

        System.out.println(
                shortestUnweightedPath(graph, "F", "E", 5)
        ); // []
    }
}
~~~

Ví dụ dùng kiểu dữ liệu sẵn có trong Java, không cần kết nối cơ sở dữ liệu. Khi đổi sang graph database thật, một thao tác `outgoing(current)` có thể phải gửi truy vấn lấy quan hệ kề. Nếu mỗi nút lại thực hiện một round trip riêng, vấn đề **N+1 queries** và độ trễ mạng sẽ xuất hiện; một graph query engine thường có cơ chế duyệt quan hệ phía máy chủ để tránh phải đưa toàn bộ quá trình sang client.

**Giới hạn `maxDepth` chỉ giới hạn số cạnh trên đường đi**, không tự động bảo đảm truy vấn nhẹ. Một nút có hàng triệu láng giềng vẫn có thể rất tốn kém ở độ sâu 1. Với API thật còn cần số nút/cạnh tối đa được duyệt, timeout, cancellation và giới hạn tài nguyên.

## 7. DFS: duyệt sâu và phát hiện chu trình

**Depth-First Search (DFS)** đi sâu theo một nhánh trước khi quay lui. DFS cũng có thể dùng `visited` để tìm các nút có thể tới. Nhưng để phát hiện **chu trình có hướng**, cần phân biệt ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **WHITE / 0** | Chưa vào DFS |
| **GRAY / 1** | Đã vào DFS và **đang ở trên nhánh gọi đệ quy hiện tại** |
| **BLACK / 2** | Đã xử lý xong toàn bộ cạnh đi ra và rời nhánh hiện tại |

Khi DFS xét cạnh `u → v`:

1. Nếu v **WHITE**, tiếp tục DFS từ v.
2. Nếu v **GRAY**, cạnh đi tới một tổ tiên đang hoạt động ⇒ phát hiện **chu trình có hướng**.
3. Nếu v **BLACK**, v đã xử lý xong trên một nhánh trước; **không kết luận có chu trình chỉ vì v từng được thăm**.

### 7.1. Vì sao visited dạng boolean là chưa đủ?

Xét một đồ thị **không có chu trình**:

~~~text
A -> B -> C
 \------> C
~~~

DFS từ A có thể đi A → B → C, đánh dấu C đã thăm, rồi quay lại A xét cạnh A → C. Việc thấy C “đã thăm” **không chứng minh có chu trình**: C đã hoàn tất và không nằm trong chuỗi gọi đang hoạt động.

Nếu thuật toán báo chu trình cho mọi cạnh đi đến nút `visited`, nó sẽ tạo **false positive**. Màu GRAY giúp tách trường hợp **quay về tổ tiên đang mở** khỏi **nút đã xử lý xong**.

### 7.2. Giả mã phát hiện chu trình có hướng

~~~text
state[v] ∈ {WHITE, GRAY, BLACK}; ban đầu tất cả WHITE

function dfsCycle(u):
    state[u] = GRAY

    for v in outgoing(u):
        if state[v] == GRAY:
            return true

        if state[v] == WHITE and dfsCycle(v):
            return true

    state[u] = BLACK
    return false

function hasDirectedCycle(graph):
    for u in allVertices:
        if state[u] == WHITE and dfsCycle(u):
            return true

    return false
~~~

Cần bắt đầu DFS ở **từng thành phần chưa thăm**, vì đồ thị có thể không liên thông. Trong ví dụ A–F, thuật toán phát hiện ít nhất chu trình A → B → C → A hoặc C → D → E → C, tùy thứ tự xét cạnh.

Với danh sách kề, phát hiện chu trình có hướng bằng DFS ba màu có độ phức tạp thời gian `O(V + E)` và bộ nhớ `O(V)`, chưa tính dữ liệu đồ thị đầu vào. Đệ quy trên đồ thị rất sâu có nguy cơ **tràn stack**; với graph lớn nên xem xét phiên bản DFS dùng stack tường minh hoặc thuật toán thích hợp của nền tảng.

### 7.3. Đồ thị vô hướng có cách kiểm tra khác

Với cạnh vô hướng giữa A và B, duyệt từ A tới B rồi nhìn thấy A trong danh sách láng giềng của B là bình thường. Đó là cạnh vừa đi qua, không phải bằng chứng về chu trình.

Trong **đồ thị vô hướng đơn**, DFS thường bỏ qua cạnh quay về `parent`; nếu gặp một đỉnh đã thăm khác parent thì có chu trình. Nhưng nếu đồ thị cho phép **cạnh song song**, chỉ so sánh parent node có thể không đủ: cần nhận diện và bỏ qua đúng **edge ID** đã dùng để tới nút hiện tại. Self-loop cũng cần được xử lý theo định nghĩa chu trình của mô hình.

**Không lấy thuật toán DFS ba màu của đồ thị có hướng áp dụng nguyên xi cho đồ thị vô hướng** mà không xét ngữ nghĩa cạnh ngược và edge ID.

## 8. Chống lặp theo nút, theo cạnh và theo đường đi hiện tại

Tùy nghiệp vụ, đơn vị chống lặp có thể khác nhau:

### 8.1. Không lặp nút toàn cục trong một lượt traversal

Dùng `visitedNodes` chung cho toàn bộ BFS/DFS khi mục tiêu là **tìm nút có thể tới** hoặc lấy **một đường ngắn nhất** theo số cạnh.

~~~text
A → B → D
 \→ C → D

visited toàn cục:
  D chỉ cần được khám phá một lần để biết A tới được D.
~~~

Cách này tiết kiệm công việc vì không cần khám phá lại cả cây con của D.

### 8.2. Không lặp nút trên một đường đi đang xét

Khi yêu cầu **liệt kê mọi đường đi đơn** từ A đến D, phải giữ `onCurrentPath` theo từng nhánh:

~~~text
Đường hợp lệ 1: A → B → D
Đường hợp lệ 2: A → C → D
~~~

Nếu dùng `visited` toàn cục, lần đầu tìm thấy D qua B có thể khiến nhánh qua C bị bỏ qua. Cách đúng cho bài toán liệt kê là **đánh dấu khi đi vào và bỏ đánh dấu khi quay lui**:

~~~text
function enumerateSimplePaths(u, target, currentPath, onPath):
    if u == target:
        emit(copy(currentPath))
        return

    for v in outgoing(u):
        if v not in onPath:
            onPath.add(v)
            currentPath.push(v)

            enumerateSimplePaths(v, target, currentPath, onPath)

            currentPath.pop()
            onPath.remove(v)
~~~

Khi gọi, `currentPath` đã chứa nút bắt đầu và `onPath` cũng chứa nút đó. Mỗi đường kết quả không lặp nút, nhưng một nút có thể xuất hiện trong **nhiều đường kết quả khác nhau**.

**Chi phí:** số simple path giữa hai nút có thể tăng theo cấp số mũ trên những đồ thị có nhiều nhánh. Chống lặp nút giúp các đường đi hữu hạn trên đồ thị hữu hạn, nhưng **không bảo đảm số kết quả nhỏ**. Khi phục vụ API, cần đặt `maxDepth`, `maxPaths`, timeout và quy định rõ có cho phép bỏ qua kết quả sau ngưỡng hay không.

### 8.3. Không lặp cạnh trên một đường đi

Một số bài toán cho phép thăm lại nút nhưng **không dùng lại cùng quan hệ**. Ví dụ mạng đường hai chiều được biểu diễn bằng các cạnh có hướng riêng biệt, đường đi A → B → A có thể sử dụng hai cạnh khác nhau nếu cả hai thực sự tồn tại.

Đối với *trail*, trạng thái cần theo dõi là **tập edge ID đã có trên đường đang xét**. Chỉ lưu cặp nút đầu/cuối có thể không đủ nếu hai nút nối với nhau bằng nhiều cạnh song song khác ID.

Điều này đặc biệt quan trọng khi cơ sở dữ liệu đồ thị coi **mỗi quan hệ có định danh riêng**; hai quan hệ cùng loại và cùng hai đầu vẫn có thể là hai relationship khác nhau.

### 8.4. Không “cấm lặp” khi chính mục tiêu là tìm chu trình

Để phát hiện chu trình, cần cho phép **so khớp việc quay về nút khởi đầu hoặc tổ tiên hiện hành**. Nếu loại bỏ mọi cạnh dẫn tới nút đã ở trên đường trước khi kiểm tra điều kiện cycle, thuật toán sẽ bỏ qua chính bằng chứng cần tìm.

Quy tắc đúng là **phát hiện sự quay lại rồi kết thúc/ghi nhận có kiểm soát**, chứ không phải im lặng bỏ qua mọi lần gặp lại.

## 9. Tìm chu trình trong nghiệp vụ đồ thị

Chu trình không mặc nhiên là lỗi. Ý nghĩa phụ thuộc **loại quan hệ**:

| Miền nghiệp vụ | Quan hệ | Chu trình có ý nghĩa gì? |
| --- | --- | --- |
| Mạng xã hội | A theo dõi B | Hoàn toàn có thể tồn tại nhóm theo dõi vòng |
| Sơ đồ phụ thuộc build | Module A phụ thuộc B | Chu trình có thể làm thứ tự build hoặc giải quyết phụ thuộc không hợp lệ |
| Sắp xếp công việc | Công việc A phải xong trước B | Chu trình làm thứ tự thực hiện bất khả thi |
| Tổ chức dạng cây | Nhân viên A quản lý B | Vòng quản lý thường vi phạm mô hình phân cấp |
| Liên kết trang web | Trang A liên kết B | Chu trình thường hợp lệ và rất phổ biến |
| Giao dịch chuyển tiền | Tài khoản A chuyển cho B | Chu trình có thể là tín hiệu để phân tích, không tự chứng minh gian lận |

Nếu nghiệp vụ yêu cầu quan hệ `DEPENDS_ON` là **đồ thị không chu trình có hướng** (*Directed Acyclic Graph — DAG*), thêm cạnh mới `u → v` có thể tạo chu trình khi **đã tồn tại đường đi từ v trở lại u**.

~~~text
Hiện tại: A → B → C
Đề nghị thêm: C → A

Kiểm tra trước khi thêm C → A:
  có đường đi A → ... → C không?
  Có: A → B → C
  => thêm C → A sẽ tạo chu trình.
~~~

Điều kiện này áp dụng để bảo toàn DAG khi **đồ thị hiện tại đã không có chu trình**. Nếu dữ liệu đang chứa chu trình từ trước, kiểm tra riêng cạnh mới không chứng minh toàn bộ đồ thị sạch.

Trong hệ nhiều người ghi đồng thời, **hai yêu cầu thêm cạnh** có thể cùng kiểm tra “chưa có đường quay lại” trên các snapshot cũ rồi tạo chu trình sau khi cả hai ghi. Nếu không được phép có chu trình, việc kiểm tra và ghi cần cơ chế phối hợp đồng thời phù hợp (ví dụ khóa, transaction hoặc thực thi tuần tự trong phạm vi được bảo vệ). Kiểm tra trước ghi ở client đơn thuần chưa đủ.

## 10. Truy vấn đường đi trong graph database

BFS/DFS ở trên giúp hiểu thuật toán; một graph database thường cung cấp ngôn ngữ riêng để diễn đạt **mẫu quan hệ** và duyệt nhiều bước. Ví dụ dưới dùng cú pháp **Cypher** thường gặp trong Neo4j. Hành vi và cú pháp chi tiết có thể khác theo phiên bản, vì vậy khi triển khai cần xem tài liệu phiên bản đang dùng.

### 10.1. Tạo đồ thị thử nghiệm nhỏ

Đoạn Cypher minh họa tạo sáu nút thuộc nhãn `LabNode` và các quan hệ `LINK` theo đồ thị A–F:

~~~cypher
CREATE
  (a:LabNode {code: 'A'}),
  (b:LabNode {code: 'B'}),
  (c:LabNode {code: 'C'}),
  (d:LabNode {code: 'D'}),
  (e:LabNode {code: 'E'}),
  (f:LabNode {code: 'F'}),
  (a)-[:LINK]->(b),
  (a)-[:LINK]->(c),
  (b)-[:LINK]->(c),
  (b)-[:LINK]->(d),
  (c)-[:LINK]->(a),
  (c)-[:LINK]->(d),
  (d)-[:LINK]->(e),
  (e)-[:LINK]->(c);
~~~

Đây là ví dụ học tập; chạy lại `CREATE` có thể tạo thêm nút/cạnh trùng về mặt nghiệp vụ. Hãy dùng database thực hành riêng hoặc quy trình reset dữ liệu thích hợp trước lần chạy lại.

### 10.2. Tìm đường đi từ A tới E với độ sâu giới hạn

~~~cypher
MATCH p = (a:LabNode {code: 'A'})-[:LINK*1..4]->(e:LabNode {code: 'E'})
RETURN [n IN nodes(p) | n.code] AS nodeCodes,
       length(p) AS hops
ORDER BY hops
LIMIT 20;
~~~

Mẫu `[:LINK*1..4]` cho phép duyệt từ 1 đến 4 quan hệ có hướng loại `LINK`. `nodes(p)` trả các nút trên path, `length(p)` là số quan hệ. Kết quả có thể chứa nhiều đường, không chỉ đường ngắn nhất.

Điểm cần lưu ý:

- **Giới hạn độ sâu** làm rõ phạm vi traversal.
- **`LIMIT 20` giới hạn số dòng kết quả trả về**, nhưng không nên coi đây là bảo đảm chắc chắn về tổng lượng công việc mở rộng trong mọi kế hoạch thực thi.
- Ngữ nghĩa **duy nhất của nút và quan hệ trên path** tùy mẫu truy vấn, chế độ match và phiên bản engine. Trong Cypher truyền thống, một relationship thường không được dùng lại trong cùng một path match, nhưng **node vẫn có thể xuất hiện nhiều lần**. Do đó, một path trả về chưa chắc là *simple path* theo định nghĩa toán học.
- Nếu mục tiêu là mọi simple path, cần áp dụng ràng buộc không lặp nút và cân nhắc chi phí liệt kê.

### 10.3. Lọc đường đi đơn bằng điều kiện không lặp nút

Một cách biểu diễn quy tắc “mỗi nút trong path chỉ xuất hiện một lần”:

~~~cypher
MATCH p = (a:LabNode {code: 'A'})-[:LINK*1..4]->(e:LabNode {code: 'E'})
WHERE all(n IN nodes(p)
          WHERE single(m IN nodes(p) WHERE m = n))
RETURN [n IN nodes(p) | n.code] AS simplePath
LIMIT 20;
~~~

Điều kiện `single(m IN nodes(p) WHERE m = n)` kiểm tra mỗi nút `n` xuất hiện đúng một lần trong danh sách các nút của path. Đây là một cách **diễn đạt tính duy nhất**, nhưng việc filter sau khi khớp mẫu không mặc nhiên khiến kế hoạch truy vấn tránh được mọi nhánh bị loại từ sớm. Với graph lớn, cần xem execution plan và khả năng tối ưu/path uniqueness của engine.

### 10.4. Tìm walk quay lại điểm xuất phát

~~~cypher
MATCH p = (a:LabNode {code: 'A'})-[:LINK*2..5]->(end:LabNode)
WHERE end = a
RETURN [n IN nodes(p) | n.code] AS closedWalk,
       length(p) AS hops
LIMIT 20;
~~~

Truy vấn này tìm các path kết thúc ở chính A. Kết quả như `A → B → C → A` là một chu trình đơn, nhưng **không phải mọi closed walk đều là chu trình đơn** nếu các nút bên trong lặp lại. Muốn tìm *simple cycle* cần thêm điều kiện không lặp các nút **bên trong**, đồng thời cho phép nút đầu bằng nút cuối.

Để kiểm tra **có hay không** chu trình, thường không cần tải hàng loạt path; có thể dùng thuật toán phát hiện cycle được hệ hỗ trợ, hoặc traversal với điều kiện dừng ngay khi có bằng chứng.

### 10.5. Tối ưu truy cập tới nút bắt đầu

Trong dữ liệu lớn, truy vấn nên tìm nhanh nút khởi đầu bằng **khóa/thuộc tính có index**, rồi mới mở rộng theo quan hệ. Nếu thiếu index hoặc không biết nút bắt đầu, engine có thể phải quét nhiều nút trước khi traversal.

Nhãn `LabNode` và `code` trong ví dụ chỉ phục vụ bài thực hành. Trong hệ thật, có thể tạo ràng buộc duy nhất/index cho ID nghiệp vụ của nút, phân biệt tenant và kiểm soát quyền được đi qua các loại quan hệ.

## 11. Giới hạn duyệt: độ sâu, độ rộng và số kết quả

Ngăn quay lại nút giúp giải quyết lặp vô hạn ở bài toán reachability, nhưng **không giải quyết hết bùng nổ tìm kiếm**. Nếu trung bình mỗi nút có `b` quan hệ đi ra, số chuỗi bước dài `d` có thể tăng gần theo `b^d` trước khi loại các nhánh trùng hoặc không thỏa điều kiện.

Ví dụ một người có 100 kết nối, mỗi kết nối lại có 100 kết nối khác:

~~~text
Độ sâu 1: có thể xét khoảng 100 cạnh
Độ sâu 2: có thể xét khoảng 10.000 chuỗi hai cạnh
Độ sâu 3: có thể xét khoảng 1.000.000 chuỗi ba cạnh
~~~

Các số trên minh họa **số nhánh tiềm năng** nếu không xét trùng lặp, không phải số nút duy nhất hoặc dự báo chính xác hiệu năng. Đồ thị thực có thể có nhiều cạnh quay lại, degree phân bố lệch và chỉ mục khác nhau.

Khi xây API traversal cần xác định:

| Ràng buộc | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **`maxDepth`** | Số bước quan hệ tối đa trên một path | Chỉ xem bạn trong 3 cấp |
| **`maxVisitedNodes`** | Số nút duy nhất được phép mở rộng | Dừng khi đã thấy 50.000 nút |
| **`maxExpandedEdges`** | Giới hạn số cạnh đã xét | Tránh nút cực nhiều láng giềng |
| **`maxResults`** | Số đường/nút trả về | Trả tối đa 100 gợi ý |
| **Deadline/timeout** | Không giữ tài nguyên vượt thời gian | Hủy request khi quá hạn |
| **Relation filter** | Chỉ duyệt loại cạnh cần thiết | `FOLLOWS` nhưng bỏ `BLOCKED` |
| **Scope/tenant filter** | Ngăn vượt ranh giới dữ liệu | Chỉ tìm trong tổ chức hiện tại |
| **Cycle policy** | Nút/cạnh được lặp trong từng path hay không | Simple path hoặc trail |

Khi áp dụng giới hạn, API cần nói rõ kết quả là **đầy đủ hay bị cắt**, và kết quả “không tìm thấy” là do thực sự không có đường hay do đã đạt ngưỡng tìm kiếm. Tránh trả “không có quan hệ” khi thực tế chỉ mới duyệt đến độ sâu 3.

## 12. Các bẫy thuật toán thường gặp

### 12.1. Một visited dùng cho nhiều request

`visited` phục vụ một lần duyệt. Nếu giữ bộ visited toàn cục giữa các truy vấn A→E và F→E, kết quả lần sau có thể bị ảnh hưởng bởi lịch sử lần trước. Thông thường mỗi request/traversal phải có **trạng thái visited riêng** hoặc một cấu trúc chia sẻ có ngữ nghĩa được xác định rất rõ.

### 12.2. Đánh dấu visited quá muộn

Nếu BFS chỉ đánh dấu khi lấy khỏi queue, cùng một nút có thể bị đưa vào queue nhiều lần khi có nhiều cạnh dẫn tới nó. Với reachability và shortest path không trọng số, hãy đánh dấu **khi enqueue**.

### 12.3. Coi “đã thăm” là “đang nằm trên đường DFS”

Trong đồ thị có hướng, cạnh tới nút đã hoàn tất (BLACK) không phải là bằng chứng về chu trình. Phát hiện cycle bằng DFS cần màu GRAY hoặc trạng thái tương đương của **recursion stack**.

### 12.4. Dùng global visited để tìm tất cả đường đi

Nút D được đi đến qua hai nhánh A→B→D và A→C→D. Global visited sẽ loại một nhánh, làm thiếu kết quả. Với simple paths, dùng tập nút **trên đường hiện tại**, bỏ dấu khi backtrack.

### 12.5. Chỉ giới hạn số kết quả, không giới hạn số bước

`LIMIT 10` không nhất thiết ngăn engine khám phá một tập path khổng lồ trước khi có đủ kết quả hợp lệ, đặc biệt khi có nhiều filter hoặc sort. Giới hạn `maxDepth` và điều kiện cắt nhánh càng sớm càng tốt.

### 12.6. Bỏ qua quan hệ có hướng

Cạnh A→B không chứng minh B→A. Nếu nghiệp vụ thực sự hai chiều, phải định nghĩa cách lưu hoặc cách truy vấn cho quan hệ hai chiều. Nếu chỉ có một hướng, không tự thêm chiều ngược trong thuật toán.

### 12.7. Không phân biệt node ID và edge ID

Có thể có nhiều cạnh song song cùng nối A và B nhưng có ID riêng hoặc thuộc loại khác nhau. Một `visitedEdges` dựa trên cặp (A,B) có thể gộp nhầm các cạnh đó. Khi bài toán quan tâm quan hệ, cần dùng **định danh cạnh**.

### 12.8. Thay đổi đồ thị trong lúc duyệt

Trong graph database đang có ghi đồng thời, một cạnh có thể được tạo hoặc xóa khi truy vấn đang chạy. Tùy isolation và consistency model, traversal có thể thấy một snapshot nhất định hoặc một trạng thái theo chính sách khác. Nếu cần câu trả lời nhất quán theo một thời điểm, phải kiểm tra bảo đảm transaction/snapshot của sản phẩm, thay vì giả định mọi lượt mở rộng thấy cùng một đồ thị bất biến.

### 12.9. Duyệt qua quan hệ không được phép

Nếu graph nhiều tenant, đường A→B→C có thể qua B thuộc tenant khác. Chỉ kiểm tra quyền ở nút đầu và nút cuối là chưa đủ nếu policy cấm đi qua dữ liệu trung gian. Phải đưa **điều kiện quyền và phạm vi** vào quá trình duyệt theo ngữ nghĩa nghiệp vụ.

## 13. Tình huống thực tế: phụ thuộc dịch vụ và phát hiện vòng

Giả sử hệ thống có các service và cạnh `DEPENDS_ON`:

~~~text
API → Auth
API → Catalog
Catalog → Search
Search → Cache
~~~

Đây là DAG nếu không có cạnh nào quay ngược lại các nút tổ tiên. Bây giờ một thay đổi cấu hình muốn thêm `Cache → API`. Sau khi thêm cạnh này sẽ có chu trình:

~~~text
API → Catalog → Search → Cache → API
~~~

Để tránh cấu hình lỗi:

1. Xác định cạnh dự kiến thêm `Cache → API`.
2. Trước khi ghi, duyệt theo cạnh `DEPENDS_ON` từ **API** xem có tới **Cache** hay không.
3. Nếu có đường `API → Catalog → Search → Cache`, từ chối cạnh mới vì tạo vòng.
4. Nếu không tìm thấy, chỉ chấp nhận khi kiểm tra đã đủ phạm vi và việc kiểm tra–ghi được bảo vệ trước thay đổi đồng thời có thể phá vỡ bất biến DAG.

Bài toán này ưu tiên **reachability** hơn liệt kê tất cả đường đi. Chỉ cần phát hiện **một đường** từ API tới Cache là đủ chứng minh thêm cạnh mới sẽ tạo vòng. Duyệt mọi simple path là tốn công không cần thiết.

Ngược lại, khi điều tra vì sao một service bị ảnh hưởng gián tiếp, kỹ sư có thể cần **nhiều đường phụ thuộc khác nhau**. Khi đó dùng `onCurrentPath` để liệt kê các đường đơn trong một giới hạn, thay vì global visited vốn chỉ giữ một cách tới mỗi nút.

## 14. Tình huống thực tế: mạng xã hội có liên kết vòng

Một mạng xã hội có quan hệ:

~~~text
An → Binh
Binh → Chi
Chi → An
An → Dung
Chi → Dung
~~~

Nếu cần danh sách những người có thể tiếp cận từ An trong tối đa 3 bước, BFS với visited theo **userId** giúp mỗi tài khoản chỉ xuất hiện một lần.

Nếu cần giải thích vì sao Dung là gợi ý kết nối, ứng dụng có thể muốn biết hai đường:

~~~text
An → Dung
An → Binh → Chi → Dung
~~~

Một visited toàn cục chỉ bảo đảm reachability và có thể không cung cấp đủ các đường giải thích. Nếu muốn trả nhiều lý do gợi ý, có thể lưu nhiều tiền nhiệm trong các đường đi ngắn nhất hoặc liệt kê simple paths có ràng buộc độ sâu/kết quả.

Nếu cần tìm nhóm theo dõi vòng, phải cho phép chu trình An→Binh→Chi→An như một kết quả hợp lệ, đồng thời tránh xuất ra vô số biến thể lặp đi lặp lại của cùng vòng.

Với chu trình, còn có chuyện **khử trùng kết quả**: vòng A→B→C→A và B→C→A→B có thể là **cùng một chu trình** chỉ khác nút bắt đầu. Tùy mục tiêu, hệ có thể cần quy tắc chuẩn hóa thứ tự biểu diễn chu trình; nếu cạnh có hướng, không được tự xem vòng theo chiều ngược là tương đương khi những cạnh ngược không tồn tại.

## 15. Bài tập luyện tư duy

### Bài 1: phân loại đường đi

Cho đồ thị phần 1, phân loại:

1. `A → B → D → E`
2. `A → B → C → A`
3. `A → C → A → B`
4. `C → D → E → C`

**Gợi ý:** (1) simple path, độ dài 3; (2) và (4) là simple cycle/closed walk; (3) là walk có lặp nút A nên không phải simple path. Các nhận xét dựa trên những cạnh thực sự có trong đồ thị có hướng.

### Bài 2: BFS và visited

Tại sao sau khi xét A, B và C đều được đưa vào queue, nhưng D chỉ được đưa vào queue một lần?

**Gợi ý:** Khi mở rộng B, D được thêm vào `visited` ngay lúc enqueue. Khi mở rộng C và thấy cạnh C→D, việc `visited.add(D)` không thành công nên D không bị enqueue thêm.

### Bài 3: kết quả tìm đường đi đơn

Hai đường `A → B → D → E` và `A → C → D → E` có hợp lệ không? Có nên dùng một global visited nếu mục tiêu là trả về **cả hai**?

**Gợi ý:** Cả hai hợp lệ, đều có độ dài 3. Global visited phù hợp để biết E có thể tới và lấy một đường ngắn nhất, nhưng có thể loại một đường khác. Liệt kê cần trạng thái theo đường hiện tại hoặc cơ chế lưu nhiều đường/tiền nhiệm.

### Bài 4: phát hiện chu trình có hướng

Đồ thị mới có A→B, B→C, A→C. Nếu khi DFS từ A gặp cạnh tới C đã được thăm rồi báo có cycle, kết luận có đúng không?

**Gợi ý:** Sai. Đồ thị không có chu trình. C đã hoàn tất (BLACK) sau nhánh A→B→C. Cạnh A→C không quay lại nút đang GRAY. Phải phân biệt hai trạng thái.

### Bài 5: bảo vệ DAG

Đồ thị có X→Y và Y→Z. Ứng dụng muốn thêm Z→X. Cần kiểm tra reachability theo hướng nào?

**Gợi ý:** Kiểm tra có đường từ X tới Z trước khi thêm Z→X. Có X→Y→Z, nên thêm cạnh sẽ tạo cycle X→Y→Z→X.

### Bài 6: giới hạn độ sâu

API tìm đường đi A→E với `maxDepth = 2` trả “không tìm thấy”. Kết luận có thể đưa ra là gì?

**Gợi ý:** “Không tìm thấy đường có **tối đa 2 cạnh** trong phạm vi truy vấn.” Không thể kết luận A không tới được E, vì trong đồ thị mẫu tồn tại đường có 3 cạnh.

### Bài 7: cạnh song song

Giữa A và B có hai quan hệ riêng biệt: một quan hệ `MENTORS` và một quan hệ `FOLLOWS`. Nếu cần liệt kê các trail không dùng lại cùng relationship, `visitedEdges` nên lưu gì?

**Gợi ý:** Lưu **ID của từng relationship**, không chỉ cặp hai nút A,B; hai quan hệ có thể cùng đầu/cuối nhưng vẫn là cạnh riêng.

### Bài 8: chọn phương pháp

Ghép yêu cầu với cách tiếp cận:

| Yêu cầu | Hướng tiếp cận |
| --- | --- |
| Liệt kê mỗi nút có thể tới đúng một lần | BFS/DFS với visited toàn cục trong một lượt duyệt |
| Tìm đường ít cạnh nhất | BFS với visited khi enqueue và parent |
| Kiểm tra đồ thị có hướng chứa cycle | DFS ba màu hoặc thuật toán cycle detection tương đương |
| Liệt kê nhiều simple path | Backtracking với onCurrentPath và giới hạn kết quả |
| Phát hiện trước khi thêm một cạnh tạo cycle trong DAG | Kiểm tra đường đi từ đích cạnh mới trở lại nguồn của cạnh mới |
| Tìm đường tổng trọng số nhỏ nhất với trọng số không âm | Thuật toán đường đi có trọng số như Dijkstra |

Hãy giải thích **vì sao** quy tắc visited hợp lệ cho từng trường hợp, thay vì chỉ nêu tên thuật toán.

## 16. Ghi nhớ khi thiết kế traversal trên NoSQL đồ thị

**Đường đi** nói về chuỗi các nút và quan hệ nối với nhau. **Chu trình** xuất hiện khi có thể đi theo cạnh để quay lại nút ban đầu; trong đồ thị thực tế, chu trình có thể là liên kết hoàn toàn hợp lệ hoặc là lỗi nghiệp vụ. **Chống duyệt lặp** là một phần của ngữ nghĩa truy vấn và của quản lý tài nguyên.

Quy tắc cần nhớ:

1. **Reachability và BFS ít cạnh nhất:** dùng `visited` theo nút trong một lần duyệt, đánh dấu khi enqueue.
2. **Cycle detection trên đồ thị có hướng:** cần biết nút nào đang nằm trên nhánh DFS (GRAY), không chỉ biết đã từng thăm.
3. **Liệt kê simple paths:** chống lặp theo nút **trong đường hiện tại**, rồi bỏ dấu khi backtrack để không làm mất đường khác.
4. **Trail:** chống lặp bằng ID cạnh; lặp nút có thể được phép.
5. **Truy vấn đồ thị thực tế:** luôn xác định hướng cạnh, loại quan hệ, độ sâu, phạm vi truy cập, chính sách lặp và giới hạn tài nguyên.

Khi gặp câu hỏi “tìm đường qua đồ thị”, trước tiên hãy làm rõ **cần một đường hay mọi đường, đường ít cạnh hay ít chi phí, có cho phép lặp đỉnh/cạnh không, muốn phát hiện hay loại trừ chu trình**. Sau đó mới chọn BFS, DFS, truy vấn đường đi hay thuật toán phù hợp.
