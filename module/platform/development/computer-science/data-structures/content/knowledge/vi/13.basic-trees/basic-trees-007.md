# Quan hệ giữa chiều cao với số nút và số lá

Một cây có **nhiều nút** chưa chắc **cao**, và một cây có **ít lá** chưa chắc **nhỏ**. Ví dụ, 100 nút xếp thành một chuỗi tạo cây có chiều cao 99 nhưng chỉ một lá; ngược lại, một gốc nối trực tiếp tới 99 lá có cùng 100 nút nhưng chiều cao chỉ bằng 1. Hai trường hợp này dẫn đến chi phí duyệt đường đi, bộ nhớ đệ quy và khả năng tìm kiếm rất khác nhau.

Trong chương **Cây cơ bản** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài học này làm rõ các quan hệ toán học giữa **chiều cao** (*height*, ký hiệu \(h\)), **số nút** (*number of nodes*, \(n\)) và **số lá** (*number of leaves*, \(L\)). Ta sẽ chứng minh những giới hạn đúng với mọi cây có gốc, rồi xem các kết quả mạnh hơn khi mỗi nút chỉ có tối đa \(b\) con hoặc khi cây có hình dạng đặc biệt như **cây nhị phân đầy đủ** (*full*), **hoàn hảo** (*perfect*) và **hoàn chỉnh** (*complete*). Cuối bài có chương trình Python, bảng tổng hợp và bài tập tự kiểm tra.

**Mục tiêu học tập:** biết chọn công thức đúng cho **đúng loại cây**, nhận diện giả thiết bị thiếu, ước lượng bộ nhớ/độ sâu thao tác từ hình dạng cây và tránh suy luận sai rằng “nhiều nút ⇒ nhiều tầng” hoặc “nhiều lá ⇒ cây cao”.

## 1. Thống nhất quy ước: chiều cao được đếm bằng cạnh

Xét một **cây có gốc hữu hạn, không rỗng**. Trong bài:

- **Gốc** (*root*) có độ sâu \(0\).
- **Độ sâu** của nút \(u\), ký hiệu \(d(u)\), là số **cạnh** trên đường duy nhất từ gốc đến \(u\).
- **Lá** (*leaf*) là nút **không có con**, kể cả gốc nếu cây chỉ có một nút.
- **Nút trong** (*internal node*) là nút có ít nhất một con.
- **Chiều cao của nút** \(u\), ký hiệu \(h(u)\), là số cạnh trên đường đi dài nhất từ \(u\) xuống một lá thuộc cây con của \(u\).
- **Chiều cao cây** \(h\) bằng chiều cao gốc, cũng bằng độ sâu lớn nhất của một lá.
- **Mức/tầng** (*level*) ở đây là tập nút có cùng độ sâu. Nếu cây cao \(h\) thì có \(h+1\) mức, đánh số \(0,1,\ldots,h\).

Với nút \(u\):

\[
h(u)=
\begin{cases}
0,&\text{nếu }u\text{ là lá},\\
1+\max_{v\in\operatorname{children}(u)}h(v),&\text{nếu }u\text{ có con}.
\end{cases}
\]

Ví dụ:

~~~text
Độ sâu       Cây ví dụ
   0                R
                  / | \
   1             A  B  C
                / \ |
   2           D   E F
                      |
   3                  G
~~~

Đường dài nhất là \(R\rightarrow B\rightarrow F\rightarrow G\), có **3 cạnh**, nên \(h=3\). Cây có **4 mức**, không phải 3 mức. Các lá là \(C,D,E,G\).

| Đại lượng | Kết quả trong hình |
| --- | --- |
| Tổng số nút \(n\) | 8 |
| Số cạnh | 7 |
| Số lá \(L\) | 4: C, D, E, G |
| Số nút trong \(I=n-L\) | 4: R, A, B, F |
| Chiều cao \(h\) tính bằng cạnh | 3 |
| Số mức | 4 |

**Cảnh báo quy ước:** Một số giáo trình định nghĩa chiều cao bằng **số nút trên đường dài nhất** hoặc gọi gốc thuộc mức 1. Khi đó cây ví dụ có chiều cao theo số nút là 4. Các công thức trong bài này dùng **số cạnh**; nếu tài liệu khác dùng số nút, cần dịch \(h_{\mathrm{nút}}=h_{\mathrm{cạnh}}+1\) cho cây không rỗng.

**Cây rỗng:** Có tài liệu đặt chiều cao cây rỗng bằng \(-1\), có tài liệu xem là không xác định. Để tránh mơ hồ, các định lý chính dưới đây áp dụng cho **\(n\ge1\)**. Khi xét rừng rỗng, ta sẽ nêu riêng.

## 2. Bất biến cơ bản: số cạnh, số nút trong và số lá

Trong một cây có gốc \(n\ge1\), mỗi nút trừ gốc có **đúng một cha**, do đó:

\[
\boxed{|E|=n-1.}
\]

Gọi \(I\) là số nút trong và \(L\) là số lá. Vì hai loại nút không giao nhau và bao phủ toàn cây:

\[
\boxed{n=I+L.}
\]

Gọi \(\deg^+(u)\) là **số con** của nút \(u\). Mỗi cạnh đi từ đúng một cha đến một con, nên tổng số con của tất cả các nút bằng tổng số cạnh:

\[
\sum_{u\in V}\deg^+(u)=n-1.
\]

Các lá có số con bằng 0, nên:

\[
\sum_{u\text{ là nút trong}}\deg^+(u)=n-1=I+L-1.
\]

Trừ \(I\) từ hai vế cho công thức quan trọng:

\[
\boxed{L=1+\sum_{u\text{ là nút trong}}\bigl(\deg^+(u)-1\bigr).}
\]

### Ý nghĩa trực quan

- Khởi đầu từ cây **một nút**, có một lá.
- Biến một lá hiện tại thành nút có **\(d\ge1\) con** làm số lá thay đổi từ 1 thành \(d\), tức **tăng \(d-1\)** lá.
- Thêm đúng **một con** vào một lá cũ chỉ thay thế một lá bằng lá mới, nên **số lá không tăng**.
- Thêm hai con vào một lá cũ làm **tăng một lá**.

Trong ví dụ mục 1, các nút trong R, A, B, F có số con lần lượt là \(3,2,1,1\):

\[
L=1+[(3-1)+(2-1)+(1-1)+(1-1)]=4.
\]

**Hệ quả:** Độ dài của một chuỗi gồm các nút mỗi nút chỉ có một con có thể tăng rất nhiều, trong khi số lá vẫn bằng 1. Số lá phản ánh **sự phân nhánh**, không trực tiếp đo chiều cao.

## 3. Cây tổng quát: giới hạn chiều cao khi đã biết số nút

Trước tiên **không giới hạn số con** của mỗi nút. Nếu cây cao \(h\), phải tồn tại một đường từ gốc đến lá sâu nhất gồm \(h\) cạnh, tức chứa **\(h+1\) nút phân biệt**. Do đó:

\[
\boxed{n\ge h+1\quad\Longleftrightarrow\quad 0\le h\le n-1.}
\]

Giới hạn \(h\le n-1\) đạt được ở **cây dạng chuỗi** (*path/chain*): mỗi nút trong có đúng một con.

~~~text
Cây chuỗi, n=7:                 Cây hình sao, n=7:

 A                              A
 |                            / | | | | \
 B                           B  C D E F  G
 |
 C
 |
 D
 |
 E
 |
 F
 |
 G

 h=6, L=1                      h=1, L=6
~~~

Hai cây đều có \(n=7\) nút nhưng chiều cao và số lá khác nhau rất nhiều.

**Không có một cận trên nhỏ kiểu \(O(\log n)\) cho chiều cao của cây tổng quát bất kỳ.** Muốn suy ra \(h=O(\log n)\), cần thêm bất biến hình dạng/cân bằng của một lớp cây cụ thể.

### Cây một nút là trường hợp biên

Với \(n=1\): \(h=0\), \(L=1\), \(I=0\), \(|E|=0\). Nút gốc vừa là gốc vừa là lá. Các công thức tổng quát vẫn đúng:

\[
1\ge0+1,\qquad L=1+\sum_{\varnothing}(\cdots)=1.
\]

Đừng áp dụng những công thức suy ra khi **\(h\ge1\)** cho cây một nút mà không kiểm tra điều kiện.

## 4. Ràng buộc đồng thời \(n\), \(h\) và \(L\) ở cây không giới hạn bậc

Nếu biết **cả số nút và chiều cao**, ta có thể giới hạn số lá khá chặt ngay cả khi một nút được phép có tùy ý nhiều con.

### 4.1. Cận trên số lá: \(L\le n-h\)

Trên đường từ gốc đến một lá sâu nhất có \(h\) cạnh, **\(h\) nút đầu tiên** của đường đó đều là nút trong (có con kế tiếp). Vì vậy tổng số nút trong ít nhất bằng \(h\):

\[
I\ge h.
\]

Từ \(n=I+L\):

\[
\boxed{L\le n-h.}
\]

Để đạt dấu bằng khi \(h\ge1\), có thể tạo **một đường dài \(h\) cạnh** rồi gắn tất cả \(n-h-1\) nút còn lại làm những lá phụ ngay dưới gốc hoặc một nút trong khác, sao cho không làm tăng chiều cao.

Ví dụ với \(n=10,h=3\): cây gồm một đường dài 3 cạnh (4 nút) và **6 lá phụ** có thể đạt \(L=1+6=7=n-h\).

### 4.2. Cận dưới số lá: \(L\ge\lceil(n-1)/h\rceil\), với \(h\ge1\)

Mỗi nút không phải gốc nằm trên đường từ gốc tới **ít nhất một lá**. Vì vậy, toàn bộ \(n-1\) cạnh của cây được bao phủ bởi hợp của các đường gốc–lá. Có \(L\) đường như vậy và độ dài của mỗi đường **không vượt quá \(h\)**:

\[
n-1\le \sum_{\ell\text{ là lá}} d(\ell)\le Lh.
\]

Do \(h\ge1\):

\[
\boxed{L\ge \left\lceil\frac{n-1}{h}\right\rceil.}
\]

Đây là cận cho cây có gốc tổng quát, **không đòi hỏi mọi lá ở cùng một độ sâu**.

### 4.3. Ghép hai cận

Với **cây không rỗng có \(h\ge1\)** và **không giới hạn số con**:

\[
\boxed{\left\lceil\frac{n-1}{h}\right\rceil\le L\le n-h,\qquad n\ge h+1.}
\]

Tương đương:

\[
\boxed{h+L\le n\le 1+hL.}
\]

**Hai cận có thể đạt được** đối với cây tổng quát: cận trên số lá bằng cách dồn các nhánh phụ thành lá, cận dưới số lá bằng cách dùng những “cánh tay” xuất phát từ gốc có độ dài nhiều nhất \(h\). Với \(n=10,h=3\):

| Cách phân nhánh | Số lá \(L\) | Cách xây |
| --- | ---: | --- |
| Ít lá nhất | 3 | Ba nhánh độc lập từ gốc, mỗi nhánh dài 3 cạnh: \(n=1+3+3+3=10\) |
| Nhiều lá nhất | 7 | Một đường dài 3 cạnh, thêm 6 lá phụ: \(n=4+6=10\) |

**Chú ý phạm vi:** Cận này đúng khi số con **không bị chặn**. Nếu mỗi nút chỉ có tối đa \(b\) con, các giá trị đạt được còn phải tuân theo ràng buộc phân nhánh của loại cây \(b\)-phân, xét ở phần tiếp theo.

### 4.4. Biết riêng \(n\) hay riêng \(L\) không đủ suy ra chiều cao chính xác

- Với \(n=7\), cây chuỗi có \(h=6,L=1\), còn cây hình sao có \(h=1,L=6\).
- Với \(L=1\), cây có thể là **một nút** (\(h=0\)) hoặc **một đường dài tùy ý** (\(h\) lớn) nếu không cố định \(n\).
- Với \(L=6\), một cây hình sao có \(h=1\); thêm các nút chỉ có một con trên một nhánh có thể làm \(h\) tăng mà **\(L\) vẫn bằng 6**.

Vì vậy, từ riêng số lá **không thể kết luận chiều cao luôn tăng theo logarit của số lá**. Giới hạn logarit cần thêm giả thiết cụ thể về dạng cây.

## 5. Khi mỗi nút có tối đa \(b\) con: giới hạn theo số tầng

Một **cây \(b\)-phân tổng quát** (*\(b\)-ary tree*) là cây có gốc mà mỗi nút có **không quá \(b\) con**. Ở đây \(b\) là một số nguyên cố định, \(b\ge2\). Cây nhị phân là trường hợp \(b=2\).

Tại độ sâu 0 có tối đa 1 nút. Mỗi nút có tối đa \(b\) con, nên số nút ở độ sâu \(d\) được giới hạn bởi:

\[
\boxed{N_d\le b^d.}
\]

Với cây cao \(h\), cộng tất cả các mức:

\[
\begin{aligned}
n&=\sum_{d=0}^{h}N_d\\
&\le1+b+b^2+\cdots+b^h\\
&=\boxed{\frac{b^{h+1}-1}{b-1}}.
\end{aligned}
\]

Đồng thời, mọi lá nằm ở một trong các mức từ 0 đến \(h\). Ta còn có cận:

\[
\boxed{L\le b^h.}
\]

**Giải thích cận số lá:** Có thể hình dung mỗi lá ở độ sâu nhỏ hơn \(h\) được kéo dài bằng những nhánh phân biệt tới mức \(h\). Mỗi lá ban đầu có thể gán một vị trí hậu duệ riêng ở mức \(h\) của cây \(b\)-phân đầy đủ tưởng tượng, trong khi mức đó chỉ có \(b^h\) vị trí. Dấu bằng đạt được khi mọi nút ở các mức \(0,\ldots,h-1\) có đúng \(b\) con.

### Các cận này nói điều gì về chiều cao?

Từ giới hạn số nút, với \(b\ge2\):

\[
(b-1)n+1\le b^{h+1}.
\]

Lấy logarit cơ số \(b\) cho ta:

\[
\boxed{h\ge
\left\lceil\log_b\bigl((b-1)n+1\bigr)\right\rceil-1.}
\]

Tương tự, từ \(L\le b^h\):

\[
\boxed{h\ge\lceil\log_b L\rceil.}
\]

Đây đều là **cận dưới** cho chiều cao khi số nút hoặc lá đã biết: cây **không thể thấp hơn** một mức nhất định nếu số con tối đa bị giới hạn. Chúng **không** phải cận trên \(h=O(\log n)\) cho mọi cây \(b\)-phân; cây dạng chuỗi vẫn hợp lệ vì mỗi nút chỉ có một con.

### Trường hợp đặc biệt \(b=1\)

Nếu mỗi nút có tối đa một con, cây không rỗng luôn là một **đường đi**:

\[
\boxed{n=h+1,\qquad L=1.}
\]

Không dùng công thức cấp số nhân \((b^{h+1}-1)/(b-1)\) khi \(b=1\), vì mẫu số bằng 0. Khi đó tổng số nút ở mỗi độ sâu đơn giản bằng 1.

### Ví dụ số với cây nhị phân (\(b=2\))

\[
n\le2^{h+1}-1,\qquad L\le2^h.
\]

| Chiều cao \(h\) | Mức từ 0 tới \(h\) | Số nút lớn nhất | Số lá lớn nhất |
| ---: | ---: | ---: | ---: |
| 0 | 1 | 1 | 1 |
| 1 | 2 | 3 | 2 |
| 2 | 3 | 7 | 4 |
| 3 | 4 | 15 | 8 |
| 4 | 5 | 31 | 16 |
| 5 | 6 | 63 | 32 |

Nếu một **cây nhị phân có 20 nút**, chiều cao không thể là 3 vì cây nhị phân cao 3 chứa tối đa 15 nút. Nó phải có \(h\ge4\). Nhưng cây 20 nút vẫn có thể cao tới 19 nếu suy biến thành một chuỗi.

## 6. Cây \(b\)-phân đầy đủ: công thức chính xác từ số nút trong

Từ **full** thường được dịch là **cây đầy đủ**. Trong bài, một **cây \(b\)-phân đầy đủ** (*full \(b\)-ary tree*) là cây mà **mỗi nút trong có đúng \(b\) con**, còn mỗi lá có 0 con. Không yêu cầu tất cả lá ở cùng một độ sâu.

Giả sử có \(I\) nút trong. Mỗi nút trong đóng góp đúng \(b\) cạnh tới các con, nên:

\[
n-1=bI.
\]

Kết hợp \(n=I+L\):

\[
\begin{aligned}
n&=bI+1,\\
L&=(b-1)I+1.
\end{aligned}
\]

Do đó:

\[
\boxed{n=bI+1,\quad L=(b-1)I+1,\quad
n=\frac{bL-1}{b-1}.}
\]

Đối với **cây nhị phân đầy đủ** (\(b=2\)):

\[
\boxed{L=I+1,\qquad n=2L-1.}
\]

Các quan hệ này **không đúng cho mọi cây nhị phân**. Chúng đòi hỏi mọi nút trong có **đúng hai con**, chứ không chỉ tối đa hai con.

### Ví dụ: đầy đủ nhưng không hoàn hảo

~~~text
             A
            / \
           B   C
              / \
             D   E
                / \
               F   G
~~~

Ở đây A, C, E đều có đúng hai con; các nút B, D, F, G là lá. Vì vậy:

\[
I=3,\quad L=4,\quad n=7=2L-1,\quad h=3.
\]

Cây **đầy đủ**, nhưng **không hoàn hảo** vì các lá ở độ sâu khác nhau.

### Quan hệ chiều cao cho cây \(b\)-phân đầy đủ

Nếu cây đầy đủ cao \(h\), chọn một đường gốc–lá dài \(h\) cạnh. Trên đường đó có ít nhất \(h\) nút trong, nên \(I\ge h\). Do vậy:

\[
\boxed{n\ge bh+1,\qquad L\ge(b-1)h+1.}
\]

Các dấu bằng có thể đạt được bằng cây đầy đủ dạng “xương sống”: ở mỗi nút trong trên một đường dài \(h\), **một con tiếp tục đường**, còn \(b-1\) con khác đều là lá.

Kết hợp với cận trên theo \(h\):

\[
\boxed{bh+1\le n\le\frac{b^{h+1}-1}{b-1}},
\]

\[
\boxed{(b-1)h+1\le L\le b^h}.
\]

Với cây nhị phân đầy đủ:

\[
\boxed{2h+1\le n\le2^{h+1}-1,\qquad
h+1\le L\le2^h.}
\]

Từ \(h+1\le L\) suy ra **\(h\le L-1\)** với cây nhị phân đầy đủ. Đây là một cận trên về chiều cao theo số lá, **không có** ở cây nhị phân tùy ý: cây chuỗi có thể cao tùy ý nhưng chỉ một lá.

## 7. Cây hoàn hảo, cây hoàn chỉnh và cây cân bằng

Ba khái niệm này thường bị gộp làm một nhưng có ràng buộc khác nhau.

### 7.1. Cây \(b\)-phân hoàn hảo (*perfect \(b\)-ary tree*)

Cây hoàn hảo có **mọi nút trong đúng \(b\) con** và **mọi lá cùng độ sâu \(h\)**. Mọi mức từ 0 tới \(h\) đều được lấp đầy:

\[
\boxed{n=1+b+\cdots+b^h=\frac{b^{h+1}-1}{b-1},\quad L=b^h.}
\]

Với **cây nhị phân hoàn hảo**:

\[
\boxed{n=2^{h+1}-1,\qquad L=2^h,\qquad n=2L-1.}
\]

Ví dụ \(h=2\):

~~~text
               A
             /   \
            B     C
           / \   / \
          D   E F   G

         h=2, n=7, L=4
~~~

Tất cả lá D, E, F, G ở độ sâu 2. Nếu biết cây **chắc chắn hoàn hảo**, có thể suy ra chính xác:

\[
h=\log_b L=\log_b\bigl((b-1)n+1\bigr)-1.
\]

Nếu đầu vào chỉ cho \(n\) tùy ý, các biểu thức logarit này **không** chứng minh cây có hình dạng hoàn hảo; n phải đúng một giá trị của cấp số nhân tương ứng và cấu trúc phải thỏa bất biến.

### 7.2. Cây nhị phân hoàn chỉnh (*complete binary tree*)

Theo quy ước phổ biến trong cấu trúc dữ liệu, cây nhị phân **hoàn chỉnh** là cây mà **mọi tầng trừ có thể tầng cuối đều đầy**, và các nút ở **tầng cuối được lấp từ trái sang phải không có khoảng trống**.

Với \(n\ge1\), cây nhị phân hoàn chỉnh có:

\[
\boxed{h=\lfloor\log_2n\rfloor}.
\]

Nó cũng có số lá:

\[
\boxed{L=\left\lceil\frac n2\right\rceil}.
\]

Vì sao? Nếu đánh chỉ số theo thứ tự tầng từ **0** đến \(n-1\), nút ở chỉ số \(i\) có con ở \(2i+1\) và \(2i+2\) khi các chỉ số đó nhỏ hơn \(n\). Một nút là lá khi \(2i+1\ge n\), tức \(i\ge\lfloor n/2\rfloor\). Như vậy số lá là \(n-\lfloor n/2\rfloor=\lceil n/2\rceil\).

Ví dụ với \(n=6\):

~~~text
             A
           /   \
          B     C
         / \   /
        D   E F

       n=6, h=2, L=3
~~~

Cây này **hoàn chỉnh**, nhưng **không đầy đủ theo nghĩa full**, vì C chỉ có một con F. Nó cũng **không hoàn hảo**, do tầng cuối chưa đủ bốn nút.

Những công thức \(h=\lfloor\log_2n\rfloor\) và \(L=\lceil n/2\rceil\) **chỉ áp dụng cho cây nhị phân hoàn chỉnh**, không dùng cho một cây nhị phân tùy ý.

### 7.3. Cây cân bằng (*balanced tree*)

“Cân bằng” cần đi kèm **một định nghĩa hoặc bất biến cụ thể**, ví dụ giới hạn chênh lệch chiều cao hai cây con theo nút của AVL. Một cây có thể **cân bằng nhưng không hoàn hảo**.

Với những họ cây cân bằng được thiết kế tốt như **AVL** hoặc **red-black tree**, chiều cao của cây tìm kiếm nhị phân có thể được chứng minh là **\(O(\log n)\)** nhờ những ràng buộc riêng. Không được suy ra kết quả này chỉ từ việc cây có **tối đa hai con**, hoặc chỉ từ việc bản vẽ trông gần cân đối.

| Loại cây | Số con mỗi nút | Điều kiện bổ sung | Liên hệ chiều cao |
| --- | --- | --- | --- |
| Cây tổng quát | Không giới hạn | Không có | \(h\le n-1\) |
| Cây nhị phân bất kỳ | Tối đa 2 | Không có | \(\lceil\log_2(n+1)\rceil-1\le h\le n-1\) |
| Cây nhị phân full | 0 hoặc đúng 2 | Không bắt buộc các lá cùng mức | \(h+1\le L\le2^h\) |
| Cây nhị phân perfect | 0 hoặc đúng 2 | Tất cả lá cùng mức | \(h=\log_2L\) |
| Cây nhị phân complete | Tối đa 2 | Các mức đầy từ trên; mức cuối lấp trái→phải | \(h=\lfloor\log_2n\rfloor\) |
| Cây tìm kiếm AVL/red-black | Tối đa 2 | Bất biến cân bằng cụ thể | \(h=O(\log n)\) |

**Ghi nhớ:** *Full* nói về **số con của nút trong**; *perfect* nói thêm về **độ sâu lá**; *complete* nói về **lấp các vị trí theo mức**; *balanced* nói về **bất biến kiểm soát hình dạng**. Chúng không đồng nghĩa.

## 8. Số lá và kiểu phân nhánh: vì sao có nút một con làm thay đổi kết quả?

Trong cây nhị phân **bất kỳ**, một nút có thể có **0, 1 hoặc 2 con**. Đặt:

- \(I_1\): số nút có **đúng một con**.
- \(I_2\): số nút có **đúng hai con**.
- \(L\): số nút không có con.

Khi đó \(n=I_1+I_2+L\). Tổng số cạnh bằng tổng số con:

\[
n-1=I_1+2I_2.
\]

Thay \(n\) và rút gọn:

\[
I_1+I_2+L-1=I_1+2I_2
\quad\Longrightarrow\quad
\boxed{L=I_2+1.}
\]

**Kết luận tinh tế:** Trong cây nhị phân tùy ý, **số lá bằng số nút có hai con cộng một**, hoàn toàn **không phụ thuộc trực tiếp vào số nút chỉ có một con**.

Ví dụ:

~~~text
Cây X:                    Cây Y:
     A                         A
    / \                       / \
   B   C                     B   C
                            /
                           D
                          /
                         E
                        /
                       F

I2=1, I1=0, L=2       I2=1, I1=3, L=2
h=1, n=3              h=4, n=6
~~~

Kéo dài một nhánh bằng các nút có một con làm **tăng \(n\) và \(h\)** mà **không làm tăng \(L\)**. Vì thế:

- \(L=I+1\) **chỉ đúng** khi mọi nút trong đều có hai con (\(I_1=0\)).
- \(L=I_2+1\) đúng với **mọi cây nhị phân có gốc, không rỗng**, kể cả cây một nút.
- Nếu biết \(n\) và \(L\), có thể tính \(I_2=L-1\), nhưng **chưa thể biết \(h\)** nếu chưa xác định cách các nút được nối.

### Ví dụ tính nhanh

Một cây nhị phân có \(n=15\) nút và \(L=6\) lá. Khi đó:

\[
I_2=L-1=5,\qquad I_1=n-L-I_2=15-6-5=4.
\]

Nó có 5 nút hai con, 4 nút một con và 6 lá. Nếu ai đó dùng \(n=2L-1\), sẽ tính ra 11 nút và kết luận sai; cây ở đây **không phải full**.

## 9. Phạm vi của các công thức khi dữ liệu là rừng

Một **rừng** (*forest*) gồm nhiều thành phần cây không nối với nhau. Nếu rừng có \(c\) thành phần **không rỗng** với số nút, số lá và chiều cao lần lượt là \(n_j,L_j,h_j\), ta có:

\[
\boxed{n=\sum_{j=1}^{c}n_j,\qquad
L=\sum_{j=1}^{c}L_j,\qquad
|E|=n-c.}
\]

Không có một “chiều cao rừng” duy nhất được mọi tài liệu định nghĩa giống nhau. **Nếu** ta quy ước chiều cao rừng bằng chiều cao **lớn nhất** của các thành phần:

\[
h_{\mathrm{forest}}=\max_{1\le j\le c}h_j.
\]

Ta có các cận:

\[
\boxed{n\ge c+h_{\mathrm{forest}}},\qquad
\boxed{L\ge c}.
\]

Cận đầu đúng vì ít nhất một thành phần có \(h_{\mathrm{forest}}+1\) nút, còn mỗi thành phần khác có ít nhất một nút. Cận sau đúng vì mỗi cây không rỗng có ít nhất một lá.

Từ mỗi thành phần, \(I_j\ge h_j\), suy ra:

\[
\boxed{L\le n-\sum_{j=1}^{c}h_j.}
\]

**Ví dụ:** một rừng gồm cây ví dụ mục 1 (\(n_1=8,L_1=4,h_1=3\)) và một nút gốc độc lập X (\(n_2=1,L_2=1,h_2=0\)). Toàn rừng có:

\[
n=9,\quad L=5,\quad c=2,\quad |E|=7,\quad
h_{\mathrm{forest}}=3.
\]

Nếu chuyển rừng thành một cây bằng cách thêm **gốc giả** nối tới hai gốc cũ, số nút tăng thêm một, chiều cao theo số cạnh của cây mới trở thành \(h_{\mathrm{forest}}+1=4\) và số lá **không đổi** khi rừng ban đầu không rỗng. Phải ghi rõ có tính nút gốc giả hay không khi so sánh thống kê.

## 10. Chiều cao ảnh hưởng đến hiệu năng như thế nào?

Các công thức \(n,h,L\) không chỉ dùng để làm bài tập đếm; chúng giúp phân tích **độ sâu thao tác** và **bộ nhớ phụ**.

| Hoạt động | Phụ thuộc nào thường quan trọng? | Giải thích |
| --- | --- | --- |
| Duyệt toàn bộ cây DFS/BFS | \(O(n)\) thời gian | Phải xử lý mọi nút/cạnh; cây cao hay thấp vẫn có \(n\) nút |
| Theo đường từ gốc tới một nút hoặc lá | \(O(h)\) bước ở trường hợp sâu nhất | Cây chuỗi có thể đi qua \(n-1\) cạnh |
| DFS đệ quy | \(O(h)\) bộ nhớ ngăn xếp lời gọi | Cây sâu có thể vượt giới hạn recursion/stack |
| BFS với hàng đợi | Tối đa \(O(n)\) bộ nhớ phụ | Cây hình sao có thể đưa gần \(n\) nút vào hàng đợi một lúc |
| Lưu liên kết cha–con | \(O(n)\) bộ nhớ cấu trúc | Cây \(n\) nút có \(n-1\) cạnh bất kể chiều cao |
| Tìm kiếm khóa trong BST thường | \(O(h)\) so sánh theo đường tìm | Nếu cây suy biến, \(h\) có thể là \(n-1\) |
| Tìm kiếm trong BST cân bằng | \(O(\log n)\) nếu bất biến cân bằng được duy trì | Độ cao logarit là **hệ quả của bất biến bổ sung** |
| Tìm nhãn bất kỳ trong cây không có chỉ mục | \(O(n)\) trường hợp xấu nhất | Không thể loại cả nhánh chỉ từ độ cao |

**Ví dụ so sánh cùng \(n=1023\):**

- Cây nhị phân **hoàn hảo** có \(1023=2^{10}-1\), nên \(h=9\), \(L=512\).
- Cây **chuỗi** 1023 nút có \(h=1022\), \(L=1\).

Đường gốc–lá sâu nhất của hai cây khác nhau **hơn một trăm lần**, mặc dù tổng số nút bằng nhau. Tuy vậy, nếu cần duyệt **tất cả 1023 nút**, cả hai vẫn cần thời gian \(O(n)\).

### Chiều cao nhỏ không có nghĩa mọi thao tác nhanh

Cây hình sao 1023 nút có \(h=1\) nhưng gốc chứa 1022 con. Nếu các con được lưu bằng danh sách không có chỉ mục, tìm một con theo **nhãn** có thể phải duyệt đến 1022 phần tử.

Do đó, phân tích độ phức tạp phải tính cả:

- **Chiều cao \(h\):** số cạnh của đường đi sâu nhất.
- **Bậc \(d(u)\):** số con ở một nút, ảnh hưởng tới việc tìm/duyệt anh em.
- **Bất biến tìm kiếm:** liệu có thể loại bỏ nhánh nhờ thứ tự khóa hay không.
- **Cách biểu diễn:** mảng con, danh sách liên kết, map theo ID, con trỏ cha hoặc biểu diễn theo mức.

## 11. Python minh họa: đếm nút, lá, chiều cao và số nút mỗi mức

Đoạn mã sau dùng **cây có gốc tổng quát** (không giới hạn số con) và **duyệt lặp** bằng ngăn xếp, tránh phụ thuộc vào giới hạn đệ quy của Python. Mỗi nút là một **đối tượng riêng**, dù hai nút có thể mang cùng nhãn.

Trước khi chèn các con vào stack, chương trình đếm các cạnh từ cha đến con. Khi gặp lại cùng một đối tượng nút trên một đường khác, chương trình báo lỗi: cấu trúc đầu vào có thể chứa **chu trình** hoặc **nút chia sẻ nhiều cha**, không còn là cây đúng nghĩa.

~~~python
from dataclasses import dataclass, field


@dataclass(eq=False)
class Node:
    label: str
    children: list["Node"] = field(default_factory=list)


def analyze_tree(root: Node):
    if root is None:
        raise ValueError("Bài này yêu cầu một cây không rỗng")

    seen = set()
    stack = [(root, 0)]  # (node, depth)
    levels = []
    leaves = 0
    internal = 0
    edges = 0
    max_degree = 0

    while stack:
        node, depth = stack.pop()

        if node in seen:
            raise ValueError("Đã gặp lại một nút: có chu trình/chia sẻ")
        seen.add(node)

        if depth == len(levels):
            levels.append(0)
        levels[depth] += 1

        degree = len(node.children)
        max_degree = max(max_degree, degree)
        edges += degree

        if degree == 0:
            leaves += 1
        else:
            internal += 1

        for child in node.children:
            stack.append((child, depth + 1))

    n = len(seen)
    height = len(levels) - 1

    assert edges == n - 1
    assert n == internal + leaves
    assert n >= height + 1
    assert leaves <= n - height
    if height >= 1:
        assert leaves * height >= n - 1

    return {
        "nodes": n,
        "leaves": leaves,
        "internal": internal,
        "edges": edges,
        "height": height,
        "levels": levels,
        "max_degree": max_degree,
    }


R, A, B, C, D, E, F, G = [Node(s) for s in "RABCDEFG"]
R.children = [A, B, C]
A.children = [D, E]
B.children = [F]
F.children = [G]

result = analyze_tree(R)
print(result)
# {
#   'nodes': 8, 'leaves': 4, 'internal': 4, 'edges': 7,
#   'height': 3, 'levels': [1, 3, 3, 1], 'max_degree': 3
# }

# Cùng n=7 nhưng hình dạng khác:
chain_nodes = [Node(str(i)) for i in range(7)]
for i in range(6):
    chain_nodes[i].children = [chain_nodes[i + 1]]

star = Node("center", [Node(str(i)) for i in range(6)])

print(analyze_tree(chain_nodes[0])["height"])  # 6
print(analyze_tree(chain_nodes[0])["leaves"])  # 1
print(analyze_tree(star)["height"])            # 1
print(analyze_tree(star)["leaves"])            # 6
~~~

### Đọc đúng mã

1. `eq=False` giúp các nút được nhận dạng theo **danh tính đối tượng**, không theo nhãn. Hai nút đều ghi "X" vẫn là hai nút khác nhau.
2. `seen` kiểm tra lỗi tham chiếu lặp. Một cây có gốc đúng nghĩa không cho phép một nút xuất hiện ở hai vị trí khác nhau.
3. `levels[d]` là số nút tại độ sâu \(d\), nên **số phần tử của levels bằng \(h+1\)**.
4. `edges` đếm tổng số con, phải bằng \(n-1\). Đây là kiểm tra bất biến cấu trúc.
5. `leaves` chỉ tăng khi nút có 0 con. Một nút chỉ có một con **không phải lá**.
6. Mã **không sắp xếp** các con; thứ tự con không ảnh hưởng đến những số đếm \(n,L,h\).

**Giới hạn triển khai:** Bộ nhớ phụ của mã là \(O(n)\) vì có `seen`, ngăn xếp và danh sách số nút theo mức. Việc kiểm tra chu trình không thay thế quy trình xác minh tất cả thuộc tính nghiệp vụ của cây; trong môi trường nhiều luồng, không được vừa thay đổi con của nút vừa duyệt mà không có cơ chế đồng bộ thích hợp.

## 12. Đếm lá và chiều cao bằng đệ quy: cách nhìn theo cây con

Các công thức đệ quy giúp chứng minh và thiết kế thuật toán ở mức trừu tượng:

\[
\operatorname{nodes}(u)=1+\sum_{v\in\operatorname{children}(u)}\operatorname{nodes}(v),
\]

\[
\operatorname{leaves}(u)=
\begin{cases}
1,&\operatorname{children}(u)=\varnothing,\\
\sum_v\operatorname{leaves}(v),&\text{ngược lại},
\end{cases}
\]

\[
\operatorname{height}(u)=
\begin{cases}
0,&\operatorname{children}(u)=\varnothing,\\
1+\max_v\operatorname{height}(v),&\text{ngược lại}.
\end{cases}
\]

Ví dụ hiện thực ngắn:

~~~python
def recursive_stats(node):
    if not node.children:
        return (1, 1, 0)  # (nodes, leaves, height)

    parts = [recursive_stats(child) for child in node.children]
    nodes = 1 + sum(part[0] for part in parts)
    leaves = sum(part[1] for part in parts)
    height = 1 + max(part[2] for part in parts)
    return (nodes, leaves, height)


assert recursive_stats(R) == (8, 4, 3)
~~~

Với một **cây hợp lệ**, mỗi nút được duyệt đúng một lần nên thời gian là **\(O(n)\)**. Bộ nhớ ngăn xếp đệ quy phụ thuộc chiều cao **\(O(h)\)**, chưa kể danh sách con và dữ liệu trung gian. Nếu một cây suy biến thành đường dài, phiên bản đệ quy có thể **vượt giới hạn lời gọi hàm**; phiên bản lặp có cơ chế phát hiện lỗi trong mục 11 phù hợp hơn cho đầu vào rất sâu.

**Cách kiểm chứng nhanh:** Chạy hai cách trên cùng một cây hợp lệ, rồi kiểm tra các bất biến \(n=I+L\), \(|E|=n-1\), \(n\ge h+1\). Nếu công thức \(L=I+1\) không đúng, **không nhất thiết có lỗi**: có thể cây chỉ không thuộc loại nhị phân full.

## 13. Chọn công thức qua một sơ đồ quyết định

Khi gặp bài toán cho trước \(n,h,L\), hãy **xác nhận loại cây trước**. Việc áp dụng công thức của cây hoàn hảo cho cây chỉ “có tối đa hai con” sẽ cho kết quả sai.

~~~mermaid
flowchart TD
    A["Đề bài có cây có gốc không rỗng?"] --> B{"Có giới hạn tối đa b con?"}
    B -->|Không| C["Dùng n ≥ h+1; L ≤ n−h; n ≤ 1+hL"]
    B -->|Có| D["Có n ≤ (b^(h+1)−1)/(b−1); L ≤ b^h"]
    D --> E{"Mọi nút trong có đúng b con?"}
    E -->|Không| F["Không tự dùng L=(b−1)I+1"]
    E -->|Có| G["Dùng n=bI+1; L=(b−1)I+1"]
    G --> H{"Mọi lá cùng độ sâu h?"}
    H -->|Có| I["Perfect: n=(b^(h+1)−1)/(b−1), L=b^h"]
    H -->|Không| J["Full nhưng chưa chắc perfect"]
    D --> K{"Cây nhị phân complete?"}
    K -->|Có| L["h=floor(log2 n), L=ceil(n/2)"]
    K -->|Không| M["Không dùng công thức complete"]
~~~

Sơ đồ nói về **giả thiết đủ** để dùng công thức, không phải danh sách các điều kiện loại trừ lẫn nhau: một cây nhị phân hoàn hảo vừa **full** vừa **complete**. Ngược lại, một cây hoàn chỉnh có thể không full, và một cây full có thể không hoàn chỉnh.

### Bảng công thức tổng hợp

| Kiểu cây / giả thiết | Quan hệ về nút và lá | Quan hệ về chiều cao |
| --- | --- | --- |
| Cây có gốc \(n\ge1\) bất kỳ | \(n=I+L\); \(L=1+\sum_{\mathrm{internal}}(\deg^+-1)\) | \(0\le h\le n-1\) |
| Cây bất kỳ, \(h\ge1\), không giới hạn bậc | \(\lceil(n-1)/h\rceil\le L\le n-h\) | \(h+L\le n\le1+hL\) |
| Cây \(b\)-phân, tối đa \(b\ge2\) con | \(n\le(b^{h+1}-1)/(b-1)\); \(L\le b^h\) | \(h\ge\lceil\log_b((b-1)n+1)\rceil-1\) |
| Cây \(b\)-phân full, \(b\ge2\) | \(n=bI+1\); \(L=(b-1)I+1\) | \(bh+1\le n\le(b^{h+1}-1)/(b-1)\) |
| Cây nhị phân bất kỳ | \(L=I_2+1\), \(I_2\) là số nút hai con | \(h\ge\lceil\log_2(n+1)\rceil-1\) |
| Cây nhị phân full | \(n=2L-1\), \(L=I+1\) | \(h+1\le L\le2^h\) |
| Cây \(b\)-phân perfect | \(n=(b^{h+1}-1)/(b-1)\); \(L=b^h\) | \(h=\log_b L\) |
| Cây nhị phân complete, \(n\ge1\) | \(L=\lceil n/2\rceil\) | \(h=\lfloor\log_2 n\rfloor\) |
| Rừng \(c\) cây không rỗng | \(|E|=n-c\), \(L=\sum L_j\) | Tính theo từng \(h_j\) hoặc quy ước \(h_{\mathrm{forest}}=\max h_j\) |

**Cách sử dụng:** Đọc dòng có giả thiết đúng **mạnh nhất mà đề bài đã cho**. Nếu đề chỉ nói “cây nhị phân”, chỉ được dùng các công thức cho cây nhị phân bất kỳ, **không** tự giả sử full, complete hoặc balanced.

## 14. Ví dụ ứng dụng: chiều cao, lá và cách lưu dữ liệu

### Thư mục và đường dẫn

Một hệ thống tệp có hàng nghìn thư mục con trực tiếp dưới một thư mục gốc có thể có **chiều cao nhỏ nhưng rất nhiều lá**. Chi phí tìm một đường dẫn từ gốc có thể liên quan đến chiều cao, còn chi phí liệt kê con hoặc so khớp tên trong một thư mục lại phụ thuộc **số con** và cách lập chỉ mục ở thư mục đó.

### Cây biểu thức

Một biểu thức có nhiều toán tử lồng nhau theo một chuỗi dài có thể sinh **cây cú pháp cao**, làm quá trình tính đệ quy hoặc phân tích đệ quy cần ngăn xếp sâu. Một biểu thức được nhóm cân đối có thể đạt cùng số nút nhưng **chiều cao thấp hơn**.

### Heap nhị phân bằng mảng

Heap nhị phân thông dụng giữ bất biến **hình dạng complete**. Vì vậy chiều cao của nó là \(\lfloor\log_2 n\rfloor\), và những thao tác **sift-up/sift-down** đi theo một đường có độ dài \(O(\log n)\). Bất biến **heap-order** kiểm soát thứ tự ưu tiên cha/con, còn **complete** kiểm soát chiều cao.

### Cây tìm kiếm nhị phân

Nếu chèn các khóa đã sắp tăng vào **BST không tự cân bằng**, cây có thể trở thành chuỗi và chiều cao gần \(n-1\). AVL và red-black tree dùng những quy tắc cân bằng khác nhau để giữ chiều cao \(O(\log n)\), nhờ đó giới hạn chi phí tìm kiếm trên đường từ gốc.

### Cây phân cấp tổ chức

Hai tổ chức cùng có 1.000 nhân sự nhưng một nơi có nhiều tầng quản lý và mỗi quản lý ít cấp dưới, nơi khác có ít tầng và nhiều cấp dưới trực tiếp. **Chiều cao** phản ánh số tầng quản lý tối đa; **số lá** có thể đại diện các đơn vị không quản lý thêm ai; **bậc nút** phản ánh số cấp dưới trực tiếp. Không đại lượng nào đơn lẻ mô tả đầy đủ hiệu quả vận hành.

### Cây tiền tố (*trie*)

Chiều cao trie thường liên quan tới **độ dài khóa** theo đơn vị ký tự hoặc bit. Một trie có thể có rất nhiều nhánh nhưng chiều cao không vượt quá chiều dài khóa lớn nhất (trong mô hình không nén). Số lá phụ thuộc việc đánh dấu khóa kết thúc và cấu trúc các chuỗi; không thể tự giả sử mỗi khóa tương ứng một lá nếu khóa có thể là **tiền tố** của khóa khác.

**Bài học chung:** Chiều cao cho biết **đường sâu nhất**, số lá cho biết **điểm kết thúc không có con**, còn số nút đo **quy mô tổng**. Khi phân tích ứng dụng, cần xem cả **số con ở từng nút** và **bất biến dữ liệu**.

## 15. Những nhầm lẫn thường gặp

1. **“Cây có chiều cao \(h\) thì có đúng \(h\) mức.”** Với cách đếm chiều cao bằng cạnh, cây có **\(h+1\) mức**, từ 0 tới \(h\).
2. **“Gốc luôn là nút trong.”** Với cây một nút, gốc không có con nên **đồng thời là lá**.
3. **“Cây \(n\) nút có chiều cao luôn bằng \(\log_2n\).”** Sai: cây chuỗi có \(h=n-1\); chỉ một số lớp cây có bất biến hình dạng mới có chiều cao logarit.
4. **“Có tối đa \(b\) con nghĩa là mọi nút trong có đúng \(b\) con.”** Sai: đây là hai giả thiết khác nhau, làm công thức số lá thay đổi.
5. **“Full và complete là một.”** Sai: full nói mọi nút trong có số con cố định, complete nói các vị trí theo tầng được lấp không có khoảng trống từ trái sang phải.
6. **“Perfect chỉ cần các lá cùng mức.”** Với định nghĩa trong bài, perfect còn yêu cầu **mọi nút trong có đúng \(b\) con**.
7. **“Một cây nhị phân luôn có \(L=I+1\).”** Sai nếu có nút một con; công thức tổng quát là \(L=I_2+1\).
8. **“Thêm một nút vào cây luôn thêm một lá.”** Nếu thêm một con vào một lá cũ, lá cũ trở thành nút trong và nút mới thành lá: **số lá không đổi**.
9. **“Chiều cao và số lá luôn tăng cùng nhau.”** Có thể kéo dài nhánh qua nhiều nút một con, làm \(h\) tăng mà \(L\) không tăng.
10. **“Nếu \(L=b^h\) thì mọi cây chắc chắn hoàn hảo mà không cần xét điều kiện.”** Phải biết cây có tối đa \(b\) con và độ sâu không vượt \(h\), cùng quy ước lá/gốc; với những điều kiện đó dấu bằng mới buộc các mức trung gian phân nhánh tối đa.
11. **“Công thức \((b^{h+1}-1)/(b-1)\) dùng cho cả \(b=1\).”** Sai vì chia cho 0; cây có tối đa một con là chuỗi với \(n=h+1\).
12. **“Cây hai nhánh trái/phải luôn có hai lá.”** Sai: cây nhị phân cao hơn có thể có rất nhiều lá; cây một nhánh dài chỉ có một lá.
13. **“Cây có số nút lớn thì chiều cao phải lớn.”** Chỉ đúng nếu số con mỗi nút bị giới hạn và phải đọc như **cận dưới**; với cây tổng quát không giới hạn bậc, cây hình sao có \(h=1\) và rất nhiều nút.
14. **“Độ cao tính bằng nút hay cạnh đều có thể thay vào công thức mà không đổi.”** Sai: chiều cao theo số nút lớn hơn đúng 1 với cây không rỗng.
15. **“Số lá của rừng là số lá của cây cao nhất.”** Sai: phải **cộng số lá của mọi thành phần**, kể cả cây một nút.
16. **“DFS luôn tốn bộ nhớ \(O(n)\) cho lời gọi đệ quy.”** Bộ nhớ call stack sâu nhất là \(O(h)\); trong trường hợp xấu nhất \(h\) có thể bằng \(n-1\), nên khi ấy mới thành \(O(n)\).
17. **“Bậc nút không ảnh hưởng độ trễ nếu chiều cao nhỏ.”** Sai: một gốc có rất nhiều con vẫn có thể tốn nhiều bước để tìm một con nếu không có chỉ mục.

## 16. Câu hỏi và bài tập tự kiểm tra kèm lời giải

### Câu 1. Cây chỉ có một nút

Một cây chỉ gồm gốc A. Hãy xác định \(n,L,I,h\), số mức và số cạnh.

**Lời giải:** \(n=1\), \(L=1\), \(I=0\), \(h=0\) cạnh; có \(h+1=1\) mức và \(n-1=0\) cạnh. Gốc A **cũng là lá**.

### Câu 2. Đếm trên cây minh họa

Cho cây có các cạnh R—A, R—B, R—C, A—D, A—E, B—F, F—G; gốc R. Tính \(n,L,h\) và số nút mỗi mức.

**Lời giải:** Có 8 nút, bốn lá C, D, E, G nên \(L=4\). Đường sâu nhất R—B—F—G có 3 cạnh nên \(h=3\). Số nút theo mức 0 đến 3 lần lượt là **1, 3, 3, 1**. Số cạnh là 7.

### Câu 3. Cùng số nút, khác hình dạng

Với \(n=11\), hãy xây một cây có số lá ít nhất và một cây có số lá nhiều nhất khi không giới hạn số con. Chiều cao mỗi cây bằng bao nhiêu?

**Lời giải:** Cây chuỗi 11 nút có \(h=10,L=1\). Cây hình sao với một gốc và 10 con trực tiếp có \(h=1,L=10\). Hai ví dụ chứng minh **số nút không xác định duy nhất chiều cao hoặc số lá**.

### Câu 4. Giới hạn số lá khi biết \(n,h\)

Một cây tổng quát có \(n=19\) nút và chiều cao \(h=4\) cạnh. Số lá có thể nằm trong khoảng nào?

**Lời giải:**

\[
\left\lceil\frac{n-1}{h}\right\rceil
=\left\lceil\frac{18}{4}\right\rceil=5,
\]

\[
n-h=19-4=15.
\]

Vậy **\(5\le L\le15\)**. Cận dưới có thể đạt với các nhánh xuất phát từ gốc dài \(4,4,4,4,2\) cạnh: tổng \(18\) cạnh và 5 lá. Cận trên có thể đạt bằng một đường dài 4 cạnh kèm 14 lá phụ.

### Câu 5. Số nút tối đa của cây nhị phân

Cây nhị phân có chiều cao \(h=3\). Tối đa có bao nhiêu nút và bao nhiêu lá? Khi nào đạt được?

**Lời giải:**

\[
n\le2^{3+1}-1=15,\qquad L\le2^3=8.
\]

Đạt đồng thời hai cận nếu cây **nhị phân hoàn hảo** cao 3: các mức 0,1,2,3 lần lượt có 1,2,4,8 nút.

### Câu 6. Cận dưới chiều cao từ số nút

Một cây nhị phân tùy ý có \(n=18\) nút. Chiều cao nhỏ nhất có thể là bao nhiêu? Có được kết luận chiều cao đúng bằng giá trị đó không?

**Lời giải:** Vì cây cao 3 tối đa có 15 nút nên 18 nút cần ít nhất chiều cao 4:

\[
h\ge\left\lceil\log_2(18+1)\right\rceil-1
=\left\lceil\log_2 19\right\rceil-1=4.
\]

Không thể kết luận \(h=4\) khi chỉ biết n; một cây 18 nút có thể có chiều cao tới **17** nếu là chuỗi.

### Câu 7. Cây nhị phân đầy đủ với số nút trong

Một cây nhị phân full có \(I=10\) nút trong. Tính \(L,n\) và khoảng chiều cao có thể có.

**Lời giải:**

\[
L=I+1=11,\qquad n=2I+1=21.
\]

Cận dưới \(L\le2^h\) cho \(h\ge\lceil\log_2 11\rceil=4\). Cận trên của chiều cao là \(h\le L-1=10\) từ tính full. Vì vậy **\(4\le h\le10\)**; muốn xác định chính xác \(h\), cần biết cách các nút trong phân bố.

### Câu 8. Cây tam phân đầy đủ

Một cây **full 3-ary**, mỗi nút trong đúng ba con, có \(I=8\). Tính số nút và lá.

**Lời giải:** Với \(b=3\):

\[
n=bI+1=3\cdot8+1=25,
\]

\[
L=(b-1)I+1=2\cdot8+1=17.
\]

Kiểm tra \(n=I+L=8+17=25\), số cạnh \(n-1=24=3I\).

### Câu 9. Cây nhị phân hoàn chỉnh có 26 nút

Một cây complete binary tree lưu các nút theo thứ tự mức, không có khoảng trống. Tính chiều cao và số lá nếu \(n=26\).

**Lời giải:**

\[
h=\lfloor\log_2 26\rfloor=4,\qquad
L=\lceil26/2\rceil=13.
\]

Không dùng \(n=2L-1\) vì cây complete có thể có một nút trong chỉ một con.

### Câu 10. Cây nhị phân hoàn hảo cao 5

Cây nhị phân perfect có chiều cao 5 cạnh. Tính tổng số nút, số lá, số nút trong và số mức.

**Lời giải:**

\[
n=2^{5+1}-1=63,\quad L=2^5=32,\quad
I=n-L=31.
\]

Số mức là \(h+1=6\). Bất biến full cũng đúng vì \(L=I+1=32\).

### Câu 11. Nút một con không làm tăng lá

Trong một cây nhị phân, có 5 nút đúng hai con và 4 nút đúng một con. Cây có bao nhiêu lá và tổng số nút?

**Lời giải:**

\[
L=I_2+1=6,\qquad
n=I_1+I_2+L=4+5+6=15.
\]

Có 14 cạnh. Công thức \(L=I+1\) **không phù hợp**, vì cây có các nút một con.

### Câu 12. Rừng với các chiều cao khác nhau

Một rừng có ba cây: cây thứ nhất là cây nhị phân hoàn hảo cao 2; cây thứ hai là chuỗi 3 nút; cây thứ ba chỉ có một nút. Tính tổng số nút, lá, cạnh và chiều cao rừng nếu định nghĩa bằng chiều cao lớn nhất của các thành phần.

**Lời giải:**

- Cây 1: \(n_1=7,L_1=4,h_1=2\).
- Cây 2: \(n_2=3,L_2=1,h_2=2\).
- Cây 3: \(n_3=1,L_3=1,h_3=0\).

Vậy \(n=11\), \(L=6\), \(c=3\), \(|E|=n-c=8\) và \(h_{\mathrm{forest}}=2\).

### Câu 13. Độ sâu đường đi và giới hạn bộ nhớ

Có hai cây cùng chứa 1023 nút: một cây nhị phân perfect và một cây chuỗi. Nếu duyệt DFS bằng đệ quy từ gốc, độ sâu lời gọi tối đa khác nhau ra sao?

**Lời giải:** Cây perfect có \(1023=2^{10}-1\), nên \(h=9\); cây chuỗi có \(h=1022\). Theo quy ước chiều cao bằng cạnh, số mức trên đường đệ quy sâu nhất lần lượt là **10** và **1023**. Bộ nhớ call stack tỷ lệ \(O(h+1)\); vì thế cây chuỗi dễ vượt giới hạn đệ quy hơn.

### Câu 14. Có thể suy ra chiều cao chỉ từ số lá không?

Hai cây đều có \(L=6\) lá. Cây thứ nhất có một gốc nối thẳng tới sáu lá. Cây thứ hai được tạo bằng cách thêm 100 nút chỉ có một con nối tiếp trên một nhánh của cây thứ nhất. Chiều cao và số lá biến đổi thế nào?

**Lời giải:** Cây đầu có \(h=1,L=6\). Mỗi lần thêm một nút trên một nhánh bằng phép **chia một cạnh thành hai cạnh**, không làm mất lá hay tạo lá mới, nhưng đường sâu nhất tăng dần. Sau 100 nút, chiều cao có thể là **101**, còn số lá vẫn **6**. Do đó **\(L\) riêng lẻ không xác định \(h\)**.

### Câu 15. Cận số nút của cây 3-phân cao 4

Một cây có gốc, mỗi nút tối đa 3 con và chiều cao 4. Tổng số nút và số lá nhiều nhất có thể là bao nhiêu?

**Lời giải:**

\[
n_{\max}=1+3+3^2+3^3+3^4
=\frac{3^5-1}{3-1}=\frac{243-1}{2}=121,
\]

\[
L_{\max}=3^4=81.
\]

Cả hai đạt được với **cây tam phân hoàn hảo** cao 4.

### Câu 16. Thao tác thêm con có làm tăng số lá?

Một cây có lá X. Chèn một nút mới Y làm con duy nhất của X. Hãy tính số nút, số cạnh, số lá thay đổi ra sao. Có chắc chiều cao cũng tăng một không?

**Lời giải:** \(\Delta n=+1\), \(\Delta|E|=+1\), còn \(\Delta L=0\): X không còn là lá, Y trở thành lá. **Chiều cao chỉ chắc chắn tăng một nếu X nằm ở độ sâu bằng chiều cao cũ**, tức là lá sâu nhất. Nếu X là lá nông hơn, cây có thể giữ nguyên chiều cao.

### Câu 17. Điều kiện kiểm chứng cây full

Một cây nhị phân có \(n=31\) nút và \(L=9\) lá. Có thể là cây nhị phân full không? Từ hai số đó suy ra được điều gì về số nút có một hoặc hai con?

**Lời giải:** Nếu full thì phải có \(n=2L-1=17\), trái với \(n=31\). Vậy cây **không full**. Vì là cây nhị phân:

\[
I_2=L-1=8,\qquad
I_1=n-L-I_2=31-9-8=14.
\]

Nó có 8 nút hai con, 14 nút một con và 9 lá.

## 17. Ghi nhớ và phương pháp giải

**Bước 1 — Thống nhất quy ước.** Chiều cao \(h\) tính bằng **số cạnh** từ gốc tới lá sâu nhất; một cây không rỗng có \(h+1\) mức. Cây một nút có \(n=L=1,h=0\).

**Bước 2 — Dùng bất biến đúng cho mọi cây có gốc:**

\[
\boxed{|E|=n-1,\qquad n=I+L,\qquad
L=1+\sum_{\mathrm{internal}}(\deg^+-1),\qquad
n\ge h+1.}
\]

Nếu biết \(n,h\ge1\) mà **không giới hạn số con**, ta còn có:

\[
\boxed{\left\lceil\frac{n-1}{h}\right\rceil\le L\le n-h.}
\]

**Bước 3 — Kiểm tra giả thiết phân nhánh.** Nếu mỗi nút có tối đa \(b\ge2\) con:

\[
\boxed{n\le\frac{b^{h+1}-1}{b-1},\qquad L\le b^h.}
\]

Nếu **mọi nút trong có đúng \(b\) con**, thêm \(n=bI+1\) và \(L=(b-1)I+1\). Nếu cây **hoàn hảo**, các cận về số nút và lá theo \(h\) đạt dấu bằng. Riêng cây nhị phân **hoàn chỉnh** có \(h=\lfloor\log_2 n\rfloor\) và \(L=\lceil n/2\rceil\).

**Bước 4 — Liên hệ tới thuật toán.** Đường gốc–lá dài nhất có \(h\) cạnh, nên duyệt dọc đường hoặc tìm kiếm theo đường trong BST thường phụ thuộc \(O(h)\). Duyệt toàn bộ cây cần \(O(n)\), bất kể hình dạng. Để suy ra \(h=O(\log n)\) cho mọi đầu vào của một cấu trúc, cần **bất biến hình dạng hoặc cân bằng phù hợp**, không chỉ cần chữ “cây”.

**Tư duy cần giữ:** **Số nút** đo quy mô, **số lá** đo các điểm kết thúc/nhánh và **chiều cao** đo độ sâu lớn nhất. Chỉ khi biết **loại cây và ràng buộc số con** mới có thể liên kết ba đại lượng bằng công thức chính xác thay vì chỉ các cận.
