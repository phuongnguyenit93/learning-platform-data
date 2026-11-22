# Phát hiện chu trình trong đồ thị vô hướng

Khi **duyệt đồ thị**, nhận biết một **chu trình (cycle)** là thao tác nền tảng: kiểm tra đồ thị có phải cây/rừng, xác minh việc thêm một cạnh có tạo vòng, hoặc xử lý các cấu trúc liên thông trong mạng. Một bẫy quan trọng của **đồ thị vô hướng** là khi từ u đi tới v theo một cạnh, danh sách kề của v luôn chứa cung quay lại u của chính cạnh ấy. Nhìn thấy đỉnh đã thăm **chưa phải** là bằng chứng có chu trình nếu cung đó chỉ đi ngược trên cạnh vừa dùng.

Bài học thuộc nhóm **Duyệt đồ thị** của Computer Science Algorithms, tập trung vào **Phát hiện chu trình trong đồ thị vô hướng**. Nội dung giải thích DFS, BFS và Disjoint Set Union (DSU/Union-Find), chứng minh tính đúng đắn, phân biệt đồ thị đơn với đa đồ thị có cạnh song song và khuyên (self-loop), phân tích O(V+E) và cách trả về một **chu trình cụ thể**. Chương trình Java 17+ phía dưới kiểm chứng cả ba thuật toán với oracle độc lập trên **3.060 đồ thị**.

## 1. Định nghĩa chính xác chu trình

Cho G=(V,E), đồ thị vô hướng có n=|V| đỉnh đánh số từ 0 đến n−1 và m=|E| **cạnh vật lý**. Một cạnh vô hướng (u,v) không phân biệt chiều nối từ u sang v hay từ v sang u. Một đường đi là chuỗi các đỉnh liên tiếp có cạnh nối. Trong bài này, một chu trình là một **đường đi đóng** quay về đỉnh ban đầu, không lặp **cạnh vật lý**, và không lặp đỉnh nội bộ.

Đối với **đồ thị đơn** (không có khuyên, không có cạnh song song), chu trình có ít nhất 3 cạnh. Đối với **đa đồ thị**, cần tính cả:

- Khuyên (u,u): một cạnh tạo chu trình dài **1 cạnh**, thể hiện bằng dãy đỉnh [u,u].
- Hai cạnh **khác nhau** cùng nối u,v: tạo chu trình dài **2 cạnh**, đi từ u sang v bằng cạnh thứ nhất rồi quay lại bằng cạnh thứ hai.
- Một cạnh (u,v) được đi qua rồi quay về trên **chính cạnh ấy** không phải chu trình theo định nghĩa này.

Mỗi cạnh đầu vào có một **ID riêng**, bằng thứ tự của nó trong danh sách. Nếu hai phần tử đầu vào có cùng hai đầu mút, chúng vẫn là **hai cạnh vật lý** khác nhau.

Ví dụ:

~~~text
A: edges = [(0,1),(1,2),(2,0)]
   Có chu trình 0 -> 1 -> 2 -> 0.

B: edges = [(0,1),(1,2),(1,3)]
   Không có chu trình: đây là cây.

C: edges = [(0,1),(0,1)]
   Có chu trình 0 -> 1 -> 0, dùng ID 0 và ID 1.

D: edges = [(0,0)]
   Có một khuyên, chính là chu trình độ dài 1.
~~~

**Đồ thị rỗng:** n=0, m=0 là trường hợp hợp lệ theo API minh họa và trả false. Với n>0 mà không có cạnh, đồ thị gồm các đỉnh cô lập và cũng không có chu trình.

## 2. Cây, rừng và vai trò của chu trình

Một đồ thị vô hướng **không chứa chu trình** được gọi là **rừng (forest)**. Mỗi thành phần liên thông của rừng là một cây; nếu toàn bộ đồ thị liên thông và có ít nhất một đỉnh, rừng ấy là một **cây (tree)**.

Các ứng dụng thường thấy gồm xác định một mạng đã có vòng chưa, kiểm tra dữ liệu cạnh trùng, duy trì rừng khi thêm cạnh trong thuật toán Kruskal, hoặc xuất một đường đi đóng chứng minh cấu trúc không phải rừng. Việc chỉ xác nhận có chu trình khác với yêu cầu **tìm chu trình ngắn nhất**: DFS đầu tiên tìm thấy một chu trình không được bảo đảm là ngắn nhất.

Nếu đồ thị có nhiều thành phần liên thông, chỉ cần **một thành phần chứa chu trình** là đủ để trả true. Đây là lý do DFS/BFS phải chạy từ **mọi đỉnh chưa thăm**, không chỉ từ đỉnh 0.

## 3. Danh sách kề và ID cạnh

Với một cạnh vật lý có ID e, nối u với v, danh sách kề của đồ thị vô hướng thêm hai cung:

~~~text
adj[u].add((to=v, edgeId=e))
adj[v].add((to=u, edgeId=e))
~~~

Hai cung đại diện cho **một cạnh vật lý** và phải có **cùng ID**. Nếu có hai cạnh song song nối u-v, chúng có hai ID khác nhau và mỗi cạnh tạo hai cung.

Với khuyên (u,u), đoạn mã trên thêm hai entry vào **cùng adj[u]**, vẫn dùng chung một ID. Ta không vì hai entry đó mà đếm nhầm thành hai cạnh vật lý. Cấu trúc dùng O(n+m) bộ nhớ: n danh sách và 2m entry kề.

**Phân biệt rõ:**

- Edge(u,v) là một cạnh vật lý xuất hiện đúng một lần trong danh sách input.
- Arc(to,id) là một hướng duyệt của cạnh đó, xuất hiện hai lần cho mỗi cạnh.
- parentEdge[v] là ID của **cạnh đã khám phá v**, không chỉ là nhãn đỉnh đã khám phá v.

Chính trường parentEdge làm phiên bản DFS/BFS của bài hoạt động đúng cả trên đa đồ thị.

## 4. DFS với cạnh cha: ba trường hợp khi xét một cung

Duyệt sâu (Depth-First Search — DFS) đánh dấu visited khi khám phá đỉnh đầu tiên. Mỗi đỉnh khác gốc được đưa vào cây DFS qua một cạnh có ID parentEdge[v]. Tại v, xét cung kề (v,w,e):

1. Nếu e == parentEdge[v], đây là **cung quay ngược trên chính cạnh cây** vừa dùng để đi tới v. Bỏ qua, không báo chu trình.
2. Nếu e khác parentEdge[v] và w chưa visited, dùng e để khám phá w, ghi parent[w]=v, parentEdge[w]=e và tiếp tục DFS.
3. Nếu e khác parentEdge[v] và w đã visited, một **cạnh ngoài cây DFS** nối v với đỉnh đã được khám phá tạo chu trình. Dừng và trả true hoặc dựng một chu trình chứng minh.

Khi thực hiện DFS chuẩn trên đồ thị vô hướng, cạnh ngoài cây đang xét ở bước 3 nối v với **tổ tiên còn nằm trên đường DFS**, hoặc với chính v khi là khuyên. Do đó đường đi trong cây DFS từ tổ tiên tới v, cộng cạnh ngoài cây, tạo thành đường đi đóng hợp lệ.

**Tại sao không chỉ dùng visited[w]?** Với cây chỉ có cạnh 0–1, khi từ 0 tới 1, cung ngược 1→0 chắc chắn gặp 0 đã visited. Nếu báo chu trình, mọi cây có cạnh cũng bị nhận nhầm là có vòng.

## 5. Phản ví dụ: kiểm tra đỉnh cha sai với cạnh song song

Với đồ thị **đơn**, người ta thường viết điều kiện bỏ qua khi w == parentVertex[v]. Do chỉ có tối đa một cạnh giữa hai đỉnh, đây là cách viết đúng dưới giả thiết đó.

Nhưng trong đa đồ thị:

~~~text
Cạnh ID0: 0 ----- 1
Cạnh ID1: 0 ----- 1

DFS đi 0 -> 1 bằng ID0.
Ở 1:
  - cung 1 -> 0 thuộc ID0: phải bỏ qua, vì là cạnh cây;
  - cung 1 -> 0 thuộc ID1: là cạnh KHÁC và tạo chu trình.
~~~

Nếu bỏ mọi cung đi về **đỉnh cha 0**, thuật toán bỏ cả ID0 và ID1 rồi trả false: sai. Bỏ duy nhất cung có **ID bằng parentEdge[1]** mới đúng.

Tương tự, tự ý dùng Set để loại bỏ những cạnh có cùng đầu mút sẽ xóa mất một chu trình hai cạnh trong một đa đồ thị. Chỉ chuẩn hóa cạnh trùng nếu **đề bài định nghĩa dữ liệu là đồ thị đơn** và quy định rõ cách xử lý input.

## 6. Giả mã DFS phát hiện chu trình

Bản đệ quy có thể trình bày ngắn gọn:

~~~text
dfs(v, incomingEdge):
    visited[v] = true

    for (w, edgeId) in adj[v]:
        if edgeId == incomingEdge:
            continue

        if not visited[w]:
            if dfs(w, edgeId):
                return true
        else:
            return true

    return false

hasCycle:
    for root = 0 .. n-1:
        if not visited[root] and dfs(root, -1):
            return true
    return false
~~~

Gốc dùng incomingEdge=−1, không trùng ID cạnh thật 0..m−1. Vòng ngoài xử lý **mọi thành phần liên thông**, nên chu trình ở một thành phần không bị bỏ sót chỉ vì điểm bắt đầu nằm ở nơi khác.

Với DFS đệ quy trên đường rất dài, stack Java có thể sâu O(n) và gây StackOverflowError. Mã đầy đủ dùng **DFS lặp với ArrayDeque**, có cùng tư duy nhưng quản lý stack và vị trí duyệt adjacency tường minh.

## 7. DFS lặp và bất biến của ngăn xếp

Một DFS lặp đúng nghĩa cần lưu:

~~~text
stack        các đỉnh trên đường DFS đang hoạt động;
nextArc[v]   index của entry kề tiếp theo chưa xử lý tại v;
visited[v]   v đã được khám phá hay chưa;
parent[v]    đỉnh đã khám phá v, hoặc -1 nếu v là gốc;
parentEdge[v] ID của cạnh đã khám phá v, hoặc -1 nếu gốc.
~~~

Tại mỗi bước, nhìn stack.peek():

- Nếu không còn entry kề tại v, pop v ra khỏi đường hoạt động.
- Nếu còn, đọc entry theo nextArc[v] rồi tăng con trỏ.
- Bỏ đúng entry có ID là parentEdge[v].
- Nếu gặp w chưa khám phá, đánh dấu ngay, ghi parent và push w; không pop v lúc ấy.
- Nếu gặp w đã khám phá qua một cạnh khác, đã có nhân chứng chu trình.

**Bất biến:** mỗi đỉnh được đánh dấu một lần, được push lên stack một lần và mỗi entry kề được đọc tối đa một lần. Giữ đỉnh cha trên stack tới lúc duyệt xong mọi entry làm các cạnh ngoài cây trong đồ thị vô hướng nối tới tổ tiên đang hoạt động.

Nếu chỉ dùng stack để push **tất cả láng giềng** cùng lúc, quan hệ parent có thể không còn giống DFS đệ quy. Một thuật toán chỉ kiểm tra boolean vẫn có thể được thiết kế đúng theo cách khác, nhưng **hàm dựng chu trình theo chuỗi tổ tiên** cần bất biến DFS phù hợp.

## 8. Truy vết chu trình: đỉnh và ID cạnh

Khi phát hiện cạnh ngoài cây nối từ v tới tổ tiên w, giữ lại closingEdge là ID của cạnh đó. Đi ngược qua parent[v], parent[parent[v]] ... cho đến w, thu các ID parentEdge của đường cây; sau đó đảo thứ tự và thêm cạnh closingEdge.

~~~text
Đường cây: w -> ... -> v
Cạnh ngoài cây: v -> w

Chu trình:
vertices = [w, ..., v, w]
edgeIds  = [ID các cạnh cây, closingEdge]
~~~

Ví dụ tam giác với ID0=(0,1), ID1=(1,2), ID2=(2,0):

~~~text
vertices = [0, 1, 2, 0]
edgeIds  = [0, 1, 2]
~~~

Với self-loop: vertices=[u,u], edgeIds=[idOfLoop].

Với hai cạnh song song: vertices=[u,v,u], edgeIds=[id0,id1], hai ID **phân biệt**.

Chỉ lưu đỉnh là chưa đủ với đa đồ thị: dãy [u,v,u] có thể là cách đi tới rồi quay lại trên **cùng cạnh duy nhất** nếu không kiểm tra ID; trường hợp đó **không phải chu trình hợp lệ**.

## 9. Cách xác minh một nhân chứng chu trình

Nếu thuật toán trả một nhân chứng có L cạnh, cần kiểm tra:

1. L≥1; số phần tử vertices bằng L+1 và số edgeIds bằng L.
2. Đỉnh đầu bằng đỉnh cuối.
3. Mỗi ID cạnh thuộc [0,m−1] và mỗi đỉnh thuộc [0,n−1].
4. Cạnh thật tại edgeIds[i] nối đúng vertices[i] và vertices[i+1], không phân biệt chiều.
5. Không dùng lại cùng ID cạnh trong chu trình.
6. Không lặp đỉnh nội bộ, ngoại trừ lần xuất hiện bắt buộc của đỉnh đầu tại cuối.

Những điều kiện trên công nhận vòng một cạnh (khuyên) và vòng hai cạnh song song, nhưng từ chối việc dùng lại **cùng một cạnh** hai lần. Hàm checkWitness trong Java thực hiện các kiểm tra đó cho mọi ca có kết quả DFS là true.

Nếu DFS trả false, hai mảng nhân chứng phải rỗng. Điều này giúp API nói rõ rằng không có đường đi đóng nào được phát hiện.

## 10. Chứng minh DFS phát hiện chu trình đúng

**Chiều không báo nhầm (soundness):** thuật toán bỏ qua đúng cạnh cây đã dùng để tới v. Khi gặp một cung khác nối v tới w đã visited, tính chất DFS vô hướng bảo đảm w là tổ tiên của v hoặc chính v. Đường cây từ w tới v không lặp đỉnh; cung ngoài cây là một cạnh vật lý khác ID cạnh cây bị bỏ. Ghép lại tạo một chu trình. Với khuyên, đường cây có độ dài 0 và cạnh khuyên tự tạo vòng.

**Chiều không bỏ sót (completeness):** giả sử đồ thị có chu trình nhưng DFS duyệt hết mọi thành phần mà không nhận thấy cạnh ngoài cây. Khi ấy mọi cạnh của đồ thị chỉ là cạnh cây DFS; tập cạnh cây DFS là một **rừng** nên không thể chứa chu trình. Mâu thuẫn. Vì vòng ngoài duyệt mọi gốc chưa visited, chu trình ở thành phần khác cũng được xét.

Bản lặp dùng nextArc mô phỏng đúng thứ tự phụ thuộc của DFS đệ quy, nên bất biến tổ tiên và chứng minh trên tiếp tục đúng.

## 11. BFS phát hiện chu trình tương tự, nhưng truy vết khác

Duyệt rộng (Breadth-First Search — BFS) dùng queue. Cấu trúc cần thiết là visited[v] và parentEdge[v]:

~~~text
Với mỗi gốc chưa visited:
    visited[root] = true
    queue.add(root)

    while queue không rỗng:
        v = queue.remove()
        for mỗi cung (v,w,e):
            if e == parentEdge[v]:
                continue
            if not visited[w]:
                visited[w] = true
                parentEdge[w] = e
                queue.add(w)
            else:
                return true
~~~

Tương tự DFS, kiểm tra theo cạnh ID xử lý đúng khuyên và cạnh song song. Trong BFS, một cung ngoài cây nối hai đỉnh trong cùng thành phần cây BFS tạo một vòng; thuật toán không nhầm cung quay lại **chính cạnh cha**.

**Khác DFS:** khi BFS gặp một láng giềng đã visited, láng giềng đó không nhất thiết là tổ tiên trên một đường stack hiện hành. Vì vậy hàm dựng đường đi qua parent của DFS không thể áp dụng nguyên xi cho BFS. Nếu cần in chu trình từ BFS, hãy xây đường từ hai đầu cạnh ngoài cây lên **tổ tiên chung**, rồi ghép hai đường đó với cạnh ngoài cây.

BFS lặp lại từ mọi gốc để xử lý đồ thị không liên thông; với danh sách kề nó chạy **O(n+m) thời gian** và tổng bộ nhớ O(n+m), gồm cả lưu đồ thị.

## 12. DSU/Union-Find: một góc nhìn theo quá trình thêm cạnh

Với input dạng danh sách cạnh, DSU rất phù hợp. Ban đầu mỗi đỉnh là một tập riêng. Khi đọc cạnh (u,v):

- Nếu find(u) khác find(v), u và v nằm ở hai thành phần khác nhau. Union hai tập; cạnh này không tạo chu trình.
- Nếu find(u) bằng find(v), đã có đường đi từ u tới v qua những cạnh được xét trước đó; thêm cạnh mới tạo một chu trình. Trả true.

~~~text
DSU bắt đầu với n tập một đỉnh

for each physical edge (u,v):
    if find(u) == find(v):
        return true
    union(u,v)

return false
~~~

**Khuyên:** u=v, nên find bằng nhau ngay ở cạnh đầu. **Cạnh song song:** cạnh thứ nhất hợp nhất hai đầu; cạnh thứ hai thấy hai đầu đã thuộc cùng thành phần, báo chu trình. **Nhiều thành phần:** DSU xử lý tự nhiên và không cần tìm gốc từng thành phần bằng DFS/BFS.

Mã sử dụng **nén đường đi (path compression)** và **gộp theo kích thước (union by size)**, cho tổng O(n+mα(n)) thời gian và O(n) bộ nhớ phụ, với α là hàm nghịch đảo Ackermann tăng cực chậm. Không cần xây adjacency list nếu danh sách cạnh đã sẵn có.

**Giới hạn:** DSU chuẩn giải tốt việc **thêm cạnh**; không hỗ trợ xóa cạnh tùy ý để cập nhật phân hoạch. Nó cũng không trực tiếp giữ đường đi để in chu trình cụ thể.

## 13. Chứng minh điều kiện DSU báo chu trình

Bất biến trước mỗi cạnh: các tập DSU là đúng **thành phần liên thông của đồ thị gồm các cạnh đã thêm**, và nếu chưa báo chu trình, những cạnh đó tạo thành một rừng.

Nếu hai đầu u,v ở hai thành phần khác nhau, trước đó không có đường đi giữa chúng; ghép bằng một cạnh tạo cây lớn hơn, không thể tạo vòng.

Nếu chúng đã cùng một thành phần, trong rừng đã có một đường đi đơn từ u tới v; thêm cạnh vật lý mới sẽ đóng một chu trình. Khi u=v, chính cạnh khuyên là chu trình.

Vì thế, DSU trả true **đúng khi** một cạnh được thêm nối hai đỉnh đã liên thông; nếu duyệt hết mà không gặp trường hợp này, mọi cạnh đều chỉ nối các thành phần khác nhau, tạo rừng và không có chu trình.

Chứng minh này đồng thời làm rõ lý do **ID vật lý của cạnh** quan trọng. Hai cung của cùng một cạnh vô hướng không được đem union hai lần như thể có hai cạnh: input của DSU phải là **mỗi cạnh vật lý đúng một lần**.

## 14. So sánh ba thuật toán

| Tiêu chí | DFS cạnh cha | BFS cạnh cha | DSU |
| --- | --- | --- | --- |
| Input thuận tiện | Danh sách kề | Danh sách kề | Danh sách cạnh |
| Có chu trình? | Có | Có | Có |
| Tạo nhân chứng chu trình | Thuận tiện với parent/stack | Cần ghép các đường cha | Cần cấu trúc bổ sung |
| Đồ thị không liên thông | Duyệt mọi gốc | Duyệt mọi gốc | Tự nhiên |
| Khuyên / cạnh song song | Xử lý bằng ID cạnh | Xử lý bằng ID cạnh | Xử lý theo từng cạnh vật lý |
| Thêm cạnh tuần tự | Thường cần duyệt lại | Tương tự | Rất phù hợp |
| Xóa cạnh trực tuyến | Không có hỗ trợ trực tiếp | Không có hỗ trợ trực tiếp | Không có hỗ trợ trong DSU chuẩn |
| Thời gian | O(n+m) | O(n+m) | O(n+mα(n)) |
| Bộ nhớ ngoài danh sách input | O(n+m) nếu xây adjacency | O(n+m) nếu xây adjacency | O(n) |

Trong bài chỉ cần **boolean** và nhận danh sách cạnh, DSU có thể gọn nhất. Nếu đề cần trả **một chu trình thực sự**, DFS với parentEdge dễ khôi phục. BFS hữu ích khi bài còn yêu cầu khoảng cách từ nguồn trong đồ thị không trọng số, nhưng mã ví dụ dùng BFS chỉ để trả boolean.

**Không áp dụng trực tiếp cho đồ thị có hướng:** gặp visited không phải cha và điều kiện DSU nối hai đỉnh đã liên thông vô hướng không phải tiêu chuẩn phát hiện vòng có hướng. Đồ thị có hướng cần xét cạnh quay về trạng thái đang trên stack DFS (gray), hoặc dùng sắp xếp topo.

## 15. Định lý rừng và số cạnh

Với một đồ thị vô hướng có n đỉnh, m cạnh vật lý, c thành phần liên thông, điều kiện không chu trình tương đương:

~~~text
G không có chu trình  <=>  m = n - c.
~~~

Trong rừng, mỗi thành phần có k đỉnh là một cây gồm k−1 cạnh; cộng cho mọi thành phần cho m=Σ(k−1)=n−c. Ngược lại, để nối k đỉnh trong một thành phần phải có ít nhất k−1 cạnh. Nếu cả đồ thị đạt đúng tổng n−c, không thành phần nào có cạnh dư, nên mỗi thành phần là cây.

**Cẩn thận:** biết m=n−1 **chưa đủ** để kết luận đồ thị là cây nếu chưa biết nó liên thông. Một tam giác trên {0,1,2} cộng một đỉnh cô lập 3 có n=4, m=3=n−1 nhưng có chu trình.

Định lý trên vẫn đúng cho đa đồ thị nếu m tính **các cạnh vật lý**: khuyên làm tăng m mà không tăng liên thông, hai cạnh song song cũng có thể tạo cạnh dư, nên báo có chu trình.

Nếu n≥1, một đồ thị **liên thông** và m=n−1 là cây. Còn nếu n=0, nên giữ quy ước đồ thị rỗng và c=0 để hệ thức m=n−c không gây bất ngờ.

## 16. Chương trình Java 17+ hoàn chỉnh

Lưu tệp **UndirectedCycleDetection.java**. Chương trình chứa ba phương pháp công khai:

- dfsCycle(n,edges): DFS lặp dùng nextArc và parentEdge, trả CycleResult với trạng thái có chu trình và hai mảng **đỉnh/ID cạnh** của một chu trình nếu có.
- bfsHasCycle(n,edges): BFS dùng parentEdge, trả boolean.
- dsuHasCycle(n,edges): DSU có nén đường và union by size, trả boolean.

Ngoài ra có hàm **oracleByRemovingEdge** dành riêng cho kiểm thử, và hàm **checkWitness** xác nhận một chu trình trả về thực sự đi qua những ID cạnh khác nhau, khép kín và không lặp đỉnh nội bộ.

Hợp đồng đầu vào: n≥0, danh sách cạnh khác null, cạnh không null, hai đầu thuộc 0..n−1; **cho phép self-loop và cạnh song song**. Không thay đổi danh sách input. Khi n=0 với danh sách rỗng, trả false. Record chứa mảng sao chép phòng vệ ở cả constructor và accessor, tránh trả tham chiếu nội bộ có thể bị sửa từ bên ngoài.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;

public final class UndirectedCycleDetection {
    public record Edge(int u, int v) { }
    private record Arc(int to, int edgeId) { }

    public record CycleResult(boolean hasCycle, int[] vertices, int[] edgeIds) {
        public CycleResult {
            vertices = vertices.clone();
            edgeIds = edgeIds.clone();
        }
        @Override
        public int[] vertices() {
            return vertices.clone();
        }
        @Override
        public int[] edgeIds() {
            return edgeIds.clone();
        }
    }

    private UndirectedCycleDetection() { }

    private static void validate(int n, List<Edge> edges) {
        if (n < 0 || edges == null) {
            throw new IllegalArgumentException("n >= 0 and nonnull edges required");
        }
        for (Edge edge : edges) {
            if (edge == null || edge.u() < 0 || edge.u() >= n
                    || edge.v() < 0 || edge.v() >= n) {
                throw new IllegalArgumentException("invalid vertex endpoint");
            }
        }
    }

    private static List<List<Arc>> adjacency(int n, List<Edge> edges) {
        List<List<Arc>> adj = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            adj.add(new ArrayList<>());
        }
        for (int id = 0; id < edges.size(); id++) {
            Edge e = edges.get(id);
            adj.get(e.u()).add(new Arc(e.v(), id));
            adj.get(e.v()).add(new Arc(e.u(), id));
        }
        return adj;
    }

    public static CycleResult dfsCycle(int n, List<Edge> edges) {
        validate(n, edges);
        List<List<Arc>> adj = adjacency(n, edges);
        boolean[] seen = new boolean[n];
        int[] parent = new int[n];
        int[] parentEdge = new int[n];
        int[] nextArc = new int[n];
        Arrays.fill(parent, -1);
        Arrays.fill(parentEdge, -1);
        ArrayDeque<Integer> stack = new ArrayDeque<>();

        for (int root = 0; root < n; root++) {
            if (seen[root]) {
                continue;
            }
            seen[root] = true;
            stack.push(root);
            while (!stack.isEmpty()) {
                int v = stack.peek();
                if (nextArc[v] == adj.get(v).size()) {
                    stack.pop();
                    continue;
                }
                Arc arc = adj.get(v).get(nextArc[v]++);
                if (arc.edgeId() == parentEdge[v]) {
                    continue;
                }
                int w = arc.to();
                if (!seen[w]) {
                    seen[w] = true;
                    parent[w] = v;
                    parentEdge[w] = arc.edgeId();
                    stack.push(w);
                } else {
                    return reconstruct(v, w, arc.edgeId(), parent, parentEdge);
                }
            }
        }
        return new CycleResult(false, new int[0], new int[0]);
    }

    private static CycleResult reconstruct(int from, int ancestor,
                                           int closingEdge, int[] parent,
                                           int[] parentEdge) {
        List<Integer> vertices = new ArrayList<>();
        List<Integer> edgeIds = new ArrayList<>();
        int at = from;
        vertices.add(at);
        while (at != ancestor) {
            if (at < 0 || parentEdge[at] < 0) {
                throw new AssertionError("DFS neighbor was not an ancestor");
            }
            edgeIds.add(parentEdge[at]);
            at = parent[at];
            vertices.add(at);
        }
        Collections.reverse(vertices);
        Collections.reverse(edgeIds);
        vertices.add(ancestor);
        edgeIds.add(closingEdge);
        return new CycleResult(true,
                vertices.stream().mapToInt(Integer::intValue).toArray(),
                edgeIds.stream().mapToInt(Integer::intValue).toArray());
    }

    public static boolean bfsHasCycle(int n, List<Edge> edges) {
        validate(n, edges);
        List<List<Arc>> adj = adjacency(n, edges);
        boolean[] seen = new boolean[n];
        int[] parentEdge = new int[n];
        Arrays.fill(parentEdge, -1);
        ArrayDeque<Integer> queue = new ArrayDeque<>();

        for (int root = 0; root < n; root++) {
            if (seen[root]) {
                continue;
            }
            seen[root] = true;
            queue.add(root);
            while (!queue.isEmpty()) {
                int v = queue.remove();
                for (Arc arc : adj.get(v)) {
                    if (arc.edgeId() == parentEdge[v]) {
                        continue;
                    }
                    int w = arc.to();
                    if (!seen[w]) {
                        seen[w] = true;
                        parentEdge[w] = arc.edgeId();
                        queue.add(w);
                    } else {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    private static final class DSU {
        private final int[] parent;
        private final int[] size;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
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

        boolean union(int a, int b) {
            int rootA = find(a);
            int rootB = find(b);
            if (rootA == rootB) {
                return false;
            }
            if (size[rootA] < size[rootB]) {
                int tmp = rootA;
                rootA = rootB;
                rootB = tmp;
            }
            parent[rootB] = rootA;
            size[rootA] += size[rootB];
            return true;
        }
    }

    public static boolean dsuHasCycle(int n, List<Edge> edges) {
        validate(n, edges);
        DSU dsu = new DSU(n);
        for (Edge edge : edges) {
            if (!dsu.union(edge.u(), edge.v())) {
                return true;
            }
        }
        return false;
    }

    private static boolean oracleByRemovingEdge(int n, List<Edge> edges) {
        for (int removed = 0; removed < edges.size(); removed++) {
            Edge targetEdge = edges.get(removed);
            if (targetEdge.u() == targetEdge.v()) {
                return true;
            }
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[targetEdge.u()] = true;
            queue.add(targetEdge.u());
            while (!queue.isEmpty()) {
                int vertex = queue.remove();
                for (int id = 0; id < edges.size(); id++) {
                    if (id == removed) {
                        continue;
                    }
                    Edge e = edges.get(id);
                    int neighbor = -1;
                    if (e.u() == vertex) {
                        neighbor = e.v();
                    } else if (e.v() == vertex) {
                        neighbor = e.u();
                    }
                    if (neighbor >= 0 && !seen[neighbor]) {
                        seen[neighbor] = true;
                        queue.add(neighbor);
                    }
                }
            }
            if (seen[targetEdge.v()]) {
                return true;
            }
        }
        return false;
    }

    private static void checkWitness(int n, List<Edge> edges,
                                     CycleResult result) {
        int[] vertices = result.vertices();
        int[] ids = result.edgeIds();
        if (!result.hasCycle()) {
            if (vertices.length != 0 || ids.length != 0) {
                throw new AssertionError("cycle absent but witness nonempty");
            }
            return;
        }
        if (ids.length < 1 || vertices.length != ids.length + 1
                || vertices[0] != vertices[vertices.length - 1]) {
            throw new AssertionError("malformed closed cycle");
        }
        boolean[] usedEdge = new boolean[edges.size()];
        boolean[] usedVertex = new boolean[n];
        for (int i = 0; i < ids.length; i++) {
            int u = vertices[i], v = vertices[i + 1], id = ids[i];
            if (u < 0 || u >= n || v < 0 || v >= n
                    || id < 0 || id >= edges.size()
                    || usedEdge[id] || usedVertex[u]) {
                throw new AssertionError("repeated or invalid cycle member");
            }
            Edge edge = edges.get(id);
            if (!((edge.u() == u && edge.v() == v)
                    || (edge.u() == v && edge.v() == u))) {
                throw new AssertionError("witness edge does not connect vertices");
            }
            usedEdge[id] = true;
            usedVertex[u] = true;
        }
    }

    private static void compare(int n, List<Edge> edges) {
        boolean expected = oracleByRemovingEdge(n, edges);
        CycleResult dfs = dfsCycle(n, edges);
        boolean bfs = bfsHasCycle(n, edges);
        boolean dsu = dsuHasCycle(n, edges);
        if (dfs.hasCycle() != expected || bfs != expected || dsu != expected) {
            throw new AssertionError("cycle mismatch: n=" + n
                    + " edges=" + edges);
        }
        checkWitness(n, edges, dfs);
    }

    private static void verify() {
        int simpleCases = 0;
        for (int n = 0; n <= 5; n++) {
            List<Edge> possible = new ArrayList<>();
            for (int a = 0; a < n; a++) {
                for (int b = a + 1; b < n; b++) {
                    possible.add(new Edge(a, b));
                }
            }
            int selections = 1 << possible.size();
            for (int mask = 0; mask < selections; mask++) {
                List<Edge> edges = new ArrayList<>();
                for (int id = 0; id < possible.size(); id++) {
                    if ((mask & (1 << id)) != 0) {
                        edges.add(possible.get(id));
                    }
                }
                compare(n, edges);
                simpleCases++;
            }
        }

        int multiCases = 0;
        for (int n = 0; n <= 3; n++) {
            List<Edge> possible = new ArrayList<>();
            for (int a = 0; a < n; a++) {
                for (int b = a; b < n; b++) {
                    possible.add(new Edge(a, b));
                }
            }
            int selections = 1;
            for (int i = 0; i < possible.size(); i++) {
                selections *= 3;
            }
            for (int code = 0; code < selections; code++) {
                List<Edge> edges = new ArrayList<>();
                int value = code;
                for (Edge edge : possible) {
                    int copies = value % 3;
                    value /= 3;
                    for (int count = 0; count < copies; count++) {
                        edges.add(edge);
                    }
                }
                compare(n, edges);
                multiCases++;
            }
        }

        int randomCases = 0;
        Random random = new Random(2682026L);
        for (int n = 4; n <= 9; n++) {
            for (int trial = 0; trial < 200; trial++) {
                int m = random.nextInt(2 * n + 4);
                List<Edge> edges = new ArrayList<>();
                for (int id = 0; id < m; id++) {
                    edges.add(new Edge(random.nextInt(n), random.nextInt(n)));
                }
                compare(n, edges);
                randomCases++;
            }
        }

        try {
            dfsCycle(-1, List.of());
            throw new AssertionError("negative vertex count accepted");
        } catch (IllegalArgumentException expected) {
        }
        try {
            bfsHasCycle(2, List.of(new Edge(0, 2)));
            throw new AssertionError("out-of-range endpoint accepted");
        } catch (IllegalArgumentException expected) {
        }
        try {
            dsuHasCycle(1, null);
            throw new AssertionError("null edge list accepted");
        } catch (IllegalArgumentException expected) {
        }
        if (dfsCycle(3, List.of(new Edge(0, 1))).hasCycle()
                || !dfsCycle(1, List.of(new Edge(0, 0))).hasCycle()
                || !dfsCycle(2, List.of(
                        new Edge(0, 1), new Edge(0, 1))).hasCycle()) {
            throw new AssertionError("basic forest/loop/parallel case failed");
        }

        System.out.println("Verified " + simpleCases
                + " simple graphs: PASS");
        System.out.println("Verified " + multiCases
                + " small multigraphs: PASS");
        System.out.println("Verified " + randomCases
                + " seeded multigraphs: PASS");
        System.out.println("Boundary and cycle-witness checks: PASS");
    }

    public static void main(String[] args) {
        List<Edge> triangle = List.of(
                new Edge(0, 1), new Edge(1, 2), new Edge(2, 0),
                new Edge(3, 4), new Edge(4, 5));
        CycleResult found = dfsCycle(6, triangle);
        System.out.println("Triangle DFS cycle: " + found.hasCycle());
        System.out.println("Triangle DFS vertices: "
                + Arrays.toString(found.vertices()));
        System.out.println("Triangle DFS edge IDs: "
                + Arrays.toString(found.edgeIds()));
        System.out.println("Triangle BFS cycle: "
                + bfsHasCycle(6, triangle));
        System.out.println("Triangle DSU cycle: "
                + dsuHasCycle(6, triangle));

        List<Edge> tree = List.of(new Edge(0, 1),
                new Edge(1, 2), new Edge(1, 3));
        System.out.println("Tree DFS/BFS/DSU: "
                + dfsCycle(4, tree).hasCycle() + "/"
                + bfsHasCycle(4, tree) + "/"
                + dsuHasCycle(4, tree));

        CycleResult parallel = dfsCycle(2, List.of(
                new Edge(0, 1), new Edge(0, 1)));
        System.out.println("Parallel edges cycle: " + parallel.hasCycle()
                + ", vertices=" + Arrays.toString(parallel.vertices())
                + ", edgeIds=" + Arrays.toString(parallel.edgeIds()));

        CycleResult loop = dfsCycle(1, List.of(new Edge(0, 0)));
        System.out.println("Self-loop cycle: " + loop.hasCycle()
                + ", vertices=" + Arrays.toString(loop.vertices())
                + ", edgeIds=" + Arrays.toString(loop.edgeIds()));
        System.out.println("Empty graph cycle: "
                + dfsCycle(0, List.of()).hasCycle());

        verify();
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac UndirectedCycleDetection.java
java UndirectedCycleDetection
~~~

Stdout chính xác từ phương thức main đã được chạy và đối chiếu:

~~~text
Triangle DFS cycle: true
Triangle DFS vertices: [0, 1, 2, 0]
Triangle DFS edge IDs: [0, 1, 2]
Triangle BFS cycle: true
Triangle DSU cycle: true
Tree DFS/BFS/DSU: false/false/false
Parallel edges cycle: true, vertices=[0, 1, 0], edgeIds=[0, 1]
Self-loop cycle: true, vertices=[0, 0], edgeIds=[0]
Empty graph cycle: false
Verified 1100 simple graphs: PASS
Verified 760 small multigraphs: PASS
Verified 1200 seeded multigraphs: PASS
Boundary and cycle-witness checks: PASS
~~~

Trong ví dụ, tam giác được đánh ID0=(0,1), ID1=(1,2), ID2=(2,0), nên DFS báo đường [0,1,2,0] và ID [0,1,2]. Nếu thay thứ tự cạnh trong danh sách, thuật toán vẫn đúng nhưng **nhân chứng đầu tiên** có thể khác. DSU và BFS chỉ báo true/false, không tự in một chu trình.

## 17. Oracle độc lập: bỏ một cạnh rồi kiểm tra kết nối

Một cạnh vật lý e=(u,v) thuộc chu trình **khi và chỉ khi** xóa đúng cạnh e mà hai đầu u,v **vẫn liên thông** qua các cạnh còn lại.

**Chứng minh:** nếu e nằm trên chu trình, phần còn lại của chu trình là một đường nối u-v không dùng e. Ngược lại, có một đường nối u-v không dùng e thì thêm e sẽ tạo đường đi đóng không lặp cạnh; lấy một đường đi đơn nếu cần. Với khuyên u=v, cạnh đó tự là chu trình; với hai cạnh song song, xóa một cạnh vẫn còn cạnh khác trực tiếp nối u-v.

Mã oracle thử từng cạnh trong danh sách, bỏ **chính ID của cạnh ấy**, rồi dùng queue kiểm tra còn đường từ đầu thứ nhất tới đầu thứ hai hay không. Đây là một cách kiểm thử **không dựa vào quy tắc cạnh cha của DFS/BFS cũng không dựa vào DSU**.

Oracle cố ý chậm: mỗi lần BFS lấy một đỉnh lại quét toàn bộ danh sách m cạnh, lặp cho tới m cạnh bị thử xóa. Cận thô **O(nm²)** cho việc tìm trong ví dụ là đủ để thấy không thích hợp trên đồ thị lớn. Nó chỉ phục vụ kiểm chứng trên n,m nhỏ; thuật toán thực tế nên dùng DFS/BFS O(n+m) hoặc DSU gần tuyến tính.

## 18. Kiểm thử vét cạn 1.100 đồ thị đơn

Với đồ thị đơn vô hướng n đỉnh, có n(n−1)/2 cặp cạnh khả dĩ, mỗi cạnh có hai lựa chọn: có hoặc không. Vì thế tổng số đồ thị gắn nhãn với n từ 0 tới 5:

~~~text
n = 0: 2^0  =    1
n = 1: 2^0  =    1
n = 2: 2^1  =    2
n = 3: 2^3  =    8
n = 4: 2^6  =   64
n = 5: 2^10 = 1024

Tổng: 1+1+2+8+64+1024 = 1100 đồ thị.
~~~

Với từng đồ thị, verify so kết quả của DFS, BFS, DSU với oracle xóa cạnh. Nếu DFS báo true, checkWitness còn kiểm tra các cạnh của chu trình cụ thể. Nếu DFS báo false, kiểm tra hai mảng kết quả rỗng.

Tập này bao gồm đồ thị rỗng, đỉnh cô lập, rừng, cây, tam giác, nhiều vòng và thành phần không liên thông. **Nhưng chưa bao gồm** khuyên hoặc cạnh song song, vì đó là đồ thị đơn; vì thế bài còn có một bộ kiểm thử đa đồ thị.

## 19. Kiểm thử vét cạn 760 đa đồ thị nhỏ

Với n=0..3, xét mọi cặp đầu mút không thứ tự a≤b, bao gồm a=b là khuyên. Mỗi loại cạnh có **0, 1 hoặc 2 bản sao vật lý**. Số loại cạnh là n(n+1)/2, nên số đa đồ thị:

~~~text
n = 0: 3^0 =   1
n = 1: 3^1 =   3
n = 2: 3^3 =  27
n = 3: 3^6 = 729

Tổng: 1+3+27+729 = 760 đa đồ thị.
~~~

Bộ thử này trực tiếp bắt lỗi khi so **parentVertex thay vì parentEdge**, hoặc khi nhập hai cạnh song song mà không giữ ID riêng. Nó còn kiểm tra khuyên ở đỉnh đơn, hai khuyên cùng đỉnh, cạnh song song kèm nhiều thành phần và các cấu hình hỗn hợp.

Đối với mọi ca, chương trình so ba thuật toán với oracle xóa một cạnh và kiểm tra nhân chứng DFS. Số lần so là **760 cấu hình**, không phải 760 lần gọi hàm đơn lẻ.

## 20. Kiểm thử seeded thêm 1.200 đa đồ thị

Bộ kiểm thử tiếp tục tạo **200 đồ thị cho mỗi n=4..9**, tổng 6×200=1.200 cấu hình, bằng Random với seed cố định 2682026.

Mỗi đồ thị có số cạnh được chọn trong khoảng [0,2n+3]; hai đầu mỗi cạnh được lấy độc lập trong [0,n−1]. Điều này cho phép sinh cả cạnh lặp, khuyên, đỉnh cô lập và cấu trúc liên thông ngẫu nhiên.

Tổng cộng có:

~~~text
1.100 đồ thị đơn
  760 đa đồ thị nhỏ vét cạn
1.200 đa đồ thị seeded
----------------------------
3.060 đồ thị được đối chiếu.
~~~

Chương trình còn kiểm tra đầu vào n âm, đầu cạnh ra ngoài phạm vi, danh sách null, cây, khuyên và cạnh song song. Các dòng PASS xác nhận đúng các ca đã thực thi, **không thay thế chứng minh tổng quát** của DFS/BFS/DSU.

## 21. Phân tích thời gian và bộ nhớ

| Phương án | Dữ liệu cần dùng | Thời gian | Bộ nhớ phụ |
| --- | --- | --- | --- |
| DFS lặp với danh sách kề | n đỉnh, m cạnh vật lý | O(n+m) | O(n+m) nếu tính cả adjacency |
| BFS với danh sách kề | n đỉnh, m cạnh vật lý | O(n+m) | O(n+m) nếu tính cả adjacency |
| DSU trên danh sách cạnh | n đỉnh, m cạnh vật lý | O(n+mα(n)) | O(n) |
| Oracle xóa mỗi cạnh, quét danh sách mỗi bước | n,m nhỏ | Cận thô O(nm²) | O(n) mỗi lượt reachability |

DFS/BFS đi qua mỗi đỉnh tối đa một lần và quét mỗi cung kề một lần; với m cạnh có 2m cung, nên O(n+m). DFS lặp giữ stack, parent và nextArc O(n), còn adjacency O(n+m).

DSU dùng các mảng parent,size O(n). Với path compression và union by size, chi phí amortized của find/union là O(α(n)) trong dãy thao tác, α cực chậm tăng. DFS/BFS thường là lựa chọn tự nhiên nếu đồ thị đã có adjacency và cần dựng chu trình; DSU phù hợp nhất khi chỉ cần phát hiện vòng trong quá trình **thêm cạnh**.

Nếu cần **trả mọi chu trình** hoặc **chu trình ngắn nhất**, độ phức tạp khác; đừng suy rộng O(n+m) của bài toán chỉ phát hiện một chu trình sang các yêu cầu đầu ra khó hơn.

## 22. Lỗi phổ biến và bài tập tự luyện

**Những lỗi thường gặp:**

1. Gặp visited neighbor rồi báo chu trình ngay, quên bỏ cung đi ngược trên đúng cạnh cây.
2. Bỏ qua mọi cung tới **đỉnh cha**, khiến cạnh song song bị bỏ sót.
3. Nhầm hai cung vô hướng của cùng một cạnh thành hai cạnh vật lý độc lập.
4. Xóa cạnh trùng mà đề cho phép đa đồ thị.
5. Quên xét khuyên hoặc đọc đầu mút không hợp lệ.
6. Chỉ duyệt thành phần chứa đỉnh 0, bỏ sót chu trình ở thành phần khác.
7. Dùng BFS parent như DFS ancestor khi dựng witness mà không xử lý tổ tiên chung.
8. In một dãy đỉnh đóng nhưng không xác minh ID cạnh thực tế.
9. Quên ngăn xếp DFS khi mô phỏng bản đệ quy, làm sai bất biến tổ tiên.
10. Coi m=n−1 là đủ kết luận cây dù đồ thị không liên thông.
11. Dùng DSU cho việc **xóa cạnh** như thể union có thao tác đảo ngược trực tiếp.
12. Áp dụng logic vô hướng cho đồ thị có hướng.
13. Giả định DFS tìm vòng ngắn nhất thay vì một vòng bất kỳ.
14. Bỏ qua độ sâu call stack nếu dùng DFS đệ quy cho n lớn.
15. Chỉ thử đồ thị có vòng, không thử cây/rừng hoặc các trường hợp biên.

**Bài 1 — Cạnh cha:** dựng danh sách kề của cây 0–1–2. Chạy DFS từ 0, ghi visited và parentEdge tại mỗi đỉnh; chỉ ra tại sao cung quay về cha không tạo chu trình.

**Bài 2 — Cạnh song song:** cho n=2 và hai cạnh ID0=(0,1), ID1=(0,1). Chạy DFS theo ID, chứng minh nhận vòng [0,1,0]; rồi thử thay parentEdge bằng parentVertex và chỉ ra chỗ trả sai.

**Bài 3 — Nhiều thành phần:** một thành phần 0–1–2 là cây, thành phần còn lại là 3–4–5–3. Chạy BFS/DFS theo từng root, xác nhận chu trình ở thành phần thứ hai.

**Bài 4 — Union-Find:** với các cạnh (0,1),(1,2),(3,4),(2,0), viết thành phần DSU sau mỗi cạnh và xác định đúng cạnh nào gây vòng.

**Bài 5 — Tự khôi phục:** bổ sung khả năng trả cycle witness bằng BFS, tìm tổ tiên chung của hai đầu một cạnh ngoài cây, kiểm tra danh sách ID không trùng.

**Bài 6 — Định lý rừng:** dựng một đồ thị n=4,m=3 có chu trình nhưng không liên thông. Tính c và giải thích vì sao điều kiện m=n−c phân biệt rừng với đồ thị đó.

**Bài 7 — Oracle:** với đồ thị n≤4, duyệt mọi tổ hợp cạnh, kiểm tra ba thuật toán với tiêu chuẩn xóa một cạnh rồi xem hai đầu có còn đường đi hay không.

**Bài 8 — Giới hạn đề:** với n rất lớn và m≈n, so DFS lặp với DFS đệ quy về nguy cơ StackOverflowError. Với dữ liệu chỉ có danh sách cạnh và kết quả boolean, đánh giá DSU.

**Tổng kết:** để phát hiện chu trình trong **đồ thị vô hướng**, phải phân biệt cung quay lại trên **chính cạnh cây** với một cạnh vật lý khác nối tới đỉnh đã khám phá. **DFS và BFS** xử lý điều này bằng parentEdge; **DSU** phát hiện khi thêm cạnh nối hai đỉnh đã liên thông. Giữ ID cạnh riêng giúp thuật toán đúng cho cả khuyên và cạnh song song. Phân tích cây duyệt, bất biến thành phần, kiểm tra nhân chứng và oracle xóa cạnh tạo một giải pháp vững chắc, không chỉ là vài dòng kiểm tra visited.
