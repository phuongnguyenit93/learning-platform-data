# Lan truyền trì hoãn khi cập nhật theo đoạn

**Lan truyền trì hoãn** (*lazy propagation*) là kỹ thuật mở rộng **segment tree (cây đoạn)** để xử lý hiệu quả các phép **cập nhật hàng loạt trên một đoạn liên tiếp**. Thay vì đi xuống mọi phần tử khi nhận lệnh “cộng 5 vào các chỉ số từ l đến r”, cây cập nhật ngay thông tin tổng hợp của nút đang bao phủ trọn đoạn và ghi lại một **thẻ cập nhật đang chờ** (*lazy tag*). Chỉ khi cần xử lý sâu hơn bên trong đoạn đó, thẻ mới được **đẩy xuống nút con** (*push*).

Nhờ kỹ thuật này, một dãy n phần tử có thể hỗ trợ nhiều thao tác đan xen như:

- **Cộng một giá trị vào mọi phần tử của đoạn \([l,r]\)** (*range add*).
- **Gán mọi phần tử của đoạn \([l,r]\) bằng một giá trị** (*range assign / range set*).
- **Truy vấn tổng, giá trị nhỏ nhất và giá trị lớn nhất của đoạn** (*range sum/min/max*).

Với một segment tree được xây đúng và thẻ cập nhật được **kết hợp theo đúng thứ tự**, mỗi thao tác trên đoạn liên tiếp mất **O(log n)** thời gian trong trường hợp xấu, sau O(n) thời gian xây và O(n) bộ nhớ.

Chủ đề nằm trong nhóm **Truy vấn và ngoại tuyến**, nhưng một cây đoạn có lazy propagation hoạt động **trực tuyến**: sau mỗi lệnh cập nhật, có thể trả lời ngay truy vấn tiếp theo mà không cần biết trước toàn bộ danh sách lệnh. Điều quan trọng là phân biệt kỹ thuật này với *difference array* phù hợp cho việc gom cập nhật rồi tổng kết ngoại tuyến.

Bài học này đi từ cây đoạn cơ bản, bất biến nút, cơ chế `apply / push / pull`, phép hợp thành hai loại thẻ **SET và ADD không giao hoán**, đến chương trình **Java 17+ chạy độc lập** có truy vấn tổng/nhỏ nhất/lớn nhất, kiểm tra chỉ số, phát hiện tràn số và **oracle đối chiếu bằng mảng thường**. Các trường hợp gán 0, cộng số âm, cập nhật chồng lấn, đoạn chỉ có một phần tử và nhiều thứ tự cập nhật đều được trình bày chi tiết.

## 1. Phát biểu bài toán

Cho mảng có n phần tử nguyên:

\[
a[0],a[1],\ldots,a[n-1].
\]

Bài học sử dụng **chỉ số 0-based**, đoạn **đóng hai đầu** \([l,r]\), nghĩa là bao gồm cả a[l] và a[r]. Một thao tác hợp lệ cần:

\[
\boxed{0\le l\le r<n.}
\]

Ta cần xử lý nhiều lệnh theo đúng thứ tự xuất hiện:

**Cập nhật cộng:**

\[
\forall i\in[l,r],\quad a[i]\leftarrow a[i]+d.
\]

**Cập nhật gán:**

\[
\forall i\in[l,r],\quad a[i]\leftarrow v.
\]

**Truy vấn tổng:**

\[
\operatorname{sum}(l,r)=\sum_{i=l}^{r}a[i].
\]

**Truy vấn nhỏ nhất:**

\[
\operatorname{min}(l,r)=\min_{l\le i\le r}a[i].
\]

**Truy vấn lớn nhất:**

\[
\operatorname{max}(l,r)=\max_{l\le i\le r}a[i].
\]

Ví dụ:

~~~text
a = [5, -2, 7, 1, 4, 0]
add(1, 4, +3)       -> [5,  1, 10,  4, 7, 0]
assign(2, 5, -1)    -> [5,  1, -1, -1,-1,-1]
add(3, 5, +4)       -> [5,  1, -1,  3, 3, 3]
~~~

Thao tác phải được **áp dụng theo thứ tự**. Không thể gom mọi phép gán và cộng một cách tùy ý, vì “gán rồi cộng” khác với “cộng rồi gán”.

## 2. Vì sao cập nhật từng phần tử có thể quá chậm?

Một lời giải trực tiếp lưu mảng a và thực hiện:

~~~text
rangeAdd(l,r,d):
    for i from l to r:
        a[i] += d

rangeAssign(l,r,v):
    for i from l to r:
        a[i] = v
~~~

Mỗi cập nhật tốn:

\[
\Theta(r-l+1)
\]

thời gian, lên tới Θ(n) nếu cập nhật gần như toàn bộ mảng. Với q lệnh cùng có đoạn dài n, thời gian có thể Θ(qn).

Ngược lại, tiền tố cộng dồn (*prefix sums*) giúp truy vấn tổng nhanh, nhưng **một cập nhật đoạn** có thể làm nhiều tổng tiền tố thay đổi. Vì vậy một mảng prefix sum tĩnh không giải quyết tốt việc **cập nhật và truy vấn xen kẽ**.

Khi có rất nhiều cập nhật đoạn rồi **chỉ cần tính mảng kết quả cuối**, *difference array* là lựa chọn tốt:

~~~text
diff[l] += d
diff[r+1] -= d      // nếu r+1 < n
cuối cùng quét prefix sum của diff
~~~

Nhưng nếu truy vấn tổng/min/max liên tục xuất hiện **giữa các cập nhật**, ta cần một cấu trúc duy trì trạng thái có tổ chức hơn, chẳng hạn segment tree với lazy propagation.

## 3. Cây đoạn cơ bản lưu những gì?

Mỗi nút p của segment tree đại diện một đoạn \([L,R]\) trong mảng gốc.

- Nút gốc đại diện [0,n−1].
- Nếu L<R, chia tại \(M=\lfloor(L+R)/2\rfloor\).
- Con trái đại diện [L,M].
- Con phải đại diện [M+1,R].
- Lá đại diện một phần tử duy nhất.

Ví dụ mảng 8 phần tử:

~~~text
                       [0,7]
                  /             \
               [0,3]           [4,7]
              /     \          /     \
           [0,1]   [2,3]    [4,5]   [6,7]
           /  \    /  \     /  \     /  \
          0    1  2    3   4    5   6    7
~~~

Nút p giữ ba tổng hợp cho **toàn bộ đoạn mà nó đại diện**:

\[
\begin{aligned}
sum[p]&=\sum_{i=L}^{R}a[i],\\
min[p]&=\min_{i=L}^{R}a[i],\\
max[p]&=\max_{i=L}^{R}a[i].
\end{aligned}
\]

Nếu không có thẻ đang chờ, thông tin nút cha có thể **gộp** từ hai con:

\[
\boxed{sum[p]=sum[2p]+sum[2p+1]}
\]

\[
\boxed{min[p]=\min(min[2p],min[2p+1])}
\]

\[
\boxed{max[p]=\max(max[2p],max[2p+1]).}
\]

Trong mảng lưu cây kiểu 1-based, nút con trái là `2*p`, con phải là `2*p+1`. Số nút thực sự của cây nhị phân đoạn là O(n); một cách cấp phát phổ biến sử dụng mảng `4*n` phần tử để tránh tính kích thước cây làm tròn lên lũy thừa 2.

## 4. Tại sao cây đoạn thường chưa đủ?

Với truy vấn tổng, ta có thể đi xuống những nút có đoạn giao với [l,r] và gộp tổng hợp, không cần duyệt từng phần tử.

Nhưng với lệnh cập nhật đoạn **không có lazy tag**, nếu muốn thay đổi mọi phần tử dưới một nút bao phủ trọn đoạn, ta vẫn có thể phải đi xuống tất cả các lá của nút ấy.

Ví dụ:

~~~text
a = [1,2,3,4,5,6,7,8]
add(0,7,+10)
~~~

Nếu thay đổi từng lá, cập nhật đầy mảng phải đụng tới 8 vị trí; với n lớn là O(n).

Thực ra tổng mới của toàn bộ đoạn được tính ngay:

\[
sum[0..7]_{\text{mới}}
=sum[0..7]_{\text{cũ}}+10\cdot8.
\]

Giá trị nhỏ nhất/lớn nhất cũng tăng đúng 10:

\[
min_{\text{mới}}=min_{\text{cũ}}+10,\quad
max_{\text{mới}}=max_{\text{cũ}}+10.
\]

Ta có thể **cập nhật thẳng nút gốc** và ghi nhớ rằng các con **chưa được cập nhật tương ứng**. Đó chính là ý tưởng của lazy propagation.

## 5. Ý nghĩa của thẻ trì hoãn

Một **lazy tag** biểu diễn phép biến đổi cần áp dụng lên **toàn bộ phần tử** trong đoạn của nút.

Đối với bài hỗ trợ cả cộng và gán, ta xét hai loại phép biến đổi:

\[
ADD(d):\quad x\mapsto x+d
\]

\[
SET(v):\quad x\mapsto v.
\]

Khi một lệnh cập nhật **bao trọn** đoạn [L,R] của nút p:

1. **Cập nhật ngay** `sum[p]`, `min[p]`, `max[p]` để tổng hợp của nút p phản ánh trạng thái mới.
2. Ghi lại **tag** để khi truy vấn/cập nhật cần đi sâu, có thể áp dụng cùng biến đổi cho hai con.
3. **Không** đi xuống các con ngay lúc đó.

Do các tổng hợp của nút p đã đúng, nếu truy vấn cũng **bao trọn** nút p, trả kết quả ngay mà không cần đẩy tag.

### Bất biến cốt lõi

Đối với mỗi nút p đại diện đoạn [L,R]:

> **Các tổng hợp sum/min/max tại p luôn phản ánh mọi lệnh cập nhật đã nhận đối với đoạn [L,R]. Nếu p mang tag chưa đẩy, các con của p có thể chưa phản ánh cập nhật ấy; tag là lời hứa để đồng bộ các con trước khi truy cập sâu.**

Nhờ vậy cây có thể đúng ngay cả khi một phần các nút con còn chứa giá trị “cũ”.

Không nên hiểu `lazy[p]` là “tổng hợp sum[p] chưa được tính”. Thực tế **sum[p] đã đúng**; chính các con của p mới đang chờ nhận cập nhật.

## 6. Hàm apply: cập nhật tổng hợp của một nút

Gọi độ dài đoạn p là:

\[
len=R-L+1.
\]

### A. Áp dụng lệnh gán SET(v)

Khi mọi phần tử trong đoạn trở thành v:

\[
\boxed{sum[p]=v\cdot len}
\]

\[
\boxed{min[p]=max[p]=v.}
\]

Đồng thời mọi cập nhật đang chờ **trước đó** trên cùng nút phải bị phép gán mới **ghi đè**. Vì thế ta đặt:

~~~text
hasSet[p] = true
setValue[p] = v
addValue[p] = 0
~~~

### B. Áp dụng lệnh cộng ADD(d)

Khi mọi phần tử trong đoạn tăng d:

\[
\boxed{sum[p]\leftarrow sum[p]+d\cdot len}
\]

\[
\boxed{min[p]\leftarrow min[p]+d}
\]

\[
\boxed{max[p]\leftarrow max[p]+d.}
\]

Thẻ cần hợp thành với tag đang có:

- Nếu nút đã chờ `SET(v)`, cộng mới biến nó thành **SET(v+d)**.
- Nếu nút chỉ chờ `ADD(a)`, cộng mới biến nó thành **ADD(a+d)**.
- Nếu chưa có tag, coi như `ADD(0)`.

Do đó:

~~~text
if hasSet[p]:
    setValue[p] += d
else:
    addValue[p] += d
~~~

Quan trọng: lệnh ADD sau một SET có thể được hấp thụ ngay vào **giá trị SET**. Vì vậy thiết kế này duy trì quy ước: **nếu hasSet=true thì addValue=0**.

## 7. Hợp thành tag và thứ tự thời gian

Tại một phần tử x, đặt:

\[
A_v(x)=v,\qquad D_d(x)=x+d.
\]

Dùng ký hiệu \(f\circ g\) nghĩa là **áp dụng g trước, f sau**.

Ta có:

\[
\boxed{D_d\circ A_v=A_{v+d}.}
\]

Nghĩa là **gán v rồi cộng d** tương đương **gán v+d**.

Nhưng:

\[
\boxed{A_v\circ D_d=A_v.}
\]

Nghĩa là **cộng d rồi gán v** chỉ còn **gán v**: phép gán mới xóa bỏ tác dụng của phép cộng trước.

Hai phép cộng hợp lại:

\[
\boxed{D_b\circ D_a=D_{a+b}.}
\]

Hai phép gán hợp lại:

\[
\boxed{A_v\circ A_u=A_v.}
\]

Phép gán mới nhất thắng.

Bảng hợp thành:

| Thẻ cũ tại nút | Lệnh mới | Thẻ hợp thành |
|---|---|---|
| Không có | ADD(d) | ADD(d) |
| ADD(a) | ADD(d) | ADD(a+d) |
| SET(v) | ADD(d) | SET(v+d) |
| Không có | SET(v) | SET(v) |
| ADD(a) | SET(v) | SET(v) |
| SET(u) | SET(v) | SET(v) |

Đây là **bảng quan trọng nhất** khi cài segment tree hỗ trợ vừa range add vừa range assign.

### Ví dụ không giao hoán

~~~text
Ban đầu một phần tử x = 10

SET(3) rồi ADD(4):
    x = 3 rồi x = 7         -> kết quả 7

ADD(4) rồi SET(3):
    x = 14 rồi x = 3        -> kết quả 3
~~~

Nếu xử lý cả hai như những con số có thể cộng chung tùy ý, ta sẽ cho ra kết quả sai.

## 8. Vì sao phải có cờ hasSet?

Một lỗi phổ biến là dùng `setValue[p]=0` làm dấu hiệu “không có phép gán đang chờ”.

Điều này **sai** vì:

\[
SET(0)
\]

là một lệnh cập nhật hoàn toàn hợp lệ.

Ví dụ:

~~~text
a = [5, 7, 9]
assign(0,2,0)
query(0,2) -> 0
~~~

Nếu hiểu tag `setValue=0` là “không có gán”, các nút con sẽ không nhận việc gán về 0 khi cần push, và truy vấn từng phần tử có thể trả lại giá trị cũ.

Cách an toàn là lưu riêng:

~~~text
boolean hasSet[p]
long    setValue[p]
long    addValue[p]
~~~

Khi hasSet=false, setValue có thể là bất kỳ giá trị còn lưu trong ô nhớ, nhưng **không được dùng**. Khi hasSet=true, setValue là giá trị gán còn chờ; theo quy ước của bài, addValue=0.

Một `boolean` riêng cũng giúp phân biệt `ADD(0)` — có thể coi là không có thay đổi — với `SET(0)`, vốn **không thể bỏ qua**.

## 9. Hàm push: chuyển thẻ của cha xuống hai con

Khi nút p đại diện [L,R] chưa phải lá, chia tại M.

Trước khi duyệt một phần bên trong nó, phải đồng bộ hai con bằng cách:

1. Nếu cha có `SET(v)` đang chờ: **apply SET(v)** lên cả con trái và con phải, sau đó xóa cờ gán ở cha.
2. Nếu cha có `ADD(d)` đang chờ: **apply ADD(d)** lên cả hai con, sau đó xóa thẻ cộng ở cha.

Mã giả:

~~~text
push(p, L, R):
    if L == R:
        return

    M = floor((L+R)/2)

    if hasSet[p]:
        applySet(leftChild,  L,   M, setValue[p])
        applySet(rightChild, M+1, R, setValue[p])
        hasSet[p] = false

    if addValue[p] != 0:
        applyAdd(leftChild,  L,   M, addValue[p])
        applyAdd(rightChild, M+1, R, addValue[p])
        addValue[p] = 0
~~~

**Thứ tự SET trước ADD** trong dạng tag tổng quát là thiết yếu khi một cấu trúc lưu đồng thời hai tác động. Với thiết kế ở bài, các hàm apply luôn hấp thụ ADD vào SET nên thường **không có cả hai tag khác 0 đồng thời**; tuy vậy thứ tự push vẫn phản ánh phép hợp thành đúng.

### Vì sao không tự thay đổi sum[p] lần nữa khi push?

Trước khi push, `sum[p]` đã phản ánh cập nhật. Khi chuyển tag cho con, ta chỉ làm **con bắt kịp trạng thái của cha**, không tạo một cập nhật mới cho toàn đoạn.

Nếu push lại tự cộng d·len vào sum[p], tổng của cha sẽ bị **cập nhật hai lần**.

### Đẩy tag có làm mất dữ liệu không?

Không: các phép biến đổi đã được áp dụng lên hai con trước khi xóa tag của cha. Sau push, con có thông tin đúng, cha vẫn có tổng hợp đúng và có thể được tính lại bằng `pull` nếu cần.

## 10. Hàm pull: ghép tổng hợp từ hai con

Sau khi cập nhật **một phần** đoạn của nút p, hai nút con đã được sửa tương ứng. Cần tính lại nút cha bằng:

~~~text
sum[p] = sum[left] + sum[right]
min[p] = min(min[left], min[right])
max[p] = max(max[left], max[right])
~~~

Đây là `pull(p)`.

Điểm cần nhớ:

- **Apply:** biến đổi ngay tổng hợp của nút khi đoạn nó bao trùm được cập nhật toàn bộ.
- **Push:** chuyển cập nhật chưa đẩy từ cha xuống con khi phải đi sâu.
- **Pull:** tổng hợp thông tin từ hai con sau khi cập nhật một phần.

Mọi thao tác cập nhật đoạn có cấu trúc:

~~~text
update(p, nodeSegment, querySegment, operation):
    if querySegment covers nodeSegment:
        apply(operation, p)
        return

    push(p)
    update(children that overlap)
    pull(p)
~~~

Nếu quên `pull`, truy vấn trọn đoạn của cha sau một cập nhật một phần có thể đọc **tổng/min/max cũ**.

## 11. Cập nhật đoạn với lazy propagation

Giả sử cần cộng d trên đoạn [ql,qr], đang đứng ở nút p bao phủ [L,R].

**Trường hợp 1 — bao trọn:**

\[
ql\le L\quad\text{và}\quad R\le qr.
\]

Áp dụng `applyAdd(p,L,R,d)` và dừng, không đi sâu.

**Trường hợp 2 — chỉ giao một phần:**

1. Gọi `push(p,L,R)`.
2. Tính \(M=\lfloor(L+R)/2\rfloor\).
3. Nếu ql≤M, cập nhật con trái.
4. Nếu qr>M, cập nhật con phải.
5. Gọi `pull(p)`.

Lệnh **range assign** có cấu trúc đệ quy hoàn toàn tương tự, chỉ thay `applyAdd` bằng `applySet` ở nút bao trọn.

### Giải thích cận O(log n)

Mỗi nút được đi xuống chỉ khi đoạn cập nhật cần xử lý một phần con; các nút bao trọn được xử lý **ngay tại đó**.

Một đoạn liên tiếp [ql,qr] phân rã thành O(log n) nút bao trọn chuẩn và O(log n) nút biên trên các đường từ gốc xuống hai đầu ql,qr. Do đó số nút thăm trong một cập nhật là O(log n), không phải O(r−l+1).

Mỗi nút dùng O(1) thao tác tổng hợp/tag, nên:

\[
\boxed{T_{\text{range update}}=O(\log n).}
\]

Cận này **giả sử tag có thể hợp thành trong O(1)** và các giá trị số học nằm trong một số word máy. Nếu mỗi tag chứa một cấu trúc phức tạp hoặc phép toán BigInteger nhiều bit, cần tính thêm chi phí tương ứng.

## 12. Truy vấn tổng/min/max theo đoạn

Truy vấn \([ql,qr]\) cũng đi qua segment tree:

- Nếu nút p nằm **trọn** trong đoạn truy vấn, trả ngay bộ tổng hợp \((sum[p],min[p],max[p])\).
- Nếu chỉ giao một phần, **push** để con được cập nhật đúng rồi lấy kết quả của những con giao với truy vấn.
- Gộp hai kết quả bằng \((sum_A+sum_B,\min(min_A,min_B),\max(max_A,max_B))\).

Khi một truy vấn hoàn toàn nằm trong con trái, chỉ cần hỏi con trái. Tương tự cho con phải. Nếu truy vấn cắt qua M thì hỏi cả hai rồi ghép.

Mã giả:

~~~text
query(p, L, R, ql, qr):
    if ql <= L and R <= qr:
        return (sum[p], min[p], max[p])

    push(p,L,R)
    M = floor((L+R)/2)

    if qr <= M:
        return query(left, L,M, ql,qr)

    if ql > M:
        return query(right,M+1,R, ql,qr)

    leftStats  = query(left, L,M, ql,qr)
    rightStats = query(right,M+1,R, ql,qr)
    return merge(leftStats,rightStats)
~~~

**Độ phức tạp:** O(log n) trong trường hợp xấu.

### Vì sao truy vấn cũng có thể thay đổi cấu trúc lưu?

Một lời gọi `query` có thể **push thẻ từ cha xuống con**. Do đó mảng `lazy` và tổng hợp nội bộ có thể thay đổi, nhưng **mảng logic mà cây biểu diễn không thay đổi**.

Chính vì vậy lời gọi query không nhất thiết là thao tác “read-only” với cấu trúc nội bộ. Nếu triển khai đa luồng, không thể coi `query` dạng có push là tự động an toàn để chạy đồng thời với các thao tác khác. Cần khóa, snapshot, phiên bản bất biến hoặc thiết kế đồng bộ phù hợp.

## 13. Ví dụ hỗ trợ cả ADD và SET qua nhiều bước

Mảng đầu:

~~~text
index:  0   1   2   3   4   5
value:  5  -2   7   1   4   0
~~~

Thực hiện lần lượt:

| Bước | Lệnh | Mảng logic sau lệnh | sum cả mảng | min | max |
|---:|---|---|---:|---:|---:|
| 0 | Ban đầu | [5,-2,7,1,4,0] | 15 | -2 | 7 |
| 1 | add(1,4,+3) | [5,1,10,4,7,0] | 27 | 0 | 10 |
| 2 | assign(2,5,-1) | [5,1,-1,-1,-1,-1] | 2 | -1 | 5 |
| 3 | add(3,5,+4) | [5,1,-1,3,3,3] | 14 | -1 | 5 |
| 4 | assign(0,3,2) | [2,2,2,2,3,3] | 14 | 2 | 3 |
| 5 | add(1,2,-5) | [2,-3,-3,2,3,3] | 4 | -3 | 3 |

Sau toàn bộ cập nhật:

\[
a=[2,-3,-3,2,3,3].
\]

Truy vấn đoạn \([1,4]\) gồm \([-3,-3,2,3]\):

\[
sum=-1,\quad min=-3,\quad max=3.
\]

Truy vấn \([5,5]\) gồm duy nhất giá trị 3:

\[
sum=min=max=3.
\]

### Đoạn có độ dài 1

Với \([i,i]\), độ dài là 1. Cập nhật cộng thay tổng/min/max của lá thêm d; cập nhật gán đặt cả ba trường bằng v. Không được push từ lá xuống những “con” không tồn tại.

### Cập nhật toàn mảng

Với \([0,n-1]\), đoạn cập nhật bao trọn nút gốc. Một phép gán hoặc cộng có thể cập nhật tổng hợp ở **nút gốc ngay lập tức**, chưa cần đụng tới các lá. Khi hỏi một đoạn con về sau, tag mới được đẩy xuống đường đi cần thiết.

## 14. Sơ đồ trạng thái tag trong một nút

Có thể nhìn tag như một **hàm biến đổi đang chờ**.

Giả sử nút p trước đó đại diện các phần tử:

~~~text
[2, 5, 8, 11]
~~~

Thực hiện:

~~~text
assign(all, 7)
add(all, 3)
~~~

Sau lệnh assign:

~~~text
sum[p] = 28
min[p] = 7
max[p] = 7
hasSet[p] = true
setValue[p] = 7
addValue[p] = 0
~~~

Sau lệnh add:

~~~text
sum[p] = 40
min[p] = 10
max[p] = 10
hasSet[p] = true
setValue[p] = 10
addValue[p] = 0
~~~

Nếu một truy vấn hỏi **toàn đoạn**, có thể trả sum=40 ngay.

Nếu truy vấn hỏi **phần tử thứ hai**, cần push `SET(10)` xuống hai con, sau đó đi tiếp tới lá. Cả cây khi được đồng bộ đầy đủ sẽ đại diện:

~~~text
[10, 10, 10, 10]
~~~

### Thứ tự ngược lại

~~~text
add(all, 3)
assign(all, 7)
~~~

Trạng thái cuối phải là:

~~~text
[7, 7, 7, 7]
~~~

Tag cuối là SET(7), **không** phải SET(10). Nếu chương trình lưu riêng `lazyAdd=3` rồi push sau `SET(7)` một cách không đúng thời gian, kết quả sai.

## 15. Cây đoạn với tag là một kiểu “đại số phép cập nhật”

Để tổng quát hóa, có thể coi:

- **Tổng hợp nút** là một đối tượng có phép gộp kết hợp (*associative merge*) — ví dụ tổng, min, max.
- **Thẻ cập nhật** là một phép biến đổi tác động đồng đều lên mọi phần tử của đoạn.
- Có một hàm **applyTagToAggregate(tag, aggregate, len)**.
- Có một hàm **compose(newTag, oldTag)** bảo đảm thứ tự thời gian.

Khi hai thẻ khác nhau không giao hoán, `compose` phải được định nghĩa cẩn thận: **thẻ mới được áp dụng sau thẻ cũ**.

Ví dụ, với phép biến đổi affine:

\[
x\longmapsto ax+b,
\]

hợp thành \((a_2,b_2)\) sau \((a_1,b_1)\) cho:

\[
\boxed{(a_2a_1,\ a_2b_1+b_2).}
\]

Tổng đoạn dài len biến đổi:

\[
sum'=a\cdot sum+b\cdot len.
\]

Trường hợp:

- ADD(d) tương ứng \(a=1,b=d\).
- SET(v) tương ứng \(a=0,b=v\).

Do đó hỗ trợ đồng thời ADD và SET là một **trường hợp riêng của lazy affine transformations**.

Tuy nhiên, để cập nhật min/max dưới phép affine bất kỳ, nếu a âm thì thứ tự lớn/nhỏ đảo ngược; phải hoán đổi vai trò của min và max trong công thức. Bài chỉ cài **ADD và SET**, không khẳng định hỗ trợ phép nhân hay affine tổng quát.

## 16. Java 17+: cây đoạn cộng/gán, truy vấn sum/min/max

Chương trình **LazyPropagationRangeUpdatesDemo.java** dưới đây là một tệp Java độc lập. Nó có:

- `SegmentTree` xây từ `long[]` nguồn và không sửa mảng nguồn.
- `rangeAdd(l,r,delta)` và `rangeAssign(l,r,value)` với đoạn **đóng, 0-based**.
- `rangeQuery(l,r)` trả bản ghi `Stats(sum,min,max)`.
- Ba thẻ `hasSet`, `setTag`, `addTag`, có quy tắc hợp thành **gán ghi đè** và **cộng sau gán**.
- `Math.addExact` và `Math.multiplyExact` để **báo lỗi tràn long** thay vì im lặng wrap-around.
- Kiểm tra mảng rỗng, chỉ số ngoài biên và đoạn đảo chiều.
- So sánh thuật toán với **mảng thường**: 4.980 cập nhật liệt kê đầy đủ, 28.380 truy vấn nhỏ và 97.500 thao tác ngẫu nhiên từ seed cố định.

Lưu ý: thao tác cập nhật có thể **không có tính nguyên tử** khi gặp lỗi tràn số giữa một đệ quy. Nếu có `ArithmeticException`, bản demo chỉ dùng để báo lỗi và không bảo đảm cây còn hợp lệ để tiếp tục; một thư viện production cần thiết kế kiểm tra trước, rollback hoặc số học độ rộng lớn hơn theo yêu cầu.

~~~java
import java.util.Arrays;
import java.util.Random;

public class LazyPropagationRangeUpdatesDemo {

    record Stats(long sum, long min, long max) {
        static Stats merge(Stats a, Stats b) {
            return new Stats(
                Math.addExact(a.sum(), b.sum()),
                Math.min(a.min(), b.min()),
                Math.max(a.max(), b.max())
            );
        }

        @Override
        public String toString() {
            return "sum=" + sum + ", min=" + min + ", max=" + max;
        }
    }

    static final class SegmentTree {
        private final int n;
        private final long[] sum;
        private final long[] min;
        private final long[] max;

        private final long[] addTag;
        private final long[] setTag;
        private final boolean[] hasSet;

        SegmentTree(long[] input) {
            if (input == null) {
                throw new IllegalArgumentException("input must not be null");
            }
            if (input.length == 0) {
                throw new IllegalArgumentException("array must be nonempty");
            }
            if (input.length > Integer.MAX_VALUE / 4) {
                throw new IllegalArgumentException(
                    "array too large for 4*n tree allocation"
                );
            }

            n = input.length;
            int capacity = 4 * n;
            sum = new long[capacity];
            min = new long[capacity];
            max = new long[capacity];
            addTag = new long[capacity];
            setTag = new long[capacity];
            hasSet = new boolean[capacity];

            build(1, 0, n - 1, input);
        }

        private void build(int node, int left, int right,
                           long[] input) {
            if (left == right) {
                sum[node] = input[left];
                min[node] = input[left];
                max[node] = input[left];
                return;
            }

            int mid = left + (right - left) / 2;
            build(node * 2, left, mid, input);
            build(node * 2 + 1, mid + 1, right, input);
            pull(node);
        }

        private void pull(int node) {
            int lc = node * 2;
            int rc = lc + 1;

            sum[node] = Math.addExact(sum[lc], sum[rc]);
            min[node] = Math.min(min[lc], min[rc]);
            max[node] = Math.max(max[lc], max[rc]);
        }

        private void applyAssign(int node, int left, int right,
                                 long value) {
            long length = (long) right - left + 1L;
            long updatedSum = Math.multiplyExact(value, length);

            sum[node] = updatedSum;
            min[node] = value;
            max[node] = value;

            hasSet[node] = true;
            setTag[node] = value;
            addTag[node] = 0L;
        }

        private void applyAdd(int node, int left, int right,
                              long delta) {
            long length = (long) right - left + 1L;

            // Calculate before assigning: avoid partial node writes.
            long updatedSum = Math.addExact(
                sum[node],
                Math.multiplyExact(delta, length)
            );
            long updatedMin = Math.addExact(min[node], delta);
            long updatedMax = Math.addExact(max[node], delta);

            if (hasSet[node]) {
                long newSet = Math.addExact(setTag[node], delta);
                sum[node] = updatedSum;
                min[node] = updatedMin;
                max[node] = updatedMax;
                setTag[node] = newSet;
            } else {
                long newAdd = Math.addExact(addTag[node], delta);
                sum[node] = updatedSum;
                min[node] = updatedMin;
                max[node] = updatedMax;
                addTag[node] = newAdd;
            }
        }

        private void push(int node, int left, int right) {
            if (left == right) {
                return;
            }

            int mid = left + (right - left) / 2;
            int lc = node * 2;
            int rc = lc + 1;

            // Older pending SET must be applied before newer ADD.
            if (hasSet[node]) {
                applyAssign(lc, left, mid, setTag[node]);
                applyAssign(rc, mid + 1, right, setTag[node]);
                hasSet[node] = false;
                setTag[node] = 0L;
            }

            if (addTag[node] != 0L) {
                applyAdd(lc, left, mid, addTag[node]);
                applyAdd(rc, mid + 1, right, addTag[node]);
                addTag[node] = 0L;
            }
        }

        private void validateRange(int left, int right) {
            if (left < 0 || left > right || right >= n) {
                throw new IllegalArgumentException(
                    "invalid inclusive range"
                );
            }
        }

        void rangeAdd(int left, int right, long delta) {
            validateRange(left, right);
            update(1, 0, n - 1, left, right, delta, false);
        }

        void rangeAssign(int left, int right, long value) {
            validateRange(left, right);
            update(1, 0, n - 1, left, right, value, true);
        }

        private void update(int node, int left, int right,
                            int qLeft, int qRight,
                            long value, boolean assign) {
            if (qLeft <= left && right <= qRight) {
                if (assign) {
                    applyAssign(node, left, right, value);
                } else {
                    applyAdd(node, left, right, value);
                }
                return;
            }

            push(node, left, right);
            int mid = left + (right - left) / 2;

            if (qLeft <= mid) {
                update(node * 2, left, mid,
                       qLeft, qRight, value, assign);
            }
            if (qRight > mid) {
                update(node * 2 + 1, mid + 1, right,
                       qLeft, qRight, value, assign);
            }
            pull(node);
        }

        Stats rangeQuery(int left, int right) {
            validateRange(left, right);
            return query(1, 0, n - 1, left, right);
        }

        private Stats query(int node, int left, int right,
                            int qLeft, int qRight) {
            if (qLeft <= left && right <= qRight) {
                return new Stats(
                    sum[node], min[node], max[node]
                );
            }

            push(node, left, right);
            int mid = left + (right - left) / 2;

            if (qRight <= mid) {
                return query(
                    node * 2, left, mid, qLeft, qRight
                );
            }
            if (qLeft > mid) {
                return query(
                    node * 2 + 1, mid + 1, right, qLeft, qRight
                );
            }

            Stats leftStats = query(
                node * 2, left, mid, qLeft, qRight
            );
            Stats rightStats = query(
                node * 2 + 1, mid + 1, right, qLeft, qRight
            );

            return Stats.merge(leftStats, rightStats);
        }
    }

    // Independent, straightforward O(length) query oracle.
    static Stats slowQuery(long[] values, int left, int right) {
        long total = 0L;
        long smallest = Long.MAX_VALUE;
        long largest = Long.MIN_VALUE;

        for (int i = left; i <= right; i++) {
            total = Math.addExact(total, values[i]);
            smallest = Math.min(smallest, values[i]);
            largest = Math.max(largest, values[i]);
        }
        return new Stats(total, smallest, largest);
    }

    static void check(SegmentTree tree, long[] oracle,
                      int left, int right, String label) {
        Stats got = tree.rangeQuery(left, right);
        Stats expected = slowQuery(oracle, left, right);

        if (!got.equals(expected)) {
            throw new AssertionError(
                label + " range=[" + left + "," + right + "]"
                + " expected=" + expected
                + " actual=" + got
            );
        }
    }

    static void verifyExhaustiveSmall() {
        long updateCases = 0L;
        long queryChecks = 0L;
        long[] updateValues = {-3L, 0L, 3L};

        // Every array length 1..3 with values from {-2,-1,0,1,2}.
        for (int n = 1; n <= 3; n++) {
            int patterns = 1;
            for (int i = 0; i < n; i++) {
                patterns *= 5;
            }

            for (int code = 0; code < patterns; code++) {
                int state = code;
                long[] initial = new long[n];

                for (int i = 0; i < n; i++) {
                    initial[i] = (state % 5) - 2;
                    state /= 5;
                }

                for (int left = 0; left < n; left++) {
                    for (int right = left; right < n; right++) {
                        for (int mode = 0; mode < 2; mode++) {
                            for (long value : updateValues) {
                                SegmentTree tree =
                                    new SegmentTree(initial);
                                long[] oracle = initial.clone();

                                if (mode == 0) {
                                    tree.rangeAdd(left, right, value);
                                    for (int i = left; i <= right; i++) {
                                        oracle[i] += value;
                                    }
                                } else {
                                    tree.rangeAssign(left, right, value);
                                    for (int i = left; i <= right; i++) {
                                        oracle[i] = value;
                                    }
                                }

                                for (int ql = 0; ql < n; ql++) {
                                    for (int qr = ql; qr < n; qr++) {
                                        check(
                                            tree, oracle, ql, qr,
                                            "exhaustive"
                                        );
                                        queryChecks++;
                                    }
                                }
                                updateCases++;
                            }
                        }
                    }
                }
            }
        }

        System.out.println(
            "Exhaustive one-update checks: PASS ("
            + updateCases + " updates, "
            + queryChecks + " queries)"
        );
    }

    static void verifyRandomSequences() {
        Random random = new Random(502L);
        int cases = 650;
        int operations = 150;

        for (int test = 0; test < cases; test++) {
            int n = 1 + random.nextInt(24);
            long[] source = new long[n];
            for (int i = 0; i < n; i++) {
                source[i] = random.nextInt(101) - 50;
            }

            long[] original = source.clone();
            long[] oracle = source.clone();
            SegmentTree tree = new SegmentTree(source);

            for (int step = 0; step < operations; step++) {
                int left = random.nextInt(n);
                int right = random.nextInt(n);

                if (left > right) {
                    int temp = left;
                    left = right;
                    right = temp;
                }

                int mode = random.nextInt(5);
                if (mode == 0) {
                    long delta = random.nextInt(61) - 30;
                    tree.rangeAdd(left, right, delta);
                    for (int i = left; i <= right; i++) {
                        oracle[i] += delta;
                    }
                } else if (mode == 1) {
                    long value = random.nextInt(101) - 50;
                    tree.rangeAssign(left, right, value);
                    for (int i = left; i <= right; i++) {
                        oracle[i] = value;
                    }
                } else {
                    check(tree, oracle, left, right, "random");
                }

                if (step % 17 == 0) {
                    check(tree, oracle, 0, n - 1, "global");
                    for (int i = 0; i < n; i++) {
                        check(tree, oracle, i, i, "point");
                    }
                }
            }

            if (!Arrays.equals(source, original)) {
                throw new AssertionError(
                    "constructor/update mutated source"
                );
            }
        }

        System.out.println(
            "Random operation sequences: PASS ("
            + cases + " cases x " + operations + " operations)"
        );
    }

    static void printStats(String label,
                           SegmentTree tree, int left, int right) {
        System.out.println(
            label + ": " + tree.rangeQuery(left, right)
        );
    }

    public static void main(String[] args) {
        long[] source = {5, -2, 7, 1, 4, 0};
        SegmentTree tree = new SegmentTree(source);

        printStats("Initial [0,5]", tree, 0, 5);

        tree.rangeAdd(1, 4, 3);
        printStats("After add [1,4] by 3", tree, 0, 5);

        tree.rangeAssign(2, 5, -1);
        printStats("After assign [2,5] to -1", tree, 0, 5);

        tree.rangeAdd(3, 5, 4);
        printStats("After add [3,5] by 4", tree, 0, 5);

        tree.rangeAssign(0, 3, 2);
        printStats("After assign [0,3] to 2", tree, 0, 5);

        tree.rangeAdd(1, 2, -5);
        printStats("After add [1,2] by -5", tree, 0, 5);

        printStats("Query [1,4]", tree, 1, 4);
        printStats("Query [5,5]", tree, 5, 5);

        long[] finalArray = new long[source.length];
        for (int i = 0; i < finalArray.length; i++) {
            finalArray[i] = tree.rangeQuery(i, i).sum();
        }
        System.out.println(
            "Final array: " + Arrays.toString(finalArray)
        );

        try {
            tree.rangeQuery(-1, 3);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid range rejected: " + e.getMessage()
            );
        }

        try {
            new SegmentTree(new long[0]);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Empty input rejected: " + e.getMessage()
            );
        }

        verifyExhaustiveSmall();
        verifyRandomSequences();
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 LazyPropagationRangeUpdatesDemo.java
java LazyPropagationRangeUpdatesDemo
~~~

**Stdout dự kiến:**

~~~text
Initial [0,5]: sum=15, min=-2, max=7
After add [1,4] by 3: sum=27, min=0, max=10
After assign [2,5] to -1: sum=2, min=-1, max=5
After add [3,5] by 4: sum=14, min=-1, max=5
After assign [0,3] to 2: sum=14, min=2, max=3
After add [1,2] by -5: sum=4, min=-3, max=3
Query [1,4]: sum=-1, min=-3, max=3
Query [5,5]: sum=3, min=3, max=3
Final array: [2, -3, -3, 2, 3, 3]
Invalid range rejected: invalid inclusive range
Empty input rejected: array must be nonempty
Exhaustive one-update checks: PASS (4980 updates, 28380 queries)
Random operation sequences: PASS (650 cases x 150 operations)
~~~

### Nội dung của hai bài kiểm thử

**Exhaustive:** xây mọi mảng độ dài n=1..3 có giá trị trong \{-2,-1,0,1,2\}. Với mỗi mảng, xét mọi đoạn cập nhật và thử sáu hành động:

- Cộng d bằng −3, 0, hoặc 3.
- Gán v bằng −3, 0, hoặc 3.

Sau **mỗi cập nhật độc lập trên một cây mới**, so sánh sum/min/max của **mọi đoạn truy vấn có thể có** với oracle mảng thường. Số trường hợp cập nhật là:

\[
\begin{aligned}
&5^1\cdot1\cdot6
+5^2\cdot3\cdot6
+5^3\cdot6\cdot6\\
&=30+450+4500=\boxed{4980}.
\end{aligned}
\]

Số truy vấn đã so:

\[
30\cdot1+450\cdot3+4500\cdot6
=\boxed{28380}.
\]

**Random sequences:** với seed `502L`, sinh 650 mảng độ dài 1..24. Mỗi mảng nhận 150 thao tác xen kẽ cập nhật và truy vấn, tổng cộng:

\[
\boxed{650\cdot150=97500\text{ thao tác}.}
\]

Sau những mốc định kỳ, kiểm cả toàn đoạn và từng điểm; sau mỗi bộ thử xác nhận mảng đầu vào **không bị thay đổi**. Các phép tính giới hạn trong những số nhỏ để tập trung tìm lỗi logic thẻ và cấu trúc cây, không cố tạo overflow.

### Giá trị của hai loại kiểm thử

Bộ exhaustive chứng minh đúng trên **toàn bộ không gian nhỏ đã liệt kê** cho một lần cập nhật. Bộ ngẫu nhiên bổ sung các **chuỗi cập nhật chồng lấn nhiều bước**, nơi phép hợp thành SET/ADD phức tạp và lỗi chỉ lộ sau vài truy vấn đẩy thẻ xuống.

Tuy vậy, kiểm thử hữu hạn **không thay thế chứng minh đúng tổng quát** dựa trên bất biến của node, phép hợp thành tag và quy nạp theo cây.

## 17. Phân tích từng đoạn quan trọng của mã Java

### A. Stats là một record bất biến

`Stats(sum,min,max)` gói ba kết quả của đoạn. Hàm `merge` gộp hai đoạn kề nhau:

\[
(sum_A+sum_B,\ \min(min_A,min_B),\ \max(max_A,max_B)).
\]

Hàm `toString()` chỉ phục vụ in ví dụ dễ đọc. Record giúp các kiểm thử dùng `equals` để so cả ba giá trị, tránh bỏ quên một trường.

### B. Không sửa mảng nguồn

Constructor đọc các giá trị từ `input` để xây nút lá, không ghi lại `input[i]`. Các phép cập nhật chỉ sửa những mảng lưu cây.

Do đó nếu caller giữ lại `long[] source` rồi gọi `rangeAdd`, giá trị trong `source` **vẫn như cũ**. Muốn lấy ảnh chụp trạng thái logic mới, có thể gọi truy vấn từng điểm, hoặc bổ sung một hàm xuất mảng O(n).

### C. applyAssign luôn xóa lazyAdd

Một lệnh gán mới sẽ ghi đè mọi phép cộng cũ đối với đoạn. `applyAssign` phải:

~~~text
hasSet[node] = true
setTag[node] = value
addTag[node] = 0
~~~

Nếu quên `addTag=0`, sau này push có thể áp lại phép cộng **trước phép gán**, khiến thứ tự thời gian bị đảo và kết quả sai.

### D. applyAdd cập nhật tag phù hợp

Nếu `hasSet[node]=true`, cộng mới phải được cộng vào **setTag**, không cộng vào `addTag` độc lập nếu thiết kế chỉ cho một dạng tag đã chuẩn hóa.

Nếu `hasSet=false`, cộng vào `addTag`. Hai trường hợp vẫn cập nhật ngay sum/min/max của nút.

### E. push trước khi đi xuống

Nếu nút p bao phủ trọn một cập nhật cũ, tổng hợp p đã được sửa nhưng hai con có thể còn cũ. Khi truy vấn hay cập nhật **một phần**, phải `push` trước khi đọc/sửa con.

Nếu quên, các phép biến đổi cũ có thể bị mất, hoặc khi pull lại sẽ lấy tổng hợp từ những con cũ và ghi sai lên cha.

### F. pull sau cập nhật một phần

`pull` bảo đảm tổng hợp của cha bằng gộp hai con sau khi các thay đổi liên quan đã được xử lý. Không cần pull khi toàn đoạn được cập nhật bằng `apply` và trả ngay.

### G. query có thể push nhưng không đổi mảng logic

Do một truy vấn bộ phận có thể đẩy thẻ, trạng thái các mảng lưu cây có thể thay đổi ngay cả khi không gọi rangeAdd hay rangeAssign. Đó là hành vi bình thường của lazy propagation.

### H. Kiểm tràn số

Java `long` có giới hạn; tính `delta*length` có thể tràn trước khi cộng vào sum. Mã dùng `Math.multiplyExact` rồi `Math.addExact` để phát hiện.

Đây là ví dụ giáo dục **không bảo đảm rollback** nếu lỗi xảy ra giữa cập nhật một phần. Nếu áp dụng trong hệ thống giao dịch, cần bảo đảm tính nguyên tử hoặc precheck theo thiết kế riêng.

## 18. Chứng minh tính đúng bằng quy nạp

Ta chứng minh đồng thời cho các tổng hợp tại nút và tag.

**Bất biến I — tổng hợp đúng:** Với mọi nút p đại diện [L,R], `sum[p]`, `min[p]`, `max[p]` là tổng/nhỏ nhất/lớn nhất của **mảng logic sau tất cả cập nhật đã nhận** trên đoạn [L,R].

**Bất biến II — thẻ biểu diễn phần chưa đồng bộ:** Nếu p còn tag, con của p chưa chắc đã nhận phép biến đổi ấy. Áp dụng `push` sẽ làm con đúng mà không làm thay đổi trạng thái logic.

### Cơ sở: build

Ở lá L=R, ba tổng hợp đều bằng a[L]. Ở nút trong, nếu hai con đúng thì `pull` cho tổng/min/max đúng trên hợp hai đoạn. Ban đầu mọi tag đều rỗng, nên I và II đúng.

### Bước quy nạp: cập nhật bao trọn

Nếu cập nhật \([ql,qr]\) bao trọn [L,R]:

- Với ADD(d), công thức `sum+d·len`, `min+d`, `max+d` đúng vì tất cả phần tử đều tăng d.
- Với SET(v), công thức `sum=v·len`, `min=max=v` đúng vì mọi phần tử đều bằng v.

Hàm hợp thành tag tương ứng đúng theo **thứ tự thời gian** nên phần cập nhật chưa đẩy cũng được biểu diễn đúng. Hai bất biến giữ nguyên.

### Bước quy nạp: cập nhật một phần

Nếu cập nhật chỉ tác động một phần nút:

1. `push` đồng bộ các con, giữ nguyên mảng logic.
2. Đệ quy xử lý những con giao với đoạn, theo giả thiết quy nạp chúng có tổng hợp đúng.
3. `pull` gộp hai con, cho tổng hợp của cha đúng.

Vậy hai bất biến còn đúng sau cập nhật.

### Bước quy nạp: truy vấn

Nếu nút được bao trọn, trả tổng hợp đúng theo I.

Nếu chỉ giao một phần, `push` bảo đảm các con chính xác rồi đệ quy. Kết quả từ một hoặc hai con được gộp đúng do tổng là phép cộng kết hợp, min/max là phép min/max kết hợp trên các đoạn rời nhau.

Do đó mọi truy vấn trả **đúng sum/min/max của đoạn** sau toàn bộ cập nhật trước đó.

### Mấu chốt không được bỏ qua

Bằng chứng phụ thuộc việc:

- Tag ADD và SET được **hợp thành đúng thứ tự**.
- Tổng hợp được **apply ngay** tại nút bao trọn.
- **Push trước** truy cập sâu.
- **Pull sau** cập nhật một phần.
- Thao tác trên đoạn liên tiếp và có cấu trúc gộp phù hợp.

Nếu thiếu một trong các điều kiện này, cận thời gian O(log n) vẫn có thể đúng nhưng **kết quả không còn đúng**.

## 19. Phân tích độ phức tạp

Giả sử n≥1 và có q lệnh cập nhật/truy vấn.

| Công đoạn | Thời gian | Bộ nhớ phụ |
|---|---:|---:|
| Xây cây từ mảng | O(n) | O(n) |
| Range add | O(log n) | O(log n) stack đệ quy |
| Range assign | O(log n) | O(log n) stack đệ quy |
| Range sum/min/max | O(log n) | O(log n) stack đệ quy |
| Truy vấn một điểm | O(log n) | O(log n) stack |
| Xuất toàn bộ n điểm bằng n truy vấn | O(n log n) | O(n) cho kết quả |
| Xử lý q lệnh bất kỳ | O(n+q log n) tổng | O(n) lưu cây |

Cây dùng năm mảng `long[]`: sum, min, max, addTag, setTag; và một mảng boolean hasSet, mỗi mảng kích thước O(n). Vì vậy:

\[
\boxed{\text{Bộ nhớ cây}=O(n).}
\]

Nếu cần xuất cả mảng logic, có thể duyệt toàn bộ cây và đẩy tag xuống các lá trong O(n) thời gian, nhưng ví dụ chọn cách truy vấn từng điểm vì đơn giản; đó là O(n log n).

### Tại sao không là O(log² n)?

Một truy vấn đoạn **không** thực hiện một tìm kiếm log n riêng cho từng nút của O(log n) đường đi; nó duyệt trực tiếp các nút có liên quan trong một lần đệ quy. Tổng số nút gặp là O(log n) đối với một đoạn liên tiếp, nên thời gian O(log n).

Một số bài toán phức tạp hơn khi mỗi nút còn chứa cấu trúc cần truy vấn O(log n) có thể có O(log² n), nhưng đó **không** phải chi phí của cây đoạn tổng/min/max với tag ADD/SET này.

## 20. Trường hợp biên cần xử lý

| Trường hợp | Hành vi đúng |
|---|---|
| n=1 | Cây chỉ có một lá; query/update vẫn đúng |
| n=0 | Mã Java từ chối vì min/max trên đoạn không tồn tại |
| \([l,r]=[0,n-1]\) | Cập nhật bao trọn gốc, không cần xuống lá ngay |
| \([l,r]=[i,i]\) | Chỉ một phần tử |
| ADD(0) | Không đổi giá trị; có thể giữ hoặc tối ưu bỏ thẻ |
| SET(0) | Phải thực hiện thật; không được coi là không có tag |
| ADD số âm | sum/min/max cùng giảm tương ứng |
| SET số âm | sum=value·len, min=max=value |
| Nhiều ADD chồng nhau | Cộng tổng các delta đúng thứ tự |
| SET rồi ADD | Gộp thành SET(v+d) |
| ADD rồi SET | Chỉ giữ SET mới |
| SET rồi SET | SET mới nhất thắng |
| Đoạn rời nhau | Các phần không giao phải giữ nguyên |
| Chỉ số âm, lớn hơn n−1 | Ném lỗi phạm vi |
| l>r | Ném lỗi, không tự swap trong API |
| Tổng phép cộng vượt long | Phải phát hiện hoặc dùng kiểu rộng hơn |
| Query sau nhiều cập nhật chưa push | Phải trả đúng nhờ apply tổng hợp và push khi cần |
| Phạm vi toàn đoạn có nhiều phép gán/cộng | Tag hợp thành tương đương thứ tự lệnh thật |

### Lưu ý về cập nhật chồng lấn

Ví dụ:

~~~text
a = [0,0,0,0]
add(0,3,5)       -> [5,5,5,5]
assign(1,2,1)    -> [5,1,1,5]
add(2,3,-2)      -> [5,1,-1,3]
~~~

Nếu bỏ push trước khi gán [1,2], các con có thể chưa biết phép cộng +5 của gốc, và tổng hợp sau pull sẽ sai.

### Không có “trạng thái rỗng” cho truy vấn hợp lệ

Mã chỉ nhận \([l,r]\) với l≤r. Do vậy một `Stats` luôn đại diện **ít nhất một phần tử**, không cần tạo identity với `min=+\infty` và `max=-\infty` ở API công khai.

Nếu muốn hỗ trợ đoạn rỗng, phải định nghĩa rõ sum/min/max của đoạn rỗng theo yêu cầu nghiệp vụ và sửa hàm truy vấn cho nhất quán.

## 21. So sánh với Fenwick Tree và Difference Array

| Nhu cầu | Lựa chọn thường phù hợp | Ghi chú |
|---|---|---|
| Cộng nhiều đoạn rồi lấy mảng cuối | Difference array | O(1) mỗi cập nhật, O(n) quét cuối; ngoại tuyến |
| Truy vấn tổng tiền tố, cập nhật một điểm | Fenwick Tree | O(log n), cấu trúc gọn |
| Cộng trên đoạn và truy vấn tổng đoạn | Hai Fenwick Tree hoặc lazy segment tree | Cả hai có thể O(log n) |
| Gán trên đoạn và cộng trên đoạn xen kẽ | Lazy segment tree | Tag composition SET/ADD thuận tiện |
| Cộng trên đoạn và truy vấn min/max | Lazy segment tree | Aggregate min/max phản ứng O(1) với ADD |
| Gán trên đoạn và truy vấn tổng/min/max | Lazy segment tree | APPLY SET thay nguyên tổng hợp |
| Chỉ truy vấn trên mảng không đổi | Prefix sum, sparse table, segment tree tùy phép toán | Không nhất thiết cần lazy |
| Điểm cập nhật và đoạn truy vấn | Segment tree thông thường | Lazy không bắt buộc |
| Miền tọa độ rất lớn nhưng điểm thưa | Dynamic/sparse segment tree | Cấp phát nút khi cần, vẫn phải phân tích giới hạn |
| Yêu cầu nhiều phiên bản lịch sử | Persistent segment tree với tag thích hợp | Thiết kế phức tạp hơn, không tự có từ bản hiện tại |

**Difference array** có lợi thế lớn nếu mọi cập nhật được gom trước và không cần trả lời truy vấn giữa chừng. **Fenwick Tree** gọn khi chỉ cần cộng và tổng. Cây đoạn lazy trở nên đặc biệt hữu ích khi cần **nhiều loại tổng hợp và nhiều kiểu cập nhật đoạn**.

### Không phải thao tác nào cũng có tag O(1)

Một tag ADD áp dụng cho sum/min/max rất gọn. Nhưng nếu muốn vừa **lấy min với một ngưỡng** (range chmin), vừa hỏi tổng đoạn, cập nhật \(\min(a_i,x)\) không thể suy ra tổng mới chỉ từ \((sum,min,max)\) trong mọi trường hợp.

Những bài phức tạp có thể cần **segment tree beats**, thêm thông tin như max thứ hai và số lần max, hoặc cấu trúc khác. Không nên dùng công thức ADD/SET như một “mẫu thần kỳ” cho mọi phép cập nhật.

## 22. Những lỗi thường gặp

1. **Quên cập nhật sum/min/max ngay trong apply**, khiến truy vấn bao trọn đoạn trả số cũ.
2. **Push mà cộng thêm một lần nữa vào tổng hợp cha**, cập nhật lặp.
3. **Quên push trước khi truy cập một phần nút**, đọc trạng thái con còn cũ.
4. **Quên pull sau cập nhật một phần**, tổng hợp cha không phản ánh con.
5. **Dùng `setTag=0` làm dấu hiệu không có SET**, khiến SET(0) bị bỏ.
6. **Giữ addTag cũ khi nhận SET mới**, khiến phép cộng cũ chạy sau phép gán.
7. **Cộng ADD sau SET vào addTag không đúng quy ước hợp thành**, có thể đẩy sai thứ tự.
8. **Gộp ADD rồi SET như SET(v+d)**, trong khi SET mới phải ghi đè.
9. **Gộp SET rồi ADD như SET(v)**, quên cộng d.
10. **Đẩy tag xuống con theo thứ tự sai**, làm lệnh đến sau được áp trước.
11. **Quên xóa thẻ cha sau push**, khiến lần push sau lặp cập nhật.
12. **Gọi push trên lá rồi truy cập con không tồn tại**, lỗi chỉ số/đệ quy.
13. **Tính len bằng R−L thay vì R−L+1**, làm sai tổng sau range update.
14. **Nhầm đoạn đóng [l,r] với đoạn nửa mở [l,r)**, dẫn đến lệch một.
15. **Nhầm chỉ số 0-based với 1-based**, truy vấn/cập nhật sai vị trí.
16. **Không chặn l>r**, dẫn tới cây trả kết quả tùy ý.
17. **Chỉ kiểm sum mà không kiểm min/max**, lỗi apply aggregate bị bỏ sót.
18. **Dùng sentinel Long.MAX_VALUE cho trạng thái rỗng mà không phân biệt giá trị thật**, hỏng nếu dữ liệu có cùng giá trị.
19. **Quên min/max khi SET(v)**, giữ min/max của đoạn trước gán.
20. **Cho rằng ADD âm sẽ đổi min thành max**, trong khi cộng cùng một số giữ thứ tự nên cả min và max đều cộng delta.
21. **Thử update đoạn không giao mà vẫn đi xuống cả hai con**, tăng chi phí/lỗi.
22. **Không tính lại cha sau khi update chỉ một con**, tổng hợp sai.
23. **Coi query có push là read-only về mảng nội bộ**, gặp race condition khi chạy đa luồng.
24. **Sử dụng `long` mà không kiểm overflow của delta·len**, có thể wrap-around.
25. **Chỉ kiểm overflow ở tổng cuối thay vì trước phép nhân**, tràn đã xảy ra trước.
26. **Tiếp tục sử dụng cây sau ngoại lệ giữa update mà không rollback**, có thể dùng trạng thái đã sửa một phần.
27. **Cấp phát `new long[4*n]` khi 4*n tràn int**, tạo kích thước âm.
28. **Nhầm O(log n) mỗi thao tác với O(n) cho toàn bộ q lệnh**, quên q log n.
29. **Khẳng định cả cập nhật đoạn và truy vấn đoạn với prefix sum tĩnh đều O(1)**, quên chi phí cập nhật prefix.
30. **Dùng difference array rồi đòi trả lời ngay truy vấn giữa các lần cập nhật**, sai mô hình ngoại tuyến.
31. **Dùng Fenwick một cây cho range assign+sum mà không chứng minh cách triển khai**, bỏ sót phép gán.
32. **Gọi SET và ADD giao hoán**, làm kết quả phụ thuộc thứ tự thực thi sai.
33. **Chỉ test một cập nhật mỗi lần**, bỏ sót lỗi hợp thành khi lệnh chồng lấn.
34. **Chỉ test mảng dương**, bỏ sót ADD âm và SET âm.
35. **Không test SET(0), ADD(0)**, bỏ qua tình huống tag đặc biệt.
36. **Không kiểm nguyên mảng nguồn còn nguyên**, vi phạm hợp đồng của wrapper.
37. **Không phân biệt tổng hợp node đã đúng với con chưa đồng bộ**, hiểu sai bản chất lazy.
38. **Cho rằng mọi phép cập nhật đều có thể áp lên aggregate O(1)**, áp dụng bừa cho range chmin, gcd hay histogram.
39. **Gán max/min bằng giá trị đầu tiên của đoạn mà chưa tính đúng đoạn**, biến truy vấn sai.
40. **Đổi hàm merge từ sum sang min mà quên đổi apply và tag**, phá tính đúng.
41. **Viết công thức cộng delta vào sum mà không nhân len**, sai khi đoạn dài hơn 1.
42. **Quên rằng khi query chỉ cắt qua một con không cần hỏi con còn lại**, gây tính toán thừa hoặc tạo Stats rỗng.
43. **Gộp các thống kê từ hai đoạn giao nhau**, đếm trùng phần tử.
44. **Không giới hạn quyền cập nhật với vùng chỉ số hợp lệ**, có thể đọc ngoài mảng.
45. **Đánh giá chỉ tốc độ bằng input nhỏ rồi khẳng định không có lỗi**, thiếu chứng minh bất biến và kiểm thử chuỗi nhiều bước.

## 23. Bài tập và câu hỏi tự luyện

**Bài 1.** Cây đoạn với lazy propagation dùng để giải quyết khó khăn nào?

*Đáp án:* Cập nhật cả đoạn liên tiếp mà không cần sửa từng phần tử ngay, trong khi vẫn trả lời được truy vấn đoạn xen kẽ.

**Bài 2.** Nút p đại diện đoạn [L,R] cần lưu gì khi hỗ trợ sum/min/max?

*Đáp án:* Tổng, giá trị nhỏ nhất và giá trị lớn nhất của đoạn đó.

**Bài 3.** Nếu cộng d vào mọi phần tử của đoạn dài len, sum thay đổi bao nhiêu?

*Đáp án:* **d·len**.

**Bài 4.** Cùng phép cộng trên, min và max thay đổi thế nào?

*Đáp án:* Cùng cộng **d**.

**Bài 5.** Nếu gán cả đoạn bằng v, sum/min/max trở thành gì?

*Đáp án:* \(\boxed{sum=v\cdot len,\ min=max=v}\).

**Bài 6.** Tại sao phải lưu cờ hasSet riêng?

*Đáp án:* Vì SET(0) là phép gán hợp lệ; không thể dùng 0 làm dấu hiệu không có tag.

**Bài 7.** SET(3) rồi ADD(4) có thể hợp thành gì?

*Đáp án:* **SET(7)**.

**Bài 8.** ADD(4) rồi SET(3) có thể hợp thành gì?

*Đáp án:* **SET(3)**.

**Bài 9.** ADD(2) rồi ADD(−5) có thể hợp thành gì?

*Đáp án:* **ADD(−3)**.

**Bài 10.** SET(9) rồi SET(−1) có thể hợp thành gì?

*Đáp án:* **SET(−1)**.

**Bài 11.** Hàm apply làm việc gì?

*Đáp án:* Cập nhật tổng hợp nút ngay và hợp thành tag còn chờ cho các con.

**Bài 12.** Hàm push làm việc gì?

*Đáp án:* Chuyển thẻ đang chờ từ cha xuống hai con đúng thứ tự, rồi xóa thẻ ở cha.

**Bài 13.** Hàm pull làm việc gì?

*Đáp án:* Gộp sum/min/max của hai con để tính lại nút cha sau cập nhật một phần.

**Bài 14.** Nếu cập nhật bao trọn [L,R] của nút, có phải đi tới tất cả lá không?

*Đáp án:* Không; apply vào nút và ghi tag, kết thúc nhánh đệ quy.

**Bài 15.** Khi truy vấn bao trọn đoạn của nút có tag chưa push, có thể trả ngay tổng hợp nút không?

*Đáp án:* **Có**, vì tổng hợp nút đã được apply chính xác.

**Bài 16.** Khi truy vấn chỉ một phần nút có tag, phải làm gì trước khi đi xuống con?

*Đáp án:* **Push** tag để đồng bộ hai con.

**Bài 17.** Build segment tree mất bao nhiêu thời gian?

*Đáp án:* **O(n)**.

**Bài 18.** Range add và range assign có độ phức tạp bao nhiêu trong thiết kế này?

*Đáp án:* **O(log n)** mỗi thao tác.

**Bài 19.** Range sum/min/max có chi phí bao nhiêu?

*Đáp án:* **O(log n)** cho một đoạn.

**Bài 20.** Với n phần tử và q thao tác, tổng thời gian là gì?

*Đáp án:* \(O(n+q\log n)\).

**Bài 21.** Bộ nhớ cây với các mảng O(4n) là bao nhiêu theo bậc?

*Đáp án:* **O(n)**.

**Bài 22.** Cho [1,2,3,4], add(1,3,+2), mảng thành gì?

*Đáp án:* **[1,4,5,6]**.

**Bài 23.** Tiếp tục assign(0,2,0), mảng thành gì?

*Đáp án:* **[0,0,0,6]**.

**Bài 24.** Tiếp tục query(0,3), sum/min/max là gì?

*Đáp án:* **6, 0, 6**.

**Bài 25.** Nếu muốn cộng vào nhiều đoạn rồi chỉ in mảng sau tất cả cập nhật, có cần segment tree không?

*Đáp án:* Không nhất thiết; **difference array + prefix sum** có thể đơn giản và nhanh hơn.

**Bài 26.** Nếu muốn trả lời truy vấn giữa các lần cập nhật, prefix sum tĩnh có đủ không?

*Đáp án:* Không; phải cập nhật cấu trúc hoặc dùng phương án động như segment tree.

**Bài 27.** Với một đoạn có min=-2,max=8, sau ADD(-5) kết quả min/max?

*Đáp án:* **−7 và 3**.

**Bài 28.** Với đoạn dài 4, sau SET(-3), tổng là gì?

*Đáp án:* **−12**.

**Bài 29.** Vì sao SET và ADD không giao hoán?

*Đáp án:* Vì SET mới xóa giá trị trước đó, còn ADD mới tăng giá trị đã gán.

**Bài 30.** Nếu `Math.multiplyExact` ném lỗi trong range update, mã demo có được coi là đã rollback về trạng thái ban đầu không?

*Đáp án:* **Không**. Ngoại lệ số học không tạo tính nguyên tử cho cả cập nhật; cần thiết kế rollback/validation khác.

**Bài 31.** Tại sao bản test random phải có nhiều lệnh SET và ADD chồng lấn?

*Đáp án:* Để phát hiện lỗi hợp thành thẻ theo thứ tự thời gian mà test một lệnh khó phát hiện.

**Bài 32.** Truy vấn một điểm \([i,i]\) có trả được giá trị hiện tại của a[i] không?

*Đáp án:* Có; cả sum/min/max của đoạn một phần tử đều bằng a[i].

**Bài 33.** Segment tree lazy hiện tại có tự hỗ trợ range chmin+range sum đúng không?

*Đáp án:* Không. Cần tổng hợp/tag khác và có thể cần segment tree beats.

**Bài 34.** Nếu query có push, có thể chạy đồng thời nhiều query mà không đồng bộ trên cùng cây không?

*Đáp án:* Không nên giả định an toàn; query có thể ghi vào cấu trúc nội bộ, nên cần chiến lược đồng bộ phù hợp.

**Bài 35.** Nếu dùng chỉ số 1-based thay cho 0-based, phải thay đổi gì?

*Đáp án:* Phải biến đổi nhất quán các biên và quy tắc chia đoạn, hoặc chuyển input về 0-based trước khi gọi API.

**Tổng kết:** Lazy propagation giúp segment tree thực hiện **cập nhật trên đoạn và truy vấn đoạn trong O(log n)** bằng cách **apply trực tiếp lên tổng hợp của nút bao trọn**, **lưu tag để hoãn việc sửa con**, **push khi cần đi sâu** và **pull khi cập nhật một phần**. Khi hỗ trợ cùng lúc **range assign** và **range add**, phép hợp thành không giao hoán: **SET mới ghi đè thẻ cũ; ADD sau SET trở thành SET(v+d); ADD sau ADD cộng dồn**. Mỗi nút lưu sum/min/max và các tag `hasSet/setTag/addTag`, trong đó cờ riêng cho SET là cần thiết để xử lý **SET(0)**. Chương trình Java 17 minh họa các thao tác trên đoạn đóng 0-based, phép kiểm tràn số, so với mảng chậm qua 4.980 trường hợp cập nhật exhaustive, 28.380 truy vấn và 97.500 thao tác nhiều bước. Phải phân biệt **trạng thái logic đã cập nhật** với **con chưa nhận tag**, và chọn lazy tree khi thực sự cần **truy vấn xen giữa cập nhật**; nếu chỉ cần gom cập nhật ngoại tuyến, các kỹ thuật đơn giản hơn như difference array có thể thích hợp hơn.
