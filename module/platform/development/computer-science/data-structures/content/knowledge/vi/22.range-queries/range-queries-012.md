# Xây cây đoạn, cập nhật điểm và truy vấn đoạn

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **cây đoạn (segment tree)** lưu thông tin gì, tại sao một nút đại diện cho một **đoạn chỉ số liên tiếp**, và bất biến nào giúp kết hợp kết quả của hai cây con.
- Dùng quy ước đoạn **nửa mở `[l,r)`** với `0≤l≤r≤n` một cách nhất quán trong xây cây, truy vấn và kiểm thử.
- Vẽ cây phân hoạch từ mảng ban đầu, tính giá trị từng nút, và phân biệt **chỉ số phần tử**, **khoảng nút quản lý** và **vị trí lưu nút trong mảng cây**.
- Cài đặt **xây cây trong O(n)**, **gán lại một điểm trong O(log n)** và **truy vấn một đoạn trong O(log n)**; giải thích các cận bằng số nút được xử lý.
- Hiểu điều kiện tổng quát của phép gộp: **tính kết hợp (associativity)** và **phần tử đơn vị (identity)**; biết tại sao phép gộp **không nhất thiết phải giao hoán**.
- Phân biệt **gán giá trị mới** với **cộng thêm delta**, truy vấn tổng/min/max/gcd với truy vấn cần nhiều metadata hơn.
- Xử lý đúng **mảng rỗng, đoạn rỗng, đoạn một phần tử, `r=n`, `n` không phải lũy thừa hai, khóa/giá trị âm và chỉ số ngoài miền**.
- Đọc mã Python tự chứa cho cây đoạn đệ quy và biến thể xây dưới lên, cùng bộ ví dụ `assert` và phép đối chiếu với cách tính trực tiếp.
- Chọn giữa **duyệt trực tiếp, mảng tổng tiền tố, Fenwick tree và segment tree** theo loại truy vấn, tần suất cập nhật, thời gian, bộ nhớ và độ phức tạp triển khai.

## 1. Bài toán: nhiều truy vấn đoạn trên dữ liệu thay đổi

Giả sử một nền tảng học cấu trúc dữ liệu ghi lại số lần tương tác với bài học theo từng ngày:

```text
Ngày (chỉ số):       0   1   2   3   4   5   6   7
Số tương tác A:     -2   5   3   7   1   4   6   0
```

Giá trị âm trong ví dụ có thể biểu diễn **điều chỉnh số liệu**, không nhất thiết là số lần truy cập thô. Ta cần liên tục trả lời:

1. Tổng từ chỉ số 2 đến ngay trước chỉ số 6 là bao nhiêu?
2. Nếu dữ liệu ở chỉ số 3 được sửa từ 7 thành 10, tổng đoạn `[2,6)` mới là bao nhiêu?
3. Có thể dùng cùng ý tưởng để tìm **nhỏ nhất/lớn nhất** hoặc **ước chung lớn nhất** trên đoạn không?

Với mảng `A` có `n` phần tử, **truy vấn tổng đoạn nửa mở** được định nghĩa:

\[
\operatorname{sum}(l,r)=\sum_{i=l}^{r-1}A[i],
\qquad 0\le l\le r\le n.
\]

Đoạn `[l,r)` chứa `l,l+1,\ldots,r-1`, **không** chứa `r`. Khi `l=r`, đoạn rỗng, tổng bằng **0**.

Trong ví dụ:

\[
\operatorname{sum}(2,6)=3+7+1+4=15.
\]

Nếu thay `A[3]=10`, kết quả thành:

\[
\operatorname{sum}(2,6)=3+10+1+4=18.
\]

### 1.1. So sánh ba cách giải ban đầu

| Phương pháp | Xây dựng ban đầu | Gán lại một phần tử | Truy vấn tổng `[l,r)` |
| --- | --- | --- | --- |
| Mảng thường, cộng trực tiếp | O(n) để có dữ liệu | O(1) | O(r-l), xấu nhất O(n) |
| Tổng tiền tố `P` cố định | O(n) | O(n) nếu cập nhật lại các tổng phía sau | O(1), dùng `P[r]-P[l]` |
| **Segment tree** | **O(n)** | **O(log n)** | **O(log n)** |

Khi dữ liệu **không thay đổi**, mảng tổng tiền tố có thể đơn giản và hiệu quả hơn. Khi có cả **nhiều truy vấn đoạn lẫn cập nhật điểm**, cây đoạn là một cấu trúc phù hợp.

**Segment tree không phải BST.** Nó không tìm theo thứ tự khóa; nó **phân chia miền chỉ số** để lưu kết quả gộp của từng đoạn.

## 2. Cấu trúc của một cây đoạn

Mỗi nút biểu diễn **một đoạn liên tiếp `[L,R)`** của mảng:

- Gốc quản lý toàn bộ `[0,n)`.
- Với đoạn có từ hai phần tử trở lên, chọn `M=(L+R)//2`.
- Con trái quản lý `[L,M)`, con phải quản lý `[M,R)`.
- Lá quản lý `[i,i+1)` và chứa giá trị `A[i]`.
- Giá trị nút trong là **kết quả gộp** hai giá trị cây con.

Sơ đồ cây tổng cho mảng tám phần tử `A=[-2,5,3,7,1,4,6,0]`:

```text
                          [0,8) : 24
                       /               \
               [0,4) : 13           [4,8) : 11
               /        \           /         \
         [0,2):3      [2,4):10  [4,6):5      [6,8):6
          /    \       /    \     /    \       /    \
       [0,1) [1,2) [2,3) [3,4) [4,5) [5,6) [6,7) [7,8)
         -2      5      3      7      1      4      6      0
```

Giải thích:

- `[0,2)` chứa `-2,5` nên lưu `3`.
- `[2,4)` chứa `3,7` nên lưu `10`.
- `[0,4)` lưu `3+10=13`.
- `[4,8)` lưu `5+6=11`.
- Gốc `[0,8)` lưu `13+11=24`.

### 2.1. Bất biến quan trọng nhất

Ký hiệu `tree(v)` là giá trị lưu tại nút `v` quản lý đoạn `[L,R)`, `combine` là phép gộp:

\[
tree(v)=
\begin{cases}
A[L],&R-L=1,\\
\operatorname{combine}(tree(v_{left}),tree(v_{right})),
&R-L>1.
\end{cases}
\]

Khi truy vấn tổng, `combine(a,b)=a+b`. Với `min`, dùng `combine(a,b)=min(a,b)`. Đây là **bất biến tổng hợp**: mỗi nút phải tóm tắt đúng đoạn mà nó quản lý.

**Giữ bất biến này sau mỗi lần cập nhật** chính là lý do ta chỉ cần sửa các nút trên đường từ lá tới gốc.

### 2.2. Chỉ số mảng dữ liệu khác với chỉ số lưu nút

Trong cài đặt cây đệ quy bằng một mảng `tree`:

- `v` là **vị trí lưu nút trong mảng cây**.
- `L,R` là **ranh giới đoạn của dữ liệu gốc** mà nút `v` quản lý.
- Chọn gốc `v=1`, con trái `2v`, con phải `2v+1`.
- Chỉ số dữ liệu `i` là vị trí trong `A`, không phải `v`.

Ví dụ nút `v=5` trong cây tám phần tử quản lý `[2,4)`, **không phải phần tử `A[5]`**.

### 2.3. Không cần n là lũy thừa hai

Với `n=5`, cây vẫn chia theo trung điểm:

```text
                 [0,5)
                /     \
             [0,2)   [2,5)
             /   \    /    \
          [0,1)[1,2)[2,3) [3,5)
                            /  \
                        [3,4) [4,5)
```

Hai nhánh có thể khác nhau một mức. Mọi lá vẫn quản lý đúng **một phần tử** và số nút thật của cây phân hoạch nhị phân đầy đủ này là **2n−1** khi `n≥1`.

**“Cây nhị phân đầy đủ” ở đây** nghĩa là mọi nút trong có đúng hai con; không có nghĩa tất cả lá cùng độ sâu.

## 3. Phép gộp: từ tổng đoạn đến monoid

Để cây đoạn hoạt động đúng với cách phân chia bất kỳ, phép gộp cần **tính kết hợp**:

\[
(a\otimes b)\otimes c=a\otimes(b\otimes c).
\]

Nếu triển khai truy vấn đệ quy trả kết quả đơn vị cho các phần **không giao nhau**, ta còn cần một **phần tử đơn vị `e`**:

\[
e\otimes a=a\otimes e=a.
\]

Một tập giá trị với phép toán kết hợp và phần tử đơn vị được gọi là **monoid**. Cây đoạn có thể xem là cách lưu phép gộp monoid trên từng đoạn liên tiếp.

### 3.1. Các phép gộp thường gặp

| Cần truy vấn | `a⊗b` | `e` cho đoạn rỗng | Ghi chú |
| --- | --- | --- | --- |
| Tổng số | `a+b` | `0` | Cộng số nguyên là kết hợp |
| Tích số | `a*b` | `1` | Chú ý tràn số trong ngôn ngữ có miền số cố định |
| Nhỏ nhất | `min(a,b)` | `+∞` | Phải xử lý kiểu dữ liệu có so sánh được |
| Lớn nhất | `max(a,b)` | `−∞` | Đơn vị cần nhỏ hơn mọi giá trị hợp lệ |
| Ước chung lớn nhất | `gcd(a,b)` | `0` | `gcd(0,a)=|a|` |
| AND bit | `a & b` | Tất cả bit 1 trong miền bit cố định | Định nghĩa độ rộng bit rõ ràng |
| Ghép chuỗi | `a+b` (nối chuỗi) | Chuỗi rỗng `""` | **Kết hợp nhưng không giao hoán** |

Phép `min` có thể dùng `float("inf")` khi miền dữ liệu là số hữu hạn Python. Không dùng một số “rất lớn” tùy tiện làm đơn vị nếu dữ liệu thật có thể lớn hơn số đó.

### 3.2. Không cần tính giao hoán

**Kết hợp** không có nghĩa **giao hoán**:

\[
a\otimes b\ \text{có thể khác}\ b\otimes a.
\]

Ví dụ ghép chuỗi:

```text
A = ["A", "B", "C", "D"]
combine(x,y) = x + y
identity = ""

query(1,4) = "BCD"
query(2,4) = "CD"
```

Nếu gộp `right` trước `left` thì trả `"DCB"` và sai dù phép nối chuỗi có tính kết hợp. Vì vậy **phải giữ thứ tự con trái rồi con phải** trong cây và truy vấn.

### 3.3. Một phép gộp không kết hợp sẽ không phù hợp

Phép trừ thông thường **không kết hợp**:

\[
(10-3)-2=5,\qquad 10-(3-2)=9.
\]

Nếu lấy `combine(a,b)=a-b`, kết quả phụ thuộc cách ngoặc và hình dạng phân hoạch. Không thể dùng trực tiếp công thức xây cây/truy vấn chuẩn để hứa kết quả “trừ từ trái sang phải” cho mọi đoạn.

Muốn hỗ trợ một truy vấn phức tạp, cần thiết kế **dữ liệu tóm tắt và phép combine kết hợp** phù hợp, không chỉ thay tùy ý dấu `+` bằng một phép toán khác.

## 4. Xây cây (build): tính tổng từ các lá lên gốc

Giả sử `n≥1`, lời gọi ban đầu là:

```text
build(v=1, L=0, R=n)
```

Thuật toán:

1. Nếu `R-L=1`: nút `v` là lá cho `A[L]`; gán `tree[v]=A[L]`.
2. Nếu `R-L>1`: tính `M=(L+R)//2`.
3. Gọi `build(2*v,L,M)` và `build(2*v+1,M,R)`.
4. Gán `tree[v]=combine(tree[2*v],tree[2*v+1])`.

Mã giả:

```text
BUILD(v, L, R):
    if R - L == 1:
        tree[v] = A[L]
        return

    M = (L + R) // 2
    BUILD(2*v, L, M)
    BUILD(2*v + 1, M, R)
    tree[v] = combine(tree[2*v], tree[2*v + 1])
```

Lưu ý: xử lý **hai con trước** rồi mới gộp kết quả vào cha. Đây là **duyệt hậu tự (postorder)** theo nghĩa tính toán trên cây.

### 4.1. Truy vết build trên bốn phần tử

```text
A = [4, -1, 7, 2]

                  [0,4) = 12
                  /         \
          [0,2) = 3       [2,4) = 9
            /   \           /   \
         [0,1) [1,2)    [2,3)  [3,4)
            4     -1        7      2
```

Thứ tự tính giá trị có thể là:

```text
tree[4] <- 4
tree[5] <- -1
tree[2] <- 4 + (-1) = 3
tree[6] <- 7
tree[7] <- 2
tree[3] <- 7 + 2 = 9
tree[1] <- 3 + 9 = 12
```

`tree[1]` lưu tổng cả mảng, nhưng `tree[1]` **không phải** `A[1]`.

### 4.2. Chứng minh bất biến build bằng quy nạp

Mệnh đề: sau `BUILD(v,L,R)`, `tree[v]` là kết quả gộp đúng các phần tử `A[L],\ldots,A[R-1]` theo thứ tự.

**Cơ sở:** Nếu `R-L=1`, cây con chỉ có một phần tử `A[L]`. Thuật toán lưu đúng `A[L]`.

**Bước quy nạp:** Với `R-L>1`, hai lời gọi con đã cho kết quả đúng của `[L,M)` và `[M,R)`. Hai đoạn liên tiếp, không giao nhau và hợp lại bằng `[L,R)`. Vì `combine` kết hợp, gộp kết quả **trái rồi phải** cho đúng kết quả của toàn đoạn.

Vậy mọi nút, đặc biệt gốc, thỏa bất biến sau build.

### 4.3. Tại sao build O(n), không phải O(n log n)?

Cây phân hoạch có `n` lá. Mỗi nút trong có **hai con**; số nút trong bằng `n−1`, nên có:

\[
n+(n-1)=2n-1
\]

nút thật khi `n≥1`.

Mỗi nút được xây **đúng một lần** và thực hiện O(1) công việc ngoài các lời gọi con nếu `combine` có chi phí O(1). Do đó:

\[
T_{\mathrm{build}}(n)=\Theta(n).
\]

**Không phải** xây cây bằng cách khởi tạo rỗng rồi chèn từng phần tử O(log n), vì cách đó có thể tốn O(n log n). Với dữ liệu ban đầu đã biết, build từ các lá tiết kiệm hơn.

## 5. Cập nhật điểm (point update): chỉ sửa một đường từ lá lên gốc

Giả sử cần **gán giá trị mới**:

```text
set(index=3, value=10)
```

Trước đó `A[3]=7`. Sau phép gán, cần bảo đảm tất cả nút quản lý đoạn **chứa chỉ số 3** được cập nhật theo bất biến.

Với mảng tám phần tử:

```text
TRƯỚC:
                          [0,8) : 24
                         /            \
                  [0,4) : 13       [4,8) : 11
                  /         \
              [0,2):3     [2,4):10
                           /      \
                       [2,3):3  [3,4):7

SAU set(3,10):
                          [0,8) : 27
                         /            \
                  [0,4) : 16       [4,8) : 11
                  /         \
              [0,2):3     [2,4):13
                           /      \
                       [2,3):3  [3,4):10
```

Chỉ các nút `[3,4)`, `[2,4)`, `[0,4)` và `[0,8)` thay đổi. Mọi nút quản lý đoạn **không chứa chỉ số 3** vẫn giữ nguyên kết quả.

### 5.1. Thuật toán cập nhật

Cho nút `v` quản lý `[L,R)`:

1. Nếu `R-L=1` thì `L=index`, đặt `tree[v]=new_value`.
2. Nếu không, tính `M=(L+R)//2`.
3. Nếu `index<M`, đi xuống **con trái**; ngược lại đi xuống **con phải**.
4. Khi quay lên từ đệ quy, gán lại:

\[
tree[v]=\operatorname{combine}(tree[2v],tree[2v+1]).
\]

Mã giả:

```text
SET(v, L, R, index, new_value):
    if R - L == 1:
        tree[v] = new_value
        return
    M = (L + R) // 2
    if index < M:
        SET(2*v, L, M, index, new_value)
    else:
        SET(2*v+1, M, R, index, new_value)
    tree[v] = combine(tree[2*v], tree[2*v+1])
```

Vì chỉ chọn **một** trong hai con ở mỗi tầng, chi phí cập nhật tương ứng với chiều cao cây.

### 5.2. Chứng minh cập nhật O(log n)

Mỗi lần chia theo trung điểm làm độ dài đoạn giảm gần một nửa. Chiều cao cây là O(log n) với `n≥1`. Một cập nhật:

- Ghé **một nút trên mỗi tầng**.
- Mỗi tầng chỉ cần so sánh chỉ số, đi một nhánh và gộp lại O(1).
- Kết thúc tại đúng **một lá**.

Vì vậy:

\[
T_{\mathrm{set}}(n)=O(\log n)
\]

với `n≥2` và phép gộp O(1). Với `n=1`, thao tác là O(1); có thể viết thống nhất **O(log(n+1))** để bao cả trường hợp nhỏ.

### 5.3. Gán giá trị khác với cộng thêm delta

Hai API thường gặp:

```text
set(3, 10)        # A[3] trở thành 10
add(3, 10)        # A[3] trở thành A[3] + 10
```

Nếu trước đó `A[3]=7`, `set(3,10)` cho `10`, còn `add(3,10)` cho `17`. Nhầm hai loại cập nhật làm sai kết quả.

Với cây tổng, khi biết `old=A[index]`, thao tác gán có thể được chuyển thành cộng `delta=new-old`, nhưng đây là **một chiến lược riêng phụ thuộc phép cộng**. Với cây `min` hoặc `gcd`, không thể mặc định sửa mọi nút bằng **cộng cùng delta**.

Trong cài đặt tổng quát bên dưới, `set` là thao tác nền tảng. Muốn cộng thêm một điểm cho cây tổng, có thể dùng `set(index, get(index)+delta)`.

### 5.4. Nếu cập nhật giá trị nhưng quên cập nhật cha?

Ví dụ thay `A[3]` ở lá nhưng giữ `tree[5]` hay `tree[1]` cũ. Truy vấn chỉ đụng đúng lá có thể cho giá trị mới, nhưng truy vấn một đoạn bao trùm nút cha có thể trả giá trị **cũ**, vi phạm bất biến.

Vì vậy bộ kiểm thử phải hỏi cả **đoạn nhỏ** và **đoạn lớn** sau cập nhật, không chỉ kiểm tra `get(3)`.

## 6. Truy vấn đoạn: không giao, phủ hoàn toàn, giao một phần

Mỗi lời gọi truy vấn nhận:

- Nút `v` quản lý `[L,R)`.
- Đoạn cần hỏi `[ql,qr)`.

Có **ba trường hợp**:

1. **Không giao nhau:** `qr≤L` hoặc `R≤ql`. Trả **identity `e`**.
2. **Phủ hoàn toàn:** `ql≤L` và `R≤qr`. Trả ngay `tree[v]`, **không đi xuống**.
3. **Giao một phần:** chia đoạn theo `M`, truy vấn hai con và **gộp kết quả trái rồi phải**.

```text
QUERY(v, L, R, ql, qr):
    if qr <= L or R <= ql:
        return identity
    if ql <= L and R <= qr:
        return tree[v]
    M = (L + R) // 2
    left_result = QUERY(2*v, L, M, ql, qr)
    right_result = QUERY(2*v+1, M, R, ql, qr)
    return combine(left_result, right_result)
```

Phải kiểm **không giao** trước **phủ hoàn toàn** để xử lý đúng các đoạn rỗng hoặc các đoạn không liên quan. Giao một phần chỉ xuất hiện ở nút có ít nhất hai phần tử, nếu đầu vào hợp lệ.

### 6.1. Truy vết truy vấn `[2,6)` trên cây tám phần tử

```text
                                     [0,8):24
                                   giao một phần
                                  /             \
                         [0,4):13               [4,8):11
                       giao một phần           giao một phần
                        /        \               /       \
                  [0,2):3      [2,4):10      [4,6):5    [6,8):6
                    loại       lấy ngay        lấy ngay    loại
```

Các nút được chọn để trả kết quả:

```text
[2,4) -> 10
[4,6) ->  5
--------------
[2,6) -> 15
```

Không cần xuống bốn lá riêng lẻ `[2,3),[3,4),[4,5),[5,6)` vì hai nút phủ hoàn toàn đã lưu tổng sẵn.

Sau `set(3,10)`:

```text
[2,4) -> 13
[4,6) ->  5
--------------
[2,6) -> 18
```

### 6.2. Vì sao query O(log n), dù có thể đi xuống hai con?

Cây có chiều cao `O(log n)`. Một đoạn truy vấn liên tiếp có **tối đa hai ranh giới** cần xét: bên trái `ql` và bên phải `qr`.

Ở một mức bất kỳ:

- Các nút quản lý đoạn **nằm hoàn toàn trong truy vấn** sẽ được lấy ngay, không mở rộng cây con.
- Các nút phải **tiếp tục chia** chỉ có thể nằm dọc những đường giáp **ranh giới trái/phải** của đoạn.
- Vì thế số nút được mở rộng mỗi mức bị chặn bởi một hằng số, không phải tăng gấp đôi vô hạn.

Tổng số nút được thăm là **O(log n)** với `n≥1` và phép gộp O(1). Do đó:

\[
T_{\mathrm{query}}(n)=O(\log(n+1)).
\]

Một cách diễn giải khác: đoạn `[ql,qr)` được biểu diễn thành **O(log n)** nút phân hoạch lớn nhất, không giao nhau, rồi gộp các kết quả của các nút ấy.

### 6.3. Đoạn rỗng và đoạn ngoài miền

Với `n=8`:

- `query(0,8)`: tổng toàn mảng, trả ngay giá trị gốc.
- `query(3,4)`: một phần tử, bằng `A[3]`.
- `query(2,2)`: đoạn rỗng, trả identity `0` với phép tổng.
- `query(8,8)`: đoạn rỗng hợp lệ ở ranh giới cuối, trả `0`.
- `query(5,3)`: **không hợp lệ** vì `l>r`.
- `query(-1,4)` hoặc `query(0,9)`: **ngoài miền**, phải báo lỗi thay vì âm thầm cắt đoạn.

Quy ước khác như đoạn đóng `[l,r]` cũng có thể dùng, nhưng khi đó phải chuyển đổi cẩn thận: `[l,r]` tương đương `[l,r+1)` nếu `r` là chỉ số hợp lệ. Bài này chỉ dùng **nửa mở**.

### 6.4. Truy vấn theo thứ tự trái–phải

Với tổng, phép cộng giao hoán nên đổi thứ tự trái–phải vẫn tình cờ cho cùng số. Nhưng với phép **nối chuỗi** hoặc kết hợp ma trận, thứ tự rất quan trọng.

Quy tắc chung:

```text
answer = combine(answer_from_left, answer_from_right)
```

Không được đảo ngẫu nhiên vì thuật toán cây đoạn chỉ đòi **kết hợp**, không đòi **giao hoán**.

## 7. Cài đặt Python đầy đủ: cây đoạn đệ quy tổng quát

Ta xây lớp `SegmentTree` nhận:

- `values`: danh sách giá trị ban đầu.
- `combine(a,b)`: phép gộp **kết hợp** theo thứ tự **trái rồi phải**.
- `identity`: phần tử đơn vị của phép gộp.

Các phương thức:

| API | Ý nghĩa | Thời gian |
| --- | --- | --- |
| `SegmentTree(values,combine,identity)` | Xây cây | O(n) |
| `get(i)` | Đọc giá trị tại một điểm từ bản sao mảng dữ liệu | O(1) |
| `set(i,value)` | Gán lại một phần tử và cập nhật các nút tổ tiên | O(log(n+1)) |
| `query(l,r)` | Gộp các phần tử có chỉ số trong `[l,r)` | O(log(n+1)) |
| `to_list()` | Lấy một bản sao danh sách giá trị hiện tại | O(n) |
| `validate()` | Kiểm tra bất biến mọi nút bằng tính lại từ lá | O(n) |

Cận trên giả định **một lần `combine` tốn O(1)**, như cộng số nguyên cỡ máy, `min` hoặc `max`. Với số nguyên độ dài không bị chặn, chuỗi ký tự dài hoặc ma trận kích thước tăng, chi phí phép gộp phải được cộng vào phân tích; phần cấu trúc cây vẫn thăm O(log n) nút cho mỗi cập nhật/truy vấn.

### 7.1. Toàn bộ lớp `SegmentTree`

```python
class SegmentTree:
    """Cây đoạn trên mảng A[0:n], truy vấn nửa mở [l, r).

    combine phải kết hợp và có identity hai phía.
    Phép combine nên thuần (không sửa đối số).
    Giả định giá trị/identity bất biến trong lúc nằm trong cây.
    """

    def __init__(self, values, combine, identity):
        if not callable(combine):
            raise TypeError("combine phải là hàm gọi được")

        self._values = list(values)
        self.n = len(self._values)
        self.combine = combine
        self.identity = identity

        # Gốc ở 1; con trái 2*v, con phải 2*v + 1.
        # Với n>=1, cấp phát 4*n+1 ô là cận trên an toàn.
        self.tree = (
            [identity] * (4 * self.n + 1)
            if self.n > 0 else []
        )
        if self.n > 0:
            self._build(1, 0, self.n)

    def _build(self, v, left, right):
        if right - left == 1:
            self.tree[v] = self._values[left]
            return

        mid = (left + right) // 2
        self._build(2 * v, left, mid)
        self._build(2 * v + 1, mid, right)
        self.tree[v] = self.combine(
            self.tree[2 * v],
            self.tree[2 * v + 1],
        )

    def _check_index(self, index):
        if type(index) is not int:
            raise TypeError("index phải là int, không nhận bool")
        if not (0 <= index < self.n):
            raise IndexError("Chỉ số nằm ngoài [0, n)")

    def _check_range(self, left, right):
        if type(left) is not int or type(right) is not int:
            raise TypeError("Hai ranh giới phải là int")
        if not (0 <= left <= right <= self.n):
            raise IndexError("Cần 0 <= left <= right <= n")

    def get(self, index):
        """Đọc giá trị điểm, không truy vấn cây."""
        self._check_index(index)
        return self._values[index]

    def to_list(self):
        """Bản sao nông của các giá trị."""
        return list(self._values)

    def set(self, index, value):
        """Gán A[index] = value, rồi sửa lá và các tổ tiên."""
        self._check_index(index)
        self._values[index] = value
        self._set(1, 0, self.n, index, value)

    def _set(self, v, left, right, index, value):
        if right - left == 1:
            self.tree[v] = value
            return

        mid = (left + right) // 2
        if index < mid:
            self._set(2 * v, left, mid, index, value)
        else:
            self._set(2 * v + 1, mid, right, index, value)

        self.tree[v] = self.combine(
            self.tree[2 * v],
            self.tree[2 * v + 1],
        )

    def query(self, left, right):
        """Gộp theo đúng thứ tự A[left:right]."""
        self._check_range(left, right)
        if left == right:
            return self.identity
        return self._query(1, 0, self.n, left, right)

    def _query(self, v, seg_l, seg_r, ql, qr):
        # 1. Không giao nhau.
        if qr <= seg_l or seg_r <= ql:
            return self.identity

        # 2. Đoạn của nút nằm trọn trong truy vấn.
        if ql <= seg_l and seg_r <= qr:
            return self.tree[v]

        # 3. Giao một phần: đi cả hai con, giữ trái-trước-phải.
        mid = (seg_l + seg_r) // 2
        left_answer = self._query(
            2 * v, seg_l, mid, ql, qr
        )
        right_answer = self._query(
            2 * v + 1, mid, seg_r, ql, qr
        )
        return self.combine(left_answer, right_answer)

    def validate(self):
        """Kiểm thử O(n), không chạy trong thao tác lõi.

        Giả định toán tử == so sánh đúng các giá trị gộp.
        """
        if self.n == 0:
            assert self.tree == []
            return True

        def visit(v, left, right):
            if right - left == 1:
                expected = self._values[left]
            else:
                mid = (left + right) // 2
                expected_left = visit(2 * v, left, mid)
                expected_right = visit(2 * v + 1, mid, right)
                expected = self.combine(
                    expected_left, expected_right
                )

            assert self.tree[v] == expected, (
                f"Ô cây sai tại nút {v}, đoạn [{left},{right})"
            )
            return expected

        visit(1, 0, self.n)
        return True
```

**Lưu ý về dữ liệu khả biến:** Ví dụ trên giả định `combine` là một phép **thuần**, không sửa đổi đối số, và giá trị lưu trong cây **không bị sửa từ bên ngoài mà bỏ qua `set`**. Chẳng hạn, nếu một ô chứa `list` và code bên ngoài `append` trực tiếp vào chính đối tượng ấy, những giá trị tổng hợp tại tổ tiên có thể không được cập nhật. Muốn hỗ trợ giá trị khả biến, cần thiết kế quy tắc sao chép hoặc bất biến hóa thích hợp.

### 7.2. Dùng cho phép tổng và đối chiếu từng bước

```python
from operator import add

values = [-2, 5, 3, 7, 1, 4, 6, 0]
tree = SegmentTree(values, combine=add, identity=0)

assert tree.n == 8
assert tree.to_list() == values
assert tree.validate()

# Tổng theo từng nút ở sơ đồ mục 2.
assert tree.query(0, 8) == 24
assert tree.query(0, 4) == 13
assert tree.query(4, 8) == 11
assert tree.query(2, 4) == 10
assert tree.query(4, 6) == 5
assert tree.query(2, 6) == 15

# Đoạn một phần tử và đoạn rỗng.
assert tree.query(3, 4) == 7
assert tree.query(0, 0) == 0
assert tree.query(8, 8) == 0

# Gán A[3] từ 7 thành 10: không phải cộng thêm 10.
tree.set(3, 10)
assert tree.get(3) == 10
assert tree.to_list() == [-2, 5, 3, 10, 1, 4, 6, 0]

# Những đoạn chứa chỉ số 3 đổi, nhánh phải không đổi.
assert tree.query(2, 4) == 13
assert tree.query(0, 4) == 16
assert tree.query(4, 8) == 11
assert tree.query(2, 6) == 18
assert tree.query(0, 8) == 27
assert tree.validate()

# Nếu cần cộng thêm delta=2 ở chỉ số 3:
tree.set(3, tree.get(3) + 2)
assert tree.get(3) == 12
assert tree.query(2, 6) == 20
assert tree.query(0, 8) == 29
assert tree.validate()
```

Các phép `assert` thể hiện **kết quả mong đợi**, không phải báo cáo rằng mã đã chạy trong bước biên soạn tài liệu.

### 7.3. Mảng rỗng, chỉ số không hợp lệ và n không phải lũy thừa hai

```python
empty = SegmentTree([], add, 0)
assert empty.n == 0
assert empty.query(0, 0) == 0
assert empty.validate()

try:
    empty.set(0, 5)
except IndexError:
    pass
else:
    raise AssertionError("Không thể cập nhật điểm của mảng rỗng")

try:
    empty.query(0, 1)
except IndexError:
    pass
else:
    raise AssertionError("Không cho phép truy vấn ngoài miền")

small = SegmentTree([4, -1, 7, 2, 5], add, 0)
assert small.n == 5
assert small.query(0, 5) == 17
assert small.query(1, 4) == 8
assert small.query(5, 5) == 0
small.set(4, -5)
assert small.query(0, 5) == 7
assert small.query(3, 5) == -3
assert small.validate()

for bad_range in [(-1, 3), (0, 6), (4, 2)]:
    try:
        small.query(*bad_range)
    except IndexError:
        pass
    else:
        raise AssertionError(f"Đã chấp nhận {bad_range}")
```

**Quyết định API đáng chú ý:** mảng rỗng vẫn hỗ trợ truy vấn **đoạn rỗng `[0,0)`** và trả identity. Nhưng cập nhật điểm ở mảng rỗng là lỗi. Các đoạn có `r=n` hoàn toàn hợp lệ.

### 7.4. Tổng, nhỏ nhất, lớn nhất và GCD

```python
from math import gcd, inf

numbers = [18, 24, 30, 42, 12]

sum_tree = SegmentTree(numbers, add, 0)
min_tree = SegmentTree(numbers, min, inf)
max_tree = SegmentTree(numbers, max, -inf)
gcd_tree = SegmentTree(numbers, gcd, 0)

assert sum_tree.query(1, 4) == 24 + 30 + 42
assert min_tree.query(1, 4) == 24
assert max_tree.query(1, 4) == 42
assert gcd_tree.query(1, 4) == 6

# Mỗi cây có trạng thái riêng: phải cập nhật từng cây nếu
# ứng dụng dùng nhiều chỉ mục trên cùng dữ liệu logic.
for t in [sum_tree, min_tree, max_tree, gcd_tree]:
    t.set(2, 9)
    assert t.validate()

assert sum_tree.query(1, 4) == 75
assert min_tree.query(1, 4) == 9
assert max_tree.query(1, 4) == 42
assert gcd_tree.query(1, 4) == 3

# Đơn vị của đoạn rỗng tùy phép gộp.
assert sum_tree.query(3, 3) == 0
assert min_tree.query(3, 3) == inf
assert max_tree.query(3, 3) == -inf
assert gcd_tree.query(3, 3) == 0
```

Không thể lấy một cây tổng rồi gọi `query` như thể nó là cây `min`: giá trị lưu tại các nút trong đã được gộp theo phép `sum`. Muốn đổi loại truy vấn, phải **xây cây với phép gộp/metadata tương ứng**, hoặc thiết kế một cấu trúc tổng hợp nhiều trường.

### 7.5. Phép gộp kết hợp nhưng không giao hoán

```python
letters = SegmentTree(
    ["A", "B", "C", "D", "E"],
    combine=lambda a, b: a + b,
    identity="",
)

assert letters.query(0, 5) == "ABCDE"
assert letters.query(1, 4) == "BCD"
assert letters.query(2, 2) == ""

letters.set(2, "X")
assert letters.query(0, 5) == "ABXDE"
assert letters.query(1, 4) == "BXD"
assert letters.validate()
```

Trong ví dụ này `combine` nối chuỗi Python và có thể tốn thời gian **tỉ lệ độ dài chuỗi đầu ra**, không còn O(1) theo kích thước nội dung. Cây vẫn **phân rã truy vấn thành O(log n) nút**, nhưng không nên kết luận thời gian CPU của việc tạo chuỗi dài là O(log n) mà bỏ qua chi phí sao chép ký tự.

## 8. Biến thể lặp: các lá đặt ở cuối mảng cây

Cài đặt đệ quy dễ học vì mỗi lời gọi có đoạn `[L,R)` rõ ràng. Một cách khác là dùng **cây đoạn lặp (iterative segment tree)**, thuận lợi khi muốn tránh lời gọi hàm đệ quy trong `set/query`.

Ta chọn `base` là **lũy thừa hai nhỏ nhất không nhỏ hơn `n`**:

```text
n = 5, base = 8

Vị trí mảng tree:
         tree[1]                    gốc
       /         \
    tree[2]      tree[3]
    ...
    tree[8] ... tree[15]            lá
        A[0] ... A[4], e, e, e       các ô đệm
```

- `tree[base+i]` lưu `A[i]` với `0≤i<n`.
- Các lá `i≥n` là **phần đệm identity `e`**.
- Các nút trong được gộp từ hai con: `tree[p]=combine(tree[2p],tree[2p+1])`.
- Các đoạn bên ngoài `[0,n)` không bao giờ được trả như dữ liệu thật; phần đệm chỉ giúp cây có hình dạng đều.

### 8.1. Cài đặt đầy đủ

```python
class IterativeSegmentTree:
    """Cây đoạn xây dưới lên, query [left,right).

    Giá trị bất biến; combine thuần, kết hợp và có identity.
    """

    def __init__(self, values, combine, identity):
        if not callable(combine):
            raise TypeError("combine phải là hàm gọi được")
        data = list(values)
        self.n = len(data)
        self.combine = combine
        self.identity = identity

        self.base = 1
        while self.base < self.n:
            self.base *= 2

        self.tree = [identity] * (2 * self.base)
        for i, value in enumerate(data):
            self.tree[self.base + i] = value

        for p in range(self.base - 1, 0, -1):
            self.tree[p] = self.combine(
                self.tree[2 * p],
                self.tree[2 * p + 1],
            )

    def _check_index(self, index):
        if type(index) is not int:
            raise TypeError("index phải là int")
        if not (0 <= index < self.n):
            raise IndexError("index nằm ngoài [0,n)")

    def _check_range(self, left, right):
        if type(left) is not int or type(right) is not int:
            raise TypeError("Ranh giới phải là int")
        if not (0 <= left <= right <= self.n):
            raise IndexError("Cần 0 <= left <= right <= n")

    def get(self, index):
        self._check_index(index)
        return self.tree[self.base + index]

    def set(self, index, value):
        self._check_index(index)
        p = self.base + index
        self.tree[p] = value

        p //= 2
        while p >= 1:
            self.tree[p] = self.combine(
                self.tree[2 * p],
                self.tree[2 * p + 1],
            )
            p //= 2

    def query(self, left, right):
        self._check_range(left, right)

        l = self.base + left
        r = self.base + right
        left_acc = self.identity
        right_acc = self.identity

        while l < r:
            if l % 2 == 1:
                # Lấy nút ở biên TRÁI, nối vào cuối phần trái.
                left_acc = self.combine(left_acc, self.tree[l])
                l += 1

            if r % 2 == 1:
                # Ranh phải là nửa mở: lùi trước khi lấy nút.
                r -= 1
                # Nút mới lấy ở bên TRÁI phần phải đã tích lũy.
                right_acc = self.combine(
                    self.tree[r], right_acc
                )

            l //= 2
            r //= 2

        return self.combine(left_acc, right_acc)
```

### 8.2. Vì sao phải có hai biến tích lũy?

Trong cách cài lặp, các nút phủ đoạn được thu thập từ **hai biên**:

- `left_acc` đi từ trái qua phải, nên gộp `combine(left_acc,tree[l])`.
- `right_acc` được tìm từ phải về trái, nhưng thứ tự dữ liệu thực vẫn phải từ trái sang phải, nên **đặt nút mới ở phía trước**: `combine(tree[r],right_acc)`.
- Cuối cùng gộp `combine(left_acc,right_acc)`.

Nếu dùng `combine(right_acc,tree[r])` khi phép gộp là nối chuỗi, thứ tự kết quả có thể bị đảo ở phần phải.

```text
Truy vấn các chữ cái ở [1,5):
left_acc  nhận "B"
right_acc có thể nhận các nhóm ở biên phải
Kết quả cuối phải là "BCDE", không phải "BEDC".
```

Hai biến tích lũy giúp cài đặt hỗ trợ **mọi monoid không giao hoán**, miễn giữ đúng thứ tự.

### 8.3. Đối chiếu hai phiên bản

```python
from operator import add

values = [-2, 5, 3, 7, 1, 4, 6, 0]
recursive = SegmentTree(values, add, 0)
iterative = IterativeSegmentTree(values, add, 0)

for left in range(len(values) + 1):
    for right in range(left, len(values) + 1):
        expected = sum(values[left:right])
        assert recursive.query(left, right) == expected
        assert iterative.query(left, right) == expected

recursive.set(3, 10)
iterative.set(3, 10)
values[3] = 10

for left in range(len(values) + 1):
    for right in range(left, len(values) + 1):
        expected = sum(values[left:right])
        assert recursive.query(left, right) == expected
        assert iterative.query(left, right) == expected

# Phép không giao hoán giúp phát hiện lỗi ghép thứ tự.
letters = ["A", "B", "C", "D", "E"]
cat = lambda a, b: a + b
concat = IterativeSegmentTree(letters, cat, "")
assert concat.query(0, 5) == "ABCDE"
assert concat.query(1, 4) == "BCD"
concat.set(2, "X")
assert concat.query(0, 5) == "ABXDE"
assert concat.query(1, 4) == "BXD"

# Khi n=0, chỉ đoạn [0,0) hợp lệ.
empty_iter = IterativeSegmentTree([], add, 0)
assert empty_iter.query(0, 0) == 0
```

**Khác biệt về bố trí:** bản đệ quy phân chia chính xác `[0,n)`, dùng mảng tối đa khoảng `4n` ô. Bản lặp dùng `base` lũy thừa hai, mảng `2·base` ô và thêm các lá identity. **Cả hai dùng O(n) bộ nhớ** khi `n≥1`.

Không có lựa chọn nào luôn nhanh hơn trên mọi runtime. Cách lặp có thể giảm overhead gọi hàm, nhưng phép gộp, kiểu dữ liệu và chi phí truy cập bộ nhớ còn quyết định tốc độ thực tế.

## 9. Chứng minh độ phức tạp và giới hạn bộ nhớ

### 9.1. Chiều cao

Mỗi lần chia một đoạn độ dài `k>1` tại trung điểm, hai cây con có kích thước gần `k/2`. Đường gốc–lá có **O(log n)** cạnh:

\[
h=\lceil\log_2 n\rceil
\quad\text{hoặc lệch tối đa hằng số theo quy ước đo chiều cao.}
\]

Khi `n=1`, gốc đồng thời là lá; chiều cao theo **số cạnh** là 0, theo **số nút** là 1. Ta dùng `O(log(n+1))` để tránh việc `log 1=0` làm nhầm với thao tác cần thời gian hằng số.

### 9.2. Số nút và bộ nhớ

Với cây đệ quy chia đến từng phần tử:

- `n` lá.
- `n−1` nút trong.
- `2n−1` nút thật.

Nếu đánh số theo cây nhị phân `v,2v,2v+1`, có thể có **lỗ trống** trong mảng chỉ số nút khi `n` không phải lũy thừa hai. Cấp phát **`4n+1` ô** là lựa chọn đơn giản và an toàn cho `n≥1`; nó vẫn là **O(n)**.

Với cây lặp:

- `base=2^{\lceil\log_2n\rceil}` cho `n≥1`, nên `n≤base<2n` trừ trường hợp `n=1` mà bất đẳng thức chặt vẫn đúng `1<2`.
- Mảng cây có `2·base<4n` ô; phần đệm identity làm cây cân đối hoàn toàn.
- Khi `n=0`, ví dụ dùng `base=1` và 2 ô đệm, vẫn là O(1) bộ nhớ.

### 9.3. Bảng chi phí tổng kết

| Thao tác | Cây đoạn | Giải thích |
| --- | --- | --- |
| Xây từ n giá trị | Θ(n) | Mỗi nút thật tính một lần |
| Gán điểm | O(log(n+1)) | Một đường từ lá tới gốc |
| Truy vấn đoạn | O(log(n+1)) | Chỉ mở rộng các vùng sát ranh giới |
| Đọc điểm từ mảng gốc phụ trợ hoặc lá trong cây lặp | O(1) | Không phải phép truy vấn đoạn |
| Duyệt mọi giá trị gốc | Θ(n) | Cần trả n phần tử |
| Bộ nhớ cây | Θ(n) | Mảng nút cộng metadata |

*Trong bảng, giả định một lần `combine` và truy cập giá trị có chi phí O(1). Cận Θ(n) về số nút áp dụng khi `n≥1`; với `n=0` mã xử lý đặc biệt và dùng O(1) bộ nhớ. Nếu giá trị tổng hợp rất lớn như chuỗi liên tục được sao chép, phải cộng chi phí xử lý payload.*

### 9.4. Tại sao cập nhật là một đường, còn truy vấn là vài nhánh?

**Cập nhật điểm** chỉ liên quan đến các nút có đoạn **chứa một chỉ số duy nhất `i`**. Tại mỗi mức tồn tại đúng một đoạn như vậy trên đường từ gốc tới lá. Do đó chỉ cần một nhánh.

**Truy vấn đoạn** có thể gồm nhiều nhánh, nhưng mỗi lần một nút nằm **trọn** trong đoạn cần hỏi, kết quả của nó đã sẵn sàng và ta dừng tại đó. Những nhánh phải chia tiếp nằm sát **hai biên** của khoảng; bởi vậy chỉ có O(1) phần mở rộng ở mỗi mức, O(log n) mức.

Nếu thay truy vấn đoạn bằng “duyệt mọi lá nằm trong khoảng”, thời gian sẽ quay về **O(k)** với `k=r-l`, không còn khai thác kết quả tóm tắt đã lưu.

## 10. Chọn giữa mảng thường, prefix sum, Fenwick và segment tree

Không có cấu trúc nào tốt nhất cho mọi loại truy vấn. Hãy xác định **loại phép gộp**, **cách cập nhật** và **tần suất thao tác** trước khi quyết định.

### 10.1. Mảng thường

Nếu mảng rất nhỏ hoặc chỉ cần rất ít truy vấn:

```python
def direct_sum(a, left, right):
    return sum(a[left:right])
```

Phép `set` là O(1). Một `range sum` dài `k` phần tử có chi phí O(k), xấu nhất O(n). Ưu điểm là đơn giản, dễ kiểm chứng, không tốn mảng cây.

### 10.2. Tổng tiền tố (prefix sum) với dữ liệu tĩnh

Đặt:

\[
P[0]=0,\qquad
P[i+1]=P[i]+A[i].
\]

Khi đó:

\[
\operatorname{sum}(l,r)=P[r]-P[l].
\]

Ví dụ `A=[4,-1,7,2]`:

```text
A = [4, -1, 7, 2]
P = [0, 4, 3, 10, 12]
sum(1,4) = P[4] - P[1] = 12 - 4 = 8
```

Xây `P` trong O(n), truy vấn tổng O(1), nhưng sau thay `A[1]`, mọi tổng tiền tố từ `P[2]` đến `P[n]` có thể phải cập nhật, O(n) trong cách xây đơn giản.

Do đó, nếu **dữ liệu bất biến**, prefix sum thường đáng ưu tiên trước segment tree cho bài toán tổng.

### 10.3. Fenwick tree (Binary Indexed Tree)

Với **tổng đoạn**, Fenwick tree hỗ trợ:

- Cộng `delta` tại một điểm: O(log n).
- Lấy tổng tiền tố: O(log n).
- Tổng `[l,r)`: `prefix(r)-prefix(l)`, O(log n).

Nếu cần **gán** `A[i]=new` thay vì cộng delta, có thể giữ `old=A[i]` và cập nhật Fenwick bằng `delta=new-old`.

Fenwick có thể gọn hơn segment tree cho những bài toán **tổng và các phép tương tự có cấu trúc phù hợp**. Tuy nhiên, công thức lấy tổng đoạn bằng **hiệu hai prefix** dựa trên việc có thể loại bỏ đóng góp của phần trước. Với **min** hoặc **gcd**, không thể chỉ lấy hiệu hai kết quả prefix để nhận kết quả đoạn:

```text
min(A[0:r]) và min(A[0:l]) không đủ để suy
min(A[l:r]) bằng một phép "trừ" tương tự tổng.
```

Fenwick có các biến thể cho những bài toán đặc biệt khác, nhưng không nên mặc định rằng **một Fenwick tổng chuẩn** thay thế được mọi loại segment tree.

### 10.4. Segment tree

Phù hợp khi:

- Có **truy vấn đoạn tổng/min/max/gcd** trên dữ liệu thay đổi.
- Phải gán lại **bất kỳ vị trí nào** và cập nhật kết quả đoạn nhanh.
- Muốn kết hợp **nhiều thông tin** trên một đoạn, ví dụ `(sum,min,max)`.
- Phép gộp có tính kết hợp nhưng **không có phép nghịch đảo prefix đơn giản**, hoặc không giao hoán.

Đánh đổi là **O(n) bộ nhớ cho cây**, chi phí cài đặt lớn hơn và có nhiều lỗi chỉ số/ràng buộc cần kiểm thử.

### 10.5. Bảng quyết định

| Yêu cầu chính | Phương án đáng thử trước | Lý do |
| --- | --- | --- |
| Vài truy vấn trên mảng nhỏ | Mảng thường | Trực tiếp, ít trạng thái |
| Rất nhiều truy vấn tổng, **không cập nhật** | Prefix sum | O(1) mỗi truy vấn sau O(n) xây |
| Tổng đoạn + cộng điểm thường xuyên | Fenwick tree | O(log n) mỗi thao tác, cài đặt gọn |
| Tổng/min/max/gcd + **gán điểm** | Segment tree | Phép gộp ở nút, O(log n) cập nhật/truy vấn |
| Truy vấn một đoạn theo **phép kết hợp có thứ tự** | Segment tree giữ thứ tự trái–phải | Không cần giả thiết giao hoán |
| Cập nhật **cả một đoạn** thường xuyên | Segment tree có lazy propagation hoặc cấu trúc chuyên dụng | Cây đoạn **chỉ có set điểm** của bài này chưa đủ |
| Chỉ cần toàn bộ min/max, ít thay đổi | Một biến thống kê hoặc cách đơn giản hơn | Tránh xây cây nếu chức năng không yêu cầu |

## 11. Giới hạn của bài toán và các mở rộng

### 11.1. Cập nhật điểm khác cập nhật đoạn

Bài đang triển khai **point assignment**:

```text
set(3, 10)
```

Không phải cập nhật đoạn:

```text
add_range(2, 7, 5)   # cộng 5 vào mọi A[i] với 2 <= i < 7
```

Nếu gọi `set` cho từng vị trí trong `[l,r)`, chi phí là **O((r-l) log n)**. Để cập nhật cả đoạn với O(log n) trong những bài toán phù hợp, ta thường học **lazy propagation**: trì hoãn một phần cập nhật ở nút và đẩy xuống khi cần.

**Không thể** tự thêm một biến `lazy` tùy tiện cho mọi `combine`: quy tắc áp cập nhật lên kết quả gộp và quy tắc kết hợp các thao tác trì hoãn phải được thiết kế nhất quán. Ví dụ “cộng `d` vào cả đoạn” làm **sum** tăng `d·length`, còn **min** tăng `d`.

### 11.2. Truy vấn tổng hợp nhiều chỉ số

Nếu cần trả cả tổng và giá trị nhỏ nhất, mỗi nút có thể chứa:

```text
node_value = (sum_of_segment, min_of_segment)
```

Phép gộp:

```python
def combine_sum_min(a, b):
    return (a[0] + b[0], min(a[1], b[1]))

def to_pair(x):
    return (x, x)

values = [5, -2, 7, 1]
pairs = [to_pair(x) for x in values]
tree = SegmentTree(
    pairs,
    combine=combine_sum_min,
    identity=(0, float("inf")),
)

assert tree.query(1, 4) == (6, -2)
tree.set(2, to_pair(3))
assert tree.query(0, 4) == (7, -2)
assert tree.validate()
```

**Vì sao phải chuyển mỗi lá thành cặp?** `combine_sum_min` mong hai đối số là `(sum,min)`, không phải một số nguyên đơn. Cách biểu diễn của lá phải nhất quán với nút trong.

### 11.3. Tìm vị trí đầu tiên thỏa điều kiện

Một segment tree tổng các giá trị **không âm** còn có thể hỗ trợ tìm vị trí mà **tổng tiền tố đầu tiên đạt một ngưỡng** bằng cách đi xuống theo tổng con trái. Nhưng nếu phần tử có thể âm, các tổng tiền tố không còn đơn điệu nên chiến lược đó **không đúng** trong trường hợp tổng quát.

Đây là một bài toán **tìm kiếm trên cây tóm tắt**, không phải `query(l,r)` trực tiếp. Khi dùng cần chứng minh điều kiện đơn điệu và định nghĩa rõ ngưỡng, nhất là khi tổng bằng 0 hoặc dữ liệu rỗng.

### 11.4. Chỉ số thưa hoặc miền rất lớn

Ví dụ mảng có `n=10^9` vị trí nhưng chỉ một số ít vị trí có dữ liệu. Cấp phát `4n` ô thường không thực tế. Có thể cân nhắc:

- **Nén tọa độ (coordinate compression)** nếu biết trước những chỉ số xuất hiện. Ánh xạ tọa độ sang vị trí 0..m−1, nhưng cần xét ý nghĩa khoảng khi tọa độ không liên tiếp.
- **Cây đoạn động (dynamic/sparse segment tree)** chỉ cấp phát nút khi cần.
- Cấu trúc khác như bản đồ/treap có tăng cường thống kê nếu mô hình truy vấn thích hợp.

Những cấu trúc này vẫn dựa trên bất biến đoạn, nhưng cách lưu trữ, chi phí cấp phát và cách xử lý tọa độ **khác** mã `SegmentTree` cố định ở mục 7.

### 11.5. Dữ liệu nhiều chiều

Segment tree trong bài quản lý **một trục chỉ số**. Với truy vấn hình chữ nhật hai chiều, không thể lấy trực tiếp `query(l,r)` trên mảng một chiều rồi coi là truy vấn chữ nhật.

Có các biến thể cây đoạn 2D hoặc tổ hợp nhiều cấu trúc, thường đánh đổi **bộ nhớ và hệ số logarit** lớn hơn. Chỉ triển khai khi yêu cầu thực tế cần truy vấn hai chiều.

## 12. Ứng dụng trong nền tảng học cấu trúc dữ liệu

Một hệ thống học có thể theo dõi số bài được hoàn thành hoặc thời lượng học theo ngày. Ví dụ:

```text
day_index:       0   1   2   3   4   5   6   7
minutes_studied: 45  20  60  30  15  90  25  40
```

Khi người học điều chỉnh một bản ghi ngày, ứng dụng gọi `set(day_index,new_minutes)`. Khi muốn xem tổng phút học trong các ngày `[2,6)`, ứng dụng gọi `query(2,6)`. Với cây tổng:

\[
\operatorname{sum}(2,6)=60+30+15+90=195.
\]

Nếu ngày thứ 3 được sửa từ 30 thành 50 phút, tổng đoạn mới là `215`.

### 12.1. Đừng nhầm chỉ số với ID bài học

Segment tree dùng **đoạn vị trí liên tiếp**, không tìm trực tiếp theo khóa `lesson_id`. Nếu dữ liệu theo ID rời rạc, hệ thống cần một **ánh xạ ID sang vị trí** hoặc một trục thứ tự rõ ràng trước khi dùng cây đoạn.

Ví dụ với chỉ mục theo ngày, `day_index` là vị trí hợp lệ. Với một tập bài có ID dạng chuỗi, phải sắp xếp/ánh xạ theo quy tắc nghiệp vụ nếu muốn định nghĩa “đoạn các bài”.

### 12.2. Nhiều chỉ mục phải được cập nhật nhất quán

Nếu cùng lúc duy trì:

- Mảng dữ liệu nguồn theo ngày.
- Cây tổng `total_minutes`.
- Cây min `min_minutes`.
- Bảng băm theo ID bản ghi.

Thay đổi một ngày phải cập nhật đúng tất cả chỉ mục bị ảnh hưởng. Cây đoạn chỉ duy trì bất biến **bên trong bản thân nó**; không tự cung cấp giao dịch nguyên tử giữa nhiều cấu trúc.

### 12.3. Truy vấn trực tuyến và snapshot

Khi một yêu cầu đang đọc cây trong lúc một luồng khác sửa dữ liệu, có thể nhìn thấy **trạng thái chưa nhất quán** nếu không đồng bộ; điều này đúng với cả cây đoạn dù không dùng con trỏ nút phức tạp.

Cần xác định:

- Truy vấn có cần thấy một **ảnh chụp nhất quán** tại một thời điểm không?
- Có thể khóa hoặc dùng cơ chế phiên bản không?
- Một yêu cầu có được đọc giá trị mới ngay khi cập nhật hoàn tất không?
- Khi truy vấn chạy song song với cập nhật, có cần tuyến tính hóa (linearizability) hay chỉ nhất quán cuối cùng?

Mã Python của bài là **thuật toán tuần tự**, không có cơ chế đồng thời. Không suy “đọc O(log n)” nghĩa là “đọc an toàn giữa lúc ghi”.

## 13. Bộ kiểm thử đối chiếu với cách tính trực tiếp

Một lỗi segment tree có thể **chỉ xuất hiện sau một số lần cập nhật** hoặc khi `n` không phải lũy thừa hai. Vì vậy đừng chỉ kiểm một truy vấn ngay sau khi build.

### 13.1. Bộ kiểm thử với seed cố định

Mã sau là **bài thực hành để người học tự chạy**, không phải kết quả đã thực thi trong quá trình viết tài liệu. Nó đối chiếu cả cây đệ quy và cây lặp với phương án “tính trực tiếp từ mảng”.

```python
from operator import add
from random import Random

rng = Random(2026)

for n in [0, 1, 2, 3, 5, 8, 13, 31]:
    reference = [rng.randint(-20, 20) for _ in range(n)]
    recursive = SegmentTree(reference, add, 0)
    iterative = IterativeSegmentTree(reference, add, 0)

    for round_number in range(20):
        # Đối chiếu mọi đoạn hợp lệ, kể cả đoạn rỗng.
        for left in range(n + 1):
            for right in range(left, n + 1):
                expected = sum(reference[left:right])
                assert recursive.query(left, right) == expected
                assert iterative.query(left, right) == expected

        # Gán một vị trí ngẫu nhiên rồi lại hỏi mọi đoạn.
        if n > 0:
            index = rng.randrange(n)
            new_value = rng.randint(-50, 50)
            reference[index] = new_value
            recursive.set(index, new_value)
            iterative.set(index, new_value)
            assert recursive.get(index) == new_value
            assert iterative.get(index) == new_value

        assert recursive.validate()

    assert recursive.to_list() == reference
```

**Tại sao có cả `n=0` và `n=1`?** Vì mã thường có lỗi khi build hoặc query không còn nút con. **Tại sao có `n=5,13,31`?** Vì các độ dài không phải lũy thừa hai giúp phát hiện lỗi khoảng chia và phần đệm.

**Tại sao có số âm?** Vì nếu đơn vị hoặc phép gộp sai, ví dụ dùng `0` làm identity cho phép `max` trên toàn số âm, kết quả có thể sai một cách rõ ràng.

### 13.2. Kiểm riêng phép gộp không giao hoán

Đối chiếu phép nối chuỗi là cách dễ phát hiện lỗi thứ tự trong cây lặp:

```python
for n in [0, 1, 2, 5, 9]:
    chars = [chr(ord("A") + i) for i in range(n)]
    slow = SegmentTree(chars, lambda a, b: a + b, "")
    fast = IterativeSegmentTree(chars, lambda a, b: a + b, "")

    for left in range(n + 1):
        for right in range(left, n + 1):
            expected = "".join(chars[left:right])
            assert slow.query(left, right) == expected
            assert fast.query(left, right) == expected

    if n > 0:
        slow.set(n - 1, "!")
        fast.set(n - 1, "!")
        chars[-1] = "!"
        assert slow.query(0, n) == "".join(chars)
        assert fast.query(0, n) == "".join(chars)
```

Nếu đổi thứ tự gộp của `right_acc` trong mã lặp, nhiều test tổng vẫn qua vì cộng có tính giao hoán, nhưng test ghép chuỗi có thể phát hiện lỗi.

### 13.3. Kiểm cập nhật tại các biên

Nên có những ca kiểm riêng:

- Chỉ số đầu `0`.
- Chỉ số cuối `n-1`.
- Gán lại **đúng giá trị cũ**.
- Gán `0`, giá trị âm, giá trị cực lớn trong miền cho phép.
- Cập nhật **cùng một điểm liên tiếp**.
- Xen kẽ cập nhật ở hai nhánh trái/phải.
- Hỏi `[0,n)` sau mỗi cập nhật.
- Hỏi `[i,i+1)` để xác minh lá.
- Hỏi đoạn rỗng tại `l=0`, `l=n` và vị trí bất kỳ.
- Truy vấn với `l<0`, `r>n`, `l>r`, chỉ số không phải int để chắc chắn API báo lỗi.

### 13.4. Khóa khởi tạo và cập nhật không được dùng chung một oracle sai

Nếu đồng thời cập nhật **cả bản mảng tham chiếu và cây** bằng một phép tính sai giống nhau, so sánh có thể vẫn “đúng” nhưng không phản ánh hợp đồng. Hãy viết rõ:

```text
set(i, x) nghĩa là A[i] = x, không phải A[i] += x.
query(l, r) nghĩa là gộp A[l],...,A[r-1].
```

Dùng `sum(reference[left:right])` làm oracle cho **sum** và công thức toán học độc lập cho những phép gộp khác. Khi kiểm min/max trên đoạn rỗng, oracle phải trả **identity đã chọn**, không gọi `min([])` hay `max([])` vì Python sẽ báo lỗi.

## 14. Những sai lầm thường gặp

### 14.1. Sai ranh giới đoạn

- **“`[l,r)` chứa cả phần tử `r`.”** Sai: `r` là đầu mút không bao gồm.
- **“Có thể gọi `query(0,n-1)` để hỏi cả mảng.”** Với nửa mở, đúng phải là `query(0,n)`.
- **“Đoạn `[i,i)` có một phần tử.”** Sai: đó là đoạn rỗng, trả identity.
- **“`[n,n)` không hợp lệ.”** Sai: là đoạn rỗng hợp lệ nếu `n` là độ dài mảng.
- **“`query(l,r)` ngoài miền nên tự cắt về miền hợp lệ.”** Không theo hợp đồng bài này: phải báo lỗi, tránh che dấu sai chỉ số.
- **“Con trái `[L,M]` và con phải `[M,R)`.”** Không nhất quán với nửa mở; phải dùng `[L,M)` và `[M,R)`.
- **“Giao nhau khi `qr==L`.”** Sai: hai đoạn chỉ chạm biên nhưng không chứa phần tử chung.

### 14.2. Sai bất biến tổng hợp

- **“Lá có thể lưu tùy ý miễn gốc đúng.”** Sai: mỗi lá phải đại diện đúng `A[i]` để cập nhật và các truy vấn nhỏ đúng.
- **“Chỉ cần sửa lá sau cập nhật điểm.”** Sai: phải tính lại mọi nút trên đường tới gốc.
- **“Có thể sửa cả hai nhánh khi cập nhật một điểm.”** Đó là công việc thừa; chỉ một nhánh chứa chỉ số cần được đi xuống.
- **“`tree[5]` là `A[5]`.”** Sai với mảng nút cây đệ quy; đây là hai không gian chỉ số khác nhau.
- **“Phép gộp nào cũng dùng được.”** Sai nếu không kết hợp hoặc không có identity phù hợp với cách xử lý không giao.
- **“Phải giao hoán thì mới dùng segment tree.”** Sai: nối chuỗi hoặc nhân ma trận theo thứ tự là ví dụ kết hợp **không giao hoán**.
- **“Có thể đảo thứ tự `left_result` và `right_result`.”** Sai với phép gộp không giao hoán.
- **“Đoạn không giao luôn trả 0.”** Chỉ đúng cho **tổng** (và các phép có identity 0), không đúng cho `min` hoặc `max`.
- **“Có thể dùng 0 làm identity của max mọi số.”** Sai khi tất cả giá trị âm: kết quả có thể bị kéo thành 0.

### 14.3. Sai đánh giá độ phức tạp

- **“Build O(n log n) vì cây cao log n.”** Không đúng với build từ các lá: mỗi nút thật xử lý một lần, O(n).
- **“Truy vấn có thể rẽ hai nhánh nên O(n).”** Sai với thuật toán dừng ở nút phủ trọn; chỉ có O(log n) nút cần xử lý theo ranh giới.
- **“Mọi truy vấn O(1) vì gốc lưu tổng cả mảng.”** Sai cho đoạn tùy ý; chỉ `[0,n)` có thể trả ngay gốc.
- **“Cập nhật điểm O(1) vì chỉ sửa một giá trị.”** Sai: cần cập nhật O(log n) tổ tiên.
- **“Gọi set cho mỗi điểm trong đoạn dài k vẫn O(log n).”** Sai: tổng thường O(k log n).
- **“Có O(log n) phép combine thì chuỗi nối dài chắc chắn O(log n) thời gian.”** Sai nếu mỗi phép nối phải sao chép nhiều ký tự.
- **“Cấp phát `4n` ô có nghĩa cây có 4n nút thật.”** Sai: cây phân hoạch có `2n−1` nút thật; mảng cấp phát có thể có ô trống.
- **“Dùng segment tree luôn tốt hơn prefix sum.”** Sai khi dữ liệu tĩnh và chỉ hỏi tổng: prefix sum cho O(1) truy vấn.

### 14.4. Sai về hợp đồng cập nhật và dữ liệu

- **“`set(i,x)` và `add(i,x)` tương đương.”** Sai: một bên gán, một bên cộng thêm.
- **“Tôi có thể sửa trực tiếp một list lưu ở lá mà không cập nhật cây.”** Có nguy cơ phá bất biến vì nút trong không được tính lại.
- **“Đã có một cây sum thì lấy ngay được min đoạn.”** Sai: các nút lưu tóm tắt tổng, không có thông tin min.
- **“Muốn cập nhật cả đoạn, cứ thêm trường lazy là đủ.”** Chưa đủ: phải chứng minh tác động của cập nhật lên mỗi loại giá trị tổng hợp.
- **“Dữ liệu có chỉ số rời rạc nên cứ lấy ID làm vị trí mảng.”** Chưa chắc: có thể cần nén/ánh xạ tọa độ.
- **“Đọc và cập nhật đồng thời trên một cây Python không khóa luôn an toàn.”** Không có bảo đảm như vậy từ thuật toán tuần tự.
- **“Kiểm thử `validate` O(n) không ảnh hưởng benchmark O(log n).”** Sai nếu tính `validate` vào mỗi phép đo.

## 15. Checklist cài đặt đúng

Trước khi đánh dấu một cài đặt segment tree hoàn chỉnh:

1. Đã định nghĩa rõ đoạn là **`[l,r)`** hay **`[l,r]`** chưa?
2. `combine` có **tính kết hợp** không?
3. `identity` có thỏa cả **`combine(e,x)=x` và `combine(x,e)=x`** không?
4. Phép gộp có **thứ tự trái–phải** đúng khi nó không giao hoán không?
5. Build có dừng đúng ở `R-L=1` và không gọi build cho đoạn rỗng không?
6. Với `n=0`, code có xử lý riêng không?
7. Cập nhật điểm đi **đúng một nhánh** tại mỗi mức không?
8. Sau cập nhật, mọi nút tổ tiên đã được **gộp lại** chưa?
9. Query có phân biệt **không giao, phủ trọn, giao một phần** không?
10. API có từ chối chỉ số âm, `l>r` và `r>n` không?
11. Đoạn rỗng trả **identity** phù hợp không?
12. `n` không phải lũy thừa hai có đúng không?
13. Mã lặp có gộp **`right_acc` theo thứ tự đúng** không?
14. Có kiểm với dữ liệu âm, khóa/giá trị lớn, nhiều lần cập nhật và phép nối không giao hoán không?
15. Có loại chi phí `validate`/in log khỏi benchmark thao tác lõi không?
16. Nếu có cập nhật từ nhiều luồng, đã xác định **đồng bộ/phiên bản** chưa?

## 16. Bài tập vận dụng

### Bài 1 — Đọc đúng đoạn nửa mở

Cho `A=[4,-1,7,2,5]`. Tính tổng `[1,4)`, `[0,5)` và `[3,3)`.

*Gợi ý:* Lần lượt `-1+7+2=8`, `17` và `0`. `r` không được tính vào đoạn.

### Bài 2 — Vẽ cây phân hoạch

Với `A=[4,-1,7,2]`, hãy vẽ cây quản lý `[0,4)`, chỉ rõ các nút `[0,2)`, `[2,4)` và bốn lá.

*Gợi ý:* Lá lưu `4,-1,7,2`; hai nút cha lưu `3,9` và gốc lưu `12`.

### Bài 3 — Đếm số nút thật

Một cây đoạn xây tới từng lá cho `n=11` phần tử có bao nhiêu lá, nút trong và nút thật? Vì sao không phải có chính xác `4n` nút thật?

*Gợi ý:* `n` lá, `n-1` nút trong, tổng `2n-1=21`; `4n` chỉ là cách cấp phát mảng an toàn.

### Bài 4 — Xây cây khi n không phải lũy thừa hai

Vẽ cấu trúc các đoạn của cây với `n=5`, dùng `M=(L+R)//2`. Có lá nào quản lý nhiều hơn một phần tử không?

*Gợi ý:* Các lá luôn là `[i,i+1)`; nhánh trái/phải có thể có độ sâu khác nhau.

### Bài 5 — Chứng minh xây cây O(n)

Giải thích vì sao thời gian `build` là Θ(n) nếu phép gộp O(1), mặc dù cây có O(log n) mức.

*Gợi ý:* Mỗi nút thật được xử lý đúng một lần, tổng `2n−1` nút.

### Bài 6 — Cập nhật điểm và đường đi

Với `A=[-2,5,3,7,1,4,6,0]`, gán `A[3]=10`. Hãy liệt kê các đoạn nút cần tính lại và tổng mới tại từng nút.

*Gợi ý:* `[3,4):10`, `[2,4):13`, `[0,4):16`, `[0,8):27`.

### Bài 7 — Gán so với cộng thêm

Ban đầu `A[3]=7`. So sánh kết quả của `set(3,10)` với `add(3,10)`. Tại sao không dùng chung tên `update` nếu chưa mô tả hợp đồng?

*Gợi ý:* Gán cho `10`, cộng thêm cho `17`; hai hành vi khác nhau.

### Bài 8 — Truy vết truy vấn đoạn

Với cây ở mục 2, truy vấn `[2,6)`. Nêu chính xác các nút **phủ hoàn toàn** được dùng để trả kết quả; có phải thăm từng lá không?

*Gợi ý:* Dùng `[2,4)` và `[4,6)`, trả `10+5=15`; không mở rộng các nút đã phủ trọn.

### Bài 9 — Ba trường hợp giao đoạn

Nút `v` quản lý `[4,8)` trong một cây có ít nhất 8 phần tử. Với các truy vấn `[0,4)`, `[3,8)` và `[5,7)`, hãy phân loại **không giao / phủ hoàn toàn / giao một phần**.

*Gợi ý:* Lần lượt **không giao**, **phủ hoàn toàn**, **giao một phần**.

### Bài 10 — Các biên của đoạn rỗng

Với `n=8`, `query(0,0)`, `query(8,8)`, `query(0,8)`, `query(8,9)` khác nhau như thế nào?

*Gợi ý:* Hai truy vấn đầu là đoạn rỗng hợp lệ; truy vấn thứ ba là cả mảng; `[8,9)` ngoài miền.

### Bài 11 — Định nghĩa identity

Hãy nêu identity tương ứng cho **sum**, **product**, **min**, **max**, **gcd**. Giải thích vì sao `0` không phải identity của `max` trên các số âm.

*Gợi ý:* `0,1,+∞,−∞,0`; `max(−5,0)=0` không giữ `−5`.

### Bài 12 — Phép gộp kết hợp nhưng không giao hoán

Cho `A=["A","B","C","D","E"]`, phép gộp là nối chuỗi. Kết quả `query(1,4)` là gì? Nếu đảo thứ tự con phải/trái, có thể sai thế nào?

*Gợi ý:* `"BCD"`, không phải chuỗi có thứ tự đảo.

### Bài 13 — Kiểm tra phép trừ

Hãy tính `(10−3)−2` và `10−(3−2)`. Tại sao phép trừ trực tiếp không dùng được như `combine` của cây đoạn chuẩn?

*Gợi ý:* Kết quả `5` và `9` khác nhau, vi phạm tính kết hợp.

### Bài 14 — Query O(log n) có luôn đúng về CPU không?

Nếu mỗi nút lưu một chuỗi rất dài và `combine(a,b)=a+b` sao chép toàn bộ ký tự, tại sao không thể chỉ đếm số nút để kết luận toàn thao tác mất O(log n) thời gian?

*Gợi ý:* Cần tính chi phí **tạo kết quả gộp**, có thể tỉ lệ độ dài payload.

### Bài 15 — Đoạn min và max

Cho `A=[-7,-2,-11,-4]`. Hãy chọn identity đúng để xây cây `min` và `max`, rồi tính kết quả của đoạn `[1,4)`.

*Gợi ý:* `min` dùng `+∞` cho đoạn rỗng, trả `−11`; `max` dùng `−∞`, trả `−2`.

### Bài 16 — GCD có identity 0

Với `A=[18,24,30,42]`, hãy tính `gcd([1,4))`. Nếu gán `A[2]=9`, giá trị mới của truy vấn là gì?

*Gợi ý:* `gcd(24,30,42)=6`; sau cập nhật `gcd(24,9,42)=3`.

### Bài 17 — Chỉ số mảng cây

Trong cách đánh số `v,2v,2v+1`, giải thích sự khác nhau giữa `v=5` và phần tử `A[5]`. Với cây tám phần tử ở mục 2, nút `v=5` quản lý đoạn nào?

*Gợi ý:* `v` là vị trí lưu **nút**, còn `A[5]` là vị trí dữ liệu; `v=5` quản lý `[2,4)`.

### Bài 18 — Cập nhật một điểm trong cây lặp

Cho `n=5`, `base=8`. Lá của `A[3]` nằm tại vị trí `tree` nào? Sau gán mới, dãy vị trí cha được cập nhật theo phép chia hai ra sao?

*Gợi ý:* Lá ở `base+3=11`; các nút cha lần lượt `5,2,1`.

### Bài 19 — Hai biến tích lũy ở query lặp

Vì sao `left_acc` gộp `combine(left_acc,tree[l])` nhưng `right_acc` gộp `combine(tree[r],right_acc)`? Cho một phản ví dụ nếu dùng thứ tự ngược với nối chuỗi.

*Gợi ý:* Các nút biên phải được lấy theo thứ tự **từ phải sang trái**, nên nút mới phải đặt trước phần đã gom.

### Bài 20 — Chọn giữa prefix sum và segment tree

Một bộ báo cáo chỉ có `n=100000` giá trị bất biến, nhận hàng triệu truy vấn tổng đoạn và không cập nhật. Bạn chọn cấu trúc nào trước? Nếu mỗi phút có hàng trăm lượt gán điểm, quyết định thay đổi thế nào?

*Gợi ý:* Dữ liệu tĩnh: prefix sum O(1) mỗi truy vấn. Có cập nhật điểm: segment tree hoặc Fenwick cần được đánh giá.

### Bài 21 — Fenwick và min

Tại sao công thức `prefix(r)-prefix(l)` phù hợp với sum nhưng không dùng tương tự để tính min đoạn bằng `min_prefix(r)` và `min_prefix(l)`?

*Gợi ý:* Phép min không có phép “trừ đóng góp tiền tố” như cộng trên số.

### Bài 22 — Cây đoạn tổng hợp `(sum,min)`

Thiết kế giá trị lá, identity và phép `combine` để một cây trả cùng lúc **tổng** và **min**. Với `A=[5,-2,7,1]`, kết quả trên `[1,4)` là gì?

*Gợi ý:* Lá `(x,x)`; identity `(0,+∞)`; kết quả `(6,−2)`.

### Bài 23 — Tại sao không thể tự thêm lazy tùy ý?

Nếu cộng `d` vào tất cả `k` phần tử của một đoạn, giá trị **sum** và **min** của đoạn thay đổi như thế nào? Vì sao đây là hai công thức khác nhau?

*Gợi ý:* Sum tăng `k·d`, min tăng `d`; quy tắc lazy phải phụ thuộc metadata.

### Bài 24 — Nén tọa độ

Chỉ có ba vị trí có dữ liệu ở những chỉ số `10`, `1000` và `1000000`. Khi nào có thể ánh xạ chúng sang `0,1,2`? Điều gì cần giữ khi một truy vấn hỏi khoảng tọa độ gốc?

*Gợi ý:* Dùng nén tọa độ nếu biết tập vị trí; phải ánh xạ **cả biên truy vấn** cho đúng ý nghĩa thứ tự và khoảng.

### Bài 25 — Tổng tiền tố đạt ngưỡng

Tại sao tìm vị trí đầu tiên có tổng tiền tố đạt `X` bằng cách dựa vào tổng cây con trái thường yêu cầu các phần tử không âm? Nêu một ví dụ có phần tử âm làm tổng tiền tố không đơn điệu.

*Gợi ý:* `[5,-10,8]` có tổng tiền tố `5,-5,3`, không tăng đều.

### Bài 26 — Kiểm thử mảng rỗng và một phần tử

Đặt hợp đồng cho `SegmentTree([],sum,0)` và `SegmentTree([7],sum,0)` đối với `query(0,0)`, `query(0,1)` và `set(0,10)`.

*Gợi ý:* Mảng rỗng chỉ cho `query(0,0)=0`; `query(0,1)` và `set(0,10)` lỗi. Mảng một phần tử cho `query(0,1)=7` rồi `10` sau set.

### Bài 27 — Tìm lỗi trong bộ mã cập nhật

Một lập trình viên đã sửa lá nhưng bỏ dòng `tree[v]=combine(tree[2v],tree[2v+1])` khi trở về. Viết hai truy vấn có thể cho kết quả mâu thuẫn sau cập nhật `A[3]` từ 7 thành 10.

*Gợi ý:* `query(3,4)` có thể trả `10` nhưng `query(0,8)` vẫn giữ tổng cũ `24`, lẽ ra `27`.

### Bài 28 — Phân tích số phép gộp

Vì sao một lần `set(i,x)` dùng O(log n) phép `combine` và một lần `query(l,r)` chỉ cần O(log n) nút phân hoạch, dù đoạn hỏi có thể chứa gần `n` phần tử?

*Gợi ý:* Cập nhật theo **một đường gốc–lá**; truy vấn dừng ở các nút phủ trọn và chỉ mở rộng quanh **hai biên**.

### Bài 29 — Đánh giá benchmark

Một thí nghiệm gọi `validate()` sau **mỗi** lần `set`, rồi kết luận “cập nhật cây đoạn O(n)”. Có vấn đề gì với phương pháp đo?

*Gợi ý:* `validate()` duyệt toàn cây O(n) và không thuộc thao tác lõi `set` O(log n).

### Bài 30 — Thiết kế chỉ mục học tập

Ứng dụng ghi số phút học mỗi ngày, đồng thời cần tổng theo tuần và min/max theo các khoảng thời gian. Bạn sẽ dùng một cây có dữ liệu tổng hợp hay nhiều cây? Những thay đổi nào phải được cập nhật đồng bộ?

*Gợi ý:* Một nút `(sum,min,max)` với phép gộp kết hợp có thể đủ; hoặc dùng nhiều cây riêng. Mỗi lần sửa một ngày phải cập nhật tất cả metadata/đồ thị trạng thái liên quan nhất quán.

## 17. Tổng kết

**Cây đoạn (segment tree)** lưu kết quả gộp của các **đoạn chỉ số liên tiếp**. Mỗi nút quản lý `[L,R)`; hai con quản lý `[L,M)` và `[M,R)`; lá là một phần tử; nút trong lưu `combine(left,right)`. Nếu phép gộp **kết hợp** và có **phần tử đơn vị hai phía**, thuật toán truy vấn có thể trả identity cho phần không giao, dùng ngay giá trị nút phủ trọn và gộp các nhánh giao một phần theo đúng thứ tự.

Ba thao tác nền tảng có chi phí:

- **Xây cây:** Θ(n), do có `2n−1` nút thật cho `n≥1` và mỗi nút được xử lý một lần.
- **Gán lại một điểm:** O(log(n+1)), chỉ cần sửa lá chứa chỉ số đó và các tổ tiên của nó.
- **Truy vấn `[l,r)`:** O(log(n+1)), nhờ gộp từ các nút phủ hoàn toàn và chỉ tiếp tục chia gần hai ranh giới truy vấn.
- **Bộ nhớ cây:** O(n), với mảng cấp phát khoảng `4n` ô hoặc phiên bản lặp có lá đệm identity.

Các cận thời gian trên giả định mỗi phép gộp tốn O(1); dữ liệu tổng hợp lớn có thể làm chi phí thực tế cao hơn. Cần phân biệt **gán điểm** với **cộng thêm delta**, **đoạn nửa mở** với đoạn đóng, và **point update** với **range update có lazy propagation**.

Khi bài toán chỉ có tổng đoạn trên dữ liệu tĩnh, **prefix sum** thường đơn giản và cho truy vấn O(1); khi chỉ cần tổng với cập nhật điểm, **Fenwick** cũng rất đáng cân nhắc. Segment tree có giá trị khi cần **cập nhật và truy vấn nhiều loại kết quả đoạn**, kể cả phép gộp kết hợp nhưng không giao hoán. Để dùng đúng trong hệ thống thực, hãy kiểm tra **bất biến, ranh giới, identity, thứ tự kết hợp, xử lý mảng rỗng, cập nhật nhất quán và bộ kiểm thử độc lập** trước khi tối ưu.
