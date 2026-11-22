# Tổ tiên nhảy bậc bằng binary lifting

## Mục tiêu học tập

**Binary lifting** (*nhảy bậc nhị phân*, *doubling*) là kỹ thuật tiền xử lý trong nhóm **Thuật toán trên cây**, dùng để trả lời nhanh câu hỏi:

> “Đỉnh nào là **tổ tiên bậc k** của đỉnh v?”

Thay vì đi từng cạnh cha từ v lên trên k lần, ta chuẩn bị trước tổ tiên cách v **1, 2, 4, 8, 16, ... cạnh**, rồi tách k thành tổng những lũy thừa của 2. Cách này thường có **tiền xử lý O(n log n)**, **bộ nhớ O(n log n)** và mỗi truy vấn **O(log n)** trong trường hợp xấu nhất, với n là số đỉnh. Nó đặc biệt hữu ích khi có rất nhiều truy vấn trên cùng một cây hoặc một rừng cố định.

Sau bài này, bạn sẽ có thể:

1. Phân biệt **cha trực tiếp**, **tổ tiên**, **tổ tiên bậc k**, **độ sâu**, **gốc** và **tổ tiên chung gần nhất** (*lowest common ancestor — LCA*).
2. Biểu diễn cây có gốc bằng `parent[v]`, hiểu điều kiện không chu trình và mỗi đỉnh chỉ có tối đa một cha.
3. Xây bảng `up[j][v]` là tổ tiên cách v `2^j` cạnh theo công thức **doubling**.
4. Trả lời truy vấn tổ tiên bậc k bằng **phân tích bit của k**, xử lý k=0, k lớn hơn độ sâu và tổ tiên không tồn tại.
5. Tiền xử lý cây bằng DFS/BFS **không đệ quy**, tránh lỗi tràn call stack khi cây là một đường rất sâu.
6. Mở rộng sang rừng có nhiều gốc, phát hiện parent input lỗi, self-parent hoặc chu trình.
7. Hiểu cách **nâng hai đỉnh lên cùng độ sâu** và tìm **LCA trong O(log n)** bằng cùng bảng nhảy.
8. Viết chương trình **Java 17+** hoàn chỉnh, có kiểm tra dữ liệu, các truy vấn xác định và stdout có thể kiểm chứng.
9. Chứng minh tính đúng, phân tích độ phức tạp, tránh tràn khi dịch bit và nhận ra trường hợp thuật toán không phù hợp.
10. Vận dụng cho khoảng cách theo số cạnh, kiểm tra quan hệ tổ tiên và các bài toán truy vấn tĩnh trên cây.

---

## 1. Mô hình cây có gốc

### 1.1. Từ cây vô hướng đến cây có gốc

Một **cây** là đồ thị vô hướng liên thông và không có chu trình. Với n đỉnh, cây có đúng n−1 cạnh (n≥1). Khi ta **chọn một đỉnh r làm gốc**, mọi đỉnh còn lại có một **cha trực tiếp** (*parent*) duy nhất: hàng xóm đi về phía r trên đường đi đơn duy nhất.

Ví dụ:

```text
           0
         /   \
        1     2
       / \   / \
      3   4 5   6
     / \    |   |
    7   8   9  10
```

Đây là cây đã chọn gốc 0, có 11 đỉnh. Ta có:

```text
parent[0] = -1
parent[1] = 0, parent[2] = 0
parent[3] = 1, parent[4] = 1
parent[5] = 2, parent[6] = 2
parent[7] = 3, parent[8] = 3
parent[9] = 5, parent[10] = 6
```

Quy ước `-1` nghĩa là **không có cha**; nó không phải một đỉnh thật. Nếu cây được đánh số 1-based, nhiều bài dùng 0 làm sentinel; cần chọn đúng một quy ước và nhất quán.

### 1.2. Cha và tổ tiên

- **Cha trực tiếp** của v là đỉnh có cạnh đi lên một bước.
- **Ông/bà** là tổ tiên bậc 2: cha của cha.
- **Tổ tiên bậc k** là đỉnh đạt được sau đúng k lần chuyển từ đỉnh hiện tại lên cha.
- **Gốc** không có cha; đi lên quá gốc cho kết quả không tồn tại.

Định nghĩa chính xác:

\[
ancestor(v,0)=v,
\]

\[
ancestor(v,k)=parent(ancestor(v,k-1))
\quad(k\ge1),
\]

trong đó nếu một bước trước đã không có đỉnh thì kết quả tiếp tục là **không tồn tại**.

**Quy ước k=0 quan trọng:** tổ tiên bậc 0 của v là **chính v**. Một số đề dùng cách đếm khác, nên luôn đọc định nghĩa bài toán trước khi áp dụng công thức.

### 1.3. Độ sâu

`depth[v]` là **số cạnh** từ gốc của cây tới v:

\[
depth[root]=0,\qquad
depth[child]=depth[parent]+1.
\]

Với cây trên:

```text
depth[0] = 0
depth[1] = depth[2] = 1
depth[3] = depth[4] = depth[5] = depth[6] = 2
depth[7] = depth[8] = depth[9] = depth[10] = 3
```

Đi tới tổ tiên bậc k làm độ sâu giảm đúng k nếu tổ tiên ấy tồn tại. Vì vậy:

\[
k>depth[v]\implies ancestor(v,k)=-1.
\]

Đây là cách kiểm tra biên rất hiệu quả trước khi đọc bất kỳ phần tử bảng nhảy nào.

### 1.4. Khi nào dùng “rừng”?

Một **rừng có gốc** (*rooted forest*) gồm nhiều cây rời nhau, mỗi cây có một gốc. Ví dụ bổ sung:

```text
    11
    |
    12
```

Khi ấy ta có **13 đỉnh**, hai cây riêng:

- Cây thứ nhất có gốc 0, chứa 0 đến 10.
- Cây thứ hai có gốc 11, chứa 11 và 12.

Binary lifting vẫn hoạt động **riêng trên mỗi cây**. Tổ tiên của v không thể nhảy sang cây khác. Nếu hỏi LCA của hai đỉnh thuộc hai cây khác nhau, câu trả lời phải là **không tồn tại**.

### 1.5. Không phải đồ thị nào cũng là cây cha

Một đồ thị tổng quát có chu trình hoặc một đỉnh có nhiều cha không tạo ngay được định nghĩa `parent[v]` nhất quán cho binary lifting. Nếu đầu vào là **đồ thị vô hướng**, phải xác định nó là cây/rừng và **chọn gốc** rồi duyệt để xây parent.

Nếu đầu vào là **DAG** có nhiều đường đi tới cùng một đỉnh, khái niệm “tổ tiên bậc k” dựa trên **một cha duy nhất** không tự xác định. Binary lifting dùng ở đây giả sử ta đã có **một quan hệ cha tạo rừng**, không phải tùy tiện lấy một hàng xóm làm cha ở một graph bất kỳ.

---

## 2. Giải pháp đơn giản: đi lên k lần

Nếu đã có mảng `parent[]`, cách trực tiếp là:

```text
kthAncestorNaive(v,k):
    if k < 0: báo lỗi
    repeat k lần:
        if v == -1:
            return -1
        v = parent[v]
    return v
```

Ví dụ với đỉnh 8:

```text
8 -> 3 -> 1 -> 0 -> -1
```

Suy ra:

```text
ancestor(8,0) = 8
ancestor(8,1) = 3
ancestor(8,2) = 1
ancestor(8,3) = 0
ancestor(8,4) = -1
```

### 2.1. Độ phức tạp

Một truy vấn mất `O(k)` phép nhảy cha trong trường hợp tổ tiên bậc k tồn tại, hoặc tối đa `O(depth[v]+1)` nếu ta dừng khi lên quá gốc. Nếu có q truy vấn cùng trên một cây dài n, cách trực tiếp có thể mất tới `O(qn)`.

Ví dụ cây là một đường có 100.000 đỉnh và có 100.000 câu hỏi tổ tiên bậc 80.000: việc nhảy từng bước dẫn tới hàng tỷ phép đọc mảng, không hiệu quả.

### 2.2. Khi nào cách đơn giản vẫn hợp lý?

Nếu chỉ có một vài truy vấn với k nhỏ, cách đi từng cha rất dễ viết, không cần bảng lớn. Binary lifting có chi phí tiền xử lý và bộ nhớ cao hơn, nên nó đặc biệt có lợi khi:

- Cây/rừng **ít thay đổi**.
- Có **nhiều truy vấn**.
- k có thể rất lớn.
- Cần thêm các phép toán như LCA, khoảng cách, hoặc tổng/min trên đường đi.

Không nên tự động dùng O(n log n) bộ nhớ nếu bài chỉ cần một phép hỏi k=1.

---

## 3. Ý tưởng doubling: từ 1 bước đến 2, 4, 8, ...

Thay vì chỉ lưu cha trực tiếp, ta lưu các **cú nhảy lũy thừa của 2**.

Định nghĩa:

\[
up[j][v]=\text{tổ tiên của }v\text{ cách }2^j\text{ cạnh}.
\]

Các mức:

| j | Độ dài bước nhảy | Ý nghĩa của `up[j][v]` |
| ---: | ---: | --- |
| 0 | 1 | Cha trực tiếp |
| 1 | 2 | Cha của cha |
| 2 | 4 | Tổ tiên cách 4 cạnh |
| 3 | 8 | Tổ tiên cách 8 cạnh |
| 4 | 16 | Tổ tiên cách 16 cạnh |
| j | `2^j` | Tổ tiên cách `2^j` cạnh |

Nếu tổ tiên ấy không tồn tại, ghi `-1`.

### 3.1. Cơ sở

Cấp 0 chính là mảng cha:

\[
\boxed{up[0][v]=parent[v].}
\]

Với gốc r, `up[0][r]=-1`.

### 3.2. Công thức quy hoạch động

Để nhảy `2^j` bước, thực hiện **hai lần nhảy `2^{j-1}` bước**:

\[
\boxed{
up[j][v]
=up[j-1]\bigl[up[j-1][v]\bigr].
}
\]

Chỉ áp dụng biểu thức bên phải khi `up[j-1][v]\ne-1`. Nếu bước thứ nhất không tồn tại thì:

\[
up[j][v]=-1.
\]

Giả mã:

```text
for v = 0..n-1:
    up[0][v] = parent[v]

for j = 1..LOG-1:
    for v = 0..n-1:
        mid = up[j-1][v]
        if mid == -1:
            up[j][v] = -1
        else:
            up[j][v] = up[j-1][mid]
```

Đừng đọc `up[j-1][-1]`. Giá trị `-1` là **sentinel**, không phải chỉ số mảng.

### 3.3. Tại sao công thức đúng?

Chứng minh bằng quy nạp theo j:

- j=0: `up[0][v]` là cha trực tiếp, đúng 1 bước.
- Giả sử `up[j-1][v]` là tổ tiên cách `2^{j-1}` bước.
- Nếu tổ tiên trung gian mid tồn tại, từ mid nhảy tiếp `2^{j-1}` bước đưa tới tổ tiên cách:

\[
2^{j-1}+2^{j-1}=2^j
\]

bước từ v.

Nếu mid không tồn tại, không thể có tổ tiên xa hơn. Vì vậy công thức đúng cho mọi j.

Đây chính là cơ chế **binary lifting**: dùng kết quả của bước ngắn hơn để xây trước bước dài hơn.

---

## 4. Bảng nhảy trên cây 13 đỉnh

Ta dùng rừng cố định có mảng cha:

```text
Index:   0   1  2  3  4  5  6  7  8  9 10 11 12
Parent: -1   0  0  1  1  2  2  3  3  5  6 -1 11
```

Hình cây:

```text
                 0                 11
              /     \               |
             1       2             12
           /  \    /   \
          3    4  5     6
         / \      |     |
        7   8     9    10
```

Các mức lên gốc của đỉnh 8:

```text
8 -> 3 -> 1 -> 0 -> -1
```

Bảng theo j cho một số đỉnh:

| v | `depth[v]` | `up[0][v]` (1) | `up[1][v]` (2) | `up[2][v]` (4) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | -1 | -1 | -1 |
| 1 | 1 | 0 | -1 | -1 |
| 2 | 1 | 0 | -1 | -1 |
| 3 | 2 | 1 | 0 | -1 |
| 4 | 2 | 1 | 0 | -1 |
| 5 | 2 | 2 | 0 | -1 |
| 6 | 2 | 2 | 0 | -1 |
| 7 | 3 | 3 | 1 | -1 |
| 8 | 3 | 3 | 1 | -1 |
| 9 | 3 | 5 | 2 | -1 |
| 10 | 3 | 6 | 2 | -1 |
| 11 | 0 | -1 | -1 | -1 |
| 12 | 1 | 11 | -1 | -1 |

Đỉnh sâu nhất chỉ sâu 3, nên tất cả `up[2][v]` (nhảy 4 cạnh) đều là `-1`. Ta vẫn có thể **cấp phát mức này**; nó hữu ích khi dùng một bảng kích thước dựa trên số đỉnh chứ không phải độ sâu thực tế.

### 4.1. Ví dụ tự tính ô bảng

Với v=8:

\[
up[0][8]=parent[8]=3,
\]

\[
up[1][8]=up[0][up[0][8]]
=up[0][3]=1,
\]

\[
up[2][8]=up[1][up[1][8]]
=up[1][1]=-1.
\]

Với v=9:

\[
up[0][9]=5,\quad
up[1][9]=parent[5]=2.
\]

Với v=12 thuộc cây gốc 11:

\[
up[0][12]=11,\quad up[1][12]=-1.
\]

Cần đặc biệt nhớ `up[1][9]=2`, **không phải 0**: mức j=1 nghĩa là **2 cạnh**, còn từ 9 lên 0 cần 3 cạnh.

---

## 5. Chọn số mức LOG như thế nào?

Với n đỉnh, một cây có gốc sâu nhất không quá n−1. Tổ tiên xa nhất từ một đỉnh cũng chỉ cách tối đa n−1 cạnh.

Ta cần đủ các bit để biểu diễn mọi k hợp lệ (≤n−1). Một lựa chọn dễ cài:

```text
LOG = 1
while 2^LOG <= n:
    LOG++
```

Bảng có các mức `0..LOG-1`.

Ví dụ:

- n=1: LOG=1, có mức j=0.
- n=2: LOG=2, có j=0,1 (thêm một mức không gây hại).
- n=13: LOG=4, có j=0,1,2,3.
- n=100000: LOG=17, có j=0 đến 16 (vì `2^{16}=65536`, `2^{17}=131072`).

Một số cài đặt dùng `LOG=ceil(log2(n))+1` để dư thêm một mức. Cách nào cũng đúng nếu bảng đủ bit và không truy cập vượt chỉ số.

### 5.1. Không dùng dịch bit int tùy tiện

Trong Java, `1<<j` dùng kiểu `int`. Với j lớn, kết quả có thể tràn dấu hoặc hành vi dịch không tương ứng trực giác về lũy thừa cần tính.

Dùng:

```java
long step = 1L << j;
```

và giới hạn j hợp lý. Với số đỉnh của mảng Java là một `int` không âm, `LOG` thường không vượt khoảng 31; `1L<<LOG` an toàn trong miền này.

Trong chương trình mẫu, điều kiện xác định mức là:

```java
int levels = 1;
while ((1L << levels) <= n) {
    levels++;
}
```

Trường hợp n=0 vẫn cấp một mức nhưng bảng có **0 cột** và không cho phép truy vấn đỉnh; điều này làm API rừng rỗng rõ ràng.

### 5.2. LOG không phải số lần được phép đi lên

Có LOG=4 không nghĩa chỉ được nhảy tối đa 4 cạnh. Nó nghĩa có các **bước nhảy độ dài 1,2,4,8**; kết hợp các bước cho một k lớn hơn, chẳng hạn 13=8+4+1 nếu độ sâu cây đủ.

---

## 6. Truy vấn tổ tiên bậc k bằng bit của k

Mọi số nguyên không âm k biểu diễn được dưới dạng tổng lũy thừa của 2:

\[
k=\sum_{j\ge0}b_j2^j,\quad b_j\in\{0,1\}.
\]

Nếu bit j của k là 1, ta thực hiện một bước nhảy `2^j` bằng `up[j][v]`.

### 6.1. Giả mã

```text
kthAncestor(v,k):
    nếu v ngoài [0,n): báo lỗi
    nếu k < 0: báo lỗi
    nếu k > depth[v]: return -1

    bit = 0
    while k > 0:
        if (k & 1) == 1:
            v = up[bit][v]

        k = k >> 1
        bit++

    return v
```

Điều kiện `k>depth[v]` bảo đảm ta không cần truy cập bit vượt bảng và không cố nhảy quá gốc.

### 6.2. Ví dụ với k=3

`3` trong nhị phân là `11₂`:

\[
3=2^1+2^0.
\]

Để hỏi `ancestor(8,3)`:

1. Bit 0 bằng 1: từ 8 nhảy 1 cạnh tới 3.
2. Bit 1 bằng 1: từ 3 nhảy 2 cạnh tới 0.
3. Kết quả 0.

Tương đương nhìn đường cha:

```text
8 -> 3 -> 1 -> 0
  1 bước   2 bước từ 3
```

### 6.3. Ví dụ với k=13

`13=8+4+1=1101₂`. Nếu ở một cây đủ sâu, ta có thể:

- Nhảy `2^0=1` cạnh.
- Nhảy `2^2=4` cạnh.
- Nhảy `2^3=8` cạnh.

Tổng là 13 cạnh; số lần truy cập bảng chỉ là **3**, thay vì 13 lần đọc cha. Thứ tự thực hiện các bước không ảnh hưởng tổ tiên cuối cùng vì mỗi thao tác chỉ đi lên đường cha duy nhất.

### 6.4. Kết quả cho đỉnh 8

```text
ancestor(8,0) = 8
ancestor(8,1) = 3
ancestor(8,2) = 1
ancestor(8,3) = 0
ancestor(8,4) = -1
```

Đỉnh 8 sâu 3; k=4 vượt độ sâu, nên trả `-1` ngay không cần đọc bảng.

### 6.5. Truy vấn k cực lớn

Một số bài cho k đến `10^18` hoặc nhập bằng kiểu `long`, trong khi cây chỉ có 100.000 đỉnh. Ta không cần xây bảng tới bit 60 nếu truy vấn là **tổ tiên trong cây hữu hạn**:

\[
k>depth[v]\Longrightarrow -1.
\]

Do đó ta có thể loại k quá lớn **trước khi xử lý bit**, giúp số mức chỉ phụ thuộc n, không phụ thuộc giá trị k tối đa trong truy vấn.

Nếu bài không có độ sâu hoặc đang xét một **đồ thị hàm** (*functional graph*) với chu trình, không được dùng trực tiếp kết luận này: đi theo ánh xạ “cha” có thể quay vòng mãi. Đó là một bài toán khác và có thể cần mức nhảy tới 60 bit.

---

## 7. Xây parent, depth và bảng up không đệ quy

Nếu đầu vào đã có mảng `parent[]` hợp lệ, có thể dùng mảng ấy dựng các danh sách **con** của mỗi đỉnh:

```text
for v trong [0,n):
    if parent[v] != -1:
        children[parent[v]].add(v)
```

Sau đó thực hiện BFS từ **mọi gốc** để tính depth và xác định mỗi đỉnh thuộc cây nào.

### 7.1. Xây depth bằng BFS

```text
queue = empty

for v = 0..n-1:
    if parent[v] == -1:
        depth[v] = 0
        componentRoot[v] = v
        queue.pushBack(v)

while queue không rỗng:
    v = queue.popFront()

    for child trong children[v]:
        depth[child] = depth[v] + 1
        componentRoot[child] = componentRoot[v]
        queue.pushBack(child)
```

Trong một **rừng cha hợp lệ**, mỗi đỉnh xuất hiện đúng một lần trong một danh sách con (trừ các gốc). BFS đi từ các gốc sẽ gặp **mọi đỉnh** đúng một lần.

### 7.2. Phát hiện parent input có chu trình

Đầu vào cần thỏa:

- Mỗi `parent[v]` hoặc là `-1`, hoặc là id đỉnh hợp lệ `0..n−1`.
- Không có `parent[v]=v`.
- Mọi chuỗi cha cuối cùng phải tới một gốc `-1`; không có chu trình.

Với quan hệ **mỗi đỉnh có tối đa một cha**, mọi đỉnh trên chu trình đều **không thể** đi về một gốc qua các liên kết cha. Do đó sau BFS từ mọi gốc, nếu số đỉnh đã thăm **nhỏ hơn n**, input chứa một hoặc nhiều chu trình cha (sau khi đã kiểm tra phạm vi parent).

Ví dụ sai:

```text
parent = [1,2,0]
```

Lúc này:

```text
0 -> parent 1 -> parent 2 -> parent 0
```

Không có gốc. BFS từ gốc không thăm được đỉnh nào, nên phải **từ chối**, không nên tiền xử lý bảng up cho cấu trúc ấy rồi coi là cây.

### 7.3. Tại sao tránh DFS đệ quy để xây depth?

Nếu cây là một đường có 200.000 đỉnh, gọi DFS đệ quy đi sâu theo đường ấy có thể gây `StackOverflowError` trên JVM do giới hạn thread stack.

BFS bằng `ArrayDeque<Integer>` hoặc DFS bằng stack tường minh tránh phụ thuộc vào độ sâu call stack. Tổng thời gian dựng danh sách con và depth là `O(n)` với parent input hợp lệ.

### 7.4. Từ adjacency vô hướng đến parent

Nếu đề cho n đỉnh và n−1 cạnh vô hướng, phải:

1. Kiểm tra graph thật sự liên thông và không chu trình, hoặc xác định nó là rừng theo yêu cầu.
2. Chọn gốc r.
3. Duyệt BFS/DFS từ r, gán `parent[r]=-1` và `parent[child]=v` chỉ khi child chưa thăm.
4. Tính depth và dựng bảng up.

Đừng lầm danh sách hàng xóm của một đỉnh với danh sách **cha**: trên cây vô hướng, mỗi cạnh được lưu hai chiều; một hàng xóm có thể là con **hoặc** cha tùy gốc.

---

## 8. Java 17+ — triển khai đầy đủ và đầu ra xác định

Ví dụ sau nhận **mảng parent của rừng có gốc**. Nó:

1. Kiểm tra id cha không hợp lệ, tự làm cha và chu trình.
2. Tạo danh sách con, dùng BFS từ mọi gốc để tính độ sâu và id gốc thành phần.
3. Tính `up[j][v]` bằng doubling.
4. Trả lời `kthAncestor(v,k)` với k kiểu `long`; k=0 trả v, k quá độ sâu trả -1.
5. Hỗ trợ `lca(a,b)` và số cạnh trên đường đi `distanceEdges(a,b)`.
6. Có thể đọc một phần tử bảng bằng `powerAncestor(v,j)`.
7. Trả bản sao của các mảng khi in để tránh người gọi vô tình sửa cấu trúc bên trong.

Tệp: **`BinaryLiftingAncestorsDemo.java`**.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class BinaryLiftingAncestorsDemo {

    public static final class ForestIndex {
        private final int n;
        private final int levels;
        private final int[] parent;
        private final int[] depth;
        private final int[] componentRoot;
        private final int[][] up;

        public ForestIndex(int[] parentInput) {
            Objects.requireNonNull(parentInput, "parentInput");

            this.parent = parentInput.clone();
            this.n = parent.length;

            List<List<Integer>> children = new ArrayList<>(n);
            for (int v = 0; v < n; v++) {
                children.add(new ArrayList<>());
            }

            // Each vertex has one parent or -1 as a root.
            for (int v = 0; v < n; v++) {
                int p = parent[v];
                if (p < -1 || p >= n || p == v) {
                    throw new IllegalArgumentException(
                            "invalid parent of vertex " + v);
                }

                if (p != -1) {
                    children.get(p).add(v);
                }
            }

            int levelCount = 1;
            while ((1L << levelCount) <= n) {
                levelCount++;
            }
            this.levels = levelCount;

            up = new int[levels][n];
            for (int[] row : up) {
                Arrays.fill(row, -1);
            }

            depth = new int[n];
            componentRoot = new int[n];
            Arrays.fill(componentRoot, -1);

            ArrayDeque<Integer> queue = new ArrayDeque<>();

            // Start BFS from every root of the forest.
            for (int v = 0; v < n; v++) {
                if (parent[v] == -1) {
                    componentRoot[v] = v;
                    queue.addLast(v);
                }
            }

            int reached = 0;

            while (!queue.isEmpty()) {
                int v = queue.removeFirst();
                reached++;

                up[0][v] = parent[v];

                for (int child : children.get(v)) {
                    depth[child] = depth[v] + 1;
                    componentRoot[child] = componentRoot[v];
                    queue.addLast(child);
                }
            }

            // A component without a root contains a
            // parent cycle and cannot be a rooted tree.
            if (reached != n) {
                throw new IllegalArgumentException(
                        "parent relation contains a cycle");
            }

            // Doubling: 2^j = 2^(j-1) + 2^(j-1).
            for (int j = 1; j < levels; j++) {
                for (int v = 0; v < n; v++) {
                    int mid = up[j - 1][v];

                    up[j][v] = (mid == -1)
                            ? -1
                            : up[j - 1][mid];
                }
            }
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "vertex out of range: " + v);
            }
        }

        public int size() {
            return n;
        }

        public int levels() {
            return levels;
        }

        public int[] parents() {
            return parent.clone();
        }

        public int[] depths() {
            return depth.clone();
        }

        public int[] componentRoots() {
            return componentRoot.clone();
        }

        // For inspection: ancestor at distance 2^power.
        public int powerAncestor(int v, int power) {
            checkVertex(v);
            if (power < 0) {
                throw new IllegalArgumentException(
                        "negative power");
            }
            if (power >= levels) {
                return -1;
            }
            return up[power][v];
        }

        // 0th ancestor = the vertex itself.
        public int kthAncestor(int v, long k) {
            checkVertex(v);

            if (k < 0) {
                throw new IllegalArgumentException(
                        "negative ancestor count");
            }

            // Also avoids accessing bits beyond the table.
            if (k > depth[v]) {
                return -1;
            }

            int bit = 0;

            while (k != 0) {
                if ((k & 1L) != 0L) {
                    v = up[bit][v];
                }

                k >>>= 1;
                bit++;
            }

            return v;
        }

        // Lowest common ancestor in the same rooted tree.
        // Returns -1 for vertices in different trees.
        public int lca(int a, int b) {
            checkVertex(a);
            checkVertex(b);

            if (componentRoot[a] != componentRoot[b]) {
                return -1;
            }

            if (depth[a] < depth[b]) {
                int temp = a;
                a = b;
                b = temp;
            }

            a = kthAncestor(a, depth[a] - depth[b]);

            if (a == b) {
                return a;
            }

            for (int j = levels - 1; j >= 0; j--) {
                if (up[j][a] != up[j][b]) {
                    a = up[j][a];
                    b = up[j][b];
                }
            }

            return up[0][a];
        }

        // Distance measured in number of edges.
        // -1 when vertices are in different trees.
        public long distanceEdges(int a, int b) {
            int c = lca(a, b);

            if (c == -1) {
                return -1L;
            }

            return (long) depth[a] + depth[b]
                    - 2L * depth[c];
        }
    }

    public static void main(String[] args) {
        // First tree rooted at 0, second tree rooted at 11.
        int[] parent = {
                -1, 0, 0, 1, 1, 2, 2,
                 3, 3, 5, 6, -1, 11
        };

        ForestIndex index = new ForestIndex(parent);

        System.out.println(
                "Parents: " + Arrays.toString(index.parents()));
        System.out.println(
                "Depths: " + Arrays.toString(index.depths()));
        System.out.println(
                "Component roots: "
                        + Arrays.toString(index.componentRoots()));
        System.out.println(
                "Table levels: " + index.levels());

        System.out.println(
                "up[0][8]: " + index.powerAncestor(8, 0));
        System.out.println(
                "up[1][8]: " + index.powerAncestor(8, 1));
        System.out.println(
                "up[2][8]: " + index.powerAncestor(8, 2));

        for (int k = 0; k <= 4; k++) {
            System.out.println(
                    "ancestor(8," + k + "): "
                            + index.kthAncestor(8, k));
        }

        System.out.println(
                "ancestor(9,2): "
                        + index.kthAncestor(9, 2));
        System.out.println(
                "ancestor(12,1): "
                        + index.kthAncestor(12, 1));
        System.out.println(
                "ancestor(12,2): "
                        + index.kthAncestor(12, 2));
        System.out.println(
                "ancestor(8,1000000000000): "
                        + index.kthAncestor(8, 1_000_000_000_000L));

        System.out.println(
                "lca(7,8): " + index.lca(7, 8));
        System.out.println(
                "lca(7,4): " + index.lca(7, 4));
        System.out.println(
                "lca(9,10): " + index.lca(9, 10));
        System.out.println(
                "lca(7,10): " + index.lca(7, 10));
        System.out.println(
                "lca(8,12): " + index.lca(8, 12));
        System.out.println(
                "lca(5,9): " + index.lca(5, 9));
        System.out.println(
                "lca(11,12): " + index.lca(11, 12));

        System.out.println(
                "distance(7,10): "
                        + index.distanceEdges(7, 10));
        System.out.println(
                "distance(8,12): "
                        + index.distanceEdges(8, 12));

        ForestIndex empty = new ForestIndex(new int[0]);
        System.out.println(
                "Empty forest size: " + empty.size());

        boolean cycleRejected = false;
        try {
            new ForestIndex(new int[] {1, 2, 0});
        } catch (IllegalArgumentException ex) {
            cycleRejected = true;
        }
        System.out.println(
                "Cycle rejected: " + cycleRejected);

        boolean selfParentRejected = false;
        try {
            new ForestIndex(new int[] {0});
        } catch (IllegalArgumentException ex) {
            selfParentRejected = true;
        }
        System.out.println(
                "Self-parent rejected: " + selfParentRejected);
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac BinaryLiftingAncestorsDemo.java
java BinaryLiftingAncestorsDemo
```

**Đầu ra chuẩn:**

```text
Parents: [-1, 0, 0, 1, 1, 2, 2, 3, 3, 5, 6, -1, 11]
Depths: [0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 0, 1]
Component roots: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 11, 11]
Table levels: 4
up[0][8]: 3
up[1][8]: 1
up[2][8]: -1
ancestor(8,0): 8
ancestor(8,1): 3
ancestor(8,2): 1
ancestor(8,3): 0
ancestor(8,4): -1
ancestor(9,2): 2
ancestor(12,1): 11
ancestor(12,2): -1
ancestor(8,1000000000000): -1
lca(7,8): 3
lca(7,4): 1
lca(9,10): 2
lca(7,10): 0
lca(8,12): -1
lca(5,9): 5
lca(11,12): 11
distance(7,10): 6
distance(8,12): -1
Empty forest size: 0
Cycle rejected: true
Self-parent rejected: true
```

### 8.1. Giải thích kết quả

- `componentRoot[0..10]=0` vì các đỉnh ấy thuộc cùng cây gốc 0; `componentRoot[11]=componentRoot[12]=11` thuộc cây khác.
- `up[0][8]=3` là cha trực tiếp; `up[1][8]=1` cách hai cạnh; `up[2][8]=-1` vì không có tổ tiên cách bốn cạnh.
- Đỉnh 8 sâu 3, nên tổ tiên bậc 4 và bậc `10^{12}` đều không tồn tại.
- `lca(7,8)=3` vì 7 và 8 cùng có cha 3.
- `lca(9,10)=2` vì đường đi từ 9 và 10 lên gốc gặp nhau ở 2.
- `lca(7,10)=0` vì hai nhánh lớn chỉ có gốc 0 chung.
- `lca(8,12)=-1` vì 8 và 12 thuộc hai cây khác nhau.
- `distanceEdges(7,10)=6` vì đường 7→3→1→0→2→6→10 có 6 cạnh.
- Input `[1,2,0]` tạo chu trình cha nên bị từ chối. Input `[0]` có đỉnh tự làm cha nên cũng bị từ chối.

### 8.2. Vì sao không dùng đệ quy khi xây bảng?

Constructor dựng danh sách `children`, đưa mọi gốc vào `ArrayDeque` và BFS tới tất cả đỉnh. Chiều sâu một cây dạng dây có thể rất lớn nhưng **không tạo chuỗi lời gọi đệ quy dài**.

Với mỗi đỉnh, `parent[v]` đã được kiểm tra phạm vi. Nếu sau BFS từ mọi gốc còn đỉnh chưa thăm, quan hệ cha không phải rừng hợp lệ; constructor từ chối trước khi dùng bảng.

### 8.3. Vì sao mảng được clone?

Constructor sao chép `parentInput`, tránh tình huống người gọi thay mảng cha sau khi bảng up đã được tính. Các getter `parents()`, `depths()`, `componentRoots()` cũng trả bản sao, không đưa tham chiếu mảng nội bộ để bên ngoài sửa.

Bảng `up` chỉ được xây một lần, rồi dùng cho nhiều truy vấn. Nếu dữ liệu cây thay đổi, phải **xây lại** hoặc dùng cấu trúc dữ liệu động phù hợp; không được sửa `parent[]` sau tiền xử lý rồi kỳ vọng bảng cũ vẫn đúng.

### 8.4. Tại sao dùng long cho k?

Một truy vấn có thể có k rất lớn, vượt `Integer.MAX_VALUE`. Code nhận `long` để biểu diễn những giá trị đó; nhờ so sánh `k>depth[v]`, truy vấn vượt độ sâu trả `-1` ngay mà không cần một bảng hàng chục mức.

`k<0` không có nghĩa là “đi xuống” và bị từ chối vì đặc tả của `kthAncestor` chỉ chấp nhận số bước **không âm**.

### 8.5. Vì sao BFS đếm reached phát hiện chu trình cha?

Mỗi đỉnh có **tối đa một cha**. Nếu mọi chuỗi cha kết thúc ở một đỉnh `parent=-1`, thì từ các gốc BFS qua danh sách con sẽ thăm được mọi đỉnh đúng một lần.

Nếu có một chu trình cha, các đỉnh trong chu trình không thể có đường cha kết thúc ở root. Vì thế chúng không nằm trong bất kỳ cây con mọc ra từ root nào, làm `reached<n`. Cách kiểm tra này đúng cho mô hình mảng cha khi đã loại parent ngoài phạm vi và self-parent.

### 8.6. LCA và distance chỉ là phần mở rộng

Trọng tâm của bài là **tổ tiên nhảy bậc**. Hai hàm `lca` và `distanceEdges` được thêm để minh họa rằng cùng bảng nhảy có thể trả lời những truy vấn cây khác mà **không cần tiền xử lý một lần nữa**. Phần LCA được giải thích kỹ ở mục tiếp theo.

---

## 9. Tổ tiên chung gần nhất (LCA) bằng binary lifting

**LCA(a,b)** là đỉnh **sâu nhất** đồng thời là tổ tiên của a và b trong cùng một cây có gốc. Nếu hai đỉnh ở hai cây khác nhau, LCA không tồn tại.

Ví dụ:

```text
lca(7,8) = 3
lca(7,4) = 1
lca(9,10) = 2
lca(7,10) = 0
lca(8,12) = -1
```

Nếu một đỉnh là tổ tiên của đỉnh kia thì LCA chính là **đỉnh tổ tiên ấy**, ví dụ `lca(5,9)=5`.

### 9.1. Bước 1: kiểm tra cùng cây

Trong rừng, nếu:

```text
componentRoot[a] != componentRoot[b]
```

thì trả `-1`. Không được cố đưa hai đỉnh lên bằng độ sâu rồi coi hai giá trị `-1` là một tổ tiên chung có thật.

### 9.2. Bước 2: cân bằng độ sâu

Giả sử `depth[a]≥depth[b]`; nếu không thì đổi a và b.

Nhảy a lên:

\[
depth[a]-depth[b]
\]

cạnh bằng chính `kthAncestor`. Sau bước này hai đỉnh có **độ sâu bằng nhau**.

Nếu chúng trở thành cùng một đỉnh, đỉnh đó chính là LCA; có thể trả ngay.

### 9.3. Bước 3: nhảy song song từ bit lớn xuống nhỏ

Khi hai đỉnh có cùng độ sâu nhưng khác nhau:

```text
for j = LOG-1 xuống 0:
    if up[j][a] != up[j][b]:
        a = up[j][a]
        b = up[j][b]

return up[0][a]
```

Trực giác: với mỗi mức lớn nhất có thể, thử nhảy **cả hai đỉnh** lên `2^j` bước. Chỉ thực hiện khi hai tổ tiên sau nhảy **vẫn khác nhau**, nghĩa là chưa nhảy tới hoặc qua LCA chung. Khi không thể tiếp tục nhảy mà vẫn tách biệt, chúng là hai đỉnh nằm ngay dưới LCA; cha chung là đáp án.

### 9.4. Vì sao không nhảy qua LCA?

Sau khi cân bằng độ sâu, hai đỉnh nằm trong **cùng một cây**, cùng độ sâu. Nếu một bước nhảy của cả hai lên độ sâu bằng nhau làm hai đỉnh trùng nhau, ta đã tới **một tổ tiên chung**; không nên đi xa hơn khi muốn tìm tổ tiên chung **gần nhất**.

Khi `up[j][a]!=up[j][b]`, bước nhảy này vẫn để hai đỉnh phân biệt; vì chúng cùng độ sâu và cùng cây, bước đó không thể vượt qua tổ tiên chung gần nhất. Thuật toán hạ dần j để tìm cặp đỉnh cao nhất còn nằm hai phía ngay dưới LCA.

### 9.5. Độ phức tạp LCA

- Kiểm tra gốc thành phần: `O(1)`.
- Nâng độ sâu: `O(log n)`.
- Vòng j giảm dần: `O(log n)`.

Tổng mỗi truy vấn LCA là:

\[
\boxed{O(\log n)}
\]

sau khi đã tiền xử lý bảng up O(n log n).

### 9.6. LCA khi cùng một đỉnh

Theo quy ước **một đỉnh cũng là tổ tiên của chính nó**, nên:

```text
lca(v,v) = v
```

Nếu cần câu hỏi “tổ tiên chung **nghiêm ngặt**” (không tính chính đỉnh), đề đã thay đổi định nghĩa; kết quả có thể là cha của v hoặc một cấu trúc khác.

---

## 10. Khoảng cách theo số cạnh từ LCA

Trên một cây không xét trọng số cạnh, giữa hai đỉnh u và v có một đường đi đơn duy nhất. Đường đó đi từ u lên LCA rồi đi xuống v.

Nếu `c=lca(u,v)` thì:

\[
\operatorname{distanceEdges}(u,v)
=depth[u]+depth[v]-2\cdot depth[c].
\]

Ví dụ `u=7`, `v=10`:

```text
7 -> 3 -> 1 -> 0 -> 2 -> 6 -> 10
```

Đường có 6 cạnh, và `depth[7]=3`, `depth[10]=3`, `depth[0]=0`:

\[
3+3-2\cdot0=6.
\]

Nếu hai đỉnh ở hai cây khác nhau, không có đường nối trong rừng; ví dụ Java trả `-1`.

### 10.1. Khoảng cách trọng số khác khoảng cách số cạnh

Nếu mỗi cạnh trong cây có trọng số khác nhau, biểu thức độ sâu trên **chỉ đếm số cạnh**, không cho tổng trọng số.

Muốn khoảng cách có trọng số, có thể tính `sumFromRoot[v]` — tổng trọng số theo đường từ gốc tới v — rồi:

\[
dist_w(u,v)
=sumFromRoot[u]+sumFromRoot[v]-2sumFromRoot[lca(u,v)].
\]

Cần chú ý tràn số khi cộng tổng trọng số, và chỉ áp dụng trong **cùng cây** có đường đi đơn. Đây là một mở rộng của mô hình cây có gốc; `depth[]` thông thường vẫn là số cạnh để binary lifting cân bằng mức.

---

## 11. Chứng minh tính đúng của truy vấn k-th ancestor

### 11.1. Bất biến bảng nhảy

Sau bước tiền xử lý, với mọi j và v:

\[
up[j][v]=ancestor(v,2^j)
\]

khi tổ tiên tồn tại, ngược lại bằng `-1`. Đã chứng minh bằng quy nạp ở mục 3.

### 11.2. Bất biến trong vòng xét bit

Gọi k ban đầu là K. Sau khi đã xử lý các bit thấp từ 0 tới j−1, biến v hiện tại là tổ tiên của đỉnh gốc truy vấn cách:

\[
\sum_{i=0}^{j-1}b_i2^i
\]

cạnh.

- Ban đầu chưa xử lý bit, tổng bằng 0 và v là chính đỉnh đầu vào.
- Nếu bit j=0, không nhảy; tổng số cạnh đã đi không đổi.
- Nếu bit j=1, truy cập `up[j][v]` sẽ đi thêm đúng `2^j` cạnh theo bất biến bảng.
- Khi mọi bit của k đã xét, tổng số cạnh đã nhảy chính là K.

Vì đã kiểm tra `K≤depth[v_{\mathrm{original}}]`, tổ tiên cần tìm chắc chắn nằm trên đường từ đỉnh đó tới gốc, nên từng bước nhảy trong truy vấn đều tồn tại và không truy cập `-1`.

Kết quả trả về vì thế là **tổ tiên bậc K**.

### 11.3. Khi k vượt độ sâu

Nếu `K>depth[v]`, đường từ v tới gốc chỉ có `depth[v]` cạnh. Không có tổ tiên xa hơn gốc trong cây, nên trả `-1` là chính xác.

Điều kiện này cũng loại k cực lớn từ đầu, tránh cần bảng nhảy theo bit 60 khi graph chỉ có n đỉnh.

### 11.4. Tính dừng

Vòng xét bit thực hiện `k >>>= 1` trên số nguyên `long` không âm. Sau hữu hạn bước, k trở về 0. Nếu k≤n−1, số bước không quá `O(log n)`.

### 11.5. Tính đúng với rừng

Bảng up chỉ dùng **cạnh cha của chính mỗi cây**; không có cạnh cha nào nối hai gốc khác nhau. Bởi vậy một truy vấn tổ tiên của v không thể rời khỏi cây có gốc `componentRoot[v]`. LCA cũng chỉ trả giá trị khi hai đỉnh có cùng gốc thành phần.

---

## 12. Phân tích độ phức tạp chi tiết

Đặt n là số đỉnh, q là số truy vấn.

### 12.1. Tiền xử lý

- Sao chép parent: `O(n)`.
- Kiểm tra id cha, xây children: `O(n)`.
- BFS qua tất cả cây: `O(n)` (mỗi đỉnh có tối đa một cha nên tổng cạnh con đúng `n-c` với c gốc).
- Tính LOG: `O(log n)`.
- Bảng up có n cột và LOG hàng, mỗi ô tính O(1): `O(n log n)`.

Vậy:

\[
\boxed{T_{\text{preprocess}}=O(n\log n)}
\]

với n≥2. Có thể viết cận chính xác cho mọi n là `O(n(1+\log n))` nếu quy ước log n ở n=1.

### 12.2. Một truy vấn tổ tiên bậc k

- Kiểm tra đỉnh, k âm, k>depth: `O(1)`.
- Nếu k=0, trả ngay: `O(1)`.
- Nếu k hợp lệ, số lần lặp bằng số bit cần đọc: `O(1+\log k)`; mỗi bit chỉ đọc nhiều nhất một ô bảng.
- Vì k≤depth[v]<n, cận trên là `O(log n)`.

Do đó:

\[
\boxed{T_{\text{query}}=O(\log n)}
\]

trong trường hợp xấu nhất, thậm chí `O(1)` cho k=0 hoặc k vượt độ sâu nếu code kiểm tra sớm.

### 12.3. Nhiều truy vấn

Nếu có q câu hỏi độc lập trên một rừng không thay đổi:

\[
\boxed{O(n\log n+q\log n)}
\]

thời gian tổng, ngoài chi phí đọc input/in output.

So với phương pháp đi cha từng bước có thể tốn `O(qn)` trong trường hợp xấu nhất, binary lifting thường thắng khi q lớn và nhiều k dài.

### 12.4. Bộ nhớ

- Bảng up: `n\times LOG=O(n\log n)` số nguyên.
- Parent, depth, componentRoot: `O(n)`.
- Danh sách con: `O(n)` phần tử cạnh và các list.
- Queue BFS tối đa `O(n)`.
- Mỗi truy vấn chỉ dùng O(1) biến phụ ngoài bảng.

Tổng:

\[
\boxed{O(n\log n)}
\]

bộ nhớ thêm cho chỉ mục binary lifting; nếu input là parent[] thì cả cấu trúc cũng dùng cùng bậc.

### 12.5. Ước lượng RAM thực tế

Một bảng `int[LOG][n]` trong Java dùng khoảng `4n\cdot LOG` byte **chỉ cho dữ liệu phần tử int**, chưa kể header của từng mảng, các mảng phụ, danh sách con, queue và runtime.

Ví dụ n=100.000, LOG≈17:

\[
100000\times17\times4=6{,}800{,}000\text{ byte}
\]

khoảng **6,5 MiB** cho phần tử bảng up. RAM thực tế cao hơn do các đối tượng phụ, đặc biệt `ArrayList` cho mỗi đỉnh trong bản dễ đọc này.

Nếu n vài triệu, nên tính bộ nhớ trước; có thể dùng cấu trúc mảng phẳng, CSR hoặc cách tiền xử lý gọn hơn để tiết kiệm overhead.

---

## 13. Những lỗi phổ biến khi xây bảng

### 13.1. Nhầm chỉ số j với số bước

`up[3][v]` không có nghĩa là tổ tiên bậc **3**. Nó là tổ tiên cách:

\[
2^3=8
\]

cạnh.

Tổ tiên bậc 3 phải nhảy theo `3=2+1`, tức kết hợp hai mức j=1 và j=0.

### 13.2. Sai thứ tự tính j

Không thể tính `up[j][v]` trước khi các giá trị `up[j-1][*]` đã có. Phải duyệt **j tăng dần** từ 1 tới LOG−1.

Duyệt v theo thứ tự bất kỳ **ở cùng j** vẫn được vì mỗi ô cấp j chỉ phụ thuộc cấp j−1 đã hoàn tất.

### 13.3. Không kiểm tra sentinel -1

Công thức:

```java
up[j][v] = up[j - 1][up[j - 1][v]];
```

sẽ gây truy cập mảng tại -1 nếu v không có tổ tiên đủ xa. Cần tách:

```java
int mid = up[j - 1][v];
up[j][v] = (mid == -1) ? -1 : up[j - 1][mid];
```

### 13.4. Không xây đủ mức

Nếu bảng thiếu bit cao nhất của một k hợp lệ, code có thể trả sai hoặc đọc vượt mảng. Hãy chọn LOG từ n hoặc độ sâu lớn nhất sau khi đã tiền xử lý.

### 13.5. K lớn hơn độ sâu

Với v sâu 3, k=10^12 không có tổ tiên. Nếu chỉ duyệt các bit có trong bảng ngắn mà bỏ qua bit cao, code có thể trả một đỉnh sai. Kiểm tra `k>depth[v]` ngay đầu truy vấn là cách gọn và chắc chắn cho **rừng có gốc**.

### 13.6. Dịch bit int bị tràn

Dùng `1<<j` cho j lớn có thể tạo số âm hoặc sai phạm vi. Dùng `1L<<j` khi tính độ dài nhảy và đừng mở rộng j vượt miền bit của kiểu long.

### 13.7. Sai quy ước k=0

Theo bài này, `ancestor(v,0)=v`. Nếu chương trình trả parent[v] cho k=0, mọi truy vấn sẽ lệch một bậc.

### 13.8. Nhầm n và n−1

Một cây n đỉnh có độ sâu tối đa n−1, không phải n; độ sâu của gốc là 0. Với cây đường dài 5 đỉnh, đỉnh cuối sâu 4. Độ dài nhảy hợp lệ tới gốc của nó là 4; 5 bước cho -1.

### 13.9. Không phát hiện chu trình parent

Mảng `parent=[1,2,0]` không phải cây/rừng. Nếu cố nâng “tổ tiên” trên đó, kết quả quay vòng và không có gốc rõ ràng; `depth` không xác định như cây. Hãy kiểm tra đầu vào.

### 13.10. Nhầm cây gốc của các đỉnh

Hai đỉnh thuộc **hai cây khác nhau** không có LCA. Nếu code cứ đưa cả hai tới `-1` rồi coi -1 như một gốc chung, kết quả bị sai về ngữ nghĩa.

---

## 14. Mở rộng: các phép truy vấn trên đường đi

Bảng up không chỉ lưu **đỉnh tổ tiên**. Khi các cạnh đi lên chứa thêm thông tin, ta có thể tiền xử lý các phép **gộp (aggregate)** tương ứng.

### 14.1. Tổng trọng số khi đi lên

Giả sử cạnh nối v với parent[v] có trọng số `wToParent[v]`.

Định nghĩa `sumUp[j][v]` là **tổng trọng số** của `2^j` cạnh đi lên từ v, nếu đoạn đường đó tồn tại.

Cơ sở:

```text
sumUp[0][v] = wToParent[v] nếu v không phải gốc
```

Bước quy nạp (nếu mid tồn tại):

\[
sumUp[j][v]
=sumUp[j-1][v]+sumUp[j-1][mid],
\]

với `mid=up[j-1][v]`.

Khi hỏi tổng trên k cạnh từ v đi lên, ta cộng `sumUp[j][current]` cho từng bit 1 của k, song song với việc cập nhật current bằng `up[j][current]`.

### 14.2. Min/max trên đường đi

Tương tự:

\[
maxUp[j][v]
=\max(maxUp[j-1][v],maxUp[j-1][mid]).
\]

Hoặc thay max bằng min. Nếu cần tìm **cạnh lớn nhất** trên đường từ u tới v, trước tiên tìm LCA, rồi tính max của hai đoạn từ u và v lên LCA.

Phải có quy ước rõ với đường dài 0 cạnh: giá trị trung hòa cho phép max thường là một giá trị rất nhỏ (chẳng hạn `Long.MIN_VALUE`), nhưng có thể cần API phân biệt “không có cạnh”.

### 14.3. Điều kiện để aggregate ghép được

Phép gộp cần có tính **kết hợp** (*associative*) để chia đoạn theo lũy thừa của 2 mà không đổi kết quả:

\[
(a\star b)\star c=a\star(b\star c).
\]

Sum, min, max là các ví dụ thường dùng. Nếu phép gộp **không giao hoán**, thứ tự ghép các đoạn đường có thể rất quan trọng: cần lưu hướng và ghép theo thứ tự đường đi phù hợp, không tùy tiện đổi vị trí hai đoạn.

### 14.4. Kiểm tra quan hệ tổ tiên

Với hai đỉnh u,v trong cùng cây, u là tổ tiên của v **kể cả u=v** nếu:

\[
depth[u]\le depth[v]
\]

và:

\[
ancestor(v,depth[v]-depth[u])=u.
\]

Bằng bảng nhảy, kiểm tra trong `O(log n)`. Nếu đã có `tin/tout` từ DFS chuẩn, cũng có thể kiểm tra quan hệ tổ tiên trong `O(1)` sau tiền xử lý O(n), nhưng hai mô hình lưu thông tin khác nhau.

### 14.5. Tìm đỉnh nằm trên đường giữa u và v

Biết `c=lca(u,v)`, khoảng cách theo cạnh giữa u và v là:

\[
d=depth[u]+depth[v]-2depth[c].
\]

Muốn tìm đỉnh cách u đúng k cạnh trên đường u→v:

- Nếu k vượt d hoặc k âm, không tồn tại.
- Nếu k≤`depth[u]-depth[c]`, đó là `ancestor(u,k)`.
- Ngược lại, đi từ v lên `d-k` cạnh: `ancestor(v,d-k)`.

Cả hai trường hợp dùng binary lifting trong O(log n), sau một lần LCA O(log n). Đây là ứng dụng trực tiếp của tổ tiên bậc k, không cần lưu đường đi đầy đủ.

---

## 15. Binary lifting khác những kỹ thuật cây khác như thế nào?

### 15.1. BFS/DFS thuần túy

BFS hoặc DFS giúp dựng parent và depth trong O(n). Nếu sau đó chỉ đi từng cha để tìm tổ tiên bậc k, truy vấn vẫn O(k). Binary lifting **dùng thêm O(n log n) tiền xử lý/bộ nhớ** để đổi sang O(log n) mỗi truy vấn.

### 15.2. Euler Tour + RMQ cho LCA

Một cách tìm LCA khác là tạo Euler tour của cây và dùng cấu trúc **range minimum query** trên độ sâu. Tùy thiết kế RMQ, LCA có thể đạt truy vấn O(1) hoặc O(log n) sau tiền xử lý.

Nhưng nếu câu hỏi chính là **tổ tiên bậc k**, bảng doubling xử lý trực tiếp và thường đơn giản hơn. Euler tour thông thường không tự trả ancestor(v,k) nhanh nếu chưa có cấu trúc bổ sung.

### 15.3. Heavy-Light Decomposition (HLD)

HLD chia cây thành các đường nặng/nhẹ để trả lời truy vấn đường đi, thường kết hợp segment tree. Nó mạnh khi cần **cập nhật trọng số cạnh/đỉnh** và truy vấn tổng/min/max trên đường, nhưng phức tạp hơn binary lifting cơ bản.

Khi bài chỉ hỏi **tổ tiên bậc k** hoặc **LCA trên cây tĩnh**, binary lifting là lựa chọn dễ triển khai và chứng minh.

### 15.4. Cây động

Nếu thay đổi parent hoặc cắt/nối cạnh giữa các truy vấn, bảng up cũ có thể trở nên **sai**. Cần tính lại những phần bị ảnh hưởng hoặc dùng cấu trúc dữ liệu cho cây động như link-cut tree tùy bài toán.

Trường hợp đặc biệt **chỉ thêm lá mới** vào rừng hiện có có thể cập nhật các mức up cho lá mới từ cha của nó trong O(log n), nếu có đủ bảng mức và ràng buộc gốc không đổi. Nhưng thay cha của một đỉnh nội bộ có thể ảnh hưởng **toàn bộ các hậu duệ**, không thể coi như cập nhật một ô parent đơn giản.

### 15.5. Functional graph

Một **functional graph** có mỗi đỉnh trỏ tới đúng một đỉnh kế tiếp, nhưng có thể có chu trình. Doubling `next[j][v]` vẫn hữu ích để đi đúng k lần theo hàm kế tiếp với k tới 10^18. Tuy nhiên:

- Không có khái niệm “độ sâu tới gốc -1” chung cho mọi đỉnh.
- Đi k lớn không nhất thiết trả -1 vì có thể quay vòng.
- Bảng cần đủ mức theo **số bit của k tối đa**, không chỉ theo n.

Đây là điểm phân biệt quan trọng: **binary lifting là kỹ thuật nhảy nhị phân tổng quát**, còn bài tổ tiên bậc k trên cây được đơn giản hóa bởi **rừng có gốc và độ sâu hữu hạn**.

---

## 16. Kiểm thử đầy đủ

### 16.1. Các bộ test gợi ý

| Đầu vào | Mong đợi |
| --- | --- |
| Một đỉnh gốc `[-1]` | `ancestor(0,0)=0`, `ancestor(0,1)=-1` |
| Chuỗi 5 đỉnh `[-1,0,1,2,3]` | `ancestor(4,4)=0`, k=5 trả -1 |
| Cây sao `[-1,0,0,0]` | Mọi lá có cha 0, tổ tiên bậc 2 không tồn tại |
| Rừng hai gốc | Query không nhảy giữa các cây; LCA khác cây trả -1 |
| Đồ thị 13 đỉnh ở mục 4 | `ancestor(8,3)=0`, `lca(9,10)=2` |
| k=0 | Trả chính v |
| k rất lớn kiểu long | Trả -1 nếu vượt depth |
| k âm | Báo lỗi đầu vào |
| id v âm hoặc v≥n | Báo lỗi đầu vào |
| Parent bằng -2 | Báo lỗi đầu vào |
| Parent v trỏ tới v | Báo lỗi |
| Chu trình `[1,2,0]` | Báo lỗi |
| Cây đường rất sâu | Tiền xử lý lặp không tràn call stack |
| Rừng rỗng n=0 | Có thể tạo index rỗng, truy vấn đỉnh phải báo lỗi |

### 16.2. Thuộc tính cần đúng với mọi rừng hợp lệ

1. `ancestor(v,0)=v`.
2. `ancestor(v,1)=parent[v]`.
3. `ancestor(v,depth[v])=componentRoot[v]`.
4. `ancestor(v,depth[v]+1)=-1`.
5. Nếu `a=ancestor(v,k)` tồn tại thì `depth[a]=depth[v]-k`.
6. Với a,b không âm và tổng không vượt depth[v]:

\[
ancestor(v,a+b)
=ancestor(ancestor(v,a),b).
\]

7. Với mọi j, nếu `up[j][v]` tồn tại thì depth của nó bằng `depth[v]-2^j`.
8. Nếu `componentRoot[u]\ne componentRoot[v]` thì `lca(u,v)=-1`.
9. Nếu `c=lca(u,v)` tồn tại, c là tổ tiên của cả u,v.
10. Không có tổ tiên chung nào của u,v sâu hơn c.
11. `distanceEdges(v,v)=0`.
12. Khoảng cách trên cây theo số cạnh đối xứng:

\[
distanceEdges(u,v)=distanceEdges(v,u)
\]

khi u,v cùng cây.

### 16.3. Oracle chậm nhưng đơn giản

Với n nhỏ, có thể dựng một hàm tham chiếu **đi từng cha**:

```text
slowAncestor(v,k):
    repeat k lần:
        if v == -1: return -1
        v = parent[v]
    return v
```

Sinh nhiều truy vấn ngẫu nhiên v,k, so `slowAncestor` với `kthAncestor`. Lấy k từ 0 tới depth[v]+3, thêm vài giá trị long rất lớn.

Đây là một oracle độc lập về **cách tính**, nên có thể phát hiện lỗi công thức doubling, xử lý bit hoặc giới hạn LOG.

### 16.4. Oracle LCA chậm

Với hai đỉnh cùng cây:

1. Ghi tất cả tổ tiên của u (kể cả u) vào một tập.
2. Đi từ v lên cha, gặp đỉnh đầu tiên nằm trong tập thì đó là LCA.
3. Nếu hai cây khác nhau, trả -1.

So với hàm LCA dùng bảng up cho tất cả cặp đỉnh trên những rừng nhỏ. Có thể thử mọi cặp n≤20, vừa dễ kiểm chứng vừa không tốn nhiều tài nguyên.

### 16.5. Kiểm tra công thức khoảng cách

Nếu cùng cây, lấy chuỗi đường từ u lên c và v lên c, đếm số cạnh. Kết quả phải bằng:

`depth[u]+depth[v]-2*depth[c]`.

Với đường đi dài, dùng `long` ở phép cộng/trừ nếu muốn tránh tràn `int` ở trường hợp biên rất lớn.

---

## 17. Những sai lầm thường gặp

1. **Đếm tổ tiên bậc 0 là cha trực tiếp**, gây lệch một bậc toàn bộ truy vấn.
2. **Nhầm up[j][v] là tổ tiên bậc j** thay vì bậc `2^j`.
3. **Không dùng sentinel -1**, làm gốc tự trỏ về chính nó và các truy vấn vượt gốc trả sai.
4. **Đọc up[j-1][-1]** khi tổ tiên trung gian không tồn tại.
5. **Tính bảng theo j giảm** hoặc cập nhật cùng mức sai phụ thuộc.
6. **Chỉ cấp LOG=log2(n) làm tròn xuống mà quên bit cao nhất** của k hợp lệ.
7. **Dùng `1<<j` kiểu int** rồi bị tràn khi j lớn.
8. **Không kiểm tra k>depth[v]**, sau đó truy cập bit vượt bảng hoặc trả một tổ tiên giả.
9. **Dùng k kiểu int** khi input có thể tới 10^12 hoặc 10^18.
10. **Nhầm depth tính số đỉnh với số cạnh** trên đường từ gốc tới v.
11. **Giả định parent[v] luôn hợp lệ**, không kiểm tra id âm/ngoài phạm vi.
12. **Chấp nhận parent[v]=v** hay một chu trình cha, dù không phải rừng có gốc.
13. **Không xử lý rừng có nhiều gốc**, suy ra LCA giả giữa hai cây.
14. **Dùng parent[] từ graph vô hướng nhưng chưa chọn root**, khiến ý nghĩa cha không xác định.
15. **Dùng DFS đệ quy để tiền xử lý cây dạng đường quá dài**, gây StackOverflowError.
16. **Nhầm index 0-based với 1-based**, quên chuyển từ id đề bài sang id mảng.
17. **Coi một đồ thị có nhiều cha là cây**, áp dụng ancestor mà không có quy tắc chọn cha hợp lệ.
18. **LCA không cân bằng độ sâu trước**, có thể nhảy sai.
19. **LCA nhảy cả hai đỉnh dù up[j] đã trùng nhau**, bỏ qua tổ tiên chung gần nhất.
20. **Không kiểm tra hai đỉnh ở cùng cây khi hỏi LCA**, rồi trả -1 như một đỉnh hợp lệ.
21. **Gọi công thức depth là khoảng cách trọng số**, dù depth chỉ đếm cạnh.
22. **Sửa parent sau khi build bảng mà không rebuild**, khiến up và depth không nhất quán.
23. **Lãng phí O(n log n) RAM khi chỉ có một truy vấn k=1**, trong khi đọc parent trực tiếp đủ.
24. **Cho rằng functional graph có chu trình cũng có độ sâu hữu hạn tới -1**, dẫn tới cắt mất truy vấn k lớn hợp lệ.
25. **Không bảo vệ mảng nội bộ trong API**, khiến bên ngoài sửa depth/up làm dữ liệu không nhất quán.
26. **Chỉ kiểm tra vài ví dụ cân đối**, bỏ qua cây đường, cây sao, rừng rỗng và truy vấn vượt root.
27. **Nhầm n và số cạnh** để chọn LOG; nếu input là rừng có c cây, số cạnh là n−c nhưng độ sâu có thể tới n−1 trong một cây.
28. **Dùng vòng đi cha O(k) bên trong mỗi truy vấn LCA**, làm mất ý nghĩa tiền xử lý.
29. **Không giữ thứ tự đoạn khi dùng aggregate không giao hoán**, khiến tổng hợp trên đường sai.
30. **Không xử lý biên n=0**, cố tra up[0][0] dù bảng không có cột.

---

## 18. Bài tập tự kiểm tra

### Bài 1 — Khái niệm

Thế nào là tổ tiên bậc 0, 1, 2 của v? Nếu v là gốc, tổ tiên bậc 1 của nó là gì?

### Bài 2 — Đường lên gốc

Cây có `parent[8]=3`, `parent[3]=1`, `parent[1]=0` và `parent[0]=-1`. Tính `ancestor(8,k)` cho k từ 0 tới 5.

### Bài 3 — Công thức bảng

Viết công thức `up[j][v]` theo hai ô cấp j−1. Vì sao phải kiểm tra sentinel trước khi truy cập mảng lần thứ hai?

### Bài 4 — Bảng mức

Với cây 13 đỉnh của mục 4, tìm `up[0][9]`, `up[1][9]`, `up[2][9]`.

### Bài 5 — Phân tích bit

Viết 13 dưới dạng tổng lũy thừa của 2. Nếu một đỉnh đủ sâu, truy vấn tổ tiên bậc 13 cần những mức nào của bảng?

### Bài 6 — K lớn

Cây có n=100.000 và `depth[v]=37`. Truy vấn `ancestor(v,10^{12})` trả gì? Có cần xây bảng tới bit 40 không?

### Bài 7 — Trường hợp k=0

Nếu k=0 và v hợp lệ, hàm phải trả gì? Tại sao đây là một cách kiểm tra lỗi lệch chỉ số?

### Bài 8 — Cây đường

Mảng parent `[-1,0,1,2,3]` tạo cây như thế nào? Tổ tiên bậc 3 và bậc 5 của đỉnh 4 là gì?

### Bài 9 — Cây sao

Với parent `[-1,0,0,0,0]`, depth của các lá là bao nhiêu? Có đỉnh nào có tổ tiên bậc 2 không?

### Bài 10 — LCA cùng nhánh

Trên cây mục 4, tính `lca(7,8)`, `lca(7,4)` và `lca(5,9)`.

### Bài 11 — LCA khác nhánh

Tính `lca(9,10)` và `lca(7,10)` trên cây gốc 0.

### Bài 12 — LCA khác cây

Với rừng gốc 0 và 11, `lca(8,12)` là gì? Tại sao không được trả 0 hay 11?

### Bài 13 — Khoảng cách

Tính khoảng cách **theo số cạnh** giữa 7 và 10 bằng depth và LCA; liệt kê đường đi.

### Bài 14 — Tính đúng

Nêu bất biến của bảng `up[j][v]`. Chứng minh truy vấn bit của k đi lên tổng đúng k cạnh.

### Bài 15 — Độ phức tạp

Với n đỉnh, q truy vấn, tiền xử lý binary lifting và trả lời q truy vấn cần thời gian và bộ nhớ bao nhiêu? So với q truy vấn đi cha từng bước.

### Bài 16 — Parent lỗi

Mảng parent `[1,2,0]` có phải một rừng hợp lệ không? Một chương trình tiền xử lý nên làm gì?

### Bài 17 — Id không hợp lệ

Nếu n=5 nhưng `parent[3]=8` hoặc `parent[4]=-2`, cần xử lý ra sao? Vì sao không được đọc children[8]?

### Bài 18 — Đồ thị chưa chọn gốc

Bạn nhận danh sách cạnh vô hướng của một cây. Muốn áp dụng binary lifting, cần làm gì trước khi điền bảng up?

### Bài 19 — Nâng hai đỉnh để tìm LCA

Hai đỉnh a,b có depth khác nhau 5. Nêu bước cân bằng độ sâu. Sau khi cân bằng mà a=b thì kết luận gì?

### Bài 20 — Tính đúng của bước nhảy LCA

Tại sao khi `up[j][a]==up[j][b]`, không nên nhảy cả hai đỉnh lên mức j trong vòng tìm LCA từ cao xuống thấp?

### Bài 21 — Kiểm tra tổ tiên

Cho hai đỉnh u,v cùng cây. Viết một điều kiện dùng `depth` và `kthAncestor` để biết u là tổ tiên của v, cho phép u=v.

### Bài 22 — Điểm thứ k trên đường đi

Với u,v cùng cây và c=LCA(u,v), hãy viết cách tìm đỉnh nằm cách u đúng k cạnh trên đường u→v.

### Bài 23 — Cây động

Nếu một cạnh cha của đỉnh nội bộ bị thay đổi sau tiền xử lý, tại sao chỉ sửa `parent[v]` là chưa đủ? Khi nào cập nhật riêng một lá có thể dễ hơn?

### Bài 24 — Weighted aggregate

Muốn tính tổng trọng số trên đoạn k cạnh đi lên từ v, ngoài `up` cần bảng nào? Công thức doubling cho bảng tổng là gì?

### Bài 25 — Phân biệt functional graph

Trong một đồ thị hàm có chu trình, k có thể bằng `10^{18}`. Vì sao điều kiện “k>depth thì -1” không áp dụng, và bảng nhảy cần đủ những bit nào?

### Đáp án gợi ý

1. Bậc 0 là chính v; bậc 1 là cha; bậc 2 là cha của cha. Gốc không có cha nên bậc 1 là -1.
2. `[8,3,1,0,-1,-1]` cho k=0..5.
3. `mid=up[j-1][v]`; nếu mid=-1 thì `up[j][v]=-1`, ngược lại `up[j][v]=up[j-1][mid]`. Không được truy cập chỉ số -1.
4. `up[0][9]=5`, `up[1][9]=2`, `up[2][9]=-1`.
5. `13=8+4+1`, cần j=3,2,0; chỉ ba lần nhảy bảng.
6. Trả -1 ngay vì `10^{12}>37`; không cần bảng có bit 40 cho rừng có gốc.
7. Trả chính v. Nếu trả cha thì chương trình đã lệch một bậc.
8. Đường `0→1→2→3→4`. Tổ tiên bậc 3 của 4 là 1; bậc 5 là -1.
9. Mọi lá có depth=1, gốc depth=0. Không đỉnh nào có tổ tiên bậc 2.
10. `lca(7,8)=3`, `lca(7,4)=1`, `lca(5,9)=5`.
11. `lca(9,10)=2`, `lca(7,10)=0`.
12. Trả -1 vì hai đỉnh ở hai cây khác nhau và không có tổ tiên chung.
13. `depth[7]=3`, `depth[10]=3`, c=0, nên `3+3-0=6`. Đường `7→3→1→0→2→6→10`.
14. `up[j][v]` là tổ tiên cách `2^j` cạnh, hoặc -1. Truy vấn duyệt từng bit 1 của k, mỗi bit cộng đúng `2^j` bước; tổng bằng k.
15. Tiền xử lý `O(n log n)`, q truy vấn `O(q log n)`, bộ nhớ `O(n log n)`. Đi cha từng bước có thể `O(qn)`.
16. Không hợp lệ: 0→1→2→0 là chu trình. Phải từ chối input, không coi là cây có gốc.
17. Báo input không hợp lệ trước khi dựng children. Các id 8 và -2 không thuộc tập cha hợp lệ `{-1,0,...,4}`.
18. Chọn gốc, BFS/DFS để xây parent và depth (đồng thời kiểm tra rừng/cây nếu chưa chắc dữ liệu), rồi điền bảng up.
19. Dùng `kthAncestor` nâng đỉnh sâu hơn lên 5 cạnh. Nếu hai đỉnh trùng nhau sau đó thì chính đỉnh ấy là LCA.
20. Nếu nhảy khiến chúng trùng nhau, có thể đã đi tới hoặc vượt qua LCA; thuật toán cần giữ hai nhánh phân biệt đến ngay dưới LCA rồi trả cha chung.
21. `depth[u]≤depth[v]` và `kthAncestor(v,depth[v]-depth[u])==u`, sau khi biết cùng cây.
22. Đặt `d=depth[u]+depth[v]-2depth[c]`. Nếu k<0 hoặc k>d, không tồn tại. Nếu `k≤depth[u]-depth[c]`, trả `ancestor(u,k)`; ngược lại trả `ancestor(v,d-k)`.
23. Bảng up/depth của v và nhiều hậu duệ có thể đổi, nên phải rebuild hoặc dùng cấu trúc động. Nếu chỉ thêm lá với cha đã biết và gốc không đổi, có thể tính các mức up của lá trong O(log n).
24. Dùng `sumUp[j][v]` với `sumUp[0][v]=wToParent[v]` và `sumUp[j][v]=sumUp[j-1][v]+sumUp[j-1][mid]` khi mid hợp lệ.
25. Trong functional graph, đi theo ánh xạ kế tiếp có thể quay vòng thay vì kết thúc ở -1; cần đủ mức để biểu diễn k tối đa, chẳng hạn bit 0..59 cho số k dưới `2^{60}`.

---

## Ghi nhớ

**Binary lifting** biến chuỗi k lần đi lên cha thành những bước nhảy **1,2,4,8,...**. Tiền xử lý `up[0][v]=parent[v]` và:

\[
up[j][v]
=\begin{cases}
-1, & up[j-1][v]=-1,\\
up[j-1][up[j-1][v]], & \text{ngược lại}.
\end{cases}
\]

Tách k theo bit để nhảy, vì thế **một truy vấn tổ tiên bậc k tốn O(log n)** sau khi tiền xử lý **O(n log n)** và lưu bảng **O(n log n)**. Trong cây có gốc, `ancestor(v,0)=v`, còn `k>depth[v]` phải trả **không tồn tại**; `-1` luôn là sentinel, không được đọc như chỉ số mảng. Cùng bảng nhảy còn giúp tìm **LCA** và khoảng cách theo số cạnh. Luôn phân biệt **cây/rừng có gốc** với đồ thị tổng quát hoặc functional graph có chu trình, và xây lại bảng nếu quan hệ cha thay đổi.
