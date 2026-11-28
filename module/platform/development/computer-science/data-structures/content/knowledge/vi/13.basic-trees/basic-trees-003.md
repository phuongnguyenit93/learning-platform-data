# Độ sâu, chiều cao, bậc của nút và quy ước tính chiều cao

## 1. Tại sao phải phân biệt các đại lượng của cây?

**Cây (tree)** là một cấu trúc dữ liệu biểu diễn quan hệ phân cấp. Trong cây có gốc (*rooted tree*), ta chọn một **nút gốc** và xác định các quan hệ **cha–con**, **tổ tiên–hậu duệ** trên các cạnh nối nút. Từ cấu trúc đó, những câu hỏi thường gặp là:

- Một nút cách gốc bao xa?
- Từ một nút xuống lá xa nhất còn bao nhiêu bước?
- Một nút có bao nhiêu con trực tiếp?
- Cây cao bao nhiêu và cao theo **cạnh** hay theo **số nút**?
- Vì sao có nút bậc lớn nhưng độ sâu nhỏ, hoặc nút độ sâu lớn nhưng không có con?

Các câu hỏi dẫn tới ba đại lượng trọng tâm:

1. **Độ sâu (depth)**: khoảng cách từ **gốc tới nút**.
2. **Chiều cao (height)**: khoảng cách từ **nút tới lá xa nhất trong cây con**.
3. **Bậc (degree)**: số quan hệ trực tiếp kề nút, nhưng cần phân biệt **bậc trong cây có gốc** với **bậc trong đồ thị vô hướng**.

Trong học phần **Cấu trúc dữ liệu**, đây là nền tảng cho việc phân tích **thời gian tìm kiếm**, **bộ nhớ của đệ quy/stack**, giới hạn các phép duyệt, cũng như cách chọn giữa cây cân đối, cây lệch, cây tìm kiếm, heap và đồ thị. **Một quy ước đếm không rõ ràng có thể tạo ra lỗi lệch một đơn vị (off-by-one)** ngay cả khi thuật toán đúng.

Bài này dùng mặc định:

- Cây có gốc không rỗng, hữu hạn, không có chu trình.
- **Độ sâu và chiều cao được đếm theo số cạnh**.
- Gốc có độ sâu `0`; lá có chiều cao `0`.
- Trường hợp cây rỗng và quy ước đếm theo **số nút** sẽ được trình bày riêng.

## 2. Cây minh họa chung

Xét một cây tổng quát có tám nút:

```text
                        R               depth = 0
                     /  |  \
                    A   B   C           depth = 1
                   / \   \
                  D   E   F             depth = 2
                      |
                      G                 depth = 3

R là gốc; các cạnh cha–con:
R–A, R–B, R–C, A–D, A–E, B–F, E–G.
```

Cấu trúc này có:

- `n = 8` nút và `n - 1 = 7` cạnh.
- Gốc `R`; nút lá `C, D, F, G`; nút trong `R, A, B, E`.
- Đường dài nhất từ gốc tới một lá là `R → A → E → G`, gồm **3 cạnh** hoặc **4 nút**.

Tất cả các phép tính sau đều căn cứ vào cây này. Để tránh nhầm khi biểu diễn trong code, ta dùng nhãn `R, A, B, C, D, E, F, G` cho các nút **khác nhau**; không mặc định rằng hai nút có giá trị dữ liệu bằng nhau là cùng một đối tượng nút.

## 3. Độ sâu (depth): đếm từ gốc đến nút

### 3.1. Định nghĩa chính xác

**Độ sâu của nút `u`**, ký hiệu `depth(u)`, là **số cạnh trên đường đi duy nhất từ gốc `r` đến `u`**:

\[
\operatorname{depth}(u)=\operatorname{dist}(r,u).
\]

Ở đây `dist` là số cạnh của đường đi trong cây **không trọng số**. Vì giữa hai nút trong cây có đúng một đường đi đơn, độ sâu được xác định duy nhất khi gốc đã được chọn.

Quy tắc đệ quy theo quan hệ cha–con:

\[
\operatorname{depth}(r)=0,
\qquad
\operatorname{depth}(u)=\operatorname{depth}(\operatorname{parent}(u))+1
\quad\text{với }u\ne r.
\]

Trong cây mẫu:

| Nút | Đường từ gốc `R` tới nút | Độ sâu theo cạnh |
|---|---|---:|
| `R` | `R` | `0` |
| `A` | `R → A` | `1` |
| `B` | `R → B` | `1` |
| `C` | `R → C` | `1` |
| `D` | `R → A → D` | `2` |
| `E` | `R → A → E` | `2` |
| `F` | `R → B → F` | `2` |
| `G` | `R → A → E → G` | `3` |

**Ghi nhớ:** depth đi **từ trên xuống**, lấy **gốc làm mốc**, và **không** phụ thuộc vào việc nút có bao nhiêu con. `G` là lá nhưng có độ sâu `3`; `R` có ba con nhưng vẫn có độ sâu `0`.

### 3.2. Level (mức) và depth có luôn bằng nhau không?

Nhiều tài liệu gọi nhóm nút cùng độ sâu là một **mức/tầng (level)**. Tuy nhiên, có hai quy ước đánh số phổ biến:

| Quy ước | Mức của gốc | Mức của nút `G` | Quan hệ với depth theo cạnh |
|---|---:|---:|---|
| Đánh số từ `0` | `0` | `3` | `level(u) = depth(u)` |
| Đánh số từ `1` | `1` | `4` | `level(u) = depth(u)+1` |

Vì vậy, khi bài toán nói “nút ở level 3”, phải hỏi rõ level được đánh số từ `0` hay từ `1`. Không nên âm thầm coi `level` luôn bằng `depth`.

### 3.3. Tính độ sâu từ một liên kết cha

Nếu mỗi nút có trường `parent`, việc tìm độ sâu của một nút chỉ cần lần theo cha tới gốc, đếm số lần đi qua cạnh.

```text
DEPTH(u):
    d = 0
    while u còn có cha:
        u = parent(u)
        d = d + 1
    return d
```

Nếu chiều cao cây tính theo cạnh là `h`, một nút có độ sâu không vượt quá `h`. Vì thế phép tính này tốn **`O(depth(u))` thời gian**, chặn trên `O(h)`, và dùng **`O(1)` bộ nhớ phụ** nếu chỉ giữ con trỏ cùng bộ đếm.

Đây là **độ sâu trong cây có gốc**; không phải “độ sâu gọi hàm” của runtime. Tuy nhiên, khi thực hiện đệ quy đi xuống mỗi con, độ sâu cây là yếu tố có thể khiến call stack trở nên sâu.

## 4. Chiều cao (height): đếm từ nút xuống lá xa nhất

### 4.1. Định nghĩa theo số cạnh

**Chiều cao của nút `u`**, ký hiệu `height(u)`, là **số cạnh nhiều nhất trên một đường đi từ `u` xuống một lá thuộc cây con gốc `u`**.

Với nút lá, không có cạnh đi xuống nào, nên:

\[
\operatorname{height}(u)=0\quad\text{khi }u\text{ là lá}.
\]

Với nút trong:

\[
\operatorname{height}(u)
=1+\max_{v\in\operatorname{children}(u)}
\operatorname{height}(v).
\]

Ta lấy **max** chứ không lấy trung bình hoặc min, bởi chiều cao phản ánh **nhánh sâu nhất** phía dưới nút.

Áp dụng từ các lá đi ngược lên cây mẫu:

- `height(C)=height(D)=height(F)=height(G)=0`.
- `height(E)=1+height(G)=1`.
- `height(B)=1+height(F)=1`.
- `height(A)=1+max(height(D),height(E))=1+max(0,1)=2`.
- `height(R)=1+max(height(A),height(B),height(C))=1+max(2,1,0)=3`.

### 4.2. Chiều cao của cả cây

**Chiều cao cây** là chiều cao của **gốc**:

\[
\operatorname{height}(T)=\operatorname{height}(r).
\]

Theo quy ước đếm cạnh, nó bằng **độ sâu lớn nhất của một nút bất kỳ** trong cây:

\[
\operatorname{height}(T)
=\max_{u\in V}\operatorname{depth}(u).
\]

Ở cây mẫu, chiều cao là `3` cạnh vì có đường `R → A → E → G` dài ba cạnh. Đừng nhầm **chiều cao của nút** với **độ sâu của nút**:

- `depth(R)=0` nhưng `height(R)=3`.
- `depth(G)=3` nhưng `height(G)=0`.
- `depth(A)=1` còn `height(A)=2`.
- `depth(B)=1` còn `height(B)=1`.

Một nút ở sâu trong cây thường có ít đường đi xuống hơn, nhưng **không tồn tại công thức chung** kiểu `height(u)=height(T)-depth(u)`. Công thức đó chỉ đúng với một số nút nằm trên đường sâu nhất, không đúng cho mọi nút.

Ví dụ, ở nút `C`: `height(C)=0`, trong khi `height(T)-depth(C)=3-1=2`.

### 4.3. Chiều cao của cây con

Nếu lấy nút `A` làm gốc của **cây con gồm `A, D, E, G`**, chiều cao cây con là `2` cạnh. Nó không phụ thuộc vào độ sâu `1` của `A` trong cây ban đầu.

Đây là lý do công thức chiều cao tự nhiên được tính **từ dưới lên (bottom-up)**, còn công thức độ sâu thường tính **từ trên xuống (top-down)**.

## 5. Hai quy ước chiều cao: theo cạnh và theo nút

Đây là phần dễ xảy ra sai lệch nhất khi đọc tài liệu hoặc thực hiện bài lập trình.

### 5.1. Quy ước A: chiều cao bằng số cạnh

Trong bài này, nếu không có ghi chú khác, ta dùng:

- `height_edges(leaf)=0`.
- `height_edges(root)=` số cạnh trên đường dài nhất từ gốc tới lá.
- Với cây **rỗng**, chọn `height_edges(None)=-1` để công thức đệ quy thống nhất.

Công thức gọn:

\[
H_e(\varnothing)=-1,\qquad
H_e(u)=1+\max_{v\in\operatorname{children}(u)}H_e(v).
\]

Ở một nút lá, tập con rỗng nên ta hiểu giá trị mặc định của phép `max` là `-1`; vì vậy `H_e(leaf)=1+(-1)=0`.

Việc quy ước **cây rỗng có chiều cao `-1`** là thuận tiện về mặt đại số. Nó **không có nghĩa** một đường đi thực sự có số cạnh âm; đây là giá trị quy ước cho cấu trúc vắng mặt.

### 5.2. Quy ước B: chiều cao bằng số nút

Một số sách và thư viện định nghĩa chiều cao là **số nút** trên đường dài nhất từ nút đang xét đến một lá, **tính cả nút đầu và nút cuối**:

- `height_nodes(leaf)=1`.
- `height_nodes(root)=` số nút trên đường dài nhất tới lá.
- `height_nodes(None)=0`.

Công thức:

\[
H_v(\varnothing)=0,\qquad
H_v(u)=1+\max_{v\in\operatorname{children}(u)}H_v(v),
\]

trong đó giá trị mặc định của `max` ở nút lá là `0`.

Với mọi **cây con không rỗng**:

\[
H_v(u)=H_e(u)+1.
\]

Và theo các quy ước rỗng đã chọn, công thức này cũng cho `H_v(\varnothing)=0` từ `H_e(\varnothing)=-1`.

### 5.3. So sánh trực tiếp

| Trường hợp | Chiều cao theo **cạnh** | Chiều cao theo **nút** |
|---|---:|---:|
| Cây rỗng (theo quy ước bài này) | `-1` | `0` |
| Cây có một nút | `0` | `1` |
| Gốc có một lá con | `1` | `2` |
| Đường đi gồm bốn nút từ gốc đến lá | `3` | `4` |
| Cây mẫu `R → A → E → G` dài nhất | `3` | `4` |

Có nguồn chọn **chiều cao cây rỗng bằng `0`** và đồng thời định nghĩa chiều cao lá bằng `0`; cách đó vẫn có thể được dùng nếu viết **base case/công thức riêng** phù hợp. Điều quan trọng là **không trộn các quy ước** trong cùng thuật toán.

### 5.4. Mẹo phòng lỗi off-by-one

Trước khi viết công thức hoặc so đáp án, hãy xác nhận:

1. Độ sâu của gốc là `0` hay mức được đánh số từ `1`?
2. Chiều cao lá là `0` hay `1`?
3. Chiều cao của cây rỗng là `-1`, `0` hay không xác định?
4. Kết quả yêu cầu **số cạnh** hay **số nút**?

Nếu chưa thống nhất, những kết quả `3` và `4` cho cùng đường đi `R → A → E → G` có thể đều đúng **theo hai định nghĩa khác nhau**. Khi làm bài, luôn nêu rõ “chiều cao theo số cạnh” hoặc “chiều cao theo số nút”.

## 6. Bậc của nút trong cây có gốc

### 6.1. Bậc theo số con

Trong nhiều giáo trình cấu trúc dữ liệu về **cây có gốc**, **bậc của nút** là **số con trực tiếp** của nút đó:

\[
\deg_{\mathrm{rooted}}(u)
=|\operatorname{children}(u)|.
\]

Ta cũng có thể gọi nó là **child degree** hoặc **out-degree** nếu biểu diễn các cạnh có hướng từ cha xuống con.

Với cây mẫu:

| Nút | Danh sách con trực tiếp | Bậc theo số con |
|---|---|---:|
| `R` | `A, B, C` | `3` |
| `A` | `D, E` | `2` |
| `B` | `F` | `1` |
| `C` | Không có | `0` |
| `D` | Không có | `0` |
| `E` | `G` | `1` |
| `F` | Không có | `0` |
| `G` | Không có | `0` |

Suy ra:

- **Lá** có bậc theo số con bằng `0`.
- **Nút trong** có bậc theo số con **ít nhất `1`**.
- Nút có **một con** vẫn là nút trong, chẳng hạn `B` và `E`.
- Gốc có thể có bậc khác `0`, chẳng hạn `R` có bậc `3`.

### 6.2. Bậc của cả cây

Một định nghĩa thường dùng là **bậc của cây** bằng **bậc lớn nhất của một nút**:

\[
\deg(T)=\max_{u\in V}\deg_{\mathrm{rooted}}(u).
\]

Với cây mẫu, `deg(T)=3` vì gốc `R` có ba con.

Điều này **không phải chiều cao**: cây mẫu tình cờ có cả `deg(T)=3` và `height(T)=3`, nhưng hai đại lượng mô tả những tính chất khác nhau. Một cây hình sao có thể có bậc rất lớn mà chiều cao chỉ `1`; một cây đường thẳng có bậc theo số con tối đa `1` nhưng chiều cao có thể rất lớn.

### 6.3. Bậc vào và bậc ra của cây có hướng cha → con

Nếu hướng cạnh từ cha xuống con:

- `out_degree(u)=child_count(u)`.
- `in_degree(root)=0`.
- `in_degree(u)=1` đối với mọi nút không phải gốc.

Tổng các bậc ra đúng bằng số cạnh:

\[
\sum_{u\in V}\operatorname{out\_degree}(u)=n-1.
\]

Tương tự, tổng bậc vào cũng bằng `n-1`, vì mỗi cạnh có hướng đóng góp một đầu đi ra và một đầu đi vào.

Đây là bất biến hữu ích để kiểm tra cấu trúc phân cấp, nhưng **chỉ tổng đúng chưa đủ** chứng minh mọi nút thuộc cùng một cây và không có chu trình.

## 7. Bậc trong đồ thị vô hướng khác bậc theo số con

Khi xem cây như một **đồ thị vô hướng**, bậc của đỉnh `u` là **số cạnh kề với `u`**. Với cây có gốc và các cạnh chỉ là cạnh cha–con:

\[
\deg_{\mathrm{graph}}(u)=
\begin{cases}
|\operatorname{children}(u)|, & u=r,\\[3pt]
|\operatorname{children}(u)|+1, & u\ne r.
\end{cases}
\]

Lý do: nút không phải gốc có thêm **một cạnh nối tới cha**; gốc không có cạnh tới cha.

Bảng so sánh ở cây mẫu:

| Nút | Bậc theo số con | Có cha? | Bậc đồ thị vô hướng |
|---|---:|---|---:|
| `R` | 3 | Không | `3` |
| `A` | 2 | Có | `3` |
| `B` | 1 | Có | `2` |
| `C` | 0 | Có | `1` |
| `D` | 0 | Có | `1` |
| `E` | 1 | Có | `2` |
| `F` | 0 | Có | `1` |
| `G` | 0 | Có | `1` |

Tổng bậc vô hướng là:

\[
3+3+2+1+1+2+1+1=14=2\cdot 7=2(n-1).
\]

Đây là **định lý bắt tay (handshaking lemma)**: mỗi cạnh vô hướng đóng góp `1` vào bậc của mỗi đầu mút, nên tổng các bậc bằng **hai lần số cạnh**.

### Đặc biệt: gốc ở một đỉnh bậc 1

Với cây ít nhất hai đỉnh, một đỉnh bậc vô hướng bằng `1` được gọi là **lá trong góc nhìn đồ thị vô hướng**. Nhưng nếu **chọn chính đỉnh đó làm gốc**, nó có **một con** nên là **nút trong theo góc nhìn cây có gốc**.

Ví dụ: cây chỉ có cạnh `U—V`, chọn `U` làm gốc thì:

- `U` có bậc vô hướng `1` và bậc theo số con `1`: nút trong.
- `V` có bậc vô hướng `1` nhưng bậc theo số con `0`: lá.

Trên một cây **chỉ có một nút**, bậc vô hướng của nút đó bằng `0`, đồng thời nó là gốc và là lá vì không có con. Cần nhớ trường hợp biên này khi đọc định lý về số lượng lá.

## 8. Depth, height, degree không quyết định lẫn nhau

Ba đại lượng mô tả ba chiều khác nhau:

| Đại lượng | Câu hỏi trả lời | Hướng quan sát |
|---|---|---|
| **Depth** | Từ gốc đến nút phải qua bao nhiêu cạnh? | Từ trên xuống |
| **Height** | Từ nút đi xuống lá xa nhất còn bao nhiêu cạnh? | Từ dưới lên |
| **Child degree** | Nút có bao nhiêu con trực tiếp? | Tại nút, một tầng |
| **Graph degree** | Nút có bao nhiêu cạnh kề trong cây vô hướng? | Tại nút, không xét hướng |

Một số phản ví dụ giúp tránh suy luận sai:

- **Bậc lớn không bảo đảm chiều cao lớn:** gốc cây hình sao có `100` lá con; bậc theo số con là `100` nhưng chiều cao chỉ `1` cạnh.
- **Bậc nhỏ không bảo đảm chiều cao nhỏ:** trong cây dạng chuỗi `R → A → B → C → D`, mỗi nút trong chỉ có `1` con nhưng chiều cao cây là `4`.
- **Depth bằng nhau không bảo đảm height bằng nhau:** `A` và `B` trong cây mẫu đều có depth `1`, nhưng height lần lượt là `2` và `1`.
- **Height bằng nhau không bảo đảm depth bằng nhau:** các lá `C, D, F, G` đều có height `0`, nhưng depth khác nhau.
- **Cùng bậc theo số con không bảo đảm cùng vai trò trong đường đi:** `B` và `E` cùng có một con nhưng ở các độ sâu khác nhau.

Đặc biệt, phép đổi gốc của **một cây vô hướng** có thể làm thay đổi depth, height và **bậc theo số con**; **bậc vô hướng** của từng đỉnh không đổi vì tập cạnh không đổi.

## 9. Cây cân đối, cây lệch và ảnh hưởng tới chiều cao

Với cùng `n` nút, chiều cao của cây phụ thuộc mạnh vào **hình dạng phân nhánh**, không chỉ vào số lượng nút.

### 9.1. Cây dạng chuỗi

```text
R
|
A
|
B
|
C
|
D
```

Cây có `5` nút, chiều cao **`4` cạnh**. Trong cây có `n` nút dạng chuỗi, chiều cao là **`n-1`**. Vì phải đi qua mọi nút từ gốc tới lá duy nhất, đây là trường hợp rất sâu.

### 9.2. Cây dạng sao

```text
         R
       / | \
      A  B  C
         ...   (nhiều lá trực tiếp)
```

Nếu tất cả `n-1` nút không phải gốc đều là con trực tiếp của gốc và `n>1`, chiều cao chỉ **`1` cạnh**, dù bậc của gốc rất lớn.

### 9.3. Cây nhị phân có chiều cao nhỏ

Với cây nhị phân, mỗi nút có tối đa hai con. Nếu chiều cao theo cạnh là `h`, số nút tối đa là:

\[
n\leq 1+2+4+\cdots+2^h=2^{h+1}-1.
\]

Do đó, đối với cây nhị phân không rỗng:

\[
h\geq \left\lceil\log_2(n+1)\right\rceil-1.
\]

Dấu bằng xảy ra ở chiều cao nhỏ nhất khả dĩ đối với số nút cho trước (có thể sắp các nút thành các tầng từ trên xuống mà không cần đường đi sâu hơn). Với **cây nhị phân hoàn hảo** (*perfect binary tree*), mọi tầng từ `0` tới `h` đều đầy, nên `n=2^{h+1}-1`.

Ngược lại, một cây nhị phân lệch hoàn toàn vẫn có thể đạt `h=n-1`. Vì vậy, nếu một thuật toán tìm kiếm trên cây cần đi dọc theo đường từ gốc tới nút, độ phức tạp có thể phụ thuộc vào **`h`**:

- Cây cân đối thích hợp: chiều cao thường `O(\log n)`.
- Cây lệch: chiều cao có thể `O(n)`.

**Không được suy ra mọi cây nhị phân đều có chiều cao `O(\log n)`.** Đó là tính chất của các cấu trúc cân bằng hoặc hình dạng phù hợp, không phải của định nghĩa “nhị phân”.

### 9.4. Số con tối đa và chiều cao

Nếu một cây có gốc có nhiều nhất `b` con trực tiếp ở mỗi nút, thì với `b\ge2` và chiều cao `h`:

\[
n\leq 1+b+b^2+\cdots+b^h
=\frac{b^{h+1}-1}{b-1}.
\]

Đây là **chặn trên số nút** khi đã biết giới hạn phân nhánh và chiều cao. Nó không có nghĩa mọi cây bậc tối đa `b` đều đạt chặn trên; một cây có thể thiếu rất nhiều nhánh.

Với `b=1`, cây không rỗng chỉ có thể là một chuỗi từ gốc đến lá; khi đó `n=h+1`. Với cây một nút, bậc tối đa bằng `0` và `h=0`.

## 10. Mô hình Python: cấu trúc cây tổng quát

Ta xây một mô hình nhất quán để tính depth, height và degree. Mỗi nút lưu:

- `name`: nhãn nhận diện để hiển thị.
- `parent`: cha trực tiếp, hoặc `None` đối với gốc.
- `children`: danh sách con trực tiếp.

Mã dưới đây giả định cây có **một cha cho mỗi nút không phải gốc** và **không có chu trình**. Phương thức `add_child` kiểm tra tránh gắn một nút đã có cha và tránh tạo chu trình qua quan hệ tổ tiên.

```python
class Node:
    def __init__(self, name):
        self.name = name
        self.parent = None
        self.children = []

    def add_child(self, child):
        if not isinstance(child, Node):
            raise TypeError("child phải là Node")
        if child.parent is not None:
            raise ValueError("nút con đã có cha")

        # Nếu child là tổ tiên của self, phép gắn sẽ tạo vòng.
        cursor = self
        while cursor is not None:
            if cursor is child:
                raise ValueError("không được tạo chu trình")
            cursor = cursor.parent

        self.children.append(child)
        child.parent = self

    def child_degree(self):
        return len(self.children)

    def graph_degree(self):
        return len(self.children) + (self.parent is not None)


nodes = {name: Node(name) for name in "RABCDEFG"}

nodes["R"].add_child(nodes["A"])
nodes["R"].add_child(nodes["B"])
nodes["R"].add_child(nodes["C"])
nodes["A"].add_child(nodes["D"])
nodes["A"].add_child(nodes["E"])
nodes["B"].add_child(nodes["F"])
nodes["E"].add_child(nodes["G"])

root = nodes["R"]
```

**Chú ý về cài đặt:** `graph_degree()` cộng một cạnh cha đối với nút không phải gốc. Công thức đúng cho cây không có cạnh khác ngoài các cạnh cha–con. Nếu dữ liệu là đồ thị tổng quát với các cạnh chéo, bậc đồ thị phải được tính theo danh sách cạnh thực tế, không thể suy ra chỉ từ `parent` và `children`.

Mã lớp chưa ngăn việc bên ngoài sửa trực tiếp các trường. Trong thư viện thực tế cần **đóng gói hoặc xác thực thay đổi** để bảo đảm quan hệ hai chiều giữa `parent` và `children` luôn nhất quán.

## 11. Tính độ sâu theo cha và theo duyệt cây

### 11.1. Depth của một nút: đi ngược về gốc

```python
def depth_from_parents(node):
    depth = 0
    cursor = node

    while cursor.parent is not None:
        depth += 1
        cursor = cursor.parent

    return depth


print(depth_from_parents(root))        # 0
print(depth_from_parents(nodes["E"]))  # 2
print(depth_from_parents(nodes["G"]))  # 3
```

**Bất biến:** sau mỗi lượt lặp, biến `depth` bằng số cạnh đã đi từ nút ban đầu lên tới `cursor`. Khi `cursor.parent is None`, ta đã tới gốc, nên số cạnh chính là độ sâu.

Độ phức tạp: **`O(depth(u))` thời gian**, **`O(1)` bộ nhớ phụ**. Nếu cấu trúc bị sai và có chu trình trong liên kết cha, vòng lặp có thể không kết thúc; đầu vào phải là cây hợp lệ hoặc API phải có bước phát hiện lỗi.

### 11.2. Depth của tất cả nút: DFS từ gốc

Khi cần độ sâu của **mọi nút**, thay vì lần theo cha riêng cho từng nút (có thể lặp công việc), ta duyệt một lần từ gốc bằng stack tường minh:

```python
def all_depths(root):
    if root is None:
        return {}

    result = {}
    pending = [(root, 0)]

    while pending:
        node, depth = pending.pop()
        result[node] = depth

        for child in reversed(node.children):
            pending.append((child, depth + 1))

    return result


depths = all_depths(root)

for name in "RABCDEFG":
    print(name, depths[nodes[name]])

# R 0
# A 1
# B 1
# C 1
# D 2
# E 2
# F 2
# G 3
```

**Bất biến:** mỗi phần tử `(node, depth)` trong stack chứa chính xác độ sâu mà nút sẽ nhận dựa trên cha của nó. Khi xử lý nút ở độ sâu `d`, mọi con trực tiếp có độ sâu `d+1`.

Với cây có `n` nút, mỗi nút được thêm/lấy khỏi stack đúng một lần, nên tổng thời gian **`O(n)`**. Bảng kết quả có `n` mục, tốn **`O(n)` bộ nhớ**; riêng stack chờ có thể lớn tới `O(n)` nếu một nút có rất nhiều con. Đây là một phép duyệt cho **cây hợp lệ**; nếu nhận đồ thị có chu trình hoặc nút có nhiều cha, phải bổ sung kiểm tra cấu trúc hay tập `visited` cho bài toán tương ứng.

## 12. Tính chiều cao bằng đệ quy và stack tường minh

### 12.1. Chiều cao theo cạnh bằng đệ quy

Định nghĩa chiều cao có cấu trúc **từ dưới lên**: phải biết chiều cao các cây con trước khi tính chiều cao nút cha.

```python
def height_edges_recursive(node):
    if node is None:
        return -1

    return 1 + max(
        (height_edges_recursive(child) for child in node.children),
        default=-1
    )


def height_nodes_recursive(node):
    if node is None:
        return 0

    return 1 + max(
        (height_nodes_recursive(child) for child in node.children),
        default=0
    )


print(height_edges_recursive(root))       # 3
print(height_nodes_recursive(root))       # 4
print(height_edges_recursive(nodes["E"]))  # 1
print(height_nodes_recursive(nodes["G"]))  # 1
print(height_edges_recursive(None))        # -1
print(height_nodes_recursive(None))        # 0
```

Phương thức dùng `max(..., default=-1)` cho phép **lá** không có con trả `0` theo cạnh; với chiều cao theo nút, `default=0` khiến lá trả `1`.

**Độ phức tạp:** với một lần gọi trên một cây con có `s` nút, mỗi nút được thăm một lần, nên **`O(s)` thời gian**. Bộ nhớ phụ của khung đệ quy là **`O(h_s+1)`** với `h_s` là chiều cao của cây con theo cạnh; nếu cây rất sâu, lời gọi đệ quy có thể vượt giới hạn của runtime.

**Không nên** gọi `height_edges_recursive(node)` cho từng nút riêng rẽ trong một vòng lặp nếu muốn tính chiều cao của tất cả nút: việc duyệt lặp lại các cây con có thể làm tổng chi phí tăng lên **`O(n²)`** trong cây dạng chuỗi.

### 12.2. Chiều cao tất cả nút bằng hậu thứ tự (postorder) lặp

Nếu muốn tính chiều cao **một lần cho mỗi nút** mà không dùng đệ quy sâu, ta mô phỏng hai giai đoạn:

1. **Enter**: đưa các công việc của con lên stack.
2. **Finish**: khi các con đã được tính chiều cao, tính `height(node)`.

```python
def all_heights_edges(root):
    if root is None:
        return {}

    heights = {}
    frames = [(root, False)]  # (node, ready)

    while frames:
        node, ready = frames.pop()

        if ready:
            # Tại đây chiều cao của mọi con đều đã có.
            heights[node] = 1 + max(
                (heights[child] for child in node.children),
                default=-1
            )
        else:
            # Frame cha cần hoàn tất SAU các frame con.
            frames.append((node, True))
            for child in reversed(node.children):
                frames.append((child, False))

    return heights


heights = all_heights_edges(root)

for name in "RABCDEFG":
    print(name, heights[nodes[name]])

# R 3
# A 2
# B 1
# C 0
# D 0
# E 1
# F 0
# G 0

print(heights[root])  # 3: chiều cao của cả cây
```

**Bất biến quan trọng:** khi lấy ra frame `(node, True)`, các frame con của `node` đã hoàn tất; vì thế bảng `heights` chứa chiều cao của **mọi con trực tiếp**. Ta chỉ cần lấy max của chúng rồi cộng một.

Mỗi nút sinh một frame enter, một frame finish và được xử lý số lần hằng số. Tổng số mục con được xem là `n-1` nên **`O(n)` thời gian**. Bảng `heights` có `n` mục; stack các frame có thể có `O(n)` phần tử trong trường hợp cây rất rộng, do đó **`O(n)` bộ nhớ bổ sung**.

Với cấu trúc chỉ dùng một con ở mỗi cấp, phương án lặp vẫn lưu nhiều frame đang chờ, nhưng tránh giới hạn đệ quy của Python. Đổi lại, nó không phải tự động tiết kiệm bộ nhớ hơn cách đệ quy, vì vẫn lưu trạng thái cần quay về.

### 12.3. Đối chiếu độ sâu và chiều cao trong cùng một bảng

Từ các hàm trên:

| Nút | Depth theo cạnh | Height theo cạnh | Height theo nút | Child degree | Graph degree |
|---|---:|---:|---:|---:|---:|
| `R` | 0 | 3 | 4 | 3 | 3 |
| `A` | 1 | 2 | 3 | 2 | 3 |
| `B` | 1 | 1 | 2 | 1 | 2 |
| `C` | 1 | 0 | 1 | 0 | 1 |
| `D` | 2 | 0 | 1 | 0 | 1 |
| `E` | 2 | 1 | 2 | 1 | 2 |
| `F` | 2 | 0 | 1 | 0 | 1 |
| `G` | 3 | 0 | 1 | 0 | 1 |

Bảng là cách hiệu quả để kiểm tra một cài đặt: cùng một nút phải có các đại lượng thỏa đúng định nghĩa, không suy ra chiều cao chỉ từ độ sâu hay bậc.

## 13. Tính bậc, số lá và bất biến tổng số cạnh

Với cây có gốc `n \ge 1` nút và chỉ có cạnh cha–con:

\[
\sum_{u\in V}\deg_{\mathrm{rooted}}(u)=n-1,
\]

và trong góc nhìn vô hướng:

\[
\sum_{u\in V}\deg_{\mathrm{graph}}(u)=2(n-1).
\]

Có thể kiểm tra hai đẳng thức bằng cách duyệt các nút đã tìm được:

```python
def degree_summary(root):
    if root is None:
        return {
            "nodes": 0,
            "leaves": 0,
            "internal": 0,
            "sum_child_degree": 0,
            "sum_graph_degree": 0,
            "max_child_degree": 0,
        }

    stack = [root]
    nodes = 0
    leaves = 0
    internal = 0
    sum_child_degree = 0
    sum_graph_degree = 0
    max_child_degree = 0

    while stack:
        node = stack.pop()
        nodes += 1

        count = node.child_degree()
        sum_child_degree += count
        sum_graph_degree += node.graph_degree()
        max_child_degree = max(max_child_degree, count)

        if count == 0:
            leaves += 1
        else:
            internal += 1

        stack.extend(node.children)

    return {
        "nodes": nodes,
        "leaves": leaves,
        "internal": internal,
        "sum_child_degree": sum_child_degree,
        "sum_graph_degree": sum_graph_degree,
        "max_child_degree": max_child_degree,
    }


summary = degree_summary(root)
print(summary)
# {
#   'nodes': 8, 'leaves': 4, 'internal': 4,
#   'sum_child_degree': 7, 'sum_graph_degree': 14,
#   'max_child_degree': 3
# }

assert summary["sum_child_degree"] == summary["nodes"] - 1
assert summary["sum_graph_degree"] == 2 * (summary["nodes"] - 1)
assert summary["nodes"] == summary["leaves"] + summary["internal"]
```

Những đẳng thức **cần thiết** cho một cây hợp lệ, nhưng **không đủ** để phát hiện mọi lỗi cấu trúc. Nếu các liên kết bị sửa ngoài API, có thể xuất hiện chu trình và các thành phần tách biệt nhưng một số tổng vẫn bằng giá trị dự kiến. Để xác minh cấu trúc thực sự là cây, cần kiểm tra thêm **một gốc, mỗi nút không phải gốc đúng một cha, tính liên thông và không có chu trình**.

Với cây tổng quát không rỗng, gọi `I` là số nút trong và `L` là số lá, ta có `n=I+L`. Nếu cây nhị phân **đầy đủ theo nghĩa mọi nút trong có đúng hai con**, thì:

\[
n-1=2I,\quad n=I+L
\quad\Longrightarrow\quad L=I+1.
\]

Công thức `L=I+1` **không đúng cho mọi cây**. Chẳng hạn, một chuỗi gồm bốn nút có ba nút trong và một lá, không thỏa công thức này.

## 14. Chọn gốc mới sẽ làm thay đổi điều gì?

Xét cây vô hướng bên dưới:

```text
R–A, R–B, R–C, A–D, A–E, B–F, E–G
```

Khi chọn `R` làm gốc, chiều cao là `3` cạnh, nút `G` có depth `3`.

Nếu **chọn `C` làm gốc** thay vì `R`, đường đi từ `C` tới `G` là:

```text
C → R → A → E → G
```

Đường đó dài `4` cạnh, và là một đường sâu nhất từ gốc `C`. Do đó:

- `depth_new(C)=0`.
- `depth_new(R)=1`.
- `depth_new(G)=4`.
- Chiều cao cây theo gốc `C` là `4` cạnh.
- `C` không còn là lá theo nghĩa **không có con**: nó có con `R`.
- Bậc vô hướng của `C` vẫn bằng `1` vì **không thay đổi cạnh**.

Kết luận:

| Đại lượng | Có thể thay đổi khi chọn gốc khác? | Lý do |
|---|---|---|
| Depth của nút | Có | Đường từ gốc mới tới nút có độ dài khác |
| Height của nút/cả cây | Có | Hướng đi xuống các cây con thay đổi |
| Child degree | Có | Một cạnh có thể chuyển vai trò cha ↔ con |
| Graph degree | **Không** | Tập cạnh kề mỗi đỉnh giữ nguyên |
| Số đỉnh, số cạnh | **Không** | Không thêm hoặc xóa liên kết |
| Đường đi đơn giữa hai đỉnh | **Không** | Vẫn là cây vô hướng ban đầu |

Trong ứng dụng thực tế, việc đổi gốc có thể thay đổi **ngữ nghĩa** của dữ liệu phân cấp, chẳng hạn ai quản lý ai hoặc thư mục nào chứa thư mục nào; không nên tùy ý đổi gốc chỉ vì phép đổi hợp lệ về lý thuyết đồ thị.

## 15. Cập nhật cây và duy trì các đại lượng

Các giá trị depth, height và degree **không bất biến qua mọi chỉnh sửa cây**. Nếu ứng dụng lưu sẵn các giá trị này, phải biết cách cập nhật chúng.

### 15.1. Thêm một lá mới

Giả sử thêm nút `H` làm con của `C` trong cây mẫu:

- `child_degree(C)` tăng từ `0` lên `1`.
- `C` từ lá trở thành nút trong; `H` là lá mới.
- `depth(H)=depth(C)+1=2`.
- `height(C)` tăng từ `0` lên `1`.
- Chiều cao của gốc **có thể không đổi**: nhánh mới dài `2` cạnh từ `R`, ngắn hơn nhánh `R→A→E→G` dài `3` cạnh.

Nếu thêm một lá vào **đường đang sâu nhất** khiến đường đó kéo dài, chiều cao gốc có thể tăng `1`.

### 15.2. Xóa một lá

Khi xóa một lá, số con của cha giảm một. Nếu cha không còn con, nó trở thành lá mới. Chiều cao các tổ tiên **có thể giảm**, nhưng không nhất thiết giảm:

- Nếu xóa một lá không nằm trên bất kỳ đường sâu nhất của một tổ tiên, chiều cao tổ tiên đó không đổi.
- Nếu xóa lá duy nhất làm một nhánh sâu nhất bị rút ngắn, chiều cao của một số tổ tiên có thể giảm.
- Nếu còn một nhánh **khác cùng chiều cao**, xóa một nhánh không làm chiều cao của tổ tiên giảm.

Vì chiều cao là **max của chiều cao các con**, không thể chỉ trừ `1` vào chiều cao tất cả tổ tiên một cách máy móc.

### 15.3. Chuyển cây con sang cha khác

Giả sử chuyển cây con gốc `u` từ cha cũ sang cha mới `v`, với điều kiện `v` không nằm trong cây con của `u`:

- Depth của **mọi nút trong cây con của `u`** có thể đổi bởi một lượng chênh lệch.
- Height của các nút **bên trong cây con `u`** không đổi nếu các cạnh nội bộ không đổi.
- Height của tổ tiên ở **đường cha cũ và đường cha mới** có thể thay đổi.
- Child degree của **cha cũ giảm một**, của **cha mới tăng một**.
- Bậc đồ thị vô hướng của hai cha đó thay đổi; bậc vô hướng của `u` có thể giữ nguyên nếu nó vẫn có đúng một cha.

**Chi phí cập nhật:** cập nhật depth cho toàn bộ một cây con có `s` nút cần `O(s)` nếu lưu depth trực tiếp ở từng nút. Nếu muốn cập nhật các height đã lưu, có thể phải xét lại các giá trị max trên các đường tổ tiên; chi phí phụ thuộc số nút và số con cần kiểm tra. Tính lại tất cả độ sâu/chiều cao bằng các phép duyệt `O(n)` thường là phương án đơn giản, an toàn cho cây không quá lớn.

### 15.4. Cache giúp truy vấn nhanh nhưng có cái giá của tính nhất quán

Nếu không lưu sẵn:

- Độ sâu một nút được tính bằng cách lần theo cha, `O(h)`.
- Chiều cao một cây con có thể phải duyệt tất cả nút trong cây con, `O(s)`.
- Số con thường sẵn qua `len(children)`, `O(1)` nếu dùng `list` Python.

Nếu **lưu cache depth hoặc height** tại từng nút, truy vấn có thể nhanh thành `O(1)`, nhưng khi cập nhật cấu trúc phải **duy trì cache đúng**. Bất biến cache sai sẽ gây ra kết quả sai âm thầm. Khi tần suất truy vấn thấp hoặc cây ít nút, tính theo yêu cầu có thể đơn giản và đáng tin cậy hơn.

## 16. Độ phức tạp và cách chọn phương pháp

Gọi `n` là số nút của cây, `h` là chiều cao theo cạnh, `s` là số nút trong cây con được xét, và `k` là số con trực tiếp của một nút.

| Tác vụ | Thời gian | Bộ nhớ phụ | Điều kiện/ghi chú |
|---|---|---|---|
| Đọc child degree với `len(children)` | `O(1)` | `O(1)` | Có sẵn tham chiếu nút và danh sách con |
| Tính graph degree từ parent/children | `O(1)` | `O(1)` | Chỉ có cạnh cha–con |
| Tính depth của một nút bằng parent | `O(depth(u))`, tối đa `O(h)` | `O(1)` | Quan hệ cha hợp lệ |
| Tính depth tất cả nút bằng DFS/BFS | `O(n)` | `O(n)` để lưu bảng kết quả | Duyệt một lần |
| Tính height của một cây con bằng đệ quy | `O(s)` | `O(h_s+1)` call stack | Có thể gặp giới hạn đệ quy |
| Tính height tất cả nút bằng postorder lặp | `O(n)` | `O(n)` | Frame chờ + bảng kết quả |
| Duyệt toàn bộ cây để thống kê bậc | `O(n)` | Tối đa `O(n)` cho stack công việc | Bậc từng nút xem `O(1)` |
| Tìm nút theo giá trị khi chưa có chỉ mục | Tối đa `O(n)` | Theo cách duyệt | Khác với việc đã có tham chiếu nút |

**Phân tích bộ nhớ không chỉ là số dòng mã.** Một hàm đệ quy ngắn có thể cần `O(h)` khung đang hoạt động. Trên một cây rất sâu, `h` có thể tỷ lệ với `n`; trên một cây rất rộng, một stack tường minh thêm tất cả con cùng lúc cũng có thể tốn `O(n)` phần tử chờ.

**Độ cao theo nút** và **theo cạnh** khác nhau đúng `1` trên cây không rỗng, nên có cùng cấp độ tiệm cận trong phân tích Big-O; nhưng sự khác biệt này vẫn quan trọng khi **so sánh kết quả số nguyên, xác định base case và đánh giá giới hạn chiều cao**.

## 17. Các lỗi thường gặp

1. **Không nêu quy ước chiều cao.** Cây một nút có height `0` theo cạnh và `1` theo nút; chọn sai base case dẫn đến lỗi lệch một.
2. **Nhầm depth với height.** Depth tính từ gốc; height tính từ nút xuống lá xa nhất.
3. **Gán height của lá bằng `1` nhưng lại áp dụng công thức height theo cạnh.** Đây là trộn quy ước.
4. **Gọi level mà không ghi gốc bắt đầu từ `0` hay `1`.** Hai hệ đánh số khác nhau một đơn vị.
5. **Dùng số con làm bậc đồ thị của mọi đỉnh.** Nút không phải gốc còn có một cạnh tới cha.
6. **Cho rằng gốc có bậc bằng `0` vì không có cha.** Gốc có thể có nhiều con; bậc theo số con và bậc vô hướng của gốc đều bằng số con.
7. **Cho rằng lá luôn là nút ở tầng sâu nhất.** Có thể có lá ở nhiều độ sâu khác nhau.
8. **Tính chiều cao bằng tổng chiều cao các con.** Cần lấy **max**, không lấy tổng.
9. **Cho rằng depth và height cộng lại luôn bằng height của cây.** Điều đó sai với các nút không nằm trên đường sâu nhất.
10. **Tưởng cây nhị phân luôn cao `O(\log n)`.** Cây lệch vẫn có chiều cao `n-1`.
11. **Cho rằng giá trị height không thay đổi khi đổi gốc.** Cách định hướng cạnh cha–con thay đổi có thể đổi chiều cao toàn cây.
12. **Tính height mỗi nút bằng một lần duyệt riêng biệt.** Có thể lặp công việc tới `O(n²)` trên cây dạng chuỗi; tính bottom-up một lượt sẽ `O(n)`.
13. **Cập nhật cấu trúc nhưng quên sửa cache.** Depth các hậu duệ hoặc height các tổ tiên có thể không còn đúng.
14. **Dùng công thức tổng bậc làm chứng minh duy nhất rằng dữ liệu là cây.** Cần bảo đảm không có chu trình và các nút liên thông qua một gốc.
15. **Bỏ qua trường hợp cây rỗng.** Chọn `height_edges(None)=-1` và `height_nodes(None)=0` trong bài này, nhưng phải nói rõ khi đưa vào API.

## 18. Tự kiểm tra bằng các phép thử

Các đoạn dưới dùng các lớp và hàm Python đã định nghĩa ở phần trên; chúng mô tả những tình huống nên được kiểm thử khi thực hành.

```python
# Cây mẫu R, A, B, C, D, E, F, G:
assert depth_from_parents(root) == 0
assert depth_from_parents(nodes["G"]) == 3

assert height_edges_recursive(root) == 3
assert height_nodes_recursive(root) == 4
assert height_edges_recursive(nodes["C"]) == 0
assert height_nodes_recursive(nodes["C"]) == 1

all_depth = all_depths(root)
all_height = all_heights_edges(root)
assert max(all_depth.values()) == all_height[root]
assert all_height[nodes["E"]] == 1

assert root.child_degree() == 3
assert nodes["A"].child_degree() == 2
assert nodes["A"].graph_degree() == 3
assert nodes["C"].child_degree() == 0
assert nodes["C"].graph_degree() == 1

single = Node("single")
assert single.child_degree() == 0
assert single.graph_degree() == 0
assert depth_from_parents(single) == 0
assert height_edges_recursive(single) == 0
assert height_nodes_recursive(single) == 1

assert height_edges_recursive(None) == -1
assert height_nodes_recursive(None) == 0
assert all_depths(None) == {}
assert all_heights_edges(None) == {}
```

Các phép `assert` là ví dụ tự kiểm tra khi học; chúng không thay thế việc kiểm thử đầu vào không hợp lệ, cây rất sâu, thay đổi cha–con hoặc tương tác đồng thời trong ứng dụng thực tế.

## 19. Bài tập thực hành có đáp án

### Bài 1. Depth và height trên cây mẫu

Tính `depth(E)`, `depth(G)`, `height(E)` và `height(R)` theo quy ước đếm **số cạnh**.

**Đáp án:** `depth(E)=2`; `depth(G)=3`; `height(E)=1` vì từ `E` tới `G` có một cạnh; `height(R)=3` do đường sâu nhất `R→A→E→G` có ba cạnh.

### Bài 2. Cây một nút và cây rỗng

Cho một cây chỉ có nút `X`. Chiều cao theo cạnh và theo nút bằng bao nhiêu? Theo quy ước của bài, cây rỗng có chiều cao lần lượt là bao nhiêu?

**Đáp án:** Cây chỉ có `X`: `H_e=0` và `H_v=1`. Cây rỗng: `H_e=-1` và `H_v=0`.

### Bài 3. Cùng độ sâu khác chiều cao

Hai nút `A` và `B` trong cây mẫu cùng có depth bằng `1`. Chiều cao của chúng là bao nhiêu? Có thể suy ra height từ depth không?

**Đáp án:** `height(A)=2` và `height(B)=1`. Không thể suy ra height của một nút chỉ từ depth vì các cây con có thể sâu khác nhau.

### Bài 4. Bậc của nút

Trong cây mẫu, tính bậc theo số con và bậc vô hướng của `R`, `A`, `B` và `C`.

**Đáp án:** `R`: `3/3`; `A`: `2/3`; `B`: `1/2`; `C`: `0/1` (viết theo thứ tự bậc theo số con/bậc vô hướng).

### Bài 5. Kiểm tra tổng bậc

Cây có `n=8` nút và `7` cạnh. Tổng bậc theo số con và tổng bậc vô hướng lần lượt bằng bao nhiêu?

**Đáp án:** Tổng bậc theo số con là `n-1=7`; tổng bậc vô hướng là `2(n-1)=14`.

### Bài 6. Level đánh số từ 1

Nếu gốc `R` ở level `1`, nút `G` ở level mấy? Nếu đổi sang quy ước depth theo số cạnh từ gốc `0` thì giá trị là bao nhiêu?

**Đáp án:** `G` ở level `4` theo cách đánh số từ `1`; độ sâu theo cạnh là `3`.

### Bài 7. Cây dạng chuỗi

Cây có `10` nút, mỗi nút trừ nút cuối có đúng một con. Chọn một đầu làm gốc và xem cây là một chuỗi. Chiều cao theo cạnh và theo nút là bao nhiêu?

**Đáp án:** Chiều cao theo cạnh là `9`, theo nút là `10`. Bậc theo số con lớn nhất là `1`.

### Bài 8. Cây hình sao

Một gốc có `20` lá con trực tiếp, không có cạnh nào khác. Số nút, bậc theo số con của gốc và chiều cao theo cạnh là bao nhiêu?

**Đáp án:** Có `21` nút; bậc theo số con của gốc là `20`; chiều cao cây chỉ là `1` cạnh.

### Bài 9. Kiểm tra công thức cây nhị phân

Một cây nhị phân không rỗng có chiều cao theo cạnh `h=3`. Nó có tối đa bao nhiêu nút? Nếu có `8` nút thì có thể đạt chiều cao `2` không?

**Đáp án:** Tối đa `2^{3+1}-1=15` nút. Nếu chiều cao `2`, tối đa `2^{2+1}-1=7` nút; vậy cây có `8` nút **không thể** cao chỉ `2` cạnh.

### Bài 10. Chọn gốc mới

Giữ nguyên các cạnh trong cây mẫu, nhưng chọn `C` làm gốc. Độ sâu của `G` và chiều cao toàn cây theo số cạnh là bao nhiêu? Bậc vô hướng của `C` có đổi không?

**Đáp án:** `depth(G)=4`; chiều cao toàn cây theo gốc `C` là `4`. Bậc vô hướng của `C` vẫn bằng `1`, vì tập cạnh không đổi.

### Bài 11. Thêm một lá

Trong cây mẫu, thêm nút `H` làm con của `C`. Depth và height của `H` là bao nhiêu? Height của `R` có đổi không?

**Đáp án:** `depth(H)=2`; `height(H)=0` theo số cạnh. Chiều cao `R` vẫn là `3` vì nhánh mới có độ sâu tối đa `2`, nhỏ hơn đường tới `G`.

### Bài 12. Cache chiều cao

Một cây có gốc `R` với hai cây con cùng chiều cao `3` cạnh dưới hai con khác nhau. Nếu xóa một trong hai nhánh sâu nhất, chiều cao của `R` có chắc chắn giảm không?

**Đáp án:** Không. Nếu nhánh còn lại vẫn có chiều cao `3`, chiều cao của `R` vẫn là `1+3=4`. Chỉ khi **mọi** nhánh từng đạt cực đại bị rút ngắn thì chiều cao gốc mới giảm tương ứng.

### Bài 13. Phân tích truy vấn

Một ứng dụng cần hỏi `depth(u)` một lần cho vài nút và cây hiếm khi thay đổi. Một ứng dụng khác hỏi độ sâu của **mọi nút** sau mỗi lần tải dữ liệu. Hướng tính nào phù hợp?

**Đáp án:** Với một vài truy vấn và có liên kết `parent`, đi ngược về gốc cho từng nút đơn giản, mất `O(depth(u))`. Với tất cả nút, duyệt DFS/BFS một lần từ gốc và lập bảng độ sâu, tốn `O(n)` thời gian, thuận lợi cho truy vấn tiếp theo. Nếu cây thường xuyên sửa, phải cân nhắc chi phí cập nhật bảng.

### Bài 14. Phân biệt độ sâu của cây và call stack

Một hàm đệ quy duyệt cây bằng cách gọi chính nó cho mỗi con; cây có chiều cao `h` cạnh. Số lời gọi của hàm duyệt trên một đường đệ quy sâu nhất có thể là bao nhiêu nếu mỗi nút tạo một lời gọi?

**Đáp án:** `h+1` lời gọi tương ứng với `h+1` nút trên đường sâu nhất, không tính các khung khác của chương trình. Do đó chi phí stack của thuật toán thường là `O(h+1)`, có thể tăng tới `O(n)` khi cây lệch.

## 20. Tổng kết

**Độ sâu** của một nút đo đường từ **gốc tới nút**; **chiều cao** đo đường từ **nút xuống lá xa nhất**. Cả hai thường được tính theo **số cạnh**, nhưng chiều cao còn có quy ước đếm theo **số nút**: với cây không rỗng, hai kết quả khác nhau đúng `1`. Trong bài này, gốc có depth `0`, lá có height theo cạnh `0`, cây rỗng quy ước height theo cạnh `-1`.

**Bậc theo cây có gốc** là **số con trực tiếp**; **bậc đồ thị vô hướng** còn tính cạnh tới cha đối với nút không phải gốc. Vì cây có `n-1` cạnh, tổng bậc theo số con là `n-1`, tổng bậc vô hướng là `2(n-1)`.

Các đại lượng không thay thế cho nhau: cùng depth có thể khác height, bậc nhỏ vẫn có thể tạo cây rất sâu, và một nút nhiều con chưa chắc nằm sâu. Với yêu cầu truy vấn cụ thể, hãy chọn tính depth từ parent, dựng depth toàn cây bằng DFS/BFS, hoặc tính height từ dưới lên bằng postorder. Khi cập nhật cấu trúc, phải duy trì các **bất biến cha–con và giá trị đã lưu** để kết quả luôn đúng.
