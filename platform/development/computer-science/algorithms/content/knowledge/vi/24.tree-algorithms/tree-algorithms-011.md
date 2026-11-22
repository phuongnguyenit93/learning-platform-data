# Phân rã nặng–nhẹ (HLD) cho truy vấn trên đường đi

**Heavy-Light Decomposition (HLD — phân rã nặng–nhẹ)** là kỹ thuật biến những truy vấn trên **đường đi giữa hai đỉnh của cây** thành một số nhỏ các truy vấn trên **những đoạn liên tiếp của mảng**. Khi kết hợp với Segment Tree, HLD hỗ trợ hiệu quả các thao tác như:

- Tính **tổng** hoặc **giá trị lớn nhất/nhỏ nhất** của các đỉnh trên đường đi u–v.
- Cập nhật giá trị của một đỉnh rồi hỏi lại đường đi.
- Tìm **LCA** (tổ tiên chung gần nhất) bằng cách nhảy qua đầu các chuỗi nặng.
- Truy vấn một **cây con** bằng một đoạn liên tiếp, nếu thứ tự đánh số HLD được xây theo kiểu duyệt ưu tiên con nặng.
- Mở rộng sang trọng số **trên cạnh**, hoặc cập nhật cả đường đi bằng lazy segment tree khi phép cập nhật phù hợp.

Trọng tâm bài học thuộc nhóm **Thuật toán trên cây**: HLD **không tự tính tổng hay maximum**; HLD chỉ tổ chức các đỉnh thành những đoạn để một cấu trúc dữ liệu đoạn như Segment Tree xử lý truy vấn.

Với n đỉnh, cách triển khai thường gặp có:

- Tiền xử lý cây và HLD: **O(n)**.
- Xây Segment Tree: **O(n)**.
- Cập nhật một đỉnh: **O(log n)**.
- Truy vấn đường đi giữa hai đỉnh bằng Segment Tree: **O(log² n)**.
- Truy vấn cây con: **O(log n)** khi đánh số đảm bảo tính liên tiếp.
- Bộ nhớ tổng: **O(n)**, ngoài danh sách cạnh của cây cũng chỉ có n−1 cạnh.

Bài trình bày đầy đủ định nghĩa, bất biến, chứng minh cận số đoạn, các bước triển khai, ví dụ minh họa, code **Java 17+ độc lập** và kiểm thử ngẫu nhiên so với phép duyệt đường đi trực tiếp.

## 1. Bài toán mà HLD giải quyết

Cho cây vô hướng T có n đỉnh, mỗi đỉnh u mang một giá trị a[u]. Cây có đúng n−1 cạnh, liên thông và không có chu trình.

Ví dụ:

~~~text
               1(5)
             /      \
          2(-2)     3(4)
          /   \        \
       4(7)   5(1)     6(-3)
                         /   \
                      7(6)   8(2)
~~~

Nhãn đỉnh ở ngoài ngoặc; giá trị đỉnh ở trong ngoặc.

Ta cần xử lý một chuỗi thao tác:

- \`SET 6 10\`: thay a[6] từ −3 thành 10.
- \`SUM 4 7\`: tổng giá trị đỉnh trên đường 4→2→1→3→6→7.
- \`MAX 5 8\`: maximum trên đường 5→2→1→3→6→8.
- \`SUBTREE_SUM 3\`: tổng các đỉnh nằm trong cây con của 3 khi gốc là 1.

Nếu chỉ có một truy vấn và n nhỏ, đi từ hai đỉnh qua parent/LCA hoặc BFS có thể đủ. Nhưng với **q rất lớn**, mỗi lần duyệt toàn bộ đường đi có thể tốn **O(n)**.

Một cây hình dây n đỉnh có đường giữa hai đầu dài n−1 cạnh. Nếu mỗi truy vấn duyệt từng đỉnh thì q truy vấn mất **O(qn)** trong trường hợp xấu.

HLD đưa mỗi đường đi qua **O(log n) đoạn liên tiếp**, rồi Segment Tree xử lý mỗi đoạn trong O(log n). Vì vậy thời gian còn khoảng **O(q log² n)** cho q truy vấn đường đi, sau O(n) tiền xử lý.

### Điểm cần nhớ

HLD được thiết kế cho **cây**. Nếu đầu vào là đồ thị tổng quát có chu trình, khái niệm “đường đi duy nhất giữa hai đỉnh” không còn đúng. Muốn dùng HLD cho một graph, trước hết phải có một **cây cụ thể** hoặc cấu trúc khác được xác định rõ (ví dụ một cây khung hoặc cây phân rã), rồi đặt truy vấn lên cây đó.

## 2. Những mảng nền tảng của cây có gốc

Chọn một gốc, thường là đỉnh 1. Với mỗi đỉnh u, chuẩn bị:

| Mảng | Ý nghĩa |
| --- | --- |
| \`parent[u]\` | Cha của u trong cây gốc; gốc không có cha |
| \`depth[u]\` | Số cạnh từ gốc đến u |
| \`size[u]\` | Số đỉnh thuộc cây con của u, kể cả u |
| \`heavy[u]\` | Một con có cây con **lớn nhất** của u; −1 nếu là lá |
| \`head[u]\` | Đỉnh đầu chuỗi nặng chứa u |
| \`pos[u]\` | Chỉ số trong mảng tuyến tính sau phân rã |
| \`vertexAtPos[p]\` | Đỉnh nằm tại vị trí tuyến tính p |

Đỉnh v là **con của u** nếu \`parent[v]=u\`. Kích thước cây con:

**size[u] = 1 + tổng size[v] trên mọi con v của u.**

Sau khi biết size của từng con, chọn:

**heavy[u] = con v có size[v] lớn nhất.**

Nếu nhiều con có size bằng nhau, chọn một con tùy ý (ví dụ nhãn nhỏ nhất để chương trình chạy xác định). Việc chọn khi hòa **không làm thay đổi tính đúng** của HLD.

Một cạnh nối u tới heavy[u] gọi là **cạnh nặng (heavy edge)**. Mọi cạnh từ u đến con khác gọi là **cạnh nhẹ (light edge)**.

**Chỉ có tối đa một cạnh nặng đi xuống từ mỗi đỉnh**. Điều này bảo đảm các cạnh nặng kết thành các chuỗi đỉnh không phân nhánh.

## 3. Ví dụ xác định cạnh nặng và nhẹ

Với cây 8 đỉnh ở mục đầu:

~~~text
          1
         / \
        2   3
       / \   \
      4   5   6
             / \
            7   8
~~~

Kích thước cây con:

| Đỉnh | size |
| ---: | ---: |
| 4, 5, 7, 8 | 1 |
| 2 | 3 |
| 6 | 3 |
| 3 | 4 |
| 1 | 8 |

Cách chọn heavy, ưu tiên nhãn nhỏ khi bằng nhau:

- heavy[1]=3 vì size[3]=4 lớn hơn size[2]=3.
- heavy[3]=6 vì 6 là con duy nhất.
- heavy[6]=7 vì size[7]=size[8]=1 và 7 nhỏ hơn.
- heavy[2]=4 vì size[4]=size[5]=1 và 4 nhỏ hơn.
- Lá 4,5,7,8 có heavy=−1.

Chuỗi nặng hình thành:

~~~text
Chuoi A: 1 -> 3 -> 6 -> 7
Chuoi B: 2 -> 4
Chuoi C: 5
Chuoi D: 8
~~~

Cạnh 1–2, 2–5 và 6–8 là **cạnh nhẹ**.

Mỗi đỉnh thuộc **đúng một chuỗi nặng**. Một chuỗi có thể dài một đỉnh.

**Không được nhầm “heavy” với giá trị/trọng số lớn.** Con nặng được chọn theo **kích thước cây con**, không dựa trên a[u], trọng số cạnh hay độ sâu. Đó là điều tạo ra chứng minh O(log n) lần nhảy chuỗi.

## 4. Vì sao chỉ phải qua O(log n) cạnh nhẹ?

Giả sử v là **con nhẹ** của u. Vì heavy[u] là một con có size lớn nhất, ta có:

**size[heavy[u]] ≥ size[v]**.

Hai cây con heavy[u] và v không giao nhau, và còn có đỉnh u. Do đó:

**size[u] ≥ 1 + size[heavy[u]] + size[v] ≥ 1 + 2·size[v]**.

Suy ra:

**size[v] < size[u]/2**.

Mỗi lần đi từ u xuống một **cạnh nhẹ**, kích thước cây con chứa vị trí hiện tại giảm hơn một nửa.

Một chuỗi các lần đi qua cạnh nhẹ trên đường từ gốc xuống lá không thể dài hơn **O(log₂ n)** lần, vì size ban đầu không quá n và sau mỗi lần giảm quá nửa.

Cạnh nặng có thể xuất hiện nhiều trên một đường dài, nhưng **chúng nằm trong cùng chuỗi**, nên có thể gộp thành **một truy vấn đoạn liên tiếp** thay vì xét từng cạnh.

**Hệ quả:** đường đi u–v có thể tách thành **O(log n)** đoạn thuộc các chuỗi nặng, thường xét riêng hai nửa từ u và v lên LCA.

Cần nói đúng: đây là giới hạn trên **số chuỗi/đoạn**, không phải số đỉnh của đường đi. Đường có thể chứa n đỉnh nhưng số đoạn vẫn nhỏ.

## 5. Đánh số HLD thành một mảng liên tiếp

Sau khi chọn các cạnh nặng, ta đánh số đỉnh vào mảng \`base[]\` sao cho **mọi đỉnh của một chuỗi nặng có các pos liên tiếp**.

Một cách phổ biến là **duyệt ưu tiên con nặng trước các con nhẹ** (heavy-first DFS order). Khi đó còn có tính chất mạnh hơn:

**Tất cả đỉnh trong cây con của u chiếm một đoạn liên tiếp bắt đầu tại pos[u] và dài size[u].**

Tức là:

**subtree(u) ↔ [pos[u], pos[u]+size[u]−1]**.

Trong code, ta triển khai vòng lặp và stack tác vụ thay cho đệ quy để tránh tràn call stack trên cây hình dây. Thứ tự vẫn bảo đảm mỗi chuỗi nặng được đặt liên tiếp và mỗi cây con được đặt thành một khối.

Với ví dụ cây 8 đỉnh, một thứ tự hợp lệ là:

~~~text
pos (0-based):     0   1   2   3   4   5   6   7
vertexAtPos:       1   3   6   7   8   2   4   5
base[] value:      5   4  -3   6   2  -2   7   1

Chuoi A: [0..3] = [1,3,6,7]
Chuoi D: [4..4] = [8]
Chuoi B: [5..6] = [2,4]
Chuoi C: [7..7] = [5]

subtree(3): [1..4] = [3,6,7,8]
subtree(2): [5..7] = [2,4,5]
~~~

Lưu ý \`pos\` **không phải độ sâu**, và các đỉnh liền nhau theo pos không nhất thiết có cạnh trực tiếp (ví dụ vị trí 4 là đỉnh 8, vị trí 5 là đỉnh 2, thuộc các nhánh khác nhau).

**Chỉ các khoảng được chứng minh hợp lệ** — chuỗi nặng hoặc toàn bộ cây con — mới được dùng làm khoảng truy vấn. Không thể tùy tiện lấy [pos[u],pos[v]] để đại diện đường đi u–v nếu chúng không nằm cùng chuỗi.

## 6. Segment Tree xử lý các khoảng trên base[]

HLD quyết định **những khoảng nào** trong \`base[]\` phải lấy. Segment Tree quyết định **tính toán trên khoảng ấy thế nào**.

Ví dụ mỗi đỉnh có trọng số a[u] và cần hai hàm:

- \`sum(l,r)\`: tổng các giá trị trên đoạn [l,r].
- \`max(l,r)\`: giá trị lớn nhất trên đoạn [l,r].

Ta có thể lưu ở mỗi node của Segment Tree một cặp:

**Aggregate = (sum, max)**.

Phép gộp hai đoạn rời nhau:

**combine((s₁,m₁),(s₂,m₂))=(s₁+s₂,max(m₁,m₂))**.

Phần tử trung hòa (neutral element):

**(0, −∞)**.

Với kiểu \`long\` trong Java, \`Long.MIN_VALUE\` có thể đóng vai trò trung hòa cho maximum, miễn tổng và thao tác số học được xử lý theo giới hạn dữ liệu. **Không dùng max trung hòa 0** nếu mọi giá trị có thể âm, vì max trên một đường toàn âm sẽ bị sai thành 0.

Segment Tree cung cấp:

- Xây từ \`base[]\`: O(n).
- Cập nhật giá trị tại một \`pos[u]\`: O(log n).
- Truy vấn đoạn [l,r]: O(log n).
- Truy vấn cả \`base[]\`: O(1) bằng node gốc nếu cần.

Mã Java bên dưới dùng Segment Tree lặp (iterative) với hai mảng \`sum[]\`, \`max[]\`, trả cặp giá trị.

### Điều kiện phép gộp

Để làm truy vấn bằng cách chia đoạn rồi gộp lại, cần phép gộp **kết hợp** (associative). Tổng, min, max, gcd đều có tính kết hợp.

Tổng và max còn có tính **giao hoán** (commutative): đảo thứ tự các đoạn không đổi đáp án. Điều này giúp code truy vấn đường đi đơn giản.

Với phép **không giao hoán** như nối chuỗi, nhân ma trận hoặc tổ hợp trạng thái có hướng, cần bảo toàn **thứ tự đi trên đường**; xem mục riêng về noncommutative queries.

## 7. Truy vấn đường đi u–v bằng cách nhảy đầu chuỗi

Đặt u và v là hai đỉnh cần hỏi. HLD sử dụng \`head[u]\`, \`head[v]\`.

**Khi head[u] != head[v]:**

1. So độ sâu \`depth[head[u]]\` và \`depth[head[v]]\`.
2. Chọn phía có **đầu chuỗi sâu hơn**; giả sử đó là u.
3. Đoạn từ \`head[u]\` tới u nằm hoàn toàn trên một chuỗi nặng, nên truy vấn Segment Tree ở **[pos[head[u]], pos[u]]**.
4. Gộp đoạn ấy vào đáp án.
5. Dời u lên **parent[head[u]]** — nhảy qua một cạnh nhẹ.
6. Tiếp tục đến khi hai đỉnh nằm cùng chuỗi.

**Khi head[u] == head[v]:**

Nếu \`depth[u] > depth[v]\`, đổi chỗ u,v. Khi ấy u là tổ tiên của v **trong cùng chuỗi**. Đoạn cuối là:

**[pos[u], pos[v]]**.

Gộp đoạn cuối và trả đáp án.

Pseudocode cho tổng/max trên **đỉnh**, bao gồm cả hai đầu u,v:

~~~text
answer = neutralAggregate

while head[u] != head[v]:
    if depth[head[u]] < depth[head[v]]:
        swap(u,v)

    answer = combine(answer,
                     segmentQuery(pos[head[u]], pos[u]))
    u = parent[head[u]]

if depth[u] > depth[v]:
    swap(u,v)

answer = combine(answer, segmentQuery(pos[u],pos[v]))
return answer
~~~

### Vì sao chọn đầu chuỗi sâu hơn?

Nếu đầu chuỗi của u sâu hơn đầu chuỗi của v, toàn bộ đoạn từ u lên head[u] nằm dưới LCA của hai đỉnh và thuộc đúng một nhánh của đường đi. Do đó ta có thể **lấy toàn bộ đoạn này**, nhảy qua cạnh nhẹ để lên trên mà không bỏ sót hoặc đếm trùng đỉnh.

Khi hai đầu chuỗi trùng nhau, đoạn giữa hai đỉnh thuộc cùng chuỗi chính là phần đường đi còn lại. LCA được tính đúng **một lần** trong trường hợp truy vấn giá trị trên đỉnh.

### Độ phức tạp

Mỗi lần qua nhánh \`while\`, một phía nhảy qua đầu chuỗi bằng một cạnh nhẹ. Có O(log n) lần nhảy. Mỗi lần query Segment Tree O(log n). Tổng:

**O(log² n)**.

Vì chuỗi nặng có thể dài O(n) nhưng được xử lý bằng một query đoạn, độ dài đường đi **không xuất hiện trực tiếp** trong thời gian mỗi truy vấn.

## 8. Truy vết đường đi 4–7 trong ví dụ

Cây gốc 1 có HLD:

~~~text
Chuoi A: 1--3--6--7
Chuoi B: 2--4
Chuoi C: 5
Chuoi D: 8
~~~

Đường cần hỏi:

**4 → 2 → 1 → 3 → 6 → 7**

Các giá trị tương ứng:

**7, −2, 5, 4, −3, 6**.

Tổng là:

**7−2+5+4−3+6=17**.

Giá trị lớn nhất là **7**.

HLD thực hiện:

1. \`head[4]=2\` có depth 1, còn \`head[7]=1\` có depth 0.
2. Lấy đoạn chuỗi B từ 2 đến 4: **[pos[2],pos[4]]=[5,6]**, gồm [−2,7], tổng 5, max 7.
3. Dời u từ 4 lên parent[2]=1.
4. Bây giờ u=1, v=7 có cùng head=1. Lấy đoạn chuỗi A [pos[1],pos[7]]=[0,3], gồm [5,4,−3,6], tổng 12, max 6.
5. Gộp: tổng **5+12=17**, max **max(7,6)=7**.

Hai truy vấn Segment Tree đã thay thế việc duyệt riêng cả sáu đỉnh trên đường đi.

### Ví dụ đường 7–8

Đường là 7→6→8, có các giá trị 6,−3,2. Tổng bằng **5**, max bằng **6**.

Vì 8 là một chuỗi riêng, HLD lấy đoạn một đỉnh 8 trước, sau đó lấy đoạn liên tiếp từ 6 đến 7 trên chuỗi A.

### Khi hai đỉnh trùng nhau

Đường u→u chứa **một đỉnh u** đối với vertex-query:

- sum(u,u)=a[u].
- max(u,u)=a[u].

Không được coi đó là đoạn rỗng khi đang truy vấn **trọng số trên đỉnh**.

## 9. Cập nhật một đỉnh

Nếu thao tác là:

**SET(u,x)** — đặt giá trị của đỉnh u bằng x,

thì chỉ cần cập nhật một điểm của Segment Tree:

**segmentTree.set(pos[u],x)**.

Không cần tính lại size, heavy, head hay pos, vì HLD phụ thuộc **cấu trúc cây**, không phụ thuộc giá trị trên các đỉnh.

Trong ví dụ, sau \`SET(6,10)\`:

- Đường 4–7: 7−2+5+4+10+6 = **30**, max **10**.
- Đường 5–8: 1−2+5+4+10+2 = **20**, max **10**.
- Cây con 3 có các giá trị 4,10,6,2, tổng **22**, max **10**.

Chi phí mỗi SET là **O(log n)**.

### Phân biệt cập nhật điểm và cập nhật cả đường

\`SET(u,x)\` thay đúng một giá trị, nên chỉ cần point update.

\`ADD_PATH(u,v,delta)\` cộng delta vào **mọi đỉnh trên đường**: HLD vẫn tách đường thành O(log n) đoạn, nhưng Segment Tree phải hỗ trợ **range add** bằng lazy propagation. Khi đó mỗi đoạn cập nhật O(log n), tổng O(log² n).

Không được dùng point-update Segment Tree rồi gán từng đỉnh trên đường nếu muốn giữ O(log² n); cách đó quay lại O(length(path) log n) trong trường hợp xấu.

## 10. Truy vấn cây con và vai trò của thứ tự heavy-first

Với cây có gốc cố định, nếu pos được xây bằng **duyệt con nặng trước, rồi các cây con nhẹ**, toàn bộ cây con của u có vị trí:

**[pos[u], pos[u]+size[u]−1]**.

Vì thế:

~~~text
subtreeQuery(u)
    = segmentQuery(pos[u],
                   pos[u]+size[u]-1)
~~~

Chỉ **một** truy vấn Segment Tree, tốn **O(log n)**.

Với ví dụ:

~~~text
subtree(3) = {3,6,7,8}
base positions = [1..4]
values before update = [4,-3,6,2]
sum = 9, max = 6
~~~

Sau khi cập nhật a[6]=10, cây con 3 có tổng 22 và max 10.

### Điều kiện tiên quyết

Không phải bất kỳ cách gán \`pos[]\` nào cũng làm cây con liên tiếp. Nếu đánh số **từng chuỗi tùy ý** và đặt các chuỗi theo thứ tự tùy tiện, phép [pos[u],pos[u]+size[u]−1] có thể chứa đỉnh ngoài cây con.

Mã bên dưới xếp cả chuỗi nặng trước, sau đó xử lý các cây con nhẹ của chuỗi theo một stack **LIFO** có thứ tự phù hợp, để giữ tính liên tiếp cây con. Bộ kiểm thử độc lập so sánh trực tiếp subtreeQuery với việc duyệt con theo parent để bắt lỗi thứ tự phân rã.

Nếu cần đổi **gốc của cây theo từng truy vấn**, subtree của u theo gốc mới không còn đơn giản là một đoạn này; cần xử lý riêng bằng quan hệ LCA và phần bù cây con.

## 11. LCA bằng HLD

**Lowest Common Ancestor (LCA)** của u,v là tổ tiên chung sâu nhất khi cây có gốc cố định.

Có thể tìm LCA chỉ từ mảng HLD:

~~~text
while head[u] != head[v]:
    if depth[head[u]] > depth[head[v]]:
        u = parent[head[u]]
    else:
        v = parent[head[v]]

return u if depth[u] < depth[v] else v
~~~

Mỗi bước đi lên một cạnh nhẹ ở phía có đầu chuỗi sâu hơn. Do số cạnh nhẹ từ một đỉnh lên gốc là O(log n), LCA dùng HLD chạy **O(log n)**.

Ví dụ:

- LCA(4,5)=2.
- LCA(4,7)=1.
- LCA(7,8)=6.

### Khi nào dùng LCA riêng?

Nếu chỉ muốn LCA, **binary lifting** cũng là lựa chọn thông dụng với O(n log n) tiền xử lý và O(log n) mỗi query (có biến thể khác). Khi đang dùng HLD cho path queries, hàm LCA dựa trên head rất tiện vì không phải xây thêm bảng nhảy.

Nếu cần tính tổng trên đường u–v bằng root-prefix sum mà **không có cập nhật**, công thức:

**sumPath(u,v)=prefix[u]+prefix[v]−2·prefix[lca]+a[lca]**

cũng giải được với LCA. Nhưng khi cập nhật động các đỉnh, HLD + Segment Tree thường thuận tiện hơn cách prefix tĩnh ấy.

## 12. Code Java 17+ hoàn chỉnh: HLD + Segment Tree

Chương trình hỗ trợ:

- \`path(u,v)\`: trả **tổng và maximum** trên đường u–v, tính cả hai đầu.
- \`setValue(u,x)\`: đặt giá trị một đỉnh.
- \`subtree(u)\`: tổng và maximum trên cây con của u khi gốc là 1.
- \`lca(u,v)\`: tìm tổ tiên chung gần nhất.

Input là **cây vô hướng** gồm n≥1 đỉnh đánh số **1..n**, chính xác n−1 cạnh và một giá trị long trên mỗi đỉnh. Chương trình xác minh điều kiện cây bằng DSU: nếu có self-loop, cạnh song song tạo chu trình hoặc bất kỳ chu trình nào, nó từ chối input; với n−1 cạnh và không chu trình thì tính liên thông được bảo đảm.

Để tránh tràn **call stack** trên cây hình dây rất dài, các bước DFS xác định parent/order và phân rã được thực hiện **lặp bằng mảng stack**, không đệ quy.

Segment Tree dùng \`Math.addExact\` để **phát hiện** tràn long thay vì trả tổng sai. Điều kiện áp dụng là mọi tổng trung gian cần tính đều nằm trong phạm vi long; nếu đề cho trị số/tổng lớn hơn, cần thay thành \`BigInteger\` cho tổng. \`Long.MIN_VALUE\` làm phần tử trung hòa của maximum, đúng cả khi tất cả giá trị âm.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class HeavyLightPathQueriesDemo {

    record Aggregate(long sum, long max) {}

    static final Aggregate NEUTRAL =
            new Aggregate(0L, Long.MIN_VALUE);

    static Aggregate merge(Aggregate a, Aggregate b) {
        return new Aggregate(
                Math.addExact(a.sum(), b.sum()),
                Math.max(a.max(), b.max()));
    }

    static final class DSU {
        final int[] parent;
        final int[] size;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            while (parent[x] != x) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) return false;
            if (size[a] < size[b]) {
                int tmp = a;
                a = b;
                b = tmp;
            }
            parent[b] = a;
            size[a] += size[b];
            return true;
        }
    }

    static final class SegTree {
        final int base;
        final long[] sum;
        final long[] max;

        SegTree(long[] values) {
            int b = 1;
            while (b < values.length) {
                b <<= 1;
            }
            base = b;

            sum = new long[2 * base];
            max = new long[2 * base];
            Arrays.fill(max, Long.MIN_VALUE);

            for (int i = 0; i < values.length; i++) {
                sum[base + i] = values[i];
                max[base + i] = values[i];
            }

            for (int i = base - 1; i >= 1; i--) {
                pull(i);
            }
        }

        void pull(int i) {
            sum[i] = Math.addExact(
                    sum[i << 1], sum[i << 1 | 1]);
            max[i] = Math.max(
                    max[i << 1], max[i << 1 | 1]);
        }

        void set(int index, long value) {
            int i = base + index;
            sum[i] = value;
            max[i] = value;
            for (i >>= 1; i >= 1; i >>= 1) {
                pull(i);
            }
        }

        Aggregate query(int left, int right) {
            if (left > right) return NEUTRAL;

            int l = base + left;
            int r = base + right;
            Aggregate a = NEUTRAL;
            Aggregate b = NEUTRAL;

            while (l <= r) {
                if ((l & 1) == 1) {
                    a = merge(a,
                            new Aggregate(sum[l], max[l]));
                    l++;
                }
                if ((r & 1) == 0) {
                    b = merge(
                            new Aggregate(sum[r], max[r]), b);
                    r--;
                }
                l >>= 1;
                r >>= 1;
            }
            return merge(a, b);
        }
    }

    static final class HLD {
        final int n;
        final List<List<Integer>> adj;
        final int[] parent;
        final int[] depth;
        final int[] subtreeSize;
        final int[] heavy;
        final int[] head;
        final int[] pos;
        final int[] vertexAtPos;
        final SegTree seg;

        HLD(int n, int[][] edges, long[] values) {
            if (n < 1 || edges == null || values == null
                    || edges.length != n - 1
                    || values.length != n) {
                throw new IllegalArgumentException(
                        "Expected a tree and n vertex values");
            }
            this.n = n;
            adj = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                adj.add(new ArrayList<>());
            }

            DSU dsu = new DSU(n);
            for (int[] e : edges) {
                if (e == null || e.length != 2
                        || e[0] < 1 || e[0] > n
                        || e[1] < 1 || e[1] > n) {
                    throw new IllegalArgumentException(
                            "Invalid edge endpoints");
                }
                int u = e[0] - 1;
                int v = e[1] - 1;
                if (!dsu.union(u, v)) {
                    throw new IllegalArgumentException(
                            "Cycle or repeated edge in tree input");
                }
                adj.get(u).add(v);
                adj.get(v).add(u);
            }

            parent = new int[n];
            depth = new int[n];
            subtreeSize = new int[n];
            heavy = new int[n];
            head = new int[n];
            pos = new int[n];
            vertexAtPos = new int[n];

            Arrays.fill(parent, -2);
            Arrays.fill(heavy, -1);

            // Iterative DFS order from root vertex 1 (index 0).
            int[] order = new int[n];
            int[] stack = new int[n];
            int top = 0;
            int count = 0;

            parent[0] = -1;
            stack[top++] = 0;

            while (top > 0) {
                int u = stack[--top];
                order[count++] = u;

                for (int v : adj.get(u)) {
                    if (v == parent[u]) continue;
                    parent[v] = u;
                    depth[v] = depth[u] + 1;
                    stack[top++] = v;
                }
            }
            if (count != n) {
                throw new IllegalArgumentException(
                        "Tree is disconnected");
            }

            // Compute subtree sizes and heaviest children bottom-up.
            for (int i = n - 1; i >= 0; i--) {
                int u = order[i];
                subtreeSize[u] = 1;

                for (int v : adj.get(u)) {
                    if (v == parent[u]) continue;

                    subtreeSize[u] += subtreeSize[v];
                    if (heavy[u] == -1
                            || subtreeSize[v] >
                               subtreeSize[heavy[u]]
                            || (subtreeSize[v] ==
                                subtreeSize[heavy[u]]
                                && v < heavy[u])) {
                        heavy[u] = v;
                    }
                }
            }

            // Assign positions. Work items are new light chains.
            // Process one heavy chain continuously; nested light
            // subtrees are handled in LIFO order.
            int[] chainNode = new int[n];
            int[] chainHead = new int[n];
            int jobs = 0;
            chainNode[jobs] = 0;
            chainHead[jobs++] = 0;
            int timer = 0;

            while (jobs > 0) {
                jobs--;
                int start = chainNode[jobs];
                int h = chainHead[jobs];

                for (int u = start; u != -1; u = heavy[u]) {
                    head[u] = h;
                    pos[u] = timer;
                    vertexAtPos[timer++] = u;

                    for (int v : adj.get(u)) {
                        if (v != parent[u] && v != heavy[u]) {
                            chainNode[jobs] = v;
                            chainHead[jobs++] = v;
                        }
                    }
                }
            }

            long[] linear = new long[n];
            for (int u = 0; u < n; u++) {
                linear[pos[u]] = values[u];
            }
            seg = new SegTree(linear);
        }

        private int index(int vertex) {
            if (vertex < 1 || vertex > n) {
                throw new IllegalArgumentException(
                        "Vertex outside 1..n");
            }
            return vertex - 1;
        }

        // Query values ON VERTICES, including both endpoints.
        Aggregate path(int vertexU, int vertexV) {
            int u = index(vertexU);
            int v = index(vertexV);
            Aggregate answer = NEUTRAL;

            while (head[u] != head[v]) {
                if (depth[head[u]] < depth[head[v]]) {
                    int tmp = u;
                    u = v;
                    v = tmp;
                }

                answer = merge(answer,
                        seg.query(pos[head[u]], pos[u]));
                u = parent[head[u]];
            }

            if (depth[u] > depth[v]) {
                int tmp = u;
                u = v;
                v = tmp;
            }

            return merge(answer, seg.query(pos[u], pos[v]));
        }

        void setValue(int vertex, long value) {
            int u = index(vertex);
            seg.set(pos[u], value);
        }

        Aggregate subtree(int vertex) {
            int u = index(vertex);
            return seg.query(
                    pos[u], pos[u] + subtreeSize[u] - 1);
        }

        int lca(int vertexU, int vertexV) {
            int u = index(vertexU);
            int v = index(vertexV);

            while (head[u] != head[v]) {
                if (depth[head[u]] > depth[head[v]]) {
                    u = parent[head[u]];
                } else {
                    v = parent[head[v]];
                }
            }
            return (depth[u] < depth[v] ? u : v) + 1;
        }
    }

    static void show(String title, Aggregate value) {
        System.out.println(title + ": sum=" + value.sum()
                + ", max=" + value.max());
    }

    public static void main(String[] args) {
        HLD h = new HLD(8,
                new int[][] {
                    {1, 2}, {1, 3},
                    {2, 4}, {2, 5},
                    {3, 6}, {6, 7}, {6, 8}
                },
                new long[] {5, -2, 4, 7, 1, -3, 6, 2});

        show("Path 4-7", h.path(4, 7));
        show("Path 5-8", h.path(5, 8));
        show("Path 7-8", h.path(7, 8));
        show("Path 3-3", h.path(3, 3));
        show("Subtree 3", h.subtree(3));

        System.out.println("LCA 4-5: " + h.lca(4, 5));
        System.out.println("LCA 4-7: " + h.lca(4, 7));
        System.out.println("LCA 7-8: " + h.lca(7, 8));

        h.setValue(6, 10);
        show("After SET6 Path 4-7", h.path(4, 7));
        show("After SET6 Path 5-8", h.path(5, 8));
        show("After SET6 Subtree 3", h.subtree(3));

        HLD neg = new HLD(3,
                new int[][] {{1, 2}, {2, 3}},
                new long[] {-8, -6, -9});
        show("All negative", neg.path(1, 3));

        HLD single = new HLD(1, new int[][] {},
                new long[] {-9});
        show("Single before", single.path(1, 1));
        single.setValue(1, 3);
        show("Single after", single.subtree(1));
    }
}
~~~

Lưu với tên **HeavyLightPathQueriesDemo.java** trong thư mục làm việc. Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 HeavyLightPathQueriesDemo.java
java HeavyLightPathQueriesDemo
~~~

**Đầu ra chính xác của ví dụ:**

~~~text
Path 4-7: sum=17, max=7
Path 5-8: sum=7, max=5
Path 7-8: sum=5, max=6
Path 3-3: sum=4, max=4
Subtree 3: sum=9, max=6
LCA 4-5: 2
LCA 4-7: 1
LCA 7-8: 6
After SET6 Path 4-7: sum=30, max=10
After SET6 Path 5-8: sum=20, max=10
After SET6 Subtree 3: sum=22, max=10
All negative: sum=-23, max=-6
Single before: sum=-9, max=-9
Single after: sum=3, max=3
~~~

### Các lựa chọn triển khai cần hiểu

**Đồ thị đầu vào phải là cây.** Constructor kiểm tra số cạnh n−1 và dùng DSU để loại chu trình, self-loop hoặc cạnh trùng khiến phát sinh chu trình. Khi n−1 cạnh không tạo chu trình thì graph liên thông, nên có thể xác định parent cho n đỉnh từ gốc 1.

**Hai lượt xử lý cây.** Lượt đầu duyệt cây theo stack để tạo parent, depth và order. Duyệt ngược order để con được tính size trước cha và chọn heavy. Lượt thứ hai xếp các chuỗi vào base[] theo heavy-first để truy vấn đường đi lẫn cây con.

**head[u] là đỉnh đầu chuỗi.** Khi hai head khác nhau, ta xử lý nguyên đoạn từ head của phía sâu hơn xuống đỉnh hiện tại, rồi đi tới parent của head đó.

**Segment Tree hỗ trợ cả sum và max.** Không cần hai Segment Tree khác nhau; cùng một node có thể lưu cặp aggregate, miễn phép combine đúng.

**Không dùng đệ quy.** Cây có thể là một đường rất dài; stack mảng tường minh tránh rủi ro StackOverflowError của DFS đệ quy trong Java.

**Cập nhật không làm đổi phân rã.** Đổi trọng số một đỉnh chỉ update Segment Tree. Nếu bài thay đổi **cấu trúc cạnh của cây**, HLD tĩnh không cập nhật được trong O(log n) bằng cách này; cần xây lại hoặc dùng cấu trúc cây động như link-cut tree khi thực sự có yêu cầu.

## 13. Chứng minh tính đúng của các truy vấn đường đi

Để chứng minh kết quả HLD đúng, cần hai bổ đề.

### Bổ đề 1: đoạn trong cùng một chuỗi là một đoạn mảng đúng

Một chuỗi nặng được ghi liên tiếp theo chiều từ đầu chuỗi xuống các con nặng; mỗi bước chỉ đi dọc một cạnh cha–con. Vì vậy, nếu x và y nằm cùng chuỗi và x là tổ tiên của y, các đỉnh trên đường x→y chính xác là các vị trí:

**[pos[x], pos[y]]**.

Mảng Segment Tree gắn đúng giá trị mỗi đỉnh ở pos của nó, nên truy vấn đoạn cho tổng/max chính xác của đoạn đường x→y.

### Bổ đề 2: mỗi lần nhảy loại đi một đoạn đúng của đường u–v

Khi head[u] và head[v] khác nhau, chọn phía có head sâu hơn. Đoạn từ head[u] tới u nằm trên nhánh đi từ u lên LCA(u,v) và không chứa phần đường đã được xử lý ở phía còn lại.

Sau khi tính aggregate của đoạn này, phần đường còn lại bắt đầu tại **parent[head[u]]** ở phía u và vẫn kết thúc ở v. Bởi vậy thay u bằng parent[head[u]] không bỏ sót và không đếm lặp bất kỳ đỉnh nào.

Quá trình kết thúc khi hai head trùng nhau. Khi đó phần đường chưa lấy chính là đoạn nằm trên một chuỗi từ đỉnh nông hơn đến đỉnh sâu hơn.

### Định lý

Theo bổ đề 2, toàn bộ đường u–v được phân thành những đoạn **không trùng nhau** trên các chuỗi nặng. Theo bổ đề 1, từng truy vấn Segment Tree trả đúng aggregate của đoạn tương ứng. Phép combine của sum/max kết hợp và giao hoán, nên gộp các đoạn theo thứ tự mà thuật toán dùng vẫn ra tổng và maximum đúng của toàn đường.

Không đếm LCA hai lần vì nó chỉ thuộc **đoạn cuối** khi hai head trùng nhau; các đoạn đã lấy trước đó nằm hoàn toàn dưới LCA.

### Tính kết thúc và thời gian

Mỗi vòng while khiến ít nhất một phía đi lên qua một cạnh nhẹ. Mỗi đường lên gốc có O(log n) cạnh nhẹ, nên số vòng O(log n); đoạn cuối chỉ lấy một lần. Mỗi query Segment Tree O(log n), dẫn đến O(log² n) thời gian.

## 14. Truy vấn trên **cạnh** thay vì trên đỉnh

Nhiều đề gán trọng số w cho **cạnh**, không phải a[u] cho đỉnh. Có thể vẫn dùng HLD bằng cách lưu trọng số cạnh (parent[v],v) tại vị trí **pos[v]**, tức là vị trí của **đỉnh con sâu hơn**.

Đỉnh gốc không có cạnh đi lên; giá trị tại pos[root] được xem là trung hòa và **không được tính** vào đường đi trên cạnh.

Cách xử lý đường u–v khi head khác nhau:

- Lấy đoạn **[pos[head[u]],pos[u]]** của phía sâu hơn. Đoạn này gồm cả vị trí head[u], đại diện cho cạnh nối head[u] tới **parent[head[u]]**. Cạnh đó thuộc đường cần hỏi vì ta tiếp tục nhảy lên parent[head[u]].
- Dời u lên parent[head[u]].

Khi hai head đã trùng nhau, giả sử u là đỉnh nông hơn:

- **Bỏ vị trí của u** vì nó đại diện cạnh đi từ parent[u] tới u, nằm **ngoài** đường u–v.
- Lấy đoạn **[pos[u]+1,pos[v]]**.

Do đó:

**vertex-path:** đoạn cuối [pos[u],pos[v]].

**edge-path:** đoạn cuối **[pos[u]+1,pos[v]]**.

Nếu u=v, đường trên cạnh **không có cạnh nào**; tổng bằng 0 theo phép trung hòa, còn max cần quy ước riêng (không tồn tại cạnh để lấy maximum). Không tự in 0 cho maximum của một tập rỗng nếu có thể có giá trị cạnh âm.

### Cây con khi trọng số nằm trên cạnh

Đối với cây con của u, các cạnh hoàn toàn nằm trong cây con được đại diện bởi **các đỉnh con của u**, ngoại trừ chính u. Do đó khoảng tương ứng là:

**[pos[u]+1, pos[u]+size[u]−1]**,

với cùng heavy-first order. Đừng tính cạnh nối u tới parent[u], vì nó ở **ngoài** cây con.

### Sai lầm quan trọng

Một code HLD đúng cho truy vấn đỉnh có thể sai đúng một đơn vị ở LCA khi chuyển sang truy vấn cạnh. Cần xác định rõ mỗi vị trí pos đại diện **giá trị đỉnh** hay **cạnh từ cha tới đỉnh** trước khi viết query.

## 15. Những phép gộp **không giao hoán** cần xử lý chiều đường đi

Tổng, min, max và gcd đều không đổi khi đảo thứ tự các đoạn. Nhưng một số bài muốn:

- Ghép ký tự/chuỗi theo thứ tự từ u tới v.
- Nhân các ma trận theo thứ tự đường đi.
- Hợp thành các hàm hoặc phép biến đổi không giao hoán.

Khi đó **không được chỉ gộp mọi đoạn vào một biến answer theo thứ tự tìm thấy**. Đoạn phía u đang được duyệt **từ dưới lên**, trong khi Segment Tree thường trả aggregate theo chiều pos tăng **từ đầu chuỗi xuống dưới**. Đảo chiều có thể thay đổi kết quả.

Cách tổng quát:

1. Dùng hai bộ tích lũy: **leftPart** cho phía u, **rightPart** cho phía v.
2. Khi cắt một đoạn phía u, gộp nó theo chiều **từ u đi lên** vào cuối leftPart.
3. Khi cắt một đoạn phía v, gộp nó theo chiều **từ trên đi xuống** vào **đầu** rightPart.
4. Segment Tree cần trả được aggregate **forward** và **reverse** của đoạn (hoặc cấu trúc monoid thuận/ngược).
5. Sau khi xử lý đoạn cùng head, ghép phần còn lại theo đúng chiều rồi kết hợp leftPart với rightPart.

Mã Java trong mục 12 dùng **sum/max giao hoán**, nên không cần các biến thể forward/reverse. Nếu đổi phép gộp thành nối chuỗi hoặc nhân ma trận mà giữ nguyên thuật toán ghép, sẽ sai.

## 16. Cập nhật trên cả đường và cây con: HLD + lazy propagation

HLD chỉ là bước **chia đối tượng đường đi thành đoạn mảng**. Segment Tree quyết định loại update có thể làm nhanh.

Nếu bài có:

- \`ADD_PATH(u,v,delta)\`: cộng delta vào mọi đỉnh trên đường.
- \`SUM_PATH(u,v)\`: lấy tổng sau các update.
- \`MAX_PATH(u,v)\`: lấy maximum sau các update.

Ta có thể dùng **lazy segment tree hỗ trợ range add**:

Với một đoạn dài len nhận thêm delta:

**sum += delta·len**,

**max += delta**,

và cộng delta vào lazy tag. Cần chú ý overflow khi tính delta·len hoặc tổng.

HLD chia đường thành O(log n) đoạn, mỗi segment tree range add/query O(log n), nên:

- Path add: **O(log² n)**.
- Path sum/max: **O(log² n)**.
- Subtree add/query: **O(log n)** vì cây con là một đoạn.

Nếu thao tác là **gán toàn bộ đoạn bằng x**, lazy tag lại có quy tắc khác với cộng đoạn. Không nên dùng chung mã update cộng và update gán mà không phân biệt cách compose lazy tags.

### Khi chỉ cần tổng và cập nhật điểm

Không nhất thiết phải dùng Segment Tree. **Fenwick Tree (BIT)** hỗ trợ point update và range sum bằng hai prefix sums trong O(log n); kết hợp HLD cũng cho O(log² n) truy vấn đường đi và O(log n) cập nhật điểm.

Nhưng Fenwick Tree thông thường **không hỗ trợ range max tùy ý với point assignment** dễ dàng như Segment Tree. Nếu cần vừa sum vừa max, Segment Tree là lựa chọn trực tiếp hơn.

## 17. Cách kiểm thử HLD bằng lời giải chậm độc lập

HLD có nhiều mảng và chỉ số, nên dễ có lỗi mà vẫn đúng ở các ví dụ dạng đường thẳng. Hãy xây một **oracle đơn giản** dành cho cây nhỏ:

1. Với truy vấn \`path(u,v)\`, BFS từ u trong cây để tìm chuỗi cha của v; dựng lại các đỉnh trên đường duy nhất u–v.
2. Tính tổng và maximum trực tiếp từ các đỉnh trên đường ấy.
3. Với \`subtree(u)\`, dựng parent theo gốc 1 rồi duyệt các con của u để gom đúng tập đỉnh cây con.
4. Với \`lca(u,v)\`, liệt kê tổ tiên của u, sau đó đi từ v lên cho đến khi gặp tổ tiên chung đầu tiên.
5. Với \`setValue(u,x)\`, sửa mảng giá trị trực tiếp và kiểm tra các truy vấn sau cập nhật.

Không nên dùng cùng công thức \`head/pos\` trong oracle vì lỗi chung ở HLD có thể khiến hai phép kiểm tra đều sai như nhau.

### Bộ ca biên thiết yếu

| Ca | Điều cần kiểm tra |
| --- | --- |
| n=1 | path(u,u), subtree(u), LCA(u,u) đều hợp lệ |
| Cây hình dây | Có chuỗi nặng dài, dễ bắt lỗi stack sâu |
| Cây hình sao | Nhiều chuỗi một đỉnh và light edges |
| Cây cân bằng | Nhiều light chains, tie giữa các con |
| Đường u–v qua gốc | Không bỏ hoặc đếm đôi LCA |
| u=v | Vertex path có đúng một giá trị |
| Giá trị đều âm | Maximum không được mặc định bằng 0 |
| Giá trị bằng 0 | Neutral cho sum đúng |
| Nhiều point updates | Không dùng lại giá trị cũ trong Segment Tree |
| Query subtree của lá | Trả đúng một đỉnh |
| Query subtree của root | Trả toàn bộ n đỉnh |
| Trọng số cạnh thay vì đỉnh | Đoạn cuối phải bỏ LCA theo quy ước edge |
| Cây đầu vào có chu trình/self-loop | Phải từ chối nếu API đòi cây |
| Nhãn đỉnh ngoài 1..n | Phải từ chối rõ ràng |

Nếu code tự in một bảng \`head[],pos[],heavy[]\`, hãy nhớ có thể có nhiều HLD khác nhau khi size các con bằng nhau. Trong QA nên so **đáp án truy vấn**, không nên buộc cách đánh số duy nhất nếu tie-break không được đề quy định.

## 18. Những lỗi phổ biến

1. **Chọn heavy theo giá trị đỉnh/trọng số cạnh**, không theo size cây con; mất chứng minh số light edges O(log n).
2. **Chọn nhiều hơn một heavy child** cho một đỉnh, khiến chuỗi phân nhánh.
3. **Tính size theo thứ tự từ gốc xuống** trước khi biết size của con; phải tính bottom-up.
4. **Nhầm head[u] với parent[u]**; head là đầu chuỗi, không phải cha trực tiếp.
5. **Đánh số pos không làm chuỗi nặng liên tiếp**, rồi query một đoạn sai.
6. **Coi mọi cây con liên tiếp khi không có heavy-first DFS order**, dẫn đến subtree query chứa đỉnh ngoài.
7. **Dùng [pos[u],pos[v]] cho đường đi bất kỳ**, dù hai đỉnh thuộc chuỗi khác nhau.
8. **Khi head khác nhau, nhảy phía đầu chuỗi nông hơn**, làm phức tạp hoặc sai lập luận tách đường.
9. **Dời u về parent[u] thay vì parent[head[u]]** sau khi query cả chuỗi; dễ đếm lặp hoặc tăng số bước.
10. **Không gộp đoạn cuối khi hai head giống nhau**, bỏ sót phần chứa LCA.
11. **Đếm LCA hai lần**, nhất là khi viết hai nhánh riêng nhưng không phối hợp đoạn cuối.
12. **Khi truy vấn trên cạnh, vẫn tính vị trí LCA**, làm dư một cạnh ngoài đường.
13. **Khi truy vấn trên đỉnh, lại bỏ vị trí LCA**, làm thiếu một giá trị đỉnh.
14. **Khởi tạo maximum trung hòa bằng 0** khi dữ liệu có số âm.
15. **Không kiểm tra u=v**, bỏ qua đường dài một đỉnh hoặc xử lý đoạn rỗng sai.
16. **Thay đổi giá trị đỉnh mà rebuild HLD toàn bộ**, dù chỉ cần point update.
17. **Giả định point-update Segment Tree hỗ trợ range add**, rồi thực hiện từng đỉnh với thời gian quá lớn.
18. **Dùng phép gộp không giao hoán nhưng không xét chiều đoạn**, làm sai nối chuỗi/nhân ma trận.
19. **Đọc nhầm label 1-based với index 0-based**, gây lỗi array.
20. **Dùng DFS đệ quy cho cây dây rất dài**, dễ StackOverflowError trong Java.
21. **Đưa graph có chu trình hoặc không liên thông vào HLD tĩnh**, không còn là cây hợp lệ.
22. **Nhầm HLD path query với shortest path trong graph tổng quát**, dù đường cây là duy nhất.
23. **Không kiểm soát overflow long cho tổng**, tạo kết quả âm/dương sai.
24. **Dùng Long.MIN_VALUE làm sentinel “không có giá trị” cho một đỉnh**, dù Long.MIN_VALUE là trọng số đỉnh hợp lệ; cần tách neutral aggregate khỏi dữ liệu.
25. **Đổi cấu trúc cạnh mà không xây lại HLD**, khiến parent/head/pos lỗi thời.
26. **Chỉ thử đường u→ancestor**, không thử u,v nằm ở hai nhánh khác nhau.
27. **Chỉ so sum mà quên max trong QA**, bỏ qua lỗi neutral/merge.
28. **Chỉ thử path nhưng không thử subtree**, không phát hiện sai thứ tự heavy-first.
29. **Quên rằng root khác nhau có thể đổi LCA/subtree**, dù tập đỉnh trên path(u,v) không đổi.
30. **Bắt buộc một cấu hình heavy khi các size bằng nhau**, dù nhiều lựa chọn đều đúng.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** HLD dùng để chuyển bài toán gì thành bài toán đoạn mảng?  
**Đáp án:** Truy vấn và cập nhật trên đường đi hoặc cây con trong một cây có gốc, thông qua các đoạn liên tiếp của base[].

**Câu 2.** Heavy child được chọn theo tiêu chí gì?  
**Đáp án:** Một con có \`size[child]\` lớn nhất trong các con của đỉnh hiện tại.

**Câu 3.** Vì sao con nhẹ có size nhỏ hơn một nửa size cha?  
**Đáp án:** Heavy child có size ít nhất bằng con nhẹ; cộng hai cây con và đỉnh cha cho size[parent]≥1+2·size[light].

**Câu 4.** Một đường đi cắt qua bao nhiêu chuỗi nặng trong trường hợp xấu?  
**Đáp án:** O(log n) đoạn, do số cạnh nhẹ trên mỗi nhánh lên gốc là O(log n).

**Câu 5.** Truy vấn đường đi bằng HLD + Segment Tree mất thời gian bao nhiêu?  
**Đáp án:** O(log² n) với mỗi đoạn O(log n).

**Câu 6.** Cập nhật giá trị một đỉnh mất thời gian bao nhiêu?  
**Đáp án:** O(log n), chỉ cập nhật Segment Tree tại pos[u].

**Câu 7.** Cây con của u chiếm đoạn nào khi đánh số heavy-first?  
**Đáp án:** [pos[u], pos[u]+size[u]−1].

**Câu 8.** Khi hai đỉnh nằm cùng chuỗi, với truy vấn trên đỉnh lấy đoạn nào?  
**Đáp án:** [pos[đỉnh nông hơn],pos[đỉnh sâu hơn]], tính cả LCA.

**Câu 9.** Với truy vấn trên cạnh, đoạn cuối khác thế nào?  
**Đáp án:** Bỏ vị trí của đỉnh nông hơn/LCA, dùng [pos[LCA]+1,pos[đỉnh sâu hơn]].

**Câu 10.** Vì sao maximum trung hòa nên là −∞ thay vì 0?  
**Đáp án:** Một đường có tất cả giá trị âm vẫn phải trả maximum âm; 0 sẽ làm sai.

**Câu 11.** Tại sao HLD không cần rebuild khi đổi giá trị đỉnh?  
**Đáp án:** Heavy/head/pos được xác định bởi cấu trúc cây và size, không bởi giá trị dữ liệu.

**Câu 12.** Đường 4–7 trong ví dụ trước cập nhật có sum/max bao nhiêu?  
**Đáp án:** Tổng 17, max 7.

**Câu 13.** Sau SET(6,10), đường 4–7 có sum/max bao nhiêu?  
**Đáp án:** Tổng 30, max 10.

**Câu 14.** Khi chỉ cần LCA, có thể dùng HLD không?  
**Đáp án:** Có, nhảy qua head sâu hơn cho đến khi cùng chuỗi, trong O(log n).

**Câu 15.** Có thể dùng nguyên thuật toán gộp sum/max để nối chuỗi ký tự theo thứ tự u→v không?  
**Đáp án:** Không; nối chuỗi không giao hoán, phải giữ chiều các đoạn và gộp trái/phải đúng thứ tự.

**Câu 16.** Nếu graph thay đổi cạnh liên tục, HLD tĩnh có tự cập nhật không?  
**Đáp án:** Không. Cần xây lại hoặc dùng một cấu trúc hỗ trợ cây động.

## 20. Tổng kết và checklist triển khai

Một quy trình xây HLD đáng tin cậy:

1. **Xác minh input là cây** và quyết định gốc, ví dụ đỉnh 1.
2. Duyệt cây để tính parent, depth và thứ tự đỉnh.
3. Tính **size bottom-up**; chọn heavy child có size lớn nhất.
4. Phân rã thành các chuỗi nặng, tạo head, pos và vertexAtPos bằng **heavy-first order**.
5. Gán dữ liệu đỉnh vào \`base[pos[u]]=a[u]\`.
6. Xây Segment Tree theo phép gộp cần thiết.
7. Với path(u,v), cắt các đoạn từ **đầu chuỗi sâu hơn** cho đến khi hai head trùng nhau; lấy đoạn cuối chứa LCA **đúng một lần** đối với vertex query.
8. Với point update(u,x), chỉ sửa Segment Tree ở pos[u].
9. Với subtree(u), lấy đoạn [pos[u],pos[u]+size[u]−1] nếu thứ tự heavy-first bảo đảm liên tiếp.
10. Với trọng số **trên cạnh**, lưu tại pos của đỉnh con và **bỏ LCA ở đoạn cuối**.
11. Với phép gộp **không giao hoán**, quản lý thứ tự trái/phải và chiều đoạn riêng.
12. Kiểm thử trên cây dây, sao, cân bằng, giá trị âm, u=v, cập nhật nhiều lần, và so trực tiếp với đường tìm bằng BFS trên cây nhỏ.

**Cốt lõi để nhớ:** HLD làm cho mỗi đường đi trên cây trở thành **O(log n) đoạn trong mảng**. Segment Tree xử lý mỗi đoạn trong O(log n), tạo tổng thời gian **O(log² n)**, trong khi việc chọn heavy child theo **kích thước cây con** chính là lý do số lần đổi chuỗi chỉ tăng theo log n.
