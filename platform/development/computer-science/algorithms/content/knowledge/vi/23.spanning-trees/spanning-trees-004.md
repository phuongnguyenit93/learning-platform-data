# Thuật toán Kruskal với DSU

## 1. Bài toán cây khung nhỏ nhất (Minimum Spanning Tree)

Cho một đồ thị **vô hướng, có trọng số** G=(V,E), mỗi cạnh nối hai đỉnh u,v và có chi phí w(u,v). Một **cây khung (spanning tree)** là một tập cạnh nối tất cả các đỉnh thành **một cây**: liên thông và không có chu trình.

Nếu đồ thị có n đỉnh và liên thông, mọi cây khung phải có đúng **n-1 cạnh**. Trong số các cây khung đó, **cây khung nhỏ nhất** (Minimum Spanning Tree, viết tắt MST) là cây có **tổng trọng số các cạnh nhỏ nhất**.

Mô hình toán học:

~~~text
Chon T la tap con cua E.

Dieu kien:
    (V,T) lien thong
    (V,T) khong co chu trinh
    |T| = |V|-1        (voi do thi lien thong, |V| >= 1)

Muc tieu:
    minimize SUM(weight(e)) voi moi e thuoc T
~~~

Ví dụ trong thực tế: chọn tuyến cáp nối các khu nhà, mạng ống nối các trạm, hoặc các tuyến kết nối giữa các điểm sao cho **tổng chi phí xây dựng nhỏ nhất**, nhưng vẫn đảm bảo mọi điểm liên thông.

Đặc điểm quan trọng:

- MST tối ưu **tổng trọng số toàn mạng**, không phải khoảng cách ngắn nhất từ một nguồn đến mọi đỉnh.
- Đồ thị có thể có nhiều MST khác nhau có cùng tổng trọng số, đặc biệt khi tồn tại các cạnh bằng trọng số.
- Trọng số cạnh có thể **âm, bằng 0 hoặc dương**; Kruskal vẫn đúng vì tính chất cắt và chu trình không yêu cầu trọng số không âm.
- Cạnh tự nối (self-loop) **không bao giờ** có trong cây khung, dù trọng số rất âm, bởi nó tự tạo chu trình và không kết nối hai đỉnh khác nhau.
- Cạnh song song giữa cùng hai đỉnh được phép xuất hiện trong multigraph; thuật toán chọn hoặc bỏ theo trọng số và tình trạng liên thông.

### Nếu đồ thị không liên thông thì sao?

Một đồ thị vô hướng không liên thông **không có cây khung duy nhất nối tất cả đỉnh**, vì không có cạnh nào nối một số thành phần với nhau.

Trong trường hợp đó, Kruskal có thể tạo **rừng khung nhỏ nhất** (Minimum Spanning Forest, MSF): một cây khung nhỏ nhất cho **mỗi thành phần liên thông** của đồ thị gốc. Nếu đồ thị có n đỉnh và c thành phần liên thông, rừng khung chứa đúng **n-c cạnh**.

Cụm từ “nhỏ nhất” ở đây nghĩa là rừng phải **trải hết từng thành phần gốc** và có tổng trọng số nhỏ nhất trong những rừng thỏa điều kiện đó. Không có nghĩa được tùy ý chọn tập cạnh rỗng chỉ để làm tổng trọng số nhỏ; ngay cả khi mọi cạnh có trọng số dương, ta vẫn phải nối đủ các đỉnh nằm trong cùng một thành phần.

### Phạm vi riêng của thuật toán

**Kruskal** giải bài toán MST/MSF cho đồ thị **vô hướng**. Với đồ thị có hướng và yêu cầu một cây phân nhánh có gốc (minimum arborescence), Kruskal chuẩn **không áp dụng**; cần thuật toán dành cho đồ thị có hướng, chẳng hạn Chu–Liu/Edmonds trong điều kiện thích hợp.

## 2. Ý tưởng tham lam: xét cạnh nhẹ trước, chỉ lấy nếu không tạo chu trình

Kruskal là một thuật toán **tham lam (greedy)**. Tại mỗi bước, nó xét cạnh có trọng số nhỏ nhất **trong số những cạnh chưa xét**, và:

- **Giữ cạnh** nếu hai đầu của cạnh hiện đang nằm trong **hai thành phần khác nhau của rừng đã chọn**. Khi nối chúng, số thành phần giảm một và không tạo chu trình.
- **Bỏ cạnh** nếu hai đầu đã thuộc **cùng một thành phần**. Khi đó giữa hai đầu đã có một đường đi bằng các cạnh đã chọn; thêm cạnh mới sẽ tạo chu trình.

Thuật toán bắt đầu từ một rừng có n cây đơn đỉnh, chưa có cạnh nào. Quá trình lặp đến khi hết cạnh; nếu graph liên thông và đã chọn n-1 cạnh thì cũng có thể kết thúc sớm khi chỉ cần MST.

~~~text
Kruskal(G):
    selected = []
    sort all edges by nondecreasing weight
    initialize DSU with each vertex in its own set

    for edge e=(u,v,w) in sorted edges:
        if DSU.union(u,v) succeeds:
            selected.add(e)
        else:
            skip e because it closes a cycle

    if DSU.components == 1 and n>0:
        selected is an MST
    else:
        selected is an MSF
~~~

Ở đây **DSU** (Disjoint Set Union) là cấu trúc dữ liệu giúp xác định nhanh liệu hai đỉnh đã nối với nhau trong rừng hay chưa. Kruskal là phần **chiến lược lựa chọn cạnh**; DSU là phần **thực thi hiệu quả phép kiểm chu trình**.

**Không nên nhầm:** Kruskal không cố lấy tất cả cạnh có trọng số âm, không cố chọn cạnh nhẹ nhất cho mỗi đỉnh riêng rẽ, và cũng không tìm đường đi ngắn nhất từ một nguồn. Nó chọn các cạnh theo **thứ tự toàn cục**, kèm điều kiện **không tạo chu trình**.

### Bất biến hình học của quá trình chọn

Sau mỗi bước, tập selected luôn là một **rừng**:

1. Ban đầu n đỉnh cô lập là rừng.
2. Nếu thêm cạnh nối hai cây khác nhau, hai cây nhập thành một cây, vẫn không có chu trình.
3. Nếu hai đầu ở cùng cây, cạnh đó bị bỏ; rừng không đổi.

Như vậy số cạnh được chọn không bao giờ vượt n-1 khi n>0, và trong trường hợp không liên thông, không bao giờ vượt n-c với c là số thành phần của graph gốc.

## 3. DSU là gì? Ba phép toán cốt lõi

**Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, quản lý một phân hoạch các phần tử thành những tập **không giao nhau**. Nó hỗ trợ:

- **makeSet(v):** ban đầu mỗi đỉnh v là một tập riêng.
- **find(v):** tìm **đại diện (root)** của tập chứa v.
- **union(u,v):** gộp hai tập của u và v nếu đang khác nhau; cho biết lần gộp có thực sự diễn ra không.

Trong Kruskal, hai đỉnh có cùng root **nếu và chỉ nếu** chúng đã được nối bằng các cạnh trong rừng currently selected.

Một triển khai DSU thường dùng:

~~~text
parent[v]: cha cua v trong rung dai dien
size[root]: kich thuoc tap ma root dai dien
components: so tap hien tai

Ban dau:
    parent[v] = v
    size[v] = 1
    components = n
~~~

### find(v) và nén đường đi

Nếu parent[v]=v thì v là root. Nếu không, lần theo parent cho đến root.

**Path compression** làm phẳng cây đại diện: khi tìm root, chỉnh lại parent của các nút trên đường để các lần find sau nhanh hơn. Có thể dùng **path halving** dạng lặp:

~~~text
find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
~~~

Mỗi lần lặp, x được đưa lên gần root hơn và nén một phần đường đi. Cách này tránh dùng đệ quy trong find.

### union by size

Khi cần gộp hai tập khác root, gắn cây **nhỏ hơn** dưới root của cây **lớn hơn**:

~~~text
union(a,b):
    ra = find(a)
    rb = find(b)

    if ra == rb:
        return false

    if size[ra] < size[rb]:
        swap ra, rb

    parent[rb] = ra
    size[ra] += size[rb]
    components -= 1
    return true
~~~

Lợi ích: giữ độ sâu cấu trúc đại diện nhỏ, hạn chế chuỗi parent dài. Kết hợp union by size với path compression/path halving cho độ phức tạp **khấu hao gần hằng số**, thường ký hiệu O(α(n)) cho mỗi phép toán, với α là hàm Ackermann nghịch đảo tăng cực chậm.

**Root không nhất thiết là đỉnh nhỏ nhất** của tập. Ví dụ union(5,1) có thể khiến 5 là root dù 1 nhỏ hơn. Tính đúng của Kruskal chỉ cần so sánh root, **không phụ thuộc tên root**.

### Vì sao union trả boolean là tiện nhất?

Kruskal muốn biết “cạnh này nối được **hai cây khác nhau** không?”. Thay vì gọi find(u), find(v) rồi gọi union thêm lần nữa, ta để union thực hiện cả kiểm tra và gộp:

~~~text
if dsu.union(u,v):
    add edge to MST
else:
    ignore edge
~~~

Khi union trả false, hai đầu đã chung tập, vì vậy cạnh sẽ tạo chu trình; trường hợp self-loop u==v cũng tự động false.

## 4. Mô phỏng toàn bộ Kruskal trên đồ thị sáu đỉnh

Xét **đồ thị vô hướng** gồm 6 đỉnh 0..5. Các cạnh và trọng số được đưa vào chương trình theo thứ tự dưới đây:

~~~text
0--1   weight 4
0--2   weight 3
1--2   weight 1
1--3   weight 2
2--3   weight 4
3--4   weight 2
4--5   weight 6
3--5   weight 7
2--5   weight 10
0--0   weight -9    (self-loop)
1--2   weight 5     (parallel, nang hon)
0--3   weight 5
~~~

Đồ thị **liên thông** vì có thể đi tới mọi đỉnh qua các cạnh nối. Ta có n=6 nên cần đúng **5 cạnh** để tạo cây khung.

Sắp cạnh tăng theo trọng số, khi bằng nhau dùng cặp đỉnh chuẩn hóa (min(u,v),max(u,v)) để phá hòa. Thứ tự xét:

~~~text
(0,0,-9)
(1,2, 1)
(1,3, 2)
(3,4, 2)
(0,2, 3)
(0,1, 4)
(2,3, 4)
(0,3, 5)
(1,2, 5)
(4,5, 6)
(3,5, 7)
(2,5,10)
~~~

Mô phỏng:

| Cạnh được xét | Hai root trước union | Quyết định | Vì sao |
| --- | --- | --- | --- |
| 0–0 (-9) | Cùng root 0 | Bỏ | Self-loop không nối hai tập |
| 1–2 (1) | Khác | Lấy | Gộp {1} với {2} |
| 1–3 (2) | Khác | Lấy | Gộp {1,2} với {3} |
| 3–4 (2) | Khác | Lấy | Gộp {1,2,3} với {4} |
| 0–2 (3) | Khác | Lấy | Gộp {0} với {1,2,3,4} |
| 0–1 (4) | Cùng | Bỏ | Đã có đường 0→2→1 trong rừng |
| 2–3 (4) | Cùng | Bỏ | Tạo chu trình trong cây hiện tại |
| 0–3 (5) | Cùng | Bỏ | Đã liên thông |
| 1–2 (5) | Cùng | Bỏ | Cạnh song song nặng hơn |
| 4–5 (6) | Khác | Lấy | Gắn đỉnh 5 vào rừng |
| 3–5 (7) | Cùng | Bỏ | Tạo chu trình |
| 2–5 (10) | Cùng | Bỏ | Tạo chu trình |

**Lưu ý về root:** cột “khác/cùng” biểu diễn quan hệ tập, không bắt buộc root có đúng nhãn nhỏ nhất. Giá trị parent của DSU phụ thuộc thứ tự union và union by size; chỉ quan hệ “cùng tập” là bất biến cần dùng.

Các cạnh được chọn theo thứ tự:

~~~text
(1-2:1)
(1-3:2)
(3-4:2)
(0-2:3)
(4-5:6)
~~~

Tổng trọng số:

~~~text
1 + 2 + 2 + 3 + 6 = 14
~~~

Kết quả gồm 5 cạnh trên 6 đỉnh, nối mọi đỉnh và không có chu trình, nên là một **MST**. Các cạnh bị bỏ gồm 7 cạnh (tính cả self-loop); không cần công bố mọi cạnh bị bỏ nếu đề chỉ hỏi tổng trọng số MST.

### Vì sao không lấy self-loop có trọng số -9?

Nếu mục tiêu đơn thuần là chọn tổng trọng số nhỏ nhất mà không có ràng buộc cây, thêm self-loop -9 sẽ làm tổng giảm. Nhưng cây khung **bắt buộc không có chu trình và phải nối các đỉnh khác nhau**. Cạnh 0–0 tạo chu trình độ dài một cạnh, không giúp kết nối mới, nên phải bỏ dù rất rẻ.

### Có thể dừng sớm ở 5 cạnh không?

Đối với đồ thị **đã biết liên thông** và chỉ cần một MST, khi số cạnh selected=n-1 có thể dừng: không thể thêm cạnh nào vào một cây mà không tạo chu trình.

Tuy nhiên, nếu cần **thống kê mọi cạnh bị từ chối** như chương trình ở phần 11, phải duyệt hết input. Với đồ thị không liên thông, không thể tự kết luận lỗi từ việc chưa đủ n-1 cạnh khi mới duyệt một phần input; phải xét đủ cạnh hoặc có thông tin liên thông từ trước.

## 5. Ví dụ đồ thị không liên thông: Minimum Spanning Forest

Xét n=6 và các cạnh:

~~~text
0--1 weight  2
1--2 weight -1
0--2 weight  5
3--4 weight  0

Dinh 5 co lap.
~~~

Ba thành phần liên thông ban đầu của graph gốc:

~~~text
{0,1,2}
{3,4}
{5}
~~~

Kruskal sort theo trọng số:

~~~text
(1-2:-1) -> lay
(3-4: 0) -> lay
(0-1: 2) -> lay
(0-2: 5) -> bo, vi 0 va 2 da chung tap
~~~

Rừng khung nhỏ nhất:

~~~text
Selected edges = [(1-2:-1),(3-4:0),(0-1:2)]
Total weight = -1+0+2 = 1
Components = 3
Selected edge count = n-c = 6-3 = 3
~~~

Kruskal đã trải hết từng thành phần gốc, nhưng **không có cây khung nối cả sáu đỉnh** vì đỉnh 5 không có đường nào tới những đỉnh khác. API Java trả **hasSpanningTree=false**, đồng thời vẫn cung cấp một **rừng khung nhỏ nhất** đầy đủ.

Đừng báo “MST weight = 1” như thể có một cây nối mọi đỉnh. Diễn đạt đúng là **MSF weight = 1; components = 3; no spanning tree**.

### Định nghĩa MSF tránh ngộ nhận

Nếu chỉ yêu cầu một tập cạnh không chu trình với tổng nhỏ nhất **mà không yêu cầu trải hết các thành phần gốc**, người ta có thể chọn những cạnh âm và bỏ các cạnh dương (hoặc chọn tập rỗng khi toàn cạnh dương). Đó **không phải bài toán MSF chuẩn**. Trong MSF, mỗi thành phần liên thông gốc phải được nối thành một cây.

Đối với một đỉnh cô lập như 5, cây thành phần của nó có **0 cạnh và trọng số 0**. Nó vẫn đóng góp một đơn vị vào số thành phần c.

## 6. Vì sao Kruskal đúng? Tính chất cắt (cut property)

Một **phép cắt (cut)** chia tập đỉnh thành hai tập không rỗng S và V\S. Cạnh **băng qua cut** là cạnh có một đầu ở S và đầu kia ở V\S.

**Tính chất cắt:** cho một cut không cắt qua bất kỳ cạnh nào trong rừng an toàn đã chọn, một cạnh có **trọng số nhỏ nhất** trong các cạnh băng qua cut là **an toàn**: có ít nhất một MST chứa rừng đang chọn và có chứa cạnh đó.

Khi Kruskal xét một cạnh e=(u,v,w) và DSU thấy u,v thuộc hai cây khác nhau, xét S là tập đỉnh trong cây DSU chứa u **ngay trước khi lấy e**. Cạnh e băng qua cut (S,V\S), và không có cạnh đã chọn nào băng qua cut ấy.

Vì thuật toán xét cạnh theo thứ tự trọng số không giảm, nếu tồn tại một cạnh băng qua cut **nhẹ hơn e**, cạnh ấy đã được xét trước đó. Lúc ấy hai đầu của nó **không thể đã thuộc cùng một cây DSU** (các cây chỉ có thể gộp, không tách, và hiện chúng ở hai phía cut), nên Kruskal hẳn đã chọn nó và làm thay đổi cut. Mâu thuẫn. Do đó e là một **cạnh nhẹ nhất** băng qua cut này, với trường hợp hòa được xử lý tùy thứ tự cố định.

Từ tính chất cắt, thêm e không làm mất khả năng hoàn thành thành một MST. Lặp lại từ rừng rỗng đến khi đã nối đủ các đỉnh sẽ tạo một MST.

### Chứng minh trao đổi (exchange argument) cho cut property

Giả sử đã có một MST T chứa mọi cạnh Kruskal chọn trước đó. Nếu T đã chứa e, không cần làm gì.

Nếu T chưa có e, thêm e vào T tạo **một chu trình**. Chu trình ấy phải có một cạnh f khác cũng băng qua cut S,V\S (vì đi từ S sang ngoài S rồi quay về S). Theo việc e nhẹ nhất băng qua cut, ta có w(e)≤w(f).

Thay f bằng e:

~~~text
T' = T + e - f
~~~

T' vẫn nối tất cả các đỉnh và không có chu trình, nên là một cây khung. Tổng trọng số:

~~~text
weight(T') = weight(T) + w(e) - w(f)
weight(T') <= weight(T)
~~~

Vì T đã là MST, T' cũng là MST; đồng thời T' chứa e và giữ mọi cạnh Kruskal chọn trước đó. Do vậy e an toàn để chọn.

Lập luận áp dụng cả khi w âm hoặc bằng nhau, vì chỉ dựa vào so sánh trọng số, không dựa vào giả định w≥0.

### Đồ thị không liên thông

Nếu graph gốc có nhiều thành phần, áp dụng lập luận riêng cho từng thành phần **liên thông**. Không có cạnh giữa hai thành phần gốc, nên thuật toán không thể gộp chúng. Trong từng thành phần, các cạnh được chọn tạo MST của thành phần ấy. Hợp của những cây này là **MSF**.

## 7. Tính chất chu trình (cycle property) và quyết định bỏ cạnh

**Tính chất chu trình:** nếu một cạnh e là cạnh **nặng nhất duy nhất (strictly heavier)** trong một chu trình, thì e **không thuộc bất kỳ MST nào** của đồ thị liên thông tương ứng.

Với trường hợp có nhiều cạnh cùng đạt trọng số lớn nhất, không thể kết luận mọi cạnh lớn nhất đều bị loại khỏi **mọi** MST; có thể tồn tại các MST khác nhau chọn những cạnh khác nhau trong nhóm hòa.

Trong Kruskal, nếu union(u,v)=false, rừng đã chọn có một đường đi từ u đến v. Thêm e=(u,v) sẽ khép một chu trình. Vì mọi cạnh trên đường đi đã được xét và chọn **trước e**, trọng số của chúng **không lớn hơn** w(e) theo thứ tự sort.

Do vậy e là **một cạnh nặng nhất** trên chu trình vừa tạo. Bỏ e là an toàn đối với quá trình xây một MST/MSF bằng Kruskal, kể cả khi có cạnh bằng trọng số. Khi có cạnh hòa, có thể tồn tại MST khác chọn e thay vì một cạnh khác, nhưng thuật toán chỉ cần trả **một** MST.

### Ví dụ tam giác

~~~text
0--1 weight 1
1--2 weight 2
0--2 weight 3
~~~

Kruskal lấy cạnh 1 rồi cạnh 2; khi gặp cạnh 0–2 trọng số 3, hai đầu đã nối bằng đường 0–1–2. Thêm cạnh 3 tạo chu trình, nên bỏ nó; tổng MST là 3.

Nếu cả ba cạnh đều có trọng số 1, bất kỳ hai cạnh nào cũng tạo MST trọng số 2. Không có một MST duy nhất, nhưng Kruskal vẫn đúng với một quy tắc phá hòa nhất quán.

### Cạnh song song

Hai cạnh giữa cùng một cặp đỉnh u,v cũng có thể tạo một chu trình dài hai cạnh trong mô hình đa đồ thị vô hướng. Kruskal xét cạnh rẻ hơn trước, gộp u,v. Khi cạnh nặng hơn đến, DSU báo cùng tập và bỏ nó. Nếu bằng trọng số, chọn cạnh nào cũng cho tổng MST như nhau.

### Vì sao không thể luôn chọn cạnh rẻ nhất cho từng đỉnh?

Lựa chọn tối ưu ở cấp từng đỉnh không đảm bảo cây khung: những cạnh “rẻ nhất cục bộ” có thể tạo chu trình, bỏ sót đỉnh khác hoặc không tối ưu toàn cục. Kruskal xét cạnh **theo thứ tự toàn đồ thị** và dùng DSU để duy trì cấu trúc rừng an toàn.

## 8. Trọng số âm, trọng số bằng nhau và cạnh đặc biệt

### Trọng số âm không làm Kruskal sai

Xét n=4 với các cạnh:

~~~text
0--1 weight -3
1--2 weight  2
0--2 weight  4
2--3 weight -1
1--3 weight  6
~~~

Thứ tự xét bắt đầu với -3, -1, 2. Các cạnh được chọn:

~~~text
(0-1:-3)
(2-3:-1)
(1-2:2)
~~~

Tổng MST:

~~~text
-3 + (-1) + 2 = -2
~~~

Hai cạnh còn lại sẽ tạo chu trình khi thêm vào rừng đang có. Với MST, trọng số âm là hợp lệ: ta chỉ cần tìm cây nối đủ đỉnh có tổng nhỏ nhất. Đây là khác biệt với **Dijkstra đường đi ngắn nhất**, nơi cạnh âm làm mất bảo đảm của thuật toán chuẩn.

### Cạnh có trọng số bằng nhau

Nếu hai cạnh có cùng trọng số, thứ tự xét giữa chúng có thể ảnh hưởng **hình dạng MST**, nhưng không ảnh hưởng **tổng trọng số nhỏ nhất**. Để output dễ tái lập, mã Java chọn tie-breaking:

~~~text
1. Tang dan theo weight.
2. Neu hoa, tang dan theo min(u,v).
3. Neu van hoa, tang dan theo max(u,v).
4. Neu canh hoan toan trung nhau, de nguyen thu tu input.
~~~

Lưu ý cạnh vô hướng (u,v) và (v,u) đại diện cho **cùng cặp đỉnh**; chuẩn hóa endpoints khi so sánh giúp không phụ thuộc chiều viết cạnh.

Ví dụ các cạnh đều trọng số 1:

~~~text
0--1, 0--2, 1--2, 1--3, 2--3
~~~

Sau sắp sort, Kruskal lấy (0,1), (0,2), bỏ (1,2) vì tạo chu trình rồi lấy (1,3). Tổng MST=3. Cách chọn khác có thể vẫn đạt trọng số 3.

### Self-loop và cạnh trùng

- **Self-loop (u,u):** DSU.find(u)==DSU.find(u), luôn bị bỏ; không cần quy tắc riêng trong vòng Kruskal.
- **Cạnh song song cùng endpoints:** mỗi cạnh được xét riêng. DSU đảm bảo chỉ một cạnh trong số chúng có thể nối hai tập tại thời điểm phù hợp.
- **Đỉnh cô lập:** vẫn là một tập riêng trong DSU, đóng góp một component cho rừng khung.
- **Graph không cạnh:** với n>0, mỗi đỉnh là một cây đơn; MSF có n component và trọng số 0.
- **Graph n=1:** cây khung có 0 cạnh, trọng số 0, ngay cả khi có self-loop (self-loop bị bỏ).

### Đồ thị rỗng n=0

Một graph không đỉnh có rừng khung rỗng, tổng trọng số 0 và số thành phần 0. Quy ước “có MST không” đối với graph rỗng có thể khác giữa bài toán và tài liệu. API trong bài **định nghĩa hasSpanningTree=false cho n=0**, vì không có tập đỉnh không rỗng nào cần nối. Điều này chỉ là **hợp đồng output rõ ràng**, không phải một định lý phổ quát về graph rỗng.

## 9. Cách cài DSU đúng và các lỗi tinh vi

### Luôn cập nhật size ở root

Khi union hai tập với root ra và rb, sau khi gắn rb dưới ra thì cập nhật **size[ra] += size[rb]**. Không được cập nhật size ở một đỉnh bất kỳ không phải root rồi suy ra đó là kích thước cả tập.

Sau union, size[rb] có thể giữ giá trị cũ; mã chỉ đọc size tại **root hiện tại**, nên không cần cập nhật tất cả size của các đỉnh. Muốn lấy kích thước tập chứa v, phải tính root=find(v) rồi đọc size[root].

### Phải dùng find để kiểm liên thông

Kiểm parent[u]==parent[v] trực tiếp có thể sai, vì parent của một nút có thể là một nút trung gian, chưa phải đại diện cuối cùng. Chỉ **find(u)==find(v)** mới biểu diễn chắc chắn rằng hai đỉnh nằm cùng tập.

Path compression/path halving có thể thay đổi parent mà **không đổi** phân hoạch. Vì vậy không nên so mảng parent byte-for-byte để kiểm tính đúng của DSU; hãy kiểm quan hệ cùng tập và các kích thước ở root.

### Nếu union không giảm components

Một lỗi phổ biến là giảm components mỗi lần gọi union, kể cả khi hai đầu đã cùng tập. Điều đó làm số thành phần âm hoặc khiến thuật toán báo liên thông sai. Chỉ khi hai root khác nhau và thực hiện gộp mới **components--**.

### Kiểm tra chỉ số trước khi truy cập mảng

DSU trong ví dụ dùng mảng kích thước n; các đỉnh hợp lệ phải ở [0,n). Nếu đầu vào edge có u<0 hoặc u≥n, find/union có thể ném lỗi chỉ số. API kruskal xác thực toàn bộ edge **trước khi** sort và union, giúp lỗi được báo có ngữ nghĩa rõ ràng.

### Comparator không được trừ trọng số để so

Đừng viết:

~~~java
return (int) (a.weight() - b.weight());
~~~

Phép trừ long có thể **tràn số**, ép long sang int có thể cắt mất bit và dẫn tới thứ tự sort sai, cuối cùng trả MST không tối ưu.

Dùng Comparator.comparingLong(Edge::weight), hoặc Long.compare(a.weight(),b.weight()). Cả hai so sánh đúng toàn miền long mà không cần tự trừ.

### Tổng trọng số có thể vượt long

Ngay cả khi trọng số **mỗi cạnh** nằm trong long, tổng của n-1 cạnh có thể vượt Long.MAX_VALUE hoặc nhỏ hơn Long.MIN_VALUE. Ví dụ hai cạnh đều có trọng số Long.MAX_VALUE tạo tổng:

~~~text
9223372036854775807 + 9223372036854775807
= 18446744073709551614
~~~

Trong mã, tổng MST/MSF dùng **BigInteger** để tránh overflow; không dùng long += weight nếu đề cho kích thước/trọng số có thể vượt miền.

## 10. Độ phức tạp: sort cạnh chi phối, DSU gần hằng số

Đặt n=|V|, m=|E|. Kruskal thực hiện:

1. Khởi tạo DSU với n singleton: **O(n)** thời gian và bộ nhớ.
2. Sao chép và sort m cạnh theo trọng số: **O(m log(m+1))** thời gian.
3. Với mỗi cạnh, thực hiện tối đa một union và các find tương ứng: **O(m α(n))** thời gian khấu hao với path compression và union by size.
4. Lưu danh sách các cạnh được chọn: tối đa n-c cạnh, không quá n-1 khi n>0.

Tổng:

~~~text
Time: O(n + m log(m+1) + m * alpha(n))
      thong thuong viet O(m log m) khi m du lon.

Extra memory: O(n + m) trong ma Java demo
              (DSU O(n), sorted edges O(m), selected <= n-1).
~~~

Hàm α(n), Ackermann nghịch đảo, tăng cực chậm; với kích thước thực tế, số bước find khấu hao rất nhỏ. Chính việc **sort cạnh** thường chiếm phần lớn thời gian.

### Nếu đồ thị ban đầu không liên thông

DSU vẫn xử lý mọi cạnh, và số component cuối cùng bằng **số thành phần liên thông vô hướng của graph gốc**. Số selected cuối cùng là **n-components**. Không cần chạy DFS/BFS riêng trước đó nếu mục tiêu là lấy một MSF và báo có MST hay không.

### Khai báo chi phí BigInteger một cách chính xác

Phân tích O(m log m + m α(n)) giả định so sánh trọng số long và phép cộng tổng có chi phí đơn vị. Trong chương trình, mỗi lần chọn một cạnh, BigInteger được cập nhật; số bit của tổng có thể tăng theo kích thước đầu vào, nên thời gian số học BigInteger có thể phụ thuộc số bit. Đổi lại, kết quả không bị tràn long. Với bài lập trình giới hạn trọng số chặt, long có kiểm tra overflow có thể nhanh hơn.

### Có thể dừng sớm không?

Nếu đã kết nối tất cả n đỉnh của graph liên thông (components==1, n>0), phần còn lại không thể tạo cạnh an toàn, nên có thể break khi chỉ cần kết quả MST.

Mã demo **không dừng sớm** vì in số cạnh bị từ chối do chu trình (rejectedCycleEdges). Đây là lựa chọn báo cáo thống kê, không làm thay đổi tập MST được chọn hay tính đúng.

## 11. Java 17 – Kruskal và DSU chạy độc lập

Chương trình sau dùng:

- record **Edge(u,v,weight)** cho cạnh vô hướng.
- DSU với **path halving** và **union by size**, theo dõi số component.
- Comparator sort theo weight, rồi endpoints chuẩn hóa.
- **BigInteger** để cộng tổng trọng số mà không tràn long.
- ForestResult trả cạnh đã chọn, tổng chi phí, số component, cờ có cây khung và số cạnh bị từ chối.
- Các ca minh họa: connected MST, disconnected MSF, trọng số âm, tie, parallel edge, singleton/self-loop, graph rỗng, tổng lớn hơn long và edge sai phạm vi.

**Lưu đúng một tệp tên KruskalDsuDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class KruskalDsuDemo {

    record Edge(int u, int v, long weight) {
        @Override
        public String toString() {
            return "(" + u + "-" + v + ":" + weight + ")";
        }
    }

    record ForestResult(
            List<Edge> chosen,
            BigInteger totalWeight,
            int components,
            boolean hasSpanningTree,
            int rejectedCycleEdges) {}

    static final class Dsu {
        private final int[] parent;
        private final int[] size;
        private int components;

        Dsu(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            for (int v = 0; v < n; v++) {
                parent[v] = v;
                size[v] = 1;
            }
        }

        // Find with iterative path halving.
        int find(int x) {
            while (parent[x] != x) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        // Return true only when two different sets merge.
        boolean union(int a, int b) {
            int ra = find(a);
            int rb = find(b);
            if (ra == rb) {
                return false;
            }
            if (size[ra] < size[rb]) {
                int temp = ra;
                ra = rb;
                rb = temp;
            }
            parent[rb] = ra;
            size[ra] += size[rb];
            components--;
            return true;
        }

        int components() {
            return components;
        }
    }

    static ForestResult kruskal(int n, List<Edge> input) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "n must be nonnegative");
        }
        Objects.requireNonNull(input, "input");

        // Validate all endpoints before sorting/union.
        for (Edge e : input) {
            if (e == null
                    || e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException("invalid edge");
            }
        }

        List<Edge> sorted = new ArrayList<>(input);
        sorted.sort(
                Comparator.comparingLong(Edge::weight)
                        .thenComparingInt(
                                e -> Math.min(e.u(), e.v()))
                        .thenComparingInt(
                                e -> Math.max(e.u(), e.v())));

        Dsu dsu = new Dsu(n);
        List<Edge> chosen = new ArrayList<>();
        BigInteger totalWeight = BigInteger.ZERO;
        int rejectedCycleEdges = 0;

        for (Edge e : sorted) {
            if (dsu.union(e.u(), e.v())) {
                chosen.add(e);
                totalWeight = totalWeight.add(
                        BigInteger.valueOf(e.weight()));
            } else {
                rejectedCycleEdges++;
            }
        }

        // Contract: empty graph has an empty forest, not an MST.
        boolean hasSpanningTree =
                n > 0 && dsu.components() == 1;

        return new ForestResult(
                List.copyOf(chosen),
                totalWeight,
                dsu.components(),
                hasSpanningTree,
                rejectedCycleEdges);
    }

    public static void main(String[] args) {
        ForestResult connected = kruskal(6, List.of(
                new Edge(0, 1, 4),
                new Edge(0, 2, 3),
                new Edge(1, 2, 1),
                new Edge(1, 3, 2),
                new Edge(2, 3, 4),
                new Edge(3, 4, 2),
                new Edge(4, 5, 6),
                new Edge(3, 5, 7),
                new Edge(2, 5, 10),
                new Edge(0, 0, -9),
                new Edge(1, 2, 5),
                new Edge(0, 3, 5)));

        System.out.println("connected edges = " +
                connected.chosen());
        System.out.println("connected weight = " +
                connected.totalWeight());
        System.out.println("connected components = " +
                connected.components());
        System.out.println("connected has MST = " +
                connected.hasSpanningTree());
        System.out.println("connected rejected = " +
                connected.rejectedCycleEdges());

        ForestResult disconnected = kruskal(6, List.of(
                new Edge(0, 1, 2),
                new Edge(1, 2, -1),
                new Edge(0, 2, 5),
                new Edge(3, 4, 0)));
        System.out.println("disconnected edges = " +
                disconnected.chosen());
        System.out.println("disconnected weight = " +
                disconnected.totalWeight());
        System.out.println("disconnected components = " +
                disconnected.components());
        System.out.println("disconnected has MST = " +
                disconnected.hasSpanningTree());

        ForestResult negative = kruskal(4, List.of(
                new Edge(0, 1, -3),
                new Edge(1, 2, 2),
                new Edge(0, 2, 4),
                new Edge(2, 3, -1),
                new Edge(1, 3, 6)));
        System.out.println("negative edges = " +
                negative.chosen());
        System.out.println("negative weight = " +
                negative.totalWeight());

        ForestResult equal = kruskal(4, List.of(
                new Edge(0, 1, 1),
                new Edge(0, 2, 1),
                new Edge(1, 2, 1),
                new Edge(1, 3, 1),
                new Edge(2, 3, 1)));
        System.out.println("tie edges = " + equal.chosen());

        ForestResult parallel = kruskal(2, List.of(
                new Edge(0, 1, 5),
                new Edge(0, 1, 2),
                new Edge(0, 1, 2)));
        System.out.println("parallel edges = " +
                parallel.chosen());

        ForestResult singleton = kruskal(1, List.of(
                new Edge(0, 0, -5)));
        System.out.println("singleton components = " +
                singleton.components() +
                ", has MST = " + singleton.hasSpanningTree());

        ForestResult empty = kruskal(0, List.of());
        System.out.println("empty components = " +
                empty.components() +
                ", has MST = " + empty.hasSpanningTree());

        ForestResult huge = kruskal(3, List.of(
                new Edge(0, 1, Long.MAX_VALUE),
                new Edge(1, 2, Long.MAX_VALUE)));
        System.out.println("overflow-safe weight = " +
                huge.totalWeight());

        try {
            kruskal(2, List.of(new Edge(0, 2, 1)));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid input: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac KruskalDsuDemo.java
java KruskalDsuDemo
~~~

**Stdout chính xác** với tie-breaking trong chương trình:

~~~text
connected edges = [(1-2:1), (1-3:2), (3-4:2), (0-2:3), (4-5:6)]
connected weight = 14
connected components = 1
connected has MST = true
connected rejected = 7
disconnected edges = [(1-2:-1), (3-4:0), (0-1:2)]
disconnected weight = 1
disconnected components = 3
disconnected has MST = false
negative edges = [(0-1:-3), (2-3:-1), (1-2:2)]
negative weight = -2
tie edges = [(0-1:1), (0-2:1), (1-3:1)]
parallel edges = [(0-1:2)]
singleton components = 1, has MST = true
empty components = 0, has MST = false
overflow-safe weight = 18446744073709551614
invalid input: invalid edge
~~~

### Cách đọc ví dụ Java

Trong đồ thị connected, cạnh self-loop có trọng số âm -9 bị DSU.union(0,0) từ chối. Năm cạnh được chọn có tổng bằng 14, các cạnh còn lại tạo chu trình nên rejected=7. Kết quả components=1 và hasSpanningTree=true xác nhận chúng tạo MST.

Trong đồ thị disconnected, các cạnh được chọn trải hết hai thành phần có cạnh và giữ đỉnh 5 cô lập, vì vậy components=3 và hasSpanningTree=false. Tổng 1 là **trọng số MSF**, không phải trọng số một cây khung của toàn bộ graph.

Trong ví dụ negative, các cạnh -3 và -1 là hoàn toàn hợp lệ; cây khung có tổng âm -2. Ví dụ tie chỉ ra một MST cụ thể với tổng 3. Ví dụ parallel chọn cạnh rẻ nhất và bỏ hai cạnh còn lại vì cùng cặp đỉnh đã liên thông.

Với singleton, đồ thị một đỉnh được xem là có cây khung rỗng (0 cạnh), ngay cả khi có self-loop âm. Với empty, chương trình dùng quy ước báo không có MST dù có MSF rỗng. Các trường hợp này được nêu rõ để không tạo mâu thuẫn khi người học tự test.

Trong ví dụ overflow, tổng hai trọng số Long.MAX_VALUE là **18446744073709551614**, vượt long, nhưng BigInteger hiển thị chính xác.

### Hợp đồng dữ liệu và tính bất biến

- n phải không âm; mỗi endpoint phải thuộc [0,n). Cạnh sai phạm vi được từ chối trước khi gọi DSU.
- Input là danh sách **cạnh vô hướng**. Đừng thêm cả (u,v) và (v,u) chỉ vì quen tạo adjacency list; nếu có thì chúng trở thành hai cạnh song song, vẫn cho kết quả trọng số đúng nhưng làm phát sinh xử lý thừa.
- Edge là record; ForestResult giữ List.copyOf(chosen), và mỗi Edge là một record bất biến. DSU không được trả ra ngoài nên người gọi không thể sửa phân hoạch sau khi giải.
- Comparator đã chọn quy tắc phá hòa, nhưng một đồ thị có thể có nhiều MST hợp lệ. Không nên kiểm thử một thứ tự edges duy nhất nếu đề hoặc thuật toán không quy định tie-breaking.
- Code ưu tiên clarity: các trường hợp n=0, n=1 và graph có self-loop được định nghĩa rõ. Một API khác có thể chọn cách báo lỗi n=0; cả hai phải nêu hợp đồng.
- Nếu các trọng số đầu vào nằm ngoài miền long, cần thay record Edge.weight bằng BigInteger hoặc kiểu số thích hợp, không thể chỉ đổi biến tổng.

## 12. Chứng minh tính đúng của DSU và Kruskal

### Bất biến DSU

Tại bất kỳ thời điểm nào, hai đỉnh u,v có cùng find root **khi và chỉ khi** chúng nằm trong cùng một thành phần liên thông của rừng selected.

**Cơ sở:** trước khi chọn cạnh, không có cạnh nối các đỉnh; mỗi đỉnh là một singleton, DSU cũng có một tập riêng.

**Bước quy nạp:** nếu xét một cạnh u–v mà find(u)==find(v), hai đỉnh đã nối bởi một đường trong rừng; bỏ cạnh thì cấu trúc rừng và phân hoạch DSU đều không đổi.

Nếu find(u)!=find(v), hai đỉnh thuộc hai cây khác nhau; chọn cạnh nối hai cây và union hai tập tương ứng. Cả quan hệ liên thông trong rừng và quan hệ cùng DSU root đều được gộp cùng một cách. Bất biến được duy trì.

Hệ quả: DSU.union trả true chính xác khi thêm cạnh không tạo chu trình. Nếu union trả false thì đã có đường giữa hai đầu, nên thêm cạnh tạo chu trình.

### Bất biến an toàn của rừng tham lam

Sau mọi bước, rừng selected có thể mở rộng thành một MST của từng thành phần liên thông trong graph gốc.

**Cơ sở:** rừng rỗng là tập con của một MST nào đó trong mỗi thành phần gốc, nếu thành phần có ít nhất một đỉnh.

**Bước:** khi Kruskal lấy e nối hai tập khác nhau, tính chất cắt và exchange argument ở phần 6 bảo đảm tồn tại một MST chứa cả selected cũ và e. Khi Kruskal bỏ e, selected không đổi nên tính chất không mất.

### Khi kết thúc

Mọi cạnh E đã được xét. Nếu hai đỉnh thuộc **cùng một thành phần liên thông của graph gốc** mà vẫn ở hai tập DSU khác nhau, tồn tại đường trong graph gốc giữa chúng. Trên đường đó phải có ít nhất một cạnh nối hai tập DSU khác nhau tại cuối thuật toán. Cạnh ấy đã được xét, và vì các tập DSU chỉ gộp chứ không tách, lúc xét nó cũng nối hai tập khác nhau nên phải được chọn. Mâu thuẫn.

Do vậy mỗi thành phần gốc đã được gộp thành đúng một cây trong rừng selected; số cạnh là n-c. Kết hợp tính an toàn của từng cạnh chọn, ta được **MSF tối ưu**. Nếu c=1 và n>0, đó chính là **MST**.

### Đúng cả khi cạnh âm và cạnh hòa

Chứng minh chỉ dùng so sánh w(e)≤w(f), không dùng giả định w≥0, nên trọng số âm không phá tính đúng. Khi w(e)==w(f), exchange argument vẫn tạo một MST khác có tổng bằng nhau; thuật toán có thể chọn bất kỳ cạnh nào trong nhóm hòa mà vẫn an toàn.

## 13. So sánh với Prim và các phương pháp khác

| Thuật toán | Cách xây MST/MSF | Cấu trúc dữ liệu điển hình | Độ phức tạp phổ biến |
| --- | --- | --- | --- |
| Kruskal | Sort cạnh toàn cục, lấy cạnh không tạo chu trình | DSU + sort | O(m log m + m α(n)) |
| Prim | Từ một cây đang tăng, lấy cạnh nhẹ nhất vượt cut | Min-heap + adjacency list | O(m log n) phổ biến |
| Borůvka | Mỗi thành phần đồng thời lấy cạnh nhẹ nhất đi ra | DSU + duyệt cạnh | O(m log n) |
| DFS/BFS | Duyệt một đồ thị, dựng cây bao phủ tùy thứ tự | Stack/queue | O(n+m), **không bảo đảm tối thiểu trọng số** |

### Kruskal và Prim khác nhau ở đâu?

**Kruskal:** bắt đầu với n cây đơn đỉnh và gộp các cây. Nó không cần một đỉnh nguồn. Khi xét cạnh nhẹ, có thể chọn một cạnh ở bất cứ thành phần nào trên toàn graph.

**Prim:** bắt đầu từ một đỉnh nguồn và mở rộng **một cây** bằng cạnh nhẹ nhất nối từ cây hiện tại ra đỉnh mới. Với graph không liên thông, một lượt Prim từ một nguồn chỉ tìm cây trong thành phần chứa nguồn; muốn MSF phải lặp trên các thành phần khác.

Cả hai đều dựa trên **cut property**. Cả hai vẫn đúng với trọng số âm trong bài MST; không được nhầm Prim với Dijkstra chỉ vì cả hai có thể dùng priority queue.

### Khi nên chọn Kruskal?

- Đầu vào đã ở dạng **danh sách cạnh**.
- Cần MSF cả khi graph không liên thông.
- Thích triển khai gọn với sort và DSU.
- Có nhiều cạnh thưa; DSU kiểm tra chu trình rất hiệu quả.

### Khi nên chọn Prim?

- Graph được lưu sẵn bằng danh sách kề, muốn mở rộng cây từ một vùng.
- Có thể hưởng lợi từ việc không cần sort **toàn bộ** danh sách cạnh một lần trong một số cài đặt/miền dữ liệu.
- Graph dày với ma trận kề có thể dùng một biến thể Prim O(n²) đơn giản, đôi khi phù hợp hơn sort m≈n² cạnh.

Không có một thuật toán MST luôn tối ưu nhất về thời gian/memory cho mọi loại input; cần nhìn vào mật độ cạnh, cấu trúc dữ liệu và yêu cầu output.

## 14. MST không phải cây đường đi ngắn nhất (SPT)

Đây là một khác biệt quan trọng giữa hai chủ đề **Cây khung** và **Đường đi ngắn nhất**.

Một cây MST tối thiểu hóa **tổng trọng số tất cả cạnh trong cây**. Một **shortest-path tree (SPT)** từ nguồn s cố gắng giữ khoảng cách từ s tới mọi đỉnh tối ưu so với graph gốc.

Xét tam giác:

~~~text
0--1 weight 2
1--2 weight 2
0--2 weight 3
~~~

Kruskal chọn hai cạnh trọng số 2, tạo MST với tổng 4:

~~~text
0 --(2)-- 1 --(2)-- 2
~~~

Nhưng khoảng cách từ 0 tới 2 **trong cây MST** là 2+2=4, còn trong graph gốc có cạnh trực tiếp 0–2 trọng số 3. Do đó cây MST **không phải** một SPT từ 0.

Ngược lại, một SPT có thể sử dụng cạnh dài để rút ngắn một vài đường từ nguồn nhưng làm **tổng trọng số các cạnh của toàn cây** lớn hơn MST.

**Câu hỏi chọn thuật toán:**

- “Nối tất cả điểm với **chi phí xây mạng** thấp nhất” → MST, Kruskal/Prim.
- “Từ điểm A đến từng điểm khác có **chi phí đường đi** thấp nhất” → shortest-path algorithms (BFS/Dijkstra/Bellman–Ford tùy trọng số).

Nếu đề dùng các từ “minimum cost to connect all nodes”, cần xác định đó là tổng chi phí **các cạnh được xây** hay tổng **khoảng cách đi lại**; hai mục tiêu không giống nhau.

## 15. Kiểm thử bằng thuộc tính và đối chứng brute force

Kruskal thường trả kết quả “trông giống cây”, nhưng có thể sai trọng số khi comparator, DSU hoặc điều kiện nối bị lỗi. Kiểm thử nên kiểm cả tính hợp lệ lẫn tính tối ưu.

### Thuộc tính bắt buộc

1. **Không chu trình:** chạy một DSU mới trên các cạnh chosen; mọi union của cạnh chosen phải trả true.
2. **Trải hết thành phần gốc:** với mọi u,v được nối trong graph gốc, chúng cũng phải được nối trong rừng chosen. Có thể so phân hoạch bằng DSU/BFS độc lập.
3. **Đúng số cạnh:** nếu graph có c thành phần, selected.size()==n-c.
4. **Đúng tổng:** totalWeight bằng tổng trọng số của các cạnh chosen, tính không tràn số.
5. **Đúng status:** với n>0, hasSpanningTree iff components==1; n=0 theo hợp đồng là false.
6. **Mọi cạnh chosen thuộc input:** không tự tạo cạnh mới hoặc đổi trọng số.
7. **Self-loop không được chọn**, bất kể trọng số.
8. **Cạnh song song** không khiến cùng cặp đỉnh được nối thêm lần hai, nếu hai đầu đã ở cùng tập.
9. **Thay thứ tự input** không đổi tổng trọng số MST/MSF; với tie-breaking giống nhau, thường cũng không đổi tập cạnh theo id.
10. **Trọng số âm** không làm mất tính hợp lệ của rừng.

### Brute force làm oracle trên graph nhỏ

Với n≤7, m≤14, có thể liệt kê mọi tập con của các cạnh. Đối với graph liên thông:

- Chỉ giữ tập có đúng n-1 cạnh.
- Dùng DSU kiểm không chu trình.
- Kiểm tất cả đỉnh cùng component.
- Lấy trọng số nhỏ nhất trong những tập hợp lệ.

Với graph không liên thông:

- Tính c bằng một DFS/DSU độc lập trên **toàn bộ cạnh gốc**.
- Chỉ xét các tập có đúng n-c cạnh, không chu trình.
- Kiểm chúng tạo liên thông đúng trong từng thành phần gốc.
- Lấy tổng nhỏ nhất trong các rừng hợp lệ.

Kết quả brute force phải bằng tổng Kruskal. Với rất nhiều cạnh, brute force 2^m tăng cấp số mũ và không thể dùng để giải bài lớn; nó chỉ là oracle test cho dữ liệu nhỏ.

### Đối chứng với Prim

Trên đồ thị vô hướng liên thông ngẫu nhiên, chạy cả Kruskal và một cài đặt Prim độc lập; tổng MST phải giống nhau, dù danh sách cạnh có thể khác khi hòa. Đối với graph không liên thông, chạy Prim trên **từng thành phần** để tạo MSF rồi so tổng với Kruskal.

Không nên dùng phiên bản Prim cố tình hạn chế trọng số không âm để làm oracle cho graph có cạnh âm; thuật toán MST Prim **vẫn có thể xử lý cạnh âm** nếu triển khai đúng.

### Các ca biên cần có

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| n=0, m=0 | Forest rỗng, components=0, hasMST=false theo API |
| n=1, không cạnh | Forest rỗng, components=1, hasMST=true |
| n=1, self-loop -5 | Self-loop bị bỏ, MST rỗng |
| n=2, một cạnh -4 | MST có một cạnh, trọng số -4 |
| n=2, hai cạnh song song 5 và 2 | Chọn cạnh trọng số 2 |
| n=3, tam giác trọng số 1,2,3 | Chọn cạnh 1 và 2, tổng 3 |
| n=4, tất cả cạnh cùng trọng số | Có nhiều MST, tổng bằng nhau |
| n=4, ví dụ có cạnh âm | MST total=-2 |
| n=6, graph connected của bài | MST total=14, chọn 5 cạnh |
| n=6, graph disconnected | MSF total=1, components=3 |
| Có đỉnh cô lập | Không có MST toàn graph nếu n>1 |
| Có trọng số Long.MAX_VALUE trên 2 cạnh cây | BigInteger total=18446744073709551614 |
| Cạnh chứa endpoint ngoài [0,n) | IllegalArgumentException |
| Input n âm, list null hoặc Edge null | Từ chối input theo API |

### Một kiểm thử chuyển dạng hữu ích

Đổi nhãn các đỉnh bằng một hoán vị bất kỳ, đồng thời đổi endpoints của mọi cạnh theo hoán vị. **Tổng trọng số MST/MSF phải không đổi**, vì cấu trúc và trọng số graph không thay đổi về mặt toán học. Danh sách cạnh được in ra sẽ đổi nhãn, nên không so chuỗi nguyên văn.

Đổi tất cả trọng số thành w+c với cùng c **không nhất thiết** giữ nguyên tổng trọng số nhưng vì mọi spanning forest đầy đủ có cùng số cạnh n-c, tổng của mỗi forest tăng **c(n-c)**. Vì vậy tập các forest tối ưu không thay đổi khi cộng cùng một hằng số vào mọi trọng số (nếu phép cộng không overflow); đây là phép kiểm rất tốt cho tính đúng của thuật toán.

Tương tự, nhân tất cả trọng số với một hằng số **dương** giữ thứ tự so sánh và tính tối ưu; nhân với hằng số âm đảo thứ tự, nên không còn bảo toàn MST theo cách đơn giản.

## 16. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Sửa |
| --- | --- | --- |
| Sort giảm dần | Tạo cây khung lớn nhất hoặc sai MST | Sort trọng số tăng dần |
| So comparator bằng phép trừ long | Overflow, thứ tự cạnh sai | Long.compare/comparingLong |
| Chọn mọi cạnh âm dù tạo chu trình | Kết quả không còn cây | Vẫn kiểm union |
| Không kiểm chu trình | Có thể chọn hơn n-1 cạnh | DSU.union phải quyết định |
| So parent[u]==parent[v] | Nhầm khi parent có nút trung gian | Dùng find(u)==find(v) |
| Không path compression | find có thể chậm | Nén đường đi/path halving |
| Gộp cây lớn dưới cây nhỏ liên tục | Cây đại diện sâu hơn | Union by size/rank |
| Giảm components ngay cả khi union=false | Sai số thành phần | Giảm khi thực sự gộp |
| Không khởi tạo mọi đỉnh | Bỏ đỉnh cô lập | DSU(n) với n phần tử |
| Giả định graph luôn liên thông | Trả forest như một MST | Kiểm components==1 |
| Cho rằng MSF được bỏ cạnh dương tùy ý | Không trải hết thành phần gốc | Bắt buộc n-c cạnh |
| Thêm cả hai hướng như hai cạnh input | Dư cạnh, tăng số lượt | Input vô hướng chỉ cần mỗi cạnh một record |
| Nhầm Kruskal với topo hoặc Dijkstra | Chọn thuật toán sai mục tiêu | Phân biệt cây khung/đường đi |
| Coi self-loop âm là có lợi | Vi phạm không chu trình | Union(u,u)=false |
| Gộp edge trùng không nhất quán | Bỏ cạnh rẻ hoặc thay trọng số | Giữ từng Edge đúng hoặc chuẩn hóa an toàn |
| Tổng trọng số bằng long không kiểm tra | Tràn số khi cộng nhiều cạnh | BigInteger hoặc addExact |
| Đòi MST duy nhất khi có tie | Test báo sai giả | So tổng và tính hợp lệ |
| Nêu O(nm) dù dùng DSU tốt | Đánh giá chậm không đúng | O(m log m + m α(n)) |
| Không xác thực endpoint | Lỗi truy cập mảng | Kiểm chỉ số trước union |
| Dừng trước khi duyệt đủ cạnh ở graph disconnected | Bỏ thành phần | Duyệt đủ để lấy MSF |
| Kiểm MST chỉ bằng số cạnh n-1 | Có thể không nối đủ đỉnh nếu không kiểm chu trình | Kiểm cả connected và acyclic |

**Lưu ý quan trọng:** rừng selected có đúng n-c cạnh và không chu trình, **nếu các cạnh ấy nối đủ các thành phần gốc**, thì nó là một rừng khung. Nhưng hai điều kiện “đúng số cạnh” và “không chu trình” cần được đối chiếu với c thật của graph gốc; không đoán c bằng số đỉnh có cạnh trong input.

## 17. Bài tập thực hành

1. Cho tam giác với cạnh 0–1 (1), 1–2 (2), 0–2 (3). Mô phỏng Kruskal và DSU, ghi sau mỗi cạnh: find(u),find(v), quyết định và số component.
2. Với graph connected 6 đỉnh ở phần 4, tự sort cạnh theo tie-breaking và điền bảng union. Chứng minh tổng MST=14 bằng cut property trên từng cạnh được chọn.
3. Bỏ cạnh 4–5 (6) khỏi graph phần 4. Chạy lại Kruskal, xem cạnh nào nối đỉnh 5 và tổng MST thay đổi ra sao.
4. Với graph disconnected ở phần 5, tính số thành phần c độc lập bằng BFS. Kiểm selected.size()==n-c và giải thích tại sao không có MST toàn graph.
5. Cài DSU với path compression đệ quy thay path halving, kết hợp union by rank; đo số lần find trên input ngẫu nhiên và so với union by size.
6. Viết DSU có hàm componentSize(x) trả size[find(x)]. Kiểm sau mỗi union rằng tổng size của các root hiện tại bằng n.
7. Cho một graph có nhiều self-loop âm và cạnh song song. Giải thích vì sao self-loop luôn bị bỏ, còn một cạnh song song rẻ hơn có thể thay cạnh cũ nếu được xét sớm.
8. Dùng brute force liệt kê tất cả subset cạnh cho n≤6,m≤12. So trọng số MST/MSF với Kruskal trên ít nhất 100 graph ngẫu nhiên.
9. Thay comparator sort bằng phép trừ ép int và tạo hai trọng số gần Long.MIN_VALUE/Long.MAX_VALUE. Tìm một phản ví dụ cho thứ tự sort sai.
10. Viết phiên bản Kruskal **dừng sớm** ngay khi selected.size()==n-1, nhưng chỉ dùng khi đã kết nối n đỉnh. So số cạnh xử lý với phiên bản duyệt hết để đếm rejected.
11. Thêm yêu cầu “trả mỗi thành phần rừng” bằng cách gom các đỉnh theo find root sau khi xử lý đủ cạnh; không giả định root là id nhỏ nhất của nhóm.
12. Với n=1 và self-loop trọng số -100, chứng minh MST vẫn có 0 cạnh, trọng số 0; giải thích định nghĩa chu trình.
13. So sánh Kruskal và Prim trên graph có trọng số âm, sau đó trên graph có tất cả trọng số bằng nhau; giải thích vì sao edge list có thể khác nhưng trọng số tối ưu giống nhau.
14. Đưa ra graph mà MST từ Kruskal **không phải** shortest-path tree từ 0. Dùng ví dụ tam giác phần 14 và so khoảng cách từ 0 tới 2.
15. Giả sử yêu cầu tối đa hóa tổng trọng số một cây khung (maximum spanning tree). Bạn sẽ đổi thứ tự sort như thế nào? DSU có cần đổi không?
16. Thử nghiệm phép biến đổi cộng hằng số k vào mọi trọng số, xác minh tổng MSF tăng k(n-c) mà tập forest tối ưu không đổi, nếu không có overflow.
17. Kiểm trường hợp n=0, m=0: so hợp đồng trả forest rỗng với một đặc tả khác định nghĩa graph rỗng có MST rỗng. Vì sao API phải nói rõ quy ước?
18. Đối với đồ thị có hướng, tìm ví dụ cho thấy DSU/Kruskal không bảo đảm một arborescence hợp lệ. Tìm hiểu khi nào dùng thuật toán Chu–Liu/Edmonds.
19. Phân tích bộ nhớ khi có hàng triệu cạnh nhưng rất ít đỉnh. So chi phí sort và DSU, và cách xử lý cạnh song song/streaming tùy yêu cầu.
20. Nếu thêm hoặc xóa cạnh sau khi đã tìm MST, mô tả vì sao cần thuật toán cập nhật MST động hoặc tính lại; DSU chỉ hỗ trợ **gộp tập**, không hỗ trợ tách tập khi xóa cạnh.

## 18. Tổng kết và checklist áp dụng

Trước khi dùng Kruskal với DSU, hãy hỏi:

- **Mục tiêu có phải nối mọi đỉnh với tổng trọng số các cạnh nhỏ nhất không?** Nếu hỏi shortest path, thuật toán MST không phải đáp án.
- **Đồ thị có vô hướng không?** Nếu có hướng, cần mô hình khác cho cây phân nhánh.
- **Có thể có nhiều thành phần không?** Nếu graph không liên thông, trả MSF và cờ không có MST; không giả vờ có một cây nối tất cả.
- **Đã đưa tất cả đỉnh vào DSU chưa?** Không bỏ sót đỉnh cô lập.
- **Đã sort cạnh theo trọng số tăng dần đúng kiểu số chưa?** Tránh comparator trừ gây tràn.
- **DSU có dùng find thực sự, path compression và union by size/rank không?**
- **Chỉ thêm cạnh khi union=true?** Nếu union=false, cạnh khép chu trình và phải bỏ.
- **Tổng trọng số có thể tràn kiểu số không?** Cân nhắc BigInteger hoặc kiểm tra overflow.
- **Có cần thống kê rejected edges không?** Nếu không, có thể dừng khi đã nối tất cả n đỉnh.
- **Đã kiểm các ca self-loop, cạnh song song, trọng số âm, trọng số hòa, n=0 và n=1 chưa?**
- **Đã xác minh bằng cut property/exchange argument và kiểm thử trên graph nhỏ chưa?**

**Kết luận:** Kruskal xây cây/rừng khung nhỏ nhất bằng cách **sort toàn bộ cạnh theo trọng số tăng dần** và **chỉ chọn cạnh nối hai thành phần khác nhau**. DSU với path compression và union by size giúp phát hiện chu trình nhanh, còn **cut property** chứng minh chiến lược tham lam an toàn, kể cả khi trọng số âm hoặc bằng nhau. Đồ thị liên thông cho MST gồm n-1 cạnh; đồ thị không liên thông cho MSF gồm n-c cạnh. Luôn phân biệt **tối ưu tổng chi phí mạng** với **tối ưu khoảng cách đường đi**.
