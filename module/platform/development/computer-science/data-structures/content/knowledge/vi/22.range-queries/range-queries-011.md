# Cây đoạn (segment tree) và phân chia miền chỉ số

Giả sử một hệ thống thống kê ghi doanh thu theo ngày trong mảng. Người dùng thường hỏi **“Tổng doanh thu từ ngày l đến trước ngày r là bao nhiêu?”**, **“Giá trị nhỏ nhất trong khoảng này là gì?”** và đôi khi sửa số liệu của một ngày. Nếu mỗi truy vấn đều quét qua tất cả các phần tử, một đoạn dài có thể tốn O(n) thời gian. Nếu dùng mảng tổng tiền tố, truy vấn tổng tĩnh nhanh nhưng cập nhật một ngày có thể làm nhiều tiền tố lỗi thời.

**Cây đoạn** (*segment tree*) giải quyết tình huống đó bằng cách **chia miền chỉ số thành các đoạn con có trật tự**, lưu tại mỗi nút một kết quả tổng hợp cho đoạn mà nút quản lý. Các đoạn con được ghép từ dưới lên; truy vấn chỉ thăm các nhánh thực sự cần; cập nhật một điểm chỉ sửa những nút trên đường từ lá tương ứng lên gốc.

Với `n` phần tử và một phép gộp có chi phí O(1), segment tree cơ bản cho:

| Công việc | Độ phức tạp điển hình |
|---|---|
| Xây dựng cây | O(n) |
| Tổng hợp một đoạn `[l,r)` | O(log n) |
| Gán/cộng một phần tử | O(log n) |
| Bộ nhớ lưu cây | O(n) |
| Chiều sâu cây cân bằng | O(log n) |

Bài này thuộc chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, trong lộ trình xây nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Ta đặc biệt chú trọng **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để biết khi nào chọn segment tree, thay vì chỉ ghi nhớ đoạn mã đệ quy.

Tâm điểm của bài là câu hỏi:

> **Một nút đại diện cho đoạn chỉ số nào, đoạn ấy được chia như thế nào, và tại sao chỉ cần một số ít nút để trả lời truy vấn?**

## 1. Bài toán và hợp đồng chỉ số

Cho mảng có `n` phần tử:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Ta thống nhất dùng **chỉ số 0-based** và **đoạn nửa mở `[l,r)`**:

```text
0 <= l <= r <= n
```

Đoạn `[l,r)` chứa những chỉ số:

```text
l, l+1, ..., r-1
```

và có độ dài đúng bằng `r-l`.

Với phép tổng:

```text
range_sum(l,r) = a[l] + ... + a[r-1]
```

Ví dụ:

```text
Chỉ số:    0  1  2  3  4  5  6  7
Giá trị:   5  2  6  3  1  7  4  8
```

| Truy vấn | Những phần tử được lấy | Tổng |
|---|---|---:|
| `[0,8)` | Cả tám phần tử | 36 |
| `[2,6)` | 6,3,1,7 | 17 |
| `[4,5)` | Chỉ 1 | 1 |
| `[1,3)` | 2,6 | 8 |
| `[8,8)` | Không có phần tử | 0 |

Đối với **truy vấn tổng**, bài chọn **tổng đoạn rỗng bằng 0**. Với **truy vấn min**, nếu không dùng phần tử đơn vị đặc biệt, thường cần quy định riêng rằng đoạn rỗng không hợp lệ. Quy ước chính xác phụ thuộc phép gộp và API.

Một số đề sử dụng đoạn **1-based đóng `[L,R]`**, tức lấy cả hai đầu. Ta quy đổi thành:

```text
[L,R] 1-based đóng  ->  [L-1,R) 0-based nửa mở
```

Chẳng hạn `[3,6]` 1-based tương ứng `[2,6)`, gồm bốn phần tử `a[2],a[3],a[4],a[5]`.

## 2. Tại sao phải chia miền chỉ số?

Nếu cần tổng của `[2,6)` trong mảng tám phần tử, cách trực tiếp phải cộng:

```text
6+3+1+7 = 17
```

Giả sử ta đã chuẩn bị sẵn:

```text
sum([2,4)) = 6+3 = 9
sum([4,6)) = 1+7 = 8
```

thì chỉ cần một lần gộp:

```text
sum([2,6)) = sum([2,4)) + sum([4,6))
            = 9 + 8 = 17
```

Đây là ý tưởng chung của segment tree: lưu kết quả của những **đoạn chuẩn** sinh ra bởi một quy tắc chia cố định. Khi một truy vấn đến, ta biểu diễn đoạn cần hỏi bằng một số ít đoạn chuẩn đã có kết quả.

Muốn cách đó hiệu quả, cây phải có hai đặc tính:

1. **Mỗi đoạn có thể chia thành hai đoạn con kề nhau, không trùng phần tử.**
2. **Hai kết quả của hai con có thể gộp lại để được kết quả của cha.**

Ta bắt đầu bằng quy tắc chia đoạn, chưa cần nghĩ tới mã cây.

## 3. Chia đoạn nửa mở [lo,hi) bằng mid

Một nút quản lý đoạn:

```text
[lo,hi)
```

Nếu đoạn có nhiều hơn một phần tử, đặt:

```text
mid = (lo + hi) // 2
```

Hai con quản lý:

```text
Con trái:  [lo,mid)
Con phải:  [mid,hi)
```

Các tính chất quan trọng:

- Hai đoạn **không giao nhau**, vì biên phải của con trái là exclusive.
- Hợp của hai đoạn **đúng bằng** `[lo,hi)`.
- Chúng giữ nguyên **thứ tự trái–phải** trong mảng.
- Khi `hi-lo>=2`, cả hai con đều **không rỗng**.
- Độ dài hai con chênh nhau nhiều nhất 1.

Ví dụ `[0,8)`:

```text
mid = (0+8)//2 = 4

[0,8)
  /   \
[0,4) [4,8)
```

Ví dụ đoạn có độ dài lẻ `[0,7)`:

```text
mid = (0+7)//2 = 3

[0,7)
  /   \
[0,3) [3,7)
```

Con trái có 3 phần tử, con phải có 4. Segment tree **không đòi hỏi n phải là lũy thừa của 2**.

### Tại sao dùng nửa mở?

Với đoạn nửa mở, phép chia viết gọn:

```text
[lo,hi) = [lo,mid) ∪ [mid,hi)
```

Không cần xử lý `mid+1` ở con phải. Nếu chọn đoạn đóng `[lo,hi]`, quy tắc tương ứng phải là `[lo,mid]` và `[mid+1,hi]`, cùng điều kiện dừng `lo==hi`.

**Hai quy ước đều có thể đúng, nhưng không được trộn chúng trong cùng một thuật toán.**

## 4. Lá cây và điều kiện dừng

Quá trình chia tiếp tục cho đến khi mỗi đoạn chỉ chứa **một phần tử**:

```text
hi - lo == 1
```

Nút đó là **lá**.

Ví dụ:

```text
[4,5)
```

chỉ chứa `a[4]`, nên kết quả tổng hợp của nút lá là chính `a[4]`.

Đối với segment tree đệ quy, không tiếp tục chia một lá. Nếu vẫn đặt `mid=(lo+hi)//2` với `hi-lo=1`, ta có `mid=lo` và đoạn trái `[lo,mid)` rỗng; nếu cứ đệ quy mà không dừng, thuật toán có thể lặp vô hạn.

### Khi n=0

Toàn mảng là `[0,0)`, một đoạn rỗng. Không tạo cây đệ quy có lá ở đây, vì không tồn tại phần tử nào để gán cho lá. Một triển khai nên:

- Cho phép khởi tạo cây rỗng.
- Trả đơn vị phù hợp khi truy vấn `[0,0)`.
- Từ chối cập nhật tại bất kỳ chỉ số điểm nào.

Đừng gọi hàm build đệ quy trên `[0,0)` nếu hàm chỉ biết dừng ở đoạn dài 1.

## 5. Toàn bộ phân chia cho n=8

Với tám phần tử, các đoạn chuẩn tạo thành cây cân đối:

```text
                         [0,8)
                    /              \
                [0,4)              [4,8)
               /     \            /     \
           [0,2)    [2,4)      [4,6)    [6,8)
           /   \     /   \      /   \     /   \
        [0,1)[1,2)[2,3)[3,4) [4,5)[5,6)[6,7)[7,8)
```

Ở mỗi tầng:

- Tầng 0 có đoạn dài 8.
- Tầng 1 có hai đoạn dài 4.
- Tầng 2 có bốn đoạn dài 2.
- Tầng 3 có tám đoạn dài 1.

Cây có **8 lá**, mỗi lá tương ứng đúng một vị trí của mảng. Các nút bên trong lưu kết quả tổng hợp của những lá thuộc đoạn chúng quản lý.

**Không có phép truy vấn nào phải đi tới tất cả tám lá nếu đoạn được phủ bởi một vài nút ở tầng trên.**

## 6. Phân chia khi n không phải lũy thừa 2

Đây là trường hợp dễ bị bỏ qua khi chỉ học ví dụ n=8.

Giả sử `n=7` và dữ liệu:

```text
a = [4, -1, 3, 0, 2, 5, -2]
```

Quy tắc `mid=(lo+hi)//2` sinh:

```text
                        [0,7)
                    /           \
                [0,3)          [3,7)
                /   \           /    \
             [0,1) [1,3)     [3,5)  [5,7)
                   /   \       / \    / \
                [1,2)[2,3) [3,4)[4,5)[5,6)[6,7)
```

Những đoạn như `[0,3)` không có độ dài là lũy thừa 2, nhưng vẫn được chia thành các đoạn nhỏ hơn hợp lệ.

Ta nhận thấy:

- Con trái và phải của một nút không nhất thiết bằng độ dài nhau.
- Mỗi phần tử vẫn có **một lá duy nhất**.
- Đường từ gốc đến một lá dài O(log n), vì mỗi lần chia gần như một nửa.

### Những đoạn chuẩn cho truy vấn [2,6)

Với cây n=7, đoạn `[2,6)` có thể được phủ bởi:

```text
[2,3) ∪ [3,5) ∪ [5,6)
```

Các đoạn **không giao nhau** và hợp lại đúng `[2,6)`.

Với mảng mẫu:

```text
sum([2,3)) = 3
sum([3,5)) = 0+2 = 2
sum([5,6)) = 5

3+2+5 = 10
```

Đây là lý do việc “phân chia miền chỉ số” quan trọng hơn việc thuộc một hình cây cụ thể: **n thay đổi thì hình cây thay đổi, nhưng bất biến phủ đoạn không đổi**.

## 7. Một nút lưu giá trị gì?

Segment tree không cố định chỉ dùng tổng. Mỗi nút lưu một giá trị tóm tắt `value` cho đoạn mà nó quản lý.

Ví dụ:

| Bài toán | Giá trị của nút | Cách gộp hai con |
|---|---|---|
| Tổng đoạn | Tổng các phần tử | `left + right` |
| Min đoạn | Giá trị nhỏ nhất | `min(left,right)` |
| Max đoạn | Giá trị lớn nhất | `max(left,right)` |
| XOR đoạn | XOR tất cả giá trị | `left ^ right` |
| GCD đoạn | Ước chung lớn nhất | `gcd(left,right)` |
| Nối chuỗi đoạn | Chuỗi đã nối theo thứ tự | `left + right` |
| Đếm số phần tử thỏa điều kiện cố định | Số lượng | `left_count + right_count` |

Điều kiện tối thiểu cho cách gộp từ hai con là **tính kết hợp**:

```text
combine(combine(x,y),z)
   = combine(x,combine(y,z))
```

Tính kết hợp cho phép đặt ngoặc theo hình cây khác mà không làm thay đổi kết quả.

### Phần tử đơn vị cho đoạn rỗng

Nhiều cách cài truy vấn cần một giá trị `identity` sao cho:

```text
combine(identity,x) = x
combine(x,identity) = x
```

Ví dụ:

- Tổng số: identity = 0.
- Nhân số: identity = 1.
- XOR: identity = 0.
- Min số thực mở rộng: identity = `+∞`.
- Max số thực mở rộng: identity = `-∞`.
- Nối chuỗi: identity = chuỗi rỗng `""`.

Một phép gộp **kết hợp + có phần tử đơn vị** tạo thành một *monoid*. Segment tree tổng quát thường được mô tả như một cấu trúc lưu kết quả của một monoid trên từng đoạn.

### Không nhất thiết phải giao hoán

Tính giao hoán là:

```text
combine(x,y) = combine(y,x)
```

Segment tree **không yêu cầu** điều này. Ví dụ nối chuỗi `"A"+"B"="AB"` khác `"BA"`, nhưng vẫn có thể lưu chuỗi trong cây nếu luôn gộp **con trái trước con phải**.

## 8. Bất biến quan trọng nhất của segment tree

Với mỗi nút `node` quản lý đoạn `[lo,hi)`, định nghĩa:

```text
tree[node] = aggregate(a[lo:hi])
```

Trong trường hợp tổng:

```text
tree[node] = sum(a[lo:hi])
```

Đây là **bất biến của mọi nút**.

Với nút lá `hi-lo=1`:

```text
tree[node] = a[lo]
```

Với nút trong, chia `mid=(lo+hi)//2`:

```text
tree[node] = combine(
    tree[left_child],
    tree[right_child]
)
```

Bởi vì:

```text
[lo,hi) = [lo,mid) ∪ [mid,hi)
```

và hai đoạn con không giao nhau, ghép kết quả của chúng theo đúng thứ tự cho ra kết quả đoạn cha.

**Nếu gán một phần tử nhưng không tính lại các nút tổ tiên, bất biến này bị phá.** Truy vấn đầy đủ đoạn cha sau đó sẽ trả kết quả cũ.

## 9. Tính tổng từ lá lên gốc: ví dụ n=8

Lấy dữ liệu:

```text
a = [5,2,6,3,1,7,4,8]
```

Ở mức lá, các giá trị là:

```text
[0,1)=5, [1,2)=2, [2,3)=6, [3,4)=3
[4,5)=1, [5,6)=7, [6,7)=4, [7,8)=8
```

Gộp cặp lá:

```text
[0,2) = 5+2 = 7
[2,4) = 6+3 = 9
[4,6) = 1+7 = 8
[6,8) = 4+8 = 12
```

Gộp tiếp:

```text
[0,4) = 7+9 = 16
[4,8) = 8+12 = 20
```

Gốc:

```text
[0,8) = 16+20 = 36
```

Sơ đồ mang cả khoảng và tổng:

```text
                              [0,8):36
                          /                 \
                   [0,4):16                [4,8):20
                   /      \                /      \
              [0,2):7  [2,4):9        [4,6):8   [6,8):12
               /   \     /   \          /   \       /   \
              5     2   6     3        1     7     4     8
```

Nếu hỏi tổng toàn mảng, chỉ cần đọc gốc `36` — **O(1) công việc truy vấn sau khi cây được xây** cho trường hợp cụ thể đó.

## 10. Xây dựng bằng đệ quy: chia rồi gộp

Thuật toán xây một nút `node` cho `[lo,hi)`:

1. Nếu đoạn chỉ có một phần tử, gán giá trị của lá.
2. Ngược lại, tính `mid`.
3. Xây cây con trái trên `[lo,mid)`.
4. Xây cây con phải trên `[mid,hi)`.
5. Gộp hai con để tính giá trị nút hiện tại.

Giả mã:

```text
BUILD(node, lo, hi):
    if hi-lo == 1:
        tree[node] = a[lo]
        return

    mid = (lo+hi)//2

    BUILD(2*node, lo, mid)
    BUILD(2*node+1, mid, hi)

    tree[node] = combine(
        tree[2*node],
        tree[2*node+1]
    )
```

Lưu ý:

- **Đầu vào build phải không rỗng.**
- `node` là **vị trí lưu trong mảng cây**, khác với `lo/hi` là **chỉ số trong mảng dữ liệu**.
- Nhánh trái lưu ở `2*node`, nhánh phải ở `2*node+1` nếu gốc nằm ở vị trí 1.
- Trong các bản cài khác, cách đánh số nút có thể thay đổi, nhưng **đoạn mà nút quản lý** vẫn là khái niệm cốt lõi.

## 11. Hai kiểu biểu diễn segment tree trong mảng

Có hai cách rất phổ biến; chúng giữ cùng bất biến nhưng khác hình thức lưu.

### 11.1. Đệ quy, gốc tại 1, cấp phát khoảng 4n

Dùng:

```text
root=1
left_child(node)=2*node
right_child(node)=2*node+1
```

Hàm build chia đoạn thật `[0,n)` theo `mid` cho đến từng phần tử, kể cả n không là lũy thừa 2.

Để mã đơn giản, thường cấp phát một mảng cỡ **4n** (hoặc `4n+1` nếu giữ chỉ số 0 không dùng). Đây là **cận đủ thông dụng** cho cách đánh số nút như trên, không có nghĩa chính xác 4n nút đều được sử dụng.

Với n=0, dùng mảng tối thiểu và **không gọi build**.

### 11.2. Lặp, đệm lá đến lũy thừa 2 P

Lấy:

```text
P = lũy thừa 2 nhỏ nhất >= n
```

Với n=0, có thể quy ước `P=1` để mảng cây có kích thước hợp lệ.

Ta lưu:

```text
tree[P] ... tree[P+n-1] = a[0] ... a[n-1]
```

Những lá còn lại từ `P+n` đến `2P-1` là **padding** và nhận phần tử đơn vị của phép gộp. Các nút bên trong được gộp từ dưới lên:

```text
tree[v] = combine(tree[2v],tree[2v+1])
```

Có `2P` ô đánh số từ 0 đến `2P-1`, trong đó nút 0 không dùng; nút gốc là 1.

### So sánh hai biểu diễn

| Đặc điểm | Đệ quy 4n | Lặp 2P |
|---|---|---|
| Mảng đầu vào dài không là lũy thừa 2 | Chia đoạn thật không đều | Đệm thêm lá đơn vị |
| Biên đoạn của nút | Truyền `lo,hi` khi đệ quy | Suy từ vị trí trong cây hoàn chỉnh |
| Cập nhật điểm | Đi theo đường root→leaf | Sửa lá rồi đi ngược cha |
| Truy vấn | Ba trường hợp phủ/không phủ/giao | Hai con trỏ biên đi lên |
| Bộ nhớ | O(n) với khoảng 4n ô | O(n), vì `P<2n` khi n>0 |
| Thuận lợi giảng giải miền chỉ số | Rất trực quan | Ngắn gọn, thường ít đệ quy |

Bài sẽ triển khai **cả hai** để thấy sự tương ứng của các vùng chỉ số và bảo đảm không phụ thuộc một cách cài duy nhất.

## 12. Vì sao cây chỉ có O(n) nút?

Với `n>=1`, nếu xây cây nhị phân đầy đủ theo nghĩa **mỗi nút trong có đúng hai con** và mỗi lá là một phần tử, ta có:

```text
Số lá = n
Số nút trong = n-1
Tổng số nút thật = 2n-1
```

Đây là đếm **nút logic**, không phải số ô của mảng `4n` đã cấp phát (vốn có thể chứa các vị trí chưa dùng).

Trong biểu diễn lặp, có `P` lá kể cả padding. Toàn cây đầy đủ có `2P-1` nút logic. Vì `P` là lũy thừa 2 nhỏ nhất không dưới n:

```text
n <= P < 2n       với n>=1
```

nên:

```text
2P < 4n
```

và bộ nhớ cũng là **O(n)**.

**Tên “cây” không buộc phải dùng đối tượng nút và con trỏ**. Cách lưu bằng mảng thường đủ để tận dụng quan hệ cha–con, đồng thời tránh chi phí phân bổ hàng loạt đối tượng nhỏ.

## 13. Truy vấn đoạn đệ quy: ba quan hệ giữa hai đoạn

Giả sử nút hiện tại quản lý `[lo,hi)` và cần hỏi `[ql,qr)`.

Có ba tình huống:

### Tình huống A — Không giao nhau

Nếu:

```text
qr <= lo    hoặc    hi <= ql
```

thì nút không đóng góp phần tử nào. Với truy vấn tổng, trả **0**.

Ví dụ nút `[0,2)` và truy vấn `[3,6)` không giao nhau.

### Tình huống B — Nằm hoàn toàn bên trong truy vấn

Nếu:

```text
ql <= lo    và    hi <= qr
```

thì toàn bộ đoạn nút được lấy. Trả ngay:

```text
tree[node]
```

**Không đệ quy xuống các lá bên dưới**, vì kết quả đã được lưu.

Ví dụ nút `[2,4)` nằm gọn trong truy vấn `[2,6)`.

### Tình huống C — Giao nhau một phần

Nếu không thuộc hai tình huống trên, ta phải tách:

```text
mid = (lo+hi)//2
```

Truy vấn con trái và con phải, sau đó gộp hai kết quả theo đúng thứ tự.

Giả mã cho tổng:

```text
QUERY(node, lo, hi, ql, qr):
    if qr <= lo or hi <= ql:
        return 0

    if ql <= lo and hi <= qr:
        return tree[node]

    mid = (lo+hi)//2

    left_answer  = QUERY(2*node, lo, mid, ql, qr)
    right_answer = QUERY(2*node+1, mid, hi, ql, qr)

    return left_answer + right_answer
```

Các điều kiện này phải nhất quán với `[l,r)`; nếu đổi nhầm `<=` thành `<` ở quan hệ không giao nhau, ta có thể lãng phí truy cập hoặc sai biên.

## 14. Truy vết truy vấn [2,6) trên cây n=8

Cây tổng của `a=[5,2,6,3,1,7,4,8]` có gốc `[0,8)=36`.

Truy vấn `[2,6)`:

1. Gốc `[0,8)` giao một phần, tách thành `[0,4)` và `[4,8)`.
2. `[0,4)` giao một phần, tách `[0,2)` và `[2,4)`.
3. `[0,2)` **không giao** → góp 0.
4. `[2,4)` **nằm trọn trong truy vấn** → góp giá trị lưu là 9.
5. `[4,8)` giao một phần, tách `[4,6)` và `[6,8)`.
6. `[4,6)` nằm trọn → góp 8.
7. `[6,8)` không giao → góp 0.

Kết quả:

```text
0 + 9 + 8 + 0 = 17
```

Hai nút hữu ích:

```text
[2,4) -> 6+3 = 9
[4,6) -> 1+7 = 8

[2,6) = [2,4) ∪ [4,6)
Tổng = 9+8 = 17
```

Nếu thay tổng bằng phép nối chuỗi, ta vẫn phải ghép kết quả **theo thứ tự các đoạn**; không đảo 8 lên trước 9 chỉ vì nhánh phải được duyệt nhanh hơn.

## 15. Đoạn phủ chuẩn và tại sao không đếm trùng

Những nút **nằm hoàn toàn trong truy vấn** được chọn để đóng góp giá trị của chúng. Tập các đoạn do những nút ấy quản lý gọi là một **phân hoạch theo các đoạn chuẩn** (*canonical cover*) của truy vấn.

Nó thỏa:

1. Mỗi đoạn được chọn nằm trọn trong `[ql,qr)`.
2. Hai đoạn được chọn **không chồng lấn**.
3. Hợp của các đoạn được chọn bằng đúng `[ql,qr)`.
4. Các đoạn được gộp theo thứ tự chỉ số tăng.

Ví dụ n=8:

```text
[2,6) = [2,4) ∪ [4,6)
```

Ví dụ n=7:

```text
[2,6) = [2,3) ∪ [3,5) ∪ [5,6)
```

Khác với truy vấn hai khối **có thể chồng lấn** của sparse table dành cho min/max, segment tree chuẩn xây đáp án bằng **những đoạn rời nhau**. Vì thế, phép gộp **không cần tính lũy đẳng**; tính kết hợp cùng phần tử đơn vị cho nhánh rỗng là đủ.

## 16. Vì sao truy vấn tốn O(log n), không phải O(n)?

Cây có chiều cao:

```text
h = O(log n)
```

vì mỗi lần chia gần một nửa độ dài đoạn.

Đối với một truy vấn liên tiếp, tại mỗi độ sâu:

- Các nút nằm trọn trong truy vấn có thể được lấy kết quả **ngay tại đó**.
- Chỉ những nút nằm ở **hai mép trái và phải của khoảng hỏi** mới cần chia tiếp.
- Do truy vấn là một đoạn liên tục, có tối đa **hai nút giao một phần** ở mỗi độ sâu.

Các nút “chạm biên” tạo thành nhiều nhất hai đường theo chiều cao cây; những nút được chọn trọn vẹn xuất hiện dọc hai mép đó.

Do vậy số nút được thăm và số phép gộp được chặn bởi **O(log n)**, không tỷ lệ với số phần tử `r-l`.

### Đừng suy luận sai từ hai lời gọi đệ quy

Giả mã có hai dòng:

```text
QUERY(left)
QUERY(right)
```

nhưng **không có nghĩa mỗi truy vấn thăm toàn bộ 2^h lá**. Rất nhiều nhánh dừng ngay vì **không giao** hoặc **nằm trọn** trong truy vấn. Đó chính là công dụng của việc lưu trước giá trị tổng hợp ở các nút.

### Chi phí theo phép gộp

Cận O(log n) giả định mỗi lần `combine` tốn O(1). Với chuỗi Python, nối hai chuỗi có thể phải sao chép nhiều ký tự. Khi đó tổng chi phí thực tế còn phụ thuộc **kích thước của giá trị tóm tắt**, dù số nút đi qua vẫn O(log n).

## 17. Cập nhật một điểm: chỉ một nhánh ở mỗi tầng

Muốn gán:

```text
a[pos] = new_value
```

ta tìm lá quản lý `[pos,pos+1)`, sửa giá trị lá, sau đó gộp lại các nút tổ tiên.

Với nút `[lo,hi)` có `mid=(lo+hi)//2`:

- Nếu `pos < mid`: đi xuống con trái.
- Nếu `pos >= mid`: đi xuống con phải.

Không bao giờ cần cập nhật **cả hai** nhánh cho một điểm.

### Giả mã

```text
ASSIGN(node, lo, hi, pos, new_value):
    if hi-lo == 1:
        tree[node] = new_value
        return

    mid = (lo+hi)//2

    if pos < mid:
        ASSIGN(2*node, lo, mid, pos, new_value)
    else:
        ASSIGN(2*node+1, mid, hi, pos, new_value)

    tree[node] = combine(
        tree[2*node],
        tree[2*node+1]
    )
```

Mỗi tầng chỉ thăm **một** nút trên đường xuống rồi gộp lại khi quay lên. Chi phí:

```text
O(log n)
```

### Cộng một điểm

Với tổng:

```text
a[pos] += delta
```

có thể đọc giá trị cũ rồi gọi phép gán:

```text
ASSIGN(pos, old_value+delta)
```

Nếu giữ một bản sao `a`, đọc cũ trong O(1); chi phí chính vẫn O(log n). Nếu chỉ giữ cây, có thể hỏi điểm trong O(log n), rồi gán; tổng cũng vẫn O(log n).

## 18. Truy vết cập nhật vị trí 4 trên n=8

Với:

```text
a = [5,2,6,3,1,7,4,8]
```

gán `a[4]` từ 1 thành 10.

Đường đi xuống:

```text
[0,8) -> [4,8) -> [4,6) -> [4,5)
```

Sửa lá `[4,5)` thành 10; các tổng thay đổi theo chiều ngược:

```text
[4,5):  1 -> 10
[4,6):  1+7 = 8 -> 10+7 = 17
[4,8):  8+12 = 20 -> 17+12 = 29
[0,8): 16+20 = 36 -> 16+29 = 45
```

Những đoạn **không chứa chỉ số 4** giữ nguyên: `[0,4)=16`, `[6,8)=12`, `[2,4)=9`, v.v.

Truy vấn `[2,6)` sau cập nhật:

```text
[2,4) = 9
[4,6) = 17
=> 9+17 = 26
```

Giá trị cũ 17 tăng thành 26 đúng bằng `delta=9` vì vị trí 4 nằm trong đoạn hỏi.

## 19. Python hoàn chỉnh: segment tree tổng dùng đệ quy

Lớp dưới đây dùng API công khai **0-based, [l,r)** và chia thật `[0,n)` bằng `mid`. Giá trị là **số nguyên** để hành vi cộng/trừ rõ ràng; với số thực cần thêm chính sách về sai số.

```python
class RecursiveSegmentTreeSum:
    """Cây đoạn tổng, gốc ở tree[1], API 0-based [l,r)."""

    def __init__(self, values):
        self.values = list(values)

        if any(type(x) is not int for x in self.values):
            raise TypeError("Ví dụ này chỉ nhận số nguyên")

        self.n = len(self.values)
        self.tree = [0] * (4 * self.n + 1)

        if self.n > 0:
            self._build(1, 0, self.n)

    def _build(self, node, lo, hi):
        if hi - lo == 1:
            self.tree[node] = self.values[lo]
            return

        mid = (lo + hi) // 2
        self._build(2 * node, lo, mid)
        self._build(2 * node + 1, mid, hi)

        self.tree[node] = (
            self.tree[2 * node] + self.tree[2 * node + 1]
        )

    def _check_range(self, l, r):
        if type(l) is not int or type(r) is not int:
            raise TypeError("l và r phải là số nguyên")
        if not 0 <= l <= r <= self.n:
            raise IndexError("Đoạn [l,r) không hợp lệ")

    def _check_pos(self, pos):
        if type(pos) is not int:
            raise TypeError("pos phải là số nguyên")
        if not 0 <= pos < self.n:
            raise IndexError("pos nằm ngoài mảng")

    def range_sum(self, l, r):
        self._check_range(l, r)

        if l == r:
            return 0

        return self._query(1, 0, self.n, l, r)

    def _query(self, node, lo, hi, ql, qr):
        # Không giao nhau.
        if qr <= lo or hi <= ql:
            return 0

        # Đoạn nút nằm trọn trong đoạn hỏi.
        if ql <= lo and hi <= qr:
            return self.tree[node]

        # Giao nhau một phần: chia tiếp.
        mid = (lo + hi) // 2

        left_answer = self._query(
            2 * node, lo, mid, ql, qr
        )
        right_answer = self._query(
            2 * node + 1, mid, hi, ql, qr
        )

        return left_answer + right_answer

    def point_assign(self, pos, value):
        self._check_pos(pos)
        if type(value) is not int:
            raise TypeError("Giá trị gán phải là số nguyên")

        self.values[pos] = value
        self._assign(1, 0, self.n, pos, value)

    def _assign(self, node, lo, hi, pos, value):
        if hi - lo == 1:
            self.tree[node] = value
            return

        mid = (lo + hi) // 2

        if pos < mid:
            self._assign(2 * node, lo, mid, pos, value)
        else:
            self._assign(2 * node + 1, mid, hi, pos, value)

        self.tree[node] = (
            self.tree[2 * node] + self.tree[2 * node + 1]
        )

    def point_add(self, pos, delta):
        self._check_pos(pos)
        if type(delta) is not int:
            raise TypeError("delta phải là số nguyên")

        self.point_assign(pos, self.values[pos] + delta)

    def point_get(self, pos):
        self._check_pos(pos)
        return self.values[pos]
```

### Kiểm thử xây và các đoạn

```python
a = [5, 2, 6, 3, 1, 7, 4, 8]
seg = RecursiveSegmentTreeSum(a)

assert seg.tree[1] == 36
assert seg.tree[2] == 16
assert seg.tree[3] == 20
assert seg.tree[4] == 7
assert seg.tree[5] == 9
assert seg.tree[6] == 8
assert seg.tree[7] == 12

assert seg.range_sum(0, 8) == 36
assert seg.range_sum(2, 6) == 17
assert seg.range_sum(4, 5) == 1
assert seg.range_sum(1, 3) == 8
assert seg.range_sum(8, 8) == 0
```

### Kiểm thử cập nhật

```python
seg.point_assign(4, 10)

assert seg.point_get(4) == 10
assert seg.tree[6] == 17
assert seg.tree[3] == 29
assert seg.tree[1] == 45
assert seg.range_sum(2, 6) == 26

seg.point_add(1, -5)

assert seg.values == [5, -3, 6, 3, 10, 7, 4, 8]
assert seg.tree[1] == 40
assert seg.range_sum(1, 3) == 3

# Danh sách ngoài không bị sửa.
assert a == [5, 2, 6, 3, 1, 7, 4, 8]
```

### Kiểm thử mảng dài lẻ

```python
odd = RecursiveSegmentTreeSum([4, -1, 3, 0, 2, 5, -2])

assert odd.tree[1] == 11
assert odd.range_sum(2, 6) == 10
assert odd.range_sum(0, 3) == 6
assert odd.range_sum(3, 7) == 5

odd.point_add(6, 2)

assert odd.values == [4, -1, 3, 0, 2, 5, 0]
assert odd.range_sum(0, 7) == 13
```

**Lưu ý:** mã chỉ sửa tệp bài học; ví dụ Python được đưa vào để người học chạy thử, không phải tuyên bố đã thực thi chúng trong bước biên soạn.

## 20. Chứng minh tính đúng của bước xây

Ta chứng minh bất biến:

> Với mọi nút `node` quản lý `[lo,hi)`, `tree[node]` bằng tổng đúng của các phần tử `a[lo:hi]`.

### Cơ sở: nút lá

Nếu `hi-lo=1`:

```text
tree[node] = a[lo]
```

Đúng vì đoạn chỉ có phần tử `a[lo]`.

### Bước quy nạp: nút bên trong

Giả sử hai nút con đã được xây đúng:

```text
tree[left]  = sum(a[lo:mid])
tree[right] = sum(a[mid:hi])
```

Hai đoạn con kề nhau, không giao nhau và hợp thành đoạn cha. Vì thế:

```text
tree[node]
 = tree[left] + tree[right]
 = sum(a[lo:mid]) + sum(a[mid:hi])
 = sum(a[lo:hi])
```

Bất biến đúng ở cha. Theo quy nạp từ lá lên gốc, mọi nút được xây đúng.

Lập luận này còn đúng nếu thay cộng bằng một phép **kết hợp** và gộp hai đoạn **theo đúng thứ tự trái–phải**.

## 21. Chứng minh truy vấn trả đúng kết quả

Với truy vấn `Q=[ql,qr)` và nút quản lý `S=[lo,hi)`:

### Không giao nhau

`Q∩S=∅`, không có phần tử nào của nút thuộc truy vấn. Trả phần tử đơn vị 0 là đúng cho tổng.

### Phủ hoàn toàn

Nếu `S⊆Q`, bất biến xây đã bảo đảm `tree[node]=sum(a[lo:hi])`. Ta trả ngay giá trị đã lưu, không bỏ sót phần tử.

### Phủ một phần

Chia `S` thành hai đoạn không giao nhau:

```text
S_left=[lo,mid)
S_right=[mid,hi)
```

Theo giả thiết quy nạp trên các đoạn nhỏ hơn, hai lời gọi con trả tổng đúng của phần truy vấn nằm trong mỗi con. Cộng hai kết quả cho ra tổng đúng của phần truy vấn nằm trong cả `S`.

Với gốc `S=[0,n)`, do mọi truy vấn hợp lệ nằm trong gốc, kết quả là tổng của đúng `[ql,qr)`.

**Điều quan trọng:** nhánh nằm trọn không cần đi tiếp; nhánh không giao dùng đơn vị; nhánh giao một phần phải gộp cả hai theo đúng thứ tự.

## 22. Chứng minh cập nhật bảo toàn bất biến

Giả sử trước khi cập nhật mọi nút lưu tổng đúng.

Gán giá trị mới cho phần tử `a[pos]`:

1. Đi từ gốc xuống **duy nhất một lá** quản lý `[pos,pos+1)`.
2. Sửa giá trị lá thành `new_value`, vì tổng một phần tử bằng chính phần tử ấy.
3. Khi trở lên, tính lại mỗi tổ tiên bằng tổng hai con.

Các nút **không nằm trên đường gốc–lá** không quản lý phần tử pos, nên giá trị của chúng vẫn đúng và không cần thay đổi.

Mỗi tổ tiên sau khi gộp hai con mới vẫn đúng theo chứng minh bước xây.

Vì vậy, sau khi cập nhật, bất biến của **toàn bộ cây** được khôi phục. Tất cả truy vấn sau đó tiếp tục đúng với trạng thái dữ liệu mới.

### Vì sao chỉ một đường?

Tại mỗi nút trong, con trái quản lý `[lo,mid)` và con phải quản lý `[mid,hi)`. Một chỉ số `pos` không thể đồng thời thuộc cả hai vì chúng không giao nhau. Vì vậy mỗi tầng có chính xác một nhánh chứa pos.

## 23. Độ sâu O(log n) và chi phí xây O(n)

Mỗi lần chia đoạn `[lo,hi)`, độ dài hai con xấp xỉ bằng một nửa:

```text
floor(length/2) và ceil(length/2)
```

Sau khoảng `ceil(log2 n)` lần chia, độ dài còn 1. Chiều cao là O(log n).

Đối với `n>=1`, cây có n lá, n−1 nút trong nên tổng `2n−1` nút thật. Trong quá trình xây:

- Mỗi lá nhận đúng một giá trị.
- Mỗi nút trong gộp đúng một lần.
- Mỗi nút được xử lý một số hằng định thao tác.

Do đó **thời gian xây O(n)** với phép gộp O(1).

Với kiểu lưu `4n+1`:

```text
Bộ nhớ mảng cây: O(n)
Bản sao values:  O(n)
Ngăn xếp đệ quy: O(log n)
```

Tổng O(n). Ngăn xếp đệ quy tốn O(log n) **bộ nhớ phụ khi xây/truy vấn/cập nhật**, ngoài các mảng đã được giữ lâu dài.

### Có phải mọi query luôn O(log n) đúng bằng số tầng?

Không. Truy vấn toàn mảng có thể trả ngay ở gốc. Truy vấn đoạn rỗng trả đơn vị tức thì. Một truy vấn bất kỳ có cận O(log n), nhưng số nút thăm thực tế phụ thuộc vị trí biên và hình dạng đoạn.

## 24. Cây đoạn lặp với số lá đệm đến P

Cách đệ quy thể hiện rất rõ miền chỉ số. Một cách cài khác sử dụng một cây nhị phân hoàn chỉnh với số lá `P` là lũy thừa 2.

Ví dụ `n=5`:

```text
a = [4, 2, 7, 1, 3]
P = 8
```

Ta đặt các giá trị ở tám lá:

```text
[4,2,7,1,3,0,0,0]
```

Ba số 0 cuối là **lá đệm** cho phép tổng. Chúng không phải các phần tử hợp lệ của mảng thật, nên không được nhận truy vấn cập nhật tại pos từ 5 đến 7.

Với phép min, padding dùng `+∞`, không được luôn đặt 0, vì 0 có thể làm min sai.

### Sơ đồ vị trí trong mảng cây

```text
tree[1]       root
tree[2:4]     hai con gốc
tree[4:8]     bốn nút mức tiếp
tree[8:16]    tám lá

tree[8]  = a[0]
tree[9]  = a[1]
tree[10] = a[2]
tree[11] = a[3]
tree[12] = a[4]
tree[13] = identity
tree[14] = identity
tree[15] = identity
```

Build:

```text
for i=0..n-1:
    tree[P+i]=a[i]

for node=P-1 down to 1:
    tree[node] = combine(
        tree[2*node], tree[2*node+1]
    )
```

Thời gian O(P)=O(n); bộ nhớ O(2P)=O(n).

### Biên truy vấn lặp

Để hỏi `[l,r)`, đổi hai biên sang mức lá:

```text
L = l + P
R = r + P
```

Trong khi `L<R`, ta chọn những nút **nằm trọn** trong phần đoạn chưa xử lý, rồi chuyển L và R lên cha.

Nếu L là con phải (L lẻ), nút L được lấy và L tăng lên. Nếu R là biên sau một con trái (R lẻ), giảm R trước rồi lấy nút R. Sau đó cả hai được chia đôi.

Do phương thức này xử lý từ **hai phía** của đoạn, với phép gộp không giao hoán phải giữ hai biến kết quả trái/phải để bảo đảm thứ tự.

## 25. Python: segment tree lặp cho phép gộp kết hợp

Cài đặt này tổng quát hơn một cây chỉ cộng số. Nó nhận:

- `combine(x,y)`: phép gộp kết hợp, giữ thứ tự.
- `identity`: phần tử đơn vị hai phía.
- `values`: dãy đầu vào.

Người gọi có trách nhiệm bảo đảm phép gộp thực sự **kết hợp** và `identity` phù hợp. Mã không thể tự chứng minh các tính chất của một hàm tùy ý.

```python
class MonoidSegmentTree:
    """Segment tree lặp, query [l,r) theo đúng thứ tự trái -> phải."""

    def __init__(self, values, combine, identity):
        values = list(values)

        self.n = len(values)
        self.combine = combine
        self.identity = identity

        self.size = 1
        while self.size < self.n:
            self.size *= 2

        self.tree = [identity] * (2 * self.size)

        for i, value in enumerate(values):
            self.tree[self.size + i] = value

        for node in range(self.size - 1, 0, -1):
            self.tree[node] = self.combine(
                self.tree[2 * node],
                self.tree[2 * node + 1],
            )

    def _check_range(self, l, r):
        if type(l) is not int or type(r) is not int:
            raise TypeError("l và r phải là số nguyên")
        if not 0 <= l <= r <= self.n:
            raise IndexError("Đoạn [l,r) không hợp lệ")

    def _check_pos(self, pos):
        if type(pos) is not int:
            raise TypeError("pos phải là số nguyên")
        if not 0 <= pos < self.n:
            raise IndexError("pos nằm ngoài mảng")

    def point_assign(self, pos, value):
        self._check_pos(pos)

        node = self.size + pos
        self.tree[node] = value

        node //= 2
        while node:
            self.tree[node] = self.combine(
                self.tree[2 * node],
                self.tree[2 * node + 1],
            )
            node //= 2

    def point_get(self, pos):
        self._check_pos(pos)
        return self.tree[self.size + pos]

    def query(self, l, r):
        self._check_range(l, r)

        left_answer = self.identity
        right_answer = self.identity

        L = l + self.size
        R = r + self.size

        while L < R:
            if L & 1:
                left_answer = self.combine(
                    left_answer, self.tree[L]
                )
                L += 1

            if R & 1:
                R -= 1
                right_answer = self.combine(
                    self.tree[R], right_answer
                )

            L //= 2
            R //= 2

        return self.combine(left_answer, right_answer)
```

### Dùng cho tổng

```python
values = [5, 2, 6, 3, 1, 7, 4, 8]
seg_sum = MonoidSegmentTree(values, lambda a, b: a + b, 0)

assert seg_sum.query(0, 8) == 36
assert seg_sum.query(2, 6) == 17
assert seg_sum.query(4, 5) == 1
assert seg_sum.query(8, 8) == 0

seg_sum.point_assign(4, 10)

assert seg_sum.query(2, 6) == 26
assert seg_sum.query(0, 8) == 45
```

### Dùng cho min

```python
from math import inf

values = [5, 2, 6, 3, 1, 7, 4, 8]
seg_min = MonoidSegmentTree(values, min, inf)

assert seg_min.query(0, 8) == 1
assert seg_min.query(2, 4) == 3
assert seg_min.query(5, 8) == 4
assert seg_min.query(0, 0) == inf

seg_min.point_assign(4, 10)

assert seg_min.query(2, 6) == 3
```

Ở đây min trên đoạn rỗng trả `inf` theo phần tử đơn vị, không phải “phần tử nhỏ nhất của tập rỗng” theo nghĩa thông thường. Một API có thể thay bằng kiểm tra và báo lỗi nếu muốn.

### Dùng cho ghép chuỗi không giao hoán

```python
words = ["A", "B", "C", "D", "E"]
seg_words = MonoidSegmentTree(words, lambda a, b: a + b, "")

assert seg_words.query(0, 5) == "ABCDE"
assert seg_words.query(1, 4) == "BCD"
assert seg_words.query(1, 5) == "BCDE"
assert seg_words.query(2, 2) == ""

seg_words.point_assign(2, "X")
assert seg_words.query(1, 4) == "BXD"
```

Nếu vô tình gộp kết quả bên phải trước bên trái, phép cộng số vẫn có thể qua test nhờ tính giao hoán, nhưng test chuỗi sẽ **phát hiện lỗi thứ tự**.

## 26. Vì sao cần hai biến left_answer và right_answer?

Trong truy vấn lặp, ta thu nhặt những nút trọn vẹn từ **hai đầu**:

- `left_answer` tích lũy các khối lấy từ **bên trái sang phải**.
- `right_answer` tích lũy các khối lấy từ **bên phải sang trái**, nhưng cần **ghép khối mới vào trước** kết quả đã có.
- Kết thúc, đáp án là `combine(left_answer,right_answer)`.

Công thức:

```text
left_answer  = combine(left_answer, tree[L])

right_answer = combine(tree[R], right_answer)
```

Phép gộp thứ hai có thứ tự **ngược chiều cập nhật** so với dòng đầu. Nếu viết:

```text
right_answer = combine(right_answer, tree[R])
```

thì có thể đảo thứ tự những khối đã thu từ bên phải.

### Truy vết với chuỗi [1,5)

Với:

```text
values = ["A","B","C","D","E"]
n=5, size=8

query [1,5)
L=1+8=9
R=5+8=13
```

Bước đầu:

- `L=9` lẻ: lấy nút 9 tương ứng `[1,2)`, ghép `"B"` vào trái, tăng L thành 10.
- `R=13` lẻ: giảm R thành 12, lấy nút 12 tương ứng `[4,5)`, ghép `"E"` vào **đầu** của kết quả phải.
- Chia L và R cho 2: `L=5,R=6`.

Bước sau:

- `L=5` lẻ: lấy nút 5 tương ứng `[2,4)`, gộp `"CD"` vào cuối kết quả trái.
- Tăng L thành 6, L=R nên dừng.

Kết quả:

```text
left_answer  = "BCD"
right_answer = "E"

answer = "BCD" + "E" = "BCDE"
```

Các đoạn được lấy là `[1,2)`, `[2,4)` và `[4,5)`: chúng kề nhau, không giao nhau, phủ đúng `[1,5)`.

## 27. Bất biến của truy vấn lặp

Với truy vấn gốc `[l,r)`, khi hai con trỏ `L,R` tiến dần lên, ta giữ ý nghĩa:

> Những khối đã gộp vào `left_answer`, rồi những khối chưa xử lý giữa L và R, rồi những khối đã gộp vào `right_answer`, theo thứ tự trái–phải, tạo thành đúng toàn bộ truy vấn ban đầu.

Khi `L` là con phải, khối ở `L` nằm sát **biên trái** của phần chưa xử lý. Ta lấy khối ấy, gộp vào bên trái rồi tăng L để bỏ khối vừa lấy.

Khi `R` lẻ, nút `R-1` nằm sát **biên phải** của phần chưa xử lý. Ta giảm R, lấy khối ấy và gộp **ở đầu** của kết quả bên phải.

Sau khi đã xử lý hai mép, L và R nằm đúng ranh giới các khối ở tầng cha, nên có thể chia hai chỉ số cho 2.

Khi `L>=R`, không còn khối nào chưa xử lý. Gộp `left_answer` và `right_answer` cho ra kết quả truy vấn đúng.

Đây là cùng ý tưởng **phủ bởi các đoạn chuẩn rời nhau** như bản đệ quy, chỉ khác cách duyệt.

## 28. Cập nhật trên cây lặp

Với mảng lá bắt đầu ở `size=P`, phần tử ngoài `pos` nằm ở:

```text
node = P + pos
```

Gán trực tiếp:

```text
tree[node] = new_value
```

Sau đó liên tục đi lên:

```text
node //= 2
tree[node] = combine(tree[2*node],tree[2*node+1])
```

cho đến khi `node=0`.

Ví dụ `n=5,P=8`, cập nhật `pos=4`:

```text
Vị trí lá: 8+4 = 12
Đường đi cha: 12 -> 6 -> 3 -> 1
```

Có O(log P)=O(log n) mức. Các lá padding giữ nguyên phần tử đơn vị, nên không ảnh hưởng những tổng hợp hợp lệ.

### Khi n không phải lũy thừa 2

Không được quên kiểm tra `pos<n`. Với `n=5,P=8`, những vị trí từ 5 đến 7 là **padding**, không thuộc mảng logic.

Nếu cho phép cập nhật `pos=6`, cây vẫn có một lá vật lý nhận được giá trị mới, nhưng kết quả của gốc sẽ không còn chỉ mô tả mảng n=5. Vì vậy lớp `MonoidSegmentTree` từ chối mọi chỉ số điểm ngoài `[0,n)`.

## 29. Nút nào thực sự chứa đoạn nào trong cây lặp?

Cây lặp đầy đủ có `P=2^h` lá. Với gốc `node=1`:

- Nút 1 quản lý `[0,P)`.
- Hai nút 2 và 3 quản lý `[0,P/2)` và `[P/2,P)`.
- Nút `P+i` quản lý một phần tử `[i,i+1)`.

Ở độ sâu `d` tính từ gốc, mỗi nút quản lý đoạn dài:

```text
P / 2^d
```

Cụ thể, nếu:

```text
first = 2^d
offset = node - first
width = P / 2^d
```

thì nút có phạm vi:

```text
[offset*width, (offset+1)*width)
```

cho tới P, kể cả padding.

### Ví dụ P=8

| Nút | Đoạn mà nó quản lý | Ghi chú |
|---:|---|---|
| 1 | `[0,8)` | Gốc |
| 2 | `[0,4)` | Trái |
| 3 | `[4,8)` | Phải |
| 4 | `[0,2)` | Hai phần tử đầu |
| 5 | `[2,4)` | Hai phần tử tiếp |
| 6 | `[4,6)` | Có thể chứa padding nếu n=5 |
| 7 | `[6,8)` | Padding nếu n<=6 |
| 8 | `[0,1)` | Lá a[0] |
| 12 | `[4,5)` | Lá a[4] |
| 15 | `[7,8)` | Lá cuối của cây vật lý |

Khi n=5, đoạn logic là `[0,5)`, nhưng cây vật lý có đoạn gốc `[0,8)`. Các lá padding sử dụng phần tử đơn vị, nên gốc vẫn biểu thị kết quả của **năm phần tử thật**.

**Đoạn vật lý và miền dữ liệu hợp lệ là hai khái niệm khác nhau** trong biểu diễn có padding. Phương thức query phải kiểm tra `0<=l<=r<=n`, không chỉ `r<=P`.

## 30. Mảng rỗng và một phần tử trong hai cách cài

### Đệ quy với n=0

```python
empty_recursive = RecursiveSegmentTreeSum([])

assert empty_recursive.range_sum(0, 0) == 0
assert empty_recursive.n == 0

try:
    empty_recursive.point_assign(0, 4)
except IndexError:
    pass
else:
    raise AssertionError("Không có phần tử để cập nhật")
```

Không có lời gọi `_build` khi `n=0`, do đó không đệ quy vô hạn trên đoạn rỗng.

### Cây lặp với n=0

```python
empty_iterative = MonoidSegmentTree([], lambda a, b: a + b, 0)

assert empty_iterative.n == 0
assert empty_iterative.size == 1
assert empty_iterative.query(0, 0) == 0
```

Cây vật lý vẫn có hai ô `[identity,identity]` ở chỉ số 0 và 1, nhưng **không có phần tử dữ liệu thật**.

### Một phần tử

```python
single_recursive = RecursiveSegmentTreeSum([7])
single_iterative = MonoidSegmentTree([7], lambda a, b: a + b, 0)

assert single_recursive.range_sum(0, 1) == 7
assert single_iterative.query(0, 1) == 7

single_recursive.point_assign(0, -3)
single_iterative.point_assign(0, -3)

assert single_recursive.range_sum(0, 1) == -3
assert single_iterative.query(0, 1) == -3
assert single_recursive.range_sum(1, 1) == 0
assert single_iterative.query(1, 1) == 0
```

Ở n=1, gốc cũng là lá của cây, nên cập nhật chỉ sửa một giá trị.

## 31. Sai lầm về biên và cách tránh

| Sai lầm | Điều có thể xảy ra | Quy tắc đúng |
|---|---|---|
| Dùng `[lo,mid]` và `[mid,hi)` khi trộn quy ước | Trùng chỉ số mid hoặc sai độ dài | Nửa mở: `[lo,mid)` và `[mid,hi)` |
| Đệ quy khi `hi-lo==1` vẫn tiếp tục chia | Tạo đoạn rỗng, có thể lặp vô hạn | Lá là điều kiện dừng |
| Gọi build đệ quy cho n=0 | Không có lá hợp lệ | Bỏ build; xử lý cây rỗng |
| Xác định “không giao” bằng so sánh sai | Thăm nhánh không cần hoặc đọc sai | `qr<=lo or hi<=ql` |
| Trả `tree[node]` khi giao một phần | Lấy thừa phần tử | Chỉ trả trực tiếp khi nút nằm trọn |
| Gộp hai con rồi không giữ thứ tự | Sai với phép không giao hoán | Luôn `combine(left,right)` |
| Quên cập nhật nút tổ tiên | Query đoạn lớn dùng dữ liệu cũ | Gộp lại trên đường lên |
| Đi xuống cả hai con khi sửa một điểm | Làm việc thừa và dễ sửa sai | Chọn con chứa pos |
| Dùng `pos=n` làm chỉ số điểm | Ngoài miền mảng | Cần `0<=pos<n` |
| Không cho phép `r=n` ở truy vấn | Bỏ sót tổng toàn mảng | `r=n` hợp lệ |
| Tính tổng đoạn rỗng bằng cách vào truy vấn lá | Có thể gặp đoạn rỗng khó xử lý | Trả identity trước |
| Dùng 0 làm identity cho min số âm/dương | Kết quả min có thể sai | Min dùng `inf` hoặc API khác |
| Coi mọi phép gộp đều kết hợp | Không thể bảo đảm từ cây | Kiểm tra hợp đồng đại số |
| Đổi chỗ hai biến tích lũy của query lặp | Đảo thứ tự chuỗi/ma trận | Dùng left/right accumulator |
| Lấy L và R ở chỉ số lá mà quên cộng P | Đọc nhầm nút | `L=l+P,R=r+P` |
| Cho query tới các lá padding | Kết quả ngoài miền logic | Validate `r<=n`, không chỉ `r<=P` |
| Cấp phát mảng đúng `2n-1` rồi dùng chỉ số heap 2v/2v+1 tùy ý | Có thể vượt chỉ số do “lỗ” khi n lẻ | Cấp phát đủ 4n hoặc dùng cách đóng gói khác |
| Báo query O(1) vì có gốc | Chỉ toàn mảng có thể trả ở gốc | Đoạn bất kỳ O(log n) |
| Báo build O(n log n) vì cao log n | Đếm mỗi nút nhiều lần | Mỗi nút xây một lần: O(n) |
| Cập nhật đoạn bằng việc sửa một nút tổ tiên | Không cập nhật đúng các đoạn con | Cần cơ chế lazy hoặc phân rã/cập nhật phù hợp |

Những lỗi này đều liên quan trực tiếp đến việc **nhầm đoạn mà nút quản lý**, chứ không chỉ là lỗi cú pháp.

## 32. Kiểm thử đối chiếu với cách quét mảng

Một cách kiểm tra mạnh là dùng cách quét trực tiếp làm **oracle** trên dữ liệu nhỏ.

```python
def assert_all_range_sums(values, seg):
    n = len(values)

    for l in range(n + 1):
        for r in range(l, n + 1):
            expected = sum(values[l:r])
            assert seg.range_sum(l, r) == expected


samples = [
    [],
    [42],
    [0, 0, 0],
    [5, 2, 6, 3, 1, 7, 4, 8],
    [4, -1, 3, 0, 2, 5, -2],
    [3, -7, 8, 0, 1],
]

for sample in samples:
    seg = RecursiveSegmentTreeSum(sample)
    assert_all_range_sums(sample, seg)
```

Với cây lặp:

```python
def assert_all_generic_sum(values):
    seg = MonoidSegmentTree(values, lambda a, b: a + b, 0)

    for l in range(len(values) + 1):
        for r in range(l, len(values) + 1):
            assert seg.query(l, r) == sum(values[l:r])


for sample in samples:
    assert_all_generic_sum(sample)
```

Kiểm thử này có **O(n²) truy vấn** nên phù hợp cho mảng nhỏ, không phải cách xử lý một workload thực tế lớn.

### Kiểm thử cập nhật xen kẽ

```python
reference = [4, -1, 3, 0, 2, 5, -2]
recursive = RecursiveSegmentTreeSum(reference)
iterative = MonoidSegmentTree(reference, lambda a, b: a + b, 0)

operations = [
    ("assign", 4, 10),
    ("add", 0, 3),
    ("assign", 6, 0),
    ("add", 2, -8),
    ("assign", 1, -1),
]

for kind, pos, value in operations:
    if kind == "assign":
        reference[pos] = value
        recursive.point_assign(pos, value)
        iterative.point_assign(pos, value)
    else:
        reference[pos] += value
        recursive.point_add(pos, value)
        iterative.point_assign(pos, reference[pos])

    assert_all_range_sums(reference, recursive)
    assert_all_generic_sum(reference)

    for l in range(len(reference) + 1):
        for r in range(l, len(reference) + 1):
            assert iterative.query(l, r) == sum(reference[l:r])
```

Bộ đối chiếu có **cả n lẻ và n chẵn, dữ liệu âm, update ở hai đầu và đoạn rỗng**, để bắt lỗi biên hoặc lỗi cập nhật tổ tiên.

## 33. Kiểm tra bất biến của nút, không chỉ đáp án truy vấn

Ta còn có thể kiểm tra trực tiếp từng nút của bản đệ quy bằng cách duyệt lại đúng miền nó quản lý.

```python
def assert_recursive_node_invariant(seg):
    if seg.n == 0:
        return

    def walk(node, lo, hi):
        assert seg.tree[node] == sum(seg.values[lo:hi])

        if hi - lo == 1:
            return

        mid = (lo + hi) // 2
        walk(2 * node, lo, mid)
        walk(2 * node + 1, mid, hi)

    walk(1, 0, seg.n)


seg = RecursiveSegmentTreeSum([4, -1, 3, 0, 2, 5, -2])
assert_recursive_node_invariant(seg)

seg.point_assign(3, 9)
assert_recursive_node_invariant(seg)

seg.point_add(6, -4)
assert_recursive_node_invariant(seg)
```

Nếu một nút bên trong giữ tổng cũ nhưng các truy vấn test tình cờ không đi qua nó, phép kiểm tra bất biến **vẫn có thể phát hiện**.

Với cây lặp, kiểm tra:

```python
def assert_iterative_sum_invariant(seg):
    for node in range(1, seg.size):
        assert seg.tree[node] == (
            seg.tree[2 * node] + seg.tree[2 * node + 1]
        )


seg = MonoidSegmentTree([4, -1, 3, 0, 2], lambda a, b: a + b, 0)
assert_iterative_sum_invariant(seg)
```

Để kiểm tra giá trị của từng nút với mảng gốc, có thể bổ sung phép tính khoảng của node như ở mục 29, rồi so sánh với mảng đầu vào cộng các lá padding bằng identity.

## 34. Mở rộng từ tổng sang vị trí có min: argmin

Đôi khi câu hỏi không chỉ là **min của đoạn** mà còn là **vị trí xuất hiện đầu tiên của min**.

Ví dụ:

```text
a = [4, 2, 9, 2, 2, 7]
```

Min của `[0,6)` là 2, xuất hiện ở các vị trí 1,3,4. Nếu chỉ lưu giá trị min, cây không biết nên trả vị trí nào.

Giải pháp là lưu cặp:

```text
(value,index)
```

và gộp bằng `min` theo thứ tự từ điển: so sánh value trước, nếu hòa thì lấy index nhỏ hơn.

```python
from math import inf

values = [4, 2, 9, 2, 2, 7]

pairs = [
    (value, index)
    for index, value in enumerate(values)
]

argmin = MonoidSegmentTree(pairs, min, (inf, inf))

assert argmin.query(0, 6) == (2, 1)
assert argmin.query(2, 6) == (2, 3)
assert argmin.query(4, 6) == (2, 4)

argmin.point_assign(1, (10, 1))

assert argmin.query(0, 6) == (2, 3)
```

Bất biến nút giờ là **cặp (min_value,leftmost_index)** trên đoạn, chứ không đơn thuần là một số. Phép `min` trên cặp vẫn kết hợp và có identity phù hợp.

**Bài học thiết kế:** mỗi nút phải lưu **đủ thông tin** để trả lời đúng loại truy vấn, không chỉ lưu một giá trị ngẫu nhiên.

## 35. Một phép gộp không giao hoán: tổng hợp theo thứ tự

Những bản tóm tắt như chuỗi ký tự, phép hợp thành hàm, tích ma trận có thể **không giao hoán**, nhưng vẫn có tính kết hợp.

Ví dụ chuỗi:

```text
["H", "O", "C"]
```

Truy vấn `[0,3)` phải là `"HOC"`, không phải `"COH"`.

Trong segment tree:

```text
parent = combine(left_child,right_child)
```

và khi trả kết quả từ nhiều đoạn:

```text
answer = combine(block_1,block_2,...)
```

theo **thứ tự trái–phải**, không phụ thuộc thứ tự phần mềm tình cờ thăm các nút.

### Lý do nên kiểm thử thêm phép không giao hoán

Một triển khai nhầm thứ tự thường vẫn đúng với tổng/min/max vì những phép này giao hoán. Thêm một test dùng chuỗi có thể phát hiện lỗi tư duy:

```python
words = ["ab", "cd", "ef", "gh"]
seg = MonoidSegmentTree(words, lambda a, b: a + b, "")

assert seg.query(1, 4) == "cdefgh"
assert seg.query(0, 4) == "abcdefgh"
```

### Lưu ý chi phí nối chuỗi

Khi các nút chứa chuỗi dài, phép `x+y` của Python thường tạo chuỗi mới, chi phí có thể tỷ lệ với tổng độ dài ký tự được nối. Mô hình O(n) build và O(log n) query về **số lần gộp** không nhất thiết là O(n)/O(log n) về **thời gian xử lý byte**.

Nếu bài toán thật yêu cầu xử lý chuỗi lớn, cần cân nhắc một bản tóm tắt có kích thước cố định, hash đoạn, hoặc một cấu trúc thiết kế riêng.

## 36. Segment tree và lazy propagation: khi cập nhật cả đoạn

Cây được xây trong bài hỗ trợ **cập nhật một điểm**. Nếu yêu cầu:

```text
range_add(l,r,delta):
    tăng mọi a[i] trong [l,r) thêm delta
```

thì gọi `point_add` cho từng phần tử sẽ tốn:

```text
O((r-l)log n)
```

không còn O(log n) cho đoạn dài.

Muốn cập nhật **toàn bộ một đoạn** mà không đi tới mọi lá, thường dùng **lazy propagation** — lưu nhãn tác động còn chờ ở các nút có đoạn nằm trọn trong vùng cập nhật.

### Ý tưởng ví dụ với tổng

Nếu một nút quản lý `[lo,hi)`, độ dài `len=hi-lo`, và mọi phần tử của nó tăng `delta`, thì tổng nút tăng:

```text
delta * (hi-lo)
```

Ta có thể cập nhật tổng nút ngay và lưu một **lazy tag** báo rằng hai con chưa nhận đủ tác động đó. Khi lần sau cần đi xuống, mới đẩy tag xuống các con.

Điểm quan trọng là **phải cập nhật cả giá trị tổng hợp lẫn cách tích lũy tag** cho đúng. Không được sửa mỗi `tree[node]` rồi tiếp tục query các đoạn con như thể chúng đã được cập nhật.

### Phạm vi của bài

Bài này chỉ giới thiệu **vì sao phân chia miền chỉ số cho phép lazy**, chưa triển khai toàn bộ các phép cập nhật đoạn. Đặc biệt, thao tác **gán đoạn** có quy tắc hợp thành nhãn khác **cộng đoạn**; không được chỉ thay tên phép toán.

## 37. So sánh segment tree với Fenwick và sparse table

| Cấu trúc | Xây | Tổng/min đoạn | Cập nhật điểm | Thế mạnh |
|---|---:|---:|---:|---|
| Quét mảng trực tiếp | O(1) ngoài mảng | O(r-l) | O(1) | Ít câu hỏi, dữ liệu nhỏ |
| Prefix sum | O(n) | O(1) tổng tĩnh | O(n) để duy trì các tiền tố | Tổng, không cập nhật |
| Sparse table | O(n log n) | O(1) min/max tĩnh | Không hiệu quả theo thiết kế | Rất nhiều RMQ tĩnh |
| Fenwick tổng | O(n) | O(log n) tổng | O(log n) cộng điểm | Tổng động, mã gọn |
| **Segment tree cơ bản** | **O(n)** | **O(log n)** cho phép kết hợp phù hợp | **O(log n)** | Nhiều loại bản tóm tắt động |
| Sqrt decomposition | O(n) | O(√n) thường gặp | Phụ thuộc phép tổng hợp | Giải pháp theo khối đơn giản |
| Segment tree lazy | O(n) | O(log n) | Hỗ trợ cập nhật đoạn phù hợp O(log n) | Cập nhật đoạn và truy vấn đoạn |

Các con số dựa trên phép gộp/áp dụng tag O(1); bảng không hàm ý mỗi loại cập nhật đoạn đều có sẵn mà không cần thiết kế riêng.

### Khi nào dùng segment tree?

- Truy vấn đoạn liên tục và có cập nhật.
- Muốn thay đổi phép tổng hợp từ tổng sang min/max/GCD/XOR.
- Cần lưu nhiều thông tin hơn một số, như cặp (giá trị, chỉ số).
- Cần tôn trọng thứ tự gộp của những phép không giao hoán.
- Có kế hoạch mở rộng sang lazy hoặc các biến thể cây chuyên biệt.

### Khi nào cấu trúc khác có thể tốt hơn?

- Tổng tĩnh, không cập nhật: prefix sum đơn giản hơn.
- Chỉ cộng điểm/hỏi tổng: Fenwick thường ngắn gọn và ít bộ nhớ hằng số hơn.
- Min tĩnh với rất nhiều truy vấn: sparse table O(1) query đáng cân nhắc nếu có đủ RAM.
- Rất ít thao tác: quét trực tiếp có thể dễ đọc và nhanh hơn tiền xử lý.

**Lựa chọn cấu trúc phải dựa trên loại thao tác và bất biến**, không chỉ nhìn vào các ký hiệu O(log n).

## 38. Đề bài lớn, chỉ số lớn và cây đoạn động

Trong ví dụ của bài, ta biết mảng gồm `n` phần tử và cấp phát bộ nhớ O(n).

Nếu miền chỉ số rộng cực lớn nhưng chỉ **rất ít vị trí có dữ liệu**, cấp phát một cây dày cho toàn miền có thể lãng phí. Một biến thể gọi là **dynamic segment tree** (*implicit segment tree*) chỉ tạo nút khi cần.

Ví dụ miền chỉ số là:

```text
[0, 10^12)
```

nhưng chỉ vài nghìn điểm được cập nhật. Thay vì cấp phát khoảng `10^12` phần tử, có thể lưu những nút đã phát sinh theo các lần cập nhật/truy vấn.

**Tư duy phân chia không đổi:**

```text
[lo,hi)
  ->
[lo,mid) và [mid,hi)
```

Tuy nhiên, cách lưu nút đổi từ mảng dày sang đối tượng hoặc bảng ánh xạ theo nhu cầu. Mỗi đường đi có độ dài O(log U) với `U` là kích thước miền; bộ nhớ phụ thuộc số nút thực sự tạo ra, không nhất thiết O(U).

Đây là mở rộng của ý tưởng chia miền chỉ số, không phải một lý do để luôn dùng cây động trong mảng nhỏ.

## 39. Cây đoạn và bài toán truy vấn nhiều chiều

Cấu trúc chia đoạn còn được áp dụng khi dữ liệu không chỉ là một dãy 1D mà là ma trận hoặc các tập điểm.

Với ma trận `R×C`, ta có thể xây một cây theo **hàng**, và tại mỗi nút hàng lưu một cấu trúc theo **cột**. Một cách triển khai segment tree 2D hỗ trợ truy vấn hình chữ nhật và cập nhật điểm với các cận quen thuộc:

```text
Truy vấn:      O(log R * log C)
Cập nhật điểm: O(log R * log C)
Bộ nhớ:        O(R*C) cho biểu diễn dày phù hợp
```

Các biến thể triển khai cụ thể có hằng số và cách cấp phát khác nhau. Điểm quan trọng về khái niệm là cùng một đoạn chỉ số được **phân chia đệ quy theo chiều**, rồi các kết quả được gộp từ những vùng nhỏ hơn.

Đừng suy rằng segment tree 2D tự động thích hợp với mọi thao tác hình chữ nhật: cập nhật diện rộng, gán vùng và dữ liệu thưa cần thêm phân tích.

## 40. Các tình huống cần định nghĩa lại phần tử đơn vị

Cách truy vấn dùng giá trị đơn vị cho đoạn không giao/đoạn rỗng rất tiện, nhưng ta phải chọn đúng.

### Min các số có thể âm

Nếu lưu min và dùng identity=0:

```text
values = [5,6,7]

min(0,5) = 0
```

Kết quả có thể sai, vì 0 không phải “không đóng góp” cho min trên toàn bộ các giá trị dương.

Với miền số thực mở rộng, chọn:

```text
identity = +inf
```

### Max các số có thể âm

Nếu lưu max và dùng identity=0:

```text
values = [-5,-6,-7]

max(0,-5) = 0
```

cũng sai. Có thể chọn `-inf`.

### Nếu không có đơn vị tiện lợi

Ta có thể thiết kế kiểu kết quả dạng:

```text
(empty_flag, value)
```

trong đó nút rỗng được biểu diễn riêng, và phép gộp xử lý:

- Rỗng + kết quả thật → kết quả thật.
- Kết quả thật + rỗng → kết quả thật.
- Hai kết quả thật → dùng phép gộp ban đầu.

Không phải mọi phép gộp tùy ý đều có phần tử đơn vị trong miền gốc. **Thiết kế API cho đoạn rỗng là một phần của tính đúng**, không phải một chi tiết thừa.

## 41. Bài tập tự luyện có lời giải

**Bài 1 — Độ dài đoạn.** Đoạn `[2,7)` có bao nhiêu phần tử?

*Lời giải:* `7-2=5` phần tử, chỉ số 2,3,4,5,6.

**Bài 2 — Chia miền chỉ số.** Chia `[0,9)` theo `mid=(lo+hi)//2`.

*Lời giải:* `mid=4`; con trái **`[0,4)`**, con phải **`[4,9)`**.

**Bài 3 — Chia đoạn con.** Chia `[4,9)` theo cùng quy tắc.

*Lời giải:* `mid=6`; hai con **`[4,6)`** và **`[6,9)`**.

**Bài 4 — Lá.** Đoạn `[5,6)` có nên chia tiếp không?

*Lời giải:* **Không**. Độ dài 1, nên đây là lá quản lý `a[5]`.

**Bài 5 — Số lá.** Với n=7 phần tử, cây chia đến mỗi phần tử có bao nhiêu lá?

*Lời giải:* **7** lá.

**Bài 6 — Số nút logic.** Với n=7, cây nhị phân mà mỗi nút trong có hai con có bao nhiêu nút thật?

*Lời giải:* `2n-1=13` nút.

**Bài 7 — Gốc quản lý đoạn nào?** Với n=7, gốc quản lý `[0,7)` hay `[0,8)` trong bản đệ quy?

*Lời giải:* **`[0,7)`**; bản đệ quy chia đúng miền dữ liệu thật.

**Bài 8 — Tổng toàn mảng.** Với `a=[5,2,6,3,1,7,4,8]`, giá trị gốc của cây tổng là gì?

*Lời giải:* **36**.

**Bài 9 — Tổng hai nửa.** Trên mảng bài 8, nút `[0,4)` và `[4,8)` có tổng nào?

*Lời giải:* **16** và **20**.

**Bài 10 — Nút dài hai.** Nút `[2,4)` trên mảng bài 8 có tổng gì?

*Lời giải:* `6+3=**9**`.

**Bài 11 — Truy vấn [2,6).** Những nút được lấy trực tiếp trên cây n=8 là gì?

*Lời giải:* **`[2,4)` và `[4,6)`**, có tổng 9 và 8.

**Bài 12 — Kết quả truy vấn.** Tổng `[2,6)` từ bài 11 là bao nhiêu?

*Lời giải:* `9+8=**17**`.

**Bài 13 — Chia n lẻ.** Với n=7, gốc có hai con là những đoạn nào?

*Lời giải:* **`[0,3)`** và **`[3,7)`**.

**Bài 14 — Phủ [2,6) khi n=7.** Nêu một phân hoạch thành các đoạn chuẩn.

*Lời giải:* **`[2,3)`, `[3,5)`, `[5,6)`**, không giao nhau và phủ đúng `[2,6)`.

**Bài 15 — Trường hợp không giao.** Nút `[0,2)` có giao với truy vấn `[2,6)` không?

*Lời giải:* **Không**, vì `hi=2<=ql=2`. Với tổng, nút góp 0.

**Bài 16 — Nút nằm trọn.** Nếu một nút quản lý `[4,6)` và truy vấn `[2,7)`, có cần xuống con không?

*Lời giải:* **Không**; đoạn nút nằm trọn trong truy vấn, trả ngay giá trị đã lưu.

**Bài 17 — Tại sao kết hợp?** Vì sao phép gộp của cây cần tính kết hợp?

*Lời giải:* Để kết quả không phụ thuộc cách đặt ngoặc khi gộp các đoạn con theo hình cây; ví dụ tổng `(a+b)+c=a+(b+c)`.

**Bài 18 — Có cần giao hoán?** Có thể dùng segment tree nối chuỗi không?

*Lời giải:* **Có**, vì nối chuỗi kết hợp; phải giữ **thứ tự từ trái sang phải**, dù nó không giao hoán.

**Bài 19 — Đơn vị cho tổng.** Giá trị đóng góp của một nút không giao truy vấn tổng là gì?

*Lời giải:* **0**, vì `x+0=0+x=x`.

**Bài 20 — Đơn vị cho min.** Nếu các giá trị là số âm/dương tùy ý, có thể dùng 0 làm đơn vị cho min không?

*Lời giải:* **Không**; dùng **`+∞`** hoặc biểu diễn đoạn rỗng riêng.

**Bài 21 — Cập nhật một điểm.** Gán `a[4]` từ 1 thành 10, những vùng trên cây n=8 cần sửa theo đường nào?

*Lời giải:* **`[4,5)→[4,6)→[4,8)→[0,8)`**.

**Bài 22 — Tổng sau cập nhật.** Sau bài 21, tổng toàn mảng trở thành bao nhiêu?

*Lời giải:* Tăng `10-1=9`, nên `36+9=**45**`.

**Bài 23 — Truy vấn sau cập nhật.** Sau bài 21, tổng `[2,6)` là gì?

*Lời giải:* `6+3+10+7=**26**`.

**Bài 24 — Độ phức tạp xây.** Vì sao build không phải O(n log n)?

*Lời giải:* Mỗi lá và nút trong được tính đúng một lần; có `2n-1` nút thật, nên **O(n)** khi gộp O(1).

**Bài 25 — Cập nhật điểm.** Vì sao `point_assign` chỉ O(log n)?

*Lời giải:* Chỉ một nhánh được chọn ở mỗi tầng, chiều cao cây O(log n); mỗi tổ tiên gộp lại một lần.

**Bài 26 — Truy vấn đoạn.** Vì sao `range_sum(l,r)` không cần duyệt `r-l` lá?

*Lời giải:* Nút nằm trọn trả kết quả đã tổng hợp; chỉ các nhánh sát biên truy vấn cần chia tiếp, nên **O(log n)** nút.

**Bài 27 — Số lá đệm.** Với n=5, cây lặp lấy `P` bằng bao nhiêu?

*Lời giải:* **P=8**, lũy thừa 2 nhỏ nhất không dưới 5.

**Bài 28 — Vị trí lá.** Với n=5,P=8, phần tử `a[4]` nằm ở vị trí `tree` nào?

*Lời giải:* **`tree[P+4]=tree[12]`**.

**Bài 29 — Padding.** Với truy vấn min, các lá padding của cây lặp phải nhận giá trị nào?

*Lời giải:* **`+∞`** để chúng không làm thay đổi min của các phần tử thật.

**Bài 30 — Tìm tổng lặp không giao hoán.** Vì sao cần hai biến `left_answer` và `right_answer`?

*Lời giải:* Các nút được lấy từ hai biên theo hai hướng; hai biến giúp **ghép đúng thứ tự trái–phải** ngay cả với chuỗi hoặc phép không giao hoán.

**Bài 31 — Đoạn rỗng.** Với cây tổng n=0, `range_sum(0,0)` nên trả gì? Có cập nhật điểm 0 được không?

*Lời giải:* Trả **0**; không có phần tử nên cập nhật vị trí 0 phải bị từ chối.

**Bài 32 — Đoạn đóng 1-based.** Đề hỏi `[L=3,R=6]` 1-based đóng, chuyển sang dạng nào?

*Lời giải:* **`[2,6)`** 0-based nửa mở.

**Bài 33 — Argmin.** Với `a=[4,2,9,2,2,7]`, trả cặp (min, chỉ số nhỏ nhất khi hòa) trên `[0,6)`.

*Lời giải:* **`(2,1)`**.

**Bài 34 — Cập nhật cả đoạn.** Nếu n phần tử, gọi O(n) lần point_add để tăng toàn mảng sẽ có chi phí nào?

*Lời giải:* **O(n log n)**. Có thể dùng segment tree lazy được thiết kế riêng để cập nhật đoạn O(log n).

**Bài 35 — Chọn cấu trúc.** Dữ liệu không đổi, hỏi rất nhiều tổng đoạn: prefix sum hay segment tree đơn giản hơn?

*Lời giải:* **Prefix sum** thường phù hợp: xây O(n), query tổng O(1).

**Bài 36 — Tại sao có cây đoạn động?** Miền chỉ số cực lớn nhưng chỉ vài vị trí được cập nhật, vì sao không cấp phát mảng 4U?

*Lời giải:* Tốn O(U) bộ nhớ dù dữ liệu thưa; **dynamic segment tree** chỉ tạo nút cần thiết theo những đường truy cập, dùng chiều cao O(log U).

## 42. Tổng kết

**Segment tree là cây nhị phân phân chia miền chỉ số**. Một nút quản lý đoạn nửa mở `[lo,hi)`; khi độ dài lớn hơn 1, nó chia thành:

```text
mid = (lo+hi)//2

[lo,mid)    và    [mid,hi)
```

Hai đoạn con **không chồng lấn**, phủ đúng đoạn cha và giữ nguyên thứ tự của dữ liệu. Mỗi nút lưu kết quả tổng hợp:

```text
tree[node] = aggregate(a[lo:hi])
```

Với nút lá, giá trị là dữ liệu một phần tử. Với nút trong, kết quả được tính bằng phép gộp hai con:

```text
tree[node] = combine(tree[left],tree[right])
```

Truy vấn `[l,r)` dừng ở nút **không giao** hoặc **nằm trọn**, chỉ chia tiếp khi **giao một phần**. Các đoạn chuẩn được chọn không giao nhau và phủ đúng truy vấn. Cập nhật một điểm chỉ sửa lá tương ứng và các tổ tiên trên một đường lên gốc.

Khi phép gộp kết hợp, có phần tử đơn vị phù hợp và xử lý mỗi giá trị trong O(1), cây hỗ trợ **xây O(n), truy vấn đoạn O(log n), cập nhật điểm O(log n), bộ nhớ O(n)**. Có thể lưu đệ quy bằng mảng cỡ 4n hoặc lặp bằng mảng 2P với P là lũy thừa 2 gần n nhất ở phía trên.

Điều quan trọng nhất khi triển khai là **không lẫn hai loại chỉ số**: `lo,mid,hi,l,r,pos` mô tả miền của **mảng dữ liệu**, còn `node,2*node,2*node+1` mô tả **vị trí lưu cây**. Nắm đúng bất biến đoạn, quy tắc chia không giao nhau, phần tử đơn vị và thứ tự gộp sẽ giúp bạn áp dụng segment tree cho nhiều phép tổng hợp, đồng thời nhận ra khi nào cần biến thể lazy, cây động hoặc một cấu trúc khác phù hợp hơn.
