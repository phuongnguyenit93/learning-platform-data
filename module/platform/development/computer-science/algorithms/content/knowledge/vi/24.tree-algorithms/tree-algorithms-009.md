# Tâm cây, trọng tâm và các tiêu chí cân bằng

Trong **thuật toán trên cây**, từ “đỉnh ở giữa” có thể chỉ những đối tượng rất khác nhau. **Tâm cây (tree center)** giảm khoảng cách xa nhất tới một đỉnh; **trọng tâm cây (tree centroid)** giảm kích thước thành phần lớn nhất còn lại sau khi loại bỏ một đỉnh; **trung vị cây (tree median)** giảm **tổng** khoảng cách tới các đỉnh. Trên một số cây đối xứng chúng trùng nhau, nhưng trên cây lệch nhánh, **tâm và trọng tâm thường khác nhau**. Chọn nhầm tiêu chí sẽ dẫn đến lời giải tối ưu cho *một bài toán khác*, không phải bài người dùng đặt ra.

Bài học này thuộc nhóm **Thuật toán trên cây** của Computer Science Algorithms. Ta sẽ xác định từng hàm mục tiêu, giải tâm bằng **đường kính** hoặc **bóc lá**, tìm trọng tâm bằng **kích thước cây con**, tính tổng khoảng cách bằng **đổi gốc (rerooting DP)**, chứng minh các tính chất, xử lý cây một/hai đỉnh và cây có trọng số, phân tích O(n), rồi kiểm chứng bằng chương trình **Java 17+** kèm đầu ra xác định và **300 cây kiểm thử** với phương pháp brute-force độc lập.

## 1. Cây là gì và các giả định

Một **cây vô hướng** có n đỉnh và n−1 cạnh, đồng thời **liên thông và không có chu trình**. Giữa hai đỉnh bất kỳ u,v có đúng **một đường đi đơn**. Với các thuật toán chính trong bài:

- n là **số nguyên dương**, đỉnh mang ID `0..n−1`.
- Mỗi cạnh **vô hướng** dài **1 đơn vị** trong mô hình không trọng số.
- Một đỉnh được tính là **một đơn vị khối lượng/kích thước** nếu đề hỏi cân bằng theo số đỉnh.
- Khoảng cách `dist(u,v)` là số cạnh trên đường đi duy nhất u–v.
- Khi xóa đỉnh v, xóa luôn mọi cạnh kề v; phần còn lại có thể tách thành nhiều **thành phần liên thông**.
- Chương trình Java **từ chối n=0, đồ thị thiếu cạnh, không liên thông, khuyên, cạnh trùng làm sai tính cây**; một cây một đỉnh n=1 hoàn toàn hợp lệ.

Một cạnh có **trọng số độ dài** khác 1 sẽ làm thay đổi khoảng cách và có thể làm thay đổi tâm, nhưng **không tự động làm đổi trọng tâm theo số đỉnh**. Nếu mỗi đỉnh mang **trọng lượng/nhu cầu riêng**, định nghĩa trọng tâm theo tổng khối lượng cần được sửa tương ứng. Các biến thể này được trình bày tách biệt ở phần sau.

## 2. Tâm cây — giảm khoảng cách xa nhất

Với đỉnh v, định nghĩa **độ lệch tâm (eccentricity)**:

`ecc(v) = max_{u∈V} dist(v,u)`

**Bán kính cây (radius)** là `R = min_{v∈V} ecc(v)`. Các đỉnh đạt R là **tâm cây**.

Tâm giải các câu hỏi như:

- Đặt **một trạm phục vụ** ở đỉnh nào để khách xa nhất phải đi **ít bước nhất**?
- Chọn **gốc cây** nào để chiều cao (độ sâu lớn nhất tính theo cạnh) của cây đã gốc hóa nhỏ nhất?
- Nếu truyền thông tin từ gốc, mỗi cạnh mất một đơn vị thời gian và mọi nhánh truyền song song, nên bắt đầu ở đâu để hoàn tất sớm nhất?

Tâm tối ưu **trường hợp xấu nhất**, tức đối tượng xa nhất; nó không trực tiếp quan tâm có bao nhiêu đỉnh ở các nhánh gần nguồn.

**Ví dụ đường thẳng 6 đỉnh:**

~~~text
0 -- 1 -- 2 -- 3 -- 4 -- 5
~~~

Giá trị `ecc(v)` lần lượt là `[5,4,3,3,4,5]`. Bán kính là **3**, nên có **hai tâm [2,3]**. Đường kính dài **5 cạnh**. Nếu có 5 đỉnh thay vì 6, tâm duy nhất là đỉnh 2, bán kính 2, đường kính 4.

### Đặc tính tâm với cạnh không trọng số

Với cây có **đường kính D** (khoảng cách lớn nhất giữa hai đỉnh), ta có:

`radius = ceil(D/2)`

Số tâm theo đỉnh là **một hoặc hai**:

- D **chẵn**: tâm là đỉnh ở chính giữa một đường kính.
- D **lẻ**: tâm là hai đỉnh kề nhau bao quanh giữa đường kính.

**Một đỉnh**: D=0, tâm [0], bán kính 0.

**Hai đỉnh**: D=1, cả hai đỉnh là tâm, bán kính 1.

Lưu ý: công thức trên giả định **mỗi cạnh dài đúng 1** và tâm phải nằm ở **đỉnh**. Nếu được đặt cơ sở **giữa cạnh**, hoặc các cạnh có độ dài khác nhau, bài toán trung tâm liên tục có một cách giải thích khác.

## 3. Trọng tâm cây — giảm nhánh lớn nhất sau khi bỏ một đỉnh

Xóa đỉnh v của cây sẽ chia phần còn lại thành nhiều thành phần liên thông, mỗi thành phần nằm về một hướng hàng xóm của v. Gọi:

`largest(v) = max{size(C): C là một thành phần của T−v}`

Với cây một đỉnh, sau khi xóa đỉnh không còn thành phần nào; quy ước `largest(v)=0`.

**Trọng tâm cây (centroid)** là đỉnh v **tối thiểu hóa largest(v)**. Một đặc tính mạnh hơn, đặc biệt hữu ích khi cài đặt:

> v là trọng tâm **khi và chỉ khi** mọi thành phần còn lại sau khi xóa v có **không quá n/2 đỉnh**.

Do kích thước là số nguyên, cũng có thể viết `largest(v) ≤ floor(n/2)`. Vậy mục tiêu không phải làm **độ sâu** nhỏ nhất, mà là làm **nhánh lớn nhất theo số đỉnh** nhỏ nhất.

Trọng tâm phù hợp khi:

- Chọn một điểm chia cây để **mỗi bài toán con có nhiều nhất một nửa số đỉnh**.
- Xây dựng **centroid decomposition**: chọn trọng tâm, xóa nó, rồi làm tương tự cho từng thành phần còn lại.
- Cân bằng khối lượng công việc khi mỗi đỉnh tương ứng một phần việc có cùng chi phí.
- Chọn điểm “đại diện” nhằm giảm số đối tượng còn ở bên lớn nhất sau khi chia.

Trên cây có n≥1 và tất cả đỉnh nặng bằng nhau, tồn tại **một hoặc hai trọng tâm**. Nếu có hai, chúng là **hai đỉnh kề nhau**, và khi xóa cạnh nối chúng, cây tách thành hai phía đều có **n/2 đỉnh**. Hai trọng tâm chỉ có thể xảy ra khi n **chẵn**.

### Ví dụ đường thẳng 6 đỉnh

~~~text
0 -- 1 -- 2 -- 3 -- 4 -- 5
~~~

Xóa 2: có phần `{0,1}` cỡ 2 và `{3,4,5}` cỡ 3, nên `largest(2)=3`.

Xóa 3: có phần `{0,1,2}` cỡ 3 và `{4,5}` cỡ 2, nên `largest(3)=3`.

Xóa 1: phần bên phải `{2,3,4,5}` cỡ 4, nên `largest(1)=4`.

Vì vậy **trọng tâm [2,3]**, giống tâm của đường thẳng này. Tuy nhiên, điều đó không cho phép coi hai khái niệm luôn trùng nhau.

## 4. Ví dụ “cán chổi”: tâm và trọng tâm khác nhau

Dùng cây 10 đỉnh gồm một đường 6 đỉnh `0−1−2−3−4−5` và **bốn lá gắn vào 0** là `6,7,8,9`:

~~~text
       6
       |
       0 -- 1 -- 2 -- 3 -- 4 -- 5
      /|\
     7 8 9

Các cạnh:
(0,1),(1,2),(2,3),(3,4),(4,5),
(0,6),(0,7),(0,8),(0,9)
~~~

### Tìm tâm theo khoảng cách xa nhất

Đường từ một lá bất kỳ `6,7,8,9` đến đỉnh 5 có **6 cạnh**, nên đường kính D=6. Đỉnh giữa trên đường ấy là **2**, do đó:

~~~text
center = [2]
diameter = 6
radius = 3
~~~

Từ đỉnh 2 đến lá treo ở 0 mất 3 cạnh và đến đỉnh 5 cũng mất 3 cạnh. Từ đỉnh 0, đỉnh 5 cách 5 cạnh nên 0 không thể là tâm theo khoảng cách.

### Tìm trọng tâm theo số đỉnh còn lại

Xóa **0**: nhánh đường `{1,2,3,4,5}` có 5 đỉnh, bốn lá `{6},{7},{8},{9}` có mỗi nhánh 1 đỉnh. Nhánh lớn nhất bằng **5**.

Xóa **1**: phía 0 cùng bốn lá có 5 đỉnh; phía `{2,3,4,5}` có 4 đỉnh. Nhánh lớn nhất cũng bằng **5**.

Xóa **2**: phía trái `{0,1,6,7,8,9}` có **6 đỉnh**, phía phải `{3,4,5}` có 3 đỉnh. Vì 6>5 nên 2 **không phải trọng tâm**.

Kết quả:

~~~text
centroids = [0,1]
minimumLargestComponent = 5
~~~

**Kết luận đối chiếu:** **tâm là [2]**, **trọng tâm là [0,1]**. Đỉnh 2 cân bằng độ **xa** của đầu mút, nhưng bỏ đỉnh 2 tạo một nhánh chứa **6/10** số đỉnh nên không cân bằng theo **quy mô**.

### Tổng khoảng cách cũng cho một tiêu chí khác

Nếu đặt dịch vụ tại 0, tổng khoảng cách đến mọi đỉnh là:

`0+1+2+3+4+5+1+1+1+1 = 19`

Tại 1, tổng cũng bằng **19**. Tại 2, tổng bằng **21**.

Vì vậy **trung vị cây [0,1]** và giá trị tổng nhỏ nhất **19**. Trên cây với mọi đỉnh có trọng lượng như nhau và các cạnh có độ dài dương, **tập trung vị theo tổng khoảng cách trùng với tập trọng tâm theo khối lượng đỉnh**; đây là một định lý riêng, **không** đồng nhất với tâm tối thiểu hóa khoảng cách tối đa.

## 5. Ba tiêu chí tối ưu dễ bị đánh đồng

| Câu hỏi cần giải | Hàm mục tiêu tại đỉnh v | Tên | Kỹ thuật |
| --- | --- | --- | --- |
| Đỉnh xa nhất cách v bao nhiêu? | `max_u dist(v,u)`, lấy min | **Tâm cây / 1-center** | Đường kính, BFS/DFS, bóc lá |
| Xóa v, nhánh lớn nhất còn bao nhiêu đỉnh? | `max size(component of T−v)`, lấy min | **Trọng tâm / centroid** | DFS kích thước cây con |
| Tổng khoảng cách từ v đến các đỉnh bao nhiêu? | `Σ_u dist(v,u)`, lấy min | **Trung vị / 1-median** | Đổi gốc; trên cây unit-demand trùng centroid |
| Chọn gốc để chiều cao lớn nhất nhỏ nhất? | `max depth_root(u)`, lấy min | **Tâm cây** | Đường kính, bóc lá |
| Chọn gốc để cây con lớn nhất của các con nhỏ nhất? | `max(size(child subtree))`, lấy min | **Không luôn là centroid** | Phải tính cả phần phía cha khi đổi gốc |
| Chia để trị sao cho mọi phần sau xóa gốc ≤n/2? | Cận trên kích thước thành phần | **Trọng tâm** | Centroid decomposition |

**Cảnh báo về “cây con lớn nhất”:** nếu chỉ tính những nhánh xuống dưới trong một cây đã chọn gốc cố định, ta có thể bỏ sót thành phần **phía cha** của đỉnh đang xét. Để đánh giá đúng `largest(v)` khi coi **v là điểm bị xóa**, phải tính cả **n−subtreeSize[v]**.

**Không có tiêu chí nào tự nhiên “tốt hơn” tiêu chí khác.** Bài toán hỏi tối thiểu hóa độ trễ xa nhất thì tâm phù hợp; bài hỏi chia thành nhóm gần bằng nhau thì trọng tâm phù hợp; bài hỏi tổng chi phí phục vụ thì trung vị phù hợp.

## 6. Tìm tâm bằng hai (hoặc ba) lượt BFS: đường kính

Trên cây **không trọng số**, dùng tính chất đường kính:

1. Chọn bất kỳ đỉnh s (ví dụ 0), chạy BFS để tìm một đỉnh xa s nhất, gọi là a.
2. Chạy BFS từ a, tìm đỉnh b xa a nhất; khoảng cách `dist(a,b)` chính là **đường kính D**.
3. Có thể lần ngược parent từ b về a để lấy đường kính, rồi chọn **một hoặc hai đỉnh giữa** làm tâm.
4. Hoặc chạy thêm BFS từ b, có hai mảng `distA[v]` và `distB[v]`; tính:

`ecc(v) = max(distA[v], distB[v])`

Sau đó chọn những v có ecc nhỏ nhất. Cách hai mảng còn cho **eccentricity của mọi đỉnh**, hữu ích nếu cần nhiều truy vấn hoặc báo cáo giá trị từng đỉnh.

### Vì sao chọn xa nhất hai lần tìm được đường kính?

Trên cây chỉ có một đường đi đơn giữa mọi cặp đỉnh. Một đỉnh a xa nhất từ s là đầu mút của **một đường kính**; sau đó đỉnh b xa nhất từ a là đầu mút đối diện của một đường kính. Đây là tính chất đặc biệt của **cây**, không phải phát biểu đúng cho mọi đồ thị tổng quát có chu trình.

Từ a và b là hai đầu một đường kính, mọi đỉnh v có:

`ecc(v)=max(dist(v,a),dist(v,b))`

Vì nếu có đỉnh x còn xa v hơn cả hai đầu đường kính thì, khi chiếu các đường đi lên đường kính a–b và xét nhánh chứa x, ta sẽ xây được một đường dài hơn D — mâu thuẫn tính cực đại của đường kính. Hai đầu đường kính đủ mô tả độ lệch tâm của mọi đỉnh.

Từ đó, chọn đỉnh ở giữa đường kính giảm giá trị lớn hơn trong hai khoảng cách về hai đầu, đạt bán kính `ceil(D/2)` đối với cạnh đơn vị.

### Giả mã

~~~text
FUNCTION TREE_CENTERS_BY_DIAMETER(tree)
    a <- farthestVertex(BFS(tree, source=0))
    fromA <- BFS(tree, source=a)
    b <- farthestVertex(fromA)
    fromB <- BFS(tree, source=b)

    D <- fromA.distance[b]
    radius <- +infinity
    centers <- []

    FOR v IN 0..n-1:
        ecc <- max(fromA.distance[v], fromB.distance[v])
        IF ecc < radius:
            radius <- ecc
            centers <- [v]
        ELSE IF ecc == radius:
            APPEND v TO centers

    RETURN D, radius, centers
END FUNCTION
~~~

BFS trên cây n đỉnh có n−1 cạnh nên mỗi lượt **O(n)**, ba lượt vẫn O(n) thời gian, O(n) bộ nhớ. Không cần chạy BFS từ **mọi** đỉnh, vốn sẽ tốn O(n²) với cây lớn.

### Khi nào không được dùng thẳng hai BFS theo số cạnh?

- Nếu đề hỏi **khoảng cách theo tổng độ dài cạnh** (cạnh có trọng số), BFS FIFO không còn tính tổng trọng số. Vì cây có **đường đi duy nhất**, có thể dùng DFS/lượt duyệt cây cộng trọng số **không âm** dọc đường; không cần Dijkstra nếu chỉ cần khoảng cách từ một nguồn trên cây và đã biết cấu trúc.
- Nếu có **trọng số âm**, khoảng cách không còn là metric thông thường và các tính chất đường kính/tâm cần phát biểu lại; thuật toán bài học không áp dụng.
- Nếu đồ thị **không phải cây**, hai lần BFS không bảo đảm tìm đường kính của đồ thị tổng quát.
- Nếu tâm được phép ở **giữa cạnh**, điểm tối ưu có thể không phải một đỉnh; cần xác định miền nghiệm.

## 7. Tìm tâm bằng cách bóc lá từng lớp

Có một cách tìm **tâm cây không trọng số** rất trực quan: liên tục xóa đồng thời các **lá** — đỉnh có bậc 1 (trường hợp n=1, đỉnh duy nhất cũng là tâm) — cho đến khi còn **một hoặc hai đỉnh**.

Bài toán ở đây là tính tâm của **cây vô hướng**, không phải chỉ tìm lá trong một cây gốc hóa.

~~~text
FUNCTION CENTERS_BY_LEAF_PEELING(tree)
    IF n <= 2:
        RETURN all vertices

    degree[v] <- number of neighbors of v
    queue <- all vertices with degree[v] <= 1
    remaining <- n

    WHILE remaining > 2:
        layerSize <- queue.size()
        REPEAT layerSize TIMES:
            u <- queue.popFront()
            mark u removed
            remaining <- remaining - 1

            FOR neighbor v of u:
                IF v is not removed:
                    degree[v] <- degree[v] - 1
                    IF degree[v] == 1:
                        queue.pushBack(v)

    RETURN vertices not removed
END FUNCTION
~~~

**Quan trọng:** xóa **đồng thời cả một lớp lá** mỗi vòng. Nếu xóa từng lá và ngay lập tức coi đỉnh mới trở thành lá trong **cùng vòng** mà không giữ số lượng lớp cũ, có thể xóa quá sâu vào một bên và trả tâm sai.

### Vì sao bóc lá đúng?

Mọi đường đi dài nhất của một cây có ít nhất hai đỉnh đều bắt đầu và kết thúc tại **lá**. Xóa đồng thời tất cả lá làm độ dài các đường dài nhất còn lại giảm **hai cạnh** trong mỗi vòng khi còn cây không tầm thường, nhưng không thay đổi phần **giữa** của đường kính. Vì thế đỉnh ở giữa của đường kính ban đầu vẫn ở giữa cây sau mỗi lần bóc.

Khi chỉ còn một hoặc hai đỉnh, chúng chính là tâm. Độ phức tạp **O(n)** vì mỗi đỉnh bị đưa vào hàng đợi tối đa một lần, mỗi cạnh được cập nhật bậc một số lần hằng định.

**Tâm bằng bóc lá và tâm bằng đường kính phải cho cùng tập đỉnh**. Đây là một phép đối chiếu mạnh vì hai thuật toán có cách tổ chức khác nhau.

## 8. Tính trọng tâm bằng kích thước cây con

Chọn **một gốc bất kỳ**, thường là đỉnh 0. Duyệt cây để xác định `parent[v]` và thứ tự xử lý con trước cha. Gọi:

`subtreeSize[v] = 1 + Σ subtreeSize[child]`

với các con theo cây gốc hóa tại 0.

Khi **xóa v**, các thành phần còn lại chính là:

- Mỗi cây con trực tiếp c của v, có `subtreeSize[c]` đỉnh.
- Nếu v không phải gốc, **phần còn lại phía cha** có `n−subtreeSize[v]` đỉnh.

Vì vậy:

`largest(v)=max(n−subtreeSize[v], max_{child c} subtreeSize[c])`

Đối với gốc, `n−subtreeSize[root]=0` nên công thức vẫn đúng.

### Giả mã hậu thứ tự

~~~text
parent[root] = NONE
order = traversal order from root

subtreeSize[v] = 1 for all v

FOR v IN reverse(order) EXCEPT root:
    subtreeSize[parent[v]] += subtreeSize[v]

FOR v IN all vertices:
    largest[v] = n - subtreeSize[v]
    FOR child c of v:
        largest[v] = max(largest[v], subtreeSize[c])

bestBalance = min(largest)
centroids = all v with largest[v] == bestBalance
~~~

Dùng một lượt DFS hoặc BFS dựng parent và order, một lượt ngược tính subtree size, một lượt xét các cạnh: **O(n)** thời gian và bộ nhớ.

### Vì sao tồn tại một đỉnh cân bằng n/2?

Bắt đầu tại bất kỳ đỉnh v. Nếu khi xóa v có một thành phần chứa **hơn n/2 đỉnh**, di chuyển sang đỉnh hàng xóm thuộc thành phần ấy. Sau khi chuyển từ v sang w, **nhánh lớn trước đó co lại** khi xét phía v; các phía khác của w nằm trong nhánh cũ và đều nhỏ hơn nhánh cũ. Có thể chứng minh đại lượng lớn nhất giảm nghiêm ngặt qua bước di chuyển này. Vì cây hữu hạn, ta sẽ dừng tại đỉnh không còn nhánh nào >n/2, tức một trọng tâm.

Một cách chứng minh khác dựa trên công thức `largest(v)`: nếu có thành phần sau xóa v kích thước >n/2 thì thành phần ấy là **duy nhất** có thể lớn hơn n/2. Đi sang hàng xóm thuộc thành phần lớn đó sẽ giảm phần lớn nhất và quá trình không quay lại, vì phía vừa rời chỉ có <n/2 đỉnh.

### Vì sao có nhiều nhất hai trọng tâm?

Nếu hai đỉnh u và v khác nhau đều đạt điều kiện mọi phần sau khi xóa ≤n/2, chúng phải nằm **kề nhau** và cạnh u–v phải chia cây thành hai phía cùng có n/2 đỉnh. Nếu chúng cách nhau hơn một cạnh, các phía được tách dọc đường nối sẽ tạo yêu cầu không tương thích với việc mỗi phía đều ≤n/2.

Vì vậy tập centroid theo **số đỉnh** có:

- Một đỉnh trong mọi cây có n lẻ.
- Một hoặc hai đỉnh khi n chẵn.
- Nếu hai đỉnh, chúng kề nhau.

**Ví dụ n=10 cán chổi:** bestBalance=5, có hai centroid [0,1]. Đây là ví dụ cân bằng đúng bằng một nửa.

## 9. Đổi gốc để tính tổng khoảng cách và trung vị

Một tiêu chí khác là:

`sumDist(v) = Σ_{u∈V} dist(v,u)`

Một **trung vị cây (tree median)** tối thiểu hóa sumDist(v). Nếu chạy BFS từ từng v để tính tổng, thời gian O(n²). Trên cây, ta tính được tổng cho **mọi v trong O(n)** bằng **rerooting DP**.

### Tổng khoảng cách ở gốc ban đầu

Chọn gốc 0, duyệt một lần tính `depth[v]=dist(0,v)`. Khi đó:

`sumDist(0) = Σ depth[v]`

### Công thức chuyển gốc qua một cạnh

Giả sử c là con của p theo gốc ban đầu và `s=subtreeSize[c]`.

Khi chuyển gốc từ p sang c:

- Có **s đỉnh** ở phía cây con c: khoảng cách tới chúng **giảm 1**.
- Có **n−s đỉnh** ngoài cây con c: khoảng cách tới chúng **tăng 1**.

Vì thế:

`sumDist(c) = sumDist(p) − s + (n−s) = sumDist(p) + n−2s`

Trong Java, tổng khoảng cách dùng `long` vì O(n²) có thể vượt giới hạn `int` khi n lớn.

### Giả mã

~~~text
sumDist[root] = sum(depth[v] for every vertex v)

FOR each parent-before-child vertex c except root:
    p = parent[c]
    s = subtreeSize[c]
    sumDist[c] = sumDist[p] + n - 2*s

minimumSum = min(sumDist)
medians = all v with sumDist[v] == minimumSum
~~~

Duyệt theo thứ tự parent trước child giúp mọi `sumDist[p]` sẵn sàng khi tính `sumDist[c]`. Mỗi cạnh sử dụng một lần, tổng **O(n)**.

### Vì sao trung vị trùng trọng tâm khi mỗi đỉnh có khối lượng 1?

Trên cạnh p–c, dấu của hiệu:

`sumDist(c)−sumDist(p)=n−2s`

Nếu `s>n/2`, đi vào phía c **làm giảm tổng khoảng cách**, nên p không thể là tối ưu. Nếu `s<n/2`, đi vào phía c làm **tăng** tổng khoảng cách. Chỉ khi `s=n/2` hai phía hòa.

Vì vậy một đỉnh tối ưu tổng khoảng cách chính là đỉnh mà **không có phía nào chứa hơn n/2 đỉnh** — điều kiện của centroid. Khi có hai centroid kề nhau, tổng khoảng cách ở chúng bằng nhau.

Kết luận:

> **Trên cây với nhu cầu 1 tại mỗi đỉnh, medians = centroids theo số đỉnh.** Tâm cây có thể khác cả hai.

Điều này vẫn đúng khi **độ dài các cạnh dương nhưng không đồng nhất**, nếu vẫn đặt nhu cầu 1 tại mỗi đỉnh. Khi đi qua cạnh dài L>0, hiệu là `L·(n−2s)`; dấu không đổi. Nếu **khối lượng đỉnh khác nhau**, ta cần thay n và s bằng **tổng khối lượng**, không còn dựa đơn thuần vào số đỉnh.

## 10. Đối chiếu trên một số cây quen thuộc

| Hình dạng | Tâm | Trọng tâm | Trung vị |
| --- | --- | --- | --- |
| Đường 5 đỉnh 0–1–2–3–4 | [2] | [2] | [2] |
| Đường 6 đỉnh 0–1–2–3–4–5 | [2,3] | [2,3] | [2,3] |
| Sao 6 đỉnh, tâm nối 5 lá | [0] nếu 0 là hub | [0] | [0] |
| Cây 1 đỉnh | [0] | [0] | [0] |
| Cây 2 đỉnh | [0,1] | [0,1] | [0,1] |
| “Cán chổi” 10 đỉnh, bốn lá tại 0 | [2] | [0,1] | [0,1] |

Tại sao sao 6 đỉnh có hub 0 là trọng tâm? Xóa hub để lại 5 thành phần đơn đỉnh, nên `largest(0)=1`; xóa một lá thì 5 đỉnh còn lại nối với nhau, `largest(leaf)=5`. Hub cũng là tâm vì nó cách tất cả lá 1 cạnh, trong khi từ lá này đến lá khác phải đi 2 cạnh.

Ở cây đường, các đỉnh nằm giữa vừa giảm khoảng cách đến đầu xa nhất, vừa chia đôi số đỉnh. Nhưng hình dạng cây có nhiều nhánh lệch sẽ phá sự trùng hợp này.

## 11. Cây có trọng số: cần xác định đang cân bằng điều gì

### 11.1. Trọng số trên cạnh là độ dài

Nếu cạnh `(u,v)` có độ dài L>0, khoảng cách là **tổng độ dài dọc đường đi duy nhất**. Khi đó **tâm theo khoảng cách** có thể thay đổi so với cây không trọng số.

**Ví dụ:** đường bốn đỉnh:

~~~text
0 --(2)-- 1 --(7)-- 2 --(1)-- 3
~~~

Đường kính theo tổng độ dài là **10**. Độ lệch tâm tại các đỉnh:

~~~text
ecc(0)=10
ecc(1)=8
ecc(2)=9
ecc(3)=10
~~~

Nếu tâm buộc là **một đỉnh**, tâm là **1**, bán kính **8**. Nhưng nếu được phép đặt tâm **trong lòng cạnh**, điểm tối ưu nằm trên cạnh 1–2, cách 1 đúng **3 đơn vị độ dài**, để cân bằng hai phía đường kính, với bán kính **5**.

**Trọng tâm theo số đỉnh** của đường bốn đỉnh vẫn là **[1,2]**, vì xóa 1 hoặc 2 chia cây thành hai phía bằng hai đỉnh; độ dài cạnh không đổi số đỉnh.

**Trung vị tổng độ dài theo nhu cầu một đơn vị/đỉnh** cũng là [1,2] với tổng khoảng cách nhỏ nhất **17**. Vì khi đi qua cạnh độ dài L, công thức đổi gốc trở thành:

`sumDist(c) = sumDist(p) + L·(n−2·subtreeSize[c])`

L>0 không đổi dấu nên tập median vẫn bằng centroid theo số đỉnh.

**Nếu có cạnh độ dài 0:** nhiều đỉnh có thể cùng độ lệch tâm/tổng khoảng cách; định lý “tâm chỉ 1 hoặc 2 đỉnh” có thể không còn đúng. Nếu độ dài âm, nhiều tính chất metric ở trên không còn áp dụng. Mã Java minh họa **chỉ giải cây không trọng số**.

### 11.2. Trọng số trên đỉnh là khối lượng/nhu cầu

Giả sử mỗi đỉnh u mang một khối lượng `mass[u]>0`. Định nghĩa:

`totalMass=Σ mass[u]`

Sau khi xóa v, khối lượng của mỗi thành phần được tính bằng tổng mass của các đỉnh nằm trong thành phần đó (không tính mass[v] đã xóa). Nếu muốn cân bằng khối lượng, định nghĩa `largestMass(v)` là khối lượng lớn nhất trong các phần còn lại.

Để tìm điểm cân bằng theo một định nghĩa **weighted centroid** chuẩn dùng cận nửa **tổng khối lượng ban đầu** (tính cả mass[v]), ta tìm v sao cho không thành phần nào sau xóa v có khối lượng **lớn hơn totalMass/2**. Đây cũng là điều kiện để v tối thiểu hóa **tổng khoảng cách có trọng số nhu cầu**:

`weightedSum(v)=Σ_u mass[u]·dist(v,u)`

Nếu đổi gốc qua cạnh p–c có độ dài L>0, gọi `subtreeMass[c]` là tổng nhu cầu phía c, ta có:

`weightedSum(c)−weightedSum(p) = L·(totalMass−2·subtreeMass[c])`

**Lưu ý tinh tế:** với khối lượng đỉnh không đồng đều, tiêu chí “tối thiểu hóa **largestMass sau xóa v**” không nhất thiết đồng nhất với tiêu chí “mọi phần ≤ totalMass/2” hay với **weighted median**, vì khối lượng **của chính v** được loại bỏ và có thể rất lớn. Cần đọc kỹ đề đang muốn **minimax kích thước phần còn lại**, **minimax khối lượng phần còn lại**, hay **tổng chi phí phục vụ có nhu cầu**.

Ví dụ đường 3 đỉnh A–B–C với khối lượng `[100,1,1]`:

- Xóa A: phần còn lại B–C có khối lượng **2**, nên `largestMass(A)=2`.
- Xóa B: hai phần A và C có khối lượng **100** và **1**, nên `largestMass(B)=100`.
- Xóa C: phần A–B có khối lượng **101**, nên `largestMass(C)=101`.

Ở đây A vừa tối ưu largestMass sau xóa vừa là weighted median, nhưng sự trùng hợp **không phải định lý tổng quát cho mọi bộ trọng số**. Khi đề định nghĩa weighted centroid bằng **bất đẳng thức nửa tổng**, phải phân biệt với “đỉnh làm khối lượng phần lớn nhất nhỏ nhất” nếu định nghĩa ấy được dùng.

### 11.3. Nếu độ dài cạnh hoặc nhu cầu thay đổi theo thời gian

Trên cây động, khi thêm/xóa cạnh, thay đổi khối lượng đỉnh hoặc thay đổi độ dài, cần xét lại đại lượng mục tiêu. Các thuật toán O(n) đơn giản trong bài thích hợp **cây tĩnh**, không tự động giải truy vấn cập nhật online quy mô lớn. Khi có nhiều truy vấn động, có thể cần cấu trúc dữ liệu phức tạp hoặc tiền xử lý riêng.

## 12. Centroid decomposition: chia để trị nhờ trọng tâm

Trọng tâm hữu ích vì khi xóa nó, mọi thành phần còn lại có nhiều nhất `n/2` đỉnh. Lặp lại quy tắc trên từng thành phần:

~~~text
CENTROID_DECOMPOSITION(component):
    IF component is empty:
        RETURN

    c <- a centroid of component
    mark c as decomposition root of component

    FOR each connected component part after removing c:
        CENTROID_DECOMPOSITION(part)
        connect decomposition root(part) under c
~~~

Mỗi bước đệ quy giảm quy mô bài toán con xuống không quá một nửa, nên **độ sâu cây phân rã O(log n)**. Nếu mỗi tầng duyệt toàn bộ các đỉnh của thành phần để tính centroid, thời gian xây thường **O(n log n)**, bộ nhớ phụ O(n) ngoài stack/metadata (có thể phụ thuộc cách tổ chức).

**Đừng nhầm centroid decomposition với việc “root cây một lần ở centroid”**. Centroid decomposition **chọn lại trọng tâm cho từng phần sau khi xóa trọng tâm trước**, xây một cây cấu trúc mới để hỗ trợ các truy vấn khoảng cách/đánh dấu động. Một centroid duy nhất chỉ tạo được một lần chia.

**Cũng đừng dùng tâm thay centroid để bảo đảm nửa số đỉnh.** Trên cây cán chổi, tâm 2 để lại nhánh 6/10, không đáp ứng yêu cầu của phân rã theo n/2.

## 13. Java 17+: giải cả ba tiêu chí trong O(n)

Chương trình độc lập sau thực hiện:

- `Tree`: kiểm tra cây vô hướng hợp lệ, yêu cầu n≥1 và đúng n−1 cạnh, không khuyên, duyệt kiểm tra liên thông. Điều này đồng thời loại bỏ trường hợp cạnh lặp làm sai tính cây.
- `bfs`: khoảng cách theo số cạnh từ nguồn, tìm đỉnh xa nhất.
- `analyze`: ba lượt BFS lấy đường kính, bán kính, tâm; tính trọng tâm qua subtree size; đổi gốc để tìm median.
- `peelCenters`: bóc lá theo từng lớp, độc lập với phương pháp đường kính.
- `verifySmall`: chạy BFS từ **từng đỉnh** để brute-force eccentricity/tổng khoảng cách, đồng thời thử **xóa từng đỉnh và đếm lại** cỡ thành phần lớn nhất; so với thuật toán tuyến tính.
- `randomCrossCheck`: kiểm tra **300 cây nhỏ** sinh với hạt ngẫu nhiên cố định.
- `main`: in kết quả 6 cây mẫu, chứng minh tâm ≠ trọng tâm ở cây cán chổi, thử input không phải cây.

**Tệp:** `TreeCenterCentroidDemo.java`

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class TreeCenterCentroidDemo {
    static final class Tree {
        final int n;
        final List<List<Integer>> adj = new ArrayList<>();

        Tree(int n, int[][] edges) {
            Objects.requireNonNull(edges, "edges");
            if (n < 1 || edges.length != n - 1) {
                throw new IllegalArgumentException(
                        "Tree needs n>=1 and n-1 edges");
            }
            this.n = n;
            for (int v = 0; v < n; v++) {
                adj.add(new ArrayList<>());
            }

            for (int[] edge : edges) {
                if (edge == null || edge.length != 2) {
                    throw new IllegalArgumentException("Invalid edge");
                }
                int u = edge[0], v = edge[1];
                if (u < 0 || u >= n || v < 0 || v >= n || u == v) {
                    throw new IllegalArgumentException(
                            "Invalid endpoint/self-loop");
                }
                adj.get(u).add(v);
                adj.get(v).add(u);
            }

            // Connected + exactly n-1 undirected edges = a tree.
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.add(0);
            seen[0] = true;
            int reached = 0;

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                reached++;
                for (int v : adj.get(u)) {
                    if (!seen[v]) {
                        seen[v] = true;
                        queue.addLast(v);
                    }
                }
            }
            if (reached != n) {
                throw new IllegalArgumentException(
                        "Disconnected or cyclic graph");
            }
        }
    }

    record BfsData(int farthest, int[] distance) {}

    static BfsData bfs(Tree tree, int source) {
        int n = tree.n;
        int[] dist = new int[n];
        Arrays.fill(dist, -1);
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        queue.addLast(source);
        dist[source] = 0;
        int farthest = source;

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            if (dist[u] > dist[farthest]) {
                farthest = u;
            }
            for (int v : tree.adj.get(u)) {
                if (dist[v] == -1) {
                    dist[v] = dist[u] + 1;
                    queue.addLast(v);
                }
            }
        }
        return new BfsData(farthest, dist);
    }

    record Metrics(
            int diameter,
            int radius,
            List<Integer> centers,
            List<Integer> peeledCenters,
            List<Integer> centroids,
            int bestBalance,
            List<Integer> medians,
            long minimumDistanceSum,
            int[] eccentricity,
            int[] largestAfterRemoval,
            long[] distanceSums) {}

    static List<Integer> peelCenters(Tree tree) {
        int n = tree.n;
        int[] degree = new int[n];
        boolean[] removed = new boolean[n];
        ArrayDeque<Integer> leaves = new ArrayDeque<>();

        for (int v = 0; v < n; v++) {
            degree[v] = tree.adj.get(v).size();
            if (degree[v] <= 1) {
                leaves.addLast(v);
            }
        }

        int remaining = n;
        while (remaining > 2) {
            int layer = leaves.size();

            for (int i = 0; i < layer; i++) {
                int u = leaves.removeFirst();
                removed[u] = true;
                remaining--;

                for (int v : tree.adj.get(u)) {
                    if (!removed[v] && --degree[v] == 1) {
                        leaves.addLast(v);
                    }
                }
            }
        }

        List<Integer> centers = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (!removed[v]) {
                centers.add(v);
            }
        }
        return List.copyOf(centers);
    }

    static Metrics analyze(Tree tree) {
        int n = tree.n;

        int a = bfs(tree, 0).farthest();
        BfsData fromA = bfs(tree, a);
        int b = fromA.farthest();
        BfsData fromB = bfs(tree, b);
        int diameter = fromA.distance()[b];

        int[] eccentricity = new int[n];
        int radius = Integer.MAX_VALUE;
        for (int v = 0; v < n; v++) {
            eccentricity[v] = Math.max(
                    fromA.distance()[v], fromB.distance()[v]);
            radius = Math.min(radius, eccentricity[v]);
        }

        List<Integer> centers = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (eccentricity[v] == radius) {
                centers.add(v);
            }
        }

        // Parent-before-child order (BFS root=0), no recursion.
        int[] parent = new int[n];
        int[] depth = new int[n];
        int[] order = new int[n];
        Arrays.fill(parent, -1);
        order[0] = 0;
        int count = 1;

        for (int i = 0; i < count; i++) {
            int u = order[i];
            for (int v : tree.adj.get(u)) {
                if (v == parent[u]) {
                    continue;
                }
                parent[v] = u;
                depth[v] = depth[u] + 1;
                order[count++] = v;
            }
        }

        int[] subtreeSize = new int[n];
        Arrays.fill(subtreeSize, 1);
        for (int i = n - 1; i > 0; i--) {
            int u = order[i];
            subtreeSize[parent[u]] += subtreeSize[u];
        }

        int[] largest = new int[n];
        int bestBalance = Integer.MAX_VALUE;

        for (int u = 0; u < n; u++) {
            int biggest = n - subtreeSize[u];
            for (int v : tree.adj.get(u)) {
                if (parent[v] == u) {
                    biggest = Math.max(biggest, subtreeSize[v]);
                }
            }
            largest[u] = biggest;
            bestBalance = Math.min(bestBalance, biggest);
        }

        List<Integer> centroids = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (largest[v] == bestBalance) {
                centroids.add(v);
            }
        }

        long sumAtRoot = 0L;
        for (int d : depth) {
            sumAtRoot += d;
        }

        long[] sums = new long[n];
        sums[0] = sumAtRoot;
        for (int i = 1; i < n; i++) {
            int v = order[i];
            sums[v] = sums[parent[v]]
                    + (long) n - 2L * subtreeSize[v];
        }

        long minimumSum = Long.MAX_VALUE;
        for (long s : sums) {
            minimumSum = Math.min(minimumSum, s);
        }

        List<Integer> medians = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (sums[v] == minimumSum) {
                medians.add(v);
            }
        }

        return new Metrics(diameter, radius,
                List.copyOf(centers), peelCenters(tree),
                List.copyOf(centroids), bestBalance,
                List.copyOf(medians), minimumSum,
                eccentricity, largest, sums);
    }

    // Oracle chậm: xóa từng đỉnh, đo thành phần lớn nhất.
    static int bruteLargestPiece(Tree tree, int removed) {
        boolean[] seen = new boolean[tree.n];
        seen[removed] = true;
        int largest = 0;

        for (int start = 0; start < tree.n; start++) {
            if (seen[start]) {
                continue;
            }
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.addLast(start);
            seen[start] = true;
            int size = 0;

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                size++;
                for (int v : tree.adj.get(u)) {
                    if (!seen[v]) {
                        seen[v] = true;
                        queue.addLast(v);
                    }
                }
            }
            largest = Math.max(largest, size);
        }
        return largest;
    }

    static void verifySmall(Tree tree, Metrics m) {
        int n = tree.n;
        int bestRadius = Integer.MAX_VALUE;
        int bestBalance = Integer.MAX_VALUE;
        long bestSum = Long.MAX_VALUE;
        int bruteDiameter = 0;

        int[] ecc = new int[n];
        int[] big = new int[n];
        long[] sums = new long[n];

        for (int v = 0; v < n; v++) {
            int[] d = bfs(tree, v).distance();
            for (int x : d) {
                ecc[v] = Math.max(ecc[v], x);
                sums[v] += x;
                bruteDiameter = Math.max(bruteDiameter, x);
            }
            big[v] = bruteLargestPiece(tree, v);
            bestRadius = Math.min(bestRadius, ecc[v]);
            bestBalance = Math.min(bestBalance, big[v]);
            bestSum = Math.min(bestSum, sums[v]);
        }

        List<Integer> centers = new ArrayList<>();
        List<Integer> centroids = new ArrayList<>();
        List<Integer> medians = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (ecc[v] == bestRadius) centers.add(v);
            if (big[v] == bestBalance) centroids.add(v);
            if (sums[v] == bestSum) medians.add(v);
        }

        if (bruteDiameter != m.diameter()
                || bestRadius != m.radius()
                || bestBalance != m.bestBalance()
                || bestSum != m.minimumDistanceSum()
                || !centers.equals(m.centers())
                || !centers.equals(m.peeledCenters())
                || !centroids.equals(m.centroids())
                || !medians.equals(m.medians())
                || !medians.equals(centroids)
                || !Arrays.equals(ecc, m.eccentricity())
                || !Arrays.equals(big, m.largestAfterRemoval())
                || !Arrays.equals(sums, m.distanceSums())) {
            throw new AssertionError("Tree metric mismatch");
        }
    }

    static void show(String label, Tree tree) {
        Metrics m = analyze(tree);
        verifySmall(tree, m);
        System.out.println(label
                + " diameter=" + m.diameter()
                + " radius=" + m.radius()
                + " centers=" + m.centers()
                + " peeled=" + m.peeledCenters()
                + " centroids=" + m.centroids()
                + " largest=" + m.bestBalance()
                + " medians=" + m.medians()
                + " sum=" + m.minimumDistanceSum());
    }

    static void randomCrossCheck() {
        Random random = new Random(2026L);

        for (int test = 0; test < 300; test++) {
            int n = 1 + random.nextInt(12);
            int[][] edges = new int[n - 1][2];

            // Sinh cây: nối mỗi đỉnh mới v với một đỉnh cũ < v.
            for (int v = 1; v < n; v++) {
                edges[v - 1][0] = v;
                edges[v - 1][1] = random.nextInt(v);
            }

            Tree tree = new Tree(n, edges);
            verifySmall(tree, analyze(tree));
        }
        System.out.println("randomCrossCheck=PASS (300 trees)");
    }

    public static void main(String[] args) {
        show("broom", new Tree(10, new int[][]{
            {0,1}, {1,2}, {2,3}, {3,4}, {4,5},
            {0,6}, {0,7}, {0,8}, {0,9}
        }));

        show("path5", new Tree(5, new int[][]{
            {0,1}, {1,2}, {2,3}, {3,4}
        }));

        show("path6", new Tree(6, new int[][]{
            {0,1}, {1,2}, {2,3}, {3,4}, {4,5}
        }));

        show("star6", new Tree(6, new int[][]{
            {0,1}, {0,2}, {0,3}, {0,4}, {0,5}
        }));

        show("single", new Tree(1, new int[0][2]));
        show("pair", new Tree(2, new int[][]{{0,1}}));

        try {
            new Tree(4, new int[][]{
                {0,1}, {1,0}, {2,3}
            });
            throw new AssertionError("Expected invalid tree");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidGraph=rejected");
        }

        randomCrossCheck();
    }
}
~~~

### Chạy trên JDK 17 trở lên

~~~bash
javac TreeCenterCentroidDemo.java
java TreeCenterCentroidDemo
~~~

**Đầu ra dự kiến chính xác** (danh sách dùng định dạng mặc định của Java):

~~~text
broom diameter=6 radius=3 centers=[2] peeled=[2] centroids=[0, 1] largest=5 medians=[0, 1] sum=19
path5 diameter=4 radius=2 centers=[2] peeled=[2] centroids=[2] largest=2 medians=[2] sum=6
path6 diameter=5 radius=3 centers=[2, 3] peeled=[2, 3] centroids=[2, 3] largest=3 medians=[2, 3] sum=9
star6 diameter=2 radius=1 centers=[0] peeled=[0] centroids=[0] largest=1 medians=[0] sum=5
single diameter=0 radius=0 centers=[0] peeled=[0] centroids=[0] largest=0 medians=[0] sum=0
pair diameter=1 radius=1 centers=[0, 1] peeled=[0, 1] centroids=[0, 1] largest=1 medians=[0, 1] sum=1
invalidGraph=rejected
randomCrossCheck=PASS (300 trees)
~~~

### Giải thích các trường được in

- `diameter`: số cạnh của đường đi dài nhất giữa hai đỉnh.
- `radius`: khoảng cách xa nhất nhỏ nhất có thể đạt tại một đỉnh; với cây đơn vị, bằng `ceil(diameter/2)`.
- `centers`: các đỉnh minimax khoảng cách tìm bằng hai đầu đường kính.
- `peeled`: các đỉnh còn lại sau bóc lá theo lớp; phải khớp hoàn toàn `centers`.
- `centroids`: các đỉnh tối thiểu hóa số đỉnh của thành phần lớn nhất sau xóa.
- `largest`: kích thước phần lớn nhất tối ưu tại centroid.
- `medians`: các đỉnh tối thiểu hóa tổng khoảng cách tới mọi đỉnh.
- `sum`: tổng khoảng cách tối thiểu tại medians.

Ở **broom**, các trường `centers=[2]` và `centroids=[0,1]` khác nhau, trong khi `medians=[0,1]` trùng centroid. Ở **path6**, cả ba tập đều là `[2,3]`; điều này không phải tính chất tổng quát.

### Kiểm tra độc lập trong chương trình

Hàm `verifySmall` không lấy các kết quả diameter/centroid/median của thuật toán nhanh làm oracle. Nó:

1. Chạy BFS từ **từng đỉnh** để tự tính độ lệch tâm, tổng khoảng cách và đường kính bằng cách tối đa hóa khoảng cách trên mọi cặp.
2. **Xóa từng đỉnh** (giả lập bằng đánh dấu đỉnh bị cấm), chạy BFS trên phần còn lại để đo kích thước thành phần lớn nhất.
3. Tìm argmin theo các bảng giá trị brute-force.
4. So chính xác mọi giá trị và danh sách đỉnh với phân tích tuyến tính; đồng thời kiểm tra tập tâm bóc lá và tập median/centroid.

Vì n≤12 trong 300 cây sinh ngẫu nhiên, oracle O(n²) là đủ nhanh. Nếu có bất kỳ sai lệch, mã ném `AssertionError`; nếu tất cả khớp, in PASS.

### Về đầu vào không phải cây

Với n=4 và các cạnh `(0,1),(1,0),(2,3)`, danh sách có **n−1=3 cạnh**, nhưng đồ thị **không liên thông** và có cạnh lặp 0–1. Constructor phát hiện chỉ có 2 đỉnh tới được từ 0 và ném `IllegalArgumentException`. Điều này minh họa vì sao kiểm tra **chỉ n−1 cạnh chưa đủ** để khẳng định đầu vào là cây: còn cần kiểm tra tính liên thông (hoặc không chu trình).

## 14. Độ phức tạp của toàn quy trình

Với n đỉnh và n−1 cạnh:

| Bước | Thời gian | Bộ nhớ phụ |
| --- | ---: | ---: |
| Xây danh sách kề và kiểm tra liên thông | O(n) | O(n) |
| BFS tìm hai đầu đường kính + mảng eccentricity | O(n) | O(n) |
| Bóc lá theo lớp | O(n) | O(n) |
| Duyệt thứ tự gốc và kích thước cây con | O(n) | O(n) |
| Tính largest(v) và danh sách centroid | O(n) | O(n) |
| Đổi gốc tính sumDist mọi đỉnh | O(n) | O(n) |
| **Kết hợp các thuật toán chính** | **O(n)** | **O(n)** |
| Brute-force verifySmall trên một cây nhỏ | O(n²) | O(n) mỗi lần |

**Không nhầm:** chương trình chạy `verifySmall` và 300 bài thử trong chế độ demo; đó là **kiểm thử**, không nằm trong chi phí O(n) của thuật toán giải một cây. Nếu sử dụng `analyze` hoặc `peelCenters` để xử lý bài thi với n lớn, không chạy oracle O(n²) cho mọi đầu vào.

**Độ sâu đệ quy:** code dùng BFS/array-order thay vì DFS đệ quy, nên không gặp lỗi tràn call stack trên cây đường dài chỉ vì thuật toán bị lồng n lời gọi Java. Đổi lại, nó dùng các mảng phụ O(n).

## 15. Những lỗi thường gặp

1. **Gọi trọng tâm là tâm** mà không xem định nghĩa: minimax độ xa và minimax nhánh lớn nhất khác nhau.
2. **Thấy tâm và trọng tâm trùng trên đường thẳng/sao rồi suy ra luôn trùng**, bị phản ví dụ cây cán chổi bác bỏ.
3. **Tính eccentricity bằng tổng khoảng cách** thay vì khoảng cách xa nhất.
4. **Tính centroid bằng chiều cao nhỏ nhất** thay vì kích thước thành phần lớn nhất sau xóa.
5. **Bỏ quên phần phía cha n−subtreeSize[v]** khi đánh giá một đỉnh không phải gốc DFS.
6. **Chỉ tìm một centroid rồi cho rằng không bao giờ có hai**; cây đường chẵn có hai trọng tâm kề nhau.
7. **Cho rằng n lẻ có hai centroid theo số đỉnh**, trái với tính chất hai centroid phải chia n/2.
8. **Dùng diameter/leaf-peeling cho đồ thị có chu trình** mà không kiểm tra giả định cây.
9. **Bóc lá không theo từng lớp**, làm lệch tâm.
10. **Đếm số cạnh trong đường đi bằng số đỉnh**, sai lệch 1.
11. **Quên trường hợp n=1**, làm hàng đợi bóc lá rỗng hoặc công thức cây con hỏng.
12. **Cho rằng n=0 có một tâm tự nhiên**; cần hợp đồng đầu vào riêng.
13. **Không khởi tạo khoảng cách/visited** trước BFS, khiến đỉnh bị thăm nhiều lần hoặc bỏ sót.
14. **Để DFS đi ngược cha vô hạn** trong danh sách kề vô hướng.
15. **Tính subtreeSize theo thứ tự cha trước con khi cộng dồn**, trong khi cần con trước cha (thứ tự ngược).
16. **Tính reroot sumDist mà chưa có sumDist[parent]**, phải duyệt cha trước con.
17. **Dùng int cho tổng khoảng cách n lớn**, có thể tràn.
18. **Quên nhân độ dài cạnh L** khi đổi gốc ở cây có cạnh trọng số.
19. **Dùng BFS theo số cạnh để tính khoảng cách có trọng số 2,7,1**, giải nhầm metric.
20. **Cho rằng cạnh độ dài 0 vẫn bảo đảm một/hai tâm**, có thể có nhiều đỉnh cùng độ lệch tâm.
21. **Gộp trọng lượng đỉnh với độ dài cạnh**, dẫn đến sai khối lượng cân bằng hoặc sai hàm tổng khoảng cách.
22. **Tưởng tối thiểu hóa nhánh lớn nhất sau xóa theo khối lượng tùy ý luôn đồng nhất weighted median**, phải xét đúng định nghĩa và việc loại trọng lượng chính đỉnh bị xóa.
23. **Áp dụng centroid decomposition bằng tâm** và kỳ vọng mọi bài con ≤n/2.
24. **Quên rằng mọi đường giữa hai đỉnh trong cây là duy nhất**, dẫn đến dùng Dijkstra/heap không cần thiết khi chỉ cộng trọng số cạnh trên cây.
25. **Không kiểm tra tính liên thông** khi nhận n−1 cạnh, có thể là đồ thị có chu trình ở một phần và đỉnh cô lập ở phần khác.
26. **Lấy leaf-peeling center làm centroid** vì đều có thể “xóa lá” ở một cách cài đặt khác; đó là hai tiêu chí khác.
27. **Dùng tính chất hai đầu đường kính cho mọi đồ thị tổng quát** mà chưa chứng minh.
28. **Đánh giá một phép thử O(n²) rồi gọi toàn bộ thuật toán O(n)**, nhầm chế độ kiểm thử với chế độ giải chính.
29. **Giữ chỉ một centroid dù đề cần liệt kê tất cả điểm tối ưu**; trong trường hợp hòa phải trả cả hai.
30. **Không kiểm tra kết quả tâm/trọng tâm trên một cây bất đối xứng**, bỏ sót phân biệt quan trọng nhất.

## 16. Bài tập có lời giải

**Bài 1.** Tâm cây tối thiểu hóa đại lượng nào? **Đáp án:** khoảng cách **lớn nhất** từ đỉnh được chọn đến một đỉnh bất kỳ, tức eccentricity.

**Bài 2.** Trọng tâm tối thiểu hóa đại lượng nào? **Đáp án:** kích thước thành phần liên thông **lớn nhất** sau khi xóa đỉnh đó, với mỗi đỉnh tính là một đơn vị.

**Bài 3.** Trung vị cây tối thiểu hóa gì? **Đáp án:** **tổng** khoảng cách từ điểm được chọn đến mọi đỉnh (hoặc tổng có trọng số nhu cầu nếu đề nêu).

**Bài 4.** Đường 0–1–2–3–4 có đường kính và bán kính? **Đáp án:** D=4, R=2, tâm [2].

**Bài 5.** Đường 0–1–2–3–4–5 có bao nhiêu tâm? **Đáp án:** hai, [2,3], vì D=5 lẻ.

**Bài 6.** Với đường sáu đỉnh, nếu xóa đỉnh 2 thì thành phần lớn nhất có mấy đỉnh? **Đáp án:** 3, gồm {3,4,5}.

**Bài 7.** Vì sao centroid có tối đa hai đỉnh? **Đáp án:** hai centroid, nếu tồn tại, phải kề nhau và cạnh nối chúng chia đúng n/2 đỉnh mỗi phía.

**Bài 8.** Một cây n=1 có tâm và centroid nào? **Đáp án:** cùng là đỉnh duy nhất; radius=0, largest sau xóa=0.

**Bài 9.** Trên cây cán chổi 10 đỉnh, tâm là gì? **Đáp án:** [2], vì khoảng cách xa nhất tại 2 bằng 3.

**Bài 10.** Trên cùng cây, centroid là gì? **Đáp án:** [0,1], vì xóa mỗi đỉnh ấy cho thành phần lớn nhất cỡ 5; xóa 2 tạo nhánh cỡ 6.

**Bài 11.** Tổng khoảng cách tối thiểu trên cây cán chổi? **Đáp án:** 19, đạt ở 0 và 1.

**Bài 12.** Có cần chạy BFS từ mọi đỉnh để tìm tâm không? **Đáp án:** không; hai đầu đường kính qua vài lượt BFS cho eccentricity của mọi đỉnh trong O(n).

**Bài 13.** Vì sao bóc lá cùng một lớp? **Đáp án:** để đồng thời loại hai đầu của mọi đường dài nhất, giữ nguyên giữa đường kính.

**Bài 14.** Tại sao bỏ đỉnh có subtreeSize[v]=4 trong cây 10 đỉnh thì phía cha có cỡ 6? **Đáp án:** vì phần ngoài cây con v gồm `n−4=6` đỉnh.

**Bài 15.** Cho n=10 và một con c có subtreeSize[c]=7. Đổi gốc từ cha sang c làm sumDist biến đổi bao nhiêu? **Đáp án:** `10−2·7=−4`, tức tổng giảm 4.

**Bài 16.** Khi nào median và centroid trùng nhau? **Đáp án:** trên cây có mỗi đỉnh mang nhu cầu bằng nhau và cạnh có độ dài dương, tập đỉnh tối ưu tổng khoảng cách trùng tập đỉnh cân bằng theo số đỉnh.

**Bài 17.** Trong đường trọng số 0–(2)–1–(7)–2–(1)–3, tâm là đỉnh nào nếu buộc đặt tại đỉnh? **Đáp án:** 1, có eccentricity 8.

**Bài 18.** Cùng đường trọng số, nếu được đặt giữa cạnh thì bán kính nhỏ nhất là bao nhiêu? **Đáp án:** 5, tại trung điểm theo độ dài của đường kính 10.

**Bài 19.** Nếu chỉ thay độ dài cạnh nhưng giữ số đỉnh mỗi phía, centroid theo số đỉnh đổi không? **Đáp án:** không, vì largest(v) tính số đỉnh chứ không tính độ dài.

**Bài 20.** Vì sao centroid decomposition có chiều sâu O(log n)? **Đáp án:** mỗi lần chọn centroid để xóa, mọi thành phần con còn tối đa một nửa số đỉnh của phần trước.

**Bài 21.** Nếu một đồ thị có n=6 và đúng 5 cạnh nhưng không liên thông, có chắc là cây không? **Đáp án:** không; phải kiểm tra liên thông/chu trình.

**Bài 22.** Nếu một đỉnh có hàng xóm con với các subtreeSize [2,3,1] và phía cha có 4 đỉnh, largest(v) là bao nhiêu? **Đáp án:** 4, vì tính max của tất cả phía sau khi xóa v.

**Bài 23.** Nếu đoạn đường có chiều dài cạnh 0, có còn bảo đảm tâm theo đỉnh chỉ có 1 hoặc 2 không? **Đáp án:** không; nhiều đỉnh nối bởi cạnh độ dài 0 có thể cùng đạt bán kính.

**Bài 24.** Tại sao chương trình dùng `long` cho sumDist? **Đáp án:** tổng khoảng cách O(n²) trong cây đường dài, có thể vượt giới hạn `int`.

**Bài 25.** Đặt một trạm để giảm **thời gian đi xa nhất** nên chọn tâm hay centroid? **Đáp án:** tâm theo metric thời gian, không nhất thiết centroid.

**Bài 26.** Chia việc thành nhiều nhóm, muốn **nhóm lớn nhất** sau khi bỏ người điều phối ≤n/2 nên chọn gì? **Đáp án:** trọng tâm cây.

**Bài 27.** Nếu n chẵn nhưng mọi nhánh sau xóa một đỉnh có ít hơn n/2, có thể có hai centroid không? **Đáp án:** không; hai centroid chỉ xảy ra khi tồn tại cạnh chia cây thành hai nửa đúng n/2.

**Bài 28.** Có thể dùng cách đổi gốc để tính sumDist mọi đỉnh trong O(n) không? **Đáp án:** có, dùng `sumDist(child)=sumDist(parent)+n−2·subtreeSize[child]` trên cây cạnh đơn vị.

## 17. Checklist chọn tiêu chí và cài đặt

1. **Đầu vào là cây vô hướng thật sự?** Có liên thông và đúng n−1 cạnh không?
2. **Đề hỏi khoảng cách xa nhất, nhánh lớn nhất hay tổng khoảng cách?** Chọn tương ứng center, centroid, median.
3. **Khoảng cách đo theo cạnh đơn vị hay độ dài có trọng số?** Không dùng BFS sai metric.
4. **Gốc có thể chọn là đỉnh hay ở giữa cạnh?** Với center liên tục, đáp án có thể nằm trên cạnh.
5. **Khi tính centroid, có kể phía cha `n−subtreeSize[v]` không?**
6. **Có xét tất cả con của từng đỉnh khi tính thành phần lớn nhất sau xóa?**
7. **Đã xử lý n=1, n=2 và khả năng có hai tâm/hai centroid chưa?**
8. **Bóc lá có giữ đúng ranh giới từng lớp không?**
9. **Nếu tìm center qua đường kính, có chạy BFS từ hai đầu và tính max khoảng cách không?**
10. **SubtreeSize có cộng từ con lên cha theo thứ tự ngược chưa?**
11. **Reroot sumDist có duyệt cha trước con và dùng kiểu long cho tổng không?**
12. **Nếu vertex mass không đều, có xác định rõ cân bằng theo khối lượng hay theo số đỉnh không?**
13. **Nếu bài cần centroid decomposition, có chọn lại centroid cho từng thành phần sau khi xóa không?**
14. **Đã đối chiếu center qua đường kính với bóc lá, centroid qua brute xóa đỉnh và median qua BFS mọi nguồn trên cây nhỏ chưa?**
15. **Có thử cây đường, sao, cán chổi bất đối xứng và cây một đỉnh chưa?**
16. **Đã phân tích O(n) cho thuật toán chính, tách khỏi O(n²) của oracle kiểm thử chưa?**

**Ghi nhớ:** **tâm** giảm *khoảng cách xa nhất*; **trọng tâm** giảm *nhánh lớn nhất sau xóa đỉnh*; **trung vị** giảm *tổng khoảng cách*. Tâm tìm bằng **đường kính/bóc lá**; trọng tâm tìm bằng **kích thước cây con**, luôn tính cả phía cha; tổng khoảng cách tìm bằng **đổi gốc**. Trên cây đơn vị với nhu cầu đồng đều, median trùng centroid, nhưng **center không nhất thiết trùng centroid**.
