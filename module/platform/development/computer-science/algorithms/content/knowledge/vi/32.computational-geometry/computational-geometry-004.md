# Giao nhau của hai đoạn thẳng

**Chủ đề:** Computer Science Algorithms · Hình học tính toán

## 1. Bài toán hình học và ý nghĩa của giao nhau

Cho hai **đoạn thẳng đóng** AB và CD trên mặt phẳng tọa độ. Mỗi đoạn chứa **cả hai đầu mút** và tất cả điểm nằm giữa chúng:

\[
AB=\{A+t(B-A)\mid 0\le t\le1\},
\qquad
CD=\{C+u(D-C)\mid 0\le u\le1\}.
\]

Cần xác định giao của hai tập điểm đó. Nếu hai đường thẳng đỡ hai đoạn cắt nhau, **chưa chắc hai đoạn cắt nhau**: điểm giao của đường thẳng vô hạn có thể nằm ngoài một hoặc cả hai đoạn.

Giao của hai đoạn thẳng đóng trong mặt phẳng chỉ có ba loại:

1. **NONE:** không có điểm chung.
2. **POINT:** đúng một điểm chung. Điểm ấy có thể là giao cắt bên trong hai đoạn, là đầu mút chung hoặc một đầu mút của đoạn này nằm bên trong đoạn kia.
3. **OVERLAP:** có vô số điểm chung trên một **đoạn thẳng có độ dài dương**; hai đoạn nằm trên cùng một đường thẳng và phần chung không chỉ là một điểm.

Ví dụ hình học:

~~~text
Cắt nhau ở tâm:
A(0,0) --------- B(4,4)
C(0,4) --------- D(4,0)
Intersection: POINT (2,2)

Nằm trên cùng đường thẳng:
AB từ (0,0) tới (5,0)
CD từ (2,0) tới (7,0)
Intersection: OVERLAP [(2,0)..(5,0)]

Chỉ chạm ở đầu mút:
AB từ (0,0) tới (2,0)
CD từ (2,0) tới (5,0)
Intersection: POINT (2,0)
~~~

Bài này trình bày một thuật toán **O(1) phép kiểm tra hình học** trên hai đoạn, dựa trên **tích có hướng (cross product)** và kiểm tra hộp bao trục song song (AABB), rồi trả một trong ba loại trên. Vì phép định hướng là nền tảng của tính đúng, chương trình Java 17 dùng **BigInteger** để tính chính xác khi đầu vào là tọa độ nguyên kiểu long. Với giao cắt không nguyên, nó trả **phân số hữu tỉ chính xác**, không lấy điểm gần đúng bằng double.

Các trường hợp **đoạn suy biến thành một điểm**, hai đoạn cùng đường thẳng, đầu mút, tọa độ âm, thứ tự đầu mút đảo ngược và tọa độ gần giới hạn long đều được xử lý rõ ràng.

## 2. Điểm, vectơ và phép định hướng

Điểm A=(Ax,Ay), B=(Bx,By). Vectơ AB=(Bx−Ax,By−Ay). Với hai vectơ u=(ux,uy), v=(vx,vy), định nghĩa **tích có hướng trong 2D** là số vô hướng:

\[
\operatorname{cross}(u,v)=u_xv_y-u_yv_x.
\]

Đối với ba điểm A,B,P:

\[
\boxed{
\operatorname{orient}(A,B,P)=
(B_x-A_x)(P_y-A_y)
-(B_y-A_y)(P_x-A_x)
}.
\]

Giá trị này là **hai lần diện tích tam giác có dấu**, vì thế nó mang thông tin vị trí tương đối của P so với đường thẳng có hướng A→B.

| Dấu của orient(A,B,P) | Diễn giải |
|---|---|
| Dương | P nằm bên **trái** hướng A→B (quay ngược chiều kim đồng hồ) |
| Âm | P nằm bên **phải** hướng A→B (quay cùng chiều kim đồng hồ) |
| Bằng 0 | A, B, P **thẳng hàng** về mặt đại số |

Nếu đảo A và B, dấu của phép định hướng đổi ngược. Dấu không phụ thuộc độ dài đoạn: chỉ phụ thuộc thứ tự điểm và tính thẳng hàng.

Ví dụ:
- A=(0,0), B=(4,0), P=(2,3): orient=4×3−0×2=**12>0**, P ở bên trái.
- A=(0,0), B=(4,0), P=(2,−3): orient=**−12<0**, P ở bên phải.
- A=(0,0), B=(4,0), P=(2,0): orient=**0**, ba điểm thẳng hàng.

### 2.1. Thẳng hàng chưa có nghĩa nằm trên đoạn

Với AB từ (0,0) tới (4,0), điểm P=(7,0) cho orient(A,B,P)=0 nhưng P nằm ngoài đoạn.

Do đó, **P nằm trên đoạn đóng AB** khi và chỉ khi:
1. orient(A,B,P)=0, và
2. P nằm trong hộp bao của hai đầu mút:

\[
\min(A_x,B_x)\le P_x\le\max(A_x,B_x),
\]

\[
\min(A_y,B_y)\le P_y\le\max(A_y,B_y).
\]

Điều kiện hộp bao được dùng cùng định hướng chính xác, không thay thế định hướng.

### 2.2. Tại sao nên xét dấu, không nhân hai giá trị định hướng?

Để biết P và Q nằm **ở hai phía nghiêm ngặt** của đường AB, có thể so dấu:

~~~text
orient(A,B,P) > 0 và orient(A,B,Q) < 0
hoặc ngược lại
~~~

Nếu đã chuẩn hóa thành signum thuộc {−1,0,1}, kiểm tra sign1×sign2<0 là an toàn. Tuy nhiên **không nhân trực tiếp hai định thức lớn** để xét dấu: ngay cả khi mỗi định thức còn trong long, tích của hai định thức có thể tràn.

Mã sẽ dùng hàm trả **chỉ dấu** từ BigInteger.signum, và kiểm tra hai dấu trái nhau.

## 3. Tại sao long và double có thể làm hình học sai?

### 3.1. Tràn số ngay khi trừ tọa độ

Hai tọa độ kiểu long đều hợp lệ:

~~~text
Ax = Long.MIN_VALUE
Bx = Long.MAX_VALUE
~~~

Nhưng hiệu **Bx−Ax = 2^64−1** không thể lưu trong long. Vì vậy, viết:

~~~java
long dx = bx - ax; // có thể overflow
BigInteger corrected = BigInteger.valueOf(dx); // đã quá muộn
~~~

không cứu được giá trị thật. Phải **chuyển từng tọa độ thành BigInteger trước khi trừ**:

~~~java
BigInteger dx = BigInteger.valueOf(bx)
        .subtract(BigInteger.valueOf(ax));
~~~

Ngoài hiệu tọa độ, tích chéo của hai hiệu cũng có thể vượt long rất xa. Mã dùng BigInteger cho **mọi phép trừ, nhân và cộng** phục vụ định hướng và tọa độ giao.

### 3.2. Dùng double và ngưỡng epsilon tùy tiện

Một cách cài thường gặp:

~~~text
if abs(cross) < EPS: coi như thẳng hàng
~~~

Vấn đề là EPS tuyệt đối không thích hợp cho mọi tỷ lệ tọa độ. Với dữ liệu rất lớn hoặc các đường gần song song, một sai số dấu phẩy động có thể đổi dấu cross hoặc gộp hai đường khác nhau thành thẳng hàng. Mặt khác, phép tính double không phân biệt được tất cả các số nguyên long.

Với **tọa độ nguyên**, BigInteger cho phép quyết định **đúng tuyệt đối** dấu định hướng và phân loại giao cắt. Không cần EPS cho các predicate này.

Với **tọa độ thực đo đạc**, vấn đề khác: cần định nghĩa sai số hình học, độ chính xác đầu vào và có thể dùng **robust/adaptive orientation predicates**. Không được coi một EPS ma thuật là chứng minh hình học.

## 4. Lọc nhanh bằng hộp bao trục song song (AABB)

Hộp bao của AB là tích của hai khoảng:

\[
[\min(A_x,B_x),\max(A_x,B_x)]
\times
[\min(A_y,B_y),\max(A_y,B_y)].
\]

Nếu hai hộp bao **không chồng lên nhau trên trục x hoặc y**, thì hai đoạn chắc chắn **không giao nhau**.

Điều kiện cần để có giao:

\[
\max(\min(A_x,B_x),\min(C_x,D_x))
\le
\min(\max(A_x,B_x),\max(C_x,D_x)),
\]

và điều kiện tương tự trên trục y.

Với đoạn **đóng**, dấu bằng được chấp nhận vì đầu mút vẫn thuộc đoạn.

Đây là **bộ lọc đủ để loại**, không phải kết luận đủ để khẳng định giao. Ví dụ:
- AB từ (0,0) tới (4,4).
- CD từ (0,3) tới (2,4).

Hộp bao của chúng chồng nhau, nhưng đường thẳng chứa CD cắt đường chứa AB ngoài phạm vi các đoạn, nên kết quả vẫn **NONE**.

Mã thực hiện AABB trước để tránh phép tính BigInteger tốn công khi các khoảng trục đã tách rời. Phép min/max trên long an toàn ngay cả ở giới hạn của kiểu số.

## 5. Trường hợp hai đoạn cắt nghiêm ngặt tại phần trong

Đặt:

\[
o_1=\operatorname{sign}(\operatorname{orient}(A,B,C)),
\qquad
o_2=\operatorname{sign}(\operatorname{orient}(A,B,D)),
\]

\[
o_3=\operatorname{sign}(\operatorname{orient}(C,D,A)),
\qquad
o_4=\operatorname{sign}(\operatorname{orient}(C,D,B)).
\]

Nếu **không có dấu nào bằng 0**, hai đoạn cắt nhau nghiêm ngặt tại một điểm nằm bên trong cả hai khi:

\[
\boxed{o_1o_2<0\quad\land\quad o_3o_4<0}.
\]

Vì:
- C và D nằm ở **hai phía khác nhau** của đường vô hạn AB.
- A và B nằm ở **hai phía khác nhau** của đường vô hạn CD.

Với hai đoạn không suy biến và không có điểm thẳng hàng đặc biệt, điều kiện này là cần và đủ để chúng có một giao điểm **trong phần trong tương đối** của mỗi đoạn.

Ví dụ:
- AB=(0,0)→(4,4).
- CD=(0,4)→(4,0).

Hai đoạn cắt tại **(2,2)**. Các định hướng hai bên đổi dấu ở cả hai hướng.

### 5.1. Giao tại tọa độ hữu tỉ

Ngay cả khi mọi đầu mút có tọa độ nguyên, giao điểm không nhất thiết có tọa độ nguyên.

Ví dụ:
- AB=(0,0)→(4,4), đường thẳng y=x.
- CD=(0,3)→(4,0), đường thẳng y=3−3x/4.

Giải:

\[
x=3-\frac34x
\Longrightarrow
\frac74x=3
\Longrightarrow
x=\frac{12}{7},
\quad y=\frac{12}{7}.
\]

Kết quả chính xác là **POINT (12/7,12/7)**, không phải (2,2) và không phải số được làm tròn đến tọa độ nguyên.

## 6. Chạm đầu mút và giao ở dạng chữ T

Điều kiện cắt nghiêm ngặt ở phần 5 **không bắt được** giao điểm ở đầu mút vì khi đó có một định hướng bằng 0.

Đối với đoạn đóng, cần kiểm tra **bốn** tình huống:

1. C thẳng hàng và nằm trên đoạn AB.
2. D thẳng hàng và nằm trên đoạn AB.
3. A thẳng hàng và nằm trên đoạn CD.
4. B thẳng hàng và nằm trên đoạn CD.

Một điều kiện đúng thì giao có ít nhất điểm đầu mút tương ứng.

Ví dụ **chạm đầu mút**:
- AB=(0,0)→(4,0).
- CD=(4,0)→(5,3).
- Kết quả POINT (4,0).

Ví dụ **chữ T**:
- AB=(0,0)→(4,0).
- CD=(2,0)→(2,3).
- Kết quả POINT (2,0).

Hai trường hợp trên cùng loại **POINT**, vì tập giao chứa đúng một điểm. Nếu một bài khác cần phân biệt giao nghiêm ngặt và tiếp xúc, có thể giữ thêm nhãn **CROSS_INTERIOR** hoặc **TOUCH_ENDPOINT**, nhưng phải định nghĩa rõ quy ước. API trong bài trả một loại hình học tổng quát POINT.

**Thứ tự kiểm tra quan trọng:** cần xử lý **đồng tuyến và chồng lấn** trước khi trả một đầu mút chạm. Nếu hai đoạn chung một khoảng, một trong các đầu mút cũng có thể nằm trên đoạn kia, nhưng giao thực phải là **OVERLAP**, không phải POINT.

## 7. Hai đoạn đồng tuyến: phân biệt một điểm và một đoạn chung

Nếu cả bốn định hướng o1,o2,o3,o4 đều bằng 0, hai đoạn nằm trên cùng một đường thẳng (kể cả cách hiểu tương thích khi một hoặc hai đoạn suy biến thành điểm). Ta phải tìm **phần giao của hai khoảng** dọc theo đường ấy.

Một cách đơn giản, không cần chia và không lo đường thẳng đứng: **sắp hai đầu mút theo thứ tự từ điển của cặp (x,y)**:
- Điểm có x nhỏ hơn đứng trước.
- Nếu x bằng nhau thì điểm có y nhỏ hơn đứng trước.

Với các điểm nằm trên cùng một đường thẳng:
- Nếu đường không thẳng đứng, x biến thiên đơn điệu dọc theo đường; sắp (x,y) tương ứng sắp dọc đoạn.
- Nếu đường thẳng đứng, mọi x bằng nhau và y biến thiên đơn điệu; so y là đủ.
- Nếu đoạn là một điểm, đầu trái và đầu phải theo thứ tự này trùng nhau.

Đặt:
- lo1=minLex(A,B), hi1=maxLex(A,B).
- lo2=minLex(C,D), hi2=maxLex(C,D).

Phần giao:

\[
lo=\max_{\mathrm{lex}}(lo_1,lo_2),\qquad
hi=\min_{\mathrm{lex}}(hi_1,hi_2).
\]

Có ba kết quả:
- **lo>hi:** hai khoảng tách nhau → NONE.
- **lo=hi:** chỉ chung một điểm → POINT (lo).
- **lo<hi:** chung một đoạn độ dài dương → OVERLAP [lo..hi].

### 7.1. Nằm ngang, dọc và dốc âm

Ví dụ đoạn ngang:
- AB=(0,0)→(5,0).
- CD=(2,0)→(7,0).
- Phần chung là **[(2,0)..(5,0)]**.

Ví dụ đoạn thẳng đứng:
- AB=(0,0)→(0,5).
- CD=(0,2)→(0,7).
- Phần chung là **[(0,2)..(0,5)]**.

Ví dụ đường có hệ số góc âm:
- AB=(0,5)→(5,0).
- CD=(2,3)→(8,−3).
- Phần chung là **[(2,3)..(5,0)]**.

Thứ tự cặp (x,y) vẫn hoạt động với đường có độ dốc âm, dù y giảm khi x tăng.

### 7.2. Đồng tuyến nhưng không chồng nhau

AB=(0,0)→(1,0) và CD=(3,0)→(4,0): bốn điểm cùng đường y=0 nhưng hai khoảng không chồng. Kết quả **NONE**.

AB=(0,0)→(2,0) và CD=(2,0)→(5,0): lo=hi=(2,0), nên kết quả **POINT (2,0)**, không phải OVERLAP.

## 8. Đoạn suy biến và các trường hợp dễ bị bỏ sót

**Đoạn suy biến** là đoạn có hai đầu mút trùng nhau. Về hình học nó là một **tập chỉ gồm một điểm**.

Các trường hợp:
- Một đoạn là điểm P, đoạn còn lại chứa P → POINT (P).
- Một đoạn là điểm P, đoạn còn lại không chứa P → NONE.
- Cả hai là cùng một điểm P → POINT (P).
- Cả hai là hai điểm khác nhau → NONE.

Vì orient(A,A,P)=0 với **mọi** P, nếu chỉ dùng một cặp định hướng có gốc ở đoạn suy biến sẽ dễ kết luận sai là đồng tuyến.

Do đó thuật toán sử dụng đầy đủ **bốn định hướng**, kiểm tra **AABB**, rồi xử lý các điều kiện điểm nằm trên đoạn. Khi cả bốn định hướng bằng 0, phép giao khoảng theo (x,y) vẫn đúng cho các đoạn suy biến.

Ví dụ:
- AB=(2,0)→(2,0); CD=(0,0)→(4,0) → **POINT (2,0)**.
- AB=(5,0)→(5,0); CD=(0,0)→(4,0) → **NONE**.
- AB=(1,1)→(1,1); CD=(1,1)→(1,1) → **POINT (1,1)**.
- AB=(1,1)→(1,1); CD=(2,2)→(2,2) → **NONE**.

Không được dùng hệ số góc (By−Ay)/(Bx−Ax) làm trung tâm của thuật toán: mẫu số có thể bằng 0 với đường thẳng đứng hoặc đoạn suy biến. Phép định hướng bằng cross product tránh phép chia ấy.

## 9. Tọa độ giao chính xác bằng tham số và số hữu tỉ

Khi hai đoạn **cắt nghiêm ngặt** và không song song, ta biết giao điểm duy nhất thuộc cả hai đoạn. Đặt:

\[
r=B-A,\qquad s=D-C.
\]

Điểm trên đường thứ nhất là:

\[
P=A+tr.
\]

Trên đường thứ hai:

\[
P=C+us.
\]

Từ A+tr=C+us, lấy cross với s:

\[
t\operatorname{cross}(r,s)=\operatorname{cross}(C-A,s).
\]

Vì hai đường không song song, \(\operatorname{cross}(r,s)\ne0\). Do đó:

\[
\boxed{
t=\frac{\operatorname{cross}(C-A,s)}
        {\operatorname{cross}(r,s)}
}.
\]

Đặt:

\[
den=\operatorname{cross}(r,s),\qquad
tNum=\operatorname{cross}(C-A,s).
\]

Tọa độ giao:

\[
\boxed{
P_x=\frac{A_x\cdot den+r_x\cdot tNum}{den},
\quad
P_y=\frac{A_y\cdot den+r_y\cdot tNum}{den}.
}
\]

Mọi số trong tử và mẫu đều là **số nguyên** nếu tọa độ đầu vào nguyên. Vì vậy, để biểu diễn chính xác P, chỉ cần số hữu tỉ (num,den) và chuẩn hóa:
- Nếu den âm, đổi dấu cả num và den.
- Rút gọn num/den bằng gcd(|num|,den).
- Bảo đảm den dương.
- Nếu num=0, chuẩn hóa thành 0/1.
- Nếu den=1, có thể hiển thị như số nguyên.

### 9.1. Không chia nguyên để lấy tọa độ

Nếu P=(12/7,12/7), thực hiện số nguyên 12/7 sẽ cho 1 và làm mất dữ liệu. Dùng double có thể cho 1.714285714..., nhưng đó là gần đúng. Lưu phân số BigInteger cho phép kết quả **chính xác** và so sánh hai giao điểm hữu tỉ mà không phụ thuộc epsilon.

### 9.2. Giao tại đầu mút

Nếu giao là đầu mút đã biết, không cần giải hai phương trình đường thẳng. Trả trực tiếp tọa độ nguyên của đầu mút dưới dạng phân số có mẫu 1. Như vậy tránh gọi công thức trên trong các trường hợp hai đường đồng tuyến (den=0).

### 9.3. Tọa độ long cực trị

Lấy hai đường chéo qua hình vuông có hai giá trị tọa độ cực trị:
- A=(Long.MIN_VALUE,Long.MIN_VALUE).
- B=(Long.MAX_VALUE,Long.MAX_VALUE).
- C=(Long.MIN_VALUE,Long.MAX_VALUE).
- D=(Long.MAX_VALUE,Long.MIN_VALUE).

Vì Long.MIN_VALUE + Long.MAX_VALUE = −1, giao điểm chính xác là **(−1/2,−1/2)**.

Dù từng tọa độ đầu vào vừa trong long, hiệu Bx−Ax và các định thức vượt long. Chương trình dùng BigInteger **trước khi trừ** nên trả đúng:

~~~text
Extreme long crossing: POINT (-1/2,-1/2)
~~~

## 10. Quy trình phân loại đầy đủ

Một quy trình an toàn, trả đúng loại giao:

~~~text
intersect(AB,CD):
    if AABB(AB) và AABB(CD) không chồng:
        return NONE

    o1 = sign(orient(A,B,C))
    o2 = sign(orient(A,B,D))
    o3 = sign(orient(C,D,A))
    o4 = sign(orient(C,D,B))

    if o1=o2=o3=o4=0:
        sort endpoints of each segment by lex(x,y)
        lo = max(lower endpoints)
        hi = min(upper endpoints)
        if lo>hi: return NONE
        if lo=hi: return POINT(lo)
        return OVERLAP([lo..hi])

    if C on AB: return POINT(C)
    if D on AB: return POINT(D)
    if A on CD: return POINT(A)
    if B on CD: return POINT(B)

    if o1 and o2 have strict opposite signs
       and o3 and o4 have strict opposite signs:
        compute exact rational line intersection
        return POINT(intersection)

    return NONE
~~~

**Không được đổi thứ tự “đồng tuyến” và “một đầu mút nằm trên đoạn kia”** nếu muốn phân biệt OVERLAP. Trường hợp đồng tuyến có thể chứa một hoặc nhiều đầu mút nằm trong đoạn đối phương; phải lấy cả khoảng giao trước.

### 10.1. Đúng với các kiểu giao cắt vì sao?

- Nếu hộp bao rời nhau, không tồn tại điểm chung: trả NONE là an toàn.
- Nếu bốn định hướng bằng 0, hai đoạn có thể xem là cùng đường đỡ hoặc các điểm suy biến có thể kiểm tra bằng giao khoảng theo lex; trả NONE, POINT hoặc OVERLAP đúng kích thước tập giao.
- Nếu có đầu mút nằm trên đoạn đối phương nhưng không phải trường hợp đồng tuyến chồng đoạn, giao điểm đó là một điểm chung; hai đoạn không đồng tuyến không thể có một đoạn chung có độ dài dương.
- Nếu không đầu mút nào nằm trên đoạn kia nhưng hai cặp dấu định hướng trái nhau nghiêm ngặt, định lý giao đoạn cho một giao điểm trong phần trong của cả hai.
- Nếu tất cả điều kiện trên sai, không thể có điểm chung còn lại: trả NONE.

Sự phân hoạch này bao phủ cả tiếp xúc, giao nghiêm ngặt, đồng tuyến, song song và đoạn suy biến.

### 10.2. Các bất biến hữu ích

1. **Đối xứng:** intersect(AB,CD) bằng intersect(CD,AB).
2. **Đảo chiều:** đổi AB thành BA hoặc CD thành DC không đổi hình học giao.
3. **Chính xác:** nếu trả POINT, tọa độ ấy thuộc cả hai đoạn.
4. **Tối đa:** nếu trả OVERLAP, cả hai đầu đoạn chung đều thuộc cả hai đoạn và không có điểm chung nằm ngoài khoảng trả về.
5. **Tính đóng:** chạm tại đầu mút được tính là giao.
6. **Chuẩn hóa:** đầu mút của OVERLAP được sắp tăng theo cặp (x,y), phân số có mẫu dương và đã rút gọn.

Hai bất biến đầu rất hữu ích cho **property-based testing**. Để so kết quả chính xác giữa nhiều thứ tự đầu mút, cần chuẩn hóa đầu đoạn OVERLAP và phân số như mã trong bài.

## 11. Java 17 hoàn chỉnh: NONE, POINT, OVERLAP

Lưu file **SegmentIntersectionDemo.java**. Mã sử dụng:
- Java record **Point**, **Segment**, **Rational**, **RationalPoint** và **Result**.
- BigInteger cho dấu định hướng và phép tính giao điểm.
- Long.compare và Math.min/max cho phép so đầu mút/hộp bao, không tạo hiệu long dễ tràn.
- Phân đoạn chồng lấn trả dưới dạng **hai đầu mút nguyên** sắp theo lex.
- Giao một điểm ở tọa độ hữu tỉ rút gọn.
- Không dùng EPS; tọa độ đầu vào là **số nguyên long**.
- Phân loại điểm suy biến và đoạn đóng.

~~~java
import java.math.BigInteger;
import java.util.Objects;

public final class SegmentIntersectionDemo {
    private SegmentIntersectionDemo() {
    }

    public enum Kind {
        NONE, POINT, OVERLAP
    }

    public record Point(long x, long y) {
        @Override
        public String toString() {
            return "(" + x + "," + y + ")";
        }
    }

    public record Segment(Point from, Point to) {
        public Segment {
            Objects.requireNonNull(from, "from");
            Objects.requireNonNull(to, "to");
        }
    }

    public record Rational(
            BigInteger numerator, BigInteger denominator) {
        public Rational {
            Objects.requireNonNull(numerator, "numerator");
            Objects.requireNonNull(denominator, "denominator");

            if (denominator.signum() == 0) {
                throw new IllegalArgumentException(
                        "Denominator cannot be zero");
            }
            if (denominator.signum() < 0) {
                numerator = numerator.negate();
                denominator = denominator.negate();
            }

            BigInteger divisor = numerator.gcd(denominator);
            numerator = numerator.divide(divisor);
            denominator = denominator.divide(divisor);
        }

        public static Rational whole(long value) {
            return new Rational(
                    BigInteger.valueOf(value), BigInteger.ONE);
        }

        @Override
        public String toString() {
            if (denominator.equals(BigInteger.ONE)) {
                return numerator.toString();
            }
            return numerator + "/" + denominator;
        }
    }

    public record RationalPoint(Rational x, Rational y) {
        public RationalPoint {
            Objects.requireNonNull(x, "x");
            Objects.requireNonNull(y, "y");
        }

        public static RationalPoint from(Point p) {
            return new RationalPoint(
                    Rational.whole(p.x()),
                    Rational.whole(p.y()));
        }

        @Override
        public String toString() {
            return "(" + x + "," + y + ")";
        }
    }

    public record Result(
            Kind kind, RationalPoint point, Segment overlap) {
        public Result {
            Objects.requireNonNull(kind, "kind");
            switch (kind) {
                case NONE -> {
                    if (point != null || overlap != null) {
                        throw new IllegalArgumentException(
                                "NONE cannot carry geometry");
                    }
                }
                case POINT -> {
                    if (point == null || overlap != null) {
                        throw new IllegalArgumentException(
                                "POINT requires exactly one point");
                    }
                }
                case OVERLAP -> {
                    if (point != null || overlap == null) {
                        throw new IllegalArgumentException(
                                "OVERLAP requires a segment");
                    }
                }
            }
        }

        public static Result none() {
            return new Result(Kind.NONE, null, null);
        }

        public static Result at(RationalPoint p) {
            return new Result(Kind.POINT, p, null);
        }

        public static Result along(Segment segment) {
            return new Result(Kind.OVERLAP, null, segment);
        }

        @Override
        public String toString() {
            return switch (kind) {
                case NONE -> "NONE";
                case POINT -> "POINT " + point;
                case OVERLAP -> "OVERLAP ["
                        + overlap.from() + ".." + overlap.to() + "]";
            };
        }
    }

    private static BigInteger bi(long value) {
        return BigInteger.valueOf(value);
    }

    // Dấu hai lần diện tích tam giác có hướng ABC.
    public static int orientation(Point a, Point b, Point c) {
        BigInteger abx = bi(b.x()).subtract(bi(a.x()));
        BigInteger aby = bi(b.y()).subtract(bi(a.y()));
        BigInteger acx = bi(c.x()).subtract(bi(a.x()));
        BigInteger acy = bi(c.y()).subtract(bi(a.y()));

        return abx.multiply(acy)
                .subtract(aby.multiply(acx))
                .signum();
    }

    // Chỉ dùng min/max và so long, không trừ tọa độ.
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

    // Kiểm tra cả thẳng hàng và thuộc hộp bao.
    public static boolean onSegment(
            Point a, Point b, Point p) {
        return orientation(a, b, p) == 0
                && p.x() >= Math.min(a.x(), b.x())
                && p.x() <= Math.max(a.x(), b.x())
                && p.y() >= Math.min(a.y(), b.y())
                && p.y() <= Math.max(a.y(), b.y());
    }

    // So theo (x,y), không tính x1-x2 vì có thể overflow.
    private static int compareLex(Point a, Point b) {
        int cx = Long.compare(a.x(), b.x());
        return cx != 0 ? cx : Long.compare(a.y(), b.y());
    }

    private static Point minLex(Point a, Point b) {
        return compareLex(a, b) <= 0 ? a : b;
    }

    private static Point maxLex(Point a, Point b) {
        return compareLex(a, b) >= 0 ? a : b;
    }

    private static boolean opposite(int a, int b) {
        return (a < 0 && b > 0) || (a > 0 && b < 0);
    }

    // Chỉ gọi khi hai đường không song song.
    private static RationalPoint lineCrossing(
            Point a, Point b, Point c, Point d) {
        BigInteger rx = bi(b.x()).subtract(bi(a.x()));
        BigInteger ry = bi(b.y()).subtract(bi(a.y()));
        BigInteger sx = bi(d.x()).subtract(bi(c.x()));
        BigInteger sy = bi(d.y()).subtract(bi(c.y()));

        BigInteger cax = bi(c.x()).subtract(bi(a.x()));
        BigInteger cay = bi(c.y()).subtract(bi(a.y()));

        BigInteger den = rx.multiply(sy)
                .subtract(ry.multiply(sx));
        if (den.signum() == 0) {
            throw new IllegalArgumentException(
                    "Parallel supporting lines");
        }

        BigInteger tNum = cax.multiply(sy)
                .subtract(cay.multiply(sx));

        BigInteger xNum = bi(a.x()).multiply(den)
                .add(rx.multiply(tNum));
        BigInteger yNum = bi(a.y()).multiply(den)
                .add(ry.multiply(tNum));

        return new RationalPoint(
                new Rational(xNum, den),
                new Rational(yNum, den));
    }

    public static Result intersect(
            Segment first, Segment second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");

        Point a = first.from();
        Point b = first.to();
        Point c = second.from();
        Point d = second.to();

        if (!boxesOverlap(a, b, c, d)) {
            return Result.none();
        }

        int o1 = orientation(a, b, c);
        int o2 = orientation(a, b, d);
        int o3 = orientation(c, d, a);
        int o4 = orientation(c, d, b);

        // Đồng tuyến / suy biến thành điểm:
        // lấy phần giao của hai khoảng theo thứ tự lex.
        if (o1 == 0 && o2 == 0 && o3 == 0 && o4 == 0) {
            Point low = maxLex(
                    minLex(a, b), minLex(c, d));
            Point high = minLex(
                    maxLex(a, b), maxLex(c, d));

            int comparison = compareLex(low, high);
            if (comparison > 0) {
                return Result.none();
            }
            if (comparison == 0) {
                return Result.at(RationalPoint.from(low));
            }
            return Result.along(new Segment(low, high));
        }

        // Đoạn đóng: đầu mút trên đoạn đối phương.
        if (o1 == 0 && onSegment(a, b, c)) {
            return Result.at(RationalPoint.from(c));
        }
        if (o2 == 0 && onSegment(a, b, d)) {
            return Result.at(RationalPoint.from(d));
        }
        if (o3 == 0 && onSegment(c, d, a)) {
            return Result.at(RationalPoint.from(a));
        }
        if (o4 == 0 && onSegment(c, d, b)) {
            return Result.at(RationalPoint.from(b));
        }

        // Giao nghiêm ngặt ở phần trong cả hai đoạn.
        if (opposite(o1, o2) && opposite(o3, o4)) {
            return Result.at(lineCrossing(a, b, c, d));
        }
        return Result.none();
    }

    private static Segment segment(
            long ax, long ay, long bx, long by) {
        return new Segment(
                new Point(ax, ay), new Point(bx, by));
    }

    private static void show(
            String label, Segment first, Segment second) {
        System.out.println(label + ": "
                + intersect(first, second));
    }

    public static void main(String[] args) {
        Segment diagA = segment(0, 0, 4, 4);
        Segment diagB = segment(0, 4, 4, 0);

        show("Crossing diagonals", diagA, diagB);
        show("Fractional crossing",
                segment(0, 0, 4, 4),
                segment(0, 3, 4, 0));
        show("Endpoint touch",
                segment(0, 0, 4, 0),
                segment(4, 0, 5, 3));
        show("T-junction",
                segment(0, 0, 4, 0),
                segment(2, 0, 2, 3));
        show("Collinear overlap",
                segment(0, 0, 5, 0),
                segment(2, 0, 7, 0));
        show("Collinear endpoint",
                segment(0, 0, 2, 0),
                segment(2, 0, 5, 0));
        show("Collinear disjoint",
                segment(0, 0, 1, 0),
                segment(3, 0, 4, 0));
        show("Parallel disjoint",
                segment(0, 0, 4, 0),
                segment(0, 2, 4, 2));
        show("Boxes overlap but segments do not",
                segment(0, 0, 4, 4),
                segment(0, 3, 2, 4));
        show("Crossing reversed",
                segment(4, 4, 0, 0),
                segment(4, 0, 0, 4));
        show("Vertical overlap",
                segment(0, 0, 0, 5),
                segment(0, 2, 0, 7));
        show("Negative-slope overlap",
                segment(0, 5, 5, 0),
                segment(2, 3, 8, -3));
        show("Degenerate on segment",
                segment(2, 0, 2, 0),
                segment(0, 0, 4, 0));
        show("Degenerate outside segment",
                segment(5, 0, 5, 0),
                segment(0, 0, 4, 0));
        show("Two identical points",
                segment(1, 1, 1, 1),
                segment(1, 1, 1, 1));
        show("Two distinct points",
                segment(1, 1, 1, 1),
                segment(2, 2, 2, 2));

        Segment hugeA = segment(
                Long.MIN_VALUE, Long.MIN_VALUE,
                Long.MAX_VALUE, Long.MAX_VALUE);
        Segment hugeB = segment(
                Long.MIN_VALUE, Long.MAX_VALUE,
                Long.MAX_VALUE, Long.MIN_VALUE);
        show("Extreme long crossing", hugeA, hugeB);

        System.out.println("Extreme orientation: "
                + orientation(
                        hugeA.from(), hugeA.to(),
                        hugeB.from()));

        Result original = intersect(diagA, diagB);
        Result swapped = intersect(diagB, diagA);
        Result reversed = intersect(
                new Segment(diagA.to(), diagA.from()),
                new Segment(diagB.to(), diagB.from()));
        System.out.println("Symmetry: "
                + (original.equals(swapped)
                   && original.equals(reversed)));
    }
}
~~~

### 11.1. Biên dịch và chạy

Cần **JDK 17 trở lên**, lưu đúng tên public class:

~~~bash
javac -encoding UTF-8 SegmentIntersectionDemo.java
java SegmentIntersectionDemo
~~~

**Kết quả stdout dự kiến:**

~~~text
Crossing diagonals: POINT (2,2)
Fractional crossing: POINT (12/7,12/7)
Endpoint touch: POINT (4,0)
T-junction: POINT (2,0)
Collinear overlap: OVERLAP [(2,0)..(5,0)]
Collinear endpoint: POINT (2,0)
Collinear disjoint: NONE
Parallel disjoint: NONE
Boxes overlap but segments do not: NONE
Crossing reversed: POINT (2,2)
Vertical overlap: OVERLAP [(0,2)..(0,5)]
Negative-slope overlap: OVERLAP [(2,3)..(5,0)]
Degenerate on segment: POINT (2,0)
Degenerate outside segment: NONE
Two identical points: POINT (1,1)
Two distinct points: NONE
Extreme long crossing: POINT (-1/2,-1/2)
Extreme orientation: 1
Symmetry: true
~~~

### 11.2. Lý giải các thành phần Java

**Point và Segment:** Point mang tọa độ long; Segment cho phép from==to để biểu diễn đoạn suy biến. Segment kiểm tra không nhận null cho đầu mút.

**orientation:** chuyển **từng tọa độ** từ long sang BigInteger rồi mới tính hiệu và tích. Vì vậy kể cả hai đầu mút ở Long.MIN_VALUE và Long.MAX_VALUE, dấu cross được tính đúng. Trả -1,0,1, không trả giá trị định thức lớn.

**boxesOverlap:** dùng min/max và so sánh long an toàn. Đây là prefilter; kết quả true chưa chứng minh đoạn giao nhau.

**onSegment:** đồng thời kiểm tra orientation==0 và bốn điều kiện giới hạn trục. Riêng trường hợp AB là một điểm, nó chỉ trả true khi P đúng bằng điểm ấy.

**compareLex:** so x trước, nếu hòa so y. Không dùng trừ x1−x2 để so thứ tự vì phép trừ có thể tràn.

**Rational:** luôn đưa mẫu số về dương, rút gọn bằng gcd. Hai phân số có cùng giá trị toán học sẽ có biểu diễn chuẩn giống nhau, tiện cho so Result.equals và property tests.

**RationalPoint:** biểu diễn giao cắt có thể không nguyên. Với giao ở đầu mút đã biết, sử dụng Rational.whole để nhận mẫu 1.

**Result:** loại NONE không kèm hình học, loại POINT chứa đúng một RationalPoint, loại OVERLAP chứa một Segment. Record kiểm tra tính nhất quán dữ liệu trong compact constructor. Vì các record có equals theo giá trị, các trường hợp đảo chiều/đổi thứ tự có thể so trực tiếp.

**lineCrossing:** tính tọa độ điểm giao từ tham số tNum/den, dùng toàn BigInteger. Nó chỉ được gọi khi hai cặp dấu định hướng trái ngược nghiêm ngặt, nên den khác 0. Nếu gọi trực tiếp với hai đường song song, hàm từ chối mẫu số 0.

**intersect:** xử lý AABB, bốn dấu định hướng, trường hợp tất cả cùng bằng 0, bốn dạng chạm đầu mút, rồi cắt nghiêm ngặt. Những trường hợp còn lại không giao. Đoạn đồng tuyến có thể đảo chiều đầu mút nhưng phần giao vẫn được chuẩn hóa theo (x,y).

**main:** gồm giao cắt nguyên/phân số, chạm đầu mút, chữ T, chồng lấn ngang/dọc/dốc âm, hai đoạn không giao, đoạn suy biến, tọa độ long cực trị, kiểm thử đảo chiều và đổi thứ tự.

## 12. Độ phức tạp và giới hạn thực tế

**Số thao tác hình học** với hai đoạn là **O(1)**:
- Một lần kiểm tra AABB.
- Tối đa bốn orientation.
- Một số phép so điểm, kiểm tra thuộc đoạn.
- Nếu có giao nghiêm ngặt, một lần tính giao điểm hữu tỉ.

Với mô hình số nguyên có giới hạn bit cố định và các phép toán cơ bản chi phí O(1), thường nói thuật toán giao hai đoạn chạy **O(1) thời gian và O(1) bộ nhớ phụ**.

Nhưng chương trình dùng **BigInteger** để bảo đảm không tràn. Khi phân tích chi tiết ở mức bit, một phép nhân và gcd của các số nhiều bit **không miễn phí**, nên chi phí phụ thuộc độ dài bit của tọa độ và các giá trị trung gian. Vì đầu vào là bốn tọa độ long mỗi đoạn, độ dài bit của mỗi giá trị trung gian vẫn bị chặn bởi một hằng số về mặt lý thuyết; trong thực tế BigInteger tạo thêm đối tượng và chi phí cao hơn arithmetic nguyên cố định.

Nếu đầu vào bị giới hạn chắc chắn, ví dụ tọa độ nguyên đủ nhỏ và đã chứng minh mọi định thức không tràn long, có thể thay BigInteger bằng số nguyên cố định để tăng tốc. Nhưng không nên đổi chỉ vì “tọa độ đầu vào vừa long”: **hiệu và tích của hiệu** có thể lớn hơn long.

### 12.1. Chỉ cần biết có giao hay không?

Nếu đề chỉ hỏi boolean intersect, ta có thể dừng ngay khi thấy chạm/đồng tuyến chồng nhau hoặc cắt nghiêm ngặt; **không cần tính phân số giao điểm**. Điều này tiết kiệm phép BigInteger nhiều bit.

Bài này trả ba loại và tọa độ/khoảng giao để bảo đảm diễn giải hình học đầy đủ.

### 12.2. Đoạn mở và nửa mở

Bài dùng **đoạn đóng**: 0≤t≤1, nên chạm ở đầu mút tính là giao.

Nếu đề dùng **đoạn mở** (0<t<1) hoặc nửa mở, kết quả ở đầu mút có thể đổi. Không thể chỉ thay mọi dấu ≤ thành < trong AABB mà vẫn chắc chắn đúng mọi trường hợp đồng tuyến: cần xác định rõ việc đầu mút nào được nhận, và giao đoạn có thể là một khoảng mở/nửa mở.

## 13. Kiểm thử bằng oracle độc lập

Một cách kiểm thử không nên chỉ gọi lại cùng công thức orientation rồi so kết quả với chính nó. Có thể làm **oracle tham số**:

Đặt r=B−A, s=D−C, q=C−A.

\[
den=\operatorname{cross}(r,s).
\]

Nếu den≠0, tính:

\[
t=\frac{\operatorname{cross}(q,s)}{den},
\qquad
u=\frac{\operatorname{cross}(q,r)}{den}.
\]

**Điều kiện đủ và cần để hai đoạn đóng cắt tại một điểm** trong trường hợp không song song là:

\[
0\le t\le1,\qquad0\le u\le1.
\]

Có thể kiểm tra các bất đẳng thức trên **không dùng số thực**: so tử với 0 và den, đổi chiều bất đẳng thức khi den âm. Nếu đúng, giao điểm là A+tr và phải trùng với kết quả của thuật toán orientation.

Nếu den=0, hai đường đỡ song song hoặc một đoạn suy biến; xử lý riêng:
- Hai đoạn suy biến: so trực tiếp hai điểm.
- Một đoạn suy biến: kiểm tra điểm có thuộc đoạn kia không.
- Hai đoạn không suy biến: xác định có cùng đường đỡ bằng cross với q; nếu có thì giao các khoảng chiếu.

Phương pháp này **khác cấu trúc nhánh** của orientation+endpoint tests, nên hữu ích để phát hiện lỗi logic, nhất là ở các trường hợp biên.

### 13.1. Bộ test tối thiểu có chủ đích

| Hai đoạn | Kết quả |
|---|---|
| Hai đường chéo của hình vuông 0..4 | POINT (2,2) |
| AB=(0,0)→(4,4), CD=(0,3)→(4,0) | POINT (12/7,12/7) |
| Hai đoạn chung đúng đầu mút | POINT ở đầu mút |
| Đầu mút của đoạn này nằm trong đoạn kia | POINT, chữ T |
| Hai đoạn đồng tuyến chồng độ dài dương | OVERLAP |
| Hai đoạn đồng tuyến chỉ chạm ranh giới | POINT |
| Hai đoạn đồng tuyến tách rời | NONE |
| Hai đoạn song song khác đường | NONE |
| Hai AABB chồng nhưng đoạn không cắt | NONE |
| Hai đoạn dọc đồng tuyến | OVERLAP tính theo y |
| Hai đoạn cùng đường dốc âm | OVERLAP chính xác |
| Một đoạn là điểm và nằm trên đoạn kia | POINT |
| Một đoạn là điểm ở ngoài đoạn kia | NONE |
| Hai đoạn đều là cùng một điểm | POINT |
| Hai đoạn đều là hai điểm khác nhau | NONE |
| Hai đoạn dài từ Long.MIN_VALUE tới Long.MAX_VALUE | Phân loại đúng và giao (-1/2,-1/2) |

### 13.2. Property-based tests

Sinh nhiều tọa độ nguyên nhỏ, gồm số âm/0/dương, với cặp điểm đầu mút bất kỳ. Với mỗi trường hợp:
1. So kết quả thuật toán với oracle tham số sử dụng phân số nguyên chính xác.
2. Đổi thứ tự hai đoạn: kết quả phải bất biến.
3. Đảo hai đầu mút của mỗi đoạn: kết quả phải bất biến.
4. Nếu kết quả POINT, kiểm tra điểm nằm trên cả hai đoạn bằng tham số hữu tỉ.
5. Nếu OVERLAP, kiểm tra hai đầu đoạn chung nằm trên cả hai đoạn, và đoạn chung là cực đại.

Để tăng tỷ lệ gặp biên đồng tuyến, không chỉ sinh tọa độ độc lập mà hãy **cố ý sinh bốn điểm trên một đường** bằng cách chọn gốc P và vectơ v nguyên, rồi lấy P+t_iv với nhiều t_i nguyên. Bổ sung những đoạn suy biến v=(0,0) và cả x cố định để kiểm tra đường thẳng đứng.

Kiểm thử ngẫu nhiên không thay chứng minh. Nó đặc biệt hữu ích để bắt lỗi nhánh điều kiện, thứ tự đầu mút, phân số âm và so sánh khi hai hình chiếu có ranh giới chung.

## 14. Những lỗi phổ biến

1. **Chỉ kiểm tra đường thẳng vô hạn cắt nhau**, không kiểm tra điểm giao có thuộc cả hai đoạn.
2. **Chỉ kiểm tra AABB**, dù hộp bao chồng chưa đủ để kết luận giao.
3. **Chỉ dùng hai orientation** rồi quên hai orientation đảo vai trò đoạn, gây false positive.
4. **Bắt buộc mọi orientation khác 0**, bỏ sót chạm đầu mút.
5. **Dùng dấu < thay vì ≤** cho đoạn đóng, loại mất trường hợp chạm ranh giới.
6. **Coi orientation=0 là thuộc đoạn**, bỏ điều kiện min/max.
7. **Trả POINT ngay khi phát hiện một đầu mút trên đoạn đối phương**, quên đồng tuyến chồng thành OVERLAP.
8. **Không xử lý hai đoạn đồng tuyến**, chỉ dựa vào cặp dấu trái ngược.
9. **Coi đoạn đồng tuyến gặp đúng đầu mút là OVERLAP độ dài dương**, dù tập giao chỉ có một điểm.
10. **Không xử lý đoạn suy biến**, vì orient(A,A,P) luôn bằng 0.
11. **Tính hệ số góc bằng chia** và gặp mẫu 0 ở đoạn đứng hoặc đoạn suy biến.
12. **Dùng phép trừ tọa độ long trước khi chuyển sang BigInteger**, tràn xảy ra trước khi đổi kiểu.
13. **Lấy trị tuyệt đối Long.MIN_VALUE như số long bình thường**, vẫn tràn vì −Long.MIN_VALUE không biểu diễn được trong long.
14. **Tính tích hai định thức long để xét dấu** và bị overflow.
15. **Dùng EPS tuyệt đối tùy tiện cho tọa độ nguyên**, gộp sai điểm gần đường thẳng.
16. **Dùng double để tính định hướng của long lớn**, mất thông tin nguyên khi chuyển đổi.
17. **Ép giao điểm hữu tỉ thành long bằng phép chia nguyên**, đánh mất phần phân số.
18. **Quên chuẩn hóa dấu mẫu số và gcd**, khiến cùng một điểm có nhiều biểu diễn khác nhau.
19. **Không kiểm tra mẫu số den=0 trước khi tính t**, gây chia cho 0 ở các đường song song.
20. **Dùng thứ tự lex để lấy overlap khi chưa xác định đồng tuyến**, hoàn toàn không hợp lệ cho hai đoạn khác đường.
21. **Chỉ so x trong bài đồng tuyến**, sai với đường thẳng đứng có x cố định.
22. **Giả định y tăng khi x tăng**, sai với đường có hệ số góc âm.
23. **Không chuẩn hóa chiều đoạn OVERLAP**, khiến kết quả đổi theo thứ tự nhập đầu mút.
24. **Không kiểm tra tính đối xứng của API**, dù giao hai tập điểm không phụ thuộc thứ tự cặp.
25. **Không phân biệt giao một điểm với chồng vô số điểm**, làm mất thông tin quan trọng cho bài toán lớn hơn.
26. **Dùng số thực và sau đó so Point bằng ==**, sai do sai số tọa độ.
27. **Chỉ test hai đoạn cắt vuông góc ở điểm nguyên**, không kiểm tra giao điểm phân số.
28. **Bỏ các ca đầu mút, suy biến, đồng tuyến, tọa độ cực trị**, khiến code chỉ đúng bài đơn giản.
29. **Dùng một oracle dựa trên chính hàm orientation giống hệt code chính**, khó phát hiện lỗi chung.
30. **Không đọc rõ quy ước đoạn đóng/mở và có tính tiếp xúc hay không**, dẫn đến tranh cãi đáp án mặc dù thuật toán khác quy ước.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Có những dạng giao nào của hai đoạn thẳng đóng?

**Đáp án:** NONE, POINT và OVERLAP (chung một đoạn độ dài dương).

**Câu 2.** Ý nghĩa orient(A,B,P)>0?

**Đáp án:** P nằm bên trái đường thẳng có hướng A→B, tương ứng quay ngược chiều kim đồng hồ.

**Câu 3.** Khi orient(A,B,P)=0 có chắc P thuộc AB?

**Đáp án:** Không. Còn cần P nằm trong hộp bao của A,B trên cả hai trục.

**Câu 4.** Điều kiện giao nghiêm ngặt khi không điểm nào thẳng hàng?

**Đáp án:** o1 và o2 trái dấu nghiêm ngặt, đồng thời o3 và o4 trái dấu nghiêm ngặt.

**Câu 5.** Vì sao bốn orientation đều bằng 0 cần xử lý riêng?

**Đáp án:** Hai đoạn có thể chồng thành một đoạn, chỉ chung một điểm hoặc hoàn toàn rời nhau trên cùng đường đỡ.

**Câu 6.** Vì sao không dùng phép tính hệ số góc để giải mọi trường hợp?

**Đáp án:** Đoạn thẳng đứng và đoạn suy biến có mẫu số 0; cross product không cần phép chia.

**Câu 7.** Vì sao lọc AABB không đủ chứng minh giao nhau?

**Đáp án:** Hộp bao có thể chồng nhưng hai đoạn nằm ở các hướng không cắt trong phần hữu hạn.

**Câu 8.** Giao của AB=(0,0)→(5,0) và CD=(2,0)→(7,0)?

**Đáp án:** OVERLAP [(2,0)..(5,0)].

**Câu 9.** Giao của AB=(0,0)→(2,0) và CD=(2,0)→(5,0)?

**Đáp án:** POINT (2,0), vì chỉ chung một đầu mút.

**Câu 10.** Giao của AB=(0,0)→(4,4) và CD=(0,3)→(4,0)?

**Đáp án:** POINT (12/7,12/7).

**Câu 11.** Nếu A=B, orientation(A,B,P) có cho biết P nằm trên đoạn suy biến không?

**Đáp án:** Không. Nó bằng 0 với mọi P; cần kiểm tra P trùng A hoặc dùng kiểm tra thuộc đoạn có hộp bao.

**Câu 12.** Vì sao phải chuyển từng tọa độ long sang BigInteger trước khi trừ?

**Đáp án:** Hiệu của hai tọa độ long có thể vượt giới hạn long, nên chuyển sau khi trừ sẽ không phục hồi giá trị thật.

**Câu 13.** Làm sao trả giao có tọa độ không nguyên chính xác?

**Đáp án:** Lưu số hữu tỉ num/den bằng BigInteger, chuẩn hóa dấu mẫu và rút gọn gcd.

**Câu 14.** Đổi AB thành BA có đổi giao hình học không?

**Đáp án:** Không. Hướng có thể đổi dấu orientation, nhưng tập điểm của đoạn không đổi.

**Câu 15.** Vì sao không dùng một epsilon cố định cho mọi dữ liệu thực?

**Đáp án:** Sai số phụ thuộc tỷ lệ giá trị và mô hình đo; EPS tuyệt đối có thể phân loại sai các cấu hình gần thẳng hàng.

**Câu 16.** Với hai đường chéo có tọa độ long cực trị đối xứng, giao là gì?

**Đáp án:** POINT (−1/2,−1/2), vì Long.MIN_VALUE+Long.MAX_VALUE=−1.

**Câu 17.** Làm sao kiểm thử độc lập với orientation-based algorithm?

**Đáp án:** Dùng biểu thức tham số t,u với các phép so hữu tỉ chính xác, cùng phép xử lý riêng trường hợp song song/đồng tuyến.

**Câu 18.** Nếu đề chỉ cần boolean, có bắt buộc dựng RationalPoint không?

**Đáp án:** Không. Chỉ các predicate orientation, onSegment và overlap là đủ kết luận giao hay không.

**Ghi nhớ:** Giao hai đoạn thẳng **đóng** cần phân biệt **không giao, giao một điểm và chồng đoạn**. Hãy dùng **cross product/orientation chính xác**, bổ sung **onSegment** cho đầu mút, xử lý **đồng tuyến trước** để không nhầm OVERLAP thành POINT, và chỉ tính tọa độ giao hữu tỉ khi thật sự cần. Với tọa độ long, **chuyển từng số sang BigInteger trước khi trừ hoặc nhân** để không mất tính đúng vì overflow.
