# Đồ thị thưa, đồ thị dày và lựa chọn cách lưu trữ

## 1. Cùng số đỉnh, số cạnh rất khác nhau

Giả sử ta quản lý một mạng gồm 1.000 thiết bị. Trong mạng thứ nhất, mỗi thiết bị chỉ kết nối với vài thiết bị khác. Trong mạng thứ hai, hầu như mọi cặp thiết bị đều có liên kết. Nếu dùng **ma trận kề** cho cả hai mạng, ta vẫn phải dành chỗ cho khoảng **một triệu ô**. Ngược lại, nếu dùng **danh sách kề**, số mục lưu trữ tăng chủ yếu theo số liên kết thực.

Đó là lý do cần phân biệt:

- **Đồ thị thưa (sparse graph):** số cạnh/cung nhỏ so với số liên kết tối đa có thể có.
- **Đồ thị dày (dense graph):** có nhiều cạnh/cung so với số liên kết tối đa.

Không phải hai loại đồ thị có hai định nghĩa cấu trúc khác nhau. Chúng vẫn là đồ thị `G=(V,E)`; khác biệt nằm ở **quy mô tập E tương đối với tập V** và hệ quả về bộ nhớ, truy vấn, thao tác cập nhật và thuật toán.

**Mục tiêu bài học:** tính mật độ cạnh đúng theo loại đồ thị, hiểu vì sao chi phí biểu diễn có thể là `O(n+m)` hoặc `O(n²)`, lựa chọn giữa **danh sách kề, ma trận kề, danh sách cạnh và CSR**, đồng thời tránh suy luận sai rằng “dày thì luôn dùng ma trận” hay “thưa thì mọi thao tác đều nhanh”.

## 2. N, M và số liên kết tối đa

Ký hiệu:

- `n=|V|`: số **đỉnh**.
- `m=|E|`: số **cạnh vô hướng** hoặc **cung có hướng** thực tế.
- `m_max`: số liên kết tối đa theo **mô hình đồ thị đang xét**.

Để nói về mật độ theo tỷ lệ hữu hạn, trước tiên xét **đồ thị đơn không có khuyên và không có cạnh/cung song song**.

### Đồ thị vô hướng đơn

Một cạnh nối hai đỉnh **phân biệt**, và cặp `{u,v}` không phân biệt thứ tự. Số cặp có thể chọn từ `n` đỉnh là:

\[
m_{\max}=\binom{n}{2}=\frac{n(n-1)}{2}.
\]

Định nghĩa mật độ cạnh, khi `n\ge2`:

\[
\rho_{\mathrm{vo\ huong}}
=\frac{m}{m_{\max}}
=\frac{2m}{n(n-1)}.
\]

### Đồ thị có hướng đơn

Một cung từ `u` tới `v` khác cung từ `v` tới `u`. Vì không cho khuyên, mỗi đỉnh có thể có cung tới `n-1` đỉnh khác:

\[
m_{\max}=n(n-1),
\qquad
\rho_{\mathrm{co\ huong}}=\frac{m}{n(n-1)}.
\]

Trong hai công thức, `0\le\rho\le1`. Đồ thị không có cạnh có mật độ 0; đồ thị đầy đủ theo đúng quy ước đang dùng có mật độ 1.

**Với `n=0` hoặc `n=1` và mô hình không cho khuyên**, `m_max=0`: tỷ số mật độ là `0/0`, **không xác định**. Một API có thể quy ước trả 0 cho tiện xử lý, nhưng phải nêu rõ đó là **quy ước phần mềm**, không phải kết quả chia số học.

### Khi có khuyên hoặc cạnh song song

Nếu **cho phép khuyên nhưng vẫn không có cạnh/cung song song**:

- Vô hướng: `m_max=n(n+1)/2` vì có thêm `n` khuyên.
- Có hướng: `m_max=n²` vì thêm `n` cung `u→u`.

Nếu **cho phép cạnh/cung song song không giới hạn**, `m` không còn bị chặn bởi `O(n²)` theo số đỉnh cố định. Khi đó không nên áp dụng máy móc công thức mật độ của đồ thị đơn. Có thể đo **tỷ lệ cặp đỉnh có ít nhất một liên kết** và đo riêng **số liên kết trung bình trên mỗi cặp**, tùy mục đích phân tích.

## 3. Tính mật độ qua những ví dụ

| Mô hình đơn không khuyên | `n` | `m` | `m_max` | Mật độ xấp xỉ |
| --- | ---: | ---: | ---: | ---: |
| Vô hướng, mạng thưa | 1.000 | 2.000 | 499.500 | 0,40% |
| Vô hướng, mạng dày | 1.000 | 400.000 | 499.500 | 80,08% |
| Vô hướng, quy mô lớn thưa | 10.000 | 30.000 | 49.995.000 | 0,06% |
| Có hướng, 1.000 đỉnh | 1.000 | 2.000 | 999.000 | 0,20% |

Hai hàng đầu có **cùng `n=1000`** nhưng số cạnh chênh lệch 200 lần. Với ma trận kề đặc, cả hai vẫn có `n²=1.000.000` vị trí; với danh sách kề, số mục kề cho đồ thị vô hướng không khuyên lần lượt là **4.000** và **800.000**.

**Ví dụ tính tay:** `n=1000, m=2000` trong đồ thị vô hướng đơn:

\[
\rho=\frac{2\cdot2000}{1000\cdot999}
\approx0{,}004004=0{,}4004\%.
\]

Nếu cùng `n,m` nhưng coi cung là **có hướng**, tỷ lệ nhỏ hơn một nửa:

\[
\rho=\frac{2000}{1000\cdot999}\approx0{,}2002\%.
\]

Không thể so sánh “mật độ 2%” của hai bộ dữ liệu khi một bộ **vô hướng** và bộ kia **có hướng** mà quên nêu cách tính mẫu số.

## 4. “Thưa” và “dày” không phải nhãn tuyệt đối

Trong phân tích tiệm cận, hai tình huống điển hình là:

- **Rất thưa:** `m=O(n)`, tức số liên kết tăng gần tuyến tính theo số đỉnh. Một cây vô hướng có `n-1` cạnh là ví dụ điển hình.
- **Dày:** `m=\Theta(n²)`, tức số liên kết tăng cùng bậc với số cặp đỉnh có thể tạo.

Đây là các **mô tả họ đồ thị khi n tăng**, không phải quy định rằng “dưới 10% là thưa, trên 10% là dày”. Một bộ dữ liệu hữu hạn phải được chọn cấu trúc theo **mật độ, bộ nhớ thực tế và kiểu truy vấn**, không chỉ theo một nhãn.

Một số điều cần phân biệt:

1. **Liên thông không có nghĩa dày.** Một cây có `n-1` cạnh vẫn liên thông nếu `n\ge1`, nhưng rất thưa.
2. **Không liên thông không có nghĩa thưa.** Hai nhóm đỉnh có thể tạo hai clique lớn nhưng không có cạnh giữa hai nhóm; số cạnh toàn đồ thị vẫn là `\Theta(n²)`.
3. **Có hướng không có nghĩa dày.** Một chuỗi phụ thuộc `A→B→C→D` chỉ có `n-1` cung.
4. **Không có chu trình không nhất thiết thưa** đối với đồ thị có hướng: một DAG có thể chứa tới `n(n-1)/2` cung nếu mọi cung đi từ đỉnh đứng trước tới đỉnh đứng sau trong một thứ tự topo.
5. **Trọng số không quyết định mật độ.** Một cạnh trọng số 0 vẫn là cạnh; một cung trọng số 1.000 vẫn chỉ là một cung.

Mật độ cho biết **bao nhiêu liên kết tồn tại**, không cho biết đồ thị có liên thông hay không, phân bố bậc có đều không, trọng số lớn hay nhỏ, hoặc thuật toán nào chắc chắn chạy nhanh hơn trên máy thực tế.

## 5. Danh sách kề: chi phí tăng theo số cạnh thực

**Danh sách kề (adjacency list)** lưu mỗi đỉnh kèm các láng giềng/cung đi ra:

```text
Đồ thị vô hướng:
A: [B, C]
B: [A]
C: [A]
D: []       Đỉnh cô lập vẫn được lưu
```

Với đồ thị **có hướng**, mỗi cung `u→v` thường đóng góp **một mục** vào `adj[u]`. Với đồ thị **vô hướng**, một cạnh `{u,v}` giữa hai đỉnh phân biệt thường đóng góp **hai mục**, một ở mỗi phía.

Khi mỗi mục và mỗi ID có kích thước hằng số:

\[
S_{\mathrm{danh\ sach\ ke}}=\Theta(n+m).
\]

Ngay cả `m=0`, cấu trúc vẫn phải dành chỗ cho **n đỉnh**, kể cả danh sách kề rỗng.

### Các thao tác điển hình

- **Duyệt láng giềng của `u`:** `O(deg(u))` vô hướng, hoặc `O(outdeg(u))` có hướng.
- **BFS/DFS toàn bộ đồ thị:** `O(n+m)` khi thăm từng đỉnh, duyệt từng mục kề một số lần hằng định và đánh dấu ID hiệu quả.
- **Kiểm tra có cạnh/cung `u→v` không:** `O(deg(u))` hoặc `O(outdeg(u))` nếu mỗi danh sách là **list không có chỉ mục tìm nhanh**.
- **Nếu dùng hash set/map cho láng giềng:** kiểm tra cạnh thường đạt `O(1)` **kỳ vọng**, với đánh đổi bộ nhớ phụ và các giả định về hàm băm/chi phí khóa.
- **Nếu mỗi danh sách đã sắp xếp:** có thể kiểm tra cạnh bằng tìm nhị phân trong `O(\log(d(u)+1))`, nhưng chèn/xóa giữa mảng động có thể cần `O(d(u))` để dời phần tử.

Danh sách kề đặc biệt phù hợp cho **đồ thị thưa có nhiều thao tác duyệt từ một đỉnh**, chẳng hạn tìm các học phần phụ thuộc, lan truyền thông tin hay BFS/DFS. Tuy vậy, “danh sách kề” không tự có `O(1)` cho mọi truy vấn; **kiểu dữ liệu bên trong mỗi danh sách** vẫn quan trọng.

## 6. Ma trận kề: chi phí tăng theo bình phương số đỉnh

**Ma trận kề (adjacency matrix)** lưu `A[i][j]` cho **mọi cặp chỉ số đỉnh**:

```text
V = [A, B, C, D]
E vô hướng = {{A,B}, {A,C}}

      A  B  C  D
A     0  1  1  0
B     1  0  0  0
C     1  0  0  0
D     0  0  0  0
```

Đồ thị vô hướng đơn có ma trận **đối xứng**; đồ thị có hướng không bắt buộc đối xứng. Khuyên nếu được phép xuất hiện tại đường chéo `A[i][i]`.

Ma trận **đặc** có `n²` ô:

\[
S_{\mathrm{ma\ tran\ ke}}=\Theta(n²).
\]

Đồ thị với `m=0` vẫn có `n²` ô. Nếu đã biết chỉ số `i,j`, kiểm tra **một liên kết cụ thể** chỉ mất:

\[
T_{\mathrm{hasEdge}}=O(1).
\]

Nhưng để **liệt kê láng giềng của `u`**, phải quét cả hàng `n` ô: **`O(n)`**, ngay cả khi chỉ có một láng giềng. BFS/DFS duyệt **toàn bộ** ma trận theo cách quét hàng có cận **`O(n²)`**.

### Ma trận có trọng số

Nếu ô lưu trọng số, cần một giá trị riêng cho **không có cạnh**, chẳng hạn `None`. Không nên dùng `0` để biểu thị vắng liên kết nếu **trọng số 0 hợp lệ**. Với đồ thị vô hướng có trọng số, hai ô `A[i][j]` và `A[j][i]` phải thống nhất theo cùng một cạnh.

Một ma trận Boolean chỉ ghi nhận **có/không** một liên kết; để giữ **cạnh song song**, phải mở rộng mỗi ô thành số lượng hoặc danh sách ID cạnh. Khi đó bậc chi phí bộ nhớ còn phụ thuộc các bản ghi liên kết thật được lưu trong ô.

## 7. Dung lượng thô: một bit, một số và overhead

Giả sử `n=10.000`. Ma trận có:

\[
n²=100.000.000\text{ ô}.
\]

Nếu lưu bằng một cấu trúc dữ liệu **đặc, đóng gói chặt**:

| Quy ước kích thước một ô | Dữ liệu thô cho `n=10.000` |
| --- | ---: |
| 1 bit/ô (bitset cho có/không) | 12,5 MB |
| 4 byte/ô | 400 MB |
| 8 byte/ô | 800 MB |

Các số dùng **MB thập phân**, chỉ đếm dữ liệu thô. Ví dụ một ma trận Python kiểu `list[list[object]]` còn tốn bộ nhớ cho **đối tượng danh sách, tham chiếu và quản lý cấp phát**. Ngược lại, một thư viện bitset chuyên dụng có thể sử dụng ít byte hơn trên mỗi ô và hỗ trợ một số phép toán song song theo từ máy.

Vì thế, không nên kết luận “ma trận kề của 10.000 đỉnh chắc chắn tốn đúng 800 MB” nếu chưa biết loại ô và cách cấp phát. Dù nén theo bit, **bậc tăng trưởng `\Theta(n²)` không thay đổi**.

Danh sách kề cũng có overhead: mỗi mục có thể mang ID đỉnh, trọng số, con trỏ, hoặc ID liên kết; nếu lưu bằng nhiều đối tượng Python, bộ nhớ thực tế có thể lớn hơn một mảng chỉ số nguyên được đóng gói chặt.

**Kết luận:** khi so sánh bộ nhớ thực tế, cần xét **số mục** lẫn **số byte cho mỗi mục**; chỉ dùng Big-O là chưa đủ để quyết định điểm giao giữa hai biểu diễn.

## 8. Danh sách cạnh và CSR: hai lựa chọn nữa

### Danh sách cạnh (edge list)

Danh sách cạnh lưu từng liên kết thành một bản ghi, ví dụ:

```text
id   nguồn   đích   trọng số
e0   A       B      5
e1   A       C      7
e2   C       D      2
```

Khi giữ cả tập đỉnh, bộ nhớ là **`O(n+m)`**. Phù hợp với **nhập/xuất dữ liệu, lưu đa đồ thị** và các thuật toán thường quét **toàn bộ các cạnh** (ví dụ Kruskal sắp cạnh theo trọng số, Bellman–Ford nới lỏng các cung nhiều lần).

Nhưng nếu chỉ có một mảng bản ghi chưa có chỉ mục, tìm **mọi cung đi ra từ một đỉnh** có thể phải quét **`O(m)`** cạnh. Nếu BFS làm vậy cho nhiều đỉnh, chi phí có thể tăng tới `O(nm)` thay vì `O(n+m)`. Thường nên chuyển sang danh sách kề nếu cần duyệt từ đỉnh nhiều lần.

### CSR: Compressed Sparse Row

**CSR** là một cách lưu **danh sách kề dạng mảng nén**, phổ biến trong đồ thị tĩnh và ma trận thưa. Với các đỉnh đánh số `0,1,...,n-1`, CSR thường gồm:

- `offset` hoặc `row_ptr`: mảng `n+1` chỉ số; `offset[u]` là điểm bắt đầu các mục kề của `u`.
- `neighbor` hoặc `col_idx`: mảng chứa các đích kề, có **`m` mục** ở đồ thị có hướng nếu mỗi cung có một mục đi ra.
- Mảng `weight` hoặc `edge_id` tùy nhu cầu, căn chỉnh cùng các mục kề.

Ví dụ đồ thị có hướng:

```text
0 -> 1, 0 -> 3, 2 -> 3
V = {0,1,2,3}

adj[0] = [1,3]
adj[1] = []
adj[2] = [3]
adj[3] = []

offset   = [0, 2, 2, 3, 3]
neighbor = [1, 3, 3]

Láng giềng u = neighbor[offset[u] : offset[u+1]]
```

CSR chiếm **`\Theta(n+m)` mục** (vô hướng thường có `2m` mục kề) nhưng tránh lưu nhiều đối tượng list nhỏ. Duyệt một hàng là `\Theta(d(u))`. Nếu các đích trong hàng đã sắp xếp, có thể kiểm tra thành viên bằng tìm nhị phân `O(\log(d(u)+1))`; nếu chưa sắp xếp thì kiểm tra thường phải quét `O(d(u))`.

CSR phù hợp khi **tập cạnh tương đối tĩnh**. Chèn/xóa một mục có thể buộc dịch chuyển các phần tử phía sau và sửa `offset`, tốn **`O(n+m)` trường hợp xấu** cho một cập nhật đơn lẻ; trong trường hợp cập nhật nhiều, có thể dựng lại theo lô hoặc chọn cấu trúc động.

## 9. Bảng so sánh nhanh các biểu diễn

Giả sử đồ thị đơn, mỗi ID/trọng số có kích thước hằng số; `d(u)` là số mục kề của `u`, tương ứng với bậc vô hướng hoặc bậc ra.

| Biểu diễn | Bộ nhớ | Kiểm tra có cung/cạnh `u→v` | Liệt kê láng giềng của u | Duyệt toàn bộ bằng BFS/DFS |
| --- | --- | --- | --- | --- |
| Danh sách kề dạng **list** | `O(n+m)` | `O(d(u))` xấu nhất | `O(d(u))` | `O(n+m)` |
| Danh sách kề dạng **hash set/map** | `O(n+m)` về số mục | `O(1)` kỳ vọng | `O(d(u))` | `O(n+m)` kỳ vọng về phép truy cập hash |
| **Ma trận kề đặc** | `O(n²)` | `O(1)` theo chỉ số | `O(n)` | `O(n²)` |
| **Danh sách cạnh thuần** | `O(n+m)` nếu giữ V | `O(m)` | `O(m)` khi lọc | Có thể `O(nm)` nếu quét lại E tại từng đỉnh |
| **CSR** | `O(n+m)` | `O(d(u))`, hoặc `O(\log(d(u)+1))` nếu hàng được sắp | `O(d(u))` | `O(n+m)` |

Nhìn bảng có thể thấy **mật độ không phải yếu tố duy nhất**:

- Nếu cần **tra cứu cặp đỉnh** rất nhiều, ma trận hoặc danh sách kề dạng hash map đều đáng cân nhắc.
- Nếu cần **duyệt từng láng giềng**, danh sách kề/CSR thường tránh xét nhiều ô trống.
- Nếu cần **xử lý từng cạnh độc lập** hoặc nhập/xuất dữ liệu, danh sách cạnh rất thuận tiện.
- Nếu dữ liệu ít thay đổi và quy mô lớn, CSR có lợi thế **bố trí mảng gọn**; nếu thay đổi liên tục, danh sách kề động linh hoạt hơn.

## 10. Thuật toán có thể thay đổi quyết định lựa chọn

### BFS và DFS

Trên danh sách kề, duyệt toàn bộ đồ thị theo cách thông thường có:

\[
T=O(n+m).
\]

Với ma trận kề đặc, mỗi lần xử lý một đỉnh phải quét hàng độ dài `n`, nên duyệt toàn bộ có:

\[
T=O(n²).
\]

Nếu `m=O(n)`, khác biệt tiệm cận rất rõ. Nếu `m=\Theta(n²)`, hai cận cùng bậc; ma trận có thể cạnh tranh nhờ truy cập ô trực tiếp hoặc bitset, nhưng hiệu năng thực còn tùy hiện thực.

### Dijkstra và Prim

Không nên mặc định “danh sách kề luôn chạy mọi thuật toán nhanh hơn”:

- Dijkstra với **danh sách kề và heap nhị phân** có cận thông dụng `O((n+m)\log n)` đối với đồ thị có trọng số **không âm**.
- Dijkstra dùng **mảng khoảng cách và lựa chọn đỉnh nhỏ nhất bằng quét tuyến tính** có thể thực hiện trong `O(n²)` trên ma trận kề, thích hợp để cân nhắc khi đồ thị **rất dày**.
- Prim tìm cây khung nhỏ nhất trong **đồ thị vô hướng có trọng số** cũng có biến thể `O(n²)` với ma trận và phép chọn đỉnh bằng quét; biến thể dùng heap/danh sách kề có cận phụ thuộc `n,m`.

Đây là các **cách cài đặt khác nhau của thuật toán**, không phải bảo đảm ma trận luôn thắng khi `m` lớn. Lựa chọn phải xét đặc tính thuật toán, mật độ, kích thước dữ liệu và môi trường triển khai.

### Thuật toán trên tất cả cặp đỉnh

Một số bài toán cần xét **mọi cặp đỉnh**, chẳng hạn tính đường đi ngắn nhất cho tất cả cặp bằng **Floyd–Warshall** với chi phí `O(n³)` thời gian và `O(n²)` bộ nhớ. Khi đó, lưu một **ma trận khoảng cách** thường tự nhiên bất kể đồ thị ban đầu thưa hay dày.

Đặc biệt, **ma trận khoảng cách sau khi tính đường đi** không phải lúc nào cũng giống **ma trận kề đầu vào**: nó chứa thông tin về đường đi qua nhiều cung, không chỉ các liên kết trực tiếp.

## 11. Dữ liệu có hướng, có trọng số và nhiều cạnh

Những quy tắc này vẫn quan trọng dù đồ thị thưa hay dày:

**Có hướng:** danh sách kề thường lưu cung **đi ra**; ma trận có quy ước **hàng nguồn, cột đích**. Một cung `A→B` không tự tạo cung `B→A`. Nếu thường xuyên hỏi cung đi vào, cần chỉ mục ngược, bộ đếm bậc vào hoặc quét cấu trúc theo cách thích hợp.

**Có trọng số:** mỗi cạnh/cung có thể mang chi phí, độ dài hoặc thuộc tính khác. Trọng số `0` vẫn có thể biểu diễn một liên kết tồn tại. Trong ma trận, `None` hoặc một dấu vắng rõ ràng tách **không có cạnh** khỏi **cạnh có trọng số bằng 0**. Trong danh sách kề, mỗi mục có thể là `(neighbor,weight)`.

**Khuyên:** đồ thị vô hướng có khuyên đóng góp **hai vào bậc** theo quy ước chuẩn; cung khuyên đóng góp một vào bậc ra và một vào bậc vào. Ma trận đặt khuyên ở đường chéo; danh sách kề cần chính sách đếm rõ ràng.

**Cạnh/cung song song:** nếu một cặp đỉnh có nhiều liên kết riêng, mỗi liên kết nên có **edge ID**; set láng giềng và ma trận Boolean chỉ cho biết **có ít nhất một liên kết**. Khi cần lưu nhiều tuyến/trọng số, dùng danh sách cạnh theo ID, danh sách kề kèm ID hoặc ô ma trận chứa danh sách ID, không gộp mất dữ liệu.

**Đỉnh cô lập:** cho dù không xuất hiện trong cạnh nào, đỉnh vẫn thuộc `V`; danh sách kề phải có mục rỗng, ma trận phải có hàng và cột tương ứng.

## 12. Python: so sánh số mục phải xem khi BFS

Ví dụ dưới đây tạo **cùng một đồ thị vô hướng đơn không khuyên** bằng danh sách kề và ma trận kề. Hai thuật toán BFS trả về cùng tập đỉnh tới được nhưng **đếm số mục phải xét khác nhau**. Đây là số phép duyệt mục, **không phải số mili-giây** và không thay thế đo hiệu năng trên dữ liệu thực.

```python
from collections import deque


def tao_hai_bieu_dien(n, edges):
    # Đỉnh được đánh số nguyên từ 0 đến n-1.
    adj = [[] for _ in range(n)]
    matrix = [[False] * n for _ in range(n)]
    da_co = set()

    for u, v in edges:
        if not (0 <= u < n and 0 <= v < n):
            raise ValueError("Đầu mút ngoài phạm vi")
        if u == v:
            raise ValueError("Ví dụ này không cho phép khuyên")
        pair = (min(u, v), max(u, v))
        if pair in da_co:
            raise ValueError("Cạnh vô hướng bị trùng")
        da_co.add(pair)

        adj[u].append(v)
        adj[v].append(u)
        matrix[u][v] = True
        matrix[v][u] = True

    return adj, matrix


def bfs_danh_sach(adj, start):
    queue = deque([start])
    seen = {start}
    order = []
    examined = 0
    while queue:
        u = queue.popleft()
        order.append(u)
        for v in adj[u]:
            examined += 1  # Một mục kề đang tồn tại
            if v not in seen:
                seen.add(v)
                queue.append(v)
    return order, examined


def bfs_ma_tran(matrix, start):
    queue = deque([start])
    seen = {start}
    order = []
    examined = 0
    while queue:
        u = queue.popleft()
        order.append(u)
        for v, has_edge in enumerate(matrix[u]):
            examined += 1  # Mọi ô, gồm cả ô False
            if has_edge and v not in seen:
                seen.add(v)
                queue.append(v)
    return order, examined


n = 8
edges = [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4)]
adj, matrix = tao_hai_bieu_dien(n, edges)

print(len(edges))              # 5 cạnh vô hướng
print(n * (n - 1) // 2)        # 28 cặp đỉnh tối đa
print(f"{len(edges) / 28:.2%}")  # 17.86% mật độ
print(adj[3])                  # [1, 2, 4]
print(adj[7])                  # []: đỉnh cô lập
print(matrix[0][2])           # True
print(matrix[0][7])           # False

print(bfs_danh_sach(adj, 0))
# ([0, 1, 2, 3, 4], 10) -- xét 10 mục kề

print(bfs_ma_tran(matrix, 0))
# ([0, 1, 2, 3, 4], 40) -- xét 5 hàng * 8 ô

print(sum(len(row) for row in adj))  # 10 = 2 * 5 cạnh
print(sum(map(len, matrix)))         # 64 = 8 * 8 ô
```

Trong ví dụ, BFS từ `0` chỉ đi tới các đỉnh `0,1,2,3,4`; ba đỉnh `5,6,7` không thuộc thành phần này. Danh sách kề chỉ xét **10 mục có liên kết**, còn ma trận phải đọc **40 ô** trên năm hàng được thăm.

Nếu muốn **duyệt toàn bộ đồ thị**, chương trình còn phải duyệt riêng những đỉnh chưa thăm. Với danh sách kề, số mục được xét trên toàn đồ thị là `2m=10`, cộng công xử lý `n` đỉnh. Với ma trận, việc quét mọi hàng sẽ xem đủ `n²=64` ô.

**Lưu ý về bộ nhớ:** hàm `tao_hai_bieu_dien` chủ động xây dựng **cả hai cấu trúc** để đối chiếu, vì vậy bộ nhớ của **chính chương trình minh họa** là `O(n²)`. Nếu chỉ giữ `adj`, bộ nhớ biểu diễn còn `O(n+m)`; nếu chỉ giữ `matrix`, là `O(n²)`.

## 13. Quy trình lựa chọn cách lưu trữ

Thay vì chọn chỉ bằng nhãn “thưa/dày”, có thể lần lượt trả lời:

1. **Đồ thị là loại nào?** Có hướng hay vô hướng? Có trọng số, khuyên hoặc cạnh song song không? Có cần giữ từng ID liên kết riêng?
2. **Tập đỉnh có ổn định không?** Thêm/xóa đỉnh thường xuyên có thể khiến việc mở rộng ma trận, cập nhật chỉ số hoặc xây lại CSR trở nên đắt.
3. **Mật độ hiện tại và dự kiến là bao nhiêu?** Tính `m/m_max` theo đúng mô hình; ước lượng `n,m` khi dữ liệu tăng trong tương lai.
4. **Truy vấn quan trọng nhất là gì?** Kiểm tra một cặp đỉnh, duyệt láng giềng, tìm đường, hay quét/sắp xếp toàn bộ cạnh?
5. **Bộ nhớ thực tế ra sao?** Một ô Boolean đóng gói theo bit rất khác một ô số 8 byte hoặc một tham chiếu đối tượng Python.
6. **Cần thứ tự hoặc chỉ mục phụ không?** Danh sách kề dạng set, mảng tăng dần, CSR hay hai chỉ mục kề có các đánh đổi khác nhau.
7. **Có cần cập nhật đồng thời nhiều biểu diễn không?** Nếu vừa giữ danh sách cạnh vừa giữ chỉ mục kề, mọi thao tác thêm/xóa phải cập nhật nhất quán.

### Một vài trường hợp mẫu

| Bài toán | Dấu hiệu | Lựa chọn nên cân nhắc |
| --- | --- | --- |
| Hàng chục nghìn học phần, mỗi học phần có ít quan hệ | Thưa, duyệt phụ thuộc nhiều | **Danh sách kề** hoặc CSR nếu dữ liệu ít thay đổi |
| Mạng cảm biến, cần BFS/DFS thường xuyên | Thưa, truy vấn theo láng giềng | **Danh sách kề** |
| Quan hệ gần như đầy đủ giữa vài trăm đỉnh | Dày, hỏi “có cạnh u–v không?” liên tục | **Ma trận kề**, có thể là bitset nếu không trọng số |
| Thuật toán Kruskal trên một tập cạnh có trọng số | Chủ yếu sắp xếp/duyệt cạnh | **Danh sách cạnh** |
| Đồ thị quy mô lớn, nạp một lần và duyệt tuần tự nhiều lần | Tĩnh, cần cấu trúc mảng gọn | **CSR** |
| Đồ thị cập nhật liên tục, cần tra cạnh nhanh | Có nhiều thêm/xóa | **Danh sách kề dùng hash set/map**, kiểm soát dữ liệu trùng |

Đây là **gợi ý thiết kế**, không phải quy tắc bắt buộc. Một ứng dụng có thể lưu **bản ghi cạnh chuẩn** và đồng thời tạo **chỉ mục danh sách kề** để phục vụ nhiều dạng truy vấn; đổi lại phải trả chi phí bộ nhớ, cập nhật và đồng bộ.

## 14. Những ngộ nhận thường gặp

1. **“Có 1.000 đỉnh thì đồ thị luôn dày.”** Sai: còn phụ thuộc số cạnh/cung `m` so với số liên kết có thể có.
2. **“Mật độ của đồ thị có hướng giống đồ thị vô hướng nếu n,m bằng nhau.”** Sai: với mô hình đơn không khuyên, mẫu số lần lượt là `n(n-1)` và `n(n-1)/2`.
3. **“Liên thông nghĩa là dày.”** Sai: cây có `n-1` cạnh vẫn liên thông và thưa.
4. **“Ma trận kề chỉ dùng bộ nhớ cho các cạnh có thật.”** Sai với ma trận **đặc**: nó cấp phát `n²` ô.
5. **“Danh sách kề lưu mỗi cạnh vô hướng đúng một mục.”** Thông thường sai: cạnh không khuyên được ghi ở cả hai đầu mút.
6. **“Ma trận kề có kiểm tra `O(1)` thì BFS cũng `O(n+m)`.”** Sai: BFS kiểu quét hàng trên ma trận đặc thường có cận `O(n²)` để duyệt toàn bộ.
7. **“Danh sách kề luôn kiểm tra cạnh `O(1)`.”** Sai với list thường; hash set/map cho `O(1)` **kỳ vọng**, còn mảng đã sắp dùng tìm nhị phân.
8. **“Khi đồ thị dày thì ma trận luôn tốt hơn mọi cấu trúc khác.”** Sai: còn phụ thuộc thuật toán, độ biến động dữ liệu, cách nén, bộ nhớ và chi phí hằng số.
9. **“Trọng số 0 đồng nghĩa không có cạnh.”** Sai: phải phân biệt sự tồn tại với trọng số.
10. **“Một set láng giềng hoặc ma trận Boolean giữ được nhiều cạnh song song.”** Sai nếu không mở rộng biểu diễn theo ID hoặc số lượng.
11. **“CSR cập nhật nhanh như list động.”** Không mặc nhiên: chèn/xóa giữa mảng nén có thể phải dịch chuyển nhiều mục và sửa offset.
12. **“Chỉ cần xem Big-O là biết biểu diễn nào dùng ít RAM.”** Chưa đủ: phải xét bitset, kích thước ô, overhead và dữ liệu thực.

## 15. Tự kiểm tra

**Câu 1.** Đồ thị vô hướng đơn không khuyên có `n=100` đỉnh. Số cạnh tối đa là bao nhiêu?

**Đáp án:** `100\cdot99/2=4.950` cạnh.

**Câu 2.** Đồ thị có hướng đơn không khuyên có `n=100` đỉnh và `m=990` cung. Mật độ bằng bao nhiêu?

**Đáp án:** `m_max=100\cdot99=9.900`. Mật độ `990/9.900=0,1=10\%`.

**Câu 3.** Vì sao một cây vô hướng `n` đỉnh với `n-1` cạnh được xem là thưa dù vẫn liên thông?

**Đáp án:** Vì số cạnh tăng tuyến tính theo `n`, còn số cặp đỉnh tối đa tăng theo `n²`. Liên thông không đòi hỏi số cạnh bậc `n²`.

**Câu 4.** Đồ thị có hướng với `n=10.000`, `m=20.000` lưu bằng danh sách kề đi ra có bao nhiêu mục cung? Ma trận đặc có bao nhiêu ô?

**Đáp án:** Có `20.000` mục cung đi ra cộng các cấu trúc chứa `10.000` đỉnh; ma trận đặc có `100.000.000` ô.

**Câu 5.** Tại sao BFS toàn bộ đồ thị dùng danh sách kề có thể là `O(n+m)`, còn ma trận kề đặc là `O(n²)`?

**Đáp án:** Danh sách kề chỉ xét các liên kết tồn tại và các đỉnh; ma trận phải quét cả những ô không có cạnh trong từng hàng được duyệt.

**Câu 6.** Một đồ thị rất thưa nhưng phải hỏi `hasEdge(u,v)` hàng triệu lần. Có nhất thiết chỉ được dùng ma trận để có truy vấn nhanh?

**Đáp án:** Không. Có thể dùng danh sách kề với **hash set/map** láng giềng để kiểm tra `O(1)` kỳ vọng mà bộ nhớ vẫn theo `O(n+m)`; nên cân nhắc thêm chi phí hash, kiểu khóa và cập nhật.

**Câu 7.** Một ma trận có 100 triệu ô Boolean đóng gói 1 bit/ô cần khoảng bao nhiêu MB dữ liệu thô? Nếu mỗi ô dùng 8 byte thì sao?

**Đáp án:** Khoảng **12,5 MB** ở mức bit và **800 MB** ở mức 8 byte/ô, chưa tính overhead và theo đơn vị MB thập phân.

**Câu 8.** Một đồ thị vô hướng cho phép khuyên và cạnh song song. Tại sao không thể áp dụng trực tiếp mật độ `2m/[n(n-1)]` nếu `m` tính tất cả liên kết?

**Đáp án:** Vì công thức giả định **đồ thị đơn không khuyên**. Cạnh song song làm `m` có thể vượt số cặp đỉnh phân biệt; cần thay đổi định nghĩa mật độ và tách tính bội.

**Câu 9.** CSR gồm những mảng chính nào, và vì sao cập nhật thường xuyên có thể bất lợi?

**Đáp án:** Thường gồm `offset` có `n+1` phần tử và `neighbor` chứa các mục kề, có thể thêm trọng số/ID. Chèn/xóa giữa các mảng nén phải dịch chuyển phần tử và điều chỉnh offset, nên đắt hơn cấu trúc động trong nhiều tình huống.

**Câu 10.** Khi nào danh sách cạnh có thể là lựa chọn tốt hơn danh sách kề, và khi nào nên chuyển sang danh sách kề?

**Đáp án:** Danh sách cạnh thuận tiện khi **nhập/xuất, lưu từng liên kết hoặc quét/sắp xếp toàn bộ cạnh**. Nếu thường xuyên cần tìm tất cả láng giềng từ một đỉnh để chạy BFS/DFS, nên dùng/chuyển sang danh sách kề hoặc duy trì chỉ mục kề.

**Ghi nhớ:** **Đồ thị thưa** có số liên kết nhỏ so với số cặp đỉnh có thể nối, còn **đồ thị dày** có nhiều liên kết, thường tới bậc `\Theta(n²)` trong mô hình đồ thị đơn. **Danh sách kề/CSR** lưu theo số đỉnh và cạnh **`\Theta(n+m)`**; **ma trận kề đặc** lưu theo số cặp đỉnh **`\Theta(n²)`** nhưng kiểm tra cạnh đã biết hai đầu mút trong **`O(1)`**. **Danh sách cạnh** tiện quét toàn bộ liên kết, nhưng truy vấn láng giềng có thể tốn `O(m)` nếu không có chỉ mục. Hãy chọn biểu diễn từ **loại đồ thị, mật độ, thuật toán, tần suất cập nhật, kích thước bộ nhớ thực và các bất biến dữ liệu**, không chỉ dựa vào một nhãn “thưa” hoặc “dày”.
