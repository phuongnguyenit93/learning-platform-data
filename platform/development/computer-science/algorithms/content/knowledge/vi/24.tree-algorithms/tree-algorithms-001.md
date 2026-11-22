# Gốc hóa cây và xử lý theo thứ tự trước, sau

Khi làm việc với **thuật toán trên cây**, rất nhiều phép tính trở nên đơn giản sau khi ta **chọn một đỉnh làm gốc** rồi xét quan hệ **cha–con**. Những gì phụ thuộc kết quả của cha nên xử lý **trước khi đi vào các con** (*preorder, top-down*); những gì phụ thuộc kết quả của các con nên xử lý **sau khi các con hoàn tất** (*postorder, bottom-up*). Sự phân biệt về thời điểm rất quan trọng đối với kích thước cây con, tổng cây con, độ sâu, giá trị DP và truy vấn tổ tiên.

Bài này thuộc nhóm **Thuật toán trên cây** của Computer Science Algorithms, với đề trực tiếp **“Gốc hóa cây và xử lý theo thứ tự trước, sau”**. Ta sẽ định nghĩa gốc hóa, xây DFS enter/exit, chứng minh các bất biến, trải phẳng cây bằng preorder và đoạn [tin,tout), so sánh BFS/DFS, xử lý từ trên xuống/từ dưới lên, thảo luận đổi gốc và các trường hợp biên. Cuối bài là chương trình **Java 17+ hoàn chỉnh** đã chạy thực tế, có thử nghiệm mọi cây gắn nhãn nhỏ cùng nhiều cây ngẫu nhiên và đường thẳng 20.000 đỉnh.

## 1. Từ cây vô hướng đến cây có gốc

Một cây vô hướng liên thông, không có chu trình, có n≥1 đỉnh và chính xác n−1 cạnh. Giữa hai đỉnh bất kỳ tồn tại đúng **một đường đi đơn**. Khi chưa chọn gốc, cạnh (u,v) không xác định u là cha của v hay ngược lại.

Chọn gốc r. Với mỗi đỉnh v≠r, **parent[v]** là đỉnh ngay trước v trên đường đi duy nhất từ r tới v. Mọi đỉnh w thỏa parent[w]=v được gọi là **con của v**. Mã dùng parent[r]=−1 cho gốc.

Các khái niệm gắn với gốc:

- **depth[v]**: số cạnh từ r tới v; depth[r]=0.
- **Ancestor (tổ tiên)**: u nằm trên đường từ r tới v; bài học cho phép u=v.
- **Subtree(v)**: v và tất cả hậu duệ của v theo gốc đã chọn.
- **Lá có gốc**: đỉnh không có con. Gốc có bậc 1 của cây vô hướng vẫn có thể có một con và không phải lá theo nghĩa gốc hóa.

Chọn một root **không sửa tập cạnh**. Đồ thị vẫn vô hướng, thường vẫn lưu hai chiều trong danh sách kề; quan hệ cha–con chỉ tạo hướng tư duy để tính toán.

## 2. Hợp đồng đầu vào: phải là một cây

Phương pháp DFS trên cây thường duyệt mọi hàng xóm khác **đỉnh cha**. Điều đó an toàn vì cây không có chu trình; nếu đầu vào thực sự là đồ thị tổng quát có vòng, cách viết ấy có thể thăm lại một đỉnh và lặp mãi. Nếu đồ thị không liên thông, một root không đến được tất cả các đỉnh.

Vì vậy ví dụ Java nhận:

~~~text
n từ 1 đến 300000.
Đỉnh là các số nguyên 0..n-1.
Danh sách có đúng n-1 cạnh vô hướng vật lý.
Không khuyên, không cạnh song song gây chu trình.
Mọi đỉnh cùng một thành phần liên thông.
root là một đỉnh hợp lệ.
weight có đúng n trọng số đỉnh kiểu long.
~~~

Mã dùng **DSU/Union-Find** kiểm tra cạnh tạo chu trình, đồng thời xác nhận tất cả các đỉnh liên thông. Về toán học, **n−1 cạnh và không chu trình** đã đủ suy ra liên thông, nhưng việc kiểm tra rõ ràng khiến hợp đồng dễ hiểu.

Nếu input là **rừng**, không thể gốc hóa toàn bộ như một cây liên thông theo nghĩa trên. Ta phải chọn **một root cho từng thành phần**, hoặc dùng siêu gốc ảo theo đặc tả bài toán. Không nên tự nối những thành phần không có cạnh thật chỉ vì muốn có một mảng parent duy nhất.

## 3. Ví dụ xuyên suốt: cây bảy đỉnh

Cho n=7, các cạnh được đưa vào theo thứ tự:

~~~text
(0,1), (0,2), (1,3), (1,4), (2,5), (5,6)
~~~

Chọn root=0:

~~~text
          0
        /   \
       1     2
      / \     \
     3   4     5
                \
                 6
~~~

Ta có:

~~~text
parent = [-1,0,0,1,1,2,5]
depth  = [ 0,1,1,2,2,2,3]

subtree(1) = {1,3,4}
subtree(2) = {2,5,6}
subtree(0) = {0,1,2,3,4,5,6}
~~~

Thứ tự cạnh trong adjacency tác động tới **thứ tự thử các con**. Nếu con 1 được xét trước con 2 thì preorder khác với trường hợp xét con 2 trước. Tuy nhiên parent/depth, số đỉnh cây con và quan hệ tổ tiên **không phụ thuộc thứ tự kề** khi gốc và tập cạnh giữ nguyên.

## 4. Preorder: xử lý khi bước vào đỉnh

**Preorder (thứ tự trước)** ghi nhận v khi **vừa được khám phá**, trước khi đi sâu vào bất cứ con nào:

~~~text
dfs(v, parent):
    ENTER(v)
    for mỗi w kề v:
        if w == parent: continue
        dfs(w, v)
~~~

Với cây ví dụ, duyệt các con theo thứ tự input:

~~~text
preorder = [0,1,3,4,2,5,6]
~~~

**Tính chất:** một đỉnh luôn xuất hiện **trước mọi hậu duệ**. Do đó preorder tự nhiên để tính những giá trị cần cha:

~~~text
depth[child] = depth[parent] + 1
distFromRoot[child] = distFromRoot[parent]
                      + edgeWeight(parent,child)
~~~

Cần phân biệt **trọng số cạnh** trong công thức distFromRoot với **trọng số tại đỉnh** dùng để tính subtreeSum của chương trình Java. Đây là hai bài toán khác nhau.

Preorder không phải thứ tự đánh số tăng dần và cũng không bắt buộc độ sâu tăng dần toàn cục. DFS có thể đi rất sâu trong nhánh đầu trước khi quay ra xử lý một con khác ở độ sâu 1.

## 5. Postorder: xử lý khi rời đỉnh

**Postorder (thứ tự sau)** ghi nhận v **sau khi tất cả cây con của v được duyệt xong**:

~~~text
dfs(v, parent):
    for mỗi w kề v:
        if w == parent: continue
        dfs(w, v)
    EXIT(v)
~~~

Cây ví dụ:

~~~text
postorder = [3,4,1,6,5,2,0]
~~~

**Tính chất:** mọi hậu duệ đứng **trước tổ tiên** trong postorder. Vì vậy postorder là thứ tự tự nhiên cho bài toán tính từ con lên cha:

~~~text
subtreeSize[v] = 1 + Σ subtreeSize[w]
subtreeSum[v]  = weight[v] + Σ subtreeSum[w]
                 (w chạy qua các con trực tiếp của v)
~~~

Không được tính những tổng này ngay tại enter(v), vì các giá trị của con còn chưa hoàn chỉnh. Một DFS có cả sự kiện enter/exit có thể tạo **cả preorder lẫn postorder trong một lượt**, không cần chạy hai DFS tách biệt.

## 6. Preorder khác BFS và thứ tự độ sâu

BFS từ root đi theo độ sâu tăng dần, nên vẫn có thể xác định đúng parent/depth trên cây. Nhưng thứ tự BFS **khác preorder DFS** nói chung:

~~~text
BFS:       [0,1,2,3,4,5,6]
Preorder:  [0,1,3,4,2,5,6]
Postorder: [3,4,1,6,5,2,0]
~~~

Nếu chỉ cần khoảng cách tính bằng số cạnh tới gốc, BFS đủ đúng. Nếu cần **cây con chiếm đoạn liên tiếp trong một mảng**, không thể tự ý dùng thứ tự BFS thay cho DFS preorder.

Một thứ tự mà **cha trước con** đủ để truyền thông tin top-down. Một thứ tự mà **con trước cha** đủ để tính các tổng bottom-up. Nhưng tính chất mạnh hơn **mọi cây con là một đoạn liên tiếp** đến từ việc DFS đi hết một cây con trước khi sang nhánh khác.

## 7. DFS enter/exit với đồng hồ tăng khi enter

Có thể kết hợp hai lượt xử lý trong một dạng mã ngắn:

~~~text
clock = 0

dfs(v,p):
    parent[v] = p
    tin[v] = clock
    preorder[clock] = v
    clock++

    subtreeSize[v] = 1
    subtreeSum[v] = weight[v]

    for w kề v:
        if w == p: continue
        depth[w] = depth[v] + 1
        dfs(w,v)
        subtreeSize[v] += subtreeSize[w]
        subtreeSum[v] += subtreeSum[w]

    tout[v] = clock
    postorder.add(v)
~~~

**Quy ước đồng hồ cực quan trọng:** clock **chỉ tăng khi enter**, nên tin[v] là **vị trí của v trong preorder** và tout[v] là **chỉ số kết thúc không bao gồm**. Không tăng clock tại exit.

Có một quy ước Euler tour khác tăng timestamp ở cả enter và exit. Quy ước ấy vẫn hữu ích cho các bài khác nhưng **không được lấy tout−tin làm kích thước cây con** nếu dùng 2n thời điểm thay vì n vị trí enter.

## 8. Cài đặt DFS lặp bằng frame thay vì đệ quy sâu

DFS đệ quy đơn giản nhưng một cây hình đường thẳng có chiều cao n−1 có thể làm tràn call stack của JVM (StackOverflowError). Mã hoàn chỉnh dùng ArrayDeque và **frame** lưu:

~~~text
vertex        = đỉnh hiện tại
parent        = cha trong cây đã chọn gốc
nextNeighbor  = index hàng xóm tiếp theo chưa xét
~~~

Với mỗi frame trên đỉnh stack:

1. Nếu còn hàng xóm, đọc một hàng xóm w rồi tăng nextNeighbor.
2. Nếu w bằng parent, bỏ qua để không đi ngược cạnh cha.
3. Nếu w là con, đặt parent[w], depth[w], thực hiện **ENTER(w)** và push frame mới.
4. Nếu không còn hàng xóm, thực hiện **EXIT(v)**, pop frame và cộng kết quả cây con của v lên cha.

Khác với cách push tất cả con ngay lập tức, frame giữ đỉnh cha **trên stack cho tới khi các cây con hoàn tất**. Điều này mô phỏng đúng đệ quy và bảo đảm thời điểm exit đáng tin cậy.

**Bất biến:** tại enter(v), parent/depth của v đã đúng, còn số lượng/tổng đang được khởi tạo; tại exit(v), mọi hậu duệ đã exit và tổng của v đã nhận đủ từ các con. Mỗi đỉnh được enter và exit đúng một lần vì input đã được xác minh là cây.

## 9. Tính kích thước cây con

Đặt subtreeSize[v] là số đỉnh trong cây con v, **bao gồm chính v**. Ban đầu tại enter(v):

~~~text
subtreeSize[v] = 1
~~~

Mỗi lần một con w của v hoàn tất:

~~~text
subtreeSize[v] += subtreeSize[w]
~~~

Với cây bảy đỉnh:

| Đỉnh | Các con | subtreeSize |
| --- | --- | ---: |
| 3 | Không | 1 |
| 4 | Không | 1 |
| 1 | 3, 4 | 3 |
| 6 | Không | 1 |
| 5 | 6 | 2 |
| 2 | 5 | 3 |
| 0 | 1, 2 | 7 |

Kết quả mảng:

~~~text
subtreeSize = [7,3,3,1,1,2,1]
~~~

Hai kiểm tra hữu ích: **subtreeSize[root]=n** và mọi lá có cây con kích thước 1. Nếu một đỉnh chưa phải root mà kích thước cây con bằng n trong một cây nhiều đỉnh, có thể đã nhầm gốc hoặc cộng nhầm phía cha.

## 10. Tính tổng giá trị cây con có số âm

Mỗi đỉnh có trọng số weight[v]. Mục tiêu tính tổng **trọng số đỉnh** trong cây con:

~~~text
subtreeSum[v] = weight[v] + Σ subtreeSum[w]
                                   với w là con của v.
~~~

Ví dụ:

~~~text
weight = [5,-2,3,7,1,-4,6]

sum[3]=7
sum[4]=1
sum[1]=-2+7+1=6

sum[6]=6
sum[5]=-4+6=2
sum[2]=3+2=5

sum[0]=5+6+5=16

subtreeSum = [16,6,5,7,1,2,6].
~~~

Số âm không làm công thức mất hiệu lực, vì mỗi cây con là hợp của đỉnh gốc và các cây con của những người con, **không giao nhau**. Số học cần đủ rộng: mã dùng long và Math.addExact để **phát hiện tràn** thay vì âm thầm sai. Nếu kết quả hoặc tổng trung gian vượt giới hạn long, API báo ArithmeticException; bài có tổng rất lớn nên cân nhắc BigInteger hoặc giới hạn đầu vào.

## 11. Trải phẳng cây bằng preorder

Với đồng hồ tăng duy nhất ở enter:

~~~text
tin[v]  = vị trí v trong preorder.
tout[v] = vị trí ngay sau đỉnh cuối thuộc subtree(v).

subtree(v) tương ứng đoạn nửa mở:
preorder[tin[v] .. tout[v])

subtreeSize[v] = tout[v] - tin[v].
~~~

Ví dụ:

~~~text
preorder = [0,1,3,4,2,5,6]
index    =  0 1 2 3 4 5 6

tin  = [0,1,4,2,3,5,6]
tout = [7,4,7,3,4,7,7]

subtree(1) = preorder[1..4) = [1,3,4]
subtree(2) = preorder[4..7) = [2,5,6]
subtree(5) = preorder[5..7) = [5,6].
~~~

Vì DFS **hoàn thành toàn bộ nhánh con hiện tại trước khi bắt đầu nhánh khác**, mọi đỉnh trong cùng cây con xuất hiện liên tiếp. Đây là nền tảng để chuyển **truy vấn cây con** thành **truy vấn đoạn của một mảng**.

Nếu đặt flattened[tin[v]]=weight[v], tổng cây con tại v là tổng đoạn flattened[tin[v]..tout[v]). Với dữ liệu tĩnh, dùng **prefix sum** cho O(1) mỗi truy vấn. Với cập nhật trọng số đỉnh và truy vấn tổng cây con, Fenwick tree hoặc segment tree trên mảng đã trải phẳng là lựa chọn tự nhiên.

## 12. Kiểm tra tổ tiên bằng hai mốc tin/tout

Với cùng root, hai đỉnh u,v thỏa u là tổ tiên của v (kể cả u=v) khi và chỉ khi:

~~~text
tin[u] <= tin[v] && tin[v] < tout[u]
~~~

Giải thích: toàn bộ đỉnh trong subtree(u) chiếm đoạn [tin[u],tout[u]), và v thuộc subtree(u) đúng khi tin[v] nằm trong đoạn đó. Sau tiền xử lý, điều kiện có chi phí O(1).

Ví dụ:

~~~text
isAncestor(1,4) = true.
isAncestor(2,4) = false.
isAncestor(5,6) = true.
isAncestor(0,0) = true theo quy ước không nghiêm ngặt.
~~~

Hai cây con trong một cây có gốc hoặc **lồng nhau** (một đỉnh là tổ tiên của đỉnh kia) hoặc **rời nhau** (nằm ở các nhánh khác nhau). Vì vậy các khoảng nửa mở của chúng cũng lồng nhau hoặc rời nhau; không có hai subtree giao một phần mà không chứa nhau.

Nếu đề hỏi **tổ tiên nghiêm ngặt**, thêm điều kiện u!=v. Nếu thay root, phải tính lại hoặc suy luận lại tin/tout theo root mới; không được giữ mảng cũ nhưng hiểu cây con theo root khác.

## 13. Chứng minh thứ tự trước, sau là đúng

Đầu vào là một cây liên thông, không chu trình. Root là đỉnh đầu tiên enter, parent[root]=−1 và depth[root]=0.

Khi từ cha v đi xuống hàng xóm w khác cha của v, đường duy nhất từ root tới w đi qua v. Bởi không có chu trình, w chưa từng được khám phá ở nhánh khác. Do đó gán parent[w]=v và depth[w]=depth[v]+1 là đúng. w được ghi vào preorder **sau v**.

Frame của v ở trên stack cho đến khi toàn bộ hàng xóm được xử lý; vì vậy mỗi cây con đã được xử lý xong trước khi v exit. v được ghi vào postorder **sau mọi con và hậu duệ**.

Mỗi đỉnh khác root có đúng một parent trên đường tới root và được thăm đúng một lần; vì cây liên thông nên mọi đỉnh được thăm. Bởi vậy:

~~~text
preorder và postorder đều là hoán vị 0..n-1.
preorder[0] = root.
postorder[n-1] = root.
Với mọi v != root:
    vị trí của parent[v] trong preorder < vị trí của v.
    vị trí của parent[v] trong postorder > vị trí của v.
~~~

Bộ test Java kiểm tra những bất biến này trên hàng nghìn cây, không chỉ trên một ví dụ hình vẽ.

## 14. Chứng minh phép gom cây con là đúng

Chứng minh theo **postorder**.

**Cơ sở:** lá không có con. subtreeSize[leaf]=1 và subtreeSum[leaf]=weight[leaf] đúng vì cây con chỉ có chính nó.

**Bước quy nạp:** giả sử với mọi con w của v, các giá trị đã hoàn tất và đúng. Vì là cây, các cây con của các con trực tiếp **không giao nhau**, và hợp của chúng cộng {v} bằng chính subtree(v). Vì vậy:

~~~text
subtreeSize[v] = 1 + Σ subtreeSize[w].
subtreeSum[v] = weight[v] + Σ subtreeSum[w].
~~~

Đúng vì cộng đủ từng con đúng một lần. Thuật toán chỉ exit(v) sau khi mọi con xong, nên mọi điều kiện quy nạp được bảo đảm.

Với root, subtreeSize[root]=n và subtreeSum[root] là tổng trọng số toàn cây. Đây không phải “phép cộng may mắn” mà là hệ quả cấu trúc của tree.

## 15. Đổi gốc thay đổi cây con, không thay tập cạnh

Nếu chuyển root từ 0 sang 2 trong ví dụ:

~~~text
          2
        /   \
       0     5
       |      \
       1       6
      / \
     3   4
~~~

Ta có:

~~~text
parent mới = [2,0,-1,1,1,2,5].
subtree(0) = {0,1,3,4} nên subtreeSize[0]=4.
subtreeSize[2]=7.
subtreeSum[2]=16.
~~~

Khi root=0, subtreeSize[0]=7; root=2 thì subtreeSize[0]=4. Các giá trị **phụ thuộc root**: parent, depth, cây con, tin/tout. Các đại lượng **không đổi**: số đỉnh/cạnh, đường đi vô hướng và tổng trọng số của toàn cây.

Nếu có nhiều yêu cầu đổi root, chạy lại DFS từ đầu tốn O(n) mỗi lần. Với những hàm mục tiêu phù hợp, kỹ thuật **rerooting DP** có thể tính tất cả phương án root qua hai lượt bottom-up/top-down, nhưng đó là nội dung mở rộng. Không được tự động tái sử dụng các đoạn subtree từ root cũ mà chưa có công thức biến đổi.

## 16. Phân biệt xử lý từ cha xuống và từ con lên

| Bài toán | Phụ thuộc | Thứ tự phù hợp |
| --- | --- | --- |
| parent, depth | Cha đã biết | Preorder / enter |
| distanceFromRoot | Khoảng cách cha và trọng số cạnh | Preorder |
| prefix label từ root | Trạng thái cha | Preorder |
| subtreeSize | Kích thước của tất cả con | Postorder / exit |
| subtreeSum | Tổng cây con của tất cả con | Postorder |
| height[v] | 1+max(height[con]) | Postorder |
| DP đếm cấu hình trong subtree | Kết quả DP của con | Thường postorder |
| DP tính đại lượng cho mọi root | Kết quả con và phần ngoài subtree | Thường một pass sau + một pass trước |
| Truy vấn tổng cây con | Đoạn preorder và cấu trúc đoạn | DFS enter/exit |

Không nên áp dụng máy móc câu “lúc nào cũng duyệt trước rồi duyệt sau”. Hãy nhìn **đồ thị phụ thuộc** của trạng thái: nếu v cần kết quả của con, đợi con hoàn tất; nếu con cần kết quả của v, tính ở cha trước.

## 17. Độ phức tạp và nguy cơ tràn stack

Với một cây n đỉnh có m=n−1 cạnh:

- Dựng danh sách kề: O(n), tổng 2(n−1) entry.
- Kiểm tra tính hợp lệ bằng DSU: O(n α(n)) amortized, α là nghịch đảo Ackermann tăng rất chậm.
- DFS lặp: **O(n)** thời gian vì mỗi đỉnh enter/exit một lần, mỗi cạnh được xem theo tối đa hai hướng.
- Mảng parent, depth, tin, tout, preorder, postorder, subtreeSize, subtreeSum và stack: **O(n)** bộ nhớ.
- isAncestor sau tiền xử lý: O(1).
- Truy vấn subtreeSum với trọng số không đổi: O(1).
- Nếu bỏ bước DSU do input chắc chắn là cây, toàn bộ gốc hóa/duyệt có O(n) thời gian và O(n) bộ nhớ.

Trên cây đường thẳng, DFS đệ quy có thể gọi n tầng và gây StackOverflowError. **DFS lặp bằng stack trên heap** tránh lỗi call stack đó, dù vẫn dùng O(n) bộ nhớ; phần bộ nhớ này là chủ động và quản lý được.

## 18. Java 17+: chương trình hoàn chỉnh

Lưu mã bên dưới trong tệp **RootedTreeTraversals.java**. Lớp nhận cây vô hướng và trọng số tại **đỉnh**, xác nhận đầu vào bằng DSU, gốc hóa ở root chỉ định, rồi dùng DFS lặp với frame(vertex,parent,nextNeighbor). Thuật toán ghi:

- parent/depth khi bước từ cha tới con;
- preorder và tin ở sự kiện enter;
- postorder và tout ở sự kiện exit;
- subtreeSize/subtreeSum được khởi tạo tại enter và cộng từ con lên cha khi con exit.

Kiểu record Analysis cung cấp **bản sao phòng vệ** cho các mảng, đồng thời có isAncestor bằng đoạn nửa mở. Mã có kiểm thử độc lập của parent/depth, các tập subtree, tổng trọng số, thứ tự trước/sau và trường hợp cây sâu.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;

public final class RootedTreeTraversals {
    public record Edge(int u, int v) { }

    public record Analysis(int root, int[] parent, int[] depth,
                           int[] preorder, int[] postorder,
                           int[] tin, int[] tout,
                           int[] subtreeSize, long[] subtreeSum) {
        public Analysis {
            parent = parent.clone();
            depth = depth.clone();
            preorder = preorder.clone();
            postorder = postorder.clone();
            tin = tin.clone();
            tout = tout.clone();
            subtreeSize = subtreeSize.clone();
            subtreeSum = subtreeSum.clone();
        }

        @Override public int[] parent() { return parent.clone(); }
        @Override public int[] depth() { return depth.clone(); }
        @Override public int[] preorder() { return preorder.clone(); }
        @Override public int[] postorder() { return postorder.clone(); }
        @Override public int[] tin() { return tin.clone(); }
        @Override public int[] tout() { return tout.clone(); }
        @Override public int[] subtreeSize() { return subtreeSize.clone(); }
        @Override public long[] subtreeSum() { return subtreeSum.clone(); }

        public boolean isAncestor(int ancestor, int descendant) {
            int n = parent.length;
            if (ancestor < 0 || ancestor >= n ||
                    descendant < 0 || descendant >= n) {
                throw new IllegalArgumentException("invalid vertex");
            }
            return tin[ancestor] <= tin[descendant] &&
                    tin[descendant] < tout[ancestor];
        }
    }

    private static final class Frame {
        final int vertex;
        final int parent;
        int nextNeighbor;

        Frame(int vertex, int parent) {
            this.vertex = vertex;
            this.parent = parent;
        }
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
            int x = find(a), y = find(b);
            if (x == y) {
                return false;
            }
            if (size[x] < size[y]) {
                int temp = x;
                x = y;
                y = temp;
            }
            parent[y] = x;
            size[x] += size[y];
            return true;
        }
    }

    private RootedTreeTraversals() { }

    public static Analysis analyze(int n, List<Edge> edges,
                                   long[] weight, int root) {
        if (n < 1 || n > 300_000 || edges == null ||
                edges.size() != n - 1 || weight == null ||
                weight.length != n || root < 0 || root >= n) {
            throw new IllegalArgumentException("invalid tree arguments");
        }
        DSU dsu = new DSU(n);
        List<List<Integer>> adjacency = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            adjacency.add(new ArrayList<>());
        }
        for (Edge edge : edges) {
            if (edge == null || edge.u() < 0 || edge.u() >= n ||
                    edge.v() < 0 || edge.v() >= n ||
                    !dsu.union(edge.u(), edge.v())) {
                throw new IllegalArgumentException("not a simple tree");
            }
            adjacency.get(edge.u()).add(edge.v());
            adjacency.get(edge.v()).add(edge.u());
        }
        int representative = dsu.find(root);
        for (int v = 0; v < n; v++) {
            if (dsu.find(v) != representative) {
                throw new IllegalArgumentException("disconnected graph");
            }
        }

        int[] parent = new int[n];
        int[] depth = new int[n];
        int[] preorder = new int[n];
        int[] postorder = new int[n];
        int[] tin = new int[n];
        int[] tout = new int[n];
        int[] size = new int[n];
        long[] sum = new long[n];
        Arrays.fill(parent, -1);

        ArrayDeque<Frame> stack = new ArrayDeque<>();
        stack.push(new Frame(root, -1));
        size[root] = 1;
        sum[root] = weight[root];
        tin[root] = 0;
        preorder[0] = root;
        int preCount = 1, postCount = 0;

        while (!stack.isEmpty()) {
            Frame frame = stack.peek();
            int v = frame.vertex;
            List<Integer> neighbors = adjacency.get(v);
            if (frame.nextNeighbor < neighbors.size()) {
                int w = neighbors.get(frame.nextNeighbor++);
                if (w == frame.parent) {
                    continue;
                }
                parent[w] = v;
                depth[w] = depth[v] + 1;
                tin[w] = preCount;
                preorder[preCount++] = w;
                size[w] = 1;
                sum[w] = weight[w];
                stack.push(new Frame(w, v));
            } else {
                stack.pop();
                postorder[postCount++] = v;
                tout[v] = preCount;
                if (frame.parent != -1) {
                    size[frame.parent] += size[v];
                    sum[frame.parent] =
                            Math.addExact(sum[frame.parent], sum[v]);
                }
            }
        }
        if (preCount != n || postCount != n) {
            throw new AssertionError("tree traversal incomplete");
        }
        return new Analysis(root, parent, depth, preorder, postorder,
                            tin, tout, size, sum);
    }

    private static List<Edge> decodePrufer(int n, int code) {
        if (n == 1) {
            return List.of();
        }
        int[] degree = new int[n];
        Arrays.fill(degree, 1);
        int[] sequence = new int[n - 2];
        for (int i = 0; i < sequence.length; i++) {
            sequence[i] = code % n;
            code /= n;
            degree[sequence[i]]++;
        }
        List<Edge> edges = new ArrayList<>();
        for (int next : sequence) {
            int leaf = 0;
            while (degree[leaf] != 1) {
                leaf++;
            }
            edges.add(new Edge(leaf, next));
            degree[leaf]--;
            degree[next]--;
        }
        int left = -1, right = -1;
        for (int i = 0; i < n; i++) {
            if (degree[i] == 1) {
                if (left == -1) {
                    left = i;
                } else {
                    right = i;
                }
            }
        }
        edges.add(new Edge(left, right));
        return edges;
    }

    private static void checkAgainstIndependentOracle(int n,
                     List<Edge> edges, long[] weight, int root) {
        Analysis a = analyze(n, edges, weight, root);
        int[] parent = a.parent(), depth = a.depth();
        int[] pre = a.preorder(), post = a.postorder();
        int[] tin = a.tin(), tout = a.tout();
        int[] size = a.subtreeSize();
        long[] sum = a.subtreeSum();

        List<List<Integer>> adj = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            adj.add(new ArrayList<>());
        }
        for (Edge e : edges) {
            adj.get(e.u()).add(e.v());
            adj.get(e.v()).add(e.u());
        }
        int[] bfsParent = new int[n], bfsDepth = new int[n];
        Arrays.fill(bfsParent, -2);
        bfsParent[root] = -1;
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        queue.add(root);
        while (!queue.isEmpty()) {
            int v = queue.remove();
            for (int w : adj.get(v)) {
                if (bfsParent[w] == -2) {
                    bfsParent[w] = v;
                    bfsDepth[w] = bfsDepth[v] + 1;
                    queue.add(w);
                }
            }
        }
        if (!Arrays.equals(parent, bfsParent) ||
                !Arrays.equals(depth, bfsDepth)) {
            throw new AssertionError("parent/depth mismatch");
        }

        boolean[] seenPre = new boolean[n], seenPost = new boolean[n];
        int[] postPosition = new int[n];
        for (int i = 0; i < n; i++) {
            if (pre[i] < 0 || pre[i] >= n || seenPre[pre[i]] ||
                    post[i] < 0 || post[i] >= n || seenPost[post[i]]) {
                throw new AssertionError("order is not a permutation");
            }
            seenPre[pre[i]] = true;
            seenPost[post[i]] = true;
            postPosition[post[i]] = i;
            if (tin[pre[i]] != i) {
                throw new AssertionError("tin/preorder disagreement");
            }
        }
        if (pre[0] != root || post[n - 1] != root) {
            throw new AssertionError("root order mismatch");
        }

        for (int v = 0; v < n; v++) {
            boolean[] reachable = new boolean[n];
            ArrayDeque<Integer> frontier = new ArrayDeque<>();
            reachable[v] = true;
            frontier.add(v);
            int count = 0;
            long total = 0;
            while (!frontier.isEmpty()) {
                int x = frontier.remove();
                count++;
                total = Math.addExact(total, weight[x]);
                for (int y : adj.get(x)) {
                    if ((x == v && y == bfsParent[v]) ||
                            (x == bfsParent[v] && y == v)) {
                        continue;
                    }
                    if (!reachable[y]) {
                        reachable[y] = true;
                        frontier.add(y);
                    }
                }
            }
            if (count != size[v] || total != sum[v] ||
                    tout[v] - tin[v] != count) {
                throw new AssertionError("subtree oracle mismatch");
            }
            if (v != root &&
                    (tin[parent[v]] >= tin[v] ||
                     postPosition[parent[v]] <= postPosition[v])) {
                throw new AssertionError("parent order mismatch");
            }

            for (int u = 0; u < n; u++) {
                boolean ancestor = false;
                for (int x = u; x != -1; x = bfsParent[x]) {
                    if (x == v) {
                        ancestor = true;
                        break;
                    }
                }
                boolean interval = tin[v] <= tin[u] && tin[u] < tout[v];
                if (a.isAncestor(v, u) != ancestor ||
                        interval != ancestor || reachable[u] != ancestor) {
                    throw new AssertionError("ancestor/interval mismatch");
                }
            }
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input was accepted");
    }

    private static void verify() {
        int exhaustive = 0;
        for (int n = 1; n <= 6; n++) {
            int treeCount = n == 1 ? 1 : 1;
            for (int i = 0; i < n - 2; i++) {
                treeCount *= n;
            }
            for (int code = 0; code < treeCount; code++) {
                List<Edge> edges = decodePrufer(n, code);
                long[] weights = new long[n];
                for (int v = 0; v < n; v++) {
                    weights[v] = (v * 7L + code) % 13 - 6;
                }
                for (int root = 0; root < n; root++) {
                    checkAgainstIndependentOracle(n, edges, weights, root);
                    exhaustive++;
                }
            }
        }

        Random random = new Random(3132026L);
        int seeded = 0;
        for (int trial = 0; trial < 300; trial++) {
            int n = 7 + random.nextInt(20);
            List<Edge> edges = new ArrayList<>();
            for (int v = 1; v < n; v++) {
                edges.add(new Edge(v, random.nextInt(v)));
            }
            Collections.shuffle(edges, random);
            long[] weights = new long[n];
            for (int v = 0; v < n; v++) {
                weights[v] = random.nextInt(41) - 20;
            }
            checkAgainstIndependentOracle(n, edges, weights,
                    random.nextInt(n));
            seeded++;
        }

        int n = 20_000;
        List<Edge> chain = new ArrayList<>();
        long[] unitWeight = new long[n];
        Arrays.fill(unitWeight, 1);
        for (int v = 1; v < n; v++) {
            chain.add(new Edge(v - 1, v));
        }
        Analysis longChain = analyze(n, chain, unitWeight, n - 1);
        if (longChain.preorder()[0] != n - 1 ||
                longChain.postorder()[n - 1] != n - 1 ||
                longChain.subtreeSize()[n - 1] != n ||
                longChain.subtreeSum()[n - 1] != n ||
                longChain.depth()[0] != n - 1) {
            throw new AssertionError("deep iterative DFS failed");
        }

        expectInvalid(() -> analyze(0, List.of(), new long[0], 0));
        expectInvalid(() -> analyze(2, List.of(), new long[2], 0));
        expectInvalid(() -> analyze(2, List.of(new Edge(0, 0)),
                                   new long[2], 0));
        expectInvalid(() -> analyze(2, List.of(new Edge(0, 2)),
                                   new long[2], 0));
        expectInvalid(() -> analyze(3, List.of(new Edge(0, 1),
                              new Edge(0, 1)), new long[3], 0));
        expectInvalid(() -> analyze(4, List.of(new Edge(0, 1),
                    new Edge(1, 2), new Edge(2, 0)), new long[4], 0));
        expectInvalid(() -> analyze(2, List.of(new Edge(0, 1)),
                                   new long[2], -1));
        expectInvalid(() -> analyze(2, List.of(new Edge(0, 1)),
                                   new long[1], 0));
        try {
            analyze(2, List.of(new Edge(0, 1)),
                    new long[] {Long.MAX_VALUE, 1}, 0);
            throw new AssertionError("overflow was not detected");
        } catch (ArithmeticException expected) {
        }

        Analysis sample = analyze(2, List.of(new Edge(0, 1)),
                                  new long[] {3, 4}, 0);
        int[] external = sample.parent();
        external[1] = 123;
        if (sample.parent()[1] != 0) {
            throw new AssertionError("defensive copy failed");
        }

        System.out.println("Verified " + exhaustive +
                " exhaustive rooted trees: PASS");
        System.out.println("Verified " + seeded +
                " seeded trees: PASS");
        System.out.println("Deep chain of " + n + " vertices: PASS");
        System.out.println("Invalid inputs and defensive copies: PASS");
    }

    public static void main(String[] args) {
        List<Edge> edges = List.of(new Edge(0, 1), new Edge(0, 2),
                new Edge(1, 3), new Edge(1, 4),
                new Edge(2, 5), new Edge(5, 6));
        long[] weight = {5, -2, 3, 7, 1, -4, 6};
        Analysis a = analyze(7, edges, weight, 0);
        System.out.println("Preorder: " + Arrays.toString(a.preorder()));
        System.out.println("Postorder: " + Arrays.toString(a.postorder()));
        System.out.println("Parent: " + Arrays.toString(a.parent()));
        System.out.println("Depth: " + Arrays.toString(a.depth()));
        System.out.println("tin: " + Arrays.toString(a.tin()));
        System.out.println("tout: " + Arrays.toString(a.tout()));
        System.out.println("subtreeSize: " +
                Arrays.toString(a.subtreeSize()));
        System.out.println("subtreeSum: " +
                Arrays.toString(a.subtreeSum()));
        System.out.println("1 ancestor of 4: " +
                a.isAncestor(1, 4));
        System.out.println("2 ancestor of 4: " +
                a.isAncestor(2, 4));
        System.out.println("Preorder segment of subtree(1): " +
                Arrays.toString(Arrays.copyOfRange(a.preorder(),
                        a.tin()[1], a.tout()[1])));
        Analysis rerooted = analyze(7, edges, weight, 2);
        System.out.println("Root 2 parent: " +
                Arrays.toString(rerooted.parent()));
        System.out.println("Root 2 subtreeSize(0): " +
                rerooted.subtreeSize()[0]);
        System.out.println("Root 2 total weight: " +
                rerooted.subtreeSum()[2]);
        verify();
    }

~~~

Biên dịch và chạy:

~~~bash
javac RootedTreeTraversals.java
java RootedTreeTraversals
~~~

**Stdout chính xác** đã quan sát được:

~~~text
Preorder: [0, 1, 3, 4, 2, 5, 6]
Postorder: [3, 4, 1, 6, 5, 2, 0]
Parent: [-1, 0, 0, 1, 1, 2, 5]
Depth: [0, 1, 1, 2, 2, 2, 3]
tin: [0, 1, 4, 2, 3, 5, 6]
tout: [7, 4, 7, 3, 4, 7, 7]
subtreeSize: [7, 3, 3, 1, 1, 2, 1]
subtreeSum: [16, 6, 5, 7, 1, 2, 6]
1 ancestor of 4: true
2 ancestor of 4: false
Preorder segment of subtree(1): [1, 3, 4]
Root 2 parent: [2, 0, -1, 1, 1, 2, 5]
Root 2 subtreeSize(0): 4
Root 2 total weight: 16
Verified 8477 exhaustive rooted trees: PASS
Verified 300 seeded trees: PASS
Deep chain of 20000 vertices: PASS
Invalid inputs and defensive copies: PASS
~~~

Trong kết quả, preorder[0]=0, postorder[6]=0, cây con của 1 là đoạn [1,4) chứa [1,3,4], tổng gốc là 16. Sau khi đổi gốc sang 2, parent đổi và subtreeSize[0]=4 trong khi tổng toàn cây vẫn là 16.

## 19. Oracle độc lập cho parent, depth và cây con

Để kiểm thử chính xác, không nên chỉ viết một bản DFS khác dùng cùng công thức và so hai kết quả. Chương trình xây một **BFS** độc lập từ root để lấy parent/depth, vì trong cây có **một đường đi duy nhất** từ root đến mọi đỉnh.

Với mỗi đỉnh v, để kiểm tra subtree(v):

1. Nếu v≠root, **xóa riêng cạnh nối v với parent[v]**.
2. BFS từ v trong đồ thị sau khi xóa cạnh ấy.
3. Thành phần liên thông chứa v đúng là subtree(v).
4. Đếm số đỉnh và cộng trọng số từ tập độc lập này, so với subtreeSize[v], subtreeSum[v].
5. So với số vị trí trong đoạn [tin[v],tout[v]) và quan hệ tổ tiên từ đường parent BFS.

Kết hợp kiểm tra preorder/postorder là **hoán vị** và cha có vị trí đúng chiều, bộ test phát hiện được lỗi ghi đè parent, tính cây con sai, sai đoạn nửa mở hoặc thứ tự exit chưa hoàn tất.

## 20. Vét cạn toàn bộ cây gắn nhãn nhỏ

Dùng **mã Prüfer**: với n≥2, mỗi cây vô hướng gắn nhãn n đỉnh tương ứng một dãy có n−2 phần tử, mỗi phần tử thuộc 0..n−1. Do đó có n^(n−2) cây khác nhau. Với n=1, có một cây đơn đỉnh.

Mã giải mã mọi dãy Prüfer cho n=1..6, và đối với **mỗi cây** thử **mọi root**:

~~~text
n=1:    1 cây x 1 root =    1.
n=2:    1 cây x 2 root =    2.
n=3:    3 cây x 3 root =    9.
n=4:   16 cây x 4 root =   64.
n=5:  125 cây x 5 root =  625.
n=6: 1296 cây x 6 root = 7776.

Tổng = 8477 trường hợp cây có gốc.
~~~

Trọng số được tạo bằng công thức xác định và gồm giá trị âm, 0 và dương. Mỗi trường hợp được so với oracle BFS/xóa cạnh cha, và kiểm tra interval của tất cả cặp u,v.

**8.477 là số lần kiểm thử theo cặp (cây, root)**, không phải số lượng cây vô hướng khác nhau. Việc thử đủ lựa chọn gốc rất quan trọng để phát hiện code chỉ đúng khi root=0 hoặc root có bậc lớn.

## 21. Kiểm thử cây có cấu trúc khác và input biên

Mã tạo 300 cây bằng Random(3132026L), kích thước n từ 7 đến 26; với v=1..n−1, nối v với một đỉnh có chỉ số nhỏ hơn v để bảo đảm là cây, rồi **xáo trộn danh sách cạnh** trước khi phân tích. Root ngẫu nhiên, trọng số từng đỉnh từ −20 đến 20, và toàn bộ kết quả được đối chiếu với oracle độc lập.

Ngoài ra, chương trình dựng một **đường thẳng 20.000 đỉnh** và đặt root ở đầu mút n−1; kỳ vọng depth[0]=19.999, subtreeSize[root]=20.000, subtreeSum[root]=20.000 nếu tất cả giá trị bằng 1. Bản lặp vượt qua bài kiểm thử này mà không tràn call stack.

Các input lỗi được từ chối: n=0; thiếu cạnh; self-loop; đầu mút ngoài phạm vi; hai cạnh trùng gây vòng; tam giác và một đỉnh cô lập; root âm; mảng trọng số sai kích thước. Tràn long được phát hiện bằng ArithmeticException. Bản sao mảng ngoài record không được thay đổi kết quả lưu bên trong.

## 22. Những lỗi rất dễ mắc

1. Nhầm đồ thị có chu trình là cây rồi chỉ bỏ parent, dẫn tới duyệt lặp hoặc trùng đỉnh.
2. Không nêu root nhưng lại sử dụng các khái niệm phụ thuộc root.
3. Quên parent[root]=−1, depth[root]=0.
4. Quên bỏ cạnh từ v về parent[v] trong adjacency vô hướng.
5. Tính subtreeSum hoặc subtreeSize quá sớm trước khi mọi con hoàn tất.
6. Quên tính chính v trong subtreeSize; lá phải có size=1.
7. Trộn trọng số tại **đỉnh** với trọng số trên **cạnh**.
8. Tăng clock cả ở exit rồi áp dụng tout−tin=subtreeSize.
9. Nhầm đoạn [tin,tout) với [tin,tout] bao gồm phần tử cuối.
10. Coi BFS hoặc thứ tự tăng depth là preorder DFS và dùng truy vấn đoạn subtree.
11. Duyệt các con bằng stack nhưng không bảo toàn enter/exit theo frame.
12. Khẳng định preorder và postorder là duy nhất bất chấp thứ tự con.
13. Tái sử dụng parent/tin/tout sau khi đổi root mà không tính lại.
14. Dùng DFS đệ quy với đường thẳng có hàng trăm nghìn đỉnh dẫn tới StackOverflowError.
15. Dùng int để cộng trọng số lớn hoặc không phát hiện overflow.
16. Không kiểm tra n=1, root ở lá, cây hình sao hoặc cây hình đường.
17. Chỉ kiểm tra giá trị root mà không kiểm tra từng subtree và thứ tự cha/con.
18. Nhầm postorder là “mọi đỉnh phải được sắp độ sâu giảm dần”. Điều cần là mỗi **con đứng trước cha**, không phải thứ tự độ sâu giảm toàn cục.

## 23. Bài tập tự luyện

**Bài 1:** Vẽ cây ví dụ và ghi sự kiện ENTER/EXIT, preorder/postorder, parent/depth. Chỉ ra tại sao hậu thứ tự kết thúc bằng root.

**Bài 2:** Tính subtreeSize và subtreeSum của các đỉnh trong ví dụ. Kiểm tra subtreeSize=[7,3,3,1,1,2,1] và subtreeSum=[16,6,5,7,1,2,6].

**Bài 3:** Với tin=[0,1,4,2,3,5,6] và tout=[7,4,7,3,4,7,7], tìm đoạn của subtree(1), subtree(5); kiểm tra isAncestor(1,4), isAncestor(2,4), isAncestor(5,6).

**Bài 4:** Đặt root=2 thay vì 0, tính parent và subtreeSize mới tại đỉnh 0. Giải thích tính phụ thuộc gốc của cây con.

**Bài 5:** Định nghĩa height[v]=0 cho lá, height[v]=1+max(height[con]) cho nút khác. Viết phép gom bottom-up theo postorder.

**Bài 6:** Thêm trọng số cho mỗi cạnh, tính distanceFromRoot trong preorder. Giải thích khác biệt so với tổng trọng số đỉnh subtreeSum.

**Bài 7:** Dùng flattened[tin[v]]=weight[v], xây prefix sum để trả tổng subtree tĩnh trong O(1). Mở rộng sang Fenwick khi một trọng số đỉnh có thể được cập nhật.

**Bài 8:** Tự cài DFS lặp theo frame có nextNeighbor, chạy trên đường thẳng 20.000 đỉnh. So với đệ quy về nguy cơ StackOverflowError.

**Bài 9:** Tạo một đồ thị có n=4, m=3 nhưng ba cạnh lập tam giác và đỉnh cuối cô lập. Giải thích vì sao m=n−1 không đủ kết luận là cây khi chưa xác nhận liên thông.

**Bài 10:** Viết một bộ so sánh độc lập bằng cách xóa cạnh cha rồi BFS để xác minh cây con của từng đỉnh. Thử cây sao, cây đường, cây một đỉnh và tất cả root.

**Kết luận:** **Gốc hóa cây** chuyển góc nhìn một đồ thị vô hướng thành quan hệ cha–con. **Preorder** giúp tính những gì phụ thuộc cha; **postorder** giúp tổng hợp những gì phụ thuộc con. Một DFS với sự kiện enter/exit có thể cho parent/depth, preorder/postorder, kích thước/tổng cây con và đoạn nửa mở [tin,tout) trong một lượt. Hiểu đúng bất biến “cha trước con / con trước cha” và “mọi cây con là đoạn liên tiếp trong preorder” là nền tảng quan trọng của DP trên cây, truy vấn cây con và các bài đổi gốc về sau.
