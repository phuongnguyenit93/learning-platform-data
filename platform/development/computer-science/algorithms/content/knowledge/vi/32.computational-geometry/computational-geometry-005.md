# Kiểm tra điểm trong đa giác và xử lý điểm trên biên

**Kiểm tra điểm trong đa giác (point-in-polygon, PIP)** là bài toán quyết định một điểm truy vấn Q nằm **bên trong**, **bên ngoài**, hay **trên biên** của một đa giác. Một lời giải chỉ trả true/false dễ bỏ sót tình huống quan trọng nhất: điểm nằm đúng trên một cạnh hoặc trùng một đỉnh. Đặc biệt, thuật toán đếm tia cắt cạnh có thể sai tại các đỉnh nếu đếm hai lần, còn phép tính hình học bằng số nguyên có thể tràn số trước khi người lập trình nhận ra.

Bài thuộc nhóm **Hình học tính toán** của Computer Science Algorithms. Ta sẽ xây một lời giải chính xác cho **đa giác đơn** (simple polygon), dùng tọa độ nguyên và ba trạng thái `INSIDE`, `OUTSIDE`, `BOUNDARY`. Trọng tâm là phép **định hướng** bằng tích có hướng, kiểm tra **điểm trên đoạn thẳng**, hai quy tắc **ray casting / even–odd** và **winding number**, cách xử lý cạnh ngang và đỉnh bằng khoảng **nửa mở**, lỗ của miền đa giác, chính sách biên đóng/mở, chứng minh, độ phức tạp, Java 17+ chạy độc lập và phép kiểm thử bằng oracle hình học.

## 1. Phát biểu bài toán và hợp đồng đầu ra

Cho một đa giác được mô tả bằng dãy đỉnh theo thứ tự đi dọc đường biên:

`P=(V₀,V₁,…,V_(n−1))`, với n≥3.

Cạnh thứ i nối:

`Eᵢ=[Vᵢ,V_((i+1) mod n)]`.

Cạnh từ đỉnh cuối quay về đỉnh đầu được **hiểu ngầm**, nên không bắt buộc lặp lại V₀ ở cuối danh sách. Chương trình minh họa chấp nhận cả dạng khép kín lặp V₀ đúng **một lần** ở cuối và loại bản sao cuối trước khi xử lý.

Cho điểm `Q=(x,y)`, yêu cầu trả:

| Trạng thái | Ý nghĩa | Ví dụ với hình chữ nhật `[0,8]×[0,6]` |
| --- | --- | --- |
| `INSIDE` | Q nằm trong miền trong, **không nằm trên biên** | (3,2) |
| `OUTSIDE` | Q ở miền ngoài, **không nằm trên biên** | (9,2) |
| `BOUNDARY` | Q nằm trên ít nhất một cạnh kín hoặc trùng đỉnh | (8,3), (0,0) |

Phải làm rõ ràng khi bài toán cuối cùng muốn kết quả kiểu boolean:

- **Bao gồm biên (closed polygon):** `containsInclusive(Q) = (location != OUTSIDE)`.
- **Loại biên (open interior):** `containsStrict(Q) = (location == INSIDE)`.

Cả hai đều có thể đúng tùy đề. Trả **ba trạng thái trước**, sau đó chuyển thành boolean theo yêu cầu là cách giảm nhầm lẫn.

### Giả thiết về đa giác

Phần giải thích và mã Java coi đường biên là một **đa giác đơn không tự cắt**, tức các cạnh chỉ gặp nhau ở các đỉnh liên tiếp và tạo một đường kín hợp lệ. Đa giác có thể **lồi**, **lõm**, có cạnh ngang/dọc, và được liệt kê theo **chiều kim đồng hồ (CW)** hay **ngược chiều kim đồng hồ (CCW)**.

Đa giác **tự cắt** như hình nơ, hoặc một đa giác có **nhiều vòng và lỗ**, cần thêm quy tắc miền bên trong. Even–odd và winding có thể cho kết quả khác nhau trên đường tự cắt. Mã minh họa kiểm tra số đỉnh, cạnh độ dài 0 và diện tích có hướng khác 0, nhưng **không làm phép kiểm tra mọi cặp cạnh giao nhau**: tính đơn của đa giác vẫn là **điều kiện đầu vào**.

### Tọa độ và độ chính xác

Phiên bản chính dùng **tọa độ nguyên 64 bit (`long`)**. Phép định hướng có thể vượt 64 bit ngay cả khi tất cả tọa độ đầu vào hợp lệ, nên Java dùng **`BigInteger`** để không tràn phép trừ hay tích có hướng. Bài cũng phân biệt cách xử lý dữ liệu số thực bằng epsilon ở phần sau.

## 2. Bước bắt buộc trước khi đếm tia: kiểm tra trên đoạn

Cho đoạn AB với:

`A=(aₓ,aᵧ)`, `B=(bₓ,bᵧ)`,

và điểm `Q=(qₓ,qᵧ)`.

Tích có hướng của vectơ AB và AQ là:

`cross(A,B,Q)=(bₓ−aₓ)(qᵧ−aᵧ)−(bᵧ−aᵧ)(qₓ−aₓ)`.

Ý nghĩa:

- `cross>0`: Q nằm bên **trái** hướng A→B.
- `cross<0`: Q nằm bên **phải** hướng A→B.
- `cross=0`: A, B, Q **thẳng hàng**.

**Thẳng hàng chưa đồng nghĩa Q nằm trên đoạn.** Với A=(0,0), B=(4,0), Q=(7,0), cross=0 nhưng Q nằm ngoài đoạn AB.

Điều kiện **đủ và cần** cho Q nằm trên **đoạn kín** AB:

`cross(A,B,Q)=0`,

và:

`min(aₓ,bₓ)≤qₓ≤max(aₓ,bₓ)`,

`min(aᵧ,bᵧ)≤qᵧ≤max(aᵧ,bᵧ)`.

Đối với cạnh ngang/dọc, công thức này vẫn dùng được; với Q trùng A hoặc B, cũng trả true. Chương trình **kiểm tra onSegment trước khi đếm tia**, tránh phải tranh luận một tia đi qua đúng đỉnh sẽ tính bên trong hay ngoài.

### Ví dụ về đoạn thẳng

Cho A=(0,0), B=(8,0):

| Q | Cross | Trong hộp bao? | Kết luận |
| --- | ---: | --- | --- |
| (3,0) | 0 | Có | Trên đoạn |
| (0,0) | 0 | Có | Trùng đỉnh |
| (8,0) | 0 | Có | Trùng đỉnh |
| (9,0) | 0 | Không | Ngoài đoạn |
| (3,1) | 8 | Có về x nhưng khác y | Không nằm trên đoạn |

### Vì sao dùng BigInteger thay vì nhân long?

Nếu tọa độ là `long`, phép `b.x - a.x` có thể tràn ngay từ bước trừ: ví dụ `Long.MAX_VALUE - Long.MIN_VALUE` không nằm trong `long`. Kể cả khi hiệu không tràn, tích hai hiệu cũng có thể vượt 64 bit.

**Sai:**

~~~java
long dx = b.x() - a.x(); // Có thể tràn trước bước nhân.
long cross = dx * (q.y() - a.y())
        - (b.y() - a.y()) * (q.x() - a.x());
~~~

**Đúng cho toàn bộ miền tọa độ long:**

~~~java
BigInteger dx = BigInteger.valueOf(b.x())
        .subtract(BigInteger.valueOf(a.x()));
BigInteger dy = BigInteger.valueOf(b.y())
        .subtract(BigInteger.valueOf(a.y()));
BigInteger qx = BigInteger.valueOf(q.x())
        .subtract(BigInteger.valueOf(a.x()));
BigInteger qy = BigInteger.valueOf(q.y())
        .subtract(BigInteger.valueOf(a.y()));

BigInteger cross = dx.multiply(qy).subtract(dy.multiply(qx));
~~~

Đây là **mảnh mã minh họa**, cần `import java.math.BigInteger` và các điểm được định nghĩa; chương trình đầy đủ ở mục 12 sử dụng phương pháp này. Không gọi `Math.abs(cross)` trên một `long` đã bị tràn rồi mong sửa được kết quả.

## 3. Phương pháp 1: tia ngang và quy tắc chẵn–lẻ

**Ray casting (even–odd rule)**: từ Q, phát một tia ngang sang **phải vô hạn**. Đếm số lần tia **cắt đường biên** của đa giác.

- Nếu số lần cắt **lẻ**: Q ở trong.
- Nếu **chẵn**: Q ở ngoài.
- Nếu Q nằm trực tiếp **trên biên**: trả `BOUNDARY`, không sử dụng tính chẵn/lẻ.

Lý do trực giác: bắt đầu rất xa ngoài đa giác, mỗi lần vượt qua biên của đa giác đơn sẽ chuyển giữa ngoài và trong. Khi quét từ Q sang phải, một số lần cắt lẻ nghĩa là đang ở phía trong; chẵn nghĩa là phía ngoài.

### Một ví dụ hình chữ nhật

~~~text
(0,6) +----------------------+ (8,6)
      |                      |
      |       Q(3,2) *------>+---------- tia sang phải
      |                      |
(0,0) +----------------------+ (8,0)
~~~

Q=(3,2) có đúng một giao điểm tia sang phải với cạnh x=8 ⇒ `INSIDE`. Q=(9,2) ở bên phải hình chữ nhật: tia không cắt cạnh nào ⇒ `OUTSIDE`.

**Rắc rối:** tia có thể đi qua **đỉnh**, một cạnh có thể nằm **ngang theo đúng tia**, và giao điểm có thể nằm bên **trái Q**. Thuật toán đúng phải loại bỏ những tình huống đếm trùng hoặc sai hướng đó.

## 4. Quy tắc khoảng nửa mở tránh đếm hai lần tại đỉnh

Xét cạnh AB. Ta chỉ coi cạnh là ứng viên cắt tia khi cao độ của Q nằm trong một khoảng **nửa mở** giữa hai đầu cạnh:

- **Cạnh đi lên:** `aᵧ≤qᵧ<bᵧ`.
- **Cạnh đi xuống:** `bᵧ≤qᵧ<aᵧ`.

Nói chung:

`min(aᵧ,bᵧ)≤qᵧ<max(aᵧ,bᵧ)`.

Nhờ **đầu dưới được tính, đầu trên không tính**, một đỉnh chung không bị đếm hai lần chỉ vì hai cạnh kề nhau cùng chạm tia tại đúng cao độ của đỉnh. Đối với cạnh ngang, min=max nên không có y nào thỏa bất đẳng thức; cạnh ngang **không được dùng để thay đổi parity**, nhưng **vẫn phải kiểm tra BOUNDARY trước**.

### Kiểm tra giao điểm ở bên phải mà không tính số thực

Nếu cạnh cắt đường ngang y=qᵧ, tọa độ giao điểm lý thuyết là:

`x_intersection = aₓ + (qᵧ−aᵧ)(bₓ−aₓ)/(bᵧ−aᵧ)`.

Về mặt ý tưởng, ta muốn đếm khi `x_intersection>qₓ`.

Thay vì chia số thực hoặc làm tròn giao điểm, dùng **dấu của cross**:

- Nếu cạnh **đi lên**, giao điểm ở **bên phải Q** khi `cross(A,B,Q)>0`.
- Nếu cạnh **đi xuống**, giao điểm ở **bên phải Q** khi `cross(A,B,Q)<0`.

Có thể kiểm chứng bằng ví dụ cạnh dọc đi lên A=(8,0), B=(8,6), Q=(3,2): `cross=6·(3−8)` theo dạng vectơ, cụ thể `cross=(0)(2)−(6)(−5)=30>0`, và giao điểm x=8 ở bên phải 3. Nếu đảo hướng cạnh, cross đổi dấu và điều kiện tương ứng cũng đảo.

**Nếu cross=0 và Q thuộc phạm vi y của cạnh**, Q nằm trên đường thẳng cạnh và, vì qᵧ nằm giữa hai đầu, Q nằm trên **đoạn**: hàm `onSegment` đã trả `BOUNDARY` trước đó. Vì vậy bước đổi parity chỉ cần các dấu nghiêm ngặt >0 hoặc <0.

### Giả mã even–odd đúng biên

~~~text
LOCATE_EVEN_ODD(P, Q):
    parity = 0
    for every directed edge A->B of P:
        if ON_SEGMENT(A, B, Q):
            return BOUNDARY

        up = A.y <= Q.y < B.y
        down = B.y <= Q.y < A.y

        if up and CROSS(A, B, Q) > 0:
            parity = parity XOR 1
        else if down and CROSS(A, B, Q) < 0:
            parity = parity XOR 1

    return INSIDE if parity == 1 else OUTSIDE
~~~

Ở đây `XOR 1` đảo 0→1 hoặc 1→0. Không cần lưu tổng số giao điểm nếu chỉ cần tính chẵn/lẻ.

**Điểm quan trọng:** không kiểm tra `Q.x≤x_intersection` bằng double, vì Q chính xác trên đường biên đã được xử lý trước. Ở phần parity, ta chỉ đếm **giao điểm thật sự ở bên phải** bằng dấu nguyên chính xác.

## 5. Vì sao cạnh ngang và đỉnh làm lời giải ngây thơ sai?

### 5.1. Cạnh nằm ngang trên tia

Cho hình chữ nhật có cạnh đáy y=0 và Q=(3,0). Nếu code đếm “đường ngang trùng cạnh” như nhiều giao điểm hoặc bỏ qua không kiểm tra biên, kết quả có thể thất thường.

Cách đúng:

1. Kiểm tra Q có nằm trên cạnh đáy không: có ⇒ `BOUNDARY`.
2. **Không cần** đưa Q vào bước đếm tia nữa.
3. Với Q ở y=0 nhưng **ngoài** đoạn đáy, `onSegment` false; cạnh ngang không tham gia parity, hai cạnh đứng vẫn được đếm theo quy tắc nửa mở.

### 5.2. Tia đi qua một đỉnh

Khi tia có cùng y với một đỉnh, hai cạnh kề nhau có thể cùng được xét nếu dùng điều kiện `minY≤qY≤maxY` ở cả hai phía. Khoảng **nửa mở** bảo đảm quy tắc thống nhất tại mọi đỉnh.

Đếm không đúng tại đỉnh là nguyên nhân khiến nhiều cài đặt PIP cho điểm rất gần một đỉnh kết quả không ổn định.

### 5.3. Điểm trùng đỉnh

Q=Vᵢ là **BOUNDARY** kể cả khi hai cạnh kề tạo góc lõm hay lồi. Không để phép ray casting tự quyết định trường hợp này; dùng `onSegment` ngay đầu mỗi cạnh.

### 5.4. Đỉnh lõm (reflex vertex)

Với đa giác chữ L:

~~~text
(0,6) +----+ (2,6)
      |    |
      |    |    phần bị khoét là OUTSIDE
(0,2) |    +------------> (6,2)
      |                   |
(0,0) +-------------------+ (6,0)
~~~

Tập các đỉnh có thể viết:

`[(0,0),(6,0),(6,2),(2,2),(2,6),(0,6)]`.

Điểm (4,4) nằm **trong hộp bao của toàn đa giác** nhưng **ngoài** hình chữ L. Điểm (2,2) đúng đỉnh lõm là `BOUNDARY`. Điểm (2,4) nằm trên cạnh dọc bên trong góc lõm, cũng là `BOUNDARY`.

Đây là phản ví dụ cho phương pháp chỉ kiểm tra **bounding box** của đa giác hoặc coi đa giác nào cũng lồi.

## 6. Phương pháp 2: winding number (số vòng quay)

Phương pháp **winding number** đếm các lần đường biên cắt đường ngang có hướng:

- Gặp cạnh đi lên có Q ở **bên trái** cạnh (`cross>0`): `winding++`.
- Gặp cạnh đi xuống có Q ở **bên phải** cạnh (`cross<0`): `winding--`.
- Điểm trên biên: trả `BOUNDARY` ngay.
- Kết thúc: `winding≠0` ⇒ trong; `winding=0` ⇒ ngoài.

Giả mã:

~~~text
LOCATE_WINDING(P, Q):
    winding = 0

    for every directed edge A->B:
        if ON_SEGMENT(A, B, Q): return BOUNDARY

        if A.y <= Q.y < B.y and CROSS(A,B,Q) > 0:
            winding += 1
        else if B.y <= Q.y < A.y
                and CROSS(A,B,Q) < 0:
            winding -= 1

    return INSIDE if winding != 0 else OUTSIDE
~~~

Đối với **đa giác đơn**, inside/outside từ winding và even–odd **trùng nhau**, dù chiều liệt kê đỉnh có đảo CW↔CCW. Đổi chiều làm dấu winding đảo nhưng điều kiện `winding≠0` không đổi.

Với **đường tự cắt**, hai quy tắc có thể khác:

- Even–odd: vào ra theo số giao cắt modulo 2.
- Nonzero winding: xem tổng số vòng có hướng khác 0.

Vì vậy nếu ứng dụng xử lý hình vẽ phức tạp có tự cắt, cần xác định **fill rule**. Mã bài này chỉ bảo đảm kết quả đồng nhất hai cách trên **đa giác đơn hợp lệ**.

### So sánh hai cách

| Thuộc tính | Even–odd | Winding number |
| --- | --- | --- |
| Ý tưởng | Đếm giao cắt chẵn/lẻ | Cộng/trừ theo hướng cạnh |
| Cần định hướng cross | Có, để kiểm tra giao bên phải chính xác | Có, để biết phía và dấu |
| Cần xử lý BOUNDARY riêng | Có | Có |
| Với đa giác đơn | Đúng, độc lập chiều đỉnh | Đúng, độc lập chiều đỉnh khi dùng !=0 |
| Với đường tự cắt | Quy tắc chẵn–lẻ | Quy tắc nonzero winding |
| Độ phức tạp | O(n) | O(n) |

## 7. Chứng minh tính đúng cho đa giác đơn

Giả sử P là một đường đa giác đơn khép kín, Q không nằm trên biên và các phép định hướng được tính đúng.

**Bước 1: Kiểm tra biên có tính đầy đủ.** Mọi điểm trên biên nằm trên ít nhất một cạnh kín `[Vᵢ,V_(i+1)]`. Điều kiện `onSegment` gồm thẳng hàng và nằm trong hai khoảng tọa độ nên phát hiện đúng và đủ mọi điểm như vậy. Nếu Q thỏa, trả `BOUNDARY` trước mọi phép đếm tia.

**Bước 2: Khoảng nửa mở cho số giao cắt nhất quán.** Với một tia ngang không trùng cạnh của đa giác, giao ở phần trong cạnh được xét đúng một lần. Ở cao độ bằng đỉnh, quy tắc `minY≤qY<maxY` thống nhất chọn đầu dưới và không chọn đầu trên, loại sự đếm đôi do hai cạnh kề. Các cạnh nằm ngang không làm thay đổi parity nếu Q không trên biên.

**Bước 3: Dấu cross xác định đúng phía của giao điểm.** Với cạnh không ngang thỏa điều kiện y, biểu thức cross là tích có hướng, và việc xét dấu theo hướng lên/xuống tương đương `x_intersection>q.x`; phép chia không cần thiết.

**Bước 4: Chẵn/lẻ quyết định inside/outside.** Từ một điểm rất xa bên phải, trạng thái là OUTSIDE. Với đường kín đơn, mỗi lần qua một cạnh chuyển trạng thái ngoài↔trong. Sau số lần giao cắt lẻ ta ở trong, sau số chẵn ta ở ngoài. Do đó ray casting trả đúng `INSIDE` và `OUTSIDE`.

**Bước 5: Winding cũng đúng.** Khi xét các cạnh có hướng, tổng dấu các lần vượt đường ngang biểu diễn số vòng của đường biên quanh Q. Với đa giác đơn, điểm ngoài có winding 0, còn điểm trong có winding +1 hoặc −1 theo chiều đi quanh. Vì thế dùng `winding≠0` cho cùng kết quả với parity.

**Kết luận:** với đa giác đơn hợp lệ và tọa độ nguyên, thuật toán trả đúng một trong ba trạng thái, kể cả cạnh ngang, đỉnh lõm và đảo chiều liệt kê đỉnh. Việc dùng BigInteger bảo đảm dấu cross không bị biến dạng bởi tràn số.

## 8. Hộp bao: tối ưu đúng vai trò, không phải thuật toán đầy đủ

Trước khi duyệt n cạnh, có thể lấy:

`minX,maxX,minY,maxY`.

Nếu:

`q.x<minX`, `q.x>maxX`, `q.y<minY` hoặc `q.y>maxY`,

thì Q chắc chắn nằm **ngoài** đa giác. Đây là phép loại trừ nhanh O(1) sau tiền xử lý O(n).

Nhưng **điểm bên trong bounding box chưa chắc bên trong đa giác**, đặc biệt với đa giác lõm. Ví dụ Q=(4,4) của chữ L nằm trong hộp [0,6]×[0,6] nhưng OUTSIDE.

Nếu dùng tiền xử lý bounding box, vẫn cần bước `onSegment`/ray casting cho các điểm không bị loại. Có thể tích hợp bounding box vào đối tượng Polygon để cải thiện nhiều truy vấn ở xa, nhưng không thay đổi kết luận hình học cơ bản.

## 9. Đa giác có lỗ: phân loại thêm các vòng

Một đa giác có **lỗ** thường được mô tả bằng:

- Một vòng ngoài (outer ring).
- Không hoặc nhiều vòng lỗ (hole rings) nằm hẳn trong vòng ngoài.
- Các vòng không tự cắt, không tiếp xúc/cắt nhau; lỗ không lồng nhau theo mô hình đơn giản của bài.

Một cách xác định vị trí:

1. Phân loại Q với **vòng ngoài**.
2. Nếu OUTSIDE vòng ngoài ⇒ OUTSIDE miền.
3. Nếu BOUNDARY vòng ngoài ⇒ BOUNDARY miền.
4. Nếu INSIDE vòng ngoài, kiểm tra từng lỗ:
   - Nếu BOUNDARY của lỗ ⇒ BOUNDARY của miền.
   - Nếu INSIDE lỗ ⇒ OUTSIDE của miền (vì điểm nằm trong phần bị khoét).
5. Nếu không vào lỗ nào ⇒ INSIDE.

Ví dụ:

~~~text
Outer: hình vuông [0,12] x [0,12]
Hole:  hình vuông [4,8] x [4,8]

Q=(2,2)   -> INSIDE
Q=(6,6)   -> OUTSIDE (nằm trong lỗ)
Q=(4,6)   -> BOUNDARY (cạnh lỗ)
Q=(12,6)  -> BOUNDARY (cạnh ngoài)
Q=(13,6)  -> OUTSIDE
~~~

Trong mẫu này không bắt buộc vòng lỗ liệt kê ngược hướng với vòng ngoài, vì ta **trừ miền lỗ bằng logic riêng**. Trong các định dạng GIS hay phép tô theo quy tắc nonzero, hướng ring có thể mang ý nghĩa khác; phải theo chuẩn dữ liệu đã chọn.

Đoạn Java `locateWithHoles` triển khai mô hình trên, **không** xác minh các vòng lỗ có hợp lệ, lồng nhau hay giao nhau. Nếu dữ liệu không thỏa cấu hình các lỗ rời nhau trong outer, kết quả không phải lời giải tổng quát cho đa giác tự cắt/nhiều miền.

## 10. Đa giác lồi và cách tối ưu truy vấn

Đa giác **lồi** có tính chất đường nối hai điểm bất kỳ trong miền vẫn nằm trọn trong miền. Với đa giác lồi được liệt kê nhất quán CW/CCW, có thể kiểm tra các nửa mặt phẳng bằng dấu cross:

- Với CCW, một điểm nằm trong hoặc trên biên nếu nó **không ở bên phải bất kỳ cạnh định hướng nào**.
- Với CW, đảo dấu.
- Phải tách riêng điểm trên **đoạn cạnh thực**, không chỉ trên đường thẳng kéo dài.

Duyệt mọi cạnh vẫn O(n). Nếu đa giác lồi có đỉnh theo thứ tự và có nhiều truy vấn, có thể dùng **binary search góc quạt** từ một đỉnh cố định để đạt O(log n) sau tiền xử lý phù hợp. Cách đó đòi xử lý đúng ranh giới, đoạn đầu/cuối của quạt và thứ tự hướng.

**Không áp dụng phép kiểm cùng một phía cho đa giác lõm**: ở chữ L, một điểm INSIDE có thể nằm “bên phải” một số đường kéo dài của cạnh, dù không nằm ngoài hình. Ray casting và winding xử lý được cả đa giác lõm.

## 11. Độ phức tạp, hệ tọa độ và độ ổn định số học

### Phức tạp theo số cạnh

Với đa giác n cạnh:

- Phân loại even–odd: **O(n)** phép kiểm cạnh, O(1) biến đếm.
- Phân loại winding: **O(n)** phép kiểm cạnh, O(1) biến đếm.
- Nếu lưu `List<Point>` của polygon: **O(n)** để lưu hình.
- Với h lỗ có tổng e cạnh và một outer n cạnh: **O(n+e)** cho một truy vấn trong trường hợp xấu.

Trong Java, `BigInteger` tạo một số đối tượng tạm để tính định hướng chính xác. Vì input là `long` 64 bit, hiệu tọa độ và cross có số bit bị chặn bởi hằng số (không phải số bit tùy ý không giới hạn), nên trong mô hình độ rộng cố định, mỗi định hướng có chi phí bị chặn. Nếu mở rộng sang tọa độ BigInteger độ dài tùy ý, phải tính thêm **độ phức tạp số học theo số bit**, không thể luôn gọi phép nhân là O(1).

### Khi có nhiều điểm truy vấn

Nếu có q điểm, cách quét n cạnh cho mỗi điểm mất O(qn). Có thể:

- Tiền xử lý bounding box để loại nhanh nhiều điểm ở xa.
- Dùng cấu trúc không gian (grid, spatial index, R-tree, trapezoidal decomposition/point-location structures) tùy dữ liệu và số truy vấn.
- Nếu đa giác luôn lồi, cân nhắc tìm theo quạt O(log n).

Các cấu trúc tăng tốc phải giữ nguyên chính sách BOUNDARY. Không thể bỏ kiểm tra cạnh vì “điểm có vẻ gần/xa” nếu đề đòi chính xác tuyệt đối.

### Tọa độ số thực và epsilon

Nếu dữ liệu đến từ tọa độ GPS, CAD hoặc phép giao đường thẳng, tọa độ có thể là số thực. Một phép tính cross bằng `double` có thể chịu sai số làm tròn. Khi đó cần quy định:

- Đang kiểm tra **trùng đúng về mặt toán học** hay **gần biên trong một khoảng dung sai**?
- Epsilon có đơn vị gì (tọa độ, khoảng cách đến đoạn, hay đại lượng cross có đơn vị bình phương)?
- Dung sai có phụ thuộc độ lớn tọa độ và độ dài cạnh không?
- Có cần phép định hướng **adaptive/exact predicate** thay vì `double`?

**Sai lầm:** kiểm tra `Math.abs(cross)<=1e-9` cho mọi đoạn mà không chuẩn hóa theo độ dài cạnh. Cross có độ lớn tỉ lệ với chiều dài đoạn; cùng một khoảng cách hình học có thể tạo cross rất khác.

Với điểm–đoạn số thực, cách thường dùng là khoảng cách Euclid từ Q tới đoạn AB, có hình chiếu chặn trong [0,1], rồi so với một **dung sai khoảng cách** do nghiệp vụ quy định. Với bài đếm tia, các phép định hướng gần suy biến cần quy tắc nhất quán, nếu không có thể xuất hiện nghịch lý ngay gần đỉnh.

Mã chính dùng **số nguyên chính xác**, vì vậy không áp epsilon và không đưa ra kết luận “gần biên” tùy tiện. Nếu tọa độ địa lý ở kinh/vĩ độ, phải cân nhắc **mặt cầu, đường kinh tuyến, phép chiếu, cực, đường đổi ngày**; áp đa giác phẳng trực tiếp có thể không đúng mô hình địa lý. Đây là bài toán phẳng Euclid.

## 12. Java 17+ chạy độc lập: ray casting, winding và lỗ

Lưu thành **`PointInPolygonBoundaryDemo.java`** và biên dịch trên JDK 17+.

Hợp đồng:

- `Point(long x,long y)`: một điểm nguyên.
- `Polygon`: danh sách n đỉnh của một **vòng đơn**. Có thể truyền điểm đầu lặp ở cuối; constructor bỏ bản sao cuối. Từ chối ít hơn 3 đỉnh, cạnh độ dài 0 và diện tích có hướng bằng 0. **Không kiểm tra toàn bộ self-intersection**.
- `Location`: `INSIDE` / `OUTSIDE` / `BOUNDARY`.
- `onSegment`: kiểm tra điểm trên đoạn **chính xác** bằng BigInteger.
- `locateEvenOdd` và `locateWinding`: hai cách phân loại có cùng hợp đồng.
- `locateWithHoles`: outer + danh sách lỗ rời nhau nằm bên trong outer, theo quy tắc miền bị khoét.
- `analyticRectangle`, `analyticRightTriangle`: các oracle độc lập từ bất đẳng thức hình học, không gọi hai thuật toán PIP.
- `randomCheck`: kiểm tra 300 hình chữ nhật × 50 điểm = **15.000 truy vấn**, cộng 300 tam giác vuông × 30 điểm = **9.000 truy vấn**. Mỗi trường hợp so cả even–odd và winding với oracle hình học.
- `main`: in các tình huống mẫu ở cạnh, đỉnh, đa giác lõm, chiều CW, lỗ, tọa độ cực trị long và kiểm tra input suy biến.

### Mã nguồn hoàn chỉnh

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class PointInPolygonBoundaryDemo {
    record Point(long x, long y) {}

    enum Location {
        INSIDE, OUTSIDE, BOUNDARY
    }

    static final class Polygon {
        final List<Point> vertices;

        Polygon(List<Point> input) {
            Objects.requireNonNull(input, "vertices");
            List<Point> v = new ArrayList<>(input);
            for (Point p : v) Objects.requireNonNull(p, "vertex");

            // Accept optional repeated first vertex at the end.
            if (v.size() > 1 &&
                    v.get(0).equals(v.get(v.size() - 1))) {
                v.remove(v.size() - 1);
            }
            if (v.size() < 3) {
                throw new IllegalArgumentException(
                        "At least three distinct vertices required");
            }

            BigInteger twiceArea = BigInteger.ZERO;
            for (int i = 0; i < v.size(); i++) {
                Point a = v.get(i);
                Point b = v.get((i + 1) % v.size());
                if (a.equals(b)) {
                    throw new IllegalArgumentException(
                            "Zero-length polygon edge");
                }
                twiceArea = twiceArea.add(
                        bi(a.x()).multiply(bi(b.y()))
                        .subtract(
                            bi(b.x()).multiply(bi(a.y()))));
            }
            if (twiceArea.signum() == 0) {
                throw new IllegalArgumentException(
                        "Zero signed area polygon");
            }

            // Caller must supply a SIMPLE polygon.
            // This constructor does not check every edge pair.
            vertices = List.copyOf(v);
        }
    }

    static BigInteger bi(long x) {
        return BigInteger.valueOf(x);
    }

    static Polygon polygon(long... coordinates) {
        if (coordinates.length < 6 ||
                (coordinates.length & 1) != 0) {
            throw new IllegalArgumentException(
                    "Expected at least 3 (x,y) pairs");
        }
        List<Point> points = new ArrayList<>();
        for (int i = 0; i < coordinates.length; i += 2) {
            points.add(new Point(
                    coordinates[i], coordinates[i + 1]));
        }
        return new Polygon(points);
    }

    static Polygon reverse(Polygon p) {
        List<Point> reversed = new ArrayList<>(p.vertices);
        Collections.reverse(reversed);
        return new Polygon(reversed);
    }

    static BigInteger cross(Point a, Point b, Point q) {
        BigInteger dx = bi(b.x()).subtract(bi(a.x()));
        BigInteger dy = bi(b.y()).subtract(bi(a.y()));
        BigInteger qx = bi(q.x()).subtract(bi(a.x()));
        BigInteger qy = bi(q.y()).subtract(bi(a.y()));
        return dx.multiply(qy).subtract(dy.multiply(qx));
    }

    static boolean onSegment(Point a, Point b, Point q) {
        if (cross(a, b, q).signum() != 0) return false;
        return Math.min(a.x(), b.x()) <= q.x()
                && q.x() <= Math.max(a.x(), b.x())
                && Math.min(a.y(), b.y()) <= q.y()
                && q.y() <= Math.max(a.y(), b.y());
    }

    static Location locateEvenOdd(Polygon polygon, Point q) {
        Objects.requireNonNull(q, "query");
        List<Point> v = polygon.vertices;
        int parity = 0;

        for (int i = 0; i < v.size(); i++) {
            Point a = v.get(i);
            Point b = v.get((i + 1) % v.size());

            if (onSegment(a, b, q)) return Location.BOUNDARY;

            boolean upward = a.y() <= q.y()
                    && q.y() < b.y();
            boolean downward = b.y() <= q.y()
                    && q.y() < a.y();

            if (upward || downward) {
                int sign = cross(a, b, q).signum();
                if ((upward && sign > 0) ||
                        (downward && sign < 0)) {
                    parity ^= 1;
                }
            }
        }

        return parity == 1 ? Location.INSIDE : Location.OUTSIDE;
    }

    static Location locateWinding(Polygon polygon, Point q) {
        Objects.requireNonNull(q, "query");
        List<Point> v = polygon.vertices;
        int winding = 0;

        for (int i = 0; i < v.size(); i++) {
            Point a = v.get(i);
            Point b = v.get((i + 1) % v.size());

            if (onSegment(a, b, q)) return Location.BOUNDARY;

            boolean upward = a.y() <= q.y()
                    && q.y() < b.y();
            boolean downward = b.y() <= q.y()
                    && q.y() < a.y();

            if (upward || downward) {
                int sign = cross(a, b, q).signum();
                if (upward && sign > 0) winding++;
                else if (downward && sign < 0) winding--;
            }
        }

        return winding != 0 ? Location.INSIDE
                : Location.OUTSIDE;
    }

    static Location locateWithHoles(
            Polygon outer, List<Polygon> holes, Point q) {
        Objects.requireNonNull(holes, "holes");
        Location boundaryOrOuter = locateEvenOdd(outer, q);
        if (boundaryOrOuter != Location.INSIDE)
            return boundaryOrOuter;

        for (Polygon hole : holes) {
            Location inHole = locateEvenOdd(hole, q);
            if (inHole == Location.BOUNDARY)
                return Location.BOUNDARY;
            if (inHole == Location.INSIDE)
                return Location.OUTSIDE;
        }
        return Location.INSIDE;
    }

    static boolean containsInclusive(Location location) {
        return location != Location.OUTSIDE;
    }

    static boolean containsStrict(Location location) {
        return location == Location.INSIDE;
    }

    static void show(String name, Polygon p, Point q) {
        Location parity = locateEvenOdd(p, q);
        Location winding = locateWinding(p, q);
        if (parity != winding) {
            throw new AssertionError("PIP methods disagree: " + name);
        }
        System.out.println(name + " (" + q.x() + "," + q.y()
                + ") evenOdd=" + parity
                + " winding=" + winding);
    }

    static void showRegion(
            String name, Polygon outer, Polygon hole, Point q) {
        Location actual = locateWithHoles(
                outer, List.of(hole), q);
        System.out.println(name + " (" + q.x() + "," + q.y()
                + ")=" + actual);
    }

    // Independent closed-rectangle oracle, including boundary.
    static Location analyticRectangle(
            long x0, long y0, long x1, long y1, Point q) {
        if (q.x() < x0 || q.x() > x1 ||
                q.y() < y0 || q.y() > y1) {
            return Location.OUTSIDE;
        }
        if (q.x() == x0 || q.x() == x1 ||
                q.y() == y0 || q.y() == y1) {
            return Location.BOUNDARY;
        }
        return Location.INSIDE;
    }

    // Independent oracle for triangle (0,0), (w,0), (0,h).
    // The test chooses w,h positive and small enough for long.
    static Location analyticRightTriangle(
            long w, long h, Point q) {
        if (q.x() < 0 || q.y() < 0)
            return Location.OUTSIDE;
        long weighted = q.x() * h + q.y() * w;
        long limit = w * h;
        if (weighted > limit)
            return Location.OUTSIDE;
        if (q.x() == 0 || q.y() == 0 ||
                weighted == limit) {
            return Location.BOUNDARY;
        }
        return Location.INSIDE;
    }

    static void check(
            Polygon polygon, Point q, Location expected) {
        Location parity = locateEvenOdd(polygon, q);
        Location winding = locateWinding(polygon, q);
        if (parity != expected || winding != expected) {
            throw new AssertionError("Point classification mismatch");
        }
    }

    static void randomCheck() {
        Random random = new Random(2026L);

        // Rectangle oracle: arbitrary positions and either order.
        int rectangleQueries = 0;
        for (int test = 0; test < 300; test++) {
            long x0 = random.nextInt(61) - 30L;
            long y0 = random.nextInt(61) - 30L;
            long width = 1L + random.nextInt(20);
            long height = 1L + random.nextInt(20);
            long x1 = x0 + width;
            long y1 = y0 + height;

            Polygon box = polygon(
                    x0, y0, x1, y0, x1, y1, x0, y1);
            if ((test & 1) != 0) box = reverse(box);

            for (int t = 0; t < 50; t++) {
                long x = x0 - 2L +
                        random.nextInt((int) width + 5);
                long y = y0 - 2L +
                        random.nextInt((int) height + 5);
                Point q = new Point(x, y);
                check(box, q,
                        analyticRectangle(x0, y0, x1, y1, q));
                rectangleQueries++;
            }
        }
        System.out.println("rectangleCheck=PASS ("
                + rectangleQueries + " points)");

        // Independent linear-inequality triangle oracle.
        int triangleQueries = 0;
        for (int test = 0; test < 300; test++) {
            long w = 2L + random.nextInt(30);
            long h = 2L + random.nextInt(30);
            Polygon triangle = polygon(
                    0, 0, w, 0, 0, h);
            if ((test & 1) != 0)
                triangle = reverse(triangle);

            for (int t = 0; t < 30; t++) {
                long x = -2L +
                        random.nextInt((int) w + 5);
                long y = -2L +
                        random.nextInt((int) h + 5);
                Point q = new Point(x, y);
                check(triangle, q,
                        analyticRightTriangle(w, h, q));
                triangleQueries++;
            }
        }
        System.out.println("triangleCheck=PASS ("
                + triangleQueries + " points)");
    }

    public static void main(String[] args) {
        Polygon rectangle = polygon(
                0, 0, 8, 0, 8, 6, 0, 6);

        show("rectInside", rectangle, new Point(3, 2));
        show("rectOutside", rectangle, new Point(9, 2));
        show("rectRightEdge", rectangle, new Point(8, 3));
        show("rectVertex", rectangle, new Point(0, 0));
        show("rectTopEdge", rectangle, new Point(3, 6));
        show("rectNearTopInside",
                rectangle, new Point(3, 5));
        show("rectNearTopOutside",
                rectangle, new Point(3, 7));
        show("rectBottomEdge", rectangle, new Point(3, 0));
        show("rectLeftOutside",
                rectangle, new Point(-1, 0));

        Polygon concave = polygon(
                0, 0, 6, 0, 6, 2, 2, 2, 2, 6, 0, 6);
        show("concaveLeft", concave, new Point(1, 5));
        show("concaveBottom", concave, new Point(5, 1));
        show("concaveNotch", concave, new Point(4, 4));
        show("concaveReflexVertex",
                concave, new Point(2, 2));
        show("concaveVerticalEdge",
                concave, new Point(2, 4));
        show("concaveHorizontalEdge",
                concave, new Point(4, 2));

        Polygon triangle = polygon(0, 0, 6, 0, 3, 6);
        show("triangleInside", triangle, new Point(3, 2));
        show("triangleSlopeEdge",
                triangle, new Point(1, 2));
        show("triangleTop", triangle, new Point(3, 6));
        show("triangleOutside",
                triangle, new Point(6, 6));

        Polygon cw = reverse(rectangle);
        show("clockwiseInside", cw, new Point(3, 2));
        show("clockwiseEdge", cw, new Point(8, 3));

        Polygon outer = polygon(
                0, 0, 12, 0, 12, 12, 0, 12);
        Polygon hole = polygon(4, 4, 8, 4, 8, 8, 4, 8);
        showRegion("regionCore",
                outer, hole, new Point(2, 2));
        showRegion("regionHole",
                outer, hole, new Point(6, 6));
        showRegion("regionHoleEdge",
                outer, hole, new Point(4, 6));
        showRegion("regionHoleVertex",
                outer, hole, new Point(4, 4));
        showRegion("regionOuterEdge",
                outer, hole, new Point(12, 6));
        showRegion("regionOutside",
                outer, hole, new Point(13, 6));

        Polygon extreme = polygon(
                Long.MIN_VALUE, Long.MIN_VALUE,
                Long.MAX_VALUE, Long.MIN_VALUE,
                Long.MAX_VALUE, Long.MAX_VALUE,
                Long.MIN_VALUE, Long.MAX_VALUE);
        show("extremeCenter", extreme, new Point(0, 0));
        show("extremeCorner", extreme,
                new Point(Long.MIN_VALUE, Long.MIN_VALUE));
        System.out.println("extremeCrossBits="
                + cross(
                    extreme.vertices.get(0),
                    extreme.vertices.get(1),
                    extreme.vertices.get(2)).bitLength());

        Location boundary =
                locateEvenOdd(rectangle, new Point(8, 3));
        System.out.println("boundaryPolicy inclusive="
                + containsInclusive(boundary)
                + " strict=" + containsStrict(boundary));

        // Optional duplicated closing vertex is accepted.
        Polygon closed = polygon(
                0, 0, 8, 0, 8, 6, 0, 6, 0, 0);
        check(closed, new Point(3, 2), Location.INSIDE);
        System.out.println("closedRing=PASS");

        try {
            polygon(0, 0, 1, 1, 2, 2);
            throw new AssertionError(
                    "Collinear polygon must be rejected");
        } catch (IllegalArgumentException expected) {
            System.out.println("collinearRing=rejected");
        }

        try {
            polygon(0, 0, 2, 0, 2, 0, 0, 2);
            throw new AssertionError(
                    "Zero-length edge must be rejected");
        } catch (IllegalArgumentException expected) {
            System.out.println("duplicateEdge=rejected");
        }

        randomCheck();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 PointInPolygonBoundaryDemo.java
java PointInPolygonBoundaryDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
rectInside (3,2) evenOdd=INSIDE winding=INSIDE
rectOutside (9,2) evenOdd=OUTSIDE winding=OUTSIDE
rectRightEdge (8,3) evenOdd=BOUNDARY winding=BOUNDARY
rectVertex (0,0) evenOdd=BOUNDARY winding=BOUNDARY
rectTopEdge (3,6) evenOdd=BOUNDARY winding=BOUNDARY
rectNearTopInside (3,5) evenOdd=INSIDE winding=INSIDE
rectNearTopOutside (3,7) evenOdd=OUTSIDE winding=OUTSIDE
rectBottomEdge (3,0) evenOdd=BOUNDARY winding=BOUNDARY
rectLeftOutside (-1,0) evenOdd=OUTSIDE winding=OUTSIDE
concaveLeft (1,5) evenOdd=INSIDE winding=INSIDE
concaveBottom (5,1) evenOdd=INSIDE winding=INSIDE
concaveNotch (4,4) evenOdd=OUTSIDE winding=OUTSIDE
concaveReflexVertex (2,2) evenOdd=BOUNDARY winding=BOUNDARY
concaveVerticalEdge (2,4) evenOdd=BOUNDARY winding=BOUNDARY
concaveHorizontalEdge (4,2) evenOdd=BOUNDARY winding=BOUNDARY
triangleInside (3,2) evenOdd=INSIDE winding=INSIDE
triangleSlopeEdge (1,2) evenOdd=BOUNDARY winding=BOUNDARY
triangleTop (3,6) evenOdd=BOUNDARY winding=BOUNDARY
triangleOutside (6,6) evenOdd=OUTSIDE winding=OUTSIDE
clockwiseInside (3,2) evenOdd=INSIDE winding=INSIDE
clockwiseEdge (8,3) evenOdd=BOUNDARY winding=BOUNDARY
regionCore (2,2)=INSIDE
regionHole (6,6)=OUTSIDE
regionHoleEdge (4,6)=BOUNDARY
regionHoleVertex (4,4)=BOUNDARY
regionOuterEdge (12,6)=BOUNDARY
regionOutside (13,6)=OUTSIDE
extremeCenter (0,0) evenOdd=INSIDE winding=INSIDE
extremeCorner (-9223372036854775808,-9223372036854775808) evenOdd=BOUNDARY winding=BOUNDARY
extremeCrossBits=128
boundaryPolicy inclusive=true strict=false
closedRing=PASS
collinearRing=rejected
duplicateEdge=rejected
rectangleCheck=PASS (15000 points)
triangleCheck=PASS (9000 points)
~~~

### Diễn giải kết quả

**rectInside / rectOutside:** tia sang phải lần lượt cắt một cạnh hoặc không cắt cạnh nào; cả hai thuật toán cùng kết luận.

**rectRightEdge / rectVertex / rectTopEdge / rectBottomEdge:** điểm trên cạnh đứng, cạnh ngang hoặc trùng một đỉnh phải là **BOUNDARY**, không được phụ thuộc vào cách đếm tia.

**rectNearTopInside / rectNearTopOutside:** thay đổi y một đơn vị quanh cạnh trên làm kết quả chuyển từ INSIDE sang OUTSIDE; điểm đúng trên y=6 mới là BOUNDARY.

**rectLeftOutside:** tuy Q có y trùng cạnh đáy kéo dài nhưng x ngoài đoạn [0,8], kết quả là OUTSIDE. Đây là test cho lỗi “cross=0 là trên cạnh” mà không kiểm tra bounding box của đoạn.

**concaveLeft / concaveBottom:** hai vùng của chữ L đều được nhận diện là INSIDE.

**concaveNotch:** Q=(4,4) nằm trong bounding box của chữ L nhưng nằm ngoài hình thực, vì vậy OUTSIDE.

**concaveReflexVertex / concaveVerticalEdge / concaveHorizontalEdge:** đỉnh lõm và hai cạnh tạo phần lõm đều được gắn nhãn BOUNDARY.

**triangleSlopeEdge:** Q=(1,2) nằm đúng trên cạnh dốc từ (0,0) tới (3,6), nên BOUNDARY; không thể chỉ kiểm tra cạnh ngang/dọc.

**clockwiseInside / clockwiseEdge:** đảo thứ tự đỉnh không làm thay đổi vị trí hình học hay kết quả phân loại.

**regionCore / regionHole:** điểm trong vòng ngoài nhưng trong lỗ phải bị xem là OUTSIDE; điểm nằm trên ranh giới lỗ là BOUNDARY.

**extremeCenter / extremeCorner:** đúng với các tọa độ sát `Long.MIN_VALUE` và `Long.MAX_VALUE`; `BigInteger` ngăn tràn hiệu tọa độ. Giá trị cross của ba đỉnh đầu có **128 bit**, lớn hơn hẳn khả năng của signed long.

**boundaryPolicy:** trạng thái BOUNDARY được chuyển thành true theo chính sách **inclusive** và false theo **strict**.

**closedRing:** chương trình chấp nhận vòng có lặp điểm đầu ở cuối bằng cách bỏ phần tử cuối dư trước khi kiểm tra cạnh.

**collinearRing / duplicateEdge:** từ chối đa giác toàn thẳng hàng hoặc có cạnh độ dài 0; không giả vờ gọi những trường hợp suy biến đó là miền 2D hợp lệ.

**rectangleCheck / triangleCheck:** 24.000 truy vấn được so với hai bộ điều kiện hình học độc lập: hình chữ nhật dùng giới hạn x/y; tam giác vuông dùng bất đẳng thức tuyến tính của cạnh huyền. Cả even–odd và winding đều phải trùng với oracle trên mỗi điểm. Bộ test cố ý đảo CW/CCW và chứa điểm ở bên trong, bên ngoài, trên các cạnh.

### Phạm vi xác minh

Kiểm tra ngẫu nhiên giúp phát hiện lỗi ở phép xét điều kiện y nửa mở, dấu cross, xử lý đỉnh, chiều đỉnh và trường hợp biên. Tuy nhiên, bộ test không chứng minh chương trình hỗ trợ đa giác tự cắt, các vòng lỗ không hợp lệ, hay hình học trên mặt cầu. Những trường hợp đó nằm **ngoài hợp đồng** đã công bố.

## 13. Lỗi triển khai thường gặp

1. Chỉ trả boolean mà không ghi rõ điểm trên cạnh được tính trong hay ngoài.
2. Kiểm tra bounding box rồi kết luận ngay INSIDE cho mọi điểm nằm trong hộp.
3. Quên kiểm tra điểm trên đoạn trước khi đếm giao cắt.
4. Kiểm tra `cross=0` rồi trả BOUNDARY dù Q nằm ngoài đoạn kéo dài.
5. Quên cạnh đóng từ đỉnh cuối về đỉnh đầu.
6. Dùng cả hai đầu mút y theo khoảng đóng, làm đếm hai lần tại đỉnh.
7. Dùng cả hai đầu mút y theo khoảng mở, bỏ giao cắt cần thiết tại đỉnh.
8. Tính x giao điểm bằng chia nguyên, làm tròn và đổi sai parity.
9. Tính x giao điểm bằng double rồi coi là chính xác tuyệt đối với tọa độ long lớn.
10. Đếm một giao điểm nằm bên **trái** Q như nằm bên phải.
11. Dùng cùng dấu cross cho cạnh đi lên và đi xuống.
12. Để cạnh ngang tham gia parity dù Q không trên biên.
13. Bỏ qua cạnh ngang khi kiểm tra BOUNDARY.
14. Quên kiểm tra điểm trùng đỉnh chính xác.
15. Coi đỉnh lõm là trường hợp ngoài hình nếu Q nằm đúng tại đó.
16. Cho rằng mọi điểm trong bounding box của đa giác lõm đều INSIDE.
17. Áp dụng kiểm tra nửa mặt phẳng của đa giác lồi lên một đa giác lõm.
18. Không kiểm tra CW/CCW và giả định winding luôn dương.
19. Dùng `winding>0` thay cho `winding!=0` rồi sai với polygon CW.
20. Coi even–odd và nonzero winding luôn tương đương trên mọi đường tự cắt.
21. Coi đoạn có hai điểm trùng nhau là cạnh hợp lệ để tính biên mà không xác định chính sách.
22. Chấp nhận n<3 làm đa giác có diện tích không rỗng.
23. Chỉ kiểm tra diện tích có hướng khác 0 rồi khẳng định đã chứng minh đa giác đơn.
24. Nhân cross bằng `int`, làm tràn ngay trên tọa độ trung bình.
25. Nhân cross bằng `long` nhưng quên hiệu tọa độ long có thể tràn **trước** phép nhân.
26. Trộn epsilon tùy tiện với điều kiện đúng tuyệt đối mà không đặt thước đo khoảng cách.
27. Dùng `abs(cross)<=epsilon` cố định cho mọi đoạn dù đơn vị cross phụ thuộc chiều dài.
28. Lẫn hệ tọa độ phẳng với kinh/vĩ độ trên mặt cầu.
29. Chỉ kiểm tra cạnh ngoài khi miền có lỗ, dẫn tới nhận sai điểm trong lỗ.
30. Tự động lấy hướng của vòng lỗ để suy ra thuộc miền mà không biết quy tắc fill của định dạng.
31. Không phân biệt điểm **trên biên lỗ** với điểm **trong lỗ**.
32. Dùng hình chữ nhật làm mọi test và không thử chữ L lõm.
33. Chỉ test điểm ở xa cạnh, không test đúng cạnh ngang/đứng và đỉnh.
34. Chỉ test chiều CCW, không đảo CW.
35. Dựa vào một bộ random seed mà không có ví dụ biên xác định.
36. Không kiểm tra tọa độ âm hoặc cực trị kiểu dữ liệu.
37. Không chuẩn hóa hoặc không xử lý dữ liệu đầu vào trùng điểm đầu cuối theo quy ước.
38. Dùng một chỉ số đỉnh sai khiến bỏ cạnh cuối hoặc đọc ngoài danh sách.
39. Xét số tia cắt từ điểm trên biên mà bỏ qua phân loại trước, làm kết quả phụ thuộc quy ước giao.
40. Gắn nhãn INSIDE/OUTSIDE cho dữ liệu tự cắt mà không xác định fill rule.

## 14. Bài tập có lời giải

**Bài 1.** Trên hình chữ nhật `[0,8]×[0,6]`, Q=(3,2) thuộc đâu? **Đáp án:** INSIDE.

**Bài 2.** Cùng hình, Q=(8,3)? **Đáp án:** BOUNDARY vì nằm trên cạnh phải.

**Bài 3.** Q=(0,0) nằm đâu? **Đáp án:** BOUNDARY vì trùng một đỉnh.

**Bài 4.** Q=(9,2) thuộc đâu? **Đáp án:** OUTSIDE.

**Bài 5.** Q=(3,6) thuộc đâu? **Đáp án:** BOUNDARY trên cạnh ngang phía trên.

**Bài 6.** Q=(-1,0) có cross=0 với đường thẳng đáy, có trên đoạn đáy không? **Đáp án:** không, vì x ngoài đoạn [0,8]; OUTSIDE.

**Bài 7.** Công thức định hướng của A,B,Q? **Đáp án:** `(bₓ−aₓ)(qᵧ−aᵧ)−(bᵧ−aᵧ)(qₓ−aₓ)`.

**Bài 8.** Cross bằng 0 có đủ để kết luận onSegment? **Đáp án:** không, phải kiểm tra q trong bounding box của đoạn.

**Bài 9.** Vì sao cần xử lý BOUNDARY trước ray casting? **Đáp án:** tia đi qua chính điểm nằm trên biên không có định nghĩa chẵn/lẻ ổn định theo cách đếm giao; kiểm tra đoạn là chính xác.

**Bài 10.** Điều kiện y của cạnh đi lên? **Đáp án:** `aᵧ≤qᵧ<bᵧ`.

**Bài 11.** Điều kiện y của cạnh đi xuống? **Đáp án:** `bᵧ≤qᵧ<aᵧ`.

**Bài 12.** Vì sao điều kiện nửa mở có ý nghĩa? **Đáp án:** tránh đếm hai lần giao tại một đỉnh chung.

**Bài 13.** Với cạnh đi lên, Q ở trái cạnh, giao tia ở đâu? **Đáp án:** ở phía phải Q nếu cao độ nằm trong khoảng nửa mở; điều kiện cross>0.

**Bài 14.** Với cạnh đi xuống, giao tia ở bên phải Q khi cross có dấu nào? **Đáp án:** âm (cross<0).

**Bài 15.** Cạnh ngang có được dùng để đảo parity không? **Đáp án:** không; nhưng vẫn phải xét Q trên cạnh để trả BOUNDARY.

**Bài 16.** Tia có 5 giao cắt hợp lệ bên phải Q, kết quả? **Đáp án:** INSIDE vì 5 lẻ.

**Bài 17.** Tia có 4 giao cắt hợp lệ bên phải Q, kết quả? **Đáp án:** OUTSIDE vì 4 chẵn.

**Bài 18.** Với chữ L gồm các đỉnh đã nêu, Q=(4,4)? **Đáp án:** OUTSIDE vì nằm trong góc bị khoét, dù trong bounding box.

**Bài 19.** Với chữ L, Q=(2,2)? **Đáp án:** BOUNDARY vì trùng đỉnh lõm.

**Bài 20.** Với chữ L, Q=(2,4)? **Đáp án:** BOUNDARY trên cạnh dọc tạo phần lõm.

**Bài 21.** Với tam giác [(0,0),(6,0),(3,6)], Q=(1,2)? **Đáp án:** BOUNDARY, nằm trên cạnh từ (0,0) đến (3,6).

**Bài 22.** Đảo thứ tự đỉnh hình chữ nhật có làm INSIDE thành OUTSIDE không? **Đáp án:** không với even–odd và winding!=0 trên đa giác đơn.

**Bài 23.** Với winding=-1 và Q không trên biên, kết luận? **Đáp án:** INSIDE vì winding khác 0.

**Bài 24.** Winding=0 và Q không trên biên? **Đáp án:** OUTSIDE.

**Bài 25.** Vì sao hai quy tắc có thể khác trên đường tự cắt? **Đáp án:** even–odd dùng parity, winding dùng tổng số vòng có hướng; hình tự cắt cần fill rule xác định.

**Bài 26.** Outer=[0,12]×[0,12], hole=[4,8]×[4,8]; Q=(6,6)? **Đáp án:** OUTSIDE của miền vì nằm trong lỗ.

**Bài 27.** Cùng miền, Q=(4,6)? **Đáp án:** BOUNDARY vì trên biên lỗ.

**Bài 28.** Cùng miền, Q=(2,2)? **Đáp án:** INSIDE.

**Bài 29.** Chính sách inclusive đối với Q trên biên trả boolean gì? **Đáp án:** true.

**Bài 30.** Chính sách strict đối với Q trên biên trả boolean gì? **Đáp án:** false.

**Bài 31.** Số cạnh n, một truy vấn PIP mất bao lâu? **Đáp án:** O(n) lần kiểm cạnh.

**Bài 32.** Có q truy vấn cùng đa giác, duyệt tuần tự mất bao nhiêu? **Đáp án:** O(qn) trước các tối ưu tiền xử lý.

**Bài 33.** Vì sao phép trừ hai `long` trong cross có thể tràn? **Đáp án:** hiệu `Long.MAX_VALUE−Long.MIN_VALUE` vượt phạm vi signed 64-bit.

**Bài 34.** Cách bảo đảm dấu cross chính xác với tọa độ long? **Đáp án:** chuyển từng tọa độ sang BigInteger **trước khi trừ**, sau đó nhân/trừ BigInteger.

**Bài 35.** Chỉ kiểm tra diện tích có hướng khác 0 đủ chứng minh polygon đơn? **Đáp án:** không; còn cần loại tự cắt, giao cạnh không hợp lệ và các suy biến khác.

**Bài 36.** Vì sao không nên dùng `Math.abs(cross)<=1e-9` để kiểm tra gần biên cho mọi cạnh? **Đáp án:** cross phụ thuộc chiều dài cạnh và hệ đơn vị; nên dùng chính sách khoảng cách/dung sai thích hợp hoặc predicate chính xác.

**Bài 37.** Đa giác lồi có nhiều truy vấn có thể tăng tốc bằng cách nào? **Đáp án:** sắp đỉnh theo chu vi và binary search quạt từ một đỉnh cố định, xử lý biên đúng, O(log n) mỗi truy vấn.

**Bài 38.** Một vòng đa giác khép kín lặp V₀ ở cuối có cần tạo cạnh độ dài 0 không? **Đáp án:** không; chuẩn hóa bằng bỏ phần tử cuối dư trước khi tạo các cạnh chu kỳ.

## 15. Checklist triển khai

1. **Input** đã là đa giác đơn, hay có thể tự cắt/có lỗ?
2. **Đầu ra** cần ba trạng thái hay boolean? Nếu boolean, biên tính trong hay ngoài?
3. Đã làm rõ **tọa độ nguyên, thực, phẳng hay địa lý**?
4. Có đoạn/cạnh nào dài 0 hoặc số đỉnh ít hơn 3 không?
5. Có xử lý đúng cạnh từ **đỉnh cuối về đỉnh đầu**?
6. Có kiểm tra điểm đúng **trên đoạn** trước đếm tia?
7. OnSegment đã kết hợp **cross=0 và bounding box đoạn**?
8. Có tránh overflow ở hiệu tọa độ và tích cross không?
9. Cạnh đi lên có dùng `a.y≤q.y<b.y`?
10. Cạnh đi xuống có dùng `b.y≤q.y<a.y`?
11. Cạnh ngang có bị loại khỏi **parity** nhưng vẫn được xét **BOUNDARY**?
12. Có đếm **chỉ giao điểm ở bên phải Q**, không tính bên trái?
13. Có dùng đúng dấu cross cho mỗi hướng cạnh?
14. Đã thử cạnh ngang, cạnh dọc, cạnh dốc và điểm trùng đỉnh?
15. Đã thử **đa giác lõm**, đặc biệt điểm trong bounding box nhưng OUTSIDE?
16. Đã thử cả đỉnh CW và CCW, bảo đảm kết quả vị trí không đổi?
17. Nếu dùng winding, có xét `winding!=0` thay vì `winding>0`?
18. Nếu có lỗ, đã kiểm tra biên lỗ và tách lỗ khỏi outer?
19. Nếu tự cắt có thể xảy ra, đã xác định even–odd/nonzero fill rule và validate hình?
20. Nếu có epsilon, đã xác định **dung sai theo khoảng cách/đơn vị**, không chỉ abs(cross) ngẫu nhiên?
21. Có test tọa độ âm, số lớn gần giới hạn và mọi kiểu biên?
22. Có kiểm thử bằng oracle khác cách đếm tia, ví dụ hình chữ nhật/tam giác với bất đẳng thức trực tiếp?
23. Với nhiều truy vấn, đã đánh giá O(qn), bounding box, spatial index hoặc thuật toán lồi O(log n)?
24. Có phân biệt việc **kiểm tra hợp lệ của đa giác** với **phân loại một điểm**? Hai bài toán khác nhau.

**Ghi nhớ:** để kiểm tra điểm trong đa giác chính xác, thứ tự quan trọng nhất là **(1) thử BOUNDARY bằng cross và giới hạn đoạn; (2) đếm tia với điều kiện y nửa mở; (3) dùng dấu cross thay phép chia giao điểm; (4) diễn giải parity hoặc winding**. Cả hai phương pháp đúng O(n) với đa giác đơn lồi hoặc lõm. Đối với dữ liệu nguyên `long`, hãy tính định hướng bằng **BigInteger** khi muốn bảo đảm không tràn trên toàn miền; nếu miền có lỗ hay đường tự cắt, cần mô hình vùng và quy tắc tô phù hợp.
