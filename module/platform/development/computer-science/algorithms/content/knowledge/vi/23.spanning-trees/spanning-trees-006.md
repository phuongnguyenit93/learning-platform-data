# Thuật toán Borůvka và hợp nhất theo thành phần

**Borůvka** (cũng viết *Boruvka*) là thuật toán tìm **cây khung nhỏ nhất — Minimum Spanning Tree, MST** trên **đồ thị vô hướng, có trọng số, liên thông**. Nếu đồ thị có nhiều thành phần liên thông, cùng thuật toán tự nhiên trả về **rừng khung nhỏ nhất — Minimum Spanning Forest, MSF**, gồm một cây khung nhỏ nhất cho mỗi thành phần. Đặc điểm nổi bật của Borůvka là **không phát triển từ một đỉnh duy nhất**: nó giữ **nhiều thành phần rời nhau**, cho mỗi thành phần chọn **cạnh nhẹ nhất đi ra bên ngoài**, rồi **hợp nhất các thành phần bằng DSU/Union-Find**. Cứ sau một vòng, các cụm lớn hơn tiếp tục tìm cạnh nhẹ nhất để nối sang cụm khác.

Thuật toán là một ví dụ rõ ràng về **lựa chọn tham lam an toàn nhờ tính chất lát cắt (cut property)**. Khi mỗi thành phần đã là một cây con của rừng đang xây, cạnh rẻ nhất băng qua lát cắt phân biệt thành phần ấy với phần còn lại là lựa chọn có thể xuất hiện trong một MST. Hợp nhất bằng **Disjoint Set Union (DSU)** giúp tránh thêm cạnh tạo chu trình và truy vấn nhanh hai đầu cạnh có thuộc cùng thành phần hay không.

Bài học thuộc nhóm **Cây khung** của Computer Science Algorithms, tập trung vào ý nghĩa “hợp nhất theo thành phần”, cách hoạt động theo vòng, điều kiện an toàn, độ phức tạp, đồ thị rời rạc, cạnh âm/bằng nhau/song song/khuyên, so sánh với Kruskal và Prim, và chương trình **Java 17+** chạy độc lập có đối chiếu với Kruskal trên **300 đồ thị kiểm thử**.

## 1. Phát biểu và phân biệt cây khung với rừng khung

Cho đồ thị vô hướng `G=(V,E,w)`; mỗi cạnh `e={u,v}` nối hai đỉnh và có trọng số `w(e)`. Trọng số có thể dương, bằng 0 hoặc âm, trừ khi đề quy định khác.

**Cây khung** của một đồ thị liên thông là tập cạnh thỏa:

1. Chứa **tất cả đỉnh** của đồ thị (kể cả các đỉnh chỉ có một cạnh).
2. **Liên thông**: có đường giữa mọi cặp đỉnh.
3. **Không có chu trình**.
4. Với V đỉnh và V≥1, nó có đúng **V−1 cạnh**.

**Cây khung nhỏ nhất (MST)** là cây khung có tổng trọng số `Σ w(e)` nhỏ nhất. “Nhỏ nhất” ở đây là **tổng trọng số cạnh**, không phải số đỉnh hay số cạnh: mọi cây khung của cùng một đồ thị liên thông đều có V−1 cạnh.

Nếu đồ thị có **k thành phần liên thông**, sẽ không có **một cây** nối mọi đỉnh mà chỉ dùng cạnh có sẵn. Khi đó ta tìm **rừng khung nhỏ nhất (MSF)**: mỗi thành phần liên thông của đồ thị gốc nhận một cây khung nhỏ nhất. Với n đỉnh và k thành phần liên thông ban đầu, rừng gồm đúng `n−k` cạnh.

**Quy ước biên:**

- Đồ thị **một đỉnh, không cạnh** có MST tầm thường, tổng trọng số 0.
- Đồ thị **không có đỉnh (n=0)** trả rừng rỗng tổng trọng số 0; chương trình không gọi đó là “một cây” theo quy ước báo cáo.
- **Đỉnh cô lập** là thành phần gồm một đỉnh và không cần cạnh nào để tạo cây khung của thành phần ấy.
- **Khuyên tự nối** `u−u` không thể giúp nối hai thành phần khác nhau, và đưa nó vào rừng sẽ tạo chu trình, nên bỏ qua dù trọng số âm.
- **Cạnh song song** giữa cùng cặp đỉnh được phép: mỗi cạnh có ID riêng và thuật toán có thể chọn cạnh rẻ hơn.
- Thuật toán này dành cho **vô hướng**. Một đồ thị có hướng cần khái niệm khác như cây có hướng gốc (arborescence) và thuật toán thích hợp, không áp dụng Borůvka nguyên xi.

### Đừng nhầm MST với shortest path

Cây khung nhỏ nhất tối thiểu hóa **tổng trọng số của tất cả cạnh trong cây**, không tối thiểu hóa khoảng cách từ một nguồn đến từng đỉnh. Một đường đi giữa hai đỉnh trong MST **không nhất thiết là đường đi ngắn nhất** của đồ thị gốc. Nếu bài hỏi đường đi ngắn nhất, dùng thuật toán như BFS, Dijkstra hoặc thuật toán khác theo trọng số; nếu hỏi **kết nối tất cả đỉnh với chi phí tổng nhỏ nhất**, cân nhắc MST.

## 2. Tư tưởng chính: mỗi thành phần chọn cạnh đi ra nhẹ nhất

Ban đầu, chưa chọn cạnh nào; mỗi đỉnh là một **thành phần riêng**. Đó là một rừng gồm n cây một đỉnh. Một vòng Borůvka làm bốn việc:

1. **Xác định thành phần hiện tại:** mỗi đỉnh thuộc một cụm được biểu diễn bằng một **gốc DSU**.
2. **Quét toàn bộ cạnh:** với cạnh `e=(u,v,w)`, tìm `ru=find(u)` và `rv=find(v)`. Nếu `ru==rv`, cạnh nằm bên trong cùng cụm và không giúp nối cụm, bỏ qua. Nếu khác nhau, xét e làm ứng viên **nhẹ nhất đi ra** cho **cả hai** cụm ru và rv.
3. **Thu thập các ứng viên của vòng:** mỗi cụm có tối đa một cạnh rẻ nhất băng sang cụm khác. Một cạnh có thể được hai cụm chọn cùng lúc, nên **loại trùng theo ID cạnh**.
4. **Hợp nhất:** lần lượt thử `union(u,v)` đối với các cạnh ứng viên. Nếu hai đầu đang ở hai cụm khác nhau, thêm cạnh vào rừng, cộng trọng số và hợp nhất. Nếu chúng đã cùng cụm vì các cạnh trước đó của **cùng vòng** đã hợp nhất chúng, không thêm nữa để tránh chu trình.

Sau vòng đó, các cụm đã hợp nhất thành những cây lớn hơn. Ta **làm mới danh sách cạnh rẻ nhất**, quét lại cạnh cho những cụm mới và tiếp tục.

Thuật toán dừng khi **không có hợp nhất nào** trong một vòng. Nếu ban đầu liên thông và chỉ còn một cụm, có thể dừng ngay với MST. Nếu đồ thị rời rạc, khi mỗi cụm cuối cùng chính là một thành phần liên thông gốc và không có cạnh nối giữa các cụm, thuật toán dừng với MSF.

### Vẽ theo cụm

~~~text
Ban đầu, 6 đỉnh:
{0}  {1}  {2}       {3}  {4}  {5}

Các cạnh nội bộ của hai nhóm có trọng số nhỏ:
{0}--1--{1}--1--{2}       {3}--1--{4}--1--{5}
                 \                         /
                   --10---- nối hai nhóm

Vòng 1 chọn các cạnh nội bộ rẻ:
{0,1,2}                 {3,4,5}

Vòng 2 chọn cạnh nối hai cụm:
{0,1,2,3,4,5}
~~~

Đặc điểm cần nhớ: Borůvka chọn **một cạnh cho từng thành phần**, không phải chọn **một cạnh rẻ nhất toàn đồ thị** trong mỗi vòng. Rất nhiều cạnh có thể được thêm trong **cùng một vòng**, miễn tất cả được kiểm tra bằng DSU để giữ tính không chu trình.

## 3. DSU / Union-Find: công cụ hợp nhất theo thành phần

**Disjoint Set Union** duy trì một tập hợp các nhóm đỉnh **không giao nhau**. Nó hỗ trợ hai phép cơ bản:

- `find(x)`: trả về ID **đại diện (root)** của nhóm chứa x.
- `union(x,y)`: nếu x và y thuộc **hai nhóm khác nhau**, gộp chúng và trả `true`; nếu đã cùng nhóm, **không gộp**, trả `false`.

Ví dụ:

~~~text
Khởi đầu:
0 | 1 | 2 | 3 | 4 | 5

union(0,1):
{0,1} | 2 | 3 | 4 | 5

union(1,2):
{0,1,2} | 3 | 4 | 5

find(0)==find(2)   -> true
find(0)==find(3)   -> false
~~~

Trong Borůvka, **một thành phần DSU chính là một cây** của rừng đang được xây. Khi `union(u,v)` thành công, cạnh (u,v) nối **hai cây khác nhau**, do đó thêm cạnh ấy **không thể tạo chu trình**. Sau đó hai cây trở thành một cây lớn hơn.

### Cấu trúc triển khai nhanh

DSU thường có:

- `parent[x]`: cha trong cấu trúc đại diện.
- `size[root]`: số đỉnh của nhóm có gốc root.
- `components`: số nhóm còn lại, giảm một mỗi lần union thành công.

**Path compression (nén đường đi):** khi gọi `find(x)`, cập nhật các cha trên đường tới gốc để những truy vấn sau nhanh hơn.

**Union by size (hợp theo kích thước):** luôn gắn gốc của nhóm nhỏ vào gốc của nhóm lớn. Nếu bằng kích thước, có thể chọn gốc ID nhỏ hơn để đầu ra và việc xử lý dễ tái lập.

Khi kết hợp hai kỹ thuật, mỗi thao tác DSU có thời gian **O(α(V)) amortized**, với α là **hàm Ackermann ngược** tăng cực chậm; trong thực tế thường gần hằng số.

**Đừng nhầm ID gốc với đỉnh quan trọng của đồ thị.** Gốc DSU chỉ là nhãn đại diện tạm thời. Sau union, gốc của một cụm có thể đổi; thuật toán không được xem một gốc cũ như danh tính vĩnh viễn của thành phần.

## 4. Cách chọn cạnh nhẹ nhất cho từng cụm

Cho danh sách cạnh `edges`. Trong mỗi vòng, tạo mảng `cheapest[root]`, ban đầu null. Quét từng cạnh:

~~~text
a = find(edge.u)
b = find(edge.v)

if a == b:
    skip                 // Cạnh nội bộ không nối cụm.

if edge is better than cheapest[a]:
    cheapest[a] = edge

if edge is better than cheapest[b]:
    cheapest[b] = edge
~~~

Điều này đồng thời kiểm tra cạnh theo cả **hai phía của lát cắt**. Một cạnh nối cụm A và cụm B là ứng viên rời A lẫn ứng viên rời B. Nếu chỉ cập nhật một phía, có thể bỏ lỡ cạnh rẻ nhất cho phía còn lại.

### Quy tắc hòa trọng số

Nếu hai cạnh đi ra một cụm có cùng trọng số, chọn **ID cạnh nhỏ hơn**. Định nghĩa khóa so sánh:

`key(edge) = (weight, edgeId)`

So sánh **theo từ điển tăng**: nhẹ hơn trước; nếu bằng trọng số, ID nhỏ hơn trước. Mỗi cạnh đầu vào có ID duy nhất nên quy tắc này tạo thứ tự toàn phần xác định.

**Vì sao cần quy tắc?** MST có thể không duy nhất khi trọng số bằng nhau. Cùng một đầu vào nhưng thứ tự duyệt hoặc cách xử lý tie khác nhau vẫn có thể trả **những cây khác nhau với tổng trọng số như nhau**. Quy tắc `(weight,edgeId)` giúp chương trình cho đầu ra nhất quán và hỗ trợ lập luận về một thứ tự trọng số phân biệt.

**Không được** lấy ID cạnh làm tiêu chí chính rồi chỉ xét trọng số phụ. Một cạnh ID nhỏ nhưng nặng hơn không phải cạnh nhẹ nhất qua lát cắt.

### Vì sao thu thập ứng viên trước khi union?

Trong một vòng, `cheapest` phải được tính theo **ảnh chụp thành phần tại đầu vòng**. Nếu vừa quét cạnh vừa union ngay, thành phần đổi giữa lúc quét; một vài cụm đã dùng quy tắc “nhẹ nhất” theo trạng thái cũ, vài cụm theo trạng thái mới, dễ mất ý nghĩa của một vòng Borůvka.

Cách rõ ràng:

1. Quét hết danh sách cạnh để tính `cheapest`.
2. Lấy các ứng viên cho **từng root trước hợp nhất**; loại cạnh trùng ID.
3. Sau đó mới duyệt danh sách ứng viên và gọi `union`.

Dù đã loại cạnh trùng ID, vẫn phải kiểm tra `union` trước khi thêm vào đáp án: **nhiều cạnh ứng viên khác nhau** có thể kết nối thành một chu trình nếu không kiểm tra lại thành phần sau những lần union trước. Với quy tắc tổng thứ tự (weight,ID) nhất quán, các ứng viên nhẹ nhất có cấu trúc đặc biệt an toàn, nhưng kiểm tra DSU vẫn là rào chắn chính xác và đơn giản trong triển khai.

## 5. Ví dụ chi tiết: hai vòng hợp nhất và đỉnh cô lập

Xét đồ thị **7 đỉnh (0..6)**, gồm hai tam giác nối bằng một cạnh nặng hơn, một cạnh song song và một khuyên:

| ID cạnh | Hai đầu | Trọng số | Vai trò |
| ---: | --- | ---: | --- |
| 0 | 0–1 | 1 | Cạnh rẻ trong nhóm trái |
| 1 | 1–2 | 1 | Cạnh rẻ trong nhóm trái |
| 2 | 0–2 | 3 | Cạnh thứ ba của tam giác trái |
| 3 | 3–4 | 1 | Cạnh rẻ trong nhóm phải |
| 4 | 4–5 | 1 | Cạnh rẻ trong nhóm phải |
| 5 | 3–5 | 3 | Cạnh thứ ba của tam giác phải |
| 6 | 2–3 | 10 | Cạnh nối hai nhóm |
| 7 | 0–1 | 2 | Song song với ID 0, đắt hơn |
| 8 | 5–5 | -100 | Khuyên, không được chọn |

**Đỉnh 6 không có cạnh**, nên đồ thị rời rạc: không tồn tại một MST phủ cả 7 đỉnh; kết quả đúng là **MSF**.

### Vòng 1: từ 7 thành phần còn 3

Ban đầu `components=7` và mỗi đỉnh là một root.

- Cụm {0} thấy cạnh ID 0 trọng số 1 là tốt nhất; cụm {1} cũng có thể chọn ID 0.
- Cụm {2} chọn ID 1 trọng số 1.
- Cụm {3} và {4} chọn ID 3; cụm {5} chọn ID 4.
- Cụm {6} không có cạnh đi ra.
- Cạnh ID 8 là khuyên, hai đầu đã thuộc cùng cụm ngay từ đầu, bỏ qua dù trọng số -100.

Loại trùng các lựa chọn từ hai đầu, ta có các ứng viên theo thứ tự root tăng trong chương trình: `[0,1,3,4]`. Cả bốn đều nối hai thành phần khác nhau, nên được nhận.

~~~text
Sau vòng 1:

Cụm trái: {0,1,2}   -- chọn ID 0,1
Cụm phải: {3,4,5}   -- chọn ID 3,4
Cụm cô lập: {6}

components = 3
totalWeight = 1+1+1+1 = 4
~~~

### Vòng 2: từ 3 thành phần còn 2

Giữa hai cụm lớn có cạnh ID 6 `(2,3,10)`. Cả hai cùng nhận đây là cạnh nhẹ nhất đi ra của mình; sau khử trùng ID chỉ còn một ứng viên. `union(2,3)` thành công:

~~~text
Cụm lớn: {0,1,2,3,4,5}
Cụm cô lập: {6}

components = 2
totalWeight = 4+10 = 14
selectedIds = [0,1,3,4,6]
~~~

### Dừng

Vòng kiểm tra tiếp theo không có cạnh nối hai cụm còn lại vì đỉnh 6 cô lập. Không có union mới, thuật toán dừng. Theo định nghĩa chương trình, **chỉ đếm vòng có ít nhất một lần hợp nhất**, nên kết quả là:

~~~text
weight=14
components=2
rounds=2
afterRounds=[3,2]
selected=[0,1,3,4,6]
~~~

Có đúng `7−2=5` cạnh được nhận. Nếu bỏ đỉnh cô lập 6 và xét đồ thị chỉ gồm 6 đỉnh 0..5 với cùng danh sách cạnh, kết quả là **MST** với `components=1`, `weight=14`, `afterRounds=[2,1]` và vẫn có hai vòng hợp nhất.

**Trọng số -100 của khuyên không được cộng.** MST/MSF chỉ nhận cạnh giúp **nối hai đỉnh thuộc các thành phần khác nhau**, vì khuyên luôn tạo chu trình và không tăng khả năng liên thông.

## 6. Giả mã chuẩn Borůvka

~~~text
ALGORITHM BORUVKA(n, edges)
    REQUIRE graph is undirected
    REQUIRE endpoints in 0..n-1
    REQUIRE each edge has a unique ID

    dsu <- make n singleton sets
    selected <- empty list
    totalWeight <- 0

    REPEAT
        cheapest[0..n-1] <- null

        // A. Tìm cạnh rẻ nhất băng qua từng thành phần.
        FOR EACH edge e=(u,v,w,id) IN edges DO
            a <- dsu.find(u)
            b <- dsu.find(v)
            IF a = b THEN
                CONTINUE
            END IF
            IF cheapest[a] is null OR
               key(e) < key(cheapest[a]) THEN
                cheapest[a] <- e
            END IF
            IF cheapest[b] is null OR
               key(e) < key(cheapest[b]) THEN
                cheapest[b] <- e
            END IF
        END FOR

        // B. Thu thập theo root tại đầu giai đoạn.
        candidates <- empty list
        seenEdgeId[0..E-1] <- false
        FOR vertex FROM 0 TO n-1 DO
            IF dsu.find(vertex) != vertex THEN
                CONTINUE
            END IF
            e <- cheapest[vertex]
            IF e != null AND NOT seenEdgeId[e.id] THEN
                seenEdgeId[e.id] <- true
                APPEND e TO candidates
            END IF
        END FOR

        // C. Union để giữ rừng không có chu trình.
        merged <- 0
        FOR EACH e IN candidates DO
            IF dsu.union(e.u,e.v) THEN
                APPEND e.id TO selected
                totalWeight <- totalWeight + e.weight
                merged <- merged + 1
            END IF
        END FOR

        IF merged = 0 THEN
            BREAK
        END IF

        RECORD dsu.componentCount AS afterRound
    UNTIL dsu.componentCount = 1

    RETURN (selected,totalWeight,dsu.componentCount)
END ALGORITHM
~~~

Lưu ý:

- `cheapest` **phải đặt lại** ở đầu **mỗi vòng**. Sau union, root và miền thành phần đã thay đổi.
- `seenEdgeId` khử **cùng một cạnh** được hai cụm chọn, không loại mọi cạnh song song vì chúng có ID khác nhau.
- `union` chính là bộ lọc không chu trình. Chỉ khi trả true mới **cộng trọng số** và thêm ID vào đáp án.
- Không có yêu cầu **sắp xếp toàn bộ cạnh** trong Borůvka; chỉ quét E cạnh mỗi vòng và giữ ứng viên nhẹ nhất.
- Nếu không có cạnh băng qua cụm còn lại, `merged=0` và thuật toán đã hoàn tất MSF, kể cả khi `componentCount>1`.

## 7. Vì sao thuật toán đúng? Tính chất lát cắt

### Lát cắt và cạnh nhẹ

Một **lát cắt (cut)** của đồ thị chia các đỉnh thành hai tập không rỗng `S` và `V\S`. Một cạnh **băng qua lát cắt** nếu một đầu trong S và đầu kia ngoài S.

**Tính chất lát cắt (cut property):** với một phân hoạch S và phần còn lại, nếu chọn một cạnh có trọng số nhỏ nhất trong các cạnh băng qua lát cắt, cạnh đó **an toàn** để bổ sung vào một rừng cạnh đã được chọn phù hợp với lát cắt. Khi có nhiều cạnh cùng trọng số, có thể lựa chọn nhất quán theo một thứ tự phụ để lập luận rõ ràng.

#### Chứng minh hoán đổi (exchange argument)

Giả sử F là rừng cạnh đã chọn và có một MST T chứa F. Xét thành phần S của F. Vì S là thành phần của F, **không có cạnh của F băng qua lát cắt (S,V\S)**.

Lấy e là **cạnh nhẹ nhất** nối từ S sang ngoài S. Nếu T đã chứa e, không cần thay đổi gì. Nếu T không chứa e, thêm e vào T sẽ tạo **một chu trình**. Chu trình ấy phải có một cạnh f khác băng qua cùng lát cắt S vì e vừa đi từ trong S ra ngoài và để quay lại chu trình phải qua lát cắt lần nữa. Cạnh f không thuộc F, vì F không có cạnh vượt lát cắt. Do e là cạnh nhẹ nhất, `w(e)<=w(f)`. Bỏ f, giữ e được một cây khung có trọng số không lớn hơn T, nên vẫn tối ưu và vẫn chứa F cùng e.

Lập luận cho thấy chọn e là an toàn. Để chọn nhiều cạnh cùng vòng và tránh vấn đề hòa trọng số, chương trình dùng **khóa duy nhất `(weight,id)`**. Có thể xem đây là thứ tự ưu tiên phụ rất nhỏ, không thay đổi mục tiêu tổng trọng số chính: với mỗi lát cắt, cạnh nhẹ nhất theo khóa là **duy nhất**. Theo tính chất lát cắt, nó thuộc cây khung nhỏ nhất xác định bởi thứ tự khóa ấy. Mọi cạnh được các thành phần chọn trong vòng đều tương thích với cùng một cây/rừng tối ưu theo khóa; DSU vẫn kiểm tra để không bao giờ thêm chu trình.

**Không nhầm:** nếu dùng cách phá hòa khác nhưng vẫn luôn chọn cạnh có trọng số nhỏ nhất qua lát cắt, một cây khung có **tổng trọng số tối ưu** vẫn có thể được tìm. ID chỉ làm cho lựa chọn xác định, không biến ID thành trọng số của bài toán.

### Bất biến của rừng đang xây

Sau mỗi lần union thành công:

1. Các cạnh đã chọn tạo thành **rừng**, không có chu trình.
2. Mỗi cây của rừng là **một thành phần DSU**.
3. Rừng đã chọn có thể được mở rộng thành một MSF tối ưu của đồ thị gốc.

**Cơ sở:** rừng rỗng gồm n đỉnh, chưa có chu trình và là tập con của một MSF.

**Duy trì:** các ứng viên được chọn từ cạnh nhẹ nhất băng qua lát cắt của từng thành phần đầu vòng. Theo tính chất lát cắt và quy tắc phá hòa nhất quán, các lựa chọn an toàn cho rừng tối ưu; `union` chỉ nhận cạnh nối hai thành phần khác nhau. Vì thế rừng mới vẫn không có chu trình và còn có thể mở rộng thành một MSF tối ưu.

**Kết thúc:** nếu không có cạnh nối hai thành phần DSU khác nhau, mỗi thành phần DSU đã là một **thành phần liên thông của đồ thị gốc**. Rừng đang xây đã nối mọi đỉnh **trong** từng thành phần ấy. Vì rừng là tập con của một MSF tối ưu và đã chứa đủ `n−k` cạnh để phủ k thành phần, nó **chính là MSF tối ưu**.

### Vì sao có thể chọn nhiều cạnh trong một vòng?

Có thể nhìn Borůvka như chạy đồng thời nhiều phép chọn cạnh an toàn trên **các lát cắt thành phần**. Thứ tự thứ cấp theo ID loại mơ hồ ở trường hợp bằng trọng số; `union` kiểm tra lần cuối rằng một cạnh không làm phát sinh chu trình. Đây là khác biệt quan trọng với “cứ cộng tất cả cạnh rẻ nhất được các đỉnh đề xuất”: cách cộng thẳng không dùng DSU có thể đếm một cạnh nhiều lần hoặc tạo chu trình trong những cách xử lý hòa thiếu nhất quán.

## 8. Vì sao số vòng tăng rất chậm?

Xét một thành phần liên thông ban đầu có k đỉnh, k≥2. Đầu một vòng, mỗi thành phần DSU **chưa phải cả thành phần liên thông gốc** đều có ít nhất **một cạnh đi ra** tới một thành phần DSU khác; Borůvka chọn một cạnh như thế.

Xét đồ thị tạm trong vòng với mỗi thành phần DSU là một “siêu đỉnh” và mỗi cạnh ứng viên là một cạnh nối hai siêu đỉnh. Mọi siêu đỉnh còn cần hợp nhất đều tham gia ít nhất một cạnh ứng viên. Sau các phép union, mỗi thành phần mới chứa ít nhất **hai siêu đỉnh cũ**. Vì vậy số cụm còn hoạt động trong thành phần liên thông gốc giảm **ít nhất một nửa** sau mỗi vòng chưa hoàn thành.

~~~text
k cụm -> nhiều nhất ceil(k/2)
      -> nhiều nhất ceil(k/4)
      -> ...
      -> 1 cụm
~~~

Suy ra cần **O(log V) vòng hợp nhất**. Đây là lý do Borůvka có ít vòng dù một vòng có thể thêm nhiều cạnh.

**Chú ý đồ thị không liên thông:** các thành phần gốc khác nhau và đỉnh cô lập **không thể hợp nhất với nhau**. Không đúng nếu khẳng định “tổng số component của toàn đồ thị luôn giảm một nửa mỗi vòng” khi có nhiều đỉnh cô lập. Lập luận chia đôi đúng **bên trong từng thành phần liên thông gốc còn chưa được nối xong**, và tổng số vòng vẫn bị chặn O(log V) nhờ xét thành phần lớn nhất.

## 9. Độ phức tạp và tài nguyên

Gọi `V=n` là số đỉnh, `E=m` là số cạnh.

**Trong một vòng:**

- Khởi tạo `cheapest` độ dài V: O(V).
- Quét mọi cạnh và gọi `find` hai đầu: O(E·α(V)) amortized.
- Lấy ứng viên theo root và loại trùng: O(V·α(V)) cho kiểm tra gốc cộng O(E) để khởi tạo `seenEdgeId`.
- Hợp nhất tối đa O(V) ứng viên bằng DSU: O(V·α(V)).
- Không cần sort cạnh toàn bộ.

**Qua O(log V) vòng:** một chặn chính xác cho cài đặt DSU nén đường đi + union-by-size là

`O((V+E)·α(V)·log V)`

với V≥2 (với V=0 hoặc 1, xem riêng trường hợp biên). Vì α(V) cực nhỏ, trong mô tả thuật toán thường nói **O((V+E) log V)** hoặc **O(E log V)** cho đồ thị liên thông có E≥V−1, khi coi phép DSU gần O(1).

**Bộ nhớ:**

- Cạnh đầu vào: O(E).
- DSU parent/size, mảng cheapest: O(V).
- `seenEdgeId`: O(E).
- Danh sách ứng viên và cạnh nhận: O(V).
- Lịch sử số thành phần theo vòng: O(log V).

Tổng bộ nhớ **O(V+E)**. Chương trình Java dùng `Math.addExact` khi cộng tổng trọng số dạng `long` để phát hiện tràn thay vì âm thầm trả kết quả sai.

**Không phải thuật toán đa thức theo tổng số MST có thể tồn tại:** Borůvka chỉ tìm **một** MST/MSF, không liệt kê mọi cây khung nhỏ nhất. Nếu có nhiều MST cùng trọng số, chúng có thể rất nhiều; tìm một cây bằng tham lam vẫn hiệu quả.

## 10. Java 17+ — Borůvka và đối chiếu Kruskal

Chương trình sau có đủ các phần:

- `Graph`: kiểm tra đỉnh và cạnh, gán **ID theo vị trí trong input**, cho phép cạnh song song, khuyên và trọng số âm.
- `DSU`: `find` nén đường đi; `union` theo kích thước, hòa kích thước chọn gốc ID nhỏ hơn.
- `boruvka`: mỗi vòng tìm cạnh rẻ nhất theo khóa `(weight,id)` của từng root, **lấy ứng viên trước khi union**, loại ID trùng và chỉ cộng cạnh khi union thành công.
- `kruskalReference`: giải độc lập bằng sort cạnh rồi DSU, dùng làm oracle so tổng trọng số và số thành phần.
- `verifyForest`: xác minh ID hợp lệ, không chọn một cạnh hai lần, không chu trình, tổng trọng số đúng, số cạnh `n−components` và kết nối đúng bằng các thành phần liên thông của đồ thị gốc.
- `randomCrossCheck`: tạo **300 đồ thị** nhỏ bằng seed cố định, gồm đồ thị không liên thông, cạnh trùng, khuyên, trọng số bằng nhau, 0 và âm; đối chiếu hai cách.
- `Result`: xuất tổng trọng số, số thành phần, ID cạnh được chọn, lịch sử số cụm sau những vòng có union, và kiểm tra liệu kết quả là một cây hay rừng.

**Tệp:** `BoruvkaComponentsDemo.java`

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class BoruvkaComponentsDemo {
    record Edge(int id, int u, int v, int weight) {}

    static final Comparator<Edge> BY_WEIGHT_ID =
            Comparator.comparingInt(Edge::weight)
                    .thenComparingInt(Edge::id);

    record Result(
            long totalWeight,
            int components,
            List<Integer> selectedIds,
            List<Integer> afterRounds) {

        int rounds() {
            return afterRounds.size();
        }

        boolean isTree(int vertexCount) {
            return vertexCount > 0
                    && components == 1
                    && selectedIds.size() == vertexCount - 1;
        }
    }

    static final class Graph {
        final int n;
        final List<Edge> edges = new ArrayList<>();

        Graph(int n, int[][] tuples) {
            Objects.requireNonNull(tuples, "edges");
            if (n < 0) {
                throw new IllegalArgumentException("Negative n");
            }
            this.n = n;

            for (int id = 0; id < tuples.length; id++) {
                int[] tuple = tuples[id];
                if (tuple == null || tuple.length != 3) {
                    throw new IllegalArgumentException(
                            "Expected {u,v,weight}");
                }
                int u = tuple[0];
                int v = tuple[1];
                int weight = tuple[2];

                if (u < 0 || u >= n || v < 0 || v >= n) {
                    throw new IllegalArgumentException(
                            "Endpoint out of range");
                }
                // Parallel edges, negative weights and loops allowed.
                edges.add(new Edge(id, u, v, weight));
            }
        }
    }

    static final class DSU {
        final int[] parent;
        final int[] size;
        int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;

            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            int root = x;
            while (root != parent[root]) {
                root = parent[root];
            }
            while (x != root) {
                int next = parent[x];
                parent[x] = root;
                x = next;
            }
            return root;
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) {
                return false;
            }
            if (size[a] < size[b]
                    || (size[a] == size[b] && a > b)) {
                int swap = a;
                a = b;
                b = swap;
            }

            parent[b] = a;
            size[a] += size[b];
            components--;
            return true;
        }
    }

    // Một cạnh nhẹ hơn nếu trọng số nhỏ hơn,
    // hoặc trọng số bằng mà ID nhỏ hơn.
    private static Edge pickBetter(Edge old, Edge candidate) {
        if (old == null || BY_WEIGHT_ID.compare(candidate, old) < 0) {
            return candidate;
        }
        return old;
    }

    public static Result boruvka(Graph g) {
        Objects.requireNonNull(g, "graph");
        DSU dsu = new DSU(g.n);
        List<Integer> selected = new ArrayList<>();
        List<Integer> afterRounds = new ArrayList<>();
        long totalWeight = 0L;

        while (true) {
            Edge[] cheapest = new Edge[g.n];

            // A. Chọn cạnh nhẹ nhất đi ra mỗi component.
            for (Edge e : g.edges) {
                int a = dsu.find(e.u());
                int b = dsu.find(e.v());

                if (a == b) {
                    continue; // Internal edge or self-loop.
                }
                cheapest[a] = pickBetter(cheapest[a], e);
                cheapest[b] = pickBetter(cheapest[b], e);
            }

            // B. Chụp các ứng viên của cả vòng TRƯỚC union.
            boolean[] seenId = new boolean[g.edges.size()];
            List<Edge> candidates = new ArrayList<>();

            for (int v = 0; v < g.n; v++) {
                if (dsu.find(v) != v) {
                    continue; // Only current roots.
                }
                Edge e = cheapest[v];
                if (e != null && !seenId[e.id()]) {
                    seenId[e.id()] = true;
                    candidates.add(e);
                }
            }

            // C. Hợp nhất, bảo đảm rừng không có chu trình.
            int merged = 0;
            for (Edge e : candidates) {
                if (dsu.union(e.u(), e.v())) {
                    selected.add(e.id());
                    totalWeight = Math.addExact(
                            totalWeight, (long) e.weight());
                    merged++;
                }
            }

            if (merged == 0) {
                break;
            }

            afterRounds.add(dsu.components);
            if (dsu.components == 1) {
                break;
            }
        }

        return new Result(totalWeight, dsu.components,
                List.copyOf(selected),
                List.copyOf(afterRounds));
    }

    // Oracle: Kruskal trên cùng đồ thị, sắp cạnh theo weight/ID.
    public static Result kruskalReference(Graph g) {
        DSU dsu = new DSU(g.n);
        List<Edge> sorted = new ArrayList<>(g.edges);
        sorted.sort(BY_WEIGHT_ID);

        List<Integer> chosen = new ArrayList<>();
        long weight = 0L;

        for (Edge e : sorted) {
            if (dsu.union(e.u(), e.v())) {
                chosen.add(e.id());
                weight = Math.addExact(weight, (long) e.weight());
            }
        }

        return new Result(weight, dsu.components,
                List.copyOf(chosen), List.of());
    }

    // Test oracle: rừng được chọn phải không chu trình,
    // đủ liên thông trong từng thành phần gốc,
    // không chứa cạnh trùng ID và có trọng số khớp.
    private static void verifyForest(Graph g, Result r) {
        boolean[] selected = new boolean[g.edges.size()];
        DSU forest = new DSU(g.n);
        long total = 0L;

        for (int id : r.selectedIds()) {
            if (id < 0 || id >= g.edges.size() || selected[id]) {
                throw new AssertionError("Invalid/duplicate edge ID");
            }
            selected[id] = true;
            Edge e = g.edges.get(id);

            if (!forest.union(e.u(), e.v())) {
                throw new AssertionError("Cycle/self-loop selected");
            }
            total = Math.addExact(total, (long) e.weight());
        }

        if (total != r.totalWeight()
                || forest.components != r.components()
                || r.selectedIds().size() != g.n - r.components()) {
            throw new AssertionError("Invalid forest size/weight");
        }

        DSU original = new DSU(g.n);
        for (Edge e : g.edges) {
            original.union(e.u(), e.v());
        }

        if (original.components != r.components()) {
            throw new AssertionError("Original components mismatch");
        }

        for (int u = 0; u < g.n; u++) {
            for (int v = u + 1; v < g.n; v++) {
                boolean originallyConnected =
                        original.find(u) == original.find(v);
                boolean connectedByForest =
                        forest.find(u) == forest.find(v);

                if (originallyConnected != connectedByForest) {
                    throw new AssertionError(
                            "Spanning connectivity mismatch");
                }
            }
        }
    }

    private static void show(
            String name, int n, int[][] tuples) {
        Graph g = new Graph(n, tuples);
        Result answer = boruvka(g);
        Result oracle = kruskalReference(g);

        verifyForest(g, answer);
        verifyForest(g, oracle);

        if (answer.totalWeight() != oracle.totalWeight()
                || answer.components() != oracle.components()) {
            throw new AssertionError(name + " not optimal");
        }

        System.out.println(name
                + " weight=" + answer.totalWeight()
                + " components=" + answer.components()
                + " rounds=" + answer.rounds()
                + " selected=" + answer.selectedIds()
                + " after=" + answer.afterRounds()
                + " tree=" + answer.isTree(n));
    }

    private static void randomCrossCheck() {
        Random random = new Random(2026L);

        for (int test = 0; test < 300; test++) {
            int n = random.nextInt(9); // 0..8.
            int m = n == 0 ? 0
                    : random.nextInt(2 * n * n + 1);
            int[][] tuples = new int[m][3];

            for (int i = 0; i < m; i++) {
                tuples[i][0] = random.nextInt(n);
                tuples[i][1] = random.nextInt(n);
                tuples[i][2] = random.nextInt(31) - 15;
            }

            Graph g = new Graph(n, tuples);
            Result b = boruvka(g);
            Result k = kruskalReference(g);

            verifyForest(g, b);
            verifyForest(g, k);

            if (b.totalWeight() != k.totalWeight()
                    || b.components() != k.components()) {
                throw new AssertionError(
                        "Wrong MST/MSF at test " + test);
            }
        }

        System.out.println("randomCrossCheck=PASS (300 graphs)");
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0,1,1}, {1,2,1}, {0,2,3},
            {3,4,1}, {4,5,1}, {3,5,3},
            {2,3,10}, {0,1,2}, {5,5,-100}
        };

        show("main", 7, edges);       // Isolated vertex 6.
        show("connected", 6, edges);  // Same edges, no isolated vertex.

        show("ties", 4, new int[][]{
            {0,1,1}, {1,2,1}, {2,3,1},
            {3,0,1}, {0,2,2}, {1,3,2}
        });

        show("negative", 4, new int[][]{
            {0,1,-5}, {1,2,0}, {2,3,7},
            {0,3,10}, {1,3,1}
        });

        show("parallel", 2, new int[][]{
            {0,1,8}, {0,1,-3}, {0,0,-100}
        });

        show("single", 1, new int[0][3]);
        show("empty", 0, new int[0][3]);
        show("noEdges", 3, new int[0][3]);

        randomCrossCheck();
    }
}
~~~

**Chạy bằng JDK 17 trở lên:**

~~~bash
javac BoruvkaComponentsDemo.java
java BoruvkaComponentsDemo
~~~

**Đầu ra chính xác:**

~~~text
main weight=14 components=2 rounds=2 selected=[0, 1, 3, 4, 6] after=[3, 2] tree=false
connected weight=14 components=1 rounds=2 selected=[0, 1, 3, 4, 6] after=[2, 1] tree=true
ties weight=3 components=1 rounds=1 selected=[0, 1, 2] after=[1] tree=true
negative weight=-4 components=1 rounds=1 selected=[0, 1, 4] after=[1] tree=true
parallel weight=-3 components=1 rounds=1 selected=[1] after=[1] tree=true
single weight=0 components=1 rounds=0 selected=[] after=[] tree=true
empty weight=0 components=0 rounds=0 selected=[] after=[] tree=false
noEdges weight=0 components=3 rounds=0 selected=[] after=[] tree=false
randomCrossCheck=PASS (300 graphs)
~~~

### Cách hiểu kết quả

**main:** có 7 đỉnh nhưng đỉnh 6 cô lập, nên trả **rừng** gồm 2 thành phần và 5 cạnh, tổng trọng số 14. `after=[3,2]` là số cụm **sau từng vòng có hợp nhất**, không gồm vòng kiểm tra cuối cùng không có union.

**connected:** cùng cạnh nhưng n=6; sau hai vòng còn 1 thành phần và đúng 5 cạnh, nên có MST. `tree=true`.

**ties:** chu trình bốn đỉnh có bốn cạnh trọng số 1; thuật toán chọn một bộ 3 cạnh tạo cây tổng 3, với cách phá hòa theo ID chọn `[0,1,2]`. Một bộ ba cạnh khác cũng có thể là MST nếu dùng cách phá hòa khác.

**negative:** cạnh trọng số -5 được nhận, những cạnh còn lại tối ưu tạo tổng -4. Thuật toán không đòi trọng số dương; tính chất lát cắt vẫn đúng với trọng số âm.

**parallel:** hai cạnh nối 0–1 có trọng số 8 và -3, chọn ID 1 trọng số -3. Khuyên trọng số -100 bỏ qua dù còn nhỏ hơn -3 vì nó **không kết nối hai thành phần khác nhau**.

**single:** một đỉnh không có cạnh là cây khung tầm thường, nên `tree=true` theo quy ước chương trình.

**empty:** n=0 có rừng rỗng nhưng không coi đó là “một cây”. **noEdges:** n=3, không cạnh, nên mỗi đỉnh là một thành phần riêng; kết quả là rừng ba cây đơn đỉnh.

**randomCrossCheck:** 300 đồ thị nhỏ có thể trùng ID đầu mút, cạnh song song, trọng số âm hoặc bằng nhau; mã so tổng trọng số Borůvka với **Kruskal** và xác minh rừng được chọn không chu trình, phủ đúng từng thành phần, có `n−k` cạnh. Nếu phát hiện sai, chương trình ném `AssertionError` trước khi in PASS.

**Lưu ý thứ tự ID được in:** `selected` là **thứ tự union thành công theo các ứng viên ở từng vòng**, không phải cam kết đã sắp toàn cục theo trọng số. Bản tham chiếu Kruskal duyệt cạnh theo weight/ID, còn Borůvka không cần sort tất cả cạnh để làm việc.

## 11. Borůvka, Kruskal và Prim khác nhau ở đâu?

| Tính chất | Borůvka | Kruskal | Prim |
| --- | --- | --- | --- |
| Tư tưởng tham lam | Mỗi **thành phần hiện có** chọn cạnh nhẹ nhất đi ra | Xét cạnh theo trọng số tăng, nhận nếu nối hai thành phần | Phát triển một cây từ một đỉnh, chọn cạnh nhẹ nhất ra ngoài cây |
| Trạng thái | Nhiều cây/cụm cùng tăng | Rừng các cây dần hợp nhất | Một cây đang phát triển |
| Công cụ chủ đạo | DSU + quét cạnh từng vòng | Sắp xếp cạnh + DSU | Min-heap hoặc mảng khóa theo đỉnh |
| Có cần sort cạnh toàn bộ? | Không | Có trong bản tiêu chuẩn | Không |
| Phức tạp điển hình | O(E log V), ẩn chi phí DSU | O(E log E) với sort | O(E log V) bằng heap, tùy cấu trúc |
| Đồ thị rời rạc | Tự tạo MSF | Tự tạo MSF | Cần chạy lại từ từng đỉnh chưa bao phủ nếu muốn MSF |
| Khả năng xử lý song song | Chọn cạnh cho nhiều cụm theo vòng | Sort/union có phụ thuộc thứ tự | Một cây tiến dần từ một ranh giới |

**Cùng một mục tiêu:** nếu đồ thị liên thông, cả ba có thể tìm MST; nếu rời rạc, Borůvka và Kruskal tự nhiên tìm MSF. Khi trọng số hòa, tập cạnh trả về có thể khác nhau giữa các cài đặt, nhưng **tổng trọng số tối ưu phải giống nhau**.

### Khi nào Borůvka đáng cân nhắc?

- Khi muốn **gom cụm đồng thời** bằng các cạnh rẻ nhất đi ra từng cụm.
- Khi làm việc với **đồ thị lớn** và xử lý theo nhiều vòng có thể được song song hóa.
- Khi muốn kết hợp **Borůvka vài vòng đầu** để giảm số siêu đỉnh, sau đó chuyển sang Kruskal hoặc Prim trên đồ thị co cụm.
- Khi cần hiểu bản chất **cut property, DSU, lựa chọn cạnh an toàn** và cách một rừng dần trở thành cây.

Không phải lúc nào Borůvka cũng nhanh hơn Kruskal hay Prim trên một máy. Nó **quét lại tất cả cạnh ở nhiều vòng**. Tính thực tế phụ thuộc đồ thị, số vòng, overhead DSU, cấu trúc lưu dữ liệu và khả năng song song hóa.

### Khác biệt với thuật toán đường đi ngắn nhất

Prim và Borůvka đều tìm cách **kết nối toàn bộ đỉnh với chi phí tổng nhỏ nhất**, còn Dijkstra giải đường đi ngắn nhất **từ một nguồn**. Việc hai thuật toán đều “chọn cạnh rẻ” không có nghĩa chúng cho kết quả thay thế nhau.

## 12. Trường hợp khó và biến thể

### 12.1. Đồ thị không liên thông

Nếu có k thành phần liên thông gốc, không có cách hợp nhất qua các thành phần ấy vì không có cạnh. Borůvka dừng khi mọi cụm cuối cùng đã phủ một thành phần gốc. Trả `components=k` và `selectedEdges=n-k`. Không tự ý báo “MST” cho cả đồ thị nếu k>1.

Đối với bài bắt buộc **một mạng kết nối toàn bộ đỉnh**, kết quả k>1 có thể phải báo “không tồn tại cây khung” thay vì in rừng; điều đó tùy hợp đồng đầu ra. Thuật toán vẫn trả MSF để người dùng thấy phần có thể nối.

### 12.2. Trọng số âm hoặc bằng không

MST không yêu cầu trọng số dương. Cạnh âm nối hai thành phần có thể được ưu tiên và làm tổng trọng số âm. Không cần biến đổi tất cả trọng số thành số dương. Cạnh khuyên âm vẫn bị bỏ vì không hữu ích cho cây khung.

### 12.3. Nhiều cạnh bằng trọng số

Với các cạnh bằng nhau, có thể có nhiều MST khác nhau. So sánh `(weight,id)` khiến lựa chọn xác định trong chương trình, nhưng nếu đổi cách đánh ID hoặc input, tập cạnh được chọn có thể đổi. Tổng trọng số tối ưu không được đổi.

Khi kiểm thử hai thuật toán khác nhau, **so tổng trọng số, số thành phần và tính hợp lệ của rừng**, không mặc định danh sách ID cạnh phải y hệt, trừ khi đã chứng minh cả hai dùng cùng quy tắc phá hòa cho đúng cùng thứ tự toàn phần.

### 12.4. Cạnh song song

Mỗi cạnh song song có ID riêng. Mảng `seenId` chỉ loại **cùng ID được hai cụm đề xuất**, không xóa mọi cạnh nối cùng cặp đầu mút. Trong ví dụ `(0,1,8)` và `(0,1,-3)`, phải chọn cạnh -3 nếu nối hai thành phần. Trọng số âm không làm thay đổi tiêu chí hợp nhất.

### 12.5. Khuyên và cạnh nội bộ

Ngay khi `find(u)==find(v)`, bỏ cạnh đó. Điều này gồm cả **khuyên** từ đầu và các cạnh đã nằm trong cùng cụm sau nhiều vòng. Dù chúng có trọng số rất thấp, thêm vào rừng sẽ tạo chu trình hoặc không nối thêm đỉnh nào.

### 12.6. Nhiều vòng và lựa chọn phát sinh chu trình

Trong một vòng, một cạnh có thể là lựa chọn của cả hai cụm; lưu nó **một lần**. Các lựa chọn khác nhau cũng phải được kiểm tra bằng union sau những hợp nhất trước. Không bao giờ tăng bộ đếm cạnh hoặc cộng trọng số trước khi biết union có thành công không.

### 12.7. Cần kết quả có thứ tự hoặc trọng số rất lớn

Chương trình lưu tổng trọng số `long` và dùng `Math.addExact`. Đầu vào mỗi trọng số là `int`. Nếu cần trọng số `long` cho từng cạnh, đổi kiểu record và comparator sang `Long.compare`, đồng thời kiểm soát tràn tổng. Nếu đề cần liệt kê cạnh theo thứ tự tăng toàn cục, **sắp danh sách đầu ra sau khi tính**; việc đó không làm đổi MST nhưng thêm chi phí O(V log V).

### 12.8. Đồ thị rất lớn hoặc phân tán

Borůvka chọn cạnh rẻ nhất **theo từng component**; các cạnh có thể được quét song song để tìm local minimum rồi tổng hợp theo component. Tuy nhiên, hợp nhất phải được **đồng bộ**: các worker không được tùy tiện nhận cạnh khiến cùng một chu trình được cộng nhiều lần. Trong hệ thống phân tán còn cần quản lý ID gốc qua các vòng, đồng bộ trạng thái component và khử trùng cạnh.

Một vài vòng Borůvka đầu có thể giảm mạnh số siêu đỉnh. Sau đó có thể **co cụm đồ thị**: xem mỗi thành phần DSU là một siêu đỉnh, giữ cạnh băng qua với trọng số gốc, rồi giải tiếp bằng thuật toán MST phù hợp. Các cạnh nội bộ phải bị loại.

## 13. Phản ví dụ của những cách làm sai

### Chọn cạnh nhẹ nhất đi ra mỗi **đỉnh** một lần là chưa đủ

Lựa chọn cạnh theo từng đỉnh ở **vòng đầu** có thể tạo ra vài cụm tách biệt. Nếu dừng luôn, chưa có MST. Trong ví dụ hai tam giác nối cạnh 10, vòng đầu chỉ chọn các cạnh 1 tạo hai cụm, phải có **vòng thứ hai** để lấy cạnh 10.

Borůvka khác với “mỗi đỉnh chọn một hàng xóm gần nhất rồi kết thúc”: sau các union, phải tính lại **cạnh rẻ nhất đi ra mỗi cụm đã hợp nhất**.

### Chọn cạnh rẻ nhất mà không kiểm tra DSU gây chu trình

Một tam giác có các cạnh trọng số 1,1,1. Nếu tùy ý chấp nhận cả ba cạnh “rẻ” để nối ba đỉnh, kết quả tạo chu trình và có 3 cạnh thay vì `V−1=2`. Kiểm tra `union` chỉ nhận cạnh nối hai cụm khác nhau, bảo đảm không chu trình.

### Không reset cheapest sau union

Ở vòng 1, cạnh 0–1 có thể là tốt nhất của cụm {0}, nhưng ở vòng 2 khi 0 và 1 đã cùng cụm, nó là **cạnh nội bộ**, không còn là ứng viên nối cụm. Nếu dùng lại `cheapest` cũ, thuật toán có thể dừng sớm, lặp vô ích hoặc bỏ qua cạnh cần thiết. Mỗi vòng phải xây cheapest từ trạng thái DSU **mới nhất**.

### Nhầm tổng MST với tổng cạnh được đề xuất

Một cạnh có thể được **hai component chọn**. Nếu cứ cộng mỗi đề xuất, cạnh ấy bị tính hai lần. Tổng đúng chỉ được cộng ở những lần `union` thành công. Tương tự, nếu union trả false vì hai đầu đã cùng cụm, không cộng nữa.

### Thử thuật toán trên đồ thị có hướng

Borůvka như trình bày dùng cut property của **cây khung vô hướng**. Nếu đề có hướng cạnh, một cung chỉ đi một chiều và bài toán tối ưu cấu trúc phân nhánh có hướng khác về định nghĩa; không thể chỉ bỏ mũi tên hoặc thêm cạnh ngược rồi khẳng định đã giải bài gốc.

## 14. Kiểm thử và cách đánh giá

Các test nên phủ **cả tính tối ưu và tính hợp lệ của rừng**:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Đồ thị liên thông 6 đỉnh, hai tam giác nối cạnh 10 | MST có 5 cạnh, tổng 14, hai vòng hợp nhất. |
| Đồ thị tương tự với đỉnh thứ 7 cô lập | MSF có 2 thành phần, 5 cạnh, tổng 14. |
| Chu trình 4 đỉnh, bốn cạnh trọng số 1 | Chọn 3 cạnh, tổng 3; không nhận cạnh thứ tư tạo chu trình. |
| Có cạnh trọng số âm | Cạnh âm nối hai cụm có thể được nhận, tổng có thể âm. |
| Cạnh song song | Ưu tiên cạnh nhẹ hơn nếu băng qua lát cắt. |
| Khuyên trọng số rất âm | Không bao giờ xuất hiện trong MST/MSF. |
| Một đỉnh, không cạnh | Một cây tầm thường, tổng 0, số vòng 0. |
| Không có đỉnh | Rừng rỗng, số thành phần 0. |
| Vài đỉnh không có cạnh | Rừng gồm các đỉnh đơn lẻ, số vòng 0. |
| Nhiều cạnh cùng trọng số | Tổng tối ưu giữ nguyên, đầu ra có thể phụ thuộc tie-break. |
| Đồ thị rời rạc nhiều cụm | Số cạnh được nhận đúng n−k. |
| 300 đồ thị sinh ngẫu nhiên | Borůvka khớp tổng trọng số và số component của Kruskal. |

**Chỉ so tổng trọng số là chưa đủ để kết luận một kết quả đúng.** Một chương trình có thể chọn cạnh lặp hoặc không nối đủ các đỉnh mà tình cờ tính được cùng tổng. Do đó `verifyForest` còn kiểm tra:

1. Mỗi ID hợp lệ và xuất hiện **không quá một lần**.
2. Mỗi cạnh được chọn nối hai thành phần khác nhau tại thời điểm đưa vào rừng (**không chu trình**).
3. Tổng trọng số tính lại từ cạnh đã chọn khớp kết quả báo cáo.
4. Số cạnh là `n−k` với k là số thành phần cuối.
5. Tính liên thông giữa mọi cặp đỉnh trong rừng được chọn **giống hệt** tính liên thông của đồ thị gốc.

Với đồ thị lớn, kiểm tra mọi cặp đỉnh là O(V²) nên chỉ nên dùng cho **đồ thị nhỏ trong unit test**. Cách kiểm thử độc lập bằng Kruskal cần sắp xếp cạnh, khác trực tiếp với chiến lược chọn theo component của Borůvka, giúp bắt sai sót về cut/union.

## 15. Lỗi thường gặp khi cài đặt

1. **Dùng một cạnh rẻ nhất toàn đồ thị cho mỗi vòng** rồi gọi đó là Borůvka; đúng ra phải tìm cạnh rẻ nhất **của từng component**.
2. **Dùng nhãn component cũ sau union**, dẫn đến truy cập cheapest sai; luôn gọi `find` theo DSU hiện tại.
3. **Không reset `cheapest` ở đầu vòng**, khiến cạnh từng tốt giờ là cạnh nội bộ.
4. **Quên cập nhật cạnh ứng viên cho cả hai root** của một cạnh băng qua.
5. **Không bỏ cạnh nội bộ `find(u)==find(v)`**, tạo chu trình hoặc xét khuyên vô ích.
6. **Không khử ID trùng** khi hai component cùng đề xuất một cạnh.
7. **Cộng trọng số dù union thất bại**, tính một cạnh hai lần.
8. **Không kiểm tra union**, có thể chọn chu trình.
9. **Hợp nhất ngay khi đang tìm cheapest**, làm pha quét không dựa trên ảnh chụp component đầu vòng.
10. **Dừng khi còn nhiều component mà không kiểm tra có cạnh nối ra ngoài**, bỏ dở một đồ thị liên thông.
11. **Không dừng khi không có hợp nhất**, làm chương trình lặp vô hạn trên đồ thị rời rạc.
12. **Cho rằng MSF là một MST của toàn đồ thị rời rạc**, trong khi không có cây nối toàn bộ đỉnh.
13. **Nhầm số cạnh của MST bằng V**; đúng là V−1 cho V≥1.
14. **Nhầm số cạnh của MSF bằng V−1** dù có k>1; đúng là V−k.
15. **Bỏ đỉnh cô lập khỏi số component**, làm kết quả rừng không đầy đủ.
16. **Từ chối mọi trọng số âm**, dù MST vẫn xử lý được cạnh âm.
17. **Chọn khuyên âm** vì thấy nó có trọng số nhỏ nhất; khuyên không giúp nối cụm.
18. **Gộp cạnh song song thành một cạnh tùy ý**, có thể làm mất cạnh rẻ nhất.
19. **So sánh trọng số bằng phép trừ int** có thể tràn số; dùng `Integer.compare` hoặc comparator an toàn.
20. **Dùng ID làm tiêu chí đầu tiên** khi phá hòa, thay vì trọng số.
21. **Cho rằng mọi MST có cùng tập cạnh**, không đúng khi có cạnh bằng trọng số.
22. **Cho rằng Borůvka luôn cần sắp E cạnh**, trong khi mỗi vòng chỉ cần quét.
23. **Tuyên bố số component toàn đồ thị luôn giảm một nửa** dù có đỉnh cô lập; lập luận chia đôi theo từng thành phần gốc còn hoạt động.
24. **Bỏ qua chi phí DSU, chi phí quét lại E cạnh**, rồi hứa hẹn O(E) cho toàn bộ thuật toán.
25. **Nhầm cây khung nhỏ nhất với đường đi ngắn nhất từ nguồn**.
26. **Áp dụng thẳng cho đồ thị có hướng**, bỏ qua khác biệt về arborescence.
27. **Đánh dấu cạnh đã chọn theo cặp đầu mút** thay vì ID, gây lỗi khi có cạnh song song.
28. **Không giữ thứ tự phá hòa ổn định**, khiến kết quả khó tái lập/debug dù tổng vẫn đúng.
29. **Chỉ kiểm tra tổng trọng số** mà không chứng minh rừng phủ đúng thành phần và không chu trình.
30. **Sử dụng DFS đệ quy không cần thiết cho DSU**, có thể gây stack sâu; phiên bản `find` lặp dễ kiểm soát.

## 16. Bài tập tự luyện có lời giải

**Bài 1.** Borůvka tối ưu đại lượng gì? **Đáp án:** tổng trọng số cạnh của cây khung cho đồ thị liên thông; với đồ thị rời rạc là tổng của các cây khung nhỏ nhất từng thành phần.

**Bài 2.** Ban đầu có n đỉnh và chưa chọn cạnh. Có bao nhiêu component DSU? **Đáp án:** n, mỗi đỉnh là một singleton.

**Bài 3.** Một component C nên chọn cạnh nào? **Đáp án:** cạnh có trọng số nhỏ nhất **băng từ C sang component khác**; hòa trọng số có thể chọn ID nhỏ hơn.

**Bài 4.** Vì sao không chọn cạnh `(u,v)` khi `find(u)==find(v)`? **Đáp án:** nó không nối thêm component và thêm vào rừng sẽ tạo chu trình.

**Bài 5.** Hai component cùng chọn cạnh e. Cộng trọng số e mấy lần? **Đáp án:** một lần khi union hai đầu e thành công; không cộng theo số lần đề xuất.

**Bài 6.** Trong ví dụ 7 đỉnh, các cạnh ID nào được nhận? **Đáp án:** `[0,1,3,4,6]` theo thứ tự chương trình, tổng trọng số 14.

**Bài 7.** Vì sao ví dụ 7 đỉnh chỉ có MSF mà không có MST toàn đồ thị? **Đáp án:** đỉnh 6 cô lập, không có cạnh nối nó với phần còn lại.

**Bài 8.** Với n=7 và k=2 thành phần gốc, MSF có bao nhiêu cạnh? **Đáp án:** `n−k=5`.

**Bài 9.** Nếu cùng ví dụ chỉ có 6 đỉnh 0..5, MST gồm bao nhiêu cạnh và tổng bằng bao nhiêu? **Đáp án:** 5 cạnh, tổng 14.

**Bài 10.** Cạnh cầu nối hai nhóm có trọng số 10 có thể cần chọn dù nhiều cạnh nội bộ chỉ có trọng số 1? **Đáp án:** có. Để nối hai nhóm không có cạnh thay thế rẻ hơn, phải trả chi phí 10.

**Bài 11.** Một cạnh tự nối đỉnh 5 có trọng số -100. Có nên lấy? **Đáp án:** không, vì khuyên không nối hai đỉnh khác nhau và tạo chu trình.

**Bài 12.** Hai cạnh song song nối 0–1 có trọng số 8 và -3. Cạnh nào ưu tiên khi hai đỉnh chưa cùng cụm? **Đáp án:** cạnh trọng số -3.

**Bài 13.** Với chu trình bốn đỉnh, cả bốn cạnh trọng số 1, MST có tổng bằng bao nhiêu? **Đáp án:** 3, dùng đúng 3 cạnh tạo một cây, bỏ một cạnh để không có chu trình.

**Bài 14.** Tại sao `union` nên trả Boolean? **Đáp án:** để biết cạnh mới có thật sự hợp nhất hai cụm hay không; chỉ khi true mới thêm cạnh và cộng trọng số.

**Bài 15.** Nếu có nhiều MST cùng tổng, Borůvka có sai không khi kết quả khác Prim? **Đáp án:** không, nếu cả hai tạo rừng/cây hợp lệ với tổng trọng số tối ưu.

**Bài 16.** Vì sao điều kiện “cạnh nhẹ nhất đi ra một cụm” là an toàn? **Đáp án:** theo cut property; có thể thay cạnh nặng hơn băng qua cùng lát cắt trong một MST mà không tăng tổng.

**Bài 17.** Vì sao phải làm mới `cheapest` sau một vòng? **Đáp án:** cụm đã thay đổi sau union; cạnh cũ có thể trở thành nội bộ hoặc không còn là cạnh đi ra tốt nhất.

**Bài 18.** Trong một thành phần liên thông đang có k supercomponents, sau một vòng Borůvka còn tối đa khoảng bao nhiêu? **Đáp án:** nhiều nhất `ceil(k/2)` nếu k>1 và mỗi supercomponent có một cạnh đi ra được chọn.

**Bài 19.** Cần tối đa bao nhiêu vòng theo cấp bậc độ lớn? **Đáp án:** O(log V) vòng hợp nhất, xét trong từng thành phần liên thông ban đầu còn hoạt động.

**Bài 20.** Độ phức tạp cốt lõi của Borůvka với DSU gần O(1) trên đồ thị liên thông? **Đáp án:** thường viết O(E log V); chi tiết hơn cho DSU là O((V+E)α(V)log V).

**Bài 21.** Kruskal chọn cạnh khác gì Borůvka? **Đáp án:** Kruskal sắp toàn bộ cạnh tăng theo trọng số rồi xét tuần tự; Borůvka mỗi vòng chọn cạnh rẻ nhất **của từng component**.

**Bài 22.** Prim khác Borůvka ở điểm nào? **Đáp án:** Prim phát triển một cây từ nguồn, Borůvka phát triển **nhiều cây đồng thời** rồi hợp nhất.

**Bài 23.** Nếu đề là đồ thị có hướng, có áp dụng Borůvka này trực tiếp không? **Đáp án:** không; cần xác định bài cây có hướng và thuật toán tương ứng.

**Bài 24.** Nếu muốn kiểm tra kết quả ngoài việc so tổng trọng số, còn điều kiện nào? **Đáp án:** ID cạnh hợp lệ không lặp, không chu trình, phủ đúng từng thành phần liên thông và chọn đúng n−k cạnh.

**Bài 25.** Có 5 đỉnh không có bất kỳ cạnh nào, kết quả là gì? **Đáp án:** 5 thành phần singleton, 0 cạnh, tổng trọng số 0, không có MST nối tất cả.

**Bài 26.** Nếu `best edge` của một cụm có trọng số bằng nhau ở hai lựa chọn, có thể chọn cạnh ID thấp hơn không? **Đáp án:** có; đó là quy tắc phá hòa ổn định, vẫn chọn cạnh nhẹ nhất theo trọng số.

## 17. Checklist triển khai Borůvka và hợp nhất thành phần

1. **Đồ thị vô hướng có trọng số?** Nếu có hướng, kiểm tra lại định nghĩa bài toán.
2. **Đề yêu cầu MST hay MSF?** Với đồ thị rời rạc cần báo không có MST toàn cục hoặc trả MSF theo hợp đồng.
3. **Các cạnh có ID duy nhất không?** Cạnh song song không nên bị gộp nhầm.
4. **Mỗi đỉnh khởi tạo thành singleton DSU?** `components=n`.
5. **`find` có nén đường đi và `union` theo size/rank?** Có giảm component khi union thành công?
6. **Đầu mỗi vòng đã reset `cheapest[root]` chưa?**
7. **Mỗi cạnh có kiểm tra cả hai root và bỏ `rootU==rootV` không?**
8. **Ứng viên có được chọn theo trọng số nhỏ nhất, tie-break rõ ràng không?**
9. **Đã thu thập ứng viên theo component cũ trước khi hợp nhất chưa?**
10. **Có khử cùng một ID được hai cụm đề xuất không?**
11. **Mỗi cạnh chỉ được thêm và cộng trọng số nếu `union` trả true?**
12. **Có dừng đúng khi không còn hợp nhất hoặc chỉ còn một component?**
13. **Có phân biệt tổng trọng số tối ưu với shortest path không?**
14. **Có xử lý trọng số âm, cạnh song song, khuyên, đỉnh cô lập và n=0/1 không?**
15. **Có kiểm tra rừng không chu trình, phủ đúng từng component và đủ `n−k` cạnh không?**
16. **Có đối chiếu tổng với Kruskal/Prim trên input nhỏ, nhiều tie và rời rạc không?**
17. **Có báo rõ độ phức tạp O(log V) vòng và O((V+E)α(V)log V) cài đặt DSU không?**
18. **Có cân nhắc giới hạn bộ nhớ O(V+E), tổng trọng số long và tràn số khi dữ liệu lớn không?**

**Ghi nhớ:** Borůvka thực hiện nhiều lựa chọn tham lam **theo component** ở mỗi vòng: quét cạnh, chọn cạnh nhẹ nhất đi ra, kiểm tra bằng DSU, hợp nhất và lặp lại trên những cụm lớn hơn. **Cut property** bảo đảm lựa chọn an toàn; **union-find** bảo đảm không chu trình; **số cụm giảm nhanh** giúp chỉ cần O(log V) vòng. Trên đồ thị liên thông ta nhận MST; trên đồ thị rời rạc ta nhận MSF, không cố nối các đỉnh vốn không có đường đi giữa chúng.
