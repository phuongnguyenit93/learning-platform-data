# Thuật toán tham số hóa và giới hạn tìm kiếm theo tham số

**Thuật toán tham số hóa** (*parameterized algorithms*) là cách thiết kế và phân tích lời giải cho bài toán khó bằng cách tách kích thước đầu vào `n` khỏi một **tham số k** thể hiện phần khó của bài. Thay vì chỉ hỏi thuật toán có chạy đa thức theo n trên mọi trường hợp hay không, ta hỏi: **Khi k nhỏ, liệu có thể giải chính xác bằng một hàm theo k nhân với đa thức bậc cố định theo n?**

Đây là trọng tâm của **độ phức tạp tham số hóa** (*parameterized complexity*). Khác với heuristic hoặc giới hạn thời gian đơn thuần, một thuật toán **FPT** (*fixed-parameter tractable*) cung cấp **bảo đảm độ đúng tuyệt đối** và giới hạn thời gian dạng toán học có thể chứng minh.

Bài thuộc chủ đề **Độ khó bài toán**. Ví dụ xuyên suốt là **Vertex Cover tham số k**: cho đồ thị vô hướng và ngân sách k, tìm tập không quá k đỉnh sao cho **mỗi cạnh** có ít nhất một đầu mút trong tập. Ta sẽ đi từ vét cạn `n^k`, đến cây tìm kiếm độ sâu k, quy tắc bắt buộc chọn đỉnh, cận dưới matching, rồi **kernelization**. Mã Java 17+ chạy độc lập trả về **một nghiệm cụ thể**, kiểm tra nghiệm và đối chiếu với vét cạn trên hàng nghìn trường hợp.

## 1. Định nghĩa bài toán tham số hóa

Một bài toán tham số hóa có đầu vào gồm đối tượng x và tham số nguyên không âm k:

```text
INSTANCE: (x,k)
QUESTION: Có tồn tại một nghiệm hợp lệ thỏa điều kiện k?
```

Ở bài Vertex Cover:

```text
Input:
  G=(V,E), đồ thị vô hướng đơn
  k>=0, ngân sách số đỉnh

Question:
  Tồn tại S subset V sao cho |S|<=k
  và với mọi cạnh {u,v} trong E:
      u in S OR v in S ?
```

Ký hiệu `n=|V|`, `m=|E|`. **Tham số k không phải lúc nào cũng nhỏ**; phương pháp này đặc biệt hữu ích khi k nhỏ so với n hoặc khi cấu trúc bài toán có một tham số nhỏ khác.

**Ví dụ:**

- Đồ thị hình sao với một tâm nối 1.000 lá: `n=1001`, nhưng Vertex Cover tối ưu chỉ cần **k=1** (chọn tâm).
- Tam giác có ba cạnh: cần tối thiểu **k=2**.
- Chu trình lẻ C5: cần tối thiểu **k=3**.
- Ba cạnh rời nhau không chung đỉnh: cần ít nhất **k=3**.

Đồ thị có thể rất lớn nhưng k nhỏ. Tuy nhiên, tham số hóa **không tự làm mọi bài toán khó trở thành dễ**: cần tìm được một thuật toán có độ phức tạp phù hợp, và không phải mọi bài toán đều FPT với mọi tham số.

### 1.1. Thuật toán FPT là gì?

Một bài toán thuộc lớp **FPT đối với tham số k** nếu có thuật toán giải chính xác trong thời gian:

```text
T(n,k) <= f(k) * n^c
```

với `f` là một hàm tính được **chỉ phụ thuộc k**, và `c` là một **hằng số không phụ thuộc k**. Có thể thay n bằng kích thước mã hóa đầu vào `N`, hoặc viết `f(k)*poly(N)` cho tổng quát.

Ví dụ:

```text
2^k * (n+m)
3^k * n^2
k! * n^3
```

đều có **dạng FPT**, vì số mũ của n không tăng theo k. Một thuật toán FPT có thể vẫn rất chậm khi k lớn: `2^50` là rất nhiều, và `k!` tăng đặc biệt nhanh.

**Lưu ý:** Viết `2^k * (n+m)` là FPT theo tổng kích thước đồ thị. Viết `f(k)*poly(n+m)` cũng chính xác; m có thể là O(n²) trong đồ thị đơn.

### 1.2. XP khác FPT ở đâu?

Một thuật toán thuộc **XP** (*slice-wise polynomial*) nếu thời gian có dạng:

```text
T(n,k) <= n^{f(k)} * poly(k)
```

với mỗi k **cố định**, nó là đa thức theo n, nhưng **bậc đa thức được phép phụ thuộc k**.

Ví dụ:

```text
n^k
n^(k+2)
```

là các dạng XP, **không phải một chứng minh FPT**. Vét cạn tất cả tập k đỉnh có thể cần `C(n,k)` lựa chọn, cận trên `O(n^k)`; đây là lời giải XP tự nhiên cho Vertex Cover, nhưng không thể kết luận “FPT vì k là hằng số nhỏ trong test”.

| Tính chất | FPT | XP |
| --- | --- | --- |
| Dạng thời gian | `f(k)*n^c` | `n^{f(k)}` |
| Số mũ của n | Hằng số độc lập k | Có thể tăng theo k |
| Khi k cố định | Đa thức | Đa thức |
| Bảo đảm khi n lớn và k nhỏ | Thường phù hợp hơn | Có thể rất chậm do `n^k` |
| Ví dụ dạng | `2^k*n²` | `n^k` |

Mọi thuật toán FPT có thể được xem là cho tính XP với cách đánh giá thích hợp, nhưng **không phải mọi lời giải XP đều là FPT**. Đối với một bài toán cụ thể, muốn nói **nó không có lời giải FPT** thường cần giả thiết hoặc kết quả độ phức tạp tham số hóa, không phải chỉ nhìn thấy một thuật toán XP.

### 1.3. Tham số hóa khác thuật toán xấp xỉ

- **FPT chính xác:** Có thể tốn `2^k`, nhưng kết quả có/không và nghiệm trả về là **chính xác**.
- **Approximation:** Có thể chạy đa thức theo n và tìm một nghiệm gần tối ưu theo một tỷ lệ, nhưng **không nhất thiết tối ưu**.
- **Heuristic:** Thường hiệu quả thực tế, nhưng có thể không có bảo đảm lời giải tối ưu hoặc độ phức tạp.
- **Timeout/cutoff:** Dừng sau ngân sách có thể trả “không biết” nếu chưa giải xong; **không được tự biến timeout thành kết luận NO**.

Một thuật toán tham số hóa có thể kết hợp kernel, heuristic ưu tiên nhánh hoặc xấp xỉ để tìm cận tốt, nhưng kết luận chính xác vẫn phải dựa trên các quy tắc **sound** và phép duyệt đầy đủ có chặn.

## 2. Bài toán mẫu: Vertex Cover với ngân sách k

Với đồ thị vô hướng đơn G, một **vertex cover** là tập S đỉnh sao cho **mọi cạnh đều có ít nhất một đầu mút thuộc S**.

Ví dụ tam giác:

```text
Vertices: {0,1,2}
Edges: {(0,1),(1,2),(0,2)}

k=1: NO
k=2: YES, ví dụ S={0,1}
```

Một đỉnh không thể phủ cả ba cạnh của tam giác, nhưng hai đỉnh thì có.

### 2.1. Bài toán quyết định và bài toán tối ưu

**Quyết định:** “Có cover kích thước không quá k không?” Trả **YES/NO**.

**Dựng nghiệm:** Nếu YES, trả tập đỉnh S làm **chứng cứ**; sau đó kiểm tra độc lập S bằng cách duyệt từng cạnh.

**Tối ưu:** “Kích thước cover nhỏ nhất bằng bao nhiêu?” Có thể gọi bộ giải quyết định theo k tăng dần từ 0 đến K:

```text
for k=0..K:
    if findCover(G,k) returns YES:
        return this cover as minimum
return "no cover of size <= K"
```

Tính chất đơn điệu: nếu có cover kích thước ≤k, cũng có cover kích thước ≤k+1. Vì thế phương pháp **iterative deepening theo tham số** đúng; khi gặp giá trị k đầu tiên cho YES, nghiệm là tối ưu. Nếu biết cận dưới/lớn nhất, có thể cải tiến cách tìm k, nhưng phải bảo đảm solver trả đúng YES/NO. **Không nên gọi đây là tìm kiếm nhị phân trên dữ liệu đã sắp xếp:** ta đang tìm ngưỡng khả thi theo k.

### 2.2. Vét cạn n^k chưa đủ cho FPT

Thử mọi tập S có không quá k đỉnh:

```text
sum_{i=0..k} C(n,i) <= O(n^k) for k>=1
```

Mỗi tập kiểm tra tất cả m cạnh. Độ phức tạp có dạng `n^{O(k)}*poly(n+m)`; số mũ của n vẫn phụ thuộc k. Đây là thuật toán XP, không phải lời giải FPT đã chứng minh.

**Ý tưởng thay thế:** Chỉ quyết định giữa **hai đầu mút của một cạnh chưa được phủ**; mỗi quyết định chắc chắn phải được thực hiện bởi mọi nghiệm, và ngân sách k giảm ít nhất 1 mỗi mức. Do đó số nhánh phụ thuộc k, không phụ thuộc trực tiếp số lượng tập con của n.

## 3. Cây tìm kiếm giới hạn theo tham số

Gọi `E'` là tập **cạnh chưa được phủ** bởi những đỉnh đã chọn, và `r` là ngân sách còn lại (ban đầu `r=k`).

Nếu không còn cạnh chưa phủ, ta đã tìm được vertex cover và trả YES cùng danh sách đỉnh.

Nếu `r=0` mà vẫn còn cạnh chưa phủ, trả NO.

Nếu tồn tại cạnh chưa phủ `{u,v}`, **mọi vertex cover phải chọn ít nhất một trong u,v**. Vì vậy ta có hai nhánh **đầy đủ**:

```text
SEARCH(E',r):
    if E' empty: YES
    if r == 0: NO

    choose an uncovered edge {u,v}

    Branch 1:
      include u, remove edges incident to u
      SEARCH(remainder, r-1)

    Branch 2:
      include v, remove edges incident to v
      SEARCH(remainder, r-1)

    if either branch succeeds: YES
    otherwise: NO
```

**Cơ sở tính đúng** nằm ở ràng buộc của đúng cạnh `{u,v}`. Nếu một nghiệm S không chứa u, nó **bắt buộc chứa v**. Nếu S không chứa v, nó **bắt buộc chứa u**. Kể cả S chứa cả hai, ít nhất một trong hai nhánh vẫn có thể dẫn tới nghiệm (trong một nhánh, S vẫn là ứng viên).

### 3.1. Vì sao gọi là “giới hạn tìm kiếm theo tham số”?

Cây có tối đa hai con mỗi nút; ở mỗi nhánh ngân sách r giảm 1. Độ sâu tìm kiếm tối đa k (nếu không kể các bước trả kết quả). Số nút tối đa:

```text
1 + 2 + 4 + ... + 2^k
    = 2^(k+1)-1
    = O(2^k).
```

Mỗi nút nếu quét các cạnh và đỉnh để tìm cạnh chưa phủ dùng `O(n+m)`, nên:

```text
T(n,m,k) = O(2^k * (n+m)).
```

Đó là dạng **FPT**. Nó vẫn có thể lớn với k cao, nhưng **số mũ của kích thước đầu vào không tăng cùng k** như `n^k`.

### 3.2. Dùng bất biến thay vì dựa vào may mắn

Tại mỗi nút:

- Tập đỉnh `selected` là những đỉnh đã chọn, không bao giờ chọn cùng một đỉnh hai lần trong một nhánh.
- Một cạnh được phủ nếu ít nhất một đầu mút thuộc `selected`.
- r là số đỉnh mới còn được phép chọn.
- Tính khả thi tại nút nghĩa là **có thể bổ sung ≤r đỉnh để phủ mọi cạnh chưa phủ**.

Mọi nhánh giảm r và không loại bỏ khả năng tìm một nghiệm hợp lệ nếu chưa chứng minh điều kiện cắt tỉa. Các lựa chọn ưu tiên để có nghiệm sớm có thể dùng heuristic, nhưng **không được xóa nhánh còn có thể chứa nghiệm**.

## 4. Quy tắc giảm bắt buộc: bậc đỉnh > r

Xét **đồ thị phần dư** chỉ gồm những cạnh chưa được phủ. Bậc phần dư của v là số cạnh chưa phủ kề với v.

Nếu:

```text
degreeResidual(v) > r,
```

thì v **bắt buộc thuộc mọi vertex cover còn lại kích thước ≤r**.

**Chứng minh:** Giả sử không chọn v. Mỗi trong hơn r cạnh kề với v phải được phủ bằng **đầu mút còn lại** của cạnh. Vì đồ thị đơn, những đầu mút kia là các đỉnh **khác nhau**. Cần hơn r đỉnh, mâu thuẫn ngân sách r. Vậy bắt buộc chọn v.

Áp dụng:

```text
choose v;
mark v selected;
r = r-1;
recompute residual graph.
```

Đây là một **reduction rule an toàn**, không phải heuristic dự đoán. Nếu nhánh sau đó thất bại, phải **backtrack** và bỏ chọn v trước khi trở về mức cha.

### 4.1. Ví dụ hình sao

```text
V={0,1,2,3,4,5,6}
E={(0,1),(0,2),(0,3),(0,4),(0,5),(0,6)}
k=1.
```

Bậc phần dư của đỉnh 0 là 6, lớn hơn r=1, nên mọi cover kích thước 1 phải chọn 0. Chọn 0 phủ cả sáu cạnh, còn r=0, không còn cạnh. Nghiệm chính xác `{0}`.

Nếu k=0 và còn cạnh, kết luận NO ngay; không cần chọn đỉnh.

### 4.2. Vì sao cần giả thiết đồ thị đơn?

Nếu có **cạnh song song**, số cạnh kề >r không đồng nghĩa có >r láng giềng khác nhau. Nếu có **self-loop**, endpoint đó trực tiếp buộc phải chọn theo định nghĩa phủ cạnh. Mã Java trong bài **từ chối self-loop và cạnh lặp**, bảo đảm quy tắc bậc đỉnh sử dụng đúng giả thiết. Khi mở rộng sang multigraph, phải xử lý trùng cạnh/self-loop hoặc chuyển về đồ thị đơn tương đương đúng cách.

## 5. Giới hạn cạnh sau khi giảm bậc: m' ≤ r²

Sau khi đã xử lý tất cả đỉnh có bậc phần dư >r, ta có:

```text
maxResidualDegree <= r.
```

Nếu một cover còn lại dùng không quá r đỉnh, mỗi đỉnh được chọn có thể phủ tối đa r cạnh chưa phủ. Do đó r đỉnh phủ tối đa:

```text
r * r = r^2 cạnh.
```

Vậy nếu số cạnh chưa phủ `m'` thỏa:

```text
m' > r^2
```

thì **chắc chắn không có nghiệm** với ngân sách còn lại r.

### 5.1. Ví dụ chu trình lẻ C5

```text
E={(0,1),(1,2),(2,3),(3,4),(4,0)}
k=2.

max degree = 2 <= k
m'=5
k^2=4
m'>k², nên NO.
```

Đúng với thực tế C5 cần tối thiểu 3 đỉnh để phủ tất cả các cạnh.

**Thứ tự rất quan trọng:** Phải áp dụng quy tắc **đỉnh bậc >r bắt buộc chọn** trước khi kết luận từ `m'>r²`. Nếu vẫn có đỉnh bậc >r, mỗi đỉnh được chọn có thể phủ hơn r cạnh, nên suy luận `r²` **không hợp lệ** ở giai đoạn đó.

### 5.2. Liên hệ kernelization

**Kernelization** là phép biến đổi trong thời gian đa thức từ `(G,k)` sang `(G',k')` tương đương về câu trả lời YES/NO, trong đó kích thước đầu ra được chặn bởi một hàm chỉ theo k.

Sau quy tắc bậc lớn:

- Nếu `m'>r²`, trả NO ngay.
- Nếu `m'≤r²`, có không quá `2m'≤2r²` **đỉnh còn kề ít nhất một cạnh**.
- Các đỉnh cô lập không ảnh hưởng Vertex Cover, có thể bỏ khỏi kernel.
- Vì `r≤k` ban đầu, kích thước phần dư (sau bỏ isolated) có O(k²) cạnh/đỉnh.

Đây là ý tưởng **kernel bậc hai** cho Vertex Cover. Trong mã Java, thay vì dựng một đối tượng đồ thị kernel riêng, bộ giải **kiểm tra ngay cận cạnh** và làm việc trên những cạnh chưa phủ. Lập luận kernel vẫn chứng minh tại sao phần “khó” có thể được nén theo k.

Đừng nhầm `k²` là số cạnh gốc được phép có: đồ thị sao có rất nhiều cạnh nhưng k=1 vẫn có nghiệm, nhờ quy tắc chọn đỉnh tâm trước khi áp cận.

## 6. Cận dưới từ matching rời đỉnh

Một **matching** là tập cạnh không chia sẻ đầu mút. Nếu matching có t cạnh rời đỉnh, **bất kỳ vertex cover nào cũng phải chọn ít nhất t đỉnh**, bởi mỗi cạnh trong matching cần một đầu mút riêng.

```text
matchingSize > r  => NO
```

Ta có thể tìm một **maximal matching** bằng greedy:

```text
matching = empty
for each uncovered edge {u,v}:
    if neither endpoint has been matched:
        add edge {u,v}
```

**Maximal** nghĩa là không thể thêm cạnh nào mà vẫn giữ rời đỉnh; nó **không nhất thiết là maximum matching** (matching có số cạnh lớn nhất). Tuy vậy, **bất kỳ matching nào** đều cho một cận dưới hợp lệ lên kích thước vertex cover, nên greedy đủ để cắt nhánh an toàn nếu tìm được hơn r cạnh.

### 6.1. Ví dụ ba cạnh rời nhau

```text
V={0,1,2,3,4,5}
E={(0,1),(2,3),(4,5)}
k=2.
```

Cả ba cạnh đều rời đỉnh, matching có 3 cạnh. Một cover phải lấy ít nhất một endpoint từ **mỗi** cạnh, nên cần ≥3 đỉnh. Cận dưới matching kết luận NO.

Trong ví dụ này:

```text
max degree = 1 <= k
m=3 <= k²=4
```

nên quy tắc giới hạn cạnh **không loại nhánh**, còn matching cắt được ngay. Đây là lý do kết hợp nhiều quy tắc **đều an toàn nhưng độc lập về sức mạnh**.

### 6.2. Matching không quyết định mọi trường hợp

Nếu greedy matching tìm t≤r, **không** được kết luận YES. Nó chỉ chứng minh nghiệm tối ưu cần **ít nhất t** đỉnh, không đảm bảo t đỉnh ấy tạo vertex cover. Trên tam giác, matching có thể chỉ gồm 1 cạnh, nhưng vertex cover tối ưu cần 2 đỉnh.

## 7. Trình tự xử lý trong bộ giải chính xác

Ở mỗi nút DFS của chương trình:

```text
DFS(selected,r):
    compute all uncovered edges E'
    if E' empty: YES
    if r == 0: NO

    if some residual degree(v)>r:
        select v (forced)
        recurse with r-1
        undo selection on failure
        return result

    // Now every residual degree <= r:
    if |E'| > r*r: NO

    matching = greedy maximal matching of E'
    if |matching|>r: NO

    pick one uncovered edge {u,v}
    select u; recurse with r-1; undo on failure
    select v; recurse with r-1; undo on failure

    if both branches fail: NO
```

Thứ tự bảo đảm mỗi phép cắt tỉa có **tiền đề đã được chứng minh**. Quy tắc bậc lớn và matching không thay thế nhánh tìm kiếm ở trường hợp còn lại.

### 7.1. Khi trả YES phải có witness

Trong Java, `boolean[] selected` giữ lựa chọn hiện tại. Nếu đệ quy tìm được lời giải, chương trình **giữ nguyên** các đỉnh đang được chọn trên đường thành công. Nếu một nhánh thất bại, chương trình **bỏ chọn** đỉnh của nhánh ấy trước khi thử nhánh kia. Sau cùng, `solve` thu các chỉ số v có `selected[v]` và xác nhận:

```text
|selected| <= k
AND
for every edge {u,v}:
    selected[u] OR selected[v].
```

Đây là bước kiểm tra **nghiệm cụ thể**. Chỉ có dòng `return true` mà không quản lý backtrack chính xác có thể khiến thuật toán dựng một cover chứa đỉnh từ **những nhánh đã thất bại**.

### 7.2. Cắt tỉa NO phải có lý do chứng minh

Ba loại NO an toàn:

1. **Hết ngân sách:** `r=0` mà còn ít nhất một cạnh.
2. **Quá nhiều cạnh:** Đã bảo đảm bậc phần dư ≤r nhưng `m'>r²`.
3. **Matching quá lớn:** Có `r+1` cạnh phần dư đôi một rời đỉnh.

Không được dùng “đã tìm lâu quá”, “cận ước lượng có vẻ xấu” hoặc “greedy chưa thấy nghiệm” để trả NO trong một thuật toán chính xác. Những heuristic này có thể dùng để **ưu tiên nhánh**, không làm tiêu chí loại các nhánh chưa được chứng minh bất khả thi.

## 8. Chứng minh tính đúng của FPT Vertex Cover

### 8.1. Bất biến của trạng thái DFS

Mỗi trạng thái gồm những đỉnh đã chọn S và ngân sách r. Các cạnh còn lại E' là đúng những cạnh chưa có endpoint thuộc S. Phát biểu:

```text
DFS(S,r) = YES
  iff
exists S' subset V\S with |S'|<=r
such that S union S' covers every original edge.
```

**Cơ sở:** Nếu E' rỗng, S đã phủ tất cả cạnh → YES. Nếu r=0 và E' còn cạnh, không thể thêm đỉnh → NO.

**Giảm bậc lớn:** Nếu v có hơn r hàng xóm khác nhau trong E', mọi S' hợp lệ bắt buộc chứa v. Do đó chọn v rồi gọi DFS với r−1 giữ nguyên tính khả thi.

**Cận cạnh:** Nếu mọi bậc phần dư ≤r nhưng `m'>r²`, không thể phủ hết E' bằng ≤r đỉnh; trả NO không loại nghiệm.

**Cận matching:** Nếu E' chứa >r cạnh rời đỉnh, mọi S' cần >r đỉnh; trả NO không loại nghiệm.

**Phân nhánh:** Với cạnh `{u,v}∈E'`, mọi S' phủ E' chứa u hoặc v. Bởi vậy bài toán ban đầu khả thi **khi và chỉ khi** ít nhất một nhánh chọn u hoặc v khả thi với ngân sách r−1. Quy nạp theo r cho kết luận đúng.

### 8.2. Kết thúc và độ sâu

Mỗi lần DFS đệ quy, ít nhất một đỉnh mới được chọn và r giảm 1. Vì r không âm và bắt đầu ở k, chiều sâu các lời gọi đệ quy được chặn bởi k+1 (tính cả nút gốc). Không có vòng đệ quy giữ nguyên r, nên quá trình tìm kiếm kết thúc.

**Chú ý triển khai:** Với k rất lớn, đệ quy Java có thể gặp giới hạn stack. Phân tích FPT không xóa các giới hạn tài nguyên vật lý của JVM; chương trình được thiết kế để minh họa bài toán với k nhỏ hoặc vừa.

### 8.3. Độ phức tạp

Cây DFS có tối đa `O(2^k)` nút trong trường hợp chưa bị cắt tỉa. Mỗi nút:

- Tạo mảng degree kích thước n: `O(n)`.
- Quét m cạnh để tính bậc và cạnh còn chưa phủ: `O(m)`.
- Kiểm tra bậc, cận `r²`, tìm greedy matching bằng cách quét cạnh: `O(n+m)`.
- Kiểm tra witness cuối: `O(n+m)`.

Do đó:

```text
Time = O(2^k * (n+m))
Space (excluding read-only graph storage)
     = O(n+k) for selected/degrees/matching/recursion.
```

Các mảng `degree` và `matched` của **mỗi lời gọi** có thể sống đồng thời trên stack của các mức đệ quy. Trong **cài đặt Java cụ thể** dưới đây, không tái sử dụng workspace giữa mức đệ quy, nên cận bộ nhớ phụ an toàn là:

```text
O(k*n + k)
```

cùng đồ thị đầu vào `O(n+m)`. Nếu chủ động tái sử dụng/giải phóng bảng tạm giữa các mức, có thể giảm memory implementation, nhưng không được báo `O(n)` nếu nhiều mảng n phần tử tồn tại đồng thời.

Tổng tính cả lưu graph:

```text
O(n+m + k*n + k).
```

Với kernelization tường minh có thể giảm kích thước phần dư theo `O(k²)`, nhưng thuật toán **không tự động có thời gian `O(2^k*k²)` chỉ vì suy ra cận kernel**: còn có bước xây/duyệt graph ban đầu, chi phí tạo kernel, và cấu trúc dữ liệu khác. Cận O(2^k*(n+m)) ở trên an toàn cho mã hiện tại.

## 9. Kernel, branching, matching phối hợp ra sao?

| Thành phần | Kết luận khi kích hoạt | Vì sao đúng? | Tác dụng |
| --- | --- | --- | --- |
| `degree(v)>r` | **Bắt buộc chọn v** | Bỏ v sẽ phải chọn >r láng giềng | Giảm r không cần nhánh đôi |
| `maxDegree≤r && m'>r²` | **NO** | r đỉnh phủ tối đa r² cạnh | Loại nhanh input không khả thi |
| Matching có `t>r` | **NO** | Mỗi cạnh rời đỉnh cần endpoint riêng | Cận dưới lời giải |
| Chọn cạnh `{u,v}` | **Nhánh chọn u hoặc v** | Ít nhất một endpoint phải nằm trong cover | Tìm kiếm đầy đủ độ sâu ≤k |
| E' rỗng | **YES + witness** | Tất cả cạnh đã phủ | Kết thúc thành công |
| E' còn, r=0 | **NO** | Không còn quyền chọn đỉnh | Kết thúc bất khả thi |

Các quy tắc an toàn có thể thay đổi thứ tự hợp lý để tối ưu thời gian, nhưng phải giữ **tiền đề**: đặc biệt `m'>r²` chỉ dùng sau khi biết mọi bậc phần dư ≤r. Một phép matching greedy cho cận dưới, không cho nghiệm bao phủ trực tiếp.

## 10. Ví dụ tự phân tích bằng tay

### 10.1. Hình sao, k=1

```text
Edges: {(0,1),(0,2),(0,3),(0,4),(0,5),(0,6)}
k=1, degree(0)=6>1

Forced: choose vertex 0.
Residual edges: none.
Answer: YES, cover={0}.
```

### 10.2. Tam giác, k=1 và k=2

```text
E={(0,1),(1,2),(0,2)}.

k=1:
  all degrees=2>1, force one vertex;
  residual still contains one edge with r=0.
  => NO.

k=2:
  choose endpoint 0 of edge (0,1);
  residual edge (1,2), choose 1.
  => YES, cover={0,1}.
```

### 10.3. Chu trình C5, k=2

```text
E={(0,1),(1,2),(2,3),(3,4),(4,0)}
k=2
maxDegree=2<=k
m=5>k²=4
=> NO.
```

Đối với k=3, tồn tại cover 3 đỉnh, ví dụ `{0,1,3}`. Không có mâu thuẫn: tăng ngân sách có thể biến NO thành YES.

### 10.4. Ba cạnh độc lập, k=2

```text
E={(0,1),(2,3),(4,5)}
k=2

maxDegree=1<=2
m=3<=2²
matching size=3>2
=> NO.
```

Đây là ví dụ matching cắt được khi cận cạnh `r²` chưa đủ mạnh.

### 10.5. Đồ thị không có cạnh

```text
n=4, m=0, k=0
S={} covers every edge (vacuously).
=> YES, cover=[].
```

Đỉnh cô lập không cần được chọn chỉ để đạt số lượng k; điều kiện là **không quá k**, không phải **đúng k**.

## 11. Chương trình Java 17+ đầy đủ

**Tên file: `ParameterizedVertexCoverDemo.java`.** Mã giải Vertex Cover trên **đồ thị vô hướng đơn không có self-loop hay cạnh lặp**, đỉnh đánh số từ 0 tới n−1. Đầu vào hợp lệ có `k>=0`; đồ thị rỗng và các đỉnh cô lập được phép.

Các phần:

- `Graph`: kiểm tra chỉ số, từ chối self-loop/cạnh trùng; sao chép danh sách cạnh để ổn định dữ liệu.
- `solve(g,k)`: tìm đúng một vertex cover kích thước ≤k nếu tồn tại; trả `feasible`, danh sách đỉnh và thống kê số nút duyệt/cắt tỉa.
- `dfs`: áp dụng luật bậc lớn, luật m'>r², matching, rồi nhánh hai đầu mút.
- `covers`: kiểm tra witness có các đỉnh duy nhất, mọi cạnh đều được phủ.
- `minimumUpTo(g,maxK)`: tăng k từ 0, trả nghiệm tối ưu nếu có kích thước không quá maxK.
- `bruteFeasible`: oracle **độc lập** duyệt toàn bộ tập con đỉnh với đồ thị n≤20; chỉ dùng cho kiểm thử, **không** dùng để giải chính.
- `exhaustiveTests`: kiểm tra **toàn bộ 2^10=1024 đồ thị đơn có 5 đỉnh gắn nhãn** và mọi k từ 0 tới 5, tổng **6144 trường hợp**.
- `randomTests`: kiểm tra thêm **700 đồ thị ngẫu nhiên** có n từ 0 đến 9; đối chiếu quyết định và tính hợp lệ của witness.

Mọi kết quả YES đều được xác nhận số đỉnh ≤k và thật sự phủ các cạnh; mọi kết quả NO ở tập test được so với oracle duyệt tập con. Mã thống kê `forced`, `edgePrunes`, `matchingPrunes` là số lần quy tắc xuất hiện trong các **nút đã duyệt** — không phải số đỉnh của nghiệm cuối, cũng không phải phép đếm thời gian CPU.

```java
import java.util.*;

public class ParameterizedVertexCoverDemo {
    record Edge(int u, int v) {}

    record Graph(int n, List<Edge> edges) {
        Graph {
            if (n < 0) throw new IllegalArgumentException("negative n");
            Objects.requireNonNull(edges, "edges");
            Set<Long> keys = new HashSet<>();
            for (Edge e : edges) {
                Objects.requireNonNull(e, "edge");
                if (e.u() < 0 || e.v() < 0 || e.u() >= n
                        || e.v() >= n || e.u() == e.v()) {
                    throw new IllegalArgumentException(
                            "expect simple undirected graph");
                }
                int a = Math.min(e.u(), e.v());
                int b = Math.max(e.u(), e.v());
                long key = ((long) a << 32) | (b & 0xffffffffL);
                if (!keys.add(key)) {
                    throw new IllegalArgumentException("duplicate edge");
                }
            }
            edges = List.copyOf(edges);
        }
    }

    static Graph graph(int n, int... endpoints) {
        if (endpoints.length % 2 != 0) {
            throw new IllegalArgumentException("odd edge endpoint count");
        }
        List<Edge> edges = new ArrayList<>();
        for (int i = 0; i < endpoints.length; i += 2) {
            edges.add(new Edge(endpoints[i], endpoints[i + 1]));
        }
        return new Graph(n, edges);
    }

    static class Stats {
        long nodes;
        long forced;
        long edgePrunes;
        long matchingPrunes;
    }

    record Result(
            boolean feasible,
            List<Integer> cover,
            long nodes,
            long forced,
            long edgePrunes,
            long matchingPrunes) {}

    // Search for a vertex cover containing at most budget vertices.
    static Result solve(Graph g, int budget) {
        Objects.requireNonNull(g, "graph");
        if (budget < 0) {
            throw new IllegalArgumentException("negative budget");
        }
        boolean[] selected = new boolean[g.n()];
        Stats stats = new Stats();
        boolean ok = dfs(g, budget, selected, stats);
        List<Integer> answer = new ArrayList<>();
        if (ok) {
            for (int v = 0; v < selected.length; v++) {
                if (selected[v]) answer.add(v);
            }
            if (answer.size() > budget || !covers(g, answer)) {
                throw new AssertionError("incorrect witness");
            }
        }
        return new Result(ok, List.copyOf(answer), stats.nodes,
                stats.forced, stats.edgePrunes, stats.matchingPrunes);
    }

    static boolean dfs(Graph g, int remaining,
                       boolean[] selected, Stats stats) {
        stats.nodes++;

        int[] degree = new int[g.n()];
        int uncovered = 0;
        Edge first = null;
        for (Edge e : g.edges()) {
            if (!selected[e.u()] && !selected[e.v()]) {
                uncovered++;
                degree[e.u()]++;
                degree[e.v()]++;
                if (first == null) first = e;
            }
        }
        if (uncovered == 0) return true;
        if (remaining == 0) return false;

        // Safe reduction: if deg(v) > remaining,
        // EVERY cover of size <= remaining must include v.
        for (int v = 0; v < degree.length; v++) {
            if (degree[v] > remaining) {
                stats.forced++;
                selected[v] = true;
                if (dfs(g, remaining - 1, selected, stats)) {
                    return true;
                }
                selected[v] = false;
                return false;
            }
        }

        // At this point, residual max degree <= remaining.
        // A cover of size <= remaining can cover <= remaining^2
        // uncovered edges. More edges means impossible.
        if ((long) uncovered > (long) remaining * remaining) {
            stats.edgePrunes++;
            return false;
        }

        // Greedy maximal matching is a valid LOWER BOUND
        // on the number of distinct cover vertices required.
        boolean[] matched = new boolean[g.n()];
        int matching = 0;
        for (Edge e : g.edges()) {
            if (selected[e.u()] || selected[e.v()]) continue;
            if (!matched[e.u()] && !matched[e.v()]) {
                matched[e.u()] = true;
                matched[e.v()] = true;
                matching++;
                if (matching > remaining) {
                    stats.matchingPrunes++;
                    return false;
                }
            }
        }

        // Branch on an uncovered edge {u,v}: any cover must
        // contain u or v. Each branch consumes one unit of k.
        int u = first.u(), v = first.v();
        selected[u] = true;
        if (dfs(g, remaining - 1, selected, stats)) return true;
        selected[u] = false;

        selected[v] = true;
        if (dfs(g, remaining - 1, selected, stats)) return true;
        selected[v] = false;
        return false;
    }

    static boolean covers(Graph g, List<Integer> cover) {
        boolean[] in = new boolean[g.n()];
        for (int v : cover) {
            if (v < 0 || v >= g.n() || in[v]) return false;
            in[v] = true;
        }
        for (Edge e : g.edges()) {
            if (!in[e.u()] && !in[e.v()]) return false;
        }
        return true;
    }

    static Optional<Result> minimumUpTo(Graph g, int maxK) {
        for (int k = 0; k <= maxK; k++) {
            Result r = solve(g, k);
            if (r.feasible()) return Optional.of(r);
        }
        return Optional.empty();
    }

    // An independent exhaustive oracle for SMALL graphs only.
    // It enumerates all 2^n subsets, not used by dfs.
    static boolean bruteFeasible(Graph g, int budget) {
        if (g.n() > 20) {
            throw new IllegalArgumentException("oracle: n > 20");
        }
        int maxMask = 1 << g.n();
        for (int mask = 0; mask < maxMask; mask++) {
            if (Integer.bitCount(mask) > budget) continue;
            boolean valid = true;
            for (Edge e : g.edges()) {
                boolean u = (mask & (1 << e.u())) != 0;
                boolean v = (mask & (1 << e.v())) != 0;
                if (!u && !v) {
                    valid = false;
                    break;
                }
            }
            if (valid) return true;
        }
        return false;
    }

    static void check(Graph g, int budget) {
        Result got = solve(g, budget);
        boolean expected = bruteFeasible(g, budget);
        if (got.feasible() != expected
                || got.feasible() && (!covers(g, got.cover())
                || got.cover().size() > budget)) {
            throw new AssertionError(
                    "mismatch: n=" + g.n() + ", k=" + budget
                    + ", edges=" + g.edges() + ", result=" + got);
        }
    }

    static int exhaustiveTests() {
        List<Edge> pairs = new ArrayList<>();
        for (int u = 0; u < 5; u++) {
            for (int v = u + 1; v < 5; v++) {
                pairs.add(new Edge(u, v));
            }
        }
        int cases = 0;
        for (int mask = 0; mask < (1 << pairs.size()); mask++) {
            List<Edge> chosenEdges = new ArrayList<>();
            for (int b = 0; b < pairs.size(); b++) {
                if ((mask & (1 << b)) != 0) {
                    chosenEdges.add(pairs.get(b));
                }
            }
            Graph g = new Graph(5, chosenEdges);
            for (int k = 0; k <= 5; k++) {
                check(g, k);
                cases++;
            }
        }
        return cases;
    }

    static int randomTests() {
        SplittableRandom random = new SplittableRandom(20261110L);
        int cases = 0;
        for (int t = 0; t < 700; t++) {
            int n = random.nextInt(10); // includes n=0
            List<Edge> edges = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    if (random.nextInt(3) == 0) {
                        edges.add(new Edge(u, v));
                    }
                }
            }
            Graph g = new Graph(n, edges);
            int k = random.nextInt(n + 1);
            check(g, k);
            cases++;
        }
        return cases;
    }

    static void show(String name, Graph g, int k) {
        Result r = solve(g, k);
        System.out.println(name + " (k=" + k + "): "
                + (r.feasible() ? "YES cover=" + r.cover() : "NO")
                + " [nodes=" + r.nodes()
                + ", forced=" + r.forced()
                + ", edgePrunes=" + r.edgePrunes()
                + ", matchingPrunes=" + r.matchingPrunes()
                + "]");
    }

    public static void main(String[] args) {
        Graph star = graph(7, 0,1, 0,2, 0,3, 0,4, 0,5, 0,6);
        Graph triangle = graph(3, 0,1, 1,2, 0,2);
        Graph cycle5 = graph(5, 0,1, 1,2, 2,3, 3,4, 4,0);
        Graph matching3 = graph(6, 0,1, 2,3, 4,5);

        show("Star", star, 1);
        show("Triangle", triangle, 1);
        show("Triangle", triangle, 2);
        show("Odd cycle C5", cycle5, 2);
        show("Odd cycle C5", cycle5, 3);
        show("Three disjoint edges", matching3, 2);
        show("Empty graph", graph(4), 0);

        Optional<Result> optimum = minimumUpTo(cycle5, 4);
        System.out.println("C5 minimum within cap 4: "
                + optimum.map(r -> r.cover().size())
                        .orElse(-1));

        int exhaustive = exhaustiveTests();
        int random = randomTests();
        System.out.println("Oracle QA: PASS ("
                + exhaustive + " exhaustive graph-budget cases, "
                + random + " random cases)");
    }
}
```

### 11.1. Biên dịch và chạy

Lưu toàn bộ mã vào `ParameterizedVertexCoverDemo.java`, sử dụng JDK 17 trở lên:

```bash
javac ParameterizedVertexCoverDemo.java
java ParameterizedVertexCoverDemo
```

**Stdout chính xác:**

```text
Star (k=1): YES cover=[0] [nodes=2, forced=1, edgePrunes=0, matchingPrunes=0]
Triangle (k=1): NO [nodes=2, forced=1, edgePrunes=0, matchingPrunes=0]
Triangle (k=2): YES cover=[0, 1] [nodes=3, forced=0, edgePrunes=0, matchingPrunes=0]
Odd cycle C5 (k=2): NO [nodes=1, forced=0, edgePrunes=1, matchingPrunes=0]
Odd cycle C5 (k=3): YES cover=[0, 1, 3] [nodes=4, forced=1, edgePrunes=0, matchingPrunes=0]
Three disjoint edges (k=2): NO [nodes=1, forced=0, edgePrunes=0, matchingPrunes=1]
Empty graph (k=0): YES cover=[] [nodes=1, forced=0, edgePrunes=0, matchingPrunes=0]
C5 minimum within cap 4: 3
Oracle QA: PASS (6144 exhaustive graph-budget cases, 700 random cases)
```

### 11.2. Giải thích kết quả kiểm thử

- **Star k=1:** Chọn tâm 0 theo quy tắc bậc lớn, chỉ 2 nút DFS, nghiệm `[0]`.
- **Triangle k=1:** Buộc chọn một đỉnh nhưng còn một cạnh và hết ngân sách, kết luận NO.
- **Triangle k=2:** Chọn `[0,1]` phủ cả ba cạnh; YES.
- **C5 k=2:** Cắt bằng `m'=5 > k²=4`, không cần phân nhánh.
- **C5 k=3:** Nghiệm `[0,1,3]`, đúng ba đỉnh.
- **Ba cạnh rời k=2:** Greedy matching tìm 3 cạnh độc lập >2, kết luận NO dù cận cạnh chưa loại.
- **Empty graph:** Không có cạnh thì tập rỗng luôn phủ toàn bộ, kể cả k=0.
- **Minimum C5:** Thử k tăng dần cho tối ưu kích thước 3 trong ngân sách tối đa 4.
- **Oracle QA:** 5 đỉnh có `C(5,2)=10` cạnh tiềm năng, nên `2^10=1024` đồ thị đơn khác nhau theo nhãn. Mỗi đồ thị được xét k từ 0 tới 5, tổng 6144 trường hợp. Bộ giải FPT được so với một oracle thực sự liệt kê mọi tập con đỉnh (khác phương pháp search cây theo cạnh). Ngoài ra 700 đồ thị ngẫu nhiên với n≤9 được đối chiếu. Mọi trường hợp YES được kiểm tra witness có không quá k đỉnh và phủ hết các cạnh.

**Lưu ý:** Số nút/thống kê của ví dụ phụ thuộc **thứ tự duyệt các cạnh và nhánh** trong mã. Nó không phải số nút tối thiểu có thể có của mọi bộ giải hay bằng chứng rằng thời gian CPU chỉ có đúng số thao tác ấy.

## 12. Kernelization: nén bài toán rồi tìm kiếm

Ý tưởng thông dụng trong FPT là **tiền xử lý an toàn** trước khi branching:

```text
Original instance (G,k)
       |
       | polynomial-time reduction rules
       v
Equivalent smaller instance (G',k')
       |
       | FPT search using k'
       v
YES/NO + reconstruct witness for original G
```

**Tương đương** nghĩa là `(G,k)` YES khi và chỉ khi `(G',k')` YES. Nếu trả nghiệm, phải lưu lựa chọn đỉnh bắt buộc để **khôi phục witness** trên G gốc.

### 12.1. Kernel Vertex Cover đơn giản

Áp dụng nhiều lần:

1. Bỏ các đỉnh cô lập (không ảnh hưởng cạnh nào).
2. Nếu có đỉnh bậc >k, **chọn bắt buộc** đỉnh ấy, bỏ các cạnh kề, giảm k đi 1.
3. Khi tất cả bậc ≤k mà còn hơn k² cạnh, trả NO.
4. Nếu không, còn ≤k² cạnh, ≤2k² đỉnh không cô lập. Đó là một kernel kích thước O(k²).

Trong mã demo, các cạnh và đồ thị gốc được giữ nguyên để đơn giản hóa backtrack, nhưng việc xác định **cạnh chưa phủ** tại mỗi nút mô phỏng phần dư; quy tắc bắt buộc và cận m' được kiểm tra ở từng nút. Mã **chưa xuất một kernel vật lý độc lập**; không nên mô tả nó như một routine biến đổi đồ thị trả về `G'`.

### 12.2. Kernel size khác search-tree size

- `O(k²)` là **số đỉnh/cạnh trong instance đã rút gọn** (trong lập luận trên).
- `O(2^k)` là **số nút của cây quyết định** trong thuật toán branching đơn giản.
- `O(2^k*(n+m))` là cận **thời gian** cho mã quét toàn bộ cạnh ở mỗi nút.

Cả hai kỹ thuật có thể kết hợp, nhưng là **hai loại giảm độ phức tạp khác nhau**: kernel giảm **kích thước instance** còn branching giới hạn **số quyết định**. Cả hai đều phải bảo toàn tính đúng.

### 12.3. Có thể làm tốt hơn không?

Có. Trong nghiên cứu tham số hóa, Vertex Cover có những thuật toán branching và kernel tốt hơn cận đơn giản vừa trình bày. Tuy nhiên, mục tiêu học tập ở đây là phân biệt **khi nào cắt tỉa chắc chắn an toàn**, chứng minh FPT bằng `2^k`, và thiết kế một bộ giải có witness chính xác.

**Đừng tự suy một cận tốt hơn** chỉ vì chạy test nhanh trên vài mẫu: một cải tiến độ phức tạp cần lập luận toán học bao phủ cả trường hợp xấu nhất.

## 13. Chọn tham số nào là hợp lý?

Không phải bài toán nào cũng thuận lợi với tham số “kích thước nghiệm”:

- **Vertex Cover parameter k:** FPT vì có nhánh hai đầu mút và kernel.
- **Một số bài đồ thị với tham số treewidth w:** Có thể dùng dynamic programming trên phân rã cây, với thời gian dạng `f(w)*poly(n)` khi phân rã phù hợp được cung cấp hoặc tính được. Khả thi hay không còn phụ thuộc bài toán cụ thể và chi phí tìm phân rã.
- **Một số bài toán khác:** Khi chỉ tham số hóa theo kích thước nghiệm, có thể gặp độ khó như `W[1]`-hard; không được khẳng định FPT chỉ dựa vào việc k được gọi là tham số.

Câu hỏi quan trọng:

1. k có ý nghĩa thực tế không (số thao tác cho phép, số đỉnh được chọn, số ngoại lệ, chiều rộng cấu trúc...)?
2. Trong dữ liệu thật, k thường nhỏ đến mức nào?
3. Có thể tìm **quy tắc loại/bắt buộc** và **cận dưới** chỉ theo k không?
4. Cây tìm kiếm có giảm k ở mỗi bước và số nhánh chỉ phụ thuộc k không?
5. Có kernel nhỏ hoặc dynamic programming theo tham số không?
6. Có cần nghiệm chính xác hay chỉ gần tối ưu?
7. Hệ thống có chấp nhận thời gian tăng theo `2^k` khi k lớn không?

Tham số hóa hiệu quả nhất khi ta chọn **tham số thể hiện điểm khó thực sự** và chứng minh được một `f(k)` khả thi.

## 14. Thời gian tìm tối ưu và giới hạn tìm kiếm theo k

### 14.1. Tìm cover nhỏ nhất đến giới hạn K

Hàm `minimumUpTo(G,K)` thử:

```text
k=0,1,2,...,K.
```

Mỗi lần dùng bộ giải đúng. Nếu k đầu tiên cho YES thì đó là kích thước nghiệm nhỏ nhất, vì các k nhỏ hơn đã được chứng minh NO. Nếu tất cả k≤K đều NO, kết luận chính xác là **không tồn tại cover kích thước ≤K**, không phải “đồ thị không có vertex cover”: chọn mọi đỉnh luôn tạo một cover, chỉ có thể vượt K.

Tổng số nút, với cận đơn giản `O(2^k)` mỗi lượt:

```text
SUM_{k=0..K} O(2^k)
   = O(2^K).
```

Nếu quét lại toàn graph ở mỗi nút, cận tổng thể:

```text
O(2^K*(n+m)).
```

Bỏ qua các hệ số nhỏ; đây vẫn FPT theo K. Nếu chạy tìm tối ưu đến K=n, cận trở thành exponential theo n; **FPT theo k không hứa thuật toán đa thức cho k lớn bằng n**.

### 14.2. Có thể dùng tìm kiếm nhị phân theo k không?

Tính khả thi “có cover ≤k” là đơn điệu tăng theo k, nên **về mặt logic** có thể tìm ngưỡng bằng binary search nếu đã biết khoảng giới hạn. Tuy nhiên, mỗi lời gọi solver với k lớn có thể đắt hơn nhiều so với k nhỏ. **Ít lần gọi hơn không chắc tổng thời gian tốt hơn**.

Iterative deepening có ưu điểm dễ sinh nghiệm tối ưu ở k đầu tiên và tổng cận `O(2^K)` với search tree nhị phân. Chọn chiến lược phải xét **chi phí của từng lần gọi**, không chỉ số lần kiểm tra khả thi.

### 14.3. Không đánh đồng “giới hạn tìm kiếm” với cutoff bất kỳ

Giới hạn tìm kiếm bằng **tham số k** là một **giới hạn chứng minh được**: mỗi nhánh tiêu tốn ít nhất một đơn vị ngân sách k, nên độ sâu ≤k. Dừng sau một số bước tùy ý vì hết thời gian là **cutoff thực nghiệm**; nếu chưa duyệt đủ các nhánh, không được kết luận NO chính xác.

## 15. Các lỗi thường gặp

1. Gọi bất kỳ thuật toán có tham số k nào cũng là FPT.
2. Cho rằng `O(n^k)` là FPT vì k có thể cố định.
3. Không phân biệt FPT với XP và không kiểm tra số mũ của n.
4. Coi FPT nghĩa là đa thức đồng thời theo n và k.
5. Quên rằng `2^k` hoặc `k!` vẫn rất lớn khi k lớn.
6. Chọn tham số không liên quan đến phần khó của bài toán.
7. Chứng minh trường hợp k=3 nhanh rồi kết luận trường hợp mọi k đều nhanh.
8. Nhầm thuật toán chính xác tham số hóa với approximation.
9. Dừng khi timeout rồi trả NO thay vì UNKNOWN.
10. Chỉ trả YES mà không kiểm tra witness khi bài yêu cầu nghiệm cụ thể.
11. Quên backtrack một đỉnh đã chọn ở nhánh thất bại.
12. Giữ các đỉnh của nhiều nhánh thất bại trong cover cuối.
13. Chọn cả hai đầu mút mỗi cạnh mà không trừ ngân sách đúng.
14. Phân nhánh trên cạnh **đã được phủ**, tạo quyết định vô ích và có thể trùng trạng thái.
15. Giữ nguyên k khi đệ quy và tuyên bố độ sâu được chặn bởi k.
16. Không xử lý cơ sở E' rỗng trước khi kết luận r=0 là NO.
17. Coi đồ thị không cạnh với k=0 là NO.
18. Dùng luật bậc >k trên **bậc gốc** thay vì bậc của các cạnh chưa phủ trong trạng thái đã chọn đỉnh.
19. Áp luật bậc >k cho multigraph có cạnh song song mà không chuẩn hóa.
20. Không tách xử lý self-loop khi input cho phép nó.
21. Áp cận `m'>k²` trước khi bảo đảm max degree≤k.
22. Dùng số cạnh gốc m thay vì số cạnh phần dư m' cho cận.
23. Nhân `k*k` bằng int khi k lớn dẫn tới tràn; nên ép long trước.
24. Coi greedy maximal matching là maximum matching.
25. Kết luận YES chỉ vì matching size≤k; matching chỉ cho cận dưới.
26. Cắt nhánh dựa trên cận dưới không được chứng minh.
27. Nghĩ kernel nhỏ tự động cho đáp án, không cần tìm kiếm tiếp.
28. Bỏ các đỉnh bắt buộc khi khôi phục witness từ kernel.
29. Nhầm O(k²) kích thước kernel với O(k²) thời gian giải.
30. Tự ghi `O(2^k*k²)` mà quên chi phí đọc/xử lý graph ban đầu.
31. Báo memory O(n) dù mỗi mức recursion giữ mảng n phần tử.
32. Dùng mọi tập con k đỉnh rồi khẳng định số nhánh ≤2^k.
33. Dùng kết quả chạy nhanh trên sample làm chứng minh worst-case/FPT.
34. Không thử input k=0, đồ thị rỗng, đỉnh cô lập, star, triangle, C5, matching.
35. Không so với oracle brute force trên đồ thị nhỏ.
36. Cho rằng NO ở giới hạn K có nghĩa không tồn tại vertex cover với mọi kích thước.
37. Cho rằng ít lần gọi binary search trên k luôn nhanh hơn iterative deepening.
38. Bỏ chi phí vật lý stack/JVM khi k rất lớn.
39. Tuyên bố mọi bài toán NP-hard đều FPT với kích thước nghiệm làm tham số.
40. Không mô tả phạm vi đầu vào: đồ thị đơn, không self-loop, không cạnh trùng.

## 16. Bài tập tự luyện có đáp án

**Bài 1.** Thuật toán `O(2^k*n²)` có dạng FPT theo k không?

**Đáp án:** Có, vì số mũ của n là 2 độc lập k.

**Bài 2.** Thuật toán `O(n^k)` có được coi là chứng minh FPT không?

**Đáp án:** Không; đó là dạng XP, vì số mũ n phụ thuộc k.

**Bài 3.** Thuật toán `O(k!*n³)` có dạng FPT không?

**Đáp án:** Có, f(k)=k! và c=3. Nhưng có thể rất chậm nếu k lớn.

**Bài 4.** Cho graph hình sao 1001 đỉnh, tâm nối 1000 lá. Vertex Cover tối ưu bao nhiêu?

**Đáp án:** 1, chọn tâm.

**Bài 5.** Tam giác có cover kích thước 1 không?

**Đáp án:** Không; cần ít nhất 2 đỉnh.

**Bài 6.** Tam giác k=2, một nghiệm?

**Đáp án:** Bất kỳ hai đỉnh, ví dụ `{0,1}`.

**Bài 7.** Graph rỗng cạnh và k=0 có YES không?

**Đáp án:** Có, tập rỗng phủ tất cả cạnh vì không có cạnh nào cần phủ.

**Bài 8.** Vì sao có thể nhánh hai đầu mút của một cạnh chưa phủ?

**Đáp án:** Mọi vertex cover phải chứa ít nhất một endpoint của cạnh đó.

**Bài 9.** Độ sâu cây nhánh ≤k nhờ điều kiện gì?

**Đáp án:** Mỗi lần đệ quy phải chọn ít nhất một đỉnh mới và giảm ngân sách còn lại 1.

**Bài 10.** Cây nhánh nhị phân độ sâu k có bao nhiêu nút tối đa?

**Đáp án:** `2^(k+1)-1`, tức O(2^k).

**Bài 11.** Nếu mỗi nút duyệt O(n+m) và có O(2^k) nút, thời gian?

**Đáp án:** `O(2^k*(n+m))`.

**Bài 12.** Vì sao đỉnh phần dư bậc >r phải được chọn?

**Đáp án:** Nếu không chọn nó, cần hơn r láng giềng khác nhau để phủ từng cạnh kề, vượt ngân sách r.

**Bài 13.** Đồ thị sao có 6 cạnh, k=1, có thể áp `m>k²` để NO ngay không?

**Đáp án:** Không; đỉnh tâm bậc6>k phải được giảm bắt buộc trước. Sau đó E' rỗng, YES.

**Bài 14.** Khi mọi đỉnh còn lại bậc ≤r, tại sao `m'>r²` cho NO?

**Đáp án:** r đỉnh phủ tối đa r*r cạnh phần dư; nếu có nhiều hơn, không đủ.

**Bài 15.** C5 có 5 cạnh, max degree2, k=2. Kết luận?

**Đáp án:** NO vì 5>2²=4.

**Bài 16.** Một graph có m'=8, r=3 và max degree≤3. Cận cạnh có loại ngay không?

**Đáp án:** Không; 8≤9, cần thêm matching hoặc tìm kiếm. Không được kết luận YES.

**Bài 17.** Matching gồm 4 cạnh rời đỉnh, r=3. Kết luận?

**Đáp án:** NO, mọi vertex cover cần ít nhất 4 đỉnh.

**Bài 18.** Greedy matching size=2 và r=3. Có chắc YES không?

**Đáp án:** Không, matching size chỉ là cận dưới.

**Bài 19.** “Maximal matching” và “maximum matching” có giống nhau không?

**Đáp án:** Không; maximal là không thêm cạnh được, maximum là nhiều cạnh nhất có thể.

**Bài 20.** Kernel đơn giản sau reduction có tối đa bao nhiêu cạnh?

**Đáp án:** `r²`, nếu không đã trả NO.

**Bài 21.** Kernel có tối đa bao nhiêu đỉnh **không cô lập** theo cận trên?

**Đáp án:** `2r²`, vì mỗi cạnh có hai endpoint.

**Bài 22.** Mã có áp dụng kiểm tra kernel edge bound nhưng không xuất graph kernel riêng không?

**Đáp án:** Có; nó tính cạnh chưa phủ và kiểm tra m'>r² ngay trong DFS, không tạo G' vật lý.

**Bài 23.** Khi tìm nghiệm tối ưu bằng k=0,1,...,K, nếu k=3 là lần đầu YES thì tối ưu bằng bao nhiêu?

**Đáp án:** 3, vì k=0,1,2 đã được chứng minh NO.

**Bài 24.** Nếu mọi k≤K đều NO, có thể nói graph không có vertex cover không?

**Đáp án:** Không; chỉ không có cover kích thước ≤K. Chọn tất cả đỉnh luôn là một cover.

**Bài 25.** Vì sao `k*k` cần ép long trong Java?

**Đáp án:** Vì nhân int có thể overflow; dùng `(long)k*k` để so cận chính xác trong miền int của k.

**Bài 26.** Nếu input có cạnh song song, quy tắc degree>r còn tự đúng không?

**Đáp án:** Không nếu degree đếm các cạnh lặp là nhiều láng giềng; cần đơn giản hóa đồ thị hoặc đếm distinct neighbors.

**Bài 27.** Khi branch chọn u thất bại, phải làm gì trước khi thử v?

**Đáp án:** Backtrack, bỏ đánh dấu chọn u để nhánh v bắt đầu từ trạng thái cha chính xác.

**Bài 28.** Có 2^10 đồ thị đơn gắn nhãn trên 5 đỉnh; tại sao?

**Đáp án:** Có C(5,2)=10 cạnh tiềm năng, mỗi cạnh hiện diện hoặc vắng mặt, nên 2^10=1024.

**Bài 29.** Kiểm thử 1024 đồ thị với k=0..5 là bao nhiêu cặp?

**Đáp án:** 1024*6=6144.

**Bài 30.** Nếu tham số k tăng đến n, FPT có bảo đảm nhanh như đa thức n không?

**Đáp án:** Không; `2^k` có thể là `2^n`, tăng theo hàm mũ của n.

## 17. Checklist trước khi thiết kế thuật toán tham số hóa

- [ ] Đã định nghĩa đúng bài toán quyết định `(x,k)` và nghiệm nào được tính hợp lệ?
- [ ] k có ý nghĩa thực tế và thường đủ nhỏ để `f(k)` khả thi?
- [ ] Đã phân biệt FPT `f(k)*n^c` với XP `n^{f(k)}`?
- [ ] Khi branching, mọi nghiệm phải nằm trong ít nhất một nhánh?
- [ ] Mỗi nhánh có giảm tham số hoặc một đại lượng bảo đảm kết thúc?
- [ ] Quy tắc bắt buộc chọn đỉnh có chứng minh đúng và phù hợp loại đồ thị?
- [ ] Cận `m'>r²` chỉ được dùng khi max residual degree≤r?
- [ ] Matching greedy chỉ được dùng làm **lower bound**, không phải xác nhận YES?
- [ ] Các nhánh thất bại có được rollback trạng thái selected?
- [ ] Khi YES có witness cụ thể, kích thước≤k và phủ hết các cạnh?
- [ ] Khi NO có bằng chứng từ duyệt đầy đủ/cận an toàn, không phải chỉ timeout?
- [ ] Nếu áp kernelization, có cơ chế khôi phục nghiệm của bài toán gốc?
- [ ] Đã phân tích thời gian **và bộ nhớ cài đặt**, kể cả các mảng giữ trên đệ quy?
- [ ] Đã thử graph rỗng, đỉnh cô lập, star, triangle, C5, matching rời?
- [ ] Đã đối chiếu bộ giải với oracle vét cạn trên graph nhỏ?
- [ ] Đã nêu giới hạn input (simple graph, no self-loop, k≥0) rõ ràng?

## Kết luận

**Thuật toán tham số hóa** cho phép tách độ khó của một bài toán thành **tham số k** và kích thước đầu vào. Mục tiêu FPT là:

```text
T(n,k) = f(k)*poly(n).
```

Trong **Vertex Cover tham số k**, từ một cạnh chưa phủ ta buộc phải chọn một trong hai đầu mút. Quy tắc đó tạo cây nhị phân độ sâu ≤k, dẫn tới cận đơn giản:

```text
O(2^k*(n+m)).
```

Các quy tắc bậc đỉnh >r, giới hạn `m'≤r²`, matching lower bound và kernelization giúp thu hẹp phần cần tìm kiếm **mà không hy sinh tính đúng**. Chỉ cần nhớ: **giảm kích thước instance** khác **cắt nhánh có chứng minh**, `n^k` khác `2^k*n^c`, và thuật toán chính xác khác heuristic dừng vì hết thời gian.

Khi mỗi quy tắc đều có chứng minh an toàn, mỗi nhánh tiêu tốn ngân sách, và nghiệm được kiểm chứng, ta có một lời giải tham số hóa **đúng về mặt toán học**, có khả năng giải chính xác nhiều trường hợp kích thước n lớn nhưng k nhỏ.
