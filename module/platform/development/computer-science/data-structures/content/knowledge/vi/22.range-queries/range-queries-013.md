# Lan truyền lười (lazy propagation) cho cập nhật đoạn

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **vì sao cây đoạn (segment tree) chỉ cập nhật điểm chưa đủ** khi cần sửa đồng thời hàng nghìn phần tử trên một đoạn.
- Dùng quy ước đoạn **nửa mở `[l,r)`** nhất quán khi xây cây, cập nhật đoạn và truy vấn đoạn; xử lý đúng `l=r`, `r=n` và mảng rỗng.
- Phát biểu chính xác ý nghĩa của **`tree[v]`** và **`lazy[v]`** trong cây hỗ trợ *cộng đều một giá trị vào đoạn* và *truy vấn tổng đoạn*.
- Phân biệt ba thao tác **`apply`** (áp nhãn lên một nút), **`push`** (đẩy nhãn xuống con) và **`pull`** (gộp lại từ con lên cha).
- Mô phỏng cập nhật phủ trọn, giao một phần, không giao; giải thích tại sao phải `push` **trước khi** đi xuống những cây con có dữ liệu chưa cập nhật.
- Cài đặt **xây cây O(n)**, **cập nhật cả đoạn O(log n)** và **truy vấn đoạn O(log n)**, với bộ nhớ O(n) và bộ nhớ ngăn xếp O(log n).
- Hiểu tại sao **cập nhật gán giá trị** không giống **cộng thêm delta**; xử lý đúng nhãn mới/nhãn cũ khi các cập nhật chồng lấn.
- Thiết kế và kiểm chứng phép **hợp thành nhãn**; dùng một biểu diễn affine để hỗ trợ cả **cộng, gán và nhân** trên đoạn khi truy vấn **tổng**.
- Phân tích những trường hợp không thể dùng lại công thức lazy-add cho **GCD, phép nối chuỗi**, hoặc những phép biến đổi không phù hợp với thống kê đang lưu.
- Đối chiếu thuật toán với cách cập nhật trực tiếp trên mảng, thử đoạn âm/đoạn rỗng và phân biệt bảo đảm thuật toán tuần tự với an toàn truy cập đồng thời.

## 1. Vì sao cần lan truyền lười?

Trong module `COMPUTER_SCIENCE_DATA_STRUCTURES`, ta lựa chọn cấu trúc dữ liệu dựa trên bất biến, thao tác cần hỗ trợ và chi phí **thời gian/bộ nhớ**. Ở nhóm **Truy vấn đoạn**, cây đoạn thường lưu một kết quả tổng hợp cho từng đoạn liên tiếp của mảng.

Giả sử `A` ghi **số phút học mỗi ngày** trong một tháng. Hệ thống cần hai thao tác:

1. **Cộng thêm 5 phút vào các ngày có chỉ số từ 2 đến ngay trước 7**: `add(2,7,5)`.
2. **Hỏi tổng phút học của các ngày từ 1 đến ngay trước 9**: `sum(1,9)`.

Nếu gọi `set(i,A[i]+5)` cho từng chỉ số trong `[2,7)`, cập nhật năm phần tử sẽ cần năm đường gốc–lá. Tổng quát, đoạn có `k=r-l` phần tử:

\[
\text{Cập nhật từng điểm}=O(k\log(n+1)).
\]

Khi `k=\Theta(n)` và yêu cầu cập nhật cả đoạn thường xuyên, chi phí có thể trở thành **O(n log n)** trong cách cài trực tiếp này.

**Lan truyền lười (lazy propagation)** đưa ra ý tưởng khác:

> Nếu một nút quản lý **toàn bộ đoạn cần sửa**, hãy cập nhật kết quả tóm tắt ngay tại nút và **ghi nhớ thao tác còn nợ cho các nút con**. Chỉ đẩy thao tác xuống con khi một truy vấn hoặc cập nhật sau đó thực sự cần đi xuống.

Nhờ vậy, không phải mở tất cả lá ngay sau một cập nhật phủ toàn mảng.

### 1.1. Quy ước đoạn nửa mở

Trong toàn bài, `[l,r)` gồm các chỉ số `l,l+1,\ldots,r-1`. Điều kiện hợp lệ:

\[
0\le l\le r\le n.
\]

Với mảng `A` có `n` phần tử:

- `add(0,n,d)`: cộng `d` vào **toàn mảng**.
- `add(3,4,d)`: cập nhật **một phần tử `A[3]`**.
- `add(3,3,d)`: cập nhật **đoạn rỗng**, không làm gì.
- `sum(0,0)` và `sum(n,n)`: truy vấn đoạn rỗng, bằng `0` đối với tổng.
- `add(5,2,d)` hoặc `sum(0,n+1)`: **đầu vào sai**, nên báo lỗi, không âm thầm cắt chỉ số.

Đoạn nửa mở giúp hai con `[L,M)` và `[M,R)` ghép thành đúng `[L,R)` mà không trùng hay bỏ phần tử ở `M`.

### 1.2. Bảng so sánh các phương án

Giả sử cần **range add** và **range sum** trên `n` phần tử:

| Phương án | Xây dựng | Cộng một đoạn dài `k` | Tổng một đoạn |
| --- | --- | --- | --- |
| Mảng thường | O(n) để có dữ liệu | O(k) | O(k) |
| Cây đoạn chỉ cập nhật điểm | O(n) | O(k log n) nếu cập nhật từng điểm | O(log n) |
| Cây đoạn với **lazy propagation** | **O(n)** | **O(log n)** | **O(log n)** |

Trong trường hợp **chỉ có range add và range sum**, còn có thể cân nhắc kỹ thuật **hai Fenwick tree** để đạt O(log n) cập nhật/truy vấn và O(n) bộ nhớ. Lazy segment tree đáng học vì còn mở rộng được cho nhiều kiểu thống kê và tác động cập nhật khác, miễn thiết kế đúng phép gộp và nhãn.

## 2. Nhắc lại cấu trúc cây đoạn

Mỗi nút `v` quản lý một khoảng `[L,R)`, với:

- Gốc quản lý `[0,n)`.
- Nếu `R-L=1`, đó là **lá** chứa một phần tử.
- Nếu `R-L>1`, đặt `M=(L+R)//2`; hai con quản lý `[L,M)` và `[M,R)`.
- Trong ví dụ **tổng**, giá trị tổng hợp ở cha bằng tổng hai con **khi tất cả nhãn đã được đẩy xuống đầy đủ**.

Với `A=[1,2,3,4,5,6,7,8]`:

```text
                          [0,8):36
                         /         \
                    [0,4):10     [4,8):26
                    /    \        /     \
               [0,2):3  [2,4):7 [4,6):11 [6,8):15
                / \      / \     / \      / \
               1   2    3   4   5   6    7   8
```

Với một phép **cộng giá trị `d` vào tất cả phần tử của `[L,R)`**, tổng của đoạn này tăng đúng:

\[
\Delta\operatorname{sum}(L,R)=d\cdot(R-L).
\]

Đây là công thức giúp một nút phủ trọn cập nhật được tổng **không cần đi xuống từng lá**.

### 2.1. Một cập nhật phủ toàn cây

Thực hiện:

```text
range_add(0, 8, +5)
```

Mảng **theo nghĩa logic** trở thành:

```text
Trước:       [1, 2, 3, 4, 5, 6, 7, 8]
Sau +5:      [6, 7, 8, 9,10,11,12,13]
Tổng mới:   36 + 5*8 = 76
```

Tuy nhiên, **không cần sửa ngay tất cả lá**. Có thể chỉ lưu:

```text
                          [0,8)
                        tree = 76
                        lazy = +5
                         /     \
                 [0,4):10      [4,8):26
                  lazy=0        lazy=0
                    ...           ...
```

Hai nút con vẫn đang giữ **tổng trước cập nhật**. Điều này **không phải sai bất biến**: cha đã phản ánh +5 cho cả tám phần tử, đồng thời **`lazy=5`** cho biết *các con còn phải nhận +5 mỗi phần tử khi được dùng*.

### 2.2. Bất biến của `tree[v]` và `lazy[v]`

Trong cây đoạn **cộng đoạn – hỏi tổng**, định nghĩa:

- `tree[v]`: **tổng đúng của đoạn do nút `v` quản lý**, sau khi tính cả mọi cập nhật đang được lưu tại chính nút đó, nhưng các tổ tiên có thể còn nhãn chưa đẩy xuống.
- `lazy[v]`: lượng cộng `d` cần **truyền tiếp cho mỗi phần tử của hai cây con** khi một thao tác đi sâu hơn. Tác động của lượng cộng này **đã nằm trong `tree[v]`**, nhưng **chưa nhất thiết nằm trong `tree` của các con**.

Do đó, nếu `v` là nút trong và hai con chưa nhận phần cộng đang trì hoãn tại `v`:

\[
\boxed{\quad
tree[v]=tree[2v]+tree[2v+1]+lazy[v]\cdot(R-L).
\quad}
\]

Đây là **bất biến biểu diễn cục bộ** của bản cài range-add/range-sum, với điều kiện các phép cập nhật ở những nút tổ tiên đã được áp xuống `v` khi cần đi qua đường đó.

Khi `lazy[v]=0`, ta có công thức gộp quen thuộc:

\[
tree[v]=tree[2v]+tree[2v+1].
\]

Đặc biệt, **không nên lập trình bằng cách cộng `lazy[v]` thêm một lần vào `tree[v]` khi trả truy vấn phủ trọn**. Tổng ở nút **đã chứa** tác động của nhãn ấy; làm vậy sẽ **đếm hai lần**.

### 2.3. Không nhầm nhãn của một nút với kết quả tổng

Giả sử nút `v` quản lý bốn phần tử, `lazy[v]=+3`. Nó không có nghĩa “tổng của nút tăng +3”; tổng phải tăng:

\[
3\times4=12.
\]

Nhưng khi một nút con quản lý **hai** phần tử nhận nhãn +3, tổng của con tăng `3×2=6`. Mỗi đoạn phải dùng **độ dài riêng**.

Nếu dùng phép **min** thay cho tổng và cộng đều +3 vào cả đoạn, min tăng đúng **+3**, không nhân độ dài. Công thức `apply` vì vậy phụ thuộc **loại thống kê** đang lưu.

## 3. Ba động tác nền tảng: apply, push, pull

### 3.1. `apply(v,L,R,d)` — đánh dấu nút đã nhận cập nhật

Nếu **cộng `d` vào tất cả phần tử trong `[L,R)`**, thao tác:

```text
tree[v] += d * (R-L)
lazy[v] += d
```

Giải thích:

1. `tree[v]` phải cho ngay **tổng đúng** của đoạn sau cập nhật.
2. `lazy[v]` ghi nhớ **tổng các lượng cộng chưa lan xuống con**.
3. Nếu nút này lại nhận +2 sau khi đang đợi +5, nhãn mới là `5+2=7`, vì hai phép cộng kết hợp theo cách cộng delta.

Đối với **lá**, không có con cần lan tiếp; có thể vẫn lưu `lazy` ở lá mà không gây sai số nếu thuật toán không bao giờ `push` xuống dưới lá.

### 3.2. `push(v,L,R)` — chỉ lan khi phải đi xuống

Khi một lời gọi cần xử lý **một phần** cây con của nút `v` và `lazy[v]=d`, cần đẩy nhãn cho hai con:

```text
mid = (L+R)//2
apply(left_child,  L,   mid, d)
apply(right_child, mid, R,   d)
lazy[v] = 0
```

Sơ đồ sau `range_add(0,8,+5)`, rồi `push` tại gốc:

```text
TRƯỚC PUSH                          SAU PUSH

         [0,8):76                        [0,8):76
          lazy=5                          lazy=0
         /      \                        /      \
  [0,4):10    [4,8):26             [0,4):30    [4,8):46
   lazy=0      lazy=0               lazy=5      lazy=5
```

Tổng của hai con đã thành `30+46=76`. Tổng của **gốc vẫn là 76**, **không cộng thêm**. Đó là lý do `push` là hành động *chuyển trách nhiệm cập nhật xuống cấp dưới*, chứ không phải *thực hiện thêm một cập nhật dữ liệu mới*.

**Điều kiện tiền đề:** `push` chỉ áp xuống con khi đoạn nút có **ít nhất hai phần tử**. Với lá, không có con hợp lệ để đẩy.

### 3.3. `pull(v)` — dựng lại kết quả của cha

Sau khi đi xuống cập nhật một phần các con, ta gộp lại:

```text
tree[v] = tree[2*v] + tree[2*v+1]
```

**Chỉ `pull` khi nhãn của `v` đã được xử lý bằng `push`**, tức `lazy[v]=0`. Nếu nút vẫn đang chứa một nhãn chưa đẩy, cộng đơn giản hai giá trị con sẽ làm **mất tác động của nhãn ở cha**.

Ba động tác có thứ tự dễ nhớ:

```text
Cập nhật phủ trọn:       apply -> dừng
Cập nhật giao một phần:  push -> đi xuống -> pull
Truy vấn phủ trọn:       lấy tree[v] -> dừng
Truy vấn giao một phần:  push -> hỏi con -> gộp đáp án
```

### 3.4. Quy ước đặt tên và trách nhiệm

| Hàm | Nhận gì? | Sửa gì? | Khi nào gọi? |
| --- | --- | --- | --- |
| `apply(v,L,R,d)` | Nút được cập nhật đồng đều | Tổng của nút và nhãn đang đợi | Đoạn của nút được cập nhật toàn bộ |
| `push(v,L,R)` | Nút có nhãn cần giao cho con | Hai con; xóa nhãn ở cha | Trước khi đi sâu vào một nút trong |
| `pull(v)` | Nút có con đã được sửa | Tính lại tổng từ hai con | Sau cập nhật giao một phần |

Ba thao tác là **O(1)** đối với tổng số học thông thường và nhãn cộng. Số lần chúng được gọi trên một lần cập nhật/truy vấn quyết định độ phức tạp tổng.

## 4. Truy vết cập nhật và truy vấn có trì hoãn

Ta theo dõi các thao tác lên:

```text
A = [1, 2, 3, 4, 5, 6, 7, 8]
Tổng ban đầu = 36
```

### 4.1. Bước 1 — cộng vào toàn đoạn `[0,8)`

Gọi `range_add(0,8,5)`. Nút gốc có đoạn trùng hoàn toàn với đoạn cần cập nhật, nên chỉ cần:

```text
apply(root,[0,8),+5)
    tree[root] = 36 + 5*8 = 76
    lazy[root] = 5
```

**Không đi xuống hai con.** Nếu ngay sau đó gọi `range_sum(0,8)`, truy vấn cũng phủ trọn gốc nên có thể trả **76** ngay; không cần `push`.

### 4.2. Bước 2 — truy vấn một đoạn ở giữa

Gọi `range_sum(2,6)`. Vì truy vấn chỉ phủ một phần `[0,8)`, thuật toán **phải đi xuống**. Trước tiên `push` gốc để hai con nhận đúng lượng cộng:

```text
                                  [0,8)
                              tree=76, lazy=0
                             /                \
                  [0,4)                          [4,8)
              tree=30,lazy=5                tree=46,lazy=5
```

Ở nhánh trái, `[0,4)` lại chỉ giao một phần đoạn hỏi; `push` nhãn +5 tại đó:

```text
[0,2): tree=3 + 5*2 = 13, lazy=5
[2,4): tree=7 + 5*2 = 17, lazy=5
```

Nút `[0,2)` không giao với `[2,6)`, trả 0; nút `[2,4)` được phủ trọn, trả **17** mà không cần đi xuống các lá.

Tương tự nhánh phải:

```text
[4,6): tree=11 + 5*2 = 21, lazy=5
[6,8): tree=15 + 5*2 = 25, lazy=5
```

`[4,6)` phủ trọn nên trả **21**, `[6,8)` không giao trả 0. Kết quả cuối:

\[
\operatorname{sum}(2,6)=17+21=38.
\]

Đối chiếu mảng logic sau +5:

```text
[6, 7, 8, 9, 10, 11, 12, 13]
          ^   ^  ^   ^
sum(2,6)=8+9+10+11=38
```

Mỗi lần `push` chỉ chuyển phần công việc đang đợi xuống **một tầng**, không nhất thiết xuống tận lá.

### 4.3. Bước 3 — cập nhật một đoạn chồng lấn

Sau `range_add(0,8,5)` và truy vấn ở trên, tiếp tục gọi `range_add(2,6,3)`:

- Trên `[2,4)`: tổng tăng `3×2=6`, từ **17** thành **23**; nhãn đang đợi của nút trở thành **5+3=8** nếu chưa từng được đẩy xuống hai lá.
- Trên `[4,6)`: tổng tăng từ **21** thành **27**; nhãn tương ứng cũng thành **8**.
- Hai đoạn `[0,2)` và `[6,8)` không bị cộng thêm 3.
- Gốc gộp lại thành `76+3×4=88`.

```text
Mảng logic cuối:
[6, 7, 11, 12, 13, 14, 12, 13]

sum(0,8) = 88
sum(2,6) = 11+12+13+14 = 50
sum(0,2) = 6+7 = 13
```

Điểm đáng chú ý: một cập nhật mới có thể được **cộng vào nhãn cũ của các nút đã phủ trọn**, không cần áp ngay cho từng lá.

### 4.4. Vì sao query cũng có thể `push`?

Một phép truy vấn `range_sum(l,r)` có thể cần đi xuống dưới một nút đang giữ nhãn. Khi đó, để trả đúng tổng ở những con, nó phải `push`.

Vì vậy:

- **Dữ liệu logic không đổi** sau một truy vấn.
- **Biểu diễn bên trong `tree/lazy` có thể đổi** do nhãn được chuyển từ cha xuống con.
- Không nên cho rằng `range_sum` là phép **đọc bất biến bộ nhớ** trong cài đặt này.
- Nếu nhiều luồng truy vấn/cập nhật song song, phải có **cơ chế đồng bộ hoặc phiên bản thích hợp**, không thể kết luận an toàn chỉ từ tên phương thức “query”.

Một kiểu triển khai khác có thể **mang nhãn tổ tiên xuống tham số truy vấn** thay vì sửa cây trong lúc hỏi, nhưng thuật toán và bất biến của nó phải được thiết kế riêng.

## 5. Thuật toán cập nhật đoạn `range_add(l,r,d)`

Mỗi lời gọi `UPDATE(v,L,R,ql,qr,d)` quan tâm ba quan hệ của đoạn nút `[L,R)` với đoạn cập nhật `[ql,qr)`:

1. **Không giao nhau:** `qr≤L` hoặc `R≤ql` → không làm gì.
2. **Nút phủ trọn trong đoạn cập nhật:** `ql≤L` và `R≤qr` → `apply` nhãn và **dừng**.
3. **Giao một phần:** `push` trước, cập nhật các con, rồi `pull` để xây lại tổng của cha.

```text
UPDATE(v,L,R,ql,qr,d):
    if qr <= L or R <= ql:
        return

    if ql <= L and R <= qr:
        APPLY(v,L,R,d)
        return

    PUSH(v,L,R)                # Bảo đảm dữ liệu con đã nhận nợ cũ.
    M = (L+R)//2
    UPDATE(2*v, L, M, ql,qr,d)
    UPDATE(2*v+1, M, R, ql,qr,d)
    PULL(v)                    # tree[v] = left_sum + right_sum.
```

### 5.1. Chứng minh cập nhật đúng

Xét một lời gọi cho đoạn `[L,R)`:

- **Không giao:** không phần tử nào cần sửa, giữ nguyên nút là đúng.
- **Phủ trọn:** với `R-L` phần tử đều nhận +`d`, `apply` làm tổng tăng chính xác `d(R-L)` và ghi nhãn cần chuyển xuống con. Bất biến biểu diễn được duy trì.
- **Giao một phần:** `push` phân phối tác động cũ còn nợ cho các con, nên mỗi con có trạng thái đúng trước cập nhật mới. Theo quy nạp, hai lời gọi con cập nhật đúng những phần tử cần sửa. `pull` gộp hai tổng đã cập nhật thành tổng chính xác của `[L,R)`.

Do đó, sau `range_add`, mọi đoạn được cập nhật đúng về mặt logic dù nhiều lá còn chứa giá trị vật lý cũ.

### 5.2. Cập nhật cùng một đoạn nhiều lần

Ví dụ:

```text
range_add(1,5,+3)
range_add(1,5,-2)
range_add(1,5,+8)
```

Tác động logic cuối là cộng **+9** vào các phần tử trong `[1,5)`. Nếu các cập nhật được giữ trên cùng một nút phủ trọn, nhãn có thể được hợp nhất bằng **phép cộng**:

\[
lazy_{\mathrm{new}}=lazy_{\mathrm{old}}+3-2+8.
\]

**Chỉ với cập nhật “cộng đều”** ta mới có cách hợp nhất đơn giản như thế. Với cập nhật **gán**, một nhãn mới có thể **ghi đè** nhãn cũ; với phép biến đổi tổng quát, phải định nghĩa **hợp thành thao tác**.

## 6. Thuật toán truy vấn đoạn `range_sum(l,r)`

Mỗi lời gọi `QUERY(v,L,R,ql,qr)`:

1. **Không giao:** trả **0** — identity của tổng.
2. **Nút phủ trọn:** trả **`tree[v]`**, bởi tác động của nhãn đã nằm trong tổng này.
3. **Giao một phần:** `push` (nếu có nhãn), hỏi hai con, trả tổng kết quả.

```text
QUERY(v,L,R,ql,qr):
    if qr <= L or R <= ql:
        return 0

    if ql <= L and R <= qr:
        return tree[v]

    PUSH(v,L,R)
    M = (L+R)//2
    left_answer  = QUERY(2*v,L,M,ql,qr)
    right_answer = QUERY(2*v+1,M,R,ql,qr)
    return left_answer + right_answer
```

### 6.1. Tại sao không gọi `pull` sau query?

`push` chỉ **phân phối lại** lượng cập nhật đã có, không đổi dữ liệu logic. Tổng ở cha trước và sau `push` là như nhau. Query cũng không tạo cập nhật mới.

Vì thế, sau khi hỏi con, **không cần `pull` lại cha**. Mã vẫn có thể kiểm tra tổng của cha, nhưng làm thêm là thừa.

### 6.2. Tại sao query không cộng thêm `lazy[v]·length`?

Khi một nút được phủ trọn, `tree[v]` đã lưu tổng sau mọi cập nhật áp dụng tại nó. Nếu trả:

```text
tree[v] + lazy[v] * (R-L)
```

thì sẽ **cộng hai lần** một thao tác. Nếu cần đi sâu hơn, `push` trước rồi dùng các tổng đã được sửa ở con. Đây là hai trường hợp **loại trừ nhau** trong mỗi nhánh đệ quy.

### 6.3. Các trường hợp biên

Với cây gồm `n=8` phần tử:

| Lời gọi | Kết quả theo hợp đồng |
| --- | --- |
| `range_add(0,8,d)` | Cộng cho tất cả 8 phần tử |
| `range_add(4,4,d)` | Không đổi gì, không cần dựng thêm nhãn |
| `range_sum(4,4)` | 0 |
| `range_sum(8,8)` | 0 |
| `range_sum(0,8)` | Tổng toàn mảng, có thể trả ngay tại gốc |
| `range_add(7,8,d)` | Chỉ cộng vào phần tử cuối `A[7]` |
| `range_sum(3,2)` | Báo lỗi: `l>r` |
| `range_sum(-1,4)` | Báo lỗi: chỉ số âm |
| `range_add(0,9,d)` | Báo lỗi: `r>n` |

Trong ví dụ Python dưới đây, mảng rỗng vẫn cho phép `range_sum(0,0)=0` và `range_add(0,0,d)` không làm gì; mọi đoạn không rỗng trên mảng rỗng đều không hợp lệ.

## 7. Vì sao cập nhật và truy vấn đều O(log n)?

Cây đoạn phân chia theo trung điểm nên chiều cao là **O(log n)** với `n≥1`; khi `n=1`, chỉ có gốc đồng thời là lá.

Trong **cập nhật một đoạn liên tiếp**:

- Một nút hoàn toàn nằm ngoài đoạn bị bỏ qua.
- Một nút hoàn toàn nằm trong đoạn chỉ cần **`apply` O(1)** và **không mở rộng cây con**.
- Những nút phải đi sâu hơn là các nút bị **cắt bởi biên trái hoặc biên phải** của đoạn cập nhật.
- Ở mỗi mức của cây, chỉ có **O(1)** nút giao một phần cần tiếp tục mở rộng; các nút đã phủ trọn dừng ngay.

Vì thế, tổng số nút được thăm bị chặn bởi **O(log n)**. Mỗi nút làm O(1) phép toán `apply/push/pull`, nên:

\[
T_{\mathrm{range\_add}}(n)=O(\log(n+1)).
\]

Lập luận tương tự cho **truy vấn đoạn liên tiếp**:

\[
T_{\mathrm{range\_sum}}(n)=O(\log(n+1)).
\]

**Xây cây ban đầu** đến `n` lá có `2n-1` nút thật khi `n≥1`, do đó O(n) nếu mỗi phép cộng O(1). Bộ nhớ `tree` và `lazy` đều là **O(n)**, cùng ngăn xếp đệ quy O(log n).

> Chỉ đếm số mức **không đủ** để chứng minh O(log n) nếu thuật toán mở rộng mọi nhánh: cần thêm tính chất **dừng ngay ở các đoạn phủ trọn** và chỉ mở rộng những nút bị cắt bởi hai ranh giới.

### 7.1. Không nhầm với độ phức tạp của phép gộp

Các cận trên giả định cộng số nguyên có chi phí O(1) theo mô hình RAM. Với số nguyên Python không giới hạn độ dài, số cực lớn khiến phép cộng có chi phí phụ thuộc số chữ số; với chuỗi dài hoặc ma trận kích thước thay đổi, phép `combine` có thể không O(1).

Cấu trúc cây vẫn thăm O(log n) nút, nhưng khi đo thời gian CPU phải tính cả **chi phí xử lý dữ liệu tại nút**.

### 7.2. Vì sao không cần khởi tạo mọi lá sau mỗi cập nhật?

Ví dụ một triệu giá trị, cập nhật `range_add(0,n,1)`:

- Gốc được cập nhật `tree[root]+=n` và `lazy[root]+=1`.
- Không truy cập một triệu lá.
- Lần truy vấn toàn mảng trả ngay tổng từ gốc.
- Chỉ khi hỏi một khoảng nhỏ mới `push` theo những đường cần thiết.

Đây là lợi ích chính của sự **trì hoãn có kiểm soát**: làm công việc khi nó trở nên cần thiết, nhưng vẫn trả kết quả chính xác.

## 8. Python tự chứa: range add + range sum

Lớp `LazyRangeAddSum` sau đây dùng **số nguyên** và chỉ triển khai hai thao tác nền tảng:

- `range_add(left,right,delta)`: cộng `delta` vào mọi `A[i]` với `left≤i<right`.
- `range_sum(left,right)`: trả tổng đúng của đoạn `[left,right)`.

Ngoài ra có `get(i)`, `to_list()` và `validate()` dành cho minh họa/kiểm thử. **Không** giữ một bản sao `A` rồi sửa tuần tự từng phần tử khi gọi `range_add`, bởi làm như vậy sẽ phá mục tiêu O(log n) của thuật toán.

### 8.1. Cài đặt đầy đủ

```python
class LazyRangeAddSum:
    """Range add + range sum, đoạn nửa mở [left,right).

    tree[v]: tổng của nút v, đã gồm tác động lazy[v].
    lazy[v]: delta đã gộp vào tree[v] nhưng chưa truyền xuống con.
    """

    def __init__(self, values):
        data = list(values)
        if any(type(x) is not int for x in data):
            raise TypeError("Ví dụ chỉ hỗ trợ giá trị int")

        self.n = len(data)
        self.tree = [0] * (4 * self.n + 5) if self.n else []
        self.lazy = [0] * (4 * self.n + 5) if self.n else []
        if self.n:
            self._build(1, 0, self.n, data)

    def _build(self, v, left, right, data):
        if right - left == 1:
            self.tree[v] = data[left]
            return

        mid = (left + right) // 2
        self._build(v * 2, left, mid, data)
        self._build(v * 2 + 1, mid, right, data)
        self.tree[v] = self.tree[v * 2] + self.tree[v * 2 + 1]

    def _check_range(self, left, right):
        if type(left) is not int or type(right) is not int:
            raise TypeError("left, right phải là int")
        if not (0 <= left <= right <= self.n):
            raise IndexError("Cần 0 <= left <= right <= n")

    def _apply(self, v, left, right, delta):
        """Áp đồng đều +delta lên cả đoạn của nút."""
        self.tree[v] += delta * (right - left)
        self.lazy[v] += delta

    def _push(self, v, left, right):
        """Chuyển khoản cộng chưa lan từ cha xuống hai con."""
        delta = self.lazy[v]
        if delta == 0 or right - left == 1:
            return

        mid = (left + right) // 2
        self._apply(v * 2, left, mid, delta)
        self._apply(v * 2 + 1, mid, right, delta)
        self.lazy[v] = 0

    def range_add(self, left, right, delta):
        self._check_range(left, right)
        if type(delta) is not int:
            raise TypeError("delta phải là int")
        if left == right or delta == 0:
            return
        self._range_add(1, 0, self.n, left, right, delta)

    def _range_add(self, v, seg_l, seg_r, ql, qr, delta):
        if qr <= seg_l or seg_r <= ql:
            return

        if ql <= seg_l and seg_r <= qr:
            self._apply(v, seg_l, seg_r, delta)
            return

        self._push(v, seg_l, seg_r)
        mid = (seg_l + seg_r) // 2

        self._range_add(v * 2, seg_l, mid, ql, qr, delta)
        self._range_add(v * 2 + 1, mid, seg_r, ql, qr, delta)

        # Sau push, nhãn của v đã bằng 0; tính lại từ con.
        self.tree[v] = self.tree[v * 2] + self.tree[v * 2 + 1]

    def range_sum(self, left, right):
        self._check_range(left, right)
        if left == right:
            return 0
        return self._range_sum(1, 0, self.n, left, right)

    def _range_sum(self, v, seg_l, seg_r, ql, qr):
        if qr <= seg_l or seg_r <= ql:
            return 0

        if ql <= seg_l and seg_r <= qr:
            # tree[v] ĐÃ chứa tác động của lazy[v].
            return self.tree[v]

        self._push(v, seg_l, seg_r)
        mid = (seg_l + seg_r) // 2
        return (
            self._range_sum(v * 2, seg_l, mid, ql, qr)
            + self._range_sum(v * 2 + 1, mid, seg_r, ql, qr)
        )

    def get(self, index):
        if type(index) is not int:
            raise TypeError("index phải là int")
        if not (0 <= index < self.n):
            raise IndexError("index nằm ngoài [0,n)")
        return self.range_sum(index, index + 1)

    def to_list(self):
        """Vật chất hóa mảng logic bằng một lượt duyệt O(n).

        Để lấy đúng lá, hàm sẽ push các nhãn đang chờ xuống
        nhưng không thay đổi dữ liệu logic.
        """
        values = [0] * self.n
        if self.n == 0:
            return values

        def collect(v, left, right):
            if right - left == 1:
                values[left] = self.tree[v]
                return
            self._push(v, left, right)
            mid = (left + right) // 2
            collect(v * 2, left, mid)
            collect(v * 2 + 1, mid, right)

        collect(1, 0, self.n)
        return values

    def validate(self):
        """Kiểm tra nhất quán tổng và nhãn: O(n), chỉ test."""
        if self.n == 0:
            assert self.tree == [] and self.lazy == []
            return True

        def check(v, left, right):
            if right - left == 1:
                return self.tree[v]

            # Chuẩn hóa xuống các con để so sánh tổng của cha.
            self._push(v, left, right)
            mid = (left + right) // 2
            a = check(v * 2, left, mid)
            b = check(v * 2 + 1, mid, right)
            assert self.tree[v] == a + b, (
                f"Tổng không khớp ở đoạn [{left},{right})"
            )
            return self.tree[v]

        check(1, 0, self.n)
        return True
```

### 8.2. Vì sao `_apply` không cập nhật từng lá?

Một nút `v` quản lý `k=right-left` phần tử. Mọi phần tử tăng `delta`, nên tổng nút tăng `k·delta`:

```python
self.tree[v] += delta * (right - left)
self.lazy[v] += delta
```

Không có vòng lặp qua `k` phần tử. Đó chính là công việc O(1) khi một đoạn được phủ hoàn toàn.

### 8.3. Vì sao `_push` không gọi `pull`?

Trước `push`:

\[
tree[v]=tree[left]+tree[right]+lazy[v]\cdot length.
\]

Sau `push` với `d=lazy[v]`:

\[
\begin{aligned}
tree'[left]&=tree[left]+d\cdot length(left),\\
tree'[right]&=tree[right]+d\cdot length(right),\\
lazy'[v]&=0.
\end{aligned}
\]

Vì `length(left)+length(right)=length(v)`:

\[
tree'[left]+tree'[right]=tree[v].
\]

Do vậy, `push` **giữ nguyên `tree[v]`**. Không cần tính lại cha sau thao tác phân phối đơn thuần này.

### 8.4. Minh họa từ cập nhật toàn mảng đến một truy vấn nhỏ

```python
tree = LazyRangeAddSum([1, 2, 3, 4, 5, 6, 7, 8])

assert tree.n == 8
assert tree.range_sum(0, 8) == 36
assert tree.tree[1] == 36

tree.range_add(0, 8, 5)

assert tree.range_sum(0, 8) == 76
assert tree.tree[1] == 76
assert tree.lazy[1] == 5

# Hai con CHƯA nhận +5: hành vi đúng của trì hoãn.
assert tree.tree[2] == 10
assert tree.tree[3] == 26

# Truy vấn phủ trọn gốc ở trên không cần push.
assert tree.lazy[1] == 5

# Truy vấn giao một phần làm root đẩy nợ cho con.
assert tree.range_sum(2, 6) == 38
assert tree.lazy[1] == 0
assert tree.range_sum(0, 2) == 13

tree.range_add(2, 6, 3)
assert tree.range_sum(0, 8) == 88
assert tree.range_sum(2, 6) == 50
assert tree.range_sum(6, 8) == 25
assert tree.to_list() == [6, 7, 11, 12, 13, 14, 12, 13]
assert tree.validate()

# Một lần cập nhật âm cũng dùng chính thuật toán.
tree.range_add(4, 8, -2)
assert tree.to_list() == [6, 7, 11, 12, 11, 12, 10, 11]
assert tree.range_sum(0, 8) == 80
assert tree.range_sum(4, 8) == 44
assert tree.validate()
```

Trong ví dụ này, **`to_list` và `validate` có thể đẩy hết nhãn xuống các lá**. Vì thế chỉ nên kiểm `lazy[root]` **trước** khi gọi các hàm kiểm thử ấy.

### 8.5. Xử lý mảng rỗng và đoạn rỗng

```python
empty = LazyRangeAddSum([])
assert empty.n == 0
assert empty.range_sum(0, 0) == 0
empty.range_add(0, 0, 100)  # Không làm gì.
assert empty.to_list() == []
assert empty.validate()

one = LazyRangeAddSum([7])
assert one.range_sum(0, 1) == 7
one.range_add(0, 1, -9)
assert one.get(0) == -2
assert one.range_sum(0, 0) == 0
assert one.range_sum(1, 1) == 0
assert one.validate()

for left, right in [(-1, 0), (0, 2), (1, 0)]:
    try:
        one.range_sum(left, right)
    except IndexError:
        pass
    else:
        raise AssertionError(f"Đã chấp nhận [{left},{right})")

try:
    empty.range_add(0, 1, 5)
except IndexError:
    pass
else:
    raise AssertionError("Không thể cập nhật ngoài mảng rỗng")
```

Đoạn rỗng vẫn được **kiểm tra ranh giới trước khi bỏ qua**. Nhờ vậy, `range_add(-1,-1,0)` không bị chấp nhận chỉ vì `delta=0`: đoạn âm vẫn là đầu vào sai.

### 8.6. Cập nhật toàn đoạn, truy vấn từng điểm và chi phí vật chất hóa

```python
values = list(range(1, 10))  # 9 phần tử, không phải 2^k.
tree = LazyRangeAddSum(values)

tree.range_add(0, 9, 10)
tree.range_add(4, 9, -3)
tree.range_add(1, 5, 2)

expected = [11, 14, 15, 16, 14, 13, 14, 15, 16]
assert tree.to_list() == expected
assert tree.range_sum(0, 9) == sum(expected)
assert tree.range_sum(4, 7) == 14 + 13 + 14
assert tree.get(8) == 16
assert tree.validate()
```

Giải thích phép biến đổi trên:

- Ban đầu `1..9`.
- Cộng +10 toàn mảng → `11..19`.
- Trừ 3 ở `[4,9)` → các phần tử cuối thành `12,13,14,15,16`.
- Cộng 2 ở `[1,5)` → các phần tử `A[1..4]` tăng thêm 2.

Đừng tính `to_list()` sau mỗi cập nhật trong một benchmark rồi kết luận `range_add` tốn O(n): **vật chất hóa cả mảng là một thao tác O(n) riêng**.

## 9. Từ cộng đoạn tới gán đoạn: nhãn không phải lúc nào cũng cộng được

Đến đây, `lazy[v]` chỉ lưu một số `delta` vì mọi thao tác đều có dạng **cộng**. Nếu thêm thao tác:

```text
range_set(l, r, value)  # gán A[i] = value cho mọi i trong [l,r)
```

thì không thể tiếp tục lưu nhãn bằng một số cộng đơn giản.

### 9.1. Hai thứ tự cập nhật cho kết quả khác nhau

Xét một phần tử ban đầu `x=4`:

```text
Cộng +3, rồi GÁN =10:
  4 -> 7 -> 10

GÁN =10, rồi cộng +3:
  4 -> 10 -> 13
```

Vì vậy:

\[
\operatorname{set}_{10}\circ\operatorname{add}_{3}
\ne
\operatorname{add}_{3}\circ\operatorname{set}_{10}.
\]

**Thứ tự áp dụng nhãn là một phần của tính đúng đắn**, không phải chi tiết triển khai có thể đảo tùy ý.

### 9.2. Bảng hợp thành hai loại nhãn

Ký hiệu một nhãn chờ tác động lên mỗi phần tử:

- `ADD(d)`: biến `x` thành `x+d`.
- `SET(s)`: biến `x` thành `s`.

Khi **nhãn mới** đến sau nhãn cũ:

| Nhãn cũ đang đợi | Nhãn mới áp sau | Nhãn kết hợp tương đương |
| --- | --- | --- |
| `ADD(a)` | `ADD(b)` | `ADD(a+b)` |
| `SET(a)` | `SET(b)` | `SET(b)` |
| `ADD(a)` | `SET(b)` | `SET(b)` — bỏ tác động trước |
| `SET(a)` | `ADD(b)` | `SET(a+b)` |

Khi gán toàn bộ một nút quản lý đoạn dài `k` thành `s`, tổng nút thành:

\[
tree[v]=s\cdot k.
\]

Trong trường hợp này **không được** thực hiện `tree[v]+=s*k`, vì gán không phải cộng.

### 9.3. Nếu dùng hai trường `pending_set` và `pending_add`

Một cách biểu diễn là:

```text
pending_set = None hoặc số s
pending_add = số d
```

Nhãn có ý nghĩa:

```text
nếu pending_set is None:   x -> x + d
nếu có pending_set = s:    x -> s + d
```

Khi nhãn mới là `SET(t)`, đặt `pending_set=t` và `pending_add=0`, vì phép gán mới **xóa tác dụng của các nhãn cũ**. Khi nhãn mới là `ADD(d2)`, tăng `pending_add+=d2`, kể cả khi đang có pending set.

**Không dùng giá trị `0` làm dấu hiệu “không có lệnh gán”**: `SET(0)` là một cập nhật thật, khác hoàn toàn “chưa có nhãn gán”. Phải dùng `None` hoặc cờ `has_set`.

Mô hình hai trường trên đủ cho **SET + ADD**. Nếu còn muốn hỗ trợ **nhân hệ số** đồng thời với tổng đoạn, có thể dùng một biểu diễn toán học tổng quát hơn.

## 10. Hợp thành nhãn bằng phép biến đổi affine

Trên số nguyên, một phép biến đổi affine có dạng:

\[
f(x)=m\,x+b.
\]

Nó biểu diễn được các cập nhật:

| Thao tác | `m` | `b` | Ý nghĩa |
| --- | ---: | ---: | --- |
| `ADD(d)` | 1 | `d` | `x\mapsto x+d` |
| `SET(s)` | 0 | `s` | `x\mapsto s` |
| `MUL(t)` | `t` | 0 | `x\mapsto t\,x` |
| Không làm gì | 1 | 0 | `x\mapsto x` |

Với một đoạn có `k` phần tử và **tổng hiện tại `S`**, áp cùng `f` lên tất cả phần tử cho:

\[
\sum_{i=1}^{k}(m x_i+b)
=m\sum_{i=1}^{k}x_i+b\,k
=mS+bk.
\]

Đây là phép `apply` O(1) với thống kê **sum**. Không cần biết từng `x_i`.

### 10.1. Nhãn cũ và nhãn mới hợp thành theo thứ tự nào?

Giả sử một nút đã có nhãn chờ **cũ**:

\[
g(x)=m_gx+b_g.
\]

Nay xuất hiện một cập nhật **mới**:

\[
f(x)=m_fx+b_f.
\]

Vì nhãn mới xảy ra **sau** nhãn cũ, tác động lên mỗi phần tử là:

\[
(f\circ g)(x)
=m_f(m_gx+b_g)+b_f
=(m_fm_g)x+(m_fb_g+b_f).
\]

Do đó:

\[
\boxed{
\operatorname{compose}(\text{new}=f,\text{old}=g)
=(m_fm_g,\;m_fb_g+b_f).
}
\]

**Không đảo thành `g∘f`**. Đặc biệt với `SET` (`m_f=0`), công thức tự động **loại bỏ nhãn cũ** và giữ nhãn gán mới.

### 10.2. Ví dụ thứ tự nhãn

Trước tiên cộng +5, rồi gán bằng 2:

```text
old = (1,5)    # x -> x+5
new = (0,2)    # x -> 2
new ∘ old = (0*1, 0*5+2) = (0,2)
```

Trước tiên gán bằng 2, rồi cộng +5:

```text
old = (0,2)    # x -> 2
new = (1,5)    # x -> x+5
new ∘ old = (1*0, 1*2+5) = (0,7)
```

Hai kết quả `(0,2)` và `(0,7)` khác nhau. Công thức hợp thành giải quyết cả hai mà **không cần nhánh xử lý riêng cho mỗi cặp SET/ADD**.

### 10.3. Nhãn affine có phép hợp thành kết hợp

Hợp thành hàm thỏa:

\[
(h\circ f)\circ g=h\circ(f\circ g).
\]

Nhãn đơn vị là `I(x)=x` hay `(m=1,b=0)`. Vì có tính kết hợp và phần tử đơn vị, nhiều cập nhật đang đợi có thể được gộp thành **một nhãn duy nhất**, nhưng **không** phải giao hoán; thứ tự thời gian vẫn quan trọng.

Trong cây đoạn:

1. `apply(v,f)` cập nhật **tổng của nút** bằng `m_f S+b_f len`.
2. `apply` lưu nhãn mới tại `v` bằng `f∘old_tag[v]`.
3. `push(v)` áp **nhãn đang đợi của `v`** xuống cả hai con bằng cùng phép `apply`.
4. Xóa nhãn chờ ở cha bằng `I=(1,0)`.
5. Sau cập nhật giao một phần, `pull(v)` cộng tổng hai con.

Điều quan trọng: khi `apply` đến một nút con có nhãn cũ, **phải đặt nhãn cha đẩy xuống ở phía ngoài** của nhãn cũ: `new∘old`. Nếu đảo, các cập nhật xen kẽ `SET/ADD/MUL` sẽ cho kết quả sai.

### 10.4. Bất biến của cây affine

Với `tag[v]=(m,b)`, nếu hai nút con chưa nhận nhãn tại cha nhưng tổng mỗi con đã tính đúng phần việc riêng của nó, bất biến cục bộ là:

\[
tree[v]
=m\bigl(tree[2v]+tree[2v+1]\bigr)+b(R-L).
\]

Khi `tag[v]=(1,0)`, công thức rút về `tree[v]=tree[left]+tree[right]`.

Khi `push` áp nhãn xuống từng con, hai tổng con cộng lại vẫn đúng tổng `tree[v]`, nên **không thay đổi tổng cha**; chỉ thay đổi nơi lưu trách nhiệm áp dụng cập nhật.

## 11. Python mở rộng: cộng, gán và nhân đoạn với tổng đoạn

Lớp `LazyAffineSum` sử dụng hai mảng nhãn:

- `lazy_mul[v]`: hệ số `m` của thao tác đang đợi.
- `lazy_add[v]`: hằng số `b` của thao tác đang đợi.

Hợp đồng công khai:

| Phương thức | Nghĩa |
| --- | --- |
| `range_add(l,r,d)` | Mỗi `A[i]` trong `[l,r)` thành `A[i]+d` |
| `range_set(l,r,s)` | Mỗi `A[i]` trong `[l,r)` thành `s` |
| `range_mul(l,r,m)` | Mỗi `A[i]` trong `[l,r)` thành `m·A[i]` |
| `range_sum(l,r)` | Tổng của các giá trị logic hiện tại trong `[l,r)` |
| `to_list()` | Vật chất hóa toàn bộ giá trị logic, O(n) |

Lưu ý, **nhân cả đoạn với `m` có thể âm** vẫn cập nhật được tổng theo công thức affine. Nhưng nếu thống kê lưu ở mỗi nút là `min/max`, phép nhân âm có thể **đổi vai trò min và max**, nên không được sao chép công thức tổng sang cây min/max.

### 11.1. Toàn bộ lớp `LazyAffineSum`

```python
class LazyAffineSum:
    """Sum với range add / range set / range multiply.

    Mỗi nhãn chờ là hàm affine f(x) = mul*x + add.
    Khi nhãn mới f tới sau nhãn cũ g: lưu f o g.
    """

    def __init__(self, values):
        data = list(values)
        if any(type(x) is not int for x in data):
            raise TypeError("Ví dụ yêu cầu số nguyên int")

        self.n = len(data)
        size = 4 * self.n + 5
        self.tree = [0] * size if self.n else []
        self.lazy_mul = [1] * size if self.n else []
        self.lazy_add = [0] * size if self.n else []

        if self.n:
            self._build(1, 0, self.n, data)

    def _build(self, v, left, right, data):
        if right - left == 1:
            self.tree[v] = data[left]
            return

        mid = (left + right) // 2
        self._build(v * 2, left, mid, data)
        self._build(v * 2 + 1, mid, right, data)
        self.tree[v] = self.tree[v * 2] + self.tree[v * 2 + 1]

    def _check_range(self, left, right):
        if type(left) is not int or type(right) is not int:
            raise TypeError("Ranh giới phải là số nguyên int")
        if not (0 <= left <= right <= self.n):
            raise IndexError("Cần 0 <= left <= right <= n")

    def _apply(self, v, left, right, mul, add):
        """Áp nhãn mới f(x)=mul*x+add lên đoạn của v."""
        length = right - left

        # Áp f lên tổng đã có tại v.
        self.tree[v] = mul * self.tree[v] + add * length

        # Nhãn mới f đến SAU nhãn cũ g:
        # (mul, add) o (old_mul, old_add).
        self.lazy_mul[v] = mul * self.lazy_mul[v]
        self.lazy_add[v] = mul * self.lazy_add[v] + add

    def _push(self, v, left, right):
        mul = self.lazy_mul[v]
        add = self.lazy_add[v]
        if (mul == 1 and add == 0) or right - left == 1:
            return

        mid = (left + right) // 2
        self._apply(v * 2, left, mid, mul, add)
        self._apply(v * 2 + 1, mid, right, mul, add)

        # Nhãn cha đã được chuyển xuống, đặt về identity.
        self.lazy_mul[v] = 1
        self.lazy_add[v] = 0

    def _update(self, left, right, mul, add):
        self._check_range(left, right)
        if type(mul) is not int or type(add) is not int:
            raise TypeError("mul và add phải là int")
        if left == right or (mul == 1 and add == 0):
            return
        self._range_apply(1, 0, self.n, left, right, mul, add)

    def _range_apply(self, v, seg_l, seg_r, ql, qr, mul, add):
        if qr <= seg_l or seg_r <= ql:
            return

        if ql <= seg_l and seg_r <= qr:
            self._apply(v, seg_l, seg_r, mul, add)
            return

        self._push(v, seg_l, seg_r)
        mid = (seg_l + seg_r) // 2
        self._range_apply(
            v * 2, seg_l, mid, ql, qr, mul, add
        )
        self._range_apply(
            v * 2 + 1, mid, seg_r, ql, qr, mul, add
        )
        self.tree[v] = self.tree[v * 2] + self.tree[v * 2 + 1]

    def range_add(self, left, right, delta):
        self._update(left, right, mul=1, add=delta)

    def range_set(self, left, right, value):
        self._update(left, right, mul=0, add=value)

    def range_mul(self, left, right, factor):
        self._update(left, right, mul=factor, add=0)

    def range_sum(self, left, right):
        self._check_range(left, right)
        if left == right:
            return 0
        return self._range_sum(1, 0, self.n, left, right)

    def _range_sum(self, v, seg_l, seg_r, ql, qr):
        if qr <= seg_l or seg_r <= ql:
            return 0

        if ql <= seg_l and seg_r <= qr:
            return self.tree[v]

        self._push(v, seg_l, seg_r)
        mid = (seg_l + seg_r) // 2
        return (
            self._range_sum(v * 2, seg_l, mid, ql, qr)
            + self._range_sum(v * 2 + 1, mid, seg_r, ql, qr)
        )

    def to_list(self):
        """Vật chất hóa trạng thái logic bằng O(n) công việc."""
        result = [0] * self.n
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

    def validate(self):
        """Kiểm tra tổng, sau khi đẩy nhãn để dễ so sánh."""
        if self.n == 0:
            assert self.tree == []
            return True

        def check(v, left, right):
            if right - left == 1:
                return self.tree[v]

            self._push(v, left, right)
            mid = (left + right) // 2
            a = check(v * 2, left, mid)
            b = check(v * 2 + 1, mid, right)
            assert self.tree[v] == a + b, (
                f"Tổng sai ở đoạn [{left},{right})"
            )
            return self.tree[v]

        check(1, 0, self.n)
        return True
```

### 11.2. Điểm then chốt: nhãn mới nằm ngoài nhãn cũ

Hai dòng:

```python
self.lazy_mul[v] = mul * self.lazy_mul[v]
self.lazy_add[v] = mul * self.lazy_add[v] + add
```

diễn đạt đúng công thức `f∘g`, với `f` là nhãn mới và `g` là nhãn cũ đang chờ. Đây là nơi phải kiểm tra kỹ nhất nếu thêm loại cập nhật khác.

Đặc biệt:

- Nếu `range_set(l,r,0)`, nhãn mới `(0,0)` **khác identity `(1,0)`**. Các số trước đó phải trở thành 0.
- Nếu tiếp theo `range_add(l,r,7)`, nhãn kết hợp trở thành `(0,7)`, tức các phần tử được gán bằng 7.
- Nếu tiếp theo `range_mul(l,r,-1)`, nhãn thành `(0,-7)`, tức các phần tử được gán bằng −7.

Không kiểm tra trạng thái đang đợi bằng `if add == 0`. Nhãn `SET(0)` có `add=0` nhưng `mul=0` và vẫn phải được đẩy xuống.

### 11.3. Kiểm tra chuỗi cập nhật chồng lấn

```python
tree = LazyAffineSum([1, 2, 3, 4])
assert tree.range_sum(0, 4) == 10

# Cộng 5 vào toàn đoạn.
tree.range_add(0, 4, 5)
assert tree.range_sum(0, 4) == 30
assert tree.to_list() == [6, 7, 8, 9]

# Gán các vị trí 1,2 bằng 2.
tree.range_set(1, 3, 2)
assert tree.to_list() == [6, 2, 2, 9]
assert tree.range_sum(0, 4) == 19

# Cộng 3 vào [2,4).
tree.range_add(2, 4, 3)
assert tree.to_list() == [6, 2, 5, 12]
assert tree.range_sum(0, 4) == 25

# Nhân -1 vào [0,3).
tree.range_mul(0, 3, -1)
assert tree.to_list() == [-6, -2, -5, 12]
assert tree.range_sum(0, 4) == -1
assert tree.range_sum(1, 3) == -7

# Gán 0 cho toàn đoạn: KHÔNG phải bỏ qua cập nhật.
tree.range_set(0, 4, 0)
assert tree.range_sum(0, 4) == 0
assert tree.to_list() == [0, 0, 0, 0]

tree.range_add(1, 2, 7)
assert tree.to_list() == [0, 7, 0, 0]
assert tree.range_sum(0, 4) == 7
assert tree.validate()
```

### 11.4. Đảo thứ tự gán và cộng để tìm lỗi hợp thành

```python
add_then_set = LazyAffineSum([4])
add_then_set.range_add(0, 1, 3)
add_then_set.range_set(0, 1, 10)
assert add_then_set.range_sum(0, 1) == 10

set_then_add = LazyAffineSum([4])
set_then_add.range_set(0, 1, 10)
set_then_add.range_add(0, 1, 3)
assert set_then_add.range_sum(0, 1) == 13

# Nhiều lần gán: chỉ giá trị gán cuối cùng có hiệu lực.
set_then_add.range_set(0, 1, 9)
set_then_add.range_set(0, 1, 0)
assert set_then_add.range_sum(0, 1) == 0
set_then_add.range_add(0, 1, -6)
assert set_then_add.range_sum(0, 1) == -6
```

Các phép thử một phần tử dễ hiểu nhưng **chưa đủ** để bắt lỗi đẩy nhãn giữa các tầng. Bởi vậy cần thêm trường hợp trên cây dài với cập nhật phủ gốc, rồi sửa một đoạn con chồng lấn.

### 11.5. Tác động xuyên nhiều tầng, kể cả nhân âm

```python
tree = LazyAffineSum([3, 4, 5, 6, 7])

tree.range_add(0, 5, 2)    # [5, 6, 7, 8, 9]
tree.range_set(1, 4, 10)   # [5,10,10,10,9]
tree.range_add(2, 5, -3)   # [5,10,7,7,6]
tree.range_mul(1, 5, -2)   # [5,-20,-14,-14,-12]

assert tree.to_list() == [5, -20, -14, -14, -12]
assert tree.range_sum(0, 5) == -55
assert tree.range_sum(1, 4) == -48
assert tree.range_sum(3, 3) == 0
assert tree.validate()

# Mảng rỗng: chỉ chấp nhận đoạn rỗng [0,0).
empty = LazyAffineSum([])
assert empty.range_sum(0, 0) == 0
empty.range_set(0, 0, 99)
empty.range_add(0, 0, 3)
empty.range_mul(0, 0, -2)
assert empty.to_list() == []
assert empty.validate()
```

**Giới hạn của ví dụ:** lớp chỉ đảm bảo tổng đúng với **giá trị số nguyên**. Nó không áp tự động cho một truy vấn `min/max/gcd`, vì phép tác động của nhãn lên giá trị tóm tắt phải được định nghĩa riêng. Các thao tác được giả định diễn ra **tuần tự**, không thay đổi đồng thời giữa lúc `push` đang sửa các con.

## 12. Kiểm thử đối chiếu (differential testing)

Khi viết cây lazy, có nhiều lỗi chỉ xuất hiện **sau hàng chục cập nhật chồng lấn** hoặc lúc `n` không phải lũy thừa hai. Vì vậy, ngoài ví dụ tính tay, nên so sánh với **mảng tham chiếu** được cập nhật trực tiếp. Với mảng nhỏ, thuật toán tham chiếu O(n) dễ đọc và đóng vai trò *oracle* độc lập.

### 12.1. Kế hoạch kiểm thử

- Dùng `n=0,1,2` để bắt lỗi mảng rỗng, lá và một lần chia.
- Dùng `n=3,5,13` để bắt lỗi chia đoạn không đều.
- Dùng cả đoạn rỗng `[l,l)`, toàn đoạn `[0,n)` và các đoạn chạm `r=n`.
- Dùng số âm, `delta=0`, gán bằng 0, nhân bằng 0 và bằng số âm.
- Xen kẽ cập nhật **phủ gốc**, **giao một phần**, **nằm trọn trong một nhánh**, rồi truy vấn từng điểm/đoạn.
- Dùng **seed cố định** để có thể tái hiện cùng một chuỗi thao tác khi phát hiện lỗi.
- So sánh **mọi đoạn hợp lệ** sau từng lượt ở các mảng nhỏ; không chỉ hỏi `[0,n)`.
- Sau cùng, `to_list()` phải trùng danh sách oracle; `validate()` phải kiểm tổng các nút.

### 12.2. Mã kiểm thử với seed cố định

Đoạn sau là **bộ kiểm thử để người học tự chạy** sau khi chép hai lớp vào cùng một tệp Python. Nó không phải kết quả chạy thực tế của bước biên soạn bài.

```python
from random import Random

rng = Random(2026)

for n in [0, 1, 2, 3, 5, 8, 13]:
    initial = [rng.randint(-10, 10) for _ in range(n)]

    add_ref = list(initial)
    add_tree = LazyRangeAddSum(initial)

    mixed_ref = list(initial)
    mixed_tree = LazyAffineSum(initial)

    for _ in range(60):
        left = rng.randrange(n + 1)
        right = rng.randrange(left, n + 1)

        # Thử cây chỉ cộng đoạn.
        delta = rng.randint(-5, 5)
        add_tree.range_add(left, right, delta)
        for i in range(left, right):
            add_ref[i] += delta

        # Thử cây hỗ trợ ba kiểu biến đổi.
        op = rng.choice(["add", "set", "mul"])
        if op == "add":
            d = rng.randint(-5, 5)
            mixed_tree.range_add(left, right, d)
            for i in range(left, right):
                mixed_ref[i] += d
        elif op == "set":
            value = rng.randint(-8, 8)
            mixed_tree.range_set(left, right, value)
            for i in range(left, right):
                mixed_ref[i] = value
        else:
            factor = rng.choice([-2, -1, 0, 1, 2])
            mixed_tree.range_mul(left, right, factor)
            for i in range(left, right):
                mixed_ref[i] *= factor

        # Tất cả các truy vấn nửa mở hợp lệ.
        for l in range(n + 1):
            for r in range(l, n + 1):
                assert add_tree.range_sum(l, r) == sum(add_ref[l:r])
                assert (
                    mixed_tree.range_sum(l, r)
                    == sum(mixed_ref[l:r])
                )

    assert add_tree.to_list() == add_ref
    assert mixed_tree.to_list() == mixed_ref
    assert add_tree.validate()
    assert mixed_tree.validate()
```

Đoạn mã cố ý dùng mảng nhỏ để việc hỏi **mọi `[l,r)`** không quá lớn. Đối với benchmark hiệu năng, **không** nên tính những lần so sánh toàn mảng và `validate` vào thời gian của `range_add/range_sum`.

### 12.3. Kiểm riêng đầu vào không hợp lệ

```python
trees = [
    LazyRangeAddSum([1, 2, 3]),
    LazyAffineSum([1, 2, 3]),
]

bad_ranges = [(-1, 2), (0, 4), (3, 2)]
for tree in trees:
    for left, right in bad_ranges:
        try:
            tree.range_sum(left, right)
        except IndexError:
            pass
        else:
            raise AssertionError(f"Đã chấp nhận [{left},{right})")

    try:
        tree.range_sum(True, 2)
    except TypeError:
        pass
    else:
        raise AssertionError("True không được dùng như chỉ số 1")

    try:
        tree.range_add(0, 3, True)
    except TypeError:
        pass
    else:
        raise AssertionError("Delta bool không phải int")
```

Vì Python coi `bool` là một lớp con của `int`, dùng `type(x) is int` trong ví dụ là một **quyết định hợp đồng** rõ ràng. Trong ứng dụng khác, nếu chấp nhận kiểu số rộng hơn, phải điều chỉnh kiểm tra kiểu cho phù hợp, không để ranh giới và phép toán trở nên mơ hồ.

## 13. Thiết kế lazy cho thống kê khác tổng

Nguyên tắc tổng quát: một nút lưu **thống kê `S` của cả đoạn**, còn nhãn biểu diễn **phép tác động `f` lên từng phần tử**. Phải có cách tính **`apply(f,S,length)`** mà không phải mở từng lá, cùng phép hợp thành nhãn **`compose(new,old)`**.

### 13.1. Bảng tương thích điển hình

| Thống kê nút | Cập nhật đoạn | Công thức áp lên nút | Ghi chú |
| --- | --- | --- | --- |
| `sum` | Cộng `d` | `sum += d·length` | Một nhãn cộng |
| `sum` | Gán `s` | `sum = s·length` | Ghi đè cập nhật cũ theo đúng thứ tự |
| `sum` | Nhân `m` | `sum *= m` | Có thể hợp với ADD/SET bằng affine |
| `min` | Cộng `d` | `min += d` | Không nhân độ dài |
| `max` | Cộng `d` | `max += d` | Không nhân độ dài |
| `min`, `max` | Gán `s` | Cả hai thành `s` nếu đoạn không rỗng | Cần nhãn gán |
| `min`, `max` | Nhân số âm | Min/max **đổi vai trò** sau khi nhân | Nên lưu cả min và max |
| `gcd` | Cộng đều `d` | **Không có công thức từ gcd đơn lẻ** | Cần metadata khác hoặc thuật toán khác |
| Ghép chuỗi | Thay mọi phần tử bằng chuỗi `s` | Nối `s` lặp `length` lần | Chi phí tạo chuỗi có thể O(length·|s|) |

**Không có một dạng lazy “universal” cho mọi toán tử.** Thông thường ta phải chứng minh hàm tác động lên thống kê giữ được kết quả chính xác.

### 13.2. Phản ví dụ: chỉ biết GCD không đủ để cộng đoạn

Hai đoạn khác nhau:

```text
Đoạn A: [2, 4]     gcd = 2
Đoạn B: [2, 6]     gcd = 2
```

Cộng +2 vào mọi phần tử:

```text
A' = [4, 6]        gcd = 2
B' = [4, 8]        gcd = 4
```

Hai đoạn có **cùng gcd ban đầu, cùng độ dài, cùng delta cập nhật**, nhưng gcd sau cập nhật **khác nhau**. Vì vậy không thể tồn tại một công thức **chỉ dùng `(old_gcd,length,delta)`** để cập nhật chính xác gcd trong mọi trường hợp.

Có những cấu trúc hỗ trợ kết hợp cập nhật và truy vấn GCD theo cách khác, nhưng phải lưu và cập nhật **thông tin đủ dùng**. Không thể chỉ thay `tree[v]+=delta*length` bằng một phép toán tùy ý.

### 13.3. Min/max với nhân hệ số âm

Cho đoạn `[-3,2,5]`, `min=-3`, `max=5`. Nhân tất cả với `−2`:

```text
[-3, 2, 5] * -2 = [6, -4, -10]
min' = -10 = (-2) * old_max
max' =   6 = (-2) * old_min
```

Khi `m<0`, min và max **hoán đổi vai trò**. Nếu muốn kết hợp `range_mul` với truy vấn cả min/max, cần lưu đủ hai thống kê và tính đúng theo dấu của `m`.

### 13.4. Điều kiện thiết kế một lazy tag đúng

Với các giá trị đoạn `a_1,\ldots,a_k`, phép gộp `\oplus` và một cập nhật đồng đều `f`, hãy xác định một phép tác động `F` sao cho:

\[
F\bigl(f,\;a_1\oplus\cdots\oplus a_k,\;k\bigr)
=f(a_1)\oplus\cdots\oplus f(a_k).
\]

Ngoài ra, các nhãn phải có:

- **Nhãn đơn vị:** không thay đổi dữ liệu.
- **Hợp thành theo thứ tự:** thực hiện nhãn cũ trước, nhãn mới sau.
- **Tính kết hợp của phép hợp thành**, để gộp nhiều cập nhật mà không phụ thuộc cách nhóm.
- **Sự tương thích với việc gộp hai đoạn liền nhau**, để `push` và `pull` không mất thông tin.

Đây là lý do lazy propagation thường được giới thiệu cùng **monoid** và các phép tác động lên monoid. Tuy nhiên, người mới học có thể bắt đầu từ phép cộng đơn giản rồi chứng minh từng tính chất bằng công thức tổng.

## 14. So sánh với những lựa chọn khác

### 14.1. Mảng chênh lệch cho cập nhật hàng loạt ngoại tuyến

Nếu có **rất nhiều lệnh cộng đoạn**, nhưng **không cần trả lời truy vấn tổng xen giữa các lệnh**, ta có thể dùng **mảng chênh lệch (difference array)**:

```text
add(l,r,d):
    diff[l] += d
    diff[r] -= d        # với diff có ô biên n.
```

Sau khi nhận tất cả cập nhật, quét tổng tiền tố của `diff` để khôi phục các giá trị `A` trong O(n). Mỗi lệnh cập nhật chỉ cần O(1).

**Giới hạn:** Nếu người dùng hỏi `sum(l,r)` ngay sau từng cập nhật trong một luồng trực tuyến, việc phải vật chất hóa/tính lại các giá trị từ chênh lệch có thể tốn nhiều công. Lazy segment tree hỗ trợ cả cập nhật và truy vấn **xen kẽ** trong O(log n).

### 14.2. Fenwick tree và các phép cộng đoạn

Fenwick tree thường được học qua **cộng một điểm** và **hỏi tổng tiền tố**. Với hai Fenwick tree và biến đổi phù hợp, ta cũng có thể hỗ trợ **range add + range sum** trong O(log n) mỗi thao tác.

Nếu bài toán chỉ cần hai chức năng đó, phương án Fenwick có thể gọn và tiết kiệm hằng số. Lazy segment tree thường có lợi thế mở rộng khái niệm sang **SET/ADD**, **min/max**, **thuộc tính kết hợp** hoặc các bài toán tổng hợp phức tạp.

### 14.3. Segment tree chỉ hỗ trợ điểm

Cây không lazy có thể xử lý `range_add(l,r,d)` bằng vòng lặp:

```text
for i in [l,r):
    point_set(i, point_get(i) + d)
```

Thời gian là O(k log n) với `k=r-l`. Phương án này có thể chấp nhận nếu mỗi đoạn cập nhật rất ngắn hoặc số cập nhật ít, nhưng không đem lại cận **O(log n)** cho cập nhật cả đoạn dài.

### 14.4. Bảng lựa chọn

| Tải công việc | Cấu trúc đáng cân nhắc |
| --- | --- |
| Ít thao tác, mảng nhỏ | Mảng thường và duyệt trực tiếp |
| Chỉ nhiều truy vấn tổng trên dữ liệu bất biến | Prefix sum, O(1) mỗi truy vấn |
| Nhiều cộng đoạn, chỉ cần kết quả cuối | Difference array, O(1) mỗi lệnh cộng |
| Cộng điểm, hỏi tổng tiền tố/đoạn | Fenwick tree |
| Cộng đoạn và hỏi tổng xen kẽ | Hai Fenwick tree hoặc lazy segment tree |
| Cộng/gán đoạn, hỏi tổng và các thống kê khác | Lazy segment tree với nhãn/metadata tương thích |
| Dữ liệu theo tọa độ rất lớn nhưng thưa | Cây đoạn động, nén tọa độ hoặc cấu trúc chuyên dụng |

**Đánh đổi thực tế** còn phụ thuộc bộ nhớ, hằng số runtime, độ dài phần tử, yêu cầu kiểm thử, khả năng đồng thời và tính sẵn có của thư viện đáng tin cậy.

## 15. Ứng dụng: điều chỉnh lịch và thống kê học tập theo khoảng ngày

Giả sử ứng dụng học cấu trúc dữ liệu lưu thời lượng dự kiến học theo ngày, trong một tuần:

```text
Chỉ số ngày:       0   1   2   3   4   5   6
Số phút A:        30  40  20  50  35  45  25
Tổng tuần:       245
```

Người dùng muốn cộng **10 phút** cho mỗi ngày từ chỉ số 1 đến ngay trước chỉ số 6:

```text
range_add(1, 6, 10)
```

Mảng logic trở thành:

```text
[30, 50, 30, 60, 45, 55, 25]
```

Tổng cả tuần mới:

\[
245 + 10\cdot(6-1)=295.
\]

Truy vấn tổng ngày ở đoạn `[2,5)`:

\[
\operatorname{sum}(2,5)=30+60+45=135.
\]

Nếu các ngày `[3,5)` bị hủy kế hoạch, cần **gán 0**, không phải cộng 0:

```text
range_set(3, 5, 0)
Mảng logic: [30, 50, 30, 0, 0, 55, 25]
Tổng mới: 190
```

Hai loại cập nhật **cộng** và **gán** khiến việc hợp thành nhãn theo đúng thứ tự trở thành yêu cầu thực tế.

### 15.1. Kiểm tra tình huống bằng mã

```python
plan = LazyAffineSum([30, 40, 20, 50, 35, 45, 25])
assert plan.range_sum(0, 7) == 245

plan.range_add(1, 6, 10)
assert plan.range_sum(0, 7) == 295
assert plan.range_sum(2, 5) == 135

plan.range_set(3, 5, 0)
assert plan.to_list() == [30, 50, 30, 0, 0, 55, 25]
assert plan.range_sum(0, 7) == 190
assert plan.range_sum(2, 5) == 30
assert plan.validate()
```

### 15.2. Trục chỉ số không tự đại diện cho ngày lịch

Cây đoạn quản lý các **vị trí liên tiếp** từ 0 đến `n−1`. Nếu ứng dụng lưu ngày lịch rời rạc, phải có ánh xạ từ **ngày → chỉ số** hoặc một quy tắc chuẩn hóa miền thời gian trước khi gọi `range_add`.

Ví dụ, nếu dữ liệu bỏ qua ngày không có bản ghi, một khoảng “từ thứ Hai đến thứ Sáu” không đương nhiên là năm ô liên tiếp trong mảng. Cần xác định:

- Mảng có **một ô cho mỗi ngày lịch** hay chỉ những ngày có bản ghi?
- Những ngày thiếu có giá trị mặc định **0** hay bị loại khỏi miền?
- Chỉ số cuối trong `[l,r)` có được tính không?
- Khi thêm ngày mới, có cần **xây lại cây** hoặc dùng cấu trúc động không?

Lazy propagation xử lý nhanh **đoạn chỉ số**, không tự giải quyết khâu chuyển đổi ý nghĩa nghiệp vụ sang chỉ số.

### 15.3. Cập nhật đồng thời và tính nhất quán

Các hàm `range_add` và `range_set` sửa **nhiều ô trạng thái `tree/lazy`**. `range_sum` cũng có thể gọi `push` và sửa các nhãn trong lúc đọc.

Vì vậy, không được suy từ độ phức tạp O(log n) rằng có thể cho nhiều luồng gọi vào cùng cây **mà không khóa**:

```text
Luồng 1: range_sum(2,6)       Luồng 2: range_set(0,8,0)
   kiểm tra tree[root]           đang cập nhật tổng ở gốc
   bắt đầu push                 nhãn mới chưa nhất quán ở con
   đọc một phần cây             ...
```

Cây có thể bị đọc trong trạng thái **cập nhật dở** nếu không có chiến lược đồng bộ. Các lựa chọn bao gồm khóa đọc/ghi với việc **đánh giá đúng query có push là thao tác ghi**, phiên bản bất biến hoặc snapshot; mỗi lựa chọn có chi phí và hợp đồng riêng.

**Chú ý:** Thêm `lock` quanh một dòng đơn lẻ chưa đủ nếu thao tác còn nhiều bước `apply/push/pull`. Cần bảo vệ phạm vi phù hợp với yêu cầu nhất quán của toàn thao tác.

## 16. Các lỗi thường gặp và cách chẩn đoán

### 16.1. Sai cập nhật tổng hoặc chiều dài đoạn

**Lỗi 1: cộng `d` vào tổng thay vì `d·length`.**

```python
# SAI với range sum:
tree[v] += delta

# ĐÚNG:
tree[v] += delta * (seg_r - seg_l)
```

Nếu cập nhật `[0,8)` với `delta=5`, tổng phải tăng **40**, không phải 5.

**Lỗi 2: dùng độ dài cả mảng cho mọi con.** Mỗi nút phải dùng **`R-L` của chính nó**; con trái/phải có thể có độ dài khác nhau khi `n` không phải lũy thừa hai.

**Lỗi 3: gán đoạn nhưng vẫn cộng vào tổng.** `SET(s)` phải làm tổng thành `s·length`, không phải `sum+s·length`.

### 16.2. Sai thời điểm push/pull

**Lỗi 4: đi xuống khi cha còn nhãn nhưng không `push`.**

Ví dụ `range_add(0,8,5)` mới chỉ sửa gốc. Nếu truy vấn `[2,4)` đi thẳng xuống con vẫn có tổng cũ `7`, kết quả sai; phải đẩy nhãn trước.

**Lỗi 5: `pull` ngay sau `apply` mà chưa `push`.**

Tổng cha đã chứa phần cộng trì hoãn nhưng con chưa nhận. `tree[v]=left+right` ở thời điểm này sẽ **làm mất cập nhật**.

**Lỗi 6: xóa `lazy[v]` trước khi áp cho hai con.**

Nếu quên giữ `delta` tạm hoặc quên truyền cho một con, dữ liệu của một nửa đoạn bị bỏ sót.

**Lỗi 7: `push` vào lá.** Lá không có hai con hợp lệ; phải dừng tại `R-L=1`.

**Lỗi 8: truy vấn phủ trọn nhưng cộng thêm `lazy*length`.** Tổng nút đã chứa nhãn; thêm lần nữa là **đếm hai lần**.

### 16.3. Sai cách hợp thành cập nhật

**Lỗi 9: coi `SET(0)` là “không có nhãn”.** Gán bằng 0 phải được lưu; nó khác identity.

**Lỗi 10: gán mới không xóa nợ cộng cũ.** `ADD(5)` rồi `SET(2)` phải cho `2`, không phải `7`.

**Lỗi 11: đảo thứ tự hai nhãn.** Trong mã affine, khi nhãn mới `f` xuất hiện sau nhãn cũ `g`, phải dùng **`f∘g`**, không phải `g∘f`.

**Lỗi 12: sử dụng công thức cho sum để cập nhật min/max.** Khi cộng đều delta, `sum` tăng `delta·length`, nhưng `min/max` chỉ tăng `delta`.

**Lỗi 13: nhân âm vào min mà không biết max cũ.** Phải xét đổi vai trò min/max hoặc lưu cả hai.

**Lỗi 14: cho rằng mọi phép gộp đều hỗ trợ cộng đoạn O(1).** GCD một đoạn không thể cập nhật từ **GCD cũ và delta** trong mọi trường hợp.

### 16.4. Sai ranh giới và tính phức tạp

**Lỗi 15: dùng `[l,r]` trong một hàm và `[l,r)` trong hàm khác.** Dễ cập nhật thiếu/thừa một phần tử.

**Lỗi 16: xem `[l,l)` là đoạn một phần tử.** Đây là đoạn rỗng; cập nhật không làm gì, tổng bằng 0.

**Lỗi 17: bỏ qua kiểm tra đầu vào vì delta bằng 0.** `range_add(-1,3,0)` vẫn là khoảng sai theo hợp đồng.

**Lỗi 18: build trên mảng rỗng như một đoạn có lá.** Phải có nhánh đặc biệt cho `n=0` để không chia đoạn rỗng vô hạn.

**Lỗi 19: “Có push thì mọi cập nhật đoạn vẫn phải sửa từng lá.”** Không: cập nhật phủ trọn dừng ngay tại nút tóm tắt.

**Lỗi 20: đo `range_add` rồi gọi `to_list/validate` trong mỗi vòng và gán O(n) của phép kiểm thử cho cập nhật lõi.** Phải tách chi phí.

**Lỗi 21: tưởng truy vấn là hoàn toàn chỉ đọc.** Query có thể `push` và sửa trạng thái vật lý dù kết quả dữ liệu logic không đổi.

### 16.5. Checklist trước khi dùng lazy propagation

1. Đã xác định đoạn là **`[l,r)`** hay `[l,r]` chưa?
2. Nút lưu **loại thống kê gì**: tổng, min, max, hay một cấu trúc gộp?
3. `apply(tag,aggregate,length)` có công thức chính xác không?
4. Có **nhãn đơn vị** và **quy tắc hợp thành** rõ ràng không?
5. Thứ tự **nhãn mới sau nhãn cũ** đã được xử lý đúng không?
6. Cập nhật phủ trọn có **`apply` rồi dừng**, không ép xuống lá không?
7. Khi đi sâu, có `push` **trước** khi sửa hoặc hỏi các con không?
8. Sau cập nhật giao một phần, có `pull` về cha không?
9. Có tránh `pull` thừa hoặc cộng nhãn hai lần khi truy vấn không?
10. Có xử lý `n=0`, `n=1`, n không phải lũy thừa hai không?
11. Có thử các đoạn `[l,l)` và `[0,n)` không?
12. Có thử delta âm, delta 0, `SET(0)` và phép nhân âm không?
13. Có kiểm tra mọi đoạn sau nhiều cập nhật chồng lấn bằng oracle độc lập không?
14. Có tính đúng chi phí phép gộp khi dữ liệu lớn không?
15. Có phân biệt `range_add` với `range_set` và `range_mul` trong API không?
16. Có tách `to_list/validate/log` ra khỏi thời gian đo thao tác lõi không?
17. Nếu nhiều luồng dùng cây, đã có hợp đồng nhất quán và đồng bộ phù hợp không?

## 17. Bài tập vận dụng

### Bài 1 — Hiểu đoạn nửa mở

Với `n=8`, liệt kê các chỉ số được tác động bởi `range_add(2,6,5)`. Đoạn `[6,6)` chứa bao nhiêu phần tử?

*Gợi ý:* `[2,6)` gồm `2,3,4,5`; `[6,6)` là đoạn rỗng.

### Bài 2 — Vì sao lặp point update chưa đủ?

Giả sử cập nhật `k=n/2` phần tử bằng `k` lệnh `set`, mỗi lệnh O(log n). Tổng chi phí là bao nhiêu? Cây lazy cải thiện thế nào?

*Gợi ý:* Cách lặp O(n log n) trong trường hợp này; lazy range update O(log n).

### Bài 3 — Tính tổng sau cộng đoạn

Cho `A=[1,2,3,4,5,6,7,8]`. Sau `range_add(0,8,5)`, tổng toàn mảng bằng bao nhiêu?

*Gợi ý:* Tổng cũ 36; tăng `5×8=40`; tổng mới 76.

### Bài 4 — Ý nghĩa của lazy tại gốc

Sau Bài 3, vì sao `tree[root]=76` trong khi `tree[left]=10` và `tree[right]=26` vẫn chưa đổi mà thuật toán vẫn đúng?

*Gợi ý:* `lazy[root]=5` đang ghi nhận khoản cộng đã nằm trong tổng gốc nhưng chưa chuyển xuống con.

### Bài 5 — Đẩy nhãn vào hai con

Khi `root` quản lý `[0,8)` và `lazy[root]=5`, hãy tính tổng mới của hai con `[0,4)` và `[4,8)` sau `push`.

*Gợi ý:* `10+5×4=30`, `26+5×4=46`; gốc vẫn là 76.

### Bài 6 — Tại sao phải nhân độ dài riêng?

Một nút quản lý `[2,7)` nhận `delta=-3`. Tổng của nút thay đổi bao nhiêu? Nếu hai con lần lượt có độ dài 2 và 3, chúng nhận thay đổi tổng bao nhiêu?

*Gợi ý:* Toàn nút `-3×5=-15`; hai con thay đổi `-6` và `-9`.

### Bài 7 — Bất biến biểu diễn cục bộ

Viết công thức liên hệ `tree[v]` với hai tổng con và `lazy[v]` cho bản **range-add/range-sum**, khi nút `v` quản lý đoạn `[L,R)`.

*Gợi ý:* `tree[v]=tree[left]+tree[right]+lazy[v](R-L)`.

### Bài 8 — Khi nào được pull?

Tại sao không được gán `tree[v]=tree[left]+tree[right]` ngay sau một cập nhật phủ trọn khi `lazy[v]` vẫn còn khác 0?

*Gợi ý:* Hai con chưa phản ánh nhãn của cha; phép gộp đó làm mất khoản cộng đang đợi.

### Bài 9 — Khi nào query không push?

Vừa gọi `range_add(0,8,5)` xong, truy vấn `range_sum(0,8)` có phải đẩy nhãn ở gốc không? Vì sao?

*Gợi ý:* Không; đoạn truy vấn phủ trọn, `tree[root]` đã có tổng 76.

### Bài 10 — Query giao một phần

Sau `range_add(0,8,5)`, cần trả `range_sum(2,6)`. Trình bày những nút phủ trọn được lấy và kết quả của chúng.

*Gợi ý:* Sau push tại các nút giao một phần, `[2,4)` trả 17, `[4,6)` trả 21; tổng 38.

### Bài 11 — Hai cập nhật chồng lấn

Trên `[1,2,3,4,5,6,7,8]`, lần lượt cộng +5 cho `[0,8)` và +3 cho `[2,6)`. Viết mảng logic và tổng cuối.

*Gợi ý:* `[6,7,11,12,13,14,12,13]`, tổng 88.

### Bài 12 — Nhãn cộng được hợp nhất thế nào?

Một nút `[2,4)` còn nợ nhãn +5. Cập nhật mới phủ trọn nút với delta +3. Nhãn và tổng nút thay đổi thế nào?

*Gợi ý:* Nhãn trở thành +8; tổng tăng thêm `3×2=6` so với ngay trước lệnh mới.

### Bài 13 — Trừ trên một đoạn

Vì sao có thể thực hiện “trừ 4 trên `[l,r)`” bằng `range_add(l,r,-4)` mà không cần thuật toán mới?

*Gợi ý:* Trừ 4 tương đương cộng −4; công thức sum và hợp nhất nhãn giữ nguyên.

### Bài 14 — Mảng rỗng và đoạn rỗng

Với `n=0`, các lời gọi `range_sum(0,0)`, `range_add(0,0,7)` và `range_add(0,1,7)` phải cho kết quả gì theo hợp đồng trong bài?

*Gợi ý:* Lần lượt trả 0, không làm gì, và báo lỗi ngoài miền.

### Bài 15 — Cập nhật đoạn cuối cùng

Với `n=5`, `range_add(4,5,10)` cập nhật bao nhiêu phần tử? Vì sao không được viết `range_add(4,4,10)` để làm điều tương tự?

*Gợi ý:* Chỉ `A[4]`; đoạn `[4,4)` rỗng.

### Bài 16 — Chứng minh O(log n)

Thuật toán cập nhật đoạn có thể gọi đệ quy vào **cả hai con** ở một nút giao một phần. Tại sao tổng số nút được thăm vẫn O(log n) thay vì O(n)?

*Gợi ý:* Mọi nút phủ trọn dừng ngay; ở mỗi mức chỉ O(1) nút nằm sát hai ranh giới cần tiếp tục mở rộng.

### Bài 17 — Dựng cây

Một cây phân hoạch nhị phân tới từng phần tử có `n=11` lá. Số nút trong và tổng số nút thật là bao nhiêu? Vì sao `4n+5` ô là một cấp phát mảng an toàn nhưng không phải số nút thật?

*Gợi ý:* `10` nút trong, `21` nút thật; mảng có thể có ô trống do cách đánh số `v,2v,2v+1`.

### Bài 18 — Min/max với cộng đoạn

Một nút quản lý `[-4,2,7]` và nhận cộng +5 toàn đoạn. Min và max mới là bao nhiêu? Tổng mới tăng bao nhiêu?

*Gợi ý:* Min 1, max 12; tổng tăng `5×3=15`.

### Bài 19 — Tại sao GCD cũ không đủ?

So sánh `[2,4]` và `[2,6]`: cả hai có GCD ban đầu bằng 2. Sau cộng +2 toàn đoạn, GCD của từng đoạn là gì? Có thể cập nhật từ chỉ `(old_gcd,length,delta)` không?

*Gợi ý:* Một đoạn thành GCD 2, đoạn kia thành GCD 4; không đủ thông tin.

### Bài 20 — ADD rồi SET khác SET rồi ADD

Bắt đầu từ `x=4`, thực hiện `ADD(3)` rồi `SET(10)`. So sánh với `SET(10)` rồi `ADD(3)`.

*Gợi ý:* Kết quả lần lượt 10 và 13; thứ tự cập nhật quan trọng.

### Bài 21 — Gán bằng 0 không phải “không cập nhật”

Trong một cây dùng nhãn SET, vì sao không thể dùng `pending_set=0` để biểu diễn “không có lệnh gán”?

*Gợi ý:* `SET(0)` thực sự xóa giá trị mọi phần tử trong đoạn; cần cờ hoặc `None`.

### Bài 22 — Viết phép hợp thành affine

Cho nhãn cũ `g(x)=2x+3` và nhãn mới `f(x)=−x+5`. Tính `(f∘g)(x)` và cặp `(mul,add)` tương ứng.

*Gợi ý:* `f(g(x))=−(2x+3)+5=−2x+2`, tức `(-2,2)`.

### Bài 23 — Áp affine vào tổng

Một nút có tổng cũ 17 và quản lý 4 phần tử. Áp `f(x)=3x−2` đồng đều vào cả đoạn. Tổng mới là bao nhiêu?

*Gợi ý:* `3×17−2×4=43`.

### Bài 24 — Đúng thứ tự compose

Hai nhãn `ADD(5)=(1,5)` và `SET(2)=(0,2)`. Tính `SET(2)∘ADD(5)` và `ADD(5)∘SET(2)`.

*Gợi ý:* Lần lượt `(0,2)` và `(0,7)`.

### Bài 25 — Nhân âm và min/max

Cho đoạn `[-3,2,5]`, min = −3 và max = 5. Sau nhân tất cả với −2, min/max mới bằng bao nhiêu? Vì sao không thể chỉ nhân min cũ với −2 để lấy min mới?

*Gợi ý:* Min mới −10, max mới 6; khi hệ số âm, min và max đổi vai trò.

### Bài 26 — Kiểm thử qua các lần push

Một người chỉ kiểm `range_sum(0,n)` sau hàng chục lần cập nhật toàn đoạn. Vì sao chưa đủ để chứng minh `push` đúng?

*Gợi ý:* Truy vấn phủ trọn có thể không bao giờ đẩy nhãn; cần hỏi các đoạn nhỏ và kiểm tra nhiều cập nhật chồng lấn.

### Bài 27 — Phát hiện lỗi từ oracle

Hãy viết một vòng lặp kiểm thử lấy `n∈{0,1,5,13}`, phát sinh ngẫu nhiên `l,r,d` hợp lệ, cập nhật cả mảng tham chiếu và cây lazy, rồi so sánh mọi `sum(A[l:r])`.

*Gợi ý:* Dùng seed cố định, giới hạn n nhỏ và so sánh từng đoạn nửa mở sau mỗi cập nhật.

### Bài 28 — Khi nào difference array tốt hơn?

Bạn có một triệu giá trị và 100 nghìn lệnh **cộng đoạn**, nhưng chỉ cần in mảng cuối, không có truy vấn xen giữa. Vì sao difference array có thể hợp lý hơn lazy segment tree?

*Gợi ý:* Mỗi cập nhật trên difference array O(1), khôi phục cuối O(n); không cần truy vấn online.

### Bài 29 — Query có phải chỉ đọc?

Một luồng thực hiện `range_sum(2,6)` trong khi luồng khác thực hiện `range_set(0,8,0)`. Vì sao một phương thức tên “sum” vẫn có thể sửa cấu trúc và tại sao chỉ kiểm phiên bản trước lời gọi chưa chắc đủ an toàn?

*Gợi ý:* `range_sum` có thể `push` và ghi mảng nhãn; cần đồng bộ phù hợp trong toàn bộ thao tác.

### Bài 30 — Thiết kế thống kê học tập theo ngày

Hệ thống cần: cộng thêm phút theo khoảng ngày, **gán 0** cho khoảng ngày bị hủy và hỏi tổng phút trong tuần. Hãy chọn cách lưu nhãn, mô tả cách `apply/push/pull` hoạt động và nêu cận thời gian/bộ nhớ.

*Gợi ý:* Dùng một nhãn `SET/ADD` có quy tắc hợp thành, hoặc cặp affine `(m,b)`; build O(n), cập nhật/truy vấn O(log(n+1)), bộ nhớ O(n).

## 18. Tổng kết

**Lan truyền lười** là kỹ thuật giúp cây đoạn xử lý **cập nhật cả một đoạn** mà không sửa ngay từng lá. Mỗi nút giữ **kết quả tổng hợp đã tính đến tác động của cập nhật**, và một **nhãn trì hoãn** ghi nhớ công việc còn phải chuyển xuống hai con.

Với bài toán **cộng đoạn – hỏi tổng**, ba bước quan trọng là:

1. **`apply`:** tăng `tree[v]` thêm `delta·length` và cộng `delta` vào `lazy[v]` khi đoạn của nút được phủ trọn.
2. **`push`:** trước khi đi sâu, áp khoản cộng còn nợ của cha lên hai con, rồi xóa nhãn chờ ở cha. Tổng logic của cha **không đổi**.
3. **`pull`:** sau khi cập nhật giao một phần ở các con, gộp tổng mới của chúng để xây lại tổng của cha.

Nhờ dừng sớm ở các nút **phủ hoàn toàn** và chỉ tiếp tục mở rộng gần hai ranh giới, cây hỗ trợ **O(n) xây dựng**, **O(log(n+1)) cập nhật đoạn**, **O(log(n+1)) truy vấn đoạn** và **O(n) bộ nhớ**, trong mô hình phép gộp O(1).

Khi có thêm **gán** hoặc **nhân trên đoạn**, không thể hợp nhất mọi nhãn bằng phép cộng. Cần biểu diễn tác động và **hợp thành nhãn mới sau nhãn cũ**. Với truy vấn tổng, phép affine `f(x)=mx+b` có công thức cập nhật nút `S'=mS+b·length` và công thức hợp thành `(m_fm_g,\;m_fb_g+b_f)`. Cách này xử lý thống nhất `ADD`, `SET` và `MUL`, kể cả `SET(0)`.

Không phải mọi thống kê đều cho phép cùng công thức lazy. Việc lựa chọn cấu trúc cần xét **loại cập nhật, thông tin tổng hợp đang lưu, tính kết hợp, phần tử đơn vị, tính đúng của phép tác động, dữ liệu biên và mức đồng thời**. Chỉ sau khi kiểm chứng bằng các trường hợp cập nhật chồng lấn, đoạn rỗng, số âm và bộ kiểm thử đối chiếu độc lập mới nên đánh giá hiệu năng hoặc mở rộng thuật toán.
