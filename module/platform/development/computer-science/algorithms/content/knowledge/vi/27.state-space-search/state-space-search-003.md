# Tìm kiếm theo chiều rộng khi mọi bước có cùng chi phí

## 1. Tình huống và mục tiêu

Trong bài toán **tìm kiếm trạng thái (state-space search)**, mỗi cấu hình hợp lệ được xem là một trạng thái. Ta được phép thực hiện các thao tác để chuyển từ trạng thái hiện tại sang trạng thái kế tiếp và cần tìm cách đạt mục tiêu bằng **ít thao tác nhất**.

Ví dụ: từ số nguyên `x` được làm một trong ba phép:

```text
x -> x - 1
x -> x + 1
x -> 2*x
```

Chỉ chấp nhận các số trong `[0,20]` và cấm hai trạng thái `6,8`. Từ `3` đến `11`, một lời giải ngắn nhất là:

```text
3 -> 4 -> 5 -> 10 -> 11
     +1   +1   *2   +1

Số thao tác: 4.
```

Khi **mỗi thao tác hợp lệ đều tốn một đơn vị chi phí**, bài toán trở thành tìm **đường đi ít cạnh nhất trong đồ thị không trọng số**. Thuật toán phù hợp là **BFS — Breadth-First Search (tìm kiếm theo chiều rộng)**.

BFS không thử tất cả chuỗi thao tác theo kiểu vét cạn rồi so kết quả. Nó khám phá các trạng thái theo **lớp khoảng cách**: 0 bước, 1 bước, 2 bước, ... Do đó trạng thái đích được phát hiện lần đầu sẽ có số bước nhỏ nhất.

Mục tiêu sau bài học: hiểu cách dựng đồ thị trạng thái ngầm định, chứng minh BFS tối ưu khi các bước đồng chi phí, xử lý hàng đợi FIFO, visited, parent, trạng thái cấm và vòng lặp, phân biệt BFS một nguồn với nhiều nguồn, ứng dụng trên lưới và biết khi nào phải chuyển sang 0–1 BFS hoặc Dijkstra. Một chương trình Java 17+ chạy độc lập sẽ có output cụ thể và kiểm thử đối chứng bằng thuật toán Floyd–Warshall.

## 2. Mô hình hóa thành đồ thị trạng thái

Gọi `S` là tập trạng thái hợp lệ. Mỗi trạng thái `u\in S` được xem là một đỉnh. Nếu từ `u` có thể thực hiện **một thao tác được phép** để đạt `v`, ta đặt một cung:

\[
u\longrightarrow v.
\]

Một chuỗi thao tác tương đương với đường đi:

\[
s=x_0\to x_1\to\cdots\to x_k=t,
\]

có đúng `k` cung, tức `k` bước.

### 2.1. Cung có thể có hướng

Nếu bài cho phép thao tác `x\to2x`, không được tự kết luận `2x\to x` bằng phép chia là một thao tác hợp lệ. Có thể có thao tác `-1` nên từ một vài trạng thái vẫn quay về được, nhưng tính hai chiều phải xét **từng quy tắc**.

Ví dụ với chỉ một quy tắc `x\to2x`:

```text
2 -> 4 -> 8
```

Có đường từ `2` đến `8`, nhưng không nhất thiết có đường từ `8` về `2`. Khi viết hàm sinh hàng xóm, chỉ tạo những cung mà đề bài thực sự cho phép.

### 2.2. Ít bước khác ít chi phí như thế nào?

Nếu mọi bước đều có chi phí cố định `c>0` thì đường gồm `k` bước có tổng:

\[
Cost(P)=c\,k.
\]

Nhờ `c>0`:

\[
k_1<k_2\iff ck_1<ck_2.
\]

Vì vậy đường ít bước nhất cũng là đường có **tổng chi phí nhỏ nhất**. Với `c=1`, đáp án chi phí chính là khoảng cách BFS.

Tuy nhiên:

- Nếu `c=0`, mọi đường đi hữu hạn đều có tổng chi phí `0`; BFS vẫn trả một đường ít bước nhất, và đó cũng là một nghiệm có chi phí tối thiểu, nhưng không có sự tương đương nghiêm ngặt giữa thứ tự số bước và chi phí.
- Nếu `c<0`, đường nhiều bước hơn có thể có chi phí thấp hơn; đi vòng qua chu trình âm có thể làm chi phí giảm không giới hạn nếu bài cho phép walk lặp. **Không dùng BFS để tối thiểu hóa tổng chi phí âm chỉ vì mọi cạnh đều bằng nhau.**
- Nếu chi phí các thao tác khác nhau, BFS FIFO chỉ tối ưu **số bước**, không tự tối ưu tổng trọng số.

**Điều kiện dùng BFS trong chủ đề này:** bài yêu cầu **ít bước nhất**, hoặc yêu cầu tối thiểu hóa chi phí và **mọi bước có cùng chi phí dương**.

## 3. Đồ thị tường minh và đồ thị ngầm định

Trong đồ thị tường minh, ta có thể đọc sẵn danh sách cạnh `adj[u]` rồi BFS. Trong **đồ thị trạng thái ngầm định**, đề chỉ cung cấp hàm sinh hàng xóm:

```text
nextStates(u):
    trả mọi trạng thái v có thể đạt từ u bằng đúng 1 thao tác
```

Ví dụ với miền `0..20`:

```text
nextStates(5) về mặt giá trị:
    4  (trừ 1)
    6  (cộng 1)
    10 (nhân 2)
```

Nếu `6` bị cấm, ứng viên `6` bị loại trước khi đưa vào hàng đợi.

Không cần dựng toàn bộ đồ thị trước. Khi lấy `u` khỏi queue, chương trình mới sinh các hàng xóm của `u`. Điều này hữu ích khi tập trạng thái rất lớn nhưng số trạng thái thật sự tới được ít.

### 3.1. Mô hình trạng thái phải đủ thông tin

Trong mê cung có chìa khóa, `(row,col)` có thể chưa đủ:

- Đến ô `(r,c)` khi chưa có chìa khóa: không mở được cửa.
- Đến cùng ô `(r,c)` khi đã có chìa khóa: có thể đi qua cửa.

Phải dùng:

\[
state=(r,c,hasKey)
\]

hoặc `(r,c,keyMask)` nếu có nhiều chìa khóa.

Tương tự, trạng thái có thể cần chứa năng lượng còn lại, số lượt dùng phép đặc biệt, hướng di chuyển, hoặc bitmask các nhiệm vụ đã hoàn thành. **Chỉ được gộp hai trạng thái nếu những khả năng chuyển tiếp và điều kiện đích của chúng tương đương theo bài toán.**

### 3.2. Giới hạn miền hợp lệ là một phần bài toán

Với biến đổi số nguyên, phép nhân `2` có thể tạo vô hạn trạng thái nếu không có giới hạn. Cần miền hữu hạn do đề cho, hoặc phải chứng minh một ngưỡng đủ chứa mọi lời giải tối ưu.

Không được tự đặt `MAX=1000` rồi kết luận không có lời giải khi BFS không tìm thấy đích: một lời giải ngắn nhất có thể cần đi vượt đích rồi quay lại.

Trong ví dụ Java, miền `0..MAX` **được quy định ngay trong bài toán minh họa** và `MAX\le1\,000\,000` là giới hạn cấp phát của chương trình, không phải định lý rằng mọi bài biến đổi số đều có thể chặn tại mức này.

## 4. BFS bằng queue FIFO

BFS dùng hàng đợi **First In, First Out (FIFO)**. Ta lưu:

- `distance[u]`: số bước nhỏ nhất từ nguồn tới `u` nếu đã phát hiện; `-1` nếu chưa.
- `parent[u]`: trạng thái trước `u` trên một đường ngắn nhất, dùng khi cần truy vết.
- `queue`: các trạng thái đã phát hiện và chờ mở rộng hàng xóm.

Có thể dùng `distance[u]!=-1` thay cho mảng `visited` riêng.

Pseudocode:

```text
distance[*] = -1
parent[*] = -1
distance[start] = 0
queue.push_back(start)

while queue not empty:
    u = queue.pop_front()

    if u == goal:
        return distance[u], reverse(parent chain from goal)

    for each v in nextStates(u):
        if v invalid or forbidden:
            continue
        if distance[v] != -1:
            continue

        distance[v] = distance[u] + 1
        parent[v] = u
        queue.push_back(v)

return UNREACHABLE
```

**Quy tắc quan trọng nhất:** đánh dấu trạng thái đã phát hiện **ngay lúc enqueue**.

### 4.1. Vì sao không chờ đến lúc dequeue mới visited?

Giả sử `a` và `b` cùng dẫn đến `c`. Nếu `c` chưa được đánh dấu khi thêm vào queue, cả `a` lẫn `b` có thể thêm `c`, gây trùng lặp. Trong đồ thị nhiều cung và chu trình, số bản sao có thể rất lớn. Nếu còn ghi đè `parent[c]`, đường truy vết cũng có thể trở nên không nhất quán.

Đặt `distance[c]` ngay lần phát hiện đầu sẽ chặn mọi lần enqueue sau.

### 4.2. Vòng lặp và phép biến đổi trùng

Với phép `x\to2x`, trạng thái `0` sinh lại `0`. Phép `+1` và `-1` tạo chu trình hai cung như `4\to5\to4`. Hai phép khác nhau đôi khi còn sinh cùng một giá trị, ví dụ `1+1=2` và `1\times2=2`.

Nếu không có visited, BFS có thể lặp mãi hoặc xử lý nhiều bản sao. Với `distance[u]!=-1`, một trạng thái được enqueue tối đa một lần, bất kể bao nhiêu thao tác dẫn đến nó.

### 4.3. Dừng sớm như thế nào?

Nếu chỉ cần **một đích cố định**, có thể dừng khi:

1. **Lấy đích ra khỏi queue**, hoặc
2. **Đưa đích vào queue lần đầu**, sau khi đã gán `distance` và `parent`.

Cả hai đều cho khoảng cách nhỏ nhất. Chương trình Java dùng cách 1 vì dễ nhìn thấy invariant.

Nếu cần **mọi khoảng cách** hoặc **đếm tất cả đường ngắn nhất**, không nên dừng ngay khi phát hiện một đích: có thể còn những đường khác cùng số bước chưa được xét.

## 5. Chứng minh BFS tối ưu số bước

Gọi `d^*(v)` là số cung ít nhất trên một đường từ `s` tới `v`, hoặc `\infty` nếu không có đường.

### 5.1. Bất biến duyệt theo lớp

BFS lấy trạng thái ra khỏi queue theo thứ tự **không giảm `distance`**.

- Ban đầu queue chỉ chứa `s` ở lớp `0`.
- Khi lấy đỉnh `u` lớp `k`, mọi đỉnh mới sinh từ nó được gán lớp `k+1` và đưa vào **cuối queue**.
- Các đỉnh đã được đưa vào trước có lớp không lớn hơn `k+1`.

Vì vậy không thể lấy một đỉnh lớp `k+2` trước khi duyệt xong các đỉnh thuộc lớp thấp hơn cần xét.

### 5.2. Lần phát hiện đầu tiên có khoảng cách đúng

Giả sử `v` được phát hiện từ `u` với `distance[v]=k`, nhưng thực tế có một đường `s\to v` chỉ `j<k` bước.

Gọi `p` là đỉnh đứng ngay trước `v` trên đường ngắn hơn. Khi ấy `p` ở lớp không vượt `j-1<k-1`. Theo bất biến lớp, BFS đã phải xử lý `p` và phát hiện `v` trước khi phát hiện `v` từ `u` ở lớp `k`. Mâu thuẫn.

Do đó:

\[
\boxed{distance[v]=d^*(v)}
\]

ngay khi `v` được phát hiện lần đầu.

### 5.3. Parent tạo một lời giải thật

Mỗi khi gán `parent[v]=u`, ta có `distance[v]=distance[u]+1`. Khi lần theo cha từ đích, khoảng cách giảm đúng `1` qua mỗi cạnh; sau `distance[goal]` lần sẽ tới nguồn, không thể tạo chu trình trong chuỗi cha.

Đảo chuỗi cha lại cho một đường **hợp lệ** với đúng số bước BFS báo. Như vậy thuật toán vừa tìm số bước tối ưu vừa cung cấp một **witness** xác minh được.

### 5.4. Trạng thái cấm không phá chứng minh

Bỏ các trạng thái cấm khỏi đồ thị trạng thái, cùng mọi cung đi vào/ra chúng. BFS chạy trên đồ thị còn lại, nên chứng minh theo lớp vẫn đúng. Nếu nguồn hoặc đích nằm trong tập cấm, theo hợp đồng bài toán **không có đường hợp lệ**.

## 6. Mô phỏng chi tiết bài biến đổi số

Miền:

\[
S=\{0,1,\ldots,20\}.
\]

Thao tác theo thứ tự sinh `x-1`, `x+1`, `2x`. Cấm `6,8`, nguồn `3`, đích `11`.

| Lớp | Trạng thái mới |
|---:|---|
| 0 | `3` |
| 1 | `2,4` (bỏ `6` vì cấm) |
| 2 | `1,5` (bỏ `8` vì cấm) |
| 3 | `0,10` |
| 4 | `9,11,20` |

Khi xử lý `10` ở lớp `3`, BFS phát hiện `11` ở lớp `4`.

Chuỗi cha:

```text
parent[11] = 10
parent[10] = 5
parent[5]  = 4
parent[4]  = 3
parent[3]  = -1
```

Đảo ngược chuỗi `11,10,5,4,3`:

\[
\boxed{3\to4\to5\to10\to11,\quad 4\text{ bước}.}
\]

Không chọn `3\to6` chỉ vì nhân đôi “tiến nhanh”: `6` bị cấm.

### 6.1. Đích chính là nguồn

Với `start=goal=7` và `7` không cấm:

```text
steps = 0
path = [7]
```

Không có thao tác nào cần thực hiện; đường trạng thái có một đỉnh nhưng **không có cạnh**.

### 6.2. Không tới được

Với miền `0..6`, nguồn `0`, đích `6`, cấm `1`:

- `0-1=-1` nằm ngoài miền.
- `0+1=1` bị cấm.
- `0\times2=0` là self-loop, `0` đã visited.

BFS không phát hiện trạng thái mới và trả:

```text
steps = -1
path = []
```

`-1` nghĩa là **không có đường**, không phải một số bước âm thật sự.

### 6.3. Tránh tràn khi sinh hàng xóm

Đừng luôn tính `2*x` bằng kiểu `int` rồi mới kiểm tra `\le MAX`; phép nhân có thể tràn trước khi so sánh.

Kiểm tra trước:

```java
int twice = x <= max / 2 ? 2 * x : -1;
```

Với miền không âm, nhánh được tính bảo đảm `2*x\le max`. Tương tự, chỉ tính `x+1` khi `x<max`.

## 7. BFS trên mê cung khi mỗi bước có giá 1

Một robot đi trong lưới, chỉ được di chuyển **lên, xuống, trái, phải** mỗi lần một ô, không xuyên tường `#`. Các ô `S` và `T` là ô đi được.

```text
S..#..
.#.#..
.#...T
...##.
......
```

Một đường ngắn nhất:

```text
(0,0) -> (0,1) -> (0,2) -> (1,2)
      -> (2,2) -> (2,3) -> (2,4) -> (2,5)

7 bước.
```

Tọa độ bắt đầu từ `0`. Hai ô liên tiếp phải thỏa:

\[
|r_1-r_2|+|c_1-c_2|=1.
\]

### 7.1. Sinh đúng bốn hàng xóm

```text
dr = [-1, 1, 0, 0]
dc = [ 0, 0,-1, 1]

for dir in 0..3:
    nr = row + dr[dir]
    nc = col + dc[dir]

    if outside grid: skip
    if grid[nr][nc] == '#': skip
    if visited: skip

    distance[nr][nc] = distance[row][col] + 1
    parent[nr][nc] = (row,col)
    enqueue(nr,nc)
```

Không tự thêm đường chéo. Nếu đề cho đi 8 hướng **mỗi hướng đều giá 1**, có thể đổi bộ vector hướng mà vẫn dùng BFS. Nếu đi chéo tốn `\sqrt2` và ngang/dọc tốn `1`, các bước không còn đồng giá nên BFS không tối ưu tổng độ dài.

### 7.2. Mã hóa ô thành một ID

Với lưới `height\times width`:

\[
id=row\cdot width+col,
\]

\[
row=id/width,\quad col=id\bmod width.
\]

Nhờ vậy có thể dùng `distance[id]`, `parent[id]`, `queue[]` dạng mảng một chiều. Với `height\cdot width` lớn, cần kiểm tra phép nhân không tràn kiểu chỉ số.

### 7.3. Khi không có đường

Ví dụ một hàng:

```text
S#T
```

BFS không thể vượt tường giữa nguồn và đích, trả `steps=-1, path=[]`.

## 8. Multi-source BFS: nhiều nguồn cùng lớp 0

Giả sử có tập nguồn:

\[
S_0=\{s_1,s_2,\ldots,s_k\}.
\]

Muốn biết số bước nhỏ nhất **từ một nguồn bất kỳ** tới trạng thái `v`:

\[
\boxed{distance[v]=\min_{s\in S_0}d^*(s,v).}
\]

Thay vì chạy BFS `k` lần, khởi tạo **tất cả nguồn hợp lệ ở lớp 0** rồi chạy một BFS chung.

```text
distance[*] = -1
queue = empty

for each source:
    if source is valid, not forbidden, and not visited:
        distance[source] = 0
        enqueue(source)

while queue not empty:
    u = dequeue()
    for each legal v in nextStates(u):
        if distance[v] == -1:
            distance[v] = distance[u] + 1
            enqueue(v)
```

Các nguồn trùng nhau chỉ cần đưa vào queue **một lần**. Nguồn bị cấm được bỏ qua theo hợp đồng trong ví dụ Java; nếu tất cả nguồn đều bị cấm hoặc mảng nguồn rỗng, mọi khoảng cách là `-1`.

### 8.1. Ví dụ nhiều nguồn — lưu ý đường tắt nhân đôi

Trên miền `0..20`, cấm `6,8`, chọn nguồn `0` và `13`:

- `distance[0]=0` và `distance[13]=0`.
- `distance[11]=2` qua `13\to12\to11`.
- `distance[5]=4` qua `0\to1\to2\to4\to5`; **`2\to4` là phép nhân đôi**, nên đường này ngắn hơn dãy cộng 1 gồm 5 bước.
- `distance[6]=-1` vì trạng thái `6` bị cấm.

Khi kiểm thử, phải dùng **toàn bộ các phép biến đổi**, kể cả phép nhân đôi, để tính số bước thật sự. Không được chỉ nhìn khoảng cách số học `|u-v|`.

### 8.2. Multi-source có hướng không đồng nghĩa khoảng cách về nguồn

Nếu cung chỉ đi `A\to B`, BFS từ `A` cho `dist[B]=1` nhưng từ `B` có thể không tới `A`.

Multi-source BFS từ các nguồn tính **khoảng cách từ nguồn tới v**, không tự động cho khoảng cách **từ v đến nguồn gần nhất**. Khi bài hỏi chiều ngược, cần dựng **quan hệ tiền nhiệm** hoặc đảo hướng các cung cho đúng.

### 8.3. Nhiều nguồn có thời điểm xuất phát khác nhau

Nếu mỗi nguồn có độ trễ/chi phí khởi tạo khác nhau, không thể mặc định tất cả thuộc lớp `0`. Khi đó phải mô hình hóa trọng số ban đầu và thường cần Dijkstra hoặc biến đổi trạng thái phù hợp.

## 9. Truy vết lời giải và xử lý nhiều lời giải tối ưu

Khi phát hiện trạng thái `v` từ `u`:

```text
distance[v] = distance[u] + 1
parent[v] = u
```

Sau khi tới đích, lần theo cha tới nguồn rồi đảo dãy.

Nếu đề yêu cầu in **tên thao tác** thay vì dãy trạng thái, có thể lưu thêm `parentMove[v]`, ví dụ `MOVE_PLUS_ONE` hoặc `MOVE_DOUBLE`. Điều này quan trọng khi hai thao tác khác nhau đưa tới cùng một trạng thái.

### 9.1. Đường ngắn nhất có thể không duy nhất

Nếu có nhiều đường cùng số bước tối thiểu, BFS trả một đường tùy theo thứ tự hàng xóm. Thay đổi thứ tự sinh trạng thái có thể thay chuỗi parent, nhưng **không thay số bước tối ưu**.

Muốn chọn đường từ điển nhỏ nhất, cần quy tắc thứ tự/so sánh đáp ứng tiêu chí đề. Không được tự suy ra FIFO bất kỳ luôn cho đường từ điển nhỏ nhất.

### 9.2. Đếm số đường ngắn nhất

Có thể bổ sung `ways[v]`:

```text
ways[start] = 1

for each transition u -> v:
    if distance[v] == -1:
        distance[v] = distance[u] + 1
        ways[v] = ways[u]
        enqueue(v)
    else if distance[v] == distance[u] + 1:
        ways[v] += ways[u]
```

Nếu yêu cầu kết quả modulo `10^9+7`, áp dụng modulo ở mỗi phép cộng.

**Cần chốt khái niệm đường:** nếu hai phép toán khác nhau dẫn từ cùng `u` đến `v`, ta đếm **chuỗi thao tác** hay chỉ đếm **chuỗi trạng thái**? Nếu đếm chuỗi thao tác, hai cung song song có thể tạo hai cách; nếu đếm chuỗi trạng thái, cần tránh đếm trùng theo thao tác.

Với bài đếm mọi đường ngắn nhất tới một đích, không được dừng ngay khi mới gặp đích lần đầu, vì những đỉnh ở lớp trước có thể còn tạo thêm đường ngắn nhất khác.

## 10. Chọn cấu trúc dữ liệu cho trạng thái

### 10.1. Miền trạng thái nhỏ và đánh số liên tiếp

Khi trạng thái là `0..MAX`, dùng mảng:

```java
int[] distance = new int[MAX + 1];
int[] parent = new int[MAX + 1];
Arrays.fill(distance, -1);
Arrays.fill(parent, -1);
```

`distance[u]` vừa chứa số bước vừa là visited. Mỗi trạng thái chỉ enqueue một lần nên mảng `int[] queue` kích thước `MAX+1` cũng đủ. Hai con trỏ `head,tail` quản lý FIFO, không cần phân bổ đối tượng Integer cho mỗi lần đẩy.

### 10.2. Trạng thái phức tạp hoặc thưa

Nếu trạng thái là chuỗi, record, hoặc số rất lớn với tập trạng thái đến được thưa:

```java
Queue<State> queue = new ArrayDeque<>();
Map<State, Integer> distance = new HashMap<>();
Map<State, State> parent = new HashMap<>();
```

Khóa trạng thái phải có **equals/hashCode nhất quán**. Java `record` thường giúp biểu diễn trạng thái bất biến.

Không dùng `==` của hai đối tượng riêng để quyết định chúng có cùng cấu hình logic hay không. Cũng tránh dùng một khóa mutable rồi thay đổi trường sau khi đã đưa vào HashMap/HashSet.

### 10.3. Dùng BFS trên tích trạng thái

Nếu mê cung có `K` chìa khóa, một trạng thái có thể là `(row,col,mask)`. Số trạng thái tiềm năng lên tới `H\cdot W\cdot2^K`, không chỉ `HW`.

BFS vẫn đúng về mặt nguyên lý nếu mỗi phép chuyển trạng thái tốn một bước, nhưng phải tính toán lại **độ phức tạp và bộ nhớ** theo kích thước không gian tích đó. Nếu kích thước vượt khả năng cấp phát, phải tìm cách tối ưu biểu diễn hoặc chọn kỹ thuật khác, không được lờ chi phí `2^K`.

## 11. Khi không được dùng BFS FIFO

| Loại bài toán | Kỹ thuật thường phù hợp | Lý do |
|---|---|---|
| Mọi bước giá `1` hoặc cùng hằng dương | **BFS** | Ít bước ↔ ít chi phí |
| Cạnh có chi phí `0` hoặc `1` | **0–1 BFS** | Deque đưa cạnh `0` lên đầu, cạnh `1` xuống cuối |
| Trọng số không âm khác nhau | **Dijkstra** | Chọn theo tổng chi phí nhỏ nhất |
| Có trọng số âm, không có chu trình âm liên quan | **Bellman–Ford** hoặc phương pháp chuyên biệt | BFS không xét tổng chi phí; Dijkstra thường không hợp lệ |
| DAG có cạnh chi phí âm | DP theo **thứ tự topo** | Không có chu trình, tính đường ngắn nhất theo topo |
| Mỗi bước đồng giá nhưng trạng thái có mask/chìa khóa | **BFS trên trạng thái mở rộng** | Vẫn là đồ thị không trọng số |
| Tìm từ hai phía, biết chuyển tiếp đảo | **Bidirectional BFS** | Có thể giảm số trạng thái phải duyệt nếu triển khai đúng |
| Mạng có heuristic được chứng minh phù hợp | **A\*** | Ưu tiên theo chi phí đã đi và ước lượng còn lại |

### 11.1. Phản ví dụ cho BFS khi chi phí không đồng nhất

```text
s -> t       cost 1
s -> a       cost 0
a -> t       cost 0
```

BFS ít bước sẽ chọn `s\to t`: một bước, cost `1`. Nhưng đường có chi phí nhỏ nhất là `s\to a\to t`: hai bước, cost `0`. Với trọng số chỉ `0/1`, thuật toán phù hợp là **0–1 BFS**, không phải BFS FIFO thường.

### 11.2. BFS hai đầu cần chú ý chiều cạnh

Trên đồ thị **có hướng**, khi duyệt từ đích về nguồn, phải sử dụng các **cung đảo/tiền nhiệm** tương ứng với thao tác thuận. Không được chạy từ đích với chính hàm `nextStates` nếu đó không phải quan hệ đối xứng.

Để dừng ở điểm giao mà vẫn đảm bảo tối ưu, cần duy trì lớp/khoảng cách ở cả hai phía; một cách dừng “gặp nhau bất kỳ là xong” có thể sai nếu hai phía mở rộng không theo lớp phù hợp.

## 12. Java 17+ hoàn chỉnh: BFS biến đổi số, BFS nhiều nguồn và BFS trên lưới

Chương trình sau dùng hai mô hình:

- **`NumberSpace`:** trạng thái nguyên trong `0..MAX`, ba phép `x-1,x+1,2x`, danh sách cấm và BFS trả một lời giải tối ưu. Có thêm multi-source BFS.
- **`GridSpace`:** lưới chữ nhật gồm `. # S T`; đi 4 hướng qua ô không chặn, BFS trả số bước và tọa độ đường.
- **Oracle Floyd–Warshall:** tạo ma trận đường đi **độc lập với queue và parent của BFS** trên bài số nguyên/lưới nhỏ để kiểm tra tối ưu.
- **Witness validation:** kiểm tra từng bước của đường đã in, gồm đầu/cuối, bước hợp lệ, không qua tường/trạng thái cấm.
- **Test ngẫu nhiên:** 2.500 ca số nguyên, 600 ca đa nguồn và 800 ca lưới.

Đây là **toàn bộ tệp** `UniformCostStateBfsDemo.java`, không phụ thuộc thư viện bên ngoài JDK 17.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.StringJoiner;

public final class UniformCostStateBfsDemo {
    private UniformCostStateBfsDemo() {
    }

    public record Answer(int steps, List<Integer> path) {
        public Answer {
            path = List.copyOf(path);
        }
    }

    public record Cell(int row, int col) {
    }

    public record GridAnswer(int steps, List<Cell> path) {
        public GridAnswer {
            path = List.copyOf(path);
        }
    }

    private static final class NumberSpace {
        final int max;
        final boolean[] blocked;

        NumberSpace(int max, int[] forbidden) {
            Objects.requireNonNull(forbidden, "forbidden");
            if (max < 0 || max > 1_000_000) {
                throw new IllegalArgumentException(
                    "MAX must be between 0 and 1,000,000"
                );
            }
            this.max = max;
            blocked = new boolean[max + 1];

            for (int x : forbidden) {
                check(x);
                blocked[x] = true;
            }
        }

        private void check(int x) {
            if (x < 0 || x > max) {
                throw new IllegalArgumentException(
                    "state outside 0..MAX"
                );
            }
        }

        private int[] next(int x) {
            return new int[]{
                x > 0 ? x - 1 : -1,
                x < max ? x + 1 : -1,
                x <= max / 2 ? 2 * x : -1
            };
        }

        Answer shortest(int start, int goal) {
            check(start);
            check(goal);
            if (blocked[start] || blocked[goal]) {
                return new Answer(-1, List.of());
            }

            int[] distance = new int[max + 1];
            int[] parent = new int[max + 1];
            int[] queue = new int[max + 1];
            Arrays.fill(distance, -1);
            Arrays.fill(parent, -1);

            int head = 0, tail = 0;
            distance[start] = 0;
            queue[tail++] = start;

            while (head < tail) {
                int x = queue[head++];

                if (x == goal) {
                    List<Integer> reverse = new ArrayList<>();
                    for (int cur = goal; cur != -1;
                            cur = parent[cur]) {
                        reverse.add(cur);
                    }
                    Collections.reverse(reverse);
                    return new Answer(distance[goal], reverse);
                }

                for (int y : next(x)) {
                    if (y < 0 || blocked[y]
                            || distance[y] != -1) {
                        continue;
                    }
                    distance[y] = distance[x] + 1;
                    parent[y] = x;
                    queue[tail++] = y;
                }
            }
            return new Answer(-1, List.of());
        }

        int[] distancesFromSources(int[] sources) {
            Objects.requireNonNull(sources, "sources");
            int[] distance = new int[max + 1];
            int[] queue = new int[max + 1];
            Arrays.fill(distance, -1);
            int head = 0, tail = 0;

            for (int source : sources) {
                check(source);
                if (!blocked[source] && distance[source] == -1) {
                    distance[source] = 0;
                    queue[tail++] = source;
                }
            }

            while (head < tail) {
                int x = queue[head++];
                for (int y : next(x)) {
                    if (y < 0 || blocked[y]
                            || distance[y] != -1) {
                        continue;
                    }
                    distance[y] = distance[x] + 1;
                    queue[tail++] = y;
                }
            }
            return distance;
        }
    }

    private static final class GridSpace {
        private static final int[] DR = {-1, 1, 0, 0};
        private static final int[] DC = {0, 0, -1, 1};

        final char[][] cells;
        final int height;
        final int width;
        final int start;
        final int goal;

        GridSpace(List<String> rows) {
            Objects.requireNonNull(rows, "rows");
            if (rows.isEmpty()) {
                throw new IllegalArgumentException(
                    "grid cannot be empty"
                );
            }
            height = rows.size();
            width = Objects.requireNonNull(
                rows.get(0), "first row"
            ).length();

            if (width == 0
                    || (long) height * width > 1_000_000L) {
                throw new IllegalArgumentException(
                    "invalid grid size"
                );
            }
            cells = new char[height][width];
            int s = -1, t = -1;

            for (int r = 0; r < height; r++) {
                String line = Objects.requireNonNull(
                    rows.get(r), "row"
                );
                if (line.length() != width) {
                    throw new IllegalArgumentException(
                        "grid must be rectangular"
                    );
                }

                for (int c = 0; c < width; c++) {
                    char ch = line.charAt(c);
                    if (ch != '.' && ch != '#'
                            && ch != 'S' && ch != 'T') {
                        throw new IllegalArgumentException(
                            "unexpected character"
                        );
                    }
                    cells[r][c] = ch;

                    if (ch == 'S') {
                        if (s != -1) {
                            throw new IllegalArgumentException(
                                "multiple S"
                            );
                        }
                        s = r * width + c;
                    }
                    if (ch == 'T') {
                        if (t != -1) {
                            throw new IllegalArgumentException(
                                "multiple T"
                            );
                        }
                        t = r * width + c;
                    }
                }
            }
            if (s == -1 || t == -1) {
                throw new IllegalArgumentException(
                    "require exactly one S and T"
                );
            }
            start = s;
            goal = t;
        }

        private Cell cellAt(int id) {
            return new Cell(id / width, id % width);
        }

        GridAnswer shortest() {
            int count = height * width;
            int[] dist = new int[count];
            int[] parent = new int[count];
            int[] queue = new int[count];
            Arrays.fill(dist, -1);
            Arrays.fill(parent, -1);
            int head = 0, tail = 0;

            dist[start] = 0;
            queue[tail++] = start;

            while (head < tail) {
                int u = queue[head++];

                if (u == goal) {
                    List<Cell> reverse = new ArrayList<>();
                    for (int x = goal; x != -1;
                            x = parent[x]) {
                        reverse.add(cellAt(x));
                    }
                    Collections.reverse(reverse);
                    return new GridAnswer(dist[goal], reverse);
                }

                int r = u / width, c = u % width;

                for (int dir = 0; dir < 4; dir++) {
                    int nr = r + DR[dir];
                    int nc = c + DC[dir];

                    if (nr < 0 || nr >= height
                            || nc < 0 || nc >= width
                            || cells[nr][nc] == '#') {
                        continue;
                    }

                    int v = nr * width + nc;
                    if (dist[v] == -1) {
                        dist[v] = dist[u] + 1;
                        parent[v] = u;
                        queue[tail++] = v;
                    }
                }
            }
            return new GridAnswer(-1, List.of());
        }
    }

    private static String formatCells(List<Cell> path) {
        StringJoiner join = new StringJoiner("->");
        for (Cell cell : path) {
            join.add(
                "(" + cell.row() + "," + cell.col() + ")"
            );
        }
        return join.toString();
    }

    // Oracle độc lập: Floyd-Warshall trên đồ thị số nhỏ.
    // Dùng Math.min để self-loop x=0 không ghi đè d[0][0]=0.
    private static int[][] oracleNumberDistances(
            NumberSpace space) {
        int n = space.max + 1;
        final int INF = 1_000_000;
        int[][] d = new int[n][n];

        for (int x = 0; x < n; x++) {
            Arrays.fill(d[x], INF);
            if (!space.blocked[x]) {
                d[x][x] = 0;
            }
        }

        for (int x = 0; x < n; x++) {
            if (space.blocked[x]) {
                continue;
            }
            int[] candidates = {
                x > 0 ? x - 1 : -1,
                x < space.max ? x + 1 : -1,
                x <= space.max / 2 ? 2 * x : -1
            };
            for (int y : candidates) {
                if (y >= 0 && !space.blocked[y]) {
                    d[x][y] = Math.min(d[x][y], 1);
                }
            }
        }

        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                if (d[i][k] == INF) {
                    continue;
                }
                for (int j = 0; j < n; j++) {
                    if (d[k][j] != INF) {
                        d[i][j] = Math.min(
                            d[i][j], d[i][k] + d[k][j]
                        );
                    }
                }
            }
        }
        return d;
    }

    private static int oracleGridSteps(GridSpace grid) {
        int n = grid.height * grid.width;
        final int INF = 1_000_000;
        int[][] d = new int[n][n];

        for (int u = 0; u < n; u++) {
            Arrays.fill(d[u], INF);
            int r = u / grid.width;
            int c = u % grid.width;

            if (grid.cells[r][c] == '#') {
                continue;
            }
            d[u][u] = 0;

            for (int dir = 0; dir < 4; dir++) {
                int nr = r + GridSpace.DR[dir];
                int nc = c + GridSpace.DC[dir];
                if (nr >= 0 && nr < grid.height
                        && nc >= 0 && nc < grid.width
                        && grid.cells[nr][nc] != '#') {
                    d[u][nr * grid.width + nc] = 1;
                }
            }
        }

        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                if (d[i][k] == INF) {
                    continue;
                }
                for (int j = 0; j < n; j++) {
                    if (d[k][j] != INF) {
                        d[i][j] = Math.min(
                            d[i][j], d[i][k] + d[k][j]
                        );
                    }
                }
            }
        }
        return d[grid.start][grid.goal] == INF
            ? -1 : d[grid.start][grid.goal];
    }

    private static void assertNumberPath(
            NumberSpace space, int s, int t, Answer answer) {
        List<Integer> path = answer.path();
        if (answer.steps() == -1) {
            if (!path.isEmpty()) {
                throw new AssertionError(
                    "unreachable state has a path"
                );
            }
            return;
        }

        if (path.size() != answer.steps() + 1
                || path.get(0) != s
                || path.get(path.size() - 1) != t) {
            throw new AssertionError(
                "invalid state path endpoints/length"
            );
        }
        for (int i = 0; i < path.size(); i++) {
            int x = path.get(i);
            if (x < 0 || x > space.max || space.blocked[x]) {
                throw new AssertionError(
                    "path enters a forbidden state"
                );
            }
            if (i > 0) {
                int prev = path.get(i - 1);
                boolean legal =
                    x == prev - 1
                    || x == prev + 1
                    || (prev <= space.max / 2
                        && x == 2 * prev);
                if (!legal) {
                    throw new AssertionError(
                        "illegal number transition"
                    );
                }
            }
        }
    }

    private static void assertGridPath(
            GridSpace grid, GridAnswer answer) {
        List<Cell> path = answer.path();
        if (answer.steps() == -1) {
            if (!path.isEmpty()) {
                throw new AssertionError(
                    "unreachable grid has a path"
                );
            }
            return;
        }

        if (path.size() != answer.steps() + 1
                || !path.get(0).equals(
                    grid.cellAt(grid.start))
                || !path.get(path.size() - 1).equals(
                    grid.cellAt(grid.goal))) {
            throw new AssertionError(
                "invalid grid path endpoints/length"
            );
        }

        for (int i = 0; i < path.size(); i++) {
            Cell c = path.get(i);
            if (c.row() < 0 || c.row() >= grid.height
                    || c.col() < 0 || c.col() >= grid.width
                    || grid.cells[c.row()][c.col()] == '#') {
                throw new AssertionError(
                    "grid path uses a blocked cell"
                );
            }
            if (i > 0) {
                Cell p = path.get(i - 1);
                int manhattan =
                    Math.abs(c.row() - p.row())
                    + Math.abs(c.col() - p.col());
                if (manhattan != 1) {
                    throw new AssertionError(
                        "grid path has an illegal move"
                    );
                }
            }
        }
    }

    public static void main(String[] args) {
        NumberSpace space =
            new NumberSpace(20, new int[]{6, 8});

        Answer main = space.shortest(3, 11);
        System.out.println(
            "State: steps=" + main.steps()
            + " path=" + main.path()
        );

        Answer same = space.shortest(7, 7);
        System.out.println(
            "State same: steps=" + same.steps()
            + " path=" + same.path()
        );

        Answer blocked = space.shortest(3, 6);
        System.out.println(
            "State blocked target: steps=" + blocked.steps()
            + " path=" + blocked.path()
        );

        NumberSpace tiny =
            new NumberSpace(6, new int[]{1});
        Answer impossible = tiny.shortest(0, 6);
        System.out.println(
            "State unreachable: steps=" + impossible.steps()
            + " path=" + impossible.path()
        );

        int[] multi = space.distancesFromSources(
            new int[]{0, 13}
        );
        System.out.println(
            "Multi-source: d[11]=" + multi[11]
            + " d[5]=" + multi[5]
            + " d[6]=" + multi[6]
        );

        GridSpace grid = new GridSpace(List.of(
            "S..#..",
            ".#.#..",
            ".#...T",
            "...##.",
            "......"
        ));
        GridAnswer route = grid.shortest();
        System.out.println(
            "Grid: steps=" + route.steps()
            + " path=" + formatCells(route.path())
        );

        GridAnswer blockedGrid =
            new GridSpace(List.of("S#T")).shortest();
        System.out.println(
            "Grid unreachable: steps=" + blockedGrid.steps()
            + " path=" + blockedGrid.path()
        );

        boolean rejected = false;
        try {
            new NumberSpace(5, new int[]{7});
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println(
            "Invalid state rejected: " + rejected
        );

        Random random = new Random(355L);
        int numberChecks = 0;
        int multiChecks = 0;

        for (int trial = 0; trial < 2_500; trial++) {
            int max = random.nextInt(13);
            List<Integer> forbidden = new ArrayList<>();
            for (int x = 0; x <= max; x++) {
                if (random.nextInt(6) == 0) {
                    forbidden.add(x);
                }
            }
            int[] bans = new int[forbidden.size()];
            for (int i = 0; i < bans.length; i++) {
                bans[i] = forbidden.get(i);
            }

            NumberSpace small = new NumberSpace(max, bans);
            int s = random.nextInt(max + 1);
            int t = random.nextInt(max + 1);
            Answer got = small.shortest(s, t);
            int[][] oracle = oracleNumberDistances(small);

            int expected = oracle[s][t] == 1_000_000
                ? -1 : oracle[s][t];
            if (got.steps() != expected) {
                throw new AssertionError(
                    "state mismatch trial=" + trial
                );
            }
            assertNumberPath(small, s, t, got);
            numberChecks++;

            if (trial < 600) {
                int srcA = random.nextInt(max + 1);
                int srcB = random.nextInt(max + 1);
                int[] multiDist =
                    small.distancesFromSources(
                        new int[]{srcA, srcB}
                    );

                for (int v = 0; v <= max; v++) {
                    int best = 1_000_000;
                    if (!small.blocked[srcA]) {
                        best = Math.min(
                            best, oracle[srcA][v]
                        );
                    }
                    if (!small.blocked[srcB]) {
                        best = Math.min(
                            best, oracle[srcB][v]
                        );
                    }
                    int want = best == 1_000_000
                        ? -1 : best;
                    if (multiDist[v] != want) {
                        throw new AssertionError(
                            "multi-source distance mismatch"
                        );
                    }
                }
                multiChecks++;
            }
        }

        int gridChecks = 0;
        for (int trial = 0; trial < 800; trial++) {
            int h = 2 + random.nextInt(3);
            int w = 2 + random.nextInt(3);
            List<String> rows = new ArrayList<>();

            for (int r = 0; r < h; r++) {
                StringBuilder line = new StringBuilder();
                for (int c = 0; c < w; c++) {
                    line.append(
                        random.nextInt(4) == 0 ? '#' : '.'
                    );
                }
                rows.add(line.toString());
            }
            StringBuilder first =
                new StringBuilder(rows.get(0));
            first.setCharAt(0, 'S');
            rows.set(0, first.toString());

            StringBuilder last =
                new StringBuilder(rows.get(h - 1));
            last.setCharAt(w - 1, 'T');
            rows.set(h - 1, last.toString());

            GridSpace smallGrid = new GridSpace(rows);
            GridAnswer got = smallGrid.shortest();
            int expected = oracleGridSteps(smallGrid);

            if (got.steps() != expected) {
                throw new AssertionError(
                    "grid distance mismatch trial=" + trial
                );
            }
            assertGridPath(smallGrid, got);
            gridChecks++;
        }

        System.out.println(
            "Random number comparisons: " + numberChecks
        );
        System.out.println(
            "Random multi-source comparisons: " + multiChecks
        );
        System.out.println(
            "Random grid comparisons: " + gridChecks
        );
    }
}
```

Biên dịch và chạy với **JDK 17+**; lưu tệp UTF-8:

```bash
javac -encoding UTF-8 UniformCostStateBfsDemo.java
java UniformCostStateBfsDemo
```

**Đầu ra chuẩn:**

```text
State: steps=4 path=[3, 4, 5, 10, 11]
State same: steps=0 path=[7]
State blocked target: steps=-1 path=[]
State unreachable: steps=-1 path=[]
Multi-source: d[11]=2 d[5]=4 d[6]=-1
Grid: steps=7 path=(0,0)->(0,1)->(0,2)->(1,2)->(2,2)->(2,3)->(2,4)->(2,5)
Grid unreachable: steps=-1 path=[]
Invalid state rejected: true
Random number comparisons: 2500
Random multi-source comparisons: 600
Random grid comparisons: 800
```

### 12.1. Mảng queue không bị tràn

`distance[v]` được gán ngay khi enqueue nên mỗi trạng thái vào queue tối đa một lần. Với miền `0..MAX`, mảng queue có `MAX+1` phần tử đủ chứa toàn bộ trạng thái tiềm năng. Với lưới, mảng queue dài `height\cdot width` cũng đủ.

Tuy nhiên, chi phí cấp phát vẫn theo kích thước toàn miền; nếu không gian thưa và cực rộng, dùng `HashMap/HashSet` có thể phù hợp hơn.

### 12.2. Dòng xử lý self-loop quan trọng trong oracle

Trong mô hình số, từ `x=0` có thao tác `2x=0`, tạo self-loop. Floyd–Warshall phải giữ:

\[
distance(0,0)=0,
\]

vì ở nguyên trạng thái hiện tại không cần bước nào. Do đó khi dựng ma trận cạnh, mã dùng:

```java
d[x][y] = Math.min(d[x][y], 1);
```

thay vì `d[x][y]=1` một cách mù quáng, tránh ghi đè đường rỗng độ dài `0` bằng self-loop độ dài `1`. Đây là một trường hợp biên rất dễ làm **oracle kiểm thử** sai dù BFS đúng.

### 12.3. Vì sao output multi-source tới 5 là 4?

Từ nguồn `0`:

\[
0\to1\to2\to4\to5.
\]

Đó là **4 bước**; phép `2\to4` là nhân đôi, không phải đi qua `3`. Vì vậy khoảng cách tới `5` không phải `5`. Oracle Floyd–Warshall xác nhận điều này.

### 12.4. Xác minh đường in

Trước khi chấp nhận câu trả lời, `assertNumberPath` kiểm tra:

- Đường không rỗng khi có lời giải.
- Đầu và cuối đúng nguồn/đích.
- Số trạng thái là `steps+1`.
- Không trạng thái nào ngoài miền hoặc bị cấm.
- Mỗi chuyển tiếp đúng một trong ba quy tắc.

`assertGridPath` kiểm tra đầu/cuối, số bước, không qua tường và mỗi cặp ô kề có **khoảng cách Manhattan bằng 1**.

Điều này giúp phát hiện một lỗi mà chỉ so `distance` sẽ bỏ qua: số bước đúng nhưng đường parent bị ghi đè hoặc tạo ra một chuyển tiếp không hợp lệ.

## 13. Độ phức tạp

Đặt `V` là số trạng thái, `E` là số cung chuyển tiếp của đồ thị trạng thái. Với danh sách kề tường minh:

\[
\boxed{\text{Time}=O(V+E),\qquad
\text{ExtraSpace}=O(V).}
\]

BFS phát hiện mỗi trạng thái tối đa một lần; các hàng xóm/cung được xét nhiều nhất một lần từ mỗi trạng thái được mở rộng.

Nếu mỗi trạng thái có tối đa `b` thao tác, thời gian thường viết `O(Vb)`. Với `b` nhỏ và cố định (3 phép số nguyên, 4 hướng lưới), thời gian tuyến tính theo số trạng thái được xét/cấp phát.

| Biến thể | Thời gian | Bộ nhớ |
|---|---|---|
| BFS số nguyên `0..MAX`, 3 thao tác | `O(MAX)` | `O(MAX)` |
| BFS lưới `H\times W`, 4 hướng | `O(HW)` | `O(HW)` |
| Multi-source BFS | `O(V+E)` cộng khởi tạo nguồn | `O(V)` |
| Truy vết một đường `d` bước | `O(d+1)` | `O(d+1)` cho danh sách |
| Oracle Floyd–Warshall trên `V` trạng thái nhỏ | `O(V^3)` | `O(V^2)` |

**Phân biệt:** một đích có thể được tìm sớm nhưng hàm vẫn đã cấp phát các mảng kích thước `MAX+1` hoặc `HW`. Nếu số trạng thái hữu hạn không đánh số liên tiếp hoặc quá lớn, bộ nhớ mảng có thể không phù hợp.

BFS không thể được tuyên bố `O(\log V)` chỉ vì lời giải ngắn; trong trường hợp xấu nó phải khám phá toàn bộ thành phần có thể tới được.

## 14. Kiểm thử độc lập: không chỉ so hai lần BFS

Chương trình không dùng cùng một routine BFS để tạo đáp án kỳ vọng. Oracle trên dữ liệu nhỏ là **Floyd–Warshall**:

1. Tạo ma trận `d[u][v]`: `0` trên đường rỗng của trạng thái hợp lệ, `1` khi có một chuyển tiếp hợp lệ, `INF` nếu chưa có đường.
2. Với từng đỉnh trung gian `k`, thư giãn:

\[
d[i][j]=\min(d[i][j],d[i][k]+d[k][j]).
\]

3. Sau đủ `k`, `d[start][goal]` là số bước nhỏ nhất; `INF` biểu diễn không tới được.

Oracle phải không xem một trạng thái bị cấm là đỉnh hợp lệ, và phải giữ `d[u][u]=0` ngay cả khi có self-loop.

### 14.1. Kiểm thử số nguyên ngẫu nhiên

Chương trình kiểm tra **2.500** miền `MAX=0..12`, nguồn/đích và trạng thái cấm ngẫu nhiên. Mỗi ca so khoảng cách BFS với Floyd–Warshall; nếu BFS có đường, từng chuyển tiếp cũng được xác minh.

Trong **600** ca đầu, chương trình còn chọn hai nguồn ngẫu nhiên, tính khoảng cách tốt nhất theo ma trận oracle từ **từng nguồn hợp lệ**, rồi so với toàn bộ mảng multi-source BFS. Những ca có nguồn trùng, nguồn bị cấm và đích bị cấm cũng được xử lý theo hợp đồng.

### 14.2. Kiểm thử mê cung ngẫu nhiên

Chương trình tạo **800** lưới từ `2\times2` đến `4\times4` với tường ngẫu nhiên, nguồn góc trên trái và đích góc dưới phải.

Mỗi ca được đối chiếu với Floyd–Warshall trên đồ thị ô kề hợp lệ và kiểm tra đường truy vết không vượt biên, không xuyên tường, chỉ đi bốn hướng.

### 14.3. Những ca biên cần nhớ

```text
MAX=0, nguồn=đích=0, không cấm:
  steps=0, path=[0]

MAX=0, cấm 0:
  steps=-1, path=[]

Nguồn bằng đích:
  0 bước nếu trạng thái hợp lệ

Nguồn bị cấm hoặc đích bị cấm:
  không có đường

0 -> 0 do phép nhân 2:
  không được ghi đè đường rỗng dài 0

Hai phép từ u cùng dẫn tới v:
  v chỉ enqueue một lần

Hai nguồn trùng nhau:
  chỉ có một mục queue lớp 0

Nguồn 0, đích 6, cấm 1, MAX=6:
  không tới được

Lưới S#T:
  không tới được

Lưới có tường che đường trực tiếp:
  tìm được đường vòng nếu tồn tại

Đồ thị chỉ có cung một chiều:
  không giả định đường ngược

Trạng thái phức tạp nhưng visited thiếu mask:
  có nguy cơ mất lời giải đúng
```

**Kiểm thử hữu hạn không thay chứng minh** ở phần 5. Tuy nhiên, đối chứng độc lập và kiểm tra đường thật giúp bắt những lỗi triển khai thường gặp.

## 15. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng DFS và trả khi gặp đích lần đầu | Có thể trả đường dài | Dùng BFS FIFO theo lớp |
| Đánh dấu visited khi dequeue | Enqueue nhiều bản sao, ghi đè parent | Đánh dấu ngay lúc enqueue |
| Không có visited | Có thể lặp vô hạn trên chu trình | Dùng `distance!=-1` |
| Quên `distance[start]=0` | Lệch lớp của mọi trạng thái | Khởi tạo nguồn đúng |
| Gán `distance[v]=distance[u]` | Thiếu một bước mỗi cung | Cộng `1` |
| Đếm số đỉnh thay vì số cung | Lệch `1` | `steps=path.size()-1` |
| Dùng BFS cho chi phí khác nhau | Đường ít bước chưa chắc rẻ nhất | 0–1 BFS hoặc Dijkstra |
| Tự thêm cạnh ngược cho thao tác có hướng | Cho phép phép biến đổi không tồn tại | Sinh đúng hậu nhiệm |
| Đặt MAX tùy tiện | Có thể cắt mất nghiệm tối ưu | Dựa vào đề/chứng minh bound |
| Nhân `2*x` trước khi kiểm tra tràn | Sinh giá trị sai | Kiểm tra `x<=MAX/2` |
| Quên trạng thái cấm | Đường đi xuyên rào cản | Lọc trước enqueue |
| Không xử lý nguồn/đích bị cấm | Trả đường giả | Kiểm tra ngay đầu |
| Gộp trạng thái khác nhau do thiếu khóa/mask | Mất cách đi tiếp hợp lệ | Dùng state đầy đủ |
| Không lưu parent khi cần in lời giải | Không khôi phục được thao tác | Lưu cha và/hoặc ID thao tác |
| Ghi đè parent lần hai | Có thể tạo witness sai | Chỉ lưu ở lần phát hiện đầu |
| Dừng sớm khi đếm mọi đường tối ưu | Bỏ sót những đường bằng độ dài | Xử lý hết lớp cần thiết |
| Multi-source nhưng quên đánh dấu các nguồn ban đầu | Trùng nguồn hoặc sai khoảng cách | Các nguồn đều lớp 0 |
| Diễn giải multi-source ngược hướng | Sai trên đồ thị có hướng | Xét hướng đường cần tìm |
| Lưới không chữ nhật | Sai chỉ số | Validate chiều rộng |
| Tự cho đi chéo | Số bước nhỏ giả | Dùng đúng bộ hướng |
| Floyd oracle ghi đè `d[0][0]=0` bởi self-loop | Test báo sai dù BFS đúng | Dùng `Math.min` khi thêm cung |
| Đường có đúng số bước nhưng có cung không hợp lệ | Không phải lời giải thật | Validate từng bước của path |
| Dùng Map key mutable | Không tìm lại được trạng thái visited | Dùng trạng thái bất biến |
| Coi `-1` là 0 bước | Không phân biệt unreachable | Quy ước rõ sentinel |

## 16. Bài tập tự luyện kèm đáp án

**Bài 1.** Tại sao BFS chứ không phải DFS trả số thao tác ít nhất?

*Đáp án:* BFS khám phá theo lớp số bước không giảm nhờ FIFO; DFS có thể đi sâu vào nhánh dài trước khi thử nhánh ngắn.

**Bài 2.** Tại sao visited nên được đánh dấu khi enqueue?

*Đáp án:* một trạng thái chỉ được thêm một lần, tránh queue phình vì nhiều đường dẫn tới cùng trạng thái và giữ nguyên parent từ lần phát hiện tối ưu.

**Bài 3.** Với nguồn và đích cùng bằng `7` (không cấm), số bước và đường là gì?

*Đáp án:* `0` và `[7]`.

**Bài 4.** Với `MAX=20`, cấm `6,8`, từ `3` tới `11` trong bao nhiêu bước ít nhất?

*Đáp án:* `4`, qua `3\to4\to5\to10\to11`.

**Bài 5.** Một lời giải có `4` thao tác, mỗi thao tác tốn `9` đơn vị. Tổng chi phí?

*Đáp án:* `36`.

**Bài 6.** Nếu mọi thao tác có chi phí `0`, có thể kết luận đường ít bước nhất là đường duy nhất tối ưu chi phí không?

*Đáp án:* không. Mọi đường đi hữu hạn đều có chi phí `0`. BFS cho một đường ít bước nhất nhưng có thể có nhiều đường dài hơn cùng chi phí.

**Bài 7.** Cho `s\to t` giá `5` và `s\to a\to t` mỗi cung giá `1`. Đường ít bước và đường ít chi phí có giống nhau không?

*Đáp án:* không; BFS ít bước chọn `s\to t`, còn đường ít chi phí là `s\to a\to t` tổng `2`.

**Bài 8.** Từ `0` với phép `x\to2x` có phát hiện một trạng thái mới không?

*Đáp án:* không, vì `0\times2=0` đã visited. BFS phải bỏ qua self-loop.

**Bài 9.** Tại sao trong ví dụ multi-source từ `0,13` tới `5` chỉ cần `4` bước?

*Đáp án:* đi `0\to1\to2\to4\to5`; bước `2\to4` là nhân đôi.

**Bài 10.** Multi-source BFS tính khoảng cách từ `s_i` tới `v` hay từ `v` về nguồn gần nhất?

*Đáp án:* tính **từ một nguồn tới `v`** theo đúng chiều cung. Hai chiều không nhất thiết bằng nhau trên đồ thị có hướng.

**Bài 11.** Nếu lưới chỉ cho đi bốn hướng và đường có `8` ô, có bao nhiêu bước?

*Đáp án:* `7`, vì số bước là số cạnh nối các ô.

**Bài 12.** Nếu robot có chìa khóa, visited theo tọa độ có luôn đúng?

*Đáp án:* không. Cần phân biệt cùng ô ở trạng thái có và không có chìa khóa, ví dụ `(r,c,hasKey)`.

**Bài 13.** Tại sao kiểm tra `x<=MAX/2` trước khi tính `2*x`?

*Đáp án:* bảo đảm kết quả nằm trong miền và tránh tràn kiểu số.

**Bài 14.** Với cạnh trọng số chỉ `0` và `1`, nên dùng thuật toán gì?

*Đáp án:* 0–1 BFS; BFS FIFO thông thường tối ưu số cạnh nhưng không tối ưu tổng chi phí.

**Bài 15.** Khi đếm mọi đường ngắn nhất, gặp cung `u\to v` với `distance[v]=distance[u]+1` nhưng `v` đã visited, xử lý sao?

*Đáp án:* cộng `ways[u]` vào `ways[v]`; không enqueue `v` lại.

**Bài 16.** Khi nào có thể dừng ngay lúc phát hiện đích?

*Đáp án:* khi chỉ cần một đường hoặc số bước ngắn nhất tới đích cố định; phải gán distance/parent trước. Không áp dụng tùy tiện khi cần mọi khoảng cách/đếm tất cả đường ngắn nhất.

**Bài 17.** Vì sao Floyd–Warshall là oracle độc lập phù hợp cho BFS trên bài nhỏ?

*Đáp án:* nó dùng ma trận và quy hoạch động theo đỉnh trung gian, không phụ thuộc queue/parent của BFS; có thể so số bước và phát hiện lỗi.

**Bài 18.** Nếu trạng thái không thể đánh số liên tiếp mà số trạng thái tới được ít, có thể thay mảng bằng gì?

*Đáp án:* `HashMap/HashSet` với khóa trạng thái bất biến và `ArrayDeque`; vẫn duy trì visited-on-enqueue.

## 17. Checklist trước khi nộp lời giải BFS trạng thái

1. Đã mô hình hóa **đầy đủ trạng thái**, kể cả khóa, lượt đặc biệt, hướng, năng lượng nếu có?
2. Hàm sinh `nextStates` đã đúng quy tắc, đúng chiều và đúng điều kiện cấm?
3. Đề hỏi **ít bước** hoặc mọi bước thật sự có **cùng chi phí dương**?
4. Nếu bước có chi phí `0/1` hoặc nhiều trọng số, đã cân nhắc 0–1 BFS/Dijkstra?
5. Miền trạng thái có căn cứ, không tự cắt tùy tiện?
6. Có kiểm tra source/goal hợp lệ và cấm?
7. Khởi tạo `distance[start]=0` và enqueue nguồn?
8. Đánh dấu ngay **lúc enqueue**, không phải lúc dequeue?
9. Mỗi chuyển tiếp mới tăng `distance` đúng một?
10. Có chặn tràn khi tính giá trị trạng thái tiếp theo?
11. Có bỏ qua self-loop và trạng thái trùng?
12. Nếu cần path, có lưu parent đúng một lần và đảo chuỗi khi truy vết?
13. Với nguồn bằng đích, kết quả là `0` bước, đường gồm một đỉnh?
14. Với không tới được, kết quả rõ `-1` và đường rỗng?
15. Với multi-source, mọi nguồn hợp lệ có `distance=0` và đúng chiều cung?
16. Với lưới, có kiểm tra tường, biên, số hướng và số ô?
17. Có tính độ phức tạp theo **số trạng thái/cung**, không chỉ một con số đầu vào?
18. Có kiểm thử một đồ thị nhỏ độc lập và xác minh **mọi chuyển tiếp trong đường trả về**?

## Ghi nhớ

BFS là thuật toán chuẩn cho **ít bước nhất trên đồ thị không trọng số**. Với mọi bước có cùng chi phí dương `c`, kết quả ít bước cũng tối thiểu hóa tổng chi phí `c\cdot steps`.

Bất biến cốt lõi:

\[
distance[start]=0,\qquad
distance[v]=distance[u]+1
\]

khi `v` được phát hiện lần đầu từ `u`.

**FIFO duyệt theo lớp; visited ngay lúc enqueue; parent giúp truy vết.** Đồ thị trạng thái có thể được sinh ngầm, miễn là mỗi trạng thái chứa đủ thông tin và các hàng xóm được sinh chính xác.

\[
\boxed{Time=O(V+E),\quad ExtraSpace=O(V)}
\]

cho BFS tường minh; với mỗi trạng thái có số thao tác hằng định, độ phức tạp tuyến tính theo số trạng thái được xét/cấp phát. Multi-source BFS đặt mọi nguồn ở **lớp 0**.

Đừng nhầm “ít thao tác” với “ít tổng chi phí” nếu các bước có giá khác nhau. **Mô hình hóa đúng trạng thái, giữ thứ tự FIFO và đánh dấu visited khi enqueue là ba điều kiện quan trọng nhất giúp BFS vừa đúng vừa hiệu quả.**
