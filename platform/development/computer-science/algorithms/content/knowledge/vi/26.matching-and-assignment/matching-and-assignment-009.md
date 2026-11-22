# Ghép cặp trên đồ thị tổng quát và ý tưởng co blossom

**Ghép cặp** (*matching*) trên đồ thị vô hướng là một tập cạnh không có hai cạnh nào chung đầu mút. Bài toán **ghép cặp nhiều cạnh nhất** (*maximum-cardinality matching*) yêu cầu tìm matching M sao cho số cạnh |M| lớn nhất. Đồ thị **tổng quát** có thể chứa chu trình lẻ, nên không nhất thiết tách được thành hai phía.

Đối với đồ thị hai phía, các thuật toán tìm **đường tăng** (*augmenting path*) như Kuhn hoặc Hopcroft–Karp xử lý rất hiệu quả. Nhưng trong đồ thị tổng quát, việc tìm đường tăng gặp một trở ngại mới: **blossom**, tức một **chu trình lẻ luân phiên** xuất hiện khi hai nhánh chẵn trong cùng một cây tìm kiếm gặp nhau. Thuật toán **Edmonds' blossom** xử lý bằng cách **co** blossom thành một siêu đỉnh, tìm tiếp trên cấu trúc đã co, rồi **mở** blossom để khôi phục một đường tăng hợp lệ của đồ thị gốc.

Điều quan trọng: thuật toán trong bài giải **maximum-cardinality matching không trọng số** trên đồ thị **vô hướng tổng quát**, không phải maximum-weight matching. Phiên bản có trọng số của blossom cần thêm cơ chế dual/slack phức tạp hơn. Bài này trình bày khái niệm, cơ sở đúng đắn, một ví dụ mà co blossom thực sự cần thiết, quy trình Edmonds, cài đặt Java 17+ hoàn chỉnh, trường hợp biên và kiểm thử độc lập.

## 1. Matching, maximal, maximum và perfect

Cho \(G=(V,E)\), mỗi cạnh nối hai đỉnh phân biệt. Một tập \(M\subseteq E\) là **matching** nếu không đỉnh nào thuộc nhiều hơn một cạnh trong M.

\[
\nu(G)=\max_{\text{matching }M\subseteq E}|M|
\]

là **kích thước maximum matching**. Mỗi cạnh ghép chiếm hai đỉnh, nên:

\[
0\le \nu(G)\le\left\lfloor\frac{|V|}{2}\right\rfloor.
\]

| Khái niệm | Định nghĩa |
|---|---|
| Matching | Tập cạnh đôi một không chung đỉnh |
| Maximal matching | Không thể **thêm một cạnh đơn lẻ** mà vẫn là matching |
| Maximum matching | Matching có **số cạnh lớn nhất** trên toàn bộ graph |
| Perfect matching | Tất cả đỉnh đều được ghép; khi n>0 phải có n chẵn |
| Free/unmatched vertex | Đỉnh chưa thuộc cạnh matching hiện tại |
| Mate/partner | Đỉnh được ghép với v, hoặc -1 nếu v tự do |

**Maximal không đồng nghĩa maximum.** Trên đường bốn đỉnh:

~~~text
0 -- 1 -- 2 -- 3
~~~

Matching M={(1,2)} là maximal: không thể thêm (0,1) hoặc (2,3) nếu giữ nguyên cạnh đang có. Nhưng matching N={(0,1),(2,3)} có hai cạnh, tốt hơn. Một thuật toán chỉ ghép greedily cho đến khi không thêm một cạnh mới được **không bảo đảm maximum**.

**Perfect matching** là trường hợp đặc biệt của maximum matching, có đúng n/2 cạnh khi n chẵn. Với n lẻ, perfect matching là không thể vì số đỉnh sử dụng bởi cạnh ghép luôn chẵn. Có graph n chẵn nhưng vẫn không có perfect matching, chẳng hạn graph có một đỉnh cô lập.

Đồ thị không cần liên thông: matching toàn graph là hợp matching ở mỗi thành phần. **Self-loop** u–u không tạo một cặp hai đỉnh phân biệt và bị bỏ trong cài đặt. **Cạnh song song** giữa u,v có thể xuất hiện trong dữ liệu, nhưng không thể ghép u với v hai lần.

## 2. Đường luân phiên và đường tăng

Giả sử đang có matching M.

- **Cạnh ghép** (*matched edge*) thuộc M.
- **Cạnh chưa ghép** (*unmatched edge*) không thuộc M.
- **Đường luân phiên** (*alternating path*) là đường có cạnh ghép và chưa ghép **xen kẽ**.
- **Đường tăng** (*augmenting path*) là đường luân phiên **đơn**, có hai đầu là đỉnh tự do, cạnh đầu và cuối chưa ghép.

Một đường tăng có số cạnh lẻ, bằng \(2t+1\). Nó chứa \(t\) cạnh đang ghép và \(t+1\) cạnh chưa ghép.

~~~text
Trước:  0 -- 1 == 2 -- 3
Sau:    0 == 1 -- 2 == 3
~~~

Ký hiệu `==` là cạnh ghép. Ta **lật trạng thái** của mọi cạnh trên đường: xóa cạnh đang ghép và thêm cạnh trước đó chưa ghép.

Viết bằng **hiệu đối xứng**:

\[
M'=M\triangle E(P).
\]

Sau khi lật đường tăng P, hai đầu tự do có mate mới; mỗi đỉnh nội bộ chỉ đổi từ một mate sang mate khác; mọi đỉnh vẫn tham gia tối đa một cạnh. Đồng thời:

\[
|M'|=|M|-t+(t+1)=\boxed{|M|+1}.
\]

Đây là thao tác duy nhất làm kích thước matching tăng trong thuật toán Edmonds. **Co blossom không tự tăng số cạnh matching**; co chỉ giúp tìm được đường tăng bị cấu trúc lẻ che khuất.

## 3. Định lý Berge: điều kiện tối ưu hóa

**Định lý Berge** khẳng định:

\[
\boxed{M\text{ là maximum matching}
\iff
\text{không tồn tại đường tăng so với }M.}
\]

**Nếu có đường tăng**, ta lật và tăng |M| thêm 1, nên M chưa maximum.

**Nếu không có đường tăng**, giả sử có matching N với |N|>|M|. Xét đồ thị chỉ gồm các cạnh trong **hiệu đối xứng \(M\triangle N\)**. Vì mỗi đỉnh nhận tối đa một cạnh của M và một cạnh của N, mỗi thành phần có dạng đường hoặc chu trình luân phiên. Nếu N nhiều cạnh hơn M, ít nhất một đường thành phần có **nhiều hơn một cạnh của N so với M**. Đường này có hai đầu tự do đối với M, nên là một đường tăng của M — mâu thuẫn.

Vì vậy một thuật toán có thể tìm matching maximum bằng cách:

~~~text
M = empty matching
while exists an augmenting path P relative to M:
    M = M symmetric_difference edges(P)
return M
~~~

Khó khăn còn lại là **tìm đường tăng đầy đủ trên đồ thị có chu trình lẻ**.

## 4. Vì sao tìm đường tăng kiểu hai phía có thể sai?

Trong đồ thị **hai phía** \(V=L\cup R\), mọi cạnh nối L với R, và **không tồn tại chu trình lẻ**. Một cây tìm kiếm luân phiên từ đỉnh tự do có thể phân lớp **chẵn/lẻ** theo số cạnh trên đường đi:

- Ở **vị trí chẵn**, ta xét cạnh chưa ghép để sang một vị trí lẻ.
- Nếu vị trí lẻ đã ghép, ta đi qua cạnh ghép tới một vị trí chẵn khác.
- Nếu vị trí lẻ tự do, đường từ gốc tự do tới nó là đường tăng.

Trong đồ thị tổng quát, có thể có cạnh nối **hai vị trí chẵn thuộc cùng cây luân phiên**. Cạnh ấy, cùng hai nhánh đi lên tổ tiên chung, tạo một **chu trình lẻ**. Nếu bỏ nó vì “cả hai đầu đã được khám phá”, ta có thể bỏ sót đường tăng. Nếu gọi nó ngay là đường tăng, cũng sai: hai nhánh có thể có **cùng gốc tự do**, nên không tạo hai đầu tự do khác nhau.

Edmonds nhận diện trường hợp này là **blossom** và **co nó thành một siêu đỉnh tạm**.

## 5. Blossom và đế blossom

Một **blossom** trong trạng thái tìm kiếm hiện tại là chu trình **số cạnh lẻ**, cấu thành từ các đoạn đường luân phiên cùng một **cạnh nối hai vị trí chẵn**. Chu trình có một **đỉnh đế** (*base*), là điểm hai nhánh của cây luân phiên gặp nhau.

Một chu trình có 3,5,7,... cạnh đều có thể là blossom **nếu thỏa bất biến luân phiên**. Không được tùy tiện co **mọi chu trình lẻ** của graph: điều kiện đúng liên quan tới **matching hiện tại** và **cây BFS luân phiên**.

Đặc điểm:

- Trên blossom, các cạnh thuộc matching và không thuộc matching được bố trí **luân phiên quanh chu trình**, với cách nhìn đặc biệt tại đế vì độ dài chu trình lẻ.
- Đỉnh đế là nơi kết nối với phần cây luân phiên phía trên, hoặc chính là gốc tự do.
- Khi co, mọi đỉnh trong blossom tạm được xem là một siêu đỉnh B, nhưng các đầu mút cạnh đi ra ngoài phải vẫn có **thông tin gốc** để có thể mở lại.
- Một blossom có thể nằm trong blossom lớn hơn (**blossom lồng nhau**), nên cài đặt phải xử lý các đế đã co.

Để hiểu vai trò của chu trình lẻ, hãy xét ví dụ mà nó **thật sự nằm trên một đường tăng cần tìm**, không chỉ một tam giác độc lập.

## 6. Ví dụ bắt buộc phải xử lý blossom để tìm thêm một cặp

Graph có 6 đỉnh, các cạnh vô hướng theo thứ tự:

~~~text
(0,1), (0,3), (0,4), (0,5),
(1,2), (1,3),
(2,3), (2,4), (2,5)
~~~

Bắt đầu matching rỗng và tìm đường tăng theo thứ tự đỉnh 0..5 và adjacency theo input. Hai lần đầu có thể nhận:

\[
M=\{(0,1),(2,3)\}.
\]

Đỉnh 4 và 5 vẫn tự do. Nếu chỉ giữ M và thử thêm một cạnh nối **hai đỉnh tự do**, sẽ thất bại vì **không có cạnh 4–5**. Tuy nhiên vẫn tồn tại perfect matching.

### Dựng cây luân phiên từ gốc tự do 4

Hai nhánh đi được:

~~~text
4 -- 0 == 1
|
2 == 3
~~~

Trong đó 4–0 và 4–2 chưa ghép; 0–1 và 2–3 đã ghép. Vì thế **1 và 3 là hai vị trí chẵn** cùng thuộc cây gốc 4.

Graph có **cạnh 1–3 chưa ghép**. Cạnh này khép chu trình:

\[
\boxed{4\to0\to1\to3\to2\to4.}
\]

Các cạnh liên tiếp của chu trình có trạng thái:

~~~text
4-0: chưa ghép
0-1: đã ghép
1-3: chưa ghép
3-2: đã ghép
2-4: chưa ghép
~~~

Đây là **blossom 5 cạnh**, đế là **4**. Chu trình lẻ xuất hiện khi nối hai vị trí chẵn 1 và 3. Co năm đỉnh trong chu trình thành một siêu đỉnh B.

### Tìm đường tăng trên graph co

Có cạnh 0–5 trong graph gốc, nên khi co blossom, còn một cạnh từ B tới đỉnh tự do 5. Trong biểu diễn co, tìm được đường tăng **B–5**.

Nhưng kết quả cuối cùng phải là **đường hợp lệ trên graph gốc**, không phải B–5 với đỉnh giả. Mở blossom theo chiều luân phiên phù hợp, ta có:

~~~text
4 -- 2 == 3 -- 1 == 0 -- 5
~~~

Đường tăng:

\[
\boxed{4\to2\to3\to1\to0\to5}
\]

gồm 5 cạnh, với trạng thái *chưa ghép, đã ghép, chưa ghép, đã ghép, chưa ghép*. Hai đầu 4 và 5 đều tự do. Sau khi lật:

\[
\boxed{M'=\{(0,5),(1,3),(2,4)\}.}
\]

Matching M' chứa **3 cặp trên 6 đỉnh**, là **perfect** và vì thế cũng là **maximum**.

Đây là khác biệt giữa **co để tìm kiếm** và **ghép thật**: co không làm mất đỉnh gốc, và lật sau khi mở blossom thay các cặp \((0,1),(2,3)\) bằng ba cặp mới \((0,5),(1,3),(2,4)\).

### Kiểm tra bằng định lý Berge

Sau lần tăng thứ ba, mọi đỉnh đều đã ghép, nên không còn hai đầu tự do cho một đường tăng nữa. Theo Berge, matching là maximum. Trên graph này giới hạn tổng quát \(\lfloor6/2\rfloor=3\) cũng đã đạt được.

Một thuật toán tìm kiếm đơn giản **bỏ qua mọi cạnh chẵn–chẵn** trong cùng cây có thể mắc kẹt ở 2 cặp trên đúng thứ tự input này; thuật toán Edmonds nhận được 3 cặp nhờ co và mở blossom.

## 7. Vì sao co blossom không làm mất đường tăng?

Đây là ý tưởng chứng minh then chốt của Edmonds.

Một blossom hợp lệ gồm chu trình lẻ luân phiên với một **đế**. Khi đường tăng ở graph co đi vào siêu đỉnh B và đi ra qua một cạnh khác, ta phải nối hai đầu vào/ra qua một **đoạn của chu trình blossom** sao cho chuỗi cạnh mới vẫn **luân phiên** và không dùng một đỉnh hai lần.

Vì chu trình có **số đỉnh lẻ**, có hai hướng đi quanh chu trình từ một vị trí đến đế. Với cấu hình matching của blossom, có thể chọn hướng **có tính chẵn/lẻ phù hợp** để lật đường tăng mà không vi phạm matching.

Nội dung của **định lý co blossom** là: với blossom hợp lệ, việc co giữ được câu hỏi **có đường tăng hay không** theo một cách có thể **mở/lift** đường tăng tìm được trở lại graph gốc. Co là thao tác đúng vì nó không bỏ mất nghiệm augmenting-path cần thiết.

**Không nhầm:** chu trình lẻ bất kỳ có thể không mang trạng thái matching phù hợp; nếu co nhầm chu trình, sẽ không có bảo đảm khôi phục đường tăng đúng.

### Blossom lồng nhau

Sau một lần co, một cạnh khác có thể hình thành một blossom **bao cả blossom đã co trước**. Bản cài đặt mảng sử dụng `base[v]` cho đế đại diện của thành phần đã co và cập nhật `parent`, `used` để biểu diễn trạng thái luân phiên sau co.

Nhiều tài liệu triển khai co bằng một đồ thị thực sự mới rồi lưu cấu trúc để mở lại. Mã Java của bài dùng **co ngầm bằng mảng base**, không cần tạo lại graph ở mỗi bước; đường tăng được mở thông qua các quan hệ cha đã được **sửa trong quá trình co**.

## 8. Các mảng trạng thái của Edmonds

Xét mã kiểu Edmonds kinh điển, tìm đường tăng qua BFS từ **một gốc tự do**:

| Mảng/trường | Ý nghĩa |
|---|---|
| `mate[v]` | Người ghép với v, hoặc -1 nếu tự do; lưu matching chung |
| `parent[v]` | Tiền nhiệm luân phiên trên đường tìm kiếm, được cập nhật khi co |
| `base[v]` | Đế đại diện của blossom hiện chứa v |
| `used[v]` | Trạng thái đã được xét/đưa vào queue như **vị trí chẵn** |
| `inBlossom[v]` | Đánh dấu các đế trên blossom mới tìm thấy |
| `queue` | Các vị trí chẵn cần mở rộng |
| `root` | Gốc tự do của một lần tìm đường tăng |

**Không được nhầm used với “tất cả đỉnh từng nhìn thấy”.** Đỉnh lẻ là trung gian trên một cạnh unmatched đi vào và cạnh matched đi ra; thông thường **mate của đỉnh lẻ** được đưa vào queue như một vị trí chẵn mới.

### Xử lý một cạnh v–u khi v ở vị trí chẵn

1. Nếu `base[v] == base[u]`, cạnh nằm **nội bộ cùng một blossom đã co** → bỏ qua.
2. Nếu `mate[v] == u`, cạnh v–u **đang ghép** của v → không dùng làm bước unmatched tiếp theo.
3. Nếu u là **root**, hoặc u là **vị trí chẵn đã tham gia cây luân phiên**, cạnh v–u có thể khép blossom; tìm **LCA của hai nhánh trong cây luân phiên**, đánh dấu và co.
4. Nếu u chưa có `parent[u]`, gán `parent[u]=v`. Nếu u **tự do**, đã tìm được đường tăng; nếu u **đã ghép**, đưa `mate[u]` vào hàng đợi chẵn.
5. Những trường hợp còn lại là cạnh không mở rộng trạng thái theo quy tắc trên.

Một điều kiện điển hình để nhận biết trường hợp (3) trong cách biểu diễn mảng này là:

~~~text
u == root
OR (mate[u] != -1 AND parent[mate[u]] != -1)
~~~

Điều kiện ấy chỉ đúng với **bất biến parent/mate/used cụ thể** của thuật toán bên dưới. Không được lấy một thuật toán BFS khác rồi thay “đã thăm u” bằng điều kiện này mà không chứng minh lại trạng thái chẵn/lẻ.

## 9. Tìm đế bằng LCA của cây luân phiên

Tìm LCA ở đây là tìm **điểm gặp của hai nhánh trong cây tìm kiếm luân phiên**, **không phải** LCA trên một cây gốc cố định của graph đầu vào.

Cho hai vị trí chẵn x,y. Từ mỗi phía, đi ngược theo chuỗi:

~~~text
a = base[a]
đánh dấu base a
nếu mate[a] == -1: đã tới gốc tự do
ngược lại: a = parent[mate[a]]
~~~

Bước `parent[mate[a]]` đi ngược **hai cạnh của đường luân phiên**: qua một cạnh ghép tới mate, rồi qua cạnh cha luân phiên tới vị trí chẵn cao hơn.

Đầu tiên ta đánh dấu toàn bộ base trên đường từ x lên gốc, sau đó lần ngược từ y cho tới khi gặp một base đã đánh dấu. Base gặp nhau là **đế blossom mới**.

### Đánh dấu và co

Với base b mới:

- Đi từ x lên b và từ y lên b, đánh dấu những base trên hai nhánh.
- Sửa `parent` ở các vị trí cần thiết để đường tăng có thể **đi qua blossom và được mở về sau**.
- Với đỉnh i nằm trong các base được đánh dấu, gán `base[i]=b`.
- Nếu có vị trí mới trở thành **chẵn có thể mở rộng**, đưa nó vào queue.

Matching hiện tại `mate` **chưa thay đổi** khi co. Chỉ khi gặp một đầu tự do khác, thuật toán mới lần ngược `parent` và `mate` để lật matching.

LCA/marking phải cẩn thận khi có **blossom đã co bên trong**; `base` đại diện cho toàn bộ tập đã co, không phải chỉ một đỉnh vật lý.

## 10. Thuật toán đầy đủ và các bất biến

Bắt đầu mọi `mate[v]=-1` rồi xét từng đỉnh tự do làm gốc BFS:

~~~text
EDMONDS_MAXIMUM_MATCHING(G):
    mate[all vertices] = -1

    for root in vertices:
        if mate[root] != -1:
            continue

        used[:] = false
        parent[:] = -1
        base[v] = v for all v

        queue = [root]
        used[root] = true

        while queue not empty:
            v = popFront(queue)
            for each neighbor u of v:
                if base[v] == base[u] or mate[v] == u:
                    continue

                if v--u closes an alternating odd blossom:
                    b = LCA_BASE(v,u)
                    markPath(v,b,u)
                    markPath(u,b,v)
                    contract bases to b
                    enqueue newly even vertices

                else if parent[u] == -1:
                    parent[u] = v

                    if mate[u] == -1:
                        FLIP_AUGMENTING_PATH_FROM(u)
                        stop this BFS successfully
                    else:
                        enqueue mate[u] as an even position

    return mate
~~~

**Matching invariant:** mỗi v có tối đa một mate và, nếu mate[v]=u, thì mate[u]=v.

**Search invariant:** queue chứa những vị trí chẵn đang có đường luân phiên từ gốc, trong biểu diễn có xét các blossom đã co. `parent` và `base` được duy trì để mọi đường tăng tìm thấy có thể khôi phục trong graph gốc.

**Augment invariant:** lần ngược từ đầu tự do mới tới root, lật cạnh matched/unmatched trên một đường tăng, nên số cặp tăng đúng 1.

**Termination:** khi không còn đường tăng cho bất kỳ gốc tự do nào, theo Berge matching là maximum. Một BFS có thể thất bại từ một gốc ngay cả khi matching chưa tối ưu ở những gốc khác; do đó phải tiếp tục các gốc tự do còn lại.

### Một gốc hay nhiều gốc?

Có phiên bản tìm đường tăng bằng **rừng BFS đa nguồn** từ nhiều đỉnh tự do: khi hai cây **khác gốc** gặp nhau, có thể tìm được đường tăng nối hai gốc; khi hai vị trí chẵn **cùng gốc** gặp nhau, xuất hiện blossom.

Mã Java ở phần sau dùng **BFS đơn gốc** cho từng đỉnh tự do, giúp việc nhận diện blossom và duy trì một cây luân phiên rõ ràng hơn. Không được trộn cơ chế gặp hai cây đa nguồn vào mã đơn gốc nếu chưa sửa bất biến.

## 11. Java 17+: Edmonds blossom cho maximum-cardinality matching

Mã sau là một chương trình hoàn chỉnh **GeneralMatchingBlossomDemo.java**:

- Đồ thị **vô hướng**, đỉnh `0..n-1`.
- Chấp nhận **chu trình lẻ**, graph không liên thông, đỉnh cô lập.
- Bỏ self-loop; cho phép cạnh song song dù có thể tối ưu bằng cách loại trùng.
- Dùng `mate=-1` cho đỉnh chưa ghép.
- BFS từ từng gốc tự do; khi gặp blossom thì tìm **LCA base**, đánh dấu `markPath`, cập nhật các `base` và queue.
- Khi tìm được đỉnh tự do khác, `flipAugmentingPath` lật cặp ghép dựa trên `parent/mate` đã cập nhật.
- `blossomEvents` chỉ để quan sát **số sự kiện co được thực hiện trong quá trình tìm kiếm**, không phải số chu trình lẻ của graph.
- In danh sách cặp theo ID đầu mút nhỏ hơn để kiểm thử kết quả.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class GeneralMatchingBlossomDemo {
    record Edge(int u, int v) {}

    record MatchingResult(
        int cardinality, int[] mate, int blossomEvents
    ) {
        List<String> pairs() {
            List<String> result = new ArrayList<>();
            for (int u = 0; u < mate.length; u++) {
                if (mate[u] > u) {
                    result.add(u + "-" + mate[u]);
                }
            }
            return List.copyOf(result);
        }

        int unmatchedVertices() {
            int result = 0;
            for (int partner : mate) {
                if (partner == -1) {
                    result++;
                }
            }
            return result;
        }

        boolean isPerfect() {
            return unmatchedVertices() == 0;
        }
    }

    static final class Matcher {
        final int n;
        final List<List<Integer>> graph;
        final int[] mate;
        final int[] parent;
        final int[] base;
        final boolean[] used;
        final boolean[] inBlossom;
        int blossomEvents = 0;

        Matcher(int n, List<Edge> edges) {
            Objects.requireNonNull(edges, "edges");
            if (n < 0) {
                throw new IllegalArgumentException(
                    "negative number of vertices"
                );
            }
            this.n = n;
            graph = new ArrayList<>();
            for (int v = 0; v < n; v++) {
                graph.add(new ArrayList<>());
            }

            for (Edge edge : edges) {
                if (edge == null || edge.u() < 0 || edge.u() >= n
                        || edge.v() < 0 || edge.v() >= n) {
                    throw new IllegalArgumentException(
                        "invalid edge endpoint"
                    );
                }
                if (edge.u() == edge.v()) {
                    continue; // Self-loop cannot match two vertices.
                }
                graph.get(edge.u()).add(edge.v());
                graph.get(edge.v()).add(edge.u());
            }

            mate = new int[n];
            parent = new int[n];
            base = new int[n];
            used = new boolean[n];
            inBlossom = new boolean[n];
            Arrays.fill(mate, -1);
        }

        // Lowest common base of two even search positions.
        private int lcaBase(int a, int b) {
            boolean[] seen = new boolean[n];

            while (true) {
                a = base[a];
                seen[a] = true;
                if (mate[a] == -1) {
                    break;
                }
                a = parent[mate[a]];
            }

            while (true) {
                b = base[b];
                if (seen[b]) {
                    return b;
                }
                b = parent[mate[b]];
            }
        }

        // Mark two alternating branches up to blossomBase.
        private void markPath(int v, int blossomBase, int child) {
            while (base[v] != blossomBase) {
                inBlossom[base[v]] = true;
                inBlossom[base[mate[v]]] = true;
                parent[v] = child;
                child = mate[v];
                v = parent[mate[v]];
            }
        }

        private void flipAugmentingPath(int endpoint) {
            int v = endpoint;
            while (v != -1) {
                int p = parent[v];
                int next = p == -1 ? -1 : mate[p];
                mate[v] = p;
                if (p != -1) {
                    mate[p] = v;
                }
                v = next;
            }
        }

        // BFS one alternating tree from an unmatched root.
        private boolean findAugmentingPath(int root) {
            Arrays.fill(used, false);
            Arrays.fill(parent, -1);
            for (int v = 0; v < n; v++) {
                base[v] = v;
            }

            ArrayDeque<Integer> queue = new ArrayDeque<>();
            used[root] = true;
            queue.add(root);

            while (!queue.isEmpty()) {
                int v = queue.remove();

                for (int u : graph.get(v)) {
                    // Ignore internal and currently matched edges.
                    if (base[v] == base[u] || mate[v] == u) {
                        continue;
                    }

                    // Even-even edge within this search tree.
                    if (u == root
                            || (mate[u] != -1
                                && parent[mate[u]] != -1)) {
                        int b = lcaBase(v, u);
                        Arrays.fill(inBlossom, false);
                        markPath(v, b, u);
                        markPath(u, b, v);
                        blossomEvents++;

                        for (int i = 0; i < n; i++) {
                            if (inBlossom[base[i]]) {
                                base[i] = b;
                                if (!used[i]) {
                                    used[i] = true;
                                    queue.add(i);
                                }
                            }
                        }
                    } else if (parent[u] == -1) {
                        parent[u] = v;

                        if (mate[u] == -1) {
                            flipAugmentingPath(u);
                            return true;
                        }

                        int w = mate[u];
                        used[w] = true;
                        queue.add(w);
                    }
                }
            }
            return false;
        }

        MatchingResult solve() {
            for (int root = 0; root < n; root++) {
                if (mate[root] == -1) {
                    findAugmentingPath(root);
                }
            }

            int cardinality = 0;
            for (int u = 0; u < n; u++) {
                if (mate[u] > u) {
                    cardinality++;
                }
            }
            return new MatchingResult(
                cardinality, mate.clone(), blossomEvents
            );
        }
    }

    static MatchingResult maximumMatching(
        int vertices, List<Edge> edges
    ) {
        return new Matcher(vertices, edges).solve();
    }

    static void printResult(String label, MatchingResult result) {
        System.out.println(label + ": size="
            + result.cardinality()
            + ", pairs=" + result.pairs()
            + ", unmatched=" + result.unmatchedVertices()
            + ", blossomEvents=" + result.blossomEvents());
    }

    public static void main(String[] args) {
        List<Edge> needsBlossom = List.of(
            new Edge(0, 1), new Edge(0, 3),
            new Edge(0, 4), new Edge(0, 5),
            new Edge(1, 2), new Edge(1, 3),
            new Edge(2, 3), new Edge(2, 4),
            new Edge(2, 5)
        );
        MatchingResult example =
            maximumMatching(6, needsBlossom);
        printResult("Blossom example", example);
        System.out.println("Blossom example perfect: "
            + example.isPerfect());

        MatchingResult triangle = maximumMatching(3, List.of(
            new Edge(0, 1),
            new Edge(1, 2),
            new Edge(2, 0)
        ));
        printResult("Triangle", triangle);

        MatchingResult fiveCycle = maximumMatching(5, List.of(
            new Edge(0, 1),
            new Edge(1, 2),
            new Edge(2, 3),
            new Edge(3, 4),
            new Edge(4, 0)
        ));
        printResult("Five-cycle", fiveCycle);

        MatchingResult bipartite = maximumMatching(6, List.of(
            new Edge(0, 3), new Edge(0, 4),
            new Edge(1, 3), new Edge(1, 5),
            new Edge(2, 4)
        ));
        printResult("Bipartite", bipartite);

        MatchingResult parallelLoops = maximumMatching(3, List.of(
            new Edge(0, 0),  // ignored self-loop
            new Edge(0, 1),
            new Edge(0, 1),  // parallel edge
            new Edge(1, 2)
        ));
        printResult("Parallel and loops", parallelLoops);

        MatchingResult isolated = maximumMatching(4, List.of());
        printResult("Four isolated", isolated);

        MatchingResult empty = maximumMatching(0, List.of());
        printResult("Empty graph", empty);

        try {
            maximumMatching(2, List.of(new Edge(0, 2)));
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid edge rejected: "
                + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac GeneralMatchingBlossomDemo.java
java GeneralMatchingBlossomDemo
~~~

**Stdout chính xác với dữ liệu mẫu và thứ tự khám phá nêu trên:**

~~~text
Blossom example: size=3, pairs=[0-5, 1-3, 2-4], unmatched=0, blossomEvents=1
Blossom example perfect: true
Triangle: size=1, pairs=[0-1], unmatched=1, blossomEvents=1
Five-cycle: size=2, pairs=[0-1, 2-3], unmatched=1, blossomEvents=1
Bipartite: size=3, pairs=[0-3, 1-5, 2-4], unmatched=0, blossomEvents=0
Parallel and loops: size=1, pairs=[0-1], unmatched=1, blossomEvents=0
Four isolated: size=0, pairs=[], unmatched=4, blossomEvents=0
Empty graph: size=0, pairs=[], unmatched=0, blossomEvents=0
Invalid edge rejected: invalid edge endpoint
~~~

### Giải thích các phần quan trọng của mã

**Dữ liệu graph:** mỗi cạnh vô hướng thêm vào danh sách kề của cả hai đầu. Self-loop bị bỏ; cạnh song song vẫn được duyệt, nhưng matching là cặp **đỉnh**, không phải số lượng bản sao cạnh.

**Tìm đường tăng:** `findAugmentingPath(root)` bắt đầu từ một đỉnh tự do, dựng BFS trên các vị trí chẵn. Đỉnh lẻ đã ghép dẫn sang mate để đưa vị trí chẵn tiếp theo vào queue.

**Nhận diện blossom:** khi `u==root` hoặc u thuộc vị trí chẵn đã có trong cây theo bất biến parent/mate, thuật toán tìm `lcaBase(v,u)`. Nó đánh dấu hai nhánh qua `markPath`, sửa parent để cho phép mở blossom, gán base chung và thêm những vị trí chẵn mới vào queue.

**Lật matching:** khi gặp đỉnh tự do ở cuối đường luân phiên, `flipAugmentingPath` lần ngược parent và mate. Nó lưu `next` **trước** khi đổi mate; nếu đổi mate quá sớm, có thể mất thông tin để đi tiếp về gốc.

**Bản sao matching:** result trả `mate.clone()`. Record Java vẫn chứa một mảng có thể bị sửa qua accessor, nên muốn API bất biến hoàn toàn trong thư viện thực tế cần thêm defensive copy khi đọc. Demo chỉ dùng result để in.

**Không dùng blossomEvents làm tiêu chí đúng:** có graph chứa tam giác nhưng một lần tìm kiếm không gặp blossom nào vì đường tăng kết thúc sớm. Có graph cần co nhiều lần trong cùng hoặc nhiều BFS. Chỉ tính **cardinality và tính hợp lệ** mới xác định chất lượng matching.

## 12. Chứng minh tính đúng của thuật toán

Có ba tầng chứng minh.

**Tầng 1 — Matching hợp lệ sau mỗi lần augment.** Matching ban đầu rỗng. Đường tăng là đường đơn luân phiên với hai đầu tự do. Lật cạnh trên đường tăng giữ mỗi đỉnh có đúng tối đa một mate và tăng cardinality đúng một đơn vị.

**Tầng 2 — Tìm kiếm không bỏ sót đường tăng.** Tìm đường tăng trong graph hai phía thường dựa trên cây luân phiên chẵn/lẻ. Đối với graph tổng quát, Edmonds xử lý riêng cạnh nối hai vị trí chẵn bằng **co blossom hợp lệ**. Định lý co blossom bảo toàn khả năng tồn tại đường tăng; thông tin base/parent cho phép mở/lift đường tìm được về các đỉnh gốc. Vì vậy một lần tìm kiếm đầy đủ từ gốc tự do có thể tìm được đường tăng nếu có đường tăng từ gốc đó theo matching hiện tại.

**Tầng 3 — Dừng đúng.** Nếu không thể tăng từ bất kỳ đỉnh tự do nào, không có đường tăng. Theo Berge, matching hiện tại maximum. Số lần tăng không vượt \(\lfloor n/2\rfloor\), vì mỗi lần thêm đúng một cạnh.

Trong ví dụ sáu đỉnh, sau hai lần augment, lần thứ ba **không thể** được suy ra chỉ từ thao tác “thêm một cạnh mới”. Co chu trình 5 đỉnh có base 4 giúp dựng đường tăng 4–2–3–1–0–5; lật cho một matching 3 cặp hợp lệ.

## 13. Độ phức tạp và lựa chọn thuật toán

Với graph **đơn** n đỉnh, m cạnh, phiên bản Edmonds blossom kiểu BFS cơ bản có cận thường dùng:

\[
\boxed{O(n^3)\text{ thời gian},\qquad O(n+m)\text{ bộ nhớ}.}
\]

Mỗi lần tìm kiếm quét các cạnh, xử lý trạng thái base, tìm LCA và co blossom. Vòng ngoài có nhiều nhất O(n) lần thử gốc; các phép xử lý mảng cho blossom chiếm O(n) trong từng thao tác. Mảng `mate/parent/base/used/inBlossom` cần O(n), adjacency list cần O(n+m).

**Graph có rất nhiều cạnh song song:** mã giữ nguyên các bản sao trong danh sách kề, nên chi phí quét phụ thuộc m thật. Cận O(n³) thường được nêu cho graph đơn hoặc sau khi **loại trùng cặp đầu mút** (khi chỉ tối đa số cặp). Với multigraph, cần kể chi phí m; cận bảo thủ có thể viết O(nm+n³) cho cách triển khai giản đơn.

So sánh:

| Bài toán | Thuật toán | Cận tiêu biểu |
|---|---|---|
| Matching số lượng trên graph hai phía | Kuhn DFS | O(VE) |
| Matching số lượng trên graph hai phía | Hopcroft–Karp | O(E√V) |
| Matching số lượng trên graph vô hướng tổng quát | Edmonds blossom cổ điển | O(V³) |
| Min-cost assignment hai phía | Hungarian | O(n³) với bảng chi phí vuông |
| Maximum-weight matching tổng quát | Weighted blossom/thuật toán chuyên biệt | Không phải mã không trọng số trong bài |

Nếu graph đã được chứng minh là hai phía, Hopcroft–Karp thường thích hợp hơn. Nếu graph có chu trình lẻ, các đường tăng đơn giản thiếu xử lý blossom **không còn đầy đủ**.

**Định lý Kőnig** — maximum matching size bằng minimum vertex cover size — chỉ đúng với graph **hai phía**. Trên tam giác, maximum matching size=1 nhưng minimum vertex cover size=2; không được dùng đẳng thức ấy để xác minh matching trên graph tổng quát.

## 14. Biên và lỗi thường gặp

| Trường hợp | Xử lý đúng |
|---|---|
| n=0 | Matching rỗng, size 0; theo quy ước logic mọi đỉnh được ghép một cách rỗng |
| n=1 không cạnh | Size 0; một đỉnh tự do |
| Cạnh đơn 0–1 | Size 1 |
| Tam giác | Size 1, không thể perfect |
| Chu trình lẻ 5 đỉnh | Size 2 |
| Chu trình chẵn 6 đỉnh | Có thể perfect size 3 |
| Clique n đỉnh | Size \(\lfloor n/2\rfloor\) |
| Đỉnh cô lập | Giữ `mate=-1` |
| Graph nhiều thành phần | Ghép độc lập trong từng thành phần |
| Self-loop | Bỏ qua, không là một cặp hợp lệ |
| Cạnh song song | Không tạo hai cặp giữa cùng hai đỉnh |
| Graph có trọng số | Nếu tối đa tổng trọng số, cần thuật toán khác |
| Nhiều matching optimum | Có thể trả bất kỳ matching hợp lệ có size tối đa |
| ID không thuộc 0..n-1 | Từ chối input |
| n lẻ | Không thể có perfect matching |

**Các bẫy cài đặt quan trọng:**

1. Nhầm **maximal** với **maximum**.
2. Không tìm đường tăng, chỉ ghép greedily.
3. Dùng thuật toán hai phía cho graph tổng quát có chu trình lẻ.
4. Bỏ qua mọi cạnh chẵn–chẵn trong cây luân phiên.
5. Xem cạnh chẵn–chẵn cùng gốc là đường tăng trực tiếp.
6. Co một chu trình lẻ **không có cấu trúc luân phiên** của matching hiện tại.
7. Lấy base là ID nhỏ nhất thay vì **đế theo cây tìm kiếm**.
8. Tìm LCA trên graph gốc thay vì cây BFS luân phiên.
9. Không lưu `base` nhất quán khi có blossom lồng nhau.
10. Quên sửa `parent` khi co, không thể mở đường tăng.
11. Gán `used=true` cho mọi đỉnh gặp mà quên phân biệt vị trí chẵn/lẻ.
12. Quên reset `used/parent/base` trước lần tìm đường tăng mới.
13. Reset luôn `mate` sau mỗi BFS, làm mất matching đã xây.
14. Chỉ cập nhật một phía `mate[u]=v`, quên `mate[v]=u`.
15. Lật đường tăng mà không lưu mate cũ trước khi sửa.
16. Không bỏ cạnh matching hiện tại khi xét bước unmatched từ đỉnh chẵn.
17. Quên kiểm tra self-loop hoặc cạnh vô hướng ở cả hai chiều.
18. Ép matching phải perfect dù graph không cho phép.
19. Đòi hai chương trình trả **cùng các cặp** khi có nhiều nghiệm tối ưu.
20. Dùng số sự kiện co blossom làm tiêu chí tối ưu, trong khi chỉ **augment** mới tăng size.
21. Cho rằng Hopcroft–Karp O(E√V) dùng được cho graph có tam giác.
22. Dùng blossom **không trọng số** cho bài tối đa hóa tổng trọng số.
23. Áp đẳng thức matching–vertex cover của Kőnig lên graph tổng quát.
24. Không đối chiếu với oracle độc lập trên các graph nhỏ nhiều blossom.
25. Không để ý số cặp tối đa luôn ≤floor(n/2).
26. Không kiểm `mate[mate[u]]==u` trên tất cả đỉnh đã ghép.

## 15. Kiểm thử độc lập bằng bitmask DP

Vì Edmonds co blossom có nhiều trạng thái tương tác, kiểm thử chỉ trên tam giác hay graph hai phía là chưa đủ. Với n nhỏ (thường n≤16–20 tùy bộ nhớ), có thể xây **oracle vét cạn có ghi nhớ theo bitmask**, độc lập hoàn toàn với BFS/blossom.

Gọi `opt(S)` là số cặp ghép lớn nhất trên các đỉnh còn xét thuộc tập S. Chọn đỉnh u thấp nhất trong S:

- **Không ghép u:** giá trị `opt(S\{u})`.
- **Ghép u với một v kề trong S:** giá trị `1+opt(S\{u,v})`.

Lấy lớn nhất:

\[
opt(S)=\max\left(
opt(S\setminus\{u\}),
\max_{\substack{v\in S\setminus\{u\}\\\{u,v\}\in E}}
[1+opt(S\setminus\{u,v\})]
\right).
\]

Với S rỗng, `opt(0)=0`. Oracle này có chi phí mũ, nhưng thích hợp để xác minh **size tối ưu** trên hàng trăm đồ thị nhỏ ngẫu nhiên.

Khi kiểm thử matching thuật toán trả:

1. `mate[u]` bằng -1 hoặc ID hợp lệ khác u.
2. Nếu `mate[u]=v`, phải có `mate[v]=u`.
3. Đôi u,v phải là cạnh có thật của graph.
4. Không đỉnh nào xuất hiện ở hơn một đôi.
5. `cardinality` bằng đúng số đôi.
6. `unmatched=n-2*cardinality`.
7. `cardinality==opt(V)` của oracle trên graph nhỏ.
8. Xáo trộn thứ tự cạnh: kết quả cụ thể có thể đổi nhưng size tối ưu không đổi.
9. Thử graph có tam giác, chu trình 5, graph hai phía, cạnh song song, self-loop, đỉnh cô lập và nhiều blossom lồng nhau.

Oracle tốt hơn việc so với một bộ matching mẫu duy nhất: trong graph có nhiều maximum matching, cặp đỉnh cụ thể có thể khác nhưng kích thước vẫn tối ưu.

## 16. Câu hỏi tự luyện

**Bài 1.** Trên đường 0–1–2–3, matching {(1,2)} là maximal hay maximum?

*Đáp án:* **Maximal nhưng không maximum**. Có thể ghép {(0,1),(2,3)} với 2 cạnh.

**Bài 2.** Đường tăng có 7 cạnh làm số cặp tăng bao nhiêu?

*Đáp án:* **Một**. Nó có bốn cạnh chưa ghép và ba cạnh đã ghép.

**Bài 3.** Không có cạnh nối trực tiếp hai đỉnh tự do đã chứng minh matching maximum chưa?

*Đáp án:* **Chưa**. Đường tăng có thể dài 3,5,... cạnh và đi qua các cặp đang ghép.

**Bài 4.** Khi nào matching maximum theo Berge?

*Đáp án:* Khi **không tồn tại đường tăng** đối với matching hiện tại.

**Bài 5.** Maximum matching trên tam giác có bao nhiêu cạnh?

*Đáp án:* **1**, vì tam giác chỉ có ba đỉnh.

**Bài 6.** Maximum matching trên chu trình 5 đỉnh có bao nhiêu cạnh?

*Đáp án:* **2**, còn một đỉnh tự do.

**Bài 7.** Trong graph sáu đỉnh của bài, sau M={(0,1),(2,3)}, gốc tự do dùng để tìm thêm đường tăng là gì?

*Đáp án:* **4**. Đỉnh tự do còn lại là **5**.

**Bài 8.** Blossom lẻ xuất hiện khi xét cạnh 1–3 trên cây luân phiên gốc 4 là chu trình nào?

*Đáp án:* **4–0–1–3–2–4**, gồm năm cạnh luân phiên; base là **4**.

**Bài 9.** Một đường tăng từ 4 tới 5 trong ví dụ là gì?

*Đáp án:* **4–2–3–1–0–5**, lật được {(2,4),(1,3),(0,5)}.

**Bài 10.** Khi co blossom, kích thước matching đã tăng chưa?

*Đáp án:* **Chưa**. Co chỉ thay biểu diễn tìm kiếm; khi lật **đường tăng** mới tăng size.

**Bài 11.** LCA dùng để tìm base blossom là LCA của cây nào?

*Đáp án:* Của **cây luân phiên BFS hiện tại**, có xét các base đã co, không phải cây gốc tùy ý của graph.

**Bài 12.** Vì sao Hopcroft–Karp không cần co blossom?

*Đáp án:* Vì graph hai phía **không có chu trình lẻ**.

**Bài 13.** Graph có một tam giác và một cạnh độc lập, thêm hai đỉnh cô lập. Matching maximum bao nhiêu cạnh?

*Đáp án:* **2**, một cạnh từ tam giác và cạnh độc lập.

**Bài 14.** Graph có 9 đỉnh có thể có 5 cạnh ghép không?

*Đáp án:* **Không**. Mỗi cạnh dùng hai đỉnh, nên tối đa floor(9/2)=4.

**Bài 15.** Hai cạnh song song 0–1 có cho hai cặp ghép khác nhau cùng lúc không?

*Đáp án:* **Không**, cả hai dùng chung hai đỉnh.

**Bài 16.** Self-loop 2–2 có là cạnh của matching theo nghĩa ghép hai đỉnh phân biệt không?

*Đáp án:* **Không**, bản mã bỏ self-loop.

**Bài 17.** Edmonds blossom không trọng số tối ưu tổng trọng số ghép cặp được không?

*Đáp án:* **Không bảo đảm**. Nó chỉ tối đa **số cạnh**; bài có trọng số cần thuật toán riêng.

**Bài 18.** Cách kiểm tra tối ưu độc lập cho graph n rất nhỏ là gì?

*Đáp án:* **Bitmask DP/vét cạn**, thử bỏ một đỉnh không ghép hoặc ghép nó với một hàng xóm còn lại, rồi lấy max.

**Tổng kết:** Matching maximum trên **đồ thị vô hướng tổng quát** dựa vào **định lý Berge** và việc tìm **đường tăng**. Chu trình lẻ luân phiên (**blossom**) phát sinh khi các nhánh chẵn của một cây tìm kiếm gặp nhau; chỉ dùng BFS hai phía có thể bỏ sót đường tăng. Edmonds tìm **base**, **co blossom**, tiếp tục tìm kiếm và **mở** đường tăng trên đỉnh gốc để lật matching. Cài đặt Java 17 minh họa ghép cặp hoàn hảo 3 cạnh nhờ một lần co blossom, hỗ trợ graph không liên thông, tam giác, chu trình lẻ, self-loop và cạnh song song. Với đồ thị đơn, phiên bản cổ điển thường có cận **O(V³)**.