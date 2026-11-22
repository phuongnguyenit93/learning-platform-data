# Các thành phần song liên thông

**Các thành phần song liên thông (biconnected components)** mô tả những miền của đồ thị vô hướng có tính liên kết “bền vững” trước sự cố mất **một đỉnh** hoặc mất **một cạnh**. Chúng là công cụ nền tảng để phân tích **đỉnh khớp (articulation point)**, **cạnh cầu (bridge)**, tổ chức cấu trúc **block-cut tree/forest**, tìm các vùng dự phòng trong mạng và rút gọn đồ thị cho những bài toán tiếp theo.

Cần phân biệt ngay hai khái niệm thường cùng được gọi ngắn gọn là “song liên thông”:

1. **Song liên thông theo đỉnh (vertex-biconnected components, V-BCC, các khối/blocks):** phân rã đồ thị thành những **khối cực đại không có đỉnh khớp bên trong khối**. Các khối có thể **chung một đỉnh khớp**, nhưng **không chung cạnh**. Trong quy ước chuẩn về block decomposition, một cạnh cầu tạo thành **một khối hai đỉnh K₂**, còn đỉnh cô lập được xem là **khối đơn đỉnh**.
2. **Song liên thông theo cạnh (edge-biconnected components, E-BCC hay 2-edge-connected components):** những nhóm đỉnh còn liên thông sau khi **bỏ tất cả các cầu**. Mỗi đỉnh thuộc **đúng một** nhóm; các nhóm là những thành phần liên thông của đồ thị thu được sau khi xóa cầu.

Bài học tập trung vào **V-BCC theo thuật toán DFS Tarjan với ngăn xếp cạnh**, đồng thời tính đỉnh khớp, cầu và E-BCC để tránh nhầm lẫn. Bao gồm định nghĩa, chứng minh bằng `tin/low`, ví dụ duyệt tay, chương trình **Java 17+** chạy được, trường hợp đồ thị rời rạc, K₂, đỉnh cô lập, phân tích O(V+E) và ứng dụng block-cut forest.

## 1. Phân biệt liên thông, đỉnh khớp và cầu

Cho đồ thị vô hướng `G=(V,E)`, trong đó một cạnh `{u,v}` đi được theo cả hai chiều. **Thành phần liên thông** là nhóm đỉnh cực đại mà mỗi cặp đỉnh trong nhóm có một đường đi nối chúng.

**Đỉnh khớp** là đỉnh x mà khi **xóa x cùng các cạnh kề x**, số thành phần liên thông của đồ thị **tăng lên**. Ví dụ đường:

~~~text
0 -- 1 -- 2
~~~

Đỉnh 1 là đỉnh khớp: xóa 1 khiến 0 và 2 tách rời. Hai đầu mút 0, 2 không phải đỉnh khớp: xóa một đầu không làm số thành phần tăng.

**Cầu** là cạnh e mà khi **xóa e**, số thành phần liên thông của đồ thị **tăng lên**. Trong đường 0–1–2, cả hai cạnh đều là cầu. Ngược lại, các cạnh của một chu trình đơn **không phải cầu**, vì xóa một cạnh vẫn còn đường khác nối hai đầu.

~~~text
0 -- 1
|    |
3 -- 2
~~~

Bốn cạnh của chu trình trên không phải cầu; cũng không có đỉnh khớp vì sau khi xóa một đỉnh, ba đỉnh còn lại vẫn nối được thành đường.

### Phân biệt “bền trước mất đỉnh” và “bền trước mất cạnh”

Nếu mạng vẫn liên thông sau khi mất **bất kỳ một cạnh nào**, mạng không có cầu. Điều này **không bảo đảm** mất bất kỳ một đỉnh nào mạng vẫn liên thông. Ví dụ hai tam giác chỉ chung đúng đỉnh 0:

~~~text
Tam giác trái:  0-1, 1-2, 2-0
Tam giác phải: 0-3, 3-4, 4-0
~~~

Không cạnh nào là cầu, vì mỗi cạnh nằm trên một chu trình. Nhưng **0 là đỉnh khớp**: bỏ 0 tách nhóm {1,2} khỏi nhóm {3,4}.

Do đó, phân rã thành V-BCC sẽ có **hai khối** `{0,1,2}` và `{0,3,4}`; phân rã E-BCC lại cho **một nhóm duy nhất** `{0,1,2,3,4}`. Đây là phản ví dụ quan trọng nhất khi dùng thuật ngữ “song liên thông” không nói rõ theo đỉnh hay cạnh.

## 2. Định nghĩa khối song liên thông theo đỉnh

Một **block** của đồ thị vô hướng là một đồ thị con **liên thông cực đại** không chứa **đỉnh khớp của chính đồ thị con ấy**. Theo quy ước block decomposition:

- Một chu trình và những cạnh nối bên trong cùng vùng bền theo đỉnh có thể thuộc cùng một block lớn.
- **Mỗi cạnh cầu** tạo ra một block chỉ gồm **hai đầu mút và cạnh ấy**.
- Một **đỉnh cô lập** tạo thành block chỉ có đỉnh đó.
- Những block khác nhau có thể cùng có một **đỉnh khớp của đồ thị gốc**, nhưng không thể chia sẻ cả một cạnh hoặc hai đỉnh khác nhau trong một đồ thị đơn thông thường.

Trong một thành phần liên thông đủ lớn, block có ít nhất 3 đỉnh tương ứng vùng **2-vertex-connected**: xóa bất kỳ một đỉnh trong block, phần còn lại vẫn liên thông. Tuy nhiên, có **khác biệt quy ước**:

- Một số sách định nghĩa đồ thị “2-đỉnh-liên-thông” chỉ khi có **ít nhất 3 đỉnh** và tồn tại **hai đường đi độc lập theo đỉnh bên trong** giữa mọi cặp đỉnh.
- **K₂** (hai đỉnh với một cạnh) không đáp ứng yêu cầu nghiêm ngặt “ít nhất 3 đỉnh”, nhưng vẫn là **một block hợp lệ** trong phép phân rã thành blocks.
- Đỉnh đơn cũng được giữ như một block đặc biệt để mô tả đầy đủ đồ thị rời rạc; một số bài chỉ liệt kê các block có ít nhất một cạnh và do đó không in các đỉnh cô lập.

**Hãy kiểm tra quy ước đầu ra của đề.** Trong bài học và chương trình Java bên dưới, ta **gồm cả K₂ và đỉnh cô lập**, như vậy không bỏ sót phần nào của đồ thị.

### Phân hoạch cạnh, không phân hoạch đỉnh

Trong phân rã V-BCC, **mỗi cạnh thuộc đúng một block**. Nhưng một **đỉnh khớp** có thể xuất hiện trong **nhiều block**.

Ví dụ đồ thị hai tam giác chung đỉnh 0:

~~~text
Block A: {0,1,2}
Block B: {0,3,4}
~~~

Đỉnh 0 có mặt trong cả hai block, không phải lỗi đếm trùng. Hai block không chung cạnh. Nếu một bài yêu cầu danh sách đỉnh cho mỗi V-BCC, không được xóa đỉnh 0 khỏi một trong hai danh sách.

Trong phân rã E-BCC, ta xóa mọi cầu rồi lấy thành phần liên thông: các nhóm đỉnh **không giao nhau**, và mỗi đỉnh thuộc một nhóm duy nhất. Sự khác biệt này quyết định cấu trúc dữ liệu trả kết quả.

## 3. Một ví dụ gồm chu trình, cầu và đỉnh cô lập

Xét đồ thị có 8 đỉnh `0..7` và các cạnh:

~~~text
Tam giác A: (0,1), (1,2), (2,0)
Cầu nối:   (1,3)
Tam giác B: (3,4), (4,5), (5,3)
Cầu treo:  (4,6)
Đỉnh 7:    không có cạnh
~~~

Đồ thị có hai tam giác, nối nhau bằng cạnh 1–3; đỉnh 6 treo ở 4 và đỉnh 7 cô lập.

**Các block theo đỉnh (V-BCC)**, viết danh sách đỉnh theo thứ tự tăng:

~~~text
[0,1,2]   // Tam giác A.
[1,3]     // Cạnh cầu 1-3 được tính là block K₂.
[3,4,5]   // Tam giác B.
[4,6]     // Cạnh cầu 4-6 được tính là block K₂.
[7]       // Đỉnh cô lập là singleton block.
~~~

**Các đỉnh khớp:** `[1,3,4]`. Xóa 1 tách tam giác A khỏi phần còn lại của cùng thành phần; xóa 3 tách phần nối sang tam giác B; xóa 4 tách đỉnh 6.

**Các cầu:** `[(1,3),(4,6)]`. Mọi cạnh thuộc hai tam giác đều có đường vòng thay thế nên không là cầu.

**Các nhóm E-BCC**, sau khi xóa hai cầu:

~~~text
[0,1,2]
[3,4,5]
[6]
[7]
~~~

Chú ý đỉnh khớp 1 có thể ở cả block tam giác A và block cạnh (1,3), trong khi ở E-BCC nó chỉ nằm trong nhóm [0,1,2].

### Kết quả không nhất thiết là các chu trình riêng

Nếu hai chu trình có **cùng một cạnh** hoặc có nhiều đường bổ sung kết nối làm không có đỉnh khớp nội bộ, chúng có thể thuộc **cùng một block**. Không phải “mỗi chu trình là một thành phần”. Ngược lại, hai chu trình chỉ gặp ở **một đỉnh khớp** tạo hai block khác nhau.

Ví dụ hai chu trình tam giác chia sẻ cạnh 1–2 và còn có đường nối giữa các đỉnh thích hợp: một khối có thể chứa cả hai tam giác, không chia đơn giản theo số chu trình.

## 4. DFS và thời điểm thăm `tin`

Ta dùng DFS (duyệt theo chiều sâu). Mỗi đỉnh u được gán:

- `tin[u]` hoặc `disc[u]`: thời điểm DFS **phát hiện lần đầu** u, mỗi đỉnh một giá trị khác nhau.
- `low[u]`: thời điểm phát hiện nhỏ nhất của tổ tiên mà cây con gốc u có thể “vươn tới” bằng những cạnh cây DFS đi xuống và **tối đa một cạnh ngược (back edge)** đi lên.
- `parentEdge`: ID cạnh cây DFS dùng để đến u; bỏ qua chính cạnh này khi xét các cạnh kề u.

Với đồ thị vô hướng và DFS, khi gặp một đỉnh v đã thăm qua cạnh không phải cạnh cha, ta thường gặp một **tổ tiên** (back edge) hoặc một đỉnh đã xử lý theo chiều hậu duệ; ta chỉ cần cập nhật `low` và đẩy cạnh khi `tin[v]<tin[u]`, tức v là tổ tiên của u trong cây DFS.

Công thức:

~~~text
low[u] = min(
    tin[u],
    tin[v]  với mọi cạnh ngược u-v tới tổ tiên v,
    low[child] với mọi con child của u trong cây DFS
)
~~~

**Không nhầm `low` với khoảng cách ngắn nhất.** `tin` là số thứ tự phát hiện, không phải độ dài đường đi; `low` mô tả khả năng kết nối ngược về tổ tiên để phát hiện sự phụ thuộc vào đỉnh/cạnh.

### Ví dụ tam giác

DFS đi 0→1→2 trên tam giác 0–1–2–0. Gán:

~~~text
tin[0]=1, tin[1]=2, tin[2]=3

Cạnh ngược 2-0:
low[2]=min(tin[2],tin[0])=1
low[1]=min(tin[1],low[2])=1
low[0]=min(tin[0],low[1])=1
~~~

Cạnh cây 0–1 không phải cầu vì `low[1]=1` **không lớn hơn** `tin[0]=1`: cây con của 1 còn đường về 0 qua cạnh 2–0. Tương tự 1–2 không phải cầu vì `low[2]=1<tin[1]=2`.

## 5. Hai bất đẳng thức quan trọng: đỉnh khớp và cầu

Giả sử DFS duyệt **cạnh cây** `u→v`, trong đó u là cha và v là con.

### Cầu: điều kiện nghiêm ngặt

`(u,v)` là **cầu** khi:

`low[v] > tin[u]`

Vì sao? Không có cạnh ngược nào từ cây con v tới u hoặc tổ tiên của u để “đi vòng” qua cạnh cây (u,v). Nếu bỏ cạnh này, cây con v bị tách khỏi phần còn lại.

Nếu `low[v]==tin[u]`, cây con vẫn có đường trở lại **chính u** bằng một cạnh ngược, nên cạnh cây không phải cầu. Vì vậy dấu **lớn hơn nghiêm ngặt** rất quan trọng.

### Đỉnh khớp không phải gốc

Với u **không là gốc DFS**, nếu tồn tại một con v sao cho:

`low[v] >= tin[u]`

thì u là **đỉnh khớp**. Cây con v không có đường đi ngược tới **tổ tiên của u** mà tránh u. Khi xóa u, vùng cây con v sẽ không thể nối ra phía trên bằng cạnh khác.

Dấu ở đây là **lớn hơn hoặc bằng**. Nếu `low[v]==tin[u]`, cây con còn nối ngược về u nhưng **không vượt qua u** tới tổ tiên; khi xóa u, kết nối đó cũng mất. Vậy u vẫn là đỉnh khớp.

### Gốc DFS: ngoại lệ phải xử lý riêng

Một **gốc r** của cây DFS có thể không có cha. Gốc là **đỉnh khớp khi và chỉ khi có ít nhất hai con trực tiếp trong cây DFS**.

- Nếu gốc chỉ có một con, xóa gốc không tách các nhánh DFS độc lập của cùng thành phần.
- Nếu có hai con trực tiếp, các cây con này không có cạnh nối với nhau qua một back edge ngang trong DFS vô hướng; xóa gốc làm chúng tách nhau.

**Không áp dụng điều kiện “có một con low[child] >= tin[root]” để kết luận gốc là đỉnh khớp.** Với gốc, ngay cả một chu trình có thể thỏa bất đẳng thức đó nhưng gốc không phải đỉnh khớp.

### So sánh ba điều kiện

| Mục đích | Điều kiện | Ý nghĩa |
| --- | --- | --- |
| Cầu `(u,v)` | `low[v] > tin[u]` | Cây con v không quay lại được cả u hoặc tổ tiên u. |
| Đỉnh khớp u không phải gốc | Có con v: `low[v] >= tin[u]` | Cây con v không vượt được u để đến tổ tiên u. |
| Đỉnh khớp r là gốc DFS | Có ít nhất **2 con DFS** | Các cây con của gốc bị chia khi xóa gốc. |

Các điều kiện trên xuất phát từ cùng một mảng `low`, nhưng **không được hoán đổi dấu hoặc ngoại lệ gốc**.

## 6. Vì sao cần ngăn xếp CẠNH để tìm V-BCC?

Chỉ tính `tin/low` cho biết đâu là đỉnh khớp hoặc cầu. Nhưng để **trả ra các block**, cần biết **những cạnh nào nằm chung một block**. Cách chuẩn là duy trì **ngăn xếp ID cạnh (edge stack)** khi DFS.

Quy tắc:

1. Khi DFS đi theo một **cạnh cây u–v** tới v chưa thăm, **đẩy cạnh** ấy vào stack trước khi đệ quy.
2. Khi gặp một **cạnh ngược u–v tới tổ tiên v** với `tin[v]<tin[u]`, cũng **đẩy cạnh** vào stack và cập nhật `low[u]`.
3. Sau khi xử lý xong con v, cập nhật `low[u]` bằng `low[v]`.
4. Nếu `low[v]>=tin[u]`, các cạnh của **một block** đã hoàn tất: **lấy ra liên tiếp khỏi stack** đến và bao gồm cạnh cây `u–v`.
5. Từ các cạnh vừa lấy, hợp các đầu mút thành tập đỉnh của block.

**Lưu ý:** điều kiện **tách block** `low[v]>=tin[u]` áp dụng **kể cả khi u là gốc DFS có đúng một con**. Nó **không** tự động biến u thành đỉnh khớp; việc đánh dấu gốc vẫn dựa số con. Đây là phân biệt dễ sai: điều kiện đóng block và điều kiện đánh dấu articulation cho root **không giống nhau**.

### Mô phỏng stack ở ví dụ 8 đỉnh

Giả sử thêm cạnh theo thứ tự:

~~~text
e0=(0,1), e1=(1,2), e2=(2,0), e3=(1,3)
e4=(3,4), e5=(4,5), e6=(5,3), e7=(4,6)
~~~

DFS đi theo các cạnh từ 0:

~~~text
0 -> 1 -> 2, gặp back edge 2-0
1 -> 3 -> 4 -> 5, gặp back edge 5-3
4 -> 6
~~~

Với thứ tự phát hiện lần lượt 0,1,2,3,4,5,6,7:

~~~text
tin: [1,2,3,4,5,6,7,8]
low: [1,1,1,4,4,4,7,8]
~~~

Khi từ 6 quay về 4: `low[6]=7>=tin[4]=5`. Pop cạnh `e7=(4,6)`, được block `{4,6}`. Vì `low[6]>tin[4]`, e7 cũng là **cầu**.

Khi từ 4 quay về 3: `low[4]=4>=tin[3]=4`. Pop các cạnh trên đỉnh stack đến `e4=(3,4)`, thu block `{3,4,5}`. Do `low[4]==tin[3]` nên **e4 không phải cầu**: có đường trở lại 3 qua 5–3.

Khi từ 3 quay về 1: `low[3]=4>=tin[1]=2`. Pop `e3=(1,3)` thành block `{1,3}`; đây là cầu.

Khi từ 1 quay về gốc 0: `low[1]=1>=tin[0]=1`. Pop các cạnh còn lại của tam giác A, được `{0,1,2}`. Gốc 0 chỉ có **một con DFS** nên **không phải đỉnh khớp**.

Đỉnh 7 không có cạnh; tự ghi một block đơn đỉnh `{7}` theo quy ước bài học.

### Vì sao dùng ID cạnh thay vì chỉ đỉnh?

Các block được tách ra theo **cạnh**. Nếu chỉ dùng stack đỉnh và pop theo điều kiện không phù hợp, rất dễ bỏ sót cạnh cầu hoặc gộp nhầm các khối có cùng đỉnh khớp. ID cạnh cho phép “pop tới đúng cạnh cây u–v” và tránh nhầm lẫn khi chương trình mở rộng để xử lý **cạnh song song**.

Chương trình Java bên dưới chỉ nhận **đồ thị đơn vô hướng**: không khuyên và không cạnh lặp, để đặc tả và đầu ra nhất quán. Dù vậy, nó vẫn dùng ID cạnh và `parentEdge` — thiết kế cũng phù hợp làm nền tảng khi xử lý multigraph, nếu bổ sung quy tắc xét khuyên và cạnh song song rõ ràng.

## 7. Giả mã Tarjan cho đỉnh khớp, cầu và block

~~~text
ALGORITHM FIND_VERTEX_BICONNECTED_BLOCKS(G)
    REQUIRE G is a simple undirected graph

    tin[u] <- 0 for every vertex u  // 0 means unvisited
    low[u] <- 0
    isArticulation[u] <- false
    isBridge[edgeId] <- false
    edgeStack <- empty
    timer <- 0
    blocks <- empty

    PROCEDURE DFS(u, parentEdgeId)
        timer <- timer + 1
        tin[u] <- low[u] <- timer
        childCount <- 0

        FOR EACH incident edge id from u DO
            IF id = parentEdgeId THEN CONTINUE END IF
            v <- other endpoint of edge id

            IF tin[v] = 0 THEN
                childCount <- childCount + 1
                PUSH(edgeStack, id)
                DFS(v, id)
                low[u] <- min(low[u], low[v])

                IF low[v] >= tin[u] THEN
                    IF parentEdgeId != NONE THEN
                        isArticulation[u] <- true
                    END IF
                    POP_EDGES_THROUGH(id) AS NEW BLOCK
                END IF

                IF low[v] > tin[u] THEN
                    isBridge[id] <- true
                END IF

            ELSE IF tin[v] < tin[u] THEN
                low[u] <- min(low[u], tin[v])
                PUSH(edgeStack, id)   // Back edge to ancestor.
            END IF
        END FOR

        IF parentEdgeId = NONE AND childCount > 1 THEN
            isArticulation[u] <- true
        END IF
    END PROCEDURE

    FOR u FROM 0 TO V-1 DO
        IF tin[u] = 0 THEN
            DFS(u, NONE)
            IF u is isolated THEN
                ADD singleton block {u}
            END IF
        END IF
    END FOR

    RETURN blocks, articulation vertices, bridge edges
END ALGORITHM
~~~

Tại mỗi phép pop, lấy ít nhất một cạnh, gom các đầu mút thành một tập đỉnh. **Không** pop một phần tùy ý; phải pop cho đến **đúng ID cạnh cây** đã mở nhánh DFS ấy.

Nếu đồ thị có nhiều thành phần liên thông, vòng ngoài phải chạy DFS mới ở từng đỉnh chưa thăm. Đỉnh cô lập không có cạnh để đẩy vào stack, nên phải xử lý singleton nếu đầu ra bao gồm chúng.

### Các bất biến khi cài đặt

- `tin[u]!=0` đúng khi u đã được phát hiện; mỗi đỉnh được gán tin một lần.
- Với mỗi u đã xử lý xong, `low[u]` là mốc thời gian nhỏ nhất có thể quay ngược tới từ cây con u theo định nghĩa.
- Mỗi **cạnh cây** được đẩy đúng khi phát hiện con; mỗi **cạnh ngược tới tổ tiên** được đẩy đúng một lần từ đầu sâu hơn.
- Các cạnh đã pop thuộc một block hoàn chỉnh và **không xuất hiện trong block khác**.
- Sau khi DFS kết thúc một thành phần liên thông, edge stack phải rỗng với đồ thị đơn và cách tách blocks này.

### Phác thảo chứng minh tính đúng của tách block

Trong cây DFS của đồ thị vô hướng, nếu `low[v]<tin[u]` thì cây con v còn đường ngược vượt qua u tới tổ tiên của u; cạnh cây u–v chưa thể đóng thành một block riêng tại u vì vẫn có chu trình gắn với những cạnh cao hơn trong stack.

Ngược lại, khi `low[v]>=tin[u]`, mọi cạnh đang nằm trên stack thuộc phần DFS của v và phụ thuộc vào u như ranh giới để nối lên trên. Không có back edge nào từ cây con v tới một tổ tiên thực sự của u. Những cạnh từ lúc đi vào nhánh u–v cho tới khi quay về tạo **một khối tối đa** có thể pop ở thời điểm đó. Cạnh cây u–v chính là mốc phân giới nên không lấy lẫn cạnh từ phần DFS bên trên u.

Quá trình này áp dụng tại mọi cạnh cây, kết hợp với các cạnh ngược đã được đẩy đúng một lần. Do đó mọi cạnh thuộc đúng một block. Các đỉnh đầu mút có thể xuất hiện nhiều lần qua các block (đặc biệt articulation), đúng với đặc tả của V-BCC.

## 8. E-BCC: loại cầu rồi lấy thành phần liên thông

Nếu yêu cầu **song liên thông theo cạnh**, cách triển khai rất trực tiếp sau khi đã tìm được `isBridge[e]`:

1. Đánh dấu toàn bộ cầu bằng điều kiện `low[v]>tin[u]` ở mỗi cạnh cây DFS.
2. Duyệt lại đồ thị bằng DFS hoặc BFS, nhưng **không đi qua cạnh được đánh dấu là cầu**.
3. Tập đỉnh tìm được trong mỗi lượt là một **E-BCC**.

~~~text
visited[u] <- false for every vertex

FOR each vertex s DO
    IF visited[s] THEN CONTINUE END IF
    component <- empty
    queue <- [s]
    visited[s] <- true

    WHILE queue not empty DO
        u <- popFront(queue)
        add u to component

        FOR EACH edge id incident to u DO
            IF isBridge[id] THEN CONTINUE END IF
            v <- other endpoint of id
            IF not visited[v] THEN
                visited[v] <- true
                pushBack(queue,v)
            END IF
        END FOR
    END WHILE

    OUTPUT component
END FOR
~~~

**Vì sao đúng?** Nếu một cạnh là cầu, bất kỳ đường nào nối hai phía của nó phải đi qua cầu ấy, nên nó không thể nằm trong một vùng không có cầu. Khi bỏ tất cả cầu, những đỉnh còn nối với nhau bởi các đường hoàn toàn không dùng cầu thuộc cùng một nhóm tối đa. Các nhóm này **phân hoạch tập đỉnh**.

Cách này **không cho V-BCC**. Đồ thị hai tam giác chung đỉnh không có cầu, nên E-BCC coi cả hai tam giác là một nhóm, trong khi V-BCC tách thành hai block tại đỉnh khớp.

## 9. Java 17+: phân rã hai loại thành phần, đỉnh khớp và cầu

Chương trình đầy đủ dùng **Java 17 records** để biểu diễn cạnh và báo cáo. Đầu vào là số đỉnh `n>=0` và danh sách các cạnh vô hướng, mỗi cạnh là mảng `{u,v}`.

**Phạm vi của API:** đồ thị **đơn, vô hướng**, không có khuyên `u=u`, không có cạnh trùng `{u,v}`. Nếu thấy khuyên/cạnh trùng, chương trình ném `IllegalArgumentException` thay vì âm thầm dùng logic ngoài đặc tả. Một đồ thị có n=0 và danh sách cạnh rỗng được phép; kết quả không có block.

Để đầu ra ổn định, chương trình **sắp các đỉnh trong mỗi block**, và sắp danh sách blocks theo thứ tự từ điển. Phần tìm kiếm DFS Tarjan bản chất chạy tuyến tính O(V+E); **bước sắp kết quả để in ổn định là chi phí phụ**, không nên gộp thành khẳng định toàn bộ chương trình chỉ O(V+E) trong mọi cách trình bày.

Tạo tệp **`BiconnectedComponentsDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.Set;
import java.util.TreeSet;

public class BiconnectedComponentsDemo {
    record Edge(int u, int v) {
        int other(int x) {
            return x == u ? v : u;
        }
    }

    record Report(
            List<List<Integer>> blocks,
            List<Integer> articulations,
            List<List<Integer>> bridges,
            List<List<Integer>> edgeComponents) {}

    static final class Graph {
        final int n;
        final List<Edge> edges = new ArrayList<>();
        final List<List<Integer>> adjacency = new ArrayList<>();

        Graph(int n, int[][] inputEdges) {
            Objects.requireNonNull(inputEdges, "inputEdges");
            if (n < 0) {
                throw new IllegalArgumentException("Negative n");
            }
            this.n = n;
            for (int u = 0; u < n; u++) {
                adjacency.add(new ArrayList<>());
            }

            Set<Long> seen = new HashSet<>();
            for (int[] pair : inputEdges) {
                if (pair == null || pair.length != 2) {
                    throw new IllegalArgumentException("Invalid edge");
                }
                int u = pair[0];
                int v = pair[1];
                if (u < 0 || v < 0 || u >= n || v >= n || u == v) {
                    throw new IllegalArgumentException(
                            "Endpoint out of range or self-loop");
                }

                int a = Math.min(u, v);
                int b = Math.max(u, v);
                long key = ((long) a << 32) | (b & 0xffffffffL);
                if (!seen.add(key)) {
                    throw new IllegalArgumentException(
                            "Parallel edge not supported");
                }

                int id = edges.size();
                edges.add(new Edge(u, v));
                adjacency.get(u).add(id);
                adjacency.get(v).add(id);
            }
        }
    }

    private static int compareIntLists(
            List<Integer> a, List<Integer> b) {
        int limit = Math.min(a.size(), b.size());
        for (int i = 0; i < limit; i++) {
            int cmp = Integer.compare(a.get(i), b.get(i));
            if (cmp != 0) {
                return cmp;
            }
        }
        return Integer.compare(a.size(), b.size());
    }

    private static void normalize(List<List<Integer>> comps) {
        for (List<Integer> comp : comps) {
            Collections.sort(comp);
        }
        comps.sort(BiconnectedComponentsDemo::compareIntLists);
    }

    static final class Analyzer {
        final Graph g;
        final int[] tin;
        final int[] low;
        final boolean[] isArticulation;
        final boolean[] isBridge;
        final Deque<Integer> edgeStack = new ArrayDeque<>();
        final List<List<Integer>> vertexBlocks = new ArrayList<>();
        int timer = 0;

        Analyzer(Graph g) {
            this.g = g;
            tin = new int[g.n];
            low = new int[g.n];
            isArticulation = new boolean[g.n];
            isBridge = new boolean[g.edges.size()];
        }

        private void popBlock(int stopEdgeId) {
            TreeSet<Integer> vertices = new TreeSet<>();
            while (true) {
                int id = edgeStack.pop();
                Edge e = g.edges.get(id);
                vertices.add(e.u());
                vertices.add(e.v());
                if (id == stopEdgeId) {
                    break;
                }
            }
            vertexBlocks.add(new ArrayList<>(vertices));
        }

        private void dfs(int u, int parentEdge) {
            tin[u] = low[u] = ++timer;
            int children = 0;

            for (int edgeId : g.adjacency.get(u)) {
                if (edgeId == parentEdge) {
                    continue;
                }
                Edge edge = g.edges.get(edgeId);
                int v = edge.other(u);

                if (tin[v] == 0) {
                    children++;
                    edgeStack.push(edgeId);
                    dfs(v, edgeId);
                    low[u] = Math.min(low[u], low[v]);

                    if (low[v] >= tin[u]) {
                        if (parentEdge != -1) {
                            isArticulation[u] = true;
                        }
                        popBlock(edgeId);
                    }

                    if (low[v] > tin[u]) {
                        isBridge[edgeId] = true;
                    }
                } else if (tin[v] < tin[u]) {
                    low[u] = Math.min(low[u], tin[v]);
                    edgeStack.push(edgeId);
                }
            }

            // Gốc DFS chỉ là đỉnh khớp nếu có ít nhất hai con.
            if (parentEdge == -1 && children > 1) {
                isArticulation[u] = true;
            }
        }

        private List<List<Integer>> edgeComponents() {
            boolean[] visited = new boolean[g.n];
            List<List<Integer>> result = new ArrayList<>();

            for (int start = 0; start < g.n; start++) {
                if (visited[start]) {
                    continue;
                }
                List<Integer> component = new ArrayList<>();
                ArrayDeque<Integer> queue = new ArrayDeque<>();
                queue.addLast(start);
                visited[start] = true;

                while (!queue.isEmpty()) {
                    int u = queue.removeFirst();
                    component.add(u);
                    for (int id : g.adjacency.get(u)) {
                        if (isBridge[id]) {
                            continue;
                        }
                        int v = g.edges.get(id).other(u);
                        if (!visited[v]) {
                            visited[v] = true;
                            queue.addLast(v);
                        }
                    }
                }
                result.add(component);
            }
            normalize(result);
            return result;
        }

        Report run() {
            for (int start = 0; start < g.n; start++) {
                if (tin[start] != 0) {
                    continue;
                }
                dfs(start, -1);

                // Quy ước: đỉnh cô lập tạo một block đơn đỉnh.
                if (g.adjacency.get(start).isEmpty()) {
                    vertexBlocks.add(
                            new ArrayList<>(List.of(start)));
                }

                if (!edgeStack.isEmpty()) {
                    throw new IllegalStateException(
                            "Unclosed edge stack");
                }
            }

            normalize(vertexBlocks);

            List<Integer> articulations = new ArrayList<>();
            for (int u = 0; u < g.n; u++) {
                if (isArticulation[u]) {
                    articulations.add(u);
                }
            }

            List<List<Integer>> bridges = new ArrayList<>();
            for (int id = 0; id < g.edges.size(); id++) {
                if (isBridge[id]) {
                    Edge e = g.edges.get(id);
                    bridges.add(new ArrayList<>(
                            List.of(e.u(), e.v())));
                }
            }
            normalize(bridges);

            return new Report(
                    List.copyOf(vertexBlocks),
                    List.copyOf(articulations),
                    List.copyOf(bridges),
                    List.copyOf(edgeComponents()));
        }
    }

    private static int componentCount(
            Graph g, int removedVertex, int removedEdge) {
        boolean[] visited = new boolean[g.n];
        int count = 0;

        for (int start = 0; start < g.n; start++) {
            if (start == removedVertex || visited[start]) {
                continue;
            }
            count++;
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.add(start);
            visited[start] = true;

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (int id : g.adjacency.get(u)) {
                    if (id == removedEdge) {
                        continue;
                    }
                    int v = g.edges.get(id).other(u);
                    if (v == removedVertex || visited[v]) {
                        continue;
                    }
                    visited[v] = true;
                    queue.addLast(v);
                }
            }
        }
        return count;
    }

    // Oracle độc lập cho đỉnh khớp/cầu trên đồ thị nhỏ:
    // xóa hẳn một đỉnh/cạnh rồi đếm lại số thành phần.
    private static void verify(Graph g, Report result) {
        int base = componentCount(g, -1, -1);

        List<Integer> expectedArticulations = new ArrayList<>();
        for (int v = 0; v < g.n; v++) {
            if (componentCount(g, v, -1) > base) {
                expectedArticulations.add(v);
            }
        }

        List<List<Integer>> expectedBridges = new ArrayList<>();
        for (int id = 0; id < g.edges.size(); id++) {
            if (componentCount(g, -1, id) > base) {
                Edge edge = g.edges.get(id);
                expectedBridges.add(new ArrayList<>(
                        List.of(edge.u(), edge.v())));
            }
        }
        normalize(expectedBridges);

        if (!expectedArticulations.equals(result.articulations())
                || !expectedBridges.equals(result.bridges())) {
            throw new AssertionError(
                    "Articulation or bridge mismatch");
        }

        // Mỗi cạnh của đồ thị đơn nằm trong đúng một vertex block.
        for (Edge edge : g.edges) {
            int matched = 0;
            for (List<Integer> block : result.blocks()) {
                if (block.contains(edge.u())
                        && block.contains(edge.v())) {
                    matched++;
                }
            }
            if (matched != 1) {
                throw new AssertionError(
                        "Edge must belong to one block");
            }
        }
    }

    private static void show(String name, Graph graph) {
        Report r = new Analyzer(graph).run();
        verify(graph, r);
        System.out.println(name + ".blocks=" + r.blocks());
        System.out.println(name + ".articulations=" +
                r.articulations());
        System.out.println(name + ".bridges=" + r.bridges());
        System.out.println(name + ".edgeComponents=" +
                r.edgeComponents());
    }

    private static void crossCheck() {
        Random random = new Random(2026L);
        for (int test = 0; test < 200; test++) {
            int n = 1 + random.nextInt(8);
            List<int[]> pairs = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    if (random.nextInt(4) == 0) {
                        pairs.add(new int[]{u, v});
                    }
                }
            }
            Graph g = new Graph(n, pairs.toArray(new int[0][]));
            verify(g, new Analyzer(g).run());
        }
        System.out.println("crossCheck=PASS (200 graphs)");
    }

    public static void main(String[] args) {
        show("main", new Graph(8, new int[][]{
            {0,1}, {1,2}, {2,0}, {1,3},
            {3,4}, {4,5}, {5,3}, {4,6}
        }));

        show("bowtie", new Graph(5, new int[][]{
            {0,1}, {1,2}, {2,0},
            {0,3}, {3,4}, {4,0}
        }));

        show("chain", new Graph(4, new int[][]{
            {0,1}, {1,2}, {2,3}
        }));

        show("single", new Graph(2, new int[][]{
            {0,1}
        }));

        show("empty", new Graph(0, new int[0][2]));
        crossCheck();
    }
}
~~~

Lệnh biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac BiconnectedComponentsDemo.java
java BiconnectedComponentsDemo
~~~

**Đầu ra xác định** (dấu cách trong danh sách theo định dạng mặc định của `List.toString()` trong Java):

~~~text
main.blocks=[[0, 1, 2], [1, 3], [3, 4, 5], [4, 6], [7]]
main.articulations=[1, 3, 4]
main.bridges=[[1, 3], [4, 6]]
main.edgeComponents=[[0, 1, 2], [3, 4, 5], [6], [7]]
bowtie.blocks=[[0, 1, 2], [0, 3, 4]]
bowtie.articulations=[0]
bowtie.bridges=[]
bowtie.edgeComponents=[[0, 1, 2, 3, 4]]
chain.blocks=[[0, 1], [1, 2], [2, 3]]
chain.articulations=[1, 2]
chain.bridges=[[0, 1], [1, 2], [2, 3]]
chain.edgeComponents=[[0], [1], [2], [3]]
single.blocks=[[0, 1]]
single.articulations=[]
single.bridges=[[0, 1]]
single.edgeComponents=[[0], [1]]
empty.blocks=[]
empty.articulations=[]
empty.bridges=[]
empty.edgeComponents=[]
crossCheck=PASS (200 graphs)
~~~

### Giải thích bộ thử

- **main:** kết hợp hai tam giác, hai cầu, ba đỉnh khớp và một đỉnh cô lập để kiểm tra nhiều loại block trong cùng một đồ thị.
- **bowtie:** hai tam giác có chung đỉnh 0. `bowtie.articulations=[0]` nhưng `bowtie.bridges=[]`; vì vậy `bowtie.blocks` có hai khối, còn `bowtie.edgeComponents` chỉ một nhóm.
- **chain:** đường 0–1–2–3. Mỗi cạnh là một cầu và một block K₂; các đỉnh giữa 1 và 2 là khớp; sau khi bỏ cầu, mỗi đỉnh thành một E-BCC riêng.
- **single:** đúng một cạnh 0–1. Cạnh ấy là cầu, nhưng cả hai đỉnh đều **không phải đỉnh khớp**, theo định nghĩa xóa một đỉnh có làm tăng số thành phần hay không. Khối `{0,1}` vẫn phải xuất hiện.
- **empty:** đồ thị n=0 không có block, đỉnh khớp, cầu hay nhóm E-BCC.
- **crossCheck:** 200 đồ thị đơn vô hướng có seed cố định, bao gồm đồ thị có thể rời rạc, khẳng định kết quả đỉnh khớp/cầu của DFS khớp với **thử xóa từng đỉnh/cạnh và đếm thành phần bằng BFS**. Bộ kiểm thử còn xác nhận mỗi cạnh gốc được chứa trong **đúng một block theo tập đầu mút**. Nếu sai, mã ném `AssertionError` thay vì in PASS.

**Hạn chế kiểm thử:** các phép đối chiếu giúp phát hiện lỗi logic nhưng không thay cho chứng minh tính đúng. Phần `verify` theo cách thử xóa từng đỉnh/cạnh dùng để kiểm thử đồ thị nhỏ; không được dùng làm thuật toán chính cho đầu vào lớn.

## 10. Block-cut tree/forest: biểu diễn cấu trúc các block

Với phân rã **V-BCC**, có thể xây **block-cut graph** hai phía:

- Một loại nút đại diện **mỗi block** (B-node).
- Một loại nút đại diện **mỗi đỉnh khớp** (A-node).
- Nối A-node của đỉnh x với B-node của mỗi block **chứa x**.

Với mỗi thành phần liên thông ban đầu, đồ thị hai phía thu được là một **cây** (nếu không có đỉnh khớp, chỉ còn một nút block). Nếu đồ thị gốc rời rạc, thu được **rừng block-cut (block-cut forest)**.

Ví dụ `main` có các block:

~~~text
B0 = {0,1,2}
B1 = {1,3}
B2 = {3,4,5}
B3 = {4,6}
B4 = {7}
~~~

Các đỉnh khớp 1,3,4 tạo các nút A1,A3,A4. Các cạnh giữa các nút hai phía là:

~~~text
B0 -- A1 -- B1 -- A3 -- B2 -- A4 -- B3

B4 (nút đơn lẻ cho đỉnh 7 cô lập)
~~~

Dãy ở trên là **một đường** trong block-cut forest của ví dụ, nhưng với đồ thị khác có thể tạo cây nhiều nhánh.

### Block-cut tree dùng để làm gì?

- Tìm những **đỉnh dễ gây chia cắt mạng**: các A-node tương ứng với đỉnh khớp.
- Biểu diễn **cấu trúc phụ thuộc giữa các vùng bền vững**: muốn đi từ một block sang block khác thường phải qua các articulation nằm giữa chúng trên cây.
- Tiền xử lý câu hỏi về liên thông sau khi **xóa một đỉnh**: trên cấu trúc block-cut tree có thể tổ chức nhiều truy vấn nhanh hơn so với chạy BFS cho từng truy vấn, sau khi xây thêm dữ liệu thích hợp.
- Dùng làm nền cho **DP trên cây**, nơi mỗi block là một “khối” và các đỉnh khớp là điểm nối.

**Không nhầm với bridge tree:** nếu xóa cầu và rút mỗi E-BCC thành một nút, rồi nối các nút theo cầu, ta được **rừng cầu (bridge forest/tree)**. Cấu trúc này theo **cạnh**, khác block-cut tree theo **đỉnh**. Trên đồ thị bowtie, bridge forest chỉ có **một nút**, còn block-cut tree có **hai nút block và một nút articulation**.

## 11. Độ phức tạp và giới hạn triển khai

Gọi V là số đỉnh, E là số cạnh.

**Thuật toán DFS Tarjan cốt lõi:**

- Mỗi đỉnh được DFS phát hiện đúng một lần: **O(V)**.
- Mỗi cạnh vô hướng được xem từ hai đầu trong danh sách kề: **O(E)**.
- Mỗi cạnh được đẩy vào stack tối đa một lần và pop tối đa một lần: tổng **O(E)** thao tác stack.
- Tạo các nhóm sau khi loại cầu bằng một lượt BFS/DFS: **O(V+E)**.
- Kết luận: **O(V+E)** thời gian cho phần phát hiện đỉnh khớp, cầu, phân rã block và E-BCC nếu thu thập kết quả bằng cấu trúc O(1) trung bình.

**Bộ nhớ cốt lõi:** danh sách kề O(V+E), các mảng `tin/low` và dấu O(V+E), ngăn xếp đệ quy DFS O(V), ngăn xếp cạnh O(E), danh sách block O(V+E) xét theo tổng số đầu mút/đỉnh trong các block. Tổng **O(V+E)**.

**Chi phí chuẩn hóa đầu ra của mã Java:** dùng `TreeSet` trong `popBlock` và `Collections.sort` trong `normalize` để sắp đỉnh/danh sách. Những bước này có thể thêm thời gian **O((V+E) log(V+E))** trong chặn trên đơn giản. Nếu đề chỉ cần nhóm cạnh hoặc ID block mà không yêu cầu thứ tự, có thể bỏ sắp xếp để giữ tổng thời gian tuyến tính.

**Stack recursion:** ở đồ thị dạng một đường dài V đỉnh, DFS có độ sâu O(V). Java có thể bị `StackOverflowError` với V rất lớn dù bản thân thuật toán đúng. Khi đó nên chuyển sang **DFS lặp** với stack frame chứa trạng thái duyệt cạnh và bước xử lý sau con, hoặc điều chỉnh môi trường nếu được phép. Không giải quyết vấn đề bằng cách xóa logic cập nhật low sau khi đệ quy.

**Chỉ số thời gian:** mã dùng `int timer`; trong giới hạn số đỉnh của một mảng Java thực tế, số lần gán tin bằng V, phù hợp kiểu int. Nếu xử lý đồ thị theo dạng luồng hoặc phân mảnh quy mô khác thường, cần kiểm tra giới hạn chỉ số.

### So với cách chậm thử xóa từng đỉnh/cạnh

Có thể tìm đỉnh khớp bằng cách lần lượt xóa một đỉnh và chạy BFS/DFS đếm thành phần, hoặc tìm cầu bằng cách xóa từng cạnh rồi làm như vậy. Một lần BFS/DFS tốn O(V+E), nên:

- Thử xóa tất cả V đỉnh: **O(V(V+E))**.
- Thử xóa tất cả E cạnh: **O(E(V+E))**.
- Tổng theo hướng kiểm thử: **O((V+E)(V+E))** trong chặn trên rộng.

Cách này dễ hiểu và hữu ích để **làm oracle trên đồ thị nhỏ**, nhưng không phù hợp làm thuật toán chính khi đồ thị lớn. DFS low-link tìm cả khớp/cầu trong một lượt tuyến tính.

## 12. Trường hợp biên và giới hạn của định nghĩa

### 12.1. Đồ thị rời rạc

Không chỉ chạy DFS từ đỉnh 0. Phải có vòng ngoài đi qua **mọi đỉnh chưa thăm**, vì mỗi thành phần liên thông có thể có các block và đỉnh khớp riêng. Mỗi cây DFS có **gốc** và số con gốc riêng.

### 12.2. Đỉnh cô lập

Không có cạnh đẩy vào stack, nên thuật toán pop cạnh sẽ không tự tạo block. Nếu dùng quy ước có singleton block, phải thêm `{u}` cho từng đỉnh cô lập. Một đề chỉ yêu cầu “thành phần cạnh song liên thông” có thể chọn bỏ singleton khỏi đầu ra, nhưng phải thông báo rõ.

### 12.3. Đồ thị chỉ có một cạnh

Với K₂ có đỉnh 0,1, hai đỉnh đều không phải khớp, vì xóa một đầu còn một đỉnh — số thành phần **không tăng**. Nhưng cạnh 0–1 là **cầu**. V-BCC trả block `{0,1}`, E-BCC trả `{0}` và `{1}`. Từ đó thấy việc có cầu **không đồng nghĩa** các đầu mút là đỉnh khớp.

### 12.4. Chu trình đơn

Một chu trình dài ít nhất 3 không có cầu/đỉnh khớp, nên cả chu trình là **một** V-BCC, đồng thời là **một** E-BCC. Ví dụ chu trình 0–1–2–3–0 cho hai kết quả đều chứa nhóm `{0,1,2,3}`.

### 12.5. Hình sao

Với sao có tâm 0 nối lá 1,2,3,4:

- Tâm 0 là đỉnh khớp, các lá không phải.
- Bốn cạnh đều là cầu.
- V-BCC là các block K₂: `{0,1}`, `{0,2}`, `{0,3}`, `{0,4}`.
- E-BCC là năm singleton: mỗi đỉnh là một nhóm sau khi bỏ cầu.

### 12.6. Cạnh song song

Trong **đa đồ thị**, hai cạnh song song u–v có thể tạo đường thay thế khi xóa **một** cạnh, nên không được tự đánh dấu cả hai là cầu. Nếu DFS chỉ so sánh `v==parent[u]` rồi bỏ qua **tất cả** cạnh tới cha, ta có thể **bỏ sót cạnh ngược song song** và tính low sai.

Phải phân biệt bằng **ID cạnh cha**, chỉ bỏ đúng một cạnh cây đã dùng; cạnh song song còn lại có thể được xét là back edge. Tuy nhiên, để tránh mọi khác biệt về quy ước vòng khuyên, **chương trình Java minh họa từ chối multigraph**, không tuyên bố đã xử lý toàn bộ đầu vào có cạnh lặp.

### 12.7. Khuyên

Một khuyên `u–u` không giúp nối hai đỉnh khác nhau và không phải cầu, nhưng cách gán khuyên vào block có thể khác nhau theo định nghĩa “block” của đa đồ thị. Nếu triển khai không có quy tắc rõ, khuyên dễ bị bỏ quên trong edge stack hoặc gán block sai. Mã minh họa từ chối khuyên ngay tại khởi tạo.

### 12.8. Đồ thị có hướng

Phép phân rã V-BCC/E-BCC ở đây dành cho **đồ thị vô hướng**. Đồ thị có hướng có khái niệm **thành phần liên thông mạnh (SCC)**, **strong articulation/strong bridge** và **2-vertex/2-edge-strong-connectivity**, nhưng thuật toán và tiêu chí không thể sao chép trực tiếp từ low-link vô hướng. Nếu đề có cung một chiều, trước hết phải xác nhận đúng loại thành phần cần tìm.

### 12.9. Hệ thống mạng thực tế

Đỉnh khớp có thể đại diện router/máy trạm/điểm giao; cầu có thể đại diện một kết nối độc đạo. Nhưng trong mô hình thực tế, một thiết bị có thể có **nhiều liên kết phụ**, chất lượng đường đi khác nhau hoặc giới hạn định tuyến. Tarjan theo topology chỉ trả tính liên thông theo mô hình cạnh/đỉnh, **không** đo băng thông hay mức độ ưu tiên đường truyền. Tính “dự phòng” ở đây mang ý nghĩa cấu trúc, không phải bảo đảm hiệu suất.

## 13. Sai lầm thường gặp

1. **Gộp hai loại BCC làm một.** Bowtie có hai V-BCC nhưng một E-BCC.
2. **Coi các V-BCC là phân hoạch đỉnh.** Đỉnh khớp có thể nằm trong nhiều block.
3. **Quên rằng một cạnh cầu vẫn là block K₂** theo quy ước phân rã blocks.
4. **Không thêm đỉnh cô lập** khi đề có singleton blocks.
5. **Dùng `low[v]>tin[u]` để tách V-BCC.** Điều kiện đúng là `low[v]>=tin[u]`; dấu nghiêm ngặt dành cho cầu.
6. **Dùng điều kiện đỉnh khớp không phải gốc cho gốc DFS**, khiến gốc có một con bị đánh dấu nhầm.
7. **Quên đếm số con trực tiếp của từng gốc DFS** trong đồ thị rời rạc.
8. **Đánh dấu gốc là articulation chỉ vì phát hiện một block**, dù gốc không chia tách đồ thị.
9. **Quên đẩy cạnh cây trước đệ quy**, dẫn đến block bị thiếu cạnh.
10. **Không đẩy cạnh ngược tới tổ tiên vào edge stack**, khiến chu trình bị chia sai.
11. **Đẩy lại cạnh tới hậu duệ đã xử lý**, có thể lặp một cạnh và phân khối sai.
12. **Pop tới đỉnh thay vì đúng ID cạnh cây**, dễ lấy nhầm ranh giới block.
13. **Không cập nhật `low[u]=min(low[u],low[v])` sau khi trở về từ con**.
14. **Không cập nhật `low[u]` từ back edge**, làm chu trình bị xem như có cầu.
15. **Bỏ tất cả cạnh tới cha trong multigraph**, khiến cạnh song song bị mất.
16. **Chạy DFS từ một đỉnh duy nhất**, bỏ sót các thành phần liên thông khác.
17. **Dùng thứ tự `tin` làm khoảng cách ngắn nhất**, trong khi nó chỉ là số thứ tự phát hiện.
18. **Nhầm một chu trình với một block** trong trường hợp nhiều chu trình thuộc cùng vùng không có đỉnh khớp.
19. **Kết luận hai tam giác chung một đỉnh là một V-BCC** vì không có cầu.
20. **Xóa đỉnh khớp khỏi tất cả block trừ một**, làm các block không còn chứa đầy đủ cạnh.
21. **Cho rằng đầu mút của cầu luôn là đỉnh khớp**; K₂ là phản ví dụ.
22. **Báo toàn chương trình O(V+E) dù còn sắp xếp đầu ra**, không tính chi phí chuẩn hóa.
23. **Dùng DFS đệ quy trên đường rất dài mà không cân nhắc StackOverflowError**.
24. **Áp dụng quy tắc Tarjan vô hướng cho đồ thị có hướng**, nhầm với SCC.
25. **Chỉ kiểm thử đồ thị liên thông có chu trình**, bỏ qua dây xích, sao, đỉnh đơn, đồ thị rời rạc.
26. **Nhầm block-cut tree với bridge tree**, làm sai cấu trúc rút gọn khi có đỉnh khớp mà không có cầu.

## 14. Kiểm thử và phản ví dụ

Một bộ test tốt phải phân biệt các hiện tượng khác nhau:

| Trường hợp | V-BCC | Đỉnh khớp | Cầu | E-BCC |
| --- | --- | --- | --- | --- |
| Không có đỉnh | Rỗng | Rỗng | Rỗng | Rỗng |
| Một đỉnh cô lập | Một singleton | Không | Không | Một singleton |
| Một cạnh K₂ | Một block K₂ | Không | Một cầu | Hai singleton |
| Chuỗi 4 đỉnh | Ba block K₂ | Hai đỉnh giữa | Ba cầu | Bốn singleton |
| Chu trình 4 đỉnh | Một block bốn đỉnh | Không | Không | Một nhóm bốn đỉnh |
| Hình sao 5 đỉnh | Bốn block K₂ | Tâm sao | Bốn cầu | Năm singleton |
| Hai tam giác chung đỉnh | Hai block chia sẻ tâm | Tâm | Không | Một nhóm gồm cả năm đỉnh |
| Hai tam giác nối bằng cầu | Hai block tam giác + block cầu | Có khớp tại đầu cầu | Cầu nối | Hai nhóm tam giác |

**Kiểm chứng độc lập:** với đồ thị nhỏ, tính số thành phần liên thông ban đầu `k`; cho từng đỉnh v, xóa v và các cạnh kề, đếm lại `k_v`; v là đỉnh khớp nếu `k_v>k`. Tương tự, xóa từng cạnh e, e là cầu nếu `k_e>k`. Có thể dùng BFS đơn giản để đếm thành phần, không phụ thuộc công thức low.

**Kiểm tra blocks:** mỗi cạnh gốc phải thuộc đúng **một** V-BCC. Nếu một cạnh không ở block nào hoặc ở hai block, có thể đã sai logic push/pop ngăn xếp. Tuy nhiên, kiểm tra này **chưa đủ một mình** để chứng minh tính tối đa của từng block; cần kết hợp chứng minh DFS và những đồ thị đối chứng có articulation/chu trình.

**Kiểm tra E-BCC:** sau khi xóa mọi cầu, mọi cặp đỉnh trong cùng nhóm phải còn đường đi không qua cầu; các nhóm khác nhau không có đường như vậy. Đỉnh cô lập/đầu cầu đứng riêng là kết quả hợp lệ.

## 15. Bài tập có lời giải

**Bài 1.** Đỉnh khớp là gì? **Đáp án:** đỉnh mà khi xóa đỉnh và toàn bộ cạnh kề, số thành phần liên thông của đồ thị tăng.

**Bài 2.** Cầu là gì? **Đáp án:** cạnh mà khi xóa cạnh ấy, số thành phần liên thông tăng.

**Bài 3.** Trong đường 0–1–2, đỉnh nào khớp? **Đáp án:** chỉ có 1. Hai cạnh đều là cầu.

**Bài 4.** Tam giác 0–1–2–0 có bao nhiêu V-BCC? **Đáp án:** một block `{0,1,2}`, không có cầu hoặc đỉnh khớp.

**Bài 5.** Hai tam giác chung đúng đỉnh 0 có bao nhiêu V-BCC và E-BCC? **Đáp án:** hai V-BCC `{0,1,2}` và `{0,3,4}`; một E-BCC `{0,1,2,3,4}`.

**Bài 6.** Vì sao ở ví dụ hai tam giác chung đỉnh, 0 là khớp dù không có cầu? **Đáp án:** xóa 0 làm hai nhóm còn lại không nối được; nhưng xóa từng cạnh tam giác vẫn còn đường vòng thay thế.

**Bài 7.** Với cạnh cây `u→v` có `tin[u]=4` và `low[v]=5`, cạnh ấy có là cầu không? **Đáp án:** có, vì 5>4. Nếu u không phải gốc, u cũng là đỉnh khớp do 5>=4, miễn điều kiện bối cảnh DFS như đã nêu.

**Bài 8.** Nếu `tin[u]=4`, `low[v]=4` thì cạnh cây u–v có là cầu không? **Đáp án:** không, vì dấu cầu cần nghiêm ngặt >. Nếu u không phải gốc, u có thể là khớp vì dấu >= đúng.

**Bài 9.** Gốc DFS có đúng một con v và `low[v]>=tin[root]`. Gốc có là đỉnh khớp không? **Đáp án:** không, điều kiện của gốc là ít nhất hai con DFS; tuy nhiên vẫn có thể đóng một block khi low[v]>=tin[root].

**Bài 10.** Với đồ thị gồm một cạnh `0–1`, cả hai đầu mút có là khớp? **Đáp án:** không. Cạnh là cầu và tạo block K₂.

**Bài 11.** Vì sao V-BCC có thể chung đỉnh nhưng không chung cạnh? **Đáp án:** một đỉnh khớp có thể nối nhiều khối, còn mỗi cạnh thuộc một khối cực đại xác định.

**Bài 12.** Khi nào pop ngăn xếp cạnh thành một block? **Đáp án:** sau khi DFS xong một con v của u và `low[v]>=tin[u]`, pop cho đến và gồm cạnh cây u–v.

**Bài 13.** Vì sao phải đẩy back edge từ u tới tổ tiên? **Đáp án:** nó thể hiện chu trình nối cây con với tổ tiên và phải nằm trong block khi pop, đồng thời cập nhật low.

**Bài 14.** Trong chuỗi 0–1–2–3, danh sách blocks? **Đáp án:** `{0,1}`, `{1,2}`, `{2,3}`; khớp `{1,2}`; cầu là cả ba cạnh.

**Bài 15.** Trong chu trình 4 đỉnh, số cầu và số khớp? **Đáp án:** đều 0; mọi cạnh có đường vòng và bỏ một đỉnh vẫn còn đường nối ba đỉnh kia.

**Bài 16.** Đỉnh cô lập có được ghi thành V-BCC không? **Đáp án:** theo quy ước bài học, có, một singleton. Một số đề chỉ liệt kê khối có cạnh nên cần đọc định dạng mong đợi.

**Bài 17.** Sau khi đã có danh sách cầu, tìm E-BCC thế nào? **Đáp án:** chạy BFS/DFS trên đồ thị bỏ qua toàn bộ cạnh cầu; mỗi tập đỉnh gặp được là một E-BCC.

**Bài 18.** Block-cut graph nối hai loại nút nào? **Đáp án:** nút đại diện block với nút đại diện đỉnh khớp; có cạnh khi đỉnh khớp thuộc block đó.

**Bài 19.** Nếu đồ thị gốc không liên thông, block-cut graph là cây hay rừng? **Đáp án:** rừng; mỗi thành phần gốc sinh một cây cấu trúc riêng.

**Bài 20.** Một cạnh có hai đầu u,v và hai cạnh song song cùng nối u,v. Có được coi mỗi cạnh là cầu không? **Đáp án:** không. Xóa một cạnh vẫn còn cạnh kia nối u với v. Mã Java trong bài cố ý từ chối đầu vào này.

**Bài 21.** Thuật toán Tarjan low-link cốt lõi tốn bao nhiêu? **Đáp án:** O(V+E) thời gian, O(V+E) bộ nhớ cho danh sách kề, stack, kết quả và mảng trạng thái (không kể chuẩn hóa sắp xếp).

**Bài 22.** Vì sao phải phân biệt `parentEdge` bằng ID cạnh trong DFS? **Đáp án:** để bỏ qua đúng cạnh cây đã đi qua, không bỏ nhầm mọi cạnh nối tới cha trong multigraph.

**Bài 23.** Một đồ thị hình sao có tâm 0 và bốn lá. E-BCC có mấy nhóm? **Đáp án:** năm nhóm đơn đỉnh vì bốn cạnh đều là cầu.

**Bài 24.** Nếu cần truy vấn nhiều lần “xóa đỉnh x thì vùng mạng nào bị tách?”, nên nghiên cứu cấu trúc nào sau khi tìm blocks? **Đáp án:** block-cut tree/forest, kết hợp tiền xử lý truy vấn thích hợp trên cây.

## 16. Checklist giải bài các thành phần song liên thông

1. **Đề yêu cầu V-BCC hay E-BCC?** Nếu chỉ nói “song liên thông”, hãy xác định theo đỉnh hay theo cạnh từ định nghĩa/đầu ra.
2. **Đồ thị có hướng hay vô hướng?** Tarjan low-link trong bài dành cho vô hướng.
3. **Đồ thị có khuyên/cạnh song song không?** Nếu có, cần thuật toán/định nghĩa đa đồ thị thích hợp, không dùng code chỉ nhận đồ thị đơn.
4. **Có quy định về block K₂ và đỉnh cô lập không?** Khớp cách in với đề.
5. **Mỗi đỉnh có `tin` và `low` chưa?** Khởi tạo chưa thăm rõ ràng.
6. **Đã duyệt mọi thành phần liên thông** bằng vòng ngoài DFS chưa?
7. **Có dùng ID cạnh cha thay vì chỉ đỉnh cha** để tránh lọc nhầm cạnh không?
8. **Có đẩy cạnh cây và back edge tới tổ tiên vào stack đúng một lần không?**
9. **Sau con v có cập nhật `low[u]` từ `low[v]` không?**
10. **Đã nhớ dấu tách block `low[v]>=tin[u]` nhưng cầu `low[v]>tin[u]` chưa?**
11. **Đỉnh khớp không phải gốc và gốc DFS có điều kiện riêng chưa?**
12. **Khi đóng block, có pop tới đúng cạnh cây u–v và gom tất cả đầu mút không?**
13. **Có cho phép articulation xuất hiện ở nhiều V-BCC, nhưng mỗi cạnh đúng một block không?**
14. **Nếu cần E-BCC, có bỏ tất cả cầu rồi BFS/DFS phân nhóm không?**
15. **Có phân biệt block-cut tree theo đỉnh và bridge tree theo cạnh không?**
16. **Đã thử đường, sao, chu trình, bowtie, K₂, isolated và đồ thị rời rạc chưa?**
17. **Đã dự liệu O(V) stack đệ quy và chi phí sắp kết quả trong Java chưa?**

**Ghi nhớ:** phần khó nhất của các thành phần song liên thông không chỉ là chạy DFS, mà là **chọn đúng khái niệm**. V-BCC phân rã thành các blocks có thể chung **đỉnh khớp**, còn E-BCC là các nhóm đỉnh sau khi bỏ **cầu**. DFS với `tin/low` cho điều kiện phát hiện cầu, khớp, và kết hợp **edge stack** để đóng từng block ở ranh giới `low[child]>=tin[parent]`.
