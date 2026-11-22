# Quy hoạch động trên đồ thị có hướng không chu trình

**Quy hoạch động trên đồ thị có hướng không chu trình** (*dynamic programming on a directed acyclic graph – DAG DP*) là kỹ thuật tính kết quả ở mỗi đỉnh dựa trên kết quả của các đỉnh tiền nhiệm, theo một thứ tự bảo đảm **mọi dữ liệu cần thiết đã có trước khi xử lý đỉnh hiện tại**. DAG là trường hợp đặc biệt thuận lợi: vì không có chu trình có hướng, ta luôn tìm được **thứ tự tô-pô** (*topological order*) để tính các trạng thái chỉ trong một lượt qua các đỉnh và cạnh.

Nhiều bài toán có vẻ khác nhau thực chất dùng chung cơ chế này: **đếm đường đi**, **đường đi ngắn nhất có trọng số**, **đường đi dài nhất**, **đường găng của dự án**, hay **tối ưu chi phí theo các bước phụ thuộc**. Điểm khác nhau chủ yếu nằm ở **ý nghĩa trạng thái**, **giá trị khởi tạo** và **phép gộp khi chuyển trạng thái**.

Bài học tập trung vào bốn câu hỏi: quan hệ phụ thuộc trên DAG được biểu diễn như thế nào; vì sao phải xử lý theo thứ tự tô-pô; cách viết truy hồi đúng cho từng bài toán; và làm thế nào nhận diện đỉnh không tới được, chu trình, trọng số âm và lỗi tràn số khi triển khai bằng **Java 17+**.

## 1. Đồ thị DAG và ý nghĩa của quan hệ phụ thuộc

Cho một đồ thị có hướng \(G=(V,E)\), trong đó cạnh \(u\to v\) biểu thị một quan hệ có hướng từ đỉnh u tới đỉnh v. **DAG** (*Directed Acyclic Graph*) là đồ thị **không tồn tại chu trình có hướng**: không có đường đi theo chiều cạnh xuất phát từ một đỉnh rồi quay lại chính đỉnh đó bằng ít nhất một cạnh.

Ví dụ các cạnh:

~~~text
0 -> 1
0 -> 2
1 -> 3
2 -> 3
1 -> 4
3 -> 4
~~~

lập thành DAG. Có thể xử lý các đỉnh theo thứ tự `0,1,2,3,4` hoặc `0,2,1,3,4`. Cả hai đều đảm bảo với mọi cạnh `u -> v`, u xuất hiện **trước** v.

Ngược lại:

~~~text
A -> B -> C -> A
~~~

là chu trình có hướng; không thể tìm một thứ tự tuyến tính vừa đặt A trước B, B trước C, lại đặt C trước A. Vì vậy không có thứ tự tô-pô cho đồ thị trên.

### Vì sao quan hệ phụ thuộc dẫn tới DP?

Giả sử một giá trị \(dp[v]\) phải được tính từ các giá trị \(dp[u]\) trên những cạnh \(u\to v\):

\[
dp[v]=F_v\bigl(\{dp[u]\mid u\to v\}\bigr).
\]

Các đỉnh u là **tiền nhiệm** (*predecessors*) của v. Nếu tính v trước khi tất cả những u liên quan đã sẵn sàng, ta có thể bỏ sót đóng góp của một số đường đi. Thứ tự tô-pô giải quyết điều này bằng cách đặt **mọi tiền nhiệm trước đỉnh sử dụng kết quả**.

**Lưu ý:** Không phải mọi cạnh của một đồ thị đều tự động có nghĩa là công thức phụ thuộc theo hướng đó. Cần đọc đặc tả để xác định chiều chuyển trạng thái. Ví dụ nếu một bài toán tính kết quả từ đích ngược về nguồn, ta có thể cần duyệt **thứ tự tô-pô đảo ngược**.

## 2. Thứ tự tô-pô: lịch tính toán hợp lệ

Một thứ tự tô-pô là danh sách tất cả đỉnh:

\[
v_1,v_2,\ldots,v_{|V|}
\]

sao cho với mọi cạnh \(u\to v\), u nằm trước v trong danh sách.

Tính chất quan trọng:

- **DAG luôn có ít nhất một thứ tự tô-pô.**
- Thứ tự tô-pô **có thể không duy nhất**; những đỉnh không có ràng buộc thứ tự trực tiếp hoặc gián tiếp có thể đổi vị trí.
- **Số hiệu đỉnh không phải thứ tự tô-pô.** Ví dụ với cạnh `5 -> 2`, đỉnh 5 bắt buộc phải đứng trước 2 dù số 5 lớn hơn 2.
- Đỉnh **không tới được từ nguồn truy vấn** vẫn có thể xuất hiện trong thứ tự tô-pô của toàn đồ thị. Ta phải xử lý nó an toàn thay vì giả sử mọi đỉnh đều có đường đi từ nguồn.

### Thuật toán Kahn để tạo thứ tự tô-pô

Kahn dùng **bậc vào** (*indegree*) và một hàng đợi.

1. Tính `indegree[v]`: số cạnh có hướng đi vào v.
2. Đưa tất cả đỉnh có indegree bằng 0 vào hàng đợi.
3. Lấy một đỉnh u ra và đưa vào danh sách tô-pô.
4. Với mỗi cạnh \(u\to v\), giảm `indegree[v]` một đơn vị. Khi nó bằng 0, đưa v vào hàng đợi.
5. Lặp đến khi hàng đợi rỗng.
6. Nếu số đỉnh đã lấy ra **nhỏ hơn \(|V|\)**, còn tồn tại chu trình trong đồ thị; không có thứ tự tô-pô cho toàn đồ thị.

Mã giả:

~~~text
topologicalOrder(graph):
    indegree[v] = số cạnh đi vào v cho mỗi đỉnh v
    ready = hàng đợi các v có indegree[v] = 0
    order = danh sách rỗng

    while ready không rỗng:
        u = ready.removeFirst()
        order.append(u)

        for mỗi cạnh u -> v:
            indegree[v]--
            if indegree[v] == 0:
                ready.addLast(v)

    if order.size() != số đỉnh:
        báo lỗi: đồ thị có chu trình

    return order
~~~

Đối với danh sách kề, Kahn chạy trong **\(O(V+E)\)** thời gian: mỗi đỉnh vào/ra hàng đợi một lần, mỗi cạnh làm giảm indegree đúng một lần. Các biến indegree, hàng đợi và danh sách thứ tự chiếm \(O(V)\) bộ nhớ phụ, chưa kể bộ nhớ danh sách kề.

**Tính đúng của Kahn:** Một đỉnh chỉ được đưa vào hàng đợi khi tất cả cạnh đi vào nó đã bị loại trong quá trình lấy các đỉnh trước đó ra. Vì vậy, khi đưa v vào `order`, tất cả tiền nhiệm u của v đã xuất hiện. Nếu còn đỉnh chưa xử lý mà không còn đỉnh indegree=0, phần đồ thị còn lại phải chứa chu trình có hướng.

### Cách khác: DFS postorder

Có thể dùng **DFS** với ba trạng thái `UNVISITED`, `VISITING`, `DONE`; khi hoàn tất duyệt tất cả các hậu duệ từ một đỉnh, đẩy đỉnh đó vào danh sách hậu thứ tự. **Đảo ngược danh sách hậu thứ tự** tạo một thứ tự tô-pô nếu không tìm thấy cạnh dẫn tới một đỉnh đang `VISITING`. DFS cũng có thời gian \(O(V+E)\), nhưng cài đệ quy trong Java có thể gặp `StackOverflowError` trên DAG rất sâu. Ví dụ chạy được phía dưới dùng Kahn với `ArrayDeque`.

## 3. Ba bài toán DP trên cùng một DAG

Đặt s là **đỉnh nguồn** cho truy vấn. Với cạnh \(u\to v\) có trọng số \(w(u,v)\), ba bài toán sau có thể giải sau khi có thứ tự tô-pô.

### 3.1. Đếm số đường đi từ nguồn

Định nghĩa:

\[
ways[v]=\text{số đường đi có hướng từ }s\text{ tới }v.
\]

Ta tính **mỗi cạnh như một lựa chọn chuyển tiếp riêng**. Khi đồ thị có các cạnh song song, các đường đi phân biệt bằng cạnh được tính là khác nhau; nếu đề muốn đếm theo dãy đỉnh thì phải quy định cách xử lý cạnh song song.

Trạng thái cơ sở:

\[
ways[s]=1,\qquad ways[v]=0\quad (v\ne s).
\]

Giá trị 1 ở nguồn đếm **đường đi độ dài 0** từ s tới chính nó. Với mỗi cạnh \(u\to v\), khi duyệt u theo thứ tự tô-pô:

\[
\boxed{ways[v]\mathrel{+}=ways[u].}
\]

Mọi đường đi tới v (khác đường đi độ dài 0 ở chính nguồn) đều kết thúc bằng một cạnh từ tiền nhiệm u. Mỗi đường đi tới u có thể nối thêm cạnh u→v để thành một đường đi tới v. Vì mỗi cạnh được duyệt một lần, đóng góp không bị bỏ sót.

**Không cần đếm đường đi bằng cách liệt kê tất cả đường đi.** Số đường đi trên một DAG có thể **tăng theo hàm mũ** của số tầng, nhưng mỗi cạnh chỉ cần một phép cộng để cập nhật số lượng. Tuy nhiên chính **giá trị ways[v]** có thể rất lớn, vượt kiểu `long`.

### 3.2. Đường đi ngắn nhất trên DAG có trọng số

Định nghĩa:

\[
dist_{\min}[v]=\text{tổng trọng số nhỏ nhất của một đường đi từ }s\text{ tới }v.
\]

Trạng thái cơ sở: `distMin[s]=0`; đỉnh không tới được chưa có khoảng cách hợp lệ.

Với mỗi cạnh \(u\to v\), nếu u tới được từ s, xét:

\[
candidate=dist_{\min}[u]+w(u,v),
\]

và cập nhật:

\[
\boxed{dist_{\min}[v]\leftarrow
\min\bigl(dist_{\min}[v],candidate\bigr).}
\]

Nếu v chưa từng được tới, ứng viên đầu tiên tạo giá trị ban đầu cho nó. Nếu đã tới, chỉ thay khi ứng viên nhỏ hơn.

Điểm đặc biệt: **trọng số âm vẫn được phép** khi tính đường đi ngắn nhất trên **DAG**. Vì không có chu trình có hướng, không tồn tại chu trình âm mà ta có thể lặp lại vô hạn để giảm chi phí. Khác với Dijkstra chuẩn (cần điều kiện trọng số không âm để bảo đảm tính đúng), DP theo thứ tự tô-pô vẫn đúng cho cạnh trọng số âm.

### 3.3. Đường đi dài nhất trên DAG có trọng số

Định nghĩa:

\[
dist_{\max}[v]=\text{tổng trọng số lớn nhất của một đường đi từ }s\text{ tới }v.
\]

Trạng thái cơ sở tương tự: `distMax[s]=0`; chưa thể coi các đỉnh không tới được có giá trị 0.

Với mỗi cạnh \(u\to v\) từ một u tới được:

\[
\boxed{dist_{\max}[v]\leftarrow
\max\bigl(dist_{\max}[v],dist_{\max}[u]+w(u,v)\bigr).}
\]

Công thức giống đường ngắn nhất nhưng thay **min** bằng **max**.

**Không được khởi tạo toàn bộ distMax bằng 0 và coi đó là giá trị hợp lệ** nếu có thể có đường đi âm. Ví dụ chỉ có cạnh s→v trọng số -5: đường đi duy nhất tới v có giá trị -5, không phải 0. Dùng cờ `reachable[v]` hoặc một sentinel âm vô cùng an toàn để phân biệt “chưa tới được” với “đường đi có tổng bằng 0”.

Trên DAG, đường đi dài nhất từ một nguồn xác định có thể tính trong \(O(V+E)\), kể cả với trọng số âm. Trên đồ thị có chu trình tổng quát, bài toán đường đi đơn dài nhất khó hơn nhiều; **không được tự áp dụng kết quả DAG cho đồ thị bất kỳ**.

## 4. Hai cách viết chuyển trạng thái

### Cách 1: Kéo thông tin từ các tiền nhiệm (*pull*)

Khi tới v, mọi u có cạnh u→v đã tính xong:

\[
ways[v]=\sum_{u\to v}ways[u],
\]

\[
dist_{\min}[v]=\min_{u\to v,\ reachable[u]}
(dist_{\min}[u]+w(u,v)).
\]

Đối với đường dài nhất, dùng max. Cách pull thuận tiện nếu ta có **danh sách cạnh đi vào** mỗi v.

### Cách 2: Đẩy thông tin theo cạnh đi ra (*push*)

Khi lấy u theo thứ tự tô-pô, coi giá trị của u đã hoàn tất; với mỗi cạnh u→v, đóng góp từ u vào trạng thái đang xây của v:

~~~text
for u trong topologicalOrder:
    if u không tới được từ s:
        continue

    for cạnh (u -> v, weight):
        ways[v] += ways[u]
        shortest[v] = min(shortest[v], shortest[u] + weight)
        longest[v]  = max(longest[v], longest[u] + weight)
~~~

Đây là cách dùng trong mã Java. Một đỉnh v có thể được **cập nhật nhiều lần từ các tiền nhiệm** khi chưa tới lượt v, nhưng chỉ được **phát tán kết quả sang các đỉnh sau khi đã đến lượt v** trong thứ tự tô-pô. Không được lấy giá trị tạm thời của v đem xử lý các cạnh đi ra sớm hơn, vì v có thể còn một tiền nhiệm chưa đóng góp.

Trong cả hai cách, điều kiện đúng giống nhau: **khi một đỉnh được coi là hoàn tất, mọi tiền nhiệm của nó đã đóng góp đầy đủ**.

## 5. Bài toán ví dụ: một DAG có cạnh âm và đỉnh không tới được

Xét 7 đỉnh `0,1,2,3,4,5,6`, với các cạnh có trọng số:

| Cạnh | Trọng số | Ghi chú |
|---|---:|---|
| 0 → 1 | 2 | Nhánh đầu |
| 0 → 2 | 4 | Nhánh thứ hai |
| 1 → 3 | 3 | Qua đỉnh 1 |
| 2 → 3 | **-2** | Trọng số âm hợp lệ trên DAG |
| 1 → 4 | 6 | Đi thẳng từ 1 tới 4 |
| 3 → 4 | 2 | Qua đỉnh 3 |
| 4 → 5 | 1 | Đường tới đích 5 |
| 2 → 5 | 10 | Nhánh đi thẳng từ 2 tới 5 |

Đỉnh **6 cô lập**, không có cạnh vào/ra. Nguồn là **0**; đích quan tâm là **5**.

Sơ đồ quan hệ:

~~~text
          (2)        (3)
     0 --------> 1 --------> 3
     |             \          ^  \
 (4) |              \ (6)     |   \ (2)
     v               v       |    v
     2 ------------> 4 <-----+    4
      \    (-2)  /             |
       \------->3 ------------/
        \
         \---------> 5
                (10)

     4 ---------> 5  (1)       6 (cô lập)
~~~

**Lưu ý:** sơ đồ chữ ở trên chỉ gợi ý mối liên hệ; **bảng cạnh mới là dữ liệu chính xác**. Có thể vẽ gọn đồ thị bằng Mermaid để tránh nhầm:

~~~mermaid
flowchart LR
  A["0"] -->|"2"| B["1"]
  A -->|"4"| C["2"]
  B -->|"3"| D["3"]
  C -->|"-2"| D
  B -->|"6"| E["4"]
  D -->|"2"| E
  E -->|"1"| F["5"]
  C -->|"10"| F
  G["6: cô lập"]
~~~

Với Kahn, nếu bắt đầu các đỉnh indegree=0 theo **số hiệu tăng**, rồi xét cạnh theo đúng thứ tự bảng, một thứ tự tô-pô nhận được là:

~~~text
[0, 6, 1, 2, 3, 4, 5]
~~~

Đỉnh 6 có thể xuất hiện ngay sau 0 vì nó độc lập; điều đó **không** có nghĩa 0 đi tới được 6. Một thứ tự tô-pô khác cũng có thể đúng. Thuật toán DP chỉ lan truyền từ những đỉnh **reachable** từ s.

### Mô phỏng các chuyển trạng thái

Bắt đầu `reachable[0]=true`, `ways[0]=1`, `shortest[0]=longest[0]=0`. Các đỉnh khác chưa tới được và có ways=0.

| Đỉnh vừa xử lý | Cập nhật quan trọng | Kết quả trung gian |
|---|---|---|
| **0** | 0→1 (2), 0→2 (4) | ways[1]=1, shortest[1]=2; ways[2]=1, shortest[2]=4 |
| **6** | Không tới được từ 0; bỏ qua | ways[6]=0, reachable[6]=false |
| **1** | 1→3 (3), 1→4 (6) | ways[3]=1, shortest[3]=5; ways[4]=1, shortest[4]=8 |
| **2** | 2→3 (-2), 2→5 (10) | ways[3]=2, shortest[3]=2; ways[5]=1, shortest[5]=14 |
| **3** | 3→4 (2) | ways[4]=3, shortest[4]=4 |
| **4** | 4→5 (1) | ways[5]=4, shortest[5]=5 |
| **5** | Đỉnh đích, không có cạnh ra | Kết thúc |

Các giá trị cuối:

| Đỉnh v | Tới được từ 0? | ways[v] | Đường ngắn nhất từ 0 | Đường dài nhất từ 0 |
|---:|---|---:|---:|---:|
| 0 | Có | 1 | 0 | 0 |
| 1 | Có | 1 | 2 | 2 |
| 2 | Có | 1 | 4 | 4 |
| 3 | Có | 2 | **2** | **5** |
| 4 | Có | 3 | **4** | **8** |
| 5 | Có | **4** | **5** | **14** |
| 6 | Không | 0 | Không xác định | Không xác định |

Đường đi **ngắn nhất** từ 0 tới 5 là:

\[
0\to2\to3\to4\to5,\qquad 4+(-2)+2+1=\boxed{5}.
\]

Đường đi **dài nhất** từ 0 tới 5 là:

\[
0\to2\to5,\qquad 4+10=\boxed{14}.
\]

Có **4** đường đi khác nhau từ 0 tới 5:

1. \(0\to1\to3\to4\to5\).
2. \(0\to1\to4\to5\).
3. \(0\to2\to3\to4\to5\).
4. \(0\to2\to5\).

**Phân biệt:** `ways[5]=4` là tổng số **mọi đường đi**, không phải số đường đi ngắn nhất. Muốn đếm **các đường đi ngắn nhất**, ta phải dùng thêm một trạng thái đếm kết hợp với thao tác chọn min: khi tìm được khoảng cách tốt hơn thì thay số cách, khi bằng khoảng cách tốt nhất thì cộng số cách. Không được nhầm hai đại lượng này.

## 6. Chứng minh DP trên DAG luôn tính đúng

Chứng minh dùng **quy nạp theo thứ tự tô-pô** \(v_1,\ldots,v_{|V|}\).

### 6.1. Cơ sở

Trước khi xử lý đỉnh nào, nguồn s có:

\[
ways[s]=1,\quad dist_{\min}[s]=dist_{\max}[s]=0.
\]

Các đỉnh khác chưa có đường đi từ s được phát hiện, nên `reachable=false` và `ways=0`. Mọi kết quả ban đầu phù hợp với đường đi rỗng tại nguồn và việc chưa lan truyền.

### 6.2. Bước quy nạp

Giả sử mọi đỉnh xuất hiện trước v trong thứ tự tô-pô đều đã hoàn tất đúng.

Mỗi đường đi khác rỗng từ s tới v phải kết thúc bằng một cạnh \(u\to v\), trong đó u nằm **trước v** theo thứ tự tô-pô. Vì kết quả ở u đã đúng:

- Mỗi đường đi tới u được kéo dài bằng cạnh u→v và góp đúng một vào `ways[v]`. Cộng qua các cạnh vào v đếm đủ các đường đi tới v.
- Mỗi đường đi tới v có tổng trọng số bằng tổng của một đường đi tới u cộng \(w(u,v)\). Lấy min các ứng viên từ mọi tiền nhiệm tới được cho ra **đường ngắn nhất**.
- Lấy max các ứng viên tương tự cho ra **đường dài nhất**.

Các cập nhật từ mọi u đã diễn ra **trước khi bắt đầu phát tán kết quả từ v**, nên khi tới lượt v, các trạng thái của v là chính xác.

### 6.3. Kết luận và điều kiện không chu trình

Theo quy nạp, mọi đỉnh có trạng thái đúng sau khi hoàn tất vòng lặp; câu trả lời tại đích là đúng. Mỗi cạnh chỉ dùng một lần, không cần duyệt lặp đến khi ổn định.

Nếu đồ thị có **chu trình có hướng**, không tồn tại thứ tự tô-pô cho toàn đồ thị. Việc cố tính DP một lượt theo số hiệu đỉnh có thể dùng trạng thái chưa hoàn tất; với bài toán đếm **walks** qua chu trình, số cách có thể không hữu hạn. Vì vậy **phải kiểm tra điều kiện DAG** hoặc dùng thuật toán khác phù hợp với đặc tả trên đồ thị có chu trình.

## 7. Java 17+: đếm, ngắn nhất, dài nhất và truy vết

Chương trình dưới đây là một ví dụ Java 17 **hoàn chỉnh, biên dịch/chạy được**. Nó thực hiện:

- Xây danh sách kề từ danh sách cạnh có hướng có trọng số.
- Sinh thứ tự tô-pô bằng **Kahn**, phát hiện chu trình ở bất kỳ thành phần nào của đồ thị.
- Tính đồng thời **số đường đi**, **tổng trọng số nhỏ nhất**, **tổng trọng số lớn nhất** từ một nguồn.
- Lưu **parentShortest[v]** để khôi phục một đường đi ngắn nhất khi có thể tới đích.
- Dùng `reachable` để phân biệt **đỉnh chưa tới được** và **đường đi có tổng bằng 0 hoặc âm**.
- Dùng `Math.addExact` cho các phép cộng `long` để **phát hiện tràn số** thay vì im lặng quay vòng.

**Quy ước:** mỗi cạnh trong danh sách là một cạnh riêng; nếu có cạnh song song, khi đếm `ways` chúng được xem như lựa chọn khác nhau. Các nhãn đỉnh là số nguyên từ 0 tới `vertices-1`.

Lưu thành tệp **DagDpDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class DagDpDemo {
    record Arc(int from, int to, long weight) {}

    record Analysis(
        List<Integer> topo,
        long[] shortest,
        long[] longest,
        long[] ways,
        boolean[] reachable,
        int[] parentShortest
    ) {}

    static Analysis analyze(int vertices, List<Arc> edges, int source) {
        Objects.requireNonNull(edges, "edges");
        if (vertices <= 0 || source < 0 || source >= vertices) {
            throw new IllegalArgumentException("invalid vertices/source");
        }

        List<List<Arc>> outgoing = new ArrayList<>();
        for (int v = 0; v < vertices; v++) {
            outgoing.add(new ArrayList<>());
        }

        int[] indegree = new int[vertices];
        for (Arc arc : edges) {
            Objects.requireNonNull(arc, "arc");
            if (arc.from() < 0 || arc.from() >= vertices
                    || arc.to() < 0 || arc.to() >= vertices) {
                throw new IllegalArgumentException("invalid edge endpoint");
            }
            outgoing.get(arc.from()).add(arc);
            indegree[arc.to()]++;
        }

        // Kahn: every predecessor appears before its successor.
        ArrayDeque<Integer> ready = new ArrayDeque<>();
        for (int v = 0; v < vertices; v++) {
            if (indegree[v] == 0) {
                ready.addLast(v);
            }
        }

        List<Integer> topo = new ArrayList<>();
        while (!ready.isEmpty()) {
            int u = ready.removeFirst();
            topo.add(u);

            for (Arc arc : outgoing.get(u)) {
                int v = arc.to();
                if (--indegree[v] == 0) {
                    ready.addLast(v);
                }
            }
        }

        if (topo.size() != vertices) {
            throw new IllegalArgumentException("graph is not a DAG");
        }

        long[] shortest = new long[vertices];
        long[] longest = new long[vertices];
        long[] ways = new long[vertices];
        boolean[] reachable = new boolean[vertices];
        int[] parent = new int[vertices];
        Arrays.fill(parent, -1);

        reachable[source] = true;
        ways[source] = 1L;
        // shortest[source] and longest[source] are 0.

        for (int u : topo) {
            if (!reachable[u]) {
                continue;
            }

            for (Arc arc : outgoing.get(u)) {
                int v = arc.to();
                long candidateMin =
                    Math.addExact(shortest[u], arc.weight());
                long candidateMax =
                    Math.addExact(longest[u], arc.weight());

                boolean firstPathToV = !reachable[v];
                if (firstPathToV || candidateMin < shortest[v]) {
                    shortest[v] = candidateMin;
                    parent[v] = u;
                }
                if (firstPathToV || candidateMax > longest[v]) {
                    longest[v] = candidateMax;
                }

                reachable[v] = true;
                ways[v] = Math.addExact(ways[v], ways[u]);
            }
        }

        return new Analysis(
            List.copyOf(topo), shortest, longest, ways, reachable, parent
        );
    }

    static List<Integer> shortestPath(Analysis result, int target) {
        Objects.requireNonNull(result, "result");
        if (target < 0 || target >= result.reachable().length) {
            throw new IllegalArgumentException("invalid target");
        }
        if (!result.reachable()[target]) {
            return List.of();
        }

        List<Integer> backwards = new ArrayList<>();
        for (int v = target; v != -1; v = result.parentShortest()[v]) {
            backwards.add(v);
        }
        Collections.reverse(backwards);
        return backwards;
    }

    public static void main(String[] args) {
        List<Arc> edges = List.of(
            new Arc(0, 1, 2),
            new Arc(0, 2, 4),
            new Arc(1, 3, 3),
            new Arc(2, 3, -2),
            new Arc(1, 4, 6),
            new Arc(3, 4, 2),
            new Arc(4, 5, 1),
            new Arc(2, 5, 10)
        );

        Analysis result = analyze(7, edges, 0);
        System.out.println("Topological order: " + result.topo());
        System.out.println("Shortest 0 -> 5: " + result.shortest()[5]);
        System.out.println("Shortest path: " + shortestPath(result, 5));
        System.out.println("Longest 0 -> 5: " + result.longest()[5]);
        System.out.println("Number of paths 0 -> 5: " + result.ways()[5]);
        System.out.println("Vertex 6 reachable: " + result.reachable()[6]);
        System.out.println("Paths 0 -> 6: " + result.ways()[6]);

        try {
            analyze(2, List.of(
                new Arc(0, 1, 1),
                new Arc(1, 0, 1)
            ), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Cycle rejected: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac DagDpDemo.java
java DagDpDemo
~~~

**Stdout chính xác:**

~~~text
Topological order: [0, 6, 1, 2, 3, 4, 5]
Shortest 0 -> 5: 5
Shortest path: [0, 2, 3, 4, 5]
Longest 0 -> 5: 14
Number of paths 0 -> 5: 4
Vertex 6 reachable: false
Paths 0 -> 6: 0
Cycle rejected: graph is not a DAG
~~~

### Giải thích những lựa chọn kỹ thuật

**Phát hiện chu trình trên toàn bộ đồ thị.** Thuật toán Kahn chạy cả với các đỉnh không tới được từ nguồn. Nếu một thành phần không liên thông có chu trình, `topo.size()!=vertices` vẫn phát hiện và từ chối, đúng với hợp đồng đầu vào phải là DAG.

**Nguồn không nhất thiết có indegree bằng 0.** Một đỉnh nguồn cho truy vấn có thể có cạnh đi vào từ các đỉnh khác mà nguồn không thể đi tới. Ta vẫn khởi tạo `ways[source]=1` để đếm đường đi bắt đầu tại nguồn; các tiền nhiệm không tới được không đóng góp. Thứ tự tô-pô trên toàn đồ thị bảo đảm việc lan truyền đúng.

**Đỉnh không tới được không dùng khoảng cách mặc định.** Các mảng `shortest`, `longest` trong Java mặc định chứa 0; chỉ các chỉ số có `reachable[v]=true` mới có ý nghĩa khoảng cách. Nếu `reachable[v]=false`, giá trị 0 ở mảng khoảng cách **không phải một đường đi có chi phí 0**.

**Khi có nhiều đường ngắn nhất cùng chi phí**, mã chỉ cập nhật cha khi ứng viên **nhỏ hơn hẳn**. Vì vậy `shortestPath` trả **một đường đi ngắn nhất** bất kỳ theo thứ tự duyệt cạnh, không bảo đảm đường đi ít cạnh nhất hoặc thứ tự từ điển nhỏ nhất. Muốn quy tắc phá hòa khác phải bổ sung tiêu chí.

**Khi cạnh có trọng số âm**, `Math.addExact` cộng `long` với `long` và ném `ArithmeticException` nếu tràn. Việc dùng `long` không tự đảm bảo kết quả vô hạn chính xác; nếu bài toán có tổng đường đi hoặc số đường đi vượt miền `long`, cần `BigInteger` hoặc quy tắc modulo khi phù hợp với đặc tả.

**Bộ nhớ kết quả** chứa cả ba mảng DP và mảng `parent` để truy vết. Không nên ghi đè mảng `parentShortest` khi đang cập nhật đường dài nhất; đó là hai mục tiêu khác nhau. Nếu cần truy vết đường dài nhất, hãy lưu một `parentLongest` riêng và cập nhật chỉ khi có ứng viên max tốt hơn.

**Không nên đưa ra một sentinel số cố định thay cho reachability** mà quên phép cộng. Ví dụ `Long.MAX_VALUE + weight` có thể tràn, và khoảng cách thực bằng sentinel cũng gây nhập nhằng. Cờ `reachable` giúp làm rõ trạng thái có/không có đường đi.

## 8. Phân tích độ phức tạp

Đặt \(V=|V|\) là số đỉnh và \(E=|E|\) là số cạnh.

| Công đoạn | Thời gian | Bộ nhớ ngoài đầu vào |
|---|---:|---:|
| Dựng danh sách kề và indegree | \(O(V+E)\) | \(O(V+E)\) |
| Kahn: tạo thứ tự tô-pô | \(O(V+E)\) | \(O(V)\) cho indegree, queue, order |
| Khởi tạo các mảng DP | \(O(V)\) | \(O(V)\) |
| Duyệt topo, chuyển qua mỗi cạnh đúng một lần | \(O(V+E)\) | \(O(V)\) cho mảng DP và cha |
| Truy vết một đường tới đích | \(O(L)\) với L số đỉnh trên đường | \(O(L)\) cho danh sách đường đi |

Tổng thời gian:

\[
\boxed{O(V+E)}.
\]

Tổng bộ nhớ trong chương trình minh họa, bao gồm danh sách kề và kết quả:

\[
\boxed{O(V+E)}.
\]

Nếu danh sách kề đã được cung cấp và không cần lưu toàn bộ thứ tự tô-pô/kết quả riêng, chi phí **bổ sung** có thể chỉ là \(O(V)\) cho indegree, queue và các trạng thái, ngoài dữ liệu graph.

Đây là lợi thế đặc biệt của DAG: các bài toán đường đi có thể được giải bằng một lượt DP, không cần vòng lặp thư giãn cạnh nhiều lần để “hội tụ”. Tuy nhiên không nên tuyên bố DP trên DAG luôn \(O(V+E)\) cho **mọi loại trạng thái**: kết luận này đúng với những bài toán mà mỗi đỉnh/cạnh được xử lý O(1) công việc. Nếu mỗi trạng thái lưu một tập lớn, đa thức hoặc một phân phối dài, chi phí gộp có thể cao hơn.

### Số đường đi có thể rất lớn

Một DAG với nhiều lớp rẽ nhánh và hợp nhất có thể chứa **số đường đi tăng theo hàm mũ**, mặc dù chỉ có O(V+E) phép cộng để đếm. Với cách tính chính xác, giá trị kết quả có thể vượt `long`. Có thể:

- Dùng **BigInteger** nếu đề yêu cầu số nguyên chính xác không giới hạn.
- Dùng **modulo M** nếu đề chỉ yêu cầu phần dư; khi đó tính phép cộng mô-đun và xử lý an toàn tràn số theo kiểu dữ liệu.
- Dùng `Math.addExact` để phát hiện tràn khi đề yêu cầu kiểu long và không có quy tắc modulo.

Không được coi `long` đủ lớn cho mọi đồ thị DAG. Bộ nhớ/thời gian của `BigInteger` còn phụ thuộc số bit của kết quả.

## 9. Đường găng của công việc phụ thuộc là một DP trên DAG

Một ứng dụng rất gần với bài toán thực tế là **lập lịch công việc có quan hệ tiên quyết** (*critical path method* trong mô hình đơn giản).

Mỗi đỉnh v là một công việc có thời lượng \(duration[v]\ge0\); cạnh \(u\to v\) nghĩa là **u phải hoàn thành trước khi v có thể bắt đầu**. Giả sử:

- Không có giới hạn số nhân sự/máy móc, nên công việc độc lập có thể chạy song song.
- Không có thời gian chờ ngoài các quan hệ tiên quyết.
- Không ngắt một công việc giữa chừng.

Đặt:

\[
finish[v]=\text{thời điểm hoàn thành sớm nhất của công việc v}.
\]

Nếu v không có tiền nhiệm:

\[
finish[v]=duration[v].
\]

Nếu có tiền nhiệm:

\[
\boxed{finish[v]=duration[v]
+\max_{u\to v}finish[u].}
\]

Ta duyệt các công việc theo **thứ tự tô-pô**. Khi tới v, mọi `finish[u]` cần thiết đã được tính, nên có thể lấy max chính xác. Thời gian hoàn thành tối thiểu của **toàn bộ dự án** khi mọi việc đều phải xong là:

\[
\max_v finish[v].
\]

Một đường đi tạo ra giá trị lớn nhất này có thể được gọi là **đường găng** trong mô hình trên: các công việc dọc đường đó quyết định cận dưới thời gian hoàn thành dự án.

**Đừng nhầm với đường ngắn nhất trên đồ thị có trọng số cạnh.** Ở đây thời lượng nằm trên **đỉnh**, và kết quả phải cộng thời lượng công việc hiện tại. Có thể chuyển mô hình trọng số đỉnh sang cạnh hoặc viết trực tiếp công thức như trên, nhưng phải nhất quán về việc có tính công việc nguồn và công việc đích.

### Ví dụ công việc

Các công việc A, B, C, D có thời lượng:

| Việc | Thời lượng | Tiền nhiệm |
|---|---:|---|
| A | 3 | Không |
| B | 5 | Không |
| C | 4 | A và B |
| D | 2 | C |

Tính theo thứ tự A, B, C, D:

- `finish[A]=3`.
- `finish[B]=5`.
- `finish[C]=4+max(3,5)=9`.
- `finish[D]=2+9=11`.

Dự án cần tối thiểu **11** đơn vị thời gian nếu có đủ tài nguyên để chạy A/B song song. Đường găng là **B → C → D** với \(5+4+2=11\).

Nếu có giới hạn tài nguyên (chỉ một máy, số người hạn chế, chia ca, phòng chuyên dụng), việc tìm lịch tối ưu có thể phức tạp hơn; công thức DAG cơ bản **không tự giải** các ràng buộc nguồn lực đó.

## 10. Đếm đường đi ngắn nhất cần trạng thái khác đếm mọi đường đi

Một nhầm lẫn thường gặp là sau khi tính `shortest[v]`, xem luôn `ways[v]` của phần 3 là **số đường ngắn nhất**. Điều đó không đúng: `ways` đang cộng **mọi đường đi**, kể cả đường dài hơn.

Nếu yêu cầu đồng thời khoảng cách ngắn nhất và **số đường đạt khoảng cách đó**, đặt `cntMin[s]=1`. Khi duyệt một cạnh \(u\to v\) từ u tới được, tính `candidate=distMin[u]+w`.

- Nếu v **chưa tới được**, hoặc candidate **nhỏ hơn** giá trị distMin[v] hiện có: cập nhật `distMin[v]=candidate`, đồng thời **gán `cntMin[v]=cntMin[u]`**.
- Nếu candidate **bằng** distMin[v] hiện có: giữ nguyên khoảng cách, **cộng `cntMin[u]` vào `cntMin[v]`**.
- Nếu candidate **lớn hơn**: bỏ qua cho mục tiêu đếm đường ngắn nhất.

Ví dụ:

~~~text
0 -> 1 (1)
0 -> 2 (1)
1 -> 3 (2)
2 -> 3 (2)
~~~

Có hai đường 0→3 có cùng tổng trọng số **3**: `0→1→3` và `0→2→3`. Vì cả hai cho ứng viên bằng giá trị tốt nhất, `cntMin[3]=2`. Nếu một nhánh có tổng lớn hơn, nó vẫn được đếm trong **tổng số đường đi**, nhưng không được tính vào `cntMin`.

Với các cạnh trọng số âm trên DAG, quy tắc trên vẫn đúng vì không có chu trình có hướng và mọi tiền nhiệm đã hoàn tất khi chuyển tiếp. Nếu có nhiều cạnh song song, việc đếm theo cạnh hay theo dãy đỉnh cần được xác định riêng.

## 11. Khi nào cần duyệt tô-pô đảo ngược?

Không phải công thức nào trên DAG cũng phụ thuộc vào **tiền nhiệm**. Có bài yêu cầu kết quả của đường đi **từ v tới một đích t**, tức cần các trạng thái ở **hậu nhiệm** của v.

Ví dụ:

\[
bestToTarget[t]=0,
\]

\[
bestToTarget[u]
=\min_{u\to v}
(w(u,v)+bestToTarget[v])
\]

cho những u có đường đi tới t, còn u không thể tới t được đánh dấu không hợp lệ.

Để tính `bestToTarget[u]`, cần biết `bestToTarget[v]` của các đỉnh đi **sau u**. Vì vậy phải duyệt **thứ tự tô-pô ngược**: nếu topo là `[0,1,2,3]`, thì tính các trạng thái theo `[3,2,1,0]`.

Một cách khác là **đảo hướng mọi cạnh** rồi tính bài toán từ nguồn mới là t, nhưng khi đảo phải đồng thời diễn giải lại công thức và điều kiện reachability cho đúng. Việc “dùng topo ngược” thường đơn giản hơn khi chỉ muốn DP về một đích.

**Nguyên tắc chọn chiều duyệt:** nếu trạng thái ở v dùng **dp của các tiền nhiệm**, đi theo topo **xuôi**; nếu nó dùng **dp của các hậu nhiệm**, đi theo topo **ngược**.

## 12. Trạng thái không tới được và các trường hợp biên

Các thuật toán DAG thường dùng một giá trị cực lớn `INF` cho đường ngắn nhất và cực nhỏ `-INF` cho đường dài nhất. Cách này tiện nhưng dễ gặp các lỗi:

- Cộng `INF + weight` gây tràn hoặc tạo kết quả sai.
- Khoảng cách thật có thể bằng giá trị sentinel được chọn.
- Không kiểm tra `dist[u]` hợp lệ trước khi thư giãn các cạnh từ u.
- Dùng 0 để khởi tạo longest và vô tình bỏ mất những đường đi có tổng âm.

Mã Java chọn **`reachable[]`** để tách sự tồn tại đường đi khỏi giá trị trọng số. Vì vậy **đường tới được có tổng 0** và **đỉnh không tới được** là hai trạng thái khác nhau.

| Trường hợp | Cách xử lý đúng |
|---|---|
| Chỉ có một đỉnh và không có cạnh | Từ đỉnh đó tới chính nó: ways=1, khoảng cách min/max=0 |
| Đỉnh không tới được từ s | ways=0, reachable=false; không đọc min/max như khoảng cách hợp lệ |
| Đồ thị gồm nhiều thành phần | Thứ tự tô-pô vẫn chứa mọi đỉnh; DP từ s chỉ lan tới những đỉnh có đường đi từ s |
| Đỉnh nguồn có cạnh đi vào từ thành phần không tới được | Vẫn có thể chọn s làm nguồn truy vấn; các tiền nhiệm không tới được đóng góp 0 |
| Có nhiều cạnh song song u→v | Nếu đếm đường theo **cạnh**, mỗi cạnh là một lựa chọn riêng |
| Có cạnh trọng số âm | Ngắn nhất/dài nhất trên DAG vẫn có thể tính bằng topo, không cần Dijkstra |
| Mọi đường đi hợp lệ tới v đều âm | longest[v] có thể âm; không thay bằng 0 mặc định |
| Có nhiều đường ngắn nhất bằng nhau | parent có thể chọn một đường; muốn đếm tất cả phải có cntMin |
| Có chu trình ở bất cứ thành phần nào | Kahn xử lý ít hơn V đỉnh; báo đầu vào không phải DAG |
| Có cạnh tự nối v→v | Là chu trình; báo lỗi |
| Số đường đi vượt long | Dùng BigInteger/modulo hoặc báo overflow theo hợp đồng |
| Cộng trọng số vượt long | Phát hiện overflow; không dựa vào phép cộng `long` im lặng |

**Lưu ý về thuật toán DFS:** một đồ thị có chu trình vẫn có thể có đường đi đơn hữu hạn; điều đó không làm nó thành DAG. Bài toán đếm đường đi **đơn** hoặc đường đi dài nhất trên đồ thị có chu trình cần phương pháp và phân tích khác. Không nên áp dụng công thức topo khi không có topo.

## 13. Lỗi thường gặp

1. **Duyệt các đỉnh theo số hiệu 0,1,2,... và coi đó là topo:** sai nếu có cạnh từ số lớn tới số nhỏ.
2. **Không xác minh đồ thị không chu trình:** tính một lượt có thể đọc trạng thái chưa hoàn tất hoặc bỏ sót đóng góp.
3. **Chỉ topo trên phần tới được nhưng vẫn khẳng định kiểm tra DAG toàn đồ thị:** có thể bỏ sót chu trình ở thành phần khác. Nếu hợp đồng yêu cầu DAG toàn đồ thị, nên kiểm tra toàn bộ.
4. **Khởi tạo `ways[v]=1` cho mọi đỉnh:** điều đó đếm đường đi từ chính từng đỉnh, không phải chỉ từ nguồn s; cần `ways[s]=1` và những đỉnh khác bằng 0.
5. **Nhầm `ways[s]=0`:** bỏ mất đường đi độ dài 0, khiến mọi đóng góp từ nguồn có thể thành 0.
6. **Cộng số cách từ đỉnh chưa tới được:** phải giữ `ways[u]=0` và không xử lý khoảng cách không hợp lệ.
7. **Khởi tạo đường dài nhất của mọi đỉnh bằng 0:** làm sai khi những đường đi hợp lệ có tổng âm.
8. **Đặt `INF` nhưng không bảo vệ phép cộng với INF:** có thể tràn số hoặc tạo đường giả.
9. **Xử lý cạnh ra của đỉnh v trước khi tất cả cạnh vào v đóng góp:** các trạng thái downstream nhận giá trị chưa hoàn chỉnh.
10. **Cập nhật một lần rồi đánh dấu v là “xong” ngay khi vừa được tới:** v có thể còn các tiền nhiệm chưa duyệt; chỉ topo mới cho lịch hoàn tất chắc chắn.
11. **Đếm đường đi ngắn nhất bằng tổng `ways[v]` của mọi đường:** hai đại lượng khác nhau.
12. **Khi đếm đường đi ngắn nhất, không đặt lại số cách khi có khoảng cách tốt hơn:** sẽ giữ cả những đường không còn tối ưu.
13. **Dùng Dijkstra chuẩn trên đồ thị có cạnh âm:** điều kiện áp dụng của Dijkstra không còn bảo đảm; trên DAG có thể tính ngắn nhất theo topo.
14. **Giả định đường đi dài nhất trên đồ thị bất kỳ cũng tuyến tính:** cận \(O(V+E)\) nêu ở đây dựa vào tính DAG.
15. **Quên trường hợp nguồn không có indegree=0:** nguồn của truy vấn không nhất thiết là nguồn topo của toàn đồ thị.
16. **Khẳng định topo duy nhất:** nhiều DAG có các đỉnh độc lập tạo nhiều thứ tự hợp lệ.
17. **Lưu một mảng parent rồi dùng nó cho cả min và max:** phải truy vết theo mục tiêu được lưu.
18. **Không xử lý cạnh trùng/lặp trong đếm đường:** phải chốt đếm đường khác nhau theo cạnh hay theo chuỗi đỉnh.
19. **Không kiểm tra overflow của số đường và tổng trọng số:** kết quả có thể sai âm thầm nếu dùng phép cộng thường.
20. **Cho rằng mọi DP DAG đều chỉ có một trạng thái mỗi đỉnh:** một số bài phải giữ thêm chiều thời gian, số bước, số tài nguyên hoặc một tập trạng thái; topo chỉ quyết định lịch, không tự giảm số trạng thái.

## 14. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Chọn thứ tự.** Với các cạnh `5→2`, `5→3`, `2→1`, thứ tự `1,2,3,5` có hợp lệ không? Cho một thứ tự hợp lệ.

*Đáp án:* **Không** vì 5 phải đứng trước 2 và 3, còn 2 phải đứng trước 1. Một thứ tự hợp lệ là **5,2,3,1** (hoặc **5,3,2,1**).

**Bài 2 — Đếm đường đi.** Với cạnh `0→1`, `0→2`, `1→3`, `2→3`, đặt nguồn 0. Hãy tính `ways[3]`.

*Đáp án:* **2**, từ hai đường đi `0→1→3` và `0→2→3`.

**Bài 3 — Cạnh âm.** Một DAG gồm `0→1` trọng số 5, `0→2` trọng số 2 và `2→1` trọng số -4. Đường ngắn nhất từ 0 tới 1 là bao nhiêu?

*Đáp án:* **-2** qua đường `0→2→1`, vì \(2+(-4)=-2<5\). DAG cho phép giải đường ngắn nhất có trọng số âm bằng topo.

**Bài 4 — Đường dài nhất âm.** Đồ thị chỉ có một cạnh `0→1` trọng số -7, nguồn 0. Giá trị longest[1] đúng là bao nhiêu?

*Đáp án:* **-7**, không phải 0. Đỉnh 1 có đường đi hợp lệ nhưng tổng trọng số âm.

**Bài 5 — Đỉnh không tới được.** Trong ví dụ chính có đỉnh 6 cô lập. Vì sao 6 có trong thứ tự tô-pô nhưng `ways[6]=0`?

*Đáp án:* Tô-pô liệt kê **mọi đỉnh của DAG** để bảo đảm thứ tự cạnh; nó không khẳng định nguồn 0 đi tới mọi đỉnh. Không có đường 0→6, nên đếm cách từ 0 đến 6 bằng 0.

**Bài 6 — Chu trình.** Nếu thêm cạnh `4→1` vào đồ thị đang có `1→3→4`, còn dùng Kahn để tính DP một lượt được không?

*Đáp án:* **Không**, vì tạo chu trình \(1\to3\to4\to1\). Kahn không xử lý được toàn bộ đỉnh và phải báo đầu vào không phải DAG.

**Bài 7 — Truy vết.** Nếu hai đường đi ngắn nhất tới v có cùng trọng số, một mảng `parent[v]` lưu được bao nhiêu đường đi?

*Đáp án:* Thông thường chỉ lưu **một** tiền nhiệm được chọn, nên truy vết được **một** đường. Muốn đếm hoặc liệt kê nhiều đường tối ưu cần thêm dữ liệu và có thể tốn chi phí lớn theo số kết quả.

**Bài 8 — Critical path.** Công việc A dài 2, B dài 5, C dài 3 và cả A/B đều phải hoàn thành trước C. Nếu có đủ tài nguyên cho A và B chạy song song, dự án kết thúc sớm nhất lúc nào?

*Đáp án:* \(finish[C]=3+\max(2,5)=\boxed{8}\). Nhánh B→C là đường găng.

**Bài 9 — Chiều duyệt ngược.** Nếu \(dp[u]\) cần giá trị ở các đỉnh hậu nhiệm v với cạnh u→v, cần dùng topo theo chiều nào?

*Đáp án:* **Đảo ngược thứ tự tô-pô**, vì mỗi v phải được tính trước u.

## 15. Quy trình thực hành khi gặp bài DP trên DAG mới

1. **Kiểm tra cấu trúc:** đồ thị có hướng và có bảo đảm không chu trình không? Nếu không, có thể dùng Kahn/DFS để xác nhận; đừng mặc nhiên áp dụng topo cho graph tổng quát.
2. **Xác định nguồn/đích hoặc tập nguồn/đích:** bài toán tính từ một đỉnh, nhiều đỉnh hay trên mọi đường đi của graph?
3. **Định nghĩa trạng thái rõ ràng:** `ways[v]`, `distMin[v]`, `distMax[v]`, `finish[v]` hay một trạng thái nhiều chiều khác biểu diễn chính xác điều gì?
4. **Chốt cơ sở:** ví dụ `ways[source]=1`, `dist[source]=0`, và các đỉnh khác ban đầu **chưa tới được**.
5. **Viết phép chuyển trên từng cạnh:** cộng, min, max hoặc một phép gộp cụ thể. Kiểm tra điều kiện có thể chuyển từ u sang v.
6. **Chọn hướng topo:** chuyển kết quả từ tiền nhiệm sang hậu nhiệm → topo xuôi; dùng kết quả của hậu nhiệm → topo ngược.
7. **Duyệt mỗi cạnh từ một trạng thái đã hoàn tất:** trong push-DP, chỉ phát thông tin từ u khi tới đúng lượt u trong order.
8. **Lưu dữ liệu truy vết nếu cần đường đi:** cha cho min, cha cho max, số cách riêng cho bài đếm; không lẫn lộn mục tiêu.
9. **Xử lý biên và số học:** đỉnh không tới được, trọng số âm, cạnh song song, nhiều đáp án bằng nhau, tràn số và chu trình.
10. **Phân tích độ phức tạp theo trạng thái/thao tác:** với một giá trị và O(1) công việc mỗi cạnh, DP thường \(O(V+E)\) thời gian, không gian \(O(V+E)\) nếu giữ toàn bộ graph.

**Ghi nhớ:** Bản chất của DP trên DAG là **tính trạng thái theo một thứ tự tôn trọng mọi quan hệ phụ thuộc**. Sắp thứ tự tô-pô một lần, khởi tạo đúng nguồn và trạng thái không tới được, rồi chuyển thông tin theo cạnh bằng phép **cộng / min / max** thích hợp. Nhờ không có chu trình, các tiền nhiệm luôn hoàn tất trước hậu nhiệm: ta có thể đếm đường đi và tìm đường ngắn nhất/dài nhất **trong \(O(V+E)\)** khi mỗi cạnh chỉ cần O(1) công việc, kể cả khi đồ thị có cạnh trọng số âm.
