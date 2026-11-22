# Kích thước cây con, độ sâu và khoảng cách từ gốc

Trong **thuật toán trên cây**, ba đại lượng xuất hiện liên tục là **kích thước cây con** (*subtree size*), **độ sâu** (*depth*) và **khoảng cách từ gốc** (*distance from root*). Chúng thường được tính trong cùng một lượt duyệt DFS/BFS và dùng làm nền tảng cho truy vấn tổ tiên, duyệt cây con, tính tổng trên cây, quy hoạch động trên cây, tìm tổ tiên chung gần nhất (*LCA*), gom truy vấn hoặc đổi gốc (*rerooting*).

Thoạt nhìn ba đại lượng có vẻ đều mô tả “một đỉnh ở đâu trên cây”, nhưng bản chất khác nhau:

- **Độ sâu:** Có **bao nhiêu cạnh** trên đường duy nhất từ gốc tới đỉnh?
- **Khoảng cách từ gốc:** **Tổng trọng số** của các cạnh trên đường duy nhất từ gốc tới đỉnh là bao nhiêu?
- **Kích thước cây con:** Sau khi chọn gốc và hướng cha–con, có **bao nhiêu đỉnh** nằm trong cây con gốc tại một đỉnh, **tính cả chính đỉnh đó**?

Bài học giải thích định nghĩa, điều kiện input là cây, cách xây quan hệ cha–con từ cạnh vô hướng, hai chiều tính toán **từ gốc xuống lá** và **từ lá lên gốc**, một ví dụ có cạnh trọng số bằng 0 và âm, kỹ thuật dùng thứ tự DFS để lấy đoạn liên tiếp của cây con, chứng minh tính đúng và độ phức tạp, thay gốc, kiểm soát tràn số, mã **Java 17+** đầy đủ và bài tập có đáp án.

## 1. Cây vô hướng và cây có gốc

**Cây vô hướng** (*undirected tree*) là một đồ thị vô hướng **liên thông** và **không có chu trình**. Với n≥1 đỉnh, nó có chính xác **n−1 cạnh**; ngược lại, nếu một đồ thị vô hướng liên thông có n−1 cạnh thì đó là cây. Mọi cặp đỉnh trong cây có **đúng một đường đi đơn** nối hai đỉnh ấy.

Ví dụ cây bảy đỉnh:

```text
                0
              /   \
             1     2
            / \     \
           3   4     5
                      \
                       6
```

Các cạnh vô hướng:

```text
{0,1}, {0,2}, {1,3}, {1,4}, {2,5}, {5,6}
```

Chọn đỉnh **0 làm gốc**. Khi đó các cạnh được nhìn theo hướng từ gốc ra ngoài:

```text
0 -> 1, 0 -> 2
1 -> 3, 1 -> 4
2 -> 5
5 -> 6
```

**Quan trọng:** Việc chọn gốc **không đổi cạnh gốc của đồ thị**; nó chỉ xác định ai là cha, ai là con. Nếu đổi gốc sang 1, ta phải xây lại quan hệ cha–con, depth, root distance và subtree size. Một đỉnh ở cùng cây có thể có cây con rất khác nhau dưới hai gốc.

### 1.1. Ba quy ước phải ghi rõ

Bài này dùng các quy ước:

1. `depth[root]=0`: gốc có độ sâu **0 cạnh**, không phải 1.
2. `distance[root]=0`: chưa đi qua cạnh nào nên tổng trọng số bằng 0.
3. `size[v]` gồm **cả v**, nên mọi lá đều có `size[leaf]=1`, gốc của cây có n đỉnh luôn có `size[root]=n`.

Nếu một đề dùng “độ sâu theo số đỉnh” hoặc “kích thước cây con không kể đỉnh gốc”, phải điều chỉnh đúng quy ước, không âm thầm áp dụng công thức khác.

### 1.2. Cây có thể không có trọng số

Với cây **không trọng số**, có thể coi mỗi cạnh có trọng số **1**. Khi đó:

```text
distance[v] = depth[v]
```

Nhưng nếu có trọng số bất kỳ, **hai mảng không còn giống nhau**. Độ sâu luôn đếm số cạnh; khoảng cách từ gốc là tổng trọng số.

### 1.3. Đầu vào là cạnh vô hướng, không phải cung cha–con

Nếu input cung cấp cặp cạnh `(u,v)` của cây vô hướng, ta chưa được kết luận “u là cha của v” chỉ vì u xuất hiện trước. Khi xây danh sách kề, phải thêm **cả hai chiều**:

```text
adj[u].add(v)
adj[v].add(u)
```

Sau đó mới chọn gốc r và duyệt để gán `parent[v]`. Hai chiều trong adjacency phục vụ di chuyển trên cây vô hướng; quan hệ cha–con được xác định qua **quá trình duyệt và gốc đã chọn**, không phải thứ tự input.

## 2. Định nghĩa ba đại lượng

Cho cây vô hướng T có n đỉnh, chọn gốc r. Với mỗi đỉnh v, ký hiệu `parent[v]` là đỉnh ngay trước v trên đường đơn từ r tới v. Gốc không có cha, trong mã lưu `parent[r]=-1`.

### 2.1. Độ sâu depth[v]

**Độ sâu** là số cạnh trên đường đơn từ r tới v:

```text
depth[r] = 0

Với mỗi con v của u:
    depth[v] = depth[u] + 1
```

Độ sâu không phụ thuộc trọng số cạnh. Nếu từ gốc đến v cần đi qua ba cạnh thì `depth[v]=3`, dù trọng số của ba cạnh là [100,0,−5].

Ví dụ cây bảy đỉnh ở phần 1, gốc 0:

```text
depth[0]=0
depth[1]=1, depth[2]=1
depth[3]=2, depth[4]=2, depth[5]=2
depth[6]=3
```

### 2.2. Khoảng cách từ gốc dist[v]

Mỗi cạnh {u,v} có trọng số `w(u,v)`. **Khoảng cách theo đường duy nhất từ gốc** là tổng trọng số của tất cả cạnh trên đường đơn từ r tới v:

```text
dist[r] = 0

Với mỗi con v của u:
    dist[v] = dist[u] + w(u,v)
```

Nếu mỗi cạnh có trọng số 1, công thức trở thành `dist[v]=depth[v]`.

Trong code Java, dùng **long** cho tổng và `Math.addExact` cho phép cộng để phát hiện vượt miền 64 bit, thay vì để phép cộng âm thầm tràn. Nếu tổng có thể thực sự vượt long mà vẫn cần đáp án chính xác, dùng BigInteger hoặc hợp đồng dữ liệu khác.

### 2.3. Kích thước cây con size[v]

**Cây con gốc tại v** (*rooted subtree of v*) gồm v và tất cả các **hậu duệ** (*descendants*) của v trong cây có gốc. Kích thước là số đỉnh của tập ấy:

```text
size[v] = 1 + SUM(size[child])
                trên tất cả con trực tiếp của v
```

Cơ sở:

```text
Nếu v là lá:
    size[v] = 1
```

Dấu **1** là đếm chính v. Vì các cây con của những con khác nhau không giao nhau nên có thể cộng kích thước mà không đếm trùng.

Ví dụ gốc 0:

```text
Cây con(1) = {1,3,4}       => size[1]=3
Cây con(2) = {2,5,6}       => size[2]=3
Cây con(5) = {5,6}         => size[5]=2
Cây con(6) = {6}           => size[6]=1
Cây con(0) = {0,1,2,3,4,5,6} => size[0]=7
```

### 2.4. Bảng so sánh

| Đại lượng | Nghĩa | Gốc | Lá | Chiều tính |
| --- | --- | --- | --- | --- |
| `parent[v]` | Cha của v trên đường từ gốc | −1 | Cha duy nhất | Gốc → con |
| `depth[v]` | Số cạnh từ gốc tới v | 0 | Tùy vị trí | Gốc → con |
| `dist[v]` | Tổng trọng số từ gốc tới v | 0 | Tùy trọng số | Gốc → con |
| `size[v]` | Số đỉnh trong cây con của v, kể cả v | n | 1 | Lá → cha |

Từ bảng, có thể ghi nhớ: **depth và dist lan truyền xuống**, còn **size cộng dồn lên**.

## 3. Ví dụ có trọng số: depth khác distance

Dùng cây bảy đỉnh sau, với trọng số cạnh:

```text
                 0
              3 / \ 5
               1   2
             4/ \-2 \0
             3   4   5
                        \7
                         6

Cạnh:
0--1:  3
0--2:  5
1--3:  4
1--4: -2
2--5:  0
5--6:  7
```

Gốc r=0:

| Đỉnh v | parent[v] | depth[v] | dist[v] | size[v] |
| ---: | ---: | ---: | ---: | ---: |
| 0 | −1 | 0 | 0 | 7 |
| 1 | 0 | 1 | 3 | 3 |
| 2 | 0 | 1 | 5 | 3 |
| 3 | 1 | 2 | 7 | 1 |
| 4 | 1 | 2 | 1 | 1 |
| 5 | 2 | 2 | 5 | 2 |
| 6 | 5 | 3 | 12 | 1 |

Các điểm cần kiểm tra:

- `depth[4]=2` vì đường 0→1→4 có **hai cạnh**; `dist[4]=3+(−2)=1`.
- `depth[5]=2` còn `dist[5]=5+0=5`.
- `depth[6]=3` còn `dist[6]=5+0+7=12`.
- `size[1]=1+size[3]+size[4]=1+1+1=3`.
- `size[2]=1+size[5]=1+2=3`.
- `size[5]=1+size[6]=2`.
- `size[0]=1+size[1]+size[2]=1+3+3=7`.

### Trọng số âm có được phép trong một “cây” không?

Có, nếu đề yêu cầu **tổng trọng số trên đường đi đơn duy nhất**. Cây vẫn có một đường đơn duy nhất giữa hai đỉnh, nên tổng là xác định dù một vài trọng số âm.

Tuy nhiên, trong lý thuyết metric, từ “khoảng cách” thường hàm ý không âm. Nếu một cạnh có trọng số −2, `dist[4]=1` là **tổng trọng số từ gốc**, chứ không nhất thiết là khoảng cách theo nghĩa metric. Hơn nữa, nếu cho phép **walk** đi qua một cạnh vô hướng trọng số âm qua lại nhiều lần, tổng chi phí có thể giảm vô hạn. Vì vậy **không đồng nhất** tổng đường đơn duy nhất với bài đường đi ngắn nhất cho phép lặp cạnh trong đồ thị vô hướng có trọng số âm.

Nếu đề bài của bạn yêu cầu khoảng cách vật lý, thời gian di chuyển hoặc khoảng cách không âm, hãy xác thực `weight≥0` và sử dụng đúng ý nghĩa ứng dụng. Mã mẫu dưới đây **cho phép âm** để làm rõ sự khác nhau giữa depth và tổng trọng số.

## 4. Xây cây có gốc từ danh sách cạnh

Một cây thường được cho bởi n−1 cạnh vô hướng, không có sẵn con/cha. Duyệt bắt đầu từ r để định hướng các cạnh:

```text
parent[r] = -1
depth[r] = 0
dist[r] = 0

Khi đi từ u sang hàng xóm v chưa thăm:
    parent[v] = u
    depth[v] = depth[u] + 1
    dist[v] = dist[u] + weight(u,v)
```

**Phải tránh quay ngược về cha.** Danh sách kề vô hướng của u chứa cả cạnh về parent[u]. Nếu dùng DFS đệ quy mà không bỏ cha hoặc đánh dấu đã thăm, hàm sẽ đi u→parent→u mãi.

Bên cạnh kiểm tra đỉnh cha, nên có mảng `seen[]` để phát hiện input **không phải cây**. Nếu gặp một hàng xóm đã được thăm mà không phải cha, đồ thị chứa chu trình hoặc cạnh song song. Với cây đơn, điều này không được xảy ra.

### 4.1. Chỉ kiểm tra n−1 cạnh có đủ không?

**Không.** Một đồ thị có n đỉnh và n−1 cạnh nhưng **không liên thông** vẫn có thể có một chu trình ở một thành phần khác.

Ví dụ n=4, có ba cạnh:

```text
0--1, 1--2, 2--0
đỉnh 3 cô lập
```

Tổng cạnh bằng n−1=3, nhưng đồ thị chứa tam giác và không liên thông. Vì vậy cần kiểm tra **liên thông và không chu trình**, hoặc kết hợp điều kiện số cạnh với một trong hai tính chất đủ để suy ra tính chất còn lại:

- n−1 cạnh + liên thông ⇒ cây.
- n−1 cạnh + không chu trình ⇒ cây.

Code dùng **đúng n−1 cạnh** làm điều kiện nhanh, và trong duyệt còn phát hiện chu trình; kiểm tra xử lý đủ n đỉnh. Không giả định mọi input có đủ n−1 cạnh đều là cây.

### 4.2. Cạnh trùng và self-loop

- **Self-loop** `u--u` không thuộc cây vô hướng đơn và bị từ chối.
- **Cạnh trùng** giữa cùng hai đỉnh cũng không phải dữ liệu của cây đơn. Với n−1 cạnh, cạnh song song thường gây chu trình đa cạnh và/hoặc để đỉnh khác không liên thông.
- Không tự **gộp** cạnh trùng rồi tiếp tục tính mà không nói rõ, vì điều này thay đổi input. Chương trình mẫu từ chối thông qua kiểm tra chu trình hoặc số cạnh.
- Chỉ số đỉnh ngoài [0,n−1] là lỗi dữ liệu; không được truy cập mảng rồi hy vọng Java xử lý hộ.

## 5. Cách tính bằng hai lượt duyệt theo thứ tự

Thực tế có thể tính cả ba mảng bằng **một lượt DFS xuống** để tạo thứ tự cha–con và **một lượt ngược** để cộng kích thước.

**Lượt 1 — từ gốc ra ngoài:**

- Duyệt mỗi đỉnh đúng một lần.
- Ghi `parent[v]`, `depth[v]` và `dist[v]` khi lần đầu tìm thấy v.
- Ghi đỉnh vào một mảng `order` theo thứ tự duyệt sao cho **cha luôn xuất hiện trước con**.

**Lượt 2 — từ sau lên trước:**

- Khởi tạo `size[v]=1` cho mọi v.
- Duyệt `order` **từ cuối về đầu**, bỏ qua gốc.
- Với mỗi u, cộng `size[u]` vào `size[parent[u]]`.

Giả mã:

```text
BUILD_ROOTED_TREE(root):
    DFS/BFS từ root
    parent[root] = -1
    depth[root] = 0
    dist[root] = 0

    Mỗi khi phát hiện con v của u:
        parent[v] = u
        depth[v] = depth[u] + 1
        dist[v] = dist[u] + w(u,v)

    order = các đỉnh đã duyệt, cha trước con

    for v = 0..n-1:
        size[v] = 1

    for index = n-1 down to 1:
        u = order[index]
        size[parent[u]] += size[u]

    return parent, depth, dist, size
```

**Vì sao không cần đệ quy tính size?** Nếu thứ tự đã đảm bảo cha trước con, duyệt ngược đảm bảo **mọi con và hậu duệ được xử lý trước cha**. Cộng một lần cho mỗi cạnh cha–con là đủ.

### 5.1. Có thể dùng BFS thay DFS không?

**Có** để tính parent, depth, dist và size. Một BFS bắt đầu ở gốc cũng có tính chất cha được đưa vào `order` trước con, nên lượt đi ngược vẫn cộng kích thước đúng.

Tuy nhiên, **không được dùng trực tiếp thứ tự BFS để khẳng định các đỉnh của một cây con nằm liên tiếp**. Ví dụ cây có hai nhánh lớn, BFS sẽ xen các đỉnh cùng tầng từ nhiều nhánh. Tính chất đoạn liên tiếp của cây con trong phần sau cần **DFS preorder thực sự**.

### 5.2. Tại sao nên dùng DFS lặp cho cây rất sâu?

Một cây dây (chain) có n đỉnh, ví dụ 0–1–2–...–(n−1), có độ sâu n−1 khi gốc 0. Đệ quy Java có thể vượt giới hạn ngăn xếp và ném `StackOverflowError` trên input lớn.

DFS lặp dùng `ArrayDeque<Integer>` làm stack; phần dữ liệu duyệt nằm trên heap, thường dễ kiểm soát hơn, và không phụ thuộc sâu n vào **Java call stack**. Code dùng DFS lặp để chạy trên cây dây dài một cách đáng tin cậy hơn.

## 6. Thứ tự DFS preorder và đoạn liên tiếp của cây con

Một lợi ích quan trọng khi dùng DFS là mỗi **cây con có gốc** chiếm **một đoạn liên tiếp** trong thứ tự **DFS preorder**.

Gọi:

- `preorder[]`: các đỉnh theo thứ tự được đưa vào kết quả khi bắt đầu xử lý trong DFS.
- `pos[v]`: vị trí chỉ số 0-based của v trong preorder.
- `size[v]`: số đỉnh trong cây con của v.

Khi DFS duyệt trọn vẹn từng nhánh con trước khi chuyển sang anh em tiếp theo, các đỉnh thuộc cây con v là:

```text
preorder[pos[v] .. pos[v] + size[v] - 1]
```

Đây là **đoạn nửa mở** nếu biểu diễn theo chỉ số:

```text
[pos[v], pos[v] + size[v])
```

Ví dụ gốc 0, nếu sắp hàng xóm theo chỉ số tăng và duyệt DFS theo thứ tự đó:

```text
preorder = [0,1,3,4,2,5,6]
pos     = [0,1,4,2,3,5,6]
            theo thứ tự đỉnh v=0..6
```

Ta có:

```text
Cây con(1):
pos[1]=1, size[1]=3
preorder[1..3] = [1,3,4]

Cây con(2):
pos[2]=4, size[2]=3
preorder[4..6] = [2,5,6]

Cây con(5):
pos[5]=5, size[5]=2
preorder[5..6] = [5,6]
```

### 6.1. Vì sao cây con chiếm một đoạn?

Trong DFS, khi bắt đầu xử lý v, thuật toán **đi sâu hết các nhánh của v trước khi quay về cha của v** để xử lý anh em của v. Vì thế không có đỉnh nằm ngoài cây con v chen giữa các đỉnh thuộc cây con v trong preorder.

Cây con có đúng `size[v]` đỉnh. Phần tử đầu của đoạn là v ở `pos[v]`; vậy toàn bộ cây con nằm đúng trong đoạn dài `size[v]`.

**Đây là một bất biến phụ thuộc thứ tự duyệt**, không phải đặc điểm của bất kỳ hoán vị đỉnh nào. Đổi sang BFS hoặc sắp các đỉnh tùy ý sẽ phá tính liên tiếp.

### 6.2. Truy vấn tổ tiên O(1) sau tiền xử lý

Đỉnh u là **tổ tiên của v, kể cả trường hợp u=v**, khi và chỉ khi:

```text
pos[u] <= pos[v] < pos[u] + size[u]
```

Đây là phép kiểm tra O(1) sau khi đã có `preorder,pos,size`.

Ví dụ gốc 0:

```text
ancestor(1,4) = true  vì pos[4]=3 thuộc [1,4)
ancestor(1,6) = false vì pos[6]=6 không thuộc [1,4)
```

**Lưu ý:** Công thức này chỉ đúng khi `pos` được sinh từ **DFS preorder chuẩn**. Nếu `order` là BFS, việc dùng `pos+size` để kiểm tra tổ tiên có thể sai.

### 6.3. Liên hệ Euler tour và Fenwick/segment tree

Nếu mỗi đỉnh v mang giá trị `value[v]`, ta tạo mảng:

```text
flat[pos[v]] = value[v]
```

Khi đó tổng giá trị trong cây con v chính là tổng đoạn:

```text
sum(flat[pos[v] .. pos[v]+size[v]-1])
```

Vì thế có thể dùng **prefix sums** cho dữ liệu bất biến, **Fenwick tree (BIT)** hoặc **segment tree** nếu giá trị đỉnh thay đổi và cần nhiều truy vấn cây con.

Ví dụ nếu `value[v]=1` cho mọi đỉnh, tổng đoạn bằng đúng `size[v]`. Nếu giá trị khác nhau, cách flatten bằng preorder vẫn giúp biến truy vấn cây thành truy vấn đoạn trên mảng.

**Không nhầm với kỹ thuật Euler tour ghi cả lần vào và lần ra đỉnh.** Ở đây chỉ ghi **mỗi đỉnh một lần theo preorder**, nên `preorder.length=n` và khoảng cây con dùng `size[v]`.

## 7. Ví dụ: đổi gốc làm thay đổi tất cả các mảng

Vẫn cây trọng số ở phần 3 nhưng chọn gốc mới là **1**.

Theo góc nhìn mới:

```text
                1
              / | \
             0  3  4
              \
               2
                \
                 5
                  \
                   6
```

Mảng theo thứ tự đỉnh 0..6:

```text
parent       = [1,-1,0,1,1,2,5]
depth        = [1,0,2,1,1,3,4]
distance     = [3,0,8,4,-2,8,15]
subtreeSize  = [4,7,3,1,1,2,1]
preorder     = [1,0,2,5,6,3,4]
```

Để kiểm tra:

- Từ gốc 1 đi tới 4 qua cạnh 1–4 trọng số −2, nên `dist[4]=−2`.
- Từ 1 tới 6 đi qua 1–0–2–5–6, tổng `3+5+0+7=15`, số cạnh là 4.
- Gốc mới 1 có `size[1]=7`, vì cây con của gốc luôn chứa toàn bộ cây.
- Cây con của 0 dưới gốc 1 gồm {0,2,5,6}, kích thước 4, không còn chứa 1,3,4.
- Cây con của 2 vẫn là {2,5,6}, kích thước 3.

**Đổi gốc không đổi tổng trọng số trên đường đơn giữa một cặp đỉnh cố định.** Ví dụ đường 3→4 qua 3–1–4 có tổng `4+(−2)=2` dưới mọi gốc. Chỉ giá trị dist từ **gốc được chọn** tới các đỉnh thay đổi.

### 7.1. Thay gốc không được chỉ đổi parent[root]

Khi đổi root từ 0 sang 1, phải tính lại parent, depth, dist và size theo cấu trúc mới, hoặc dùng một công thức **reroot DP** đã được chứng minh. Chỉ sửa parent[1]=−1 mà giữ mảng size cũ sẽ gây các truy vấn cây con và tổ tiên sai.

### 7.2. Kích thước cây con ở hai phía của một cạnh

Với gốc r đang xét, cho cạnh cha–con (u,v), trong đó u là cha của v. Cắt cạnh này chia cây thành hai thành phần:

- Phía chứa v có đúng `size[v]` đỉnh.
- Phía chứa u có đúng `n−size[v]` đỉnh.

Đây là tính chất mạnh dùng khi đếm cặp, phân tích tác động xóa cạnh và tính lại tổng khoảng cách khi đổi gốc.

Ví dụ gốc 0, cạnh 0–1:

```text
size[1] = 3
n-size[1] = 7-3 = 4

Xóa cạnh 0--1:
Phía 1: {1,3,4}
Phía 0: {0,2,5,6}
```

Số cặp đỉnh không thứ tự bị tách bởi cạnh ấy là:

```text
size[1] * (n-size[1]) = 3 * 4 = 12
```

Trong Java, nếu n lớn, phép nhân hai `int` có thể vượt int dù mỗi size nằm trong int; ép sang long **trước khi nhân**:

```java
long separatedPairs =
        (long) size[child] * (n - size[child]);
```

## 8. Một mở rộng hữu ích: tổng khoảng cách tới tất cả đỉnh khi đổi gốc

Đây là ứng dụng trực tiếp của `subtreeSize`.

Giả sử cần tính:

```text
S[r] = SUM(distance_simple_path(r, v))
       trên mọi đỉnh v của cây
```

Khi đã biết S[r] tại một gốc r, nếu chuyển gốc từ cha u sang con v qua cạnh trọng số w, mọi đỉnh ở cây con v **gần v hơn u đúng w**; các đỉnh ngoài cây con v **xa v hơn u đúng w**.

Có `size[v]` đỉnh ở phía v và `n−size[v]` đỉnh ở phía u. Suy ra:

```text
S[v] = S[u]
     - size[v] * w
     + (n-size[v]) * w

     = S[u] + (n - 2*size[v]) * w
```

Đây là công thức **rerooting** nổi tiếng cho tổng khoảng cách trên cây có trọng số, với “khoảng cách” được hiểu là **tổng trọng số đường đơn**, kể cả khi trọng số âm.

**Điều kiện số học:** Với n lớn và w lớn, tích `(n−2*size[v])*w` có thể vượt long. Dùng Math.multiplyExact/Math.addExact hoặc BigInteger khi cần. Không để tràn số làm hỏng kết quả.

### Ví dụ không trọng số

Với đường 0–1–2–3, mọi cạnh trọng số 1:

```text
S[0] = 0+1+2+3 = 6
size[1] = 3, n = 4

S[1] = 6 + (4-2*3)*1 = 4
```

Kiểm tra trực tiếp từ 1: `1+0+1+2=4`.

**Đừng nhầm rerooting với việc đổi gốc mà không tính lại đại lượng.** Công thức được chứng minh cho **tổng khoảng cách tới mọi đỉnh**; không thể tự suy ra một công thức cùng dạng cho bài tối ưu khác nếu không kiểm tra cách mỗi giá trị thay đổi khi đi qua cạnh.

## 9. Chứng minh tính đúng

### 9.1. Tính đúng của parent, depth và dist

**Bất biến:** Khi phát hiện một đỉnh v lần đầu từ đỉnh u đã xử lý/đã phát hiện trên cây, ta đặt parent[v]=u và điền depth, dist bằng công thức cha→con.

Cơ sở: root có parent=−1, depth=0, dist=0 đúng theo định nghĩa.

Bước quy nạp: Do đồ thị là **cây**, có đúng một đường đơn từ r tới v. Nếu v được gặp lần đầu qua cạnh u–v, đường duy nhất ấy có đoạn từ r tới u, rồi cạnh u–v. Vì vậy:

```text
depth[v] = depth[u] + 1
dist[v]  = dist[u] + weight(u,v)
```

Nếu giá trị ở u đã đúng, các giá trị mới ở v cũng đúng. Mỗi đỉnh được phát hiện đúng một lần nên không có đường ứng viên thay thế gây nhập nhằng.

### 9.2. Tính đúng của kích thước cây con

Với lá v, không có con, nên size[v]=1 chính xác.

Giả sử các cây con của mọi con trực tiếp c của u đã được tính đúng. Vì các cây con con không giao nhau và hợp cùng u tạo toàn bộ cây con u:

```text
size[u] = 1 + SUM(size[c])
```

Lượt duyệt ngược đảm bảo xử lý mỗi c **trước u**, nên khi cộng size[u] đã có đủ đóng góp từ các con. Quy nạp từ lá lên gốc cho thấy tất cả kích thước đúng.

### 9.3. Tính đúng của khoảng DFS preorder

DFS xử lý u trước và **xong toàn bộ các nhánh con của u** trước khi chuyển sang đỉnh ngoài cây con u. Do đó các đỉnh trong cây con u nằm liên tiếp. Vì có đúng size[u] đỉnh và u xuất hiện tại pos[u], đoạn là `[pos[u],pos[u]+size[u])`.

Với u là tổ tiên của v, v thuộc chính đoạn ấy. Với u không phải tổ tiên của v, v nằm ở một nhánh khác và không thuộc đoạn ấy. Điều kiện so sánh vị trí vì vậy đúng.

### 9.4. Phát hiện input không phải cây

Code kiểm tra n−1 cạnh (với n≥1), không có self-loop và chỉ số hợp lệ, rồi DFS từ root. Nếu gặp một hàng xóm đã được phát hiện mà không phải parent, input có chu trình/cạnh song song; không thỏa cây đơn. Nếu không thăm đủ n đỉnh, đồ thị không liên thông; cũng không thỏa cây.

Khi các phép kiểm tra đều vượt qua, ta có n đỉnh, n−1 cạnh, đã tới đủ n đỉnh và không có chu trình, nên đầu vào là cây và các công thức trên được áp dụng chính xác.

### 9.5. Thuật toán kết thúc

Mỗi đỉnh chỉ được đưa vào stack một lần vì `seen[v]` được đánh dấu ngay khi phát hiện. Stack có hữu hạn tối đa n đỉnh chờ xử lý, mỗi cạnh được xem trong danh sách kề hữu hạn. Lượt duyệt ngược là vòng lặp n−1 phần tử. Vì vậy thuật toán kết thúc.

## 10. Độ phức tạp

Gọi n là số đỉnh, m là số cạnh. Với cây n≥1, `m=n−1`.

- Dựng danh sách kề hai chiều: O(n+m) thời gian, O(n+m) bộ nhớ.
- DFS/BFS duyệt tất cả đỉnh và mỗi cạnh vô hướng hai lần: O(n+m).
- Duyệt `order` từ sau lên để tính size: O(n).
- Tính `pos[v]` trong lúc duyệt DFS: O(n).
- Truy vấn `depth[v]`, `dist[v]`, `size[v]`, `parent[v]` và kiểm tra tổ tiên theo `pos,size`: **O(1)**.
- Trả về **danh sách tất cả đỉnh trong cây con v** theo đoạn preorder mất O(size[v]) vì phải sao chép/đọc size[v] đỉnh.

**Nếu không sắp danh sách kề:** Trên cây, toàn bộ tiền xử lý có thời gian và bộ nhớ **O(n)**.

**Trong mã Java bên dưới**, mỗi danh sách kề được **sắp theo chỉ số hàng xóm tăng** để preorder/stdout xác định. Bước sắp chi phí:

```text
O(SUM_v degree(v) * log(degree(v)+1))
    <= O(n log n)
```

Vì vậy thời gian toàn bộ chương trình tiền xử lý có cận trên **O(n log n)**, còn lõi duyệt + tính kích thước vẫn **O(n)**. Bộ nhớ **O(n)** trên cây, gồm adjacency, stack, parent, depth, distance, size, preorder và position.

**Không nhầm độ sâu với độ phức tạp:** Cây dây có độ sâu n−1 nhưng DFS lặp vẫn đi qua đúng n đỉnh và n−1 cạnh, nghĩa là O(n) thời gian duyệt; khác biệt là đệ quy có thể tràn call stack, còn DFS lặp dùng stack cấu trúc dữ liệu.

## 11. Java 17+: chương trình hoàn chỉnh, có kiểm tra đầu vào

Chương trình sử dụng **cây vô hướng có trọng số kiểu long**. Mỗi cạnh lưu hai đầu và một trọng số:

```java
record Edge(int u, int v, long weight) {}
```

Kết quả có các mảng:

```text
parent[v]      - cha trong cây có gốc, root có -1
depth[v]       - số cạnh từ root tới v
distance[v]    - tổng trọng số trên đường đơn root->v
subtreeSize[v] - số đỉnh thuộc cây con gốc tại v
preorder[i]    - đỉnh thứ i của DFS preorder
position[v]    - chỉ số xuất hiện của v trong preorder
```

Hai truy vấn bổ sung:

- `isAncestor(u,v)`: dùng đoạn preorder, tính cả u=v.
- `subtreeVertices(u)`: sao chép đoạn preorder chứa mọi đỉnh cây con của u theo thứ tự DFS.

**Chính sách n=0:** Về mặt toán học, một số tài liệu chỉ gọi cây khi n≥1. Để hàm thuần nhất với tập dữ liệu, code cho phép **cây rỗng theo quy ước API** khi n=0, danh sách cạnh rỗng và `root=-1`; khi đó mọi mảng kết quả đều rỗng. Với n≥1, root phải thuộc 0..n−1.

**Chính sách trọng số:** Cho phép long âm, 0 hoặc dương; distance là tổng trọng số đường đơn. Mọi phép cộng tích lũy dùng `Math.addExact`; nếu không biểu diễn được thì ném ArithmeticException, không trả kết quả bị tràn. Đối với bài yêu cầu khoảng cách metric, có thể thêm điều kiện weight≥0 trước khi dựng cây.

**Chính sách thứ tự:** Sắp adjacency theo chỉ số đỉnh đích tăng, rồi đẩy các con lên stack theo thứ tự **giảm** để khi lấy LIFO sẽ duyệt chỉ số **tăng**. Điều này đảm bảo output preorder ổn định, đồng thời giữ trọn từng cây con trong một đoạn liên tục.

Lưu thành tệp **`TreeRootMetricsDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class TreeRootMetricsDemo {
    record Edge(int u, int v, long weight) {}
    record Arc(int to, long weight) {}

    record TreeReport(
            int root,
            int[] parent,
            int[] depth,
            long[] distance,
            int[] subtreeSize,
            int[] preorder,
            int[] position) {

        private void checkVertex(int vertex) {
            if (vertex < 0 || vertex >= parent.length) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
        }

        // "To tien" bao gom truong hop u == v.
        boolean isAncestor(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            return position[u] <= position[v]
                    && position[v] < position[u]
                                         + subtreeSize[u];
        }

        // Doan lien tiep cua cay con trong DFS preorder.
        int[] subtreeVertices(int vertex) {
            checkVertex(vertex);
            int from = position[vertex];
            return Arrays.copyOfRange(
                    preorder, from, from + subtreeSize[vertex]);
        }
    }

    static TreeReport analyze(
            int n, List<Edge> edges, int root) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "n must be nonnegative");
        }
        Objects.requireNonNull(
                edges, "edges must not be null");

        if (n == 0) {
            if (root != -1) {
                throw new IllegalArgumentException(
                        "empty tree must use root -1");
            }
            if (!edges.isEmpty()) {
                throw new IllegalArgumentException(
                        "empty tree has no edges");
            }
            return new TreeReport(
                    -1, new int[0], new int[0],
                    new long[0], new int[0],
                    new int[0], new int[0]);
        }

        if (root < 0 || root >= n) {
            throw new IllegalArgumentException(
                    "root out of range");
        }
        if (edges.size() != n - 1) {
            throw new IllegalArgumentException(
                    "tree must have n - 1 edges");
        }

        List<List<Arc>> adj = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            adj.add(new ArrayList<>());
        }

        for (Edge e : edges) {
            Objects.requireNonNull(
                    e, "edge must not be null");

            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
            if (e.u() == e.v()) {
                throw new IllegalArgumentException(
                        "self-loop is not allowed");
            }

            adj.get(e.u()).add(
                    new Arc(e.v(), e.weight()));
            adj.get(e.v()).add(
                    new Arc(e.u(), e.weight()));
        }

        // Co dinh thu tu DFS khi co nhieu con.
        for (List<Arc> neighbors : adj) {
            neighbors.sort(
                    Comparator.comparingInt(Arc::to));
        }

        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        int[] depth = new int[n];
        long[] distance = new long[n];
        int[] preorder = new int[n];
        int[] position = new int[n];
        boolean[] seen = new boolean[n];

        ArrayDeque<Integer> stack = new ArrayDeque<>();
        seen[root] = true;
        stack.push(root);

        int count = 0;

        while (!stack.isEmpty()) {
            int u = stack.pop();
            position[u] = count;
            preorder[count++] = u;

            List<Arc> neighbors = adj.get(u);

            // Push nguoc: khi pop se xu ly
            // hang xom co chi so nho truoc.
            for (int i = neighbors.size() - 1; i >= 0; i--) {
                Arc a = neighbors.get(i);
                int v = a.to();

                if (v == parent[u]) {
                    continue; // canh nguoc ve cha
                }
                if (seen[v]) {
                    throw new IllegalArgumentException(
                            "cycle detected");
                }

                seen[v] = true;
                parent[v] = u;
                depth[v] = Math.addExact(depth[u], 1);
                distance[v] = Math.addExact(
                        distance[u], a.weight());
                stack.push(v);
            }
        }

        if (count != n) {
            throw new IllegalArgumentException(
                    "graph is disconnected");
        }

        int[] subtreeSize = new int[n];
        Arrays.fill(subtreeSize, 1);

        // Cha luon xuat hien truoc con trong preorder.
        // Duyet nguoc de don toan bo cay con len cha.
        for (int i = n - 1; i > 0; i--) {
            int u = preorder[i];
            int p = parent[u];
            subtreeSize[p] = Math.addExact(
                    subtreeSize[p], subtreeSize[u]);
        }

        return new TreeReport(
                root, parent, depth, distance,
                subtreeSize, preorder, position);
    }

    static void show(
            String title, int n, List<Edge> edges, int root) {
        TreeReport r = analyze(n, edges, root);
        System.out.println(title
                + ": parent=" + Arrays.toString(r.parent())
                + ", depth=" + Arrays.toString(r.depth())
                + ", distance=" + Arrays.toString(r.distance())
                + ", subtree=" + Arrays.toString(r.subtreeSize())
                + ", preorder=" + Arrays.toString(r.preorder()));
    }

    public static void main(String[] args) {
        List<Edge> weighted = List.of(
                new Edge(0, 1, 3),
                new Edge(0, 2, 5),
                new Edge(1, 3, 4),
                new Edge(1, 4, -2),
                new Edge(2, 5, 0),
                new Edge(5, 6, 7));

        TreeReport root0 = analyze(7, weighted, 0);
        show("Root 0", 7, weighted, 0);
        System.out.println(
                "Root 0: subtree(1)=" + Arrays.toString(
                        root0.subtreeVertices(1))
                + ", subtree(2)=" + Arrays.toString(
                        root0.subtreeVertices(2)));
        System.out.println(
                "Root 0: ancestor(1,4)="
                        + root0.isAncestor(1, 4)
                + ", ancestor(1,6)="
                        + root0.isAncestor(1, 6));

        show("Root 1", 7, weighted, 1);

        show("Chain", 4, List.of(
                new Edge(0, 1, 2),
                new Edge(1, 2, 0),
                new Edge(2, 3, 9)), 0);

        show("Star root 2", 5, List.of(
                new Edge(2, 0, 1),
                new Edge(2, 1, 2),
                new Edge(2, 3, 3),
                new Edge(2, 4, 4)), 2);

        show("Single", 1, List.of(), 0);
        show("Empty", 0, List.of(), -1);

        try {
            analyze(4, List.of(
                    new Edge(0, 1, 1),
                    new Edge(1, 2, 1)), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad count: " + ex.getMessage());
        }

        try {
            analyze(4, List.of(
                    new Edge(0, 1, 1),
                    new Edge(1, 2, 1),
                    new Edge(2, 0, 1)), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Cycle: " + ex.getMessage());
        }

        try {
            analyze(2, List.of(
                    new Edge(0, 0, 1)), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Self-loop: " + ex.getMessage());
        }

        try {
            analyze(2, List.of(
                    new Edge(0, 2, 1)), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad endpoint: " + ex.getMessage());
        }

        try {
            analyze(2, List.of(
                    new Edge(0, 1, 1)), 2);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad root: " + ex.getMessage());
        }

        try {
            analyze(3, List.of(
                    new Edge(0, 1, Long.MAX_VALUE),
                    new Edge(1, 2, 1)), 0);
        } catch (ArithmeticException ex) {
            System.out.println(
                    "Overflow: " + ex.getMessage());
        }

        try {
            analyze(0, List.of(), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad empty root: " + ex.getMessage());
        }

        try {
            analyze(3, List.of(
                    new Edge(0, 1, 1),
                    new Edge(0, 1, 2)), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Duplicate edge: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac TreeRootMetricsDemo.java
java TreeRootMetricsDemo
```

**Stdout chính xác:**

```text
Root 0: parent=[-1, 0, 0, 1, 1, 2, 5], depth=[0, 1, 1, 2, 2, 2, 3], distance=[0, 3, 5, 7, 1, 5, 12], subtree=[7, 3, 3, 1, 1, 2, 1], preorder=[0, 1, 3, 4, 2, 5, 6]
Root 0: subtree(1)=[1, 3, 4], subtree(2)=[2, 5, 6]
Root 0: ancestor(1,4)=true, ancestor(1,6)=false
Root 1: parent=[1, -1, 0, 1, 1, 2, 5], depth=[1, 0, 2, 1, 1, 3, 4], distance=[3, 0, 8, 4, -2, 8, 15], subtree=[4, 7, 3, 1, 1, 2, 1], preorder=[1, 0, 2, 5, 6, 3, 4]
Chain: parent=[-1, 0, 1, 2], depth=[0, 1, 2, 3], distance=[0, 2, 2, 11], subtree=[4, 3, 2, 1], preorder=[0, 1, 2, 3]
Star root 2: parent=[2, 2, -1, 2, 2], depth=[1, 1, 0, 1, 1], distance=[1, 2, 0, 3, 4], subtree=[1, 1, 5, 1, 1], preorder=[2, 0, 1, 3, 4]
Single: parent=[-1], depth=[0], distance=[0], subtree=[1], preorder=[0]
Empty: parent=[], depth=[], distance=[], subtree=[], preorder=[]
Bad count: tree must have n - 1 edges
Cycle: cycle detected
Self-loop: self-loop is not allowed
Bad endpoint: vertex index out of range
Bad root: root out of range
Overflow: long overflow
Bad empty root: empty tree must use root -1
Duplicate edge: cycle detected
```

### 11.1. Giải thích các kết quả kiểm thử

**Root 0:** parent, depth và distance khớp bảng ở phần 3. Khi duyệt DFS hàng xóm tăng dần, preorder là [0,1,3,4,2,5,6], nên `subtree(1)=[1,3,4]` và `subtree(2)=[2,5,6]` là các đoạn liên tiếp.

**Root 1:** Thay gốc làm `subtreeSize[0]` giảm từ 7 xuống 4, `subtreeSize[1]` tăng từ 3 lên 7; `distance[4]` thành −2 vì cạnh trực tiếp 1–4 âm. Mọi mảng vẫn tính trên **cùng sáu cạnh ban đầu**.

**Chain:** Đường 0–1–2–3 có độ sâu tăng 0,1,2,3 và kích thước giảm 4,3,2,1. Cạnh 1–2 trọng số 0 nên `dist[1]=dist[2]=2` dù độ sâu tăng thêm 1.

**Star root 2:** Gốc là tâm 2 có bốn con trực tiếp, mọi con có depth=1 và size=1, trong khi size[2]=5. Khoảng cách từ gốc là trọng số trên từng cạnh.

**Single:** Cây một đỉnh có gốc 0, size=1, depth=0 và distance=0.

**Empty:** Theo quy ước API, n=0 dùng root=-1 và không có cạnh; mọi mảng đều rỗng. Không có truy vấn đỉnh hợp lệ trên cây rỗng.

**Bad count:** n=4 nhưng chỉ hai cạnh, không thể là cây liên thông bốn đỉnh.

**Cycle:** n=4 có ba cạnh tạo tam giác giữa 0,1,2 và đỉnh 3 cô lập. Dù số cạnh bằng n−1, vẫn không phải cây; DFS phát hiện chu trình.

**Self-loop:** Cạnh 0–0 bị từ chối, vì cây vô hướng đơn không có khuyên.

**Bad endpoint/root:** Kiểm tra chỉ số đỉnh ngoài miền, tránh truy cập mảng sai.

**Overflow:** Một đường có tổng `Long.MAX_VALUE+1` không vừa kiểu long; Math.addExact ném ArithmeticException thay vì tràn thành số âm. Khi cần tổng lớn hơn long, chuyển sang BigInteger ngay từ thiết kế.

**Bad empty root:** Không thể chọn gốc 0 nếu n=0; mã chỉ cho phép root=-1 cho input rỗng.

**Duplicate edge:** Hai bản sao của cạnh 0–1 được phát hiện là cấu trúc không phải cây đơn, không được đếm thành hai nhánh con độc lập.

### 11.2. Vì sao sort neighbors không bắt buộc cho kết quả số?

Thứ tự các hàng xóm chỉ quyết định **thứ tự DFS preorder**, không quyết định quan hệ cha–con trong một cây với gốc đã cố định: do **đường đơn từ gốc tới mỗi đỉnh là duy nhất**, cha của v vẫn phải là đỉnh ngay trước v trên đường ấy.

Vì vậy khi đổi thứ tự adjacency nhưng giữ nguyên cây và gốc:

- parent, depth, distance, subtree size **không đổi**;
- preorder và position có thể đổi;
- tính chất “mỗi cây con là một đoạn preorder” vẫn đúng nếu duyệt DFS đúng;
- đoạn thực tế ứng với cây con có thể chuyển sang vị trí mới trong preorder.

Mã sort để **stdout và ví dụ có thể đối chiếu chính xác**, không phải để làm công thức toán học đúng.

## 12. Các trường hợp biên và yêu cầu an toàn

### 12.1. Cây dây rất sâu

Độ sâu của đỉnh cuối có thể là n−1. DFS đệ quy thông thường dễ gặp StackOverflowError ở n lớn. DFS lặp với ArrayDeque tránh sử dụng Java call stack sâu theo n.

Trong cây dây n=100.000, bậc tối đa chỉ 2 và duyệt DFS O(n). Trong cây hình sao n=100.000, gốc có gần n con; stack explicit có thể chứa O(n) đỉnh chờ, nhưng vẫn nằm trong cận bộ nhớ O(n).

### 12.2. Cây có trọng số bằng 0

Nếu cạnh có w=0, `dist[child]=dist[parent]` nhưng `depth[child]=depth[parent]+1`. Không được dùng điều kiện `dist[child]>dist[parent]` để nhận biết con hoặc dùng khoảng cách để thay thế độ sâu.

### 12.3. Cây có trọng số âm

Tổng đường đơn có thể âm. Nếu ứng dụng yêu cầu “khoảng cách metric” hoặc các thuật toán dựa vào monotonicity của khoảng cách, phải xác thực các trọng số không âm.

Đặc biệt, nếu suy luận “đỉnh sâu hơn thì cách gốc xa hơn” từ `dist`, điều này sai với cạnh âm hoặc cạnh 0; ngay cả khi trọng số dương khác nhau, độ sâu không quyết định thứ tự tổng trọng số.

### 12.4. Tràn số nguyên

Độ sâu không vượt n−1 và subtree size không vượt n; với n là kích thước mảng Java kiểu int có thể cấp phát được, hai giá trị này nằm trong int.

Ngược lại, tổng trọng số trên đường có thể vượt int hoặc long. Phải chọn đúng kiểu cho `distance`. Trong mã, dùng Math.addExact cho long để lỗi miền số được phát hiện rõ.

Phép tính số cặp qua cạnh có dạng `size*(n−size)` nên cần ép long **trước nhân**, dù size vẫn là int. Với n cực lớn hoặc bài đếm nhiều cấu hình, có thể cần BigInteger.

### 12.5. Cây không liên thông: thực ra là rừng

Một **rừng** (*forest*) là đồ thị vô hướng không có chu trình nhưng **có thể nhiều thành phần**. Rừng không có một gốc duy nhất cho tất cả các đỉnh nếu không thêm các cạnh giả.

Nếu đề đưa một rừng, cần chọn **một gốc cho mỗi thành phần** và chạy thuật toán trên từng thành phần; khi đó mỗi gốc có parent=-1, depth=0, distance=0 và size bằng kích thước thành phần. Không được chạy từ một gốc rồi coi những đỉnh chưa thăm có depth=0 mặc định là đã tính xong.

**Chương trình hiện tại chỉ chấp nhận một cây** (hoặc cây rỗng theo quy ước), không tự chuyển rừng thành cây. Việc từ chối input không đủ n−1 cạnh là có chủ đích.

### 12.6. Nhiều lần đổi gốc

Với một truy vấn đổi gốc đơn lẻ, chạy lại analyze mất O(n log n) trong bản sort này, hoàn toàn hợp lý cho n vừa.

Nếu có rất nhiều truy vấn đổi gốc và chỉ cần **một đại lượng cụ thể**, có thể áp dụng công thức reroot DP, LCA và binary lifting hoặc một phép tiền xử lý để trả lời nhanh. Cần xác định rõ loại truy vấn: không có một công thức O(1) duy nhất trả đồng thời parent, depth, distance và subtreeSize của mọi đỉnh dưới mọi gốc mà không lưu thông tin thích hợp.

### 12.7. Không lẫn vị trí preorder với tên đỉnh

`position[v]` là chỉ số trong mảng `preorder`; **không** phải chỉ số đỉnh và **không** nhất thiết bằng v. Ví dụ với gốc 0:

```text
preorder = [0,1,3,4,2,5,6]
position[2] = 4
position[3] = 2
```

Nếu truy vấn cây con dùng `preorder[v..v+size[v])` thay vì `preorder[position[v]..position[v]+size[v])` thì sai khi thứ tự DFS khác thứ tự số đỉnh.

## 13. Lỗi phổ biến

1. **Đếm độ sâu từ 1 trong khi bài quy định gốc độ sâu 0.** Phải chốt quy ước.
2. **Nhầm depth với distance khi có trọng số khác 1.** Depth đếm cạnh, distance cộng trọng số.
3. **Cho lá size=0.** Nếu size tính cả chính đỉnh, lá phải size=1.
4. **Quên cộng 1 trong công thức size.** `size[v]=1+Σsize[child]`.
5. **Cộng size của cha vào con thay vì con vào cha.** Kích thước cần lan từ lá lên gốc.
6. **Tính size theo thứ tự cha trước con mà không có thông tin từ con.** Phải postorder hoặc reverse parent-before-child order.
7. **Thêm cạnh vô hướng vào adjacency một chiều.** Không thể duyệt đúng cây từ gốc tùy ý.
8. **Không bỏ cạnh quay về cha trong DFS.** Gây vòng lặp hoặc phát hiện nhầm.
9. **Không đánh dấu seen khi gặp con.** Có thể đẩy cùng một đỉnh nhiều lần nếu input sai.
10. **Cho rằng đủ n−1 cạnh là chắc chắn cây.** Có thể có chu trình ở một thành phần và đỉnh cô lập.
11. **Không kiểm tra self-loop.** Cây đơn không có cạnh u–u.
12. **Không xử lý cạnh trùng.** Có thể tạo chu trình đa cạnh hoặc tính sai size nếu đếm hai bản sao như hai con.
13. **Gọi mọi đồ thị không có chu trình là cây.** Nếu không liên thông thì là rừng, không phải một cây.
14. **Dùng BFS order để khẳng định mỗi cây con liên tiếp.** Chỉ DFS preorder chuẩn mới bảo đảm đoạn liên tiếp.
15. **Sử dụng pos[v]=v thay vì vị trí trong preorder.** Sai khi thứ tự DFS không trùng tên đỉnh.
16. **Lấy size[v] làm số hậu duệ không kể v mà không trừ 1.** Số hậu duệ thực là size[v]−1 nếu không kể v.
17. **Tưởng kích thước cây con không phụ thuộc gốc.** Đổi gốc làm đổi hướng cha–con và size.
18. **Chỉ thay root trong kết quả mà không tính lại mảng.** Parent/depth/dist/size trở nên không nhất quán.
19. **Tin rằng đỉnh sâu hơn luôn có dist lớn hơn.** Cạnh 0 hoặc âm là phản ví dụ.
20. **Coi tổng đường đơn có cạnh âm là shortest-walk distance hữu hạn.** Đi qua lại cạnh âm trong đồ thị vô hướng có thể giảm tổng vô hạn nếu cho phép lặp.
21. **Dùng int để cộng trọng số lớn.** Cần long hoặc BigInteger và kiểm soát tràn.
22. **Để phép cộng long tràn âm thầm.** Dùng Math.addExact hoặc chứng minh cận.
23. **Dùng int nhân size*(n−size).** Ép long trước nhân.
24. **Tính đường đi u↔v bằng dist[u]+dist[v] mà quên trừ hai lần dist[lca].** Đường chung từ gốc bị đếm hai lần.
25. **Dùng công thức LCA nhưng không tính toán overflow trung gian.** Có thể cần Math.addExact/BigInteger.
26. **Đệ quy trên cây dây dài mà không tính giới hạn Java stack.** Dùng DFS lặp.
27. **Lấy một nhánh con rồi nghĩ nó chứa toàn bộ các đỉnh dưới cùng độ sâu.** Cây con xác định bởi quan hệ tổ tiên, không phải bằng nhau về depth.
28. **Nhầm số cạnh trong cây con với số đỉnh.** Cây con có size[v] đỉnh thì có size[v]−1 cạnh.
29. **Cho rằng thứ tự sort neighbors ảnh hưởng kích thước hoặc khoảng cách của cây đã cố định gốc.** Nó chỉ ảnh hưởng thứ tự DFS.
30. **Không kiểm tra giới hạn root và endpoint.** Gây truy cập ngoài mảng.
31. **Quên đếm riêng gốc trong lượt cộng ngược.** Gốc không có cha, nên không thể cộng size[root] vào parent[-1].
32. **Nhầm đồ thị cây vô hướng với cây tìm kiếm nhị phân.** Cây thuật toán ở đây không yêu cầu mỗi đỉnh có nhiều nhất hai con hay khóa BST.
33. **Xem khoảng cách từ gốc là khoảng cách mọi cặp.** Muốn giữa u,v, cần đường duy nhất hoặc LCA.
34. **Dùng một tour Euler ghi đỉnh nhiều lần nhưng vẫn áp công thức size trên preorder một lần mỗi đỉnh.** Hai biểu diễn có chỉ số khác.
35. **Không chốt cách xử lý n=0.** Code có root=-1 theo quy ước; nhiều đề chỉ nhận n≥1.
36. **Sao chép ngược các mảng report ra ngoài rồi tùy ý sửa.** Mảng trong record Java là tham chiếu có thể thay đổi; nếu cần API bất biến, phải defensive copy.
37. **Không kiểm tra output trên nhiều dạng cây.** Cần test dây, sao, một đỉnh, thay gốc, cạnh 0, cạnh âm và input sai.

## 14. Bài tập có đáp án

**Bài 1.** Trong cây gốc r, định nghĩa depth[v], distance[v] và subtreeSize[v].

**Đáp án:** Depth là số cạnh r→v; distance là tổng trọng số trên đường đơn r→v; subtreeSize là số đỉnh thuộc cây con gốc tại v, kể cả v.

**Bài 2.** Với cây không trọng số, mỗi cạnh trọng số 1, quan hệ giữa depth và distance là gì?

**Đáp án:** `distance[v]=depth[v]` cho mọi đỉnh v, vì số cạnh cũng chính là tổng các trọng số 1.

**Bài 3.** Cây gốc 0 có các cạnh 0–1,0–2,1–3,1–4,2–5,5–6. Subtree size của đỉnh 1,2,5 và 0?

**Đáp án:** `size[1]=3`, `size[2]=3`, `size[5]=2` và `size[0]=7`.

**Bài 4.** Trên cây trọng số ở phần 3, depth và distance của đỉnh 4 dưới gốc 0 là bao nhiêu?

**Đáp án:** Depth=2, distance=3+(−2)=**1**. Hai đại lượng khác nhau.

**Bài 5.** Dưới gốc 0, depth[6] và distance[6]?

**Đáp án:** Depth=3; distance=5+0+7=**12**.

**Bài 6.** Nếu đổi gốc thành 1, kích thước cây con của đỉnh 0 là bao nhiêu?

**Đáp án:** Cây con của 0 gồm {0,2,5,6}, nên size[0]=**4**.

**Bài 7.** Nếu đổi gốc thành 1, khoảng cách từ gốc tới đỉnh 4 là bao nhiêu?

**Đáp án:** **−2**, vì đường đơn 1→4 là cạnh có trọng số −2.

**Bài 8.** Vì sao phải cộng kích thước từ con lên cha?

**Đáp án:** Cây con của cha là hợp của chính cha và các cây con của từng con. Phải có size con trước mới dùng `1+Σsize[child]`.

**Bài 9.** Có thể dùng BFS thay DFS để tính size không?

**Đáp án:** Có. BFS vẫn có cha xuất hiện trước con, nên duyệt ngược BFS order để cộng size được. Nhưng BFS order **không nhất thiết** gom cây con thành một đoạn liên tiếp.

**Bài 10.** Nếu preorder=[0,1,3,4,2,5,6], pos[2]=4 và size[2]=3, các đỉnh thuộc cây con 2 là gì?

**Đáp án:** Đoạn preorder[4..6]=**[2,5,6]**.

**Bài 11.** Với gốc 0, đỉnh 1 có là tổ tiên của đỉnh 6 không?

**Đáp án:** Không. `pos[1]=1,size[1]=3`, nên đoạn cây con 1 là [1,4). `pos[6]=6` nằm ngoài đoạn.

**Bài 12.** Theo quy ước trong bài, đỉnh có là tổ tiên của chính nó không?

**Đáp án:** **Có**, vì truy vấn isAncestor dùng quan hệ tổ tiên **kể cả chính đỉnh**. Nếu đề đòi tổ tiên thực sự (khác chính nó), thêm điều kiện u!=v.

**Bài 13.** Cây có n đỉnh. Subtree size của gốc bằng bao nhiêu?

**Đáp án:** **n**, vì mọi đỉnh đều nằm trong cây con của gốc.

**Bài 14.** Cây có n đỉnh, cắt cạnh cha u–con v. Hai phía có bao nhiêu đỉnh?

**Đáp án:** `size[v]` và `n−size[v]`.

**Bài 15.** Với n=7, size[v]=3, có bao nhiêu cặp không thứ tự nằm hai phía của cạnh cha–con ấy?

**Đáp án:** `3×(7−3)=12` cặp. Trong Java nên ép sang long trước khi nhân.

**Bài 16.** Một cây dây 0–1–2–3 có gốc 0, tính depth và size.

**Đáp án:** `depth=[0,1,2,3]`, `size=[4,3,2,1]`.

**Bài 17.** Một cây sao gồm n=5, gốc ở tâm. Depth và size của mỗi lá?

**Đáp án:** Mọi lá có depth=1, size=1; tâm có depth=0 và size=5.

**Bài 18.** Có n=4 đỉnh và ba cạnh tạo tam giác trong 0,1,2, còn đỉnh 3 cô lập. Có phải cây không?

**Đáp án:** Không. Dù có n−1 cạnh, đồ thị chứa chu trình và không liên thông.

**Bài 19.** Với đường 0–1–2–3 và trọng số [2,0,9], distance từ gốc 0 đến 3 là bao nhiêu?

**Đáp án:** 2+0+9=**11**, còn depth=3.

**Bài 20.** Tại sao mảng distance cần long khi trọng số là int lớn?

**Đáp án:** Tổng nhiều trọng số có thể vượt int. Tuy nhiên long cũng có giới hạn; cần Math.addExact/BigInteger hoặc chứng minh cận của tổng.

**Bài 21.** Nếu một cây có cạnh trọng số âm, dist[root→v] có còn là shortest-walk distance không?

**Đáp án:** Không nhất thiết. Đây là tổng của **đường đơn duy nhất**. Một walk có thể lặp cạnh âm hai chiều và giảm chi phí không bị chặn dưới; không nên dùng ý nghĩa shortest walk nếu cho phép lặp cạnh.

**Bài 22.** Dùng công thức reroot để tính tổng khoảng cách của mọi đỉnh khi đổi gốc từ u sang con v với trọng số w.

**Đáp án:** `S[v]=S[u]+(n−2*size[v])*w`, với size[v] được tính theo gốc hiện tại mà u là cha của v. Sử dụng kiểu số đủ miền cho nhân/cộng.

**Bài 23.** Trên đường 0–1–2–3 không trọng số, S[0]=6 và size[1]=3. S[1] bằng bao nhiêu?

**Đáp án:** `6+(4−2×3)×1=4`.

**Bài 24.** Tại sao thứ tự DFS dùng để flatten cây con phải đi hết nhánh trước khi chuyển anh em?

**Đáp án:** Vì chỉ khi các hậu duệ của mỗi đỉnh xuất hiện liên tiếp mới có thể biểu diễn cây con bằng đoạn `[pos[v],pos[v]+size[v])`. BFS theo tầng có thể xen các nhánh khác.

**Bài 25.** Với một cây rỗng n=0, code dùng root nào và trả gì?

**Đáp án:** Theo quy ước của API, root=−1 và danh sách cạnh rỗng; trả các mảng rỗng. Nhiều định nghĩa toán học chỉ nhận cây n≥1, nên cần xem yêu cầu đề.

**Bài 26.** Nếu cần truy vấn tổng giá trị từng cây con và cập nhật giá trị một đỉnh nhiều lần, làm cách nào?

**Đáp án:** Dùng preorder DFS để flatten `flat[pos[v]]=value[v]`. Cây con v ứng với đoạn liên tiếp; dùng Fenwick tree hoặc segment tree để cập nhật điểm và lấy tổng đoạn nhanh.

## 15. Ghi nhớ nhanh

| Câu hỏi | Công thức hoặc cấu trúc |
| --- | --- |
| Gốc | `parent[r]=−1, depth[r]=0, dist[r]=0` |
| Độ sâu | `depth[v]=depth[parent[v]]+1` |
| Tổng trọng số từ gốc | `dist[v]=dist[parent[v]]+w(parent[v],v)` |
| Kích thước cây con | `size[v]=1+Σsize[child]` |
| Lá | `size[leaf]=1` |
| Kích thước cây con của gốc | `size[root]=n` |
| Vùng DFS của cây con | `[pos[v],pos[v]+size[v])` trong preorder |
| Kiểm tra tổ tiên u→v | `pos[u]≤pos[v]<pos[u]+size[u]` |
| Xóa cạnh cha–con | Hai phía có `size[child]` và `n−size[child]` đỉnh |
| Số cặp bị tách qua cạnh | `size[child]×(n−size[child])` |
| Reroot tổng khoảng cách | `S[v]=S[u]+(n−2size[v])×w(u,v)` |
| Tiền xử lý không sort | O(n) trên cây với danh sách kề |
| Tiền xử lý có sort neighbors | O(n log n) cận trên, O(n) bộ nhớ |
| Cây rất sâu | DFS lặp tránh tràn Java call stack |
| Tổng trọng số có thể lớn | long+Math.addExact hoặc BigInteger |

## Kết luận

Ba đại lượng **kích thước cây con, độ sâu và khoảng cách từ gốc** đều bắt đầu từ việc chọn **một gốc rõ ràng** rồi định hướng các cạnh vô hướng theo cha–con. Khi duyệt từ gốc ra ngoài, đặt:

```text
depth[root] = 0
distance[root] = 0

depth[child] = depth[parent] + 1
distance[child] = distance[parent] + weight
```

Khi duyệt ngược từ lá lên cha, đặt:

```text
size[v] = 1 + SUM(size[child])
```

Sắp xếp các đỉnh theo **DFS preorder** còn cho phép biến mọi cây con thành **một đoạn mảng liên tiếp**, từ đó kiểm tra tổ tiên, truy vấn tổng và áp dụng Fenwick/segment tree hiệu quả. Các công thức hoạt động đúng vì cây có **duy nhất một đường đi đơn giữa hai đỉnh** và các cây con của các con trực tiếp không giao nhau.

Trước khi áp dụng, hãy kiểm tra đồ thị thực sự là cây, phân biệt depth với tổng trọng số, nói rõ quy ước kích thước **tính cả đỉnh**, thay gốc thì tính lại hoặc dùng reroot DP đã chứng minh, và kiểm soát tràn số nếu trọng số lớn. Đây là bộ công cụ nền tảng để học sâu các thuật toán trên cây phức tạp hơn.
