# Tách mô hình toán học khỏi cách lưu trữ trên máy

Trong thiết kế thuật toán, ta cần phân biệt **đối tượng toán học mà bài toán nói đến** với **cách máy tính biểu diễn đối tượng ấy**. Đồ thị, tập hợp, dãy, quan hệ, số nguyên, khoảng hay hàm là những khái niệm trừu tượng; mảng, danh sách liên kết, bảng băm, ma trận, bitset, đối tượng Java và tệp là phương tiện lưu trữ cụ thể.

Một mô hình đúng giúp xác định **cái gì là nghiệm hợp lệ** và **kết quả cần có**. Một biểu diễn phù hợp giúp hiện thực thuật toán **đúng, nhanh và tiết kiệm tài nguyên**. Có thể thay đổi biểu diễn để cải thiện hiệu năng, miễn là vẫn giữ nguyên ý nghĩa của bài toán.

## 1. Ba lớp cần tách bạch

| Lớp | Câu hỏi phải trả lời | Ví dụ về bài toán đường đi |
| --- | --- | --- |
| **Đặc tả bài toán** | Đầu vào là gì? Đầu ra là gì? Khi nào đáp án đúng? | Cho đồ thị có hướng không trọng số G, hai đỉnh s và t; trả độ dài đường đi ngắn nhất tính bằng số cạnh, hoặc “không tới được”. |
| **Mô hình toán học** | Đối tượng, ràng buộc và quan hệ nào mô tả thế giới cần giải? | G = (V, E), trong đó V là tập đỉnh và E là tập cặp có thứ tự (u, v); đường đi là dãy đỉnh liên tiếp thỏa quan hệ cạnh. |
| **Biểu diễn trên máy** | Dữ liệu được mã hóa và tổ chức ra sao? | Đánh số đỉnh 0..n−1; lưu E bằng danh sách kề, ma trận kề hoặc danh sách cạnh. |

**Thuật toán** nằm giữa đặc tả và biểu diễn: nó phải thực hiện phép tính được đặc tả trên mô hình, nhưng thời gian và bộ nhớ thực tế phụ thuộc cách truy cập dữ liệu trong biểu diễn cụ thể.

Ví dụ, phép toán trừu tượng “lấy mọi đỉnh kề đi ra từ u” có cùng ý nghĩa trong cả danh sách kề và ma trận kề. Tuy nhiên, với ma trận kề, muốn tìm các đỉnh kề thường phải quét một hàng n ô; còn với danh sách kề, chỉ cần duyệt những cạnh xuất phát từ u.

### Không đồng nhất đối tượng với cấu trúc chứa nó

- Tập hợp **S = {2, 5, 9}** không có thứ tự và không chứa phần tử lặp. Máy tính có thể lưu bằng HashSet, TreeSet, mảng đã sắp xếp hoặc bitset, với các điều kiện miền giá trị thích hợp.
- Dãy **(2, 5, 9)** có thứ tự. Dãy (9, 5, 2) là dãy khác, dù hai dãy có cùng tập phần tử.
- Quan hệ cạnh **E = {(0, 1), (0, 2)}** là thông tin logic. Danh sách kề có thể lưu các hàng theo thứ tự khác nhau mà vẫn biểu diễn cùng E, nếu thứ tự cạnh không phải một phần của đề bài.
- Ma trận chứa các số 0 và 1 không tự động là một đồ thị: cần quy ước rõ trục hàng/cột tương ứng với đỉnh nào và giá trị 1 có nghĩa gì.

Cần viết rõ **ngữ nghĩa** trước rồi mới quyết định định dạng dữ liệu.

## 2. Đặc tả độc lập với biểu diễn

Một mô tả bài toán nên đủ rõ để người đọc giải được mà không cần biết dùng Java, Python, SQL hay cấu trúc dữ liệu nào.

Chẳng hạn, đặc tả bài toán trên đồ thị có hướng, không trọng số:

- **Đầu vào toán học:** G = (V, E), s ∈ V, t ∈ V.
- **Đầu ra:** d(s, t), là số cạnh ít nhất trên một đường đi có hướng từ s tới t. Nếu không tồn tại đường đi, trả một trạng thái “không tới được”.
- **Điều kiện đúng:** Nếu s = t thì d(s, s) = 0. Với mỗi đường đi từ s đến t dài k cạnh, d(s, t) ≤ k; nếu có đường đi thì tồn tại ít nhất một đường đi đạt độ dài d(s, t).
- **Giả thiết:** Mỗi cạnh có độ dài một đơn vị; không áp dụng trực tiếp kết luận này cho đồ thị có trọng số tùy ý.

Chưa cần nói gì đến số lượng mảng, chỉ số bắt đầu từ 0 hay giá trị nào đánh dấu “không tới được”. Đó là các quyết định ở tầng biểu diễn hoặc giao diện triển khai.

Một cách viết đặc tả tốt cho bài toán khác cũng theo trình tự này: **đối tượng → ràng buộc → kết quả → tiêu chí đúng → giả thiết**. Khi thay đổi cách lưu trữ, các điều kiện này giữ nguyên.

## 3. Mối quan hệ hình thức giữa mô hình và dữ liệu

Giả sử **M** là tập các đối tượng hợp lệ của mô hình toán học, **R** là tập trạng thái dữ liệu mà chương trình có thể nắm giữ.

Một **hàm trừu tượng hóa** α ánh xạ trạng thái biểu diễn hợp lệ r ∈ R về đối tượng toán học mà nó đại diện: **α(r) = m ∈ M**.

Ta còn cần **bất biến biểu diễn (representation invariant)**, viết là **RI(r)**, để nhận biết trạng thái r nào thực sự được phép dùng. Ví dụ:

- Với mảng lưu tập hợp theo thứ tự tăng dần, RI yêu cầu các phần tử **đã sắp xếp và không trùng**.
- Với ma trận kề đồ thị vô hướng đơn, RI có thể yêu cầu **A[u][v] = A[v][u]** và, nếu cấm khuyên, **A[u][u] = false**.
- Với mã hóa đỉnh bằng chỉ số mảng, RI yêu cầu mọi đỉnh xuất hiện trong cạnh đều thuộc khoảng **0..n−1**.

Hai biểu diễn r₁ và r₂ được xem là **tương đương về ngữ nghĩa** đối với mô hình khi **α(r₁) = α(r₂)**. Nếu đỉnh được đổi nhãn nhất quán, có thể cần so sánh **tương đương theo phép đổi nhãn** thay vì đòi mọi mã số bên trong bằng nhau.

Nếu truy vấn toán học là **F(m, q)**, hiện thực trên biểu diễn r phải trả kết quả có cùng ý nghĩa với **F(α(r), q)**. Đối với truy vấn có đáp án duy nhất, như độ dài đường đi ngắn nhất, hai biểu diễn tương đương phải cho cùng giá trị. Đối với truy vấn “tìm một nghiệm”, hai thuật toán có thể trả **hai nghiệm khác nhau nhưng đều hợp lệ**; khi đó chỉ so sánh bằng nhau từng ký tự là không đủ để kiểm tra tính đúng.

**Ý nghĩa thực hành:** Chỉ đổi cấu trúc dữ liệu, thuật toán duyệt hay phương thức truy cập không được âm thầm làm đổi tập phương án hợp lệ, quy tắc so sánh hoặc định nghĩa kết quả.

## 4. Một đối tượng, nhiều cách biểu diễn

### 4.1. Tập hợp, dãy và đa tập

Mô hình **tập hợp** không lưu số lần xuất hiện của phần tử; mô hình **đa tập (multiset)** có lưu số lần; mô hình **dãy (sequence)** còn có thứ tự.

Ví dụ đầu vào [2, 2, 5]:

| Mô hình muốn diễn tả | Thông tin cần giữ | Kết quả/ý nghĩa |
| --- | --- | --- |
| Tập hợp {2, 5} | Mỗi giá trị phân biệt | Số phần tử là 2 |
| Đa tập {2×2, 5×1} | Giá trị và bội số | Tổng số phần tử kể cả lặp là 3 |
| Dãy (2, 2, 5) | Vị trí và giá trị | Vị trí đầu và vị trí thứ hai là hai phần tử khác nhau |

Đưa dãy [2, 2, 5] vào HashSet và nhận {2, 5} là phép biến đổi **mất thông tin** nếu bài toán cần vị trí hoặc số lần xuất hiện. Ngược lại, nếu đặc tả chỉ quan tâm các giá trị phân biệt thì đó có thể là cách biểu diễn phù hợp.

Đừng tự mặc định rằng việc duyệt một HashSet phải trả theo thứ tự tăng dần hay theo thứ tự chèn. Nếu đề yêu cầu đầu ra ổn định theo thứ tự, phải đưa yêu cầu sắp xếp vào đặc tả hoặc chọn cấu trúc duy trì đúng thứ tự ấy.

### 4.2. Đồ thị và ba định dạng phổ biến

Với đồ thị có hướng **G = (V, E)**, đặt **n = |V|** đỉnh và **m = |E|** cạnh:

- **Danh sách cạnh:** Lưu từng cặp (u, v). Phù hợp đọc dữ liệu đầu vào, duyệt toàn bộ cạnh, một số thuật toán xử lý cạnh theo lô.
- **Danh sách kề:** Với mỗi u, lưu các đỉnh v sao cho (u, v) ∈ E. Thường phù hợp đồ thị thưa và thuật toán thường xuyên hỏi các đỉnh kề.
- **Ma trận kề:** Dùng n×n ô, A[u][v] là true khi có cạnh u → v. Hữu ích khi cần kiểm tra sự tồn tại của một cạnh thường xuyên và n đủ nhỏ.

| Biểu diễn đơn giản | Dung lượng lưu trữ | Duyệt mọi cạnh đi ra từ u | Kiểm tra u → v trực tiếp |
| --- | --- | --- | --- |
| Danh sách cạnh dạng mảng | O(m) | O(m) nếu quét toàn bộ | O(m) nếu quét |
| Danh sách kề dạng mảng danh sách | O(n + m) | O(deg⁺(u)) | O(deg⁺(u)) nếu tìm tuyến tính |
| Ma trận kề boolean | O(n²) | O(n) để quét một hàng | O(1) |

Các độ phức tạp trên giả sử đã ánh xạ nhãn đỉnh sang chỉ số thích hợp và dùng các cấu trúc mảng tiêu chuẩn; cách triển khai khác như tập băm cho từng hàng kề sẽ có chi phí khác.

**Không phải mọi mô hình đồ thị đều được ma trận boolean giữ nguyên nghĩa.** Nếu bài toán là **đa đồ thị** (có nhiều cạnh song song) hoặc đồ thị có trọng số, boolean A[u][v] chỉ cho biết có ít nhất một cạnh và làm mất các thông tin còn lại. Khi đó cần mô hình biểu diễn khác, chẳng hạn danh sách đối tượng cạnh, ma trận chứa trọng số kèm trạng thái có/không có cạnh, hoặc cấu trúc đếm số cạnh. Khi dùng ma trận trọng số, **không được mặc định trọng số 0 nghĩa là không có cạnh**, bởi cạnh trọng số 0 có thể hợp lệ.

### 4.3. Chỉ số mảng và tên đối tượng

Một bài toán có thể đặt tập đỉnh **V = {Hà Nội, Huế, Đà Nẵng}** hoặc V = {A, B, C}. Muốn lưu bằng mảng, có thể định nghĩa ánh xạ **id: V → {0, 1, ..., n−1}** là một song ánh.

- Trong mã Java, phần tử ở vị trí 0 là **mã máy tính** cho một đỉnh; không phải bản chất toán học của đỉnh đó.
- Nếu thay đổi id nhưng đồng thời đổi mọi đầu mút cạnh, nguồn, đích và dữ liệu liên quan nhất quán, các kết quả về cấu trúc đồ thị không đổi.
- Nếu chỉ đổi nhãn trong một phần của dữ liệu, chương trình sẽ tính trên đồ thị khác.

Điều tương tự xảy ra với công thức toán học dùng chỉ số 1..n, còn mảng Java dùng 0..n−1. Chuyển chỉ số phải có quy ước và kiểm tra biên rõ ràng.

### 4.4. Số, khoảng và chuỗi

**Số nguyên:** Mô hình số nguyên toán học không bị giới hạn về độ lớn. Kiểu int trong Java có miền hữu hạn; long cũng vậy. Nếu kết quả đếm có thể đạt 2^n, phải phân tích giới hạn và cân nhắc BigInteger. Tràn số không chỉ là “vấn đề kỹ thuật”: nó có thể làm đảo dấu, sai phép so sánh và thay đổi kết quả bài toán.

**Số thực:** Phần lớn số thập phân không được biểu diễn chính xác bằng kiểu double nhị phân. Nếu đặc tả cần giá trị tiền tệ chính xác theo đơn vị thập phân, cân nhắc số nguyên theo đơn vị nhỏ nhất hoặc BigDecimal với quy tắc làm tròn rõ ràng. Thuật toán trên số thực còn cần nói rõ sai số cho phép; không thể tự suy ra từ biểu diễn floating-point rằng hai giá trị xấp xỉ phải được coi là bằng nhau.

**Khoảng:** Khoảng đóng **[a, b]** chứa cả hai đầu mút; khoảng nửa mở **[a, b)** không chứa b. Với dữ liệu nguyên rời rạc, [2, 5] và [2, 6) chứa cùng các số nguyên 2, 3, 4, 5, nhưng **không phải hai tập bằng nhau trên số thực**. Khi chuyển một khoảng nguyên đóng sang khoảng nửa mở bằng cách cộng 1 vào đầu phải, cần tránh tràn số và giữ đúng miền giá trị.

**Chuỗi:** “Ký tự” có thể là đơn vị UTF-16, Unicode code point hoặc cụm ký tự người dùng nhìn thấy (grapheme cluster). Trong Java, String.length() đếm **đơn vị mã UTF-16**, không phải luôn là số code point hay số chữ hiển thị. Nếu bài toán yêu cầu so sánh, đếm hay cắt “ký tự”, phải xác định đang xét đơn vị nào trước khi chọn cách lưu và duyệt chuỗi.

## 5. Ví dụ Java 17: Một thuật toán, hai cách lưu đồ thị

Xét đồ thị có hướng, đơn, không trọng số, gồm năm đỉnh đánh số 0..4, với các cạnh:

**E = {(0, 1), (0, 2), (1, 3), (2, 3), (3, 4)}**.

Ta cần tính **số cạnh ít nhất** từ s đến t. Thuật toán BFS làm việc qua một **giao diện trừu tượng** có hai phép toán: biết số đỉnh và liệt kê các đỉnh kề đi ra từ một đỉnh. Hai lớp lưu trữ cài đặt giao diện đó theo cách riêng.

Chương trình độc lập dưới đây dùng cùng BFS cho danh sách kề và ma trận kề. Trong ví dụ này mọi đầu mút cạnh đã hợp lệ và không có cạnh song song.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class GraphModelDemo {
    interface DirectedGraph {
        int vertexCount();
        Iterable<Integer> successors(int u);
    }

    static final class AdjacencyListGraph implements DirectedGraph {
        private final List<List<Integer>> adjacency;

        AdjacencyListGraph(int n, int[][] edges) {
            adjacency = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                adjacency.add(new ArrayList<>());
            }
            for (int[] edge : edges) {
                adjacency.get(edge[0]).add(edge[1]);
            }
        }

        @Override
        public int vertexCount() {
            return adjacency.size();
        }

        @Override
        public Iterable<Integer> successors(int u) {
            return adjacency.get(u);
        }
    }

    static final class AdjacencyMatrixGraph implements DirectedGraph {
        private final boolean[][] adjacency;

        AdjacencyMatrixGraph(int n, int[][] edges) {
            adjacency = new boolean[n][n];
            for (int[] edge : edges) {
                adjacency[edge[0]][edge[1]] = true;
            }
        }

        @Override
        public int vertexCount() {
            return adjacency.length;
        }

        @Override
        public Iterable<Integer> successors(int u) {
            List<Integer> result = new ArrayList<>();
            for (int v = 0; v < adjacency.length; v++) {
                if (adjacency[u][v]) {
                    result.add(v);
                }
            }
            return result;
        }
    }

    // Tra so canh it nhat; -1 la quy uoc bao khong toi duoc.
    static int shortestDistance(DirectedGraph graph, int source, int target) {
        int[] distance = new int[graph.vertexCount()];
        Arrays.fill(distance, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        distance[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            if (u == target) {
                return distance[u];
            }

            for (int v : graph.successors(u)) {
                if (distance[v] == -1) {
                    distance[v] = distance[u] + 1;
                    queue.addLast(v);
                }
            }
        }

        return -1;
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0, 1}, {0, 2}, {1, 3}, {2, 3}, {3, 4}
        };

        DirectedGraph listGraph = new AdjacencyListGraph(5, edges);
        DirectedGraph matrixGraph = new AdjacencyMatrixGraph(5, edges);

        System.out.println("List 0->4: " +
                shortestDistance(listGraph, 0, 4));
        System.out.println("Matrix 0->4: " +
                shortestDistance(matrixGraph, 0, 4));
        System.out.println("List 4->0: " +
                shortestDistance(listGraph, 4, 0));
        System.out.println("Matrix 4->0: " +
                shortestDistance(matrixGraph, 4, 0));
    }
}
~~~

Lưu thành **GraphModelDemo.java**, rồi chạy với JDK 17 trở lên:

~~~bash
javac GraphModelDemo.java
java GraphModelDemo
~~~

Kết quả:

~~~text
List 0->4: 3
Matrix 0->4: 3
List 4->0: -1
Matrix 4->0: -1
~~~

**Tại sao kết quả giống nhau?** Cả hai đối tượng đều biểu diễn cùng E. BFS mở rộng theo từng lớp khoảng cách: từ 0 đi đến 1 hoặc 2 mất một cạnh, đến 3 mất hai cạnh và đến 4 mất ba cạnh. Không có cạnh đi ra từ 4 trong ví dụ, nên không tới được 0. Các lớp biểu diễn có thứ tự duyệt và chi phí thao tác khác nhau, nhưng không làm thay đổi tập cạnh.

**Tại sao hiệu năng có thể khác?** Với danh sách kề, BFS thông thường chạy **O(n + m)** thời gian; mỗi đỉnh được đưa vào hàng đợi tối đa một lần và mỗi cạnh được duyệt trong danh sách tương ứng. Với lớp ma trận trong ví dụ, mỗi đỉnh đã thăm phải quét n cột để tạo danh sách kề, nên giới hạn thời gian là **O(n²)**. Bộ nhớ chứa đồ thị lần lượt là O(n + m) và O(n²); BFS tự dùng thêm O(n) cho khoảng cách và hàng đợi. Việc dựng danh sách tạm trong phương thức successors của ma trận cũng làm phát sinh bộ nhớ tạm.

Bài toán toán học không tự quy định phải dùng cách lưu nào. Thay biểu diễn có thể giảm bộ nhớ hoặc tăng tốc thao tác mà vẫn giữ kết quả. Trong chương trình sản xuất nên bổ sung kiểm tra chỉ số đầu vào, quy tắc bất biến và, tùy yêu cầu, giới hạn quyền sửa cấu trúc dữ liệu.

## 6. Đổi biểu diễn mà không đổi bài toán

Một quá trình chuyển đổi an toàn gồm các bước sau:

1. **Chốt mô hình:** Viết rõ đối tượng và quan hệ. Ví dụ, đồ thị có hướng hay vô hướng, có cạnh lặp không, có trọng số âm không, đỉnh có nhãn riêng không.
2. **Chốt đặc tả đầu ra:** Trả một nghiệm, mọi nghiệm, số lượng, giá trị tối ưu hay kết quả đúng/sai? Đầu ra có yêu cầu thứ tự hay không?
3. **Chọn cấu trúc lưu:** Dựa trên số đỉnh/cạnh, giới hạn bộ nhớ, kiểu truy vấn và thao tác cập nhật. Nếu cần hỏi nhanh “có cạnh u → v không?”, ma trận hoặc tập kề phù hợp hơn mảng cạnh quét tuyến tính.
4. **Định nghĩa ánh xạ và bất biến:** Nêu cách một giá trị lưu trữ đại diện cho đối tượng toán học; xác định các trạng thái không hợp lệ và cách xử lý.
5. **Tách thuật toán khỏi dữ liệu khi hữu ích:** Xây API theo thao tác logic, ví dụ successors(u), contains(x), neighbors(u), weight(u, v), thay vì để thuật toán đọc trực tiếp cấu trúc nội bộ ở nhiều nơi.
6. **Kiểm tra tương đương:** Chạy cùng bộ truy vấn trên hai biểu diễn của cùng một đối tượng, so sánh kết quả theo đặc tả; kết hợp kiểm tra các bất biến sau khởi tạo và sau cập nhật.

**Ví dụ đổi cách lưu:** Một ứng dụng lưu tập ID duy nhất bằng danh sách tăng dần có thể chuyển sang HashSet để tăng tốc tra cứu trung bình. Nhưng nếu người dùng đang trông đợi hiển thị theo thứ tự tăng dần, cần giữ bước sắp xếp khi xuất. Yêu cầu hiển thị là một phần của giao diện/đặc tả; không thể giao ngầm cho thứ tự duyệt của HashSet.

## 7. Những lỗi thường gặp khi trộn hai tầng

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng **0** biểu thị “không có cạnh” trong đồ thị có trọng số 0 hợp lệ | Gộp hai trạng thái logic thành một mã | Dùng kiểu có trạng thái hiện diện riêng hoặc sentinel ngoài miền trọng số |
| Coi HashSet là dãy được sắp xếp | Gán ý nghĩa thứ tự cho cấu trúc tập hợp | Đưa thứ tự vào đặc tả và sắp xếp khi cần |
| Dùng mảng/matrix boolean lưu đa đồ thị | Làm mất bội số cạnh | Dùng danh sách đối tượng cạnh hoặc số lượng cạnh |
| Coi mọi đỉnh liên tiếp 0..n−1 là tên gốc | Nhầm ID lưu trữ với nhãn/đối tượng | Tạo ánh xạ hai chiều và dùng nhất quán |
| Dùng int cho số lượng tổ hợp rất lớn | Tràn số làm sai đáp án | Xác định chặn trên; dùng long, BigInteger hoặc modulo nếu đề cho phép |
| Dùng double để so sánh chính xác tiền tệ | Sai số biểu diễn nhị phân | Chọn số nguyên đơn vị nhỏ hoặc BigDecimal và quy tắc làm tròn |
| Nhầm [l, r] với [l, r) | Thêm/bớt phần tử ở biên | Chỉ rõ quy ước, đổi đầu mút đúng miền |
| Sắp xếp dữ liệu rồi coi kết quả sắp xếp là “cùng dãy” | Đổi đối tượng nếu thứ tự là thành phần của mô hình | Chỉ sắp xếp nếu bài toán cho phép hoặc lưu ánh xạ vị trí |
| Dùng BFS để giải đường đi ngắn nhất với trọng số tùy ý | Thuật toán giải mô hình khác | Dùng thuật toán thích hợp với đặc tính trọng số, chẳng hạn Dijkstra khi trọng số không âm |
| Viết thuật toán phụ thuộc trực tiếp vào định dạng file | Thay đổi định dạng kéo theo thay đổi logic, dễ phát sinh lỗi | Tách bước parse/validate, mô hình và giải thuật |

Một khác biệt quan trọng là **thứ tự duyệt**. Nếu đề chỉ yêu cầu một đường đi ngắn nhất, hai biểu diễn có thể chọn hai đường khác nhau nhưng cùng độ dài tối thiểu. Nếu đề yêu cầu “đường đi có thứ tự từ điển nhỏ nhất trong những đường ngắn nhất”, thứ tự lựa chọn lại là **một điều kiện của đặc tả** mà thuật toán phải thực hiện.

## 8. Kiểm tra tính đúng khi thay cách lưu

Không nên chỉ so sánh hai lần chạy trên một ví dụ thuận lợi. Bộ kiểm tra nên bao phủ:

- **Trường hợp cơ sở:** Tập rỗng, đồ thị không cạnh, một đỉnh, s = t, đường đi không tồn tại.
- **Trường hợp biên:** ID nhỏ nhất/lớn nhất, số đỉnh/cạnh lớn, giá trị 0, số âm (nếu mô hình cho phép), số lớn dễ tràn.
- **Ngữ nghĩa đặc biệt:** Đồ thị có hướng hay vô hướng; cạnh lặp, cạnh khuyên, trọng số 0; thứ tự phần tử và phần tử trùng.
- **Thuộc tính cần giữ:** Sau khi mã hóa rồi giải mã, đối tượng có cùng ý nghĩa; kết quả truy vấn độc lập với cách lưu, trừ các khác biệt được đặc tả cho phép.
- **Biến đổi bảo toàn mô hình:** Hoán đổi thứ tự các cạnh đầu vào không đổi bài toán đồ thị đơn; đổi nhãn đỉnh nhất quán không đổi khoảng cách giữa hai đỉnh tương ứng.

Với bài toán có **đáp án duy nhất**, so sánh trực tiếp giá trị là phù hợp. Với bài toán có **nhiều nghiệm hợp lệ**, nên kiểm tra mỗi nghiệm trả về đều thỏa ràng buộc và đạt tiêu chí cần thiết; không áp đặt rằng hai thuật toán phải chọn cùng một nghiệm. Với bài toán liệt kê, còn phải kiểm tra **không thiếu, không trùng** theo quy ước đếm nghiệm.

Nếu kiểm tra tự động bằng dữ liệu nhỏ, có thể xây một biểu diễn đơn giản làm mô hình tham chiếu, rồi so kết quả với biểu diễn tối ưu cho dữ liệu lớn. Đây là cách rất hiệu quả để phát hiện lỗi ở bước chuyển đổi lưu trữ.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Tập S = {3, 7, 9} được lưu thành mảng [9, 3, 7] và mảng [3, 7, 9]. Hai mảng có biểu diễn cùng S không?  
**Đáp án:** Có, **nếu** đặc tả xem mảng là biểu diễn tập hợp và mỗi giá trị xuất hiện đúng một lần. Nếu mô hình là dãy, hai mảng là hai dãy khác nhau.

**Câu 2.** Đồ thị có n = 10.000 đỉnh nhưng chỉ m = 20.000 cạnh. Danh sách kề hay ma trận kề boolean thường phù hợp hơn khi chạy BFS?  
**Đáp án:** Danh sách kề thường tiết kiệm bộ nhớ và cho phép BFS O(n + m), trong khi ma trận kề lưu O(n²) ô và thường khiến BFS mất O(n²) thời gian.

**Câu 3.** Chương trình đổi nhãn đỉnh 1 thành 0, 2 thành 1, ... nhưng không đổi các đầu mút trong danh sách cạnh. Đây chỉ là đổi cách lưu không?  
**Đáp án:** Không. Các phần của dữ liệu không còn thống nhất; chương trình có thể đang biểu diễn một đồ thị khác hoặc trạng thái không hợp lệ.

**Câu 4.** Hai lần chạy BFS tìm được hai đường đi ngắn nhất khác nhau cùng độ dài 5. Có mâu thuẫn với tính đúng không?  
**Đáp án:** Không, nếu đề chỉ cần một đường đi ngắn nhất; có thể có nhiều nghiệm tối ưu. Nếu đề quy định cách chọn riêng, như thứ tự từ điển nhỏ nhất, phải thỏa quy định ấy.

**Câu 5.** Một ma trận trọng số dùng số 0 cho “không có cạnh”, nhưng bài toán cho phép cạnh trọng số 0. Vấn đề ở đâu?  
**Đáp án:** Biểu diễn không phân biệt được **không có cạnh** với **cạnh tồn tại và có trọng số 0**. Phải sửa mã hóa hoặc bổ sung cờ hiện diện.

## 10. Ghi nhớ để áp dụng

Trước khi viết cấu trúc dữ liệu, hãy tự trả lời năm câu hỏi:

1. **Đối tượng toán học là gì?** Tập, dãy, đa tập, đồ thị, quan hệ, khoảng, số hay trạng thái khác?
2. **Điều gì là đúng/sai ở tầng đặc tả?** Các giả thiết và điều kiện nghiệm nào không được đổi?
3. **Biểu diễn lưu giữ thông tin nào và có làm mất thông tin không?** Trùng lặp, thứ tự, hướng, trọng số, độ chính xác và nhãn có còn nguyên?
4. **Bất biến nào bảo đảm dữ liệu hợp lệ?** Có thể diễn tả và kiểm tra chúng sau các thao tác cập nhật không?
5. **Cần thao tác gì để thuật toán hiệu quả?** Truy cập theo chỉ số, tra cứu thành viên, duyệt lân cận, cập nhật hay truy vấn theo thứ tự?

**Nguyên tắc cốt lõi:** Đặc tả quyết định **bài toán phải trả lời điều gì**; mô hình toán học quyết định **đối tượng và quan hệ có ý nghĩa gì**; biểu diễn trên máy quyết định **ta lưu trữ và truy cập chúng như thế nào**. Chuyển biểu diễn là đúng khi duy trì các bất biến và bảo toàn ngữ nghĩa quan trọng của mô hình, đồng thời có thể thay đổi chi phí thời gian, bộ nhớ và cách lập trình.