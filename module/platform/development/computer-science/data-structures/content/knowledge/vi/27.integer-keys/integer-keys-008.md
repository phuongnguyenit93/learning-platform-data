# x-fast trie, y-fast trie và ý tưởng kết hợp tiền tố với bảng băm

Khi một chương trình quản lý **tập khóa số nguyên có thứ tự**, phép toán `contains(x)` chưa đủ. Ta còn muốn tìm khóa ngay trước `x` (*predecessor*), khóa ngay sau `x` (*successor*), khóa nhỏ nhất/lớn nhất hoặc duyệt một khoảng khóa. Bảng băm thường rất mạnh khi hỏi **một khóa chính xác**, nhưng tự nó không cho biết khóa nào liền trước hoặc liền sau theo thứ tự. Trie nhị phân lại giữ **đường đi theo bit của khóa**, nhưng phải đi qua tới `w` tầng để lần ra một khóa `w` bit.

**x-fast trie** và **y-fast trie** là hai cấu trúc chuyên biệt cho **tập số nguyên trong một miền hữu hạn**. Ý tưởng x-fast trie là **lập bảng băm cho các tiền tố bit hiện có ở từng độ dài**, rồi **tìm kiếm nhị phân theo độ dài tiền tố** để bỏ qua nhiều tầng trie. y-fast trie giữ một **chỉ mục x-fast chỉ trên một tập nhỏ các khóa đại diện**, còn các khóa bình thường được gom vào các **nhóm có cây tìm kiếm cân bằng**; nhờ đó giảm đáng kể chi phí bộ nhớ của việc đánh chỉ mục mọi tiền tố của mọi khóa.

Theo mô hình chuẩn với miền `U=2^w`, các kết quả thường được trình bày như sau:

| Cấu trúc | Tìm tiền nhiệm/kế nhiệm | Chèn/xóa | Không gian |
| --- | --- | --- | --- |
| **x-fast trie** | **O(log w) kỳ vọng** | **O(w) kỳ vọng** | **O(nw)** |
| **y-fast trie** | **O(log w) kỳ vọng** | **O(log w) kỳ vọng, khấu hao** trong biến thể ngẫu nhiên hóa chuẩn | **O(n) kỳ vọng** |

Ở đây `n` là số khóa đang lưu và `w` là độ dài khóa theo bit. Vì `w=\log_2 U` khi `U` là lũy thừa của hai:

\[
\boxed{\log w=\Theta(\log\log U).}
\]

**Các bảo đảm có điều kiện.** Từ “kỳ vọng” phản ánh giả định bảng băm tra cứu O(1) kỳ vọng và, đối với y-fast, cách duy trì đại diện/nhóm bằng ngẫu nhiên hóa hoặc cơ chế có chứng minh tương ứng. Không thể tự thay các giới hạn đó bằng “O(log log U) worst-case” cho mọi bảng băm và mọi cách chia nhóm.

Bài học này thuộc chương **Khóa số nguyên** của mô-đun cấu trúc dữ liệu. Ta sẽ đi từ biểu diễn bit, bảng băm theo tiền tố, liên kết các lá, tìm tiền nhiệm/kế nhiệm, đến cách y-fast cân bằng thời gian–bộ nhớ. Phần thực hành cài đặt **x-fast trie đầy đủ ở mức học thuật bằng Java**, kèm bộ kiểm tra bất biến và kiểm thử đối chiếu với `TreeSet`; đồng thời mô phỏng các nhóm đại diện để người học hiểu thành phần cấu tạo của y-fast mà **không nhận nhầm mô phỏng là triển khai y-fast chuẩn**.

## 1. Mô hình khóa nguyên và bài toán ordered set

Giả sử miền khóa có `U` giá trị và mỗi khóa biểu diễn thành một chuỗi nhị phân **đúng `w` bit**:

\[
\mathcal U=\{0,1,\ldots,2^w-1\},\qquad U=2^w.
\]

Tập hiện có:

\[
S\subseteq\mathcal U,\qquad n=|S|.
\]

**Cần phân biệt `U` và `n`:** `U` là số khóa có thể có, còn `n` chỉ là số khóa đang hiện diện. Ví dụ một miền ID 32 bit có hàng tỷ giá trị khả dĩ, trong khi tập đang lưu chỉ vài nghìn ID.

Các truy vấn:

| Tên | Định nghĩa | Với `S=\{2,3,6,10,14\}` |
| --- | --- | --- |
| `member(x)` | `x\in S`? | `member(6)=true` |
| `predecessor(x)` hoặc `lower(x)` | `\max\{y\in S:y<x\}` | `predecessor(10)=6` |
| `successor(x)` hoặc `higher(x)` | `\min\{y\in S:y>x\}` | `successor(10)=14` |
| `floor(x)` | `\max\{y\in S:y\le x\}` | `floor(10)=10` |
| `ceiling(x)` | `\min\{y\in S:y\ge x\}` | `ceiling(9)=10` |
| `minimum()` | Khóa nhỏ nhất hiện có | 2 |
| `maximum()` | Khóa lớn nhất hiện có | 14 |
| `add(x)`, `remove(x)` | Thêm/xóa khóa nếu phù hợp | Thay đổi `S` |

Các phép tìm tiền nhiệm và kế nhiệm trong bài là **nghiêm ngặt**, dùng dấu `<` và `>`. Khi không có khóa thỏa điều kiện, kết quả là **không có** (*not found*). Đừng dùng `-1` để báo không tìm thấy nếu `-1` có thể là một khóa hợp lệ.

### Khóa hỏi không cần nằm trong tập

`predecessor(9)=6` và `successor(9)=10` đều có nghĩa dù 9 chưa được chèn. Cấu trúc ordered set trả lời về **mối quan hệ thứ tự**, không chỉ về membership.

### Chi phí các lựa chọn quen thuộc

- **Mảng địa chỉ trực tiếp / bitset:** membership O(1) với miền đã cấp phát; nhưng tìm phần tử kế tiếp bằng quét có thể phụ thuộc `U`.
- **Bảng băm:** membership O(1) trung bình/kỳ vọng; không duy trì tiền nhiệm/kế nhiệm theo thứ tự.
- **Mảng đã sắp:** tìm bằng binary search O(log n), nhưng chèn/xóa giữa mảng phải dịch O(n) phần tử.
- **Cây AVL/Red-Black:** membership và tiền nhiệm/kế nhiệm O(log n) worst-case, dùng O(n) nút.
- **Trie nhị phân chưa nén:** đi một bit mỗi tầng, thời gian O(w); có thể dùng O(nw) nút.
- **x-fast/y-fast:** dùng bảng băm tiền tố để giảm số tầng phải thử khi tìm lân cận.

Mục tiêu không phải chứng minh mọi cấu trúc mới đều nhanh hơn trong thực tế, mà hiểu **vì sao kết hợp dữ liệu theo thứ tự với tra cứu tiền tố bằng bảng băm tạo ra một đánh đổi khác**.

## 2. Đường đi bit trong trie và từ “tiền tố”

Với khóa `w` bit, xét dãy:

\[
x=b_{w-1}b_{w-2}\cdots b_1b_0.
\]

Trie nhị phân trong bài đọc bit **từ cao xuống thấp** (*MSB-first*). Ở tầng đầu tiên, ta chọn nhánh 0 hoặc 1 theo `b_{w-1}`; ở tầng cuối, theo `b_0`.

Ví dụ với `w=4`:

| Khóa | Mã 4 bit | Tiền tố 1 bit | Tiền tố 2 bit | Tiền tố 3 bit | Tiền tố 4 bit |
| ---: | --- | --- | --- | --- | --- |
| 2 | `0010` | `0` | `00` | `001` | `0010` |
| 3 | `0011` | `0` | `00` | `001` | `0011` |
| 6 | `0110` | `0` | `01` | `011` | `0110` |
| 10 | `1010` | `1` | `10` | `101` | `1010` |
| 14 | `1110` | `1` | `11` | `111` | `1110` |

Một **tiền tố độ dài `d`** giữ đúng `d` bit cao nhất và bỏ đi `w-d` bit thấp:

\[
\boxed{
prefix_d(x)=\left\lfloor \frac{x}{2^{w-d}}\right\rfloor
=x\operatorname{>>>}(w-d)
}
\]

cho `0\le d\le w` và biểu diễn không dấu. Tiền tố độ dài 0 là **tiền tố rỗng**, có duy nhất một giá trị 0.

### Tiền tố tồn tại là gì?

Một tiền tố `p` dài `d` được gọi là **hiện diện** nếu có ít nhất một khóa đang lưu bắt đầu bằng tiền tố đó:

\[
\boxed{
p\in P_d
\iff
\exists x\in S:\ prefix_d(x)=p.
}
\]

Các bảng tiền tố cho ví dụ:

```text
S = {0010, 0011, 0110, 1010, 1110}

d=0: { ε }
d=1: { 0, 1 }
d=2: { 00, 01, 10, 11 }
d=3: { 001, 011, 101, 111 }
d=4: { 0010, 0011, 0110, 1010, 1110 }
```

**Tính chất đơn điệu quan trọng:** nếu một tiền tố độ dài `d` của `x` **không tồn tại**, thì mọi tiền tố **dài hơn `d`** của chính `x` cũng **không tồn tại**. Ngược lại, nếu tiền tố dài `d` tồn tại thì mọi tiền tố ngắn hơn của nó cũng tồn tại.

Chính tính đơn điệu theo **độ dài tiền tố** này cho phép **binary search trên các tầng**, không phải binary search trên giá trị khóa.

## 3. x-fast trie: bảng băm cho mọi độ dài tiền tố

Một **x-fast trie** xây trên trie MSB-first nhưng không chỉ dựa vào con trỏ từ gốc. Nó tạo một bảng tra cứu cho **mỗi độ dài tiền tố**:

\[
H_0,H_1,\ldots,H_w.
\]

Với mỗi `d`, `H_d` lưu những tiền tố độ dài `d` đang có. Giá trị đi kèm một tiền tố có thể trỏ đến nút trie tương ứng và thông tin định vị các lá trong cây con.

```text
                           Mã khóa w bit
                                  |
                 +----------------+---------------+
                 |                |               |
             H_0: {ε}         H_1: {0,1}        ...
                                  |
                           H_d[prefix_d(x)]
                                  |
                           Nút tiền tố p
                           /           \
                       child 0       child 1
                            \          /
                     các lá của tập S ở tầng w
```

Điểm mới so với trie thông thường: thay vì muốn tới một nút ở độ sâu 16 phải đi qua 16 cạnh, ta có thể **tra `H_{16}[prefix_{16}(x)]` trực tiếp** bằng bảng băm.

### Mỗi nút tiền tố cần biết gì?

Để xử lý predecessor/successor khi nhánh truy vấn không tồn tại, thường có hai cách liên quan:

1. **Jump pointer:** một con trỏ hỗ trợ nhảy trực tiếp tới lá biên (min/max phù hợp) trong cây con hoặc tới lá lân cận, tùy bất biến biến thể.
2. **Con trỏ biên của cây con:** lưu `firstLeaf` và `lastLeaf` cho mỗi tiền tố hiện diện, sau đó dùng liên kết `prev/next` giữa các lá.

Cả hai phục vụ mục đích: **khi đã tìm thấy điểm khác biệt bit đầu tiên, xác định lá trước/sau trong O(1)** thay vì đi tiếp O(w) tầng.

Bài thực hành sử dụng cách **`firstLeaf/lastLeaf`**. Trong tài liệu thuật toán x-fast chuẩn, ta thường gặp khái niệm **jump pointers**; không nên cho rằng tất cả các biến thể buộc phải lưu chính xác cùng một loại con trỏ.

### Lá được nối thành danh sách tăng dần

```text
   prev     next
  <----    ---->
 [ 2 ] <-> [ 3 ] <-> [ 6 ] <-> [ 10 ] <-> [ 14 ]
   ^                                         ^
  min                                       max
```

Một lá chứa khóa đầy đủ và con trỏ `prev`, `next`. Khi đã biết một lá là **trước hoặc sau** truy vấn, các lá lân cận cung cấp predecessor/successor ngay.

**Bất biến:** danh sách lá chứa **đúng các khóa đang có**, theo **thứ tự tăng nghiêm ngặt**, không có khóa trùng. Đầu/cuối danh sách phản ánh minimum/maximum.

## 4. Tìm kiếm nhị phân trên độ dài tiền tố

Giả sử `x` **chưa có trong tập**. Cần tìm:

\[
d^*=\max\{d:prefix_d(x)\in H_d\}.
\]

Đây là độ dài của **tiền tố dài nhất của `x` vẫn có mặt** trong các khóa đã lưu. Nó có thể bằng 0 nếu hai nhánh gốc không khớp ngay bit đầu, nhưng không thể bằng `w` nếu `x` thật sự vắng mặt.

### Mã giả

```text
longestExistingPrefix(x):
    require S is nonempty
    require x is not stored

    lo = 0
    hi = w - 1
    while lo < hi:
        mid = ceil((lo + hi) / 2)
        if H_mid contains prefix_mid(x):
            lo = mid
        else:
            hi = mid - 1

    return H_lo[prefix_lo(x)]
```

Vì bảng `H_0` có tiền tố rỗng khi tập không rỗng, thuật toán luôn có điểm bắt đầu.

**Lưu ý tránh vòng lặp vô hạn:** khi tìm giá trị `d` lớn nhất thỏa điều kiện, dùng `mid=(lo+hi+1)/2`, làm tròn **lên**. Nếu lấy phần nguyên làm tròn xuống khi `hi=lo+1` và giữ `lo=mid`, vòng lặp có thể không tiến triển.

### Truy vết `w=4`

Với `S=\{2,3,6,10,14\}`:

```text
S ở 4 bit: 0010 0011 0110 1010 1110

Truy vấn x=9 = 1001

d=0: ε    có
d=1: 1    có
d=2: 10   có  (khóa 10=1010 có tiền tố 10)
d=3: 100  không có
d=4: 1001 không có

=> d*=2, nút tiền tố "10".
```

Tại nút này, bit tiếp theo của `x=1001` là **0**, nhưng mọi khóa dưới tiền tố `10` hiện có đều đi nhánh **1** (khóa 10 là `1010`). Do đó:

- Toàn bộ khóa ở nhánh còn lại **lớn hơn `x`**.
- Lá nhỏ nhất của nhánh đó là **10** → `successor(9)=10`.
- Lá ngay trước 10 là **6** → `predecessor(9)=6`.

Với `x=11=1011`, tiền tố `101` tồn tại nhưng nhánh bit cuối 1 vắng:

```text
x=1011, d*=3, tiền tố "101"
bit tiếp theo của x là 1 (vắng)
nhánh 0 còn lại giữ 1010 = 10

predecessor(11)=10
successor(11)=14
```

### Hai trường hợp đối xứng tại nút cuối cùng còn chung tiền tố

Gọi `v` là nút với tiền tố dài nhất còn tồn tại. Ở bit **tiếp theo** của `x`, nhánh cần đi theo `x` bị thiếu; nhánh còn lại có ít nhất một khóa.

**Trường hợp bit của `x` là 0, nhánh 0 thiếu:**

```text
              v
           0 / \ 1
       không    nhánh có khóa
        có           |
                firstLeaf -> next lớn hơn x
                    |
                   .prev -> predecessor của x
```

Mọi khóa ở nhánh 1 đều lớn hơn `x`, nên:

\[
\operatorname{succ}(x)=firstLeaf(v.one),
\quad
\operatorname{pred}(x)=\operatorname{prev}(\operatorname{succ}(x)).
\]

**Trường hợp bit của `x` là 1, nhánh 1 thiếu:**

```text
              v
           0 / \ 1
     nhánh có  không
        khóa     có
         |
     lastLeaf -> predecessor của x
         |
        .next -> successor của x
```

Mọi khóa ở nhánh 0 đều nhỏ hơn `x`, nên:

\[
\operatorname{pred}(x)=lastLeaf(v.zero),
\quad
\operatorname{succ}(x)=\operatorname{next}(\operatorname{pred}(x)).
\]

### Nếu `x` đã có mặt?

Tra trực tiếp `H_w[prefix_w(x)]`:

- Nếu có lá `x`: `predecessor(x)=x.prev`, `successor(x)=x.next`.
- Với `floor(x)` và `ceiling(x)`, cả hai đều là `x`.

Đây là một lần tra bảng băm ở mức khóa đầy đủ, kỳ vọng O(1) khi giả định hash dictionary O(1) kỳ vọng.

### Tại sao chỉ còn O(log w) lần tra bảng?

Có `w+1` độ dài tiền tố, nhưng các câu hỏi “tiền tố độ dài `d` này có tồn tại không?” là một dãy **đúng trước, sai sau** theo `d`. Binary search tìm chuyển tiếp bằng O(log w) lần tra bảng. Sau khi có nút `v`, lấy con trỏ biên và `prev/next` mất O(1).

Vì vậy:

\[
\boxed{\mathbb E[T_{\mathrm{pred/succ}}]=O(\log w)=O(\log\log U)}
\]

dưới giả định **mỗi phép tra bảng băm có O(1) kỳ vọng** và các con trỏ biên/lá được bảo trì đúng.

Đây **không phải** binary search trong một mảng `n` khóa, cũng **không phải** O(log n) theo số phần tử.

## 5. Bất biến dữ liệu của x-fast trie

Với mỗi tầng độ sâu `d`:

1. `H_d` chứa **đúng các tiền tố độ dài `d` của khóa đang có**. Không giữ tiền tố của khóa đã xóa nếu nó không còn đường tới một khóa hiện diện.
2. Mỗi mục `H_d[p]` trỏ tới **đúng nút** đại diện cho tiền tố `p` tại tầng `d`.
3. Mỗi nút khác gốc có một cha tại tầng `d-1`, và cạnh từ cha ứng với bit mới của tiền tố.
4. `count(v)` bằng số khóa có tiền tố `v`, nếu dùng bộ đếm.
5. `firstLeaf(v)` và `lastLeaf(v)` lần lượt là khóa nhỏ nhất/lớn nhất trong cây con của tiền tố `v`.
6. Những lá độ sâu `w` ứng với **một-một các khóa**; mỗi lá đầy đủ xuất hiện một lần trong danh sách liên kết tăng dần.
7. Mọi cặp lá liên tiếp thỏa `a.next=b` thì `b.prev=a`, và `a.key<b.key`.
8. Tập rỗng có thể giữ một nút gốc với `count=0`, nhưng các tầng có độ dài dương không được giữ mục tiền tố hoạt động.

Các bất biến này đảm bảo tra hash cho tiền tố không xuất hiện “dương tính giả”, và khi x-fast nhảy ra một lá biên thì đó đúng là khóa gần nhất theo thứ tự.

### Vì sao không thể chỉ băm khóa đầy đủ?

Nếu chỉ có `H_w`, ta tìm được membership nhưng không biết **độ sâu tiền tố cuối cùng còn chung**. Toàn bộ cải tiến x-fast dựa trên việc hỏi được những tiền tố trung gian ở **nhiều độ dài**.

### Vì sao không thể chỉ có các bảng tiền tố mà bỏ lá biên?

Biết tiền tố dài nhất ở độ sâu `d^*` chưa đủ để trả ngay predecessor/successor nếu phải **đi tiếp từ nút ấy xuống một lá**; con đường đó có thể mất O(w) bước. Con trỏ `jump` hoặc `first/lastLeaf` tránh bước tìm sâu, mới giữ được truy vấn O(log w).

## 6. Chèn/xóa trong x-fast trie

### Chèn khóa mới `x`

1. Kiểm tra xem khóa `x` đã có hay chưa qua `H_w`.
2. Xác định lá `prev`, `next` sẽ đứng cạnh `x` trong danh sách tăng dần.
3. Tạo những nút tiền tố còn thiếu trên đường của `x`; ở mỗi tầng tương ứng, chèn mục `prefix_d(x)` vào `H_d`.
4. Tăng `count` dọc các nút đi qua; cập nhật `firstLeaf`, `lastLeaf` nếu khóa mới trở thành biên.
5. Liên kết lá `x` vào đúng chỗ giữa `prev` và `next`.

Trên một đường chỉ có tối đa `w` độ dài tiền tố khác gốc. Do đó, **một lần cập nhật có thể làm thay đổi O(w) bảng hash**. Nếu mỗi thao tác hash O(1) kỳ vọng:

\[
\boxed{\mathbb E[T_{\mathrm{insert}}]=O(w).}
\]

Ta **không** được suy rằng vì predecessor O(log w), insert cũng O(log w). Tìm điểm cần chèn nhanh không làm biến mất công việc **bảo trì mọi tiền tố thay đổi**.

### Xóa khóa `x`

1. Tra `H_w`; nếu vắng mặt, không thay đổi gì.
2. Gỡ lá `x` khỏi danh sách `prev/next`.
3. Giảm `count` trên các nút của đường đi `x`.
4. Với nút mà `count` trở về 0, **xóa tiền tố khỏi bảng băm của tầng ấy và tháo cạnh từ cha**.
5. Với nút còn khóa, cập nhật `firstLeaf/lastLeaf` từ các nhánh con còn hoạt động.

Vì phải duyệt tối đa `w` nút:

\[
\boxed{\mathbb E[T_{\mathrm{delete}}]=O(w).}
\]

**Một chi tiết rất dễ sai:** nếu xóa khóa 2 nhưng khóa 3 vẫn chia sẻ tiền tố `001`, không được xóa `001` khỏi `H_3`. Chỉ khi **không còn bất kỳ lá nào phía dưới** mới được bỏ tiền tố ấy.

### Mô hình không gian

Mỗi khóa `w` bit đóng góp nhiều nhất **một tiền tố ở mỗi độ dài**, tức tối đa `w` nút mới. Với `n` khóa:

\[
\boxed{\text{số nút tiền tố}\le 1+nw.}
\]

Do đó bộ nhớ cho tất cả các bảng tiền tố, nút và lá là:

\[
\boxed{S_{\mathrm{x-fast}}=O(nw)=O(n\log U)}
\]

theo số mục/từ lưu trữ, với giả định bảng băm có overhead tỷ lệ số mục kỳ vọng. Các khóa chia sẻ tiền tố có thể làm số nút thực tế ít hơn cận trên, nhưng không biến bảo đảm chung thành O(n).

### Tính chất trường hợp xấu nhất

Phép băm không bảo đảm **tất cả phép truy cập đều O(1) worst-case** trong mọi mô hình và triển khai. Để phát biểu chính xác, cần nói rõ:

- Số **phép tra cứu tiền tố** của một truy vấn x-fast: O(log w) trường hợp xấu nhất nếu cấu trúc và con trỏ nhất quán.
- Thời gian thực thi: O(log w) **kỳ vọng** với bảng băm có O(1) kỳ vọng mỗi lần tra.
- Số mức bị cập nhật: O(w); thời gian O(w) kỳ vọng dưới giả định tương tự.

Nếu băm có tình huống va chạm tốn kém, thời gian đo thực tế có thể xấu hơn.

## 7. y-fast trie: chỉ lập chỉ mục các khóa đại diện

Vấn đề của x-fast trie khá rõ: truy vấn predecessor/successor O(log w) kỳ vọng nhưng cần **O(nw) bộ nhớ**, vì gần như mỗi khóa phải đóng góp nhiều tiền tố vào những bảng băm.

**y-fast trie** đặt câu hỏi:

> Có nhất thiết phải đặt **mọi khóa** vào x-fast trie, hay chỉ cần đánh chỉ mục một số **đại diện**, rồi tìm trong nhóm nhỏ tương ứng?

Câu trả lời là: ta có thể chia tập thành những **bucket/nhóm có thứ tự**, mỗi nhóm chứa khoảng `\Theta(w)` khóa theo mức độ kỳ vọng trong thiết kế chuẩn. Chỉ các **khóa đại diện** (*representatives*) mới được đưa vào x-fast trie. Bên trong mỗi nhóm, ta dùng một **cấu trúc có thứ tự**, chẳng hạn cây tìm kiếm nhị phân cân bằng.

```text
                      Tập S có n khóa nguyên
                                |
                    Chọn các khóa đại diện
                                |
                       x-fast trên reps
                                |
          +---------------------+--------------------+
          |                     |                    |
       đại diện r1           đại diện r2          đại diện r3
          |                     |                    |
       bucket B1             bucket B2            bucket B3
       Balanced BST          Balanced BST         Balanced BST
       ~w khóa               ~w khóa              ~w khóa
```

**Vai trò các tầng:**

- **x-fast của đại diện:** nhanh chóng tìm nhóm nằm quanh ngưỡng truy vấn theo tiền tố.
- **Cây cân bằng trong nhóm:** tìm khóa thật, thêm/xóa, lấy min/max của nhóm mà không quét tuyến tính toàn bộ nhóm.
- **Quy tắc duy trì đại diện và kích thước nhóm:** giữ số đại diện khoảng `n/w` và kích thước bucket khoảng `w` theo kỳ vọng/khấu hao của biến thể được chứng minh.

Sự phối hợp này là ví dụ điển hình của **kết hợp hai cấu trúc để bù nhược điểm của nhau**: x-fast mạnh về định vị theo miền số, còn BST mạnh về bộ nhớ theo số phần tử và cập nhật nội bộ trong nhóm nhỏ.

## 8. Ví dụ các bucket và cách tìm lân cận

Giả sử `w=8`, miền `U=2^8=256`. Tập đang lưu:

\[
S=\{3,4,7,12,18,19,20,31,45,48,52,60,90,93\}.
\]

Ta chia thành bốn bucket để minh họa, mỗi bucket được sắp bằng cây cân bằng. Chọn khóa **lớn nhất của bucket** làm đại diện trong ví dụ tĩnh này:

| Bucket | Các khóa | Đại diện minh họa |
| --- | --- | ---: |
| `B_{12}` | `\{3,4,7,12\}` | 12 |
| `B_{31}` | `\{18,19,20,31\}` | 31 |
| `B_{60}` | `\{45,48,52,60\}` | 60 |
| `B_{93}` | `\{90,93\}` | 93 |

Chỉ bốn khóa `\{12,31,60,93\}` nằm trong chỉ mục x-fast. Các khóa còn lại được tìm bằng cây cân bằng tương ứng.

```text
   x-fast trên representatives: [12] <-> [31] <-> [60] <-> [93]
                                  |        |        |        |
                                  v        v        v        v
                                B12      B31      B60      B93
                              3 4 7 12 18..31  45..60   90 93
```

### Tìm `predecessor(50)`

1. Trong x-fast đại diện, tìm đại diện **nhỏ nhất không nhỏ hơn 50**: 60.
2. Chọn `B_{60}=\{45,48,52,60\}`.
3. Hỏi cây cân bằng của bucket: khóa lớn nhất `<50` là **48**.

Vậy:

\[
\operatorname{predecessor}(50)=48.
\]

### Tìm `successor(31)`

Ngưỡng là chính đại diện 31. Bucket `B_{31}` có phần tử lớn nhất 31, nên **không có khóa lớn hơn 31 trong bucket đó**.

1. Tìm bucket tiếp theo qua x-fast: `B_{60}`.
2. Lấy `min(B_{60})=45`.

Vậy:

\[
\operatorname{successor}(31)=45.
\]

Không thể trả đại diện 60 ngay lập tức vì 45 là khóa gần hơn.

### Tìm `predecessor(70)`

1. Đại diện nhỏ nhất `\ge70` là 93.
2. Bucket `B_{93}=\{90,93\}` không có khóa `<70`.
3. Quay sang bucket liền trước `B_{60}`, lấy max 60.

Vậy:

\[
\operatorname{predecessor}(70)=60.
\]

### Vì sao có lúc phải thử bucket kề bên?

Một truy vấn gần **ranh giới** giữa hai nhóm có thể không có lời giải trong bucket được định vị đầu tiên. Phải kiểm tra **bucket bên trái/phải**, nhưng nhờ các bucket được sắp và không chồng lấn theo khoảng khóa, chỉ cần số lượng bucket lân cận **hằng số** sau khi đã định vị đúng nhóm.

**Phạm vi của ví dụ:** chúng ta cố ý dùng **max của bucket làm đại diện** để dễ nhìn. Đây là **snapshot minh họa cách định tuyến**. Nếu sau này thêm khóa lớn hơn max hiện tại, xóa đúng max, gộp hoặc tách bucket, chương trình phải cập nhật đại diện. Chỉ đơn giản tạo bucket theo ý thích rồi giữ nguyên mãi **không đủ** để chứng minh các giới hạn của y-fast trie động chuẩn.

## 9. Vì sao y-fast giảm được không gian xuống O(n)?

Giả sử mỗi bucket chứa **cỡ `w` khóa**, nên số bucket/đại diện cỡ:

\[
r\approx \frac{n}{w}.
\]

Chỉ các đại diện đi vào x-fast trie. Mỗi đại diện tạo O(w) tiền tố, nên chi phí chỉ mục:

\[
O(rw)=O\left(\frac{n}{w}\cdot w\right)=O(n).
\]

Các bucket lưu tổng cộng `n` khóa trong những cây cân bằng, chiếm O(n) nút. Vì vậy:

\[
\boxed{
S_{\mathrm{y-fast}}
=O(n)+O((n/w)\cdot w)
=O(n)
}
\]

theo **kỳ vọng** của việc duy trì khoảng `n/w` đại diện và overhead bảng băm tỷ lệ số mục.

### Trường hợp tập có ít hơn `w` khóa

Nếu `n<w`, vẫn cần ít nhất một nhóm để chứa dữ liệu. Vì vậy nên hiểu:

\[
r=O(1+n/w),
\]

và chi phí một chỉ mục đại diện có thể tạo một phần phụ thuộc `w`. Trong nhiều phân tích RAM chuẩn, `w=O(\log U)` được coi là kích thước từ và `n` đủ lớn cho cận `O(n)`, hoặc dùng **nhóm đặc biệt/không tạo chỉ mục x-fast** khi `n` nhỏ để tránh trả O(w) tiền tố chỉ cho một vài khóa.

Đối với bản thiết kế tổng quát cam kết O(n) không gian, ta **phải xử lý trường hợp n rất nhỏ**, chẳng hạn lưu thẳng các khóa trong một cây cân bằng khi chưa đủ một nhóm. Không thể bỏ qua chi tiết biên này rồi tuyên bố mọi cài đặt tự động dùng đúng O(n).

### Không gian trung bình và cận xấu nhất của bucket

Nếu chọn mỗi khóa thành đại diện một cách **ngẫu nhiên với xác suất xấp xỉ `1/w`**, khoảng cách giữa các đại diện liên tiếp có số khóa kỳ vọng O(w). Điều đó **không** có nghĩa mọi bucket chắc chắn có đúng `w` khóa: có thể có bucket dài hơn nhiều.

Một số thiết kế dùng **ngưỡng tách/gộp**, chiến lược đại diện thích hợp hoặc phân tích xác suất để đảm bảo những giới hạn mong muốn. Cần nêu rõ biến thể trước khi kết luận **worst-case** cho từng bucket; không lấy “kích thước kỳ vọng O(w)” làm bằng chứng rằng mọi lần tìm trong bucket là O(log w) worst-case.

## 10. Truy vấn trong y-fast: hai bước định vị

Hãy tách phép `predecessor(x)` thành hai phần:

1. **Định vị đại diện bằng x-fast:** tìm một bucket có miền khóa liên quan tới `x`, dựa trên tiền nhiệm/kế nhiệm của các đại diện.
2. **Tìm trong bucket:** dùng `lower/floor` của cây cân bằng; nếu cần, kiểm tra bucket liền kề và lấy min/max của nó.

Nếu bucket chứa `b` phần tử:

\[
T_{\mathrm{query}}
=O(\log w)+O(\log(b+1))
\]

theo kỳ vọng cho phần x-fast. Nếu thiết kế đảm bảo `b=O(w)` ở mức cần thiết thì:

\[
\boxed{\mathbb E[T_{\mathrm{query}}]=O(\log w).}
\]

Trong biến thể đại diện được lấy mẫu ngẫu nhiên với kích thước bucket kỳ vọng O(w), có thể dùng tính lõm của log để giải thích vì sao **kỳ vọng** của chi phí tìm kiếm cân bằng vẫn O(log w) khi điều kiện phân bố và chọn bucket phù hợp:

\[
\mathbb E[\log(b+1)]
\le \log(\mathbb E[b]+1)
=O(\log w).
\]

Điều kiện “bucket được chọn phù hợp” quan trọng: **không được dùng một kỳ vọng chỉ cho bucket chọn ngẫu nhiên đều rồi suy ngay cho bucket chứa một khóa truy vấn cố định**, vì phân bố bucket mà truy vấn gặp có thể bị lệch theo kích thước. Phân tích y-fast chuẩn xử lý chi tiết chọn mẫu và truy vấn này.

### Membership trong y-fast

Khác x-fast, đa số khóa **không** xuất hiện trong bảng băm tiền tố đầy đủ. Do vậy:

- Một y-fast kiểu bucket có thể tìm membership bằng cách **xác định bucket rồi tìm trong cây cân bằng**, kỳ vọng O(log w).
- Có thể duy trì thêm **một hash set trực tiếp trên tất cả khóa** để có membership O(1) kỳ vọng, đổi lấy O(n) bộ nhớ và chi phí cập nhật bổ sung; đó là **phần thêm của một biến thể**, không mặc định có trong định nghĩa.

Không nên lấy bảo đảm `member(x)` O(1) kỳ vọng của **x-fast** rồi gán cho mọi **y-fast**.

### Minimum/maximum

Nếu các bucket có thứ tự và lưu con trỏ tới bucket đầu/cuối, minimum/maximum có thể lấy trực tiếp hoặc qua đại diện biên trong O(1), nhưng cập nhật phải giữ các con trỏ đúng. Một triển khai y-fast không có cache biên có thể cần truy vấn trên chỉ mục. Khi nói thời gian min/max, hãy chỉ rõ metadata được duy trì.

## 11. Chèn/xóa trong y-fast: chi phí bảo trì đại diện

Một cập nhật bình thường thường bắt đầu bằng:

1. Định vị bucket phù hợp qua x-fast trên đại diện.
2. Chèn/xóa khóa trong cây cân bằng của bucket.
3. Nếu nhóm/đại diện thay đổi theo quy tắc thiết kế, thực hiện **tách, gộp hoặc cập nhật chỉ mục đại diện**.

Phần lớn lần cập nhật không cần thay đổi x-fast trên đại diện. Nhưng một lần thay đổi đại diện trong x-fast có thể mất **O(w)** thao tác băm tiền tố. Muốn có thời gian cập nhật y-fast hấp dẫn, phải **phân bổ chi phí O(w)** này qua nhiều lần cập nhật thông thường.

### Cách nhìn khấu hao bằng tách/gộp nhóm

Giả sử một biến thể duy trì các nhóm kích thước khoảng `w`:

```text
Nhóm bình thường:         ~w khóa
Sau nhiều lần thêm:       nhóm quá lớn
                          -> tách thành hai nhóm, tạo representative mới

Sau nhiều lần xóa:        nhóm quá nhỏ
                          -> mượn/gộp nhóm, điều chỉnh representatives
```

Nếu quy tắc tách/gộp được thiết kế để **không phải trả phí O(w) ở mỗi cập nhật**, ta có thể tính chi phí tái cấu trúc vào các thao tác tạo ra nhu cầu tái cấu trúc. **Chỉ nói “tách/gộp khi cần” chưa đủ để chứng minh O(log w) khấu hao**: cần ngưỡng và lập luận bảo đảm có đủ số cập nhật giữa các lần tái tổ chức tốn kém.

### Cách nhìn ngẫu nhiên hóa bằng đại diện mẫu

Trong cách trình bày y-fast thường gặp, chọn các khóa làm đại diện với xác suất cỡ **`1/w`**. Ý tưởng:

- Xác suất một khóa mới ảnh hưởng đến tập đại diện là nhỏ, khoảng `1/w`.
- Một cập nhật x-fast của đại diện có chi phí cỡ `O(w)` kỳ vọng.
- Phần chi phí kỳ vọng do thay đổi đại diện được phân bổ xấp xỉ `(1/w)\cdot O(w)=O(1)` trên một cập nhật, ngoài công việc trên bucket.

Đây là **trực giác chi phí**, không phải một chứng minh đầy đủ cho mọi trường hợp xóa đại diện, phân chia lại bucket và lựa chọn bucket lệch. Một cấu trúc y-fast chuẩn cần quy tắc duy trì mẫu và các cây cân bằng được phân tích chặt chẽ.

Với những giả định đó, giới hạn phổ biến:

\[
\boxed{
\mathbb E[T_{\mathrm{insert/delete}}]
=O(\log w)\ \text{khấu hao}.
}
\]

Đừng nói `O(\log w)` **worst-case deterministic** cho phiên bản ngẫu nhiên hóa khi chưa có chứng minh và cơ chế cụ thể.

### Cẩn thận nếu dùng max làm representative

Với ví dụ `B_{60}=\{45,48,52,60\}`, nếu xóa 60, khóa đại diện trở thành 52. Nếu **mỗi lần xóa max bucket** đều xóa đại diện cũ khỏi x-fast rồi chèn đại diện mới, một kẻ chọn dữ liệu bất lợi có thể ép cập nhật x-fast O(w) liên tục.

Do đó ví dụ dùng max bucket để **dạy định tuyến** không tự động mang tính chất cập nhật y-fast chuẩn. Phải chọn chiến lược đại diện/nhóm có phân tích cập nhật rõ ràng.

## 12. Tổng hợp độ phức tạp và giả định

Các biểu thức dưới đây dùng:

\[
w=\lceil\log_2 U\rceil,
\]

và mô hình máy có thao tác bit trên khóa `w` bit trong thời gian O(1), cùng **bảng băm kỳ vọng O(1)**. Với miền lũy thừa của 2, `w=\log_2 U`.

| Phép toán | Binary trie chưa nén | x-fast trie | y-fast trie chuẩn (ngẫu nhiên hóa) |
| --- | --- | --- | --- |
| `member(x)` | O(w) | **O(1) kỳ vọng** qua bảng khóa đầy đủ | **O(log w) kỳ vọng** qua chỉ mục và bucket, nếu không có hash phụ |
| `predecessor/successor` | O(w) | **O(log w) kỳ vọng** | **O(log w) kỳ vọng** |
| `insert(x)` | O(w) | **O(w) kỳ vọng** | **O(log w) kỳ vọng, khấu hao** |
| `delete(x)` | O(w) | **O(w) kỳ vọng** | **O(log w) kỳ vọng, khấu hao** |
| `minimum/maximum` | O(w) nếu đi xuống, có thể cache | O(1) nếu giữ lá biên | O(1) nếu giữ bucket/lá biên |
| Không gian | O(nw) nút | **O(nw)** mục/nút tiền tố | **O(n) kỳ vọng** với chiến lược duy trì nhóm thích hợp |

### “Kỳ vọng”, “khấu hao” và “trường hợp xấu nhất” khác nhau

- **Worst-case:** cận trên cho **mỗi thao tác** với mọi trạng thái hợp lệ và đầu vào trong mô hình đã nêu.
- **Expected:** trung bình trên lựa chọn ngẫu nhiên của thuật toán hoặc bảng băm, không phải trung bình tùy tiện trên dữ liệu đẹp.
- **Amortized:** tính tổng chi phí trên một **chuỗi thao tác**, phân bổ những lần tái cấu trúc đắt đỏ cho nhiều thao tác rẻ; không hứa mọi lần riêng lẻ đều nhanh.

Một phép cập nhật y-fast có thể kích hoạt split/merge và đổi x-fast representative, do đó chậm hơn giới hạn khấu hao cho **một** thao tác. Một hash table có thể tái băm gây thao tác đơn lẻ đắt; cận kỳ vọng/khấu hao phải được hiểu theo **mô hình bảng băm cụ thể**.

### Nếu kích thước khóa là 32 hoặc 64 bit cố định

Trong Java, `int` có 32 bit; nếu ta cố định `w=32`, `\log w` là một hằng số. Nhưng phát biểu “O(1) vì `w=32`” có thể che giấu:

- Nhiều lần truy cập bảng hash ở các độ sâu khác nhau.
- Chi phí tạo, xóa và cấp phát các nút tiền tố.
- Cache miss do các bảng hash nằm phân tán trong RAM.
- Chi phí hash/object boxing và quản lý bộ nhớ.

Trong giải thuật, nên nêu O(log w) để **giữ được ý nghĩa cách mở rộng theo độ dài khóa**; trong triển khai thực tế, benchmark mới quyết định cấu trúc nào nhanh hơn.

### Có phải `O(\log\log U)` luôn nhanh hơn `O(\log n)`?

Không. Tính tiệm cận theo **hai tham số khác nhau**:

- `O(\log\log U)` giảm theo kích thước **miền khóa**.
- `O(\log n)` tăng theo số khóa **đang lưu**.

Với `n` rất nhỏ, cây cân bằng có thể chỉ cần vài mức và dùng ít đối tượng hơn nhiều. Nếu `U` cực lớn nhưng chỉ có vài khóa, bảng tiền tố hoặc cơ chế phân nhóm có thể không bù được overhead.

## 13. Xử lý khóa âm và thứ tự `int` trong Java

Các mô tả của trie theo bit thường giả định **khóa không dấu**. Trong Java, `int` có dấu:

\[
-2^{31}\le x\le2^{31}-1.
\]

Nếu đơn giản đọc bit cao nhất của `x` rồi chọn nhánh 0 trước nhánh 1, ta sẽ đặt **số không âm trước số âm**, tương ứng thứ tự không dấu, trái với `Integer.compare` và `TreeSet<Integer>`.

### Đảo duy nhất bit dấu

Ta dùng:

```java
long encoded = Integer.toUnsignedLong(
    key ^ Integer.MIN_VALUE);
```

Phép XOR với `Integer.MIN_VALUE` đảo bit dấu, giữ nguyên 31 bit thấp. Khi so mã `encoded` theo thứ tự **không dấu**, thứ tự đúng là thứ tự `int` có dấu của `key`.

Ví dụ rút gọn 8 bit:

| Khóa signed | Mẫu bit | Mã sau đảo bit dấu |
| ---: | --- | --- |
| -128 | `1000 0000` | `0000 0000` |
| -1 | `1111 1111` | `0111 1111` |
| 0 | `0000 0000` | `1000 0000` |
| 127 | `0111 1111` | `1111 1111` |

Do đó những mã đã biến đổi vẫn có các tiền tố chia sẻ giống trie bit thông thường, nhưng **`first/lastLeaf` và `prev/next` phải giữ thứ tự có dấu của khóa gốc**.

### Tránh dịch 32 bit trong kiểu `int`

Trong Java, phép `int >>> 32` được tính như dịch `0` vị trí do số bước dịch bị mask. Vì vậy không dùng:

```java
int prefix0 = code >>> 32; // SAI nếu muốn tiền tố rỗng.
```

Trong bản thực hành, mã được mở rộng sang `long` trước và định nghĩa:

```java
long prefix(long code, int depth) {
    // 0 <= depth <= 32, code in [0, 2^32 - 1].
    return code >>> (32 - depth);
}
```

Với `long`, dịch 32 vị trí là hợp lệ và cho `prefix_0=0`. Trường hợp `depth=32` là dịch 0, giữ nguyên mã 32 bit.

### Khóa ngoài miền trong cấu trúc có `w<32`

Nếu ứng dụng dùng miền `[a,b]` nhỏ, có thể chuẩn hóa `offset=x-a` rồi giới hạn `0\le offset<U`, với phép trừ kiểu `long` để tránh tràn. Khi đó `w=\lceil\log_2 U\rceil` có thể nhỏ hơn 32 và các tiền tố được tính trên **offset**, không phải trực tiếp trên mã bit toàn miền `int`.

**Không trộn hai cách mã hóa:** XOR bit dấu phục vụ **thứ tự toàn miền `int`**, còn `x-a` phục vụ **miền liên tục tùy chọn**. Mỗi cấu trúc phải chọn một biểu diễn khóa nhất quán ở mọi phép cập nhật/truy vấn.

## 14. Java hoàn chỉnh: x-fast trie bằng bảng băm tiền tố và liên kết lá

Để hiểu x-fast ở mức có thể kiểm tra, ta cài đặt một lớp `XFastIntSet` cho **toàn miền `int` có dấu, `w=32`**. Mã sử dụng:

- `HashMap<Long,Node>` cho mỗi độ dài tiền tố `0..32`.
- Mã `Integer.toUnsignedLong(key ^ Integer.MIN_VALUE)` để sắp đúng theo **thứ tự số nguyên có dấu**.
- Cây các `Node` chỉ tạo những **tiền tố thực sự có mặt**.
- `Node.first/last` là lá biên của cây con, đóng vai trò con trỏ nhảy hỗ trợ truy vấn.
- `Leaf.prev/next` tạo danh sách liên kết tăng dần.
- `Node.count` là số lá khóa trong cây con, giúp cắt tiền tố khi xóa.
- `neighbors(x)` tìm tiền tố chung dài nhất bằng **binary search trên 33 bảng độ sâu**, trả đúng ba khả năng: lá nhỏ hơn, lá bằng, lá lớn hơn.

Với HashMap có thời gian thao tác kỳ vọng O(1), các phép `lower/higher/floor/ceiling` dùng **O(log w) lần tra mức tiền tố** nếu khóa vắng; membership trực tiếp ở tầng 32 có O(1) kỳ vọng. Các lần cập nhật tạo/xóa tối đa 32 nút, nên O(w) kỳ vọng.

Đây là bản học thuật có bảo trì đầy đủ các nút, con trỏ biên và danh sách lá, không phải một `TreeSet` được đổi tên. Mã sau đó mới dùng `TreeSet` làm **oracle độc lập**.

### Mã Java — phần 1: cấu trúc và các thao tác

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.TreeMap;
import java.util.TreeSet;

public class XFastYFastPrefixHashDemo {
    private static final int WIDTH = 32;

    static final class Leaf {
        final int key;
        final long code;
        Leaf prev;
        Leaf next;

        Leaf(int key, long code) {
            this.key = key;
            this.code = code;
        }
    }

    static final class Node {
        final int depth;
        final long prefix;
        final Node parent;
        Node zero;
        Node one;
        int count;
        Leaf first;
        Leaf last;
        Leaf leaf; // Non-null only at depth WIDTH.

        Node(int depth, long prefix, Node parent) {
            this.depth = depth;
            this.prefix = prefix;
            this.parent = parent;
        }
    }

    static final class Neighbors {
        final Leaf lower;
        final Leaf exact;
        final Leaf higher;

        Neighbors(Leaf lower, Leaf exact, Leaf higher) {
            this.lower = lower;
            this.exact = exact;
            this.higher = higher;
        }
    }

    static final class XFastIntSet {
        private final HashMap<Long, Node>[] levels;
        private final Node root;
        private int size;

        @SuppressWarnings("unchecked")
        XFastIntSet() {
            levels = (HashMap<Long, Node>[])
                new HashMap[WIDTH + 1];
            for (int d = 0; d <= WIDTH; d++) {
                levels[d] = new HashMap<>();
            }
            root = new Node(0, 0L, null);
            levels[0].put(0L, root);
        }

        private static long encode(int key) {
            return Integer.toUnsignedLong(
                key ^ Integer.MIN_VALUE);
        }

        private static long prefix(long code, int depth) {
            // code is a 32-bit unsigned value stored in long.
            // The depth=0 shift of 32 bits is valid for long.
            return code >>> (WIDTH - depth);
        }

        private static int nextBit(long code, int nextDepth) {
            if (nextDepth < 1 || nextDepth > WIDTH) {
                throw new IllegalArgumentException(
                    "Invalid next depth");
            }
            return (int) ((code >>> (WIDTH - nextDepth)) & 1L);
        }

        int size() {
            return size;
        }

        boolean contains(int key) {
            // Full-key hash table; no root-to-leaf traversal.
            return levels[WIDTH].containsKey(encode(key));
        }

        Integer minimum() {
            return root.first == null ? null : root.first.key;
        }

        Integer maximum() {
            return root.last == null ? null : root.last.key;
        }

        // Find immediate neighbors of any signed int key.
        // For an absent key, binary-search the deepest
        // existing prefix and jump to a subtree boundary.
        private Neighbors neighbors(int key) {
            long code = encode(key);
            Node exactNode = levels[WIDTH].get(code);
            if (exactNode != null) {
                Leaf exact = exactNode.leaf;
                return new Neighbors(
                    exact.prev, exact, exact.next);
            }
            if (size == 0) {
                return new Neighbors(null, null, null);
            }

            // Monotone existence:
            // present at depth d => present at all shorter depths.
            int lo = 0, hi = WIDTH - 1;
            while (lo < hi) {
                int mid = lo + (hi - lo + 1) / 2;
                long p = prefix(code, mid);
                if (levels[mid].containsKey(p)) {
                    lo = mid;
                } else {
                    hi = mid - 1;
                }
            }

            Node boundary = levels[lo].get(prefix(code, lo));
            if (boundary == null) {
                throw new IllegalStateException(
                    "Broken prefix table");
            }
            int desiredBit = nextBit(code, lo + 1);

            if (desiredBit == 0) {
                // Missing 0 child; existing 1 child has
                // the first stored key greater than query.
                if (boundary.zero != null || boundary.one == null) {
                    throw new IllegalStateException(
                        "Missing expected right branch");
                }
                Leaf higher = boundary.one.first;
                return new Neighbors(
                    higher.prev, null, higher);
            } else {
                // Missing 1 child; existing 0 child has
                // the last stored key smaller than query.
                if (boundary.one != null || boundary.zero == null) {
                    throw new IllegalStateException(
                        "Missing expected left branch");
                }
                Leaf lower = boundary.zero.last;
                return new Neighbors(
                    lower, null, lower.next);
            }
        }

        Integer lower(int key) {
            Leaf leaf = neighbors(key).lower;
            return leaf == null ? null : leaf.key;
        }

        Integer higher(int key) {
            Leaf leaf = neighbors(key).higher;
            return leaf == null ? null : leaf.key;
        }

        Integer floor(int key) {
            Neighbors n = neighbors(key);
            Leaf leaf = n.exact != null ? n.exact : n.lower;
            return leaf == null ? null : leaf.key;
        }

        Integer ceiling(int key) {
            Neighbors n = neighbors(key);
            Leaf leaf = n.exact != null ? n.exact : n.higher;
            return leaf == null ? null : leaf.key;
        }

        // Expected O(1) prefix count via the requested level's hash.
        int countWithPrefix(int key, int prefixLength) {
            if (prefixLength < 0 || prefixLength > WIDTH) {
                throw new IllegalArgumentException(
                    "Prefix length must be 0..32");
            }
            long p = prefix(encode(key), prefixLength);
            Node node = levels[prefixLength].get(p);
            return node == null ? 0 : node.count;
        }

        // Add a new leaf and maintain every ancestor prefix.
        boolean add(int key) {
            if (contains(key)) {
                return false;
            }
            if (size == Integer.MAX_VALUE) {
                throw new IllegalStateException("Size overflow");
            }

            long code = encode(key);
            Neighbors n = neighbors(key);
            Leaf added = new Leaf(key, code);

            // Insert the leaf into the sorted doubly linked list.
            added.prev = n.lower;
            added.next = n.higher;
            if (n.lower != null) {
                n.lower.next = added;
            }
            if (n.higher != null) {
                n.higher.prev = added;
            }

            Node current = root;
            current.count++;
            if (current.first == null || key < current.first.key) {
                current.first = added;
            }
            if (current.last == null || key > current.last.key) {
                current.last = added;
            }

            for (int d = 1; d <= WIDTH; d++) {
                int bit = nextBit(code, d);
                Node child = bit == 0
                    ? current.zero : current.one;
                if (child == null) {
                    long p = prefix(code, d);
                    child = new Node(d, p, current);
                    if (bit == 0) {
                        current.zero = child;
                    } else {
                        current.one = child;
                    }
                    levels[d].put(p, child);
                }

                current = child;
                current.count++;
                if (current.first == null
                        || key < current.first.key) {
                    current.first = added;
                }
                if (current.last == null
                        || key > current.last.key) {
                    current.last = added;
                }
            }
            current.leaf = added;
            size++;
            return true;
        }

        // Remove the full leaf, then prune dead prefix nodes.
        boolean remove(int key) {
            long code = encode(key);
            Node terminalNode = levels[WIDTH].get(code);
            if (terminalNode == null) {
                return false;
            }
            Leaf deleted = terminalNode.leaf;

            // Unlink the leaf before recomputing prefix extremes.
            if (deleted.prev != null) {
                deleted.prev.next = deleted.next;
            }
            if (deleted.next != null) {
                deleted.next.prev = deleted.prev;
            }

            for (Node current = terminalNode;
                    current != null; ) {
                Node parent = current.parent;
                current.count--;
                if (current.count == 0) {
                    current.first = null;
                    current.last = null;
                    current.leaf = null;
                    if (parent != null) {
                        levels[current.depth].remove(
                            current.prefix);
                        if (parent.zero == current) {
                            parent.zero = null;
                        } else if (parent.one == current) {
                            parent.one = null;
                        } else {
                            throw new IllegalStateException(
                                "Broken parent pointer");
                        }
                    }
                } else {
                    // For an active internal node, the left
                    // subtree owns first and right owns last.
                    current.first = current.zero != null
                        ? current.zero.first : current.one.first;
                    current.last = current.one != null
                        ? current.one.last : current.zero.last;
                }
                current = parent;
            }
            size--;
            return true;
        }

        List<Integer> keysInOrder() {
            List<Integer> out = new ArrayList<>(size);
            for (Leaf leaf = root.first;
                    leaf != null; leaf = leaf.next) {
                out.add(leaf.key);
            }
            return out;
        }

        int prefixNodeCount() {
            int total = 0;
            for (Map<Long, Node> table : levels) {
                total += table.size();
            }
            return total;
        }

        // Validation methods follow in the next part of this
        // continuous Java listing.

        // Rebuild the active structure from pointers, without
        // relying on the public search/update methods.
        private int verifyNode(
                Node node, Node expectedParent,
                int depth, long expectedPrefix,
                IdentityHashMap<Node, Boolean> seen,
                List<Leaf> discovered) {
            if (node == null) {
                return 0;
            }
            if (seen.put(node, Boolean.TRUE) != null) {
                throw new IllegalStateException(
                    "Cycle or aliased prefix node");
            }
            if (node.parent != expectedParent
                    || node.depth != depth
                    || node.prefix != expectedPrefix
                    || levels[depth].get(expectedPrefix) != node) {
                throw new IllegalStateException(
                    "Prefix table/path inconsistency");
            }

            if (depth == WIDTH) {
                if (node.count != 1
                        || node.leaf == null
                        || node.leaf.code != expectedPrefix
                        || node.leaf.key !=
                            (int) (expectedPrefix ^ 0x80000000L)
                        || node.zero != null || node.one != null
                        || node.first != node.leaf
                        || node.last != node.leaf) {
                    throw new IllegalStateException(
                        "Invalid full-key leaf");
                }
                discovered.add(node.leaf);
                return 1;
            }

            if (node.leaf != null) {
                throw new IllegalStateException(
                    "Internal prefix with leaf payload");
            }
            int left = verifyNode(
                node.zero, node, depth + 1,
                expectedPrefix << 1, seen, discovered);
            int right = verifyNode(
                node.one, node, depth + 1,
                (expectedPrefix << 1) | 1L, seen, discovered);

            if (node.count != left + right
                    || (depth > 0 && node.count == 0)) {
                throw new IllegalStateException(
                    "Broken subtree count");
            }
            Leaf expectedFirst = left > 0
                ? node.zero.first
                : right > 0 ? node.one.first : null;
            Leaf expectedLast = right > 0
                ? node.one.last
                : left > 0 ? node.zero.last : null;
            if (node.first != expectedFirst
                    || node.last != expectedLast) {
                throw new IllegalStateException(
                    "Broken first/last jump pointers");
            }
            return left + right;
        }

        void verify() {
            IdentityHashMap<Node, Boolean> seen =
                new IdentityHashMap<>();
            List<Leaf> leaves = new ArrayList<>();
            int counted = verifyNode(
                root, null, 0, 0L, seen, leaves);

            if (counted != size || root.count != size
                    || (size == 0 &&
                        (root.zero != null || root.one != null))) {
                throw new IllegalStateException(
                    "Wrong root cardinality");
            }

            // Every table entry must be a genuinely reachable node.
            int entries = 0;
            for (int d = 0; d <= WIDTH; d++) {
                for (Map.Entry<Long, Node> entry
                        : levels[d].entrySet()) {
                    Node node = entry.getValue();
                    if (!seen.containsKey(node)
                            || node.depth != d
                            || node.prefix != entry.getKey()) {
                        throw new IllegalStateException(
                            "Extraneous prefix hash entry");
                    }
                    entries++;
                }
            }
            if (entries != seen.size()) {
                throw new IllegalStateException(
                    "Missing or duplicate hash entries");
            }

            // Prefix DFS visits the leaves in signed key order.
            Leaf previous = null;
            for (Leaf leaf : leaves) {
                if (leaf.prev != previous
                        || (previous != null &&
                          (previous.next != leaf
                           || previous.key >= leaf.key))) {
                    throw new IllegalStateException(
                        "Broken sorted leaf links");
                }
                previous = leaf;
            }
            if (previous != root.last
                    || (previous != null && previous.next != null)
                    || (size > 0 && root.first != leaves.get(0))) {
                throw new IllegalStateException(
                    "Broken first/last leaf boundary");
            }
        }
    }

    // A STATIC bucket snapshot for explaining y-fast routing.
    // It is NOT a dynamically maintained y-fast trie:
    // no split/merge, no sampling or amortized update guarantee.
    static final class RepresentativeBucketSnapshot {
        private final TreeMap<Integer, TreeSet<Integer>> buckets =
            new TreeMap<>();
        private final XFastIntSet representatives =
            new XFastIntSet();

        void addBucket(int... values) {
            if (values.length == 0) {
                throw new IllegalArgumentException("Empty bucket");
            }
            TreeSet<Integer> bucket = new TreeSet<>();
            for (int value : values) {
                if (!bucket.add(value)) {
                    throw new IllegalArgumentException(
                        "Duplicate key in bucket");
                }
            }
            Integer previousRep = representatives.maximum();
            if (previousRep != null
                    && bucket.first() <= previousRep) {
                throw new IllegalArgumentException(
                    "Buckets must be in disjoint ascending ranges");
            }
            int representative = bucket.last();
            buckets.put(representative, bucket);
            representatives.add(representative);
        }

        // Largest key strictly less than x.
        Integer lower(int x) {
            Integer chosen = representatives.ceiling(x);
            if (chosen == null) {
                chosen = representatives.maximum();
            }
            if (chosen == null) {
                return null;
            }
            Integer inside = buckets.get(chosen).lower(x);
            if (inside != null) {
                return inside;
            }
            Integer prior = representatives.lower(chosen);
            return prior == null ? null : buckets.get(prior).last();
        }

        // Smallest key strictly greater than x.
        Integer higher(int x) {
            Integer chosen = representatives.ceiling(x);
            if (chosen == null) {
                return null;
            }
            Integer inside = buckets.get(chosen).higher(x);
            if (inside != null) {
                return inside;
            }
            Integer after = representatives.higher(chosen);
            return after == null ? null : buckets.get(after).first();
        }

        List<Integer> representativeKeys() {
            return representatives.keysInOrder();
        }

        void verifyRouting() {
            representatives.verify();
            TreeSet<Integer> oracle = new TreeSet<>();
            for (Map.Entry<Integer, TreeSet<Integer>> entry
                    : buckets.entrySet()) {
                TreeSet<Integer> bucket = entry.getValue();
                if (bucket.isEmpty()
                        || !Objects.equals(bucket.last(),
                                           entry.getKey())) {
                    throw new IllegalStateException(
                        "Invalid snapshot representative");
                }
                oracle.addAll(bucket);
            }
            if (!representatives.keysInOrder().equals(
                    new ArrayList<>(buckets.keySet()))) {
                throw new IllegalStateException(
                    "Representative list differs from buckets");
            }
            for (int q = -10; q <= 270; q++) {
                if (!Objects.equals(lower(q), oracle.lower(q))
                        || !Objects.equals(higher(q),
                                           oracle.higher(q))) {
                    throw new IllegalStateException(
                        "Bucket routing mismatch for " + q);
                }
            }
        }
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new IllegalStateException(message);
        }
    }

    private static void compareAgainst(
            XFastIntSet set, TreeSet<Integer> oracle) {
        set.verify();
        require(set.size() == oracle.size(),
                "Wrong total size");
        require(set.keysInOrder().equals(new ArrayList<>(oracle)),
                "Wrong leaf traversal");
        Integer first = oracle.isEmpty()
            ? null : oracle.first();
        Integer last = oracle.isEmpty()
            ? null : oracle.last();
        require(Objects.equals(set.minimum(), first),
                "Wrong minimum");
        require(Objects.equals(set.maximum(), last),
                "Wrong maximum");

        int[] probes = {
            Integer.MIN_VALUE, -1000, -8, -7, -1,
            0, 1, 2, 3, 5, 6, 9, 10, 11, 14,
            100, Integer.MAX_VALUE
        };
        for (int key : probes) {
            require(set.contains(key) == oracle.contains(key),
                    "Membership mismatch for " + key);
            require(Objects.equals(set.lower(key), oracle.lower(key)),
                    "Lower mismatch for " + key);
            require(Objects.equals(set.floor(key), oracle.floor(key)),
                    "Floor mismatch for " + key);
            require(Objects.equals(
                    set.ceiling(key), oracle.ceiling(key)),
                    "Ceiling mismatch for " + key);
            require(Objects.equals(
                    set.higher(key), oracle.higher(key)),
                    "Higher mismatch for " + key);
        }

        // Check prefix counts against an independent scan of
        // the oracle. The same signed-order encoding is used.
        int[] depths = {0, 1, 2, 8, 16, 31, 32};
        for (int depth : depths) {
            for (int key : probes) {
                long wanted = XFastIntSet.prefix(
                    XFastIntSet.encode(key), depth);
                int expected = 0;
                for (int stored : oracle) {
                    long p = XFastIntSet.prefix(
                        XFastIntSet.encode(stored), depth);
                    if (p == wanted) {
                        expected++;
                    }
                }
                require(set.countWithPrefix(key, depth) == expected,
                        "Prefix count mismatch");
            }
        }
    }

    public static void main(String[] args) {
        XFastIntSet set = new XFastIntSet();
        TreeSet<Integer> reference = new TreeSet<>();

        int[] keys = {
            Integer.MIN_VALUE, -7, -1,
            0, 2, 3, 6, 10, 14, Integer.MAX_VALUE
        };
        for (int key : keys) {
            require(set.add(key) == reference.add(key),
                    "Initial insertion mismatch");
        }
        compareAgainst(set, reference);

        System.out.println("x-fast size=" + set.size());
        System.out.println("x-fast min=" + set.minimum());
        System.out.println("x-fast max=" + set.maximum());
        System.out.println("lower(9)=" + set.lower(9));
        System.out.println("higher(9)=" + set.higher(9));
        System.out.println("floor(10)=" + set.floor(10));
        System.out.println("ceiling(9)=" + set.ceiling(9));
        System.out.println("negative keys="
            + set.countWithPrefix(-1, 1));
        System.out.println("nonnegative keys="
            + set.countWithPrefix(0, 1));

        System.out.println("remove(3)=" + set.remove(3));
        reference.remove(3);
        System.out.println("higher(2) after removal="
            + set.higher(2));
        System.out.println("add(3)=" + set.add(3));
        reference.add(3);
        System.out.println("add(3) again=" + set.add(3));
        compareAgainst(set, reference);

        Random random = new Random(20261128L);
        for (int step = 0; step < 500; step++) {
            int key = step % 23 == 0
                ? Integer.MIN_VALUE
                : step % 29 == 0
                    ? Integer.MAX_VALUE
                    : random.nextInt(101) - 50;
            boolean adding = random.nextBoolean();
            boolean expected = adding
                ? reference.add(key) : reference.remove(key);
            boolean actual = adding
                ? set.add(key) : set.remove(key);
            require(expected == actual,
                    "Update mismatch at step " + step);
            compareAgainst(set, reference);
        }
        System.out.println("Randomized x-fast updates: 500");

        RepresentativeBucketSnapshot snapshot =
            new RepresentativeBucketSnapshot();
        snapshot.addBucket(3, 4, 7, 12);
        snapshot.addBucket(18, 19, 20, 31);
        snapshot.addBucket(45, 48, 52, 60);
        snapshot.addBucket(90, 93);
        snapshot.verifyRouting();

        System.out.println("representatives="
            + snapshot.representativeKeys());
        System.out.println("snapshot lower(50)="
            + snapshot.lower(50));
        System.out.println("snapshot higher(31)="
            + snapshot.higher(31));
        System.out.println("snapshot lower(70)="
            + snapshot.lower(70));
        System.out.println("All invariants: OK");
    }
}
```

### Đầu ra dự kiến

```text
x-fast size=10
x-fast min=-2147483648
x-fast max=2147483647
lower(9)=6
higher(9)=10
floor(10)=10
ceiling(9)=10
negative keys=3
nonnegative keys=7
remove(3)=true
higher(2) after removal=6
add(3)=true
add(3) again=false
Randomized x-fast updates: 500
representatives=[12, 31, 60, 93]
snapshot lower(50)=48
snapshot higher(31)=45
snapshot lower(70)=60
All invariants: OK
```

**Ghi chú về đầu ra:** Các dòng ngẫu nhiên chỉ in **số lần kiểm tra**, không in tập cuối nên nội dung mô phỏng không phụ thuộc người học phải tính thủ công 500 thao tác. Các đầu ra trên là kết quả suy ra từ logic chương trình; bước viết bài của tài liệu không thay thế việc biên dịch và chạy code độc lập ở giai đoạn kiểm thử chuyên sâu.

### Điểm đáng chú ý trong mã x-fast

**Thứ nhất, `levels[d]` chứa tiền tố thực sự có mặt.** `prefix(code,d)` tính bằng `long` để tiền tố rỗng ở `d=0` đúng và không gặp lỗi `int >>> 32`. Giá trị trong map là con trỏ `Node`, không chỉ một cờ boolean.

**Thứ hai, tìm kiếm binary search không đi từng nút.** `neighbors` hỏi các `HashMap` ở những tầng được chọn; nếu khóa vắng, nó tìm độ sâu chung dài nhất rồi dùng `first/last` của nhánh còn lại và liên kết `prev/next`. Đây là phần tạo ra O(log w) lần tra bảng, thay vì O(w) bước lần theo trie.

**Thứ ba, các lá được sắp theo khóa Java có dấu.** Hàm `encode` đảo bit dấu. Bởi vậy thứ tự DFS đi nhánh 0 trước nhánh 1 trùng với thứ tự `TreeSet<Integer>` và liên kết giữa các lá.

**Thứ tư, xóa phải xóa cả tiền tố đã chết.** Khi `count(node)` trở về 0, mã xóa mục tương ứng khỏi `HashMap` của độ sâu đó và tháo con trỏ từ cha. Những nút còn khóa được tính lại `first/last` từ hai con.

**Thứ năm, validator là một đường kiểm tra riêng.** Nó duyệt toàn bộ cây theo con trỏ, kiểm tra bảng hash, phát hiện nút dùng chung/chu trình qua `IdentityHashMap`, so `count` và `first/last`, rồi kiểm tra liên kết lá. Bài kiểm tra `TreeSet` độc lập đối chiếu lower/floor/ceiling/higher và đếm tiền tố.

**Thứ sáu, ví dụ snapshot y-fast không có cập nhật động.** `RepresentativeBucketSnapshot` chỉ chứng minh **định vị bucket bằng x-fast đại diện**, rồi hỏi cây `TreeSet` trong bucket, có fallback sang bucket kề nhau. Nó không có tách/gộp, lấy mẫu đại diện hay chứng minh giới hạn O(log w) cập nhật khấu hao. Không dùng lớp này làm bằng chứng rằng một y-fast trie động chuẩn đã được cài đặt.

## 15. Mô phỏng cập nhật tiền tố của x-fast theo từng bước

Để kiểm tra chính xác cách bảo trì, hãy tạm dùng **khóa không dấu 4 bit** với:

\[
S=\{0010,0011,0110,1010,1110\}.
\]

Tại mỗi tầng, bảng tiền tố chỉ giữ các đường có ít nhất một khóa phía dưới.

### Chèn 7 = `0111`

Trước chèn, khóa 6 = `0110` đã có:

```text
d=1: 0
d=2: 01
d=3: 011
d=4: 0110
```

Sau chèn 7:

```text
d=1: 0           vẫn tồn tại, count tăng
d=2: 01          vẫn tồn tại, count tăng
d=3: 011         vẫn tồn tại, count tăng
d=4: 0111        tiền tố đầy đủ MỚI

Danh sách lá:
2 <-> 3 <-> 6 <-> 7 <-> 10 <-> 14
```

Chỉ có **nút ở tầng 4** mới cần thêm vào hash table; các nút tầng 1–3 phải tăng bộ đếm và có thể cập nhật con trỏ biên tùy khóa chèn. Đó là sự khác biệt giữa:

- **Số tiền tố mới:** có thể ít hơn `w`.
- **Số nút cần bảo trì:** tối đa `w+1`.

Không được bỏ qua cập nhật `count` chỉ vì không tạo nút mới.

### Xóa 6 = `0110` sau khi thêm 7

```text
Trước:
   prefix 011 có hai lá 0110 và 0111

Xóa 0110:
   xóa mục 0110 khỏi H_4
   prefix 011 vẫn có lá 0111
   H_3[011] PHẢI được giữ
   cập nhật firstLeaf(011) = lastLeaf(011) = 0111
```

Nếu xóa luôn `H_3[011]`, truy vấn `contains(7)` có thể vẫn tìm thấy lá ở `H_4` nhưng **tìm kiếm tiền tố bằng binary search bị sai**, vì tính chất “tiền tố dài tồn tại thì tiền tố ngắn phải tồn tại” đã bị phá vỡ.

### Xóa tiếp 7 = `0111`

```text
H_4[0111] bị xóa
H_3[011] không còn lá -> xóa
H_2[01] không còn lá -> xóa
H_1[0] vẫn còn vì 2,3 bắt đầu bằng 0 -> giữ
```

Cần đi từ lá lên hoặc duy trì `count` chính xác để biết tới đâu thì phải dừng việc cắt nút. Đây là nguyên tắc giống **pruning** trong trie nhị phân, nhưng x-fast còn phải **xóa những mục hash** tương ứng.

### Biên đầu/cuối của danh sách lá

Khi chèn một khóa nhỏ hơn mọi khóa hiện có:

```text
Trước:  [2] <-> [3] <-> [6]
Thêm 1:
Sau:    [1] <-> [2] <-> [3] <-> [6]
```

Con trỏ `root.firstLeaf` phải đổi thành 1, còn `1.prev=null`. Khi xóa 6 khỏi đầu bên phải, `root.lastLeaf` phải đổi sang 3 và `3.next=null`. Nếu còn dùng con trỏ lá biên đã bị xóa, `minimum/maximum` và các truy vấn kề cận có thể trả dữ liệu không còn trong tập.

## 16. Kiểm thử có oracle và kiểm thử bất biến

Một cấu trúc vừa có **nút tiền tố**, vừa có **bảng băm**, vừa có **liên kết lá** dễ gặp lỗi mà phép `contains` đơn thuần không phát hiện. Ví dụ:

- Lá 10 còn ở `H_w`, nhưng `H_2[10]` bị xóa nhầm: membership đúng, predecessor/successor có thể sai.
- Liên kết `3.next=10` bỏ qua 6: bảng tiền tố đúng, nhưng lời gọi successor từ nút biên có thể trả sai.
- `firstLeaf` hoặc `lastLeaf` của một nút vẫn trỏ đến khóa đã xóa: chỉ một số truy vấn tại khoảng rẽ nhánh mới bị lỗi.

### Bộ kiểm tra của chương trình Java xác minh gì?

| Bất biến | Phương pháp |
| --- | --- |
| Mỗi hash entry là một tiền tố đang có | Đi từ gốc theo con trỏ và so với bảng `levels[depth]` |
| Mỗi nút thuộc đúng tầng và tiền tố | So `depth`, `prefix`, `parent` và bit cạnh |
| Không có alias/chu trình | Dùng `IdentityHashMap<Node,Boolean>` |
| Nút lá là khóa đầy đủ | Kiểm tra độ sâu 32, `count=1` và khóa giải mã đúng |
| Bộ đếm cây con | `count(node)=count(zero)+count(one)` |
| Con trỏ biên | `first/last` khớp hai nhánh con đang hoạt động |
| Lá tăng nghiêm ngặt | DFS trái-trước-phải và so khóa |
| Danh sách lá hai chiều | Kiểm tra `prev/next` đối xứng |
| Không còn tiền tố đã chết | Tất cả mục hash phải thuộc những nút thực sự đi được từ gốc |
| Kích thước tập | `size` bằng tổng số lá và `root.count` |

### Oracle độc lập

Java có `TreeSet<Integer>` với hợp đồng:

| API x-fast | API tương ứng của `TreeSet` |
| --- | --- |
| `contains` | `contains` |
| `add` | `add` |
| `remove` | `remove` |
| `lower` | `lower` |
| `floor` | `floor` |
| `ceiling` | `ceiling` |
| `higher` | `higher` |
| `minimum` | `first` nếu không rỗng |
| `maximum` | `last` nếu không rỗng |

Sau mỗi lần cập nhật, so **danh sách lá theo thứ tự tăng** với `new ArrayList<>(treeSet)`, rồi so các truy vấn tại những ngưỡng đại diện.

### Những trường hợp nên thử riêng

1. **Tập rỗng:** lower/higher/floor/ceiling/min/max đều rỗng; bảng gốc có `count=0`.
2. **Một khóa:** chỉ có một lá; `prev/next` đều `null`.
3. **Chèn trùng:** không thêm lá, không tăng `count` hoặc số mục tiền tố.
4. **Xóa vắng:** không cắt tiền tố và không thay đổi liên kết lá.
5. **Hai khóa chia sẻ tiền tố dài:** ví dụ 6 và 7; xóa một phải giữ tiền tố của khóa còn lại.
6. **Hai khóa khác bit đầu:** mọi truy vấn vượt từ nhóm 0 sang nhóm 1 phải đúng.
7. **Xóa khóa nhỏ nhất/lớn nhất:** cập nhật `first/last` ở gốc.
8. **Xóa tất cả:** các bảng tiền tố độ sâu dương trở nên rỗng, chỉ gốc còn hoạt động về cấu trúc.
9. **Thêm lại sau xóa:** khôi phục đúng những tiền tố và con trỏ bị cắt.
10. **Khóa âm/dương và `Integer.MIN_VALUE/MAX_VALUE`:** thứ tự signed phải trùng `TreeSet`.
11. **Độ dài tiền tố `d=0`, `d=1`, `d=32`:** đếm toàn tập, đếm nhóm dấu và membership.
12. **Ngưỡng không hiện diện:** predecessor và successor phải tìm đúng hai lá kẹp ngưỡng.

### Kiểm thử ngẫu nhiên có seed cố định

```text
oracle = TreeSet<Integer>()
test   = XFastIntSet()
random = Random(20261128)

repeat many steps:
    choose key from small signed range
    occasionally choose MIN_VALUE/MAX_VALUE
    choose add/remove
    require operation-result flags match
    compare sizes and all keys in ascending order
    check trie/hash/leaf invariants
    compare lower/floor/ceiling/higher
    verify prefix counts at selected depths
```

Chọn một miền nhỏ trong test làm **thêm trùng** và **xóa khóa vắng** xuất hiện thường xuyên. Giữ seed giúp tái hiện cùng chuỗi khi phát hiện lỗi.

**Không nhầm validator với thuật toán thao tác:** kiểm tra toàn bộ bảng hash và nút có thể tốn O(nw) thời gian hoặc hơn theo cách triển khai; nó dùng cho test/debug. Không được cộng validator vào mỗi `insert` rồi vẫn tuyên bố hoạt động thực tế O(w).

## 17. Quy trình chọn cấu trúc theo workload

Các cấu trúc có cùng mục tiêu ordered set nhưng rất khác về bộ nhớ và giả định.

| Nhu cầu | Lựa chọn đáng cân nhắc | Đánh đổi cần đo |
| --- | --- | --- |
| Miền nhỏ, membership/bitwise nhiều | **Bitset** hoặc bitmap tóm tắt | `U`, số từ/summary, RAM |
| Khóa rải rác, chỉ tra chính xác | **HashSet** | Hashing, va chạm, tính thứ tự không có |
| Cần ordered set tổng quát, ổn định | **AVL/Red-Black/TreeMap** | O(log n), con trỏ/cache |
| Khóa không đổi, cần predecessor | **Mảng đã sắp + binary search** | Chèn/xóa O(n) |
| Cần tiền tố bit và XOR | **Binary trie/Patricia** | O(w), chi phí nút/prefix |
| Có RAM, muốn truy vấn predecessor nhanh theo `w` | **x-fast trie** | O(nw) bộ nhớ, update O(w) |
| Tập lớn, cần vừa nhanh vừa gọn theo `n` | **y-fast trie** | Phức tạp cập nhật đại diện, ngẫu nhiên hóa |
| Miền tương đối nhỏ, chấp nhận O(U) | **vEB cổ điển** | O(log log U) và cấp phát/khởi tạo O(U) |
| Lưu dữ liệu phân trang trên đĩa | **B-tree/B+ tree** | Chi phí I/O, kích thước trang, range scan |

### Khi nào x-fast có thể hợp lý hơn y-fast?

Nếu tập tương đối nhỏ, khối lượng **truy vấn predecessor/successor lớn hơn nhiều so với cập nhật** và bộ nhớ còn thoải mái, x-fast dễ giải thích và bỏ qua được lớp bảo trì bucket. Nhưng overhead của `w+1` bảng hash và O(nw) mục có thể vẫn quá lớn trên JVM.

### Khi nào y-fast đáng cân nhắc?

Khi cần ordered set trên miền nguyên lớn, nhiều khóa và truy vấn lân cận thường xuyên, **O(n) bộ nhớ kỳ vọng** có thể rất hấp dẫn so với O(nw) của x-fast. Tuy nhiên, triển khai chuẩn bao gồm chọn mẫu, cập nhật đại diện, bucket và cân bằng nhóm là **khó hơn nhiều** so với mô tả hai tầng.

### Khi nào cây cân bằng thực tế hơn?

Nếu thư viện chuẩn `TreeMap/TreeSet` đã đáp ứng độ trễ, dùng ít bộ nhớ hơn và dễ kiểm thử/bảo trì, một cấu trúc tự viết phức tạp chưa chắc đáng chi phí. Các số hạng `\log w` và `\log n` là hướng dẫn lý thuyết; đo **throughput, tail latency, allocations, GC, cache misses** mới phản ánh workload thực.

### Có thể dùng x-fast/y-fast cho khóa chuỗi không?

Không trực tiếp dưới cùng các bảo đảm. Cấu trúc này khai thác **mã bit có độ dài xác định của khóa nguyên** và các phép dịch/mask trên từ máy. Với chuỗi biến độ dài, cần encoding thành miền nguyên có cấu trúc và phải đảm bảo thứ tự phù hợp, hoặc dùng trie/radix tree cho chuỗi. Không thể áp dụng `U=2^w` tùy tiện mà bỏ qua chi phí mã hóa chuỗi.

## 18. Những lỗi và ngộ nhận thường gặp

1. **Nhầm x-fast trie với bảng băm một khóa.** Điểm cốt lõi là có **bảng cho từng độ dài tiền tố**, không chỉ `H_w`.
2. **Tìm predecessor bằng binary search trên `n` khóa rồi gọi đó là x-fast.** x-fast binary search trên **độ dài tiền tố `0..w`**, không phải trên phần tử của mảng đã sắp.
3. **Bỏ qua tính đơn điệu tồn tại tiền tố.** Nếu một tiền tố dài có thì các tiền tố ngắn hơn phải có; mất bất biến này làm binary search sai.
4. **Dùng `mid=(lo+hi)/2` khi tìm mức đúng lớn nhất rồi giữ `lo=mid`.** Có thể không tiến triển khi `hi=lo+1`; lấy midpoint làm tròn lên.
5. **Cho rằng biết tiền tố chung dài nhất đủ để tìm lân cận O(1).** Cần con trỏ biên hoặc jump pointers và liên kết lá.
6. **Quên hướng của bit tiếp theo.** Bit 0 bị thiếu → nhánh 1 còn lại chứa khóa **lớn hơn**; bit 1 bị thiếu → nhánh 0 còn lại chứa khóa **nhỏ hơn**.
7. **Chọn nhánh 0 trước 1 trên mã `int` gốc rồi so với thứ tự Java signed.** Phải chuẩn hóa dấu hoặc định nghĩa thứ tự unsigned rõ ràng.
8. **Đảo bit dấu khi chèn mà không đảo khi tìm.** Cùng một khóa sẽ có mã khác nhau ở các phép toán.
9. **Tính tiền tố rỗng bằng `intCode >>> 32`.** Java với `int` sẽ dịch như 0, dẫn đến prefix sai. Sử dụng `long` hoặc xử lý `d=0` riêng.
10. **Cho rằng hai tiền tố số học bằng nhau ở hai độ dài là cùng một nút.** Tiền tố phải được phân biệt bằng **độ dài**; dùng bảng riêng cho từng tầng hoặc khóa ghép `(depth,prefix)`.
11. **Giữ mục hash tiền tố đã không còn lá.** Khi khóa cuối của một nhánh bị xóa, phải xóa các mục tiền tố đã chết.
12. **Xóa mọi tiền tố trên đường một khóa bất kể khóa khác còn chia sẻ.** Chỉ cắt nút khi số khóa trong cây con bằng 0.
13. **Không cập nhật `firstLeaf/lastLeaf` sau khi xóa lá biên.** Có thể trả khóa đã bị xóa.
14. **Chỉ sửa liên kết `next` mà quên `prev`.** Danh sách hai chiều sẽ sai ở truy vấn ngược.
15. **Cho rằng x-fast `insert/delete` cũng O(log w) vì predecessor O(log w).** Cập nhật phải bảo trì O(w) mức tiền tố; O(w) kỳ vọng là cận thường dùng.
16. **Cho rằng x-fast có O(n) bộ nhớ.** Tổng số nút/mục tiền tố có thể O(nw), không chỉ O(n).
17. **Gọi O(log w) worst-case cho thời gian hash lookup không có bảo đảm worst-case.** Số lần dò có cận, nhưng thời gian mỗi phép băm có giả định kỳ vọng.
18. **Cho rằng y-fast xây x-fast trên mọi khóa.** y-fast chỉ đánh chỉ mục một số **đại diện**, còn các khóa còn lại nằm trong bucket.
19. **Thay bucket BST bằng mảng và vẫn nói chèn/xóa O(log w).** Chèn/xóa vào mảng đã sắp có thể phải dịch O(w) phần tử trong bucket.
20. **Tưởng mọi bucket y-fast có chính xác `w` khóa.** Với lấy mẫu ngẫu nhiên, kích thước chỉ có tính chất phân bố/kỳ vọng phù hợp, không cố định.
21. **Lấy `E[b]=O(w)` cho một bucket đều rồi áp thẳng cho mọi truy vấn ngưỡng cố định.** Phải kiểm tra phân bố bucket được chọn có bị thiên lệch kích thước hay không.
22. **Đổi representative mỗi lần khóa max bucket thay đổi nhưng vẫn gọi cập nhật O(log w) khấu hao.** Cần chiến lược bảo trì đại diện có chứng minh, không dùng mô hình snapshot tĩnh làm bảo đảm động.
23. **Không xử lý nhóm đầu/cuối khi truy vấn vượt mọi đại diện.** Predecessor có thể nằm trong bucket cuối; successor ngoài toàn bộ tập phải rỗng.
24. **Không thử bucket liền kề khi bucket đầu không có lời giải.** Khi truy vấn sát ranh giới, predecessor/successor có thể ở nhóm kế.
25. **Tưởng một representative luôn là khóa gần nhất của ngưỡng.** Representative chỉ định vị nhóm; cần tìm tiếp trong bucket.
26. **Tự kết luận y-fast membership O(1) vì x-fast có full-key hash.** Hầu hết khóa y-fast không nằm trong x-fast đại diện; cần tìm bucket hoặc hash phụ.
27. **Đồng nhất expected với amortized.** Một cận có thể vừa là kỳ vọng vừa là khấu hao; phải xác định xác suất và chuỗi cập nhật.
28. **Cho rằng không gian O(n) có ngay chỉ từ câu nói “mỗi bucket khoảng w phần tử”.** Phải chứng minh/duy trì số đại diện khoảng O(n/w) hoặc xử lý thích hợp khi `n<w`.
29. **Bỏ qua overhead của các đối tượng Java và bảng HashMap.** O(nw) mục là số lượng trừu tượng; RAM thực có thể lớn hơn đáng kể so với mảng int.
30. **Chạy validator sau mọi thao tác trong ứng dụng sản xuất nhưng vẫn báo chi phí thao tác O(w).** Validator quét nhiều nút, chỉ phù hợp cho debug/test.
31. **Không thử `Integer.MIN_VALUE/MAX_VALUE`.** Mã hóa dấu và xử lý biên rất dễ sai nếu chỉ thử khóa không âm nhỏ.
32. **Nhầm x-fast/y-fast với trie nhị phân dành cho chuỗi biến độ dài.** Các bảo đảm dựa vào khóa nguyên độ dài `w` bit và Word-RAM.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** x-fast trie giải quyết điểm yếu gì của trie nhị phân thông thường?

**Đáp án:** Trie thường phải đi qua tối đa `w` bit để tìm đường. x-fast băm các tiền tố theo tầng và tìm tiền tố chung dài nhất bằng binary search theo độ dài, giúp truy vấn lân cận O(log w) kỳ vọng.

**Câu 2.** Ký hiệu `n`, `U`, `w` khác nhau thế nào?

**Đáp án:** `n` là số khóa đang lưu; `U` là số khóa có thể có; `w` là số bit của mã khóa, bằng `\log_2U` khi `U=2^w`.

**Câu 3.** Với `S=\{0010,0011,0110,1010,1110\}`, tập tiền tố độ dài 2 là gì?

**Đáp án:** `\{00,01,10,11\}`.

**Câu 4.** Tiền tố độ dài 3 của khóa `10=1010` là gì?

**Đáp án:** `101`.

**Câu 5.** Tại sao tồn tại tiền tố theo độ dài là tính chất đơn điệu?

**Đáp án:** Nếu một khóa hiện có chia sẻ `d` bit đầu với truy vấn, nó cũng chia sẻ mọi tiền tố ngắn hơn; nếu không có khóa nào chia sẻ `d` bit, không thể có khóa chia sẻ nhiều hơn `d` bit đầu.

**Câu 6.** Với `x=9=1001` và `S=\{2,3,6,10,14\}`, tiền tố chung dài nhất tồn tại có độ dài bao nhiêu?

**Đáp án:** `d^*=2`, tiền tố `10`; ở độ dài 3, tiền tố `100` vắng mặt.

**Câu 7.** Với truy vấn 9, predecessor và successor lần lượt là gì?

**Đáp án:** `predecessor(9)=6`, `successor(9)=10`.

**Câu 8.** Tại nút tiền tố cuối cùng, nếu bit cần đi của truy vấn là 0 nhưng nhánh 0 không có, nhánh 1 còn lại chứa khóa nhỏ hơn hay lớn hơn ngưỡng?

**Đáp án:** Chứa những khóa **lớn hơn** ngưỡng, vì bit khác nhau đầu tiên của chúng là 1 trong khi ngưỡng là 0.

**Câu 9.** Nếu bit cần đi là 1 nhưng nhánh 1 vắng, ta dùng lá nào của nhánh 0?

**Đáp án:** `lastLeaf` (khóa lớn nhất của nhánh 0) để lấy predecessor; successor là `lastLeaf.next`.

**Câu 10.** Vì sao x-fast cần liên kết `prev/next` giữa các lá?

**Đáp án:** Khi đã định vị một lá biên của một nhánh, có thể tìm khóa lân cận trên toàn tập trong O(1), không phải duyệt lại từ gốc.

**Câu 11.** Membership của x-fast thường được thực hiện thế nào?

**Đáp án:** Tra bảng `H_w` ở tiền tố đủ `w` bit của khóa, kỳ vọng O(1) với hash table.

**Câu 12.** Giới hạn thời gian predecessor/successor x-fast là bao nhiêu?

**Đáp án:** O(log w) kỳ vọng, hay O(log log U) kỳ vọng khi `w=\Theta(\log U)`.

**Câu 13.** Tại sao chèn/xóa x-fast thường O(w) kỳ vọng chứ không phải O(log w)?

**Đáp án:** Phải tạo/xóa/cập nhật bộ đếm và con trỏ biên trên tối đa `w` nút tiền tố, chứ không chỉ tìm nơi cập nhật.

**Câu 14.** Vì sao bộ nhớ x-fast có thể là O(nw)?

**Đáp án:** Mỗi khóa tạo tối đa một nút tiền tố ở mỗi độ sâu từ 1 đến `w`, nên tổng tối đa `1+nw` nút/tiền tố.

**Câu 15.** y-fast trie thay đổi điều gì so với x-fast?

**Đáp án:** Chỉ đưa một số **khóa đại diện** vào x-fast, còn mỗi nhóm khóa nằm trong một cấu trúc có thứ tự như cây cân bằng.

**Câu 16.** Vì sao các nhóm y-fast thường có kích thước cỡ `w`?

**Đáp án:** Để số đại diện cỡ `n/w` và chi phí chỉ mục x-fast cỡ `(n/w)\cdot w=O(n)`, trong khi tìm trong một nhóm bằng BST tốn O(log w).

**Câu 17.** Với bucket `B_{60}=\{45,48,52,60\}`, `predecessor(50)` là gì?

**Đáp án:** 48.

**Câu 18.** Trong ví dụ các đại diện `\{12,31,60,93\}`, `successor(31)` là gì?

**Đáp án:** 45, là khóa nhỏ nhất của bucket tiếp theo, không phải đại diện 60.

**Câu 19.** Vì sao khi hỏi `predecessor(70)`, bucket đại diện 93 có thể không trả được lời giải?

**Đáp án:** Bucket 93 chỉ chứa 90 và 93, đều lớn hơn 70; cần lấy max của bucket trước là 60.

**Câu 20.** y-fast có mặc định dùng O(1) expected cho membership không?

**Đáp án:** Không. Nếu chỉ có x-fast trên đại diện và BST trong bucket, membership dùng định vị nhóm và tìm trong nhóm, thường O(log w) kỳ vọng. Hash phụ toàn khóa mới cho phép expected O(1) nếu được thêm vào.

**Câu 21.** Vì sao cập nhật representative tại mỗi lần thay đổi max của bucket có thể phá giới hạn cập nhật?

**Đáp án:** Vì mỗi lần đổi representative phải cập nhật các bảng tiền tố x-fast với chi phí O(w); nếu xảy ra quá thường xuyên thì không khấu hao được về O(log w).

**Câu 22.** Có thể nói mọi bucket được lấy mẫu ngẫu nhiên đều có đúng `w` khóa không?

**Đáp án:** Không. Kích thước nhóm là biến ngẫu nhiên; kỳ vọng cỡ `w` không có nghĩa giá trị cố định hoặc worst-case `w` cho từng nhóm.

**Câu 23.** Bộ nhớ lý thuyết của y-fast chuẩn thường là bao nhiêu?

**Đáp án:** O(n) kỳ vọng theo một chiến lược duy trì đại diện và bucket được phân tích đúng.

**Câu 24.** Giới hạn cập nhật của y-fast chuẩn được mô tả chính xác thế nào?

**Đáp án:** O(log w) **kỳ vọng, khấu hao** cho biến thể ngẫu nhiên hóa điển hình; không khẳng định deterministic worst-case nếu chưa có chứng minh.

**Câu 25.** Vì sao phải đảo bit dấu của `int` trước khi sắp x-fast MSB-first?

**Đáp án:** Vì số âm có bit dấu 1 nhưng đứng trước số không âm trong thứ tự có dấu; XOR với `Integer.MIN_VALUE` biến thứ tự signed thành thứ tự mã unsigned.

**Câu 26.** Có thể lấy tiền tố rỗng bằng `intCode >>> 32` trong Java không?

**Đáp án:** Không, vì số bước dịch `int` bị mask và dịch 32 tương đương dịch 0. Dùng `long` rồi dịch 32 hoặc xử lý tầng 0 riêng.

**Câu 27.** Tại sao validator phải kiểm tra các bảng tiền tố, con trỏ biên và danh sách lá đồng thời?

**Đáp án:** Một thành phần có thể đúng còn thành phần khác sai. Chẳng hạn `H_w` còn lá khóa nhưng tiền tố trung gian bị xóa, hoặc liên kết `next` bỏ qua một lá, khiến predecessor/successor trả sai.

**Câu 28.** Khi nào nên cân nhắc `TreeSet` thay cho x-fast hoặc y-fast dù giới hạn lý thuyết của nó là O(log n)?

**Đáp án:** Khi cần triển khai đơn giản, đáng tin cậy, bộ nhớ/độ trễ thực tế phù hợp, hoặc `n` nhỏ khiến overhead hash tiền tố và quản lý bucket không đáng.

## 20. Tóm tắt

**Ý tưởng then chốt của x-fast trie** là **biến mỗi tầng tiền tố của trie thành một bảng băm**. Tính chất đơn điệu “tiền tố ngắn có thể tồn tại, tiền tố dài hơn có thể biến mất” cho phép **tìm kiếm nhị phân theo chiều dài tiền tố** chỉ với O(log w) phép tra hash. Con trỏ biên và **lá nối đôi** biến điểm rẽ nhánh ấy thành predecessor/successor mà không phải đi thêm O(w) tầng.

Đổi lại, x-fast duy trì O(nw) mục tiền tố và phải sửa O(w) mức khi cập nhật. **y-fast trie** khắc phục phần lớn chi phí không gian bằng cách giữ x-fast **chỉ cho các đại diện**, lưu khóa còn lại trong **nhóm có cây cân bằng**, và dùng một chiến lược duy trì nhóm/đại diện có phân tích xác suất–khấu hao.

\[
\boxed{
\begin{array}{c|ccc}
 & \text{Predecessor/successor} & \text{Update} & \text{Space}\\
\hline
\text{x-fast} & O(\log w)\ \text{kỳ vọng}
              & O(w)\ \text{kỳ vọng}
              & O(nw)\\
\text{y-fast} & O(\log w)\ \text{kỳ vọng}
              & O(\log w)\ \text{kỳ vọng, khấu hao}
              & O(n)\ \text{kỳ vọng}
\end{array}
}
\]

**Điểm ghi nhớ:** **x-fast = trie bit + hash theo độ dài tiền tố + con trỏ lá biên/liên kết lá**; **y-fast = x-fast của các đại diện + các bucket có thứ tự**. Hai cấu trúc nhằm giải quyết **truy vấn thứ tự trên khóa nguyên**, không đơn thuần thay thế bảng băm membership. Khi áp dụng, hãy ghi rõ **độ rộng khóa `w`, mô hình băm, quy tắc duy trì đại diện, loại cận kỳ vọng/khấu hao**, và đo cả bộ nhớ thực lẫn thời gian cập nhật.
