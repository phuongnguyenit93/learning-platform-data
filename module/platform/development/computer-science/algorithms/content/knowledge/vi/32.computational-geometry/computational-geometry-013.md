# Tính chính xác của phép kiểm tra và lựa chọn số nguyên hay số thực

Trong **hình học tính toán**, nhiều câu hỏi cần một quyết định **đúng hoặc sai tuyệt đối**: ba điểm rẽ trái hay rẽ phải, hai đoạn thẳng có giao nhau không, điểm nằm trên cạnh hay ở trong đa giác, một điểm có phải đỉnh bao lồi hay không. Các quyết định này thường được gọi là **geometric predicates**. Chúng khác với các phép đo xấp xỉ như độ dài Euclid, góc và chu vi. Một sai số rất nhỏ trong tích có hướng có thể đổi dấu một predicate, khiến cả thuật toán hình học bị sai cấu trúc.

Bài thuộc nhóm **Hình học tính toán** trong Computer Science Algorithms. Ta học cách chọn `int`, `long`, `BigInteger`, `double`, `BigDecimal` hoặc **phân số hữu tỉ**; chứng minh cận tràn số; nhận diện sai số làm tròn IEEE-754; cài **orientation, on-segment, giao đoạn, diện tích shoelace, convex hull, point-in-polygon và tọa độ giao hữu tỉ**; giải thích khi nào `EPS` là heuristic nguy hiểm và khi nào cần **robust/adaptive predicates**.

Chương trình Java 17 ở cuối dùng **BigInteger cho mọi quyết định chính xác trên tọa độ signed long**, có ví dụ phản chứng cho double và các phép đối chiếu độc lập trên **77.932 trường hợp**.

## 1. Predicate hay phép đo?

Một **predicate hình học** trả kết quả rời rạc:
- `orientation(A,B,C)`: dương (rẽ trái), âm (rẽ phải), không (thẳng hàng).
- `onSegment(A,B,P)`: P thuộc **đoạn đóng** AB.
- `segmentsIntersect(A,B,C,D)`: hai đoạn có ít nhất một điểm chung, **bao gồm chạm đầu và chồng lấn**.
- `pointInPolygon(P)`: `INSIDE`, `BOUNDARY` hay `OUTSIDE`.
- `inCircle(A,B,C,D)` trong Delaunay: D nằm trong/ngoài/trên đường tròn, phụ thuộc chiều định hướng của ba điểm đầu.

**Phép đo** trả số lượng, chẳng hạn khoảng cách, góc, tọa độ giao hoặc diện tích. Đôi khi chỉ cần in 6 chữ số thập phân nên số thực đủ; nhưng khi dùng phép đo để quyết định **thứ tự chính xác**, có thể so giá trị bình phương dưới số học nguyên thay vì tính căn gần đúng.

| Yêu cầu | Cách tiếp cận phù hợp khi đầu vào nguyên |
| --- | --- |
| Xác định trái/phải/thẳng hàng | Tích chéo **nguyên chính xác** |
| Điểm trên cạnh, giao đoạn | Định hướng + kiểm tra khoảng đóng |
| So sánh khoảng cách | **Bình phương khoảng cách**, không cần sqrt |
| Diện tích đa giác | **Hai lần diện tích** nguyên chính xác |
| Convex hull | Sort có thứ tự chặt + orientation exact |
| Giao hai đường thẳng | Tọa độ có thể là **phân số** |
| In khoảng cách, góc, chu vi | Double có kiểm soát yêu cầu sai số |

**Quy tắc:** chọn kiểu theo **giá trị trung gian có thể xuất hiện**, không chỉ theo kiểu của tọa độ đầu vào.

## 2. Định hướng ba điểm bằng tích có hướng

Với A=(aₓ,aᵧ), B=(bₓ,bᵧ), C=(cₓ,cᵧ), đặt:

\[
\boxed{
D(A,B,C)=(b_x-a_x)(c_y-a_y)
-(b_y-a_y)(c_x-a_x).
}
\]

D là **tích có hướng** của vector B−A và C−A; cũng là **hai lần diện tích có hướng** của tam giác ABC.

- `D>0`: A→B→C **ngược chiều kim đồng hồ (CCW)**, C ở **bên trái** tia A→B.
- `D<0`: rẽ phải, theo chiều kim đồng hồ.
- `D=0`: thẳng hàng, kể cả khi có hai điểm trùng nhau.

Ví dụ:

~~~text
A=(0,0), B=(4,0), C=(2,3)
D(A,B,C) = 4*3 - 0*2 = 12     LEFT
D(A,C,B) = 2*0 - 3*4 = -12   RIGHT
D(A,B,(2,0)) = 0             COLLINEAR
~~~

Không được đảo thứ tự tham số tùy tiện: đổi B,C đổi dấu. Nhiều thuật toán như Andrew convex hull, segment intersection, ray casting và polygon clipping dựa vào **dấu**, nên kết quả rất nhạy với overflow/rounding.

## 3. Vì sao phép tính với long vẫn có thể sai?

`int` có 32 bit, `long` có 64 bit signed, nhưng **tích của hai hiệu tọa độ** có thể rộng hơn nhiều.

### A. Tràn khi nhân

~~~text
A=(0,0)
B=(4000000000,0)
C=(0,4000000000)

D exact = 4000000000 * 4000000000
        = 16000000000000000000
~~~

`Long.MAX_VALUE=9223372036854775807`. Tích chính xác trên **lớn hơn giới hạn long**, nên biểu thức `(b.x-a.x)*(c.y-a.y)` bằng `long` có thể tràn thành số âm. Một phép rẽ **trái** có thể bị nhận nhầm thành **rẽ phải**.

### B. Tràn ngay khi trừ

~~~text
A=(Long.MIN_VALUE,0)
B=(Long.MAX_VALUE,0)
C=(0,1)

B.x - A.x = 18446744073709551615
D exact   = 18446744073709551615
~~~

Hiệu toán học đã vượt long. Nếu viết `BigInteger.valueOf(b.x-a.x)`, phép trừ đã tràn **trước** khi chuyển kiểu, nên BigInteger chỉ nhận một kết quả sai.

Cách làm đúng:

~~~java
BigInteger dx = BigInteger.valueOf(b.x())
        .subtract(BigInteger.valueOf(a.x()));
~~~

Phải **chuyển từng toán hạng gốc** rồi mới trừ/nhân/cộng.

### C. Cận chứng minh long đủ

Nếu mọi tọa độ đều thỏa `|x|,|y|≤B`, mỗi hiệu có trị tuyệt đối tối đa 2B, nên:

\[
|D|\le |dx_1dy_2|+|dy_1dx_2|\le 8B^2.
\]

Nếu `8B²≤Long.MAX_VALUE`, đây là **điều kiện đủ bảo thủ** để tính một D bằng long (với mọi hiệu/tích đã được thực hiện dưới kiểu long). Với B=10^9, `8×10^{18}<9.22×10^{18}`, long có thể đủ cho một cross. Nhưng với B=2×10^9, cận `32×10^{18}` đã vượt long.

Cận cho một orientation **không tự bảo đảm** tổng diện tích shoelace qua hàng nghìn cạnh vẫn vừa long. Với độ lớn bất kỳ trong signed long, chương trình chọn BigInteger để không cần giả định thêm.

`Math.subtractExact`, `Math.multiplyExact` giúp **phát hiện** overflow trong fast path long; nếu cần tốc độ cao, có thể dùng long có kiểm tra rồi fallback BigInteger, thay vì âm thầm để tràn.

## 4. Bình phương khoảng cách và các phép đo

Khoảng cách Euclid giữa A và B là:

\[
\sqrt{(b_x-a_x)^2+(b_y-a_y)^2}.
\]

Nếu chỉ so hai khoảng cách, **so bình phương**:

\[
\boxed{D^2(A,B)=(b_x-a_x)^2+(b_y-a_y)^2.}
\]

Căn bậc hai là hàm tăng trên số không âm, nên so D² cho cùng thứ tự mà không cần sai số sqrt.

Ví dụ A=(0,0), B=(4×10^9,4×10^9):

~~~text
D² = (4000000000)^2 + (4000000000)^2
   = 32000000000000000000 (> Long.MAX_VALUE)
~~~

Trong bài, cả các phép trừ, bình phương và cộng đều được làm bằng BigInteger. Nếu yêu cầu **in khoảng cách với độ chính xác thập phân cho phép**, có thể dùng `Math.hypot` trên dữ liệu double; đây là **phép đo xấp xỉ**, khác với so sánh thứ tự exact.

Tương tự, để kiểm tra P thuộc đường tròn có tâm nguyên O và bán kính nguyên r, có thể so `D²(O,P)≤r²` bằng BigInteger. Nhưng nếu bán kính/tâm là phân số hoặc bài cần dấu định thức `inCircle` trong Delaunay, phải thiết kế predicate và bound riêng.

## 5. Điểm nằm trên đoạn AB

Ba điểm thẳng hàng **chưa đủ** để P thuộc đoạn hữu hạn AB. Cần:

\[
D(A,B,P)=0
\]

và:

\[
\min(a_x,b_x)\le p_x\le\max(a_x,b_x),\quad
\min(a_y,b_y)\le p_y\le\max(a_y,b_y).
\]

Ví dụ AB=(0,0)–(4,0):
- P=(2,0): nằm trên đoạn.
- P=(7,0): thẳng hàng nhưng **ngoài** đoạn.
- P=(4,0): trùng đầu mút, vẫn nằm trên đoạn.

**Trường hợp suy biến A=B:** đoạn chỉ có **một điểm**. Cross(A,B,P) luôn bằng 0, nhưng hai khoảng x,y suy biến buộc P=A. Vì thế công thức trên xử lý được cả đoạn độ dài 0.

Không cần dùng phép đo `|AP|+|PB|≈|AB|` với EPS cho tọa độ nguyên: cách đó thêm căn bậc hai và sai số mà không có ích.

## 6. Giao hai đoạn thẳng, kể cả đầu mút và chồng lấn

Xét AB và CD, tính:

\[
o_1=D(A,B,C),\quad o_2=D(A,B,D),
\quad o_3=D(C,D,A),\quad o_4=D(C,D,B).
\]

Nếu `o₁,o₂` **trái dấu nghiêm ngặt** và `o₃,o₄` trái dấu nghiêm ngặt thì hai đoạn **cắt nhau tại nội bộ**, không phải chỉ tại đầu mút.

Nhưng phải kiểm tra riêng các trường hợp bằng 0:
- o₁=0 và **C nằm trên AB**;
- o₂=0 và **D nằm trên AB**;
- o₃=0 và **A nằm trên CD**;
- o₄=0 và **B nằm trên CD**.

Bất kỳ điều kiện nào đúng thì hai đoạn giao. Nếu không có và không có cắt nghiêm ngặt, kết luận không giao.

| AB | CD | Giao? |
| --- | --- | --- |
| (0,0)–(4,0) | (2,−2)–(2,2) | Có, giao cắt |
| (0,0)–(4,0) | (4,0)–(5,5) | Có, chạm đầu mút |
| (0,0)–(4,0) | (2,0)–(6,0) | Có, chồng lấn |
| (0,0)–(2,0) | (3,0)–(4,0) | Không, thẳng hàng rời |
| (2,0)–(2,0) | (0,0)–(4,0) | Có, đoạn suy biến nằm trên đoạn kia |
| (2,1)–(2,1) | (0,0)–(4,0) | Không |

**Phản ví dụ quan trọng:** bốn orientation có thể đều bằng 0 khi AB,CD **thẳng hàng nhưng rời nhau**. Nếu chỉ kiểm tra `o₁×o₂≤0` và `o₃×o₄≤0` mà không kiểm tra **khoảng đóng**, sẽ kết luận sai.

Nên kiểm tra dấu bằng `signum()` thay vì nhân hai BigInteger chỉ để biết chúng trái dấu; vừa đơn giản vừa tránh phép nhân không cần thiết.

## 7. Nếu cần tọa độ giao, phải xét phân số

Tọa độ nguyên không bảo đảm giao điểm đường thẳng là số nguyên. Cho:

\[
A+t(B-A)=C+u(D-C).
\]

Đặt `r=B−A`, `s=D−C`, `q=C−A`. Nếu hai đường thẳng không song song (`den=cross(r,s)≠0`):

\[
\boxed{t=\frac{cross(q,s)}{cross(r,s)},\qquad I=A+t\,r.}
\]

Tọa độ I là phân số của các định thức nguyên. Ta có thể lưu **tử và mẫu BigInteger**, chuyển mẫu về dương, chia `gcd` để tối giản, không cần ép sang double.

Ví dụ:

~~~text
AB: (0,0)–(3,2)
CD: (0,2)–(3,0)

Giao hai đường thẳng: (3/2,1)
~~~

Nếu `den=0`, hai đường thẳng **song song phân biệt hoặc trùng nhau** nên không có **một giao điểm duy nhất**. Hàm trả `null` trong cả hai trường hợp và nêu rõ hợp đồng.

Giao của hai **đường thẳng vô hạn** khác với giao của hai **đoạn hữu hạn**. Khi den khác 0, muốn biết giao điểm thuộc cả hai đoạn thì phải kiểm tra `t,u∈[0,1]` (so tử/mẫu chính xác) hoặc gọi predicate giao đoạn. Khi các đoạn thẳng hàng, phần giao có thể rỗng, một điểm hoặc cả đoạn.

## 8. Diện tích đa giác theo công thức shoelace

Với các đỉnh theo thứ tự biên `P_0,...,P_{h-1}` và `P_h=P_0`, diện tích **có hướng gấp đôi**:

\[
\boxed{2S_{\rm signed}=
\sum_{i=0}^{h-1}(x_i y_{i+1}-y_i x_{i+1}).}
\]

- Các đỉnh theo CCW: `2S_signed>0`.
- Theo CW: `2S_signed<0`.
- Diện tích hình học là `|2S_signed|/2`; với tọa độ nguyên, hai lần diện tích là **số nguyên chính xác**.

Ví dụ rectangle `[(0,0),(4,0),(4,3),(0,3)]` có `2S=24`, diện tích 12. Đảo chiều thứ tự đỉnh được `2S=−24`.

Dùng BigInteger cho từng tích và **tổng**, vì polygon có nhiều cạnh có thể tràn long ở tổng ngay cả khi một tích vẫn vừa long. Nếu `|2S|` lẻ, có thể in diện tích chính xác dạng `|2S|/2` hoặc biểu diễn số nguyên kèm `.5`.

Cần phân biệt đa giác **đơn** với đa giác tự cắt: shoelace cho diện tích có hướng đại số, không mặc nhiên bằng diện tích hợp các vùng theo mọi quy tắc tô màu.

## 9. Bao lồi Andrew monotone chain

**Convex hull** là bao lồi nhỏ nhất chứa toàn bộ tập điểm. Cách xây monotone chain:

1. Sort tăng theo x rồi y; dùng `Long.compare` hoặc comparator `comparingLong`, không lấy `(int)(a.x-b.x)`.
2. Xóa điểm trùng tọa độ.
3. Xây **lower hull** khi đi từ trái sang phải.
4. Xây **upper hull** khi đi ngược.
5. Khi ba điểm cuối cho `orientation≤0`, bỏ điểm giữa (không tạo rẽ trái nghiêm ngặt).
6. Bỏ hai đầu mút lặp rồi ghép lower và upper.

Cách dùng `≤0` **loại các điểm thẳng hàng nằm giữa trên biên**, chỉ giữ **đỉnh cực trị**. Nếu đề yêu cầu giữ **mọi điểm trên cạnh hull**, phải thay chính sách và xử lý riêng trường hợp tất cả thẳng hàng.

Ví dụ:

~~~text
Tập đầu vào:
[(0,0),(4,0),(4,3),(0,3),(2,2),(4,0)]

Bao lồi CCW:
[(0,0),(4,0),(4,3),(0,3)]
~~~

Nếu đầu vào rỗng, hull rỗng; một điểm cho hull một điểm; tập toàn điểm thẳng hàng có ít nhất hai vị trí phân biệt cho **hai đầu cực trị**.

Độ phức tạp: `O(h log h)` phép so sánh để sort h điểm, sau đó `O(h)` lời gọi orientation amortized; bộ nhớ `O(h)`. Một orientation sai dấu do overflow/double có thể bỏ nhầm một điểm cực trị, không còn là một “sai số diện tích nhỏ”.

## 10. Điểm trong đa giác: ray casting với boundary chính xác

Cho một **đa giác đơn** không tự cắt, các đỉnh xếp quanh biên, không lặp đỉnh đầu ở cuối. Ta phân loại điểm P:
- `BOUNDARY` nếu P nằm trên một cạnh (dùng `onSegment`).
- `INSIDE` nếu tia từ P sang phải cắt biên số lần **lẻ**.
- `OUTSIDE` nếu cắt số lần **chẵn**.

**Tránh đếm đôi một đỉnh:** xét cạnh A→B cắt đường ngang tại y=P.y khi:

~~~text
(A.y > P.y) != (B.y > P.y)
~~~

Đây là **quy tắc nửa mở theo y**. Cạnh nằm ngang không vượt qua đường ngang theo quy tắc ấy, nhưng điểm thuộc cạnh đã được xử lý bởi onSegment.

Với cạnh vượt qua đường ngang, không cần tính hoành độ giao bằng double. Đặt `o=D(A,B,P)`:
- Nếu cạnh đi lên (`B.y>A.y`), giao tia nằm **bên phải P** khi o>0.
- Nếu đi xuống (`B.y<A.y`), giao tia bên phải khi o<0.

Khi đúng, đảo boolean inside.

Ví dụ:

~~~text
Rectangle=[(0,0),(4,0),(4,3),(0,3)]
P=(2,2): INSIDE
P=(4,1): BOUNDARY
P=(5,1): OUTSIDE
~~~

Mã có oracle **winding number** độc lập để đối chiếu với ray casting trên đa giác đơn. Với đa giác tự cắt, parity và winding number có thể định nghĩa vùng trong khác nhau; không được giả định hai phương pháp luôn tương đương nếu phá hợp đồng đầu vào.

## 11. Sai số double và vấn đề EPS

Java `double` là binary64, có **53 bit độ chính xác phần trị**, còn khoảng cách giữa hai giá trị có thể biểu diễn (*ULP*) tăng theo độ lớn. Không phải mọi số nguyên lớn đều có biểu diễn double chính xác.

### Ví dụ double đánh mất cả dấu định hướng

Xét các điểm **nguyên chính xác**:

~~~text
A=(0,0)
B=(1000000000000000000,1000000000000000000)
C=(1000000000000000001,1000000000000000002)

Cross exact = 1000000000000000000  (>0)
Cross double sau ép tọa độ = 0.0
~~~

`10^18+1` và `10^18+2` đều quá gần `10^18` so với bước ULP tại miền này nên có thể được lưu bằng cùng một giá trị double. Thông tin đã mất **trước** phép cross; giảm EPS không thể khôi phục dấu dương từ kết quả 0.0.

### Một EPS tuyệt đối có thể quá lớn hoặc quá nhỏ

Nhiều mã viết:

~~~text
if (abs(cross) < 1e-9) return COLLINEAR;
else return sign(cross);
~~~

Nhưng cross có đơn vị **tọa độ bình phương**; khi nhân thang tọa độ với k, cross nhân k². Với:

~~~text
A=(0,0)
B=(1e-12,0)
C=(0,1e-12)

Cross toán học = 1e-24 > 0
EPS = 1e-9 => coi nhầm là COLLINEAR
~~~

Ở hình lớn, ngược lại, sai số tuyệt đối của hiệu hai tích lớn có thể vượt 1e-9 mà vẫn rất nhỏ theo tỉ lệ dữ liệu; một EPS cố định không phản ánh điều kiện số.

**Điều đúng:** nếu có **cận sai số đã chứng minh** cho phép tính double, và trị tuyệt đối định thức tính được lớn hơn cận ấy, ta có thể chứng nhận dấu. Nếu không chắc chắn, cần fallback độ chính xác cao hơn. Một heuristic kiểu `eps*(|dx1*dy2|+|dy1*dx2|)` chỉ có ý nghĩa **chứng nhận** khi hệ số eps thực sự được xây từ phân tích sai số của phép toán và mô hình floating-point.

### EPS có thể phá Comparator

Quan hệ “a≈b nếu |a−b|<EPS” **không bắc cầu**. Có thể a≈b, b≈c nhưng a không gần c. Nếu comparator trong sort trả 0 khi hai tọa độ cách nhau dưới EPS, nó có thể vi phạm hợp đồng thứ tự, làm sai sort/sweep line hoặc khiến Java sort phát sinh lỗi comparator bất nhất.

Trong code:
- Sort tọa độ nguyên bằng `Long.compare` / `Comparator.comparingLong`.
- Sort tọa độ double hữu hạn bằng `Double.compare` với thứ tự nhất quán.
- Nếu muốn **gom điểm gần nhau theo ngưỡng**, cần quy tắc clustering riêng, không biến “gần” thành “bằng” của comparator.

### NaN, Infinity và −0.0

Số thực có NaN, ±Infinity và ±0.0. Một predicate kiểu `det>eps` hoặc `det<−eps` sẽ đều false khi det là NaN, dễ vô tình trả “thẳng hàng”. Với thuật toán yêu cầu tọa độ hữu hạn, nên kiểm tra `Double.isFinite` và có chính sách từ chối hay xử lý cụ thể. Đừng mặc định phép so float có đầy đủ tính chất thứ tự của số thực toán học.

## 12. Khi nào chọn int, long, BigInteger, BigDecimal hoặc Rational?

| Kiểu | Lợi ích | Cảnh báo chính |
| --- | --- | --- |
| `int` | Nhẹ, nhanh, tọa độ nhỏ | Hiệu/tích thường tràn int |
| `long` | Nhiều bài có bound có thể dùng an toàn | Phải chứng minh cả hiệu, tích **và tổng** |
| `BigInteger` | Exact trên tọa độ nguyên signed long và các trung gian rất lớn | Có overhead và chi phí nhân số lớn |
| `double` | Phù hợp đo gần đúng, sqrt, góc và đầu vào đo đạc | Có ULP, cancellation, NaN; predicate gần zero khó |
| `BigDecimal(String)` | Giữ chính xác chuỗi thập phân hữu hạn | Không tự phục hồi số gốc nếu đã ép double |
| `Rational(BigInteger)` | Tọa độ giao hữu tỉ **chính xác** | Phải tối giản, so bằng nhân chéo/chung mẫu an toàn |

**Chọn theo nguồn dữ liệu:**
- Tọa độ **nguyên exact**, chỉ cần predicate: ưu tiên long sau chứng minh bound, hoặc BigInteger.
- Tọa độ từ **chuỗi thập phân hữu hạn** như "0.125": đọc `new BigDecimal("0.125")`, quy về cùng scale nguyên hoặc Rational, rồi tính exact.
- Tọa độ đã ở dạng **double**: nếu cần predicate chắc chắn của **giá trị binary64 đang lưu**, có thể dùng **robust/adaptive exact predicates** (chẳng hạn thuật toán định hướng thích nghi) để bảo đảm dấu của định thức từ các số binary64. `BigDecimal.valueOf(double)` dùng chuỗi thập phân biểu diễn giá trị double, không phải công cụ khôi phục tọa độ thật trước khi nó bị làm tròn.
- Đầu ra chỉ cần **khoảng cách/góc xấp xỉ**: `Math.hypot`, `Math.atan2` có thể thích hợp theo sai số bài.

Tối ưu thực tế có thể kết hợp **fast path long với `Math.*Exact`** rồi chuyển BigInteger khi vượt cận; nhưng phải chắc rằng không có phép tính long âm thầm tràn trước khi điều kiện fallback được đánh giá.

## 13. Java 17: chương trình hình học exact và kiểm thử

File **GeometryPrecisionDemo.java** là một chương trình chạy độc lập. Mã có:
- `Pt(long x,long y)`, `orientation` BigInteger, `distanceSquared`;
- `onSegment`, `segmentsIntersect`, `lineIntersection` trả Rational;
- `twiceSignedArea`, `convexHull` Andrew, `pointInPolygon` exact;
- `orientationDouble` và `fixedEpsSign` để minh họa trường hợp **không robust**;
- Ba oracle: định thức khai triển, giao đoạn bằng **hệ phương trình hữu tỉ**, và point-in-polygon bằng **winding number**.
- Bộ kiểm thử xác định có lưới 4×4, đoạn suy biến và tọa độ signed long cực trị.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class GeometryPrecisionDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;

    record Pt(long x, long y) {
        @Override public String toString() {
            return "(" + x + "," + y + ")";
        }
    }
    record DoublePt(double x, double y) {}
    enum Location { INSIDE, BOUNDARY, OUTSIDE }

    static BigInteger bi(long x) {
        return BigInteger.valueOf(x);
    }
    // Ep hai toa do rieng truoc khi tru.
    static BigInteger diff(long a, long b) {
        return bi(a).subtract(bi(b));
    }
    static BigInteger crossVec(
            BigInteger ax, BigInteger ay,
            BigInteger bx, BigInteger by) {
        return ax.multiply(by).subtract(ay.multiply(bx));
    }
    // Exact cho toan bo mien toa do signed long.
    static BigInteger orientation(Pt a, Pt b, Pt c) {
        return crossVec(
                diff(b.x(), a.x()), diff(b.y(), a.y()),
                diff(c.x(), a.x()), diff(c.y(), a.y()));
    }
    // Oracle theo cong thuc dinh thuc khai trien.
    static BigInteger orientationOracle(Pt a, Pt b, Pt c) {
        return bi(a.x()).multiply(diff(b.y(), c.y()))
                .add(bi(b.x()).multiply(diff(c.y(), a.y())))
                .add(bi(c.x()).multiply(diff(a.y(), b.y())));
    }
    static BigInteger distanceSquared(Pt a, Pt b) {
        BigInteger dx = diff(b.x(), a.x());
        BigInteger dy = diff(b.y(), a.y());
        return dx.multiply(dx).add(dy.multiply(dy));
    }
    static boolean between(long a, long x, long b) {
        return Math.min(a, b) <= x
                && x <= Math.max(a, b);
    }
    static boolean onSegment(Pt a, Pt b, Pt p) {
        return orientation(a,b,p).signum() == 0
                && between(a.x(), p.x(), b.x())
                && between(a.y(), p.y(), b.y());
    }
    static boolean opposite(BigInteger x, BigInteger y) {
        return x.signum() * y.signum() < 0;
    }
    // Giao bao gom cham dau mut, overlap va doan suy bien.
    static boolean segmentsIntersect(
            Pt a, Pt b, Pt c, Pt d) {
        BigInteger o1 = orientation(a,b,c);
        BigInteger o2 = orientation(a,b,d);
        BigInteger o3 = orientation(c,d,a);
        BigInteger o4 = orientation(c,d,b);
        if (o1.signum()==0 && onSegment(a,b,c)) return true;
        if (o2.signum()==0 && onSegment(a,b,d)) return true;
        if (o3.signum()==0 && onSegment(c,d,a)) return true;
        if (o4.signum()==0 && onSegment(c,d,b)) return true;
        return opposite(o1,o2) && opposite(o3,o4);
    }

    // Oracle khac: A+t(B-A)=C+u(D-C), 0<=t,u<=1.
    static boolean segmentOracle(Pt a, Pt b, Pt c, Pt d) {
        if (a.equals(b)) return onSegment(c,d,a);
        if (c.equals(d)) return onSegment(a,b,c);
        BigInteger rx=diff(b.x(),a.x()), ry=diff(b.y(),a.y());
        BigInteger sx=diff(d.x(),c.x()), sy=diff(d.y(),c.y());
        BigInteger qx=diff(c.x(),a.x()), qy=diff(c.y(),a.y());
        BigInteger den=crossVec(rx,ry,sx,sy);

        if (den.signum()==0) {
            if (crossVec(qx,qy,rx,ry).signum()!=0)
                return false;
            // Cung duong: intersection cua 2 projection x/y.
            return Math.max(Math.min(a.x(),b.x()),
                            Math.min(c.x(),d.x()))
                    <= Math.min(Math.max(a.x(),b.x()),
                                Math.max(c.x(),d.x()))
                && Math.max(Math.min(a.y(),b.y()),
                            Math.min(c.y(),d.y()))
                    <= Math.min(Math.max(a.y(),b.y()),
                                Math.max(c.y(),d.y()));
        }
        BigInteger t=crossVec(qx,qy,sx,sy);
        BigInteger u=crossVec(qx,qy,rx,ry);
        if (den.signum()<0) {
            den=den.negate(); t=t.negate(); u=u.negate();
        }
        return t.signum()>=0 && t.compareTo(den)<=0
                && u.signum()>=0 && u.compareTo(den)<=0;
    }

    // Phan so mau duong, toi gian.
    record Fraction(BigInteger num, BigInteger den) {
        Fraction {
            if (den.signum()==0)
                throw new ArithmeticException("Zero denominator");
            if (den.signum()<0) {
                num=num.negate(); den=den.negate();
            }
            BigInteger g=num.gcd(den);
            num=num.divide(g); den=den.divide(g);
        }
        @Override public String toString() {
            return den.equals(ONE)
                    ? num.toString() : num+"/"+den;
        }
    }
    record RationalPt(Fraction x, Fraction y) {
        @Override public String toString() {
            return "("+x+","+y+")";
        }
    }
    // Giao DUONG THANG vo han, null neu khong don nhat.
    static RationalPt lineIntersection(
            Pt a, Pt b, Pt c, Pt d) {
        BigInteger rx=diff(b.x(),a.x()), ry=diff(b.y(),a.y());
        BigInteger sx=diff(d.x(),c.x()), sy=diff(d.y(),c.y());
        BigInteger qx=diff(c.x(),a.x()), qy=diff(c.y(),a.y());
        BigInteger den=crossVec(rx,ry,sx,sy);
        if (den.signum()==0) return null;
        BigInteger tNum=crossVec(qx,qy,sx,sy);
        BigInteger xNum=bi(a.x()).multiply(den)
                .add(rx.multiply(tNum));
        BigInteger yNum=bi(a.y()).multiply(den)
                .add(ry.multiply(tNum));
        return new RationalPt(
                new Fraction(xNum,den),
                new Fraction(yNum,den));
    }
    static BigInteger twiceSignedArea(List<Pt> poly) {
        BigInteger sum=ZERO;
        for (int i=0; i<poly.size(); i++) {
            Pt a=poly.get(i);
            Pt b=poly.get((i+1)%poly.size());
            sum=sum.add(bi(a.x()).multiply(bi(b.y()))
                    .subtract(bi(a.y()).multiply(bi(b.x()))));
        }
        return sum;
    }

    static void appendHull(List<Pt> chain, Pt p) {
        while (chain.size()>=2
                && orientation(chain.get(chain.size()-2),
                    chain.get(chain.size()-1),p).signum()<=0)
            chain.remove(chain.size()-1);
        chain.add(p);
    }
    // Hull CCW, bo duplicate va collinear o giua.
    static List<Pt> convexHull(List<Pt> input) {
        List<Pt> sorted=new ArrayList<>(input);
        sorted.sort(Comparator.comparingLong(Pt::x)
                .thenComparingLong(Pt::y));
        List<Pt> unique=new ArrayList<>();
        for (Pt p:sorted)
            if (unique.isEmpty()
                    || !unique.get(unique.size()-1).equals(p))
                unique.add(p);
        if (unique.size()<=1) return unique;

        List<Pt> lower=new ArrayList<>();
        List<Pt> upper=new ArrayList<>();
        for (Pt p:unique) appendHull(lower,p);
        for (int i=unique.size()-1;i>=0;i--)
            appendHull(upper,unique.get(i));
        lower.remove(lower.size()-1);
        upper.remove(upper.size()-1);
        lower.addAll(upper);
        return lower;
    }

    // Da giac DON, khong lap dinh dau o cuoi.
    static Location pointInPolygon(List<Pt> poly, Pt p) {
        if (poly.size()<3)
            throw new IllegalArgumentException(
                    "Need simple polygon with >=3 vertices");
        boolean inside=false;
        for (int i=0;i<poly.size();i++) {
            Pt a=poly.get(i), b=poly.get((i+1)%poly.size());
            if (onSegment(a,b,p)) return Location.BOUNDARY;

            if ((a.y()>p.y()) != (b.y()>p.y())) {
                int s=orientation(a,b,p).signum();
                boolean right=b.y()>a.y() ? s>0 : s<0;
                if (right) inside=!inside;
            }
        }
        return inside?Location.INSIDE:Location.OUTSIDE;
    }
    // Oracle PIP dung winding number thay parity.
    static Location polygonOracle(List<Pt> poly, Pt p) {
        int winding=0;
        for (int i=0;i<poly.size();i++) {
            Pt a=poly.get(i), b=poly.get((i+1)%poly.size());
            if (onSegment(a,b,p)) return Location.BOUNDARY;
            int s=orientation(a,b,p).signum();
            if (a.y()<=p.y()) {
                if (b.y()>p.y() && s>0) winding++;
            } else {
                if (b.y()<=p.y() && s<0) winding--;
            }
        }
        return winding==0?Location.OUTSIDE:Location.INSIDE;
    }

    // KHONG robust: chi minh hoa mat precision double.
    static double orientationDouble(
            DoublePt a, DoublePt b, DoublePt c) {
        return (b.x()-a.x())*(c.y()-a.y())
                -(b.y()-a.y())*(c.x()-a.x());
    }
    static int fixedEpsSign(double det, double eps) {
        if (!Double.isFinite(det) || !Double.isFinite(eps)
                || eps<0)
            throw new IllegalArgumentException(
                    "Finite det/epsilon required");
        return det>eps ? 1 : det<-eps ? -1 : 0;
    }

    static int seed=4302026;
    static long nextUnsigned32() {
        seed=seed*1664525+1013904223;
        return Integer.toUnsignedLong(seed);
    }
    static long randomCoordinate() {
        int kind=(int)(nextUnsigned32()%6L);
        return switch(kind) {
            case 0 -> Long.MAX_VALUE;
            case 1 -> Long.MIN_VALUE;
            case 2 -> 1_000_000_000_000_000_000L;
            case 3 -> -1_000_000_000_000_000_000L;
            default -> nextUnsigned32()%2_000_001L
                    -1_000_000L;
        };
    }
    static Pt randomPoint() {
        return new Pt(randomCoordinate(),randomCoordinate());
    }
    record Stats(int orient, int segments, int polygons,
                 int randomOrient, int randomSegments) {
        int total() {
            return orient+segments+polygons
                    +randomOrient+randomSegments;
        }
    }

    static Stats verify() {
        List<Pt> grid=new ArrayList<>();
        for (long x=-1;x<=2;x++)
            for (long y=-1;y<=2;y++)
                grid.add(new Pt(x,y));

        int orient=0, segments=0;
        for (Pt a:grid) for (Pt b:grid) for (Pt c:grid) {
            if (!orientation(a,b,c).equals(
                    orientationOracle(a,b,c)))
                throw new AssertionError("Orientation mismatch");
            orient++;
        }
        for (Pt a:grid) for (Pt b:grid)
            for (Pt c:grid) for (Pt d:grid) {
                if (segmentsIntersect(a,b,c,d)
                        != segmentOracle(a,b,c,d))
                    throw new AssertionError("Segment mismatch");
                segments++;
            }

        List<Pt> rectangle=List.of(
                new Pt(0,0),new Pt(4,0),
                new Pt(4,3),new Pt(0,3));
        List<Pt> concave=List.of(
                new Pt(0,0),new Pt(5,0),new Pt(5,5),
                new Pt(3,2),new Pt(0,5));
        List<Pt> reversed=List.of(
                new Pt(0,3),new Pt(4,3),
                new Pt(4,0),new Pt(0,0));
        int polygons=0;
        for (List<Pt> poly:List.of(
                rectangle,concave,reversed))
            for (long x=-2;x<=7;x++)
                for (long y=-2;y<=7;y++) {
                    Pt p=new Pt(x,y);
                    if (pointInPolygon(poly,p)
                            != polygonOracle(poly,p))
                        throw new AssertionError("Polygon mismatch");
                    polygons++;
                }

        int randomOrient=0, randomSegments=0;
        for (int i=0;i<4000;i++) {
            Pt a=randomPoint(), b=randomPoint();
            Pt c=randomPoint(), d=randomPoint();
            if (!orientation(a,b,c).equals(
                    orientationOracle(a,b,c)))
                throw new AssertionError(
                        "Random orientation mismatch");
            randomOrient++;
            if (segmentsIntersect(a,b,c,d)
                    != segmentOracle(a,b,c,d))
                throw new AssertionError(
                        "Random segment mismatch");
            randomSegments++;
        }
        Stats stats=new Stats(
                orient,segments,polygons,
                randomOrient,randomSegments);
        if (orient!=4096 || segments!=65536
                || polygons!=300 || randomOrient!=4000
                || randomSegments!=4000 || stats.total()!=77932)
            throw new AssertionError("Unexpected test count");
        return stats;
    }

    public static void main(String[] args) {
        Pt zero=new Pt(0,0), right=new Pt(4,0),
                top=new Pt(2,3);
        System.out.println("orientation.left="
                +orientation(zero,right,top));
        System.out.println("orientation.right="
                +orientation(zero,top,right));
        System.out.println("orientation.collinear="
                +orientation(zero,right,new Pt(2,0)));

        System.out.println("orientation.large="
                +orientation(zero,new Pt(4_000_000_000L,0),
                    new Pt(0,4_000_000_000L)));
        System.out.println("orientation.subtractionOverflow="
                +orientation(new Pt(Long.MIN_VALUE,0),
                    new Pt(Long.MAX_VALUE,0),new Pt(0,1)));

        Pt nearB=new Pt(
                1_000_000_000_000_000_000L,
                1_000_000_000_000_000_000L);
        Pt nearC=new Pt(
                1_000_000_000_000_000_001L,
                1_000_000_000_000_000_002L);
        System.out.println("orientation.nearExact="
                +orientation(zero,nearB,nearC));
        System.out.println("orientation.nearDouble="
                +orientationDouble(
                    new DoublePt(0,0),
                    new DoublePt((double)nearB.x(),
                                 (double)nearB.y()),
                    new DoublePt((double)nearC.x(),
                                 (double)nearC.y())));

        double tiny=orientationDouble(
                new DoublePt(0,0),
                new DoublePt(1e-12,0),
                new DoublePt(0,1e-12));
        System.out.println("tiny.doubleDet="+tiny);
        System.out.println("tiny.fixedEpsSign="
                +fixedEpsSign(tiny,1e-9));

        System.out.println("segments.cross="
                +segmentsIntersect(zero,right,
                    new Pt(2,-2),new Pt(2,2)));
        System.out.println("segments.touch="
                +segmentsIntersect(zero,right,
                    right,new Pt(5,5)));
        System.out.println("segments.overlap="
                +segmentsIntersect(zero,right,
                    new Pt(2,0),new Pt(6,0)));
        System.out.println("segments.disjoint="
                +segmentsIntersect(zero,new Pt(2,0),
                    new Pt(3,0),right));
        System.out.println("segments.pointOn="
                +segmentsIntersect(new Pt(2,0),
                    new Pt(2,0),zero,right));
        System.out.println("segments.pointOff="
                +segmentsIntersect(new Pt(2,1),
                    new Pt(2,1),zero,right));

        System.out.println("line.intersection="
                +lineIntersection(zero,new Pt(3,2),
                    new Pt(0,2),new Pt(3,0)));

        List<Pt> rect=List.of(zero,right,
                new Pt(4,3),new Pt(0,3));
        List<Pt> reverse=List.of(
                new Pt(0,3),new Pt(4,3),right,zero);
        System.out.println("polygon.twiceArea="
                +twiceSignedArea(rect));
        System.out.println("polygon.reversedTwiceArea="
                +twiceSignedArea(reverse));
        System.out.println("polygon.inside="
                +pointInPolygon(rect,new Pt(2,2)));
        System.out.println("polygon.boundary="
                +pointInPolygon(rect,new Pt(4,1)));
        System.out.println("polygon.outside="
                +pointInPolygon(rect,new Pt(5,1)));

        List<Pt> input=new ArrayList<>(rect);
        input.add(new Pt(2,2));
        input.add(right);
        System.out.println("hull="+convexHull(input));
        System.out.println("distanceSquared.large="
                +distanceSquared(zero,
                    new Pt(4_000_000_000L,
                           4_000_000_000L)));

        Stats s=verify();
        System.out.println("verified.orientation="+s.orient());
        System.out.println("verified.segments="+s.segments());
        System.out.println("verified.polygon="+s.polygons());
        System.out.println("verified.randomTriples="
                +s.randomOrient());
        System.out.println("verified.randomSegments="
                +s.randomSegments());
        System.out.println("verified.total="+s.total());
    }
}
~~~

Lưu thành tệp **GeometryPrecisionDemo.java**, chạy với **JDK 17 trở lên**:

~~~bash
javac GeometryPrecisionDemo.java
java GeometryPrecisionDemo
~~~

**Đầu ra dự kiến:**

~~~text
orientation.left=12
orientation.right=-12
orientation.collinear=0
orientation.large=16000000000000000000
orientation.subtractionOverflow=18446744073709551615
orientation.nearExact=1000000000000000000
orientation.nearDouble=0.0
tiny.doubleDet=1.0E-24
tiny.fixedEpsSign=0
segments.cross=true
segments.touch=true
segments.overlap=true
segments.disjoint=false
segments.pointOn=true
segments.pointOff=false
line.intersection=(3/2,1)
polygon.twiceArea=24
polygon.reversedTwiceArea=-24
polygon.inside=INSIDE
polygon.boundary=BOUNDARY
polygon.outside=OUTSIDE
hull=[(0,0), (4,0), (4,3), (0,3)]
distanceSquared.large=32000000000000000000
verified.orientation=4096
verified.segments=65536
verified.polygon=300
verified.randomTriples=4000
verified.randomSegments=4000
verified.total=77932
~~~

### Cách hiểu kết quả

`orientation.large` và `orientation.subtractionOverflow` lớn hơn `Long.MAX_VALUE` nhưng BigInteger vẫn trả đúng dấu/giá trị. `orientation.nearExact` là **10^18 dương**, trong khi `orientation.nearDouble=0.0` vì tọa độ bị làm tròn khi ép kiểu. `tiny.doubleDet` dương nhưng `fixedEpsSign=0` cho thấy EPS có thể làm mất một góc thực sự.

Các phép giao đoạn xử lý đúng **giao cắt, chạm đầu mút, chồng lấn, rời thẳng hàng và đoạn suy biến**. Giao hai đường thẳng là phân số `(3/2,1)`. Diện tích gấp đôi của rectangle là `24` hoặc `−24` theo chiều đỉnh. Bao lồi loại điểm (2,2) và bản sao của (4,0). Bình phương khoảng cách lớn vượt signed long.

Bộ kết quả thống kê **không đo hiệu năng**: đây là số ca kiểm thử và đối chiếu, không phải thời gian chạy hoặc chứng chỉ cho mọi input.

## 14. Kiểm thử độc lập 77.932 trường hợp

Để tránh “một thuật toán tự xác nhận chính nó”, bài sử dụng các oracle theo **cách lập luận khác**:
1. **Orientation:** công thức chính dùng `(B−A)×(C−A)`. Oracle dùng dạng khai triển `a_x(b_y−c_y)+b_x(c_y−a_y)+c_x(a_y−b_y)`.
2. **Giao đoạn:** hàm chính xét bốn dấu orientation và onSegment. Oracle giải **hệ tuyến tính tham số hữu tỉ**; nếu song song thì kiểm tra collinear và chồng lấn khoảng chiếu; nếu suy biến thì xét điểm.
3. **Điểm trong polygon:** hàm chính là ray casting **parity**; oracle là **winding number**. Với polygon đơn, cả hai phải khớp.

| Bộ test | Số phép kiểm |
| --- | ---: |
| Mọi bộ ba từ lưới 4×4 gồm 16 điểm | `16^3=4096` |
| Mọi bộ bốn điểm (hai đoạn có thứ tự) từ cùng lưới | `16^4=65536` |
| Ba đa giác đơn, mỗi đa giác 100 vị trí điểm | 300 |
| 4.000 bộ bốn điểm giả ngẫu nhiên, so orientation | 4.000 |
| Cùng 4.000 bộ, so giao đoạn | 4.000 |
| **Tổng** | **77.932** |

Các đoạn được thử có thể **suy biến hoặc trùng nhau**, vì đầu và cuối được chọn độc lập. Các polygon gồm rectangle CCW, rectangle CW và một đa giác lõm. Bộ random có tọa độ `Long.MIN_VALUE`, `Long.MAX_VALUE`, ±10^18 và các giá trị nhỏ; seed cố định để tái tạo được kết quả.

Mô hình định thức exact, kiểm tra đoạn bằng tham số và kiểm tra polygon bằng winding đã được đối chiếu độc lập trên các nhóm này: **không phát hiện sai khác**. Bộ thử hữu hạn không thay thế các chứng minh về định thức, khoảng đóng và số học nguyên chính xác.

### Vì sao phải có test đối kháng?

Nếu chỉ thử tọa độ `0..10`, phép tính `int` hoặc double thiếu an toàn vẫn có thể vượt hàng triệu test. Những ca khó thực sự gồm:
- Số nguyên đầu vào vừa long nhưng tích hai hiệu **không vừa long**.
- Phép **trừ tọa độ** đã tràn trước khi nhân.
- Hai tọa độ nguyên rất gần nhau ở vùng 10^18 bị double coi là một.
- Cross khác 0 nhưng cực nhỏ hơn EPS tuyệt đối tùy chọn.
- Đoạn thẳng hàng rời nhau, chạm đầu mút, chồng lấn hoặc suy biến.
- Đa giác lõm, chiều CW/CCW, điểm chính xác trên cạnh.
- Bao lồi có điểm trùng và điểm thẳng hàng nằm giữa.

Những ca này được chọn để kiểm tra **điều kiện ranh giới** mà chương trình hình học thường mắc lỗi.

## 15. Vì sao các phép kiểm tra exact đúng?

**Orientation:** tích có hướng là định thức cấp hai của B−A và C−A. Dấu của định thức xác định nửa mặt phẳng chính xác. BigInteger bảo toàn mọi phép trừ và nhân trên tọa độ long, nên không thể đổi dấu do overflow hoặc rounding.

**On-segment:** P nằm trên đoạn AB khi và chỉ khi thẳng hàng với A,B và nằm trong cả hai khoảng tọa độ đóng. Công thức vẫn đúng với đoạn suy biến A=B.

**Segment intersection:** khi hai đoạn không thẳng hàng cắt nhau tại nội bộ, các đầu của mỗi đoạn nằm ở hai phía khác nhau của đường chứa đoạn kia, nên hai cặp orientation trái dấu nghiêm ngặt. Khi có giao tại biên hoặc collinear overlap, ít nhất một đầu mút thuộc đoạn còn lại; kiểm tra onSegment bao phủ các trường hợp đó.

**Convex hull:** mỗi lần thêm điểm, bỏ đỉnh giữa nếu tạo rẽ phải hoặc collinear, nên lower và upper lần lượt giữ biên lồi. Sau khi sort, các điểm không phải cực trị nằm phía trong hoặc trên cạnh bị loại; hai chuỗi ghép thành hull. Orientation exact giữ bất biến.

**Ray casting:** với polygon đơn, parity số lần tia xuất/nhập vùng quyết định inside/outside. Quy tắc nửa mở theo y tránh đếm trùng đỉnh; dấu orientation xác định tia cắt bên phải P bằng số nguyên, không phải chia số thực.

**Rational intersection:** nghiệm tham số `t=cross(C−A,D−C)/cross(B−A,D−C)` của hai đường thẳng không song song là phân số hai số nguyên. BigInteger và chuẩn hóa gcd giữ tọa độ chính xác. Nếu cần giao của **đoạn**, phải thêm điều kiện t,u∈[0,1].

## 16. Độ phức tạp

| Phép toán | Số phép số học | Bộ nhớ phụ |
| --- | --- | --- |
| Orientation, D², onSegment | O(1) cộng/nhân/so sánh | O(1) số lớn |
| Hai đoạn giao | O(1) orientation | O(1) số lớn |
| Giao hai đường thẳng | O(1) định thức và gcd | O(1) phân số |
| Twice signed area với h đỉnh | O(h) | O(1) số lớn ngoài input |
| Convex hull h điểm | O(h log h) so sánh, O(h) orientation amortized | O(h) |
| Point in polygon h cạnh | O(h) | O(1) số lớn |

Ở bảng, O(1) là **số phép toán trên hệ số**, không có nghĩa phép nhân BigInteger với b bit có bit-complexity O(1). Với tọa độ đầu vào signed long, các toán hạng do tích chéo sinh ra có số bit giới hạn, nên các phép BigInteger thường phù hợp cho bài học; với n cực lớn cần benchmark và thiết kế fast path.

## 17. Những lỗi thường gặp

| Sai lầm | Nguyên nhân sai | Cách sửa |
| --- | --- | --- |
| `long D=(bx-ax)*(cy-ay)-...` với tọa độ không bound | Tích/trừ long có thể tràn | BigInteger trước phép trừ |
| `BigInteger.valueOf(bx-ax)` | Long tràn trước ép kiểu | Chuyển từng toán hạng gốc |
| `(int)(x1-x2)` trong Comparator | Tràn, không bảo đảm thứ tự | Long.compare |
| Thấy tọa độ int nên dùng cross int | Tích hai int có thể ~10^18 | Chứng minh cận và ép trước |
| So cross double với EPS cố định | Sai theo scale và mất bit | Robust/exact predicate |
| Dùng EPS “gần bằng” trong comparator | Quan hệ không bắc cầu | Strict comparator |
| Chuyển long lớn sang double rồi mới BigDecimal | Không khôi phục bit đã mất | Giữ dữ liệu nguyên gốc |
| Chỉ orientation=0 để kết luận onSegment | Điểm thẳng hàng ngoài đoạn | Kiểm tra khoảng đóng |
| Chỉ `o₁o₂≤0` và `o₃o₄≤0` để kiểm giao | Đoạn collinear rời vẫn có o=0 | OnSegment riêng |
| Nhầm line intersection với segment intersection | Nghiệm có thể ngoài đoạn | Kiểm tra t,u trong [0,1] |
| Trả tọa độ giao bằng long khi là 3/2 | Mất phần phân số | Rational |
| Tính shoelace bằng long với polygon lớn | Tổng có thể tràn | BigInteger cho tích/tổng |
| Quên xử lý điểm biên trước ray casting | Boundary bị phân loại tùy tiện | OnSegment trước |
| Đếm hai cạnh tại cùng một đỉnh | Sai parity | Nửa mở theo y |
| Convex hull quên dedupe | Có thể tạo đỉnh/cạnh thừa | Loại điểm trùng |
| Không rõ yêu cầu giữ collinear hull | Kết quả khác hợp đồng | Chốt cross≤0 hoặc <0 |
| Không kiểm tra NaN/Infinity | So double không như số thực | Validate finite |
| Chỉ test tọa độ nhỏ | Bỏ overflow và precision loss | Test giá trị long cực trị |

## 18. Bài tập và lời giải

**Bài 1.** A=(0,0), B=(4,0), C=(2,3). Orientation?

*Đáp án:* 12>0, C ở bên trái A→B.

**Bài 2.** Đổi B,C trong bài 1 cho dấu gì?

*Đáp án:* −12, vì đổi hai vector trong cross đảo dấu.

**Bài 3.** A=(0,0), B=(4,0), P=(8,0) có thuộc AB không?

*Đáp án:* Không; thẳng hàng nhưng ngoài khoảng x=[0,4].

**Bài 4.** Đoạn A=B=(2,0), P=(2,0) có thuộc không?

*Đáp án:* Có, đoạn suy biến chỉ gồm điểm ấy.

**Bài 5.** Tích `4×10^9×4×10^9` vừa signed long không?

*Đáp án:* Không, là 16×10^18 > Long.MAX_VALUE.

**Bài 6.** Vì sao ép `bx-ax` sang BigInteger sau phép trừ chưa đủ?

*Đáp án:* Phép trừ long có thể tràn trước khi ép; phải ép cả bx và ax riêng.

**Bài 7.** D² giữa (0,0) và (4×10^9,4×10^9) là bao nhiêu?

*Đáp án:* 32×10^18, vượt signed long.

**Bài 8.** AB=(0,0)–(4,0), CD=(2,−2)–(2,2) có giao?

*Đáp án:* Có, tại (2,0).

**Bài 9.** Hai đoạn chỉ chạm tại (4,0) thì giao theo bài không?

*Đáp án:* Có, hợp đồng bài bao gồm đầu mút.

**Bài 10.** Hai đoạn thẳng hàng nhưng AB có x∈[0,2], CD có x∈[3,4] có giao?

*Đáp án:* Không, hai khoảng chiếu không chồng.

**Bài 11.** Giao của hai đường (0,0)–(3,2) và (0,2)–(3,0)?

*Đáp án:* (3/2,1), phải dùng phân số nếu cần exact.

**Bài 12.** Hình chữ nhật (0,0),(4,0),(4,3),(0,3) có 2S?

*Đáp án:* 24. Đảo thứ tự đỉnh thì 2S=−24.

**Bài 13.** Point-in-polygon của (4,1) trên rectangle trên?

*Đáp án:* BOUNDARY, không phải INSIDE hoặc OUTSIDE.

**Bài 14.** Bao lồi của bốn góc rectangle thêm (2,2)?

*Đáp án:* Vẫn là bốn góc vì (2,2) nằm trong.

**Bài 15.** Với tất cả điểm trên một đường, cross≤0 của Andrew loại gì?

*Đáp án:* Các điểm collinear nằm giữa; chỉ giữ hai điểm cực trị nếu có ít nhất hai điểm phân biệt.

**Bài 16.** Cross=10^−24 dương nhưng EPS=10^−9. Kết luận collinear chính xác?

*Đáp án:* Không; EPS đang lớn hơn cross 10^15 lần.

**Bài 17.** Vì sao long 10^18+1 và 10^18+2 có thể bị double coi cùng số?

*Đáp án:* Bước ULP tại cỡ 10^18 lớn hơn các chênh lệch 1,2.

**Bài 18.** Gọi BigDecimal.valueOf sau khi đã ép long thành double có hồi phục được bit không?

*Đáp án:* Không, bit thấp bị mất ở lần ép đầu tiên.

**Bài 19.** Đầu vào "0.125" là số thập phân chính xác. Muốn định hướng exact làm thế nào?

*Đáp án:* Đọc BigDecimal(String), quy về cùng scale nguyên hoặc Rational, rồi định thức BigInteger.

**Bài 20.** Vì sao comparator coi hai double cách dưới EPS là bằng nhau có thể sai?

*Đáp án:* Quan hệ gần bằng không bắc cầu, làm thứ tự sort bất nhất.

**Bài 21.** Tại sao ray casting dùng điều kiện (A.y>P.y)!=(B.y>P.y)?

*Đáp án:* Dùng quy tắc nửa mở để không đếm đôi một đỉnh.

**Bài 22.** Tọa độ `|x|,|y|≤10^9` có thể dùng long cho một orientation không?

*Đáp án:* Có theo cận đủ `|D|≤8×10^18<Long.MAX_VALUE`, nếu tất cả bước tính dưới long. Tổng shoelace nhiều cạnh cần cận riêng.

**Bài 23.** Chỉ cần in độ dài tới 6 chữ số thập phân. Có nhất thiết dùng BigInteger cho sqrt?

*Đáp án:* Không. Math.hypot/double có thể phù hợp nếu đáp ứng sai số; còn so thứ tự khoảng cách exact nên dùng D² nguyên.

**Bài 24.** Convex hull monotone chain có độ phức tạp nào?

*Đáp án:* O(n log n) so sánh sort, thêm O(n) orientation amortized, chưa tính bit complexity.

**Bài 25.** Điểm đầu vào là double thực sự và cross rất gần 0. Có được tuyên bố dấu exact chỉ với EPS tùy chọn?

*Đáp án:* Không; cần một cận sai số **đúng với phép tính** hoặc adaptive/exact predicate cho giá trị binary64.

## 19. Checklist

1. Chốt tọa độ là **nguyên exact, thập phân exact hay double đo đạc**.
2. Chốt yêu cầu **predicate đúng tuyệt đối** hay phép đo **cho sai số**.
3. Chứng minh cận **hiệu, tích và tổng** nếu muốn dùng int/long.
4. Với BigInteger, **chuyển từng tọa độ trước khi trừ**.
5. Với giao đoạn, xử lý **biên và collinear** thay vì chỉ nhìn dấu hai tích.
6. Với giao đường thẳng, dùng Rational khi tọa độ có thể không nguyên; kiểm tra thêm t,u khi xét **đoạn**.
7. Với polygon, tính twiceArea nguyên, dùng onSegment trước parity, và quy tắc y nửa mở.
8. Với hull, sort comparator chặt, loại trùng, chốt chính sách đối với collinear.
9. Đừng dùng EPS cố định hay “phần thập phân rất nhỏ” như chứng nhận exact.
10. Với double, kiểm tra NaN/Infinity và cân nhắc robust/adaptive predicates.
11. Test input cực trị long, mất precision double, giao đầu mút, đoạn suy biến, polygon lõm/CW.
12. Dùng **oracle khác công thức** và minh bạch số ca kiểm tra, không đánh đồng kiểm thử hữu hạn với chứng minh.

## Tổng kết

Trong hình học tính toán, **predicate** là các quyết định rời rạc nên sai một dấu có thể làm hỏng cả thuật toán. Tọa độ nguyên nên dùng số nguyên đủ rộng hoặc BigInteger cho định thức, giao đoạn, khoảng cách bình phương và hai lần diện tích. Khi giao đường thẳng có tọa độ phân số, Rational giúp giữ exact. Với double, EPS cố định không thể khôi phục bit đầu vào đã mất và không phải bảo đảm tổng quát cho dấu của cross.

Chương trình Java 17 đưa ra một bộ predicate **chính xác trên toàn miền tọa độ signed long** bằng BigInteger và Rational; đồng thời cho thấy double có thể biến một cross dương rất lớn thành 0.0. Các phép kiểm tra đã được đối chiếu với oracle độc lập trên **77.932 trường hợp**, bao gồm 65.536 cặp đoạn nhỏ và hàng nghìn bộ tọa độ long cực trị. Độ tin cậy tổng quát vẫn dựa vào **định thức toán học, kiểm tra khoảng đóng và phép tính nguyên chính xác**, không chỉ số lượng test.
