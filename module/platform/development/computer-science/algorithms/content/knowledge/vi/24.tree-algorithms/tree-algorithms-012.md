# Gộp thông tin cây con và kỹ thuật giữ dữ liệu nhánh lớn

Trong bài toán **thuật toán trên cây**, rất nhiều truy vấn không hỏi một đường đi mà hỏi **toàn bộ các đỉnh nằm trong cây con** của một đỉnh. Ví dụ: “Cây con của u có bao nhiêu màu khác nhau?”, “Màu nào xuất hiện nhiều nhất trong cây con u?”, “Tổng các nhãn màu có tần suất lớn nhất là bao nhiêu?”. Nếu cứ duyệt lại toàn bộ cây con cho **mỗi** u, trường hợp cây là một đường dây có thể tốn **O(n²)**.

Kỹ thuật **DSU on tree**, còn gọi là **sack** hoặc **giữ dữ liệu nhánh lớn** (*keep the heavy child's data*), giúp giải đồng thời nhiều truy vấn dạng **thống kê trên mọi cây con** mà không phải xây lại cấu trúc đếm từ đầu tại mỗi đỉnh. Ý tưởng chính là:

> Với mỗi đỉnh u, xử lý các **cây con nhỏ** trước rồi bỏ dữ liệu tạm; xử lý **cây con lớn nhất** cuối cùng và **giữ lại dữ liệu** của nó; sau đó thêm toàn bộ các nhánh nhỏ vào dữ liệu đang giữ, thêm u và ghi đáp án. Khi cần trả về cho cha mà u là nhánh nhỏ, xóa dữ liệu của cả cây con u.

Bài học giải thích kỹ thuật này từ nguyên lý, cấu trúc triển khai và chứng minh **O(n log n)**, cùng mã **Java 17+ chạy được**, bao gồm **nén tọa độ màu, DFS preorder, xác định heavy child, stack mô phỏng đệ quy**, một cấu trúc tần suất hỗ trợ **số màu phân biệt / tần suất lớn nhất / tổng màu đồng hạng cao nhất**, kiểm thử các trường hợp có màu âm và 0, phép thay gốc và đối chiếu kết quả với cách đếm trực tiếp.

**Phạm vi chính xác:** Một cây vô hướng được chọn gốc, mỗi đỉnh mang một **nhãn màu nguyên**. Ta trả lời **một lần cho tất cả cây con** của gốc đã chọn, không có cập nhật màu trực tuyến. DSU-on-tree không phải lời giải mặc định cho truy vấn đường đi u–v hoặc thay gốc liên tục; các trường hợp đó có kỹ thuật khác.

## 1. Bài toán mẫu: thống kê tần suất màu trên mọi cây con

Cho một cây có n đỉnh, đánh số 0..n−1, chọn gốc r. Mỗi đỉnh v có màu `color[v]`, có thể là số nguyên âm, bằng 0 hoặc dương. Với cây con `subtree(u)`, định nghĩa:

```text
freq_u(c) =
    số đỉnh v thuộc subtree(u) có color[v] = c

distinct[u] =
    số màu c có freq_u(c) > 0

maxFrequency[u] =
    max_c freq_u(c)

modeSum[u] =
    tổng giá trị c trên mọi màu PHÂN BIỆT c
    thỏa freq_u(c) = maxFrequency[u]
```

Một màu được tính vào `modeSum` **một lần**, không nhân với số lần xuất hiện. Nếu màu 2 và màu 5 cùng xuất hiện ba lần nhiều nhất, `modeSum=2+5=7`, không phải `3×2+3×5`.

Với mọi cây con không rỗng, `maxFrequency>=1`. Theo quy ước, cây rỗng n=0 trả các mảng rỗng; không có một cây con có đỉnh nào để tính mode.

### Ví dụ cây chín đỉnh

```text
                 0 (màu 2)
               /   \
        1 (1)         2 (2)
        /   \         /    \
     3 (1) 4 (3)   5 (2)  6 (3)
                    /   \
                  7 (3) 8 (2)
```

Danh sách cạnh:

```text
(0,1), (0,2), (1,3), (1,4),
(2,5), (2,6), (5,7), (5,8)
```

Mảng màu theo thứ tự đỉnh 0..8:

```text
color = [2,1,2,1,3,2,3,3,2]
```

Bảng kết quả chính xác:

| u | Các màu trong cây con (kể cả lặp) | distinct[u] | maxFrequency[u] | modeSum[u] |
| ---: | --- | ---: | ---: | ---: |
| 0 | 2,1,2,1,3,2,3,3,2 | 3 | 4 | 2 |
| 1 | 1,1,3 | 2 | 2 | 1 |
| 2 | 2,2,3,3,2 | 2 | 3 | 2 |
| 3 | 1 | 1 | 1 | 1 |
| 4 | 3 | 1 | 1 | 3 |
| 5 | 2,3,2 | 2 | 2 | 2 |
| 6 | 3 | 1 | 1 | 3 |
| 7 | 3 | 1 | 1 | 3 |
| 8 | 2 | 1 | 1 | 2 |

Đặc biệt:

- Cây con 0 có **ba màu**. Màu 2 xuất hiện **bốn lần**, nhiều hơn màu 3 ba lần và màu 1 hai lần; modeSum[0]=2.
- Cây con 1 có [1,1,3], nên màu 1 đứng đầu với tần suất 2.
- Cây con 5 có [2,3,2], nên modeSum[5]=2.
- Nếu hai màu cùng có tần suất cao nhất, **phải cộng cả hai nhãn**, không tùy tiện lấy màu nhỏ hơn.

### Vì sao duyệt cây con riêng cho mỗi đỉnh có thể chậm?

Cách đơn giản nhất: với mỗi u, khởi tạo một map tần suất rỗng, duyệt mọi đỉnh trong cây con u, rồi tính distinct, maxFrequency và modeSum. Chi phí tổng là:

```text
SUM_{u thuộc V} size[u]
```

Với cây đường dây gốc ở một đầu:

```text
size = [n, n−1, n−2, ..., 1]
tổng = n + (n−1) + ... + 1
     = n(n+1)/2
     = Θ(n²)
```

Với n lớn và nhiều cây con lồng nhau, việc **đếm lại cùng một màu** ở rất nhiều mức tổ tiên là phần cần tối ưu.

## 2. Cấu trúc gốc, cây con và heavy child

Chọn một gốc r. Với mỗi đỉnh u, xác định:

- `parent[u]`: cha của u, riêng gốc có parent=−1.
- `children[u]`: các con trực tiếp của u trong cây có gốc.
- `size[u]`: tổng số đỉnh thuộc cây con u **kể cả u**.
- `heavy[u]`: đứa con có cây con **lớn nhất** theo size; nếu u là lá thì heavy[u]=−1.
- Các con còn lại gọi là **light children** (*nhánh nhỏ*).

Công thức kích thước:

```text
size[u] = 1 + SUM(size[v])
                với v là con của u
```

Chọn nhánh lớn:

```text
heavy[u] =
    argmax(size[v]) trên mọi con v của u
```

Nếu có nhiều con cùng kích thước lớn nhất, chọn **một** con tùy ý làm heavy; trong mã, chọn **chỉ số đỉnh nhỏ nhất** để kết quả có thể tái lập. Các nhánh còn lại vẫn là light, kể cả nhánh có kích thước bằng nhánh heavy.

**Không nhầm heavy child với con có giá trị màu lớn nhất, chiều sâu lớn nhất hoặc trọng số cạnh lớn nhất.** Tiêu chí của kỹ thuật này là **số đỉnh trong cây con**.

### Ví dụ cây chín đỉnh

Với gốc 0:

```text
size = [9,3,5,1,1,3,1,1,1]

heavy[0] = 2    vì size[2]=5 > size[1]=3
heavy[1] = 3    vì size[3]=size[4]=1; chọn id nhỏ
heavy[2] = 5    vì size[5]=3 > size[6]=1
heavy[5] = 7    vì size[7]=size[8]=1; chọn id nhỏ
heavy[các lá] = -1
```

Mảng heavy:

```text
heavy = [2,3,5,-1,-1,7,-1,-1,-1]
```

Một cạnh cha→con gọi là **heavy edge** nếu con đó là heavy[cha], còn lại là **light edge**. Đây là phân loại tương đối theo **gốc và kích thước cây con**, không phải thuật ngữ “cạnh có trọng số nặng” trong đồ thị có trọng số.

## 3. Cốt lõi “giữ nhánh lớn” hoạt động như thế nào?

Tại một đỉnh u, ta muốn kết quả thống kê của toàn bộ cây con u. Có thể chia nó thành:

```text
subtree(u) =
    {u} cộng các subtree(v) của từng con v
```

Các cây con của những con khác nhau **không giao nhau**. Vì vậy có thể cập nhật cấu trúc đếm lần lượt bằng cách thêm màu của các đỉnh trong từng cây con.

Kỹ thuật DSU-on-tree đặt ra một quy tắc giữ/xóa:

1. **Xử lý mọi con nhẹ v với keep=false.** Mỗi con tự tính đáp án trong cây con v, sau đó xóa dữ liệu đếm đã dùng để không làm lẫn dữ liệu giữa các nhánh.
2. **Xử lý con nặng h với keep=true.** Sau khi giải xong h, **giữ nguyên cấu trúc đếm tần suất** của toàn bộ subtree(h).
3. **Thêm lại các cây con nhẹ** bằng cách duyệt các đỉnh của chúng và cập nhật tần suất vào cấu trúc đang chứa nhánh nặng.
4. **Thêm màu của chính u.** Lúc này cấu trúc đếm chứa **đúng tất cả đỉnh của subtree(u)**; ghi các đáp án cho u.
5. Nếu lời gọi cho u có `keep=false`, **xóa toàn bộ dữ liệu của subtree(u)** trước khi trả về; nếu keep=true, **giữ lại** để cha có thể tái sử dụng.

Tại sao xử lý nhánh lớn **cuối cùng**? Vì nếu đã giữ dữ liệu lớn rồi lại gọi một nhánh nhỏ có thao tác xóa toàn bộ cấu trúc dùng chung, dữ liệu cần giữ sẽ bị phá. Xử lý các nhánh nhỏ với keep=false trước, sau đó xử lý nhánh lớn keep=true, giúp cấu trúc chung mang **đúng dữ liệu nhánh lớn** trước lúc nhập thêm phần còn lại.

### Quy tắc keep rất quan trọng

- `keep=false` **không** có nghĩa “bỏ qua đáp án của cây con này”. Nó vẫn tính và lưu đầy đủ đáp án cho mọi đỉnh bên trong, chỉ **xóa cấu trúc tần suất làm việc** trước khi cha tiếp tục.
- `keep=true` **không** có nghĩa bỏ qua nhánh nhỏ. Mọi nhánh nhẹ được thêm vào lại trước khi ghi đáp án của u.
- Ở lời gọi gốc, thường dùng keep=false để dọn trạng thái sau cùng; các đáp án đã lưu trong mảng không bị mất.

## 4. Giả mã DSU-on-tree / sack

Giả sử đã có `children[u]`, `size[u]`, `heavy[u]`, các đoạn DFS preorder và cấu trúc tần suất `freq[color]`.

```text
SOLVE(u, keep):
    h = heavy[u]

    // 1. Nhánh nhẹ: tính kết quả, rồi xóa dữ liệu.
    for each child v of u:
        if v != h:
            SOLVE(v, false)

    // 2. Nhánh lớn: giữ toàn bộ dữ liệu của nó.
    if h != -1:
        SOLVE(h, true)

    // 3. Gộp lại các nhánh nhẹ vào dữ liệu nhánh lớn.
    for each child v of u:
        if v != h:
            for each vertex x in subtree(v):
                ADD(color[x])

    // 4. Thêm u và lưu đáp án.
    ADD(color[u])

    distinct[u] = currentDistinct
    maxFrequency[u] = currentMaxFrequency
    modeSum[u] = currentModeSum

    // 5. Chỉ xóa khi cha không muốn giữ cây con u.
    if not keep:
        CLEAR_ALL_COLORS_IN_SUBTREE(u)
```

Thứ tự các nhánh nhẹ trong bước 1 không ảnh hưởng đáp án, miễn chúng đều được xử lý với keep=false trước heavy. Kỹ thuật này **không** tự chọn một đường đi duy nhất và không bỏ các đỉnh ở nhánh nhẹ khỏi kết quả: việc “giữ nhánh lớn” chỉ tối ưu **tái sử dụng bộ đếm**.

### Vì sao không gộp bằng cách cộng ba số đáp án của các con?

Với bài đếm **màu phân biệt**, không thể tính:

```text
distinct[u] =
    1 + SUM(distinct[child])
```

vì **cùng một màu có thể xuất hiện ở nhiều cây con khác nhau**. Ví dụ con A có màu {1,2}, con B có {2,3}: tổng số màu của hai con là 2+2=4 nhưng hợp chỉ có {1,2,3}, tức 3 màu. Để gộp chính xác, cần giữ **thông tin màu/tần suất**, không chỉ vài số tổng hợp.

Tương tự, không thể cộng đơn giản `maxFrequency[child]` hay `modeSum[child]` để ra kết quả ở cha: các tần suất của cùng màu ở nhiều nhánh phải được cộng dồn rồi mới tìm mode.

## 5. Dữ liệu lưu trong “sack”: tần suất và các thống kê

Với nhãn màu sau khi nén tọa độ thành id 0..K−1:

```text
freq[id] = số đỉnh đang được giữ có màu id

currentDistinct =
    số id có freq[id] > 0

currentMaxFrequency =
    max(freq[id])

currentModeSum =
    tổng NHÃN MÀU GỐC của mọi id
    có freq[id] = currentMaxFrequency
```

**Nén tọa độ** (*coordinate compression*) chỉ thay màu thành id liên tiếp để truy cập `freq[]` nhanh. Đáp án `modeSum` vẫn cộng **giá trị màu gốc**, không cộng id nén.

Ví dụ màu gốc `[-5, 1000000000, 42]` được ánh xạ thành id 0,2,1 theo thứ tự tăng. Nếu màu −5 và 42 cùng có tần suất lớn nhất, modeSum phải là **37**, không phải 0+1=1.

### 5.1. Thêm một đỉnh x

Gọi c là id màu của x:

```text
old = freq[c]
freq[c] = old + 1
now = freq[c]

if now == 1:
    currentDistinct++

if now > currentMaxFrequency:
    currentMaxFrequency = now
    currentModeSum = originalColor[c]

else if now == currentMaxFrequency:
    currentModeSum += originalColor[c]
```

Tại sao cập nhật modeSum như vậy?

- Nếu tần suất mới **lớn hơn** max cũ, màu c là màu **duy nhất** đạt max mới ngay tại thời điểm ấy, nên modeSum trở thành giá trị màu c.
- Nếu tần suất mới **bằng** max hiện tại, màu c **vừa gia nhập nhóm đồng hạng cao nhất**, nên cộng giá trị c.
- Nếu tần suất mới **nhỏ hơn** max, nhóm mode không đổi.
- Nếu màu c đã ở max trước khi tăng, nó chuyển sang mức max+1 và rơi vào nhánh **lớn hơn**, thay thế nhóm mode cũ; không phải cộng một lần nữa vào nhóm cũ.

**Ví dụ tần suất hòa:**

```text
Đang có:
freq[2]=2
freq[3]=1
max=2, modeSum=2

Thêm màu 3:
freq[3]=2
max=2, modeSum=2+3=5

Thêm màu 2:
freq[2]=3
max=3, modeSum=2
```

Đây là cập nhật O(1) cho mỗi lần thêm đỉnh. Mọi màu được tính theo **giá trị gốc**, kể cả âm và 0.

### 5.2. Vì sao xóa dữ liệu cần cẩn thận?

Khi **giảm tần suất một màu**, `currentMaxFrequency` có thể giảm và tập mode có thể thay đổi. Ví dụ đang có màu 2 xuất hiện ba lần, màu 3 xuất hiện hai lần. Xóa một đỉnh màu 2 làm hai màu cùng tần suất 2, modeSum đổi từ 2 sang 5. Chỉ trừ 1 trong freq mà không cập nhật mode sẽ sai.

Kỹ thuật DSU-on-tree kiểu sack cho phép tránh bài toán xóa từng màu phức tạp bằng một quy tắc quan trọng:

> Khi keep=false, **xóa TOÀN BỘ dữ liệu của cây con hiện có** để đưa cấu trúc tần suất về trạng thái rỗng.

Do đó ta có thể đặt `freq[color[x]]=0` cho từng đỉnh x của cây con u; sau khi đã quét hết, đặt `currentDistinct=0, currentMaxFrequency=0, currentModeSum=0`. Không cần bảo trì mode chính xác **trong lúc đang xóa từng phần**, bởi không ai đọc đáp án giữa quá trình xóa.

**Điều kiện an toàn của phép clear nhanh:** Tại thời điểm clear, cấu trúc chung phải đang chứa **đúng tất cả các đỉnh thuộc subtree(u)**, không chứa dữ liệu của anh em hay tổ tiên. Đây là bất biến được bảo đảm bởi thứ tự xử lý nhánh nhẹ trước, nhánh lớn sau và quy tắc keep.

Nếu thay đổi luồng xử lý và để cấu trúc vẫn chứa dữ liệu bên ngoài subtree(u), câu lệnh đặt freq về 0 theo màu có thể xóa **cả những lần xuất hiện cùng màu ở ngoài cây con**, làm hỏng tất cả các đáp án phía trên.

## 6. Duyệt cây con nhanh bằng DFS preorder

Trong bước thêm các nhánh nhẹ, cần liệt kê toàn bộ đỉnh trong subtree(v). Nếu mỗi lần lại DFS từ v, vẫn có thể đạt cận O(n log n) theo lập luận light-edge khi cài đặt phù hợp, nhưng việc dùng **DFS preorder** khiến truy cập liên tiếp và code rõ ràng hơn.

Định nghĩa:

- `preorder[]`: mảng đỉnh theo thứ tự DFS vào đỉnh, **cha trước con**, hoàn thành nhánh trước khi chuyển nhánh anh em.
- `tin[u]`: vị trí của u trong preorder.
- `size[u]`: số đỉnh trong cây con u.
- `tout[u] = tin[u] + size[u]`: **cận phải loại trừ**.

Cây con u tương ứng đoạn nửa mở:

```text
preorder[tin[u] .. tout[u] - 1]
```

Với ví dụ chín đỉnh, nếu thăm hàng xóm theo chỉ số tăng:

```text
preorder = [0,1,3,4,2,5,7,8,6]

tin[0]=0, size[0]=9  => [0,9)
tin[1]=1, size[1]=3  => [1,4): [1,3,4]
tin[2]=4, size[2]=5  => [4,9): [2,5,7,8,6]
tin[5]=5, size[5]=3  => [5,8): [5,7,8]
```

Thêm cả cây con u:

```text
ADD_SUBTREE(u):
    for i = tin[u] .. tout[u]-1:
        x = preorder[i]
        ADD(color[x])
```

Xóa cả cây con u về trạng thái rỗng:

```text
CLEAR_SUBTREE(u):
    for i = tin[u] .. tout[u]-1:
        x = preorder[i]
        freq[compressedColor[x]] = 0

    currentDistinct = 0
    currentMaxFrequency = 0
    currentModeSum = 0
```

**Lưu ý:** Đoạn trên đúng với **DFS preorder**, không phải với BFS order theo độ sâu. Cũng không phải Euler tour kiểu ghi đỉnh ở cả lần vào và lần ra; ở đây **mỗi đỉnh xuất hiện đúng một lần**.

### 6.1. Tính size và heavy từ một lần duyệt ngược

Có thể duyệt cây bằng DFS lặp để thu `preorder` và `parent`; cha luôn có vị trí trước con. Khởi tạo `size[u]=1`, sau đó duyệt `preorder` ngược, cộng kích thước từng u vào cha:

```text
for i = n-1 down to 1:
    u = preorder[i]
    p = parent[u]

    size[p] += size[u]

    if heavy[p] == -1 OR size[u] > size[heavy[p]]:
        heavy[p] = u
```

Khi xét một con u, tất cả các hậu duệ của u đã được xử lý vì thứ tự ngược, nên size[u] đã hoàn chỉnh. Nếu muốn tie-break theo id nhỏ, thêm điều kiện bằng size nhưng `u < heavy[p]`.

**Dùng stack LIFO và duyệt hàng xóm theo thứ tự giảm** giúp pop theo thứ tự tăng, tạo preorder xác định. Cẩn thận đánh dấu đã phát hiện khi push, không để cùng một đỉnh được push nhiều lần nếu input không phải cây.

## 7. Mô phỏng một phần quá trình giữ nhánh lớn

Dùng cây chín đỉnh, gốc 0:

```text
size[0]=9
  light child 1: size=3
  heavy child 2: size=5

size[2]=5
  heavy child 5: size=3
  light child 6: size=1

size[5]=3
  heavy child 7: size=1  (hòa với 8, chọn id nhỏ)
  light child 8: size=1
```

### 7.1. Xử lý đỉnh 5

- Xử lý lá 8 như light child: ghi đáp án riêng cho 8, rồi clear, cấu trúc chung trở về rỗng.
- Xử lý lá 7 như heavy child và **giữ** dữ liệu màu 3 một lần.
- Thêm toàn bộ light subtree(8): thêm màu 2. Lúc này hai màu 2 và 3 cùng tần suất 1, modeSum=2+3=5.
- Thêm chính đỉnh 5 có màu 2: tần suất màu 2 lên 2, thắng màu 3, modeSum=2.
- Ghi kết quả cho 5: distinct=2, maxFrequency=2, modeSum=2.
- Nếu cha 2 xử lý 5 với keep=true, dữ liệu của {5,7,8} được **giữ nguyên**.

### 7.2. Xử lý đỉnh 2

- Light child 6 (màu 3) đã được tính và clear.
- Heavy child 5 được giữ, trong bộ đếm đang có màu 2 hai lần, màu 3 một lần.
- Thêm light subtree(6): màu 3 tăng lên hai lần, tạo hòa giữa màu 2 và 3, modeSum=5.
- Thêm chính đỉnh 2 màu 2: tần suất màu 2 lên ba lần, modeSum chuyển về 2.
- Ghi cho 2: distinct=2, maxFrequency=3, modeSum=2.

### 7.3. Xử lý gốc 0

- Light child 1 (màu [1,1,3]) được xử lý trước, ghi đáp án của các đỉnh 1,3,4 rồi clear.
- Heavy child 2 (các màu [2,2,3,3,2]) được giữ: màu 2 ba lần, màu 3 hai lần.
- Thêm lại subtree(1) bằng đoạn preorder [1,3,4]: màu 1 hai lần, màu 3 thêm một lần.
- Thêm màu của chính 0 là 2, làm màu 2 xuất hiện bốn lần.

Cuối cùng trong subtree(0):

```text
freq[1]=2
freq[2]=4
freq[3]=3

distinct[0]=3
maxFrequency[0]=4
modeSum[0]=2
```

Đáp án **không phụ thuộc** con nào được chọn làm heavy nếu cùng kích thước; chỉ lượng thao tác tái sử dụng và thứ tự duyệt thay đổi. Tie-break theo id chỉ giúp kiểm tra và tái lập thứ tự.

## 8. Tại sao độ phức tạp giảm xuống O(n log n)?

Đây là phần quan trọng nhất của kỹ thuật. Hãy chứng minh, không chỉ ghi nhớ công thức.

### 8.1. Nhánh nhẹ có kích thước không quá một nửa

Với đỉnh cha u, chọn con nặng h có cây con lớn nhất. Xét một con nhẹ v khác h.

Vì h lớn nhất:

```text
size[h] >= size[v]
```

Mặt khác, cây con u gồm chính u và các cây con con rời nhau:

```text
size[u] >= 1 + size[h] + size[v]
        >= 1 + 2 * size[v]
```

Suy ra:

```text
size[v] < size[u] / 2
```

Hệ quả: **Mỗi khi đi xuống một light edge trên một đường gốc→đỉnh, kích thước cây con giảm ít nhất khoảng một nửa.** Sau k light edges, kích thước còn không quá n/2ᵏ; vì không thể dưới 1, nên k=O(log n).

**Chú ý:** Kết luận này đúng kể cả khi có nhiều con cùng kích thước max; chỉ **một** con được chọn heavy, các con khác là light và vẫn thỏa size[v]≤size[h].

### 8.2. Đếm số lần một đỉnh bị thêm lại

Mỗi đỉnh x được thêm một lần khi xử lý chính nó. Sau đó màu của x có thể bị **thêm lại** khi một tổ tiên u thực hiện bước `ADD_SUBTREE(v)` cho một light child v chứa x.

Những tổ tiên gây thêm lại chính là những tổ tiên mà đường từ u xuống x đi qua **light edge** ở bước đầu liên quan. Vì mỗi đường từ gốc tới x có tối đa O(log n) light edges, một đỉnh x chỉ bị thêm lại **O(log n)** lần.

Do đó tổng số thao tác `ADD_VERTEX(x)` trên toàn bộ thuật toán là:

```text
SUM_x O(log n) = O(n log n)
```

Nếu dùng mảng `freq[]` sau khi nén màu, mỗi lần thêm O(1). Vì vậy phần cập nhật thống kê mất O(n log n).

### 8.3. Chi phí xóa dữ liệu

Khi một subtree(u) được xử lý với keep=false, ta quét toàn bộ đoạn preorder của nó để clear. Một đỉnh x bị clear ở những light-subtree chứa nó trên các mức tổ tiên (và có thể ở chính root). Số lần tương ứng cũng O(log n), nên tổng số đỉnh được quét khi clear là **O(n log n)**.

Vì chỉ **xóa nguyên một sack** rồi đưa tất cả thống kê về 0, clear không phải thực hiện các thao tác tìm lại max phức tạp.

### 8.4. Tiền xử lý và tổng chi phí

- Xây adjacency, DFS preorder, size, heavy: **O(n)** trên cây nếu không cần sort danh sách kề.
- Nén tọa độ nhãn màu bằng Arrays.sort + binarySearch: **O(n log n)**.
- Trong mã mẫu, sắp danh sách kề để output xác định: nhiều nhất **O(n log n)** trên cây.
- DSU-on-tree add/clear: **O(n log n)**.
- Ghi một kết quả cho mỗi đỉnh: **O(n)**.

Tổng thời gian **O(n log n)**, bộ nhớ **O(n+K)=O(n)** với K≤n màu phân biệt. Không cần lưu một HashMap riêng cho mỗi cây con.

### 8.5. Một số dạng cây điển hình

| Cấu trúc | Trực giác |
| --- | --- |
| **Cây dây** | Mỗi đỉnh có tối đa một con, con ấy đều heavy; hầu như không có bước nhập lại nhánh light; gần O(n) thao tác add |
| **Cây sao** | Các lá có size=1; chọn một lá heavy, những lá còn lại light; root thêm các lá một lần; vẫn O(n) thao tác add/clear ở mô hình này |
| **Cây cân bằng** | Một đường có thể có Θ(log n) light edges, nên giới hạn O(n log n) phản ánh việc một số đỉnh được thêm lại nhiều mức |
| **Cây rất lệch, nhiều nhánh** | Bound vẫn O(n log n) vì mỗi lần đi vào light subtree kích thước giảm ít nhất một nửa |

**Không nên tuyên bố mọi test đều đúng n log n thao tác.** Đây là **cận trên**; trên đường dây thuật toán gần tuyến tính. Tốc độ thực tế còn phụ thuộc nén màu, cache và chi phí cấu trúc cập nhật.

## 9. Điều kiện để DSU-on-tree có thể dùng hiệu quả

Kỹ thuật có lợi khi:

1. **Các truy vấn đều trên cây con** của một cây có gốc cố định.
2. Có một cấu trúc dữ liệu tạm hỗ trợ **thêm thông tin của một đỉnh** tương đối nhanh.
3. Có thể **ghi đáp án tại một đỉnh** trực tiếp từ cấu trúc đang giữ.
4. Có thể **xóa sạch dữ liệu tạm** của một subtree sau khi hoàn thành nhánh nhẹ, rồi tái sử dụng bộ nhớ.
5. Các thống kê được yêu cầu cho tất cả hoặc rất nhiều đỉnh; xây mới từng map tốn O(n²).

Các thống kê thường phù hợp:

- Số màu/giá trị phân biệt trong cây con.
- Tần suất lớn nhất của một giá trị trong cây con.
- Tổng các nhãn có tần suất lớn nhất.
- Số màu xuất hiện đúng k lần, nếu có cấu trúc đếm **tần suất của các tần suất** phù hợp.
- Số lần xuất hiện của một màu truy vấn trong mỗi cây con, khi có thể đọc `freq[colorId]` tại thời điểm trả lời.
- Các truy vấn offline mang theo mỗi đỉnh và chỉ cần cấu trúc dữ liệu đang chứa subtree của đỉnh ấy.

### Khi phải dùng cấu trúc cập nhật khác

Nếu cần tìm **median**, k-th smallest, mex, số cặp thỏa điều kiện hoặc giá trị có thứ tự, có thể kết hợp sack với Fenwick/segment tree, ordered set hoặc cấu trúc khác. Khi ấy `ADD` có thể tốn O(log n), đẩy tổng thời gian lên **O(n log² n)** hoặc một mức khác. Không được lấy nguyên O(n log n) nếu thao tác bổ sung không còn O(1).

Nếu cần cập nhật màu online rồi hỏi nhiều lần trên các cây con, bản DSU-on-tree tĩnh **không tự hỗ trợ cập nhật**. Có thể dùng Euler tour + BIT/segment tree cho các loại thống kê ghép được, Mo's algorithm with modifications, heavy-light decomposition hoặc cấu trúc chuyên biệt tùy yêu cầu.

Nếu truy vấn về **đường đi giữa hai đỉnh u,v** thay vì một subtree, DSU-on-tree kiểu sack ở đây không giải quyết trực tiếp. Thường xem xét LCA, heavy-light decomposition, Mo on tree hoặc tree DP phù hợp.

## 10. Phân biệt với small-to-large merging của map

Có một ý tưởng gần gũi: **gộp cấu trúc dữ liệu nhỏ vào cấu trúc lớn** (*small-to-large merging*).

Giả sử mỗi cây con trả về một map `color→count`:

```text
map[u] = map của con có map lớn nhất

for mỗi con v khác:
    for mỗi (color, count) trong map[v]:
        map[u][color] += count

map[u][color[u]]++
```

Nếu luôn gộp **map có ít khóa** vào **map có nhiều khóa**, số lần một khóa di chuyển có thể được khống chế theo lập luận tăng gấp đôi, thường cho cận gần **O(n log n)** thao tác map trong các thiết kế small-to-large đúng; nếu mỗi thao tác map dùng cây cân bằng O(log n), cận thường thành O(n log² n).

**Nhưng đừng đồng nhất hai kỹ thuật:**

| Điểm | DSU-on-tree / sack giữ heavy child | Small-to-large map merging |
| --- | --- | --- |
| Dữ liệu giữ lại | **Một** cấu trúc tần suất dùng chung toàn cục | Map tạm của các cây con, gộp map nhỏ vào map lớn |
| Quyết định “lớn” | Thường theo **size cây con** | Thường theo **số khóa trong map** hoặc kích thước cấu trúc |
| Xử lý nhánh nhẹ | Tính xong, clear; về sau **thêm lại** bằng Euler | Giữ map con, di chuyển/gộp từng entry |
| Cần duyệt lại cây con không? | Có, nhưng chỉ O(log n) lần/đỉnh theo light-edge | Không nhất thiết; thường lặp trên entry của map nhỏ |
| Nên dùng khi | Có ADD/CLEAR toàn bộ và thống kê online trong một sack | Dễ kết hợp trạng thái từng cây con, thao tác merge có tính kết hợp |
| Rủi ro | Sai thứ tự keep/clear làm ô nhiễm bộ đếm | Merge nhầm chiều hoặc copy toàn bộ map khiến tốn O(n²) |

DSU-on-tree trong bài này **không phải cấu trúc Union-Find** (*disjoint-set union*) thường dùng để quản lý các thành phần liên thông. Tên gọi có liên hệ tư tưởng “gộp nhỏ vào lớn”, nhưng kỹ thuật sack dùng **traversal và heavy child trên cây gốc**, không dùng `find/union` để sắp xếp các đỉnh theo thành phần.

### Khác gì heavy-light decomposition (HLD)?

HLD cũng đánh dấu mỗi đỉnh có **heavy child** là con có cây con lớn nhất. Nhưng HLD tách một **đường đi u→v** thành O(log n) đoạn heavy-chain để xử lý truy vấn **trên đường đi** bằng segment tree, còn sack xử lý **một tập đỉnh thuộc subtree** bằng cách **giữ dữ liệu tần suất của nhánh nặng** và thêm lại nhánh nhẹ.

Chúng có chung bổ đề “mỗi đường từ gốc có O(log n) light edges” nhưng **mục tiêu và thao tác triển khai khác nhau**.

## 11. Thiết kế dữ liệu và quy ước đầu vào trong chương trình Java

Chương trình cuối bài nhận:

```text
n       số đỉnh
edges   danh sách n−1 cạnh vô hướng (u,v)
colors  mảng n nhãn màu kiểu int
root    gốc của cây
```

Quy ước:

- Với n≥1, root thuộc [0,n−1]; cạnh vô hướng được thêm **cả hai chiều** vào danh sách kề.
- Cây là **đồ thị vô hướng đơn**: không self-loop, không cạnh song song, liên thông và không chu trình.
- Mọi đỉnh mang **một** màu nguyên; nhãn có thể âm, 0, dương, rất lớn; nén tọa độ trước khi đếm.
- `size[u]` tính **cả u**; `heavy[u]=-1` nếu là lá; nếu nhiều con size lớn nhất bằng nhau, chọn **con id nhỏ nhất**.
- `tin[u]` là index 0-based trong DFS preorder, `tout[u]=tin[u]+size[u]`, cận phải loại trừ.
- Với n=0, API yêu cầu `edges=[]`, `colors=[]` và `root=-1`; trả mảng rỗng theo quy ước.
- Với n≥1, root có parent=−1. Đồ thị chỉ có n−1 cạnh **chưa đủ** để tin là cây; chương trình còn kiểm tra chu trình và liên thông.
- Màu âm, kể cả −1, là **nhãn hợp lệ**, không phải ký hiệu “không có màu”.
- Mode sum dùng long để cộng nhiều nhãn int khác nhau, và `Math.addExact` để phát hiện lỗi miền số nếu mô hình sau này thay đổi.

### Tại sao không dùng đệ quy trong mã mẫu?

Mã minh họa DSU-on-tree thường có hai DFS đệ quy:

```text
dfsSize(u,parent)
dfsSack(u,parent,keep)
```

Nhưng cây dây n rất lớn có chiều sâu O(n); Java có thể ném `StackOverflowError`. Bản hoàn chỉnh dưới đây dùng:

1. **Stack LIFO** để tạo DFS preorder, parent và mảng tin.
2. **Duyệt ngược preorder** để tính size và heavy.
3. **Stack các frame có trạng thái** để mô phỏng chính xác thứ tự: *light children → heavy child → add light subtrees → add u → record → optional clear*.

Cách này tránh phụ thuộc vào độ sâu đệ quy của JVM, đồng thời giữ nguyên lập luận thuật toán O(n log n).

## 12. Chương trình Java 17+ đầy đủ

Lưu thành tệp **`SackOnTreeDemo.java`**. Mã sử dụng màu kiểu int và các mảng kết quả kiểu int/long; không cần HashMap để lưu tần suất vì đã nén tọa độ.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;

public class SackOnTreeDemo {
    record Report(
            int root,
            int[] parent,
            int[] subtreeSize,
            int[] heavy,
            int[] preorder,
            int[] tin,
            int[] tout,
            int[] distinct,
            int[] maxFrequency,
            long[] modeSum) {

        int[] subtreeVertices(int u) {
            if (u < 0 || u >= parent.length) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
            return Arrays.copyOfRange(
                    preorder, tin[u], tout[u]);
        }
    }

    private static final class Frame {
        final int u;
        final boolean keep;
        int phase;
        int nextChild;

        Frame(int u, boolean keep) {
            this.u = u;
            this.keep = keep;
            this.phase = 0;
            this.nextChild = 0;
        }
    }

    private static final class Engine {
        final int n;
        final int root;
        final int[] parent;
        final int[] subtreeSize;
        final int[] heavy;
        final int[] preorder;
        final int[] tin;
        final int[] tout;
        final List<List<Integer>> children;

        final int[] compressed;
        final int[] uniqueColors;
        final int[] freq;

        final int[] distinct;
        final int[] maxFrequency;
        final long[] modeSum;

        int currentDistinct = 0;
        int currentMax = 0;
        long currentModeSum = 0;

        Engine(int n, int[][] edges,
               int[] colors, int root) {
            this.n = n;
            this.root = root;

            parent = new int[n];
            Arrays.fill(parent, -1);
            subtreeSize = new int[n];
            Arrays.fill(subtreeSize, 1);
            heavy = new int[n];
            Arrays.fill(heavy, -1);
            preorder = new int[n];
            tin = new int[n];
            tout = new int[n];

            distinct = new int[n];
            maxFrequency = new int[n];
            modeSum = new long[n];

            List<List<Integer>> adj = new ArrayList<>();
            children = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                adj.add(new ArrayList<>());
                children.add(new ArrayList<>());
            }

            for (int[] e : edges) {
                if (e == null || e.length != 2) {
                    throw new IllegalArgumentException(
                            "each edge must have two endpoints");
                }
                int u = e[0];
                int v = e[1];
                if (u < 0 || u >= n
                        || v < 0 || v >= n) {
                    throw new IllegalArgumentException(
                            "vertex index out of range");
                }
                if (u == v) {
                    throw new IllegalArgumentException(
                            "self-loop is not allowed");
                }
                adj.get(u).add(v);
                adj.get(v).add(u);
            }

            // Co dinh thu tu preorder de stdout tai lap.
            for (List<Integer> neighbors : adj) {
                neighbors.sort(Comparator.naturalOrder());
            }

            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> stack = new ArrayDeque<>();
            stack.push(root);
            seen[root] = true;

            int count = 0;
            while (!stack.isEmpty()) {
                int u = stack.pop();
                tin[u] = count;
                preorder[count++] = u;

                List<Integer> neighbors = adj.get(u);
                // Push nguoc de khi pop thi con id nho truoc.
                for (int i = neighbors.size() - 1; i >= 0; i--) {
                    int v = neighbors.get(i);
                    if (v == parent[u]) {
                        continue;
                    }
                    if (seen[v]) {
                        throw new IllegalArgumentException(
                                "cycle detected");
                    }
                    seen[v] = true;
                    parent[v] = u;
                    stack.push(v);
                }
            }

            if (count != n) {
                throw new IllegalArgumentException(
                        "graph is disconnected");
            }

            // Them moi con vao danh sach cua cha;
            // duyet v tang dan giu tie-break nhat quan.
            for (int v = 0; v < n; v++) {
                if (parent[v] != -1) {
                    children.get(parent[v]).add(v);
                }
            }

            // Reverse preorder: size cua con da hoan chinh
            // truoc khi size cua cha duoc tong hop.
            for (int i = n - 1; i > 0; i--) {
                int u = preorder[i];
                int p = parent[u];

                subtreeSize[p] += subtreeSize[u];

                if (heavy[p] == -1
                        || subtreeSize[u] >
                                subtreeSize[heavy[p]]
                        || (subtreeSize[u] ==
                                subtreeSize[heavy[p]]
                            && u < heavy[p])) {
                    heavy[p] = u;
                }
            }
            for (int u = 0; u < n; u++) {
                tout[u] = tin[u] + subtreeSize[u];
            }

            // Nen mau theo thu tu gia tri tang dan.
            int[] sorted = colors.clone();
            Arrays.sort(sorted);
            int countUnique = 0;
            for (int i = 0; i < n; i++) {
                if (countUnique == 0
                        || sorted[i] != sorted[countUnique - 1]) {
                    sorted[countUnique++] = sorted[i];
                }
            }
            uniqueColors = Arrays.copyOf(
                    sorted, countUnique);
            compressed = new int[n];
            for (int v = 0; v < n; v++) {
                compressed[v] = Arrays.binarySearch(
                        uniqueColors, colors[v]);
            }
            freq = new int[countUnique];
        }

        private void addVertex(int v) {
            int id = compressed[v];
            int now = ++freq[id];

            if (now == 1) {
                currentDistinct++;
            }
            if (now > currentMax) {
                currentMax = now;
                currentModeSum = uniqueColors[id];
            } else if (now == currentMax) {
                currentModeSum = Math.addExact(
                        currentModeSum,
                        (long) uniqueColors[id]);
            }
        }

        private void addSubtree(int u) {
            for (int i = tin[u]; i < tout[u]; i++) {
                addVertex(preorder[i]);
            }
        }

        // Chi goi khi sack CHINH XAC la subtree(u).
        // Khong can bao tri max khi xoa tung phan,
        // vi sau cung toan bo trang thai thanh rong.
        private void clearSubtree(int u) {
            for (int i = tin[u]; i < tout[u]; i++) {
                int v = preorder[i];
                freq[compressed[v]] = 0;
            }
            currentDistinct = 0;
            currentMax = 0;
            currentModeSum = 0;
        }

        Report run() {
            ArrayDeque<Frame> stack = new ArrayDeque<>();
            stack.push(new Frame(root, false));

            while (!stack.isEmpty()) {
                Frame f = stack.peek();
                int u = f.u;
                List<Integer> child = children.get(u);

                if (f.phase == 0) {
                    // Giai doan 0: giai tat ca light
                    // children voi keep=false.
                    while (f.nextChild < child.size()
                            && child.get(f.nextChild)
                                    == heavy[u]) {
                        f.nextChild++;
                    }
                    if (f.nextChild < child.size()) {
                        int v = child.get(f.nextChild++);
                        stack.push(new Frame(v, false));
                    } else {
                        f.phase = 1;
                    }

                } else if (f.phase == 1) {
                    // Giai doan 1: chi heavy child duoc keep.
                    f.phase = 2;
                    if (heavy[u] != -1) {
                        stack.push(new Frame(
                                heavy[u], true));
                    }

                } else {
                    // Giai doan 2: sack dang chua
                    // CHINH XAC subtree(heavy[u]).
                    for (int v : child) {
                        if (v != heavy[u]) {
                            addSubtree(v);
                        }
                    }
                    addVertex(u);

                    distinct[u] = currentDistinct;
                    maxFrequency[u] = currentMax;
                    modeSum[u] = currentModeSum;

                    if (!f.keep) {
                        clearSubtree(u);
                    }
                    stack.pop();
                }
            }

            return new Report(
                    root, parent, subtreeSize, heavy,
                    preorder, tin, tout,
                    distinct, maxFrequency, modeSum);
        }
    }

    static Report analyze(
            int n, int[][] edges,
            int[] colors, int root) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "n must be nonnegative");
        }
        Objects.requireNonNull(
                edges, "edges must not be null");
        Objects.requireNonNull(
                colors, "colors must not be null");

        if (colors.length != n) {
            throw new IllegalArgumentException(
                    "colors length must equal n");
        }

        if (n == 0) {
            if (root != -1) {
                throw new IllegalArgumentException(
                        "empty tree must use root -1");
            }
            if (edges.length != 0) {
                throw new IllegalArgumentException(
                        "empty tree has no edges");
            }
            return new Report(
                    -1, new int[0], new int[0],
                    new int[0], new int[0], new int[0],
                    new int[0], new int[0], new int[0],
                    new long[0]);
        }

        if (root < 0 || root >= n) {
            throw new IllegalArgumentException(
                    "root out of range");
        }
        if (edges.length != n - 1) {
            throw new IllegalArgumentException(
                    "tree must have n - 1 edges");
        }
        return new Engine(
                n, edges, colors, root).run();
    }

    static void show(
            String title, int n,
            int[][] edges, int[] colors, int root) {
        Report r = analyze(n, edges, colors, root);

        System.out.println(title
                + ": root=" + r.root()
                + ", size=" + Arrays.toString(r.subtreeSize())
                + ", heavy=" + Arrays.toString(r.heavy())
                + ", distinct=" + Arrays.toString(r.distinct())
                + ", maxFreq=" + Arrays.toString(r.maxFrequency())
                + ", modeSum=" + Arrays.toString(r.modeSum())
                + ", preorder=" + Arrays.toString(r.preorder()));
    }

    // Oracle doc lap, chi dung trong kiem thu cay nho.
    private static void checkWithBrute(
            int n, int[][] edges,
            int[] colors, int root) {
        Report result = analyze(n, edges, colors, root);

        for (int u = 0; u < n; u++) {
            Map<Integer, Integer> counts = new HashMap<>();
            ArrayDeque<Integer> stack = new ArrayDeque<>();
            stack.push(u);
            int vertices = 0;

            while (!stack.isEmpty()) {
                int x = stack.pop();
                vertices++;
                counts.merge(
                        colors[x], 1, Integer::sum);

                // Oracle co y quet tat ca dinh:
                // cham nhung de doc va doc lap khoi sack.
                for (int v = 0; v < n; v++) {
                    if (result.parent()[v] == x) {
                        stack.push(v);
                    }
                }
            }

            int bestCount = 0;
            long sum = 0;
            for (Map.Entry<Integer, Integer> e
                    : counts.entrySet()) {
                int count = e.getValue();
                if (count > bestCount) {
                    bestCount = count;
                    sum = e.getKey();
                } else if (count == bestCount) {
                    sum += e.getKey();
                }
            }

            if (vertices != result.subtreeSize()[u]
                    || counts.size() != result.distinct()[u]
                    || bestCount != result.maxFrequency()[u]
                    || sum != result.modeSum()[u]) {
                throw new AssertionError(
                        "mismatch at vertex " + u);
            }
        }
    }

    static void randomizedCheck() {
        Random rng = new Random(20261110L);
        int[] palette = {-2, -1, 0, 1, 2, 5};

        for (int trial = 0; trial < 300; trial++) {
            int n = 1 + rng.nextInt(18);
            int[][] edges = new int[n - 1][2];

            for (int v = 1; v < n; v++) {
                edges[v - 1][0] = v;
                edges[v - 1][1] = rng.nextInt(v);
            }

            int[] colors = new int[n];
            for (int v = 0; v < n; v++) {
                colors[v] = palette[
                        rng.nextInt(palette.length)];
            }
            int root = rng.nextInt(n);
            checkWithBrute(n, edges, colors, root);
        }
        System.out.println(
                "Random cross-check: PASS (300 trees)");
    }

    public static void main(String[] args) {
        int[][] nineEdges = {
                {0, 1}, {0, 2},
                {1, 3}, {1, 4},
                {2, 5}, {2, 6},
                {5, 7}, {5, 8}
        };
        int[] nineColors = {
                2, 1, 2, 1, 3, 2, 3, 3, 2
        };

        show("Basic nine", 9,
                nineEdges, nineColors, 0);

        Report base = analyze(
                9, nineEdges, nineColors, 0);
        System.out.println(
                "Subtree 2 in preorder: "
                        + Arrays.toString(
                                base.subtreeVertices(2)));

        show("Reroot at 2", 9,
                nineEdges, nineColors, 2);

        show("Alternating negative", 4,
                new int[][]{
                        {0, 1}, {1, 2}, {2, 3}},
                new int[]{-1, 5, -1, 5}, 0);

        show("Star tie", 5,
                new int[][]{
                        {0, 1}, {0, 2}, {0, 3}, {0, 4}},
                new int[]{10, 20, 30, 20, 30}, 0);

        show("All equal", 4,
                new int[][]{
                        {0, 1}, {0, 2}, {0, 3}},
                new int[]{7, 7, 7, 7}, 0);

        show("Single zero", 1,
                new int[0][], new int[]{0}, 0);
        show("Empty", 0,
                new int[0][], new int[0], -1);

        try {
            analyze(3,
                    new int[][]{{0, 1}},
                    new int[]{1, 2, 3}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad count: " + ex.getMessage());
        }

        try {
            analyze(4,
                    new int[][]{
                            {0, 1}, {1, 2}, {2, 0}},
                    new int[]{1, 2, 3, 4}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Cycle: " + ex.getMessage());
        }

        try {
            analyze(2,
                    new int[][]{{0, 0}},
                    new int[]{1, 2}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Self-loop: " + ex.getMessage());
        }

        try {
            analyze(2,
                    new int[][]{{0, 2}},
                    new int[]{1, 2}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad endpoint: " + ex.getMessage());
        }

        try {
            analyze(2,
                    new int[][]{{0, 1}},
                    new int[]{1}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad colors: " + ex.getMessage());
        }

        try {
            analyze(2,
                    new int[][]{{0, 1}},
                    new int[]{1, 2}, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad root: " + ex.getMessage());
        }

        try {
            analyze(0, new int[0][],
                    new int[0], 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad empty root: " + ex.getMessage());
        }

        try {
            analyze(3,
                    new int[][]{{0, 1}, {0, 1}},
                    new int[]{1, 2, 3}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Duplicate edge: " + ex.getMessage());
        }

        randomizedCheck();
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac SackOnTreeDemo.java
java SackOnTreeDemo
```

**Stdout chính xác:**

```text
Basic nine: root=0, size=[9, 3, 5, 1, 1, 3, 1, 1, 1], heavy=[2, 3, 5, -1, -1, 7, -1, -1, -1], distinct=[3, 2, 2, 1, 1, 2, 1, 1, 1], maxFreq=[4, 2, 3, 1, 1, 2, 1, 1, 1], modeSum=[2, 1, 2, 1, 3, 2, 3, 3, 2], preorder=[0, 1, 3, 4, 2, 5, 7, 8, 6]
Subtree 2 in preorder: [2, 5, 7, 8, 6]
Reroot at 2: root=2, size=[4, 3, 9, 1, 1, 3, 1, 1, 1], heavy=[1, 3, 0, -1, -1, 7, -1, -1, -1], distinct=[3, 2, 3, 1, 1, 2, 1, 1, 1], maxFreq=[2, 2, 4, 1, 1, 2, 1, 1, 1], modeSum=[1, 1, 2, 1, 3, 2, 3, 3, 2], preorder=[2, 0, 1, 3, 4, 5, 7, 8, 6]
Alternating negative: root=0, size=[4, 3, 2, 1], heavy=[1, 2, 3, -1], distinct=[2, 2, 2, 1], maxFreq=[2, 2, 1, 1], modeSum=[4, 5, 4, 5], preorder=[0, 1, 2, 3]
Star tie: root=0, size=[5, 1, 1, 1, 1], heavy=[1, -1, -1, -1, -1], distinct=[3, 1, 1, 1, 1], maxFreq=[2, 1, 1, 1, 1], modeSum=[50, 20, 30, 20, 30], preorder=[0, 1, 2, 3, 4]
All equal: root=0, size=[4, 1, 1, 1], heavy=[1, -1, -1, -1], distinct=[1, 1, 1, 1], maxFreq=[4, 1, 1, 1], modeSum=[7, 7, 7, 7], preorder=[0, 1, 2, 3]
Single zero: root=0, size=[1], heavy=[-1], distinct=[1], maxFreq=[1], modeSum=[0], preorder=[0]
Empty: root=-1, size=[], heavy=[], distinct=[], maxFreq=[], modeSum=[], preorder=[]
Bad count: tree must have n - 1 edges
Cycle: cycle detected
Self-loop: self-loop is not allowed
Bad endpoint: vertex index out of range
Bad colors: colors length must equal n
Bad root: root out of range
Bad empty root: empty tree must use root -1
Duplicate edge: cycle detected
Random cross-check: PASS (300 trees)
```

### Giải thích các test quan trọng

**Basic nine:** Có ba màu 1,2,3 trong cây con gốc 0. Màu 2 đạt tần suất cao nhất là 4, nên modeSum[0]=2. Nhánh lớn của 0 là 2; nhánh lớn của 2 là 5.

**Subtree 2 in preorder:** Đoạn `[tin[2],tout[2])=[4,9)` trong preorder là `[2,5,7,8,6]`. Nó chứa đúng năm đỉnh của cây con 2 dù thứ tự của chúng không tăng theo id.

**Reroot at 2:** Chọn gốc mới 2 trên cùng cây và cùng nhãn màu. Cây con của đỉnh 0 trở thành {0,1,3,4}; nó có ba màu, trong đó màu 1 xuất hiện hai lần nên modeSum[0]=1. Toàn bộ cây con của gốc 2 vẫn gồm cả chín đỉnh, có modeSum[2]=2.

**Alternating negative:** Trên cây đường dây, toàn bộ gốc 0 có hai nhãn −1 và 5, mỗi nhãn hai lần. Chúng **hòa tần suất**, nên modeSum[0]=−1+5=4. Giá trị −1 là một nhãn màu bình thường, không phải sentinel.

**Star tie:** Cây sao gốc 0 có nhãn 20 và 30 cùng xuất hiện hai lần nhiều nhất; modeSum[0]=20+30=50. Không được chỉ chọn một trong hai.

**All equal:** Tất cả đỉnh màu 7. Root có distinct=1, maxFreq=4, modeSum=7. Mỗi lá có maxFreq=1.

**Single zero:** Một đỉnh màu 0 có distinct=1 và maxFreq=1 nhưng modeSum=0. **Tổng mode bằng 0 không có nghĩa cây con rỗng**.

**Empty:** Quy ước API cho phép n=0 nếu root=−1; không có đỉnh hoặc cây con hợp lệ để truy vấn.

**Các lỗi đầu vào:** Mã từ chối thiếu cạnh, chu trình dù có n−1 cạnh, self-loop, đầu cạnh ngoài miền, chiều dài colors sai, root ngoài miền và cạnh song song. Không lẳng lặng sửa đồ thị không phải cây thành một input khác.

**Random cross-check:** Dùng seed cố định để sinh 300 cây nhỏ, màu gồm cả số âm/0, gốc ngẫu nhiên. So sánh từng đáp án của sack với **cách duyệt đếm trực tiếp của từng cây con**; nếu có sai khác, chương trình ném AssertionError thay vì in PASS. Kiểm thử này là lớp xác minh thực hành, bổ sung cho chứng minh toán học.

## 13. Chứng minh tính đúng của DSU-on-tree

### 13.1. Bất biến trạng thái ở mỗi lời gọi

Xét thủ tục khái niệm `SOLVE(u,keep)`. Các đáp án của những đỉnh đã xử lý được lưu riêng trong mảng, còn bộ đếm làm việc có trạng thái:

- Trước khi bắt đầu xử lý u trong thứ tự sack, dữ liệu làm việc **rỗng**.
- Sau khi xử lý một con nhẹ v với keep=false, các đáp án bên trong subtree(v) đã ghi chính xác và dữ liệu làm việc **rỗng trở lại**.
- Sau khi xử lý con nặng h với keep=true, dữ liệu làm việc chứa **đúng những đỉnh của subtree(h)**.
- Sau bước thêm các con nhẹ và u, dữ liệu làm việc chứa **đúng những đỉnh của subtree(u)**, mỗi đỉnh đúng một lần.
- Nếu keep=false, clear đưa dữ liệu làm việc về **rỗng**; nếu keep=true, giữ nguyên đúng subtree(u).

Cơ sở: Một lá không có con. Thêm màu của nó tạo sack gồm đúng một đỉnh; ghi đáp án đúng. Nếu keep=false, clear nó trở về rỗng.

Bước quy nạp: Giả sử bất biến đúng cho mọi con v của u. Các con nhẹ đều làm việc trên dữ liệu rỗng và xóa sạch sau khi xong. Nhánh nặng giữ đúng dữ liệu của nó. Vì các cây con con **rời nhau**, thêm từng đỉnh của mọi cây con nhẹ vào sack nặng không gây trùng đỉnh. Thêm u tạo đúng toàn bộ subtree(u). Phép add duy trì tần suất đúng, nên distinct/maxFrequency/modeSum của u đều chính xác. Cuối cùng keep quyết định giữ hoặc clear như bất biến yêu cầu.

### 13.2. Vì sao các thống kê cộng được khi thêm màu?

Với mỗi màu c, `freq[c]` là số đỉnh đã thêm có màu c. Mỗi đỉnh được thêm **một lần trong trạng thái sack hiện tại**, nên sau khi gộp đủ subtree(u), `freq[c]=freq_u(c)`.

- `distinct` tăng đúng khi màu c chuyển từ 0 sang 1.
- `maxFrequency` cập nhật đúng nếu tần suất vừa tăng vượt max cũ.
- `modeSum` được thay bằng màu c khi max mới xuất hiện, hoặc cộng c khi màu c vừa hòa max; những màu thấp hơn max không đóng góp.

Quy nạp trên số lần add chứng minh các biến tóm tắt luôn đúng sau mỗi lần thêm. Vì không có thao tác xóa lẻ trong giai đoạn quan sát đáp án, không xảy ra tình huống phải tính lại max khi giảm tần suất.

### 13.3. Vì sao clear trực tiếp freq=0 không gây mất dữ liệu ngoài cây con?

Trong bất biến, khi phải clear subtree(u) với keep=false, sack chứa đúng **tập đỉnh subtree(u)**. Mọi tần suất khác 0 đều đến từ các đỉnh trong đoạn preorder ấy. Đặt freq của từng màu xuất hiện trong đoạn về 0, rồi reset các biến tóm tắt, sẽ đưa cả cấu trúc về rỗng.

Nếu cùng màu xuất hiện nhiều lần, việc gán 0 nhiều lần không ảnh hưởng kết quả cuối; không cần biết giá trị tần suất giảm qua những bước trung gian vì không có truy vấn đọc giữa quá trình clear.

### 13.4. Vì sao mọi đỉnh được giải đúng đúng một lần?

Mỗi đỉnh thuộc chính một vị trí trong cây có gốc. Trình tự các frame xử lý gọi giải **mỗi con đúng một lần**, và u được ghi đáp án ở phase cuối đúng một lần. Các bước `ADD_SUBTREE` chỉ cập nhật tần suất, **không tái giải** các đỉnh đã tính. Vì cây có n đỉnh hữu hạn, thuật toán đi hết và có đáp án cho cả n đỉnh.

### 13.5. Tính đúng của nén màu

Nén màu ánh xạ một-một từ mỗi **giá trị màu phân biệt** sang một id liên tiếp. Hai đỉnh có cùng màu gốc nhận cùng id, hai màu khác nhau nhận id khác nhau; do đó **mọi tần suất và số màu phân biệt được giữ nguyên**.

Với modeSum, chương trình cộng `uniqueColors[id]` là nhãn gốc của id đó, nên tổng màu đồng hạng vẫn chính xác dù nén màu thay đổi giá trị id.

## 14. Trường hợp biên và những giả thiết quan trọng

### 14.1. Nhiều màu trùng nhau

Nếu mọi đỉnh đều mang màu c, trong cây con u:

```text
distinct[u] = 1
maxFrequency[u] = size[u]
modeSum[u] = c
```

Không phải `modeSum[u]=size[u]×c`; mỗi nhãn màu đồng hạng được cộng **một lần**.

### 14.2. Mọi màu đều khác nhau

Nếu mỗi đỉnh có một màu riêng, trong cây con u:

```text
distinct[u] = size[u]
maxFrequency[u] = 1
modeSum[u] = tổng các NHÃN MÀU của các đỉnh trong cây con u
```

Do mọi màu đều xuất hiện đúng một lần, tất cả hòa max=1.

### 14.3. Màu âm và màu 0

Nhãn −1 hay 0 là giá trị bình thường. Không được dùng `color==-1` để đánh dấu thiếu màu hoặc `modeSum==0` để kết luận dữ liệu rỗng. Ví dụ hai màu −1 và 1 mỗi màu hai lần có modeSum=0 nhưng distinct=2, maxFrequency=2.

Nén tọa độ giúp xử lý cả nhãn cỡ `Integer.MIN_VALUE`, `Integer.MAX_VALUE` mà không cần tạo mảng freq theo giá trị màu gốc.

### 14.4. Gốc và hướng cạnh

Input là **cây vô hướng**. Để trả cây con, phải chọn gốc rõ ràng và xác định parent/children. Không dùng hướng xuất hiện của cặp (u,v) trong input để suy ra u là cha.

Nếu đổi root, subtree của một đỉnh có thể đổi, nên toàn bộ mảng size, heavy, tin/tout và các đáp án **phải tính lại** hoặc dùng một cấu trúc chuyên biệt phục vụ reroot queries. Ví dụ code chạy lại từ gốc 2 để minh họa.

### 14.5. Cây không hợp lệ

Thuật toán sack dựa vào việc các cây con con của u **không giao nhau**. Trên đồ thị có chu trình, không tồn tại quan hệ cha–con kiểu cây một cách tự nhiên cho mọi cạnh; việc đếm có thể lặp hoặc bỏ đỉnh. Code yêu cầu n−1 cạnh, kiểm tra chỉ số/self-loop, rồi phát hiện chu trình và yêu cầu duyệt đủ n đỉnh.

**n−1 cạnh không đủ để kết luận là cây**: có thể một thành phần chứa chu trình và một đỉnh khác cô lập. Phải kiểm tra thêm.

### 14.6. Cây rất sâu và giới hạn bộ nhớ

DFS đệ quy độ sâu n có thể tràn call stack của Java ở cây dây. Mã dùng `ArrayDeque` để mô phỏng cả DFS tạo preorder lẫn lời gọi sack, nên độ sâu được lưu trong cấu trúc dữ liệu heap thay vì JVM call stack.

Bộ nhớ vẫn là O(n) trên cây, gồm adjacency, children, preorder, tin/tout, size/heavy, bảng nén màu, freq, mảng đáp án và stack frame. Không cần giữ một bản sao map khổng lồ ở mọi đỉnh.

### 14.7. Khi sửa bài thành truy vấn đếm theo giá trị k

Nếu tại mỗi u cần biết “có bao nhiêu màu xuất hiện **đúng k lần**”, một mảng `countOfFrequency[f]` có thể cập nhật khi thêm màu c:

```text
old = freq[c]

if old > 0:
    countOfFrequency[old]--

freq[c] = old + 1
countOfFrequency[old+1]++
```

Khi sack chứa subtree(u), trả `countOfFrequency[k]`. Khi clear toàn bộ subtree, phải reset cả `freq` và những ô countOfFrequency đã dùng, hoặc có cơ chế timestamp để đặt lại trạng thái hiệu quả; không được chỉ reset freq rồi quên mảng phụ.

### 14.8. Khi bài yêu cầu tổng màu có tần suất lớn nhất nhưng nhãn rất lớn

Mã dùng nhãn gốc kiểu int và modeSum kiểu long. Số màu phân biệt tối đa n, và tổng của các giá trị int khác nhau nằm trong miền long trong những giới hạn kích thước mảng Java thực tế; dùng `Math.addExact` còn cho khả năng phát hiện lỗi nếu thay đổi mô hình dữ liệu.

Nếu nhãn màu được lưu trực tiếp bằng long cực lớn, tổng của nhiều mode có thể vượt long; khi đó chuyển modeSum sang BigInteger hoặc một cách cộng có kiểm tra đúng phạm vi.

## 15. Những lỗi thường gặp

1. **Không chọn gốc trước khi định nghĩa cây con.** Cây vô hướng không có khái niệm con/cha cố định cho tới khi chọn root.
2. **Chọn heavy child bằng depth hoặc giá trị màu.** Heavy được chọn theo **size cây con**.
3. **Cho size của lá bằng 0** trong khi size phải tính cả chính đỉnh, khiến chọn heavy sai.
4. **Chỉ tính size một lần ở cha trước khi có size các con.** Phải dùng postorder hoặc reverse preorder.
5. **Xử lý heavy child trước rồi xử lý light child có clear.** Clear của light có thể xóa dữ liệu heavy đã giữ.
6. **Dùng keep=false ở heavy child.** Không tái sử dụng được sack lớn và có thể tăng độ phức tạp.
7. **Dùng keep=true ở mọi light child.** Nhiều nhánh tồn tại cùng lúc trong sack trước khi gộp, gây đếm lẫn và phá bất biến.
8. **Quên thêm lại các light subtrees sau khi giữ heavy.** Đáp án của cha sẽ thiếu màu từ nhánh nhỏ.
9. **Quên thêm màu của chính u.** Thiếu một đỉnh trong mọi subtree answer.
10. **Quên clear khi keep=false.** Dữ liệu nhánh trước tràn sang nhánh kế tiếp.
11. **Xóa từng màu nhưng không cập nhật maxFrequency/modeSum.** Nếu cần xóa lẻ, phải duy trì thống kê đầy đủ; mã này chỉ clear nguyên sack.
12. **Clear bằng cách đặt freq về 0 trong khi sack chứa đỉnh ngoài subtree(u).** Có thể xóa luôn số lần xuất hiện màu đó ở nhánh khác.
13. **Clear tất cả K màu ở mỗi light subtree mà không tính chi phí.** Có thể làm mất cận O(n log n) khi K lớn; quét đúng đoạn Euler subtree.
14. **Dùng BFS order thay DFS preorder để lấy đoạn [tin,tin+size).** Các đỉnh cây con có thể bị xen kẽ, dẫn tới thêm/xóa nhầm.
15. **Quên cận phải là loại trừ.** Đoạn đúng là [tin,tout), với tout=tin+size; truy cập đến tout sẽ lấn sang nhánh khác.
16. **Thêm lại cả heavy subtree ở phase gộp.** Đếm màu trong nhánh lớn **hai lần**.
17. **Cộng số distinct của từng con thay vì gộp tần suất.** Một màu xuất hiện ở nhiều nhánh sẽ bị đếm trùng.
18. **Cộng maxFrequency của các con.** Các mode có thể khác màu nên không thể cộng trực tiếp.
19. **Cộng modeSum của các con.** Tần suất ở cha cần được cộng giữa nhánh trước khi xác định màu đứng đầu.
20. **Nhầm modeSum là tổng màu của tất cả đỉnh có màu thắng.** ModeSum cộng **mỗi nhãn mode đúng một lần**.
21. **Quên trường hợp nhiều màu hòa tần suất cao nhất.** Phải cộng toàn bộ nhãn cùng max.
22. **Dùng id màu nén thay cho giá trị gốc trong modeSum.** Trả kết quả sai khi nhãn gốc không phải [0..K−1].
23. **Dùng màu 0 hoặc −1 làm sentinel “không có màu”.** Đây có thể là giá trị input hoàn toàn hợp lệ.
24. **Cho rằng modeSum=0 nghĩa là không có màu.** Các màu âm/dương có thể triệt tiêu nhau; màu 0 đơn lẻ cũng tạo tổng 0.
25. **Không kiểm tra cạnh trùng, self-loop, chu trình và liên thông.** DSU-on-tree yêu cầu cấu trúc là cây.
26. **Coi n−1 cạnh là chứng minh đủ để gọi input là cây.** Có thể có chu trình ở một thành phần và đỉnh cô lập.
27. **Quên đếm root trong preorder/size.** Mọi cây con, nhất là cây con gốc, phải tính chính u.
28. **Sắp adjacency mà không đảo chiều khi push stack LIFO.** Có thể ra preorder khác mong đợi; đáp án thống kê vẫn đúng nhưng test output không khớp.
29. **Tưởng đổi heavy tie-break làm đổi đáp án.** Chỉ thứ tự/thao tác đổi; đáp án phụ thuộc tập đỉnh chứ không phụ thuộc con heavy được chọn.
30. **Đồng nhất DSU-on-tree với Union-Find DSU.** Sack không quản lý các thành phần kết nối bằng find/union.
31. **Đồng nhất sack với heavy-light decomposition.** Hai kỹ thuật dùng light-edge bound nhưng truy vấn mục tiêu và cách dùng khác nhau.
32. **Tuyên bố O(n log n) khi ADD dùng một cấu trúc O(log n) mà không nhân chi phí.** Khi ấy thường thành O(n log² n).
33. **Dùng đệ quy trên cây dây lớn và bỏ qua StackOverflowError.** Có thể dùng stack frame tường minh.
34. **Tạo một HashMap mới rồi duyệt toàn bộ subtree cho mọi u.** Trường hợp dây sẽ bị O(n²).
35. **Dùng nén màu mà không bảo toàn ánh xạ nhãn gốc.** Không thể khôi phục modeSum chính xác.
36. **Chỉ kiểm thử trên cây cân bằng, bỏ qua cây dây và cây sao.** Đây là những input phát hiện rõ lỗi hiệu năng và thứ tự clear.
37. **Không đối chiếu với oracle trên cây nhỏ.** Lỗi giữ/xóa thường chỉ lộ ở nhánh có nhiều màu trùng giữa các con.
38. **Giả định sack tĩnh hỗ trợ cập nhật màu trực tuyến.** Với các cập nhật xen kẽ truy vấn cần giải pháp khác.
39. **Dùng thuật toán cho truy vấn đường đi bất kỳ mà không biến đổi bài toán.** Sack ở đây trả kết quả trên subtree, không trực tiếp trên path u–v.
40. **Không phân biệt tiền xử lý với thời gian mỗi truy vấn.** Bài này tính trước mọi đáp án trong O(n log n), sau đó lấy kết quả của từng u bằng O(1) từ mảng.

## 16. Bài tập tự luyện có đáp án

**Bài 1.** Cho định nghĩa của subtree(u) trong một cây vô hướng đã chọn gốc.

**Đáp án:** Gồm u và tất cả hậu duệ của u khi các cạnh được định hướng từ gốc ra ngoài. Một đỉnh khác gốc có thể thuộc subtree(u) dưới gốc này nhưng không thuộc dưới gốc khác.

**Bài 2.** Tại sao `size[u]=1+Σsize[child]`?

**Đáp án:** Cây con của u gồm chính u và các cây con của những con trực tiếp, chúng không giao nhau. Số đỉnh bằng 1 cộng kích thước từng con.

**Bài 3.** Với cây chín đỉnh ở phần 1, size[0], size[1], size[2], size[5] là bao nhiêu?

**Đáp án:** 9,3,5,3.

**Bài 4.** Với cùng cây, heavy[0] và heavy[2] là đỉnh nào?

**Đáp án:** heavy[0]=2 (size=5 lớn hơn size[1]=3); heavy[2]=5 (size=3 lớn hơn size[6]=1).

**Bài 5.** Nếu hai con có size bằng nhau, chọn con nào làm heavy?

**Đáp án:** Có thể chọn một trong hai; mã mẫu chọn id nhỏ hơn để kết quả xác định. **Chỉ một** con được heavy tại mỗi đỉnh, con còn lại vẫn là light.

**Bài 6.** Với màu [2,1,2,1,3,2,3,3,2], distinct của toàn bộ cây là bao nhiêu?

**Đáp án:** **3** màu phân biệt {1,2,3}.

**Bài 7.** Tần suất lớn nhất của một màu trên toàn cây chín đỉnh là bao nhiêu, và modeSum bằng bao nhiêu?

**Đáp án:** Màu 2 xuất hiện 4 lần, nên maxFrequency=4, modeSum=2.

**Bài 8.** Vì sao không thể tính distinct[u] bằng 1+Σdistinct[child]?

**Đáp án:** Cùng một màu có thể xuất hiện ở nhiều cây con, nên tổng các distinct đếm trùng màu. Phải hợp nhất **tập/tần suất màu**.

**Bài 9.** Nếu hiện có màu 2 hai lần và màu 3 một lần, thêm màu 3 rồi thêm màu 2 thì modeSum thay đổi ra sao?

**Đáp án:** Ban đầu 2; thêm màu 3 tạo hòa hai màu, modeSum=2+3=5; thêm màu 2 tạo max=3 riêng màu 2, modeSum=2.

**Bài 10.** Khi solve một light child với keep=false, có được bỏ qua việc ghi đáp án của các đỉnh trong nhánh không?

**Đáp án:** Không. Vẫn ghi mọi đáp án trước khi clear; keep=false chỉ quyết định **cấu trúc dữ liệu tạm có được giữ lại hay không**.

**Bài 11.** Tại sao phải xử lý light children trước heavy child?

**Đáp án:** Vì các light children sẽ clear dữ liệu. Nếu đã giữ heavy trước, một light child chạy và clear cấu trúc chung có thể xóa dữ liệu heavy; xử lý light trước bảo đảm cấu trúc rỗng khi gọi heavy.

**Bài 12.** Với preorder=[0,1,3,4,2,5,7,8,6], tin[2]=4 và size[2]=5, các đỉnh subtree(2) theo preorder?

**Đáp án:** Đoạn [4,9) là **[2,5,7,8,6]**.

**Bài 13.** Tại sao không được dùng BFS order để lấy đoạn subtree tương ứng [tin,tin+size)?

**Đáp án:** BFS theo tầng có thể xen các đỉnh thuộc nhánh khác vào giữa hậu duệ của một đỉnh, nên subtree không nhất thiết là đoạn liên tiếp trong BFS order.

**Bài 14.** Chứng minh mỗi cạnh nhẹ v của u có `size[v] < size[u]/2`.

**Đáp án:** Gọi h là con heavy. Vì size[h]≥size[v] và size[u]≥1+size[h]+size[v], suy ra size[u]≥1+2size[v], nên size[v]<(size[u])/2.

**Bài 15.** Vì sao một đường gốc→đỉnh có tối đa O(log n) light edges?

**Đáp án:** Mỗi lần đi qua light edge, size cây con giảm hơn một nửa; sau k lần còn dưới n/2ᵏ nhưng phải ít nhất 1, nên k=O(log n).

**Bài 16.** Tại sao tổng số lần thêm lại màu của một đỉnh bất kỳ chỉ O(log n)?

**Đáp án:** Đỉnh ấy chỉ bị thêm lại khi thuộc light subtree của một tổ tiên; số light edges trên đường gốc→đỉnh chỉ O(log n).

**Bài 17.** Nếu mọi lần thêm màu O(1) và clear nguyên subtree theo Euler, độ phức tạp DSU-on-tree bao nhiêu?

**Đáp án:** O(n log n) thao tác add/clear và O(n) bộ nhớ sau tiền xử lý. Nén màu/sắp adjacency cũng không vượt O(n log n) thời gian.

**Bài 18.** Nếu mỗi lần add cần một cập nhật segment tree O(log n), thời gian thường tăng đến mức nào?

**Đáp án:** O(n log² n) trong cận trên điển hình vì mỗi đỉnh được thêm O(log n) lần và mỗi add tốn O(log n).

**Bài 19.** Nếu mọi đỉnh cùng màu 7 và subtree(u) có 10 đỉnh, ba đáp án là gì?

**Đáp án:** distinct=1, maxFrequency=10, modeSum=7; không phải 70.

**Bài 20.** Nếu các màu trong subtree là −1,5,−1,5, modeSum bằng bao nhiêu?

**Đáp án:** Cả −1 và 5 đều đạt maxFrequency=2, nên modeSum=−1+5=**4**.

**Bài 21.** Nếu một cây con chỉ có một đỉnh màu 0, modeSum=0 có nghĩa dữ liệu rỗng không?

**Đáp án:** Không. distinct=1, maxFrequency=1 và modeSum=0 vì giá trị màu là 0.

**Bài 22.** Đổi gốc từ 0 sang 2 trên cây chín đỉnh, subtree(0) có còn chứa toàn bộ cây không?

**Đáp án:** Không. Dưới gốc 2, subtree(0) gồm {0,1,3,4}, có 4 đỉnh. Phải tính lại size, heavy và đáp án theo gốc mới.

**Bài 23.** DSU-on-tree có giống Union-Find DSU không?

**Đáp án:** Không. Sack dùng việc giữ bộ đếm của nhánh lớn và thêm lại nhánh nhỏ trên cây đã có gốc; Union-Find dùng find/union để quản lý các thành phần của một phân hoạch.

**Bài 24.** Đề yêu cầu truy vấn tổng các giá trị nút trong subtree và cập nhật một giá trị nút nhiều lần. Có nhất thiết dùng sack không?

**Đáp án:** Không. Nếu chỉ là tổng, dùng DFS preorder để flatten subtree thành đoạn, rồi Fenwick tree hoặc segment tree để cập nhật điểm và lấy tổng đoạn, thường phù hợp hơn.

**Bài 25.** Với cây sao n=5 gốc ở tâm, các lá đều có size=1. Nên chọn heavy nào?

**Đáp án:** Bất kỳ một lá; mã chọn lá có id nhỏ nhất. Các lá còn lại light, tổng chi phí thêm/xóa vẫn tuyến tính trong ví dụ này.

**Bài 26.** Vì sao clear bằng cách gán freq của các màu trong subtree về 0 là an toàn trong mã mẫu?

**Đáp án:** Vì ngay trước clear, bất biến bảo đảm sack chứa **chính xác** subtree ấy và không chứa đỉnh ngoài. Sau khi gán tất cả các màu có trong subtree về 0 và reset thống kê, sack rỗng; không có truy vấn giữa chừng.

**Bài 27.** Nếu muốn đếm số màu xuất hiện đúng k lần trên mỗi subtree, cần bổ sung gì?

**Đáp án:** Dùng cấu trúc countOfFrequency hoặc tương đương, cập nhật khi freq màu thay đổi; khi clear phải reset các trạng thái phụ. Không thể chỉ đọc maxFrequency để suy ra số màu có tần suất k.

**Bài 28.** Nếu n=0, chương trình yêu cầu root bằng bao nhiêu?

**Đáp án:** Theo quy ước của API minh họa, root=−1, edges và colors rỗng, trả toàn bộ mảng kết quả rỗng.

## 17. Ghi nhớ nhanh

| Nội dung | Công thức / Quy tắc |
| --- | --- |
| Kích thước cây con | `size[u] = 1 + Σsize[child]` |
| Heavy child | Con có size lớn nhất, hòa thì chọn một con |
| Light child | Mọi con khác heavy |
| Tiền xử lý preorder | Cha trước con, duyệt trọn một nhánh trước nhánh khác |
| Đoạn cây con u | `[tin[u], tin[u]+size[u])` |
| Light children | `SOLVE(v,false)` trước |
| Heavy child | `SOLVE(heavy[u],true)` sau |
| Gộp tại u | Thêm lại **chỉ các light subtrees**, rồi thêm u |
| Ghi đáp án | Khi sack chứa chính xác subtree(u) |
| keep=false | Clear toàn bộ sack sau khi ghi đáp án |
| Đếm distinct | Tăng khi freq màu chuyển 0→1 |
| Tăng max | Nếu freq mới lớn hơn max cũ, đặt modeSum=màu đó |
| Hòa max | Nếu freq mới bằng max cũ, cộng màu gốc vào modeSum |
| Giữ dữ liệu an toàn | Không clear dữ liệu heavy sau khi đã giữ |
| Số light edges trên đường gốc→đỉnh | O(log n) |
| Tổng số lần thêm/xóa đỉnh | O(n log n) |
| Thời gian với freq[] O(1) | **O(n log n)** |
| Bộ nhớ | **O(n)** |
| Hỗ trợ cập nhật màu online? | Không trực tiếp với bản sack tĩnh này |
| Có giải trực tiếp path(u,v) không? | Không; đây là thuật toán subtree |

## Kết luận

**Gộp thông tin cây con và kỹ thuật giữ dữ liệu nhánh lớn** tận dụng một tính chất hình học rất mạnh của cây: mỗi đỉnh có thể chọn một **heavy child**, và mỗi lần đi qua **light edge** trên một đường gốc→đỉnh, kích thước cây con giảm hơn một nửa.

Nhờ đó, khi ta **giữ lại dữ liệu của nhánh lớn**, giải các nhánh nhỏ với keep=false rồi **thêm lại** các nhánh nhỏ, mỗi đỉnh chỉ được thêm/xóa O(log n) lần. Với thao tác thêm màu O(1), giải được thống kê tần suất cho **mọi cây con** trong tổng thời gian **O(n log n)** và bộ nhớ **O(n)**.

Hai điểm dễ sai nhất là **thứ tự light trước heavy** và **điều kiện clear chỉ khi sack đang chứa đúng cây con cần xóa**. Đoạn DFS preorder [tin,tout) giúp thêm/xóa toàn bộ cây con không cần duyệt lại adjacency phức tạp. Khi hiểu rõ bất biến giữ/xóa, có thể mở rộng cấu trúc sack để giải nhiều bài toán tần suất, số màu phân biệt hoặc mode trên cây một cách hiệu quả và có chứng minh.
