# Lựa chọn cấu trúc theo thao tác thuật toán cần thực hiện

## 1. Tư duy cốt lõi: chọn theo thao tác, không chọn theo tên cấu trúc

Cùng một tập dữ liệu, hai thuật toán có thể cần cấu trúc hỗ trợ hoàn toàn khác nhau. Nếu phải tìm phần tử có tồn tại hay không nhiều lần, bảng băm là ứng viên tốt. Nếu phải liên tục lấy phần tử nhỏ nhất, hàng đợi ưu tiên phù hợp hơn. Nếu cần lấy các phần tử theo đúng thứ tự đến trước, hàng đợi hai đầu có thể đáp ứng với chi phí thấp. Bài toán lựa chọn vì thế bắt đầu từ **những thao tác phải thực hiện**, tần suất của chúng và các ràng buộc, rồi mới quyết định cấu trúc dữ liệu.

Cấu trúc hỗ trợ là cách tổ chức trạng thái trung gian cho thuật toán: lưu những phần tử chưa xử lý, nhớ kết quả đã tính, đánh dấu đã thăm, quản lý thứ tự ưu tiên, lưu quan hệ kề, hoặc trả lời truy vấn nhanh. Nó khác với cấu trúc của dữ liệu đầu vào: một thuật toán có thể đọc dữ liệu từ mảng nhưng dùng thêm HashMap, ArrayDeque hay PriorityQueue trong quá trình xử lý.

Trước khi chọn, hãy xác định:

1. **Các phép toán chính:** truy cập theo chỉ số, kiểm tra thuộc tập, đếm tần suất, thêm/xóa, lấy min/max, tìm phần tử kế tiếp theo thứ tự, nối tập, truy vấn đoạn, duyệt láng giềng...
2. **Tần suất:** thực hiện một lần hay hàng triệu lần; số phép đọc so với phép cập nhật là bao nhiêu?
3. **Kích thước và phân bố:** n phần tử, số phần tử phân biệt u, số đỉnh V và cạnh E, miền khóa nhỏ hay lớn, dữ liệu thưa hay dày?
4. **Ngữ nghĩa kết quả:** có cần giữ thứ tự chèn, thứ tự tăng dần, cho phép giá trị trùng, hay cần thao tác FIFO/LIFO?
5. **Giới hạn:** thời gian, bộ nhớ, khả năng cập nhật, chi phí khởi tạo và các bảo đảm xấu nhất.
6. **Tính hợp lệ và bất biến:** dữ liệu có sắp xếp không, chỉ số có nằm trong miền không, cấu trúc có duy trì đúng trạng thái sau mỗi phép toán không?

**Mục tiêu là tối ưu tổng chi phí của cả quy trình**, bao gồm dựng cấu trúc, xử lý mọi thao tác, cập nhật, bộ nhớ và chi phí bảo trì; không chỉ tối ưu một phép tra cứu riêng lẻ.

## 2. Bảng đối chiếu thao tác với cấu trúc thường dùng

Bảng sau trình bày độ phức tạp phổ biến cho mỗi thao tác với n phần tử, trừ khi ghi tham số khác. Các chi phí kỳ vọng/trung bình không phải là bảo đảm xấu nhất.

| Thao tác chủ đạo | Cấu trúc nên xem xét | Chi phí điển hình | Đánh đổi hoặc điều kiện |
| --- | --- | --- | --- |
| Truy cập phần tử thứ i thường xuyên | Mảng, ArrayList | Truy cập O(1) | Thêm/xóa giữa dãy O(n), mảng cố định kích thước |
| Thêm vào cuối và duyệt tuần tự | ArrayList, mảng động | Thêm cuối O(1) trung bình khấu hao; duyệt O(n) | Đôi khi phải cấp phát lại và sao chép |
| Thêm/xóa hai đầu theo FIFO, LIFO | ArrayDeque | Thêm/lấy ở hai đầu O(1) khấu hao | Không hỗ trợ truy cập ngẫu nhiên theo chỉ số |
| Tồn tại khóa, ánh xạ khóa → giá trị, đếm | HashSet, HashMap | Tra/thêm/xóa kỳ vọng O(1) | Phụ thuộc hàm băm; không có thứ tự sắp xếp |
| Cần khóa có thứ tự, tìm khóa nhỏ hơn/lớn hơn gần nhất | TreeSet, TreeMap | Thao tác tra/thêm/xóa O(log n) | Chậm hơn bảng băm cho tra cứu đơn thuần |
| Liên tục lấy phần tử nhỏ nhất/lớn nhất | PriorityQueue (heap) | Peek O(1), offer/poll O(log n) | Không hỗ trợ tra cứu hay xóa tùy ý nhanh; iterator không có thứ tự |
| Dữ liệu tĩnh đã sắp xếp; tìm nhiều lần | Mảng đã sắp xếp + tìm kiếm nhị phân | Tìm O(log n) | Sắp xếp ban đầu O(n log n); chèn vào mảng O(n) |
| Tổng của nhiều đoạn, dữ liệu ít thay đổi | Mảng tổng tiền tố (prefix sums) | Dựng O(n), truy vấn tổng đoạn O(1) | Cập nhật một phần tử làm hỏng nhiều tổng đã lưu |
| Tổng tiền tố/đoạn và cập nhật điểm xen kẽ | Fenwick tree (BIT) | Cập nhật O(log n), truy vấn O(log n) | Thích hợp phép tổng/cấu trúc đại số hỗ trợ phù hợp |
| Truy vấn min/max/tổng trên đoạn và cập nhật | Segment tree | Dựng O(n), truy vấn/cập nhật điểm O(log n) | Tốn bộ nhớ và mã phức tạp hơn; cập nhật cả đoạn cần lazy propagation |
| Kiểm tra hai đỉnh cùng thành phần khi nối cạnh | Disjoint Set Union (DSU) | Gần O(1) khấu hao, chính xác là O(α(n)) | Không phù hợp xóa cạnh hoặc tìm đường đi |
| Duyệt láng giềng đồ thị thưa | Danh sách kề | Lưu O(V + E), duyệt toàn bộ O(V + E) | Kiểm tra một cạnh bất kỳ có thể tốn O(bậc đỉnh) |
| Kiểm tra cạnh (u,v) liên tục trên đồ thị vừa và dày | Ma trận kề | Tra cạnh O(1), lưu O(V²) | Tốn bộ nhớ với đồ thị nhiều đỉnh |
| Truy vấn chuỗi theo tiền tố | Trie | Đi theo tiền tố độ dài L trong O(L) | Chi phí bộ nhớ con trỏ/nút có thể lớn |
| Tập chỉ số nguyên không âm trong miền vừa phải | BitSet | Kiểm tra/đánh dấu bit hiệu quả | Dung lượng phụ thuộc chỉ số lớn nhất, không chỉ số phần tử có mặt |

Ký hiệu α(n) là hàm Ackermann nghịch đảo, tăng rất chậm. Với HashMap/HashSet, O(1) là chi phí **kỳ vọng** khi phân bố băm phù hợp; không nên khẳng định mọi trường hợp đều có chi phí cố định. Với các cấu trúc có kèm dữ liệu ngoài nút/cấu trúc quản lý, độ phức tạp bộ nhớ tổng thể còn phụ thuộc cách lưu giá trị.

## 3. Trường hợp 1: cần truy cập theo vị trí hay duy trì thứ tự xử lý?

### Mảng và ArrayList: khi chỉ số quan trọng

Nếu vòng lặp phải đọc a[i] rất nhiều lần, mảng và ArrayList cho phép truy cập O(1). Dữ liệu thường được đặt gần nhau trong bộ nhớ, thuận tiện cho duyệt tuần tự; với các kiểu nguyên thủy, mảng int[] còn tránh chi phí boxing của Integer. Khi cần mở rộng dần, ArrayList thích hợp vì thêm cuối thường O(1) khấu hao.

Một danh sách liên kết không tự động nhanh hơn ArrayList. Dù có thể thêm/xóa tại nút **đã biết** với O(1), việc tìm đến nút ở vị trí i vẫn O(n), và các đối tượng/nút rời rạc thường tốn bộ nhớ, giảm tính cục bộ bộ nhớ đệm. Đừng chọn LinkedList chỉ vì nghe tới thao tác chèn.

### ArrayDeque: khi thứ tự lấy ra quyết định thuật toán

- **FIFO (first in, first out):** BFS, hàng đợi xử lý tác vụ; thêm cuối bằng addLast, lấy đầu bằng removeFirst.
- **LIFO (last in, first out):** DFS dùng ngăn xếp, duyệt biểu thức; thêm/lấy cùng một đầu bằng push/pop.
- **Hai đầu:** duy trì cửa sổ trượt đơn điệu, hoặc thuật toán 0-1 BFS có thể thêm cạnh trọng số 0 ở đầu và trọng số 1 ở cuối.

Trong Java, ArrayDeque thường là lựa chọn tốt cho stack/queue một luồng. Nó không cho phần tử null; không cần dùng lớp Stack cũ hoặc LinkedList nếu chỉ cần thao tác đầu/cuối. Queue dành cho độ ưu tiên khác FIFO: PriorityQueue lấy theo **thứ tự so sánh**, không theo thời gian đến.

**Bất biến cần giữ:** BFS xử lý các đỉnh theo khoảng cách số cạnh không giảm từ nguồn trong đồ thị không trọng số; dùng FIFO bảo toàn thứ tự mức. Thay hàng đợi FIFO bằng stack sẽ biến cách duyệt thành DFS và không còn bảo đảm phát hiện đường ngắn nhất theo số cạnh.

## 4. Trường hợp 2: hỏi “đã gặp chưa?”, đếm hay cần thứ tự khóa?

### HashSet và HashMap: tra cứu khóa lặp lại

HashSet hữu ích để đánh dấu visited, phát hiện phần tử trùng hoặc kiểm tra điều kiện tồn tại. HashMap hữu ích cho bảng tần suất, ánh xạ id → vị trí, ghi nhớ trạng thái đã tính trong memoization, hoặc lưu khoảng cách theo đỉnh.

Ví dụ, nếu dữ liệu có n phần tử và cần m lần kiểm tra xem khóa tồn tại:

- Quét tuyến tính một List tốn O(n) mỗi truy vấn, tổng O(mn).
- Dựng HashSet dự kiến O(n), sau đó m phép contains dự kiến O(m), tổng O(n + m), đổi lại bộ nhớ O(u) với u là số giá trị phân biệt.
- Nếu m rất nhỏ hoặc n rất nhỏ, chi phí cấp phát/băm có thể không đáng so với quét mảng đơn giản.

Không được suy từ HashMap rằng kết quả duyệt sẽ có thứ tự cố định. Nếu thuật toán phải xuất khóa tăng dần, có thể sắp xếp kết quả sau cùng hoặc dùng TreeMap/TreeSet; cần tính cả chi phí sắp xếp/duy trì thứ tự. LinkedHashMap hỗ trợ thứ tự lặp theo thứ tự chèn (hoặc thứ tự truy cập khi cấu hình tương ứng), nhưng không tự sắp xếp theo giá trị khóa.

### TreeMap và TreeSet: khi cần hàng xóm trong thứ tự

Một cây tìm kiếm cân bằng có thể hỗ trợ ceiling, floor, higher, lower, min/max khóa và truy vấn phạm vi với chi phí logarit cho tìm điểm khởi đầu. Nếu bài toán hỏi “thời điểm gần nhất không vượt quá t” sau mỗi lần chèn, TreeMap thường phù hợp hơn HashMap. Nếu chỉ cần đếm theo khóa chính xác, HashMap thường gọn hơn về phép toán.

Lưu ý với TreeMap/TreeSet: comparator quyết định tính tương đương của khóa trong cấu trúc có thứ tự; comparator không phù hợp có thể khiến hai đối tượng bị coi là một khóa, dù logic nghiệp vụ muốn phân biệt.

## 5. Trường hợp 3: luôn lấy phần tử ưu tiên nhất

PriorityQueue của Java mặc định là **min-heap**: peek xem phần tử nhỏ nhất O(1), offer chèn O(log n), poll lấy và xóa nhỏ nhất O(log n). Có thể dùng comparator đảo để tạo max-heap.

Đó là công cụ phổ biến trong:

- **Dijkstra:** lấy ứng viên có khoảng cách tạm thời nhỏ nhất; thường dùng PriorityQueue chứa cặp (distance, vertex). Java PriorityQueue không hỗ trợ decrease-key trực tiếp; cách đơn giản là thêm bản ghi khoảng cách mới và **bỏ qua bản ghi cũ** khi lấy ra, sau khi so với dist hiện tại.
- **Trộn k dãy đã sắp xếp:** lưu phần tử đầu của mỗi dãy trong heap kích thước k, mỗi lần xuất phần tử nhỏ nhất rồi đưa phần tử tiếp theo của dãy đó vào.
- **Top-k nhỏ nhất/lớn nhất:** chỉ giữ heap kích thước k thay vì sắp xếp toàn bộ n giá trị. Để giữ k giá trị nhỏ nhất, dùng **max-heap kích thước k**; phần tử lớn nhất trong k giá trị đang chọn là ứng viên bị loại khi gặp giá trị nhỏ hơn.

Không nhầm thao tác poll với duyệt iterator: iterator của PriorityQueue **không bảo đảm xuất ra thứ tự ưu tiên**. Xóa một phần tử tùy ý theo giá trị hoặc tìm một phần tử không nằm ở đỉnh thường là O(n); heap không thích hợp cho mọi kiểu truy vấn khóa.

## 6. Trường hợp 4: nhiều truy vấn trên đoạn dữ liệu

Bài toán nhận mảng ban đầu, rồi trả lời nhiều truy vấn đoạn [l, r] có thể chọn cấu trúc dựa vào **loại phép gộp** và **tần suất cập nhật**.

| Yêu cầu | Giải pháp | Phần chuẩn bị | Truy vấn | Cập nhật điểm |
| --- | --- | --- | --- | --- |
| Tổng đoạn, mảng không đổi | Prefix sum | O(n) | O(1) | O(n) nếu duy trì trực tiếp |
| Tổng đoạn và nhiều cập nhật điểm | Fenwick tree | O(n) hoặc O(n log n), tùy cách dựng | O(log n) | O(log n) |
| Min/max/tổng đoạn, cập nhật điểm | Segment tree | O(n) | O(log n) | O(log n) |
| Min/max cửa sổ trượt độ rộng k | Monotonic deque | Không cần tiền xử lý toàn mảng | O(n) cho toàn bộ n cửa sổ | Không áp dụng kiểu cập nhật truy vấn tổng quát |

Với tổng tiền tố, định nghĩa prefix[0] = 0 và prefix[i+1] = prefix[i] + a[i], khi đó sum(l,r) = prefix[r+1] - prefix[l] cho 0 ≤ l ≤ r < n. Mảng long[] nên được cân nhắc khi tổng có thể vượt giới hạn int, nhưng long cũng có giới hạn; bài toán phải nói rõ miền đầu vào.

Fenwick tree có ưu điểm triển khai gọn cho tổng: cập nhật một giá trị và lấy tổng tiền tố trong O(log n). Segment tree rộng hơn khi cần min/max, kết hợp nhiều thống kê hoặc cập nhật đoạn phức tạp. Nếu chỉ truy vấn một lần, dựng cấu trúc mất công có thể thừa; quét O(n) đôi khi tối ưu hơn trong thực tế.

**Quan trọng:** một phép gộp phải phù hợp với cấu trúc. Không thể tự động lấy chênh lệch của hai “giá trị nhỏ nhất tiền tố” để suy ra min trên đoạn như cách làm với tổng.

## 7. Trường hợp 5: thuật toán đồ thị

Lựa chọn cấu trúc lưu cạnh tác động trực tiếp đến độ phức tạp. Với đồ thị V đỉnh, E cạnh:

- **Danh sách kề:** mỗi đỉnh lưu danh sách láng giềng; O(V + E) bộ nhớ, BFS/DFS O(V + E). Phù hợp đồ thị thưa và bài toán cần duyệt cạnh. Với đồ thị vô hướng, mỗi cạnh thường xuất hiện hai lần trong danh sách; độ lớn vẫn O(V + E).
- **Ma trận kề:** m[u][v] cho biết có cạnh hay không; kiểm tra cạnh O(1), bộ nhớ O(V²). Với mỗi đỉnh, phải quét O(V) vị trí để tìm láng giềng, nên BFS/DFS kiểu ma trận thường O(V²).
- **Danh sách cạnh:** hữu ích khi cần duyệt tất cả cạnh, như Kruskal sau khi sắp theo trọng số; không hỗ trợ truy vấn láng giềng của một đỉnh nhanh nếu không lập chỉ mục bổ sung.

Thao tác trung tâm còn quyết định **cấu trúc trung gian**:

| Thuật toán / truy vấn | Cấu trúc hỗ trợ quan trọng | Lý do |
| --- | --- | --- |
| BFS đồ thị không trọng số | ArrayDeque FIFO + mảng visited/distance | Xử lý theo từng mức số cạnh |
| DFS lặp | ArrayDeque LIFO + visited | Khám phá sâu trước, tránh tràn ngăn xếp đệ quy với đồ thị rất sâu |
| Dijkstra với trọng số cạnh không âm | PriorityQueue + dist[]/Map | Luôn xử lý ứng viên có khoảng cách tạm nhỏ nhất |
| Kruskal | Sắp xếp cạnh + DSU | Duyệt cạnh theo trọng số, kiểm tra hai đầu thuộc cùng thành phần |
| Kiểm tra kết nối khi chỉ thêm cạnh | DSU | Union/Find rất nhanh, nhưng không cho biết đường đi |
| Đếm bậc đỉnh | Mảng int[] hoặc Map | Chọn mảng nếu id đỉnh liên tiếp, Map nếu khóa thưa |

Dijkstra không áp dụng trực tiếp khi tồn tại cạnh trọng số âm; thay PriorityQueue bằng một cấu trúc khác không tự sửa được yêu cầu thuật toán. Với số đỉnh lớn và id liên tiếp từ 0 đến V-1, int[]/boolean[] cho dist/visited thường nhẹ hơn HashMap<Integer,...>. Với id rời rạc như chuỗi hoặc UUID, Map/Set phù hợp hơn hoặc cần bước nén chỉ số.

## 8. Ví dụ Java 17+: ba mục tiêu, ba cấu trúc hỗ trợ

Ví dụ độc lập dưới đây minh họa: **đếm bằng HashMap**, **lấy k giá trị nhỏ nhất bằng max-heap giới hạn k**, và **đường đi ngắn nhất theo số cạnh bằng BFS + ArrayDeque**. Chúng giải quyết ba bộ thao tác khác nhau trên dữ liệu đơn giản.

Lưu thành **StructureChoiceDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

public class StructureChoiceDemo {
    // Nhieu truy van tan suat: Map cho tra cuu theo khoa.
    static Map<String, Integer> frequencies(List<String> items) {
        if (items == null) {
            throw new IllegalArgumentException("items must not be null");
        }
        Map<String, Integer> count = new HashMap<>();
        for (String item : items) {
            if (item == null) {
                throw new IllegalArgumentException("item must not be null");
            }
            count.merge(item, 1, Integer::sum);
        }
        return count;
    }

    // Chi can k gia tri nho nhat: giu max-heap kich thuoc k.
    static List<Integer> smallestK(int[] values, int k) {
        if (values == null) {
            throw new IllegalArgumentException("values must not be null");
        }
        if (k < 0 || k > values.length) {
            throw new IllegalArgumentException("k out of range");
        }
        if (k == 0) {
            return List.of();
        }

        PriorityQueue<Integer> heap =
                new PriorityQueue<>(Comparator.reverseOrder());
        for (int value : values) {
            if (heap.size() < k) {
                heap.offer(value);
            } else if (value < heap.peek()) {
                heap.poll();
                heap.offer(value);
            }
        }

        List<Integer> answer = new ArrayList<>(heap);
        Collections.sort(answer);
        return answer;
    }

    // BFS tren do thi khong trong so, dinh duoc danh so 0..V-1.
    static int shortestHops(List<List<Integer>> graph, int source, int target) {
        if (graph == null) {
            throw new IllegalArgumentException("graph must not be null");
        }
        int n = graph.size();
        if (source < 0 || source >= n || target < 0 || target >= n) {
            throw new IllegalArgumentException("vertex out of range");
        }
        for (List<Integer> neighbors : graph) {
            if (neighbors == null) {
                throw new IllegalArgumentException("neighbors must not be null");
            }
            for (int next : neighbors) {
                if (next < 0 || next >= n) {
                    throw new IllegalArgumentException("edge endpoint out of range");
                }
            }
        }

        int[] distance = new int[n];
        Arrays.fill(distance, -1);
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        distance[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            if (u == target) {
                return distance[u];
            }
            for (int v : graph.get(u)) {
                if (distance[v] == -1) {
                    distance[v] = distance[u] + 1;
                    queue.addLast(v);
                }
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        Map<String, Integer> counts =
                frequencies(List.of("login", "view", "login", "buy", "login"));
        System.out.println("login count = " + counts.getOrDefault("login", 0));
        System.out.println("buy count = " + counts.getOrDefault("buy", 0));

        System.out.println(
                "smallest 3 = " + smallestK(new int[]{8, 3, 6, 3, 1}, 3)
        );

        List<List<Integer>> graph = List.of(
                List.of(1, 2),
                List.of(0, 3),
                List.of(0, 3),
                List.of(1, 2, 4),
                List.of(3)
        );
        System.out.println("hops 0 to 4 = " + shortestHops(graph, 0, 4));
    }
}
~~~

Biên dịch/chạy trong thư mục có tệp:

~~~bash
javac StructureChoiceDemo.java
java StructureChoiceDemo
~~~

Đầu ra chính xác:

~~~text
login count = 3
buy count = 1
smallest 3 = [1, 3, 3]
hops 0 to 4 = 3
~~~

**Phân tích:**

- frequencies duyệt n chuỗi, HashMap trung bình kỳ vọng O(n) thời gian và O(u) bộ nhớ cho u khóa khác nhau. Lệnh in dùng getOrDefault nên không phụ thuộc thứ tự duyệt của HashMap.
- smallestK giữ tối đa k giá trị. Heap có phần tử lớn nhất nằm trên đỉnh, vì vậy khi gặp số nhỏ hơn đỉnh, ta loại số lớn nhất trong nhóm được giữ. Sau n bước, nhóm chứa k giá trị nhỏ nhất (kể cả giá trị trùng); bước sắp xếp khiến danh sách kết quả tăng dần. Độ phức tạp O(n log k + k log k) khi k ≥ 1, không tính hằng số cho k=1; bộ nhớ O(k). Với k=0, hàm trả danh sách rỗng.
- shortestHops sử dụng danh sách kề, kiểm tra đầu vào rồi BFS. Mỗi đỉnh được đưa vào queue tối đa một lần nhờ distance[v] được gán trước khi thêm. Lần đầu gặp đỉnh ở mức d là đường đi có d cạnh nhỏ nhất từ nguồn, nên khi lấy target ra ta trả đúng số cạnh ít nhất. Tổng thời gian O(V + E), bộ nhớ phụ O(V) (không kể graph). Nếu target không tới được, trả -1.
- Tiền điều kiện graph gồm các danh sách láng giềng chứa chỉ số đỉnh hợp lệ. Với đồ thị vô hướng như ví dụ, mỗi quan hệ được ghi ở cả hai đầu. Với đồ thị có hướng, vẫn dùng BFS nhưng chỉ theo cạnh có hướng đã lưu. Không dùng BFS để suy ra tổng trọng số nhỏ nhất khi các cạnh có trọng số khác nhau.

Ví dụ trên trả về kết quả, chứ không xây dựng API sản xuất đầy đủ: đầu vào có số lượng cực lớn có thể cần xử lý tràn bộ đếm int; cấu trúc dữ liệu có tính chất đồng thời cũng cần thiết nếu nhiều luồng cập nhật chung.

## 9. Cách chọn theo khối lượng truy vấn và cập nhật

Không có cấu trúc tối ưu cho mọi thao tác. Xét ba tình huống:

**Tình huống A – danh sách người dùng cố định và tra cứu hàng triệu lần:** một HashSet/HashMap dựng một lần rồi tra cứu nhiều lần có thể đáng giá. Nếu cần thứ tự chữ cái và hiếm khi đổi dữ liệu, sắp xếp mảng và tìm nhị phân cũng là lựa chọn hợp lý; nếu vừa cần tìm theo khóa vừa cần in theo thứ tự, có thể dùng TreeMap hoặc duy trì hai biểu diễn có kiểm soát.

**Tình huống B – liên tục thêm sự kiện và hỏi “sự kiện sớm nhất chưa xử lý?”:** ArrayDeque theo FIFO đáp ứng trực tiếp, không cần heap. Nếu hỏi “sự kiện có độ ưu tiên cao nhất?”, PriorityQueue mới phù hợp, nhưng phải định nghĩa quy tắc xử lý khi nhiều sự kiện có cùng mức ưu tiên; heap không tự đảm bảo thứ tự FIFO trong trường hợp hòa.

**Tình huống C – n số, chỉ hỏi tổng của q đoạn:** quét mỗi đoạn O(n) một lần. Với q lớn và mảng bất biến, prefix sums tổng O(n + q). Với thay đổi xen kẽ, Fenwick hoặc segment tree có thể giảm chi phí từ cập nhật tuyến tính xuống logarit. Nếu chỉ có một truy vấn, việc tạo cây có thể không đem lại lợi ích.

Có thể hình dung điểm hòa vốn qua công thức tổng: **T = T_khởi_tạo + số_truy_vấn × T_truy_vấn + số_cập_nhật × T_cập_nhật**. Đây chỉ là mô hình tiệm cận; hiệu năng thực tế còn phụ thuộc bộ nhớ, kích thước dữ liệu, phân bố khóa, bộ nhớ đệm CPU và chi phí Java boxing/GC.

## 10. Quy trình ra quyết định thực tế

1. **Viết thao tác bằng động từ chính xác.** “Tìm” nghĩa là tìm khóa bằng nhau, tìm phần tử gần nhất, tìm min, hay tìm đường ngắn nhất? Mỗi loại có cấu trúc phù hợp khác nhau.
2. **Xếp hạng thao tác theo số lần.** Nếu số lần contains lớn hơn nhiều so với insert, ưu tiên cấu trúc tối ưu lookup. Nếu có nhiều cập nhật, đánh giá cả chi phí cập nhật.
3. **Định nghĩa ràng buộc kết quả.** Thứ tự, phần tử trùng, tính ổn định khi hòa, thứ tự duyệt, hoặc yêu cầu truy hồi đường đi có thể quyết định lựa chọn.
4. **Đặt giới hạn n, m, V, E, k.** So sánh cấu trúc dữ liệu theo cỡ thực, không chỉ Big-O. Với V=100 nhưng đồ thị dày, ma trận kề có thể hợp lý; với V=1.000.000 và E≈V, ma trận O(V²) bất khả thi.
5. **Tính toàn bộ pipeline.** Có thể cần dựng map, duy trì queue và lấy kết quả ra mảng; đừng chỉ tính một phép lặp trung tâm.
6. **Xác định bất biến dữ liệu.** Ví dụ heap luôn chứa k giá trị nhỏ nhất đã thấy; BFS đánh dấu ngay khi đưa vào queue; DSU đại diện cho các thành phần sau mọi phép union.
7. **Chọn giao diện thao tác nhỏ nhất cần thiết.** Nếu thuật toán chỉ cần offer/poll, hãy sử dụng PriorityQueue trực tiếp thay vì xây một cấu trúc tổng quát phức tạp.
8. **Kiểm thử trường hợp biên, sau đó đo nếu cần.** Các biên gồm tập rỗng, k=0, nhiều khóa trùng, id thưa, đồ thị không liên thông, nhiều phần tử cùng ưu tiên. Đối với hiệu năng Java, dùng benchmark thích hợp như JMH khi quyết định phụ thuộc vào hằng số thời gian.

### Sơ đồ gợi ý nhanh

- Cần truy cập theo vị trí hoặc quét liên tục → array/ArrayList.
- Cần FIFO/LIFO → ArrayDeque.
- Cần kiểm tra membership hoặc đếm theo khóa → HashSet/HashMap.
- Cần tìm khóa kế trước/kế sau hay duy trì thứ tự sắp xếp → TreeSet/TreeMap.
- Cần liên tục lấy min/max → PriorityQueue.
- Cần tổng đoạn trên mảng bất biến → prefix sums; cập nhật điểm xen kẽ → Fenwick/segment tree.
- Cần nối các thành phần và hỏi cùng tập → DSU.
- Cần duyệt cạnh trong đồ thị thưa → danh sách kề; rất nhiều phép hỏi có cạnh trực tiếp trong đồ thị dày vừa phải → cân nhắc ma trận kề.

Đây là các điểm khởi đầu có điều kiện, không phải quy tắc bất biến. Chẳng hạn, bài toán tìm **k phần tử lớn nhất** một lần có thể dùng sắp xếp, heap kích thước k hoặc thuật toán chọn theo thứ tự; lựa chọn phụ thuộc k, nhu cầu xuất kết quả đã sắp xếp và yêu cầu xấu nhất.

## 11. Các sai lầm phổ biến

- **Chọn theo “O(1) nhanh hơn O(log n)” mà quên loại truy vấn.** HashMap không hỗ trợ nhanh truy vấn khóa gần nhất, còn TreeMap có.
- **Tạo nhiều chỉ mục không cần thiết.** Tốn bộ nhớ, tăng chi phí cập nhật và dễ khiến các chỉ mục lệch nhau.
- **Dùng PriorityQueue như một danh sách đã sắp.** iterator không trả phần tử theo thứ tự; muốn theo thứ tự phải poll lần lượt hoặc sao chép rồi sắp.
- **Nhầm danh sách kề với kiểm tra cạnh O(1).** Danh sách kề thường duyệt O(deg(u)) để tìm cạnh (u,v); muốn tra nhanh có thể dùng set láng giềng, đổi lại bộ nhớ.
- **Không đánh giá số lần cập nhật.** Prefix sums xuất sắc cho truy vấn tổng trên mảng tĩnh nhưng không tối ưu khi thay đổi thường xuyên.
- **Quên tính chất dữ liệu.** HashMap cần khóa có equals/hashCode nhất quán; TreeMap cần comparator phù hợp; BFS không thay thế Dijkstra với trọng số không đều.
- **Quên giá trị trùng và thứ tự ổn định.** Set bỏ trùng; PriorityQueue không tự ổn định khi hòa; thuật toán có thể cần kèm chỉ số gốc/sequence number.
- **Đồng nhất độ phức tạp với tốc độ thực tế.** ArrayList thường có lợi thế locality; cấu trúc nút nhiều đối tượng gây áp lực lên bộ cấp phát và garbage collector.
- **Xem DSU như công cụ tìm đường.** DSU trả lời hai đỉnh có cùng thành phần hay không, không cho đường đi cụ thể và không hỗ trợ xóa cạnh đơn giản.
- **Đếm Big-O từng phép mà quên tổng pipeline.** Heap kích thước k có thể tốt hơn sắp n phần tử khi k nhỏ, nhưng nếu cuối cùng vẫn phải xuất toàn bộ dữ liệu theo thứ tự thì cần xem lại.

## 12. Bài tập ứng dụng và tự kiểm tra

1. Có n=100.000 mã sản phẩm và m=1.000.000 truy vấn “mã này có tồn tại không?”. Hãy so sánh quét List, HashSet và mảng đã sắp + binary search theo thời gian dựng, truy vấn và bộ nhớ. Nếu mỗi truy vấn còn cần “mã hợp lệ gần nhất nhỏ hơn”, lựa chọn thay đổi thế nào?
2. Một hệ thống nhận 10.000 tác vụ, mỗi tác vụ có mức ưu tiên và thời điểm đến. Muốn luôn lấy ưu tiên cao nhất; khi hòa thì lấy tác vụ đến sớm nhất. Hãy chọn heap với comparator ghép (ưu tiên giảm dần, thứ tự đến tăng dần), giải thích vì sao FIFO thuần không đủ.
3. Mảng có n số và lần lượt 100.000 thao tác thuộc hai loại: cộng delta tại vị trí i hoặc hỏi tổng đoạn [l,r]. Nêu bất biến và chi phí của Fenwick tree so với prefix sums.
4. Đồ thị có V=200.000, E=400.000, cần tìm số cạnh ít nhất từ nguồn tới từng đỉnh. Chọn biểu diễn cạnh và cấu trúc hàng đợi, chứng minh O(V+E). Nếu thay câu hỏi bằng “cùng thành phần kết nối?” sau mỗi lần thêm cạnh, chọn gì?
5. Có k=20 trong n=1.000.000 số, chỉ cần 20 số nhỏ nhất theo thứ tự tăng dần. So sánh sắp xếp toàn bộ với max-heap kích thước k, tính cả chi phí sắp 20 phần tử ở bước cuối.

**Tự kiểm tra kết luận:** Hãy thử thay đổi đúng **một** yêu cầu (ví dụ “có cần thứ tự không?”, “có cập nhật không?”, “đồ thị có trọng số không?”) và xem vì sao cấu trúc nên đổi. Kỹ năng quan trọng là thiết kế phép toán và bất biến trước, rồi đánh giá cấu trúc nào giúp thực hiện các phép toán ấy đúng, đơn giản và hiệu quả nhất.
