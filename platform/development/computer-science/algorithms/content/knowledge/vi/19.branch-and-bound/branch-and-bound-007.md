# Nhánh và cận cho bài toán người du lịch

**Bài toán người du lịch** (*Traveling Salesperson Problem – TSP*) yêu cầu tìm một hành trình có tổng chi phí nhỏ nhất, xuất phát từ một thành phố, thăm **mỗi thành phố còn lại đúng một lần** rồi quay về điểm xuất phát. Nếu xem thành phố là đỉnh và tuyến đi là cạnh/cung, đó là bài tìm **chu trình Hamilton có trọng số nhỏ nhất**.

**Nhánh và cận** (*branch and bound – B&B*) giải bài toán tối ưu này bằng cách kết hợp **tìm kiếm có hệ thống** và **chứng minh rằng nhiều nhánh không thể cải thiện nghiệm tốt nhất đã tìm thấy**. Ta xây từng đoạn đường, giữ một **cận trên** từ một hành trình hoàn chỉnh và tính **cận dưới** cho mọi cách hoàn thành nhánh hiện tại. Khi cận dưới đã không thể tốt hơn cận trên, ta bỏ cả cây con mà **không cần liệt kê tất cả hoán vị**.

Ba điều cần hiểu trước khi lập trình:

1. **Ràng buộc lời giải:** Xuất phát ở một đỉnh cố định, mỗi đỉnh khác xuất hiện đúng một lần, phải có cung quay về đỉnh xuất phát.
2. **Cận dưới phải an toàn:** Giá trị ước lượng phải **không lớn hơn** chi phí của bất kỳ cách hoàn tất hợp lệ nào từ trạng thái hiện tại. Cận “ước lượng nhanh” nhưng quá lớn có thể cắt mất nghiệm tối ưu.
3. **Khôi phục trạng thái khi quay lui:** Khi thử một thành phố tiếp theo, phải đánh dấu đã thăm, tiếp tục tìm kiếm rồi **bỏ đánh dấu** trước khi thử nhánh khác.

Bài học phân biệt bài toán có hướng/bất đối xứng với vô hướng/đối xứng; trình bày cận dưới dựa trên **cạnh đi ra tối thiểu của mỗi đỉnh chưa thăm**; dùng hành trình tham lam làm **cận trên ban đầu**, rồi kiểm chứng kết quả bằng một chương trình **Java 17+** chạy được. Các trường hợp có **cung bị thiếu, chi phí bằng 0, greedy mắc ngõ cụt, không tồn tại hành trình, một hoặc không có thành phố** đều được xử lý rõ.

## 1. Phát biểu bài toán và mô hình dữ liệu

Cho n thành phố, đánh số 0..n−1. Định nghĩa `cost[u][v]` là chi phí đi trực tiếp từ u sang v; có thể là khoảng cách, thời gian hoặc chi phí tiền tệ, miễn mô hình được dùng nhất quán.

Trong bài này, ta dùng:

- **Ma trận có hướng** `int[][] cost`; không bắt buộc `cost[u][v] = cost[v][u]`. TSP đối xứng là trường hợp riêng khi các giá trị tương ứng bằng nhau.
- Chi phí của cung có thật là **số nguyên không âm**, kể cả 0.
- Giá trị **-1** biểu diễn **không có cung** từ u tới v.
- Đường chéo `cost[u][u] = -1` vì không dùng cung tự nối một thành phố trong hành trình thông thường.
- Điểm xuất phát cố định là thành phố **0**; mọi lời giải đều bắt đầu và kết thúc ở 0.

Đối với n≥2, một hành trình ứng viên phải có dạng:

```text
0 -> v1 -> v2 -> ... -> v(n-1) -> 0

{v1, v2, ..., v(n-1)} = {1, 2, ..., n-1}
mỗi vi xuất hiện đúng một lần
mọi cung liên tiếp đều tồn tại

Tổng chi phí =
    cost[0][v1]
  + cost[v1][v2]
  + ...
  + cost[v(n-1)][0]
```

Cần tìm **chi phí nhỏ nhất** và có thể trả thêm **một hành trình tối ưu**.

**Không được nhầm với đường đi Hamilton:** Đường Hamilton chỉ đi qua mỗi đỉnh một lần và có thể kết thúc ở bất kỳ đỉnh nào. TSP ở đây đòi **quay về điểm đầu**, nên một đường đi qua đủ n đỉnh nhưng thiếu cung về 0 **không phải nghiệm**.

### Quy ước cho trường hợp rất nhỏ

Để API thống nhất, chương trình áp dụng:

- **n=0:** Trả chi phí 0, hành trình `[]`, coi đó là nghiệm rỗng theo quy ước của chương trình, không có cung nào.
- **n=1:** Trả chi phí 0, hành trình `[0,0]`, biểu diễn đứng tại thành phố duy nhất; không yêu cầu một self-loop có thật.
- **n≥2:** Bắt buộc có đủ các cung của chu trình. Nếu không tồn tại chu trình Hamilton, trả chi phí **-1** và hành trình `[]`. Do mọi chi phí cung không âm, -1 không lẫn với một chi phí hợp lệ.

Nếu một đề thi/ứng dụng yêu cầu n≥2 hoặc quy định khác cho hành trình một đỉnh, cần điều chỉnh tiền điều kiện và các trường hợp cơ sở. Không được mặc định quy ước ở một API là định nghĩa duy nhất của TSP.

## 2. Một ví dụ đầy đủ về TSP đối xứng

Xét bốn thành phố với ma trận chi phí:

| Từ / đến | 0 | 1 | 2 | 3 |
| --- | ---: | ---: | ---: | ---: |
| **0** | – | 10 | 15 | 20 |
| **1** | 10 | – | 35 | 25 |
| **2** | 15 | 35 | – | 30 |
| **3** | 20 | 25 | 30 | – |

Một hành trình hợp lệ:

```text
0 -> 1 -> 3 -> 2 -> 0

Chi phí = 10 + 25 + 30 + 15 = 80
```

Hành trình ngược `0->2->3->1->0` cũng có chi phí 80 vì ma trận đối xứng. Nhưng **không phải mọi thứ tự thăm đều tối ưu**; chẳng hạn:

```text
0 -> 1 -> 2 -> 3 -> 0
Chi phí = 10 + 35 + 30 + 20 = 95
```

Ta muốn chứng minh không tồn tại hành trình nào có chi phí dưới 80, nhưng **không muốn liệt kê hết hoán vị** nếu có thể cắt bớt nhánh.

Với n thành phố, cố định điểm đầu là 0 loại bỏ những cách viết chu trình chỉ khác nhau ở việc xoay điểm xuất phát. Số thứ tự còn lại trong bài có hướng đầy đủ là `(n−1)!`. Trong bài đối xứng, hai chiều ngược nhau có cùng chi phí, nhưng chương trình B&B tổng quát bên dưới **không tự loại đối xứng đảo chiều**.

## 3. Nhánh và cận khác gì quay lui thông thường?

**Quay lui (backtracking)** xây lời giải từng bước và loại ngay lựa chọn **vi phạm ràng buộc cứng**. Ví dụ, không được đi đến một thành phố đã thăm; không được dùng một cung -1.

**Nhánh và cận (branch and bound)** còn loại một nhánh **vẫn có thể hoàn thành hợp lệ** nhưng **không thể đạt chi phí tốt hơn** nghiệm đã có. Đây là cắt nhánh theo **giá trị mục tiêu**, không chỉ theo tính hợp lệ.

Ví dụ đã có hành trình hoàn chỉnh trị giá 80. Tại trạng thái đang xét, nếu chứng minh mọi hành trình tiếp theo đều tốn **ít nhất 85**, ta bỏ nhánh ấy mà không cần liệt kê hết các cách đi tiếp. Trái lại, nếu chỉ dự đoán “chắc sẽ tốn 85” bằng heuristic không bảo đảm, **không được dùng dự đoán đó để loại nhánh** trong bộ giải yêu cầu tối ưu tuyệt đối.

### Các thuật ngữ quan trọng

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Incumbent** | Hành trình hoàn chỉnh tốt nhất đã tìm thấy tại thời điểm hiện tại |
| **Cận trên (upper bound, UB)** | Chi phí của incumbent; vì là hành trình hợp lệ nên không nhỏ hơn tối ưu thật |
| **Cận dưới (lower bound, LB)** | Giá trị được chứng minh **không vượt quá** chi phí mọi cách hoàn thành từ một trạng thái |
| **Phân nhánh (branching)** | Thử mỗi thành phố chưa thăm có cung đi tới từ thành phố cuối |
| **Cắt nhánh (pruning)** | Bỏ một trạng thái/ứng viên khi bất khả thi hoặc khi LB≥UB |
| **Hoàn tác (undo)** | Bỏ dấu đã thăm sau khi thử nhánh để không ảnh hưởng nhánh khác |
| **Best-first / depth-first** | Hai thứ tự duyệt cây tìm kiếm; bài này dùng DFS với thử cung rẻ trước |

**Lưu ý chiều bất đẳng thức:** Với bài **tối thiểu hóa**, cắt khi **LB ≥ UB**. Nếu bài là **tối đa hóa**, ý nghĩa cận và phép so sánh phải đảo phù hợp. Không thể lấy nguyên điều kiện trên cho bài tối đa.

## 4. Trạng thái tìm kiếm của TSP

Mỗi nút của cây tìm kiếm được mô tả bởi:

- `last`: thành phố cuối cùng trong đường đi hiện tại.
- `visited[v]`: đã đến thành phố v hay chưa.
- `depth`: số thành phố đã đưa vào đường đi (bao gồm 0).
- `path[0..depth−1]`: thứ tự thăm tương ứng.
- `spent`: tổng chi phí các cung đã đi.
- `best`: chi phí hành trình hoàn chỉnh tốt nhất tìm được.
- `bestPath`: hành trình hoàn chỉnh đạt giá trị best, nếu đã có.

Ban đầu:

```text
last = 0
visited[0] = true
visited[1..n-1] = false
depth = 1
path[0] = 0
spent = 0
best = +infinity nếu chưa có hành trình hoàn chỉnh
```

Một bước đi từ last sang đỉnh v:

```text
Điều kiện:
    not visited[v]
    cost[last][v] >= 0

Hành động:
    visited[v] = true
    path[depth] = v
    spent' = spent + cost[last][v]

Đệ quy:
    SEARCH(v, depth+1, spent')

Hoàn tác:
    visited[v] = false
```

**Không đi về 0 trước khi đã thăm hết các thành phố.** Vì 0 được đánh dấu đã thăm ngay từ đầu, vòng lặp chọn thành phố kế tiếp chỉ xét 1..n−1. Sau khi `depth=n`, ta mới kiểm tra **cung đóng chu trình last->0**.

### Trường hợp đã thăm đủ n thành phố

Nếu `depth=n`:

- Có cung `last->0`: hành trình hợp lệ, giá trị `spent+cost[last][0]`; nếu **nhỏ hơn best** thì cập nhật incumbent và sao chép path thêm 0 vào cuối.
- Không có cung `last->0`: đường hiện tại chỉ là một **đường Hamilton**, không phải chu trình; loại.
- Không tìm thấy hành trình nào khi duyệt xong: bài toán TSP trên đồ thị có cung thiếu có thể **không có nghiệm**.

Chỉ gán `bestPath` khi thực sự có **một chu trình hoàn chỉnh hợp lệ**. Cận dưới nhỏ không bao giờ tự chứng minh tồn tại một chu trình.

## 5. Cận trên ban đầu: nearest-neighbor greedy

Nếu bắt đầu với `best=+infinity`, trong giai đoạn đầu ta cắt theo giá trị rất ít. Một mẹo hữu ích là tìm trước **một hành trình hợp lệ**, dù chưa chắc tối ưu, làm **cận trên**.

Heuristic **láng giềng gần nhất** (*nearest-neighbor*):

1. Bắt đầu tại 0.
2. Khi còn thành phố chưa thăm, chọn một thành phố v chưa thăm mà cung từ last tới v có **chi phí nhỏ nhất**.
3. Nếu hòa chi phí, chọn **chỉ số nhỏ nhất** để đầu ra tái lập được.
4. Nếu không còn cung tới một thành phố chưa thăm, heuristic **thất bại**.
5. Sau khi thăm hết, chỉ chấp nhận nếu có cung từ last về 0.

Nếu tạo được hành trình, đặt `best=greedyCost` và `bestPath=greedyPath`.

### Nearest-neighbor KHÔNG chứng minh tối ưu

TSP có hướng sau cho thấy greedy có thể kém tối ưu:

```text
Ma trận (dấu - nghĩa là không dùng cung tự nối):

     0  1  2  3
0:   -  1  5  9
1:   8  -  2  1
2:   3  8  -  1
3:   2  6  6  -
```

Greedy từ 0 chọn 1 (chi phí 1), sau đó chọn 3 (1), rồi 2 (6), cuối cùng về 0 (3):

```text
0 -> 1 -> 3 -> 2 -> 0
Chi phí greedy = 1 + 1 + 6 + 3 = 11
```

Nhưng hành trình:

```text
0 -> 1 -> 2 -> 3 -> 0
Chi phí = 1 + 2 + 1 + 2 = 6
```

mới là tối ưu. Vì vậy **greedy=11 chỉ là cận trên**, không thể dùng làm kết luận cuối.

### Greedy có thể thất bại dù TSP vẫn có nghiệm

Với ma trận cung thiếu:

```text
     0  1  2  3
0:   -  1  2  -
1:   -  -  1  2
2:   -  1  -  -
3:   2  -  1  -
```

Greedy đi `0->1->2` rồi **không có cung từ 2 sang 3**; nó thất bại. Nhưng có chu trình Hamilton:

```text
0 -> 2 -> 1 -> 3 -> 0
Chi phí = 2 + 1 + 2 + 2 = 7
```

Do đó nếu greedy thất bại, **không được kết luận TSP vô nghiệm**. Chỉ giữ `best=+infinity` rồi để nhánh-và-cận tìm tiếp; một nhánh khác vẫn có thể hoàn thành.

## 6. Thiết kế một cận dưới an toàn cho TSP có hướng

Ta cần ước lượng chi phí hoàn tất của một đường đi từng phần mà **không lớn hơn** chi phí hoàn tất thực sự.

Giả sử:

- `last` là thành phố cuối đã thăm.
- `U` là **tập thành phố chưa thăm**, không chứa thành phố xuất phát 0.
- `spent` là chi phí đã đi.
- Mọi chi phí cung **không âm**; cung -1 nghĩa là không có đường.

### 6.1. Trường hợp chưa thăm hết: U khác rỗng

Trong bất kỳ chu trình Hamilton hoàn tất nào từ trạng thái hiện tại:

1. `last` phải đi tới **một thành phố nào đó trong U**.
2. Mỗi thành phố `u∈U` phải có đúng **một cung đi ra**, dẫn tới một thành phố khác chưa thăm hoặc dẫn về 0; không được dẫn về một thành phố đã đi qua trước đó.
3. Các cung ấy, cộng những cung đã đi, tạo nên hành trình hoàn chỉnh.

Định nghĩa:

```text
A(last,U) =
    min cost[last][v]
    với v ∈ U và tồn tại cung last -> v

B(u,U) =
    min(
        cost[u][0] nếu có cung u -> 0,
        cost[u][v] với v ∈ U, v != u, có cung u -> v
    )

LB(state) =
    spent + A(last,U) + SUM_{u∈U} B(u,U)
```

Nếu không tồn tại cung hợp lệ để tính `A` hoặc một `B(u,U)`, đặt `LB=+infinity`: trạng thái **không có cách hoàn tất** theo các điều kiện cần đó.

Tại sao các tập ứng viên đi ra được giới hạn như vậy?

- Cung rời last phải đi tới **chưa thăm**, vì còn thành phố phải đi và không thể trở lại 0 sớm.
- Mỗi u chưa thăm, khi đến lượt rời u, chỉ có thể đi sang **một u khác chưa thăm khi đó** hoặc về 0 lúc cuối. Tập các ứng viên `(U\{u})∪{0}` là một **tập cho phép rộng hơn hoặc bằng** các cung thực tế theo thứ tự đi trong tương lai.
- Bỏ các ràng buộc như **mỗi đỉnh chỉ nhận một cung đi vào** làm cận yếu hơn, nhưng **không làm cận quá cao**.

### 6.2. Chứng minh LB không vượt chi phí của mọi cách hoàn tất

Xét **một hành trình hoàn tất hợp lệ bất kỳ** từ trạng thái hiện tại.

- Hành trình ấy có một cung rời `last` sang `v∈U`. Theo định nghĩa min, `A(last,U)≤cost[last][v]`.
- Với mỗi `u∈U`, hành trình ấy dùng đúng một cung rời u sang một đỉnh khác trong U hoặc về 0. Theo định nghĩa min, `B(u,U)≤chi phí cung rời u trong hành trình ấy`.
- Cộng các bất đẳng thức trên cho **những cung đi ra từ các đỉnh khác nhau**, cộng `spent`, thu được:

```text
LB(state) <= tổng chi phí hành trình hoàn tất.
```

Vì điều này đúng với **mọi** hành trình hoàn tất hợp lệ, LB là **cận dưới chấp nhận được (admissible lower bound)** cho phần cây tìm kiếm ấy.

**Cảnh báo:** Các cung đạt min khi tính LB có thể kết hợp thành chu trình nhỏ tách biệt (*subtour*) hoặc có hai cung đi vào một đỉnh. **Chúng không nhất thiết tạo thành một tour hợp lệ.** Điều đó không khiến LB sai; nó chỉ khiến LB **thấp hơn** đáp án thật và cắt ít nhánh hơn. Nhánh-và-cận đòi cận **không quá lạc quan về chi phí tối thiểu**, chứ không đòi cận tự tạo được nghiệm.

### 6.3. Trường hợp đã thăm hết: U rỗng

Khi không còn thành phố nào chưa thăm, chỉ còn cung về 0:

```text
LB = spent + cost[last][0], nếu có cung last -> 0
LB = +infinity, nếu không có cung ấy
```

Chương trình Java xử lý trạng thái này trực tiếp ở **lá đệ quy**, không gọi hàm cận dành cho U khác rỗng.

### 6.4. Vì sao chi phí không âm hữu ích?

Vì mọi cung có chi phí ≥0, nếu ở trạng thái từng phần đã có:

```text
spent >= best
```

thì mọi cách hoàn thành sẽ có tổng chi phí ≥spent≥best. Có thể cắt ngay mà không cần tính LB.

Nếu cho phép cạnh âm, điều này **không còn đúng**: một cung âm về sau có thể làm tổng chi phí giảm. Cận dưới dựa trên các cung đi ra vẫn có thể được thiết kế cho trường hợp âm khi cẩn thận, nhưng chương trình này **cố ý từ chối trọng số âm**, trừ -1 dùng làm sentinel không tồn tại cung.

## 7. Ví dụ tính cận dưới từng bước

Dùng lại ma trận có hướng ở phần 5:

```text
     0  1  2  3
0:   -  1  5  9
1:   8  -  2  1
2:   3  8  -  1
3:   2  6  6  -
```

Ban đầu `last=0`, `U={1,2,3}`, `spent=0`.

**Cung đi ra từ last=0 tới U:**

```text
A(0,U) = min(1,5,9) = 1
```

**Mỗi thành phố trong U cần ít nhất một cung đi ra:**

```text
B(1,U) = min(
    cost[1][0]=8,
    cost[1][2]=2,
    cost[1][3]=1
) = 1

B(2,U) = min(
    cost[2][0]=3,
    cost[2][1]=8,
    cost[2][3]=1
) = 1

B(3,U) = min(
    cost[3][0]=2,
    cost[3][1]=6,
    cost[3][2]=6
) = 2
```

Do đó:

```text
LB(root) = spent + A + B1 + B2 + B3
         = 0 + 1 + 1 + 1 + 2
         = 5
```

Ta biết **không tour nào rẻ hơn 5**. Cận này chưa chứng minh một tour giá 5 tồn tại; nghiệm tối ưu thực tế là 6.

### Sau khi chọn 0->1

```text
path = [0,1], last=1, U={2,3}, spent=1

A(1,U) = min(cost[1][2]=2, cost[1][3]=1) = 1

B(2,U) = min(cost[2][0]=3, cost[2][3]=1) = 1
B(3,U) = min(cost[3][0]=2, cost[3][2]=6) = 2

LB = 1 + 1 + 1 + 2 = 5
```

Nhánh này vẫn phải được xét khi `best=11` từ greedy, vì LB=5 <11. Một nhánh khác của trạng thái này tìm được:

```text
0 -> 1 -> 2 -> 3 -> 0
Tổng = 1+2+1+2 = 6
```

Lúc đó best giảm từ 11 xuống 6. Từ đây, mọi trạng thái có LB≥6 đều có thể bị cắt nếu chỉ cần tìm **một** tour tối ưu.

### Vì sao có thể cắt khi LB bằng best?

Giả sử đang có một tour hợp lệ giá 6 và LB của một nhánh mới bằng 6. Nhánh đó có thể chứa tour giá 6 nhưng **không thể chứa tour rẻ hơn 6**. Nếu mục tiêu là **giá trị tối ưu và một nghiệm**, không cần thăm nhánh ấy: incumbent đã tốt bằng. Nếu muốn **liệt kê mọi tour tối ưu** hoặc áp dụng tiêu chí phụ như tour từ điển nhỏ nhất, không thể cắt các nhánh hòa theo cách đơn giản này.

## 8. Phát biểu quy tắc cắt tỉa chính xác

Với `best` là chi phí một tour **đã được kiểm chứng hợp lệ**, các điều kiện cắt an toàn gồm:

1. **Cạnh không tồn tại:** Không được đi qua `cost[last][next] = -1`.
2. **Đã thăm:** Không chọn một thành phố từng thăm; không trở về 0 khi chưa đủ n.
3. **Không thể tiếp diễn:** Cận dưới trả +∞ do một thành phố bắt buộc rời đi không có cung hợp lệ.
4. **Cận dưới đã không tốt hơn:** `LB(state) >= best`.
5. **Chi phí hiện tại đã đủ lớn:** `spent >= best`, an toàn nhờ chi phí cung không âm.

**Quan trọng:** Không được so LB với **chi phí greedy chưa tạo thành tour**. Nếu greedy đi đến ngõ cụt hoặc không quay về 0, nó **không phải cận trên hợp lệ**. Chỉ dùng nó khi đã có một chu trình Hamilton hợp lệ.

### Nhánh-và-cận không bỏ qua tính hợp lệ của tour

Hàm LB có thể cho một số nhỏ dù không tồn tại hành trình hoàn tất. Điều đó chỉ làm ta tốn thêm lượt tìm kiếm; cuối cùng DFS vẫn kiểm tra mọi cung được chọn và cung cuối về 0. Ngược lại, một cận được tính bằng giả định quá chặt có thể đánh giá cao sai chi phí và loại mất lời giải tối ưu. Vì vậy **tính an toàn của LB quan trọng hơn độ “mạnh” của một heuristic**.

## 9. Giả mã đầy đủ của DFS nhánh-và-cận

```text
BEST = +infinity
BEST_TOUR = none

greedyTour = NEAREST_NEIGHBOR_FROM_0()
if greedyTour is a complete Hamiltonian cycle:
    BEST = cost(greedyTour)
    BEST_TOUR = greedyTour

visited[0] = true
path[0] = 0

SEARCH(last, depth, spent):
    if depth == n:
        if edge(last,0) exists:
            total = spent + cost[last][0]
            if total < BEST:
                BEST = total
                BEST_TOUR = path followed by 0
        return

    LB = LOWER_BOUND(last, visited, spent)
    if LB == +infinity or LB >= BEST:
        return

    for each unvisited city v with edge(last,v):
        // Thử cung rẻ trước để dễ cải thiện BEST sớm.
        newCost = spent + cost[last][v]
        if newCost >= BEST:
            continue              // chỉ đúng vì cost >= 0

        visited[v] = true
        path[depth] = v
        SEARCH(v, depth + 1, newCost)
        visited[v] = false          // hoàn tác

SEARCH(0, 1, 0)
```

Hàm `LOWER_BOUND` ở đây dùng đúng công thức min-cung-đi-ra của phần 6, không tự dùng chi phí cạnh ngắn nhất toàn đồ thị như cận đầy đủ.

Trong code, thứ tự thử ứng viên được sắp theo chi phí cung tăng dần; nếu chi phí bằng nhau, thử thành phố có **chỉ số nhỏ hơn** trước. Đây là heuristic **thứ tự nhánh**, không phải phép bỏ nhánh; nó có thể tăng cơ hội tìm được một incumbent tốt sớm, nhưng không tự bảo đảm tối ưu.

### Bất biến trạng thái khi quay lui

Trước mỗi lời gọi `SEARCH`:

- `path[0] = 0`.
- `path[0..depth−1]` gồm **depth thành phố phân biệt**.
- `visited[v]=true` đúng cho những thành phố trong đoạn path đã chọn, không có thành phố khác.
- Mọi cung liên tiếp trong path đều tồn tại.
- `spent` bằng đúng tổng chi phí những cung trong path.
- `best=+infinity` nếu chưa có tour hợp lệ, hoặc bằng chi phí một tour hợp lệ trong `bestTour`.

Bước gán/đệ quy/hoàn tác giữ nguyên bất biến. Chỉ cập nhật best ở lá có **cung quay về 0 hợp lệ** hoặc từ greedy tour đã kiểm chứng.

## 10. Chứng minh tính đúng của thuật toán

### 10.1. Tính hợp lệ của mọi tour được nhận

Một đường đi được mở rộng chỉ bằng một thành phố chưa thăm có cung thực. Sau n mức, nó chứa 0 và mọi thành phố khác **đúng một lần**. Nếu còn cung về 0, đó là chu trình Hamilton hợp lệ; chương trình tính đúng tổng chi phí bằng cách cộng các cung đã đi và cung quay về.

Greedy cũng chỉ được chấp nhận nếu đi đủ mọi thành phố và quay được về 0. Vì vậy `bestTour` được lưu luôn là **một tour thực sự hợp lệ**.

### 10.2. Mọi tour có thể biểu diễn thành một nhánh

Cố định một tour hợp lệ:

```text
0 -> v1 -> v2 -> ... -> v(n-1) -> 0
```

Nếu chưa cắt theo bound, tại mức đầu DFS có thể chọn v1, ở mức sau chọn v2, v.v. Mỗi vi chưa thăm trước khi đến lượt, và các cung của tour đều tồn tại. Vì thuật toán thử mọi ứng viên tiếp diễn hợp lệ, tour này được biểu diễn bởi một đường đi trong cây tìm kiếm.

### 10.3. Chỉ cắt nhánh không thể cải thiện incumbent

Nếu cắt vì không còn cung bắt buộc, nhánh không có cách hoàn tất. Nếu cắt vì LB≥best, theo chứng minh ở phần 6, mọi cách hoàn tất đều có tổng chi phí ≥LB≥best. Do best là **chi phí một tour hợp lệ**, bất kỳ tour bị cắt nào cũng **không tốt hơn** tour đã biết.

Nếu cắt vì spent≥best, tổng chi phí phần còn lại không âm, nên mọi tour hoàn tất có chi phí ≥spent≥best. Không mất cơ hội tìm tour rẻ hơn.

Vậy không có nhánh chứa tour **cải thiện best** bị loại sai.

### 10.4. Kết luận tối ưu và kết thúc

Nếu có một tour tối ưu T*, thì thuật toán hoặc xét đến nó và cập nhật best, hoặc cắt nhánh chứa nó khi đã có incumbent có chi phí **không lớn hơn** T*. Theo định nghĩa tối ưu, incumbent đó phải có cùng chi phí tối ưu. Vì thế kết quả cuối cùng là tối ưu.

Nếu không tồn tại chu trình Hamilton, greedy không thể tạo incumbent, và DFS không thể cập nhật best ở lá. Nó trả “không có nghiệm”.

Mỗi bước xuống cây đệ quy đánh dấu thêm một thành phố chưa thăm; depth tăng nghiêm ngặt tới n. Mỗi mức thử hữu hạn thành phố, nên thuật toán kết thúc.

**Chứng minh không phụ thuộc B&B may mắn tìm được nhánh tốt.** Dù greedy rất kém hoặc không có tour, điều kiện cắt an toàn vẫn đủ giữ tính đúng. Greedy và thứ tự thử cạnh chỉ ảnh hưởng **số nhánh đã xét**, không ảnh hưởng tối ưu cuối cùng.

## 11. Độ phức tạp thời gian và bộ nhớ

### Vét cạn

Cố định điểm đầu 0, có thể có tới `(n−1)!` thứ tự thăm các thành phố còn lại trong đồ thị đầy đủ có hướng. Kiểm tra mỗi tour mất O(n) nếu cộng lại toàn bộ chi phí, nên vét cạn tốn cỡ **O(n·(n−1)!)** thời gian nếu chỉ duyệt mỗi hoán vị một lần và tính chi phí cuối.

### Nhánh và cận

Trong trường hợp xấu, B&B vẫn có thể phải duyệt một số lượng rất lớn các đường đi từng phần. Cận dưới **không bảo đảm** luôn cắt được đủ nhánh để đưa thời gian về đa thức.

Với code ở phần 13:

- Tiền xử lý danh sách ứng viên rẻ trước cho từng đỉnh: O(n² log n) thời gian, O(n²) bộ nhớ.
- Greedy tìm một tour: O(n²) thời gian với ma trận hoặc danh sách đã sắp; không bảo đảm tour tồn tại.
- Mỗi lần tính LB đơn giản quét những thành phố chưa thăm và các ứng viên cung đi ra, nên **O(n²)** thời gian.
- Số trạng thái DFS ở trường hợp xấu không vượt bậc giai thừa, xét theo các hoán vị từng phần của n−1 thành phố.
- Cận trên thời gian tổng quát an toàn là **O(n²·n!)** nếu tính cả LB và chi phí lựa chọn tại mọi trạng thái. Kết quả thực tế phụ thuộc mức độ cắt nhánh và chất lượng incumbent.

**Bộ nhớ:** Ma trận chi phí O(n²), bảng thứ tự ứng viên O(n²), visited/path/bestTour O(n), đệ quy sâu tối đa n. Tổng bộ nhớ **O(n²)**, chưa tính chi phí riêng của máy ảo/đối tượng Java.

### Vì sao không nên tuyên bố “B&B luôn nhanh”?

Một LB rất yếu (ví dụ chỉ lấy chi phí hiện tại) có thể không loại được nhiều nhánh trước khi duyệt gần hết tất cả tour. Một LB chặt hơn giúp giảm số nhánh, nhưng tính LB có thể tốn thêm CPU. B&B là chiến lược **khai thác cấu trúc và giới hạn chi phí**, không phải lời bảo đảm giải TSP lớn trong thời gian đa thức.

**TSP tối ưu tổng quát là NP-hard**, và biến thể quyết định “có tour Hamilton chi phí ≤B không?” có dạng NP-complete trong mô hình thích hợp. Sự khó khăn của bài là lý do những thuật toán chính xác có thể tăng rất nhanh theo n.

## 12. So sánh với các phương pháp TSP khác

| Phương pháp | Độ phức tạp điển hình | Bảo đảm kết quả |
| --- | --- | --- |
| Vét cạn mọi hoán vị | O(n·(n−1)!) | Tối ưu nếu xét đủ tour hợp lệ |
| **Nhánh và cận** | Vẫn có thể giai thừa; giảm nhánh nhờ LB và UB | **Tối ưu chính xác** nếu LB admissible và duyệt/cắt đúng |
| Held–Karp DP theo tập con | O(n²·2ⁿ) thời gian, O(n·2ⁿ) bộ nhớ | **Tối ưu chính xác** với trạng thái và chuyển đầy đủ |
| Nearest-neighbor greedy | O(n²) kiểu ma trận thông dụng | Tour khả thi nếu tìm được, **không có bảo đảm tối ưu** |
| 2-opt / local search | Phụ thuộc số vòng cải thiện và cách chọn cặp | Cải thiện heuristic, có thể mắc tối ưu cục bộ |

**Held–Karp** thường biểu diễn:

```text
dp[S][v] =
    chi phí nhỏ nhất đi từ 0,
    thăm chính xác các thành phố trong S
    và kết thúc ở v.

dp[S∪{u}][u] =
    min(dp[S∪{u}][u],
        dp[S][v] + cost[v][u])

Kết quả:
    min_v(dp[ALL][v] + cost[v][0])
```

Phải bỏ các cung không tồn tại, đảm bảo 0 chỉ là đầu và đích, và kiểm tra kết thúc có cung về 0. Khác với B&B, Held–Karp **gộp** nhiều đường đi cùng tập đã thăm và đỉnh cuối vào một trạng thái; đổi lại dùng bộ nhớ theo số tập con, thường rất lớn.

### TSP đối xứng có thể dùng cận mạnh hơn

Với đồ thị **vô hướng, đối xứng, trọng số không âm**, có thể xây LB từ:

- **Cây khung nhỏ nhất (MST)** trên các thành phố chưa thăm, cộng kết nối cần thiết từ hai đầu đường hiện tại;
- Cận **1-tree** (*one-tree relaxation*) và tối ưu hóa nhân tử Lagrange;
- Relaxation bậc đỉnh, ràng buộc số cung vào/ra;
- Một tour tốt từ nearest-neighbor, 2-opt hoặc heuristic khác để làm UB.

Những cận này thường chặt hơn hoặc được dùng trong bộ giải quy mô lớn, nhưng cần chứng minh tương ứng và cài đặt đúng các trường hợp đặc biệt. **Không tự lấy MST của ma trận có hướng bất đối xứng** rồi coi nó là cận an toàn cho TSP có hướng: đối tượng cây khung và chi phí hai chiều không còn cùng ý nghĩa.

### TSP có hướng và bài toán gán

Với TSP có hướng, một relaxation có thể chọn cung sao cho mỗi thành phố có **một cung vào và một cung ra** mà chưa cấm subtour; đó là kiểu **assignment relaxation**. Chi phí tối ưu của bài toán thoải ràng buộc subtour là một cận dưới tiềm năng, vì mọi tour Hamilton đều là một phép gán hợp lệ đặc biệt.

Cận min-cung-đi-ra trong mã Java thậm chí **không yêu cầu các cung đi vào phân biệt**, nên thường yếu hơn assignment relaxation nhưng dễ giải thích và dễ chứng minh đúng.

## 13. Chương trình Java 17+ hoàn chỉnh

Chương trình cài đặt:

1. **Kiểm tra dữ liệu:** Ma trận vuông; phần đường chéo là -1; ngoài đường chéo chỉ được -1 hoặc trọng số nguyên không âm. Có thể là đồ thị **có hướng và thiếu cung**.
2. **Greedy ban đầu:** Láng giềng gần nhất, thử cung giá thấp trước, hòa theo chỉ số thành phố.
3. **LB admissible:** Min-cung-đi-ra từ last tới tập chưa thăm cộng min-cung-đi-ra của mỗi đỉnh chưa thăm tới một đỉnh khác chưa thăm hoặc thành phố 0.
4. **DFS nhánh-và-cận:** Thử thành phố tiếp theo theo trọng số cung tăng; prune khi LB≥best, không thể hoàn tất hoặc chi phí hiện tại đã ≥best.
5. **Lưu tour tối ưu:** Nếu tìm tour tốt hơn, sao chép path và nối 0.
6. **Thống kê:** `expanded` là số lần vào thủ tục DFS; `pruned` là số nhánh/lượt thử bị loại do cận, chi phí không cải thiện hoặc không có cung về 0 ở lá. Hai con số này phụ thuộc thứ tự thử và heuristic.

Để tránh tràn `int` khi cộng nhiều cung, chi phí tổng và cận dùng **long**; bản thân trọng số cung là **int không âm**. Với n là số nguyên int và mọi cung tối đa `Integer.MAX_VALUE`, tổng tối đa của n cung vẫn nằm trong long về mặt toán học nếu có thể cấp phát được ma trận n×n. Code dùng `Math.addExact` để không bỏ qua tràn nếu mô hình đầu vào thay đổi sau này.

Lưu file **`TspBranchAndBoundDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class TspBranchAndBoundDemo {
    record Result(long greedyCost,
                  long optimum,
                  int[] tour,
                  long expanded,
                  long pruned) {}

    private record Tour(long cost, int[] path) {}

    private static final class Search {
        private static final long INF = Long.MAX_VALUE;

        private final int[][] distance;
        private final int[][] order;
        private final int n;
        private final boolean[] visited;
        private final int[] path;

        private long best = INF;
        private int[] bestPath = new int[0];
        private long expanded = 0;
        private long pruned = 0;

        Search(int[][] distance) {
            this.distance = distance;
            n = distance.length;
            visited = new boolean[n];
            path = new int[n + 1];
            order = buildOrder(distance);
        }

        // Moi dong sap xep thanh pho dich 1..n-1
        // theo gia cung tang dan, hoa theo chi so.
        private static int[][] buildOrder(int[][] d) {
            int n = d.length;
            int[][] sorted = new int[n][Math.max(0, n - 1)];

            for (int from = 0; from < n; from++) {
                final int row = from;
                Integer[] ids = new Integer[n - 1];

                for (int v = 1; v < n; v++) {
                    ids[v - 1] = v;
                }
                Arrays.sort(ids, (a, b) -> {
                    long wa = d[row][a] < 0
                            ? Long.MAX_VALUE : d[row][a];
                    long wb = d[row][b] < 0
                            ? Long.MAX_VALUE : d[row][b];
                    int byCost = Long.compare(wa, wb);
                    return byCost != 0
                            ? byCost : Integer.compare(a, b);
                });

                for (int t = 0; t < ids.length; t++) {
                    sorted[from][t] = ids[t];
                }
            }
            return sorted;
        }

        // Heuristic chi sinh CAN TREN neu la chu trinh day du.
        private Tour nearestNeighbor() {
            boolean[] seen = new boolean[n];
            int[] candidatePath = new int[n + 1];
            seen[0] = true;
            candidatePath[0] = 0;

            int last = 0;
            long spent = 0;

            for (int depth = 1; depth < n; depth++) {
                int next = -1;
                for (int city : order[last]) {
                    if (!seen[city]
                            && distance[last][city] >= 0) {
                        next = city;
                        break;
                    }
                }
                if (next == -1) {
                    return new Tour(-1, new int[0]);
                }

                spent = Math.addExact(
                        spent, distance[last][next]);
                seen[next] = true;
                candidatePath[depth] = next;
                last = next;
            }

            if (distance[last][0] < 0) {
                return new Tour(-1, new int[0]);
            }
            spent = Math.addExact(spent, distance[last][0]);
            candidatePath[n] = 0;
            return new Tour(spent, candidatePath);
        }

        // U khac rong: spent + min(last->U)
        // + sum_{u in U} min(u->(U\{u} hoac 0)).
        private long lowerBound(int last, long spent) {
            long leaveLast = INF;
            for (int v = 1; v < n; v++) {
                if (!visited[v] && distance[last][v] >= 0) {
                    leaveLast = Math.min(
                            leaveLast, distance[last][v]);
                }
            }
            if (leaveLast == INF) {
                return INF;
            }

            long bound = Math.addExact(spent, leaveLast);

            for (int u = 1; u < n; u++) {
                if (visited[u]) {
                    continue;
                }
                long leaveU = distance[u][0] >= 0
                        ? distance[u][0] : INF;

                for (int v = 1; v < n; v++) {
                    if (v != u && !visited[v]
                            && distance[u][v] >= 0) {
                        leaveU = Math.min(
                                leaveU, distance[u][v]);
                    }
                }

                if (leaveU == INF) {
                    return INF;
                }
                bound = Math.addExact(bound, leaveU);
            }
            return bound;
        }

        private void dfs(int last, int depth, long spent) {
            expanded++;

            // Moi thanh pho da tham: kiem tra cung dong vong.
            if (depth == n) {
                if (distance[last][0] < 0) {
                    pruned++;
                    return;
                }

                long total = Math.addExact(
                        spent, distance[last][0]);

                if (total < best) {
                    best = total;
                    bestPath = Arrays.copyOf(path, n + 1);
                    bestPath[n] = 0;
                }
                return;
            }

            long bound = lowerBound(last, spent);
            if (bound == INF || bound >= best) {
                pruned++;
                return;
            }

            for (int next : order[last]) {
                if (visited[next]
                        || distance[last][next] < 0) {
                    continue;
                }

                long nextCost = Math.addExact(
                        spent, distance[last][next]);

                // Hop le vi moi chi phi cung deu khong am.
                if (nextCost >= best) {
                    pruned++;
                    continue;
                }

                visited[next] = true;
                path[depth] = next;
                dfs(next, depth + 1, nextCost);
                visited[next] = false; // hoan tac
            }
        }

        Result run() {
            if (n == 0) {
                return new Result(0, 0, new int[0], 0, 0);
            }
            if (n == 1) {
                return new Result(0, 0,
                        new int[]{0, 0}, 1, 0);
            }

            Tour greedy = nearestNeighbor();
            if (greedy.cost() >= 0) {
                best = greedy.cost();
                bestPath = greedy.path().clone();
            }

            visited[0] = true;
            path[0] = 0;
            dfs(0, 1, 0L);

            return new Result(
                    greedy.cost(),
                    best == INF ? -1 : best,
                    best == INF ? new int[0] : bestPath,
                    expanded, pruned);
        }
    }

    static Result solve(int[][] matrix) {
        Objects.requireNonNull(
                matrix, "matrix must not be null");
        int n = matrix.length;

        for (int i = 0; i < n; i++) {
            Objects.requireNonNull(
                    matrix[i], "matrix row must not be null");
            if (matrix[i].length != n) {
                throw new IllegalArgumentException(
                        "matrix must be square");
            }
            for (int j = 0; j < n; j++) {
                int weight = matrix[i][j];
                if (i == j && weight != -1) {
                    throw new IllegalArgumentException(
                            "diagonal must be -1");
                }
                if (i != j && weight < -1) {
                    throw new IllegalArgumentException(
                            "weights must be nonnegative or -1");
                }
            }
        }

        return new Search(matrix).run();
    }

    private static String costText(long cost) {
        return cost < 0 ? "none" : Long.toString(cost);
    }

    static void show(String label, int[][] matrix) {
        Result result = solve(matrix);
        System.out.println(label
                + ": greedy=" + costText(result.greedyCost())
                + ", optimum=" + costText(result.optimum())
                + ", tour=" + Arrays.toString(result.tour())
                + ", expanded=" + result.expanded()
                + ", pruned=" + result.pruned());
    }

    public static void main(String[] args) {
        show("Symmetric 4", new int[][]{
                {-1, 10, 15, 20},
                {10, -1, 35, 25},
                {15, 35, -1, 30},
                {20, 25, 30, -1}
        });

        show("Directed trap", new int[][]{
                {-1, 1, 5, 9},
                {8, -1, 2, 1},
                {3, 8, -1, 1},
                {2, 6, 6, -1}
        });

        show("Greedy dead end", new int[][]{
                {-1, 1, 2, -1},
                {-1, -1, 1, 2},
                {-1, 1, -1, -1},
                {2, -1, 1, -1}
        });

        show("Sparse impossible", new int[][]{
                {-1, 2, -1},
                {-1, -1, 2},
                {-1, 1, -1}
        });

        show("Zero costs", new int[][]{
                {-1, 0, 5},
                {4, -1, 0},
                {0, 3, -1}
        });

        show("All ones", new int[][]{
                {-1, 1, 1, 1},
                {1, -1, 1, 1},
                {1, 1, -1, 1},
                {1, 1, 1, -1}
        });

        show("Two cities", new int[][]{
                {-1, 3},
                {7, -1}
        });

        show("One city", new int[][]{{-1}});
        show("Empty", new int[0][0]);

        try {
            solve(new int[][]{
                    {-1, 3}, {1}
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("Bad shape: " + ex.getMessage());
        }

        try {
            solve(new int[][]{
                    {0, 2}, {2, -1}
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("Bad diagonal: " + ex.getMessage());
        }

        try {
            solve(new int[][]{
                    {-1, -2}, {2, -1}
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("Bad weight: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac TspBranchAndBoundDemo.java
java TspBranchAndBoundDemo
```

**Stdout chính xác:**

```text
Symmetric 4: greedy=80, optimum=80, tour=[0, 1, 3, 2, 0], expanded=10, pruned=6
Directed trap: greedy=11, optimum=6, tour=[0, 1, 2, 3, 0], expanded=6, pruned=3
Greedy dead end: greedy=none, optimum=7, tour=[0, 2, 1, 3, 0], expanded=5, pruned=1
Sparse impossible: greedy=none, optimum=none, tour=[], expanded=2, pruned=1
Zero costs: greedy=0, optimum=0, tour=[0, 1, 2, 0], expanded=1, pruned=1
All ones: greedy=4, optimum=4, tour=[0, 1, 2, 3, 0], expanded=1, pruned=1
Two cities: greedy=10, optimum=10, tour=[0, 1, 0], expanded=1, pruned=1
One city: greedy=0, optimum=0, tour=[0, 0], expanded=1, pruned=0
Empty: greedy=0, optimum=0, tour=[], expanded=0, pruned=0
Bad shape: matrix must be square
Bad diagonal: diagonal must be -1
Bad weight: weights must be nonnegative or -1
```

### Vì sao một số test chỉ mở rộng một trạng thái?

Ở **Zero costs**, greedy tìm ngay chu trình trị giá 0. Chi phí cung đều không âm, nên **không thể có chu trình rẻ hơn 0**. Cận dưới của gốc cũng bằng 0, thỏa `LB≥best`, nên DFS cắt ngay ở gốc, còn giữ hành trình hợp lệ của greedy.

Ở **All ones** và **Two cities**, greedy đã tìm được hành trình trùng giá trị cận dưới tại gốc. Khi cận dưới bằng incumbent, B&B có thể kết luận không có nhánh nào cải thiện được incumbent, dù chưa tự mở rộng tới lá; điều này **không phải lỗi**.

### Trường hợp greedy thất bại

**Greedy dead end** cho `greedy=none` nhưng B&B vẫn tìm được tour trị giá 7. Điều đó xác nhận code chỉ dùng greedy **nếu đã khép được chu trình**, còn ngõ cụt greedy không khiến thuật toán chính trả “không có nghiệm” sai.

**Sparse impossible** không có cung cần thiết để hoàn thiện bất kỳ tour nào. Thuật toán không gán một cost tùy tiện; trả `optimum=none` và mảng tour rỗng.

### Vì sao cần hai trường hợp n=0 và n=1?

Nếu n=1 mà gọi vòng quay về 0 theo ma trận đường chéo -1, thuật toán sẽ tưởng thiếu self-loop và trả không có nghiệm. Ta quy ước ở một thành phố có hành trình “đứng tại chỗ” giá 0; n=0 cũng có nghiệm rỗng theo quy ước API. Với n≥2, quy tắc phải có cung đóng chu trình được áp dụng đầy đủ.

### Các bộ đếm không phải độ phức tạp lý thuyết

Các con số expanded/pruned chỉ đo **một lần thực thi với thứ tự thử cụ thể**. Nếu đổi tie-break, thứ tự thử cung, cận trên greedy hoặc công thức LB, số nút có thể đổi dù chi phí tối ưu không đổi. Không nên suy từ một test có expanded=1 rằng TSP là bài toán dễ tổng quát.

## 14. Kiểm tra tính đúng của code và các rủi ro cài đặt

### 14.1. Bảo toàn mảng input

Code không thay nội dung của ma trận `matrix`; chỉ dựng một bảng thứ tự thành phố theo chi phí cung. Trong DFS, chỉ thay mảng `visited` và `path` nội bộ.

Sau mỗi nhánh:

```java
visited[next] = true;
path[depth] = next;
dfs(next, depth + 1, nextCost);
visited[next] = false;
```

Ô `path[depth]` không nhất thiết phải đặt về 0 vì `depth` quy định phần prefix hiện đang có hiệu lực và sẽ được ghi đè ở nhánh khác. **Tuy nhiên visited[next] phải trở về false**; nếu quên, những nhánh sau sẽ tưởng thành phố ấy đã thăm và có thể bỏ mất tour tối ưu.

### 14.2. Sao chép hành trình khi thấy nghiệm tốt hơn

Khi tìm thấy một tour tốt hơn, phải **sao chép** path. Nếu chỉ đặt `bestPath=path`, các lần quay lui sau sẽ ghi đè nội dung cùng mảng, khiến cuối cùng bestCost đúng nhưng đường đi được trả **không tương ứng**.

Code dùng:

```java
bestPath = Arrays.copyOf(path, n + 1);
bestPath[n] = 0;
```

Greedy cũng được sao chép khi làm incumbent. Vì vậy kết quả giữ nguyên sau khi DFS tiếp tục thử các nhánh khác.

### 14.3. Cắt sớm theo spent khi trọng số không âm

Ở mỗi cung mới:

```java
if (nextCost >= best) {
    pruned++;
    continue;
}
```

Điều kiện này đúng với **tối thiểu hóa** khi mọi cung còn lại có chi phí ≥0. Nếu cho phép chi phí âm, một tour hoàn chỉnh có thể rẻ hơn nextCost sau khi thêm các cung âm, nên cắt ở đây sẽ sai. Chương trình xác thực ngoài đường chéo không có giá trị dưới -1.

### 14.4. Tránh nhầm -1 với số âm hợp lệ

Ở đồ thị thiếu cung, -1 biểu diễn **không có tuyến đường**. Nếu một bài thực tế cho phép chi phí âm, không nên cố dùng đồng thời -1 làm trọng số âm và sentinel; hãy đổi biểu diễn tồn tại cung thành boolean riêng hoặc một kiểu dữ liệu có trường `exists`, rồi chứng minh lại điều kiện prune.

### 14.5. Không làm hỏng đường đi khi dùng đồ thị bất đối xứng

Không được tự thay `cost[u][v]` bằng `cost[v][u]`. Trong TSP có hướng, `0->1` có thể rất rẻ nhưng `1->0` rất đắt hoặc không tồn tại. Chi phí tour phải dùng đúng **hướng của từng cung**.

Chương trình cài đặt **một bộ giải hỗ trợ đồ thị có hướng**; khi ma trận tình cờ đối xứng, nó vẫn chạy đúng TSP vô hướng có cùng trọng số.

### 14.6. Greedy upper bound không phải lower bound

Nếu greedy tìm được tour giá 11, nó chứng minh **tối ưu ≤11**, không chứng minh **tối ưu ≥11**. Chỉ cận dưới admissible mới cho mệnh đề “mọi tour trong nhánh có chi phí ít nhất LB”. Nhầm chiều bất đẳng thức sẽ phá toàn bộ logic cắt.

### 14.7. Không có cung khác với cung miễn phí

`cost[u][v]=-1`: không được dùng.
`cost[u][v]=0`: cung có thật và chi phí bằng 0.

Nếu viết điều kiện `cost[u][v] > 0` để kiểm tra cung tồn tại, ta loại sai các tuyến đường miễn phí và có thể trả “không có nghiệm” hoặc chi phí không tối ưu.

## 15. Những lỗi phổ biến

1. **Không quay lại điểm xuất phát.** Một đường Hamilton đi đủ n thành phố chưa chắc có cung đóng chu trình.
2. **Tìm kiếm bắt đầu từ mọi thành phố không cần thiết.** Cố định thành phố 0 loại những cách xoay điểm xuất phát khi chu trình có thứ tự.
3. **Quên visited[0]=true.** Có thể quay về 0 giữa chừng rồi thăm trùng.
4. **Cho phép thăm một thành phố hai lần.** Vi phạm điều kiện tour Hamilton.
5. **Không khôi phục visited sau DFS thất bại.** Các nhánh khác bị ô nhiễm trạng thái.
6. **Gán bestPath tham chiếu tới path đang thay đổi.** Hành trình cuối có thể sai dù chi phí đúng.
7. **Cập nhật incumbent từ đường chưa khép chu trình.** Cận trên không hợp lệ có thể gây cắt mất nghiệm tối ưu.
8. **Dùng greedy như chứng minh tối ưu.** Greedy có thể cho 11 trong khi tối ưu 6.
9. **Greedy mắc ngõ cụt rồi trả không có nghiệm.** Có thể tồn tại tour theo thứ tự thăm khác.
10. **Cắt nhánh dựa vào một ước lượng không được chứng minh là LB.** Nếu ước lượng cao hơn chi phí thật, có thể mất nghiệm tối ưu.
11. **Nhầm LB≥UB thành LB≤UB.** Trong bài tối thiểu, chỉ khi LB đã không tốt hơn UB mới cắt theo bound.
12. **Dùng cận theo cạnh nhỏ nhất toàn đồ thị rồi cộng thiếu/sai số cung.** Phải tính đúng số cung còn phải đi; nếu chỉ cần cận đơn giản, chọn công thức chứng minh được.
13. **Đếm trùng chi phí đã đi.** LB ở đây là spent cộng tối thiểu **những cung chưa đi**, không cộng lại một cung thuộc prefix.
14. **Cộng cung về 0 quá sớm.** Khi còn thành phố chưa thăm, không được quay về 0.
15. **Quên cung về 0 ở lá.** Tạo đáp án quá thấp nhưng hành trình không khép kín.
16. **Bỏ trường hợp n=0 hoặc n=1.** Các quy ước đặc biệt cần được công bố rõ.
17. **Coi -1 là cạnh giá -1.** Sentinel biểu diễn không có cung, không phải một cơ hội giảm chi phí.
18. **Coi chi phí 0 là cạnh không tồn tại.** Cung trọng số 0 vẫn hợp lệ.
19. **Mặc định ma trận đối xứng khi đề có hướng.** Đảo chiều hành trình có thể thay đổi chi phí hoặc mất cung.
20. **Dùng int cộng chi phí của nhiều cung.** Có thể tràn và khiến cắt nhánh sai; dùng long.
21. **Dùng +∞ như một tour hợp lệ.** Nếu không có incumbent, không được suy ra tour tồn tại chỉ vì LB hữu hạn.
22. **Cho rằng cận min-cung-đi-ra tự tạo tour.** Các cung min độc lập có thể tạo subtour hay xung đột cung vào; chúng chỉ cho LB.
23. **Không phân biệt cắt vì bất khả thi và cắt vì không thể cải thiện.** Hai lý do cùng hợp lệ nhưng có ý nghĩa khác nhau khi debug.
24. **Cắt nhánh hòa khi phải liệt kê mọi tour tối ưu.** `LB≥best` chỉ thích hợp cho một tour/chi phí tối ưu, không để đếm tất cả tour tối ưu.
25. **Sắp thứ tự thử rẻ trước rồi nghĩ bản thân nó là chứng minh.** Đây là heuristic tăng tốc, không cắt bất cứ ứng viên nào.
26. **Nhầm tour đối xứng với có hướng.** Trong đồ thị có hướng, tour đảo chiều không nhất thiết có cùng chi phí.
27. **Tuyên bố B&B luôn chạy đa thức.** Trường hợp xấu vẫn có số nhánh bùng nổ giai thừa.
28. **Dùng MST của đồ thị bất đối xứng như một bound hiển nhiên.** Phải chọn relaxation đúng cho mô hình có hướng.
29. **Quên chi phí tính LB.** Mỗi nút trong code quét O(n²), nên giảm nút chưa chắc giảm tổng thời gian trên input rất nhỏ.
30. **Không kiểm thử đồ thị không có tour.** Tour không tồn tại là một đầu ra hợp lệ của bài TSP có cung thiếu.
31. **Coi mọi vòng lặp qua các đỉnh là có thể thăm 0 lại.** Ở trạng thái chưa đủ n, 0 phải bị loại khỏi các ứng viên.
32. **Đặt greedy cost làm best khi không có cung quay về 0.** Một đường đi qua đủ đỉnh nhưng thiếu cạnh đóng vòng chưa phải upper bound.
33. **Không kiểm tra ma trận vuông và chỉ số.** Một ô hàng ngắn gây lỗi truy cập không đáng có.
34. **Đếm số node expanded như số tour hoàn chỉnh.** Một lời gọi DFS có thể ở trạng thái từng phần; có thể cắt trước khi đến lá.
35. **Khẳng định LB càng lớn càng đúng.** LB lớn hơn nhưng **không admissible** là sai; cần vừa đủ lớn vừa không vượt chi phí hoàn tất khả thi.

## 16. Bài tập thực hành có đáp án

**Bài 1.** Viết định nghĩa tour Hamilton và công thức tổng chi phí trong TSP xuất phát ở 0.

**Đáp án:** Tour có dạng `0->v1->...->v(n−1)->0` với các thành phố vi là hoán vị của 1..n−1, mọi cung tồn tại. Tổng chi phí là tổng trọng số n cung liên tiếp của chu trình.

**Bài 2.** Với ma trận đối xứng bốn thành phố ở phần 2, chi phí của tour `0->1->3->2->0` là bao nhiêu?

**Đáp án:** 10+25+30+15=**80**, là tối ưu với dữ liệu mẫu.

**Bài 3.** Tại sao cố định điểm đầu 0 không loại mất lời giải tối ưu?

**Đáp án:** Một chu trình Hamilton đi qua tất cả đỉnh có thể được **xoay cách viết** để bắt đầu tại 0 mà không đổi thứ tự chu trình hay tổng chi phí. Điều này đúng cả đồ thị có hướng, vì chỉ xoay chứ **không đảo chiều**.

**Bài 4.** Với greedy 11 và LB của một trạng thái bằng 8, có được cắt không?

**Đáp án:** Chưa được. Có thể tồn tại tour hoàn tất trong nhánh trị giá 8,9 hoặc10, tốt hơn incumbent 11. Chỉ cắt theo LB khi LB≥11.

**Bài 5.** Nếu đã có tour hợp lệ giá 6 và LB của nhánh bằng 6, có thể cắt không?

**Đáp án:** Có nếu chỉ cần chi phí tối ưu và một tour. Nhánh không thể cải thiện giá trị 6. Không dùng cắt hòa nếu cần liệt kê **tất cả** tour đồng tối ưu.

**Bài 6.** Với trạng thái `last=0,U={1,2,3},spent=0` của ma trận directed trap, tính LB.

**Đáp án:** Cung rẻ nhất rời 0 có giá 1; min cung rời các đỉnh 1,2,3 tương ứng là 1,1,2. Vì vậy LB=0+1+1+1+2=**5**. Đây là cận dưới, không phải tour chi phí 5.

**Bài 7.** Greedy `0->1->3->2->0` có chi phí 11 nhưng tồn tại tour `0->1->2->3->0` có chi phí 6. Vậy greedy cung cấp loại cận nào?

**Đáp án:** **Cận trên UB=11**, vì nó là một tour hợp lệ. Đường chi phí 6 chứng minh UB ban đầu chưa tối ưu.

**Bài 8.** Ở ma trận greedy dead end, tại sao greedy báo thất bại nhưng B&B vẫn tìm được đường?

**Đáp án:** Greedy đi 0->1->2 thì thiếu cung sang 3. B&B quay lui thử 0->2->1->3->0 với chi phí 7, nên greedy thất bại không có nghĩa đồ thị vô nghiệm.

**Bài 9.** Nếu một đỉnh u chưa thăm không có cung tới bất kỳ đỉnh chưa thăm khác hoặc về 0, nhánh đó có thể hoàn thành không?

**Đáp án:** Không. Trong tour hoàn chỉnh, u bắt buộc phải có cung đi ra đến một đỉnh tiếp theo hợp lệ. Thiếu tất cả cung ấy là chứng cứ bất khả thi.

**Bài 10.** Chi phí đã đi là 50 và incumbent là 49, các cung đều không âm. Cần tính LB nữa không?

**Đáp án:** Không. Tổng chi phí hoàn tất không thể nhỏ hơn 50≥49, nên có thể cắt ngay bằng spent.

**Bài 11.** Vì sao cận `spent + min(last->U) + Σ min(outgoing(u))` vẫn đúng dù những cung min có thể tạo subtour?

**Đáp án:** Vì mỗi cung min có chi phí **không lớn hơn** cung đi ra tương ứng của bất kỳ tour hoàn tất nào. Ta đã bỏ bớt ràng buộc kết nối/in-degree, làm cận thấp hoặc bằng chi phí thật; cận không cần tự tạo tour.

**Bài 12.** Với n=5 và điểm đầu cố định, có bao nhiêu hoán vị của bốn thành phố còn lại trong đồ thị đầy đủ có hướng?

**Đáp án:** `(5−1)!=4!=24` tour có thứ tự xuất phát ở 0 trước khi xét chi phí. Trong TSP đối xứng có thể ghép các tour đảo chiều cùng chi phí, nhưng code mẫu không làm bước giảm đối xứng đó.

**Bài 13.** Tại sao phải sao chép path khi tìm được best mới?

**Đáp án:** Vì path là mảng làm việc tiếp tục bị sửa trong các nhánh đệ quy sau. Nếu bestPath trỏ chung mảng, đường cuối có thể không khớp chi phí best; `Arrays.copyOf` tạo bản lưu độc lập.

**Bài 14.** Với n=3, các cung có chi phí 0 tạo tour 0->1->2->0. Best và kết quả B&B có gì đặc biệt?

**Đáp án:** Best=0 là cận trên hợp lệ từ một tour. Vì mọi chi phí khác đều không âm, không có tour nào rẻ hơn 0. B&B có thể cắt ở gốc nếu LB cũng bằng 0.

**Bài 15.** Vì sao TSP có cung thiếu cần giá trị “không tồn tại cung” khác với 0?

**Đáp án:** Cung 0 vẫn là một tuyến đi hợp lệ không tốn chi phí; sentinel -1 mới biểu diễn cung không có thật. Nhầm sẽ bỏ mất tour tối ưu hoặc nhận đường không tồn tại.

**Bài 16.** So sánh B&B và Held–Karp về bộ nhớ.

**Đáp án:** B&B DFS với ma trận và thứ tự ứng viên dùng O(n²) bộ nhớ nhưng thời gian xấu nhất vẫn giai thừa. Held–Karp DP theo tập con dùng O(n·2ⁿ) bộ nhớ và O(n²·2ⁿ) thời gian, đổi bộ nhớ lớn để gộp nhiều đường vào cùng trạng thái.

**Bài 17.** Nếu cần in **tất cả tour tối ưu**, cần thay đổi gì về cắt nhánh?

**Đáp án:** Không được loại toàn bộ nhánh chỉ vì LB==best. Cần quản lý các nhánh hòa, thu thập mọi tour cùng giá trị tối ưu và xử lý đối xứng/định nghĩa “khác tour” theo yêu cầu.

**Bài 18.** Có được dùng cắt `spent>=best` khi trọng số có thể âm không?

**Đáp án:** Không. Một cung âm tương lai có thể giảm tổng, nên spent không còn là cận dưới của chi phí hoàn chỉnh. Muốn hỗ trợ cung âm phải sửa mô hình sentinel, cận và chứng minh cắt; mã mẫu không hỗ trợ.

## Ghi nhớ

**TSP nhánh-và-cận** xây đường từ 0, chọn từng thành phố **chưa thăm**, tính chi phí đã đi, rồi quay về 0 khi đã đi đủ n đỉnh. Tìm trước một tour bằng greedy cho **cận trên UB** nếu có thể, nhưng **không coi greedy là nghiệm tối ưu**. Với tập U chưa thăm, một cận dưới an toàn cho đồ thị có hướng trọng số không âm là:

```text
LB = spent
   + min(cost[last][v], v ∈ U)
   + SUM_{u ∈ U} min(
         cost[u][0],
         cost[u][v], v ∈ U, v != u
     )
```

Chỉ xét **cung thật có chi phí ≥0**; cung -1 là không tồn tại. Nếu không còn cung bắt buộc, nhánh vô nghiệm. Khi `LB≥best` từ một tour đã xác thực, nhánh **không thể cải thiện** và được cắt an toàn. Sau mọi nhánh thất bại, phải **hoàn tác visited**. Tính đúng đến từ **cận dưới admissible và duyệt đủ các ứng viên không bị cắt**, không đến từ việc greedy “thường tốt”. B&B có thể nhanh hơn vét cạn nhiều trong thực tế nhưng **trường hợp xấu vẫn tăng giai thừa**.
