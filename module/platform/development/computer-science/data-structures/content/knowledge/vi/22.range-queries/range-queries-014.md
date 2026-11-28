# Hợp thành nhãn cập nhật và bảo toàn bất biến tổng hợp

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **giá trị tổng hợp của một đoạn**, **nhãn cập nhật đang trì hoãn** và **giá trị ở các nút con chưa nhận nhãn** trong cây đoạn có lazy propagation.
- Phát biểu hợp đồng của ba phép toán **gộp kết quả (`merge`)**, **áp nhãn lên giá trị tổng hợp (`apply`)** và **hợp thành nhãn theo thứ tự thời gian (`compose`)**.
- Viết công thức chính xác cho **cộng, gán, nhân** trên cả đoạn khi truy vấn **tổng**; hiểu vì sao `SET(0)` là cập nhật thật chứ không phải nhãn rỗng.
- Suy ra **bất biến ở nút trong khi nhãn chưa đẩy xuống** và chứng minh vì sao `push` không đổi dữ liệu logic, còn `pull` chỉ hợp lệ sau khi nhãn ở cha đã được chuyển xuống.
- Thiết kế cặp nhãn affine `(m,b)`, chứng minh phép hợp thành **`new∘old`** và phân biệt **tính kết hợp** với **tính giao hoán**.
- Kiểm tra ba định luật tương thích: nhãn đơn vị, hợp thành nhãn và bảo toàn phép gộp trên hai đoạn liền nhau.
- Cài đặt **một cây đoạn lazy tổng quát theo các phép toán được cung cấp**, rồi chuyên biệt hóa thành **range ADD/SET/MUL + range SUM**.
- Mở rộng giá trị tổng hợp thành **(sum, min, max)** và xử lý đúng nhân với hệ số âm.
- Giải thích vì sao cùng một nhãn không thể cập nhật `gcd` chỉ từ gcd cũ, hoặc áp một phép biến đổi không tương thích với thông tin đang lưu.
- Tự xây bộ kiểm tra bằng mảng đối chiếu, thử mảng rỗng, đoạn nửa mở, nhãn gán 0, cập nhật chồng lấn, thứ tự nhãn và giới hạn độ phức tạp.

## 1. Vấn đề: cây có thể trả đúng tổng khi các con còn chứa dữ liệu cũ

Trong module `COMPUTER_SCIENCE_DATA_STRUCTURES`, chúng ta lựa chọn cấu trúc dữ liệu bằng **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ**. Với truy vấn đoạn, cây đoạn (segment tree) chia mảng thành các đoạn liên tiếp; mỗi nút lưu một giá trị **tổng hợp** để tránh đi qua từng phần tử khi hỏi một khoảng.

**Lan truyền lười (lazy propagation)** làm nảy sinh câu hỏi tưởng như mâu thuẫn: một nút cha đã nhận phép cập nhật, nhưng các con vẫn chưa nhận. Làm sao kết quả tổng hợp của cha vẫn đúng?

Xét mảng tám phần tử:

```text
Chỉ số:     0  1  2  3  4  5  6  7
A:          2  4  1  3  5  7  6  8
Tổng: 36
```

Ta muốn **gán tất cả phần tử bằng 10**:

```text
range_set(0, 8, 10)

Mảng LOGIC sau cập nhật:
[10, 10, 10, 10, 10, 10, 10, 10]
Tổng = 80
```

Một cây lazy có thể giữ:

```text
                       [0,8)
                 aggregate = 80
               pending = SET(10)
                    /         \
               [0,4)         [4,8)
              sum = 10       sum = 26
             pending=ID      pending=ID
```

**Hai con chưa chứa tổng mới 40 và 40**. Nhưng nút gốc đã trả được tổng 80 vì nó ghi nhớ **phép gán đang đợi** cho hai con. Nếu có truy vấn chỉ hỏi `[0,8)`, ta không cần đi xuống.

Lúc truy vấn `[2,4)`, hệ thống phải đẩy nhãn `SET(10)` xuống các con theo đúng quy tắc. **Thứ tự hợp thành nhãn** là vấn đề cốt lõi: nếu con đang đợi `ADD(3)` rồi cha nhận `SET(10)`, kết quả phải là 10 chứ không phải 13; nếu cha nhận `ADD(3)` *sau* một nhãn `SET(10)`, kết quả phải là 13.

### 1.1. Quy ước đoạn nửa mở

Trong toàn bài, một đoạn chỉ số có dạng **`[l,r)`**, chứa `l,l+1,\ldots,r-1` nhưng **không chứa `r`**. Với `n` phần tử:

\[
0\le l\le r\le n.
\]

- `[0,n)` là toàn mảng.
- `[i,i+1)` là một phần tử.
- `[i,i)` là đoạn rỗng, không cập nhật gì.
- `[n,n)` cũng là đoạn rỗng hợp lệ.
- `[r,l)` với `r>l` không được dùng để diễn đạt đoạn đảo; phải báo lỗi nếu đầu trái lớn hơn đầu phải.

Một nút quản lý `[L,R)` được tách tại `M=(L+R)//2` thành hai đoạn **`[L,M)`** và **`[M,R)`**. Độ dài của nút là `R-L`.

### 1.2. Ba phép toán không được nhầm lẫn

| Phép toán | Đầu vào | Kết quả cần đảm bảo |
| --- | --- | --- |
| **merge** | Hai giá trị tổng hợp của hai đoạn liền nhau | Giá trị tổng hợp của đoạn hợp |
| **apply** | Một nhãn, giá trị tổng hợp hiện tại và độ dài đoạn | Giá trị tổng hợp **sau khi** nhãn tác động đến mọi phần tử đoạn |
| **compose** | Nhãn mới và nhãn cũ | Một nhãn có tác động tương đương **làm cũ trước, mới sau** |

Để tái sử dụng một cây lazy cho nhiều bài toán, cần thiết kế đúng **cả ba**, không chỉ thay công thức tính tổng thành một hàm khác.

## 2. Bất biến tổng hợp của cây đoạn

Mỗi nút `v` quản lý một khoảng `I_v=[L,R)`. Gọi `S(I)` là kết quả tổng hợp của các phần tử thuộc đoạn `I` theo đúng thứ tự. Ví dụ, khi `merge(a,b)=a+b`:

\[
S([L,R))=\sum_{i=L}^{R-1}A[i].
\]

Với phép tổng, đoạn rỗng trả **0**. Với `min`, một identity thường dùng là `+\infty`; với `max` là `-\infty`. Không được tự động dùng 0 làm kết quả của mọi đoạn rỗng.

### 2.1. Bất biến không có nhãn

Khi một nút trong **không có công việc trì hoãn**, giá trị tổng hợp của nó được gộp từ hai con:

\[
tree[v]=merge(tree[2v],tree[2v+1]).
\]

Khi nút là lá `[i,i+1)`, giá trị tổng hợp chính là biểu diễn của một phần tử `A[i]` (hoặc một thống kê được tạo từ phần tử ấy).

### 2.2. Bất biến có nhãn đang đợi

Đặt `tag[v]` là một phép biến đổi đã được tính vào **`tree[v]`**, nhưng còn phải truyền xuống các con khi đi sâu. Khi nút trong đang giữ nhãn `t`:

\[
\boxed{
tree[v]
=apply\left(t,\ merge(tree[2v],tree[2v+1]),\ R-L\right).
}
\]

Trong trường hợp **chỉ cộng delta** và lưu **sum**:

\[
tree[v]
=tree[2v]+tree[2v+1]+lazy[v]\,(R-L).
\]

Trong trường hợp **gán `s` toàn đoạn**:

\[
tree[v]=s\,(R-L),
\]

ngay cả khi hai con vẫn lưu tổng cũ. Với các phép gộp khác, phải thay `apply` bằng phép tác động tương ứng.

**Ý nghĩa quan trọng:** `tree[v]` đã tính **tác động của `tag[v]`**. Nếu truy vấn phủ trọn nút, chỉ trả `tree[v]`; không cộng hay gán thêm nhãn lần nữa.

### 2.3. Nhãn của cha và con không nhất thiết diễn ra cùng thời điểm

Giả sử con đã nhận cập nhật `g` ở một thời điểm cũ, nhưng cha sau đó nhận cập nhật `f` phủ cả đoạn và chưa đẩy xuống. Khi đẩy từ cha xuống con:

```text
Giá trị gốc ở con: x

Con đã chờ nhãn cũ: g
Cha mới có nhãn:    f

Tác động đúng: x -> g(x) -> f(g(x))
```

Do đó nhãn chờ mới của con phải là **`f∘g`**, không phải `g∘f`. Nếu các nhãn không giao hoán, đảo thứ tự sẽ làm sai dữ liệu.

Thứ tự thời gian này được duy trì trong thuật toán chuẩn bởi quy tắc **`push` nhãn cha trước khi đi sâu vào một cập nhật giao một phần**. Vì vậy nếu cha còn nhãn phủ toàn đoạn thì nhãn đó thuộc về một cập nhật **mới hơn** các nhãn chưa đẩy trong con.

### 2.4. Bất biến không phải “mọi lá luôn mang giá trị mới nhất”

Sau `range_set(0,n,10)`, có thể chỉ gốc đổi. Khi đó:

- **Mảng logic** đúng là toàn số 10.
- **Giá trị ở những lá chưa được `push` tới** có thể vẫn là giá trị trước cập nhật.
- **Các truy vấn** vẫn phải trả đúng vì thuật toán đẩy nhãn trên đường cần thiết.
- Nếu muốn vật chất hóa mọi phần tử ra một danh sách, phải làm thêm công việc duyệt cây, thường **O(n)**.

Không nên dùng cách đọc trực tiếp mảng `tree` ở các lá cũ như thể nó đã được đồng bộ ngay sau mọi cập nhật.

## 3. Ba định luật để một thiết kế lazy đúng

Ta trừu tượng hóa:

- `\oplus`: phép **gộp hai giá trị tổng hợp** theo thứ tự trái rồi phải.
- `e`: phần tử đơn vị của phép gộp.
- `f,g,h`: các nhãn cập nhật có thể tác động lên mọi phần tử của một đoạn.
- `I`: nhãn đơn vị (*identity tag*) không thay đổi dữ liệu.
- `apply(f,S,k)`: tác động của `f` lên một đoạn có `k` phần tử và giá trị tổng hợp `S`.
- `compose(f,g)`: nhãn tương đương thực hiện `g` trước, `f` sau.

### 3.1. Luật gộp: monoid của giá trị tổng hợp

Phép `\oplus` phải **kết hợp**:

\[
(a\oplus b)\oplus c=a\oplus(b\oplus c),
\]

và `e` là đơn vị **hai phía**:

\[
e\oplus a=a\oplus e=a.
\]

Đây là một **monoid**. Không bắt buộc `a\oplus b=b\oplus a`: phép nối chuỗi cũng kết hợp nhưng **không giao hoán**. Cây phải giữ đúng thứ tự **trái rồi phải**.

### 3.2. Luật nhãn: identity và hợp thành

Với nhãn đơn vị `I`:

\[
apply(I,S,k)=S.
\]

Với nhãn cũ `g` và nhãn mới `f`, yêu cầu:

\[
\boxed{
apply(compose(f,g),S,k)
=apply(f,\ apply(g,S,k),\ k).
}
\]

Nếu viết hàm `compose(new,old)`, nhãn trả về là **`new∘old`**. Phép hợp thành các hàm luôn có tính kết hợp:

\[
compose(h,compose(f,g))
=compose(compose(h,f),g).
\]

Điều này cho phép hợp nhất nhiều nhãn đang đợi mà không phụ thuộc cách đặt dấu ngoặc, **nhưng không cho phép đảo thứ tự thời gian**.

### 3.3. Luật phân phối trên hai đoạn liền nhau

Giả sử `S_L` và `S_R` là thống kê của hai đoạn **liền nhau** có độ dài `k_L,k_R`. Để `push` bảo toàn tổng hợp, cần:

\[
\boxed{
apply(f,S_L\oplus S_R,k_L+k_R)
=apply(f,S_L,k_L)\oplus apply(f,S_R,k_R).
}
\]

Đây là điều kiện mà việc áp **một nhãn lên nút cha** phải tương đương với việc áp **cùng nhãn lên cả hai con rồi gộp**.

Nếu luật này không đúng đối với metadata đang lưu, thuật toán **không thể** đẩy nhãn và giữ kết quả chỉ bằng các giá trị tổng hợp hiện có.

### 3.4. Tại sao cần ba định luật, không chỉ một công thức?

| Luật | Bảo vệ thao tác nào? | Ví dụ lỗi nếu vi phạm |
| --- | --- | --- |
| Gộp kết hợp + identity | Xây cây, tổng hợp kết quả truy vấn từ nhiều nút | Dùng phép trừ thông thường làm `merge` |
| Nhãn đơn vị + hợp thành | Nhiều cập nhật chồng lấn, chuyển nhãn cũ/mới | `SET(2)` sau `ADD(5)` bị tính thành 7 |
| Phân phối nhãn qua hai con | `apply` ở cha và `push` xuống con | Cập nhật GCD sau cộng đoạn chỉ từ GCD cũ |

Với những kiểu dữ liệu lớn, còn cần xác định **chi phí của `merge/apply/compose`**; cận O(log n) của số nút được đi qua không tự đảm bảo thời gian CPU O(log n) nếu các phép toán đó tốn O(k) theo kích thước payload.

## 4. Ba thao tác duy trì bất biến: apply, push, pull

### 4.1. `apply(v,tag)` — cập nhật ngay giá trị tổng hợp, hoãn việc xuống con

Nút `v` quản lý `[L,R)`, độ dài `k=R-L`. Khi một nhãn mới `f` phủ trọn nút:

```text
tree[v] = apply(f, tree[v], k)
tag[v]  = compose(f, tag[v])  # MỚI sau CŨ.
```

Hai dòng cùng thực hiện một cập nhật logic: tổng hợp của nút đã đúng ngay bây giờ; nhãn lưu khoản nợ cần chuyển xuống hai con **ở thời điểm sau**. Không cần đi xuống các lá nếu đoạn của nút đã được phủ trọn.

### 4.2. `push(v)` — chuyển khoản nợ từ cha xuống con

Nếu `v` là nút trong và `tag[v]=t` khác identity:

```text
mid = (L+R)//2
apply(left_child,  t, [L,mid))
apply(right_child, t, [mid,R))
tag[v] = identity_tag
```

Ở mỗi con, `apply` **hợp thành nhãn của cha với nhãn con đang có** theo thứ tự **cha sau con**. Tổng hợp ở cha **không thay đổi** do `push`: dữ liệu logic không đổi, chỉ nơi ghi nhớ cập nhật đổi.

Với một **lá**, không có hai con thật để chuyển; `push` phải dừng. Có thể để nhãn lá tồn tại hoặc chuẩn hóa về identity theo một chính sách nhất quán.

### 4.3. `pull(v)` — lấy lại giá trị tổng hợp sau khi cập nhật con

Khi `v` đã được `push` và hai con đã hoàn tất cập nhật:

```text
assert tag[v] == identity_tag
tree[v] = merge(tree[left_child], tree[right_child])
```

Điểm dễ sai nhất: **không gọi `pull` ngay khi cha vẫn còn nhãn chưa đẩy**, vì tổng hợp hai con khi đó có thể còn cũ.

### 4.4. Bảng thao tác theo quan hệ giao đoạn

| Quan hệ giữa đoạn nút `[L,R)` và đoạn `[ql,qr)` | Cập nhật đoạn | Truy vấn đoạn |
| --- | --- | --- |
| **Không giao nhau** | Không thay đổi | Trả identity `e` của giá trị tổng hợp |
| **Được phủ hoàn toàn** | `apply` nhãn rồi dừng | Trả `tree[v]` ngay |
| **Giao một phần** | `push`, đệ quy vào các con, rồi `pull` | `push`, đệ quy, `merge` hai đáp án |

**Không cần `pull` sau một truy vấn thuần túy về mặt dữ liệu logic.** `push` đã giữ nguyên giá trị cha, còn hỏi con chỉ đọc kết quả. Nhưng chính `push` có thể làm **thay đổi trạng thái bộ nhớ** của cây; nếu nhiều luồng cùng dùng cây, đó vẫn là vấn đề đồng bộ.

### 4.5. Chứng minh `push` bảo toàn bất biến

Trước `push`, giả sử:

\[
tree[v]=apply(t,\ merge(S_L,S_R),\ k_L+k_R).
\]

Sau khi dùng `apply` để chuyển `t` xuống mỗi con, các tổng hợp mới của chúng là:

\[
S'_L=apply(t,S_L,k_L),
\quad S'_R=apply(t,S_R,k_R).
\]

Theo **luật phân phối**:

\[
merge(S'_L,S'_R)
=apply(t,merge(S_L,S_R),k_L+k_R)
=tree[v].
\]

Vì `tag[v]` sau đẩy là identity, công thức mới ở cha là:

\[
tree[v]=merge(tree[2v],tree[2v+1]).
\]

Như vậy `push` không làm thay đổi giá trị logic nào. Đây là **chứng minh tổng quát**, áp dụng cho mọi phép gộp/nhãn thỏa ba định luật, không chỉ phép cộng.

## 5. Truy vết các nhãn chồng lấn theo đúng thứ tự thời gian

Ta dùng mảng:

```text
Chỉ số:  0  1  2  3  4  5  6  7
A:       2  4  1  3  5  7  6  8
Tổng: 36
```

### 5.1. Lệnh thứ nhất: gán cả đoạn bằng 10

```text
range_set(0,8,10)
```

Nút gốc `[0,8)` được phủ hoàn toàn:

```text
                 [0,8): sum=80, tag=SET(10)
                      /              \
                [0,4):10           [4,8):26
                  tag=ID             tag=ID
```

**Mảng logic** là `[10,10,10,10,10,10,10,10]`, nhưng chưa cần sửa hai con.

### 5.2. Lệnh thứ hai: cộng 3 vào `[2,6)`

```text
range_add(2,6,3)
```

Đây là cập nhật giao một phần với gốc, nên đầu tiên **`push` nhãn `SET(10)` xuống cả hai con**:

```text
                           [0,8):sum=80,tag=ID
                          /                  \
               [0,4):sum=40               [4,8):sum=40
                tag=SET(10)                tag=SET(10)
```

Khi đi sâu tiếp, `[2,4)` và `[4,6)` nhận cập nhật `ADD(3)` **sau** `SET(10)`. Tại những nút phủ trọn này:

```text
Nhãn cũ: SET(10)
Nhãn mới: ADD(3)
Nhãn hợp thành: SET(13)

[2,4): hai phần tử 13 -> sum=26
[4,6): hai phần tử 13 -> sum=26
```

Sau khi `pull` các nút đã cập nhật:

```text
Mảng LOGIC: [10,10,13,13,13,13,10,10]
Tổng:      92
```

**Bài kiểm tra quan trọng:** nếu thuật toán hợp thành `SET(10)∘ADD(3)` thay vì `ADD(3)∘SET(10)`, nó sẽ làm các phần tử thành 10, không phải 13.

### 5.3. Lệnh thứ ba: gán 0 cho `[3,5)`

```text
range_set(3,5,0)
```

Các phần tử ở chỉ số 3 và 4 trở thành 0:

```text
Mảng LOGIC: [10,10,13,0,0,13,10,10]
Tổng:      66
```

Ở những lá bị gán 0, phép gán mới **ghi đè tác động cũ**; không được dùng “giá trị nhãn bằng 0” để suy đây là **không cập nhật**.

### 5.4. Lệnh thứ tư: nhân toàn mảng với −2

```text
range_mul(0,8,-2)
```

Đoạn phủ toàn gốc nên chỉ cần áp nhãn ở gốc:

```text
Trước: [10,10,13,0,0,13,10,10]
Sau:   [-20,-20,-26,0,0,-26,-20,-20]
Tổng:  -132
```

Các con có thể vẫn chứa những tổng trước lệnh nhân. Nhãn ở gốc hiện mang cập nhật **mới hơn** các nhãn cũ tại con. Khi một truy vấn nhỏ đi xuống, `push` phải hợp thành **`MUL(-2)∘old_child_tag`**.

### 5.5. Những gì không nên suy từ sơ đồ

Sơ đồ cho biết **tập giá trị logic** và ý nghĩa nhãn. Không có yêu cầu mọi nút phải chứa cùng dạng tag sau những chuỗi thao tác khác nhau: thuật toán có thể đẩy một số nhãn sớm hơn do truy vấn xen giữa. Hai biểu diễn nội bộ khác nhau vẫn có thể cho **cùng kết quả của mọi truy vấn**, miễn giữ các định luật và bất biến.

## 6. Nhãn affine: biểu diễn thống nhất cộng, gán, nhân

Đối với giá trị số, một phép biến đổi affine có dạng:

\[
f(x)=mx+b.
\]

Ta biểu diễn nhãn bằng cặp `(m,b)`:

| Thao tác | Nhãn `(m,b)` | Tác động lên một giá trị |
| --- | --- | --- |
| Không cập nhật | `(1,0)` | `x\mapsto x` |
| `ADD(d)` | `(1,d)` | `x\mapsto x+d` |
| `SET(s)` | `(0,s)` | `x\mapsto s` |
| `MUL(t)` | `(t,0)` | `x\mapsto tx` |

### 6.1. Áp nhãn vào tổng của đoạn

Nếu một nút quản lý `k` giá trị `x_1,\ldots,x_k` có tổng `S`, áp `f(x)=mx+b` đồng đều:

\[
\begin{aligned}
S'&=\sum_{i=1}^{k}(mx_i+b)\\
&=m\sum_{i=1}^{k}x_i+bk\\
&=\boxed{mS+bk}.
\end{aligned}
\]

Do đó:

```text
apply_affine_to_sum(tag=(m,b), sum=S, length=k):
    return m*S + b*k
```

Ví dụ tổng cũ `S=17` trên bốn phần tử, cập nhật `f(x)=3x-2`:

\[
S'=3\cdot17-2\cdot4=43.
\]

Nếu `m=0` và `b=0`, nhãn `(0,0)` chính là **SET(0)**: tổng thành 0. Nó **không phải** identity `(1,0)`.

### 6.2. Hợp thành hai nhãn có thứ tự

Giả sử nhãn **cũ**:

\[
g(x)=m_gx+b_g,
\]

nhãn **mới**:

\[
f(x)=m_fx+b_f.
\]

Vì `g` được áp trước và `f` sau:

\[
\begin{aligned}
(f\circ g)(x)
&=f(m_gx+b_g)\\
&=m_f(m_gx+b_g)+b_f\\
&=(m_fm_g)x+(m_fb_g+b_f).
\end{aligned}
\]

Vậy:

\[
\boxed{
compose(new=f,\ old=g)
=(m_fm_g,\;m_fb_g+b_f).
}
\]

**Trật tự tham số là quyết định thiết kế:** `compose(new,old)` có nghĩa *áp old trước, new sau*. Đổi tên hàm hoặc đảo tham số mà không cập nhật các vị trí gọi là nguyên nhân phổ biến của lỗi.

### 6.3. Bảng ví dụ hợp thành

| Nhãn cũ | Nhãn mới | Nhãn kết hợp `new∘old` |
| --- | --- | --- |
| `ADD(5)` | `ADD(3)` | `ADD(8)` |
| `SET(10)` | `ADD(3)` | `SET(13)` |
| `ADD(3)` | `SET(10)` | `SET(10)` |
| `SET(10)` | `SET(4)` | `SET(4)` |
| `ADD(2)` | `MUL(3)` | `(3,6)`, tức `3x+6` |
| `MUL(3)` | `ADD(2)` | `(3,2)`, tức `3x+2` |
| `SET(0)` | `ADD(-7)` | `SET(-7)` |
| `MUL(-1)` | `SET(0)` | `SET(0)` |

Hai phép `ADD` liên tiếp có thể đổi thứ tự mà vẫn được tổng delta. Nhưng **SET, MUL và ADD nói chung không giao hoán**.

### 6.4. Kiểm trực tiếp các định luật trên tổng

Với nhãn `f=(m_f,b_f)`, hai tổng `S_L,S_R` và độ dài `k_L,k_R`:

\[
\begin{aligned}
apply(f,S_L+S_R,k_L+k_R)
&=m_f(S_L+S_R)+b_f(k_L+k_R)\\
&=(m_fS_L+b_fk_L)+(m_fS_R+b_fk_R)\\
&=apply(f,S_L,k_L)+apply(f,S_R,k_R).
\end{aligned}
\]

Luật **phân phối** đã được chứng minh. Công thức `compose` ở mục 6.2 chứng minh luật **áp nhãn hợp thành**, còn `(1,0)` là identity vì:

\[
apply((1,0),S,k)=S.
\]

Vì vậy, phép **tổng** và các nhãn affine thỏa những hợp đồng cần thiết để áp dụng lazy propagation.

## 7. Thuật toán tổng quát với nhãn và giá trị tổng hợp

Một cây lazy tổng quát nhận các hàm:

```text
merge(left_aggregate, right_aggregate)
apply(tag, aggregate, segment_length)
compose(new_tag, old_tag)
aggregate_identity
tag_identity
```

Các thao tác công khai:

```text
range_apply(l, r, new_tag)
range_query(l, r)
```

### 7.1. Xây cây

```text
BUILD(v, L, R):
    if R-L == 1:
        tree[v] = representation_of(A[L])
        tag[v] = ID
        return
    M = (L+R)//2
    BUILD(2*v, L, M)
    BUILD(2*v+1, M, R)
    tree[v] = merge(tree[2*v], tree[2*v+1])
    tag[v] = ID
```

Với `n≥1`, cây phân hoạch có **`n` lá, `n-1` nút trong, tổng `2n-1` nút thật**. Nếu mỗi `merge` O(1), dựng cây O(n).

### 7.2. Cập nhật một đoạn

```text
UPDATE(v, L, R, ql, qr, new_tag):
    if qr <= L or R <= ql:      # Không giao
        return
    if ql <= L and R <= qr:     # Nút phủ trọn
        APPLY_HERE(v,L,R,new_tag)
        return

    PUSH(v,L,R)                 # Chuyển cập nhật cũ xuống con
    M = (L+R)//2
    UPDATE(2*v, L, M, ql, qr, new_tag)
    UPDATE(2*v+1, M, R, ql, qr, new_tag)
    PULL(v)                     # Gộp hai con đã đúng
```

Nếu `new_tag` là identity, có thể bỏ qua toàn bộ cập nhật **sau khi đã kiểm tra miền chỉ số**. Không nên đặt việc bỏ qua trước kiểm tra, vì `range_apply(-1,3,ID)` vẫn là đầu vào không hợp lệ.

### 7.3. Truy vấn một đoạn

```text
QUERY(v,L,R,ql,qr):
    if qr <= L or R <= ql:
        return aggregate_identity
    if ql <= L and R <= qr:
        return tree[v]

    PUSH(v,L,R)
    M = (L+R)//2
    left = QUERY(2*v,L,M,ql,qr)
    right = QUERY(2*v+1,M,R,ql,qr)
    return merge(left,right)
```

Với một phép `merge` không giao hoán, **phải gộp trái trước, phải sau**. Kết quả `QUERY` là **cùng giá trị tổng hợp logic** cho dù thuật toán có đẩy một số nhãn xuống khi truy vấn hay không.

### 7.4. Tại sao cập nhật và truy vấn đều O(log n)?

Một đoạn liên tiếp `[ql,qr)` có **tối đa hai ranh giới**. Ở một mức của cây phân hoạch:

- Nút không giao bị bỏ qua.
- Nút được phủ trọn dừng ngay, không mở rộng con.
- Chỉ các nút bị ranh giới truy vấn cắt qua mới tiếp tục mở rộng.

Do đó, số nút được mở rộng ở mỗi độ sâu bị chặn bởi một hằng số, còn chiều cao là O(log n). Nếu `merge/apply/compose` có chi phí O(1):

\[
\begin{aligned}
T_{\mathrm{build}}(n)&=O(n),\\
T_{\mathrm{range\_apply}}(n)&=O(\log(n+1)),\\
T_{\mathrm{range\_query}}(n)&=O(\log(n+1)).
\end{aligned}
\]

Mảng cây và mảng nhãn cùng tốn **O(n) bộ nhớ**, ngăn xếp đệ quy O(log n). Với `n=0`, ví dụ dưới cho phép chỉ đoạn `[0,0)` và trả identity.

## 8. Python: cây lazy tổng quát qua các phép toán được cung cấp

Để tránh lặp nhiều phiên bản của `apply/push/pull`, ta viết lớp `LazySegmentTree` không biết cụ thể nhãn là **ADD, SET, MUL** hay gì khác.

Đây là **một bài thực hành tự chứa**, không dùng thư viện ngoài Python tiêu chuẩn. Mã giả định:

- `merge` kết hợp và có `aggregate_identity` hai phía.
- `apply_tag(tag,aggregate,length)` tuân theo luật phân phối.
- `compose(new,old)` đúng thứ tự thời gian.
- `tag_identity` có phép so sánh `==` xác định đúng nhãn không làm gì.
- Giá trị tổng hợp và nhãn nên là các đối tượng **bất biến**; các hàm không được sửa dữ liệu đầu vào một cách ngầm.

### 8.1. Lớp `LazySegmentTree` hoàn chỉnh

```python
class LazySegmentTree:
    """Lazy segment tree tổng quát, truy vấn đoạn nửa mở [l,r).

    merge(a,b)        : gộp thống kê đoạn trái, rồi đoạn phải
    aggregate_identity: identity hai phía của merge
    apply_tag(t,a,k)  : áp t lên aggregate a của đoạn dài k
    compose(new,old)  : nhãn tương đương làm old trước new
    tag_identity      : nhãn không thay đổi dữ liệu

    Người gọi chịu trách nhiệm bảo đảm các định luật đại số.
    """

    def __init__(
        self,
        leaves,
        merge,
        aggregate_identity,
        apply_tag,
        compose,
        tag_identity,
    ):
        if not all(callable(fn) for fn in (merge, apply_tag, compose)):
            raise TypeError("merge, apply_tag, compose phải là hàm")

        data = list(leaves)
        self.n = len(data)
        self.merge = merge
        self.aggregate_identity = aggregate_identity
        self.apply_tag = apply_tag
        self.compose = compose
        self.tag_identity = tag_identity

        # Đánh số nút từ 1; hai con của v là 2*v và 2*v+1.
        size = 4 * self.n + 5
        self.tree = (
            [aggregate_identity] * size if self.n else []
        )
        self.pending = (
            [tag_identity] * size if self.n else []
        )
        if self.n:
            self._build(1, 0, self.n, data)

    def _build(self, v, left, right, data):
        if right - left == 1:
            self.tree[v] = data[left]
            return

        mid = (left + right) // 2
        self._build(v * 2, left, mid, data)
        self._build(v * 2 + 1, mid, right, data)
        self._pull(v)

    def _check_range(self, left, right):
        # Không nhận bool: Python xem True == 1, False == 0.
        if type(left) is not int or type(right) is not int:
            raise TypeError("Ranh giới phải thuộc kiểu int")
        if not (0 <= left <= right <= self.n):
            raise IndexError("Cần 0 <= left <= right <= n")

    def _apply_here(self, v, left, right, new_tag):
        length = right - left
        self.tree[v] = self.apply_tag(
            new_tag, self.tree[v], length
        )
        # NEW nằm ngoài OLD: apply(new, apply(old, ...)).
        self.pending[v] = self.compose(
            new_tag, self.pending[v]
        )

    def _push(self, v, left, right):
        tag = self.pending[v]
        if tag == self.tag_identity or right - left == 1:
            return

        mid = (left + right) // 2
        self._apply_here(v * 2, left, mid, tag)
        self._apply_here(v * 2 + 1, mid, right, tag)
        self.pending[v] = self.tag_identity

    def _pull(self, v):
        assert self.pending[v] == self.tag_identity
        self.tree[v] = self.merge(
            self.tree[v * 2], self.tree[v * 2 + 1]
        )

    def range_apply(self, left, right, new_tag):
        self._check_range(left, right)
        if left == right or new_tag == self.tag_identity:
            return
        self._update(1, 0, self.n, left, right, new_tag)

    def _update(self, v, seg_l, seg_r, ql, qr, new_tag):
        if qr <= seg_l or seg_r <= ql:
            return

        if ql <= seg_l and seg_r <= qr:
            self._apply_here(v, seg_l, seg_r, new_tag)
            return

        self._push(v, seg_l, seg_r)
        mid = (seg_l + seg_r) // 2
        self._update(v * 2, seg_l, mid, ql, qr, new_tag)
        self._update(v * 2 + 1, mid, seg_r, ql, qr, new_tag)
        self._pull(v)

    def range_query(self, left, right):
        self._check_range(left, right)
        if left == right:
            return self.aggregate_identity
        return self._query(1, 0, self.n, left, right)

    def _query(self, v, seg_l, seg_r, ql, qr):
        if qr <= seg_l or seg_r <= ql:
            return self.aggregate_identity
        if ql <= seg_l and seg_r <= qr:
            return self.tree[v]

        self._push(v, seg_l, seg_r)
        mid = (seg_l + seg_r) // 2
        a = self._query(v * 2, seg_l, mid, ql, qr)
        b = self._query(v * 2 + 1, mid, seg_r, ql, qr)
        return self.merge(a, b)

    def to_leaves(self):
        """Vật chất hóa các GIÁ TRỊ TỔNG HỢP CỦA LÁ: O(n).

        Các nhãn đang đợi có thể được push trong quá trình duyệt.
        """
        result = [None] * self.n
        if self.n == 0:
            return result

        def collect(v, left, right):
            if right - left == 1:
                result[left] = self.tree[v]
                return

            self._push(v, left, right)
            mid = (left + right) // 2
            collect(v * 2, left, mid)
            collect(v * 2 + 1, mid, right)

        collect(1, 0, self.n)
        return result

    def validate_normalized(self):
        """Kiểm thử O(n): đẩy nhãn rồi so tổng hợp cha-con.

        Hàm này CÓ thể thay đổi biểu diễn tree/pending
        nhưng KHÔNG thay đổi mảng logic.
        """
        if self.n == 0:
            assert self.tree == []
            assert self.pending == []
            return True

        def check(v, left, right):
            if right - left == 1:
                return self.tree[v]

            self._push(v, left, right)
            assert self.pending[v] == self.tag_identity
            mid = (left + right) // 2
            a = check(v * 2, left, mid)
            b = check(v * 2 + 1, mid, right)
            expected = self.merge(a, b)
            assert self.tree[v] == expected, (
                f"Nút {v} sai trên [{left},{right})"
            )
            return expected

        check(1, 0, self.n)
        return True
```

### 8.2. Hợp đồng về lá và identity

Khi khởi tạo, `leaves` đã phải chứa **giá trị tổng hợp của một phần tử**, không nhất thiết là giá trị thô. Với phép tổng, biểu diễn lá là số nguyên. Với tuple `(sum,min,max)`, mỗi lá từ `x` phải trở thành `(x,x,x)`.

`to_leaves()` trả **giá trị tổng hợp ở các lá**, nên với mô hình tuple nó trả **tuple**, không tự chuyển ngược thành các số thô.

Ví dụ giữ `pending` ở lá là hợp lệ, vì lá không có con để nhận khoản nợ. `tree` ở lá đã chứa tác động của nhãn; thuật toán không cố `push` xuống dưới lá.

### 8.3. Vì sao hàm kiểm tra không được tính vào thời gian thao tác lõi?

`validate_normalized()` duyệt **mọi nút thật**, O(n). `to_leaves()` cũng cần O(n) để xuất đủ `n` phần tử. Hai hàm này phục vụ học tập và đối chiếu; nếu gọi sau mỗi thao tác trong benchmark, bạn đang đo thêm chi phí O(n) và không còn đo riêng **range update/query O(log n)**.

### 8.4. Một chi tiết của Python: giá trị bất biến và alias

Phép `[aggregate_identity] * size` hoặc `[tag_identity] * size` tạo nhiều ô ban đầu cùng tham chiếu đến identity. Điều này **an toàn nếu identity và phép toán là bất biến/thuần**, như số nguyên, tuple số nguyên và dataclass `frozen=True`.

Nếu identity là một **list/dict khả biến** rồi một hàm cập nhật sửa **trực tiếp** nó, nhiều nút có thể bị ảnh hưởng ngoài ý muốn. Trong trường hợp đó, hãy thiết kế lại cách tạo identity theo từng ô và đảm bảo `merge/apply/compose` không sửa đối số dùng chung.

## 9. Chuyên biệt hóa Python cho tổng đoạn và nhãn affine

Mã dưới dùng lại **nguyên lớp `LazySegmentTree` ở mục 8**. Nhãn là một đối tượng bất biến gồm `mul` và `add`; nhãn đơn vị là `(1,0)`.

### 9.1. Biểu diễn nhãn rõ ràng

```python
from dataclasses import dataclass
from operator import add


@dataclass(frozen=True)
class AffineTag:
    mul: int = 1
    add: int = 0


IDENTITY_TAG = AffineTag(1, 0)


def apply_affine_sum(tag, total, length):
    # f(x) = m*x+b, tổng mới m*total+b*length.
    return tag.mul * total + tag.add * length


def compose_affine(new_tag, old_tag):
    """Hợp thành new ∘ old: nhãn CŨ trước, MỚI sau."""
    return AffineTag(
        mul=new_tag.mul * old_tag.mul,
        add=new_tag.mul * old_tag.add + new_tag.add,
    )


def make_sum_tree(values):
    data = list(values)
    if any(type(x) is not int for x in data):
        raise TypeError("Ví dụ yêu cầu phần tử kiểu int")
    return LazySegmentTree(
        leaves=data,
        merge=add,
        aggregate_identity=0,
        apply_tag=apply_affine_sum,
        compose=compose_affine,
        tag_identity=IDENTITY_TAG,
    )
```

Tạo cây và gọi cập nhật:

```python
tree = make_sum_tree([2, 4, 1, 3, 5, 7, 6, 8])

def range_add(tree, left, right, delta):
    if type(delta) is not int:
        raise TypeError("delta phải là int")
    tree.range_apply(left, right, AffineTag(1, delta))

def range_set(tree, left, right, value):
    if type(value) is not int:
        raise TypeError("value phải là int")
    tree.range_apply(left, right, AffineTag(0, value))

def range_mul(tree, left, right, factor):
    if type(factor) is not int:
        raise TypeError("factor phải là int")
    tree.range_apply(left, right, AffineTag(factor, 0))
```

Những hàm trợ giúp `range_add/range_set/range_mul` chỉ chuyển ý nghĩa nghiệp vụ sang nhãn. **Toàn bộ cơ chế đệ quy, `apply/push/pull` vẫn dùng chung**.

### 9.2. Kiểm lại ví dụ `SET → ADD → SET → MUL`

```python
assert tree.range_query(0, 8) == 36

# SET(10) cho toàn đoạn.
range_set(tree, 0, 8, 10)
assert tree.range_query(0, 8) == 80
assert tree.pending[1] == AffineTag(0, 10)
assert tree.tree[2] == 10
assert tree.tree[3] == 26

# ADD(3) cho [2,6): cha phải push trước khi đi sâu.
range_add(tree, 2, 6, 3)
assert tree.to_leaves() == [10, 10, 13, 13, 13, 13, 10, 10]
assert tree.range_query(0, 8) == 92
assert tree.range_query(2, 6) == 52

# SET(0) là cập nhật thật.
range_set(tree, 3, 5, 0)
assert tree.to_leaves() == [10, 10, 13, 0, 0, 13, 10, 10]
assert tree.range_query(0, 8) == 66

# MUL(-2) toàn mảng.
range_mul(tree, 0, 8, -2)
assert tree.range_query(0, 8) == -132
assert tree.to_leaves() == [-20, -20, -26, 0, 0, -26, -20, -20]
assert tree.range_query(2, 6) == -52
assert tree.validate_normalized()
```

Tất cả `assert` là **kết quả kỳ vọng để người học tự chạy**, không phải báo cáo đã thực thi thử nghiệm trong quá trình biên soạn.

### 9.3. Kiểm riêng thứ tự nhãn trên một điểm

```python
tree_a = make_sum_tree([4])
range_add(tree_a, 0, 1, 3)
range_set(tree_a, 0, 1, 10)
assert tree_a.range_query(0, 1) == 10

tree_b = make_sum_tree([4])
range_set(tree_b, 0, 1, 10)
range_add(tree_b, 0, 1, 3)
assert tree_b.range_query(0, 1) == 13

# SET(0) không giống identity.
range_set(tree_b, 0, 1, 0)
assert tree_b.range_query(0, 1) == 0
assert tree_b.pending[1] == AffineTag(0, 0)
assert tree_b.pending[1] != IDENTITY_TAG

range_add(tree_b, 0, 1, -7)
assert tree_b.range_query(0, 1) == -7
assert tree_b.pending[1] == AffineTag(0, -7)
```

### 9.4. Kiểm trên cây nhiều tầng và nhãn chồng lấn

```python
tree = make_sum_tree([1, 2, 3, 4, 5])

range_add(tree, 0, 5, 2)    # [3, 4, 5, 6, 7]
range_set(tree, 1, 4, 10)   # [3,10,10,10,7]
range_add(tree, 2, 5, -3)   # [3,10,7,7,4]
range_mul(tree, 1, 5, -2)   # [3,-20,-14,-14,-8]

assert tree.to_leaves() == [3, -20, -14, -14, -8]
assert tree.range_query(0, 5) == -53
assert tree.range_query(1, 4) == -48
assert tree.range_query(3, 3) == 0
assert tree.validate_normalized()
```

Một lỗi `compose` có thể không lộ ra khi **chỉ hỏi cả mảng**, vì `apply` vẫn cập nhật tổng ở gốc đúng. Lỗi thường xuất hiện khi **nhãn cha và nhãn con chồng lên nhau** rồi một truy vấn nhỏ bắt buộc `push` chúng xuống.

## 10. Kiểm chứng các định luật bằng phép thử độc lập

Ngoài kiểm tra truy vấn/cập nhật đầu cuối, nên kiểm tra **trực tiếp hợp đồng đại số**. Nếu `compose` đã sai thì mọi thuật toán cây phía trên đều có nguy cơ sai dù logic chia đoạn đúng.

### 10.1. Identity và hợp thành nhãn

```python
tags = [
    AffineTag(1, 0),   # ID
    AffineTag(1, 5),   # ADD 5
    AffineTag(0, 2),   # SET 2
    AffineTag(0, 0),   # SET 0
    AffineTag(-2, 0),  # MUL -2
    AffineTag(3, -4),  # x -> 3*x-4
]

for tag in tags:
    assert compose_affine(IDENTITY_TAG, tag) == tag
    assert compose_affine(tag, IDENTITY_TAG) == tag
    for total in [-9, 0, 12]:
        for length in [1, 2, 7]:
            assert (
                apply_affine_sum(IDENTITY_TAG, total, length)
                == total
            )

for old in tags:
    for new in tags:
        composed = compose_affine(new, old)
        for total in [-9, 0, 12]:
            for length in [1, 2, 7]:
                expected = apply_affine_sum(
                    new, apply_affine_sum(old, total, length),
                    length,
                )
                assert (
                    apply_affine_sum(composed, total, length)
                    == expected
                )
```

### 10.2. Phân phối qua hai đoạn và tính kết hợp

```python
for tag in tags:
    for left_sum, left_len in [(-5, 1), (7, 2), (0, 4)]:
        for right_sum, right_len in [(6, 1), (-3, 3)]:
            whole = apply_affine_sum(
                tag,
                left_sum + right_sum,
                left_len + right_len,
            )
            pieces = (
                apply_affine_sum(tag, left_sum, left_len)
                + apply_affine_sum(tag, right_sum, right_len)
            )
            assert whole == pieces

for first in tags:
    for second in tags:
        for third in tags:
            # third đến sau second, second đến sau first.
            left_assoc = compose_affine(
                third, compose_affine(second, first)
            )
            right_assoc = compose_affine(
                compose_affine(third, second), first
            )
            assert left_assoc == right_assoc
```

Ở đây `left_sum` và `left_len` được chọn làm **đầu vào kiểm tra luật**, không nhất thiết xuất phát từ một mảng cụ thể; tính đúng của công thức affine vẫn phải có với mọi tổng và độ dài hợp lệ.

### 10.3. Vì sao phép thử đại số chưa thay thế được kiểm thử cấu trúc?

Một hàm `compose` đúng không đảm bảo `_push` luôn được gọi **đúng lúc**, `_pull` dùng đúng hai con, hoặc các đoạn `[l,r)` được chia đúng chỉ số. Cần cả hai nhóm kiểm thử:

1. **Kiểm thử luật đại số:** phát hiện sai quy tắc `merge/apply/compose`.
2. **Kiểm thử thao tác toàn cây:** phát hiện sai liên kết giữa **nhãn, vị trí nút, chiều dài đoạn và thứ tự truy vấn**.

Một lỗi điển hình là `apply_tag` đã đúng với độ dài 4, nhưng `_push` truyền nhầm **độ dài nút cha** cho cả hai con. Kiểm thử nhãn đơn lẻ sẽ không bắt được lỗi tổ chức cây đó.

## 11. Mở rộng tổng hợp thành `(sum, min, max)`

Một bài toán thực tế có thể yêu cầu **cả tổng, giá trị nhỏ nhất và giá trị lớn nhất** của đoạn, trong khi vẫn cập nhật bằng nhãn affine.

Thay vì ba cây rời nhau, ta có thể lưu trong mỗi nút:

\[
S(I)=(sum(I),\ min(I),\ max(I)).
\]

### 11.1. Phép gộp của hai đoạn liền nhau

Với `a=(s_a,mn_a,mx_a)` và `b=(s_b,mn_b,mx_b)`:

\[
merge(a,b)=
(s_a+s_b,\ \min(mn_a,mn_b),\ \max(mx_a,mx_b)).
\]

Identity cho đoạn rỗng:

\[
e=(0,+\infty,-\infty).
\]

Một phần tử `x` trở thành lá:

\[
leaf(x)=(x,x,x).
\]

### 11.2. Nhãn affine tác động lên cả ba giá trị

Với `f(x)=mx+b`, độ dài đoạn `k>0`:

- Tổng: `sum'=m·sum+b·k`.
- Nếu `m≥0`, thứ tự các phần tử không đổi, nên:
  `min'=m·min+b` và `max'=m·max+b`.
- Nếu `m<0`, thứ tự đảo, nên:
  `min'=m·max+b` và `max'=m·min+b`.

Trường hợp `m=0` là phép gán, cho `min'=max'=b`, hoàn toàn phù hợp với nhánh `m≥0`.

Ví dụ:

```text
Đoạn: [-3, 2, 5]
sum = 4, min = -3, max = 5

MUL(-2):
giá trị mới: [6, -4, -10]
sum = -8, min = -10, max = 6
```

Nếu chỉ nhân `min=-3` với −2 để lấy min mới là 6, kết quả sai vì −10 mới là giá trị nhỏ nhất.

### 11.3. Python: sử dụng lại đúng lớp lazy tổng quát

```python
from math import inf


STATS_ID = (0, inf, -inf)


def merge_stats(a, b):
    return (
        a[0] + b[0],
        min(a[1], b[1]),
        max(a[2], b[2]),
    )


def apply_affine_stats(tag, aggregate, length):
    # Giữ nguyên identity cho đoạn rỗng.
    if length == 0:
        return STATS_ID

    total, minimum, maximum = aggregate
    new_sum = tag.mul * total + tag.add * length

    if tag.mul >= 0:
        new_min = tag.mul * minimum + tag.add
        new_max = tag.mul * maximum + tag.add
    else:
        new_min = tag.mul * maximum + tag.add
        new_max = tag.mul * minimum + tag.add

    return (new_sum, new_min, new_max)


def make_stats_tree(values):
    data = list(values)
    if any(type(x) is not int for x in data):
        raise TypeError("Ví dụ yêu cầu phần tử int")
    return LazySegmentTree(
        leaves=[(x, x, x) for x in data],
        merge=merge_stats,
        aggregate_identity=STATS_ID,
        apply_tag=apply_affine_stats,
        compose=compose_affine,
        tag_identity=IDENTITY_TAG,
    )
```

### 11.4. Kiểm thử đúng các trường hợp đổi dấu

```python
stats = make_stats_tree([3, -2, 5, 1])
assert stats.range_query(0, 4) == (7, -2, 5)
assert stats.range_query(1, 3) == (3, -2, 5)

range_add(stats, 1, 4, 2)
# [3,0,7,3]: sum=13, min=0, max=7.
assert stats.range_query(0, 4) == (13, 0, 7)

range_mul(stats, 0, 4, -2)
# [-6,0,-14,-6]: sum=-26, min=-14, max=0.
assert stats.range_query(0, 4) == (-26, -14, 0)
assert stats.range_query(1, 3) == (-14, -14, 0)

range_set(stats, 2, 4, 0)
# [-6,0,0,0]: sum=-6, min=-6, max=0.
assert stats.range_query(0, 4) == (-6, -6, 0)
assert stats.range_query(2, 4) == (0, 0, 0)
assert stats.range_query(3, 3) == STATS_ID
assert stats.to_leaves() == [
    (-6, -6, -6),
    (0, 0, 0),
    (0, 0, 0),
    (0, 0, 0),
]
assert stats.validate_normalized()
```

**Giải thích:** Lớp `LazySegmentTree` không thay đổi dòng nào. Ta chỉ cung cấp **monoid tổng hợp khác** và **hàm apply tương thích**. Đây là lợi ích của việc tách **bất biến tổng hợp** khỏi **cơ chế phân đoạn**.

### 11.5. Khi nào tổng hợp nhiều trường có lợi?

Nếu một ứng dụng cần trả `(sum,min,max)` trên **cùng đoạn** và chịu **cùng cập nhật**, lưu tuple có thể giúp mỗi thao tác đi qua cây một lần. Nhưng:

- Mỗi nút chứa nhiều metadata hơn.
- Phép `merge/apply` tốn nhiều việc hơn một phép cộng đơn.
- Nếu ba loại thống kê có **những quy tắc cập nhật khác nhau**, cần bảo đảm cùng một tag hợp lệ cho cả ba.
- Nếu chỉ cần sum, việc lưu min/max sẽ là chi phí thừa.

Do đó, dùng **đúng metadata cần thiết** chứ không mặc định thêm mọi thống kê vào mỗi nút.

## 12. Phản ví dụ: metadata không đủ thì không thể “tự thêm lazy”

Không phải mọi phép cập nhật có thể tác động lên một giá trị tổng hợp ở nút trong O(1).

### 12.1. GCD sau cộng đều cả đoạn

Hai đoạn:

```text
A = [2, 4]     gcd(A)=2
B = [2, 6]     gcd(B)=2
```

Cả hai dài hai phần tử và có **cùng gcd ban đầu**. Cộng +2 cho mọi phần tử:

```text
A' = [4, 6]    gcd(A')=2
B' = [4, 8]    gcd(B')=4
```

Nếu có một hàm:

```text
apply_add_to_gcd(old_gcd, length, delta)
```

thì đầu vào của hai trường hợp đều là `(2,2,2)` nhưng phải cho **hai kết quả khác nhau** (2 và 4) — điều bất khả thi. Vì vậy, chỉ lưu **GCD** ở nút không đủ để hỗ trợ cập nhật cộng đoạn bằng một nhãn O(1) theo cách này.

Có thể giải những bài GCD + cập nhật bằng **thông tin khác**, chẳng hạn khai thác mảng hiệu và một cấu trúc bổ trợ, nhưng phải chứng minh một bất biến mới. Không thể chỉ thay `merge=sum` bằng `merge=gcd` trong lớp ví dụ rồi giữ nguyên `apply_affine_sum`.

### 12.2. Giá trị trung vị, phần tử xuất hiện nhiều nhất và sắp xếp

Nếu nút chỉ lưu `sum`, nó không biết được **trung vị**, **phân phối khóa** hay **phần tử phổ biến nhất** trong đoạn. Ngay cả khi không cập nhật, không thể lấy các thống kê đó từ hai số tổng một cách tổng quát.

Muốn hỗ trợ truy vấn khác, phải lưu **metadata đủ thông tin để gộp** và bảo đảm có phép tác động nhãn tương thích; đôi khi việc đó cần cấu trúc lớn hơn O(1) ở mỗi nút hoặc một thiết kế hoàn toàn khác.

### 12.3. Ghép chuỗi và cập nhật từng ký tự

Phép nối chuỗi có **tính kết hợp và identity là chuỗi rỗng**, nhưng **không giao hoán**. Một cây đoạn lưu toàn bộ chuỗi ghép tại nút có thể đòi **O(độ dài chuỗi)** để xây giá trị mới do sao chép ký tự. Vì vậy dù chỉ đi qua O(log n) nút, thời gian CPU không nhất thiết O(log n).

Thêm một nhãn “thay mọi ký tự bằng chuỗi `s`” có thể khiến giá trị tổng hợp ở nút thành chuỗi `s` lặp `length` lần. Việc tạo kết quả dài không thể xem là O(1) chỉ vì thao tác được ghi trong một dòng mã.

### 12.4. Nhãn tùy ý không tự có phép hợp thành dạng gọn

Các cập nhật có điều kiện phụ thuộc từng phần tử, ví dụ:

```text
nếu A[i] chẵn thì A[i] += 3
nếu A[i] lẻ  thì A[i] *= 2
```

có thể không áp được lên **chỉ một tổng S** mà không biết phân bố các giá trị. Cần chứng minh tồn tại phép `apply` cho metadata đang lưu trước khi triển khai cập nhật lười.

## 13. Kiểm thử chéo bằng mảng tham chiếu

Một bộ `assert` cố định có thể bỏ sót lỗi chỉ xuất hiện khi các nhãn chồng lên nhau theo một thứ tự hiếm gặp. Cách kiểm chứng tốt là so sánh với **mảng thường** dùng làm oracle, trên dữ liệu nhỏ.

### 13.1. Sinh chuỗi thao tác tái lập được

```python
from random import Random

rng = Random(2026)

for n in [0, 1, 2, 3, 5, 8, 13, 31]:
    reference = [rng.randint(-7, 7) for _ in range(n)]
    tree = make_sum_tree(reference)

    for step in range(60):
        left = rng.randrange(n + 1)
        right = rng.randrange(left, n + 1)
        kind = rng.choice(("ADD", "SET", "MUL"))

        if kind == "ADD":
            delta = rng.randint(-5, 5)
            range_add(tree, left, right, delta)
            for i in range(left, right):
                reference[i] += delta

        elif kind == "SET":
            value = rng.randint(-5, 5)
            range_set(tree, left, right, value)
            for i in range(left, right):
                reference[i] = value

        else:
            factor = rng.choice((-2, -1, 0, 1, 2))
            range_mul(tree, left, right, factor)
            for i in range(left, right):
                reference[i] *= factor

        # Kiểm mọi đoạn, kể cả đoạn rỗng.
        for l in range(n + 1):
            for r in range(l, n + 1):
                assert tree.range_query(l, r) == sum(reference[l:r])

    assert tree.to_leaves() == reference
    assert tree.validate_normalized()
```

**Đây là mã kiểm thử để người học tự chạy**, không phải kết quả đã thực thi trong bước viết bài. Dùng seed cố định giúp tái tạo chính xác chuỗi thao tác nếu phát hiện sai.

### 13.2. Oracle cho `(sum,min,max)`

```python
from math import inf

def slow_stats(values):
    if not values:
        return (0, inf, -inf)
    return (sum(values), min(values), max(values))

rng = Random(55)
for n in [0, 1, 3, 7]:
    reference = [rng.randint(-10, 10) for _ in range(n)]
    tree = make_stats_tree(reference)

    for _ in range(30):
        l = rng.randrange(n + 1)
        r = rng.randrange(l, n + 1)
        kind = rng.choice(("add", "set", "mul"))
        value = rng.randint(-3, 3)

        if kind == "add":
            range_add(tree, l, r, value)
            for i in range(l, r):
                reference[i] += value
        elif kind == "set":
            range_set(tree, l, r, value)
            for i in range(l, r):
                reference[i] = value
        else:
            range_mul(tree, l, r, value)
            for i in range(l, r):
                reference[i] *= value

        for left in range(n + 1):
            for right in range(left, n + 1):
                expected = slow_stats(reference[left:right])
                assert tree.range_query(left, right) == expected

    assert tree.to_leaves() == [(x, x, x) for x in reference]
    assert tree.validate_normalized()
```

### 13.3. Những trường hợp không hợp lệ

```python
tree = make_sum_tree([2, 4, 6])

for bad in [(-1, 1), (2, 4), (3, 2)]:
    left, right = bad
    try:
        tree.range_query(left, right)
    except IndexError:
        pass
    else:
        raise AssertionError("Phải từ chối đoạn ngoài miền")

for invalid in [(True, 2), (0, False), (1.5, 2)]:
    try:
        tree.range_apply(invalid[0], invalid[1], IDENTITY_TAG)
    except TypeError:
        pass
    else:
        raise AssertionError("Chỉ số không được là bool/float")

empty = make_sum_tree([])
assert empty.range_query(0, 0) == 0
range_add(empty, 0, 0, 3)
range_set(empty, 0, 0, 0)
assert empty.to_leaves() == []
assert empty.validate_normalized()
```

Nếu phần tử hoặc nhãn dùng kiểu dữ liệu khác `int`, hãy định nghĩa rõ cách kiểm tra kiểu theo yêu cầu hệ thống. Không nên âm thầm chấp nhận mọi đối tượng bất kỳ vì `apply` có thể có nghĩa khác nhau tùy kiểu.

## 14. Chọn cách biểu diễn nhãn cho yêu cầu thực tế

Nhãn affine là một cách gọn để đồng thời xử lý **ADD, SET và MUL** trên dữ liệu số. Tuy vậy, không phải mọi hệ thống đều cần đủ cả ba phép biến đổi.

### 14.1. Chỉ có cộng đoạn

Nếu bài toán chỉ có `ADD(d)` và `SUM`:

```text
tag = delta
tag_identity = 0
compose(new_delta, old_delta) = old_delta + new_delta
apply(delta, S, len) = S + delta*len
```

Ở đây hai nhãn cộng **giao hoán**, nhưng thuật toán tổng quát vẫn nên giữ quy tắc `new∘old` để không gây nhầm lẫn khi mở rộng.

### 14.2. Chỉ có gán đoạn

Nếu chỉ có `SET(s)`:

```text
tag = None hoặc SET(s)
tag_identity = None

compose(SET(new_s), SET(old_s)) = SET(new_s)
apply(SET(s), S, len) = s*len
```

Không nên dùng số `0` làm ký hiệu “không có lệnh gán” vì **`SET(0)` là một cập nhật hợp lệ**.

### 14.3. Cộng và gán, không có nhân

Có thể dùng:

```text
pending_set = None hoặc một số s
pending_add = một số d
```

Một nhãn biểu diễn:

```text
nếu pending_set is None: x -> x + d
nếu pending_set = s:     x -> s + d
```

Khi đến `SET(t)` mới, phần gán mới **xóa** mọi khoản cũ: `pending_set=t, pending_add=0`. Khi đến `ADD(d2)`, tăng `pending_add+=d2`.

Biểu diễn này có thể dễ giải thích trong code ứng dụng nhưng thường cần thêm nhánh điều kiện. Nhãn affine `(m,b)` loại bỏ phần lớn nhánh vì `SET(t)` chính là `(0,t)`.

### 14.4. Chỉ cần tổng cập nhật khi dữ liệu tĩnh?

Nếu không có truy vấn xen kẽ, **mảng chênh lệch (difference array)** có thể đơn giản hơn:

```text
range_add(l,r,d):
    diff[l] += d
    diff[r] -= d
```

Sau tất cả cập nhật, lấy tổng tiền tố của `diff` để tính giá trị ở từng điểm. Mỗi cập nhật O(1), khôi phục cuối O(n). Nhưng không thể mặc nhiên dùng kết quả này để trả **range sum online O(log n)** khi dữ liệu đang liên tục thay đổi.

### 14.5. Một hoặc hai Fenwick tree

Fenwick tree chuẩn hỗ trợ cộng điểm và tổng tiền tố. Với phép biến đổi phù hợp, **hai Fenwick tree** cũng hỗ trợ **range add và range sum** trong O(log n). Nó đáng cân nhắc khi bài toán chỉ cần phép cộng.

Lazy segment tree có lợi thế về tính khái quát khi cần **gán đoạn, metadata tổng hợp, cập nhật theo phép biến đổi đặc thù**, nhưng không tự nhanh hơn hoặc dùng ít bộ nhớ hơn Fenwick trong mọi ứng dụng.

### 14.6. Những nhãn phức tạp hơn affine

Cập nhật dạng `chmin` hoặc `chmax` (giới hạn trên/dưới mỗi phần tử), ví dụ:

```text
for i in [l,r):
    A[i] = min(A[i], cap)
```

không thể nói “đưa `cap` vào một cặp affine là xong”. Nếu nút chỉ lưu tổng, tổng sau `chmin` còn phụ thuộc **bao nhiêu giá trị vượt cap và chúng lớn bao nhiêu**. Các thuật toán nâng cao như **segment tree beats** lưu metadata bổ sung và dùng phân tích khác.

**Nguyên tắc:** luôn thử chứng minh luật `apply` tương thích với `merge` trước khi thiết kế phần cài đặt lazy.

## 15. Ứng dụng: thống kê kế hoạch học theo ngày

Giả sử nền tảng học quản lý số phút học dự kiến theo bảy ngày:

```text
Ngày:       0   1   2   3   4   5   6
Số phút:   30  40  20  50  35  45  25
Tổng tuần: 245
```

Các thao tác nghiệp vụ:

1. **Thưởng 10 phút mỗi ngày** ở `[1,6)` → `ADD(10)`.
2. **Hủy kế hoạch** trong `[3,5)` → `SET(0)`.
3. **Giảm một nửa kế hoạch** ở `[0,3)` → nếu dùng số nguyên, phải định nghĩa rõ quy tắc làm tròn; **phép chia nguyên có làm tròn không còn là affine trên số nguyên theo nghĩa tổng đơn giản**.

Để tránh mơ hồ ở thao tác thứ ba, ta có thể thay bằng **nhân 2** số phút ở `[0,3)`, một biến đổi affine chính xác trên số nguyên.

### 15.1. Truy vết bằng nhãn affine

```text
Ban đầu:
[30,40,20,50,35,45,25]
Tổng = 245

ADD(10) trên [1,6):
[30,50,30,60,45,55,25]
Tổng = 295

SET(0) trên [3,5):
[30,50,30,0,0,55,25]
Tổng = 190

MUL(2) trên [0,3):
[60,100,60,0,0,55,25]
Tổng = 300
```

```python
weekly = make_stats_tree([30, 40, 20, 50, 35, 45, 25])

range_add(weekly, 1, 6, 10)
assert weekly.range_query(0, 7) == (295, 25, 60)

range_set(weekly, 3, 5, 0)
assert weekly.range_query(0, 7) == (190, 0, 55)

range_mul(weekly, 0, 3, 2)
assert weekly.to_leaves() == [
    (60, 60, 60),
    (100, 100, 100),
    (60, 60, 60),
    (0, 0, 0),
    (0, 0, 0),
    (55, 55, 55),
    (25, 25, 25),
]
assert weekly.range_query(0, 7) == (300, 0, 100)
assert weekly.range_query(1, 4) == (160, 0, 100)
assert weekly.validate_normalized()
```

Một cây duy nhất có thể trả cả **tổng, nhỏ nhất và lớn nhất** trong O(log n) theo hợp đồng, vì mỗi nút lưu một tuple phù hợp với cùng nhãn cập nhật.

### 15.2. Giới hạn mô hình số học

Nếu đơn vị là **phút nguyên**, một thao tác “giảm 20% rồi làm tròn lên mỗi ngày” không thể gộp ngây thơ bằng `m=0.8`, bởi làm tròn **riêng từng phần tử** khác với làm tròn **sau khi nhân tổng**:

```text
Giảm 50% rồi làm tròn lên cho từng ngày [1,1]:
ceil(1/2) + ceil(1/2) = 1 + 1 = 2

Nhưng làm trên tổng:
ceil((1+1)/2) = ceil(1) = 1
```

Muốn dùng lazy đúng, cần định nghĩa một thống kê đủ mạnh hoặc thay đổi hợp đồng cập nhật. Không được coi phép làm tròn từng giá trị là một phép affine chính xác của **tổng**.

### 15.3. Chuyển khoảng ngày thành khoảng chỉ số

Segment tree làm việc trên **vị trí 0..n−1**, không tự hiểu ngày lịch hay mã bài học. Nếu dữ liệu bỏ qua ngày không có bản ghi, cần quyết định:

- Mỗi ngày lịch đều có một ô (kể cả ngày có giá trị 0), hay chỉ giữ ngày có bản ghi?
- `[l,r)` tính ngày đầu và bỏ ngày cuối theo đúng quy ước không?
- Khi chèn thêm ngày vào giữa, có cần cập nhật ánh xạ và **xây lại cây** không?
- Nếu miền ngày lớn nhưng thưa, có nên dùng cây đoạn động hoặc nén tọa độ không?

**Đúng về mặt cấu trúc dữ liệu** chưa đủ nếu ánh xạ từ nghiệp vụ sang chỉ số bị sai.

### 15.4. Nhiều chỉ mục phải nhất quán

Ứng dụng có thể đồng thời lưu một bảng băm `lesson_id→record`, một mảng thời lượng theo ngày và một cây tổng hợp trên mảng ấy. Khi thay đổi bản ghi, mọi chỉ mục liên quan cần được cập nhật nhất quán theo giao dịch hoặc giao thức ứng dụng.

Cây lazy chỉ duy trì **bất biến bên trong chính nó**. Nó không tự bảo đảm dữ liệu trong bảng băm, cơ sở dữ liệu hay các phiên bản báo cáo khác đồng bộ với cây.

## 16. Đồng thời, phiên bản và giới hạn truy vấn “chỉ đọc”

### 16.1. Tại sao `range_query` có thể ghi dữ liệu?

Khi query phủ trọn một nút, nó trả `tree[v]`. Nhưng khi chỉ giao một phần, nó có thể phải gọi `_push`:

```text
Nhánh truy vấn:
  đọc pending[v]
  apply xuống con trái
  apply xuống con phải
  đặt pending[v] = identity
  sau đó mới truy vấn các con
```

Do đó, truy vấn **không đổi giá trị logic** nhưng có thể **thay đổi biểu diễn bộ nhớ**. Một API chỉ gắn khóa đọc cho mọi `range_query` mà không xét `push` có thể cho phép hai truy vấn cùng sửa các ô trạng thái và gây race condition.

### 16.2. Epoch không đủ bảo vệ tính nguyên tử

Một bộ đếm phiên bản tăng sau cập nhật giúp phát hiện thay đổi trong lịch tuần tự, nhưng không tự ngăn được:

```text
Luồng A: đọc pending[root]
Luồng B: bắt đầu push root, đã sửa con trái nhưng chưa sửa con phải
Luồng A: tiếp tục đọc một phần cây từ trạng thái chưa hoàn chỉnh
```

Nếu cần đọc/ghi đồng thời, hãy dùng chiến lược đồng bộ/phiên bản phù hợp với toàn bộ phép `apply/push/pull`, không chỉ kiểm tra epoch một lần. Các lựa chọn có thể là **khóa**, **snapshot nhất quán** hoặc **cấu trúc phiên bản bất biến**, mỗi loại có đánh đổi riêng.

### 16.3. Truy vấn không `push` là một biến thể khác

Có thể viết thuật toán query **không thay đổi cây** bằng cách mang nhãn chưa áp từ tổ tiên xuống các lời gọi con. Nhưng khi đó phải tính đúng:

- Thứ tự của nhãn **tổ tiên và nút con**.
- Những cập nhật nào đã phản ánh trong `tree[v]`.
- Cách áp nhãn mang theo cho một đoạn được phủ trọn.

Không thể chỉ bỏ dòng `_push` trong mã rồi cho rằng query sẽ bất biến và vẫn đúng. Một biến thể không `push` cần được **thiết kế và chứng minh riêng**.

### 16.4. Tràn số, số rất lớn và kiểu dữ liệu

Trong ngôn ngữ có số nguyên cố định, `mS+b·length` có thể tràn dù các giá trị đầu vào riêng lẻ nhỏ. Phải quyết định:

- Dùng kiểu số đủ rộng?
- Kiểm tra tràn và báo lỗi?
- Làm việc modulo `p`, với điều kiện thống kê và phép toán cũng được định nghĩa modulo `p`?

Trong Python, số nguyên có độ dài tùy ý nhưng các phép toán trên số cực lớn không còn có chi phí hằng số chính xác theo **số bit**. Cận O(log n) là cận số bước cấu trúc trong mô hình phép toán số học O(1).

## 17. Những lỗi dễ mắc khi hợp thành nhãn

### 17.1. Sai về thời gian của các cập nhật

**Lỗi 1 — Đảo `compose(new,old)` thành `compose(old,new)`.**

Ví dụ `SET(10)` rồi `ADD(3)` phải cho 13. Nếu đảo nhãn sẽ ra 10.

**Lỗi 2 — Xem cập nhật `SET(0)` như nhãn đơn vị.**

Identity affine là `(1,0)`, còn `SET(0)=(0,0)`. Một bên không thay dữ liệu, một bên biến mọi giá trị thành 0.

**Lỗi 3 — Cho rằng các nhãn giao hoán vì phép cộng giao hoán.**

Phép gộp **sum** có tính giao hoán nhưng phép cập nhật **SET và ADD** không giao hoán. Tính chất của `merge` và `compose` là hai vấn đề độc lập.

**Lỗi 4 — Cộng nhãn SET cũ và SET mới.**

`SET(5)` rồi `SET(2)` chỉ còn `SET(2)`, không phải `SET(7)`.

**Lỗi 5 — Hợp thành `MUL` trước `ADD` sai thứ tự.**

`ADD(2)` rồi `MUL(3)` cho `3x+6`; `MUL(3)` rồi `ADD(2)` cho `3x+2`.

### 17.2. Sai bất biến tổng hợp

**Lỗi 6 — Áp delta cho sum mà quên nhân độ dài.**

Với nút quản lý bốn phần tử, `ADD(3)` phải tăng tổng **12**, không phải 3.

**Lỗi 7 — Áp công thức sum cho min/max.**

Nếu cộng 3 vào mọi phần tử, **min và max tăng 3**, không tăng `3·length`.

**Lỗi 8 — Nhân số âm vào min mà không đổi vai trò min/max.**

Với `min=-3,max=5`, nhân −2 cho min mới **−10**, không phải 6.

**Lỗi 9 — Chỉ lưu GCD mà muốn cộng đoạn bằng cách cập nhật GCD từ delta.**

Hai đoạn cùng GCD ban đầu có thể có GCD mới khác nhau sau cùng một cập nhật.

**Lỗi 10 — Dùng tổng của hai con trong khi cha còn nhãn chưa đẩy.**

Khi `tag[v]≠ID`, công thức `tree[v]=merge(left,right)` thường **chưa đúng**. Cần `push` trước `pull` hoặc dùng đúng công thức có nhãn.

**Lỗi 11 — `push` tăng thêm `tree[v]` một lần nữa.**

`tree[v]` đã tính tác động của nhãn, `push` chỉ chuyển tác động xuống con.

**Lỗi 12 — Truy vấn phủ trọn rồi vẫn áp nhãn lần hai.**

Với một nút đã lưu sum=80, tag=SET(10), `range_query` phủ trọn phải trả **80**, không thêm `10·length` hay gán lại một lần.

### 17.3. Sai đường đi và ranh giới

**Lỗi 13 — Đi xuống con trước `push`.**

Con đang giữ thống kê cũ; cập nhật một phần có thể làm mất tác động cập nhật của cha.

**Lỗi 14 — `pull` sau cập nhật phủ trọn.**

Nút đã đúng nhờ `apply` và còn nhãn chờ; `pull` từ con cũ sẽ ghi đè kết quả mới.

**Lỗi 15 — Đẩy nhãn vào lá.**

Lá không có hai con thật; phải dừng khi `R-L=1`.

**Lỗi 16 — Dùng độ dài cha cho cả hai con.**

Với `n` không là lũy thừa hai, chiều dài con trái và phải có thể khác nhau; mỗi con cần chiều dài riêng.

**Lỗi 17 — Lẫn `[l,r)` với `[l,r]`.**

`range_apply(2,5,tag)` tác động các vị trí 2,3,4; không chứa vị trí 5.

**Lỗi 18 — Đoạn rỗng bị coi là một phần tử.**

`[i,i)` không chứa phần tử; cập nhật không làm gì và truy vấn trả identity.

**Lỗi 19 — Bỏ kiểm tra ranh giới vì nhãn là identity.**

`range_apply(-1,3,ID)` vẫn phải báo lỗi, không được bỏ qua như một yêu cầu hợp lệ.

### 17.4. Sai hợp đồng về kiểu dữ liệu và hiệu năng

**Lỗi 20 — Dùng object identity thay vì giá trị nhãn để nhận biết identity.**

Hai đối tượng `AffineTag(1,0)` khác vị trí nhớ vẫn là cùng phép biến đổi. Với dataclass bất biến, so sánh giá trị `==` là phù hợp.

**Lỗi 21 — Dùng list/dict khả biến làm identity rồi sửa tại chỗ.**

Các ô mảng cây có thể đang chia sẻ cùng đối tượng. Cần value bất biến hoặc tạo identity riêng cho từng ô.

**Lỗi 22 — Nhầm `to_leaves` với một thao tác O(log n).**

Xuất đủ `n` lá cần O(n); không tính chi phí này vào thời gian của `range_apply`.

**Lỗi 23 — Chạy kiểm tra toàn cây sau mỗi cập nhật rồi kết luận cập nhật O(n).**

`validate_normalized` O(n) là kiểm thử riêng.

**Lỗi 24 — Xem phép nối chuỗi dài là O(1) chỉ vì nó là một phép `merge`.**

Chi phí tạo bản sao chuỗi còn phụ thuộc độ dài dữ liệu.

**Lỗi 25 — Cho rằng `range_query` luôn chỉ đọc trạng thái vật lý.**

Query có thể `push` nhãn và ghi vào các mảng cây; cần cân nhắc đồng bộ.

### 17.5. Một bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân nên kiểm trước |
| --- | --- |
| Hỏi cả mảng đúng, hỏi một phần sai | `push` hoặc thứ tự `compose` |
| Chỉ sai sau `SET` rồi `ADD` | Nhãn gán mới/cũ bị đảo thứ tự |
| `SET(0)` không có tác động | Identity bị nhầm với nhãn gán 0 |
| Lỗi khi nhân số âm và hỏi min/max | Không hoán đổi vai trò min/max |
| Sai khi `n=5` nhưng đúng khi `n=8` | Tính chiều dài con hoặc ranh giới chia đoạn |
| Một phép cập nhật làm tổng tăng quá nhiều | Áp nhãn ở cha và con hai lần, hoặc `pull` sai |
| Sau kiểm thử `to_leaves`, mảng `pending` thay đổi | Đó là hành vi vật chất hóa có `push`, không nhất thiết là lỗi |
| Kết quả chỉ sai khi nhiều luồng cùng chạy | Truy cập trạng thái `tree/pending` không được đồng bộ |

## 18. Checklist kiểm chứng thuật toán

Trước khi đưa một cây lazy vào bài thực hành hoặc dịch vụ:

1. Đã ghi rõ ý nghĩa đoạn **`[l,r)`** chưa?
2. `merge` có **tính kết hợp** và identity hai phía chưa?
3. Nhãn identity có thực sự **không đổi mọi phần tử** chưa?
4. `compose(new,old)` có định nghĩa rõ **old trước, new sau** chưa?
5. Có chứng minh **`apply(compose(new,old),S,k)=apply(new,apply(old,S,k),k)`** chưa?
6. Có chứng minh **`apply(tag,merge(A,B),lenA+lenB)=merge(apply(tag,A,lenA),apply(tag,B,lenB))`** chưa?
7. `apply` đã cập nhật **tổng hợp của nút** và **nhãn đang đợi** cùng lúc chưa?
8. `push` có được gọi trước khi đi xuống con đang nợ nhãn không?
9. `push` có dùng đúng **độ dài con** và xóa nhãn ở cha không?
10. `pull` có chỉ chạy khi nhãn của cha đã là identity không?
11. Truy vấn phủ trọn có chỉ trả `tree[v]` mà không áp nhãn lần nữa không?
12. Cây có xử lý `n=0`, `n=1` và `n` không phải lũy thừa hai không?
13. Đã kiểm `SET(0)`, `ADD(0)`, `MUL(0)`, số âm và các lần cập nhật xen kẽ chưa?
14. Đã so với một **mảng tham chiếu độc lập** sau nhiều cập nhật chồng lấn chưa?
15. Nếu lưu min/max, đã kiểm cả phép nhân âm chưa?
16. Nếu dữ liệu có kiểu khác số nguyên, đã xác định chi phí và khả năng tương thích của phép tác động chưa?
17. Đã tách `to_leaves/validate/log` khỏi phép đo hiệu năng chưa?
18. Nếu nhiều luồng truy cập, đã có chiến lược **đồng bộ hoặc phiên bản** đúng với `push` chưa?

## 19. Bài tập vận dụng

### Bài 1 — Giá trị logic khác giá trị ở lá

Cho cây tổng trên `[2,4,1,3]`. Sau `range_set(0,4,10)`, vì sao `tree[root]=40` nhưng các lá có thể vẫn giữ những số cũ?

*Gợi ý:* Gốc đã cập nhật tổng và giữ nhãn `SET(10)` cho các con. Việc vật chất hóa lá có thể bị trì hoãn.

### Bài 2 — Tính kết quả sau các lệnh chồng lấn

Với `A=[2,4,1,3,5,7,6,8]`, lần lượt gọi `SET(10)` trên `[0,8)` và `ADD(3)` trên `[2,6)`. Mảng logic và tổng cuối là gì?

*Gợi ý:* `[10,10,13,13,13,13,10,10]`, tổng 92.

### Bài 3 — Gán 0 không phải identity

Sau Bài 2, gán 0 cho `[3,5)`. Tính tổng mới. Vì sao dùng `(0,0)` làm identity của nhãn affine sẽ sai?

*Gợi ý:* Tổng 66; `(0,0)` nghĩa là `SET(0)`, còn identity là `(1,0)`.

### Bài 4 — Phân biệt nhãn cũ và nhãn mới

Một nút con có nhãn `SET(7)`; cha sau đó nhận `ADD(5)` và chưa push. Khi push, nhãn mới của con là gì?

*Gợi ý:* `ADD(5)∘SET(7)=SET(12)`.

### Bài 5 — Đảo thứ tự phép cập nhật

Từ `x=4`, so sánh `ADD(3)` rồi `SET(10)` với `SET(10)` rồi `ADD(3)`.

*Gợi ý:* Kết quả 10 và 13; không giao hoán.

### Bài 6 — Nhân độ dài đoạn

Một nút có tổng 23, độ dài 5; áp `ADD(-4)`. Tổng mới là bao nhiêu? Nếu nhãn được đẩy xuống hai con dài 2 và 3, mỗi tổng con thay đổi bao nhiêu?

*Gợi ý:* Tổng mới 3; hai con thay đổi −8 và −12.

### Bài 7 — Xác định ba phép toán

Với một cây cần `range_add` và `range_sum`, viết `merge`, `apply` và `compose` tương ứng.

*Gợi ý:* `merge(a,b)=a+b`, `apply(d,S,k)=S+dk`, `compose(new,old)=old+new`.

### Bài 8 — Chứng minh luật phân phối

Chứng minh với tổng đoạn và cập nhật `ADD(d)`:

\[
apply(d,S_L+S_R,k_L+k_R)
=apply(d,S_L,k_L)+apply(d,S_R,k_R).
\]

*Gợi ý:* Phân phối phép nhân `d(k_L+k_R)`.

### Bài 9 — Chứng minh luật nhãn đơn vị

Với affine `I=(1,0)`, chứng minh `apply(I,S,k)=S` và `compose(I,f)=compose(f,I)=f`.

*Gợi ý:* Thế `m=1,b=0` vào hai công thức.

### Bài 10 — Hợp thành hai nhãn affine

Nhãn cũ `g(x)=2x+3`, nhãn mới `f(x)=-x+5`. Tính `f∘g`.

*Gợi ý:* `-2x+2`, cặp `(-2,2)`.

### Bài 11 — Chứng minh phép hợp thành kết hợp

Giải thích vì sao `compose(h,compose(f,g))=compose(compose(h,f),g)` dù nói chung `compose(f,g)≠compose(g,f)`.

*Gợi ý:* Hợp thành hàm là kết hợp nhưng không nhất thiết giao hoán.

### Bài 12 — Độ dài con không bằng nhau

Nút quản lý `[0,5)`, con trái `[0,2)` và con phải `[2,5)`. Đẩy nhãn `ADD(4)` làm tổng của mỗi con tăng bao nhiêu?

*Gợi ý:* Con trái tăng 8, con phải tăng 12.

### Bài 13 — Khi nào không push?

Một nút quản lý đúng `[0,8)` có `tree[v]=80` và `tag[v]=SET(10)`. Truy vấn `[0,8)` có cần đẩy nhãn không? Trả kết quả gì?

*Gợi ý:* Không; trả 80 ngay.

### Bài 14 — Khi nào phải push?

Vẫn nút trên, nhưng cần hỏi `[2,4)`. Vì sao không được đi xuống con còn lưu giá trị cũ trước khi push?

*Gợi ý:* Con chưa phản ánh SET(10), phải chuyển nhãn từ cha xuống trước.

### Bài 15 — Vì sao pull sai lúc cha còn nhãn?

Sau `SET(10)` toàn mảng, gốc tổng 80, hai con còn tổng cũ 10 và 26. Nếu gọi `pull` ngay, gốc sẽ bị sửa thành bao nhiêu và vì sao sai?

*Gợi ý:* Thành 36; làm mất cập nhật.

### Bài 16 — Tính tổng bằng affine

Nút có tổng 17 trên bốn phần tử. Áp `f(x)=3x−2` đồng đều. Tổng sau cập nhật là gì?

*Gợi ý:* `3×17−2×4=43`.

### Bài 17 — SET sau ADD

Hợp thành nhãn cũ `ADD(7)=(1,7)` với nhãn mới `SET(4)=(0,4)` theo công thức affine.

*Gợi ý:* `(0,4)∘(1,7)=(0,4)`.

### Bài 18 — ADD sau SET

Hợp thành nhãn cũ `SET(4)=(0,4)` với nhãn mới `ADD(7)=(1,7)`.

*Gợi ý:* `(1,7)∘(0,4)=(0,11)`.

### Bài 19 — Nhân trước cộng và nhân sau cộng

So sánh `ADD(2)` rồi `MUL(3)` với `MUL(3)` rồi `ADD(2)`. Viết nhãn affine kết quả.

*Gợi ý:* Lần lượt `(3,6)` và `(3,2)`.

### Bài 20 — Nhân với 0 khác identity

Vì sao `MUL(0)=(0,0)` không thể được bỏ qua như `(1,0)`? Hãy cho ví dụ trên mảng hai phần tử.

*Gợi ý:* `[5,9]` trở thành `[0,0]`, không giữ `[5,9]`.

### Bài 21 — Min/max khi nhân số âm

Đoạn `[-3,2,5]` có `sum=4,min=-3,max=5`. Nhân cả đoạn với −2. Tính tuple mới.

*Gợi ý:* `(-8,-10,6)`.

### Bài 22 — Identity của tuple `(sum,min,max)`

Nêu identity của phép gộp ba trường này. Vì sao `(0,0,0)` không phù hợp nếu mọi phần tử đoạn đều âm?

*Gợi ý:* `(0,+∞,-∞)`; dùng min identity 0 sẽ làm min sai trên đoạn toàn dương, dùng max identity 0 sẽ làm max sai trên đoạn toàn âm.

### Bài 23 — GCD không cập nhật được chỉ từ nhãn cộng

Cho hai đoạn `[2,4]` và `[2,6]` có cùng GCD là 2. Sau cộng +2 vào mọi phần tử, GCD của từng đoạn là bao nhiêu? Điều đó bác bỏ giả thiết nào?

*Gợi ý:* GCD mới 2 và 4; không thể suy GCD mới chỉ từ GCD cũ, độ dài và delta.

### Bài 24 — Gộp chuỗi không giao hoán

Với `merge(a,b)` là nối chuỗi, dùng thứ tự `merge(right,left)` thay `merge(left,right)` có còn đúng không?

*Gợi ý:* Không; `"AB"+"CD"="ABCD"` khác `"CDAB"`.

### Bài 25 — Sai do làm tròn từng phần tử

Cho đoạn `[1,1]` và phép cập nhật `x↦ceil(x/2)`. Tổng sau cập nhật là bao nhiêu? So sánh với `ceil(sum/2)`.

*Gợi ý:* Tổng mới 2; `ceil(2/2)=1`. Chỉ lưu sum là không đủ cho công thức ấy.

### Bài 26 — Kiểm tra trường hợp n=0

Trong cây lazy trên mảng rỗng, `range_query(0,0)` phải trả gì với phép tổng? `range_apply(0,0,SET(0))` có thay đổi phần tử nào không?

*Gợi ý:* Trả 0, cập nhật không làm gì; nhưng `range_apply(-1,0,ID)` vẫn là lỗi miền chỉ số.

### Bài 27 — Bắt lỗi từ nhãn chồng lấn

Thiết kế một chuỗi thao tác giúp phát hiện lỗi hợp thành `SET` và `ADD` trong cây có ít nhất bốn phần tử. Những truy vấn nào cần thực hiện?

*Gợi ý:* Gán toàn mảng rồi cộng một đoạn con, hỏi **một điểm trong đoạn con** và **một điểm ngoài đoạn con**, không chỉ hỏi cả mảng.

### Bài 28 — Hai loại kiểm thử

Tại sao cần vừa kiểm các định luật `apply/compose/merge`, vừa đối chiếu `range_query` với mảng trực tiếp?

*Gợi ý:* Nhóm đầu phát hiện sai đại số; nhóm sau phát hiện sai chia đoạn, `push/pull` và ranh giới.

### Bài 29 — Độ phức tạp thực sự của vật chất hóa

Với `n` phần tử, `range_query` có O(log n) bước cấu trúc còn `to_leaves()` cần bao nhiêu thời gian? Tại sao không nên gọi `to_leaves()` trong mỗi lần đo tốc độ `range_apply`?

*Gợi ý:* O(n), vì phải xuất đủ n phần tử; đó là thao tác riêng.

### Bài 30 — Phân tích đồng thời

Một hệ thống có nhiều luồng `range_query` nhưng cài đặt query sử dụng `push`. Vì sao chỉ cho tất cả query giữ **read lock đồng thời** chưa chắc an toàn?

*Gợi ý:* `push` có thể sửa các nhãn và tổng con trong bộ nhớ; cần đồng bộ với những ghi đó.

### Bài 31 — Lựa chọn cho thống kê học tập

Một hệ thống cần `ADD`, `SET` theo đoạn ngày và truy vấn `sum/min/max`. Đề xuất metadata, identity, nhãn và công thức `apply`.

*Gợi ý:* Metadata `(sum,min,max)`, identity `(0,+∞,-∞)`, nhãn affine; nhân âm cần đổi min/max nếu còn hỗ trợ MUL.

### Bài 32 — Khi nào không nên dùng cây lazy?

Đầu vào có 100 nghìn lệnh cộng đoạn nhưng không có truy vấn xen giữa; chỉ cần danh sách giá trị cuối. Nêu một phương án đơn giản hơn có thể phù hợp và độ phức tạp.

*Gợi ý:* Difference array, O(1) mỗi lệnh cộng và O(n) để khôi phục cuối.

## 20. Tổng kết

**Hợp thành nhãn cập nhật và bảo toàn bất biến tổng hợp** là trung tâm của lazy propagation. Nút cha có thể chứa kết quả đã được cập nhật trong khi các con còn giữ giá trị cũ, vì **`tag[v]` ghi nhớ tác động đã tính vào `tree[v]` nhưng chưa truyền xuống con**.

Để cài cây lazy đúng, hãy xác định:

- **`merge`:** giá trị tổng hợp của hai đoạn liền nhau; phải kết hợp và có identity.
- **`apply(tag,aggregate,length)`:** giá trị tổng hợp sau khi nhãn tác động lên mọi phần tử đoạn.
- **`compose(new,old)`:** nhãn tương đương thực hiện **old trước, new sau**; phải hợp thành theo đúng thời gian.
- **`push`:** chuyển nhãn của cha xuống các con mà **không đổi dữ liệu logic**.
- **`pull`:** sau khi cập nhật giao một phần, gộp tổng hợp các con khi nhãn cha đã được chuyển xuống.

Với **truy vấn tổng**, nhãn affine `f(x)=mx+b` biểu diễn được `ADD`, `SET` và `MUL`. Hai công thức then chốt là:

\[
apply((m,b),S,k)=mS+bk
\]

và:

\[
compose((m_f,b_f),(m_g,b_g))
=(m_fm_g,\ m_fb_g+b_f).
\]

Cần lưu ý `SET(0)=(0,0)` **không phải** nhãn đơn vị `(1,0)`, và `compose` **không giao hoán** nói chung. Khi thay `sum` bằng `(sum,min,max)`, ta phải đổi cả `merge` và `apply`, nhất là với phép nhân âm.

Trong mô hình mỗi phép `merge/apply/compose` tốn O(1), cây lazy hỗ trợ **O(n) xây dựng, O(log(n+1)) cập nhật đoạn, O(log(n+1)) truy vấn đoạn và O(n) bộ nhớ**. Những cận này chỉ có ý nghĩa khi **định luật đại số**, **ranh giới đoạn**, **hợp thành nhãn**, **bất biến sau push/pull** và **kiểm thử đối chiếu** đều đúng. Không nên đánh đổi tính đúng đắn chỉ để giảm số lần đi xuống cây.
