# Tìm láng giềng gần nhất và cắt nhánh bằng cận khoảng cách

Một ứng dụng định vị có hàng triệu điểm trên bản đồ nhưng chỉ cần trả về địa điểm gần vị trí người dùng nhất. Nếu tính khoảng cách từ vị trí truy vấn đến **mọi** điểm, ta phải đọc và so sánh toàn bộ dữ liệu. Với chỉ mục không gian như **k-d tree**, **quadtree**, **octree** hoặc **R-tree**, nhiều điểm có thể được bỏ qua **theo cả nhóm** mà vẫn bảo đảm tìm đúng nghiệm.

Để bỏ một nhánh an toàn, ta phải trả lời câu hỏi: **Điểm gần nhất có thể tồn tại bên trong nhánh này cách truy vấn ít nhất bao nhiêu?** Câu trả lời là một **cận dưới khoảng cách** (*distance lower bound*). Nếu cận dưới của cả nhánh còn lớn hơn khoảng cách đến nghiệm tốt nhất hiện tại, không điểm nào trong nhánh có thể cải thiện nghiệm ấy.

Bài thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**: học cấu trúc dữ liệu qua bất biến, thao tác và đánh đổi thời gian–bộ nhớ. Nội dung tập trung vào tìm láng giềng gần nhất **chính xác** (*exact nearest neighbor*, NN), **k láng giềng gần nhất** (*kNN*), truy vấn bán kính, cắt nhánh bằng mặt chia và hộp bao, thuật toán branch-and-bound, các trường hợp biên cùng mã Python minh họa.

> **Nguyên tắc:** Chỉ được cắt một nhánh khi đã **chứng minh** cận dưới của mọi điểm trong nhánh không thể thắng nghiệm hiện có. Cận dưới quá nhỏ chỉ làm duyệt thừa; cận dưới bị tính **quá lớn** có thể khiến thuật toán bỏ sót nghiệm thật.

## 1. Phát biểu bài toán láng giềng gần nhất

Cho tập \(P=\{p_1,\ldots,p_n\}\subset\mathbb R^d\), điểm truy vấn \(q\in\mathbb R^d\) và một **metric** \(D\) (hàm khoảng cách) được chọn rõ ràng.

**Một láng giềng gần nhất (1-NN)** là điểm:

\[
\boxed{p^*\in\arg\min_{p\in P}D(q,p).}
\]

Nếu nhiều điểm cùng đạt khoảng cách nhỏ nhất, biểu thức \(\arg\min\) có thể chứa **nhiều nghiệm**. Hệ thống phải quyết định trả một nghiệm bất kỳ hay đặt **quy tắc phá hòa** ổn định.

Trong bài này, mỗi bản ghi có **ID chuỗi duy nhất**; nếu khoảng cách bằng nhau, chọn ID nhỏ hơn theo thứ tự từ điển. Khóa so sánh là:

\[
\boxed{\operatorname{rank}_q(p)=\bigl(D^2(q,p),\ \operatorname{ID}(p)\bigr)}
\]

khi sử dụng khoảng cách Euclid và bình phương khoảng cách để so sánh. Nếu hai bản ghi có cùng tọa độ nhưng ID khác nhau, chúng vẫn là **hai bản ghi khác nhau**.

**kNN** cần trả tối đa \(k\) bản ghi đầu tiên theo thứ tự khóa trên. Với \(k>n\), ví dụ trong bài trả toàn bộ \(n\) bản ghi; với \(k\le0\), API minh họa từ chối đầu vào.

**Truy vấn bán kính** với \(r\ge0\) trả tất cả điểm:

\[
\boxed{R(q,r)=\{p\in P:D(q,p)\le r\}.}
\]

Đừng nhầm ba bài toán:

| Truy vấn | Điều kiện đầu ra | Cần biết trước bán kính? |
| --- | --- | --- |
| 1-NN | Một bản ghi gần nhất, có tie-break | Không |
| kNN | K bản ghi gần nhất, có thứ tự | Không |
| Radius | Mọi bản ghi cách không quá r | Có |

Nếu không có điểm nào, 1-NN trả **None** và kNN/radius trả danh sách rỗng theo quy ước ví dụ Python.

### Mốc tham chiếu: duyệt tuyến tính

Với khoảng cách Euclid trong \(d\) chiều cố định, duyệt \(n\) điểm để lấy 1-NN có chi phí:

\[
\boxed{O(nd)}.
\]

Nếu cần kNN, có thể sắp toàn bộ điểm theo (distance², ID), chi phí \(O(nd+n\log n)\), hoặc giữ heap kích thước k, chi phí \(O(nd+n\log k)\) với \(k\ge1\). Dù không dùng chỉ mục, các thuật toán này có ưu thế **đơn giản và dễ kiểm chứng**, rất hữu ích làm chuẩn đối chiếu.

## 2. Metric nào đang được tối ưu?

Kết quả gần nhất **phụ thuộc vào định nghĩa khoảng cách**, không chỉ tọa độ hay cấu trúc cây.

Với \(p=(p_1,\ldots,p_d)\), \(q=(q_1,\ldots,q_d)\):

| Khoảng cách | Công thức | Hình học trong 2D |
| --- | --- | --- |
| Euclid \(L_2\) | \(\sqrt{\sum_i(p_i-q_i)^2}\) | Đường tròn đồng khoảng cách |
| Manhattan \(L_1\) | \(\sum_i|p_i-q_i|\) | Hình thoi |
| Chebyshev \(L_\infty\) | \(\max_i|p_i-q_i|\) | Hình vuông song song trục |
| Euclid có trọng số | \(\sqrt{\sum_i w_i(p_i-q_i)^2}\), \(w_i>0\) | Ellipse khi trọng số khác nhau |

Các metric này có thể tạo thứ tự láng giềng khác nhau. Ví dụ với \(q=(0,0)\), hai điểm \(A=(3,0)\), \(B=(2,2)\):

- Euclid: \(D_2(q,A)=3\), \(D_2(q,B)=\sqrt8\), nên **B gần hơn**.
- Manhattan: \(D_1(q,A)=3\), \(D_1(q,B)=4\), nên **A gần hơn**.

Do đó, **không được tính cận dưới theo một metric rồi tự dùng nó như cận dưới của metric khác** nếu chưa chứng minh bất đẳng thức cần thiết.

### Vì sao thường dùng bình phương khoảng cách Euclid?

\[
\boxed{D_2^2(q,p)=\sum_{i=1}^{d}(q_i-p_i)^2.}
\]

Vì hàm căn bậc hai **đơn điệu tăng** trên các số không âm:

\[
D_2(q,a)<D_2(q,b)
\iff D_2^2(q,a)<D_2^2(q,b).
\]

Ta so sánh các **bình phương khoảng cách**, tránh tính căn trong vòng lặp nóng. Nếu API cần trả khoảng cách theo đơn vị thực, có thể lấy căn khi trả kết quả.

**Chú ý số học:** Dù các tọa độ đầu vào là float hữu hạn, bình phương hiệu cực lớn vẫn có thể tràn thành vô cực hoặc mất độ chính xác. Với dữ liệu cực trị, cần kiểm soát miền tọa độ, kiểu số hoặc thuật toán số học ổn định; không coi kiểm tra “đầu vào hữu hạn” là đủ cho mọi phép tính.

## 3. AABB và cận dưới khoảng cách \(\operatorname{minDist}\)

**AABB** (*axis-aligned bounding box*) là hộp có các cạnh song song với trục. Trong \(d\) chiều, một hộp **đóng**:

\[
\boxed{B=\prod_{i=1}^{d}[lo_i,hi_i],\qquad lo_i\le hi_i.}
\]

Giả sử **mọi điểm trong một cây con** đều thuộc B. Ta cần cận dưới khoảng cách từ q tới **bất kỳ** điểm nào trong B.

Đối với Euclid, trên từng trục i, xác định:

\[
\delta_i(q,B)=
\begin{cases}
lo_i-q_i,&q_i<lo_i,\\
0,&lo_i\le q_i\le hi_i,\\
q_i-hi_i,&q_i>hi_i.
\end{cases}
\]

Khi đó:

\[
\boxed{\operatorname{minDist}_2^2(q,B)
=\sum_{i=1}^{d}\delta_i(q,B)^2.}
\]

Đây là **khoảng cách bình phương từ q tới điểm gần nhất trong toàn bộ hộp B**. Vì B **bao** tập điểm thực của cây con, ta có:

\[
\boxed{\forall p\in\operatorname{subtree}(B):
D_2^2(q,p)\ge\operatorname{minDist}_2^2(q,B).}
\]

### Tại sao công thức đúng?

Trên một trục, ta chỉ có thể chọn tọa độ bên trong \([lo_i,hi_i]\). Giá trị trong khoảng gần \(q_i\) nhất chính là:

\[
c_i=\min\bigl(\max(q_i,lo_i),hi_i\bigr).
\]

Đây là phép **clamp** (kẹp) tọa độ vào khoảng. Mọi giá trị \(x_i\in[lo_i,hi_i]\) thỏa:

\[
|q_i-x_i|\ge|q_i-c_i|=\delta_i.
\]

Bình phương và cộng từng trục:

\[
\sum_i(q_i-x_i)^2\ge\sum_i\delta_i^2.
\]

Do \(c=(c_1,\ldots,c_d)\) nằm trong B, cận dưới này còn là **khoảng cách tới một điểm của chính B**, nên là khoảng cách nhỏ nhất tới hộp.

**Nhưng điểm c có thể không phải là một bản ghi đang lưu.** Vì thế minDist là cận dưới cho cây con, **không** phải lời khẳng định có một bản ghi thật đúng tại vị trí c.

### Ví dụ số học 2D

Cho \(q=(1,4)\), \(B=[3,6]\times[2,5]\).

- Trục x: q nằm bên trái hộp, \(\delta_x=3-1=2\).
- Trục y: \(4\in[2,5]\), \(\delta_y=0\).

Vậy:

\[
\boxed{\operatorname{minDist}_2^2(q,B)=2^2+0^2=4.}
\]

Tất cả điểm thực trong B cách q **ít nhất 2**, nhưng chưa biết có điểm nào cách đúng 2 hay không.

### Ba trường hợp cần nhớ

**q ở trong B:** \(\delta_i=0\) mọi trục, nên \(\operatorname{minDist}=0\). Không có nghĩa B chứa một bản ghi đúng tại q.

**q nằm ngoài B:** ít nhất một \(\delta_i>0\); ta tính tổng bình phương các khoảng cách thiếu trên từng trục.

**B suy biến:** ví dụ \([4,4]\times[7,7]\) chứa một điểm hình học; công thức vẫn đúng và cho khoảng cách từ q tới điểm ấy.

## 4. Quy tắc cắt nhánh an toàn

Giả sử đã tìm thấy một bản ghi có bình phương khoảng cách:

\[
\boxed{best^2=D_2^2(q,p_{\mathrm{best}}).}
\]

Với cây con có hộp bao B, nếu:

\[
\boxed{\operatorname{minDist}_2^2(q,B)>best^2,}
\]

thì **mọi điểm** trong cây con đều có khoảng cách bình phương **lớn hơn** nghiệm hiện tại. Ta có thể bỏ toàn bộ cây con mà vẫn giữ nghiệm tốt nhất.

Đây là kỹ thuật **branch-and-bound**: *bound* là cận dưới của nhánh; *branch* là lựa chọn tiếp tục mở một nhánh còn khả năng tốt hơn.

### Vì sao không dùng dấu \(\ge\) tùy tiện?

Nếu minDist² **bằng** best², nhánh vẫn có thể chứa điểm **cùng khoảng cách** với best. Nếu bài toán chỉ yêu cầu một NN bất kỳ, việc bỏ nhánh bằng khoảng cách có thể vẫn hợp lệ. Nhưng bài này quy định:

\[
\operatorname{rank}_q(p)=(D_2^2(q,p),ID),
\]

nên điểm cùng khoảng cách với **ID nhỏ hơn** phải được ưu tiên. Chỉ từ AABB, ta chưa biết ID của điểm gần nhất trong nhánh. Vì vậy quy tắc đơn giản và an toàn là:

\[
\boxed{\text{Prune nếu }minDist^2>best^2,\text{ không prune nếu bằng.}}
\]

### Ví dụ prune và không prune

Nếu \(best^2=9\):

| minDist² của nhánh | Quyết định | Giải thích |
| ---: | --- | --- |
| 16 | **Bỏ** | Mọi điểm trong nhánh xa hơn best |
| 9 | **Giữ để xét tie** | Có thể có ID tốt hơn ở cùng khoảng cách |
| 4 | **Giữ** | Nhánh có thể chứa điểm gần hơn |
| 0 | **Giữ** | Hộp chứa q, nhưng chưa chắc có điểm ngay tại q |

**Cận dưới sai làm sai kết quả:** nếu B không thực sự bao điểm của cây con, phép prune có thể bỏ cả nhánh chứa nghiệm thật. Vì vậy hộp bao và quy tắc cập nhật chỉ mục là phần của **bất biến tính đúng**, không chỉ là metadata tối ưu.

## 5. Cận theo mặt chia của k-d tree

**K-d tree** phân chia điểm theo một trục ở từng nút. Với nút có trục \(j\) và tọa độ pivot \(s\), giả sử cây giữ bất biến hình học:

\[
\forall p\in Left,\ p_j\le s,\qquad
\forall p\in Right,\ p_j\ge s.
\]

Bất biến yếu này vẫn đúng nếu các điểm bằng s được phân trái/phải theo **ID**. Nó đủ để suy ra cận từ mặt phẳng chia (*splitting plane*).

### Thăm nhánh gần trước

- Nếu \(q_j<s\), chọn **nhánh trái** trước, nhánh phải là nhánh xa.
- Nếu \(q_j>s\), chọn **nhánh phải** trước, nhánh trái là nhánh xa.
- Nếu \(q_j=s\), có thể chọn một nhánh theo quy tắc cố định; cận theo mặt chia của nhánh còn lại bằng 0, nên không được loại chỉ vì mặt chia.

Nếu \(q_j<s\), mọi điểm nhánh phải đều có \(p_j\ge s\), vì vậy:

\[
D_2^2(q,p)=\sum_i(q_i-p_i)^2
\ge(q_j-p_j)^2\ge(s-q_j)^2.
\]

Tương tự, nếu \(q_j>s\), mọi điểm nhánh trái có \(p_j\le s\), nên:

\[
\boxed{D_2^2(q,p)\ge(q_j-s)^2.}
\]

Do đó, với **nhánh xa**:

\[
\boxed{lowerBound_{\mathrm{plane}}^2=(q_j-s)^2.}
\]

Sau khi đã duyệt nhánh gần và cập nhật best, có thể **bỏ nhánh xa** khi:

\[
\boxed{(q_j-s)^2>best^2.}
\]

### Vì sao chỉ so một trục đã đủ để prune?

Khoảng cách Euclid bình phương là tổng các số không âm. Chỉ riêng **một thành phần** đã lớn hơn best² thì tổng chắc chắn lớn hơn best². Nhưng nếu thành phần theo trục chia nhỏ, các trục còn lại vẫn có thể khiến mọi điểm rất xa: cận mặt chia khi đó **an toàn nhưng lỏng**.

### Khi nào cận mặt chia không dùng được?

Nếu node không thực sự phân hoạch theo \(p_j\le s\) ở trái và \(p_j\ge s\) ở phải, ta không được dùng bất đẳng thức trên. Chẳng hạn một cấu trúc chỉ nhóm các hộp bao chồng lấp mà không có quan hệ trái/phải theo trục thì cần **AABB của nhánh** hoặc một cận khác được chứng minh từ metadata thật.

**Chú ý:** Xét nhánh gần trước chỉ là **thứ tự heuristic**. Không được tự dừng sau nhánh gần khi nhánh xa còn có cận dưới \(\le best^2\).

## 6. Cận AABB so với cận mặt chia

Cận từ mặt chia chỉ kiểm tra khoảng cách theo **một trục**. Nếu lưu AABB bao các điểm của cả cây con, minDist sử dụng **mọi trục**, thường cho cận mạnh hơn.

Cho truy vấn \(q=(6,6)\), mặt chia theo x tại \(s=4\). Giả sử nhánh xa (phía x nhỏ hơn) có AABB:

\[
B=[0,4]\times[0,2].
\]

Cận theo mặt chia:

\[
lowerBound_{\mathrm{plane}}^2=(6-4)^2=4.
\]

Cận theo AABB:

\[
\operatorname{minDist}_2^2(q,B)
=(6-4)^2+(6-2)^2=4+16=\boxed{20}.
\]

Nếu best²=9:

- Theo **mặt chia**, \(4\le9\), chưa thể loại.
- Theo **AABB**, \(20>9\), bỏ được cả nhánh.

Hộp bao cho biết nhánh cũng cách xa theo **y**; điều này làm cận chặt hơn.

### Có phải minDist AABB luôn lớn hơn cận mặt chia?

Nếu AABB thật sự chứa các điểm nhánh và nhánh đúng nằm toàn phía xa của mặt chia, thì mỗi điểm trong AABB có tọa độ theo trục chia thuộc phía xa; khi đó khoảng cách tối thiểu tới AABB trên trục này ít nhất bằng khoảng cách tới mặt chia. Do đó minDist AABB **không yếu hơn** cận mặt chia trong bối cảnh đó.

Nhưng nếu metadata AABB là **hộp nới rộng bảo thủ** (vẫn bao điểm thật nhưng lấn qua mặt chia), nó có thể tạo cận **nhỏ hơn** cận từ mặt chia. Vẫn có thể dùng:

\[
\boxed{lowerBound^2=\max\bigl(
lowerBound_{\mathrm{plane}}^2,\
lowerBound_{\mathrm{AABB}}^2
\bigr)}
\]

**chỉ khi cả hai cận đều đã được chứng minh độc lập là cận dưới hợp lệ** cho đúng nhánh.

### AABB của nút không đồng nghĩa vùng phân hoạch

Một cây con có thể có miền phân hoạch rất rộng nhưng chỉ chứa điểm trong một cụm nhỏ. AABB tính từ điểm thường **chặt hơn** vùng phân hoạch, tăng hiệu quả cắt tỉa.

Tuy vậy, duy trì AABB tốn thêm \(O(d)\) số tọa độ cho mỗi nút và chi phí cập nhật. Nếu dữ liệu thay đổi thường xuyên, cần cân nhắc chi phí duy trì so với số lần truy vấn được tăng tốc.

## 7. Thuật toán DFS branch-and-bound cho 1-NN

Một thuật toán phổ biến là **duyệt sâu** (*depth-first search*, DFS), cập nhật ứng viên hiện tại và cắt tỉa theo AABB.

Mỗi nút k-d tree có:

- Một điểm pivot với ID.
- Cây con trái và phải.
- Hộp bao AABB của toàn bộ cây con **kể cả pivot**.

Thuật toán:

~~~text
NEAREST(root, q):
    best = None

    VISIT(node):
        nếu node rỗng:
            return

        nếu best tồn tại và
           minDistSquared(q, node.bbox) > best.distanceSquared:
            return    // Cả cây con không thể thắng.

        candidate = (distanceSquared(q, node.point), node.point.ID)
        nếu candidate tốt hơn best theo (dist², ID):
            best = candidate

        children = các con không rỗng của node
        duyệt con có minDistSquared nhỏ hơn trước
        với mỗi child trong children:
            VISIT(child)

    VISIT(root)
    return best
~~~

### Chứng minh tính đúng của DFS

Tại mọi thời điểm, best là một **điểm đã thực sự thấy trong dữ liệu**. Vì vậy khoảng cách tới best là một **cận trên** của khoảng cách NN tối ưu:

\[
\boxed{D^2(q,p^*)\le best^2.}
\]

Nếu một nhánh có minDist² \(>best^2\), mọi điểm trong nhánh xa hơn best, nên bỏ nhánh không thể loại nghiệm tốt hơn. Tất cả nhánh **không bị loại** cuối cùng được xét, nên best trả về là NN chính xác.

Việc xử lý ID khi khoảng cách bằng nhau cần **so sánh cả cặp** \((dist^2,ID)\) khi cập nhật best. Cắt tỉa chỉ khi minDist² \(>best^2\), nên không bỏ điểm có thể cùng khoảng cách và ID tốt hơn.

### Vì sao duyệt vùng gần trước?

Giả sử đã tìm được một điểm cách 2 và sau đó gặp nhánh có minDist=3. Ta bỏ được nhánh ấy. Nếu duyệt một vùng xa trước, best có thể vẫn là 10, khi đó không bỏ được nhánh có cận 3; phải thăm nhiều node hơn.

**Thứ tự duyệt ảnh hưởng tốc độ, không ảnh hưởng đáp án chính xác**, miễn là quy tắc prune và cập nhật best đúng.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Thăm nút hoặc vùng B"] --> B{"Đã có best và minDist²(B) > best²?"}
    B -->|Có| C["Bỏ toàn bộ cây con"]
    B -->|Không| D["Tính khoảng cách tới pivot"]
    D --> E["Cập nhật best theo (dist², ID)"]
    E --> F["Sắp thứ tự con theo minDist tăng dần"]
    F --> G["Đệ quy những nhánh còn có thể cải thiện best"]
~~~

## 8. Ví dụ tính tay trên một k-d tree

Cho sáu bản ghi 2D:

| ID | Điểm |
| --- | --- |
| A | \((1,1)\) |
| B | \((2,3)\) |
| C | \((4,5)\) |
| D | \((5,2)\) |
| E | \((8,8)\) |
| F | \((9,2)\) |

Xây bằng trung vị, chọn **x ở gốc** rồi **y ở mức kế tiếp**:

~~~text
                         D=(5,2), axis x
                        /                \
                 B=(2,3), axis y    E=(8,8), axis y
                  /        \               /
              A=(1,1)    C=(4,5)       F=(9,2)
~~~

Với dữ liệu trên, các hộp bao là:

- **Cây con trái của D:** \(B_L=[1,4]\times[1,5]\).
- **Cây con phải của D:** \(B_R=[8,9]\times[2,8]\).
- **Gốc D:** \(B_{\mathrm{root}}=[1,9]\times[1,8]\).

### Truy vấn \(q=(6,3)\)

Tính khoảng cách đến pivot gốc D:

\[
D_2^2(q,D)=(6-5)^2+(3-2)^2=1+1=\boxed{2}.
\]

Best hiện là D với best²=2.

Đối với **trái**:

\[
\operatorname{minDist}_2^2(q,B_L)
=(6-4)^2+0^2=\boxed{4}>2.
\]

Đối với **phải**:

\[
\operatorname{minDist}_2^2(q,B_R)
=(8-6)^2+0^2=\boxed{4}>2.
\]

**Cả hai cây con bị loại ngay tại gốc.** Đáp án là **D**, và thuật toán chỉ cần tính khoảng cách thật tới D.

Để kiểm tra, bình phương khoảng cách thật tới các điểm còn lại:

| ID | \(D_2^2((6,3),p)\) |
| --- | ---: |
| A | 29 |
| B | 16 |
| C | 8 |
| D | **2** |
| E | 29 |
| F | 10 |

Đáp án khớp với quét toàn bộ tập điểm, nhưng chỉ mục đã tránh đọc khoảng cách thật tới năm điểm còn lại.

### Truy vấn \(q=(7,3)\) và tie

Tại gốc D:

\[
D_2^2((7,3),D)=(7-5)^2+(3-2)^2=\boxed{5}.
\]

Cây con trái có minDist² \((7-4)^2=9>5\), nên bỏ. Cây con phải có minDist² \((8-7)^2=1\), phải xét. Trong cây con ấy, F=(9,2) có:

\[
D_2^2((7,3),F)=(7-9)^2+(3-2)^2=\boxed{5}.
\]

F và D **cùng khoảng cách**, nhưng ID **D** nhỏ hơn **F**, vì vậy kết quả với quy tắc tie là **D**. Ví dụ cho thấy một nhánh có cận nhỏ hơn best không nhất thiết chứa nghiệm tốt hơn; nó chỉ **có khả năng** và cần được kiểm tra.

**Phân biệt hai số:** \(\operatorname{minDist}(q,B)\) là cận hình học của **cả hộp**, còn \(D(q,p)\) là khoảng cách thật tới **một bản ghi**. Không được thay best bằng minDist của hộp vì hộp có thể không chứa điểm dữ liệu ở vị trí gần nhất.

## 9. kNN: giữ k ứng viên thay vì một best

Với kNN, không thể chỉ giữ một bản ghi tốt nhất. Ta cần một tập \(S\) gồm **tối đa k điểm tốt nhất đã gặp**, xét theo thứ tự:

\[
\boxed{\bigl(D_2^2(q,p),\operatorname{ID}(p)\bigr).}
\]

Một lựa chọn là **max-heap** kích thước k, trong đó đỉnh là phần tử **tệ nhất** trong S: có khoảng cách lớn nhất; nếu khoảng cách bằng nhau thì có ID lớn hơn.

### Cập nhật heap

Với điểm p mới:

1. Nếu heap đang có **ít hơn k** phần tử, thêm p.
2. Nếu đã đủ k phần tử, so p với phần tử tệ nhất trên đỉnh.
3. Nếu p **tốt hơn** phần tử tệ nhất theo \((dist^2,ID)\), bỏ phần tử tệ nhất rồi thêm p.
4. Nếu không tốt hơn, bỏ p.

Một heap kích thước k cần \(O(k)\) bộ nhớ, mỗi lần thêm hoặc thay có thể tốn \(O(\log k)\).

### Khi nào được cắt nhánh?

**Khi heap chưa đủ k điểm**, chưa thể kết luận một nhánh xa không cần thiết: nhánh đó có thể chứa **điểm thứ k**.

Khi heap đủ k điểm, gọi \(\tau^2\) là khoảng cách bình phương của **phần tử tệ nhất** trong heap. Nếu:

\[
\boxed{\operatorname{minDist}_2^2(q,B)>\tau^2,}
\]

không điểm nào trong B có thể lọt vào top-k, nên loại nhánh.

Trường hợp **bằng** \(\tau^2\) vẫn cần xét khi tie theo ID chưa được giải quyết; một điểm cùng khoảng cách nhưng ID nhỏ hơn có thể đẩy phần tử tệ nhất ra.

### Ví dụ k=3

Giả sử các ứng viên đã thấy:

| ID | Khoảng cách bình phương |
| --- | ---: |
| A | 1 |
| B | 4 |
| C | 9 |

Heap có đủ 3 điểm, ngưỡng \(\tau^2=9\).

- Nhánh với minDist²=16: **bỏ**, vì không điểm nào có dist² nhỏ hơn 16.
- Nhánh với minDist²=8: **phải xét**, có thể thay C.
- Nhánh với minDist²=9: **phải xét tie**, có thể chứa ID đứng trước C.

Nếu mới có A và B (heap chưa đủ 3), thậm chí nhánh minDist²=100 vẫn có thể chứa điểm thứ ba duy nhất; không được prune theo ngưỡng của B khi chưa đủ kết quả.

### Khi k lớn hơn n

Nếu \(k>n\), heap không bao giờ đạt k, thuật toán sẽ xét đủ tất cả điểm và trả **n bản ghi**, theo thứ tự đã chọn. Đây là một quy tắc API hợp lý; một API khác có thể từ chối k>n, nhưng phải ghi rõ để người dùng không hiểu nhầm.

## 10. Best-first search: luôn mở vùng có cận dưới nhỏ nhất

DFS không phải cách duyệt duy nhất. Một chiến lược khác là **best-first search**: dùng **min-heap của các vùng chưa duyệt**, sắp theo \(\operatorname{minDist}_2^2(q,B)\).

### Các bước với 1-NN

1. Đưa vùng gốc vào heap ưu tiên, khóa là minDist² của nó.
2. Lấy vùng có **cận dưới nhỏ nhất** ra.
3. Nếu đã có best và cận vùng \(>best^2\), có thể kết thúc: mọi vùng **còn lại** đều có cận không nhỏ hơn vùng này.
4. Nếu chưa thể kết thúc, xử lý pivot/điểm thuộc vùng, cập nhật best.
5. Đưa các cây con không rỗng vào heap với minDist² của chúng.
6. Lặp tới khi heap rỗng hoặc mọi vùng còn lại đã được chứng minh không thể cải thiện.

~~~text
frontier = minHeap()
push(frontier, (minDistSquared(root.box, q), root))
best = None

while frontier not empty:
    bound, node = popMin(frontier)

    if best exists and bound > best.distanceSquared:
        break

    consider(node.point)
    for child in node.children:
        if child exists:
            push(frontier, (minDistSquared(child.box,q), child))

return best
~~~

### Vì sao được dừng cả vòng lặp?

Giả sử vùng có cận **nhỏ nhất trong frontier** đã có \(bound>best^2\). Mọi vùng khác trong frontier đều có cận \(\ge bound>best^2\), nên không vùng nào chứa điểm thắng best. Các điểm chưa thăm đều thuộc một vùng trong frontier; do đó kết thúc an toàn.

**Không nhầm heap vùng với heap top-k:** với kNN best-first, có thể cần **hai cấu trúc riêng**:

- **Min-heap vùng**: ưu tiên cận dưới **nhỏ nhất** để khám phá.
- **Max-heap ứng viên**: giữ k điểm thật đã gặp, với phần tử **tệ nhất** trên đỉnh.

Khi kNN đã đủ k ứng viên, điều kiện kết thúc tương tự: cận nhỏ nhất còn lại **lớn hơn** khoảng cách của phần tử thứ k hiện tại, nếu vẫn xử lý tie theo ID.

### Đánh đổi với DFS

| Tiêu chí | DFS nhánh gần trước | Best-first |
| --- | --- | --- |
| Tổ chức duyệt | Đệ quy/stack | Min-heap các vùng |
| Bộ nhớ phụ | \(O(h)\) stack với cây cao h | Tới \(O(V)\) vùng chờ trong trường hợp xấu |
| Chi phí quản lý vùng | Thường nhỏ | Có \(O(\log V)\) cho push/pop |
| Thứ tự thăm | Ưu tiên cục bộ theo nhánh | Ưu tiên toàn cục theo cận AABB |
| Có bảo đảm NN chính xác? | Có, nếu cận và prune đúng | Có, nếu cận và dừng đúng |

Best-first có thể tìm ứng viên gần tốt nhanh hơn trên một số dữ liệu, nhưng overhead heap có thể làm chậm trên dữ liệu nhỏ hoặc cây được phân vùng rất phù hợp với DFS. **Cần benchmark**, không có lựa chọn thắng tuyệt đối.

## 11. Truy vấn bán kính dùng chính cận dưới ấy

Nếu bài toán không hỏi “gần nhất” mà hỏi “mọi điểm trong bán kính \(r\)”, điều kiện xét điểm là:

\[
\boxed{D_2^2(q,p)\le r^2.}
\]

Nhánh có AABB B bị loại khi:

\[
\boxed{\operatorname{minDist}_2^2(q,B)>r^2.}
\]

Điều này gần giống 1-NN nhưng **ngưỡng r cố định**, không thay đổi khi ta tìm được điểm mới.

~~~text
RADIUS(node, q, r²):
    nếu node rỗng: return

    nếu minDistSquared(node.box, q) > r²:
        return

    nếu distanceSquared(node.point, q) <= r²:
        xuất node.point

    RADIUS(node.left, q, r²)
    RADIUS(node.right, q, r²)
~~~

**Điểm trên đường tròn** có bình phương khoảng cách đúng bằng \(r^2\) được trả. Vì vậy prune dùng \(>\), không dùng \(\ge\).

### Bắt đầu từ hộp vuông có được không?

Có thể trước hết lấy AABB \([q_x-r,q_x+r]\times[q_y-r,q_y+r]\), dùng range query để lọc ứng viên rồi kiểm tra khoảng cách tròn. Cách này đúng nếu xử lý **biên đóng** nhất quán, nhưng có thể duyệt dư điểm gần góc hộp. Truy vấn trực tiếp bằng minDist tới AABB các nhánh có thể prune chặt hơn cho hình tròn.

### Khi \(r=0\)

Kết quả radius gồm tất cả bản ghi có tọa độ **đúng bằng q** theo metric Euclid, có thể gồm nhiều ID. Không được mặc định kết quả chỉ có một điểm vì 1-NN luôn trả một bản ghi.

## 12. Ứng dụng vào quadtree, octree và R-tree

Ý tưởng minDist **không riêng k-d tree**. Chỉ cần một node cung cấp **miền bao tất cả đối tượng trong cây con**, ta có thể sử dụng cận dưới thích hợp.

| Chỉ mục | Metadata vùng | Cách cắt tỉa NN |
| --- | --- | --- |
| k-d tree | AABB của điểm trong cây con hoặc vùng phân hoạch | Bỏ nhánh nếu minDist² > best² |
| PR quadtree 2D | Hình chữ nhật mỗi vùng/nút | Bỏ vùng có cận dưới quá xa |
| Octree 3D | AABB khối hộp 3D | Dùng cả ba trục x,y,z |
| R-tree | Minimum bounding rectangle/box (MBR) của các nhánh | Dùng minDist tới MBR để ưu tiên và prune |
| Lưới đều/spatial hash | Biên của mỗi ô | Bỏ ô khi cận dưới ô > ngưỡng |

### K-d tree

K-d tree thường lưu **một pivot mỗi node**, nên khi thăm node phải kiểm tra pivot ngay cả khi hai cây con bị prune. AABB node phải bao **cả pivot và mọi hậu duệ**.

### Quadtree/octree

Các node có thể chỉ đại diện một vùng, còn **điểm nằm ở lá**. Khi cận dưới vùng lớn hơn best, bỏ nguyên vùng; khi tới lá, kiểm tra những điểm thật trong bucket. Với vùng **nửa mở**, ta có thể dùng **bao đóng** của vùng để tính cận dưới an toàn: cận có thể nhỏ hơn khoảng cách đạt được thật, nhưng không khiến bỏ sót.

### R-tree

MBR của một nhánh có thể **chồng lấp** MBR của nhánh khác. Không có bảo đảm “chỉ đi đúng một nhánh” như tìm khóa trong BST. Phải xét tất cả MBR có khả năng cải thiện best.

Nếu lá R-tree chứa **đối tượng hình học** (đoạn thẳng, đa giác) chứ không phải điểm, khoảng cách tới MBR chỉ là **cận dưới của khoảng cách tới hình thật**. Muốn trả đối tượng gần nhất chính xác phải tính khoảng cách tới **hình gốc** khi đánh giá ứng viên, không chỉ khoảng cách tới MBR.

### Vùng có vật thể lớn, đăng ký nhiều lá

Nếu cùng một đối tượng xuất hiện ở nhiều bucket hoặc nhiều lá, truy vấn kNN/radius phải **khử trùng theo ID**. Việc một đối tượng được đọc hai lần không có nghĩa nó là hai láng giềng khác nhau.

**Bất biến chung:** Một nhánh bị prune phải có vùng bao đúng mọi điểm/đối tượng mà nó đại diện và cận dưới phải hợp lệ theo **metric truy vấn thực sự dùng**.

## 13. Độ phức tạp: không nhầm chiều cao cây với chi phí NN

Đặt:

- \(n\): số bản ghi điểm.
- \(d\): số chiều tọa độ.
- \(V\): số node mà thuật toán thăm thật sự.
- \(h\): chiều cao cây.
- \(k\): số láng giềng cần trả.
- \(m\): số vùng đưa vào hàng đợi ưu tiên, nếu dùng best-first.

Với một node k-d tree lưu AABB và pivot, kiểm tra minDist², khoảng cách pivot và thứ tự hai con cần \(O(d)\) phép toán số học.

### Bảng chi phí điển hình

| Công việc | Chi phí tổng quát | Điều kiện |
| --- | --- | --- |
| Tính khoảng cách q–p | \(O(d)\) | Euclid |
| Tính minDist² q–AABB | \(O(d)\) | Đã có bbox |
| 1-NN DFS với \(V\) node thăm | \(O(dV)\) | Không sắp đầu ra |
| Radius với \(V\) node, k kết quả | \(O(dV+k)\) | Không sắp đầu ra |
| kNN DFS, heap k phần tử | \(O(dV+V\log k+k\log k)\) | k≥1, nếu sắp k kết quả |
| Best-first 1-NN | \(O(dm+m\log m)\) | m vùng xử lý/đẩy heap, cùng bậc số node được xét |
| Bộ nhớ metadata AABB cho k-d tree | \(O(nd)\) | Mỗi node chứa 2d cận |
| Bộ nhớ DFS | \(O(h)\) stack | Cây cân bằng có h \(O(\log n)\) |
| Bộ nhớ kNN | \(O(k+h)\) phụ | Heap ứng viên và stack DFS |

Với kNN và \(k>n\), có thể thay k bằng \(\min(k,n)\) khi phân tích số phần tử thực sự được lưu. Trong bảng, \(V\) không bao gồm việc duyệt tất cả điểm không cần thiết nhờ prune; nhưng trường hợp xấu **\(V=n\)** vẫn có thể xảy ra.

### Cây median cân bằng chưa đủ để bảo đảm NN \(O(\log n)\)

Khi xây một k-d tree bằng trung vị, đường đi từ gốc tới một lá có chiều dài \(O(\log n)\). Nhưng tìm NN khác tìm kiếm một khóa BST:

- Một cây con gần mặt chia có thể chứa điểm gần q hơn điểm đã thấy.
- Để bảo đảm chính xác, có thể phải quay lại **nhiều** cây con.
- Khi cận dưới của nhiều vùng nhỏ hoặc bằng best², thuật toán không được bỏ chúng.

Vì vậy NN có **trường hợp xấu \(O(nd)\)**, tương đương quét tuyến tính về bậc thời gian nếu mọi node bị xét.

### Xây cây và chi phí bộ nhớ

Một cách xây k-d tree tĩnh là:

1. Chọn trục ở mỗi node.
2. Sắp tập con theo \((tọa độ\ trên\ trục,ID)\).
3. Lấy trung vị, đệ quy trái/phải.
4. Tính AABB bottom-up.

Nếu **sắp lại tại mỗi node**, với d cố định, cây median có chi phí xây khoảng:

\[
\boxed{O(n\log^2 n).}
\]

Có các cách xây nhanh hơn bằng median selection hoặc duy trì danh sách sắp, nhưng không gán chi phí tối ưu ấy cho mã minh họa sắp lại trên từng tập con.

### Số kết quả là giới hạn dưới

Nếu truy vấn radius trả 100.000 điểm, riêng việc xuất đủ ID đã cần \(\Omega(100\,000)\) công việc. Nếu kNN trả k bản ghi, việc xuất k bản ghi cần \(\Omega(k)\), dù chỉ mục xác định được tập kết quả rất nhanh.

## 14. Cận dưới thay đổi thế nào với metric khác?

Đừng dùng công thức Euclid một cách máy móc nếu ứng dụng tối ưu khoảng cách khác.

Với mỗi trục, giữ:

\[
\delta_i=\max(lo_i-q_i,\ 0,\ q_i-hi_i)
\]

cho hộp AABB đóng. Khi đó:

**Manhattan \(L_1\):**

\[
\boxed{\operatorname{minDist}_1(q,B)=\sum_i\delta_i.}
\]

**Chebyshev \(L_\infty\):**

\[
\boxed{\operatorname{minDist}_\infty(q,B)=\max_i\delta_i.}
\]

**Euclid trọng số, \(w_i>0\):**

\[
\boxed{\operatorname{minDist}_{2,w}^2(q,B)=\sum_iw_i\delta_i^2.}
\]

Các công thức này là cận dưới hợp lệ vì hộp AABB tách độc lập theo các trục, và mỗi khoảng tọa độ đóng đều có điểm gần \(q_i\) nhất là clamp.

### Với bán kính Manhattan

Nếu \(r=3\) theo \(L_1\), một nhánh có \(\sum_i\delta_i>3\) chắc chắn không chứa điểm thuộc bán kính. Dùng \(\sum_i\delta_i^2>r^2\) thay cho phép kiểm tra L1 không được tự coi là cùng một truy vấn.

### Với khoảng cách địa lý

Kinh độ/vĩ độ thường tính bằng **độ góc**. Bình phương hiệu kinh độ và vĩ độ không tự là khoảng cách mét; sự biến dạng còn tùy vĩ độ và đường đổi ngày.

Muốn NN theo **khoảng cách địa lý**, cần:

- Xác định CRS, thứ tự trục, mô hình cầu/ellipsoid và độ chính xác yêu cầu.
- Dùng hàm khoảng cách địa lý phù hợp (ví dụ great-circle trên cầu hoặc ellipsoid).
- Thiết kế **cận dưới khoảng cách địa lý** hợp lệ cho từng vùng; nếu chưa có cận đúng, không được dùng Euclid trên độ để prune như thể đang đo mét.

Một giải pháp thực dụng cho vùng nhỏ là **chiếu sang hệ tọa độ phẳng thích hợp** và kiểm soát sai số phép chiếu. Nhưng nếu bài toán yêu cầu NN chính xác theo một metric địa lý gốc, phải chứng minh việc chiếu/cận không thể làm đổi kết quả hoặc kiểm tra lại các ứng viên với metric thật.

### Dữ liệu có nhiều loại đơn vị

Một vector \((x,y,t)\) có thể trộn mét và giây. Không có ý nghĩa tự nhiên cho công thức \(x^2+y^2+t^2\) nếu chưa định nghĩa trọng số/chuẩn hóa. **Metric phải được xác định trước khi chọn cận dưới và trước khi đánh giá hiệu năng.**

## 15. Khi số chiều lớn và khi cần kết quả gần đúng

Trong không gian 2D/3D, hộp bao có thể loại được phần lớn dữ liệu trong các truy vấn thuận lợi. Nhưng khi d lớn:

1. Mỗi lần tính khoảng cách hoặc minDist cần xét \(d\) trục.
2. Nhiều hộp bao có minDist nhỏ mặc dù không chứa điểm gần q.
3. Các khoảng cách giữa nhiều điểm có thể tương đối gần nhau trong một số phân bố.
4. Thuật toán phải mở nhiều nhánh, khiến hiệu năng tiến gần quét toàn bộ.

Đây là một khía cạnh của **lời nguyền số chiều** (*curse of dimensionality*). Không thể kết luận k-d tree luôn nhanh cho vector 128 hoặc 768 chiều chỉ vì cây có chiều cao \(O(\log n)\).

### Exact NN và approximate NN

**Exact NN:** kết quả phải là nghiệm thực sự tốt nhất theo metric và quy tắc tie đã định.

**Approximate NN (ANN):** có thể chấp nhận một điểm không phải tốt nhất để tăng tốc, theo một bảo đảm hoặc thước đo chất lượng cụ thể. Hai hình thức thường gặp:

- **Bảo đảm xấp xỉ theo tỷ lệ:** nếu thuật toán hứa hệ số \(1+\varepsilon\), thì khoảng cách kết quả \(D(q,\hat p)\le(1+\varepsilon)D(q,p^*)\), với các giả thiết thích hợp.
- **Đo recall trên bộ truy vấn:** so những ID được ANN trả với tập kNN chính xác trên dữ liệu kiểm thử.

Nếu dùng cận khoảng cách để **dừng sớm**, phải suy ra quy tắc dừng từ **định nghĩa sai số được chấp nhận**, không chỉ dừng sau một số nhánh tùy ý rồi gọi là có bảo đảm.

Ví dụ với 1-NN, nếu đã có ứng viên cách q bằng \(best\) và mọi nhánh chưa mở có **cận dưới khoảng cách** \(\ge best/(1+\varepsilon)\), thì mọi điểm chưa xét có khoảng cách ít nhất bằng ngưỡng đó. Vì vậy kết quả hiện tại thỏa bảo đảm \(best\le(1+\varepsilon)\,D(q,p^*)\). Đây là cách hiểu toán học của một quy tắc dừng xấp xỉ, không có nghĩa mọi thuật toán ANN đều dùng chính cách này.

**Trường hợp khoảng cách tối ưu bằng 0** cần đặc biệt thận trọng: một điểm cách 0 là nghiệm chính xác; phép so sánh tỷ lệ không thể che lấp việc trả một điểm cách dương.

## 16. Cập nhật điểm và sai lệch hộp bao

Một k-d tree ban đầu có AABB đúng có thể trở thành **không đúng** sau khi thêm, xóa hoặc di chuyển điểm nếu metadata không được duy trì.

### Điểm di chuyển ra ngoài hộp cũ

~~~text
Trước: ID X ở (2,2), cây con có bbox [0,4] × [0,4]
Sau:   ID X đổi vị trí thành (20,20)
Nhưng: bbox vẫn [0,4] × [0,4]
~~~

Với truy vấn \(q=(20,20)\), minDist² tới bbox cũ là:

\[
(20-4)^2+(20-4)^2=256+256=512.
\]

Nếu đã thấy một ứng viên khác có best² nhỏ hơn 512, thuật toán có thể **bỏ nhánh chứa X** dù X thực sự cách q bằng 0. Đây là lỗi **false negative**, làm NN sai.

### Bbox nới rộng và bbox thu hẹp

**Bbox nới rộng** vẫn bao toàn bộ điểm trong nhánh thì phép cắt tỉa **đúng nhưng có thể chậm hơn**, vì minDist của bbox rộng thường nhỏ hơn.

**Bbox thu hẹp thiếu điểm** có thể tạo minDist quá lớn, khiến prune sai. Một số hệ thống cố tình dùng **loose bounds** để giảm tần suất cập nhật, nhưng vẫn phải bảo đảm hộp luôn chứa trọn dữ liệu thật.

### Tái cấu trúc sau cập nhật

Trong k-d tree động:

- Chèn: đưa điểm vào đúng nhánh theo khóa phân hoạch, **mở rộng AABB tổ tiên** và cập nhật metadata.
- Xóa: bỏ ID hoặc dùng tombstone, cập nhật AABB nếu cần và xử lý cân bằng.
- Di chuyển: thường coi như **xóa vị trí cũ + chèn vị trí mới**; chỉ sửa tọa độ tại node cũ có thể phá điều kiện phân hoạch.
- Nhiều lần cập nhật: cân nhắc **rebuild cây con hoặc toàn cây** để khôi phục chất lượng phân hoạch.

Nếu luồng truy vấn đọc cây trong lúc luồng cập nhật thay tọa độ và bbox, phải có khóa, phiên bản hoặc cơ chế snapshot nhất quán. **Duyệt trên một trạng thái nửa cũ nửa mới** có thể trả sai ngay cả khi công thức minDist hoàn toàn đúng.

## 17. Python: k-d tree tĩnh với minDist, NN, kNN và radius

Đoạn mã sau dùng **Python 3.10+** và thư viện chuẩn. Nó là một ví dụ **tự chứa**:

- Mỗi bản ghi gồm **ID chuỗi duy nhất** và tọa độ \(d\) chiều hữu hạn.
- Dựng cây tĩnh bằng **median split**; chọn trục **cyclic** hoặc **widest spread**.
- Lưu AABB của toàn bộ cây con **bao gồm pivot**, cùng số điểm.
- Tính cận minDist² tới AABB.
- Tìm **1-NN**, **kNN** và các điểm trong **bán kính đóng**.
- Phá hòa theo **ID** để kết quả ổn định.
- Có hàm validate kiểm tra bất biến chia, AABB và số điểm.

Mã cố ý ưu tiên tính dễ học hơn việc tối ưu thư viện sản xuất. Các phép khoảng cách dùng bình phương float; xem mục 20 về giới hạn số học.

~~~python
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappush, heapreplace
from math import isfinite


@dataclass(frozen=True)
class SpatialPoint:
    id: str
    coords: tuple[float, ...]


@dataclass
class KDNode:
    point: SpatialPoint
    axis: int
    lo: tuple[float, ...]
    hi: tuple[float, ...]
    size: int
    left: KDNode | None = None
    right: KDNode | None = None


class ExactKDIndex:
    def __init__(self, data, axis_strategy="cyclic"):
        if axis_strategy not in ("cyclic", "widest"):
            raise ValueError("axis_strategy phải là cyclic hoặc widest")

        points = []
        ids = set()
        dimension = None
        for item_id, raw_coords in data:
            if not isinstance(item_id, str) or not item_id:
                raise ValueError("ID phải là chuỗi không rỗng")
            if item_id in ids:
                raise ValueError("ID phải duy nhất")
            coords = tuple(float(v) for v in raw_coords)
            if not coords or not all(isfinite(v) for v in coords):
                raise ValueError("Tọa độ phải có chiều và hữu hạn")
            if dimension is None:
                dimension = len(coords)
            if len(coords) != dimension:
                raise ValueError("Mọi điểm phải có cùng số chiều")
            ids.add(item_id)
            points.append(SpatialPoint(item_id, coords))

        self.dimension = dimension or 0
        self.axis_strategy = axis_strategy
        # ID theo thứ tự từ điển dùng để phá hòa trong max-heap.
        self.id_rank = {
            item_id: rank
            for rank, item_id in enumerate(sorted(ids))
        }
        self.root = self._build(points, depth=0)

    def _axis(self, points, depth):
        if self.axis_strategy == "cyclic":
            return depth % self.dimension

        spreads = []
        for axis in range(self.dimension):
            values = [p.coords[axis] for p in points]
            spreads.append(max(values) - min(values))
        # Hai spread bằng nhau thì chọn index trục nhỏ hơn.
        return max(
            range(self.dimension),
            key=lambda axis: (spreads[axis], -axis)
        )

    def _build(self, points, depth):
        if not points:
            return None

        axis = self._axis(points, depth)
        ordered = sorted(
            points, key=lambda p: (p.coords[axis], p.id)
        )
        mid = len(ordered) // 2
        pivot = ordered[mid]
        left = self._build(ordered[:mid], depth + 1)
        right = self._build(ordered[mid + 1:], depth + 1)

        lo = list(pivot.coords)
        hi = list(pivot.coords)
        size = 1
        for child in (left, right):
            if child is not None:
                size += child.size
                for i in range(self.dimension):
                    lo[i] = min(lo[i], child.lo[i])
                    hi[i] = max(hi[i], child.hi[i])

        return KDNode(
            pivot, axis, tuple(lo), tuple(hi),
            size=size, left=left, right=right
        )

    def _query_vector(self, values):
        q = tuple(float(v) for v in values)
        if (len(q) != self.dimension
                or not all(isfinite(v) for v in q)):
            raise ValueError("Vector truy vấn sai chiều hoặc không hữu hạn")
        return q

    @staticmethod
    def _distance_sq(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))

    @staticmethod
    def _min_distance_sq(node, q):
        return sum(
            max(low - x, 0.0, x - high) ** 2
            for low, x, high in zip(node.lo, q, node.hi)
        )

    def nearest(self, raw_query):
        """Trả một SpatialPoint gần nhất; None khi chỉ mục rỗng."""
        if self.root is None:
            return None
        q = self._query_vector(raw_query)
        best_key = None
        best_point = None

        def visit(node):
            nonlocal best_key, best_point
            if node is None:
                return
            bound = self._min_distance_sq(node, q)
            if best_key is not None and bound > best_key[0]:
                return

            key = (
                self._distance_sq(node.point.coords, q),
                node.point.id,
            )
            if best_key is None or key < best_key:
                best_key = key
                best_point = node.point

            children = [
                c for c in (node.left, node.right)
                if c is not None
            ]
            children.sort(
                key=lambda c: self._min_distance_sq(c, q)
            )
            for child in children:
                visit(child)

        visit(self.root)
        return best_point

    def k_nearest(self, raw_query, k):
        """Trả tối đa k điểm, sắp theo (distance², ID)."""
        if type(k) is not int or k < 1:
            raise ValueError("k phải là số nguyên dương")
        if self.root is None:
            return []
        q = self._query_vector(raw_query)
        heap = []  # (-distance², -id_rank, SpatialPoint)

        def visit(node):
            if node is None:
                return

            bound = self._min_distance_sq(node, q)
            if len(heap) == k and bound > -heap[0][0]:
                return

            dist = self._distance_sq(node.point.coords, q)
            rank = self.id_rank[node.point.id]
            entry = (-dist, -rank, node.point)
            if len(heap) < k:
                heappush(heap, entry)
            else:
                worst = (-heap[0][0], -heap[0][1])
                if (dist, rank) < worst:
                    heapreplace(heap, entry)

            children = [
                c for c in (node.left, node.right)
                if c is not None
            ]
            children.sort(
                key=lambda c: self._min_distance_sq(c, q)
            )
            for child in children:
                visit(child)

        visit(self.root)
        return [
            entry[2]
            for entry in sorted(
                heap, key=lambda item: (-item[0], -item[1])
            )
        ]

    def radius(self, raw_query, radius):
        """Liệt kê mọi điểm có khoảng cách Euclid <= radius."""
        radius = float(radius)
        if not isfinite(radius) or radius < 0:
            raise ValueError("Bán kính phải hữu hạn và không âm")
        if self.root is None:
            return []
        q = self._query_vector(raw_query)
        threshold = radius * radius
        result = []

        def visit(node):
            if node is None:
                return
            if self._min_distance_sq(node, q) > threshold:
                return

            if self._distance_sq(node.point.coords, q) <= threshold:
                result.append(node.point)
            visit(node.left)
            visit(node.right)

        visit(self.root)
        return sorted(result, key=lambda p: p.id)

    def validate(self):
        """Kiểm tra ID, phân hoạch tại mọi tổ tiên, AABB và size."""
        seen = set()

        def visit(node, constraints):
            if node is None:
                return []

            if node.point.id in seen:
                raise AssertionError("ID xuất hiện nhiều lần")
            seen.add(node.point.id)

            for axis, pivot_key, left_side in constraints:
                key = (node.point.coords[axis], node.point.id)
                if left_side and not (key < pivot_key):
                    raise AssertionError("Sai phân hoạch nhánh trái")
                if not left_side and not (key > pivot_key):
                    raise AssertionError("Sai phân hoạch nhánh phải")

            pivot_key = (
                node.point.coords[node.axis], node.point.id
            )
            left_points = visit(
                node.left,
                constraints + [(node.axis, pivot_key, True)]
            )
            right_points = visit(
                node.right,
                constraints + [(node.axis, pivot_key, False)]
            )
            all_points = [node.point] + left_points + right_points

            if node.size != len(all_points):
                raise AssertionError("Sai subtree size")

            for axis in range(self.dimension):
                expected_lo = min(
                    p.coords[axis] for p in all_points
                )
                expected_hi = max(
                    p.coords[axis] for p in all_points
                )
                if (node.lo[axis] != expected_lo
                        or node.hi[axis] != expected_hi):
                    raise AssertionError("AABB không bao đúng cây con")
            return all_points

        records = visit(self.root, [])
        if len(records) != len(seen):
            raise AssertionError("ID thiếu hoặc trùng")
        return True
~~~

### Giải thích cấu trúc mã

**Xây median tree:** Mỗi node chọn một trục, sắp điểm theo tọa độ của trục đó và ID, chọn pivot giữa. Cây con trái/phải nhận những ID khác nhau, giúp cây có chiều cao \(O(\log n)\) theo số điểm khi dựng tĩnh.

**AABB bottom-up:** Bắt đầu từ tọa độ pivot, mở rộng theo min/max hai con. Mọi điểm của cây con nằm trong bbox node, nên minDist là cận dưới hợp lệ.

**nearest:** Duyệt các con theo minDist tăng dần, cập nhật best bằng cặp \((dist^2,ID)\). Không prune nhánh có cận bằng best² để giữ tie-break đúng.

**k_nearest:** Python cung cấp min-heap; mã lưu bộ ba \((-dist^2,-rank(ID),point)\) để phần tử **tệ nhất** trong k ứng viên có khóa nhỏ nhất và nằm ở đỉnh. Rank được tạo theo thứ tự tăng của ID, nên không có hai ID khác nhau cùng rank.

**radius:** Mỗi bản ghi nằm ở một node, nên không cần dedup. Nếu một cấu trúc khác đăng ký một vật thể vào nhiều bucket, cần có tập seen ID.

**validate:** Dùng để kiểm tra học thuật, có thể tốn nhiều thời gian và bộ nhớ hơn các truy vấn bình thường vì thu thập toàn bộ điểm của các cây con. Không nên gọi validate sau mỗi truy vấn trong hệ thống cần độ trễ thấp.

## 18. Python: kiểm chứng với quét tuyến tính

Đoạn tiếp theo **nối tiếp** các lớp đã khai báo ở mục 17. Ta dùng chính dữ liệu của ví dụ tính tay ở mục 8, kiểm tra các trường hợp hòa khoảng cách, trùng tọa độ, truy vấn bán kính 0, tập rỗng và dữ liệu 3D.

~~~python
from heapq import nsmallest


samples = [
    ("A", (1, 1)),
    ("B", (2, 3)),
    ("C", (4, 5)),
    ("D", (5, 2)),
    ("E", (8, 8)),
    ("F", (9, 2)),
]

cyclic = ExactKDIndex(samples, axis_strategy="cyclic")
widest = ExactKDIndex(samples, axis_strategy="widest")

assert cyclic.validate()
assert widest.validate()
assert cyclic.root is not None

# Đúng ví dụ tính tay: D gần (6,3) nhất.
assert cyclic.nearest((6, 3)).id == "D"
assert widest.nearest((6, 3)).id == "D"

# q=(7,3) có D và F bằng khoảng cách 5, ưu tiên ID D.
assert cyclic.nearest((7, 3)).id == "D"
assert [p.id for p in cyclic.k_nearest((7, 3), 2)] == [
    "D", "F"
]

# q=(6,3): dist² D=2, C=8, F=10.
assert [p.id for p in cyclic.k_nearest((6, 3), 3)] == [
    "D", "C", "F"
]
assert [p.id for p in cyclic.radius((6, 3), 3)] == [
    "C", "D"
]

# Lớn hơn số bản ghi: trả hết, vẫn sắp theo khoảng cách.
assert len(cyclic.k_nearest((0, 0), 100)) == len(samples)

# Trùng tọa độ nhưng khác ID: không mất bản ghi.
with_duplicate = ExactKDIndex(
    samples + [("G", (5, 2))]
)
assert with_duplicate.nearest((5, 2)).id == "D"
assert [
    p.id for p in with_duplicate.k_nearest((5, 2), 2)
] == ["D", "G"]
assert [
    p.id for p in with_duplicate.radius((5, 2), 0)
] == ["D", "G"]
assert with_duplicate.validate()

# Tập rỗng: NN là None, kNN và radius là danh sách rỗng.
empty = ExactKDIndex([])
assert empty.nearest((1, 2)) is None
assert empty.k_nearest((1, 2), 3) == []
assert empty.radius((1, 2), 2) == []
assert empty.validate()

# Với 3D, minDist phải xét đủ ba trục.
space = ExactKDIndex([
    ("P", (0, 0, 0)),
    ("Q", (1, 1, 1)),
    ("R", (-2, 2, 0)),
])
assert space.nearest((0, 0, 0)).id == "P"
assert [p.id for p in space.radius((0, 0, 0), 2)] == [
    "P", "Q"
]
assert space.validate()


def brute_sq(point, query):
    return sum(
        (a - b) ** 2 for a, b in zip(point, query)
    )


def brute_knn(records, query, k):
    return [
        item_id
        for item_id, coords in nsmallest(
            k,
            records,
            key=lambda item: (brute_sq(item[1], query), item[0]),
        )
    ]


def brute_radius(records, query, radius):
    return sorted(
        item_id for item_id, coords in records
        if brute_sq(coords, query) <= radius ** 2
    )


for query in [(0, 0), (6, 3), (7, 3), (20, 20)]:
    for index in (cyclic, widest):
        assert index.nearest(query).id == brute_knn(
            samples, query, 1
        )[0]
        for k in (1, 2, 3, 10):
            actual = [
                p.id for p in index.k_nearest(query, k)
            ]
            assert actual == brute_knn(samples, query, k)
        for radius in (0, 1, 3, 10):
            actual = [
                p.id for p in index.radius(query, radius)
            ]
            assert actual == brute_radius(samples, query, radius)
~~~

### Vì sao phép đối chiếu có giá trị?

**Quét tham chiếu** không sử dụng AABB, phân hoạch hoặc thứ tự duyệt của cây, nên có thể phát hiện cắt nhánh sai. Nếu chỉ so hai cách duyệt của cùng một k-d tree, hai cách có thể cùng mắc lỗi metadata mà vẫn cho kết quả giống nhau.

Kiểm tra riêng:

- **Trùng tọa độ** để bảo đảm mỗi ID là một bản ghi.
- **Khoảng cách bằng nhau** để bảo đảm tie-break ổn định.
- **Bán kính bằng 0** để phân biệt radius với 1-NN.
- **k lớn hơn n** để bảo đảm heap chưa đầy vẫn xử lý đúng.
- **Tọa độ âm/3D** để phát hiện mã cứng hai trục hoặc giả định tọa độ dương.
- **Truy vấn xa dữ liệu** để kiểm tra cả trường hợp minDist lớn.

**Lưu ý:** Các đoạn Python là ví dụ học thuật để người học chạy và kiểm thử; trong quy trình biên soạn STEP 4, chúng **chưa được thực thi tự động**. Không xem các lệnh assert được viết ra là bằng chứng đã chạy QA phần mềm.

## 19. Số thực, sai số cận dưới và điều kiện biên

Tính đúng về mặt toán học cần được chuyển sang các phép so sánh số thực cụ thể.

### Khi q nằm đúng trên biên

Với \(B=[2,5]\times[3,7]\), \(q=(5,4)\), ta có:

\[
\operatorname{minDist}_2^2(q,B)=0.
\]

Điểm q nằm trên cạnh phải của **hộp đóng**. Không được tính cận là số dương chỉ vì “chạm biên” hay vì miền phân hoạch một cấu trúc khác sử dụng **biên nửa mở**.

### Khi hai bản ghi có cùng khoảng cách

Nếu A và B đều cách q một đoạn r, thuật toán exact 1-NN theo ID phải trả ID nhỏ hơn. Điều kiện prune **\(bound>best^2\)** thay vì \(bound\ge best^2\) giúp không loại nhánh có khả năng chứa điểm cùng khoảng cách.

### Sai số làm tròn

Về mặt lý thuyết, minDist² phải **không lớn hơn** khoảng cách bình phương tới mọi điểm thật trong nhánh. Tuy nhiên, số thực hữu hạn có thể gây sai số ở thao tác trừ/bình phương/cộng.

- Với dữ liệu có yêu cầu chính xác nghiêm ngặt, cân nhắc kiểu số và predicate được chứng minh phù hợp.
- Không tự cộng một epsilon vào cận dưới khi prune, vì cận quá lớn có thể bỏ nhánh có nghiệm tốt hơn.
- Nếu cần biên sai số để an toàn, phải chứng minh được khoảng sai số và dùng **cận dưới bảo thủ** (không lớn hơn giá trị thực), thay vì chọn một epsilon tùy ý.
- Không sử dụng NaN, vô cực hay khoảng cách tính ra NaN trong thứ tự ưu tiên heap. Đầu vào hữu hạn chưa đủ bảo đảm mọi phép trừ/bình phương trung gian không tràn.

### Đơn vị tọa độ

Nếu dữ liệu là mét, D₂ là khoảng cách thẳng tính bằng mét. Nếu dữ liệu là kinh độ/vĩ độ tính bằng độ, D₂ trên tọa độ độ không phải khoảng cách địa lý mét. Metric không phù hợp dẫn tới “láng giềng gần nhất” **khác ý nghĩa nghiệp vụ**, dù thuật toán tìm đúng nghiệm của metric đã viết.

### Bounding box không nhất thiết đạt minDist tại điểm dữ liệu

Giả sử \(q=(0,0)\), hộp \(B=[0,10]\times[0,10]\) chứa các điểm thật (10,0) và (0,10). minDist²(q,B)=0 vì q nằm trong hộp, nhưng cả hai điểm thật đều cách q bình phương khoảng cách 100.

Đây là **false positive của cận dưới**, không phải lỗi. Thuật toán chỉ cần tiếp tục duyệt; không được trả “khoảng cách 0” mà chưa kiểm tra một bản ghi thật.

## 20. Những lỗi và hiểu lầm thường gặp

1. **“Điểm nằm gần nhất trong AABB chính là láng giềng gần nhất của nhánh.”** Sai. Điểm gần nhất trong *hộp* có thể không tồn tại trong tập dữ liệu.
2. **“minDist là cận trên của khoảng cách tới các điểm.”** Sai. Nó là **cận dưới**: mọi điểm trong hộp cách q **ít nhất** bằng minDist.
3. **“Đã tìm thấy điểm ở nhánh gần thì có thể bỏ nhánh xa.”** Sai. Nhánh xa vẫn có thể chứa điểm tốt hơn nếu cận của nó không vượt best.
4. **“Nhánh gần theo trục chia luôn chứa NN.”** Sai. “Gần” chỉ quyết định thứ tự duyệt, không phải kết luận nghiệm.
5. **“Có thể prune ngay khi minDist² bằng best².”** Sai khi cần tie-break theo ID hoặc liệt kê mọi nghiệm cùng khoảng cách.
6. **“Nếu minDist² nhỏ hơn best², nhánh chắc chắn có nghiệm tốt hơn.”** Sai. Đó chỉ là **khả năng**; bbox có thể chứa nhiều vùng trống.
7. **“Cây con có bbox lớn không giao Q thì vẫn có thể có điểm ở Q.”** Không thể nếu bbox đúng và bao toàn bộ điểm của nhánh.
8. **“Một bbox chỉ cần bao pivot của nút.”** Sai. Nó phải bao **pivot và tất cả hậu duệ**.
9. **“Bbox cũ vẫn đúng sau khi điểm di chuyển ra khỏi vùng.”** Sai. Metadata lỗi thời có thể dẫn đến bỏ sót nghiệm thật.
10. **“Bbox rộng hơn dữ liệu là lỗi tính đúng.”** Không hẳn: nếu vẫn bao tất cả điểm, nó an toàn nhưng kém cắt tỉa.
11. **“Dùng dấu \(\ge\) trong radius sẽ không ảnh hưởng điểm trên biên.”** Sai. Radius đóng phải nhận điểm có khoảng cách bằng r.
12. **“Bán kính bằng 0 chỉ có một kết quả.”** Sai. Nhiều ID có thể cùng tọa độ q.
13. **“1-NN và kNN có cùng điều kiện dừng ngay từ đầu.”** Sai. kNN cần đủ k ứng viên trước khi dùng khoảng cách của phần tử tệ nhất làm ngưỡng.
14. **“Heap top-k nên đặt điểm tốt nhất ở đỉnh để thay nhanh.”** Nếu dùng max-heap giới hạn k để loại phần tử tệ nhất, đỉnh phải là **điểm tệ nhất**.
15. **“Min-heap vùng và max-heap điểm là cùng một cấu trúc.”** Sai. Chúng phục vụ hai mục tiêu ưu tiên trái ngược nhau.
16. **“Best-first cứ tìm được một điểm là có thể dừng.”** Sai. Phải xét cận nhỏ nhất của **mọi vùng chưa mở**.
17. **“Cận mặt chia và AABB luôn có cùng giá trị.”** Sai. AABB kết hợp nhiều chiều nên có thể cho cận chặt hơn.
18. **“Có thể áp dụng cận mặt chia cho bất kỳ cây chứa hộp chồng lấp.”** Sai. Phải có bất biến phân hoạch hình học tương ứng.
19. **“Cây cao \(O(\log n)\) nghĩa là NN chỉ thăm \(O(\log n)\) điểm.”** Sai. Có thể phải quay lại nhiều nhánh và thăm gần n điểm.
20. **“Bình phương Euclid và Manhattan xếp điểm theo cùng thứ tự.”** Sai. Hai metric có thể cho nghiệm khác nhau.
21. **“Tọa độ kinh/vĩ độ theo độ có thể dùng Euclid để ra mét.”** Sai. Metric địa lý và hệ quy chiếu cần được xác định riêng.
22. **“KNN trả k kết quả không cần quan tâm ID khi các khoảng cách bằng nhau.”** Nếu API yêu cầu thứ tự ổn định, tie-break theo ID là bắt buộc.
23. **“Hai bản ghi cùng tọa độ có thể coi là một.”** Sai nếu chúng có ID riêng và bài toán tìm bản ghi, không phải vị trí duy nhất.
24. **“ANN có thể gắn nhãn exact NN mà không cần kiểm chứng.”** Sai. Kết quả gần đúng cần được mô tả và đánh giá đúng bảo đảm/recall.
25. **“Cùng công thức cận với mọi metric.”** Sai. Cận Manhattan, Chebyshev, Euclid có cách tổng hợp \(\delta_i\) khác nhau.
26. **“Chỉ cần đầu vào float hữu hạn, mọi bình phương khoảng cách chắc chắn hữu hạn.”** Sai. Số trung gian có thể tràn hoặc mất độ chính xác.
27. **“Dùng epsilon tùy ý tăng minDist sẽ giúp prune an toàn hơn.”** Sai. Cận dưới bị tăng quá giá trị thật có thể gây false negative.
28. **“Khi k>n, heap chưa đủ k là lỗi thuật toán.”** Không. Với API minh họa, thuật toán trả tất cả n điểm đúng thứ tự.
29. **“R-tree chỉ cần đi một nhánh giống BST.”** Sai. MBR các nhánh có thể chồng lấp; NN phải xét mọi vùng chưa thể loại.
30. **“Nhiều đối tượng hình học đăng ký trong các lá khác nhau không cần dedup.”** Sai. Cùng một ID có thể xuất hiện ở nhiều bucket.
31. **“Lưu node theo pointer hay mảng không ảnh hưởng hiệu năng.”** Hình thức lưu có thể ảnh hưởng cache locality, cấp phát, bộ nhớ và độ trễ dù độ phức tạp tiệm cận không đổi.
32. **“Truy vấn trả k điểm có thể xuất tất cả trong \(O(1)\).”** Sai. Riêng phần xuất k bản ghi cần ít nhất \(\Omega(k)\) công việc.

## 21. Benchmark: đo phần cắt tỉa và chi phí thật

Để đánh giá một chỉ mục cho NN/kNN, không chỉ đo tổng thời gian của một truy vấn đẹp. Nên so:

1. **Quét tuyến tính** dùng đúng metric và tie-break.
2. **K-d tree với cận mặt chia** và duyệt nhánh gần trước.
3. **K-d tree với minDist AABB** và DFS nhánh gần trước.
4. Nếu cần, **best-first AABB**.

Mọi phương án phải dùng **cùng tập điểm, cùng tọa độ, cùng truy vấn và cùng định nghĩa metric**. Nếu không, kết quả benchmark không so sánh công bằng.

### Những chỉ số nên đo

| Chỉ số | Ý nghĩa |
| --- | --- |
| \(n,d\) | Quy mô bản ghi và số chiều |
| Số node thăm \(V\) | Phần dữ liệu chưa cắt tỉa được |
| Số điểm tính khoảng cách thật | Chi phí ứng viên sau lọc |
| Số lần minDist | Overhead tính cận dưới |
| Số nhánh bị prune | Hiệu quả bỏ cây con |
| Thời gian build và rebuild | Chi phí chuẩn bị/chăm sóc chỉ mục |
| Độ trễ p50/p95/p99 | Phân bố hiệu năng, bao gồm truy vấn xấu |
| Bộ nhớ cây/AABB | Giá metadata so với mảng điểm |
| Kích thước heap đỉnh | Bộ nhớ tạm kNN/best-first |
| Recall/độ lệch nếu dùng ANN | Chất lượng kết quả gần đúng |

### Tập dữ liệu thử nên đa dạng

**Phân bố đều:** nhiều điểm trải đều trong hình vuông/hình lập phương.

**Phân bố cụm:** nhiều điểm tập trung ở một vùng hẹp, vùng khác thưa.

**Điểm trùng:** nhiều ID cùng tọa độ; quan trọng cho trường hợp bán kính 0 và NN tie.

**Điểm nằm trên đường/mặt phẳng:** có trục gần như không thay đổi; giúp kiểm tra việc chọn trục chia.

**Điểm ngoài lệch (*outlier*):** một vài điểm rất xa phần còn lại, ảnh hưởng AABB và cách chia.

**Tăng số chiều:** cùng cỡ n nhưng d bằng 2, 3, 8, 32, 128 để quan sát khả năng cắt tỉa.

**Truy vấn ở vùng rỗng:** q nằm rất xa các cụm dữ liệu.

**Truy vấn sát mặt chia và sát biên AABB:** giúp phát hiện lỗi dấu so sánh và tie.

### Ví dụ phép đo cần tách

Nếu cách A quét 1.000 điểm nhưng không cần tính bbox, còn cách B thăm 30 node nhưng tính minDist AABB cho 60 nhánh, không thể kết luận B nhanh **chỉ từ số điểm thực sự xét**. Cần đo cả chi phí tính bound, heap, cache và những thao tác phụ khác.

Nếu phần lớn truy vấn có k lớn gần n, chỉ mục khó giúp tránh chi phí xuất kết quả; **quét tuyến tính trên mảng liên tiếp** đôi khi có lợi thế cache. Nếu tập dữ liệu nhỏ, chi phí xây và duyệt cây có thể lớn hơn lợi ích prune.

### Quy trình kiểm chứng độc lập

Với một tập truy vấn \(Q_{\mathrm{test}}\), luôn tính kết quả chính xác bằng quét:

\[
\boxed{
\forall q\in Q_{\mathrm{test}}:\quad
\operatorname{NN}_{\mathrm{index}}(q)
=\operatorname{NN}_{\mathrm{brute}}(q).
}
\]

Với kNN, so **danh sách ID đã sắp theo (dist², ID)**. Với radius, so **tập ID** hoặc danh sách ID đã chuẩn hóa thứ tự. Mục tiêu đầu tiên là phát hiện **bỏ sót nghiệm**; chỉ sau khi kết quả đúng mới dùng benchmark để chọn chính sách chỉ mục.

## 22. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Chọn NN từ các khoảng cách bình phương

Cho q=(6,3) và A=(1,1), B=(2,3), C=(4,5), D=(5,2), E=(8,8), F=(9,2). Điểm gần nhất theo Euclid là điểm nào?

**Lời giải:** Bình phương khoảng cách lần lượt là 29, 16, 8, **2**, 29 và 10. Vì 2 nhỏ nhất, NN là **D**. Không cần lấy căn bậc hai để so thứ tự.

### Câu 2. Vì sao dùng bình phương thay cho căn bậc hai?

Nếu \(D_2^2(q,A)=8\) và \(D_2^2(q,B)=9\), có cần tính \(\sqrt8\) và \(\sqrt9\) mới so được không?

**Lời giải:** **Không.** Hàm căn tăng đơn điệu trên số không âm; vì 8<9 nên A gần hơn B.

### Câu 3. Tính minDist tới AABB

Cho \(q=(1,4)\), \(B=[3,6]\times[2,5]\). Tính minDist² và minDist.

**Lời giải:** Trục x chênh 2, trục y chênh 0. Vì vậy:

\[
\operatorname{minDist}^2=2^2+0^2=\boxed{4},
\quad\operatorname{minDist}=\boxed{2}.
\]

### Câu 4. Điểm q ở trong bbox

Cho \(q=(3,3)\), \(B=[0,10]\times[0,10]\), nhưng B chỉ chứa các bản ghi A=(10,0) và C=(0,10). minDist² tới B là bao nhiêu? Có thể kết luận có bản ghi cách 0 không?

**Lời giải:** Vì q nằm trong B, minDist²=0. Nhưng **không** có nghĩa một bản ghi nằm đúng q; các điểm dữ liệu thật đều cách q một khoảng dương. minDist chỉ là cận **hình học của hộp**.

### Câu 5. Cắt nhánh khi cận dưới lớn

Ứng viên tốt nhất có \(best^2=9\). Một nhánh có minDist²=16. Có thể bỏ nhánh không?

**Lời giải:** **Có**. Mọi điểm trong nhánh có khoảng cách bình phương ít nhất 16, lớn hơn 9; không điểm nào thắng best.

### Câu 6. Cận bằng khoảng cách tốt nhất

Vẫn \(best^2=9\), nhưng minDist² của một nhánh bằng 9. Nếu tie-break ưu tiên ID nhỏ hơn, có thể bỏ nhánh chỉ từ hai số này không?

**Lời giải:** **Không.** Nhánh có thể chứa điểm cùng khoảng cách 3 nhưng ID nhỏ hơn best hiện tại. Quy tắc an toàn là chỉ prune khi **minDist² > best²**.

### Câu 7. Cận từ mặt chia

Một node k-d tree chia theo x tại \(s=4\), truy vấn q=(7,2) nằm bên phải mặt chia. Cận dưới bình phương của nhánh trái theo riêng mặt chia là bao nhiêu?

**Lời giải:** Khoảng cách theo x tới mặt chia là \(7-4=3\), nên:

\[
\boxed{lowerBound_{\mathrm{plane}}^2=3^2=9.}
\]

Nếu best²<9, có thể bỏ nhánh trái theo bất biến \(x\le4\).

### Câu 8. Cận hộp mạnh hơn cận mặt chia

Cho q=(6,6), nhánh trái của mặt chia x=4 có AABB \(B=[0,4]\times[0,2]\). Tính hai cận bình phương và quyết định nếu best²=9.

**Lời giải:** Cận mặt chia là \(4\). Cận AABB là \(4+16=\boxed{20}\). Cận mặt chia chưa đủ bỏ nhánh vì 4≤9, còn AABB **cho phép prune** vì 20>9.

### Câu 9. Tại sao phải duyệt nhánh gần trước?

Hai nhánh có minDist² lần lượt bằng 1 và 36. Nếu chưa có best, nên thăm nhánh nào trước?

**Lời giải:** Nên **thăm nhánh cận 1 trước** để có khả năng tìm được best tốt sớm, giúp bỏ nhánh cận 36 về sau. Đây là heuristic hiệu năng, không phải chứng minh nhánh cận 1 chắc chắn chứa NN.

### Câu 10. Heap kNN chưa đầy

Cần tìm 3NN nhưng chỉ mới gặp hai điểm có dist²=1 và 4. Một nhánh có minDist²=100. Có thể bỏ nhánh vì 100>4 không?

**Lời giải:** **Không.** Chưa có đủ 3 điểm; nhánh ấy có thể chứa điểm thứ ba. Ngưỡng của phần tử thứ k chỉ có ý nghĩa khi heap đã đủ k ứng viên.

### Câu 11. Heap kNN đã đủ

Đang tìm 3NN; heap chứa A(dist²=1), B(dist²=4), C(dist²=9). Nhánh X có minDist²=10, nhánh Y minDist²=8. Nhánh nào có thể bỏ?

**Lời giải:** Ngưỡng top-3 là \(\tau^2=9\). **Bỏ X** vì 10>9; **giữ Y** vì 8≤9 và có thể chứa điểm tốt hơn C.

### Câu 12. Tie-break trong kNN

Heap top-3 có phần tử tệ nhất C với dist²=9, ID="M". Nhánh khác có minDist²=9. Nếu nhánh chứa một điểm A với dist²=9, ID="A", có phải thay C không?

**Lời giải:** **Có.** Khóa (9,"A") nhỏ hơn (9,"M"). Vì thế cận bằng ngưỡng không được tự prune khi cần tie-break theo ID.

### Câu 13. Truy vấn bán kính đóng

Tâm q=(0,0), r=5, các điểm A=(3,4), B=(4,4), C=(-5,0), D=(0,6). Trả những điểm nào?

**Lời giải:** Bình phương khoảng cách lần lượt là 25, 32, 25, 36. Radius đóng nhận \(\le25\), nên trả **A và C**.

### Câu 14. Bán kính 0

Trong tập có hai bản ghi A=(2,2), B=(2,2) và C=(3,2), bán kính 0 tại (2,2) trả gì?

**Lời giải:** Trả **A và B**. C khác vị trí. Radius không tự gộp các ID cùng tọa độ; 1-NN theo ID sẽ chỉ chọn **A**.

### Câu 15. Best-first và điều kiện kết thúc

Best hiện có dist²=16. Min-heap các vùng chưa mở có cận nhỏ nhất lần lượt là 25, 36, 49. Có thể dừng toàn bộ tìm kiếm 1-NN không?

**Lời giải:** **Có**, vì cận nhỏ nhất 25 đã >16, nên mọi vùng còn lại đều không thể có điểm thắng best. Không cần pop từng vùng còn lại để xác minh lại.

### Câu 16. Best-first chưa thể dừng

Best có dist²=16, cận nhỏ nhất frontier là 9. Có được dừng không?

**Lời giải:** **Không.** Vùng cận 9 có thể chứa điểm dist²=9, gần hơn best. Phải tiếp tục mở vùng.

### Câu 17. Tính cận trong 3D

Cho \(q=(0,0,0)\), hộp:

\[
B=[2,4]\times[-1,1]\times[3,5].
\]

Tính minDist² theo Euclid 3D.

**Lời giải:** Các \(\delta\) lần lượt là (2,0,3), nên:

\[
\boxed{\operatorname{minDist}_2^2=2^2+0^2+3^2=13.}
\]

Nếu chỉ tính x/y sẽ bị thiếu thành phần z và cận yếu hơn.

### Câu 18. Hai metric cho kết quả khác nhau

Từ q=(0,0), A=(3,0) và B=(2,2). Điểm gần nhất theo Euclid và Manhattan lần lượt là gì?

**Lời giải:** Euclid: A có dist²=9, B có dist²=8 → **B**. Manhattan: A có khoảng cách 3, B có 4 → **A**.

### Câu 19. Cận Manhattan từ AABB

Cho \(q=(1,4)\), \(B=[3,6]\times[2,5]\). MinDist theo \(L_1\) bằng bao nhiêu?

**Lời giải:** \(\delta_x=2,\delta_y=0\). Cận Manhattan là \(\delta_x+\delta_y=\boxed{2}\). Không cần tính căn hay bình phương.

### Câu 20. Bbox lỗi thời sau di chuyển

Điểm P chuyển từ (2,2) đến (20,20), nhưng bbox nhánh vẫn \([0,4]\times[0,4]\). Khi truy vấn q=(20,20), nguy cơ nào xảy ra?

**Lời giải:** Bbox cũ cho minDist²=512 mặc dù điểm P thật cách q bằng 0. Nếu đã có best² nhỏ hơn 512, thuật toán có thể prune sai và **bỏ sót nghiệm thật**. Phải cập nhật chỉ mục/bbox hoặc rebuild.

### Câu 21. Hộp bao nới rộng

Bbox cũ của một nhánh là \([0,4]\times[0,4]\); hệ thống cố tình dùng hộp lớn hơn \([-5,10]\times[-5,10]\), vẫn bao mọi điểm. Việc này gây sai kết quả NN không?

**Lời giải:** **Không nhất thiết.** Hộp rộng vẫn là một bao **hợp lệ**, minDist của nó là cận dưới an toàn nhưng thường nhỏ hơn, khiến **prune ít hơn** và truy vấn có thể chậm.

### Câu 22. Tính bảo đảm ANN

Một thuật toán 1-NN gần đúng có best=10. Mọi nhánh chưa xét đều có cận dưới khoảng cách ít nhất 8. Có thể kết luận best không quá 1,25 lần khoảng cách tối ưu không?

**Lời giải:** **Có**, nếu cận dưới của mọi nhánh chưa xét thực sự hợp lệ. Khoảng cách tối ưu ít nhất \(\min(10,8)=8\), trong khi best=10; vì vậy:

\[
\frac{best}{D^*}\le\frac{10}{8}=\boxed{1.25}.
\]

Đây là bảo đảm theo **tỷ lệ khoảng cách**, không đồng nghĩa các ID top-k đã được tìm chính xác.

### Câu 23. Độ phức tạp NN trong trường hợp xấu

Một k-d tree có chiều cao \(O(\log n)\) nhưng truy vấn phải thăm tất cả n node để bảo đảm exact NN. Tổng chi phí ở d chiều là bao nhiêu?

**Lời giải:** Mỗi node có thể cần \(O(d)\) để tính minDist và khoảng cách, nên tổng \(O(nd)\). Cây cân bằng không biến mọi truy vấn NN thành \(O(\log n)\).

### Câu 24. Chọn chỉ mục phù hợp

Ba ứng dụng: (a) 300 điểm 2D, truy vấn ít; (b) 2 triệu điểm 3D tương đối tĩnh, cần NN chính xác; (c) 500.000 vector 256 chiều, chấp nhận gần đúng. Nên thử hướng nào trước?

**Lời giải:** (a) **quét tuyến tính** có thể đủ; (b) thử **k-d tree hoặc octree 3D có cận AABB** và so với brute-force; (c) thử **chỉ mục ANN chuyên dụng** và đo recall/độ trễ, đồng thời giữ kết quả chính xác làm chuẩn. Không có một cấu trúc thắng mọi dữ liệu.

## 23. Tổng kết

**Nearest neighbor** tìm bản ghi có khoảng cách nhỏ nhất tới điểm truy vấn. Với Euclid, dùng bình phương khoảng cách:

\[
\boxed{D_2^2(q,p)=\sum_{i=1}^{d}(q_i-p_i)^2.}
\]

Nếu một cây con được bao đúng bởi AABB \(B=\prod_i[lo_i,hi_i]\), ta tính từng khoảng cách thiếu trên các trục:

\[
\delta_i=\max(lo_i-q_i,\ 0,\ q_i-hi_i),
\]

và cận:

\[
\boxed{\operatorname{minDist}_2^2(q,B)=\sum_i\delta_i^2.}
\]

Đây là **cận dưới an toàn** cho mọi bản ghi trong nhánh, không phải khoảng cách tới một bản ghi đã được tìm thấy. Khi đã có nghiệm tốt nhất với best², có thể bỏ nhánh nếu:

\[
\boxed{\operatorname{minDist}_2^2(q,B)>best^2.}
\]

Với **kNN**, thay best² bằng ngưỡng của **phần tử tệ nhất trong k ứng viên**, nhưng **chỉ khi đã có đủ k ứng viên**. Với **radius**, dùng ngưỡng cố định \(r^2\). Với tie-break theo ID, giữ dấu \(>\) nghiêm ngặt khi prune để không bỏ kết quả cùng khoảng cách nhưng có ID tốt hơn.

**DFS nhánh gần trước** thường rẻ về bộ nhớ và overhead; **best-first** mở vùng có cận nhỏ nhất bằng một hàng đợi ưu tiên. Cả hai có thể tìm NN chính xác nếu cận hợp lệ và điều kiện dừng đúng. Không gian nhiều chiều, vùng bao rộng hoặc phân bố dữ liệu bất lợi có thể khiến truy vấn phải xét \(O(n)\) điểm dù cây cân bằng.

Để áp dụng vào thực tế, hãy xác định **metric và đơn vị tọa độ**, xây **hộp bao không bỏ sót điểm**, chọn chiến lược NN/kNN theo yêu cầu chính xác và thứ tự đầu ra, xử lý **ID trùng tọa độ và tie**, rồi **so kết quả với quét tuyến tính**. Sau khi chứng minh tính đúng, đo số node được thăm, số lần tính cận, độ trễ và bộ nhớ. Một chỉ mục tốt không phải cấu trúc luôn thăm ít node nhất trên một ví dụ đẹp, mà là cấu trúc **giữ đúng nghiệm với chi phí phù hợp dữ liệu và workload**.
