# Kiểm thử hình học bằng đối xứng và phép biến đổi bảo toàn

**Chủ đề:** Computer Science Algorithms · Hình học tính toán

## 1. Tư duy kiểm thử biến hình

Trong hình học tính toán, một thuật toán có thể chạy đúng với ví dụ dễ nhưng sai ở những trường hợp thẳng hàng, chạm đầu mút, điểm trùng, tràn số hoặc đảo dấu định hướng. Để kiểm thử, không phải lúc nào ta cũng tính được kết quả đúng cho hàng nghìn đầu vào lớn. **Metamorphic testing** (kiểm thử biến hình) sử dụng **quan hệ toán học đã chứng minh** giữa kết quả của một đầu vào và kết quả của đầu vào được biến đổi.

Ví dụ, giao hai đoạn thẳng đóng là giao của hai tập điểm. Vì phép giao có tính giao hoán:

\[
G(AB,CD)=G(CD,AB).
\]

Nếu thuật toán trả NONE cho một thứ tự và POINT cho thứ tự còn lại, nó chắc chắn sai, dù ta chưa biết tọa độ giao điểm thực tế.

Một quan hệ khác: với phép affine **khả nghịch** T, nghĩa là phần ma trận có định thức khác 0:

\[
\boxed{G(T(AB),T(CD))=G(AB,CD)}
\]

khi G chỉ là loại hình học **NONE, POINT hoặc OVERLAP**. T là một-một và bảo toàn đoạn nên không thể biến giao rỗng thành có giao, hoặc ép một đoạn chồng không suy biến thành một điểm.

Tuy vậy, không được kết luận mọi kết quả đều giữ nguyên:
- **Tịnh tiến, quay, phản xạ** giữ khoảng cách Euclid.
- **Phản xạ** đảo dấu orientation và diện tích có hướng.
- **Phóng đại đều hệ số s** làm độ dài tăng |s|, bình phương khoảng cách và diện tích không âm tăng s² trong không gian 2D.
- **Shear/xiên** có thể giữ diện tích (khi định thức bằng 1) nhưng **không giữ khoảng cách hoặc góc**.

Một bộ kiểm thử tốt gồm **bất biến**, **quy luật biến đổi**, **phản ví dụ cho tính chất không đúng**, và **oracle độc lập** khi có thể.

## 2. Những phép thử đổi thứ tự đầu vào

### 2.1. Hai đoạn và đầu mút

Đoạn thẳng đóng AB chứa các điểm \(A+t(B-A)\) với 0≤t≤1, nên AB và BA biểu diễn cùng một đoạn. Từ đó:

\[
G(AB,CD)=G(BA,CD)=G(AB,DC)=G(CD,AB).
\]

Đây là kiểm thử **đối xứng biểu diễn**, không cần di chuyển điểm trên mặt phẳng.

Một hàm phân loại giao trả một trong ba giá trị:
- **NONE:** không có điểm chung.
- **POINT:** đúng một điểm chung, kể cả tiếp xúc ở đầu mút.
- **OVERLAP:** hai đoạn đồng tuyến cùng chia sẻ một đoạn có chiều dài dương.

Kiểm thử đổi thứ tự phải đúng cho cả giao chữ X, tiếp xúc chữ T, chạm đầu mút, chồng lấn, hai đoạn song song rời nhau và đoạn suy biến thành một điểm.

### 2.2. Đổi thứ tự trong phép định hướng

Với ba điểm A,B,C, giá trị orientation là:

\[
\operatorname{orient}(A,B,C)
=(B_x-A_x)(C_y-A_y)
-(B_y-A_y)(C_x-A_x).
\]

Đổi B và C làm đổi dấu:

\[
\boxed{\operatorname{orient}(A,C,B)
=-\operatorname{orient}(A,B,C)}.
\]

Đảo hướng đoạn AB làm giá trị định hướng đổi dấu, dù **tập điểm của đoạn** không đổi. Vì vậy không được áp đặt cùng một quy luật giữ nguyên cho mọi hàm.

Ví dụ A=(0,0), B=(4,0), C=(1,3):

~~~text
orient(A,B,C) = 12
orient(A,C,B) = -12
~~~

### 2.3. Bao lồi và hoán vị đầu vào

Bao lồi conv(P) là tập lồi nhỏ nhất chứa mọi điểm P. Nó không phụ thuộc thứ tự nạp điểm, cũng không thay đổi nếu chèn thêm một bản sao của điểm sẵn có.

Nhưng **danh sách đỉnh trả về** có thể khác thứ tự xoay vòng, khác đỉnh bắt đầu hoặc đảo hướng dưới phản xạ. Cần chốt hợp đồng:
- Trong bài, convexHull **loại điểm trùng** và **loại điểm thẳng hàng nằm trong cạnh**, chỉ giữ các điểm cực biên.
- Khi kiểm thử phép biến đổi, so **tập đỉnh**, không so từng phần tử trong hai danh sách theo vị trí.
- Khi kiểm tra định dạng output của một API yêu cầu thứ tự CCW hoặc đỉnh bắt đầu cụ thể, kiểm tra thêm quy tắc ấy riêng.

## 3. Phép affine 2D và định thức

Phép affine T có dạng:

\[
T(p)=Mp+t,\qquad
M=\begin{pmatrix}a&b\\c&d\end{pmatrix},
\quad t=(t_x,t_y).
\]

Tọa độ:

\[
x'=ax+by+t_x,\qquad y'=cx+dy+t_y.
\]

**Định thức**:

\[
\boxed{\det(M)=ad-bc}.
\]

Với det(M)≠0, phần tuyến tính và toàn phép affine đều khả nghịch. Một phép affine khả nghịch là một song ánh của mặt phẳng, bảo toàn thẳng hàng, quan hệ điểm nằm giữa hai điểm và cấu trúc giao của đoạn thẳng.

Các biến đổi dùng trong chương trình:

| Phép | Ma trận M | t | det | Thuộc tính |
|---|---|---|---:|---|
| Tịnh tiến | [[1,0],[0,1]] | (10,−7) | 1 | Giữ khoảng cách/hướng |
| Quay 90° | [[0,−1],[1,0]] | (0,0) | 1 | Giữ khoảng cách/hướng |
| Phản xạ qua Ox | [[1,0],[0,−1]] | (0,0) | −1 | Giữ khoảng cách, đảo hướng |
| Phóng đại đều ×2 | [[2,0],[0,2]] | (0,0) | 4 | Khoảng cách ×2, diện tích ×4 |
| Shear theo x | [[1,1],[0,1]] | (0,0) | 1 | Giữ diện tích có hướng, đổi khoảng cách |

### 3.1. Định thức bằng 0 là ranh giới quan trọng

Nếu det(M)=0, phép biến đổi không còn một-một. Ví dụ phép chiếu S(x,y)=(x,0) ép toàn bộ mặt phẳng xuống trục Ox.

Trước chiếu:
- AB=(0,0)→(1,0).
- CD=(0,1)→(1,1).
- Hai đoạn song song rời nhau: **NONE**.

Sau chiếu, cả hai đều thành (0,0)→(1,0), nên giao thành **OVERLAP**.

~~~text
Before singular projection: NONE
After singular projection: OVERLAP
~~~

Bài test đòi “giao đoạn luôn bất biến dưới affine kể cả det=0” là sai giả thiết. Mã Java cố ý từ chối tạo Affine nếu det=0, rồi trình bày phép chiếu suy biến bằng một phản ví dụ riêng.

## 4. Orientation: quy luật nhân định thức

Đặt u=B−A, v=C−A. Phần tịnh tiến t bị triệt tiêu trong hiệu:

\[
T(B)-T(A)=Mu,\qquad T(C)-T(A)=Mv.
\]

Tính chất đại số của cross product 2D:

\[
\operatorname{cross}(Mu,Mv)
=\det(M)\operatorname{cross}(u,v).
\]

Suy ra quan hệ chính xác:

\[
\boxed{
\operatorname{orient}(TA,TB,TC)
=\det(M)\operatorname{orient}(A,B,C).
}
\]

Khi det>0, dấu orientation được bảo toàn. Khi det<0, dấu đảo. Nếu orientation gốc bằng 0, sau mọi affine vẫn bằng 0, kể cả phép suy biến.

Với A=(0,0), B=(4,0), C=(1,3), orientation=12:
- Sau tịnh tiến: **12**.
- Sau quay 90°: **12**.
- Sau phản xạ qua Ox: **−12**.
- Sau phóng đại đều ×2: **48**.
- Sau shear x'=x+y: **12**.

Đây là **equivariance**, không phải bất biến nguyên giá trị đối với mọi ma trận. Khi muốn so orientation theo dấu thay vì giá trị, áp dụng sign(orient')=sign(det)×sign(orient) cho det≠0.

## 5. Quan hệ điểm nằm trên đoạn

Điểm P thuộc đoạn đóng AB nếu và chỉ nếu tồn tại t trong [0,1] để:

\[
P=A+t(B-A).
\]

Với T affine:

\[
T(P)=T(A)+t(T(B)-T(A)).
\]

Vậy P thuộc AB thì T(P) thuộc T(AB). Nếu T khả nghịch, chiều ngược cũng đúng:

\[
\boxed{P\in AB\iff T(P)\in T(AB)}.
\]

Một predicate onSegment chính xác trên tọa độ nguyên kiểm tra:
1. orient(A,B,P)=0.
2. P.x nằm giữa hai đầu x của A,B, kể cả ranh giới.
3. P.y nằm giữa hai đầu y của A,B, kể cả ranh giới.

Khi A=B là đoạn suy biến thành một điểm, orientation(A,A,P)=0 cho mọi P, nhưng hai điều kiện khoảng chỉ chấp nhận P=A. Vì vậy phải dùng **cả orientation và hộp bao**, không chỉ kiểm tra cross=0.

Metamorphic test của onSegment rất hữu ích với đường thẳng đứng, dốc âm, đầu mút, điểm ngoài đoạn nhưng thẳng hàng và đoạn suy biến.

## 6. Phân loại giao đoạn và các biến đổi bảo toàn

Với hai đoạn đóng S1,S2 và T khả nghịch:

\[
T(S_1\cap S_2)=T(S_1)\cap T(S_2).
\]

Chứng minh: chiều thuận đúng vì ảnh của một điểm chung vẫn thuộc cả hai ảnh. Chiều ngược đúng vì T một-một, mọi điểm giao trong ảnh có đúng một tiền ảnh thuộc cả hai đoạn. Từ đó loại **NONE/POINT/OVERLAP** bất biến, ngay cả dưới phản xạ và shear.

### 6.1. Thuật toán orientation-based

Đặt:

\[
o_1=\operatorname{sign}(\operatorname{orient}(A,B,C)),
\quad
o_2=\operatorname{sign}(\operatorname{orient}(A,B,D)),
\]

\[
o_3=\operatorname{sign}(\operatorname{orient}(C,D,A)),
\quad
o_4=\operatorname{sign}(\operatorname{orient}(C,D,B)).
\]

- Nếu hai AABB không chồng trên một trong hai trục: **NONE**.
- Nếu cả bốn orientation đều bằng 0: xử lý **đồng tuyến** bằng cách lấy giao hai khoảng đầu mút theo thứ tự lex(x,y). Nếu rời: NONE; chạm tại một điểm: POINT; chồng đoạn dương: OVERLAP.
- Nếu một trong C,D nằm trên AB hoặc một trong A,B nằm trên CD: **POINT**.
- Nếu o1,o2 trái dấu nghiêm ngặt và o3,o4 trái dấu nghiêm ngặt: **POINT**.
- Các trường hợp còn lại: **NONE**.

**Đặt nhánh đồng tuyến trước nhánh chạm đầu mút.** Nếu hai đoạn có phần chung là một đoạn, một đầu mút thường nằm trên đoạn kia; trả POINT ngay sẽ sai.

Trong bài, **đoạn đóng** bao gồm đầu mút. Với đoạn mở/nửa mở, quy ước giao tiếp xúc khác, không thể tái sử dụng mọi quan hệ kiểm thử mà không chỉnh điều kiện.

### 6.2. Kiểm thử các nhánh khó

Bảng mẫu:

| Cấu hình | Kết quả |
|---|---|
| Hai đường chéo hình vuông cắt nhau | POINT |
| Hai đoạn đồng tuyến chồng nhau | OVERLAP |
| Hai đoạn đồng tuyến chỉ chạm ranh giới | POINT |
| Hai đoạn song song khác đường | NONE |
| Hộp bao AABB chồng nhưng đoạn rời | NONE |
| Một đoạn suy biến thành điểm nằm trên đoạn kia | POINT |
| Một đoạn là điểm nằm ngoài đoạn kia | NONE |
| Hai đoạn là cùng một điểm | POINT |
| Hai đoạn là hai điểm khác nhau | NONE |

Khi làm metamorphic tests, nên thêm **đảo đầu mút**, **đổi thứ tự đoạn** và các ma trận khả nghịch vào từng mẫu này.

## 7. Diện tích có hướng theo công thức shoelace

Cho chu trình có thứ tự các điểm P0,...,P(n−1) với Pn=P0, đặt:

\[
S_2=\sum_{i=0}^{n-1}
(x_i y_{i+1}-y_i x_{i+1}).
\]

Với đa giác đơn, |S2|/2 là diện tích hình học; dấu phản ánh chiều duyệt đỉnh. Với chu trình tự cắt, S2 vẫn có nghĩa là **tổng đại số có hướng**, không được đồng nhất máy móc với diện tích của miền phủ.

Phép affine có định thức det(M) thỏa:

\[
\boxed{S_2(T(P))=\det(M)S_2(P)}.
\]

Tịnh tiến không tác động vì các hạng dịch chuyển triệt tiêu qua chu trình; phần tuyến tính làm tích có hướng biến đổi theo định thức.

### Ví dụ hình chữ nhật

Đa giác (0,0)→(3,0)→(3,2)→(0,2) có S2=12 và diện tích hình học 6.

~~~text
Rectangle area2: 12
Reflected rectangle area2: -12
Sheared rectangle area2: 12
Scaled rectangle area2: 48
~~~

Phản xạ đảo **diện tích có hướng**, không biến diện tích không âm thành âm. Phóng đại đều ×2 làm diện tích tăng ×4.

## 8. Bao lồi và phép biến đổi

Với mọi affine T, dù suy biến:

\[
T(\operatorname{conv}(P))=\operatorname{conv}(T(P)).
\]

Lý do: affine bảo toàn mọi tổ hợp lồi \(\sum\lambda_ip_i\), với \(\lambda_i\ge0\) và tổng các \(\lambda_i=1\).

Nếu T **khả nghịch**, mỗi đỉnh cực biên của bao lồi gốc ánh xạ đến đúng một cực đỉnh của bao lồi ảnh. Vậy:

\[
\operatorname{vertices}(\operatorname{conv}(T(P)))
=T(\operatorname{vertices}(\operatorname{conv}(P))).
\]

Lưu ý hai tầng kết quả:
- **Tập bao lồi** là một tập hình học và quan hệ trên đúng ngay cả khi affine suy biến.
- **Tập đỉnh cực biên** ánh xạ một-một cần phép khả nghịch. Phép chiếu có thể gộp nhiều đỉnh và làm những điểm không cực biên trước đó trở thành cực trị của ảnh.

### 8.1. Thuật toán monotone chain trong bài

Bản Java:
1. Loại các điểm trùng.
2. Sort theo x, rồi y.
3. Dựng chuỗi dưới và chuỗi trên; trong khi hai cạnh liên tiếp không tạo một góc quay trái nghiêm ngặt (orientation≤0), bỏ đỉnh giữa.
4. Ghép hai chuỗi, tránh lặp lại hai đầu.

Kết quả chỉ có **đỉnh cực biên**, không giữ điểm nằm giữa trên cạnh. Nếu mọi điểm thẳng hàng, hull chỉ là hai đầu mút khác nhau; nếu mọi điểm trùng, hull gồm một điểm; tập rỗng trả danh sách rỗng.

Phản xạ có thể đảo chiều vòng CCW/CW, nên kiểm thử so **HashSet các điểm cực biên** của hull đã biến đổi với **HashSet ảnh của các đỉnh hull ban đầu**. Không nên so danh sách theo từng chỉ số.

## 9. Khoảng cách và sai lầm “affine nào cũng bảo toàn”

Bình phương khoảng cách Euclid:

\[
d^2(P,Q)=(P_x-Q_x)^2+(P_y-Q_y)^2.
\]

Nếu T(p)=Mp+t:

\[
d^2(T(P),T(Q))=(P-Q)^TM^TM(P-Q).
\]

- Với **đẳng cự** (MᵀM=I), bình phương khoảng cách giữ nguyên: tịnh tiến, quay, phản xạ.
- Với **phóng đại đều hệ số s** (MᵀM=s²I), bình phương khoảng cách nhân **s²**.
- Với **affine tổng quát** như shear, thường không có quan hệ giữ nguyên khoảng cách.

Chọn P=(0,0), Q=(1,1):
- Gốc: d²=1²+1²=2.
- Quay 90°: d²=2.
- Phản xạ: d²=2.
- Phóng đại đều ×2: d²=8.
- Shear (x,y)→(x+y,y): Q'=(2,1), d²=**5**.

Do shear det=1, nó vẫn giữ diện tích có hướng và phân loại giao đoạn. Điều đó **không** suy ra nó giữ khoảng cách, góc, tính vuông góc, chu vi, bán kính hoặc thứ tự điểm gần nhất.

AABB (hộp bao song song trục x,y) cũng không được coi là bất biến qua quay hoặc shear. Bộ lọc AABB phải được tính lại trong hệ tọa độ sau biến đổi.

## 10. Oracle độc lập và bộ sinh dữ liệu

Metamorphic relation có thể phát hiện lỗi, nhưng một thuật toán sai có hệ thống vẫn có thể vô tình thỏa các đối xứng. Vì vậy cần **oracle khác cơ chế** cùng những ví dụ có đáp án chắc chắn.

### 10.1. Oracle tham số giao đoạn

Đặt r=B−A, s=D−C, q=C−A, den=cross(r,s).

Khi den≠0, hai đường thẳng vô hạn gặp nhau tại:

\[
t=\frac{\operatorname{cross}(q,s)}{den},
\qquad
u=\frac{\operatorname{cross}(q,r)}{den}.
\]

Hai **đoạn đóng** giao một điểm khi và chỉ khi **0≤t≤1 và 0≤u≤1**. Với tử/mẫu BigInteger, chỉ cần so với 0 và den; nếu den âm thì đảo chiều bất đẳng thức, không cần dùng double.

Khi den=0:
- Nếu một/both đoạn là điểm, kiểm tra tọa độ điểm hoặc kiểm tra điểm trên đoạn kia.
- Nếu hai đường khác nhau và song song, kết quả NONE.
- Nếu hai đoạn đồng tuyến, chiếu thành khoảng theo thứ tự lex(x,y): rời nhau, chạm một điểm hoặc chồng đoạn dương.

Oracle tham số không dùng bốn orientation dấu để quyết định nhánh không song song, nên đủ **khác cơ chế** để làm kiểm tra chéo hữu ích. Tuy nhiên cả hai vẫn dùng phép toán nguyên chính xác và logic riêng cho đồng tuyến, vì thế nó không thay thế chứng minh toán học.

### 10.2. Tạo trường hợp suy biến có chủ đích

Sinh bốn/sáu điểm độc lập từ một bảng tọa độ lớn dễ bỏ lỡ các ca đồng tuyến chính xác. Dùng bộ sinh thứ hai:
- Chọn một gốc P nguyên.
- Chọn vectơ v=(dx,dy) nguyên.
- Chọn các hệ số nguyên t1,...,t6.
- Sinh các điểm \(P+t_iv\).

Cách này chủ động sinh điểm cùng đường, trùng nhau khi ti bằng nhau, đường đứng nếu dx=0 và cả đoạn suy biến khi v=(0,0).

Bản demo sử dụng:
- 2.000 bộ điểm độc lập.
- 500 bộ đồng tuyến có chủ đích.
- 5 phép biến đổi affine khả nghịch cho mỗi bộ.
- Tổng **2.500 bộ dữ liệu, 12.500 lượt biến đổi**.
- Random(4312026L) cho khả năng tái lập.

### 10.3. Khi một test thất bại

Cần ghi seed, trialIndex, ma trận/translation và các điểm gốc. Sau đó thử **rút gọn phản ví dụ (shrinking)**: giảm số điểm, đưa tọa độ về số nhỏ, bỏ phép biến đổi không thiết yếu. Lưu ca tối giản thành regression test cố định.

Bộ kiểm thử dùng một hàm verify ném AssertionError rõ ràng, **không dùng Java assert** phụ thuộc cờ JVM -ea. Do đó thất bại không bị bỏ qua khi chạy mặc định.

## 11. Chương trình Java 17 đầy đủ

Lưu tệp **GeometryMetamorphicDemo.java**. Code sau dùng record Point, Segment, Affine; BigInteger cho determinant, orientation, signed area và distanceSquared; phân loại giao đoạn; convex hull monotone chain; oracle tham số; và property-based tests qua các phép biến đổi đã định nghĩa.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.Set;

public final class GeometryMetamorphicDemo {
    private GeometryMetamorphicDemo() {
    }

    private static final BigInteger ZERO = BigInteger.ZERO;
    private static final BigInteger FOUR = BigInteger.valueOf(4);

    public record Point(long x, long y) {
    }

    public record Segment(Point a, Point b) {
        public Segment {
            Objects.requireNonNull(a, "a");
            Objects.requireNonNull(b, "b");
        }

        public Segment reversed() {
            return new Segment(b, a);
        }
    }

    public record Affine(
            long xx, long xy, long yx, long yy,
            long dx, long dy) {
        public Affine {
            if (determinantOf(xx, xy, yx, yy).signum() == 0) {
                throw new IllegalArgumentException(
                        "Affine matrix must be invertible");
            }
        }

        public BigInteger det() {
            return determinantOf(xx, xy, yx, yy);
        }

        public Point map(Point p) {
            BigInteger x = bi(xx).multiply(bi(p.x()))
                    .add(bi(xy).multiply(bi(p.y())))
                    .add(bi(dx));
            BigInteger y = bi(yx).multiply(bi(p.x()))
                    .add(bi(yy).multiply(bi(p.y())))
                    .add(bi(dy));
            return new Point(
                    x.longValueExact(), y.longValueExact());
        }

        public Segment map(Segment s) {
            return new Segment(map(s.a()), map(s.b()));
        }
    }

    public enum Kind {
        NONE, POINT, OVERLAP
    }

    private static BigInteger bi(long value) {
        return BigInteger.valueOf(value);
    }

    private static BigInteger determinantOf(
            long xx, long xy, long yx, long yy) {
        return bi(xx).multiply(bi(yy))
                .subtract(bi(xy).multiply(bi(yx)));
    }

    private static BigInteger cross(
            BigInteger ux, BigInteger uy,
            BigInteger vx, BigInteger vy) {
        return ux.multiply(vy).subtract(uy.multiply(vx));
    }

    public static BigInteger orientation(
            Point a, Point b, Point c) {
        return cross(
                bi(b.x()).subtract(bi(a.x())),
                bi(b.y()).subtract(bi(a.y())),
                bi(c.x()).subtract(bi(a.x())),
                bi(c.y()).subtract(bi(a.y())));
    }

    public static boolean onSegment(
            Point a, Point b, Point p) {
        return orientation(a, b, p).signum() == 0
                && p.x() >= Math.min(a.x(), b.x())
                && p.x() <= Math.max(a.x(), b.x())
                && p.y() >= Math.min(a.y(), b.y())
                && p.y() <= Math.max(a.y(), b.y());
    }

    private static boolean boxesOverlap(
            Point a, Point b, Point c, Point d) {
        long left = Math.max(
                Math.min(a.x(), b.x()),
                Math.min(c.x(), d.x()));
        long right = Math.min(
                Math.max(a.x(), b.x()),
                Math.max(c.x(), d.x()));
        long bottom = Math.max(
                Math.min(a.y(), b.y()),
                Math.min(c.y(), d.y()));
        long top = Math.min(
                Math.max(a.y(), b.y()),
                Math.max(c.y(), d.y()));
        return left <= right && bottom <= top;
    }

    private static final Comparator<Point> LEX =
            Comparator.comparingLong(Point::x)
                    .thenComparingLong(Point::y);

    private static Point low(Point a, Point b) {
        return LEX.compare(a, b) <= 0 ? a : b;
    }

    private static Point high(Point a, Point b) {
        return LEX.compare(a, b) >= 0 ? a : b;
    }

    private static boolean opposite(int x, int y) {
        return (x > 0 && y < 0) || (x < 0 && y > 0);
    }

    public static Kind intersectionKind(
            Segment first, Segment second) {
        Point a = first.a(), b = first.b();
        Point c = second.a(), d = second.b();

        if (!boxesOverlap(a, b, c, d)) {
            return Kind.NONE;
        }

        int o1 = orientation(a, b, c).signum();
        int o2 = orientation(a, b, d).signum();
        int o3 = orientation(c, d, a).signum();
        int o4 = orientation(c, d, b).signum();

        if (o1 == 0 && o2 == 0 && o3 == 0 && o4 == 0) {
            Point start = high(low(a, b), low(c, d));
            Point end = low(high(a, b), high(c, d));
            int cmp = LEX.compare(start, end);
            return cmp > 0 ? Kind.NONE
                    : cmp == 0 ? Kind.POINT : Kind.OVERLAP;
        }

        if ((o1 == 0 && onSegment(a, b, c))
                || (o2 == 0 && onSegment(a, b, d))
                || (o3 == 0 && onSegment(c, d, a))
                || (o4 == 0 && onSegment(c, d, b))) {
            return Kind.POINT;
        }

        return opposite(o1, o2) && opposite(o3, o4)
                ? Kind.POINT : Kind.NONE;
    }

    // Kiểm tra 0 <= numerator/denominator <= 1.
    private static boolean withinUnit(
            BigInteger numerator, BigInteger denominator) {
        if (denominator.signum() > 0) {
            return numerator.signum() >= 0
                    && numerator.compareTo(denominator) <= 0;
        }
        return numerator.signum() <= 0
                && numerator.compareTo(denominator) >= 0;
    }

    // Oracle cho đoạn điểm: collinear + tích vô hướng <= 0.
    private static boolean referenceOnSegment(
            Point a, Point b, Point p) {
        BigInteger px = bi(p.x()).subtract(bi(a.x()));
        BigInteger py = bi(p.y()).subtract(bi(a.y()));
        BigInteger vx = bi(b.x()).subtract(bi(a.x()));
        BigInteger vy = bi(b.y()).subtract(bi(a.y()));
        if (cross(px, py, vx, vy).signum() != 0) {
            return false;
        }
        BigInteger qx = bi(p.x()).subtract(bi(b.x()));
        BigInteger qy = bi(p.y()).subtract(bi(b.y()));
        return px.multiply(qx).add(py.multiply(qy))
                .signum() <= 0;
    }

    // Oracle dùng tham số đường thẳng, không dùng bốn dấu orientation.
    public static Kind referenceKind(
            Segment first, Segment second) {
        Point a = first.a(), b = first.b();
        Point c = second.a(), d = second.b();

        BigInteger rx = bi(b.x()).subtract(bi(a.x()));
        BigInteger ry = bi(b.y()).subtract(bi(a.y()));
        BigInteger sx = bi(d.x()).subtract(bi(c.x()));
        BigInteger sy = bi(d.y()).subtract(bi(c.y()));
        BigInteger qx = bi(c.x()).subtract(bi(a.x()));
        BigInteger qy = bi(c.y()).subtract(bi(a.y()));

        BigInteger den = cross(rx, ry, sx, sy);
        if (den.signum() != 0) {
            BigInteger t = cross(qx, qy, sx, sy);
            BigInteger u = cross(qx, qy, rx, ry);
            return withinUnit(t, den) && withinUnit(u, den)
                    ? Kind.POINT : Kind.NONE;
        }

        if (a.equals(b) && c.equals(d)) {
            return a.equals(c) ? Kind.POINT : Kind.NONE;
        }
        if (a.equals(b)) {
            return referenceOnSegment(c, d, a)
                    ? Kind.POINT : Kind.NONE;
        }
        if (c.equals(d)) {
            return referenceOnSegment(a, b, c)
                    ? Kind.POINT : Kind.NONE;
        }

        if (cross(qx, qy, rx, ry).signum() != 0) {
            return Kind.NONE;
        }

        Point start = high(low(a, b), low(c, d));
        Point end = low(high(a, b), high(c, d));
        int cmp = LEX.compare(start, end);
        return cmp > 0 ? Kind.NONE
                : cmp == 0 ? Kind.POINT : Kind.OVERLAP;
    }

    public static BigInteger signedDoubleArea(
            List<Point> vertices) {
        BigInteger sum = ZERO;
        for (int i = 0; i < vertices.size(); i++) {
            Point p = vertices.get(i);
            Point q = vertices.get((i + 1) % vertices.size());
            sum = sum.add(bi(p.x()).multiply(bi(q.y())))
                    .subtract(bi(p.y()).multiply(bi(q.x())));
        }
        return sum;
    }

    public static BigInteger distanceSquared(
            Point a, Point b) {
        BigInteger dx = bi(a.x()).subtract(bi(b.x()));
        BigInteger dy = bi(a.y()).subtract(bi(b.y()));
        return dx.multiply(dx).add(dy.multiply(dy));
    }

    // Monotone chain: chỉ giữ cực đỉnh, bỏ điểm trùng và thẳng hàng giữa.
    public static List<Point> convexHull(List<Point> input) {
        List<Point> points = new ArrayList<>(
                new HashSet<>(input));
        points.sort(LEX);
        if (points.size() <= 1) {
            return points;
        }

        List<Point> lower = new ArrayList<>();
        for (Point p : points) {
            while (lower.size() >= 2
                    && orientation(
                        lower.get(lower.size() - 2),
                        lower.get(lower.size() - 1), p
                    ).signum() <= 0) {
                lower.remove(lower.size() - 1);
            }
            lower.add(p);
        }

        List<Point> upper = new ArrayList<>();
        for (int i = points.size() - 1; i >= 0; i--) {
            Point p = points.get(i);
            while (upper.size() >= 2
                    && orientation(
                        upper.get(upper.size() - 2),
                        upper.get(upper.size() - 1), p
                    ).signum() <= 0) {
                upper.remove(upper.size() - 1);
            }
            upper.add(p);
        }
        lower.remove(lower.size() - 1);
        upper.remove(upper.size() - 1);
        lower.addAll(upper);
        return lower;
    }

    private static List<Point> mappedPoints(
            List<Point> points, Affine transform) {
        List<Point> result = new ArrayList<>();
        for (Point p : points) {
            result.add(transform.map(p));
        }
        return result;
    }

    private static boolean sameHullVertexSet(
            List<Point> points, Affine transform) {
        Set<Point> transformedOriginal = new HashSet<>();
        for (Point vertex : convexHull(points)) {
            transformedOriginal.add(transform.map(vertex));
        }
        Set<Point> actual = new HashSet<>(
                convexHull(mappedPoints(points, transform)));
        return actual.equals(transformedOriginal);
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static Point randomPoint(Random rng) {
        return new Point(
                rng.nextInt(25) - 12,
                rng.nextInt(25) - 12);
    }

    private static List<Point> randomCase(
            Random rng, boolean collinear) {
        List<Point> points = new ArrayList<>();
        if (!collinear) {
            for (int i = 0; i < 6; i++) {
                points.add(randomPoint(rng));
            }
            return points;
        }

        Point origin = randomPoint(rng);
        long vx = rng.nextInt(7) - 3;
        long vy = rng.nextInt(7) - 3;
        for (int i = 0; i < 6; i++) {
            long t = rng.nextInt(11) - 5;
            points.add(new Point(
                    Math.addExact(origin.x(),
                            Math.multiplyExact(t, vx)),
                    Math.addExact(origin.y(),
                            Math.multiplyExact(t, vy))));
        }
        return points;
    }

    private static void checkCase(
            List<Point> points,
            List<Affine> transforms, int trial) {
        Point a = points.get(0), b = points.get(1);
        Point c = points.get(2), d = points.get(3);
        Point p = points.get(4);
        Segment first = new Segment(a, b);
        Segment second = new Segment(c, d);

        Kind kind = intersectionKind(first, second);
        boolean belongs = onSegment(a, b, p);
        BigInteger orientationValue = orientation(a, b, c);
        BigInteger area = signedDoubleArea(
                List.of(a, b, c, d));
        BigInteger distance = distanceSquared(a, b);

        check(kind == referenceKind(first, second),
                "Original reference mismatch trial=" + trial);
        check(kind == intersectionKind(second, first),
                "Segment swap mismatch trial=" + trial);
        check(kind == intersectionKind(
                first.reversed(), second.reversed()),
                "Endpoint reversal mismatch trial=" + trial);
        check(orientation(a, c, b)
                .equals(orientationValue.negate()),
                "Orientation antisymmetry mismatch trial=" + trial);

        for (int index = 0; index < transforms.size(); index++) {
            Affine affine = transforms.get(index);
            List<Point> mapped = mappedPoints(points, affine);
            Point aa = mapped.get(0), bb = mapped.get(1);
            Point cc = mapped.get(2), dd = mapped.get(3);
            Point pp = mapped.get(4);
            Segment left = new Segment(aa, bb);
            Segment right = new Segment(cc, dd);
            String tag = "trial=" + trial
                    + " transform=" + index;

            check(intersectionKind(left, right) == kind,
                    "Intersection relation failed: " + tag);
            check(intersectionKind(left, right)
                    == referenceKind(left, right),
                    "Transformed oracle mismatch: " + tag);
            check(onSegment(aa, bb, pp) == belongs,
                    "Point-on-segment changed: " + tag);
            check(orientation(aa, bb, cc).equals(
                    orientationValue.multiply(affine.det())),
                    "Cross determinant law failed: " + tag);
            check(signedDoubleArea(
                    List.of(aa, bb, cc, dd)).equals(
                    area.multiply(affine.det())),
                    "Area determinant law failed: " + tag);
            check(sameHullVertexSet(points, affine),
                    "Hull vertex relation failed: " + tag);

            BigInteger newDistance = distanceSquared(aa, bb);
            if (index <= 2) {
                check(newDistance.equals(distance),
                        "Isometry distance failed: " + tag);
            } else if (index == 3) {
                check(newDistance.equals(distance.multiply(FOUR)),
                        "Scale-square distance failed: " + tag);
            }
            // index==4 là shear: không yêu cầu giữ khoảng cách.
        }
    }

    public static void main(String[] args) {
        Affine translation = new Affine(
                1, 0, 0, 1, 10, -7);
        Affine rotation = new Affine(
                0, -1, 1, 0, 0, 0);
        Affine reflection = new Affine(
                1, 0, 0, -1, 0, 0);
        Affine scale2 = new Affine(
                2, 0, 0, 2, 0, 0);
        Affine shear = new Affine(
                1, 1, 0, 1, 0, 0);
        List<Affine> transforms = List.of(
                translation, rotation, reflection, scale2, shear);

        Point a = new Point(0, 0);
        Point b = new Point(4, 0);
        Point c = new Point(1, 3);
        System.out.println("Orientation original: "
                + orientation(a, b, c));
        System.out.println("Orientation swapped: "
                + orientation(a, c, b));
        System.out.println("Orientation reflected: "
                + orientation(
                    reflection.map(a), reflection.map(b),
                    reflection.map(c)));
        System.out.println("Orientation scaled: "
                + orientation(
                    scale2.map(a), scale2.map(b),
                    scale2.map(c)));

        List<Point> rectangle = List.of(
                new Point(0, 0), new Point(3, 0),
                new Point(3, 2), new Point(0, 2));
        System.out.println("Rectangle area2: "
                + signedDoubleArea(rectangle));
        System.out.println("Reflected rectangle area2: "
                + signedDoubleArea(
                    mappedPoints(rectangle, reflection)));
        System.out.println("Sheared rectangle area2: "
                + signedDoubleArea(
                    mappedPoints(rectangle, shear)));
        System.out.println("Scaled rectangle area2: "
                + signedDoubleArea(
                    mappedPoints(rectangle, scale2)));

        Point p = new Point(0, 0);
        Point q = new Point(1, 1);
        System.out.println("Distance2 original: "
                + distanceSquared(p, q));
        System.out.println("Distance2 rotate90: "
                + distanceSquared(
                    rotation.map(p), rotation.map(q)));
        System.out.println("Distance2 shear: "
                + distanceSquared(
                    shear.map(p), shear.map(q)));
        System.out.println("Distance2 scale2: "
                + distanceSquared(
                    scale2.map(p), scale2.map(q)));

        Segment diagonalA = new Segment(
                new Point(0, 0), new Point(4, 4));
        Segment diagonalB = new Segment(
                new Point(0, 4), new Point(4, 0));
        Segment overlapA = new Segment(
                new Point(0, 0), new Point(5, 0));
        Segment overlapB = new Segment(
                new Point(2, 0), new Point(7, 0));

        System.out.println("Crossing kind: "
                + intersectionKind(diagonalA, diagonalB));
        System.out.println("Crossing reflected kind: "
                + intersectionKind(
                    reflection.map(diagonalA),
                    reflection.map(diagonalB)));
        System.out.println("Overlap kind: "
                + intersectionKind(overlapA, overlapB));

        Segment horizontal0 = new Segment(
                new Point(0, 0), new Point(1, 0));
        Segment horizontal1 = new Segment(
                new Point(0, 1), new Point(1, 1));
        Kind beforeProjection = intersectionKind(
                horizontal0, horizontal1);
        Kind afterProjection = intersectionKind(
                horizontal0, horizontal0);
        System.out.println("Singular projection changes kind: "
                + (beforeProjection == Kind.NONE
                   && afterProjection == Kind.OVERLAP));

        List<Point> hullPoints = new ArrayList<>(rectangle);
        hullPoints.add(new Point(1, 1));
        System.out.println("Hull vertex count: "
                + convexHull(hullPoints).size());
        System.out.println("Hull reflected vertex set: "
                + sameHullVertexSet(hullPoints, reflection));

        try {
            new Affine(1, 0, 0, 0, 0, 0);
            System.out.println("Reject singular matrix: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject singular matrix: true");
        }

        try {
            scale2.map(new Point(Long.MAX_VALUE, 0));
            System.out.println("Reject long overflow: false");
        } catch (ArithmeticException expected) {
            System.out.println("Reject long overflow: true");
        }

        Point extremeA = new Point(
                Long.MIN_VALUE, Long.MIN_VALUE);
        Point extremeB = new Point(
                Long.MAX_VALUE, Long.MIN_VALUE);
        Point extremeC = new Point(
                Long.MIN_VALUE, Long.MAX_VALUE);
        System.out.println("Extreme orientation positive: "
                + (orientation(
                    extremeA, extremeB, extremeC).signum() > 0));

        Random rng = new Random(4312026L);
        int trials = 2500;
        for (int trial = 0; trial < trials; trial++) {
            List<Point> points = randomCase(
                    rng, trial >= 2000);
            checkCase(points, transforms, trial);
        }
        System.out.println("Randomized cases: " + trials);
        System.out.println("Affine relation checks: "
                + (trials * transforms.size()));
        System.out.println("All assertions passed: true");
    }
}
~~~

### 11.1. Biên dịch và chạy

Với **JDK 17 trở lên**, lưu đúng tên public class:

~~~bash
javac -encoding UTF-8 GeometryMetamorphicDemo.java
java GeometryMetamorphicDemo
~~~

**Kết quả stdout dự kiến:**

~~~text
Orientation original: 12
Orientation swapped: -12
Orientation reflected: -12
Orientation scaled: 48
Rectangle area2: 12
Reflected rectangle area2: -12
Sheared rectangle area2: 12
Scaled rectangle area2: 48
Distance2 original: 2
Distance2 rotate90: 2
Distance2 shear: 5
Distance2 scale2: 8
Crossing kind: POINT
Crossing reflected kind: POINT
Overlap kind: OVERLAP
Singular projection changes kind: true
Hull vertex count: 4
Hull reflected vertex set: true
Reject singular matrix: true
Reject long overflow: true
Extreme orientation positive: true
Randomized cases: 2500
Affine relation checks: 12500
All assertions passed: true
~~~

### 11.2. Giải thích triển khai

**Point và Segment** là record bất biến; đầu mút trùng nhau được chấp nhận để mô tả đoạn suy biến.

**Affine** chứa ma trận 2×2 và tịnh tiến. Constructor bác bỏ det=0. Hàm map sử dụng BigInteger trước khi nhân cộng, sau đó longValueExact để phát hiện ảnh ra ngoài phạm vi long.

**orientation** trả nguyên định thức chứ không chỉ sign. Vì vậy có thể thử chính xác quan hệ orientation ảnh bằng det×orientation gốc.

**intersectionKind** dùng AABB, bốn dấu orientation, xử lý đồng tuyến trước chạm đầu mút và giao nghiêm ngặt. Để tăng tính độc lập, **referenceKind** dùng tham số t,u của hai đường, kiểm tra tử/mẫu trong [0,1], rồi xử lý các trường hợp song song và suy biến riêng.

**signedDoubleArea** tính shoelace trên chu trình có thứ tự. Với bốn điểm ngẫu nhiên có thể tự cắt, nó vẫn là tổng đại số và vẫn nhân det dưới affine.

**convexHull** dùng monotone chain, so BigInteger orientation, bỏ điểm trùng/collinear nội cạnh. **sameHullVertexSet** so hai HashSet: ảnh của hull gốc và hull dựng từ toàn bộ điểm đã biến đổi.

**checkCase** kiểm tra đối xứng đổi đoạn/đảo đầu mút, oracle tham số, orientation đảo dấu, năm phép affine, nhãn giao đoạn, onSegment, cross/area và hull. Với ba biến đổi đẳng cự đầu, khoảng cách bình phương giữ nguyên; với scale2 tăng ×4; với shear không có assertion sai về khoảng cách.

**randomCase** sinh ngẫu nhiên có seed: 2.000 bộ thông thường và 500 bộ collinear có chủ đích, kể cả trường hợp đoạn suy biến.

**check** luôn ném AssertionError nếu sai, không phụ thuộc JVM -ea. Nếu một trial thất bại, stdout thành công cuối sẽ không được in; thông báo lỗi chứa chỉ số trial và phép biến đổi.

## 12. Độ phức tạp và phạm vi bảo đảm

Với hai đoạn và tọa độ nguyên trong long, một lần kiểm tra orientation, onSegment hoặc giao đoạn dùng **O(1) phép hình học** trong mô hình số học đơn vị. Trên BigInteger, chi phí thực tế mỗi phép tính phụ thuộc độ dài bit, dù với đầu vào long và ma trận long thì số bit giá trị trung gian vẫn bị chặn.

Với h điểm:
- Tính signedDoubleArea O(h).
- ConvexHull monotone chain O(h log h) thời gian, O(h) bộ nhớ, với sort và hai lượt duyệt.
- Kiểm tra biến đổi một bộ h điểm qua K ma trận cần O(Kh) để dựng ảnh; kiểm tra hull làm tổng **O(Kh log h)**.

Với T bộ dữ liệu, toàn bộ harness có cận:

\[
\boxed{O(TK h\log h)}
\]

cho phần kiểm thử có bao lồi, cộng chi phí BigInteger/đối chiếu oracle. Bản demo dùng T=2500,K=5,h=6; đây là quy mô kiểm thử chức năng nhỏ, không phải benchmark thuật toán hull trên hàng triệu điểm.

**Giới hạn quan trọng:** Metamorphic tests là bằng chứng thực nghiệm và giúp tìm lỗi, **không phải chứng minh thuật toán đúng mọi đầu vào**. Cần phối hợp với chứng minh toán học, oracle độc lập và regression cases.

## 13. Những lỗi thường gặp

1. Đòi mọi affine khả nghịch giữ khoảng cách Euclid.
2. Đòi phản xạ giữ nguyên dấu orientation.
3. Đòi scale2 giữ nguyên diện tích hoặc bình phương khoảng cách.
4. Dùng phép chiếu det=0 trong bộ thử quan hệ giao đoạn bảo toàn.
5. So danh sách hull nguyên vị trí sau phản xạ mà không chuẩn hóa vòng.
6. Bỏ qua điểm thẳng hàng và bản sao điểm trong hợp đồng convex hull.
7. Chỉ sinh đầu mút ngẫu nhiên độc lập, không tạo ca đồng tuyến có chủ đích.
8. Quên đầu mút được tính trong đoạn đóng.
9. Coi AABB chồng là đủ kết luận giao đoạn.
10. Kiểm tra orientation bằng long nhưng tính hiệu trước khi ép BigInteger.
11. Dùng double và epsilon tuyệt đối tùy tiện với tọa độ nguyên.
12. Dùng Java longValue không kiểm tra tràn khi chuyển ảnh affine.
13. So độ lớn cross thay vì nhân nó với det(M) trong test đúng.
14. So diện tích có hướng với diện tích hình học không âm mà không lấy trị tuyệt đối.
15. Khẳng định hull vertex relation đúng dưới affine suy biến.
16. Đánh đồng thuộc tính tập hình học với thứ tự serialization của đỉnh.
17. Không kiểm tra đổi thứ tự hai đoạn/đảo chiều đầu mút.
18. Dùng mỗi thuật toán chính làm oracle cho chính nó.
19. Không kiểm thử điểm trùng, đoạn suy biến, đường đứng, điểm thẳng hàng.
20. Dùng Java assert khi không có -ea, khiến checks bị vô hiệu.
21. Không lưu seed/trial khi gặp một case hiếm sai.
22. Coi ArithmeticException do vượt long là phản ví dụ của định lý toán học.
23. Đòi bảo toàn AABB dưới quay/shear.
24. Dùng quan hệ shear bảo toàn khoảng cách chỉ vì shear có det=1.
25. Chỉ test dấu orientation mà không test giá trị nhân định thức.
26. Không phân biệt thuộc tính “bất biến” và “biến đổi có quy luật”.
27. Không đưa phản ví dụ của giả thiết sai vào bộ test.
28. Cho rằng vượt hàng nghìn test là chứng minh đầy đủ.
29. Không rút gọn và lưu regression case từ một lỗi tìm được.
30. Không đọc rõ quy ước giữ/loại collinear hull hoặc đoạn đóng/mở.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Metamorphic testing là gì?

**Đáp án:** Kiểm thử quan hệ đã chứng minh giữa kết quả đầu vào gốc và đầu vào đã biến đổi; hữu ích khi không có đáp án trực tiếp cho mọi ca.

**Câu 2.** Đổi thứ tự hai đoạn có đổi tập giao không?

**Đáp án:** Không, vì S1∩S2=S2∩S1.

**Câu 3.** Đảo A,B thành B,A làm orientation thay đổi thế nào?

**Đáp án:** Đổi dấu; nhưng bản thân đoạn AB và BA là cùng tập điểm.

**Câu 4.** Điều kiện để affine bảo toàn loại giao đoạn NONE/POINT/OVERLAP?

**Đáp án:** det(M)≠0, tức phép affine khả nghịch.

**Câu 5.** Công thức orientation sau affine?

**Đáp án:** orient(TA,TB,TC)=det(M)orient(A,B,C).

**Câu 6.** Vì sao phản xạ đảo dấu orientation?

**Đáp án:** Phản xạ có định thức âm.

**Câu 7.** Tại sao scale2 làm diện tích tăng 4?

**Đáp án:** det([[2,0],[0,2]])=4.

**Câu 8.** Phóng đại ×2 làm bình phương khoảng cách tăng bao nhiêu?

**Đáp án:** Bốn lần, vì d'²=s²d².

**Câu 9.** Shear x'=x+y làm d²((0,0),(1,1)) thành bao nhiêu?

**Đáp án:** 5, từ điểm mới (2,1), so với 2 ban đầu.

**Câu 10.** Khi kiểm thử hull qua phản xạ nên so gì?

**Đáp án:** Tập các đỉnh cực biên sau biến đổi, không so thô danh sách theo chỉ số.

**Câu 11.** Vì sao sinh điểm đồng tuyến có chủ đích?

**Đáp án:** Vì random độc lập có thể ít đụng nhánh suy biến khó.

**Câu 12.** Phép chiếu (x,y)→(x,0) có bảo toàn loại giao đoạn không?

**Đáp án:** Không; hai đoạn song song rời nhau có thể thành hai đoạn trùng nhau.

**Câu 13.** BigInteger giúp gì khi kiểm tra orientation tọa độ long?

**Đáp án:** Tránh tràn ở hiệu và tích tọa độ trước khi lấy dấu.

**Câu 14.** Điều kiện để squared distance giữ nguyên qua tuyến tính M?

**Đáp án:** MᵀM=I.

**Câu 15.** Oracle tham số khác giao đoạn dựa trên bốn orientation ở điểm nào?

**Đáp án:** Nó kiểm tra t,u∈[0,1] của giao hai đường thẳng bằng phân số nguyên, thay vì so vị trí các đầu mút ở hai phía.

**Câu 16.** Dùng Java assert mà không có -ea có rủi ro gì?

**Đáp án:** Assertion có thể bị tắt, test báo hoàn thành dù không kiểm tra điều kiện.

**Câu 17.** Tại sao seed ngẫu nhiên cố định hữu ích?

**Đáp án:** Tái hiện chính xác ca lỗi, sau đó có thể rút gọn và lưu regression test.

**Câu 18.** Vượt 2.500 bộ test có chứng minh đúng cho mọi đầu vào không?

**Đáp án:** Không. Cần chứng minh các quan hệ và dùng test/oracle như bằng chứng bổ sung.

**Tóm tắt:** Thiết kế kiểm thử hình học bằng **đối xứng, phép affine khả nghịch và quy luật định thức**. Giao đoạn, điểm thuộc đoạn và tập cực đỉnh hull được bảo toàn theo cách thích hợp; orientation và diện tích có hướng **nhân det(M)**; khoảng cách chỉ giữ nguyên dưới đẳng cự hoặc biến đổi theo s² với phép tỉ lệ đều. Muốn test đáng tin, hãy dùng **tọa độ nguyên tính bằng BigInteger**, ca đồng tuyến/suy biến có chủ đích, seed cố định, oracle tham số và phản ví dụ cho giả thiết không đúng.
