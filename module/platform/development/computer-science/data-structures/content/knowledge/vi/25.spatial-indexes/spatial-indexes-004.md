# Cây k-d và lựa chọn trục chia

Một tập điểm hai chiều có thể được sắp theo trục \(x\), nhưng truy vấn “điểm nào nằm trong hình chữ nhật này?” còn phụ thuộc trục \(y\). **Cây k-d** (*k-dimensional tree*, viết tắt **k-d tree**) giải quyết bài toán bằng cách chia tập điểm nhiều chiều qua các mặt phẳng vuông góc với từng trục tọa độ. Mỗi lần đi xuống cây, ta thu hẹp miền tìm kiếm theo một điều kiện tọa độ.

Điểm cần hiểu không chỉ là cách cây tìm kiếm, mà còn là **chọn trục nào để chia**. Chia luân phiên \(x,y,z,\ldots\) dễ cài đặt, còn chọn trục có độ trải rộng lớn nhất có thể tạo những phân hoạch phù hợp hơn với dữ liệu lệch. Dùng trung vị giúp cây cân theo **số điểm**, trong khi dùng trung điểm miền có thể cân theo **không gian hình học** nhưng không cân theo số bản ghi.

Bài học thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, tập trung vào bất biến, thao tác và độ phức tạp của cấu trúc dữ liệu. Ta sẽ xây dựng k-d tree trong \(d\) chiều, so sánh chiến lược trục chia, tìm kiếm phạm vi và láng giềng gần nhất, phân tích cập nhật/xóa và giới hạn khi số chiều lớn. Cuối bài có mã Python cho cây tĩnh với hộp bao ở mỗi nút.

> **Nguyên tắc cốt lõi:** K-d tree phân chia **các điểm theo tọa độ**, còn AABB ở mỗi nút là công cụ để cắt tỉa. Chọn trục và điểm chia ảnh hưởng mạnh tới hiệu năng; nhưng mọi lựa chọn phải giữ bất biến phân hoạch và hộp bao chứa đủ điểm của cây con.

## 1. Vì sao cần cây k-d?

Cho tập \(P\) gồm \(n\) điểm trong không gian \(d\) chiều:

\[
P=\{p^{(1)},p^{(2)},\ldots,p^{(n)}\},\qquad
p=(p_1,\ldots,p_d).
\]

Một truy vấn phạm vi hình chữ nhật/hộp:

\[
Q=\prod_{i=1}^{d}[a_i,b_i]
\]

cần tìm:

\[
\boxed{R(Q)=\{p\in P:\forall i,\ a_i\le p_i\le b_i\}.}
\]

Nếu không có chỉ mục, ta phải kiểm tra tất cả \(n\) điểm; với \(d\) chiều, chi phí là \(O(nd)\), thường ghi \(O(n)\) khi \(d\) cố định.

K-d tree tổ chức điểm thành các nhánh theo từng trục. Nếu một nhánh chắc chắn nằm ngoài Q, ta bỏ **cả nhánh** mà không kiểm tra từng điểm.

Các ứng dụng:

- Tìm vị trí lân cận trong bản đồ phẳng đã chiếu phù hợp.
- Tìm đối tượng gần người chơi hoặc cảm biến trong game/mô phỏng.
- Truy vấn vector ít chiều theo nhiều điều kiện tọa độ.
- Tìm láng giềng gần nhất trong point cloud hoặc dữ liệu hình học.
- Lọc điểm ứng viên cho bước kiểm tra hình học chi tiết.

**K-d tree không phải cấu trúc tối ưu cho mọi số chiều.** Khi \(d\) cao, nhiều nhánh có thể cùng gần truy vấn và hiệu quả cắt tỉa giảm mạnh.

## 2. Ý tưởng chia bằng siêu phẳng

Trong 2D, một nút chọn một trục:

- Trục \(x\): chia mặt phẳng bằng đường thẳng đứng \(x=s\).
- Trục \(y\): chia bằng đường thẳng ngang \(y=s\).

Trong \(d\) chiều, mặt phân chia là **siêu phẳng** vuông góc với trục \(j\):

\[
\boxed{p_j=s.}
\]

Mỗi nút chứa một điểm phân chia \(v\), trục \(j\), cùng cây con trái/phải:

- Trái: các điểm có tọa độ trục \(j\) **nhỏ hơn** ngưỡng.
- Phải: các điểm có tọa độ trục \(j\) **lớn hơn hoặc bằng** ngưỡng.

Một quy tắc phổ biến dùng:

\[
P_{\mathrm{left}}=\{p:p_j<s\},\qquad
P_{\mathrm{right}}=\{p:p_j\ge s\}.
\]

Đây là **quy ước trái nghiêm ngặt/phải bao gồm bằng**. Một triển khai khác có thể dùng tie-break theo ID; điều quan trọng là **chọn một quy tắc nhất quán** khi xây cây và tìm kiếm.

~~~text
                    trục x
                       ^
          điểm trái    |    điểm phải
             o  o      |      o
                 o     |   o
       -----------+----|----+----------> trục y
                  |    |
                  | x=s|
                  |    |

Mặt chia x=s tách các điểm theo tọa độ x.
Trong 2D, mặt chia là đường thẳng; trong 3D là mặt phẳng.
~~~

### Không phải mỗi nút đều chia theo cùng một trục

K-d tree thường thay đổi trục theo độ sâu hoặc chọn trục theo thống kê của tập điểm ở nút. Vì vậy đường đi trong cây có thể dùng:

~~~text
depth 0: split x
depth 1: split y
depth 2: split x
depth 3: split y
...
~~~

Trong 3D, một chu kỳ có thể là \(x,y,z,x,y,z,\ldots\). Nhưng đây chỉ là **một chính sách chọn trục**, không phải định nghĩa duy nhất của k-d tree.

## 3. Bất biến phân hoạch và xử lý điểm bằng nhau

Để tìm kiếm đúng, mỗi nút phải giữ một quy tắc nhất quán về những điểm nằm ở mỗi phía của mặt chia.

Giả sử nút \(v\) chọn trục \(j\), giá trị chia \(s\):

\[
\boxed{
\forall p\in P_{\mathrm{left}}:\ p_j<s,\qquad
\forall p\in P_{\mathrm{right}}:\ p_j\ge s.
}
\]

Với mọi điểm trong cây con, các điều kiện phân hoạch của **tất cả tổ tiên trên đường đi** đều phải được thỏa mãn.

### Vì sao cần tie-break?

Giả sử 10.000 điểm có cùng tọa độ \(x=5\). Nếu quy tắc trái là \(x<5\), không điểm nào đi trái; toàn bộ điểm rơi vào phải. Cây có thể mất cân bằng dù số điểm lớn.

Một lựa chọn là dùng **khóa tổng hợp**:

\[
\boxed{K_j(p)=(p_j,\operatorname{id}(p))}
\]

và so sánh theo thứ tự từ điển. Khi đó:

- Trái: \(K_j(p)<K_j(v)\).
- Phải: \(K_j(p)\ge K_j(v)\).

ID phải **duy nhất và có thứ tự ổn định**. Cách này phân tách được các điểm cùng tọa độ theo ID, nhưng lưu ý rằng **mặt hình học \(p_j=s\) có thể xuất hiện ở cả hai nhánh**. Vì vậy không được cắt tỉa bằng giả định trái luôn có \(p_j<s\) nếu tie-break cho phép điểm bằng tọa độ nằm ở trái.

Một lựa chọn khác là giữ các điểm cùng tọa độ chia trong **bucket** tại nút hoặc lá. Điều này đơn giản hơn về hình học nhưng bucket có thể lớn khi nhiều ID trùng tọa độ.

### Tách hai khái niệm: tọa độ và danh tính

Hai bản ghi có thể:

~~~text
ID A -> (5, 7)
ID B -> (5, 7)
~~~

Chúng là **hai đối tượng khác nhau** dù cùng tọa độ. Nếu ứng dụng cần trả cả hai, không được loại một bản ghi chỉ vì tọa độ trùng.

Trong bài này, mã Python sẽ dùng **ID duy nhất**, khóa phân hoạch là \((tọa\ độ\ trên\ trục,\ ID)\) để cây có thể cân theo số bản ghi ngay cả khi nhiều tọa độ giống nhau. Truy vấn hình học vẫn kiểm tra **tọa độ**, không dùng ID để quyết định điểm có thuộc vùng không gian hay không.

## 4. Chọn trục chia: luân phiên, độ trải rộng và phương sai

Trục chia quyết định hình dạng vùng và cách phân phối dữ liệu. Có ba chiến lược phổ biến.

### 4.1. Luân phiên theo độ sâu (*cyclic axis*)

Với \(d\) chiều, ở độ sâu \(h\):

\[
\boxed{axis=h\bmod d.}
\]

Ví dụ 2D: \(x,y,x,y,\ldots\); 3D: \(x,y,z,x,y,z,\ldots\).

**Ưu điểm:** đơn giản, dễ cài đặt, chi phí chọn trục \(O(1)\), không cần quét dữ liệu để tính thống kê.

**Nhược điểm:** có thể chia theo một chiều gần như không thay đổi, trong khi chiều khác trải rất rộng. Cây vẫn cân theo số điểm nếu chọn trung vị, nhưng **vùng hình học** có thể kéo dài hoặc kém phù hợp.

### 4.2. Trục có độ trải rộng lớn nhất (*widest spread*)

Với tập điểm tại nút \(S\), tính độ trải rộng mỗi chiều:

\[
spread_i=\max_{p\in S}p_i-\min_{p\in S}p_i.
\]

Chọn:

\[
\boxed{axis=\arg\max_i spread_i.}
\]

Nếu hai chiều có cùng spread, cần quy tắc phá hòa ổn định, chẳng hạn chọn **index trục nhỏ hơn**.

**Ưu điểm:** ưu tiên chia theo chiều có phạm vi tọa độ rộng nhất; thường giúp giảm những vùng quá kéo dài.

**Nhược điểm:** cần quét tập điểm để tính min/max trên mỗi chiều, tốn \(O(nd)\) cho một nút chứa \(n\) điểm. Khi lặp ở nhiều cấp, tổng chi phí xây tăng; phải cân nhắc số chiều và kích thước dữ liệu.

### 4.3. Trục có phương sai lớn nhất (*maximum variance*)

Tính trung bình:

\[
\mu_i=\frac1n\sum_{p\in S}p_i
\]

và phương sai:

\[
\boxed{\sigma_i^2=
\frac1n\sum_{p\in S}(p_i-\mu_i)^2.}
\]

Chọn chiều có \(\sigma_i^2\) lớn nhất.

**Khác với spread:** spread chỉ phụ thuộc hai điểm cực trị; phương sai phản ánh **toàn bộ phân bố**. Một outlier rất xa có thể làm spread lớn nhưng phương sai vẫn tùy phần còn lại.

**Nhược điểm:** phải tính thống kê trên dữ liệu tại mỗi nút; phương sai lớn không tự bảo đảm một phép chia cụ thể cân bằng số điểm.

### Bảng so sánh

| Chiến lược | Chi phí chọn trục tại nút \(m\) điểm, \(d\) chiều | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| Luân phiên | \(O(1)\) | Rẻ, ổn định | Có thể chọn chiều ít thông tin |
| Spread lớn nhất | \(O(md)\) | Nhìn vào phạm vi hình học | Nhạy với outlier |
| Phương sai lớn nhất | \(O(md)\) | Nhìn vào phân tán tổng thể | Tốn thống kê, không bảo đảm cân |

**Chọn trục và chọn điểm chia là hai quyết định khác nhau.** Sau khi chọn trục, ta vẫn cần quyết định dùng trung vị, trung điểm miền hay một giá trị khác làm ngưỡng.

## 5. Chọn giá trị chia: median hay midpoint?

Giả sử đã chọn trục \(j\). Có hai chiến lược dễ nhầm:

### Median split — chia theo trung vị của dữ liệu

Sắp điểm theo khóa:

\[
(p_j,\operatorname{id}(p))
\]

rồi chọn phần tử ở giữa làm pivot. Hai tập trái/phải có số điểm gần bằng nhau:

\[
|P_{\mathrm{left}}|\approx|P_{\mathrm{right}}|\approx n/2.
\]

Nếu lặp theo trung vị, chiều cao cây có xu hướng \(O(\log n)\) theo **số lượng nút**, kể cả khi tọa độ phân bố không đều.

### Midpoint split — chia tại trung điểm miền

Nếu vùng hiện tại có cận \(lo_j,hi_j\), chọn:

\[
s=\frac{lo_j+hi_j}{2}.
\]

Phân hoạch theo **không gian**, không theo số lượng điểm. Một phía có thể nhận 99% điểm, phía còn lại chỉ 1%, thậm chí rỗng.

### So sánh

| Tiêu chí | Median | Midpoint miền |
| --- | --- | --- |
| Cân bằng số điểm | Thường tốt nếu có tie-break | Không bảo đảm |
| Phù hợp phân vùng không gian | Có thể lệch hình học | Phản ánh trung điểm vùng |
| Điểm trùng tọa độ | Cần tie-break/bucket | Có thể dồn hết một phía |
| Xây cây tĩnh | Thường dùng để giữ chiều cao | Có thể sinh nhánh lệch |
| Phân hoạch cố định theo miền | Ngưỡng phụ thuộc dữ liệu | Ngưỡng phụ thuộc vùng |

**K-d tree cân theo median** thường phù hợp cho tập điểm tĩnh và truy vấn NN/range. **Midpoint split** có thể phù hợp khi cần phân vùng miền ổn định, nhưng nếu mục tiêu là cây cân theo số điểm thì phải kiểm tra phân bố.

## 6. Cách chọn trục ảnh hưởng thế nào tới hình học?

Cho tập điểm:

\[
P=\{(0,0),(1,0),(2,0),(3,0),(4,0),(5,0),(6,0)\}.
\]

Tất cả điểm có cùng \(y=0\), còn x trải rộng từ 0 đến 6.

- **Cyclic axis tại gốc** chọn x nếu depth=0: có thông tin để chia.
- Nếu gốc bắt đầu bằng y: spread của y bằng 0, mọi điểm có cùng tọa độ trên trục chia; chỉ tie-break ID mới có thể tách số lượng.
- **Widest spread** chọn x vì \(spread_x=6\), \(spread_y=0\).
- **Maximum variance** cũng chọn x vì phương sai y bằng 0, còn x dương.

Đây là ví dụ cho thấy lựa chọn trục có thể tránh một phép chia hình học không mang lại thông tin.

### Outlier và khác biệt spread/variance

Cho các giá trị trên trục x:

\[
0,\ 1,\ 1,\ 1,\ 1,\ 1,\ 100.
\]

Spread là 100 do outlier 100. Phương sai cũng tăng bởi outlier, nhưng nếu một chiều khác có nhiều giá trị phân tán vừa phải, việc chọn trục theo phương sai và theo spread có thể khác nhau tùy dữ liệu. Vì vậy **không có chiến lược trục tốt nhất cho mọi tập điểm**.

### Tọa độ có đơn vị khác nhau

Nếu vector gồm \((x,y,t)\) với x/y tính bằng mét còn t tính bằng mili giây, spread hoặc phương sai thô có thể bị chi phối bởi **đơn vị đo**, không phải tầm quan trọng của chiều. Muốn so sánh các trục theo ý nghĩa nghiệp vụ, phải chuẩn hóa hoặc định nghĩa metric và quy tắc chia phù hợp.

## 7. Xây cây tĩnh bằng median

Một cách xây k-d tree cân đối cho tập điểm tĩnh:

1. Nhận tập điểm tại nút hiện tại.
2. Chọn trục chia theo chính sách.
3. Sắp theo \((tọa độ\ trên\ trục, ID)\).
4. Chọn phần tử trung vị làm pivot.
5. Đệ quy xây cây trái và phải từ hai nửa còn lại.
6. Tính hộp bao AABB chứa pivot và tất cả điểm trong hai cây con.

~~~text
BUILD(points, depth):
    nếu points rỗng: return null

    axis = choose_axis(points, depth)
    ordered = sort(points, key=(coordinate[axis], ID))
    mid = floor(length(ordered) / 2)
    pivot = ordered[mid]

    left  = BUILD(ordered[0:mid], depth + 1)
    right = BUILD(ordered[mid+1:], depth + 1)

    bbox = envelope(pivot, bbox(left), bbox(right))
    return Node(pivot, axis, left, right, bbox)
~~~

### Vì sao chọn median giúp cây cân?

Vì mỗi lần tách gần một nửa số bản ghi sang mỗi phía, kích thước tập con giảm theo:

\[
n,\quad n/2,\quad n/4,\quad n/8,\ldots
\]

Số mức cho tới khi còn một điểm xấp xỉ:

\[
\boxed{h=\lfloor\log_2 n\rfloor}
\]

theo quy ước chiều sâu tối đa là số cạnh, với một số chênh lệch 1 tùy số nút và cách lấy trung vị. Nếu các ID duy nhất, tie-break giúp **phân chia cả khi mọi tọa độ trên trục giống nhau**.

### Hộp bao của cây con

Mỗi node có thể lưu:

\[
lo_i=\min\{p_i:p\text{ nằm trong cây con}\},
\qquad
hi_i=\max\{p_i:p\text{ nằm trong cây con}\}.
\]

Hộp:

\[
\boxed{B(node)=\prod_{i=1}^{d}[lo_i,hi_i]}
\]

bao toàn bộ điểm trong cây con, kể cả pivot.

Để tính hộp khi xây:

- Khởi tạo \(lo=hi=pivot\).
- Với mỗi con, lấy min của các \(lo\) và max của các \(hi\).

Chi phí tính hộp từ hai con là \(O(d)\) mỗi node, nên tổng \(O(nd)\) cho toàn cây.

**Bất biến hộp bao:** Không một điểm nào trong cây con được nằm ngoài AABB của node. Nếu hộp bị tính thiếu, truy vấn có thể cắt nhánh sai và bỏ sót kết quả.

## 8. Truy vấn phạm vi bằng k-d tree

Với hộp truy vấn đóng:

\[
Q=\prod_{i=1}^{d}[a_i,b_i],\quad a_i\le b_i,
\]

điểm \(p\) thuộc Q khi:

\[
\boxed{\forall i,\ a_i\le p_i\le b_i.}
\]

### Cách 1 — Dựa vào mặt chia

Tại nút chia theo trục \(j\) tại \(s\):

- Nếu \(b_j<s\), vùng truy vấn nằm hoàn toàn bên trái; chỉ đi trái.
- Nếu \(a_j>s\), vùng truy vấn nằm hoàn toàn bên phải; chỉ đi phải.
- Nếu Q cắt mặt chia, có thể cần đi cả hai nhánh.

Điều kiện phụ thuộc chính xác vào quy tắc phân hoạch và tie-break. Nếu dùng khóa tổng hợp \((p_j,ID)\), các điểm bằng s có thể phân tán giữa hai nhánh. Vì vậy **khi Q chứa s ở biên đóng** (kể cả \(a_j=s\) hoặc \(b_j=s\)), phải xem cả hai nhánh có thể chứa điểm trên mặt đó. Chỉ khi \(a_j>s\) mới chắc chắn có thể bỏ nhánh trái; chỉ khi \(b_j<s\) mới chắc chắn có thể bỏ nhánh phải.

### Cách 2 — Dựa vào AABB cây con

Nếu AABB của một node **không giao Q**, ta bỏ cả node:

\[
\boxed{B(node)\cap Q=\varnothing
\implies\text{không điểm nào trong cây con thuộc Q}.}
\]

Với hai hộp đóng \(A,B\), chúng không giao nếu tồn tại trục \(i\) sao cho:

\[
A.hi_i<B.lo_i\quad\lor\quad B.hi_i<A.lo_i.
\]

Nếu hộp giao, kiểm tra pivot rồi đệ quy xuống các con. Hộp bao là một **cận bảo thủ**, có thể tạo ứng viên dư nhưng không được bỏ nhánh có điểm hợp lệ.

### Mã giả

~~~text
RANGE(node, Q):
    nếu node == null: return
    nếu bbox(node) không giao Q: return

    nếu pivot(node) thuộc Q:
        thêm pivot vào kết quả

    RANGE(node.left, Q)
    RANGE(node.right, Q)
~~~

### Độ phức tạp

Đặt \(V\) là số node được thăm và \(k\) là số kết quả:

\[
\boxed{T_{\mathrm{range}}=O(dV+k).}
\]

Với \(d\) cố định, thường ghi \(O(V+k)\). Trường hợp tốt, các AABB loại được nhiều nhánh. Trường hợp xấu, Q rộng hoặc các hộp con chồng lấp nhiều có thể khiến \(V=\Theta(n)\).

Độ phức tạp trên giả định **không yêu cầu thứ tự đầu ra**. Hàm Python ở mục 12 sắp kết quả theo ID để dễ kiểm thử, nên thêm \(O(k\log k)\) cho bước sắp xếp.

**Không khẳng định mọi truy vấn range là \(O(\log n+k)\).** K-d tree hỗ trợ cắt tỉa theo cấu trúc, nhưng hiệu quả phụ thuộc hình dạng vùng, cách chia và phân bố điểm.

## 9. Nearest neighbor: tìm điểm gần nhất chính xác

Với điểm truy vấn \(q\), nearest neighbor theo metric Euclid:

\[
\boxed{p^*=\arg\min_{p\in P}D_2(p,q).}
\]

Ta có thể so sánh bình phương khoảng cách:

\[
D_2^2(p,q)=\sum_{i=1}^{d}(p_i-q_i)^2,
\]

không cần tính căn bậc hai.

### Cận dưới khoảng cách từ q tới AABB

Với hộp đóng \(B=[lo,hi]\), đặt:

\[
\delta_i=
\begin{cases}
lo_i-q_i,&q_i<lo_i,\\
0,&lo_i\le q_i\le hi_i,\\
q_i-hi_i,&q_i>hi_i.
\end{cases}
\]

Khi đó:

\[
\boxed{minDist^2(q,B)=\sum_{i=1}^{d}\delta_i^2.}
\]

Đây là **cận dưới** của bình phương khoảng cách từ q tới mọi điểm nằm trong B. Nếu node lưu AABB bao tất cả điểm trong cây con, cận này cũng là cận dưới cho cả nhánh.

### Branch-and-bound

1. Tới một node, tính khoảng cách từ q tới pivot; cập nhật ứng viên tốt nhất.
2. Tính minDist² tới AABB của từng cây con.
3. Duyệt cây con có cận dưới nhỏ hơn trước để sớm tìm ứng viên tốt.
4. Chỉ bỏ một cây con khi:

\[
\boxed{minDist^2(q,B(node))>bestDist^2.}
\]

5. Tiếp tục tới khi mọi nhánh còn lại đều không thể có điểm tốt hơn.

**Tại sao dấu phải là \(>\), không phải \(\ge\)?** Nếu minDist bằng khoảng cách tốt nhất, nhánh vẫn có thể chứa điểm cùng khoảng cách nhưng ID nhỏ hơn theo quy tắc tie. Nếu API chỉ cần bất kỳ một NN, có thể dùng quy tắc dừng khác; nhưng phải định nghĩa rõ tie.

### Ví dụ

Đã tìm được điểm A có \(bestDist^2=16\). Một cây con có AABB với \(minDist^2=25\). Mọi điểm trong nhánh cách q ít nhất 5, trong khi A cách q 4, nên nhánh không thể thắng và được bỏ.

Nếu \(minDist^2=16\), vẫn có thể có điểm cùng khoảng cách; với tie theo ID, tiếp tục xét nhánh.

## 10. k-nearest neighbors (kNN)

KNN cần trả **k điểm gần nhất** theo thứ tự (khoảng cách, ID). Có thể giữ một **max-heap kích thước tối đa k** chứa các ứng viên tốt nhất hiện tại:

- Heap giữ điểm **tệ nhất trong k điểm** ở đỉnh.
- Khi gặp điểm mới tốt hơn điểm tệ nhất, thay điểm đó.
- Khi heap đã đủ k điểm, khoảng cách của điểm tệ nhất tạo ngưỡng để cắt tỉa.

Nếu \(best_k^2\) là bình phương khoảng cách của phần tử tệ nhất hiện tại:

\[
\boxed{minDist^2(q,B(node))>best_k^2
\implies\text{bỏ nhánh}.}
\]

Nếu heap chưa đủ k điểm, chưa có ngưỡng đầy đủ để loại nhánh dựa trên ứng viên thứ k.

### Tie-break ổn định

Giả sử thứ tự tốt nhất là:

\[
\boxed{(D_2^2(p,q),\operatorname{id}(p))}
\]

thì khi khoảng cách bằng nhau, ID nhỏ hơn đứng trước. Cận dưới bằng ngưỡng vẫn cần được xem nếu nhánh có thể chứa ID ưu tiên hơn.

### Độ phức tạp

Nếu có \(V\) node được thăm và heap kích thước k:

\[
O(dV+V\log k+k\log k)
\]

ở mức mô tả đơn giản, gồm tính cận/điểm, cập nhật heap và sắp kết quả cuối. Với k nhỏ, heap quản lý ứng viên thường hiệu quả hơn sắp toàn bộ n điểm; nhưng **trường hợp xấu vẫn có thể thăm mọi node**.

## 11. Chọn nhánh gần trước: split plane và AABB

Trong k-d tree truyền thống, tại nút chia trục \(j\), ta có thể chọn nhánh gần bằng cách so \(q_j\) với tọa độ pivot. Nhánh gần thường là nhánh chứa q theo trục chia; sau đó mới kiểm tra nhánh xa.

Tuy nhiên, **nhánh gần theo một trục chưa chắc là nhánh có AABB gần nhất theo metric**. Khi đã lưu AABB, có thể tính minDist tới cả hai con rồi sắp tăng dần theo cận dưới.

| Cách chọn thứ tự | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Theo phía của split plane | Rẻ, phù hợp cấu trúc cơ bản | Không nhất thiết ưu tiên vùng gần nhất theo toàn bộ chiều |
| Theo minDist tới AABB con | Phản ánh metric và hình dạng vùng | Tốn thêm \(O(d)\) mỗi con |

Một triển khai có thể dùng **split plane để xác định nhánh ưu tiên**, sau đó vẫn dùng **AABB để quyết định có cần thăm nhánh còn lại**. Đây là cách đơn giản và thường hiệu quả trong k-d tree cân bằng.

## 12. Python: k-d tree tĩnh với hai chính sách chọn trục

Ví dụ sau dùng **Python 3.10+** và thư viện chuẩn. Nó hỗ trợ:

- Tập điểm \(d\) chiều, ID chuỗi duy nhất.
- Xây median tree bằng **cyclic axis** hoặc **widest spread**.
- AABB chính xác tại từng node.
- Truy vấn hộp đóng.
- Nearest neighbor chính xác.
- k-nearest neighbors chính xác với tie-break theo ID.

Mã tập trung vào **chỉ mục tĩnh**. Khi dữ liệu thay đổi nhiều, bài sẽ phân tích chiến lược cập nhật và rebuild riêng.

~~~python
from dataclasses import dataclass
from heapq import heappush, heapreplace
from math import isfinite


@dataclass(frozen=True)
class KDPoint:
    id: str
    coords: tuple[float, ...]


@dataclass
class KDNode:
    point: KDPoint
    axis: int
    left: "KDNode | None"
    right: "KDNode | None"
    lo: tuple[float, ...]
    hi: tuple[float, ...]


class KDTree:
    def __init__(self, points, axis_strategy="cyclic"):
        if axis_strategy not in ("cyclic", "widest"):
            raise ValueError("axis_strategy phải là cyclic hoặc widest")

        normalized = []
        seen = set()
        dimension = None
        for item_id, raw_coords in points:
            if not isinstance(item_id, str) or not item_id:
                raise ValueError("ID phải là chuỗi không rỗng")
            if item_id in seen:
                raise ValueError("ID phải duy nhất")
            coords = tuple(float(x) for x in raw_coords)
            if not coords or not all(isfinite(x) for x in coords):
                raise ValueError("Tọa độ phải hữu hạn và có chiều")
            if dimension is None:
                dimension = len(coords)
            if len(coords) != dimension:
                raise ValueError("Mọi điểm phải cùng số chiều")
            seen.add(item_id)
            normalized.append(KDPoint(item_id, coords))

        self.dimension = dimension or 0
        self.axis_strategy = axis_strategy
        self.id_rank = {
            item_id: rank
            for rank, item_id in enumerate(sorted(seen))
        }
        self.root = self._build(normalized, depth=0)

    def _choose_axis(self, records, depth):
        if self.axis_strategy == "cyclic":
            return depth % self.dimension

        spreads = []
        for axis in range(self.dimension):
            values = [p.coords[axis] for p in records]
            spreads.append(max(values) - min(values))
        # Nếu spread bằng nhau, max chọn axis nhỏ hơn nhờ -axis.
        return max(
            range(self.dimension),
            key=lambda axis: (spreads[axis], -axis),
        )

    def _build(self, records, depth):
        if not records:
            return None

        axis = self._choose_axis(records, depth)
        ordered = sorted(
            records,
            key=lambda p: (p.coords[axis], p.id),
        )
        middle = len(ordered) // 2
        pivot = ordered[middle]
        left = self._build(ordered[:middle], depth + 1)
        right = self._build(ordered[middle + 1:], depth + 1)

        lo = list(pivot.coords)
        hi = list(pivot.coords)
        for child in (left, right):
            if child is not None:
                for i in range(self.dimension):
                    lo[i] = min(lo[i], child.lo[i])
                    hi[i] = max(hi[i], child.hi[i])

        return KDNode(
            pivot, axis, left, right, tuple(lo), tuple(hi)
        )

    def _query_vector(self, raw):
        coords = tuple(float(x) for x in raw)
        if (len(coords) != self.dimension
                or not all(isfinite(x) for x in coords)):
            raise ValueError("Vector truy vấn sai chiều hoặc không hữu hạn")
        return coords

    @staticmethod
    def _box_intersects(node, lower, upper):
        return all(
            node.lo[i] <= upper[i] and lower[i] <= node.hi[i]
            for i in range(len(lower))
        )

    @staticmethod
    def _min_distance_sq(node, query):
        return sum(
            max(node.lo[i] - query[i],
                0.0,
                query[i] - node.hi[i]) ** 2
            for i in range(len(query))
        )

    @staticmethod
    def _distance_sq(a, b):
        return sum((x-y)**2 for x, y in zip(a, b))

    def range_query(self, lower, upper):
        if self.root is None:
            return []
        lower = self._query_vector(lower)
        upper = self._query_vector(upper)
        if any(a > b for a, b in zip(lower, upper)):
            raise ValueError("Cận dưới lớn hơn cận trên")

        result = []

        def visit(node):
            if node is None:
                return
            if not self._box_intersects(node, lower, upper):
                return

            if all(
                a <= x <= b
                for a, x, b in zip(lower, node.point.coords, upper)
            ):
                result.append(node.point)
            visit(node.left)
            visit(node.right)

        visit(self.root)
        return sorted(result, key=lambda p: p.id)

    def nearest(self, query):
        if self.root is None:
            return None
        query = self._query_vector(query)
        best_key = None
        best_point = None

        def visit(node):
            nonlocal best_key, best_point
            if node is None:
                return
            lower_bound = self._min_distance_sq(node, query)
            if best_key is not None and lower_bound > best_key[0]:
                return

            candidate_key = (
                self._distance_sq(node.point.coords, query),
                node.point.id,
            )
            if best_key is None or candidate_key < best_key:
                best_key = candidate_key
                best_point = node.point

            children = [
                child for child in (node.left, node.right)
                if child is not None
            ]
            children.sort(
                key=lambda child: self._min_distance_sq(child, query)
            )
            for child in children:
                visit(child)

        visit(self.root)
        return best_point

    def k_nearest(self, query, k):
        if type(k) is not int or k < 1:
            raise ValueError("k phải là số nguyên dương")
        if self.root is None:
            return []
        query = self._query_vector(query)
        heap = []

        def visit(node):
            if node is None:
                return
            lower_bound = self._min_distance_sq(node, query)
            if len(heap) == k and lower_bound > -heap[0][0]:
                return

            distance = self._distance_sq(node.point.coords, query)
            rank = self.id_rank[node.point.id]
            entry = (-distance, -rank, node.point)
            if len(heap) < k:
                heappush(heap, entry)
            else:
                worst_key = (-heap[0][0], -heap[0][1])
                if (distance, rank) < worst_key:
                    heapreplace(heap, entry)

            children = [
                child for child in (node.left, node.right)
                if child is not None
            ]
            children.sort(
                key=lambda child: self._min_distance_sq(child, query)
            )
            for child in children:
                visit(child)

        visit(self.root)
        return [
            entry[2]
            for entry in sorted(
                heap,
                key=lambda item: (
                    -item[0], self.id_rank[item[2].id]
                ),
            )
        ]

    def all_points(self):
        result = []

        def walk(node):
            if node is None:
                return
            result.append(node.point)
            walk(node.left)
            walk(node.right)

        walk(self.root)
        return result

    def validate(self):
        """Kiểm tra AABB chứa pivot và mọi điểm của cây con."""
        ids = []

        def walk(node, constraints):
            if node is None:
                return []
            for axis, boundary, is_left in constraints:
                candidate = (node.point.coords[axis], node.point.id)
                if is_left and not (candidate < boundary):
                    raise AssertionError("Vi phạm cận trái phân hoạch")
                if not is_left and candidate < boundary:
                    raise AssertionError("Vi phạm cận phải phân hoạch")

            key = (node.point.coords[node.axis], node.point.id)
            left_points = walk(
                node.left, constraints + [(node.axis, key, True)]
            )
            right_points = walk(
                node.right, constraints + [(node.axis, key, False)]
            )
            current = [node.point] + left_points + right_points
            ids.append(node.point.id)

            for p in current:
                if any(
                    p.coords[i] < node.lo[i]
                    or p.coords[i] > node.hi[i]
                    for i in range(self.dimension)
                ):
                    raise AssertionError("AABB không bao hết cây con")
            return current

        walk(self.root, [])
        if len(ids) != len(set(ids)):
            raise AssertionError("ID bị lặp")
        return True


data = [
    ("A", (2, 3)),
    ("B", (5, 4)),
    ("C", (9, 6)),
    ("D", (4, 7)),
    ("E", (8, 1)),
    ("F", (7, 2)),
    ("G", (1, 8)),
    ("H", (5, 4)),  # Trùng tọa độ với B, nhưng ID khác.
]

cyclic_tree = KDTree(data, axis_strategy="cyclic")
wide_tree = KDTree(data, axis_strategy="widest")
assert cyclic_tree.validate()
assert wide_tree.validate()

inside = cyclic_tree.range_query((2, 2), (8, 7))
assert [p.id for p in inside] == ["A", "B", "D", "F", "H"]

assert cyclic_tree.nearest((6, 4)).id == "B"
assert [p.id for p in cyclic_tree.k_nearest((6, 4), 3)] == [
    "B", "H", "F"
]

# k lớn hơn số điểm: trả tối đa toàn bộ điểm.
assert len(cyclic_tree.k_nearest((0, 0), 100)) == len(data)

# Hai chiến lược trục phải cho cùng kết quả hình học.
for lower, upper in [
    ((0, 0), (10, 10)),
    ((0, 0), (5, 5)),
    ((5, 4), (5, 4)),
    ((10, 10), (11, 11)),
]:
    ids_cyclic = [
        p.id for p in cyclic_tree.range_query(lower, upper)
    ]
    ids_wide = [
        p.id for p in wide_tree.range_query(lower, upper)
    ]
    assert ids_cyclic == ids_wide
~~~

### Giải thích tie-break trong heap

Heap Python là **min-heap**. Để phần tử tệ nhất nằm ở đỉnh, mã lưu:

\[
(-distance^2,\ -rank(ID),\ point).
\]

Trong đó rank(ID) là thứ tự tăng theo ID. Khoảng cách càng lớn thì số âm càng nhỏ; cùng khoảng cách, ID càng lớn thì \(-rank\) càng nhỏ. Vì vậy đỉnh heap là **ứng viên tệ nhất** theo thứ tự (distance², ID). Mã chỉ thay đỉnh khi ứng viên mới có khóa tốt hơn.

### Giới hạn của mã

- Build sắp xếp lại ở mỗi mức, đơn giản và dễ đọc nhưng không tối ưu.
- Axis widest tính min/max tại từng node; với nhiều chiều và nhiều điểm, chi phí thống kê tăng.
- Mỗi node giữ AABB \(2d\) tọa độ; bộ nhớ metadata là \(O(nd)\).
- Range/NN/kNN đều có thể thăm gần hết cây trong trường hợp xấu.
- Cây **không có API insert/delete** trong ví dụ này; phần tiếp theo phân tích cập nhật và cách chọn rebuild.

## 13. Cập nhật động: chèn, xóa và di chuyển điểm

K-d tree được dùng phổ biến cho **tập điểm tương đối tĩnh**. Ta vẫn có thể chèn/xóa, nhưng những thao tác đó có thể làm cây mất cân bằng hoặc làm metadata cũ không còn đúng.

### Chèn một điểm

Với mỗi node:

1. Tính khóa phân hoạch \((p_{axis},ID)\).
2. So với khóa của pivot.
3. Nếu nhỏ hơn, đi trái; nếu lớn hơn hoặc bằng, đi phải.
4. Tới vị trí rỗng, tạo node mới.
5. Cập nhật AABB trên đường từ vị trí chèn trở về gốc.

Nếu chiều cao hiện tại là \(h\), chi phí tìm vị trí là \(O(h)\) phép so sánh khóa, cộng \(O(dh)\) nếu cập nhật AABB từng tổ tiên. Khi cây cân bằng, \(h=O(\log n)\); sau nhiều lần chèn lệch, \(h\) có thể thành \(O(n)\).

**Quan trọng:** Khi chèn động, dùng đúng trục và tie-break đã lưu ở mỗi node. Không tự đổi trục của một node hiện hữu mà không tái phân hoạch toàn bộ cây con.

### Xóa một điểm

Xóa trong k-d tree phức tạp hơn BST một chiều vì mỗi node có thể chia theo **trục khác nhau**.

Các chiến lược:

- **Tombstone/lazy deletion:** đánh dấu node đã xóa, truy vấn bỏ qua nó; định kỳ xây lại cây để loại node chết. Dễ triển khai nhưng cây và AABB có thể còn bao cả vùng của điểm đã xóa, làm cắt tỉa kém hiệu quả.
- **Thay thế theo trục chia:** tìm phần tử nhỏ nhất phù hợp theo trục của node trong một cây con, thay pivot rồi xóa bản ghi thay thế ở vị trí cũ. Nếu không có cây con phải, cách xử lý cây con trái cần chuyển nhánh để bảo toàn quy tắc phân hoạch.
- **Rebuild cây con:** thu thập các điểm còn sống trong một cây con rồi xây lại bằng median. Dễ giữ bất biến hơn nhưng tốn chi phí xây dựng tại thời điểm cập nhật.

Không thể áp dụng nguyên xi thao tác “lấy successor bên phải” của BST thông thường mà không xét **trục chia tại từng mức**.

### Di chuyển điểm

Di chuyển một điểm \(p\) tới tọa độ \(p'\) thường được xem như:

\[
\boxed{\operatorname{move}(p,p')
=\operatorname{delete}(p)+\operatorname{insert}(p').}
\]

Nếu chỉ cập nhật tọa độ tại node cũ, điểm có thể không còn thỏa bất biến của các mặt chia tổ tiên. Khi đó một truy vấn đi đúng nhánh theo tọa độ mới có thể **không bao giờ gặp node**.

### Rebuild toàn cây hoặc một cây con

Khi cây mất cân bằng hoặc nhiều tombstone:

1. Duyệt lấy tất cả bản ghi còn sống.
2. Chọn trục theo chiến lược đã định.
3. Xây lại bằng median.
4. Tính lại AABB.
5. Thay tham chiếu gốc/cây con khi bản mới hoàn chỉnh.

Rebuild định kỳ dễ bảo đảm chất lượng cấu trúc hơn việc duy trì cân bằng phức tạp sau mọi lần chèn/xóa.

## 14. Vì sao chọn trục tốt chưa đủ?

Một cây có thể chọn đúng chiều có spread lớn nhất nhưng vẫn tạo truy vấn tệ nếu **giá trị chia** không phù hợp. Ngược lại, median có thể giữ chiều cao nhỏ nhưng AABB của nhánh vẫn chồng lấp rộng.

### Median cân theo số lượng, không theo khoảng cách

Cho tập điểm có một cụm rất dày ở gần \((0,0)\) và vài điểm rải xa. Median chia gần một nửa số điểm mỗi bên, nhưng một vùng chứa phần lớn diện tích có thể vẫn có rất ít điểm. Truy vấn theo một vị trí trong vùng rỗng có thể phải đi nhiều nhánh nếu AABB cây con bao rộng.

### Spread nhạy với outlier

Một điểm rất xa làm spread của một chiều tăng mạnh. Nếu phần lớn điểm còn lại tập trung hẹp, chia theo chiều đó có thể tạo một nhánh chỉ chứa outlier và nhánh còn lại gần như toàn bộ dữ liệu. Median vẫn cân theo số lượng sau khi chọn trục, nhưng **hình học vùng** của hai nhánh có thể chưa tối ưu.

### Phương sai nhạy với đơn vị

Nếu trục x tính bằng kilomet còn trục y tính bằng mét, phương sai thô có thể ưu tiên y chỉ vì số đo lớn hơn 1.000 lần. Muốn chọn trục theo ý nghĩa hình học, hãy dùng **cùng hệ đơn vị** hoặc chuẩn hóa có chủ đích.

### Đánh giá bằng workload thật

Không chỉ đo chiều cao. Cần quan sát:

- Số node được thăm trong range/NN.
- Tỷ lệ cắt tỉa theo từng trục.
- Kích thước và độ chồng lấp của AABB cây con.
- Chi phí chọn trục và xây dựng.
- Tỷ lệ insert/delete so với query.

Một chính sách chọn trục tốt thường là **một giả thuyết để benchmark**, không phải bảo đảm hiệu năng.

## 15. Phân tích độ phức tạp

Gọi:

- \(n\): số điểm.
- \(d\): số chiều.
- \(h\): chiều cao thực của cây.
- \(V\): số node được thăm trong truy vấn.
- \(k\): số kết quả.

### Xây cây bằng sort tại mỗi mức

Trong ví dụ Python, mỗi node sắp tập điểm con theo khóa trên trục đã chọn rồi lấy median. Nếu cây chia cân bằng:

- Mỗi mức tổng kích thước các tập con là \(O(n)\).
- Mỗi mức sắp xếp tổng cộng tối đa cỡ \(O(n\log n)\).
- Có \(O(\log n)\) mức.

Vì vậy:

\[
\boxed{T_{\mathrm{build}}=O(n\log^2 n)}
\]

cho số chiều cố định; nếu tính chi phí so sánh vector/khóa theo d thì cần thêm hệ số phù hợp. Với widest spread, quét min/max tại mỗi mức thêm \(O(nd\log n)\); khi d cố định, tổng vẫn thuộc mức \(O(n\log^2 n)\).

Các thuật toán xây dựng tối ưu hơn có thể duy trì danh sách điểm đã sắp theo từng trục hoặc dùng lựa chọn median tuyến tính kỳ vọng:

\[
O(d\,n\log n)
\]

trong các giả thiết cài đặt thích hợp. Không nên gán chi phí này cho đoạn mã sắp lại ở mỗi node.

### Chiều cao và tìm kiếm

Với median split và ID duy nhất, số điểm ở hai phía gần bằng nhau, nên chiều cao:

\[
\boxed{h=O(\log n).}
\]

Nhưng chiều cao nhỏ **không đồng nghĩa truy vấn luôn chỉ thăm \(O(\log n)\) node**.

| Thao tác | Trường hợp thuận lợi | Trường hợp xấu |
| --- | --- | --- |
| Tìm vị trí một điểm | \(O(\log n)\) trong cây cân bằng | \(O(n)\) |
| Range query | Cắt được nhiều nhánh; phụ thuộc V và k | \(O(nd)\), tức \(O(n)\) khi d cố định |
| Nearest neighbor | Cận dưới AABB loại được nhiều nhánh | \(O(nd)\) |
| kNN | \(O(dV+V\log k+k\log k)\) với heap và sắp kết quả | \(O(nd+n\log k)\) |
| Insert động | \(O(dh)\) kể cả cập nhật bbox | \(O(dn)\) nếu cây lệch |
| Delete/rebuild cây con m điểm | Thu thập và xây lại, tùy cách build | Có thể \(O(dm\log^2m)\) với cách sort đơn giản |

### Bộ nhớ

- Mỗi điểm có một node → \(O(n)\) node.
- Mỗi node giữ AABB gồm \(2d\) tọa độ → \(O(nd)\) metadata.
- Ngăn xếp đệ quy cho cây cân bằng thường \(O(\log n)\); trường hợp cây lệch có thể \(O(n)\).
- kNN giữ heap tối đa k ứng viên → \(O(k)\) bộ nhớ phụ.

Nếu d cố định nhỏ, có thể xem bộ nhớ cây là \(O(n)\). Khi d tăng, chi phí AABB và tính metric tăng tuyến tính theo d.

## 16. Lời nguyền số chiều và khi nào k-d tree kém hiệu quả

K-d tree phát huy tốt nhất trong **không gian ít chiều**. Khi d tăng:

1. Mỗi phép tính khoảng cách và AABB tốn \(O(d)\).
2. AABB của nhánh có thể bao rộng theo nhiều chiều.
3. Khoảng cách tới nhiều nhánh có thể gần nhau, khiến cắt tỉa ít hiệu quả.
4. Số điểm cần thăm trong NN có thể tiến gần n.

Trong dữ liệu chiều cao như embedding 128, 384 hoặc 768 chiều, một k-d tree chính xác có thể không nhanh hơn quét tuyến tính đủ nhiều để bù chi phí xây dựng.

### Chuẩn hóa và metric

Nếu các chiều có đơn vị khác nhau, khoảng cách Euclid thô có thể bị một chiều chi phối. Có thể:

- Chuẩn hóa theo miền/độ lệch chuẩn nếu nghiệp vụ cho phép.
- Dùng metric Manhattan, Chebyshev hoặc metric chuyên biệt.
- Chuyển đổi dữ liệu sang hệ tọa độ phù hợp.

Tuy nhiên, thay đổi metric có thể làm thay đổi cách tính cận dưới và hiệu quả cắt tỉa. Mọi cận dùng để loại nhánh phải là **cận dưới hợp lệ theo đúng metric**.

### Khi cần approximate nearest neighbor

Nếu ứng dụng chấp nhận kết quả gần đúng để đổi lấy tốc độ ở số chiều cao, hãy đánh giá cấu trúc ANN phù hợp. Khi đó cần đo **recall**, tỷ lệ tìm được láng giềng đúng so với nghiệm chính xác trên tập kiểm thử. Không gọi kết quả gần đúng là NN chính xác.

## 17. Các lỗi và hiểu lầm thường gặp

1. **“K-d tree luôn chia luân phiên x/y.”** Đây chỉ là một chính sách; có thể chọn widest spread hoặc maximum variance.
2. **“Chọn trục spread lớn nhất thì cây chắc chắn cân bằng.”** Sai: trục chỉ quyết định hướng; giá trị chia và tie-break mới quyết định số điểm mỗi phía.
3. **“Median split và midpoint split là cùng một phép.”** Sai: một phép chia theo thứ tự dữ liệu, phép kia chia theo hình học vùng.
4. **“Median làm cây cân thì mọi truy vấn đều nhanh.”** Sai: range/NN có thể phải thăm nhiều nhánh dù chiều cao \(O(\log n)\).
5. **“Tọa độ trùng nhau có thể bỏ qua ID.”** Sai nếu nhiều bản ghi cùng vị trí nhưng là các đối tượng khác nhau.
6. **“Dùng tie-break theo ID thì mọi điểm trái đều có tọa độ nhỏ hơn pivot.”** Sai: hai điểm cùng tọa độ có thể khác ID và nằm ở hai phía theo khóa tổng hợp.
7. **“Có thể tìm kiếm theo split plane nhưng bỏ qua tie-break đã dùng lúc build.”** Sai: đường đi có thể không tới được bản ghi.
8. **“AABB cây con có thể chỉ bao pivot.”** Sai: phải bao **mọi điểm trong cây con**, nếu không cắt tỉa có thể bỏ sót.
9. **“AABB giao Q nghĩa là mọi điểm trong cây con thuộc Q.”** Sai: vẫn phải kiểm tra pivot/điểm ở node được thăm.
10. **“AABB không giao Q nhưng vẫn có điểm trong Q.”** Không thể nếu AABB bao đủ mọi điểm và predicate giao được tính đúng.
11. **“Nearest neighbor chỉ cần đi một đường xuống lá.”** Sai: nhánh khác có thể chứa điểm gần hơn.
12. **“minDist bằng bestDist thì luôn được prune.”** Sai khi cần xử lý tie theo ID hoặc trả tất cả điểm đồng khoảng cách.
13. **“kNN chưa đủ k ứng viên vẫn có thể prune theo điểm tệ nhất.”** Sai: khi heap chưa đầy, chưa có ngưỡng thứ k.
14. **“K-d tree xóa giống BST thông thường.”** Sai: tiêu chí chia đổi theo trục tại từng node.
15. **“Chỉ sửa tọa độ node là hoàn tất move.”** Sai: node có thể vi phạm phân hoạch của tổ tiên.
16. **“Cây median ban đầu cân thì chèn thêm vẫn cân.”** Sai: insert động lệch có thể tạo nhánh dài.
17. **“Chọn widest spread luôn tốt hơn cyclic.”** Sai: widest nhạy outlier và tốn chi phí thống kê.
18. **“Phương sai giữa các trục có thể so trực tiếp dù đơn vị khác nhau.”** Sai: cần chuẩn hóa hoặc metric có ý nghĩa.
19. **“Tăng số chiều không làm thay đổi hiệu quả cắt tỉa.”** Sai: curse of dimensionality có thể khiến truy vấn gần quét tuyến tính.
20. **“Cây có chiều cao log n thì NN cũng O(log n).”** Sai: số node được thăm không chỉ phụ thuộc chiều cao.
21. **“Một điểm nằm đúng split plane luôn chỉ thuộc một nhánh hình học.”** Với tie-break theo ID, điểm cùng tọa độ có thể nằm ở hai nhánh; predicate vùng phải xử lý cả hai.
22. **“Dữ liệu địa lý kinh độ/vĩ độ dùng Euclid trực tiếp ra mét.”** Sai: cần CRS, phép chiếu và metric phù hợp.
23. **“Có thể so sánh mọi trục theo spread thô dù khác đơn vị.”** Sai: đơn vị đo có thể quyết định trục được chọn một cách vô nghĩa.
24. **“K-d tree là lựa chọn tốt nhất cho mọi dữ liệu nhiều chiều.”** Sai: benchmark với quét tuyến tính và ANN nếu cần.

## 18. Quy trình benchmark và chọn trục chia

Không có một chính sách trục thắng trong mọi phân bố. Hãy so sánh ít nhất **cyclic**, **widest spread**, và nếu phù hợp **maximum variance**.

### Dữ liệu thử

- Điểm phân bố đều trong hình vuông/hình lập phương.
- Điểm nằm trên đường chéo hoặc một đường thẳng.
- Điểm tập trung trong một cụm, có outlier xa.
- Nhiều điểm trùng một tọa độ nhưng ID khác nhau.
- Dữ liệu có chiều với đơn vị khác nhau.
- Tập điểm thay đổi liên tục so với tập gần như tĩnh.

### Chỉ số đo

| Chỉ số | Vì sao quan trọng? |
| --- | --- |
| Thời gian build | Một cây truy vấn nhanh nhưng xây rất lâu có thể không phù hợp |
| Chiều cao thực | Phát hiện cây lệch |
| Số node được thăm V | Đo hiệu quả cắt tỉa thật |
| Số điểm phải tính khoảng cách | Đặc biệt quan trọng với NN/kNN |
| Số lần cắt tỉa | Cho biết AABB có hữu ích |
| p50/p95/p99 latency | Phát hiện truy vấn xấu |
| RAM và metadata AABB | Mỗi node giữ 2d tọa độ |
| Chi phí rebuild | Đo khả năng duy trì cây |
| Độ đúng so với brute force | Bảo đảm không bỏ sót hoặc sai tie |

### Quy trình kiểm thử

1. Sinh một tập điểm và ID giống nhau cho từng chiến lược.
2. Xây cây theo từng chính sách trục.
3. Chạy cùng tập truy vấn range/NN/kNN.
4. Đối chiếu ID và khoảng cách với quét tuyến tính.
5. Ghi số node được thăm, số điểm được kiểm tra, thời gian và bộ nhớ.
6. Lặp trên phân bố đều, cụm, outlier và trùng tọa độ.
7. Chọn chiến lược theo **tổng workload**, không chỉ một truy vấn đẹp.

Nếu truy vấn gần như toàn bộ tập điểm, quét tuyến tính có thể thắng do truy cập mảng tuần tự và ít overhead. Chỉ mục chỉ có giá trị khi phần cắt tỉa tiết kiệm được nhiều công việc hơn chi phí điều phối.

## 19. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Chọn trục luân phiên

K-d tree 3D dùng cyclic axis, gốc ở depth 0 và trục bắt đầu là x. Các mức 0 tới 7 lần lượt chia theo trục nào?

**Lời giải:** \(axis=depth\bmod3\), nên thứ tự là **x, y, z, x, y, z, x, y**.

### Câu 2. Tìm trục theo spread

Tập điểm có min/max theo từng trục:

| Trục | Min | Max | Spread |
| --- | ---: | ---: | ---: |
| x | -2 | 8 | 10 |
| y | 1 | 4 | 3 |
| z | 0 | 20 | 20 |

Chọn trục nào theo widest spread?

**Lời giải:** Spread lớn nhất là 20 ở trục **z**, nên chọn z.

### Câu 3. So sánh spread và phương sai

Một trục có các giá trị \(0,1,1,1,1,1,100\). Vì sao spread và phương sai có thể dẫn tới lựa chọn khác nhau so với một trục khác có nhiều giá trị phân tán vừa phải?

**Lời giải:** Spread chỉ xét hai cực trị, còn phương sai xét toàn bộ độ lệch quanh trung bình. Outlier 100 tác động mạnh tới cả hai nhưng mức ảnh hưởng khác nhau; trục còn lại có nhiều giá trị phân tán vừa phải có thể có phương sai lớn dù spread nhỏ hơn. Phải tính thống kê trên dữ liệu cụ thể.

### Câu 4. Median hay midpoint?

Các giá trị trên trục x là \(1,2,3,4,100\). Median chia thành hai nhóm kích thước nào? Nếu miền x là \([0,100]\), midpoint chia theo ngưỡng nào?

**Lời giải:** Median là 3, lấy pivot 3 thì hai phía còn lại có 2 điểm mỗi bên. Midpoint miền là 50, chia theo tọa độ tại 50; nhóm trái có 4 điểm, nhóm phải có 1 điểm. **Median cân theo số điểm**, midpoint cân theo chiều dài miền.

### Câu 5. Tie-break theo ID

Hai điểm A=(5,2), B=(5,8) được chia theo trục x, khóa là (x, ID), với A đứng trước B theo thứ tự ID. Nếu pivot là B, A vào nhánh nào?

**Lời giải:** Khóa A=(5,"A") nhỏ hơn khóa B=(5,"B"), nên A vào **nhánh trái** dù tọa độ x bằng nhau. Điều này cho thấy không thể giả định mọi điểm trái đều có \(x<5\).

### Câu 6. Tìm số điểm ở các nhánh median

Có 16 điểm có khóa duy nhất và sắp theo trục chia. Chọn phần tử giữa với index \(n//2\). Số điểm ở trái, tại pivot và ở phải là bao nhiêu?

**Lời giải:** Pivot ở index 8 (đánh số từ 0), nên trái có **8 điểm**, pivot 1 điểm, phải có **7 điểm**.

### Câu 7. Chiều cao median tree

Một k-d tree được dựng median với 31 điểm. Chiều cao tối đa theo số cạnh gần bao nhiêu?

**Lời giải:** \(2^4=16\), \(2^5=32\). Cây median có chiều cao khoảng **4 cạnh** theo cách lấy trung vị này; số mức là 5.

### Câu 8. Kiểm tra range query

Cho Q=\([2,6]\times[1,5]\). Các điểm A=(2,1), B=(6,5), C=(6.1,3), D=(4,0), E=(3,4). Điểm nào thuộc Q?

**Lời giải:** A và B nằm trên biên đóng; E nằm bên trong. C vượt cận x, D thấp hơn cận y. Kết quả **A, B, E**.

### Câu 9. Cắt tỉa bằng AABB

Một cây con có AABB \(B=[10,20]\times[0,5]\). Truy vấn Q=\([0,9]\times[0,5]\). Có thể bỏ nhánh không?

**Lời giải:** Có. Trục x tách rời vì \(Q.hi_x=9<B.lo_x=10\). Nếu AABB bao đủ mọi điểm trong nhánh, không điểm nào có thể thuộc Q.

### Câu 10. Hộp bao phải chứa toàn bộ điểm

Một cây con có các điểm (1,1), (4,5), (8,2), nhưng metadata lưu AABB \([1,4]\times[1,5]\). Truy vấn quanh (8,2) có thể bị ảnh hưởng thế nào?

**Lời giải:** Điểm (8,2) nằm ngoài AABB đã lưu. Một truy vấn nhỏ quanh điểm đó có thể thấy AABB không giao Q rồi bỏ nhánh, gây **false negative**. Hộp phải có max x ít nhất bằng 8.

### Câu 11. Khoảng cách bình phương

Với q=(0,0), điểm A=(3,4), B=(2,2), so sánh khoảng cách Euclid mà không tính căn.

**Lời giải:** \(D^2(A,q)=25\), \(D^2(B,q)=8\). Vì 8 nhỏ hơn 25, **B gần hơn**.

### Câu 12. MinDist tới hộp

Cho q=(1,4), B=\([3,6]\times[2,5]\). Tính minDist².

**Lời giải:** Trục x cách 2, trục y nằm trong khoảng nên cách 0. \(minDist^2=2^2+0^2=\boxed{4}\).

### Câu 13. Prune NN

Ứng viên tốt nhất có \(bestDist^2=9\). Một nhánh có \(minDist^2=16\). Có thể bỏ nhánh? Nếu minDist²=9 thì sao?

**Lời giải:** Với 16>9, **có thể bỏ**. Nếu bằng 9, vẫn phải xét khi tie-break theo ID có ý nghĩa vì nhánh có thể chứa điểm cùng khoảng cách nhưng ID tốt hơn.

### Câu 14. kNN và heap chưa đầy

Đang tìm 5NN nhưng mới gặp 3 điểm. Một nhánh có minDist²=100 trong khi điểm tốt nhất hiện tại có dist²=4. Có thể bỏ nhánh chỉ dựa vào điểm tốt nhất không?

**Lời giải:** **Không.** Heap chưa đủ 5 điểm; nhánh có thể chứa điểm thứ tư hoặc thứ năm dù xa hơn 4. Chỉ khi có đủ k ứng viên mới có ngưỡng của phần tử tệ nhất trong top k để prune.

### Câu 15. Tie trong kNN

Kết quả hiện có ở ngưỡng top-k là (dist²=25, ID="M"). Một nhánh có minDist²=25. Có thể bỏ nhánh nếu quy tắc tie ưu tiên ID nhỏ hơn không?

**Lời giải:** Không thể bỏ chỉ dựa vào khoảng cách. Nhánh có thể chứa điểm dist²=25 với ID "A", đứng trước M theo thứ tự kết quả. Cần xét tiếp hoặc có metadata bổ sung để chứng minh không thể thắng tie.

### Câu 16. Chèn động làm cây lệch

Một k-d tree ban đầu cân bằng. Ta chèn liên tiếp các điểm có tọa độ tăng dần theo một đường sao cho chúng đều đi vào cùng một nhánh. Chiều cao có thể tăng tới mức nào?

**Lời giải:** Có thể tăng tới **\(O(n)\)** nếu không tái cân bằng/rebuild; chiều cao ban đầu \(O(\log n)\) không được bảo toàn tự động sau chèn.

### Câu 17. Di chuyển điểm

Một điểm được lưu ở node thỏa điều kiện x<5 với tổ tiên, sau đó tọa độ của nó đổi thành x=9. Vì sao không nên chỉ sửa trường tọa độ tại node cũ?

**Lời giải:** Điểm vi phạm bất biến phân hoạch của tổ tiên. Tìm kiếm theo x=9 sẽ đi sang nhánh khác và không gặp node cũ. Cần **xóa rồi chèn lại** hoặc rebuild phần cây liên quan.

### Câu 18. Chọn trục theo đơn vị

Vector có x tính bằng kilomet, y tính bằng mét. Spread thô của y là 500, của x là 2. Nếu chọn widest spread trực tiếp, kết luận gì và vì sao có thể sai về ý nghĩa?

**Lời giải:** Thuật toán số học sẽ chọn y vì 500>2. Nhưng hai trục khác đơn vị, 500 mét chỉ là 0,5 km; so sánh thô có thể làm lựa chọn trục lệch ý nghĩa. Cần đưa về cùng đơn vị hoặc chuẩn hóa theo nghiệp vụ.

### Câu 19. Xây cây bằng sort ở mỗi mức

Một thuật toán sắp xếp lại toàn bộ tập con tại mỗi mức median. Với cây cân bằng có \(\log n\) mức, vì sao tổng chi phí là \(O(n\log^2 n)\) thay vì \(O(n\log n)\)?

**Lời giải:** Mỗi mức có tổng \(n\) phần tử nhưng mỗi nhóm phải sắp xếp, tổng chi phí sắp xếp của một mức cỡ \(O(n\log n)\). Có \(O(\log n)\) mức, nhân lại thành \(O(n\log^2 n)\). Nếu dùng median selection hoặc danh sách sắp theo trục được duy trì, có thể cải thiện.

### Câu 20. Chọn cấu trúc cho dữ liệu chiều cao

Một tập gồm 500.000 vector 256 chiều, truy vấn gần nhất rất thường xuyên. Có nên mặc định dùng k-d tree chính xác không?

**Lời giải:** Không. Ở 256 chiều, cắt tỉa k-d tree có thể kém hiệu quả và gần quét toàn bộ. Cần benchmark với quét tuyến tính/vector hóa và cân nhắc chỉ mục ANN nếu ứng dụng chấp nhận gần đúng; nếu yêu cầu chính xác, so tổng thời gian và bộ nhớ của các phương án.

### Câu 21. Chọn chính sách trục cho đường thẳng

Một tập điểm nằm trên đường ngang y=7, còn x phân bố rộng. Nếu gốc chọn trục y theo cyclic, spread của y là bao nhiêu? Widest spread chọn gì?

**Lời giải:** Spread y bằng **0**. Widest spread chọn **x** vì x có độ trải rộng dương. Nếu vẫn chia y, tie-break ID có thể cân số điểm nhưng không tạo phân hoạch không gian có ích.

### Câu 22. Kiểm tra hai chiến lược

Hai k-d tree được dựng từ cùng tập điểm, một dùng cyclic axis và một dùng widest spread. Kết quả range query chính xác có được khác nhau không?

**Lời giải:** Nếu cả hai cài đặt giữ đúng mọi điểm, AABB bao đủ cây con và dùng cùng predicate, **tập kết quả phải giống nhau**. Cây có thể khác hình dạng, số node được thăm và thời gian truy vấn.

## 20. Tổng kết và quy trình lựa chọn trục

**K-d tree** chia tập điểm \(d\) chiều bằng các mặt phẳng vuông góc với trục tọa độ. Mỗi node giữ một pivot, trục chia và hai cây con. Bất biến phân hoạch phải được duy trì ở mọi tổ tiên; nếu dùng khóa tổng hợp \((tọa độ,ID)\), truy vấn phải tôn trọng tie-break đó.

Có ba chiến lược chọn trục thường gặp:

- **Cyclic:** rẻ, dễ triển khai, luân phiên các chiều.
- **Widest spread:** chọn chiều có max-min lớn nhất, phản ánh phạm vi hình học nhưng nhạy outlier.
- **Maximum variance:** chọn chiều phân tán theo thống kê lớn nhất, cần tính toán và chú ý đơn vị.

Sau khi chọn trục, **median split** giúp cân số điểm và giữ chiều cao gần \(O(\log n)\); **midpoint split** chia miền hình học nhưng không bảo đảm cân số bản ghi. Hai quyết định này phải được phân biệt.

**Range query** và **nearest neighbor** có thể cắt tỉa bằng AABB cây con. Range loại nhánh không giao cửa sổ; NN/kNN loại nhánh khi cận dưới khoảng cách lớn hơn ngưỡng tốt nhất. Các cận chỉ đúng nếu **AABB chứa mọi điểm của cây con**. Trong trường hợp xấu, truy vấn vẫn có thể thăm \(\Theta(n)\) node.

K-d tree tĩnh phù hợp với tập điểm ít chiều và tỷ lệ truy vấn cao. Chèn/xóa liên tục có thể làm cây mất cân bằng; thường cần tombstone, rebuild cây con hoặc xây lại toàn bộ. Với số chiều cao, cần benchmark với quét tuyến tính và ANN thay vì mặc định k-d tree luôn nhanh.

**Quy trình thực hành:** xác định số chiều/đơn vị/metric → chọn cyclic, widest hay variance → chọn median hay midpoint → định nghĩa tie-break và ID → xây AABB chính xác → kiểm thử range/NN/kNN với quét tham chiếu → đo số node thăm, độ trễ và bộ nhớ trên dữ liệu đều, cụm, outlier và trùng tọa độ. Mục tiêu là **giữ đúng kết quả và giảm công việc thực tế**, không phải chỉ tạo một cây có chiều cao đẹp.
