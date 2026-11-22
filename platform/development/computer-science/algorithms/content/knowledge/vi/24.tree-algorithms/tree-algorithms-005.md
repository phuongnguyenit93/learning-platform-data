# Tổ tiên chung thấp nhất (LCA)

## 1. Khái niệm LCA trên cây có gốc

Cho một **cây có gốc (rooted tree)** T, một đỉnh a được gọi là **tổ tiên** của đỉnh v nếu a nằm trên đường duy nhất từ gốc đến v. Theo quy ước thường dùng, **mỗi đỉnh là tổ tiên của chính nó**. Một đỉnh v khác gốc có đúng một cha, ký hiệu parent[v].

**Lowest Common Ancestor (LCA)** của hai đỉnh u và v là **tổ tiên chung có độ sâu lớn nhất**, nghĩa là tổ tiên chung nằm gần hai đỉnh nhất về phía dưới cây.

Cây ví dụ với gốc 0:

~~~text
              0
           /  |  \
          1   2   3
         / \ / \
        4  5 6  7
          / \  / \
         8   9 10 11
                    |
                   12
~~~

Các kết quả:

~~~text
LCA(8,9)   = 5
LCA(8,4)   = 1
LCA(8,10)  = 0
LCA(8,12)  = 0
LCA(10,12) = 7
LCA(12,11) = 11
LCA(3,3)   = 3
LCA(0,12)  = 0
~~~

LCA hữu ích để tính khoảng cách giữa hai đỉnh, xử lý truy vấn đường đi, tìm tổ tiên thứ k, chọn đỉnh thứ k trên đường u→v, thực hiện truy vấn đổi gốc và làm nhiều bài thuật toán trên cây.

**Phạm vi:** định nghĩa ở đây dành cho **cây có gốc**. Trong một đồ thị có hướng nhiều cha, một DAG hoặc một đồ thị có chu trình, không thể mặc định rằng LCA theo parent của một cây DFS là LCA của đồ thị ban đầu. Nếu đầu vào là **rừng nhiều cây**, hai đỉnh ở hai cây khác nhau không có tổ tiên chung thật sự.

## 2. Parent, depth và ảnh hưởng của gốc

Để tính LCA, cần xác định một root r và duyệt cây:

- parent[r]=-1: gốc không có cha.
- depth[r]=0: độ sâu là **số cạnh** từ root đến đỉnh.
- Nếu u là cha của v thì parent[v]=u và depth[v]=depth[u]+1.
- Mỗi đỉnh khác root có duy nhất một cha; đường v,parent[v],parent[parent[v]],... kết thúc tại root.

Với cây ví dụ:

~~~text
vertex:   0 1 2 3 4 5 6 7 8 9 10 11 12
parent:  -1 0 0 0 1 1 2 2 5 5  7  7 11
depth:    0 1 1 1 2 2 2 2 3 3  3  3  4
~~~

**Cây vô hướng chưa chỉ gốc** là một cấu trúc khác với rooted tree. Sau khi chọn gốc, quan hệ parent/ancestor trở nên rõ ràng. Đổi gốc có thể làm LCA thay đổi. Tuy nhiên **đường đơn giữa hai đỉnh** và số cạnh của nó không đổi khi chỉ thay gốc.

Hai đường root→u và root→v có một đoạn tiền tố chung. Đỉnh cuối cùng của tiền tố chung chính là LCA(u,v). Từ u đi lên LCA rồi từ LCA đi xuống v sẽ tạo đúng đường đơn giữa u và v.

## 3. Thuật toán đơn giản O(h): nâng từng cha

Nếu cây nhỏ hoặc ít truy vấn, chỉ cần parent và depth:

~~~text
lcaNaive(u,v):
    while depth[u] > depth[v]:
        u = parent[u]

    while depth[v] > depth[u]:
        v = parent[v]

    while u != v:
        u = parent[u]
        v = parent[v]

    return u
~~~

Đầu tiên đưa hai đỉnh về **cùng độ sâu**, sau đó cùng đi từng cha tới khi gặp nhau.

Ví dụ LCA(10,12):

~~~text
depth[10]=3, depth[12]=4
Nang 12 len 11 de cung depth=3
10 va 11 khac nhau
Nang dong thoi: parent[10]=7, parent[11]=7
Gap tai 7 => LCA(10,12)=7
~~~

Nếu một đỉnh là tổ tiên của đỉnh kia, sau căn chỉnh depth ta đã gặp nhau ngay. Nếu u==v ngay từ đầu, LCA(u,u)=u, không được nhích lên rồi trả cha.

Thời gian O(h) mỗi truy vấn, h là chiều cao cây. Với cây dạng chuỗi dài n đỉnh, h có thể là n-1, khiến hàng trăm nghìn truy vấn tốn thời gian lớn. **Binary lifting** giải quyết việc này bằng cách nhảy theo lũy thừa 2.

## 4. Binary lifting: bảng nhảy tổ tiên

Đặt:

~~~text
up[k][v] = to tien cua v cach dung 2^k canh.
~~~

Nếu tổ tiên ấy không tồn tại, dùng -1.

~~~text
up[0][v] = parent[v]              // 1 canh
up[1][v] = to tien cach 2 canh
up[2][v] = to tien cach 4 canh
up[3][v] = to tien cach 8 canh
...
~~~

Công thức xây bảng:

~~~text
mid = up[k-1][v]
up[k][v] = -1 if mid == -1
up[k][v] = up[k-1][mid] otherwise
~~~

Vì 2^k = 2^(k-1) + 2^(k-1), nhảy 2^k cạnh chính là **hai lần nhảy 2^(k-1)**. Đây là quy hoạch động trên chiều dài bước nhảy.

Ví dụ đường đi từ đỉnh 12 lên gốc:

~~~text
12 -> 11 -> 7 -> 2 -> 0

up[0][12] = 11   // 1 canh
up[1][12] = 7    // 2 canh
up[2][12] = 0    // 4 canh
up[3][12] = -1   // 8 canh, khong co
~~~

Chỉ cần **LOG=O(log n)** mức. Có thể tính:

~~~text
LOG=1
while 2^LOG <= n:
    LOG++
~~~

Với n=13, LOG=4. Với n=1, LOG=1. Trong Java dùng **1L << LOG** thay vì 1 << LOG để tránh lỗi tràn int khi n lớn.

**Khởi tạo:** up[0] từ BFS/DFS của cây. Sau đó với từng k tăng dần, tính up[k][v] từ up[k-1][v]. Mỗi mức phải được hoàn tất trước khi tính mức cao hơn.

Bộ nhớ O(n log n); tiền xử lý O(n log n). Bảng này trả lời các truy vấn nhảy và LCA mà không phải đi từng cha.

## 5. Truy vấn tổ tiên thứ k

Số k có biểu diễn nhị phân duy nhất, chẳng hạn:

~~~text
k=5 = 4+1 = 2^2 + 2^0
~~~

Muốn nâng v lên k cạnh, chỉ cần thực hiện các bước up[bit] ứng với bit được bật trong k.

~~~text
kthAncestor(v,k):
    if k < 0: error
    if k > depth[v]: return -1

    for bit from 0 to LOG-1:
        if bit 'bit' of k is 1:
            v = up[bit][v]
    return v
~~~

Ví dụ:

~~~text
kthAncestor(12,0)=12
kthAncestor(12,1)=11
kthAncestor(12,2)=7
kthAncestor(12,3)=2
kthAncestor(12,4)=0
kthAncestor(12,5)=-1
~~~

**Lưu ý:** k=0 trả chính đỉnh. Với k>depth[v], không có tổ tiên ở độ cao đó; phải trả -1 **trước khi truy cập** bất kỳ up[bit][-1] nào. Với k âm, bài này ném lỗi đầu vào.

Một truy vấn kthAncestor chạy O(log n), không phải O(k).

## 6. Hai giai đoạn tìm LCA O(log n)

### Giai đoạn 1: cân bằng độ sâu

Nếu depth[u]<depth[v], đổi chỗ u,v. Nâng đỉnh sâu hơn lên đúng diff=depth[u]-depth[v] cạnh:

~~~text
u = kthAncestor(u, diff)

if u == v:
    return u
~~~

Nếu gặp nhau sau căn chỉnh, một đỉnh ban đầu là tổ tiên của đỉnh kia.

### Giai đoạn 2: nâng cả hai từ mức lớn xuống mức nhỏ

Khi u,v cùng depth nhưng chưa bằng nhau, xét k từ LOG-1 xuống 0:

~~~text
if up[k][u] != up[k][v]:
    u = up[k][u]
    v = up[k][v]
~~~

Chỉ nhảy khi hai tổ tiên ở mức đó **khác nhau**; như vậy cả hai đỉnh vẫn nằm dưới LCA thật. Nếu bằng nhau mà vẫn nhảy, ta có thể nhảy lên tới LCA hoặc cao hơn, mất yêu cầu **thấp nhất**.

Sau khi xét hết các mức, u và v là hai đỉnh khác nhau có **chung cha gần nhất**, nên:

~~~text
return up[0][u]
~~~

Giả mã tổng hợp:

~~~text
lca(u,v):
    if depth[u] < depth[v]:
        swap(u,v)

    u = kthAncestor(u, depth[u]-depth[v])
    if u == v:
        return u

    for k from LOG-1 down to 0:
        if up[k][u] != up[k][v]:
            u = up[k][u]
            v = up[k][v]

    return up[0][u]
~~~

Thời gian O(log n) cho cả giai đoạn căn chỉnh và đồng thời nâng. Với cùng một cây tiền xử lý, chi phí không tăng theo đường đi thực tế giữa u,v.

### Mô phỏng LCA(8,12)

depth[8]=3, depth[12]=4. Nâng 12 lên 11 để cùng depth=3 với 8. Lúc này xét cặp 11,8.

Ở mức 1, up[1][11]=2 và up[1][8]=1 khác nhau; nâng thành 2 và 1. Ở mức 0, up[0][2]=up[0][1]=0 giống nhau; không nhảy. Trả up[0][2]=0.

~~~text
LCA(8,12)=0
~~~

Còn LCA(8,9): hai đỉnh cùng depth và có cha trực tiếp 5. Không mức nhảy nào có hai tổ tiên khác nhau đủ để nâng, nên trả 5.

## 7. Bảng kiểm tra trên cây 13 đỉnh

Bảng một số đỉnh:

| v | depth | up[0] (1 cạnh) | up[1] (2 cạnh) | up[2] (4 cạnh) |
| --- | ---: | ---: | ---: | ---: |
| 5 | 2 | 1 | 0 | -1 |
| 7 | 2 | 2 | 0 | -1 |
| 8 | 3 | 5 | 1 | -1 |
| 9 | 3 | 5 | 1 | -1 |
| 10 | 3 | 7 | 2 | -1 |
| 11 | 3 | 7 | 2 | -1 |
| 12 | 4 | 11 | 7 | 0 |

Thử kiểm các truy vấn:

~~~text
LCA(8,9)   = 5  // cung cha
LCA(8,4)   = 1  // cung nhanh 1
LCA(8,10)  = 0  // hai nhanh khac nhau
LCA(10,12) = 7  // cung nhanh 7
LCA(12,11) = 11 // 11 la to tien cua 12
LCA(3,3)   = 3  // cung dinh
LCA(0,12)  = 0  // root
~~~

**Giá trị của LCA là id đỉnh**, không phải depth. Nếu cần khoảng cách giữa hai đỉnh, dùng công thức phần tiếp theo.

Nếu đổi thứ tự duyệt các láng giềng trong BFS, **parent/depth không thay đổi** khi graph thực sự là cây có gốc đã cố định, vì đường từ root tới mỗi đỉnh là duy nhất. Đây là khác biệt so với BFS trên đồ thị có nhiều đường đi.

## 8. Khoảng cách và đỉnh thứ k trên đường u→v

Gọi p=LCA(u,v). Đường u→v đi lên từ u đến p rồi đi xuống p→v. Đếm theo số **cạnh**:

~~~text
distanceEdges(u,v)
    = (depth[u]-depth[p]) + (depth[v]-depth[p])
    = depth[u] + depth[v] - 2*depth[p]
~~~

Ví dụ:

~~~text
distance(8,9)   = 3+3-2*2 = 2
distance(8,12)  = 3+4-2*0 = 7
distance(10,12) = 3+4-2*2 = 3
~~~

Trong Java nên tính biểu thức trung gian bằng long nếu kích thước lớn.

### Đỉnh thứ k trên đường đi

Dùng **k bắt đầu từ 0**: k=0 là u, k=distanceEdges(u,v) là v.

Đặt:

~~~text
p = LCA(u,v)
a = depth[u]-depth[p]
b = depth[v]-depth[p]
total = a+b
~~~

- k<0 hoặc k>total: trả -1.
- 0≤k≤a: **kthAncestor(u,k)**.
- a<k≤total: **kthAncestor(v,total-k)**.

Ví dụ đường từ 8 tới 12:

~~~text
8 -> 5 -> 1 -> 0 -> 2 -> 7 -> 11 -> 12
k:   0    1    2    3    4    5    6    7
~~~

Do đó kthOnPath(8,12,4)=2, kthOnPath(8,12,7)=12, kthOnPath(8,12,8)=-1.

### Tính chất

~~~text
distanceEdges(u,v) = distanceEdges(v,u)
distanceEdges(u,u) = 0
distanceEdges(u,v) >= 0
~~~

Một đỉnh x nằm trên đường đơn u→v khi và chỉ khi:

~~~text
distanceEdges(u,x)+distanceEdges(x,v)
    = distanceEdges(u,v)
~~~

Công thức là một oracle hữu ích khi kiểm kthOnPath.

## 9. Truy vấn đổi gốc (rerooted LCA)

Nếu bảng up được xây theo gốc cố định r0, vẫn có thể tìm LCA của u,v khi **gốc truy vấn mới là r** mà không xây lại bảng.

Tính ba LCA theo gốc **r0**:

~~~text
a = LCA_r0(u,v)
b = LCA_r0(u,r)
c = LCA_r0(v,r)
~~~

Khi đó:

~~~text
LCA_r(u,v) = dinh co depth_r0 lon nhat trong {a,b,c}.
~~~

Đây là tính chất của **điểm trung vị trên ba đường đơn** nối u,v,r trong cây: điểm chung của ba đường u↔v, v↔r, r↔u chính là LCA(u,v) nếu lấy r làm gốc, đồng thời là ứng viên sâu nhất trong ba LCA tính từ gốc r0.

Ví dụ từ cây mẫu:

~~~text
u=8, v=12, newRoot=7

LCA_0(8,12)=0
LCA_0(8,7) =0
LCA_0(12,7)=7

Chon dinh sau nhat: 7
=> LCA voi root=7 cua (8,12) la 7
~~~

Thử đổi root thành 5 khi hỏi (8,10):

~~~text
LCA_0(8,10)=0
LCA_0(8,5) =5
LCA_0(10,5)=0
=> LCA voi root=5 cua (8,10) la 5
~~~

Ba truy vấn O(log n) cộng lựa chọn deepest O(1), nên mỗi rerooted LCA vẫn O(log n).

**Cẩn thận:** công thức dùng **depth theo gốc tiền xử lý** để so, không cần tính depth theo gốc mới. Số cạnh trên đường u↔v không thay đổi do đổi root.

## 10. Cây có trọng số: LCA vẫn như cũ

LCA chỉ phụ thuộc **cấu trúc cây và gốc**, không phụ thuộc trọng số các cạnh. Với cây có trọng số, ta lưu thêm prefixWeight[v] là tổng trọng số trên đường từ root tới v.

~~~text
prefixWeight[root] = 0

Khi tham tu cha u toi con v co canh trong so w:
    prefixWeight[v] = prefixWeight[u] + w
~~~

Với p=LCA(u,v), tổng trọng số trên **đường đơn duy nhất** giữa u và v:

~~~text
pathWeight(u,v)
    = prefixWeight[u] + prefixWeight[v]
      - 2*prefixWeight[p]
~~~

Ví dụ:

~~~text
0 --(3)-- 1 --(-2)-- 2
           |
          (5)
           |
           3

root=0
prefix[0]=0, prefix[1]=3
prefix[2]=1, prefix[3]=8

LCA(2,3)=1
pathWeight(2,3)=1+8-2*3=3
            = -2+5
~~~

Trọng số âm không làm sai công thức đường đơn. Tuy nhiên nếu bài hỏi **walk có tổng chi phí nhỏ nhất** trên đồ thị vô hướng và cho phép đi qua lại cạnh âm nhiều lần, có thể xuất hiện chi phí -∞. Phải phân biệt **tổng trọng số trên đường đơn duy nhất** với bài toán shortest walk tổng quát.

Với trọng số có biên rất lớn, prefixWeight và biểu thức tổng có thể tràn long; dùng BigInteger hoặc cơ chế phát hiện overflow khi cần. Mã Java dưới đây tập trung vào **LCA không trọng số**, nhằm minh họa cấu trúc up trước khi mở rộng sang tổng trọng số.

## 11. Xác thực cây, rừng và graph không hợp lệ

Một đồ thị vô hướng n≥1 là cây khi **liên thông và không có chu trình**, tương đương **n-1 cạnh và không chu trình**.

Cần kiểm input trước khi dùng binary lifting:

1. n≥1, root hợp lệ trong [0,n).
2. Có đúng n-1 cạnh vô hướng.
3. Mọi endpoint thuộc [0,n).
4. Không có self-loop.
5. Không có chu trình, kể cả do **cạnh song song** tạo vòng hai cạnh trong đa đồ thị.
6. Có thể dùng DSU: nếu union(u,v) thất bại, cạnh tạo chu trình; khi n-1 cạnh đều union thành công, graph chắc chắn liên thông.

### Nếu có nhiều cây (forest)

Với forest, có thể chọn root **riêng từng thành phần** rồi dựng depth/up và componentId cho từng đỉnh. Khi hỏi:

~~~text
if componentId[u] != componentId[v]:
    return UNDEFINED
else:
    return lcaInsideComponent(u,v)
~~~

Nếu cố thêm một **siêu gốc** nối tất cả root của forest, các đỉnh ở hai cây khác nhau sẽ có LCA bằng siêu gốc, nhưng siêu gốc không có trong forest ban đầu. Phải chuyển câu trả lời ấy về “không có LCA thật”.

### Nếu có chu trình hoặc graph có hướng nhiều cha

BFS/DFS có thể tạo một **cây bao phủ**, nhưng LCA trên cây bao phủ ấy không phải lời giải tự nhiên của đồ thị gốc có nhiều đường. Định nghĩa LCA trên một DAG với nhiều cha có thể không duy nhất; nếu bài thật sự cho DAG, phải có định nghĩa riêng thay vì tự dùng bảng parent của cây DFS.

Mã Java bên dưới **từ chối input không phải một cây**, không âm thầm trả kết quả theo một spanning tree tùy thứ tự duyệt.

## 12. Euler Tour + RMQ và Tarjan offline LCA

Binary lifting không phải cách duy nhất.

### Euler Tour + Range Minimum Query

Chạy DFS trên cây, ghi đỉnh khi đi xuống **và khi trở về cha**, tạo một chuỗi Euler có **2n-1** phần tử. Lưu độ sâu ứng với từng phần tử.

Ví dụ:

~~~text
    0
   / \
  1   2

Euler:  [0,1,0,2,0]
Depth:  [0,1,0,1,0]
~~~

Đặt first[v] là **vị trí xuất hiện đầu tiên** của v trong Euler. Với u,v, LCA là đỉnh có **độ sâu nhỏ nhất** trong đoạn Euler giữa first[u] và first[v]. Đây là truy vấn **RMQ (Range Minimum Query)**.

Có thể xử lý RMQ bằng:

- **Segment Tree:** tiền xử lý O(n), truy vấn O(log n), bộ nhớ O(n).
- **Sparse Table:** tiền xử lý O(n log n), truy vấn O(1), bộ nhớ O(n log n).
- Cấu trúc RMQ chuyên biệt phức tạp hơn có thể đạt O(n) tiền xử lý và O(1) mỗi query.

**Không nhầm Euler Tour cho LCA với preorder mỗi đỉnh một lần.** Phải có bước **ghi lại cha khi quay lên**, nếu không tính chất RMQ của đoạn first occurrences không đúng.

### Tarjan offline LCA

Khi biết trước toàn bộ Q truy vấn, thuật toán **Tarjan offline LCA** dùng DFS và DSU:

- Khi DFS vào một đỉnh, tạo tập DSU cho nó và lưu ancestor[find(u)]=u.
- Sau khi xử lý xong một cây con v của u, union(u,v) và đặt ancestor[find(u)]=u.
- Khi cả hai đầu truy vấn đã được xử lý hoàn toàn theo quy tắc BLACK, dùng ancestor[find(other)] để xác định LCA.

Tổng thời gian thường O((n+Q) α(n)), với DSU có nén đường đi. Đây là **giải pháp offline**, không giống một API nhận truy vấn bất kỳ sau tiền xử lý rồi trả ngay như binary lifting.

**Đừng nhầm Tarjan offline LCA với Tarjan SCC** cho đồ thị có hướng; chúng xử lý hai bài toán khác nhau.

### Chọn giải pháp

| Phương pháp | Tiền xử lý | Một query | Bộ nhớ |
| --- | --- | --- | --- |
| Đi cha | O(n) | O(h) | O(n) |
| Binary lifting | O(n log n) | O(log n) | O(n log n) |
| Euler+Segment Tree | O(n) | O(log n) | O(n) |
| Euler+Sparse Table | O(n log n) | O(1) | O(n log n) |
| Tarjan offline | O((n+Q) α(n)) cho cả batch | Không hỗ trợ online độc lập | O(n+Q) |

Với một cây tĩnh và nhiều truy vấn online, binary lifting thường là lựa chọn dễ cài và dễ mở rộng cho kthAncestor/kthOnPath.

## 13. Java 17 – chương trình binary lifting chạy độc lập

Chương trình dùng DSU để kiểm tra input thực sự là **một cây vô hướng**, BFS lặp để xác định parent/depth và bảng nhảy, sau đó cung cấp các phương thức:

- lca(u,v)
- kthAncestor(v,steps)
- distanceEdges(u,v)
- kthOnPath(u,v,k), k bắt đầu từ 0
- lcaWithRoot(u,v,newRoot), không phải dựng lại up
- depthOf(v)

**Lưu toàn bộ code vào LcaBinaryLiftingDemo.java:**

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class LcaBinaryLiftingDemo {

    // DSU just validates that input is a tree.
    private static final class Dsu {
        private final int[] parent;
        private final int[] size;

        Dsu(int n) {
            parent = new int[n];
            size = new int[n];
            for (int v = 0; v < n; v++) {
                parent[v] = v;
                size[v] = 1;
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
            int ra = find(a);
            int rb = find(b);
            if (ra == rb) {
                return false;
            }
            if (size[ra] < size[rb]) {
                int tmp = ra;
                ra = rb;
                rb = tmp;
            }
            parent[rb] = ra;
            size[ra] += size[rb];
            return true;
        }
    }

    static final class Lca {
        private final int n;
        private final int log;
        private final int[] depth;
        private final int[][] up;

        Lca(int n, int[][] edges, int root) {
            if (n <= 0) {
                throw new IllegalArgumentException(
                        "n must be positive");
            }
            if (root < 0 || root >= n) {
                throw new IllegalArgumentException(
                        "root out of range");
            }
            Objects.requireNonNull(edges, "edges");
            if (edges.length != n - 1) {
                throw new IllegalArgumentException(
                        "expected n-1 edges");
            }

            List<List<Integer>> graph = new ArrayList<>();
            for (int v = 0; v < n; v++) {
                graph.add(new ArrayList<>());
            }

            Dsu dsu = new Dsu(n);
            for (int[] edge : edges) {
                if (edge == null || edge.length != 2) {
                    throw new IllegalArgumentException(
                            "invalid edge");
                }
                int u = edge[0];
                int v = edge[1];
                if (u < 0 || u >= n || v < 0 || v >= n) {
                    throw new IllegalArgumentException(
                            "vertex out of range");
                }
                if (u == v || !dsu.union(u, v)) {
                    throw new IllegalArgumentException(
                            "graph must be a tree");
                }
                graph.get(u).add(v);
                graph.get(v).add(u);
            }

            // n-1 edges and acyclic implies connected.
            this.n = n;
            int levels = 1;
            while ((1L << levels) <= n) {
                levels++;
            }
            this.log = levels;
            this.depth = new int[n];
            Arrays.fill(depth, -1);
            this.up = new int[log][n];
            for (int[] level : up) {
                Arrays.fill(level, -1);
            }

            // Iterative BFS: no deep recursion.
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            depth[root] = 0;
            queue.addLast(root);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (int v : graph.get(u)) {
                    if (depth[v] != -1) {
                        continue;
                    }
                    depth[v] = depth[u] + 1;
                    up[0][v] = u;
                    queue.addLast(v);
                }
            }

            for (int k = 1; k < log; k++) {
                for (int v = 0; v < n; v++) {
                    int mid = up[k - 1][v];
                    up[k][v] =
                            mid == -1 ? -1 : up[k - 1][mid];
                }
            }
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "vertex out of range");
            }
        }

        int depthOf(int v) {
            checkVertex(v);
            return depth[v];
        }

        int kthAncestor(int v, int steps) {
            checkVertex(v);
            if (steps < 0) {
                throw new IllegalArgumentException(
                        "steps must be nonnegative");
            }
            if (steps > depth[v]) {
                return -1;
            }
            for (int bit = 0; bit < log; bit++) {
                if (((steps >>> bit) & 1) != 0) {
                    v = up[bit][v];
                }
            }
            return v;
        }

        int lca(int u, int v) {
            checkVertex(u);
            checkVertex(v);

            if (depth[u] < depth[v]) {
                int tmp = u;
                u = v;
                v = tmp;
            }
            u = kthAncestor(u, depth[u] - depth[v]);
            if (u == v) {
                return u;
            }

            for (int k = log - 1; k >= 0; k--) {
                if (up[k][u] != up[k][v]) {
                    u = up[k][u];
                    v = up[k][v];
                }
            }
            return up[0][u];
        }

        long distanceEdges(int u, int v) {
            int p = lca(u, v);
            return (long) depth[u] + depth[v]
                    - 2L * depth[p];
        }

        // k=0 denotes u; k=total denotes v.
        int kthOnPath(int u, int v, long k) {
            int p = lca(u, v);
            long upCount = (long) depth[u] - depth[p];
            long downCount = (long) depth[v] - depth[p];
            long total = upCount + downCount;

            if (k < 0 || k > total) {
                return -1;
            }
            if (k <= upCount) {
                return kthAncestor(u, (int) k);
            }
            return kthAncestor(v, (int) (total - k));
        }

        // Query under newRoot while up/depth stay rooted at 0.
        int lcaWithRoot(int u, int v, int newRoot) {
            checkVertex(newRoot);
            int a = lca(u, v);
            int b = lca(u, newRoot);
            int c = lca(v, newRoot);
            int best = a;
            if (depth[b] > depth[best]) {
                best = b;
            }
            if (depth[c] > depth[best]) {
                best = c;
            }
            return best;
        }
    }

    public static void main(String[] args) {
        int[][] edges = {
                {0,1}, {0,2}, {0,3},
                {1,4}, {1,5}, {2,6}, {2,7},
                {5,8}, {5,9}, {7,10}, {7,11}, {11,12}
        };
        Lca tree = new Lca(13, edges, 0);

        int[] depths = new int[13];
        for (int v = 0; v < 13; v++) {
            depths[v] = tree.depthOf(v);
        }
        System.out.println("depth = " + Arrays.toString(depths));
        System.out.println("LCA(8,9) = " + tree.lca(8, 9));
        System.out.println("LCA(8,4) = " + tree.lca(8, 4));
        System.out.println("LCA(8,10) = " + tree.lca(8, 10));
        System.out.println("LCA(8,12) = " + tree.lca(8, 12));
        System.out.println("LCA(10,12) = " + tree.lca(10, 12));
        System.out.println("LCA(12,11) = " + tree.lca(12, 11));
        System.out.println("LCA(3,3) = " + tree.lca(3, 3));

        System.out.println("distance(8,9) = " +
                tree.distanceEdges(8, 9));
        System.out.println("distance(8,12) = " +
                tree.distanceEdges(8, 12));
        System.out.println("distance(10,12) = " +
                tree.distanceEdges(10, 12));

        System.out.println("ancestor(12,0) = " +
                tree.kthAncestor(12, 0));
        System.out.println("ancestor(12,2) = " +
                tree.kthAncestor(12, 2));
        System.out.println("ancestor(12,4) = " +
                tree.kthAncestor(12, 4));
        System.out.println("ancestor(12,5) = " +
                tree.kthAncestor(12, 5));

        System.out.println("path(8,12,k=0) = " +
                tree.kthOnPath(8, 12, 0));
        System.out.println("path(8,12,k=4) = " +
                tree.kthOnPath(8, 12, 4));
        System.out.println("path(8,12,k=7) = " +
                tree.kthOnPath(8, 12, 7));
        System.out.println("path(8,12,k=8) = " +
                tree.kthOnPath(8, 12, 8));

        System.out.println("reroot 7: LCA(8,12) = " +
                tree.lcaWithRoot(8, 12, 7));
        System.out.println("reroot 5: LCA(8,10) = " +
                tree.lcaWithRoot(8, 10, 5));

        Lca singleton = new Lca(1, new int[0][2], 0);
        System.out.println("singleton LCA(0,0) = " +
                singleton.lca(0, 0));
        System.out.println("singleton ancestor(0,1) = " +
                singleton.kthAncestor(0, 1));

        try {
            new Lca(3, new int[][]{{0,1}, {1,1}}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("self-loop input: " +
                    ex.getMessage());
        }
        try {
            new Lca(3, new int[][]{{0,1}}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad edge count: " +
                    ex.getMessage());
        }
        try {
            tree.kthAncestor(12, -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative step: " +
                    ex.getMessage());
        }
        try {
            tree.lca(8, 13);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid vertex: " +
                    ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac LcaBinaryLiftingDemo.java
java LcaBinaryLiftingDemo
~~~

**Stdout chính xác:**

~~~text
depth = [0, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4]
LCA(8,9) = 5
LCA(8,4) = 1
LCA(8,10) = 0
LCA(8,12) = 0
LCA(10,12) = 7
LCA(12,11) = 11
LCA(3,3) = 3
distance(8,9) = 2
distance(8,12) = 7
distance(10,12) = 3
ancestor(12,0) = 12
ancestor(12,2) = 7
ancestor(12,4) = 0
ancestor(12,5) = -1
path(8,12,k=0) = 8
path(8,12,k=4) = 2
path(8,12,k=7) = 12
path(8,12,k=8) = -1
reroot 7: LCA(8,12) = 7
reroot 5: LCA(8,10) = 5
singleton LCA(0,0) = 0
singleton ancestor(0,1) = -1
self-loop input: graph must be a tree
bad edge count: expected n-1 edges
negative step: steps must be nonnegative
invalid vertex: vertex out of range
~~~

**Đọc output:** cây 13 đỉnh có 12 cạnh, được xác thực bởi DSU. BFS gốc 0 cho depth đã in. Ancestor 12 k=4 là root, k=5 vượt root nên -1. Path 8→12 có 7 cạnh/8 đỉnh; chỉ số k=4 là đỉnh 2. Hai truy vấn đổi gốc trả đúng LCA dưới root mới mà không thay đổi bảng up. Singleton n=1 vẫn hợp lệ với cây một đỉnh. Self-loop và số cạnh sai bị từ chối.

**Giới hạn API:** n phải dương; đây là bộ giải cho đúng một cây, không phải forest; root và mọi endpoint dùng chỉ số 0..n-1. Không có hỗ trợ cập nhật thêm/bớt cạnh động sau tiền xử lý. Hàm private Dsu chỉ kiểm tra tính hợp lệ của input, không tham gia câu trả lời LCA. BFS lặp tránh StackOverflowError của DFS đệ quy trên cây rất sâu.

## 14. Chứng minh tính đúng

### Bảng tổ tiên up đúng

Với k=0, up[0][v]=parent[v] đúng theo BFS từ root trên cây. Giả sử up[k-1][v] là tổ tiên cách 2^(k-1) cạnh. Ghép hai bước như vậy cho tổ tiên cách 2^k cạnh, hoặc -1 khi bước trung gian không tồn tại. Theo quy nạp, up đúng mọi k,v.

### kthAncestor đúng

Bất kỳ k≤depth[v] được biểu diễn bằng tổng các lũy thừa 2 có bit bật. Mỗi lần nhảy tương ứng một đoạn đường theo hướng parent, nên ghép các lần nhảy đi đúng k cạnh. Nếu k>depth[v] thì không có tổ tiên ở khoảng cách ấy và trả -1.

### Căn chỉnh depth bảo toàn LCA

Giả sử depth[u]≥depth[v]. Nếu p=LCA(u,v), depth[p]≤depth[v]. Nâng u lên depth[u]-depth[v] cạnh không vượt lên trên p, nên LCA của cặp mới vẫn bằng p. Nếu sau căn chỉnh u==v, kết quả chính là tổ tiên chung thấp nhất.

### Nâng đồng thời không vượt qua LCA

Sau khi u,v cùng depth và khác nhau, chúng thuộc hai nhánh khác nhau dưới p. Chỉ khi up[k][u]!=up[k][v] mới nhảy hai đỉnh; điều này giữ chúng ở các nhánh khác nhau phía dưới p. Sau khi xét mọi k giảm dần, không còn bước nhảy 1 cạnh nào giữ hai tổ tiên khác nhau. Khi ấy u,v vẫn khác nhau nhưng có cùng cha p. Trả up[0][u] đúng là LCA.

### Kết thúc

BFS đánh dấu depth ngay khi enqueue, xử lý mỗi đỉnh đúng một lần vì input là cây; up có LOG mức hữu hạn. Query xét tối đa O(LOG) mức, nên thuật toán luôn kết thúc.

Độ đúng của LCA không phụ thuộc trọng số vì cấu trúc ancestor không sử dụng trọng số.

## 15. Độ phức tạp thời gian và bộ nhớ

Đặt n là số đỉnh, q là số truy vấn, h là chiều cao cây.

| Công việc | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Xây adjacency tree | O(n) | O(n) |
| Kiểm cây bằng DSU | O(n α(n)) khấu hao | O(n) |
| BFS parent/depth | O(n) | O(n) cho queue và depth |
| Xây bảng up | O(n log n) | O(n log n) |
| Một LCA | O(log n) | O(1) thêm |
| Một kthAncestor | O(log n) | O(1) thêm |
| Một distanceEdges | O(log n) | O(1) thêm |
| Một kthOnPath | O(log n) | O(1) thêm |
| Một lcaWithRoot | O(log n), ba LCA | O(1) thêm |

Tổng cho q truy vấn LCA sau một lần tiền xử lý là **O(n log n + q log n)** thời gian và **O(n log n)** bộ nhớ. Trong bảng, α(n) là Ackermann nghịch đảo của DSU, tăng rất chậm.

### Ước lượng bộ nhớ

Bảng up chứa khoảng n×LOG phần tử int.

- n=100000, LOG≈17: khoảng 1,7 triệu int, **6,8 MB** dữ liệu thô.
- n=1000000, LOG≈20: khoảng 20 triệu int, **80 MB** dữ liệu thô.

Số trên chưa tính ArrayList<Integer>, boxing, queue, DSU, overhead các mảng JVM. Vì vậy khi n lớn, phải xét giới hạn heap thật sự.

Với ít query, O(h) mỗi query có thể đủ và tiết kiệm bộ nhớ. Với nhiều query cố định cần O(1), Euler Tour + Sparse Table là một lựa chọn khác. Nếu biết toàn bộ query từ trước, có thể cân nhắc Tarjan offline LCA.

## 16. Sai sót thường gặp

| Sai sót | Hậu quả | Cách tránh |
| --- | --- | --- |
| Không xác định root | Khái niệm tổ tiên mơ hồ | Chọn gốc theo đề |
| Coi ancestor không bao gồm chính đỉnh | LCA(u,u) sai | Nêu quy ước rõ |
| depth(root)=1 nhưng tính theo 0 | Công thức số cạnh bị lệch | Dùng depth(root)=0 nhất quán |
| parent[root]=root lẫn -1 | Nhảy vượt root trả sai | Một quy ước toàn chương trình |
| Cấp LOG thiếu một mức | Không nhảy đủ cây sâu | Dựa trên n và dùng 1L shift |
| up[k][v] khi mid=-1 | Lỗi truy cập index âm | Kiểm mid trước |
| Nhầm up[v][k] với up[k][v] | Truy tổ tiên sai | Quy định thứ tự chỉ số |
| Không đưa hai đỉnh về cùng depth | LCA sai | Căn chỉnh trước khi nâng |
| Quên kiểm u==v sau căn chỉnh | Trả cha hoặc tổ tiên quá cao | Trả ngay u |
| Nhảy khi up[k][u]==up[k][v] | Có thể vượt qua LCA | Chỉ nhảy khi khác nhau |
| Không kiểm steps>depth | Truy -1 | Trả -1 trước khi nhảy |
| Nhầm k-th vertex bắt đầu từ 1 | Sai một vị trí | k=0 là u |
| Nhầm LCA là độ sâu | Output sai kiểu/ý nghĩa | Trả id đỉnh |
| Tính distance chỉ bằng chênh lệch depth | Sai khi khác nhánh | Dùng LCA trong công thức |
| Dùng int cho tổng trung gian lớn | Overflow | Ép long đúng chỗ |
| Dùng LCA root cũ cho root truy vấn mới | Sai ancestor | Deepest của ba LCA |
| Dùng LCA trên graph có chu trình | Sai ngữ nghĩa | Xác thực cây trước |
| Không xử lý forest khác component | Tổ tiên chung giả | Trả UNDEFINED |
| Euler Tour chỉ ghi preorder | RMQ không đúng | Ghi cả lần quay lên cha |
| Nhầm Tarjan SCC với Tarjan offline LCA | Sai thuật toán | Phân biệt phạm vi |

### Lưu ý về gốc tự trỏ

Một số code cài parent[root]=root và up mọi mức của root cũng là root. Cách này có thể hoạt động nếu tất cả phép toán đồng nhất với quy ước “nhảy vượt root vẫn ở root”. Tuy nhiên bài này sử dụng **-1** cho tổ tiên không tồn tại. Trộn hai quy ước sẽ gây lỗi ở kthAncestor và LCA; hãy cố định một cách xử lý.

## 17. Kiểm thử theo tính chất và oracle độc lập

Để tránh phụ thuộc vào cùng một implementation khi test, hãy viết **lcaNaive** đi từng cha làm oracle cho cây nhỏ. So mọi cặp (u,v) với LCA binary lifting.

Các tính chất nên luôn đúng:

- **Đối xứng:** LCA(u,v)=LCA(v,u).
- **Phản xạ:** LCA(u,u)=u.
- LCA(u,v) phải là tổ tiên của cả u lẫn v.
- Không có tổ tiên chung nào có depth cao hơn depth[LCA].
- Nếu u là tổ tiên của v, LCA(u,v)=u.
- LCA(root,v)=root.
- depth[LCA(u,v)]≤min(depth[u],depth[v]).
- distanceEdges(u,v)=distanceEdges(v,u), và distanceEdges(u,u)=0.
- kthAncestor(v,0)=v.
- kthAncestor(v,depth[v])=root.
- kthAncestor(v,depth[v]+1)=-1.
- kthOnPath(u,v,0)=u.
- kthOnPath(u,v,distanceEdges(u,v))=v.
- lcaWithRoot(u,v,r) bằng kết quả của một LCA được **tiền xử lý lại thật sự dưới root r**.

### Các cây kiểm thử

| Cấu trúc | Kết quả quan trọng |
| --- | --- |
| Cây một đỉnh | LCA(0,0)=0 |
| Cây hình sao | Hai lá khác nhau có LCA=root |
| Cây dây xích | LCA(i,j) theo root đầu chuỗi là đỉnh gần root hơn |
| Cây cân bằng | Có LCA tại nhiều độ sâu |
| Hai đỉnh ở cùng nhánh | Một đỉnh có thể là ancestor của đỉnh kia |
| Hai nhánh khác nhau | LCA ở điểm tách nhánh |
| Một nhánh sâu, một nhánh nông | Kiểm căn chỉnh depth |
| Đổi root thành lá | LCA có thể đổi |
| Có self-loop | Không phải tree |
| n-1 cạnh nhưng có chu trình | Không phải tree |
| Có đỉnh cô lập trong graph n>1 | Không phải một tree |
| steps âm hoặc id ngoài miền | Báo lỗi hoặc trả theo hợp đồng |

### Sinh cây ngẫu nhiên

Có thể sinh một cây hợp lệ bằng cách với mỗi v từ 1 đến n-1, nối v với một đỉnh ngẫu nhiên thuộc [0,v-1]. Mỗi đỉnh mới chỉ có một cạnh về phần đã dựng, nên kết quả liên thông và không chu trình.

Sau đó:

1. Trộn thứ tự edges, hoán đổi endpoint vì cạnh vô hướng.
2. Chọn root ngẫu nhiên, dựng up.
3. So LCA mọi cặp với lcaNaive.
4. Kiểm kthAncestor bằng vòng lặp parent k lần.
5. Kiểm kthOnPath bằng cách dựng đường u→LCA→v thật sự trên cây nhỏ.
6. Chọn root mới r rồi so công thức ba LCA với một oracle có parent/depth theo r.
7. Thử cây dây xích n lớn để bảo đảm BFS lặp không gây StackOverflowError.

### Kiểm thử thay nhãn

Đổi tên các đỉnh qua một hoán vị, đổi endpoints và root theo hoán vị đó. Sau khi map output về nhãn ban đầu, LCA và khoảng cách phải giữ đúng quan hệ cấu trúc, dù id số đã đổi.

## 18. Bài tập thực hành

1. Tự dựng parent/depth cho cây 13 đỉnh. Tính LCA(8,9), LCA(8,10), LCA(10,12), LCA(12,11).
2. Dựng up[0], up[1], up[2] cho mọi đỉnh. Giải thích up[2][12]=0 bằng hai lần nhảy 2 cạnh.
3. Mô phỏng từng bước LCA(8,12): căn chỉnh depth rồi kiểm các mức k giảm dần.
4. Chạy lcaNaive và binary lifting trên cây dây xích dài. So chi phí một truy vấn xa.
5. Viết hàm isAncestor(a,v) dựa trên kthAncestor(v,depth[v]-depth[a]) khi depth[a]≤depth[v].
6. Viết distanceEdges(u,v) dùng LCA. Kiểm distanceEdges(8,12)=7.
7. Viết kthOnPath với k bắt đầu từ 0; kiểm k=0,k=L và giá trị ngoài miền.
8. Đổi gốc cây mẫu thành 7, tự xây parent mới và kiểm LCA(8,12)=7.
9. Đổi gốc truy vấn thành 5 và tính LCA(8,10) không xây lại up.
10. Gán trọng số có cả số âm lên cây, tính prefixWeight và pathWeight. Phân biệt đường đơn với shortest walk.
11. Vẽ Euler Tour (2n-1 phần tử) của một cây nhỏ, tính first[v] và RMQ cho LCA.
12. Cài forest LCA thêm componentId; khi hai đỉnh thuộc hai cây khác nhau, trả -1.
13. Dùng DSU kiểm một input n-1 cạnh nhưng có self-loop hoặc cạnh song song.
14. Cài Tarjan offline LCA cho danh sách query cố định; so với binary lifting.
15. Sinh nhiều cây ngẫu nhiên nhỏ và so mọi query LCA với oracle đi từng cha.
16. Với cây dây xích 100000 đỉnh root=0, chứng minh LCA(i,j)=min(i,j).
17. Cài Sparse Table trên Euler Tour và đo thời gian khi có rất nhiều query cố định.
18. Với DAG có nhiều cha, cho ví dụ chứng minh LCA của một DFS tree không phản ánh toàn graph.
19. Ước lượng bộ nhớ up khi n=1000000, LOG=20; đề xuất lựa chọn khác nếu thiếu heap.
20. Đổi nhãn đỉnh bằng hoán vị rồi ánh xạ LCA về nhãn ban đầu, xác minh kết quả bất biến về cấu trúc.

## 19. Tổng kết và checklist áp dụng

Khi gặp bài LCA:

- Input có thật là **một cây có gốc** không? Xác thực n, edges, root và chu trình.
- Có phải **forest** không? Hai đỉnh khác cây không có LCA chung thật sự.
- Quy ước tổ tiên gồm chính đỉnh? Depth(root)=0 hay 1?
- Số query nhiều không? Ít query có thể đi cha; nhiều query dùng binary lifting.
- Bảng up[k][v] có đủ mức và gán -1 khi tổ tiên không tồn tại?
- Đã căn chỉnh depth trước, rồi nâng đồng thời từ bit lớn xuống bit nhỏ **chỉ khi tổ tiên khác nhau**?
- Nếu u==v sau căn chỉnh, đã trả ngay u?
- Khoảng cách có dùng LCA thay vì chỉ lấy chênh lệch độ sâu?
- K-th vertex trên path có thống nhất k bắt đầu từ 0?
- Truy vấn đổi root đã dùng deepest của ba LCA theo root tiền xử lý?
- Có trọng số thì tính tổng đường đơn bằng prefixWeight; kiểm overflow nếu cần.
- Đã kiểm n=1, self-loop, edge sai, tree dây xích, cây hình sao, queries out-of-range?
- Đã đối chứng với lcaNaive và các bất biến trên cây nhỏ?

**Kết luận:** LCA là **tổ tiên chung sâu nhất của hai đỉnh trong một cây có gốc**. Binary lifting lưu trước tổ tiên theo các bước nhảy 1,2,4,8,... cạnh; sau tiền xử lý **O(n log n)**, mỗi truy vấn LCA hoặc tổ tiên thứ k chạy **O(log n)**. Kết hợp LCA với depth, ta tính được khoảng cách, đỉnh thứ k trên đường đi và truy vấn đổi gốc nhanh chóng. Tính đúng phụ thuộc việc input thật sự là cây và mọi quy ước root/parent/depth được dùng nhất quán.
