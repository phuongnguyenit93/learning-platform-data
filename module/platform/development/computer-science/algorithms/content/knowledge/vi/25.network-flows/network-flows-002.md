# Mạng dư, cạnh ngược và đường tăng luồng

## 1. Mục tiêu: hiểu cách luồng có thể được điều chỉnh, không chỉ tăng thêm

Trong bài toán **luồng cực đại (maximum flow)**, ta có một mạng có hướng. Mỗi cạnh có **dung lượng (capacity)**, và ta muốn gửi nhiều đơn vị luồng nhất có thể từ **nguồn `s`** tới **đích `t`**. Nếu chỉ nhìn các cạnh gốc còn dung lượng trống, một chiến lược chọn đường ban đầu có thể làm luồng “đi sai nhánh”, rồi tưởng rằng không tăng thêm được nữa.

Cấu trúc giúp sửa lựa chọn trước đó là **mạng dư (residual network)**. Mạng dư chứa:

- **Cạnh dư thuận (forward residual edge):** cho biết có thể tăng thêm bao nhiêu luồng trên một cạnh gốc.
- **Cạnh dư ngược (reverse residual edge):** cho biết có thể **giảm/hoàn tác** bao nhiêu luồng đã gửi qua cạnh gốc trước đó.
- **Đường tăng luồng (augmenting path):** một đường có hướng từ `s` tới `t` trong **mạng dư**, trên đó mọi cạnh có dung lượng dư **dương**.

Điểm quan trọng nhất: **đi qua cạnh ngược trong mạng dư không có nghĩa là mạng gốc đột nhiên có thêm một cạnh thật theo chiều ngược**. Nó chỉ biểu diễn thao tác **giảm luồng** trên một cạnh gốc đã dùng. Nhờ vậy, thuật toán có thể đổi cách phân phối luồng trong mạng mà vẫn giữ các điều kiện khả thi.

Bài học sẽ giải thích các bất biến dung lượng/bảo toàn luồng; đưa ví dụ mà cạnh ngược thực sự xuất hiện trong lần tăng luồng; mô tả Ford–Fulkerson và Edmonds–Karp; chứng minh **không còn đường tăng luồng ⇔ luồng đã cực đại**; rồi cài đặt **Java 17** có kiểm chứng min-cut bằng vét cạn.

## 2. Mô hình mạng và các điều kiện của một luồng hợp lệ

Cho đồ thị có hướng `G=(V,E)`, nguồn `s` và đích `t` với `s\ne t`. Mỗi **cạnh vật lý** `e=(u,v)` có dung lượng:

\[
c(e)\ge0.
\]

Nếu có hai cạnh song song cùng đi từ `u` tới `v`, chúng vẫn là **hai cạnh riêng biệt** với ID riêng. Nếu có cạnh gốc `u\to v` và cạnh gốc `v\to u`, chúng cũng là **hai cạnh thật độc lập**, không được nhầm với cạnh dư ngược.

Đặt `f(e)` là **luồng thực tế đang gửi trên cạnh gốc `e`**, thỏa:

### 2.1. Ràng buộc dung lượng

Với mọi cạnh:

\[
\boxed{0\le f(e)\le c(e).}
\]

Không được gửi luồng âm theo chiều cạnh gốc và không được vượt dung lượng. Trạng thái ban đầu thường là `f(e)=0` cho tất cả cạnh, nên luôn hợp lệ.

### 2.2. Bảo toàn luồng

Với mọi đỉnh trung gian `v\notin\{s,t\}`:

\[
\boxed{
\sum_{e:\,\operatorname{to}(e)=v}f(e)
=
\sum_{e:\,\operatorname{from}(e)=v}f(e).
}
\]

Nói cách khác: lượng đi vào bằng lượng đi ra. Đỉnh trung gian không tự sinh hoặc tiêu thụ luồng. Khuyên `v\to v` xuất hiện ở cả tổng vào lẫn tổng ra, nên hai đóng góp của nó triệt tiêu trong phương trình bảo toàn.

### 2.3. Giá trị của luồng

Giá trị luồng `|f|` là lượng ròng rời nguồn:

\[
\boxed{
|f|=
\sum_{e:\operatorname{from}(e)=s}f(e)
-
\sum_{e:\operatorname{to}(e)=s}f(e).
}
\]

Theo bảo toàn luồng, giá trị này cũng bằng:

\[
|f|=
\sum_{e:\operatorname{to}(e)=t}f(e)
-
\sum_{e:\operatorname{from}(e)=t}f(e).
\]

**Không tự động lấy tổng tất cả cạnh đi ra nguồn mà bỏ qua cạnh đi vào nguồn** trên một mạng bất kỳ. Luồng có thể có chu trình hoặc cạnh đi vào nguồn; giá trị đúng là **luồng ròng**.

Bài toán **max flow** tìm một luồng thỏa dung lượng và bảo toàn, có `|f|` lớn nhất.

### 2.4. Tổng luồng khác tổng lượng đã chạy qua các cạnh

Nếu `1` đơn vị luồng đi `s\to a\to b\to t`, bốn đỉnh có ba cạnh mỗi cạnh mang `1`. **Giá trị luồng là `1`**, không phải tổng luồng trên mọi cạnh bằng `3`.

Mỗi lần tăng luồng từ `s` tới `t` thêm `\Delta` vào **giá trị ròng**, dù đường tăng có nhiều cạnh và có thể chứa cạnh ngược.

## 3. Mạng dư: khả năng thay đổi luồng hiện tại

Mạng dư tại luồng `f`, ký hiệu `G_f`, mô tả **những điều chỉnh vẫn giữ được điều kiện dung lượng**.

Với mỗi **cạnh gốc riêng biệt** `e=(u,v)` có dung lượng `c_e` và luồng `f_e`, tạo **một cặp cung dư**:

1. Cung dư thuận `u\to v`, dung lượng:

\[
\boxed{r_{\mathrm{forward}}(e)=c_e-f_e.}
\]

2. Cung dư ngược `v\to u`, dung lượng:

\[
\boxed{r_{\mathrm{reverse}}(e)=f_e.}
\]

Chỉ những cung dư có `r>0` mới có thể được dùng trong đường tăng luồng.

Hai dung lượng dư của cùng một cạnh gốc có tổng bất biến:

\[
\boxed{r_{\mathrm{forward}}(e)+r_{\mathrm{reverse}}(e)=c_e.}
\]

### 3.1. Ví dụ một cạnh

Có cạnh gốc `A\to B` dung lượng `10`.

| Trạng thái | Luồng `f` | Dư thuận `10-f` | Dư ngược `f` |
|---|---:|---:|---:|
| Chưa gửi gì | 0 | 10 | 0 |
| Đã gửi 4 | 4 | 6 | 4 |
| Đã gửi 10 | 10 | 0 | 10 |
| Hoàn tác 3 từ trạng thái gửi 10 | 7 | 3 | 7 |

Nếu đã gửi `4` mà một đường tăng dùng cung dư `B\to A` với `\Delta=3`, luồng trên cạnh gốc `A\to B` giảm từ `4` về `1`.

**Không có hàng hóa nào “chạy ngược lại” trên cạnh vật lý nếu mạng gốc không có cạnh `B\to A`.** Đây là thao tác điều chỉnh cách hạch toán phân phối luồng.

### 3.2. Vì sao có cạnh ngược kể cả khi đầu vào không có?

Khi `f_e=0`, cung ngược có dư `0` nên không sử dụng được. Sau khi gửi `\Delta` qua cung thuận, cập nhật:

\[
r_{\mathrm{forward}}\gets
r_{\mathrm{forward}}-\Delta,
\]

\[
r_{\mathrm{reverse}}\gets
r_{\mathrm{reverse}}+\Delta.
\]

Ta vừa tiêu thụ `\Delta` khả năng tăng thuận, vừa tạo `\Delta` khả năng **rút lại**. Đây là lý do mọi cài đặt luồng kiểu Ford–Fulkerson/Edmonds–Karp đều cần quản lý **cặp cạnh thuận–ngược**.

### 3.3. Cung dư ngược khác cạnh gốc ngược chiều

Giả sử đầu vào có **hai cạnh thật**:

```text
ID 0: A -> B, capacity 5
ID 1: B -> A, capacity 7
```

Mạng dư ban đầu có **bốn đối tượng cung riêng**:

```text
ID 0: A -> B, thuận, r=5
      B -> A, ngược của ID 0, r=0

ID 1: B -> A, thuận, r=7
      A -> B, ngược của ID 1, r=0
```

Nếu tăng `2` trên **cạnh gốc ID 0**:

```text
ID 0: A -> B, thuận, r=3
      B -> A, ngược, r=2

ID 1: B -> A, thuận, r=7      (không đổi)
      A -> B, ngược, r=0       (không đổi)
```

Lúc này có **hai cung dư `B\to A` khác nhau**: cung ngược mang ý nghĩa hoàn tác `2` trên ID 0, và cung thuận mang ý nghĩa gửi mới tối đa `7` trên ID 1. **Không được gộp hai đối tượng này thành một cờ “có cạnh B→A”.**

Một số định nghĩa lý thuyết gộp dung lượng dư cùng chiều bằng tổng các khả năng khác nhau. Nhưng khi cài danh sách kề và truy vết **luồng trên từng cạnh vật lý**, giữ **cặp cung riêng cho từng ID** rõ ràng và ít lỗi hơn.

## 4. Đường tăng luồng và nút thắt cổ chai

Một **đường tăng luồng** `P` là một đường có hướng từ `s` tới `t` trong mạng dư `G_f` mà **mọi cung trên đường** có dư dương.

Ví dụ:

```text
s --r=6--> a --r=4--> b --r=9--> t
```

Lượng tăng tối đa có thể gửi theo đường này là **nút thắt cổ chai (bottleneck)**:

\[
\boxed{
\Delta=\min_{a\in P}r(a).
}
\]

Ở ví dụ, `\Delta=\min(6,4,9)=4`.

Vì `\Delta\le r(a)` với mọi cung của đường, tăng theo đường đó không làm bất kỳ dung lượng dư nào âm.

### 4.1. Cách tăng theo một đường dư

Với mỗi cung `a` trên đường `P`:

```text
a.residual -= delta
a.reverse.residual += delta
```

Nếu `a` là cung dư **thuận của một cạnh gốc**, ta đã **tăng** luồng gốc thêm `\Delta`. Nếu `a` là cung dư **ngược**, ta đã **giảm** luồng gốc đi `\Delta`.

Phải cập nhật **cả hai cung trong cùng cặp**. Nếu chỉ trừ dư thuận mà không cộng dư ngược, thuật toán mất khả năng hoàn tác và có thể dừng trước tối ưu.

### 4.2. Tại sao luồng mới vẫn hợp lệ?

**Dung lượng:** cung dư thuận của một cạnh gốc chỉ cho phép tăng tối đa `c-f`; cung dư ngược chỉ cho phép giảm tối đa `f`. Chọn `\Delta` không lớn hơn dung lượng dư của từng cung nên luồng gốc luôn trong `[0,c]`.

**Bảo toàn:** tại mỗi đỉnh trung gian trên đường tăng, có đúng một bước dư đi vào và một bước dư đi ra; nhìn theo luồng ròng trên các cạnh gốc, lượng thay đổi vào và ra triệt tiêu nhau. Ở nguồn, lượng ròng rời nguồn tăng `\Delta`; ở đích, lượng ròng nhận được tăng `\Delta`.

Vì vậy, sau mỗi đường tăng, ta nhận một luồng khả thi mới với:

\[
\boxed{|f_{\mathrm{new}}|=|f_{\mathrm{old}}|+\Delta.}
\]

Chú ý: một đường dư có thể đi qua **cung ngược** nhưng giá trị luồng ròng vẫn tăng `\Delta`. Hoàn tác một đoạn luồng cũ ở giữa đường chính là cách **chuyển hướng** luồng để tạo thêm khả năng từ nguồn tới đích.

### 4.3. Nếu không có đường tăng thì sao?

Nếu không còn đường `s\rightsquigarrow t` qua các cung dư dương, ta **không thể áp dụng thêm một bước tăng dọc đường dư**. Định lý max-flow/min-cut ở phần sau chứng minh điều này còn mạnh hơn: **luồng hiện tại đã là luồng cực đại toàn cục**, không chỉ là một cực đại địa phương.

## 5. Ví dụ tối giản: cạnh ngược sửa một lựa chọn đường đi trước đó

Xét mạng có bốn đỉnh `s=0, a=1, b=2, t=3`, tất cả cạnh dung lượng `1`:

```text
ID 0: s -> a  (1)
ID 1: s -> b  (1)
ID 2: a -> b  (1)
ID 3: a -> t  (1)
ID 4: b -> t  (1)
```

Có thể đạt luồng `2` bằng hai đường gốc không tranh chấp cạnh:

```text
s -> a -> t : 1 đơn vị
s -> b -> t : 1 đơn vị
Tổng = 2
```

Nhưng một chiến lược chọn đường tùy ý ban đầu lại có thể chọn:

\[
P_1=s\to a\to b\to t.
\]

Tăng `\Delta=1` theo `P_1`, ta dùng hết dung lượng của `s\to a`, `a\to b` và `b\to t`.

### 5.1. Nếu chỉ tìm đường trong cạnh gốc còn dư

Từ `s`, cạnh `s\to b` còn `1`. Nhưng `b\to t` đã bão hòa; cạnh `b\to a` **không có trong đầu vào**. Nếu chương trình chỉ xem cạnh thuận gốc còn dư, nó có thể kết luận sai rằng không thể tăng thêm.

### 5.2. Mạng dư mở ra đường thứ hai

Sau lần tăng đầu, cung dư ngược `b\to a` của **ID 2: a→b** có dung lượng dư `1`. Vì vậy có một đường tăng mới:

\[
P_2=s\to b\to a\to t,
\]

trong đó **`b\to a` là cung dư ngược**, không phải cạnh gốc mới.

Tăng tiếp `1` theo `P_2`:

- Tăng luồng `s\to b` từ `0` lên `1`.
- **Giảm luồng `a\to b` từ `1` về `0`** (đi qua cung dư ngược).
- Tăng luồng `a\to t` từ `0` lên `1`.

Kết quả:

```text
s -> a : 1
s -> b : 1
a -> b : 0     (đã được hoàn tác)
a -> t : 1
b -> t : 1

Giá trị luồng cuối = 2.
```

Luồng cuối tương đương với hai đường gốc:

```text
s -> a -> t
s -> b -> t
```

**Bài học:** đường tăng trong mạng dư **không nhất thiết** là đường chỉ gồm các cạnh gốc theo chiều gốc. Nó là **một chuỗi thao tác điều chỉnh luồng**, bao gồm tăng mới và hoàn tác, để tạo một luồng tổng thể tốt hơn.

### 5.3. Cạnh ngược có thể biến mất sau khi hoàn tác hết

Với ID 2 `a\to b` dung lượng `1`:

| Giai đoạn | Luồng trên ID 2 | Dư thuận `a→b` | Dư ngược `b→a` |
|---|---:|---:|---:|
| Ban đầu | 0 | 1 | 0 |
| Sau `P_1` | 1 | 0 | 1 |
| Sau `P_2` | 0 | 1 | 0 |

Nếu không cập nhật cả **thuận lẫn ngược** theo mỗi lần tăng, bảng này sẽ không đúng và khả năng phân phối lại luồng sẽ bị mất.

## 6. Một ví dụ Edmonds–Karp thực sự dùng cạnh ngược

Ví dụ phần 5 cố tình chọn đường tăng đầu tiên không ngắn nhất. Điều đó giải thích cơ chế Ford–Fulkerson nói chung, nhưng chưa cho thấy **Edmonds–Karp** (BFS chọn đường dư ngắn nhất theo **số cung**) có thể dùng cạnh ngược.

Xét mạng có **sáu đỉnh** `0..5`, nguồn `s=0`, đích `t=5`, cạnh theo đúng thứ tự ID:

| ID | Cạnh gốc | Dung lượng |
|---:|---|---:|
| 0 | `0\to3` | 3 |
| 1 | `3\to2` | 3 |
| 2 | `2\to5` | 3 |
| 3 | `0\to1` | 1 |
| 4 | `1\to2` | 1 |
| 5 | `3\to4` | 1 |
| 6 | `4\to5` | 1 |

Ta dùng danh sách kề theo thứ tự chèn cạnh và BFS đánh dấu đỉnh ngay khi đưa vào queue.

### 6.1. Lần tăng 1: đường BFS ngắn

BFS gặp đường:

\[
P_1=0\to3\to2\to5,
\]

với:

\[
\Delta_1=\min(3,3,3)=3.
\]

Sau lần này:

- Cạnh ID 0 `0\to3` bão hòa.
- Cạnh ID 1 `3\to2` bão hòa; **cung dư ngược `2\to3` có dung lượng 3**.
- Cạnh ID 2 `2\to5` bão hòa.

Tổng luồng hiện tại là `3`.

### 6.2. Lần tăng 2: dùng cung dư ngược của ID 1

Từ `0` chỉ còn cạnh gốc `0\to1` có khả năng ra ngoài. BFS trong mạng dư tìm đường:

\[
P_2=0\to1\to2\to3\to4\to5.
\]

Tại bước **`2\to3`**, BFS đang đi **cung dư ngược của cạnh gốc ID 1 `3\to2`**. Bottleneck:

\[
\Delta_2=\min(1,1,3,1,1)=1.
\]

Sau lần tăng 2:

- Luồng ID 1 giảm từ `3` xuống `2`.
- Luồng các ID 3,4,5,6 tăng từ `0` lên `1`.
- Giá trị luồng tăng từ `3` lên `4`.

Luồng cuối trên các cạnh gốc theo thứ tự ID:

```text
ID 0 (0->3): 3
ID 1 (3->2): 2    <- được giảm nhờ reverse
ID 2 (2->5): 3
ID 3 (0->1): 1
ID 4 (1->2): 1
ID 5 (3->4): 1
ID 6 (4->5): 1

Giá trị luồng = 4.
```

Kiểm tra bảo toàn tại `2`: luồng vào `2` là `2` từ `3` và `1` từ `1`, tổng `3`; luồng ra `2\to5` là `3`. Tại `3`: vào `3` là `3` từ nguồn; ra `3\to2` là `2` và `3\to4` là `1`, tổng `3`.

Ta có thể **phân rã luồng cuối** thành ba đường chỉ dùng cạnh gốc:

```text
0->3->2->5 : 2 đơn vị
0->3->4->5 : 1 đơn vị
0->1->2->5 : 1 đơn vị
Tổng = 4.
```

Đây là minh chứng cụ thể rằng luồng ban đầu đã được **định tuyến lại**: một đơn vị vốn đi qua `3\to2` được chuyển sang `3\to4`, nhường chỗ cho một đơn vị mới đi từ `0\to1\to2\to5`.

### 6.3. Vì sao luồng 4 là cực đại?

Nguồn `0` chỉ có hai cạnh đi ra:

```text
0->3 capacity 3
0->1 capacity 1
```

Bất kỳ luồng nào cũng có:

\[
|f|\le3+1=4.
\]

Thuật toán đã đạt đúng `4`, nên không thể tăng thêm. Lát cắt `S=\{0\}` và `T=V\setminus S` có dung lượng `4`. Đó là một **min-cut**.

## 7. Ford–Fulkerson và Edmonds–Karp

**Ford–Fulkerson** là khung thuật toán:

```text
Khởi tạo luồng bằng 0
Tạo mạng dư với mỗi cạnh gốc có một cung thuận
và một cung ngược ban đầu có dư 0

while tồn tại đường tăng từ s tới t trong mạng dư:
    delta = min residual trên đường
    for mỗi cung a trên đường:
        a.residual -= delta
        a.reverse.residual += delta
    flowValue += delta

Trả flowValue và luồng trên các cạnh gốc.
```

Phần không cố định là **cách chọn đường tăng**.

### 7.1. Tìm bằng DFS

Có thể dùng DFS trong mạng dư để lấy **bất kỳ đường tăng nào**. Với dung lượng **nguyên không âm**, mỗi lần tăng theo bottleneck ít nhất là `1`, nên sau hữu hạn lần sẽ dừng. Tuy nhiên độ phức tạp theo giá trị luồng tối đa có thể rất xấu; không phải thuật toán đa thức mạnh theo số bit đầu vào.

Thường viết giới hạn đơn giản cho Ford–Fulkerson dùng DFS và dung lượng nguyên là:

\[
O(E\,|f^*|),
\]

với `|f^*|` là giá trị luồng cực đại, giả sử các lần tăng ít nhất một đơn vị và tìm đường `O(E)`. Giới hạn này **phụ thuộc độ lớn số học** của luồng tối đa, không chỉ vào số đỉnh/cạnh.

Với dung lượng thực vô tỉ và một quy tắc chọn đường không phù hợp, Ford–Fulkerson tổng quát có thể **không dừng** hoặc không đạt max flow sau hữu hạn bước. Không được dùng lập luận “mỗi lần tăng ít nhất 1” trong trường hợp trọng số thực.

### 7.2. Edmonds–Karp: tìm đường tăng bằng BFS

**Edmonds–Karp** chọn đường tăng có **ít cung dư nhất** từ `s` tới `t` bằng **BFS**. Không xét trọng số chi phí hay độ dài số học của cạnh; BFS chỉ cần xem cung có dư `>0`.

Một lượt:

1. BFS từ `s` trên những cung dư có dung lượng dương.
2. Lưu `parentArc[v]`: **chính đối tượng cung dư** đã đưa BFS đến `v`.
3. Nếu không thăm tới `t`, dừng.
4. Lần ngược các cung từ `t` về `s` để tính bottleneck.
5. Cập nhật hai chiều của từng cặp cung dư.
6. Lặp lại.

Nhờ BFS, Edmonds–Karp có bảo đảm:

\[
\boxed{O(VE^2)}
\]

thời gian trên mô hình thao tác số học hằng số, bất kể dung lượng cực đại lớn bao nhiêu. Đồ thị lưu `2E` cung dư (một cặp cho mỗi cạnh gốc), nên bộ nhớ cho mạng dư **`O(V+E)`**.

### 7.3. Định lý số lần tăng của Edmonds–Karp

Gọi `dist_f(v)` là khoảng cách theo số cung từ nguồn tới `v` trong mạng dư hiện tại.

Trong Edmonds–Karp, các khoảng cách BFS tới những đỉnh còn tới được **không giảm** qua các lần tăng (theo nghĩa khoảng cách ngắn nhất khi vẫn tới được). Mỗi lần tăng làm **bão hòa ít nhất một cung** trên đường BFS được chọn.

Một cung có thể được bão hòa nhiều lần sau khi dung lượng dư của nó được phục hồi nhờ sử dụng cung ngược. Nhưng để nó được bão hòa lại trong một đường BFS, mức khoảng cách liên quan phải **tăng ít nhất 2** trong quá trình đó. Vì khoảng cách BFS hữu hạn không vượt `V-1`, mỗi cung được bão hòa chỉ `O(V)` lần.

Với `O(E)` cung dư, tổng số lần tăng là `O(VE)`. Mỗi BFS quét `O(E)` cung (cộng `O(V)` công việc), suy ra `O(VE^2)` với đồ thị được biểu diễn thông thường. Đây là điểm mạnh của BFS so với chọn đường DFS tùy ý.

### 7.4. Edmonds–Karp không phải min-cost max-flow

Edmonds–Karp tìm **giá trị luồng lớn nhất**, không tối ưu **chi phí vận chuyển** trên các cạnh. BFS tối thiểu hóa **số cung của một đường tăng**, không tối thiểu hóa tổng cost. Muốn tìm **max flow có tổng chi phí nhỏ nhất**, cần một mô hình/thuật toán **min-cost flow** khác, thường dùng chi phí dư và đường tăng chi phí thấp với các kỹ thuật phù hợp.

## 8. Định lý max-flow/min-cut: chứng nhận rằng không còn đường tăng

Một **lát cắt `(S,T)`** chia `V` thành hai tập rời nhau, với:

\[
s\in S,\qquad t\in T.
\]

**Dung lượng lát cắt** là tổng dung lượng **các cạnh gốc đi từ `S` sang `T`**, không trừ cạnh đi ngược lại:

\[
\boxed{
c(S,T)=\sum_{\substack{e=(u,v)\in E\\u\in S,\ v\in T}}c(e).
}
\]

### 8.1. Mọi luồng đều không vượt dung lượng của mọi lát cắt

Theo bảo toàn luồng trên mọi đỉnh trung gian, tổng luồng ròng rời `S` phải bằng giá trị `|f|`:

\[
|f|=
\sum_{u\in S,v\in T}f(u,v)
-
\sum_{u\in T,v\in S}f(u,v),
\]

trong đó mỗi tổng tính theo **cạnh vật lý và đúng chiều**.

Vì `0\le f(e)\le c(e)`:

\[
\boxed{|f|\le c(S,T).}
\]

Vậy bất kỳ lát cắt nào cũng đưa ra một **cận trên** cho luồng cực đại.

### 8.2. Không có đường dư s→t thì xây được một lát cắt bằng giá trị luồng

Giả sử BFS trong mạng dư không tới được `t`. Gọi:

\[
S=\{\text{các đỉnh còn tới được từ }s
\text{ theo cung dư dương}\},
\quad T=V\setminus S.
\]

Khi ấy `s\in S` và `t\in T`.

- Với cạnh gốc `e=(u,v)` có `u\in S,v\in T`, cung dư thuận `u\to v` phải có dư `0`; nếu dương thì `v` cũng tới được. Vì vậy **`f(e)=c(e)`**: mọi cạnh gốc băng từ `S` sang `T` đều bão hòa.
- Với cạnh gốc `e=(v,u)` đi **từ `T` về `S`**, cung dư ngược `u\to v` có dung lượng `f(e)`. Nếu `f(e)>0`, BFS từ `S` sẽ tới được `v\in T`, mâu thuẫn. Vì vậy **`f(e)=0`** trên tất cả cạnh gốc từ `T` về `S`.

Từ biểu thức luồng ròng qua lát cắt:

\[
|f|=
\sum_{S\to T}c(e)-\sum_{T\to S}0
=c(S,T).
\]

Mặt khác mọi luồng đều có giá trị không vượt `c(S,T)`. Luồng hiện tại **đạt cận trên**, nên là **luồng cực đại**; lát cắt ấy là **min-cut**.

### 8.3. Ba phát biểu tương đương

Đối với một luồng **khả thi** `f`:

\[
\boxed{
f\text{ là luồng cực đại}
\iff
G_f\text{ không có đường tăng }s\to t
\iff
\exists(S,T):|f|=c(S,T).
}
\]

Đây chính là **định lý luồng cực đại – lát cắt cực tiểu (max-flow/min-cut theorem)**.

Đừng kết luận “không có đường nào trên **đồ thị gốc chỉ dùng cạnh chưa bão hòa**” là cực đại. Phải tìm trong **mạng dư đầy đủ**, gồm cả các cung ngược có dư dương.

### 8.4. Lát cắt cuối không nhất thiết duy nhất

Từ mạng dư cuối cùng, BFS tới được tập `S` tạo **một min-cut**. Đồ thị có thể có nhiều min-cut khác cùng dung lượng, cũng như có thể có nhiều cách phân phối luồng cực đại khác nhau. Bài toán max flow thường chỉ đòi giá trị hoặc một nghiệm; không được giả định kết quả cạnh và tập min-cut là duy nhất.

## 9. Cài đặt mạng dư: giữ cặp cung bằng tham chiếu trực tiếp

Có hai cách phổ biến:

1. **Chỉ số reverse (`revIndex`):** trong mỗi đối tượng cung lưu chỉ số của cung ngược trong danh sách kề của đỉnh đích.
2. **Tham chiếu đôi (`reverse` pointer):** mỗi đối tượng `Arc` trỏ trực tiếp tới đối tượng cung dư ngược của nó.

Cả hai đúng nếu duy trì cặp nhất quán. Đoạn Java ở phần 11 dùng **tham chiếu đôi**, vì nó dễ kiểm tra và xử lý được các trường hợp **khuyên, cạnh song song, cạnh gốc hai chiều** mà không cần sửa chỉ số riêng cho `u=v`.

### 9.1. Một cạnh vật lý luôn sinh đúng hai đối tượng Arc

Cho cạnh gốc `e=(u,v,c)`:

```text
Arc forward:
    from = u, to = v, residual = c
    original = true, edgeId = id

Arc backward:
    from = v, to = u, residual = 0
    original = false, edgeId = id

forward.reverse = backward
backward.reverse = forward
adj[u].add(forward)
adj[v].add(backward)
```

Nếu `u=v` (khuyên), cả hai Arc nằm trong **cùng một danh sách kề**, nhưng vẫn là **hai đối tượng phân biệt** tham chiếu qua lại. BFS không chọn khuyên thành cạnh của đường đơn vì đỉnh đã được đánh dấu thăm; khuyên cũng không làm thay đổi giá trị luồng cực đại từ nguồn tới đích.

### 9.2. Không được đồng nhất reverse với “cạnh đã có”

Một lỗi thường gặp:

```text
Nếu adj[v] đã có cạnh v->u, dùng cạnh ấy làm reverse của u->v.
```

Đây là **sai** nếu cạnh `v\to u` ấy là một cạnh gốc riêng có dung lượng riêng. Hai cạnh gốc phải có **hai cặp dư độc lập**, nếu không cập nhật một cạnh sẽ vô tình thay đổi khả năng gửi luồng thật trên cạnh khác.

### 9.3. Tại sao BFS lưu Arc, không chỉ lưu đỉnh cha?

Nếu mạng có cạnh song song hoặc có nhiều cung dư cùng chiều, chỉ lưu `parentVertex[v]` không đủ để biết **cung nào** đã được BFS chọn. Phải lưu thêm **Arc cụ thể** hoặc **edgeId+chỉ số cung**.

Trong mã:

```java
parentVertex[v] = u;
parentArc[v] = arc;
```

Khi lần ngược từ `t` tới `s`, `parentArc[v]` cho biết chính xác dung lượng dư và đối tượng `reverse` cần cập nhật. Với `BigInteger`, cũng tránh dùng một sentinel số lớn để thay cho bottleneck: bắt đầu từ `null` rồi lấy min các cung thực sự nằm trên đường.

## 10. Những trường hợp đầu vào cần có chính sách rõ ràng

### 10.1. Dung lượng âm

Dung lượng phải **không âm**. Một cạnh có capacity `-1` không có ý nghĩa trong mô hình flow chuẩn và phải bị từ chối, thay vì âm thầm xem là cạnh không đi được.

### 10.2. Dung lượng bằng 0

Cạnh capacity `0` là cạnh gốc hợp lệ nhưng không có dư thuận dương lúc đầu. Nó không được dùng trong đường tăng cho tới khi có điều chỉnh hợp lệ liên quan; với luồng gốc trên cạnh đó luôn bằng `0`.

Khi tính dung lượng min-cut, cạnh capacity `0` băng qua lát cắt vẫn có thể được liệt kê nhưng đóng góp `0`.

### 10.3. Nguồn và đích trùng nhau

Bài toán max flow chuẩn trong bài này yêu cầu **`s\ne t`**. Nếu `s=t`, một “đường” độ dài `0` gây mơ hồ cho vòng tăng, nên API Java **từ chối** trường hợp này. Nếu bài khác định nghĩa flow từ một đỉnh tới chính nó là `0`, phải xử lý riêng trước khi gọi thuật toán.

### 10.4. Đồ thị không có đường nguồn–đích

Nếu không có đường dư dương `s\rightsquigarrow t` ngay từ đầu, luồng `0` là tối ưu. Edmonds–Karp không ném lỗi và không trả một đường giả; nó trả `0` và một min-cut dung lượng `0`.

### 10.5. Cạnh song song và cạnh ngược chiều thật

- Mỗi cạnh song song có ID và cặp Arc riêng.
- Cạnh gốc `u\to v` và `v\to u` không chia sẻ cặp Arc.
- Khi có nhiều cung dư giữa hai đỉnh, BFS giữ thứ tự chèn và chọn **đối tượng Arc** chứ không chọn “cặp đỉnh” chung chung.
- Thứ tự đường tăng có thể thay đổi nếu đổi thứ tự input, nhưng **giá trị max flow** không đổi.

### 10.6. Dung lượng và tổng luồng rất lớn

Một cạnh gốc có capacity `long`, nhưng tổng luồng từ nhiều cạnh có thể vượt `Long.MAX_VALUE`. Nếu dùng `long maxFlow`, phép cộng số lớn có thể tràn.

Ví dụ có hai cạnh song song `s\to t`, mỗi cạnh capacity `Long.MAX_VALUE`. Giá trị luồng cực đại là:

\[
2\cdot Long.MAX\_VALUE
=18446744073709551614.
\]

Chương trình Java sử dụng **`BigInteger`** cho dung lượng dư, bottleneck, luồng trên cạnh, giá trị max flow và dung lượng min-cut. Đầu vào vẫn dùng `long capacity`; do vậy mỗi cạnh hợp lệ có capacity tối đa `Long.MAX_VALUE`, còn tổng không bị tràn.

### 10.7. Dung lượng không nguyên

Edmonds–Karp cũng đúng về mặt lý thuyết với dung lượng hữu hạn không âm là số thực khi phép tính đủ chính xác; số lần tăng bị chặn theo cấu trúc BFS. Trong thực tế, dùng `double` có thể gây dư rất nhỏ do sai số, khiến thuật toán lặp trên các cạnh có dư gần `0`.

Nếu bài dùng dung lượng số thực, phải chốt quy ước so sánh `>epsilon`, cách làm tròn và mức sai số được chấp nhận. Chương trình trong bài dùng **dung lượng nguyên** để tránh toàn bộ mơ hồ số thực.

## 11. Java 17+ hoàn chỉnh: Edmonds–Karp, cạnh ngược và min-cut

Chương trình độc lập sau:

1. Nhận danh sách **cạnh có hướng** `InputEdge(from,to,capacity)` theo thứ tự được cung cấp.
2. Kiểm tra `n\ge2`, `s,t` hợp lệ và khác nhau; mọi endpoint hợp lệ; capacity không âm.
3. Tạo **một cặp Arc thuận–ngược riêng cho mỗi cạnh gốc**, cả khi hai cạnh gốc ngược chiều nhau, có cạnh song song hoặc khuyên.
4. Dùng **BFS** tìm đường tăng ngắn nhất theo số cung dư, lưu đúng đối tượng `Arc` trong `parentArc[]`.
5. Tìm bottleneck bằng `BigInteger`; cập nhật cả hai cung của mỗi cặp.
6. Lưu lịch sử từng đường tăng, phân biệt bước **thuận F** và **ngược R**.
7. Khi không còn đường dư, xác định tập `S` tới được, danh sách cạnh gốc cắt từ `S` sang phần còn lại và dung lượng cut.
8. Xác minh **`maxFlow==cutCapacity`**, mọi `0\le f_e\le c_e` và bảo toàn luồng ở các đỉnh trung gian.
9. Kiểm thử **300 mạng nhỏ** bằng cách vét cạn **mọi tập cắt `S`** chứa `s` mà không chứa `t` (oracle độc lập), và so dung lượng nhỏ nhất với max flow.

Hàm `solve` trả **một giá trị max flow**, một phương án luồng trên từng cạnh gốc, lịch sử tăng luồng và chứng chỉ min-cut. Nếu có nhiều nghiệm tối ưu, chuỗi đường tăng và luồng từng cạnh có thể thay đổi theo thứ tự input.

**Tên tệp:** `ResidualAugmentingPathDemo.java`.

```java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public final class ResidualAugmentingPathDemo {
    private ResidualAugmentingPathDemo() {
    }

    public record InputEdge(
            int from, int to, long capacity) {
    }

    public record Step(
            int from, int to,
            int originalEdgeId, boolean reverse) {
    }

    public record Augment(
            BigInteger delta, List<Step> path) {
        public Augment {
            path = List.copyOf(path);
        }
    }

    public record Result(
            BigInteger maxFlow,
            List<BigInteger> edgeFlows,
            List<Augment> augmentations,
            List<Integer> sourceSide,
            List<Integer> cutEdgeIds,
            BigInteger cutCapacity) {
        public Result {
            edgeFlows = List.copyOf(edgeFlows);
            augmentations = List.copyOf(augmentations);
            sourceSide = List.copyOf(sourceSide);
            cutEdgeIds = List.copyOf(cutEdgeIds);
        }
    }

    private static final class Arc {
        final int to;
        final int originalEdgeId;
        final boolean original;
        BigInteger residual;
        Arc reverse;

        Arc(int to, BigInteger residual,
                int originalEdgeId, boolean original) {
            this.to = to;
            this.residual = residual;
            this.originalEdgeId = originalEdgeId;
            this.original = original;
        }
    }

    private static void validate(
            int n, List<InputEdge> edges,
            int source, int sink) {
        Objects.requireNonNull(edges, "edges");
        if (n < 2 || source < 0 || source >= n
                || sink < 0 || sink >= n
                || source == sink) {
            throw new IllegalArgumentException(
                "require n>=2 and distinct valid source/sink"
            );
        }
        for (InputEdge edge : edges) {
            Objects.requireNonNull(edge, "edge");
            if (edge.from() < 0 || edge.from() >= n
                    || edge.to() < 0 || edge.to() >= n
                    || edge.capacity() < 0) {
                throw new IllegalArgumentException(
                    "invalid edge endpoint or capacity"
                );
            }
        }
    }

    private static List<List<Arc>> emptyAdj(int n) {
        List<List<Arc>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }
        return graph;
    }

    // Chỉ đi qua những cung dư có dung lượng > 0.
    private static boolean bfs(
            List<List<Arc>> graph, int source, int sink,
            int[] parentVertex, Arc[] parentArc) {
        Arrays.fill(parentVertex, -1);
        Arrays.fill(parentArc, null);

        Deque<Integer> queue = new ArrayDeque<>();
        parentVertex[source] = source;
        queue.addLast(source);

        while (!queue.isEmpty()
                && parentVertex[sink] == -1) {
            int u = queue.removeFirst();

            for (Arc arc : graph.get(u)) {
                if (arc.residual.signum() <= 0
                        || parentVertex[arc.to] != -1) {
                    continue;
                }
                parentVertex[arc.to] = u;
                parentArc[arc.to] = arc;
                queue.addLast(arc.to);

                if (arc.to == sink) {
                    break;
                }
            }
        }
        return parentVertex[sink] != -1;
    }

    private static boolean[] reachableInResidual(
            List<List<Arc>> graph, int source) {
        boolean[] seen = new boolean[graph.size()];
        Deque<Integer> queue = new ArrayDeque<>();
        seen[source] = true;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (Arc arc : graph.get(u)) {
                if (arc.residual.signum() > 0
                        && !seen[arc.to]) {
                    seen[arc.to] = true;
                    queue.addLast(arc.to);
                }
            }
        }
        return seen;
    }

    public static Result solve(
            int n, List<InputEdge> input,
            int source, int sink) {
        validate(n, input, source, sink);

        List<List<Arc>> graph = emptyAdj(n);
        List<Arc> originals = new ArrayList<>();

        // Một cặp cung dư riêng cho mỗi cạnh vật lý.
        for (int id = 0; id < input.size(); id++) {
            InputEdge e = input.get(id);

            Arc forward = new Arc(
                e.to(), BigInteger.valueOf(e.capacity()),
                id, true
            );
            Arc backward = new Arc(
                e.from(), BigInteger.ZERO, id, false
            );

            forward.reverse = backward;
            backward.reverse = forward;

            graph.get(e.from()).add(forward);
            graph.get(e.to()).add(backward);
            originals.add(forward);
        }

        BigInteger maxFlow = BigInteger.ZERO;
        List<Augment> history = new ArrayList<>();
        int[] parentVertex = new int[n];
        Arc[] parentArc = new Arc[n];

        // Edmonds-Karp: BFS ngắn nhất theo số cung dư.
        while (bfs(
                graph, source, sink,
                parentVertex, parentArc)) {
            BigInteger delta = null;
            List<Step> backwardSteps = new ArrayList<>();

            for (int v = sink; v != source;
                    v = parentVertex[v]) {
                int u = parentVertex[v];
                Arc arc = parentArc[v];

                if (delta == null
                        || arc.residual.compareTo(delta) < 0) {
                    delta = arc.residual;
                }
                backwardSteps.add(new Step(
                    u, v, arc.originalEdgeId, !arc.original
                ));
            }

            if (delta == null || delta.signum() <= 0) {
                throw new IllegalStateException(
                    "BFS produced an invalid augmenting path"
                );
            }

            Collections.reverse(backwardSteps);

            for (int v = sink; v != source;
                    v = parentVertex[v]) {
                Arc arc = parentArc[v];
                arc.residual = arc.residual.subtract(delta);
                arc.reverse.residual =
                    arc.reverse.residual.add(delta);
            }

            maxFlow = maxFlow.add(delta);
            history.add(new Augment(delta, backwardSteps));
        }

        // Chứng chỉ min-cut: S = các đỉnh còn tới được.
        boolean[] reachable =
            reachableInResidual(graph, source);

        List<Integer> sourceSide = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            if (reachable[u]) {
                sourceSide.add(u);
            }
        }
        if (reachable[sink]) {
            throw new IllegalStateException(
                "sink must be unreachable after termination"
            );
        }

        List<Integer> cutEdgeIds = new ArrayList<>();
        BigInteger cutCapacity = BigInteger.ZERO;
        for (int id = 0; id < input.size(); id++) {
            InputEdge e = input.get(id);
            if (reachable[e.from()] && !reachable[e.to()]) {
                cutEdgeIds.add(id);
                cutCapacity = cutCapacity.add(
                    BigInteger.valueOf(e.capacity())
                );
            }
        }

        // Luồng gốc = dư của cung ngược trong cùng cặp.
        List<BigInteger> edgeFlows = new ArrayList<>();
        BigInteger[] net = new BigInteger[n];
        Arrays.fill(net, BigInteger.ZERO);

        for (int id = 0; id < input.size(); id++) {
            InputEdge e = input.get(id);
            BigInteger flow =
                originals.get(id).reverse.residual;
            BigInteger capacity =
                BigInteger.valueOf(e.capacity());

            if (flow.signum() < 0
                    || flow.compareTo(capacity) > 0) {
                throw new IllegalStateException(
                    "capacity invariant violated"
                );
            }

            edgeFlows.add(flow);
            net[e.from()] = net[e.from()].add(flow);
            net[e.to()] = net[e.to()].subtract(flow);
        }

        for (int u = 0; u < n; u++) {
            BigInteger expected = u == source
                ? maxFlow
                : u == sink
                    ? maxFlow.negate()
                    : BigInteger.ZERO;

            if (!net[u].equals(expected)) {
                throw new IllegalStateException(
                    "flow conservation invariant violated"
                );
            }
        }
        if (!maxFlow.equals(cutCapacity)) {
            throw new IllegalStateException(
                "max-flow/min-cut certificate failed"
            );
        }

        return new Result(
            maxFlow, edgeFlows, history,
            sourceSide, cutEdgeIds, cutCapacity
        );
    }

    private static String pathText(List<Step> path) {
        List<String> parts = new ArrayList<>();

        for (Step step : path) {
            parts.add(
                step.from() + "->" + step.to()
                + "[" + (step.reverse() ? "R" : "F")
                + step.originalEdgeId() + "]"
            );
        }
        return String.join(" ", parts);
    }

    // Oracle độc lập: vét cạn mọi lát cắt S chứa s, bỏ t.
    // Chỉ dùng cho n nhỏ trong kiểm thử.
    private static BigInteger bruteMinCut(
            int n, List<InputEdge> edges,
            int source, int sink) {
        if (n > 12) {
            throw new IllegalArgumentException(
                "min-cut brute force requires n<=12"
            );
        }

        BigInteger best = null;
        int subsets = 1 << n;

        for (int mask = 0; mask < subsets; mask++) {
            if ((mask & (1 << source)) == 0
                    || (mask & (1 << sink)) != 0) {
                continue;
            }

            BigInteger capacity = BigInteger.ZERO;
            for (InputEdge e : edges) {
                boolean fromInS =
                    (mask & (1 << e.from())) != 0;
                boolean toInS =
                    (mask & (1 << e.to())) != 0;

                if (fromInS && !toInS) {
                    capacity = capacity.add(
                        BigInteger.valueOf(e.capacity())
                    );
                }
            }

            if (best == null
                    || capacity.compareTo(best) < 0) {
                best = capacity;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        // Thứ tự cạnh quyết định đường BFS trên mẫu.
        List<InputEdge> main = List.of(
            new InputEdge(0, 3, 3), // ID 0
            new InputEdge(3, 2, 3), // ID 1
            new InputEdge(2, 5, 3), // ID 2
            new InputEdge(0, 1, 1), // ID 3
            new InputEdge(1, 2, 1), // ID 4
            new InputEdge(3, 4, 1), // ID 5
            new InputEdge(4, 5, 1)  // ID 6
        );

        Result a = solve(6, main, 0, 5);
        System.out.println("Main max flow: " + a.maxFlow());

        for (int i = 0; i < a.augmentations().size(); i++) {
            Augment augment = a.augmentations().get(i);
            System.out.println(
                "Augment " + (i + 1)
                + ": delta=" + augment.delta()
                + " path=" + pathText(augment.path())
            );
        }

        System.out.println(
            "Main edge flows: " + a.edgeFlows()
        );
        System.out.println(
            "Main source side: " + a.sourceSide()
        );
        System.out.println(
            "Main cut IDs: " + a.cutEdgeIds()
        );
        System.out.println(
            "Main cut capacity: " + a.cutCapacity()
        );

        // Hai cạnh song song, cạnh gốc ngược và khuyên.
        List<InputEdge> mixed = List.of(
            new InputEdge(0, 1, 2),
            new InputEdge(0, 1, 3),
            new InputEdge(1, 2, 5),
            new InputEdge(2, 1, 7),
            new InputEdge(1, 1, 4)
        );

        Result b = solve(3, mixed, 0, 2);
        System.out.println(
            "Mixed max flow: " + b.maxFlow()
        );
        System.out.println(
            "Mixed edge flows: " + b.edgeFlows()
        );
        System.out.println(
            "Mixed cut capacity: " + b.cutCapacity()
        );

        // Tổng luồng vượt Long.MAX_VALUE dù mỗi cạnh hợp lệ.
        List<InputEdge> huge = List.of(
            new InputEdge(0, 1, Long.MAX_VALUE),
            new InputEdge(0, 1, Long.MAX_VALUE)
        );
        Result big = solve(2, huge, 0, 1);
        System.out.println(
            "Huge max flow: " + big.maxFlow()
        );

        Result empty = solve(3, List.of(), 0, 2);
        System.out.println(
            "Empty max flow: " + empty.maxFlow()
        );
        System.out.println(
            "Empty min-cut capacity: " + empty.cutCapacity()
        );

        boolean negativeRejected = false;
        try {
            solve(
                2, List.of(new InputEdge(0, 1, -1)),
                0, 1
            );
        } catch (IllegalArgumentException expected) {
            negativeRejected = true;
        }
        System.out.println(
            "Negative capacity rejected: "
            + negativeRejected
        );

        boolean sameVertexRejected = false;
        try {
            solve(2, List.of(), 0, 0);
        } catch (IllegalArgumentException expected) {
            sameVertexRejected = true;
        }
        System.out.println(
            "Source equals sink rejected: "
            + sameVertexRejected
        );

        Random random = new Random(328L);
        int checked = 0;

        for (int trial = 0; trial < 300; trial++) {
            int n = 2 + random.nextInt(6);
            int m = random.nextInt(15);
            List<InputEdge> edges = new ArrayList<>();

            for (int id = 0; id < m; id++) {
                int u = random.nextInt(n);
                int v = random.nextInt(n);
                long capacity = random.nextInt(8);
                edges.add(new InputEdge(u, v, capacity));
            }

            int source = 0;
            int sink = n - 1;
            Result result = solve(n, edges, source, sink);
            BigInteger oracle =
                bruteMinCut(n, edges, source, sink);

            if (!result.maxFlow().equals(oracle)
                    || !result.cutCapacity().equals(oracle)) {
                throw new AssertionError(
                    "min-cut mismatch at trial " + trial
                );
            }
            checked++;
        }
        System.out.println(
            "Random min-cut comparisons: " + checked
        );
    }
}
```

Lưu UTF-8, biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 ResidualAugmentingPathDemo.java
java ResidualAugmentingPathDemo
```

**Đầu ra chuẩn (deterministic với thứ tự cạnh đã cho):**

```text
Main max flow: 4
Augment 1: delta=3 path=0->3[F0] 3->2[F1] 2->5[F2]
Augment 2: delta=1 path=0->1[F3] 1->2[F4] 2->3[R1] 3->4[F5] 4->5[F6]
Main edge flows: [3, 2, 3, 1, 1, 1, 1]
Main source side: [0]
Main cut IDs: [0, 3]
Main cut capacity: 4
Mixed max flow: 5
Mixed edge flows: [2, 3, 5, 0, 0]
Mixed cut capacity: 5
Huge max flow: 18446744073709551614
Empty max flow: 0
Empty min-cut capacity: 0
Negative capacity rejected: true
Source equals sink rejected: true
Random min-cut comparisons: 300
```

### 11.1. Cách đọc ký hiệu F/R trong lịch sử tăng luồng

Trong output:

```text
3->2[F1]
```

nghĩa là đi **cung dư thuận của cạnh gốc ID 1**, nên tăng luồng trên cạnh `3\to2`.

Còn:

```text
2->3[R1]
```

nghĩa là đi **cung dư ngược của chính cạnh gốc ID 1**, nên **giảm** luồng trên `3\to2`. Đây **không** phải một cạnh thật `2\to3` có ID mới.

Cặp ID 1 từ `f=0` qua lần đầu `f=3`, rồi qua lần hai `f=2`. Output `Main edge flows` xác nhận việc hoàn tác này.

### 11.2. Vì sao main cut là S=[0]?

Sau hai lần tăng, hai cạnh đi ra nguồn `0\to3` và `0\to1` đều bão hòa, nên trong mạng dư không còn cung dương nào từ `0` tới đỉnh khác. BFS dư cuối chỉ tới được `S=\{0\}`.

Những cạnh gốc băng qua lát cắt `S\to T` là ID 0 dung lượng `3` và ID 3 dung lượng `1`, tổng `4`. Luồng cũng bằng `4`, nên bằng định lý max-flow/min-cut, kết quả tối ưu.

### 11.3. Vì sao kiểm tra bảo toàn luồng bằng net?

Trong mã:

```java
net[e.from()] = net[e.from()].add(flow);
net[e.to()] = net[e.to()].subtract(flow);
```

`net[u]` là **luồng ròng đi ra** khỏi `u`. Sau khi cộng tất cả cạnh gốc:

- `net[source]=maxFlow`.
- `net[sink]=-maxFlow`.
- Mọi `net[u]=0` ở đỉnh trung gian.

Đây là kiểm tra độc lập với số lần tăng và chiều của từng cung dư. Với khuyên `u\to u`, một cạnh được cộng rồi trừ ngay trên cùng phần tử `net[u]`, đúng vì nó không tạo thêm luồng ròng.

### 11.4. Vì sao dùng BigInteger?

Hai cạnh song song từ `0` sang `1`, mỗi cạnh `Long.MAX_VALUE`, có thể cùng được dùng hết; kết quả:

\[
2\cdot 9223372036854775807
=18446744073709551614.
\]

Một `long` có dấu không biểu diễn được tổng này. Mã dùng `BigInteger` cho **dư, bottleneck, tổng luồng, tổng cut và chứng chỉ bảo toàn**, nên không bị tràn.

### 11.5. Tại sao mixed không bị ảnh hưởng bởi cạnh ngược gốc?

Ở `mixed`, cạnh gốc ID 3 là `2\to1` dung lượng `7`; cạnh ID 2 là `1\to2` dung lượng `5`. Mỗi cạnh gốc sinh **cặp dư riêng**, không dùng chung một đối tượng Arc.

Kết quả có luồng ID 2 bằng `5`, ID 3 bằng `0`, dù cả hai có cùng cặp đầu mút nhưng ngược chiều. Khuyên ID 4 `1\to1` cũng có luồng `0`. Hai cạnh song song ID 0,1 gửi `2+3=5`.

### 11.6. Xác minh kích thước kết quả

`Result.edgeFlows()` có đúng một giá trị cho **mỗi ID cạnh gốc**. `Result.augmentations()` có một bản ghi cho mỗi lần BFS thành công. `sourceSide()` chứa đỉnh ở phía `S` của min-cut cuối; `cutEdgeIds()` liệt kê **cạnh gốc từ `S` sang `T`**, không liệt kê các cung dư ngược tự sinh.

Hàm `solve` kiểm tra lại khả thi và max-flow/min-cut trước khi trả, nên nếu một sửa đổi code làm hỏng tính bảo toàn hoặc cập nhật cặp dư, chương trình có cơ hội phát hiện bằng ngoại lệ.

## 12. Chứng minh tính đúng của thuật toán tăng luồng

### 12.1. Bất biến trước mỗi BFS

Trước mỗi lần BFS:

1. Với mỗi cạnh gốc `e`, `0\le f_e\le c_e`.
2. Mọi đỉnh trung gian bảo toàn luồng.
3. Dư thuận là `c_e-f_e` và dư ngược là `f_e`, không âm.
4. Giá trị `maxFlow` bằng lượng ròng rời nguồn.
5. Các cặp Arc thuận/ngược tham chiếu đúng lẫn nhau, và tổng dư của một cặp là capacity gốc.

**Cơ sở:** khởi tạo `f_e=0`, dư thuận bằng `c_e` và dư ngược bằng `0`, nên tất cả bất biến đúng; giá trị luồng `0`.

### 12.2. Bước tăng giữ bất biến

Nếu BFS tìm được một đường dư `P`, mọi cung của nó có dư dương. Chọn `\Delta` là min dư trên đường nên `\Delta>0`.

Với mỗi cung trên đường, trừ dư của cung được đi và cộng vào dư của cung đối. Điều này tương đương:

- Tăng `f_e` trên những cạnh gốc được đi thuận.
- Giảm `f_e` trên những cạnh gốc được đi ngược.

Vì `\Delta` không vượt dư theo chiều điều chỉnh, luồng mới vẫn nằm trong `[0,c_e]`. Tại đỉnh trung gian, tác động ròng của một bước vào và một bước ra cân bằng nhau. Giá trị luồng tăng đúng `\Delta`.

Vì vậy tất cả bất biến được giữ sau mỗi lần tăng.

### 12.3. Dừng nghĩa là tối ưu

Khi BFS thất bại, gọi `S` là tập đỉnh còn tới được theo cung dư dương. Phần 8.2 đã chứng minh mọi cạnh gốc từ `S` sang `T` đều bão hòa, mọi cạnh gốc từ `T` về `S` có luồng `0`. Vậy:

\[
|f|=c(S,T).
\]

Mọi luồng khả thi đều không vượt dung lượng lát cắt đó, nên luồng hiện tại là **cực đại toàn cục**. Đây là chứng minh dừng–tối ưu.

### 12.4. Tại sao thuật toán thực sự dừng?

Với capacity nguyên không âm, mỗi lần tăng gửi một lượng dương nguyên và giá trị luồng tăng nghiêm ngặt. Giá trị luồng bị chặn trên bởi tổng capacity các cạnh đi ra nguồn, nên Ford–Fulkerson chọn đường bất kỳ cũng kết thúc sau hữu hạn bước (dù có thể rất nhiều).

Riêng Edmonds–Karp còn được bảo đảm `O(VE)` lần tăng qua phân tích khoảng cách BFS và các lần bão hòa cung, nên có độ phức tạp đa thức `O(VE^2)`.

### 12.5. Cần gì nếu chỉ muốn biết giá trị max flow?

Nếu không cần in lịch sử đường tăng, có thể **bỏ `history`** để giảm bộ nhớ xuống `O(V+E)` cho mạng dư và cấu trúc BFS. Giá trị `maxFlow` vẫn được cập nhật qua mỗi `\Delta`, và min-cut cuối vẫn có thể trích xuất.

Việc lưu đầy đủ tất cả đường tăng có thể tốn thêm `O(V)` Step cho mỗi lần tăng và tối đa `O(VE)` lần tăng; trong trường hợp xấu phần **lịch sử** có thể chiếm tới `O(V^2E)` đối tượng Step. Chương trình minh họa cố tình lưu lịch sử để giải thích rõ cạnh ngược.

## 13. Độ phức tạp và cách chọn thuật toán thực tế

Đặt `V=|V|` và `E=|E|`, tính theo **cạnh vật lý** của đầu vào; mạng dư có **`2E` cung**, kể cả những cung có dung lượng dư bằng `0`.

| Công việc | Thời gian | Bộ nhớ |
|---|---|---|
| Validate và dựng mạng dư | `O(V+E)` | `O(V+E)` |
| Một BFS tìm đường tăng | `O(V+E)` | `O(V)` cho parent/queue |
| Một lần cập nhật đường | `O(V)` trong trường hợp xấu | `O(V)` nếu lưu Step của đường |
| Số lần tăng Edmonds–Karp | `O(VE)` | Phụ thuộc việc lưu lịch sử |
| Toàn bộ Edmonds–Karp | `O(VE^2)` | `O(V+E)` nếu không lưu lịch sử |
| Tạo min-cut cuối từ reachable | `O(V+E)` | `O(V+E)` kết quả/cấu trúc |
| Vét cạn min-cut để làm oracle | `O(2^V(V+E))` hoặc `O(2^VE)` theo cài đặt | `O(V+E)` |

Với `BigInteger`, mỗi phép cộng/trừ/so sánh có chi phí theo độ dài bit của capacity và tổng; công thức `O(VE^2)` ở đây đếm các thao tác mạng, không phải chi phí bit chính xác khi số nguyên tùy ý lớn.

### Những thuật toán có thể nhanh hơn

- **Dinic:** dùng BFS tạo level graph và tìm blocking flow; thường hiệu quả hơn Edmonds–Karp trên nhiều mạng. Giới hạn tổng quát phổ biến `O(V^2E)`, với những cải thiện trên các lớp mạng đặc biệt.
- **Push–relabel:** không nhất thiết gửi luồng theo toàn bộ đường tăng mỗi bước, mà duy trì preflow và chiều cao; có các bảo đảm đa thức và thường mạnh trên một số dạng mạng.
- **Edmonds–Karp:** dễ đọc, dễ chứng minh và phù hợp để học mạng dư/cạnh ngược hoặc làm bài quy mô vừa.

Dù dùng thuật toán nào, khái niệm **dung lượng dư và khả năng hoàn tác luồng** vẫn là nền tảng.

## 14. Kiểm thử độc lập bằng lát cắt vét cạn

Một bộ kiểm thử tốt không nên chỉ chạy Edmonds–Karp hai lần rồi so hai kết quả. Cả hai lần có thể mắc cùng một lỗi.

**Oracle độc lập:** với mạng có ít đỉnh, duyệt **mọi tập con `S\subset V`** thỏa `s\in S` và `t\notin S`, tính:

\[
capacity(S,V\setminus S)
=\sum_{u\in S,v\notin S}c(u,v).
\]

Lấy min trên tất cả tập `S`. Đây là **min-cut bằng định nghĩa**, không chạy BFS augment và không dùng cập nhật mạng dư.

Nhờ định lý max-flow/min-cut, kết quả min-cut vét cạn phải bằng giá trị max flow từ thuật toán.

### 14.1. Kiểm tra song song ba lớp

Với mỗi mạng thử:

1. **Giá trị:** `maxFlow==minCutOracle`.
2. **Luồng trên từng cạnh gốc:** mỗi `f_e` trong `[0,c_e]`.
3. **Bảo toàn:** với mỗi đỉnh trung gian, tổng vào bằng tổng ra; nguồn và đích mang luồng ròng `\pm maxFlow`.
4. **Chứng chỉ cut cuối:** `cutCapacity==maxFlow` và `sourceSide` chứa nguồn nhưng không chứa đích.
5. **Các đường tăng:** mỗi bước trên một cung dư dương ở thời điểm chọn; `\Delta` không lớn hơn bottleneck.
6. **Cạnh ngược:** nếu một bước có loại `R`, ID tương ứng phải là cạnh gốc có thể **giảm** luồng ở thời điểm đó.

Các kiểm tra đầu–cuối chưa đủ để phát hiện mọi lỗi nội bộ, nhưng tổ hợp **oracle vét cạn + bất biến luồng + lịch sử tăng** có sức bao phủ tốt trên các mạng nhỏ.

### 14.2. Test ngẫu nhiên có seed

Chương trình Java dùng `Random(328L)` để tạo **300 mạng có hướng** với:

- `n` từ `2` tới `7`.
- Số cạnh `m` từ `0` tới `14`.
- Dung lượng nguyên từ `0` tới `7`.
- Đầu mút được chọn độc lập, nên có thể sinh **cạnh song song, cạnh thật ngược chiều, khuyên và cạnh capacity 0**.
- Nguồn `0` và đích `n-1`.

Mỗi mạng được giải bằng Edmonds–Karp và được đối chiếu với **mọi lát cắt hợp lệ** bằng vét cạn. Mã cũng tự kiểm tra capacity/conservation/cut certificate trong `solve`.

**Kiểm thử ngẫu nhiên không thay thế chứng minh.** Nhưng một lỗi kiểu “gộp cạnh ngược với cạnh thật”, “không cập nhật reverse”, “chỉ kiểm tra cạnh gốc” hoặc “sai tổng cut” thường sẽ bộc lộ khi đối chiếu với oracle độc lập.

### 14.3. Các ca cố định nên thêm

```text
1. Mạng không có cạnh: maxFlow = 0.
2. Có cạnh nhưng không có đường từ s tới t: 0.
3. Một cạnh s->t capacity 5: maxFlow = 5.
4. Hai cạnh song song s->t capacity 2 và 3: maxFlow = 5.
5. Có cả u->v và v->u là hai cạnh gốc riêng.
6. Có khuyên u->u, không được nhầm với s-t flow.
7. Cạnh capacity 0.
8. Đường dài với bottleneck nhỏ.
9. Nhiều đường tranh chấp một cạnh.
10. Ví dụ phần 5: đường tăng thứ hai cần reverse để sửa lựa chọn đầu.
11. Ví dụ phần 6: BFS Edmonds-Karp thực sự dùng reverse.
12. Tổng max flow > Long.MAX_VALUE từ các cạnh hợp lệ.
13. Capacity âm: phải bị từ chối.
14. Chỉ số đỉnh ngoài miền: phải bị từ chối.
15. source == sink: xử lý theo hợp đồng API.
16. Nhiều min-cut cùng dung lượng: chấp nhận bất kỳ chứng chỉ đúng.
```

## 15. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Không tạo cạnh dư ngược | Không thể hoàn tác luồng cũ, có thể dừng trước tối ưu | Mỗi cạnh gốc tạo **cặp Arc thuận–ngược** |
| Coi cạnh ngược là cạnh thật đi chiều ngược | Hiểu sai nghiệm, có thể xuất đường không tồn tại trong đồ thị gốc | Phân biệt **bước cập nhật dư** và **cạnh vật lý** |
| Dùng cạnh gốc `v→u` làm reverse của cạnh `u→v` | Hai dung lượng độc lập bị liên kết sai | Cặp reverse riêng cho **mỗi ID cạnh gốc** |
| Gộp các cạnh song song vào một cờ boolean | Mất dung lượng và sai luồng trên từng cạnh | Giữ từng cạnh có ID riêng |
| Chỉ lưu đỉnh cha trong BFS | Không biết cung nào được chọn nếu có nhiều cung cùng đầu–cuối | Lưu **parentArc[v]** hoặc edge ID/chỉ số cụ thể |
| Chỉ cập nhật `forward.residual-=delta` | Mất khả năng hoàn tác ở tương lai | Đồng thời `reverse.residual+=delta` |
| Tăng nhiều hơn min residual trên đường | Dung lượng dư âm, vi phạm capacity | Dùng bottleneck `min` |
| Tăng luồng trên cung ngược như thể tăng luồng gốc theo cùng chiều | Luồng gốc có thể vượt ràng buộc hoặc sai bảo toàn | Đi ngược ⇒ **giảm** luồng của cạnh gốc |
| BFS qua cung dư `0` | Tạo đường giả, có thể vòng lặp vô hạn | Chỉ đi qua cung `residual>0` |
| Dừng vì đồ thị gốc hết đường chưa bão hòa | Bỏ sót đường dư có reverse | Tìm trong **toàn mạng dư** |
| Không đánh dấu đã thăm trong BFS | Có thể quay vòng, trùng cha và đường không đơn | Đánh dấu khi enqueue |
| Ghi `parentVertex[source]=-1` rồi cho BFS thăm lại nguồn | Có thể tạo chu trình trong đường parent | Đặt `parent[source]=source` |
| Không kiểm tra `source!=sink` | Có đường rỗng và bottleneck không xác định | API từ chối hoặc có quy ước riêng |
| Chấp nhận capacity âm | Residual/flow không có nghĩa chuẩn | Validate `capacity>=0` |
| Tính maxFlow bằng tổng luồng mọi cạnh | Đếm một đơn vị nhiều lần qua các đoạn | Dùng luồng ròng nguồn hoặc tổng `\Delta` |
| Quên cạnh đi vào nguồn khi tự tính net flow | Luồng giá trị có thể sai | `outflow(s)-inflow(s)` |
| Tính cut bằng các cung dư ngược | Không phải dung lượng lát cắt của đồ thị gốc | Chỉ cộng **capacity cạnh gốc S→T** |
| Tính cut cộng cả cạnh T→S | Báo cận trên sai | Chỉ lấy cạnh gốc từ `S` sang `T` |
| Quên xác minh conservation | Có thể trả một tập số không phải luồng hợp lệ | Kiểm tra tổng vào/ra tại mọi đỉnh |
| Dùng `long` cho tổng khi quá nhiều cạnh lớn | Tràn và trả giá trị cực đại sai | `BigInteger` hoặc kiểu/cận có chứng minh |
| Dùng `double` và kiểm tra `residual>0` tuyệt đối | Nhiễu số thực tạo dư ảo | Quy định epsilon/kỹ thuật số phù hợp |
| Nhầm BFS Edmonds–Karp với min-cost flow | Tối ưu sai mục tiêu | BFS tối ưu **số cung trên đường tăng**, không tối ưu chi phí |
| Tuyên bố không còn đường dư nhưng không xem cạnh ngược | Chứng minh dừng–tối ưu không hợp lệ | Dựa trên reachable trong **mạng dư đầy đủ** |
| Giữ toàn lịch sử đường tăng cho mạng khổng lồ | Tốn bộ nhớ lớn | Chỉ lưu lịch sử khi cần debug/minh họa |
| Dùng ngẫu nhiên mà không cố định seed | Khó tái hiện lỗi | In/giữ seed, danh sách cạnh và thứ tự input |

## 16. Câu hỏi tự luyện kèm đáp án

**Bài 1 — Dung lượng dư.** Cạnh gốc `u\to v` capacity `12` đang có flow `5`. Dư thuận và dư ngược là bao nhiêu?

*Đáp án:* dư thuận `12-5=7`, dư ngược `5`.

**Bài 2 — Hoàn tác.** Từ trạng thái trên, một đường dư đi `v\to u` với bottleneck `3`. Flow gốc và hai dư mới là gì?

*Đáp án:* flow gốc giảm từ `5` xuống `2`; dư thuận tăng từ `7` lên `10`; dư ngược giảm từ `5` xuống `2`.

**Bài 3 — Bottleneck.** Đường dư có các dung lượng `[8,2,6,9]`. Có thể tăng tối đa bao nhiêu một lần?

*Đáp án:* `2`; tăng `3` sẽ vượt dung lượng ở cung thứ hai.

**Bài 4 — Giá trị luồng.** Gửi `4` đơn vị theo một đường có `5` cạnh. Giá trị max flow đã tăng bao nhiêu?

*Đáp án:* tăng `4`, không phải `20`. Giá trị là lượng ròng qua nguồn/đích.

**Bài 5 — Tại sao cần cạnh ngược?** Với mạng `s\to a,s\to b,a\to b,a\to t,b\to t` mỗi capacity `1`, đã đi `s\to a\to b\to t`. Nêu đường tăng thứ hai.

*Đáp án:* `s\to b\to a\to t`, trong đó `b\to a` là cung dư ngược của cạnh gốc `a\to b`.

**Bài 6 — Tổng luồng sau hoàn tác.** Sau hai đường tăng ở bài 5, flow trên `a\to b` là bao nhiêu, và max flow bằng bao nhiêu?

*Đáp án:* flow `a\to b=0`; max flow `=2`. Luồng cuối phân rã thành `s\to a\to t` và `s\to b\to t`, mỗi đường một đơn vị.

**Bài 7 — Cạnh ngược thật.** Đầu vào có `u\to v` capacity `4` và `v\to u` capacity `6`. Tổng cộng cần tạo bao nhiêu đối tượng Arc dư với mô hình cặp riêng?

*Đáp án:* **4 Arc**: 2 thuận gốc + 2 reverse. Không dùng chung reverse với cạnh vật lý chiều đối diện.

**Bài 8 — BFS reverse.** Trong ví dụ sáu đỉnh, tại sao bước `2\to3` trong đường tăng thứ hai được gắn `R1`?

*Đáp án:* vì đó là cung dư ngược của cạnh gốc ID 1 `3\to2`. Nó giảm flow ID 1 từ `3` xuống `2`.

**Bài 9 — Kiểm tra bảo toàn.** Ở ví dụ phần 6, đỉnh `2` nhận `2` từ `3` và `1` từ `1`, rồi gửi `3` tới `5`. Có vi phạm bảo toàn không?

*Đáp án:* không; tổng vào `3` bằng tổng ra `3`. Giá trị `net[2]=0`.

**Bài 10 — Cận trên.** Nếu nguồn chỉ có hai cạnh ra capacity `3` và `1`, không có cạnh khác đi ra nguồn, max flow có thể lớn hơn `4` không?

*Đáp án:* không, lát cắt `S=\{s\}` có capacity `4`, nên mọi luồng `\le4`.

**Bài 11 — Min-cut.** Sau khi Edmonds–Karp dừng, tập `S` các đỉnh tới được trong mạng dư có những tính chất nào?

*Đáp án:* chứa nguồn, không chứa đích. Mọi cạnh gốc `S\to T` bão hòa, mọi cạnh gốc `T\to S` có flow `0`; do đó `maxFlow=c(S,T)`.

**Bài 12 — Capacity 0.** Một cạnh gốc có capacity `0` được đi trong đường tăng không?

*Đáp án:* không, vì dư thuận ban đầu `0` và không thể mang flow dương. Nó vẫn là cạnh đầu vào hợp lệ, có thể nằm trong danh sách cạnh cắt với đóng góp `0`.

**Bài 13 — BigInteger.** Hai cạnh song song `s\to t`, mỗi cạnh capacity `Long.MAX_VALUE`, max flow bằng bao nhiêu?

*Đáp án:* `18446744073709551614`. Không thể lưu bằng `long` có dấu.

**Bài 14 — Ford–Fulkerson và Edmonds–Karp.** Sự khác biệt cốt lõi về cách chọn đường tăng là gì?

*Đáp án:* Ford–Fulkerson cho phép chọn **bất kỳ đường dư** (ví dụ DFS), còn Edmonds–Karp dùng **BFS lấy đường ít cung nhất**. Cả hai phải dùng mạng dư đầy đủ và cập nhật reverse.

**Bài 15 — Đồ thị không nối s-t.** Nếu không có đường tăng nào từ lúc luồng ban đầu `0`, câu trả lời là gì?

*Đáp án:* max flow `0`; một lát cắt dung lượng `0` được xác nhận bằng tập tới được `S` trong mạng dư.

**Bài 16 — Chứng minh.** Giải thích tại sao “không có đường tăng” chứng minh được luồng cực đại, không chỉ cực đại địa phương.

*Đáp án:* lấy `S` là tập reachable từ nguồn qua cung dư dương. Mọi cạnh gốc `S\to T` bão hòa và mọi cạnh `T\to S` có flow `0`, do đó `|f|=c(S,T)`. Bất kỳ luồng khả thi nào cũng `\le c(S,T)`, nên `f` tối ưu toàn cục.

**Bài 17 — Oracle độc lập.** Với mạng tối đa `8` đỉnh, hãy vét cạn mọi tập `S` chứa nguồn, không chứa đích; cộng capacity các cạnh gốc từ `S` sang phần còn lại và lấy min. So với giá trị Edmonds–Karp.

*Đáp án mong đợi:* hai kết quả bằng nhau trên mọi mạng hợp lệ, kể cả cạnh song song, cạnh ngược chiều thật, khuyên, capacity `0` và mạng không tới được đích.

## 17. Checklist khi viết thuật toán luồng cực đại

1. Đầu vào là **mạng có hướng**? Mỗi cạnh có capacity `\ge0`?
2. Nguồn và đích có **hợp lệ, phân biệt** không?
3. Có **một cặp forward/reverse** cho **mỗi cạnh gốc**, kể cả cạnh song song và cạnh thật ngược chiều?
4. Các đối tượng Arc có tham chiếu reverse **đúng cặp** không, kể cả khuyên?
5. BFS/DFS tìm đường trong **mạng dư**, chỉ theo cung `residual>0`?
6. Có lưu **cung cha cụ thể**, không chỉ đỉnh cha, để cập nhật đúng cạnh?
7. Bottleneck có phải **min residual** dọc đường dư đã tìm?
8. Mỗi lần tăng có cập nhật **`arc.residual-=delta`** và **`arc.reverse.residual+=delta`**?
9. Có nhớ rằng đi cung reverse làm **giảm flow của cạnh gốc**, không tạo cạnh gốc mới?
10. Giá trị flow có cộng đúng `\Delta` một lần cho mỗi đường tăng?
11. Có kiểm tra luồng gốc `0\le f_e\le c_e` và bảo toàn ở đỉnh trung gian?
12. Khi không còn đường tăng, có tìm `S` reachable từ nguồn trên **mạng dư cuối**?
13. Có tính capacity min-cut chỉ từ **cạnh gốc `S\to T`**, không cộng cung dư hay cạnh `T\to S`?
14. Có xác minh **`maxFlow=cutCapacity`**?
15. Kiểu số có chịu nổi tổng capacity trên nhiều cạnh không? Có thể dùng `BigInteger`?
16. Nếu chỉ cần giá trị, có thể **không lưu lịch sử** để tiết kiệm bộ nhớ không?
17. Đã thử ca **reverse thật sự xuất hiện** và đối chiếu với **min-cut vét cạn** chưa?
18. Có phân biệt max flow với **min-cost flow** hoặc đường đi ngắn nhất theo trọng số không?

## Ghi nhớ

Với mỗi cạnh gốc `e=(u,v)`, dung lượng `c_e` và luồng `f_e`:

\[
\boxed{r(u\to v;\,e)=c_e-f_e,\qquad
r(v\to u;\,e)=f_e.}
\]

Một **đường tăng luồng** là đường `s\rightsquigarrow t` trong **mạng dư** gồm các cung có dư dương. Mức tăng:

\[
\boxed{\Delta=\min_{a\text{ trên đường}}r(a).}
\]

Cho mỗi cung của đường: **trừ `\Delta` ở cung được đi, cộng `\Delta` ở cung reverse tương ứng**. Đi cung reverse có nghĩa **hoàn tác một phần luồng gốc**, giúp định tuyến lại và không bị mắc kẹt vì lựa chọn đường trước đó.

Edmonds–Karp dùng **BFS** để chọn đường tăng theo số cung, có giới hạn thời gian chuẩn **`O(VE^2)`**. Khi không còn đường tăng, tập đỉnh còn tới được từ nguồn trong mạng dư xác định một lát cắt `(S,T)` với:

\[
\boxed{|f|=c(S,T).}
\]

Theo định lý **max-flow/min-cut**, đó là chứng chỉ luồng đã **cực đại toàn cục**. Bốn ý cần nắm vững: **dư thuận = phần có thể tăng; dư ngược = phần có thể rút lại; bottleneck = mức tăng an toàn; không còn đường dư = tối ưu.**
