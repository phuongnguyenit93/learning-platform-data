# Nội suy đa thức và đánh giá sai số

## Mục tiêu

Trong nhóm **Thuật toán số**, bài toán **nội suy đa thức** (*polynomial interpolation*) xây dựng một đa thức khớp những giá trị đã biết tại các **nút nội suy**. Nhưng khớp điểm dữ liệu **không tự bảo đảm** dự đoán tốt ở giữa các nút hoặc khi ngoại suy. Vì vậy, việc nội suy phải được học cùng với **đánh giá sai số**.

Cho n+1 cặp:

\[
(x_0,y_0),\ldots,(x_n,y_n)
\]

với `x_i` **đôi một phân biệt**, có duy nhất một đa thức `P_n` bậc **không vượt quá n** sao cho:

\[
\boxed{P_n(x_i)=y_i,\quad i=0,\ldots,n.}
\]

Nếu giá trị dữ liệu được sinh từ một hàm thật f, tức `y_i=f(x_i)`, sai số nội suy ở x là:

\[
\boxed{R_n(x)=f(x)-P_n(x).}
\]

Bài học này giải thích:

- Định lý tồn tại/duy nhất, vai trò các nút và hệ Vandermonde.
- **Lagrange**, **Newton với sai phân chia** và **barycentric Lagrange**.
- Tính toán O(n²) khi tiền xử lý, O(n) mỗi truy vấn bằng Newton Horner hoặc barycentric.
- Công thức sai số theo **đạo hàm bậc n+1**, điều kiện áp dụng và ví dụ `f(x)=\sin x`.
- **Sai số xấp xỉ**, **nhiễu dữ liệu** và **sai số dấu phẩy động**.
- **Hàm Lebesgue** và mức khuếch đại nhiễu.
- **Runge phenomenon**, nút cách đều, nút **Chebyshev**, spline và hồi quy.
- Chương trình **Java 17+** tự chạy, có stdout đối chiếu độc lập.
- Kiểm thử, lỗi thường gặp và bài tập có lời giải.

---

## 1. Phát biểu bài toán và ví dụ mở đầu

Giả sử có dữ liệu:

| x | y |
| ---: | ---: |
| −1 | 0 |
| 0 | 1 |
| 2 | 9 |

Đa thức:

\[
P(x)=(x+1)^2=x^2+2x+1
\]

khớp cả ba điểm:

\[
P(-1)=0,\quad P(0)=1,\quad P(2)=9.
\]

Vì có ba nút phân biệt, đa thức nội suy **bậc ≤2** là duy nhất. Nó tình cờ có bậc thực tế bằng 2.

Nếu ba điểm là `(0,1),(1,3),(2,5)`, đa thức nội suy duy nhất lại là `P(x)=2x+1`, bậc thực tế **1**. Do đó “n+1 nút ⇒ đa thức bậc không vượt quá n”, **không phải luôn đúng bậc n**.

### 1.1. Nội suy chính xác và dữ liệu bị nhiễu

Nếu `y_i=f(x_i)`, dữ liệu được xem là các mẫu **chính xác** của hàm f.

Nếu cảm biến trả:

\[
\tilde y_i=f(x_i)+\eta_i,
\]

với `\eta_i` là sai số phép đo, đa thức nội suy được dựng từ dữ liệu ấy thỏa:

\[
\tilde P_n(x_i)=\tilde y_i,
\]

không nhất thiết thỏa `\tilde P_n(x_i)=f(x_i)`.

Đây là lý do một đa thức **khớp hoàn toàn các phép đo** vẫn có thể sai so với hiện tượng thật.

### 1.2. Phân biệt nội suy, hồi quy và ngoại suy

**Nội suy:** buộc đa thức đi qua mọi cặp `(x_i,y_i)`.

**Hồi quy:** chọn tham số mô hình để giảm một hàm mất mát (chẳng hạn bình phương sai số) và có thể **không** đi qua mọi điểm.

**Ngoại suy:** dùng đa thức tại x **ngoài khoảng** từ nút nhỏ nhất đến lớn nhất. Ngoại suy có thể không đáng tin ngay cả khi các điểm nội suy được khớp chính xác.

---

## 2. Định lý tồn tại và duy nhất

**Định lý:** Cho n+1 nút x_i đôi một khác nhau và giá trị y_i bất kỳ. Tồn tại duy nhất một đa thức thực P bậc ≤n sao cho `P(x_i)=y_i`.

### 2.1. Chứng minh tính duy nhất

Giả sử P,Q là hai đa thức bậc ≤n cùng thỏa mọi điều kiện. Đặt:

\[
S(x)=P(x)-Q(x).
\]

Vì:

\[
S(x_i)=P(x_i)-Q(x_i)=0,
\]

nên S có n+1 nghiệm phân biệt. Nhưng một đa thức khác 0 bậc ≤n chỉ có tối đa n nghiệm phân biệt trên trường thực. Do đó S≡0, suy ra P=Q.

### 2.2. Chứng minh tồn tại

Công thức Lagrange ở mục 3 xây được một đa thức bậc ≤n đi qua mọi nút; vậy nó chứng minh tồn tại. Kết hợp chứng minh duy nhất, ta có định lý.

### 2.3. Khi các x_i trùng nhau

Dữ liệu:

```text
(1,2)
(1,5)
```

mâu thuẫn, vì không có hàm đơn trị nào đồng thời nhận hai giá trị khác nhau tại x=1.

Ngay cả khi hai bản ghi trùng cả x và y, ràng buộc ấy là **lặp lại**; nó không thêm một điều kiện độc lập cho tính duy nhất khi đếm số nút.

Các công thức sai phân chia và barycentric sẽ xuất hiện mẫu `x_i-x_j`. Nếu x_i=x_j, xảy ra phép chia cho 0. Bài mẫu chọn hợp đồng **từ chối mọi nút trùng**, thay vì tự ý gộp hoặc xử lý nội suy Hermite (bài toán khác cần thông tin đạo hàm).

### 2.4. Quan hệ với Vandermonde

Viết:

\[
P_n(x)=a_0+a_1x+\cdots+a_nx^n.
\]

Thay x_i tạo hệ tuyến tính với ma trận:

\[
V=
\begin{bmatrix}
1&x_0&\cdots&x_0^n\\
1&x_1&\cdots&x_1^n\\
\vdots&\vdots&\ddots&\vdots\\
1&x_n&\cdots&x_n^n
\end{bmatrix}.
\]

Định thức:

\[
\boxed{\det V=\prod_{0\le i<j\le n}(x_j-x_i).}
\]

Nếu các nút phân biệt, định thức khác 0 nên hệ xác định duy nhất hệ số của đa thức.

Tuy nhiên, **giải trực tiếp hệ Vandermonde bằng double** có thể không ổn định khi các x_i phân bố kém hoặc bậc lớn. Tính duy nhất về mặt toán học không bảo đảm thuật toán số nào cũng cho kết quả đáng tin.

---

## 3. Nội suy Lagrange

Với mỗi nút i, định nghĩa đa thức cơ sở:

\[
\boxed{
L_i(x)=
\prod_{\substack{0\le j\le n\\j\ne i}}
\frac{x-x_j}{x_i-x_j}.
}
\]

Do các nút khác nhau, mẫu số luôn khác 0.

**Tính chất nút:**

\[
L_i(x_k)=
\begin{cases}
1&k=i,\\
0&k\ne i.
\end{cases}
\]

Đa thức nội suy:

\[
\boxed{P_n(x)=\sum_{i=0}^{n}y_iL_i(x).}
\]

### 3.1. Chứng minh công thức

Tại x=x_k, mọi L_i với i≠k đều bằng 0, chỉ L_k(x_k)=1. Vì vậy:

\[
P_n(x_k)=\sum_i y_iL_i(x_k)=y_k.
\]

Mỗi L_i bậc ≤n, nên P_n cũng có bậc ≤n. Điều này vừa dựng được đa thức nội suy, vừa chứng minh tồn tại.

### 3.2. Ví dụ ba nút

Với `x=[-1,0,2]`:

\[
L_0(x)=\frac{x(x-2)}{3},
\]

\[
L_1(x)=-\frac{(x+1)(x-2)}{2},
\]

\[
L_2(x)=\frac{x(x+1)}{6}.
\]

Với `y=[0,1,9]`:

\[
P_2(x)=0L_0(x)+1L_1(x)+9L_2(x)
=(x+1)^2.
\]

Tại x=0.5:

\[
\boxed{P_2(0.5)=2.25}.
\]

Tại x=3:

\[
\boxed{P_2(3)=16}.
\]

Mặc dù x=3 nằm ngoài [−1,2], ví dụ này vẫn đúng hoàn toàn vì hàm gốc chính là một đa thức bậc ≤2. **Không khái quát kết quả ấy cho ngoại suy những hàm khác**.

### 3.3. Tổng các cơ sở

Vì đa thức hằng 1 được nội suy chính xác, ta có đẳng thức:

\[
\boxed{\sum_{i=0}^{n}L_i(x)=1.}
\]

Nó sẽ được dùng để đánh giá khuếch đại sai số phép đo.

### 3.4. Độ phức tạp

Tại một query x, tính n+1 cơ sở L_i, mỗi cơ sở có n thừa số, cần **O(n²)** phép số học theo cách trực tiếp.

Nó dễ chứng minh và làm oracle, nhưng nếu có rất nhiều query trên cùng các nút, ta nên tiền xử lý để đánh giá nhanh hơn.

---

## 4. Nội suy Newton với sai phân chia

Đa thức Newton có dạng:

\[
\boxed{
P_n(x)=c_0+c_1(x-x_0)+
c_2(x-x_0)(x-x_1)
+\cdots+
c_n\prod_{j=0}^{n-1}(x-x_j).
}
\]

Các hệ số c_k là **sai phân chia** (*divided differences*).

### 4.1. Định nghĩa

Bậc 0:

\[
f[x_i]=y_i.
\]

Bậc cao hơn:

\[
\boxed{
f[x_i,\ldots,x_{i+k}]
=
\frac{
f[x_{i+1},\ldots,x_{i+k}]
-
f[x_i,\ldots,x_{i+k-1}]
}{
x_{i+k}-x_i
}.
}
\]

Hệ số:

\[
c_k=f[x_0,\ldots,x_k].
\]

### 4.2. Ví dụ tính tay

Với:

```text
x = [-1,0,2]
y = [ 0,1,9]
```

Sai phân bậc 1:

\[
f[-1,0]=\frac{1-0}{0-(-1)}=1,
\]

\[
f[0,2]=\frac{9-1}{2-0}=4.
\]

Sai phân bậc 2:

\[
f[-1,0,2]=\frac{4-1}{2-(-1)}=1.
\]

Do đó:

\[
\boxed{c=[0,1,1].}
\]

Và:

\[
P(x)=0+1(x+1)+1(x+1)x=(x+1)^2.
\]

### 4.3. Cập nhật tại chỗ

Giả mã (m=n+1 nút):

```text
DIVIDED_DIFFERENCES(x,y):
    c = copy(y)
    m = length(x)

    for order = 1..m-1:
        for i = m-1 downTo order:
            c[i] =
                (c[i]-c[i-1]) /
                (x[i]-x[i-order])

    return c
```

**Phải duyệt i giảm dần** ở cùng một order. Nếu đi từ trái sang phải, c[i−1] đã có thể bị cập nhật và không còn là sai phân của bậc trước.

### 4.4. Horner theo cơ sở Newton

Khi đã có c, đánh giá tại z mà không tính mọi tích từ đầu:

```text
NEWTON_HORNER(x,c,z):
    value=c[m-1]

    for i=m-2 downTo 0:
        value = value*(z-x[i]) + c[i]

    return value
```

Tại z=0.5:

```text
value=1
value=1*(0.5-0)+1=1.5
value=1.5*(0.5-(-1))+0=2.25
```

Nó là Horner lồng theo các nhân tử `(z-x_i)`, **không phải** coi c[i] là hệ số của `x^i`.

### 4.5. Độ phức tạp

- Tiền xử lý sai phân chia: **O(m²)**.
- Lưu m hệ số: **O(m)**.
- Mỗi lần đánh giá Newton Horner: **O(m)**.
- q lần đánh giá sau tiền xử lý: **O(m²+qm)**.

Dạng Newton còn thuận tiện khi bổ sung một nút mới vào cuối thứ tự nút, vì có thể giữ hệ số cũ và tính thêm hệ số sai phân chia mới. Không thể chỉ nối y mới mà bỏ bước tính hệ số.

---

## 5. Công thức barycentric Lagrange

Đặt:

\[
\boxed{
w_i=\frac1{\prod_{j\ne i}(x_i-x_j)}.
}
\]

Với z **khác tất cả nút**, giá trị nội suy:

\[
\boxed{
P_n(z)=
\frac{\displaystyle\sum_i\frac{w_i y_i}{z-x_i}}
{\displaystyle\sum_i\frac{w_i}{z-x_i}}.
}
\]

Nếu z=x_k, trả ngay:

\[
\boxed{P_n(x_k)=y_k}.
\]

Không được tính tỉ số ở trên khi z trùng nút vì sẽ chia cho 0.

### 5.1. Suy ra công thức

Đặt:

\[
\omega(z)=\prod_{j=0}^{n}(z-x_j).
\]

Với z khác nút:

\[
L_i(z)=\omega(z)\frac{w_i}{z-x_i}.
\]

Từ `\sum_iL_i(z)=1`:

\[
\omega(z)\sum_i\frac{w_i}{z-x_i}=1.
\]

Thay vào `P_n(z)=\sum_i y_iL_i(z)`, ta thu được công thức barycentric.

### 5.2. Trọng số ví dụ

Với `x=[-1,0,2]`:

\[
w_0=\frac13,\quad
w_1=-\frac12,\quad
w_2=\frac16.
\]

Barycentric trả `P(0.5)=2.25`, khớp Lagrange và Newton.

### 5.3. Chi phí

Với m nút:

- Tính w_i bằng tích ngây thơ: **O(m²)**.
- Một query sau tiền xử lý: **O(m)**.
- Lưu m trọng số: **O(m)**.
- q query: **O(m²+qm)**.

Vì tử và mẫu cùng nhân một hệ số nếu tất cả w_i được nhân cùng c≠0, có thể **chuẩn hóa đồng thời trọng số** mà không đổi giá trị toán học. Tuy nhiên nếu đã overflow/underflow **khi tính trọng số**, chuẩn hóa về sau không khôi phục được thông tin.

### 5.4. Lưu ý về ổn định

Dạng barycentric thường hữu ích để tính nội suy trong số học dấu phẩy động, nhưng **không tuyệt đối chính xác**:

- Tính trọng số có thể mất độ chính xác nếu nút rất gần nhau.
- Bậc rất cao có thể làm trọng số overflow/underflow.
- Tử và mẫu có thể triệt tiêu khi ngoại suy.
- Query rất gần nút có thể nhạy.
- Trọng số chỉ phụ thuộc x_i, nên y_i thay đổi không cần tính lại trọng số, nhưng điều đó không có nghĩa sai số đo bị loại bỏ.

Đừng dùng một ngưỡng gần bằng tuyệt đối tùy ý để tự biến query gần x_i thành x_i: làm thế có thể đổi giá trị cần hỏi.

---

## 6. Sai số nội suy và phần dư

Giả sử `y_i=f(x_i)` là giá trị chính xác, f có đạo hàm liên tục đến bậc n+1 trên một khoảng chứa các nút và điểm query x.

Khi đó tồn tại `\xi` trên khoảng bao trùm các nút và x sao cho:

\[
\boxed{
f(x)-P_n(x)=
\frac{f^{(n+1)}(\xi)}{(n+1)!}
\prod_{i=0}^{n}(x-x_i).
}
\]

Nếu x trùng nút, sai số bằng 0. Nếu x khác nút, công thức có thể chứng minh bằng Rolle.

### 6.1. Phác thảo chứng minh

Đặt:

\[
\omega(t)=\prod_{i=0}^{n}(t-x_i)
\]

và với x không trùng nút:

\[
K=\frac{f(x)-P_n(x)}{\omega(x)}.
\]

Xét:

\[
g(t)=f(t)-P_n(t)-K\omega(t).
\]

g có n+2 nghiệm: n+1 nút và x. Theo Rolle lặp n+1 lần, tồn tại `\xi` mà:

\[
g^{(n+1)}(\xi)=0.
\]

Do `P_n^{(n+1)}=0` và `\omega^{(n+1)}=(n+1)!`:

\[
0=f^{(n+1)}(\xi)-K(n+1)!.
\]

Vậy:

\[
K=\frac{f^{(n+1)}(\xi)}{(n+1)!}.
\]

Thế lại định nghĩa K cho công thức phần dư.

### 6.2. Cận sai số

Nếu:

\[
|f^{(n+1)}(t)|\le M
\]

trên khoảng cần xét, thì:

\[
\boxed{
|f(x)-P_n(x)|
\le
\frac{M}{(n+1)!}
\prod_{i=0}^{n}|x-x_i|.
}
\]

Cận phụ thuộc **độ trơn của f**, **vị trí nút** và **vị trí query**. Không được kết luận rằng cứ tăng n là sai số sẽ giảm, vì đạo hàm bậc cao và tích các khoảng cách cũng thay đổi.

### 6.3. Cận chỉ tính sai số nội suy lý tưởng

Công thức giả sử:

- Giá trị tại nút đúng bằng f(x_i).
- Các phép tính là số học chính xác.
- f có đạo hàm cấp yêu cầu.
- Cận M đúng trên khoảng chứa cả nút và x.

Nếu có nhiễu ở y_i hoặc số học double, ta cần cộng thêm các nguồn sai số khác.

---

## 7. Ví dụ kiểm tra cận với f(x)=sin(x)

Lấy ba nút:

\[
x_0=0,\quad x_1=1,\quad x_2=2,
\]

\[
y_i=\sin(x_i).
\]

Đánh giá tại x=0.5:

\[
P_2(0.5)\approx0.5174410603.
\]

Hàm thật:

\[
\sin(0.5)\approx0.4794255386.
\]

Sai số tuyệt đối:

\[
\boxed{|P_2(0.5)-\sin(0.5)|
\approx0.0380155216.}
\]

### 7.1. Cận đạo hàm

Vì n=2:

\[
f'(x)=\cos x,
\quad f''(x)=-\sin x,
\quad f'''(x)=-\cos x.
\]

Trên [0,2]:

\[
|f'''(x)|\le1.
\]

Chọn M=1. Tích khoảng cách:

\[
|(0.5-0)(0.5-1)(0.5-2)|
=|0.5(-0.5)(-1.5)|
=0.375.
\]

Do đó:

\[
|R_2(0.5)|
\le\frac{1}{3!}\cdot0.375
=\boxed{0.0625}.
\]

Đối chiếu:

\[
\boxed{0.038016\le0.062500}.
\]

**Cận trên không phải sai số thật.** Nó là giới hạn được chứng minh cho dữ liệu/hàm đáp ứng điều kiện.

### 7.2. Ở nút và ngoài khoảng

Tại x=0,1,2, đa thức nội suy lý tưởng khớp chính xác sin.

Nếu cần ngoại suy tại x=10, **không được dùng cận M được chứng nhận riêng trên [0,2]**. Định lý sai số cần khoảng chứa cả x=10 và các nút. Ngay khi điều kiện trơn vẫn đúng, tích `\prod|x-x_i|` có thể rất lớn ở ngoại suy xa.

---

## 8. Ba loại sai số và sự khác nhau

### 8.1. Sai số xấp xỉ

Ngay cả khi dữ liệu chính xác:

\[
E_{\text{interp}}(x)=f(x)-P_n(x)
\]

có thể khác 0 giữa các nút. Đạo hàm bậc n+1 giúp đánh giá nó trong những điều kiện phù hợp.

### 8.2. Sai số dữ liệu

Nếu quan sát:

\[
\tilde y_i=f(x_i)+\eta_i,
\]

thì nội suy `\tilde P_n` đi qua dữ liệu bị nhiễu. Thay đổi `\tilde P_n-P_n` được kiểm soát bởi các hàm cơ sở Lagrange và hàm Lebesgue.

### 8.3. Sai số làm tròn

Với `double`:

- Một số thập phân có thể không biểu diễn chính xác.
- Mẫu số sai phân nhỏ khuếch đại sai số.
- Phép cộng trừ các số gần nhau có thể mất chữ số có nghĩa.
- Trọng số có thể underflow/overflow.
- Các công thức tương đương toán học có thể cho kết quả cuối khác vài bit.

### 8.4. Conditioning và numerical stability

**Điều kiện (conditioning)** là độ nhạy vốn có của bài toán: dữ liệu đổi rất nhỏ thì kết quả đổi bao nhiêu?

**Độ ổn định số (numerical stability)** là tính chất của cách tính: thuật toán có hạn chế việc tăng sai số làm tròn hay không?

Một thuật toán ổn định vẫn có thể khó cho kết quả chính xác nếu bài toán **rất nhạy**, đặc biệt với nút kém và bậc cao.

---

## 9. Hàm Lebesgue và nhiễu dữ liệu

Từ Lagrange:

\[
P_n(x)=\sum_{i=0}^{n}y_iL_i(x).
\]

Nếu mỗi giá trị bị nhiễu `\eta_i`:

\[
\tilde P_n(x)-P_n(x)
=\sum_{i=0}^{n}\eta_iL_i(x).
\]

Nếu `|\eta_i|\le\varepsilon` thì:

\[
|\tilde P_n(x)-P_n(x)|
\le\varepsilon\sum_i|L_i(x)|.
\]

Định nghĩa **hàm Lebesgue**:

\[
\boxed{\lambda_n(x)=\sum_{i=0}^{n}|L_i(x)|.}
\]

Cận:

\[
\boxed{|\tilde P_n(x)-P_n(x)|
\le\varepsilon\lambda_n(x).}
\]

### 9.1. Tính chất

Vì `\sum_i L_i(x)=1`:

\[
\lambda_n(x)\ge
\left|\sum_iL_i(x)\right|=1.
\]

Tại nút x_k, `L_k(x_k)=1` và các L_i khác 0, nên `\lambda_n(x_k)=1`.

**Hằng số Lebesgue** trên [a,b]:

\[
\Lambda_n=\max_{x\in[a,b]}\lambda_n(x)
\]

đo cận khuếch đại nhiễu trong chuẩn đều trên khoảng.

### 9.2. Ví dụ nút 0,1,2 tại x=0.5

Các cơ sở:

\[
L_0(0.5)=0.375,
\]

\[
L_1(0.5)=0.75,
\]

\[
L_2(0.5)=-0.125.
\]

Tổng:

\[
0.375+0.75-0.125=1.
\]

Hàm Lebesgue:

\[
\boxed{\lambda_2(0.5)=1.25}.
\]

Nếu mỗi phép đo có nhiễu tuyệt đối ≤0.01, sai số do nhiễu tại x=0.5 bị chặn bởi:

\[
0.01\cdot1.25=\boxed{0.0125}.
\]

### 9.3. Chỉ một phép đo thay đổi

Nếu chỉ y_1 ở nút x_1=1 được tăng 0.01, hai dữ liệu khác giữ nguyên:

\[
\tilde P(0.5)-P(0.5)
=0.01L_1(0.5)
=\boxed{0.0075}.
\]

Chương trình Java dùng chính ví dụ này để in đầu ra.

### 9.4. Ghép cận nhiễu và sai số nội suy

Với dữ liệu có nhiễu:

\[
f(x)-\tilde P_n(x)
=[f(x)-P_n(x)]+[P_n(x)-\tilde P_n(x)].
\]

Suy ra:

\[
|f(x)-\tilde P_n(x)|
\le|f(x)-P_n(x)|
+\varepsilon\lambda_n(x).
\]

Nếu có cận M:

\[
\boxed{
|f(x)-\tilde P_n(x)|
\le
\frac{M}{(n+1)!}\prod_i|x-x_i|
+
\varepsilon\lambda_n(x).
}
\]

**Chú ý:** cận trên chưa tự tính sai số làm tròn của chương trình double.

### 9.5. Liên hệ xấp xỉ tốt nhất

Gọi `E_n(f)` là sai số đều nhỏ nhất khi xấp xỉ hàm liên tục f bằng các đa thức bậc ≤n trên [a,b]. Với các nút nằm trong khoảng:

\[
\|f-P_n\|_\infty
\le(1+\Lambda_n)E_n(f).
\]

Vì vậy một tập nút có Lebesgue constant lớn có thể làm nội suy kém ngay cả khi tồn tại một đa thức bậc n xấp xỉ f tốt.

---

## 10. Hiện tượng Runge và nút Chebyshev

Xét hàm:

\[
\boxed{f(x)=\frac1{1+25x^2},\quad x\in[-1,1].}
\]

Hàm này trơn. Nhưng nếu nội suy bằng một đa thức bậc cao qua nhiều **nút cách đều**, đa thức có thể dao động mạnh gần hai đầu khoảng và sai số tăng.

Đây là **Runge phenomenon**.

### 10.1. Vì sao tăng bậc không tự bảo đảm tốt hơn?

Nội suy chỉ bắt buộc khớp f tại các nút. Nó không buộc sai số nhỏ giữa các nút. Với nút kém:

- Các cơ sở Lagrange có độ lớn lớn.
- Hàm Lebesgue có thể tăng nhanh.
- Nhiễu dữ liệu và roundoff có thể bị khuếch đại.
- Đa thức có thể dao động lớn gần biên.

Không có định lý chung “cứ dùng thêm nút cách đều là sai số trên toàn khoảng giảm”.

### 10.2. Nút Chebyshev roots

Với m=n+1 nút trong [a,b]:

\[
\boxed{
x_k=\frac{a+b}{2}
+\frac{b-a}{2}
\cos\left(\frac{(2k+1)\pi}{2m}\right),
\quad k=0,\ldots,m-1.
}
\]

Các nút này dày hơn gần hai đầu khoảng, thường cho chất lượng nội suy đa thức toàn cục tốt hơn nút cách đều ở bậc cao.

Nút Chebyshev là **lựa chọn vị trí lấy mẫu**, không thay thế công thức Lagrange/Newton/barycentric.

### 10.3. Ví dụ định lượng

Dùng hàm Runge, **11 nút** (đa thức bậc ≤10), đánh giá sai số trên lưới 2001 điểm:

\[
z_j=-1+\frac{2j}{2000},\quad j=0,\ldots,2000.
\]

Kết quả gần đúng:

| Nút | Sai số tuyệt đối lớn nhất **trên lưới** |
| --- | ---: |
| 11 nút cách đều | **1.915643** |
| 11 nút Chebyshev | **0.109153** |

Những con số này là **cực đại trên lưới hữu hạn**, không phải chứng minh chính xác supremum trên toàn khoảng liên tục. Không suy ra Chebyshev luôn tốt hơn mọi cấu hình với mọi hàm.

### 10.4. Nếu không thể chọn nút

Dữ liệu đo thường đến từ các x_i cố định. Khi đó có thể:

- Nội suy **cục bộ bậc thấp**.
- Dùng **spline** theo từng khoảng.
- Dùng **hồi quy** nếu dữ liệu nhiễu.
- Chuẩn hóa thang x.
- Dùng phép tính độ chính xác cao hơn nếu roundoff là vấn đề chính.

Tăng độ chính xác số học **không thay đổi điều kiện toán học** của một bộ nút kém.

---

## 11. Java 17+: chương trình hoàn chỉnh

Mã độc lập sau:

- Kiểm tra các nút phân biệt, cùng số giá trị y, dữ liệu hữu hạn.
- Sao chép mảng đầu vào để tránh sửa dữ liệu ngoài ý muốn.
- Tính sai phân chia Newton và trọng số barycentric.
- Có ba hàm `newtonHorner`, `lagrangeDirect`, `barycentric`.
- Có `lebesgue` tại điểm query.
- Minh họa đa thức chính xác, sin và cận đạo hàm, nhiễu một mẫu, Runge với hai tập nút.
- Định dạng in 6 chữ số sau dấu thập phân bằng `Locale.ROOT`.
- Xử lý n=1 và dữ liệu lỗi.

Tệp **`PolynomialInterpolationErrorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;

public final class PolynomialInterpolationErrorDemo {

    public static final class Interpolant {
        private final double[] x;
        private final double[] y;
        private final double[] coefficients;
        private final double[] weights;

        public Interpolant(double[] nodes, double[] values) {
            Objects.requireNonNull(nodes, "nodes");
            Objects.requireNonNull(values, "values");

            if (nodes.length == 0
                    || nodes.length != values.length) {
                throw new IllegalArgumentException(
                        "Need equally many nonempty nodes and values");
            }

            x = nodes.clone();
            y = values.clone();

            for (int i = 0; i < x.length; i++) {
                if (!Double.isFinite(x[i])
                        || !Double.isFinite(y[i])) {
                    throw new IllegalArgumentException(
                            "All nodes and values must be finite");
                }
            }

            for (int i = 0; i < x.length; i++) {
                for (int j = i + 1; j < x.length; j++) {
                    if (x[i] == x[j]) {
                        throw new IllegalArgumentException(
                                "Duplicate x coordinates");
                    }
                }
            }

            int n = x.length;

            // Newton divided differences: O(n^2).
            coefficients = y.clone();

            for (int order = 1; order < n; order++) {
                for (int i = n - 1; i >= order; i--) {
                    coefficients[i] =
                            (coefficients[i]
                             - coefficients[i - 1])
                            / (x[i] - x[i - order]);
                }
            }

            // Barycentric weights: O(n^2).
            weights = new double[n];

            for (int i = 0; i < n; i++) {
                double w = 1.0;

                for (int j = 0; j < n; j++) {
                    if (i != j) {
                        w /= (x[i] - x[j]);
                    }
                }

                weights[i] = w;
            }
        }

        public double[] newtonCoefficients() {
            return coefficients.clone();
        }

        private static void checkQuery(double z) {
            if (!Double.isFinite(z)) {
                throw new IllegalArgumentException(
                        "Query must be finite");
            }
        }

        public double newtonHorner(double z) {
            checkQuery(z);

            int n = x.length;
            double result = coefficients[n - 1];

            for (int i = n - 2; i >= 0; i--) {
                result = result * (z - x[i])
                        + coefficients[i];
            }

            return result;
        }

        public double barycentric(double z) {
            checkQuery(z);

            for (int i = 0; i < x.length; i++) {
                if (z == x[i]) {
                    return y[i];
                }
            }

            double numerator = 0.0;
            double denominator = 0.0;

            for (int i = 0; i < x.length; i++) {
                double term = weights[i] / (z - x[i]);
                numerator += term * y[i];
                denominator += term;
            }

            return numerator / denominator;
        }

        public double lagrangeDirect(double z) {
            checkQuery(z);

            for (int i = 0; i < x.length; i++) {
                if (z == x[i]) {
                    return y[i];
                }
            }

            double result = 0.0;

            for (int i = 0; i < x.length; i++) {
                double basis = 1.0;

                for (int j = 0; j < x.length; j++) {
                    if (i != j) {
                        basis *= (z - x[j]) / (x[i] - x[j]);
                    }
                }

                result += y[i] * basis;
            }

            return result;
        }

        public double lebesgue(double z) {
            checkQuery(z);

            for (int i = 0; i < x.length; i++) {
                if (z == x[i]) {
                    return 1.0;
                }
            }

            double sum = 0.0;

            for (int i = 0; i < x.length; i++) {
                double basis = 1.0;

                for (int j = 0; j < x.length; j++) {
                    if (i != j) {
                        basis *= (z - x[j]) / (x[i] - x[j]);
                    }
                }

                sum += Math.abs(basis);
            }

            return sum;
        }
    }

    private static double runge(double z) {
        return 1.0 / (1.0 + 25.0 * z * z);
    }

    private static double maxRungeError(Interpolant model) {
        double maximum = 0.0;

        // Grid of 2001 points in [-1,1].
        for (int i = 0; i <= 2000; i++) {
            double z = -1.0 + 2.0 * i / 2000.0;
            double error =
                    Math.abs(model.barycentric(z) - runge(z));
            maximum = Math.max(maximum, error);
        }

        return maximum;
    }

    public static void main(String[] args) {
        Interpolant polynomial = new Interpolant(
                new double[] {-1.0, 0.0, 2.0},
                new double[] { 0.0, 1.0, 9.0});

        System.out.println(
                "Newton coefficients: "
                + Arrays.toString(
                        polynomial.newtonCoefficients()));

        System.out.printf(
                Locale.ROOT,
                "P(0.5) Newton: %.6f%n",
                polynomial.newtonHorner(0.5));

        System.out.printf(
                Locale.ROOT,
                "P(0.5) Lagrange: %.6f%n",
                polynomial.lagrangeDirect(0.5));

        System.out.printf(
                Locale.ROOT,
                "P(0.5) barycentric: %.6f%n",
                polynomial.barycentric(0.5));

        System.out.printf(
                Locale.ROOT,
                "P(0) node: %.6f%n",
                polynomial.barycentric(0.0));

        System.out.printf(
                Locale.ROOT,
                "P(3) extrapolated: %.6f%n",
                polynomial.newtonHorner(3.0));

        double[] sx = {0.0, 1.0, 2.0};
        double[] sy = {
                Math.sin(0.0),
                Math.sin(1.0),
                Math.sin(2.0)
        };

        Interpolant sinus = new Interpolant(sx, sy);
        double query = 0.5;
        double predicted = sinus.barycentric(query);
        double actual = Math.sin(query);

        double theoreticalBound =
                Math.abs(
                        (query - sx[0])
                        * (query - sx[1])
                        * (query - sx[2])) / 6.0;

        System.out.printf(
                Locale.ROOT,
                "sin(0.5) interpolated: %.6f%n",
                predicted);

        System.out.printf(
                Locale.ROOT,
                "sin(0.5) true: %.6f%n",
                actual);

        System.out.printf(
                Locale.ROOT,
                "sin absolute error: %.6f%n",
                Math.abs(predicted - actual));

        System.out.printf(
                Locale.ROOT,
                "sin error upper bound: %.6f%n",
                theoreticalBound);

        System.out.printf(
                Locale.ROOT,
                "Lebesgue at 0.5: %.6f%n",
                sinus.lebesgue(query));

        double[] noisy = sy.clone();
        noisy[1] += 0.01;

        Interpolant perturbed = new Interpolant(sx, noisy);

        System.out.printf(
                Locale.ROOT,
                "Perturb middle y by 0.01 effect: %.6f%n",
                perturbed.barycentric(query) - predicted);

        int count = 11;
        double[] uniformX = new double[count];
        double[] chebyshevX = new double[count];
        double[] uniformY = new double[count];
        double[] chebyshevY = new double[count];

        for (int i = 0; i < count; i++) {
            uniformX[i] = -1.0 + 2.0 * i / (count - 1);
            chebyshevX[i] = Math.cos(
                    (2.0 * i + 1.0)
                    * Math.PI / (2.0 * count));

            uniformY[i] = runge(uniformX[i]);
            chebyshevY[i] = runge(chebyshevX[i]);
        }

        Interpolant uniform =
                new Interpolant(uniformX, uniformY);
        Interpolant chebyshev =
                new Interpolant(chebyshevX, chebyshevY);

        System.out.printf(
                Locale.ROOT,
                "Runge uniform grid max error: %.6f%n",
                maxRungeError(uniform));

        System.out.printf(
                Locale.ROOT,
                "Runge Chebyshev grid max error: %.6f%n",
                maxRungeError(chebyshev));

        Interpolant constant = new Interpolant(
                new double[] {2.0},
                new double[] {5.0});

        System.out.printf(
                Locale.ROOT,
                "One node constant: %.6f%n",
                constant.newtonHorner(100.0));

        boolean duplicateRejected = false;
        try {
            new Interpolant(
                    new double[] {0.0, 1.0, 0.0},
                    new double[] {1.0, 2.0, 3.0});
        } catch (IllegalArgumentException ex) {
            duplicateRejected = true;
        }
        System.out.println(
                "Duplicate nodes rejected: " + duplicateRejected);

        boolean invalidNumberRejected = false;
        try {
            new Interpolant(
                    new double[] {0.0, Double.NaN},
                    new double[] {1.0, 2.0});
        } catch (IllegalArgumentException ex) {
            invalidNumberRejected = true;
        }
        System.out.println(
                "Nonfinite input rejected: " + invalidNumberRejected);

        boolean invalidQueryRejected = false;
        try {
            polynomial.barycentric(
                    Double.POSITIVE_INFINITY);
        } catch (IllegalArgumentException ex) {
            invalidQueryRejected = true;
        }
        System.out.println(
                "Nonfinite query rejected: " + invalidQueryRejected);

        boolean emptyRejected = false;
        try {
            new Interpolant(
                    new double[] {},
                    new double[] {});
        } catch (IllegalArgumentException ex) {
            emptyRejected = true;
        }
        System.out.println(
                "Empty data rejected: " + emptyRejected);
    }
}
```

### 11.1. Biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac PolynomialInterpolationErrorDemo.java
java PolynomialInterpolationErrorDemo
```

**Stdout kỳ vọng:**

```text
Newton coefficients: [0.0, 1.0, 1.0]
P(0.5) Newton: 2.250000
P(0.5) Lagrange: 2.250000
P(0.5) barycentric: 2.250000
P(0) node: 1.000000
P(3) extrapolated: 16.000000
sin(0.5) interpolated: 0.517441
sin(0.5) true: 0.479426
sin absolute error: 0.038016
sin error upper bound: 0.062500
Lebesgue at 0.5: 1.250000
Perturb middle y by 0.01 effect: 0.007500
Runge uniform grid max error: 1.915643
Runge Chebyshev grid max error: 0.109153
One node constant: 5.000000
Duplicate nodes rejected: true
Nonfinite input rejected: true
Nonfinite query rejected: true
Empty data rejected: true
```

### 11.2. Giải thích thiết kế

**Interpolant:** giữ các mảng nút, giá trị y, hệ số Newton và trọng số barycentric dưới dạng `private final`. Constructor **clone** input để dữ liệu không bị thay đổi ngoài ý muốn.

**Sai phân Newton:** khởi tạo `coefficients=y.clone()`, duyệt order từ 1 đến n−1, rồi i từ n−1 xuống order để tránh ghi đè thông tin.

**Newton Horner:** sau tiền xử lý, chạy một vòng O(n) tại query z, dùng `z-x[i]` và hệ số c.

**Barycentric:** nếu z trùng nút x_i thì trả y_i; nếu không, tính hai tổng của công thức.

**Lagrange trực tiếp:** nhân các thừa số cơ sở ở mỗi query, chậm hơn nhưng dễ đối chiếu.

**Lebesgue:** cộng trị tuyệt đối các cơ sở L_i; tại nút trả 1.

### 11.3. Quy tắc dữ liệu

- Mảng x/y null → `NullPointerException`.
- Mảng rỗng hoặc hai mảng khác chiều dài → `IllegalArgumentException`.
- Nút trùng x → `IllegalArgumentException`.
- NaN/Infinity trong x/y hoặc query → `IllegalArgumentException`.
- Một nút là hợp lệ, cho đa thức hằng.
- `-0.0==+0.0` trong Java, nên chúng được xem là hai nút trùng theo nghĩa toán học.

### 11.4. Giới hạn

Đây là mã giảng dạy dùng `double`, không phải bộ nội suy độ chính xác tùy ý. Với rất nhiều nút hoặc nút gần nhau, trọng số có thể underflow/overflow và sai phân chia có thể kém ổn định. Cần chuẩn hóa, sử dụng nút tốt hơn, chia đoạn hoặc các thuật toán chuyên dụng.

Đầu ra số thực được định dạng sáu chữ số thập phân. Các cách nội suy tương đương về toán học có thể khác nhau ở các bit cuối của double.

---

## 12. Đánh giá sai số thực nghiệm

### 12.1. Sai số tuyệt đối

Khi có f thật:

\[
\boxed{E_{\mathrm{abs}}(x)=|P_n(x)-f(x)|.}
\]

Nó có đơn vị như f và có ý nghĩa ngay cả khi f(x)=0.

### 12.2. Sai số tương đối

Khi `f(x)\ne0`:

\[
\boxed{E_{\mathrm{rel}}(x)=|P_n(x)-f(x)|/|f(x)|.}
\]

Nếu f gần 0, sai số tương đối có thể rất lớn ngay khi sai số tuyệt đối nhỏ; không nên dùng riêng chỉ số tương đối trong mọi trường hợp.

### 12.3. Cực đại trên lưới kiểm thử

Với các điểm z_j không nhất thiết là nút, đo:

\[
\max_j|P_n(z_j)-f(z_j)|.
\]

Lưới càng dày càng hữu ích để quan sát dao động, nhưng **cực đại trên lưới hữu hạn không mặc nhiên là cực đại liên tục đã chứng minh**.

### 12.4. Không đánh giá chỉ trên training nodes

Nội suy lý tưởng có:

\[
P_n(x_i)=y_i.
\]

Vì thế sai số tại các nút dữ liệu bằng 0 theo thiết kế. Điều đó **không** chứng minh kết quả tốt giữa các nút.

Nên dành điểm kiểm chứng độc lập hoặc dùng cận đạo hàm, thông tin nhiễu và lập luận mô hình.

### 12.5. Nếu không biết hàm thật

Với dữ liệu cảm biến, có thể không biết f tại các vị trí mới. Khi đó:

- Đo thêm các điểm kiểm chứng.
- Sử dụng tập validation không đưa vào xây nội suy.
- Kiểm tra tính phù hợp với mô hình vật lý.
- Ước lượng độ nhiễu cảm biến.
- Cân nhắc spline/hồi quy nếu mục tiêu là dự báo.

Không tự gọi sai số tại các nút là “độ chính xác dự báo”.

---

## 13. Chọn nội suy toàn cục, spline hay hồi quy?

### 13.1. Nội suy toàn cục

Một đa thức duy nhất đi qua tất cả điểm, tiện về lý thuyết và có các công thức Lagrange/Newton. Tuy nhiên bậc rất cao với nhiều nút cách đều có thể dao động mạnh (Runge).

### 13.2. Nội suy spline

**Cubic spline** dùng các đa thức bậc 3 trên từng khoảng nút, nối nhau theo điều kiện trơn thích hợp (thường tới đạo hàm bậc hai). Nó thường kiểm soát dao động tốt hơn một đa thức toàn cục bậc rất cao trên khoảng rộng.

### 13.3. Hồi quy

Nếu dữ liệu chứa nhiễu và mục tiêu là ước lượng xu hướng, **least squares/regularization** không buộc đi qua mọi điểm, có thể giảm overfitting và tổng quát hóa tốt hơn. Đây là bài toán khác nội suy chuẩn.

### 13.4. Ngoại suy xa

Nếu query nằm xa khoảng nút, các công thức nội suy vẫn trả số nhưng không bảo đảm tin cậy. Nên dùng mô hình phản ánh cấu trúc thật của hiện tượng, hoặc đánh giá độ nhạy và cận mở rộng trước khi kết luận.

---

## 14. So sánh công thức và chi phí

| Tiêu chí | Lagrange trực tiếp | Newton | Barycentric |
| --- | --- | --- | --- |
| Dạng | `\sum y_iL_i(x)` | Tích `(x-x_j)` với hệ số c | Tỉ số hai tổng trọng số |
| Tiền xử lý | Có thể không cần | O(n²) | O(n²) theo công thức cơ bản |
| Mỗi query | O(n²) | O(n) | O(n) |
| Dữ liệu lưu | x,y | x,y,c | x,y,w |
| Dễ thêm một nút | Cơ sở thay đổi | Có thể thêm hệ số | Cần cập nhật trọng số |
| Rủi ro | Tích và triệt tiêu | Sai phân chia nhạy nút gần | Trọng số và hai tổng nhạy |
| Query trùng nút | Khớp theo định nghĩa | Khớp theo toán học | Cần xử lý đặc biệt trong mã |

n là bậc tối đa, có n+1 nút; có thể thay bằng m=n+1 mà không đổi bậc lớn-O.

---

## 15. Những lỗi thường gặp

1. **Không kiểm tra nút trùng**, chia cho 0.
2. **Đếm n nút là đa thức bậc ≤n** mà quên n+1 nút cho bậc n.
3. **Tuyên bố một hàm duy nhất đi qua dữ liệu** thay vì đa thức bậc ≤n duy nhất.
4. **Coi Vandermonde giải bằng double luôn ổn định**.
5. **Nhầm y_i là hệ số Newton**, không tính sai phân chia.
6. **Duyệt cập nhật sai phân từ trái sang phải**, ghi đè hệ số.
7. **Dùng mẫu sai `x_i-x_{i-k}`**.
8. **Đánh giá Newton như đa thức hệ số đơn thức x^i**, sai.
9. **Không kiểm tra z trùng nút trong barycentric**, chia cho 0.
10. **Tưởng trọng số barycentric không thể overflow/underflow**.
11. **Tự gộp hai nút gần nhau bằng tolerance tùy ý**, đổi bài toán.
12. **Không kiểm tra NaN/Infinity** trong dữ liệu.
13. **Dùng training error bằng 0 làm bằng chứng dự đoán tốt**.
14. **Áp phần dư đạo hàm khi hàm không đủ trơn**.
15. **Dùng cận M trên miền không chứa điểm ngoại suy**.
16. **Nhầm upper bound với sai số thật**.
17. **Bỏ nhiễu dữ liệu**, nhất là từ phép đo.
18. **Bỏ sai số làm tròn double**.
19. **Không xét hàm Lebesgue** khi dữ liệu có nhiễu.
20. **Dùng relative error khi f=0**, phép chia không xác định.
21. **Coi grid max là cực đại liên tục đã chứng minh**.
22. **Cho rằng tăng bậc với nút cách đều luôn tốt**, quên Runge.
23. **Cho rằng Chebyshev luôn tốt hơn với mọi hàm và mọi nút**.
24. **Ngoại suy xa mà không kiểm tra mô hình**, có thể sai lớn.
25. **Nội suy bậc rất cao vào dữ liệu nhiều nhiễu**, dễ overfit.
26. **Không thử trường hợp một nút**, bỏ đa thức hằng.
27. **Không thử mảng rỗng/mảng khác độ dài**, phát sinh lỗi khó hiểu.
28. **Hoán vị x mà không hoán vị y tương ứng**, làm sai dữ liệu.
29. **Đòi ba cách double bằng nhau bit-for-bit**, quá nghiêm với sai số làm tròn.
30. **Không so với một đa thức gốc đã biết**, bỏ oracle có giá trị.
31. **Nhầm nội suy với least squares**, hai hợp đồng khác nhau.
32. **Không phân biệt conditioning và numerical stability**, phân tích sai nguyên nhân.

---

## 16. Kiểm thử độc lập

### 16.1. Kiểm tra tại nút

Trong số học chính xác:

\[
P_n(x_i)=y_i.
\]

Barycentric trong mã trả trực tiếp y_i nếu query bằng nút. Với Newton/double, một sai khác rất nhỏ có thể do roundoff; nên dùng tolerance hợp lý thay vì ép equality bit-for-bit.

### 16.2. Đa thức gốc đã biết

Dùng `f(x)=(x+1)^2`, nút −1,0,2, y=0,1,9.

Kiểm thử:

```text
P(0.5)=2.25
P(3)=16
```

Vì f bậc ≤2, sai số nội suy toán học bằng 0 ở **mọi x**, không chỉ các nút.

### 16.3. Đối chiếu ba biểu diễn

Tại các điểm z khác nút, so kết quả:

```text
newtonHorner(z)
lagrangeDirect(z)
barycentric(z)
```

Chọn dữ liệu nút phân biệt, phân bố tốt, bậc vừa phải và so trong tolerance số thực. Điều này phát hiện nhiều bug về công thức và thứ tự cập nhật.

### 16.4. Các hàm cơ sở

`L_i(x_j)=\delta_{ij}` và:

\[
\sum_iL_i(z)\approx1.
\]

Với nút 0,1,2, tại z=0.5:

```text
L0=0.375
L1=0.750
L2=-0.125
sum=1
lambda=1.25
```

### 16.5. Nhiễu một nút

Thay y_1 thành y_1+0.01:

\[
\tilde P(0.5)-P(0.5)=0.0075.
\]

Nếu mọi dữ liệu bị nhiễu ≤0.01, cận Lebesgue là 0.0125 ở z=0.5.

### 16.6. Sin và cận lý thuyết

Với f=sin, nút 0,1,2, query 0.5:

```text
P(0.5)           ~ 0.5174410603
sin(0.5)         ~ 0.4794255386
absolute error   ~ 0.0380155216
theoretical bound = 0.0625
```

Kiểm tra sai số thật nhỏ hơn cận 0.0625.

### 16.7. Runge và nút

Dùng 11 nút, lưới 2001 điểm: sai số tối đa trên lưới của nút cách đều khoảng 1.915643, Chebyshev khoảng 0.109153. Trường hợp này minh họa bậc cao và phân bố nút ảnh hưởng mạnh đến chất lượng giữa nút.

### 16.8. Đầu vào biên

Thử:

- 0 nút.
- Chỉ 1 nút.
- x/y khác độ dài.
- Có hai x trùng (kể cả +0.0 và −0.0).
- x hoặc y là NaN, Infinity.
- Query NaN, Infinity.
- Nút rất gần nhau, nhiều nút, ngoại suy xa để quan sát độ nhạy.

### 16.9. Kiểm thử ngẫu nhiên

1. Sinh m nút khác nhau, m nhỏ (1..8).
2. Chọn một đa thức f bậc ≤m−1 với hệ số nhỏ.
3. Sinh y_i=f(x_i).
4. Dựng ba cách nội suy.
5. So ở các điểm ngẫu nhiên với f(z).
6. Hoán vị đồng thời các cặp (x_i,y_i), xác minh kết quả toán học không đổi.
7. Tăng một y_i bởi `\eta`, đối chiếu thay đổi theo `\eta L_i(z)`.
8. Dùng tolerance phù hợp double, không đòi mọi phép số thực chính xác vô hạn.

---

## 17. Bài tập tự kiểm tra

### Bài 1
Phát biểu điều kiện để có duy nhất một đa thức bậc ≤n qua n+1 cặp dữ liệu.

### Bài 2
Vì sao nút x trùng nhưng y khác làm bài toán vô nghiệm?

### Bài 3
Chứng minh tính duy nhất bằng hiệu hai đa thức.

### Bài 4
Ba điểm `(0,1),(1,3),(2,5)` cho đa thức nội suy bậc thực tế mấy?

### Bài 5
Viết công thức L_i(x) của Lagrange.

### Bài 6
Vì sao L_i(x_j) bằng 1 khi i=j và bằng 0 khi i≠j?

### Bài 7
Với `(-1,0),(0,1),(2,9)`, tìm P(x).

### Bài 8
Tính P(0.5) và P(3) cho ví dụ trên.

### Bài 9
Định nghĩa sai phân chia bậc một và bậc hai.

### Bài 10
Tìm các hệ số Newton cho ví dụ ba nút.

### Bài 11
Viết giả mã Horner cho dạng Newton.

### Bài 12
Vì sao cần duyệt i từ phải qua trái khi cập nhật sai phân chia?

### Bài 13
Viết trọng số w_i và công thức barycentric khi z khác mọi nút.

### Bài 14
Khi query đúng nút, barycentric cần trả gì?

### Bài 15
So chi phí một query của Lagrange trực tiếp, Newton và barycentric.

### Bài 16
Viết công thức phần dư f(x)-P_n(x).

### Bài 17
Để dùng cận đạo hàm, f phải có tính chất gì trên khoảng nào?

### Bài 18
Tính cận sai số sin với nút 0,1,2 tại x=0.5.

### Bài 19
Phân biệt sai số nội suy với sai số nhiễu dữ liệu.

### Bài 20
Định nghĩa hàm Lebesgue và cận khuếch đại nhiễu.

### Bài 21
Với nút 0,1,2 tại x=0.5, tính các L_i và λ.

### Bài 22
Nếu chỉ y tại nút 1 tăng 0.01, giá trị nội suy tại 0.5 thay đổi bao nhiêu?

### Bài 23
Giải thích Runge phenomenon.

### Bài 24
Viết công thức n+1 nút Chebyshev roots trên [a,b].

### Bài 25
Cực đại sai số trên 2001 điểm có phải cực đại đã chứng minh trên khoảng liên tục không?

### Bài 26
Vì sao cận M trên [0,2] không được dùng tùy tiện cho x=10?

### Bài 27
Khi dữ liệu nhiễu, tại sao hồi quy có thể phù hợp hơn nội suy?

### Bài 28
Spline bậc ba có ưu điểm gì với dữ liệu dài?

### Bài 29
Phân biệt conditioning và stability.

### Bài 30
Nêu ít nhất bốn cách kiểm thử một triển khai Newton/barycentric.

### Đáp án

1. Có n+1 nút hoành độ đôi một khác nhau; duy nhất một đa thức bậc ≤n.
2. Hàm đơn trị không thể nhận hai y khác nhau tại cùng x.
3. Hiệu P−Q có n+1 nghiệm nhưng bậc ≤n, nên là đa thức không.
4. Bậc 1, `P(x)=2x+1`.
5. `L_i(x)=\prod_{j\ne i}(x-x_j)/(x_i-x_j)`.
6. Tại nút khác có thừa số 0; tại đúng nút mọi thừa số bằng 1.
7. `P(x)=(x+1)^2=x²+2x+1`.
8. `P(0.5)=2.25`, `P(3)=16`.
9. `f[x_i,x_j]=(y_j-y_i)/(x_j-x_i)`; bậc hai là hiệu hai sai phân bậc một chia khoảng cách hai nút ngoài.
10. `c=[0,1,1]`.
11. `v=c[n]`, với i=n−1..0: `v=v(z-x_i)+c_i`.
12. Để c[i−1] chưa bị ghi đè trong cùng một order.
13. `w_i=1/\prod_{j\ne i}(x_i-x_j)`; `P=(\sum w_i y_i/(z-x_i))/(\sum w_i/(z-x_i))`.
14. Trả y_i, tránh chia 0.
15. Lagrange trực tiếp O(n²); Newton và barycentric O(n) mỗi query sau tiền xử lý O(n²).
16. `f(x)-P_n(x)=f^{(n+1)}(\xi)\prod_i(x-x_i)/(n+1)!`.
17. f có đạo hàm liên tục đến bậc n+1 trên khoảng bao gồm x và tất cả nút.
18. `|(0.5)(-0.5)(-1.5)|/6=0.0625`.
19. Sai số nội suy tồn tại cả khi y_i chính xác; nhiễu là thay đổi các giá trị đầu vào.
20. `\lambda_n(x)=\sum|L_i(x)|`; `|\tilde P-P|\le\varepsilon\lambda_n(x)`.
21. `L0=0.375,L1=0.75,L2=-0.125,\lambda=1.25`.
22. `0.01\cdot0.75=0.0075`.
23. Với nút cách đều và bậc cao, đa thức có thể dao động lớn gần biên dù hàm trơn.
24. `x_k=(a+b)/2+((b-a)/2)\cos((2k+1)\pi/(2(n+1)))`.
25. Không, đó chỉ là cực đại trên lưới hữu hạn.
26. Khoảng của định lý phải bao gồm cả x=10 và các nút.
27. Hồi quy không buộc khớp mọi nhiễu và có thể cho dự đoán tổng quát tốt hơn.
28. Spline dùng đa thức bậc thấp ghép theo đoạn, thường tránh dao động toàn cục.
29. Conditioning là độ nhạy bài toán; stability là sự ổn định của thuật toán số.
30. Kiểm tra tại nút; đa thức gốc đã biết; so ba phương pháp; thử nhiễu; cận sin; Runge; NaN/nút trùng; ngoại suy.

---

## Ghi nhớ

Với n+1 nút phân biệt, **đa thức nội suy bậc ≤n tồn tại duy nhất**.

Ba cách biểu diễn:

1. **Lagrange:** `P_n(x)=\sum_i y_iL_i(x)`.
2. **Newton:** hệ số sai phân chia, đánh giá bằng Horner.
3. **Barycentric:** trọng số w_i, đánh giá O(n) mỗi query sau tiền xử lý.

Sai số nội suy với các mẫu chính xác của f đủ trơn:

\[
\boxed{
|f(x)-P_n(x)|
\le
\frac{M}{(n+1)!}
\prod_i|x-x_i|.
}
\]

Nếu các y_i bị nhiễu nhiều nhất ε:

\[
\boxed{
|\tilde P_n(x)-P_n(x)|
\le
\varepsilon\lambda_n(x).
}
\]

**Không nhầm** cận sai số xấp xỉ với sai số do nhiễu hoặc roundoff. Khớp mọi nút không bảo đảm sai số nhỏ giữa các nút hoặc khi ngoại suy. Với bậc cao, cần xem xét **Runge** và cách chọn nút **Chebyshev**; với dữ liệu dài/nhiễu, cân nhắc **spline** hoặc **hồi quy** và đánh giá trên dữ liệu độc lập.
