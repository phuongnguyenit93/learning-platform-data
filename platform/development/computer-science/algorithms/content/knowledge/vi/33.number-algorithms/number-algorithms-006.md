# Phân rã ma trận để giải nhiều hệ liên quan

**Phân rã ma trận** (*matrix factorization*) là kỹ thuật biểu diễn một ma trận \(A\) thành tích của những ma trận có cấu trúc đặc biệt, để các phép toán về sau dễ thực hiện hơn. Một ứng dụng cốt lõi của **thuật toán số** là giải **nhiều hệ phương trình tuyến tính dùng chung ma trận hệ số**:

\[
\boxed{A x^{(1)}=b^{(1)},\quad A x^{(2)}=b^{(2)},\ \ldots,\ A x^{(k)}=b^{(k)}.}
\]

Khi \(A\) không thay đổi mà chỉ có vế phải \(b\) thay đổi, việc khử Gauss toàn bộ từ đầu cho từng hệ sẽ lặp lại phần công việc tốn kém nhất. Thay vào đó, ta **phân rã A một lần**, rồi giải các hệ tam giác cho từng vế phải.

Phương pháp chính của bài là **LU với pivot một phần** (*LU factorization with partial pivoting*):

\[
\boxed{P A=L U.}
\]

Trong đó:

- \(P\): ma trận hoán vị hàng, mô tả những lần đổi hàng để chọn phần tử trụ;
- \(L\): ma trận **tam giác dưới** có các phần tử đường chéo bằng 1;
- \(U\): ma trận **tam giác trên**.

Sau khi đã có \(P,L,U\), muốn giải \(Ax=b\) chỉ cần:

\[
\boxed{L y=P b,\qquad U x=y.}
\]

Hai phép thế tam giác này tốn **O(n²)** cho một vế phải, trong khi phân rã một ma trận đặc \(n\times n\) tốn **O(n³)**. Với k vế phải, chi phí tổng quát là:

\[
\boxed{O(n^3+k n^2)}
\]

thay vì khoảng \(O(k n^3)\) nếu cứ khử lại từ đầu. Bài học cũng phân biệt khi nào dùng **Cholesky**, **QR**, hoặc **SVD**; cách kiểm tra nghiệm bằng **residual**, xử lý ma trận suy biến/gần suy biến, giới hạn của phép kiểm ngưỡng và cách dùng **Java 17+** để giải nhiều vế phải một cách có thể kiểm chứng.

## 1. Bài toán: một A, nhiều b

Một hệ tuyến tính có dạng:

\[
Ax=b,
\]

với \(A\in\mathbb R^{n\times n}\), \(x\in\mathbb R^n\), \(b\in\mathbb R^n\).

Cho ví dụ:

\[
A=
\begin{bmatrix}
2&1&1\\
4&-6&0\\
-2&7&2
\end{bmatrix}.
\]

Ta muốn giải lần lượt ba hệ:

\[
Ax^{(1)}=
\begin{bmatrix}5\\-2\\9\end{bmatrix},\quad
Ax^{(2)}=
\begin{bmatrix}6\\14\\-5\end{bmatrix},\quad
Ax^{(3)}=
\begin{bmatrix}5\\24\\-18\end{bmatrix}.
\]

Các nghiệm chính xác là:

\[
x^{(1)}=\begin{bmatrix}1\\1\\2\end{bmatrix},\quad
x^{(2)}=\begin{bmatrix}2\\-1\\3\end{bmatrix},\quad
x^{(3)}=\begin{bmatrix}3\\-2\\1\end{bmatrix}.
\]

Ta có thể kiểm bằng phép nhân trực tiếp, chẳng hạn:

\[
A\begin{bmatrix}1\\1\\2\end{bmatrix}
=\begin{bmatrix}
2+1+2\\4-6+0\\-2+7+4
\end{bmatrix}
=\begin{bmatrix}5\\-2\\9\end{bmatrix}.
\]

Điểm quan trọng: **A giống nhau ở cả ba hệ**. Những phép biến đổi chỉ phụ thuộc A có thể được lưu lại và dùng chung.

### Dạng ma trận nhiều vế phải

Ghép các vế phải thành **các cột** của một ma trận:

\[
B=[b^{(1)}\ b^{(2)}\ b^{(3)}]
=\begin{bmatrix}
5&6&5\\
-2&14&24\\
9&-5&-18
\end{bmatrix}.
\]

Ghép nghiệm tương ứng thành \(X=[x^{(1)}\ x^{(2)}\ x^{(3)}]\). Toàn bộ yêu cầu trở thành:

\[
\boxed{A X=B.}
\]

Kết quả:

\[
X=
\begin{bmatrix}
1&2&3\\
1&-1&-2\\
2&3&1
\end{bmatrix}.
\]

**Quy ước chiều dữ liệu:** với ma trận B kích thước \(n\times k\), **cột j là một vế phải**. Nếu lưu trong Java bằng `double[][] b`, phần tử `b[i][j]` là tọa độ i của vế phải j. Rất dễ vô tình coi mỗi **hàng** là một vế phải và giải sai.

## 2. Vì sao không khử Gauss lại từ đầu?

Phương pháp **khử Gauss** thông thường đưa ma trận mở rộng \([A|b]\) về dạng tam giác rồi thế ngược. Với một hệ đặc n×n, số phép toán trong khử tiến là bậc O(n³), còn thế ngược O(n²).

Nếu có k vế phải mà mỗi lần đều tạo lại \([A|b^{(j)}]\) và khử lại các phần tử của A, ta lặp lại phần O(n³) tới k lần:

\[
\boxed{T_{\text{khử lại}}=O(k n^3).}
\]

Nhưng khi A cố định, các hệ số khử và các lần đổi hàng **chỉ phụ thuộc A**, không phụ thuộc b. Phân rã LU lưu lại những thông tin ấy. Chi phí:

- Phân rã một lần: O(n³).
- Mỗi vế phải: hoán vị b, thế tiến và thế ngược, tổng O(n²).
- k vế phải: O(kn²).

Vì vậy:

\[
\boxed{T_{\text{tái sử dụng LU}}=O(n^3+k n^2).}
\]

### Khi k lớn thì tiết kiệm ở đâu?

Nếu n=1000 và k=100, khử lại từ đầu về mặt bậc có khoảng 100 lượt O(n³). Phân rã LU làm **một** lượt O(n³) rồi 100 lần O(n²).

Đây là so sánh về **bậc chi phí**, không phải cam kết một con số thời gian cố định: hiệu năng thật phụ thuộc bộ nhớ đệm, tính toán đa luồng, thư viện BLAS/LAPACK, mô hình ma trận đặc/thưa và cách giải nhiều RHS theo khối.

Khi chỉ có **một** vế phải, LU vẫn là một phương pháp giải hệ phù hợp, nhưng lợi thế **tái sử dụng** không còn là lý do chính. Khi A thay đổi, thường **không thể dùng lại nguyên phân rã LU cũ**.

## 3. Ma trận tam giác và phép thế

Trước khi học LU, cần biết vì sao hệ tam giác dễ giải.

### Ma trận tam giác dưới

Ví dụ:

\[
L=
\begin{bmatrix}
1&0&0\\
\ell_{21}&1&0\\
\ell_{31}&\ell_{32}&1
\end{bmatrix}.
\]

Muốn giải \(Ly=c\), ta tính y từ trên xuống dưới (**forward substitution**):

\[
\boxed{
y_i=\frac{c_i-\sum_{j=0}^{i-1}L_{ij}y_j}{L_{ii}}.
}
\]

Nếu L có đường chéo 1 như trong LU chuẩn, mẫu số \(L_{ii}=1\), chỉ cần:

\[
\boxed{y_i=c_i-\sum_{j<i}L_{ij}y_j.}
\]

Ở mỗi hàng i tính tổng qua i phần tử trước; tổng số phép cộng/nhân trên n hàng là bậc **O(n²)**.

### Ma trận tam giác trên

Ví dụ:

\[
U=
\begin{bmatrix}
u_{11}&u_{12}&u_{13}\\
0&u_{22}&u_{23}\\
0&0&u_{33}
\end{bmatrix}.
\]

Giải \(Ux=y\) từ dưới lên (**back substitution**):

\[
\boxed{
x_i=\frac{y_i-\sum_{j=i+1}^{n-1}U_{ij}x_j}{U_{ii}}.
}
\]

Tổng thời gian cũng là **O(n²)**. Các \(U_{ii}\) phải đủ khác 0 theo tiêu chí số học của phương pháp, nếu không phép chia không an toàn.

### Ý nghĩa trong LU

LU chuyển một bài giải hệ tổng quát thành **hai bài giải hệ tam giác**. Chi phí lớn nằm ở việc xây dựng L và U; các hệ về sau được giải bằng những thao tác rẻ hơn.

## 4. LU cơ bản khi không cần đổi hàng

Trong khử Gauss, muốn loại \(A_{ik}\) nằm dưới phần tử trụ \(A_{kk}\), ta tính **hệ số nhân**:

\[
m_{ik}=\frac{A_{ik}}{A_{kk}}
\]

rồi cập nhật các phần tử phía sau của hàng i:

\[
A_{ij}\leftarrow A_{ij}-m_{ik}A_{kj},\qquad j>k.
\]

Đến cuối, phần còn lại phía trên đường chéo là **U**. Những hệ số nhân \(m_{ik}\) được lưu trong phần dưới đường chéo tạo thành **L** có đường chéo 1.

Về lý thuyết, ta có:

\[
A=LU
\]

khi các phần tử trụ của quá trình không cần đổi hàng đều hợp lệ.

Tuy nhiên, ví dụ:

\[
A=\begin{bmatrix}0&2\\1&3\end{bmatrix}
\]

là ma trận **khả nghịch** vì định thức bằng -2, nhưng phần tử trụ đầu \(A_{00}=0\). Không thể chia cho 0 chỉ vì không cho phép đổi hàng.

Ngay cả khi pivot không bằng 0 nhưng cực nhỏ, chia cho nó có thể tạo hệ số nhân rất lớn, khuếch đại sai số dấu phẩy động. Do đó trong thực tế cần **pivoting**.

## 5. Pivot một phần: vì sao có P A = L U?

**Pivot một phần** (*partial pivoting*) ở cột k chọn trong các hàng i≥k một hàng có:

\[
\boxed{
r=\operatorname*{arg\,max}_{i=k,\ldots,n-1}|A_{ik}^{\text{hiện tại}}|.
}
\]

Nếu r≠k, đổi hàng r với hàng k. Các lần đổi hàng được biểu diễn bằng **ma trận hoán vị P**.

Sau khử, quan hệ chính xác là:

\[
\boxed{PA=LU}
\]

chứ **không phải** lúc nào cũng là A=LU.

### Ý nghĩa của ma trận P

P là ma trận nhận được bằng cách hoán vị các hàng của ma trận đơn vị. Nó chỉ thay thứ tự hàng, không thay ý nghĩa hệ phương trình nếu vế phải cũng được hoán vị **giống hệt**.

Nếu:

\[
P=\begin{bmatrix}
0&1&0\\
1&0&0\\
0&0&1
\end{bmatrix},
\]

thì \(PA\) đặt hàng cũ số 1 lên hàng mới số 0, hàng cũ số 0 xuống hàng mới số 1, hàng cũ số 2 giữ nguyên.

Khi giải hệ:

\[
Ax=b,
\]

nhân cả hai vế với P:

\[
PAx=Pb.
\]

Vì \(PA=LU\):

\[
LUx=Pb.
\]

Đặt \(Ux=y\), thu được **hai bước giải**:

\[
\boxed{Ly=Pb,\qquad Ux=y.}
\]

**Sai lầm phổ biến:** áp dụng hoán vị lên A khi phân rã nhưng lại không hoán vị b lúc solve. Khi đó nghiệm nhận được là nghiệm của **một hệ khác**.

## 6. Ví dụ phân rã LU với pivot cụ thể

Lấy lại:

\[
A=
\begin{bmatrix}
2&1&1\\
4&-6&0\\
-2&7&2
\end{bmatrix}.
\]

Ở cột 0, các trị tuyệt đối là 2,4,2. Pivot lớn nhất nằm ở **hàng số 1** (đánh chỉ số từ 0), nên đổi hai hàng 0 và 1.

Sau đổi hàng:

\[
PA=
\begin{bmatrix}
4&-6&0\\
2&1&1\\
-2&7&2
\end{bmatrix}.
\]

Khử dưới phần tử trụ 4:

\[
m_{10}=2/4=0.5,\qquad
m_{20}=-2/4=-0.5.
\]

Các hàng còn lại ở phần U:

~~~text
[4, -6, 0]
[0,  4, 1]
[0,  4, 2]
~~~

Ở cột 1, hai phần tử ứng viên đều có trị tuyệt đối 4; chính sách bài chọn **hàng đầu tiên** khi hòa. Không cần đổi hàng. Ta có:

\[
m_{21}=4/4=1.
\]

Trừ một lần hàng trụ, hàng cuối còn \([0,0,1]\). Kết quả:

\[
\boxed{
L=
\begin{bmatrix}
1&0&0\\
0.5&1&0\\
-0.5&1&1
\end{bmatrix},
\qquad
U=
\begin{bmatrix}
4&-6&0\\
0&4&1\\
0&0&1
\end{bmatrix}.
}
\]

Ma trận P đổi chỗ hai hàng đầu:

\[
P=
\begin{bmatrix}
0&1&0\\
1&0&0\\
0&0&1
\end{bmatrix}.
\]

Kiểm tra:

\[
LU=
\begin{bmatrix}
4&-6&0\\
2&1&1\\
-2&7&2
\end{bmatrix}
=PA.
\]

Đây là một phép kiểm độc lập rất quan trọng của **pha phân rã**, trước khi xét nghiệm x.

### Hoán vị dưới dạng mảng

Không cần lưu một ma trận P có \(n^2\) phần tử, vì P chỉ hoán vị hàng. Ta lưu:

~~~text
pivot = [1,0,2]
~~~

nghĩa là **hàng i trong PA lấy từ hàng pivot[i] của A ban đầu**. Khi giải:

~~~text
c[i] = b[pivot[i]]
~~~

ta có \(c=Pb\).

## 7. Giải tay hệ đầu tiên bằng hai phép thế

Với vế phải:

\[
b^{(1)}=\begin{bmatrix}5\\-2\\9\end{bmatrix},
\]

mảng hoán vị `pivot=[1,0,2]` cho:

\[
Pb^{(1)}
=\begin{bmatrix}-2\\5\\9\end{bmatrix}.
\]

Giải \(Ly=Pb\):

\[
y_0=-2.
\]

\[
y_1=5-0.5(-2)=6.
\]

\[
y_2=9-(-0.5)(-2)-1(6)=9-1-6=2.
\]

Vậy:

\[
\boxed{y=(-2,6,2)^T.}
\]

Giải \(Ux=y\) từ dưới lên:

\[
x_2=2/1=2,
\]

\[
x_1=(6-1\cdot2)/4=1,
\]

\[
x_0=(-2-(-6)\cdot1)/4=1.
\]

Nghiệm:

\[
\boxed{x^{(1)}=(1,1,2)^T.}
\]

**L và U không đổi** khi ta thay \(b^{(1)}\) bằng \(b^{(2)}\) hoặc \(b^{(3)}\). Chỉ tính lại \(Pb\), phép thế tiến và phép thế ngược.

## 8. Nhiều vế phải dưới dạng A X = B

Giả sử B có k cột:

\[
B=
\begin{bmatrix}
|&|&&|\\
b^{(1)}&b^{(2)}&\cdots&b^{(k)}\\
|&|&&|
\end{bmatrix}.
\]

Cùng một phân rã \(PA=LU\), ta giải:

\[
\boxed{LY=PB,\qquad UX=Y.}
\]

Mỗi cột của Y và X là một bài thế tam giác. Có hai cách triển khai:

**Cách dễ hiểu:** dùng một hàm `solve(double[] b)` cho từng cột của B, sau đó ghép các nghiệm thành cột của X. Chi phí O(kn²), dễ kiểm thử và tránh lẫn chỉ số.

**Cách tối ưu theo khối:** dùng các phép toán BLAS level-3 cho nhiều cột B đồng thời, giảm overhead và tận dụng cache tốt hơn trên ma trận lớn. Về bậc, pha giải vẫn là O(kn²), nhưng hằng số thời gian có thể tốt hơn đáng kể.

Trong mã Java minh họa, `solveColumns` dùng cách **gọi solve cho từng cột** để giải thích rõ hoạt động. Ta không phân rã lại A khi chuyển từ cột này sang cột khác.

### Kết quả của ví dụ ba vế phải

\[
B=
\begin{bmatrix}
5&6&5\\
-2&14&24\\
9&-5&-18
\end{bmatrix}
\Longrightarrow
X=
\begin{bmatrix}
1&2&3\\
1&-1&-2\\
2&3&1
\end{bmatrix}.
\]

Cột 0 của X chính là nghiệm x^(1); cột 1 là x^(2); cột 2 là x^(3).

## 9. Mã giả: phân rã LU có pivot một phần

Mã giả sau mô tả phân rã trên **bản sao A**, không thay A đầu vào. Các hệ số của L và U được lưu chung trong một mảng `lu`:

- `lu[i][j]` với i>j lưu phần tử dưới đường chéo của L.
- `lu[i][i]` và i<j lưu các phần tử của U.
- Đường chéo 1 của L là **ngầm định**, không lưu riêng.

~~~text
factor(A):
    require A is n x n, n >= 1
    lu = deepCopy(A)
    pivot = [0,1,...,n-1]

    for k = 0..n-1:
        r = index of maximum abs(lu[i][k]), i >= k

        if abs(lu[r][k]) <= pivotThreshold:
            reject singular/near-singular under chosen policy

        if r != k:
            swap entire rows lu[k], lu[r]
            swap pivot[k], pivot[r]

        for i = k+1 .. n-1:
            lu[i][k] /= lu[k][k]       // L multiplier

            for j = k+1 .. n-1:
                lu[i][j] -= lu[i][k] * lu[k][j]

    return lu, pivot
~~~

### Phải đổi **cả hàng**, kể cả phần đã lưu hệ số L

Khi k>0, các cột trước k của `lu` đã chứa các hệ số khử của L. Nếu pivot làm đổi hai hàng, phải đổi **toàn bộ hàng** trong mảng `lu`, không chỉ phần từ cột k trở đi.

Vì sao? Khi hoán vị hàng hiện tại, những hệ số L đã ghi cần đi theo hàng tương ứng; nếu chỉ đổi phần U mà giữ phần L ở hàng cũ, hệ thức \(PA=LU\) có thể bị phá.

Một mã dùng hai ma trận L và U riêng cũng làm được, nhưng phải hoán vị đúng phần L đã được xây ở các cột trước. Lưu chung là lựa chọn ngắn và thường gặp.

### Chính sách khi có pivot bằng nhau

Để mã xác định, ví dụ chọn **vị trí đầu tiên** đạt trị tuyệt đối lớn nhất: trong vòng tìm max chỉ đổi `r` khi gặp giá trị **lớn hơn nghiêm ngặt**, không đổi khi bằng. Các cách tie-break khác vẫn có thể cho phân rã hợp lệ nhưng mảng pivot và các số trong L/U có thể khác.

## 10. Mã giả: giải một vế phải từ LU đã có

Với `lu` và `pivot` đã được xây:

~~~text
solve(b):
    require b.length = n

    // Forward substitution: L*y = P*b
    for i = 0..n-1:
        sum = b[pivot[i]]
        for j = 0..i-1:
            sum -= lu[i][j] * y[j]
        y[i] = sum

    // Back substitution: U*x = y
    for i = n-1 .. 0:
        sum = y[i]
        for j = i+1..n-1:
            sum -= lu[i][j] * x[j]
        x[i] = sum / lu[i][i]

    return x
~~~

L không cần chia cho phần tử đường chéo, vì mọi \(L_{ii}=1\). U phải chia cho \(U_{ii}\).

Nếu một ma trận có n=1000, chỉ riêng việc lưu L/U đặc cần O(n²) số. Từng vế phải chỉ tạo thêm hai vector y,x độ dài n và chạy O(n²), thay vì khử lại toàn ma trận.

## 11. Java 17+: triển khai LU có pivot và nhiều vế phải

Chương trình **MultipleRightHandSidesLU.java** sau:

1. Kiểm tra A là ma trận vuông không rỗng, mọi hệ số hữu hạn.
2. Tính norm vô cùng của A và một **ngưỡng pivot tương đối** có thể cấu hình.
3. Phân rã `P*A=L*U` với **partial pivoting**; lưu `lu[][]`, `pivot[]` và số lần đổi hàng.
4. Giải riêng `solve(b)` và giải cả ma trận vế phải `solveColumns(B)`, **không tái phân rã A**.
5. Xuất L/U để minh họa, tính định thức từ pivot và đường chéo U, và tính residual \(\|Ax-b\|_\infty\).
6. Từ chối các ma trận suy biến hoặc pivot nhỏ dưới ngưỡng đã chọn, thay vì chia cho 0 hay silently tạo NaN.
7. Kiểm chứng bằng các nghiệm được dựng trước, so với một bộ giải **Gauss–Jordan độc lập** trên hệ nhỏ, và kiểm tra \(PA\approx LU\).
8. Dùng `Locale.US` để in dấu thập phân nhất quán.

**Lưu ý:** mã dưới dùng `double` và là ví dụ thuật toán số, không phải thư viện tối ưu tốc độ hoặc có chứng nhận sai số cho mọi ma trận. Ngưỡng pivot là **chính sách thực dụng**, không phải phép xác định hạng số học tuyệt đối.

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;
import java.util.StringJoiner;

public class MultipleRightHandSidesLU {

    static final class LU {
        private final double[][] lu;
        private final int[] pivot;
        private final int swaps;
        private final double pivotThreshold;

        private LU(
            double[][] lu, int[] pivot, int swaps, double threshold
        ) {
            this.lu = lu;
            this.pivot = pivot;
            this.swaps = swaps;
            this.pivotThreshold = threshold;
        }

        static LU factor(double[][] matrix, double relTolerance) {
            Objects.requireNonNull(matrix, "matrix");
            if (!Double.isFinite(relTolerance) || relTolerance < 0) {
                throw new IllegalArgumentException(
                    "relative tolerance must be finite and nonnegative"
                );
            }

            int n = matrix.length;
            if (n == 0) {
                throw new IllegalArgumentException(
                    "matrix must be nonempty and square"
                );
            }

            double[][] a = new double[n][n];
            double infinityNorm = 0.0;

            for (int i = 0; i < n; i++) {
                if (matrix[i] == null || matrix[i].length != n) {
                    throw new IllegalArgumentException(
                        "matrix must be nonempty and square"
                    );
                }

                double rowSum = 0.0;
                for (int j = 0; j < n; j++) {
                    double value = matrix[i][j];
                    if (!Double.isFinite(value)) {
                        throw new IllegalArgumentException(
                            "matrix must contain finite numbers"
                        );
                    }
                    a[i][j] = value;
                    rowSum += Math.abs(value);
                }
                infinityNorm = Math.max(infinityNorm, rowSum);
            }

            if (!Double.isFinite(infinityNorm)) {
                throw new IllegalArgumentException(
                    "matrix infinity norm overflow"
                );
            }

            double threshold = relTolerance * infinityNorm;
            int[] pivot = new int[n];
            for (int i = 0; i < n; i++) {
                pivot[i] = i;
            }
            int swaps = 0;

            for (int k = 0; k < n; k++) {
                int best = k;
                for (int i = k + 1; i < n; i++) {
                    if (Math.abs(a[i][k]) > Math.abs(a[best][k])) {
                        best = i;
                    }
                }

                double absPivot = Math.abs(a[best][k]);
                if (!Double.isFinite(absPivot)
                        || !(absPivot > threshold)) {
                    throw new IllegalArgumentException(
                        "matrix is singular or near-singular "
                            + "for chosen tolerance"
                    );
                }

                if (best != k) {
                    double[] tempRow = a[k];
                    a[k] = a[best];
                    a[best] = tempRow;

                    int tempIndex = pivot[k];
                    pivot[k] = pivot[best];
                    pivot[best] = tempIndex;
                    swaps++;
                }

                for (int i = k + 1; i < n; i++) {
                    a[i][k] /= a[k][k];

                    for (int j = k + 1; j < n; j++) {
                        a[i][j] -= a[i][k] * a[k][j];
                        if (!Double.isFinite(a[i][j])) {
                            throw new ArithmeticException(
                                "non-finite elimination result"
                            );
                        }
                    }
                }
            }

            return new LU(a, pivot, swaps, threshold);
        }

        int[] rowPermutation() {
            return pivot.clone();
        }

        int swapCount() {
            return swaps;
        }

        double[][] lower() {
            int n = lu.length;
            double[][] out = new double[n][n];
            for (int i = 0; i < n; i++) {
                out[i][i] = 1.0;
                for (int j = 0; j < i; j++) {
                    out[i][j] = lu[i][j];
                }
            }
            return out;
        }

        double[][] upper() {
            int n = lu.length;
            double[][] out = new double[n][n];
            for (int i = 0; i < n; i++) {
                for (int j = i; j < n; j++) {
                    out[i][j] = lu[i][j];
                }
            }
            return out;
        }

        // Useful for illustration; can overflow/underflow for large n.
        double determinant() {
            double result = (swaps % 2 == 0) ? 1.0 : -1.0;
            for (int i = 0; i < lu.length; i++) {
                result *= lu[i][i];
            }
            return result;
        }

        // Solve A*x=b using the stored P*A=L*U.
        double[] solve(double[] rhs) {
            Objects.requireNonNull(rhs, "rhs");
            int n = lu.length;
            if (rhs.length != n) {
                throw new IllegalArgumentException(
                    "right-hand side length must equal matrix size"
                );
            }

            for (double value : rhs) {
                if (!Double.isFinite(value)) {
                    throw new IllegalArgumentException(
                        "right-hand side must contain finite numbers"
                    );
                }
            }

            // Forward substitution: L*y=P*b, diag(L)=1.
            double[] y = new double[n];
            for (int i = 0; i < n; i++) {
                double sum = rhs[pivot[i]];
                for (int j = 0; j < i; j++) {
                    sum -= lu[i][j] * y[j];
                }
                if (!Double.isFinite(sum)) {
                    throw new ArithmeticException(
                        "non-finite forward substitution result"
                    );
                }
                y[i] = sum;
            }

            // Backward substitution: U*x=y.
            double[] x = new double[n];
            for (int i = n - 1; i >= 0; i--) {
                double sum = y[i];
                for (int j = i + 1; j < n; j++) {
                    sum -= lu[i][j] * x[j];
                }
                x[i] = sum / lu[i][i];
                if (!Double.isFinite(x[i])) {
                    throw new ArithmeticException(
                        "non-finite backward substitution result"
                    );
                }
            }
            return x;
        }

        // B is n-by-k: each COLUMN is one RHS.
        double[][] solveColumns(double[][] b) {
            Objects.requireNonNull(b, "b");
            int n = lu.length;
            if (b.length != n || b[0] == null) {
                throw new IllegalArgumentException(
                    "right-hand-side matrix must have n rows"
                );
            }

            int k = b[0].length;
            for (int i = 0; i < n; i++) {
                if (b[i] == null || b[i].length != k) {
                    throw new IllegalArgumentException(
                        "right-hand-side matrix is ragged"
                    );
                }
            }

            double[][] result = new double[n][k];
            for (int col = 0; col < k; col++) {
                double[] rhs = new double[n];
                for (int i = 0; i < n; i++) {
                    rhs[i] = b[i][col];
                }

                double[] solution = solve(rhs);
                for (int i = 0; i < n; i++) {
                    result[i][col] = solution[i];
                }
            }
            return result;
        }
    }

    static String formatVector(double[] values) {
        StringJoiner join = new StringJoiner(", ", "[", "]");
        for (double value : values) {
            join.add(String.format(Locale.US, "%.6f", value));
        }
        return join.toString();
    }

    static String formatMatrix(double[][] matrix) {
        StringJoiner join = new StringJoiner(", ", "[", "]");
        for (double[] row : matrix) {
            join.add(formatVector(row));
        }
        return join.toString();
    }

    static double[] multiply(double[][] a, double[] x) {
        double[] out = new double[a.length];
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < x.length; j++) {
                out[i] += a[i][j] * x[j];
            }
        }
        return out;
    }

    static double maxResidual(
        double[][] a, double[] x, double[] b
    ) {
        double[] product = multiply(a, x);
        double norm = 0.0;
        for (int i = 0; i < b.length; i++) {
            norm = Math.max(norm, Math.abs(product[i] - b[i]));
        }
        return norm;
    }

    static void assertClose(double found, double expected) {
        if (!Double.isFinite(found)
                || Math.abs(found - expected) > 1e-8) {
            throw new AssertionError(
                "expected " + expected + " but found " + found
            );
        }
    }

    // Independent Gauss-Jordan oracle on small invertible systems.
    static double[] gaussJordanOracle(
        double[][] a, double[] b
    ) {
        int n = a.length;
        double[][] aug = new double[n][n + 1];

        for (int i = 0; i < n; i++) {
            System.arraycopy(a[i], 0, aug[i], 0, n);
            aug[i][n] = b[i];
        }

        for (int col = 0; col < n; col++) {
            int best = col;
            for (int row = col + 1; row < n; row++) {
                if (Math.abs(aug[row][col])
                        > Math.abs(aug[best][col])) {
                    best = row;
                }
            }

            if (Math.abs(aug[best][col]) < 1e-14) {
                throw new AssertionError(
                    "random oracle matrix unexpectedly singular"
                );
            }

            double[] temp = aug[col];
            aug[col] = aug[best];
            aug[best] = temp;

            double value = aug[col][col];
            for (int j = col; j <= n; j++) {
                aug[col][j] /= value;
            }

            for (int row = 0; row < n; row++) {
                if (row == col) {
                    continue;
                }
                double factor = aug[row][col];
                for (int j = col; j <= n; j++) {
                    aug[row][j] -= factor * aug[col][j];
                }
            }
        }

        double[] result = new double[n];
        for (int i = 0; i < n; i++) {
            result[i] = aug[i][n];
        }
        return result;
    }

    // Verify the identity P*A = L*U.
    static void verifyFactors(double[][] a, LU factor) {
        double[][] l = factor.lower();
        double[][] u = factor.upper();
        int[] p = factor.rowPermutation();

        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < a.length; j++) {
                double product = 0.0;
                for (int t = 0; t < a.length; t++) {
                    product += l[i][t] * u[t][j];
                }
                assertClose(product, a[p[i]][j]);
            }
        }
    }

    static void verifyRandomSystems() {
        Random random = new Random(2026L);
        int cases = 240;

        for (int test = 0; test < cases; test++) {
            int n = 1 + random.nextInt(6);
            double[][] a = new double[n][n];

            // Strictly diagonally dominant test matrices.
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    a[i][j] = random.nextInt(9) - 4;
                }
                a[i][i] += 10.0 * n;
            }

            LU factor = LU.factor(a, 1e-12);
            verifyFactors(a, factor);

            int columns = 1 + random.nextInt(4);
            double[][] b = new double[n][columns];
            double[][] expectedX = new double[n][columns];

            for (int col = 0; col < columns; col++) {
                double[] knownX = new double[n];
                for (int i = 0; i < n; i++) {
                    knownX[i] = random.nextInt(7) - 3;
                }

                double[] rhs = multiply(a, knownX);
                double[] solved = factor.solve(rhs);
                double[] independent = gaussJordanOracle(a, rhs);

                for (int i = 0; i < n; i++) {
                    b[i][col] = rhs[i];
                    expectedX[i][col] = knownX[i];
                    assertClose(solved[i], knownX[i]);
                    assertClose(solved[i], independent[i]);
                }
                assertClose(maxResidual(a, solved, rhs), 0.0);
            }

            double[][] batch = factor.solveColumns(b);
            for (int i = 0; i < n; i++) {
                for (int col = 0; col < columns; col++) {
                    assertClose(batch[i][col], expectedX[i][col]);
                }
            }
        }

        System.out.println(
            "Random known-solution and Gauss-Jordan checks: PASS ("
            + cases + " matrices)"
        );
    }

    public static void main(String[] args) {
        double[][] a = {
            {2, 1, 1},
            {4, -6, 0},
            {-2, 7, 2}
        };
        double[] b1 = {5, -2, 9};
        double[] b2 = {6, 14, -5};
        double[] b3 = {5, 24, -18};

        LU factor = LU.factor(a, 1e-12);
        System.out.println(
            "row permutation: "
            + Arrays.toString(factor.rowPermutation())
        );
        System.out.println("row swaps: " + factor.swapCount());
        System.out.println("L: " + formatMatrix(factor.lower()));
        System.out.println("U: " + formatMatrix(factor.upper()));
        System.out.println(
            "det(A): "
            + String.format(Locale.US, "%.6f", factor.determinant())
        );

        double[] x1 = factor.solve(b1);
        double[] x2 = factor.solve(b2);
        double[] x3 = factor.solve(b3);

        System.out.println("x1: " + formatVector(x1));
        System.out.println("x2: " + formatVector(x2));
        System.out.println("x3: " + formatVector(x3));

        // Each column of B is a separate right-hand side.
        double[][] bColumns = {
            {5, 6, 5},
            {-2, 14, 24},
            {9, -5, -18}
        };
        System.out.println(
            "X (solutions by column): "
            + formatMatrix(factor.solveColumns(bColumns))
        );
        System.out.println(
            "residual infinity norm for b1: "
            + String.format(
                Locale.US, "%.6f", maxResidual(a, x1, b1)
            )
        );

        double[][] spd = {
            {4, 1},
            {1, 3}
        };
        System.out.println(
            "SPD example x: "
            + formatVector(
                LU.factor(spd, 1e-12).solve(new double[] {1, 2})
            )
        );

        try {
            LU.factor(
                new double[][] {{1, 2}, {2, 4}}, 1e-12
            );
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "Singular matrix rejected: " + ex.getMessage()
            );
        }

        verifyFactors(a, factor);
        verifyRandomSystems();
    }
}
~~~

**Biên dịch và chạy** với JDK 17 trở lên, lưu thành tệp `MultipleRightHandSidesLU.java`:

~~~bash
javac -encoding UTF-8 MultipleRightHandSidesLU.java
java MultipleRightHandSidesLU
~~~

**Stdout dự kiến chính xác:**

~~~text
row permutation: [1, 0, 2]
row swaps: 1
L: [[1.000000, 0.000000, 0.000000], [0.500000, 1.000000, 0.000000], [-0.500000, 1.000000, 1.000000]]
U: [[4.000000, -6.000000, 0.000000], [0.000000, 4.000000, 1.000000], [0.000000, 0.000000, 1.000000]]
det(A): -16.000000
x1: [1.000000, 1.000000, 2.000000]
x2: [2.000000, -1.000000, 3.000000]
x3: [3.000000, -2.000000, 1.000000]
X (solutions by column): [[1.000000, 2.000000, 3.000000], [1.000000, -1.000000, -2.000000], [2.000000, 3.000000, 1.000000]]
residual infinity norm for b1: 0.000000
SPD example x: [0.090909, 0.636364]
Singular matrix rejected: matrix is singular or near-singular for chosen tolerance
Random known-solution and Gauss-Jordan checks: PASS (240 matrices)
~~~

### Phân tích thiết kế của chương trình

**Giữ A gốc:** phương thức `LU.factor` **sao chép sâu** các hàng của A vào `lu`, không sửa A đầu vào. Điều này cho phép kiểm \(Ax-b\) với ma trận thật, tránh nhầm A sau phân rã với A ban đầu.

**Dùng một mảng lu:** phần dưới đường chéo lưu hệ số L, phần từ đường chéo trở lên lưu U. Hai ma trận L/U được khôi phục riêng chỉ để minh họa và kiểm thử; giải nhiều hệ không cần tạo lại chúng.

**Hoán vị hàng:** `pivot[i]` là chỉ số hàng gốc đang ở vị trí i sau các lần swap. Trong solve, lấy `rhs[pivot[i]]` để tạo \(Pb\).

**Tái sử dụng:** một đối tượng `LU` được tạo bằng `factor(a,1e-12)` và dùng liên tiếp cho b1,b2,b3, cũng như giải cả B bằng `solveColumns`.

**Hệ nhiều vế phải:** `solveColumns` nhận B dạng n hàng × k cột, lấy từng **cột** làm một vector b. Kết quả X cũng có n hàng × k cột. Đầu vào B không bị ghi đè.

**Chuẩn kiểm tra số học:** trước phân rã, mã từ chối NaN, Infinity và kích thước không vuông. Trong quá trình, nếu một phép loại trừ hoặc thế tạo số không hữu hạn, mã báo lỗi thay vì âm thầm in kết quả không đáng tin.

**Ngưỡng pivot:** mã tính `threshold = relTolerance * ||A||∞`; nếu pivot tối đa còn lại không lớn hơn ngưỡng, nó từ chối. Đây là **chính sách** để phát hiện trường hợp kỳ dị/gần kỳ dị; ma trận vẫn có thể khả nghịch trong toán học nhưng bị từ chối nếu rất kém điều kiện hoặc thang đo bất lợi.

**Residual:** `maxResidual(a,x1,b1)` lấy chuẩn vô cùng của \(Ax-b\) đối với A gốc. Ví dụ số nguyên ở trên có residual 0 trong số học double của trường hợp cụ thể; điều này **không có nghĩa mọi nghiệm của mọi ma trận đều chính xác tuyệt đối**.

**Oracle độc lập:** 240 ma trận ngẫu nhiên được xây **chéo trội nghiêm ngặt** để bảo đảm có nghiệm duy nhất. Chương trình chọn các vector nghiệm đã biết, tính b=A·x, giải LU rồi so nghiệm, đối chiếu thêm với **Gauss–Jordan** và kiểm \(PA\approx LU\).

## 12. Độ phức tạp chi tiết

Cho A là ma trận đặc n×n và k cột của B.

**Phân rã LU có pivot một phần:**

- Ở bước k, tìm pivot tối đa trong O(n−k).
- Cập nhật phần ma trận còn lại kích thước xấp xỉ (n−k−1)².
- Tổng số phép toán theo bậc là O(n³).

**Giải một vế phải:**

- Hoán vị b: O(n).
- Thế tiến qua L: O(n²).
- Thế ngược qua U: O(n²).

Tổng một RHS:

\[
\boxed{O(n^2)}.
\]

**Giải k vế phải:**

\[
\boxed{O(n^3+k n^2)}.
\]

**Bộ nhớ:**

- Lưu ma trận lu đặc: O(n²).
- Lưu pivot: O(n).
- Lưu một b,y,x: O(n).
- Nếu giữ toàn bộ B và X kích thước n×k: thêm O(nk).

Trong mã ví dụ:

\[
\boxed{\text{Bộ nhớ chứa kết quả hàng loạt }O(n^2+nk).}
\]

Nếu vế phải đến lần lượt và không cần giữ mọi nghiệm, có thể đọc từng b, giải rồi xuất kết quả, chỉ cần O(n²+n) bộ nhớ ngoài dữ liệu input đang xử lý.

### Thời gian thực tế của thư viện tối ưu

Dù `solveColumns` gọi `solve` k lần là đúng và dễ học, thư viện số học lớn thường giải cả ma trận RHS bằng phép nhân theo khối, tận dụng **BLAS** và kiến trúc CPU/GPU. Bậc vẫn O(kn²), nhưng số lần truy cập bộ nhớ và tốc độ tính toán có thể khác rất nhiều.

## 13. Pivoting giúp gì, và không giúp gì?

Một ma trận khả nghịch có thể có pivot bằng 0 nếu không đổi hàng. Partial pivoting giúp chọn pivot có trị tuyệt đối lớn nhất trong cột còn lại, tránh chia cho 0 khi có thể và thường giảm nguy cơ hệ số nhân quá lớn.

Với pivot lớn nhất trong cột, các hệ số nhân dưới pivot tại bước đó thường có:

\[
|m_{ik}|\le1
\]

trong số học chính xác. Đây là một lợi ích quan trọng cho tính ổn định của khử Gauss.

Nhưng:

- Partial pivoting **không biến mọi ma trận thành bài toán điều kiện tốt**.
- Không có bảo đảm nghiệm có nhiều chữ số chính xác nếu A **gần suy biến**.
- Một số ma trận đặc biệt có **pivot growth** lớn dù đã pivot một phần.
- Phép tính double vẫn có sai số.
- Chọn pivot theo giá trị lớn nhất trong cột không giống **complete pivoting** (chọn tối đa trên cả phần ma trận còn lại và có thể đổi cả cột).

### Không trộn khái niệm kỳ dị và kém điều kiện

**Suy biến** (*singular*): A không có nghịch đảo, có thể không có nghiệm hoặc vô số nghiệm tùy b.

**Gần suy biến/kém điều kiện** (*ill-conditioned*): A có thể vẫn khả nghịch, nhưng nghiệm **rất nhạy** với những nhiễu rất nhỏ trong A hoặc b.

Ví dụ:

\[
A_\varepsilon=
\begin{bmatrix}
1&1\\
1&1+\varepsilon
\end{bmatrix}
\]

có định thức \(\varepsilon\). Khi \(\varepsilon\ne0\), A khả nghịch trong toán học; nhưng với \(\varepsilon\) rất nhỏ, hệ có thể rất kém điều kiện và một ngưỡng pivot thực dụng có thể từ chối.

Đừng ghi trong báo cáo “ma trận chắc chắn suy biến” chỉ vì một pivot nhỏ hơn ngưỡng tương đối. Phải nói chính xác: **“suy biến hoặc gần suy biến theo ngưỡng đã chọn.”**

## 14. Ngưỡng pivot và các lựa chọn chuẩn hóa

Mã dùng:

\[
\boxed{\tau=\text{relTolerance}\cdot\|A\|_\infty}
\]

với:

\[
\|A\|_\infty
=\max_i\sum_j|A_{ij}|.
\]

Nếu pivot tốt nhất ở một bước không lớn hơn τ, mã từ chối.

Với `relTolerance=1e-12`, đây là một quy tắc **minh họa dễ hiểu**. Không có một giá trị tolerance duy nhất tối ưu cho mọi bài toán.

### Vì sao scale của A quan trọng?

Xét hai ma trận có hàng/cột có thang số rất khác nhau. Một pivot nhỏ so với \(\|A\|_\infty\) không nhất thiết đồng nghĩa **toàn hệ** không thể giải; ngược lại, pivot nhìn có vẻ lớn cũng không bảo đảm bài toán điều kiện tốt.

Vì vậy những thư viện chuyên dụng có thể dùng:

- **Scaled partial pivoting**: cân nhắc trị tuyệt đối pivot so với scale của hàng.
- **Equilibration**: chuẩn hóa hàng/cột trước khi giải.
- Kiểm tra **rank** hay **condition estimation**.
- **QR/SVD** nếu cần xử lý các hệ gần suy biến hoặc thiếu hạng một cách đáng tin hơn.

Bài học dùng pivot tối đa theo cột để giải thích LU chuẩn, không khẳng định ngưỡng τ là công thức phân loại chính xác cho mọi ma trận.

### Khi nào tolerance=0?

Ngưỡng 0 chỉ từ chối pivot bằng đúng 0 hoặc không hữu hạn. Nó **không bảo đảm ổn định số**: một pivot cực nhỏ có thể gây kết quả rất nhiễu. Mặt khác, một tolerance dương quá lớn có thể từ chối những ma trận vẫn khả nghịch và giải được.

Khi triển khai sản phẩm, cần lựa chọn chính sách theo thang dữ liệu, độ chính xác cần thiết và bài toán cụ thể.

## 15. Residual và sai số nghiệm là hai điều khác nhau

Sau khi tìm nghiệm gần đúng \(\hat x\), ta kiểm tra **residual**:

\[
\boxed{r=A\hat x-b}.
\]

Chuẩn vô cùng:

\[
\boxed{\|r\|_\infty=\max_i|r_i|}.
\]

Nếu residual nhỏ, \(\hat x\) gần như thỏa phương trình đầu vào. Nhưng **không suy ra \(\hat x\) nhất thiết gần nghiệm thật theo mọi chuẩn**, đặc biệt khi A kém điều kiện.

### Backward error tương đối

Một thước đo phù hợp hơn khi scale dữ liệu thay đổi là:

\[
\boxed{
\eta=
\frac{\|A\hat x-b\|_\infty}
{\|A\|_\infty\|\hat x\|_\infty+\|b\|_\infty}.
}
\]

Khi mẫu số bằng 0, cần định nghĩa xử lý riêng, chẳng hạn nếu tử cũng 0 thì đặt η=0 theo quy ước.

Đại lượng η cho biết nghiệm gần đúng cần một nhiễu dữ liệu **tương đối nhỏ đến đâu** để thỏa đúng một hệ lân cận.

### Điều kiện ma trận

Số điều kiện trong một chuẩn tương thích:

\[
\kappa(A)=\|A\|\cdot\|A^{-1}\|.
\]

Khi \(\kappa(A)\) rất lớn, một backward error nhỏ vẫn có thể đi kèm **forward error** đáng kể trong nghiệm. Đó là lý do một residual gần 0 **không đủ** để khẳng định nghiệm có độ chính xác cao.

### Kiểm nhiều nghiệm

Với \(AX=B\), có thể kiểm:

\[
R=AX-B
\]

và chuẩn lớn nhất của R, hoặc kiểm từng cột \(A x^{(j)}-b^{(j)}\). Đặc biệt, phải dùng **ma trận A gốc**, không phải mảng lu đã bị khử; hai ma trận chứa thông tin khác nhau.

## 16. Vì sao thường không nên tính A⁻¹ rồi nhân b?

Theo lý thuyết:

\[
x=A^{-1}b
\]

khi A khả nghịch. Nhưng để **giải hệ số học**, việc tạo tường minh ma trận nghịch đảo thường **không cần thiết**.

Nhược điểm của cách lấy nghịch đảo trước:

- Vẫn phải dùng một phương pháp số học để tính nghịch đảo, thường không rẻ hơn phân rã.
- Phải lưu toàn bộ \(A^{-1}\) nếu không cần nó cho mục đích khác.
- Nhân nghịch đảo đã tính xấp xỉ với b có thể thêm sai số và không nhất thiết là cách ổn định nhất để solve.
- Dễ dẫn tới hiểu nhầm rằng có thể giải hệ suy biến bằng cách “nghịch đảo gần đúng” mà không phân tích tính điều kiện.

**Quy tắc thực hành:** khi cần nghiệm của Ax=b, ưu tiên gọi **solver dựa trên factorization**, không tạo \(A^{-1}\) chỉ để nhân b. Nếu thật sự cần nghịch đảo cho một ứng dụng đã được phân tích, đó là một đầu ra khác và phải đánh giá chi phí/độ chính xác riêng.

## 17. Những phân rã khác cần biết

LU với pivot một phần hợp lý cho nhiều ma trận vuông **đặc, khả nghịch**. Nhưng không phải mọi hệ đều nên dùng LU.

### A. Cholesky cho A đối xứng xác định dương

Nếu A thỏa:

\[
A=A^T,\qquad x^T A x>0\ \forall x\ne0,
\]

thì A **đối xứng xác định dương** (*symmetric positive definite, SPD*) và có phân rã Cholesky:

\[
\boxed{A=LL^T}.
\]

Ta giải:

\[
Ly=b,\qquad L^T x=y.
\]

Ưu điểm: khai thác tính đối xứng, thường cần ít phép toán/bộ nhớ hơn LU tổng quát, với điều kiện dữ liệu thực sự SPD.

Ví dụ:

\[
A=\begin{bmatrix}4&1\\1&3\end{bmatrix},\quad
b=\begin{bmatrix}1\\2\end{bmatrix}.
\]

Nghiệm:

\[
x=\begin{bmatrix}1/11\\7/11\end{bmatrix}
\approx\begin{bmatrix}0.090909\\0.636364\end{bmatrix}.
\]

Mã Java vẫn giải ví dụ này bằng LU để tái sử dụng một API; nếu biết trước A là SPD, **Cholesky** thường thích hợp hơn.

### B. QR cho bình phương tối thiểu và ma trận chữ nhật

Với A hình chữ nhật \(m\times n\), thường có bài toán:

\[
\min_x\|Ax-b\|_2.
\]

Phân rã QR:

\[
\boxed{A=QR}
\]

với Q có các cột trực chuẩn và R tam giác trên, thường được dùng để giải **least squares**. QR (đặc biệt dạng Householder) có ưu điểm ổn định hơn so với tự lập **normal equations** \(A^TAx=A^Tb\), vốn có thể làm số điều kiện bị bình phương.

Nếu nhiều vector b cùng chia sẻ A, có thể **tái sử dụng Q/R** tương tự LU, nhưng bài toán và công thức giải khác.

### C. SVD cho hạng thiếu và bài toán rất kém điều kiện

Phân rã giá trị kỳ dị:

\[
\boxed{A=U\Sigma V^T}
\]

giúp phân tích các giá trị kỳ dị, hạng và độ nhạy. SVD hữu ích cho **hệ thiếu hạng**, nghiệm chuẩn nhỏ nhất, pseudoinverse và các bài toán cần regularization.

SVD thường tốn chi phí hơn LU/Cholesky/QR, nhưng có nhiều thông tin hơn về cấu trúc hạng và tính điều kiện.

### D. Ma trận thưa: sparse LU/Cholesky

Nếu A rất lớn nhưng phần lớn phần tử bằng 0, lưu `double[n][n]` sẽ lãng phí O(n²) bộ nhớ. Các thư viện **sparse direct solvers** dùng lưu trữ thưa, sắp thứ tự để giảm fill-in, và tách **symbolic factorization** khỏi **numeric factorization**.

Với nhiều hệ có **cùng mẫu cấu trúc thưa** nhưng hệ số số học thay đổi, có thể tái sử dụng một phần kết quả symbolic; tuy nhiên thường **không thể tái sử dụng nguyên các hệ số L/U số học** khi giá trị của A đổi.

## 18. Khi nào có thể tái sử dụng factorization?

### Trường hợp được

- **A không đổi**, các RHS b khác nhau.
- Một RHS được cập nhật qua nhiều bước, nhưng **hệ số A vẫn giữ nguyên**.
- Cần giải nhiều cột trong \(AX=B\) với cùng A.
- Một số tác vụ cần dùng các tính chất của LU như định thức hoặc solve bổ sung mà không phân rã lại.

### Trường hợp cần xem lại

- **A đổi dù chỉ một phần tử:** LU cũ nói chung không còn là factorization của A mới.
- **A bị hoán vị hàng/cột theo cách mới:** phải quản lý những phép biến đổi và vế phải tương ứng.
- **A^T x=b:** có thể tận dụng các yếu tố L/U với thuật toán giải hệ chuyển vị riêng, nhưng **không** được gọi `solve(b)` thông thường rồi coi là solve của A^T.
- **A thay đổi hạng thấp:** có kỹ thuật cập nhật hệ và công thức Sherman–Morrison/Woodbury dưới điều kiện thích hợp, nhưng không tự động đúng, có thể kém ổn định và cần kiểm tra tính khả nghịch.
- **A đổi cấu trúc sparsity:** thậm chí symbolic factorization cũng có thể không còn dùng được.

**Nguyên tắc:** factorization là kết quả gắn với **ma trận hệ số tại thời điểm phân rã**. Chỉ những phép solve dùng đúng ma trận ấy mới được hưởng lợi ích tái sử dụng trực tiếp.

## 19. Trường hợp suy biến, không duy nhất và least squares

Với A vuông **suy biến**:

- Có thể không tồn tại x nào thỏa Ax=b.
- Hoặc có vô số nghiệm nếu b thuộc không gian cột phù hợp.
- Không thể nói “nghiệm duy nhất” chỉ vì số hàng bằng số cột.

LU với pivot **không được phép chia cho pivot bằng 0**. Mã minh họa sẽ từ chối khi pivot không vượt ngưỡng, rồi để phía gọi lựa chọn cách xử lý thích hợp.

Nếu muốn tìm nghiệm theo nghĩa **bình phương tối thiểu** hoặc nghiệm có chuẩn nhỏ nhất, có thể dùng QR/SVD và xác định rõ tiêu chí tối ưu. Không nên tùy tiện thay pivot 0 bằng epsilon rồi tuyên bố giải đúng hệ gốc.

### Một ví dụ suy biến

\[
A=\begin{bmatrix}1&2\\2&4\end{bmatrix}.
\]

Hàng thứ hai gấp đôi hàng đầu, nên hạng chỉ là 1; định thức bằng 0. Với b=[3,6], có vô số nghiệm; với b=[3,7], không có nghiệm đúng.

Mã LU từ chối cả hai khi phân rã A, vì mục tiêu API là **giải duy nhất cho A vuông khả nghịch**, không phải xử lý các bài toán thiếu hạng.

## 20. Những lỗi thường gặp

1. **Khử Gauss lại từ đầu cho mỗi b** dù A không đổi, lãng phí O(kn³).
2. **Phân rã không pivot cho ma trận có pivot bằng 0**, chia cho 0 mặc dù A khả nghịch.
3. **Nhầm PA=LU thành A=LU**, không kiểm P.
4. **Quên hoán vị b**, giải \(LUx=b\) thay vì \(LUx=Pb\).
5. **Nhầm pivot[i] là vị trí mới của hàng gốc i**, thay vì hàng gốc nằm ở hàng mới i trong API.
6. **Chỉ đổi phần U của hai hàng khi pivot ở bước sau**, không đổi phần L đã lưu trước đó.
7. **Để đường chéo L không phải 1 nhưng vẫn bỏ phép chia khi forward substitution**.
8. **Thế tiến từ dưới lên**, trái thứ tự phụ thuộc của L.
9. **Thế ngược từ trên xuống**, trái thứ tự phụ thuộc của U.
10. **Chia cho hệ số sai \(U_{ii}\)** hoặc nhầm chỗ lưu L/U trong mảng lu.
11. **Coi mỗi hàng B là một RHS trong khi API yêu cầu mỗi cột**, trả X sai chiều.
12. **Thay đổi A sau factor nhưng vẫn dùng LU cũ**, giải sai hệ mới.
13. **Thay đổi phân rã trong mỗi lần solve** mà không cần, khiến lần solve sau dùng dữ liệu đã hỏng.
14. **Dùng phép toán số thực mà không kiểm NaN/Infinity**, sai lan sang mọi nghiệm.
15. **Xem pivot nhỏ là bằng 0 tuyệt đối**, từ chối thiếu giải thích một ma trận vẫn khả nghịch.
16. **Xem pivot khác 0 là bảo đảm nghiệm chính xác**, bỏ qua tính điều kiện.
17. **Chọn tolerance cố định theo đơn vị tuyệt đối** cho mọi thang đo mà không phân tích dữ liệu.
18. **Chỉ in nghiệm mà không kiểm \(Ax-b\)**, khó phát hiện hoán vị sai.
19. **Kiểm residual dựa trên lu thay vì A gốc**, so sai hệ phương trình.
20. **Tin residual nhỏ chứng minh forward error nhỏ**, bỏ qua \(\kappa(A)\).
21. **Tính nghịch đảo A chỉ để nhân b**, dù solver LU cho nghiệm trực tiếp.
22. **Dùng LU đặc cho một ma trận thưa cực lớn** mà không phân tích bộ nhớ.
23. **Dùng Cholesky cho ma trận không SPD**, có thể gặp căn của giá trị không dương.
24. **Dùng normal equations cho bài least squares kém điều kiện mà không hiểu rủi ro**, có thể làm trầm trọng sai số.
25. **Coi LU là cách giải duy nhất cho ma trận hạng thiếu**, thay vì xác định nghiệm tối ưu/khả thi.
26. **Coi định thức rất nhỏ là một bộ kiểm điều kiện đầy đủ**, trong khi scale và condition number phức tạp hơn.
27. **Không thử ma trận cần đổi hàng**, code pivot giả đúng trên ma trận chéo trội nhưng sai ở zero pivot.
28. **Không thử RHS với nghiệm âm**, dễ che lỗi dấu trong thế tam giác.
29. **Không thử nhiều RHS cùng lúc**, lỗi chuyển hàng/cột không được phát hiện.
30. **Không kiểm \(PA=LU\)**, một lỗi hoán vị có thể tồn tại dù vài nghiệm tình cờ đúng.
31. **Dùng float/double cho dữ liệu số nguyên lớn mà không xem xét độ chính xác**, phần tử có thể mất chữ số có nghĩa.
32. **Quên rằng O(n³) là cận cho ma trận đặc**, không phải cho mọi ma trận thưa/đặc biệt.
33. **Tái sử dụng LU cho A^T mà không đổi công thức solve**, giải sai hệ chuyển vị.
34. **Không phân biệt hệ có nghiệm duy nhất với hệ vô số nghiệm/không nghiệm**, gọi sai kết quả gần đúng là nghiệm chính xác.
35. **Không lưu và áp dụng cùng một thứ tự pivot cho mọi vế phải**, làm các kết quả không nhất quán.

## 21. Chiến lược kiểm thử độc lập

**Kiểm thử đúng công thức PA=LU.** Sau phân rã, dựng lại L/U và mảng hoán vị, kiểm:

\[
\|PA-LU\|_\infty
\]

nhỏ so với thang ma trận. Đối với test số nhỏ, kiểm từng phần tử trong một ngưỡng sai số thích hợp.

**Kiểm với nghiệm đã biết.** Sinh trước một vector \(x^\star\), tính \(b=Ax^\star\), rồi gọi solver. Nếu A điều kiện tốt, kết quả phải gần \(x^\star\).

**Kiểm nhiều cột.** Sinh k nghiệm \(x^{(1)},...,x^{(k)}\), ghép B từ \(A x^{(j)}\), rồi giải hàng loạt. Kiểm từng cột X thu được bằng nghiệm đã sinh.

**Kiểm độc lập bằng Gauss–Jordan.** Trên hệ nhỏ khả nghịch, dựng ma trận mở rộng \([A|b]\), chuẩn hóa hàng trụ và khử cả phía trên lẫn phía dưới để được nghiệm. Cách này có luồng thao tác khác với LU+thế tam giác, giúp phát hiện lỗi triển khai.

**Kiểm residual.** Tính \(A\hat x-b\) bằng A đầu vào. Khi có thang dữ liệu khác nhau, cân nhắc cả residual tương đối.

**Kiểm trường hợp xấu:**

- Ma trận 1×1.
- Ma trận đơn vị.
- Ma trận đường chéo có hệ số khác nhau.
- Ma trận phải đổi hàng ở pivot đầu hoặc pivot sau.
- Ma trận có hàng trùng hoặc hàng tỉ lệ.
- Ma trận gần suy biến nhưng vẫn khả nghịch trong toán học.
- Ma trận có giá trị âm, 0 và RHS chứa giá trị âm.
- B có k=1, k>1 hoặc k=0 theo hợp đồng API.
- RHS sai chiều hoặc chứa NaN/Infinity.
- Ma trận có hàng bị thiếu phần tử.
- Scale số liệu lớn/nhỏ, quan sát tolerance và residual.

**Lưu ý về kiểm sai số:** ngưỡng tuyệt đối \(10^{-8}\) có thể dùng cho những bộ test nhỏ, scale vừa phải như trong Java. Với dữ liệu rất lớn hoặc rất nhỏ, cần điều chỉnh theo thang và độ chính xác của bài toán, không giữ epsilon cố định một cách máy móc.

## 22. Câu hỏi tự luyện

**Bài 1.** Khi nào tái sử dụng LU mang lại lợi ích rõ ràng?

*Đáp án:* Khi **A giữ nguyên**, nhiều vế phải b khác nhau cần giải.

**Bài 2.** Viết phân rã LU có pivot một phần.

*Đáp án:* \(\boxed{PA=LU}\).

**Bài 3.** Trong phân rã trên, L và U là ma trận gì?

*Đáp án:* L **tam giác dưới** với đường chéo 1, U **tam giác trên**.

**Bài 4.** Muốn giải Ax=b từ PA=LU, giải hai hệ nào?

*Đáp án:* \(Ly=Pb\), sau đó \(Ux=y\).

**Bài 5.** Vì sao phải hoán vị b?

*Đáp án:* Vì phép đổi hàng đã tạo PA; phương trình tương đương là \(PAx=Pb\).

**Bài 6.** Mỗi lần solve dùng lại LU tốn bao nhiêu?

*Đáp án:* **O(n²)** cho một RHS ma trận đặc.

**Bài 7.** Với k RHS, tổng thời gian gồm phân rã và giải là bao nhiêu?

*Đáp án:* **O(n³+kn²)**.

**Bài 8.** Trong ví dụ A của bài, hàng nào được chọn làm pivot đầu?

*Đáp án:* **Hàng chỉ số 1**, vì trị tuyệt đối đầu cột bằng 4 lớn nhất.

**Bài 9.** Mảng hoán vị của ví dụ là gì?

*Đáp án:* **[1,0,2]**.

**Bài 10.** Với b1=[5,-2,9], giá trị Pb1 là gì?

*Đáp án:* **[-2,5,9]**.

**Bài 11.** Giải Ly=Pb1 cho ví dụ cho y bằng bao nhiêu?

*Đáp án:* **[-2,6,2]**.

**Bài 12.** Nghiệm cuối của hệ thứ nhất là gì?

*Đáp án:* **x=[1,1,2]**.

**Bài 13.** Vì sao phải lưu các hệ số khử m_ik?

*Đáp án:* Chúng tạo phần dưới đường chéo L, dùng lại trong forward substitution.

**Bài 14.** Khi đổi hai hàng ở bước k>0, có thể chỉ đổi các cột ≥k không?

*Đáp án:* Không với biểu diễn lu gộp trong bài; phải đổi cả những hệ số L đã ghi trước đó để giữ \(PA=LU\).

**Bài 15.** Nếu A là đối xứng xác định dương, có phân rã thường phù hợp hơn LU nào?

*Đáp án:* **Cholesky**, \(A=LL^T\).

**Bài 16.** Nếu A là ma trận chữ nhật trong bài least squares, nên cân nhắc gì?

*Đáp án:* **QR**, hoặc SVD khi cần xử lý hạng/điều kiện phức tạp.

**Bài 17.** A=[[1,2],[2,4]] có nghiệm duy nhất cho mọi b không?

*Đáp án:* Không. A suy biến nên có b vô nghiệm và b vô số nghiệm.

**Bài 18.** Pivot nhỏ hơn ngưỡng có chứng minh A đúng bằng singular không?

*Đáp án:* Không. A có thể **gần suy biến** hoặc scale không thuận lợi; đó là quyết định theo ngưỡng số học.

**Bài 19.** Nếu residual nhỏ, nghiệm có chắc gần nghiệm thật không?

*Đáp án:* Không nhất thiết; cần xét **condition number** của A.

**Bài 20.** Có nên tính nghịch đảo A rồi nhân từng b cho bài này không?

*Đáp án:* Thường **không cần**; giải từ LU ổn định và hiệu quả thực dụng hơn.

**Bài 21.** Trong B kích thước n×k, mỗi vế phải nằm ở đâu?

*Đáp án:* **Một cột** của B, theo API của bài.

**Bài 22.** Sau khi A đổi một phần tử, có thể tự động dùng lại LU cũ không?

*Đáp án:* **Không**; cần factor mới hoặc phương pháp cập nhật được chứng minh phù hợp.

**Bài 23.** Vì sao không nên so kết quả double bằng `==` trong kiểm thử số học?

*Đáp án:* Sai số làm tròn có thể tạo độ lệch nhỏ; nên kiểm theo ngưỡng có thang phù hợp.

**Bài 24.** Với nghiệm đã biết x*, xây b thế nào để test solver?

*Đáp án:* Tính **b=A·x***, giải rồi so nghiệm nhận được với x*.

**Bài 25.** Nếu muốn giải A^T x=b từ LU của A, có dùng nguyên `solve` hiện tại không?

*Đáp án:* **Không**. Cần quy trình giải hệ chuyển vị tương ứng với U^T, L^T và hoán vị.

**Tổng kết:** Khi nhiều hệ tuyến tính dùng chung một ma trận hệ số **A**, ta nên **phân rã A một lần** rồi tái sử dụng các yếu tố để giải nhanh mỗi vế phải. Với **LU có pivot một phần**, phân rã là \(PA=LU\), từng nghiệm được tính bằng **\(Ly=Pb\)** rồi **\(Ux=y\)**. Chi phí cho ma trận đặc là **O(n³)** để factor và **O(n²)** mỗi RHS, tức **O(n³+kn²)** cho k hệ. Mã Java 17 minh họa hoán vị hàng, lưu L/U trong một mảng, giải nhiều cột của B, kiểm \(PA=LU\) và residual, kiểm chéo bằng Gauss–Jordan. Khi A gần suy biến, dư lượng nhỏ chưa đủ bảo đảm nghiệm chính xác; cần xem **tính điều kiện**, chọn ngưỡng/chuẩn hóa phù hợp hoặc dùng **Cholesky, QR, SVD** tùy cấu trúc hệ.
