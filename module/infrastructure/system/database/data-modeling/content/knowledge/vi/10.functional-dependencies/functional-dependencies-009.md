# Bảo toàn phụ thuộc và đánh đổi với mức chuẩn hóa

## Mục tiêu học tập

Phân rã một quan hệ lớn thành các quan hệ nhỏ hơn là công cụ quan trọng để giảm dư thừa, hạn chế bất thường khi cập nhật và tổ chức dữ liệu rõ ràng. Nhưng một phép phân rã “trông có vẻ chuẩn hóa tốt” vẫn có thể khiến **quy tắc nghiệp vụ trước đây được kiểm tra trong một quan hệ phải kiểm tra trên nhiều quan hệ**. Đây là vấn đề **bảo toàn phụ thuộc hàm** (*dependency preservation*).

Bài thuộc chương **Phụ thuộc dữ liệu** trong module **DATABASE_DATA_MODELING**. Theo mục tiêu của module, người học cần chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu có thực thể, quan hệ, ràng buộc và khóa rõ ràng; biết dùng chuẩn hóa, chỉ mục, lược đồ vật lý và các lựa chọn mô hình quan hệ/document/đồ thị/phân tích để tạo cấu trúc phù hợp, dễ tiến hóa và kiểm chứng. Bài này tập trung vào **đánh đổi giữa mức chuẩn hóa và khả năng bảo vệ các phụ thuộc hàm** khi thiết kế quan hệ.

Sau bài học, bạn có thể:

1. Phát biểu chính xác ý nghĩa của **phụ thuộc hàm** và **bảo toàn phụ thuộc** trong một phép phân rã.
2. Phân biệt **phân rã không mất mát thông tin** (*lossless-join decomposition*) với **bảo toàn phụ thuộc**: đây là hai tiêu chí độc lập.
3. Kiểm tra phụ thuộc có được suy ra từ các phụ thuộc cục bộ sau phân rã hay không bằng **bao đóng thuộc tính**.
4. Hiểu tại sao thuật toán tổng hợp **3NF** có thể bảo đảm cả bảo toàn phụ thuộc và phân rã không mất mát, còn phân rã **BCNF** nói chung không bảo đảm bảo toàn mọi phụ thuộc.
5. Phân tích phản ví dụ hình thức với \(R(A,B,C)\), \(F=\{AB\to C,\ C\to B\}\) và hai bảng BCNF.
6. Đánh giá tác động thực tế lên **UNIQUE, khóa, giao dịch, trigger, JOIN, dư thừa, hiệu năng và khả năng tiến hóa**.
7. Chọn thiết kế hợp lý từ yêu cầu nghiệp vụ, thay vì mặc định mức chuẩn hóa càng cao càng tốt.

## 1. Phụ thuộc hàm diễn đạt quy tắc nghiệp vụ

Cho lược đồ quan hệ \(R(U)\) với \(U\) là tập thuộc tính. Một **phụ thuộc hàm** (functional dependency, viết tắt **FD**) có dạng:

\[
X \rightarrow Y,\qquad X,Y\subseteq U
\]

Nó phát biểu: trong **mọi trạng thái hợp lệ** của quan hệ, nếu hai bộ bằng nhau trên tất cả thuộc tính X thì chúng cũng phải bằng nhau trên các thuộc tính Y.

\[
\forall t_1,t_2\in r(R),\quad
t_1[X]=t_2[X]\ \Longrightarrow\ t_1[Y]=t_2[Y]
\]

**Ví dụ nghiệp vụ:** Mỗi đơn hàng thuộc một khách hàng; mã đơn xác định khách hàng.

\[
MaDon \rightarrow MaKhach
\]

Nếu hai dòng của cùng đơn có cùng MaDon nhưng khác MaKhach, dữ liệu vi phạm phụ thuộc hàm này. FD được phát biểu từ **ý nghĩa nghiệp vụ**, không phải suy luận vì dữ liệu thử đang tình cờ duy nhất.

Một số thuật ngữ:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Vế trái (X)** | Tập thuộc tính xác định |
| **Vế phải (Y)** | Tập thuộc tính bị xác định |
| **Phụ thuộc tầm thường** | \(X\to Y\) với \(Y\subseteq X\) |
| **Siêu khóa** | X mà \(X\to U\) được suy ra từ các FD đang xét |
| **Khóa ứng viên** | Siêu khóa tối thiểu, không thể bỏ một thành phần mà vẫn là siêu khóa |
| **Bao đóng thuộc tính \(X^+\)** | Mọi thuộc tính suy ra được từ X bằng các FD |
| **Bao đóng tập phụ thuộc \(F^+\)** | Tập toàn bộ FD suy ra logic từ F |

Trong đại số quan hệ cổ điển, các định nghĩa này xét các bộ với giá trị xác định và ngữ nghĩa tập hợp. SQL có thể cho phép **NULL** và các dòng trùng, nên khi ánh xạ FD sang SQL phải chọn quy tắc NULL, khóa và miền giá trị rõ ràng; không tự suy ra rằng một phép kiểm tra UNIQUE với cột nullable thực thi chính xác mọi FD toán học.

### 1.1. Hai loại vi phạm không nên nhầm

**Vi phạm phụ thuộc hàm** là hai bộ cùng giá trị X nhưng khác giá trị Y, ví dụ cùng MaKhach mà khác TenKhach trong một hệ thống quy định mỗi mã khách ứng với đúng một tên được quản lý.

**Vi phạm khóa** là hai bộ trùng giá trị khóa ứng viên (và khác ở các thuộc tính khác). Một FD có vế trái **không phải siêu khóa** vẫn quan trọng: nó có thể bị vi phạm ngay cả khi tất cả khóa chính vẫn duy nhất.

Ví dụ các đơn hàng có mã khác nhau nhưng cùng MaKhach và tên khách khác nhau có thể không vi phạm khóa MaDon; chúng lại vi phạm \(MaKhach\to TenKhach\).

## 2. Vì sao cần phân rã và phải đánh giá hai tiêu chí?

Giả sử có một bảng tổng hợp phục vụ bán hàng:

~~~~text
CHI_TIET_BAN(
    MaDon, MaKhach, TenKhach,
    MaSP, TenSP, SoLuong
)
~~~~

Ta đặt bộ phụ thuộc nghiệp vụ:

\[
\begin{aligned}
MaDon &\rightarrow MaKhach\\
MaKhach &\rightarrow TenKhach\\
MaSP &\rightarrow TenSP\\
(MaDon,MaSP) &\rightarrow SoLuong
\end{aligned}
\]

Ở ví dụ này, mỗi sản phẩm xuất hiện **tối đa một dòng trong mỗi đơn**; nếu nghiệp vụ cho sản phẩm lặp nhiều dòng, phải có thêm định danh dòng hoặc sửa khóa. Theo các FD đang xét, **(MaDon, MaSP)** là một khóa ứng viên của quan hệ tổng hợp.

Một vài dòng dữ liệu:

| MaDon | MaKhach | TenKhach | MaSP | TenSP | SoLuong |
| --- | --- | --- | --- | --- | ---: |
| D01 | K01 | An | P01 | Bút | 2 |
| D01 | K01 | An | P02 | Sổ | 1 |
| D02 | K01 | An | P01 | Bút | 3 |

Nếu khách K01 đổi tên hiển thị, cần sửa **nhiều dòng**. Nếu chỉ sửa một dòng, cùng K01 có thể có hai tên khác nhau, vi phạm FD. Nếu xóa mọi dòng của một sản phẩm, ta có thể mất cả tên sản phẩm dù danh mục sản phẩm vẫn cần tồn tại. Đó là những ví dụ về **bất thường cập nhật/xóa/chèn**.

Phân rã bảng để lưu thông tin khách, sản phẩm, đơn và dòng đơn riêng giúp hạn chế dữ liệu lặp. Tuy nhiên, trước khi phân rã, phải đánh giá ít nhất hai điều:

1. **Không mất mát thông tin khi JOIN:** Từ các hình chiếu lên các bảng con, có thể khôi phục chính xác quan hệ ban đầu bằng phép nối tự nhiên tương ứng trong mọi trạng thái hợp lệ không?
2. **Bảo toàn phụ thuộc:** Có thể kiểm tra toàn bộ các FD ban đầu bằng cách kiểm tra những FD thích hợp **trong từng bảng con**, mà không phải nối các bảng trở lại để phát hiện vi phạm không?

Hai câu hỏi này khác nhau. Một phép phân rã có thể **không mất mát nhưng không bảo toàn phụ thuộc**, hoặc **bảo toàn một số FD nhưng làm JOIN sinh bộ giả**.

## 3. Phân rã không mất mát thông tin (lossless join)

Giả sử chia quan hệ R thành các lược đồ \(R_1,\ldots,R_n\). Gọi \(\pi_{R_i}(r)\) là phép chiếu trạng thái r lên các thuộc tính của \(R_i\).

Phân rã **không mất mát thông tin** đối với tập phụ thuộc F nếu với mọi trạng thái \(r\) thỏa F:

\[
r=\pi_{R_1}(r)\bowtie\pi_{R_2}(r)\bowtie\cdots\bowtie\pi_{R_n}(r)
\]

Ở đây \(\bowtie\) là **phép nối tự nhiên** theo các thuộc tính chung, áp dụng trong mô hình quan hệ cổ điển với ngữ nghĩa tập hợp.

**Điểm cần nhớ:** Không mất mát không nói rằng mọi tổ hợp dữ liệu tùy ý chèn vào các bảng con đều tạo thành trạng thái hợp lệ của R. Nó chỉ bảo đảm phép chiếu rồi JOIN **không làm mất hoặc tạo thêm bộ** đối với những trạng thái gốc đã thỏa các FD.

### 3.1. Điều kiện nhanh cho phân rã hai bảng

Nếu \(R\) được phân thành \(R_1\) và \(R_2\), một tiêu chuẩn cần và đủ cho phân rã không mất mát theo F là ít nhất một trong hai phụ thuộc sau thuộc \(F^+\):

\[
(R_1\cap R_2)\rightarrow (R_1-R_2)
\]

hoặc

\[
(R_1\cap R_2)\rightarrow (R_2-R_1)
\]

Có thể phát biểu tương đương: các thuộc tính chung là siêu khóa của **ít nhất một trong hai hình chiếu**.

Ví dụ \(R(A,B,C)\) có FD \(A\to B\), phân rã thành \(R_1(A,B)\) và \(R_2(A,C)\). Giao nhau là A và A xác định B, nên phân rã **không mất mát**.

### 3.2. Ví dụ phân rã làm sinh bộ giả

Xét quan hệ gốc:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Chiếu lên R1(A,B):

| A | B |
| --- | --- |
| a1 | b1 |
| a2 | b1 |

Chiếu lên R2(B,C):

| B | C |
| --- | --- |
| b1 | c1 |
| b1 | c2 |

Nối R1 và R2 theo B cho **bốn bộ**, gồm **(a1,b1,c2)** và **(a2,b1,c1)** vốn không tồn tại trong quan hệ gốc. Đây là **bộ giả** (*spurious tuples*). Khi B không xác định A hoặc C, phân rã thành AB và BC không được bảo đảm không mất mát.

Như vậy, chỉ nhìn việc các bảng con đều có khóa chính hoặc đều đạt một mức chuẩn hóa nào đó **không đủ** để kết luận phép phân rã không mất mát.

## 4. Bảo toàn phụ thuộc (dependency preservation)

Cho lược đồ gốc \(R(U)\) với tập FD \(F\), và phép phân rã \(\rho=\{R_1,\ldots,R_n\}\).

Trên từng bảng con \(R_i\), ta có tập **phụ thuộc được chiếu**:

\[
F_i = \pi_{R_i}(F)
    =\{X\to Y\in F^+\mid X\cup Y\subseteq R_i\}
\]

Hợp các phụ thuộc cục bộ:

\[
G=F_1\cup F_2\cup\cdots\cup F_n
\]

Phân rã **bảo toàn phụ thuộc** khi:

\[
G^+=F^+
\]

Vì mọi FD trong \(G\) đều được suy ra từ F nên \(G^+\subseteq F^+\). Trong thực hành, chỉ cần kiểm tra mọi FD của một tập sinh ra F, chẳng hạn các FD trong F hoặc phủ tối thiểu, **đều suy ra được từ G**.

### 4.1. Ý nghĩa vận hành

Nếu bảo toàn phụ thuộc:

- Mỗi FD ban đầu có thể được suy ra từ những ràng buộc có thể kiểm tra **trong từng quan hệ con**.
- Không cần nối tất cả bảng con chỉ để xác nhận tính đúng của các FD gốc.
- Việc kiểm tra và duy trì ràng buộc thường dễ tổ chức hơn khi chèn, sửa, xóa, nhất là với hệ thống có nhiều giao dịch ghi.

Nhưng **bảo toàn phụ thuộc không có nghĩa SQL tự thực thi mọi FD bằng PRIMARY KEY hoặc UNIQUE**. Một FD có vế trái không phải khóa vẫn có thể cần trigger, cơ chế kiểm tra dữ liệu hoặc một thiết kế khác. Bảo toàn chỉ nói rằng **thông tin cần để kiểm tra FD nằm đủ trong một quan hệ cục bộ**, không bảo đảm có cú pháp ràng buộc đơn giản cho nó.

### 4.2. Đừng chỉ giữ các FD được ghi nguyên văn

Khi chiếu F lên từng bảng, phải xét cả **FD suy ra từ \(F^+\)**, không chỉ các FD được liệt kê ban đầu. Một phụ thuộc không xuất hiện trực tiếp trong F vẫn có thể là phụ thuộc cục bộ quan trọng.

Ví dụ nếu \(A\to B\) và \(B\to C\), thì \(A\to C\) suy ra theo tính bắc cầu. Nếu một bảng con chỉ chứa A và C, phụ thuộc \(A\to C\) vẫn thuộc hình chiếu FD lên bảng đó dù không được khai báo nguyên văn trong F.

### 4.3. Kiểm tra bằng bao đóng thuộc tính

Để kiểm tra \(X\to Y\) có suy ra từ G không:

1. Khởi tạo \(X^+=X\).
2. Với mỗi FD \(L\to R\) của G, nếu \(L\subseteq X^+\), thêm các thuộc tính R vào \(X^+\).
3. Lặp lại đến khi không thêm được thuộc tính nào.
4. Nếu \(Y\subseteq X^+\), phụ thuộc được suy ra; nếu không, **không được bảo toàn bởi các FD cục bộ đã xét**.

Ví dụ \(G=\{A\to B,\ B\to C\}\). Bắt đầu \(A^+=\{A\}\), áp dụng A→B được \(\{A,B\}\), rồi B→C được \(\{A,B,C\}\). Vì C thuộc \(A^+\), ta suy ra \(A\to C\).

Đây là một phép kiểm tra **logic trên lược đồ**, không phải SQL SELECT dò dữ liệu hiện tại. Một tập dữ liệu nhỏ không có vi phạm không đủ chứng minh FD sẽ luôn được bảo toàn khi có dữ liệu mới.

## 5. Tổng hợp lược đồ 3NF để bảo toàn phụ thuộc

**Dạng chuẩn ba (Third Normal Form, 3NF)** cung cấp một mục tiêu thực tế: có thuật toán tổng hợp lược đồ 3NF bảo đảm **bảo toàn phụ thuộc** và **phân rã không mất mát thông tin** đối với tập FD đã biết. Đây là điểm mạnh khi dữ liệu phải được kiểm tra nghiêm ngặt trong các giao dịch ghi.

### 5.1. Nhắc lại điều kiện 3NF

Một lược đồ R ở **3NF** đối với tập FD F nếu với mọi FD không tầm thường \(X\to A\) thuộc \(F^+\), trong đó A là một thuộc tính đơn, **ít nhất một** điều sau đúng:

1. X là **siêu khóa** của R; hoặc
2. A là **thuộc tính nguyên tố** (*prime attribute*), tức A thuộc **ít nhất một khóa ứng viên** của R.

Thuộc tính **nguyên tố** không đồng nghĩa với thuộc tính nằm trong **khóa chính được chọn**. Nếu R có nhiều khóa ứng viên, một thuộc tính có thể nằm trong khóa ứng viên không được chọn mà vẫn là thuộc tính nguyên tố.

Điều kiện này sẽ rất quan trọng trong phản ví dụ 3NF–BCNF ở mục sau.

### 5.2. Thuật toán tổng hợp 3NF

Một phiên bản thường dùng của thuật toán:

1. **Tìm phủ tối thiểu/phủ chính tắc** \(F_c\) tương đương F. Thường đưa mỗi FD về vế phải một thuộc tính, loại thuộc tính thừa ở vế trái và loại FD dư thừa.
2. **Với mỗi FD \(X\to A\) trong \(F_c\)**, tạo một lược đồ con gồm \(X\cup\{A\}\). Có thể gộp các FD cùng vế trái vào một lược đồ.
3. **Loại lược đồ con bị bao hàm hoàn toàn** trong một lược đồ con khác, nếu việc loại bỏ không ảnh hưởng yêu cầu tổng hợp.
4. **Nếu chưa có lược đồ con nào chứa một khóa ứng viên của R**, thêm một lược đồ chứa khóa ứng viên đó.
5. Xác định PK, khóa ứng viên, FK và ràng buộc nghiệp vụ của từng bảng trước khi triển khai SQL.

Theo các điều kiện thông thường của thuật toán tổng hợp 3NF, kết quả có ba bảo đảm:

- Mỗi lược đồ được tạo đạt **3NF**.
- Các phụ thuộc trong F được **bảo toàn** bằng các phụ thuộc cục bộ.
- Phép phân rã là **không mất mát thông tin**; bước bảo đảm có một lược đồ chứa khóa ứng viên có vai trò quan trọng trong chứng minh.

**Cẩn thận:** Đây là bảo đảm của **thuật toán tổng hợp đúng** với tập FD đã được xác định, không phải bảo đảm cho **mọi cách tùy ý chia R thành các bảng đều đang ở 3NF**. Thiếu FD nghiệp vụ hoặc loại bảng sai vẫn có thể làm mất ràng buộc.

### 5.3. Thực hiện trên ví dụ đơn hàng

Ta trở lại quan hệ:

\[
R(MaDon,MaKhach,TenKhach,MaSP,TenSP,SoLuong)
\]

Tập FD:

\[
F=\{
MaDon\to MaKhach,\
MaKhach\to TenKhach,\
MaSP\to TenSP,\
MaDon\,MaSP\to SoLuong
\}
\]

Tập này đã có vế phải đơn thuộc tính và, theo giả định, không có thành phần thừa ở vế trái của FD cuối. Nó là một phủ tối thiểu thích hợp cho ví dụ.

Với \(X=\{MaDon,MaSP\}\), quá trình tính bao đóng:

\[
\begin{aligned}
X^+_0 &= \{MaDon,MaSP\}\\
X^+_1 &= \{MaDon,MaSP,MaKhach,TenSP,SoLuong\}\\
X^+_2 &= \{MaDon,MaSP,MaKhach,TenSP,SoLuong,TenKhach\}
\end{aligned}
\]

Vì bao đóng chứa mọi thuộc tính, **(MaDon, MaSP)** là siêu khóa. Không thể bỏ MaDon hoặc MaSP mà vẫn suy ra tất cả thuộc tính, nên đây là **khóa ứng viên**.

Tổng hợp tạo bốn quan hệ:

| Bảng con | Thuộc tính | Phụ thuộc bảo toàn tại bảng |
| --- | --- | --- |
| **DON_HANG** | MaDon, MaKhach | \(MaDon\to MaKhach\) |
| **KHACH_HANG** | MaKhach, TenKhach | \(MaKhach\to TenKhach\) |
| **SAN_PHAM** | MaSP, TenSP | \(MaSP\to TenSP\) |
| **DONG_DON_HANG** | MaDon, MaSP, SoLuong | \((MaDon,MaSP)\to SoLuong\) |

Không cần thêm một bảng khóa riêng, vì DONG_DON_HANG đã chứa khóa ứng viên **(MaDon, MaSP)** của quan hệ gốc.

### 5.4. Vì sao thiết kế trên vừa bảo toàn phụ thuộc vừa không mất mát?

**Bảo toàn phụ thuộc:** Mỗi FD trong F có **tất cả thuộc tính liên quan nằm trong một bảng con**. Chẳng hạn muốn kiểm tra MaKhach→TenKhach, chỉ cần xét KHACH_HANG; muốn kiểm tra (MaDon,MaSP)→SoLuong, chỉ cần xét DONG_DON_HANG. Không phải JOIN để biết cùng một mã khách có hai tên hay cùng một cặp đơn–sản phẩm có hai số lượng khác nhau.

**Không mất mát:** Với dữ liệu hợp lệ của R, có thể:

- Nối DONG_DON_HANG với DON_HANG theo MaDon; vì MaDon quyết định MaKhach nên không nhân sai mã khách.
- Nối tiếp KHACH_HANG theo MaKhach; vì MaKhach quyết định TenKhach nên khôi phục đúng tên.
- Nối SAN_PHAM theo MaSP; vì MaSP quyết định TenSP nên khôi phục đúng tên sản phẩm.

Từ các hình chiếu của một trạng thái R thỏa F, phép JOIN khôi phục đúng các bộ gốc. Việc bảng danh mục thực tế còn chứa khách hoặc sản phẩm chưa giao dịch **không làm sai logic phân rã**: trong phép chứng minh lossless, ta đang xét **hình chiếu của cùng một quan hệ gốc**, không phải tùy ý nối mọi bản ghi danh mục bên ngoài phạm vi đó.

### 5.5. DDL PostgreSQL cho thiết kế bảo toàn phụ thuộc

Đoạn SQL sau độc lập, có thể chạy theo thứ tự trên cơ sở dữ liệu thử nghiệm trống:

~~~~sql
CREATE TABLE khach_hang_3nf (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ten_kh VARCHAR(120) NOT NULL
);

CREATE TABLE san_pham_3nf (
    ma_sp VARCHAR(20) PRIMARY KEY,
    ten_sp VARCHAR(120) NOT NULL
);

CREATE TABLE don_hang_3nf (
    ma_don VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    CONSTRAINT fk_don_khach_3nf
        FOREIGN KEY (ma_kh)
        REFERENCES khach_hang_3nf(ma_kh)
);

CREATE TABLE dong_don_hang_3nf (
    ma_don VARCHAR(20) NOT NULL,
    ma_sp VARCHAR(20) NOT NULL,
    so_luong INTEGER NOT NULL,
    CONSTRAINT pk_dong_3nf PRIMARY KEY (ma_don, ma_sp),
    CONSTRAINT fk_dong_don_3nf
        FOREIGN KEY (ma_don) REFERENCES don_hang_3nf(ma_don),
    CONSTRAINT fk_dong_sp_3nf
        FOREIGN KEY (ma_sp) REFERENCES san_pham_3nf(ma_sp),
    CONSTRAINT ck_dong_so_luong_3nf CHECK (so_luong > 0)
);

INSERT INTO khach_hang_3nf (ma_kh, ten_kh)
VALUES ('K01', 'An'), ('K02', 'Bình');

INSERT INTO san_pham_3nf (ma_sp, ten_sp)
VALUES ('P01', 'Bút'), ('P02', 'Sổ');

INSERT INTO don_hang_3nf (ma_don, ma_kh)
VALUES ('D01', 'K01'), ('D02', 'K01');

INSERT INTO dong_don_hang_3nf (ma_don, ma_sp, so_luong)
VALUES
    ('D01', 'P01', 2),
    ('D01', 'P02', 1),
    ('D02', 'P01', 3);
~~~~

Các PK bảo đảm:

- Một MaKhach chỉ có một hàng KHACH_HANG với một TenKhach hiện tại.
- Một MaSP chỉ có một hàng SAN_PHAM với một TenSP hiện tại.
- Một MaDon chỉ có một hàng DON_HANG với một MaKhach.
- Một cặp (MaDon, MaSP) chỉ có một hàng DONG_DON_HANG với một SoLuong.

Các FK bảo vệ quan hệ giữa đơn–khách, dòng–đơn và dòng–sản phẩm. **FD và FK là hai loại ràng buộc khác nhau**; chúng cùng cần thiết trong mô hình dữ liệu đầy đủ.

Truy vấn khôi phục dạng dữ liệu tổng hợp:

~~~~sql
SELECT
    d.ma_don,
    d.ma_kh,
    k.ten_kh,
    ct.ma_sp,
    sp.ten_sp,
    ct.so_luong
FROM dong_don_hang_3nf AS ct
JOIN don_hang_3nf AS d
    ON d.ma_don = ct.ma_don
JOIN khach_hang_3nf AS k
    ON k.ma_kh = d.ma_kh
JOIN san_pham_3nf AS sp
    ON sp.ma_sp = ct.ma_sp
ORDER BY d.ma_don, ct.ma_sp;
~~~~

| ma_don | ma_kh | ten_kh | ma_sp | ten_sp | so_luong |
| --- | --- | --- | --- | --- | ---: |
| D01 | K01 | An | P01 | Bút | 2 |
| D01 | K01 | An | P02 | Sổ | 1 |
| D02 | K01 | An | P01 | Bút | 3 |

Nếu đổi tên khách K01, chỉ cần sửa **một hàng KHACH_HANG**; mọi đơn tham chiếu K01 tiếp tục đọc đúng tên hiện tại. Nếu cần lưu **tên tại thời điểm giao dịch**, đó là một yêu cầu dữ liệu lịch sử khác, cần mô hình snapshot hoặc phiên bản có ý nghĩa nghiệp vụ, không nên tạo bản sao dữ liệu chỉ vì muốn tránh JOIN.

### 5.6. Kiểm tra sự bảo toàn bằng chính DDL

Những thao tác sau dự kiến bị từ chối bởi ràng buộc liên quan:

~~~~sql
-- Hai bản ghi cùng mã khách nhưng khác tên:
INSERT INTO khach_hang_3nf (ma_kh, ten_kh)
VALUES ('K01', 'Tên khác');
-- Vi phạm PRIMARY KEY(ma_kh).

-- Hai bản ghi cùng mã đơn nhưng khác khách:
INSERT INTO don_hang_3nf (ma_don, ma_kh)
VALUES ('D01', 'K02');
-- Vi phạm PRIMARY KEY(ma_don).

-- Hai bản ghi cùng cặp đơn và sản phẩm:
INSERT INTO dong_don_hang_3nf (ma_don, ma_sp, so_luong)
VALUES ('D01', 'P01', 99);
-- Vi phạm PRIMARY KEY(ma_don, ma_sp).

-- Dòng đơn tham chiếu một mã đơn chưa tồn tại:
INSERT INTO dong_don_hang_3nf (ma_don, ma_sp, so_luong)
VALUES ('D99', 'P01', 1);
-- Vi phạm FOREIGN KEY.
~~~~

Chạy từng câu thử lỗi riêng, không dùng làm dữ liệu khởi tạo thành công. Việc PK ngăn hai hàng có cùng vế trái nhưng khác vế phải là một cách **thực thi mạnh** các FD liên quan trong ví dụ này: vế trái của từng FD là khóa của một bảng con.

**Nhận xét đáng chú ý:** Bốn bảng kết quả không chỉ đạt 3NF, mà với các FD đã xác định chúng còn đạt **BCNF** vì các vế trái FD không tầm thường tương ứng đều là khóa. Điều này cho thấy **BCNF không phải lúc nào cũng làm mất phụ thuộc**; vấn đề mất phụ thuộc chỉ xuất hiện ở **một số cấu trúc FD và phép phân rã cụ thể**.

## 6. BCNF: chuẩn hóa mạnh hơn nhưng có thể mất phụ thuộc

**Dạng chuẩn Boyce–Codd (BCNF)** yêu cầu: với **mọi FD không tầm thường** \(X\to Y\) trong \(F^+\), **X phải là siêu khóa** của quan hệ đang xét.

So với 3NF:

- **BCNF** chỉ chấp nhận vế trái là siêu khóa.
- **3NF** còn chấp nhận trường hợp vế trái không là siêu khóa **nếu thuộc tính vế phải là thuộc tính nguyên tố**.

Vì vậy:

\[
BCNF\ \Longrightarrow\ 3NF
\]

nhưng chiều ngược lại **không luôn đúng**.

Phân rã theo một FD vi phạm BCNF có thể tạo hai lược đồ và vẫn **không mất mát**. Tuy nhiên, sau nhiều lần phân rã, một FD ban đầu có thể liên hệ các thuộc tính nằm ở **nhiều bảng**, khiến nó không còn suy ra được từ tập FD cục bộ.

### 6.1. Phản ví dụ kinh điển

Cho:

\[
R(A,B,C)
\]

và tập phụ thuộc hàm:

\[
F=\{AB\rightarrow C,\quad C\rightarrow B\}
\]

Đọc bằng lời:

- Cặp **(A,B)** xác định C.
- Giá trị **C** xác định B.

Không có FD nào khác ngoài các FD có thể suy ra logic từ hai điều trên. Ta giả định **A, B, C là các giá trị xác định**, tránh vấn đề NULL kiểu SQL.

### 6.2. Xác định khóa ứng viên

Tính các bao đóng quan trọng:

\[
\begin{aligned}
(AB)^+ &= \{A,B,C\}
&&\text{(nhờ }AB\to C\text{)}\\
(AC)^+ &= \{A,B,C\}
&&\text{(nhờ }C\to B\text{)}\\
C^+ &= \{C,B\}
&&\text{(không suy ra A)}\\
A^+ &= \{A\},\qquad B^+=\{B\}
\end{aligned}
\]

Vì vậy hai **khóa ứng viên** là:

\[
\boxed{\{A,B\}\quad\text{và}\quad\{A,C\}}
\]

Thuộc tính **A, B, C đều là thuộc tính nguyên tố**, bởi mỗi thuộc tính nằm trong ít nhất một khóa ứng viên.

### 6.3. Quan hệ R đang ở 3NF nhưng không ở BCNF

Đối với \(AB\to C\), AB là siêu khóa nên **đạt cả 3NF lẫn BCNF**.

Đối với \(C\to B\):

- C **không phải siêu khóa**, vì \(C^+=\{B,C\}\) không chứa A.
- B **là thuộc tính nguyên tố**, vì B nằm trong khóa ứng viên AB.

Do đó FD \(C\to B\) **được chấp nhận trong 3NF** nhưng **vi phạm BCNF**. Toàn bộ lược đồ R đạt **3NF mà không đạt BCNF**.

Đây không phải lỗi chứng minh: 3NF chủ ý cho phép một số FD như vậy để có thể bảo toàn phụ thuộc khi phân rã BCNF không thực hiện được cả hai mục tiêu.

### 6.4. Phân rã thành hai quan hệ BCNF

Phân rã theo phụ thuộc vi phạm \(C\to B\):

\[
R_1(C,B),\qquad R_2(A,C)
\]

Kiểm tra từng lược đồ:

- Trong **R1(C,B)** có FD \(C\to B\). C là khóa của R1, nên **R1 đạt BCNF**.
- Trong **R2(A,C)**, không có FD không tầm thường nào với vế trái không là siêu khóa suy ra từ F. Theo các FD đang xét, **R2 đạt BCNF**.

**Kiểm tra không mất mát:** Giao các thuộc tính là \(R_1\cap R_2=\{C\}\); F có \(C\to B\), tức C xác định phần \(R_1-R_2=\{B\}\). Vì vậy phân rã thành CB và AC là **không mất mát thông tin**.

### 6.5. Nhưng phụ thuộc \(AB\to C\) không còn được bảo toàn

Chiếu tập FD lên từng bảng:

~~~~text
R1(C,B):  C → B
R2(A,C):  không có FD không tầm thường cần bổ sung
~~~~

Tập phụ thuộc cục bộ có thể xét là:

\[
G=\{C\to B\}
\]

Để kiểm tra \(AB\to C\), tính bao đóng theo **G**, không theo F gốc:

\[
(AB)^+_G=\{A,B\}
\]

Không có FD trong G với vế trái C được kích hoạt vì C chưa thuộc bao đóng. Do đó **C không được suy ra**:

\[
G\not\models AB\to C
\]

Kết luận:

| Thuộc tính của phân rã \(R_1(C,B),R_2(A,C)\) | Kết quả |
| --- | --- |
| Cả hai bảng đạt BCNF | **Có** |
| Phân rã không mất mát thông tin theo F | **Có** |
| Bảo toàn FD \(C\to B\) | **Có** |
| Bảo toàn FD \(AB\to C\) | **Không** |
| Bảo toàn đầy đủ F | **Không** |

Nói cách khác, **BCNF được cải thiện** mà **khả năng kiểm tra một FD nghiệp vụ bằng các FD cục bộ bị mất**.

## 7. Nhìn thấy lỗi bằng dữ liệu và SQL

Phản ví dụ trở nên rõ ràng hơn nếu thử chèn hai bảng con **đều hợp lệ theo ràng buộc cục bộ**, nhưng khi JOIN lại tạo dữ liệu vi phạm FD gốc.

### 7.1. Dữ liệu sau phân rã

Bảng R2(A,C):

| A | C |
| --- | --- |
| a1 | c1 |
| a1 | c2 |

Bảng R1(C,B):

| C | B |
| --- | --- |
| c1 | b1 |
| c2 | b1 |

Các bộ này không vi phạm FD cục bộ:

- Trong R1, mỗi C xác định một B; **c1→b1** và **c2→b1** đều hợp lệ. Nhiều C có thể cùng xác định một B.
- Trong R2, cặp (A,C) là duy nhất và không có phụ thuộc nào yêu cầu A xác định C.

JOIN theo C sẽ tạo:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a1 | b1 | c2 |

Hai bộ có cùng **(A,B)=(a1,b1)** nhưng C khác nhau. Chúng **vi phạm \(AB\to C\)**.

Điều này không mâu thuẫn với kết quả “phân rã không mất mát”: các bảng vừa chèn là **hai quan hệ con hợp lệ theo ràng buộc cục bộ**, nhưng chúng **không phải hình chiếu của một trạng thái gốc thỏa F**. Lossless chỉ phát biểu điều gì xảy ra **khi bắt đầu từ trạng thái gốc hợp lệ**.

### 7.2. DDL PostgreSQL có thể tái hiện phản ví dụ

Đoạn SQL sau là một kịch bản độc lập:

~~~~sql
-- R1(C,B): C → B, nên C là khóa.
CREATE TABLE r_cb_bcnf (
    c VARCHAR(10) PRIMARY KEY,
    b VARCHAR(10) NOT NULL
);

-- R2(A,C): cặp (A,C) định danh mỗi dòng của quan hệ này.
CREATE TABLE r_ac_bcnf (
    a VARCHAR(10) NOT NULL,
    c VARCHAR(10) NOT NULL,
    PRIMARY KEY (a, c),
    FOREIGN KEY (c) REFERENCES r_cb_bcnf(c)
);

INSERT INTO r_cb_bcnf (c, b) VALUES
    ('c1', 'b1'),
    ('c2', 'b1');

INSERT INTO r_ac_bcnf (a, c) VALUES
    ('a1', 'c1'),
    ('a1', 'c2');

SELECT ac.a, cb.b, ac.c
FROM r_ac_bcnf AS ac
JOIN r_cb_bcnf AS cb ON cb.c = ac.c
ORDER BY ac.a, cb.b, ac.c;
~~~~

Tất cả INSERT trên đều hợp lệ với PK và FK đã khai báo. Nhưng kết quả JOIN chứa **(a1,b1,c1)** và **(a1,b1,c2)**, vi phạm \(AB\to C\).

Đáng chú ý, ta đã thêm **FK từ AC đến CB** để mọi C ở AC đều có hàng CB tương ứng. FK giúp bảo vệ tồn tại bản ghi được tham chiếu nhưng **vẫn không bảo toàn \(AB\to C\)**.

### 7.3. Tại sao không thể chỉ thêm UNIQUE vào một trong hai bảng?

- R1 chỉ có B và C nên **không có A** để kiểm tra \(AB\to C\).
- R2 chỉ có A và C nên **không có B** để kiểm tra \(AB\to C\).
- Thêm **UNIQUE(C)** ở R2 sẽ **quá chặt**: nó cấm hai giá trị A khác nhau cùng liên kết tới một C, dù điều này hoàn toàn hợp lệ theo F gốc.
- Thêm **UNIQUE(A)** ở R2 cũng quá chặt, vì F không nói A một mình xác định C.

Ví dụ trạng thái gốc hợp lệ:

| A | B | C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a2 | b1 | c1 |

Nó thỏa \(AB\to C\) vì hai cặp AB khác nhau, và thỏa \(C\to B\) vì cùng C xác định cùng B. Nếu buộc C duy nhất ở R2, ta sẽ từ chối trạng thái hợp lệ này. Do đó, **ép một khóa không đúng để thay thế phụ thuộc bị mất** có thể làm sai mô hình.

### 7.4. Muốn giữ BCNF thì phải trả giá gì?

Nếu vẫn dùng hai bảng BCNF nói trên, để thực thi \(AB\to C\) cần một cơ chế kiểm tra **liên bảng**:

- Khi thêm/sửa R2(A,C) hoặc sửa R1(C,B), phải xác nhận không có **hai C khác nhau** cùng tạo ra một cặp AB sau JOIN.
- Nếu dùng trigger, phải nghĩ đến **giao dịch đồng thời**, thời điểm kiểm tra, khóa thích hợp hoặc mức cô lập đủ mạnh; trigger kiểm tra trước rồi ghi đơn giản có thể gặp tình huống cạnh tranh.
- Có thể duy trì một **bảng hoặc ánh xạ bổ sung** có ràng buộc duy nhất cho cặp AB, nhưng bảng bổ sung phải được giữ nhất quán và có thể làm giảm lợi ích của phân rã ban đầu.
- Có thể chấp nhận giữ quan hệ ở **3NF** khi việc bảo toàn và thực thi phụ thuộc quan trọng hơn lợi ích đạt BCNF.

Tính bảo toàn phụ thuộc là tiêu chí thiết kế logic; quyết định cách thực thi còn liên quan đến **chi phí vận hành, giao dịch và năng lực của DBMS**.

## 8. Bảo toàn phụ thuộc không đồng nghĩa mọi FD đều thành UNIQUE

Một điểm dễ bị bỏ qua là **bảo toàn ở mức toán học** và **thực thi ràng buộc trong SQL** không phải một khái niệm.

Ở lược đồ \(R(A,B,C)\) ban đầu:

\[
F=\{AB\to C,\ C\to B\}
\]

R đạt 3NF và cả hai FD đều nằm trong **một quan hệ**, nên không mất thông tin để kiểm tra bằng cách xét từng quan hệ. Nhưng **C không phải siêu khóa**; phụ thuộc \(C\to B\) không thể được bảo vệ chính xác chỉ bằng ràng buộc UNIQUE(C) mà không cấm các trạng thái hợp lệ có nhiều A cùng C.

### 8.1. Ví dụ SQL: khóa không tự thực thi FD không khóa

~~~~sql
CREATE TABLE r_3nf_vi_du (
    a VARCHAR(10) NOT NULL,
    b VARCHAR(10) NOT NULL,
    c VARCHAR(10) NOT NULL,
    CONSTRAINT pk_r_3nf PRIMARY KEY (a, b),
    CONSTRAINT ak_r_3nf UNIQUE (a, c)
);

INSERT INTO r_3nf_vi_du (a, b, c) VALUES
    ('a1', 'b1', 'c1'),
    ('a2', 'b2', 'c1');
~~~~

Các thao tác trên **được PRIMARY KEY(A,B) và UNIQUE(A,C) cho phép**, vì hai cặp AB khác nhau và hai cặp AC khác nhau. Tuy nhiên, cùng **C = c1** lại có **B = b1** và **B = b2**, vi phạm \(C\to B\).

Ta có thể phát hiện bằng một truy vấn cục bộ:

~~~~sql
SELECT c
FROM r_3nf_vi_du
GROUP BY c
HAVING COUNT(DISTINCT b) > 1;
-- Kết quả: c1
~~~~

Vì b được khai báo NOT NULL, COUNT(DISTINCT b) phản ánh số giá trị B khác nhau của từng C trong ví dụ. Nếu b có thể NULL, phải xác định ngữ nghĩa NULL và đổi cách kiểm tra cho phù hợp.

**Kết luận:** Lược đồ 3NF bảo toàn phụ thuộc ở đây có thể **phát hiện vi phạm trong chính bảng R**, nhưng muốn **ngăn vi phạm ngay khi ghi** có thể cần một cơ chế ràng buộc liên bộ như trigger/giao dịch hoặc tổ chức bảng theo cách khác. Điều này khác với ví dụ tổng hợp mục 5, nơi vế trái của các FD được chọn làm khóa của từng bảng nhỏ nên PK bảo vệ được trực tiếp.

### 8.2. Phân biệt các công cụ ràng buộc

| Cơ chế | Kiểm tra tốt điều gì? | Hạn chế liên quan đến FD |
| --- | --- | --- |
| **PRIMARY KEY** | Định danh duy nhất, không NULL | Không trực tiếp biểu diễn FD có vế trái không là siêu khóa |
| **UNIQUE** | Không trùng các tổ hợp thuộc tính được chọn theo ngữ nghĩa DBMS | Có thể **quá chặt** nếu muốn diễn đạt \(X\to Y\) nhưng X được phép lặp |
| **NOT NULL** | Một thuộc tính phải có giá trị | Không diễn đạt mối quan hệ xác định giữa các bộ |
| **FOREIGN KEY** | Giá trị tham chiếu phải có hàng cha phù hợp | Không tự kiểm tra mọi FD liên bảng hoặc điều kiện có ít nhất một hàng con |
| **CHECK** | Điều kiện trên giá trị một hàng, miền giá trị và tổ hợp cột của hàng | Trong PostgreSQL không trực tiếp truy vấn các hàng khác để kiểm tra FD liên bộ |
| **Trigger/kiểm tra giao dịch** | Có thể kiểm tra logic phức tạp, kể cả liên bảng | Cần thiết kế thời điểm, khóa và xử lý cạnh tranh đồng thời đúng đắn |
| **Kiểm tra dữ liệu định kỳ** | Phát hiện vi phạm đã lọt vào dữ liệu | Không thay thế chặn vi phạm ngay khi ghi |

Nếu một phụ thuộc **không bảo toàn** trong phép phân rã, chi phí kiểm tra có thể cao hơn vì phải JOIN hoặc đồng bộ trạng thái qua nhiều bảng. Nếu phụ thuộc **bảo toàn** nhưng vế trái không là khóa, vẫn cần xác định cách thực thi phù hợp.

## 9. So sánh mức chuẩn hóa và các mục tiêu đánh đổi

### 9.1. 2NF, 3NF, BCNF giải quyết những vấn đề khác nhau

| Mức chuẩn | Ý tưởng cốt lõi theo phụ thuộc hàm | Điều cần lưu ý |
| --- | --- | --- |
| **1NF** | Các cột chứa giá trị đơn theo mô hình quan hệ đang chọn, không dùng nhóm lặp dạng phi quan hệ | Chưa giải quyết dư thừa do FD |
| **2NF** | Đạt 1NF; không có thuộc tính không nguyên tố phụ thuộc một phần vào một khóa ứng viên | Chưa loại mọi phụ thuộc bắc cầu hoặc FD có vế trái không là khóa |
| **3NF** | Với mỗi \(X\to A\) không tầm thường, X là siêu khóa **hoặc** A là thuộc tính nguyên tố | Có thể còn bất thường do FD với vế trái không là khóa |
| **BCNF** | Với mọi FD không tầm thường, vế trái là siêu khóa | Loại được nhiều bất thường hơn do FD nhưng phân rã có thể không bảo toàn FD |

**Điểm thực hành:** Một bảng đạt 3NF chưa chắc đạt BCNF; một bộ bảng đạt BCNF không tự chứng minh rằng **phép phân rã của cả hệ thống** bảo toàn toàn bộ phụ thuộc ban đầu.

Các dạng chuẩn cao hơn như **4NF** hoặc **5NF** quan tâm thêm đến phụ thuộc đa trị và phụ thuộc nối. Đạt BCNF không đồng nghĩa tự động giải quyết mọi loại dư thừa. Bài này giới hạn ở **phụ thuộc hàm**, vì đó là nền tảng của đánh đổi 3NF–BCNF.

### 9.2. Nhận định “càng chuẩn hóa cao càng tốt” thiếu điều kiện

Một lựa chọn thiết kế phải xét cả:

1. **Mức giảm dư thừa:** Dữ liệu có đang lặp theo một FD với vế trái không là khóa không?
2. **An toàn khi cập nhật:** Một thay đổi nghiệp vụ cần sửa một hay nhiều hàng?
3. **Bảo toàn FD:** Có thể kiểm tra các quy tắc gốc mà không JOIN giữa các bảng không?
4. **Không mất mát:** Các phép JOIN dự kiến có khôi phục đúng thông tin không?
5. **Chi phí truy vấn:** Truy vấn phổ biến có thêm JOIN hoặc UNION phức tạp không? Có chỉ mục thích hợp không?
6. **Chi phí ghi và tính đồng thời:** Quy tắc nào phải thực thi trong nhiều bảng và nhiều giao dịch?
7. **Tính tiến hóa:** Khi đổi khóa nghiệp vụ, thêm thuộc tính hoặc bổ sung nguồn dữ liệu, lược đồ nào dễ duy trì hơn?
8. **Mức bảo đảm ràng buộc ở DBMS:** Những quy tắc nào có thể thực thi bằng PK/FK/UNIQUE, quy tắc nào cần trigger hay quy trình khác?

Với phản ví dụ \(R(A,B,C)\):

- Ở **3NF giữ nguyên R**, cả AB→C và C→B có thể được kiểm tra **trong một bảng**. Tuy nhiên, B bị lặp theo cùng C ở nhiều hàng, có nguy cơ cập nhật sai và phải bảo vệ C→B bằng cơ chế phù hợp.
- Ở **BCNF tách AC và CB**, B chỉ lưu một lần theo mỗi C, nên cập nhật B cho C đơn giản hơn. Nhưng điều kiện AB→C **không còn cục bộ**, có thể bị vi phạm khi các bảng con đều thỏa PK/FK riêng.

Không có “miễn phí”: **giảm dư thừa có thể làm tăng chi phí bảo vệ một phụ thuộc khác**.

### 9.3. Bảng quyết định 3NF và BCNF

| Tiêu chí | Tổng hợp 3NF đúng thuật toán | Phân rã BCNF |
| --- | --- | --- |
| Các bảng kết quả có mức chuẩn | 3NF, đôi khi đồng thời đạt BCNF | BCNF |
| Không mất mát thông tin | Có bảo đảm theo thuật toán | Có thể xây dựng bằng phân rã không mất mát |
| Bảo toàn toàn bộ FD đã biết | **Có bảo đảm theo thuật toán** | **Không có bảo đảm tổng quát** |
| Bất thường do FD có vế trái không là khóa | Có thể còn ở một số lược đồ 3NF | Được loại theo các FD đã xét |
| Kiểm tra FD trong một bảng | Có thể tổ chức cục bộ | Một số FD gốc có thể cần JOIN |
| Bảo đảm mọi FD chỉ bằng UNIQUE/PK | **Không tự bảo đảm** | **Không tự bảo đảm**, nhất là FD không được bảo toàn |
| Chi phí JOIN, cập nhật và chỉ mục | Phụ thuộc số bảng và truy vấn | Phụ thuộc phép phân rã, có thể thêm bảng và kiểm tra liên bảng |
| Khi nào thường cân nhắc | Yêu cầu bảo toàn ràng buộc quan trọng và muốn một điểm bắt đầu có bảo đảm | Muốn giảm tối đa dư thừa do FD và đã xác nhận không mất phụ thuộc quan trọng hoặc có cơ chế thực thi bổ sung |

Đừng biến bảng này thành quy tắc “luôn chọn 3NF”. Nếu phép phân rã BCNF **vẫn bảo toàn mọi FD**, BCNF thường rất hấp dẫn: chuẩn hóa mạnh hơn mà không chịu bất lợi về bảo toàn phụ thuộc. Ví dụ bốn bảng ở mục 5 là một trường hợp như vậy.

### 9.4. Chi phí truy vấn không chỉ là số lượng JOIN

Một bảng lớn có ít JOIN chưa chắc nhanh hơn vì:

- Dữ liệu lặp làm tăng kích thước bảng và chỉ mục, tăng I/O hoặc chi phí cập nhật.
- Dữ liệu được tách có thể giúp chỉ mục nhỏ hơn và bộ lọc có tính chọn lọc cao hơn.
- Trình tối ưu truy vấn và thống kê có thể xử lý JOIN hiệu quả, đặc biệt trên các khóa được lập chỉ mục hợp lý.
- Ngược lại, nhiều JOIN trên bảng lớn và luồng báo cáo phức tạp cũng có thể là chi phí thực.

Cần đo **truy vấn thực tế**, kế hoạch thực thi, số lần ghi, lock contention, dung lượng lưu trữ và tốc độ tăng dữ liệu. **Không nên phá bỏ một phụ thuộc nghiệp vụ chỉ để giảm một JOIN trong báo cáo.**

### 9.5. Phi chuẩn hóa là một quyết định khác

Một hệ thống có thể cố ý lưu thêm bản sao tên khách hoặc tổng doanh thu đã tính để phục vụ báo cáo, cache hay kho dữ liệu phân tích. Đây là **phi chuẩn hóa có chủ đích** (*denormalization*), nên đi kèm:

- Xác định **nguồn dữ liệu chuẩn** (*source of truth*).
- Quy tắc cập nhật hoặc làm mới bản sao, độ trễ được phép và chiến lược xử lý lỗi.
- Kiểm tra nhất quán định kỳ, giám sát vi phạm và cơ chế sửa chữa.
- Tài liệu phân biệt trường **snapshot lịch sử** với trường **bản sao để tối ưu**.

**Materialized view** hoặc mô hình dữ liệu phân tích có thể giúp truy vấn nhanh mà không buộc phải bỏ ràng buộc ở các bảng ghi giao dịch. Khi dùng document hoặc đồ thị, câu hỏi tương tự vẫn tồn tại: thông tin chung được lưu tại một nơi hay nhiều bản sao, và quy tắc nghiệp vụ được kiểm chứng bằng cách nào?

## 10. Quy trình lựa chọn mức chuẩn hóa có thể kiểm chứng

Một quy trình thực tế nên bắt đầu từ **ràng buộc nghiệp vụ**, thay vì từ mục tiêu “phải chia thành bao nhiêu bảng”.

### Bước 1 — Xác định ý nghĩa của một bộ

Ghi rõ một hàng đang biểu diễn sự kiện nào: một khách hàng, một đơn hàng, một dòng đơn hay một lần ghi nhận giá. Cùng một cột có thể mang ý nghĩa khác nhau tùy độ hạt. Ví dụ **MaSP→TenSP** có thể đúng với danh mục sản phẩm hiện tại nhưng không thay thế nhu cầu lưu **TenSP tại thời điểm bán** khi doanh nghiệp yêu cầu snapshot lịch sử.

### Bước 2 — Thu thập phụ thuộc hàm từ nghiệp vụ

Ghi mỗi FD bằng câu có thể phản chứng:

- **MaDon→MaKhach:** một mã đơn luôn có cùng mã khách?
- **MaKhach→TenKhach:** cùng một mã khách có luôn cùng một tên hiện tại?
- **(MaDon,MaSP)→SoLuong:** sản phẩm được xuất hiện nhiều dòng trong một đơn hay không?

Hỏi về ngoại lệ, thời gian hiệu lực, tenant, thay đổi mã và dữ liệu nhập từ nhiều hệ thống. Tránh coi các ràng buộc **tạm đúng trong mẫu thử** là phụ thuộc hàm toàn cục.

### Bước 3 — Tìm khóa và phủ tối thiểu

Tính bao đóng các tập thuộc tính để tìm siêu khóa và khóa ứng viên. Với các FD đã được xác nhận, tìm phủ tối thiểu; kiểm tra thuộc tính thừa và FD dư thừa. Nếu thiếu các FD quan trọng ngay từ đầu, cả phép chứng minh 3NF lẫn BCNF đều có thể dẫn đến mô hình sai nghiệp vụ.

### Bước 4 — Tạo phương án 3NF có bảo đảm

Dùng thuật toán tổng hợp 3NF:

- Mỗi FD trong phủ tối thiểu có một lược đồ chứa đầy đủ thuộc tính của FD.
- Loại các lược đồ con dư thừa theo quy tắc thuật toán.
- Bảo đảm có một lược đồ chứa **khóa ứng viên của quan hệ gốc**.

Đây là phương án tham chiếu để đối chiếu với các lựa chọn khác, bởi nó có bảo đảm **lossless và preservation** đối với F.

### Bước 5 — Thử phân rã BCNF

Xác định các FD vi phạm BCNF, tức có vế trái không là siêu khóa. Phân rã từng bước theo các phụ thuộc vi phạm, ghi rõ:

- Giao của hai lược đồ con và lý do phép phân rã **không mất mát**.
- FD được chiếu lên mỗi bảng con.
- Mọi FD ban đầu còn suy ra được từ hợp các FD cục bộ không, dùng **bao đóng** hoặc thuật toán kiểm tra preservation thích hợp.

Không dừng ở việc mọi bảng con “trông giống BCNF”: phải kiểm tra **kết quả tổng thể của phép phân rã**.

### Bước 6 — Đánh giá phần phụ thuộc bị mất

Với mỗi FD không bảo toàn:

1. Nó là **quy tắc nghiệp vụ cứng**, nếu vi phạm sẽ làm sai giao dịch hay báo cáo không?
2. Tần suất các thao tác có thể vi phạm là bao nhiêu?
3. Để kiểm tra, phải JOIN bao nhiêu bảng? Có cần khóa hay cô lập giao dịch đặc biệt?
4. Có phương án BCNF khác bảo toàn được FD đó không?
5. Nếu không, có nên **giữ 3NF**, thêm bảng/ràng buộc hỗ trợ, hoặc chấp nhận quy tắc kiểm tra bổ sung với chi phí rõ ràng?

### Bước 7 — Triển khai và kiểm chứng ở SQL

Chuyển các định danh và tham chiếu thành **PRIMARY KEY**, **UNIQUE**, **NOT NULL**, **FOREIGN KEY** và kiểm tra giá trị bằng **CHECK**. Đối với FD không thể diễn đạt chính xác bằng những ràng buộc này, tài liệu hóa phương thức thực thi bổ sung.

Chuẩn bị dữ liệu phản ví dụ: hai bộ cùng X nhưng khác Y, hai khóa ghép trùng nhau, bản ghi không có cha, thuộc tính NULL không phù hợp. Nếu cần trigger, thực hiện thử nghiệm cả tình huống ghi **đồng thời**, không chỉ INSERT tuần tự trong một kết nối.

### Bước 8 — Đo lường và duy trì

Sau khi tính đúng đã được bảo vệ:

- Đo khối lượng JOIN, số bản ghi, chỉ mục, độ trễ truy vấn và chi phí ghi.
- Kiểm tra thay đổi chính sách nghiệp vụ có làm một FD cũ không còn hợp lệ không.
- Nếu tạo bảng tổng hợp hoặc view vật hóa, theo dõi độ mới và tính nhất quán với nguồn chính.
- Đưa những FD quan trọng vào tài liệu schema, kiểm thử tích hợp và kiểm tra dữ liệu vận hành.

~~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ và FD"] --> B["Khóa ứng viên, phủ tối thiểu"]
    B --> C["Tổng hợp 3NF: lossless + preserve"]
    C --> D{"Có nên thử BCNF?"}
    D -- "Không" --> H["Thực thi ràng buộc và đo truy vấn"]
    D -- "Có" --> E["Phân rã BCNF không mất mát"]
    E --> F{"Các FD gốc còn bảo toàn?"}
    F -- "Có" --> H
    F -- "Không" --> G["Đánh giá chi phí kiểm tra liên bảng / giữ 3NF"]
    G --> H
    H --> I["Kiểm thử phản ví dụ và đồng thời"]
~~~~

## 11. Bài tập tự kiểm tra

Các bài tập dưới đây dùng ngữ nghĩa quan hệ toán học với **giá trị xác định**; khi hỏi về SQL, giả sử các cột khóa và cột kiểm tra FD đều **NOT NULL** trừ khi đề bài nói khác.

### Bài 1 — Phân biệt hai tiêu chí

Một nhóm chia R thành R1 và R2. Với mọi trạng thái r hợp lệ theo F, phép nối từ các hình chiếu khôi phục đúng r. Tuy nhiên, một FD ban đầu không suy ra được từ các FD của từng bảng con.

**Câu hỏi:** Phân rã có lossless không? Có bảo toàn phụ thuộc không?

**Đáp án:** **Có lossless**, bởi JOIN các hình chiếu của mọi trạng thái hợp lệ khôi phục đúng r. **Không bảo toàn phụ thuộc**, bởi một FD gốc không thể suy ra từ hợp các FD cục bộ. Hai tiêu chí độc lập.

### Bài 2 — Tìm khóa ứng viên

Cho \(R(A,B,C)\), \(F=\{AB\to C,\ C\to B\}\).

**Câu hỏi:** Những tập nào là khóa ứng viên? C có là siêu khóa không?

**Đáp án:** **AB và AC** là hai khóa ứng viên. Từ AB suy ra C; từ AC suy ra B nhờ C→B. Bỏ A khỏi hai tập không suy ra được A; một mình A hay B cũng không đủ. **C không là siêu khóa** vì \(C^+=\{C,B\}\), không có A.

### Bài 3 — Quan hệ ở 3NF hay BCNF?

Vẫn với \(R(A,B,C)\) và F ở bài 2.

**Câu hỏi:** Tại sao R ở 3NF nhưng không ở BCNF?

**Đáp án:** Trong FD \(AB\to C\), AB là siêu khóa. Trong \(C\to B\), C không là siêu khóa nhưng B là **thuộc tính nguyên tố** vì nằm trong khóa ứng viên AB; vì vậy FD này được 3NF chấp nhận. BCNF yêu cầu C là siêu khóa cho \(C\to B\), nên R **không đạt BCNF**.

### Bài 4 — Kiểm tra lossless cho phép phân rã BCNF

Phân rã \(R(A,B,C)\) thành \(R_1(C,B)\) và \(R_2(A,C)\).

**Câu hỏi:** Vì sao không mất mát thông tin theo F?

**Đáp án:** Hai lược đồ giao nhau ở C. FD **C→B** suy ra từ F, nên các thuộc tính chung C xác định các thuộc tính chỉ có trong R1. Theo tiêu chí phân rã hai bảng, đây là **phân rã không mất mát**.

### Bài 5 — Kiểm tra phụ thuộc sau phân rã

Trong phép phân rã bài 4, tập FD cục bộ có thể dùng là \(G=\{C\to B\}\).

**Câu hỏi:** \(AB\to C\) có được bảo toàn không? Hãy tính bao đóng.

**Đáp án:** Không. Với G, \((AB)^+_G=\{A,B\}\); chưa có C để kích hoạt C→B, nên không suy ra C. Vì vậy \(AB\to C\) **không được bảo toàn**.

### Bài 6 — Hai bảng BCNF hợp lệ có thể JOIN thành trạng thái sai không?

Cho:

~~~~text
R1(C,B) = {(c1,b1), (c2,b1)}
R2(A,C) = {(a1,c1), (a1,c2)}
~~~~

**Câu hỏi:** Hai bảng có thỏa các FD cục bộ không? JOIN có vi phạm FD gốc nào?

**Đáp án:** Cả hai thỏa các FD cục bộ: C xác định một B ở R1; R2 không vi phạm khóa (A,C). Nhưng JOIN sinh **(a1,b1,c1)** và **(a1,b1,c2)**, cùng AB mà khác C; do đó vi phạm **AB→C**. Đây là cách nhìn cụ thể của việc **không bảo toàn phụ thuộc**, không phải bác bỏ tính lossless.

### Bài 7 — Có nên thêm UNIQUE(C) để sửa?

Sau khi tách R thành R1(C,B), R2(A,C), một lập trình viên muốn đặt UNIQUE(C) trên R2 để ngăn cặp AB có nhiều C.

**Câu hỏi:** Phương án này có tương đương với FD gốc \(AB\to C\) không?

**Đáp án:** **Không.** UNIQUE(C) tại R2 cấm hai A khác nhau cùng tham chiếu một C, trong khi F gốc cho phép ví dụ **(a1,b1,c1)** và **(a2,b1,c1)**. UNIQUE(C) là một ràng buộc **quá mạnh**, từ chối dữ liệu hợp lệ.

### Bài 8 — Tổng hợp 3NF từ một tập FD nghiệp vụ

Cho quan hệ:

~~~~text
R(MaDon, MaKhach, TenKhach, MaSP, TenSP, SoLuong)
~~~~

và F gồm MaDon→MaKhach, MaKhach→TenKhach, MaSP→TenSP, (MaDon,MaSP)→SoLuong.

**Câu hỏi:** Đề xuất các bảng để mỗi FD được kiểm tra cục bộ. Có cần thêm bảng chỉ chứa khóa ứng viên không?

**Đáp án:** Dùng **DON_HANG(MaDon,MaKhach)**, **KHACH_HANG(MaKhach,TenKhach)**, **SAN_PHAM(MaSP,TenSP)**, **DONG_DON_HANG(MaDon,MaSP,SoLuong)**. Mỗi FD nằm trong một bảng. Không cần bảng khóa riêng vì DONG_DON_HANG đã chứa khóa ứng viên **(MaDon,MaSP)** của R gốc.

### Bài 9 — “Mọi bảng ở 3NF” có đủ để kết luận không?

Một kỹ sư tự chia bảng rồi xác nhận từng bảng riêng đều ở 3NF.

**Câu hỏi:** Từ đó có thể kết luận chắc chắn phép phân rã là lossless và bảo toàn đầy đủ FD không?

**Đáp án:** **Không.** Mức chuẩn của từng bảng không thay thế kiểm tra tính **không mất mát** và **bảo toàn phụ thuộc** đối với phân rã tổng thể. Đặc biệt, bảo đảm kép được gắn với **thuật toán tổng hợp 3NF đúng**, chứ không phải một phép chia tùy ý.

### Bài 10 — Khi FD nằm trong một bảng nhưng không phải khóa

Vẫn với R(A,B,C) ở 3NF, một người thêm PK(A,B) và UNIQUE(A,C), rồi tuyên bố FD C→B đã được DB kiểm tra.

**Câu hỏi:** Tuyên bố đúng không? Cho một phản ví dụ.

**Đáp án:** **Không.** Hai hàng **(a1,b1,c1)** và **(a2,b2,c1)** có AB và AC khác nhau, nên không vi phạm hai ràng buộc khóa. Nhưng chúng có cùng C và khác B, vi phạm **C→B**. Cần cơ chế bổ sung để kiểm tra phụ thuộc không khóa.

### Bài 11 — Chọn phương án cho hệ thống giao dịch

Một hệ thống ghi liên tục cần kiểm tra nghiêm ngặt FD ban đầu. Phân rã BCNF giảm dư thừa nhưng làm mất một FD rất quan trọng; chưa có cơ chế kiểm tra liên bảng an toàn khi ghi đồng thời.

**Câu hỏi:** Có bắt buộc chọn BCNF vì đó là mức chuẩn cao hơn không?

**Đáp án:** **Không.** Giữ thiết kế **3NF bảo toàn phụ thuộc** là lựa chọn hợp lý cho đến khi có phương án khác vừa bảo đảm ràng buộc vừa đáp ứng hiệu năng. Nếu vẫn chọn BCNF, phải thiết kế và kiểm chứng cơ chế thực thi FD không bảo toàn, đặc biệt dưới các giao dịch đồng thời.

### Bài 12 — Phi chuẩn hóa để phục vụ báo cáo

Để tăng tốc báo cáo, hệ thống lưu **TenKhach** cùng các dòng đơn mặc dù đã có bảng khách hàng chuẩn. Tên khách có thể thay đổi.

**Câu hỏi:** Đây có nhất thiết là sai không? Cần làm rõ điều gì?

**Đáp án:** Không nhất thiết sai nếu là **phi chuẩn hóa có mục đích**. Cần xác định tên lưu tại dòng đơn là **snapshot tên tại thời điểm giao dịch** hay **bản sao tên hiện tại để tối ưu**. Nếu là snapshot, giá trị có thể khác tên hiện tại mà không phải lỗi; nếu là bản sao, cần quy tắc đồng bộ, kiểm tra nhất quán và xác định nguồn chính.

## 12. Bảng tổng kết

| Khái niệm | Ghi nhớ |
| --- | --- |
| **FD \(X\to Y\)** | Cùng X phải xác định cùng Y trong mọi trạng thái hợp lệ |
| **Phân rã lossless** | JOIN các hình chiếu của trạng thái hợp lệ khôi phục đúng trạng thái gốc |
| **Bảo toàn phụ thuộc** | Mọi FD gốc suy ra được từ hợp các FD cục bộ trên từng quan hệ con |
| **Chiếu phụ thuộc** | Xét cả các FD trong \(F^+\) có thuộc tính nằm trong bảng con |
| **Kiểm tra preservation** | Dùng bao đóng thuộc tính theo **hợp các FD cục bộ**, không dùng F gốc |
| **Tổng hợp 3NF** | Thuật toán chuẩn có thể bảo đảm cả lossless và dependency preservation |
| **BCNF** | Mọi FD không tầm thường có vế trái là siêu khóa |
| **3NF khác BCNF** | 3NF có thể chấp nhận vế phải nguyên tố khi vế trái không là siêu khóa |
| **Phản ví dụ \(AB\to C,\ C\to B\)** | R ở 3NF; phân rã CB và AC ở BCNF, lossless nhưng mất AB→C |
| **Lossless ≠ preservation** | Hai yêu cầu độc lập, không thể suy ra cái này từ cái kia |
| **Preservation ≠ PK/UNIQUE tự đủ** | FD với vế trái không là khóa vẫn có thể cần kiểm tra liên bộ |
| **Mức chuẩn hóa** | Phải cân bằng dư thừa, kiểm tra ràng buộc, truy vấn, giao dịch và khả năng tiến hóa |
| **Phi chuẩn hóa** | Cần mục tiêu rõ, nguồn dữ liệu chuẩn và cơ chế kiểm soát nhất quán |

**Kết luận:** Khi quyết định phân rã một lược đồ, hãy kiểm tra **đồng thời** tính **không mất mát thông tin** và **bảo toàn phụ thuộc hàm**. Tổng hợp 3NF đúng thuật toán cho một điểm xuất phát có hai bảo đảm này; BCNF có thể giảm thêm bất thường do FD nhưng không luôn bảo toàn mọi FD gốc. Từ mô hình logic đến SQL thực tế, điều quan trọng không phải nhãn mức chuẩn cao nhất, mà là **quy tắc nghiệp vụ được ghi rõ, kiểm tra được và duy trì đúng khi dữ liệu và hệ thống thay đổi**.
