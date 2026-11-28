# Định nghĩa B-tree và các quy ước về bậc hoặc bậc tối thiểu

**B-tree** là một cây tìm kiếm nhiều nhánh được **cân bằng theo chiều cao**: mỗi nút có thể chứa nhiều khóa đã sắp xếp và nhiều liên kết đến cây con, trong khi **tất cả lá đều nằm ở cùng độ sâu**. B-tree thường được dùng làm nền tảng của chỉ mục cơ sở dữ liệu và hệ thống lưu trữ vì một nút có thể gom đủ khóa và thông tin định tuyến vào một trang, giúp hạn chế số tầng cần truy cập.

Khi học B-tree, một trở ngại lớn không nằm ở thao tác tìm kiếm mà ở thuật ngữ **bậc** (*order*) và **bậc tối thiểu** (*minimum degree*). Có tài liệu gọi “B-tree bậc 4” khi **mỗi nút có tối đa bốn con**, có tài liệu lại dùng bậc để chỉ **số khóa tối đa**. Một cách mô tả khác dùng tham số `t`, đặt **tối thiểu `t` con** (trừ gốc) và **tối đa `2t` con** cho mỗi nút trong. Nếu không biết quy ước đang được dùng, cùng một cụm từ có thể dẫn đến các công thức khác nhau.

Bài này đưa ra định nghĩa và bất biến của B-tree, so sánh các cách đặt tham số, hướng dẫn đổi quy ước chính xác, giải thích ngoại lệ của gốc và lá, minh họa tác động đến thao tác tách/gộp và chiều cao, kèm ví dụ Java xác minh cây.

## 1. Một nút B-tree lưu gì?

Trong mô hình B-tree tìm kiếm với **các khóa phân biệt**, một nút có `k` khóa tăng dần:

\[
K_0<K_1<\dots<K_{k-1}.
\]

Nếu là **nút trong**, nó có `k+1` con trỏ con:

\[
P_0,P_1,\dots,P_k.
\]

Các khóa trong nút phân chia miền tìm kiếm thành các khoảng. Ví dụ:

```text
                         [ 20 | 40 | 60 ]
                        /      |     |     \
                      P0      P1    P2      P3

P0:  x < 20
P1:  20 < x < 40
P2:  40 < x < 60
P3:  x > 60
```

Khóa bằng `20`, `40` hoặc `60` được tìm thấy ngay tại nút trong theo mô hình B-tree đang xét. Một **nút lá** lưu khóa nhưng không có con trỏ trỏ xuống tầng thấp hơn; vì thế câu “`k` khóa, `k+1` con” là quy tắc về **nút trong**, không phải về lá.

Một B-tree cũng cần đảm bảo:

- Mọi khóa trong mỗi nút được sắp tăng và không trùng, theo mô hình tập hợp khóa phân biệt.
- Các khóa ở mỗi cây con tuân theo các khoảng do khóa phân cách của nút cha tạo ra.
- Mọi lá cùng độ sâu.
- Mỗi nút tuân theo giới hạn **số khóa và số con tối thiểu/tối đa**, có ngoại lệ dành cho gốc.

Chính giới hạn mức lấp đầy kết hợp điều kiện lá cùng độ sâu giúp B-tree giữ chiều cao **O(log n)** thay vì có thể thoái hóa thành một chuỗi dài.

> Quy tắc nhớ nhanh: **Một nút trong chứa `k` khóa thì có `k+1` con**. Bậc của B-tree xác định các giới hạn `k` được phép, chứ không làm mất mối quan hệ cơ bản này.

## 2. Quy ước A: bậc tối thiểu `t` (*minimum degree*)

Đây là quy ước được sử dụng trong nhiều tài liệu thuật toán, đặc biệt khi trình bày thuật toán B-tree theo kiểu **tách một nút đầy trước khi đi xuống**. Chọn một số nguyên:

\[
t\ge 2.
\]

Đối với B-tree có **bậc tối thiểu `t`**:

| Loại nút | Số khóa tối thiểu | Số khóa tối đa | Số con nếu là nút trong |
| --- | ---: | ---: | --- |
| Nút **không phải gốc** | `t-1` | `2t-1` | Từ `t` đến `2t` |
| Gốc **là nút trong** | 1 | `2t-1` | Từ 2 đến `2t` |
| Gốc **là lá và cây không rỗng** | 1 | `2t-1` | 0 |
| Cây rỗng | 0 khóa trên toàn cây | 0 | Có thể biểu diễn bằng gốc rỗng hoặc `null` tùy cài đặt |

Một nút không phải gốc có từ `t-1` đến `2t-1` khóa. Nếu là nút trong, số con tăng thêm một, tức từ `t` đến `2t`. **Nút lá không phải gốc** cũng cần ít nhất `t-1` khóa, nhưng nó **không có con**.

### Ví dụ `t=2`

\[
\begin{aligned}
\text{khóa mỗi nút không phải gốc} &: 1\text{ đến }3,\\
\text{con của nút trong không phải gốc} &: 2\text{ đến }4.
\end{aligned}
\]

Các nút có thể là:

```text
Nút 2: [10]                1 khóa, 2 con nếu là nút trong
Nút 3: [10 | 20]           2 khóa, 3 con nếu là nút trong
Nút 4: [10 | 20 | 30]      3 khóa, 4 con nếu là nút trong
```

Do đó, **B-tree với `t=2` tương ứng cây 2–3–4** theo các quy tắc cân bằng và mô hình khóa đã nêu.

### Ví dụ `t=3`

\[
\begin{aligned}
\text{khóa mỗi nút không phải gốc} &: 2\text{ đến }5,\\
\text{con của nút trong không phải gốc} &: 3\text{ đến }6.
\end{aligned}
\]

Một nút trong có hai khóa phải có ba con; một nút trong có năm khóa phải có sáu con. Không phải mọi nút đều phải có đúng ba con: **`t` chỉ là cận dưới cho nút trong không phải gốc**, còn `2t` mới là cận trên.

## 3. Quy ước B: bậc `m` là **số con tối đa**

Một quy ước khác định nghĩa **B-tree bậc `m`** (*order `m`*) là cây trong đó **mỗi nút trong có tối đa `m` con**. Thường yêu cầu:

\[
m\ge3.
\]

Trong mô hình chuẩn này, nút trong không phải gốc phải có ít nhất `\lceil m/2\rceil` con, nên bảng giới hạn là:

| Loại nút | Số khóa tối thiểu | Số khóa tối đa | Số con nếu là nút trong |
| --- | ---: | ---: | --- |
| Nút không phải gốc | `\lceil m/2\rceil-1` | `m-1` | Từ `\lceil m/2\rceil` đến `m` |
| Gốc không rỗng | 1 | `m-1` | Nếu là nút trong: từ 2 đến `m` |
| Nút lá | Theo giới hạn khóa của nó | `m-1` | 0 |

**Ví dụ `m=5`** theo quy ước “tối đa năm con”:

- Nút trong không phải gốc có **3–5 con**.
- Nút không phải gốc có **2–4 khóa**.
- Gốc có thể chỉ có **một khóa và hai con** khi là nút trong.

```text
Nút trong không phải gốc hợp lệ với m = 5:

             [20 | 40 | 60 | 80]
              /    |    |    |    \
             P0    P1   P2   P3    P4

4 khóa và 5 con: nằm ở mức tối đa.
```

Theo định nghĩa này, một nút trong không phải gốc chỉ có **một khóa và hai con** là **thiếu mức lấp đầy** nếu `m=5`; nhưng một **gốc** có một khóa và hai con vẫn hợp lệ.

### Khi nào `m=2t`?

Nếu áp dụng cả hai cách tham số hóa và muốn chúng mô tả **chính xác cùng những giới hạn**, có thể đặt:

\[
m=2t.
\]

Ví dụ:

| Bậc tối thiểu `t` | Bậc `m=2t` tính theo số con tối đa | Khóa nút không phải gốc | Con của nút trong không phải gốc |
| ---: | ---: | --- | --- |
| 2 | 4 | 1–3 | 2–4 |
| 3 | 6 | 2–5 | 3–6 |
| 4 | 8 | 3–7 | 4–8 |

**Không được tùy tiện chuyển `m=5` thành `t=3` rồi coi hai cây hoàn toàn tương đương.** Khi `m=5`, giới hạn tối đa là **5 con/4 khóa**. Khi `t=3`, giới hạn tối đa là **6 con/5 khóa**. Hai cách mô tả khác nhau ở cận trên dù cận dưới của nút trong đều là ba con.

Đây là nguyên nhân phổ biến khiến ví dụ “B-tree bậc 5” có hình dạng khác nhau giữa các sách.

## 4. Quy ước C: bậc là **số khóa tối đa**

Một số giáo trình hoặc bài giảng dùng từ **bậc `m`** để nói rằng **mỗi nút chứa tối đa `m` khóa**, chứ không phải tối đa `m` con. Khi đó:

\[
\text{số con tối đa của nút trong}=m+1.
\]

Nếu còn áp dụng quy tắc một nút không phải gốc được lấp ít nhất khoảng một nửa theo **số con**, thì:

\[
\begin{aligned}
\text{khóa tối thiểu}&=\left\lceil\frac{m+1}{2}\right\rceil-1,\\
\text{khóa tối đa}&=m.
\end{aligned}
\]

Ví dụ “**bậc 5**” theo quy ước **tối đa năm khóa** nghĩa là:

- Tối đa **5 khóa và 6 con** ở một nút trong.
- Theo quy tắc lấp đầy nêu trên, nút không phải gốc có ít nhất **2 khóa**, nút trong có ít nhất **3 con**.
- Những giới hạn này tương đương `t=3` của quy ước bậc tối thiểu.

Trong khi đó, “**bậc 5**” theo quy ước **tối đa năm con** chỉ có tối đa **4 khóa**. Vì thế cần kiểm tra xem ký hiệu `m` đang đo **khóa**, **con**, hay **mức lấp đầy tối thiểu** trước khi áp dụng bất kỳ công thức nào.

### Bảng đối chiếu ba phát biểu

| Phát biểu trong đề bài | Khóa tối đa/nút | Con tối đa/nút trong | Khóa tối thiểu/nút không phải gốc |
| --- | ---: | ---: | ---: |
| “B-tree có bậc tối thiểu `t=3`” | 5 | 6 | 2 |
| “B-tree bậc `m=5`, `m` là **số con tối đa**” | 4 | 5 | 2 |
| “B-tree bậc `m=5`, `m` là **số khóa tối đa**” | 5 | 6 | 2, nếu dùng điều kiện lấp đầy theo số con ở trên |

**Cách đọc an toàn:** không suy số khóa tối đa từ cụm từ “bậc 5” nếu chưa có định nghĩa đi kèm. Một đề thi rõ ràng sẽ cho trực tiếp ít nhất một trong các quy ước: số con tối đa, số khóa tối đa hoặc bậc tối thiểu `t`.

## 5. Các bất biến chung quyết định B-tree có hợp lệ không

Để kiểm tra một cây, không thể chỉ đếm khóa trong từng nút. Ta cần đồng thời kiểm tra **số khóa, số con, thứ tự các khóa và độ sâu lá**.

### 5.1. Thứ tự khóa và khoảng cây con

Nếu nút trong có `[20 | 40]`, ba con phải giữ các khóa theo đúng khoảng:

```text
                           [20 | 40]
                          /    |     \
                       [5,10] [25,30] [50,70]
                        P0      P1      P2

P0: khóa < 20
P1: 20 < khóa < 40
P2: khóa > 40
```

Không thể chỉ kiểm tra nút con `P1` được sắp nội bộ rồi cho rằng cây hợp lệ: **mọi khóa trong toàn bộ cây con `P1`** phải nằm giữa 20 và 40.

### 5.2. Số khóa và số con

Với quy ước bậc tối thiểu `t`, đặt `k = số khóa thực trong nút`:

```text
Nút trong:
  t - 1 <= k <= 2t - 1    nếu không phải gốc
  số con = k + 1

Gốc là nút trong:
  1 <= k <= 2t - 1
  số con = k + 1 >= 2

Lá không phải gốc:
  t - 1 <= k <= 2t - 1
  không có con
```

Mảng vật lý cấp sẵn `2t-1` ô khóa và `2t` ô con **không có nghĩa tất cả các ô đều đang được dùng**. Cài đặt phải quản lý `keyCount` tách biệt với sức chứa tối đa, tương tự việc phân biệt `size` và `capacity` trong mảng động.

### 5.3. Mọi lá cùng độ sâu

```text
Hợp lệ (mọi lá ở mức 2):

                    [40]
                   /    \
                 [20]   [60]
                 /  \   /  \
              [10] [30][50] [70]

Không hợp lệ nếu chỉ một nhánh được nối thêm tầng:
                    [40]
                   /    \
                 [20]   [60]
                 /  \   /  \
              [10] [30][50] [70]
                            |
                           [80]   <- chỉ nhánh này sâu hơn
```

Trong ví dụ **độ sâu** là số cạnh từ gốc. B-tree giữ mọi lá cùng độ sâu, nên một phép chèn không được tùy ý làm dài chỉ một nhánh; khi cần tăng chiều cao, thuật toán có thể tách gốc và tạo gốc mới chung cho toàn cây.

### 5.4. Ngoại lệ của gốc và cây rỗng

Trong quy ước `t`, **gốc có thể có ít hơn `t-1` khóa**: một khóa vẫn hợp lệ ngay cả khi `t=100`. Nếu gốc không phải lá, nó phải có ít nhất hai con. Nếu xóa khiến gốc thành một nút không còn khóa nhưng có một con, thuật toán thường thay gốc bằng con duy nhất để giảm chiều cao.

Cây rỗng có thể biểu diễn bằng con trỏ gốc `null`, hoặc một đối tượng gốc lá có `0` khóa nếu thư viện chọn quy ước đó. Không được lấy ngoại lệ “gốc có thể rỗng” để cho phép **nút không phải gốc** có 0 khóa trong một B-tree đã được cân bằng hợp lệ.

## 6. Vì sao bậc tối thiểu liên quan trực tiếp đến chiều cao?

Gọi `n` là tổng số khóa trong một B-tree không rỗng theo bậc tối thiểu `t \ge 2`, và `h` là số cạnh từ gốc đến một lá. Vì tất cả lá cùng độ sâu, `h` là chiều cao chung.

Với `h \ge 1`, số khóa **ít nhất** xảy ra khi:

- Gốc chỉ có **một khóa** và **hai con**.
- Mọi nút khác có **`t-1` khóa**, đồng thời mỗi nút trong có **`t` con**.

Do đó số khóa tối thiểu thỏa:

\[
\begin{aligned}
n_{\min}(h)
&=1+2(t-1)\left(1+t+\cdots+t^{h-1}\right)\\
&=1+2(t-1)\frac{t^h-1}{t-1}\\
&=2t^h-1.
\end{aligned}
\]

Suy ra:

\[
2t^h-1\le n
\quad\Longrightarrow\quad
h\le\log_t\left(\frac{n+1}{2}\right).
\]

Với `t` cố định và `t \ge 2`:

\[
h=O(\log_t n)=O(\log n).
\]

Ở phía còn lại, nếu mọi nút đều chứa `2t-1` khóa và mọi nút trong có `2t` con, cây cao `h` có tối đa:

\[
n_{\max}(h)=(2t)^{h+1}-1
\]

khóa. Ví dụ:

| Bậc tối thiểu | Chiều cao `h` | Khóa tối thiểu với chiều cao đó | Khóa tối đa với chiều cao đó |
| ---: | ---: | ---: | ---: |
| `t=2` | 1 | 3 | 15 |
| `t=2` | 2 | 7 | 63 |
| `t=3` | 1 | 5 | 35 |
| `t=3` | 2 | 17 | 215 |

Để kiểm tra hàng `t=3, h=2`: số khóa ít nhất là `2×3²−1=17`, còn tối đa là `6³−1=215`.

**Diễn giải:** bậc tối thiểu càng lớn, một nút trong phải có càng nhiều con (trừ gốc), nên cây có thể chứa nhiều khóa dù chiều cao thấp. Đây là lý do B-tree thích hợp làm chỉ mục trang lưu trữ: giảm số lần đi từ trang cha sang trang con.

## 7. Tác động của quy ước tới chèn, tách và xóa

Biết chính xác giới hạn là điều cần thiết để xây dựng thuật toán cập nhật đúng. Với quy ước `t`, nút **đầy** là nút có đúng `2t-1` khóa.

### 7.1. Tách nút đầy theo bậc tối thiểu `t`

Với `t=3`, nút đầy có **5 khóa**:

```text
Nút đầy:
                  [10 | 20 | 30 | 40 | 50]

Đẩy khóa giữa 30 lên cha:
                           [30]
                          /    \
                    [10 | 20] [40 | 50]
```

Hai nút mới đều có `t-1=2` khóa, vừa bằng ngưỡng tối thiểu. Nếu nút bị tách là **nút trong**, sáu con cũ được chia thành ba con cho nút trái và ba con cho nút phải. Như vậy, cả khóa lẫn khoảng con đều hợp lệ.

Theo quy tắc chèn từ trên xuống, thuật toán xử lý gốc đầy bằng cách tạo gốc mới rồi tách, và tách những con đầy trước khi đi sâu vào chúng. Nhờ thế, khi đến lá sẽ còn chỗ cho khóa mới.

**Tại sao công thức `2t-1` thuận tiện?** Nút đầy có số khóa **lẻ**, nên tồn tại chính xác một khóa giữa. Sau khi đẩy khóa này lên, hai bên còn `t-1` khóa, đều đạt ngưỡng tối thiểu mà không cần trước đó chèn thêm khóa vào nút.

### 7.2. Cẩn thận với quy ước “tối đa `m` con” khi `m` lẻ

Nếu đề định nghĩa **`m=5` là tối đa năm con**, nút đầy có **4 khóa**, nút không phải gốc cần ít nhất **2 khóa**. Không thể lấy một khóa trong nút bốn khóa đẩy lên rồi chia **ba khóa còn lại** thành hai nút mỗi nút ít nhất hai khóa.

Một cách thiết kế chèn phù hợp là cho phép nút có **năm khóa tạm thời sau khi chèn**, sau đó tách:

```text
Trước khi chèn:       [10 | 20 | 40 | 50]   (đầy 4 khóa)
Thêm 30 tạm thời:     [10 | 20 | 30 | 40 | 50]
Tách, đẩy 30 lên:     [10 | 20]  +  [40 | 50]
```

Cách xử lý phải tính cả các con trỏ con nếu đây là nút trong. Ví dụ này nêu rõ **quy ước số khóa tối đa ảnh hưởng trực tiếp tới cách tách**. Không được sao chép một cách máy móc thuật toán “tách trước khi đi xuống” viết cho `2t-1` khóa sang mọi định nghĩa order `m`.

### 7.3. Xóa và mức lấp đầy tối thiểu

Với `t=3`, một nút không phải gốc phải có ít nhất **2 khóa**. Nếu xóa một khóa khỏi nút đang chỉ có hai khóa, nút có nguy cơ còn một khóa và **thiếu mức lấp đầy**.

Các cách phục hồi thường dùng:

- **Mượn/luân chuyển** khóa qua nút cha từ nút anh em còn nhiều hơn số khóa tối thiểu.
- **Gộp** hai nút sát nhau thông qua khóa phân cách ở nút cha. Trong quy ước `t`, hai nút mỗi nút `t-1` khóa cộng với một khóa cha tạo nút `2t-1` khóa, vừa mức tối đa.
- **Sửa lên trên** nếu cha bị thiếu khóa; khi gốc rỗng sau gộp, có thể nâng con duy nhất làm gốc.

Ví dụ `t=3`:

```text
Nút trái:    [10 | 20]      (2 khóa)
Khóa cha:       30
Nút phải:   [40 | 50]      (2 khóa)

Gộp:
             [10 | 20 | 30 | 40 | 50]
             = 5 khóa = 2t - 1 (hợp lệ)
```

Chi phí tái cân bằng được phân bổ trên các tầng của một cây thấp; với `t` cố định, tìm, chèn và xóa có thời gian O(log n) trong mô hình thao tác trên các khóa có chi phí hằng số.

## 8. Tìm kiếm và chi phí I/O khi `t` lớn

Tại một nút, tìm kiếm phải xác định xem khóa cần tìm nằm trong nút hay thuộc khoảng của một trong `k+1` con:

```text
search(node, x):
    tìm vị trí i đầu tiên có node.keys[i] >= x
    nếu i tồn tại và node.keys[i] == x:
        trả về true
    nếu node là lá:
        trả về false
    ngược lại:
        search(node.children[i], x)
```

Có thể quét tuyến tính trong nút với O(`t`) phép so sánh ở trường hợp xấu khi `k \le 2t-1`, hoặc tìm nhị phân trong mảng khóa với O(log `t`) phép so sánh. Cây có chiều cao O(log_t `n`).

| Thước đo | Chi phí điển hình trong mô hình phù hợp |
| --- | --- |
| Số nút trên một đường tìm kiếm | O(log_t `n`) |
| Số lần đọc trang tối đa khi mỗi nút là một trang và chưa cache | O(log_t `n`) |
| So sánh CPU với tìm nhị phân trong mỗi nút | O(log `t` × log_t `n`), tương đương O(log `n`) |
| So sánh CPU với quét tuyến tính trong mỗi nút | O(`t` × log_t `n`) |
| Tìm/chèn/xóa khi `t` cố định | O(log `n`) theo mô hình chuẩn |

**Phân biệt:** O(log_t `n`) mô tả số nút/tầng trên đường tìm kiếm, không mặc định mọi lần truy cập nút đều phát sinh I/O từ đĩa. Nếu các trang đã nằm trong RAM, chi phí so sánh trong nút và tính cục bộ bộ nhớ lại đóng vai trò lớn.

Trong thực tế, `t` thường được chọn gián tiếp theo kích thước trang, kích thước khóa, con trỏ và metadata; không nhất thiết dùng đúng một giá trị cho mọi hệ thống. Một trang lưu được nhiều khóa–con trỏ có thể tăng fan-out, giảm chiều cao và giảm số lần đọc trang.

## 9. Ví dụ Java: xác minh bất biến với `t=3`

Để học đúng quy ước, có thể viết một bộ kiểm tra cây B-tree nhỏ thay vì chỉ nhìn sơ đồ bằng mắt. Ví dụ sau xây dựng cây **sẵn có**, tìm kiếm trên nó và kiểm tra:

1. Số khóa mỗi nút tuân giới hạn `t-1` đến `2t-1`, xét riêng gốc.
2. Khóa trong nút sắp tăng nghiêm ngặt.
3. Các cây con nằm trong khoảng khóa đúng.
4. Nút trong có chính xác `k+1` con.
5. Mọi lá cùng độ sâu.

Mã không cài đặt chèn/xóa; thuật toán chèn/xóa của một thư viện B-tree hoàn chỉnh phải **bảo toàn những bất biến này sau mỗi thao tác**.

```java
public class BTreeDegreeDemo {
    static final class Node {
        final int[] keys;
        final Node[] children; // null: nut la

        Node(int[] keys, Node[] children) {
            this.keys = keys.clone();
            this.children = children == null ? null : children.clone();
        }

        boolean isLeaf() {
            return children == null;
        }
    }

    static final class BTree {
        private final int t; // minimum degree
        private final Node root;

        BTree(int minimumDegree, Node root) {
            if (minimumDegree < 2) {
                throw new IllegalArgumentException("t must be >= 2");
            }
            this.t = minimumDegree;
            this.root = root;
        }

        boolean contains(int target) {
            Node current = root;
            while (current != null) {
                int lo = 0, hi = current.keys.length;
                while (lo < hi) {
                    int mid = lo + (hi - lo) / 2;
                    if (current.keys[mid] < target) {
                        lo = mid + 1;
                    } else {
                        hi = mid;
                    }
                }
                if (lo < current.keys.length
                        && current.keys[lo] == target) {
                    return true;
                }
                if (current.isLeaf()) {
                    return false;
                }
                current = current.children[lo];
            }
            return false;
        }

        boolean validate() {
            if (root == null) {
                return true; // Cay rong duoc bieu dien bang null.
            }
            int[] firstLeafDepth = {-1};
            return validNode(root, true,
                Long.MIN_VALUE, Long.MAX_VALUE, 0, firstLeafDepth);
        }

        private boolean validNode(Node node, boolean isRoot,
                                  long lower, long upper,
                                  int depth, int[] firstLeafDepth) {
            if (node == null) {
                return false;
            }

            int k = node.keys.length;
            int minKeys = isRoot ? 1 : t - 1;
            if (k < minKeys || k > 2 * t - 1) {
                return false;
            }

            for (int i = 0; i < k; i++) {
                long key = node.keys[i];
                if (key <= lower || key >= upper) {
                    return false;
                }
                if (i > 0 && node.keys[i - 1] >= key) {
                    return false;
                }
            }

            if (node.isLeaf()) {
                if (firstLeafDepth[0] == -1) {
                    firstLeafDepth[0] = depth;
                }
                return depth == firstLeafDepth[0];
            }

            if (node.children.length != k + 1) {
                return false;
            }

            for (int i = 0; i <= k; i++) {
                long childLower = i == 0 ? lower : node.keys[i - 1];
                long childUpper = i == k ? upper : node.keys[i];
                if (!validNode(node.children[i], false,
                        childLower, childUpper,
                        depth + 1, firstLeafDepth)) {
                    return false;
                }
            }
            return true;
        }
    }

    public static void main(String[] args) {
        Node left = new Node(new int[] {5, 10, 20}, null);
        Node middle = new Node(new int[] {35, 40, 50}, null);
        Node right = new Node(new int[] {70, 80, 90}, null);
        Node root = new Node(
            new int[] {30, 60},
            new Node[] {left, middle, right}
        );

        BTree tree = new BTree(3, root);
        System.out.println("Valid: " + tree.validate());
        System.out.println("Find 40: " + tree.contains(40));
        System.out.println("Find 65: " + tree.contains(65));

        Node tooSmall = new Node(new int[] {35}, null);
        BTree invalid = new BTree(3, new Node(
            new int[] {30, 60},
            new Node[] {left, tooSmall, right}
        ));
        System.out.println("Underfilled leaf valid: "
            + invalid.validate());
    }
}
```

Kết quả dự kiến:

```text
Valid: true
Find 40: true
Find 65: false
Underfilled leaf valid: false
```

Với `t=3`, ba lá của cây hợp lệ chứa ba khóa mỗi nút, nằm trong khoảng **2–5**. Gốc chứa hai khóa, có ba con và được phép có ít nhất một khóa. Trong cây không hợp lệ, lá giữa chỉ chứa **một khóa**, thấp hơn cận `t-1=2`.

**Phạm vi minh họa:** Bộ kiểm tra duyệt cây được cung cấp và kiểm tra các quy tắc cấu trúc trọng yếu của mô hình khóa phân biệt. Nó giả định đầu vào thực sự là cấu trúc cây không có chu trình hoặc nút con được chia sẻ giữa nhiều cha; nó không kiểm tra tính toàn vẹn của đối tượng đồ thị tổng quát. Một hệ thống sản xuất còn cần xử lý bộ nhớ, lỗi cập nhật, đồng thời và các định dạng khóa phức tạp.

## 10. B-tree và B+ tree: cùng họ nhưng không cùng hợp đồng khóa

B-tree và B+ tree đều sử dụng **nút nhiều khóa và nhiều con**, thường được cân bằng và tổ chức theo trang. Tuy nhiên, cách lưu dữ liệu khác nhau:

| Khía cạnh | B-tree theo mô hình bài này | B+ tree thông dụng |
| --- | --- | --- |
| Khóa tại nút trong | Có thể là khóa của bản ghi và tham gia tìm kiếm kết quả | Thường là khóa phân cách để dẫn đường |
| Dữ liệu bản ghi | Có thể gắn với khóa ở nút trong hoặc lá | Thường nằm ở lá hoặc được lá trỏ tới |
| Bằng khóa nút trong | Có thể trả về kết quả ngay ở nút đó | Thường tiếp tục xuống lá để lấy bản ghi |
| Duyệt phạm vi | Cần duyệt cây theo thứ tự | Các lá thường có liên kết để duyệt tuần tự |
| Giới hạn khóa/con | Tùy định nghĩa và bố cục nút | Cũng tùy bố cục; giới hạn cho nút trong và lá có thể khác nhau |

Vì vậy, không nên đem nguyên xi **hợp đồng nút và cận số khóa** của ví dụ B-tree để áp cho mọi biến thể B+ tree. Các tham số về fan-out, số bản ghi lá, cách lặp khóa phân cách và quy tắc xử lý khóa bằng nhau phải được xác định riêng.

## 11. Những nhầm lẫn thường gặp

1. **“Order `m` luôn là số con tối đa.”** Không. Có tài liệu dùng `m` làm số khóa tối đa; phải đọc định nghĩa.
2. **“Bậc tối thiểu `t` là số khóa tối thiểu.”** Không chính xác: nút **không phải gốc** có tối thiểu `t-1` khóa, còn nút trong đó có tối thiểu `t` con.
3. **“Mọi nút đều phải có ít nhất `t` con.”** Lá có **0 con**, còn gốc là nút trong có thể chỉ có **2 con** bất kể `t` lớn đến đâu.
4. **“Có `k` khóa thì có `k` con.”** Nút trong B-tree tìm kiếm có `k+1` khoảng/con.
5. **“`m=5` con tối đa tương đương `t=3`.”** Cận dưới giống nhau nhưng cận trên khác: `m=5` cho tối đa 5 con; `t=3` cho tối đa 6 con.
6. **“Nút đầy `m-1` khóa luôn tách được trước khi chèn.”** Với order tối đa `m` con mà `m` lẻ, phép tách nút đầy trước khi có khóa mới có thể không bảo đảm hai nút sau tách đạt cận tối thiểu.
7. **“Gốc không phải tuân bất kỳ giới hạn nào.”** Gốc là ngoại lệ ở **cận dưới**, nhưng khi cây không rỗng vẫn có ít nhất một khóa và không vượt sức chứa tối đa.
8. **“Chỉ cần mọi nút đúng số khóa là đã có B-tree.”** Còn cần thứ tự khóa, phạm vi cây con và tất cả lá cùng độ sâu.
9. **“Nếu cây tìm kiếm có chiều cao thấp thì chắc chắn là B-tree.”** Phải thỏa chính xác các bất biến số khóa, số con và cấu trúc lá.
10. **“Mỗi lần truy cập nút chắc chắn phải đọc đĩa.”** Trang đã có trong RAM có thể được sử dụng mà không phát sinh I/O thiết bị.
11. **“`reserve` số ô của một nút tương đương số khóa thực.”** Sức chứa mảng vật lý và số khóa đang dùng trong nút là hai đại lượng khác nhau.
12. **“B+ tree cũng trả về bản ghi ngay khi khóa trùng khóa phân cách ở nút trong.”** Với B+ tree thông dụng, bản ghi thường ở lá.

## 12. Tự kiểm tra

**Câu 1.** Với bậc tối thiểu `t=4`, một nút không phải gốc phải chứa từ bao nhiêu đến bao nhiêu khóa? Nếu là nút trong, nó có thể có bao nhiêu con?

**Đáp án:** Từ `t-1=3` đến `2t-1=7` khóa. Nút trong có từ `4` đến `8` con.

**Câu 2.** Một B-tree theo quy ước order `m=5` là **số con tối đa** có cận khóa như thế nào ở nút không phải gốc?

**Đáp án:** Từ `ceil(5/2)-1=2` đến `5-1=4` khóa. Nút trong có từ 3 đến 5 con.

**Câu 3.** Nếu “order 5” được định nghĩa là **số khóa tối đa**, thì nút trong có tối đa bao nhiêu con?

**Đáp án:** Tối đa `5+1=6` con. Đây là quy ước khác với “order 5 = tối đa năm con”.

**Câu 4.** Trong B-tree `t=3`, một nút lá không phải gốc có đúng hai khóa và không có con. Nó có hợp lệ không?

**Đáp án:** Hợp lệ về mức lấp đầy: `2=t-1` khóa đạt cận dưới, còn lá có 0 con. Cây vẫn cần thỏa các bất biến khác.

**Câu 5.** Trong B-tree `t=3`, gốc là nút trong có một khóa và hai con. Nó có sai vì chưa đủ ba con không?

**Đáp án:** Không. Gốc là ngoại lệ: khi là nút trong và cây không rỗng, nó có thể chỉ có một khóa và hai con.

**Câu 6.** Nút trong giữ các khóa `[20,40,60]`. Khóa `50` phải nằm trong cây con nào, nếu con được đánh số `P0, P1, P2, P3` từ trái sang phải?

**Đáp án:** `P2` vì `40<50<60`.

**Câu 7.** Với `t=3`, một nút đầy có năm khóa `[10,20,30,40,50]`. Khi tách trước khi đi xuống, khóa nào được đẩy lên? Hai nút còn bao nhiêu khóa?

**Đáp án:** Đẩy `30` lên cha; nút trái giữ `[10,20]`, nút phải giữ `[40,50]`, mỗi nút có hai khóa.

**Câu 8.** Vì sao nút đầy bốn khóa trong quy ước tối đa năm con (`m=5`) không thể tách thành hai nút không phải gốc hợp lệ bằng cách đẩy ngay một khóa lên?

**Đáp án:** Sau khi đẩy một khóa chỉ còn ba khóa để chia, trong khi mỗi nút không phải gốc phải có ít nhất hai khóa. Một cách xử lý là để xuất hiện năm khóa tạm thời rồi tách thành `2+1+2`.

**Câu 9.** Với `t=3` và chiều cao `h=2` cạnh từ gốc đến lá, số khóa ít nhất theo mô hình B-tree không rỗng là bao nhiêu?

**Đáp án:** `2t^h-1=2×3²-1=17` khóa.

**Câu 10.** Cũng với `t=3,h=2`, số khóa tối đa là bao nhiêu?

**Đáp án:** `(2t)^{h+1}-1=6³-1=215` khóa.

**Câu 11.** Nếu một cây có mọi nút đúng giới hạn khóa nhưng một lá ở độ sâu 2 còn lá khác ở độ sâu 3, nó có phải B-tree hợp lệ không?

**Đáp án:** Không. Mọi lá của B-tree phải nằm ở cùng độ sâu.

**Câu 12.** Một B-tree `t=2` có những loại nút nào theo số con tối đa và tên gọi thông dụng?

**Đáp án:** Nút có thể có 1, 2 hoặc 3 khóa; nếu là nút trong có tương ứng 2, 3 hoặc 4 con. Đây là cây **2–3–4**.

**Câu 13.** Tại sao không nên kết luận thời gian tìm kiếm B-tree là O(1) chỉ vì mỗi nút có nhiều nhánh?

**Đáp án:** Vẫn phải đi qua O(log_t `n`) tầng và tìm vị trí khóa trong mỗi nút. Khi `t` cố định, thời gian tìm thông thường là O(log `n`).

**Câu 14.** Nếu một đề bài chỉ nói “B-tree bậc 6” mà không định nghĩa bậc, cần làm gì trước khi tính số khóa tối đa?

**Đáp án:** Xác nhận “bậc 6” là **số con tối đa**, **số khóa tối đa**, hay tham số khác. Nếu tối đa sáu con thì có tối đa năm khóa; nếu tối đa sáu khóa thì có tối đa bảy con. Không tự chọn một quy ước rồi coi là phổ quát.

**Câu 15.** Khi xóa làm một nút B-tree `t` còn dưới `t-1` khóa, hai kỹ thuật phục hồi chính là gì?

**Đáp án:** Mượn hoặc luân chuyển khóa từ anh em đủ khóa qua nút cha; hoặc gộp với nút anh em và một khóa phân cách từ cha, sau đó sửa tiếp lên trên nếu cần.

**Điểm ghi nhớ:** B-tree là cây tìm kiếm nhiều nhánh cân bằng, trong đó nút trong có `k` khóa tạo ra `k+1` khoảng con và mọi lá ở cùng độ sâu. Khi dùng **bậc tối thiểu `t`**, nút không phải gốc có **`t-1` đến `2t-1` khóa**, nút trong có **`t` đến `2t` con**. Khi dùng **order `m`**, phải xác minh `m` là **số con tối đa hay số khóa tối đa**; chỉ khi định nghĩa rõ mới có thể tính giới hạn, tách/gộp đúng và phân tích chiều cao một cách nhất quán.
