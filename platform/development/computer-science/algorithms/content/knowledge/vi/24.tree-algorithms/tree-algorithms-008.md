# Tìm đường kính cây với giả thiết trọng số phù hợp

## 1. Đặt bài toán cho đúng trước khi chọn thuật toán

**Đường kính cây (tree diameter)** là độ dài lớn nhất của đường đi giữa hai đỉnh trên một **cây vô hướng**. Cây có n đỉnh, n−1 cạnh, liên thông và không có chu trình; vì vậy giữa mọi cặp đỉnh u,v có **duy nhất một đường đi đơn**.

Có ba loại đề thường gặp nhưng không được đánh đồng:

1. **Cây không trọng số:** độ dài là **số cạnh** trên đường đi; có thể xem tất cả cạnh có trọng số 1. Dùng **BFS/DFS hai lượt** để tìm đường kính trong O(n).
2. **Cây có trọng số không âm:** độ dài bằng **tổng trọng số** trên đường đi, mọi w≥0. Dùng **hai lượt duyệt cây** (DFS hoặc BFS kiểu xây cha và cộng trọng số), tìm đỉnh có khoảng cách lớn nhất sau mỗi lượt; vẫn đúng trong O(n).
3. **Cây có cạnh âm:** tổng đường đi có thể âm. Thuật toán **hai lần chọn đỉnh xa nhất không còn bảo đảm đúng**, mặc dù mỗi lần DFS vẫn tính tổng theo đường duy nhất chính xác. Có thể dùng **quy hoạch động trên cây (tree DP)** để tìm đường đi có tổng lớn nhất.

Cần xác định thêm: đường đi tối ưu có được **0 cạnh** hay phải nối **hai đỉnh khác nhau**? Khi có trọng số âm, hai quy ước có thể cho đáp án khác nhau.

Bài học đi từ định nghĩa và giả thiết, chứng minh hai lượt khi w≥0, chỉ ra phản ví dụ khi w<0, rồi đưa chương trình Java 17 chạy độc lập cho **hai lượt không âm** và **tree DP trọng số có dấu**, kèm kiểm thử và truy vết.

## 2. Định nghĩa, đơn vị đo và hai quy ước

Cho cây \(T=(V,E)\) có n≥1. Mỗi cạnh vô hướng e mang trọng số nguyên \(w(e)\). Vì chỉ có một đường đi đơn \(P(u,v)\), đặt:

\[
d(u,v)=\sum_{e\in P(u,v)} w(e).
\]

Cây không trọng số là trường hợp w(e)=1. Nếu mọi w≥0 thì d(u,v) không âm; nếu có w<0 thì d không nhất thiết là “khoảng cách” theo nghĩa metric, dù tổng trọng số vẫn xác định.

**Quy ước cho phép cùng đầu mút (đường 0 cạnh):**

\[
D_0=\max_{u,v\in V}d(u,v).
\]

Đường đi u→u có tổng 0, nên D_0≥0. Với n=1, D_0=0 và đường [0].

**Quy ước bắt buộc hai đầu khác nhau (đường ít nhất một cạnh):**

\[
D_1=\max_{\substack{u,v\in V\\u\ne v}}d(u,v).
\]

Giá trị D_1 chỉ có nghĩa khi **n≥2**. Nó có thể **âm**: trên cây chỉ có cạnh 0--1 trọng số −5, D_1=−5, còn D_0=0.

Khi n≥2 và mọi trọng số không âm, D_0 và D_1 có **cùng giá trị**. Chương trình hai lượt chọn **hai đầu khác nhau** nếu n≥2, kể cả khi tất cả trọng số đều 0. Nếu n=1, chương trình trả đường [0] với giá trị 0.

**Giả thiết cấu trúc:** Đầu vào phải thật sự là cây; một đồ thị có n−1 cạnh **chưa chắc** là cây nếu có chu trình trong một thành phần và đỉnh cô lập ở thành phần khác. Chương trình dùng DSU để kiểm tra cấu trúc và từ chối đồ thị không hợp lệ.

## 3. Điểm then chốt: tính khoảng cách khác chọn đường kính

Giả sử chọn một đỉnh gốc s. Do cây không có chu trình, đường từ s tới v là duy nhất. Khi đi DFS hoặc BFS và lưu cha, ta tính được:

\[
dist[s]=0,\qquad
dist[v]=dist[parent[v]]+w(parent[v],v).
\]

Công thức này đúng trên cây **cho cả trọng số âm**, vì không cần tìm giữa nhiều đường khác nhau.

Nhưng quy tắc:

> Lấy một đỉnh xa nhất a từ s, rồi lấy một đỉnh xa nhất b từ a thì a–b là đường kính

**chỉ có bảo đảm tổng quát khi trọng số không âm**. Tính đúng của một lượt cộng trọng số **không kéo theo** tính đúng của phép chọn hai đầu mút khi có cạnh âm.

Trong đồ thị tổng quát có chu trình, DFS trên một cây duyệt chỉ tính độ dài theo **các cạnh cây DFS**, không bảo đảm đó là khoảng cách ngắn nhất. Vì vậy không thể bê nguyên thuật toán đường kính cây sang đồ thị tổng quát.

### Có cần Dijkstra trên cây có trọng số không âm?

**Không.** Dijkstra dùng min-heap để chọn đường ngắn nhất trong đồ thị có thể có nhiều đường thay thế. Trên cây, mỗi cặp đỉnh chỉ có **một** đường đơn; cộng trọng số dọc đường cha–con trong O(n) đã cho chính xác d(s,v), không cần PriorityQueue.

Với cây **không trọng số**, có thể dùng BFS và tăng mỗi cạnh thêm 1. Với cây có trọng số, dù dùng hàng đợi FIFO hay stack DFS để duyệt, **không được giả định đỉnh ra hàng đợi cuối cùng có tổng trọng số lớn nhất**; phải quét mọi dist sau khi duyệt.

## 4. Hai lượt duyệt cho cây không trọng số

Nếu mỗi cạnh dài đúng 1, làm như sau:

~~~text
diameterUnweighted(tree):
    start = 0
    first = BFS(tree, start)           // dist = số cạnh
    a = một đỉnh xa nhất từ start

    second = BFS(tree, a)
    b = một đỉnh xa nhất từ a

    return second.dist[b],
           đường a -> b truy bằng second.parent
~~~

Tại sao gọi là hai lượt? Vì lần đầu chỉ dùng để tìm **một đầu mút a**; lần hai tìm đầu còn lại b và xác định chiều dài. Không cần thử mọi cặp đỉnh.

Ví dụ đường:

~~~text
0 -- 1 -- 2 -- 3 -- 4 -- 5
~~~

BFS từ 0 chọn a=5 (cách 5 cạnh). BFS từ 5 chọn b=0 (cách 5 cạnh). Đường kính theo **số cạnh** bằng 5.

Nếu đề hỏi số **đỉnh** trên đường kính, trong đường này có **6 đỉnh**, nhưng độ dài theo quy ước số cạnh là 5. Khi in kết quả, phải ghi rõ đơn vị đo.

**Chú ý:** Hai lượt BFS để lấy đường kính **không đúng trên đồ thị tùy ý có chu trình**. Tính chất đỉnh xa nhất là đầu đường kính được dùng ở đây là định lý riêng của **cây**.

## 5. Hai lượt duyệt cho cây có trọng số không âm

Khi trọng số cạnh không âm, chỉ thay phép cộng 1 bằng trọng số thật:

~~~text
twoSweepsNonnegative(tree):
    validate(tree)
    assert every edge weight >= 0

    first = traverseUniqueTreePaths(tree, 0)
    a = argmax_v first.distance[v]

    second = traverseUniqueTreePaths(tree, a)
    b = argmax_v second.distance[v]

    return length=second.distance[b],
           endpoints=(a,b),
           path=reconstruct(second.parent, b)
~~~

Hàm traverseUniqueTreePaths **không cần PriorityQueue**: mỗi đỉnh chỉ có một đường duy nhất từ gốc, nên một lượt DFS/stack đủ để tính tổng.

**Chính sách hòa của chương trình:**
- Khi có nhiều ứng viên với cùng khoảng cách lớn nhất, chọn **ID nhỏ nhất**.
- Khi n≥2, không chọn chính nguồn của lượt duyệt làm đỉnh xa nhất, để kết quả có **hai đầu khác nhau**.
- Khi n=1, chỉ có đỉnh 0, cho phép from=to=0 với chiều dài 0.
- Đầu mút trả về không bắt buộc duy nhất; **độ dài đường kính** vẫn đúng.

**Trọng số 0 được phép.** Ví dụ 0--(0)--1--(0)--2 có đường kính bằng 0. Chương trình chọn a=1 từ gốc 0, rồi b=0 từ a=1; đường [1,0] có tổng 0, hợp lệ theo quy ước hai đầu khác nhau.

### Tính đúng của mảng parent

Lượt thứ hai xuất phát từ a. Khi phát hiện v từ u qua cạnh (u,v), lưu parent[v]=u. Đi ngược parent từ b tới a rồi đảo danh sách thu được đường a→b, là đường đơn duy nhất trên cây. **Không dùng mảng parent của lượt đầu** để khôi phục đường a→b, vì mảng ấy được xây từ gốc s khác.

## 6. Vì sao hai lượt đúng khi mọi trọng số không âm?

Định lý quen thuộc cho cây trọng số không âm:

**Một đỉnh xa nhất a từ một đỉnh s bất kỳ luôn là đầu của ít nhất một đường kính; vì vậy một đỉnh b xa nhất từ a cho d(a,b)=D.**

Có thể nhìn bằng cấu trúc đường đi của cây. Chọn một đường kính p–q. Đường từ s tới trục p–q chạm trục tại một vị trí duy nhất. Mọi nhánh rẽ khỏi trục có thể được so sánh với hai hướng về p hoặc q. Nếu nhánh đủ dài để tạo đường dài hơn đường p–q, p–q chưa phải đường kính, mâu thuẫn. Giả thiết **độ dài cạnh không âm** bảo đảm các đoạn đường không làm giảm tổng độ dài khi mở rộng theo các hướng cần so sánh. Từ tính chất này suy ra một đỉnh xa nhất từ s nằm ở đầu của một đường kính nào đó.

Vì a là đầu của đường kính, tồn tại q với d(a,q)=D. Lượt thứ hai chọn b xa nhất từ a nên:

\[
d(a,b)\ge d(a,q)=D.
\]

Mặt khác, D là cực đại của tất cả cặp đỉnh, nên d(a,b)≤D. Do đó:

\[
\boxed{d(a,b)=D}.
\]

Đây là chứng minh hai lượt, **không phải** giả thiết rằng “DFS tìm sâu nhất thì tự động tối ưu” với mọi trọng số.

### Trọng số 0 và nhiều đường kính

Khi có cạnh 0, có thể có nhiều cặp đỉnh cho cùng tổng D. Định lý vẫn áp dụng vì trọng số **không âm**. Lựa chọn a,b cụ thể tùy đỉnh bắt đầu và cách phá hòa; chỉ cần kiểm tra đường trả có tổng D.

Nếu yêu cầu **liệt kê tất cả cặp đầu mút đường kính** hoặc chọn cặp theo tiêu chí từ điển toàn cục, thuật toán hai lượt với tie-break cục bộ chỉ trả **một** cặp; cần phương pháp bổ sung để đáp ứng yêu cầu mạnh hơn.

## 7. Ví dụ đầy đủ: cây 9 đỉnh với một cạnh trọng số 0

Các cạnh vô hướng:

| Cạnh | Trọng số |
|---|---:|
| 0--1 | 3 |
| 1--2 | 2 |
| 1--3 | 4 |
| 3--4 | 1 |
| 3--5 | 6 |
| 5--6 | 2 |
| 5--7 | 0 |
| 7--8 | 5 |

Cây có 9 đỉnh, 8 cạnh, không có chu trình. Đường nối từ 0 qua 1,3,5,7 tới 8 có tổng:

\[
3+4+6+0+5=\boxed{18}.
\]

### Lượt đầu từ 0

Mảng khoảng cách theo ID 0..8:

~~~text
[0, 3, 5, 7, 8, 13, 15, 13, 18]
~~~

Đỉnh xa nhất là **a=8**, với tổng 18.

### Lượt thứ hai từ 8

Mảng khoảng cách từ 8:

~~~text
[18, 15, 17, 11, 12, 5, 7, 5, 0]
~~~

Đỉnh xa nhất là **b=0**, với tổng 18.

Đường đường kính trả về:

~~~text
8 -> 7 -> 5 -> 3 -> 1 -> 0
~~~

Đường này có **5 cạnh, 6 đỉnh, tổng trọng số 18**. Nếu đề chỉ đếm số cạnh thì kết quả tương ứng là 5, không phải 18.

Đường 2→1→3→5→7→8 có tổng 2+4+6+0+5=17; đường 0→1→3→5→6 có tổng 3+4+6+2=15. Chúng nhỏ hơn 18.

**Điểm dễ sai:** Đỉnh 7 và 5 có thể có cùng khoảng cách từ một số nguồn vì cạnh 5--7 có trọng số 0. Cần xem trọng số **0** là hợp lệ; không được dùng weight==0 để biểu thị “không có cạnh”.

## 8. Trọng số âm: phản ví dụ phá cả hai cách phá hòa

Xét cây 5 đỉnh:

~~~text
1 --(-1)-- 0 --(-10)-- 2 --(5)-- 3
                          |
                         (5)
                          |
                          4
~~~

Đường từ 0 tới các đỉnh 0..4 có tổng:

~~~text
[0, -1, -10, -5, -5]
~~~

Nếu cho phép lấy chính nguồn làm đỉnh xa nhất, **0 là đỉnh xa nhất từ 0** (tổng 0); lặp hai lượt từ 0 chẳng tìm được đường tổng 10 ở nhánh khác.

Ngay cả nếu **loại nguồn khỏi các ứng viên**, đỉnh xa nhất từ 0 là 1 ở tổng −1. Lượt từ 1 chọn 0 ở tổng −1; hai lượt trả đường **1→0 với tổng −1**.

Nhưng đường:

~~~text
3 -> 2 -> 4
~~~

có tổng **5+5=10**, lớn hơn −1. Đây mới là đường đi tổng lớn nhất giữa hai đỉnh khác nhau.

Vậy:
- **DFS/BFS tính các tổng trên cây vẫn đúng**, cả khi có âm.
- **Chọn đỉnh xa nhất hai lần không đúng** với trọng số âm.
- Chỉ loại s khỏi argmax hoặc sửa thứ tự tie **không khôi phục bảo đảm**.

Khi bài cho phép âm, không dùng hai lượt như một chứng minh tối ưu. Dùng tree DP ở phần tiếp theo.

## 9. Trường hợp tất cả cạnh âm và đường đi rỗng

Cây hai đỉnh:

~~~text
0 --(-5)-- 1
~~~

Nếu bắt buộc hai đầu khác nhau, đường duy nhất có tổng **−5**. Nếu cho phép đầu trùng nhau, đi từ 0 tới chính 0 có tổng **0**, lớn hơn −5.

Vì vậy:
- **D_1=-5** nếu bắt buộc ít nhất một cạnh.
- **D_0=0** nếu cho phép đường đi không cạnh.

Một thuật toán DP khởi tạo đáp án tốt nhất bằng **0** sẽ **sai cho quy ước D_1** khi toàn bộ cạnh đều âm. Phải dùng cờ đã có ứng viên hoặc cách biểu diễn −∞ riêng, không để trường hợp đường rỗng chiếm đáp án.

Với cây **một đỉnh**, D_0=0 nhưng D_1 **không tồn tại**. Chương trình Java trả Optional.empty() cho signed DP trong trường hợp một đỉnh, thay vì bịa một đường có cạnh.

## 10. Tree DP tìm tổng lớn nhất khi trọng số có dấu

Root cây tại 0; hướng các cạnh thành cha→con chỉ phục vụ tính toán, bản chất cây vẫn **vô hướng**. Duyệt tạo danh sách đỉnh và mảng cha, sau đó xử lý thứ tự **ngược của DFS** để bảo đảm mọi con được tính trước cha.

### 10.1. Trạng thái gain[u]

Gọi **gain[u]** là tổng lớn nhất của một đường đi **bắt đầu tại u và đi xuống cây con**, **được phép kết thúc ngay tại u**. Nếu dừng tại u, đường có 0 cạnh và tổng 0:

\[
\boxed{gain[u]=\max\left(0,\max_{v\text{ là con của }u}\bigl(w(u,v)+gain[v]\bigr)\right).}
\]

Ý nghĩa:
- Nếu mọi nhánh đi xuống đều âm, gain[u]=0.
- Nếu tồn tại một nhánh mang giá trị dương, chọn nhánh có tổng lớn nhất.
- gain[u] chỉ là **tối ưu đường đi xuống từ u**, **không phải** đáp án đường kính của cả cây.

Lưu **gainEnd[u]** là đầu mút cuối cùng của nhánh đem lại gain[u], để có thể truy vết đường tốt.

### 10.2. Mỗi đường tối ưu xuất hiện tại LCA của hai đầu

Bất kỳ đường đơn nối hai đỉnh x≠y đều có một **tổ tiên chung thấp nhất (LCA) u** theo gốc 0. Có hai dạng:

1. **Một nhánh:** một đầu chính là u, đầu kia ở một cây con của u. Đường đi từ u xuống con v đóng góp:

\[
c(u,v)=w(u,v)+gain[v].
\]

2. **Hai nhánh:** hai đầu thuộc **hai cây con khác nhau** v1 và v2 của u. Đường đi giữa chúng qua u có tổng:

\[
c(u,v_1)+c(u,v_2).
\]

Vì thế, ở mỗi u:
- Xem **mỗi c(u,v)** là một ứng viên cho đường đi chứa **ít nhất một cạnh**.
- Nếu có từ hai con, chọn **hai contribution lớn nhất từ hai con khác nhau** rồi xem tổng của chúng là một ứng viên.
- Sau đó cập nhật gain[u] với max(0, contribution lớn nhất) để truyền lên cha.

Không được ghép hai nhánh thuộc **cùng một con**, vì khi đó hai nửa đường có thể chồng nhau, không còn một đường đơn. Không được bắt buộc cả hai contribution dương: đôi khi toàn bộ cây có giá trị âm, và **ứng viên một cạnh âm vẫn phải được ghi nhận**.

### 10.3. Cách khôi phục đường đi của signed DP

Khi có một ứng viên tốt hơn, lưu **hai đầu mút** của đường. Không cần sao chép cả đường đi tại từng nút DP. Sau khi tìm được tổng lớn nhất, duyệt từ một đầu a trên cây một lần để tìm mảng parent rồi truy vết đường đơn đến đầu b.

Chương trình chuẩn hóa hai đầu (minID,maxID) để in ổn định. Tie-break trong DP chọn ứng viên đầu mút nhỏ hơn giữa những ứng viên đã được xét; nó **không được thiết kế để bảo đảm cặp từ điển nhỏ nhất trong toàn bộ mọi đường hòa có đoạn gain=0**. Nếu yêu cầu đầu mút theo quy tắc mạnh hơn, cần mở rộng trạng thái hòa và chứng minh riêng.

### 10.4. Hai ví dụ signed DP

**Ví dụ âm ở mục 8:** đỉnh 2 có hai nhánh xuống 3 và 4 cùng contribution +5. Tổng hai nhánh qua 2 là **10**, đường [3,2,4].

**Chuỗi trọng số [6,−2,6]:**

~~~text
0 --(6)-- 1 --(-2)-- 2 --(6)-- 3
~~~

Đường từ 0 tới 3 có tổng **6−2+6=10**; lớn hơn mỗi cạnh đơn +6. Vì vậy không được “loại hết cạnh âm” trước khi tìm đường có tổng lớn nhất. Một đường tối ưu **có thể chứa đoạn âm** nếu hai phần dương bù lại đủ.

### 10.5. Đáp án theo quy ước có cho phép đường 0 cạnh

Tree DP ở đây giải D_1 (hai đầu khác nhau). Khi n≥2 và muốn D_0, có thể lấy:

\[
D_0=\max(0,D_1).
\]

Nếu D_1<0, đường rỗng tại một đỉnh bất kỳ cho tổng 0 và tối ưu theo D_0. Nếu n=1, D_0=0 còn D_1 không tồn tại.

## 11. Chương trình Java 17 hoàn chỉnh

Chương trình sau có hai API riêng:

**twoSweepsNonnegative(n,edges):** xác thực cây và **từ chối mọi cạnh âm**, sau đó duyệt hai lượt, chọn endpoint xa nhất và trả đường đi.

**signedDistinctDiameter(n,edges):** xác thực cây nhưng **cho phép cạnh âm**, dùng tree DP và trả đường đi tổng lớn nhất có **ít nhất một cạnh** dưới dạng Optional<Diameter>.

Mỗi dòng cạnh input có dạng {u,v,w}, lưu dưới dạng long[][] để hỗ trợ trọng số long. Đây là **cạnh vô hướng**, chỉ nhập mỗi cạnh **một lần**; code tự thêm hai chiều vào danh sách kề.

Cả hai thuật toán dùng **stack tường minh**, tránh tràn ngăn xếp gọi hàm khi cây có dạng đường rất dài. Mọi tổng trọng số được tính bằng **Math.addExact**, để báo lỗi overflow thay vì âm thầm cho số sai.

Lưu tệp **TreeDiameterWeightAssumptionsDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

public final class TreeDiameterWeightAssumptionsDemo {
    private TreeDiameterWeightAssumptionsDemo() {
    }

    private record Edge(int to, long weight) {
    }

    public record Diameter(
            long length, int from, int to, List<Integer> path) {
    }

    private record Walk(long[] distance, int[] parent) {
    }

    private static final class Dsu {
        final int[] parent;
        final int[] size;
        int components;

        Dsu(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            while (parent[x] != x) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        boolean union(int x, int y) {
            int a = find(x);
            int b = find(y);
            if (a == b) {
                return false;
            }
            if (size[a] < size[b]) {
                int temp = a;
                a = b;
                b = temp;
            }
            parent[b] = a;
            size[a] += size[b];
            components--;
            return true;
        }
    }

    private static List<List<Edge>> buildTree(
            int n, long[][] rows, boolean requireNonnegative) {
        if (n <= 0 || rows == null || rows.length != n - 1) {
            throw new IllegalArgumentException(
                    "Need n>=1 and exactly n-1 edges");
        }

        List<List<Edge>> tree = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            tree.add(new ArrayList<>());
        }

        Dsu dsu = new Dsu(n);
        for (long[] row : rows) {
            if (row == null || row.length != 3) {
                throw new IllegalArgumentException(
                        "Expected u, v, weight");
            }

            long u = row[0];
            long v = row[1];
            long weight = row[2];

            if (u < 0 || v < 0 || u >= n || v >= n) {
                throw new IllegalArgumentException(
                        "Vertex out of range");
            }
            if (requireNonnegative && weight < 0) {
                throw new IllegalArgumentException(
                        "Two sweeps require nonnegative weights");
            }
            if (!dsu.union((int) u, (int) v)) {
                throw new IllegalArgumentException(
                        "Cycle, parallel edge, or self-loop");
            }

            tree.get((int) u).add(new Edge((int) v, weight));
            tree.get((int) v).add(new Edge((int) u, weight));
        }

        if (dsu.components != 1) {
            throw new IllegalArgumentException("Disconnected graph");
        }
        return tree;
    }

    // Tính tổng trọng số trên đường DUY NHẤT từ source.
    private static Walk traverse(List<List<Edge>> tree, int source) {
        long[] distance = new long[tree.size()];
        int[] parent = new int[tree.size()];
        Arrays.fill(parent, -2);

        ArrayDeque<Integer> stack = new ArrayDeque<>();
        parent[source] = -1;
        stack.push(source);

        while (!stack.isEmpty()) {
            int u = stack.pop();
            for (Edge e : tree.get(u)) {
                int v = e.to();
                if (parent[v] != -2) {
                    continue;
                }
                parent[v] = u;
                distance[v] = Math.addExact(
                        distance[u], e.weight());
                stack.push(v);
            }
        }
        return new Walk(distance, parent);
    }

    private static int farthest(long[] distance, int source) {
        int best = -1;
        long value = Long.MIN_VALUE;

        for (int v = 0; v < distance.length; v++) {
            if (distance.length > 1 && v == source) {
                continue;
            }
            if (best == -1 || distance[v] > value
                    || (distance[v] == value && v < best)) {
                best = v;
                value = distance[v];
            }
        }
        return best;
    }

    private static List<Integer> buildPath(
            int[] parent, int target) {
        List<Integer> reversed = new ArrayList<>();
        for (int at = target; at != -1; at = parent[at]) {
            reversed.add(at);
        }
        Collections.reverse(reversed);
        return List.copyOf(reversed);
    }

    public static Diameter twoSweepsNonnegative(
            int n, long[][] edges) {
        List<List<Edge>> tree = buildTree(n, edges, true);
        Walk first = traverse(tree, 0);
        int a = farthest(first.distance(), 0);
        Walk second = traverse(tree, a);
        int b = farthest(second.distance(), a);

        return new Diameter(second.distance()[b], a, b,
                            buildPath(second.parent(), b));
    }

    // Dựng đường a -> b, không cần cộng trọng số lần nữa.
    private static List<Integer> pathBetween(
            List<List<Edge>> tree, int a, int b) {
        int[] parent = new int[tree.size()];
        Arrays.fill(parent, -2);
        parent[a] = -1;

        ArrayDeque<Integer> stack = new ArrayDeque<>();
        stack.push(a);
        while (!stack.isEmpty()) {
            int u = stack.pop();
            if (u == b) {
                break;
            }
            for (Edge e : tree.get(u)) {
                int v = e.to();
                if (parent[v] != -2) {
                    continue;
                }
                parent[v] = u;
                stack.push(v);
            }
        }
        return buildPath(parent, b);
    }

    private static final class Best {
        boolean present = false;
        long length;
        int from;
        int to;

        void consider(long candidate, int x, int y) {
            int a = Math.min(x, y);
            int b = Math.max(x, y);
            if (!present || candidate > length
                    || (candidate == length
                        && (a < from
                            || (a == from && b < to)))) {
                present = true;
                length = candidate;
                from = a;
                to = b;
            }
        }
    }

    // Đường có ít nhất một cạnh; cho phép trọng số âm.
    public static Optional<Diameter> signedDistinctDiameter(
            int n, long[][] edges) {
        List<List<Edge>> tree = buildTree(n, edges, false);
        if (n == 1) {
            return Optional.empty();
        }

        int[] parent = new int[n];
        Arrays.fill(parent, -2);
        parent[0] = -1;
        int[] order = new int[n];
        int count = 0;

        ArrayDeque<Integer> stack = new ArrayDeque<>();
        stack.push(0);
        while (!stack.isEmpty()) {
            int u = stack.pop();
            order[count++] = u;
            for (Edge e : tree.get(u)) {
                int v = e.to();
                if (parent[v] == -2) {
                    parent[v] = u;
                    stack.push(v);
                }
            }
        }

        long[] gain = new long[n];
        int[] gainEnd = new int[n];
        Best best = new Best();

        for (int pos = count - 1; pos >= 0; pos--) {
            int u = order[pos];
            gainEnd[u] = u;

            boolean hasFirst = false;
            boolean hasSecond = false;
            long first = 0;
            long second = 0;
            int firstEnd = -1;
            int secondEnd = -1;

            for (Edge e : tree.get(u)) {
                int v = e.to();
                if (parent[v] != u) {
                    continue;
                }

                long contribution = Math.addExact(
                        e.weight(), gain[v]);
                int end = gain[v] > 0 ? gainEnd[v] : v;

                // Một nhánh u -> con, luôn ít nhất một cạnh.
                best.consider(contribution, u, end);

                if (!hasFirst || contribution > first
                        || (contribution == first && end < firstEnd)) {
                    second = first;
                    secondEnd = firstEnd;
                    hasSecond = hasFirst;
                    first = contribution;
                    firstEnd = end;
                    hasFirst = true;
                } else if (!hasSecond || contribution > second
                        || (contribution == second && end < secondEnd)) {
                    second = contribution;
                    secondEnd = end;
                    hasSecond = true;
                }
            }

            // Hai nhánh thuộc hai con DFS khác nhau.
            if (hasSecond) {
                best.consider(Math.addExact(first, second),
                              firstEnd, secondEnd);
            }

            // Gain được phép không đi cạnh nào, nên >= 0.
            if (hasFirst && first > 0) {
                gain[u] = first;
                gainEnd[u] = firstEnd;
            }
        }

        return Optional.of(new Diameter(
                best.length, best.from, best.to,
                pathBetween(tree, best.from, best.to)));
    }

    private static String describe(Diameter result) {
        return "length=" + result.length()
                + ", endpoints=(" + result.from()
                + "," + result.to() + ")"
                + ", path=" + result.path();
    }

    public static void main(String[] args) {
        long[][] weighted = {
                {0, 1, 3}, {1, 2, 2}, {1, 3, 4},
                {3, 4, 1}, {3, 5, 6}, {5, 6, 2},
                {5, 7, 0}, {7, 8, 5}
        };

        System.out.println("Weighted main: "
                + describe(twoSweepsNonnegative(9, weighted)));

        System.out.println("Zero-weight ties: "
                + describe(twoSweepsNonnegative(3,
                        new long[][] {{0, 1, 0}, {1, 2, 0}})));

        System.out.println("One vertex: "
                + describe(twoSweepsNonnegative(
                        1, new long[][] {})));

        long[][] counterexample = {
                {0, 1, -1}, {0, 2, -10},
                {2, 3, 5}, {2, 4, 5}
        };

        System.out.println("Signed DP: "
                + describe(signedDistinctDiameter(
                        5, counterexample).orElseThrow()));

        System.out.println("All-negative DP: "
                + describe(signedDistinctDiameter(
                        2, new long[][] {{0, 1, -5}}).orElseThrow()));

        System.out.println("Mixed-sign chain: "
                + describe(signedDistinctDiameter(
                        4, new long[][] {
                                {0, 1, 6}, {1, 2, -2}, {2, 3, 6}
                        }).orElseThrow()));

        System.out.println("Signed single vertex: "
                + (signedDistinctDiameter(
                        1, new long[][] {}).isEmpty() ? "none" : "error"));

        try {
            twoSweepsNonnegative(5, counterexample);
            System.out.println("Two-sweep negative rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Two-sweep negative rejected: true");
        }

        try {
            twoSweepsNonnegative(4, new long[][] {
                    {0, 1, 1}, {1, 2, 1}, {2, 0, 1}
            });
            System.out.println("Cycle rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Cycle rejected: true");
        }

        try {
            twoSweepsNonnegative(4, new long[][] {
                    {0, 1, 1}, {1, 2, 1}
            });
            System.out.println("Disconnected rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Disconnected rejected: true");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 TreeDiameterWeightAssumptionsDemo.java
java TreeDiameterWeightAssumptionsDemo
~~~

**Stdout mong đợi:**

~~~text
Weighted main: length=18, endpoints=(8,0), path=[8, 7, 5, 3, 1, 0]
Zero-weight ties: length=0, endpoints=(1,0), path=[1, 0]
One vertex: length=0, endpoints=(0,0), path=[0]
Signed DP: length=10, endpoints=(3,4), path=[3, 2, 4]
All-negative DP: length=-5, endpoints=(0,1), path=[0, 1]
Mixed-sign chain: length=10, endpoints=(0,3), path=[0, 1, 2, 3]
Signed single vertex: none
Two-sweep negative rejected: true
Cycle rejected: true
Disconnected rejected: true
~~~

### 11.1. Tại sao dùng hai API thay vì một hàm “tự đoán”?

Nếu input có cạnh âm, phương pháp hai lượt **không còn bảo đảm**. Việc tự bỏ qua cạnh âm hoặc áp dụng hai lượt rồi trả kết quả như chính xác là sai. Hai API tách riêng hợp đồng:
- twoSweepsNonnegative **từ chối** w<0, bảo đảm định lý áp dụng.
- signedDistinctDiameter giải mục tiêu khác có quy ước cụ thể là hai đầu khác nhau, xử lý trọng số âm.

Chương trình không phân loại âm/dương để lựa chọn thuật toán theo suy đoán; người gọi có thể chọn rõ bài toán và hợp đồng mình cần.

### 11.2. Kiểm tra cây thật sự

buildTree yêu cầu n≥1 và **đúng n−1 cạnh**; sau đó DSU từ chối cạnh tạo chu trình, self-loop hoặc cạnh song song. Vì có n−1 cạnh và không chu trình, kết quả là liên thông, tức cây. Code vẫn kiểm tra components==1.

Trên cây vô hướng, input chỉ chứa **một hàng cho mỗi cạnh**. Hàm tự thêm hai cung vào adjacency. Nếu truyền cả (u,v,w) và (v,u,w) như hai dòng độc lập, code xem đó là cạnh song song/chu trình và báo lỗi.

Với n=0, không có đỉnh xuất phát hợp lệ theo API. Nếu đề cần “đường kính rừng trống”, phải quy định trường hợp đó riêng; không tự coi n=0 là cây thông thường.

### 11.3. Stack thay vì đệ quy

Hai lượt traverse và signed DP đều dùng ArrayDeque<Integer> làm **stack tường minh**. Chúng không phụ thuộc độ sâu ngăn xếp gọi hàm của JVM nên phù hợp hơn cho cây đường dài; bộ nhớ có thể vẫn là O(n) theo số đỉnh.

### 11.4. Trọng số âm và gain

gain[u] có thể dừng tại u với tổng 0. Nhưng biến Best được cập nhật bằng **mọi contribution của cạnh thật**, kể cả âm, nên signedDistinctDiameter trả đúng −5 cho cây chỉ có một cạnh −5. Nó không tự biến −5 thành 0.

### 11.5. Truy vết và giới hạn tie-break

Path của hai lượt lấy từ parent của **lượt thứ hai**. Signed DP lưu hai đầu mút tối ưu rồi đi trên cây một lần để lấy đường duy nhất. Cả hai đều trả đúng một đường tối ưu, không liệt kê tất cả đường hòa.

Trong signed DP, tie-break theo ID nhỏ giữa các **ứng viên đã xét**, không phải lời hứa cặp đầu mút nhỏ nhất trong mọi cách đi qua các đoạn có contribution 0. Nếu đề yêu cầu thứ tự đầu mút từ điển tuyệt đối, phải thiết kế thêm dữ liệu đại diện các nhánh có tổng 0.

### 11.6. Tràn số

Các tổng đường đi và contribution dùng Math.addExact; nếu vượt miền long, hàm ném ArithmeticException. Hợp đồng chương trình là các tổng cần xét đều biểu diễn được bằng long. Với dữ liệu có trọng số cực lớn, có thể dùng BigInteger hoặc thiết kế miền số phù hợp; tuyệt đối không dùng overflow làm kết quả “xa nhất” giả.

## 12. Chứng minh tính đúng của signed tree DP

Có hai phần cần chứng minh.

### 12.1. Bất biến gain[u]

Sau khi đã xử lý các con của u, gain[u] là tổng lớn nhất của một đường đi bắt đầu ở u, đi xuống cây con u và **cho phép không đi cạnh nào**.

Chứng minh quy nạp:
- Với lá, không có nhánh đi xuống, cách dừng ở u có tổng 0.
- Với nút u, một đường đi xuống hoặc kết thúc ở u với tổng 0, hoặc đi qua đúng một cạnh (u,v) tới một con v rồi tiếp tục tối ưu trong cây con v. Theo giả thuyết quy nạp, phần tốt nhất sau cạnh đó là gain[v], nên lấy max của 0 và mọi w(u,v)+gain[v] chính xác.

### 12.2. Mọi đường hai đầu khác nhau được xét

Với đường đơn từ x tới y, lấy LCA u của x,y theo gốc. Nếu một đầu bằng u, đường là một nhánh từ u xuống con. Nếu hai đầu ở hai cây con khác nhau, đường gồm hai nhánh từ hai con **khác nhau** nối qua u.

Mỗi nhánh tốt nhất được tính bằng contribution(u,v); nếu có hai nhánh, tổng hai contribution lớn nhất từ hai con khác nhau tối ưu cho các đường có LCA u. Vì ta xét mọi đỉnh u, lời giải lớn nhất toàn cục chắc chắn được xem là ứng viên.

Code luôn xét đường **có ít nhất một cạnh**, do đó không chọn nhầm đường rỗng khi tất cả trọng số âm. Với n≥2, cây có ít nhất một cạnh, Best sẽ có ứng viên thật và trả tổng đúng.

**Kết luận:** tree DP O(n) trả được tổng trọng số lớn nhất trên đường đi giữa hai đỉnh khác nhau, không yêu cầu dấu trọng số.

## 13. Độ phức tạp và bộ nhớ

Với cây n đỉnh và n−1 cạnh:
- Tạo danh sách kề: O(n).
- DSU với path compression và union by size xác thực cây: O(nα(n)) thời gian khấu hao.
- Một lượt DFS theo stack: O(n).
- Hai lượt DFS và tìm argmax: O(n).
- Tạo hậu thứ tự và duyệt ngược để tính gain: O(n).
- Khôi phục đường cuối: O(n) trong trường hợp xấu nhất.

Vì vậy **cốt lõi hai lượt và signed DP đều O(n) thời gian, O(n) bộ nhớ** trên cây đã được xác thực. Nếu tính cả DSU ở bước kiểm tra đầu vào, có thể báo O(nα(n)) thời gian khấu hao.

Các mảng distance, parent, order, gain và gainEnd cùng adjacency/stack dùng O(n) bộ nhớ. Không cần min-heap Dijkstra, không cần O(n²) để thử mọi cặp trong lời giải tối ưu.

Tuy nhiên, **oracle kiểm thử** bằng duyệt mọi nguồn trên cây nhỏ cần O(n²) thời gian: đó là cách kiểm tra độc lập, không phải độ phức tạp chương trình chính.

## 14. Những lỗi thường gặp

1. **Dùng hai lượt chọn xa nhất trên cây có trọng số âm** mà vẫn tuyên bố tối ưu.
2. **Sửa giả thiết âm bằng cách chỉ loại nguồn khỏi argmax**; phản ví dụ 5 đỉnh vẫn sai.
3. **Không phân biệt số cạnh với tổng trọng số**, ví dụ đường có 5 cạnh nhưng tổng 18.
4. **Cứ thấy cây có trọng số thì dùng Dijkstra**, dù chỉ có một đường đơn và DFS O(n) đã đủ.
5. **Dùng công thức dist[v]=dist[u]+1 khi đề đo tổng trọng số**, làm đổi bài toán.
6. **Lấy đỉnh pop/dequeue cuối cùng làm xa nhất** trên cây trọng số không đồng nhất.
7. **Dùng thuật toán đường kính cây cho đồ thị có chu trình** mà không xác thực cấu trúc.
8. **Chỉ thấy n−1 cạnh thì cho là cây** mà không kiểm tra chu trình và liên thông.
9. **Không lưu parent của lượt duyệt thứ hai**, dẫn đến không khôi phục được đường từ a tới b.
10. **Nhầm parent của lượt đầu với lượt hai**, khiến path không tương ứng kết quả cuối.
11. **Coi trọng số 0 là thiếu cạnh**, làm sai khoảng cách và cấu trúc.
12. **Không mô tả tie-break**, sau đó unit test ép một bộ endpoint duy nhất dù nhiều nghiệm hòa.
13. **Cho rằng mọi cặp endpoint tối ưu phải là hai đầu có ID lớn nhất/nhỏ nhất**, điều này không xuất phát từ định nghĩa đường kính.
14. **Khởi tạo best của signed distinct bằng 0**, trả 0 sai khi tất cả cạnh âm.
15. **Dùng max gain[u] làm đường kính**, trong khi gain chỉ là đường đi xuống có thể rỗng.
16. **Không xét ứng viên đường một nhánh âm** ở signed DP, bỏ mất lời giải hợp lệ khi n≥2 toàn âm.
17. **Ghép hai nhánh thuộc cùng một con DFS**, làm đường đi không đơn.
18. **Không xét hai nhánh qua LCA**, bỏ mất đường đi dài nhất giữa hai cây con.
19. **Tự xóa mọi cạnh âm** trước khi tìm đường tốt nhất; ví dụ 6,−2,6 vẫn có đường tổng 10.
20. **Không tách n=1 theo hai quy ước**; signed distinct không có cặp đầu mút.
21. **Không xác thực đầu vào có phải cây** khi gặp self-loop, cạnh song song và thành phần cô lập.
22. **Dùng DFS đệ quy không kiểm soát độ sâu** trên một đường rất dài và bị StackOverflowError.
23. **Dùng int cho tổng trọng số lớn**, dẫn đến overflow; dùng long và kiểm tra.
24. **Không xác nhận các tổng không vượt long**, để phép cộng bọc vòng tạo “độ dài” giả.
25. **Chỉ so độ dài mà không kiểm tra path là đường đơn đúng cạnh thật**, làm lỗi khôi phục không bị phát hiện.
26. **Xem tập đầu mút thay đổi do tie là lỗi thuật toán**, dù tổng tối ưu vẫn đúng.

## 15. Cách kiểm thử có oracle độc lập

Trên cây nhỏ, cách đơn giản nhất để kiểm tra độ dài tối ưu là **duyệt mọi cặp đỉnh**:
1. Với mỗi nguồn s, duyệt cây một lần để tính tổng trọng số trên các đường đơn duy nhất từ s tới mọi v.
2. Nếu yêu cầu hai đầu khác nhau, lấy max trên **u<v**. Nếu cho phép hai đầu trùng nhau, lấy max trên **u≤v**.
3. So độ dài với kết quả **hai lượt** khi w≥0 hoặc **tree DP** khi trọng số có thể âm.
4. Kiểm tra path trả về đi đúng cạnh thật, không lặp đỉnh, đầu/cuối khớp và tổng trọng số đúng length.

Oracle tốn O(n²) cho n nguồn, mỗi lần duyệt O(n), nhưng hoàn toàn phù hợp để kiểm tra n nhỏ và **không phụ thuộc cách chọn hai nhánh của DP**.

Bộ dữ liệu nên có:
- Cây 9 đỉnh trọng số không âm với một cạnh 0, đường kính **18**.
- Cây 3 đỉnh mọi trọng số 0, kết quả **0** với hai đầu khác nhau.
- Một đỉnh, không cạnh: hai lượt=0, signed distinct=none.
- Phản ví dụ trọng số −1,−10,+5,+5: signed distinct=**10**, hai lượt không dùng.
- Hai đỉnh với một cạnh −5: signed distinct=**−5**.
- Chuỗi [6,−2,6]: signed distinct=**10**.
- Cây sao với các trọng số dương/âm xen kẽ.
- Cây đường dài để kiểm tra bộ nhớ stack và hiệu năng.
- Đồ thị có self-loop hoặc chu trình: bị từ chối.
- Rừng nhiều thành phần hoặc thiếu cạnh: bị từ chối.
- Tổng quá giới hạn long: phát hiện lỗi số học.

### Kiểm thử ngẫu nhiên trên cây nhỏ

Sinh cây bằng cách cho mỗi đỉnh v>0 chọn một cha p trong [0,v), rồi:
- Gán w ngẫu nhiên từ 0..k, kiểm tra hai lượt bằng oracle mọi cặp.
- Gán w ngẫu nhiên từ −k..k, kiểm tra signed DP bằng oracle mọi cặp **u<v**.

Nếu chỉ so đoạn đầu ra path, có thể kết luận nhầm lỗi vì nhiều cặp đạt cùng đường kính. Hãy so **length** trước, rồi kiểm tra tính hợp lệ của path riêng.

### Bất biến về đường đi

Với Diameter(length,from,to,path):
- Phần tử đầu của path bằng from, phần tử cuối bằng to.
- Các đỉnh xuất hiện không lặp trên đường đơn.
- Mọi cặp liên tiếp là một cạnh của input.
- Tổng trọng số trên path bằng length.
- Với hai lượt n≥2, from≠to.
- Với signedDistinctDiameter thành công, path có **ít nhất hai đỉnh**.
- Với n=1, twoSweepsNonnegative trả length=0/path=[0], signed distinct trả Optional.empty().

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Hai lượt tìm đường kính cây đúng dưới giả thiết trọng số nào?

**Đáp án:** Cây vô hướng hợp lệ, mọi cạnh có trọng số **không âm**. Trường hợp không trọng số là tất cả cạnh dài 1.

**Câu 2.** Trên cây có trọng số, vì sao dùng DFS cũng tính được tổng tới mọi đỉnh?

**Đáp án:** Vì giữa hai đỉnh chỉ có **một đường đi đơn**, nên cộng trọng số theo cha–con đủ để tính tổng; không cần tìm giữa nhiều đường.

**Câu 3.** Nếu đề hỏi số cạnh nhưng input có trọng số, phải làm gì?

**Đáp án:** Bỏ trọng số khỏi đại lượng đo, xem mỗi cạnh dài 1. Không dùng tổng w khi đề đo **số cạnh**.

**Câu 4.** Vì sao trọng số âm phá định lý đầu mút xa nhất?

**Đáp án:** Một nhánh nối tới vùng có đường tốt có thể bị cạnh âm lớn làm xa nguồn trở thành gần theo tổng, khiến đỉnh xa nhất từ nguồn nằm nơi khác không phải đầu đường kính.

**Câu 5.** Với phản ví dụ 5 đỉnh, tổng đường 3→2→4 là bao nhiêu?

**Đáp án:** 5+5=**10**. Hai lượt từ 0 (loại nguồn khi chọn xa nhất) trả −1, nên sai.

**Câu 6.** Cây hai đỉnh với cạnh −5 có đáp án gì?

**Đáp án:** Với hai đầu khác nhau, −5. Nếu cho phép u=v và đường 0 cạnh, 0.

**Câu 7.** Trạng thái gain[u] của signed DP là gì?

**Đáp án:** Tổng lớn nhất của một đường đi từ u xuống cây con, được phép dừng tại u: max(0,max_child(w+gain[child])).

**Câu 8.** Vì sao gain[u] không thay thế trực tiếp đáp án signed distinct?

**Đáp án:** Gain có thể là đường 0 cạnh/tổng 0, còn đề distinct yêu cầu một cạnh thật và có thể có đáp án âm.

**Câu 9.** Một đường tốt qua u có thể dùng bao nhiêu cây con trực tiếp?

**Đáp án:** Tối đa **hai** cây con khác nhau; một đường đơn có hai nhánh đi qua LCA u, hoặc một nhánh khi một đầu là u.

**Câu 10.** Trên cây trọng số không âm n=9 của ví dụ, kết quả là 5 hay 18?

**Đáp án:** Nếu đo **số cạnh** trên đường 0–8 thì 5; nếu đo **tổng trọng số** thì 18.

**Câu 11.** Có thể kết luận đồ thị là cây chỉ vì m=n−1 không?

**Đáp án:** Chưa. Cần kiểm tra không chu trình và liên thông. Một chu trình ở một phần và đỉnh cô lập ở phần khác vẫn có thể khiến tổng m=n−1.

**Câu 12.** Độ phức tạp thuật toán hai lượt và signed DP?

**Đáp án:** O(n) thời gian, O(n) bộ nhớ trên cây đã có adjacency. Bước xác thực DSU thêm O(nα(n)) khấu hao nếu tính cả kiểm tra.

**Câu 13.** Cạnh trọng số 0 có hợp lệ với hai lượt không?

**Đáp án:** Có. Điều kiện là **w≥0**, không phải w>0. Khi mọi w=0, đường kính có độ dài 0.

**Câu 14.** Đường đi tối ưu signed có thể chứa cạnh âm không?

**Đáp án:** Có. Chuỗi 6,−2,6 có đường nối hai đầu tổng 10 lớn hơn một cạnh +6, nên đoạn âm vẫn thuộc đường tối ưu.

**Ghi nhớ:** Trên **cây không trọng số hoặc cây có trọng số không âm**, đường kính tìm được bằng **hai lượt duyệt O(n)** và truy vết qua parent lượt hai. Với **cạnh âm**, tổng trên đường cây vẫn tính đúng, nhưng chọn xa nhất hai lần không còn chứng minh được tối ưu. Khi cần đường đi có tổng lớn nhất giữa hai đỉnh khác nhau, dùng **tree DP với gain[u] và tối đa hai nhánh khác nhau**, không quên quy ước đường đi 0 cạnh và kiểm tra đầu vào thật sự là cây.
