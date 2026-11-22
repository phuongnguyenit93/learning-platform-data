# Phương pháp Ford–Fulkerson và ảnh hưởng của cách chọn đường

**Ford–Fulkerson** là một phương pháp cơ bản để tìm **luồng cực đại (maximum flow)** trong mạng có hướng và dung lượng cạnh không âm. Ý tưởng nghe rất đơn giản: bắt đầu với luồng 0, tìm một đường từ nguồn tới đích còn khả năng chuyển thêm luồng, tăng luồng dọc đường ấy, rồi lặp lại. Nhưng một chi tiết có ảnh hưởng lớn tới hiệu năng là **chọn đường tăng luồng (augmenting path) như thế nào**.

Bài học thuộc chủ đề cha **Luồng mạng** của Computer Science Algorithms, tập trung vào **“Phương pháp Ford–Fulkerson và ảnh hưởng của cách chọn đường”**. Ta sẽ xây mô hình luồng và đồ thị dư, giải thích cạnh ngược để hủy một phần quyết định trước đó, chứng minh thuật toán đúng bằng định lý **max-flow/min-cut**, so sánh đường tìm bằng **DFS** với **BFS của Edmonds–Karp**, phân tích ví dụ thực tế mà cả hai cho cùng đáp án nhưng khác số lần tăng, và dựng một họ ví dụ có thể khiến cách chọn đường tùy ý thực hiện **2K lần tăng thay vì 2 lần**.

Mã Java 17+ cuối bài có đủ hai chiến lược, truy vết từng đường và lượng luồng tăng, xuất chứng chỉ lát cắt nhỏ nhất, kiểm tra theo oracle **duyệt mọi lát cắt** trên 729 cấu hình dung lượng vét cạn và 1.200 mạng giả ngẫu nhiên.

## 1. Bài toán luồng cực đại là gì?

Cho một đồ thị có hướng G=(V,E) với **nguồn (source) s**, **đích (sink) t** khác nhau. Mỗi cạnh e=(u,v) có **dung lượng capacity c(e)≥0**. Mục tiêu tìm lượng luồng lớn nhất có thể chuyển từ s sang t, với hai điều kiện:

1. **Ràng buộc dung lượng:** 0≤f(e)≤c(e), nghĩa là trên mỗi cạnh vật lý lượng luồng không âm và không vượt mức cho phép.
2. **Bảo toàn luồng:** tại mỗi đỉnh v khác s,t, tổng luồng đi vào bằng tổng luồng đi ra.

Giá trị của luồng f bằng **luồng ròng** đi ra s: tổng các f(s,v) trừ tổng các f(u,s). Trong trạng thái hợp lệ, giá trị này cũng bằng luồng ròng đi vào t. Không bắt buộc một luồng chỉ đi theo các đường đơn s→t; trong mô hình tổng quát còn có thể có tuần hoàn luồng, dù thuật toán tăng đường bắt đầu từ 0 không cần chủ động tạo vòng có ích.

**Ví dụ mạng:**

~~~text
s = 0, a = 1, b = 2, t = 3

0 --4--> 1 --4--> 3
 \        |
  \       1
   \      v
    --4-->2 --4--> 3

Các cạnh vật lý theo thứ tự:
(0,1,4), (1,2,1), (2,3,4),
(1,3,4), (0,2,4).
~~~

Có thể gửi 4 đơn vị theo 0→1→3 và 4 đơn vị theo 0→2→3, tổng **8**. Tổng dung lượng hai cạnh rời nguồn 0 là 4+4=8, vì vậy không thể vượt 8. Ví dụ này sẽ cho thấy **cách chọn đường DFS có thể cần 4 lần tăng**, còn BFS chỉ cần 2, dù cả hai cùng tìm thấy luồng cực đại 8.

## 2. Đồ thị dư là gì?

Giả sử cạnh vật lý u→v có capacity c và hiện đang mang f đơn vị luồng. Đồ thị dư (*residual network*) có hai khả năng dịch chuyển:

~~~text
u -> v có dung lượng dư (forward residual) = c - f.
v -> u có dung lượng dư (backward residual) = f.
~~~

Cung thuận cho phép **gửi thêm luồng** trên cạnh gốc. Cung ngược cho phép **rút bớt một phần luồng đã gửi trước đó**, nghĩa là hoàn tác một quyết định cũ để mở đường phân phối khác. Ban đầu f=0 nên cung thuận có dư c và cung ngược có dư 0.

Ví dụ cạnh vật lý 1→2 có c=1. Sau khi gửi 1 đơn vị từ 1 tới 2, cung thuận 1→2 có dư 0 và cung ngược 2→1 có dư 1. Lúc này một đường tăng luồng có thể **đi 2→1 trên cung ngược** để hủy 1 đơn vị từng đi 1→2. Đây **không phải cạnh mới** trong input: nó đại diện cho khả năng hoàn tác luồng.

**Nguyên tắc:** mọi lần tìm đường phải diễn ra trên **đồ thị dư hiện thời**, không phải chỉ trên cạnh gốc và cũng không chỉ những cạnh gốc còn capacity. Không có cung ngược, một lựa chọn sớm không tốt có thể làm thuật toán lầm tưởng đã hết đường tới t dù có thể sắp xếp lại luồng.

## 3. Cách biểu diễn cung thuận và cung ngược

Với mỗi cạnh vật lý InputEdge(u,v,c), tạo **hai đối tượng cung dư**:

~~~text
forward:  from=u, to=v, residual=c
backward: from=v, to=u, residual=0

forward.reverse = backward
backward.reverse = forward
~~~

Nếu đi qua một cung dư a theo chiều đang chọn và tăng lượng Δ, cập nhật:

~~~text
a.residual -= Δ
a.reverse.residual += Δ
~~~

Nhờ con trỏ reverse trỏ **đúng đối tượng cung đối ứng**, thuật toán không nhầm khi input chứa:

- **Cạnh song song:** nhiều cạnh u→v khác ID; mỗi cạnh có cặp cung dư riêng.
- **Cạnh ngược chiều có thật:** input đồng thời có u→v và v→u; hai cạnh thật này vẫn có **hai cặp cung dư độc lập**, không được trộn cung ngược ảo của cạnh thứ nhất với cạnh thuận thật của cạnh thứ hai.
- **Self-loop:** cạnh u→u có thể có trong input; nó không giúp tăng luồng s→t trên đường đơn, nhưng hai cung của riêng cạnh đó vẫn được ghép đối ứng. Chương trình Java giữ riêng hai đối tượng và dùng visited khi tìm đường để không tự đi vòng qua một đỉnh.

Bảo đảm mỗi cung biết chính xác cung reverse của nó giúp phép cập nhật **O(1) mỗi cạnh trên đường**, bất kể thứ tự cạnh trong danh sách kề.

## 4. Đường tăng luồng và lượng nghẽn cổ chai

Một **augmenting path P** là một đường từ s tới t trong đồ thị dư, trong đó tất cả cung trên đường có residual **dương**. Lượng có thể tăng mà không vi phạm capacity là:

~~~text
Δ = min(residual(e)) với e nằm trên P.
~~~

Giá trị Δ được gọi là **bottleneck** hoặc dung lượng cổ chai. Ta giảm residual của từng cung trong đường đi Δ và tăng residual của cung ngược tương ứng Δ. Kết quả là **giá trị luồng toàn mạng tăng đúng Δ**.

Trong ví dụ 0→1→2→3 với các dung lượng 4,1,4, ta có Δ=min(4,1,4)=1. Sau lần tăng đó:

~~~text
Residual 0->1 giảm từ 4 xuống 3.
Residual 1->2 giảm từ 1 xuống 0.
Residual 2->3 giảm từ 4 xuống 3.

Các cung ngược 1->0, 2->1, 3->2 tăng thêm 1.
Giá trị luồng tăng từ 0 lên 1.
~~~

Bottleneck của đường đi quyết định số lượng tăng, không phải số cạnh trên đường. Một đường rất ngắn có thể bị nghẽn ở capacity nhỏ, và một đường nhiều cạnh có thể mang lượng lớn; **BFS chọn ít cạnh nhất**, chứ không nhất thiết chọn đường có bottleneck lớn nhất.

## 5. Thuật toán Ford–Fulkerson tổng quát

Pseudo-code:

~~~text
Khởi tạo f(e)=0 với mọi cạnh gốc e.
Xây residual graph với forward residual=c và backward residual=0.

repeat:
    P = tìm một đường s -> t chỉ dùng cung dư residual>0
    nếu không có P: dừng
    Δ = min residual của các cung trên P
    với mỗi cung a thuộc P:
        a.residual -= Δ
        a.reverse.residual += Δ
    tổng giá trị luồng += Δ

Kết quả: giá trị luồng và đồ thị dư cuối.
~~~

Điểm mấu chốt: **Ford–Fulkerson không chỉ định cách chọn P**. Nó là một khung thuật toán (*method*). Ta có thể dùng DFS để tìm đường bất kỳ, BFS để tìm đường ngắn nhất theo số cạnh, hay một chiến lược hợp lệ khác. **Tính đúng khi phương pháp dừng vì không còn đường tăng** không phụ thuộc việc đã chọn đường nào, nhưng **số lần tăng và khả năng bảo đảm dừng** có thể phụ thuộc mạnh vào lựa chọn này và loại dung lượng.

Không nhầm tên **Ford–Fulkerson** với **Edmonds–Karp**: Edmonds–Karp là biến thể cụ thể luôn chọn đường tăng bằng **BFS** trong đồ thị dư.

## 6. Vì sao tăng theo đường vẫn giữ luồng hợp lệ?

Xét một lần tăng Δ trên đường dư s→t. Với mỗi cạnh vật lý, ta có thể diễn giải cung thuận là **tăng f** và cung ngược là **giảm f**. Bởi Δ không vượt residual của bất kỳ cung nào, các giá trị mới vẫn nằm trong [0,c]:

- Nếu đi trên cung thuận, Δ≤c−f nên f+Δ≤c.
- Nếu đi trên cung ngược, Δ≤f nên f−Δ≥0.

Tại mỗi đỉnh **nội bộ của đường**, đường nhận Δ qua một cung và đưa Δ ra qua cung tiếp theo. Dù những cung đó có thể là cung ngược của cạnh gốc, thay đổi **luồng ròng** tại đỉnh vẫn bằng 0. Vì vậy bảo toàn luồng không bị phá.

Tại s, luồng ròng ra tăng Δ; tại t, luồng ròng vào tăng Δ. Do đó giá trị luồng tăng Δ dương. Khởi tạo f=0 hợp lệ; phép tăng giữ hợp lệ; suy ra **mọi trạng thái trong quá trình chạy đều là luồng khả thi**.

Đó là bất biến nền tảng dùng trong chứng minh thuật toán tìm luồng cực đại.

## 7. Chạy ví dụ bằng DFS-first

Trên mạng bốn đỉnh ở mục 1, nếu adjacency giữ đúng thứ tự cạnh input và DFS duyệt theo thứ tự đó, các đường tăng được tìm như sau:

| Lượt | Đường tăng DFS | Δ | Luồng tích lũy |
| ---: | --- | ---: | ---: |
| 1 | 0→1→2→3 | 1 | 1 |
| 2 | 0→1→3 | 3 | 4 |
| 3 | 0→2→1→3 | 1 | 5 |
| 4 | 0→2→3 | 3 | 8 |

Lượt 1 đi qua cạnh hẹp 1→2 capacity 1, nên chỉ tăng được 1 dù các tuyến ngoài đều có capacity 4. Lượt 2 dùng 3 đơn vị còn lại của 0→1, nhưng cạnh 1→3 vẫn còn dư 1.

Lượt 3 dùng đường **0→2→1→3**, trong đó cung **2→1 là cung dư ngược** của cạnh gốc 1→2. Việc chuyển 1 đơn vị qua cung này **hủy luồng 1→2 trước đó**. Kết quả thực chất được điều chỉnh lại để dùng các tuyến 0→1→3 và 0→2→3 tối ưu.

Lượt 4 đẩy nốt 3 đơn vị qua 0→2→3. Tổng cuối bằng **8**, nhưng phải trải qua **4 lần tăng**. Từ đây không còn đường dư từ s=0 tới t=3.

**Lưu ý:** đường DFS đầu tiên phụ thuộc thứ tự adjacency; đổi thứ tự cạnh có thể tạo thứ tự tăng và số lượt khác. Mã không khẳng định “DFS luôn mất bốn lượt” trên mọi cách lưu cùng mạng.

## 8. Cùng mạng, BFS chỉ cần hai lượt

Nếu dùng **BFS** trên đồ thị dư, đường tăng trước tiên có ít cạnh nhất. Ở lượt đầu mạng có các đường dài 2 cạnh:

~~~text
0 -> 1 -> 3, bottleneck=4.
0 -> 2 -> 3, bottleneck=4.
~~~

BFS có thể chọn 0→1→3 trước, gửi 4; lượt kế chọn 0→2→3, gửi 4. Khi đó:

| Lượt | Đường BFS | Δ | Luồng tích lũy |
| ---: | --- | ---: | ---: |
| 1 | 0→1→3 | 4 | 4 |
| 2 | 0→2→3 | 4 | 8 |

Cả DFS và BFS **đều trả 8** và cùng chứng minh được lát cắt nhỏ nhất có capacity 8. Khác biệt là **số lần tăng** (DFS 4, BFS 2) và lượng tăng trên mỗi đường.

BFS chọn đường **ngắn nhất theo số cạnh**, không phải theo trọng số đường, tổng capacity, hay bottleneck. Đường có ít cạnh thường phù hợp để kiểm soát số lần tăng theo lý thuyết Edmonds–Karp, nhưng không có định lý nói BFS sẽ luôn có **số lần tăng ít nhất tuyệt đối** trong mọi mạng.

## 9. Cạnh ngược là cơ chế hủy lựa chọn sai, không phải sai sót

Trong ví dụ, ban đầu cạnh gốc 1→2 có c=1, f=0. Sau lượt 1 (0→1→2→3):

~~~text
Trên cạnh gốc 1->2:
    f = 1.
    forward residual(1->2) = 0.
    backward residual(2->1) = 1.
~~~

Đến lượt 3, dùng cung 2→1 với Δ=1. Cập nhật:

~~~text
backward residual(2->1): 1 -> 0.
forward residual(1->2):  0 -> 1.
luồng gốc 1->2:          1 -> 0.
~~~

Nếu không tạo cung 2→1 hoặc cấm tìm đường qua cung ấy, ta có thể không thấy cách **đổi phân phối luồng** hợp lệ để đạt giá trị tối ưu. Đây là tính năng thiết yếu của Ford–Fulkerson, không phải “đi ngược hướng mạng” trong thực tế.

Với hai cạnh vật lý ngược chiều có thật, cần phân biệt: một cung dư 2→1 có thể là **cung thuận** của một cạnh gốc 2→1, hoặc **cung ngược** thuộc một cạnh gốc 1→2. Chỉ thao tác trên đúng cặp forward/reverse của từng cạnh gốc mới bảo toàn phép cập nhật.

## 10. Một họ ví dụ: chọn đường cực tệ có thể cần 2K lượt

Xét mạng có bốn đỉnh s,a,b,t, các cạnh:

~~~text
s -> a: K
s -> b: K
a -> t: K
b -> t: K
a -> b: 1

K là số nguyên dương.
~~~

Hai đường ngắn s→a→t và s→b→t mỗi đường mang được K. Chọn chúng có thể hoàn tất chỉ trong **2 lần tăng**, cho tổng 2K.

Nhưng **một chiến lược chọn đường hợp lệ mà rất tệ** có thể làm:

~~~text
Lượt lẻ:  s -> a -> b -> t, Δ=1.
Lượt chẵn: s -> b -> a -> t, Δ=1,
           dùng cung dư ngược b->a của cạnh gốc a->b.

Lặp lại cặp lượt này K lần.
Tổng số lần tăng = 2K.
Giá trị luồng cuối = 2K.
~~~

Sau mỗi cặp lượt, luồng đi qua a→b được hủy về 0, trong khi capacity trên bốn cạnh ngoài giảm mỗi cạnh đúng 1. Vì vậy cùng lựa chọn zigzag có thể được lặp lại K lần. Với K=1.000.000, chiến lược tệ tạo **2.000.000 lần tăng**, dù có nghiệm hai đường rất đơn giản.

**Đây là ví dụ về quyền tự chọn đường của Ford–Fulkerson**, không phải khẳng định một DFS cụ thể nào với mọi thứ tự kề sẽ tự sinh đúng chuỗi tệ này. Nó giải thích vì sao không thể chỉ nhìn n,m và kết luận phiên bản chọn đường tùy ý chạy thời gian đa thức theo độ dài input.

## 11. Cài DFS tìm đường: đơn giản nhưng thứ tự cạnh quan trọng

Một biến thể chọn đường là duyệt sâu **DFS** trên đồ thị dư, chỉ qua cung có residual>0. Khi thăm một đỉnh v:

~~~text
visited[v] = true
for mỗi cung dư a: v -> w theo thứ tự adjacency:
    nếu a.residual <= 0 hoặc visited[w]: bỏ qua
    ghi parentArc[w] = a
    đi sâu vào w
    nếu tìm thấy sink: dừng và truy vết
~~~

DFS thường dễ cài đặt; tuy nhiên lựa chọn tìm được phụ thuộc cách sắp thứ tự cung, gồm cả cung ngược được thêm trong quá trình tạo mạng. Chỉ số đỉnh nhỏ hơn **không nhất thiết** được xét trước trừ khi người viết cố ý sắp adjacency.

Mã Java dùng **DFS lặp bằng stack và nextNeighbor[v]** để mô phỏng đường DFS đệ quy, tránh StackOverflowError ở mạng có đường đi dài. Mỗi lần tìm đường tạo mảng visited **mới**. Không được giữ visited cũ sau một lần tăng vì cung dư thay đổi, và trước đó một đỉnh không vào được từ s có thể trở thành vào được sau điều chỉnh luồng.

Tìm đường DFS hết mọi khả năng mà không tới t có nghĩa **không còn đường tăng** trong residual graph hiện tại. Khi đó không chạy lại với cùng trạng thái mà hy vọng “lần sau may mắn hơn”: đã tới điều kiện dừng tối ưu.

## 12. Edmonds–Karp: BFS tìm đường ngắn nhất theo số cạnh

Thay DFS bằng **BFS** trên đồ thị dư. Khởi tạo queue với s, đánh dấu visited[s], sau đó mở rộng các cung dư có residual dương. Khi lần đầu gặp t, parentArc cho phép dựng một đường tăng ít cạnh nhất.

Điều này mang lại một bảo đảm hiệu năng mạnh: số cạnh trên đường tăng được chọn bởi BFS **không giảm** theo các lần tăng. Sau một cạnh dư bị nghẽn và được sử dụng lại theo hướng tương tự trong một đường tăng sau đó, độ dài đường từ s đến đầu cạnh đó phải tăng đủ để không lặp hiện tượng quá nhiều lần.

Phân tích chuẩn cho thấy **mỗi cung dư chỉ có thể là cạnh nghẽn với số lần O(V)** theo nghĩa thích hợp, nên tổng số lượt tăng là **O(VE)**, với V=n và E=m là số đỉnh/cạnh gốc. Mỗi lần tìm đường BFS trên danh sách kề tốn O(V+E) và trên mạng có các đỉnh hữu ích liên thông được phân tích bằng O(E) theo quy ước chuẩn; hệ quả quen thuộc là **Edmonds–Karp O(VE²) thời gian**, không phụ thuộc giá trị số của các capacity.

Đây là biến thể có **bảo đảm đa thức** dù dung lượng rất lớn hoặc là số thực hợp lệ trong mô hình số học chính xác. Mã Java dùng long, nên không xử lý trực tiếp số thực và chủ động kiểm soát tràn số.

## 13. Phân tích DFS Ford–Fulkerson với dung lượng nguyên

Giả sử mọi dung lượng là **số nguyên không âm** và bắt đầu từ luồng nguyên 0. Sau mỗi lần tăng, tất cả residual vẫn nguyên, bottleneck Δ là một **số nguyên dương** nên ít nhất bằng 1.

Nếu giá trị luồng cực đại là F (số nguyên), tổng số lượt tăng **không vượt F** vì mỗi lượt tăng giá trị luồng ít nhất 1. Nếu mỗi lần tìm đường và cập nhật tốn O(V+E), ta có cận:

~~~text
Ford–Fulkerson chọn đường tùy ý với capacity nguyên:
  số lượt tăng <= F.
  thời gian O((V+E) * F).

Khi chỉ xét phần mạng liên thông hữu ích thường viết O(E*F).
~~~

Cận này là **giả đa thức (pseudo-polynomial)**: F có thể rất lớn trong khi số bit biểu diễn F chỉ tăng theo log F. Ví dụ K=1.000.000 có thể được ghi bằng rất ít chữ số, nhưng chiến lược zigzag nêu ở trên cần O(K) lần tăng.

Nếu mọi capacity là số hữu tỉ, có thể nhân với mẫu số chung để phân tích dạng nguyên, nhưng mẫu số chung có thể cực lớn so với độ dài input. Với capacity **vô tỉ**, Ford–Fulkerson chọn đường tùy ý có thể có những chuỗi tăng **không kết thúc** (nontermination) trong mô hình số học thực; do đó không thể chứng minh dừng chỉ bằng lập luận “đường tăng luôn dương”. Edmonds–Karp khắc phục vấn đề **chọn đường** bằng bảo đảm số lần tăng đa thức.

## 14. Vì sao không thể tính đúng bằng cách cấm các cung ngược?

Xét lại ví dụ 0→1→2→3 được chọn ban đầu. Nếu chỉ duyệt **các cạnh gốc còn dư theo hướng thuận**, sau một số lựa chọn sai, phần luồng đang ở cạnh 1→2 không được phép hoàn tác, và những đường bổ sung cần điều chỉnh phân phối có thể bị khóa.

Mô hình residual được xây dựng nhằm giữ **tất cả biến đổi cục bộ vẫn tạo một luồng hợp lệ**. Bất kỳ đường dư nào (kể cả cung ngược) đều chuyển từ một luồng khả thi sang một luồng khả thi có giá trị lớn hơn. Bỏ những cung ngược tương đương loại bỏ một số biến đổi hợp lệ, nên cách dừng “không có đường thuận” **không tương đương** điều kiện tối ưu của Ford–Fulkerson.

Nếu muốn chứng minh đã tối ưu, phải xác nhận **không còn đường s→t trong đồ thị dư đầy đủ** — cả cung thuận dư lẫn cung ngược dư.

## 15. Định lý max-flow/min-cut và chứng chỉ kết quả

Một **lát cắt s–t (s–t cut)** là phân hoạch V thành S và T=V\S sao cho s thuộc S và t thuộc T. **Dung lượng lát cắt**:

~~~text
capacity(S,T) = Σ capacity(u,v),
                  với u thuộc S, v thuộc T.
~~~

Chỉ tính **các cạnh gốc có hướng đi từ S sang T**; không cộng cạnh đi T→S khi tính capacity của lát cắt có hướng. Mọi luồng khả thi luôn có giá trị **không vượt capacity(S,T)** cho mọi lát cắt, vì luồng ròng qua cắt bằng tổng dòng S→T trừ dòng T→S.

Sau khi thuật toán dừng, lấy S là tập đỉnh vẫn **đi tới được từ s qua các cung dư có residual dương**. Vì không còn đường dư s→t, t không thuộc S. Mọi cung dư đi ra khỏi S đều đã có residual bằng 0.

Với mỗi cạnh gốc u→v đi từ S sang T, residual thuận bằng 0 nên luồng trên cạnh đã **bão hòa: f=c**. Với mỗi cạnh gốc đi từ T về S, residual ngược đi từ S về T bằng 0 nên luồng trên cạnh gốc phải bằng **0**. Bởi vậy luồng ròng qua lát cắt bằng đúng tổng capacity của các cạnh S→T:

~~~text
value(flow) = capacity(S,T).
~~~

Ta vừa có một luồng khả thi đạt **cận trên của mọi luồng khả thi**, nên đó là **luồng cực đại**; lát cắt là **lát cắt nhỏ nhất**. Đây là nội dung cốt lõi của định lý **max-flow/min-cut** và giải thích vì sao điều kiện dừng **không có đường tăng** là chính xác.

## 16. Trích lát cắt sau khi chạy

Sau khi tìm được luồng cực đại:

1. Từ s, BFS/DFS theo **những cung dư có residual>0**.
2. Ghi tập S gồm tất cả đỉnh reachable.
3. Đảm bảo t không thuộc S.
4. Duyệt **danh sách cạnh vật lý đầu vào**; nếu cạnh u→v có u∈S, v∉S thì cộng capacity của nó.
5. Kiểm tra tổng capacity vừa tính bằng giá trị maxFlow.

Trên mạng ví dụ, sau khi đạt flow=8, cả 0→1 lẫn 0→2 đều bão hòa, nên chỉ có nguồn 0 reachable từ 0 trên đồ thị dư:

~~~text
S = {0}, T = {1,2,3}.

Các cạnh của lát cắt đi S -> T:
0 -> 1, capacity 4.
0 -> 2, capacity 4.

capacity(S,T) = 4+4=8=maxFlow.
~~~

Việc kiểm tra cả maxFlow và cutCapacity tạo một **chứng chỉ tối ưu** độc lập tương đối với thứ tự đường tăng, và chương trình in chúng cùng tập đỉnh phía nguồn.

## 17. Một lưu ý về cạnh song song, cạnh hai chiều và self-loop

Dù ví dụ chính chỉ có năm cạnh khác đầu mút, một triển khai tổng quát cần bảo toàn **từng cạnh vật lý**:

- **Cạnh song song u→v:** phải cộng đúng từng capacity khi tính lát cắt; mỗi cạnh có cặp residual riêng.
- **Có hai cạnh vật lý u→v và v→u:** không được dùng một cung ngược giả đại diện luôn cho cạnh ngược có thật; mỗi cạnh có thể đồng thời có luồng riêng theo hướng của nó.
- **Khuyên u→u:** không đi qua từ S tới T vì hai đầu luôn cùng một phía, nên không đóng góp dung lượng lát cắt. Với tìm đường không lặp đỉnh, khuyên không tạo đường tăng s→t hữu ích.
- **Cạnh capacity=0:** giữ trong danh sách input là được, nhưng tìm đường phải bỏ qua cung có residual≤0.
- **Nguồn hoặc đích có thể nằm giữa các cạnh khác:** định nghĩa luồng ròng vẫn đúng; không cần cấm cạnh vào s hoặc ra t. Phương pháp đường tăng trên residual vẫn có hiệu lực.

Khi dựng Graph, mã Java dùng hai đối tượng Arc ghép với nhau bằng con trỏ reverse, xử lý các trường hợp trên mà không phụ thuộc việc đầu mút có trùng nhau hay không.

## 18. Lỗi tràn số và chi phí lưu mọi đường tăng

Java dùng **long** làm dung lượng, vì tổng luồng có thể lớn hơn giới hạn int. Mỗi lần cập nhật, mã dùng Math.addExact cho tổng luồng và dung lượng dư tăng thêm. Nếu tổng vượt giới hạn long, chương trình ném ArithmeticException thay vì tự bọc số âm thành một kết quả có vẻ hợp lệ. Với dữ liệu có bound rất lớn, cần đảm bảo tổng tối đa có thể biểu diễn được, hoặc dùng BigInteger với triển khai riêng.

Mã lưu cả **danh sách Step** của mọi đường tăng để phục vụ giảng giải và in kết quả. Chi phí ghi trace có thể tới O(A·V), với A là số lần tăng, vì mỗi đường có tối đa V đỉnh. Đây là **chi phí tùy chọn của demo**, không phải phần bắt buộc của Ford–Fulkerson hay Edmonds–Karp. Trong hệ thống lớn, chỉ giữ giá trị luồng cuối và chứng chỉ lát cắt, hoặc ghi log có giới hạn, để tránh sử dụng quá nhiều bộ nhớ.

Một Network sau khi gọi solve đã bị **thay đổi trạng thái residual**. Để so sánh hai chiến lược độc lập, phải **tạo hai Network mới từ cùng danh sách cạnh gốc**. Mã minh họa làm đúng điều này qua hàm build; gọi hai lần solve trên cùng một instance đã được dùng để tìm max flow không phải hai thí nghiệm cùng điểm xuất phát.

## 19. Java 17+: thực hiện cả DFS-first và Edmonds–Karp

Tệp **FordFulkersonPathChoice.java** cung cấp:

- InputEdge(from,to,capacity): một cạnh vật lý có hướng.
- Network.addEdge: tạo cung residual thuận và ngược, liên kết chúng trực tiếp.
- Network.solve(s,t,Choice.DFS_FIRST): chọn đường tăng bằng DFS lặp với con trỏ cạnh kề, dễ bị ảnh hưởng thứ tự cung.
- Network.solve(s,t,Choice.BFS_SHORTEST): chọn đường ngắn nhất theo **số cạnh residual** bằng BFS — biến thể Edmonds–Karp.
- Step(vertices,increase): đường tăng và bottleneck từng lần.
- Result(maxFlow,minCut,sourceSide,steps): giá trị luồng cực đại, dung lượng lát cắt, phía nguồn và trace.
- enumerateMinCut: oracle duyệt mọi phân hoạch s–t trên đồ thị nhỏ, không dùng cùng thuật toán đường tăng.
- verify: nhiều capacity assignments vét cạn, đồ thị có hướng ngẫu nhiên có seed, capacity lớn và các input lỗi.

**Hợp đồng:** mạng có n≥2 đỉnh đánh số 0..n−1, s≠t, capacity kiểu long **không âm**, cạnh song song/cạnh ngược chiều/self-loop được phép. Với mạng không có đường từ s tới t, đáp án flow=0. Gọi solve trên **một Network mới** cho mỗi thí nghiệm; phương thức này thay đổi residual tại chỗ. Không dùng dung lượng âm để mô phỏng cung ngược; cung ngược có residual dương được tạo **động bởi thuật toán** khi luồng đã đi qua cạnh gốc.

DFS dùng stack lặp, không đệ quy; BFS dùng ArrayDeque. Mã hiện thực yêu cầu được gọi với Choice hợp lệ, từ chối source==sink và chỉ số đỉnh sai. Trên mạng lớn, nếu cần tốc độ vượt Edmonds–Karp, xem thêm thuật toán Dinic với **level graph và blocking flow**; đó là thuật toán khác, không phải chỉ thay DFS bằng BFS trong một lần.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;

public final class FordFulkersonPathChoice {
    public enum Choice { DFS_FIRST, BFS_SHORTEST }
    public record InputEdge(int from, int to, long capacity) { }
    public record Step(List<Integer> vertices, long increase) {
        public Step {
            vertices = List.copyOf(vertices);
            if (increase <= 0) throw new IllegalArgumentException("nonpositive increase");
        }
    }
    public record Result(long maxFlow, long minCut,
                         boolean[] sourceSide, List<Step> steps) {
        public Result {
            sourceSide = sourceSide.clone();
            steps = List.copyOf(steps);
        }
        @Override public boolean[] sourceSide() { return sourceSide.clone(); }
    }
    private static final class Arc {
        final int from;
        final int to;
        long residual;
        Arc reverse;
        Arc(int from, int to, long residual) {
            this.from = from;
            this.to = to;
            this.residual = residual;
        }
    }
    public static final class Network {
        private final int n;
        private final List<List<Arc>> adjacency;
        private final List<InputEdge> originals = new ArrayList<>();
        public Network(int n) {
            if (n < 2) throw new IllegalArgumentException("n must be >= 2");
            this.n = n;
            adjacency = new ArrayList<>();
            for (int i = 0; i < n; i++) adjacency.add(new ArrayList<>());
        }
        public void addEdge(int from, int to, long capacity) {
            if (from < 0 || from >= n || to < 0 || to >= n || capacity < 0) {
                throw new IllegalArgumentException("invalid directed edge");
            }
            Arc forward = new Arc(from, to, capacity);
            Arc backward = new Arc(to, from, 0);
            forward.reverse = backward;
            backward.reverse = forward;
            adjacency.get(from).add(forward);
            adjacency.get(to).add(backward);
            originals.add(new InputEdge(from, to, capacity));
        }
        private boolean findDfs(int source, int sink, Arc[] parent) {
            boolean[] visited = new boolean[n];
            int[] next = new int[n];
            ArrayDeque<Integer> stack = new ArrayDeque<>();
            visited[source] = true;
            stack.push(source);
            while (!stack.isEmpty()) {
                int u = stack.peek();
                if (u == sink) return true;
                if (next[u] == adjacency.get(u).size()) {
                    stack.pop();
                    continue;
                }
                Arc arc = adjacency.get(u).get(next[u]++);
                if (arc.residual > 0 && !visited[arc.to]) {
                    visited[arc.to] = true;
                    parent[arc.to] = arc;
                    stack.push(arc.to);
                }
            }
            return false;
        }
        private boolean findBfs(int source, int sink, Arc[] parent) {
            boolean[] visited = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.add(source);
            visited[source] = true;
            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (Arc arc : adjacency.get(u)) {
                    if (arc.residual <= 0 || visited[arc.to]) continue;
                    visited[arc.to] = true;
                    parent[arc.to] = arc;
                    if (arc.to == sink) return true;
                    queue.add(arc.to);
                }
            }
            return false;
        }
        private boolean[] reachable(int source) {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[source] = true;
            queue.add(source);
            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (Arc arc : adjacency.get(u)) {
                    if (arc.residual > 0 && !seen[arc.to]) {
                        seen[arc.to] = true;
                        queue.add(arc.to);
                    }
                }
            }
            return seen;
        }
        public Result solve(int source, int sink, Choice choice) {
            if (source < 0 || source >= n || sink < 0 || sink >= n
                    || source == sink || choice == null) {
                throw new IllegalArgumentException("invalid terminals/choice");
            }
            long flow = 0;
            List<Step> trace = new ArrayList<>();
            while (true) {
                Arc[] parent = new Arc[n];
                boolean found = choice == Choice.DFS_FIRST
                        ? findDfs(source, sink, parent)
                        : findBfs(source, sink, parent);
                if (!found) break;
                long delta = Long.MAX_VALUE;
                ArrayList<Integer> route = new ArrayList<>();
                int at = sink;
                route.add(at);
                while (at != source) {
                    Arc e = parent[at];
                    if (e == null || e.residual <= 0) {
                        throw new AssertionError("invalid augmenting path");
                    }
                    delta = Math.min(delta, e.residual);
                    at = e.from;
                    route.add(at);
                }
                Collections.reverse(route);
                long newFlow = Math.addExact(flow, delta);
                for (int v = sink; v != source; ) {
                    Arc e = parent[v];
                    e.residual -= delta;
                    e.reverse.residual =
                            Math.addExact(e.reverse.residual, delta);
                    v = e.from;
                }
                flow = newFlow;
                trace.add(new Step(route, delta));
            }
            boolean[] sourceSide = reachable(source);
            long cutCapacity = 0;
            for (InputEdge e : originals) {
                if (sourceSide[e.from()] && !sourceSide[e.to()]) {
                    cutCapacity = Math.addExact(cutCapacity, e.capacity());
                }
            }
            if (sourceSide[sink] || cutCapacity != flow) {
                throw new AssertionError("max-flow/min-cut invariant broken");
            }
            return new Result(flow, cutCapacity, sourceSide, trace);
        }
    }

    private static Network build(int n, List<InputEdge> edges) {
        Network network = new Network(n);
        for (InputEdge e : edges) {
            network.addEdge(e.from(), e.to(), e.capacity());
        }
        return network;
    }

    private static long enumerateMinCut(int n, List<InputEdge> edges,
                                        int source, int sink) {
        long optimum = Long.MAX_VALUE;
        for (int mask = 0; mask < (1 << n); mask++) {
            if ((mask & (1 << source)) == 0 ||
                    (mask & (1 << sink)) != 0) continue;
            long sum = 0;
            for (InputEdge e : edges) {
                boolean fromInside = (mask & (1 << e.from())) != 0;
                boolean toInside = (mask & (1 << e.to())) != 0;
                if (fromInside && !toInside) {
                    sum = Math.addExact(sum, e.capacity());
                }
            }
            optimum = Math.min(optimum, sum);
        }
        return optimum;
    }

    private static void check(int n, List<InputEdge> edges) {
        long expected = enumerateMinCut(n, edges, 0, n - 1);
        for (Choice choice : Choice.values()) {
            Result result = build(n, edges).solve(0, n - 1, choice);
            if (result.maxFlow() != expected || result.minCut() != expected) {
                throw new AssertionError("incorrect flow " + choice + ": " + edges);
            }
            long added = 0;
            for (Step step : result.steps()) {
                if (step.vertices().size() < 2 ||
                        step.vertices().get(0) != 0 ||
                        step.vertices().get(step.vertices().size() - 1) != n - 1 ||
                        step.increase() <= 0) {
                    throw new AssertionError("bad augmenting-path trace");
                }
                added = Math.addExact(added, step.increase());
            }
            if (added != expected) {
                throw new AssertionError("augmentation sum mismatch");
            }
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException correct) {
            return;
        }
        throw new AssertionError("invalid arguments accepted");
    }

    private static void verify() {
        InputEdge[] arcs = {
                new InputEdge(0, 1, 0), new InputEdge(1, 3, 0),
                new InputEdge(0, 2, 0), new InputEdge(2, 3, 0),
                new InputEdge(1, 2, 0), new InputEdge(2, 1, 0)
        };
        int exhaustive = 0;
        for (int code = 0; code < 729; code++) {
            int rest = code;
            List<InputEdge> edges = new ArrayList<>();
            for (InputEdge arc : arcs) {
                int capacity = rest % 3;
                rest /= 3;
                edges.add(new InputEdge(arc.from(), arc.to(), capacity));
            }
            check(4, edges);
            exhaustive++;
        }
        Random random = new Random(3302026L);
        int seeded = 0;
        for (int n = 2; n <= 7; n++) {
            for (int trial = 0; trial < 200; trial++) {
                List<InputEdge> edges = new ArrayList<>();
                int m = random.nextInt(2 * n + 4);
                for (int j = 0; j < m; j++) {
                    edges.add(new InputEdge(random.nextInt(n),
                            random.nextInt(n), random.nextInt(13)));
                }
                check(n, edges);
                seeded++;
            }
        }
        check(4, List.of(new InputEdge(0, 1, 1_000_000_000L),
                         new InputEdge(1, 3, 1_000_000_000L),
                         new InputEdge(0, 2, 1_000_000_000L),
                         new InputEdge(2, 3, 1_000_000_000L)));
        expectInvalid(() -> new Network(1));
        expectInvalid(() -> new Network(2).addEdge(-1, 1, 1));
        expectInvalid(() -> new Network(2).addEdge(0, 2, 1));
        expectInvalid(() -> new Network(2).addEdge(0, 1, -1));
        expectInvalid(() -> new Network(2).solve(0, 0, Choice.BFS_SHORTEST));
        expectInvalid(() -> new Network(2).solve(0, 1, null));
        Network sample = new Network(2);
        sample.addEdge(0, 1, 1);
        sample.solve(0, 1, Choice.BFS_SHORTEST);
        boolean[] copy = sample.reachable(0);
        if (copy[0] != true) throw new AssertionError("residual-side issue");
        System.out.println("Exhaustive capacity assignments: " + exhaustive + " PASS");
        System.out.println("Seeded flow networks: " + seeded + " PASS");
        System.out.println("Large capacities, loops, parallel edges: PASS");
        System.out.println("Invalid-input checks: PASS");
    }

    private static void print(String title, Result result) {
        System.out.println(title + " maxFlow=" + result.maxFlow()
                + ", minCut=" + result.minCut()
                + ", augmentations=" + result.steps().size());
        for (Step step : result.steps()) {
            System.out.println("  path=" + step.vertices()
                    + " delta=" + step.increase());
        }
        List<Integer> side = new ArrayList<>();
        boolean[] in = result.sourceSide();
        for (int i = 0; i < in.length; i++) {
            if (in[i]) side.add(i);
        }
        System.out.println("  Source-side min-cut=" + side);
    }

    public static void main(String[] args) {
        List<InputEdge> sample = List.of(
                new InputEdge(0, 1, 4),
                new InputEdge(1, 2, 1),
                new InputEdge(2, 3, 4),
                new InputEdge(1, 3, 4),
                new InputEdge(0, 2, 4));
        print("DFS-first", build(4, sample).solve(
                0, 3, Choice.DFS_FIRST));
        print("BFS-shortest", build(4, sample).solve(
                0, 3, Choice.BFS_SHORTEST));
        verify();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac FordFulkersonPathChoice.java
java FordFulkersonPathChoice
~~~

**Stdout chính xác của chương trình Java khi chạy độc lập:**

~~~text
DFS-first maxFlow=8, minCut=8, augmentations=4
  path=[0, 1, 2, 3] delta=1
  path=[0, 1, 3] delta=3
  path=[0, 2, 1, 3] delta=1
  path=[0, 2, 3] delta=3
  Source-side min-cut=[0]
BFS-shortest maxFlow=8, minCut=8, augmentations=2
  path=[0, 1, 3] delta=4
  path=[0, 2, 3] delta=4
  Source-side min-cut=[0]
Exhaustive capacity assignments: 729 PASS
Seeded flow networks: 1200 PASS
Large capacities, loops, parallel edges: PASS
Invalid-input checks: PASS
~~~

Đối chiếu dòng log: DFS-first dùng bốn đường có Δ=1,3,1,3; BFS-shortest dùng hai đường có Δ=4,4. Cả hai trả maxFlow=8 và minCut=8. Đường 0→2→1→3 của DFS dùng **cung ngược residual** 2→1 để hủy bớt luồng đã gửi qua cạnh gốc 1→2.

## 20. Bộ kiểm thử vét cạn 729 cấu hình

Để tránh chỉ kiểm tra một ví dụ, mã thử một họ mạng có bốn đỉnh s=0, a=1, b=2, t=3 và sáu loại cạnh có hướng:

~~~text
0->1, 1->3, 0->2, 2->3, 1->2, 2->1.
~~~

Mỗi cạnh trong sáu loại có capacity thuộc {0,1,2}. Tổng số cách gán capacity:

~~~text
3^6 = 729 mạng.
~~~

Mỗi mạng được giải bằng **hai chiến lược trên hai bản Network riêng**, sau đó so với oracle duyệt **tất cả tập đỉnh S chứa s nhưng không chứa t**, tính tổng capacity của các cạnh đi từ S sang phần còn lại. Tập cắt có capacity nhỏ nhất chính là cận trên lý thuyết và theo định lý max-flow/min-cut cũng là max flow.

Bộ thử xác nhận ba đẳng thức độc lập:

~~~text
DFS.maxFlow == BFS.maxFlow == minCutOracle.
result.minCut == minCutOracle.
Tổng tất cả bottleneck trong trace == maxFlow.
~~~

Bộ gán bao phủ trường hợp không có đường, capacity bằng 0, nhiều đường cạnh tranh, cặp cạnh ngược hướng thật và những tình huống mà thứ tự tăng có thể khác.

## 21. Bộ thử seeded 1.200 mạng và các biên

Mã sử dụng Random với seed 3302026, mỗi n từ **2 tới 7** sinh **200 mạng**, tổng 6×200=1.200 mạng. Mỗi mạng có số cạnh ngẫu nhiên trong [0,2n+3], hai đầu ngẫu nhiên độc lập và capacity nguyên từ 0 tới 12. Nhờ chọn hai đầu độc lập, dữ liệu có thể chứa **self-loop, cạnh song song, cạnh đối hướng**, cạnh capacity 0 hoặc nhiều thành phần không nối tới t.

Với từng mạng, chương trình chạy DFS/BFS và đối chiếu với oracle duyệt lát cắt, xác minh chứng chỉ minCut của cả hai. Ngoài ra có một mạng capacity **1.000.000.000** trên mỗi nhánh, cho tổng luồng 2.000.000.000, nhằm xác nhận code không mặc định dung lượng nhỏ hoặc giới hạn bước tăng theo một giá trị cố định.

Những input bị từ chối trong bộ test gồm n<2, đầu cạnh âm/ngoài phạm vi, capacity âm, chọn s=t, và Choice null. Đây là quyết định của API demo, không phải ràng buộc định nghĩa toán học của mọi phát biểu bài max flow.

**Tổng số mạng đối chiếu oracle là 729+1.200=1.929**, chưa tính ví dụ tay và một số ca biên. Kết quả PASS trên miền thử không thay thế chứng minh tổng quát nhưng giúp bắt các lỗi reverse arc, visited, tìm đường và cộng capacity lát cắt.

## 22. So sánh Ford–Fulkerson và các biến thể

| Phương án | Đường tăng chọn thế nào? | Bảo đảm và lưu ý |
| --- | --- | --- |
| Ford–Fulkerson tổng quát | Bất kỳ đường dư s→t hợp lệ | Đúng nếu dừng khi hết đường; có thể rất chậm hoặc không dừng với capacity vô tỉ và lựa chọn tệ |
| DFS-first | Một đường do DFS tìm được | Dễ cài; phụ thuộc thứ tự adjacency, cận giả đa thức với dung lượng nguyên |
| Edmonds–Karp | BFS, ít **cung dư** nhất | Bảo đảm O(VE²) theo phân tích chuẩn, không phụ thuộc trị số capacity |
| Dinic | BFS xây level graph rồi xử lý blocking flow | Phương pháp mạnh hơn cho nhiều lớp bài, không đồng nhất với một lần BFS lấy một đường |
| Push–relabel | Duy trì preflow và đẩy theo local residual | Khác họ đường tăng trực tiếp, hữu ích cho max flow lớn |

Nếu một bài yêu cầu **giải thích nguyên lý** hoặc xử lý mạng nhỏ, DFS Ford–Fulkerson rất minh bạch. Nếu cần một phiên bản đường tăng có bảo đảm hiệu năng đa thức, hãy ưu tiên **Edmonds–Karp**. Với kích thước lớn, có thể cân nhắc **Dinic** hoặc phương pháp cao cấp khác, nhưng trước hết phải hiểu đồ thị dư và cạnh ngược.

## 23. Những lỗi hay gặp

1. **Chỉ dựng cung thuận**, quên cung ngược; không thể điều chỉnh lại luồng đã gửi.
2. **Hiểu cung ngược là cạnh gốc thật** và cộng nhầm khi tính lát cắt.
3. **Dùng cạnh ngược vật lý làm reverse arc của cạnh khác** khi input có hai hướng.
4. **Không kiểm tra residual>0** khi tìm đường, nên đi qua cung không còn khả năng tăng.
5. **Dùng tổng capacity hoặc trung bình** thay cho bottleneck nhỏ nhất trên đường.
6. **Quên giảm residual thuận khi tăng residual ngược**; vi phạm quan hệ giữa f và capacity.
7. **Chỉ tăng cung ngược mà không giảm cung đã đi qua**, làm sai bảo toàn luồng.
8. **Không reset visited** cho từng lần tìm đường mới khi residual đã thay đổi.
9. **Ngộ nhận BFS luôn chọn đường có Δ lớn nhất**: BFS tối thiểu hóa số cạnh, không tối đa hóa bottleneck.
10. **Cho rằng DFS luôn có cùng số lần tăng** bất kể thứ tự input.
11. **Bỏ kiểm tra nguồn và đích khác nhau**, khiến đường rỗng s=t có ý nghĩa không rõ.
12. **Cho rằng số lượt tăng phụ thuộc duy nhất V,E** với Ford–Fulkerson chọn đường tùy ý và capacity nguyên.
13. **Dùng số thực double và kiểm tra residual>0 một cách thiếu kiểm soát**: sai số có thể tạo đường giả hoặc vòng lặp số học. Nên có hợp đồng số rõ.
14. **Dùng int cho tổng flow lớn** dù mỗi capacity riêng không quá int.
15. **Không bảo toàn từng cạnh song song** và lấy nhầm một capacity duy nhất cho cả cặp đầu mút.
16. **Tính minCut bằng các cung dư**, trong khi capacity cut cần từ **các cạnh gốc** có u∈S,v∉S.
17. **Cộng cả cạnh T→S vào capacity cut**: capacity lát cắt có hướng chỉ tính S→T.
18. **Gọi solve hai lần trên cùng Network để so DFS/BFS** mà không khởi tạo lại residual.
19. **Lưu vô hạn trace đường tăng trên mạng khổng lồ** mà không tính bộ nhớ O(A·V).
20. **Dừng khi một chiến lược không tìm thấy đường do bug duyệt**, không kiểm tra reachable và định lý min-cut.
21. **Không thử mạng có maxFlow=0** hoặc có nhiều đường dư bị nghẽn.
22. **Nhầm Edmonds–Karp với BFS chạy một lần**: phải BFS lại sau mỗi lần cập nhật residual.

## 24. Bài tập tự luyện

**Bài 1 — Chạy tay:** với mạng (0,1,4),(1,2,1),(2,3,4),(1,3,4),(0,2,4), hãy tính residual trước và sau đường 0→1→2→3. Xác định capacity của cung ngược 2→1 rồi tiếp tục các đường DFS còn lại.

**Bài 2 — Hai chiến lược:** cho cùng mạng, liệt kê đường tăng và bottleneck nếu mỗi lượt dùng BFS theo số cạnh. So số lần tăng với DFS, kiểm chứng hai kết quả đều bằng 8.

**Bài 3 — Hủy luồng:** giả sử ban đầu đã có f(1,2)=1 trong mạng ví dụ. Giải thích vì sao đi qua cung dư 2→1 với Δ=1 tương đương đặt f(1,2)=0, không phải tạo cạnh 2→1 thật mới.

**Bài 4 — Chọn đường tệ:** với các cạnh s→a=K, a→t=K, s→b=K, b→t=K và a→b=1, chứng minh hai đường ngắn cho 2K luồng sau hai lượt, còn chuỗi zigzag có thể dùng 2K lượt mỗi lượt tăng 1.

**Bài 5 — Max-flow/min-cut:** sau khi max flow trên mạng ví dụ, tính tập S reachable qua residual>0, liệt kê cạnh gốc từ S sang T, so cutCapacity với maxFlow.

**Bài 6 — Oracle brute force:** tự viết hàm duyệt 2^V tập S cho n≤7, tính capacity của mọi s–t cut. Đối chiếu với Ford–Fulkerson DFS/BFS trên tất cả capacity 0,1,2 của một mạng nhỏ.

**Bài 7 — Đa cạnh:** cho hai cạnh vật lý 0→1 capacity 2 và 3, một cạnh 1→0 capacity 4, và 1→2 capacity 6. Dựng từng cặp Arc/Arc.reverse, tìm maxFlow 0→2 và giải thích vì sao không thể gộp tất cả cung 1→0 làm reverse của cùng một đối tượng.

**Bài 8 — Cạnh bằng 0 và self-loop:** thêm 0→0 capacity 100, 1→1 capacity 50 và một cạnh 0→1 capacity 0 vào mạng. Chúng có giúp tăng giá trị luồng 0→t không? Kiểm tra nguyên tắc visited/residual và capacity lát cắt.

**Bài 9 — Cận giả đa thức:** giải thích vì sao O(EF) có thể lớn ngay cả khi E nhỏ và F được lưu bằng số bit O(log F). Chỉ ra ưu điểm của O(VE²) với BFS so với số lượng capacity khổng lồ.

**Bài 10 — Triển khai thực tế:** bỏ việc lưu mọi Step khỏi giải thuật để chỉ trả maxFlow, minCut và sourceSide; so bộ nhớ trên mạng lớn. Giữ lại cơ chế cập nhật reverse arc và chứng chỉ min-cut.

**Kết luận:** **Ford–Fulkerson** tăng luồng theo những đường còn capacity trong **đồ thị dư**. Cung ngược cho phép sửa lại một quyết định phân phối luồng cũ, còn **bottleneck** quyết định lượng tăng mỗi lượt. Khi không còn đường tăng, lát cắt reachable từ s trong residual chứng minh luồng đang có là **tối ưu**. Cách chọn đường là một quyết định thuật toán lớn: DFS có thể đơn giản nhưng gặp chuỗi đường rất tệ; Edmonds–Karp dùng BFS để có cận thời gian đa thức. Nắm vững mô hình residual, hướng cạnh vật lý, và chứng chỉ max-flow/min-cut giúp triển khai cả hai phiên bản một cách chính xác.
