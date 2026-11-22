# Khoảng cách và tổng trọng số trên đường đi trong cây

## 1. Bài toán và điều cần phân biệt ngay từ đầu

Cho một **cây vô hướng có trọng số** gồm `n` đỉnh, mỗi cạnh `e` có trọng số `w(e)`. Có nhiều truy vấn, mỗi truy vấn cho hai đỉnh `u,v` và yêu cầu:

1. **Khoảng cách theo số cạnh** trên đường đi từ `u` tới `v`.
2. **Tổng trọng số các cạnh** trên đường đi đó.
3. Khi cần, **liệt kê các đỉnh** theo đúng thứ tự trên đường.
4. Nếu bài toán có gốc, có thể cần biết **tổ tiên chung gần nhất** (Lowest Common Ancestor, **LCA**) của `u` và `v`.

Trong một **cây**, giữa hai đỉnh bất kỳ có **đúng một đường đi đơn**. Nhờ tính duy nhất ấy, ta không phải “chọn đường tốt nhất” trong nhiều đường như khi giải Dijkstra/Floyd–Warshall trên đồ thị tổng quát. Bài toán chủ yếu là tìm đường duy nhất và tính các đại lượng trên nó thật nhanh.

Ví dụ cây sau:

```text
            0
         4 / \ 2
          1   2
        7/ \-3 / \1
        3   4 5   6
             / \
           0/   \9
           7     8

Danh sách cạnh chính xác:
0--1 (4)      0--2 (2)
1--3 (7)      1--4 (-3)
2--5 (5)      2--6 (1)
5--7 (0)      5--8 (9)

Số đỉnh: 9; số cạnh: 8.
```

Đường đơn từ `3` tới `8`:

```text
3 -> 1 -> 0 -> 2 -> 5 -> 8

Số cạnh = 5
Tổng trọng số = 7 + 4 + 2 + 5 + 9 = 27
```

Đường từ `3` tới `4`:

```text
3 -> 1 -> 4

Số cạnh = 2
Tổng trọng số = 7 + (-3) = 4
```

**Khoảng cách theo số cạnh không giống tổng trọng số.** Trọng số âm hoặc bằng `0` càng làm rõ sự khác biệt: đường có nhiều cạnh hơn có thể có tổng trọng số nhỏ hơn.

Bài học sẽ đi từ cách giải một truy vấn bằng DFS/BFS tới tiền xử lý **độ sâu + tổng trọng số từ gốc + LCA bằng binary lifting**, cho truy vấn `O(\log n)` thay vì phải đi dọc từng đường mỗi lần. Nội dung gồm chứng minh công thức, xử lý trọng số rất lớn, mã **Java 17** chạy độc lập, kết quả chuẩn, kiểm thử đối chứng và các biến thể quan trọng.

## 2. Hợp đồng dữ liệu và định nghĩa cây

### 2.1. Cây vô hướng là gì?

Một cây vô hướng `T=(V,E)` là đồ thị **liên thông** và **không có chu trình**. Với `n\ge1`:

\[
|E|=n-1.
\]

Các điều kiện sau tương đương với việc đồ thị là cây:

- Liên thông và không chu trình.
- Liên thông và có `n-1` cạnh.
- Không chu trình và có `n-1` cạnh.

Mỗi cặp đỉnh có đúng một đường đi đơn. Nếu có hai đường đơn khác nhau nối `u,v`, hợp của chúng chứa một chu trình, trái với định nghĩa cây. Nếu thiếu đường đi thì đồ thị không liên thông. Đây là cơ sở của mọi công thức khoảng cách trong bài.

Cây với `n=1` không có cạnh; đường từ đỉnh `0` tới chính nó chỉ gồm `[0]`, số cạnh và tổng trọng số đều bằng `0`.

### 2.2. Cạnh có trọng số

Một cạnh vô hướng `\{u,v\}` trọng số `w` được đi qua theo cả hai chiều. Mỗi cạnh xuất hiện một lần trong danh sách cạnh vật lý, còn trong **danh sách kề** thường thêm hai mục:

```text
adj[u].add((v, w))
adj[v].add((u, w))
```

Nếu mỗi cạnh có trọng số `long`, tổng nhiều cạnh có thể vượt phạm vi `long`. Chương trình Java trong bài dùng **`BigInteger`** để lưu **prefix sum** và kết quả tổng đường, còn trọng số riêng từng cạnh là `long`.

Trọng số có thể:

- Dương: độ dài, thời gian hoặc chi phí không âm theo nhiều ngữ cảnh.
- Bằng `0`.
- Âm: lợi ích/chi phí có dấu trong mô hình **tổng trên đường đơn duy nhất**.

**Lưu ý toán học:** với trọng số âm, “tổng trọng số trên đường đơn duy nhất” vẫn được định nghĩa rõ ràng. Nhưng nếu đề hỏi “walk có tổng nhỏ nhất” và cho phép đi qua cùng cạnh vô hướng nhiều lần, một cạnh âm có thể bị đi qua rồi quay lại mãi, làm tổng giảm không giới hạn. Khi ấy không được tự đồng nhất bài toán ấy với tổng đường đơn trên cây.

### 2.3. Phải kiểm tra thật sự là cây

Chỉ thấy `m=n-1` chưa đủ nếu đồ thị có thể không liên thông hoặc có chu trình. Ví dụ `n=4,m=3` với ba cạnh tạo thành tam giác ở `\{0,1,2\}` và đỉnh `3` cô lập: đủ `n-1` cạnh nhưng **không phải cây**.

Vì vậy, cài đặt mẫu kiểm tra:

1. `n\ge1` và gốc `root` hợp lệ.
2. Có đúng `n-1` cạnh.
3. Mọi đầu mút cạnh nằm trong `0..n-1`.
4. Dùng **DSU (Disjoint Set Union)**, chỉ nối hai thành phần khác nhau. Nếu `union(u,v)` trả false, cạnh vừa xét tạo chu trình ⇒ đầu vào sai.
5. Sau khi xử lý, DSU phải có đúng **một thành phần**.

Điều này cũng tự loại **khuyên** `u--u` và **cạnh song song** tạo chu trình hai cạnh. Nếu đầu vào là một **rừng** thay vì một cây, cần thiết kế truy vấn theo thành phần; không thể hỏi LCA giữa hai đỉnh khác thành phần.

## 3. Cách đơn giản nhất: DFS hoặc BFS cho từng truy vấn

Nếu số truy vấn ít, ta có thể tìm đường từ `u` tới `v` bằng DFS/BFS ngay tại lúc truy vấn.

Ý tưởng:

```text
query(u, v):
    chạy DFS/BFS từ u
    lưu parent[x] và trọng số cạnh đưa ta tới x
    tìm tới v
    đi ngược parent từ v về u để lấy đường
    đếm số cạnh và cộng các trọng số
```

Trong cây liên thông, vì đường đơn là duy nhất nên DFS và BFS đều tìm đúng **cùng một chuỗi đỉnh**, chỉ có thứ tự khám phá các nhánh không liên quan có thể khác.

**Độ phức tạp:** mỗi truy vấn tốn `O(n)` thời gian trong trường hợp xấu, vì cây có `n-1` cạnh. Bộ nhớ cho `visited/parent/queue` là `O(n)`. Với `q` truy vấn, tổng có thể là `O(qn)`.

Ví dụ `n=200\,000` và `q=200\,000`, không nên duyệt toàn cây cho từng truy vấn. Ta cần tiền xử lý để trả lời nhanh hơn.

### 3.1. Khi chỉ cần in đường

Đường có thể dài tới `n-1` cạnh. Dù dùng LCA, nếu đề yêu cầu **in toàn bộ các đỉnh của đường**, việc tạo/in kết quả vẫn tốn ít nhất:

\[
\Omega(\text{số đỉnh trên đường}).
\]

Không thể tuyên bố in một đường dài `n` đỉnh trong `O(\log n)` chỉ vì LCA được tính trong `O(\log n)`. Phải phân biệt **truy vấn một giá trị tổng** với **xuất toàn bộ đường**.

## 4. Gốc hóa cây và ba mảng nền tảng

Chọn một đỉnh bất kỳ làm **gốc** (ví dụ `root=0`), biến cây vô hướng thành cây có cha–con chỉ để phục vụ thuật toán. Thay gốc làm thay các quan hệ cha và LCA, nhưng **không thay** đường đơn thật, số cạnh hay tổng trọng số giữa hai đỉnh.

Ta tính:

- `parent[u]`: cha trực tiếp của `u`; quy ước `parent[root]=root`.
- `depth[u]`: **số cạnh** từ gốc tới `u`; `depth[root]=0`.
- `prefix[u]`: **tổng trọng số cạnh** trên đường đơn từ gốc tới `u`; `prefix[root]=0`.

Nếu `v` là con của `u` qua cạnh có trọng số `w`:

\[
parent[v]=u,
\]

\[
depth[v]=depth[u]+1,
\]

\[
prefix[v]=prefix[u]+w.
\]

Các phép tính này có thể hoàn thành bằng một lượt DFS/BFS `O(n)`, vì mỗi cạnh của cây được dùng đúng một lần để phát hiện đỉnh con.

### 4.1. Bảng ví dụ với gốc 0

Với cây ở phần 1:

| Đỉnh | Cha | `depth` | `prefix` |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 1 | 0 | 1 | 4 |
| 2 | 0 | 1 | 2 |
| 3 | 1 | 2 | 11 |
| 4 | 1 | 2 | 1 |
| 5 | 2 | 2 | 7 |
| 6 | 2 | 2 | 3 |
| 7 | 5 | 3 | 7 |
| 8 | 5 | 3 | 16 |

Kiểm tra:

- `prefix[3]=4+7=11`.
- `prefix[4]=4+(-3)=1`.
- `prefix[7]=2+5+0=7`.
- `prefix[8]=2+5+9=16`.

Đặc biệt `prefix[4]=1` **nhỏ hơn** `prefix[1]=4` vì cạnh `1--4` có trọng số `-3`. Điều này hoàn toàn hợp lệ; không được giả định prefix luôn tăng khi đi xuống.

### 4.2. Bất biến khi duyệt

Khi một đỉnh `u` được lấy khỏi BFS queue:

1. `parent[u]` đã chỉ đúng đỉnh đứng trước `u` trên đường từ gốc (gốc trỏ tới chính nó).
2. `depth[u]` đúng bằng số cạnh của đường gốc–`u`.
3. `prefix[u]` đúng bằng tổng trọng số cạnh của đường gốc–`u`.
4. Đỉnh `u` đã được phát hiện đúng một lần.

Vì cây không chu trình, khi đi từ `u` sang hàng xóm `v` chưa phát hiện, cạnh `u--v` nhất thiết là cạnh trên đường duy nhất từ gốc tới `v`. Các công thức ở trên giữ nguyên bất biến.

## 5. LCA: tổ tiên chung gần nhất

**LCA(u,v)** là đỉnh **sâu nhất** đồng thời là tổ tiên của `u` và `v` trong cây đã gốc hóa.

Ví dụ trong cây mẫu gốc `0`:

```text
LCA(3, 4) = 1
LCA(7, 8) = 5
LCA(3, 8) = 0
LCA(4, 6) = 0
LCA(2, 2) = 2
```

Nếu `u` là tổ tiên của `v` thì `LCA(u,v)=u`. Nếu `u=v` thì `LCA(u,u)=u`.

### 5.1. Tại sao LCA là điểm chia đường?

Đặt:

\[
a=LCA(u,v).
\]

Đường đơn từ `u` tới `v` đi:

1. Từ `u` **đi ngược lên** các cha cho tới `a`.
2. Từ `a` **đi xuống** các con cho tới `v`.

Hai nhánh này không có cạnh chung và chỉ gặp nhau tại `a`. Nếu đường từ `u` lên `v` không đi qua `a`, nó sẽ đi qua một tổ tiên chung khác sâu hơn `a`, trái với định nghĩa LCA.

Vì vậy:

\[
path(u,v)=path(u,a)\ \cup\ path(a,v),
\]

với điểm `a` chỉ được ghi **một lần** khi xuất dãy đỉnh.

## 6. Công thức khoảng cách theo số cạnh

Với `a=LCA(u,v)`:

- Đường từ `u` lên `a` có `depth[u]-depth[a]` cạnh.
- Đường từ `a` xuống `v` có `depth[v]-depth[a]` cạnh.

Cộng hai đoạn:

\[
\boxed{
edgeDistance(u,v)
=depth[u]+depth[v]-2\,depth[LCA(u,v)].
}
\]

Đây là **số cạnh** trên đường đơn. Nếu mọi cạnh có độ dài `1`, nó cũng chính là tổng độ dài.

Ví dụ:

\[
edgeDistance(3,8)
=2+3-2\cdot0=5.
\]

\[
edgeDistance(3,4)
=2+2-2\cdot1=2.
\]

\[
edgeDistance(7,8)
=3+3-2\cdot2=2.
\]

\[
edgeDistance(u,u)=0.
\]

**Chú ý:** `depth` luôn đo bằng **số cạnh**, không phải tổng trọng số. Không được tự gán `depth[child]=depth[parent]+weight` rồi áp dụng công thức tìm số cạnh, vì điều đó biến `depth` thành một đại lượng khác.

### 6.1. Tại sao nên trả kiểu long cho số cạnh?

Mỗi đường đơn trong cây có nhiều nhất `n-1` cạnh, nên với `n` kiểu `int`, kết quả cuối nằm trong phạm vi `int`. Tuy nhiên, biểu thức trung gian `depth[u]+depth[v]` nếu thực hiện bằng `int` có thể tràn trong các giới hạn cực lớn.

Ví dụ Java dùng:

```java
long count = (long) depth[u] + depth[v]
    - 2L * depth[lca];
```

Việc ép sang `long` trước khi cộng bảo vệ biểu thức trung gian và làm rõ ý nghĩa kiểu dữ liệu.

## 7. Công thức tổng trọng số trên đường

Vẫn đặt `a=LCA(u,v)`. Vì:

\[
prefix[u]
=prefix[a]+weight(path(a,u)),
\]

nên:

\[
weight(path(u,a))=prefix[u]-prefix[a].
\]

Tương tự:

\[
weight(path(a,v))=prefix[v]-prefix[a].
\]

Cộng hai đoạn:

\[
\boxed{
pathSum(u,v)
=prefix[u]+prefix[v]-2\,prefix[LCA(u,v)].
}
\]

Công thức này hoàn toàn tương tự công thức số cạnh, nhưng dùng **prefix trọng số** thay cho depth.

### 7.1. Ví dụ có trọng số âm

Tính đường `3\to4`:

- `prefix[3]=11`.
- `prefix[4]=1`.
- `LCA(3,4)=1`, `prefix[1]=4`.

Vậy:

\[
pathSum(3,4)=11+1-2\cdot4=4.
\]

Kiểm tra trực tiếp: `3\to1` nặng `7`; `1\to4` nặng `-3`. Tổng `7-3=4`.

### 7.2. Ví dụ qua gốc

Tính đường `3\to8`:

- `prefix[3]=11`.
- `prefix[8]=16`.
- `LCA(3,8)=0`, `prefix[0]=0`.

\[
pathSum(3,8)=11+16-2\cdot0=27.
\]

Đường là `3\to1\to0\to2\to5\to8`, có các trọng số `7,4,2,5,9`, tổng `27`.

### 7.3. Ví dụ không qua gốc

Tính `7\to8`:

- `prefix[7]=7`.
- `prefix[8]=16`.
- `LCA(7,8)=5`, `prefix[5]=7`.

\[
pathSum(7,8)=7+16-2\cdot7=9.
\]

Đường `7\to5\to8` có trọng số `0+9=9`. **Nếu chỉ cộng `prefix[7]+prefix[8]` sẽ đếm phần gốc–`5` hai lần**, cho kết quả sai `23`. Phải trừ hai lần prefix của LCA.

### 7.4. Trường hợp cùng đỉnh

\[
pathSum(u,u)=prefix[u]+prefix[u]-2prefix[u]=0.
\]

Đây là **tổng trọng số cạnh trên đường rỗng**. Nếu bài hỏi tổng **giá trị đỉnh** trên đường và tính cả đỉnh `u`, kết quả cho `(u,u)` phải bằng giá trị của chính đỉnh ấy, không phải `0`. Phần 13 sẽ nêu công thức riêng.

## 8. Binary lifting: tìm LCA trong O(log n)

Nếu mỗi truy vấn đều đi ngược `parent` tới gốc, một cây dạng dây `0-1-2-\cdots-(n-1)` có thể khiến truy vấn tốn `O(n)`.

**Binary lifting (nhảy tổ tiên theo lũy thừa hai)** lưu:

\[
up[k][u]=\text{tổ tiên cách }u\text{ đúng }2^k\text{ cạnh}.
\]

Gốc được quy ước là **cha của chính nó** để việc nâng vượt gốc không truy cập `-1`. Vì vậy `up[k][root]=root`.

### 8.1. Tiền xử lý bảng up

Cơ sở:

\[
up[0][u]=parent[u].
\]

Bước quy nạp:

\[
\boxed{
up[k][u]
=up[k-1][\,up[k-1][u]\,].
}
\]

Tức đi lên `2^{k-1}` bước hai lần liên tiếp thì bằng đi lên `2^k` bước.

Chọn `LOG` sao cho `2^{LOG-1}\le n<2^{LOG}` (với `n=1` vẫn cần ít nhất một mức). Bảng có `LOG` hàng và `n` cột.

Ví dụ trong cây mẫu:

```text
parent[8] = 5     => up[0][8] = 5
parent[5] = 2     => up[1][8] = 2  (đi lên 2 cạnh)
parent[2] = 0     => đi lên 3 cạnh tới gốc 0
```

### 8.2. Nâng đỉnh sâu hơn

Giả sử `depth[u]>depth[v]`. Trước hết nâng `u` lên:

\[
\Delta=depth[u]-depth[v].
\]

Phân tích `\Delta` thành tổng các lũy thừa hai, rồi nhảy theo các bit bật. Ví dụ `\Delta=13=8+4+1` chỉ cần ba bước nhảy, không phải mười ba lần đi lên từng cha.

Sau khi nâng, hai đỉnh có cùng độ sâu.

### 8.3. Tìm điểm phân nhánh

- Nếu hai đỉnh sau nâng **trùng nhau**, đỉnh đó là LCA.
- Nếu khác nhau, xét `k` từ lớn xuống nhỏ.
- Nếu `up[k][u]\ne up[k][v]`, cả hai vẫn ở hai nhánh khác nhau khi đi lên `2^k` bước; ta có thể nâng cả hai mà **chưa nhảy vượt LCA**.
- Kết thúc, `u` và `v` là hai con ở hai nhánh bên dưới LCA; đáp án là `up[0][u]`.

Pseudocode:

```text
lca(u, v):
    if depth[u] < depth[v]:
        swap(u, v)

    u = raise(u, depth[u] - depth[v])

    if u == v:
        return u

    for k = LOG-1 down to 0:
        if up[k][u] != up[k][v]:
            u = up[k][u]
            v = up[k][v]

    return up[0][u]
```

Mỗi truy vấn xét tối đa `O(\log n)` mức. Sau khi có LCA, hai công thức số cạnh và tổng trọng số chỉ còn các phép toán số học hằng số (hoặc chi phí theo độ dài bit nếu dùng `BigInteger`).

## 9. Chứng minh tính đúng của LCA bằng binary lifting

### 9.1. Bất biến bảng up

Ta chứng minh bằng quy nạp theo `k`:

- `k=0`: `up[0][u]=parent[u]` là tổ tiên đúng một bước.
- Giả sử `up[k-1][u]` là tổ tiên sau `2^{k-1}` bước (hoặc gốc nếu đã lên hết).
- Từ `up[k-1][u]` đi thêm `2^{k-1}` bước được tổ tiên sau tổng `2^k` bước, đúng bằng `up[k][u]`.

Do đó bảng nhảy tổ tiên chính xác.

### 9.2. Bất biến nâng cùng độ sâu

Giả sử `u` sâu hơn `v`. LCA ban đầu của hai đỉnh nằm ở độ sâu **không lớn hơn** `depth[v]`. Nâng `u` lên đúng hiệu độ sâu không vượt LCA: nếu `v` là tổ tiên thì kết thúc đúng ở `v`, còn nếu không, `u` vẫn ở trong nhánh riêng bên dưới LCA.

Vì thế nâng cùng độ sâu **không thay** LCA cần tìm.

### 9.3. Bất biến khi nhảy từ k lớn xuống nhỏ

Sau khi hai đỉnh có cùng độ sâu và chưa trùng nhau, chúng thuộc hai nhánh khác nhau phía dưới LCA.

Nếu `up[k][u]\ne up[k][v]`, hai tổ tiên sau `2^k` bước vẫn khác nhau. Vì mọi tổ tiên ở **phía trên LCA** phải chung nhau, hai đỉnh ấy chưa đạt tới LCA. Ta có thể nâng cả hai lên đúng `2^k` bước mà không vượt LCA.

Nếu hai tổ tiên bằng nhau, nhảy mức ấy có thể đưa cả hai tới LCA hoặc vượt lên trên nó; thuật toán **không nhảy**.

Sau khi duyệt hết mức, hai đỉnh khác nhau nhưng cha trực tiếp của chúng bằng nhau. Cha đó chính là **tổ tiên chung gần nhất**.

### 9.4. Tổng đường đi đúng theo LCA

Mọi đường đơn `u\rightsquigarrow v` chia thành hai đoạn không trùng cạnh `u\rightsquigarrow LCA` và `LCA\rightsquigarrow v`. Hiệu prefix của mỗi đoạn tính đúng tổng trọng số, vì prefix đo tổng từ gốc trên cùng cây.

Cộng hai hiệu prefix nhận:

\[
prefix[u]-prefix[a]+prefix[v]-prefix[a]
=prefix[u]+prefix[v]-2prefix[a].
\]

Đây là chứng minh hoàn chỉnh công thức tổng đường; không dựa vào việc các trọng số không âm.

## 10. Ví dụ đầy đủ: tính nhiều loại truy vấn trên một cây

Với cây 9 đỉnh ở phần 1, gốc `0`:

| Truy vấn `u,v` | LCA | Số cạnh | Tổng trọng số | Đường đỉnh |
|---|---:|---:|---:|---|
| `(3,4)` | 1 | 2 | 4 | `3→1→4` |
| `(3,8)` | 0 | 5 | 27 | `3→1→0→2→5→8` |
| `(7,8)` | 5 | 2 | 9 | `7→5→8` |
| `(4,6)` | 0 | 4 | 4 | `4→1→0→2→6` |
| `(2,2)` | 2 | 0 | 0 | `2` |
| `(0,8)` | 0 | 3 | 16 | `0→2→5→8` |

Giải thích thêm hàng `(4,6)`:

```text
4 -> 1 -> 0 -> 2 -> 6
Trọng số: -3, 4, 2, 1
Số cạnh: 4
Tổng: -3+4+2+1=4
```

Dù tổng bằng `4`, số cạnh là `4` chỉ tình cờ bằng nhau. Với hàng `(3,8)` thì số cạnh `5` nhưng tổng `27`.

### Gốc thay đổi thì sao?

Nếu chọn gốc `5` thay vì `0`:

- `parent`, `depth`, `prefix`, `LCA` đều có thể khác.
- Nhưng **đường `3\rightsquigarrow8`**, số cạnh **5** và tổng **27** vẫn y nguyên.
- Công thức `prefix[u]+prefix[v]-2prefix[LCA]` vẫn đúng vì cả ba prefix được tính **nhất quán từ cùng gốc mới**.

Không được ghép `prefix` tính từ gốc `0` với LCA được tìm từ gốc `5`: các thành phần không còn cùng hệ quy chiếu.

## 11. Java 17+ hoàn chỉnh: LCA, số cạnh, tổng trọng số và đường cụ thể

Chương trình sau dùng **BFS lặp** để gốc hóa cây, tránh đệ quy sâu và `StackOverflowError` trên cây dạng dây. Nó xây **bảng nhảy tổ tiên**, trả kết quả truy vấn trong `O(\log n)`, và có hàm riêng trả chuỗi đỉnh của đường trong `O(\text{độ dài đường})`.

Hợp đồng:

- `n\ge1`; đỉnh đánh số từ `0` đến `n-1`.
- Danh sách cạnh có đúng `n-1` phần tử và tạo **một cây vô hướng hợp lệ**.
- Cạnh có trọng số kiểu `long`, có thể âm, bằng không hoặc rất lớn.
- `root` là đỉnh hợp lệ.
- Truy vấn `(u,v)` phải nằm trong `0..n-1`.
- Tổng trọng số dùng `BigInteger`, không tràn khi cộng nhiều cạnh.
- `Query` trả `lca`, `edgeCount` (kiểu `long`) và `weightSum`.
- Hàm `pathVertices` là tùy chọn; giá phải trả để xuất đường tỉ lệ với số đỉnh xuất ra.

Lưu toàn bộ chương trình trong tệp **`TreePathQueriesDemo.java`**:

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

public final class TreePathQueriesDemo {
    private TreePathQueriesDemo() {
    }

    public record Edge(int u, int v, long weight) {
    }

    private record Arc(int to, long weight) {
    }

    public record Query(
            int lca,
            long edgeCount,
            BigInteger weightSum) {
    }

    // Kiểm tra dữ liệu là một cây, không phải đồ thị bất kỳ.
    private static final class DSU {
        final int[] parent;
        final int[] size;
        int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            Arrays.fill(size, 1);
            for (int i = 0; i < n; i++) {
                parent[i] = i;
            }
        }

        int find(int x) {
            if (parent[x] != x) {
                parent[x] = find(parent[x]);
            }
            return parent[x];
        }

        boolean union(int a, int b) {
            int x = find(a);
            int y = find(b);
            if (x == y) {
                return false;
            }
            if (size[x] < size[y]) {
                int tmp = x;
                x = y;
                y = tmp;
            }
            parent[y] = x;
            size[x] += size[y];
            components--;
            return true;
        }
    }

    public static final class TreeIndex {
        private final int n;
        private final int log;
        private final int[] depth;
        private final int[][] up;
        private final BigInteger[] prefix;

        public TreeIndex(int n, List<Edge> edges, int root) {
            Objects.requireNonNull(edges, "edges");
            if (n < 1 || root < 0 || root >= n) {
                throw new IllegalArgumentException(
                    "n must be positive and root must exist"
                );
            }
            if (edges.size() != n - 1) {
                throw new IllegalArgumentException(
                    "a tree requires exactly n-1 edges"
                );
            }

            List<List<Arc>> adj = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                adj.add(new ArrayList<>());
            }

            DSU dsu = new DSU(n);
            for (Edge e : edges) {
                Objects.requireNonNull(e, "edge");
                int u = e.u(), v = e.v();

                if (u < 0 || u >= n || v < 0 || v >= n) {
                    throw new IllegalArgumentException(
                        "edge endpoint out of range"
                    );
                }
                if (!dsu.union(u, v)) {
                    throw new IllegalArgumentException(
                        "cycle or parallel edge in input"
                    );
                }

                adj.get(u).add(new Arc(v, e.weight()));
                adj.get(v).add(new Arc(u, e.weight()));
            }
            if (dsu.components != 1) {
                throw new IllegalArgumentException(
                    "input is disconnected"
                );
            }

            this.n = n;
            int levels = 1;
            while ((1L << levels) <= n) {
                levels++;
            }
            this.log = levels;

            depth = new int[n];
            Arrays.fill(depth, -1);
            up = new int[log][n];
            prefix = new BigInteger[n];

            Deque<Integer> queue = new ArrayDeque<>();
            queue.addLast(root);
            depth[root] = 0;
            up[0][root] = root;
            prefix[root] = BigInteger.ZERO;

            // Không dùng đệ quy: tránh lỗi stack trên cây sâu.
            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Arc arc : adj.get(u)) {
                    int v = arc.to();
                    if (depth[v] != -1) {
                        continue;
                    }
                    depth[v] = depth[u] + 1;
                    up[0][v] = u;
                    prefix[v] = prefix[u].add(
                        BigInteger.valueOf(arc.weight())
                    );
                    queue.addLast(v);
                }
            }

            for (int k = 1; k < log; k++) {
                for (int u = 0; u < n; u++) {
                    up[k][u] =
                        up[k - 1][up[k - 1][u]];
                }
            }
        }

        private void checkVertex(int u) {
            if (u < 0 || u >= n) {
                throw new IllegalArgumentException(
                    "query vertex out of range"
                );
            }
        }

        // Nâng u lên 'steps' cạnh qua các bit.
        private int raise(int u, int steps) {
            int bit = 0;
            while (steps != 0) {
                if ((steps & 1) != 0) {
                    u = up[bit][u];
                }
                steps >>>= 1;
                bit++;
            }
            return u;
        }

        public int lca(int u, int v) {
            checkVertex(u);
            checkVertex(v);

            if (depth[u] < depth[v]) {
                int tmp = u;
                u = v;
                v = tmp;
            }

            u = raise(u, depth[u] - depth[v]);
            if (u == v) {
                return u;
            }

            for (int k = log - 1; k >= 0; k--) {
                if (up[k][u] != up[k][v]) {
                    u = up[k][u];
                    v = up[k][v];
                }
            }
            return up[0][u];
        }

        public Query query(int u, int v) {
            int a = lca(u, v);

            long edgesOnPath =
                (long) depth[u] + depth[v]
                - 2L * depth[a];

            BigInteger total = prefix[u]
                .add(prefix[v])
                .subtract(prefix[a].shiftLeft(1));

            return new Query(a, edgesOnPath, total);
        }

        // Chi phí O(số đỉnh trên đường): dùng khi cần in đường.
        public List<Integer> pathVertices(int u, int v) {
            int a = lca(u, v);
            List<Integer> left = new ArrayList<>();
            List<Integer> right = new ArrayList<>();

            for (int x = u; x != a; x = up[0][x]) {
                left.add(x);
            }
            left.add(a);

            for (int x = v; x != a; x = up[0][x]) {
                right.add(x);
            }
            Collections.reverse(right);
            left.addAll(right);
            return List.copyOf(left);
        }
    }

    // Oracle độc lập: BFS để dựng đường thật từ s tới t.
    // Chỉ dùng cho kiểm thử, không tận dụng up[]/prefix[].
    private static List<Integer> bfsPath(
            int n, List<Edge> edges, int s, int t) {
        List<List<Integer>> adj = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            adj.add(new ArrayList<>());
        }
        for (Edge e : edges) {
            adj.get(e.u()).add(e.v());
            adj.get(e.v()).add(e.u());
        }

        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        Deque<Integer> queue = new ArrayDeque<>();
        queue.addLast(s);
        parent[s] = s;

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : adj.get(u)) {
                if (parent[v] == -1) {
                    parent[v] = u;
                    queue.addLast(v);
                }
            }
        }

        if (parent[t] == -1) {
            throw new AssertionError(
                "disconnected input in BFS oracle"
            );
        }

        List<Integer> path = new ArrayList<>();
        for (int x = t; x != s; x = parent[x]) {
            path.add(x);
        }
        path.add(s);
        Collections.reverse(path);
        return List.copyOf(path);
    }

    // Tổng theo một đường BFS: tìm cạnh thật giữa từng cặp.
    private static BigInteger bfsPathWeight(
            List<Edge> edges, List<Integer> path) {
        BigInteger total = BigInteger.ZERO;
        for (int i = 1; i < path.size(); i++) {
            int a = path.get(i - 1);
            int b = path.get(i);
            boolean found = false;

            for (Edge e : edges) {
                if ((e.u() == a && e.v() == b)
                        || (e.u() == b && e.v() == a)) {
                    total = total.add(
                        BigInteger.valueOf(e.weight())
                    );
                    found = true;
                    break;
                }
            }
            if (!found) {
                throw new AssertionError(
                    "BFS path uses a missing edge"
                );
            }
        }
        return total;
    }

    // Oracle LCA độc lập: lấy hai đường root->u, root->v.
    private static int naiveLca(
            int n, List<Edge> edges, int root,
            int u, int v) {
        List<Integer> ru = bfsPath(n, edges, root, u);
        List<Integer> rv = bfsPath(n, edges, root, v);
        int answer = root;

        for (int i = 0;
                i < Math.min(ru.size(), rv.size()); i++) {
            if (!ru.get(i).equals(rv.get(i))) {
                break;
            }
            answer = ru.get(i);
        }
        return answer;
    }

    private static void show(
            String label, TreeIndex index,
            int u, int v) {
        Query q = index.query(u, v);
        System.out.println(
            label + ": lca=" + q.lca()
            + " edges=" + q.edgeCount()
            + " weight=" + q.weightSum()
            + " path=" + index.pathVertices(u, v)
        );
    }

    public static void main(String[] args) {
        List<Edge> example = List.of(
            new Edge(0, 1, 4),
            new Edge(0, 2, 2),
            new Edge(1, 3, 7),
            new Edge(1, 4, -3),
            new Edge(2, 5, 5),
            new Edge(2, 6, 1),
            new Edge(5, 7, 0),
            new Edge(5, 8, 9)
        );

        TreeIndex index = new TreeIndex(9, example, 0);
        show("Main 3->4", index, 3, 4);
        show("Main 3->8", index, 3, 8);
        show("Main 7->8", index, 7, 8);
        show("Main 4->6", index, 4, 6);
        show("Main 2->2", index, 2, 2);
        show("Main 0->8", index, 0, 8);

        TreeIndex single =
            new TreeIndex(1, List.of(), 0);
        show("Single 0->0", single, 0, 0);

        List<Edge> huge = List.of(
            new Edge(0, 1, Long.MAX_VALUE),
            new Edge(1, 2, Long.MAX_VALUE)
        );
        TreeIndex large = new TreeIndex(3, huge, 0);
        show("Long.MAX_VALUE twice", large, 0, 2);

        List<Edge> negativeExtreme = List.of(
            new Edge(0, 1, Long.MIN_VALUE),
            new Edge(1, 2, -5)
        );
        TreeIndex neg =
            new TreeIndex(3, negativeExtreme, 0);
        show("Long.MIN_VALUE plus -5", neg, 0, 2);

        boolean cycleRejected = false;
        try {
            new TreeIndex(3, List.of(
                new Edge(0, 1, 1),
                new Edge(0, 1, 2)
            ), 0);
        } catch (IllegalArgumentException expected) {
            cycleRejected = true;
        }
        System.out.println(
            "Cycle/multi-edge rejected: " + cycleRejected
        );

        boolean invalidVertexRejected = false;
        try {
            index.query(3, 9);
        } catch (IllegalArgumentException expected) {
            invalidVertexRejected = true;
        }
        System.out.println(
            "Invalid vertex rejected: "
            + invalidVertexRejected
        );

        // Đối chứng: 400 cây ngẫu nhiên, 12 truy vấn/cây.
        Random random = new Random(319L);
        int checked = 0;

        for (int trial = 0; trial < 400; trial++) {
            int n = 1 + random.nextInt(20);
            int root = random.nextInt(n);
            List<Edge> edges = new ArrayList<>();

            // Mỗi đỉnh v>0 nối với đúng một đỉnh trước v.
            for (int v = 1; v < n; v++) {
                int parent = random.nextInt(v);
                long weight = random.nextInt(41) - 20L;
                edges.add(new Edge(v, parent, weight));
            }

            TreeIndex tree = new TreeIndex(n, edges, root);

            for (int q = 0; q < 12; q++) {
                int u = random.nextInt(n);
                int v = random.nextInt(n);

                List<Integer> expectedPath =
                    bfsPath(n, edges, u, v);
                BigInteger expectedSum =
                    bfsPathWeight(edges, expectedPath);
                int expectedLca =
                    naiveLca(n, edges, root, u, v);

                Query got = tree.query(u, v);
                if (got.lca() != expectedLca
                        || got.edgeCount()
                            != expectedPath.size() - 1L
                        || !got.weightSum().equals(expectedSum)
                        || !tree.pathVertices(u, v)
                            .equals(expectedPath)) {
                    throw new AssertionError(
                        "Mismatch at trial=" + trial
                        + " query=" + q
                    );
                }
            }
            checked++;
        }

        System.out.println(
            "Random BFS comparisons: " + checked
        );
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**, lưu tệp UTF-8:

```bash
javac -encoding UTF-8 TreePathQueriesDemo.java
java TreePathQueriesDemo
```

**Đầu ra chuẩn:**

```text
Main 3->4: lca=1 edges=2 weight=4 path=[3, 1, 4]
Main 3->8: lca=0 edges=5 weight=27 path=[3, 1, 0, 2, 5, 8]
Main 7->8: lca=5 edges=2 weight=9 path=[7, 5, 8]
Main 4->6: lca=0 edges=4 weight=4 path=[4, 1, 0, 2, 6]
Main 2->2: lca=2 edges=0 weight=0 path=[2]
Main 0->8: lca=0 edges=3 weight=16 path=[0, 2, 5, 8]
Single 0->0: lca=0 edges=0 weight=0 path=[0]
Long.MAX_VALUE twice: lca=0 edges=2 weight=18446744073709551614 path=[0, 1, 2]
Long.MIN_VALUE plus -5: lca=0 edges=2 weight=-9223372036854775813 path=[0, 1, 2]
Cycle/multi-edge rejected: true
Invalid vertex rejected: true
Random BFS comparisons: 400
```

### 11.1. Vì sao gốc tự trỏ tới chính nó?

Cây có một gốc; với gốc đó, không tồn tại “cha thực sự”. Tuy nhiên, `up[k][root]=root` giúp mọi phép nhảy tổ tiên có chỉ số hợp lệ, kể cả khi nâng nhiều bước hơn độ sâu thực.

Nếu dùng `-1` cho cha của gốc, phải kiểm tra liên tục để không truy cập `up[k][-1]`. Cả hai cách đều có thể đúng khi cài cẩn thận; ví dụ này chọn **gốc tự trỏ** để giản lược.

### 11.2. Vì sao dùng BFS lặp?

Cây dạng dây có thể sâu gần `n`. Dùng DFS đệ quy trên Java có thể gây `StackOverflowError` nếu `n` rất lớn. BFS dùng `ArrayDeque` với vòng `while`, không phụ thuộc độ sâu ngăn xếp lời gọi Java.

Dù dùng BFS, các giá trị `parent/depth/prefix` vẫn đúng vì cây có **đường duy nhất từ gốc tới mỗi đỉnh**. Không bắt buộc DFS mới xây được cây cha.

### 11.3. Vì sao validate bằng DSU trước?

Nếu đầu vào có chu trình, có thể có **nhiều đường đơn** giữa hai đỉnh. Khi đó `pathSum` không còn là một đại lượng duy nhất nếu không nêu rõ chọn đường nào. Nếu đầu vào không liên thông, LCA giữa hai đỉnh ở hai thành phần khác nhau **không tồn tại**.

Kiểm tra `n-1` cạnh + `DSU.union` không phát hiện chu trình + một thành phần bảo đảm dữ liệu đúng loại **cây**. Mã từ chối cạnh song song/khuyên dẫn đến chu trình, không âm thầm chọn một cây DFS của đồ thị rồi trả kết quả như thể đó là đường duy nhất của đồ thị gốc.

### 11.4. Tại sao truy vấn O(log n) nhưng đường trả về không O(log n)?

`query(u,v)` chỉ:

1. Tìm `LCA(u,v)` bằng `O(\log n)` bước nhảy.
2. Tính `edgeCount` theo độ sâu.
3. Tính `weightSum` theo prefix.

Không phải duyệt những đỉnh trên đường. Nhưng `pathVertices(u,v)` phải lần lượt thêm `u,parent[u],...` cho tới LCA, rồi đi nhánh xuống `v`. Vì vậy hàm này tốn **`O(\ell+1)`** thời gian/bộ nhớ cho đường có `\ell` cạnh, ngoài `O(\log n)` để tìm LCA.

**Không được nhận xét toàn bộ `show` là `O(\log n)`**, vì `show` vừa gọi `query` vừa dựng/in cả đường.

### 11.5. Giới hạn BigInteger

Trọng số từng cạnh là `long`, còn prefix và tổng trả về là `BigInteger` nên không tràn khi cộng các trọng số hợp lệ kiểu `long`.

Ví dụ:

\[
Long.MAX\_VALUE + Long.MAX\_VALUE
=18446744073709551614,
\]

lớn hơn `Long.MAX_VALUE` nhưng được biểu diễn chính xác.

Tương tự:

\[
Long.MIN\_VALUE-5=-9223372036854775813.
\]

Nếu đề chỉ cho trọng số `int` và đảm bảo tổng trong `long`, có thể dùng `long prefix[]` để giảm overhead; nhưng phải chứng minh cận của tổng trước khi bỏ `BigInteger`.

## 12. Độ phức tạp chính xác

Đặt `n` là số đỉnh, `q` là số truy vấn, `\ell` là số cạnh trên đường cần in.

| Thao tác | Thời gian | Bộ nhớ phụ |
|---|---|---|
| Kiểm tra cây bằng DSU | `O(n\alpha(n))` | `O(n)` |
| Xây danh sách kề | `O(n)` trên cây vì `m=n-1` | `O(n)` |
| BFS gốc hóa, tính depth/prefix | `O(n)` phép duyệt | `O(n)` |
| Xây bảng nhảy `up` | `O(n\log n)` | `O(n\log n)` |
| Tính một `LCA(u,v)` | `O(\log n)` | `O(1)` ngoài bảng |
| Trả số cạnh và tổng trọng số | `O(\log n)` kể cả LCA | `O(1)` phần tính công thức |
| Xuất đường đỉnh | `O(\log n+\ell+1)` | `O(\ell+1)` cho danh sách |
| `q` truy vấn chỉ cần giá trị | `O(n\log n+q\log n)` | `O(n\log n)` |

Đây là độ phức tạp trên mô hình phép toán số học chuẩn. Với `BigInteger`, phép cộng/trừ và đối tượng kết quả còn có chi phí phụ thuộc số bit của tổng. Trong các bài tập có trọng số bị chặn bởi `long` và `n` thực tế, chi phí này thường nhỏ, nhưng không nên khẳng định tuyệt đối là hằng số khi xét số nguyên dài tùy ý.

### Lưu ý bộ nhớ

Bảng `up[LOG][n]` có khoảng `n\lfloor\log_2n\rfloor` phần tử `int`, có thể lớn khi `n` rất cao. Cấu trúc binary lifting phù hợp khi có nhiều truy vấn, còn nếu chỉ có một truy vấn, DFS/BFS trực tiếp có thể đơn giản và tiết kiệm hơn.

## 13. Biến thể quan trọng: tổng giá trị trên các đỉnh thay vì các cạnh

Nhiều đề ghi “tổng trọng số trên đường đi” nhưng trọng số có thể gắn vào:

- **Cạnh**: dùng công thức prefix cạnh đã chứng minh.
- **Đỉnh**: dùng một công thức hơi khác vì **LCA được tính là một đỉnh trên đường**.

Nếu mỗi đỉnh `u` có giá trị `value[u]`, định nghĩa:

\[
vertexPrefix[u]
=\sum_{x\text{ trên đường từ root tới }u}value[x],
\]

**bao gồm cả gốc và `u`**. Với `a=LCA(u,v)`, tổng giá trị đỉnh trên đường `u\rightsquigarrow v` là:

\[
\boxed{
vertexPathSum(u,v)
=vertexPrefix[u]+vertexPrefix[v]
-2\,vertexPrefix[a]+value[a].
}
\]

Tại sao phải cộng lại `value[a]`?

Hai prefix đều chứa toàn bộ đoạn từ gốc đến `a`. Trừ hai lần `vertexPrefix[a]` sẽ xóa luôn đóng góp của **chính `a`** khỏi tổng. Nhưng trên đường `u\rightsquigarrow v`, đỉnh `a` cần được tính **một lần**, nên phải cộng lại `value[a]`.

### 13.1. Ví dụ đỉnh có giá trị

Cho cây ba đỉnh `0--1--2`, các giá trị đỉnh:

```text
value[0] = 5
value[1] = 7
value[2] = -2

root=0
vertexPrefix[0]=5
vertexPrefix[1]=12
vertexPrefix[2]=10
```

Tổng giá trị các đỉnh trên đường `1\to2` là `7+(-2)=5`.

Theo công thức:

\[
12+10-2\cdot12+7=5.
\]

Nếu dùng nhầm công thức **cạnh** không có `+value[LCA]`, kết quả chỉ là `-2`, thiếu giá trị đỉnh `1`.

Đối với truy vấn `u=u`:

\[
vertexPathSum(u,u)=value[u],
\]

khác với **tổng trọng số cạnh** trên đường từ `u` tới nó, vốn luôn bằng `0`.

### 13.2. Trọng số ở đỉnh nhưng chỉ muốn đếm đỉnh

Nếu cần **số đỉnh** trên đường đơn:

\[
\boxed{vertexCount(u,v)=edgeDistance(u,v)+1.}
\]

Ví dụ đường `3\to1\to4` có **2 cạnh** nhưng **3 đỉnh**. Truy vấn `(u,u)` có **0 cạnh** và **1 đỉnh**.

## 14. Các truy vấn khác và khi công thức prefix không đủ

### 14.1. Tổng trọng số là phép toán có tính cộng dồn

Tổng trọng số có tính chất:

\[
sum(A\cup B)=sum(A)+sum(B)
\]

khi hai tập cạnh `A,B` không giao nhau. Vì thế ta có thể lấy prefix trên các đường gốc rồi **trừ đoạn chung**.

Nhưng nếu truy vấn hỏi **cạnh lớn nhất/nhỏ nhất** trên đường, phép trừ prefix kiểu:

```text
maxPrefix[u] + maxPrefix[v] - 2 * maxPrefix[LCA]
```

**không có ý nghĩa**. Phép `max` không có phép nghịch đảo tương tự phép cộng. Ta phải lưu bảng binary lifting của **min/max trên đoạn nhảy 2^k**, hoặc dùng kỹ thuật khác.

Ví dụ:

```text
maxUp[k][u] = cạnh nặng nhất trên đoạn từ u lên up[k][u]
maxUp[k][u] = max(
    maxUp[k-1][u],
    maxUp[k-1][up[k-1][u]]
)
```

Khi nâng hai đỉnh để tìm LCA, đồng thời gộp các giá trị max của những đoạn đã nhảy. Truy vấn max/min có thể đạt `O(\log n)` sau tiền xử lý `O(n\log n)`.

### 14.2. XOR trên đường

Nếu trọng số nguyên được kết hợp bằng **XOR**, phép XOR có tính chất `x\oplus x=0`. Vì vậy nếu định nghĩa `xorPrefix[u]` là XOR các trọng số cạnh từ gốc tới `u`:

\[
\boxed{pathXor(u,v)=xorPrefix[u]\oplus xorPrefix[v].}
\]

Không cần XOR thêm LCA, bởi mọi cạnh trên đoạn chung tự triệt tiêu. Đây là đặc điểm của phép toán XOR, **không phải** công thức tổng số học.

### 14.3. Khoảng cách hình học có trọng số

Nếu mọi cạnh có trọng số **không âm**, tổng trọng số trên đường đơn có thể được xem là **weighted shortest-path distance** vì cây chỉ có một đường đơn, và đi thêm vòng không giúp giảm tổng.

Nếu tất cả cạnh **dương**, nó thỏa tính chất khoảng cách dương cho hai đỉnh khác nhau. Nếu có cạnh trọng số `0`, hai đỉnh khác nhau có thể có “khoảng cách trọng số” bằng `0`, nên chỉ có **pseudometric** trong một số định nghĩa.

Nếu có cạnh âm, tổng đường vẫn có nghĩa đại số nhưng **không còn là metric**; không được tự áp dụng những định lý yêu cầu khoảng cách không âm hoặc bất đẳng thức tam giác của metric chuẩn.

## 15. Nếu trọng số thay đổi theo thời gian thì sao?

Mã Java ở phần 11 dùng **cây tĩnh**: cấu trúc cạnh và trọng số không đổi sau khi tiền xử lý.

Giả sử trọng số của cạnh `e` thay từ `w` thành `w+\Delta`. Khi gốc hóa cây, chọn đầu con `child` của cạnh đó. Mọi đỉnh trong **cây con của `child`** có prefix mới tăng thêm `\Delta`; các đỉnh ngoài cây con giữ nguyên.

Do đó, cập nhật một cạnh tác động tới **một đoạn cây con**, không chỉ tới hai đầu mút.

### 15.1. Không được sửa mỗi prefix của hai đầu

Nếu chỉ sửa `prefix[child]` nhưng không sửa prefix của mọi hậu duệ, các truy vấn đi qua các cạnh bên dưới sẽ nhận kết quả sai. Cũng không thể tiếp tục dùng prefix cũ sau thay đổi mà không có cấu trúc cập nhật phù hợp.

### 15.2. Euler tour + Fenwick/segment tree cho cập nhật cạnh

Với cây có gốc, tạo thứ tự **DFS Euler entry** sao cho toàn bộ cây con của một đỉnh chiếm **một đoạn liên tiếp** `[tin[u],tout[u])` theo quy ước một mốc vào cho mỗi đỉnh.

Một lần thay cạnh `parent[child]--child` bởi `+\Delta` làm tăng root-prefix của **mọi đỉnh trong cây con child** đúng `\Delta`. Có thể:

- Dùng **segment tree lazy** để **range add** trên đoạn subtree, **point query** tại `tin[u]`.
- Hoặc dùng **Fenwick tree trên mảng hiệu** để range add, point query.

Khi hỏi tổng đường:

\[
dynamicPrefix(u)+dynamicPrefix(v)
-2dynamicPrefix(LCA(u,v)).
\]

Nếu cấu trúc cây **không thay**, LCA binary lifting vẫn dùng được. Phần cập nhật/đọc prefix từ Fenwick/segment tree tốn khoảng `O(\log n)`, nên truy vấn tổng vẫn khoảng `O(\log n)` cộng LCA.

**Điều kiện:** cần xử lý đúng đỉnh con theo gốc, lưu `\Delta` chính xác, và xác định rằng tin/tout là **quy ước subtree interval** của Euler tour, không phải tùy tiện lấy thời điểm vào/ra có hai mốc mỗi đỉnh mà không chuyển đổi chỉ số.

### 15.3. HLD cho truy vấn trên đường động

**Heavy-Light Decomposition (HLD)** chia các đường đi trên cây thành `O(\log n)` đoạn liên tiếp trên một mảng cơ sở. Dùng segment tree để duy trì tổng/min/max và cập nhật trọng số, truy vấn tổng trên đường thường đạt `O(\log^2 n)`.

HLD hữu ích khi:

- Có nhiều cập nhật trọng số đỉnh/cạnh.
- Truy vấn không chỉ là tổng, mà còn min/max hoặc các phép gộp đoạn.
- Cần xử lý các đoạn đường động theo nhiều dạng.

Nếu chỉ hỏi khoảng cách/sum trên **cây tĩnh**, binary lifting + prefix đơn giản hơn HLD.

## 16. Cây có thể thay đổi cấu trúc: khi nào cần kỹ thuật khác?

Thay một trọng số cạnh **khác** với **xóa/thêm một cạnh**. Nếu cấu trúc cây thay đổi, `parent/depth/LCA` đã tiền xử lý có thể không còn đúng.

Ví dụ xóa cạnh `1--4` rồi nối `4--6`:

- Đường đi từ `4` tới nhiều đỉnh thay đổi.
- Độ sâu và cha của `4` có thể đổi.
- Prefix cũ của `4` và các đỉnh trong nhánh nó không còn ứng với cây mới.
- Kết quả LCA tiền xử lý không được tái sử dụng mù.

Đối với truy vấn động **link/cut** liên tục, cần cấu trúc cao cấp như **link-cut tree** hoặc Euler-tour tree trong đúng bài toán được hỗ trợ. Với số lần thay đổi cấu trúc rất ít, xây lại tiền xử lý sau mỗi lần thay đổi cũng có thể là lựa chọn đơn giản và đúng.

Không được coi thuật toán LCA tĩnh là tự động hỗ trợ tất cả phép cập nhật động.

## 17. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Nhầm số cạnh với tổng trọng số | `depth` không phải prefix trọng số | Dùng hai mảng `depth[]` và `prefix[]` riêng |
| Gọi Dijkstra cho một cây chỉ để tìm đường đơn | Không cần tìm trong nhiều đường; tốn công triển khai | BFS/DFS hoặc LCA + prefix trên cây |
| Coi `u\to v` và `v\to u` là hai cạnh vật lý khác nhau của cây vô hướng | Gây đếm cạnh sai; có thể báo chu trình giả | Một cạnh đầu vào, hai mục adjacency |
| Không kiểm tra đầu vào là cây | Công thức theo cây cha có thể trả đường không duy nhất hoặc thiếu đường | Kiểm tra `n-1`, không chu trình, liên thông |
| Bỏ qua khuyên/cạnh song song khi kiểm tra cây | Có thể nhận đồ thị có chu trình | DSU kiểm tra từng cạnh vật lý |
| Quên trường hợp `n=1` | Truy cập cạnh/cha không tồn tại | Gốc tự trỏ; query(0,0) trả số cạnh 0, sum 0 |
| Dùng `depth[child]=depth[parent]+weight` | Depth mất ý nghĩa số cạnh | Depth luôn cộng `1` qua mỗi cạnh |
| Không đặt `prefix[root]=0` | Mọi tổng đường có thể sai | Khởi tạo rõ ràng từ gốc |
| Trộn prefix tính từ gốc A với LCA tính từ gốc B | Công thức hai hệ quy chiếu khác nhau | Tính và truy vấn nhất quán một gốc |
| Quên trừ `2*prefix[LCA]` | Đếm đoạn gốc–LCA hai lần | Dùng công thức chuẩn cho trọng số cạnh |
| Nhầm công thức trọng số đỉnh với trọng số cạnh | Mất giá trị đỉnh LCA | Với trọng số đỉnh, cộng lại `value[LCA]` |
| Dùng `int` để cộng trọng số hoặc tính trung gian độ sâu cực lớn | Có thể tràn | `BigInteger` cho sum, `long` cho biểu thức đếm |
| Chỉ dùng `long` cho tổng mà không có giới hạn đề | Tổng nhiều cạnh có thể tràn | Dùng `BigInteger` hoặc `Math.addExact` |
| Sử dụng `up[k][u]` trước khi xây các mức nhỏ hơn | Bảng tổ tiên sai | Tính `up[0]` trước, rồi `k=1..LOG-1` |
| Nhảy mức `k` khi tổ tiên hai phía đã bằng nhau | Có thể nhảy vượt LCA | Chỉ nâng khi `up[k][u]!=up[k][v]` |
| Không nâng hai đỉnh về cùng độ sâu | Bước đối xứng tìm LCA bị sai | Nâng đỉnh sâu hơn trước |
| Dùng `parent[root]=-1` nhưng không bảo vệ khi nhảy | Có thể truy cập `up[-1]` | Dùng gốc tự trỏ hoặc kiểm tra rõ |
| Tin rằng dựng cả đường là `O(\log n)` | Phải xuất `\ell+1` đỉnh | Tách API query giá trị và dựng đường |
| Với trọng số âm, gọi tổng đường là metric | Không thỏa tính không âm | Phân biệt tổng đường đơn với shortest walk |
| Với nhiều cập nhật trọng số vẫn dùng prefix tĩnh | Prefix của cả cây con có thể sai | Euler tour + Fenwick/segment tree hoặc xây lại |
| Với nhiều lần link/cut vẫn dùng LCA cũ | Thay cấu trúc phá cây cha | Rebuild hoặc cấu trúc dynamic tree |
| Áp công thức prefix tổng cho max/min | Max/min không có phép trừ prefix phù hợp | Lưu aggregate min/max trên bước nhảy hoặc HLD |
| Chỉ so một vài ví dụ mà không đối chiếu đường thật | Có thể không lộ lỗi nhảy LCA | Sinh cây và truy vấn ngẫu nhiên, so BFS độc lập |
| Không kiểm tra u/v trước khi truy vấn | Truy cập mảng ngoài miền | Validate `0\le u,v<n` |

## 18. Kiểm thử độc lập: BFS làm oracle cho công thức LCA

Kiểm thử tốt phải **không dùng lại công thức đang cần kiểm tra** để suy ra đáp án kỳ vọng.

Trong chương trình mẫu, oracle `bfsPath` không truy cập `up[]`, `depth[]` hoặc `prefix[]`. Nó chỉ nhìn các cạnh đầu vào để tìm đường từ `u` tới `v` theo BFS. Vì đầu vào là cây, đường ấy là đường đơn duy nhất.

Đối với mỗi cặp truy vấn:

1. Chạy BFS để dựng danh sách đỉnh kỳ vọng.
2. **Đếm cạnh** trong danh sách: `expectedEdgeCount=path.size()-1`.
3. Tính **tổng trọng số thực** của các cạnh liên tiếp trong danh sách.
4. Tìm LCA độc lập bằng cách dựng đường `root\to u` và `root\to v` qua BFS, lấy **đỉnh cuối cùng chung trong tiền tố**.
5. So ba kết quả đó với `TreeIndex.query(u,v)`.
6. So danh sách đường với `TreeIndex.pathVertices(u,v)`.

### 18.1. Sinh cây ngẫu nhiên chắc chắn hợp lệ

Một cách đơn giản để tạo cây `n` đỉnh:

```text
for v = 1 .. n-1:
    chọn parent ngẫu nhiên trong [0, v-1]
    thêm cạnh vô hướng (parent, v) với trọng số ngẫu nhiên
```

Mỗi đỉnh `v>0` được nối với một đỉnh có chỉ số nhỏ hơn, nên mọi đỉnh có đường đi về `0`; có đúng `n-1` cạnh và không tạo chu trình. Sau đó chọn **gốc truy vấn** ngẫu nhiên, có thể không phải `0`.

Để lộ lỗi dấu và prefix, trọng số nên có cả âm, `0` và dương. Trọng số ở hai nhánh gần LCA cần khác nhau. Không chỉ tạo toàn số `1`.

### 18.2. Những ca biên bắt buộc

```text
1 đỉnh, không cạnh: query(0,0) => edges=0, weight=0
2 đỉnh, 1 cạnh: đường có đúng 1 cạnh
Cây dạng dây: LCA của hai đỉnh nằm ở đỉnh nông hơn
Cây hình sao: LCA hai lá khác nhau là tâm nếu tâm làm gốc
Cây cân bằng: LCA có thể sâu hơn gốc
Hai đỉnh cùng nhau: u==v => edges=0, weight=0
Một đỉnh là tổ tiên của đỉnh còn lại
Hai nhánh khác nhau qua gốc
Đường chứa cạnh trọng số 0
Đường chứa cạnh trọng số âm
Tổng vượt Long.MAX_VALUE hoặc dưới Long.MIN_VALUE
Gốc là một lá thay vì đỉnh 0
Cạnh song song, khuyên, chu trình: phải bị từ chối
Đỉnh không hợp lệ: phải bị từ chối
```

### 18.3. Property-based checks

Với trọng số cạnh bất kỳ (kể cả âm), trên **cây tĩnh**:

\[
edgeDistance(u,v)=edgeDistance(v,u),
\]

\[
pathSum(u,v)=pathSum(v,u),
\]

\[
edgeDistance(u,u)=0,
\]

\[
pathSum(u,u)=0.
\]

Nếu `x` nằm trên đường đơn từ `u` tới `v`, thì:

\[
edgeDistance(u,v)
=edgeDistance(u,x)+edgeDistance(x,v),
\]

\[
pathSum(u,v)
=pathSum(u,x)+pathSum(x,v).
\]

Với trọng số cạnh không âm, còn có bất đẳng thức tam giác cho tổng trọng số. Với trọng số âm, **không được** dùng bất đẳng thức metric chuẩn để kết luận.

Nếu đổi gốc nhưng không đổi cấu trúc/trọng số cây, **LCA có thể khác**, nhưng `edgeDistance` và `pathSum` phải giữ nguyên. Đây là một test rất mạnh để phát hiện việc tính prefix không nhất quán.

### 18.4. Kiểm thử 400 cây như chương trình

Mã Java trong `main` tạo **400 cây** có kích thước `1..20`, gốc ngẫu nhiên, trọng số trong `[-20,20]`. Mỗi cây sinh **12 cặp truy vấn**, tổng **4.800 truy vấn** đối chiếu:

- LCA so với giao tiền tố của hai đường BFS từ gốc.
- Số cạnh so với `path.size()-1`.
- Tổng trọng số so với cộng trực tiếp từng cạnh của đường BFS.
- Danh sách đường so với oracle BFS.

Kiểm thử hữu hạn **không thay thế chứng minh** ở phần 9. Nhưng nó giúp bắt lỗi code khi nâng bit, tính cha, nhầm trọng số hay tạo đường.

## 19. Bài tập tự luyện kèm lời giải

**Bài 1 — Số cạnh.** Trong cây mẫu, tính `edgeDistance(3,8)` và `edgeDistance(7,8)`.

*Đáp án:* `5` và `2`.

**Bài 2 — Tổng có trọng số âm.** Vì sao `pathSum(3,4)=4` dù một nhánh có tổng prefix `11`?

*Đáp án:* `LCA=1`, nên `11+1-2\cdot4=4`. Đường có trọng số `7` và `-3`, tổng bằng `4`.

**Bài 3 — LCA.** Với cây mẫu gốc `0`, xác định `LCA(3,4)`, `LCA(7,8)`, `LCA(4,6)`.

*Đáp án:* lần lượt `1`, `5`, `0`.

**Bài 4 — Độ sâu.** Nếu `depth[3]=2`, `depth[8]=3`, `depth[LCA(3,8)]=0`, số cạnh là bao nhiêu?

*Đáp án:* `2+3-0=5`.

**Bài 5 — Một đỉnh.** Cây chỉ có một đỉnh `0`. Đường `0\to0` có bao nhiêu cạnh và tổng trọng số bao nhiêu?

*Đáp án:* không có cạnh, tổng `0`; nếu hỏi số **đỉnh**, đáp án là `1`.

**Bài 6 — Không thuộc cùng cây.** Một rừng có hai thành phần, `u` ở thành phần A và `v` ở thành phần B. Có thể áp dụng công thức LCA chung như trên không?

*Đáp án:* không. Không có đường giữa `u,v` và không có LCA trong cùng một cây; cần trả `NO_PATH` hoặc xử lý theo thành phần nếu đề cho rừng.

**Bài 7 — Thay gốc.** Nếu đổi gốc từ `0` sang `5`, đường đơn và tổng trọng số giữa `3,8` có thay đổi không?

*Đáp án:* không; vẫn có `5` cạnh, tổng `27`. LCA, parent, depth/prefix mới có thể thay đổi nhưng phải cho cùng kết quả sau khi dùng nhất quán.

**Bài 8 — Giá trị đỉnh.** Nếu `value[0]=5,value[1]=7,value[2]=-2` trên cây `0--1--2`, tổng giá trị đỉnh trên đường `1\to2` là bao nhiêu?

*Đáp án:* `5`. Công thức `vertexPrefix[1]+vertexPrefix[2]-2vertexPrefix[1]+value[1]=5`.

**Bài 9 — Max trên đường.** Có thể trả cạnh nặng nhất trên đường bằng `maxPrefix[u]+maxPrefix[v]-2maxPrefix[LCA]` không?

*Đáp án:* không. Max không có phép trừ nghịch đảo như tổng số học; cần lưu `maxUp[k][u]` hoặc dùng HLD/segment tree.

**Bài 10 — Cập nhật trọng số cạnh.** Cạnh cha–con `p--c` đổi trọng số tăng `\Delta`. Những `prefix[x]` nào cần tăng?

*Đáp án:* `prefix[x]` của **mọi đỉnh trong cây con gốc tại c** khi giữ gốc hiện tại; các đỉnh ngoài cây con không đổi.

**Bài 11 — Tại sao BigInteger?** Hai cạnh trên đường đều có trọng số `Long.MAX_VALUE`. Tổng bằng bao nhiêu?

*Đáp án:* `18446744073709551614`, lớn hơn `long` có dấu. Dùng `BigInteger` hoặc kiểm tra tràn và giới hạn tương ứng.

**Bài 12 — Dựng đường.** Vì sao `pathVertices(u,v)` có thể tốn `O(n)` dù `LCA(u,v)` chỉ mất `O(\log n)`?

*Đáp án:* phải xuất từng đỉnh trên đường. Với cây dạng dây, đường có thể chứa tới `n` đỉnh, nên độ dài output đã là `\Omega(n)`.

**Bài 13 — XOR đường.** Cho `xorPrefix[u]` là XOR trọng số cạnh từ gốc đến `u`. Viết công thức XOR trên đường `u\to v`.

*Đáp án:* `xorPrefix[u] ^ xorPrefix[v]`. Các cạnh trên đoạn gốc–LCA xuất hiện hai lần nên tự triệt tiêu theo XOR.

**Bài 14 — Chứng minh đường duy nhất.** Vì sao giữa hai đỉnh khác nhau trong một cây chỉ có một đường đơn?

*Đáp án:* liên thông bảo đảm có ít nhất một đường. Nếu có hai đường đơn khác nhau, hợp chúng chứa chu trình, trái với tính phi chu trình của cây.

**Bài 15 — Hướng triển khai cho nhiều truy vấn.** Đề cho cây tĩnh, `n` và `q` đều lớn; mỗi truy vấn cần trả số cạnh và tổng trọng số cạnh. Nên dùng gì?

*Đáp án:* gốc hóa cây một lần, tính `depth[]`, `prefix[]`, dựng `up[][]` để tìm LCA bằng binary lifting. Tiền xử lý `O(n\log n)`, mỗi truy vấn `O(\log n)`.

## 20. Checklist khi làm bài “khoảng cách/tổng trọng số trên đường”

1. Đầu vào chắc chắn là **cây** hay có thể là đồ thị/rừng? Có kiểm tra `n-1` và liên thông/chu trình?
2. **Trọng số gắn với cạnh hay với đỉnh?** Hai công thức prefix khác nhau tại LCA.
3. Đề hỏi **số cạnh, số đỉnh, tổng trọng số, min/max hay XOR**? Không gộp các đại lượng đó.
4. Nếu hỏi **chỉ một truy vấn**, DFS/BFS `O(n)` có thể đủ. Nếu có **nhiều truy vấn**, cân nhắc LCA.
5. Gốc đã chọn có hợp lệ không? `parent[root]` theo quy ước nào?
6. `depth[root]=0` và `prefix[root]=0` đã được gán chưa?
7. Khi đi từ cha `u` sang con `v`, có gán `depth[v]=depth[u]+1` và `prefix[v]=prefix[u]+w` không?
8. Bảng `up[k][u]` đã xây theo thứ tự `k` tăng, với `up[0]` đúng?
9. Tìm LCA đã nâng hai đỉnh về **cùng độ sâu** trước?
10. Công thức số cạnh có trừ **`2depth[LCA]`** không?
11. Công thức tổng cạnh có trừ **`2prefix[LCA]`** không?
12. Tổng có thể âm hoặc vượt `long` không? Có chọn kiểu và cách cộng phù hợp?
13. Với `u=v`, query cạnh có trả `0`, còn query giá trị đỉnh có trả `value[u]`?
14. Có **trọng số thay đổi** hoặc **link/cut** sau tiền xử lý không? Nếu có, mảng tĩnh vẫn hợp lệ chứ?
15. Có yêu cầu **in cả đường** không? Nếu có, độ phức tạp phải tính thêm số đỉnh xuất ra.
16. Có đối chứng với **BFS độc lập**, cả trên cây dạng dây, hình sao, gốc khác `0`, trọng số âm/`0` và số cực trị?

## Ghi nhớ

Trên một **cây vô hướng có trọng số**, giữa hai đỉnh bất kỳ có **đúng một đường đơn**. Gốc hóa cây để tính `depth[u]` (số cạnh từ gốc), `prefix[u]` (tổng trọng số cạnh từ gốc) và `LCA(u,v)`.

Với `a=LCA(u,v)`:

\[
\boxed{
edgeDistance(u,v)=depth[u]+depth[v]-2depth[a].
}
\]

\[
\boxed{
pathSum(u,v)=prefix[u]+prefix[v]-2prefix[a].
}
\]

- Binary lifting xây `up[k][u]` trong **`O(n\log n)`** và tìm LCA trong **`O(\log n)`**.
- Tổng trọng số cạnh có thể **âm hoặc vượt `long`**; dùng kiểu đủ rộng, ví dụ `BigInteger`.
- Nếu đếm **đỉnh**, dùng `edgeDistance+1`. Nếu cộng **giá trị đỉnh**, cần cộng lại `value[LCA]` trong công thức prefix.
- Nếu phải **in toàn đường**, thêm thời gian `O(\ell)` cho `\ell` cạnh; nếu trọng số/cấu trúc thay đổi, cần cập nhật tiền xử lý hoặc cấu trúc dữ liệu phù hợp.

**Phân biệt số cạnh, trọng số cạnh và giá trị đỉnh; hiểu vì sao LCA chia đường thành hai đoạn; và tính prefix nhất quán từ một gốc là ba chìa khóa để trả lời truy vấn đường đi trên cây chính xác, hiệu quả.**
