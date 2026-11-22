# Lựa chọn thuật toán theo mật độ đồ thị và bộ nhớ

Trong bài toán **cây khung nhỏ nhất (Minimum Spanning Tree — MST)**, biết sử dụng Kruskal hoặc Prim chưa đủ: cùng một đồ thị có thể có hàng trăm nghìn đỉnh và rất ít cạnh, hoặc chỉ vài nghìn đỉnh nhưng gần như mọi cặp đỉnh đều có cạnh. Khi đó, **mật độ đồ thị**, **kiểu dữ liệu đầu vào**, **giới hạn bộ nhớ**, **chi phí sắp xếp** và **chi phí quản lý heap** ảnh hưởng trực tiếp tới việc chọn thuật toán.

Ba lựa chọn thực tế cần phân biệt:

- **Kruskal + DSU:** xử lý danh sách cạnh theo trọng số tăng dần. Thường rất phù hợp với **đồ thị thưa** hoặc khi đã có sẵn danh sách cạnh.
- **Prim + adjacency list + priority queue:** phát triển cây từ các đỉnh đã chọn, dùng heap để ưu tiên cạnh nhẹ nối ra ngoài. Phù hợp với đồ thị **thưa đến trung bình**, đặc biệt khi biểu diễn bằng danh sách kề.
- **Prim + adjacency matrix + tìm tuyến tính:** mỗi lần chọn đỉnh có chi phí nối nhỏ nhất bằng cách quét các đỉnh chưa chọn. Có thời gian **O(n²)** và hợp lý khi đồ thị **dày**, n vừa đủ nhỏ để chứa bảng n×n trong RAM.

Bài học cũng làm rõ trường hợp **đồ thị không liên thông**: khi không có một MST bao phủ tất cả đỉnh, các thuật toán có thể trả **rừng khung nhỏ nhất (Minimum Spanning Forest — MSF)**, gồm cây khung nhỏ nhất trên từng thành phần liên thông.

Mục tiêu không phải tìm một thuật toán luôn tốt hơn hai thuật toán còn lại. Mục tiêu là **ước lượng số cạnh, bộ nhớ, cấu trúc dữ liệu và công việc thực tế** để chọn đúng phương án cho giới hạn của đề.

## 1. Nhắc lại MST và MSF

Xét đồ thị **vô hướng**, có n đỉnh và m cạnh. Mỗi cạnh e nối hai đỉnh u,v và có trọng số w(e), có thể âm, 0 hoặc dương.

**Cây khung (spanning tree)** của một đồ thị liên thông là tập n−1 cạnh:

1. Nối được **toàn bộ n đỉnh**.
2. **Không chứa chu trình**.
3. Tổng số cạnh bằng n−1.

**Cây khung nhỏ nhất (MST)** là cây khung có tổng trọng số **nhỏ nhất** trong tất cả cây khung của đồ thị.

Nếu đồ thị **không liên thông**, không tồn tại một cây khung bao phủ toàn bộ n đỉnh. Thay vào đó, ta có thể tìm **MSF**: trong mỗi thành phần liên thông, chọn một cây khung nhỏ nhất. Tổng trọng số MSF là tổng trọng số các cây thành phần.

Gọi c là số thành phần liên thông của toàn bộ đồ thị, kể cả đỉnh cô lập. Một MSF có:

**n−c cạnh**.

Ví dụ, có sáu đỉnh chia thành ba thành phần, thì rừng khung có sáu trừ ba bằng **ba cạnh**.

### Ba điều cần phân biệt

- **MST:** tồn tại cho đồ thị vô hướng liên thông có ít nhất một đỉnh; với n=1, MST là tập cạnh rỗng trọng số 0.
- **MSF:** luôn xác định theo từng thành phần khi n hữu hạn; cho đồ thị rỗng n=0, thường quy ước rừng rỗng trọng số 0.
- **Shortest path tree:** tối ưu khoảng cách từ **một nguồn** tới các đỉnh; không phải MST. Cây đường đi ngắn nhất và cây khung nhỏ nhất có thể khác nhau.

MST **không yêu cầu** các đường từ một đỉnh cố định đến các đỉnh khác là ngắn nhất. Nó chỉ tối thiểu hóa **tổng trọng số của các cạnh trong cây**.

## 2. Đồ thị thưa hay dày: đếm n, m và mật độ

Với **đồ thị vô hướng đơn, không khuyên và không cạnh song song**, số cạnh tối đa là:

**m_max = n(n−1)/2**.

Có thể định nghĩa mật độ:

**density = m / m_max = 2m / [n(n−1)]**,

khi n≥2. Mật độ nằm trong [0,1]:

- **Thưa:** m nhỏ so với n², chẳng hạn m=O(n), hoặc chỉ vài cạnh trên mỗi đỉnh.
- **Dày:** m có cùng bậc n², ví dụ graph đầy đủ hoặc gần đầy đủ.
- **Trung bình:** nằm giữa hai vùng; cần xét cả n, m, kiểu input và tài nguyên.

Không có một ngưỡng density cố định như 0,3 hoặc 0,5 bảo đảm chọn được thuật toán tối ưu trên mọi môi trường.

### Đồ thị có cạnh song song

Nếu graph là **đa đồ thị**, m có thể lớn hơn n(n−1)/2 vì có nhiều cạnh giữa cùng hai đỉnh. Công thức density trên có thể vượt 1, không còn là tỷ lệ cạnh của đồ thị đơn.

Để đánh giá chi phí thuật toán:

- Dùng **m thực tế** khi ước lượng số cạnh phải duyệt hoặc sắp xếp.
- Dùng **số cặp đỉnh có cạnh khác nhau** nếu muốn tính mật độ hình học của graph sau khi gộp cạnh song song.
- Với MST, trong các cạnh song song cùng cặp đỉnh, **chỉ cạnh nhẹ nhất** mới cần để xây một MST; cạnh nặng hơn không hữu ích cho trọng số tối ưu.

**Self-loop** không giúp nối thêm đỉnh nào nên luôn có thể bỏ qua khi tìm MST/MSF, kể cả khuyên có trọng số âm rất nhỏ.

### Hai kịch bản đối lập

**Kịch bản thưa:** n=100.000, m=200.000. Danh sách kề hoặc danh sách cạnh có kích thước cùng bậc n+m. Một ma trận n×n cần **10 tỷ vị trí**, không thực tế với giới hạn RAM phổ biến.

**Kịch bản dày:** n=2.000, graph gần đầy đủ. Số cạnh có thể gần **2 triệu**. Ma trận n×n có 4 triệu vị trí, có thể được cân nhắc nếu RAM cho phép. Prim ma trận có khoảng O(n²) vòng quét, không cần sắp xếp hàng triệu cạnh theo trọng số.

Đây là lý do phải đọc **n, m và giới hạn bộ nhớ** trước khi chọn cách giải.

## 3. Biểu diễn dữ liệu quyết định bộ nhớ nền tảng

Ba biểu diễn phổ biến:

| Biểu diễn | Bộ nhớ chính | Hợp với |
| --- | --- | --- |
| Danh sách cạnh: (u,v,w) | O(m) | Kruskal và input dạng m cạnh |
| Danh sách kề (adjacency list) | O(n+m) | Prim heap và phần lớn graph thưa |
| Ma trận kề (adjacency matrix) | O(n²) | Prim ma trận và graph dày n vừa phải |

### Danh sách cạnh

Mỗi cạnh chỉ cần một bản ghi gồm hai đầu và trọng số. Với Kruskal, ta sắp các bản ghi rồi duyệt theo thứ tự tăng dần.

Nếu graph có cạnh song song, mỗi bản ghi vẫn là một cạnh riêng. Nếu graph có hướng thì **không** được áp dụng MST vô hướng như không có gì khác biệt; bài cây có hướng là bài toán khác.

### Danh sách kề

Mỗi đỉnh lưu các cạnh kề. Đối với một cạnh vô hướng không phải khuyên, thường lưu hai mục kề: u→v và v→u, cùng trọng số và ID cạnh. Tổng mục kề O(m).

Prim heap dễ mở rộng từ đỉnh vừa chọn bằng việc duyệt chính các cạnh kề của nó.

### Ma trận kề

Đặt một bảng **weight[u][v]** cho chi phí nối u−v. Nếu không có cạnh, phải có cách phân biệt **không tồn tại cạnh** với **trọng số hợp lệ**.

Trong code, dùng:

- **boolean[][] hasEdge**: cặp đỉnh có cạnh hay không.
- **long[][] minWeight**: trọng số nhỏ nhất giữa hai đỉnh, nếu có cạnh.

Cách này không nhầm một cạnh trọng số Long.MAX_VALUE với một sentinel báo “không có cạnh”. Đối với MST, các cạnh song song có thể gộp bằng trọng số nhỏ nhất theo cặp.

**Bộ nhớ ma trận luôn O(n²)** dù chỉ có m=5 cạnh. Đây là điểm bất lợi chính trên đồ thị thưa.

## 4. Kruskal: sắp cạnh và nối bằng DSU

**Kruskal** bắt đầu với n thành phần rời nhau và một tập cạnh kết quả rỗng.

1. Sắp toàn bộ m cạnh theo trọng số **tăng dần**.
2. Duyệt cạnh e=(u,v,w) theo thứ tự ấy.
3. Nếu u và v đang thuộc **hai thành phần khác nhau** trong rừng hiện tại, chọn cạnh e và hợp nhất hai thành phần.
4. Nếu u,v đã cùng thành phần, bỏ e vì thêm nó tạo chu trình.
5. Kết thúc sau khi xét đủ cạnh, hoặc đã chọn n−1 cạnh nếu graph được biết là liên thông.

**DSU / Union-Find** hỗ trợ tìm đại diện tập và hợp nhất hai tập gần như hằng thời gian khấu hao: O(α(n)) cho một phép, với path compression và union by size/rank.

Pseudocode:

~~~text
sort edges by weight increasing
make n singleton DSU sets
total = 0
chosen = 0

for (u,v,w) in sorted edges:
    if find(u) != find(v):
        union(u,v)
        total += w
        chosen++

return total, chosen, numberOfComponents
~~~

### Độ phức tạp Kruskal

- Sắp xếp: **O(m log m)**, với m≥2; thường viết O(m log m).
- DSU: **O(m α(n)+n)**.
- Tổng: **O(m log m + m α(n)+n)**.
- Bộ nhớ làm việc: **O(n+m)** nếu tính cả m cạnh; DSU tự nó cần O(n). Nếu sort in-place trên mảng cạnh đã có, phần bổ sung cho sort/DSU có thể nhỏ hơn O(m) nhưng cách bố trí dữ liệu cụ thể vẫn quan trọng.

Đối với graph đơn với m≤n(n−1)/2, ta có log m=O(log n), nên cách nói gọn thường là **O(m log n)** khi có cạnh đủ để m phù hợp.

### Vì sao phù hợp graph thưa?

Khi m=O(n), thời gian sắp m cạnh cỡ O(n log n) và lưu dữ liệu O(n). Không cần tạo một ma trận n×n.

Kruskal đặc biệt hấp dẫn khi đề cho **danh sách cạnh đầu vào** và chỉ cần tổng trọng số MST, danh sách cạnh hoặc các cạnh được chọn.

### Nhược điểm

Nếu graph dày có m≈n², Kruskal thường phải **sắp O(n²) cạnh**: thời gian O(n² log n), đồng thời có áp lực bộ nhớ do nhiều đối tượng cạnh và mảng sort.

Kruskal không phải lúc nào cũng chậm trên graph dày; ví dụ input vốn đã được sắp hoặc graph có cấu trúc đặc biệt có thể thay đổi thực tế. Nhưng đối với graph dày tổng quát, Prim ma trận thường có lợi thế bậc thời gian.

## 5. Prim bằng heap và danh sách kề

**Prim** duy trì một tập đỉnh **đã vào cây**. Ở mỗi bước, chọn cạnh **nhẹ nhất** nối một đỉnh đã vào cây với một đỉnh chưa vào cây.

Đối với graph không liên thông, có thể khởi động Prim lại từ từng đỉnh chưa thăm để tạo **MSF**.

Một cách cài đơn giản dùng **priority queue chứa cạnh ứng viên**:

~~~text
adj = adjacency lists
visited[*] = false
total = 0
components = 0

for root = 1..n:
    if visited[root]:
        continue
    components++
    visited[root] = true
    push all edges (root -> notVisited) into heap

    while heap not empty:
        e = pop minimum-weight edge
        if visited[e.to]:
            continue

        visited[e.to] = true
        total += e.weight
        push all edges (e.to -> notVisited) into heap
~~~

**Cạnh trong heap có thể trở nên lỗi thời**: từ lúc được thêm, đầu đến có thể đã được chọn bằng cạnh khác. Khi pop thấy đầu đến đã visited, ta bỏ ứng viên đó.

### Độ phức tạp của cách lazy edge-heap

Với đồ thị vô hướng có m cạnh, mỗi cạnh thực có thể được đưa vào heap tối đa một lần khi một đầu vừa được chọn và đầu kia chưa chọn (self-loop bị bỏ qua). Có O(m) lần offer/poll.

- Xây danh sách kề: O(n+m).
- Tối đa O(m) phép heap, mỗi phép O(log(m+1)).
- Tổng **O(n+m log(m+1))**.
- Bộ nhớ **O(n+m)**, bao gồm danh sách kề, visited và heap có thể chứa O(m) ứng viên.

Trong graph đơn, m≤O(n²), nên log(m+1)=O(log(n+1)). Vì vậy Prim heap thường được mô tả là **O((n+m) log n)** trên graph đơn khi dùng biến thể phù hợp.

Một biến thể khác dùng **best[v]** và heap chứa khóa của đỉnh, có thể giảm số mục heap ở một số thời điểm nhưng vẫn cần chú ý phần tử lỗi thời khi dùng PriorityQueue Java không hỗ trợ decrease-key trực tiếp.

### Vì sao hợp graph thưa hoặc trung bình?

Khi m gần n, cả dữ liệu adjacency lẫn heap chỉ có số mục cùng bậc n. Prim không phải lập ma trận n×n.

Ngoài ra, thuật toán có thể hiệu quả nếu graph ban đầu đã được lưu bằng adjacency list. Tránh chuyển sang ma trận chỉ để chạy Prim nếu n rất lớn mà m nhỏ.

## 6. Prim bằng ma trận: O(n²) không cần heap

**Prim dense** không dùng priority queue. Nó dùng:

- **used[v]**: đỉnh v đã được đưa vào cây chưa.
- **best[v]**: trọng số cạnh nhẹ nhất hiện biết nối v với một đỉnh đã được chọn trong thành phần hiện tại.
- **parent[v]**: đỉnh nối v vào cây, nếu cần xuất cạnh.
- **hasEdge[u][v]** và **minWeight[u][v]**: dữ liệu ma trận.

Ở mỗi lần chọn đỉnh mới:

1. Quét toàn bộ n đỉnh để tìm v chưa chọn có best nhỏ nhất.
2. Thêm v vào cây; cộng best[v] nếu v không phải gốc thành phần.
3. Quét toàn bộ n đỉnh để cải thiện best của hàng xóm.
4. Lặp đến khi không còn đỉnh có best hữu hạn trong thành phần.
5. Chọn một gốc khác nếu còn đỉnh chưa chọn, để trả MSF.

Pseudocode:

~~~text
for each unvisited root:
    components++
    best[root] = 0
    known[root] = true
    parent[root] = none

    loop:
        u = unvisited vertex with known best smallest
        if no such u:
            break

        visited[u] = true
        if parent[u] exists:
            total += best[u]

        for v = 1..n:
            if not visited[v] and edge(u,v) exists:
                if best[v] unknown or w(u,v) < best[v]:
                    best[v] = w(u,v)
                    known[v] = true
                    parent[v] = u
~~~

### Độ phức tạp

- Nếu input là danh sách cạnh, xây ma trận: O(n²+m) thời gian để cấp phát/khởi tạo và nạp dữ liệu.
- Mỗi đỉnh được chọn tối đa một lần; chọn một đỉnh quét n mục và cập nhật hàng xóm quét n mục.
- Tổng tìm MST/MSF: **O(n²)**.
- Bộ nhớ ma trận: **O(n²)**; các mảng phụ O(n).

**Nếu vẫn giữ nguyên một Edge[] dài m trong RAM rồi tạo ma trận**, peak memory của chương trình minh họa là **O(n²+m)**. Khi input ban đầu đã ở dạng ma trận hoặc có thể nạp từng cạnh trực tiếp vào ma trận, có thể tránh giữ đồng thời cả hai biểu diễn.

### Khi nào đáng dùng?

Nếu m≈n² và n vừa đủ để ma trận nằm trong RAM, Prim ma trận có thời gian **O(n²)** thay vì phải sắp m cạnh bằng Kruskal hoặc xử lý m ứng viên heap.

Nhưng nếu n lớn đến mức ma trận không vừa bộ nhớ, **O(n²) là bất lợi chí mạng**, dù nó có vẻ nhanh hơn về Big-O thời gian trong tình huống graph rất dày.

### Không dùng một sentinel dễ va chạm

Một ma trận dùng Long.MAX_VALUE để biểu thị “không có cạnh” sẽ sai nếu input cho phép cạnh hợp lệ có trọng số đúng bằng Long.MAX_VALUE. Mã Java dùng **boolean hasEdge[][] riêng**, nên phân biệt được hai trường hợp.

## 7. So sánh đầy đủ ba phương án

| Tiêu chí | Kruskal + DSU | Prim heap + adjacency | Prim ma trận |
| --- | --- | --- | --- |
| Dữ liệu tự nhiên | Danh sách cạnh | Danh sách kề | Ma trận |
| Thao tác chính | Sort cạnh rồi union | Heap cạnh nhỏ nhất qua cut | Quét best và hàng ma trận |
| Thời gian điển hình | O(m log m + mα(n)+n) | O(n+m log(m+1)) với lazy edge heap | O(n²+m) nếu dựng ma trận từ list |
| Bộ nhớ graph + cấu trúc chính | O(n+m) | O(n+m) | O(n²), cộng Edge[] nếu còn giữ |
| Graph rất thưa | Rất hợp | Rất hợp | Thường không hợp |
| Graph rất dày, n vừa | Có thể tốn sort | Heap thao tác rất nhiều | Thường nên cân nhắc |
| Graph không liên thông | Trả MSF tự nhiên | Chạy lại từ các gốc | Chạy lại từ các gốc |
| Cạnh âm | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| Self-loop | DSU bỏ qua | Bỏ qua vì đã visited | Bỏ qua khi dựng ma trận |
| Cạnh song song | Xét từng cạnh | Xét từng cạnh | Gộp cạnh nhẹ nhất của mỗi cặp |
| Rủi ro bộ nhớ chính | M cạnh object/sort | Adjacency + heap O(m) | Bảng n×n |
| Muốn xuất danh sách cạnh | Dễ lưu cạnh union thành công | Dễ lưu cạnh được chọn | Dùng parent[v] |

Bảng là hướng dẫn thiết kế, **không phải bảng xếp hạng tuyệt đối**. Nhiều cài đặt và dữ liệu có thể khiến một thuật toán chậm trên graph tưởng phù hợp.

## 8. Chọn theo n và m, không chỉ theo density

Một quy trình thực tế:

1. Đọc **n**, **m**, loại graph, trọng số và giới hạn RAM.
2. Kiểm tra graph có phải **vô hướng** không; nếu là directed MST/arborescence, không dùng ba thuật toán này như cũ.
3. Đánh giá liệu **n² vị trí** có thể được cấp phát an toàn không.
4. Nếu ma trận không khả thi, chỉ cân nhắc **Kruskal** hoặc **Prim heap/danh sách kề**.
5. Nếu graph rất dày và ma trận khả thi, thử **Prim ma trận O(n²)**.
6. Nếu graph thưa, chọn Kruskal khi đã có edge list và việc sort dễ; chọn Prim heap khi đã có adjacency hoặc muốn phát triển từ một gốc.
7. Nếu graph không liên thông, xác định đề muốn **NO MST** hay cho phép **MSF**.
8. Nếu có nhiều bộ dữ liệu, tính cả **chi phí cấp phát và khởi tạo lại**.

### Minh họa bộ nhớ ma trận

Trong Java, một bảng long[n][n] lưu n² giá trị 8 byte; một bảng boolean[n][n] có khoảng n² giá trị boolean. Bỏ qua overhead đối tượng và alignment, tổng dữ liệu thô khoảng **9n² byte**.

| n | n² vị trí | Long + boolean thô, gần đúng |
| ---: | ---: | ---: |
| 1.000 | 1.000.000 | ~9 MB |
| 5.000 | 25.000.000 | ~225 MB |
| 10.000 | 100.000.000 | ~900 MB |
| 100.000 | 10.000.000.000 | ~90 GB |

**Đây chỉ là ước lượng sàn cho mảng dữ liệu**, chưa gồm overhead của hàng ma trận, đối tượng Java, danh sách cạnh input, DSU, heap, JVM và hệ điều hành. Vì vậy tại n=10.000, một ma trận đôi long+boolean đã có thể vượt mức RAM của nhiều bài thi.

Không nên tuyên bố n≤5.000 luôn an toàn: nếu giới hạn bộ nhớ chỉ 128 MB thì ~225 MB dữ liệu thô đã vượt giới hạn.

### Bài toán từ input dạng ma trận

Nếu n=1.500 và đề cung cấp n×n trọng số, Prim ma trận có thể xử lý trực tiếp, không cần tạo m≈n²/2 Edge objects chỉ để sort. Khi input vốn là ma trận, đây là lợi thế cả thời gian chuyển đổi lẫn peak memory.

## 9. Mật độ không phải yếu tố duy nhất

Cần xem thêm:

- **Giới hạn RAM:** ma trận chỉ khả thi nếu n² vị trí vừa bộ nhớ.
- **Định dạng input:** edge list, adjacency list hay matrix.
- **Graph có song song/khuyên:** m có thể rất lớn dù số cặp đỉnh nhỏ.
- **Độ lớn trọng số:** tổng MST có thể vượt int, long; cần cận số học rõ ràng.
- **Kết quả cần xuất:** chỉ tổng trọng số, danh sách cạnh, số thành phần, hoặc xác nhận tồn tại MST.
- **Tình trạng liên thông:** graph thưa m<n−1 chắc chắn không có MST phủ n đỉnh, nhưng vẫn có MSF.
- **Nhiều test case:** cấp phát ma trận cho nhiều bộ dữ liệu có thể tốn thời gian và gây áp lực GC.
- **Hằng số triển khai:** heap chứa nhiều object, boxing, mảng primitive, cách sort, cache locality.
- **Có thể xử lý streaming không:** nếu chỉ đọc từng cạnh một lần, Kruskal cần giữ/sắp tập cạnh hoặc biến thể thuật toán thích hợp; Prim ma trận có thể nạp cạnh vào bảng khi n nhỏ.
- **Trọng số bằng nhau:** nhiều MST hợp lệ; không nên coi danh sách cạnh khác nhau là kết quả sai nếu tổng trọng số bằng nhau và cấu trúc hợp lệ.

### Khi nào còn chọn Borůvka?

**Borůvka** lặp theo pha: mỗi thành phần hiện tại chọn một cạnh rẻ nhất đi ra, hợp nhất các thành phần, lặp cho tới khi không còn cạnh nối thành phần khác. Số thành phần thường giảm đáng kể sau mỗi pha; với DSU và quét cạnh, thời gian tiêu chuẩn **O(m log n)**.

Borůvka hữu ích trong một số thiết kế song song/phân tán và các biến thể kết hợp, nhưng thường không phải lựa chọn đơn giản nhất nếu chỉ cần MST trên một máy với input quen thuộc. Không cần cố dùng Borůvka chỉ vì graph dày; quyết định vẫn dựa trên triển khai và tài nguyên.

## 10. Các ví dụ tính MST/MSF

### Ví dụ A: graph thưa liên thông

~~~text
n=5
(1,2,4) (1,3,2) (2,3,1)
(2,4,5) (3,4,8) (3,5,10) (4,5,2)
~~~

Kruskal theo trọng số tăng dần chọn:

1. (2,3,1).
2. (1,3,2).
3. (4,5,2).
4. (2,4,5) để nối hai thành phần.

Tổng: **1+2+2+5=10**. Có **4 cạnh**, **1 thành phần**, nên tồn tại MST toàn graph.

Prim heap và Prim ma trận có thể chọn cạnh theo thứ tự khác nhưng cùng tổng 10.

### Ví dụ B: graph dày 4 đỉnh

~~~text
(1,2,3) (1,3,1) (1,4,4)
(2,3,2) (2,4,7) (3,4,5)
~~~

Cây tối ưu chọn các cạnh có trọng số **1,2,4**, tổng **7**, có 3 cạnh và 1 thành phần.

Nếu số đỉnh chỉ vài nghìn nhưng graph gần đầy đủ, lựa chọn Prim ma trận rất đáng cân nhắc vì không cần sort tất cả các cạnh.

### Ví dụ C: không liên thông, có trọng số âm, cạnh song song và khuyên

~~~text
n=6
(1,2,-4) (2,3,2) (1,3,3)
(4,5,5) (4,5,1)
(6,6,-9)
~~~

Các thành phần liên thông:

- {1,2,3}: chọn cạnh −4 và 2, tổng −2.
- {4,5}: chọn cạnh nhẹ hơn trong hai cạnh song song, trọng số 1.
- {6}: đỉnh cô lập về mặt nối các đỉnh khác; khuyên (6,6,−9) không được chọn.

MSF có **3 cạnh**, tổng **−1**, gồm **3 thành phần**. Đồ thị **không có MST bao phủ cả 6 đỉnh**, dù có MSF hợp lệ.

Lưu ý: một khuyên trọng số −9 vẫn bị bỏ vì chọn nó không nối thêm đỉnh nào và tạo chu trình ngay.

### Ví dụ D: trường hợp biên

- n=0, m=0: theo quy ước rừng rỗng có tổng 0, 0 cạnh, 0 thành phần.
- n=1, có một khuyên âm: MSF/MST một đỉnh vẫn có 0 cạnh, tổng 0, 1 thành phần.
- n=4, không cạnh: 4 thành phần cô lập, MSF có 0 cạnh, tổng 0.
- n=2, cạnh song song có trọng số 8 và −2, cùng khuyên −100: MST lấy cạnh −2, tổng −2.

## 11. Chứng minh ngắn bằng tính chất cắt

**Tính chất cắt (cut property)** là căn cứ để Kruskal và Prim đều an toàn.

Xét một **cut** phân hoạch đỉnh thành S và V\S. Một cạnh crossing có một đầu thuộc S, đầu kia thuộc V\S.

Một cạnh có trọng số nhỏ nhất băng qua cut là **cạnh an toàn**: tồn tại một MST chứa cạnh đó (khi xét trong bối cảnh rừng đã chọn tương thích). Nếu có nhiều cạnh đồng trọng số thấp nhất, có thể chọn một trong số chúng.

### Kruskal an toàn vì sao?

Ở thời điểm chọn e=(u,v), u và v thuộc hai thành phần DSU khác nhau. Xét cut chia phần liên thông của u trong rừng hiện tại với phần còn lại. Do duyệt cạnh theo trọng số tăng dần, e là một cạnh nhẹ nhất hợp lệ băng qua cut tương ứng. Chọn e không tạo chu trình và có thể được đưa vào một MST.

Nếu u,v đã cùng thành phần, e sẽ tạo chu trình nên bỏ e là hợp lệ.

### Prim an toàn vì sao?

Ở mỗi bước, S là các đỉnh đã vào cây đang xây. Prim chọn cạnh nhẹ nhất từ S tới V\S. Theo cut property, việc thêm cạnh ấy an toàn. Lặp đến khi thành phần được nối hết.

Nếu graph không liên thông, khi không còn cạnh nối ra ngoài S, thành phần hiện tại đã hoàn thành; bắt đầu gốc mới tạo cây cho thành phần tiếp theo.

**Trọng số âm không phá tính chất cắt.** Chứng minh so sánh trọng số, không đòi trọng số không âm. Vì vậy cả Kruskal và Prim đều hỗ trợ cạnh âm.

## 12. Java 17+: cùng một input, chạy ba thuật toán

Chương trình dưới đây triển khai:

1. **Kruskal** với DSU gồm path compression và union by size.
2. **PrimHeap** với adjacency list và PriorityQueue chứa cạnh ứng viên.
3. **PrimDense** với ma trận long[][] + boolean[][] và quét tuyến tính để chọn best.

Input là graph vô hướng, đỉnh đánh số **1..n**. Mỗi cạnh được tạo bằng **new Edge(u,v,weight)**. Cạnh song song hợp lệ, self-loop hợp lệ nhưng không được đưa vào rừng khung. Đồ thị không liên thông trả **MSF** và số thành phần.

Để tổng trọng số không bị tràn, chương trình cộng bằng **BigInteger**, dù mỗi cạnh có trọng số long. Nếu bài có giới hạn tổng nằm trong long, có thể tối ưu bằng long sau khi chứng minh giới hạn đó.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class MstDensityMemoryDemo {

    record Edge(int u, int v, long weight) {}
    record Arc(int to, long weight, int id) {}
    record Candidate(int to, long weight, int id) {}

    record Result(BigInteger totalWeight,
                  int edgesUsed, int components) {}

    static void validate(int n, Edge[] edges) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }
        Objects.requireNonNull(edges, "edges");
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.u() < 1 || e.u() > n
                    || e.v() < 1 || e.v() > n) {
                throw new IllegalArgumentException(
                        "Endpoint must lie in 1..n");
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
            while (parent[x] != x) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
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

    static Result kruskal(int n, Edge[] edges) {
        validate(n, edges);

        Edge[] sorted = edges.clone();
        Arrays.sort(sorted,
                Comparator.comparingLong(Edge::weight)
                        .thenComparingInt(Edge::u)
                        .thenComparingInt(Edge::v));

        DSU dsu = new DSU(n);
        BigInteger total = BigInteger.ZERO;
        int chosen = 0;

        for (Edge e : sorted) {
            if (dsu.union(e.u() - 1, e.v() - 1)) {
                total = total.add(
                        BigInteger.valueOf(e.weight()));
                chosen++;
            }
        }

        return new Result(total, chosen, dsu.components);
    }

    static List<List<Arc>> adjacency(int n, Edge[] edges) {
        List<List<Arc>> adj = new ArrayList<>(n);
        for (int v = 0; v < n; v++) {
            adj.add(new ArrayList<>());
        }

        for (int id = 0; id < edges.length; id++) {
            Edge e = edges[id];
            int u = e.u() - 1;
            int v = e.v() - 1;

            if (u == v) {
                continue; // self-loop cannot enter an MST
            }
            adj.get(u).add(new Arc(v, e.weight(), id));
            adj.get(v).add(new Arc(u, e.weight(), id));
        }
        return adj;
    }

    static void pushFrontier(
            int u, List<List<Arc>> adj, boolean[] visited,
            PriorityQueue<Candidate> pq) {
        for (Arc arc : adj.get(u)) {
            if (!visited[arc.to()]) {
                pq.add(new Candidate(
                        arc.to(), arc.weight(), arc.id()));
            }
        }
    }

    static Result primHeap(int n, Edge[] edges) {
        validate(n, edges);
        List<List<Arc>> adj = adjacency(n, edges);
        boolean[] visited = new boolean[n];

        PriorityQueue<Candidate> pq =
                new PriorityQueue<>(
                    Comparator.comparingLong(Candidate::weight)
                            .thenComparingInt(Candidate::id));

        BigInteger total = BigInteger.ZERO;
        int chosen = 0;
        int components = 0;

        for (int root = 0; root < n; root++) {
            if (visited[root]) {
                continue;
            }

            components++;
            visited[root] = true;
            pushFrontier(root, adj, visited, pq);

            while (!pq.isEmpty()) {
                Candidate c = pq.poll();
                if (visited[c.to()]) {
                    continue; // stale frontier edge
                }

                visited[c.to()] = true;
                chosen++;
                total = total.add(
                        BigInteger.valueOf(c.weight()));
                pushFrontier(c.to(), adj, visited, pq);
            }
        }

        return new Result(total, chosen, components);
    }

    static Result primDense(int n, Edge[] edges) {
        validate(n, edges);

        long[][] minWeight = new long[n][n];
        boolean[][] hasEdge = new boolean[n][n];

        for (Edge e : edges) {
            int u = e.u() - 1;
            int v = e.v() - 1;

            if (u == v) {
                continue;
            }

            if (!hasEdge[u][v]
                    || e.weight() < minWeight[u][v]) {
                hasEdge[u][v] = true;
                hasEdge[v][u] = true;
                minWeight[u][v] = e.weight();
                minWeight[v][u] = e.weight();
            }
        }

        boolean[] visited = new boolean[n];
        boolean[] known = new boolean[n];
        long[] best = new long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        BigInteger total = BigInteger.ZERO;
        int chosen = 0;
        int components = 0;

        for (int root = 0; root < n; root++) {
            if (visited[root]) {
                continue;
            }

            components++;
            known[root] = true;
            best[root] = 0;
            parent[root] = -1;

            while (true) {
                int u = -1;
                for (int v = 0; v < n; v++) {
                    if (visited[v] || !known[v]) {
                        continue;
                    }
                    if (u == -1 || best[v] < best[u]
                            || (best[v] == best[u] && v < u)) {
                        u = v;
                    }
                }

                if (u == -1) {
                    break;
                }

                visited[u] = true;
                if (parent[u] != -1) {
                    chosen++;
                    total = total.add(
                            BigInteger.valueOf(best[u]));
                }

                for (int v = 0; v < n; v++) {
                    if (!visited[v] && hasEdge[u][v]
                            && (!known[v]
                            || minWeight[u][v] < best[v])) {
                        known[v] = true;
                        best[v] = minWeight[u][v];
                        parent[v] = u;
                    }
                }
            }
        }

        return new Result(total, chosen, components);
    }

    static void compare(String name, int n, Edge... edges) {
        Result k = kruskal(n, edges);
        Result h = primHeap(n, edges);
        Result d = primDense(n, edges);

        if (!k.equals(h) || !k.equals(d)) {
            throw new AssertionError("MST algorithms disagree");
        }

        System.out.println(name + ": K=" + k
                + "; PH=" + h + "; PM=" + d);
    }

    public static void main(String[] args) {
        compare("Sparse connected", 5,
                new Edge(1, 2, 4),
                new Edge(1, 3, 2),
                new Edge(2, 3, 1),
                new Edge(2, 4, 5),
                new Edge(3, 4, 8),
                new Edge(3, 5, 10),
                new Edge(4, 5, 2));

        compare("Dense connected", 4,
                new Edge(1, 2, 3),
                new Edge(1, 3, 1),
                new Edge(1, 4, 4),
                new Edge(2, 3, 2),
                new Edge(2, 4, 7),
                new Edge(3, 4, 5));

        compare("Disconnected", 6,
                new Edge(1, 2, -4),
                new Edge(2, 3, 2),
                new Edge(1, 3, 3),
                new Edge(4, 5, 5),
                new Edge(4, 5, 1),
                new Edge(6, 6, -9));

        compare("Parallel and loop", 2,
                new Edge(1, 2, 8),
                new Edge(1, 2, -2),
                new Edge(1, 1, -100));

        compare("Isolated", 4);

        compare("Single vertex", 1,
                new Edge(1, 1, -7));

        compare("Empty", 0);
    }
}
~~~

Lưu thành **MstDensityMemoryDemo.java**, biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 MstDensityMemoryDemo.java
java MstDensityMemoryDemo
~~~

**Đầu ra chính xác:**

~~~text
Sparse connected: K=Result[totalWeight=10, edgesUsed=4, components=1]; PH=Result[totalWeight=10, edgesUsed=4, components=1]; PM=Result[totalWeight=10, edgesUsed=4, components=1]
Dense connected: K=Result[totalWeight=7, edgesUsed=3, components=1]; PH=Result[totalWeight=7, edgesUsed=3, components=1]; PM=Result[totalWeight=7, edgesUsed=3, components=1]
Disconnected: K=Result[totalWeight=-1, edgesUsed=3, components=3]; PH=Result[totalWeight=-1, edgesUsed=3, components=3]; PM=Result[totalWeight=-1, edgesUsed=3, components=3]
Parallel and loop: K=Result[totalWeight=-2, edgesUsed=1, components=1]; PH=Result[totalWeight=-2, edgesUsed=1, components=1]; PM=Result[totalWeight=-2, edgesUsed=1, components=1]
Isolated: K=Result[totalWeight=0, edgesUsed=0, components=4]; PH=Result[totalWeight=0, edgesUsed=0, components=4]; PM=Result[totalWeight=0, edgesUsed=0, components=4]
Single vertex: K=Result[totalWeight=0, edgesUsed=0, components=1]; PH=Result[totalWeight=0, edgesUsed=0, components=1]; PM=Result[totalWeight=0, edgesUsed=0, components=1]
Empty: K=Result[totalWeight=0, edgesUsed=0, components=0]; PH=Result[totalWeight=0, edgesUsed=0, components=0]; PM=Result[totalWeight=0, edgesUsed=0, components=0]
~~~

### Tại sao các cách luôn có cùng tổng?

Kruskal chọn cạnh an toàn theo cut và loại chu trình bằng DSU. Prim chọn cạnh nhẹ nhất băng qua cut của cây hiện tại. Cả hai đều tối ưu trên từng thành phần liên thông nên phải cho **cùng tổng MSF** và **cùng số cạnh n−c**, dù có thể chọn **các cạnh cụ thể khác nhau** khi trọng số bằng nhau.

### Vì sao không dùng PrimDense cho n rất lớn?

Chương trình gọi ba thuật toán để **so sánh trên các ví dụ nhỏ**. Trong bài thực tế, chỉ gọi thuật toán được chọn, tránh cấp phát ma trận n×n khi n vượt ngân sách RAM.

Nếu cần chạy đồng thời cả ba để benchmark, phải tính peak memory của **toàn bộ chương trình**, không chỉ công thức một phương án độc lập.

### Thu hồi danh sách cạnh MST

- Với **Kruskal**, mỗi lần DSU.union thành công, lưu cạnh đang xét.
- Với **PrimHeap**, mỗi Candidate được chấp nhận là một cạnh nối đỉnh mới vào rừng; lưu thêm đầu nguồn hoặc ID để xuất.
- Với **PrimDense**, khi chọn đỉnh u có parent[u] khác −1, lưu cạnh parent[u]→u với trọng số best[u].

Code demo chỉ xuất tổng, số cạnh và số thành phần; đó là đủ cho ví dụ lựa chọn thuật toán theo mật độ và bộ nhớ.

## 13. Tự kiểm tra chọn thuật toán trên các quy mô khác nhau

### Trường hợp 1: n=100.000, m=150.000

Graph rất thưa, thường dữ liệu đầu vào là edge list. Không thể tạo ma trận 100.000×100.000 trong RAM bình thường. Kruskal + DSU hoặc Prim heap + danh sách kề đều phù hợp về bậc tài nguyên.

Nếu chỉ cần tổng MST và input đã là danh sách cạnh, **Kruskal** thường là điểm bắt đầu đơn giản. Nếu đã có adjacency và muốn xử lý từng thành phần từ gốc, **Prim heap** đáng cân nhắc.

### Trường hợp 2: n=2.000, m gần 2.000.000

Graph gần đầy đủ. Dữ liệu ma trận 2.000×2.000 có 4 triệu vị trí; trong ngân sách RAM đủ lớn, **Prim ma trận O(n²)** có thể cạnh tranh tốt hơn phương án phải sort gần 2 triệu cạnh.

Nhưng nếu chỉ có 64 MB RAM mà vẫn giữ Edge objects input và hai ma trận, cần tính kỹ. Ma trận không tự động rẻ hơn mọi cách biểu diễn.

### Trường hợp 3: n=100.000, m=0

Graph có 100.000 thành phần cô lập, MSF gồm 0 cạnh tổng trọng số 0. Không có MST bao phủ mọi đỉnh.

Kruskal chỉ khởi tạo DSU O(n), Prim heap chỉ duyệt các gốc O(n). Prim ma trận sẽ cấp phát O(n²) ô vô ích.

### Trường hợp 4: n=5.000, m=5.000.000 nhưng có rất nhiều cạnh song song

Số m lớn chưa chắc tương đương graph dày theo **số cặp đỉnh khác nhau**. Nếu các cạnh chủ yếu tập trung vào một vài cặp:

- Có thể **gộp mỗi cặp** về cạnh nhẹ nhất trước MST.
- Số cạnh hiệu dụng giảm nhiều, giúp Kruskal và Prim heap nhẹ hơn.
- Nếu n vẫn lớn, ma trận n² có thể còn nặng hơn việc giữ tập cạnh đã khử trùng.

Mỗi bước gộp cần tính chi phí bộ nhớ và thời gian của cấu trúc map/sort; không áp dụng nếu đề yêu cầu phân biệt ID cạnh trong một nhiệm vụ khác.

## 14. Cách kiểm tra đúng: MSF và đồ thị không liên thông

Đừng chỉ so tổng trọng số của hai phương pháp mà quên điều kiện **spanning**.

Với n đỉnh và c thành phần liên thông:

- Một rừng khung phải **không có chu trình**.
- Nó phải có **n−c cạnh**.
- Trong mỗi thành phần gốc, các đỉnh phải được nối bởi cây tương ứng.
- Tổng trọng số phải nhỏ nhất trong mọi rừng khung thỏa các điều kiện trên.

Trong code, Result trả **components**:

- Nếu n≥1 và components=1: MSF cũng là MST của toàn graph.
- Nếu components>1: có MSF nhưng **không có một MST phủ tất cả các đỉnh**.
- Nếu n=0: không có đỉnh, convention rừng rỗng, không gọi đó là cây khung n−1 cạnh.

Một lỗi phổ biến là **chọn n−1 cạnh bằng Kruskal rồi mặc định graph liên thông**. Khi graph không liên thông, thuật toán chỉ có thể chọn n−c cạnh, nhỏ hơn n−1 nếu c>1.

### Trọng số âm và khuyên âm

Một self-loop có trọng số −100 không được đưa vào MST: nó không nối hai thành phần, và bản thân là một chu trình. Cây khung có định nghĩa **không chu trình**, nên “cứ thấy cạnh âm thì chọn” là sai.

Ngược lại, một cạnh âm nối hai thành phần khác nhau có thể được chọn hoàn toàn hợp lệ. Kruskal và Prim không cần giả định trọng số không âm.

## 15. Bộ nhớ Java: Big-O và chi phí thật

Big-O ghi O(n+m) hoặc O(n²) nhưng trên Java còn nhiều thành phần:

- **Edge record** là object, có overhead, pointer mảng và alignment.
- **ArrayList** có mảng lưu tham chiếu, thường có phần dung lượng dư.
- **PriorityQueue** lưu các tham chiếu tới Candidate; một graph dày có thể tạo nhiều Candidate objects.
- **long[][]** và **boolean[][]** là mảng của các mảng, gồm overhead mỗi hàng.
- **DSU** có các mảng parent,size dùng int[n].
- **BigInteger** có object và mảng biểu diễn số khi tổng trọng số đủ lớn.

Do đó công thức khoảng 9n² byte cho ma trận đôi chỉ là **ước tính phần dữ liệu thô tối thiểu**, không phải bộ nhớ toàn chương trình hoặc bảo đảm phù hợp với RAM cụ thể.

### Cách giảm bộ nhớ khi cần

- Nếu Kruskal đã có Edge[], **sort trực tiếp trong mảng** nếu không cần giữ nguyên thứ tự input, tránh clone.
- Khi n và m rất lớn, dùng **mảng primitive song song** u[],v[],w[] hoặc cấu trúc compact để tránh một object cho mỗi cạnh.
- Trong Prim heap, cân nhắc lưu thông tin cần thiết nhất trong Candidate; không lưu toàn bộ đường đi hoặc parent chain không cần thiết.
- Với đồ thị dày có matrix input, chạy Prim trực tiếp trên ma trận, tránh đồng thời tạo một Edge object cho từng cặp.
- Nếu graph là đồ thị đơn và mật độ tương đối thấp, danh sách kề tiết kiệm hơn ma trận rất nhiều.
- Nếu chỉ cần xác định graph có MST hay không, cần **kết nối**, có thể dùng BFS/DFS/DSU trong O(n+m) thay vì luôn tính trọng số tối ưu.

Lưu ý việc tự tối ưu mảng primitive làm code khó đọc; chỉ nên ưu tiên khi giới hạn dữ liệu và RAM thực sự yêu cầu.

## 16. Độ phức tạp khác nhau khi thay biến thể Prim

Tên “Prim” không đủ để xác định Big-O. Phải hỏi **Prim với cấu trúc gì**:

- **Prim + ma trận + quét tuyến tính:** O(n²) thời gian, O(n²) bộ nhớ ma trận.
- **Prim + adjacency list + binary heap** (lazy cạnh): O(n+m log(m+1)) thời gian, O(n+m) bộ nhớ.
- **Prim + Fibonacci heap / decrease-key** ở mô hình lý thuyết thích hợp: O(m+n log n) thời gian khấu hao, đổi lại triển khai phức tạp hơn nhiều.

Bản Java PriorityQueue chuẩn không cung cấp thao tác **decrease-key** bằng cách sửa trực tiếp khóa của phần tử trong heap và tự tái cân bằng. Nếu muốn dùng key tốt nhất cho từng đỉnh, cách phổ biến là thêm **entry mới** và bỏ entry cũ khi pop; phải phân tích số entry và bộ nhớ.

Không nên ghi “Prim luôn O(n²)” hoặc “Prim luôn O(m log n)” mà không nêu cấu trúc dữ liệu.

### Tính toán crossover

Khi m gần n, Kruskal/Prim heap thường có số thao tác xấp xỉ n log n, trong khi Prim ma trận quét n² vị trí.

Khi m gần n², Kruskal hoặc heap có thể cần n² log n thao tác trên cạnh, còn Prim ma trận quét n² vị trí.

Tuy nhiên, thời gian thực còn có yếu tố **cache locality, object allocation, cost của comparator, GC, overhead của input**, nên ranh giới crossover cần được đo trên máy và bài cụ thể. Không có công thức mật độ duy nhất giải quyết mọi trường hợp.

## 17. Kiểm thử độc lập: vét cạn rừng khung trên graph nhỏ

Để QA ba thuật toán trên, có thể dùng một oracle **không dựa trên Kruskal hoặc Prim** cho n nhỏ và m nhỏ.

1. Dùng connectivity của graph gốc để tính số thành phần c.
2. Duyệt mọi tập con cạnh bằng bitmask từ 0 đến 2^m−1.
3. Với mỗi tập con, kiểm tra **không có chu trình**. Nếu xuất hiện chu trình, loại tập con.
4. Kiểm tra tập con có đúng **n−c cạnh**. Một rừng không chu trình có n−c cạnh là rừng bao phủ mỗi thành phần của graph gốc.
5. Tính tổng trọng số và lấy giá trị nhỏ nhất.

Với m≤11, số tập con nhiều nhất 2.048, nên có thể thử hàng trăm graph nhỏ gồm cạnh song song, self-loop và trọng số âm.

So kết quả của cả ba:

- **totalWeight** đúng bằng oracle.
- **edgesUsed** bằng n−c.
- **components** bằng c.
- Nếu có danh sách cạnh được xuất, kiểm tra mỗi cạnh có trong input, không trùng ID, không chu trình, và nối đủ thành phần.

### Vì sao không chỉ so Kruskal với Prim?

Nếu hai thuật toán có cùng một lỗi trong xử lý self-loop, ví dụ gộp trọng số cạnh âm vào tổng mà không chọn cạnh, chúng có thể cùng sai. Oracle độc lập kiểm tra **tính tối ưu của một tập con thực sự** và điều kiện không chu trình, giúp phát hiện lỗi mà chỉ đối chiếu hai lời giải có thể bỏ qua.

### Những ca QA quan trọng

| Ca | Kết quả kỳ vọng |
| --- | --- |
| n=0, m=0 | MSF rỗng, tổng 0, c=0 |
| n=1, có self-loop âm | Tổng 0, c=1 |
| n=4, không cạnh | Tổng 0, c=4 |
| n=2, hai cạnh song song 8 và −2 | Chọn cạnh −2 |
| Hai tam giác rời nhau | Có MSF nhưng không MST chung |
| Graph thưa nối thành đường | Tất cả cạnh đường thường phải chọn |
| Graph đầy đủ có nhiều trọng số bằng nhau | Có thể nhiều MST, tổng phải giống |
| Graph có trọng số âm và 0 | Không được loại cạnh chỉ vì âm |
| Input có cạnh trọng số Long.MAX_VALUE | Không nhầm với không có cạnh |
| Tổng MST vượt long | BigInteger giữ được tổng chính xác |
| Một component cô lập khỏi các component còn lại | MSF vẫn bao gồm cây của mỗi component |

**Kiểm thử không thay thế chứng minh tính chất cắt.** Kết hợp thử nghiệm trên đồ thị nhỏ với chứng minh cut property mới cho độ tin cậy cao.

## 18. Những lỗi phổ biến cần tránh

1. **Chọn thuật toán theo m mà bỏ qua n**, không kiểm tra n² có vừa RAM hay không.
2. **Tạo ma trận n×n cho graph thưa n rất lớn**, gây hết bộ nhớ.
3. **Tuyên bố Prim luôn O(n²)** hoặc luôn O(m log n) mà không nêu cách cài.
4. **Tính density=2m/[n(n−1)] với multigraph rồi tin luôn nằm trong [0,1]**.
5. **Dùng adjacency matrix nhưng vẫn giữ tất cả Edge objects trong RAM** khi không cần.
6. **Dùng comparator lấy hiệu hai trọng số long rồi ép int**, có thể tràn và sort sai.
7. **Dùng một sentinel Long.MAX_VALUE trong ma trận**, nhầm cạnh hợp lệ có trọng số ấy với không có cạnh.
8. **Không bỏ qua self-loop**, dù nó không nối thêm đỉnh.
9. **Gộp cạnh song song bằng trung bình trọng số hoặc cạnh cuối**, thay vì cạnh nhẹ nhất nếu muốn tối ưu.
10. **Dùng visited[vertex] để loại cạnh Kruskal**, thay vì DSU để xác định chu trình.
11. **Thêm cạnh vào Prim dù cả hai đầu đã visited**, tạo chu trình.
12. **Không bỏ entry heap lỗi thời**, có thể tính một đỉnh nhiều lần.
13. **Không khởi động lại Prim cho thành phần mới**, trả rừng thiếu cây.
14. **Coi MSF của graph không liên thông là MST toàn graph**, sai yêu cầu connected spanning.
15. **Nhầm MST với shortest path tree**, tối ưu sai tiêu chí.
16. **Cho rằng cạnh âm không được phép trong MST**, dù cut property vẫn đúng.
17. **Chọn mọi cạnh âm**, kể cả self-loop hoặc cạnh tạo chu trình.
18. **Dùng tổng int hoặc long thiếu cận**, có thể tràn khi có nhiều cạnh lớn.
19. **Chỉ so tổng weight trong QA**, không kiểm tra số cạnh n−c và tính nối/cyclic.
20. **Không tính cả input và cấu trúc phụ khi ước lượng RAM**, báo sai phương án an toàn.
21. **Dùng ma trận cho graph có hướng rồi coi như MST vô hướng**, trong khi directed arborescence là bài khác.
22. **Cố dừng Kruskal khi chọn n−1 cạnh** trên graph không liên thông mà không xem c thật.
23. **Giữ PriorityQueue với entry cũ nhưng thay khóa object đang ở trong heap**, có thể phá heap order.
24. **Tuyên bố graph dày luôn Prim ma trận**, ngay cả khi n² không thể cấp phát.
25. **Không phân biệt đồ thị đơn với đa đồ thị khi tính số cạnh tối đa**.
26. **Không đọc đúng định dạng đầu ra MST/MSF của đề**, gây WA dù tổng weight hợp lý.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** n=100.000, m=200.000, giới hạn RAM 256 MB. Có nên dựng ma trận n×n?  
**Đáp án:** Không. Ma trận có 10 tỷ ô, vượt xa RAM. Ưu tiên Kruskal hoặc Prim heap trên cấu trúc thưa.

**Câu 2.** Graph vô hướng đơn có n đỉnh tối đa bao nhiêu cạnh?  
**Đáp án:** n(n−1)/2, khi không có self-loop và không có cạnh song song.

**Câu 3.** Graph không liên thông có tồn tại MST phủ hết mọi đỉnh không?  
**Đáp án:** Không. Có thể tìm MSF trên từng thành phần.

**Câu 4.** MSF của graph n đỉnh với c thành phần có bao nhiêu cạnh?  
**Đáp án:** n−c cạnh.

**Câu 5.** Kruskal dựa trên thao tác nào để tránh chu trình?  
**Đáp án:** DSU kiểm tra hai đầu cạnh thuộc hai thành phần khác nhau rồi mới union.

**Câu 6.** Prim heap lazy cần xử lý entry lỗi thời thế nào?  
**Đáp án:** Nếu đầu đến đã visited khi lấy entry khỏi heap, bỏ entry đó.

**Câu 7.** Prim ma trận O(n²) có ưu thế gì khi graph gần đầy đủ?  
**Đáp án:** Không phải sort/heap gần n² cạnh; chỉ quét n² khóa/cạnh ma trận.

**Câu 8.** Nếu có self-loop trọng số −100, MST có chọn không?  
**Đáp án:** Không. Self-loop không nối đỉnh khác và tạo chu trình.

**Câu 9.** Nhiều cạnh giữa cùng hai đỉnh với trọng số 5,2,9. Cạnh nào đủ để xét MST?  
**Đáp án:** Cạnh trọng số 2; các cạnh song song nặng hơn không thể cải thiện tổng.

**Câu 10.** Trong graph đơn, m≈n, chọn Kruskal hay Prim ma trận?  
**Đáp án:** Thường Kruskal/Prim heap vì O(n+m) bộ nhớ; Prim ma trận O(n²) lãng phí.

**Câu 11.** Prim ma trận muốn phân biệt không có cạnh với cạnh weight=Long.MAX_VALUE cần gì?  
**Đáp án:** Cờ hasEdge hoặc một biểu diễn existence tách biệt, không dùng sentinel trùng trọng số.

**Câu 12.** Hai MST có thể khác tập cạnh nhưng cùng tổng không?  
**Đáp án:** Có khi nhiều cạnh bằng trọng số hoặc có nhiều lựa chọn tối ưu.

**Câu 13.** Graph có hướng có thể áp dụng trực tiếp Kruskal/Prim vô hướng không?  
**Đáp án:** Không. Bài cây khung định hướng có mô hình và thuật toán riêng.

**Câu 14.** Vì sao BigInteger hữu ích khi tổng trọng số lớn?  
**Đáp án:** Tránh overflow của tổng qua nhiều cạnh, dù từng trọng số riêng lẻ nằm trong long.

**Câu 15.** Để kiểm tra ba thuật toán trên graph n,m nhỏ, oracle nào độc lập?  
**Đáp án:** Duyệt tất cả tập con m cạnh, chỉ giữ tập con không chu trình có n−c cạnh, rồi lấy tổng nhỏ nhất.

## 20. Tổng kết

**Mật độ và bộ nhớ là hai trục chính khi chọn thuật toán MST**:

- **Đồ thị thưa (m gần n):** Kruskal + DSU hoặc Prim + adjacency list + heap. Tránh ma trận n².
- **Đồ thị dày (m gần n²) và n vừa RAM:** Prim ma trận có lợi thế O(n²) thời gian.
- **Graph input là danh sách cạnh:** Kruskal thường thuận tiện; Prim heap cần dựng adjacency.
- **Graph input là ma trận:** Prim ma trận có thể dùng trực tiếp, không phải tạo và sort mọi cạnh.
- **Graph không liên thông:** ba thuật toán có thể trả MSF; nếu đề yêu cầu MST toàn graph, phải báo không tồn tại khi components>1.
- **Cạnh âm, cạnh song song, self-loop:** đều có thể xuất hiện trong dữ liệu; cạnh âm hợp lệ, song song cần giữ/gộp đúng, còn khuyên tự nối không thuộc rừng khung.
- **Độ phức tạp cụ thể:** Kruskal phụ thuộc sort m cạnh, Prim heap phụ thuộc thao tác heap, Prim ma trận phụ thuộc n².
- **Big-O chỉ là một phần:** khi dùng Java, overhead objects, queue, mảng hàng và input gốc cũng tiêu thụ RAM đáng kể.

**Quy tắc tư duy:** hãy ước lượng **n, m, m/n², RAM và kiểu input** trước, sau đó chọn biểu diễn và thuật toán phù hợp. Đừng chọn chỉ vì một thuật toán có tên quen thuộc hoặc vì mật độ vượt một tỷ lệ tùy ý.
