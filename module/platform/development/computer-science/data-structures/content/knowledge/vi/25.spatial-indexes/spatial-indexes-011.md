# Lời nguyền số chiều và giới hạn của giả định truy vấn nhanh

Một chỉ mục không gian có thể tìm điểm gần nhất rất nhanh trên bản đồ hai chiều nhưng chậm đi rõ rệt khi cùng kỹ thuật được áp dụng cho vector 128 hoặc 768 chiều. Sự khác biệt này không đơn giản do mỗi điểm có nhiều tọa độ hơn: **hình học của không gian thay đổi khi số chiều tăng**, khiến các vùng tìm kiếm khó thu hẹp và các nhánh của cây khó bị loại bỏ.

Hiện tượng đó thường được gọi là **lời nguyền số chiều** (*curse of dimensionality*). Trong môn Cấu trúc dữ liệu, đây là lý do quan trọng để đánh giá lại các tuyên bố như “KD-tree tìm hàng xóm gần nhất trong $O(\log n)$”, “R-tree chỉ duyệt một vài nút” hoặc “đã có chỉ mục thì không cần quét toàn bộ dữ liệu”. Những câu nói ấy có thể đúng trong một số mô hình và bộ dữ liệu, nhưng **không phải bảo đảm chung cho mọi số chiều và phân phối điểm**.

Bài học sẽ đi từ khái niệm số chiều, hình học của truy vấn, khả năng tỉa nhánh, đến cách lựa chọn giữa quét toàn bộ, chỉ mục không gian chính xác và tìm kiếm gần đúng.

## 1. Số chiều tác động tới bài toán như thế nào?

Giả sử có $n$ điểm; mỗi điểm là một vector gồm $d$ tọa độ:

$$
p=(p_1,p_2,\ldots,p_d)\in\mathbb{R}^{d}.
$$

Trong không gian hai chiều, một điểm có thể là vị trí $(x,y)$ trên bản đồ. Trong không gian nhiều chiều, một vector có thể là bộ đặc trưng của ảnh, âm thanh, văn bản hoặc hồ sơ người dùng.

Một số thao tác cần phân biệt:

| Truy vấn | Ý nghĩa | Ví dụ |
|---|---|---|
| **Point lookup** | Tìm điểm có tọa độ bằng đúng giá trị yêu cầu | Điểm $(3,5)$ có tồn tại không? |
| **Range query** | Liệt kê các điểm nằm trong một vùng | Các điểm có $2\le x\le5$ và $1\le y\le4$ |
| **Nearest neighbor (NN)** | Tìm một điểm có khoảng cách nhỏ nhất tới truy vấn $q$ | Vị trí gần địa điểm $q$ nhất |
| **$k$-nearest neighbors ($k$-NN)** | Tìm $k$ điểm gần $q$ nhất theo một khoảng cách đã chọn | 10 embedding tương tự nhất |
| **Radius query** | Tìm tất cả điểm có khoảng cách không vượt $r$ | Các điểm trong bán kính 2 km |

**Point lookup** bằng bảng băm có thể rất nhanh dù khóa là vector dài, nếu có biểu diễn khóa và hàm băm phù hợp. Nhưng đó là **khớp chính xác**, không giải quyết tự động bài toán “gần nhất” hoặc truy vấn khoảng. Với dữ liệu không gian, chi phí tính khoảng cách và khả năng loại bỏ vùng không chứa đáp án thường quan trọng hơn phép so sánh bằng nhau.

Các ký hiệu cần theo dõi là $n$ (số điểm), $d$ (số chiều biểu diễn), $k$ (số kết quả cần lấy) và $m$ (số kết quả thực sự thuộc vùng truy vấn). Độ phức tạp có thể phụ thuộc tất cả các tham số này.

## 2. Không gian tăng nhanh khi thêm chiều

Giả sử mỗi tọa độ nằm trong $[0,1]$, và ta chia mỗi trục thành $b$ khoảng bằng nhau. Nếu tạo lưới đều trên cả $d$ chiều, số ô là:

$$
N_{\text{cells}}=b^d.
$$

| Số chiều $d$ | Số ô khi $b=10$ |
|---:|---:|
| 2 | $10^2=100$ |
| 3 | $10^3=1\,000$ |
| 6 | $10^6=1\,000\,000$ |
| 10 | $10^{10}=10\,000\,000\,000$ |
| 20 | $10^{20}$ |

Một lưới đầy đủ có thể phù hợp cho bản đồ 2D hoặc 3D, nhưng trở nên không khả thi ở số chiều lớn. Lưới thưa (*sparse grid*) chỉ lưu ô có điểm sẽ tránh cấp phát toàn bộ $b^d$ ô, song vẫn phải giải quyết bài toán **ô nào đáng thăm để tìm hàng xóm gần nhất**; số lượng ô cần xem có thể rất lớn.

Nếu một hộp truy vấn chiếm tỷ lệ $a$ trên **mỗi trục**, thể tích tương đối của hộp là:

$$
\operatorname{volume}(Q)=a^d,\qquad 0<a<1.
$$

Ví dụ, hộp có cạnh dài 10% phạm vi của mỗi trục chỉ chiếm $0{,}1^2=1\%$ miền 2D, nhưng chiếm $0{,}1^{10}=10^{-10}$ miền 10D. Vì thế, một vùng có vẻ rộng theo từng tọa độ lại có thể chứa rất ít điểm khi tăng chiều.

### Cần vùng rộng bao nhiêu để bắt gặp đủ điểm?

Giả sử $n=1\,000\,000$ điểm được lấy **độc lập, đều** trong siêu lập phương đơn vị $[0,1]^d$. Nếu một hộp truy vấn nằm hoàn toàn trong miền và có cạnh bằng tỷ lệ $a$ của mỗi trục, số điểm kỳ vọng bên trong là:

$$
\mathbb E[m]=n a^d.
$$

Muốn kỳ vọng khoảng 10 điểm, ta cần:

$$
a=\left(\frac{10}{1\,000\,000}\right)^{1/d}=10^{-5/d}.
$$

| Số chiều | Tỷ lệ cạnh $a$ trên **mỗi trục** để kỳ vọng 10 điểm |
|---:|---:|
| $d=2$ | $\approx 0{,}0032$ (0,32%) |
| $d=5$ | $0{,}10$ (10%) |
| $d=10$ | $\approx0{,}316$ (31,6%) |
| $d=20$ | $\approx0{,}562$ (56,2%) |

Để gặp được một lượng điểm cố định, vùng truy vấn phải trải rộng qua tỷ lệ ngày càng lớn trên **mỗi tọa độ**. Đây là một trực giác quan trọng về sự khó khăn của tìm kiếm lân cận nhiều chiều. Công thức dựa trên giả định phân phối đều, các tọa độ độc lập và hộp không bị cắt ở biên; **không áp dụng nguyên xi** cho mọi dữ liệu thực.

## 3. Khoảng cách có thể trở nên khó phân biệt

Trong không gian Euclid, khoảng cách giữa $p$ và $q$ là:

$$
\operatorname{dist}(p,q)=
\sqrt{\sum_{i=1}^{d}(p_i-q_i)^2}.
$$

Tính trực tiếp một khoảng cách cần $O(d)$ phép tính số học theo mô hình thông thường. Nếu lần lượt so sánh truy vấn với mọi điểm, việc đánh giá khoảng cách có chi phí $O(nd)$, trước khi xét thêm chi phí chọn $k$ điểm tốt nhất.

Đối với một số phân phối dữ liệu nhiều chiều, khi $d$ tăng, khoảng cách giữa các cặp điểm ngẫu nhiên **tập trung quanh giá trị điển hình** (*distance concentration*). Chẳng hạn, nếu $X_i$ và $Y_i$ độc lập, đều trên $[0,1]$, thì:

$$
\mathbb E[(X_i-Y_i)^2]=\frac16,\qquad
\mathbb E[\|X-Y\|_2^2]=\frac d6.
$$

Các thành phần bình phương khoảng cách độc lập trong mô hình trên; độ lệch chuẩn của **tổng bình phương khoảng cách** tăng cỡ $\sqrt d$, còn kỳ vọng tăng cỡ $d$. Vì vậy, dao động *tương đối* của tổng bình phương khoảng cách giảm theo bậc $1/\sqrt d$. Nhiều cặp điểm có khoảng cách gần một mức điển hình.

Điều này có thể khiến “gần” và “xa” khó phân biệt hơn, và làm giảm hiệu quả của nhiều điều kiện tỉa nhánh. Tuy nhiên:

- **Không phải định lý cho mọi bộ dữ liệu:** dữ liệu có cụm rõ ràng, phân bố lệch hoặc có chiều nội tại thấp vẫn có thể dễ tìm kiếm.
- **Độ gần phụ thuộc thước đo:** Euclid, Manhattan, cosine similarity và khoảng cách địa lý mô tả các khái niệm khác nhau.
- **Chuẩn hóa là quyết định ngữ nghĩa:** nếu một tọa độ có thang đo lớn hơn hẳn, nó có thể chi phối khoảng cách. Việc chuẩn hóa có thể thay đổi chính thứ tự hàng xóm gần nhất.
- **Số điểm cũng quan trọng:** khoảng cách tới hàng xóm gần nhất còn chịu ảnh hưởng của $n$, không thể chỉ suy ra từ $d$.

Ví dụ thực tế: dữ liệu ảnh có nhiều đặc trưng nhưng các vector nằm gần vài cụm hoặc một đa tạp (*manifold*) có số chiều nội tại thấp. Khi đó, thuật toán khai thác cấu trúc phân bố vẫn có thể làm việc tốt hơn so với trường hợp các tọa độ độc lập, phân bố đều.

## 4. Vì sao chỉ mục không gian nhanh? Nhờ loại bỏ vùng

Mấu chốt của cây chỉ mục không gian là **tỉa nhánh** (*pruning*): không thăm những nhánh chắc chắn không chứa đáp án.

Với truy vấn khoảng, mỗi nút có thể chứa một **hộp bao** (*bounding box*) của các điểm phía dưới. Nếu hộp bao không giao vùng truy vấn, ta bỏ qua toàn bộ nhánh.

Với truy vấn hàng xóm gần nhất, một nút được gắn vùng $B$ cho phép tính cận dưới:

$$
LB(q,B)\le \min_{p\in B}\operatorname{dist}(q,p).
$$

Nếu ta đã biết điểm tốt nhất có khoảng cách $D$ và $LB(q,B)>D$, không điểm nào trong vùng có thể tốt hơn; toàn bộ nhánh có thể bị bỏ qua. Với khoảng cách Euclid bình phương và hộp trục song song $B=[\ell_1,u_1]\times\cdots\times[\ell_d,u_d]$, cận dưới có thể tính bằng:

$$
LB_2(q,B)=\sum_{i=1}^{d}
\begin{cases}
(\ell_i-q_i)^2,&q_i<\ell_i,\\
(q_i-u_i)^2,&q_i>u_i,\\
0,&\ell_i\le q_i\le u_i.
\end{cases}
$$

Giá trị này là **cận dưới của bình phương khoảng cách**. Khi truy vấn nằm bên trong hộp, cận dưới bằng 0 cho dù không có điểm dữ liệu nào thực sự gần truy vấn. Hộp bao rộng hoặc chồng lấn khiến rất nhiều cận dưới trở nên yếu.

Giả mã sau minh họa tìm **một** hàng xóm gần nhất chính xác bằng cây có hộp bao:

```text
nearest(node, query, best):
    nếu node là rỗng:
        trả_về best

    nếu lower_bound_squared(query, node.box) > best.distance_squared:
        trả_về best             // Nhánh chắc chắn không có điểm tốt hơn

    nếu node là lá:
        cho mỗi point trong node.points:
            d2 = squared_distance(query, point)
            nếu d2 < best.distance_squared:
                best = (point, d2)
        trả_về best

    // Thăm nhánh triển vọng trước để sớm có cận trên tốt.
    children = sort_by_lower_bound(node.children, query)
    cho mỗi child trong children:
        best = nearest(child, query, best)
    trả_về best
```

Khởi tạo `best.distance_squared = +infinity`. Dấu `>` giữ lại những điểm đồng hạng; nếu chỉ cần một đáp án bất kỳ khi hòa, chính sách tỉa nhánh có thể khác. Mã này là **mẫu tư duy**, không phải một cài đặt KD-tree/R-tree hoàn chỉnh.

Điểm quan trọng: cây chỉ nhanh khi **nhiều nhánh bị bỏ qua**. Nếu phần lớn các hộp bao vẫn giao truy vấn hoặc có cận dưới không đủ mạnh, nó có thể phải duyệt gần toàn bộ tập điểm và trả thêm chi phí đi qua cây.

## 5. Giới hạn của các cấu trúc không gian quen thuộc

### 5.1. KD-tree

**KD-tree** chia tập điểm bằng mặt phẳng vuông góc với một trục tọa độ. Chẳng hạn nút gốc tách theo $x$, nút kế tiếp theo $y$, sau đó theo các trục khác; cách chọn trục và điểm chia tùy thuật toán.

Với các giả định thích hợp, cây tĩnh phân chia cân bằng có chiều cao $O(\log n)$ và dùng $O(n)$ nút. **Chiều cao nhỏ không đồng nghĩa truy vấn NN mất $O(\log n)$**: khi không thể loại bỏ các vùng đối diện mặt phẳng chia, thuật toán phải quay lui và duyệt nhiều nhánh.

Đối với KD-tree cân bằng tĩnh có phép chia trục thông thường, trong mô hình phân tích cổ điển với **số chiều cố định**, truy vấn hộp chữ nhật trực giao có thể đạt chặn trên cỡ:

$$
O\!\left(n^{1-1/d}+m\right),
$$

với $m$ là số điểm được báo cáo (giả sử $d\ge2$ và các điều kiện của cây cân bằng đó). Khi $d$ tăng, số mũ $1-1/d$ tiến dần tới 1. Kết quả này **không** phải bảo đảm cho mọi biến thể KD-tree, mọi kiểu truy vấn hoặc mọi cấu hình dữ liệu. Với **NN chính xác**, thời gian trường hợp xấu nhất có thể vẫn là $\Theta(n)$ lượt xét điểm, tương ứng tới $O(nd)$ phép toán tọa độ nếu mỗi khoảng cách tốn $O(d)$.

KD-tree rất hữu ích trong nhiều bài toán 2D/3D hoặc số chiều vừa phải, đặc biệt khi dữ liệu có khả năng phân tách tốt. Ở số chiều lớn, mặt phẳng chia theo từng tọa độ có thể không đủ để tách được các điểm “gần” theo khoảng cách toàn cục.

### 5.2. Quadtree, octree và lưới

Quadtree thường chia một vùng 2D thành 4 phần; octree chia vùng 3D thành 8 phần. Khi khái quát chia đôi trên **mọi** trục, một nút có thể có tới $2^d$ ô con: 4 ở 2D, 8 ở 3D nhưng 1024 ở 10D.

Triển khai thưa chỉ tạo ô có dữ liệu có thể tiết kiệm nhiều bộ nhớ; vẫn có thể gặp nhiều ô cần thăm ở truy vấn lân cận. Các kiểu chia không gian khác có thể giảm số nhánh trên mỗi nút nhưng không loại bỏ được khó khăn hình học do số chiều tăng.

### 5.3. R-tree

**R-tree** nhóm các đối tượng trong những **minimum bounding rectangles** (MBR), thường rất hữu ích cho dữ liệu địa lý 2D, đa giác và truy vấn giao cắt. Nó còn được thiết kế phù hợp với lưu trữ theo trang, để giảm số lần truy cập đĩa trong những tình huống thuận lợi.

Nếu các MBR của những nhánh anh em **chồng lấn nhiều**, truy vấn giao với nhiều MBR phải đi sâu vào nhiều nhánh. Khi số chiều và độ phủ hộp tăng, việc dùng MBR để lọc có thể kém phân biệt; hiệu quả còn phụ thuộc phân phối điểm, chiến lược tách nút, kích thước trang và dạng truy vấn. Không có bảo đảm phổ quát rằng truy vấn R-tree luôn chỉ thăm $O(\log n)$ nút.

### 5.4. Ball tree và các chỉ mục theo metric

**Ball tree** bao điểm bằng các quả cầu, còn **vantage-point tree** và các chỉ mục metric khác dựa trên khoảng cách và bất đẳng thức tam giác. Chúng có thể thích hợp khi ranh giới hình cầu hoặc cấu trúc khoảng cách mô tả dữ liệu tốt hơn hộp theo trục.

Ví dụ, nếu mọi điểm trong một cụm nằm trong bán kính $r$ quanh tâm $c$, thì:

$$
\operatorname{dist}(q,p)\ge
\max\{0,\operatorname{dist}(q,c)-r\}.
$$

Đây là cận dưới hợp lệ khi `dist` là **metric** thỏa bất đẳng thức tam giác. Tuy nhiên, nếu cận dưới quá nhỏ hoặc các quả cầu chồng lấn nhiều, cây vẫn phải thăm nhiều cụm. Những công thức tỉa nhánh của metric tree không được áp dụng máy móc cho một hàm tương tự **không thỏa bất đẳng thức tam giác**.

## 6. “Số chiều biểu diễn” khác “số chiều nội tại”

**Số chiều biểu diễn** (*ambient dimension*) là số tọa độ lưu trên mỗi vector, ví dụ $d=768$. **Số chiều nội tại** (*intrinsic dimension*) mô tả mức độ tự do thực sự cần để giải thích hình dạng hoặc phân bố dữ liệu.

Ví dụ, nhiều điểm có dạng $(t,2t,3t,\ldots,768t)$ được lưu trong không gian 768D, nhưng đều nằm trên một đường thẳng được xác định bởi một tham số $t$. Với thước đo thích hợp, bài toán có thể đơn giản gần giống tìm kiếm trên một chiều.

Ngược lại, bộ dữ liệu mà tọa độ biến thiên gần độc lập trên nhiều trục thường khó phân tách hơn. Do đó, chỉ nhìn cột “vector length” không đủ dự đoán chất lượng chỉ mục.

Những cách giảm hoặc khai thác chiều gồm:

- **Loại đặc trưng dư thừa:** bỏ những tọa độ trùng lặp hoặc ít giá trị cho khoảng cách nghiệp vụ.
- **PCA, phép chiếu, embedding học được:** tạo biểu diễn gọn hơn để tìm kiếm.
- **Chọn thước đo hợp lý:** Euclid cho các tọa độ có ý nghĩa hình học; cosine similarity hoặc khoảng cách góc có thể thích hợp với nhiều embedding đã chuẩn hóa.
- **Khai thác cụm hoặc phân bố dữ liệu:** chỉ mục có thể hiệu quả nếu điểm nằm trong các vùng có cấu trúc.

Cần thận trọng: giảm chiều **có thể thay đổi thứ tự hàng xóm**. Nếu tìm ứng viên trên không gian đã chiếu rồi tính lại khoảng cách gốc cho ứng viên, kết quả cuối vẫn chỉ bảo đảm **chính xác trong tập ứng viên đó**; nó chưa chắc là hàng xóm gần nhất trên toàn bộ dữ liệu gốc.

## 7. Quét toàn bộ đôi khi là lựa chọn tốt

Để tìm một hàng xóm gần nhất theo Euclid một cách chính xác, cách cơ sở là quét qua toàn bộ $n$ điểm và giữ điểm có bình phương khoảng cách nhỏ nhất:

```python
def nearest_exact(points, query):
    """points: iterable các vector, query: vector cùng số chiều."""
    best_point = None
    best_d2 = float("inf")
    for point in points:
        if len(point) != len(query):
            raise ValueError("Các vector phải có cùng số chiều")
        d2 = sum((x - y) ** 2 for x, y in zip(point, query))
        if d2 < best_d2:
            best_d2 = d2
            best_point = point
    return best_point, best_d2
```

Thuật toán cần $O(nd)$ phép tính tọa độ, ngoài bộ nhớ chứa dữ liệu và một lượng bộ nhớ phụ $O(1)$ cho kết quả, nếu mỗi vector được đọc tuần tự và không cần sao chép. Với $k$-NN, có thể giữ một heap tối đa kích thước $k$: chi phí thường là $O(nd+n\log k)$, với giả định so sánh khoảng cách đã tính tốn $O(1)$.

Quét tuần tự có ưu điểm: dễ chứng minh đúng, dữ liệu có thể nằm liên tục trong bộ nhớ, thuận lợi cho vectorization/SIMD hoặc xử lý theo lô. Một cây phải thăm gần hết các điểm **cộng thêm** chi phí duyệt nút có thể chậm hơn quét toàn bộ. Vì thế, brute force là mốc so sánh cần có khi thử một chỉ mục.

Ngoài thời gian, số chiều còn tăng **chi phí lưu trữ thô**. Với một triệu vector lưu bằng `float32` (4 byte/tọa độ), chỉ riêng tọa độ cần:

| Số chiều | Bộ nhớ thô cho 1 triệu vector |
|---:|---:|
| 2 | 8 MB |
| 128 | 512 MB |
| 768 | 3,072 GB (khoảng 2,86 GiB) |

Ở đây dấu phẩy trong “3,072 GB” là dấu thập phân: khoảng **3,072 tỷ byte**, chưa kể định danh, cấu trúc chỉ mục, metadata và dữ liệu tạm. Nếu dùng R-tree, graph hay cấu trúc bổ trợ, ngân sách bộ nhớ còn tăng thêm.

## 8. Tìm kiếm gần đúng: đổi bảo đảm để lấy tốc độ

Khi $d$ lớn, $n$ rất lớn và ứng dụng cho phép một mức sai lệch, có thể dùng **approximate nearest neighbor (ANN)**. Mục tiêu là tìm điểm đủ gần trong thời gian và bộ nhớ chấp nhận được, thay vì luôn bảo đảm tìm đúng hàng xóm gần nhất toàn cục.

| Hướng tiếp cận | Ý tưởng | Đánh đổi |
|---|---|---|
| **HNSW và chỉ mục dựa trên đồ thị** | Đi theo các cạnh lân cận để đến các điểm ngày càng gần truy vấn | Chất lượng phụ thuộc xây dựng đồ thị, tham số tìm kiếm và dữ liệu; tốn bộ nhớ cho cạnh |
| **IVF / phân cụm trước** | Chia điểm thành các danh sách/cụm, truy vấn một số cụm triển vọng | Có thể bỏ qua cụm chứa đáp án chính xác |
| **Product quantization (PQ)** | Nén vector bằng các mã ngắn, so sánh khoảng cách xấp xỉ | Giảm bộ nhớ nhưng thêm sai số lượng tử hóa |
| **LSH (locality-sensitive hashing)** | Xây các hàm băm khiến điểm gần có xác suất chung bucket cao hơn trong thiết kế phù hợp | Chất lượng/phí bộ nhớ phụ thuộc họ hàm băm, số bảng và thước đo |

Một thiết kế phổ biến là **truy xuất ứng viên gần đúng → tính lại khoảng cách gốc → xếp hạng ứng viên**. Việc xếp hạng lại có thể cải thiện chất lượng, nhưng **không khôi phục bảo đảm tìm kiếm chính xác** nếu đáp án thật chưa từng lọt vào tập ứng viên.

Chất lượng của ANN thường được đo bằng **recall@$k$**:

$$
\operatorname{recall}@k
=\frac{|\text{Top-}k_{\mathrm{ANN}}\cap\text{Top-}k_{\mathrm{exact}}|}{k}.
$$

Để so sánh đúng, cùng một thước đo khoảng cách phải được dùng cho kết quả gần đúng và “đáp án chuẩn” chính xác. Khi có nhiều điểm đồng hạng, cần định nghĩa cách xử lý các vị trí hòa để chỉ số đánh giá nhất quán.

Các chỉ mục ANN không cung cấp cùng một bảo đảm thời gian **trường hợp xấu nhất** cho mọi dữ liệu. Hiệu năng phải được đo theo kích thước tập điểm, phân phối truy vấn, tham số, yêu cầu độ chính xác và tần suất thêm/xóa/cập nhật.

## 9. Bảng lựa chọn theo chiều, truy vấn và bảo đảm

| Bối cảnh | Ứng viên hợp lý để thử | Cần kiểm tra |
|---|---|---|
| Dữ liệu địa lý 2D/3D, truy vấn vùng | R-tree, quadtree, KD-tree, chỉ mục không gian của hệ quản trị | Hệ tọa độ, hình học đối tượng, số trang truy cập |
| Điểm 2D/3D, NN chính xác, cập nhật ít | KD-tree hoặc ball tree | Số nhánh bị tỉa, phân phối điểm, chi phí xây dựng |
| Miền lưới nhỏ và thưa vừa phải | Spatial hash hoặc lưới thưa | Chọn cỡ ô, số ô cần tìm lân cận |
| Vector nhiều chiều nhưng có cụm/chiều nội tại thấp | KD/ball tree, chỉ mục chuyên dụng sau khi thử nghiệm | Tỷ lệ nhánh bị tỉa và độ chính xác theo metric |
| Vector nhiều chiều, bắt buộc NN chính xác | Quét tuần tự tối ưu hóa; thử cây nếu có cấu trúc phân bố | Thời gian $O(nd)$, mức tăng tốc thực tế |
| Vector nhiều chiều, chấp nhận kết quả gần đúng | HNSW, IVF/PQ, LSH hoặc ANN phù hợp | Recall@$k$, p95/p99 latency, bộ nhớ và tốc độ cập nhật |
| Dữ liệu thay đổi liên tục | Chỉ mục hỗ trợ cập nhật hoặc kết hợp tầng mới/cũ | Chi phí rebuild, xóa, tombstone, độ mới kết quả |

Không có ranh giới cứng kiểu “dưới 20 chiều dùng KD-tree, trên 20 chiều bắt buộc dùng ANN”. Một tập 64D có thể dễ tìm nếu các điểm nằm trên vài đường cong, trong khi một tập 8D gần phân bố đều có thể khó tỉa nhánh. Lựa chọn cần dựa trên **phân phối dữ liệu và hợp đồng truy vấn**.

## 10. Đánh giá chỉ mục bằng thử nghiệm có kiểm soát

Để biết chỉ mục có thực sự tăng tốc hay không, hãy triển khai hoặc dùng một **baseline quét toàn bộ**, sau đó so sánh dưới cùng điều kiện:

1. **Xác định bài toán:** point lookup, range reporting, radius, NN hay $k$-NN; tìm chính xác hay chấp nhận xấp xỉ; chọn Euclid, Manhattan, cosine/angle hoặc metric khác.
2. **Ghi kích thước dữ liệu:** $n$, $d$, kiểu dữ liệu, kích thước vector, dữ liệu tĩnh hay thường xuyên cập nhật.
3. **Kiểm tra hình học:** tương quan giữa các tọa độ, mật độ, số cụm, mức độ lệch phân phối, ước lượng chiều nội tại, đặc điểm của truy vấn thực.
4. **Thử nhiều loại truy vấn:** truy vấn trong cụm đông, vùng thưa, ở biên, gần ngoại lệ, các mức bán kính và giá trị $k$ khác nhau.
5. **Đo việc tỉa nhánh:** số nút/hộp bao đã thăm, số điểm phải tính khoảng cách, tỷ lệ nhánh bị bỏ qua; so sánh với số phép tính của quét toàn bộ.
6. **Đo chi phí vận hành:** thời gian xây chỉ mục, thời gian thêm/xóa, bộ nhớ đỉnh, kích thước đĩa, mức tiêu thụ cache và thời gian làm mới.
7. **Đo chất lượng và độ trễ:** throughput, p50/p95/p99 latency; nếu ANN, đo recall@$k$ theo kết quả exact đã tính độc lập.

Đối với chỉ mục trong cơ sở dữ liệu, cần thêm **I/O theo trang**, số trang phải đọc, loại bộ lọc và các bước hậu kiểm hình học. Với truy vấn kết hợp “vector gần nhất và thuộc một danh mục nhất định”, **độ chọn lọc của bộ lọc** có thể quyết định nên lọc trước, tìm lân cận trước hay phối hợp cả hai.

Nếu chỉ thử trên dữ liệu ngẫu nhiên đơn giản rồi áp dụng vào dữ liệu thực có cụm, nhiều điểm trùng hoặc truy vấn lệch, kết quả có thể đánh lừa. Benchmark cần gồm dữ liệu và lịch sử truy vấn đại diện cho ứng dụng.

## 11. Những nhầm lẫn thường gặp

| Nhận định dễ sai | Cách hiểu đúng |
|---|---|
| “KD-tree cân bằng nên mọi truy vấn NN là $O(\log n)$.” | Chiều cao $O(\log n)$ không bảo đảm tỉa nhánh; NN chính xác có thể xét nhiều hoặc toàn bộ điểm. |
| “Một chỉ mục không gian luôn thắng quét tuyến tính.” | Nếu tỉa nhánh kém, chi phí duyệt chỉ mục và truy cập bộ nhớ rời rạc có thể làm nó chậm hơn. |
| “Cứ tăng số chiều thì khoảng cách nào cũng vô nghĩa.” | Tập trung khoảng cách phụ thuộc phân phối, metric và số điểm; dữ liệu có cấu trúc vẫn có hàng xóm hữu ích. |
| “Vector 768D chắc chắn có 768 chiều nội tại.” | Các tọa độ có thể tương quan mạnh hoặc nằm trên một đa tạp thấp chiều. |
| “R-tree luôn chỉ đọc vài trang.” | MBR chồng lấn khiến nhiều nhánh phải duyệt; hiệu năng còn phụ thuộc trang, phân bố và truy vấn. |
| “Nén hoặc chiếu vector rồi rerank vẫn là NN chính xác.” | Nếu bước chọn ứng viên bỏ sót đáp án, rerank chỉ đúng trong tập ứng viên, không bảo đảm exact toàn cục. |
| “Một chỉ số ANN rất nhanh nghĩa là chất lượng đủ tốt.” | Phải đo recall@$k$ hoặc tiêu chí nghiệp vụ cùng độ trễ, bộ nhớ và độ mới dữ liệu. |
| “Chọn ngưỡng số chiều cố định cho mọi loại dữ liệu.” | Khả năng tỉa nhánh còn tùy $n$, phân phối điểm, intrinsic dimension và loại truy vấn. |

## 12. Bài tập tự kiểm tra

**Câu 1.** Chia mỗi trục thành 10 khoảng. Cần bao nhiêu ô cho không gian 3D và 12D nếu dùng lưới đầy đủ?

**Đáp án:** $10^3=1\,000$ ô ở 3D và $10^{12}$ ô ở 12D. Số ô tăng theo hàm mũ của $d$, dù số điểm $n$ có thể không tăng.

**Câu 2.** Trong bộ dữ liệu gồm $n=1\,000\,000$ điểm độc lập đều ở 10D, cạnh một hộp truy vấn phải chiếm khoảng bao nhiêu phần mỗi trục để kỳ vọng có 10 điểm?

**Đáp án:** $a=(10/1\,000\,000)^{1/10}\approx0{,}316$, tức khoảng 31,6% độ dài mỗi trục, với các giả định của mô hình đều.

**Câu 3.** KD-tree đã tìm thấy điểm cách truy vấn 0,2. Một nút khác có cận dưới khoảng cách là 0,3. Có cần thăm nút đó không?

**Đáp án:** Không, vì mọi điểm trong nút đều cách truy vấn ít nhất 0,3, lớn hơn kết quả tốt nhất 0,2. Nếu cận dưới chỉ bằng 0,1, chưa đủ để tỉa nhánh.

**Câu 4.** Một chỉ mục ANN trả về 8 điểm trùng với top-10 chính xác trong 10 kết quả của nó. Recall@10 là bao nhiêu?

**Đáp án:** $8/10=0{,}8$, tức 80% cho truy vấn đó, giả sử không có vấn đề hòa khoảng cách.

**Câu 5.** Tại sao một tập vector 128 chiều nằm gần một đường cong có thể dễ tìm kiếm hơn tập 20 chiều có các tọa độ gần độc lập?

**Đáp án:** Vì chiều nội tại, phân bố và cấu trúc hình học quyết định hiệu quả phân nhóm và tỉa nhánh; 128 là số tọa độ lưu, không phải số chiều độc lập thực tế.

**Câu 6.** Khi nào nên ưu tiên quét toàn bộ thay vì tiếp tục tối ưu KD-tree?

**Đáp án:** Khi đo thực tế cho thấy cây phải thăm phần lớn điểm, quét tuần tự đạt độ trễ tốt hơn hoặc chi phí xây dựng/cập nhật chỉ mục không đáng với lượng truy vấn. Quét toàn bộ còn là cách tạo đáp án exact để đánh giá ANN.

Lời nguyền số chiều không khẳng định mọi tìm kiếm nhiều chiều đều chậm. Nó nhắc rằng **tốc độ của chỉ mục phụ thuộc khả năng loại bỏ ứng viên**, mà khả năng ấy có thể suy giảm mạnh khi miền không gian tăng, khoảng cách khó phân biệt và các vùng bao chồng lấn. Trước khi coi $O(\log n)$ là hiệu năng mặc định, hãy xác định số chiều, phân phối dữ liệu, loại truy vấn, metric, mức chính xác cần có, rồi đo số nhánh thực sự bị loại và so sánh với một baseline quét toàn bộ.
