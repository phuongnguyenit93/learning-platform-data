# Quét mặt phẳng và quản lý sự kiện hình học

**Quét mặt phẳng** (*plane sweep*, *sweep line*) là một tư duy thiết kế thuật toán hình học: thay vì kiểm tra tất cả các cặp đối tượng trên toàn mặt phẳng, ta tưởng tượng một **đường quét** chuyển động theo một hướng, thường từ trái sang phải theo trục x. Khi đường quét đi qua những vị trí quan trọng, ta cập nhật một **trạng thái hoạt động** (*active set, sweep-line status*) và tính kết quả dựa trên trạng thái hiện tại.

Trọng tâm của kỹ thuật không phải “vẽ một đường thẳng”, mà là quản lý chính xác ba thành phần:

1. **Sự kiện (events):** những tọa độ mà quan hệ hình học có thể thay đổi, như cạnh bắt đầu/kết thúc, một điểm cần truy vấn hay giao điểm mới.
2. **Thứ tự xử lý sự kiện:** sắp theo tọa độ quét và giải quyết những sự kiện **cùng tọa độ** theo quy tắc phù hợp với biên đóng/mở của bài toán.
3. **Trạng thái đang hoạt động:** tập đối tượng giao với đường quét hoặc một cấu trúc tổng hợp của chúng; có thể dùng biến đếm, tập cân bằng, Fenwick tree, segment tree hoặc cấu trúc hình học chuyên biệt.

Khi dùng đúng, plane sweep thường biến một bài kiểm tra mọi cặp O(n²) thành O(n log n), hoặc giúp cộng diện tích hình học mà không phải duyệt từng ô trên mặt phẳng.

Bài học trình bày quy trình thiết kế sự kiện, các bất biến và quy tắc đồng tọa độ, sau đó đi sâu vào **diện tích hợp của các hình chữ nhật song song trục** bằng **quét theo x + nén y + segment tree lưu chiều dài được phủ**, một ví dụ kinh điển O(n log n). Có chương trình **Java 17+ đầy đủ**, kết quả chạy xác định, phép kiểm độc lập bằng lưới nhỏ, bài toán phụ đếm số khoảng hoạt động, lưu ý về số nguyên lớn, giao cắt đoạn thẳng và các câu hỏi tự luyện.

## 1. Trực giác: thay bài toán hai chiều bằng một chuỗi sự kiện

Giả sử có nhiều hình chữ nhật nằm trên hệ trục Oxy. Nếu muốn tính **diện tích hợp**, cách ngây thơ là duyệt từng điểm/ô rồi xem có thuộc ít nhất một hình hay không. Cách này không khả thi nếu tọa độ lớn tới hàng tỷ hoặc không nguyên.

Quan sát: khi đường thẳng đứng `x = const` trượt từ trái sang phải, tập hình chữ nhật **đang cắt đường quét** chỉ thay đổi tại các tọa độ x của **cạnh trái hoặc cạnh phải**. Giữa hai tọa độ sự kiện liên tiếp, không có hình nào bắt đầu hoặc kết thúc, nên **độ dài hợp được phủ trên trục y không đổi**.

Nếu các sự kiện ở:

\[
x_0<x_1<\cdots<x_k,
\]

và \(coveredY_i\) là chiều dài hợp các đoạn y đang hoạt động trên dải \([x_i,x_{i+1})\), diện tích là:

\[
\boxed{
Area=\sum_{i=0}^{k-1}(x_{i+1}-x_i)\,coveredY_i.
}
\]

Bài toán hai chiều đã trở thành:

- Sắp xếp các mốc x.
- Khi hình chữ nhật “vào” hoặc “ra”, cập nhật một đoạn y.
- Sau mỗi nhóm sự kiện x, biết nhanh **tổng chiều dài hợp trên y**.

Đây là khung thuật toán quét mặt phẳng.

## 2. Sự kiện hình học là gì?

Một **sự kiện** không nhất thiết là một điểm trong tập input; đó là **thời điểm theo tọa độ quét mà trạng thái cần cập nhật hoặc kết quả cần quan sát**.

Ví dụ:

| Bài toán | Tọa độ quét | Những sự kiện điển hình | Trạng thái |
|---|---|---|---|
| Số đoạn thời gian chồng lấn lớn nhất | thời gian t | bắt đầu/kết thúc | biến đếm |
| Diện tích hợp hình chữ nhật | x | cạnh trái/cạnh phải | hợp các khoảng y |
| Trả lời số điểm trong hình chữ nhật | x | thêm điểm, truy vấn tiền tố | Fenwick/segment tree theo y |
| Phát hiện giao nhau của đoạn thẳng | x | đầu mút, giao điểm | trật tự các đoạn tại đường quét |
| Tìm cặp điểm gần nhất trong mặt phẳng | x | thêm/bỏ điểm trong dải ứng viên | tập điểm theo y |
| Đếm cặp thỏa điều kiện tọa độ | x hoặc y | thêm, loại, truy vấn | Fenwick, multiset hoặc cây cân bằng |

Không có một cấu trúc dữ liệu duy nhất đúng cho mọi bài toán sweep. Ta chọn cấu trúc dựa trên **trạng thái cần truy vấn**.

### Event queue và active status là hai thứ khác nhau

**Event queue** là thứ tự **sự kiện sẽ xảy ra**, thường được sắp theo x (và các khóa phụ). Với các event biết trước, có thể lưu trong mảng rồi sort. Nếu trong quá trình quét có thể phát hiện **giao điểm mới** cần xử lý ở x tương lai, ta cần cấu trúc thêm sự kiện động, chẳng hạn priority queue.

**Active status** là thông tin **đang đúng tại vị trí đường quét hiện tại**. Nó phải hỗ trợ cập nhật và trả câu hỏi của bài toán: số khoảng đang mở, hợp chiều dài y, vị trí kề nhau của các đoạn cắt đường quét, v.v.

Một hàng đợi sự kiện được sort đúng **không đủ** để thuật toán chạy nhanh; còn phải chọn cấu trúc trạng thái có thao tác update/query phù hợp.

## 3. Quy trình thiết kế một thuật toán plane sweep

Một cách làm có hệ thống gồm sáu bước:

**Bước 1 — Chọn trục và chiều quét.** Thường từ x nhỏ tới x lớn. Có bài đổi vai trò x/y hoặc quét theo thời gian.

**Bước 2 — Xác định tất cả loại sự kiện.** Ví dụ hình chữ nhật có `ENTER` ở cạnh trái và `EXIT` ở cạnh phải; truy vấn point-in-rectangle có `QUERY`.

**Bước 3 — Cố định ý nghĩa active tại thời điểm t.** Đang xét phía **trước t**, **sau t**, hay chính **t**? Nếu hình chữ nhật được biểu diễn bằng khoảng nửa mở, trạng thái sau nhóm event x là tập hình cắt mọi dải \([x,x_{next})\).

**Bước 4 — Xác định thứ tự khi đồng tọa độ.** Những event có cùng x có thể cần xử lý theo nhóm hoặc theo một loại thứ tự nhất quán. Điều này quan trọng cho số lần chồng lấn, số giao điểm tại biên và truy vấn.

**Bước 5 — Duy trì bất biến và truy vấn kết quả.** Ví dụ diện tích hợp: sau khi xử lý toàn bộ event tại x, segment tree phải lưu đúng chiều dài hợp y cho dải ngay bên phải x.

**Bước 6 — Tính độ phức tạp theo cả sort và update/query.** Nếu có E events và mỗi update O(log n), tổng thường O(E log E + E log n). Không mặc nhiên nói O(n log n) nếu trạng thái cần kiểm lại tất cả các đối tượng ở mỗi event.

### Một bất biến tổng quát

Sau khi xử lý các sự kiện ở tọa độ x, **trạng thái hoạt động phải bằng chính xác những đối tượng có ảnh hưởng tới các vị trí ngay sau x**.

Bất biến này là lý do nhiều thuật toán sắp xếp/nhóm các sự kiện đồng x và chỉ tính đại lượng cần thiết **sau khi cả nhóm đã cập nhật**.

## 4. Điểm dễ sai nhất: sự kiện cùng tọa độ

Giả sử các khoảng thời gian đều dùng quy ước **nửa mở \([start,end)\)**:

~~~text
A = [1,3)
B = [3,5)

time: 1---2---3---4---5
A:    [=======)
B:            [=======)
~~~

A và B **không** hoạt động đồng thời tại bất kỳ thời điểm nào: A kết thúc đúng lúc B bắt đầu.

Nếu dùng mảng sự kiện:

~~~text
A start: (1,+1)
A end:   (3,-1)
B start: (3,+1)
B end:   (5,-1)
~~~

thì ở t=3 cần tính đúng trạng thái. Nếu cập nhật và **đo max sau từng event**, quy tắc an toàn với khoảng nửa mở là:

\[
\boxed{\text{Tại cùng t: END (-1) trước START (+1).}}
\]

Nếu START trước END, bộ đếm tạm thời có thể tăng thành 2, trả sai “số đoạn chồng lấn tối đa” là 2 thay vì 1.

### Nếu khoảng đóng [start,end] thì sao?

Đối với khoảng **đóng**, hai đoạn \([1,3]\) và \([3,5]\) cùng chứa điểm 3. Nếu muốn đếm số đoạn cùng phủ một điểm t, START phải được coi là có hiệu lực **trước khi xử lý END tại cùng t**:

\[
\boxed{\text{Khoảng đóng: START trước END khi đo tại t.}}
\]

Một cách khác là **gom tất cả event cùng tọa độ**, áp dụng chính sách “trước/sau/đúng tại điểm” rồi đo trạng thái tại giai đoạn phù hợp. Không có thứ tự tie-break cố định đúng cho tất cả bài toán hình học.

### Đo diện tích hợp hình chữ nhật khác bài đếm thời điểm

Với diện tích, ta cộng diện tích trên **dải giữa hai x khác nhau**. Mọi event cùng x nằm trên một đường có **bề rộng 0**, vì vậy không tạo diện tích mới ngay tại x. Ta có thể:

1. Cộng diện tích dải \([previousX,x)\) bằng trạng thái **trước event x**.
2. Áp dụng **tất cả event ở x**.
3. Chuyển `previousX=x`, tiếp tục.

Thứ tự nội bộ cùng x **không ảnh hưởng kết quả diện tích** nếu trạng thái cuối nhóm đúng và không tính diện tích giữa các event đồng x. Mã Java chọn **ENTER trước EXIT** để trật tự xác định, nhưng phép cộng diện tích chỉ diễn ra **một lần cho cả nhóm**.

## 5. Các hình chữ nhật song song trục và quy ước biên

Một hình chữ nhật được biểu diễn bằng:

\[
\boxed{[x_1,x_2)\times[y_1,y_2)}
\]

với:

\[
x_1<x_2,\qquad y_1<y_2.
\]

Theo quy ước nửa mở:

- Biên trái và biên dưới thuộc hình.
- Biên phải và biên trên là biên loại trừ.
- Hai hình chỉ **chạm cạnh** nhưng không chồng diện tích.
- Độ rộng = x2−x1, độ cao = y2−y1.

Đối với **diện tích**, việc đóng/mở một cạnh đơn lẻ không thay đổi độ đo diện tích. Nhưng dùng nửa mở giúp biểu diễn dải và mảng nén tọa độ rõ ràng, tránh lỗi đếm hai lần ở ranh giới.

Bài dùng **hình chữ nhật có diện tích dương** và từ chối x1≥x2 hoặc y1≥y2. Nếu đề cho phép hình suy biến (đoạn thẳng/điểm), cần quy định rõ có loại bỏ chúng hay xét các đại lượng khác ngoài diện tích.

### Cặp hình ví dụ

Hình A:

\[
[1,4)\times[1,4),\quad area(A)=3\cdot3=9.
\]

Hình B:

\[
[3,6)\times[2,5),\quad area(B)=3\cdot3=9.
\]

Phần giao là:

\[
[3,4)\times[2,4),
\]

có diện tích 1·2=2. Vậy diện tích hợp:

\[
\boxed{area(A\cup B)=9+9-2=16}.
\]

Manh mối của sweep line là chỉ cần xét các tọa độ x: **1,3,4,6**.

## 6. Sự kiện của một hình chữ nhật

Mỗi hình chữ nhật \([x_1,x_2)\times[y_1,y_2)\) tạo đúng hai event:

~~~text
(x1, y1, y2, +1)   // ENTER
(x2, y1, y2, -1)   // EXIT
~~~

Trong đó `+1` nghĩa là thêm đoạn y=[y1,y2) vào tập các đoạn đang hoạt động; `-1` nghĩa là gỡ bỏ **chính đoạn ấy**.

Nếu có n hình, tổng số events là **2n**, có thể sắp theo x trong O(n log n).

Với hai hình A và B ở phần 5:

~~~text
x=1: A ENTER, add y in [1,4)
x=3: B ENTER, add y in [2,5)
x=4: A EXIT,  remove y in [1,4)
x=6: B EXIT,  remove y in [2,5)
~~~

Giữa hai tọa độ sự kiện liền nhau, tập đoạn y đang hoạt động không đổi.

### Diện tích từng dải trong ví dụ

| Dải x | Các hình hoạt động | Hợp các đoạn y | Chiều dài y | Diện tích dải |
|---|---|---|---:|---:|
| [1,3) | A | [1,4) | 3 | 2×3=6 |
| [3,4) | A và B | [1,5) | 4 | 1×4=4 |
| [4,6) | B | [2,5) | 3 | 2×3=6 |

Tổng diện tích **6+4+6=16**.

Điều quan trọng: tại x=3, hai đoạn y [1,4) và [2,5) **chồng lấn**, nên hợp có chiều dài **4**, không phải 3+3=6. Vì vậy **chỉ dùng biến đếm số hình hoạt động là không đủ** cho bài tính diện tích.

## 7. Nếu thêm một hình thứ ba

Thêm hình C:

\[
C=[2,5)\times[4,6),\quad area(C)=3\cdot2=6.
\]

Các tọa độ event: x=1 (A vào), x=2 (C vào), x=3 (B vào), x=4 (A ra), x=5 (C ra), x=6 (B ra).

Bảng chi tiết:

| Dải x | Hình hoạt động | Hợp đoạn y | Độ dài y | Diện tích dải |
|---|---|---|---:|---:|
| [1,2) | A | [1,4) | 3 | 3 |
| [2,3) | A,C | [1,6) | 5 | 5 |
| [3,4) | A,B,C | [1,6) | 5 | 5 |
| [4,5) | B,C | [2,6) | 4 | 4 |
| [5,6) | B | [2,5) | 3 | 3 |

Tổng:

\[
\boxed{3+5+5+4+3=20}.
\]

Đối chiếu bằng giao diện tích: A=9, B=9, C=6; giao A∩B có diện tích 2, giao B∩C có diện tích 2, A∩C chỉ chạm biên y=4 nên có diện tích 0. Do không có giao ba hình có diện tích dương:

\[
9+9+6-2-2=20.
\]

Ví dụ này minh họa rõ lý do **độ dài hợp y** thay đổi qua các event, trong khi công thức diện tích vẫn là “độ rộng dải × chiều dài hợp y”.

## 8. Nén tọa độ y: từ tọa độ lớn thành chỉ số nhỏ

Một hình chữ nhật có thể có tọa độ y là \(10^{12}\), nhưng nếu chỉ có n hình thì chỉ có tối đa **2n đầu mút y** xuất hiện.

Ta thu:

\[
Y=\operatorname{sortUnique}(y_1^{(1)},y_2^{(1)},\ldots,y_1^{(n)},y_2^{(n)}).
\]

Giả sử m là số giá trị y **phân biệt** trong Y. Chúng chia trục y thành **m−1 đoạn cơ sở**:

\[
[Y_0,Y_1), [Y_1,Y_2),\ldots,[Y_{m-2},Y_{m-1}).
\]

Đây là những **khoảng có chiều dài thật**, không phải những điểm đơn vị.

Nếu Y=[1,2,4,5,6], các đoạn cơ sở là:

~~~text
index 0: [1,2) length 1
index 1: [2,4) length 2
index 2: [4,5) length 1
index 3: [5,6) length 1
~~~

Một đoạn y=[2,5) tương ứng dải chỉ số cơ sở **[1,3)**, tức [2,4) và [4,5), có tổng chiều dài 3.

### Vì sao không nén y thành 0,1,2,... rồi tính theo số ô?

Nếu thay chiều dài của mỗi đoạn cơ sở bằng 1, kết quả sai khi các đầu mút không cách đều.

Ví dụ Y=[0,100,1000]. Hai đoạn cơ sở có độ dài 100 và 900, **không phải 1 và 1**. Nén tọa độ dùng để giảm **số vị trí phải lưu**, nhưng khi tính diện tích vẫn phải dùng **tọa độ y thật** để tính chiều dài.

### Tìm vị trí bằng binary search

Với một đầu mút y xuất hiện trong Y, tìm vị trí:

~~~text
i = lowerBound(Y, y)
~~~

Đối với y1<y2, cập nhật đoạn cơ sở:

\[
\boxed{[lowerBound(Y,y_1),\ lowerBound(Y,y_2))}.
\]

Hình học dùng nửa mở, nên việc dùng hai chỉ số theo nửa mở rất tự nhiên. **Không** cập nhật thêm phần tử ở vị trí right: nó bắt đầu tại y2 và không thuộc đoạn [y1,y2).

## 9. Vì sao cần segment tree?

Khi quét từ trái sang phải, mỗi event cần **thêm hoặc gỡ một khoảng y**. Sau cập nhật, ta cần biết:

\[
\boxed{\text{Tổng chiều dài của các đoạn y đang được ít nhất một hình phủ}.}
\]

Nếu mỗi lần event đều duyệt tất cả các đoạn cơ sở để cộng chiều dài, chi phí có thể O(n) cho mỗi event, dẫn tới O(n²).

**Segment tree** trên m−1 đoạn cơ sở hỗ trợ:

- Cập nhật cộng `+1` hoặc `-1` trên một khoảng chỉ số.
- Trả về **chiều dài hợp toàn trục y** tại nút gốc.

Điểm quan trọng là mỗi nút quản lý một dải chỉ số cơ sở `[lo,hi)` và lưu hai giá trị:

- `coverCount[node]`: số lần cập nhật **phủ trọn chính dải của nút** còn hiệu lực.
- `coveredLength[node]`: chiều dài **hợp y thực tế** được phủ ở dải nút, tính bằng đơn vị tọa độ gốc.

Ta **không** lưu tổng số hình ở mỗi điểm y. Ta lưu “có ít nhất một hình phủ” thông qua quy tắc tổng hợp.

## 10. Quy tắc kéo trạng thái từ con lên cha

Giả sử một nút segment tree quản lý `[lo,hi)` theo chỉ số đoạn cơ sở. Chiều dài hình học của toàn dải là:

\[
Y_{hi}-Y_{lo}.
\]

Quy tắc cập nhật `coveredLength[node]` là:

\[
\boxed{
coveredLength(node)=
\begin{cases}
Y_{hi}-Y_{lo},&coverCount(node)>0,\\
0,&coverCount(node)=0\text{ và nút lá},\\
coveredLength(left)+coveredLength(right),
&coverCount(node)=0\text{ và không phải lá}.
\end{cases}}
\]

### Trường hợp coverCount>0

Có ít nhất một hình đang phủ **toàn bộ khoảng** của nút, nên chiều dài hợp chính là độ dài thật của khoảng, **không cần biết con đang có gì**.

### Trường hợp coverCount=0

Không có hình nào đang phủ trọn cả dải của nút tại cấp hiện tại. Phần được phủ, nếu có, nằm trong hai nút con. Vì hai nửa không giao về chiều dài, ta cộng độ dài hợp của con trái và con phải.

### Tại sao không nhân theo coverCount?

Nếu hai hình cùng phủ \([1,4)\), `coverCount=2` ở nút tương ứng, nhưng chiều dài hợp vẫn là **3**, không phải 2×3=6.

Diện tích **hợp** là diện tích phủ **ít nhất một lần**. Nếu bài hỏi diện tích được phủ **chính xác k lần**, chỉ `coveredLength` như trên chưa đủ; phải lưu một cấu trúc phân phối độ phủ phù hợp.

### Gỡ bỏ hình có làm mất dữ liệu con không?

Không. Khi coverCount của cha dương, `coveredLength[cha]` được đặt bằng độ dài toàn dải; các nút con **vẫn giữ trạng thái riêng** của chúng. Khi hình phủ trọn cha rời đi và coverCount trở về 0, ta có thể cộng lại kết quả hai nút con để biết chính xác phần còn được các hình khác phủ.

## 11. Công thức quét theo x không bị lệch thời điểm

Giả sử đã sort các events theo x. Ta duy trì:

- `previousX`: tọa độ sự kiện đã xử lý gần nhất.
- `tree.coveredLength()`: chiều dài hợp y sau khi xử lý các sự kiện ở previousX.
- `area`: diện tích đã tích lũy ở mọi dải bên trái sự kiện đang xét.

Tại tọa độ sự kiện mới x:

\[
dx=x-previousX.
\]

Trạng thái cây hiện tại là của dải \([previousX,x)\), nên **trước khi cập nhật sự kiện ở x**, ta cộng:

\[
\boxed{area\mathrel{+}=dx\cdot tree.coveredLength()}.
\]

Sau đó xử lý **toàn bộ** events ở x để cây biểu diễn dải tiếp theo, rồi gán `previousX=x`.

Mã giả:

~~~text
sort events by x (and tie-break deterministically)
previousX = events[0].x
area = 0
activeY = empty segment tree

i = 0
while i < events.length:
    x = events[i].x

    dx = x - previousX
    area += dx * activeY.coveredLength()

    while i < events.length AND events[i].x == x:
        update [y1,y2) with delta +/-1
        i++

    previousX = x

return area
~~~

### Vì sao “tính diện tích trước rồi mới cập nhật” là đúng?

Hình có cạnh trái x **chưa phủ** dải bên trái x; hình có cạnh phải x **vẫn đã phủ** dải ngay trước x. Nếu cập nhật events tại x **trước khi cộng diện tích dải [previousX,x)**, ta dùng trạng thái **tương lai** để tính diện tích **quá khứ**, dễ cộng thiếu hoặc thừa.

### Nếu có nhiều events cùng x thì sao?

Khoảng giữa chúng có dx=0, nên ta **không cộng diện tích** sau mỗi event cùng x. Ta nhóm toàn bộ sự kiện tại x, cập nhật hết rồi mới bước sang x kế tiếp.

Quy tắc đơn giản này giải quyết nhiều lỗi tie-break đối với diện tích, kể cả hai hình chạm nhau ở cùng một cạnh thẳng đứng.

## 12. Java 17+: chương trình quét hình chữ nhật hoàn chỉnh

Chương trình **SweepLineGeometryDemo.java** gồm:

- `Rectangle`: hình chữ nhật có diện tích dương, dùng `long` cho tọa độ.
- `Event`: `ENTER=+1` tại x1 và `EXIT=-1` tại x2.
- `CoveredYTree`: segment tree theo các đoạn cơ sở sau khi nén y, lưu số lần phủ và chiều dài hợp.
- `unionArea`: sắp events theo x, tính từng dải trước khi xử lý nhóm events cùng x; dùng `Math.subtractExact`, `Math.multiplyExact`, `Math.addExact` để **phát hiện tràn long**, không âm thầm trả số sai.
- `maxConcurrent`: bài phụ đếm số khoảng nửa mở đang hoạt động lớn nhất, với **END trước START** khi bằng thời điểm.
- `verifyRectangleUnion`: kiểm tra diện tích hợp với oracle đếm các ô đơn vị trên lưới nhỏ, chỉ chạy trên dữ liệu nguyên nhỏ.
- `verifyIntervals`: kiểm tra ví dụ đếm khoảng đang hoạt động với phép thử trực tiếp.
- `main`: in các ví dụ có hình giao, chạm, lồng nhau, trùng nhau, cách xa nhau và tọa độ lớn.

**Mã đầy đủ, biên dịch trên Java 17 trở lên:**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Random;

public class SweepLineGeometryDemo {

    record Rectangle(long x1, long y1, long x2, long y2) {
        Rectangle {
            if (x1 >= x2 || y1 >= y2) {
                throw new IllegalArgumentException(
                    "rectangle must satisfy x1 < x2 and y1 < y2"
                );
            }
        }
    }

    record Event(long x, long y1, long y2, int delta) {}

    // A leaf represents one elementary y segment [ys[i], ys[i+1]).
    static final class CoveredYTree {
        final long[] ys;
        final int segments;
        final int[] coverCount;
        final long[] coveredLength;

        CoveredYTree(long[] distinctSortedY) {
            this.ys = distinctSortedY;
            this.segments = ys.length - 1;
            if (segments < 1) {
                throw new IllegalArgumentException(
                    "at least two distinct y coordinates required"
                );
            }
            coverCount = new int[4 * segments + 5];
            coveredLength = new long[4 * segments + 5];
        }

        long coveredLength() {
            return coveredLength[1];
        }

        void update(int from, int to, int delta) {
            if (from < 0 || from > to || to > segments) {
                throw new IllegalArgumentException(
                    "invalid compressed y interval"
                );
            }
            if (from == to) {
                return;
            }
            modify(1, 0, segments, from, to, delta);
        }

        private void modify(
            int node, int lo, int hi, int from, int to, int delta
        ) {
            if (to <= lo || hi <= from) {
                return;
            }
            if (from <= lo && hi <= to) {
                coverCount[node] =
                    Math.addExact(coverCount[node], delta);
                if (coverCount[node] < 0) {
                    throw new IllegalStateException(
                        "negative coverage counter"
                    );
                }
                pull(node, lo, hi);
                return;
            }

            int mid = lo + (hi - lo) / 2;
            modify(node * 2, lo, mid, from, to, delta);
            modify(node * 2 + 1, mid, hi, from, to, delta);
            pull(node, lo, hi);
        }

        private void pull(int node, int lo, int hi) {
            if (coverCount[node] > 0) {
                coveredLength[node] =
                    Math.subtractExact(ys[hi], ys[lo]);
            } else if (hi - lo == 1) {
                coveredLength[node] = 0;
            } else {
                coveredLength[node] = Math.addExact(
                    coveredLength[node * 2],
                    coveredLength[node * 2 + 1]
                );
            }
        }
    }

    static int lowerBound(long[] sorted, long target) {
        int lo = 0;
        int hi = sorted.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (sorted[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        return lo;
    }

    static long unionArea(List<Rectangle> rectangles) {
        if (rectangles.isEmpty()) {
            return 0L;
        }

        int n = rectangles.size();
        Event[] events = new Event[2 * n];
        long[] yValues = new long[2 * n];

        for (int i = 0; i < n; i++) {
            Rectangle r = rectangles.get(i);
            events[2 * i] =
                new Event(r.x1(), r.y1(), r.y2(), +1);
            events[2 * i + 1] =
                new Event(r.x2(), r.y1(), r.y2(), -1);
            yValues[2 * i] = r.y1();
            yValues[2 * i + 1] = r.y2();
        }

        Arrays.sort(yValues);
        int distinct = 0;
        for (long y : yValues) {
            if (distinct == 0 || yValues[distinct - 1] != y) {
                yValues[distinct++] = y;
            }
        }
        long[] ys = Arrays.copyOf(yValues, distinct);

        // Deterministic tie-break; area is computed per x group.
        Arrays.sort(
            events,
            Comparator.comparingLong(Event::x)
                .thenComparing(
                    (Event a, Event b) ->
                        Integer.compare(b.delta(), a.delta())
                )
                .thenComparingLong(Event::y1)
                .thenComparingLong(Event::y2)
        );

        CoveredYTree tree = new CoveredYTree(ys);
        long area = 0L;
        long previousX = events[0].x();

        for (int i = 0; i < events.length;) {
            long x = events[i].x();
            long width = Math.subtractExact(x, previousX);
            long strip = Math.multiplyExact(
                width, tree.coveredLength()
            );
            area = Math.addExact(area, strip);

            // Apply ALL changes at this x before the next strip.
            while (i < events.length && events[i].x() == x) {
                Event event = events[i];
                int from = lowerBound(ys, event.y1());
                int to = lowerBound(ys, event.y2());
                tree.update(from, to, event.delta());
                i++;
            }
            previousX = x;
        }
        return area;
    }

    record TimeEvent(long time, int delta) {}

    // Counts maximum simultaneous half-open intervals [start,end).
    static int maxConcurrent(long[][] intervals) {
        List<TimeEvent> events = new ArrayList<>();

        for (long[] interval : intervals) {
            if (interval.length != 2) {
                throw new IllegalArgumentException(
                    "interval must have two endpoints"
                );
            }
            long start = interval[0];
            long end = interval[1];
            if (start > end) {
                throw new IllegalArgumentException(
                    "interval start must be <= end"
                );
            }
            if (start == end) {
                continue; // Empty half-open interval.
            }
            events.add(new TimeEvent(start, +1));
            events.add(new TimeEvent(end, -1));
        }

        // For [start,end): exits (-1) BEFORE entries (+1).
        events.sort(
            Comparator.comparingLong(TimeEvent::time)
                .thenComparingInt(TimeEvent::delta)
        );

        int active = 0;
        int best = 0;
        for (TimeEvent event : events) {
            active = Math.addExact(active, event.delta());
            if (active < 0) {
                throw new AssertionError(
                    "negative active interval count"
                );
            }
            best = Math.max(best, active);
        }
        return best;
    }

    // Oracle for SMALL integer rectangles entirely inside [-5,10)^2.
    static long bruteUnionOnSmallGrid(List<Rectangle> rectangles) {
        long cells = 0L;
        for (int x = -5; x < 10; x++) {
            for (int y = -5; y < 10; y++) {
                for (Rectangle r : rectangles) {
                    if (r.x1() <= x && x < r.x2()
                            && r.y1() <= y && y < r.y2()) {
                        cells++;
                        break;
                    }
                }
            }
        }
        return cells;
    }

    static void verifyRectangleUnion() {
        Random random = new Random(2026L);
        int cases = 300;
        for (int t = 0; t < cases; t++) {
            int n = random.nextInt(9);
            List<Rectangle> rectangles = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                long x1 = random.nextInt(9) - 4;
                long y1 = random.nextInt(9) - 4;
                long x2 = x1 + 1 + random.nextInt(5);
                long y2 = y1 + 1 + random.nextInt(5);
                rectangles.add(new Rectangle(x1, y1, x2, y2));
            }
            long fast = unionArea(rectangles);
            long slow = bruteUnionOnSmallGrid(rectangles);
            if (fast != slow) {
                throw new AssertionError(
                    "rectangle union mismatch at case " + t
                );
            }
        }
        System.out.println(
            "Rectangle grid oracle: PASS (" + cases + " cases)"
        );
    }

    static void verifyIntervals() {
        Random random = new Random(427L);
        int cases = 200;

        for (int t = 0; t < cases; t++) {
            int n = random.nextInt(9);
            long[][] intervals = new long[n][2];
            for (int i = 0; i < n; i++) {
                long start = random.nextInt(9) - 4;
                long end = start + random.nextInt(8);
                intervals[i][0] = start;
                intervals[i][1] = end;
            }

            int brute = 0;
            for (int x = -5; x < 20; x++) {
                int covered = 0;
                for (long[] interval : intervals) {
                    if (interval[0] <= x && x < interval[1]) {
                        covered++;
                    }
                }
                brute = Math.max(brute, covered);
            }

            if (maxConcurrent(intervals) != brute) {
                throw new AssertionError(
                    "active interval mismatch at case " + t
                );
            }
        }
        System.out.println(
            "Interval oracle: PASS (" + cases + " cases)"
        );
    }

    static void show(String label, List<Rectangle> rectangles) {
        System.out.println(label + ": " + unionArea(rectangles));
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(1, 1, 4, 4);
        Rectangle b = new Rectangle(3, 2, 6, 5);
        Rectangle c = new Rectangle(2, 4, 5, 6);

        show("Two overlapping", List.of(a, b));
        show("Three overlapping", List.of(a, b, c));
        show("Touching edges", List.of(
            new Rectangle(0, 0, 2, 2),
            new Rectangle(2, 0, 4, 2)
        ));
        show("Nested rectangles", List.of(
            new Rectangle(0, 0, 5, 5),
            new Rectangle(1, 1, 4, 4)
        ));
        show("Duplicate rectangles", List.of(
            new Rectangle(0, 0, 3, 3),
            new Rectangle(0, 0, 3, 3)
        ));
        show("Separated rectangles", List.of(
            new Rectangle(0, 0, 2, 2),
            new Rectangle(3, 1, 5, 3)
        ));
        show("No rectangles", List.of());
        show("Large coordinates", List.of(
            new Rectangle(
                1_000_000_000_000L, 2_000_000_000_000L,
                1_000_000_000_003L, 2_000_000_000_005L
            )
        ));

        System.out.println("Maximum half-open overlaps: "
            + maxConcurrent(new long[][] {
                {1, 4}, {2, 5}, {4, 6}
            }));
        System.out.println("Touching intervals: "
            + maxConcurrent(new long[][] {
                {1, 3}, {3, 5}
            }));
        System.out.println("Empty interval ignored: "
            + maxConcurrent(new long[][] {
                {2, 2}
            }));

        verifyRectangleUnion();
        verifyIntervals();

        try {
            new Rectangle(1, 1, 1, 4);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid rectangle rejected: " + e.getMessage()
            );
        }

        try {
            maxConcurrent(new long[][] {{4, 3}});
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid interval rejected: " + e.getMessage()
            );
        }
    }
}
~~~

Lưu tệp chính xác là **SweepLineGeometryDemo.java** và dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 SweepLineGeometryDemo.java
java SweepLineGeometryDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
Two overlapping: 16
Three overlapping: 20
Touching edges: 8
Nested rectangles: 25
Duplicate rectangles: 9
Separated rectangles: 8
No rectangles: 0
Large coordinates: 15
Maximum half-open overlaps: 2
Touching intervals: 1
Empty interval ignored: 0
Rectangle grid oracle: PASS (300 cases)
Interval oracle: PASS (200 cases)
Invalid rectangle rejected: rectangle must satisfy x1 < x2 and y1 < y2
Invalid interval rejected: interval start must be <= end
~~~

### Đọc hiểu những dòng quyết định

**`Rectangle`:** dùng Java record và constructor kiểm \(x_1<x_2,y_1<y_2\). Dữ liệu diện tích bằng 0 bị từ chối thay vì bỏ qua ngầm; nếu đề yêu cầu cho hình suy biến thì phải đổi hợp đồng.

**`Event`:** một hình tạo hai event với cùng đoạn y; ENTER=+1 và EXIT=−1. Nhờ cập nhật chính xác cùng khoảng, bộ đếm phủ trong segment tree tăng/giảm cân bằng.

**Nén y:** lấy tất cả đầu mút y, sort, loại giá trị trùng. `lowerBound` trả chỉ số của đầu mút theo tọa độ thật. Segment tree xây trên **m−1 đoạn giữa hai đầu mút**, không xây trên m điểm.

**Segment tree:** nếu coverCount[node]>0, chiều dài phủ bằng `ys[hi]-ys[lo]`; nếu coverCount=0, cộng chiều dài phủ hai con. Ở lá không có phủ, chiều dài là 0.

**`unionArea`:** trước khi cập nhật nhóm events ở x, tính `width * tree.coveredLength()`; sau đó áp dụng mọi event cùng x. Do vậy không dùng trạng thái sau sự kiện để tính diện tích dải trước sự kiện.

**Thứ tự đồng x:** comparator chọn `ENTER(+1)` trước `EXIT(-1)` để nhất quán, nhưng kết quả diện tích không phụ thuộc thứ tự nội bộ khi mọi event tại x đều được áp dụng trước khi tính dải kế tiếp.

**`maxConcurrent`:** bài phụ có semantics khác. Đo chồng lấn của các khoảng `[start,end)` nên khi đồng thời điểm, `END(-1)` trước `START(+1)`. Nếu không, hai khoảng chỉ chạm nhau có thể bị đếm là chồng lấn.

**`Math.*Exact`:** phép trừ hai tọa độ, nhân chiều rộng với chiều dài, và cộng diện tích có thể tràn `long` với tọa độ cực trị. Mã **ném `ArithmeticException`** thay vì âm thầm sinh diện tích âm hoặc một giá trị wrap-around sai. Nếu bài đòi kết quả lớn hơn miền long, cần chuyển sang `BigInteger` và cấu trúc số học phù hợp.

**Oracle lưới:** chỉ kiểm hình chữ nhật có tọa độ nguyên nhỏ nằm hoàn toàn trong miền \([-5,10)\times[-5,10)\), nên mỗi ô đơn vị góp đúng một đơn vị diện tích nếu được phủ. Với tọa độ thực hoặc hình có cạnh nghiêng, oracle này không còn áp dụng trực tiếp.

## 13. Chứng minh tính đúng của quét diện tích hợp

Để chứng minh, ta xét hai bất biến:

### Bất biến A — trạng thái cây sau một nhóm x

Sau khi xử lý tất cả events tại một tọa độ x, một hình chữ nhật có mặt trong trạng thái nếu và chỉ nếu:

\[
x_1\le x<x_2.
\]

Vì hình được thêm tại cạnh trái x1 và gỡ tại cạnh phải x2, sau khi xử lý nhóm event, các hình đang hoạt động chính là những hình có thể phủ **dải ngay bên phải x**.

Segment tree lưu đúng chiều dài hợp các đoạn y của hình đang hoạt động: coverCount dương ở nút nghĩa là toàn bộ dải y của nút được phủ; khi không có phủ trọn nút, hợp chiều dài là hợp của hai con rời nhau.

### Bất biến B — area tích lũy trước một nhóm event

Ngay trước khi xử lý sự kiện ở x, `previousX` là tọa độ nhóm x đã xử lý trước đó. Không có event nào trong khoảng mở giữa hai mốc, nên tập hình đang hoạt động và chiều dài hợp y là **hằng trên dải [previousX,x)**.

Diện tích đúng của dải ấy:

\[
(x-previousX)\cdot coveredLength.
\]

Thuật toán cộng đúng giá trị này một lần, sau đó cập nhật toàn bộ event tại x. Quy nạp theo các nhóm x cho thấy tổng sau nhóm cuối bằng **diện tích hợp các hình chữ nhật**.

### Vì sao không đếm hai lần vùng chồng lấn?

Ở mỗi x, segment tree trả về **chiều dài hợp** trên y, không phải tổng chiều dài từng đoạn. Nếu ba hình cùng phủ một vùng y, `coveredLength` vẫn chỉ đếm mỗi phần tử độ dài một lần. Theo các dải x rời nhau, tổng diện tích dải vì thế không đếm trùng vùng trên mặt phẳng.

### Các hình chạm biên có ảnh hưởng không?

Nếu hai hình chỉ chạm cạnh x hoặc y, phần giao của chúng có diện tích bằng 0. Dùng các khoảng nửa mở và nhóm event cùng x cho kết quả đúng; không cộng diện tích giả cho đường biên.

## 14. Độ phức tạp

Gọi n là số hình chữ nhật, m là số tọa độ y phân biệt; m≤2n.

**Chuẩn bị events:** 2n sự kiện, O(n) thời gian và bộ nhớ.

**Sort events theo x:** O(n log n).

**Sort và unique các tọa độ y:** O(n log n) thời gian, O(n) bộ nhớ.

**Cập nhật segment tree:** mỗi hình có hai sự kiện, mỗi cập nhật khoảng trên trục nén tốn O(log m) nút/công việc amortized theo phân rã chuẩn của segment tree; tổng O(n log n).

**Tính chiều dài hợp:** lấy giá trị nút gốc trong O(1) mỗi nhóm sự kiện.

Vì vậy:

\[
\boxed{\text{Thời gian }O(n\log n),\qquad \text{bộ nhớ }O(n).}
\]

Nếu cần **liệt kê các đoạn y hợp thực tế** thay vì chỉ chiều dài, đầu ra có thể lớn, cần thuật toán/truy vấn bổ sung. Cận trên chỉ đúng cho **bài tính diện tích hợp** và cấu trúc lưu tổng chiều dài phủ, không đồng nghĩa mọi bài toán hình học sweep đều O(n log n).

### So sánh với cách thử từng cặp

Với n hình chữ nhật, chỉ dùng công thức cộng tổng diện tích rồi trừ giao của từng cặp **không đủ** trong trường hợp nhiều hình: các giao ba, giao bốn,... có thể cần tính theo nguyên lý bao hàm–loại trừ. Duyệt mọi tập con là không khả thi.

Segment tree bảo trì chiều dài hợp **trực tiếp**, nên tự xử lý mọi mức chồng lấn mà không phải liệt kê các giao nhiều hình.

## 15. Quét để đếm số khoảng đang hoạt động

Bài toán hình học có thể được rút về **một chiều** để luyện kỹ năng quản lý event:

Cho các khoảng nửa mở \([s_i,e_i)\), hãy tìm số khoảng **cùng hoạt động tối đa** tại một thời điểm.

Tạo hai sự kiện cho mỗi khoảng:

~~~text
(start, +1)
(end,   -1)
~~~

Nếu start=end, khoảng rỗng và không hoạt động ở thời điểm nào; nên bỏ qua.

Sort:

1. Theo `time` tăng.
2. Nếu cùng time, **`delta=-1` trước `delta=+1`**.

Duyệt, cập nhật `active+=delta`, rồi cập nhật `maxActive`.

### Ví dụ có biên chạm

~~~text
A=[1,4)
B=[2,5)
C=[4,6)

time:   1 2 3 4 5 6
A:      [=====)
B:        [=====)
C:            [===)
~~~

Tại thời điểm t=4, A đã kết thúc, C bắt đầu, B còn hoạt động. Số khoảng hoạt động vẫn là 2 chứ không phải 3.

Kết quả:

\[
\boxed{maxActive=2}.
\]

Với \([1,3)\) và \([3,5)\), maxActive=1 vì hai khoảng chỉ **chạm** tại ranh giới mà không chồng lấn theo nửa mở.

Đây là ví dụ mà **biến đếm đơn giản** đủ làm active status; không cần segment tree như bài diện tích hợp hình chữ nhật.

### Nếu cần cả thời điểm đạt cực đại?

Có thể ghi lại các đoạn thời gian giữa các mốc sự kiện sau khi xử lý nhóm đồng thời. Khi đó nên đo `active` **trên từng dải [time_i,time_{i+1})**, thay vì nhầm trạng thái tạm trong nhóm event cùng time với một khoảng có độ dài dương.

## 16. Các bài hình học khác dùng sweep line

### A. Truy vấn số điểm trong hình chữ nhật bằng offline sweep

Giả sử có nhiều điểm (x,y), muốn đếm điểm trong các truy vấn \([x_1,x_2]\times[y_1,y_2]\) theo một quy ước biên đã chốt.

Ta có thể sắp điểm theo x rồi dùng **Fenwick tree** hoặc segment tree trên trục y sau khi nén tọa độ:

- Khi đường quét đi qua một điểm, thêm 1 tại y của điểm đó.
- Với mỗi truy vấn, chuyển về hiệu của những truy vấn **tiền tố theo x**.
- Mỗi truy vấn tiền tố lấy tổng trong khoảng y bằng cây.

Độ phức tạp thường O((n+q)log(n+q)) sau sắp/nén, với n điểm và q truy vấn. Nhưng phải thiết kế thứ tự **INSERT POINT** và **QUERY** cùng x để bao gồm hoặc loại biên đúng. Ví dụ để đếm điểm có x≤X, thường **thêm điểm tại X trước** khi trả prefix query tại X.

### B. Phát hiện giao nhau của các đoạn thẳng

Với đoạn thẳng bất kỳ, một đường quét đứng thường lưu các đoạn giao đường quét theo **thứ tự tung độ tại x hiện tại**. Trong những thuật toán giao đoạn kiểu **Bentley–Ottmann**, event queue có thể chứa:

- Đầu mút bắt đầu.
- Đầu mút kết thúc.
- **Giao điểm** phát hiện trong quá trình quét.

Những đoạn kề nhau trong thứ tự tại đường quét được kiểm tra khả năng tạo giao điểm tiếp theo. Trong điều kiện hình học thích hợp, thuật toán có độ phức tạp đầu ra nhạy \(\mathcal O((n+k)\log n)\), với k là số giao điểm được báo.

**Cảnh báo khi dùng `TreeSet` ở Java:** nếu comparator so hai đoạn theo tung độ của chúng tại một biến `currentX` và comparator **thay đổi kết quả khi currentX thay đổi**, bất biến trật tự của cây cân bằng có thể bị phá. Không chỉ cập nhật một biến x rồi hy vọng TreeSet tự sắp xếp lại. Cần thiết kế thuật toán/cấu trúc xử lý sự kiện và cập nhật thứ tự giao cắt đúng cách.

Các trường hợp **đoạn thẳng đứng, đầu mút trùng, nhiều đoạn giao cùng một điểm và chồng đoạn thẳng** cũng cần xử lý riêng; công thức “hàng xóm kề nhau” đơn giản thường giả định các đoạn ở vị trí tổng quát.

### C. Cặp điểm gần nhất

Có thể sort điểm theo x rồi duy trì các điểm đủ gần đường quét, sắp theo y. Khi đã có khoảng cách tốt nhất d, chỉ xét những điểm trong dải \([x-d,x]\) và phạm vi y tương ứng. Kỹ thuật hình học suy ra số ứng viên cần so ở mỗi bước có thể được chặn nhỏ nếu quản lý đúng.

Ở đây active status là tập điểm đang ở trong **dải khả dĩ**, không phải mọi điểm đã xuất hiện trước đó.

### D. Hợp đoạn và độ dài phủ

Bài tính hợp các khoảng một chiều có thể làm đơn giản hơn bằng sort các đầu mút hoặc sort intervals và gộp chồng. Segment tree chỉ thật sự hữu ích khi cần **thêm/gỡ nhiều khoảng giữa chừng** trong bài hai chiều hoặc khi cần truy vấn tổng sau mỗi sự kiện.

Không nên sử dụng cấu trúc quá phức tạp nếu trạng thái chỉ cần một biến đếm hoặc một đoạn hợp hiện tại.

## 17. Vấn đề số học: tràn long và tính đúng hình học

Các bài hình học rất dễ gặp **sai số/overflow**, ngay cả khi sort và event order hoàn toàn đúng.

### A. Tọa độ lớn và hiệu hai tọa độ

Với `long x1,x2`, một biểu thức `x2-x1` có thể tràn nếu hai đầu ở hai phía cực trị miền long. Trong Java, phép cộng/trừ long thông thường có thể **wrap-around** mà không báo lỗi.

Mã dùng:

~~~java
long width = Math.subtractExact(x2, x1);
~~~

Nếu hiệu không biểu diễn được bằng long, chương trình ném `ArithmeticException` thay vì trả số âm vô nghĩa.

### B. Tích chiều rộng × chiều cao

Ngay cả khi từng hiệu tọa độ nằm trong long, tích diện tích vẫn có thể vượt miền long:

~~~java
long stripArea = Math.multiplyExact(width, coveredY);
area = Math.addExact(area, stripArea);
~~~

Nếu bài toán cần diện tích lớn hơn `Long.MAX_VALUE`, phải dùng `BigInteger` hoặc một kiểu số phù hợp. Không nên âm thầm đổi sang double nếu đề yêu cầu diện tích **nguyên chính xác**.

### C. So sánh event

Tránh comparator:

~~~java
(a, b) -> (int) (a.x() - b.x())
~~~

vì trừ long có thể tràn rồi ép int làm hỏng thứ tự. Dùng:

~~~java
Comparator.comparingLong(Event::x)
~~~

Tương tự, đừng dùng `(int)(a.x-b.x)` trong sort điểm.

### D. Tích có hướng và tính giao cắt

Trong các bài giao đoạn, orientation dựa trên tích có hướng:

\[
cross(B-A,C-A)
=(B_x-A_x)(C_y-A_y)-(B_y-A_y)(C_x-A_x).
\]

Với tọa độ rất lớn, phép trừ/nhân trong cross product có thể tràn long. Nếu cần quyết định hình học chính xác, có thể dùng **BigInteger**, số học đa độ chính xác hoặc kỹ thuật robust predicates, thay vì tin vào long/double không kiểm soát.

### E. Độ chính xác với tọa độ thực

Mã ví dụ diện tích hợp dùng **tọa độ nguyên long**. Nếu dùng tọa độ `double`, cần xem xét:

- Hai giá trị rất gần nhau có nên được coi là cùng một tọa độ hay không?
- Sort và unique phải nhất quán với chính sách đồng nhất tọa độ.
- Comparator phải có **thứ tự tổng** và ổn định.
- Các phép cộng diện tích có sai số số học.
- Không dùng epsilon tùy tiện trong comparator vì quan hệ “xấp xỉ bằng” có thể **không bắc cầu**, phá sort và cây cân bằng.

Một cách xử lý tốt khi đầu vào thập phân có số chữ số cố định là **quy đổi về số nguyên theo đơn vị nhỏ nhất** nếu miền giá trị cho phép.

## 18. Các lỗi thường gặp

1. **Không xác định event nào làm thay đổi trạng thái**, khiến một số thay đổi hình học không được xử lý.
2. **Sort sự kiện theo tọa độ nhưng bỏ quy tắc đồng tọa độ**, sai ở hình chạm biên.
3. **Dùng START trước END cho khoảng nửa mở và đo max giữa nhóm**, đếm chồng lấn giả.
4. **Dùng END trước START cho khoảng đóng khi cần đếm điểm chung tại biên**, đếm thiếu.
5. **Cộng diện tích dải trước đó sau khi đã cập nhật sự kiện x hiện tại**, dùng trạng thái sai thời điểm.
6. **Tính diện tích giữa các event cùng x**, dù bề rộng dải đó bằng 0.
7. **Nhầm tổng chiều dài y của các hình với chiều dài hợp y**, đếm đôi vùng chồng lấn.
8. **Không nén tọa độ y**, cấp phát mảng theo giá trị tọa độ rất lớn.
9. **Nén tọa độ rồi coi các đoạn cơ sở đều dài 1**, sai diện tích khi khoảng cách y không đều.
10. **Quên unique các đầu mút y**, tạo các đoạn cơ sở độ dài 0 hoặc mô hình không rõ.
11. **Xây segment tree trên m điểm thay vì m−1 đoạn giữa điểm**, dẫn tới sai phạm vi cập nhật.
12. **Cập nhật [from,to] thay vì [from,to)** trong trục nén**, đánh dấu thừa đoạn phía trên y2.
13. **Không phân biệt coverCount với coveredLength**, đặc biệt khi nhiều hình phủ cùng dải.
14. **Tính coveredLength = coverCount × độ dài**, đếm trùng vùng.
15. **Khi coverCount cha về 0 mà không cộng lại dữ liệu con**, làm mất phần phủ từ hình khác.
16. **Dùng cùng event y cho cả thêm/gỡ nhưng sai tọa độ một đầu**, trạng thái còn sót sau hình rời đi.
17. **Không xử lý nhóm events cùng x**, có thể dùng trạng thái trung gian không phải trạng thái một dải có độ rộng dương.
18. **Không loại/khoanh phạm vi hình suy biến**, dẫn tới cập nhật đoạn y rỗng hoặc chiều rộng 0 ngoài ý muốn.
19. **Dùng int cho tọa độ/diện tích lớn**, bị tràn ngay khi hiệu/tích vượt 32-bit.
20. **Dùng long nhưng không kiểm tràn phép trừ/nhân/cộng**, vẫn có thể trả số sai.
21. **Viết comparator bằng phép trừ**, làm hỏng sort khi số lớn.
22. **Sử dụng comparator TreeSet phụ thuộc currentX và thay đổi giữa các thao tác**, phá bất biến cấu trúc dữ liệu.
23. **Nhầm bài union area với union perimeter**, dùng mỗi coveredLength rồi suy ra chu vi mà không có dữ liệu bổ sung.
24. **Nhầm đếm mọi giao điểm đoạn thẳng với phát hiện có giao**, trong khi liệt kê k giao điểm có chi phí đầu ra tối thiểu O(k).
25. **Không xét đoạn thẳng đứng hay nhiều giao điểm đồng tọa độ** trong thuật toán giao đoạn.
26. **Quên đổi loại sự kiện tại cùng x cho truy vấn điểm trên biên**, làm kết quả lệch một ở biên.
27. **Chỉ test hình không giao nhau**, bỏ sót lỗi đếm trùng chiều dài y.
28. **Chỉ test hình giao nhau**, bỏ sót lỗi hình chạm cạnh, nested, duplicate hoặc rỗng.
29. **So kết quả với một công thức bao hàm–loại trừ chỉ có giao đôi**, sai khi có giao ba hình.
30. **Không đối chiếu với oracle trên lưới nhỏ**, khó phát hiện sai cập nhật segment tree.
31. **Cho rằng mọi plane sweep có O(n log n)**, không xét số giao điểm/số truy vấn hoặc chi phí duy trì active status.
32. **Không kiểm số nguyên lớn ở `width*coveredLength`**, biến một thuật toán logic đúng thành đầu ra không tin cậy.

## 19. Kiểm chứng bằng oracle độc lập

Lý tưởng là kiểm **tập những ô thật sự được phủ** trên miền nguyên nhỏ, không dùng sự kiện hoặc segment tree trong oracle.

Với các hình có tọa độ nguyên và hoàn toàn nằm trong \([-5,10)\times[-5,10)\), mỗi ô đơn vị:

\[
[x,x+1)\times[y,y+1)
\]

có diện tích 1. Ô được phủ nếu tồn tại ít nhất một hình R sao cho:

\[
R.x_1\le x<R.x_2,\qquad R.y_1\le y<R.y_2.
\]

Oracle đơn giản:

~~~text
area = 0

for x = -5 .. 9:
    for y = -5 .. 9:
        if any rectangle covers cell (x,y):
            area++

return area
~~~

Oracle này không cần nén tọa độ, không dựng events, không dùng segment tree. Vì **khác cơ chế với thuật toán chính**, nó có thể phát hiện lỗi dù code sweep vẫn cho đúng một vài ví dụ.

### Những thuộc tính cần kiểm

- Không có hình ⇒ diện tích 0.
- Một hình ⇒ diện tích (x2−x1)(y2−y1), nếu kết quả vừa kiểu.
- Hai hình rời nhau ⇒ tổng diện tích.
- Hai hình giống hệt nhau ⇒ diện tích chỉ bằng một hình.
- Hình nằm trọn trong hình khác ⇒ diện tích bằng hình lớn.
- Hai hình chỉ chạm cạnh ⇒ tổng diện tích, không có phần giao dương.
- Đổi thứ tự input **không đổi** diện tích.
- Thêm một hình mới không thể làm **giảm** diện tích hợp.
- Dịch mọi hình cùng một vector không làm đổi diện tích.
- Nếu chỉ còn một dải x giữa hai event, diện tích dải đúng bằng chiều rộng×chiều dài hợp y.
- Tọa độ lớn nhưng độ rộng/chiều cao nhỏ vẫn xử lý được nếu không overflow.
- Thay cách sort các event đồng x mà vẫn áp dụng hết nhóm phải giữ nguyên diện tích.
- Khi muốn đếm khoảng nửa mở, \([1,3)\) và \([3,5)\) **không** được trả maxConcurrent=2.

### Bộ test tham chiếu

| Hình chữ nhật | Diện tích hợp |
|---|---:|
| [1,4)×[1,4) và [3,6)×[2,5) | 16 |
| Hai hình trên cùng [2,5)×[4,6) | 20 |
| [0,2)×[0,2) và [2,4)×[0,2) | 8 |
| [0,5)×[0,5) chứa [1,4)×[1,4) | 25 |
| Hai hình trùng nhau [0,3)×[0,3) | 9 |
| Hai hình rời nhau diện tích 4 mỗi hình | 8 |
| Không có hình | 0 |
| Một hình tọa độ quanh 10^12, rộng 3 cao 5 | 15 |

Chương trình Java dùng 300 bộ hình nhỏ ngẫu nhiên, đối chiếu mỗi diện tích với oracle lưới; và 200 bộ khoảng thời gian ngẫu nhiên đối chiếu `maxConcurrent` với cách đếm trực tiếp số khoảng đang chứa từng thời điểm nguyên.

Không chạy oracle lưới trên tọa độ cực lớn: đó là công cụ **QA cho dữ liệu nhỏ**, không phải phương pháp thay thế cho quét mặt phẳng.

## 20. Bài tập tự luyện

**Bài 1 — Mô hình.** Trong quét mặt phẳng, active status là gì?

*Đáp án:* Trạng thái của các đối tượng hiện còn tác động tại vị trí đường quét, được cập nhật khi qua sự kiện.

**Bài 2 — Events.** Một hình \([x_1,x_2)\times[y_1,y_2)\) sinh những sự kiện nào?

*Đáp án:* ENTER tại x1 và EXIT tại x2, cùng đoạn y=[y1,y2), delta lần lượt +1/−1.

**Bài 3 — Sự kiện đồng x.** Khi tính diện tích, vì sao nên xử lý hết nhóm event cùng x rồi mới quét tiếp?

*Đáp án:* Các event ấy không tạo dải có độ rộng dương; trạng thái cần đúng trên dải x kế tiếp.

**Bài 4 — Tính dải.** Nếu width=3 và hợp y dài 7, diện tích dải bằng bao nhiêu?

*Đáp án:* **21**.

**Bài 5 — Union.** Hai hình A=[1,4)×[1,4), B=[3,6)×[2,5) có diện tích hợp bao nhiêu?

*Đáp án:* **16**.

**Bài 6 — Vì sao không cộng độ dài y từng hình?**

*Đáp án:* Các đoạn y có thể chồng nhau; chỉ **hợp** của chúng được tính một lần trong diện tích.

**Bài 7 — Nén y.** Với Y=[1,2,4,5,6], có bao nhiêu đoạn cơ sở?

*Đáp án:* **4**, là [1,2),[2,4),[4,5),[5,6).

**Bài 8 — Khoảng cập nhật.** Đoạn y=[2,5) tương ứng phạm vi chỉ số nào trong Y trên?

*Đáp án:* **[1,3)**.

**Bài 9 — Cover count.** Nếu `coverCount[node]=2`, chiều dài phủ là hai lần chiều dài nút hay chiều dài nút?

*Đáp án:* **Chiều dài nút**, vì bài hỏi hợp, không hỏi số lượt phủ.

**Bài 10 — Cover count về 0.** Nếu nút không phải lá và count=0, chiều dài hợp tính thế nào?

*Đáp án:* Bằng **coveredLength của con trái + con phải**.

**Bài 11 — Công thức diện tích.** Vì sao cộng diện tích dải trước khi xử lý event x?

*Đáp án:* Active status hiện tại mô tả dải từ previousX đến ngay trước x, không phải dải sau x.

**Bài 12 — Khoảng nửa mở.** Tại t=3, [1,3) và [3,5) có cùng hoạt động không?

*Đáp án:* **Không**.

**Bài 13 — Tie-break.** Với khoảng [start,end), loại event nào đi trước ở cùng time khi đo max theo từng event?

*Đáp án:* **END (−1)** trước **START (+1)**.

**Bài 14 — Khoảng đóng.** Nếu hai khoảng đóng [1,3] và [3,5] thì có điểm chung không?

*Đáp án:* **Có**, tại t=3; nếu đếm phủ ở điểm, cần bảo đảm hai START/END được xem là cùng có hiệu lực tại t.

**Bài 15 — Bộ nhớ.** Với n hình chữ nhật, số sự kiện và số tọa độ y phân biệt tối đa là bao nhiêu?

*Đáp án:* **2n events** và **2n đầu mút y phân biệt**.

**Bài 16 — Độ phức tạp.** Quét diện tích hợp các hình chữ nhật với nén y + segment tree thường tốn bao nhiêu?

*Đáp án:* **O(n log n)** thời gian, **O(n)** bộ nhớ.

**Bài 17 — Hình chạm.** Hai hình có chung cạnh nhưng không giao nội thất có làm diện tích hợp nhỏ hơn tổng hai diện tích không?

*Đáp án:* **Không**, phần giao có diện tích 0.

**Bài 18 — Hình trùng.** Hai hình giống hệt nhau, mỗi hình diện tích 9. Diện tích hợp là bao nhiêu?

*Đáp án:* **9**, không phải 18.

**Bài 19 — Tọa độ lớn.** Vì sao nén tọa độ cần dùng chiều dài `ys[hi]-ys[lo]` thay vì hi−lo?

*Đáp án:* Các khoảng giữa hai đầu mút nén có **độ dài thật khác nhau**.

**Bài 20 — Overflow.** Vì sao `long area=width*height` vẫn có thể sai với tọa độ lớn?

*Đáp án:* Phép nhân long có thể tràn; dùng `Math.multiplyExact` để phát hiện hoặc `BigInteger` nếu cần miền lớn hơn.

**Bài 21 — Query events.** Khi đếm điểm có x≤X, điểm tại x=X cần được thêm vào cây trước hay sau khi trả truy vấn tiền tố X?

*Đáp án:* **Trước**, để bao gồm điểm trên biên phải theo dấu ≤.

**Bài 22 — TreeSet.** Vì sao một comparator phụ thuộc currentX có thể làm TreeSet bị hỏng logic?

*Đáp án:* Khi currentX thay đổi, thứ tự so sánh các phần tử có thể đổi mà cây chưa được sắp xếp lại.

**Bài 23 — Kết quả đầu ra nhạy.** Vì sao thuật toán liệt kê k giao điểm có thể cần ít nhất O(k) thời gian?

*Đáp án:* Phải xuất k kết quả, dù số đoạn đầu vào chỉ n.

**Bài 24 — QA.** Một oracle đơn giản để kiểm diện tích hợp trên tọa độ nguyên nhỏ là gì?

*Đáp án:* Duyệt mọi ô đơn vị trong miền nhỏ và đếm ô thuộc **ít nhất một hình**.

**Tổng kết:** Quét mặt phẳng biến một bài toán hình học thành **dãy sự kiện có thứ tự** và một **trạng thái hoạt động** được cập nhật khi đường quét đi qua sự kiện. Để thiết kế đúng, cần chốt trục quét, các loại event, chính sách **đồng tọa độ**, bất biến trạng thái và chi phí update/query. Với diện tích hợp hình chữ nhật, mỗi hình tạo **ENTER/EXIT theo x**, các đầu mút y được **nén tọa độ**, segment tree duy trì **chiều dài hợp y** và diện tích mỗi dải bằng **\((x_{next}-x_{current})\times coveredY\)**. Bài toán này chạy **O(n log n)** thời gian và **O(n)** bộ nhớ, đồng thời xử lý được hình trùng, lồng nhau và chạm biên. Khi cài Java, phải tránh nhầm biên nửa mở, đếm trùng vùng phủ, dùng trạng thái sai thời điểm, comparator không ổn định và **tràn long**. Những nguyên tắc đó còn áp dụng cho truy vấn điểm, giao đoạn, khoảng hoạt động và các thuật toán hình học quét khác.
