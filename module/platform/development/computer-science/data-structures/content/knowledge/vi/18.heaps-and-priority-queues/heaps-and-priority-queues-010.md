# Heap d-nhánh và đánh đổi chiều cao với số phép so sánh

## 1. Khi mỗi nút không chỉ có hai con

Trong **heap nhị phân** (*binary heap*), mỗi nút có tối đa hai con. Khi đưa một khóa mới vào heap, ta có thể phải đẩy khóa ấy lên qua nhiều tầng. Khi lấy phần tử ưu tiên nhất, ta lại phải đẩy khóa thay thế từ gốc xuống một đường tới lá.

Một ý tưởng tự nhiên là: **nếu mỗi nút có nhiều con hơn, cây sẽ thấp hơn**. Thay vì hai con, cho phép mỗi nút có tối đa `d` con, với `d` là một số nguyên ít nhất bằng `2`. Cấu trúc ấy được gọi là **heap d-nhánh**, **heap d-ary** (*d-ary heap*), hoặc đôi khi là *d-heap*.

```text
Heap nhị phân (d = 2):              Heap 4-nhánh (d = 4):

              1                                  1
           /     \                       /    /    \    \
          3       2                     3    2     4    5
         / \     / \                   / | \ \
        8   6   7   9                 8  6  7  9
```

Cây 4-nhánh có thể chứa nhiều phần tử hơn ở cùng số tầng. Nhưng khi **đẩy xuống**, nút hiện tại phải xác định **con có ưu tiên cao nhất trong tối đa bốn con**, thay vì chỉ so sánh hai con.

Đó là đánh đổi trung tâm của bài học:

> **Tăng `d` làm giảm chiều cao đường đi, nhưng có thể tăng số phép so sánh cần thực hiện tại mỗi tầng khi đẩy xuống.**

Ví dụ, một min-heap 4-nhánh có thể cần duyệt bốn con của gốc để chọn con nhỏ nhất. Một min-heap nhị phân chỉ cần xét tối đa hai con, nhưng có thể phải đi xuống nhiều tầng hơn.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phát biểu bất biến hình dạng và bất biến thứ tự của **min-heap/max-heap d-nhánh**.
2. Tính chính xác chỉ số cha và dãy chỉ số con trong **mảng bắt đầu từ `0`**.
3. Giải thích vì sao chiều cao giảm từ `O(\log_2 n)` xuống `O(\log_d n)`.
4. Phân tích `sift-up` với khoảng **một phép so sánh khóa mỗi tầng** và `sift-down` với **tối đa `d` phép so sánh khóa mỗi tầng**.
5. Mô phỏng thao tác thêm, lấy gốc và xây heap cho `d=4`.
6. Cài một **min-heap d-nhánh** có thể chọn `d` bằng Python.
7. Lập luận thời gian xây heap bằng `heapify` từ dưới lên và không nhầm với `n` lần chèn.
8. Chọn `d` dựa trên tần suất **decrease-key**, **push**, **pop**, đặc điểm cache và chi phí so sánh.
9. Liên hệ với hàng đợi ưu tiên có chỉ mục, thuật toán đồ thị và các trường hợp biên.

Chủ đề thuộc chương **Heap và hàng đợi ưu tiên** của học phần **Cấu trúc dữ liệu**. Cách chọn tham số `d` là một ví dụ quan trọng của việc dùng bất biến và độ phức tạp thời gian/bộ nhớ để đánh đổi giữa các cấu trúc như mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Định nghĩa: heap d-nhánh vẫn là một heap

**Heap d-nhánh** ở đây là một cây có thứ tự vị trí con, với:

- Mỗi nút có **nhiều nhất `d` con**.
- Các tầng được lấp đầy theo thứ tự; ở tầng cuối, các nút chiếm những vị trí liên tục **từ trái sang phải**.
- Một bất biến **heap-order** áp dụng trên **mọi cạnh cha–con**.

Ta giả định `d` là **số nguyên cố định trong suốt vòng đời cấu trúc**, trừ khi chủ động tổ chức lại heap. Heap nhị phân chỉ là trường hợp đặc biệt `d=2`.

### 2.1. Bất biến hình dạng: cây d-nhánh hoàn chỉnh

```text
d = 4, n = 9:

                         (0)
                /      /     \      \
              (1)    (2)    (3)     (4)
            /  |  \   \
          (5) (6) (7) (8)

Các số trong ngoặc là CHỈ SỐ theo thứ tự tầng.
```

Cây có chín nút theo hình trên là hợp lệ: sau khi lấp các vị trí con `1,2,3,4` của gốc, các nút `5,6,7,8` lấp liên tục vào các vị trí con của nút `1`. Nếu có thêm nút, nó sẽ đi vào vị trí `9` dưới nút `2`, không được bỏ qua `9` để đặt thẳng vào `10`.

Không yêu cầu mọi nút có đủ `d` con. Một nút gần cuối có thể có từ `1` tới `d-1` con. Nếu chỉ có vài con, chúng phải chiếm **những vị trí con đầu tiên** tính từ trái sang phải.

### 2.2. Bất biến thứ tự: cha so với tất cả các con

**Min-heap d-nhánh** yêu cầu:

\[
\boxed{key(parent)\le key(child)}
\]

với **mọi cạnh** từ cha đến từng con.

**Max-heap d-nhánh** yêu cầu:

\[
\boxed{key(parent)\ge key(child)}
\]

với **mọi cạnh** từ cha đến từng con.

Nhờ tính bắc cầu của quan hệ thứ tự dọc đường từ gốc xuống một nút bất kỳ:

- Min-heap có **một khóa nhỏ nhất ở gốc**.
- Max-heap có **một khóa lớn nhất ở gốc**.

Heap-order **không** bắt buộc các nút anh em được sắp tăng/giảm, và cũng không yêu cầu mảng biểu diễn heap đã được sắp hoàn toàn.

## 3. Ví dụ một min-heap 4-nhánh hợp lệ

Xét mảng `H` gồm 13 khóa:

```text
Chỉ số:  0   1  2  3   4  5  6  7   8   9  10  11  12
Giá trị:[1,  6, 4, 8, 12,10, 7, 9, 15, 13, 20, 11, 14]
```

Với `d=4`, cây tương ứng là:

```text
                                  1   [0]
                    /        /         \         \
                 6 [1]    4 [2]      8 [3]     12 [4]
              /  |  |  \  /  |  |  \
            10  7  9  15 13 20 11 14
            [5][6][7][8][9][10][11][12]
```

Kiểm tra mọi nhóm cha–con:

| Cha (chỉ số) | Các con trực tiếp (chỉ số) | Điều kiện min-heap |
|---|---|---|
| `1` (`0`) | `6`, `4`, `8`, `12` (`1–4`) | `1\le6,4,8,12` |
| `6` (`1`) | `10`, `7`, `9`, `15` (`5–8`) | `6\le10,7,9,15` |
| `4` (`2`) | `13`, `20`, `11`, `14` (`9–12`) | `4\le13,20,11,14` |

Tất cả các nút còn lại là lá, nên `H` là **min-heap 4-nhánh hợp lệ**.

Nhưng `H` **không tăng dần**: `H[1]=6` lớn hơn `H[2]=4`; nút con `20` cũng có thể đứng trước con `11`. Điều này đúng vì chỉ quan hệ **cha–con** mới bị ràng buộc.

### Vì sao không thể đổi `d` mà giữ nguyên các phép tính?

Xét mảng:

```text
[1, 10, 2, 3, 4, 11, 12]
```

- Với `d=4`, gốc `1` có các con `10,2,3,4`; nút `10` có các con `11,12`. Tất cả cạnh đều hợp lệ.
- Với `d=2`, nút `10` ở chỉ số `1` có con `3` và `4` tại các chỉ số `3` và `4`: `10>3`, `10>4`. Mảng ấy **không phải min-heap nhị phân**.

Đổi `d` nghĩa là **đổi quan hệ cha–con**, không chỉ thay một biến để thuật toán chạy nhanh hơn. Nếu muốn chuyển `d`, cần kiểm tra và thường phải **heapify lại** theo cấu trúc mới.

## 4. Công thức cha và con với chỉ số bắt đầu từ 0

Với `d\ge2`, `n` phần tử và các vị trí `0,1,\ldots,n-1`:

### Cha của nút i

Đối với `i>0`:

\[
\boxed{parent(i)=\left\lfloor\frac{i-1}{d}\right\rfloor.}
\]

Gốc `i=0` **không có cha**. Đừng đưa `i=0` vào công thức rồi dùng kết quả làm vị trí phần tử hợp lệ.

### Dãy con của nút i

Các **chỉ số con có thể có** của nút `i` là:

\[
\boxed{child(i,k)=di+k,\qquad k=1,2,\ldots,d.}
\]

Vì thế:

\[
\begin{aligned}
firstChild(i)&=di+1,\\
lastCandidateChild(i)&=di+d.
\end{aligned}
\]

Chỉ những chỉ số **nhỏ hơn `n`** mới là con thật sự tồn tại. Có thể biểu diễn nhóm con bằng khoảng nửa kín:

\[
\boxed{[\,di+1,\ \min(di+d+1,n)\,).}
\]

Khoảng này được xem là **rỗng** nếu `di+1\ge n`.

Ví dụ với `d=4`, `n=13`:

| Nút `i` | Cha | Các chỉ số con hợp lệ |
|---:|---:|---|
| `0` | Không có | `1,2,3,4` |
| `1` | `0` | `5,6,7,8` |
| `2` | `0` | `9,10,11,12` |
| `3` | `0` | Không có |
| `4` | `0` | Không có |
| `5` | `1` | Không có |

### Các nút trong và nút lá

Một nút `i` là **nút trong** nếu nó có ít nhất một con:

\[
di+1<n.
\]

Với `n\ge2`, nút cha cuối cùng nằm ở:

\[
\boxed{lastParent=\left\lfloor\frac{n-2}{d}\right\rfloor.}
\]

Những chỉ số **lớn hơn** `lastParent` là lá. Với `n=0` hoặc `n=1`, **không có nút trong**, nên cần xử lý riêng trước khi dùng công thức trên.

### Nếu tài liệu hoặc thư viện dùng chỉ số từ 1

Quy ước `1-based` cho kết quả khác. Nếu gốc ở chỉ số `1`, cha của `i\ge2` là:

\[
parent_{1}(i)=\left\lfloor\frac{i-2}{d}\right\rfloor+1.
\]

Con thứ `k` của nút `i`, với `k=1,\ldots,d`, ở:

\[
child_{1}(i,k)=d(i-1)+k+1.
\]

**Không trộn công thức 0-based và 1-based**. Các ví dụ và mã Python trong phần còn lại dùng hoàn toàn **0-based**.

## 5. Chiều cao của cây: tăng d làm giảm số tầng

Trong một cây `d`-nhánh đầy đủ tới tầng `h` (gốc ở tầng `0`), số vị trí có thể chứa là:

\[
N_{\max}(h)=1+d+d^2+\cdots+d^h
=\frac{d^{h+1}-1}{d-1}.
\]

Tổng số nút tối đa ở **các tầng trước tầng `h`** là:

\[
N_{\text{before}}(h)=\frac{d^h-1}{d-1}.
\]

Một heap hoàn chỉnh có `n` nút sẽ lấp từng tầng từ trên xuống. Do đó, tầng sâu nhất `h` là số nguyên lớn nhất sao cho:

\[
\frac{d^h-1}{d-1}\le n-1.
\]

Biến đổi cho `n\ge1`:

\[
d^h\le(d-1)(n-1)+1.
\]

Suy ra **chiều cao chính xác tính bằng số cạnh**, trong mô hình cây hoàn chỉnh:

\[
\boxed{h=\left\lfloor
\log_d\!\left((d-1)(n-1)+1\right)
\right\rfloor,\qquad n\ge1.}
\]

Nếu `n=1`, `h=0`. Với `n=0` không có cây nên không áp dụng công thức.

Về cấp độ tăng trưởng, khi `d` là hằng số ít nhất bằng `2`:

\[
\boxed{h=\Theta(\log_d n)
=\Theta\!\left(\frac{\log n}{\log d}\right)}
\]

với `n\ge2` và `n` tăng. Nếu xem `d` là **tham số có thể tăng theo `n`**, hãy dùng công thức chiều cao chính xác ở trên; một cận dễ sử dụng khi `n\ge2` là `h=O(1+\log_d n)`. Số tầng không thể nhỏ hơn một khi cây có ít nhất hai nút, ngay cả nếu `d>n`.

**Ví dụ với `n=65.536` phần tử:**

| `d` | Chiều cao `h` (cạnh) | Số tầng tối đa tính cả gốc |
|---:|---:|---:|
| `2` | `16` | `17` |
| `4` | `8` | `9` |
| `8` | `6` | `7` |
| `16` | `4` | `5` |

Đây là chiều cao của **cây hoàn chỉnh** theo số phần tử, không phải số lần hoán đổi bắt buộc của mọi thao tác. Nhiều thao tác có thể dừng ở tầng cao hơn mà không phải đi hết chiều cao.

**Đổi cơ số logarithm:**

\[
\log_d n=\frac{\ln n}{\ln d}.
\]

Khi `d` tăng, mẫu `\ln d` tăng, nên số tầng cần đi qua thường giảm. Nhưng đây mới là **một nửa** câu chuyện.

## 6. Đẩy lên: ít tầng hơn, mỗi tầng chỉ cần so với một cha

Trong min-heap, khi thêm khóa `x`:

1. Đặt `x` ở **cuối mảng**, giữ hình dạng cây hoàn chỉnh.
2. Từ chỉ số mới `i`, tính cha `p=(i-1)//d`.
3. Nếu `H[p]\le H[i]` thì dừng.
4. Nếu `H[p]>H[i]` thì đổi chỗ hai khóa, đặt `i=p` rồi lặp.

### Mã giả

```text
PUSH_DARY_MIN(H, d, x):
    require d >= 2
    append x to H
    i = length(H) - 1

    while i > 0:
        p = (i - 1) // d
        if H[p] <= H[i]:
            break
        swap(H[p], H[i])
        i = p
```

Tại mỗi tầng, chỉ cần so sánh **phần tử hiện tại với đúng một nút cha**. Không cần duyệt tất cả các nút anh em cùng cha.

Nếu chiều cao là `h`:

\[
\boxed{C_{\mathrm{up}}\le h,\qquad
T_{\mathrm{up}}=O(\log_d n)}
\]

theo số lần so sánh khóa và hoán đổi trong trường hợp xấu nhất, với `n\ge2` và `d` cố định. Nếu `d` có thể lớn hơn cả `n`, dùng cận `O(1+\log_d n)` thay thế.

Khi `d` tăng, đường đi lên ngắn hơn, nên **push**, **decrease-key trên min-heap**, và **increase-key trên max-heap** có thể hưởng lợi rõ rệt.

Đây là số bước bảo trì bất biến heap. Nếu mảng động phải cấp phát lại khi thêm cuối, một lần `append` riêng lẻ còn có thể phải dời dữ liệu; chi phí cấp phát cần được xét riêng. Thêm cuối của mảng động thường `O(1)` **khấu hao**, không phải luôn `O(1)` xấu nhất ở mọi lần.

## 7. Mô phỏng sift-up trên min-heap 4-nhánh

Dùng lại mảng min-heap 4-nhánh:

```text
H = [1, 6, 4, 8, 12, 10, 7, 9, 15, 13, 20, 11, 14]
n = 13; d = 4
```

Ta thêm khóa `0`.

### Bước 1 — thêm vào cuối

Chỉ số mới `i=13`, cha là:

\[
parent(13)=\left\lfloor\frac{13-1}{4}\right\rfloor=3.
\]

```text
[1, 6, 4, 8, 12, 10, 7, 9, 15, 13, 20, 11, 14, 0]
           ^                                     ^
         cha 8                                khóa mới
```

### Bước 2 — đổi với cha 8

`0<8` nên đổi chỉ số `13` và `3`:

```text
[1, 6, 4, 0, 12, 10, 7, 9, 15, 13, 20, 11, 14, 8]
          ^
          i=3
```

### Bước 3 — đổi tiếp với gốc 1

`parent(3)=0`, và `0<1` nên đổi:

```text
[0, 6, 4, 1, 12, 10, 7, 9, 15, 13, 20, 11, 14, 8]
 ^
 i=0: dừng
```

Khóa mới đi lên **hai tầng**, cần hai lần so sánh cha–con dẫn đến hoán đổi. Tất cả cạnh cha–con vẫn hợp lệ; mảng hoàn chỉnh vì ta đã thêm đúng vị trí cuối.

**Điểm học được:** ở mỗi lần đi lên, dù cha có bốn con, thuật toán chỉ cần biết **cha của đúng phần tử đang đẩy**, chứ không cần chọn con nhỏ nhất trong bốn anh em.

## 8. Đẩy xuống: mỗi tầng phải tìm con ưu tiên nhất

Lấy phần tử nhỏ nhất từ min-heap:

1. Lưu khóa ở gốc `H[0]` để trả về.
2. Lấy khóa **cuối mảng** chuyển lên gốc, rồi giảm độ dài.
3. Từ gốc, xác định các con đang tồn tại.
4. Chọn **con nhỏ nhất** trong các con.
5. Nếu cha `\le` con nhỏ nhất, dừng; nếu không, hoán đổi rồi tiếp tục xuống.

### Mã giả với d con

```text
SIFT_DOWN_DARY_MIN(H, d, i):
    n = length(H)

    loop:
        first = d*i + 1
        if first >= n:
            break

        end_exclusive = min(first + d, n)
        best = first

        for c = first + 1 to end_exclusive - 1:
            if H[c] < H[best]:
                best = c

        if H[i] <= H[best]:
            break

        swap(H[i], H[best])
        i = best
```

Trong một min-heap, **không được chọn tùy ý một con nhỏ hơn cha**. Nếu cha `12` có bốn con `7,9,3,6`, đổi với `7` sẽ để cha mới là `7` nhưng còn con `3` nhỏ hơn cha ấy. Chỉ chọn **con nhỏ nhất `3`** mới sửa đúng quan hệ tại tầng đang xử lý.

Với **max-heap**, chọn **con lớn nhất** và chỉ đổi nếu cha nhỏ hơn con được chọn.

### Đếm số lần so sánh ở một tầng

Nếu nút hiện tại có `k` con, với `1\le k\le d`:

- Để chọn con nhỏ nhất trong `k` con, ta thường cần `k-1` phép so sánh khóa.
- Để quyết định có đổi cha với con nhỏ nhất hay không, cần thêm **một** phép so sánh.

Vậy:

\[
\boxed{C_{\text{mỗi tầng}} \le k\le d.}
\]

Ở một nút có đầy đủ `d` con, phép đẩy xuống có thể dùng **`d` phép so sánh khóa trong một tầng**, so với tối đa hai phép so sánh ở mỗi tầng của heap nhị phân.

**Đánh đổi bắt đầu xuất hiện:** cây thấp hơn, nhưng chọn con mất thêm phép so sánh.

## 9. Mô phỏng extract-min trên heap 4-nhánh

Ta quay lại heap có 13 phần tử:

```text
[1, 6, 4, 8, 12, 10, 7, 9, 15, 13, 20, 11, 14]
```

### Bước 1 — lấy gốc và thay bằng phần tử cuối

Lưu `answer=1`. Lấy phần tử cuối `14` và đặt lên gốc:

```text
[14, 6, 4, 8, 12, 10, 7, 9, 15, 13, 20, 11]
 ^
 i=0, n mới = 12
```

Hình dạng còn hoàn chỉnh, nhưng `14` lớn hơn các con.

### Bước 2 — chọn con nhỏ nhất của gốc

Với `d=4`, gốc có các con chỉ số `1,2,3,4` với khóa `6,4,8,12`. Con nhỏ nhất là **`4` tại chỉ số `2`**:

```text
[4, 6, 14, 8, 12, 10, 7, 9, 15, 13, 20, 11]
       ^
       i=2
```

Ở tầng này, chọn con cần ba phép so sánh giữa bốn con; kiểm tra `14>4` là phép so sánh khóa thứ tư.

### Bước 3 — tiếp tục tại chỉ số 2

Con của nút `i=2` có các chỉ số tiềm năng `9,10,11,12`. Nhưng `n=12` nên `12` **không còn tồn tại**. Ba con thực tế là:

```text
i=9:   13
i=10:  20
i=11:  11   <- nhỏ nhất
```

Ta đổi `14` với `11`:

```text
[4, 6, 11, 8, 12, 10, 7, 9, 15, 13, 20, 14]
        ^
       i=11: lá
```

Kết quả:

- `extract_min` trả về `1`.
- Heap còn lại có gốc `4`.
- Cây vẫn hoàn chỉnh; mọi quan hệ cha–con đều hợp lệ.
- Có hai lần hoán đổi, nhưng **số so sánh khóa** của ví dụ có thể là `4+3=7`: bốn so sánh ở gốc và ba ở tầng tiếp theo.

Ví dụ này cho thấy vì sao không thể chỉ đếm **số tầng** để dự đoán chi phí: một tầng với `d` con cần quét nhiều khóa hơn để chọn con ưu tiên nhất.

## 10. Phân tích so sánh: O(log_d n) so với O(d log_d n)

Gọi:

- `n`: số phần tử của heap.
- `d\ge2`: số nhánh tối đa trên mỗi nút.
- `h`: chiều cao, xấp xỉ `\log_d n`.

### Sift-up

Mỗi tầng chỉ phải so khóa của phần tử với **một cha**:

\[
\boxed{T_{\text{sift-up}}=O(\log_d n).}
\]

Trong mô hình đếm so sánh, trường hợp xấu nhất có không quá `h` lần so sánh cha–con khi đi đến gốc. Điều này áp dụng cho:

- Thêm một khóa trong min/max-heap.
- **Giảm khóa** trên min-heap đã biết vị trí.
- **Tăng khóa** trên max-heap đã biết vị trí.

### Sift-down

Mỗi tầng có thể phải tìm cực trị trong tối đa `d` con. Điều đó tốn tới `d-1` so sánh giữa con, cộng một so sánh cha–con:

\[
\boxed{T_{\text{sift-down}}=O(d\log_d n).}
\]

Đây là các cận trên thông dụng cho `n\ge2`, **`d` cố định** và phép so sánh khóa `O(1)`. Nếu `d` có thể tăng theo `n`, dùng `O(1+\log_d n)` cho số tầng của sift-up và `O(\min(d,n)(1+\log_d n))` làm cận tổng quát cho so sánh sift-down. Tại mức cực đoan `d\ge n-1`, heap gần như là một gốc có các con trực tiếp và một lần sift-down có thể phải quét **`O(n)`** phần tử.

### Ước lượng số so sánh theo chiều cao

Với `n=65.536`, chiều cao hoàn chỉnh tính từ phần 5:

| `d` | Chiều cao `h` | Cận so sánh sift-up `h` | Cận thô so sánh sift-down `d\cdot h` |
|---:|---:|---:|---:|
| `2` | `16` | `16` | `32` |
| `4` | `8` | `8` | `32` |
| `8` | `6` | `6` | `48` |
| `16` | `4` | `4` | `64` |

**Cột cuối là cận thô, không phải kết quả benchmark.** Tầng cuối có thể không đủ con; khóa đang đẩy có thể dừng sớm; việc so sánh/trao đổi còn phụ thuộc thứ tự dữ liệu và các phép truy cập bộ nhớ.

Nhận xét:

- Khi tăng `d`, **số tầng sift-up giảm** khá rõ.
- Cận số so sánh sift-down **không giảm đơn điệu** theo `d`; nhiều con làm một tầng đắt hơn.
- Heap `d=4` có thể giảm một nửa chiều cao so với `d=2`, nhưng cận số so sánh sift-down ở bảng này vẫn xấp xỉ ngang nhau.
- `d` quá lớn có thể làm lấy gốc đắt, dù cây rất thấp.

## 11. Tìm d “tối ưu” về số so sánh có đơn giản không?

Một mô hình thô cho số phép so sánh trong `sift-down` trường hợp xấu nhất là:

\[
C_{\downarrow}(d)\approx d\log_d n
=d\frac{\ln n}{\ln d}.
\]

Với `n` cố định, điều cần tối thiểu hóa trong mô hình này là:

\[
f(d)=\frac d{\ln d},\qquad d>1.
\]

Đạo hàm:

\[
f'(d)=\frac{\ln d-1}{(\ln d)^2}.
\]

Nó bằng `0` khi `d=e\approx2{,}718`. Với `d` là số nguyên ít nhất `2`, **`d=3`** nằm gần cực tiểu của mô hình *đếm so sánh sift-down* đơn giản này.

**Nhưng không thể suy ra “heap 3-nhánh luôn nhanh nhất”.** Lý do:

1. Mô hình chỉ tính số phép so sánh tối đa, chưa tính tốc độ đọc bộ nhớ.
2. Các con của một nút nằm liên tiếp trong mảng, có thể được quét hiệu quả.
3. Số lần đẩy xuống thực tế có thể ít hơn chiều cao.
4. Workload có thể chứa rất nhiều `sift-up`, vốn được lợi khi `d` lớn.
5. Kích thước khóa, kiểu đối tượng, cache line, compiler và nhánh điều kiện đều ảnh hưởng.
6. Số mục và phân bố dữ liệu quyết định số con thực tế và khả năng dừng sớm.

Vì vậy, `d\approx3` là **một kết quả của mô hình toán học đơn giản**, không phải khuyến nghị mặc định cho mọi hàng đợi ưu tiên.

### Khi workload gồm cả đẩy lên và đẩy xuống

Giả sử:

- Có `U` thao tác chủ yếu phải đẩy lên.
- Có `P` thao tác chủ yếu phải đẩy xuống.

Một mô hình chi phí so sánh xấp xỉ là:

\[
C_{\text{total}}(d)\ \approx\
(U+dP)\frac{\ln n}{\ln d}.
\]

Ở đây `n` được xem là cỡ kích thước heap đại diện, và ta bỏ qua sự thay đổi kích thước theo từng thao tác để dễ so sánh.

Nếu `U\gg P`, tăng `d` có thể hấp dẫn vì giảm số tầng cho **rất nhiều lần đẩy lên**. Nếu `P` rất lớn, tăng `d` quá mức có thể gây tốn nhiều so sánh khi lấy gốc. Bài toán chọn `d` là **cân bằng cả hai loại thao tác**, không thể xét riêng chiều cao.

## 12. Cài đặt min-heap d-nhánh bằng Python

Phiên bản sau hỗ trợ:

- Chọn `d\ge2` khi khởi tạo.
- Xây heap từ một iterable dữ liệu bằng **heapify từ dưới lên**.
- `push`, `peek`, `pop`.
- Kiểm tra bất biến min-heap.

Để giữ ví dụ rõ ràng, các khóa là **số nguyên** và thứ tự ưu tiên là **giá trị nhỏ trước**.

```python
from collections.abc import Iterable


class DaryMinHeap:
    def __init__(self, d: int = 2, values: Iterable[int] = ()) -> None:
        if not isinstance(d, int) or d < 2:
            raise ValueError("d phải là số nguyên >= 2")
        self.d = d
        self.data: list[int] = list(values)
        self.heapify()

    def __len__(self) -> int:
        return len(self.data)

    def peek(self) -> int:
        if not self.data:
            raise IndexError("Heap rỗng")
        return self.data[0]

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // self.d
            if self.data[parent] <= self.data[i]:
                break
            self.data[parent], self.data[i] = (
                self.data[i], self.data[parent]
            )
            i = parent

    def _sift_down(self, i: int) -> None:
        n = len(self.data)
        while True:
            first = self.d * i + 1
            if first >= n:
                break

            # end là cận không bao gồm; nút cuối có thể ít hơn d con.
            end = min(first + self.d, n)
            best = first

            # Tìm con nhỏ nhất trong [first, end).
            for child in range(first + 1, end):
                if self.data[child] < self.data[best]:
                    best = child

            if self.data[i] <= self.data[best]:
                break

            self.data[i], self.data[best] = (
                self.data[best], self.data[i]
            )
            i = best

    def push(self, value: int) -> None:
        self.data.append(value)
        self._sift_up(len(self.data) - 1)

    def pop(self) -> int:
        if not self.data:
            raise IndexError("Không thể pop từ heap rỗng")

        result = self.data[0]
        last = self.data.pop()

        if self.data:
            self.data[0] = last
            self._sift_down(0)
        return result

    def heapify(self) -> None:
        n = len(self.data)
        if n < 2:
            return

        # Nút cha cuối: (n-2)//d; các nút sau nó đều là lá.
        for i in range((n - 2) // self.d, -1, -1):
            self._sift_down(i)

    def check_invariants(self) -> bool:
        # Kiểm tra từng nút (trừ gốc) so với cha.
        return all(
            self.data[(i - 1) // self.d] <= self.data[i]
            for i in range(1, len(self.data))
        )
```

### 12.1. Thêm một khóa vào heap 4-nhánh

```python
initial = [1, 6, 4, 8, 12, 10, 7, 9, 15, 13, 20, 11, 14]
heap = DaryMinHeap(d=4, values=initial)

assert heap.check_invariants()
heap.push(0)
print(heap.data)
# [0, 6, 4, 1, 12, 10, 7, 9, 15, 13, 20, 11, 14, 8]

print(heap.peek())  # 0
assert heap.check_invariants()
```

### 12.2. Xóa gốc của heap 4-nhánh

```python
heap = DaryMinHeap(d=4, values=initial)
print(heap.pop())  # 1
print(heap.data)
# [4, 6, 11, 8, 12, 10, 7, 9, 15, 13, 20, 14]
assert heap.check_invariants()
```

### 12.3. Xây heap từ mảng chưa có thứ tự

```python
values = [17, 3, 8, 1, 12, 5, 10, 6, 2]
heap = DaryMinHeap(d=3, values=values)

assert heap.check_invariants()
assert len(heap) == len(values)

ascending = [heap.pop() for _ in range(len(heap))]
print(ascending)  # [1, 2, 3, 5, 6, 8, 10, 12, 17]
assert len(heap) == 0
```

Phép lấy gốc liên tiếp trả các giá trị theo thứ tự tăng dần, nhưng **mảng bên trong heap ở các thời điểm trung gian không bắt buộc tăng dần**.

### 12.4. Trường hợp rỗng, một phần tử và d lớn hơn n

```python
empty = DaryMinHeap(d=8)
assert empty.check_invariants()
assert len(empty) == 0

single = DaryMinHeap(d=16, values=[42])
print(single.peek())  # 42
print(single.pop())   # 42
assert len(single) == 0

wide = DaryMinHeap(d=100, values=[5, 2, 9, 1])
print(wide.pop())  # 1
assert wide.check_invariants()
```

Với `d\ge n-1`, tất cả những phần tử khác có thể là con trực tiếp của gốc, nên cây chỉ cao một cạnh nếu có ít nhất hai nút. Tuy nhiên, `pop` có thể phải **quét nhiều con** để tìm nhỏ nhất; chiều cao nhỏ không đồng nghĩa với tổng thời gian nhỏ.

**Lưu ý:** mã chỉ minh họa thuật toán và giả định khóa số nguyên có phép so sánh nhất quán. Nếu có `NaN` hoặc đối tượng có phép so sánh khác, bất biến so sánh phải được định nghĩa lại rõ ràng. Không có thao tác nào an toàn để sử dụng đồng thời từ nhiều luồng nếu thiếu đồng bộ.

## 13. Vì sao heapify từ dưới lên vẫn O(n)?

Ta có thể xây d-ary heap theo hai cách:

1. Bắt đầu từ heap rỗng, thêm lần lượt `n` khóa. Mỗi `push` có thể mất `O(\log_d n)`, tổng **`O(n\log_d n)`** trong trường hợp xấu nhất.
2. Đặt toàn bộ `n` khóa vào mảng, rồi gọi `sift-down` từ **nút cha cuối** về gốc. Đây là **bottom-up heapify**, có thời gian **`O(n)` với `d` cố định**.

### 13.1. Vì sao bắt đầu từ nút cha cuối?

Trong heap d-nhánh có `n\ge2` phần tử, nút cha cuối ở:

\[
i_{\text{last parent}}
=\left\lfloor\frac{n-2}{d}\right\rfloor.
\]

Mọi nút sau đó đều là lá; lá tự thỏa bất biến thứ tự vì không có con.

Thuật toán:

```text
HEAPIFY_DARY_MIN(H, d):
    n = length(H)
    if n < 2:
        return
    for i = (n - 2) // d down to 0:
        SIFT_DOWN_DARY_MIN(H, d, i)
```

Khi đi từ những nút cha gần đáy lên gốc, các cây con của nút hiện tại đã là heap, nên `sift-down` có đúng tiền điều kiện để khôi phục bất biến.

### 13.2. Đếm tổng số công việc thay vì nhân n với log n

Không phải tất cả `n` nút đều đẩy xuống `h\approx\log_d n` tầng:

- Các nút **lá** không làm gì.
- Nhiều nút gần đáy chỉ có thể đi xuống **một tầng**.
- Ít nút hơn có thể đi xuống **hai tầng**.
- Chỉ một số rất nhỏ nút gần gốc có thể đi sâu gần toàn bộ chiều cao.

Với `d` **cố định**, số nút có chiều cao còn lại cỡ `t` giảm nhanh theo `d^t`. Một cách ước lượng tổng số so sánh là:

\[
T(n)
\ \le\
O\!\left(
n\,d\sum_{t=1}^{\infty}\frac{t}{d^t}
\right).
\]

Vì:

\[
\sum_{t=1}^{\infty}\frac{t}{d^t}
=\frac{d}{(d-1)^2},
\qquad d>1,
\]

nên, với `d` là một hằng số:

\[
\boxed{T(n)=O(n).}
\]

Ý nghĩa quan trọng là **heapify không bắt mỗi phần tử đi từ lá tới gốc**; nó khôi phục cây theo chiều từ dưới lên với phần lớn nút có công việc nhỏ.

### 13.3. Khi d là tham số biến thiên rất lớn

Phân tích Big-O chuẩn của `heapify` thường coi `d` **cố định**. Nếu `d` được chọn tăng mạnh theo `n`, cần xem số con **thực tế** ở mỗi nút, chi phí quét mỗi nhóm con và số lần so sánh trong triển khai.

Ví dụ, nếu `d\ge n-1`, heap có gốc và tối đa `n-1` con, việc biến một mảng thành min-heap chỉ cần chọn phần tử nhỏ nhất để làm gốc, bằng **`O(n)`** phép so sánh. Dùng công thức `O(d\log_d n)` thay cho số con thực có thể cho cận rất lỏng trong tình huống này.

Vì vậy, khi so sánh nhiều giá trị `d` trong một hệ thống, hãy phân biệt **cận tổng quát theo tham số** với **số lần so sánh thực tế**.

## 14. Mỗi nút d-nhánh vẫn lưu gọn trong mảng

Heap d-nhánh không yêu cầu lưu `d` con trỏ trên từng nút. Nhờ bất biến hình dạng, các con được xác định bằng chỉ số số học:

```text
d = 4:

Nút i      Con 1      Con 2      Con 3      Con 4
  i        4i+1       4i+2       4i+3       4i+4
```

Do đó:

- `n` khóa cần **`O(n)` ô lưu trữ**.
- Thông tin `d` và các biến duyệt cần **`O(1)` bộ nhớ phụ**.
- `push`, `pop`, `sift-up` và `sift-down` dạng lặp đều dùng `O(1)` biến phụ, ngoài vùng mảng.
- Không có thêm `d` con trỏ trên từng nút như ở một cây liên kết tổng quát.

Đây là một điểm quan trọng: **tăng bậc nhánh không tự nhân bộ nhớ của mỗi nút lên `d` lần** trong biểu diễn mảng. Đánh đổi chủ yếu nằm ở **cách tính vị trí**, **chiều cao** và **công việc chọn con**.

Nếu heap chứa **đối tượng lớn**, việc hoán đổi toàn bộ đối tượng có thể đắt hơn hoán đổi các khóa hoặc con trỏ/handle nhỏ. Điều này ảnh hưởng cả heap nhị phân lẫn heap d-nhánh, và có thể khiến mảng các tham chiếu/handle phù hợp hơn tùy chính sách sở hữu dữ liệu.

## 15. Bộ nhớ đệm CPU và lý do d = 4 hoặc 8 có thể đáng thử

Trong biểu diễn mảng 0-based, con của nút `i` chiếm một **đoạn liên tiếp**:

\[
H[di+1],H[di+2],\ldots,H[di+d].
\]

Ví dụ:

```text
d = 4, i = 1:

Chỉ số mảng:  0  1  2  3  4 | 5  6  7  8 | 9 ...
                                └────────┘
                              Bốn con của i=1
```

Điều này có hai mặt:

**Lợi ích tiềm năng:**

- Các khóa con nằm gần nhau, có thể được nạp trong ít dòng cache nếu kích thước phần tử nhỏ.
- Ít tầng hơn có thể giảm số lần đi tới một nhóm con ở xa.
- Khi `d` vừa phải, việc quét một nhóm nhỏ phần tử liên tiếp có thể hiệu quả trên CPU hiện đại.

**Chi phí tiềm năng:**

- Mỗi tầng có thể phải đọc và so sánh thêm nhiều khóa.
- Với `d` lớn, nhóm con có thể trải qua nhiều dòng cache.
- Nếu mỗi mục chứa payload lớn, đọc `d` phần tử có thể tốn nhiều băng thông bộ nhớ.
- Mẫu truy cập và so sánh có thể tạo thêm nhánh điều kiện hoặc phụ thuộc dữ liệu.

**Cache line** thường có kích thước hữu hạn (ví dụ `64` byte trên nhiều nền tảng, nhưng không phải chuẩn bắt buộc). Nếu mỗi mục heap chiếm `8` byte, một nhóm `4` con chỉ dùng `32` byte dữ liệu mục, còn nhóm `16` con dùng `128` byte — **chưa tính căn chỉnh và các cấu trúc khác**. Đây là cách ước lượng dung lượng quét, không phải cam kết số cache miss thực tế.

Vì vậy, `d=4` hay `d=8` có thể đáng **đem ra benchmark**, nhất là khi workload thiên về giảm khóa và các phần tử nhỏ. Nhưng không có quy tắc “`d=4` luôn tốt hơn `d=2`” hoặc “`d=8` luôn nhanh nhất”. Tốc độ phụ thuộc CPU, compiler, trình cấp phát, kích thước khóa, số phần tử và tần suất thao tác.

## 16. Heap có chỉ mục và thao tác decrease-key

Trong một heap chỉ lưu mảng, `sift-up` sửa khóa ở **chỉ số đã biết** trong `O(\log_d n)`. Nhưng ứng dụng thường chỉ biết **ID của công việc** chứ không biết vị trí hiện tại.

Ví dụ:

```text
change_priority("job-17", 1)
```

Heap-order chỉ ràng buộc **khóa ưu tiên**, không giúp tìm ID tùy ý. Nếu phải quét mảng, riêng bước tìm có thể mất **`O(n)`**, lớn hơn cả chi phí sửa heap.

**Indexed d-ary heap** kết hợp:

1. Mảng `heap` chứa các bản ghi `(priority,id)`.
2. Bảng ánh xạ ngược `position[id]=index`.

Bất biến đồng bộ:

\[
\boxed{position[heap[i].id]=i,\qquad 0\le i<n.}
\]

Khi một lần `sift-up` hoặc `sift-down` đổi chỗ hai bản ghi, phải cập nhật **cả hai ID** trong bảng ánh xạ:

```python
def swap_indexed(heap, position, i: int, j: int) -> None:
    heap[i], heap[j] = heap[j], heap[i]
    position[heap[i][1]] = i
    position[heap[j][1]] = j
```

Ví dụ giả định các bản ghi là tuple `(priority,id)` và các ID đang hoạt động là duy nhất. Hàm là minh họa một thao tác nền, không phải toàn bộ indexed heap.

Với bảng băm tra cứu ID **`O(1)` kỳ vọng**:

- `decrease-key` theo ID trong min-heap: `O(\log_d n)` kỳ vọng.
- `increase-key` theo ID trong min-heap: `O(d\log_d n)` kỳ vọng vì có thể phải đẩy xuống.
- Xóa mục theo ID: chuyển phần tử cuối vào vị trí xóa và đẩy lên hoặc xuống tùy bất biến, nên cận `O(d\log_d n)` kỳ vọng.
- Bộ nhớ bảng vị trí: thêm `O(n)` bên cạnh `O(n)` của mảng heap.

Nếu ID là số nguyên dày đặc trong một miền nhỏ, có thể dùng **mảng `position[id]`** để truy cập vị trí trong `O(1)` trường hợp xấu nhất, với chi phí bộ nhớ phụ theo kích thước miền ID.

**Không dùng chỉ số heap làm định danh lâu dài.** Chỉ số có thể đổi sau một lần `push`, `pop` hay thay khóa; các API nghiệp vụ nên nhận ID ổn định và để heap tự tra bảng vị trí hiện tại.

## 17. Ứng dụng Dijkstra: khi nhiều lần giảm khóa hơn số lần lấy gốc

Trong thuật toán Dijkstra trên đồ thị có trọng số cạnh **không âm**, mỗi đỉnh `v` có một nhãn khoảng cách tạm thời `dist[v]`. Khi tìm thấy đường đi tốt hơn, nhãn của đỉnh giảm, nên một min-priority queue có thể cần thao tác **decrease-key**.

Giả sử:

- `V` đỉnh.
- `E` cạnh được xét.
- Mỗi đỉnh có tối đa **một bản ghi đang hoạt động** trong indexed heap.
- Có `O(V)` lần lấy gốc.
- Có tối đa `O(E)` lần giảm khóa.

Với **heap d-nhánh** có tối đa `d` con mỗi nút, được lưu trong mảng:

- Mỗi lần giảm khóa: `O(\log_d V)` phép so sánh/hoán đổi theo đường lên.
- Mỗi lần lấy gốc: `O(d\log_d V)` phép so sánh trong trường hợp xấu nhất.

Tổng phần thao tác heap theo mô hình này có cận:

\[
\boxed{O\!\left(
E\log_d(V+1)+Vd\log_d(V+1)
\right).}
\]

Quét các cạnh còn tốn `O(E)` công việc; xây hoặc thêm các mục ban đầu cũng có chi phí riêng. Nếu dùng indexed heap có bảng băm, các kết luận trên được hiểu với giả định tra cứu/cập nhật ánh xạ có chi phí hằng số kỳ vọng; với mảng vị trí ID đỉnh, các thao tác chỉ số là `O(1)` trường hợp xấu nhất.

### Tại sao d lớn có thể có lợi khi E lớn?

Nếu `E\gg V`, số lần **giảm khóa** có thể lớn so với số lần **lấy gốc**. Khi đó chọn `d` lớn hơn `2` giúp giảm số tầng cho nhiều lần sift-up, trong khi ta chấp nhận mỗi lần pop phải duyệt nhiều con.

Một ý tưởng cân bằng thô dựa trên biểu thức:

\[
E\log_d V+Vd\log_d V
= (E+Vd)\log_d V
\]

là thử `d` cùng cỡ với tỷ lệ `E/V` khi tỷ lệ đó lớn, thay vì luôn `d=2`. Đây chỉ là **gợi ý định hướng**, không phải lựa chọn tối ưu tuyệt đối: số thao tác giảm khóa thực tế có thể ít hơn `E`, và chi phí cache/cấp phát ảnh hưởng lớn.

### Hai lưu ý quan trọng

1. Nếu Dijkstra được viết theo kiểu **lazy insertion** — mỗi lần cải thiện khoảng cách lại thêm một bản ghi mới rồi bỏ qua bản ghi cũ — heap có thể chứa **nhiều hơn `V` bản ghi**. Khi ấy cần phân tích theo số bản ghi vật lý trong heap, không được tự thay bằng `V`.
2. Heap d-nhánh không làm Dijkstra đúng trên đồ thị có cạnh âm. Điều kiện trọng số không âm thuộc tính đúng đắn của thuật toán đường đi, tách biệt với cách tổ chức hàng đợi ưu tiên.

Trong các đồ thị thưa, hoặc khi `pop` chiếm tỷ trọng lớn, `d=2` hay `d=4` vẫn có thể cạnh tranh rất tốt. Việc chọn `d` cần dựa trên **đếm thao tác** và **phép đo thực tế**.

## 18. Min-heap, max-heap, khóa trùng và cập nhật phần tử

### 18.1. Đổi sang max-heap

Toàn bộ công thức vị trí và bất biến hình dạng **giữ nguyên**. Chỉ đảo chiều các phép so sánh:

| Thao tác | Min-heap | Max-heap |
|---|---|---|
| Cha–con hợp lệ | `parent\le child` | `parent\ge child` |
| Đẩy lên khi | Con **nhỏ hơn** cha | Con **lớn hơn** cha |
| Chọn con khi đẩy xuống | **Con nhỏ nhất** | **Con lớn nhất** |
| Dừng đẩy xuống khi | Cha `\le` con nhỏ nhất | Cha `\ge` con lớn nhất |
| `peek` và `pop` | Khóa nhỏ nhất | Khóa lớn nhất |

**Đừng chỉ đổi dấu ở phép kiểm tra cuối** mà quên đổi cách chọn con trong vòng quét `d` con.

### 18.2. Khóa bằng nhau

Quan hệ `\le` và `\ge` đều cho phép khóa trùng. Dùng điều kiện dừng **không nghiêm ngặt** giúp tránh hoán đổi hai khóa bằng nhau không cần thiết.

Tuy nhiên, một heap thông thường **không ổn định** theo thứ tự chèn. Nếu cùng priority nhưng muốn công việc đến trước được lấy trước, dùng khóa ghép:

\[
(\text{priority},\text{arrival\_sequence}).
\]

Mỗi lần chọn cha/con, so sánh toàn bộ khóa ghép. `arrival_sequence` nên duy nhất trong tập các mục cần phân xử hòa và có chính sách rõ khi một công việc thay priority.

### 18.3. Đổi khóa giữa heap

Với min-heap và **đã biết vị trí**:

- Giảm khóa có thể vi phạm **với cha** → `sift-up`.
- Tăng khóa có thể vi phạm **với các con** → `sift-down`.

Với max-heap, đảo chiều. Khi xóa một phần tử bất kỳ, đưa phần tử cuối vào ô bị xóa rồi chọn hướng sửa dựa trên quan hệ với cha và con. Chi phí sửa có cận `O(d\log_d n)` vì có thể cần đẩy xuống; chi phí tìm vị trí theo ID phải tính riêng nếu không có chỉ mục.

## 19. Những trường hợp biên và sai lầm hay gặp

| Sai lầm | Vì sao sai? | Cách xử lý |
|---|---|---|
| Cho phép `d=0` hoặc `d=1` rồi dùng công thức log | Mô hình heap d-nhánh của bài yêu cầu `d\ge2` | Kiểm tra khi khởi tạo |
| Dùng cha `(i-1)//2` cho heap `d=4` | Sai quan hệ cha–con | Dùng `(i-1)//d` |
| Cho rằng mọi nút có đúng `d` con | Nút gần cuối có thể ít con hoặc không có con | Dùng `min(first+d,n)` |
| Dùng điều kiện `child<=n` | `n` là cận sau cuối, không phải chỉ số hợp lệ | Chỉ truy cập `child<n` |
| Đọc cha của gốc `i=0` | Gốc không có cha | Chỉ tính cha khi `i>0` |
| Chèn ở một lỗ trống bất kỳ | Phá cây hoàn chỉnh | Chèn đúng **cuối mảng** |
| Xóa gốc bằng `pop(0)` | Dịch `O(n)` ô và không tự sửa heap-order | Chuyển cuối lên gốc rồi sift-down |
| Đẩy xuống bằng cách chọn bất kỳ con nhỏ hơn cha | Có thể còn con nhỏ hơn cha mới | Min-heap chọn **con nhỏ nhất** |
| Chỉ đảo dấu so sánh cha–con khi làm max-heap | Quy tắc chọn con vẫn đang chọn min | Đảo cả hướng chọn con |
| Chỉ xét hai con vì quen binary heap | Bỏ sót con thứ `3,\ldots,d` | Quét mọi con hiện có |
| Nhìn chiều cao giảm rồi kết luận `pop` chắc chắn nhanh hơn | Mỗi tầng cần quét tối đa `d` con | Phân tích `d\log_d n` và benchmark |
| Nói `heapify=O(n\log_d n)` vì gọi sift-down nhiều lần | Nhiều nút gần lá chỉ cần ít bước | Tổng hợp chi phí theo chiều cao, `O(n)` với `d` cố định |
| Thay `d` nhưng giữ nguyên bố trí heap mà không kiểm tra | Các cạnh cha–con đổi | Heapify lại với `d` mới |
| Giữ chỉ số công việc sau những lần hoán đổi | Chỉ số không ổn định | Indexed heap và ID ổn định |
| Quên cập nhật ánh xạ sau swap | Cập nhật/xóa nhầm ID | Sửa mapping của cả hai mục |
| Coi heap d-nhánh là mảng được sắp toàn phần | Chỉ cha–con có thứ tự | Không tìm nhị phân trực tiếp trên heap |
| Dùng `d` cực lớn mà bỏ qua số con quét khi pop | Gốc có thể có gần `n` con | Thử `d` vừa phải, đo phép so sánh |
| Quên xử lý heap rỗng hoặc một phần tử | Đọc/ghi `H[0]` khi không tồn tại | Kiểm tra trước khi `peek/pop` |
| Giả định bảng băm theo ID luôn `O(1)` xấu nhất | Có va chạm và rehash | Phát biểu kỳ vọng hoặc dùng chỉ mục khác |
| Để nhiều luồng sửa heap cùng lúc không đồng bộ | Mảng và các ánh xạ có thể rơi vào trạng thái sai | Khóa/giao thức đồng thời thích hợp |

### Điều kiện chỉ số an toàn

Với `n=len(H)`:

```text
0 <= i < n                 # Chỉ số một phần tử hiện có.
i > 0                      # Điều kiện tính cha.
first = d*i + 1
first < n                  # Có ít nhất một con.
end = min(first + d, n)    # Cận nửa kín của các con.
first <= child < end       # Một con thật sự tồn tại.
```

Với C/C++ và kiểu số nguyên cố định, còn phải đảm bảo phép nhân `d*i` và cộng chỉ số **không tràn** trước khi đem kết quả ra so sánh. Với `size_t` không dấu, cũng tránh vòng lặp ngược kiểu `i>=0` vì điều kiện này luôn đúng.

## 20. Thiết kế benchmark công bằng cho các giá trị d

Nếu một hệ thống cần chọn `d`, một phép benchmark có ý nghĩa nên giữ **cùng tập thao tác** và chỉ thay cấu hình heap.

### Nên kiểm soát những gì?

1. **Kích thước heap:** thử nhiều cỡ `n`, từ vừa cache tới lớn hơn cache.
2. **Tỷ lệ thao tác:** phân biệt `push`, `pop`, `decrease-key`, `increase-key` và `remove`.
3. **Tính hợp lệ:** tất cả phiên bản `d=2,3,4,8,16,...` phải trả cùng chuỗi phần tử ưu tiên theo hợp đồng dữ liệu.
4. **Chi phí xây:** đo riêng `heapify` nếu chương trình xây một lần rồi lấy nhiều; đo chuỗi tăng dần nếu chương trình dùng `push` liên tục.
5. **Chi phí tra ID:** nếu thao tác theo ID, dùng **cùng cách indexed heap** cho mọi `d` và luôn tính chi phí bảo trì ánh xạ.
6. **Kiểu phần tử:** so số nguyên nhỏ, tuple khóa, object lớn hoặc mảng handle để hiểu khác biệt bộ nhớ.
7. **Bộ đếm phép so sánh:** có thể đếm số lần so sánh khi chọn con và khi so cha, ngoài thời gian đồng hồ.
8. **Hiệu ứng CPU:** quan sát cache miss, nhánh điều kiện hoặc CPU counters khi công cụ cho phép.
9. **Nhiều lần đo:** tránh kết luận từ một lần chạy chịu ảnh hưởng nóng/lạnh cache hay hệ thống nền.
10. **Bảo toàn kết quả:** xác minh thứ tự ưu tiên để compiler/tối ưu benchmark không vô tình loại bỏ công việc.

### Diễn giải kết quả

- Nếu `d=8` nhanh hơn `d=2` trong một workload giàu `decrease-key`, không nên kết luận nó sẽ nhanh hơn trong workload chủ yếu `pop`.
- Nếu `d=3` dùng ít phép so sánh `sift-down`, điều đó không bảo đảm ít thời gian CPU nhất.
- Nếu khác biệt chỉ vài phần trăm, nên xem độ biến thiên thống kê, chi phí bộ nhớ và tính đơn giản khi bảo trì.
- Trong một ứng dụng, **chi phí toàn bộ thuật toán** quan trọng hơn tốc độ của một phép `sift-down` tách riêng.

**Không có giá trị `d` tối ưu phổ quát**; cả phân tích và phép đo đều phải phản ánh workload cần giải quyết.

## 21. Bài tập tự kiểm tra

**Bài 1.** Đối với `d=4`, một nút ở chỉ số `i=2` có cha là chỉ số nào? Các vị trí con tiềm năng của nó là gì? Nếu `n=12`, con nào thật sự tồn tại?

**Bài 2.** Với `d=3`, `n=11`, tìm cha của nút `i=10` và các chỉ số con hợp lệ của nút `i=2`.

**Bài 3.** Mảng `[1,10,2,3,4,11,12]` có phải min-heap khi `d=4` không? Có phải min-heap khi `d=2` không? Giải thích bằng một cạnh cha–con.

**Bài 4.** Heap 4-nhánh `[1,6,4,8,12,10,7,9,15,13,20,11,14]` được thêm khóa `0`. Hãy ghi các chỉ số hoán đổi và mảng cuối.

**Bài 5.** Với cùng heap ban đầu ở Bài 4, thực hiện một lần `extract-min`. Ghi giá trị trả về, mảng cuối và số lần hoán đổi.

**Bài 6.** Một nút min-heap d-nhánh có khóa `12` và các con lần lượt mang khóa `7,9,3,6`. Nên đổi với con nào? Vì sao không được chọn con `7` chỉ vì nó nhỏ hơn `12`?

**Bài 7.** Với `d=5` và một nút có đúng `3` con, phép tìm con nhỏ nhất cần bao nhiêu phép so sánh giữa con? Cần thêm tối đa bao nhiêu phép so sánh cha với con được chọn?

**Bài 8.** Giải thích bằng công thức vì sao `sift-up` có cận `O(\log_d n)`, còn `sift-down` có cận `O(d\log_d n)`.

**Bài 9.** Với `n=65.536`, so sánh chiều cao của heap `d=2` và `d=4`. Vì sao chiều cao của `d=4` nhỏ hơn nhưng cận thô số so sánh `sift-down` có thể vẫn tương tự?

**Bài 10.** Một min-heap có `n=1` và `d=100`. Phép `pop` cần làm gì? Có cần tìm con nhỏ nhất không?

**Bài 11.** Nếu `d\ge n-1` và `n\ge2`, cây hoàn chỉnh có chiều cao bao nhiêu? Tại sao một lần `pop` vẫn có thể dùng `O(n)` phép so sánh?

**Bài 12.** Xác định nút cha cuối cùng của heap `d=4` có `n=14` phần tử. Những chỉ số nào là lá?

**Bài 13.** Vì sao heapify từ dưới lên có thể `O(n)` với `d` cố định, thay vì nhân `n` với chi phí xấu nhất của một lần sift-down?

**Bài 14.** Nếu ứng dụng có rất nhiều `decrease-key` trong min-heap nhưng ít `pop`, tăng `d` có thể giúp hay hại? Phần nào của hai loại thao tác đổi chi phí?

**Bài 15.** Khi dùng indexed d-ary heap, sau một lần hoán đổi hai phần tử `A` và `B` tại các chỉ số `i` và `j`, bảng `position` cần cập nhật thế nào?

**Bài 16.** Trong thuật toán Dijkstra có `V` đỉnh, `E` cạnh, indexed d-ary heap có thể làm tối đa `O(E)` lần giảm khóa và `O(V)` lần lấy gốc. Hãy viết cận số bước heap theo `V,E,d` trong mô hình so sánh.

**Bài 17.** So sánh bộ nhớ phụ của heap nhị phân và heap 8-nhánh khi cả hai dùng **mảng giá trị** với cùng `n` mục. Có phải heap 8-nhánh cần tám con trỏ cho mỗi nút?

**Bài 18.** Tại sao không thể chỉ xét `d/\ln d` để xác định cấu hình nhanh nhất của một hàng đợi ưu tiên thực tế?

**Bài 19.** Một thư viện xây heap với `d=4` và đã có bảng `position[id]`. Nếu đổi `d` sang `8`, phải làm gì để bảo đảm cả heap-order lẫn bảng vị trí đúng?

**Bài 20.** Hãy viết lại điều kiện chọn con trong `sift-down` để cài **max-heap d-nhánh**, và nói rõ điều kiện dừng.

### Đáp án và giải thích

1. `parent(2)=(2-1)//4=0`. Con tiềm năng `9,10,11,12`; với `n=12` chỉ `9,10,11` tồn tại vì `12` là cận sau cuối.
2. `parent(10)=(10-1)//3=3`. Con của `i=2` có chỉ số `7,8,9`, cả ba đều nhỏ hơn `11`.
3. Với `d=4` là min-heap: `1\le10,2,3,4` và `10\le11,12`. Với `d=2` không phải min-heap vì nút `10` ở `i=1` có con `3` ở `i=3` nhỏ hơn cha.
4. Thêm `0` ở `i=13`; swap `13↔3` rồi `3↔0`. Kết quả `[0,6,4,1,12,10,7,9,15,13,20,11,14,8]`.
5. Trả `1`, đưa `14` cuối lên gốc, swap `0↔2` (với `4`), rồi `2↔11` (với `11`). Kết quả `[4,6,11,8,12,10,7,9,15,13,20,14]`; hai lần hoán đổi.
6. Chọn con mang khóa `3`, vì min-heap phải đặt **con nhỏ nhất** vào vị trí cha. Chọn `7` sẽ khiến cha mới `7` vẫn lớn hơn con `3`.
7. Chọn min trong ba con cần `3-1=2` phép so sánh khóa; thêm tối đa **một** phép so sánh cha với con nhỏ nhất để quyết định hoán đổi.
8. Chiều cao `h=O(\log_d n)`. Sift-up so với một cha ở mỗi tầng nên `O(h)`; sift-down chọn cực trị trong tối đa `d` con, cần `O(d)` phép so sánh mỗi tầng, nên `O(dh)`.
9. `d=2` có `h=16`, `d=4` có `h=8`. Cận thô theo `d\cdot h` lần lượt là `2×16=32` và `4×8=32`; giảm số tầng nhưng tăng so sánh mỗi tầng.
10. Lưu giá trị gốc, xóa ô cuối làm heap rỗng, trả giá trị. Không có con và không cần gọi sift-down.
11. Chiều cao một cạnh: các phần tử khác đều là con trực tiếp của gốc. Khi pop, phần tử cuối lên gốc có thể phải quét `n-2` con còn lại để tìm nhỏ nhất, nên cần `O(n)` phép so sánh.
12. `lastParent=(14-2)//4=3`. Các nút trong có chỉ số `0,1,2,3`; các lá là `4,5,\ldots,13`.
13. Phần lớn nút là lá hoặc gần đáy, chỉ rất ít nút có chiều cao lớn. Tổng chi phí theo chiều cao có dạng `O(nd\sum_{t\ge1}t/d^t)=O(n)` khi `d` cố định.
14. Tăng `d` giảm chiều cao, thường có lợi cho nhiều lần `decrease-key` phải đẩy lên. Nhưng `pop` đẩy xuống phải xét nhiều con mỗi tầng; cần cân bằng hai loại thao tác và đo thời gian thực.
15. Sau swap: `position[A]=j` và `position[B]=i` nếu ban đầu A ở `i`, B ở `j`. Cả hai đều phải được sửa cùng với mảng.
16. Cận phần heap là `O(E\log_d(V+1)+Vd\log_d(V+1))`, chưa kể quét cạnh và chi phí đặc thù của bảng ánh xạ ngược.
17. Cả hai cần `O(n)` ô cho khóa; `d` chỉ ảnh hưởng **công thức chỉ số**, không làm phát sinh `d` con trỏ trên mỗi nút trong biểu diễn mảng. Bộ nhớ phụ của thao tác dạng lặp là `O(1)`.
18. `d/\ln d` chỉ mô phỏng cận số so sánh sift-down; chưa tính tỷ lệ push/pop, vị trí dừng sớm, cache, kích thước đối tượng, compiler và các chi phí duy trì chỉ mục/cấp phát.
19. Đổi `d` làm đổi **các cạnh cha–con**. Cần heapify lại theo `d=8` và bảo trì hoặc xây lại bảng `position` sau các lần hoán đổi; không giữ map cũ nếu mảng đã đổi vị trí.
20. Quét tất cả con thực có để chọn **con lớn nhất**; nếu `H[i]\ge H[best]` thì dừng, ngược lại hoán đổi và tiếp tục tại `best`.

## 22. Ghi nhớ

**Heap d-nhánh** mở rộng binary heap bằng cách cho mỗi nút có tối đa **`d\ge2` con**, vẫn giữ **cây hoàn chỉnh** và **bất biến thứ tự cha–con**. Với mảng 0-based, cha của `i>0` là **`(i-1)//d`**, còn con của `i` nằm trong khoảng **`[di+1,\min(di+d+1,n))`**. Khi `d` tăng, chiều cao giảm còn cỡ **`\log_d n`**: đẩy lên có thể tiết kiệm tầng vì mỗi tầng chỉ so với **một cha**. Ngược lại, đẩy xuống phải chọn cực trị trong **tối đa `d` con**, nên có cận **`O(d\log_d n)`**, không chỉ `O(\log_d n)`. **Heapify từ dưới lên** vẫn **`O(n)` với `d` cố định**; bộ nhớ mảng vẫn **`O(n)`**, không phải `d` con trỏ mỗi nút. Một `d` lớn hơn có thể phù hợp khi ứng dụng có rất nhiều **push/decrease-key** so với **pop**, đặc biệt trong hàng đợi ưu tiên cho thuật toán đồ thị, nhưng `d` quá lớn làm mỗi bước chọn con đắt hơn. Hãy chọn `d` bằng cả **phân tích phép so sánh, tính cục bộ bộ nhớ, tỷ lệ thao tác và benchmark trên workload thật**, thay vì chỉ nhìn chiều cao của cây.
