# Quy hoạch động theo biên trên bảng hẹp

**Quy hoạch động theo biên (frontier DP, profile DP, broken-profile DP)** là cách xử lý một bảng hoặc lưới có một chiều tương đối nhỏ. Ta quét từng hàng, cột hoặc ô; thay vì nhớ toàn bộ những lựa chọn đã thực hiện ở phần bảng cũ, thuật toán chỉ giữ **trạng thái trên ranh giới** giữa phần đã xử lý và phần chưa xử lý. Một trạng thái thường là **bitmask** biểu diễn các ô ở biên đã bị chiếm hoặc những điều kiện mà phần còn lại phải tiếp tục thỏa mãn.

Ý tưởng quan trọng: phần bảng nằm xa phía sau ranh giới đã hoàn tất. Nếu tất cả tương tác giữa quá khứ và tương lai đều đi qua ranh giới nhỏ, những cấu hình khác nhau của phần đã xử lý nhưng có **cùng trạng thái biên** có thể gộp vào một ô DP. Kích thước trạng thái vì thế phụ thuộc **theo hàm mũ của chiều hẹp w**, thay vì phụ thuộc theo hàm mũ của tổng số ô H×w.

Bài học thuộc chủ đề **Quy hoạch động cấu trúc**. Ví dụ chính là **đếm cách lát các ô không bị chặn của bảng hẹp bằng domino 1×2**, cho phép đặt ngang hoặc dọc, mỗi ô trống được che đúng một lần. Ví dụ này giúp thấy rõ ý nghĩa mask, điều kiện chuyển biên, thứ tự xử lý, chứng minh không đếm thiếu/đếm trùng, bộ nhớ O(2^w), độ phức tạp phụ thuộc chiều hẹp và cách cài đặt Java 17+.

**Sau bài học, bạn có thể:** nhận diện khi nào frontier DP phù hợp; chọn hướng quét làm nhỏ biên; định nghĩa trạng thái “các ô đã được chiếm từ hàng trước”; viết phép chuyển điền các ô trống của hàng hiện tại; xử lý ô chặn và biên cuối; tính số cách modulo; chứng minh bất biến; phân biệt state mask đơn giản với frontier DP phải lưu **kết nối giữa những đầu mút**; kiểm thử bằng vét cạn trên bảng nhỏ.

## 1. Vì sao bảng hẹp làm DP khả thi?

Cho bảng R hàng và C cột. Nếu tìm mọi cách đặt domino bằng vét cạn, số nhánh lựa chọn có thể tăng rất nhanh theo diện tích R×C. Nhưng một domino chỉ có kích thước **1×2**, nên khi ta hoàn thành một hàng, mọi domino có thể ảnh hưởng đến hàng tiếp theo đều phải **đi qua đúng ranh giới giữa hai hàng**.

Vì vậy, quá khứ chỉ cần cho tương lai biết: **những cột nào của hàng kế tiếp đã có nửa domino đi từ hàng vừa xử lý xuống**. Những cách lát khác nhau của các hàng trước nhưng cùng thông tin ấy có thể được **cộng số cách** lại.

Nếu quét theo một chiều với:
- `H` là số lớp/hàng được xử lý.
- `w` là số ô trên mỗi lớp — **độ rộng biên**.
- `w = min(R,C)` khi bảng chữ nhật có thể xoay/đổi chiều mà không thay đổi đáp án.

Ta cần tối đa **2^w mask** chỉ cho thông tin đã bị chiếm hay chưa của w vị trí. Với w=3 có 8 mask, với w=10 có 1.024 mask, với w=20 đã có 1.048.576 mask. Chênh lệch này giải thích vì sao phương pháp đặc biệt hữu ích với một chiều nhỏ.

**Không suy luận rằng mọi bài trên bảng hẹp chỉ cần 2^w trạng thái.** Trong các bài phải duy trì kết nối của những đường đi, thành phần liên thông hoặc điều kiện chu trình, một bit “đã chiếm” chưa đủ; trạng thái biên có thể phải lưu cả cách ghép cặp, nhãn thành phần và thông tin khác. Domino tilings là ví dụ cơ bản có biên trạng thái đơn giản.

## 2. Phát biểu bài toán lát domino

Cho một bảng chữ nhật R×C. Một số ô có thể bị **chặn**, không được che. Các ô còn lại phải được che **đúng một lần** bởi những miếng domino 1×2, mỗi miếng phủ hai ô **kề cạnh theo phương ngang hoặc phương dọc**. Domino không được phủ ô chặn và không được nhô ra ngoài bảng.

Hỏi **có bao nhiêu cách lát**? Hai cách khác nhau nếu tập vị trí các miếng domino khác nhau. Không phân biệt thứ tự mà ta “đặt” các miếng khi tìm kiếm. Để kết quả phù hợp với nhiều kích thước, bài này tính số cách **modulo 1.000.000.007** (viết tắt là MOD).

### Các kiểm tra đầu vào

1. **Số ô trống lẻ ⇒ không có cách lát**, vì mỗi domino phủ đúng hai ô. Đây là điều kiện cần, **không đủ**: số ô trống chẵn vẫn có thể không lát được do hình dạng và ô chặn.
2. **Không có ô trống ⇒ một cách lát rỗng.** Chọn quy ước số cách là **1**: không đặt miếng nào và đã che đủ mọi ô trống. Quy ước cũng áp dụng cho bảng có 0 hàng hoặc 0 cột.
3. **Bảng phải chữ nhật:** mọi hàng phải cùng số cột. Với `boolean[][]` trong Java, các hàng có thể dài khác nhau hoặc null, nên phải kiểm tra trước khi dùng.
4. Bài toán cụ thể này chỉ có domino 1×2, không có tile khác; nếu dùng L-tromino hoặc miếng dài hơn hai hàng, thông tin biên/cách chuyển phải thiết kế lại.
5. Nếu đề yêu cầu số cách **chính xác** thay vì modulo, cần dùng `BigInteger` hoặc chứng minh kiểu số đủ lớn. MOD chỉ là hợp đồng của ví dụ Java.

### Kết quả mẫu không có ô chặn

| Bảng | Số cách lát | Lý do hoặc kiểm tra |
|---|---:|---|
| 1×1 | 0 | Một ô trống không ghép thành domino |
| 1×2 | 1 | Một domino ngang |
| 1×6 | 1 | Một cách lát bằng ba domino |
| 2×2 | 2 | Hai miếng ngang hoặc hai miếng dọc |
| 2×3 | 3 | Ba mẫu lát quen thuộc |
| 2×4 | 5 | Dãy Fibonacci theo số cột |
| 3×3 | 0 | Chín ô trống, số lẻ |
| 3×4 | 11 | Có 11 cấu hình lát |
| 4×4 | 36 | Có 36 cấu hình lát |

Các số này là tổng **cấu hình hình học khác nhau**, không phải số thứ tự đặt domino.

## 3. Chọn hướng quét để có biên nhỏ nhất

Ta có thể quét theo hàng hoặc theo cột. Với bảng R×C, nếu R≤C thì **quét các cột** (mỗi biên có R ô) thường tốt hơn quét các hàng (mỗi biên có C ô). Ngược lại nếu C≤R, quét theo hàng.

Với domino, chuyển vị giữa R và C giữ nguyên số cách lát vì nó tạo ánh xạ một–một giữa cách lát của bảng gốc và của bảng chuyển vị. Ô chặn cũng được chuyển vị tương ứng.

Đặt:

**`H=max(R,C)`**, **`w=min(R,C)`**.

Ta xét bảng đã định hướng gồm H hàng, mỗi hàng w cột. Trong mã Java, có thể thực hiện chuyển vị **theo cách ánh xạ chỉ số** mà không cấp phát thêm một mảng ô R×C. Nếu đã chuyển vị:
- Hàng định hướng r tương ứng cột r của bảng gốc.
- Cột định hướng c tương ứng hàng c của bảng gốc.
- Ô chặn định hướng `(r,c)` được đọc từ `blocked[c][r]`.

Nếu không chuyển vị, ô chặn định hướng `(r,c)` đọc từ `blocked[r][c]`.

**Tại sao cần điều này?** Với bảng 2×100, quét theo các hàng gốc tạo biên rộng 100, không thể dùng một mask int nhỏ. Quét theo các cột gốc tạo biên rộng chỉ 2, có đúng 4 trạng thái. Với phương pháp theo biên, **định hướng quét có thể quyết định bài toán có giải được hay không**.

## 4. Định nghĩa trạng thái theo biên

Giả sử đang chuẩn bị xử lý hàng định hướng r, với `0≤r<H`. Ta dùng:

**`dp[mask]` = số cách lát hợp lệ các hàng 0..r−1, trong đó các domino dọc bắc qua biên đã chiếm chính xác những ô của hàng r có bit 1 trong mask.**

Mask có w bit. Bit thứ c (đánh số từ 0) bằng 1 nghĩa là ô `(r,c)` **đã bị che bởi một domino dọc đặt từ hàng r−1 xuống**, nên không được che thêm trong hàng hiện tại.

Điều này **không nói rằng ô có bit 0 chắc chắn trống**: nó chỉ nói ô đó **chưa bị chiếm bởi domino từ hàng trước**. Ô này vẫn có thể là ô chặn. Vì vậy cần mask ô chặn riêng.

Đặt:

- `blockedMask[r]`: mask có bit 1 tại những ô bị chặn ở hàng r.
- `incomingMask`: mask đi từ hàng trước xuống hàng r.
- `occupied = incomingMask | blockedMask[r]`: tất cả vị trí không cần/không được phủ thêm trong hàng r.
- `outgoingMask`: mask đánh dấu các ô **hàng r+1** sẽ bị chiếm bởi domino dọc bắt đầu tại hàng r.

### Bất biến quan trọng

Một trạng thái `dp[mask]` hợp lệ phải thỏa:

1. **Mọi ô trống ở các hàng trước r đã được che đúng một lần.**
2. Không có domino nào nhô xa hơn hàng r.
3. Những ô của hàng r đã có nửa domino đi xuống được đánh dấu **chính xác bởi mask**.
4. Không có hai domino nào chồng lên nhau; không domino nào đi qua ô chặn.

Ở r=0, chưa có hàng trước, nên trạng thái duy nhất là `dp[0]=1`: một cách chưa đặt gì và không có nửa domino treo qua biên trên của bảng. Các mask khác bằng 0.

### Loại mask đi vào ô chặn

Nếu `(incomingMask & blockedMask[r]) != 0`, một domino đi từ hàng trước đã nhô vào ô chặn của hàng r. Trạng thái đó **không hợp lệ**, phải bỏ.

Bản Java còn kiểm tra trước rằng không tạo domino dọc xuống **ô chặn ở hàng sau**; do đó các mask không hợp lệ thường đã bị loại trong khi sinh, nhưng bước kiểm tra ở đầu hàng là một **hàng rào an toàn cho bất biến**, đồng thời giúp người học nhìn rõ điều kiện đúng.

## 5. Chuyển trạng thái: điền kín hàng hiện tại

Với mỗi mask có `dp[mask] > 0`, ta cần liệt kê **mọi cách hoàn thiện các ô chưa bị chiếm của hàng r** bằng domino nằm ngang trong hàng này hoặc domino dọc từ hàng này xuống hàng r+1.

Sử dụng một hàm đệ quy nhỏ `fillRow` chỉ để **sinh các chuyển trong một hàng**. Nó không phải lời giải vét cạn trên toàn bảng: kết quả các hàng trước đã được gộp vào `dp[mask]`.

Ở mỗi bước, tìm **ô chưa bị chiếm đầu tiên** tại cột c:

1. **Đặt ngang:** nếu c+1<w và cả (r,c), (r,c+1) đều còn trống, đặt domino ngang che hai ô, đánh dấu chúng đã chiếm rồi đi tiếp.
2. **Đặt dọc:** nếu r+1<H và ô (r+1,c) **không bị chặn**, đặt domino che (r,c) và (r+1,c), đánh dấu (r,c) đã chiếm, đồng thời bật bit c trong outgoingMask, rồi đi tiếp.
3. Nếu không có lựa chọn nào hợp lệ, nhánh này thất bại; không cộng kết quả.
4. Khi **không còn ô nào chưa chiếm trong hàng r**, ta tìm được một chuyển hợp lệ từ incomingMask tới outgoingMask. Cộng `dp[incomingMask]` vào `next[outgoingMask]`, theo modulo.

Việc chọn **ô trống đầu tiên** rất quan trọng: nó bảo đảm mỗi cách lát hình học của hàng được sinh **đúng một lần**. Nếu cho phép chọn bất kỳ ô trống theo nhiều thứ tự khác nhau, một tập domino có thể bị đếm lặp do thứ tự đặt.

### Công thức chuyển trừu tượng

Gọi `T_r(in,out)` là **số cách lát riêng hàng r** tương thích mask đi vào in và mask đi ra out, có xét chướng ngại và biên bảng. Khi đó:

**`dpNext[out] = Σ_in dp[in] × T_r(in,out) (mod MOD)`.**

Hàm `fillRow` liệt kê các cách lát của hàng và cộng từng cách vào `dpNext`, nên không cần xây hẳn ma trận T. Nếu nhiều cách trong cùng một hàng tạo cùng out, chúng được cộng lại đúng số lần có các hình dạng lát khác nhau.

Sau khi hoàn tất hàng r, đặt `dp=dpNext` rồi chuyển sang hàng r+1.

**Kết quả cuối:** sau H hàng, lấy **`dp[0]`**. Không được có domino còn nhô xuống dưới bảng, nên outgoingMask sau hàng cuối bắt buộc là 0. Trong mã, nhánh đặt dọc bị cấm ngay tại hàng cuối.

## 6. Pseudocode đủ để tự cài đặt

Đầu vào là bảng đã định hướng H×w, với `blockedMask[r]` đã biết.

~~~text
MOD = 1_000_000_007
dp[0] = 1
dp[mask != 0] = 0

for r from 0 to H-1:
    next[all masks] = 0
    for incoming from 0 to (1<<w)-1:
        ways = dp[incoming]
        if ways == 0:
            continue
        if (incoming & blockedMask[r]) != 0:
            continue

        occupied = incoming | blockedMask[r]
        fillRow(
            row = r,
            nextFreeColumn = 0,
            occupied = occupied,
            outgoing = 0,
            ways = ways,
            next = next
        )

    dp = next

return dp[0]

fillRow(row, col, occupied, outgoing, ways, next):
    skip columns already occupied to find first free c

    if no free c exists:
        next[outgoing] += ways modulo MOD
        return

    if c+1 exists and is free:
        place a horizontal domino at (row,c),(row,c+1)
        recurse with those two cells marked occupied

    if row+1 exists and cell (row+1,c) is not blocked:
        place a vertical domino at (row,c),(row+1,c)
        recurse with c occupied and outgoing bit c set
~~~

Điều kiện biên của nhánh ngang **không được** nhìn sang hàng khác; domino ngang chiếm **hai cột liên tiếp của cùng hàng**. Điều kiện biên của nhánh dọc **không được** cho domino đi qua hàng cuối hoặc vào ô chặn của hàng kế tiếp.

### Tại sao không dùng toàn bộ occupied của hàng sau?

Một domino mới đặt **dọc** chiếm một ô thuộc hàng hiện tại và một ô thuộc hàng sau. Vì vậy thông tin duy nhất cần truyền sang hàng sau là **bit ở cột tương ứng**. Những domino **ngang** nằm trọn trong hàng hiện tại nên không cần lưu sang hàng sau.

Mask đi ra không được đánh dấu các ô chặn của hàng sau. Ô chặn được xử lý riêng bởi `blockedMask[r+1]`; mask chỉ biểu diễn **ô đã bị chiếm bởi domino từ quá khứ**, không biểu diễn mọi loại ô không khả dụng.

## 7. Truy vết thủ công trên bảng 2×3

Bảng 2×3 không chặn có đúng **3 cách lát**. Vì áp dụng hướng biên hẹp, thuật toán chuyển vị và quét như bảng định hướng **3×2** (H=3,w=2). Các mask từ 0 tới 3 có biểu diễn:

| Mask | Nhị phân (bit cột 1, bit cột 0) | Ý nghĩa |
|---:|---|---|
| 0 | 00 | Không có ô nào của hàng hiện tại bị chiếm sẵn |
| 1 | 01 | Cột 0 bị chiếm sẵn |
| 2 | 10 | Cột 1 bị chiếm sẵn |
| 3 | 11 | Cả hai cột bị chiếm sẵn |

Ban đầu trước hàng 0: `dp[0]=1`, các mask khác bằng 0.

**Xử lý hàng 0 (không có ô chặn):**

- Với incoming=00, có thể đặt **một domino ngang** trong hàng 0, che hai cột ⇒ outgoing=00, góp 1 cách.
- Hoặc đặt **hai domino dọc** từ hàng 0 xuống hàng 1, ở cả hai cột ⇒ outgoing=11, góp 1 cách.
- Không có cách tạo outgoing=01 hay 10 vì sẽ để thừa một ô của hàng hiện tại.

Sau hàng 0: `dp[00]=1`, `dp[11]=1`.

**Xử lý hàng 1:**

- Từ incoming=00 với 1 cách, lại có hai lựa chọn: domino ngang ⇒ outgoing=00 (góp 1), hoặc hai domino dọc xuống hàng 2 ⇒ outgoing=11 (góp 1).
- Từ incoming=11 với 1 cách, hai ô hàng 1 đã được che bởi domino dọc từ hàng 0; không đặt thêm domino ở hàng 1 ⇒ outgoing=00 (góp thêm 1).

Sau hàng 1: `dp[00]=2`, `dp[11]=1`.

**Xử lý hàng 2 (hàng cuối):**

- Từ incoming=00, chỉ có thể đặt một domino ngang, vì **không được đặt dọc ra ngoài bảng** ⇒ outgoing=00, góp 2 cách.
- Từ incoming=11, không còn ô chưa chiếm ⇒ outgoing=00, góp 1 cách.

Cuối cùng `dp[00]=2+1=3`. Đây là kết quả đúng cho bảng gốc 2×3.

### Cách đọc trạng thái

Một ô `dp[mask]=2` **không có nghĩa là hai ô được che**. Nó có nghĩa là **có hai cách hoàn thành các hàng đã xử lý** mà để lại chính mẫu che sẵn mask trên hàng tiếp theo. Những cách ấy được gộp vì mọi ảnh hưởng tới phần chưa xử lý đều được mã hóa trong mask.

## 8. Ô chặn: chuyển trạng thái phải tôn trọng cả hai hàng

Xét bảng 2×3 ban đầu không chặn, có 3 cách lát. Nếu chặn cả hai ô của **cột đầu**:

~~~text
# . .
# . .
~~~

Bốn ô còn lại tạo thành bảng 2×2, nên có **2 cách lát**.

Nếu chỉ chặn một ô:

~~~text
# . .
. . .
~~~

Còn 5 ô trống, là số lẻ ⇒ **0 cách**. Kiểm tra tính chẵn lẻ này loại đầu vào nhanh, nhưng với số ô trống chẵn vẫn phải chạy DP nếu chưa có chứng minh khác.

### Cách phối hợp occupied và blocked

Giả sử một hàng có `blockedMask=0101` (hai ô chặn tại cột 0 và 2). Nếu incomingMask=0010, thì `occupied=0111`: ba cột đã không còn cần/được phép điền tiếp, chỉ cột 3 là ô trống cần che. Trừ khi có thể đặt domino dọc xuống ô tương ứng hàng sau, nhánh ấy không thể hoàn thành hàng. Không thể đặt ngang che cột 2–3 vì cột 2 bị chặn.

Nếu incomingMask có bit chồng với blockedMask, ví dụ incoming=0001, blocked=0101, có nghĩa domino trước đã nhô vào ô chặn; phải bỏ trạng thái. Toán tử OR không thể “hợp thức hóa” chồng lấn này: **kiểm tra giao bằng AND trước khi OR**.

### Kiểm tra hàng kế tiếp

Khi thử đặt dọc ở cột c, cần bảo đảm cột ấy ở **hàng kế tiếp** không bị chặn. Nếu không kiểm tra sớm, một triển khai đúng vẫn có thể sinh outgoingMask không hợp lệ và loại nó ở đầu lượt tiếp theo. Mã Java kiểm tra ngay để **cắt nhánh không thể hoàn thành**, đồng thời vẫn giữ kiểm tra incoming∩blocked để bảo vệ bất biến.

## 9. Chứng minh đúng đắn

Ta chứng minh bằng quy nạp theo số hàng đã xử lý, kết hợp với tính đầy đủ và không trùng lặp của hàm điền hàng.

### Cơ sở

Trước khi xử lý hàng 0, có đúng **một** cách lát phần bảng rỗng: chưa đặt domino nào. Không có domino từ trên nhô xuống hàng 0, nên `dp[0]=1`; mọi mask khác không hợp lệ. Bất biến định nghĩa trạng thái được thỏa.

### Giả thiết quy nạp

Giả sử trước hàng r, `dp[in]` bằng số cách lát hợp lệ của tất cả hàng 0..r−1 sao cho các domino dọc đi sang hàng r che chính xác mask in; tất cả ô trống ở những hàng trước đã được che đúng một lần, và không domino nào đi xa hơn hàng r.

### Bước chuyển hàng

Chỉ xét in không chồng ô chặn của hàng r. Khi kết hợp in với blockedMask[r], những vị trí còn trống chính là những ô của hàng r chưa được che.

Trong bất kỳ cách lát hoàn chỉnh nào của hàng r phù hợp in, **ô trống có chỉ số nhỏ nhất** phải được che bởi:

- Domino ngang ghép với ô kế bên phải của cùng hàng; hoặc
- Domino dọc ghép với ô cùng cột ở hàng kế tiếp.

Không có lựa chọn thứ ba cho domino 1×2 nếu mọi ô đều nằm trong bảng. Hai khả năng loại trừ nhau vì chúng sử dụng hai vị trí khác nhau cho domino che ô đầu tiên. Hàm `fillRow` thử chính xác những lựa chọn hợp lệ này rồi áp dụng tiếp cùng lập luận cho ô trống đầu tiên còn lại.

Vì chọn ô trống đầu tiên ở mỗi bước, **mỗi cách lát hình học tương thích chỉ có một chuỗi quyết định** của hàm fillRow; không đếm lặp theo thứ tự đặt domino. Không nhánh nào đặt chồng hai domino, phủ ô chặn hoặc nhô ra ngoài bảng. Tại lá thành công, tất cả ô của hàng r đã được xử lý.

Do đó, từ mỗi cấu hình được đếm bởi `dp[in]`, hàm tạo chính xác tất cả cách hoàn thành hàng r và các mask out tương ứng. Cộng các đóng góp vào `dpNext[out]` cho đúng số cách của phần bảng qua hàng r, theo modulo MOD. Bất biến tiếp tục đúng với r+1.

### Kết thúc

Sau khi xử lý hàng H−1, mọi ô trống của toàn bảng đã được che. Không thể có domino vượt khỏi biên dưới, nên chỉ trạng thái mask=0 được chấp nhận. `dp[0]` chính là số cách lát toàn bảng, lấy modulo MOD.

Với bảng không có ô trống, đường đi qua tất cả các hàng không cần đặt domino nào duy trì mask=0 và đóng góp 1, đúng quy ước **một cách lát rỗng**.

**Lưu ý:** vì kết quả lấy modulo, `dp[mask]=0` trong quá trình tính có thể cũng biểu diễn một số cách dương nhưng chia hết cho MOD. Bỏ qua trạng thái có giá trị 0 **vẫn đúng đối với kết quả modulo**, nhưng không được suy luận rằng thực tế tuyệt đối không có cách lát nếu chỉ dựa vào một giá trị 0 sau modulo.

## 10. Phân tích số trạng thái, thời gian và RAM

Có H hàng định hướng và `2^w` incomingMask tiềm năng trên mỗi hàng. Bộ nhớ cho hai lớp DP là **2·2^w giá trị long**; có thể chỉ giữ hai mảng `current` và `next` rồi thay nhau dùng. Hàm chuyển đệ quy có độ sâu tối đa w vì mỗi bước xử lý ít nhất một ô của hàng.

### Chi phí xử lý một hàng

Nếu chỉ duyệt mask thì tốn O(2^w), nhưng **mỗi mask còn có thể sinh nhiều cấu hình lát trong hàng**. Không được viết ngay “O(H·2^w)” khi mỗi lần chuyển có nhiều nhánh.

Với cách cài đặt DFS ở phần 11, mỗi lời gọi đặt ngang hoặc dọc từ ô trống đầu tiên. Trong kịch bản trên–thô:

- Có tối đa 2^w incomingMask.
- Một cây lựa chọn có tối đa O(2^w) nút do chiều sâu ≤w và mỗi nút có tối đa hai nhánh.
- Bước tìm ô chưa chiếm đầu tiên quét tối đa O(w) bit.

Vì vậy một **cận trên bảo thủ** là:

**`O(H·w·4^w + H·w)`**,

gồm chuyển trạng thái và dựng mask ô chặn. Cận này không nhất thiết chặt và thường lớn hơn đáng kể so với công việc thực tế vì nhiều mask không đạt được, các nhánh nhanh chóng bị chặn và mỗi domino ngang che hai ô. Nhưng nó thể hiện điều quan trọng: **hàm mũ của chiều rộng biên**.

Một phương pháp **quét từng ô** với bitmask cửa sổ được thiết kế khác có thể cho cận như O(H·w·2^w) trong bài lát domino chuẩn, vì mỗi ô chỉ thực hiện số chuyển cục bộ hằng định. Không được gán cận đó cho một mã sinh **mọi cách hoàn tất cả hàng** mà chưa phân tích hàm sinh chuyển của nó.

### Bộ nhớ của mã Java

- Hai mảng DP: O(2^w) giá trị long.
- `blockedMasks` cho H hàng: O(H) số nguyên int.
- Độ sâu đệ quy khi sinh một hàng: O(w).
- Ngoài bảng đầu vào, bộ nhớ phụ tổng cộng **O(H+2^w+w)**.
- Nếu thay vì tính mask ô chặn khi cần mà chuyển vị ra một `boolean[][]` mới, bản sao bảng có thể tốn thêm O(Hw); mã mẫu **không** cần tạo bản sao đó.

Nếu chỉ cần số cách cho bảng **không ô chặn**, có thể không lưu blockedMasks (mọi mask chặn =0), khi ấy bộ nhớ cho phần DP gần như chỉ O(2^w+w). Với ô chặn, lưu O(H) mask giúp truy vấn nhanh ô chặn hàng kế tiếp.

### Giới hạn của ví dụ Java

Mã chặn `w>12` và nêu rõ đó là **ngưỡng thực hành của bài demo**, không phải ngưỡng lý thuyết. Với w≤12, `1<<w` an toàn trong kiểu int và số trạng thái tối đa 4.096; nhưng thời gian vẫn phụ thuộc H và cấu hình. Nếu tăng w, phải tính lại cận thời gian, số trạng thái, giới hạn kiểu bit shift và bộ nhớ JVM. Chỉ tăng ngưỡng không làm biến một bài toán rất rộng thành bài toán nhanh.

## 11. Java 17+ hoàn chỉnh: đếm domino tilings có ô chặn

Chương trình dưới đây dùng **mảng boolean hai chiều**:

- `true` nghĩa là ô **bị chặn**.
- `false` nghĩa là ô trống cần lát.
- Bảng phải chữ nhật, các hàng không null.
- Với bảng rỗng hoặc không có cột, trả **1** (một cách lát tập ô trống rỗng).
- Nếu số ô trống lẻ, trả **0**.
- Kết quả modulo `1_000_000_007L`.
- Dùng hướng quét sao cho `w=min(R,C)`. Không sao chép bảng sang mảng chuyển vị, chỉ đọc ô chặn theo ánh xạ chỉ số.
- Chỉ cho phép w≤12 trong ví dụ; bảng có biên rộng hơn bị từ chối bằng lỗi đầu vào.

Lưu thành **`NarrowBoardFrontierDemo.java`**:

~~~java
public final class NarrowBoardFrontierDemo {
    private static final long MOD = 1_000_000_007L;
    private static final int MAX_WIDTH = 12;

    static long countDominoTilings(boolean[][] blocked) {
        if (blocked == null) {
            throw new IllegalArgumentException("Null board");
        }

        int originalRows = blocked.length;
        if (originalRows == 0) {
            return 1L; // Không có ô nào: một cách lát rỗng.
        }
        if (blocked[0] == null) {
            throw new IllegalArgumentException("Null row");
        }

        int originalCols = blocked[0].length;
        for (boolean[] oneRow : blocked) {
            if (oneRow == null || oneRow.length != originalCols) {
                throw new IllegalArgumentException("Non-rectangular board");
            }
        }
        if (originalCols == 0) {
            return 1L;
        }

        int height = Math.max(originalRows, originalCols);
        int width = Math.min(originalRows, originalCols);
        if (width > MAX_WIDTH) {
            throw new IllegalArgumentException("Frontier too wide");
        }

        boolean transposed = originalCols > originalRows;
        int[] blockedMasks = new int[height];
        long freeCells = 0;

        // Đọc ô chặn theo hướng có chiều rộng biên nhỏ nhất.
        for (int r = 0; r < height; r++) {
            int mask = 0;
            for (int c = 0; c < width; c++) {
                boolean isBlocked = transposed
                        ? blocked[c][r]
                        : blocked[r][c];
                if (isBlocked) {
                    mask |= 1 << c;
                } else {
                    freeCells++;
                }
            }
            blockedMasks[r] = mask;
        }

        // Domino có đúng hai ô, nên số ô trống lẻ là vô nghiệm.
        if ((freeCells & 1L) != 0) {
            return 0L;
        }

        int stateCount = 1 << width;
        long[] dp = new long[stateCount];
        dp[0] = 1L;

        for (int r = 0; r < height; r++) {
            long[] next = new long[stateCount];
            int blockedNow = blockedMasks[r];
            int blockedNext = r + 1 < height
                    ? blockedMasks[r + 1]
                    : 0;

            for (int incoming = 0;
                    incoming < stateCount; incoming++) {
                long ways = dp[incoming];
                if (ways == 0L) {
                    continue;
                }
                if ((incoming & blockedNow) != 0) {
                    continue; // Domino không được đi vào ô chặn.
                }

                int occupied = incoming | blockedNow;
                fillRow(
                        0, occupied, 0, width,
                        r + 1 < height, blockedNext,
                        ways, next);
            }
            dp = next;
        }
        return dp[0];
    }

    // Điền các ô chưa chiếm của một hàng, từ trái qua phải.
    private static void fillRow(
            int column,
            int occupied,
            int outgoing,
            int width,
            boolean hasNextRow,
            int blockedNext,
            long ways,
            long[] next) {

        // Ô chặn hoặc ô đã được domino khác che thì bỏ qua.
        while (column < width
                && (occupied & (1 << column)) != 0) {
            column++;
        }

        if (column == width) {
            next[outgoing] = (next[outgoing] + ways) % MOD;
            return;
        }

        int bit = 1 << column;

        // Đặt ngang: che ô c và c+1 trong cùng hàng.
        if (column + 1 < width
                && (occupied & (1 << (column + 1))) == 0) {
            fillRow(
                    column + 2,
                    occupied | bit | (1 << (column + 1)),
                    outgoing,
                    width, hasNextRow, blockedNext,
                    ways, next);
        }

        // Đặt dọc: che ô c ở hàng này và hàng kế tiếp.
        if (hasNextRow && (blockedNext & bit) == 0) {
            fillRow(
                    column + 1,
                    occupied | bit,
                    outgoing | bit,
                    width, hasNextRow, blockedNext,
                    ways, next);
        }
    }

    private static boolean[][] clearBoard(int rows, int cols) {
        return new boolean[rows][cols];
    }

    public static void main(String[] args) {
        System.out.println("2x3: "
                + countDominoTilings(clearBoard(2, 3)));
        System.out.println("2x4: "
                + countDominoTilings(clearBoard(2, 4)));
        System.out.println("3x4: "
                + countDominoTilings(clearBoard(3, 4)));
        System.out.println("4x4: "
                + countDominoTilings(clearBoard(4, 4)));
        System.out.println("1x6: "
                + countDominoTilings(clearBoard(1, 6)));
        System.out.println("3x3: "
                + countDominoTilings(clearBoard(3, 3)));

        boolean[][] blockedColumn = clearBoard(2, 3);
        blockedColumn[0][0] = true;
        blockedColumn[1][0] = true;
        System.out.println("2x3 blocked first column: "
                + countDominoTilings(blockedColumn));

        boolean[][] blockedSingle = clearBoard(2, 3);
        blockedSingle[0][0] = true;
        System.out.println("2x3 blocked one cell: "
                + countDominoTilings(blockedSingle));

        System.out.println("0x0: "
                + countDominoTilings(clearBoard(0, 0)));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac NarrowBoardFrontierDemo.java
java NarrowBoardFrontierDemo
~~~

**Kết quả đầu ra:**

~~~text
2x3: 3
2x4: 5
3x4: 11
4x4: 36
1x6: 1
3x3: 0
2x3 blocked first column: 2
2x3 blocked one cell: 0
0x0: 1
~~~

### Đọc mã theo từng lớp

**Đầu vào và hướng quét:** kiểm tra `blocked` khác null, mọi hàng có cùng độ dài. Nếu một chiều bằng 0, không có ô nào cần che và trả 1. Nếu cả hai chiều dương, chọn height lớn hơn và width nhỏ hơn. Cờ `transposed` chỉ thay đổi cách đọc các ô; nó không thay đổi hình dạng vật lý của phép lát và không nhân bản bảng.

**Mask ô chặn:** mỗi hàng định hướng được chuyển thành một số int `blockedMasks[r]`. Bit c bằng 1 khi ô (r,c) bị chặn. Đếm `freeCells` để loại nhanh trường hợp lẻ.

**Bảng dp:** `dp[0]=1` trước hàng đầu; các mask khác là 0. Với mỗi hàng, tạo `next` mới, duyệt mọi mask đi vào có số cách khác 0, bỏ mask chồng ô chặn. Gộp incoming với blockedNow để xác định vị trí chưa được che.

**DFS trong một hàng:** `fillRow` luôn chọn ô chưa chiếm đầu tiên. Nó thử ngang nếu ô c+1 còn trống, thử dọc nếu có hàng sau và ô tương ứng hàng sau không chặn. Ở lá, tất cả ô hàng hiện tại đã được xử lý, vì vậy cộng ways vào trạng thái outgoing của hàng sau.

**Kết quả:** chỉ `dp[0]` ở cuối là hợp lệ. Nếu một cách còn domino dọc “treo” ra ngoài hàng cuối, nhánh ấy đã bị cấm bởi `hasNextRow=false`.

### Lưu ý số học Java

- `1 << width` chỉ an toàn cho số bit trong miền thích hợp của int; mã giới hạn width≤12 nên tránh shift lớn.
- `long ways` và `long[] dp` chứa số cách **đã lấy modulo**. Một lần cộng hai số nhỏ hơn MOD rồi lấy modulo an toàn trong long. Không dùng int tùy tiện nếu thay đổi MOD hoặc phép toán phức tạp hơn.
- `freeCells` dùng long để tránh tràn nếu tổng số ô lớn. Bảng `boolean[][]` bản thân đã chịu giới hạn cấp phát và chỉ số Java.
- Mã không tạo domino vật lý; nó đếm các cấu hình qua mask và nhánh chuyển. Nếu đề cần **in một cách lát**, phải lưu quyết định hoặc dùng phép truy vết có kiểm chứng thay vì chỉ lưu số cách modulo.

## 12. Kiểm thử bằng vét cạn độc lập

Để kiểm tra mã DP, với bảng nhỏ có thể viết một bộ đếm **vét cạn trên các ô của toàn bảng**:

1. Tìm **ô trống chưa được che đầu tiên** theo thứ tự hàng–cột.
2. Nếu không còn ô trống chưa che, có đúng **một** cách hoàn tất nhánh hiện tại.
3. Thử đặt domino ngang sang phải nếu ô bên phải nằm trong bảng, không chặn và chưa che.
4. Thử đặt domino dọc xuống dưới nếu ô phía dưới hợp lệ và chưa che.
5. Đánh dấu hai ô đã che, đệ quy, rồi hoàn tác khi quay lui.
6. Cộng số cách từ các nhánh. Với bảng nhỏ, đếm bằng số nguyên chính xác và so với DP (hoặc so modulo nếu bộ đếm tham chiếu vượt MOD).

Vét cạn này **không dùng mask theo biên**, nên hữu ích để tìm lỗi chuyển hướng hoặc xử lý chướng ngại. Chỉ nên thử bảng nhỏ, vì số nhánh có thể tăng theo diện tích.

### Những trường hợp bắt buộc

| Trường hợp | Kết quả mong đợi |
|---|---|
| Bảng 0×0 theo quy ước một cách lát rỗng | 1 |
| Bảng có H>0, w=0 | 1 |
| Bảng 1×1 trống | 0 |
| Bảng 1×2 trống | 1 |
| Bảng 2×2 trống | 2 |
| Bảng 2×3 trống | 3 |
| Bảng 2×4 trống | 5 |
| Bảng 3×4 trống | 11 |
| Bảng 4×4 trống | 36 |
| Bảng 3×3 trống | 0 |
| Bảng 2×3 chặn cả cột đầu | 2 |
| Bảng 2×3 chặn một ô | 0 |
| Bảng mọi ô bị chặn | 1 |
| Số ô trống chẵn nhưng bị cô lập | 0 |
| Hàng Java không cùng độ dài hoặc một hàng null | Ném IllegalArgumentException |

### Kiểm thử ngẫu nhiên

Với R,C trong khoảng 0..4, sinh mỗi ô bị chặn với một xác suất cố định; so **countDominoTilings** với vét cạn. Cần cả trường hợp H>w và H<w để kiểm tra việc đổi hướng quét, và cả những vị trí chặn sát biên để phát hiện lỗi kiểm tra hàng sau.

Các tính chất có thể kiểm tra thêm:

- **Đổi chiều bảng:** số cách lát của bảng và bảng chuyển vị phải bằng nhau.
- **Đổi tên các domino:** không làm thay đổi đáp án, vì chỉ đếm vị trí đặt.
- **Bảng chỉ toàn ô chặn:** có đúng một cách lát rỗng.
- **Thêm một ô chặn không bảo đảm số cách tăng hoặc giảm đơn điệu theo mọi cấu hình**, nên không tự dùng tính đơn điệu không chứng minh để kiểm thử.

Để đối chiếu sau modulo, cần biết rằng hai số cách nguyên khác nhau có thể cho cùng số dư; với bảng nhỏ các số cách thấp hơn MOD, so sánh chính xác không có vấn đề.

## 13. Những bẫy triển khai profile DP

1. **Định nghĩa mask mơ hồ:** phải nói rõ bit 1 là “ô hàng hiện tại **đã bị che từ trước**”, hay là “ô hiện tại **còn trống**”. Hai cách định nghĩa có thể dùng được nhưng công thức chuyển khác nhau.
2. **Bỏ qua ô chặn:** mask đi vào chồng ô chặn không hợp lệ; ô chặn không phải là một nửa domino.
3. **Chỉ kiểm tra bảng hiện tại:** domino dọc còn chiếm một ô ở hàng sau, phải bảo đảm ô đó tồn tại và không bị chặn.
4. **Cho phép domino dọc ở hàng cuối:** tạo mask nhô ra ngoài bảng, không phải cách lát hợp lệ.
5. **Trả tổng mọi dp[mask] ở cuối:** sai vì chỉ mask=0 mới không còn phần domino treo qua biên.
6. **Sinh các domino theo mọi thứ tự đặt:** có thể đếm lặp cùng một cấu hình hình học; cần cố định ô trống đầu tiên.
7. **Đánh dấu ngang không đủ hai ô:** có thể cho hai domino chồng lên nhau.
8. **Đánh dấu dọc trong outgoing sai cột:** những ô bị chiếm sẵn ở hàng sau phải tương ứng đúng cột có domino từ hàng trước.
9. **Sửa trực tiếp dp hiện tại khi chuyển hàng:** trộn trạng thái thuộc hai ranh giới khác nhau, làm việc đếm sai; dùng `next` riêng.
10. **Chuyển vị bảng nhưng quên chuyển vị ô chặn:** áp dụng chướng ngại sai tọa độ.
11. **Quên modulo ở những lần cộng:** số cách lát có thể rất lớn; chỉ dùng long không bảo đảm tính đúng tuyệt đối cho bảng lớn.
12. **Đặt chiều rộng không giới hạn:** bộ nhớ 2^w tăng rất nhanh và bit shift kiểu int có giới hạn; nên kiểm soát w trước khi cấp phát.
13. **Cho rằng mọi frontier DP đều 2^w:** bài liên thông có thể yêu cầu nhãn thành phần hoặc cấu hình ghép cặp phức tạp hơn.
14. **Đếm đúng số ô trống rồi kết luận có lời giải:** số ô trống chẵn chỉ là điều kiện cần; hình dạng có thể không lát được.
15. **Không phân biệt số cách chính xác và số cách modulo:** kết quả 0 modulo không đủ để kết luận không có cấu hình nếu số cách thực chia hết cho MOD.

## 14. Mở rộng: những dạng frontier DP khác

### 14.1. Đếm tập ô không kề cạnh

Ví dụ muốn đếm/tối ưu việc chọn ô sao cho hai ô được chọn **không kề theo hàng hoặc cột**. Có thể đặt mask biểu diễn các ô được chọn trong một hàng; mask trong cùng hàng hợp lệ nếu không có hai bit 1 liền nhau:

`(mask & (mask << 1)) == 0`.

Hai hàng liên tiếp không được chọn cùng một cột, nên hai mask liên tiếp phải thỏa:

`(previousMask & currentMask) == 0`.

Nếu có ô chặn/cấm chọn, còn cần `(currentMask & blockedMask[row]) == 0`.

Đặt `dp[row][mask]` là số cách hoặc giá trị tối ưu tới hàng row với mask hàng đó. Chuyển qua những mask hợp lệ; cách lưu và phép gộp thay đổi tùy mục tiêu đếm hay tối ưu. **Trong ví dụ này mask biểu diễn ô được chọn của một hàng**, không phải ô bị domino che từ hàng trước — cùng kỹ thuật bitmask nhưng ý nghĩa khác.

### 14.2. Đường đi liên thông và “plug DP”

Đối với Hamiltonian path/cycle, đường đi nối các ô, hoặc đếm cấu hình liên thông trên lưới hẹp, chỉ lưu bit “ô đã chiếm” có thể không đủ. Hai cách nối trong phần đã quét có thể tạo cùng tập ô biên nhưng khác **cách những đầu mút thuộc cùng thành phần**. Những khác biệt đó quyết định tương lai có thể nối hoàn chỉnh hay tạo chu trình sớm.

**Plug DP / connectivity-state DP** thường cần thêm:
- Trạng thái có/không có đầu mút tại từng vị trí biên.
- Nhãn hoặc kiểu ghép cặp các đầu mút với nhau.
- Quy tắc chuẩn hóa nhãn để hai trạng thái tương đương được gộp.
- Kiểm tra khi đóng một thành phần hoặc chu trình.

Không thể lấy nguyên trạng thái domino mask rồi áp dụng cho bài phải giữ liên thông: **thông tin biên tối thiểu phụ thuộc đặc tả bài toán**.

### 14.3. Tối ưu hóa thay vì đếm

Nếu mỗi cách đặt tile có chi phí và yêu cầu **chi phí nhỏ nhất**, có thể thay:
- `dp[mask]` = số cách
- bằng `dp[mask]` = chi phí nhỏ nhất để đạt mask.

Nhưng phải dùng một giá trị **INF** cho trạng thái không đạt tới và chuyển bằng **min** thay vì cộng số cách. Nếu cần truy vết một cách đặt, lưu thông tin lựa chọn hoặc tái dựng theo trạng thái. Không được đổi phép cộng thành min mà bỏ qua quy tắc xử lý vô nghiệm và bản chất các nhánh.

### 14.4. Tiền xử lý chuyển trạng thái

Nếu **không có ô chặn** và mỗi hàng có cùng cấu trúc, tập chuyển `T(in,out)` có thể được tiền tính một lần rồi dùng lại cho nhiều hàng. Điều này có thể tiết kiệm thời gian sinh DFS lặp lại, đổi lấy bộ nhớ chứa các chuyển và thời gian tiền xử lý.

Nếu ô chặn thay đổi theo hàng, các chuyển còn phụ thuộc vào **blockedNow** và **blockedNext**. Không được tái dùng một danh sách chuyển cho hàng có dạng chướng ngại khác mà không lọc lại điều kiện hợp lệ. Có thể cache theo cặp mask chặn nếu số mẫu thực tế ít.

Một số biến thể quét **từng ô** thay vì từng hàng còn cho phép chuyển số ít lựa chọn mỗi ô và dùng cùng một bitmask cửa sổ; đó là thiết kế khác có thể cải thiện cận độ phức tạp, nhưng bất biến mask cũng phải mô tả lại theo vị trí biên di động.

## 15. Checklist trước khi thiết kế frontier DP

- Bài toán có bảng/đồ thị mà **một chiều biên nhỏ** không? Có thể xoay bảng để giảm w không?
- Phần đã xử lý ảnh hưởng tới phần chưa xử lý thông qua **những thông tin nào**? Chỉ ô chiếm sẵn hay còn kết nối giữa các đầu mút?
- Đã định nghĩa chính xác bit 0/1 của mask và vị trí biên mà nó nói tới chưa?
- Có trạng thái cơ sở đúng (thường `dp[0]=1` cho bài đếm) không?
- Có kiểm tra tương thích giữa incoming, ô chặn và outgoing không?
- Mỗi cách hoàn tất một hàng có được sinh **đúng một lần**? Có bỏ sót một hướng đặt tile không?
- Có cấm các miếng nhô khỏi biên dưới/ngoài bảng không?
- Sau hàng cuối, chỉ nhận mask hợp lệ kết thúc (thường **mask 0**) chứ?
- Đã ước lượng số trạng thái 2^w **và** chi phí sinh chuyển từ một trạng thái chưa?
- Với cách sinh DFS, đã tính chi phí phụ thuộc hàm mũ của w, không tuyên bố O(H2^w) một cách vô căn cứ?
- Đã dự phòng RAM cho hai mảng DP, mask ô chặn, stack và bảng đầu vào chưa?
- Nếu trả modulo, đã áp dụng modulo đúng và phân biệt “0 modulo” với “không tồn tại” chưa?
- Đã thử bảng rỗng, tất cả ô chặn, số ô trống lẻ, bảng rất hẹp, bảng xoay, chặn sát biên và bảng nhỏ có đáp án biết trước chưa?
- Đã đối chiếu với vét cạn độc lập và tính chất **chuyển vị** của đáp án chưa?

**Ghi nhớ:** frontier DP làm việc vì một biên nhỏ có thể tóm tắt mọi ảnh hưởng của phần đã xử lý lên phần chưa xử lý. Trong bài lát domino, trạng thái chỉ cần mask những ô hàng tiếp theo **đã bị chiếm bởi domino dọc**. Điền trọn từng hàng, cộng số cách theo outgoingMask và chỉ nhận mask 0 ở cuối tạo lời giải đúng. Khi đổi sang bài có yêu cầu liên thông hoặc tile khác, phải thiết kế **trạng thái biên và chuyển trạng thái mới**, không sao chép máy móc bảng mask domino.