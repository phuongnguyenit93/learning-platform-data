# Tính diện tích đa giác bằng tổng có hướng

**Tính diện tích đa giác bằng tổng có hướng** (signed area, công thức **shoelace** hay **Gauss area formula**) là kỹ thuật hình học tính toán để tìm diện tích của một đa giác từ các tọa độ đỉnh theo thứ tự đi quanh đường biên. Không cần chia hình thành tam giác bằng một thuật toán triangulation riêng, và cũng không yêu cầu đa giác phải lồi.

Với các đỉnh P₀=(x₀,y₀), P₁=(x₁,y₁), ..., Pₙ₋₁=(xₙ₋₁,yₙ₋₁) được liệt kê theo đúng thứ tự trên đường biên, đặt Pₙ=P₀. Khi đó:

**2A_s = Σ từ i=0 đến n−1 của (xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ)**.

Trong đó **A_s** là *diện tích có hướng*:

- Nếu đi các đỉnh theo **ngược chiều kim đồng hồ (CCW)** trong hệ tọa độ x sang phải, y hướng lên, A_s>0.
- Nếu đi theo **chiều kim đồng hồ (CW)**, A_s<0.
- Nếu đường biên là một **đa giác đơn** (không tự cắt), diện tích hình học là **|A_s|**.
- Nếu đường đỉnh **tự cắt**, tổng có hướng vẫn tính được về mặt đại số, nhưng **|A_s| không nhất thiết là diện tích hợp hình học**. Có thể có các vùng được tính dấu trái nhau và triệt tiêu.

Vì công thức chỉ có một vòng lặp qua các cạnh, số phép toán tọa độ là **O(n)**. Đây là một công cụ cơ bản của nhóm **Hình học tính toán**, ứng dụng trong bài tính diện tích hình đất, nhận biết hướng polygon, xử lý vòng ngoài và lỗ, so sánh đa giác, bài toán lattice polygon và nhiều cấu trúc hình học.

Bài học sẽ triển khai công thức, cách hiểu dấu của tích có hướng, ví dụ đa giác lồi và lõm, chứng minh từ tổng các cạnh, xử lý tọa độ âm và rất lớn, code **Java 17+ chính xác bằng BigInteger**, kiểm thử độc lập và những lỗi dễ mắc.

## 1. Dữ liệu đầu vào: một chu trình đỉnh có thứ tự

Một **đa giác** trong bài được cung cấp bằng dãy các đỉnh trên đường biên:

**P₀→P₁→...→Pₙ₋₁→P₀**.

Hai đỉnh liên tiếp nối bằng một cạnh thẳng; cạnh cuối nối đỉnh cuối về đỉnh đầu. Thứ tự này là **một phần của dữ liệu**, không thể thay thế bằng một tập điểm không thứ tự.

Ví dụ hình chữ nhật:

~~~text
P3 (0,3) ------- P2 (5,3)
   |                |
   |                |
P0 (0,0) ------- P1 (5,0)

Order: P0 -> P1 -> P2 -> P3 -> P0
~~~

Đây là chiều **CCW** trong mặt phẳng toán học: đi dọc cạnh dưới sang phải, lên cạnh phải, qua cạnh trên sang trái rồi xuống cạnh trái.

Nếu đảo thứ tự thành P₀→P₃→P₂→P₁→P₀, ta đi theo **CW**, và diện tích có hướng đổi dấu.

### Đa giác đơn và đa giác tự cắt

Một **đa giác đơn** có đường biên không tự cắt (trừ việc khép kín ở đỉnh đầu/cuối). Có thể có các đỉnh thẳng hàng hoặc cạnh có độ dài 0 do đỉnh lặp liên tiếp nếu cách biểu diễn cho phép, nhưng cần xác định rõ những trường hợp suy biến ấy.

Một dãy đỉnh bất kỳ vẫn có thể đưa vào công thức shoelace, nhưng nếu các cạnh giao nhau ở giữa hoặc các vòng lặp đè lên nhau, giá trị trả về mang nghĩa **tổng đại số có hướng** chứ không phải diện tích miền đơn nhất một cách tự động.

**Điều kiện bắt buộc của đầu vào nếu muốn dùng |A_s| làm diện tích hình học:** danh sách đỉnh phải mô tả một đường biên đơn, với thứ tự đi quanh đa giác đúng.

## 2. Tích có hướng của hai vector 2D

Với hai vector u=(uₓ,uᵧ), v=(vₓ,vᵧ), định nghĩa tích có hướng dạng vô hướng trong mặt phẳng:

**cross(u,v)=uₓ·vᵧ−uᵧ·vₓ**.

Đây là định thức:

~~~text
|u_x  u_y|
|v_x  v_y| = u_x*v_y - u_y*v_x
~~~

Trị tuyệt đối |cross(u,v)| bằng diện tích hình bình hành do hai vector tạo thành. Dấu cho biết hướng quay từ u sang v:

- cross>0: quay ngược chiều kim đồng hồ (CCW) với hệ y hướng lên.
- cross<0: quay theo chiều kim đồng hồ (CW).
- cross=0: hai vector thẳng hàng hoặc có vector bằng 0.

Đối với cạnh đi từ Pᵢ tới Pᵢ₊₁, shoelace cộng:

**cross(Pᵢ,Pᵢ₊₁)=xᵢ·yᵢ₊₁−yᵢ·xᵢ₊₁**.

Ở đây Pᵢ được xem là vector tọa độ tính từ gốc O=(0,0).

### Phân biệt hai dạng cross

**cross(Pᵢ,Pᵢ₊₁)** là tích có hướng của **hai vector vị trí**, chính là số hạng trong shoelace.

**cross(B−A,C−A)** là tích có hướng của **hai vector cạnh** xuất phát từ A, dùng để kiểm tra hướng quay của ba điểm A,B,C và diện tích tam giác ABC.

Hai biểu thức liên quan nhưng không giống nhau nếu thay điểm tùy ý. Không được vô tình viết sum cross(Pᵢ₊₁−Pᵢ, Pᵢ₊₂−Pᵢ₊₁) rồi coi đó là shoelace.

## 3. Công thức shoelace đầy đủ

Cho Pᵢ=(xᵢ,yᵢ), đặt Pₙ=P₀:

**S = Σᵢ (xᵢ·yᵢ₊₁−xᵢ₊₁·yᵢ)**.

Khi đó:

**A_s=S/2** là diện tích có hướng.

Nếu polygon đơn:

**A=|S|/2** là diện tích hình học không âm.

Viết hai tổng riêng:

**S=(x₀y₁+x₁y₂+...+xₙ₋₁y₀) − (y₀x₁+y₁x₂+...+yₙ₋₁x₀)**.

Đây là cách viết gợi hình “dây giày” (shoelace): nhân chéo các tọa độ liên tiếp trong hai chiều, lấy hiệu rồi chia đôi.

### Không cần đóng vòng bằng cách ghi lại điểm đầu

Có hai cách phổ biến:

- Lưu n đỉnh, dùng **next=(i+1)%n**.
- Lưu n+1 đỉnh, trong đó Pₙ=P₀, rồi duyệt i=0..n−1.

Không được **vừa tự thêm điểm đầu vừa quên điều kiện vòng lặp**, dẫn tới đọc ngoài mảng. Trong Java demo, danh sách có thể chứa điểm đầu lặp lại; cạnh cuối từ P₀ tới chính P₀ sẽ có cross=0 nên không làm thay đổi kết quả. Tuy vậy, cách nên dùng là chỉ lưu **n đỉnh độc lập** rồi dùng modulo để khép kín.

### Vì sao gọi là “tổng có hướng”?

Với mỗi cạnh, cross có thể dương, âm hoặc 0. Ta cộng **đúng dấu của từng hạng**, không lấy trị tuyệt đối từng cross. Các phần đóng góp có thể triệt tiêu nhau, và chính sự triệt tiêu phù hợp này tạo ra diện tích đa giác lõm hoặc polygon quay theo CW.

## 4. Ví dụ tam giác: tính từng số hạng

Tam giác có các đỉnh:

**P₀=(0,0), P₁=(4,0), P₂=(0,3)**.

Thứ tự P₀→P₁→P₂ là CCW.

| Cạnh | xᵢ·yᵢ₊₁ | yᵢ·xᵢ₊₁ | Cross |
| --- | ---: | ---: | ---: |
| (0,0)→(4,0) | 0 | 0 | 0 |
| (4,0)→(0,3) | 12 | 0 | +12 |
| (0,3)→(0,0) | 0 | 0 | 0 |
| **Tổng** | 12 | 0 | **12** |

Vậy:

**S=12**, **A_s=12/2=6**, **A=6**.

Điều này khớp công thức diện tích tam giác đáy 4, cao 3:

**A=(4·3)/2=6**.

Nếu liệt kê theo chiều ngược lại P₂→P₁→P₀, ta nhận **S=−12**, nên A_s=−6 nhưng diện tích hình học vẫn bằng 6.

### Tam giác có diện tích nửa đơn vị

Cho P₀=(0,0), P₁=(3,0), P₂=(0,1). Ta có:

**S=3**, do đó **A=3/2=1,5**.

Nếu tọa độ đều là **số nguyên**, S là số nguyên, nên diện tích có thể là **số nguyên hoặc số kết thúc bằng .5**. Không được chia nguyên S/2 rồi làm mất phần .5.

Ví dụ:

~~~text
S = 3
S / 2 by Java integer division = 1 (SAI neu can dien tich)
Exact area = 1.5
~~~

Đó là lý do code lưu **signedDoubleArea=S** dưới dạng BigInteger, chỉ đổi thành chuỗi "1.5" khi cần hiển thị.

## 5. Ví dụ hình chữ nhật và đa giác lõm

Hình chữ nhật có đỉnh:

~~~text
(1,1) -> (6,1) -> (6,4) -> (1,4)
~~~

Chiều rộng 5, chiều cao 3, nên diện tích hình học là **15**.

Shoelace:

~~~text
(1,1) to (6,1): 1*1 - 1*6  = -5
(6,1) to (6,4): 6*4 - 1*6  = 18
(6,4) to (1,4): 6*4 - 4*1  = 20
(1,4) to (1,1): 1*1 - 4*1  = -3

S = -5 + 18 + 20 - 3 = 30
A = |30|/2 = 15
~~~

Không phải mọi số hạng cross đều dương, dù polygon được duyệt CCW. **Chỉ dấu của tổng S** có ý nghĩa xác định hướng của toàn đường biên đơn.

### Đa giác lõm hình chữ L

Cho các đỉnh theo CCW:

~~~text
(0,0) -> (6,0) -> (6,2) ->
(2,2) -> (2,5) -> (0,5) -> (0,0)
~~~

Hình này lõm ở góc nối (6,2)→(2,2)→(2,5), nhưng đường biên không tự cắt.

Ta có thể chia thành hai hình chữ nhật rời phần trong:

- Hình phía dưới: rộng 6, cao 2, diện tích 12.
- Hình phía trái phía trên: rộng 2, cao 3, diện tích 6.

Vậy diện tích bằng **18**.

Shoelace trả:

**S=36**, **A=18**.

**Không cần đa giác lồi.** Điều kiện quan trọng là thứ tự đỉnh tạo một đường biên đơn.

## 6. Vì sao công thức đúng? Cách nhìn tam giác có hướng

Với gốc O=(0,0), mỗi cặp vector Pᵢ, Pᵢ₊₁ tạo một **tam giác có hướng O Pᵢ Pᵢ₊₁**. Diện tích có hướng của tam giác đó là:

**(1/2)·cross(Pᵢ,Pᵢ₊₁)**.

Nếu cộng các tam giác có hướng ứng với mọi cạnh của một polygon khép kín, các phần ngoài polygon có thể được cộng và trừ để **triệt tiêu**, còn phần trong có hệ số tương ứng với hướng vòng quanh.

Do đó:

**A_s=(1/2)·Σ cross(Pᵢ,Pᵢ₊₁)**.

Lập luận dùng các tam giác có hướng không đòi tam giác nào cũng nằm trong polygon. Với đa giác lõm hoặc polygon nằm lệch xa gốc tọa độ, có tam giác ký hiệu mang dấu âm, và đó là điều bình thường.

### Diện tích thường khác diện tích có hướng

Với polygon đơn, hướng đi quanh đường biên quyết định dấu. **Trị tuyệt đối của tổng** mới là diện tích hình học:

**A=|Σcross|/2**.

Không lấy:

**(1/2)·Σ|cross(Pᵢ,Pᵢ₊₁)|**.

Công thức sai này thường đếm thừa các tam giác có hướng, nhất là khi polygon lệch khỏi gốc hoặc là đa giác lõm.

## 7. Chứng minh khác bằng tích phân đường Green

Công thức cũng là hệ quả của **định lý Green** cho đường biên đơn, định hướng dương (CCW):

**A_s = (1/2)∮(x\,dy − y\,dx)**.

Xét một cạnh thẳng từ P=(x₁,y₁) tới Q=(x₂,y₂). Tham số hóa:

**x(t)=x₁+t(x₂−x₁)**, **y(t)=y₁+t(y₂−y₁)**, với t từ 0 đến 1.

Đặt Δx=x₂−x₁, Δy=y₂−y₁. Khi đó:

**x\,dy−y\,dx = (x₁+tΔx)Δy\,dt − (y₁+tΔy)Δx\,dt**.

Hai số hạng có t triệt tiêu:

**x\,dy−y\,dx = (x₁Δy−y₁Δx)\,dt**.

Lấy tích phân trên cạnh:

**∫(x\,dy−y\,dx)=x₁(y₂−y₁)−y₁(x₂−x₁)=x₁y₂−y₁x₂**.

Cộng mọi cạnh và chia 2, thu được chính công thức shoelace.

Cách chứng minh này giải thích vì sao chỉ cần **tọa độ các đỉnh**, không cần biết nội thất được chia tam giác như thế nào.

### Phạm vi áp dụng

Định lý Green mô tả diện tích có hướng theo đường biên có định hướng. Với đường biên tự cắt, tích phân vẫn cho một **tổng có trọng số theo số vòng quấn (winding number)** chứ không nhất thiết là diện tích của tập điểm nằm “bên trong” theo một quy ước tô hình cụ thể.

## 8. Đổi thứ tự đỉnh, quay vòng và hướng polygon

Ba thao tác dễ gặp:

**1. Đảo thứ tự đỉnh:** nếu đổi P₀,P₁,...,Pₙ₋₁ thành Pₙ₋₁,...,P₁,P₀ thì mỗi cạnh được đi theo hướng ngược. Mọi cross đổi dấu, nên:

**S_reversed = −S_original**.

Với tam giác ví dụ, +12 thành −12; diện tích hình học vẫn 6.

**2. Quay vòng điểm bắt đầu:** đổi danh sách P₀,P₁,... thành P_k,Pₖ₊₁,...,Pₖ₋₁. Cạnh vẫn là cùng các cạnh và cùng hướng, nên:

**S_rotated = S_original**.

Điểm bắt đầu không quan trọng, miễn thứ tự vòng quanh không đổi.

**3. Hoán vị đỉnh tùy ý:** có thể tạo các cạnh mới, tự cắt hoặc hình khác. **S không nhất thiết được bảo toàn.** Không có quyền sort đỉnh theo x/y rồi gọi đó là chu trình polygon ban đầu.

### Nhận diện CCW/CW

Trong tọa độ toán học (x tăng sang phải, y tăng lên):

- S>0 → **CCW** với polygon đơn có diện tích dương.
- S<0 → **CW**.
- S=0 → **ZERO_SIGNED_AREA**.

**S=0 không đủ để khẳng định polygon suy biến** nếu đầu vào có thể tự cắt, vì các vùng có hướng trái nhau có thể triệt tiêu.

Để xác định một chu trình là CCW/CW có nghĩa hình học chuẩn, cần bảo đảm nó là **đường biên đơn không có diện tích 0**.

## 9. Tọa độ màn hình y hướng xuống

Trong toán học phẳng, trục y thường hướng **lên**. Trong ảnh, canvas và nhiều hệ tọa độ màn hình, y thường hướng **xuống**.

Nếu giữ x như cũ nhưng thay **y_screen = −y_math + constant**, dấu cross và shoelace đảo:

**S_screen = −S_math**.

Vì vậy một polygon nhìn bằng mắt là CCW trên màn hình có thể cho S âm khi bạn áp dụng quy ước tích có hướng trong hệ y hướng xuống.

Điều bất biến là **diện tích không âm**:

**|S_screen|/2 = |S_math|/2**, nếu phép chuyển chỉ là đảo y và tịnh tiến.

### Quy ước hướng trong API

Nếu bạn xây một hàm isClockwise cho dữ liệu tọa độ màn hình, phải nêu nó đang dùng **y-down hay y-up**. Đừng chỉ nhìn vào tên biến “clockwise” mà bỏ qua hệ tọa độ.

Trong chương trình Java của bài, nhãn hướng được định nghĩa **theo hệ x-right, y-up**. Khi dữ liệu là pixel y-down, đổi cách diễn giải hướng hoặc chuyển hệ tọa độ.

## 10. Tịnh tiến đa giác không làm đổi diện tích

Giả sử mọi đỉnh được dịch cùng vector T=(a,b):

**Pᵢ'=(xᵢ+a,yᵢ+b)**.

Số hạng mới của cạnh i là:

**(xᵢ+a)(yᵢ₊₁+b) − (xᵢ₊₁+a)(yᵢ+b)**.

Khai triển:

**cross(Pᵢ',Pᵢ₊₁') = cross(Pᵢ,Pᵢ₊₁) + a(yᵢ₊₁−yᵢ) + b(xᵢ−xᵢ₊₁)**.

Cộng theo một đường khép kín:

**Σ(yᵢ₊₁−yᵢ)=0** và **Σ(xᵢ−xᵢ₊₁)=0**.

Do đó các số hạng tịnh tiến triệt tiêu:

**S'=S**.

### Ý nghĩa thực tế

Một tam giác diện tích 6 ở quanh gốc tọa độ vẫn có diện tích 6 khi chuyển đến tọa độ cỡ **10^30**. Tuy nhiên, khi dùng double, những tích lớn có thể mất nhiều bit chính xác trước khi triệt tiêu, khiến kết quả gần 0 hoặc sai.

Dùng **BigInteger với tọa độ nguyên** giúp phép tịnh tiến và triệt tiêu chính xác về mặt toán học, miễn còn tài nguyên xử lý.

## 11. Đa giác có đỉnh thẳng hàng hoặc đỉnh lặp

Thêm một điểm B nằm trên cạnh thẳng A→C và thay cạnh đó bằng A→B→C không thay đổi tổng có hướng.

Nếu B nằm trên đoạn AC theo đúng hướng, hai hạng cross mới thay cho một hạng cũ nhưng tổng bằng nhau vì diện tích tam giác A B C bằng 0.

Ví dụ:

~~~text
(0,0) -> (5,0) -> (5,3) -> (0,3)
~~~

và:

~~~text
(0,0) -> (2,0) -> (5,0) -> (5,3) -> (0,3)
~~~

cùng cho diện tích **15**, S=30.

### Lặp điểm đầu ở cuối danh sách

Nếu polygon đã ghi P₀ ở cuối:

~~~text
[(0,0), (4,0), (0,3), (0,0)]
~~~

thì cạnh cuối từ (0,0) về (0,0) có cross=0, nên vẫn được S=12.

Tuy nhiên, **không nên lặp nhiều điểm một cách tùy tiện** vì dữ liệu có thể trở thành đường biên không đơn hoặc có cạnh không mong muốn. Một thư viện xử lý polygon tổng quát nên xác định hợp đồng về đỉnh lặp, cạnh zero-length và cách validation.

### n dưới 3

Với n=0,1,2, không có polygon đơn có diện tích dương. Code demo trả **S=0**, **A=0** để xử lý an toàn.

Nếu API của một hệ thống yêu cầu n≥3 và polygon không suy biến, có thể từ chối các trường hợp này thay vì trả 0. Hai cách đều hợp lý nếu đặc tả rõ.

## 12. Polygon tự cắt: tổng đại số không phải diện tích hợp

Xét đường “nơ bướm”:

~~~text
(0,0) -> (4,4) -> (0,4) -> (4,0) -> (0,0)
~~~

Hai cạnh chéo cắt nhau ở (2,2). Tổng shoelace:

~~~text
cross((0,0),(4,4)) = 0
cross((4,4),(0,4)) = 16
cross((0,4),(4,0)) = -16
cross((4,0),(0,0)) = 0

S = 0
A_s = 0
~~~

Nhưng các vùng tam giác phía trên và dưới vẫn có **diện tích hình học dương**; nếu tính hợp của hai tam giác trong hình nơ bướm này, tổng diện tích là **8**.

**Không được hiểu “S=0” là hình không có phần bên trong** trong trường hợp tự cắt. Đây là ví dụ phản chứng quan trọng đối với việc dùng |S|/2 như diện tích hợp cho mọi chuỗi đỉnh.

### Nếu bài hỏi diện tích miền của polygon tự cắt

Phải xác định **quy tắc vùng trong**:

- **Even-odd fill rule:** điểm thuộc miền nếu tia từ điểm cắt biên số lần lẻ.
- **Nonzero winding rule:** điểm thuộc miền nếu winding number khác 0.
- **Geometric union của các mảnh** sau khi cắt giao nhau: có thể cần xử lý arrangement và hợp vùng.

Các khái niệm này có thể cho kết quả khác nhau trên đường tự cắt phức tạp. Công thức shoelace nguyên bản cho **tổng có hướng theo đường đi**, không tự động áp dụng cả ba quy ước.

Có thể phải **tìm giao điểm cạnh, chia các vùng đơn rồi cộng diện tích không chồng lấp** khi yêu cầu area union.

## 13. Polygon có lỗ: cộng các vòng biên theo hướng

Một miền có thể gồm:

- Một hoặc nhiều **vòng ngoài** (outer rings).
- Một hoặc nhiều **vòng lỗ** (holes).

Khi các vòng đơn, không giao nhau và cấu trúc chứa/lồng nhau rõ ràng, ta có thể dùng **diện tích có hướng** để cộng các thành phần.

Quy ước thường dùng trong hệ x-right, y-up:

- Vòng ngoài đi **CCW**, S dương.
- Vòng lỗ đi **CW**, S âm.

Khi đó:

**S_net = Σ S_outer + Σ S_hole**,

và **A_net = S_net/2** nếu tất cả vòng có hướng nhất quán cho cùng miền.

### Ví dụ vòng ngoài và một lỗ

Vòng ngoài hình vuông 10×10:

~~~text
(0,0) -> (10,0) -> (10,10) -> (0,10)
S_outer = +200
A_outer = 100
~~~

Lỗ hình vuông từ (2,2) tới (5,5), sắp theo CW:

~~~text
(2,2) -> (2,5) -> (5,5) -> (5,2)
S_hole = -18
A_hole = 9
~~~

Cộng:

**S_net = 200−18=182**,

**A_net = 182/2=91**.

Không được lấy trị tuyệt đối **trước khi cộng** nếu đang dựa vào hướng vòng để trừ lỗ: |200|+|−18| sẽ cho 109, sai.

### Các ràng buộc cần kiểm tra

- Vòng lỗ phải thực sự nằm trong miền ngoài.
- Các vòng phải được tổ chức theo đúng quan hệ chứa/lồng nhau.
- Hướng ngoài/lỗ phải được chuẩn hóa theo hợp đồng ứng dụng.
- Các vòng giao nhau, chạm nhau hoặc lồng nhiều cấp cần quy tắc hình học riêng.

Với nhiều polygon rời nhau và lỗ nhiều tầng, không nên cộng bừa các signed rings nếu chưa xác định **hướng và cấp lồng**. Một số chuẩn dữ liệu địa lý có các quy tắc khác về hướng ring và vùng nội thất.

## 14. Tọa độ nguyên: giữ “hai lần diện tích” để chính xác

Nếu tất cả xᵢ,yᵢ là **số nguyên**, mỗi cross là số nguyên, nên:

**S=2A_s là số nguyên**.

Do đó diện tích của một polygon đơn có tọa độ nguyên luôn thuộc tập:

**{0, 0.5, 1, 1.5, 2, 2.5, ...}**.

Thay vì tính A bằng double hay chia nguyên, có thể lưu **S** chính xác trong suốt quá trình rồi xuất:

- Nếu |S| chẵn: **(|S|/2).0**.
- Nếu |S| lẻ: **floor(|S|/2).5**.

Với signed area, thêm dấu '-' nếu S<0.

Ví dụ:

~~~text
S = +12 -> signed area  6.0, area 6.0
S = -12 -> signed area -6.0, area 6.0
S =  +3 -> signed area  1.5, area 1.5
S =  -3 -> signed area -1.5, area 1.5
~~~

Đây là **định dạng thập phân chính xác** của diện tích cho tọa độ nguyên, không cần BigDecimal hoặc double.

### BigInteger và phép chia âm

BigInteger.divideAndRemainder với giá trị âm có quy tắc dấu của remainder theo BigInteger, không tự làm phần thập phân signed trở nên đơn giản. Code demo lấy **abs(S)** rồi chia 2, sau đó mới thêm dấu âm nếu cần, bảo đảm kết quả "-1.5" đúng.

## 15. Vì sao long có thể overflow ngay cả khi tọa độ nhìn có vẻ vừa?

Một số người viết:

~~~java
long sum = 0;
sum += x[i] * y[j] - y[i] * x[j];
~~~

Có ít nhất ba rủi ro:

1. **x·y tràn long** nếu tọa độ đủ lớn.
2. **Phép trừ hai tích tràn long** ngay cả khi một hoặc hai tích riêng lẻ vừa.
3. **Tổng qua n cạnh tràn long**, dù từng cross có thể vừa.

Ví dụ hình vuông:

~~~text
(0,0)
(10000000000,0)
(10000000000,10000000000)
(0,10000000000)
~~~

Diện tích hình học là:

**10^10·10^10 = 10^20**.

Tổng shoelace:

**S = 2·10^20 = 200000000000000000000**.

Long.MAX_VALUE chỉ khoảng 9.22·10^18, nên cả diện tích và S đều vượt miền long.

### Dùng BigInteger cho tính đúng tuyệt đối trên tọa độ nguyên

Java BigInteger.multiply và subtract thực hiện số học nguyên chính xác, không wrap long:

~~~java
BigInteger cross = x1.multiply(y2)
        .subtract(y1.multiply(x2));
sum = sum.add(cross);
~~~

Nếu tọa độ có thể vượt long ngay từ đầu, **đọc chúng bằng new BigInteger(String)**. Không parse qua Long.parseLong hoặc ép double trước.

### Dùng long khi nào?

Có thể dùng long nếu **chứng minh chặt** được cận của mỗi tích, mỗi hiệu và tổng. Ví dụ, nếu |x|,|y|≤M với n cạnh, ta có:

**|cross(Pᵢ,Pᵢ₊₁)|≤2M²**,

và:

**|S|≤2nM²**.

Đây là cận thô nhưng dễ kiểm tra. Nếu các cận này nằm trong Long.MAX_VALUE thì long an toàn. Phải tính các cận bằng kiểu đủ rộng để không overflow khi kiểm tra.

## 16. Phép trừ tọa độ cũng có thể overflow

Một cách viết khác của diện tích tam giác là:

**cross(B−A,C−A)**.

Nếu tọa độ là long và A gần Long.MIN_VALUE còn B gần Long.MAX_VALUE, phép trừ:

**B.x − A.x**

có thể vượt long dù từng tọa độ riêng lẻ vẫn hợp lệ.

Sai:

~~~java
long dx = bx - ax; // Can overflow.
BigInteger dxBig = BigInteger.valueOf(dx);
~~~

Lúc chuyển dxBig, giá trị đã sai.

Đúng:

~~~java
BigInteger dxBig =
        BigInteger.valueOf(bx)
                .subtract(BigInteger.valueOf(ax));
~~~

Tương tự, nếu dùng xᵢ·yⱼ với BigInteger, **chuyển từng tọa độ trước khi nhân**.

### Dùng double có được không?

Nếu tọa độ là số thực đo đạc và bài chấp nhận sai số, double có thể phù hợp. Nhưng cần phân tích sai số:

- Phép nhân tọa độ lớn có thể mất phần bit thấp.
- Tổng cross có thể triệt tiêu mạnh khiến **cancellation error**.
- Nếu polygon gần suy biến, dấu S có thể bị đánh giá sai.
- Tính hình học chuẩn đôi khi cần predicates chính xác (exact orientation test).

Khi tọa độ là số nguyên và bài đòi kết quả chính xác, BigInteger là lựa chọn rõ ràng hơn.

## 17. Nếu tọa độ là số thập phân hữu hạn

Công thức shoelace vẫn đúng cho tọa độ thực. Nhưng code BigInteger của bài chỉ nhận **tọa độ nguyên**.

Nếu input có đúng k chữ số sau dấu thập phân, có thể **nhân mọi tọa độ với SCALE=10^k** để chuyển về số nguyên, với điều kiện tất cả các trục dùng cùng tỷ lệ.

Khi đó:

**x'=SCALE·x**, **y'=SCALE·y**.

Diện tích theo hệ đã nhân tỉ lệ là:

**A' = SCALE²·A**.

Vì vậy:

**A = |S'| / (2·SCALE²)**,

trong đó S' là tổng có hướng tính trên tọa độ nguyên đã scale.

Ví dụ một hình chữ nhật dài 1.2, rộng 0.5:

- Chọn SCALE=10.
- Kích thước sau scale là 12 và 5.
- Diện tích sau scale là 60.
- Diện tích thật bằng 60/100=**0.6**.

Nếu trục x và y được scale theo hai hệ số khác nhau Sₓ,Sᵧ, phải chia cho **Sₓ·Sᵧ**, không mặc định bình phương một hệ số.

### Không lẫn BigDecimal với BigInteger

BigDecimal thuận tiện cho phép tính thập phân hữu hạn nhưng vẫn cần quy định độ chính xác khi chia. Nếu cần kết quả phân số chính xác từ tọa độ hữu tỉ, có thể biểu diễn bằng **tử số/mẫu số BigInteger** thay vì đổi qua double.

## 18. Công thức diện tích tam giác và hướng ba điểm

Với ba điểm A,B,C:

**2A_s(ABC)=cross(B−A,C−A)**.

Khai triển:

**cross(B−A,C−A)=cross(A,B)+cross(B,C)+cross(C,A)**.

Đây chính là shoelace của tam giác A→B→C→A.

Hàm **orientation(A,B,C)** thường dựa vào dấu của cross(B−A,C−A):

- >0: rẽ trái (CCW).
- <0: rẽ phải (CW).
- =0: thẳng hàng.

### Không nhầm orientation của ba điểm với hướng toàn polygon

Một polygon **lõm** có cả những bộ ba đỉnh liên tiếp tạo rẽ trái và rẽ phải. Dấu của một cross cục bộ **không quyết định** hướng chung của đường biên.

Để tìm hướng tổng thể của polygon đơn, dùng **dấu tổng shoelace S**, hoặc một phương pháp orientation toàn vòng đã được chứng minh tương đương.

### Công dụng khác của cross

Cùng toán tử cross còn xuất hiện khi:

- Kiểm tra ba điểm thẳng hàng.
- Kiểm tra hai đoạn thẳng giao nhau.
- Dựng convex hull bằng monotone chain.
- Tính diện tích tam giác.
- Xác định nửa mặt phẳng và hướng cạnh.

Nhưng khi chuyển giữa các bài, cần chú ý **hai vector được lấy từ đâu** để không đổi dấu hoặc sai điểm gốc.

## 19. Đếm điểm nguyên và định lý Pick

Với một **đa giác đơn** có các đỉnh là điểm nguyên (lattice polygon), diện tích liên hệ với số điểm nguyên qua **định lý Pick**:

**A = I + B/2 − 1**,

trong đó:

- I là số **điểm nguyên nằm hoàn toàn trong** polygon.
- B là số **điểm nguyên nằm trên đường biên**.

Nhân hai vế với 2:

**2A = 2I + B − 2**.

Công thức này chỉ áp dụng theo giả thiết polygon lattice đơn thích hợp, không dùng trực tiếp cho đa giác tự cắt hay polygon có lỗ mà không điều chỉnh Euler characteristic.

### Đếm B theo gcd cạnh

Với một cạnh có vector dịch:

**Δx=x₂−x₁**, **Δy=y₂−y₁**,

số đoạn nhỏ đơn vị lattice trên cạnh là:

**gcd(|Δx|,|Δy|)**.

Với polygon đơn có các cạnh không chồng sai, tổng:

**B = Σ gcd(|Δxᵢ|,|Δyᵢ|)**.

Mỗi điểm đỉnh ở hai cạnh được xử lý đúng khi cộng số đoạn lattice thay vì cộng cả hai đầu riêng lẻ.

### Ví dụ hình chữ nhật 5×3

Nếu hình chữ nhật có góc (0,0),(5,0),(5,3),(0,3):

- Điểm trong: I=(5−1)(3−1)=**8**.
- Điểm biên: B=2(5+3)=**16**.
- Pick: A=8+16/2−1=**15**.

Shoelace cũng cho A=15.

### Giá trị cho kiểm thử

Pick rất hữu ích làm **oracle độc lập** cho polygon nguyên nhỏ:

1. Đếm các điểm nguyên hoàn toàn bên trong bằng phép point-in-polygon.
2. Tính B bằng gcd cạnh.
3. So **2I+B−2** với **|S|**.

Cách này độc lập với tổng cross trong công thức shoelace, giúp phát hiện lỗi về dấu hoặc thứ tự điểm trong chương trình.

## 20. Kết nối với xử lý chu vi và trọng tâm

Từ một danh sách polygon vertices, có thể tính thêm:

- **Chu vi:** cộng độ dài Euclidean của các cạnh.
- **Độ dài cạnh bình phương:** không cần căn cho nhiều bài so sánh.
- **Hướng polygon:** dấu tổng S.
- **Trọng tâm polygon (centroid):** cũng có công thức tổng có hướng liên quan đến cross, nhưng cần diện tích có hướng khác 0.
- **Diện tích của nhiều rings:** cộng signed sums đúng orientation và nesting.

### Chu vi không suy ra từ diện tích

Hai polygon có cùng diện tích nhưng chu vi rất khác nhau. Shoelace không tính chu vi; phải dùng độ dài cạnh:

**perimeter=Σ sqrt((Δx)²+(Δy)²)**.

Nếu tọa độ nguyên rất lớn, phép tính bình phương chênh lệch cũng cần tránh overflow.

### Trọng tâm cần phân biệt polygon và đường biên

Trọng tâm của **miền diện tích** khác trung bình cộng các đỉnh và khác trọng tâm của đường biên. Không thể lấy trung bình xᵢ,yᵢ của các đỉnh rồi coi đó là centroid diện tích cho mọi polygon.

## 21. Java 17+: chương trình shoelace chính xác bằng BigInteger

Chương trình độc lập sau dùng **BigInteger** cho mọi tọa độ và mọi tích cross. Vì vậy:

- Không tràn long khi tọa độ hoặc tổng diện tích lớn.
- Giữ nguyên **S=2A_s** dưới dạng số nguyên.
- Xuất chính xác diện tích với hậu tố **.0 hoặc .5**.
- Trả nhãn **CCW, CW hoặc ZERO_SIGNED_AREA** theo quy ước x-right, y-up.
- Dùng cạnh cuối nối về đầu bằng **(i+1)%n**.
- Chấp nhận một danh sách có đỉnh đầu lặp lại cuối; cạnh zero-length không làm thay đổi S.
- Trả 0 cho n<3.
- **Không tự xác minh polygon đơn**: với polygon tự cắt, trả tổng đại số có hướng, không giả vờ đó là diện tích hợp miền.
- Minh họa một vòng lỗ CW được trừ khỏi vòng ngoài CCW.

**Lưu tệp: ShoelacePolygonAreaDemo.java**

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class ShoelacePolygonAreaDemo {

    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger TWO = BigInteger.valueOf(2L);

    record Point(BigInteger x, BigInteger y) {
        Point {
            Objects.requireNonNull(x, "x");
            Objects.requireNonNull(y, "y");
        }
    }

    static Point p(long x, long y) {
        return new Point(
                BigInteger.valueOf(x),
                BigInteger.valueOf(y));
    }

    static Point p(String x, String y) {
        return new Point(
                new BigInteger(x),
                new BigInteger(y));
    }

    static BigInteger signedDoubleArea(List<Point> polygon) {
        Objects.requireNonNull(polygon, "polygon");

        int n = polygon.size();

        if (n < 3) {
            return ZERO;
        }

        BigInteger sum = ZERO;

        for (int i = 0; i < n; i++) {
            Point a = Objects.requireNonNull(
                    polygon.get(i), "vertex");
            Point b = Objects.requireNonNull(
                    polygon.get((i + 1) % n), "vertex");

            BigInteger cross =
                    a.x().multiply(b.y())
                    .subtract(a.y().multiply(b.x()));

            sum = sum.add(cross);
        }

        return sum;
    }

    // Exact half-integer formatting for integer coordinates.
    static String formatHalf(BigInteger twiceArea) {
        Objects.requireNonNull(twiceArea, "twiceArea");

        BigInteger abs = twiceArea.abs();
        BigInteger[] quotientAndRemainder =
                abs.divideAndRemainder(TWO);

        String sign = twiceArea.signum() < 0 ? "-" : "";
        String fraction =
                quotientAndRemainder[1].signum() == 0
                        ? ".0" : ".5";

        return sign + quotientAndRemainder[0] + fraction;
    }

    // Interpretation assumes x-right, y-up coordinates.
    static String orientation(BigInteger twiceArea) {
        int sign = twiceArea.signum();
        if (sign > 0) return "CCW";
        if (sign < 0) return "CW";
        return "ZERO_SIGNED_AREA";
    }

    static List<Point> reversed(List<Point> original) {
        List<Point> copy = new ArrayList<>(original);
        Collections.reverse(copy);
        return copy;
    }

    static void show(String label, List<Point> polygon) {
        BigInteger twice = signedDoubleArea(polygon);

        System.out.println(label
                + ": signed2=" + twice
                + ", signedArea=" + formatHalf(twice)
                + ", area=" + formatHalf(twice.abs())
                + ", orientation=" + orientation(twice));
    }

    public static void main(String[] args) {

        List<Point> triangle = List.of(
                p(0, 0), p(4, 0), p(0, 3));

        show("Triangle", triangle);
        show("Triangle reversed", reversed(triangle));

        show("Half-unit triangle", List.of(
                p(0, 0), p(3, 0), p(0, 1)));

        show("Rectangle", List.of(
                p(1, 1), p(6, 1), p(6, 4), p(1, 4)));

        show("Concave L", List.of(
                p(0, 0), p(6, 0), p(6, 2),
                p(2, 2), p(2, 5), p(0, 5)));

        show("Collinear edge", List.of(
                p(0, 0), p(2, 0), p(5, 0),
                p(5, 3), p(0, 3)));

        show("Repeated first", List.of(
                p(0, 0), p(4, 0), p(0, 3), p(0, 0)));

        show("Collinear triangle", List.of(
                p(0, 0), p(1, 1), p(2, 2)));

        // Self-intersection: signed area is not union area.
        show("Bow-tie (algebraic)", List.of(
                p(0, 0), p(4, 4), p(0, 4), p(4, 0)));

        show("Huge square", List.of(
                p("0", "0"),
                p("10000000000", "0"),
                p("10000000000", "10000000000"),
                p("0", "10000000000")));

        show("Translated triangle", List.of(
                p("123456789012345678901234567890",
                  "-98765432109876543210987654321"),
                p("123456789012345678901234567894",
                  "-98765432109876543210987654321"),
                p("123456789012345678901234567890",
                  "-98765432109876543210987654318")));

        List<Point> outer = List.of(
                p(0, 0), p(10, 0), p(10, 10), p(0, 10));

        List<Point> clockwiseHole = List.of(
                p(2, 2), p(2, 5), p(5, 5), p(5, 2));

        show("Outer ring", outer);
        show("Clockwise hole", clockwiseHole);

        BigInteger netDoubleArea =
                signedDoubleArea(outer)
                .add(signedDoubleArea(clockwiseHole));

        System.out.println("Outer + hole: signed2="
                + netDoubleArea
                + ", netArea=" + formatHalf(netDoubleArea.abs()));
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 ShoelacePolygonAreaDemo.java
java ShoelacePolygonAreaDemo
~~~

**Đầu ra chính xác theo chương trình:**

~~~text
Triangle: signed2=12, signedArea=6.0, area=6.0, orientation=CCW
Triangle reversed: signed2=-12, signedArea=-6.0, area=6.0, orientation=CW
Half-unit triangle: signed2=3, signedArea=1.5, area=1.5, orientation=CCW
Rectangle: signed2=30, signedArea=15.0, area=15.0, orientation=CCW
Concave L: signed2=36, signedArea=18.0, area=18.0, orientation=CCW
Collinear edge: signed2=30, signedArea=15.0, area=15.0, orientation=CCW
Repeated first: signed2=12, signedArea=6.0, area=6.0, orientation=CCW
Collinear triangle: signed2=0, signedArea=0.0, area=0.0, orientation=ZERO_SIGNED_AREA
Bow-tie (algebraic): signed2=0, signedArea=0.0, area=0.0, orientation=ZERO_SIGNED_AREA
Huge square: signed2=200000000000000000000, signedArea=100000000000000000000.0, area=100000000000000000000.0, orientation=CCW
Translated triangle: signed2=12, signedArea=6.0, area=6.0, orientation=CCW
Outer ring: signed2=200, signedArea=100.0, area=100.0, orientation=CCW
Clockwise hole: signed2=-18, signedArea=-9.0, area=9.0, orientation=CW
Outer + hole: signed2=182, netArea=91.0
~~~

### Giải thích thiết kế chương trình

**Point record:** giữ tọa độ x,y kiểu BigInteger, có kiểm tra null. Hai hàm p(long,long) và p(String,String) thuận tiện cho tọa độ nhỏ và cực lớn.

**signedDoubleArea:** không chia cho 2 trong vòng lặp; nó tích lũy chính xác S bằng BigInteger. Với n<3, trả 0. Với n≥3, cạnh cuối được khép bởi modulo n.

**formatHalf:** lấy giá trị tuyệt đối của S, chia cho 2 bằng BigInteger, chọn .0 hoặc .5 theo phần dư, rồi thêm dấu âm khi S<0. Vì vậy không có rủi ro mất .5 hoặc biểu diễn -0.0.

**orientation:** chỉ diễn giải dấu signedDoubleArea, chưa thực hiện kiểm tra tính đơn của polygon. Nhãn ZERO_SIGNED_AREA được chọn có chủ ý vì S=0 có thể xuất hiện cả ở đường suy biến và đường tự cắt triệt tiêu.

**reversed:** sao chép danh sách trước khi đảo, không sửa polygon gốc; đặc biệt List.of là danh sách bất biến và không cho Collections.reverse trực tiếp.

**Outer + hole:** cộng signedDoubleArea của hai rings khi vòng ngoài CCW và vòng lỗ CW. Nếu lỗ được liệt kê CCW, kết quả sẽ cộng sai diện tích lỗ.

### Những giới hạn của demo

- Chỉ nhận tọa độ **nguyên**, không nhận trực tiếp số thập phân hay căn thức.
- Không kiểm tra tự giao, không sắp đỉnh, không xác định nesting của nhiều rings.
- Không tính union area cho các đường tự cắt.
- Không kiểm tra một lỗ có thực sự nằm trong vòng ngoài hay không.
- Không xuất diện tích dưới dạng phân số tùy ý cho tọa độ hữu tỉ, chỉ xuất .0/.5 cho tọa độ nguyên.
- BigInteger bảo đảm tính đúng số học nhưng không bảo đảm chi phí CPU/memory nhỏ với input quá lớn.

Đây là các giới hạn có chủ ý để tách **công thức shoelace** khỏi các bài kiểm tra tính hợp lệ và thao tác trên miền hình học phức tạp.

## 22. Độ phức tạp theo mô hình số học

Gọi n là số đỉnh.

Một vòng for xử lý mỗi cạnh một lần, mỗi cạnh gồm:

- Hai phép nhân tọa độ.
- Một phép trừ.
- Một phép cộng vào tổng.

Số lượng phép toán tọa độ:

**O(n)**.

Nếu coi các tọa độ là từ máy có độ rộng cố định và các phép nhân/cộng O(1), tổng thời gian là **O(n)** và bộ nhớ phụ **O(1)**, không tính dữ liệu đầu vào.

### Trong BigInteger, cần nói rõ bit complexity

BigInteger phải cấp phát các số trung gian và thực hiện phép nhân có chi phí phụ thuộc độ dài bit của tọa độ. Vì vậy code Java không có thời gian bit tổng quát chỉ O(n) độc lập với giá trị các tọa độ.

Một cách phát biểu chính xác:

**O(n) phép toán BigInteger**, và tổng thời gian thực tế còn phụ thuộc kích thước bit của tọa độ, tích và tổng.

Bộ nhớ dùng để lưu danh sách n đỉnh là **O(n)** đối tượng Point/BigInteger. Ngoài danh sách đã có, một phiên bản streaming có thể chỉ giữ đỉnh đầu, đỉnh trước và tổng để xử lý từng cạnh, tức O(1) đỉnh phụ, cộng bộ nhớ của BigInteger sum/intermediates.

### Công thức streaming

~~~text
first = readFirstPoint()
prev = first
sum = 0

for each nextPoint:
    sum += cross(prev, nextPoint)
    prev = nextPoint

sum += cross(prev, first)
answer = abs(sum) / 2
~~~

Cách này phù hợp nếu không cần lưu polygon để thực hiện các phép toán khác. Nếu dữ liệu được nhập từ file lớn, có thể tránh giữ toàn bộ n đỉnh trong RAM.

## 23. Cách kiểm thử độc lập với hình chữ nhật và đa giác chữ L

Một bộ kiểm thử tốt **không chỉ viết lại shoelace ở hai hàm khác nhau**, vì hai hàm có thể cùng mắc lỗi về chỉ số hoặc dấu.

### Oracle hình chữ nhật

Với góc (x,y), chiều rộng w>0, chiều cao h>0, diện tích hình học phải là:

**A=w·h**,

**|S|=2·w·h**.

Tạo nhiều hình chữ nhật với x,y âm/dương, w,h thay đổi. Thử cả CCW và CW:

- CCW → S=+2wh.
- CW → S=−2wh.
- Đảo thứ tự → đổi dấu.
- Tịnh tiến cùng vector → giữ nguyên S.

Điều này kiểm tra trực tiếp công thức diện tích hình chữ nhật, **khác cách cộng cross**.

### Oracle đa giác lõm chữ L

Với các đỉnh:

~~~text
(0,0), (w,0), (w,b),
(a,b), (a,h), (0,h)
~~~

trong đó **0<a<w**, **0<b<h**, diện tích theo hai hình chữ nhật là:

**A=w·b+a·(h−b)**.

Shoelace phải cho **S=2A** ở thứ tự trên, và **−2A** khi đảo thứ tự.

Dùng hàng trăm bộ w,h,a,b ngẫu nhiên giúp bắt lỗi chỉ đúng trên hình lồi nhưng sai ở polygon lõm.

### Tịnh tiến với tọa độ cực lớn

Nếu cộng Tₓ=10^30, Tᵧ=−10^30 vào tất cả đỉnh, S phải **giữ nguyên**. Kiểm thử này dễ phát hiện triển khai sai do nhân/trừ bằng long hoặc double rồi mới chuyển BigInteger.

### Đa giác tự cắt

Đưa ví dụ nơ bướm có S=0 vào test để bảo đảm API phân biệt **signed area** với **union area** và không in một tuyên bố sai “hình có diện tích hình học 0” nếu input tự cắt.

## 24. Kiểm thử độc lập bằng định lý Pick

Với polygon lattice đơn nhỏ, có thể dùng định lý Pick như một oracle khác:

**|S| = 2I+B−2**.

Một quy trình kiểm thử:

1. Sinh ngẫu nhiên nhiều điểm nguyên và lấy **convex hull** để bảo đảm đường biên đơn.
2. Tính S bằng hàm shoelace đang kiểm tra.
3. Với mỗi điểm nguyên trong bounding box nhỏ, kiểm tra điểm có nằm **strictly inside** hull không. Đếm được I.
4. Tính B bằng **Σ gcd(|Δx|,|Δy|)** theo các cạnh hull.
5. So **|S|** với **2I+B−2**.

Đây là oracle khác bản chất: đếm lattice points thay vì lấy tổng cross.

### Điểm trên biên

Khi kiểm tra I, **không được tính điểm trên cạnh** là điểm trong. Một điểm nằm trên đoạn AB nếu:

- cross(B−A,P−A)=0.
- x và y của P nằm trong khoảng tọa độ giữa A và B, kể cả hai đầu.

Nếu point-in-polygon dùng ray casting, cần xử lý đỉnh biên đúng để không đếm nhầm.

### Phạm vi kiểm thử Pick

Chỉ dùng cho **simple lattice polygons**. Nếu polygon có lỗ, cần công thức được điều chỉnh theo đặc trưng Euler; nếu polygon tự cắt hoặc có cạnh chồng, không áp dụng nguyên 2I+B−2.

## 25. Các lỗi phổ biến

1. **Quên nối đỉnh cuối về đỉnh đầu**, thiếu hạng cross cuối.
2. **Đếm hạng cuối hai lần** khi vừa thêm P₀ vào danh sách vừa khép vòng sai.
3. **Đổi thứ tự x/y trong cross**, đảo dấu.
4. **Dùng xᵢyᵢ thay vì xᵢyᵢ₊₁**, sai công thức.
5. **Lấy abs từng cross rồi cộng**, thay vì abs của tổng.
6. **Quên chia 2**, trả diện tích gấp đôi.
7. **Chia nguyên S/2**, làm mất .5 với tọa độ nguyên.
8. **Quên abs khi yêu cầu diện tích không âm** của polygon đơn.
9. **Lấy abs quá sớm ở từng ring lỗ**, làm lỗ bị cộng thay vì trừ.
10. **Nhầm dấu CW/CCW vì tọa độ màn hình y-down**, không ghi quy ước hệ trục.
11. **Tự sort đỉnh theo x hoặc y rồi tính**, làm thay đổi đường biên và có thể tạo tự cắt.
12. **Áp dụng |S|/2 cho polygon tự cắt rồi gọi là union area**, có thể sai lớn.
13. **Tuyên bố S=0 nghĩa hình học trống**, dù nơ bướm có S=0 và vùng dương.
14. **Giả định polygon phải lồi**, bỏ khả năng áp dụng cho polygon lõm đơn.
15. **Không xử lý cạnh thẳng hàng/đỉnh trùng liên tiếp**, tạo logic thừa hoặc sai nếu tự loại điểm không đúng.
16. **Dùng int cho tích tọa độ**, overflow nhanh.
17. **Dùng long mà không chứng minh cận tích và tổng**, overflow khi tọa độ lớn.
18. **Nhân long trước rồi mới BigInteger.valueOf**, giá trị đã sai.
19. **Lấy hiệu tọa độ long trước khi chuyển BigInteger**, có thể overflow.
20. **Chuyển tọa độ nguyên rất lớn thành double**, mất chính xác rồi báo diện tích sai.
21. **Dùng BigDecimal/double để in .5 trong khi S nguyên**, tăng rủi ro không cần thiết.
22. **In signed area với dấu sai cho S âm lẻ**, ví dụ -3/2 phải là -1.5.
23. **Không nêu polygon đơn hay tự cắt**, mơ hồ ý nghĩa “diện tích”.
24. **Không nêu quy ước vòng ngoài/lỗ**, cộng signed rings sai.
25. **Nhầm số đỉnh với số cạnh**, trong một vòng khép kín n đỉnh có n cạnh.
26. **Quên điểm cuối ở mảng n=0/1/2**, có thể truy cập ngoài.
27. **Cho rằng cross của mọi cạnh đều cùng dấu khi polygon CCW**, không đúng.
28. **Nhầm orientation(A,B,C) của ba điểm với sign tổng của polygon lõm**, suy ra sai.
29. **Dùng công thức Pick cho polygon tự cắt hoặc lỗ mà không chỉnh**, sai điều kiện.
30. **Không kiểm tra diện tích khi tịnh tiến tọa độ rất lớn**, bỏ lỗi cancellation/overflow.
31. **Không kiểm tra đảo thứ tự đỉnh**, bỏ lỗi dấu của tổng.
32. **Cho rằng BigInteger không bị giới hạn tài nguyên**, không kiểm soát input cực lớn.
33. **Làm tròn diện tích quá sớm rồi cộng nhiều hình**, tích lũy sai số.
34. **Quên rằng nếu cả hai tọa độ scale theo k thì diện tích scale theo k²**, sai đơn vị.
35. **Đưa điểm theo thứ tự quét dữ liệu thay vì thứ tự đường biên**, tính diện tích một đường khác.
36. **Tự ý loại đỉnh lặp bất kỳ dù việc loại có thể thay đổi topology**, đặc biệt với nhiều vòng và đường biên không đơn.
37. **Không phân biệt phần trong theo even-odd và winding**, sai khi xử lý đường tự cắt.
38. **Xem signed area bằng 0 như hướng CCW/CW xác định**, dù hướng trong trường hợp này không có dấu.
39. **Sử dụng dấu khoanh biên theo y-down cho thuật toán y-up**, sai kết quả orientation.
40. **Tin rằng BigInteger area trả trực tiếp một số nguyên đơn vị diện tích**, trong khi S là **hai lần** diện tích có hướng.

## 26. Bài tập tự luyện

**Bài 1 — Tam giác.** Tính S và A cho (0,0),(4,0),(0,3).  
**Đáp án:** S=12, A=6, CCW.

**Bài 2 — Đảo chiều.** Đảo thứ tự tam giác Bài 1.  
**Đáp án:** S=−12, signed area −6, diện tích vẫn 6.

**Bài 3 — Nửa đơn vị.** Cho (0,0),(3,0),(0,1).  
**Đáp án:** S=3, A=1.5.

**Bài 4 — Hình chữ nhật.** Cho (1,1),(6,1),(6,4),(1,4).  
**Đáp án:** A=15.

**Bài 5 — Lõm.** Cho (0,0),(6,0),(6,2),(2,2),(2,5),(0,5).  
**Đáp án:** A=18.

**Bài 6 — Đỉnh thẳng hàng.** Chèn (2,0) giữa (0,0) và (5,0) trên cạnh dưới hình chữ nhật.  
**Đáp án:** Diện tích không đổi.

**Bài 7 — Khép vòng.** Nếu danh sách đã kết thúc ở P₀, cạnh cuối từ P₀ đến P₀ đóng góp bao nhiêu?  
**Đáp án:** cross(P₀,P₀)=0.

**Bài 8 — Nơ bướm.** Cho (0,0),(4,4),(0,4),(4,0).  
**Đáp án:** S=0, nhưng không được suy ra union area bằng 0.

**Bài 9 — Vòng lỗ.** Vòng ngoài diện tích100, lỗ CW diện tích9.  
**Đáp án:** S_net=182, A_net=91.

**Bài 10 — Tịnh tiến.** Dịch mọi đỉnh một vector (12345678901234567890,−9999999999999999999).  
**Đáp án:** S và A không đổi nếu tính số học chính xác.

**Bài 11 — Long overflow.** Hình vuông cạnh 10^10 có S bằng bao nhiêu?  
**Đáp án:** S=2·10^20, vượt long.

**Bài 12 — Tọa độ thập phân.** Nhân cả x và y với SCALE=100, tổng S' mới so với S ban đầu thế nào?  
**Đáp án:** S'=10000S; diện tích mới nếu đo theo đơn vị cũ phải chia 10000.

**Bài 13 — Pick.** Hình chữ nhật 5×3 có I,B nào?  
**Đáp án:** I=8,B=16; A=8+8−1=15.

**Bài 14 — Tìm lỗi.** Vì sao tổng |cross(Pᵢ,Pᵢ₊₁)| không thay thế được |Σcross|?  
**Đáp án:** Mất triệt tiêu các phần diện tích có hướng, dễ đếm thừa.

**Bài 15 — Hướng màn hình.** Đảo dấu mọi tọa độ y của một polygon CCW toán học.  
**Đáp án:** S đổi dấu, diện tích |S|/2 không đổi.

**Bài 16 — Tính tổng streaming.** Viết phiên bản chỉ giữ đỉnh đầu, đỉnh trước và sum.  
**Gợi ý:** Sau khi đọc hết, nhớ cộng cross(last,first).

**Bài 17 — Bảo đảm chính xác.** Nếu tọa độ lên tới 10^30 và yêu cầu đúng tuyệt đối, dùng kiểu nào trong Java?  
**Đáp án:** BigInteger cho tọa độ, tích và tổng.

**Bài 18 — Hợp miền tự cắt.** Nếu đề yêu cầu even-odd area của đường tự cắt, chỉ dùng shoelace có đủ không?  
**Đáp án:** Không; cần phân chia vùng hoặc thuật toán xử lý miền theo quy tắc đã chọn.

**Bài 19 — Kiểm thử.** Tại sao dùng hình chữ nhật ngẫu nhiên và định lý Pick có giá trị hơn chỉ so hai bản code shoelace?  
**Đáp án:** Hai oracle dùng công thức hình học độc lập, có khả năng phát hiện lỗi chung của cách cài đặt shoelace.

**Bài 20 — Độ phức tạp.** n đỉnh, mọi phép toán tọa độ coi O(1), thời gian shoelace?  
**Đáp án:** O(n), chỉ một lượt qua các cạnh.

## 27. Tổng kết và checklist áp dụng

Trước khi dùng công thức shoelace, hãy tự kiểm tra:

1. **Danh sách đỉnh có đúng thứ tự trên chu trình biên** hay chỉ là tập điểm chưa được sắp?
2. Đa giác có **đơn, không tự cắt** không? Nếu tự cắt, đề muốn signed area hay area union theo quy tắc nào?
3. Hệ tọa độ đang dùng **y-up hay y-down**, và định nghĩa CCW/CW theo hệ nào?
4. Có đúng **cạnh cuối→đỉnh đầu** trong tổng chưa?
5. Đã tính **S=Σ(xᵢyᵢ₊₁−xᵢ₊₁yᵢ)** với dấu đúng chưa?
6. Khi cần diện tích hình học của polygon đơn, đã dùng **|S|/2** thay vì Σ|cross|/2 chưa?
7. Nếu tọa độ nguyên, có giữ **S nguyên chính xác** để không mất .5 không?
8. Mỗi tích, hiệu và tổng có thể vượt **int/long** không? Nếu có, chuyển sang BigInteger **trước phép tính**.
9. Nếu có nhiều rings, vòng ngoài/lỗ đã theo **hướng tương thích** và quan hệ chứa đã rõ chưa?
10. Nếu dùng tọa độ thập phân đã scale, có chia diện tích theo **tích hệ số scale của hai trục** chưa?
11. Đã thử **tam giác, hình chữ nhật, đa giác lõm, CW, điểm thẳng hàng, nơ bướm và tọa độ lớn** chưa?
12. Đã kiểm chứng **đảo thứ tự làm đổi dấu**, **tịnh tiến giữ nguyên S** và diện tích các hình đơn giản bằng oracle độc lập chưa?
13. Có cần thêm **simple polygon validation**, xử lý giao cạnh, clipping hay hợp miền không? Những chức năng đó **không tự xuất hiện** trong một vòng shoelace.
14. Khi phân tích độ phức tạp, phân biệt **O(n) phép toán số** và chi phí bit khi tọa độ là BigInteger.

**Kết luận:** Với một polygon đơn có thứ tự đỉnh đúng, chỉ cần cộng tích có hướng của những cặp đỉnh liên tiếp rồi lấy trị tuyệt đối và chia đôi là tính được diện tích trong **O(n)** phép toán. Giữ **hai lần diện tích có hướng** dưới dạng số nguyên chính xác là cách làm an toàn, rõ ràng, dễ kiểm thử; còn các đường tự cắt, vòng lỗ và hệ tọa độ khác nhau cần được xử lý đúng theo **ngữ nghĩa hình học cụ thể** của bài toán.
