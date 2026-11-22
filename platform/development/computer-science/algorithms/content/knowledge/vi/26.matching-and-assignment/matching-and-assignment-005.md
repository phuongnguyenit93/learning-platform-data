# Chuyển bài toán ghép cặp hai phía thành luồng mạng

Bài toán **ghép cặp hai phía (bipartite matching)** xuất hiện khi cần phân công người cho công việc, sinh viên cho đề tài, máy cho nhiệm vụ hoặc nhân viên cho ca làm. Mỗi đối tượng ở **phía trái** chỉ được chọn tối đa một đối tượng tương thích ở **phía phải**, và ngược lại. Mục tiêu căn bản là chọn được **nhiều cặp hợp lệ nhất**. Một cách giải rất quan trọng là **biến bài toán ghép cặp thành một mạng luồng có dung lượng 1**, rồi tìm luồng cực đại.

Bài thuộc nhóm **Ghép cặp và phân công** trong Computer Science Algorithms, tập trung chính xác vào **“Chuyển bài toán ghép cặp hai phía thành luồng mạng”**. Nội dung giải thích từng cạnh được thêm khi quy đổi, vì sao matching tương ứng với luồng nguyên, cách các **cung dư ngược** thay đổi ghép cặp đã chọn, cách dựng lại danh sách cặp từ luồng, nhận biết ghép cặp hoàn hảo, lấy **phủ đỉnh nhỏ nhất** từ đồ thị dư theo định lý Kőnig, so sánh độ phức tạp với các thuật toán chuyên dụng và xử lý những dữ liệu biên.

Phần Java 17+ là chương trình độc lập: dựng mạng bốn lớp **s → L → R → t**, chạy tăng luồng bằng BFS, in đường tăng và matching cuối, trích phủ đỉnh nhỏ nhất, đồng thời so sánh với **hai bộ giải vét cạn độc lập** trên 5.058 đồ thị hai phía nhỏ và 1.200 bộ input có seed. Tất cả giá trị được đối chiếu với ví dụ và chứng minh, không cần phụ thuộc thư viện ngoài Java chuẩn.

## 1. Định nghĩa ghép cặp hai phía

Cho đồ thị hai phía G=(L∪R,E). Tập L và R **rời nhau**; mỗi cạnh ghép đôi tiềm năng nối một đỉnh u thuộc L với một đỉnh v thuộc R. Không có cạnh hợp lệ nối hai đỉnh cùng phía trong mô hình đơn giản này.

Một **matching M** là tập các cạnh sao cho **không hai cạnh nào có chung đầu mút**. Nếu M chứa (u,v), cả u lẫn v được gọi là **đã ghép**; các đỉnh không xuất hiện trong M là **chưa ghép**.

**Maximum-cardinality matching** là matching có **số cạnh lớn nhất** trong tất cả matching hợp lệ. Giá trị tối ưu được ký hiệu |M*|, có cận hiển nhiên:

~~~text
0 <= |M*| <= min(|L|, |R|).
~~~

Ví dụ mô hình sinh viên–đồ án:

~~~text
L = {A, B}  (hai sinh viên)
R = {X, Y}  (hai đồ án)

Cạnh tương thích:
A -- X
A -- Y
B -- X
~~~

Chọn A–X trước rồi kết luận B không có đồ án còn trống chỉ thu được **một cặp**. Nhưng cách chọn **A–Y và B–X** đạt **hai cặp**, tối ưu. Điều này cho thấy thuật toán tham lam “gặp cặp hợp lệ thì chốt luôn, không sửa” **không đúng** cho bài tổng quát.

## 2. Vì sao đưa matching về bài toán max flow?

Trong mô hình matching, mỗi đỉnh L chỉ được tham gia **tối đa một cạnh ghép** và mỗi đỉnh R cũng vậy. Trong bài toán luồng mạng, **dung lượng cạnh** giới hạn số đơn vị luồng được gửi qua cạnh.

Nếu mọi đường từ nguồn đến đích đều phải đi qua một đỉnh trái và một đỉnh phải, và những cạnh “đi vào phía trái”, “nối hai phía”, “đi ra phía phải” đều có dung lượng 1, thì mỗi **đơn vị luồng nguyên** sẽ tương ứng với việc ghép một cặp L–R.

Ta tạo thêm một **nguồn siêu (source) s** và một **đích siêu (sink) t**. Mạng luồng là đồ thị **có hướng** dù đồ thị ghép cặp ban đầu thường biểu diễn vô hướng. Hướng của cạnh không mang ý nghĩa sinh viên “đi tới” đồ án trong thế giới thực; nó chỉ mô tả tuyến luồng dùng cho phép quy đổi.

Mục tiêu mới: tối đa hóa lượng luồng từ s đến t. Giá trị max flow thu được phải bằng số cặp tối ưu; các phần sau sẽ chứng minh điều này theo cả hai chiều.

## 3. Quy tắc dựng mạng bốn lớp

Với L có a đỉnh và R có b đỉnh:

1. Thêm nguồn s và đích t.
2. Với **mỗi** u∈L, thêm cạnh có hướng **s→u**, dung lượng **1**.
3. Với **mỗi cạnh tương thích** (u,v)∈E, thêm cạnh có hướng **u→v**, dung lượng **1**.
4. Với **mỗi** v∈R, thêm cạnh có hướng **v→t**, dung lượng **1**.
5. **Không thêm** cạnh t→v, v→u hay u→s như **cạnh gốc**; những chiều ngược cần thiết sẽ xuất hiện dưới dạng **cung dư ngược**, được quản lý riêng bởi thuật toán max flow.

Sơ đồ:

~~~text
             các cạnh           các cạnh
s --(1)--> L --(1 nếu hợp lệ)--> R --(1)--> t
             tương thích

Mỗi đường đơn s→t trong mạng ban đầu:
s → một đỉnh L → một đỉnh R → t.
~~~

**Vì sao đều dùng capacity 1?** Cạnh s→u giới hạn u được dùng tối đa một lần; cạnh v→t giới hạn v được dùng tối đa một lần; cạnh u→v mô tả một lựa chọn ghép hợp lệ. Nếu đặt capacity 2 cho s→u thì một người có thể được ghép tới hai công việc, **không còn bài matching chuẩn**.

Số đỉnh mạng mới là **N=a+b+2**. Số cạnh có hướng vật lý trước khi sinh cung dư là **E'=a+|E|+b**. Thuật toán residual sẽ thêm một cung ngược cho mỗi cạnh gốc, do đó tổng số cung lưu trữ là 2E'.

## 4. Cách đánh số đỉnh khi lập trình

Để tránh nhầm chỉ số của hai phía, chương trình quy định:

~~~text
source s = 0.

L_i  (i=0..a-1) có ID mạng = 1+i.

R_j  (j=0..b-1) có ID mạng = 1+a+j.

sink t = 1+a+b.

Tổng số đỉnh = a+b+2.
~~~

Với a=2, b=2:

~~~text
s = 0
L_0 = 1, L_1 = 2
R_0 = 3, R_1 = 4
t = 5

Các cạnh tương thích:
(L_0,R_0), (L_0,R_1), (L_1,R_0)

Cạnh mạng:
0->1, 0->2,
1->3, 1->4, 2->3,
3->5, 4->5.

Tất cả capacity = 1.
~~~

Các số 0,1 trong cặp ghép **là chỉ số bên trong từng phía**, không phải ID toàn mạng. Ví dụ cặp (0,1) nghĩa là **L_0–R_1**, được thể hiện trong mạng bởi cung **1→4**.

## 5. Chiều thuận: một matching tạo thành một luồng

Giả sử đã chọn matching M hợp lệ có k cạnh. Với mỗi cặp (u,v)∈M, gửi **đúng một đơn vị luồng** trên ba cạnh:

~~~text
s -> u -> v -> t.
~~~

Vì matching không dùng trùng đỉnh trái, hai đường trên không tranh cùng cạnh s→u. Tương tự không dùng trùng đỉnh phải nên không tranh v→t. Mỗi cặp chỉ sử dụng một cạnh tương thích u→v capacity 1. Do đó **mọi cạnh đều không vượt dung lượng**.

Tại u∈L đã ghép, một đơn vị đi từ s vào và một đơn vị đi sang R; tại v∈R đã ghép, một đơn vị từ L vào và một đơn vị đi tới t. Tại đỉnh chưa ghép, luồng 0. Bảo toàn luồng được duy trì ở mọi đỉnh nội bộ.

Tổng luồng đi khỏi s bằng đúng k vì có k cặp. Như vậy **bất kỳ matching k cặp cũng tạo ra một luồng hợp lệ có giá trị k**. Suy ra:

~~~text
maximum flow >= maximum matching size.
~~~

Điều này đặc biệt quan trọng: quy đổi không loại bỏ một phương án ghép nào. Mọi matching đều có cách biểu diễn thành luồng.

## 6. Chiều ngược: một luồng nguyên tạo thành matching

Chiều ngược cần giả thiết **luồng nguyên**. Mạng chỉ dùng capacity nguyên 0 hoặc 1, khởi tạo f=0 và tăng qua các đường dư với bottleneck nguyên, nên Ford–Fulkerson/Edmonds–Karp duy trì luồng nguyên; định lý tích phân luồng cũng bảo đảm tồn tại nghiệm tối ưu nguyên.

Xét một luồng nguyên hợp lệ. Với mỗi cạnh tương thích u→v:

- f(u,v) chỉ có thể là 0 hoặc 1 vì capacity bằng 1.
- Nếu f(u,v)=1, đưa cặp (u,v) vào M.
- Cạnh s→u capacity 1 cùng bảo toàn tại u khiến **tổng số cạnh ghép từ u không vượt 1**.
- Cạnh v→t capacity 1 cùng bảo toàn tại v khiến **tổng số cạnh ghép tới v không vượt 1**.

Vậy những cạnh u→v có luồng 1 **không xung đột đầu mút** và tạo thành matching. Tổng số cặp đúng bằng tổng luồng qua các cạnh s→L, tức **giá trị luồng**.

Do đó một luồng nguyên giá trị F quy đổi thành matching F cặp. Kết hợp với chiều thuận:

~~~text
KÍCH THƯỚC MATCHING CỰC ĐẠI
         = GIÁ TRỊ LUỒNG CỰC ĐẠI.
~~~

Nếu dùng một thuật toán tính **luồng phân số bất kỳ** mà không bảo đảm nguyên, không được tự chọn mọi cạnh có f>0 làm matching: nhiều cạnh có thể mang phân số dương qua cùng một đỉnh. Việc dùng **dung lượng nguyên và thuật toán tăng luồng nguyên** là mắt xích quan trọng.

## 7. Đồ thị dư giúp thay đổi lựa chọn ghép cũ

Sau khi chọn cặp (u,v), cạnh gốc u→v có capacity 1 và f=1. Residual:

~~~text
Cung thuận u->v có residual = 1-f = 0.
Cung ngược v->u có residual = f = 1.
~~~

Cung ngược v→u cho phép **rút lại cặp u–v** đã chọn trong quá khứ. Khi đường tăng sử dụng cung ngược đó, luồng trên cạnh tương ứng bị giảm 1; một cặp cũ được bỏ để giải phóng đỉnh cho cặp khác.

Đây chính là cơ chế giúp tìm matching tối ưu thay vì chấp nhận sai lầm của greedy. Một đường tăng có thể **xen kẽ cạnh chưa ghép và cạnh đã ghép**; sau khi thay đổi trạng thái các cạnh, số cặp tăng thêm 1.

Cung dư ngược **không phải một cạnh tương thích mới** của bài ghép cặp. Ví dụ có A→X trong mạng thì X→A là cung ngược phục vụ hủy A–X, không có nghĩa bài toán cho phép ghép X với A theo một hướng nghiệp vụ mới.

## 8. Truy vết hai lần tăng trên ví dụ A,B và X,Y

Dùng chỉ số:

~~~text
s=0, A=L_0=1, B=L_1=2,
X=R_0=3, Y=R_1=4, t=5.

Cặp hợp lệ: A-X, A-Y, B-X.
~~~

Chạy BFS tìm đường tăng của Edmonds–Karp, với adjacency được lưu theo thứ tự cạnh trong chương trình.

**Lượt 1:** tìm đường ngắn:

~~~text
0 -> 1 -> 3 -> 5
s -> A -> X -> t

Bottleneck = 1.
Matching hiện tại: {A-X}.
~~~

Bây giờ cạnh 1→3 bão hòa và cung ngược 3→1 có residual 1. B vẫn chưa ghép và Y còn trống.

**Lượt 2:** không thể chỉ đi B→X→t vì cạnh X→t đã bão hòa. Tuy nhiên đồ thị dư có đường:

~~~text
0 -> 2 -> 3 -> 1 -> 4 -> 5
s -> B -> X -> A -> Y -> t
          ^--- cung X->A là cung ngược
~~~

Khi tăng 1 qua đường này:

- Thêm B–X.
- Đi qua cung ngược X→A để **hủy A–X**.
- Thêm A–Y.
- Hai đầu A và B đều ghép, X và Y đều ghép.

Matching cuối:

~~~text
M = {(A,Y),(B,X)}
  = {(L_0,R_1),(L_1,R_0)}

|M| = 2.
~~~

Đường tăng thứ hai có nhiều cung hơn đường thứ nhất nhưng **cải thiện toàn bộ matching**, vì nó sắp xếp lại một cặp trước đó.

## 9. Vì sao greedy đơn giản có thể sai?

Một cách làm rất thường gặp là duyệt từng đỉnh bên trái rồi chọn **đỉnh bên phải đầu tiên còn rảnh**, nhưng **không cho phép thay đổi cặp đã chọn**. Với thứ tự A trước B:

~~~text
A chọn X.
B chỉ có X nhưng X đã bận.
Greedy kết thúc với 1 cặp.
~~~

Trong khi matching 2 cặp vẫn tồn tại: A–Y, B–X.

Cả thuật toán **đường tăng (augmenting path)** chuyên dụng cho matching và thuật toán **luồng cực đại với cạnh ngược residual** đều khắc phục vấn đề bằng cách **đổi ghép** trên một chuỗi xen kẽ.

Nghĩa là “đã ghép rồi” **không bắt buộc là vĩnh viễn**. Trong bài tối ưu toàn cục, có thể cần hủy một cặp cục bộ để tăng số cặp tổng thể.

Đây không phải việc tạo ra hai cặp cùng sử dụng một đỉnh trong quá trình. Khi tăng luồng trên toàn đường dư, các thay đổi phối hợp với nhau và **bảo toàn ràng buộc capacity**, nên trạng thái cuối mỗi lượt vẫn là matching hợp lệ.

## 10. Hai lần tăng tương ứng đường xen kẽ

Trong đồ thị hai phía, một **đường tăng matching** là một đường bắt đầu tại một đỉnh trái chưa ghép, kết thúc tại một đỉnh phải chưa ghép, và các cạnh xen kẽ:

~~~text
cạnh chưa ghép
cạnh đã ghép
cạnh chưa ghép
cạnh đã ghép
...
cạnh chưa ghép.
~~~

Đổi trạng thái (flip) của mọi cạnh trên đường:

- Các cạnh trước đó chưa ghép trở thành đã ghép.
- Các cạnh trước đó đã ghép bị loại khỏi matching.
- Tổng số cạnh tăng **1** vì có một cạnh chưa ghép nhiều hơn số cạnh đã ghép trên đường.

Trong mạng luồng, đường từ s tới t tương ứng với đường xen kẽ này sau khi bỏ s,t; cung L→R thuận là khả năng chọn cạnh chưa ghép và cung R→L ngược là khả năng bỏ cạnh đã ghép.

**Định lý Berge:** một matching là cực đại theo **số cặp** khi và chỉ khi **không còn đường tăng**. Đây là cách diễn đạt tương ứng của định lý không còn đường tăng trong max flow. Không nên nhầm **maximal matching** (không thêm được trực tiếp một cạnh mới mà vẫn hợp lệ) với **maximum matching** (nhiều cặp nhất): greedy có thể maximal nhưng không maximum.

## 11. Chạy max flow bằng Edmonds–Karp

Chương trình Java dùng BFS trong đồ thị dư. Mỗi lần tìm đường:

1. Khởi tạo queue với s, seen[s]=true.
2. Từ đỉnh u, chỉ duyệt những cung có **residual>0**.
3. Với đỉnh mới v, lưu **parentArc[v]** là đúng đối tượng cung u→v.
4. Khi tới t, truy ngược parentArc để dựng đường và tìm **bottleneck**.
5. Giảm residual của cung thuận theo chiều đi và tăng residual của cung reverse; luồng tổng cộng tăng bottleneck.
6. Lặp lại với mảng seen/parentArc **mới** vì mạng dư đã thay đổi.
7. Khi không tìm được đường s→t, dừng. Luồng hiện tại cực đại.

Với mạng matching dung lượng 1, **mọi lần tăng có bottleneck đúng 1**. Vì vậy số lượt tăng đúng bằng kích thước matching tối ưu. Điều này còn giúp giải thích vì sao trace Java có **2 đường** khi đáp án là 2 cặp.

Việc chọn BFS thay vì DFS không thay đổi đáp án tối ưu. BFS bảo đảm chọn đường tăng ít cung dư nhất ở từng lượt, và là phiên bản **Edmonds–Karp** với bảo đảm đa thức tổng quát.

## 12. Lấy matching từ các cạnh mang luồng 1

Sau khi max flow dừng, ta không cần suy đoán matching từ những đường tăng đã in ra, bởi đường tăng sau có thể **hủy** một cặp từng được dùng trước đó. Cách đúng là kiểm tra **trạng thái cuối của từng cạnh gốc L→R**.

Với cạnh gốc có capacity=1:

~~~text
f(u,v) = 1 - forwardResidual(u,v).

Nếu forwardResidual(u,v) == 0:
    cạnh đã có f=1 => đưa (u,v) vào matching.

Nếu forwardResidual(u,v) == 1:
    cạnh có f=0 => không chọn.
~~~

Chương trình lưu đối tượng Arc thuận của **từng cặp đầu vào** để đọc residual chính xác, rồi xuất Pair(left,right). Không dùng các cung s→L, R→t hoặc cung dư ngược để dựng danh sách matching.

Nếu input chứa hai cạnh trùng (u,v), sẽ có **hai Arc thuận khác nhau**, nhưng do s→u và v→t cùng capacity 1, tối đa **một** cạnh trong đó có thể được chọn. Bộ kiểm thử có trường hợp lặp cùng một cặp và xác nhận matching chỉ có kích thước 1.

## 13. Định lý max-flow/min-cut bảo đảm tối ưu

Trong mọi mạng có hướng, một **lát cắt s–t** chia các đỉnh thành S chứa s và T chứa t. Dung lượng lát cắt là tổng capacity của các cạnh gốc đi từ S sang T.

Mọi luồng hợp lệ có giá trị **không lớn hơn** dung lượng của bất kỳ lát cắt nào. Khi không còn đường tăng trên mạng dư, S là tập đỉnh còn **reachable từ s theo những cung có residual>0**, và t không thuộc S.

Các cạnh gốc đi S→T đều bão hòa; các cạnh đi T→S không mang luồng theo chiều gốc, nên:

~~~text
maxFlow = capacity(S,T) = minCut.
~~~

Vì đã chứng minh kích thước matching tối ưu bằng giá trị max flow, và max flow đạt cận trên min cut, một đáp án matching được trích từ luồng cực đại sẽ là **đáp án tối ưu toàn cục**.

Mạng được tạo từ matching có cấu trúc đặc biệt; ngoài việc lấy giá trị tối ưu, ta còn có thể trích một **phủ đỉnh nhỏ nhất** chỉ bằng tính reachability trên mạng dư cuối cùng.

## 14. Phủ đỉnh là gì và liên hệ với matching?

**Vertex cover (phủ đỉnh)** của đồ thị hai phía là một tập đỉnh C⊆L∪R sao cho **mỗi cạnh tương thích (u,v) có ít nhất một đầu mút nằm trong C**.

Ví dụ đồ thị A–X, A–Y, B–X:

~~~text
{A,B} là một phủ đỉnh (chọn cả hai đỉnh trái).
{X,Y} cũng là một phủ đỉnh.
{A,X} cũng là một phủ đỉnh.

Không có phủ đỉnh chỉ 1 đỉnh, vì không đỉnh nào
phủ được đồng thời tất cả 3 cạnh.
~~~

Một matching gồm k cạnh **không chung đầu mút**, nên mọi phủ đỉnh phải chứa **ít nhất k đỉnh** để chạm tới cả k cạnh ấy. Do đó:

~~~text
maximum matching size <= minimum vertex cover size.
~~~

Với **đồ thị hai phía**, định lý **Kőnig** phát biểu hai đại lượng này **bằng nhau**. Đây là tính chất đặc biệt; không được mặc định đúng cho **đồ thị tổng quát** không hai phía.

## 15. Lấy phủ đỉnh nhỏ nhất từ mạng dư

Sau khi tìm max flow, BFS từ s theo các cung dư có residual>0; gọi Z là tập reachable trong **mạng luồng**. Đặt:

~~~text
Z_L = Z ∩ L.
Z_R = Z ∩ R.

MinimumVertexCover =
    (L \ Z_L) ∪ Z_R.
~~~

Nghĩa là **chọn những đỉnh trái không reachable** và **những đỉnh phải reachable**.

Với ví dụ hai trái hai phải đã có matching hoàn hảo, tất cả cạnh s→L đều bão hòa. Không có đường dư đi khỏi s, nên Z={s}; ta thu:

~~~text
L \ Z_L = {A,B}.
Z_R = ∅.

Một minimum vertex cover = {A,B}.
Độ lớn = 2 = số cặp ghép tối đa.
~~~

Phủ đỉnh tối thiểu **không nhất thiết duy nhất**. Trên ví dụ còn có {X,Y} và {A,X}, đều có hai đỉnh. Công thức reachable trả một phủ đỉnh tối thiểu phụ thuộc matching cuối và cấu trúc residual; không cần liệt kê mọi đáp án.

## 16. Chứng minh công thức phủ đỉnh từ reachable

Đặt C=(L\Z_L)∪Z_R sau khi max flow.

**C là một phủ đỉnh:** giả sử tồn tại cạnh hợp lệ u∈L, v∈R nhưng cả hai **không** thuộc C. Khi đó u∈Z_L và v∉Z_R. Xét cung gốc u→v capacity=1.

- Nếu cung thuận còn residual=1, vì u reachable nên v cũng reachable, mâu thuẫn với v∉Z_R.
- Nếu cung thuận residual=0, cạnh u–v đang ghép và cung ngược v→u có residual=1. Vì u đã được ghép, cạnh s→u bão hòa, không thể đi trực tiếp từ s vào u. Đường dư tới u, nếu có, phải tới qua cung ngược của cạnh ghép u–v (u không có cạnh vào khác từ phía trái trong cấu trúc bốn lớp). Điều đó buộc v đã reachable, lại mâu thuẫn.

Vậy mọi cạnh phải chạm ít nhất một đỉnh C.

**C có kích thước tối thiểu:** lát cắt reachable của mạng bốn lớp không có cung L→R có capacity dương đi từ Z sang phần bù: nếu có cung thuận residual dương sẽ làm đỉnh bên phải reachable; nếu cung đã ghép thì lập luận vừa nêu cũng loại trường hợp đầu trái reachable, đầu phải không reachable.

Dung lượng của lát cắt vì thế chỉ gồm các cạnh:

- s→u với u∈L\Z_L: mỗi cạnh capacity 1.
- v→t với v∈Z_R: mỗi cạnh capacity 1.

Suy ra cutCapacity = |L\Z_L|+|Z_R|=|C|. Theo max-flow/min-cut, |C| bằng giá trị luồng cực đại, cũng bằng số cặp matching tối đa. Mà mọi phủ đỉnh có kích thước ít nhất số cặp matching, nên C là **phủ đỉnh nhỏ nhất**.

Đây cũng là một cách chứng minh trực tiếp định lý **Kőnig** qua mạng luồng.

## 17. Ghép cặp hoàn hảo và điều kiện Hall

Một **matching phủ hết phía trái (left-perfect)** cần ghép mỗi đỉnh u∈L đúng một lần. Điều kiện kiểm tra rất đơn giản sau khi tìm maximum matching:

~~~text
leftPerfect ⇔ matchingSize == |L|.
~~~

Nếu hai phía có cùng số đỉnh và matchingSize=|L|=|R|, matching là **perfect matching của cả hai phía**. Nếu |L|≠|R|, không thể ghép hết **cả hai phía** bằng các cặp một–một, dù vẫn có thể ghép hết phía nhỏ hơn.

**Định lý Hall:** tồn tại matching phủ hết L khi và chỉ khi **mọi tập con X⊆L** đều có ít nhất |X| hàng xóm phân biệt ở R:

~~~text
|N(X)| >= |X| với mọi X ⊆ L.
~~~

Nếu hai sinh viên chỉ phù hợp cùng một đồ án, tập X gồm hai sinh viên có |N(X)|=1<2, nên không thể ghép cả hai. Định lý Hall diễn giải nguyên nhân thất bại dưới dạng **thiếu khả năng lựa chọn**; max flow là cách tính đáp án mà **không cần duyệt mọi X**.

**Trường hợp L rỗng:** theo quy ước toán học, matching rỗng phủ hết L vì không có đỉnh trái nào bị bỏ sót. Nếu nghiệp vụ yêu cầu ít nhất một người được phân công, thêm điều kiện |L|>0 riêng cho ứng dụng.

## 18. Ví dụ còn đỉnh không ghép được

Lấy L có 3 đỉnh, R có 2 đỉnh và các cạnh:

~~~text
L_0 -> R_0.
L_1 -> R_0.
L_2 -> R_1.
~~~

Một matching tối đa là:

~~~text
M = {(L_0,R_0),(L_2,R_1)}.
|M| = 2.

L_1 không được ghép.
Không có left-perfect matching vì |L|=3 mà |R|=2.
~~~

Sau max flow, tìm Z từ s trên mạng dư. Do L_1 chưa ghép, cạnh s→L_1 còn residual dương; từ L_1 có thể tới R_0, rồi qua cung ngược của cạnh ghép L_0→R_0 tới L_0. Phía phải R_1 không reachable.

~~~text
Z_L = {L_0,L_1}.
Z_R = {R_0}.

C = (L \ Z_L) ∪ Z_R
  = {L_2, R_0}.

|C| = 2.
~~~

Đây là một minimum vertex cover: L_2 chạm cạnh L_2–R_1, R_0 chạm hai cạnh còn lại. Mã Java in chính các tập này để thấy rõ công thức không chỉ hoạt động khi matching hoàn hảo.

## 19. Độ phức tạp của phép chuyển

Gọi a=|L|, b=|R|, m=|E| là số cặp tương thích đầu vào (tính cả phần tử trùng nếu có).

Mạng có:

~~~text
N = a+b+2 đỉnh.
E' = a+b+m cạnh gốc có hướng.
2E' cung trong residual adjacency.
~~~

Dựng mạng: O(N+E') thời gian và bộ nhớ.

Chương trình dùng BFS mỗi lần tìm đường. Trên mạng matching capacity 1:

- Mỗi augment tăng **đúng 1** đơn vị luồng.
- Tối đa K=min(a,b) đơn vị luồng có thể đi từ s tới t.
- Mỗi lần BFS quét O(N+E') trên adjacency dư.
- Suy ra thời gian của **riêng bản cài đặt này** là **O(K(N+E'))**, chưa tính ghi log kết quả.
- Bộ nhớ cơ bản của residual, parentArc, visited, danh sách cặp và cover là **O(N+E')**.

Vì demo lưu **toàn bộ các đường augmentingPath** để giải thích, nó dùng thêm **O(KN)** bộ nhớ ở trường hợp xấu, vì mỗi đường có thể dài O(N). Nếu chỉ cần giá trị và matching cuối, có thể bỏ trường trace để giữ bộ nhớ phụ O(N+E').

Cận tổng quát của Edmonds–Karp trên mạng tùy ý là **O(NE'²)**, không phụ thuộc trị số capacity. Cận riêng O(K(N+E')) ở đây chặt và hữu ích hơn vì mọi capacity đều 1 và mỗi augment tăng 1.

## 20. So với thuật toán chuyên dụng cho matching

Mạng luồng là một phép quy đổi mang tính tổng quát và rất dễ liên hệ với ràng buộc capacity, nhưng không phải luôn là cách nhanh nhất:

| Phương pháp | Trọng tâm | Ghi chú |
| --- | --- | --- |
| Max flow bằng Edmonds–Karp | Dựng s→L→R→t rồi BFS trên residual | Tổng quát, dễ chứng minh, phù hợp dữ liệu nhỏ/vừa |
| DFS đường tăng kiểu Kuhn | Duyệt các cạnh alternating trong đồ thị hai phía | Thường O(a·m), không cần dựng s,t thật |
| Hopcroft–Karp | Tìm nhiều đường tăng ngắn nhất trong một pha | O(m√(a+b)) cho matching hai phía đơn |
| Min-cost max-flow | Có chi phí/lợi ích trên từng cặp | Giải ghép cặp có trọng số kèm mục tiêu phù hợp |
| Hungarian algorithm | Bài toán assignment có ma trận chi phí | Thuật toán chuyên cho phân công trọng số, thường O(n³) |
| Luồng với capacity đỉnh >1 | Một đỉnh được phép nhận nhiều đối tác | Dạng b-matching hoặc phân bổ có hạn mức, không còn matching một–một |

Với đồ thị hai phía lớn có nhiều cạnh, **Hopcroft–Karp** thường phù hợp hơn bản Edmonds–Karp giáo khoa vì xử lý nhiều đường tăng trong từng pha. Tuy nhiên phép quy đổi max flow trở nên cực kỳ hữu ích khi đề thêm những điều kiện về năng lực, nhóm, hạn mức hoặc ràng buộc mạng.

**Cảnh báo về trọng số:** nếu mỗi cặp có giá trị/chí phí khác nhau, mục tiêu “tối đa số cặp” chưa đủ. Không thể chỉ thay capacity từ 1 thành điểm số rồi hy vọng max flow tối ưu tổng điểm; cần một bài toán **luồng chi phí nhỏ nhất** hoặc thuật toán assignment đúng mục tiêu.

## 21. Đa cạnh, đỉnh cô lập, phía rỗng và dữ liệu lỗi

**Cạnh tương thích bị lặp:** hai bản ghi giống nhau (u,v) có thể xuất hiện trong dữ liệu. Nếu chỉ hỏi quan hệ có thể ghép, loại bản trùng trước khi dựng cũng được; Java demo **cho phép trùng** và tạo hai cạnh residual riêng, nhưng matching vẫn không dùng một u hoặc v hai lần nhờ các cạnh s→L, R→t capacity 1.

**Đỉnh cô lập:** một sinh viên không nối tới đồ án nào không thể ghép. Giá trị matching vẫn được tính cho các đỉnh còn lại; đỉnh cô lập có thể xuất hiện ở phần reachable sau max flow nhưng không tạo cặp mới.

**Một phía rỗng:** không có đường qua bốn lớp s→L→R→t, nên đáp án là 0 và matching rỗng. Phủ đỉnh nhỏ nhất cũng là rỗng vì không có cạnh L–R cần phủ.

**Số lượng hai phía khác nhau:** matchingSize≤min(a,b), không thể kết luận mọi người đã được phân công chỉ từ điều kiện matchingSize=b khi a>b.

**Đầu mút sai phía hoặc vượt phạm vi:** dữ liệu Pair(left,right) phải chứa left trong [0,a) và right trong [0,b). Không chấp nhận số âm, null hoặc chỉ số ngoài miền; code chủ động ném IllegalArgumentException.

**Đồ thị không hai phía:** không thể lấy một cạnh giữa hai đỉnh cùng nhóm rồi ép nó vào mô hình L→R mà vẫn giữ nguyên bài toán. Trước tiên phải bảo đảm hai nhóm rời nhau và mọi cạnh hợp lệ nối khác phía, hoặc dùng thuật toán matching cho đồ thị tổng quát.

**Giới hạn demo:** tổng a+b không quá 1000; giới hạn này giúp tài liệu có một hợp đồng rõ ràng cho phép thử thực hành, không phải giới hạn lý thuyết của phương pháp.

## 22. Java 17+ hoàn chỉnh: mạng luồng, matching và vertex cover

Lưu toàn bộ mã dưới đây trong **BipartiteMatchingAsFlow.java**. Chương trình thực hiện:

1. **solve(a,b,edges):** xác nhận dữ liệu, dựng mạng s→L→R→t với tất cả capacity 1.
2. **ResidualNetwork.addEdge:** tạo đúng cặp Arc thuận/ngược, liên kết con trỏ reverse.
3. **findPath:** BFS trên những cung có residual dương; trả mảng parent arc để dựng đường tăng.
4. **Cập nhật residual:** giảm dung lượng dư theo chiều đi, tăng cung ngược để có thể đổi ghép.
5. **Trích matching:** kiểm tra những Arc thuận L→R có residual bằng 0; đảm bảo không chung đầu mút.
6. **Trích minimum vertex cover:** BFS reachable từ s sau khi max flow; trả L\Z_L và Z_R.
7. **Oracle riêng:** dùng quay lui liệt kê matching và dùng bitmask liệt kê phủ đỉnh trên input nhỏ.
8. **Kiểm thử:** các đồ thị vét cạn, input ngẫu nhiên có cạnh lặp, một bài matching hoàn hảo 100×100 và các trường hợp lỗi.

**Đầu vào:** leftSize,rightSize≥0; leftSize+rightSize≤1000; danh sách Pair không null; mỗi pair hợp lệ theo miền 0-based của từng phía; có thể lặp cặp. Kết quả chứa số cặp tối ưu, các cặp đã chọn, chỉ số cover của hai phía, và các đường tăng ở **ID mạng**. List kết quả được sao chép phòng vệ; mỗi augmenting path cũng được sao chép thành danh sách bất biến.

Bản chạy có chủ đích lưu trace để dễ học. Nếu áp dụng cho mạng lớn, hãy loại bỏ trace nhằm giảm bộ nhớ; không được nhầm danh sách đường tăng lịch sử với **matching cuối**, vì một đường tăng sau có thể hoàn tác cặp cũ.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

public final class BipartiteMatchingAsFlow {
    public record Pair(int left, int right) {
        @Override public String toString() {
            return "(" + left + "," + right + ")";
        }
    }

    public record Result(int cardinality, List<Pair> pairs,
                         List<Integer> leftCover, List<Integer> rightCover,
                         List<List<Integer>> augmentingPaths) {
        public Result {
            pairs = List.copyOf(pairs);
            leftCover = List.copyOf(leftCover);
            rightCover = List.copyOf(rightCover);
            List<List<Integer>> paths = new ArrayList<>();
            for (List<Integer> p : augmentingPaths) {
                paths.add(List.copyOf(p));
            }
            augmentingPaths = List.copyOf(paths);
        }
    }

    private static final class Arc {
        final int from;
        final int to;
        int residual;
        Arc reverse;
        Arc(int from, int to, int residual) {
            this.from = from;
            this.to = to;
            this.residual = residual;
        }
    }

    private static final class ResidualNetwork {
        final List<List<Arc>> adj;

        ResidualNetwork(int n) {
            adj = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                adj.add(new ArrayList<>());
            }
        }

        Arc addEdge(int u, int v, int cap) {
            Arc forward = new Arc(u, v, cap);
            Arc backward = new Arc(v, u, 0);
            forward.reverse = backward;
            backward.reverse = forward;
            adj.get(u).add(forward);
            adj.get(v).add(backward);
            return forward;
        }

        Arc[] findPath(int source, int sink) {
            Arc[] parent = new Arc[adj.size()];
            boolean[] seen = new boolean[adj.size()];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[source] = true;
            queue.add(source);
            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (Arc arc : adj.get(u)) {
                    if (arc.residual == 0 || seen[arc.to]) {
                        continue;
                    }
                    seen[arc.to] = true;
                    parent[arc.to] = arc;
                    if (arc.to == sink) {
                        return parent;
                    }
                    queue.add(arc.to);
                }
            }
            return null;
        }

        boolean[] reachable(int source) {
            boolean[] seen = new boolean[adj.size()];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[source] = true;
            queue.add(source);
            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (Arc arc : adj.get(u)) {
                    if (arc.residual > 0 && !seen[arc.to]) {
                        seen[arc.to] = true;
                        queue.add(arc.to);
                    }
                }
            }
            return seen;
        }
    }

    private BipartiteMatchingAsFlow() { }

    public static Result solve(int leftSize, int rightSize,
                               List<Pair> edges) {
        if (leftSize < 0 || rightSize < 0 ||
                (long) leftSize + rightSize > 1000 || edges == null) {
            throw new IllegalArgumentException("invalid bipartite input");
        }
        for (Pair edge : edges) {
            if (edge == null ||
                    edge.left() < 0 || edge.left() >= leftSize ||
                    edge.right() < 0 || edge.right() >= rightSize) {
                throw new IllegalArgumentException("invalid pair");
            }
        }

        int source = 0;
        int sink = leftSize + rightSize + 1;
        ResidualNetwork net = new ResidualNetwork(sink + 1);
        for (int i = 0; i < leftSize; i++) {
            net.addEdge(source, 1 + i, 1);
        }

        List<Arc> pairArcs = new ArrayList<>();
        for (Pair e : edges) {
            pairArcs.add(net.addEdge(1 + e.left(),
                    1 + leftSize + e.right(), 1));
        }
        for (int j = 0; j < rightSize; j++) {
            net.addEdge(1 + leftSize + j, sink, 1);
        }

        int total = 0;
        List<List<Integer>> paths = new ArrayList<>();
        while (true) {
            Arc[] parent = net.findPath(source, sink);
            if (parent == null) {
                break;
            }
            int delta = Integer.MAX_VALUE;
            List<Integer> path = new ArrayList<>();
            int v = sink;
            path.add(v);
            while (v != source) {
                Arc arc = parent[v];
                if (arc == null) {
                    throw new AssertionError("broken BFS path");
                }
                delta = Math.min(delta, arc.residual);
                v = arc.from;
                path.add(v);
            }
            java.util.Collections.reverse(path);
            if (delta != 1) {
                throw new AssertionError("unit network must augment by one");
            }
            for (int to = sink; to != source; ) {
                Arc arc = parent[to];
                arc.residual -= delta;
                arc.reverse.residual += delta;
                to = arc.from;
            }
            total += delta;
            paths.add(path);
        }

        List<Pair> matching = new ArrayList<>();
        boolean[] usedLeft = new boolean[leftSize];
        boolean[] usedRight = new boolean[rightSize];
        for (int i = 0; i < edges.size(); i++) {
            if (pairArcs.get(i).residual == 0) {
                Pair p = edges.get(i);
                if (usedLeft[p.left()] || usedRight[p.right()]) {
                    throw new AssertionError("matching uses vertex twice");
                }
                usedLeft[p.left()] = true;
                usedRight[p.right()] = true;
                matching.add(p);
            }
        }

        boolean[] seen = net.reachable(source);
        List<Integer> coverLeft = new ArrayList<>();
        List<Integer> coverRight = new ArrayList<>();
        for (int i = 0; i < leftSize; i++) {
            if (!seen[1 + i]) {
                coverLeft.add(i);
            }
        }
        for (int j = 0; j < rightSize; j++) {
            if (seen[1 + leftSize + j]) {
                coverRight.add(j);
            }
        }
        if (total != matching.size() ||
                total != coverLeft.size() + coverRight.size()) {
            throw new AssertionError("flow/matching/cover mismatch");
        }
        return new Result(total, matching, coverLeft, coverRight, paths);
    }

    private static int bruteMatching(boolean[][] allowed, int i,
                                     int usedMask, int rightSize) {
        if (i == allowed.length) {
            return 0;
        }
        int best = bruteMatching(allowed, i + 1, usedMask, rightSize);
        for (int j = 0; j < rightSize; j++) {
            if (allowed[i][j] && (usedMask & (1 << j)) == 0) {
                best = Math.max(best, 1 + bruteMatching(
                        allowed, i + 1, usedMask | (1 << j), rightSize));
            }
        }
        return best;
    }

    private static int bruteCover(int leftSize, int rightSize,
                                  List<Pair> edges) {
        int best = leftSize + rightSize;
        int total = 1 << (leftSize + rightSize);
        for (int mask = 0; mask < total; mask++) {
            if (Integer.bitCount(mask) >= best) {
                continue;
            }
            boolean coversAll = true;
            for (Pair p : edges) {
                if ((mask & (1 << p.left())) == 0 &&
                        (mask & (1 << (leftSize + p.right()))) == 0) {
                    coversAll = false;
                    break;
                }
            }
            if (coversAll) {
                best = Integer.bitCount(mask);
            }
        }
        return best;
    }

    private static void verifyOne(int leftSize, int rightSize,
                                  List<Pair> edges) {
        Result answer = solve(leftSize, rightSize, edges);
        boolean[][] allowed = new boolean[leftSize][rightSize];
        for (Pair p : edges) {
            allowed[p.left()][p.right()] = true;
        }

        int matchingOracle = bruteMatching(allowed, 0, 0, rightSize);
        int coverOracle = bruteCover(leftSize, rightSize, edges);
        if (matchingOracle != answer.cardinality() ||
                coverOracle != answer.cardinality()) {
            throw new AssertionError("brute matching/cover mismatch");
        }

        boolean[] usedL = new boolean[leftSize], usedR = new boolean[rightSize];
        for (Pair p : answer.pairs()) {
            if (!allowed[p.left()][p.right()] ||
                    usedL[p.left()] || usedR[p.right()]) {
                throw new AssertionError("invalid matching witness");
            }
            usedL[p.left()] = true;
            usedR[p.right()] = true;
        }
        if (answer.pairs().size() != answer.cardinality() ||
                answer.augmentingPaths().size() != answer.cardinality()) {
            throw new AssertionError("incorrect flow trace size");
        }

        boolean[] inCoverL = new boolean[leftSize];
        boolean[] inCoverR = new boolean[rightSize];
        for (int i : answer.leftCover()) {
            if (inCoverL[i]) {
                throw new AssertionError("duplicate left cover vertex");
            }
            inCoverL[i] = true;
        }
        for (int j : answer.rightCover()) {
            if (inCoverR[j]) {
                throw new AssertionError("duplicate right cover vertex");
            }
            inCoverR[j] = true;
        }
        for (Pair p : edges) {
            if (!inCoverL[p.left()] && !inCoverR[p.right()]) {
                throw new AssertionError("uncovered edge");
            }
        }
        for (List<Integer> path : answer.augmentingPaths()) {
            if (path.size() < 4 ||
                    path.get(0) != 0 ||
                    path.get(path.size() - 1) != leftSize + rightSize + 1) {
                throw new AssertionError("bad augmenting path endpoints");
            }
            boolean[] seen = new boolean[leftSize + rightSize + 2];
            for (int v : path) {
                if (v < 0 || v >= seen.length || seen[v]) {
                    throw new AssertionError("bad augmenting path vertex");
                }
                seen[v] = true;
            }
        }
    }

    private static void expectInvalid(Runnable call) {
        try {
            call.run();
        } catch (IllegalArgumentException correct) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    private static void verify() {
        int exhaustive = 0;
        for (int left = 0; left <= 4; left++) {
            for (int right = 0; right <= 3; right++) {
                int bits = left * right;
                for (int mask = 0; mask < (1 << bits); mask++) {
                    List<Pair> edges = new ArrayList<>();
                    for (int i = 0; i < left; i++) {
                        for (int j = 0; j < right; j++) {
                            if ((mask & (1 << (i * right + j))) != 0) {
                                edges.add(new Pair(i, j));
                            }
                        }
                    }
                    verifyOne(left, right, edges);
                    exhaustive++;
                }
            }
        }

        Random rng = new Random(3462026L);
        int seeded = 0;
        for (int left = 1; left <= 6; left++) {
            for (int trial = 0; trial < 200; trial++) {
                int right = rng.nextInt(6);
                int m = rng.nextInt(left * right + 6);
                List<Pair> edges = new ArrayList<>();
                for (int e = 0; e < m; e++) {
                    if (right > 0) {
                        edges.add(new Pair(
                                rng.nextInt(left), rng.nextInt(right)));
                    }
                }
                verifyOne(left, right, edges);
                seeded++;
            }
        }

        List<Pair> diagonal = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
            diagonal.add(new Pair(i, i));
            diagonal.add(new Pair(i, (i + 1) % 100));
        }
        if (solve(100, 100, diagonal).cardinality() != 100) {
            throw new AssertionError("larger perfect matching failed");
        }

        expectInvalid(() -> solve(-1, 1, List.of()));
        expectInvalid(() -> solve(1, -1, List.of()));
        expectInvalid(() -> solve(1001, 0, List.of()));
        expectInvalid(() -> solve(1, 1, null));
        expectInvalid(() -> solve(1, 1, List.of(new Pair(1, 0))));
        expectInvalid(() -> solve(1, 1, List.of(new Pair(0, -1))));
        expectInvalid(() -> solve(1, 1, Arrays.asList((Pair) null)));

        System.out.println("Exhaustive bipartite graphs: " + exhaustive + " PASS");
        System.out.println("Seeded multigraph inputs: " + seeded + " PASS");
        System.out.println("Perfect size-100 instance: PASS");
        System.out.println("Invalid-input checks: PASS");
    }

    public static void main(String[] args) {
        Result example = solve(2, 2, List.of(
                new Pair(0, 0), new Pair(0, 1), new Pair(1, 0)));
        System.out.println("Maximum matching size: " + example.cardinality());
        System.out.println("Matched pairs: " + example.pairs());
        System.out.println("Augmenting path 1: " + example.augmentingPaths().get(0));
        System.out.println("Augmenting path 2: " + example.augmentingPaths().get(1));
        System.out.println("Minimum cover L: " + example.leftCover());
        System.out.println("Minimum cover R: " + example.rightCover());
        System.out.println("Left-perfect: " + (example.cardinality() == 2));

        Result partial = solve(3, 2, List.of(
                new Pair(0, 0), new Pair(1, 0), new Pair(2, 1)));
        System.out.println("Partial matching: " + partial.pairs());
        System.out.println("Partial cover L/R: " +
                partial.leftCover() + " / " + partial.rightCover());
        System.out.println("Both-partitions-perfect: " +
                (partial.cardinality() == 3 && partial.cardinality() == 2));

        System.out.println("No edges: " + solve(2, 3, List.of()).cardinality());
        System.out.println("Empty left: " + solve(0, 3, List.of()).cardinality());
        System.out.println("Parallel duplicates: " + solve(1, 1,
                List.of(new Pair(0, 0), new Pair(0, 0))).cardinality());
        verify();
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac BipartiteMatchingAsFlow.java
java BipartiteMatchingAsFlow
~~~

**Stdout chính xác** của chương trình khi chạy thành công:

~~~text
Maximum matching size: 2
Matched pairs: [(0,1), (1,0)]
Augmenting path 1: [0, 1, 3, 5]
Augmenting path 2: [0, 2, 3, 1, 4, 5]
Minimum cover L: [0, 1]
Minimum cover R: []
Left-perfect: true
Partial matching: [(0,0), (2,1)]
Partial cover L/R: [2] / [0]
Both-partitions-perfect: false
No edges: 0
Empty left: 0
Parallel duplicates: 1
Exhaustive bipartite graphs: 5058 PASS
Seeded multigraph inputs: 1200 PASS
Perfect size-100 instance: PASS
Invalid-input checks: PASS
~~~

Ở phần đầu, luồng đầu tiên mang cặp L_0–R_0; đường tăng thứ hai đi qua cung residual ngược R_0→L_0, đổi cặp cũ thành L_0–R_1 rồi ghép L_1–R_0. Hai cặp cuối tương ứng hai cạnh L→R có luồng 1; các chỉ số 0–5 in trong đường tăng là **chỉ số của mạng**, không phải chỉ số riêng của từng phía.

## 23. Oracle độc lập: vét cạn tất cả matching nhỏ

Để tránh chỉ so max flow với một bản max flow khác có thể mắc cùng lỗi residual, code có hàm **bruteMatching** hoạt động trực tiếp trên ma trận cho phép allowed[i][j].

Quy trình quay lui:

~~~text
best(i, usedRight):
    Nếu i == a: trả 0.

    Phương án 1: bỏ qua L_i:
        answer = best(i+1, usedRight)

    Phương án 2: với mỗi R_j là hàng xóm của L_i,
                  và R_j chưa bị sử dụng:
        answer = max(answer,
                     1 + best(i+1, usedRight thêm j))

    Trả answer.
~~~

Với mỗi trái, oracle hoặc không ghép nó, hoặc ghép với **một** phải chưa dùng. Nó không dựa vào source, sink, residual hoặc BFS, nên logic độc lập với cách triển khai luồng.

Độ phức tạp quay lui có thể tăng theo cấp số mũ hoặc giai thừa theo kích thước đồ thị, vì vậy chỉ dùng cho input nhỏ. Trong bài chạy thực tế có n lớn, **không** dùng brute force làm thuật toán chính; nó là một công cụ kiểm thử đáng tin cậy.

Input trùng cặp được gom về giá trị boolean trong ma trận allowed, đúng theo nghĩa đồ thị tương thích: cùng một u–v xuất hiện hai lần không tạo khả năng ghép thêm người.

## 24. Oracle độc lập: vét cạn phủ đỉnh

Ngoài matching brute force, code còn tính **minimum vertex cover** mà không dùng công thức reachable.

Với a+b đỉnh, một bitmask có a+b bit biểu diễn một tập C bất kỳ. Tập ấy là cover hợp lệ khi với **mỗi cạnh (u,v)**, ít nhất một trong hai bit tương ứng u hoặc v được bật.

Pseudo-code:

~~~text
minCover = a+b

for mask từ 0 đến 2^(a+b)-1:
    nếu số bit bật >= minCover:
        bỏ qua vì không cải thiện được

    kiểm tra mọi cạnh (u,v):
        left u được chọn? hoặc right v được chọn?

    nếu mọi cạnh được phủ:
        minCover = số bit bật

return minCover
~~~

Đây là phép duyệt **tập đỉnh** khác hẳn bruteMatching vốn duyệt **lựa chọn ghép theo trái**. Hai oracle độc lập này còn xác nhận định lý Kőnig trên miền thử: khi thuật toán và cả hai oracle cùng trả cùng một giá trị, ta đã kiểm tra đồng thời luồng, matching và cover.

Không dùng oracle phủ đỉnh cho a+b lớn, vì nó tốn O(2^(a+b)·m) ở trường hợp xấu.

## 25. Vét cạn 5.058 đồ thị hai phía

Chương trình sinh **tất cả đồ thị hai phía đơn gắn nhãn** với a từ 0 đến 4 và b từ 0 đến 3. Với mỗi cặp (i,j) có một khả năng được thêm hoặc không được thêm; số đồ thị cho a,b cố định là 2^(a·b).

Tổng số trường hợp:

~~~text
a=0, b=0..3:  1+1+1+1            =    4.
a=1, b=0..3:  1+2+4+8            =   15.
a=2, b=0..3:  1+4+16+64          =   85.
a=3, b=0..3:  1+8+64+512         =  585.
a=4, b=0..3:  1+16+256+4096      = 4369.

Tổng = 4+15+85+585+4369 = 5058 đồ thị.
~~~

Với từng đồ thị, verifyOne kiểm tra:

- Cardinality bằng kết quả bruteMatching.
- Cardinality bằng minCover của oracle bitmask.
- Các cặp kết quả là cạnh có thật và không dùng trùng đỉnh trái/phải.
- Danh sách augmenting path bắt đầu tại s, kết thúc tại t, không lặp đỉnh.
- Mỗi lần tăng là một đơn vị trong mạng capacity 1 nên số đường bằng cardinality.
- Các đỉnh trích trong cover không bị lặp, và cover chạm được **mọi cạnh input**.

Vét cạn bao gồm đồ thị rỗng, đỉnh cô lập, chỉ một cạnh, cạnh tranh một đối tác, ghép hoàn hảo, ghép không hoàn hảo và nhiều matching tối ưu khác nhau. Mục đích không phải chọn một matching cố định duy nhất, mà kiểm tra mọi matching được trả **hợp lệ và đạt số cặp tối ưu**.

## 26. Kiểm thử 1.200 dữ liệu có cặp lặp và trường hợp biên

Mã dùng Random(3462026L), cho a từ 1 đến 6, mỗi a sinh 200 input, tổng **6×200=1.200 bộ**. Số lượng đỉnh phải b được chọn ngẫu nhiên từ 0 đến 5. Danh sách các cặp được tạo bằng việc chọn chỉ số trái/phải độc lập, vì thế có thể có **cặp lặp**, đỉnh cô lập hoặc hai phía kích thước chênh lệch.

Mỗi input được so với bruteMatching và bruteCover, và kiểm tra danh sách matching/cover như ở phần vét cạn. Việc cho phép cặp lặp là một kiểm tra quan trọng: dù có hai bản ghi (u,v), cách chọn tối ưu vẫn không cho phép dùng cùng u hoặc v hai lần.

Các thử nghiệm khác:

- **100 trái và 100 phải:** có ít nhất các cặp đường chéo (i,i), nên matching hoàn hảo kích thước 100. Mã còn thêm các cặp (i,(i+1) mod 100) để kiểm tra khi có nhiều lựa chọn.
- **Hai phía có thể rỗng hoặc không có cạnh:** matching size 0; cover rỗng.
- **Một cặp xuất hiện hai lần:** matching size 1, không phải 2.
- **Dữ liệu sai:** số lượng đỉnh âm, vượt giới hạn demo, danh sách null, cặp null và chỉ số vượt phạm vi phải bị từ chối.

Tổng có **5.058+1.200=6.258 bộ đồ thị/input** trong hai tập lớn, ngoài một số ca biên. Các kết quả PASS được in trong stdout đã được chạy; chúng là kiểm chứng triển khai chứ **không thay thế chứng minh** bằng tính tích phân luồng và định lý max-flow/min-cut.

## 27. Những lỗi phổ biến khi chuyển matching thành flow

1. **Không phân biệt L và R** khi đánh chỉ số, dẫn tới các cạnh sai phía hoặc xung đột ID.
2. **Đặt capacity s→L lớn hơn 1**, vô tình cho một người nhận nhiều công việc.
3. **Đặt capacity R→t lớn hơn 1**, cho một công việc nhận nhiều người trong matching chuẩn.
4. **Quên cạnh L→R cho một cặp hợp lệ**, khiến đáp án bị giảm.
5. **Thêm cạnh L→R cho một cặp không tương thích**, khiến đáp án giả tăng.
6. **Thêm cả hai hướng như cạnh gốc** vì nghĩ matching là vô hướng; sẽ thay đổi cấu trúc mạng và tính toán.
7. **Không thêm cung ngược residual**, không thể sửa ghép đã chọn.
8. **Coi cung dư ngược là cặp ghép có thật**, làm sai danh sách matching.
9. **Lấy các cặp của từng đường tăng lịch sử làm kết quả cuối**, quên đường sau có thể hủy cặp trước.
10. **Lấy mọi cạnh residual=0** kể cả s→L, R→t; chỉ được xét cạnh gốc giữa L và R.
11. **Không lưu tham chiếu Arc thuận** khi có cạnh trùng, đọc nhầm cung ngược hoặc bản ghi không còn luồng.
12. **Không reset seen/parentArc ở mỗi BFS**, gây bỏ sót đường tăng mới sau thay đổi residual.
13. **Nhầm maximal với maximum matching**, chấp nhận greedy mà không kiểm tra đường xen kẽ.
14. **Coi maximum cardinality đồng nghĩa max total weight**, dù bài có trọng số cặp khác nhau.
15. **Không nêu điều kiện luồng nguyên**, rồi rút matching từ một luồng phân số.
16. **Nhầm vertex cover với edge cover**, hai khái niệm không giống nhau.
17. **Áp dụng công thức phủ đỉnh theo reachable trước khi max flow kết thúc**, không có bảo đảm tối thiểu.
18. **Đổi vai L/R trong công thức cover**, đúng là L không reachable cộng R reachable.
19. **Giả định matching hoàn hảo chỉ vì số cặp bằng |R|**, khi |L|>|R| vẫn có trái chưa ghép.
20. **Dùng max flow đơn thuần cho phân công có chi phí**, thiếu cơ chế tối ưu chi phí.
21. **Duyệt tất cả bitmask cover trên input lớn**, dù oracle chỉ dành cho kiểm thử nhỏ.
22. **Lưu mọi đường augmenting path khi không cần**, gây tăng bộ nhớ tới O(KN).
23. **Không kiểm tra input L/R rỗng hoặc không có cạnh**, gây index lỗi dù đáp án hợp lệ là 0.
24. **Không làm rõ cặp trùng có phải một quan hệ hay nhiều khả năng vật lý**, khiến quy tắc nghiệp vụ và code không nhất quán.

## 28. Quy trình giải một bài matching bằng flow

1. Đọc đề và xác định **hai nhóm rời nhau** L, R, cùng **cạnh tương thích** giữa nhóm.
2. Phân biệt mục tiêu **tối đa số cặp** với các biến thể có chi phí, quota hay ưu tiên.
3. Chốt quy ước đánh số riêng trong L/R và đánh số đỉnh toàn mạng.
4. Dựng nguồn s, đích t, các cạnh **s→L capacity1**, **L→R capacity1**, **R→t capacity1**.
5. Tạo các cung residual thuận/ngược với liên kết đối ứng.
6. Chạy max flow đến khi **không còn đường tăng** trong residual network.
7. Lấy matching từ **những cạnh gốc L→R có flow=1**; xác minh không đỉnh nào được dùng hai lần.
8. Giá trị matching size bằng max flow; kiểm tra cận min(|L|,|R|).
9. Nếu cần phủ hết L, kiểm tra matchingSize==|L|; nếu cần perfect toàn bộ, yêu cầu thêm |L|=|R|.
10. Nếu cần **minimum vertex cover**, BFS reachable từ s trong residual cuối và lấy (L\Z_L)∪Z_R.
11. Nếu bài có trọng số/hạn mức, xem xét min-cost max-flow hoặc phiên bản có capacity phù hợp, không biến thể tùy tiện.
12. Kiểm tra ít nhất các ca: greedy sai, đỉnh cô lập, cạnh trùng, phía rỗng, matching hoàn hảo, matching không hoàn hảo.
13. Đối chiếu input nhỏ với brute-force matching/cover trước khi tối ưu theo kích cỡ lớn.

## 29. Bài tập tự luyện

**Bài 1 — Dựng mạng:** với L={A,B}, R={X,Y}, E={A–X,A–Y,B–X}, đánh ID s,L,R,t như mục 4, viết toàn bộ cạnh gốc và capacity. Đếm N và E' chính xác.

**Bài 2 — Chạy tay hai lần tăng:** bắt đầu f=0. Truy vết đường 0→1→3→5, cập nhật residual từng cung. Sau đó tìm đường 0→2→3→1→4→5 và xác định cạnh matching nào bị hủy.

**Bài 3 — Greedy phản ví dụ:** chọn A–X rồi thử ghép B. Vì sao greedy không đổi ghép trả 1, còn augmenting path trả 2? Phân biệt maximal và maximum.

**Bài 4 — Chứng minh giảm bài:** từ matching k cặp dựng luồng k. Từ luồng nguyên F trích matching F cặp. Nêu chính xác vai trò của ba loại capacity bằng 1.

**Bài 5 — Phủ đỉnh:** dùng mạng residual của ví dụ, lấy Z reachable, tính C=(L\Z_L)∪Z_R. Kiểm tra mỗi cạnh của đồ thị hai phía được C phủ và |C|=|M*|=2.

**Bài 6 — Không hoàn hảo:** cho L có 3 đỉnh, R có 2 đỉnh với các cạnh (0,0),(1,0),(2,1), tìm matching tối đa, phía nào còn đỉnh không ghép, và một minimum vertex cover. Dùng định lý Hall giải thích vì sao không thể phủ hết L.

**Bài 7 — Cạnh lặp:** thêm hai bản ghi giống nhau (L_0,R_0). Dựng hai cặp Arc residual riêng; chứng minh vẫn chỉ có thể ghép tối đa một cặp nhờ s→L_0 và R_0→t capacity1.

**Bài 8 — Đếm tổng số trường hợp:** với a≤4,b≤3, tự tính tổng 2^(a·b)=5.058. Chọn ngẫu nhiên vài case rồi so kết quả code với quay lui bruteMatching.

**Bài 9 — Mở rộng năng lực:** một giáo viên được hướng dẫn tối đa 3 sinh viên, mỗi sinh viên được một giáo viên. Chỉnh capacity **s→giáo viên** thành 3; các cạnh giáo viên→sinh viên và sinh viên→t là 1. Giải thích vì sao đây là **phân bổ có hạn mức**, không còn matching một–một.

**Bài 10 — Phân công có chi phí:** mỗi người–việc có cost khác nhau, yêu cầu tối đa số cặp rồi tối thiểu tổng cost. Phác thảo cách dùng **min-cost max-flow** với capacity1 và cost trên cạnh L→R; giải thích vì sao max flow thường không bảo đảm tiêu chí chi phí.

**Bài 11 — Tối ưu hiệu năng:** với a+b lớn, thử Hopcroft–Karp thay vì Edmonds–Karp, đối chiếu cùng số cặp và tính hợp lệ trên các case nhỏ. Đừng chỉ so danh sách matching vì có thể có nhiều đáp án tối ưu.

**Bài 12 — Không dùng trace:** chỉnh chương trình để chỉ trả maxMatching, các cặp đã chọn và minimum cover. So bộ nhớ với bản lưu mọi augmenting path khi K rất lớn.

**Kết luận:** bài toán **ghép cặp hai phía tối đa số cặp** có thể chuyển chính xác thành **max flow** bằng mạng bốn lớp s→L→R→t, tất cả capacity bằng 1. Mỗi matching tạo một luồng nguyên cùng giá trị, và mỗi luồng nguyên tạo lại một matching hợp lệ; vì vậy giá trị tối ưu của hai bài bằng nhau. **Cung dư ngược** cho phép hủy và đổi cặp cũ để vượt greedy, còn điều kiện không còn đường tăng bảo đảm tối ưu. Từ residual cuối, công thức **(L\Z_L)∪Z_R** trích phủ đỉnh nhỏ nhất và làm rõ định lý Kőnig. Đây là một phép quy đổi quan trọng để mở rộng từ phân công một–một sang các bài có hạn mức, ưu tiên và chi phí.
