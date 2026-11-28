# Chi phí khấu hao của splay và một thao tác có thể vẫn tuyến tính

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt chính xác **chi phí xấu nhất của một thao tác**, **chi phí khấu hao trên một chuỗi thao tác** và **chi phí kỳ vọng theo phân phối xác suất**.
- Tự dựng một cây splay hợp lệ nhưng cao **Θ(n)**, chứng minh một lượt tìm và đưa nút sâu nhất lên gốc có thể tốn **Θ(n)** bước.
- Giải thích tại sao điều đó **không mâu thuẫn** với bảo đảm **O(log n) khấu hao** của splay tree.
- Hiểu vai trò của ba bước **zig**, **zig-zig**, **zig-zag**; giải thích vì sao **hai quay kép** có cấu trúc đặc biệt, thay vì chỉ quay đơn liên tiếp.
- Thiết lập **kích thước cây con** `s(v)`, **hạng** `r(v)=log₂s(v)` và **hàm thế** `Φ(T)=Σr(v)`; sử dụng công thức `ĉᵢ=cᵢ+ΔΦ`.
- Theo dõi lập luận của **Access Lemma** qua ba trường hợp, phép **cộng triệt tiêu (telescoping)** và cận trên tổng chi phí của chuỗi truy cập.
- Phân tích tác động của **cây khởi đầu có sẵn**, thao tác chèn/xóa, truy cập thất bại, tập khóa nóng và yêu cầu độ trễ theo từng request.
- Đọc mã Python tự chứa có đo **số nút ghé qua, số phép quay và hàm thế phục vụ học tập**, kiểm tra các ví dụ biên mà không đánh đồng bộ đếm logic với thời gian thực.
- Chọn splay, AVL hay Red–Black Tree phù hợp với bài toán dựa trên **độ trễ, thứ tự, tính cục bộ truy cập và đồng thời**.

## 1. Vấn đề: “O(log n) khấu hao” không có nghĩa mọi lần truy cập đều nhanh

Trong module `COMPUTER_SCIENCE_DATA_STRUCTURES`, ta đánh giá cấu trúc dữ liệu qua **bất biến, thao tác, thời gian và bộ nhớ**. Ở chương **Cây tìm kiếm cân bằng**, AVL và Red–Black Tree thường đảm bảo chiều cao **O(log n) sau mỗi cập nhật hoàn chỉnh**. Nhờ đó một lần tìm, thêm hay xóa mất **O(log n) trong trường hợp xấu nhất**, giả sử so sánh khóa có chi phí O(1).

**Splay tree** là cây tìm kiếm nhị phân (*BST*) **tự điều chỉnh**. Sau khi tìm được một nút, thuật toán sử dụng các phép quay để **đưa chính nút đó lên gốc**. Splay không buộc mọi cây con tuân theo chênh lệch chiều cao kiểu AVL, cũng không lưu bất biến màu kiểu Red–Black.

Điều này tạo ra hai phát biểu **đều đúng**:

1. **Một lần truy cập riêng lẻ** trên splay tree có thể tốn **Θ(n)** trong trường hợp xấu nhất.
2. **Chi phí khấu hao** của các thao tác splay chuẩn là **O(log n)**, hiểu theo giới hạn tổng chi phí trên chuỗi thao tác dưới giả định của phân tích.

Không có nghịch lý: một thao tác rất đắt có thể **thay đổi hình dạng cây** để những thao tác về sau rẻ hơn; phân tích khấu hao theo dõi cả chi phí và trạng thái tích lũy.

### 1.1. Một truy cập sâu trên cây hoàn toàn hợp lệ

Giả sử có năm khóa số nguyên:

```text
                50
               /
              40
             /
            30
           /
          20
         /
        10
```

Cây này hợp lệ theo bất biến BST: `10<20<30<40<50`. Nó có chiều cao **5 nút** (hay **4 cạnh**) dù chỉ chứa năm khóa. Khi tìm `10`:

- Đường tìm ghé `50→40→30→20→10`: **5 nút**.
- Splay `10` từ độ sâu 4 dùng **hai bước zig-zig trái–trái**, tổng **4 phép quay đơn**.
- `10` thành gốc; lần tìm `10` **ngay sau đó**, nếu không có thao tác nào xen vào, chỉ ghé một nút và không cần quay.

Mở rộng lên `n` khóa theo một chuỗi lệch: khóa sâu nhất có độ sâu `n-1`. Tìm nó đi qua **n nút**, còn splay cần **n-1 phép quay đơn**. Chi phí của **lần truy cập đó** vì thế là **Θ(n)**.

> Splay tree không bị coi là “sai” chỉ vì nó đang lệch. Bất biến bắt buộc của nó là **thứ tự BST**, không phải chiều cao logarit tại mọi thời điểm.

### 1.2. Ba cách diễn đạt chi phí cần phân biệt

| Cách đo | Câu hỏi | Ý nghĩa với splay |
| --- | --- | --- |
| **Worst-case một thao tác** | Trên trạng thái hợp lệ bất lợi nhất, thao tác này có thể tốn bao nhiêu? | Có thể **Θ(n)** |
| **Khấu hao (amortized)** | Tổng chi phí của một chuỗi thao tác được kiểm soát ra sao? | **O(log n)** trên mỗi thao tác theo phân tích chuẩn và điều kiện tương ứng |
| **Kỳ vọng (expected)** | Trung bình theo một phân phối xác suất đã nêu là bao nhiêu? | Không phải định nghĩa của bảo đảm khấu hao |
| **Đo thực nghiệm** | Trên dữ liệu, runtime và phần cứng này, có bao nhiêu lượt ghé nút/mili giây? | Phải đo thực tế, không suy ra từ Big O |

**Khấu hao không đồng nghĩa “xác suất cao”**, không yêu cầu thứ tự truy cập ngẫu nhiên và cũng không nói rằng *mọi* thao tác có giới hạn O(log n) riêng rẽ.

## 2. Splay tạo thay đổi gì sau một lần tìm?

Splay là chuỗi các phép **quay trái** và **quay phải** trên BST. Mỗi phép quay bảo toàn **thứ tự inorder**, nhưng thay đổi cha–con và chiều cao của một số cây con.

Quay trái tại `p` có con phải `x`:

```text
       p                          x
      / \                        / \
     A   x         --->         p   C
        / \                    / \
       B   C                  A   B
```

Tập khóa, quan hệ `A<p<B<x<C` và inorder không đổi. Quay phải là cấu hình đối xứng.

Trong phiên bản **bottom-up splay chuẩn**, đặt `x` là nút mục tiêu, `p=x.parent` và `g=p.parent`:

| Hình dạng | Trường hợp | Thao tác |
| --- | --- | --- |
| `p` là gốc, `x=p.left` | **Zig** trái | Quay phải tại `p` |
| `p` là gốc, `x=p.right` | **Zig** phải | Quay trái tại `p` |
| `x=p.left` và `p=g.left` | **Zig-zig LL** | Quay phải tại **`g` rồi `p`** |
| `x=p.right` và `p=g.right` | **Zig-zig RR** | Quay trái tại **`g` rồi `p`** |
| `x=p.right` và `p=g.left` | **Zig-zag LR** | Quay trái tại **`p`**, rồi phải tại **`g`** |
| `x=p.left` và `p=g.right` | **Zig-zag RL** | Quay phải tại **`p`**, rồi trái tại **`g`** |

### 2.1. Zig-zig: hai cạnh cùng hướng

```text
Trước (LL):                        Sau hai quay phải:

         g                                    x
        / \                                  / \
       p   D                                A   p
      / \                                      / \
     x   C                                    B   g
    / \                                          / \
   A   B                                        C   D
```

**Ông trước, cha sau**. Sau bước này, `x` lên **hai mức**, còn những phần cây con ở giữa vẫn nằm trong đúng khoảng khóa.

### 2.2. Zig-zag: hai cạnh ngược hướng

```text
Trước (LR):                        Sau quay trái p, phải g:

         g                                    x
        / \                                  / \
       p   D                                p   g
      / \                                  / \ / \
     A   x                                A  B C  D
        / \
       B   C
```

**Cha trước, ông sau**. Nút `x` trở thành khóa trung tâm giữa `p` và `g`.

### 2.3. Một lần splay có bao nhiêu phép quay?

Với nút thật `x` ban đầu ở độ sâu `d`, đo bằng số **cạnh từ gốc** trong một cây đang cố định và không có thao tác xen vào:

- Mỗi bước kép zig-zig/zig-zag làm độ sâu `x` giảm **2**.
- Một zig cuối, nếu còn, làm giảm **1**.
- Số vòng kép bằng `⌊d/2⌋`, số zig cuối bằng `d mod 2`.

Vì vậy, với phiên bản bottom-up trên:

\[
\operatorname{rotations}(\operatorname{splay}(x))
=2\left\lfloor\frac d2\right\rfloor+(d\bmod2)=d.
\]

Đây là **số phép quay đơn**, không phải toàn bộ số phép so sánh hoặc lệnh máy. Khi `x` ở độ sâu `n-1`, riêng phần quay có thể là **n-1=Θ(n)**. Tìm khóa trước khi quay cũng có thể là Θ(n).

## 3. Vì sao không thể kết luận từ một thao tác đắt?

Một lần splay chuyển nút vừa truy cập lên gốc, nên việc đọc lại **ngay cùng khóa** trở nên rẻ. Nhưng chỉ lập luận “lần sau rẻ hơn” vẫn **chưa đủ** để chứng minh O(log n) khấu hao cho **mọi chuỗi truy cập**: những truy cập xen kẽ có thể tiếp tục làm thay đổi gốc.

Muốn có bảo đảm tổng quát, cần một đại lượng đo **“mức độ dự trữ công việc”** trong hình dạng cây. Phân tích chuẩn dùng **phương pháp hàm thế (potential method)**:

1. Chỉ định một giá trị thế `Φ(T)≥0` cho mỗi trạng thái cây `T`.
2. Tính chi phí thực `c_i` của thao tác thứ `i`.
3. Tính **chi phí khấu hao** bằng chi phí thật cộng **độ biến thiên thế**.
4. Cộng qua chuỗi thao tác để các khoản tăng/giảm thế trung gian **triệt tiêu**.

Điểm mạnh của phương pháp này là không cần dự đoán khóa nào sẽ xuất hiện tiếp theo.

### 3.1. Định nghĩa kích thước, hạng và thế

Với một cây có `n≥1` nút thật, đặt:

\[
s(v)=\text{số nút thật trong cây con có gốc }v,
\quad r(v)=\log_2s(v),
\quad\Phi(T)=\sum_{v\in T}r(v).
\]

Những quy ước này có ý nghĩa:

- Lá thật: `s(v)=1`, nên `r(v)=0`.
- Gốc: `s(root)=n`, nên `r(root)=log₂n`.
- Nếu cây con tại `u` nằm trong cây con tại `v`, thì `s(u)≤s(v)` và `r(u)≤r(v)`.
- Vì `s(v)≥1`, mọi hạng đều **không âm** và `Φ(T)≥0`.
- Không bắt buộc **lưu `s(v)` hay `r(v)` trong từng nút** để cài splay; chúng phục vụ **chứng minh**.

Một cách chặn thế của bất kỳ cây n nút là:

\[
0\le\Phi(T)
\le \sum_{v\in T}\log_2n
=n\log_2n.
\]

**Lưu ý:** Cận thế trên không khẳng định mọi cây cân bằng đều có thế nhỏ nhất hay lớn nhất. Nó chỉ cần làm cận ban đầu cho phép cộng dồn.

### 3.2. Chi phí thực và chi phí khấu hao

Với thao tác thứ `i`, cây trước là `T_{i-1}`, cây sau là `T_i`. Đặt:

\[
\widehat c_i
=c_i+\Phi(T_i)-\Phi(T_{i-1})
=c_i+\Delta\Phi_i.
\]

- Nếu `Φ` **giảm**, `ΔΦ_i<0`: chi phí khấu hao nhỏ hơn chi phí thật, vì thao tác đã **giải phóng phần dự trữ**.
- Nếu `Φ` **tăng**, `ΔΦ_i>0`: chi phí khấu hao lớn hơn chi phí thật, xem như để dành cho tương lai.
- Nếu `Φ` không đổi, chi phí khấu hao bằng chi phí thật.

Cộng với `m` thao tác:

\[
\sum_{i=1}^m\widehat c_i
=\sum_{i=1}^m c_i+\Phi(T_m)-\Phi(T_0).
\]

Suy ra:

\[
\boxed{\sum_{i=1}^m c_i
=\sum_{i=1}^m\widehat c_i
+\Phi(T_0)-\Phi(T_m).}
\]

Đây là điểm mấu chốt: **biến thiên thế ở những trạng thái trung gian triệt tiêu**, chỉ còn **thế đầu và thế cuối**. Nếu có cận khấu hao tốt, ta suy ra cận tổng thực tế.

## 4. Ví dụ tính hàm thế trên cây lệch năm nút

Quay lại cây lệch trái:

```text
             50
            /
           40
          /
         30
        /
       20
      /
     10
```

Các kích thước cây con từ dưới lên là:

| Nút | `10` | `20` | `30` | `40` | `50` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `s(v)` trước khi splay | 1 | 2 | 3 | 4 | 5 |

Tổng thế ban đầu:

\[
\Phi(T_0)
=\log_2 1+\log_2 2+\log_2 3+\log_2 4+\log_2 5
=\log_2(120).
\]

Splay `10` bằng **hai zig-zig LL**, gồm bốn quay đơn, cho:

```text
             10
               \
                40
               /  \
              20   50
                \
                 30
```

Các kích thước mới:

| Nút | `10` | `20` | `30` | `40` | `50` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `s(v)` sau splay | 5 | 2 | 1 | 4 | 1 |

Do đó:

\[
\Phi(T_1)=\log_2(5\cdot2\cdot1\cdot4\cdot1)=\log_2(40).
\]

Với **chi phí bằng số quay đơn** của lần splay:

\[
c=4,\qquad
\Delta\Phi=\log_2(40/120)=-\log_2 3,
\qquad
\widehat c=4-\log_2 3\approx2{,}415.
\]

Trong ví dụ này, một phần chi phí bốn phép quay được “trả” bằng việc **thế giảm**. Cũng có lần splay làm **thế tăng**, nên không thể kết luận **mọi** lần splay đều giảm thế. Bảo đảm tổng quát cần chứng minh cận cho **từng loại bước**.

**Quan trọng:** Thế ở đây là đại lượng **tính lại trên toàn cây để minh họa**. Một cài đặt splay chuẩn **không cần tính `Φ` O(n)** trong mỗi thao tác; làm vậy sẽ vô tình biến chương trình đo hiệu năng thành một phép duyệt toàn cây.

## 5. Bổ đề truy cập (Access Lemma)

Bổ đề truy cập là nền tảng phân tích khấu hao của splay tree. Xét **một cây có tập nút không đổi** trong thời gian splay một nút thật `x`. Gọi `n` là số nút và dùng:

\[
r(v)=\log_2s(v),\quad
\Phi(T)=\sum_v r(v).
\]

Chọn **chi phí của một bước là số phép quay đơn** (zig = 1, zig-zig/zig-zag = 2). Nếu `root_0` là gốc **trước** khi splay, thì:

\[
\boxed{
\widehat c_{\operatorname{splay}(x)}
\le 3\bigl(r(root_0)-r_0(x)\bigr)+1
\le3\log_2n+1.
}
\]

Ở đây `r_0(x)` là hạng của `x` **trước** thao tác. Nếu tính thêm thời gian tìm khóa, lượt ghé nút tỉ lệ với số cạnh đã đi qua, nên tổng chi phí thực tế của truy cập vẫn thuộc **O(log n) khấu hao**, chỉ thay đổi hệ số hằng.

### 5.1. Ý tưởng chung của chứng minh

Một phép quay chỉ làm thay đổi kích thước cây con của **những nút trực tiếp tham gia phép quay**; các nút nằm trong những cây con `A,B,C,D` khác vẫn giữ **cùng tập hậu duệ của riêng chúng** và vì thế giữ nguyên hạng.

Đặt:

- `r(v)`: hạng **trước bước splay cục bộ**.
- `r'(v)`: hạng **sau bước**.
- `x` là nút mục tiêu; `p` là cha; `g` là ông.

Sau một bước kép, `x` thay `g` làm **gốc của cùng một cây con**, nên:

\[
s'(x)=s(g),\qquad r'(x)=r(g).
\]

Đối với bước zig cuối, thay `g` bằng `p` trong quan hệ trên.

Mục tiêu là chứng minh:

\[
\begin{aligned}
\text{zig:}\quad &1+\Delta\Phi
\le1+3\bigl(r'(x)-r(x)\bigr),\\
\text{zig-zig/zig-zag:}\quad
&2+\Delta\Phi\le3\bigl(r'(x)-r(x)\bigr).
\end{aligned}
\]

Khi cộng các bước của một lần splay, **chênh lệch hạng `r'(x)-r(x)` triệt tiêu theo chuỗi**. Trong một lần splay hoàn chỉnh, chỉ có thể có **tối đa một zig** ở cuối, do đó xuất hiện **hằng số +1** trong kết quả.

### 5.2. Một bất đẳng thức logarit dùng trong chứng minh

Với `a,b>0`:

\[
ab\le\left(\frac{a+b}{2}\right)^2
\quad\Rightarrow\quad
\log_2a+\log_2b
\le2\log_2(a+b)-2.
\]

Nếu hai cây con **không giao nhau**, đều nằm trong một cây có `N` nút, thì `a+b≤N`, suy ra:

\[
\log_2a+\log_2b\le2\log_2N-2.
\]

Trong một bước kép, ta sẽ chọn `a,b` là **kích thước hai cây con rời nhau** để áp dụng bất đẳng thức này. Đây là phần toán học giải thích vì sao **hai quay có cấu trúc đặc biệt** đủ để kiểm soát hàm thế.

### 5.3. Trường hợp zig: chỉ một quay

Trước bước zig, `p` là gốc cây con đang xét và `x` là con trực tiếp. Sau quay:

\[
r'(x)=r(p),\qquad r'(p)\le r'(x).
\]

Chỉ `x,p` có thể đổi hạng, nên:

\[
\begin{aligned}
\widehat c_{\mathrm{zig}}
&=1+r'(x)+r'(p)-r(x)-r(p)\\
&=1+r'(p)-r(x)\\
&\le1+r'(x)-r(x)\\
&\le1+3\bigl(r'(x)-r(x)\bigr).
\end{aligned}
\]

Hạng `x` không giảm khi đi lên, vì cây con mới của `x` chứa cây con cũ của nó. Lập luận đúng cho cả **zig trái** và **zig phải**.

### 5.4. Trường hợp zig-zig: hai quay cùng hướng

Xét LL; RR đối xứng.

```text
Trước:                             Sau:

            g                               x
           / \                             / \
          p   D                           A   p
         / \                                 / \
        x   C                               B   g
       / \                                     / \
      A   B                                   C   D
```

Gọi `N=s(g)=s'(x)`, `a=s(x)` (trước bước) và `b=s'(g)` (sau bước). Hai tập nút tương ứng với `a` và `b` **rời nhau** trong cây con `N`, nên:

\[
a+b\le N
\quad\Rightarrow\quad
r(x)+r'(g)\le2r(g)-2.
\tag{1}
\]

Vì `x` thuộc cây con của `p` trước bước nên `r(p)≥r(x)`; vì `p` thuộc cây con của `x` sau bước nên `r'(p)≤r'(x)=r(g)`.

Từ công thức biến thiên thế, chỉ ba nút `x,p,g` đổi hạng:

\[
\begin{aligned}
\widehat c_{\mathrm{zigzig}}
&=2+r'(x)+r'(p)+r'(g)-r(x)-r(p)-r(g)\\
&=2+r'(p)+r'(g)-r(x)-r(p)\\
&\le2+r(g)+r'(g)-2r(x)\\
&\le3\bigl(r(g)-r(x)\bigr)\\
&=3\bigl(r'(x)-r(x)\bigr).
\end{aligned}
\]

Dòng bất đẳng thức áp chót dùng trực tiếp **(1)**. Đây là chỗ thứ tự **quay tại ông trước, rồi tại cha** tạo cấu hình phân hoạch thích hợp.

### 5.5. Trường hợp zig-zag: hai quay ngược hướng

Xét LR; RL đối xứng.

```text
Trước:                             Sau:

            g                               x
           / \                             / \
          p   D                           p   g
         / \                             / \ / \
        A   x                           A  B C  D
           / \
          B   C
```

Sau bước, hai cây con tại `p` và `g` **rời nhau**, đều nằm trong cây con gốc `x` có `N=s'(x)=s(g)` nút:

\[
s'(p)+s'(g)\le N
\quad\Rightarrow\quad
r'(p)+r'(g)\le2r(g)-2.
\tag{2}
\]

Lại có `r(p)≥r(x)`. Suy ra:

\[
\begin{aligned}
\widehat c_{\mathrm{zigzag}}
&=2+r'(x)+r'(p)+r'(g)-r(x)-r(p)-r(g)\\
&=2+r'(p)+r'(g)-r(x)-r(p)\\
&\le2r(g)-r(x)-r(p)\\
&\le2\bigl(r(g)-r(x)\bigr)\\
&\le3\bigl(r'(x)-r(x)\bigr).
\end{aligned}
\]

Vậy cả **zig-zig** và **zig-zag** đều đáp ứng cận cho một bước kép, dù hình dạng sau quay khác nhau.

### 5.6. Cộng các bước: telescoping

Gọi các hạng của cùng nút `x` khi vừa bắt đầu và sau mỗi bước lần lượt là:

\[
r_0(x),r_1(x),\ldots,r_t(x).
\]

Cộng bất đẳng thức của các bước, với tối đa một zig:

\[
\begin{aligned}
\widehat c_{\mathrm{splay}(x)}
&\le3\sum_{j=1}^{t}\bigl(r_j(x)-r_{j-1}(x)\bigr)+1\\
&=3\bigl(r_t(x)-r_0(x)\bigr)+1.
\end{aligned}
\]

Khi `x` là gốc toàn cây, `s_t(x)=n` nên `r_t(x)=log₂n=r(root_0)`. Đồng thời `r_0(x)≥0`. Ta thu được:

\[
\widehat c_{\mathrm{splay}(x)}
\le3\bigl(\log_2n-r_0(x)\bigr)+1
\le3\log_2n+1.
\]

Đây là chứng minh **cận chi phí khấu hao**, không phải chứng minh mỗi lần splay có **ít hơn 3log₂n+1 phép quay**. Với một cây lệch, số quay thật vẫn có thể bằng `n-1`.

## 6. Từ một lần splay đến tổng chi phí của nhiều lần truy cập

Phân biệt ba trường hợp khởi đầu giúp hiểu đúng ý nghĩa cận khấu hao.

### 6.1. Tập `n` khóa cố định, cây ban đầu tùy ý

Giả sử ta đã có một BST chứa `n≥1` nút thật, không thêm hay xóa, rồi thực hiện `m` lần truy cập **có splay**. Ở mỗi lần:

\[
\widehat c_i\le3\log_2n+1.
\]

Cộng `m` lần và dùng công thức triệt tiêu:

\[
\begin{aligned}
\sum_{i=1}^{m}c_i
&=\sum_{i=1}^{m}\widehat c_i
+\Phi(T_0)-\Phi(T_m)\\
&\le m(3\log_2n+1)+n\log_2n.
\end{aligned}
\]

Do đó:

\[
\boxed{\text{Tổng số quay}\ =O(m\log(n+1)+n\log(n+1)).}
\]

Khi `m` đủ lớn so với `n`, phần **chi phí ban đầu** được phân bổ qua nhiều lượt truy cập và ta có trung bình khấu hao O(log n).

Khi `m=1` và cây đầu vào tùy ý, phần `n log n` **không biến mất**. Vì thế, công thức tổng quát không mâu thuẫn với ví dụ **một lượt truy cập Θ(n)**.

**Phân biệt:** Bổ đề truy cập phát biểu **chi phí khấu hao của từng lần splay** là O(log n) theo hàm thế, chứ **không** khẳng định bất kỳ một đoạn ngắn nào của chuỗi trên cây khởi đầu tùy ý có **chi phí thực trung bình** luôn O(log n) khi bỏ qua thế đầu.

### 6.2. Bắt đầu từ cây rỗng và thêm các khóa

Khi bắt đầu từ cây rỗng, `Φ(T_0)=0`. Phân tích các thao tác **chèn/xóa đúng theo thuật toán splay chuẩn** cho phép kiểm soát phần thay đổi thế do **số nút tăng/giảm**, ngoài các lần splay.

Với `m` thao tác tìm/chèn/xóa trên cây khởi đầu rỗng, số nút không thể vượt quá `m`. Một cách phát biểu tổng quát:

\[
\text{Tổng chi phí}=O(m\log(m+1)),
\]

tương ứng **O(log(m+1)) khấu hao mỗi thao tác** trong chuỗi. Cận này không phụ thuộc giả định rằng các khóa được truy cập theo phân phối ngẫu nhiên.

Định lý đầy đủ cho cập nhật yêu cầu tính cả phần **thêm/bỏ nút**, không thể chỉ lấy Access Lemma của **cây kích thước cố định** rồi bỏ qua thay đổi kích thước.

### 6.3. Vì sao chèn bằng BST rồi splay vẫn O(log n) khấu hao?

Một cách chèn phổ biến:

1. Đi theo đường BST đến khóa cũ hoặc vị trí lá mới.
2. Nếu khóa mới, tạo nút ở lá đúng vị trí.
3. Splay nút mới hoặc nút đã tồn tại lên gốc.

Với cây ban đầu có `n` nút:

- **Đường tìm** dài bằng độ sâu nút mới/cũ cộng một hằng số.
- **Splay** sau khi đưa nút mới vào cây có thể được chặn theo Access Lemma cho kích thước `n+1`.
- Việc thêm một lá làm tăng kích thước của mỗi tổ tiên trên đường đi **đúng một đơn vị**. Nếu các kích thước cũ trên đường từ lá lên gốc là các số nguyên tăng nghiêm ngặt `s_1<s_2<\dots<s_t≤n`, phần tăng thế không vượt:

\[
\sum_{j=1}^{t}\log_2\frac{s_j+1}{s_j}
\le\sum_{q=1}^{n}\log_2\frac{q+1}{q}
=\log_2(n+1).
\]

Nút lá mới có hạng `log₂1=0`. Như vậy, **sự thay đổi số nút không tạo chi phí khấu hao vượt bậc logarit**, và tổng chèn vẫn O(log n) khấu hao.

Với khóa trùng trong Map, ta chỉ cập nhật `value` rồi splay nút đã có; không thêm nút và không tăng `n`.

### 6.4. Vì sao xóa bằng splay rồi nối cũng O(log n) khấu hao?

Một thuật toán xóa điển hình:

1. Tìm khóa, splay nút đó lên gốc.
2. Bỏ gốc và tách `L=root.left`, `R=root.right`.
3. Nếu `L` rỗng, lấy `R` làm cây mới.
4. Nếu `L` không rỗng, splay **`max(L)`** lên gốc `L` rồi gắn `R` làm con phải.

Chi phí tìm và các lần splay được phân tích theo Access Lemma. Sau khi bỏ gốc, hai cây con `L,R` giữ nguyên kích thước của những cây con bên trong chúng; ta đã bỏ hạng `log₂n` của gốc cũ khỏi hàm thế. Sau khi splay `max(L)`, việc gắn `R` chỉ làm tăng kích thước cây con của **gốc mới** từ `|L|` lên `n-1`, nên phần tăng thế do nối là:

\[
\log_2\frac{n-1}{|L|}\le\log_2(n-1)
\quad\text{khi }|L|\ge1,\ n\ge2.
\]

Phần sửa liên kết cục bộ ngoài tìm/splay có thời gian O(1). Do đó, **xóa chuẩn O(log n) khấu hao**; một lần riêng lẻ vẫn có thể O(n) vì phải tìm sâu và/hoặc splay `max(L)` trên cây lệch.

Nếu không tìm thấy khóa, một chính sách thông dụng là **splay nút cuối trên đường tìm thất bại**, rồi báo khóa thiếu. Việc xử lý này cũng thuộc phân tích truy cập có splay; nó có thể thay đổi hình dạng dù **không thay tập khóa**.

### 6.5. Kích thước biến đổi và cách diễn đạt O(log n)

Trong câu “mỗi thao tác O(log n) khấu hao”, `n` thường là **quy mô cây tại thời điểm xét** hoặc **cận trên kích thước trong chuỗi**, tùy định lý được dùng. Để tránh nói thiếu:

- Với **truy cập trên cây có `n` nút không đổi**, sử dụng trực tiếp Access Lemma.
- Với **chuỗi chèn/xóa**, theo dõi sự thay đổi `n` và các biến động hàm thế.
- Với **cây có sẵn từ ngoài**, đừng quên khoản **thế ban đầu** khi đổi cận khấu hao thành cận tổng chi phí thực.

## 7. Vì sao chỉ dùng zig đơn liên tục không phải cùng một chứng minh?

Giả sử `x` có ông `g` và cha `p`. Ta có thể lặp việc **quay `x` trực tiếp qua cha** cho đến gốc. Cách làm này gọi là **move-to-root bằng zig đơn**.

Nó có thể đưa đúng nút lên gốc và giữ BST, nhưng **khác thuật toán splay chuẩn**, vì với hai cạnh cùng hướng nó quay **cha trước**, trong khi **zig-zig chuẩn quay ông trước**.

```text
Ban đầu (LL):       Hai zig đơn:        Zig-zig chuẩn:

      30                 10                  10
     /                     \                   \
    20                      30                  20
   /                       /                      \
  10                      20                       30
```

Hai cách có cùng inorder `10,20,30`, nhưng phân bố cây con và biến thiên của `Φ` có thể khác nhau. Vì vậy không thể nói “đều quay `x` lên gốc nên đều có **cùng** Access Lemma”.

Trong chứng minh ở mục 5, ta sử dụng **hai cây con rời nhau** sau mỗi **cặp quay chuẩn** để khai thác bất đẳng thức logarit. Nếu đổi thứ tự quay, các phân hoạch cần cho bất đẳng thức ấy có thể không còn đúng.

**Bài học phương pháp:** Khi một định lý hiệu năng gắn với thuật toán cụ thể, không được dùng định lý đó cho một biến thể chỉ vì **đầu ra cùng đúng về mặt chức năng**.

## 8. Những điều cận O(log n) khấu hao không bảo đảm

### 8.1. Không có hạn mức trễ cho từng request

Giả sử một ứng dụng phải phản hồi mỗi yêu cầu trong một ngân sách độ trễ rất chặt. Một cây splay có thể cao `n` và một lần tìm khóa sâu nhất vẫn cần `Θ(n)` lượt ghé nút và quay.

Khấu hao O(log n) **không tự bảo đảm** giới hạn đó. Trong trường hợp này, AVL hoặc Red–Black Tree — với chiều cao **O(log n) mọi thời điểm** — có bảo đảm đơn thao tác phù hợp hơn về mặt lý thuyết.

### 8.2. Không bảo đảm cây luôn cân bằng sau splay

Một chuỗi chèn khóa tăng dần, mỗi lần splay nút mới lên gốc, tạo hình:

```text
             50
            /
           40
          /
         30
        /
       20
      /
     10
```

Cây vẫn hợp lệ. Splay ưu tiên **đưa khóa vừa dùng lên gốc**, không phải giữ `|height(left)-height(right)|≤1`.

### 8.3. Không tự chứng minh splay nhanh hơn một cấu trúc khác

AVL và Red–Black cũng cho O(log n) **khấu hao** vì chúng đã có O(log n) **xấu nhất từng thao tác**. Chỉ so Big O là chưa đủ để khẳng định splay thắng.

Cần xét **tính cục bộ truy cập**, số quay, độ trễ phân vị cao, ghi bộ nhớ, cache, cách cấp phát và chất lượng thư viện. Khi `get` của splay làm đổi cấu trúc, **đọc đồng thời** cũng cần đồng bộ phù hợp.

### 8.4. Không bảo đảm mọi thao tác không splay vẫn được phân tích như splay

Nếu một API có `peek` chỉ duyệt BST rồi trả giá trị **mà không splay**, nó không thực hiện các bước thay đổi hàm thế mà Access Lemma sử dụng. Lượt `peek` có thể tốn Θ(n).

Đừng trộn một chuỗi chủ yếu dùng `peek` với một chuỗi dùng `get` có splay, rồi áp cận khấu hao O(log n) một cách vô điều kiện.

### 8.5. “Một khóa nóng” không loại bỏ mọi chi phí

Nếu gọi `get(k)` thành công hai lần **liên tiếp, không có cập nhật xen vào**, lần thứ hai đọc ngay tại gốc nên chi phí O(1).

Nhưng một chuỗi xen kẽ nhiều khóa có thể làm gốc đổi liên tục. Những kết quả mạnh hơn về **working set**, **dynamic finger** và **truy cập theo thứ tự** phân tích lợi ích của tính cục bộ trên chuỗi, không cho phép kết luận “khóa gần đây sẽ luôn được tìm trong O(1) ở mọi lần”.

## 9. Ví dụ Python: đo chi phí thật và hàm thế trên cùng một cây

Để thấy sự khác biệt giữa **số quay thật** và **chi phí khấu hao**, ta xây dựng một Splay Map tối giản có thể:

- Chèn khóa mới bằng **BST insert rồi splay**.
- Tìm thành công/thất bại, splay **nút thấy hoặc nút thật cuối đường tìm**.
- Xóa bằng **splay khóa**, bỏ gốc, rồi **splay `max(L)` và nối `R`**.
- Đếm **số nút ghé**, **số phép quay đơn** và loại bước splay.
- Kiểm tra **BST, `parent`, số nút, chiều cao** mà không giả định cây cân bằng.
- **Tính lại `Φ(T)` O(n) chỉ để quan sát**. Hàm này không thuộc thuật toán splay chuẩn.

Ví dụ dùng khóa **`int` phân biệt**, giá trị có thể là bất kỳ đối tượng. Chèn khóa trùng sẽ cập nhật giá trị ở nút cũ, không tạo thêm nút. Phương thức `get` trả `default` khi khóa không tồn tại; `contains` phân biệt được khóa thiếu với khóa có giá trị `None`.

### 9.1. Cài đặt Splay Map hoàn chỉnh

Đoạn mã sau là **một khối Python tự chứa**, chỉ dùng thư viện chuẩn.

```python
from math import log2


class Node:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.parent = None


class SplayMap:
    def __init__(self):
        self.root = None
        self.size = 0
        self.visits = 0
        self.rotations = 0
        self.cases = {
            name: 0 for name in (
                "zig_L", "zig_R",
                "zigzig_LL", "zigzig_RR",
                "zigzag_LR", "zigzag_RL",
            )
        }
        self.last_trace = []  # Chỉ ghi các bước ở lần splay gần nhất.

    @staticmethod
    def _check_key(key):
        if type(key) is not int:
            raise TypeError("Ví dụ yêu cầu khóa thuộc kiểu int")

    def _rotate_left(self, a):
        b = a.right
        assert b is not None

        a.right = b.left
        if b.left is not None:
            b.left.parent = a

        b.parent = a.parent
        if a.parent is None:
            self.root = b
        elif a is a.parent.left:
            a.parent.left = b
        else:
            a.parent.right = b

        b.left = a
        a.parent = b
        self.rotations += 1

    def _rotate_right(self, b):
        a = b.left
        assert a is not None

        b.left = a.right
        if a.right is not None:
            a.right.parent = b

        a.parent = b.parent
        if b.parent is None:
            self.root = a
        elif b is b.parent.left:
            b.parent.left = a
        else:
            b.parent.right = a

        a.right = b
        b.parent = a
        self.rotations += 1

    def _record(self, name, p, g):
        self.cases[name] += 1
        self.last_trace.append(
            (name, p.key, None if g is None else g.key)
        )

    def _splay(self, x):
        if x is None:
            return

        # Chỉ giữ lịch sử của lần splay hiện tại.
        self.last_trace = []
        while x.parent is not None:
            p = x.parent
            g = p.parent

            if g is None:
                if x is p.left:
                    self._record("zig_L", p, g)
                    self._rotate_right(p)
                else:
                    assert x is p.right
                    self._record("zig_R", p, g)
                    self._rotate_left(p)

            elif x is p.left and p is g.left:
                self._record("zigzig_LL", p, g)
                self._rotate_right(g)
                self._rotate_right(p)

            elif x is p.right and p is g.right:
                self._record("zigzig_RR", p, g)
                self._rotate_left(g)
                self._rotate_left(p)

            elif x is p.right and p is g.left:
                self._record("zigzag_LR", p, g)
                self._rotate_left(p)
                self._rotate_right(g)

            else:
                assert x is p.left and p is g.right
                self._record("zigzag_RL", p, g)
                self._rotate_right(p)
                self._rotate_left(g)

        assert self.root is x
        assert self.root.parent is None

    def _locate(self, key):
        """Trả (found, last) và đếm số nút thật đã ghé."""
        node = self.root
        last = None
        while node is not None:
            self.visits += 1
            last = node
            if key == node.key:
                return node, last
            node = node.left if key < node.key else node.right
        return None, last

    def get(self, key, default=None):
        self._check_key(key)
        found, last = self._locate(key)
        if found is not None:
            self._splay(found)
            return found.value
        if last is not None:
            self._splay(last)
        return default

    def contains(self, key):
        self._check_key(key)
        found, last = self._locate(key)
        if found is not None:
            self._splay(found)
            return True
        if last is not None:
            self._splay(last)
        return False

    def put(self, key, value):
        """True nếu khóa mới, False nếu cập nhật khóa đã có."""
        self._check_key(key)
        found, last = self._locate(key)
        if found is not None:
            found.value = value
            self._splay(found)
            return False

        fresh = Node(key, value)
        fresh.parent = last
        if last is None:
            self.root = fresh
        elif key < last.key:
            last.left = fresh
        else:
            last.right = fresh

        self.size += 1
        self._splay(fresh)
        return True

    def delete(self, key):
        """Trả giá trị cũ; KeyError nếu không có khóa."""
        self._check_key(key)
        found, last = self._locate(key)
        if found is None:
            if last is not None:
                self._splay(last)
            raise KeyError(key)

        self._splay(found)
        result = found.value
        left = found.left
        right = found.right
        if left is not None:
            left.parent = None
        if right is not None:
            right.parent = None

        found.left = None
        found.right = None
        found.parent = None

        if left is None:
            self.root = right
        else:
            self.root = left
            maximum = left
            while maximum.right is not None:
                self.visits += 1
                maximum = maximum.right
            self.visits += 1

            self._splay(maximum)
            assert self.root.right is None
            self.root.right = right
            if right is not None:
                right.parent = self.root

        self.size -= 1
        if self.root is not None:
            self.root.parent = None
        return result

    def items(self):
        """Duyệt inorder, không splay từng nút."""
        stack = []
        node = self.root
        while stack or node is not None:
            while node is not None:
                stack.append(node)
                node = node.left
            node = stack.pop()
            yield (node.key, node.value)
            node = node.right

    def validate(self):
        """Trả (số nút, chiều cao theo số nút); không splay."""
        if self.root is None:
            assert self.size == 0
            return (0, 0)

        assert self.root.parent is None
        seen = set()
        count = 0
        max_depth = 0
        stack = [(self.root, None, None, None, 1)]

        while stack:
            node, expected_parent, low, high, depth = stack.pop()
            marker = id(node)
            assert marker not in seen, "Chu trình/nút trùng"
            seen.add(marker)
            assert node.parent is expected_parent, "Sai parent"
            assert type(node.key) is int
            if low is not None:
                assert low < node.key, "Sai cận dưới"
            if high is not None:
                assert node.key < high, "Sai cận trên"

            count += 1
            max_depth = max(max_depth, depth)
            if node.right is not None:
                stack.append((
                    node.right, node, node.key, high, depth + 1
                ))
            if node.left is not None:
                stack.append((
                    node.left, node, low, node.key, depth + 1
                ))

        assert count == self.size, "Sai số nút"
        return count, max_depth

    def potential(self):
        """Chỉ để minh họa: tính Phi(T) bằng duyệt O(n).

        Không gọi hàm này trong thuật toán thao tác lõi hoặc
        trong phép đo thời gian find/insert/delete.
        """
        if self.root is None:
            return 0.0

        sizes = {}
        total = 0.0
        stack = [(self.root, False)]

        while stack:
            node, done = stack.pop()
            if not done:
                stack.append((node, True))
                if node.right is not None:
                    stack.append((node.right, False))
                if node.left is not None:
                    stack.append((node.left, False))
            else:
                left = (
                    sizes[id(node.left)]
                    if node.left is not None else 0
                )
                right = (
                    sizes[id(node.right)]
                    if node.right is not None else 0
                )
                count = 1 + left + right
                sizes[id(node)] = count
                total += log2(count)

        return total
```

**Ghi chú triển khai:**

- `rotations` đếm **quay đơn**; mỗi zig-zig/zig-zag đóng góp 2 đơn vị.
- `visits` đếm **nút thật đã ghé** trong các đường tìm và tìm `max(L)`; không đếm mọi câu lệnh của runtime.
- `last_trace` chỉ giữ những bước của lần splay mới nhất, nhưng bản thân việc ghi trace có thể tốn O(d) bộ nhớ và thời gian **trên một lượt**. Bỏ instrumentation khi đo hiệu năng sản phẩm.
- `validate` dùng ngăn xếp tường minh vì một splay tree hợp lệ có thể cao O(n).
- `potential` dùng ngăn xếp hậu tự để tính chính xác kích thước mọi cây con trên **trạng thái đã có**, chi phí O(n). Trong cấu trúc thực tế, không cần tính lại hàm thế để được bảo đảm khấu hao.

### 9.2. Ví dụ năm nút: bốn quay thật, thế giảm `log₂3`

Đoạn thử sau dùng đúng cây được tạo bằng cách **chèn khóa tăng dần và splay nút mới**. Các câu lệnh `assert` thể hiện kết quả **mong đợi về mặt toán học**; chúng không phải số đo đã thu từ máy của người học.

```python
tree = SplayMap()
for key in [10, 20, 30, 40, 50]:
    assert tree.put(key, f"lesson-{key}")

assert tree.root.key == 50
assert tree.validate() == (5, 5)
assert [key for key, value in tree.items()] == [
    10, 20, 30, 40, 50
]

phi_before = tree.potential()
assert abs(phi_before - log2(120)) < 1e-10

before_rotations = tree.rotations
before_visits = tree.visits

assert tree.get(10) == "lesson-10"
access_rotations = tree.rotations - before_rotations
access_visits = tree.visits - before_visits
phi_after = tree.potential()

assert access_rotations == 4
assert access_visits == 5
assert tree.root.key == 10
assert tree.validate() == (5, 4)
assert abs(phi_after - log2(40)) < 1e-10
assert tree.last_trace == [
    ("zigzig_LL", 20, 30),
    ("zigzig_LL", 40, 50),
]

amortized_rotations = (
    access_rotations + phi_after - phi_before
)
assert abs(
    amortized_rotations - (4 - log2(3))
) < 1e-10
assert amortized_rotations <= 3 * log2(5) + 1

# Lượt truy cập lại ngay sau đó ở gốc.
before_rotations = tree.rotations
before_visits = tree.visits
assert tree.get(10) == "lesson-10"
assert tree.rotations - before_rotations == 0
assert tree.visits - before_visits == 1
```

**Giải thích:** Đây là một lần splay **đắt theo số quay** (4) nhưng hàm thế giảm `log₂3`. Chi phí khấu hao tính với đúng định nghĩa `c=số quay` là `4−log₂3≈2,415`. Không được hiểu “2,415” là số câu lệnh máy hay số quay thật đã thực hiện.

### 9.3. Một lượt thật sự tuyến tính trên cây lệch

```python
tree = SplayMap()
for key in range(1, 65):
    tree.put(key, str(key))

assert tree.root.key == 64
assert tree.validate() == (64, 64)

before_rotations = tree.rotations
before_visits = tree.visits

assert tree.get(1) == "1"
assert tree.root.key == 1

# 64 nút ghé và 63 phép quay: Theta(n) cho lượt này.
assert tree.visits - before_visits == 64
assert tree.rotations - before_rotations == 63
assert tree.validate()[0] == 64
assert [key for key, value in tree.items()] == list(range(1, 65))

# Sau đó cùng khóa đang ở gốc.
before_rotations = tree.rotations
before_visits = tree.visits
assert tree.get(1) == "1"
assert tree.visits - before_visits == 1
assert tree.rotations - before_rotations == 0
```

Đây là **phản ví dụ quyết định** đối với phát biểu sai “mọi lần tìm splay đều O(log n) xấu nhất”. Số nút ghé và số quay trong lần đầu tăng **tuyến tính theo số nút trên đường lệch**.

### 9.4. Kiểm tra riêng sáu bước splay

Nếu chỉ chèn rồi truy cập ngẫu nhiên, ta không chắc mỗi trường hợp zig, zig-zig, zig-zag đều được kích hoạt. Để kiểm thử **đúng nhánh thuật toán**, có thể dựng một BST ban đầu với hình dạng hợp lệ, sau đó gọi `get`.

```python
def make_shape(rows):
    """rows: (key, parent_key, 'L'/'R'); gốc parent=None."""
    t = SplayMap()
    nodes = {}

    for key, parent_key, side in rows:
        assert key not in nodes
        nodes[key] = Node(key, f"value-{key}")

    for key, parent_key, side in rows:
        node = nodes[key]
        if parent_key is None:
            assert t.root is None
            assert side is None
            t.root = node
        else:
            parent = nodes[parent_key]
            assert node.parent is None
            node.parent = parent
            if side == "L":
                assert parent.left is None
                parent.left = node
            elif side == "R":
                assert parent.right is None
                parent.right = node
            else:
                raise ValueError("side phải là L/R")

    t.size = len(nodes)
    t.validate()  # Chỉ nhận BST đầu vào hợp lệ.
    return t


shapes = [
    (
        "zig_L",
        [(20, None, None), (10, 20, "L")],
        10, 1,
    ),
    (
        "zig_R",
        [(10, None, None), (20, 10, "R")],
        20, 1,
    ),
    (
        "zigzig_LL",
        [(30, None, None), (20, 30, "L"), (10, 20, "L")],
        10, 2,
    ),
    (
        "zigzig_RR",
        [(10, None, None), (20, 10, "R"), (30, 20, "R")],
        30, 2,
    ),
    (
        "zigzag_LR",
        [(30, None, None), (10, 30, "L"), (20, 10, "R")],
        20, 2,
    ),
    (
        "zigzag_RL",
        [(10, None, None), (30, 10, "R"), (20, 30, "L")],
        20, 2,
    ),
]

for name, rows, accessed_key, expected_rotations in shapes:
    t = make_shape(rows)
    inorder_before = list(t.items())

    assert t.get(accessed_key) == f"value-{accessed_key}"
    assert t.root.key == accessed_key
    assert t.cases[name] == 1
    assert sum(t.cases.values()) == 1
    assert t.rotations == expected_rotations
    assert list(t.items()) == inorder_before
    t.validate()
```

Hàm `make_shape` chỉ dùng để tạo **đầu vào thử nghiệm được validator xác nhận**. Không nên dùng cách nối con trỏ tùy ý này thay cho giao diện `put` trong hệ thống thật.

### 9.5. Khóa không tồn tại, cập nhật giá trị và xóa đến cây rỗng

```python
tree = SplayMap()
expected = {}

for key in [40, 20, 60, 10, 30, 50, 70, 5, 15]:
    value = f"lesson-{key}"
    assert tree.put(key, value)
    expected[key] = value
    assert tree.validate()[0] == len(expected)

# Map không sinh nút trùng khóa.
assert not tree.put(30, "updated")
expected[30] = "updated"
assert tree.size == len(expected)
assert tree.root.key == 30

# Truy cập thất bại có thể đổi gốc, nhưng không đổi tập khóa.
assert tree.get(35, "missing") == "missing"
assert list(tree.items()) == sorted(expected.items())
tree.validate()

# Xóa một số nút bên trong rồi đối chiếu bản ghi.
for key in [40, 10, 30, 60]:
    assert tree.delete(key) == expected.pop(key)
    assert list(tree.items()) == sorted(expected.items())
    assert tree.validate()[0] == len(expected)

# Xóa khóa thiếu phát sinh lỗi; tập khóa không bị mất.
items_before = list(tree.items())
try:
    tree.delete(999)
except KeyError:
    pass
else:
    raise AssertionError("Phải báo KeyError")
assert list(tree.items()) == items_before
tree.validate()

# Xóa đến cây rỗng và tái sử dụng.
for key in list(sorted(expected)):
    assert tree.delete(key) == expected.pop(key)
    tree.validate()

assert tree.validate() == (0, 0)
assert tree.put(7, None)
assert tree.get(7) is None
assert tree.contains(7)
assert tree.delete(7) is None
assert tree.validate() == (0, 0)
```

Những ví dụ trên dùng `validate` **sau** thao tác để phát hiện lỗi. Điều đó thuận lợi cho học tập, nhưng `validate` O(n) và `potential` O(n) **không phải thành phần bắt buộc** của `get/put/delete`. Khi đo thời gian của lõi thuật toán, phải để chúng **ngoài khoảng thời gian đo**.

## 10. Tự thiết kế thí nghiệm để phân biệt khấu hao và hiệu năng thực tế

### 10.1. Dãy truy cập đáng thử

| Dữ liệu/thao tác | Điều cần quan sát | Kết luận cần tránh |
| --- | --- | --- |
| Chèn `1..n` theo thứ tự tăng, rồi tìm `1` | Một lượt ghé `n` nút và quay `n-1` lần | “Splay luôn O(log n) xấu nhất” |
| Sau đó tìm `1` nhiều lần liên tiếp | Lượt đầu có thể đắt, các lượt sau ở gốc | “Mọi khóa thường dùng đều luôn O(1)” |
| Lượt tìm khóa không tồn tại | Splay **nút cuối** theo hợp đồng đã chọn | “Tìm thất bại không sửa cây” |
| Truy cập một tập khóa nóng nhỏ | Tổng số lượt ghé/quay và cách gốc thay đổi | “Có locality nghĩa là luôn thắng AVL/RB” |
| Truy cập các khóa xáo trộn với seed cố định | Mẫu chuỗi khác tạo hình khác | “Một lần xáo trộn đại diện mọi workload” |
| Chèn/xóa xen kẽ nhiều lần | Giá trị trả về, kích thước, bất biến, số quay | “Chèn/xóa chỉ là một lần splay” |

### 10.2. Bộ đếm logic và chi phí hệ thống

`visits`, `rotations` và `cases` phản ánh **các thao tác logic**. Chúng **không** có cùng đơn vị với thời gian CPU, byte bộ nhớ hoặc số lần cache miss.

Một phép quay có thể sửa vài liên kết, một lượt ghé nút có thể cần nhiều phép so sánh khóa và truy cập bộ nhớ. `last_trace` cũng gây chi phí phụ nếu bật. Vì thế:

1. Ghi **tập khóa, thứ tự cập nhật, seed ngẫu nhiên nếu có**.
2. Phân biệt **lượt tìm thành công** và **không thành công**.
3. Đo riêng **trung bình** và **các lượt chậm bất thường**.
4. Đo chiều cao ở những mốc quan sát, không bắt buộc tính lại sau mọi lần truy cập.
5. Tách chi phí dựng dữ liệu, in log, `validate` và `potential` khỏi thời gian thao tác lõi.
6. Nếu đối chiếu AVL/RB, dùng **cùng giao diện, tập khóa và trình tự thao tác**.
7. Kết luận từ mẫu số liệu thực tế, không tự điền kết quả chưa chạy.

### 10.3. Đọc phân vị độ trễ đúng cách

Độ trễ **trung bình** có thể tốt khi nhiều khóa được truy cập lại, nhưng hệ thống vẫn có một số thao tác **rất chậm**. Độ trễ ở phân vị cao (ví dụ p95/p99) và cực đại ghi nhận được giúp nhìn thấy hiện tượng ấy trên mẫu thử.

Tuy nhiên, **độ trễ cực đại đo được trên một bộ mẫu** không phải bằng chứng cho cận worst-case toán học. Phân tích lý thuyết và số đo hệ thống giải quyết **hai câu hỏi khác nhau**, nên cần trình bày tách bạch.

## 11. So sánh splay với AVL và Red–Black theo yêu cầu độ trễ

| Thuộc tính | **Splay tree** | **AVL** | **Red–Black Tree** |
| --- | --- | --- | --- |
| Bất biến cần duy trì | Thứ tự BST | BST và chênh cao mỗi nút ≤1 | BST, màu, không đỏ–đỏ, black-height |
| Chiều cao ngay sau thao tác | Có thể **Θ(n)** | **O(log n)** | **O(log n)** |
| Tìm theo khóa: xấu nhất một lần | **O(n)** | **O(log n)** | **O(log n)** |
| Tìm theo khóa: khấu hao | **O(log n)** | **O(log n)** | **O(log n)** |
| Chèn/xóa: xấu nhất một lần | **O(n)** | **O(log n)** | **O(log n)** |
| Chèn/xóa: khấu hao | **O(log n)** | **O(log n)** | **O(log n)** |
| Tìm có thể thay đổi cấu trúc? | **Có**, do splay | Thông thường không | Thông thường không |
| Metadata cân bằng bắt buộc | Không cần `height`, `BF` hoặc `color` | `height` hoặc `BF` | Màu đỏ/đen |
| Phép quay khi tìm | Có thể đến **Θ(n)** một lần | Thường không | Thường không |
| Phù hợp khi | Muốn thử khai thác tính cục bộ trên một chuỗi truy cập | Cần chiều cao chặt, truy cập nhiều | Cần cập nhật có số quay bị chặn trong thuật toán chuẩn |

### 11.1. Khi cần cam kết độ trễ từng lượt

Nếu một API yêu cầu **mỗi lần tìm hoặc xóa riêng lẻ không vượt quá O(log n) bước theo mô hình so sánh**, splay **không cung cấp** bảo đảm đó. AVL hoặc Red–Black Tree phù hợp hơn về mặt **giới hạn worst-case**.

Nếu hệ thống chạy với nhiều luồng đọc song song, splay còn có thêm trở ngại: **`get` có thể quay và sửa các tham chiếu `left/right/parent/root`**, nên thao tác được gọi là “đọc” không hẳn là thao tác không ghi.

### 11.2. Khi tính cục bộ truy cập quan trọng

Splay có thể đáng thử khi người dùng lặp lại một nhóm khóa thường xuyên, chẳng hạn nhiều lượt truy vấn vào những bài vừa học. Tuy nhiên, lợi ích chỉ có thể kết luận sau khi xem **dãy truy cập thực tế**.

Một cấu trúc giữ chiều cao logarit tức thời có thể vẫn nhanh hơn khi:

- Bố trí nút và cache tốt hơn.
- Chi phí quay và ghi bộ nhớ cao.
- Tải không có tính cục bộ đáng kể.
- Thư viện AVL/RB có triển khai được tối ưu và kiểm chứng tốt.

### 11.3. Cấu trúc khác còn phù hợp hơn khi không cần thứ tự

Nếu chỉ tra bản ghi theo `lesson_id`, bảng băm có **O(1) kỳ vọng** cho tìm theo khóa và thường đơn giản hơn một cây tự điều chỉnh. Ngược lại, khi cần **lower bound, predecessor, successor hoặc duyệt tăng dần**, chỉ mục có thứ tự có lợi thế chức năng.

Nếu dữ liệu gần như tĩnh, mảng đã sắp có thể hỗ trợ tìm nhị phân O(log n) và duyệt liên tiếp thuận lợi, dù chèn/xóa giữa dãy thường O(n). Nếu chỉ lấy ưu tiên nhỏ nhất/lớn nhất, heap cũng có mục tiêu khác với ordered Map.

## 12. Ứng dụng: chỉ mục bài học có các khóa nóng

Giả sử một dịch vụ lưu bài học theo:

- `by_id`: bảng băm từ ID tới bản ghi.
- `by_duration`: cây tìm kiếm có thứ tự với khóa `(minutes, lesson_id)`.
- `prerequisites`: đồ thị những bài học cần hoàn thành trước.

Người học có thể thường xuyên xem lại các khóa gần nhau theo thứ tự thời lượng, hoặc mở đi mở lại một bài vừa học.

**Splay tree** là ứng viên cho `by_duration` nếu:

1. Yêu cầu chính là **truy vấn có thứ tự** và chỉnh sửa danh mục.
2. Có **tính cục bộ truy cập**, cần đánh giá qua dãy thao tác.
3. Có thể chấp nhận độ trễ **một lượt đôi khi tăng tuyến tính**.
4. Lượt tìm được phép **thay đổi hình dạng cây** và có đồng bộ phù hợp.

Tuy vậy, kết quả phân tích khấu hao **không tự làm hệ thống đa chỉ mục nhất quán**:

- Khi thời lượng bài thay đổi, phải **xóa khóa cũ** khỏi `by_duration` và **chèn khóa mới**, không sửa `key` tại một nút đã nằm trong BST.
- Nếu xóa bài, cần xử lý tham chiếu trong đồ thị `prerequisites` và dữ liệu chính theo quy tắc nghiệp vụ.
- Các bước cập nhật nhiều chỉ mục cần bảo vệ **tính nguyên tử hoặc nhất quán** phù hợp với thiết kế hệ thống.
- Nếu iterator đang duyệt `by_duration`, một `get` splay khác có thể đổi các liên kết mà iterator đang dùng.

### 12.1. Câu hỏi kỹ thuật trước khi quyết định

| Câu hỏi | Tác động lên lựa chọn |
| --- | --- |
| Có cần thứ tự và truy vấn khoảng không? | Nếu không, xem bảng băm trước |
| Có bao nhiêu khóa được truy cập lặp lại gần đây? | Có thể tạo động lực thử splay |
| Có giới hạn trễ xấu nhất cho mỗi request không? | Nếu có, cân nhắc AVL/RB |
| Nhiều luồng đọc có cần không sửa cấu trúc không? | Splay cần cơ chế đồng bộ hoặc thiết kế khác |
| Có cần iterator/snapshot ổn định không? | Xem lại việc splay trong truy cập |
| Chỉ mục có cần rank/select? | Phải thêm và cập nhật `subtree_size` trong mọi phép quay |
| Có thư viện ordered Map được kiểm chứng sẵn không? | Ưu tiên độ tin cậy và API phù hợp |

### 12.2. Tại sao cận khấu hao vẫn có giá trị?

Dù một lần truy cập có thể chậm, cận khấu hao cho biết rằng **các truy cập sâu không thể liên tục “miễn phí” làm cây xấu hơn theo cách vượt cận tổng đã chứng minh**. Phân tích hàm thế theo dõi chi phí tích lũy của những lần splay, cung cấp bảo đảm **không chỉ dựa vào một chuỗi thử cụ thể**.

Giá trị của cận khấu hao nằm ở **hệ thống xử lý nhiều thao tác liên tiếp**, với điều kiện chương trình sử dụng đúng biến thể splay được phân tích. Nó không thay thế yêu cầu độ trễ theo request, cũng không đo được tác động của GC, scheduler hay cache.

## 13. Các hiểu lầm phổ biến

### 13.1. Nhầm kiểu cận

- **“O(log n) khấu hao nghĩa là mọi lần tìm ≤C log n.”** Sai: đó là suy luận từ cận chuỗi sang cận đơn thao tác.
- **“Một lượt Θ(n) chứng minh toàn bộ thuật toán có khấu hao Θ(n).”** Sai: một lượt đắt có thể được bù trong phân tích tổng.
- **“Khấu hao là trung bình theo một phân phối ngẫu nhiên.”** Sai: phân tích khấu hao không cần xác suất đầu vào.
- **“Lần nào thế cũng giảm.”** Sai: có lần thế tăng; quan trọng là tổng biến thiên và cận từng bước.
- **“Chi phí khấu hao là thời gian CPU đo được.”** Sai: đây là một đại lượng phân tích, có thể nhỏ hơn hoặc lớn hơn chi phí thực từng lần.
- **“Nếu `Φ(T_0)` lớn cũng có thể bỏ qua khi tính tổng chi phí thực trên đoạn ngắn.”** Sai: thế ban đầu là một khoản trong công thức telescoping.
- **“Access Lemma cho splay có `n` nút đã tự chứng minh chèn/xóa không đổi kích thước.”** Sai: cập nhật phải tính phần thế do thêm/bỏ nút.

### 13.2. Nhầm về hàm thế và chứng minh

- **“`s(v)` là kích thước toàn cây.”** Sai: là kích thước **cây con tại `v`**; chỉ ở gốc mới bằng `n`.
- **“Mỗi nút phải lưu `r(v)` mới thực hiện được splay.”** Sai: `r` và `Φ` là công cụ chứng minh.
- **“`Φ(T)` chính là chiều cao của cây.”** Sai: nó là **tổng log kích thước các cây con**.
- **“`Φ` luôn O(log n).”** Sai: cận tổng quát của thế là **O(n log n)**.
- **“Hai quay kép luôn giống nhau về biến thiên thế.”** Sai: zig-zig và zig-zag có những hình dạng khác nhau, phải xét các cây con rời nhau tương ứng.
- **“Một kết quả sau quay giữ inorder là đủ để mượn Access Lemma.”** Sai: thứ tự quay và cấu trúc zig-zig/zig-zag là một phần của thuật toán được phân tích.
- **“Đã có công thức `ĉ_i=c_i+ΔΦ` thì bất kỳ thuật toán nào cũng O(log n).”** Sai: cần chứng minh **cận trên của `ĉ_i`** cho thuật toán cụ thể.

### 13.3. Nhầm về cài đặt và hiệu năng

- **“Splay tree luôn có chiều cao O(log n).”** Sai: có thể lệch Θ(n).
- **“Tìm thất bại không làm thay đổi gốc.”** Không đúng với chính sách splay nút cuối đang dùng.
- **“Đã splay khóa `k` thì mọi lần tìm `k` về sau đều O(1).”** Chỉ đúng nếu nó **vẫn đang ở gốc**; thao tác xen vào có thể đổi gốc.
- **“`get` là phép đọc bất biến, an toàn cho mọi luồng.”** Sai: splay có thể quay cây và sửa liên kết.
- **“Quay xong có thể bỏ qua `parent`.”** Sai với cài đặt bottom-up dùng `parent`.
- **“Có thể dùng lại `height` của AVL để ép splay có chiều cao logarit.”** Không thể mặc định thêm bất biến rồi vẫn áp nguyên phân tích chuẩn.
- **“Ghi log và tính `Φ` toàn cây không ảnh hưởng phép đo thao tác.”** Sai: tính `Φ` thường O(n), log có thể tốn thời gian và bộ nhớ.
- **“Chỉ cần inorder tăng để xác minh cài đặt.”** Chưa đủ: phải kiểm tra cả `parent`, nút lặp, số nút, tập giá trị và các trường hợp xóa.
- **“Có ít phép quay hơn trên một lần đo nghĩa là luôn nhanh hơn AVL.”** Sai: cần đo chi phí so sánh, ghi bộ nhớ, cache và phân phối truy cập.

### 13.4. Checklist đánh giá một phát biểu về splay

Trước khi chấp nhận một tuyên bố hiệu năng, hãy hỏi:

1. Nó là cận **mỗi thao tác**, **khấu hao** hay **kỳ vọng**?
2. Chi phí được đếm theo **quay, nút ghé hay thời gian máy**?
3. Cây khởi đầu **rỗng hay đã có `n` nút tùy ý**?
4. Kích thước cây có **cố định** trong chuỗi không?
5. Các thao tác là **splay chuẩn** hay một biến thể khác?
6. Khi tìm thất bại, nút nào được splay?
7. Có bỏ sót **thế ban đầu** khi suy ra tổng chi phí không?
8. Validator và tính thế có được **loại khỏi thời gian thao tác lõi** không?
9. Có kết quả đo trên **cùng tải công việc** để so với AVL/RB không?
10. Có yêu cầu **độ trễ worst-case từng request** hoặc **đồng thời** không?

## 14. Bài tập vận dụng

### Bài 1 — Phân biệt ba loại phân tích

Nêu sự khác nhau giữa **worst-case một thao tác**, **khấu hao** và **kỳ vọng**. Trong ba khái niệm ấy, phát biểu “splay có O(log n) cho một chuỗi thao tác” thuộc loại nào?

*Gợi ý:* Đó là **khấu hao**; không yêu cầu phân phối ngẫu nhiên và không tự cho cận của từng thao tác.

### Bài 2 — Phản ví dụ chiều cao

Chèn lần lượt `10,20,30,40,50` vào cây rỗng bằng “BST insert rồi splay nút mới”. Vẽ cây cuối, tính chiều cao theo **số cạnh** và **số nút**.

*Gợi ý:* `50` là gốc với chuỗi trái `40→30→20→10`. Chiều cao là 4 cạnh hoặc 5 nút.

### Bài 3 — Lượt truy cập tuyến tính

Với cây ở Bài 2, tìm `10` cần ghé bao nhiêu nút và splay cần bao nhiêu phép quay đơn? Khái quát thành cây lệch `n` nút.

*Gợi ý:* Năm nút ghé, bốn quay; tổng quát `n` nút ghé và `n-1` quay, tức Θ(n).

### Bài 4 — Quay theo độ sâu ban đầu

Một nút `x` nằm sâu `d=11` cạnh trong cây. Với bottom-up splay chuẩn, có mấy bước kép, mấy zig cuối và bao nhiêu phép quay đơn?

*Gợi ý:* Năm bước kép, một zig cuối, tổng 11 quay.

### Bài 5 — Vì sao zig-zig khác zig đơn liên tiếp?

Cho cây `30→trái 20→trái 10`. Vẽ kết quả của zig-zig LL chuẩn và phương pháp luôn quay nút mục tiêu qua cha. Hai cây có cùng inorder không? Có cùng hình dạng không?

*Gợi ý:* Inorder giống nhau; zig-zig chuẩn cho chuỗi phải `10→20→30`, còn hai zig đơn cho `10→30` với `20` nằm trái `30`.

### Bài 6 — Hàm kích thước cây con

Với cây:

```text
        40
       /  \
      20   60
     / \
    10  30
```

Hãy tính `s(v)` cho năm nút và `r(v)=log₂s(v)` tại gốc.

*Gợi ý:* Kích thước theo khóa `10,20,30,40,60` lần lượt là `1,3,1,5,1`; `r(40)=log₂5`.

### Bài 7 — Tính hàm thế

Với cây trong Bài 6, tính `Φ(T)` và giải thích vì sao các lá không đóng góp vào tổng.

*Gợi ý:* `Φ=log₂1+log₂3+log₂1+log₂5+log₂1=log₂15`. Lá có `s=1` nên `log₂1=0`.

### Bài 8 — Tại sao `Φ(T)≥0`?

Chứng minh mỗi hạng `r(v)` của nút thật không âm và suy ra cận thô `Φ(T)≤n log₂n`. Cận này dùng để làm gì trong phân tích chuỗi?

*Gợi ý:* `1≤s(v)≤n`. Nó giúp chặn **thế đầu** khi cây ban đầu có sẵn.

### Bài 9 — Chi phí khấu hao khi thế giảm

Một thao tác có `c=10` và làm `Φ` giảm `6` đơn vị. Tính `ĉ`. Có thể kết luận số phép quay thật chỉ bằng 4 không?

*Gợi ý:* `ĉ=10-6=4` nhưng `c` vẫn là 10 theo đơn vị chi phí đã chọn.

### Bài 10 — Chi phí khấu hao khi thế tăng

Một thao tác có `c=3` và làm `Φ` tăng 5. Chi phí khấu hao là bao nhiêu, và nên hiểu 5 đơn vị tăng thế thế nào?

*Gợi ý:* `ĉ=8`; phần tăng thế có thể xem như “tín dụng” tích lũy cho tương lai.

### Bài 11 — Công thức telescoping

Cho ba thao tác với các biến thiên thế lần lượt `+4,−1,−3`. Tổng biến thiên thế là bao nhiêu? Tại sao tổng chi phí thật và tổng khấu hao bằng nhau trong ví dụ này?

*Gợi ý:* Tổng thay đổi thế bằng 0, nên `Σc_i=Σĉ_i`.

### Bài 12 — Ví dụ năm nút

Chứng minh bằng phép đếm kích thước cây con rằng cây lệch trái năm nút `50→40→30→20→10` có `Φ_before=log₂(120)`. Sau splay `10`, tại sao `Φ_after=log₂(40)`?

*Gợi ý:* Trước có các kích thước `5,4,3,2,1`; sau có `5,4,2,1,1`. Dùng tích để rút gọn tổng log.

### Bài 13 — Chi phí khấu hao của ví dụ năm nút

Với 4 phép quay, `Φ_before=log₂(120)` và `Φ_after=log₂(40)`, tính `ĉ`. So sánh với cận Access Lemma `3log₂5+1`.

*Gợi ý:* `ĉ=4−log₂3≈2,415`, nhỏ hơn cận trên của bổ đề.

### Bài 14 — Bổ đề truy cập không phải cận số quay thật

Một lần splay sâu thực hiện 63 phép quay trên 64 nút. Có mâu thuẫn với `3log₂64+1=19` không? Vì sao?

*Gợi ý:* Không: 19 là **cận chi phí khấu hao** theo hàm thế và quy ước chi phí, không phải số quay thật của một lượt.

### Bài 15 — Điều kiện cốt lõi của zig-zig

Trong zig-zig LL, gọi `a=s(x)` trước bước và `b=s'(g)` sau bước. Giải thích tại sao hai nhóm nút này rời nhau và tại sao `a+b≤s(g)`.

*Gợi ý:* Cây con cũ của `x` và cây con mới của `g` nằm ở hai đầu trong sơ đồ LL, không chia sẻ nút.

### Bài 16 — Bất đẳng thức logarit

Chứng minh từ `(a-b)^2≥0` rằng `ab≤((a+b)/2)^2`. Nếu `a+b≤N`, suy ra `log₂a+log₂b≤2log₂N−2`.

*Gợi ý:* Lấy log hai vế của bất đẳng thức tích, rồi dùng tính tăng của logarit.

### Bài 17 — Vì sao trong zig-zig quay ông trước?

Chỉ ra hai hạng `r(x)` và `r'(g)` được dùng trong bất đẳng thức `r(x)+r'(g)≤2r(g)−2`. Vì sao đổi thứ tự quay khiến không thể áp dụng nguyên cùng sơ đồ chứng minh?

*Gợi ý:* Chứng minh dùng hai cây con rời nhau trước/sau **bước zig-zig chuẩn**, không chỉ điều kiện inorder.

### Bài 18 — Zig-zag và cây con sau quay

Với zig-zag LR, hai cây con nào ở dưới `p` và `g` sau quay? Dùng quan hệ `s'(p)+s'(g)≤s(g)` để giải thích vì sao tổng hai hạng được chặn.

*Gợi ý:* `p` mang các vùng `A,B`, `g` mang `C,D`. Hai cây con này rời nhau trong cây con cũ của `g`.

### Bài 19 — Telescoping hạng của cùng nút `x`

Giả sử hạng của `x` sau các bước lần lượt là `r_0,r_1,r_2,r_3`. Rút gọn `(r_1-r_0)+(r_2-r_1)+(r_3-r_2)`. Áp dụng khi `x` cuối cùng là gốc toàn cây.

*Gợi ý:* Bằng `r_3-r_0`; sau splay `r_3=log₂n`.

### Bài 20 — Vì sao chỉ một zig cộng hằng số 1?

Trong bottom-up splay chuẩn, vì sao một lần splay có thể có nhiều zig-zig/zig-zag nhưng **tối đa một zig**?

*Gợi ý:* Zig chỉ dùng khi `x` cách gốc một cạnh; sau zig, `x` đã là gốc nên dừng.

### Bài 21 — Cây khởi đầu tùy ý

Cho cây ban đầu có `n` nút và thực hiện `m` lượt truy cập có splay, không chèn/xóa. Viết cận tổng chi phí thực suy từ `Φ(T_0)≤n log₂n`. Vì sao không thể bỏ phần `n log n` khi `m=1`?

*Gợi ý:* `Σc_i≤m(3log₂n+1)+nlog₂n`. Một lượt truy cập từ cây lệch có thể tuyến tính.

### Bài 22 — Chèn và biến thiên thế

Vì sao khi thêm một nút lá vào BST, kích thước của **mỗi tổ tiên trên đường tìm** chỉ tăng một đơn vị? Giải thích công thức chặn phần tăng thế bằng `log₂(n+1)`.

*Gợi ý:* Các kích thước cũ của tổ tiên là những số nguyên tăng nghiêm ngặt, nên tích các tỉ số `(s+1)/s` không vượt tích đủ từ `s=1` đến `n`.

### Bài 23 — Xóa bằng splay và nối cây con

Sau khi splay khóa `k` lên gốc và tách hai cây `L,R`, tại sao splay `max(L)` lại giúp nối `R` vào `right` một cách an toàn?

*Gợi ý:* `max(L)` không có khóa lớn hơn trong `L`, nên sau khi lên gốc `L` nó không có con phải.

### Bài 24 — Chi phí của tìm thất bại

Với cây có khóa `10,20,30`, khi tìm `25` mà không thấy, nút nào được splay theo hợp đồng của bài? Vì sao không thể xác định nút đó chỉ từ tập khóa mà không biết hình dạng hiện tại?

*Gợi ý:* Splay **nút cuối trên đường so sánh**; đường đi phụ thuộc cấu trúc BST hiện thời.

### Bài 25 — Phát hiện lỗi đo benchmark

Một chương trình gọi `tree.potential()` và `tree.validate()` sau **mỗi lần tìm**, rồi đo thời gian tổng của vòng lặp. Vì sao kết quả đó không cho biết chi phí lõi của một lần tìm splay?

*Gợi ý:* Hai hàm duyệt cây O(n), có thể áp đảo O(log n) khấu hao của thao tác splay chuẩn.

### Bài 26 — Đọc một báo cáo hiệu năng

Một thử nghiệm ghi nhận splay ít phép quay hơn AVL trên nhóm khóa nóng, nhưng p99 latency cao hơn. Có mâu thuẫn không? Những đại lượng nào còn thiếu để giải thích?

*Gợi ý:* Không: số quay là chỉ số logic; p99 còn chịu đường tìm, cache, runtime, ghi bộ nhớ, phân phối truy cập và đồng bộ.

### Bài 27 — Thao tác đọc và đồng thời

Hai luồng cùng gọi `get` trên cùng một splay tree không được đồng bộ. Nêu rủi ro đối với `root`, `parent` và iterator. Một AVL/RB truyền thống có lợi thế gì trong tình huống chỉ đọc?

*Gợi ý:* `get` splay có thể ghi cấu trúc. Tìm trên AVL/RB thông thường không quay, thuận lợi hơn cho đọc đồng thời khi có thiết kế đồng bộ phù hợp.

### Bài 28 — Lựa chọn chỉ mục bài học

Một danh mục cần tìm theo `lesson_id` và truy vấn theo khoảng thời lượng. Đề xuất kết hợp bảng băm với chỉ mục có thứ tự. Khi nào splay là một ứng viên đáng đo và khi nào nên nghiêng về AVL/RB?

*Gợi ý:* Bảng băm theo ID; cây theo `(minutes,lesson_id)`. Splay đáng thử nếu có locality và chấp nhận trễ khấu hao; AVL/RB hợp lý hơn khi cần worst-case từng lượt.

## 15. Tổng kết

**Splay tree** không duy trì bất biến chiều cao logarit như AVL hoặc Red–Black. Một cây hợp lệ vẫn có thể là chuỗi dài `n` nút; truy cập nút sâu nhất phải đi qua **n nút thật** và thực hiện **n−1 phép quay đơn** để đưa nó lên gốc. Do đó, **một thao tác riêng lẻ có thể Θ(n)**.

Điểm mạnh lý thuyết nằm ở **phân tích khấu hao**. Với `s(v)` là số nút cây con, `r(v)=log₂s(v)` và `Φ(T)=Σr(v)`, ta định nghĩa `ĉ=c+ΔΦ`. Chứng minh Access Lemma cho **zig, zig-zig và zig-zag** cho thấy chi phí khấu hao của một lần splay trên cây `n` nút được chặn bởi **O(log n)**, mặc dù chi phí quay thật có thể tuyến tính. Khi cộng nhiều lần, biến thiên thế **triệt tiêu**, nhưng cần giữ đúng **khoản thế đầu** nếu cây có sẵn từ trước.

Chèn và xóa splay chuẩn cũng có **O(log n) khấu hao** khi tính cả tác động thêm/bỏ nút và các lần splay cần thiết; tính đúng đắn vẫn phụ thuộc bất biến BST, liên kết cha–con và cách nối cây con. Cận khấu hao không phải **kỳ vọng ngẫu nhiên**, cũng không bảo đảm **độ trễ O(log n) cho từng request**. Khi lựa chọn cấu trúc dữ liệu, hãy xét **mẫu truy cập, yêu cầu worst-case latency, tính cục bộ, đồng thời, bộ nhớ và chất lượng triển khai** — không chỉ nhìn một lần truy cập nhanh hay một dòng Big O.
