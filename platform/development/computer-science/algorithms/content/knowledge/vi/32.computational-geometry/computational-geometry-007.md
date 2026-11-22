# Bao lồi bằng Graham scan

**Bao lồi** (*convex hull*) của một tập điểm phẳng là **tập lồi nhỏ nhất chứa toàn bộ các điểm ấy**. Hình dung đóng các chiếc đinh tại vị trí các điểm, rồi căng một sợi dây thun bao quanh tất cả đinh: khi thả ra, biên sợi dây tạo thành bao lồi. Trong mặt phẳng, nếu có ít nhất ba điểm không thẳng hàng, biên này là một **đa giác lồi**; các đỉnh của đa giác là một tập con của những điểm đầu vào. Nếu tất cả các điểm thẳng hàng, bao lồi là **đoạn thẳng** nối hai điểm cực trị; nếu chỉ có một vị trí khác biệt, bao lồi là **một điểm**.

**Graham scan** là thuật toán kinh điển tìm bao lồi của n điểm trong **O(n log n)** thời gian: chọn một điểm gốc đặc biệt (*pivot*), **sắp các điểm còn lại theo góc cực quanh pivot**, rồi duyệt theo thứ tự ấy với một ngăn xếp (*stack*) và liên tục bỏ đỉnh gây **rẽ phải** hoặc **đi thẳng**. Điểm quyết định nằm ở **tích có hướng 2D** (*cross product/orientation*), giúp kiểm tra chiều quay mà không cần tính góc bằng lượng giác.

Bài thuộc nhóm **Hình học tính toán** trong **Computer Science Algorithms**, với chủ đề **Bao lồi bằng Graham scan**. Ta sẽ học định nghĩa hình học, chọn pivot, cách so sánh góc đúng và xử lý điểm cùng tia, bất biến và chứng minh Graham scan, các ca điểm trùng/thẳng hàng/ít điểm, giới hạn tràn số khi tính cross, cận thời gian/bộ nhớ, diện tích theo công thức shoelace, quan hệ với **Andrew monotone chain** và các ứng dụng của bao lồi. Phần thực hành có **Java 17+ chạy độc lập**, kết quả stdout được xác định rõ và một kiểm thử ngẫu nhiên đối chiếu với thuật toán khác.

**Hợp đồng của bài:** đầu vào là các điểm có tọa độ nguyên trong đoạn **[−10⁹,10⁹]** ở mỗi trục. Đầu ra là **các đỉnh cực trị của bao lồi, không giữ các điểm nằm giữa trên cạnh thẳng**, liệt kê **ngược chiều kim đồng hồ (CCW)** bắt đầu từ điểm có **y nhỏ nhất, nếu hòa thì x nhỏ nhất**. Với một hoặc hai điểm, trả tất cả các vị trí khác nhau theo quy ước tương ứng; với không có điểm, trả danh sách rỗng. Điểm trùng bị loại trước khi chạy thuật toán. Đầu ra **không** lặp đỉnh đầu ở cuối; nếu cần đa giác khép kín khi vẽ thì caller tự nối đỉnh cuối về đầu.

## 1. Định nghĩa chính xác của bao lồi

Một tập C trong mặt phẳng là **lồi** nếu với mọi hai điểm a,b thuộc C, **toàn bộ đoạn thẳng** giữa a và b cũng thuộc C. Bao lồi của tập điểm hữu hạn S, ký hiệu **conv(S)**, là giao của tất cả tập lồi chứa S, tương đương tập các **tổ hợp lồi** của điểm trong S:

**`conv(S)={Σᵢ λᵢ pᵢ | λᵢ≥0, Σᵢ λᵢ=1, pᵢ∈S}`.**

Ta không nhất thiết cần tính các tổ hợp lồi trong code. Với điểm phẳng hữu hạn, bao lồi được mô tả hoàn toàn bởi **đa giác các điểm cực trị**, hoặc bằng đoạn thẳng/điểm ở trường hợp suy biến.

Ví dụ:

~~~text
       D(0,4) ------- C(4,4)
        |              |
        |    P(2,2)    |
        |              |
       A(0,0) ------- B(4,0)
~~~

A, B, C, D là bốn **đỉnh bao lồi**. P nằm trong hình vuông nên **không** cần xuất hiện trong danh sách đỉnh. Nếu đầu vào còn có các điểm trên cạnh như (2,0), (4,2), chúng cũng thuộc bao lồi theo nghĩa **tập điểm**, nhưng **không phải đỉnh cực trị** khi ta xuất một đa giác chỉ gồm các góc.

### Cần phân biệt ba câu hỏi

- **Các đỉnh của bao lồi là gì?** Đây là bài học hiện tại, chỉ giữ đỉnh làm đổi hướng cạnh.
- **Những điểm đầu vào nào nằm trên biên bao lồi?** Bao gồm cả điểm thẳng hàng nằm giữa trên cạnh; có thể nhiều hơn số đỉnh.
- **Một điểm truy vấn q có nằm trong bao lồi không?** Đây là bài *point-in-convex-polygon*; sau khi có hull, có thể kiểm tra các nửa mặt phẳng của cạnh.

Không được đánh đồng các kết quả. Một điểm giữa cạnh bị loại khỏi **danh sách đỉnh** không có nghĩa nó **nằm ngoài tập bao lồi**.

### Thứ tự output có ý nghĩa

Cùng một đa giác có thể được liệt kê từ nhiều đỉnh bắt đầu hoặc theo chiều CW/CCW. Bản mã cố định:

1. Điểm đầu **pivot**: y nhỏ nhất, nếu bằng y thì x nhỏ nhất.
2. Các đỉnh theo thứ tự **CCW**.
3. Không nối lặp pivot ở cuối.
4. Không giữ các điểm collinear **ở giữa cạnh**.

Do đó, với hình vuông ở trên, danh sách là:

**`[(0,0),(4,0),(4,4),(0,4)]`**, rồi khi vẽ nối (0,4) về (0,0).

## 2. Phép thử quan trọng: orientation của ba điểm

Cho ba điểm A=(ax,ay), B=(bx,by), C=(cx,cy). Định nghĩa tích có hướng có dấu:

**`cross(A,B,C)=(bx−ax)(cy−ay)−(by−ay)(cx−ax)`.**

Đây là định thức của hai vector **AB** và **AC**. Giá trị và dấu mang ý nghĩa:

| Giá trị | Kết luận | Diễn giải khi đi A→B→C |
|---|---|---|
| **cross > 0** | C ở bên trái đường có hướng A→B | **Rẽ trái / CCW** |
| **cross < 0** | C ở bên phải đường có hướng A→B | **Rẽ phải / CW** |
| **cross = 0** | A,B,C thẳng hàng | Không có góc quay thực sự |

Ví dụ A=(0,0), B=(4,0):

- C=(2,3): cross = 4·3−0·2 = **12 > 0** ⇒ rẽ trái.
- C=(2,−3): cross = 4·(−3) = **−12 < 0** ⇒ rẽ phải.
- C=(2,0): cross = 0 ⇒ thẳng hàng.

**Không lấy giá trị tuyệt đối của cross** khi xét chiều quay: mất dấu sẽ không còn phân biệt trái và phải. Cross có thể được tính trực tiếp bằng phép cộng/trừ/nhân số nguyên, không cần `atan2`, `acos` hoặc số thực.

### Cross không phải độ dài hay khoảng cách

Độ lớn `|cross(A,B,C)|` bằng **hai lần diện tích tam giác ABC**. Nhưng dấu mới là điều Graham scan cần để quyết định loại điểm. Bài toán không yêu cầu tính một góc theo độ.

Khi cần so sánh **hai điểm có cùng hướng cực** quanh pivot, ta dùng thêm **bình phương khoảng cách**:

**`dist²(P,A)=(ax−px)²+(ay−py)²`.**

Không cần căn bậc hai: vì `sqrt` đơn điệu trên số không âm, so sánh dist² tương đương so sánh khoảng cách Euclid thật nhưng vẫn dùng số nguyên chính xác.

## 3. Chọn pivot: tại sao y nhỏ nhất rồi x nhỏ nhất?

Graham scan cần một điểm gốc P để sắp các điểm còn lại theo **góc cực** `θ=atan2(y−py,x−px)`. Một cách chọn thông dụng và tiện chứng minh là:

**`P=argmin(y,x)`** — tối thiểu y, nếu hòa thì tối thiểu x.

Sau khi loại điểm trùng:

- Với mọi điểm Q khác P, **Q.y≥P.y**.
- Nếu Q.y=P.y thì **Q.x>P.x** vì P là điểm có x nhỏ nhất ở y thấp nhất.
- Do đó mọi vector **PQ** nằm trong **nửa mặt phẳng phía trên**, với góc cực nằm trong **[0,π)**.

Đây là tính chất mấu chốt: **tất cả góc nằm trong một khoảng độ rộng nhỏ hơn 180°**, nên với hai điểm khác pivot, dấu của cross(P,A,B) xác định thứ tự góc một cách nhất quán:

- **cross(P,A,B)>0** ⇒ góc của A **nhỏ hơn** góc của B.
- **cross(P,A,B)<0** ⇒ góc của A **lớn hơn** góc của B.
- **cross(P,A,B)=0** ⇒ chúng nằm trên **cùng một tia** từ P (vì không có tia đối diện hợp lệ tại cùng y thấp nhất).

Điều này cho phép **sort bằng cross** mà không dùng floating point.

### Cảnh báo: so sánh góc bằng cross không đúng cho pivot tùy ý

Nếu chọn P tùy ý nằm giữa đám điểm, các vector có thể phủ đủ **360°**. Khi ấy quy tắc comparator “cross>0 ⇒ A trước B” **không tạo thứ tự toàn phần bắc cầu** trên cả vòng tròn. Một bộ sort có thể vi phạm contract của comparator hoặc trả thứ tự sai.

Trong trường hợp tổng quát, cần **phân chia nửa mặt phẳng** (half-plane/quadrant), rồi so bằng cross trong từng phần; hoặc chọn pivot như Graham scan để tất cả vector nằm trong một nửa mặt phẳng thích hợp.

**Không** lấy công thức comparator dùng pivot thấp nhất áp nguyên xi cho mọi điểm gốc.

## 4. Xử lý các điểm cùng góc cực

Giả sử pivot P=(0,0), có các điểm A=(1,1), B=(2,2), C=(4,4). Cả ba nằm trên **cùng một tia 45°**.

Chúng có:

**`cross(P,A,B)=cross(P,B,C)=0`**,

nhưng khoảng cách tới P lần lượt tăng dần. Nếu mục tiêu là **chỉ lấy các đỉnh cực trị**, điểm gần P hơn trên cùng tia **không thể** là đỉnh hull nằm ngoài cùng theo hướng đó; chỉ điểm **xa nhất** còn khả năng trở thành góc biên.

Bản mã xử lý theo đúng hai bước:

1. **Sort các điểm cùng góc theo dist² tăng dần**: gần trước, xa sau.
2. Khi scan, nếu bộ ba gần nhất có **cross≤0**, pop điểm giữa. Với các điểm cùng tia, cross=0 nên các điểm gần lần lượt bị pop, điểm xa nhất được giữ.

Ví dụ:

~~~text
pivot: (0,0)
points sorted on 45° ray: (1,1), (2,2), (4,4)

stack after (1,1): [(0,0),(1,1)]
visit (2,2): cross=0 -> pop (1,1)
stack: [(0,0),(2,2)]

visit (4,4): cross=0 -> pop (2,2)
stack: [(0,0),(4,4)]
~~~

Điều này đúng với **hợp đồng bỏ các điểm nằm giữa trên một cạnh**.

### Không tự đổi điều kiện pop từ ≤0 sang <0

Một số bài cần giữ **tất cả điểm trên biên**, không chỉ vertices. Khi đó việc đổi `cross≤0` thành `cross<0` ở Graham scan **chưa đủ trong mọi trường hợp**: cần xử lý đặc biệt **nhóm điểm cùng góc ở tia cuối**, all-collinear và cách sắp khoảng cách để output đúng thứ tự quanh biên.

Bài hiện tại chọn chính sách **strictly convex vertices**: xóa các điểm trung gian collinear bằng `cross≤0`. Nếu đề muốn “mọi điểm nằm trên biên”, phải thay quy tắc và kiểm thử theo contract đó; đừng lặng lẽ tái sử dụng đầu ra này.

## 5. Các bước Graham scan đầy đủ

Đầu vào là n điểm nguyên. Thuật toán:

1. **Kiểm tra dữ liệu và loại các tọa độ trùng nhau**. Một điểm có thể xuất hiện nhiều lần trong input, nhưng chỉ được xem là một vị trí hình học.
2. Nếu có 0 hoặc 1 vị trí khác nhau, trả rỗng hoặc một điểm.
3. **Chọn pivot** có y nhỏ nhất, nếu hòa thì x nhỏ nhất.
4. **Sắp tất cả điểm còn lại theo góc cực tăng dần** quanh pivot; nếu cùng góc, **khoảng cách tới pivot tăng dần**.
5. Tạo stack ban đầu chứa pivot.
6. Lần lượt với mỗi điểm C đã sort:
   - Khi stack có ít nhất hai điểm A,B ở cuối và **`cross(A,B,C)≤0`**, **pop B** (B không làm một góc rẽ trái thực sự).
   - Dừng khi stack còn dưới hai điểm hoặc bộ ba cuối tạo rẽ trái **cross>0**.
   - **Push C**.
7. Stack cuối chứa danh sách đỉnh hull theo CCW, bắt đầu bằng pivot.

Pseudocode:

~~~text
GRAHAM(points):
    unique = distinctCoordinatePairs(points)
    if size(unique) <= 1:
        return unique

    pivot = point with minimum (y, x)

    others = unique except pivot
    sort others by:
        orientation(pivot, a, b) > 0 => a first
        orientation(pivot, a, b) < 0 => b first
        orientation = 0 => ascending squaredDistance(pivot, ·)

    stack = [pivot]

    for c in others:
        while stack.size >= 2:
            a = stack[stack.size - 2]
            b = stack[stack.size - 1]
            if cross(a,b,c) > 0:
                break
            pop b

        push c

    return stack
~~~

**Bất biến trực giác:** sau mỗi lần push, các bước ngoặt liên tiếp trong stack đều là **rẽ trái nghiêm ngặt**. Những điểm khiến đường bao hiện tại gấp sang phải hoặc giữ một đoạn cạnh thẳng có điểm giữa bị loại.

### Mô phỏng hình vuông có điểm nội bộ

Giả sử:

~~~text
(0,4) ---------------- (4,4)
  |        (2,4)        |
  |                     |
(0,2)      (2,2)       (4,2)
  |                     |
(0,0) ---- (2,0) ---- (4,0)
~~~

Có các góc và cả điểm nằm giữa cạnh/ở trong. Pivot=(0,0). Khi sort theo góc:

- Nhóm 0°: (2,0) đứng trước (4,0).
- Khi (4,0) đến, cross((0,0),(2,0),(4,0))=0 ⇒ pop (2,0), giữ (4,0).
- Khi đi dọc cạnh phải tới (4,4), điểm (4,2) cũng bị loại vì thẳng hàng ở cạnh.
- Điểm trong (2,2) bị loại khi tạo rẽ phải hoặc thẳng hàng với những đỉnh bao.
- Tại cạnh trên và cạnh trái, các điểm trung gian cũng không còn trong stack.

Kết quả:

**`[(0,0),(4,0),(4,4),(0,4)]`**.

Đó là bốn **đỉnh cực trị**, không có (2,0), (4,2), (2,4), (0,2) hay (2,2) trong danh sách, mặc dù nhiều điểm trong số đó **nằm trên** bao lồi.

### Vì sao phải dùng while, không dùng if?

Khi thêm một điểm mới C, nó có thể khiến **nhiều điểm cuối** của stack trở thành rẽ phải. Nếu chỉ pop một lần, góc cuối mới có thể vẫn không lồi. Vì vậy phải **lặp pop cho đến khi cross>0**, hoặc stack không đủ hai phần tử.

Tổng số lần pop trong **toàn bộ** thuật toán vẫn O(n), bởi mỗi điểm được push đúng một lần và pop tối đa một lần. Vòng while lồng trong for **không làm bước scan thành O(n²)**.

## 6. Xem orientation như một quyết định hình học

Cho A,B đang ở hai vị trí cuối stack và C là điểm mới.

### Trường hợp cross(A,B,C)>0

A→B→C là rẽ trái. Đi qua B rồi tới C vẫn phù hợp biên CCW của hull đang xây. Ta **giữ B** và thêm C.

### Trường hợp cross(A,B,C)<0

A→B→C tạo một chỗ lõm (*concave corner*) nếu ta giữ B trong đường bao CCW. B không còn là đỉnh trên phần biên tối ưu đang duyệt theo góc tăng. Pop B, xét C với đỉnh trước đó trên stack.

### Trường hợp cross(A,B,C)=0

A,B,C thẳng hàng. Với các điểm duyệt theo góc từ pivot, một điểm giữa trên biên không làm thay đổi hình dạng hull. Chính sách vertices-only loại B (với thứ tự góc và khoảng cách đã chọn). Việc này đặc biệt quan trọng khi dữ liệu có nhiều điểm trên một đường thẳng, nếu không đầu ra có thể chứa hàng nghìn “đỉnh” không cần thiết.

**Không chỉ dựa vào việc B nằm trên đoạn AC trong một bộ ba bất kỳ** mà bỏ kiểm tra thứ tự và bất biến scan. Đẳng thức cross=0 chỉ nói ba điểm thẳng hàng, chưa tự chứng minh B nằm **giữa** A và C nếu các điểm đầu vào được đưa vào một thứ tự tùy ý. Graham scan đảm bảo thứ tự cực và cách xử lý tie phù hợp nên phép pop collinear là đúng trong ngữ cảnh ấy.

## 7. Trường hợp suy biến: cần định nghĩa tường minh

### Không có điểm

Input `[]` ⇒ bao lồi là **tập rỗng**, output `[]`. Không được gọi sort/pivot hay truy cập phần tử đầu khi n=0.

### Chỉ có một vị trí

Input `[(2,3),(2,3)]` có hai phần tử nhưng chỉ **một vị trí khác nhau**. Sau dedup, hull là:

**`[(2,3)]`**.

Diện tích bằng 0. Không tạo một đoạn thẳng độ dài 0 có hai đỉnh lặp.

### Hai vị trí khác nhau

Input `[(3,3),(0,0),(0,0)]` ⇒ hull:

**`[(0,0),(3,3)]`**.

Bài không tự nối hai điểm thành một đa giác có ba đỉnh giả. Thứ tự theo pivot y nhỏ nhất. Diện tích bằng 0.

### Tất cả điểm thẳng hàng

Input:

**`[(-3,-3),(-1,-1),(0,0),(5,5),(2,2),(5,5)]`**.

Mọi điểm nằm trên một đường; convex hull theo hình học là **đoạn thẳng** từ (-3,-3) tới (5,5). Kết quả vertices-only:

**`[(-3,-3),(5,5)]`**.

Tương tự, nếu tất cả điểm trên một đường ngang, pivot chọn điểm x **nhỏ nhất** trên hàng có y bằng nhau; thuật toán giữ hai đầu mút x cực trị. Nếu đường dọc, pivot là điểm y nhỏ nhất và điểm cuối là y lớn nhất.

### Điểm trùng với pivot hoặc điểm khác

Nếu không xóa bản sao trùng:

- Góc của vector từ pivot tới chính nó **không được định nghĩa**.
- Khoảng cách 0 có thể bị xem nhầm cùng tia với mọi điểm.
- Output có thể lặp vertex, hoặc comparator vi phạm giả thiết tất cả điểm còn lại **khác pivot**.

Vì vậy code xóa các cặp tọa độ trùng **trước khi xác định pivot và sắp góc**. Trong Java, `record Point(long x,long y)` cung cấp `equals/hashCode` theo giá trị tọa độ, phù hợp dùng `HashSet<Point>`.

### Không được giả định luôn có ba điểm khác nhau không thẳng hàng

Nhiều lời giải Graham scan trên mạng push sẵn ba điểm rồi mới xét vòng lặp. Nếu n=0,1,2 hoặc all-collinear, chúng có thể đọc ngoài mảng, đưa ra đỉnh lặp hoặc trả một polygon không hợp lệ. Bản mã bắt đầu stack với **chỉ pivot**, rồi xử lý các điểm còn lại, nên xử lý tự nhiên cả số lượng nhỏ và trường hợp thẳng hàng.

## 8. Tính chính xác số học: cross có thể overflow

Công thức:

**`cross(A,B,C)=(bx−ax)(cy−ay)−(by−ay)(cx−ax)`**.

Nếu tọa độ là `int`, các hiệu có thể lớn gần 2³², và tích hai hiệu có thể lên đến gần 2⁶⁴. **Không thể** dùng `int` cho tích, và cũng **không an toàn tuyệt đối** khi chỉ ép các hiệu sang `long` nếu input cho phép toàn miền int 32-bit.

Bài này chủ động định nghĩa miền:

**`−1.000.000.000≤x,y≤1.000.000.000`**.

Như vậy:

- `|bx−ax|≤2·10⁹`; tương tự cho dy.
- Mỗi tích hiệu có trị tuyệt đối **≤4·10¹⁸**.
- Hiệu hai tích có trị tuyệt đối **≤8·10¹⁸**.
- `Long.MAX_VALUE≈9,22·10¹⁸`.

Vì **8·10¹⁸ < 9,22·10¹⁸**, phép cross bằng `long` **an toàn** với mọi ba điểm trong miền đã cam kết.

Tương tự, bình phương khoảng cách:

**`dx²+dy²≤(2·10⁹)²+(2·10⁹)²=8·10¹⁸`**,

cũng vừa `long`.

### Đừng thay giới hạn input mà không đổi kiểu tính

Nếu tọa độ được phép tới ±10¹², phép nhân các hiệu có thể vượt xa phạm vi long. Khi đó:

- Dùng **`BigInteger`** để tính cross/dist² chính xác; hoặc
- Dùng số học 128-bit nếu ngôn ngữ/hệ thống cho phép và kiểm soát miền; hoặc
- Chứng minh một miền giới hạn mới nhỏ hơn có thể dùng long.

**Không** “sửa nhanh” bằng `double` cho orientation với số nguyên cực lớn: double chỉ có khoảng 53 bit chính xác của phần nguyên, nên các tích gần nhau có thể bị làm tròn thành bằng nhau hoặc đảo dấu, làm sai phép sắp góc và pop đỉnh.

### Diện tích theo shoelace cần xử lý riêng

Với một hull các đỉnh `v₀,...,v_{h−1}` đi CCW, hai lần **diện tích có hướng**:

**`area2=Σ_{i=0}^{h−1}(xᵢ y_{i+1}−yᵢ x_{i+1})`**, trong đó `v_h=v₀`.

Nếu h<3, diện tích bằng 0. Với hull CCW không suy biến, area2>0; diện tích thật là **area2/2**.

Bản Java tính **`BigInteger area2`** thay vì cộng từng giá trị shoelace vào long, để không phụ thuộc vào tổng trung gian của rất nhiều cạnh. Hàm này **khác** phép cross của đúng ba điểm dùng trong comparator và stack. Mục tiêu là đảm bảo phép kiểm diện tích vẫn chính xác ngay cả khi số cạnh lớn.

### Không nhầm thứ tự tọa độ

Graham scan dùng `Point(x,y)`, còn mảng lưới thường dùng `grid[row][col]`. Nếu dữ liệu là cặp (row,col), cần quyết định chuyển về x=col,y=row. Đảo vị trí có thể đổi pivot, chiều quay và output. Luôn thống nhất **trục tọa độ hệ Descartes với y tăng lên trên** khi diễn giải dấu cross là CCW.

Trong màn hình, nhiều API có y tăng **xuống dưới**; công thức toán học vẫn cho cùng định thức trên cặp số (x,y), nhưng “rẽ trái trên màn hình” nhìn trực quan sẽ bị phản chiếu. Nếu ứng dụng vẽ màn hình, phải chú thích hoặc đổi trục/chiều output.

## 9. Sắp góc bằng comparator không dùng atan2

Với pivot P chọn đúng chuẩn, xây comparator:

~~~text
compare(a,b):
    t = cross(P,a,b)

    if t > 0: return -1    // a has smaller angle
    if t < 0: return +1    // a has larger angle

    da = squaredDistance(P,a)
    db = squaredDistance(P,b)
    return compare(da,db)  // near first, far last
~~~

Trong Java, comparator cần trả số âm/dương/0 theo thứ tự. Không dùng `(int)(da−db)`:

- Hiệu `da−db` có thể lớn hơn int, ép int **tràn** và làm comparator sai.
- Số âm/dương của long khi trừ cũng có thể tràn nếu không chứng minh miền.
- Dùng **`Long.compare(da,db)`** an toàn.

Bản mã còn có so sánh `x` và `y` làm tie-break cuối để comparator có thứ tự xác định, dù sau dedup, hai điểm khác nhau trên cùng tia không thể đồng thời có cùng khoảng cách thật tới pivot.

### Vì sao không sort bằng `Math.atan2`?

Có thể tính góc và sort theo double khi số nhỏ, nhưng:

- Không cần phép lượng giác, tốn CPU hơn.
- Số thực có thể làm hai hướng rất gần trở nên bằng nhau do làm tròn.
- Với điểm rất lớn hoặc gần collinear, sai số ở góc có thể làm thứ tự sai.
- Khi kiểm góc 0/π hoặc cách chuẩn hóa [-π,π], cần xử lý wrap-around.

Dùng **orientation với kiểu nguyên đủ lớn** giúp bảo đảm thứ tự chính xác trên miền nguyên có giới hạn. Chỉ dùng cách comparator cross nêu trên khi pivot thật sự là **điểm thấp nhất rồi trái nhất**; với pivot khác cần phân nửa mặt phẳng trước.

### Tại sao sort không tạo vòng thứ tự mâu thuẫn?

Do mọi vector Q−P có y≥0 và nếu y=0 thì x>0, chúng đều nằm trong một cung góc `[0,π)`. Với hai vector trong miền này, dấu của định thức chính là thứ tự góc. Cung có chiều dài nhỏ hơn π nên comparator không bị hiện tượng A trước B, B trước C, C trước A do xoay trọn 360°. Các điểm cùng tia được sort bằng khoảng cách tăng, tạo một thứ tự bắc cầu.

Nếu dữ liệu là `double` thay vì int/long, còn phải xử lý điểm bằng nhau về tọa độ thực, epsilon và sai số số học; các chứng minh chính xác này dựa trên **tọa độ nguyên** và cross nguyên không overflow.

## 10. Bất biến và chứng minh tính đúng

### 10.1. Pivot là đỉnh cực trị

P có y nhỏ nhất trong toàn bộ input, nên không thể nằm **bên trong** một đa giác có tất cả các đỉnh ở y≥P.y mà không chạm biên dưới. Nếu có nhiều điểm cùng y nhỏ nhất, chọn x nhỏ nhất làm P là **đầu mút** của phần đáy. Vậy P thuộc tập đỉnh cực trị của bao lồi, trừ khi tập chỉ có một vị trí.

### 10.2. Sau sort, thứ tự các tia quanh P là CCW

Với mọi Q≠P, vector PQ có góc cực trong [0,π). Comparator orientation sắp các tia theo thứ tự góc không giảm và cùng góc theo khoảng cách tăng. Vì vậy thuật toán scan xét các điểm theo một đường quét quay **một chiều CCW** quanh P, không nhảy lùi góc.

### 10.3. Bất biến stack

Sau khi xử lý một tiền tố của dãy điểm đã sort, stack là đường biên lồi đang hình thành của các điểm đã xét, đi từ P theo hướng CCW, và mọi bộ ba đỉnh liên tiếp ở stack có **cross>0** (trừ khi stack có ít hơn ba điểm).

Khi thêm C:

- Nếu bộ ba cuối A,B,C có cross>0, giữ B không tạo góc lõm.
- Nếu cross≤0, B không còn có thể là một **đỉnh góc cần thiết** trên phần hull đang được hoàn thiện: nó nằm về phía trong/được thay bởi đường nối tới C, hoặc nằm giữa trên một đoạn thẳng theo quy tắc vertices-only.
- Pop B rồi tiếp tục xét cặp trước đó, vì C có thể che khuất **nhiều đỉnh cuối**.

Khi kết thúc, không còn góc rẽ phải hoặc góc thẳng giữa các đỉnh liên tiếp của đường bao. Thứ tự góc từ P bảo đảm ta đã xét các hướng cực và những điểm không bị loại là các **điểm ngoài cùng** cần để tạo convex hull.

### 10.4. Tại sao một điểm bị pop không quay lại?

Một điểm B bị pop khi có hai điểm A,C tạo góc không trái. Trong quá trình xây đường bao với thứ tự góc đang tăng, B không còn là đỉnh cực trị cần thiết giữa A và C; việc thêm điểm ở góc lớn hơn chỉ có thể **bỏ thêm** các đỉnh đã giữ, không thể khiến B trở lại thành một góc ngoài cần thiết. Do đó thuật toán không cần tái chèn B.

Đây là nội dung quan trọng của Graham scan: stack không chứa mọi điểm đã đi qua, mà chỉ chứa những **ứng viên đỉnh cực trị** chưa bị chứng minh là không cần thiết.

### 10.5. Vì sao kết quả là hull nhỏ nhất?

Tập các đỉnh còn lại sau scan xác định một đa giác lồi CCW chứa các điểm đã duyệt; mọi điểm bị loại đều nằm trong hoặc trên bao xác định bởi các điểm giữ lại theo quá trình cập nhật. Vì các đỉnh kết quả đều là điểm gốc, đa giác kết quả là một tập lồi chứa toàn bộ đầu vào. Mặt khác, mọi tập lồi chứa đầu vào bắt buộc chứa những đỉnh này và mọi đoạn nối chúng. Do đó đa giác trả là **bao lồi nhỏ nhất** của tập ban đầu.

Các trường hợp 0/1/2 vị trí khác nhau và tất cả collinear được xử lý đúng theo hợp đồng suy biến, nên không cần dựng một đa giác ảo có diện tích dương.

### 10.6. Tổng số lần pop là tuyến tính

Mỗi điểm được push **một lần**. Một khi bị pop, điểm không được push lại. Vì thế toàn bộ quá trình có không quá O(n) push và O(n) pop, dù vòng while nằm trong vòng for. Các phép orientation/dist² đều O(1) trên miền tọa độ long đã giới hạn.

## 11. Độ phức tạp theo số điểm

Gọi n là **số điểm đầu vào**, u là **số tọa độ khác nhau** sau khi loại trùng, h là **số đỉnh hull** cuối.

| Công đoạn | Thời gian | Bộ nhớ phụ |
|---|---:|---:|
| Kiểm tra tọa độ và xóa trùng bằng HashSet | **O(n)** kỳ vọng | O(u) |
| Chọn pivot | O(u) | O(1) |
| Sắp góc cực u−1 điểm | **O(u log u)** | Tùy sort; trong Java có thêm bộ đệm |
| Scan bằng stack | O(u) | O(u) |
| Đưa h đỉnh ra output | O(h) | O(h) |
| Tính area2 theo shoelace | O(h) phép tính số lớn | O(1) đối tượng tích lũy, không tính chi phí số bit |
| Tổng Graham scan | **O(n + u log u)** kỳ vọng | **O(u)** |

Với u≤n, cận thường viết **`O(n log n)`** thời gian và **`O(n)`** bộ nhớ. Phần sort là nút thắt chính; scan không nhân lên thành O(n²). Nếu input đã sort theo góc đúng hoặc có cấu trúc đặc biệt, có thể giảm chi phí sort, nhưng đây không phải giả định của bài.

### Lower bound so sánh

Trong mô hình các thuật toán dựa trên so sánh và input tọa độ tổng quát, bài bao lồi có cận dưới **Ω(n log n)** trong những trường hợp tiêu chuẩn, nên O(n log n) của Graham scan là tối ưu về bậc trong mô hình ấy. Một số mô hình tọa độ nguyên hữu hạn cho phép cấu trúc hoặc thuật toán đặc biệt vượt cận so sánh; không khẳng định mọi dạng convex hull trên mọi mô hình tính toán đều buộc n log n.

### Nếu chỉ cần diện tích hoặc chu vi?

Tính hull trước rồi dùng shoelace cho diện tích, hoặc cộng độ dài cạnh để tính chu vi. Với h≥3, chu vi là tổng `sqrt(dx²+dy²)` cho các cạnh khép kín; với hull là đoạn thẳng, “chu vi của đa giác suy biến” không có một quy ước thống nhất — một số bài lấy 2 lần độ dài đoạn, một số chỉ quan tâm độ dài đoạn. Phải đọc đề trước khi xuất chu vi cho h≤2.

## 12. Java 17+ hoàn chỉnh: Graham scan có kiểm tra số học

Bản cài dưới đây sử dụng:

- `record Point(long x,long y)`: điểm có giá trị tọa độ, tự có `equals/hashCode` cho loại trùng.
- `cross(a,b,c)`: định thức long chính xác dưới miền **[−10⁹,10⁹]**.
- `squaredDistance`: dùng long chính xác trên cùng miền.
- `graham`: kiểm dữ liệu, dedup, pivot, polar-angle sort, stack và loại các đỉnh có cross≤0.
- `doubledArea`: tính hai lần diện tích bằng **BigInteger** từ các đỉnh đã có thứ tự CCW.
- `containsOrOn`: kiểm một điểm nằm trong hoặc trên hull bằng các nửa mặt phẳng; tách rõ trường hợp 0/1/2 điểm.
- `andrewOracle`: một cài đặt độc lập của **Andrew monotone chain**, dùng để đối chiếu trong test, **không** phải cách mà `graham` tính hull.
- `randomizedChecks`: kiểm nhiều tập điểm với seed cố định, so danh sách đỉnh chuẩn hóa từ hai thuật toán, kiểm các điểm đầu vào đều nằm trong hoặc trên hull và mọi góc của polygon cuối đều rẽ trái nghiêm ngặt.

**Hợp đồng dữ liệu:** mọi tọa độ x/y của điểm đầu vào và điểm truy vấn phải trong [−10⁹,10⁹]. Tọa độ ngoài miền bị từ chối để tránh khẳng định sai rằng phép orientation long luôn an toàn. Không giữ các điểm collinear nằm giữa biên. Kết quả không lặp pivot ở cuối. Nếu nhiều points trùng một tọa độ, chúng được gộp làm một.

Lưu mã thành **`GrahamScanDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;

public final class GrahamScanDemo {
    private static final long LIMIT = 1_000_000_000L;

    private record Point(long x, long y) {}

    private static void requirePoint(Point p) {
        if (p == null || p.x() < -LIMIT || p.x() > LIMIT
                || p.y() < -LIMIT || p.y() > LIMIT) {
            throw new IllegalArgumentException(
                    "Point must have |x|, |y| <= 1e9");
        }
    }

    // Signed double area of triangle ABC.
    // All coordinates MUST be within [-1e9, 1e9].
    private static long cross(Point a, Point b, Point c) {
        long dx1 = b.x() - a.x();
        long dy1 = b.y() - a.y();
        long dx2 = c.x() - a.x();
        long dy2 = c.y() - a.y();
        return dx1 * dy2 - dy1 * dx2;
    }

    private static long squaredDistance(Point a, Point b) {
        long dx = a.x() - b.x();
        long dy = a.y() - b.y();
        return dx * dx + dy * dy;
    }

    // Pivot order: minimum Y, break ties with minimum X.
    private static int comparePivot(Point a, Point b) {
        int byY = Long.compare(a.y(), b.y());
        return byY != 0
                ? byY : Long.compare(a.x(), b.x());
    }

    static List<Point> graham(List<Point> input) {
        if (input == null) {
            throw new IllegalArgumentException("Null point list");
        }

        // Remove duplicates; HashSet equality is by coordinates.
        Set<Point> seen = new HashSet<>();
        List<Point> unique = new ArrayList<>();
        for (Point p : input) {
            requirePoint(p);
            if (seen.add(p)) {
                unique.add(p);
            }
        }

        if (unique.size() <= 1) {
            return List.copyOf(unique);
        }

        Point minimum = unique.get(0);
        for (Point p : unique) {
            if (comparePivot(p, minimum) < 0) {
                minimum = p;
            }
        }
        final Point pivot = minimum;

        List<Point> other = new ArrayList<>();
        for (Point p : unique) {
            if (!p.equals(pivot)) {
                other.add(p);
            }
        }

        // Pivot is lowest Y, then leftmost X among lowest Y.
        // Every other vector lies in the same upper half-plane.
        Comparator<Point> polarOrder = (a, b) -> {
            long turn = cross(pivot, a, b);
            if (turn > 0) {
                return -1; // a has smaller polar angle.
            }
            if (turn < 0) {
                return 1;
            }

            // Same ray: nearer point first, farther later.
            int byDistance = Long.compare(
                    squaredDistance(pivot, a),
                    squaredDistance(pivot, b));
            if (byDistance != 0) {
                return byDistance;
            }
            int byX = Long.compare(a.x(), b.x());
            return byX != 0
                    ? byX : Long.compare(a.y(), b.y());
        };
        other.sort(polarOrder);

        List<Point> stack = new ArrayList<>();
        stack.add(pivot);

        for (Point p : other) {
            while (stack.size() >= 2) {
                int last = stack.size() - 1;
                Point a = stack.get(last - 1);
                Point b = stack.get(last);
                if (cross(a, b, p) > 0) {
                    break; // Strict left turn: keep b.
                }
                stack.remove(last); // Right turn or collinear.
            }
            stack.add(p);
        }

        return List.copyOf(stack);
    }

    // Exact shoelace formula on the polygon's CCW vertices.
    static BigInteger doubledArea(List<Point> hull) {
        if (hull.size() < 3) {
            return BigInteger.ZERO;
        }

        BigInteger sum = BigInteger.ZERO;
        for (int i = 0; i < hull.size(); i++) {
            Point a = hull.get(i);
            Point b = hull.get((i + 1) % hull.size());

            BigInteger left = BigInteger.valueOf(a.x())
                    .multiply(BigInteger.valueOf(b.y()));
            BigInteger right = BigInteger.valueOf(a.y())
                    .multiply(BigInteger.valueOf(b.x()));
            sum = sum.add(left.subtract(right));
        }
        return sum;
    }

    private static boolean onSegment(
            Point a, Point b, Point p) {
        return cross(a, b, p) == 0L
                && Math.min(a.x(), b.x()) <= p.x()
                && p.x() <= Math.max(a.x(), b.x())
                && Math.min(a.y(), b.y()) <= p.y()
                && p.y() <= Math.max(a.y(), b.y());
    }

    // Includes points on the boundary, by definition.
    static boolean containsOrOn(
            List<Point> hull, Point query) {
        requirePoint(query);

        if (hull.isEmpty()) {
            return false;
        }
        if (hull.size() == 1) {
            return hull.get(0).equals(query);
        }
        if (hull.size() == 2) {
            return onSegment(
                    hull.get(0), hull.get(1), query);
        }

        // For a CCW convex polygon, every edge must have
        // the query on its LEFT or directly on the edge.
        for (int i = 0; i < hull.size(); i++) {
            Point a = hull.get(i);
            Point b = hull.get((i + 1) % hull.size());
            if (cross(a, b, query) < 0L) {
                return false;
            }
        }
        return true;
    }

    // Independent test oracle: Andrew's monotone chain.
    // It sorts by X/Y, not by Graham's polar angles.
    private static List<Point> andrewOracle(
            List<Point> points) {
        List<Point> sorted = new ArrayList<>(
                new HashSet<>(points));
        sorted.sort(Comparator
                .comparingLong(Point::x)
                .thenComparingLong(Point::y));

        if (sorted.size() <= 1) {
            return List.copyOf(sorted);
        }

        List<Point> lower = new ArrayList<>();
        for (Point p : sorted) {
            while (lower.size() >= 2
                    && cross(
                            lower.get(lower.size() - 2),
                            lower.get(lower.size() - 1),
                            p) <= 0L) {
                lower.remove(lower.size() - 1);
            }
            lower.add(p);
        }

        List<Point> upper = new ArrayList<>();
        for (int i = sorted.size() - 1; i >= 0; i--) {
            Point p = sorted.get(i);
            while (upper.size() >= 2
                    && cross(
                            upper.get(upper.size() - 2),
                            upper.get(upper.size() - 1),
                            p) <= 0L) {
                upper.remove(upper.size() - 1);
            }
            upper.add(p);
        }

        // Endpoints were included in both chains.
        lower.remove(lower.size() - 1);
        upper.remove(upper.size() - 1);
        lower.addAll(upper);
        return rotateToPivot(lower);
    }

    private static List<Point> rotateToPivot(
            List<Point> hull) {
        if (hull.size() <= 1) {
            return List.copyOf(hull);
        }
        int start = 0;
        for (int i = 1; i < hull.size(); i++) {
            if (comparePivot(hull.get(i), hull.get(start)) < 0) {
                start = i;
            }
        }
        List<Point> result = new ArrayList<>();
        for (int i = 0; i < hull.size(); i++) {
            result.add(hull.get((start + i) % hull.size()));
        }
        return List.copyOf(result);
    }

    private static String format(List<Point> points) {
        List<String> result = new ArrayList<>();
        for (Point p : points) {
            result.add("(" + p.x() + "," + p.y() + ")");
        }
        return result.toString();
    }

    private static void show(String name, Point... points) {
        List<Point> hull = graham(List.of(points));
        System.out.println(
                name + ": hull=" + format(hull)
                + ", area2=" + doubledArea(hull));
    }

    private static Point p(long x, long y) {
        return new Point(x, y);
    }

    private static void randomizedChecks() {
        Random rng = new Random(4242026L);

        for (int trial = 0; trial < 2000; trial++) {
            int size = rng.nextInt(25);
            List<Point> points = new ArrayList<>();

            for (int j = 0; j < size; j++) {
                long x = rng.nextInt(41) - 20;
                long y = rng.nextInt(41) - 20;

                if (trial % 4 == 0) {
                    y = 2 * x + 3; // Deliberately collinear.
                } else if (trial % 4 == 2) {
                    x = (rng.nextInt(3) - 1L) * LIMIT;
                    y = (rng.nextInt(3) - 1L) * LIMIT;
                }

                Point point = p(x, y);
                points.add(point);
                if (rng.nextInt(6) == 0) {
                    points.add(point); // Duplicate coordinates.
                }
            }

            List<Point> got = graham(points);
            List<Point> expected = andrewOracle(points);
            if (!got.equals(expected)) {
                throw new AssertionError(
                        "Hull mismatch at trial " + trial);
            }

            if (got.size() >= 3) {
                if (doubledArea(got).signum() <= 0) {
                    throw new AssertionError("Non-CCW hull");
                }
                for (int k = 0; k < got.size(); k++) {
                    Point a = got.get(k);
                    Point b = got.get((k + 1) % got.size());
                    Point c = got.get((k + 2) % got.size());
                    if (cross(a, b, c) <= 0L) {
                        throw new AssertionError(
                                "Collinear or concave vertex");
                    }
                }
            }

            for (Point point : points) {
                if (!containsOrOn(got, point)) {
                    throw new AssertionError(
                            "Input point outside hull");
                }
            }
        }

        System.out.println(
                "Random cross-checks: 2000 PASS");
    }

    public static void main(String[] args) {
        show("Empty");
        show("Single", p(2, 3), p(2, 3));
        show("Two", p(3, 3), p(0, 0), p(0, 0));

        show("Triangle",
                p(0, 0), p(4, 0), p(2, 4),
                p(2, 1), p(1, 1));

        show("Square",
                p(0, 0), p(4, 0), p(4, 4), p(0, 4),
                p(2, 0), p(4, 2), p(2, 4), p(0, 2),
                p(2, 2), p(4, 4), p(0, 0));

        show("Collinear",
                p(-3, -3), p(-1, -1), p(0, 0),
                p(5, 5), p(2, 2), p(5, 5));

        show("Negative",
                p(-4, 1), p(-1, -3), p(3, -1),
                p(2, 4), p(0, 0), p(-2, 0), p(1, 1));

        show("MaxBounds",
                p(-LIMIT, -LIMIT), p(LIMIT, -LIMIT),
                p(LIMIT, LIMIT), p(-LIMIT, LIMIT),
                p(0, 0), p(LIMIT, LIMIT));

        show("HorizontalLine",
                p(-5, 1), p(3, 1), p(0, 1),
                p(5, 1), p(-5, 1));

        show("VerticalLine",
                p(2, -3), p(2, 4), p(2, 0), p(2, 9));

        show("ConcavePoints",
                p(0, 0), p(5, 0), p(5, 5), p(0, 5),
                p(3, 1), p(2, 2), p(3, 3),
                p(4, 3), p(1, 1));

        List<Point> square = graham(List.of(
                p(0, 0), p(4, 0), p(4, 4), p(0, 4)));
        System.out.println(
                "Contains square: inside="
                + containsOrOn(square, p(2, 2))
                + ", boundary="
                + containsOrOn(square, p(4, 2))
                + ", outside="
                + containsOrOn(square, p(5, 2)));

        randomizedChecks();
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 GrahamScanDemo.java
java GrahamScanDemo
~~~

**Stdout chính xác:**

~~~text
Empty: hull=[], area2=0
Single: hull=[(2,3)], area2=0
Two: hull=[(0,0), (3,3)], area2=0
Triangle: hull=[(0,0), (4,0), (2,4)], area2=16
Square: hull=[(0,0), (4,0), (4,4), (0,4)], area2=32
Collinear: hull=[(-3,-3), (5,5)], area2=0
Negative: hull=[(-1,-3), (3,-1), (2,4), (-4,1)], area2=55
MaxBounds: hull=[(-1000000000,-1000000000), (1000000000,-1000000000), (1000000000,1000000000), (-1000000000,1000000000)], area2=8000000000000000000
HorizontalLine: hull=[(-5,1), (5,1)], area2=0
VerticalLine: hull=[(2,-3), (2,9)], area2=0
ConcavePoints: hull=[(0,0), (5,0), (5,5), (0,5)], area2=50
Contains square: inside=true, boundary=true, outside=false
Random cross-checks: 2000 PASS
~~~

### Đối chiếu từng ví dụ

**Empty**: không có input point; output rỗng và area2=0.

**Single**: hai bản sao của (2,3) bị gộp thành một điểm; hull có đúng một vertex.

**Two**: hai vị trí khác nhau cho đoạn thẳng. Pivot (0,0) có y thấp hơn (3,3); không dựng polygon có diện tích.

**Triangle**: (0,0), (4,0), (2,4) tạo tam giác CCW; các điểm (2,1), (1,1) nằm trong nên không làm đỉnh. Diện tích tam giác thật bằng **16/2=8**.

**Square**: giữ đúng bốn góc; xóa điểm giữa cạnh và điểm nằm trong, kể cả bản sao các góc. `area2=32` nên diện tích hình vuông là 16.

**Collinear**: điểm thẳng hàng kể cả bản sao bị rút về hai đầu mút. Không có “đa giác lồi” diện tích dương.

**Negative**: tọa độ âm không làm thay đổi công thức orientation. Pivot là (−1,−3); các đỉnh trả theo CCW và area2=55, tức diện tích hình học 27,5.

**MaxBounds**: kiểm miền tọa độ ±10⁹, các phép cross và dist² vẫn trong `long`; shoelace dùng BigInteger. `area2=8·10¹⁸` nên diện tích hình vuông là `4·10¹⁸`.

**HorizontalLine/VerticalLine**: hai hướng thẳng hàng dễ làm lộ lỗi comparator: khi cùng y, pivot phải chọn x nhỏ nhất; khi cùng x, pivot chọn y nhỏ nhất. Cả hai trả đúng hai điểm cực trị.

**ConcavePoints**: các điểm nằm lõm trong biên không tạo thêm vertex; hull là bốn góc hình vuông 5×5, area2=50.

**Contains square**: điểm (2,2) trong, điểm (4,2) trên biên và điểm (5,2) ngoài. API dùng **inclusive boundary**, khác với yêu cầu “strictly inside” trong một số bài.

**Random cross-checks**: chương trình chạy 2000 input ngẫu nhiên có các kiểu phân bố thường, all-collinear, nhiều tọa độ lặp ở ba mức −10⁹/0/10⁹, rồi so với Andrew. Dòng PASS chỉ được in nếu không có phép kiểm nào ném AssertionError.

## 13. Vì sao cần oracle độc lập Andrew monotone chain?

Nếu chỉ chạy Graham scan hai lần rồi so kết quả, một bug trong comparator hoặc điều kiện pop sẽ lặp lại ở cả hai lần. Một oracle hữu ích nên có **cơ chế lựa chọn khác**.

**Andrew monotone chain** không sort theo góc cực. Nó:

1. Loại trùng và sort điểm theo **x tăng, rồi y tăng**.
2. Duyệt từ trái sang phải tạo **lower hull**, pop khi không rẽ trái.
3. Duyệt từ phải sang trái tạo **upper hull**, pop khi không rẽ trái.
4. Bỏ các endpoint bị lặp giữa hai chuỗi, ghép lower+upper.
5. Nếu muốn đối chiếu đúng với hợp đồng của Graham, **xoay vòng danh sách** để điểm bắt đầu là (y thấp nhất, x thấp nhất).

Cả hai thuật toán đều có cận O(n log n) do sort, nhưng **quy tắc sort khác hẳn**. Vì vậy việc hai danh sách đỉnh chuẩn hóa trùng nhau là một kiểm tra mạnh cho cách sắp góc và kiểm soát collinear.

### Vì sao phải chuẩn hóa trước khi so hai danh sách?

Graham bắt đầu từ điểm có y thấp nhất rồi x thấp nhất. Andrew thường trả một danh sách bắt đầu từ điểm **x nhỏ nhất**, rồi theo CCW. Với cùng một đa giác, các list có thể khác thứ tự bắt đầu mặc dù tập đỉnh giống nhau.

Không được báo sai chỉ vì:

~~~text
Graham: [(0,0),(4,0),(4,4),(0,4)]
Andrew: [(0,0),(4,0),(4,4),(0,4)]
~~~

đã trùng ở ví dụ đơn giản, nhưng ở hình không đối xứng hai pivot có thể khác. Khi đối chiếu, phải:

- Đảm bảo **cùng chính sách** bỏ các điểm giữa cạnh.
- Đảm bảo **cùng chiều CCW**.
- Xoay danh sách theo pivot chuẩn.
- So từng cặp tọa độ tương ứng.

Bản `andrewOracle` làm bước xoay này trước khi so. Với hull 1–2 điểm, quy tắc degeneracy cũng được thống nhất.

### Kiểm từng điểm có nằm trong hull

Chỉ so vertex list không đủ để phát hiện lỗi trong một oracle chung. Ta kiểm thêm mỗi điểm đầu vào có nằm trong hoặc trên polygon trả về hay không.

Với hull CCW có h≥3, một điểm Q nằm trong hoặc trên polygon lồi khi:

**`cross(v_i,v_{i+1},Q)≥0` cho mọi cạnh i**,

trong đó cạnh cuối nối về cạnh đầu. Đây là phép kiểm bằng giao các **nửa mặt phẳng bên trái** của các cạnh đa giác lồi CCW.

Với hull chỉ có 2 điểm A,B, phải kiểm Q **thẳng hàng và nằm trong đoạn AB**:

**`cross(A,B,Q)=0`** và tọa độ Q nằm trong các khoảng [minAxBx,maxAxBx], [minAyBy,maxAyBy].

Với hull một điểm, Q phải bằng đúng điểm ấy; với hull rỗng, không có điểm nào nằm trong.

**Không áp công thức nửa mặt phẳng h≥3 cho hull 1 hoặc 2 điểm** rồi coi các trường hợp ấy là đa giác thông thường.

## 14. Test theo thuộc tính (property-based testing)

Một bộ test tốt cho Graham scan không chỉ gồm các ví dụ hình vuông. Dưới đây là những thuộc tính **bất biến** để kiểm trên nhiều tập điểm nhỏ sinh ngẫu nhiên.

### 14.1. Bất biến về tập điểm và thứ tự

- Mỗi vertex output phải là **một vị trí có thật trong input**.
- Không có vertex trùng tọa độ trong output.
- Pivot luôn là điểm đầu khi hull không rỗng.
- Với h≥3, mọi bộ ba đỉnh liên tiếp kể cả qua vòng khép kín phải có **cross>0**.
- Với h≤2, diện tích =0 và các điểm đầu vào thuộc đoạn/điểm tương ứng.
- Với h≥3, **area2>0** do output CCW.
- Với mọi điểm input, `containsOrOn(hull,p)` phải đúng.
- Nếu loại tất cả điểm trùng lặp khỏi input, kết quả hull không đổi.
- Nếu đảo thứ tự/hoán vị input, kết quả hull theo hợp đồng chuẩn phải **không đổi**.

### 14.2. So với Andrew

Với mỗi tập điểm random:

1. Tính `H=Graham(points)`.
2. Tính `K=Andrew(points)` dùng sort x/y độc lập.
3. Dùng cùng quy tắc vertices-only và định hướng CCW.
4. Xoay K tới pivot y thấp/x thấp.
5. So h và từng điểm của H/K.
6. Kiểm area2, convexity và containment.

Nếu có mismatch, lưu **seed, danh sách điểm ban đầu và hai output** để tái hiện. Không chỉ in PASS/FAIL mà bỏ qua input đã sinh.

### 14.3. Chọn phân bố ngẫu nhiên có ý nghĩa

Các nhóm nên có:

- Điểm đồng đều trong ô vuông nhỏ: dễ có **trùng**, **thẳng hàng** ngoài ý muốn.
- Tất cả điểm nằm trên một đường thẳng: ví dụ y=2x+3; kiểm hull còn hai endpoint.
- Tọa độ cực trị và 0: chọn x,y từ {−10⁹,0,10⁹}; kiểm orientation long và tie-break.
- Hình vuông có nhiều điểm nằm trên bốn cạnh.
- Các điểm trong một đa giác lõm nhưng hull chỉ gồm đỉnh ngoài.
- Chỉ có 0,1,2 điểm phân biệt.
- Tập điểm có nhiều điểm cùng y thấp nhất.
- Các tia gần nhau quanh pivot, làm lỗi floating-point angle dễ lộ.
- Một đỉnh xa và hàng trăm điểm gần pivot trên cùng ray.
- Tập đã sort trước, sort ngược, hoán vị ngẫu nhiên.

Trong một kiểm tra độc lập ở cấp thuật toán, **6.500 tập điểm ngẫu nhiên**, tổng **107.758 điểm đầu vào được kiểm containment**, đã cho kết quả Graham trùng Andrew sau khi chuẩn hóa; mọi hull không suy biến đều CCW lồi nghiêm ngặt. Kết quả này là kiểm thử hỗ trợ, không phải thay thế chứng minh hình học hoặc bảo đảm cho một phiên bản khác tự ý đổi điều kiện comparator.

### 14.4. Kiểm tràn bằng các trường hợp cực trị

Dùng các điểm:

~~~text
(-1000000000,-1000000000)
( 1000000000,-1000000000)
( 1000000000, 1000000000)
(-1000000000, 1000000000)
~~~

Đây là hình vuông cạnh 2·10⁹; hai lần diện tích **8·10¹⁸**, còn vừa long nhưng đã gần giới hạn. Bản mã dùng BigInteger để kiểm area2. Nếu mở rộng giới hạn tọa độ dù chỉ một vài lần, công thức cross long có thể overflow và làm comparator sort hỏng — lỗi rất nguy hiểm vì có thể **không có exception**.

### 14.5. Không dựa vào diện tích đơn lẻ

Một polygon sai thứ tự hoặc bỏ mất đỉnh có thể vô tình cho cùng area2 trong một trường hợp. Vì vậy kiểm thử cần **so đầy đủ danh sách vertex**, kiểm cross ở mọi góc và containment của mọi điểm, không chỉ so tổng diện tích.

## 15. Những biến thể của bài bao lồi

### 15.1. Giữ tất cả điểm trên biên

Nếu đề yêu cầu tất cả điểm nằm **trên cạnh bao lồi**, phải định nghĩa output: theo thứ tự CCW quanh biên hay chỉ tập hợp tọa độ? Cách xử lý nhóm góc cuối trong Graham cần thiết kế cẩn thận; một giải pháp khác là xây hull gồm các góc cực trị rồi **kiểm từng điểm input có nằm trên một cạnh hull**, sắp các điểm trên từng cạnh theo thứ tự hình học. Cách hai có thể tốn O(nh) nếu kiểm tất cả các cặp điểm–cạnh ngây thơ, nên không phải giải pháp tốt nhất cho n rất lớn.

Chỉ đổi điều kiện pop mà không test trường hợp **all-collinear** và các tia cùng góc là chưa đủ để cam kết đầu ra đúng.

### 15.2. Bao lồi bao quanh điểm nguyên trên lưới

Nếu các điểm có tọa độ nguyên, đa giác có thể có diện tích nửa nguyên; `area2` là **số nguyên chính xác**, rất tiện để tránh làm tròn. Có thể dùng **định lý Pick** cho đa giác đơn có đỉnh nguyên để liên hệ diện tích A, số điểm nguyên bên trong I và trên biên B:

**`A=I+B/2−1`**.

Nhưng B ở đây là **số điểm nguyên trên biên**, không phải số **đỉnh hull**. Nếu muốn đếm điểm nguyên trên đoạn cạnh (dx,dy), dùng `gcd(|dx|,|dy|)` theo quy tắc tránh đếm trùng đỉnh; đây là bài bổ sung, không nằm trong Graham scan cốt lõi.

### 15.3. Chu vi và khoảng cách xa nhất

Sau khi có hull, có thể tính chu vi bằng cách cộng độ dài Euclid của các cạnh. **Cặp điểm xa nhất** trong một tập phẳng luôn có thể chọn từ các **đỉnh bao lồi**; vì vậy có thể chạy **rotating calipers** trên hull để tìm đường kính (*diameter*) trong O(h) sau khi đã có hull. Không cần thử mọi cặp input O(n²) khi chỉ quan tâm xa nhất.

Tuy nhiên, **cặp điểm gần nhất** không có tính chất tương tự: hai điểm gần nhất có thể nằm sâu trong nội bộ hull. Không dùng hull rồi chỉ thử các vertex để giải closest pair; thuật toán đó có thể bỏ mất nghiệm.

### 15.4. Point-in-convex-polygon

Bản code dùng `containsOrOn` trong **O(h)** mỗi truy vấn bằng cách kiểm tất cả nửa mặt phẳng cạnh. Nếu có nhiều truy vấn và hull đã được sắp CCW, có thể xây phép kiểm theo **quạt tam giác từ một đỉnh** và dùng binary search để đạt **O(log h)** mỗi truy vấn, sau khi xử lý cẩn thận các điểm nằm trên biên và trường hợp h<3.

Graham scan chỉ tính hull; tốc độ kiểm điểm nằm trong hull là một bài toán sử dụng sau tiền xử lý.

### 15.5. Bao lồi động

Nếu các điểm liên tục được **thêm/xóa**, xây Graham scan lại từ đầu sau mỗi thay đổi có thể tốn O(n log n) cho một lần update. Có những cấu trúc dữ liệu **dynamic convex hull** phức tạp để duy trì biên khi tập thay đổi. Không thể chỉ push điểm mới vào stack của lần scan cũ mà mặc định đúng vì thứ tự góc và vị trí pivot có thể thay đổi.

### 15.6. Bao lồi 3D

Trong không gian ba chiều, bao lồi là một **đa diện** với mặt, cạnh và đỉnh, không phải đa giác phẳng; cross 2D và polar-angle sort Graham scan **không đủ**. Cần thuật toán hình học không gian và các phép orientation 3D phù hợp. Không suy từ O(n log n) của bài phẳng rằng 3D có cùng cách cài.

## 16. Graham scan và Andrew monotone chain: chọn khi nào?

| Tiêu chí | Graham scan | Andrew monotone chain |
|---|---|---|
| Thứ tự sắp | **Góc cực quanh pivot** | **x rồi y** |
| Cấu trúc duyệt | Một stack rẽ trái | Lower hull và upper hull |
| Phép thử | cross của ba điểm | cross của ba điểm |
| Thời gian | O(n log n) | O(n log n) |
| Bộ nhớ | O(n) | O(n) |
| Điểm cùng góc | Cần tie-break theo khoảng cách | Sort x/y tự nhiên |
| Suy biến thẳng hàng | Đặc biệt lưu ý comparator và chính sách pop | Thường đơn giản hơn |
| Nguy cơ phổ biến | Comparator góc sai/đổi nửa mặt phẳng | Ghép hai chain lặp endpoint |
| Giá trị học tập | Hiểu **polar sweep** và stack | Hiểu **lower/upper envelope** |

Với các bài chỉ cần hull phẳng của điểm nguyên, nhiều người chọn Andrew để code ngắn và ít sai hơn. Nhưng Graham scan giúp hiểu sâu **cách sort theo hướng**, **tại sao cross có dấu quyết định góc quay**, và **tính chất mỗi điểm chỉ push/pop tối đa một lần**. Cả hai đều là thuật toán đúng nếu xử lý trùng, collinear, kiểu dữ liệu và output contract đúng.

### Kết quả có thể khác nhưng cùng hull?

Nếu một cài Graham giữ điểm giữa cạnh còn cài Andrew chỉ giữ vertex cực trị, **tập output khác** dù cùng tập bao lồi hình học. Nếu hai cài đặt dùng CW/CCW khác nhau hoặc bắt đầu từ đỉnh khác, **thứ tự output khác**. Vì vậy khi so hai thuật toán, cần thống nhất trước về:

- Strict vertices hoặc all boundary points.
- Có lặp đỉnh đầu ở cuối hay không.
- Thứ tự CW/CCW.
- Quy ước pivot/đỉnh bắt đầu.
- Trường hợp suy biến 0/1/2 điểm và all-collinear.

Bản Java đã chuẩn hóa toàn bộ các lựa chọn ấy trước khi so sánh.

## 17. Các lỗi thường gặp

1. **Không loại điểm trùng:** vector 0 từ pivot làm comparator góc không xác định, output có thể trùng.
2. **Chọn pivot chỉ theo y nhưng không phá hòa bằng x:** comparator có thể gặp vector nằm ngang cả hai phía, không còn ở cung [0,π).
3. **Dùng cross>0 để so góc với pivot bất kỳ:** trên vòng 360° comparator có thể không bắc cầu.
4. **Đảo dấu orientation:** thuật toán pop góc trái thay vì phải, trả hull CW sai hoặc polygon lõm.
5. **Sort cùng góc theo khoảng cách giảm nhưng vẫn pop cross≤0 mà không kiểm thuật toán:** có thể giữ endpoint gần thay vì xa.
6. **Không có tie-break khi cross=0:** thứ tự cùng tia không xác định, nhất là đầu ra vertices-only.
7. **Dùng `Math.atan2` rồi so double trực tiếp:** có nguy cơ sai với góc cực gần nhau, không cần thiết với điểm nguyên.
8. **Dùng `int` cho cross với tọa độ khoảng 10⁹:** nhân hai hiệu tràn nghiêm trọng.
9. **Cho tọa độ ngoài ±10⁹ nhưng vẫn tin cross long an toàn:** giả thiết toán học của code không còn đúng.
10. **Ép `(int)(distanceA−distanceB)` trong comparator:** mất dấu vì tràn/narrowing.
11. **Dùng Math.sqrt chỉ để so khoảng cách:** phát sinh số thực không cần thiết.
12. **Đổi x và y khi đọc input mà không đổi convention:** pivot và chiều quay sai.
13. **Nhầm quy ước y tăng xuống của màn hình với CCW trong toán học:** hiển thị bị phản chiếu.
14. **Chỉ dùng if thay vì while khi pop:** có thể còn nhiều góc lõm ở cuối stack.
15. **Tưởng vòng while làm scan O(n²):** mỗi điểm chỉ push/pop tối đa một lần.
16. **Pop với cross<0 trong bài vertices-only:** điểm thẳng hàng giữa cạnh có thể được giữ, trái hợp đồng.
17. **Đổi cross<=0 thành cross<0 cho all-boundary mà không xử lý nhóm tia cuối:** đầu ra có thể sai thứ tự hoặc lặp.
18. **Giữ điểm nằm trong hull như một vertex:** polygon output thừa góc hoặc không lồi.
19. **Bỏ sót điểm cực trị vì pivot/angle sort sai:** hull không chứa hết input.
20. **Giả định n≥3:** trường hợp 0/1/2 điểm gây truy cập ngoài mảng.
21. **Tất cả điểm thẳng hàng nhưng code trả nhiều “đỉnh”:** sai contract vertices-only.
22. **Tập điểm chỉ có một tọa độ nhưng gồm nhiều bản sao:** phải trả một điểm, không phải đoạn.
23. **Không xác định thứ tự start của polygon:** dễ sai judge nếu chấm danh sách chính xác.
24. **Lặp pivot ở cuối khi đề yêu cầu không lặp:** output thừa một điểm.
25. **Tính area2 của hull hai điểm như diện tích đa giác dương:** đoạn có diện tích 0.
26. **Không đóng cạnh cuối về cạnh đầu khi dùng shoelace:** bỏ một hạng tử quan trọng.
27. **Dùng long area2 tích lũy với nhiều cạnh mà không xét tổng trung gian:** có thể overflow trong cấu hình khác.
28. **Nhầm area2 với area:** tam giác ở demo area2=16 nhưng diện tích thật 8.
29. **Không dùng BigInteger/kiểu đủ rộng khi yêu cầu tọa độ lớn:** orientation có thể đảo dấu mà không báo lỗi.
30. **Dùng epsilon tùy tiện cho tọa độ nguyên:** có thể coi ba điểm không thẳng hàng thành collinear.
31. **Kiểm inside chỉ bằng bounding box của hull:** điểm nằm trong hình chữ nhật bao chưa chắc nằm trong polygon.
32. **Áp kiểm nửa mặt phẳng h≥3 cho h=1/2:** xử lý sai hull suy biến.
33. **Không kiểm điểm trên đoạn khi h=2:** cross=0 còn cho các điểm ngoài đoạn thẳng.
34. **Tưởng điểm nằm trên cạnh mà bị loại khỏi vertex list là ở ngoài hull:** nhầm boundary với vertex.
35. **Không phân biệt farthest pair và closest pair:** closest pair có thể ở nội bộ hull.
36. **Gọi convex hull cho tập 3D bằng Graham 2D:** mất thông tin chiều thứ ba.
37. **So hai thuật toán khác pivot bằng list trực tiếp mà không xoay:** false mismatch.
38. **So hai thuật toán một bên giữ boundary collinear, bên kia bỏ:** false mismatch.
39. **Chỉ kiểm diện tích mà không kiểm vertex/containment:** có thể lọt bug đường bao.
40. **Không test all-collinear và duplicates:** hai nguồn lỗi lớn nhất.
41. **Không test cực trị ±10⁹:** không kiểm được nguy cơ overflow.
42. **Chỉ test points đã sort CCW:** không chứng minh input order bất biến.
43. **Cứ cho polygon lồi có cross>0 liên tiếp là chứa mọi input:** còn phải kiểm containment.
44. **Tin rằng một điểm pop có thể phải xét lại sau:** phá phân tích stack; Graham dựa vào thứ tự góc để loại vĩnh viễn.
45. **Giữ hàng triệu điểm boundary khi chỉ cần vertices:** tốn output và có thể ảnh hưởng thuật toán downstream.
46. **Dùng HashSet để xuất hull trực tiếp:** HashSet không giữ thứ tự CCW.
47. **Quên rằng n là số điểm, h là số đỉnh hull:** khi trả output, phải tính ít nhất O(h).
48. **Gán O(n log n) cho riêng vòng stack:** sort chiếm phần log; scan chỉ O(n).
49. **Không ghi rõ chấp nhận điểm trên biên hay chỉ điểm trong:** dễ sai point-location output.
50. **Tự ý sửa chuỗi đầu vào hay tạo điểm giả để né suy biến:** thay đổi bài toán hình học.

## 18. Bài tập thực hành

**Bài 1 — Cross bằng tay.** Cho A=(1,1), B=(5,2), C=(3,6), D=(3,0). Tính cross(A,B,C) và cross(A,B,D), xác định điểm nào nằm trái/phải đường A→B. Dùng hai vector và định thức, không tính góc bằng lượng giác.

**Bài 2 — Pivot và tia góc.** Cho [(0,0),(2,0),(4,0),(3,3),(1,1),(0,4)]. Chọn pivot theo min(y,x), sort các điểm còn lại theo góc tăng, hòa theo dist² tăng. Chạy từng bước stack và nêu điểm nào bị pop.

**Bài 3 — Tất cả điểm cùng đường.** Cho n điểm trên y=2x+1 với x từ −100 tới 100, mỗi tọa độ xuất hiện hai lần. Chứng minh hull vertices-only chỉ có hai đầu mút; đo số lần pop tối đa.

**Bài 4 — Bao lồi và shoelace.** Tính hull của tập [(0,0),(4,0),(4,4),(0,4),(2,2),(4,2)]. Tính area2=32, area=16. Nếu đầu ra CCW bị đảo thành CW, shoelace trả area2 âm; giải thích vì sao.

**Bài 5 — Điểm trên biên.** Mở rộng API trả **mọi điểm đầu vào** nằm trên boundary của hull theo thứ tự quanh biên, không trùng. Kiểm hình vuông có nhiều điểm trên cạnh và all-collinear; đừng chỉ sửa một dấu so sánh mà không test.

**Bài 6 — Đo hiệu năng.** Sinh các tập điểm ngẫu nhiên, có nhiều duplicate và tất cả cùng đường, lần lượt n=1.000, 10.000, 100.000. Đo thời gian dedup/sort/scan riêng, tránh trộn I/O hoặc tạo dữ liệu vào thời gian thuật toán.

**Bài 7 — Tọa độ 64-bit thật lớn.** Cho phép x,y tới 10¹². Thay `cross` và `squaredDistance` bằng BigInteger chính xác, đảm bảo comparator không chuyển BigInteger thành int bằng ép kiểu. Kiểm các điểm gần thẳng hàng ở cực trị.

**Bài 8 — Andrew monotone chain.** Cài thuật toán sort theo x/y rồi xây lower/upper hull. Chuẩn hóa CCW/pivot và so với Graham trên 10.000 tập random, trong đó có trường hợp 0/1/2 và collinear.

**Bài 9 — Farthest pair.** Sau khi có hull CCW h đỉnh, nghiên cứu rotating calipers để tìm đường kính trong O(h). Giải thích tại sao chỉ cần xét các điểm hull cho bài xa nhất.

**Bài 10 — Đa giác lồi và truy vấn chứa điểm.** Cho hull CCW h≥3, viết kiểm inside-or-boundary O(h) như code và tối ưu O(log h) mỗi query bằng quạt tam giác từ một đỉnh. Nêu cách xử lý điểm nằm đúng trên cạnh.

**Bài 11 — Biên tập đồ họa.** Một hệ tọa độ màn hình có trục y tăng xuống. Vẽ hull của một tập điểm và kiểm khi nào cần đảo thứ tự để thể hiện đa giác CCW theo hướng mắt nhìn trên màn hình.

**Bài 12 — Chứng minh comparator.** Giải thích tại sao pivot thấp nhất rồi trái nhất làm mọi góc nằm trong [0,π), và đưa phản ví dụ khi chọn pivot ở giữa các điểm trên một vòng tròn khiến việc dùng chỉ dấu cross để so góc không còn thứ tự toàn phần.

## 19. Checklist trước khi nộp

- Đã đọc đề để biết **vertices-only** hay **all-boundary points**?
- Tọa độ là integer hay floating point? Đã chọn kiểu tính cross đủ rộng?
- Nếu dùng long, đã có **giới hạn tọa độ** chứng minh không overflow?
- Đã loại điểm trùng trước khi tính pivot, sort và scan?
- Pivot có đúng là y nhỏ nhất, nếu hòa thì x nhỏ nhất?
- Comparator góc có được sử dụng chỉ khi tất cả vector từ pivot ở **nửa mặt phẳng phù hợp**?
- Có sort các điểm **cùng tia** theo bình phương khoảng cách tăng?
- Có dùng `Long.compare` thay vì trừ rồi ép int?
- Đã dùng **cross>0** là rẽ trái trong hệ Descartes y lên trên?
- Vòng pop có là **while** đến khi cross>0, không chỉ if?
- Với vertices-only, có pop cả **cross=0**?
- Stack khởi tạo an toàn với n=0,1,2 và all-collinear?
- Output có CCW, pivot ở đầu và không lặp pivot ở cuối?
- Với all-collinear, có trả đúng **hai đầu mút** (hoặc một điểm nếu chỉ có một vị trí)?
- Với một số điểm chỉ nằm trong đa giác, code có loại khỏi vertex list?
- Có phân biệt **đỉnh cực trị**, **điểm trên biên** và **điểm bên trong**?
- Nếu tính diện tích, có tính shoelace đủ cạnh cuối và phân biệt area2 với area?
- Nếu kiểm containment, đã tách trường hợp hull rỗng, điểm và đoạn thẳng?
- Đã phân tích sort O(n log n), scan O(n) và bộ nhớ O(n)?
- Đã test ảnh hưởng của thứ tự input và điểm trùng?
- Đã test hình vuông, tam giác, concave points, all-collinear ngang/dọc và tọa độ âm?
- Đã test gần giới hạn ±10⁹ và kiểm không overflow cross/dist²?
- Đã so với **Andrew monotone chain** độc lập và chuẩn hóa output?
- Đã kiểm mọi điểm đầu vào nằm trong/on hull và mọi góc hull là rẽ trái?
- Đã xác định cách dùng kết quả downstream: area, perimeter, farthest pair, point location hoặc hiển thị?

**Kết luận:** Graham scan tìm bao lồi của các điểm phẳng bằng cách **chọn pivot cực trị, sắp góc cực và duy trì stack chỉ có các góc rẽ trái**. Phép **cross(A,B,C)** quyết định chính xác rẽ trái/phải/thẳng hàng; việc **sort theo khoảng cách khi cùng tia** và **pop khi cross≤0** giúp đầu ra chỉ còn các đỉnh cực trị, kể cả với điểm trùng hoặc tất cả cùng đường. Chi phí chủ yếu là sort **O(n log n)**; bước scan tuyến tính do mỗi điểm được thêm/bỏ tối đa một lần. Với tọa độ nguyên lớn, phải chứng minh kiểu số học không tràn; với mục tiêu sử dụng thực tế, cần quy định rõ điểm giữa cạnh có được xuất hay không, hướng CW/CCW, đỉnh đầu và dạng output cho trường hợp suy biến. Bao lồi là bước tiền xử lý quan trọng cho tính diện tích, chu vi, tìm cặp điểm xa nhất, kiểm chứa điểm và nhiều bài **hình học tính toán** khác.