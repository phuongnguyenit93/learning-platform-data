# Mô hình hóa điều kiện một–một, giới hạn năng lực và cặp bị cấm

Trong **ghép cặp và phân công**, thuật toán chỉ đúng khi **mô hình ràng buộc đúng**. Cụm “một người một việc” có thể là *nhiều nhất một* hoặc *bắt buộc đúng một*; “năng lực 3” có thể nghĩa *làm tối đa 3 việc* chứ không phải *phải làm đủ 3*; một cặp người–việc có thể **được phép**, **bị cấm**, hoặc **không có trong danh sách ứng viên**. Nếu đánh đồng các trạng thái ấy, chương trình rất dễ trả một kết quả có số lượng lớn nhưng vi phạm quy tắc thực tế.

Bài học thuộc nhóm **Ghép cặp và phân công** của Computer Science Algorithms, trình bày từ đặc tả bằng biến nhị phân đến đồ thị hai phía và mạng luồng. Trọng tâm là ba loại ràng buộc **một–một**, **giới hạn năng lực** và **cặp bị cấm**; cách kiểm tra tính khả thi khi cần đủ suất, chứng minh đúng và chứng chỉ lát cắt cực tiểu, cách phân biệt với bài có chi phí/quota tối thiểu, cùng chương trình **Java 17+** dùng Dinic với bộ kiểm thử độc lập.

## 1. Xác định tập người, tập việc và một “lượt phân công”

Giả sử có tập người/nguồn lực `W={W0,…,W(L−1)}` và tập việc/đối tượng `T={T0,…,T(R−1)}`. Hai tập là **hai phía riêng biệt của đồ thị**; ID 0 bên W không phải cùng đỉnh với ID 0 bên T.

Một **lượt phân công** là việc chọn một cặp `(Wi,Tj)`. Trong mô hình chính, **mỗi cặp phân biệt chỉ được chọn tối đa một lần**. Điều đó không nhất thiết có nghĩa một người chỉ được làm một việc: nếu năng lực của W0 là 2, có thể chọn `(W0,T0)` và `(W0,T1)`, nhưng không chọn `(W0,T0)` hai lần.

Đầu tiên cần trả lời rõ:

- **Đơn vị đếm:** cặp người–việc, buổi làm, suất dịch vụ, giờ công hay đơn vị hàng hóa? Nếu cần nhiều giờ từ cùng cặp, biến nhị phân có thể không đủ.
- **Nguồn lực:** người i được nhận tối đa mấy lượt? Việc j được nhận tối đa mấy người?
- **Tính tương thích:** kỹ năng/điều kiện nào làm cặp đủ điều kiện?
- **Quy tắc cấm:** cặp nào tuyệt đối không được chọn dù đủ kỹ năng?
- **Mục tiêu:** tối đa số lượt, phải hoàn thành mọi lượt bắt buộc, tối thiểu chi phí hay tối đa điểm phù hợp?

Trong bài, khi chưa nói khác, mục tiêu là **tối đa số cặp hợp lệ** và năng lực là **giới hạn trên**.

## 2. Biến quyết định và ràng buộc toán học

Đặt:

`x[i][j]∈{0,1}`

với x=1 khi chọn cặp Wi–Tj; x=0 khi không chọn.

Gọi:

- `a[i]≥0`: số việc tối đa của người i.
- `b[j]≥0`: số người tối đa cho việc j.
- `compatible(i,j)`: cặp xuất hiện trong danh sách ứng viên.
- `forbidden(i,j)`: cặp thuộc danh sách cấm.
- `allowed(i,j)=compatible(i,j) AND NOT forbidden(i,j)`.

Ràng buộc chính:

`Σ_j x[i][j] ≤ a[i]` cho mọi người i.

`Σ_i x[i][j] ≤ b[j]` cho mọi việc j.

`x[i][j] ≤ allowed(i,j)` cho mọi i,j.

`x[i][j]∈{0,1}`.

Hàm mục tiêu:

`maximize F=Σ_i Σ_j x[i][j]`.

Chỉ ba nhóm ràng buộc này đã biểu diễn đúng **phân công hai phía với năng lực từng đỉnh và từng cặp tối đa một lần**. Nó thường được gọi là dạng **b-matching hai phía**. Khi mọi a[i]=b[j]=1, ta nhận được bài **matching một–một** quen thuộc.

### Giới hạn trên và nghĩa vụ chính xác khác nhau thế nào?

Nếu một người **được phép nhận tối đa** hai việc, điều kiện là `Σ_j x[i][j]≤2`. Người ấy nhận 0 hoặc 1 việc vẫn hợp lệ.

Nếu bắt buộc nhận **đúng** hai việc, điều kiện phải là `Σ_j x[i][j]=2`. Nếu chỉ yêu cầu ít nhất một việc nhưng không quá hai: `1≤Σ_j x[i][j]≤2`.

Tương tự, “mỗi việc **phải** có một người” là `Σ_i x[i][j]=1`, không phải chỉ `≤1`. Viết rõ từng dấu bằng/bất đẳng thức trước khi chọn thuật toán.

**Sai lầm nguy hiểm:** chạy thuật toán tối đa số cặp rồi mặc định kết quả thỏa mọi yêu cầu “chính xác một” hoặc quota tối thiểu. Kết quả tối đa có thể vẫn **thiếu** người hoặc việc nếu dữ liệu không khả thi.

## 3. Một–một, bão hòa một phía và ghép hoàn hảo

**Matching một–một**: mọi người và việc có năng lực tối đa 1. Mỗi đỉnh thuộc nhiều nhất một cạnh đã chọn.

- Nếu ghép được `k` cặp, có `2k` đỉnh được ghép.
- Kích thước matching tối đa là `min(L,R)`.
- **Matching bão hòa W**: mọi người có đúng một việc; số cặp bằng L.
- **Matching bão hòa T**: mọi việc có đúng một người; số cặp bằng R.
- **Perfect matching**: **mọi đỉnh của cả hai phía** được ghép; cần L=R và số cặp bằng L=R.

Ví dụ L=3, R=5, chọn được 3 cặp khác người và khác việc: đó là matching bão hòa W, nhưng **không phải perfect matching** vì vẫn có hai đỉnh phía T chưa có cặp.

Nếu L=R=3 nhưng chỉ ghép được 2 cặp vì một nhóm người cùng tranh một việc, đáp án 2 là **maximum matching** theo số cặp, song **không hoàn hảo**. “Tối ưu” không đồng nghĩa “đầy đủ”.

### Đường tăng cần thiết khi các lựa chọn ban đầu không tốt

Xét W0,W1,W2 và T0,T1,T2, năng lực đều 1, với các cạnh:

~~~text
W0-T0, W0-T1
W1-T0
W2-T1, W2-T2
~~~

Greedy có thể chọn W0–T0 và W2–T1 (2 cặp). Nếu không cho sửa cặp đã chọn, W1 và T2 vẫn tự do nhưng không có cạnh trực tiếp.

Một **đường tăng xen kẽ** cho phép đổi từ:

`{W0–T0,W2–T1}`

thành:

`{W0–T1,W1–T0,W2–T2}`.

Đáp án có 3 cặp, là một **perfect matching**. Vì thế việc tồn tại năng lực và cặp tương thích không có nghĩa thuật toán chọn tham lam “thấy trước lấy trước” tìm được maximum. Mạng luồng với **cung ngược dư** là một cách tổng quát để thực hiện đổi cặp an toàn.

## 4. Ba tầng năng lực phải tách biệt

Với người Wi năng lực `a[i]`, việc Tj năng lực `b[j]`, và một cặp hiệu lực được dùng tối đa một lần, ta có ba loại giới hạn khác nhau.

| Giới hạn | Diễn giải | Cung trong mạng luồng |
| --- | --- | --- |
| `a[i]` | Người i nhận tổng cộng không quá a[i] việc | nguồn → Wi |
| `b[j]` | Việc j nhận tổng cộng không quá b[j] người | Tj → đích |
| `1` trên cặp | Wi–Tj chỉ được chọn một lần | Wi → Tj khi được phép |

**Phản ví dụ cực quan trọng:** chỉ có một người W0 năng lực 3, một việc T0 năng lực 5, và chỉ có đúng cặp W0–T0. Số lượt tối đa trong mô hình **cặp nhị phân** là **1**, chứ không phải min(3,5)=3.

Nếu đề thực sự cho phép W0 làm ba **phiên độc lập** của cùng việc T0, hãy mô hình ba phiên khác nhau hoặc cho cung cặp capacity 3 rồi trả **lượng** được phân cho cặp, thay vì một biến x∈{0,1}. Hai mô hình phục vụ **hai bài toán khác nhau**.

### Cận trên dễ tính nhưng chưa đủ

Gọi `P` là số **cặp hiệu lực phân biệt**. Mọi nghiệm hợp lệ đều thỏa:

`F ≤ min(Σ_i a[i], Σ_j b[j], P)`.

Cận này có thể rất lỏng do năng lực tập trung vào những người và việc **không tương thích với nhau**. Không được lấy ba số rồi chọn giá trị nhỏ nhất làm đáp án mà bỏ qua hình dạng đồ thị.

## 5. Cặp bị cấm là ràng buộc cứng

Một cặp có thể bị cấm do giấy phép, kỹ năng không đạt chuẩn, xung đột lợi ích, chính sách bảo mật, lịch trực, điều kiện an toàn hoặc quy định riêng.

**Quy tắc chuẩn trong bài:**

`effectiveAllowed(i,j)=candidate(i,j) AND NOT forbidden(i,j)`.

Chỉ các cặp có `effectiveAllowed=true` mới được tạo thành cạnh phân công.

Với đầu vào có:

~~~text
Candidate: W0-T0, W0-T1, W1-T0, W1-T1
Forbidden: W0-T0, W1-T1

Effective: W0-T1, W1-T0
~~~

Kết quả hợp lệ có thể gồm 2 cặp W0–T1 và W1–T0. Không được chọn W0–T0 hay W1–T1, dù các cặp này xuất hiện trong candidate.

### Không dùng “giá phạt cực lớn” thay lệnh cấm

Nếu cặp Wi–Tj **bị cấm tuyệt đối**, đặt một chi phí phạt lớn nhưng hữu hạn **không bảo đảm nó không bao giờ được chọn**. Khi yêu cầu đủ việc mà không có phương án tốt hơn, thuật toán min-cost vẫn có thể chọn cặp bị cấm để thỏa điều kiện khác.

Do đó:

- **Cấm cứng:** `x[i][j]=0` hoặc loại cạnh khỏi mạng.
- **Ưu tiên mềm:** cặp vẫn hợp lệ nhưng nhận một **chi phí/điểm phạt**; khi ấy phải dùng thuật toán tối ưu chi phí/điểm tương ứng.

**Đừng thay đổi hard constraint thành soft constraint chỉ để hệ thống luôn in được một lời giải.** Với dữ liệu bất khả thi, kết quả đúng là **báo bất khả thi**.

### Chuẩn hóa và xử lý dòng trùng

Trong Java, danh sách candidate và blacklist đều được chuẩn hóa bằng ma trận Boolean. Ba dòng cùng mô tả W0–T0 **không** tạo ba cặp riêng biệt. Blacklist có **quyền ưu tiên**: nếu một cặp vừa có trong candidate vừa bị cấm thì cặp ấy bị loại.

Quy ước **mặc định từ chối**: cặp không có trong candidate không được phép, ngay cả khi nó không có trong blacklist. Nếu nguồn dữ liệu thực tế dùng “mặc định cho phép trừ danh sách cấm”, phải chuyển đầu vào sang danh sách effective đúng quy định trước khi giải.

## 6. Chuyển bài toán thành mạng luồng

Tạo một mạng có hướng với bốn lớp:

~~~text
            a[i]            1                 b[j]
source s ----------> Wi ----------> Tj ----------------> sink t

Chỉ tạo Wi -> Tj nếu cặp (Wi,Tj) được phép hiệu lực.
~~~

Chi tiết:

1. Tạo nguồn s và đích t riêng.
2. Với mỗi người Wi, thêm cung `s→Wi` capacity `a[i]`.
3. Với mỗi việc Tj, thêm cung `Tj→t` capacity `b[j]`.
4. Với mỗi cặp effectiveAllowed(i,j), thêm cung `Wi→Tj` capacity **1**.
5. Tìm **luồng cực đại** s→t.
6. Chọn cặp Wi–Tj nếu luồng trên cung ấy bằng **1**.

### Vì sao mô hình đúng?

Giả sử có một phương án chọn k cặp hợp lệ. Gửi 1 đơn vị theo đường `s→Wi→Tj→t` với mỗi cặp. Tổng từ một người không vượt a[i]; tổng vào một việc không vượt b[j]; mỗi cặp chỉ dùng một lần. Ta tạo được **luồng khả thi giá trị k**.

Ngược lại, mọi dung lượng đều nguyên, nên tồn tại **luồng cực đại nguyên**. Trên cung cặp capacity1, luồng là 0 hoặc 1. Chọn các cung cặp có luồng1 tạo ra đúng F cặp, không vượt quota mỗi phía và không chứa cặp cấm, do các cung cấm không tồn tại.

Vì hai phép chuyển đổi bảo toàn số lượt:

`maximumValidAssignments = maxFlow(s,t)`.

Tính đúng này phụ thuộc **đơn vị luồng là một cặp**, **cung cặp cap1**, và tất cả ràng buộc cần thiết đã được biểu diễn. Nếu sau đó có thêm điều kiện thời gian/chi phí/quota tối thiểu, phải xét lại mô hình.

### Cung ngược dư không phải một cặp mới

Khi thuật toán đẩy luồng qua Wi→Tj, mạng dư có cung ngược Tj→Wi cho phép **hủy** phân công ấy để sửa thành phương án tốt hơn. Cung ngược dư chỉ biểu thị quyền **đổi quyết định đã đưa ra**, không phải cho phép phân công một cặp ngược chiều hay một cặp bị cấm.

Đừng tự xóa các cung ngược dư vì sợ “đi ngược”; nếu làm vậy, thuật toán có thể kẹt ở kết quả tham lam dưới tối ưu.

## 7. Hai ví dụ có giới hạn và cặp cấm

### Ví dụ A — năng lực hai phía khác 1

~~~text
Người:
W0 cap2, W1 cap1, W2 cap1

Việc:
T0 cap1, T1 cap2, T2 cap1

Cặp được phép:
W0-T0, W0-T1
W1-T1, W1-T2
W2-T0, W2-T2
~~~

Phương án hợp lệ:

`{W0–T0, W0–T1, W1–T1, W2–T2}`.

Ta có bốn cặp. W0 làm hai việc; T1 nhận hai người; các cặp đều phân biệt. Tổng năng lực phía người là 4 và phía việc cũng là 4, nên phương án đã đạt cận trên toàn cục: **tối ưu 4**.

### Ví dụ B — năng lực tổng đủ nhưng cấu trúc cặp thiếu

~~~text
Người: W0 cap2, W1 cap1, W2 cap1
Việc:  T0 cap3, T1 cap1
Cặp được phép: W0-T0, W1-T0, W2-T0
~~~

Tổng năng lực cả hai phía đều bằng 4. Nhưng chỉ có **ba cặp hiệu lực phân biệt** và T1 không nối với ai. Có thể chọn ba cặp cùng kết thúc ở T0, vì T0 cap3; không có cách giao lượt thứ tư. Do đó **F*=3**, không phải 4.

Người W0 còn một suất, T1 còn một suất, song không có cặp nối chúng. **Năng lực dư không sinh ra tính tương thích.**

## 8. Kiểm tra “phải phân hết” và các loại quota

### Chỉ giới hạn trên

Nếu a[i], b[j] là năng lực **tối đa**, một phương án dùng ít hơn vẫn hợp lệ. Trong trường hợp này, F* là số cặp nhiều nhất có thể chọn.

### Mọi người phải được giao đủ a[i] lượt

Gọi `A=Σ_i a[i]`. Vì không người nào được vượt a[i], một nghiệm có F=A tự động khiến **mọi người đạt đúng quota a[i]**. Do đó:

- Nếu **maxflow F*=A**, điều kiện “mọi người làm đủ quota” khả thi.
- Nếu **F*<A**, điều kiện ấy **bất khả thi** với candidate, blacklist và năng lực việc đã cho.

Ví dụ một người cap3 chỉ có một cặp cap1: F*=1 nên không thể thỏa yêu cầu giao **đúng 3 lượt**, dù vẫn có một phân công hợp lệ khi chỉ xét giới hạn trên.

### Mọi việc cũng có quota tối thiểu

Nếu mỗi việc Tj phải có ít nhất d[j] người, chỉ kiểm tra số cặp lớn nhất chưa đủ. Thuật toán có thể dồn người vào những việc dễ ghép và bỏ một việc có ràng buộc tối thiểu.

Có thể chuyển bài thành **luồng có cận dưới**: mỗi cung có ℓ≤flow≤u, lấy phần ℓ làm luồng nền, giảm capacity còn u−ℓ, điều chỉnh cân bằng ở đỉnh và tìm **circulation khả thi** qua siêu nguồn/siêu đích. Với bài s→t, kỹ thuật thường thêm cung t→s để kiểm tra khả thi rồi tối ưu tiếp. **Chương trình Java ở mục 12 chỉ hỗ trợ giới hạn trên**, không âm thầm tuyên bố thỏa lower bounds.

### Nếu chỉ cần chính xác K cặp

Khi **chỉ có giới hạn trên** và không có ràng buộc bắt buộc khác, tồn tại phương án chọn chính xác K cặp nếu và chỉ nếu **F*≥K**. Ta có thể lấy K cặp bất kỳ từ một nghiệm F* cặp: loại bớt chỉ giảm tải, không tạo vi phạm upper-bound.

Nhưng nếu còn yêu cầu mỗi nhóm/công việc phải có một mức phân công tối thiểu, **không thể xóa tùy ý** cặp khỏi một nghiệm lớn hơn.

## 9. Điều kiện Hall mở rộng và lát cắt

### Hall trong trường hợp một–một

Khi a[i]=b[j]=1, một matching bão hòa mọi người tồn tại khi và chỉ khi, với **mọi tập con U của người**:

`|N(U)| ≥ |U|`.

N(U) là tập việc có cặp hiệu lực với ít nhất một người thuộc U. Tập việc được tính **sau khi loại những cặp bị cấm**.

Ví dụ W0 và W1 đều chỉ tương thích T0. Tập U={W0,W1} chỉ có một hàng xóm {T0}, nên **không thể giao đủ hai người**, dù từng người đều có ít nhất một lựa chọn.

### Năng lực >1 và cap1 theo cặp: Hall đơn giản chưa đủ

Công thức tùy tiện:

`Σ_{i∈U} a[i] ≤ Σ_{j∈N(U)} b[j]`

chỉ là một điều kiện cần, chưa chắc đủ nếu một người không được chọn cùng một việc nhiều lần. Với một người cap3, một việc cap5 nhưng một cặp cap1, bất đẳng thức 3≤5 thỏa, song chỉ có một lượt phân công.

Gọi `deg_U(j)` là **số người phân biệt thuộc U có cặp hiệu lực tới việc j**. Số lượt mà nhóm U có thể gửi vào Tj không vượt:

`min(b[j],deg_U(j))`.

Để dùng hết mọi quota người a[i] trong **đúng mô hình cap1 mỗi cặp**, điều kiện **cần và đủ** là:

`∀U⊆W: Σ_{i∈U}a[i] ≤ Σ_j min(b[j],deg_U(j))`.

Khi a[i]=b[j]=1, công thức trở về Hall vì mỗi việc đóng góp 1 nếu có ít nhất một hàng xóm ở U.

### Giải thích tính đủ bằng lát cắt cực tiểu

Trong mạng s→W→T→t, xét một lát cắt mà tập người U và tập việc H nằm phía nguồn. Dung lượng của nó là:

`cut(U,H)=Σ_{i∉U}a[i] + Σ_{j∉H}deg_U(j) + Σ_{j∈H}b[j]`.

Thành phần thứ nhất là các cung s→người nằm phía đích; thành phần thứ hai là các cung cặp từ U đến việc phía đích, mỗi cung cap1; thành phần thứ ba là cung việc→t của những việc nằm phía nguồn.

Với U cố định, ta chọn phía cho mỗi việc j để đóng góp nhỏ hơn trong `b[j]` và `deg_U(j)`. Suy ra:

`minCut = min_{U⊆W}[Σ_{i∉U}a[i]+Σ_j min(b[j],deg_U(j))]`.

Theo **định lý max-flow min-cut**, sử dụng hết A=Σa[i] suất phía người khả thi khi và chỉ khi mọi lát cắt có dung lượng ít nhất A. Biến đổi biểu thức trên cho đúng điều kiện Hall mở rộng.

**Phạm vi:** tính cần/đủ này chỉ nói về mạng hai phía với **capacity theo đỉnh**, **cặp hiệu lực cap1** và yêu cầu **bão hòa tất cả suất phía người**. Không áp dụng máy móc cho ràng buộc nhóm, thời gian, chi phí hay lower bounds tùy ý.

### Min cut là chứng chỉ giới hạn tối ưu

Khi Dinic kết thúc, lấy S là các đỉnh còn tới được từ nguồn qua cung **dư dương**. Mọi cung gốc băng từ S ra phần còn lại đều bão hòa; tổng dung lượng lát cắt bằng max flow. Nếu F* thấp hơn số suất bắt buộc, min cut giúp chứng minh không thuật toán nào có thể tạo thêm cặp **mà vẫn giữ nguyên ràng buộc**.

## 10. Dữ liệu thực tế, chi phí và các trường hợp không dùng trực tiếp max flow này

### Chi phí và độ phù hợp

Nếu một cặp hợp lệ mang chi phí hoặc điểm:

- Chỉ **tối đa số cặp**: bài toán ở đây.
- Tối đa số cặp **trước**, rồi chọn nghiệm có điểm tốt nhất: cần tối ưu phụ trong các nghiệm F* cặp, thường dùng **min-cost max-flow** với chi phí phù hợp.
- Tìm phân công hoàn chỉnh có chi phí nhỏ nhất khi mọi năng lực đều 1: có thể dùng bài **assignment/Hungarian**, với cặp cấm bị loại theo đúng quy tắc.
- Tối đa **tổng điểm** bất kể số cặp: không chắc cùng nghiệm với tối đa số cặp.

Max flow **không tự chọn người phù hợp nhất** nếu nhiều nghiệm cùng số cặp. Để có nghiệm tái lập, code duyệt ID theo thứ tự tăng; đó là quy tắc thực thi, **không phải tiêu chí tối ưu công bằng hay chi phí**.

### Ràng buộc tương tác nhiều biến

Các điều kiện như “W0 và W1 không được cùng làm T0”, “phải chọn ít nhất một người mỗi phòng ban”, “W0 không thể nhận hai ca trùng giờ”, hoặc “giao T2 thì phải giao T1” có thể phụ thuộc **nhiều cặp đồng thời**. Một số cấu trúc quota nhóm có thể chuyển thành cung lớp trung gian, nhưng không phải mọi quy tắc đều là bài max flow tiêu chuẩn. Có thể cần **ILP/CP-SAT** hoặc mô hình thời gian/xung đột khác.

### Nhiều đơn vị trên cùng cặp

Nếu W0 thực sự được làm nhiều phiên T0, cần đổi **đơn vị quyết định**. Hoặc tách T0 thành các phiên có ID riêng, hoặc đặt capacity Wi→Tj lớn hơn 1 và xuất lượng phân công. Đừng nhập ba dòng trùng cặp rồi ngầm xem là ba phiên nếu hợp đồng đầu vào đang quy định **mỗi cặp nhị phân**.

### Khả năng mở rộng dữ liệu

Ma trận Boolean L×R dễ hiểu, tự khử trùng và lọc cấm, nhưng tốn **O(LR) bộ nhớ**. Khi hai tập cực lớn và chỉ có ít cặp được phép, nên dùng **danh sách cạnh thưa và HashSet khóa (i,j)** để loại trùng/cấm. Phần mạng luồng vẫn giữ cùng ý nghĩa.

## 11. Dinic: tính max flow và đảo phân công cũ

**Dinic** là thuật toán luồng cực đại làm việc trên **mạng dư**:

1. BFS từ nguồn, chỉ theo cung có residual>0, để gán **level** cho mỗi đỉnh.
2. DFS theo các cung thỏa `level[v]=level[u]+1` để gửi luồng trên đồ thị lớp.
3. Sau mỗi lần gửi Δ, cập nhật cung dư thuận và cung ngược.
4. Tiếp tục gửi cho đến khi không còn luồng chặn trong level graph hiện tại; dựng lại level.
5. Dừng khi BFS không còn tới được đích.

Với một cung gốc u→v dung lượng c đang dùng f, residual thuận là `c−f` và residual ngược là `f`. Nếu một đường tăng đi qua **cung ngược**, nó **hủy** một phần cặp/luồng trước đó để sắp lại chỗ.

**Cách nhìn trong matching:** ban đầu W0 nhận T0. Sau đó W1 cần T0, nhưng W0 cũng làm được T1. Đường dư có thể đi `s→W1→T0→W0→T1→t`, trong đó T0→W0 là cung ngược dư, khiến W0 chuyển sang T1, W1 nhận T0. Không có cặp cấm nào được thêm.

Độ phức tạp tổng quát của Dinic là **O(N²M)** với N đỉnh và M cung gốc; mạng dư tốn **O(N+M)**. Với mạng phân công, `N=L+R+2`, `M=L+R+P`, P là số cặp hiệu lực.

Khi mọi năng lực đều bằng 1, **Hopcroft–Karp** là lựa chọn chuyên dụng cho bipartite maximum matching, có chặn thời gian **O(P√(L+R))**. Chương trình dùng Dinic vì nó minh họa rõ cách **giới hạn năng lực khác 1** trên cả hai phía.

## 12. Java 17+ chạy độc lập: người, việc, capacity và blacklist

Chương trình hoàn chỉnh dùng bốn lớp mạng, giữ riêng mỗi cung dư thuận/ngược, trả số phân công tối đa, các cặp đã chọn và dung lượng lát cắt cực tiểu. Nó còn kiểm tra tính hợp lệ của từng cặp, độ bão hòa nguồn lực và đối chiếu với thuật toán vét cạn độc lập trên bài nhỏ.

Quy ước:

- `candidatePairs` là **whitelist**, `forbiddenPairs` là blacklist có ưu tiên.
- Đầu vào lặp cùng một cặp không tạo thêm công suất.
- Một cặp được phép có capacity **1**.
- Capacity người/việc là số nguyên **long không âm**.
- `workerSlotsFilled` chỉ báo tổng số lượt đã giao có bằng **tổng năng lực người** hay không. Nó **không phải** quy tắc mọi bài toán phải thỏa.
- Bảng in `pairs` theo ID người rồi ID việc tăng; đó chỉ là thứ tự hiển thị.

**Lưu thành `AssignmentConstraintsDemo.java`:**

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class AssignmentConstraintsDemo {
    record Pair(int worker, int task) {
        @Override
        public String toString() {
            return "W" + worker + "-T" + task;
        }
    }

    static final class Model {
        final long[] workers;
        final long[] tasks;
        final boolean[][] candidate;
        final boolean[][] forbidden;
        final boolean[][] allowed;

        Model(long[] workerCapacity, long[] taskCapacity,
              int[][] candidatePairs, int[][] forbiddenPairs) {
            Objects.requireNonNull(workerCapacity, "workers");
            Objects.requireNonNull(taskCapacity, "tasks");
            Objects.requireNonNull(candidatePairs, "candidates");
            Objects.requireNonNull(forbiddenPairs, "forbidden");
            workers = workerCapacity.clone();
            tasks = taskCapacity.clone();

            for (long x : workers) {
                if (x < 0)
                    throw new IllegalArgumentException(
                            "Negative worker capacity");
            }
            for (long x : tasks) {
                if (x < 0)
                    throw new IllegalArgumentException(
                            "Negative task capacity");
            }

            candidate = new boolean[workers.length][tasks.length];
            forbidden = new boolean[workers.length][tasks.length];
            allowed = new boolean[workers.length][tasks.length];

            for (int[] row : candidatePairs) {
                checkPair(row);
                candidate[row[0]][row[1]] = true;
            }
            for (int[] row : forbiddenPairs) {
                checkPair(row);
                forbidden[row[0]][row[1]] = true;
            }
            for (int i = 0; i < workers.length; i++)
                for (int j = 0; j < tasks.length; j++)
                    allowed[i][j] =
                            candidate[i][j] && !forbidden[i][j];
        }

        private void checkPair(int[] row) {
            if (row == null || row.length != 2 ||
                    row[0] < 0 || row[0] >= workers.length ||
                    row[1] < 0 || row[1] >= tasks.length) {
                throw new IllegalArgumentException("Invalid pair ID");
            }
        }

        int eligibleCount() {
            int result = 0;
            for (boolean[] row : allowed)
                for (boolean x : row)
                    if (x) result++;
            return result;
        }

        int blockedCandidateCount() {
            int result = 0;
            for (int i = 0; i < workers.length; i++)
                for (int j = 0; j < tasks.length; j++)
                    if (candidate[i][j] && forbidden[i][j])
                        result++;
            return result;
        }

        long workerSlots() {
            long sum = 0;
            for (long x : workers) sum = Math.addExact(sum, x);
            return sum;
        }
    }

    static final class Arc {
        final int from, to;
        long residual;
        Arc reverse;

        Arc(int from, int to, long residual) {
            this.from = from;
            this.to = to;
            this.residual = residual;
        }
    }

    record Original(int from, int to, long capacity, Arc forward) {}

    static final class Dinic {
        final int n;
        final List<List<Arc>> graph = new ArrayList<>();
        final List<Original> originals = new ArrayList<>();
        final int[] level, next;

        Dinic(int n) {
            this.n = n;
            level = new int[n];
            next = new int[n];
            for (int v = 0; v < n; v++)
                graph.add(new ArrayList<>());
        }

        Arc addArc(int u, int v, long capacity) {
            if (u < 0 || u >= n || v < 0 || v >= n ||
                    capacity < 0) {
                throw new IllegalArgumentException("Invalid flow arc");
            }
            Arc forward = new Arc(u, v, capacity);
            Arc backward = new Arc(v, u, 0L);
            forward.reverse = backward;
            backward.reverse = forward;
            graph.get(u).add(forward);
            graph.get(v).add(backward);
            originals.add(new Original(u, v, capacity, forward));
            return forward;
        }

        boolean buildLevels(int source, int sink) {
            Arrays.fill(level, -1);
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            level[source] = 0;
            queue.addLast(source);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Arc e : graph.get(u)) {
                    if (e.residual > 0 && level[e.to] == -1) {
                        level[e.to] = level[u] + 1;
                        queue.addLast(e.to);
                    }
                }
            }
            return level[sink] != -1;
        }

        long send(int u, int sink, long pushed) {
            if (u == sink) return pushed;
            for (; next[u] < graph.get(u).size(); next[u]++) {
                Arc e = graph.get(u).get(next[u]);
                if (e.residual <= 0 ||
                        level[e.to] != level[u] + 1)
                    continue;

                long delta = send(
                        e.to, sink, Math.min(pushed, e.residual));
                if (delta > 0) {
                    e.residual -= delta;
                    e.reverse.residual = Math.addExact(
                            e.reverse.residual, delta);
                    return delta;
                }
            }
            return 0L;
        }

        long maxFlow(int source, int sink) {
            long total = 0;
            while (buildLevels(source, sink)) {
                Arrays.fill(next, 0);
                long delta;
                while ((delta = send(
                        source, sink, Long.MAX_VALUE)) > 0)
                    total = Math.addExact(total, delta);
            }
            return total;
        }

        boolean[] reachable(int source) {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[source] = true;
            queue.addLast(source);
            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Arc e : graph.get(u)) {
                    if (e.residual > 0 && !seen[e.to]) {
                        seen[e.to] = true;
                        queue.addLast(e.to);
                    }
                }
            }
            return seen;
        }

        long cutCapacity(boolean[] sourceSide) {
            long total = 0;
            for (Original e : originals)
                if (sourceSide[e.from()] && !sourceSide[e.to()])
                    total = Math.addExact(total, e.capacity());
            return total;
        }

        void verify(int source, int sink, long totalFlow) {
            long[] netOut = new long[n];
            for (Original e : originals) {
                long used = Math.subtractExact(
                        e.capacity(), e.forward().residual);
                if (used < 0 || used > e.capacity() ||
                        e.forward().reverse.residual != used)
                    throw new AssertionError("Bad residual capacity");

                netOut[e.from()] = Math.addExact(
                        netOut[e.from()], used);
                netOut[e.to()] = Math.subtractExact(
                        netOut[e.to()], used);
            }

            for (int v = 0; v < n; v++) {
                long expected = v == source ? totalFlow
                        : v == sink ? -totalFlow : 0L;
                if (netOut[v] != expected)
                    throw new AssertionError("Flow conservation");
            }

            boolean[] side = reachable(source);
            if (side[sink] || cutCapacity(side) != totalFlow)
                throw new AssertionError("Bad min-cut certificate");
        }
    }

    record Result(long assigned, long cutCapacity,
                  List<Pair> pairs, int eligible, int blocked,
                  boolean workerSlotsFilled) {}

    static Result solve(Model model) {
        int left = model.workers.length;
        int right = model.tasks.length;
        int source = left + right;
        int sink = source + 1;
        Dinic net = new Dinic(left + right + 2);

        // Nguon -> nguoi.
        for (int i = 0; i < left; i++)
            net.addArc(source, i, model.workers[i]);

        // Viec -> dich.
        for (int j = 0; j < right; j++)
            net.addArc(left + j, sink, model.tasks[j]);

        // Nguoi -> viec: cap 1, chi khi hop le hieu luc.
        Arc[][] pairArc = new Arc[left][right];
        for (int i = 0; i < left; i++)
            for (int j = 0; j < right; j++)
                if (model.allowed[i][j])
                    pairArc[i][j] = net.addArc(i, left + j, 1L);

        long value = net.maxFlow(source, sink);
        net.verify(source, sink, value);
        long cut = net.cutCapacity(net.reachable(source));

        List<Pair> selected = new ArrayList<>();
        for (int i = 0; i < left; i++) {
            for (int j = 0; j < right; j++) {
                Arc e = pairArc[i][j];
                if (e == null) continue;
                long used = 1L - e.residual;
                if (used != 0 && used != 1)
                    throw new AssertionError("Nonbinary pair flow");
                if (used == 1) selected.add(new Pair(i, j));
            }
        }

        Result result = new Result(value, cut,
                List.copyOf(selected), model.eligibleCount(),
                model.blockedCandidateCount(),
                value == model.workerSlots());
        verifyAssignment(model, result);
        return result;
    }

    static void verifyAssignment(Model model, Result result) {
        int left = model.workers.length;
        int right = model.tasks.length;
        long[] usedW = new long[left];
        long[] usedT = new long[right];
        boolean[][] seen = new boolean[left][right];

        for (Pair p : result.pairs()) {
            int u = p.worker(), v = p.task();
            if (u < 0 || u >= left || v < 0 || v >= right ||
                    !model.allowed[u][v] || seen[u][v])
                throw new AssertionError("Forbidden/duplicate pair");
            seen[u][v] = true;
            usedW[u]++;
            usedT[v]++;
        }

        for (int u = 0; u < left; u++)
            if (usedW[u] > model.workers[u])
                throw new AssertionError("Worker over capacity");
        for (int v = 0; v < right; v++)
            if (usedT[v] > model.tasks[v])
                throw new AssertionError("Task over capacity");

        if (result.pairs().size() != result.assigned() ||
                result.assigned() != result.cutCapacity() ||
                result.eligible() != model.eligibleCount() ||
                result.blocked() != model.blockedCandidateCount() ||
                result.workerSlotsFilled() !=
                        (result.assigned() == model.workerSlots()))
            throw new AssertionError("Invalid assignment result");
    }

    // Oracle doc lap: thu chon/khong chon tung cap.
    // Chi dung voi toi da 4 nguoi va 4 viec.
    private static int bruteChoose(
            List<Pair> options, int index, int[] usedW,
            int[] usedT, Model model) {
        if (index == options.size()) return 0;
        int best = bruteChoose(options, index + 1,
                usedW, usedT, model);
        Pair p = options.get(index);
        int u = p.worker(), v = p.task();
        if (usedW[u] < model.workers[u] &&
                usedT[v] < model.tasks[v]) {
            usedW[u]++;
            usedT[v]++;
            best = Math.max(best, 1 + bruteChoose(
                    options, index + 1, usedW, usedT, model));
            usedW[u]--;
            usedT[v]--;
        }
        return best;
    }

    static int bruteMaximum(Model model) {
        if (model.workers.length > 4 ||
                model.tasks.length > 4)
            throw new IllegalArgumentException(
                    "Brute oracle only for small models");

        List<Pair> options = new ArrayList<>();
        for (int i = 0; i < model.workers.length; i++)
            for (int j = 0; j < model.tasks.length; j++)
                if (model.allowed[i][j])
                    options.add(new Pair(i, j));

        return bruteChoose(options, 0,
                new int[model.workers.length],
                new int[model.tasks.length], model);
    }

    static void show(String name, Model model) {
        Result r = solve(model);
        if (r.assigned() != bruteMaximum(model))
            throw new AssertionError("Wrong optimum in " + name);

        System.out.println(name
                + " assigned=" + r.assigned()
                + " cut=" + r.cutCapacity()
                + " eligible=" + r.eligible()
                + " blocked=" + r.blocked()
                + " pairs=" + r.pairs()
                + " workerSlotsFilled=" + r.workerSlotsFilled());
    }

    static void crossCheck() {
        Random random = new Random(2026L);

        for (int test = 0; test < 300; test++) {
            int left = random.nextInt(5);
            int right = random.nextInt(5);
            long[] workerCap = new long[left];
            long[] taskCap = new long[right];

            for (int i = 0; i < left; i++)
                workerCap[i] = random.nextInt(4);
            for (int j = 0; j < right; j++)
                taskCap[j] = random.nextInt(4);

            int candidateCount = left == 0 || right == 0 ? 0 :
                    random.nextInt(2 * left * right + 1);
            int forbiddenCount = left == 0 || right == 0 ? 0 :
                    random.nextInt(left * right + 1);
            int[][] candidates = new int[candidateCount][2];
            int[][] forbidden = new int[forbiddenCount][2];

            for (int i = 0; i < candidateCount; i++) {
                candidates[i][0] = random.nextInt(left);
                candidates[i][1] = random.nextInt(right);
            }
            for (int i = 0; i < forbiddenCount; i++) {
                forbidden[i][0] = random.nextInt(left);
                forbidden[i][1] = random.nextInt(right);
            }

            Model model = new Model(
                    workerCap, taskCap, candidates, forbidden);
            Result actual = solve(model);
            int expected = bruteMaximum(model);

            if (actual.assigned() != expected)
                throw new AssertionError(
                        "Random mismatch at test " + test);
        }
        System.out.println("crossCheck=PASS (300 models)");
    }

    public static void main(String[] args) {
        show("oneToOne", new Model(
                new long[]{1,1,1}, new long[]{1,1,1},
                new int[][]{{0,0},{0,1},{1,0},{2,1},{2,2}},
                new int[0][2]));

        show("capacitated", new Model(
                new long[]{2,1,1}, new long[]{1,2,1},
                new int[][]{
                    {0,0},{0,1},{1,1},{1,2},{2,0},{2,2}
                }, new int[0][2]));

        show("forbidden", new Model(
                new long[]{1,1}, new long[]{1,1},
                new int[][]{
                    {0,0},{0,1},{1,0},{1,1}
                }, new int[][]{{0,0},{1,1}}));

        show("pairOnce", new Model(
                new long[]{3}, new long[]{5},
                new int[][]{{0,0},{0,0},{0,0}},
                new int[0][2]));

        show("bottleneck", new Model(
                new long[]{2,1,1}, new long[]{3,1},
                new int[][]{{0,0},{1,0},{2,0}},
                new int[0][2]));

        show("noCompatible", new Model(
                new long[]{1,1}, new long[]{1,1},
                new int[0][2], new int[0][2]));

        show("zeroCapacity", new Model(
                new long[]{0,2}, new long[]{1,1},
                new int[][]{{0,0},{1,0},{1,1}},
                new int[0][2]));

        show("isolated", new Model(
                new long[]{1,1,1}, new long[]{1,1,1},
                new int[][]{{0,0},{2,1}},
                new int[0][2]));

        show("forbiddenOnly", new Model(
                new long[]{1}, new long[]{1},
                new int[][]{{0,0}}, new int[][]{{0,0}}));

        show("empty", new Model(
                new long[0], new long[0],
                new int[0][2], new int[0][2]));

        show("bigCap", new Model(
                new long[]{5_000_000_000L},
                new long[]{5_000_000_000L},
                new int[][]{{0,0}}, new int[0][2]));

        try {
            new Model(new long[]{1}, new long[]{1},
                    new int[][]{{0,1}}, new int[0][2]);
            throw new AssertionError("Expected invalid pair");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidPair=rejected");
        }

        try {
            new Model(new long[]{-1}, new long[]{1},
                    new int[0][2], new int[0][2]);
            throw new AssertionError("Expected negative capacity");
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeCapacity=rejected");
        }

        crossCheck();
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac AssignmentConstraintsDemo.java
java AssignmentConstraintsDemo
~~~

**Đầu ra xác định:**

~~~text
oneToOne assigned=3 cut=3 eligible=5 blocked=0 pairs=[W0-T1, W1-T0, W2-T2] workerSlotsFilled=true
capacitated assigned=4 cut=4 eligible=6 blocked=0 pairs=[W0-T0, W0-T1, W1-T1, W2-T2] workerSlotsFilled=true
forbidden assigned=2 cut=2 eligible=2 blocked=2 pairs=[W0-T1, W1-T0] workerSlotsFilled=true
pairOnce assigned=1 cut=1 eligible=1 blocked=0 pairs=[W0-T0] workerSlotsFilled=false
bottleneck assigned=3 cut=3 eligible=3 blocked=0 pairs=[W0-T0, W1-T0, W2-T0] workerSlotsFilled=false
noCompatible assigned=0 cut=0 eligible=0 blocked=0 pairs=[] workerSlotsFilled=false
zeroCapacity assigned=2 cut=2 eligible=3 blocked=0 pairs=[W1-T0, W1-T1] workerSlotsFilled=true
isolated assigned=2 cut=2 eligible=2 blocked=0 pairs=[W0-T0, W2-T1] workerSlotsFilled=false
forbiddenOnly assigned=0 cut=0 eligible=0 blocked=1 pairs=[] workerSlotsFilled=false
empty assigned=0 cut=0 eligible=0 blocked=0 pairs=[] workerSlotsFilled=true
bigCap assigned=1 cut=1 eligible=1 blocked=0 pairs=[W0-T0] workerSlotsFilled=false
invalidPair=rejected
negativeCapacity=rejected
crossCheck=PASS (300 models)
~~~

### Đọc ý nghĩa đầu ra

- `assigned` là số cặp **khác nhau** đã chọn, tương đương giá trị max flow.
- `cut` là dung lượng lát cắt tối thiểu dựng từ mạng dư; `assigned=cut` chứng nhận tối ưu khi luồng và cặp hợp lệ.
- `eligible` đếm các cặp hiệu lực phân biệt; input candidate lặp không làm số này tăng.
- `blocked` đếm **cặp phân biệt vừa có trong candidate vừa bị blacklist**. Dòng blacklist không có candidate tương ứng không tăng `blocked`.
- `pairs` được in theo thứ tự ID người, rồi ID việc tăng dần; không đồng nghĩa thuật toán tối ưu một tiêu chí thứ tự từ điển.
- `workerSlotsFilled` là `assigned=Σ a[i]`. **true không có nghĩa tất cả việc đã được giao**, nhất là khi các việc có quota lớn hơn nhu cầu người hoặc mô hình rỗng.

### Những ví dụ đáng chú ý

**oneToOne:** 3 người, 3 việc; tìm được 3 cặp dù một cách chọn greedy chỉ tìm 2. Đây là một perfect matching.

**capacitated:** W0 nhận hai việc, T1 nhận hai người; bốn cặp đạt tổng capacity người và việc, không cặp nào lặp lại.

**forbidden:** ứng viên ban đầu có cả bốn cặp nhưng hai cặp cấm đã bị loại, còn đúng W0–T1 và W1–T0. Chỉ so “số lượng=2” mà không xem cụ thể cặp được chọn là chưa đủ để kiểm tra tính hợp lệ.

**pairOnce:** cùng một candidate xuất hiện ba lần nhưng cặp vẫn có capacity1. Dù hai phía có năng lực 3 và 5, tối ưu chỉ có 1.

**bottleneck:** năng lực tổng của hai phía đều bằng 4 nhưng chỉ có 3 cặp hiệu lực; thuật toán báo 3 và không “tự điền” cặp không tương thích.

**zeroCapacity:** W0 có năng lực 0 nhưng candidate W0–T0 vẫn có thể có trong danh sách kỹ năng; không có luồng đi qua W0. W1 cap2 nhận T0 và T1.

**forbiddenOnly:** một candidate bị blacklist loại; không có cạnh người→việc hiệu lực, đáp án 0.

**empty:** không có người, không có việc; kết quả rỗng. `workerSlotsFilled=true` đơn thuần do `0=0`.

**bigCap:** năng lực 5 tỷ không tạo nhiều lượt giữa cùng một cặp Wi–Tj; đáp án vẫn chỉ là 1. Dùng `long` tránh tràn số ở dung lượng đầu vào.

**invalidPair/negativeCapacity:** không chấp nhận ID việc ngoài phạm vi hoặc năng lực âm.

## 13. Kiểm chứng độc lập và tính hợp lệ

Một con số tối ưu **không đủ** nếu danh sách cặp đã chọn vi phạm quy định. Chương trình kiểm tra đồng thời:

1. Mỗi cặp được chọn tồn tại trong `allowed` và chưa được chọn trước đó.
2. Số lượt của người i ≤a[i]; số người của việc j ≤b[j].
3. Số cặp được chọn bằng giá trị luồng.
4. Mọi cung gốc thỏa `0≤flow≤capacity` và cung ngược có residual phản ánh lượng đã dùng.
5. Bảo toàn luồng tại tất cả đỉnh trung gian.
6. Từ mạng dư cuối cùng dựng một lát cắt có dung lượng **bằng đúng max flow**.

Bên cạnh đó, `bruteMaximum` dùng cách **chọn hoặc không chọn** từng cặp hiệu lực, thử các tổ hợp trong giới hạn capacity. Nó **không gọi Dinic**, nên là một phương pháp đối chứng độc lập cho mô hình nhỏ.

Chương trình sinh **300 mô hình** ngẫu nhiên bằng seed cố định, mỗi mô hình có 0..4 người, 0..4 việc, năng lực 0..3, candidate có thể trùng và blacklist có thể giao candidate. Nó so kết quả Dinic với brute-force và báo lỗi nếu khác nhau.

Với P cặp, vét cạn có thể cần **O(2^P)** phép thử; chỉ dùng cho unit test nhỏ. Mô hình ma trận Boolean tốn O(LR); mạng Dinic tốn O(N+M), nên bộ nhớ tổng của chương trình là **O(LR+N+M)**, không phải chỉ O(N+M).

**Giới hạn mã:** hàm giải được gọi trên một mạng vừa tạo mới; không tái sử dụng trạng thái mạng dư đã bị thay đổi để tính một bài toán input khác. Nếu cần hỗ trợ điều kiện lower-bound, tổng điểm, độ công bằng hoặc ca trùng giờ, phải xây mô hình mở rộng.

## 14. Trường hợp biên và phản ví dụ

| Dữ liệu | Cách xử lý đúng |
| --- | --- |
| Không có người hoặc việc | Không có cặp; max flow 0. |
| Một phía có capacity 0 | Không có luồng qua phía đó, dù candidate tương thích. |
| Candidate rỗng | Không có cung người→việc, đáp án 0. |
| Mọi candidate đều bị cấm | Sau lọc không còn cạnh hiệu lực, đáp án 0. |
| Candidate xuất hiện trùng | Chỉ một cặp phân biệt với cap1. |
| Một người cap3, một việc cap5, một cặp | Tối đa 1 nếu cap cặp=1. |
| Nhiều người cùng tranh một việc cap1 | Tối đa một cặp vào việc đó. |
| Việc cap2 có nhiều người tương thích | Có thể nhận hai người **khác nhau**. |
| Người cap2 có nhiều việc tương thích | Có thể làm hai việc **khác nhau**. |
| Người/việc đều có năng lực nhưng không có cạnh giữa chúng | Không thể tự sinh cặp mới. |
| Có cặp vừa compatible vừa forbidden | Blacklist loại cạnh. |
| Năng lực âm hoặc ID ngoài phạm vi | Báo lỗi dữ liệu; không tự sửa. |
| Năng lực rất lớn | Dùng kiểu số phù hợp, cap cặp vẫn độc lập. |
| Yêu cầu mọi người làm đủ nhưng F*<Σa | Báo không khả thi. |
| Chỉ cần K cặp và F*≥K, không có minima | Có thể giữ K cặp bất kỳ từ nghiệm F*. |
| Mô hình có chi phí và cặp cấm | Loại cặp cấm, rồi tối ưu chi phí trên các cặp hợp lệ. |

**Một–một không được đánh đồng với “mỗi cặp chỉ một lần” khi capacity theo đỉnh >1.** Trường hợp W0 nhận hai việc khác nhau vẫn thỏa tính duy nhất của từng cặp, nhưng không còn là matching một–một theo nghĩa mỗi người tối đa một việc.

## 15. Sai lầm thường gặp

1. Dùng `≤1` khi đề yêu cầu `=1` cho mọi người hoặc mọi việc.
2. Dùng `=1` khi đề chỉ yêu cầu tối đa một, biến bài khả thi thành bất khả thi.
3. Cho một người cap3 làm ba lần **cùng một cặp**, dù cap cặp đang là 1.
4. Cho rằng đáp án bằng min(tổng năng lực hai phía), bỏ qua cấu trúc tương thích.
5. Thêm cạnh bị cấm với chi phí phạt lớn thay vì loại cạnh.
6. Không ưu tiên blacklist khi có candidate trùng cặp cấm.
7. Mặc định cặp không xuất hiện trong whitelist cũng hợp lệ.
8. Không khử các bản ghi candidate lặp, làm tăng giả số cặp.
9. Xem cung ngược **dư** như một phân công mới cho cặp cấm.
10. Bỏ cung dư ngược, khiến thuật toán không đổi được lựa chọn cũ.
11. Dùng greedy đơn giản rồi tuyên bố tối ưu toàn cục.
12. Không kiểm tra ID người/việc, gây truy cập sai hoặc ghép đối tượng không tồn tại.
13. Không kiểm tra capacity âm; âm không phải giới hạn hợp lệ.
14. Nhầm quota tối thiểu với năng lực tối đa.
15. Chỉ kiểm tra tổng F khi yêu cầu một việc cụ thể phải có ít nhất một người.
16. Không kiểm tra cặp được chọn có thực sự allowed hay không.
17. Không kiểm tra năng lực **cả hai phía** trên kết quả.
18. Không kiểm tra trùng cùng một cặp sau khi rút nghiệm từ flow.
19. Cho rằng max flow tối ưu điểm phù hợp hay chi phí, dù không dùng hàm chi phí.
20. Dùng Hall một–một cho hệ capacity>1 mà không điều chỉnh cap cặp.
21. Dùng tổng capacity hàng xóm thay cho `min(cap,deg_U)` và kết luận đủ.
22. Xem toàn bộ ràng buộc nhóm/ca làm như những quota độc lập.
23. Dùng kiểu int cho dung lượng hàng tỷ.
24. Báo thuật toán và toàn bộ chương trình có O(N+M) bộ nhớ nhưng giữ ma trận L×R.
25. Dùng brute-force 2^P như lời giải chính khi P lớn.
26. Không phân biệt “workerSlotsFilled” với “mọi người nhận ít nhất một việc”.
27. Coi nhiều nghiệm cùng số cặp là có cùng danh sách cặp, trong khi có thể có nhiều nghiệm tối ưu.
28. Không kiểm tra chứng chỉ luồng/cắt để chứng minh số lượng tối đa.
29. Không báo tính bất khả thi khi bắt buộc mọi người phải đạt đủ quota.
30. Không làm rõ đơn vị công việc là cặp, phiên hay giờ công.
31. Cho phép một cặp trùng trong candidate biểu thị nhiều suất mà không có ID phiên.
32. Không xử lý mô hình rỗng, cap0 hoặc toàn cặp cấm.
33. Thay hard constraint bằng soft preference mà không có quyết định chính sách.
34. Tự cho rằng càng tăng capacity một phía thì luôn tăng được kết quả, dù không có cạnh hợp lệ.
35. Xem số cặp lớn nhất như số công việc được bao phủ khi một việc có thể nhận nhiều người.

## 16. Bài tập có lời giải

**Bài 1.** Mỗi người nhận không quá một việc được viết thế nào? **Đáp án:** `Σ_j x[i][j]≤1` cho mọi i.

**Bài 2.** Mỗi người bắt buộc có đúng một việc thì sao? **Đáp án:** `Σ_j x[i][j]=1` cho mọi i, và phải kiểm tra tính khả thi.

**Bài 3.** Hai người có thể cùng nhận T1 khi b[1]=2 không? **Đáp án:** có nếu là **hai người khác nhau**, cả hai cặp được phép và các quota phía người cũng thỏa.

**Bài 4.** W0 cap2 có thể ghép W0–T1 hai lần không? **Đáp án:** không khi mỗi cặp capacity1; W0 có thể ghép với hai **việc khác nhau**.

**Bài 5.** Một candidate vừa nằm trong blacklist. Có được chọn không? **Đáp án:** không; cặp bị cấm tuyệt đối.

**Bài 6.** Có nên thay lệnh cấm bằng chi phí 1 tỷ? **Đáp án:** không nếu cấm cứng; chi phí hữu hạn vẫn có thể bị thuật toán chọn khi thiếu phương án.

**Bài 7.** Một người cap3, một việc cap5, chỉ một cặp hiệu lực. F* bằng bao nhiêu? **Đáp án:** 1 khi cap cặp=1.

**Bài 8.** Ba người cap [2,1,1], hai việc cap [3,1], chỉ ba cặp người khác nhau tới T0. Tối ưu bao nhiêu? **Đáp án:** 3, không thể dùng T1 nếu không có cạnh hợp lệ.

**Bài 9.** Mạng phân công có các lớp nào? **Đáp án:** nguồn s, người W, việc T, đích t.

**Bài 10.** Cung s→Wi có capacity gì? **Đáp án:** năng lực a[i] của người i.

**Bài 11.** Cung Wi→Tj có capacity gì trong mô hình nhị phân? **Đáp án:** 1 và chỉ tồn tại nếu cặp hiệu lực.

**Bài 12.** Cung Tj→t có capacity gì? **Đáp án:** b[j] của việc j.

**Bài 13.** Tại sao flow trên cung cặp 1 phải nhị phân? **Đáp án:** tính nguyên của max flow với dung lượng nguyên và capacity 1 trên cung cặp.

**Bài 14.** Nguồn W và việc T cùng có ID 0, chúng có phải cùng một đỉnh không? **Đáp án:** không; hai tập đỉnh rời nhau.

**Bài 15.** Cung dư ngược dùng để làm gì? **Đáp án:** hoàn tác một phần quyết định cũ và đổi cặp theo đường tăng.

**Bài 16.** Nếu max flow bằng min cut và kết quả hợp lệ, điều đó chứng minh gì? **Đáp án:** không có cách phân công hợp lệ nào có nhiều cặp hơn.

**Bài 17.** Mô hình chỉ có upper bounds, cần chính xác K cặp. Khi nào có nghiệm? **Đáp án:** khi F*≥K; có thể bỏ bớt cặp từ nghiệm tối đa.

**Bài 18.** Tất cả người phải làm đủ a[i] lượt. Điều kiện kiểm tra sau max flow? **Đáp án:** `F*=Σ_i a[i]`.

**Bài 19.** Một việc có quota tối thiểu nhưng không có cặp hiệu lực, max flow lớn ở việc khác có giải quyết được không? **Đáp án:** không; yêu cầu tối thiểu riêng việc đó bất khả thi.

**Bài 20.** Hall một–một phát biểu gì? **Đáp án:** mọi tập người U có ít nhất |U| việc khác nhau trong N(U).

**Bài 21.** Trong hệ capacity và cap cặp1, một việc Tj có thể nhận tối đa bao nhiêu lượt từ nhóm U? **Đáp án:** `min(b[j],deg_U(j))`.

**Bài 22.** Vì sao chỉ dùng tổng capacity hàng xóm chưa đủ khi cap cặp1? **Đáp án:** một người không thể gửi nhiều đơn vị vào một việc qua đúng một cặp cap1.

**Bài 23.** Một bài có điểm phù hợp từng cặp, Dinic cơ bản tự tối đa tổng điểm không? **Đáp án:** không; nó tối đa **số lượt** và cần bài tối ưu chi phí/điểm bổ sung.

**Bài 24.** Nếu muốn W0 làm nhiều phiên của một việc, cần sửa mô hình như thế nào? **Đáp án:** tách các phiên hoặc tăng capacity theo cặp và biểu diễn lượng, không giữ x nhị phân.

**Bài 25.** Vì sao candidate lặp ba lần không tạo ba cung? **Đáp án:** ba dòng chỉ nói về **một cặp thực thể phân biệt**, phải chuẩn hóa nếu hợp đồng cap cặp1.

**Bài 26.** Với model rỗng cả hai phía, F*=0 và workerSlotsFilled có giá trị gì? **Đáp án:** true theo 0=0; không suy ra có công việc thực tế hoàn thành.

**Bài 27.** Một người capacity 0 vẫn tương thích với một việc; tại sao không thể nhận việc? **Đáp án:** cung nguồn→người có dung lượng 0.

**Bài 28.** Max flow và min-cost max-flow khác nhau ở đâu? **Đáp án:** max flow tối đa lượng; min-cost max-flow thêm mục tiêu cực tiểu chi phí trong các luồng thỏa lượng yêu cầu.

**Bài 29.** Tại sao dữ liệu blacklist phải được kiểm tra trên từng cặp kết quả thay vì chỉ nhìn F? **Đáp án:** một phương án chọn cặp cấm có thể có **cùng số cặp tối ưu** nhưng không hợp lệ.

**Bài 30.** Vì sao cần oracle brute-force cho input nhỏ? **Đáp án:** nó thử chọn/bỏ từng cặp bằng nguyên lý khác, giúp kiểm chứng giá trị tối ưu của Dinic.

## 17. Checklist giải bài và đánh giá kết quả

1. **Xác định đơn vị** của một lượt phân công: cặp, phiên hay đơn vị liên tục.
2. **Viết rõ từng quota**: tối đa, tối thiểu hay chính xác.
3. **Phân biệt một–một với capacity >1** trên hai phía.
4. **Lọc candidate và forbidden** theo quy tắc đã công bố; cấm cứng phải loại cạnh.
5. **Khử dòng trùng** nếu một cặp chỉ được dùng một lần.
6. **Kiểm tra năng lực không âm và ID hợp lệ**.
7. **Xây mạng** s→người cap a, người→việc cap1 khi allowed, việc→t cap b.
8. **Cho phép cung dư ngược** để đổi cặp và tìm nghiệm tối ưu.
9. **Đọc nghiệm từ cung cặp**, không đếm các cung nguồn hoặc cung dư ngược như lượt.
10. **Xác nhận mọi cặp đã chọn hợp lệ, không lặp, không bị cấm**.
11. **Xác nhận năng lực từng người và việc không vượt giới hạn**.
12. **So số cặp với max flow**, kiểm tra chứng chỉ maxflow=mincut.
13. **Nếu phải dùng hết quota**, kiểm tra tính khả thi riêng, không chỉ in max flow.
14. **Nếu có lower bounds hoặc điểm/cost**, chọn bài toán mở rộng đúng.
15. **Thử input rỗng, cap0, candidate trùng, cặp cấm và nút thắt tương thích**.
16. **Dùng brute-force trên input nhỏ** và quan sát độ phức tạp cho input lớn.
17. **Đánh giá đúng tài nguyên:** ma trận L×R cộng mạng N đỉnh M cung.
18. **Không tự nới lỏng cặp cấm** chỉ để tăng số lượng.

**Ghi nhớ:** một phương án phân công đúng cần cùng lúc thỏa **năng lực người**, **năng lực việc** và **cặp được phép**. Với mỗi cặp chỉ được dùng một lần, cạnh người→việc phải có **capacity 1**; cặp bị cấm **không được tạo cạnh**. Luồng cực đại cho **số lượt nhiều nhất**, lát cắt cực tiểu cho **chứng chỉ giới hạn**, còn các yêu cầu **giao đủ quota, chi phí hoặc công bằng** phải được đặt thành điều kiện/mục tiêu riêng.
