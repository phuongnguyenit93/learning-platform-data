# Đường tăng và điều kiện cải thiện ghép cặp

## 1. Từ bài toán ghép cặp đến câu hỏi “có thể ghép thêm không?”

Cho một đồ thị vô hướng G=(V,E). Một **ghép cặp (matching)** M là tập các cạnh sao cho **không có hai cạnh được chọn nào chung đỉnh**. Mỗi đỉnh thuộc đúng một cạnh M được gọi là **đỉnh đã ghép (matched)**; đỉnh chưa thuộc cạnh nào trong M được gọi là **đỉnh tự do (free, unmatched hoặc exposed)**.

Bài toán **ghép cặp tối đa (maximum-cardinality matching)** yêu cầu chọn M có **số cạnh lớn nhất**. Đây là một trong những mô hình cơ sở của **ghép cặp và phân công**: ghép sinh viên với vị trí thực tập, người làm với ca trực, yêu cầu với tài nguyên hoặc các cặp tương thích giữa hai nhóm.

Với **đồ thị hai phía (bipartite graph)**, V được chia thành hai tập không giao nhau L và R; mọi cạnh nối một đỉnh thuộc L với một đỉnh thuộc R. Ví dụ:

~~~text
L = {L0, L1, L2}
R = {R0, R1}

Các cạnh cho phép:
L0 -- R0
L1 -- R0
L2 -- R1
~~~

Một ghép cặp hợp lệ là:

~~~text
M = {(L0,R0), (L2,R1)}
|M| = 2
~~~

Đỉnh L1 còn tự do; tuy nhiên không thể ghép thêm L1 vì nó chỉ nối với R0, mà R0 đang ghép với L0. Số cạnh tối đa là 2 vì phía R chỉ có 2 đỉnh.

**Câu hỏi trọng tâm của bài học:** đang có một ghép cặp M hợp lệ, làm thế nào biết liệu có thể tăng số cạnh được chọn từ |M| lên |M|+1 mà vẫn giữ ràng buộc mỗi đỉnh xuất hiện nhiều nhất một lần?

Câu trả lời là **đường tăng (augmenting path)**. Đây là ý tưởng cốt lõi của các thuật toán tìm maximum matching, định lý Berge và các thuật toán DFS/BFS trên đồ thị hai phía.

### Ba khái niệm cần tách biệt

- **Matching hợp lệ:** không hai cạnh M chung đỉnh; chưa nói tối ưu.
- **Matching cực đại theo phép thêm (maximal matching):** không thể thêm **một cạnh riêng lẻ** vào M mà vẫn hợp lệ.
- **Matching có kích thước tối đa (maximum matching):** không tồn tại matching nào có nhiều cạnh hơn M.

Mọi maximum matching đều là maximal, nhưng một maximal matching **có thể không maximum**. Đường tăng là công cụ phát hiện sự khác biệt.

## 2. Đường xen kẽ và đường tăng

Cho một matching M hiện tại. Một **đường xen kẽ (alternating path)** là một đường đơn có các cạnh **luân phiên thuộc M và không thuộc M**.

Ví dụ:

~~~text
L1 -- R0 -- L0 -- R1

Trang thai canh theo thu tu:
L1--R0 : khong thuoc M
R0--L0 : thuoc M
L0--R1 : khong thuoc M
~~~

Cấu trúc trên là alternating path vì các cạnh luân phiên:

~~~text
unmatched, matched, unmatched
~~~

Một **đường tăng đối với M (M-augmenting path)** là alternating path có **hai đầu đều là đỉnh free**. Trong đồ thị hai phía, nếu đi từ một đỉnh free thuộc L thì đường kết thúc tại một đỉnh free thuộc R.

Một đường tăng có dạng:

~~~text
Free-L -- unmatched -- R -- matched -- L
       -- unmatched -- R -- ... -- Free-R
~~~

Nó bắt đầu bằng cạnh **chưa ghép** và kết thúc bằng cạnh **chưa ghép**, nên có **số cạnh lẻ**.

### Vì sao hai đầu phải free?

Nếu đầu đường đang matched và ta tùy ý đảo trạng thái tất cả các cạnh trên đường, đỉnh đầu hoặc cuối có thể mất cạnh ghép thay vì tăng số cạnh. Tính chất “hai đầu đều free” bảo đảm sau khi đảo cạnh:

- Mỗi đỉnh **bên trong đường** vẫn có đúng một cạnh thuộc matching mới.
- Hai đỉnh **đầu mút** từ free trở thành matched.
- Không đỉnh nào có hai cạnh thuộc matching mới.
- Tổng số cạnh matching **tăng đúng 1**.

Một alternating path không có hai đầu free **không nhất thiết** là đường tăng. Đừng kết luận một matching cải thiện chỉ vì nhìn thấy dãy cạnh luân phiên.

### Đường có thể dài hơn một cạnh

Một cạnh nối trực tiếp hai đỉnh free chính là đường tăng dài 1 cạnh, nhưng đây chỉ là trường hợp đơn giản nhất. Một matching **maximal** có thể không có cạnh free–free nào, trong khi vẫn tồn tại đường tăng dài 3, 5, 7,... cạnh.

Đây là lý do chiến lược “cứ thêm cạnh nối hai đỉnh còn rảnh” không bảo đảm tìm matching maximum.

## 3. Phép đảo cạnh (flip) làm matching tăng đúng một đơn vị

Cho M là matching và P là một augmenting path theo M. Ta xây matching mới bằng cách **bỏ các cạnh trên P đang thuộc M và thêm các cạnh trên P chưa thuộc M**.

Phép này được viết bằng **hiệu đối xứng (symmetric difference)**:

~~~text
M' = M △ E(P)
   = (M \ E(P)) union (E(P) \ M)
~~~

Nghĩa là với mỗi cạnh của P:

- Cạnh đang thuộc M → bỏ khỏi M.
- Cạnh đang không thuộc M → thêm vào M.
- Cạnh không thuộc P → giữ nguyên trạng thái.

Giả sử P có 2k+1 cạnh, trong đó k cạnh đã ghép và k+1 cạnh chưa ghép:

~~~text
Truoc flip:
    k matched edges on P
    k+1 unmatched edges on P

Sau flip:
    k+1 matched edges on P
    k unmatched edges on P

|M'| = |M| - k + (k+1) = |M| + 1
~~~

**Điểm dễ nhầm:** ta không “thêm toàn bộ đường tăng” vào matching cũ. Làm vậy sẽ khiến các đỉnh bên trong đường nằm trên hai cạnh M, vi phạm định nghĩa matching. Phải **đảo** trạng thái đã ghép/chưa ghép dọc đường.

### Chứng minh M' vẫn là matching

Ở đỉnh bên trong P, đường P đi vào và đi ra bằng hai cạnh, một cạnh matched và một cạnh unmatched. Sau flip, nó mất cạnh matched cũ và nhận cạnh unmatched kia: vẫn chỉ có một cạnh ghép.

Hai đầu P free ban đầu, nên chưa tham gia bất kỳ cạnh matching nào; sau flip mỗi đầu nhận đúng một cạnh. Những đỉnh ngoài P không đổi.

Vì P là đường đơn, không đỉnh nào bị xử lý hai lần bên trong. Do đó M' hợp lệ và tăng kích thước đúng 1.

### Tại sao “cải thiện” ở đây là tăng số cạnh?

Bài đang xét **maximum-cardinality matching**, nghĩa là mục tiêu tăng **số cặp**. Nếu mỗi cặp có chi phí/trọng số riêng và mục tiêu là tối ưu tổng chi phí, khái niệm “cải thiện” có thêm điều kiện về **cost**; chỉ tăng số cạnh không đảm bảo tối ưu trọng số. Phần 17 phân biệt các bài toán đó.

## 4. Ví dụ: matching đã cực đại nhưng chưa tối đa

Xét hai phía:

~~~text
L = {L0, L1}
R = {R0, R1}

Canh:
L0--R0
L0--R1
L1--R0
~~~

Giả sử ban đầu ta tham lam chọn:

~~~text
M = {(L0,R0)}
~~~

Khi đó L1 và R1 đều free. Nhưng **không có cạnh trực tiếp L1–R1**, nên không thể đơn giản thêm một cạnh nối hai đỉnh free. Matching có kích thước 1 là **maximal**: từng cạnh chưa chọn đều chạm một đỉnh đã ghép.

Tuy nhiên tồn tại đường tăng:

~~~text
L1 -- R0 -- L0 -- R1
  U      M      U

U = unmatched
M = matched
~~~

Hai đầu L1 và R1 free. Khi flip:

~~~text
Bo:     (L0,R0)
Them:   (L1,R0), (L0,R1)
~~~

Matching mới:

~~~text
M' = {(L0,R1), (L1,R0)}
|M'| = 2
~~~

Vì cả hai phía đều có hai đỉnh, không matching nào có hơn 2 cạnh. Do đó M' **maximum**, đồng thời cũng là **perfect matching** trên đồ thị này.

**Bài học quan trọng:** đường tăng cho phép **phân công lại** một người/tài nguyên đã ghép, không chỉ tìm cặp mới giữa hai người/tài nguyên còn trống. Mục tiêu là tăng tổng số cặp, kể cả phải thay đổi các cặp đã chọn.

### Diễn giải như bài phân công

Ban đầu người L0 nhận công việc R0, còn người L1 chưa có việc; R1 đang trống. L1 chỉ làm được R0; L0 có thể làm R0 hoặc R1. Phân công tối ưu là **chuyển L0 sang R1** và giao R0 cho L1. Đường tăng chính là chuỗi thay đổi phân công hợp lệ.

## 5. Định lý Berge: không còn đường tăng ⇔ matching maximum

**Định lý Berge (Berge's lemma):** một matching M của đồ thị vô hướng là **matching có kích thước tối đa** khi và chỉ khi **không tồn tại đường tăng** đối với M.

Định lý này đúng cho **đồ thị vô hướng tổng quát**, không chỉ đồ thị hai phía. Tuy nhiên cách **tìm** đường tăng trong đồ thị tổng quát khó hơn vì có chu trình lẻ; thuật toán BFS hai phía ở bài này chỉ áp dụng cho bipartite graph.

### Chiều thứ nhất: có đường tăng ⇒ chưa tối đa

Nếu tồn tại đường tăng P, phép flip dọc P tạo M' hợp lệ với |M'|=|M|+1. Như vậy M chưa thể là maximum.

Chiều này là hệ quả trực tiếp của định nghĩa và phép đảo cạnh ở phần 3.

### Chiều thứ hai: chưa tối đa ⇒ có đường tăng

Giả sử M **không maximum**. Khi đó tồn tại một matching M* với |M*|>|M|.

Xét đồ thị chỉ chứa các cạnh thuộc **hiệu đối xứng M △ M***. Trong đồ thị ấy, mỗi đỉnh có bậc không quá 2 vì:

- M là matching: mỗi đỉnh thuộc nhiều nhất một cạnh M.
- M* cũng là matching: mỗi đỉnh thuộc nhiều nhất một cạnh M*.

Các thành phần liên thông của hiệu đối xứng vì vậy chỉ có thể là **đường đi** hoặc **chu trình** có các cạnh luân phiên M, M*; chu trình luân phiên phải có độ dài chẵn.

Trong một chu trình luân phiên, số cạnh M và M* bằng nhau. Trong một đường luân phiên, số cạnh M* và M có thể bằng nhau hoặc chênh lệch 1.

Vì tổng số cạnh M* lớn hơn tổng số cạnh M, ít nhất một thành phần phải là **đường có nhiều hơn 1 cạnh M* so với M**. Đường này bắt đầu và kết thúc bằng cạnh M*, trong khi không đầu mút nào được ghép bởi M (nếu có thì M-cạnh sẽ xuất hiện ở thành phần đó). Do vậy đây là **đường tăng theo M**.

Mâu thuẫn với giả sử “không có đường tăng”. Suy ra nếu không tồn tại đường tăng thì M là maximum.

### Ý nghĩa thuật toán

Ta có một cơ chế **cải thiện lặp** và một **tiêu chuẩn dừng đủ mạnh**:

~~~text
while exists M-augmenting path:
    M = M △ pathEdges

At termination:
    no augmenting path
    => M is maximum by Berge's lemma
~~~

Cần phân biệt **chứng minh rằng một matching tối đa** với **cách tìm đường tăng hiệu quả**. Trên đồ thị hai phía, việc tìm đường tăng có thể làm bằng BFS/DFS đơn giản; trên graph tổng quát, phải xử lý blossom.

## 6. Hướng đi xen kẽ trong đồ thị hai phía

Cho một bipartite graph G=(L∪R,E) và matching M. Để tìm đường tăng từ một đỉnh L còn free:

- Từ **L sang R**, chỉ đi theo cạnh **chưa thuộc M**.
- Từ **R sang L**, chỉ đi theo **cạnh đang thuộc M** của R (nếu có).
- Khi đi tới một R **free**, ta vừa tìm được điểm kết thúc của đường tăng.

Có thể tưởng tượng tạo một **đồ thị có hướng phụ thuộc M**:

~~~text
Unmatched edge L--R :  L -> R
Matched edge   L--R :  R -> L
~~~

Một đường từ L free tới R free trong đồ thị hướng này chính là một **đường tăng** theo matching hiện tại.

### Vì sao không đi L→R qua cạnh đã matched?

Nếu đi từ L qua chính cạnh matching của L rồi tiếp tục từ R về L theo cạnh matched, ta có thể quay lại vị trí cũ và không tuân theo quy tắc xen kẽ cần thiết.

Trong BFS cài bằng **chỉ queue các đỉnh L**, mỗi bước mở rộng tương đương:

~~~text
L (dang duyet)
    -- unmatched --> R

Neu R matched voi L':
    R -- matched --> L'
    enqueue L' neu chua tham
Neu R free:
    tim thay augmenting path
~~~

Như vậy một vòng xử lý từ L có thể đi qua **hai cạnh xen kẽ** để tới L mới. Đây vẫn là BFS theo **số cạnh đường tăng**, vì mỗi lần chuyển từ một L sang L khác đi qua đúng hai cạnh.

### BFS đa nguồn từ tất cả L free

Có thể khởi tạo queue bằng **mọi đỉnh free thuộc L**, thay vì lần lượt chạy BFS từ từng L free. Khi đó BFS tìm một đường tăng từ **bất kỳ** nguồn free ở L đến một đích free ở R.

Trong mỗi lần BFS:

- Mỗi L được enqueue tối đa một lần.
- Mỗi R được đánh dấu tối đa một lần.
- Ta lưu đủ predecessor để dựng đúng dãy cạnh xen kẽ.
- Khi tìm được một R free, dừng tìm và flip **một** đường tăng.
- Sau khi flip, chạy BFS mới vì matching và hướng các cạnh đã thay đổi.

BFS này **không phải toàn bộ thuật toán Hopcroft–Karp**. Hopcroft–Karp tìm nhiều đường tăng ngắn nhất đôi một không giao đỉnh trong mỗi pha để giảm số pha; bài này tập trung tìm và flip **một đường** mỗi lượt.

## 7. Lưu predecessor để dựng lại đường tăng

Để tăng matching thật sự, chỉ tìm thấy R free là chưa đủ. Phải biết đường đi **theo đúng cạnh nào** và flip chính xác.

Với cấu trúc:

~~~text
matchLeft[l] = r neu L_l dang ghep voi R_r, nguoc lai -1
matchRight[r] = l neu R_r dang ghep voi L_l, nguoc lai -1
~~~

Ta lưu thêm trong một lượt BFS:

~~~text
parentRight[r] = l
    // tu L_l di qua canh unmatched den R_r

viaRight[l] = r
    // neu L_l duoc tham tu matched edge R_r -> L_l
    // neu L_l la root free, viaRight[l] = -1
~~~

Khi tìm thấy R free cuối đường, ta truy ngược:

~~~text
right = freeRight

while right != -1:
    left = parentRight[right]
    previousRight = viaRight[left]

    matchLeft[left] = right
    matchRight[right] = left

    right = previousRight
~~~

Những lần gán trên tương đương việc flip dọc đường tăng. Ta cập nhật theo từng cặp mới từ **phía đích về đầu**, và biến previousRight được lấy từ predecessor của BFS đã dựng trước đó, không lấy từ mảng matchLeft vừa bị thay đổi.

### Ví dụ truy vết

Với đường L1→R0→L0→R1:

~~~text
parentRight[R1] = L0
viaRight[L0]    = R0

parentRight[R0] = L1
viaRight[L1]    = -1  (root free)
~~~

Bắt đầu right=R1:

1. Gán L0↔R1, chuyển right=R0.
2. Gán L1↔R0, chuyển right=-1.
3. Dừng. Matching bây giờ có hai cạnh và không đỉnh nào trùng.

**Không được chỉ lưu một đỉnh cha chung chung** rồi tùy ý chọn cạnh nếu có nhiều cạnh song song trong một graph không nhãn cạnh. Ở bài **matching không trọng số trên bipartite graph**, một cặp endpoints xác định **quan hệ ghép** và không cần lưu edge id nếu các cạnh trùng endpoints được xem tương đương. Nhưng nếu mỗi cạnh có identity, nhãn hoặc trọng số riêng, cần lưu đúng edge id trong predecessor/luồng.

## 8. Thuật toán tìm matching maximum bằng BFS lặp

Mô hình cụ thể:

~~~text
Input:
    nLeft, nRight >= 0
    edges = list (left,right)
    0 <= left < nLeft
    0 <= right < nRight

Output:
    matching maximum cardinality
    matchLeft, matchRight
~~~

Bắt đầu bằng matching rỗng, matchLeft và matchRight toàn -1.

~~~text
maximumMatching():
    M = empty matching

    while true:
        P = findAugmentingPathByBFS(M)

        if P does not exist:
            break

        flip all edges of P
        |M|++

    return M
~~~

Trong một lần findAugmentingPathByBFS:

~~~text
queue = all free left vertices
seenLeft, seenRight = false
mark and enqueue all free L

while queue not empty:
    l = queue.removeFirst()

    for r adjacent to l:
        if edge (l,r) is matched:
            continue
        if seenRight[r]:
            continue

        seenRight[r] = true
        parentRight[r] = l

        if matchRight[r] == -1:
            return augmenting path ending at r

        nextLeft = matchRight[r]
        if not seenLeft[nextLeft]:
            seenLeft[nextLeft] = true
            viaRight[nextLeft] = r
            queue.addLast(nextLeft)

return NOT_FOUND
~~~

Lặp BFS từ đầu sau mỗi lần flip vì **trạng thái cạnh matched/unmatched đã đổi**.

### Tiêu chuẩn dừng

Nếu BFS bắt đầu từ **tất cả L free** mà không tìm được R free nào qua các bước xen kẽ, không tồn tại đường tăng từ phía L sang R. Vì mọi đường tăng trong bipartite graph phải có hai đầu free khác phía, **không còn đường tăng nào**. Theo định lý Berge, matching hiện tại là **maximum**.

Đây là điều kiện dừng mạnh hơn “không thấy cạnh nối trực tiếp hai đỉnh free”. Chỉ kiểm cạnh trực tiếp có thể bỏ sót đường tăng dài 3,5,... cạnh.

### Số lần cải thiện tối đa

Mỗi lần flip tăng |M| đúng 1, và |M|≤min(nLeft,nRight). Vì bắt đầu từ matching rỗng, có nhiều nhất **min(nLeft,nRight)** lượt tăng thành công. Sau đó cần thêm một lần BFS không tìm thấy đường tăng để xác nhận tối ưu, trừ khi đã có chứng chỉ khác như matching ghép hết một phía.

## 9. Khi không cải thiện được: ví dụ Hall

Xét:

~~~text
L = {L0,L1,L2}
R = {R0,R1}

Edges:
L0--R0
L1--R0
L2--R1
~~~

BFS và flip có thể thu được:

~~~text
M = {(L0,R0), (L2,R1)}
|M|=2
~~~

L1 còn free. Đường xen kẽ bắt đầu từ L1:

~~~text
L1 --unmatched--> R0 --matched--> L0
~~~

Từ L0 không có R free nào khác: chỉ có cạnh tới R0, hiện đang matched với L0 và không được đi xuôi thêm. Vì vậy **không có đường tăng** từ L1.

Đồ thị có 3 đỉnh L và chỉ 2 đỉnh R nên không thể có matching ghép cả ba đỉnh L. Giá trị tối đa là 2; thuật toán đã đạt được.

### Tập reachable theo đường xen kẽ

Sau khi thuật toán dừng, chạy một lượt BFS cuối từ tất cả đỉnh L free theo quy tắc xen kẽ:

~~~text
Z_L = {L0,L1}
Z_R = {R0}
~~~

L1 là free root. Từ L1 qua cạnh chưa ghép tới R0; từ R0 theo cạnh matched đi tới L0. Không thể đi tới R1.

Các tập này không chỉ dùng để kết luận “không tăng được”; chúng còn cho ta **chứng chỉ định lý Hall** và **minimum vertex cover** trong đồ thị hai phía.

## 10. Định lý Hall: điều kiện ghép hết phía trái

**Định lý Hall (marriage theorem):** đồ thị hai phía G=(L∪R,E) có một matching ghép được **mọi đỉnh L** khi và chỉ khi với mọi tập con S⊆L:

~~~text
|N(S)| >= |S|
~~~

Trong đó N(S) là tập những đỉnh R có ít nhất một hàng xóm trong S.

### Ví dụ vi phạm Hall

Ở phần 9, chọn:

~~~text
S = {L0,L1}
N(S) = {R0}
~~~

Ta có |S|=2 và |N(S)|=1. Hai đỉnh L0,L1 đều chỉ chấp nhận R0, trong khi một R chỉ có thể ghép cho một L. Vì vậy không thể ghép hết L.

Đây là **nguyên nhân cấu trúc**, không phải do thứ tự lựa chọn tham lam kém.

### Lấy một tập vi phạm Hall từ BFS cuối

Nếu matching đã maximum nhưng vẫn còn L free, đặt Z_L,Z_R là các đỉnh reachable theo đường xen kẽ từ **tất cả L free**.

Trong một đồ thị hai phía, từ mỗi L trong Z_L, mọi R kề với nó đều thuộc Z_R:

- Nếu cạnh L–R là unmatched, BFS đi trực tiếp L→R.
- Nếu cạnh L–R là matched và L được tới qua đường xen kẽ, R đã được thăm để dẫn tới L. Đối với L free root không có matched edge.

Vì không còn đường tăng, mọi R trong Z_R đều **đang matched**. Hơn nữa, mỗi R trong Z_R matched với một L thuộc Z_L. Do còn ít nhất một L free trong Z_L, số đỉnh L reachable **lớn hơn** số đỉnh R reachable.

Do đó:

~~~text
N(Z_L) = Z_R
|Z_R| < |Z_L|
~~~

Z_L là một **chứng chỉ vi phạm Hall**: không thể ghép hết L.

Ví dụ ta lấy được Z_L={L0,L1}, Z_R={R0}, đúng điều kiện 1<2.

### Hall không nói rằng matching maximum là perfect

Nếu |L|>|R|, không thể ghép hết L. Nếu |L|≤|R| và Hall đúng, tồn tại matching ghép hết L, nhưng chưa chắc mọi R đều matched nếu |R|>|L|.

Một **perfect matching** theo định nghĩa phổ biến ghép **mọi đỉnh của toàn đồ thị**; đối với bipartite graph điều này cần |L|=|R| và điều kiện Hall thích hợp. Matching “ghép hết phía L” (left-perfect hoặc left-saturating) là một khái niệm khác khi hai phía có kích thước không bằng nhau.

## 11. Định lý Kőnig: chứng chỉ qua minimum vertex cover

Một **vertex cover** là tập đỉnh C sao cho **mọi cạnh của đồ thị** đều có ít nhất một đầu thuộc C. Một **minimum vertex cover** là vertex cover có số đỉnh nhỏ nhất.

**Định lý Kőnig:** trong mọi đồ thị hai phía:

~~~text
maximum matching cardinality
    = minimum vertex cover cardinality
~~~

Đây là một định lý đặc biệt quan trọng khi ghép cặp và phân công.

### Xây vertex cover từ BFS cuối

Sau khi matching maximum, dùng Z_L,Z_R là tập reachable theo đường xen kẽ từ tất cả L free, rồi đặt:

~~~text
C = (L \ Z_L) union Z_R
~~~

Tập C là một **minimum vertex cover**.

Với ví dụ Hall ở phần 9:

~~~text
L = {L0,L1,L2}
Z_L = {L0,L1}
Z_R = {R0}

C = {L2} union {R0}
  = {L2,R0}
~~~

Mọi cạnh đều được phủ:

- L0–R0 và L1–R0 được phủ bởi R0.
- L2–R1 được phủ bởi L2.

|C|=2=|M|, nên C tối ưu.

### Tại sao C che phủ mọi cạnh?

Giả sử có một cạnh L–R **không được phủ** bởi C. Khi đó L∈Z_L (nên không thuộc L\Z_L) và R∉Z_R. Nhưng từ L reachable, BFS xen kẽ sẽ tới R qua cạnh unmatched; nếu cạnh là matched thì R đã reachable trước khi L được đi tới qua cạnh matched. Mâu thuẫn.

Vậy C phủ mọi cạnh.

### Tại sao C có kích thước bằng matching?

Mỗi cạnh matching ghép một L với một R. Nếu L reachable, cạnh matched của nó đi tới một R reachable; khi ấy C chọn R. Nếu L không reachable, C chọn L. Không có cạnh matching nào có cả hai đầu thuộc C theo cách xây này. Vì C chọn đúng **một đầu của mỗi cạnh matching**, ta được |C|=|M|.

Mọi vertex cover phải có kích thước ít nhất |M| vì các cạnh matching đôi một không chung đỉnh. Vì C đạt đúng cận dưới này, C là **minimum vertex cover**.

**Lưu ý:** công thức C=(L\Z_L)∪Z_R chỉ đúng khi Z được dựng theo **cạnh xen kẽ từ các L free trong matching maximum**. Chạy BFS trên graph vô hướng gốc rồi áp công thức sẽ sai.

## 12. Các loại ghép cặp và điều kiện dừng

| Khái niệm | Điều kiện | Ví dụ ý nghĩa |
| --- | --- | --- |
| Matching hợp lệ | Không hai cạnh chung đỉnh | Phân công không trùng người/công việc |
| Maximal matching | Không thêm một cạnh đơn lẻ được | Một bước tham lam kẹt |
| Maximum matching | Không matching nào lớn hơn | Số cặp tối đa toàn cục |
| Augmenting path | Đường xen kẽ, hai đầu free | Chứng cứ có thể tăng |M| thêm 1 |
| Left-perfect matching | Mọi L đều matched | Mỗi người được giao một công việc |
| Right-perfect matching | Mọi R đều matched | Mọi vị trí được lấp |
| Perfect matching | Mọi đỉnh L∪R đều matched | Không đỉnh nào còn free |
| Minimum vertex cover | Số đỉnh phủ mọi cạnh nhỏ nhất | Chứng chỉ tối ưu bằng Kőnig |

### Một thuật toán có thể dừng theo cách nào?

- **Chứng chỉ chính xác nhất:** không còn augmenting path theo matching hiện tại → maximum (Berge).
- **Cận trên đạt được:** nếu đã ghép đủ min(|L|,|R|) cặp thì matching chắc chắn maximum, có thể dừng sớm mà không cần BFS cuối.
- **Không có cạnh free–free trực tiếp:** chỉ cho biết matching maximal; **không đủ** để kết luận maximum.
- **Không còn vertex free ở L:** matching left-perfect và đã chạm cận |L|; maximum.
- **Không còn vertex free ở R:** right-perfect và đã chạm cận |R|; maximum.

Nếu graph trống nLeft=0, khái niệm “mọi L đều matched” đúng theo logic mệnh đề phổ quát trên tập rỗng; một API có thể trả leftPerfect=true. Điều này **không tự động** có nghĩa matching là perfect trên toàn graph nếu vẫn còn đỉnh R.

## 13. Độ phức tạp của thuật toán BFS từng đường tăng

Gọi:

~~~text
L = so dinh phia trai
R = so dinh phia phai
V = L+R
E = so canh giua hai phia
K = kich thuoc matching maximum
~~~

Xây adjacency list O(V+E). Mỗi lượt BFS đa nguồn duyệt mỗi L reachable tối đa một lần, mỗi cạnh L→R liên quan tối đa một lần và một R được thăm tối đa một lần:

~~~text
Time per BFS: O(V+E)
Path reconstruction/flip: O(V)
~~~

Sau mỗi đường tăng, kích thước matching tăng đúng 1. Có đúng K lượt thành công khi bắt đầu từ matching rỗng, cộng tối đa một lượt thất bại để xác nhận tối ưu.

Vì vậy:

~~~text
Total time = O((K+1)*(V+E))
           <= O((min(L,R)+1)*(V+E))

Extra memory (without step log):
    adjacency    O(V+E)
    match arrays O(V)
    BFS parent   O(V)
    queue/seen   O(V)
    => O(V+E)
~~~

Trong nhiều tài liệu, độ phức tạp được đơn giản thành O(VE) hoặc O(L·E) đối với cách tìm đường tăng từng lượt trên graph hai phía, với các giả định về số đỉnh/cạnh không cô lập. Công thức **O((K+1)(V+E))** giữ cả trường hợp ít cạnh và nhiều đỉnh cô lập.

### Bộ nhớ log

Mã Java bên dưới lưu từng đường tăng để giải thích kết quả. Với K đường tăng, mỗi đường có tối đa O(V) đỉnh, log chiếm thêm O(KV). Bởi vậy **bộ nhớ của cả demo có log** là O(V+E+KV), không phải chỉ O(V+E).

### Khi nào dùng Hopcroft–Karp?

Hopcroft–Karp tối ưu bằng cách dùng **BFS xây tầng và DFS tìm nhiều đường tăng ngắn nhất đôi một không chung đỉnh** trong mỗi pha, đạt O(E√V) cho đồ thị hai phía (cận thường nêu với E>0). Trên graph lớn, Hopcroft–Karp có thể nhanh hơn lặp BFS tìm **một** đường mỗi lần.

Không được gọi chương trình BFS-từng-đường của bài là Hopcroft–Karp: thuật toán trong bài vẫn có cận xấu nhất dựa vào **K lần tăng**, chứ không phải số pha O(√V).

## 14. Java 17 – tìm đường tăng, flip và chứng chỉ maximum

Chương trình dưới đây giải **maximum-cardinality matching trên đồ thị hai phía không trọng số**. Mỗi cạnh input là một cặp (left,right); không dùng một ma trận trọng số hoặc công thức tối ưu chi phí.

Bộ giải:

1. Xác thực số đỉnh hai phía và endpoints của từng cạnh.
2. Dựng adjacency list từ L sang R; cho phép cạnh trùng endpoints.
3. Khởi tạo matchLeft/matchRight=-1.
4. Chạy BFS đa nguồn từ mọi đỉnh L free, theo cạnh unmatched L→R và cạnh matched R→L.
5. Lưu parentRight và viaRight; nếu tìm R free thì dựng đường, flip và tăng |M| thêm 1.
6. Lặp cho tới khi không còn đường tăng.
7. BFS xen kẽ cuối để lấy Z_L,Z_R và dựng **minimum vertex cover** bằng Kőnig.
8. Trả các mảng matching, từng đường tăng, độ phủ đỉnh và trạng thái ghép hết phía trái.

**Tên tệp:** MatchingAugmentingPathDemo.java. Dùng JDK 17 trở lên.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class MatchingAugmentingPathDemo {

    record Pair(int left, int right) {
        @Override
        public String toString() {
            return "(L" + left + "-R" + right + ")";
        }
    }

    record Step(List<String> path, int sizeAfter) {}

    record Result(
            int size,
            int[] matchLeft,
            int[] matchRight,
            List<Step> steps,
            List<Integer> reachableLeft,
            List<Integer> reachableRight,
            List<String> minVertexCover,
            boolean allLeftMatched) {}

    private static List<String> augmentOnce(
            List<List<Integer>> adj,
            int[] matchLeft,
            int[] matchRight) {

        int leftCount = matchLeft.length;
        int rightCount = matchRight.length;
        int[] parentRight = new int[rightCount];
        int[] viaRight = new int[leftCount];
        boolean[] seenLeft = new boolean[leftCount];
        boolean[] seenRight = new boolean[rightCount];

        Arrays.fill(parentRight, -1);
        Arrays.fill(viaRight, -1);

        // Start at every currently unmatched left vertex.
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int l = 0; l < leftCount; l++) {
            if (matchLeft[l] == -1) {
                seenLeft[l] = true;
                queue.addLast(l);
            }
        }

        int freeRight = -1;

        while (!queue.isEmpty() && freeRight == -1) {
            int l = queue.removeFirst();

            for (int r : adj.get(l)) {
                // From L, traverse only unmatched edges.
                if (matchLeft[l] == r || seenRight[r]) {
                    continue;
                }
                seenRight[r] = true;
                parentRight[r] = l;

                if (matchRight[r] == -1) {
                    freeRight = r;
                    break;
                }

                // Continue from R along its matched edge.
                int nextLeft = matchRight[r];
                if (!seenLeft[nextLeft]) {
                    seenLeft[nextLeft] = true;
                    viaRight[nextLeft] = r;
                    queue.addLast(nextLeft);
                }
            }
        }

        if (freeRight == -1) {
            return null; // no augmenting path
        }

        // Reconstruct from the free R endpoint, flipping
        // matched/unmatched edges along the entire path.
        List<String> reversedPath = new ArrayList<>();
        int right = freeRight;

        while (right != -1) {
            int left = parentRight[right];
            reversedPath.add("R" + right);
            reversedPath.add("L" + left);

            // This predecessor was recorded by BFS before
            // any matching arrays were modified.
            int previousRight = viaRight[left];

            matchLeft[left] = right;
            matchRight[right] = left;
            right = previousRight;
        }

        Collections.reverse(reversedPath);
        return List.copyOf(reversedPath);
    }

    static Result solve(
            int leftCount,
            int rightCount,
            List<Pair> edges) {

        if (leftCount < 0 || rightCount < 0) {
            throw new IllegalArgumentException(
                    "partition sizes must be nonnegative");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> adj = new ArrayList<>();
        for (int l = 0; l < leftCount; l++) {
            adj.add(new ArrayList<>());
        }

        for (Pair edge : edges) {
            if (edge == null) {
                throw new IllegalArgumentException("invalid edge");
            }
            int l = edge.left();
            int r = edge.right();
            if (l < 0 || l >= leftCount
                    || r < 0 || r >= rightCount) {
                throw new IllegalArgumentException(
                        "endpoint out of range");
            }
            adj.get(l).add(r);
        }

        int[] matchLeft = new int[leftCount];
        int[] matchRight = new int[rightCount];
        Arrays.fill(matchLeft, -1);
        Arrays.fill(matchRight, -1);

        List<Step> steps = new ArrayList<>();
        while (true) {
            List<String> path = augmentOnce(
                    adj, matchLeft, matchRight);
            if (path == null) {
                break;
            }
            steps.add(new Step(path, steps.size() + 1));
        }

        // Final alternating BFS from free L vertices.
        boolean[] reachedLeft = new boolean[leftCount];
        boolean[] reachedRight = new boolean[rightCount];
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int l = 0; l < leftCount; l++) {
            if (matchLeft[l] == -1) {
                reachedLeft[l] = true;
                queue.addLast(l);
            }
        }

        while (!queue.isEmpty()) {
            int l = queue.removeFirst();
            for (int r : adj.get(l)) {
                if (matchLeft[l] == r || reachedRight[r]) {
                    continue;
                }
                reachedRight[r] = true;

                int matchedLeft = matchRight[r];
                if (matchedLeft != -1
                        && !reachedLeft[matchedLeft]) {
                    reachedLeft[matchedLeft] = true;
                    queue.addLast(matchedLeft);
                }
            }
        }

        List<Integer> zLeft = new ArrayList<>();
        List<Integer> zRight = new ArrayList<>();
        List<String> cover = new ArrayList<>();

        for (int l = 0; l < leftCount; l++) {
            if (reachedLeft[l]) {
                zLeft.add(l);
            } else {
                cover.add("L" + l);
            }
        }
        for (int r = 0; r < rightCount; r++) {
            if (reachedRight[r]) {
                zRight.add(r);
                cover.add("R" + r);
            }
        }

        int size = steps.size();
        return new Result(
                size,
                matchLeft.clone(),
                matchRight.clone(),
                List.copyOf(steps),
                List.copyOf(zLeft),
                List.copyOf(zRight),
                List.copyOf(cover),
                size == leftCount);
    }

    public static void main(String[] args) {
        Result reroute = solve(2, 2, List.of(
                new Pair(0, 0),
                new Pair(0, 1),
                new Pair(1, 0)));

        System.out.println("reroute size = " + reroute.size());
        for (int i = 0; i < reroute.steps().size(); i++) {
            Step step = reroute.steps().get(i);
            System.out.println("reroute augment " + (i + 1)
                    + " = " + step.path()
                    + "; size = " + step.sizeAfter());
        }
        System.out.println("reroute matchLeft = " +
                Arrays.toString(reroute.matchLeft()));
        System.out.println("reroute matchRight = " +
                Arrays.toString(reroute.matchRight()));
        System.out.println("reroute min cover = " +
                reroute.minVertexCover());
        System.out.println("reroute all-left matched = " +
                reroute.allLeftMatched());

        Result hall = solve(3, 2, List.of(
                new Pair(0, 0),
                new Pair(1, 0),
                new Pair(2, 1)));
        System.out.println("Hall matching size = " + hall.size());
        System.out.println("Hall matchLeft = " +
                Arrays.toString(hall.matchLeft()));
        System.out.println("Hall reachable L = " +
                hall.reachableLeft());
        System.out.println("Hall reachable R = " +
                hall.reachableRight());
        System.out.println("Hall min cover = " +
                hall.minVertexCover());
        System.out.println("Hall all-left matched = " +
                hall.allLeftMatched());

        Result duplicates = solve(3, 3, List.of(
                new Pair(0, 0),
                new Pair(0, 0),
                new Pair(1, 0),
                new Pair(1, 1),
                new Pair(2, 2)));
        System.out.println("duplicate edges size = " +
                duplicates.size());
        System.out.println("duplicate matchLeft = " +
                Arrays.toString(duplicates.matchLeft()));

        Result disconnected = solve(3, 3, List.of(
                new Pair(0, 0),
                new Pair(2, 2)));
        System.out.println("disconnected size = " +
                disconnected.size());
        System.out.println("disconnected min cover = " +
                disconnected.minVertexCover());

        Result rectangular = solve(2, 3, List.of(
                new Pair(0, 1),
                new Pair(0, 2),
                new Pair(1, 1)));
        System.out.println("rectangular size = " +
                rectangular.size());
        System.out.println("rectangular matchLeft = " +
                Arrays.toString(rectangular.matchLeft()));
        System.out.println("rectangular all-left matched = " +
                rectangular.allLeftMatched());

        Result empty = solve(0, 0, List.of());
        System.out.println("empty size = " + empty.size());
        System.out.println("empty all-left matched = " +
                empty.allLeftMatched());

        Result noRight = solve(2, 0, List.of());
        System.out.println("no-right size = " + noRight.size());
        System.out.println("no-right reachable L = " +
                noRight.reachableLeft());

        try {
            solve(2, 2, List.of(new Pair(2, 0)));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid edge: " + ex.getMessage());
        }

        try {
            solve(-1, 1, List.of());
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid size: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MatchingAugmentingPathDemo.java
java MatchingAugmentingPathDemo
~~~

**Stdout chính xác** với thứ tự input và BFS của chương trình:

~~~text
reroute size = 2
reroute augment 1 = [L0, R0]; size = 1
reroute augment 2 = [L1, R0, L0, R1]; size = 2
reroute matchLeft = [1, 0]
reroute matchRight = [1, 0]
reroute min cover = [L0, L1]
reroute all-left matched = true
Hall matching size = 2
Hall matchLeft = [0, -1, 1]
Hall reachable L = [0, 1]
Hall reachable R = [0]
Hall min cover = [L2, R0]
Hall all-left matched = false
duplicate edges size = 3
duplicate matchLeft = [0, 1, 2]
disconnected size = 2
disconnected min cover = [L0, L2]
rectangular size = 2
rectangular matchLeft = [2, 1]
rectangular all-left matched = true
empty size = 0
empty all-left matched = true
no-right size = 0
no-right reachable L = [0, 1]
invalid edge: endpoint out of range
invalid size: partition sizes must be nonnegative
~~~

### Giải thích việc cập nhật trong Java

Ở lượt thứ nhất, augmentOnce nhận queue [L0,L1] và khám phá L0→R0, là một đường tăng 1 cạnh. L0 ghép với R0, matching có size=1.

Ở lượt thứ hai, chỉ còn L1 free:

~~~text
L1 --unmatched--> R0
R0 --matched----> L0
L0 --unmatched--> R1 (free)
~~~

predecessor được lưu:

~~~text
parentRight[R0] = L1
viaRight[L0] = R0
parentRight[R1] = L0
viaRight[L1] = -1
~~~

Truy ngược từ R1 rồi flip, kết quả matchLeft=[1,0]. Chương trình lấy được matching maximum size=2 và minimum vertex cover size=2 theo định lý Kőnig.

Với ví dụ Hall, không có augmenting path sau matching size=2. BFS cuối từ L1 free cho Z_L={L0,L1}, Z_R={R0}; tập {L0,L1} là Hall witness vì chỉ có một hàng xóm R0. Vertex cover dựng được là {L2,R0}, có size=2 bằng matching.

**Cạnh trùng:** ví dụ duplicate có cặp L0–R0 lặp trong input. visitedRight ngăn BFS thăm lặp vô ích; cặp trùng không giúp ghép cùng một L/R nhiều lần. **Disconnected:** đỉnh L1 cô lập khiến không thể ghép hết L; cover {L0,L2} vẫn hợp lệ. **Rectangular:** phía R có 3 đỉnh và phía L chỉ 2 đỉnh, match toàn L là tối ưu dù R0 còn free.

**Input rỗng:** nếu L=R=0, matching rỗng là tối đa; mệnh đề “tất cả L được ghép” đúng theo logic rỗng, nên allLeftMatched=true. Nếu L có 2 đỉnh nhưng R rỗng, matching size=0 và allLeftMatched=false. Nếu một ứng dụng muốn xem trường hợp L=0 là không hợp lệ, phải thay đổi hợp đồng API và xác thực nLeft>0 thay vì âm thầm đổi ý nghĩa output.

### Tính an toàn API

Chương trình clone matchLeft/matchRight trước khi trả kết quả để tách chúng khỏi các mảng nội bộ solver. Vì record chứa int[] Java có thể bị người gọi sửa sau khi trả về, Result **chưa bất biến sâu hoàn toàn**; một API production nên che giấu mảng hoặc trả bản sao trên mỗi getter nếu cần bảo toàn dữ liệu.

Kết quả thứ tự đường tăng và matching cụ thể có thể khác khi đổi thứ tự cạnh/free roots. **Số cặp tối đa không đổi**; có thể có nhiều matching maximum và nhiều min vertex cover.

## 15. Chứng minh thuật toán tìm maximum matching là đúng

**Bất biến 1 – matching luôn hợp lệ.** Ban đầu matching rỗng nên hợp lệ. Mỗi augmentOnce khi tìm được đường tăng chỉ đảo cạnh theo một alternating path có hai đầu free; theo chứng minh phần 3, matching mới vẫn không có hai cạnh chung đỉnh.

**Bất biến 2 – mỗi lượt thành công tăng đúng 1.** Đường tăng có k+1 cạnh unmatched và k cạnh matched. Sau flip, size tăng đúng 1. Do đó biến size bằng số lượt thành công kể từ matching rỗng.

**Bất biến 3 – BFS tìm thấy đường tăng nếu có.** Mọi đường tăng từ L free đi xen kẽ unmatched L→R và matched R→L. BFS khởi tạo mọi L free và khám phá đúng các chuyển trạng thái ấy. Dùng visited bảo đảm mỗi đỉnh chỉ được khám phá một lần, nhưng không mất tính reachable vì các bước theo hướng xen kẽ chỉ phụ thuộc việc đỉnh đã reachable hay chưa. Nếu tồn tại đường tới một R free, BFS sẽ tìm được R free.

**Bất biến 4 – đường được dựng là đường đơn xen kẽ.** parentRight ghi L đến R bằng unmatched edge; viaRight ghi R đến L bằng matched edge. Các đỉnh được đánh dấu khi enqueue/discover, tránh tạo chu trình trong predecessor. Khi truy từ R free về L root free, dãy cạnh đúng luân phiên và hai đầu free.

**Tính dừng.** Mỗi lần augment tăng size thêm 1; size≤min(L,R). Vì thế vòng lặp có tối đa min(L,R) lần thành công, rồi kết thúc khi BFS không thấy đường tăng.

**Tính tối ưu.** Khi BFS không còn tìm được R free, không tồn tại augmenting path. Theo định lý Berge, matching hiện tại là maximum. Định lý Kőnig cũng cho một chứng chỉ độc lập: matching size bằng số đỉnh minimum vertex cover được dựng từ BFS xen kẽ cuối.

### Bất biến kiểm tra thêm

Sau mỗi lượt, phải có:

~~~text
count(matchLeft[l] != -1) = size
count(matchRight[r] != -1) = size
~~~

Với mọi L đã ghép với R:

~~~text
matchLeft[l] = r  <=>  matchRight[r] = l
~~~

Từng cặp ghép phải có cạnh L–R thật trong input. Nếu một trong các bất biến này sai, phần reconstruct/flip hoặc predecessor của BFS có lỗi, dù kết quả size có thể tình cờ đúng.

## 16. So sánh với DFS Kuhn và Hopcroft–Karp

### DFS tăng luồng kiểu Kuhn

Một cách đơn giản tìm đường tăng trong đồ thị hai phía là duyệt lần lượt từng L và dùng DFS để thử ghép nó với R:

~~~text
tryKuhn(l):
    for r adjacent to l:
        if visitedRight[r]:
            continue
        visitedRight[r] = true

        if matchRight[r] == -1 OR
           tryKuhn(matchRight[r]):
            matchRight[r] = l
            return true

    return false
~~~

Bản trực quan này khám phá chuỗi thay đổi ghép cặp tương tự đường tăng. Cần reset visited đúng theo mỗi lần tìm đường tăng, và đồng bộ matchLeft nếu lưu cả hai phía.

Kuhn thường có thời gian O(L·E) với những giả định phù hợp khi thử tối đa L đỉnh trái; thực tế dễ cài với input vừa phải. Dùng DFS đệ quy quá sâu trên một graph lớn có thể tràn stack Java.

### BFS từng đường của bài

BFS đa nguồn cho **một đường tăng có ít cạnh nhất** trong residual alternating digraph, ghi được đường cụ thể, có thể dùng min vertex cover sau khi dừng. Cận O((K+1)(V+E)).

### Hopcroft–Karp

Hopcroft–Karp **gộp nhiều cải thiện trong một pha**:

1. BFS từ mọi L free tạo các lớp khoảng cách tới đỉnh R free gần nhất.
2. DFS theo lớp tìm nhiều đường tăng ngắn nhất **đôi một không chung đỉnh**.
3. Flip đồng loạt các đường tìm được trong pha.
4. Lặp đến khi không còn đường tăng.

Nhờ giảm số pha, độ phức tạp O(E√V) với đồ thị hai phía không trọng số. Đây là lựa chọn thường gặp cho matching kích thước rất lớn.

**Không gọi một BFS riêng cho từng đường tăng là Hopcroft–Karp.** Điểm quyết định của Hopcroft–Karp là khai thác **nhiều đường tăng ngắn nhất trong mỗi pha**, không chỉ là “cũng có dùng BFS”.

## 17. Trường hợp ngoài đồ thị hai phía và bài phân công có trọng số

### Đồ thị vô hướng tổng quát

Định lý Berge vẫn đúng: matching maximum khi và chỉ khi không có đường tăng. Tuy nhiên, trên graph có **chu trình lẻ**, tìm đường tăng bằng BFS xen kẽ cần xử lý trường hợp **blossom**; cách tách L/R của bài này không tồn tại cho mọi đồ thị.

Ví dụ tam giác với các đỉnh 0,1,2 có ba cạnh 0–1,1–2,2–0 là đồ thị **không hai phía**. Cần thuật toán matching tổng quát, chẳng hạn **Edmonds' blossom algorithm** (co các chu trình lẻ thích hợp), nếu muốn xử lý đúng mọi graph.

Không tự “tô hai màu” rồi áp code bipartite khi graph có cạnh trong cùng màu; dữ liệu không còn thỏa tiền điều kiện.

### Phân công có chi phí hoặc lợi ích

Một bài **assignment có trọng số** có thể yêu cầu:

- Ghép nhiều cặp nhất, rồi trong số đó giảm tổng chi phí.
- Ghép tất cả nhân viên vào công việc và tối thiểu hóa chi phí.
- Tối đa hóa tổng lợi ích của các cặp được chọn.
- Chỉ ghép một số cặp, có thưởng/phạt cho việc không ghép.

Trong các bài này, tăng **cardinality** có thể cải thiện mục tiêu chính hoặc có thể chưa đủ để tối ưu chi phí. Các thuật toán như **Hungarian algorithm** (bài phân công vuông/rectangular với giả định phù hợp), **min-cost max-flow** và phương pháp đường tăng có **reduced cost/tiềm năng** cần mô hình thêm chi phí.

Bài Java này giải **maximum cardinality unweighted bipartite matching**; nó không đọc trọng số trên cạnh và **không** bảo đảm tổng chi phí nhỏ nhất khi có nhiều matching cùng số cặp.

### Matching và max flow

Bài matching hai phía có thể mã hóa thành mạng luồng:

~~~text
source -> every L (capacity 1)
each allowed L -> R (capacity 1)
every R -> sink (capacity 1)
~~~

Một luồng nguyên kích thước k tương ứng matching có k cạnh. Cạnh ngược trong residual network cho phép hủy/thay một cặp đã chọn, tương tự việc **flip trên augmenting path** trong matching.

Đây là liên hệ sâu giữa đường tăng của matching và đường tăng của max flow. Tuy nhiên đường tăng trong matching thay đổi số cặp **đúng 1**, còn augmenting path trong max flow tổng quát có thể tăng lượng luồng bằng **bottleneck** lớn hơn 1.

## 18. Các trường hợp biên, giả định và lỗi thường gặp

| Vấn đề | Vì sao dễ sai | Cách làm đúng |
| --- | --- | --- |
| Matching maximal bị gọi là maximum | Không còn cạnh free–free nhưng có đường tăng dài | Áp định lý Berge |
| Alternating path không có hai đầu free | Flip có thể không tăng số cặp | Kiểm hai đầu free |
| Thêm cả cạnh cũ lẫn cạnh mới | Một đỉnh nhận hai cặp | Flip matched/unmatched |
| Từ L đi theo cạnh matched | Phá quy tắc hướng xen kẽ | Chỉ dùng unmatched L→R |
| Từ R đi theo bất kỳ cạnh nào | Có thể rời chuỗi matching | Chỉ đi matched R→L |
| Đánh dấu visited quá muộn | Parent bị ghi đè/queue lặp | Đánh dấu khi discover |
| Không reset visited mỗi lượt | Bỏ qua đường tăng mới sau flip | Khởi tạo BFS mới |
| Lưu parent nhưng không phân biệt hai phía | Truy predecessor sai | parentRight, viaRight rõ ràng |
| Cập nhật matchLeft mà quên matchRight | Matching hai phía bất nhất | Cập nhật cùng cặp |
| Dùng matchLeft đã đổi làm predecessor | Mất đường truy vết | Lưu viaRight cố định từ BFS |
| Chỉ bắt đầu từ một L rồi kết luận maximum | Bỏ L free khác có đường tăng | BFS từ tất cả L free hoặc lần lượt từng L |
| Không kiểm R cuối free | Dừng ở đỉnh R đã matched | Chỉ dừng khi matchRight[r]==-1 |
| Nghĩ mọi R reachable cuối đều free | Mâu thuẫn với dừng maximum | Sau khi tối ưu, mọi R reachable phải matched |
| Không phân biệt left-perfect với perfect | Graph chữ nhật có R free | Kiểm cả hai phía khi cần |
| Rỗng L=0 gây hiểu nhầm | all-left true do mệnh đề rỗng | Nêu rõ hợp đồng |
| Cạnh trùng bị xem như nhiều cơ hội ghép | Một R chỉ được ghép một lần | Matching theo đỉnh, không theo số bản sao cạnh |
| Cạnh trong cùng phía | Không còn bipartite | Từ chối hoặc đổi mô hình |
| Graph không hai phía có chu trình lẻ | BFS phân lớp hai phía không đủ | Dùng blossom cho graph tổng quát |
| Định lý Hall bị áp vào một matching bất kỳ | Z_L không chắc là Hall witness | Chỉ dùng sau maximum |
| Vertex cover lấy từ BFS trên graph gốc | Phủ cạnh sai, không tối thiểu | BFS theo alternating orientation |
| Kết luận maximum chỉ vì |M|=|L| khi L lớn hơn R | Điều kiện vượt cận vật lý | Luôn kiểm size và partitions |
| Giữ mọi augmentation làm memory O(V+E) | Quên chi phí log O(KV) | Bỏ log hoặc tính rõ |
| Dùng cardinality algorithm để tối ưu cost | Mất tối ưu trọng số | Hungarian/min-cost flow nếu cần |

### Cạnh trùng và input rỗng

Nếu graph có nhiều bản sao cùng cặp (L_i,R_j), chúng đều thể hiện khả năng ghép cùng hai đỉnh; không thể chọn hai bản sao đồng thời vì sẽ chung endpoints. Với matching unweighted, có thể khử trùng để tăng tốc nhưng phải giữ đúng semantics nếu edge có id/trọng số riêng.

Khi một phía rỗng hoặc không có cạnh, maximum matching size=0. Tập cover rỗng là hợp lệ nếu graph không có cạnh. Hall certificate có thể là chính tập L chưa ghép với N(L)=∅.

### Tập tối ưu không duy nhất

Có thể tồn tại nhiều matching maximum khác nhau. Đổi thứ tự duyệt cạnh hoặc thứ tự L free có thể đổi đường tăng được chọn, vị trí matchLeft hoặc minimum vertex cover được in. Kiểm thử nên so **cardinality và các bất biến**, không mặc định một matching duy nhất nếu đề không quy định tie-breaking.

## 19. Kiểm thử độc lập và kiểm chứng optimality

### Các bất biến của matching

Đối với kết quả size=k:

1. Mỗi L có matchLeft[l]=-1 hoặc một R hợp lệ.
2. Mỗi R có matchRight[r]=-1 hoặc một L hợp lệ.
3. Hai phía nhất quán: matchLeft[l]=r khi và chỉ khi matchRight[r]=l.
4. Không hai L cùng match với một R.
5. Mọi cặp đã match phải là cạnh hợp lệ trong input.
6. Đếm số L đã match bằng k và đếm số R đã match cũng bằng k.
7. k≤min(nLeft,nRight).
8. Mỗi đường tăng có hai đầu free **tại thời điểm thực hiện**, độ dài cạnh lẻ, và trạng thái cạnh U/M luân phiên.
9. Sau flip, size mới = size cũ +1.
10. Khi kết thúc, không còn đường tăng theo alternating orientation.

### Kiểm định lý Kőnig

Trên graph bipartite, minVertexCover phải thỏa:

- Mọi cạnh (l,r) của input đều có L_l∈C hoặc R_r∈C.
- |C| = matchingSize.

Nếu C hợp lệ và có đúng k đỉnh, trong khi matching có k cạnh đôi một không chung đỉnh, điều đó **chứng minh** cả matching lẫn cover tối ưu. Đây là oracle độc lập về giá trị, không cần tin vào số lượt BFS đã thực hiện.

### Brute force trên graph nhỏ

Với nLeft≤7, nRight≤7, có thể liệt kê các cách gán mỗi L vào một R chưa dùng hoặc để free, rồi lấy cardinality cao nhất:

~~~text
brute(i, usedR, count):
    if i == nLeft:
        best = max(best,count)
        return

    brute(i+1,usedR,count)

    for every neighbor r of left i:
        if r not in usedR:
            mark r used
            brute(i+1,usedR,count+1)
            unmark r
~~~

Brute force này tăng rất nhanh theo kích thước hai phía, nên chỉ phù hợp làm oracle test nhỏ, không phù hợp sản xuất. Nó khác hẳn BFS đường tăng nên có thể bắt lỗi khi triển khai predecessor/flip.

Nếu có nhiều cạnh trùng endpoints, có thể dùng một tập neighbor đã khử trùng để giảm nhánh test; kết quả cardinality không đổi.

### Các ca kiểm thử cố định

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| L0–R0, L0–R1, L1–R0 | Maximum=2, đường tăng dài 3 sau chọn L0–R0 |
| L0–R0, L1–R0, L2–R1 | Maximum=2, Z_L={L0,L1}, Z_R={R0} |
| Cạnh lặp L0–R0 | Không thể ghép R0 cho hai L |
| 3 L,3 R; L0–R0, L1–R1, L2–R2 | Perfect matching size=3 |
| 3 L,3 R; L1 cô lập | Maximum≤2, không left-perfect |
| 2 L,3 R; có thể match toàn L | Left-perfect nhưng không perfect toàn graph |
| L=0,R=0 | Size=0; allLeftMatched=true theo API |
| L=2,R=0 | Size=0; Z_L={L0,L1}; allLeftMatched=false |
| Không có cạnh | Size=0 |
| Có vertex cùng nhãn số ở L và R | L0 và R0 là hai đỉnh khác nhau |
| Edge endpoint ngoài miền | IllegalArgumentException |
| Partition size âm | IllegalArgumentException |
| Đồ thị không hai phía | Không áp dụng trực tiếp thuật toán này |
| Đổi thứ tự input edges | Cardinality giữ nguyên; matching/path có thể đổi |

### Property-based / metamorphic tests

- Đổi tên các đỉnh trong **từng phía** bằng hoán vị, cardinality không đổi.
- Đảo thứ tự input edges, cardinality không đổi.
- Nhân đôi mọi cạnh input, cardinality không đổi.
- Thêm một cạnh, maximum cardinality **không thể giảm**.
- Xóa một cạnh, maximum cardinality **không thể tăng**.
- Thêm một đỉnh cô lập vào L hoặc R, maximum cardinality không đổi.
- Nếu graph có perfect matching và thêm cạnh, perfect matching vẫn tồn tại.
- Nếu leftCount==rightCount và size==leftCount, matching perfect.
- Nếu size<leftCount sau tối ưu, Z_L phải là Hall witness: |N(Z_L)|<|Z_L|.
- Với cùng graph, thuật toán Kuhn/Hopcroft–Karp độc lập phải trả cùng cardinality dù matching cụ thể khác.

### Kiểm ngẫu nhiên có oracle rõ ràng

Sinh nLeft,nRight trong [0,7], chọn mỗi cặp L–R với xác suất bất kỳ, tùy ý thêm một số cạnh trùng. Chạy solver BFS, brute force, và kiểm minimum vertex cover bằng cách liệt kê tất cả tập con của V đối với graph nhỏ. Ba giá trị phải trùng:

~~~text
maximum matching size
= brute force matching optimum
= brute force min vertex cover size
= size of cover constructed from final alternating BFS
~~~

Kiểm thêm rằng toàn bộ các cặp trong matchLeft/matchRight là hợp lệ, và mọi augmentation có hai đầu free trước khi flip.

## 20. Bài tập tự luyện

1. Viết định nghĩa matching, maximal matching và maximum matching. Tạo một ví dụ maximal nhưng không maximum gồm hai đỉnh L và hai đỉnh R.
2. Với M={(L0,R0)} trong graph L0–R0, L0–R1, L1–R0, vẽ tất cả cạnh đã ghép/chưa ghép và đường tăng.
3. Thực hiện phép flip trên đường L1→R0→L0→R1. Giải thích vì sao |M| tăng từ 1 lên 2, không phải 3.
4. Chứng minh một alternating path dài 2k+1 cạnh có k+1 cạnh unmatched và k cạnh matched nếu cả hai đầu free.
5. Dùng định lý Berge: vì sao không còn đường tăng đủ để chứng minh maximum, dù vẫn còn free vertices?
6. Vẽ đồ thị hiệu đối xứng M△M* của hai matching bất kỳ. Giải thích vì sao mỗi thành phần có bậc tối đa 2.
7. Trên graph Hall trong phần 9, tính matching maximum, Z_L,Z_R và tập vi phạm |N(S)|<|S|.
8. Chứng minh C=(L\Z_L)∪Z_R là vertex cover khi Z được dựng đúng từ matching maximum.
9. Chứng minh |C|=|M| trên cùng graph; liên hệ với định lý Kőnig.
10. Viết DFS Kuhn cho bipartite matching và so cardinality với BFS từng đường tăng trên một graph có 1000 đỉnh.
11. Cài BFS chỉ queue L, visited L/R và parentRight/viaRight. Kiểm không đi L→R qua cạnh đã matched.
12. Sửa code để từ chối duplicate edges; giải thích vì sao xóa bản sao cạnh không thay đổi cardinality trong matching không trọng số.
13. Sửa code để không lưu toàn bộ Step nhằm giảm bộ nhớ. So sánh O(V+E) và O(V+E+KV).
14. Đổi thứ tự các edges của graph reroute. Đường tăng được chọn có thể khác ra sao? Cardinality có đổi không?
15. Tạo graph nhiều đỉnh cô lập ở L. Kiểm allLeftMatched=false và Hall witness được tìm khi có L free.
16. Với nLeft=2,nRight=3, tìm matching ghép hết L nhưng còn R free. Giải thích khác biệt left-perfect và perfect.
17. Sinh 100 đồ thị nhỏ ngẫu nhiên và đối chiếu matching size với brute force.
18. Liệt kê tất cả vertex covers của graph 3L–2R, tìm minimum cover và so với matching maximum.
19. Từ một bipartite graph, dựng mạng luồng có capacity 1 để giải matching bằng Edmonds–Karp; đối chiếu đường tăng.
20. Giải thích vì sao một mạng luồng tổng quát có bottleneck>1 trong khi một đường tăng matching cardinality tăng đúng 1.
21. Phát biểu khác biệt giữa Kuhn O(L·E) và Hopcroft–Karp O(E√V) trong các mô hình/thứ tự xử lý phù hợp.
22. Xây một graph không hai phía chứa tam giác. Giải thích vì sao code L/R của bài không thể giải trực tiếp; tìm hiểu blossom.
23. Đặt trọng số/chi phí lên từng cặp trong graph có hai maximum matchings. Chỉ ra matching maximum chưa chắc tối thiểu hóa tổng chi phí.
24. Thiết kế API trả kết quả ghép cặp theo **tên người/tên việc** thay vì chỉ số nguyên, vẫn bảo đảm mỗi tên thuộc đúng một phía.
25. Xác minh bất biến matchLeft và matchRight sau **mỗi lần flip**, không chỉ khi kết thúc.
26. Tạo graph có nhiều maximum matchings và nhiều minimum vertex covers, rồi giải thích vì sao test không nên bắt đúng một tập cạnh.

## 21. Checklist và kết luận

Khi giải bài ghép cặp bằng đường tăng, hãy kiểm tra:

- **Bài toán là maximum-cardinality matching hay minimum-cost assignment?** Không dùng thuật toán không trọng số khi cần tối ưu chi phí.
- **Graph có hai phía không?** Nếu không, phải xem xét blossom hoặc bài toán graph tổng quát phù hợp.
- **Matching hiện tại có hợp lệ?** Không có hai cạnh chung đỉnh; hai bảng matchLeft/matchRight nhất quán.
- **Đường tìm được có alternating không?** Theo quy tắc unmatched L→R và matched R→L.
- **Hai đầu đường có free không?** Nếu không thì chưa đủ điều kiện cải thiện cardinality.
- **Khi augment có flip toàn đường không?** Không cộng đơn giản mọi cạnh mới vào matching cũ.
- **Có tìm từ tất cả L free không?** Nếu chỉ thử một L và thất bại, chưa thể kết luận maximum.
- **Đã reset visited và predecessor sau mỗi flip chưa?** Hướng cạnh xen kẽ phụ thuộc matching mới.
- **Điều kiện dừng có thật sự “không còn đường tăng” không?** Maximal không đồng nghĩa maximum.
- **Có thể dựng Hall witness nếu còn L free?** Z_L từ BFS cuối có |N(Z_L)|<|Z_L|.
- **Có kiểm chứng bằng minimum vertex cover không?** Theo Kőnig, |C|=|M| tại optimum.
- **Đã kiểm các ca cạnh trùng, đỉnh cô lập, hai phía không đều, input rỗng và chỉ số không hợp lệ chưa?**
- **Đã kiểm thử brute force hoặc một thuật toán độc lập với graph nhỏ chưa?**

**Kết luận:** một **đường tăng** là đường **xen kẽ cạnh đã ghép/chưa ghép** có **hai đầu tự do**. Đảo trạng thái các cạnh dọc đường làm matching lớn thêm **đúng một cặp** mà vẫn hợp lệ. **Định lý Berge** bảo đảm matching đạt kích thước tối đa khi và chỉ khi **không còn đường tăng**. Trên đồ thị hai phía, BFS/DFS qua các cạnh unmatched L→R và matched R→L cho phép tìm và áp dụng liên tiếp các cải thiện. Khi thuật toán dừng, BFS xen kẽ còn cho **chứng chỉ tối ưu**: tập vi phạm Hall nếu không ghép hết L, và một minimum vertex cover có số đỉnh đúng bằng kích thước maximum matching theo **định lý Kőnig**. Kỹ thuật này là nền tảng để hiểu Kuhn, Hopcroft–Karp, ghép cặp qua mạng luồng và các bài phân công phức tạp hơn.
