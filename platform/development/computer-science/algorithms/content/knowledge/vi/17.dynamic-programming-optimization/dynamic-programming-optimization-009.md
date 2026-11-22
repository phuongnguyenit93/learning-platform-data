# Cây Li Chao và miền truy vấn của các đường thẳng

**Cây Li Chao (Li Chao tree)** là một cấu trúc dữ liệu để duy trì nhiều hàm tuyến tính có dạng **`f(x)=a·x+b`** và trả lời nhanh truy vấn **giá trị nhỏ nhất hoặc lớn nhất tại tọa độ x**. Các đường thẳng có thể được **thêm theo thứ tự tùy ý**; các điểm x được hỏi không cần tăng dần hoặc giảm dần. Đây là công cụ đặc biệt hữu ích để **tối ưu quy hoạch động** khi một bước chuyển có thể biến đổi thành cực trị của tập đường thẳng.

Trong bài học này, ta xây **Li Chao tree cho giá trị nhỏ nhất (minimum Li Chao)** trên một **miền tọa độ nguyên đóng, hữu hạn `[L,R]`**. Mỗi đường khi thêm vào có hiệu lực trên **toàn bộ miền** ấy. Cây phân đôi miền theo trung điểm, tại mỗi nút giữ một đường có giá trị tốt ở trung điểm, rồi đẩy đường còn lại xuống một nhánh có thể có lợi thế. Tính chất quan trọng giúp làm được điều này: **hiệu của hai đường thẳng là hàm bậc nhất, nên hai đường phân biệt cắt nhau tối đa một lần**.

Bài thuộc mục **Tối ưu quy hoạch động**. Nội dung gồm định nghĩa truy vấn, chọn miền x, bất biến và phép hoán đổi đường ở mid, chứng minh tính đúng, cận thời gian/bộ nhớ, miền âm và số lớn, các tình huống đường song song, so sánh với convex hull trick, công thức DP bình phương, Java 17+ chạy độc lập và kiểm thử đối chiếu vét cạn.

**Mục tiêu:** tự triển khai `addLine(a,b)` và `minAt(x)` đúng; biết cách kiểm soát x ngoài miền và tràn `a*x+b`; giải thích vì sao chỉ cần đi xuống một nhánh mỗi lần chèn; đưa công thức DP về `m_j·x_i+b_j`; phân biệt Li Chao toàn miền với nén tọa độ, đường theo đoạn hoặc cấu trúc hỗ trợ xóa.

## 1. Bài toán cực tiểu của tập đường thẳng

Cho tập các đường:

`f_j(x)=a_j x+b_j`.

Hỗ trợ:

- **Thêm đường:** `addLine(a,b)` đưa `y=ax+b` vào tập các ứng viên cho **mọi x thuộc miền**.
- **Truy vấn:** `minAt(x)` trả `min_j(a_j x+b_j)` tại một x hợp lệ.

Nếu tập rỗng thì **không có giá trị cực tiểu**; API có thể dùng `OptionalLong.empty()` hoặc một kiểu kết quả riêng. Không nên tự mặc định câu trả lời của tập rỗng là 0.

Ví dụ ba đường:

`f₁(x)=2x+3`, `f₂(x)=−x+5`, `f₃(x)=1`.

| x | f₁ | f₂ | f₃ | Min |
|---:|---:|---:|---:|---:|
| -2 | -1 | 7 | 1 | **-1** |
| 0 | 3 | 5 | 1 | **1** |
| 4 | 11 | 1 | 1 | **1** |
| 10 | 23 | -5 | 1 | **-5** |

Tại x=4, hai đường khác nhau cùng đạt min=1. Nếu chỉ hỏi giá trị, không cần phân biệt chúng. Nếu đề yêu cầu chỉ số đường thắng (*argmin*), cần quy tắc phá hòa và lưu ID.

### Cách làm đơn giản để đối chiếu

Giữ danh sách k cặp (a,b). Thêm đường O(1). Mỗi truy vấn quét k phần tử và lấy min, mất **O(k)**. Bộ nhớ O(k). Cách này là **oracle** tuyệt vời để kiểm thử Li Chao trên đầu vào nhỏ, mặc dù truy vấn trở nên tốn kém khi số đường lớn.

## 2. Vì sao hai đường chỉ phải xử lý ở một phía?

Với hai đường `f(x)=a_fx+b_f` và `g(x)=a_gx+b_g`, xét hiệu:

**`f(x)−g(x)=(a_f−a_g)x+(b_f−b_g)`.**

Đây là hàm bậc nhất. Nếu slope khác nhau thì hai đường cắt nhau tại **tối đa một x thực**. Nếu slope bằng nhau mà intercept khác nhau thì một đường luôn cao hơn; nếu cả hai hệ số bằng nhau thì hai đường trùng nhau.

Điều này tạo ra cấu trúc thứ tự: một đường tốt hơn tại mid, đường còn lại chỉ có thể tốt hơn ở **phía trái hoặc phía phải**, không thể bất ngờ thắng ở cả hai phía mà không vi phạm tính giao cắt tối đa một lần.

Li Chao không cần tính tọa độ giao điểm bằng phép chia. Nó so sánh **giá trị tại các tọa độ nguyên** của nút rồi chọn nhánh; cách này tránh sai số khi chia phân số nếu dùng kiểu số nguyên chính xác.

**Giới hạn của lập luận:** nếu thay đường thẳng bằng hàm tùy ý có thể cắt nhau nhiều lần, chỉ đẩy một nhánh sẽ không đủ. Một số họ hàm có tính giao cắt hạn chế có thể dùng phiên bản Li Chao riêng, nhưng phải chứng minh điều kiện ấy chứ không sao chép nguyên mã.

## 3. Miền tọa độ x: điều kiện của thiết kế

Phiên bản này nhận một đoạn nguyên **`[L,R]` với L≤R**, số điểm nguyên là:

**`D=R−L+1`.**

Nút gốc quản lý [L,R]. Nút ở [l,r] chia thành hai nửa:

`mid=l+⌊(r−l)/2⌋`,

- Con trái quản lý **`[l,mid]`**.
- Con phải quản lý **`[mid+1,r]`**.

Tại l=r chỉ có một điểm nguyên; không được phân chia nữa. Chiều cao cây là **O(log D)**. Một miền đơn điểm có độ sâu 0.

### Miền âm vẫn bình thường

Chẳng hạn `[−10,10]` là miền hợp lệ, và `f(x)=2x+3` có giá trị −1 tại x=−2. Cây chỉ so sánh giá trị y của các đường ở x, nên không có giả thiết x phải dương. Không nên lấy x âm làm chỉ số mảng; các nút tự lưu khoảng tọa độ cần kiểm tra.

### Query ngoài miền không hợp lệ

Nếu cây được xây cho [L,R], một truy vấn tại x ngoài khoảng có thể nhận giá trị sai vì đường được lưu/đẩy dựa trên các đoạn **bên trong** khoảng đó. Mã an toàn sẽ **ném IllegalArgumentException**, không tự động clamp x về biên và không âm thầm mở rộng miền sau khi đã thêm các đường.

### Mid và nguy cơ tràn

Biểu thức `(l+r)/2` có thể tràn nếu l+r vượt kiểu số. Mẫu `l+(r−l)/2` thường an toàn hơn, nhưng cũng cần kiểm tra `r−l` biểu diễn được. Mã Java minh họa giới hạn tọa độ trong [−1.000.000,1.000.000], nên `r−l≤2.000.000`, an toàn cho `int`. Nếu chuyển sang kiểu `long` với gần toàn bộ miền 64 bit, phải thiết kế phép tính mid và độ dài miền riêng.

### Tọa độ thực và tọa độ nguyên

Ở đây lá tương ứng một **x nguyên**, nên D hữu hạn. Với số thực liên tục, không có số điểm nguyên D để dùng kết luận này; cần một độ sâu/độ chính xác dừng hoặc nén tọa độ truy vấn. Không được tuyên bố O(log D) cho miền vô hạn điểm khi chưa định nghĩa D.

## 4. Mỗi nút lưu những gì?

Một nút `Node` giữ:

- `line`: **một** đường thẳng đại diện cho đoạn của nút.
- `left`: con trái (có thể null).
- `right`: con phải (có thể null).

Không cần giữ toàn bộ danh sách các đường tại mỗi nút. Khi thêm một đường mới, có thể **hoán đổi** line của nút với line đang đi xuống, sao cho line lưu ở nút **không tệ hơn tại trung điểm**.

**Bất biến truy vấn:** với mọi x hợp lệ, cực tiểu của tất cả đường đã thêm bằng **min của các line nằm trên đường đi từ root tới lá chứa x**.

Nút gốc không nhất thiết là đường tốt nhất tại mọi x. Nó chỉ có vai trò giữ một ứng viên tốt ở mid của đoạn gốc, để những đường còn lại được đưa tới nhánh nơi chúng có thể cải thiện đáp án.

### Cây tạo nút động

Ban đầu root=null. Một lệnh chèn chỉ đi qua **một nhánh tại mỗi độ sâu**, và có thể tạo **tối đa một nút mới** khi gặp vị trí con null. Vì vậy với k lệnh chèn các đường hiệu lực trên toàn miền, số nút được cấp phát là **O(k)**. Stack đệ quy O(log D).

Đây là cận cho **Li Chao động tạo nút theo nhu cầu, không rollback, không persistent, không chèn theo đoạn con**. Nếu dùng phiên bản lưu nhiều thời điểm hoặc các line chỉ hiệu lực trong đoạn, cần phân tích lại bộ nhớ.

## 5. Thuật toán addLine: giữ line tốt tại mid

Giả sử nút đang quản lý [l,r], chứa đường `old`. Ta muốn chèn `candidate`. Tính:

- **`betterLeft = candidate(l) < old(l)`**.
- **`betterMid = candidate(mid) < old(mid)`**.

Tính hai boolean **trước khi hoán đổi** đường trong nút.

1. Nếu `betterMid` đúng, **swap** đường mới và đường trong nút. Sau bước này, line ở nút tốt hơn tại mid (hoặc bằng nhau nếu quy tắc tie cho phép).
2. Nếu l=r, dừng.
3. Nếu `betterLeft != betterMid`, đưa đường còn lại xuống **con trái** `[l,mid]`.
4. Nếu hai boolean giống nhau, đưa đường còn lại xuống **con phải** `[mid+1,r]`.

Bốn trường hợp:

| betterLeft | betterMid | Line giữ ở nút | Nhánh cho line còn lại |
|---|---|---|---|
| false | false | old | Phải |
| true | false | old | Trái |
| false | true | candidate (sau swap) | Trái |
| true | true | candidate (sau swap) | Phải |

Với hai đường song song, việc so sánh ở l/mid vẫn hợp lệ: một đường có intercept thấp hơn luôn thắng nếu slope bằng nhau. Không cần xử lý phép chia để tính giao điểm.

### Vì sao không cần chèn sang cả hai nhánh?

Đường giữ ở nút đã tốt ở mid. Phần còn lại chỉ có thể cải thiện trên **một phía** bởi hiệu hai line đổi dấu tối đa một lần. Nếu phía ấy là trái, chèn tiếp vào trái; nếu không, chèn sang phải (nếu nó không thắng ở đâu, việc chèn sâu hơn không gây sai, chỉ tốn thêm công).

Một phép tối ưu có thể bỏ line bị thống trị hoàn toàn, nhưng không bắt buộc. Mã đầy đủ ưu tiên **thuật toán cơ bản dễ chứng minh**, không thêm nhánh loại bỏ sớm có thể sai nếu chưa kiểm tra đúng điều kiện.

### Đường song song và hòa

- Cùng slope, intercept lớn hơn ⇒ luôn kém cho min.
- Cùng slope, intercept nhỏ hơn ⇒ luôn tốt hơn.
- Hai đường trùng nhau ⇒ không đổi đáp án.
- Hòa ở một x ⇒ hai đường cùng cho min; dùng so sánh nghiêm ngặt `<` đủ để giữ **giá trị cực tiểu**, dù không nhất thiết chọn một ID đường theo quy tắc từ điển.

Nếu cần truy vết ID nguồn của line tốt nhất, phải mở rộng bản ghi line và quy tắc so sánh (value, id), không suy ra ID từ kết quả y.

## 6. Thuật toán minAt(x): theo một đường đi

Khi query ở x, tìm từ root xuống nửa chứa x. Ở **mỗi nút đi qua**, đánh giá line đang giữ rồi lấy min với kết quả tạm:

~~~text
minAt(x):
    require L <= x <= R
    if root is null:
        return NO_LINE

    best = +infinity
    current = root
    l = L; r = R

    while current != null:
        best = min(best, current.line(x))
        if l == r: break

        mid = l + floor((r-l)/2)
        if x <= mid:
            current = current.left
            r = mid
        else:
            current = current.right
            l = mid+1

    return best
~~~

Pseudocode dùng infinity như một khái niệm. Java thực tế dùng `OptionalLong` ở API để phân biệt cây rỗng; sau khi biết root không rỗng, có thể khởi tạo `best=Long.MAX_VALUE` khi mọi giá trị y hợp lệ nằm trong long.

**Độ phức tạp query:** một nhánh mỗi tầng, O(log D) phép đánh giá line. Không quét k line; không đi xuống cả hai con.

## 7. Truy vết ví dụ ba đường trên miền [−10,10]

Thêm:

`f₁(x)=2x+3`, `f₂(x)=−x+5`, `f₃(x)=1`.

**Bước 1:** cây rỗng, thêm f₁ tạo root chứa f₁. Truy vấn x=−2 trả −1.

**Bước 2:** thêm f₂ tại root [−10,10] có mid=0:

- Tại l=−10: f₂=15, f₁=−17 ⇒ betterLeft=false.
- Tại mid=0: f₂=5, f₁=3 ⇒ betterMid=false.
- Không swap. Hai boolean bằng nhau ⇒ đẩy f₂ xuống **phải [1,10]**.

Tại x=4, query nhìn root f₁=11 và nhánh phải f₂=1, trả **1**.

**Bước 3:** thêm f₃=1 tại root:

- Tại l=−10: f₃=1, f₁=−17 ⇒ betterLeft=false.
- Tại mid=0: f₃=1, f₁=3 ⇒ betterMid=true.
- Swap để root giữ f₃, f₁ trở thành line còn lại.
- Hai boolean khác nhau ⇒ đẩy f₁ sang **trái [−10,0]**.

Với x=−2, query đi root→trái và lấy min(1,−1)=**−1**. Với x=0, min là **1**. Với x=4, root và con phải cho min(1,1)=**1**. Với x=10, root và con phải cho min(1,−5)=**−5**.

**Bước 4:** thêm f₄=−x+7, song song và luôn kém f₂=−x+5, nên đáp án không đổi. Thêm tiếp f₅=−x+2, song song và tốt hơn f₂. Khi ấy query(10)=**−8** và query(4)=**−2**.

Không có giả thiết rằng x query tăng dần, hoặc đường có slope được chèn theo thứ tự nào.

## 8. Chứng minh đúng bằng bất biến

Xét lần chèn candidate vào một nút đang giữ old trên đoạn [l,r]. Hàm hiệu `candidate(x)−old(x)` là hàm bậc nhất nên **không đổi dấu quá một lần** nếu không trùng hoàn toàn.

Tại mid, thuật toán giữ đường **không tệ hơn** ở nút. Đường còn lại, nếu tốt hơn, chỉ có thể tốt hơn ở **một phía** của mid. Hai so sánh tại l và mid trước swap xác định phía có thể có lợi ấy. Phía kia luôn có đường giữ ở nút **không cao hơn** đường còn lại, nên bỏ qua đường còn lại ở phía kia không mất đáp án min.

Giả sử trước chèn, với mọi x, min các line được lưu trên đường root→x bằng min của tập đường đã thêm. Trong quá trình chèn:

1. Đường giữ và candidate vẫn cùng đại diện cho **hai line gốc**, chỉ đổi vị trí nếu cần.
2. Phía không truy cập tiếp đã có line tại nút không tệ hơn line còn lại.
3. Phía cần xét tiếp nhận line còn lại tại con tương ứng; nếu con chưa có, tạo nút mới.
4. Mọi line đã tồn tại ở nhánh không liên quan vẫn được giữ.

Do đó sau chèn, với mọi x, đường đi từ gốc tới x vẫn chứa một line đạt min trong tập đã chèn. Quy nạp theo số lệnh `addLine` suy ra tính đúng của toàn cây. Lúc truy vấn, đọc tất cả line trên đúng đường đi và lấy min nên trả đáp án chính xác.

### Điều gì xảy ra ở điểm hòa?

So sánh dùng `<` chứ không dùng `<=`. Nếu hai line hòa tại mid, giữ line cũ cũng đúng về **giá trị** tại mid. Vì hiệu là hàm bậc nhất, line còn lại không thể có một vùng tốt hơn nằm ở cả hai phía mà không làm thay đổi dấu nhiều lần. Quy tắc chọn nhánh vẫn đủ bảo toàn min; chỉ có ID/tie-break của line trả về có thể phụ thuộc thứ tự thêm.

**Chú ý:** chứng minh dùng giả thiết mỗi line được thêm có hiệu lực ở **mọi x trong miền [L,R]**. Nếu line chỉ hợp lệ trên một đoạn nhỏ, phải mở rộng thuật toán và bất biến.

## 9. Phân tích thời gian và bộ nhớ

Gọi k là số lần thêm đường, q là số lần hỏi, D=R−L+1 điểm nguyên của miền.

| Công việc | Chi phí với Li Chao động |
|---|---|
| Tạo cây rỗng | O(1) |
| Một lần `addLine` | **O(log D)** |
| Một lần `minAt` | **O(log D)** |
| k lần thêm và q truy vấn | **O((k+q)log D)** |
| Bộ nhớ cho k line toàn miền | **O(k)** nút, cộng O(log D) stack chèn |
| Đánh giá `a·x+b` | O(1) khi long an toàn theo mô hình RAM |

Trong một lần thêm, thuật toán chỉ đi xuống **một con mỗi mức**. Mỗi lần chèn tạo tối đa một nút mới, nên bản **dynamic nodes** có O(k) nút; không cần cấp phát trước segment tree dày O(D). Nếu giữ thêm các phiên bản quá khứ hoặc chèn theo đoạn, bộ nhớ có thể lớn hơn.

Nếu D=1, mọi thao tác ở một tọa độ là O(1). Cận log thường viết O(log(D+1)) để bao phủ D=1. Với D rất lớn nhưng hữu hạn, chiều sâu chỉ theo số bit biểu diễn số điểm, song vẫn phải kiểm soát phép nhân và kiểu tọa độ.

**So sánh với quét k line:** quét dùng thêm O(1), hỏi O(k); Li Chao dùng thêm/hỏi O(log D). Nếu chỉ có vài line và rất ít query, quét trực tiếp có thể nhanh hơn nhờ hằng số nhỏ và đơn giản hơn. Nếu nhiều line/truy vấn xen kẽ, Li Chao thường đáng cân nhắc.

## 10. Số học an toàn: không để phép so sánh bị tràn

Li Chao phụ thuộc **hoàn toàn vào phép so sánh y(x)**. Nếu `a*x+b` tràn `long`, line nhỏ hơn có thể bị xem thành lớn hơn (hoặc ngược lại), dẫn tới chọn sai nhánh. Về mặt thuật toán, phép kiểm tra số học là một phần của **tính đúng**, không chỉ là tối ưu hóa.

Có ba phương án phổ biến:

1. **Ràng buộc đầu vào:** nếu `|a|≤A`, `|x|≤X`, `|b|≤B` và `A·X+B≤Long.MAX_VALUE` thì giá trị từng line nằm trong long. Cần tính giới hạn bằng kiểu không tràn.
2. **Kiểm tra phép toán:** `Math.multiplyExact(a,x)` và `Math.addExact(product,b)` báo `ArithmeticException` nếu một phép trung gian tràn. Lưu ý tích có thể tràn dù tổng chính xác toán học vừa long nhờ b bù trừ; nếu phải hỗ trợ trường hợp đó, dùng kiểu rộng hơn.
3. **BigInteger:** đánh giá và so sánh chính xác các giá trị lớn; chi phí thời gian/bộ nhớ phụ thuộc số bit, không còn giả định tất cả thao tác số học O(1).

**Không dùng double tùy tiện** khi yêu cầu so sánh chính xác các số nguyên lớn; một sai số gần điểm giao nhau có thể đổi thứ tự hai line và dẫn tới sai cây.

### Giới hạn của mã Java trong bài

Mã minh họa cố ý yêu cầu:

- Miền x nằm trong **[−1.000.000,1.000.000]**; mỗi cây có thể chọn một đoạn con [L,R] của khoảng đó.
- Hệ số góc `|a|≤1.000.000`.
- Hệ số tự do `|b|≤1.000.000.000.000`.

Khi đó `|a·x+b|≤2.000.000.000.000`, an toàn trong long. Giới hạn này là **hợp đồng của ví dụ**, không phải hạn chế toán học của cấu trúc Li Chao.

Khi xác thực hệ số long, nên so sánh `a<−limit || a>limit`; không dùng `Math.abs(a)>limit` với mọi long vì `Math.abs(Long.MIN_VALUE)` vẫn âm do giới hạn biểu diễn.

## 11. Chương trình Java 17+ hoàn chỉnh

Ví dụ hỗ trợ:

- `new MinTree(L,R)` tạo miền nguyên đóng. Không cấp phát sẵn toàn bộ cây.
- `addLine(a,b)` đưa line hiệu lực **toàn miền**, giới hạn hệ số để tính chính xác.
- `minAt(x)` trả `OptionalLong.empty()` nếu cây chưa có line; ném `IllegalArgumentException` nếu x ngoài miền.
- Hàm `minSquaredJumpCost` minh họa DP được tối ưu bằng các line, với tọa độ của ví dụ nằm trong [-10,10].

Lưu thành **`LiChaoDomainDemo.java`**:

~~~java
import java.util.OptionalLong;

public final class LiChaoDomainDemo {
    private static final int COORD_LIMIT = 1_000_000;
    private static final long SLOPE_LIMIT = 1_000_000L;
    private static final long INTERCEPT_LIMIT = 1_000_000_000_000L;

    private record Line(long slope, long intercept) {
        long valueAt(int x) {
            // Giới hạn tại addLine và ctor bảo đảm không tràn long.
            return slope * x + intercept;
        }
    }

    private static final class Node {
        Line line;
        Node left;
        Node right;

        Node(Line line) {
            this.line = line;
        }
    }

    private static final class MinTree {
        private final int domainLeft;
        private final int domainRight;
        private Node root;

        MinTree(int left, int right) {
            if (left < -COORD_LIMIT || right > COORD_LIMIT
                    || left > right) {
                throw new IllegalArgumentException("Invalid domain");
            }
            domainLeft = left;
            domainRight = right;
        }

        void addLine(long slope, long intercept) {
            if (slope < -SLOPE_LIMIT || slope > SLOPE_LIMIT
                    || intercept < -INTERCEPT_LIMIT
                    || intercept > INTERCEPT_LIMIT) {
                throw new IllegalArgumentException("Line out of bounds");
            }
            root = insert(
                    root, new Line(slope, intercept),
                    domainLeft, domainRight);
        }

        private static Node insert(
                Node node, Line candidate, int left, int right) {
            if (node == null) {
                return new Node(candidate);
            }

            int mid = left + (right - left) / 2;
            boolean betterLeft =
                    candidate.valueAt(left) < node.line.valueAt(left);
            boolean betterMid =
                    candidate.valueAt(mid) < node.line.valueAt(mid);

            if (betterMid) {
                // Đường tốt hơn tại mid được giữ tại nút.
                Line old = node.line;
                node.line = candidate;
                candidate = old;
            }

            if (left == right) {
                return node;
            }

            // Dùng kết quả so sánh TRƯỚC khi swap.
            if (betterLeft != betterMid) {
                node.left = insert(
                        node.left, candidate, left, mid);
            } else {
                node.right = insert(
                        node.right, candidate, mid + 1, right);
            }
            return node;
        }

        OptionalLong minAt(int x) {
            if (x < domainLeft || x > domainRight) {
                throw new IllegalArgumentException("x outside domain");
            }
            if (root == null) {
                return OptionalLong.empty();
            }

            long best = Long.MAX_VALUE;
            Node node = root;
            int left = domainLeft;
            int right = domainRight;

            while (node != null) {
                best = Math.min(best, node.line.valueAt(x));
                if (left == right) {
                    break;
                }

                int mid = left + (right - left) / 2;
                if (x <= mid) {
                    node = node.left;
                    right = mid;
                } else {
                    node = node.right;
                    left = mid + 1;
                }
            }
            return OptionalLong.of(best);
        }
    }

    // dp[i] = min_{0<=j<i}(dp[j] + (x[i]-x[j])^2), dp[0]=0.
    static long minSquaredJumpCost(int[] x) {
        if (x == null || x.length == 0) {
            throw new IllegalArgumentException("Empty positions");
        }

        // Miền phải chứa mọi tọa độ được hỏi trong ví dụ.
        MinTree tree = new MinTree(-10, 10);
        for (int coordinate : x) {
            if (coordinate < -10 || coordinate > 10) {
                throw new IllegalArgumentException("Position outside domain");
            }
        }

        long[] dp = new long[x.length];
        long x0 = x[0];
        tree.addLine(-2L * x0, x0 * x0);

        for (int i = 1; i < x.length; i++) {
            long xi = x[i];
            long best = tree.minAt(x[i]).orElseThrow();
            dp[i] = xi * xi + best;

            // Trạng thái i chỉ hợp lệ cho các i' > i.
            tree.addLine(-2L * xi, dp[i] + xi * xi);
        }
        return dp[x.length - 1];
    }

    private static String display(OptionalLong value) {
        return value.isPresent()
                ? Long.toString(value.getAsLong())
                : "none";
    }

    public static void main(String[] args) {
        MinTree tree = new MinTree(-10, 10);
        System.out.println("Empty x=0: " + display(tree.minAt(0)));

        tree.addLine(2, 3);  // y = 2x + 3
        System.out.println("One line x=-2: "
                + display(tree.minAt(-2)));

        tree.addLine(-1, 5); // y = -x + 5
        System.out.println("Two lines x=4: "
                + display(tree.minAt(4)));

        tree.addLine(0, 1);  // y = 1
        System.out.println("Three lines x=-2: "
                + display(tree.minAt(-2)));
        System.out.println("Three lines x=0: "
                + display(tree.minAt(0)));
        System.out.println("Three lines x=4: "
                + display(tree.minAt(4)));
        System.out.println("Three lines x=10: "
                + display(tree.minAt(10)));

        tree.addLine(-1, 7); // Song song nhưng kém hơn.
        System.out.println("Parallel dominated x=10: "
                + display(tree.minAt(10)));

        tree.addLine(-1, 2); // Song song nhưng tốt hơn.
        System.out.println("Parallel better x=10: "
                + display(tree.minAt(10)));
        System.out.println("Parallel better x=4: "
                + display(tree.minAt(4)));

        System.out.println("Squared jump DP: "
                + minSquaredJumpCost(new int[] {0, 1, 3, 4}));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac LiChaoDomainDemo.java
java LiChaoDomainDemo
~~~

**Đầu ra chính xác:**

~~~text
Empty x=0: none
One line x=-2: -1
Two lines x=4: 1
Three lines x=-2: -1
Three lines x=0: 1
Three lines x=4: 1
Three lines x=10: -5
Parallel dominated x=10: -5
Parallel better x=10: -8
Parallel better x=4: -2
Squared jump DP: 6
~~~

### Giải thích các phần chính

**Line.valueAt:** tính `slope*x+intercept` bằng long. Giới hạn dữ liệu vào đảm bảo biểu thức luôn nằm trong long, tránh sai ở phép so sánh.

**insert:** dùng `betterLeft` và `betterMid` so trước swap; giữ line tốt tại mid; đi đúng một nhánh theo sự khác nhau của hai boolean. Nếu gặp con null thì tạo Node. Với miền đơn điểm, return ngay sau so/swap.

**minAt:** đi từ root theo nửa chứa x, lấy min tất cả line đã gặp. Với cây rỗng trả OptionalLong.empty, còn x ngoài miền bị từ chối.

**Đường song song:** `−x+7` không thắng `−x+5` tại bất kỳ x nào; `−x+2` tốt hơn đường `−x+5`, nên tại x=10 giá trị min giảm từ −5 xuống −8 và tại x=4 giảm từ 1 xuống −2.

**DP:** line ứng với j=0 được thêm đầu tiên. Mỗi i query trước, tính dp[i], rồi mới thêm line của i. Thứ tự này giữ ràng buộc `j<i` và không tạo tự phụ thuộc.

## 12. Ví dụ tối ưu DP khoảng cách bình phương

Xét dãy tọa độ nguyên `x[0..n−1]` và công thức:

**`dp[0]=0`**,

**`dp[i]=min_{0≤j<i}(dp[j]+(x[i]−x[j])²)`**, với i≥1.

Cách trực tiếp xét mọi j trước i, mất **Θ(n²)** phép chuyển cho n trạng thái.

Khai triển:

`(x[i]−x[j])²=x[i]²−2x[i]x[j]+x[j]²`.

Đưa phần chỉ phụ thuộc i ra ngoài min:

**`dp[i]=x[i]²+min_{j<i}((−2x[j])·x[i]+(dp[j]+x[j]²))`.**

Đặt:

- Tọa độ query hiện tại `X=x[i]`.
- Đường từ trạng thái j có slope **`a_j=−2x[j]`**.
- Intercept **`b_j=dp[j]+x[j]²`**.

Vậy ta có:

**`dp[i]=X²+queryMin(X)`**.

Sau khi tính dp[i], thêm line:

**`f_i(X)=−2x[i]·X+(dp[i]+x[i]²)`**.

### Tính tay x=[0,1,3,4]

- i=0: dp[0]=0, line đầu `f₀(X)=0`.
- i=1, X=1: dp[1]=1+0=**1**. Thêm `f₁(X)=−2X+2`.
- i=2, X=3: min(f₀(3)=0, f₁(3)=−4), nên dp[2]=9−4=**5**. Thêm `f₂(X)=−6X+14`.
- i=3, X=4: min(0,−6,−10)=−10, nên dp[3]=16−10=**6**.

Đối chiếu công thức gốc ở i=3:

`min(dp[0]+(4−0)², dp[1]+(4−1)², dp[2]+(4−3)²)`

`=min(16,1+9,5+1)=**6**`.

Với một query và một add cho mỗi i, thời gian trở thành **O(n log D)** trên miền nguyên hữu hạn D, so với Θ(n²) trước đó. Bộ nhớ O(n) nút Li Chao và O(n) nếu cũng lưu toàn bộ dp.

### Các yêu cầu để tối ưu không đổi bài toán

- Công thức chuyển phải biến đổi được thành **`base(i)+min_j(a_j·x_i+b_j)`**, không chỉ “trông giống” bình phương.
- Line của j phải được thêm **sau khi dp[j] đã xác định** và **trước những i được phép dùng j**.
- Nếu phép chuyển yêu cầu j<i, phải **query trước khi add line i**.
- Không được dùng một line đã hết hiệu lực khi DP có cửa sổ ứng viên hoặc giới hạn theo thời gian.
- Mọi x[i] được query phải nằm trong miền của cây, mọi giá trị cần tính không được tràn kiểu số.
- Nếu DP yêu cầu max, cấu trúc so sánh phải đổi hoặc dùng biến đổi dấu với phép tính an toàn.

## 13. Li Chao và Convex Hull Trick (CHT)

Cả hai kỹ thuật giải bài toán cực trị của tập đường thẳng nhưng khai thác các giả thiết khác nhau.

| Tiêu chí | Li Chao miền hữu hạn | Convex Hull Trick |
|---|---|---|
| Thứ tự thêm slope | **Bất kỳ** | Nhiều biến thể nhanh yêu cầu slope đơn điệu hoặc cấu trúc phức tạp hơn |
| Thứ tự query x | **Bất kỳ** | Một số biến thể con trỏ yêu cầu x đơn điệu |
| Miền x | Phải có [L,R] hoặc tập tọa độ được hỗ trợ | Tùy biến thể, đôi khi dùng giao điểm của các line |
| Thêm | O(log D) ở bản này | Phụ thuộc thứ tự slope và cách lưu hull |
| Query | O(log D) ở bản này | Có thể O(log k) hoặc O(1) khấu hao khi đủ giả thiết |
| Số học | Đánh giá line tại x, cần tránh tràn | So sánh giao điểm/slope, cũng cần tránh tràn hoặc sai số |
| Xóa | Không có ở bản cơ bản | Tùy biến thể, không mặc định có |
| Cấu trúc | Cây phân đôi miền x | Bao lồi các line, deque, tìm kiếm nhị phân hoặc cấu trúc khác |

Nếu slope chèn có thứ tự và các query x cũng tăng/giảm thích hợp, CHT dạng deque có thể rất hiệu quả. Nếu slope và query đến ngẫu nhiên, Li Chao thường dễ áp dụng hơn nhờ không cần sắp slope. Dù vậy, có overhead nút/cây và phải chọn miền x. Chọn theo **các giả thiết thực tế của đề**, không theo tên công cụ.

## 14. Nén tọa độ và các biến thể miền truy vấn

### 14.1. Discrete Li Chao trên các x biết trước

Giả sử mọi query chỉ dùng các tọa độ rất thưa, ví dụ `−10⁹,3,8,10⁹`. Thay vì xét toàn đoạn giữa hai cực trị, có thể:

1. Thu thập các x sẽ được query, sắp và loại trùng: `coords[0..q−1]`.
2. Xây cấu trúc Li Chao trên **chỉ số** 0..q−1.
3. Ở nút chỉ số [l,r], khi so sánh đường phải đánh giá tại **`coords[l]` và `coords[mid]`**, **không phải** tại chỉ số l và mid.
4. Query x dùng vị trí của x trong coords rồi đi xuống theo chỉ số ấy.

Độ sâu O(log q), q là số tọa độ phân biệt. Đây là lựa chọn hợp lý khi tập x được biết trước, như một bài xử lý offline các query (dù thứ tự add/query vẫn phải tôn trọng).

Nếu sau này có x chưa nằm trong coords, không được đoán một rank rồi query. Cần nén lại, mở rộng cấu trúc một cách có chứng minh hoặc chọn miền số ngay từ đầu.

### 14.2. Cây động không đồng nghĩa miền không giới hạn

**Dynamic nodes** nghĩa là chỉ cấp phát nút khi chèn line, không phải tự động có miền x vô hạn. Vẫn cần biết root đại diện [L,R]. Muốn mở rộng miền sau khi thêm các line, phải xây một cơ chế đúng cho việc mở rộng và tái phân bổ, không được chỉ thay biến L,R.

Nếu dùng tọa độ long rất rộng, phép tính mid và `R−L+1` có thể tràn long. Chuyển sang BigInteger cho y(x) cũng không tự sửa lỗi tọa độ nếu giới hạn miền hoặc phân đôi vẫn dùng kiểu không đủ rộng.

### 14.3. Line chỉ có hiệu lực trên một đoạn con

Bản cơ bản ở đây thêm mỗi line cho **tất cả x thuộc [L,R]**. Nếu line chỉ hợp lệ tại `x∈[ql,qr]`, chèn nó vào root như line toàn miền có thể cho đáp án quá thấp ở những x ngoài đoạn.

Một hướng mở rộng là **segment Li Chao**: phân đoạn hiệu lực theo các nút segment tree, ở từng phần thích hợp sử dụng cơ chế Li Chao. Một số thiết kế cho thời gian thêm theo đoạn khoảng **O(log² D)**, nhưng chi phí cụ thể phụ thuộc cấu trúc và cách lưu. Phải chứng minh lại bất biến và tài nguyên; không tái dùng nguyên addLine của bản toàn miền mà không giới hạn hiệu lực.

### 14.4. Ứng viên bị xóa hoặc hết thời hạn

Li Chao cơ bản chỉ thêm và query, không hỗ trợ xóa một line đã đưa vào. Nếu DP chỉ cho phép một cửa sổ j hoặc một line có thời gian hết hạn, để line cũ trong cây có thể dẫn tới một min quá tốt nhưng **không hợp lệ**.

Các kỹ thuật nâng cao có thể dùng rollback Li Chao, phân đoạn trên **thời gian hiệu lực**, hoặc một cấu trúc thay thế. Đây là bài toán khác, không nên suy ra tính đúng từ bản chỉ có thêm đường.

## 15. Các lỗi dễ gặp

1. **Quên miền x:** query ngoài [L,R] không có bảo đảm đúng.
2. **Nhầm đoạn đóng và nửa mở:** ở mã này trái [l,mid], phải [mid+1,r]; không chồng điểm.
3. **Tràn khi tính mid:** cần phân tích phạm vi r−l và l+r.
4. **So sánh slope thay vì so y ở mid:** hai line còn có intercept và vị trí giao.
5. **Hoán đổi xong mới tính lại betterLeft/betterMid:** mất ý nghĩa bảng bốn trường hợp của thuật toán.
6. **Đẩy line xuống cả hai con:** không cần cho đường thẳng, tăng chi phí.
7. **Không dừng ở lá l=r:** đệ quy vô hạn hoặc khoảng rỗng.
8. **Dùng dấu lớn hơn cho truy vấn min:** tạo cấu trúc max ngoài ý muốn.
9. **Xử lý song song bằng chia giao điểm:** không có nghiệm giao khi intercept khác; so y trực tiếp là đủ.
10. **Dùng double cho đầu vào nguyên lớn:** có thể làm sai quan hệ nhỏ/lớn do sai số.
11. **Để `a*x+b` tràn long:** so sánh sai, cả cây có thể sai.
12. **Cây rỗng trả 0:** 0 có thể là một giá trị hợp lệ; dùng OptionalLong.empty hoặc hợp đồng riêng.
13. **Chỉ đọc line ở root khi query:** đường tốt nhất tại x có thể nằm ở nút con.
14. **Đổi miền sau khi addLine:** các nhánh được chọn theo miền cũ.
15. **Nhầm O(k) nút với O(D):** dynamic full-domain khác segment tree cấp phát dày.
16. **Chèn DP line i trước khi tính dp[i]:** vô tình dùng j=i.
17. **Dùng line toàn miền cho ứng viên chỉ hợp lệ trong khoảng:** cần phương pháp có xét thời hạn/đoạn.
18. **Nén tọa độ nhưng thay x thật bằng rank khi tính ax+b:** sai giá trị line.
19. **Không kiểm tra trường hợp hòa:** nếu trả line ID cần chính sách tie rõ.
20. **Giả định mọi hàm đều giao tối đa một lần:** Li Chao nguyên bản không đúng cho hàm tùy ý.

## 16. Kiểm thử đối chiếu độc lập

Một cách xác nhận mạnh là giữ danh sách line đơn giản song song với cây. Với mỗi query x, tính:

**`expected=min(a_j·x+b_j)`** bằng cách quét hết các line đang có. So với `minAt(x)`. Trên miền nhỏ như [-20,20], có thể sau **mỗi lần thêm** kiểm tra **toàn bộ x** trong miền, không chỉ một điểm ngẫu nhiên. Điều này bắt lỗi chọn nhầm nhánh rất hiệu quả.

| Thử nghiệm | Kỳ vọng |
|---|---|
| Chưa thêm line | `OptionalLong.empty()` |
| Miền một điểm [L,L] | Min tất cả line đánh giá tại L |
| x âm | add(2,3), minAt(-2)=-1 |
| Line hằng | add(0,1), có thể thắng ở một số x |
| Song song kém hơn | add(-1,5), add(-1,7), đáp án không đổi |
| Song song tốt hơn | thêm -x+2, có thể giảm min |
| Trùng line | add(2,3) hai lần, đáp án không đổi |
| Hòa | min(−4+5,1)=1 tại x=4 |
| Đúng hai biên L,R | Query hợp lệ |
| x ngoài miền | IllegalArgumentException |
| Hệ số vượt giới hạn demo | IllegalArgumentException |
| Thứ tự thêm đường đảo | Min cuối cùng của cùng tập vẫn như nhau |
| DP x=[0,1,3,4] | Giá trị cuối 6 |
| DP x ngẫu nhiên, âm/trùng | Đối chiếu hai vòng lặp O(n²) |

### Kiểm thử ngẫu nhiên

1. Sinh miền nguyên nhỏ, kể cả miền một điểm và miền chứa x âm.
2. Xen kẽ thêm các line có slope/intercept âm, 0, dương; cố tình tạo line song song và trùng nhau.
3. Sau khi thêm, query nhiều điểm hoặc tất cả điểm trong miền, so với quét trực tiếp.
4. Với bài DP bình phương, sinh `x[i]∈[−10,10]` và đối chiếu kết quả Li Chao với công thức O(n²), kể cả tọa độ lặp và thứ tự x không tăng.
5. Kiểm tra các yêu cầu API: cây rỗng, x ngoài miền, slope/intercept ngoài giới hạn.
6. Nếu bài cần ID line, kiểm thử riêng quy tắc phá hòa, không chỉ giá trị min.

Không nên kiểm thử bằng hai phiên bản Li Chao có cùng mã swap rồi xem chúng trùng nhau là đủ. **Brute force** hoặc công thức DP gốc là oracle độc lập đáng tin hơn trên đầu vào nhỏ.

## 17. Checklist trước khi dùng Li Chao trong DP

- Phép chuyển đã được biến đổi **đại số chính xác** thành `base(i)+min_j(a_j·x_i+b_j)` chưa?
- Line của j được thêm vào **đúng thời điểm j hợp lệ** và sau khi dp[j] đã biết chưa?
- Tập ứng viên có cần xóa hoặc chỉ hiệu lực trên một đoạn x không?
- Mọi x query có thuộc một miền đã khai báo không? Có x âm không?
- Miền được hiểu là tọa độ nguyên hay một tập tọa độ đã nén?
- Mỗi cặp hàm ứng viên có tính chất giao cắt cần thiết không?
- Phép đánh giá `a*x+b` và so sánh có an toàn trước tràn/sai số không?
- Cấu trúc đang lấy **min** hay **max**? Toán tử so sánh đã tương ứng chưa?
- Khi thêm, đường tốt hơn tại mid được giữ ở nút và đường còn lại được đẩy **một nhánh** chưa?
- Hai boolean `betterLeft` và `betterMid` có được lưu **trước swap** không?
- Khi query có đọc mọi line trên đường root→x không?
- Có xử lý cây rỗng, miền một điểm, x âm, slope trùng, hòa và x ngoài miền không?
- Đã tính độ phức tạp theo **D=R−L+1**, số lệnh add/query và bộ nhớ nút chưa?
- Khi nén tọa độ, phép đánh giá line dùng **coords[index]** thật chứ không dùng index chưa?
- Nếu bài yêu cầu argmin, đã lưu đủ ID và chính sách phá hòa chưa?
- Đã kiểm thử ngẫu nhiên bằng quét các line và DP O(n²) trên đầu vào nhỏ chưa?

**Ghi nhớ:** Li Chao tree khai thác tính chất **hai đường thẳng cắt nhau tối đa một lần**. Ta giữ line tốt tại trung điểm của một đoạn và chỉ đẩy line còn lại xuống phía có thể cải thiện; vì thế thêm và query mất **O(log D)** trên miền nguyên hữu hạn. Khi kết hợp với quy hoạch động, lợi ích lớn nhất đến từ việc đưa một bước chuyển O(n) về **một query và một add**, nhưng chỉ đúng nếu **miền x, thời điểm thêm line, toán học của phép chuyển và số học máy** đều được xử lý nhất quán.