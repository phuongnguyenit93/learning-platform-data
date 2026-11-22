# Truy vấn cập nhật điểm, cập nhật đoạn và truy vấn tổng hợp

## Mục tiêu học tập

Trong nhóm **Truy vấn và ngoại tuyến**, ta thường gặp một dãy số có nhiều thao tác xen kẽ: thay đổi một phần tử, thay đổi tất cả phần tử trong một khoảng, rồi hỏi tổng hoặc cực trị trong khoảng. Khi số phần tử và số truy vấn đều lớn, cách quét lại cả đoạn sau mỗi thao tác có thể vượt thời gian cho phép.

Bài học giải thích cách lựa chọn **prefix sum**, **difference array**, **Fenwick tree** và **segment tree có lazy propagation** cho từng tổ hợp cập nhật–truy vấn. Trọng tâm là phân biệt hai loại cập nhật:

- **Cộng đoạn:** tăng mọi phần tử trên [l,r] một lượng d.
- **Gán đoạn:** thay mọi phần tử trên [l,r] bằng v.

Hai phép này **không giao hoán**; thiết kế lazy tag sai thứ tự làm sai cả sum, min và max.

Kết thúc bài, bạn có thể:

1. Chuẩn hóa chỉ số 0-based và khoảng đóng [l,r], tránh lỗi lệch một vị trí.
2. Chọn cấu trúc cho **point add / point set**, **range add / range assign** và **range sum / min / max**.
3. Hiểu khi nào xử lý **ngoại tuyến** cho phép dùng hiệu và tổng tiền tố thay vì cây.
4. Chứng minh công thức hai Fenwick cho **range add + range sum**.
5. Cài lazy segment tree hỗ trợ **cả cộng lẫn gán đoạn** với truy vấn sum/min/max trong O(log n).
6. Nhận biết ý nghĩa của phép gộp kết hợp (*monoid*) và giới hạn của từng aggregate.
7. Đọc, chạy và đối chiếu chương trình **Java 17+** tự chứa, có stdout đáng tin.
8. Viết kiểm thử mảng đối chứng, kiểm tra ngẫu nhiên, các trường hợp biên và lỗi phổ biến.

---

## 1. Phát biểu bài toán và thống nhất ký hiệu

Cho dãy:

\[
a=[2,1,3,4,5].
\]

Có n phần tử, đánh số `0..n−1`.

Trong toàn bộ bài:

\[
\boxed{0\le l\le r<n}
\]

và ký hiệu **[l,r] chứa cả hai đầu**.

| Tên thao tác | Ý nghĩa |
| --- | --- |
| `pointAdd(i,d)` | `a[i]\gets a[i]+d` |
| `pointSet(i,v)` | `a[i]\gets v` |
| `rangeAdd(l,r,d)` | `a[i]\gets a[i]+d` cho mọi i∈[l,r] |
| `rangeAssign(l,r,v)` | `a[i]\gets v` cho mọi i∈[l,r] |
| `rangeSum(l,r)` | `\sum_{i=l}^{r}a[i]` |
| `rangeMin(l,r)` | `\min_{i=l}^{r}a[i]` |
| `rangeMax(l,r)` | `\max_{i=l}^{r}a[i]` |

**Point add khác point set:** ví dụ a[2]=3, `pointAdd(2,5)` cho 8, trong khi `pointSet(2,5)` cho 5.

**Range add khác range assign:** khi một đoạn có các giá trị [1,3,4], cộng 7 cho [8,10,11], còn gán 7 cho [7,7,7].

### 1.1. Truy vấn tổng hợp (*aggregate query*)

"Truy vấn tổng hợp" nghĩa là gộp một khoảng thành một kết quả theo phép toán xác định, ví dụ:

- Tổng.
- Nhỏ nhất, lớn nhất.
- GCD, XOR, AND/OR.
- Số lượng hoặc tần suất theo một số điều kiện.
- Tích ma trận hay ghép chuỗi trong những bài toán chuyên biệt.

Mỗi phép gộp có quy tắc riêng. Một BIT lưu **tổng** không mặc nhiên trả **min** nhanh, và một lazy tag cho phép cộng đoạn đối với sum/min/max không tự áp dụng đúng cho phép XOR hay GCD.

### 1.2. Tĩnh, online và offline

**Tĩnh:** mảng không đổi sau tiền xử lý; mọi thao tác tiếp theo chỉ là query.

**Online:** update và query có thể xen kẽ, phải trả đúng đáp án theo trạng thái tại thời điểm query.

**Offline:** có thể đọc trước toàn bộ thao tác hoặc hoãn trả lời rồi xử lý lại theo thứ tự phù hợp, miễn không thay đổi ý nghĩa thời gian của từng query.

Ví dụ:

```text
sum(0,4)         -> 15
add(1,3,+2)
sum(0,4)         -> 21
```

Nếu gom update lên đầu rồi trả cả hai query là 21 thì **sai**, dù đã biết trước toàn bộ input. Xử lý ngoại tuyến không có nghĩa được bỏ qua thứ tự ngữ nghĩa.

---

## 2. Mảng trực tiếp: đơn giản nhưng có thể chậm

Với một `long[] a`, ta có:

```text
pointAdd(i,d):         a[i] += d            O(1)
pointSet(i,v):         a[i] = v             O(1)

rangeAdd(l,r,d):       for i=l..r           O(n) worst case
rangeAssign(l,r,v):    for i=l..r           O(n) worst case

rangeSum(l,r):         for i=l..r           O(n) worst case
rangeMin(l,r):         for i=l..r           O(n) worst case
rangeMax(l,r):         for i=l..r           O(n) worst case
```

Nếu n=q=100000, một chuỗi q truy vấn trên cả mảng có thể cần gần:

\[
10^5\cdot10^5=10^{10}
\]

lần đọc hoặc cập nhật phần tử.

Tuy nhiên mảng trực tiếp có một ưu điểm rất lớn: **làm oracle đối chứng trong kiểm thử**. Trên các mảng nhỏ, nó dễ đọc và ít tình huống biên hơn một segment tree lazy. Đừng bỏ phương pháp đơn giản này khỏi bộ kiểm thử.

---

## 3. Prefix sum: tổng đoạn tĩnh O(1)

Đặt mảng tiền tố `pref` dài n+1:

\[
\boxed{
pref[0]=0,\qquad pref[i+1]=pref[i]+a[i].
}
\]

Từ đó:

\[
\boxed{sum(l,r)=pref[r+1]-pref[l].}
\]

### 3.1. Ví dụ

```text
a     = [2,1,3,4,5]
pref  = [0,2,3,6,10,15]
```

Tổng đoạn [1,3]:

\[
a[1]+a[2]+a[3]=1+3+4=8,
\]

\[
pref[4]-pref[1]=10-2=\boxed{8}.
\]

Vì `pref[r+1]` cộng 0..r còn `pref[l]` cộng 0..l−1, phần hiệu còn đúng l..r.

### 3.2. Chi phí

- Xây prefix: O(n).
- Bộ nhớ: O(n).
- Mỗi query tổng: O(1).
- Khi cập nhật a[i], mọi prefix từ `pref[i+1]` tới `pref[n]` có thể thay đổi: O(n) nếu duy trì ngây thơ.

**Sai lầm:** Dùng prefix đã xây trước rồi tiếp tục hỏi tổng như dữ liệu không thay đổi sau khi cập nhật. Prefix tĩnh **không tự đồng bộ** với các update.

### 3.3. Prefix cho tổng, không cho mọi aggregate

Lấy hiệu hai tổng tiền tố dựa vào phép nghịch đảo của cộng (trừ). Với min, không có công thức chung:

```text
min(l,r) = minPrefix(r) - minPrefix(l-1)
```

Công thức đó **không tồn tại** theo nghĩa thông thường. Nếu query min tĩnh rất nhiều, sparse table có thể phù hợp hơn.

---

## 4. Difference array: cộng đoạn O(1) khi biết trước toàn bộ cập nhật

Định nghĩa sai phân:

\[
d[0]=a[0],\qquad d[i]=a[i]-a[i-1]\quad(i>0).
\]

Khôi phục:

\[
\boxed{a[i]=\sum_{j=0}^{i}d[j].}
\]

Muốn cộng v vào toàn bộ [l,r]:

\[
\boxed{d[l]\mathrel{+}=v}
\]

và nếu `r+1<n`:

\[
\boxed{d[r+1]\mathrel{-}=v.}
\]

### 4.1. Chứng minh

Tại vị trí l, tổng tiền tố d bắt đầu tăng v. Từ l tới r, nó giữ mức tăng v. Ở r+1, ta trừ v để những phần tử sau r không còn bị tăng. Nếu r=n−1, không có phần tử phía sau nên không cần viết `d[n]`.

### 4.2. Ví dụ

```text
a ban đầu = [2,1,3,4,5]
d ban đầu = [2,-1,2,1,1]

rangeAdd(1,3,+2)
    d[1] += 2
    d[4] -= 2

d sau update = [2,1,2,1,-1]
a khôi phục  = [2,3,5,6,5]
```

### 4.3. Trường hợp nên dùng

Nếu có q lần **cộng đoạn** rồi chỉ cần mảng cuối, difference array làm O(1) mỗi update, O(n) khôi phục, tổng:

\[
\boxed{O(n+q).}
\]

Nếu sau mỗi update lại có query sum ở những thời điểm khác nhau, việc chỉ có d **chưa** cho câu trả lời O(1); cần duy trì thông tin truy vấn bằng Fenwick/segment tree hoặc xử lý offline khác.

**Gán đoạn không phải cộng đoạn:** phép `rangeAssign` xóa các giá trị cũ, nên công thức hai vị trí của difference array không giải trực tiếp bài gán đoạn online.

---

## 5. Fenwick tree (Binary Indexed Tree) cho cập nhật điểm

Fenwick tree hay **BIT** quản lý tổng tiền tố bằng các đoạn có kích thước xác định qua bit thấp nhất.

Trong biểu diễn **1-based**, đặt:

\[
\boxed{lowbit(i)=i\mathbin{\&}(-i).}
\]

Một nút BIT[i] giữ tổng:

\[
\boxed{
BIT[i]=\sum_{j=i-lowbit(i)+1}^{i}a[j].
}
\]

### 5.1. Tính prefix

```text
prefix(i):
    s = 0
    while i > 0:
        s += BIT[i]
        i -= i & -i
    return s
```

Ví dụ i=12 (1100 nhị phân) có lowbit(12)=4, nên BIT[12] chứa các vị trí 9..12; tiếp tục i=8 chứa 1..8. Hai đoạn đúng phủ 1..12.

### 5.2. Cộng một điểm

```text
add(i, delta):
    while i <= n:
        BIT[i] += delta
        i += i & -i
```

Mỗi lần tăng i theo lowbit đi tới nút BIT tiếp theo có đoạn phụ trách chứa vị trí i ban đầu.

### 5.3. Tổng đoạn 0-based

Nếu giao diện ngoài dùng 0-based và [l,r] đóng, định nghĩa:

\[
P(r)=a[0]+\cdots+a[r],\qquad P(-1)=0.
\]

Thì:

\[
\boxed{sum(l,r)=P(r)-P(l-1).}
\]

Một lần point add hoặc prefix tính O(log n), nên range sum cũng O(log n). Một BIT cần O(n) bộ nhớ. Dựng qua n lần add tốn O(n log n); có biến thể build tuyến tính O(n) khi đã biết toàn bộ mảng đầu vào.

### 5.4. Point set bằng delta

BIT làm cộng, không làm gán trực tiếp. Để đặt a[i]=v:

1. Lấy old=a[i] từ mảng phụ hoặc hỏi tổng [i,i].
2. Tính `delta=v-old`.
3. Cộng delta ở i.

Nếu mỗi bước truy vấn/cập nhật BIT tốn O(log n), point set cũng O(log n).

---

## 6. Ba cấu hình Fenwick dễ bị nhầm

| Dữ liệu lưu trong BIT | Update nhanh | Query nhanh |
| --- | --- | --- |
| BIT cho a | Point add | Range sum |
| BIT cho d (sai phân) | Range add | Point value |
| **Hai BIT** cho d và j·d | **Range add** | **Range sum** |

Ở cấu hình thứ hai, một range add tương ứng hai cập nhật d, còn giá trị một điểm là prefix của d. Nhưng muốn **range sum** trực tiếp, cần mở rộng sang **hai BIT**.

### 6.1. Suy ra hai BIT bằng đổi thứ tự tổng

Dùng mảng gốc 0-based, sai phân:

\[
a[i]=\sum_{j=0}^{i}d[j].
\]

Gọi S(t) là tổng **t phần tử đầu**, từ a[0] tới a[t−1]:

\[
S(t)=\sum_{i=0}^{t-1}a[i]
=\sum_{i=0}^{t-1}\sum_{j=0}^{i}d[j].
\]

Đổi thứ tự:

\[
S(t)=\sum_{j=0}^{t-1}(t-j)d[j].
\]

Khai triển:

\[
\boxed{
S(t)=t\sum_{j=0}^{t-1}d[j]
-\sum_{j=0}^{t-1}j\,d[j].
}
\]

Duy trì:

- **B1** chứa `d[j]`.
- **B2** chứa `j·d[j]`.

Khi hỏi:

\[
\boxed{S(t)=t\cdot B1.prefix(t)-B2.prefix(t),}
\]

với `prefix(t)` của BIT 1-based trả tổng các vị trí 1..t.

Range sum:

\[
\boxed{sum(l,r)=S(r+1)-S(l).}
\]

### 6.2. Cộng đoạn [l,r] bằng hai BIT

Trong mảng sai phân 0-based:

\[
d[l]\mathrel{+}=v,
\]

\[
d[r+1]\mathrel{-}=v
\quad\text{nếu }r+1<n.
\]

Vì chỉ số BIT là 1-based:

| Vị trí BIT | B1 cập nhật | B2 cập nhật |
| --- | --- | --- |
| `l+1` | `+v` | `+l·v` |
| `r+2` nếu `r+1<n` | `−v` | `−(r+1)·v` |

**Lỗi lệch chỉ số:** cập nhật hủy ở **r+2** của BIT 1-based, không phải r+1.

Mỗi thay đổi BIT và mỗi truy vấn tiền tố tốn O(log n), nên range add và range sum đều O(log n), bộ nhớ O(n).

### 6.3. Ví dụ kiểm chứng

```text
[2,1,3,4,5]
rangeAdd(1,3,+2)
[2,3,5,6,5]
```

Tổng [0,4]:

\[
2+3+5+6+5=\boxed{21}.
\]

Công thức hai BIT trả S(5)=21.

### 6.4. Giới hạn của hai BIT

- **Không tự hỗ trợ range min/max** theo công thức tổng.
- **Range assign** bằng cách gán từng điểm trên đoạn dài L sẽ tốn O(L log n); đây là cách đúng để **đối chiếu** trên test nhỏ, không phải cấu trúc tối ưu cho gán cả đoạn.
- Nếu đầu bài cần cả range add, range assign, sum/min/max, **lazy segment tree** thích hợp hơn.

---

## 7. Segment tree cho tổng/min/max

Một **segment tree** chia dãy thành những đoạn nhị phân.

Mỗi nút p đại diện [L,R], nếu L<R và `M=\lfloor(L+R)/2\rfloor`:

- Con trái [L,M].
- Con phải [M+1,R].

Mỗi nút lưu:

\[
\boxed{(sum[p],min[p],max[p]).}
\]

Tại lá i:

\[
sum=min=max=a[i].
\]

Ở nút cha, gộp hai con:

\[
\boxed{
\begin{aligned}
sum[p]&=sum[left]+sum[right],\\
min[p]&=\min(min[left],min[right]),\\
max[p]&=\max(max[left],max[right]).
\end{aligned}
}
\]

### 7.1. Query đoạn

Khi hỏi [l,r]:

- Nút nằm hoàn toàn trong query: trả thống kê lưu ở nút.
- Nút giao một phần: hỏi các con giao với [l,r] rồi gộp.
- Nút ngoài query: không cần đi vào.

Một query range liên tục chỉ cần O(log n) nút chuẩn tắc trong phân tích cây cân bằng; bộ nhớ cho cây là O(n).

### 7.2. Point update

Cập nhật một vị trí i là cập nhật đoạn `[i,i]`. Chỉ đi dọc đường từ gốc xuống lá, sửa lá rồi tính lại các nút tổ tiên:

\[
\boxed{O(\log n).}
\]

### 7.3. Vì sao range update cần lazy?

Nếu update [l,r] mà đi tới từng lá, đoạn dài L cần O(L) lần thay đổi lá. **Lazy propagation** cho phép sửa thống kê của một nút khi đoạn nó quản lý được phủ trọn, ghi "cập nhật còn nợ" để chỉ truyền xuống con khi cần. Nhờ vậy:

\[
\boxed{\text{rangeAdd/rangeAssign}=O(\log n)}
\]

trong cây cân bằng với quy tắc lazy đúng.

"Lười" là hoãn **truyền cập nhật tới con**; thống kê của nút hiện tại **phải đúng ngay**.

---

## 8. Lazy tag cho cộng đoạn

Một nút quản lý [L,R] có độ dài:

\[
len=R-L+1.
\]

Cộng d vào mọi phần tử của đoạn này làm:

\[
\boxed{
sum\gets sum+d\cdot len,
}
\]

\[
\boxed{
min\gets min+d,\qquad max\gets max+d.
}
\]

Giải thích: tổng tăng d đúng len lần, còn mọi phần tử tăng cùng một lượng nên cực trị cũng tăng d.

### 8.1. Gộp hai lần cộng

Nếu đang chờ Add(3), lại có Add(5), hiệu lực là Add(8). Vì vậy:

\[
addTag\gets addTag+d.
\]

### 8.2. Push và pull

**push:** khi query/update cần đi vào con, truyền tag ở nút cha xuống hai con, cập nhật thống kê của con và tag chờ của con. Sau đó xóa tag ở cha.

**pull:** sau khi sửa các con, tính lại sum/min/max của cha bằng công thức gộp.

Quên **push trước truy vấn giao một phần** hoặc quên **pull sau cập nhật con** là hai lỗi điển hình gây kết quả sai.

---

## 9. Lazy tag cho gán đoạn và thứ tự thao tác

Gán đoạn thành v trên nút có len phần tử:

\[
\boxed{sum\gets v\cdot len,\qquad min=max=v.}
\]

Thẻ gán có thể lưu:

```text
hasAssign = true
assignTag = v
addTag = 0
```

### 9.1. Vì sao gán phải xóa cộng cũ?

Thực hiện:

```text
x = 5
add +3    => 8
assign 1  => 1
```

Khi gán, các phép cộng **trước** không còn tác dụng. Nếu giữ cộng +3 rồi sau đó push xuống con, con có thể trở thành 4 thay vì 1.

Vì vậy `applyAssign` phải **ghi đè thẻ gán cũ** và **xóa addTag**.

### 9.2. Cộng sau gán

Thực hiện:

```text
assign 1
add +4
```

Kết quả phải là 5. Nếu nút đang có `hasAssign=true`, khi apply Add(d) cần:

\[
\boxed{assignTag\gets assignTag+d}.
\]

Không được quên cập nhật thẻ gán, vì sau này con sẽ nhận chính giá trị ấy.

### 9.3. Bảng hợp thành

Hãy đọc các thao tác trong bảng **từ trái sang phải theo thời gian**:

| Trước đó | Mới đến | Hiệu lực cuối |
| --- | --- | --- |
| Add(a) | Add(b) | Add(a+b) |
| Add(a) | Set(v) | Set(v) |
| Set(v) | Add(b) | Set(v+b) |
| Set(v) | Set(w) | Set(w) |

Điểm mấu chốt:

\[
\boxed{\text{Add rồi Set khác Set rồi Add}.}
\]

Ví dụ:

- Add(+3), Set(1) → kết quả 1.
- Set(1), Add(+3) → kết quả 4.

### 9.4. Quy tắc chuẩn hóa thẻ trong mã Java

Mã `LazySegmentTree` bên dưới duy trì:

- `hasAssign=true` ⇒ `assignTag` đã hấp thụ mọi phép cộng xảy ra sau lần gán gần nhất trên nút, còn `addTag=0`.
- `hasAssign=false` ⇒ có thể đang có `addTag`.
- `push` ưu tiên truyền tag gán (nếu có), sau đó cộng (nếu có), rồi xóa tag ở cha.

Với bất biến chuẩn hóa này, một nút không cần giữ đồng thời hai tag hiệu lực. Dùng `hasAssign` riêng cũng xử lý đúng `Set(0)`: giá trị gán bằng 0 **không có nghĩa là không có tag**.

---

## 10. Chứng minh đúng của lazy segment tree

### 10.1. Bất biến

Ở mỗi nút p quản lý [L,R]:

1. `sum[p]` bằng tổng logic của mọi giá trị hiện tại trong [L,R].
2. `min[p]`, `max[p]` bằng cực trị logic của cùng đoạn.
3. Thẻ lazy biểu diễn chính xác hiệu ứng đã áp lên nút nhưng **chưa đẩy xuống hai con**.
4. Trước khi cần dùng các con, `push` làm chúng phản ánh những update còn nợ từ cha.

### 10.2. Cơ sở quy nạp

Ở lá [i,i], sum=min=max=a[i], không có tag, nên bất biến đúng.

Khi xây nút cha từ hai con đúng, phép gộp sum/min/max cho thống kê đúng của hợp hai đoạn.

### 10.3. Cập nhật phủ trọn

Nếu một update phủ kín nút, `applyAdd` hoặc `applyAssign` sửa đúng thống kê dựa trên len, gộp tag đúng theo thứ tự thời gian. Các con có thể chưa đổi, nhưng phần chênh lệch được biểu diễn trong tag.

### 10.4. Cập nhật giao một phần

`push` trước để các con đồng bộ; đệ quy sửa những con giao với [l,r]; sau đó `pull` để khôi phục thống kê đúng ở cha. Tính đúng theo quy nạp trên chiều cao cây.

### 10.5. Truy vấn

Query [l,r] được phân hoạch thành các đoạn cây không giao nhau. Ở nút phủ trọn, thống kê lưu sẵn đúng; ở nút giao một phần, phải push rồi truy vấn con. Phép gộp kết hợp cho đúng kết quả toàn khoảng.

**Chứng minh phải bao gồm cả thẻ cộng/gán chồng lấn**, chứ không chỉ trường hợp update duy nhất trên đoạn phủ trọn.

---

## 11. Ví dụ đầy đủ với cập nhật xen kẽ

Dãy ban đầu:

```text
a = [2,1,3,4,5]
```

### Bước 1 — Tổng ban đầu

\[
sum(0,4)=2+1+3+4+5=\boxed{15}.
\]

Min=1, max=5.

### Bước 2 — Cộng tại một điểm

```text
pointAdd(2,+5)
a = [2,1,8,4,5]
```

Tổng:

\[
sum(1,3)=1+8+4=\boxed{13}.
\]

### Bước 3 — Cộng đoạn

```text
rangeAdd(1,3,+2)
a = [2,3,10,6,5]
```

Tổng:

\[
sum(0,4)=2+3+10+6+5=\boxed{26}.
\]

Min=2, max=10.

### Bước 4 — Gán đoạn

```text
rangeAssign(0,2,7)
a = [7,7,7,6,5]
```

Tổng:

\[
sum(0,4)=7+7+7+6+5=\boxed{32}.
\]

Min=5, max=7.

### Bước 5 — Gán một điểm

```text
pointSet(4,-1)
a = [7,7,7,6,-1]
```

Tổng đoạn [3,4]:

\[
sum(3,4)=6-1=\boxed{5}.
\]

Min đoạn = −1, max đoạn = 6. Tổng toàn mảng cuối = 26.

### 11.1. Vì sao chạy hai cấu trúc song song?

**Fenwick hai cây** và **lazy segment tree** đều cho tổng nhanh sau point add và range add.

Với `rangeAssign(0,2,7)`:

- Segment tree chỉ cần một update O(log n).
- Để đối chiếu tổng, chương trình demo dùng **3 lần pointSet** ở Fenwick, không phải một range assign O(log n).

Chúng vẫn cho cùng kết quả **32** và về cuối cùng cùng tổng **26**. Min/max được lấy từ segment tree vì hai Fenwick phục vụ **tổng** chứ không lưu cực trị.

---

## 12. Java 17+: hai Fenwick và lazy segment tree có gán/cộng

Chương trình độc lập gồm:

1. `RangeFenwick` dùng hai BIT cho `rangeAdd`, `rangeSum`, `pointSet`.
2. `LazySegmentTree` dùng lazy tags cho `rangeAdd`, `rangeAssign`, `pointAdd`, `pointSet` và query sum/min/max.
3. `Summary` là record trả ba thống kê của một đoạn.
4. Hàm xây prefix/difference để minh họa lựa chọn offline/tĩnh.
5. Ví dụ tính tay mục 11 và các trường hợp biên.

**Tệp:** `RangeQueryUpdateDemo.java`.

**Quy ước số học:** dữ liệu và delta được giả sử nhỏ đủ để **mọi phép cộng, trừ, nhân length và mọi tổng trung gian nằm trong phạm vi kiểu long**. Java không tự báo tràn cho phép `+` hoặc `*` trên long; mã là demo thuật toán chứ không phải thư viện arbitrary precision. Nếu đề có giá trị cực đại, cần giới hạn rõ hoặc dùng `Math.addExact/Math.multiplyExact` hay `BigInteger` cùng thiết kế xử lý lỗi nhất quán.

### 12.1. Mã nguồn hoàn chỉnh

```java
import java.util.Arrays;

public final class RangeQueryUpdateDemo {

    private static void checkRange(int n, int l, int r) {
        if (l < 0 || r < l || r >= n) {
            throw new IllegalArgumentException(
                    "Expected 0 <= l <= r < n");
        }
    }

    public record Summary(long sum, long min, long max) {
        static Summary merge(Summary a, Summary b) {
            return new Summary(
                    a.sum() + b.sum(),
                    Math.min(a.min(), b.min()),
                    Math.max(a.max(), b.max()));
        }
    }

    // Two Fenwick trees: range add and range sum.
    // External indexes are 0-based, ranges [l,r] inclusive.
    public static final class RangeFenwick {
        private final int n;
        private final long[] b1;
        private final long[] b2;

        public RangeFenwick(long[] initial) {
            if (initial == null || initial.length == 0) {
                throw new IllegalArgumentException(
                        "Need a nonempty array");
            }

            n = initial.length;
            b1 = new long[n + 1];
            b2 = new long[n + 1];

            for (int i = 0; i < n; i++) {
                rangeAdd(i, i, initial[i]);
            }
        }

        private void update(long[] bit, int index, long delta) {
            for (int i = index; i <= n; i += i & -i) {
                bit[i] += delta;
            }
        }

        private long query(long[] bit, int index) {
            long answer = 0;

            for (int i = index; i > 0; i -= i & -i) {
                answer += bit[i];
            }

            return answer;
        }

        public void rangeAdd(int l, int r, long delta) {
            checkRange(n, l, r);

            // Difference d[l] += delta.
            update(b1, l + 1, delta);
            update(b2, l + 1, delta * l);

            // Difference d[r+1] -= delta, if in bounds.
            if (r + 1 < n) {
                update(b1, r + 2, -delta);
                update(b2, r + 2, -delta * (r + 1L));
            }
        }

        // Sum a[0..r], with prefix(-1)=0.
        private long prefix(int r) {
            if (r < 0) {
                return 0L;
            }

            int t = r + 1;
            return t * query(b1, t) - query(b2, t);
        }

        public long rangeSum(int l, int r) {
            checkRange(n, l, r);
            return prefix(r) - prefix(l - 1);
        }

        public void pointSet(int index, long value) {
            checkRange(n, index, index);
            long current = rangeSum(index, index);
            rangeAdd(index, index, value - current);
        }
    }

    // Lazy segment tree: range add, range assign,
    // sum/min/max queries. All external indexes 0-based.
    public static final class LazySegmentTree {
        private final int n;
        private final long[] sum;
        private final long[] minimum;
        private final long[] maximum;
        private final long[] addTag;
        private final long[] assignTag;
        private final boolean[] hasAssign;

        public LazySegmentTree(long[] initial) {
            if (initial == null || initial.length == 0) {
                throw new IllegalArgumentException(
                        "Need a nonempty array");
            }

            n = initial.length;

            if (n > (Integer.MAX_VALUE - 5) / 4) {
                throw new IllegalArgumentException(
                        "Array too large for 4*n tree");
            }

            int capacity = 4 * n + 5;
            sum = new long[capacity];
            minimum = new long[capacity];
            maximum = new long[capacity];
            addTag = new long[capacity];
            assignTag = new long[capacity];
            hasAssign = new boolean[capacity];

            build(1, 0, n - 1, initial);
        }

        private void build(int p, int lo, int hi, long[] a) {
            if (lo == hi) {
                sum[p] = a[lo];
                minimum[p] = a[lo];
                maximum[p] = a[lo];
                return;
            }

            int mid = lo + (hi - lo) / 2;
            build(p * 2, lo, mid, a);
            build(p * 2 + 1, mid + 1, hi, a);
            pull(p);
        }

        private void pull(int p) {
            int left = p * 2;
            int right = left + 1;

            sum[p] = sum[left] + sum[right];
            minimum[p] = Math.min(
                    minimum[left], minimum[right]);
            maximum[p] = Math.max(
                    maximum[left], maximum[right]);
        }

        private void applyAssign(
                int p, int lo, int hi, long value) {

            long len = (long) hi - lo + 1L;

            sum[p] = value * len;
            minimum[p] = value;
            maximum[p] = value;

            hasAssign[p] = true;
            assignTag[p] = value;
            addTag[p] = 0L;
        }

        private void applyAdd(
                int p, int lo, int hi, long delta) {

            long len = (long) hi - lo + 1L;

            sum[p] += delta * len;
            minimum[p] += delta;
            maximum[p] += delta;

            // Compose the new update AFTER older updates.
            if (hasAssign[p]) {
                assignTag[p] += delta;
            } else {
                addTag[p] += delta;
            }
        }

        private void push(int p, int lo, int hi) {
            if (lo == hi) {
                return;
            }

            int mid = lo + (hi - lo) / 2;
            int left = p * 2;
            int right = left + 1;

            if (hasAssign[p]) {
                applyAssign(
                        left, lo, mid, assignTag[p]);
                applyAssign(
                        right, mid + 1, hi, assignTag[p]);
                hasAssign[p] = false;
            }

            if (addTag[p] != 0L) {
                applyAdd(
                        left, lo, mid, addTag[p]);
                applyAdd(
                        right, mid + 1, hi, addTag[p]);
                addTag[p] = 0L;
            }
        }

        private void modify(
                int p, int lo, int hi,
                int l, int r,
                boolean assigning, long value) {

            if (l <= lo && hi <= r) {
                if (assigning) {
                    applyAssign(p, lo, hi, value);
                } else {
                    applyAdd(p, lo, hi, value);
                }
                return;
            }

            push(p, lo, hi);

            int mid = lo + (hi - lo) / 2;

            if (l <= mid) {
                modify(
                        p * 2, lo, mid,
                        l, r, assigning, value);
            }

            if (r > mid) {
                modify(
                        p * 2 + 1, mid + 1, hi,
                        l, r, assigning, value);
            }

            pull(p);
        }

        public void rangeAdd(int l, int r, long delta) {
            checkRange(n, l, r);
            modify(1, 0, n - 1, l, r, false, delta);
        }

        public void rangeAssign(int l, int r, long value) {
            checkRange(n, l, r);
            modify(1, 0, n - 1, l, r, true, value);
        }

        public void pointAdd(int i, long delta) {
            rangeAdd(i, i, delta);
        }

        public void pointSet(int i, long value) {
            rangeAssign(i, i, value);
        }

        private Summary ask(
                int p, int lo, int hi, int l, int r) {

            if (l <= lo && hi <= r) {
                return new Summary(
                        sum[p], minimum[p], maximum[p]);
            }

            push(p, lo, hi);

            int mid = lo + (hi - lo) / 2;

            if (r <= mid) {
                return ask(p * 2, lo, mid, l, r);
            }

            if (l > mid) {
                return ask(
                        p * 2 + 1, mid + 1, hi, l, r);
            }

            Summary left = ask(
                    p * 2, lo, mid, l, r);
            Summary right = ask(
                    p * 2 + 1, mid + 1, hi, l, r);

            return Summary.merge(left, right);
        }

        public Summary query(int l, int r) {
            checkRange(n, l, r);
            return ask(1, 0, n - 1, l, r);
        }
    }

    private static long[] prefixSums(long[] a) {
        long[] prefix = new long[a.length + 1];

        for (int i = 0; i < a.length; i++) {
            prefix[i + 1] = prefix[i] + a[i];
        }

        return prefix;
    }

    private static long[] difference(long[] a) {
        long[] diff = new long[a.length];

        if (a.length > 0) {
            diff[0] = a[0];
        }

        for (int i = 1; i < a.length; i++) {
            diff[i] = a[i] - a[i - 1];
        }

        return diff;
    }

    public static void main(String[] args) {
        long[] original = {2, 1, 3, 4, 5};

        long[] prefix = prefixSums(original);
        long[] diff = difference(original);

        System.out.println(
                "Original: " + Arrays.toString(original));
        System.out.println(
                "Static prefix: " + Arrays.toString(prefix));
        System.out.println(
                "Static sum [1,3]: "
                        + (prefix[4] - prefix[1]));
        System.out.println(
                "Initial difference: " + Arrays.toString(diff));

        // Offline range add [1,3] += 2 in difference array.
        diff[1] += 2;
        diff[4] -= 2;

        long[] rebuilt = new long[diff.length];
        long running = 0;

        for (int i = 0; i < diff.length; i++) {
            running += diff[i];
            rebuilt[i] = running;
        }

        System.out.println(
                "After offline difference add: "
                        + Arrays.toString(rebuilt));

        // Fresh independent structures for online operations.
        RangeFenwick bit = new RangeFenwick(original);
        LazySegmentTree tree =
                new LazySegmentTree(original);

        System.out.println(
                "Initial sum [0,4]: "
                        + tree.query(0, 4).sum());
        System.out.println(
                "Initial BIT sum [0,4]: "
                        + bit.rangeSum(0, 4));

        // 1) Point add at index 2.
        bit.rangeAdd(2, 2, 5);
        tree.pointAdd(2, 5);

        System.out.println(
                "After point add, sum [1,3]: "
                        + tree.query(1, 3).sum());

        // 2) Range add at [1,3].
        bit.rangeAdd(1, 3, 2);
        tree.rangeAdd(1, 3, 2);

        Summary afterAdd = tree.query(0, 4);

        System.out.println(
                "After range add, total: "
                        + afterAdd.sum());
        System.out.println(
                "After range add, min/max: "
                        + afterAdd.min() + "/" + afterAdd.max());
        System.out.println(
                "BIT total after range add: "
                        + bit.rangeSum(0, 4));

        // 3) Range assignment. Segment tree: O(log n).
        tree.rangeAssign(0, 2, 7);

        // BIT has no efficient range assignment here.
        // Use three point sets ONLY for cross-checking.
        for (int i = 0; i <= 2; i++) {
            bit.pointSet(i, 7);
        }

        Summary afterAssign = tree.query(0, 4);

        System.out.println(
                "After range assign, total: "
                        + afterAssign.sum());
        System.out.println(
                "After range assign, min/max: "
                        + afterAssign.min() + "/"
                        + afterAssign.max());
        System.out.println(
                "BIT total after 3 point sets: "
                        + bit.rangeSum(0, 4));

        // 4) Point set at index 4.
        tree.pointSet(4, -1);
        bit.pointSet(4, -1);

        Summary tail = tree.query(3, 4);

        System.out.println(
                "After point set, sum [3,4]: "
                        + tail.sum());
        System.out.println(
                "After point set, min/max [3,4]: "
                        + tail.min() + "/" + tail.max());
        System.out.println(
                "Final tree sum: "
                        + tree.query(0, 4).sum());
        System.out.println(
                "Final BIT sum: "
                        + bit.rangeSum(0, 4));

        LazySegmentTree single =
                new LazySegmentTree(new long[] {8});

        single.rangeAdd(0, 0, -3);
        single.rangeAssign(0, 0, -2);

        System.out.println(
                "Single element after add/set: "
                        + single.query(0, 0).sum());

        boolean invalidRangeRejected = false;

        try {
            tree.query(-1, 3);
        } catch (IllegalArgumentException ex) {
            invalidRangeRejected = true;
        }

        System.out.println(
                "Invalid range rejected: "
                        + invalidRangeRejected);

        boolean emptyRejected = false;

        try {
            new LazySegmentTree(new long[0]);
        } catch (IllegalArgumentException ex) {
            emptyRejected = true;
        }

        System.out.println(
                "Empty array rejected: " + emptyRejected);
    }
}
```

### 12.2. Biên dịch và chạy

Với JDK 17+:

```bash
javac RangeQueryUpdateDemo.java
java RangeQueryUpdateDemo
```

**Stdout kỳ vọng:**

```text
Original: [2, 1, 3, 4, 5]
Static prefix: [0, 2, 3, 6, 10, 15]
Static sum [1,3]: 8
Initial difference: [2, -1, 2, 1, 1]
After offline difference add: [2, 3, 5, 6, 5]
Initial sum [0,4]: 15
Initial BIT sum [0,4]: 15
After point add, sum [1,3]: 13
After range add, total: 26
After range add, min/max: 2/10
BIT total after range add: 26
After range assign, total: 32
After range assign, min/max: 5/7
BIT total after 3 point sets: 32
After point set, sum [3,4]: 5
After point set, min/max [3,4]: -1/6
Final tree sum: 26
Final BIT sum: 26
Single element after add/set: -2
Invalid range rejected: true
Empty array rejected: true
```

### 12.3. Cách đọc hai Fenwick

`b1` và `b2` lưu hai tổng tiền tố của sai phân. Cập nhật range add trong `RangeFenwick`:

```java
update(b1, l + 1, delta);
update(b2, l + 1, delta * l);

if (r + 1 < n) {
    update(b1, r + 2, -delta);
    update(b2, r + 2, -delta * (r + 1L));
}
```

Các chỉ số bên ngoài là 0-based còn BIT là 1-based. Query prefix t phần tử:

```java
return t * query(b1, t) - query(b2, t);
```

Sau đó sum [l,r] là `prefix(r)-prefix(l-1)`, với prefix(-1)=0.

### 12.4. Cách đọc lazy segment tree

- `build` xây thống kê ở lá, sau đó `pull` lên cha.
- `applyAdd` cập nhật sum/min/max ngay; nếu đang gán, cộng vào giá trị assignTag; nếu không, cộng vào addTag.
- `applyAssign` ghi đè tổng/cực trị, bật hasAssign, xóa addTag.
- `push` truyền thẻ từ cha xuống hai con khi cần.
- `modify` cập nhật một đoạn, dùng cờ `assigning` để chọn cách sửa.
- `ask` lấy `Summary` của truy vấn, tránh trả "đoạn rỗng" khi min/max có thể nhận long cực trị.

Cách cài này không sử dụng `Long.MAX_VALUE`/`Long.MIN_VALUE` làm mã nhận biết đoạn rỗng: nếu query chỉ chạm một nhánh, `ask` trả trực tiếp nhánh ấy; nếu chạm hai, gộp cả hai.

### 12.5. Đầu vào và các trường hợp biên

- Mảng rỗng hoặc null: constructor từ chối.
- `l<0`, `r>=n`, `l>r`: ném `IllegalArgumentException`.
- n=1: cây chỉ có một lá, có thể cộng/gán/query.
- `Set(0)` vẫn có tag vì dùng `hasAssign` riêng.
- Dữ liệu âm: min/max/sum xử lý theo cùng quy tắc.
- Mỗi mảng tree có khoảng `4n` phần tử; mã kiểm tra trước phép tính `4*n+5` để giảm rủi ro tràn int.
- Fenwick xây bằng n rangeAdd điểm: O(n log n), không nhầm với cách tối ưu build tuyến tính cho một BIT.

---

## 13. Bảng độ phức tạp và phạm vi áp dụng

Với n phần tử và L=r−l+1:

| Cấu trúc | Build | Update | Query | Bộ nhớ phụ |
| --- | --- | --- | --- | --- |
| Mảng thường | O(n) | Point O(1), range O(L) | Range O(L) | O(1) ngoài mảng |
| Prefix sum tĩnh | O(n) | Point O(n) nếu sửa prefix | Sum O(1) | O(n) |
| Difference array | O(n) | Range add O(1) | Khôi phục toàn dãy O(n) | O(n) |
| Fenwick 1 BIT | O(n log n) qua từng add | Point add O(log n) | Sum O(log n) | O(n) |
| Hai Fenwick | O(n log n) trong demo | Range add O(log n) | Sum O(log n) | O(n) |
| Lazy segment tree | O(n) | Add/assign đoạn O(log n) | Sum/min/max O(log n) | O(n) |
| Sparse table tĩnh | O(n log n) | Không hỗ trợ update động hiệu quả | Min O(1) | O(n log n) |
| Sqrt decomposition | O(n) | Khoảng O(√n) tùy phép | Khoảng O(√n) | O(√n) block metadata |

Cây segment tree có chiều cao O(log n). Cập nhật/truy vấn một khoảng liên tục chạm O(log n) nút chuẩn tắc và O(log n) nút biên cần đệ quy; mỗi nút thực hiện một lượng công việc hằng số để apply/push/pull/gộp, nên **O(log n)**.

Bộ nhớ tổng của segment tree vẫn O(n) dù cấp phát vài mảng dài `4n`. Với n quá lớn, overhead thực tế phải được dự toán.

**Không quên độ dài số học:** long có phạm vi hữu hạn. Nếu tổng có thể vượt kiểu long, cận O(log n) phép toán trên từ máy không tự chứng minh kết quả số nguyên là chính xác; cần số học phù hợp.

---

## 14. Tư duy monoid cho truy vấn tổng hợp

Một **monoid** gồm tập M, phép gộp `\oplus` **kết hợp** và phần tử đơn vị e:

\[
(a\oplus b)\oplus c=a\oplus(b\oplus c),
\]

\[
e\oplus a=a\oplus e=a.
\]

Ví dụ:

| Aggregate | Phép gộp | Đơn vị |
| --- | --- | --- |
| Sum | Cộng | 0 |
| Min | Min | +∞ về mặt toán học |
| Max | Max | −∞ về mặt toán học |
| GCD (không âm) | GCD | 0 |
| XOR | XOR | 0 |
| Nối chuỗi | Nối | Chuỗi rỗng |
| Nhân ma trận vuông | Nhân | Ma trận đơn vị |

### 14.1. Kết hợp không đồng nghĩa giao hoán

Ghép chuỗi có tính kết hợp:

```text
("a"+"b")+"c" = "a"+("b"+"c")
```

nhưng "ab" khác "ba". Nhân ma trận cũng thường không giao hoán. Segment tree vẫn xử lý được aggregate kết hợp **nếu giữ đúng thứ tự đoạn trái rồi đoạn phải**.

Không được đảo thứ tự gộp với phép không giao hoán.

### 14.2. Lazy update cần thêm điều kiện

Có phép gộp kết hợp mới đủ cho **range aggregate**; để **lazy range update**, còn phải biết:

1. Update trên cả đoạn biến đổi aggregate ra sao.
2. Hai update liên tiếp hợp thành thế nào.
3. Có thể truyền hiệu ứng từ cha xuống hai con mà không mất thứ tự.

Ví dụ Add(d) tác động đơn giản lên sum/min/max, nhưng không tự có công thức thay đổi **GCD của mọi phần tử trong đoạn** chỉ từ GCD cũ và d.

### 14.3. Vì sao BIT sum không thay bằng min một cách máy móc?

Range sum sử dụng `prefix(r)-prefix(l-1)`, cần phép nghịch đảo của cộng. Min không có "phép trừ hai min prefix" để khôi phục min của một đoạn tùy ý. Có biến thể Fenwick cho những mục tiêu riêng, nhưng **Fenwick sum cơ bản không hỗ trợ min động tùy ý bằng cùng công thức**.

---

## 15. Ngoại tuyến, sparse table, Mo và sqrt decomposition

### 15.1. Khi các cập nhật kết thúc trước truy vấn

Nếu tất cả q update đều là **cộng đoạn**, chỉ hỏi sum sau khi xử lý xong:

1. Dùng difference array: O(q).
2. Khôi phục mảng: O(n).
3. Xây prefix: O(n).
4. Mỗi query sum: O(1).

Tổng:

\[
\boxed{O(n+q+m)}
\]

cho m query ở cuối.

Cách này thường đơn giản hơn lazy segment tree vì **không cần xử lý xen kẽ theo thời gian**.

### 15.2. Offline nhưng có thời điểm khác nhau

Nếu query xuất hiện xen giữa update, không được gom update để tính trạng thái cuối rồi dùng cho mọi query. Có thể biến bài offline bằng **divide-and-conquer theo thời gian**, **CDQ**, **parallel binary search**, hoặc cấu trúc persistent trong các bài phù hợp, nhưng phải chứng minh đáp án tương ứng đúng thời điểm.

### 15.3. Sparse table cho min tĩnh

Với mảng **không đổi**, sparse table giữ min trên các đoạn dài `2^j`. Query RMQ [l,r] chọn `k=\lfloor\log_2(r-l+1)\rfloor` rồi lấy:

\[
\boxed{
\min(st[k][l],st[k][r-2^k+1]).
}
\]

Hai đoạn có thể chồng nhau vì min **idempotent**:

\[
\min(x,x)=x.
\]

Cận:

- Build O(n log n).
- Range min O(1).
- **Không** cập nhật online hiệu quả theo bảng cũ.

Với sum, lấy tổng hai khoảng chồng nhau sẽ đếm trùng; dùng prefix cho sum tĩnh.

### 15.4. Mo's algorithm

Mo sắp thứ tự những truy vấn đoạn tĩnh để di chuyển hai con trỏ ít hơn, áp dụng khi có thao tác **add/remove một phần tử** với chi phí đủ nhỏ. Một cấu hình thường được mô tả khoảng O((n+q)√n) thao tác, tùy biến thể và số query.

Mo chuẩn không tự hỗ trợ update xen kẽ; có biến thể **Mo with modifications** thêm trục thời gian nhưng phức tạp và phụ thuộc phép cập nhật.

### 15.5. Sqrt decomposition

Chia mảng thành block độ dài khoảng √n. Mỗi block có metadata tổng/min/max và có thể có lazy tag. Với point update + sum, thao tác thường O(√n) ở dạng cơ bản; với range add, ta cập nhật nguyên block bằng tag và các mảnh biên trực tiếp.

Nếu cần cả range assign, các block cũng phải xử lý **gán sau cộng** và **cộng sau gán** như segment tree. Không có chuyện dùng lazy tag cho cộng rồi tự nhiên hỗ trợ gán mà không bổ sung logic.

---

## 16. Kiểm thử độc lập và bất biến

### 16.1. Oracle mảng trực tiếp

Trong test với n nhỏ, duy trì `naive[]`:

```text
pointAdd(i,d):          naive[i] += d
pointSet(i,v):          naive[i] = v
rangeAdd(l,r,d):        for i=l..r: naive[i] += d
rangeAssign(l,r,v):     for i=l..r: naive[i] = v

query:
    expectedSum = sum naive[l..r]
    expectedMin = min naive[l..r]
    expectedMax = max naive[l..r]
```

So với hai BIT và lazy segment tree:

\[
sum_{\mathrm{BIT}}=sum_{\mathrm{tree}}=sum_{\mathrm{naive}},
\]

\[
min_{\mathrm{tree}}=min_{\mathrm{naive}},
\qquad
max_{\mathrm{tree}}=max_{\mathrm{naive}}.
\]

Nếu Fenwick không hỗ trợ gán đoạn nhanh, trong **test nhỏ** có thể gán từng điểm để đồng bộ oracle; phải ghi rõ đây là O(L log n), không phải range assign tối ưu.

### 16.2. Test ngẫu nhiên

1. Sinh n từ 1 tới 48.
2. Sinh mảng số nguyên nhỏ, cho phép âm và bằng 0.
3. Sinh nhiều cặp `l,r` với `0≤l≤r<n`.
4. Xen kẽ range add, range assign, query.
5. Với mỗi query, so sum/min/max của segment tree với mảng trực tiếp và sum của hai BIT.
6. Giữ seed để tái hiện sai khác.
7. Tăng tần suất update gán và cộng **chồng lấn**; đây là nguồn lỗi nhiều nhất.

Mô hình độc lập đã thực hiện **144.000 thao tác** ngẫu nhiên, gồm **72.000 truy vấn** trên các n từ 1 đến 48. Các kết quả đều khớp oracle. Đây là bằng chứng thực nghiệm kiểm thử cài đặt, **không thay chứng minh cho mọi đầu vào**.

### 16.3. Bất biến đặc biệt

- Sum [i,i] đúng giá trị phần tử i.
- Query toàn [0,n−1] đúng tổng mảng.
- Với mọi đoạn không rỗng, min≤max.
- Hai Add(a), Add(b) liên tiếp tương đương Add(a+b).
- Add(a) rồi Set(v) tương đương Set(v).
- Set(v) rồi Add(a) tương đương Set(v+a).
- Update [l,r] không đổi phần tử ngoài đoạn.
- Query không đổi các giá trị logic dù `push` có thể biến đổi cấu trúc thẻ trong cây.
- Mọi child tag khi được đẩy xuống đều phải thể hiện đúng **thứ tự thời gian**.

### 16.4. Ca lỗi điển hình cho tag

**Gán sau cộng:**

```text
a = [1,2,3,4]
add(0,3,+10)
assign(1,2,5)

a = [11,5,5,14]
sum(0,3) = 35
```

**Cộng sau gán:**

```text
a = [1,2,3,4]
assign(0,3,7)
add(1,2,+3)

a = [7,10,10,7]
sum(0,3)=34
min(0,3)=7
max(0,3)=10
```

Chỉ test một lần cộng hoặc một lần gán sẽ bỏ sót lỗi **tag composition**.

### 16.5. Trường hợp biên bắt buộc

| Trường hợp | Kết quả / yêu cầu |
| --- | --- |
| n=1 | Có thể add/set/query một phần tử |
| l=r | Tương đương point update/query |
| l=0 | Prefix(l−1) phải xử lý ranh giới |
| r=n−1 | Hai BIT không hủy ở vị trí ngoài n |
| Delta=0 | Không đổi dữ liệu logic |
| Set(0) | Phải nhận biết gán 0 bằng hasAssign |
| Giá trị âm | Min/max/sum đúng |
| Các đoạn rời nhau | Không ảnh hưởng nhau |
| Các đoạn lồng/chồng | Tag hợp thành đúng |
| l<0, r≥n, l>r | Từ chối rõ ràng |
| Mảng null/rỗng | Từ chối rõ ràng |
| Overflow long | Đặt hợp đồng đầu vào hoặc xử lý kiểm tra |

---

## 17. Những lỗi thường gặp

1. **Nhầm 0-based và 1-based** trong BIT.
2. **Nhầm đoạn đóng [l,r] với [l,r)**.
3. **Dùng `pref[r]−pref[l]` cho [l,r]**, bỏ mất a[r].
4. **Quên pref[0]=0**.
5. **Dùng prefix cũ sau update**.
6. **Cho rằng difference array tự trả range sum online O(1)**.
7. **Quên d[r+1]−=delta nếu r+1<n**.
8. **Ghi d[n] khi r=n−1**, vượt mảng.
9. **Nhầm point add với point set**.
10. **Tưởng một BIT point add/range sum tự cho range add O(log n)**.
11. **Hai BIT dùng r+1 thay r+2 trong index BIT hủy**.
12. **Thiếu nhân t trong `S(t)=tB1−B2`**.
13. **Nhầm hệ số `l·d` và `(r+1)·d` của B2**.
14. **Gọi hai BIT sum là cấu trúc range min/max động**, không đúng.
15. **Coi gán từng điểm bằng Fenwick là gán đoạn O(log n)**.
16. **Gán đoạn không xóa addTag cũ**.
17. **Cộng sau gán không tăng assignTag**.
18. **Dùng assignTag=0 làm dấu "không có thẻ"**, sai với Set(0).
19. **Đẩy thẻ xuống con sai thứ tự**.
20. **Quên cập nhật thống kê nút khi đặt lazy**, full-cover query sai.
21. **Quên push trước khi query đi vào con**.
22. **Quên pull sau khi update con**.
23. **Đảo thứ tự gộp với phép không giao hoán**, như nối chuỗi.
24. **Tưởng mọi monoid hỗ trợ cùng một lazy range add**, không đúng.
25. **Dùng minPrefix bằng cách trừ hai min prefix**, không hợp lệ.
26. **Dùng sparse table tĩnh cho mảng động mà không xây lại**.
27. **Lấy tổng hai khoảng sparse table chồng nhau**, đếm trùng.
28. **Đổi thứ tự ngữ nghĩa của query/update khi làm offline**.
29. **Tưởng Mo chuẩn hỗ trợ update theo thời gian**.
30. **Không đếm bộ nhớ O(n) của nhiều mảng `4n` trong segment tree**.
31. **Không kiểm soát overflow long**, kể cả nhân value*len.
32. **Không kiểm tra l>r, l<0, r≥n**.
33. **Chỉ test sum mà không test min/max**.
34. **Không dùng oracle độc lập trên các case nhỏ**.
35. **Chỉ test update không chồng lấn**, bỏ lỗi lazy.
36. **Cho rằng toàn bộ chương trình O(n) dù constructor hai BIT dựng bằng n lần O(log n)**.
37. **Tuyên bố không cần lazy cho range assign O(log n)** mà cập nhật từng lá.
38. **Nhầm O(log n) update với O(1)** khi n lớn.
39. **Quên xử lý n=1 hoặc mảng rỗng**, gây lỗi đệ quy.
40. **Đưa kết quả Min/Max bằng sentinel long mà không xét các giá trị cực trị thật**.

---

## 18. Bài tập tự kiểm tra

### Bài 1
Phân biệt pointAdd, pointSet, rangeAdd và rangeAssign.

### Bài 2
Với mảng `[2,1,3,4,5]`, viết prefix array dài 6.

### Bài 3
Tính tổng [1,3] bằng prefix sum.

### Bài 4
Vì sao point update ảnh hưởng nhiều giá trị prefix?

### Bài 5
Định nghĩa difference array.

### Bài 6
Cộng đoạn [l,r] bằng difference array phải sửa những vị trí nào?

### Bài 7
Cộng 2 vào [1,3] của mảng ban đầu cho dãy nào?

### Bài 8
Vì sao difference array thích hợp xử lý offline?

### Bài 9
Viết công thức lowbit(i) của BIT.

### Bài 10
BIT[i] 1-based lưu tổng đoạn nào?

### Bài 11
Vì sao pointAdd trong BIT đi lên theo i+=lowbit(i)?

### Bài 12
Viết range sum từ hai prefix.

### Bài 13
Một BIT trên a hỗ trợ cặp update/query nào?

### Bài 14
Hai BIT lưu những tổng theo sai phân nào?

### Bài 15
Suy ra `S(t)=t·B1.prefix(t)−B2.prefix(t)`.

### Bài 16
Khi range add [l,r] ở 0-based, update BIT tại hai vị trí 1-based nào?

### Bài 17
Vì sao hai BIT không tự cho range min?

### Bài 18
Quy tắc gộp sum/min/max từ hai nút con?

### Bài 19
Lazy propagation hoãn điều gì?

### Bài 20
Khi cộng d vào đoạn dài len, cập nhật sum/min/max ra sao?

### Bài 21
Khi gán v vào đoạn dài len, cập nhật sum/min/max ra sao?

### Bài 22
Vì sao gán sau cộng phải xóa addTag?

### Bài 23
Set(5) rồi Add(3) cho tag gì?

### Bài 24
Add(9) rồi Set(2) cho tag gì?

### Bài 25
Vì sao trước query một phần đoạn phải push?

### Bài 26
Độ phức tạp của range add/assign/query trên lazy segment tree?

### Bài 27
Sau pointAdd(2,5), tổng [1,3] của ví dụ là bao nhiêu?

### Bài 28
Sau rangeAdd(1,3,2), mảng là gì?

### Bài 29
Sau rangeAssign(0,2,7), tổng và min/max toàn mảng là gì?

### Bài 30
Sau pointSet(4,-1), min/max đoạn [3,4] là gì?

### Bài 31
Monoid yêu cầu phép gộp có tính chất gì?

### Bài 32
Cho ví dụ phép gộp kết hợp nhưng không giao hoán.

### Bài 33
Tại sao sparse table cho min O(1) có thể ghép hai đoạn chồng nhau?

### Bài 34
Khi nào difference array và prefix cuối thích hợp hơn lazy segment tree?

### Bài 35
Nêu một test phát hiện lỗi gán sau cộng.

### Bài 36
Vì sao không được gom update lên đầu khi query ở các thời điểm khác nhau?

### Bài 37
Với một phần tử −3, Set(0) rồi Add(5), sum/min/max bằng bao nhiêu?

### Bài 38
Tại sao hai BIT vẫn cho range sum O(log n) dù cần hai prefix?

### Bài 39
Nếu cần range assign và min/max nhưng không cần sum, nên dùng hai BIT sum không?

### Bài 40
Những phép toán nào trên long có thể overflow trong mã demo?

### Đáp án gợi ý

1. PointAdd cộng vào một phần tử; pointSet gán một phần tử; rangeAdd cộng mọi phần tử đoạn; rangeAssign gán mọi phần tử đoạn.
2. `[0,2,3,6,10,15]`.
3. `pref[4]−pref[1]=10−2=8`.
4. Mọi prefix chứa vị trí được sửa đều phải thay đổi.
5. `d[0]=a[0]`, `d[i]=a[i]−a[i−1]` với i>0.
6. `d[l]+=v` và nếu r+1<n thì `d[r+1]−=v`.
7. `[2,3,5,6,5]`.
8. Một update O(1), khôi phục mảng cuối O(n) sau tất cả update.
9. `i&(-i)`.
10. `[i−lowbit(i)+1,i]`.
11. Đi qua đúng các nút có đoạn quản lý chứa vị trí cập nhật.
12. `sum(l,r)=prefix(r)−prefix(l−1)`.
13. Point add + range sum.
14. BIT1 lưu d[j], BIT2 lưu j·d[j].
15. `S(t)=\sum_{j<t}(t-j)d[j]=t\sum_{j<t}d[j]−\sum_{j<t}j d[j]`.
16. `l+1` và `r+2` (nếu r+1<n).
17. Min không có phép nghịch đảo prefix như cộng/trừ.
18. Sum cộng, min lấy min, max lấy max.
19. Hoãn truyền update từ nút phủ trọn xuống các con, không hoãn sửa thống kê nút.
20. `sum+=d·len, min+=d, max+=d`.
21. `sum=v·len, min=max=v`.
22. Vì Set ghi đè những phép cộng xảy ra trước Set.
23. Set(8).
24. Set(2).
25. Con có thể còn cũ so với lazy tag ở cha.
26. O(log n) mỗi thao tác; build O(n).
27. 13.
28. `[2,3,10,6,5]`.
29. Mảng `[7,7,7,6,5]`; tổng 32; min 5, max 7.
30. Min −1, max 6.
31. Kết hợp và có phần tử đơn vị.
32. Nối chuỗi hoặc nhân ma trận.
33. Min idempotent: `min(x,x)=x`.
34. Khi mọi cập nhật cộng đoạn đều đến trước mọi truy vấn và chỉ cần mảng cuối.
35. `add(0,3,+10)` rồi `assign(1,2,5)` với `[1,2,3,4]` phải cho tổng 35.
36. Vì mỗi query phải phản ánh trạng thái tại thời điểm của nó.
37. Sum=min=max=5.
38. Mỗi BIT prefix tốn O(log n); số lần gọi hằng số vẫn O(log n).
39. Không, lazy segment tree với aggregate extrema và tag gán phù hợp hơn.
40. Tổng, phép nhân delta·len, hiệu tạo delta của pointSet và các phép cộng tag có thể overflow.

---

## Ghi nhớ

Đừng chọn cấu trúc dữ liệu chỉ vì có từ "range query"; hãy xác định **loại cập nhật** và **loại tổng hợp** trước:

- **Prefix sum:** query tổng đoạn O(1) khi không có cập nhật.
- **Difference array:** cộng đoạn O(1) và khôi phục O(n) khi update có thể xử lý offline.
- **Fenwick một BIT:** point add + range sum O(log n).
- **Hai Fenwick:** range add + range sum O(log n), nhưng không có range assign O(log n) theo cách này.
- **Lazy segment tree:** range add, range assign và truy vấn sum/min/max đều O(log n).

Hai công thức cần nhớ:

\[
\boxed{S(t)=t\cdot B1.prefix(t)-B2.prefix(t)}
\]

và:

\[
\boxed{
Add(d):\ (sum,min,max)\gets(sum+d\cdot len,min+d,max+d).
}
\]

\[
\boxed{
Set(v):\ (sum,min,max)\gets(v\cdot len,v,v).
}
\]

**Gán sau cộng** xóa các cộng cũ; **cộng sau gán** cộng vào giá trị đang chờ gán. Mọi triển khai phải xác định 0-based/1-based, [l,r] đóng hay nửa mở, ranh giới r=n−1, dữ liệu âm, các phép overflow và cách test độc lập bằng mảng nhỏ.
