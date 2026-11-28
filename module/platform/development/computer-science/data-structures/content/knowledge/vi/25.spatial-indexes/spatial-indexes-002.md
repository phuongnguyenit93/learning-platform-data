# Lưới không gian và chia miền thành các ô

Giả sử một trò chơi có 100.000 nhân vật, mỗi khung hình phải tìm những nhân vật ở gần người chơi. Nếu lần nào cũng kiểm tra khoảng cách từ người chơi tới **mọi** nhân vật, chương trình phải xét 100.000 đối tượng, ngay cả khi chỉ có vài chục đối tượng ở gần. Một giải pháp trực quan là **chia mặt phẳng thành những ô**, lưu danh sách đối tượng nằm trong mỗi ô, rồi chỉ đọc các ô có thể liên quan đến truy vấn.

Ý tưởng đó dẫn tới **lưới không gian** (*spatial grid*), đặc biệt là **lưới đều** (*uniform grid*) và **băm không gian** (*spatial hashing*). Chúng thường đơn giản hơn cây không gian, cho phép truy cập ô trực tiếp bằng phép tính số học và có thể cập nhật vị trí đối tượng động. Nhưng một lựa chọn kích thước ô không phù hợp có thể làm truy vấn phải duyệt hàng nghìn ô hoặc hàng nghìn đối tượng trong một ô.

Bài học thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Ta sẽ xây dựng công thức ánh xạ tọa độ vào ô, quy ước biên, cách lưu điểm và hình có kích thước, thuật toán truy vấn phạm vi/bán kính/láng giềng, cập nhật động, độ phức tạp thời gian–bộ nhớ và cài đặt Python minh họa. Mục tiêu không chỉ là tìm nhanh mà còn là **không bỏ sót đối tượng nằm đúng trên ranh giới ô**.

> **Nguyên tắc cốt lõi:** Ô lưới là một **bộ lọc ứng viên**. Việc một điểm nằm trong ô được xét không tự chứng minh điểm thuộc vùng truy vấn; phải kiểm tra tọa độ hoặc hình học thật. Đổi lại, bỏ một ô có thể liên quan là lỗi nghiêm trọng vì làm **mất kết quả đúng**.

## 1. Từ kiểm tra tất cả điểm đến chia miền

Cho tập điểm \(P=\{p_1,\ldots,p_n\}\subset\mathbb R^2\). Một truy vấn hình chữ nhật \(Q=[a,b]\times[c,d]\) cần trả:

\[
\boxed{R(Q)=\{p\in P:a\le p_x\le b,\ c\le p_y\le d\}.}
\]

**Cách đơn giản:** Duyệt \(n\) điểm, kiểm tra bốn bất đẳng thức cho từng điểm. Với số chiều \(d\) tổng quát, thời gian \(O(nd)\); trong 2D cố định thường ghi \(O(n)\).

**Ý tưởng chia miền:** Phủ mặt phẳng bởi các ô có kích thước đã biết. Mỗi điểm được gán vào một ô; chỉ duyệt các ô **giao hoặc có khả năng giao** vùng \(Q\). Với những ô không liên quan, ta bỏ qua **toàn bộ điểm bên trong** mà không cần kiểm tra từng điểm.

~~~text
                         y
                         ^
            +-----+-----+-----+-----+
            |  ·  |  P  |     |  ·  |
            +-----+-----+-----+-----+
            |     | +---+---+ |     |
            +-----+-|---+---|-+-----+
            |  P  | | P | P | |  ·  |
            +-----+-|---+---|-+-----+
            |     | +---+---+ |  P  |
            +-----+-----+-----+-----+----> x

         Khung nằm giữa hình là vùng truy vấn Q.
         Chỉ các ô bị Q chạm tới mới cần xét.
~~~

Một điểm ở ô ngoài vùng truy vấn chắc chắn không cần xét **nếu phép xác định ô và phạm vi truy vấn được xây dựng nhất quán**. Phần còn lại của bài làm rõ chính xác điều kiện này.

## 2. Lưới đều: miền, gốc tọa độ và kích thước ô

Trong mặt phẳng, chọn:

- **Gốc lưới** \(o=(o_x,o_y)\): điểm mốc để đánh chỉ số.
- **Chiều rộng ô** \(s_x>0\).
- **Chiều cao ô** \(s_y>0\).

Nếu là **ô vuông**, đặt \(s_x=s_y=s\). Một ô được định danh bằng cặp **chỉ số nguyên** \((i,j)\), không phải bằng một nhãn tùy ý.

Với quy tắc ô **nửa mở** theo mỗi trục:

\[
\boxed{C_{i,j}
=[o_x+i s_x,\ o_x+(i+1)s_x)
\times[o_y+j s_y,\ o_y+(j+1)s_y).}
\]

Các ô kề nhau không chồng lấn phần **được sở hữu** theo quy ước nửa mở; hợp của các ô với \(i,j\in\mathbb Z\) phủ toàn mặt phẳng. Nhờ đó một điểm hữu hạn có **đúng một ô chứa nó**.

### Công thức tìm ô từ tọa độ

Với điểm \(p=(x,y)\):

\[
\boxed{
i=\left\lfloor\frac{x-o_x}{s_x}\right\rfloor,\qquad
j=\left\lfloor\frac{y-o_y}{s_y}\right\rfloor.}
\]

Giá trị \(i,j\) có thể **âm**. Dấu \(\lfloor\cdot\rfloor\) là **floor** (làm tròn xuống tới số nguyên nhỏ hơn hoặc bằng), không phải làm tròn về 0.

Ví dụ với \(o=(0,0)\), \(s_x=s_y=10\):

| Điểm | Chỉ số ô \((i,j)\) | Giải thích |
| --- | --- | --- |
| \((3,7)\) | \((0,0)\) | Cả hai tọa độ thuộc \([0,10)\) |
| \((9{,}999,0)\) | \((0,0)\) | Chưa chạm biên \(x=10\) |
| \((10,0)\) | \((1,0)\) | Biên trái ô mới thuộc ô \((1,0)\) |
| \((20,10)\) | \((2,1)\) | Cả hai tọa độ nằm trên biên mới |
| \((-0{,}1,5)\) | \((-1,0)\) | \(\lfloor-0{,}01\rfloor=-1\) |
| \((-10,0)\) | \((-1,0)\) | Biên trái của ô \((-1,0)\) |
| \((-10{,}01,-0{,}01)\) | \((-2,-1)\) | Hai trục âm, phải dùng floor |

**Lỗi phổ biến:** Lấy \(\operatorname{int}(x/s)\) trong một ngôn ngữ mà chuyển số thực sang số nguyên bằng cách **cắt phần thập phân về 0**. Với \(x=-0{,}1\) và \(s=10\), kết quả là 0 thay vì \(-1\), khiến điểm bị gán vào ô sai.

### Khôi phục biên ô từ chỉ số

Cho \((i,j)\), có thể tính:

\[
x_{\min}=o_x+i s_x,\quad x_{\max}=o_x+(i+1)s_x,
\]
\[
y_{\min}=o_y+j s_y,\quad y_{\max}=o_y+(j+1)s_y.
\]

**Tâm hình học** của ô là:

\[
\boxed{\operatorname{center}(C_{i,j})
=\bigl(o_x+(i+\tfrac12)s_x,\
o_y+(j+\tfrac12)s_y\bigr).}
\]

Tâm ô thuận tiện để vẽ hoặc ước lượng khoảng cách giữa các ô, nhưng **không thay thế** tọa độ thật của các điểm nằm trong ô.

## 3. Bất biến quan trọng: mỗi điểm thuộc đúng một ô

Đối với một tập điểm tĩnh, lưới đều có thể được mô tả bằng ánh xạ:

\[
\boxed{\operatorname{cell}:P\to\mathbb Z^2.}
\]

Mỗi bản ghi điểm xuất hiện ở **một bucket ứng với ô chứa tọa độ của nó**. Khi ID là khóa định danh duy nhất, một bất biến dữ liệu có thể viết:

\[
\forall p\in P,\quad
\operatorname{id}(p)\in
\operatorname{bucket}(\operatorname{cell}(p)).
\]

Và để tránh kết quả trùng hoặc tham chiếu cũ:

\[
\operatorname{id}(p)
\notin \operatorname{bucket}(c)
\quad\text{với mọi }c\ne\operatorname{cell}(p).
\]

Điều này áp dụng cho **điểm**. Một **đoạn thẳng hoặc hình chữ nhật có kích thước** có thể giao nhiều ô; ta sẽ xem hai cách lưu đối tượng mở rộng ở phần sau.

### Tọa độ trùng không có nghĩa ID trùng

~~~text
ID 101 -> (3, 7)
ID 202 -> (3, 7)
~~~

Cả hai thuộc cùng ô \((0,0)\), nhưng là **hai bản ghi khác nhau**. Bucket phải chứa danh sách/tập ID hoặc các đối tượng có danh tính riêng. Không được dùng cặp tọa độ làm khóa duy nhất nếu nghiệp vụ cho phép nhiều đối tượng ở cùng vị trí.

### Vì sao ô nửa mở hữu ích?

Cho hai ô kề nhau theo trục \(x\):

\[
C_0=[0,10),\qquad C_1=[10,20).
\]

Điểm \(x=10\) chỉ nằm trong **\(C_1\)**. Nếu cả hai cùng dùng biên đóng \([0,10]\), \([10,20]\), điểm trên biên sẽ thuộc **hai ô**, làm mất quy tắc gán điểm duy nhất.

**Đừng nhầm quy tắc gán điểm với quy tắc truy vấn.** Ta sẽ vẫn có thể dùng cửa sổ truy vấn **biên đóng** để trả cả điểm ở \(x=10\); việc đó đòi hỏi xác định phạm vi ô cần quét một cách bảo thủ.

## 4. Lưới hữu hạn và lưới không giới hạn

Có hai cách hiểu về miền được chia:

**Lưới hữu hạn:** một hình chữ nhật thế giới đã biết trước, ví dụ \([0,1000)\times[0,600)\), được chia thành \(100\times60\) ô vuông cạnh 10. Chỉ số hợp lệ nằm trong \(0\le i<100\), \(0\le j<60\).

**Lưới không giới hạn về mặt logic:** công thức chỉ số áp dụng với mọi \(i,j\in\mathbb Z\); chỉ tạo dữ liệu lưu cho những ô đang chứa đối tượng. Đây là cách quen thuộc của **spatial hashing**.

Với miền hữu hạn, cần quy định xử lý điểm ngoài miền:

- **Từ chối** điểm ngoài miền.
- **Mở rộng** miền lưới và cấp phát ô mới.
- **Dùng lớp chỉ mục khác** hoặc vùng đệm cho đối tượng ngoài biên.
- **Chuẩn hóa tuần hoàn** chỉ khi bài toán thực sự có không gian tuần hoàn, ví dụ một thế giới game quấn quanh.

**Không nên tự kẹp (clamp)** điểm ở ngoài miền vào ô biên mà không thay đổi bản ghi tọa độ, vì làm mất thông tin vị trí thật và gây truy vấn sai.

### Quy tắc biên ngoài cùng

Nếu miền là \([0,100)\times[0,100)\), một điểm đúng tại \(x=100\) **không thuộc miền**. Nếu nghiệp vụ muốn gồm cả biên phải/trên, phải đưa ra một quy tắc riêng: mở rộng miền, xử lý ô biên cuối đặc biệt hoặc xác định hệ ô theo cách khác. Không dùng bất đẳng thức \(x\le100\) với một lưới định nghĩa nửa mở rồi xem mọi thứ tự động nhất quán.

## 5. Mảng ô đặc và băm không gian thưa

Một lưới có thể lưu bằng hai kiến trúc khá khác nhau.

### 5.1. Lưới đặc (*dense grid*)

Với \(N_x\) cột và \(N_y\) hàng, cấp phát mảng gồm \(N_xN_y\) bucket, kể cả bucket rỗng:

~~~text
grid[j][i] = danh sách ID trong ô (i,j), theo hàng j và cột i
~~~

Nếu dùng mảng một chiều, một quy ước **row-major** thông dụng là:

\[
\boxed{\operatorname{index}(i,j)=jN_x+i,}
\]

với \(0\le i<N_x,\ 0\le j<N_y\). Phép đảo:

\[
i=\operatorname{index}\bmod N_x,\qquad
j=\left\lfloor\operatorname{index}/N_x\right\rfloor.
\]

**Ưu điểm:** tính chỉ số bucket \(O(1)\), địa chỉ ô có thể liền nhau, dễ duyệt những vùng có kích thước cố định.

**Nhược điểm:** phải giữ metadata cho **toàn bộ \(N_xN_y\) ô**, ngay cả khi chỉ có vài trăm ô chứa dữ liệu. Khi mở rộng miền hữu hạn, có thể phải cấp phát lại.

### 5.2. Spatial hashing: chỉ lưu các ô có dữ liệu

Dùng bảng băm với khóa là **cặp chỉ số ô**:

~~~text
buckets[(0, 0)]  = {101, 202}
buckets[(1, 0)]  = {305}
buckets[(-1, 0)] = {410}
~~~

Không có bucket cho ô \((7,100)\) nếu nó đang rỗng. Nhờ đó, một thế giới rất rộng nhưng dữ liệu phân bố thưa không bắt buộc cấp phát toàn bộ miền.

**Điều kiện quan trọng:** khóa ô là \((i,j)\), không phải tự động là một số “hash” duy nhất. Hai khóa ô khác nhau **có thể va chạm giá trị băm**, nhưng hash map đúng phải phân biệt chúng bằng cơ chế so sánh khóa và xử lý va chạm. Không được chỉ dùng giá trị hash modulo làm ID ô mà **không** xử lý collision.

### So sánh

| Tiêu chí | Mảng lưới đặc | Hash map ô thưa |
| --- | --- | --- |
| Miền tọa độ | Thường hữu hạn, biết trước | Có thể rộng hoặc chưa biết |
| Bucket được cấp | Mọi ô | Chủ yếu ô đang có dữ liệu |
| Truy cập ô | \(O(1)\) trong giới hạn mảng | \(O(1)\) kỳ vọng với hash phù hợp |
| Metadata | \(O(N_xN_y)\) | \(O(m)\) với \(m\) ô được lưu |
| Hỗ trợ chỉ số âm | Cần dịch sang chỉ số mảng | Khóa \((i,j)\) có thể âm |
| Nhược điểm | Nhiều ô trống, resize miền | Overhead hash, cấp phát bucket, phân bố khóa |

Nếu có **\(n\)** điểm và **\(m\)** ô đang chứa ít nhất một điểm, spatial hash lưu ID trong bucket có chi phí bộ nhớ cỡ \(O(n+m)\) **ngoài dữ liệu gốc**, tùy kiểu bucket/metadata. Với đối tượng trải qua nhiều ô, cần tính thêm số bản ghi membership — sẽ phân tích riêng.

## 6. Xác định các ô có thể liên quan đến cửa sổ truy vấn

Cho vùng truy vấn hình chữ nhật **biên đóng**:

\[
Q=[a,b]\times[c,d],\quad a\le b,\ c\le d.
\]

Nếu các điểm được gán vào ô bằng floor theo công thức ở mục 2, ta có thể xét **mọi ô** với chỉ số:

\[
\boxed{
i_{\min}=\left\lfloor\frac{a-o_x}{s_x}\right\rfloor,\quad
i_{\max}=\left\lfloor\frac{b-o_x}{s_x}\right\rfloor,}
\]

\[
\boxed{
j_{\min}=\left\lfloor\frac{c-o_y}{s_y}\right\rfloor,\quad
j_{\max}=\left\lfloor\frac{d-o_y}{s_y}\right\rfloor.}
\]

Ta duyệt mọi cặp \((i,j)\) trong hình chữ nhật chỉ số:

\[
i_{\min}\le i\le i_{\max},\qquad
j_{\min}\le j\le j_{\max}.
\]

Phạm vi này **không bỏ sót điểm nào nằm trong \(Q\)**. Lý do: nếu một điểm \(p\in Q\), phép floor trên từng trục có chỉ số nằm giữa floor của cận dưới và floor của cận trên.

### Truy vấn biên đúng ô

Cho \(s=10\), gốc \((0,0)\), cửa sổ:

\[
Q=[0,10]\times[0,10].
\]

Theo công thức, \(i,j\) đều từ **0 đến 1**, tức xét bốn ô \((0,0),(0,1),(1,0),(1,1)\).

Điểm \((10,5)\) thuộc ô **\((1,0)\)**, và vì \(x=10\) là **biên đóng của Q**, nó phải được trả. Nếu chỉ xét ô \((0,0)\) do nghĩ “cửa sổ kích thước 10 chính là một ô”, kết quả sẽ **bị bỏ sót**.

Tương tự, vùng \([-10,0]\times[-10,0]\) theo biên đóng xét các chỉ số \(-1\) tới 0 trên mỗi trục. Phạm vi quét có thể chứa ô mà **nội thất** không giao Q, nhưng vẫn an toàn.

### Hai bước quan trọng

~~~mermaid
flowchart TD
    A["Nhận cửa sổ Q có tọa độ min/max"] --> B["Tính các chỉ số ô min/max bằng floor"]
    B --> C["Duyệt mọi ô trong miền chỉ số"]
    C --> D["Lấy danh sách ID trong từng bucket"]
    D --> E{"Tọa độ điểm có thật sự nằm trong Q?"}
    E -->|Có| F["Đưa điểm vào kết quả"]
    E -->|Không| G["Bỏ ứng viên"]
~~~

Ở **bước duyệt ô**, ta cố tình chấp nhận **ứng viên dư**. Ở **bước kiểm tra điểm**, ta loại hết false positive. Đối với điểm chỉ lưu đúng một ô, cùng ID sẽ không xuất hiện hai lần nếu bucket được quản lý đúng.

### Độ phức tạp

Đặt:

\[
C_Q=(i_{\max}-i_{\min}+1)(j_{\max}-j_{\min}+1)
\]

là **số ô được duyệt** và \(V_Q\) là **tổng số ID đọc từ các bucket đó**. Với 2D, chi phí truy vấn là:

\[
\boxed{T_{\mathrm{range}}=O(C_Q+V_Q+k)}
\]

theo mô hình băm trung bình, \(k\) là số kết quả được xuất. Vì \(k\le V_Q\) với dữ liệu điểm không trùng membership, có thể viết gọn \(O(C_Q+V_Q)\), nhưng việc nêu riêng \(k\) làm rõ chi phí xuất dữ liệu.

Trong trường hợp thuận lợi, \(C_Q\) nhỏ và \(V_Q\ll n\). Trong trường hợp xấu, truy vấn phủ nhiều ô hoặc một ô chứa gần hết \(n\) điểm, chi phí vẫn có thể gần **\(O(n)\)** hoặc lớn hơn nếu phải liệt kê quá nhiều ô rỗng.

## 7. Truy vấn hình tròn/bán kính bằng hộp ứng viên

Cho tâm \(q=(q_x,q_y)\) và bán kính \(r\ge0\), ta muốn tìm:

\[
\boxed{R(q,r)=
\{p\in P:(p_x-q_x)^2+(p_y-q_y)^2\le r^2\}.}
\]

Một hình tròn nằm trọn trong hộp bao:

\[
\boxed{B_r=[q_x-r,q_x+r]\times[q_y-r,q_y+r].}
\]

Thuật toán an toàn:

1. Xác định mọi ô cần xét theo **AABB \(B_r\)**.
2. Lấy các điểm ứng viên trong các bucket đó.
3. Tính **bình phương khoảng cách Euclid** tới \(q\).
4. Chỉ nhận điểm có \(D_2^2(p,q)\le r^2\).

### Ví dụ vì sao cần lọc chính xác

Với \(q=(0,0)\), \(r=5\), điểm \((4,4)\) nằm trong hộp \([-5,5]\times[-5,5]\) nhưng:

\[
D_2^2((4,4),q)=4^2+4^2=32>25=r^2.
\]

Do đó \((4,4)\) **không thuộc** vùng bán kính. Không được trả toàn bộ điểm trong hình vuông thay cho kết quả hình tròn.

### Có cần kiểm tra mọi ô quanh tâm?

Khi \(r\le s\) và lưới gồm ô vuông cạnh \(s\), hộp truy vấn bán kính có thể cắt tối đa **3 ô trên mỗi trục**, tức tối đa **9 ô trong 2D** theo phép liệt kê floor biên đóng. Với ô không vuông, điều kiện tương ứng là \(r\le s_x\) và \(r\le s_y\).

Nhưng **chỉ xét 3×3 ô xung quanh tâm không đúng cho mọi bán kính**. Nếu \(r\gg s\), có thể phải xét hàng trăm ô trên mỗi trục; số lượng ô tăng theo **diện tích hộp truy vấn so với diện tích một ô**.

### Truy vấn NN/kNN không biết trước bán kính

Nếu muốn tìm **điểm gần nhất** mà chưa biết khoảng cách kết quả, kiểm tra chỉ các ô kề cạnh **không bảo đảm đúng**: các ô gần có thể rỗng trong khi điểm gần nhất lại nằm xa hơn.

Một cách thực hiện NN chính xác có thể:

- Duyệt ô theo **cận dưới khoảng cách từ truy vấn tới vùng ô**.
- Duy trì khoảng cách tốt nhất tới điểm đã gặp.
- Chỉ dừng khi đã chứng minh **mọi ô chưa xét đều không thể có điểm tốt hơn**, có xử lý tie nếu yêu cầu.

Điều này phức tạp hơn range/radius query; với một grid thưa không giới hạn miền, việc biết ô nào **còn dữ liệu** cũng cần tổ chức phù hợp. Không thể đưa ra bảo đảm NN chính xác chỉ bằng “mở rộng một vòng rồi dừng khi thấy điểm”.

## 8. Kiểm tra lân cận cho đối tượng động

Trong mô phỏng hạt hoặc game 2D, mỗi đối tượng thường chỉ cần so với những đối tượng cách nó không quá \(r\). Khi mọi đối tượng được gán vào ô theo vị trí tâm và \(s\) được chọn tương ứng với \(r\), lưới giúp giới hạn những **cặp cần thử**.

Nếu \(r\le s\) cho lưới ô vuông, các đối tượng có thể ở trong cùng ô hoặc một trong **tối đa tám ô kề** của ô chứa tâm, nếu chỉ hỏi khoảng cách giữa **các tâm điểm**. Vì hai điểm ở những ô cách nhau **ít nhất một ô đầy đủ** trên một trục sẽ cách nhau **lớn hơn hoặc bằng** \(s\) theo trục đó; khi \(r\le s\), các ô xa hơn không thể tạo cặp khoảng cách **nhỏ hơn r**.

Với các ô **nửa mở** như bài định nghĩa và \(r\le s\), các tâm thuộc hai ô có chỉ số chênh nhau ít nhất 2 trên một trục sẽ cách nhau **lớn hơn \(s\)** trên trục ấy: biên phải của ô đứng trước bị loại khỏi ô đó. Vì thế xét chính ô chứa tâm và tám ô kề là an toàn cho các **cặp điểm** theo khoảng cách Euclid, kể cả dấu bằng ở \(r=s\). Nếu hệ thống chọn **quy ước biên khác**, có sai số làm tròn, hoặc đang xét **vật thể có kích thước**, hãy quay về cách liệt kê ô theo hộp truy vấn ở mục 7 thay vì áp dụng mẹo 3×3 một cách máy móc.

**Phân biệt vị trí tâm và kích thước vật thể:** Hai vật thể lớn có thể **va chạm dù tâm cách xa hơn \(r\)**. Nếu lưới chỉ gán theo tâm, phải tính thêm bán kính/biên độ vật thể hoặc dùng cách lưu hình vào các ô giao với **hộp bao vật thể**, như phần sau.

### Tránh xét trùng cặp

Khi tìm mọi cặp đối tượng gần nhau, không nên vừa xét \((A,B)\) trong bucket A vừa xét \((B,A)\) trong bucket B mà ghi thành **hai tương tác khác nhau**. Có thể chuẩn hóa cặp theo ID, ví dụ chỉ xét nếu \(id(A)<id(B)\), hoặc duyệt mỗi cặp ô không thứ tự đúng một lần.

Nếu các ô rất đông, số cặp trong một ô có \(t\) điểm là:

\[
\binom t2=\frac{t(t-1)}2,
\]

có thể đạt \(O(t^2)\). Lưới giảm phạm vi tìm ứng viên nhưng **không loại bỏ** chi phí trường hợp xấu khi có rất nhiều đối tượng tập trung một chỗ.

## 9. Một hình có thể giao nhiều ô

Với **điểm**, một tọa độ có đúng một ô sở hữu. Nhưng nếu dữ liệu là **hộp chữ nhật, đoạn thẳng, đa giác hoặc vật thể 3D**, một đối tượng có thể phủ **nhiều ô**.

Ví dụ AABB:

\[
B=[8,22]\times[4,15],\qquad s=10,\ o=(0,0).
\]

Các chỉ số từ min/max:

\[
i\in\{0,1,2\},\qquad j\in\{0,1\}.
\]

Hộp có khả năng giao **6 ô**, nên một chiến lược là lưu ID của B vào **cả 6 bucket** đó.

### Hai chiến lược lưu hình

**A. Đăng ký vào mọi ô mà hình giao (*multi-cell insertion*)**

- Ưu điểm: truy vấn cửa sổ chỉ cần đọc những ô cửa sổ có thể chạm; dễ chứng minh không bỏ sót.
- Nhược điểm: một vật thể rất lớn có thể được thêm vào hàng nghìn bucket; khi truy vấn phải **khử trùng ID**.
- Dữ liệu cần lưu reverse mapping hoặc tái tính các ô cũ để xóa/cập nhật đúng.

**B. Đăng ký một ô đại diện (thường theo tâm hoặc gốc hình)**

- Ưu điểm: một đối tượng chỉ nằm trong một bucket, giảm số membership.
- Nhược điểm: nếu chỉ tìm các ô mà **cửa sổ truy vấn chạm** rồi đọc các ô đại diện, có thể **bỏ sót** vật thể lớn có tâm nằm xa nhưng một góc của hình giao Q.
- Muốn đúng phải mở rộng miền truy vấn theo cỡ vật thể tối đa đã biết, có danh sách riêng cho vật thể lớn hoặc dùng chỉ mục phụ phù hợp.

**Không được tráo đổi chiến lược A và B mà giữ nguyên thuật toán truy vấn.** Mỗi chiến lược đi kèm một bất biến khác nhau về “những ô nào bắt buộc chứa ID của đối tượng”.

### Lọc false positive

Nếu đối tượng là **AABB** và truy vấn là hộp đóng, kiểm tra AABB giao Q là **predicate chính xác**.

Nếu đối tượng là **đa giác/đường thẳng**, AABB chỉ cho **ứng viên**. Một đa giác có hộp bao giao Q vẫn có thể không giao Q; sau khi lấy ứng viên phải gọi phép kiểm tra hình học thật.

### Vì sao phải khử trùng?

Giả sử một hình R được đăng ký ở 6 ô. Nếu một cửa sổ Q quét đủ 6 ô và chỉ nối toàn bộ ID trong từng bucket vào kết quả, R sẽ bị trả tới **6 lần**. Một tập **seen ID** có thể bảo đảm mỗi đối tượng được kiểm tra/đưa ra một lần.

Với \(n\) đối tượng hình, đặt \(r_a\) là số ô mà hình \(a\) được đăng ký. Tổng số membership:

\[
\boxed{M=\sum_{a=1}^{n}r_a.}
\]

Chi phí bộ nhớ không chỉ \(O(n+m)\) như với điểm, mà gần:

\[
\boxed{O(n+m+M)}
\]

theo số bản ghi, bucket và membership, chưa kể overhead của từng cấu trúc. Một số vật thể cực lớn có thể khiến \(M\gg n\).

## 10. Cập nhật động: thêm, xóa và di chuyển đối tượng

Điểm mạnh của lưới đều là có thể xác định ô cần cập nhật **trực tiếp từ tọa độ**. Tuy nhiên, để duy trì kết quả đúng, dữ liệu gốc và chỉ mục phải luôn thống nhất.

### Thêm điểm mới

Với bản ghi \((id,p)\):

1. Kiểm tra ID chưa tồn tại (nếu ID phải duy nhất).
2. Tính ô \(c=\operatorname{cell}(p)\).
3. Thêm ID vào bucket \(c\).
4. Lưu bản ghi hoặc cập nhật ánh xạ ID → tọa độ.

Nếu hash map và bucket set hoạt động tốt, chi phí thường **\(O(1)\) kỳ vọng** cho việc định ô và thêm ID, bỏ qua chi phí cấp phát/phát triển bảng băm hiếm gặp.

### Xóa điểm

Muốn xóa ID nhanh, cần biết tọa độ hoặc ô cũ. Có thể lưu:

~~~text
records[ID] = (x, y)
buckets[(i,j)] = {ID1, ID2, ...}
~~~

Tra records[ID], tính ô cũ, loại ID khỏi bucket. Nếu bucket trở thành rỗng, spatial hash có thể xóa hẳn khóa ô để tiết kiệm metadata.

### Di chuyển điểm

Nếu điểm \(p\) di chuyển thành \(p'\), đặt:

\[
c_{\mathrm{old}}=\operatorname{cell}(p),\qquad
c_{\mathrm{new}}=\operatorname{cell}(p').
\]

**Nếu hai ô giống nhau**, chỉ cần cập nhật tọa độ của bản ghi; membership vẫn đúng.

**Nếu hai ô khác nhau**, phải:

1. Gỡ ID khỏi bucket cũ.
2. Đưa ID vào bucket mới.
3. Cập nhật tọa độ gốc.

~~~text
Trước:
    ID 21 ở (9.8, 3)  -> ô (0,0)

Di chuyển:
    ID 21 tới (10.2, 3) -> ô (1,0)

Sau:
    buckets[(0,0)] không còn ID 21
    buckets[(1,0)] có ID 21
    records[21] = (10.2, 3)
~~~

**Lỗi thường gặp:** Chỉ thay tọa độ trong records nhưng vẫn giữ ID tại bucket cũ. Khi truy vấn quanh vị trí mới, chương trình không đọc bucket cũ, dẫn đến **bỏ sót đối tượng**. Nếu ID bị để lại trong cả hai bucket, một truy vấn có thể trả trùng hoặc mất công lọc bản ghi stale.

### Cập nhật hình giao nhiều ô

Nếu một hình AABB đang chiếm tập ô \(S_{\mathrm{old}}\) và sau thay đổi chiếm \(S_{\mathrm{new}}\), ta có thể cập nhật theo **hiệu tập hợp**:

\[
\boxed{\begin{aligned}
S_{\mathrm{remove}}&=S_{\mathrm{old}}\setminus S_{\mathrm{new}},\\
S_{\mathrm{add}}&=S_{\mathrm{new}}\setminus S_{\mathrm{old}}.
\end{aligned}}
\]

Các ô trong giao \(S_{\mathrm{old}}\cap S_{\mathrm{new}}\) giữ nguyên membership. Cách này tránh phải tháo rồi thêm lại mọi ô khi hình chỉ dịch chuyển rất ít.

Nếu hệ thống quản lý dữ liệu ở nhiều luồng, phải bảo đảm **không có truy vấn nhìn thấy trạng thái nửa cũ nửa mới** theo yêu cầu nhất quán của sản phẩm: dùng khóa, snapshot, giao dịch hoặc phiên bản chỉ mục phù hợp.

## 11. Chọn kích thước ô: đánh đổi quan trọng nhất

Kích thước \(s\) quyết định đồng thời **số ô truy vấn phải đọc** và **số đối tượng trong mỗi bucket**.

### Nếu ô quá lớn

- Có **ít ô** và chi phí duyệt ô nhỏ.
- Một ô có thể chứa **rất nhiều điểm**.
- Cửa sổ nhỏ phải lọc nhiều ứng viên **không nằm trong cửa sổ**.
- Với \(n\) điểm tập trung trong một ô, truy vấn tại ô đó vẫn có thể cần \(O(n)\) phép so sánh.

### Nếu ô quá nhỏ

- Mỗi ô thường có ít điểm hơn.
- Một truy vấn lớn có thể cắt qua **hàng nghìn ô**, kể cả ô trống.
- Spatial hash có thể phải tạo/quản lý nhiều bucket.
- Nếu một hình vật lý lớn trải qua nhiều ô, số membership tăng mạnh.

| Kích thước ô | Số ô phải quét cho Q cố định | Số điểm trung bình trong một ô | Rủi ro |
| --- | --- | --- | --- |
| Rất nhỏ | Lớn | Thường ít | Duyệt ô rỗng, metadata, hình bị nhân bản |
| Vừa với workload | Tương đối cân bằng | Vừa phải | Cần benchmark theo phân bố thực |
| Rất lớn | Ít | Có thể nhiều | Quét nhiều điểm ứng viên |

### Ước lượng sơ bộ theo mật độ điểm

Giả sử các điểm phân bố **tương đối đều**, mật độ:

\[
\rho=\frac{n}{A}
\]

đơn vị **điểm trên một đơn vị diện tích** trong miền rộng \(A\). Với ô vuông cạnh \(s\), diện tích ô là \(s^2\), nên số điểm trung bình mỗi ô xấp xỉ:

\[
\boxed{\lambda\approx\rho s^2.}
\]

Muốn một ô chứa trung bình \(t\) điểm, có thể chọn thử:

\[
\boxed{s\approx\sqrt{\frac{t}{\rho}}.}
\]

**Ví dụ:** Có 100.000 điểm phân bố tương đối đều trong \(1\,000\,000\text{ m}^2\). Mật độ \(\rho=0{,}1\) điểm/m². Muốn khoảng 10 điểm/ô:

\[
s\approx\sqrt{\frac{10}{0{,}1}}=10\text{ m}.
\]

Đây là **gợi ý bắt đầu đo**, không phải kích thước tối ưu chung. Nếu điểm tập trung thành cụm, một số ô có thể có hàng nghìn điểm dù \(\lambda=10\).

### Ước lượng số ô một cửa sổ phải quét

Cho Q rộng \(W\), cao \(H\), ô vuông cạnh \(s\). Bỏ qua phần làm tròn và các ô biên, số ô quét khoảng:

\[
\boxed{C_Q\approx\frac{WH}{s^2}.}
\]

Công thức chỉ là xấp xỉ phần diện tích. Trong thực tế:

\[
C_Q=(i_{\max}-i_{\min}+1)(j_{\max}-j_{\min}+1),
\]

và có thể lớn hơn \(\frac{WH}{s^2}\) đáng kể khi Q rất nhỏ, suy biến hoặc nằm đúng ranh giới.

### Mục tiêu không phải “ít ô nhất”

Một mô hình thời gian thô cho range query:

\[
\boxed{T(Q)\approx aC_Q+bV_Q+c k,}
\]

với \(a\) là chi phí xét một ô, \(b\) là chi phí kiểm tra một ứng viên và \(c\) là chi phí xuất kết quả. Những hệ số này phụ thuộc phần cứng/triển khai. Tăng \(s\) thường giảm \(C_Q\) nhưng tăng \(V_Q\); giảm \(s\) thường có tác động ngược lại.

Vì thế nên **benchmark nhiều giá trị \(s\)** trên đúng phân bố dữ liệu và đúng loại truy vấn. Một kích thước tốt cho truy vấn bán kính 5 mét không mặc nhiên tốt cho truy vấn vùng 5 km.

## 12. Mật độ không đều, hotspot và các giải pháp mở rộng

Lưới đều sử dụng **cùng kích thước ô trên toàn miền**. Điều này có lợi cho tính đơn giản, nhưng hạn chế khi dữ liệu rất không đều.

~~~text
Vùng phía trái: mật độ rất cao       Vùng phía phải: thưa

  +------+------+------+           +------+------+------+
  |***** |***** |***** |           |      |  *   |      |
  |***** |***** |***** |           |      |      |      |
  +------+------+------+           +------+------+------+
  |***** |***** |***** |           |      |      |  *   |
  +------+------+------+           +------+------+------+

  * là một hoặc nhiều điểm.
~~~

Một vùng trung tâm dày đặc có thể khiến các bucket trong vùng đó quá lớn, trong khi phần còn lại gần như rỗng.

### Các hướng khắc phục

**Giảm kích thước ô toàn cục:** có thể giải quyết hotspot phần nào nhưng khiến vùng thưa cần nhiều ô để quét. Không phải lúc nào cũng hợp lý.

**Lưới phân cấp (*hierarchical grid*) hoặc lưới đa độ phân giải:** chia những vùng đông thành ô nhỏ hơn hoặc lưu nhiều tầng ô khác kích thước. Có thể truy vấn phù hợp cả vật thể nhỏ và lớn, nhưng cần quy tắc phân cấp, dedup và cập nhật.

**Quadtree (2D) / octree (3D):** chia không gian thích nghi theo vùng; phù hợp nếu mật độ chênh lệch lớn. Tuy nhiên vẫn phải xử lý giới hạn độ sâu, điểm trùng tọa độ và hình giao nhiều ô.

**R-tree hoặc chỉ mục nhóm hộp bao:** thường đáng cân nhắc khi dữ liệu gồm nhiều hình học có kích thước khác nhau, đặc biệt khi chúng không tự nhiên phù hợp với một kích thước ô.

**Tách vật thể lớn ra lớp riêng:** có thể dùng một danh sách/nhánh chỉ mục cho vật thể lớn, còn vật thể nhỏ dùng lưới. Mọi truy vấn phải **kết hợp đủ các nguồn ứng viên** và khử trùng theo ID.

### Điểm trùng tọa độ

Nếu 100.000 bản ghi cùng tọa độ, thay đổi \(s\) không thể phân chúng ra các ô khác. Chúng vẫn nằm trong một bucket. Khi truy vấn vùng chứa tọa độ đó, thực chất **100.000 kết quả** có thể phải được xuất. Không chỉ mục nào có thể tránh thời gian \(\Omega(k)\) để trả đủ \(k\) bản ghi.

Nếu truy vấn chỉ cần **đếm** thay vì trả từng ID, một hệ thống có thể lưu thống kê tổng hợp trên ô. Nhưng để trả lời **đếm chính xác cho cửa sổ cắt một phần ô**, vẫn cần kiểm tra điểm trong phần biên hoặc sử dụng chỉ mục/tổng hợp tinh hơn.

## 13. Từ 2D sang 3D và \(d\) chiều

Với vector \(p=(p_1,\ldots,p_d)\), gốc lưới \(o=(o_1,\ldots,o_d)\) và kích thước ô \(s_i>0\), ta có:

\[
\boxed{c_i=\left\lfloor\frac{p_i-o_i}{s_i}\right\rfloor,\qquad
i=1,\ldots,d.}
\]

Mỗi ô được xác định bằng tuple nguyên:

\[
\boxed{c=(c_1,c_2,\ldots,c_d)\in\mathbb Z^d.}
\]

Trong **3D**, một ô là một khối hộp; một truy vấn AABB phải xét:

\[
\boxed{C_Q=\prod_{i=1}^{d}
(c_{i,\max}-c_{i,\min}+1)}
\]

ô ứng viên, nếu ta liệt kê dải chỉ số hình hộp đầy đủ.

Nếu một truy vấn phải xét ba ô trên mỗi trục, số ô là:

| Số chiều | Số ô \(3^d\) |
| ---: | ---: |
| 2 | 9 |
| 3 | 27 |
| 5 | 243 |
| 10 | 59.049 |
| 20 | 3.486.784.401 |

Đây là một biểu hiện của **lời nguyền số chiều** (*curse of dimensionality*). Spatial hash thưa có thể tránh cấp phát các ô rỗng, nhưng nếu thuật toán truy vấn **liệt kê mọi tổ hợp chỉ số**, số ô phải tra vẫn có thể cực lớn.

**Không mặc định lưới 2D mở rộng hiệu quả tới vector 100 chiều.** Đối với dữ liệu nhiều chiều như embedding, các cấu trúc tìm láng giềng gần đúng (*ANN*) chuyên dụng có thể phù hợp hơn nếu ứng dụng chấp nhận đánh đổi độ chính xác.

## 14. Tọa độ, sai số số thực và trường hợp biên

Các phép tính cell index dựa trên floor, nên lỗi số học gần ranh giới có thể làm điểm bị gán sang ô bên cạnh.

### Sai số dấu phẩy động

Ví dụ về mặt toán học, \(x=0{,}3\) và \(s=0{,}1\) cho \(x/s=3\). Trong máy tính dùng IEEE 754, một số biểu diễn thập phân không chính xác tuyệt đối; phép chia có thể cho giá trị hơi **dưới hoặc trên 3**.

**Không có một epsilon cố định giải quyết đúng mọi trường hợp.** Đẩy mọi tọa độ lên thêm epsilon có thể sửa một biên nhưng làm sai biên khác.

Những lựa chọn cần cân nhắc:

- Nếu tọa độ ban đầu là **số nguyên theo đơn vị nhỏ nhất**, dùng phép chia nguyên floor.
- Nếu dữ liệu đã lượng tử hóa, áp dụng **một chính sách làm tròn nhất quán** trước khi tính ô.
- Khi dùng số thực, kiểm tra các trường hợp đúng và sát ranh giới trong cùng pipeline cập nhật/truy vấn; nếu cần xử lý hình học chính xác, dùng thư viện predicate/kiểu số thích hợp.
- Hạn chế lấy một index được tính bằng nhiều hệ tọa độ hoặc nhiều cách làm tròn khác nhau rồi giả định chúng tương đương tuyệt đối.

### Không dùng NaN hoặc vô cực làm tọa độ bình thường

\(\operatorname{floor}(\mathrm{NaN})\) không có ý nghĩa hữu hạn; vô cực cũng không tương ứng ô nguyên hợp lệ. Một chỉ mục nên **từ chối hoặc xử lý tường minh** tọa độ không hữu hạn, thay vì để chúng lan vào khóa hash.

### Tọa độ địa lý

Kinh độ/vĩ độ thông thường được đo bằng **độ**, không phải mét. Chia trực tiếp kinh độ/vĩ độ thành ô theo số độ có thể hữu ích cho lọc sơ bộ, nhưng:

- Ô có độ rộng một độ kinh độ không tương ứng cùng độ dài mét ở mọi vĩ độ.
- Gần đường đổi ngày quốc tế \(+180^\circ/-180^\circ\), một vùng liên tục có thể phải chia thành hai khoảng kinh độ.
- Muốn truy vấn bán kính theo **mét**, phải dùng metric địa lý hoặc một phép chiếu phù hợp, và bảo đảm hộp ứng viên là một cận đủ an toàn.
- Thứ tự trục và **CRS** (*coordinate reference system*) phải nhất quán.

Không dùng công thức bán kính Euclid tính bằng độ rồi gọi kết quả là **khoảng cách thực theo mét**.

## 15. Python: spatial hash cho tập điểm 2D động

Ví dụ sử dụng **Python 3.10+** và thư viện chuẩn. Ta lưu:

- Một bảng **ID → bản ghi điểm**.
- Một bảng **(chỉ số ô x, chỉ số ô y) → tập ID**.
- Kích thước ô vuông \(s>0\), gốc lưới \((o_x,o_y)\).

Các API hỗ trợ **thêm**, **xóa**, **di chuyển**, **truy vấn AABB biên đóng**, **truy vấn bán kính** và **xác minh bất biến**. Tọa độ được kiểm tra hữu hạn; ID là chuỗi không rỗng và phải duy nhất.

~~~python
from dataclasses import dataclass
from math import floor, isfinite


def finite_number(value):
    number = float(value)
    if not isfinite(number):
        raise ValueError("Tọa độ phải hữu hạn")
    return number


@dataclass(frozen=True)
class Point2D:
    id: str
    x: float
    y: float


class PointSpatialGrid:
    def __init__(self, cell_size, origin=(0, 0),
                 max_query_cells=100_000):
        self.size = finite_number(cell_size)
        if self.size <= 0:
            raise ValueError("Kích thước ô phải dương")
        self.ox = finite_number(origin[0])
        self.oy = finite_number(origin[1])
        if type(max_query_cells) is not int or max_query_cells < 1:
            raise ValueError("Giới hạn số ô phải là số nguyên dương")

        self.max_query_cells = max_query_cells
        self.points: dict[str, Point2D] = {}
        self.buckets: dict[tuple[int, int], set[str]] = {}

    def cell_of(self, x, y):
        x = finite_number(x)
        y = finite_number(y)
        tx = (x - self.ox) / self.size
        ty = (y - self.oy) / self.size
        if not (isfinite(tx) and isfinite(ty)):
            raise ValueError("Tọa độ sau chuẩn hóa quá lớn")
        return floor(tx), floor(ty)

    def _make_point(self, item_id, x, y):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("ID phải là chuỗi không rỗng")
        return Point2D(item_id, finite_number(x), finite_number(y))

    def add(self, item_id, x, y):
        if item_id in self.points:
            raise ValueError("ID đã tồn tại")
        point = self._make_point(item_id, x, y)
        key = self.cell_of(point.x, point.y)
        self.points[item_id] = point
        self.buckets.setdefault(key, set()).add(item_id)

    def remove(self, item_id):
        point = self.points.pop(item_id)
        key = self.cell_of(point.x, point.y)
        bucket = self.buckets[key]
        bucket.remove(item_id)
        if not bucket:
            del self.buckets[key]
        return point

    def move(self, item_id, new_x, new_y):
        old = self.points[item_id]
        updated = self._make_point(item_id, new_x, new_y)
        old_key = self.cell_of(old.x, old.y)
        new_key = self.cell_of(updated.x, updated.y)

        if old_key != new_key:
            old_bucket = self.buckets[old_key]
            old_bucket.remove(item_id)
            if not old_bucket:
                del self.buckets[old_key]
            self.buckets.setdefault(new_key, set()).add(item_id)

        self.points[item_id] = updated

    def _window_bounds(self, xmin, ymin, xmax, ymax):
        xmin = finite_number(xmin)
        ymin = finite_number(ymin)
        xmax = finite_number(xmax)
        ymax = finite_number(ymax)
        if xmin > xmax or ymin > ymax:
            raise ValueError("Cận min không được lớn hơn cận max")

        imin, jmin = self.cell_of(xmin, ymin)
        imax, jmax = self.cell_of(xmax, ymax)
        count = (imax - imin + 1) * (jmax - jmin + 1)
        if count > self.max_query_cells:
            raise ValueError("Quá nhiều ô: cần chiến lược truy vấn khác")
        return xmin, ymin, xmax, ymax, imin, jmin, imax, jmax

    def window(self, xmin, ymin, xmax, ymax):
        """Truy vấn AABB biên đóng, kể cả điểm đúng trên ranh giới."""
        (xmin, ymin, xmax, ymax,
         imin, jmin, imax, jmax) = self._window_bounds(
            xmin, ymin, xmax, ymax
        )

        result = []
        for i in range(imin, imax + 1):
            for j in range(jmin, jmax + 1):
                for item_id in self.buckets.get((i, j), ()):
                    point = self.points[item_id]
                    if (xmin <= point.x <= xmax
                            and ymin <= point.y <= ymax):
                        result.append(point)
        return sorted(result, key=lambda p: p.id)

    def radius(self, cx, cy, r):
        """Lấy điểm cách tâm không quá r theo metric Euclid phẳng."""
        cx = finite_number(cx)
        cy = finite_number(cy)
        r = finite_number(r)
        if r < 0:
            raise ValueError("Bán kính phải không âm")

        candidates = self.window(cx-r, cy-r, cx+r, cy+r)
        radius_sq = r * r
        return [
            p for p in candidates
            if (p.x-cx)**2 + (p.y-cy)**2 <= radius_sq
        ]

    def validate(self):
        """Xác nhận mỗi ID xuất hiện đúng một lần ở ô phù hợp."""
        seen = set()
        for key, bucket in self.buckets.items():
            if not bucket:
                raise AssertionError("Bucket rỗng chưa được xóa")
            for item_id in bucket:
                if item_id not in self.points or item_id in seen:
                    raise AssertionError("ID thiếu hoặc bị đăng ký trùng")
                p = self.points[item_id]
                if self.cell_of(p.x, p.y) != key:
                    raise AssertionError("ID nằm ở ô sai")
                seen.add(item_id)
        if seen != set(self.points):
            raise AssertionError("Một số điểm không nằm trong bucket")
        return True


grid = PointSpatialGrid(10)
grid.add("A", 0, 0)
grid.add("B", 9.9, 5)
grid.add("C", 10, 5)
grid.add("D", -0.1, 5)
grid.add("E", 25, 25)
grid.add("F", 10, 10)

assert grid.cell_of(9.9, 5) == (0, 0)
assert grid.cell_of(10, 5) == (1, 0)
assert grid.cell_of(-0.1, 5) == (-1, 0)

# Cửa sổ đóng: điểm đúng ở x=10/y=10 vẫn được trả.
assert [p.id for p in grid.window(0, 0, 10, 10)] == [
    "A", "B", "C", "F"
]

# Bán kính nhỏ: ô ứng viên nhiều hơn kết quả thật.
assert [p.id for p in grid.radius(0, 0, 5.1)] == ["A", "D"]
assert grid.validate()

# C sang một ô khác: phải thay bucket cũ và mới.
grid.move("C", -2, -2)
assert grid.cell_of(-2, -2) == (-1, -1)
assert [p.id for p in grid.window(-2, -2, 0, 0)] == ["A", "C"]
assert grid.validate()

grid.remove("B")
assert "B" not in grid.points
assert grid.validate()

# Hai bản ghi khác ID có thể cùng tọa độ.
grid.add("A2", 0, 0)
assert [p.id for p in grid.window(0, 0, 0, 0)] == [
    "A", "A2"
]
~~~

### Phân tích mã

**Điểm thuộc đúng một bucket:** phép cell_of dùng floor, và window liệt kê các ô có thể chứa điểm thuộc vùng truy vấn. Vì ID không bị nhân bản sang nhiều ô, window không cần tập seen cho loại dữ liệu này.

**Cập nhật tọa độ khác cập nhật bucket:** nếu move cùng ô thì membership không đổi; nếu đổi ô thì ID phải rời bucket cũ. Hàm validate kiểm tra chính điều kiện đó.

**Chi phí quét ô rỗng:** window phải lặp qua **tất cả cặp chỉ số ô** trong miền truy vấn, kể cả khi rất nhiều ô không tồn tại trong hash map. max_query_cells giúp ví dụ **từ chối truy vấn quá lớn** thay vì chạy vòng lặp cực dài; trong sản phẩm thật, có thể dùng một chỉ mục riêng trên các ô đang có dữ liệu hoặc một cơ chế truy vấn khác.

**Chi phí sắp xếp:** Hàm window trả kết quả đã **sắp theo ID** để thuận tiện kiểm thử, nên riêng phần sắp xếp còn cần \(O(k\log k)\) trong trường hợp tổng quát. Công thức \(O(C_Q+V_Q+k)\) ở phần lý thuyết áp dụng khi **không bắt buộc thứ tự đầu ra**. Hàm radius dùng lại window và chịu cùng chi phí sắp xếp ứng viên.

**Bảo đảm đồng thời:** mã dùng cho **một luồng cập nhật tuần tự**. Nếu nhiều luồng vừa move vừa query, một truy vấn có thể thấy ID ở bucket cũ với tọa độ mới hoặc trạng thái đang chuyển; cần khóa/phiên bản phù hợp.

**Giới hạn số thực:** bài dùng số thực hữu hạn và giả định phép tính floor phản ánh quy ước tọa độ. Với dữ liệu cực lớn hoặc rất sát biên, cần chính sách lượng tử hóa/sai số nhất quán như mục 14.

## 16. Python: hình chữ nhật đăng ký ở nhiều ô và khử trùng

Với các AABB đóng, ta có thể lưu ID của mỗi hình vào tất cả ô có chỉ số từ **floor(min)** đến **floor(max)** trên từng trục. Khi một cửa sổ truy vấn đọc nhiều bucket, dùng một **tập ID ứng viên** để một hình chỉ được xét một lần.

Mã tiếp theo độc lập về cấu trúc chỉ mục nhưng dùng lại hàm finite_number từ mục 15.

~~~python
from dataclasses import dataclass
from math import floor, isfinite


@dataclass(frozen=True)
class Rect:
    id: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def __post_init__(self):
        values = [
            finite_number(v)
            for v in (self.xmin, self.ymin, self.xmax, self.ymax)
        ]
        if values[0] > values[2] or values[1] > values[3]:
            raise ValueError("Hộp có min lớn hơn max")
        for field_name, value in zip(
            ("xmin", "ymin", "xmax", "ymax"), values
        ):
            object.__setattr__(self, field_name, value)

    def intersects(self, other):
        return (
            self.xmin <= other.xmax
            and other.xmin <= self.xmax
            and self.ymin <= other.ymax
            and other.ymin <= self.ymax
        )


class RectangleSpatialGrid:
    def __init__(self, cell_size, max_cells_per_box=10_000):
        self.size = finite_number(cell_size)
        if self.size <= 0:
            raise ValueError("Kích thước ô phải dương")
        self.limit = max_cells_per_box
        self.rects: dict[str, Rect] = {}
        self.buckets: dict[tuple[int, int], set[str]] = {}
        self.memberships: dict[str, set[tuple[int, int]]] = {}

    def cells_for(self, box):
        imin = floor(box.xmin / self.size)
        imax = floor(box.xmax / self.size)
        jmin = floor(box.ymin / self.size)
        jmax = floor(box.ymax / self.size)
        count = (imax - imin + 1) * (jmax - jmin + 1)
        if count > self.limit:
            raise ValueError("Hình/truy vấn chạm quá nhiều ô")
        return {
            (i, j)
            for i in range(imin, imax + 1)
            for j in range(jmin, jmax + 1)
        }

    def add(self, rect):
        if not rect.id or rect.id in self.rects:
            raise ValueError("ID rỗng hoặc đã tồn tại")
        covered = self.cells_for(rect)
        self.rects[rect.id] = rect
        self.memberships[rect.id] = covered
        for key in covered:
            self.buckets.setdefault(key, set()).add(rect.id)

    def move(self, rect):
        """Thay hình hiện có, cập nhật theo hiệu hai tập ô."""
        if rect.id not in self.rects:
            raise KeyError(rect.id)

        new_cells = self.cells_for(rect)  # Kiểm tra trước khi sửa.
        old_cells = self.memberships[rect.id]

        for key in old_cells - new_cells:
            bucket = self.buckets[key]
            bucket.remove(rect.id)
            if not bucket:
                del self.buckets[key]
        for key in new_cells - old_cells:
            self.buckets.setdefault(key, set()).add(rect.id)

        self.memberships[rect.id] = new_cells
        self.rects[rect.id] = rect

    def remove(self, item_id):
        rect = self.rects.pop(item_id)
        for key in self.memberships.pop(item_id):
            bucket = self.buckets[key]
            bucket.remove(item_id)
            if not bucket:
                del self.buckets[key]
        return rect

    def window(self, query):
        candidates = set()
        for key in self.cells_for(query):
            candidates.update(self.buckets.get(key, ()))

        # Dedup đã xong; kiểm tra giao AABB thực sự.
        return sorted(
            (self.rects[item_id] for item_id in candidates
             if self.rects[item_id].intersects(query)),
            key=lambda box: box.id,
        )


rect_grid = RectangleSpatialGrid(10)
large = Rect("R", 8, 4, 22, 15)
rect_grid.add(large)
rect_grid.add(Rect("S", 50, 50, 51, 51))
rect_grid.add(Rect("T", 10, 10, 20, 20))

# R chạm 3 cột (0,1,2) và 2 hàng (0,1): 6 ô.
assert len(rect_grid.memberships["R"]) == 6

q = Rect("query", 10, 10, 10, 10)
assert [box.id for box in rect_grid.window(q)] == ["R", "T"]

# Dù R được đọc qua nhiều ô, kết quả chỉ có một R.
wide_query = Rect("q2", 0, 0, 30, 30)
assert [box.id for box in rect_grid.window(wide_query)] == [
    "R", "T"
]

# Dịch chuyển R sang nơi khác và cập nhật membership.
rect_grid.move(Rect("R", 30, 30, 33, 33))
assert [box.id for box in rect_grid.window(q)] == ["T"]
assert rect_grid.remove("S").id == "S"
~~~

### Lưu ý về đối tượng lớn và truy vấn lớn

Nếu một AABB giao **hàng triệu ô**, việc tạo tập membership trong cells_for có thể chiếm nhiều bộ nhớ và làm chi phí cập nhật tăng rất mạnh. Giới hạn max_cells_per_box ngăn tình huống này trong ví dụ; trong hệ thống thật, cần cơ chế dành riêng cho **vật thể rất lớn** hoặc chỉ mục đa cấp.

Khử trùng bằng **ID**, không phải bằng tọa độ hoặc giá trị hộp. Hai hình khác ID nhưng cùng min/max vẫn là hai đối tượng hợp lệ. Vì dữ liệu ở đây **chính là AABB**, phép intersects là kiểm tra chính xác. Nếu các bản ghi đại diện cho đa giác/đường, cần thêm **predicate giao hình học gốc** sau bước lọc hộp.

**Chi phí đầu ra ổn định:** Hàm window của RectangleSpatialGrid cũng **sắp kết quả theo ID**, nên phải cộng thêm \(O(k\log k)\) ngoài thời gian tìm ứng viên và refine nếu cần thứ tự này.

### Kiểm tra cấu trúc và vòng đời

Mỗi move phải bảo đảm tập membership mới và bản ghi hình đồng bộ; nếu thao tác bị ngắt giữa chừng có thể xuất hiện bản ghi thiếu hoặc còn bucket cũ. Mã minh họa **không hỗ trợ transaction/đa luồng**. Một hệ thống thực cần cơ chế nhất quán khi nhiều truy vấn/cập nhật đồng thời, cũng như kiểm thử rằng ID có mặt ở **đúng tập ô** sau mọi thay đổi.

## 17. Phân tích độ phức tạp và bộ nhớ chính xác hơn

Không nên chỉ ghi “tìm kiếm \(O(1)\)” cho lưới không gian rồi kết luận nó luôn nhanh. Hãy tách các đại lượng:

- \(n\): số điểm hoặc đối tượng.
- \(m\): số ô **đang được lưu** trong spatial hash; với lưới đặc là tổng số ô đã cấp.
- \(C_Q\): số ô mà truy vấn phải **liệt kê hoặc kiểm tra**.
- \(V_Q\): số **lượt ID đọc từ các bucket** liên quan trước khử trùng/lọc.
- \(U_Q\): số **ID ứng viên duy nhất**; \(U_Q\le V_Q\).
- \(k\): số kết quả thật sự trả về; \(k\le U_Q\).
- \(M=\sum_{a=1}^n r_a\): tổng số membership trong các ô đối với những hình được lưu ở nhiều ô.

### Bảng chi phí

| Thao tác | Với tập điểm, hash bucket thông thường | Ghi chú |
| --- | --- | --- |
| Tính chỉ số ô của một điểm 2D | \(O(1)\) | Hai phép floor và số học, bỏ qua số học đa độ chính xác |
| Thêm một điểm theo ID mới | \(O(1)\) **kỳ vọng** | Hash map, set và cấp phát có thể có lần chậm |
| Xóa một điểm khi đã biết ID | \(O(1)\) **kỳ vọng** | Phải có ánh xạ ID → tọa độ/ô |
| Di chuyển một điểm | \(O(1)\) **kỳ vọng** | Với chỉ mục điểm; đổi giữa hai bucket |
| Truy vấn cửa sổ | \(O(C_Q+V_Q+k)\) **kỳ vọng**, chưa sắp kết quả | Phụ thuộc kích thước Q và phân bố |
| Truy vấn bán kính | \(O(C_Q+V_Q+k)\) **kỳ vọng**, chưa sắp kết quả | Lấy ứng viên từ hình vuông rồi lọc Euclid |
| Duyệt mọi điểm | \(O(n)\) | Chỉ mục không giúp giảm số đầu ra |
| Xây grid điểm từ đầu | \(O(n)\) **kỳ vọng** | Mỗi điểm được gán vào một ô |
| Bộ nhớ grid điểm thưa | \(O(n+m)\) | Bản ghi ID/tọa độ, tập ID, metadata |
| Bộ nhớ grid hình đăng ký nhiều ô | \(O(n+m+M)\) | \(M\) có thể lớn hơn \(n\) rất nhiều |
| Thêm/xóa hình qua \(r_a\) ô | \(O(r_a)\) **kỳ vọng** | Chưa tính kiểm tra hình học phức tạp |
| Truy vấn hình giao cửa sổ | \(O(C_Q+V_Q+U_Q\cdot T_{\mathrm{refine}}+k)\), chưa sắp kết quả | Khử trùng rồi kiểm tra hình gốc |

\(T_{\mathrm{refine}}\) là chi phí tối đa mỗi phép kiểm tra hình học thật, ví dụ kiểm tra giao của polygon có thể phức tạp hơn so sánh hai AABB.

Nếu API yêu cầu **sắp xếp \(k\) kết quả theo ID** như các ví dụ Python, cộng thêm \(O(k\log k)\). Nếu cần duyệt kết quả theo một thứ tự khác, hãy tính thêm chi phí bảo đảm thứ tự đó; chỉ mục lưới không tự lưu các điểm theo thứ tự khoảng cách.

**Nếu một truy vấn trả \(k\) kết quả, việc xuất đủ kết quả đã cần \(\Omega(k)\) thời gian.** Dù dùng chỉ mục tốt tới đâu, không thể trả hàng triệu đối tượng trong \(O(1)\) thời gian theo mô hình phải xuất từng bản ghi.

### Trường hợp xấu

1. **Mọi điểm nằm trong cùng một ô:** Một truy vấn chạm ô đó có thể cần kiểm tra \(n\) điểm, chi phí \(O(n)\).
2. **Truy vấn rất lớn nhưng dữ liệu thưa:** Cách liệt kê các ô theo chỉ số có thể mất \(\Theta(C_Q)\) ngay cả nếu \(k=0\). Nếu \(C_Q\) cực lớn, chi phí có thể lớn hơn \(n\).
3. **Rất nhiều hình trải nhiều ô:** Tổng membership \(M\) lớn, một truy vấn có thể đọc lặp cùng ID qua rất nhiều bucket trước khi dedup.
4. **Hash map bị va chạm hoặc dữ liệu đối kháng:** Chi phí \(O(1)\) là **kỳ vọng** theo giả thiết hàm băm/triển khai; không phải giới hạn trường hợp xấu tuyệt đối.
5. **Cập nhật nhiều đối tượng cùng lúc:** Cập nhật hàng triệu điểm trong một khung hình vẫn cần xử lý số lượng bản ghi đã đổi; spatial hashing không biến tổng công việc thành hằng số.

### Chi phí khi số chiều thay đổi

Trong \(d\) chiều, tính khóa ô và so sánh một điểm với hộp cần **\(O(d)\)** thao tác tọa độ. Nếu một cửa sổ cắt \(c_i\) ô trên trục \(i\), tổng số ô cần liệt kê là:

\[
\boxed{C_Q=\prod_{i=1}^{d}c_i.}
\]

Do vậy việc viết “\(O(1)\) cho mọi trường hợp” chỉ có thể áp dụng cho **số chiều cố định**, phép tìm bucket riêng lẻ và giả thiết hash phù hợp; không áp dụng cho cả truy vấn nhiều ô.

## 18. So sánh lưới với các chỉ mục không gian khác

| Cấu trúc | Ý tưởng tổ chức | Khi nào đáng cân nhắc | Hạn chế chính |
| --- | --- | --- | --- |
| **Uniform grid / spatial hash** | Chia miền thành ô đều, tra bucket qua chỉ số | Điểm 2D/3D động, phạm vi truy vấn tương đối nhỏ và cỡ ô phù hợp | Kích thước ô cố định, hotspot, hình lớn bị nhân bản |
| **Quadtree** | Phân chia vùng 2D thành bốn vùng con theo nhu cầu | Mật độ không đều, cần chia cục bộ | Cây sâu, điểm trùng, quản lý ô giao ranh giới |
| **Octree** | Phân chia khối 3D thành tám khối con | Dữ liệu thể tích/3D phân bố không đều | Metadata và độ sâu, số nút tăng |
| **k-d tree** | Chia điểm theo từng trục và ngưỡng | Tập điểm ít chiều, chủ yếu truy vấn tĩnh | Cập nhật khó hơn, NN tệ nhất vẫn có thể \(O(n)\) |
| **R-tree** | Nhóm đối tượng bởi các hộp bao, MBR | Polygon/đường/hộp kích thước khác nhau, nhiều window query | MBR các nhánh chồng lấp, split/reinsert phức tạp |
| **Quét tuyến tính** | Kiểm tra từng đối tượng | Tập rất nhỏ, truy vấn hiếm hoặc vector hóa hiệu quả | Chi phí \(O(n)\) mỗi truy vấn |

Lưới thường dễ hiện thực khi **đơn vị truy vấn tương đồng với kích thước ô**, và dễ thao tác với điểm di chuyển. Tuy nhiên, nếu dữ liệu đa dạng về kích thước hoặc truy vấn có nhiều độ lớn, **R-tree hoặc chỉ mục phân cấp** có thể đáng thử hơn.

### Có thể kết hợp nhiều cấp không?

Có. Một hệ thống có thể dùng **lưới thô** để xác định vùng lớn, sau đó mỗi ô lớn có **lưới nhỏ hoặc chỉ mục khác**. Phải bảo đảm:

1. Mỗi đối tượng được đăng ký vào nơi phù hợp với kích thước và phạm vi hình.
2. Truy vấn phải kết hợp đúng các cấp, không bỏ sót vật thể lớn.
3. ID chỉ được trả một lần nếu xuất hiện ở nhiều lớp.
4. Cập nhật/vô hiệu cache phải đi qua tất cả cấp liên quan.

Đây là một đánh đổi giữa **hiệu năng truy vấn**, **bộ nhớ** và **độ phức tạp triển khai**. Không nên tự thêm nhiều tầng khi một spatial hash đơn giản đã đáp ứng yêu cầu.

## 19. Checklist benchmark và kiểm thử tính đúng

Để chọn \(s\), kiểu bucket và cách lưu hình, nên đo **cả tốc độ lẫn tính chính xác**.

### Workload cần có

1. **Phân bố điểm đều**, **phân bố cụm**, các điểm nằm trên một đường, và nhiều điểm trùng tọa độ.
2. **Truy vấn nhỏ hơn một ô**, tương đương vài ô, và lớn hơn miền có dữ liệu.
3. **Truy vấn đúng trên biên ô**: x hoặc y bằng bội số của kích thước ô; cả tọa độ âm và dương.
4. **Bán kính bằng 0**, nhỏ hơn \(s\), bằng \(s\) và lớn hơn nhiều lần \(s\).
5. **Di chuyển điểm trong cùng ô** và **di chuyển xuyên biên**.
6. **Thêm/xóa hình cắt nhiều ô**, hình suy biến và hình quá lớn.
7. Truy vấn **không có kết quả**, có rất ít và có rất nhiều kết quả.
8. **Kết quả trùng ID do nhiều ô**; kiểm thử dedup và thứ tự sắp nếu API yêu cầu.

### Chỉ số hiệu năng

| Chỉ số | Ý nghĩa |
| --- | --- |
| \(C_Q\) | Có đang mất nhiều thời gian duyệt ô rỗng không? |
| \(V_Q\) | Bao nhiêu lượt ID phải đọc? |
| \(U_Q\) | Bao nhiêu ứng viên duy nhất trước refine? |
| \(k\) | Bao nhiêu kết quả thực sự? |
| \(V_Q/k\) khi \(k>0\) | Mức lọc dư/nhân bản membership tương đối |
| Số ô có dữ liệu \(m\) | Mật độ metadata |
| \(M\) | Chi phí lưu ID hình ở nhiều ô |
| p50, p95, p99 độ trễ | Khả năng có truy vấn bất thường |
| RAM ổn định và RAM đỉnh | Bộ nhớ bucket, hash, kết quả trung gian, rehash |
| Tốc độ insert/move/delete | Khả năng đáp ứng dữ liệu động |

### Đối chiếu với thuật toán tham chiếu

Để kiểm thử, viết một hàm **quét tuyến tính** không dựa trên grid:

~~~python
def reference_window(all_points, xmin, ymin, xmax, ymax):
    return sorted(
        (p.id for p in all_points
         if xmin <= p.x <= xmax and ymin <= p.y <= ymax)
    )


def reference_radius(all_points, cx, cy, radius):
    return sorted(
        (p.id for p in all_points
         if (p.x-cx)**2 + (p.y-cy)**2 <= radius**2)
    )
~~~

Với mỗi truy vấn thử, so **danh sách ID đã sắp xếp** của grid với hàm tham chiếu. Nếu khác nhau, đừng vội tối ưu: cần kiểm tra **floor khi âm, biên đóng/nửa mở, cập nhật bucket, dedup** và dữ liệu gốc trước.

**Kiểm tra các trường hợp ranh giới có giá trị hơn chỉ đo dữ liệu ngẫu nhiên.** Các bộ sinh ngẫu nhiên thường hiếm khi tạo đúng \(x=10\) hoặc \(x=-10\); trong khi đó là những vị trí dễ phát hiện lỗi nhất của quy tắc đánh chỉ số.

## 20. Các lỗi và hiểu lầm thường gặp

1. **“Lấy int(x/s) luôn bằng floor(x/s).”** Sai khi \(x/s<0\) trong ngôn ngữ có phép cắt về 0; ví dụ \(\operatorname{int}(-0{,}1)=0\) nhưng \(\lfloor-0{,}1\rfloor=-1\).
2. **“Điểm ở đúng biên có thể nằm trong cả hai ô mà không sao.”** Nếu yêu cầu mỗi điểm có một ô sở hữu, phải dùng quy tắc **nửa mở hoặc tie** nhất quán.
3. **“Ô nửa mở nghĩa là truy vấn cửa sổ cũng phải nửa mở.”** Không bắt buộc. Truy vấn có thể dùng biên đóng, nhưng phạm vi ô được duyệt phải bao đủ các điểm trên biên.
4. **“Cửa sổ \([0,10]\) chỉ cần xét ô \([0,10)\).”** Sai với biên đóng: điểm \(x=10\) nằm trong ô kế tiếp.
5. **“Gán điểm âm bằng phép làm tròn về 0 là đủ.”** Sai: sẽ đưa những điểm hơi âm vào ô 0 thay vì ô -1.
6. **“Tìm ứng viên trong bucket là đã tìm đúng kết quả.”** Sai: một bucket có thể chứa điểm ngoài cửa sổ hoặc ngoài bán kính tròn.
7. **“Hình tròn bán kính r chính là hình vuông cạnh 2r.”** Sai: hộp vuông chỉ là **AABB bao**; phải kiểm tra \(D_2^2\le r^2\).
8. **“NN chính xác chỉ cần tìm trong 3×3 ô rồi dừng.”** Sai khi không biết khoảng cách gần nhất hoặc các ô lân cận đều rỗng.
9. **“Hash map tạo ra một ID ô duy nhất không bao giờ va chạm.”** Sai: các khóa ô khác nhau có thể cho cùng giá trị hash; cấu trúc băm phải xử lý collision.
10. **“Hai bản ghi trùng tọa độ là một đối tượng.”** Sai nếu chúng có ID khác nhau.
11. **“Mọi hình chỉ cần lưu ở ô chứa tâm.”** Không đúng với thuật toán chỉ xét các ô chạm cửa sổ: một hình lớn có thể giao Q dù tâm nằm xa.
12. **“Đăng ký một hình ở nhiều ô không cần dedup.”** Sai: truy vấn có thể trả cùng một ID nhiều lần.
13. **“Đăng ký ở mọi ô hoàn toàn không tốn thêm bộ nhớ.”** Sai: bộ nhớ phụ thuộc \(M=\sum r_a\), có thể lớn hơn số hình.
14. **“Di chuyển điểm chỉ cần sửa tọa độ trong records.”** Sai nếu nó vượt biên ô; cần xóa membership cũ và thêm membership mới.
15. **“Sau khi xóa ID, giữ lại bucket rỗng là vô hại trong mọi trường hợp.”** Với grid thưa không giới hạn, bucket rỗng tích lũy có thể làm tăng metadata; nên có chính sách dọn.
16. **“Ô càng nhỏ thì truy vấn luôn càng nhanh.”** Sai: số ô phải tra và số membership hình có thể tăng rất lớn.
17. **“Ô càng to thì truy vấn luôn càng nhanh.”** Sai: nhiều ứng viên không liên quan bị gom chung, khiến refine đắt.
18. **“Với phân bố đều, mọi ô thật sẽ có đúng \(\rho s^2\) điểm.”** Đây chỉ là **kỳ vọng/xấp xỉ trung bình**; số điểm thực ở từng ô có thể lệch lớn.
19. **“Nếu hash map không lưu ô rỗng thì truy vấn qua triệu ô trống chỉ mất O(1).”** Sai khi thuật toán vẫn **liệt kê từng ô** trong phạm vi truy vấn.
20. **“Lưới 2D chạy tốt thì lưới 100D cũng vậy.”** Sai: số tổ hợp ô có thể tăng theo tích trên số chiều.
21. **“Kinh độ/vĩ độ theo độ có thể thay trực tiếp vào công thức bán kính mét.”** Sai: cần metric, CRS và xử lý đường đổi ngày.
22. **“Dùng epsilon tùy ý trước floor luôn sửa được lỗi biên.”** Sai: có thể đổi ý nghĩa sở hữu ô và gây không nhất quán giữa insert/query.
23. **“Cần lập chỉ mục cả triệu điểm mới đáng dùng bất kỳ grid nào.”** Không có ngưỡng chung: với vài trăm điểm, quét tuyến tính có thể đơn giản và nhanh hơn.
24. **“Sau khi đổi kích thước ô, có thể giữ nguyên các khóa bucket cũ.”** Sai: hàm cell phụ thuộc \(s\); phải **phân phối lại mọi bản ghi** theo kích thước mới.
25. **“Có thể đổi gốc lưới mà không thay index.”** Sai: khóa ô phụ thuộc gốc \(o\), vì thế cần reindex hoặc thiết kế phép đổi tọa độ tương ứng.
26. **“Đối tượng AABB có diện tích 0 là đối tượng rỗng.”** Sai theo biên đóng: nó có thể là điểm hoặc đoạn thẳng và vẫn giao các hộp khác.
27. **“Trả \(k\) điểm có thể hoàn thành O(1) dù k rất lớn.”** Sai: xuất đủ \(k\) điểm cần tối thiểu \(\Omega(k)\) thời gian.
28. **“Cập nhật cấu trúc băm hoàn tất thì mọi truy vấn song song đều đúng.”** Không tự động; cần bảo đảm nhất quán giữa tọa độ, bản ghi, buckets và phiên bản chỉ mục.

## 21. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Tính chỉ số ô cho tọa độ dương

Lưới có gốc \((0,0)\), ô vuông cạnh \(s=5\). Tính ô của \(P=(12,8)\), \(Q=(5,5)\) và \(R=(4.999,0)\).

**Lời giải:**

\[
\operatorname{cell}(12,8)=
(\lfloor12/5\rfloor,\lfloor8/5\rfloor)=(2,1).
\]

Tương tự \(\operatorname{cell}(5,5)=(1,1)\) vì biên trái **thuộc ô mới**; \(\operatorname{cell}(4.999,0)=(0,0)\).

### Câu 2. Floor khi tọa độ âm

Lưới \(s=10\), gốc \((0,0)\). Tính ô của \((-0.5,2)\), \((-10,0)\) và \((-10.1,-0.1)\).

**Lời giải:**

- \((-0.5,2)\to(-1,0)\).
- \((-10,0)\to(-1,0)\).
- \((-10.1,-0.1)\to(-2,-1)\).

Phải dùng **floor**, không dùng phép ép kiểu số thực thành số nguyên theo hướng về 0.

### Câu 3. Gốc lưới khác 0

Cho \(o=(100,-50)\), \(s_x=20\), \(s_y=10\). Điểm \(P=(145,-35)\) thuộc ô nào?

**Lời giải:**

\[
i=\left\lfloor\frac{145-100}{20}\right\rfloor
=\lfloor2{,}25\rfloor=2,
\]
\[
j=\left\lfloor\frac{-35-(-50)}{10}\right\rfloor
=\lfloor1{,}5\rfloor=1.
\]

Vậy \(P\) thuộc ô **\((2,1)\)**.

### Câu 4. Khôi phục biên ô

Một lưới có \(o=(0,0)\), \(s=10\). Ô \((-2,3)\) đại diện vùng nào? Tâm ô ở đâu?

**Lời giải:**

\[
C_{-2,3}=[-20,-10)\times[30,40).
\]

Tâm ô là \(\boxed{(-15,35)}\).

### Câu 5. Phạm vi ô của cửa sổ đóng

Với lưới cạnh \(10\), \(o=(0,0)\), truy vấn \(Q=[0,20]\times[5,15]\) dùng biên đóng. Cần duyệt những cột/hàng nào, tổng bao nhiêu ô?

**Lời giải:**

\[
i_{\min}=\lfloor0/10\rfloor=0,\quad
i_{\max}=\lfloor20/10\rfloor=2,
\]
\[
j_{\min}=\lfloor5/10\rfloor=0,\quad
j_{\max}=\lfloor15/10\rfloor=1.
\]

Cần duyệt **3 cột** \(0,1,2\) và **2 hàng** \(0,1\): tổng \(3\cdot2=\boxed{6}\) ô. Cột 2 bảo đảm điểm đúng tại \(x=20\) không bị bỏ sót.

### Câu 6. Truy vấn điểm nằm đúng biên

Ba điểm \(A=(9,9)\), \(B=(10,9)\), \(C=(10,10)\); lưới cạnh 10. Truy vấn Q là \([0,10]\times[0,10]\) với biên đóng. Kết quả đúng là gì?

**Lời giải:** Cả **A, B, C** đều thuộc Q. Nhưng A ở ô \((0,0)\), B ở \((1,0)\), C ở \((1,1)\). Chỉ đọc ô \((0,0)\) sẽ bỏ sót hai điểm đúng biên.

### Câu 7. Phân biệt ô ứng viên với kết quả thật

Lưới cạnh 10, truy vấn \(Q=[2,3]\times[2,3]\). Bucket ô \((0,0)\) chứa A=(2,2), B=(9,9), C=(3,2). Những điểm nào được trả?

**Lời giải:** Cả ba được lấy làm **ứng viên** từ cùng một bucket, nhưng predicate point-in-Q chỉ nhận **A và C**. B không thuộc Q dù ở cùng ô với A và C.

### Câu 8. Lọc bán kính

Cho tâm \((0,0)\), bán kính \(r=5\), các điểm A=(3,4), B=(4,4), C=(-5,0), D=(0,6). Điểm nào thuộc hình tròn đóng?

**Lời giải:**

- A có bình phương khoảng cách \(3^2+4^2=25\), **được nhận**.
- B có \(4^2+4^2=32\), **bị loại**.
- C có \((-5)^2+0^2=25\), **được nhận**.
- D có \(6^2=36\), **bị loại**.

Kết quả là **A và C**; dấu bằng ở bán kính được chấp nhận.

### Câu 9. Số ô trong phạm vi radius

Với \(s=10\), tâm \(q=(12,12)\), bán kính \(r=8\), hộp ứng viên là gì và cắt bao nhiêu ô?

**Lời giải:**

\[
B_r=[12-8,12+8]\times[12-8,12+8]
=[4,20]\times[4,20].
\]

Các chỉ số mỗi trục từ \(\lfloor4/10\rfloor=0\) tới \(\lfloor20/10\rfloor=2\), tức **3×3 = 9 ô** theo phạm vi biên đóng. Sau đó vẫn phải kiểm tra khoảng cách thật.

### Câu 10. Cập nhật điểm qua ranh giới

Một ID đang ở \((9.9,1)\), lưới cạnh 10. Điểm chuyển đến \((10.1,1)\). Phải cập nhật những gì?

**Lời giải:** Ô cũ \((0,0)\), ô mới \((1,0)\). Cần **xóa ID khỏi bucket (0,0)**, **thêm vào bucket (1,0)** và cập nhật tọa độ record. Nếu bucket cũ rỗng, có thể xóa khóa khỏi spatial hash.

### Câu 11. Chuyển trong cùng ô

Điểm \((2,2)\) chuyển tới \((8,9)\), lưới cạnh 10, gốc 0. Có cần thay bucket không?

**Lời giải:** Cả hai thuộc ô \((0,0)\). Chỉ cần cập nhật tọa độ gốc; **membership không đổi**. Tuy nhiên, nếu đang cache thêm thông tin khác theo tọa độ thật, cache ấy vẫn phải được xét lại.

### Câu 12. Hình chiếm nhiều ô

Cho hình \(B=[8,22]\times[4,15]\), lưới cạnh 10. Hình phải đăng ký vào bao nhiêu ô nếu dùng quy tắc min/max đóng?

**Lời giải:** Cột \(i=0,1,2\), hàng \(j=0,1\). Tổng \(3\cdot2=\boxed{6}\) ô. Nếu một truy vấn đọc cả sáu bucket, phải **dedup ID** để B chỉ được trả một lần.

### Câu 13. Vì sao chỉ lưu ở ô tâm có thể sai?

Một vật thể có AABB \(B=[0,100]\times[0,100]\), tâm ở \((50,50)\), được lưu duy nhất trong ô chứa tâm. Truy vấn nhỏ \(Q=[0,1]\times[0,1]\) chỉ đọc các ô giao Q. Có thể bỏ sót B không?

**Lời giải:** **Có.** Hình B giao Q, nhưng ô chứa tâm \((50,50)\) không nhất thiết nằm trong những ô Q chạm tới. Muốn dùng một ô đại diện, phải có cơ chế xét **kích thước vật thể** hoặc chỉ mục phụ để không bỏ sót.

### Câu 14. Đếm membership

Có 100 hình; 80 hình đăng ký vào đúng 1 ô và 20 hình đăng ký vào đúng 6 ô. Tổng số membership \(M\) bằng bao nhiêu?

**Lời giải:**

\[
M=80\cdot1+20\cdot6
=80+120=\boxed{200}.
\]

Số đối tượng chỉ có \(n=100\), nhưng các bucket cần giữ **200 lần tham chiếu ID** trước khi tính metadata.

### Câu 15. Ước lượng kích thước ô theo mật độ

Một miền rộng 200.000 m² chứa 20.000 điểm phân bố gần đều. Muốn trung bình khoảng 25 điểm/ô vuông, nên thử cạnh ô khoảng bao nhiêu?

**Lời giải:** Mật độ \(\rho=20\,000/200\,000=0{,}1\) điểm/m². Do \(\lambda\approx\rho s^2\):

\[
s\approx\sqrt{\frac{25}{0{,}1}}
=\sqrt{250}\approx\boxed{15{,}81\text{ m}}.
\]

Đó chỉ là **giá trị thử nghiệm ban đầu**, không bảo đảm tối ưu khi điểm tụ thành cụm.

### Câu 16. Chi phí khi ô quá nhỏ

Một cửa sổ 100 m × 100 m được tra trên lưới cạnh 1 m và lưới cạnh 10 m. Bỏ qua phần làm tròn/biên, số ô phải xét chênh nhau bao nhiêu lần?

**Lời giải:** Lưới cạnh 1 m cần khoảng \(100\cdot100=10\,000\) ô; lưới cạnh 10 m cần khoảng \(10\cdot10=100\) ô. Như vậy chênh lệch **100 lần về số ô**, nhưng không đủ kết luận lưới cạnh 10 m nhanh hơn vì một ô lớn có thể chứa **nhiều điểm ứng viên hơn**.

### Câu 17. Lời nguyền số chiều

Một truy vấn cắt 3 ô trên mỗi trục của lưới. Cần xét bao nhiêu ô trong 2D, 3D và 6D?

**Lời giải:**

\[
3^2=9,\qquad3^3=27,\qquad3^6=729.
\]

Số tổ hợp ô tăng theo hàm mũ số chiều khi số ô trên mỗi trục giữ nguyên.

### Câu 18. Khi nào quét tuyến tính tốt hơn?

Ứng dụng có 200 điểm, mỗi phút chỉ chạy một truy vấn. Có nhất thiết phải dùng spatial hash không?

**Lời giải:** **Không.** Quét 200 điểm mỗi phút rất đơn giản, dễ kiểm thử và có thể nhanh hơn tổng chi phí xây/duy trì chỉ mục. Hãy đo workload trước khi chọn một cấu trúc phức tạp hơn.

### Câu 19. Vì sao phải cập nhật sau đổi kích thước ô?

Grid ban đầu có \(s=10\), ID A ở \((15,5)\) thuộc ô \((1,0)\). Đổi kích thước ô thành \(s=5\) nhưng không reindex. Điều gì xảy ra?

**Lời giải:** Theo kích thước mới, A phải thuộc ô \((3,1)\). Nếu giữ ở bucket \((1,0)\), một truy vấn nhỏ quanh \((15,5)\) sẽ đọc ô \((3,1)\) và có thể **bỏ sót A**. Cần phân phối lại mọi bản ghi khi thay đổi \(s\).

### Câu 20. Phân biệt lỗi thiếu kết quả và ứng viên dư

Một phép window dùng grid trả các ứng viên A, B, C. Sau lọc hình học, chỉ A, C thật sự thuộc Q. Trường hợp này có sai không? Ngược lại, nếu B thực sự thuộc Q nhưng không được lấy từ bucket thì sao?

**Lời giải:** **Ứng viên dư** là bình thường nếu bước refine loại được B. Nhưng **bỏ sót một kết quả thật** là lỗi nghiêm trọng: chỉ mục vi phạm bất biến đưa mọi đối tượng liên quan vào ít nhất một ô được truy vấn. Thiết kế broad-phase phải ưu tiên **không có false negative**.

## 22. Tổng kết và quy trình chọn lưới

Lưới không gian chia miền thành các ô, giúp tìm **ứng viên theo vị trí** thay vì quét toàn bộ dữ liệu. Với gốc \(o=(o_x,o_y)\) và kích thước ô \(s_x,s_y>0\):

\[
\boxed{
\operatorname{cell}(x,y)=
\left(
\left\lfloor\frac{x-o_x}{s_x}\right\rfloor,
\left\lfloor\frac{y-o_y}{s_y}\right\rfloor
\right).}
\]

**Quy tắc ô nửa mở** giúp mỗi điểm thuộc đúng một ô, kể cả tọa độ âm và điểm đúng ranh giới. **Truy vấn cửa sổ biên đóng** phải xét các ô từ floor(cận dưới) tới floor(cận trên) trên từng trục, rồi kiểm tra tọa độ thật. **Truy vấn bán kính** có thể dùng hộp ứng viên trước và lọc bằng bình phương khoảng cách Euclid sau.

**Lưới đặc** phù hợp khi miền hữu hạn và đủ dày; **spatial hash** chỉ tạo bucket có dữ liệu, phù hợp khi miền rộng/thưa. Với **điểm**, một ID thường nằm trong đúng một ô; với **hình có kích thước**, có thể cần nhiều ô, dẫn tới bộ nhớ \(O(n+m+M)\) và yêu cầu **khử trùng ID**.

Độ phức tạp một truy vấn chịu ảnh hưởng đồng thời bởi **số ô phải duyệt \(C_Q\)**, **số lượt ứng viên \(V_Q\)** và **số kết quả \(k\)**. Kích thước ô quá nhỏ gây nhiều lượt tra ô; ô quá lớn gây nhiều ứng viên dư. Không có một kích thước tối ưu cho mọi dữ liệu, mọi bán kính và mọi tỷ lệ cập nhật.

Khi áp dụng vào dự án, nên làm theo thứ tự: **thống nhất CRS/đơn vị → xác định biên ô và truy vấn → chọn cách lưu điểm hay hình → xác định kích thước ô thử nghiệm → bảo đảm cập nhật bucket đúng → đối chiếu với quét tuyến tính → benchmark cả dữ liệu đều, dữ liệu cụm và trường hợp biên**. Một lưới dễ triển khai chỉ thực sự hữu ích khi nó vừa **giảm chi phí tìm kiếm** vừa **không bỏ sót đối tượng hợp lệ**.
