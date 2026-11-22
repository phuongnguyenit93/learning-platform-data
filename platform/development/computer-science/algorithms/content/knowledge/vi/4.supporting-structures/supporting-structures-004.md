# Hàng đợi và hàng đợi hai đầu trong duyệt dữ liệu

## 1. Vì sao thuật toán duyệt cần hàng đợi?

Trong quá trình duyệt cây, đồ thị, mảng, lưới hoặc luồng sự kiện, nhiều phần tử được phát hiện trước khi đến lượt xử lý. Một cấu trúc lưu **các phần tử đang chờ** quyết định phần tử nào được xử lý trước; điều đó có thể ảnh hưởng tới tính đúng và độ phức tạp.

- **Hàng đợi (queue)** theo nguyên tắc **FIFO — First In, First Out**: vào trước, ra trước. Ta thêm phần tử ở cuối và lấy ra từ đầu.
- **Hàng đợi hai đầu (deque, double-ended queue)** cho phép thêm và lấy **ở cả đầu lẫn cuối**. Queue là một cách sử dụng deque, nhưng deque hỗ trợ thêm các chiến lược giữ ứng viên hoặc thay đổi thứ tự ưu tiên đặc biệt.
- **Ngăn xếp (stack)** theo **LIFO — Last In, First Out**: vào sau, ra trước. Stack thường được dùng cho DFS, còn queue FIFO thường dùng cho BFS.
- **PriorityQueue** khác queue FIFO: phần tử có ưu tiên cao hơn được lấy trước, bất kể thời điểm được thêm.

Ví dụ, thêm A, B, C theo thứ tự vào queue rồi lần lượt lấy ra sẽ được A, B, C. Với deque, thêm B vào cuối, thêm A vào đầu, thêm C vào cuối tạo [A, B, C]. Có thể lấy A từ đầu hoặc C từ cuối. Hai đầu của deque là **hai vị trí thao tác**, không có nghĩa nội dung tự được sắp xếp.

## 2. Hợp đồng thao tác và API Java 17+

| Ý định | Phương thức Deque | Khi rỗng hoặc không thể thêm |
|---|---|---|
| Thêm cuối | addLast(x), offerLast(x) | addLast có thể ném ngoại lệ; offerLast trả boolean |
| Thêm đầu | addFirst(x), offerFirst(x) | tương tự |
| Lấy đầu | removeFirst(), pollFirst() | removeFirst ném NoSuchElementException; pollFirst trả null |
| Lấy cuối | removeLast(), pollLast() | removeLast ném NoSuchElementException; pollLast trả null |
| Xem đầu | getFirst(), peekFirst() | getFirst ném lỗi; peekFirst trả null |
| Xem cuối | getLast(), peekLast() | getLast ném lỗi; peekLast trả null |

Java cung cấp các giao diện **java.util.Queue<E>**, **java.util.Deque<E>** và lớp **java.util.ArrayDeque<E>**. Với Queue, offer/poll/peek lần lượt tương ứng thêm cuối, lấy đầu và xem đầu. Khi thuật toán thật sự thao tác hai đầu, các tên addFirst, addLast, removeFirst, removeLast dễ đọc hơn.

**ArrayDeque** thường là lựa chọn tốt cho thao tác ở hai đầu trong ứng dụng đơn luồng. Nó sử dụng vùng lưu trữ dạng mảng có thể mở rộng; thao tác ở hai đầu có thời gian **O(1) khấu hao**, đôi khi phải mở rộng mảng nên một thao tác thêm đơn lẻ có thể tốn O(n). Duyệt toàn bộ n phần tử vẫn tốn O(n). ArrayDeque không cho phép null; trả về null từ pollFirst hoặc peekFirst có thể được hiểu là deque rỗng.

**Không dùng deque như mảng truy cập ngẫu nhiên:** deque được tối ưu cho hai đầu, không hỗ trợ truy cập phần tử thứ i với chi phí O(1) như ArrayList. ArrayDeque cũng không an toàn nếu nhiều luồng thay đổi đồng thời; bài toán producer–consumer phải chọn cấu trúc đồng thời/đồng bộ phù hợp như BlockingQueue hoặc ConcurrentLinkedQueue.

## 3. Queue FIFO trong BFS: duyệt theo lớp

Trong đồ thị không trọng số, **Breadth-First Search (BFS)** bắt đầu từ đỉnh nguồn s và duyệt dần theo số cạnh của đường đi ngắn nhất từ s:

- **Lớp 0:** đỉnh nguồn.
- **Lớp 1:** các đỉnh kề chưa thăm, tới được bằng một cạnh.
- **Lớp 2:** các đỉnh lần đầu tới được bằng hai cạnh.
- Tiếp tục cho tới khi queue rỗng.

**Bất biến của BFS:** khi một đỉnh v được phát hiện và đưa vào queue lần đầu, khoảng cách được gán cho v là số cạnh của một đường đi ngắn nhất từ nguồn. FIFO bảo đảm các đỉnh ở lớp d được xử lý trước khi những đỉnh ở lớp d+1 được lấy ra.

Giả mã cho đồ thị biểu diễn bằng danh sách kề:

~~~text
distance[*] = -1
distance[source] = 0
queue.addLast(source)

while queue not empty:
    u = queue.removeFirst()
    for each neighbor v of u:
        if distance[v] == -1:
            distance[v] = distance[u] + 1
            queue.addLast(v)
~~~

Lấy distance[v] = −1 làm dấu **chưa thăm**. Phải đánh dấu ngay lúc đưa v vào queue, không chờ tới lúc lấy ra. Nếu đánh dấu trễ, nhiều đỉnh cha có thể đưa cùng v vào queue, dẫn tới xử lý lặp, thậm chí làm hỏng tính đúng của những bất biến liên quan.

Với V đỉnh và E cạnh, danh sách kề cho BFS thời gian **O(V+E)**: mỗi đỉnh được đưa vào queue tối đa một lần, và mỗi cạnh được kiểm tra một số lần hằng số. Bộ nhớ phụ trợ **O(V)** cho queue và mảng distance. Với đồ thị vô hướng, một cạnh có mặt ở danh sách của hai đỉnh nên có thể được xét hai lần, không ảnh hưởng bậc tiệm cận. Đỉnh không tới được giữ distance = −1.

**Cẩn thận với trọng số:** BFS FIFO tìm đường ít cạnh nhất. Nếu mỗi cạnh có trọng số khác nhau, đường ít cạnh nhất không chắc có tổng chi phí nhỏ nhất. Với trọng số không âm tổng quát, dùng thuật toán phù hợp như Dijkstra; với trọng số chỉ 0 và 1, có biến thể deque 0–1 BFS.

### BFS đa nguồn và duyệt lưới

Nếu cần khoảng cách tới **nguồn gần nhất** trong một tập nguồn, hãy đặt distance = 0 và enqueue tất cả nguồn khác nhau trước khi chạy vòng lặp. Đây là **multi-source BFS**; mọi nguồn đều ở lớp 0. Cách này phù hợp cho bài toán lan truyền từ nhiều điểm hoặc khoảng cách tới ô đặc biệt gần nhất.

Trong lưới, trạng thái là ô (row, col), thường xét bốn hoặc tám ô lân cận theo đề bài. Kiểm tra biên, ô cấm và đã thăm **trước khi enqueue**. Với mảng kích thước rows × cols, số trạng thái tối đa rows·cols; BFS có thời gian O(rows·cols) khi mỗi ô có số láng giềng hằng số.

Nếu muốn duyệt từng lớp để in kết quả theo mức, ghi lại kích thước queue ở đầu lớp rồi xử lý đúng số phần tử đó. Các phần tử enqueue trong lúc xử lý sẽ thuộc lớp tiếp theo.

## 4. Deque đơn điệu trong cửa sổ trượt

Cho mảng a gồm n phần tử và k thỏa \(1\le k\le n\). Cần tìm giá trị lớn nhất trong từng đoạn liên tiếp độ dài k. Cách ngây thơ quét lại k phần tử cho mỗi cửa sổ tốn **O(nk)** thời gian. Một **monotonic deque** giữ lại những ứng viên có thể trở thành cực đại, đạt **O(n)** thời gian.

Ta lưu **chỉ số phần tử**, không chỉ giá trị, vì cần biết khi nào một ứng viên đã ra khỏi cửa sổ. Sau khi xử lý vị trí i, deque thỏa ba bất biến:

1. Các chỉ số tăng dần từ đầu tới cuối.
2. Mọi chỉ số còn trong cửa sổ hiện tại; chỉ số cũ nhất được lấy từ đầu.
3. Giá trị a[index] giảm nghiêm ngặt từ đầu tới cuối khi ta loại ứng viên có giá trị nhỏ hơn **hoặc bằng** phần tử mới. Đầu deque chứa chỉ số của cực đại hiện tại.

Khi đến vị trí i:
- **Bỏ đầu:** trong khi chỉ số đầu ≤ i−k, nó đã ra ngoài cửa sổ, nên removeFirst.
- **Bỏ cuối:** trong khi a[chỉ số cuối] ≤ a[i], phần tử ở cuối không còn cần giữ: phần tử mới tốt hơn hoặc bằng và tồn tại lâu hơn trong những cửa sổ tiếp theo.
- **Thêm i vào cuối.**
- Nếu i ≥ k−1, cực đại của cửa sổ hiện tại là a[chỉ số đầu].

Với mảng [1,3,−1,−3,5,3,6,7] và k=3, các cực đại là **[3,3,5,5,6,7]**.

**Vì sao vẫn O(n) dù có hai vòng while?** Mỗi chỉ số được thêm đúng một lần, và mỗi chỉ số bị xóa tối đa một lần, hoặc từ đầu do hết hạn, hoặc từ cuối do bị phần tử mới lấn át. Tổng số thao tác deque qua toàn bộ n bước là O(n): đây là **phân tích khấu hao**, không phải tuyên bố mỗi vòng while chỉ chạy một lần. Deque giữ tối đa k chỉ số nên cần O(k) bộ nhớ phụ trợ; mảng kết quả dài n−k+1, nên tổng bộ nhớ kể cả kết quả là O(n).

**Giá trị bằng nhau:** việc loại phần tử ở cuối khi ≤ sẽ giữ chỉ số mới hơn trong những giá trị bằng nhau. Cũng có thể dùng < và giữ cả những phần tử bằng nhau nếu vẫn loại đúng chỉ số hết hạn; khi đó bất biến “giảm nghiêm ngặt” đổi thành “không tăng”.

## 5. Chương trình Java 17+ hoàn chỉnh

Lưu mã sau dưới tên **QueueDequeTraversalDemo.java**. Một hàm dùng queue FIFO để BFS, một hàm dùng deque đơn điệu cho cực đại cửa sổ. Chương trình cũng minh họa việc lấy từ cả hai đầu.

~~~java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;

public final class QueueDequeTraversalDemo {
    private QueueDequeTraversalDemo() {
    }

    // Danh sách kề: graph[u] chứa các đỉnh kề với u.
    public static int[] bfsDistances(int[][] graph, int source) {
        if (graph == null || source < 0 || source >= graph.length) {
            throw new IllegalArgumentException("Invalid graph or source");
        }

        int[] distance = new int[graph.length];
        Arrays.fill(distance, -1);

        Deque<Integer> queue = new ArrayDeque<>();
        distance[source] = 0; // Đánh dấu ngay khi enqueue.
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : graph[u]) {
                if (v < 0 || v >= graph.length) {
                    throw new IllegalArgumentException("Invalid neighbor");
                }
                if (distance[v] == -1) {
                    distance[v] = distance[u] + 1;
                    queue.addLast(v);
                }
            }
        }
        return distance;
    }

    // Cực đại của mọi cửa sổ liên tiếp có độ dài k.
    public static int[] slidingWindowMaximum(int[] a, int k) {
        if (a == null || k < 1 || k > a.length) {
            throw new IllegalArgumentException("Require 1 <= k <= a.length");
        }

        int[] result = new int[a.length - k + 1];
        Deque<Integer> indices = new ArrayDeque<>();

        for (int i = 0; i < a.length; i++) {
            while (!indices.isEmpty() && indices.peekFirst() <= i - k) {
                indices.removeFirst(); // Chỉ số đã hết hạn.
            }

            while (!indices.isEmpty() && a[indices.peekLast()] <= a[i]) {
                indices.removeLast(); // Ứng viên bị phần tử mới lấn át.
            }

            indices.addLast(i);
            if (i >= k - 1) {
                result[i - k + 1] = a[indices.peekFirst()];
            }
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] graph = {
            {1, 2},
            {0, 3},
            {0, 3},
            {1, 2, 4},
            {3}
        };
        int[] a = {1, 3, -1, -3, 5, 3, 6, 7};

        System.out.println("BFS distance: "
                + Arrays.toString(bfsDistances(graph, 0)));
        System.out.println("Window max (k=3): "
                + Arrays.toString(slidingWindowMaximum(a, 3)));

        Deque<String> deque = new ArrayDeque<>();
        deque.addLast("B");
        deque.addFirst("A");
        deque.addLast("C");
        System.out.println("Pop first/last/first: "
                + deque.removeFirst() + ", "
                + deque.removeLast() + ", "
                + deque.removeFirst());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac QueueDequeTraversalDemo.java
java QueueDequeTraversalDemo
~~~

Kết quả chuẩn:

~~~text
BFS distance: [0, 1, 1, 2, 3]
Window max (k=3): [3, 3, 5, 5, 6, 7]
Pop first/last/first: A, C, B
~~~

Giải thích: Đồ thị có các cạnh 0–1, 0–2, 1–3, 2–3, 3–4. Khoảng cách ngắn nhất tính theo số cạnh từ 0 là [0,1,1,2,3]. Mảng tám phần tử và k=3 có sáu cửa sổ, thu được sáu cực đại như stdout. Deque chứa B, thêm A ở đầu và C ở cuối, nên ba thao tác lấy đầu/cuối/đầu cho A, C, B.

Hợp đồng đầu vào: bfsDistances yêu cầu mọi hàng của danh sách kề khác null và chỉ số láng giềng hợp lệ. Hàm có kiểm tra nguồn, graph null và đỉnh kề nằm ngoài miền; một hàng null trong graph là đầu vào không hợp lệ. slidingWindowMaximum từ chối mảng null, k<1, k>n, kể cả mảng rỗng không có k hợp lệ. Các giá trị trong mảng được phép âm, bằng nhau hoặc dương.

## 6. Biến thể: deque cho 0–1 BFS

**0–1 BFS** áp dụng cho đường đi ngắn nhất khi trọng số mỗi cạnh **chỉ bằng 0 hoặc 1**. Thay vì lấy mọi phần tử mới ở cuối theo FIFO thuần túy:

- Nếu tìm được khoảng cách tốt hơn qua cạnh trọng số 0, cập nhật khoảng cách và đưa trạng thái mới vào **đầu** deque.
- Nếu đi qua cạnh trọng số 1, cập nhật khoảng cách và đưa vào **cuối** deque.
- Chỉ thực hiện cập nhật khi khoảng cách mới nhỏ hơn khoảng cách đã biết; nếu cho phép một đỉnh xuất hiện nhiều lần trong deque, phải xử lý cẩn thận các bản ghi đã lỗi thời hoặc áp dụng biến thể có bất biến tương đương.

Tính chất trọng số 0–1 giữ các mức khoảng cách trong deque ở một trật tự đủ mạnh để đạt thời gian O(V+E) với cách triển khai chuẩn. Không dùng nguyên quy tắc này cho trọng số 2, 5 hoặc số âm; khi đó cơ sở tính đúng không còn.

## 7. Chọn cấu trúc theo bất biến thuật toán

| Tình huống | Cấu trúc | Lý do |
|---|---|---|
| BFS đồ thị/lưới không trọng số | Queue FIFO hoặc ArrayDeque | Xử lý lần lượt theo lớp khoảng cách |
| Multi-source BFS | Queue FIFO | Tất cả nguồn được đưa vào lớp 0 |
| Cực đại/cực tiểu cửa sổ trượt | Monotonic deque giữ chỉ số | Loại phần tử hết hạn và ứng viên kém |
| 0–1 BFS | Deque | Cạnh trọng số 0 ưu tiên đầu; cạnh 1 thêm cuối |
| DFS lặp | Stack hoặc Deque dùng cùng một đầu | LIFO để đi sâu trước |
| Dijkstra trọng số không âm bất kỳ | PriorityQueue | Lấy trạng thái có khoảng cách tạm thời nhỏ nhất |
| Producer–consumer nhiều luồng | Cấu trúc queue đồng thời phù hợp | Yêu cầu bảo đảm đồng bộ, khác ArrayDeque đơn luồng |

## 8. Lỗi phổ biến và kiểm thử

1. **Đánh dấu đã thăm quá muộn trong BFS:** Đánh dấu khi enqueue để tránh đẩy lại một đỉnh đã được phát hiện từ nhiều đỉnh cha.
2. **Dùng FIFO BFS cho shortest path có trọng số bất kỳ:** FIFO tối ưu theo số cạnh chứ không theo trọng số. Chọn Dijkstra hoặc biến thể đúng với lớp trọng số.
3. **Giữ giá trị thay vì chỉ số trong sliding window:** Không thể phân biệt phần tử đã hết hạn. Lưu chỉ số và bỏ từ đầu khi ≤ i−k.
4. **Quên loại ứng viên bị lấn át ở cuối:** Đầu deque có thể không còn là cực đại theo bất biến mong muốn; phải duy trì thứ tự giá trị.
5. **Hiểu sai O(n) của deque đơn điệu:** Một vòng có thể xóa nhiều phần tử; tổng O(n) vì mỗi chỉ số được thêm/xóa tối đa một lần.
6. **Nhầm O(1) với bộ nhớ phụ trợ:** BFS có thể chứa O(V) đỉnh trong queue; sliding window chứa O(k) chỉ số.
7. **Lấy khỏi deque rỗng:** removeFirst/removeLast ném ngoại lệ; kiểm tra isEmpty hoặc dùng poll với cách xử lý null rõ ràng.
8. **Không kiểm tra biên khi duyệt lưới:** Phải kiểm tra ô nằm trong miền hợp lệ và có được đi qua hay không trước khi enqueue.
9. **Dùng ArrayDeque từ nhiều luồng mà không đồng bộ:** Đổi sang cấu trúc đồng thời hoặc bảo vệ truy cập theo hợp đồng.
10. **Lẫn lộn deque với priority queue:** Deque không tự chọn phần tử có trọng số tối ưu. Sự đúng đắn đến từ cách thêm/xóa và bất biến đã chứng minh.

Bài kiểm thử cho BFS: một đỉnh, chu trình, đỉnh không tới được, nhiều cạnh hướng tới cùng đỉnh, đồ thị đường thẳng, đầu vào nguồn không hợp lệ. Bài kiểm thử cho sliding window: k=1, k=n, mảng tăng dần, giảm dần, toàn phần tử bằng nhau, có số âm, xen kẽ cực trị và k ngoài miền.

**Tự kiểm tra:** Vì sao deque của thuật toán cửa sổ trượt không cần lưu mọi chỉ số trong cửa sổ? **Đáp án:** Khi phần tử mới có giá trị lớn hơn hoặc bằng phần tử cũ, và lại hết hạn muộn hơn, phần tử cũ không thể thắng để trở thành cực đại ở bất kỳ cửa sổ tiếp theo nào còn chứa phần tử mới; có thể bỏ nó khỏi đuôi.

**Ghi nhớ:** Queue FIFO hỗ trợ duyệt theo **thứ tự phát hiện** (điển hình BFS); deque hỗ trợ thuật toán cần quản lý **cả hai đầu** (điển hình cửa sổ trượt đơn điệu và 0–1 BFS). Hãy lựa chọn cấu trúc dựa trên thứ tự xử lý cần bảo đảm, không chỉ dựa vào tên cấu trúc dữ liệu.
