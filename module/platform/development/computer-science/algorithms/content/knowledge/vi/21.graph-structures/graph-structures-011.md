# Dùng cấu trúc đồ thị để thu nhỏ bài toán

Trong nhiều bài toán đồ thị, khó khăn không chỉ nằm ở thuật toán tính đáp án, mà nằm ở việc **phải xử lý quá nhiều đỉnh, cạnh hoặc trạng thái không thực sự ảnh hưởng tới câu hỏi**. Trước khi chạy BFS, DFS, đường đi ngắn nhất, quy hoạch động, tìm kiếm tổ hợp hay tối ưu hóa, ta có thể khai thác **cấu trúc của đồ thị** để tách bài toán thành những phần độc lập, co cụm các đỉnh tương đương hoặc loại những vùng không thể tham gia lời giải.

Chủ đề **“Dùng cấu trúc đồ thị để thu nhỏ bài toán”** không chỉ là một thuật toán đơn lẻ. Đây là **cách thiết kế lời giải**: nhận ra tính chất đồ thị nào được phép giữ nguyên khi rút gọn, thực hiện phép rút gọn có chứng minh, rồi giải một bài toán nhỏ hơn và ánh xạ kết quả về dữ liệu gốc.

Ba kỹ thuật tiêu biểu được trình bày và cài đặt trong bài:

1. **Tách thành phần liên thông** của đồ thị vô hướng (*connected components*): giải độc lập từng phần khi bài toán và ràng buộc cho phép.
2. **Co thành phần liên thông mạnh** trong đồ thị có hướng (*strongly connected components – SCC*): chuyển đồ thị có thể có chu trình thành **đồ thị co DAG** (*condensation graph*) để xử lý quan hệ tiếp cận và các phụ thuộc ở mức nhóm.
3. **Bóc đỉnh bậc nhỏ hơn 2** (*2-core peeling*) trong đồ thị vô hướng đơn: giữ một vùng nhỏ chắc chắn bao gồm **mọi đỉnh nằm trên chu trình đơn**, hỗ trợ các bài toán chỉ cần tìm chu trình.

Ngoài ra, bài trình bày cách **lọc hành lang từ nguồn tới đích** bằng tìm kiếm thuận/ngược, những giới hạn khi co SCC, mối liên hệ với cầu và đỉnh khớp, các phản ví dụ chống rút gọn sai, một chương trình **Java 17+ đầy đủ**, kiểm thử và bài tập có đáp án.

**Nguyên tắc xuyên suốt:** Chỉ xóa/co/tách khi đã chứng minh phép biến đổi **bảo toàn thông tin mà đề bài hỏi**. Một phép rút gọn đúng cho *tính liên thông* có thể sai cho *số đường đi*, *chi phí đường đi ngắn nhất* hoặc *số cách thực hiện nhiệm vụ*.

## 1. Thế nào là “thu nhỏ” một bài toán đồ thị?

Cho đồ thị gốc `G=(V,E)` và một câu hỏi `Q(G)`. Ta xây một cấu trúc nhỏ hơn `H` hoặc nhiều cấu trúc `G1,G2,...`, rồi tính kết quả trên các cấu trúc ấy.

Một phép rút gọn hữu ích cần xác định rõ:

- **Phần nào được giữ?** Ví dụ các đỉnh nguồn–đích, mỗi nhóm SCC, mọi đỉnh có khả năng nằm trên chu trình.
- **Phần nào được bỏ hoặc gom?** Ví dụ thành phần khác không thể tới đích, các đỉnh được bóc khỏi 2-core, đỉnh trong cùng một SCC.
- **Ánh xạ giữa đồ thị gốc và đồ thị rút gọn là gì?** Ví dụ `componentOf[v]` cho biết đỉnh v thuộc cụm nào.
- **Điều gì được bảo toàn?** Tồn tại đường đi, tồn tại chu trình, tính độc lập của các thành phần, hoặc một giá trị tối ưu có công thức kết hợp xác định.
- **Khôi phục lời giải thế nào?** Một thứ tự nhóm SCC không tự động là thứ tự của mọi đỉnh nếu bên trong nhóm có chu trình. Một đường đi qua các SCC phải được hiện thực bằng các cung thật nếu đề yêu cầu đường đi chi tiết.

### Bảo toàn tính chất khác bảo toàn đáp án số

Giả sử hai đỉnh u và v ở cùng một SCC. Chúng đi tới được nhau, nên có thể co chúng thành một đỉnh nếu chỉ cần trả lời **nhóm nào tới được nhóm nào**. Nhưng nếu trong SCC đó có đường dài 5 và đường dài 100, co cả SCC thành **một đỉnh chi phí 0** sẽ làm sai bài toán đường đi ngắn nhất có trọng số.

Tương tự, trong đồ thị vô hướng, hai thành phần liên thông không có cạnh nối nhau nên có thể tính **số đỉnh mỗi thành phần** độc lập. Nhưng nếu đề cho một **ngân sách toàn cục k** để chọn tổng cộng k đỉnh từ mọi thành phần, không được tối ưu từng thành phần tùy ý rồi cộng đáp án mà không phối hợp ngân sách.

Vì vậy hãy luôn viết trước câu: **“Phép biến đổi này giữ nguyên ____.”** Nếu không điền được một tính chất cụ thể và chứng minh được, chưa nên rút gọn.

## 2. Chọn đúng mô hình đồ thị

Đồ thị có thể là **vô hướng** hoặc **có hướng**:

- **Vô hướng:** Cạnh {u,v} cho phép đi từ u sang v và từ v sang u. Các thành phần liên thông chia V thành những tập không có cạnh giữa các tập khác nhau.
- **Có hướng:** Cung u→v cho phép di chuyển một chiều. Hai đỉnh có thể có đường từ u tới v nhưng không có đường ngược lại.
- **Đồ thị có trọng số:** Mỗi cạnh/cung còn có chi phí, độ dài hoặc giá trị. Phép rút gọn phải xem xét **trọng số** nếu bài hỏi tối ưu theo trọng số.
- **Đồ thị đơn:** Không có khuyên tự nối, và không có nhiều bản sao của cùng một cạnh vô hướng. Điều này quan trọng khi đếm bậc cho 2-core.
- **Đồ thị đa cung:** Có thể có cung song song; SCC và tính tiếp cận vẫn hoạt động, nhưng nếu cần đếm đường đi hoặc tính bậc, các bản sao phải được xử lý nhất quán.

Trong chương trình minh họa:

- **Phần vô hướng** chuẩn hóa cạnh lặp thành một cạnh duy nhất, **từ chối khuyên** để sử dụng đúng định nghĩa 2-core của đồ thị vô hướng đơn.
- **Phần có hướng** cho phép cung lặp và khuyên, vì chúng không làm thay đổi quan hệ tới được; khi dựng DAG co SCC, các cung trùng giữa cùng hai cụm được gộp.
- Đỉnh được đánh số `0..n−1`; ví dụ sử dụng chỉ số tăng để kết quả tái lập được.

Đừng dùng một khái niệm “liên thông” không xác định trên đồ thị có hướng: **liên thông yếu** và **liên thông mạnh** là hai tính chất khác nhau. Co nhầm theo liên thông yếu có thể tạo ra kết luận “đi ngược chiều được” vốn không đúng.

## 3. Kỹ thuật thứ nhất: tách thành phần liên thông vô hướng

Trong đồ thị vô hướng, **thành phần liên thông** (*connected component*) là một tập đỉnh lớn nhất sao cho **mỗi cặp đỉnh trong tập đều có đường đi nối nhau**.

Ví dụ:

```text
0 --- 1 --- 2      3 --- 4      5

Thành phần 0: {0,1,2}
Thành phần 1: {3,4}
Thành phần 2: {5}
```

Không có cạnh nối hai thành phần khác nhau, nên chúng độc lập về khả năng đi lại trong đồ thị này.

### 3.1. Tìm thành phần bằng BFS/DFS

Ý tưởng:

1. Khởi tạo `componentOf[v]=-1` cho mọi đỉnh.
2. Duyệt v từ 0 tới n−1; nếu chưa có nhãn, bắt đầu một BFS từ v.
3. Mọi đỉnh mà BFS đi tới được từ v thuộc **cùng một thành phần**; gán nhãn `c`.
4. Ghi kích thước thành phần, rồi chuyển sang đỉnh chưa được gán tiếp theo.

Giả mã:

```text
components(G):
    id[v] = -1 cho mọi v
    count = 0

    for start = 0..n-1:
        if id[start] != -1:
            continue

        queue = [start]
        id[start] = count
        size = 0

        while queue không rỗng:
            u = queue.remove()
            size++
            for each neighbor v of u:
                if id[v] == -1:
                    id[v] = count
                    queue.add(v)

        sizes[count] = size
        count++

    return id, sizes
```

Đối với danh sách kề, việc xây và duyệt các đỉnh/cạnh tốn **O(V+E)** thời gian, **O(V+E)** bộ nhớ nếu tính cả đồ thị, và **O(V)** bộ nhớ phụ cho nhãn/hàng đợi.

### 3.2. Khi nào thực sự có thể giải từng thành phần riêng?

Có thể tách bài khi **không có tương tác qua các thành phần** và hàm mục tiêu/ràng buộc phân rã phù hợp.

| Câu hỏi | Tận dụng thành phần thế nào? |
| --- | --- |
| Có đường đi từ s tới t trong đồ thị vô hướng? | Nếu `id[s] != id[t]` thì chắc chắn **không có đường đi** |
| Kích thước thành phần lớn nhất? | Lấy `max(sizes)` |
| Có bao nhiêu cặp đỉnh **cùng** thành phần? | Cộng `size*(size−1)/2` trên từng thành phần |
| Bài chọn đáp án độc lập ở từng thành phần và tổng điểm cộng được | Giải từng thành phần rồi cộng, **nếu không có ràng buộc toàn cục** |
| Số cạnh tối thiểu để kết nối toàn bộ c thành phần, được phép thêm cạnh bất kỳ | `max(0,c−1)` |
| Đường đi giữa hai đỉnh thuộc hai thành phần khác nhau | Có thể trả “không tồn tại” mà không cần chạy thuật toán đường đi |

**Ví dụ về số cặp cùng thành phần:** Với kích thước [3,2,1], số cặp không thứ tự là:

```text
C(3,2) + C(2,2) + C(1,2)
= 3 + 1 + 0
= 4
```

Một BFS mỗi đỉnh riêng biệt để đếm các cặp sẽ làm thừa việc; dùng kích thước thành phần để gom tính toán.

### 3.3. Khi không thể chỉ cộng đáp án thành phần

Nếu đề yêu cầu chọn **đúng k đỉnh trên toàn đồ thị**, dù các thành phần không có cạnh với nhau, một lựa chọn ở thành phần A vẫn tiêu hao ngân sách chung của B. Muốn giải chính xác có thể cần **quy hoạch động ghép kết quả giữa các thành phần**.

Nếu đề cho phép thêm cạnh kết nối các thành phần với **chi phí phụ thuộc cặp thành phần**, kết quả tối ưu không còn đơn giản là c−1; c−1 chỉ là **số lượng cạnh tối thiểu**, còn chi phí có thể phải dùng MST trên một đồ thị thành phần được xây theo chi phí nối.

Nếu bài có một nguồn s và đích t, việc **xác định hai đỉnh thuộc cùng thành phần** chỉ cho biết có đường đi, chứ không trả đường đi ngắn nhất. Phải tính chi phí/đường đi bên trong thành phần liên quan nếu đề hỏi chi tiết.

## 4. Kỹ thuật thứ hai: thành phần liên thông mạnh (SCC) trong đồ thị có hướng

Với đồ thị có hướng, hai đỉnh u,v nằm trong cùng một **thành phần liên thông mạnh** khi:

```text
Có đường đi u -> ... -> v
VÀ
Có đường đi v -> ... -> u
```

Quan hệ “đi tới được theo cả hai chiều” là một quan hệ tương đương, chia V thành các lớp không giao nhau. Mỗi lớp là một SCC lớn nhất.

Ví dụ:

```text
0 -> 1 -> 2 -> 0

0,1,2 thuộc cùng một SCC:
mọi cặp đỉnh đều tới được nhau.
```

Nếu có thêm cung 2→3 nhưng **không có đường từ 3 quay lại 0,1,2**, đỉnh 3 thuộc SCC khác, dù 0 có thể tới 3.

### 4.1. Không nhầm SCC với thành phần liên thông yếu

Xét đồ thị:

```text
0 -> 1 -> 2
```

Nếu bỏ hướng, cả ba đỉnh liên thông; đó là **một thành phần liên thông yếu**. Nhưng trong đồ thị có hướng, không có đường từ 2 về 1 hay 0. Vì vậy có **ba SCC riêng**: {0}, {1}, {2}.

Co cả ba thành một đỉnh dựa trên liên thông yếu sẽ nói sai rằng từ 2 có thể đi tới 0. Đây là ví dụ rất nhỏ cho thấy **quan hệ dùng để gom nhóm phải tương ứng chính xác với thuộc tính mà ta muốn bảo toàn**.

### 4.2. Kosaraju: tìm SCC bằng hai lần DFS

Thuật toán Kosaraju thực hiện:

1. Trên đồ thị gốc G, DFS mọi đỉnh và ghi **thứ tự hoàn thành** (*finishing order*): đưa đỉnh vào danh sách khi duyệt xong toàn bộ cung đi ra.
2. Xây đồ thị **đảo cung** Gᵀ: mỗi cung u→v của G thành v→u.
3. Xét các đỉnh theo **thứ tự hoàn thành giảm dần**, DFS trên Gᵀ từ đỉnh chưa gán. Mỗi lần DFS tạo ra **một SCC**.

Giả mã:

```text
finished = []
visited = false

for v = 0..n-1:
    if not visited[v]:
        DFS_FINISH_G(v):
            visited[v] = true
            for each v -> w:
                if not visited[w]: DFS_FINISH_G(w)
            finished.append(v)

sccOf[v] = -1
sccCount = 0

for v in reverse(finished):
    if sccOf[v] == -1:
        DFS_ASSIGN_ON_REVERSED_GRAPH(v, sccCount)
        sccCount++
```

**Tại sao đảo đồ thị?** Thứ tự hoàn thành giúp chọn một thành phần mà việc DFS trên đồ thị đảo sẽ **không tràn sang SCC chưa được gán sai thứ tự**. Mọi đỉnh trong một SCC tới được nhau theo hai chiều, nên vẫn liên thông mạnh khi đảo các cung. Các cung giữa SCC có hướng ngược lại; thứ tự hoàn thành đảm bảo ta thu được từng nhóm tối đa.

Hai lượt DFS và xây đồ thị đảo tốn **O(V+E)** thời gian/bộ nhớ với danh sách kề. Một lựa chọn khác là **Tarjan**, tìm SCC bằng một lần DFS với discovery index và low-link, cũng O(V+E).

**Lưu ý kỹ thuật Java:** DFS đệ quy có thể gây `StackOverflowError` trên chuỗi cực dài; chương trình mẫu dùng đệ quy để công thức dễ đọc. Với đồ thị hàng trăm nghìn đỉnh hay hơn, nên dùng DFS lặp với stack tường minh.

## 5. Co SCC thành đồ thị DAG

Sau khi biết `sccOf[v]`, xây đồ thị mới:

- Mỗi SCC của G trở thành **một đỉnh** của H.
- Với mỗi cung u→v của G, nếu `sccOf[u] != sccOf[v]`, thêm cung `sccOf[u] → sccOf[v]` vào H.
- Các cung **nằm hoàn toàn trong một SCC** được bỏ vì chúng không ảnh hưởng quan hệ giữa các cụm.
- Có thể **gộp các cung song song** giữa cùng hai SCC nếu chỉ cần quan hệ tới được.

Đồ thị H gọi là **đồ thị co SCC** (*condensation graph*).

### 5.1. Vì sao condensation graph luôn là DAG?

Giả sử H có chu trình giữa các SCC phân biệt:

```text
C1 -> C2 -> ... -> Ck -> C1
```

Mỗi cung giữa hai SCC đại diện cho một cung thật ở G; bên trong từng SCC, mọi đỉnh tới được nhau. Vì thế từ bất kỳ đỉnh nào thuộc C1 đều có thể đi qua các cụm trong chu trình rồi quay lại C1; tương tự với mọi cụm. Như vậy các SCC C1..Ck **thực ra phải cùng liên thông mạnh**, mâu thuẫn với việc chúng là những SCC tối đa khác nhau.

Do đó đồ thị co SCC **không chứa chu trình có hướng**. Đây là **một phép biến đổi cấu trúc** rất mạnh: từ một đồ thị có thể có nhiều chu trình, ta có **một DAG nhỏ hơn** để sắp xếp tô-pô, chạy DP trên DAG hay kiểm tra sự phụ thuộc giữa các vùng.

### 5.2. Quan hệ tới được được bảo toàn đúng cách

Cho u,v là hai đỉnh gốc, và C(u),C(v) là SCC chứa chúng:

```text
u tới được v trong G
    nếu và chỉ nếu
C(u) tới được C(v) trong condensation DAG.
```

Chiều thuận: lấy một đường u→...→v trong G, thay mỗi đỉnh bằng nhãn SCC và bỏ các bước ở trong cùng SCC. Ta thu được đường trên H.

Chiều ngược: mỗi cung C_i→C_j trong H đến từ một cung thật x→y trong G. Trong mỗi SCC, ta có thể đi từ đỉnh hiện tại tới x hoặc từ y tới vị trí nối tiếp vì các đỉnh trong cùng SCC tới được nhau. Ghép các đoạn nội bộ với các cung giữa SCC tạo đường trong G.

Nếu C(u)=C(v), u và v tới được nhau ngay theo định nghĩa SCC.

**Điều được bảo toàn là tính tồn tại đường đi, không phải một đường chi tiết hay độ dài đường đi.** Để phục hồi đường đi thực, cần lưu các cung đại diện giữa SCC và tìm đường bên trong từng SCC.

### 5.3. Không thể “co SCC = đỉnh chi phí 0” cho mọi bài

Giả sử trong một SCC có nhiều đường nối từ điểm vào tới điểm ra, với các chi phí khác nhau. Khi nén thành một đỉnh, **chi phí đi xuyên cụm phụ thuộc vào cặp cổng vào/ra**, không phải chỉ một hằng số.

Ví dụ có các cung hai chiều giữa A và B, nhưng:

```text
A -> B chi phí 100
B -> A chi phí 1
```

A và B thuộc cùng SCC. Nếu co thành một đỉnh rồi gán chi phí di chuyển nội bộ bằng 0, bài toán **đường đi ngắn nhất có trọng số** có thể bị giảm chi phí ảo 100 đơn vị từ A tới B. Muốn giữ đúng chi phí, ta phải giữ thêm thông tin về đường đi tối ưu giữa các cổng, hoặc dùng thuật toán đường đi ngắn nhất trên đồ thị gốc.

Tương tự, **số đường đi**, số đường đi đơn, chu trình, chi phí thu thập phần thưởng, đường đi Hamilton và bài tối ưu có ràng buộc nội bộ SCC **không được tự động bảo toàn** chỉ bằng nhãn SCC.

## 6. Ví dụ đồ thị có hướng gồm nhiều SCC

Xét n=10, các cung:

```text
0 -> 1
1 -> 2
2 -> 0       => SCC A = {0,1,2}

2 -> 3
3 -> 4
4 -> 3       => SCC B = {3,4}

4 -> 5
5 -> 6
6 -> 5       => SCC C = {5,6}

6 -> 7
0 -> 7       => SCC D = {7}
7 -> 7       (self-loop nội bộ SCC D)

1 -> 8      => SCC E = {8}
9 -> 7      => SCC F = {9}

2 -> 3      (một cung trùng)
```

Chương trình đánh số SCC **theo chỉ số đỉnh nhỏ nhất trong nhóm** để kết quả ổn định:

| SCC id | Các đỉnh thuộc nhóm |
| ---: | --- |
| 0 | {0,1,2} |
| 1 | {3,4} |
| 2 | {5,6} |
| 3 | {7} |
| 4 | {8} |
| 5 | {9} |

Mảng nhãn:

```text
component = [0,0,0,1,1,2,2,3,4,5]
```

Các cung giữa các SCC **sau khi gộp bản sao**:

```text
0 -> 1    (2 -> 3)
0 -> 3    (0 -> 7)
0 -> 4    (1 -> 8)
1 -> 2    (4 -> 5)
2 -> 3    (6 -> 7)
5 -> 3    (9 -> 7)
```

Cung 7→7 không tạo cung tự nối trên DAG co; nó bị bỏ vì nằm nội bộ SCC 3. Cung 2→3 thứ hai không tạo thêm một cung 0→1 nếu chỉ quan tâm tới được.

Một thứ tự tô-pô của condensation DAG khi dùng min-heap là:

```text
[0,1,2,4,5,3]
```

**Chú ý:** Dãy này là thứ tự các **SCC**, không phải thứ tự tô-pô của toàn bộ 10 đỉnh gốc; đồ thị gốc chứa chu trình nên **không có thứ tự tô-pô đầy đủ**. Đó là lý do phải phân biệt mức đỉnh và mức cụm.

### 6.1. Ứng dụng: giảm bài toán lan truyền giữa vùng

Giả sử mỗi SCC đại diện cho một vùng mà mọi tác vụ/đỉnh **có thể tiếp cận lẫn nhau**, và câu hỏi chỉ yêu cầu “từ vùng này có thể tới vùng nào?” hoặc “bao nhiêu vùng khác nhau có thể bị ảnh hưởng?”. Khi ấy giải trên condensation DAG có thể dễ hơn vì:

- Số đỉnh giảm từ n xuống c SCC.
- Không còn chu trình có hướng giữa các nhóm.
- Có thể xử lý theo một thứ tự tô-pô.
- Có thể tính tính tới được hoặc các nhãn phụ thuộc trên DAG nếu định nghĩa câu hỏi phù hợp.

**Không nên mặc định mỗi SCC có trọng số bằng một đỉnh.** Nếu cần tính số đỉnh gốc có thể bị ảnh hưởng, phải giữ `sizeOfSCC[c]` để quy ngược từ số cụm sang số đỉnh.

## 7. Kỹ thuật thứ ba: chỉ giữ “hành lang” có thể đi từ s tới t

Đôi khi câu hỏi chỉ liên quan tới **một nguồn s và một đích t** trên đồ thị có hướng. Ta có thể loại trước các đỉnh chắc chắn **không thể nằm trên bất kỳ đường s→t nào** bằng hai lượt tìm kiếm.

Định nghĩa:

- `fromS[v]`: có một đường đi có hướng từ s tới v trong G.
- `toT[v]`: có một đường đi có hướng từ v tới t trong G.

Để tính `fromS`, chạy BFS/DFS từ s trên **đồ thị gốc**.

Để tính `toT`, **đảo tất cả các cung** rồi chạy BFS/DFS từ t trên **đồ thị đảo Gᵀ**. Trong Gᵀ, một đường t→...→v tương ứng chính xác với đường v→...→t trong G.

Giữ lại những đỉnh:

```text
corridor = {v | fromS[v] && toT[v]}
```

Nếu t không thuộc fromS, chắc chắn không có đường từ s tới t. Nếu s=t, theo quy ước đường đi độ dài 0, vẫn có đường từ s tới t; các đỉnh giữ thêm chỉ phản ánh những đường **đi vòng quay lại s**, không bắt buộc xuất hiện trong một đường đơn.

### 7.1. Vì sao phép cắt này an toàn?

Mọi đỉnh nằm trên một đường đi s→t thực sự đều được s tới và từ đó tới được t. Do đó, nếu một đỉnh không thuộc intersection, **nó không thể xuất hiện trên bất kỳ đường s→t nào**. Xóa nó không làm mất một đường hợp lệ nào.

Cách lọc này giữ đúng **tính tồn tại đường**, giữ tất cả các đường s→t vốn có và có thể dùng để giảm kích thước bài đường đi ngắn nhất sau khi đã xử lý các giả thiết về trọng số/chu trình.

**Tuy nhiên, chiều ngược lại cần thận trọng:** Một đỉnh vừa tới được từ s vừa tới được t **không nhất thiết** nằm trên một **đường đi đơn** s→t. Nó chắc chắn nằm trên một **walk** s→t nếu cho phép lặp đỉnh, vì có thể ghép một đường s→v và một đường v→t; đường ghép có thể lặp đỉnh.

### 7.2. Phản ví dụ “giữ không có nghĩa là chắc chắn nằm trên đường đơn”

Cung:

```text
0 -> 1
1 -> 0
0 -> 2

Nguồn s=0, đích t=2.
```

Đỉnh 1 thuộc corridor vì `0→1` và `1→0→2`. Nhưng mọi cách đi qua 1 trước khi tới 2 đều phải quay lại 0, nên **không có đường đơn 0→2 nào đi qua 1**. Đường đơn duy nhất là `0→2`.

Vì vậy corridor là một **tập bao an toàn** của các đỉnh có thể liên quan, không phải bộ xác định chính xác mọi đỉnh trên một đường đơn nguồn–đích.

### 7.3. Ví dụ kết hợp với SCC

Trên đồ thị 10 đỉnh phần 6, chọn s=0 và t=7.

- Đỉnh 8 tới được từ 0 qua 0→1→8 nhưng **không có đường từ 8 tới 7**, nên loại.
- Đỉnh 9 có đường 9→7 nhưng **không thể tới từ 0**, nên loại.
- Các đỉnh 0..7 vừa tới được từ 0 vừa đi được tới 7, nên giữ.

```text
corridor(0,7) = [0,1,2,3,4,5,6,7]
```

Nếu chọn t=8, chỉ SCC {0,1,2} và đỉnh 8 có thể xuất hiện trong corridor:

```text
corridor(0,8) = [0,1,2,8]
```

Hai BFS/DFS với danh sách kề và đồ thị đảo có thời gian **O(V+E)** và bộ nhớ **O(V+E)**, trước khi tính bất kỳ thuật toán tối ưu nặng nào.

## 8. Kỹ thuật thứ tư: bóc đỉnh bậc nhỏ hơn 2 để tìm 2-core

Trong đồ thị **vô hướng đơn**, bậc của đỉnh v là số hàng xóm của v. Một đỉnh thuộc một **chu trình đơn** phải có **ít nhất hai cạnh khác nhau** tới hai đỉnh trên chu trình: một cạnh để vào và một cạnh để đi ra theo chu trình.

Do đó:

- Đỉnh bậc 0 (cô lập) **không thuộc chu trình**.
- Đỉnh bậc 1 (lá) **không thuộc chu trình**.
- Sau khi bỏ những đỉnh ấy, các đỉnh khác có thể trở thành lá. Ta cần **bóc lặp đi lặp lại**.

Kết quả sau khi không thể bóc thêm là **2-core**: đồ thị con cảm sinh lớn nhất mà mọi đỉnh còn lại đều có bậc ít nhất 2 trong đồ thị con đó.

Giả mã:

```text
TWO_CORE(G):
    degree[v] = số hàng xóm của v
    removed[v] = false

    queue = mọi v có degree[v] < 2

    while queue không rỗng:
        v = queue.remove()
        if removed[v]:
            continue

        removed[v] = true

        for mỗi hàng xóm u của v:
            if not removed[u]:
                degree[u]--
                if degree[u] < 2:
                    queue.add(u)

    return mọi v có removed[v] == false
```

Không cần xây đồ thị mới ở mỗi lần xóa. Duy trì bậc hiện tại và hàng đợi giống cách Kahn dùng indegree, nhưng ở đây **cạnh vô hướng** và điều kiện bóc là degree<2.

### 8.1. Vì sao mọi đỉnh nằm trên chu trình đơn đều sống sót?

Xét một chu trình đơn C. Mỗi đỉnh v trong C có hai hàng xóm **khác nhau cũng nằm trên C**, nên trong mọi thời điểm chưa đỉnh nào của C bị loại, bậc còn lại của mỗi v thuộc C vẫn ít nhất 2.

Giả sử có đỉnh đầu tiên của C bị bóc. Ngay trước khi bóc, tất cả đỉnh của C vẫn còn, nên đỉnh ấy có ít nhất hai cạnh của C, trái với điều kiện degree<2. Mâu thuẫn.

Do đó:

```text
v thuộc một chu trình đơn
    => v nằm trong 2-core.
```

Đây là **chiều cần** đủ an toàn cho việc thu nhỏ khi ta muốn tìm **một chu trình** hoặc mọi chu trình: bỏ các đỉnh ngoài 2-core **không thể làm mất bất kỳ chu trình đơn nào**.

### 8.2. Chiều ngược lại có đúng không?

**Không.** “Đỉnh nằm trong 2-core” **không suy ra** “đỉnh nằm trên một chu trình đơn”.

Xem đồ thị “quả tạ” (*barbell*) gồm hai tam giác nối bằng một đường đi:

```text
      0
     / \
    1---2---3---4---5---6
                  \   /
                   7

Các cạnh:
(0,1),(1,2),(2,0)
(2,3),(3,4),(4,5)
(5,6),(6,7),(7,5)
```

Mọi đỉnh 0..7 đều có bậc ít nhất 2 trong toàn đồ thị:

- Hai tam giác chứa chu trình đơn.
- Đỉnh 3 và 4 nằm trên đường nối hai tam giác, mỗi đỉnh bậc 2.
- Các cạnh nối 2–3, 3–4, 4–5 là **cầu**: xóa một cạnh làm tăng số thành phần liên thông.

Vì thế **2-core chứa cả 3 và 4**, nhưng chúng **không thuộc bất kỳ chu trình đơn nào**. Nếu muốn tìm chính xác những đỉnh thuộc chu trình, cần phân tích thêm, chẳng hạn xác định cầu; trong đồ thị vô hướng đơn, **một cạnh nằm trên chu trình khi và chỉ khi nó không phải cầu**.

### 8.3. Thêm một thành phần chỉ có cạnh đơn

Giả sử bổ sung đỉnh 8 và 9 với cạnh 8–9. Đây là thành phần riêng có hai đỉnh bậc 1 nên sẽ bị bóc hoàn toàn. Kết quả:

```text
component sizes = [8,2]
2-core          = [0,1,2,3,4,5,6,7]
```

2-core giúp loại bỏ phần hoàn toàn không thể chứa chu trình, nhưng **không khẳng định mọi đỉnh còn lại đều có chu trình đi qua**.

### 8.4. Không dùng 2-core cho bài đường đi tùy ý

Đường đi 0–1–2–3 là đồ thị vô hướng có bốn đỉnh. Bóc bậc<2 sẽ loại toàn bộ đỉnh; 2-core rỗng.

Nhưng đường đi từ 0 tới 3 **vẫn tồn tại**, nên dùng 2-core để trả lời câu hỏi liên thông hoặc đường đi ngắn nhất sẽ **làm sai bài**. 2-core chỉ là phép lọc an toàn khi thuộc tính cần bảo toàn là **chu trình**, hoặc một bài toán đã được chứng minh chỉ cần vùng lõi như vậy.

## 9. Phép rút gọn theo cầu và đỉnh khớp

Ngoài ba thuật toán chính, có hai cấu trúc quan trọng khác để chia nhỏ đồ thị vô hướng:

- **Cầu (bridge):** Một cạnh mà nếu xóa đi, **số thành phần liên thông tăng**.
- **Đỉnh khớp (articulation point):** Một đỉnh mà nếu xóa đi, **số thành phần liên thông của phần còn lại tăng** so với ban đầu.

Có thể tìm cầu và đỉnh khớp bằng DFS với thời điểm khám phá và giá trị `low` trong **O(V+E)**. Những cấu trúc này giúp phân tích các nút cổ chai, chia thành các **khối hai-liên-thông** hoặc xây **cây khối–cầu/cây khối–đỉnh khớp** (*bridge tree / block-cut tree*) để xử lý nhiều truy vấn trên cấu trúc đơn giản hơn.

### Khi nào có ích?

Nếu muốn biết xóa một đường kết nối có làm hệ thống ngắt hay không, cầu là đối tượng trực tiếp. Nếu muốn tìm các điểm mà qua đó mọi đường liên lạc giữa hai vùng phải đi, đỉnh khớp là một gợi ý cấu trúc.

Tuy nhiên, một khối tách bởi đỉnh khớp vẫn **chia sẻ đỉnh biên** với khối khác. Nếu giải tối ưu độc lập từng khối rồi cộng, có thể đếm trùng trạng thái tại đỉnh khớp hoặc bỏ qua điều kiện ghép ở biên. Các thuật toán trên block-cut tree thường cần **trạng thái giao diện** (đã chọn đỉnh khớp chưa, chi phí kết nối, v.v.).

**Bài học:** Tìm được cấu trúc chia tách không tự động chứng minh đáp án cộng được. Phải viết chính xác ràng buộc được chia và cách ghép nghiệm ở phần biên.

## 10. Bảng lựa chọn phép rút gọn đúng bài toán

| Mục tiêu | Cấu trúc cần khai thác | Điều được bảo toàn | Cảnh báo |
| --- | --- | --- | --- |
| Hỏi hai đỉnh có liên thông trong đồ thị vô hướng không | Connected components | Tính tới được giữa hai đỉnh | Không tự trả chi phí đường đi |
| Tính tổng của những giá trị độc lập giữa các thành phần | Connected components | Phân hoạch bài toán thành nhóm | Kiểm tra ngân sách/ràng buộc toàn cục |
| Hỏi tính tới được có hướng, nhiều chu trình | SCC + condensation DAG | Tới được giữa các nhóm | Chi phí/đếm đường đi không tự bảo toàn |
| Sắp xếp phụ thuộc giữa các vùng có chu trình nội bộ | SCC + topo DAG | Thứ tự **giữa SCC**, không phải thứ tự từng đỉnh gốc | SCC nội bộ có chu trình |
| Chỉ quan tâm truy vấn từ s tới t | Reachable-from-s ∩ can-reach-t | Không bỏ đường s→t có thật | Corridor có thể chứa đỉnh không thuộc đường đơn |
| Tìm một chu trình đơn trong vô hướng đơn | 2-core peeling | Giữ lại mọi chu trình đơn | 2-core có thể chứa đỉnh không nằm trên chu trình |
| Hỏi cạnh nào là điểm nghẽn kết nối | Bridges | Xác định cạnh xóa làm tăng số thành phần | Không thay bằng kiểm tra degree đơn giản |
| Chia theo điểm nghẽn đỉnh | Articulation/block-cut tree | Cấu trúc ghép qua đỉnh biên | Phải xử lý trạng thái giao diện |
| Đếm đường đi hoặc tìm đường chi phí nhỏ nhất | Tùy thuộc mô hình, thường cần thêm dữ liệu | Chỉ dùng phép rút gọn đã chứng minh giữ giá trị | Đừng cho mọi SCC “chi phí 0” |

**Mẹo nhận dạng trong đề:** Các cụm từ “độc lập”, “không có đường nối”, “trong cùng vùng đi qua lại được”, “các nhóm phụ thuộc”, “chỉ các đỉnh đi được từ s và tới được t”, “chu trình” thường gợi ý xem xét thành phần, SCC, corridor hoặc 2-core **trước khi chọn thuật toán tối ưu nặng**.

## 11. Một quy trình giải có cấu trúc

Giả sử đề yêu cầu trả lời một câu hỏi trên đồ thị lớn. Một quy trình an toàn:

1. **Chốt hướng và trọng số:** Đồ thị có hướng không? Có cạnh song song, khuyên, trọng số âm không? Input 0-based hay 1-based?
2. **Viết điều kiện của lời giải đúng:** Có phải mọi đỉnh đều cần xem xét, hay chỉ một cặp s,t? Có cần tìm chu trình đơn, đường đi đơn, số lượng, chi phí hay chỉ tính tồn tại?
3. **Khảo sát thành phần yếu/connected components nếu vô hướng:** Một thành phần khác nguồn có chắc chắn không liên quan không?
4. **Tính SCC nếu hướng và có chu trình:** Có thể co SCC thành DAG nếu câu hỏi phụ thuộc quan hệ tới được giữa các nhóm.
5. **Lọc corridor nếu có s,t:** Chạy forward/reverse reachability và chỉ giữ các đỉnh có thể nằm trên một đường s→t.
6. **Bóc 2-core nếu chỉ cần chu trình trong vô hướng đơn:** Không dùng phép này cho bài đường đi bất kỳ.
7. **Lưu ánh xạ và dữ liệu biên:** `componentOf`, số đỉnh trong từng SCC, cung nối giữa cụm, đỉnh nguồn/đích, trọng số nội bộ cần thiết.
8. **Áp dụng thuật toán lõi trên cấu trúc nhỏ:** DFS/BFS, topo DP, tìm kiếm tổ hợp, đường đi ngắn nhất hoặc thuật toán chuyên biệt.
9. **Kiểm chứng tính tương đương:** So các trường hợp nhỏ với một cách giải trực tiếp không rút gọn.
10. **Phục hồi nghiệm khi cần:** Không in một topo order của SCC như thể đó là topo order của các đỉnh ban đầu.

**Không nhất thiết làm mọi bước**. Mỗi bước chỉ nên được dùng khi thực sự có ích và **bảo toàn mục tiêu của đề**. Với đồ thị rất nhỏ, việc tìm SCC rồi co đồ thị có thể tốn nhiều code hơn một BFS trực tiếp.

## 12. Java 17+: chương trình đầy đủ cho ba phép thu nhỏ

Chương trình gồm:

- `analyzeUndirected(n,edges)`: tìm thành phần liên thông bằng BFS, đếm kích thước và tính 2-core bằng bóc đỉnh bậc<2.
- `analyzeDirected(n,arcs)`: tìm SCC bằng Kosaraju, đánh số SCC theo **đỉnh nhỏ nhất**, dựng DAG co SCC với các cung trùng đã gộp, rồi lấy **thứ tự tô-pô của DAG** bằng min-heap.
- `sourceTargetCorridor(n,arcs,s,t)`: lấy giao giữa các đỉnh đi tới được từ s và các đỉnh có thể đi tới t thông qua đồ thị đảo.

Để dễ chạy và tái lập output, mã dùng:

- `HashSet<Long>` để gộp cạnh vô hướng lặp trước khi đếm degree.
- `TreeSet<Long>` để sắp/gộp các cung giữa SCC theo cặp chỉ số từ–đến.
- `PriorityQueue<Integer>` để trả topo order ổn định theo chỉ số SCC nhỏ nhất trong số các SCC sẵn sàng.
- Hai DFS **đệ quy** trong Kosaraju; đồ thị rất sâu cần thay bằng DFS lặp để tránh giới hạn stack của JVM.
- Mảng và danh sách cạnh **mới tạo**, không sửa mảng đầu vào.

**Quy tắc của API:**

- `n≥0`; nếu n=0, phân tích trả các mảng rỗng.
- Mỗi cạnh/cung phải có đúng hai chỉ số hợp lệ trong [0,n−1].
- Phần vô hướng chỉ chấp nhận **đồ thị đơn**, gộp cạnh trùng và từ chối self-loop.
- Phần có hướng có thể có self-loop và cung song song; chúng không làm thay đổi phân hoạch SCC.
- Hàm corridor yêu cầu s và t là đỉnh hợp lệ, vì vậy nếu n=0, không có s,t nào để truy vấn.
- SCC có thể có nhiều cách đánh số; chương trình chuẩn hóa theo **chỉ số đỉnh nhỏ nhất**, không tự suy ra thứ tự topo của SCC từ ID.

Lưu tệp **`GraphStructureReductionDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeSet;

public class GraphStructureReductionDemo {
    record UndirectedReport(int[] component,
                            int[] sizes,
                            int[] twoCore) {}

    record DirectedReport(int count,
                          int[] component,
                          int[][] dagEdges,
                          int[] topo) {}

    private static void checkN(int n) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "n must be nonnegative");
        }
    }

    private static void checkVertex(int n, int v) {
        if (v < 0 || v >= n) {
            throw new IllegalArgumentException(
                    "vertex index out of range");
        }
    }

    private static void checkEdge(int n, int[] edge) {
        if (edge == null || edge.length != 2) {
            throw new IllegalArgumentException(
                    "each edge must contain two vertices");
        }
        checkVertex(n, edge[0]);
        checkVertex(n, edge[1]);
    }

    // Thanh phan lien thong + 2-core cua do thi VO HUONG DON.
    static UndirectedReport analyzeUndirected(
            int n, int[][] edges) {
        checkN(n);
        Objects.requireNonNull(
                edges, "edges must not be null");

        List<List<Integer>> adj = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            adj.add(new ArrayList<>());
        }

        Set<Long> seenEdges = new HashSet<>();
        for (int[] edge : edges) {
            checkEdge(n, edge);
            int a = edge[0];
            int b = edge[1];

            if (a == b) {
                throw new IllegalArgumentException(
                        "self-loop not allowed in simple graph");
            }
            int lo = Math.min(a, b);
            int hi = Math.max(a, b);
            long key = (long) lo * n + hi;

            // Hai canh {a,b} va {b,a} la cung mot canh.
            if (seenEdges.add(key)) {
                adj.get(a).add(b);
                adj.get(b).add(a);
            }
        }

        int[] component = new int[n];
        Arrays.fill(component, -1);
        List<Integer> sizes = new ArrayList<>();

        for (int start = 0; start < n; start++) {
            if (component[start] != -1) {
                continue;
            }

            int id = sizes.size();
            int size = 0;
            ArrayDeque<Integer> q = new ArrayDeque<>();
            component[start] = id;
            q.addLast(start);

            while (!q.isEmpty()) {
                int u = q.removeFirst();
                size++;

                for (int v : adj.get(u)) {
                    if (component[v] == -1) {
                        component[v] = id;
                        q.addLast(v);
                    }
                }
            }
            sizes.add(size);
        }

        int[] degree = new int[n];
        boolean[] removed = new boolean[n];
        ArrayDeque<Integer> peel = new ArrayDeque<>();

        for (int v = 0; v < n; v++) {
            degree[v] = adj.get(v).size();
            if (degree[v] < 2) {
                peel.addLast(v);
            }
        }

        while (!peel.isEmpty()) {
            int v = peel.removeFirst();
            if (removed[v]) {
                continue;
            }
            removed[v] = true;

            for (int u : adj.get(v)) {
                if (!removed[u]) {
                    degree[u]--;
                    if (degree[u] < 2) {
                        peel.addLast(u);
                    }
                }
            }
        }

        int[] sizeArray = new int[sizes.size()];
        for (int i = 0; i < sizes.size(); i++) {
            sizeArray[i] = sizes.get(i);
        }

        int keep = 0;
        for (boolean r : removed) {
            if (!r) {
                keep++;
            }
        }
        int[] core = new int[keep];
        for (int v = 0, p = 0; v < n; v++) {
            if (!removed[v]) {
                core[p++] = v;
            }
        }

        return new UndirectedReport(
                component, sizeArray, core);
    }

    private static void finishDfs(
            int u, List<List<Integer>> graph,
            boolean[] seen, List<Integer> finished) {
        seen[u] = true;
        for (int v : graph.get(u)) {
            if (!seen[v]) {
                finishDfs(v, graph, seen, finished);
            }
        }
        finished.add(u);
    }

    private static void assignDfs(
            int u, List<List<Integer>> reverse,
            int[] rawComponent, int id) {
        rawComponent[u] = id;
        for (int v : reverse.get(u)) {
            if (rawComponent[v] == -1) {
                assignDfs(v, reverse, rawComponent, id);
            }
        }
    }

    // Kosaraju + co SCC thanh DAG.
    static DirectedReport analyzeDirected(
            int n, int[][] arcs) {
        checkN(n);
        Objects.requireNonNull(arcs, "arcs must not be null");

        List<List<Integer>> out = new ArrayList<>();
        List<List<Integer>> reverse = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            out.add(new ArrayList<>());
            reverse.add(new ArrayList<>());
        }
        for (int[] arc : arcs) {
            checkEdge(n, arc);
            int u = arc[0];
            int v = arc[1];
            out.get(u).add(v);
            reverse.get(v).add(u);
        }

        boolean[] seen = new boolean[n];
        List<Integer> finished = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (!seen[v]) {
                finishDfs(v, out, seen, finished);
            }
        }

        int[] rawComponent = new int[n];
        Arrays.fill(rawComponent, -1);
        int count = 0;

        for (int j = finished.size() - 1; j >= 0; j--) {
            int v = finished.get(j);
            if (rawComponent[v] == -1) {
                assignDfs(
                        v, reverse, rawComponent, count);
                count++;
            }
        }

        // Chuan hoa SCC id theo dinh nho nhat cua SCC.
        int[] smallest = new int[count];
        Arrays.fill(smallest, Integer.MAX_VALUE);
        for (int v = 0; v < n; v++) {
            int id = rawComponent[v];
            smallest[id] = Math.min(smallest[id], v);
        }

        Integer[] oldIds = new Integer[count];
        for (int i = 0; i < count; i++) {
            oldIds[i] = i;
        }
        Arrays.sort(oldIds,
                Comparator.comparingInt(id -> smallest[id]));

        int[] renumber = new int[count];
        for (int i = 0; i < count; i++) {
            renumber[oldIds[i]] = i;
        }

        int[] component = new int[n];
        for (int v = 0; v < n; v++) {
            component[v] = renumber[rawComponent[v]];
        }

        // Ma hoa canh DAG theo (from * count + to)
        // de gom trung va sap theo cap chi so.
        TreeSet<Long> encoded = new TreeSet<>();
        for (int[] arc : arcs) {
            int a = component[arc[0]];
            int b = component[arc[1]];
            if (a != b) {
                encoded.add((long) a * count + b);
            }
        }

        int[][] dagEdges = new int[encoded.size()][2];
        int index = 0;
        for (long key : encoded) {
            dagEdges[index][0] = (int) (key / count);
            dagEdges[index][1] = (int) (key % count);
            index++;
        }

        List<List<Integer>> dagOut = new ArrayList<>();
        int[] indegree = new int[count];
        for (int i = 0; i < count; i++) {
            dagOut.add(new ArrayList<>());
        }
        for (int[] edge : dagEdges) {
            dagOut.get(edge[0]).add(edge[1]);
            indegree[edge[1]]++;
        }

        PriorityQueue<Integer> ready = new PriorityQueue<>();
        for (int i = 0; i < count; i++) {
            if (indegree[i] == 0) {
                ready.add(i);
            }
        }

        int[] topo = new int[count];
        int p = 0;
        while (!ready.isEmpty()) {
            int u = ready.remove();
            topo[p++] = u;
            for (int v : dagOut.get(u)) {
                indegree[v]--;
                if (indegree[v] == 0) {
                    ready.add(v);
                }
            }
        }
        if (p != count) {
            throw new AssertionError(
                    "condensation graph must be a DAG");
        }

        return new DirectedReport(
                count, component, dagEdges, topo);
    }

    private static boolean[] reachable(
            List<List<Integer>> adj, int start) {
        int n = adj.size();
        boolean[] seen = new boolean[n];
        ArrayDeque<Integer> q = new ArrayDeque<>();
        seen[start] = true;
        q.addLast(start);

        while (!q.isEmpty()) {
            int u = q.removeFirst();
            for (int v : adj.get(u)) {
                if (!seen[v]) {
                    seen[v] = true;
                    q.addLast(v);
                }
            }
        }
        return seen;
    }

    // Loc dinh nam trong giao "di duoc tu s"
    // va "di duoc toi t" tren do thi CO HUONG.
    static int[] sourceTargetCorridor(
            int n, int[][] arcs, int source, int target) {
        checkN(n);
        checkVertex(n, source);
        checkVertex(n, target);
        Objects.requireNonNull(
                arcs, "arcs must not be null");

        List<List<Integer>> out = new ArrayList<>();
        List<List<Integer>> reverse = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            out.add(new ArrayList<>());
            reverse.add(new ArrayList<>());
        }
        for (int[] arc : arcs) {
            checkEdge(n, arc);
            out.get(arc[0]).add(arc[1]);
            reverse.get(arc[1]).add(arc[0]);
        }

        boolean[] fromSource = reachable(out, source);
        boolean[] toTarget = reachable(reverse, target);

        int length = 0;
        for (int v = 0; v < n; v++) {
            if (fromSource[v] && toTarget[v]) {
                length++;
            }
        }
        int[] kept = new int[length];
        for (int v = 0, i = 0; v < n; v++) {
            if (fromSource[v] && toTarget[v]) {
                kept[i++] = v;
            }
        }
        return kept;
    }

    static void showUndirected(
            String title, int n, int[][] edges) {
        UndirectedReport r = analyzeUndirected(n, edges);
        System.out.println(title
                + ": components=" + r.sizes().length
                + ", id=" + Arrays.toString(r.component())
                + ", sizes=" + Arrays.toString(r.sizes())
                + ", 2core=" + Arrays.toString(r.twoCore()));
    }

    static void showDirected(
            String title, int n, int[][] arcs) {
        DirectedReport r = analyzeDirected(n, arcs);
        System.out.println(title
                + ": scc=" + r.count()
                + ", id=" + Arrays.toString(r.component())
                + ", dagEdges=" + Arrays.deepToString(r.dagEdges())
                + ", topo=" + Arrays.toString(r.topo()));
    }

    static void showCorridor(
            String title, int n, int[][] arcs,
            int source, int target) {
        System.out.println(title
                + ": corridor=" + Arrays.toString(
                        sourceTargetCorridor(
                                n, arcs, source, target)));
    }

    public static void main(String[] args) {
        int[][] barbell = {
                {0, 1}, {1, 2}, {2, 0},
                {2, 3}, {3, 4}, {4, 5},
                {5, 6}, {6, 7}, {7, 5},
                {8, 9}
        };

        int[][] mainArcs = {
                {0, 1}, {1, 2}, {2, 0},
                {2, 3}, {3, 4}, {4, 3},
                {4, 5}, {5, 6}, {6, 5},
                {6, 7}, {0, 7}, {1, 8},
                {9, 7}, {7, 7}, {2, 3}
        };

        showUndirected("Barbell with tail", 10, barbell);
        showUndirected("Path", 4,
                new int[][]{{0, 1}, {1, 2}, {2, 3}});
        showUndirected("Duplicate triangle", 3,
                new int[][]{
                        {0, 1}, {0, 1}, {1, 2}, {2, 0}});
        showUndirected("Undirected empty", 0, new int[0][]);

        showDirected("Directed SCC", 10, mainArcs);
        showDirected("Directed DAG", 4,
                new int[][]{
                        {0, 2}, {1, 2}, {2, 3}});
        showDirected("Self-loop", 3,
                new int[][]{
                        {0, 1}, {1, 0}, {2, 2}});
        showDirected("Directed empty", 0, new int[0][]);

        showCorridor("Corridor 0->7",
                10, mainArcs, 0, 7);
        showCorridor("Corridor 0->8",
                10, mainArcs, 0, 8);
        showCorridor("Walk not simple", 3,
                new int[][]{
                        {0, 1}, {1, 0}, {0, 2}},
                0, 2);

        try {
            analyzeUndirected(2,
                    new int[][]{{0, 0}});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad undirected loop: " + ex.getMessage());
        }

        try {
            analyzeDirected(3,
                    new int[][]{{0, 3}});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad endpoint: " + ex.getMessage());
        }

        try {
            sourceTargetCorridor(
                    0, new int[0][], 0, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad corridor source: " + ex.getMessage());
        }

        try {
            analyzeUndirected(3,
                    new int[][]{{0}});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad edge shape: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac GraphStructureReductionDemo.java
java GraphStructureReductionDemo
```

**Stdout chính xác:**

```text
Barbell with tail: components=2, id=[0, 0, 0, 0, 0, 0, 0, 0, 1, 1], sizes=[8, 2], 2core=[0, 1, 2, 3, 4, 5, 6, 7]
Path: components=1, id=[0, 0, 0, 0], sizes=[4], 2core=[]
Duplicate triangle: components=1, id=[0, 0, 0], sizes=[3], 2core=[0, 1, 2]
Undirected empty: components=0, id=[], sizes=[], 2core=[]
Directed SCC: scc=6, id=[0, 0, 0, 1, 1, 2, 2, 3, 4, 5], dagEdges=[[0, 1], [0, 3], [0, 4], [1, 2], [2, 3], [5, 3]], topo=[0, 1, 2, 4, 5, 3]
Directed DAG: scc=4, id=[0, 1, 2, 3], dagEdges=[[0, 2], [1, 2], [2, 3]], topo=[0, 1, 2, 3]
Self-loop: scc=2, id=[0, 0, 1], dagEdges=[], topo=[0, 1]
Directed empty: scc=0, id=[], dagEdges=[], topo=[]
Corridor 0->7: corridor=[0, 1, 2, 3, 4, 5, 6, 7]
Corridor 0->8: corridor=[0, 1, 2, 8]
Walk not simple: corridor=[0, 1, 2]
Bad undirected loop: self-loop not allowed in simple graph
Bad endpoint: vertex index out of range
Bad corridor source: vertex index out of range
Bad edge shape: each edge must contain two vertices
```

### Giải thích các kết quả cần chú ý

**Barbell with tail:** Đồ thị có hai thành phần vô hướng, kích thước 8 và 2. Hai đỉnh 8,9 tạo thành một cạnh riêng, bị bóc khỏi 2-core vì có bậc 1. Các đỉnh nối giữa hai tam giác là 3 và 4 vẫn được giữ trong 2-core dù **không nằm trên chu trình đơn nào**.

**Path:** Cả bốn đỉnh liên thông nhưng 2-core rỗng, chứng minh rằng **2-core không bảo toàn tính liên thông hay đường đi**.

**Duplicate triangle:** Cạnh {0,1} xuất hiện hai lần trong input, nhưng được chuẩn hóa thành một cạnh trước khi đếm degree; vì thế ba đỉnh vẫn tạo một tam giác đúng, không có “chu trình hai cạnh” giả do đếm bản sao.

**Directed SCC:** Co 10 đỉnh thành sáu SCC. Các cung giữa cụm tạo DAG với thứ tự topo [0,1,2,4,5,3]. SCC 3 chứa đỉnh 7 có self-loop, nhưng **condensation DAG không có self-loop**. Đây là một ví dụ về việc chu trình nội bộ bị nén nhưng không xóa mất thông tin “nhóm có thể đi qua lại” khi lưu nhãn.

**Directed DAG:** Mọi đỉnh tự là một SCC vì đồ thị ban đầu đã không chứa chu trình có hướng. Co SCC không làm giảm số đỉnh; trong trường hợp này không mang lại lợi ích kích thước.

**Self-loop:** SCC {2} là một đỉnh riêng dù có khuyên 2→2; SCC {0,1} gồm hai đỉnh liên thông mạnh. DAG co không có cung nào giữa hai SCC.

**Corridor 0→7:** Loại được đỉnh 8 (không tới 7) và đỉnh 9 (không tới từ 0) mà không làm mất bất kỳ đường 0→7 nào.

**Corridor 0→8:** Chỉ giữ đỉnh 0,1,2,8; vùng SCC {0,1,2} có thể đi qua lại nhưng không buộc mọi đỉnh của SCC xuất hiện trên một đường đi đơn tới 8.

**Walk not simple:** Đỉnh 1 thuộc corridor, vì có walk 0→1→0→2, nhưng không có **đường đơn** 0→2 đi qua 1.

**Các lỗi đầu vào:** Phần vô hướng từ chối self-loop; phần có hướng từ chối đỉnh ngoài miền; corridor trên đồ thị rỗng không có nguồn hợp lệ; mỗi cạnh phải gồm đúng hai đỉnh.

### Mức tối ưu và chi phí triển khai

Ba thuật toán nền **BFS thành phần**, **Kosaraju** và **2-core peeling** đều có cận tuyến tính **O(V+E)** với danh sách kề. Chương trình còn thêm các bước để tạo **output xác định**, khiến chi phí của nhánh directed lớn hơn:

- Chuẩn hóa id SCC theo đỉnh nhỏ nhất: sắp c nhóm, O(c log c).
- Gộp/sắp các cung condensation bằng `TreeSet<Long>`: O(E log(E+1)) trong cận trên rộng.
- Lấy topo order bằng min-heap: O(c log(c+1)+E_c), với E_c là số cung DAG co.
- Phần vô hướng gộp cạnh bằng HashSet có thời gian **kỳ vọng** O(V+E), bộ nhớ O(V+E).

Vì vậy **đừng tuyên bố toàn bộ chương trình cụ thể nhất thiết O(V+E) trong trường hợp xấu**: phần sắp xếp để chuẩn hóa kết quả phát sinh log. Nếu bỏ yêu cầu ID SCC ổn định và các cung DAG phải sorted, có thể dựng các cấu trúc bằng tập hợp hash rồi thực hiện topo FIFO để đạt độ phức tạp O(V+E) **kỳ vọng**.

**Bộ nhớ** của các cấu trúc chính là O(V+E), gồm đồ thị gốc/đảo, bảng component, HashSet/TreeSet cạnh, queue, và ngăn xếp đệ quy. Với đồ thị rất sâu, chọn DFS lặp là cần thiết vì stack Java có giới hạn thực tế.

## 13. Kiểm thử các phép rút gọn thế nào?

Một chương trình rút gọn có thể biên dịch được nhưng vẫn **làm sai tính chất muốn bảo toàn**. Nên kiểm thử không chỉ mảng ID có đúng dạng hay không mà cả **bất biến toán học**.

### 13.1. Kiểm thử thành phần vô hướng

Với mỗi cặp u,v trong đồ thị nhỏ:

```text
component[u] == component[v]
    nếu và chỉ nếu
có đường vô hướng từ u tới v.
```

Có thể dùng BFS trực tiếp từ mỗi đỉnh làm oracle trên graph nhỏ. Mỗi đỉnh phải có một nhãn hợp lệ; tổng sizes phải bằng n; các nhãn component phải phân chia đỉnh không chồng lấn.

### 13.2. Kiểm thử SCC

Với đồ thị có hướng nhỏ, tính khả năng tới được bằng BFS từ mỗi đỉnh hoặc ma trận bao đóng:

```text
sccOf[u] == sccOf[v]
    iff
reachable(u,v) AND reachable(v,u)
```

Kiểm tra thêm mọi cung của DAG co đi từ cụm khác nhau, không có self-loop và tồn tại một thứ tự topo đầy đủ của các SCC.

### 13.3. Kiểm thử corridor

So kết quả với hai mảng reachable tính độc lập. Mọi đỉnh được giữ phải thỏa cả hai chiều; mọi đỉnh bị bỏ phải thiếu ít nhất một chiều. Đặc biệt kiểm tra các đỉnh **chỉ tới được từ s**, các đỉnh **chỉ đi được tới t**, đỉnh cô lập, s=t và đồ thị không có đường s→t.

### 13.4. Kiểm thử 2-core

Sau khi bóc:

- Mỗi đỉnh còn lại có **ít nhất hai hàng xóm còn lại**.
- Mọi đỉnh thuộc bất kỳ **chu trình đơn** nào của đồ thị gốc phải còn trong core.
- Một đồ thị rừng (không có chu trình) phải có 2-core rỗng.
- Các thành phần nối hai chu trình bằng đường cầu có thể vẫn chứa các đỉnh không nằm trên chu trình; điều này **không** là lỗi.

Đối với n rất nhỏ, có thể liệt kê chu trình đơn bằng brute force và đối chiếu mệnh đề “thuộc chu trình ⇒ được giữ”. Không được kiểm tra chiều đảo “được giữ ⇒ thuộc chu trình”, vì chiều đó sai.

### 13.5. Kiểm thử output Java

Đối với các test đã nêu:

- `Barbell with tail` phải cho component sizes [8,2] và 2-core 0..7.
- `Directed SCC` phải cho **sáu nhóm** và DAG topo có đủ sáu ID.
- `Corridor 0→7` bỏ chính xác 8,9.
- `Walk not simple` giữ 1 dù không có đường đơn đi qua nó.
- `n=0` được hỗ trợ ở phân tích thành phần và SCC; nhưng không có source hợp lệ cho corridor.
- Cạnh trùng vô hướng không làm tăng degree, còn cung trùng có hướng không làm SCC thay đổi.

Kiểm thử nhiều đồ thị nhỏ ngẫu nhiên, kể cả đồ thị có self-loop bên directed, nhiều thành phần rời và duplicate edges, thường phát hiện nhanh lỗi gộp nhãn, đảo chiều cung hoặc cập nhật degree sai.

## 14. Khi nào rút gọn giúp nhiều và khi nào không?

Rút gọn có ích khi:

- Đồ thị có **rất nhiều thành phần nhỏ** nhưng truy vấn chỉ liên quan một thành phần.
- Đồ thị có **nhiều chu trình trong các SCC lớn** nhưng chỉ cần xử lý quan hệ giữa các nhóm SCC.
- Nguồn s và đích t chỉ liên quan một **hành lang nhỏ** của đồ thị; nhiều đỉnh là nhánh cụt, không thể tới t.
- Bài tìm chu trình trên đồ thị vô hướng có nhiều **cây treo, lá và nhánh không tham gia chu trình**.
- Bài có nhiều truy vấn, cần tiền xử lý cấu trúc rồi trả lời nhanh hơn từng truy vấn.

Rút gọn có thể không đáng làm nếu:

- Mọi đỉnh đã nằm trong một thành phần duy nhất, toàn đồ thị là một SCC hoặc một 2-core lớn, nên hầu như không tiết kiệm kích thước.
- Bài toán trực tiếp đã chạy O(V+E) một lần; tiền xử lý SCC rồi co có thể tăng hằng số thời gian.
- Mỗi truy vấn có nguồn/đích khác nhau; lọc corridor riêng mỗi truy vấn có thể tốn thêm O(V+E) mỗi lần nếu không dùng cấu trúc tiền xử lý phù hợp.
- Đầu ra yêu cầu đường đi, thứ tự các đỉnh, hay chi phí chi tiết ở mức đỉnh gốc; khôi phục nghiệm làm phức tạp thuật toán.
- Phép rút gọn chỉ bảo toàn một tính chất khác với mục tiêu; khi ấy **không được áp dụng dù tiết kiệm nhiều thời gian**.

Điều cần tối ưu không chỉ là số đỉnh còn lại, mà là **tổng công sức chứng minh, cài đặt và khôi phục nghiệm** so với cách giải trực tiếp.

## 15. Những lỗi phổ biến

1. **Dùng thành phần liên thông vô hướng để trả lời đồ thị có hướng.** Hai đỉnh nối yếu chưa chắc tới được nhau theo cả hai chiều.
2. **Nhầm SCC với thành phần liên thông yếu.** Chỉ gom hai đỉnh khi chúng tới được nhau **theo cả hai chiều**.
3. **Co SCC rồi coi mọi đường đi nội bộ có chi phí 0.** Có thể làm sai shortest path có trọng số.
4. **Co SCC và bỏ kích thước nhóm khi cần đếm đỉnh gốc.** Đếm c SCC không tương đương đếm n đỉnh.
5. **Đưa cung nội bộ SCC vào DAG co.** Tạo self-loop và làm hỏng tính DAG.
6. **Không gộp cung song song của condensation khi bài đếm cung hoặc có logic indegree phụ thuộc số bản sao.** Phải định nghĩa đang cần quan hệ tới được hay số lượng bản sao.
7. **Giả định ID SCC tự là thứ tự topo.** ID được đánh theo quy tắc của thuật toán, thường không bảo đảm topo; phải chạy topo riêng nếu cần.
8. **In topo order của condensation như topo order của đồ thị gốc.** Đồ thị gốc có chu trình không có topo order đầy đủ.
9. **Chạy DFS Kosaraju lần hai trên đồ thị gốc thay vì đồ thị đảo.** Dễ gom nhầm các SCC.
10. **Duyệt finishing order tăng dần thay vì giảm dần ở lần hai.** Có thể tràn qua các SCC khác.
11. **Quên duyệt những đỉnh không có cung.** Đỉnh cô lập vẫn là một thành phần và một SCC riêng.
12. **Không đánh dấu visited khi thêm vào queue BFS.** Cùng đỉnh có thể bị enqueue nhiều lần, gây sai kích thước.
13. **Không chuẩn hóa cạnh vô hướng {u,v} và {v,u}.** Đếm degree hai lần có thể tạo 2-core giả.
14. **Dùng self-loop trong công thức degree của đồ thị đơn không có quy ước.** Self-loop có thể đóng góp 2 vào bậc của đa đồ thị và gây hiểu sai 2-core/chu trình đơn.
15. **Chỉ bóc các lá ban đầu một lần.** Sau khi bỏ lá, đỉnh khác có thể trở thành lá; phải lặp đến ổn định.
16. **Chỉ bóc degree=1 mà bỏ qua degree=0.** Đỉnh cô lập phải bị loại khỏi 2-core.
17. **Xem mọi đỉnh còn trong 2-core là trên một chu trình đơn.** Barbell có đường cầu và đỉnh không thuộc chu trình nhưng vẫn tồn tại trong 2-core.
18. **Dùng 2-core để trả lời shortest path hoặc connectivity.** Một đường đi đơn thuần có thể bị bóc hết.
19. **Tìm corridor bằng hai BFS cùng chiều từ s và t.** Phần từ v tới t cần BFS từ t trên **đồ thị đảo**.
20. **Nhầm reachable-from-s với can-reach-t.** Đỉnh nằm trên đường s→t cần **cả hai** điều kiện.
21. **Cho rằng một đỉnh trong corridor chắc chắn nằm trên một đường đơn s→t.** Chỉ chắc chắn có một walk qua nó; có thể phải lặp đỉnh.
22. **Không xử lý s=t đúng định nghĩa.** Đường độ dài 0 đã là một lời giải reachability theo quy ước chuẩn.
23. **Xóa đỉnh thuộc một thành phần khác nhưng bài có ràng buộc toàn cục.** Các thành phần vẫn có thể cạnh tranh chung ngân sách.
24. **Cộng các đáp án từng thành phần khi hàm mục tiêu không cộng được.** Có thể cần DP ghép ngân sách hoặc trạng thái giao diện.
25. **Giả định bridge và articulation là một kiểu.** Cầu là cạnh, đỉnh khớp là đỉnh; hành vi khi xóa khác nhau.
26. **Tách ở đỉnh khớp rồi quên trạng thái biên.** Các khối chia sẻ đỉnh khớp, có thể đếm trùng nếu cộng vô điều kiện.
27. **Khẳng định tìm SCC làm đồ thị nhỏ đi trong mọi trường hợp.** Nếu graph đã là DAG, mỗi đỉnh là SCC riêng.
28. **Không lưu ánh xạ componentOf.** Không thể trả lời truy vấn trên đỉnh gốc hoặc dựng lại nghiệm đúng.
29. **Không giữ một cung đại diện giữa hai SCC khi cần phục hồi đường đi.** Biết DAG có cung chưa đủ để biết chính xác cung u→v nào của G được dùng.
30. **Dùng thuật toán rút gọn trên đồ thị có trọng số mà bỏ các trọng số cần thiết.** Quan hệ tới được được giữ không có nghĩa tổng chi phí được giữ.
31. **Tuyên bố code có TreeSet/PriorityQueue vẫn O(V+E) worst-case.** Có thêm chi phí sắp xếp log để đầu ra xác định.
32. **Sử dụng DFS đệ quy rất sâu mà không tính nguy cơ tràn stack JVM.** Dùng DFS lặp cho dữ liệu lớn.
33. **Không kiểm tra chỉ số và dạng cạnh.** Đỉnh ngoài [0,n−1] gây truy cập sai hoặc rò dữ liệu bộ nhớ.
34. **Đếm số thành phần bằng số đỉnh chưa thăm sau DFS mà không khởi tạo lại đúng visited.**
35. **Gộp cạnh song song ở một phần nhưng không gộp ở phần khác.** Phải giữ thống nhất định nghĩa degree, indegree và quan hệ tới được.
36. **Cho rằng “thu nhỏ” luôn phải xóa đỉnh.** Đôi khi chỉ đổi biểu diễn thành DAG nhóm hoặc dùng nhãn thành phần để trả lời truy vấn nhanh hơn.
37. **Báo có chu trình chỉ vì condensation có nhiều cạnh.** Condensation luôn DAG, dù G có chu trình nội bộ.
38. **Lấy số SCC làm số thành phần liên thông vô hướng của đồ thị có hướng.** Hai khái niệm khác nhau.
39. **Tính số cặp trong thành phần bằng số phép cộng size trực tiếp.** Với thành phần size s, số cặp không thứ tự là s(s−1)/2.
40. **Quên khôi phục đường đi cụ thể nếu đề đòi đường.** Một chuỗi ID SCC không phải tour/đường đi ở mức đỉnh gốc.

## 16. Bài tập tự luyện có đáp án

**Bài 1.** Đồ thị vô hướng gồm ba thành phần có kích thước 3,2,1. Có bao nhiêu cặp đỉnh không thứ tự cùng thành phần?

**Đáp án:** C(3,2)+C(2,2)+C(1,2)=3+1+0=**4**.

**Bài 2.** Một đồ thị vô hướng có c=5 thành phần, được phép thêm cạnh nối tùy ý. Ít nhất phải thêm bao nhiêu cạnh để nó liên thông?

**Đáp án:** **4**, vì mỗi cạnh thêm giữa hai thành phần chỉ có thể làm giảm số thành phần nhiều nhất 1 và có thể nối dần năm thành phần thành một bằng bốn cạnh.

**Bài 3.** Cho đồ thị có hướng 0→1→2. Có bao nhiêu SCC?

**Đáp án:** **3**. Không có đường từ 2 quay lại 1 hoặc 0, nên mỗi đỉnh là một SCC riêng dù đồ thị có một thành phần liên thông yếu.

**Bài 4.** Cho chu trình có hướng 0→1→2→0. Có bao nhiêu SCC?

**Đáp án:** **1**, gồm {0,1,2}, vì mỗi đỉnh có thể đi tới mọi đỉnh khác theo chu trình.

**Bài 5.** Vì sao đồ thị co SCC không có chu trình?

**Đáp án:** Nếu có chu trình giữa các SCC thì từ mọi cụm trong chu trình có thể đi qua các cụm khác rồi quay lại, khiến chúng cùng thuộc một thành phần liên thông mạnh lớn hơn; trái với định nghĩa SCC tối đa.

**Bài 6.** Với ví dụ directed n=10 ở phần 6, SCC chứa các đỉnh 5 và 6 có ID bao nhiêu theo mã?

**Đáp án:** ID **2**, vì các SCC được chuẩn hóa theo chỉ số đỉnh nhỏ nhất của từng nhóm.

**Bài 7.** Condensation DAG của ví dụ n=10 có bao nhiêu đỉnh và cung phân biệt?

**Đáp án:** **6 đỉnh** và **6 cung**: (0,1),(0,3),(0,4),(1,2),(2,3),(5,3).

**Bài 8.** Một đỉnh SCC có self-loop từ một đỉnh gốc tới chính nó có khiến condensation chứa self-loop không?

**Đáp án:** Không. Cung nội bộ SCC bị bỏ khi xây condensation, để H luôn là DAG. Phần self-loop trong G vẫn có ý nghĩa nếu bài hỏi về chu trình của đồ thị gốc.

**Bài 9.** Trong đồ thị có hướng, làm sao lọc các đỉnh chắc chắn không thể xuất hiện trên đường từ s tới t?

**Đáp án:** BFS/DFS từ s trên G tạo fromS; BFS/DFS từ t trên đồ thị đảo Gᵀ tạo toT; giữ những v mà `fromS[v] && toT[v]`.

**Bài 10.** Ở ví dụ nguồn 0 đích 7, vì sao loại 8 và 9?

**Đáp án:** 8 được tới từ 0 nhưng không tới 7; 9 tới được 7 nhưng không tới được từ 0. Chúng không thể nằm trên đường từ 0 tới 7.

**Bài 11.** Với các cung 0→1,1→0,0→2, đỉnh 1 thuộc corridor(0,2) không? Có nằm trên một đường đơn 0→2 không?

**Đáp án:** Có thuộc corridor vì có walk 0→1→0→2. Không có đường **đơn** đi qua 1 vì muốn tới 2 phải quay lại 0.

**Bài 12.** Một cây vô hướng có ít nhất một cạnh có 2-core thế nào?

**Đáp án:** **Rỗng**. Mọi cây hữu hạn có lá; bóc lá lặp tới khi không còn đỉnh. Không có chu trình để giữ.

**Bài 13.** Một tam giác vô hướng có 2-core gồm những đỉnh nào?

**Đáp án:** Cả ba đỉnh. Mỗi đỉnh có bậc 2 trong đồ thị con nên không bị bóc.

**Bài 14.** Tại sao 2-core của barbell có thể chứa đỉnh 3 và 4 dù chúng không ở chu trình?

**Đáp án:** Mỗi đỉnh trên đường nối hai tam giác có bậc 2 nên không bị bóc; nhưng các cạnh nối là cầu, không nằm trên chu trình đơn. 2-core là **tập bao** các đỉnh chu trình, không trùng chính xác với tập ấy.

**Bài 15.** Nếu bài chỉ hỏi tìm một đường từ 0 tới 3 trên graph 0–1–2–3, có được xóa mọi đỉnh ngoài 2-core không?

**Đáp án:** Không. 2-core của path là rỗng nhưng đường từ 0 tới 3 vẫn tồn tại. Phép lọc không bảo toàn thuộc tính đường đi.

**Bài 16.** Khi có các thành phần liên thông tách biệt nhưng ngân sách toàn cục là k lựa chọn, có thể cộng các kết quả tối ưu từng thành phần độc lập không?

**Đáp án:** Chưa chắc. Cần phân bổ k giữa các thành phần; thường phải kết hợp các phương án bằng DP hoặc một cách ghép phù hợp với ràng buộc toàn cục.

**Bài 17.** Hai đỉnh u,v trong cùng SCC có nhất thiết có khoảng cách ngắn nhất bằng 0 không?

**Đáp án:** Không. Chỉ bảo đảm **tồn tại đường đi theo cả hai chiều**. Độ dài/chi phí có thể dương, không đều hoặc phụ thuộc hướng; gán chi phí nội bộ bằng 0 khi co SCC là sai cho shortest path tổng quát.

**Bài 18.** Kosaraju có độ phức tạp gì? Vì sao mã ví dụ có thể tốn thêm log khi in condensation?

**Đáp án:** Hai DFS và đảo đồ thị tốn O(V+E). Mã còn sắp nhãn SCC và dùng TreeSet/PriorityQueue để tạo output ổn định, phát sinh thêm chi phí O(c log c) và O(E log E) theo cận trên rộng.

**Bài 19.** Tại sao cung song song (2,3) trong ví dụ directed không làm tăng số cung phân biệt của condensation?

**Đáp án:** Cả hai bản sao cùng cho quan hệ từ SCC 0 đến SCC 1. Vì bài chỉ xét **tồn tại quan hệ nối**, TreeSet gộp thành một cung (0,1). Nếu bài cần **số lượng cung gốc**, phải lưu thêm multiplicity.

**Bài 20.** Làm thế nào kiểm thử rằng ánh xạ SCC đúng trên một graph n nhỏ?

**Đáp án:** Tính reachability từ mỗi đỉnh. Với mọi u,v, phải có `sccOf[u]==sccOf[v]` **khi và chỉ khi** u tới v và v tới u. Kiểm tra thêm condensation không có chu trình.

**Bài 21.** Tại sao không thể suy ra có một topo order của mọi đỉnh gốc từ topo order của SCC?

**Đáp án:** Đồ thị gốc có thể có chu trình nội bộ mỗi SCC. Topo order chỉ sắp **các nhóm** theo cung giữa nhóm, không giải được mâu thuẫn thứ tự giữa các đỉnh trong chu trình gốc.

**Bài 22.** Một phép rút gọn tốt cần ghi lại những thông tin nào để khôi phục nghiệm?

**Đáp án:** Ánh xạ từ đỉnh gốc tới nhóm, các đỉnh trong từng nhóm, những cung đại diện giữa nhóm khi cần, thông tin trọng số/đỉnh biên liên quan và chính xác thuộc tính được bảo toàn.

## Ghi nhớ

**Khai thác cấu trúc đồ thị để thu nhỏ bài toán** nghĩa là tìm phép biến đổi **đúng với câu hỏi** trước khi chạy một thuật toán nặng. Đồ thị vô hướng có thể tách thành các **thành phần liên thông** để giới hạn vùng tìm kiếm hoặc giải độc lập khi ràng buộc phân rã. Đồ thị có hướng có thể co **SCC** thành **condensation DAG** để giữ quan hệ tới được giữa các nhóm và xử lý phụ thuộc theo thứ tự tô-pô. Bài toán từ **s tới t** có thể bỏ các đỉnh không thuộc giao `reachableFrom(s)∩canReach(t)`; tập giao là bao an toàn của các đường nguồn–đích. Với bài tìm **chu trình đơn** ở đồ thị vô hướng đơn, bóc các đỉnh bậc<2 lấy **2-core** mà không mất chu trình.

Cả connected components, Kosaraju, corridor và 2-core peeling đều có lõi thuật toán **O(V+E)** với danh sách kề. Các bước sắp nhãn/cung để output ổn định có thể tốn thêm log. Quan trọng nhất: **có bằng chứng rằng phép rút gọn giữ nguyên thuộc tính hoặc giá trị mà đề yêu cầu**. Không tự đồng nhất “cùng SCC” với “đường đi chi phí 0”, “nằm trong 2-core” với “nằm trên chu trình”, hay “thuộc corridor” với “nằm trên một đường đơn”.
