# Bộ nhớ trên mỗi phần tử và chi phí do cấp phát

> **Chương:** Đặc tả và chi phí · **Bài học:** Bộ nhớ trên mỗi phần tử và chi phí do cấp phát

Hai cấu trúc dữ liệu đều lưu 100.000 số nguyên và đều có độ phức tạp bộ nhớ **O(n)**. Tuy nhiên, một cấu trúc có thể chứa các số trong vùng nhớ liên tục, trong khi cấu trúc khác cần tạo 100.000 đối tượng nút và lưu thêm các con trỏ. Tổng số byte, lượng bộ nhớ dư, chi phí cấp phát và hiệu năng cache có thể rất khác nhau dù ký hiệu Big-O giống hệt.

Để lựa chọn hợp lý, không chỉ hỏi “cấu trúc cần O(n) hay O(n²) bộ nhớ?” mà còn phải hỏi: **mỗi phần tử thực sự phải trả thêm bao nhiêu byte, bao nhiêu lần cấp phát xảy ra và bộ nhớ đỉnh khi mở rộng có thể lớn đến đâu?**

Bài học thuộc chương **Đặc tả và chi phí** của mô-đun **Cấu trúc dữ liệu** (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Chúng ta sẽ phân tích các lựa chọn về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, liên hệ với bất biến, thao tác và độ phức tạp thời gian–không gian để ra quyết định theo đặc điểm bài toán.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Phân biệt **dữ liệu có ích**, **bộ nhớ quản lý**, **dung lượng dự phòng**, **bộ nhớ phụ tạm thời** và **bộ nhớ đỉnh**.
2. Lập một mô hình ước tính byte trên mỗi phần tử mà không nhầm lẫn giữa đối tượng sở hữu dữ liệu và tham chiếu tới dữ liệu.
3. Giải thích tác động của header đối tượng, con trỏ, căn chỉnh vùng nhớ, độ phân mảnh và kích thước bucket.
4. So sánh bộ nhớ của mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và các cách biểu diễn đồ thị.
5. Phân biệt **chi phí thời gian do cấp phát/sao chép** với **lượng bộ nhớ cấp phát**; phân tích trường hợp mở rộng mảng và tái băm.
6. Sử dụng phép đo bộ nhớ trong Python đúng phạm vi, biết các giới hạn của `sys.getsizeof` và `tracemalloc`.
7. Chọn cấu trúc dữ liệu theo tổng chi phí bộ nhớ, thời gian truy cập/cập nhật và yêu cầu vận hành.

## 2. Một phần tử có thể tiêu tốn nhiều hơn kích thước giá trị

Giả sử một phần tử logic là số nguyên 64 bit, có 8 byte thông tin nếu được lưu trực tiếp trong một ô 64 bit. Nhưng cách biểu diễn có thể là:

- **Mảng số nguyên đóng gói:** một phần tử chiếm một ô số nguyên 8 byte, ngoài header của vùng chứa và phần dung lượng dư.
- **Mảng tham chiếu đối tượng:** mỗi phần tử cần một ô chứa địa chỉ tới đối tượng; chính đối tượng số nguyên có thể nằm ở vùng nhớ khác và có header riêng.
- **Danh sách liên kết:** mỗi nút ngoài giá trị còn có ít nhất một con trỏ `next`, thông tin cấp phát và có thể phải căn chỉnh kích thước.
- **Cây:** mỗi nút có giá trị hoặc tham chiếu khóa, các con trỏ con, đôi khi có con trỏ cha, màu hoặc chiều cao.
- **Bảng băm:** mỗi mục có khóa, giá trị và thông tin định vị/va chạm, cộng vùng bucket.

**Đơn vị đo của ADT không phải đơn vị đo byte.** Một Stack lưu `n` phần tử chỉ cam kết hành vi LIFO; số byte mỗi phần tử phụ thuộc cài đặt cụ thể.

### 2.1. Các lớp bộ nhớ cần ghi rõ

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Payload** | Thông tin thực sự cần lưu | Giá trị số, khóa, nội dung bản ghi |
| **Metadata mỗi phần tử** | Quản lý hoặc nối một phần tử | `next`, `prev`, chiều cao cây, hash đã tính |
| **Metadata cấp cấu trúc** | Mô tả toàn bộ đối tượng chứa | `size`, `capacity`, `head`, `tail` |
| **Vùng nhớ dự phòng** | Dung lượng đã cấp phát nhưng chưa có dữ liệu logic | Ô trống trong mảng động, bucket chưa dùng |
| **Bộ nhớ tạm** | Dữ liệu chỉ tồn tại khi đang xử lý | Vùng mới trong lúc resize, bộ đệm khi sắp xếp |
| **Chi phí bộ cấp phát** | Quản lý các khối nhớ riêng lẻ | Header khối, làm tròn kích thước, phân mảnh |
| **Bộ nhớ ngăn xếp lời gọi** | Trạng thái gọi hàm hoặc đệ quy | Các khung gọi khi duyệt cây sâu |

Không phải môi trường nào cũng có đủ các thành phần với kích thước giống nhau. Đặc biệt, Python, Java, C++ và JavaScript có mô hình đối tượng, bộ cấp phát và bộ gom rác khác nhau.

### 2.2. Dữ liệu sở hữu và dữ liệu chỉ được tham chiếu

Nếu một danh sách chứa địa chỉ tới những đối tượng **đã tồn tại ở nơi khác**, chi phí thêm của danh sách chủ yếu là các ô tham chiếu và phần quản lý vùng chứa.

Nếu chính danh sách được tạo ra cùng với `n` đối tượng mới, tổng chi phí có thể gồm cả các đối tượng đó.

Ví dụ:

```python
existing = {"id": "A", "score": 8}

a = [existing, existing, existing]
# Ba ô trong list nhưng đều trỏ tới CÙNG một dict.

b = [{"id": "A", "score": 8} for _ in range(3)]
# Ba dict riêng được tạo ra.
```

Khi so sánh `a` và `b`, **không được cộng bộ nhớ của cùng một dict ba lần** trong trường hợp `a`. Cần quyết định đo **vùng chứa** hay **toàn bộ đồ thị đối tượng duy nhất có thể tới được** từ vùng chứa.

## 3. Mô hình tính byte trên mỗi phần tử

Với cấu trúc chứa `n` phần tử logic và có sức chứa vật lý `C`, một mô hình đơn giản là:

\[
M(n,C) \approx H + C\,s + n\,p + A(n,C).
\]

Ở đây:

- `M(n,C)`: số byte đang được giữ lại bởi cấu trúc cùng phần dữ liệu thuộc quyền sở hữu của nó.
- `H`: chi phí cố định của cấu trúc (header, bộ đếm, con trỏ quản lý).
- `s`: số byte của **một ô trong vùng chứa**; có thể là ô dữ liệu trực tiếp hoặc ô tham chiếu.
- `p`: số byte dữ liệu phụ riêng cho mỗi phần tử **chưa được tính trong `s`**; ví dụ một đối tượng được cấp phát riêng.
- `A(n,C)`: phần quản lý bộ cấp phát, căn chỉnh, bucket hoặc những cấu trúc phụ chưa tính vào ba số hạng trên.

Phép cộng này chỉ đúng nếu các vùng nhớ **không bị đếm trùng**. Nếu mảng lưu giá trị trực tiếp trong ô rộng `s` byte, không cộng lại chính payload ấy vào `p`.

Với `n>0`, có thể xem:

\[
b_{\mathrm{effective}}(n)=\frac{M(n,C)}{n}
\]

là **số byte hiệu dụng trên mỗi phần tử logic**, bao gồm cả phần chi phí cố định và sức chứa dư được phân bổ cho `n` phần tử.

### 3.1. Tổng byte và byte tăng thêm là hai chỉ số khác nhau

- `M(n,C)/n` cho biết lượng bộ nhớ đang giữ lại bình quân cho một phần tử logic.
- `\Delta M=M_{\text{after}}-M_{\text{before}}` cho biết mức thay đổi khi thêm hoặc xóa trong **một trạng thái cụ thể**.

Với mảng động, `\Delta M` có thể bằng 0 trong lần thêm còn chỗ, nhưng rất lớn trong lần thêm gây resize. Vì thế, **không nên lấy một lần chèn làm đại diện cho byte/phần tử về lâu dài**.

Khi `n=0`, phép chia `M(n,C)/n` không xác định. Ta nên báo riêng bộ nhớ nền của cấu trúc rỗng, nhất là nếu nó đã cấp phát sẵn dung lượng lớn.

### 3.2. Một ví dụ giả định để hiểu hệ số ẩn

Giả sử trên một mô hình máy 64 bit:

- Một giá trị được lưu trực tiếp trong ô 8 byte.
- Một con trỏ rộng 8 byte.
- Một nút liên kết có thêm 16 byte header/căn chỉnh (chỉ là **giả định bài toán**, không phải số đo Python).

Khi đó, với `n` phần tử:

| Cách biểu diễn | Mô hình bộ nhớ mỗi phần tử, bỏ qua header chung | Tổng gần đúng |
| --- | --- | --- |
| Mảng đóng gói, không dư sức chứa | 8 byte | `8n` |
| Nút liên kết đơn, gồm giá trị 8 + con trỏ 8 + overhead 16 | 32 byte | `32n` |
| Nút liên kết đôi, thêm một con trỏ 8 | 40 byte | `40n` |

Nếu có 100.000 phần tử, ba vùng chứa lần lượt vào khoảng 0,8 MB, 3,2 MB và 4 MB, với quy ước MB thập phân (1 MB = 1.000.000 byte). Đây chỉ là mô hình minh họa; triển khai thật có thể thêm metadata, căn chỉnh hoặc cấp phát khác.

**Cùng O(n) bộ nhớ không có nghĩa cùng số byte.** Hệ số từ 8 lên 32 byte/phần tử làm thay đổi đáng kể nhu cầu RAM ở quy mô lớn.

## 4. Mảng: lợi thế lưu liên tục và cái giá của sức chứa dư

### 4.1. Mảng có độ dài cố định

Một mảng số nguyên kiểu đóng gói có `n` ô, mỗi ô rộng `s` byte, thường có:

\[
M(n)\approx H+n\,s.
\]

Khi `n` lớn, phần header cố định `H` trở nên nhỏ so với `n\,s`. Việc duyệt tuần tự thường có lợi thế **tính cục bộ bộ nhớ** (*spatial locality*) vì các ô nằm gần nhau.

Nhưng nếu mảng lưu **tham chiếu** tới đối tượng thay vì giá trị trực tiếp, `s` là độ rộng của tham chiếu. Kích thước những đối tượng được trỏ tới phải được tính thêm khi chúng thuộc phạm vi đo.

### 4.2. Mảng động: phân biệt `size` và `capacity`

Mảng động duy trì:

- `size=n`: số phần tử logic đang được sử dụng.
- `capacity=C`: số ô vùng chứa đã cấp phát.

Bất biến quan trọng là:

\[
0\leq n\leq C.
\]

Số byte vùng ô là `C\,s`, không phải `n\,s`. Mức sử dụng:

\[
\rho=\frac{n}{C}\quad(C>0).
\]

Phần trống trong vùng ô chiếm `(C-n)s` byte. Khi `n` nhỏ hơn nhiều so với `C`, bộ nhớ hiệu dụng trên mỗi phần tử tăng.

### 4.3. Bài toán số: 100.000 tham chiếu trên vùng chứa lớn

Giả sử một mảng có:

- `n=100.000` ô đang sử dụng.
- `C=131.072` ô đã cấp phát.
- Mỗi ô chứa một tham chiếu rộng 8 byte.

Ta có:

\[
M_{\mathrm{slots}}=131.072\times8
=1.048.576\ \text{byte}.
\]

Nếu chỉ chia bộ nhớ của **vùng ô tham chiếu** cho số phần tử đang dùng:

\[
b_{\mathrm{slots}}=
\frac{1.048.576}{100.000}
\approx10,49\ \text{byte/phần tử}.
\]

Nếu không có sức chứa dư, con số là 8 byte/phần tử. Phần gần 2,49 byte/phần tử là chi phí bình quân do **ô dự phòng**.

Con số 10,49 **không bao gồm** đối tượng mà các tham chiếu trỏ tới, header mảng hoặc metadata của bộ cấp phát. Nó không phải “bộ nhớ của một đối tượng Python” hay tổng RAM ứng dụng.

### 4.4. Tăng gấp đôi sức chứa và bộ nhớ đỉnh

Giả sử vùng đệm đang đầy với `C` ô, mỗi ô rộng `s`. Để tăng từ `C` lên `2C`, một cài đặt có thể:

1. Cấp phát vùng mới `2C\,s` byte.
2. Sao chép dữ liệu từ vùng cũ `C\,s` byte.
3. Chuyển tham chiếu sang vùng mới rồi giải phóng vùng cũ.

Trong thời gian sao chép, **nếu cả hai vùng cùng tồn tại**, tổng riêng các vùng ô có thể xấp xỉ:

\[
M_{\mathrm{peak,slots}}\approx 3C\,s.
\]

Sau thao tác, vùng đệm giữ khoảng `2C\,s`. Hai số này khác nhau: **bộ nhớ đỉnh khi mở rộng** có thể lớn hơn bộ nhớ sau khi mở rộng.

Một bộ cấp phát đôi khi có thể mở rộng khối tại chỗ hoặc dùng chiến lược khác; `3C\,s` là mô hình của trường hợp cần cấp phát vùng mới đồng thời giữ vùng cũ, **không phải kết quả bắt buộc cho mọi runtime**.

### 4.5. Thu nhỏ cũng là một quyết định

Nếu sau khi xóa nhiều phần tử, `n` còn rất nhỏ nhưng `C` vẫn lớn, mảng có thể giữ một vùng nhớ dư đáng kể. Thu nhỏ vùng đệm giải phóng không gian nhưng phải sao chép dữ liệu và có thể gây cấp phát lặp lại nếu tăng/xóa liên tiếp quanh ngưỡng.

Chính sách thường gặp là tăng theo hệ số khi đầy và chỉ thu nhỏ khi số phần tử giảm sâu hơn một ngưỡng riêng. **Khoảng đệm giữa ngưỡng tăng và giảm** giúp tránh dao động liên tục. Muốn khẳng định chi phí thời gian O(1) khấu hao cho thêm/xóa phải phân tích đúng chính sách triển khai, không chỉ nhìn tên “mảng động”.

## 5. Danh sách liên kết: một nút cần nhiều hơn một giá trị

Danh sách liên kết đơn có các nút chứa giá trị và con trỏ `next`:

```text
head
 |
 v
[value A | next] -> [value B | next] -> [value C | null]
```

Một nút có thể cần:

- Vùng lưu giá trị hoặc tham chiếu giá trị.
- Con trỏ tới nút kế tiếp.
- Header đối tượng hoặc metadata của bộ cấp phát.
- Vùng đệm do căn chỉnh kích thước.
- Đôi khi thêm thông tin như bộ đếm tham chiếu hoặc trạng thái quản lý bộ nhớ.

### 5.1. Mô hình byte của danh sách liên kết đơn

Nếu một nút cần `v` byte dữ liệu, `p` byte con trỏ và `a` byte quản lý/căn chỉnh, thì:

\[
M_{\mathrm{singly}}(n)
\approx H_{\mathrm{list}}+n(v+p+a).
\]

Danh sách liên kết đôi thường cần thêm một con trỏ `prev`:

\[
M_{\mathrm{doubly}}(n)
\approx H_{\mathrm{list}}+n(v+2p+a').
\]

`a` và `a'` có thể khác nhau vì kích thước khối được làm tròn. Cả hai đều O(n) nhưng số byte thực tế trên mỗi phần tử thường cao hơn mảng đóng gói có cùng payload.

### 5.2. Vì sao chi phí con trỏ ảnh hưởng tốc độ?

Danh sách liên kết có thể thêm/xóa nhanh gần một nút đã biết, nhưng các nút được cấp phát độc lập có thể nằm rải rác trong bộ nhớ. Khi duyệt bằng `next`, CPU phải chờ địa chỉ nút kế tiếp, dễ tạo nhiều lần truy xuất bộ nhớ thiếu tính cục bộ hơn so với mảng liên tiếp.

Hai cấu trúc đều duyệt `n` phần tử trong Θ(n) thời gian theo số bước, nhưng **hằng số, bộ nhớ cache và băng thông** có thể khác biệt đáng kể.

### 5.3. Lợi ích thật sự của danh sách liên kết

Danh sách liên kết vẫn phù hợp nếu thường xuyên chèn/xóa **khi đã biết vị trí hoặc con trỏ cần thiết**, vì chỉ phải cập nhật vài liên kết thay vì dịch nhiều ô mảng.

Tuy vậy, nếu mỗi lần phải tìm nút theo giá trị trước, tổng thời gian vẫn có thể O(n). Không nên chấp nhận overhead bộ nhớ mỗi nút chỉ vì nghe rằng “chèn danh sách liên kết O(1)” mà không xét thao tác thực tế của ứng dụng.

## 6. Header, căn chỉnh và bộ cấp phát

Máy tính và runtime không phải lúc nào cũng cấp phát chính xác số byte lý thuyết trong một đối tượng.

### 6.1. Căn chỉnh bộ nhớ (*alignment*)

Một đối tượng cần `r` byte dữ liệu có thể được cấp phát ở kích thước làm tròn lên bội của `a` byte:

\[
\operatorname{roundUp}(r,a)
=a\left\lceil\frac{r}{a}\right\rceil.
\]

Ví dụ, nếu một khối cần 25 byte và bộ cấp phát làm tròn theo đơn vị 8 byte, kích thước vùng được cấp cho khối đó có thể là 32 byte, tức 7 byte dư.

Đây là **ví dụ giả định** về căn chỉnh. Một runtime cụ thể có thể dùng nhiều lớp kích thước, header riêng, hoặc tối ưu hóa khác.

### 6.2. Overhead theo khối cấp phát

Khi cấp phát riêng `n` nút nhỏ, chi phí quản lý khối và căn chỉnh có thể xuất hiện `n` lần. Khi cấp phát một mảng lớn, một số chi phí quản lý vùng có thể được chia sẻ cho cả mảng.

Ví dụ giả định:

| Thiết kế | Số lần cấp phát chính | Overhead quản lý giả định |
| --- | --- | --- |
| Một vùng liên tục cho `n` phần tử | 1 lần | Một khối metadata chung |
| `n` nút độc lập | `n` lần | Có thể có metadata/làm tròn trên mỗi nút |
| Các khối chứa 64 nút | Xấp xỉ `⌈n/64⌉` lần | Chia sẻ chi phí quản lý trên từng khối |

Thiết kế theo khối (*block allocation*, *slab* hoặc *pool*) có thể giảm số lần gọi bộ cấp phát và cải thiện tính cục bộ, nhưng đổi lại phải quản lý ô trống và thời điểm trả bộ nhớ về hệ thống.

### 6.3. Phân mảnh trong và phân mảnh ngoài

- **Phân mảnh trong:** một khối được cấp phát lớn hơn dữ liệu có ích, ví dụ do căn chỉnh hoặc dung lượng dự phòng.
- **Phân mảnh ngoài:** tổng vùng trống có thể đủ lớn nhưng nằm thành nhiều khoảng không liên tiếp, khiến cấp phát một khối lớn gặp khó khăn hoặc cần xử lý bổ sung.

Phân mảnh ngoài phụ thuộc bộ cấp phát và kiểu vòng đời đối tượng; không thể suy ra một tỷ lệ phần trăm cố định từ Big-O.

### 6.4. Bộ gom rác và thời gian giải phóng

Trong ngôn ngữ có quản lý bộ nhớ tự động, “xóa phần tử khỏi cấu trúc” thường có nghĩa **loại tham chiếu tới đối tượng**, không đồng nghĩa lập tức trả lại toàn bộ byte cho hệ điều hành.

Một đối tượng có thể vẫn được giữ bởi tham chiếu khác; khi không còn ai dùng, runtime có thể thu hồi theo cơ chế riêng. Ngoài ra, bộ cấp phát có thể giữ các vùng trống để tái sử dụng thay vì trả ngay cho hệ điều hành.

Vì thế, cần phân biệt:

1. Số phần tử logic còn trong cấu trúc.
2. Số đối tượng còn sống và còn được tham chiếu.
3. Bộ nhớ runtime đang giữ để tái sử dụng.
4. Bộ nhớ mà hệ điều hành ghi nhận cho tiến trình.

Các đại lượng này không nhất thiết giảm đồng thời.

## 7. Chi phí thời gian do cấp phát và sao chép

Một lệnh cấp phát không luôn có chi phí thời gian cố định trong mọi môi trường. Bộ cấp phát có thể:

- Tìm khối có kích thước phù hợp.
- Cập nhật bảng quản lý vùng trống.
- Yêu cầu thêm trang nhớ từ hệ điều hành.
- Khởi tạo vùng nhớ nếu hợp đồng ngôn ngữ yêu cầu.
- Kích hoạt cơ chế thu hồi bộ nhớ hoặc dọn dẹp.

Trong mô hình phân tích cấu trúc dữ liệu, ta thường đơn giản hóa việc cấp phát **một nút nhỏ** thành O(1), còn cấp phát và **khởi tạo một mảng `n` ô** là O(n) nếu mỗi ô phải được ghi. Nhưng thời gian thực tế có thể thay đổi theo bộ cấp phát, trạng thái hệ thống và áp lực bộ nhớ.

### 7.1. Không được nhầm số lần cấp phát với số byte

Hai chương trình có thể đều cấp phát O(n) byte nhưng khác số lần cấp phát:

- Mảng: một khối lớn cho `n` phần tử.
- Danh sách liên kết: `n` khối nhỏ cho `n` nút.

Tổng byte cùng bậc không bảo đảm cùng thời gian cấp phát. Nhiều khối nhỏ có thể làm tăng chi phí quản lý, phân mảnh và tải bộ gom rác.

Ngược lại, **một lần cấp phát lớn** cũng có thể đắt khi phải khởi tạo hoặc sao chép nhiều phần tử.

### 7.2. Chi phí khấu hao của mảng động

Nếu mảng động bắt đầu với sức chứa 1 và tăng gấp đôi khi đầy, những lần sao chép sẽ di chuyển lần lượt khoảng:

```text
1, 2, 4, 8, 16, ...
```

Với `m` lần thêm cuối từ mảng rỗng, tổng số phần tử sao chép qua các lần mở rộng là:

\[
1+2+4+\cdots <2m.
\]

Cộng thêm `m` lần ghi phần tử mới, tổng công việc là O(m), nên thời gian **khấu hao** cho mỗi lần thêm cuối là O(1). Tuy nhiên, một lời gọi phải mở rộng có thể tốn Θ(n), và bộ nhớ đỉnh vẫn có thể tăng đáng kể.

**Khấu hao về thời gian không phải “khấu hao byte RAM”.** Bộ nhớ đang giữ phải được phân tích theo sức chứa thật tại thời điểm xét, không chia đều số byte cấp phát trên số lời gọi rồi kết luận mỗi lời gọi chỉ cần O(1) RAM.

### 7.3. Thêm nút liên kết và mở rộng mảng là đánh đổi

| Yếu tố | Mảng động | Danh sách liên kết |
| --- | --- | --- |
| Số lần cấp phát để thêm nhiều phần tử | Thường ít lần cấp phát khối lớn | Có thể một lần cấp phát cho mỗi nút |
| Thời gian mỗi lần thêm cuối | O(1) khấu hao, có lần O(n) | O(1) khi có `tail` và cấp phát nút theo mô hình |
| Bộ nhớ dư | Ô vùng đệm chưa dùng | Header/nút/con trỏ; có thể thêm phân mảnh |
| Tính cục bộ khi duyệt | Thường tốt | Có thể kém hơn vì lần theo con trỏ |
| Xóa giữa khi biết vị trí | Có thể phải dịch phần tử | O(1) khi có con trỏ cần thiết |
| Trường hợp cấp phát khó | Resize vùng lớn | Nhiều khối nhỏ hoặc thiếu vùng cho nút |

Cả hai có thể đúng hợp đồng của một kiểu dữ liệu, nhưng hiệu năng thực tế phụ thuộc tần suất thao tác và mô hình bộ nhớ.

## 8. Stack, Queue và Deque: cùng hành vi, cách trả chi phí khác nhau

**Stack** (LIFO) và **Queue** (FIFO) mô tả quy luật thao tác, không quy định cách lưu từng byte.

### 8.1. Stack

- **Stack bằng mảng động:** `push` thường ghi cuối, `pop` bỏ cuối. Số phần tử có thể thay đổi mà không cần một đối tượng nút riêng cho mỗi phần tử. Việc mở rộng có thể gây sao chép hàng loạt.
- **Stack bằng danh sách liên kết:** `push` tạo nút và nối ở đầu; `pop` tháo nút đầu. Chi phí thao tác liên kết có thể O(1), nhưng mỗi nút thêm con trỏ và có thể một lần cấp phát riêng.

Nếu stack thường tăng lên một kích thước lớn rồi giảm, mảng động không thu nhỏ có thể vẫn giữ vùng đệm lớn. Nếu dùng pool nút cho danh sách liên kết, phần nút đã thu hồi cũng có thể được giữ lại để tái sử dụng. **Không có thiết kế nào tự bảo đảm RAM giảm ngay khi `size` giảm.**

### 8.2. Queue

Queue dùng mảng vòng thường có `buffer`, `head` và `size`. Nó tránh dồn toàn bộ dữ liệu về đầu sau mỗi `dequeue` bằng cách sử dụng chỉ số vòng:

\[
\operatorname{index}(i)=(head+i)\bmod capacity.
\]

Khi cài đặt tốt, `enqueue`/`dequeue` có chi phí thời gian O(1) thường hoặc khấu hao; vùng nhớ chủ yếu là các ô của `buffer`.

Queue dùng liên kết đầu/đuôi cần mỗi nút có `next` và đôi khi một đối tượng độc lập; nó không phải sao chép toàn bộ vùng nhớ khi tăng số phần tử, nhưng có chi phí quản lý nút.

### 8.3. Deque có thể dùng nhiều khối thay vì một mảng

Một deque có thể sử dụng những khối chứa nhiều phần tử và các tham chiếu liên kết giữa khối để hỗ trợ thêm/xóa ở cả hai đầu. Số byte cho mỗi phần tử phụ thuộc kích thước khối, số ô chưa sử dụng và metadata cho mỗi khối.

Vì thế, không nên đoán rằng một đối tượng `deque` luôn có một con trỏ riêng cho **mỗi** phần tử, hoặc một mảng liên tục duy nhất. Hình thức tổ chức vật lý tùy cài đặt thư viện.

## 9. Bảng băm: mục dữ liệu, bucket, hệ số tải và rehash

Bảng băm thường cài đặt Map hoặc Set. Ngoài thông tin khóa và giá trị, nó cần có chỗ để xác định vị trí hoặc xử lý va chạm.

### 9.1. Tải và số bucket

Gọi:

- `n` là số mục.
- `b` là số bucket hoặc số vị trí bảng, tùy phương án.
- `α=n/b` là **hệ số tải** theo mô hình đang dùng.

Với phương án **chaining** (mỗi bucket trỏ đến danh sách/cấu trúc các mục), mô hình bộ nhớ có thể là:

\[
M_{\mathrm{hash}}(n,b)
\approx H+b\,p+n(e+\ell+a),
\]

trong đó `p` là byte tham chiếu bucket, `e` là dữ liệu khóa/giá trị mỗi mục, `\ell` là liên kết/metadata mục và `a` là chi phí quản lý/căn chỉnh bình quân.

Nếu `b≈n/α`, riêng bảng bucket tốn:

\[
\frac{b\,p}{n}\approx\frac{p}{\alpha}
\quad\text{byte/phần tử}.
\]

Giảm `α` (nhiều bucket hơn so với số mục) có thể giảm va chạm theo kỳ vọng, nhưng **tăng chi phí vùng bucket trên mỗi phần tử**.

Trong **open addressing**, các mục thường được đặt trực tiếp trong một bảng ô, nên công thức khác: phải tính ô trống, ô đã xóa (*tombstone*) và metadata trạng thái/kiểm soát. Không được áp dụng chi phí nút liên kết của chaining cho mọi bảng băm.

### 9.2. Ví dụ giả định về bucket

Giả sử mỗi tham chiếu bucket rộng 8 byte, có `n=100.000` mục:

| Số bucket `b` | Hệ số tải `α` | Byte vùng tham chiếu bucket | Byte bucket trên mỗi mục |
| --- | --- | --- | --- |
| 50.000 | 2 | 400.000 | 4 |
| 100.000 | 1 | 800.000 | 8 |
| 200.000 | 0,5 | 1.600.000 | 16 |

Bảng này chỉ tính **vùng tham chiếu bucket giả định**, chưa có khóa, giá trị, node, metadata hoặc chi phí allocator. Nó không dự đoán độ phức tạp của bất kỳ thư viện hash table cụ thể nào.

### 9.3. Rehash tăng bộ nhớ đỉnh

Khi tăng số bucket, bảng băm có thể phải tạo bảng mới rồi chuyển hoặc đánh chỉ mục lại từng mục. Trong thời gian chuyển, bảng cũ và mới cùng tồn tại.

Với ví dụ bảng bucket cũ `b` và mới `2b`, riêng vùng bucket có thể đạt gần `3b\,p` byte trước khi giải phóng vùng cũ, chưa kể các mục dữ liệu. Nếu cài đặt còn tạo mục mới thay vì tái sử dụng, bộ nhớ đỉnh có thể lớn hơn.

**Tối ưu thời gian truy cập theo khóa có thể phải trả chi phí bộ nhớ và độ trễ hiếm gặp khi rehash.** Đây là lý do cần xem cả hệ số tải, chính sách mở rộng và giới hạn RAM.

## 10. Cây và Heap: cấu trúc nút so với mảng

### 10.1. Cây tìm kiếm nhị phân

Một nút cây tìm kiếm có thể chứa:

- Khóa hoặc tham chiếu tới khóa.
- Con trỏ `left` và `right`.
- Con trỏ `parent` nếu thiết kế cần.
- Thông tin cân bằng như chiều cao hoặc màu trong cây AVL/đỏ-đen.
- Overhead đối tượng và cấp phát.

Nếu một nút có payload `v` byte, hai con trỏ con `2p`, metadata `m` và overhead `a`, có thể ước tính:

\[
M_{\mathrm{tree}}(n)
\approx H+n(v+2p+m+a).
\]

Một cây tìm kiếm cân bằng có tìm/chèn/xóa theo khóa O(log n) trường hợp xấu nhất, nhưng phải duy trì thông tin nút và các liên kết. Chi phí bộ nhớ phụ từng nút là phần đánh đổi so với mảng đóng gói.

**Chiều cao cây và số byte trên mỗi nút là hai đại lượng khác nhau.** Cân bằng giúp giới hạn thời gian đi theo đường tìm, không tự động làm một nút dùng ít byte hơn.

### 10.2. Heap nhị phân

Heap nhị phân thường biểu diễn bằng **mảng**: nút có chỉ số `i` có con ở chỉ số `2i+1` và `2i+2` (khi các chỉ số ấy tồn tại). Do đó không cần lưu `left`/`right` trong từng phần tử.

Với các ô dữ liệu kích thước `s`:

\[
M_{\mathrm{heap}}(n,C)\approx H+C\,s
\]

nếu payload được lưu trực tiếp trong ô; thêm bộ nhớ đối tượng được tham chiếu nếu dùng tham chiếu.

Cách biểu diễn này giúp heap có overhead cấu trúc thấp hơn cây dựa trên nút trong nhiều môi trường. Đổi lại, heap chỉ cam kết quan hệ ưu tiên cha–con, **không** thay thế một cây tìm kiếm có thứ tự cho mọi truy vấn theo khóa.

### 10.3. Ví dụ quyết định

Một hệ thống chỉ cần lấy nhiệm vụ có độ ưu tiên thấp nhất và thêm nhiệm vụ:

- Heap mảng thường phù hợp: `peek_min` O(1), thêm/lấy O(log n).
- Cây cân bằng có thể hỗ trợ thêm truy vấn thứ tự, nhưng cần nút và metadata.
- Bảng băm tốt cho tra theo ID, nhưng không tự hỗ trợ lấy mục ưu tiên thấp nhất.

Hãy chọn theo **hợp đồng thao tác trước**, rồi so sánh overhead byte của các cài đặt đáp ứng được hợp đồng đó.

## 11. Đồ thị: ma trận kề, danh sách kề và biểu diễn nén

Đồ thị cho thấy rõ sự khác biệt giữa độ phức tạp không gian và số byte vật lý. Đặt `V` là số đỉnh, `E` là số cạnh.

### 11.1. Ma trận kề

Ma trận kề có `V²` vị trí cho quan hệ cạnh có hướng. Nếu dùng **một byte cho mỗi cặp đỉnh**, chi phí phần ô là khoảng:

\[
M_{\mathrm{matrix,byte}}\approx V^2\ \text{byte}.
\]

Nếu biểu diễn như một **bitset đóng gói** với một bit cho mỗi cặp đỉnh, chi phí lý thuyết phần bit là:

\[
M_{\mathrm{matrix,bit}}\approx\left\lceil\frac{V^2}{8}\right\rceil
\ \text{byte},
\]

chưa kể căn chỉnh hàng, header và metadata. Với ma trận là danh sách của nhiều danh sách/đối tượng Python, số byte có thể lớn hơn đáng kể so với hai mô hình đóng gói trên.

Truy vấn `has_edge(u,v)` theo chỉ số có thể O(1) trong mô hình RAM, nhưng ma trận vẫn lưu cả những cạnh **không tồn tại**.

### 11.2. Danh sách kề

Danh sách kề lưu danh sách láng giềng của từng đỉnh. Bộ nhớ thường O(V+E), nhưng số byte cụ thể gồm:

- `V` header hoặc tham chiếu tới các danh sách kề.
- Các vùng chứa cạnh thực sự có.
- Dung lượng dư của những danh sách động.
- Có thể thêm con trỏ hoặc đối tượng cho từng cạnh và định danh đỉnh.

Với đồ thị vô hướng, một cạnh thường được lưu hai lần, một lần tại mỗi đầu. Hệ số này quan trọng khi ước tính byte, dù không thay đổi O(V+E).

### 11.3. CSR: giảm overhead cho đồ thị gần như bất biến

*Compressed Sparse Row* (CSR) là cách biểu diễn danh sách kề bằng các mảng liên tục:

- `offsets` có `V+1` phần tử, xác định vị trí bắt đầu/kết thúc vùng kề của mỗi đỉnh.
- `neighbors` có `E` phần tử với đồ thị có hướng, chứa định danh đỉnh đích của từng cạnh.

Nếu mỗi chỉ số/định danh được lưu trong ô 4 byte (giả định `V,E` nằm trong miền cho phép), chi phí phần dữ liệu chỉ số xấp xỉ:

\[
M_{\mathrm{CSR,index}}
\approx4(V+1)+4E\ \text{byte}.
\]

Cần thêm mảng trọng số nếu đồ thị có trọng số, và metadata của các mảng. CSR giúp giảm số đối tượng nhỏ, cải thiện tính cục bộ khi duyệt, nhưng **chèn/xóa cạnh tùy ý** có thể đòi dịch phần tử hoặc xây lại chỉ mục — khác với danh sách kề có khả năng cập nhật động.

### 11.4. Tính thử trên đồ thị thưa

Giả sử đồ thị có hướng, không trọng số với:

- `V=10.000` đỉnh.
- `E=20.000` cạnh.

Chỉ xét phần thông tin cạnh/index theo các giả định nêu trên:

| Biểu diễn | Phép tính | Byte xấp xỉ |
| --- | --- | --- |
| Ma trận 1 byte/ô | `10.000²×1` | 100.000.000 |
| Ma trận bitset đóng gói | `10.000²/8` | 12.500.000 |
| CSR, chỉ số 4 byte | `4(10.001+20.000)` | 120.004 |

Không nên so sánh ba con số như “số byte RAM thật” của các thư viện: chúng cố tình bỏ qua header, căn chỉnh, metadata, khả năng truy cập và cách lưu đối tượng. Nhưng chúng cho thấy ở đồ thị thưa, **lựa chọn biểu diễn quyết định quy mô bộ nhớ**. Một ma trận vẫn có thể đáng dùng khi đồ thị dày và ứng dụng kiểm tra cạnh rất nhiều.

## 12. Các kỹ thuật giảm chi phí bộ nhớ trên mỗi phần tử

### 12.1. Lưu giá trị đóng gói thay vì nhiều đối tượng nhỏ

Nếu dữ liệu là số có kiểu và miền giá trị rõ ràng, một mảng số nguyên đóng gói có thể phù hợp hơn danh sách chứa các đối tượng số nguyên riêng.

Ví dụ Python:

```python
from array import array

values = list(range(1000))
packed = array("q", range(1000))

print(packed.itemsize)  # Số byte mỗi phần tử theo môi trường chạy.
```

`array("q")` chứa số nguyên có dấu kiểu `long long` C, với kích thước kiểm tra được bằng `itemsize`; các giá trị phải nằm trong miền biểu diễn của kiểu ấy. `list` của Python lưu tham chiếu tới đối tượng, nên hai cấu trúc có hành vi và giới hạn kiểu khác nhau.

Không được chuyển sang kiểu số hẹp hơn nếu giá trị có thể vượt miền hoặc nếu phép toán yêu cầu một ngữ nghĩa khác.

### 12.2. Chia sẻ dữ liệu bất biến

Nhiều bản ghi có cùng nhãn hoặc khóa bất biến có thể tham chiếu tới cùng một đối tượng thay vì tạo bản sao của nội dung.

Tuy vậy, chia sẻ **đối tượng có thể thay đổi** có thể gây lỗi aliasing: sửa một vị trí làm thay đổi giá trị được quan sát từ những vị trí khác. Tiết kiệm bộ nhớ không được làm sai hợp đồng dữ liệu.

### 12.3. Dùng đối tượng có trường cố định khi phù hợp

Trong Python, một lớp có `__dict__` trên từng instance có thể có overhead cao hơn lớp sử dụng `__slots__` để khai báo các trường cố định. Chẳng hạn:

```python
class LinkedNode:
    __slots__ = ("value", "next")

    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node
```

`__slots__` có thể giảm chi phí bộ nhớ của các instance trong một số trường hợp, nhưng thay đổi khả năng thêm thuộc tính động, cách tương tác với kế thừa và các cơ chế liên quan. Không nên khẳng định một mức tiết kiệm byte cố định nếu chưa đo trên runtime mục tiêu.

### 12.4. Dùng khối/pool thay vì cấp phát từng nút

Một pool cấp phát nhiều nút cùng lúc có thể giảm số lời gọi allocator và phân mảnh. Nhưng nó có thể giữ bộ nhớ lâu ngay cả khi một số nút không còn được sử dụng, và cần quản lý đúng danh sách ô trống.

Chiến lược này phù hợp khi cấu trúc thường xuyên tạo/hủy đối tượng cùng kích thước, **nếu** lợi ích được xác nhận bằng phép đo và không gây lỗi sử dụng lại ô đã giải phóng.

### 12.5. Chọn cấu trúc nén theo loại truy vấn

- Bitset có thể phù hợp khi lưu tập giá trị nhỏ trong miền chỉ số đã biết.
- CSR có thể phù hợp với đồ thị ít cập nhật, duyệt cạnh nhiều.
- Cây/Map có thêm chỉ mục có thể tăng bộ nhớ nhưng giảm thời gian tìm.
- Mảng động giảm nhiều khối cấp phát nhỏ, đổi lại sức chứa dự phòng và chi phí resize.

**Nén bộ nhớ không phải mục tiêu độc lập:** nếu biến một cập nhật O(1) thành O(n) vì phải dịch dữ liệu nén, cần tính cả tần suất cập nhật.

## 13. Đo bộ nhớ trong Python: kiểm tra đúng thứ mình đang đo

Các số byte giả định chỉ phục vụ lập luận. Khi có ứng dụng cụ thể, cần đo trên phiên bản Python, kiến trúc và bộ dữ liệu mục tiêu.

### 13.1. `sys.getsizeof` là phép đo nông

`sys.getsizeof(obj)` trả kích thước của đối tượng `obj` theo cách Python báo cáo, nhưng **không tự đệ quy cộng tất cả đối tượng mà `obj` tham chiếu tới**.

```python
import sys

items = [[1, 2, 3], [4, 5, 6]]

print(sys.getsizeof(items))     # Kích thước container list ngoài.
print(sys.getsizeof(items[0]))  # Kích thước container list con.
```

Lấy `sys.getsizeof(items)` rồi gọi đó là “tổng bộ nhớ của toàn bộ đồ thị đối tượng” là không chính xác. Nếu tự viết hàm cộng kích thước sâu, phải dùng tập các đối tượng đã thấy để tránh đếm trùng khi có nhiều tham chiếu đến cùng một đối tượng.

`sys.getsizeof` cũng không phải phép đo trực tiếp tổng RSS của tiến trình hay chi phí mọi vùng nhớ do thư viện C ngoài Python quản lý.

### 13.2. `tracemalloc` cho phép theo dõi cấp phát được Python ghi nhận

Ví dụ đo cấp phát xảy ra trong một đoạn mã:

```python
import tracemalloc

tracemalloc.start()
tracemalloc.reset_peak()

before_current, _ = tracemalloc.get_traced_memory()

data = [{"id": i, "score": i % 10} for i in range(10000)]

after_current, peak = tracemalloc.get_traced_memory()

print("Mức tăng đang được theo dõi:", after_current - before_current)
print("Đỉnh được theo dõi trong phiên:", peak)
```

Đây là ví dụ minh họa cách lấy số đo, **không phải kết quả đã thực thi**. Một số lưu ý:

- `tracemalloc` theo dõi những cấp phát nằm trong phạm vi mà công cụ ghi nhận; nó không có nghĩa số đo bằng toàn bộ bộ nhớ RSS của tiến trình.
- `peak` là đỉnh của các cấp phát được theo dõi kể từ lúc bắt đầu hoặc lần đặt lại đỉnh; nếu cần tính mức tăng đỉnh riêng của thao tác, phải đặt mốc thích hợp và trừ baseline khi diễn giải.
- Các đối tượng khác tạo trong quá trình đo, bộ nhớ được giữ để tái sử dụng, và sự khác biệt giữa các runtime có thể ảnh hưởng số đo.
- So sánh các phương án trong điều kiện dữ liệu và vòng đời đối tượng tương đương, tránh giữ các bản thử trước ngoài ý muốn.

### 13.3. Bộ nhớ tiến trình không chỉ là các đối tượng Python

Một trình giám sát hệ điều hành có thể báo `RSS` hoặc những chỉ số khác về bộ nhớ tiến trình. Chúng phản ánh nhiều thành phần hơn, như trang nhớ, thư viện, heap của runtime và những vùng không được công cụ Python theo dõi.

Khi báo kết quả, nên ghi rõ **chỉ số**, **công cụ đo**, **thời điểm**, **môi trường**, **số phần tử** và **phạm vi sở hữu dữ liệu**. Không nên đặt hai số đo khác phạm vi cạnh nhau rồi kết luận cấu trúc nào “dùng ít RAM hơn”.

### 13.4. Những yếu tố cần kiểm soát khi benchmark

| Yếu tố | Rủi ro nếu bỏ qua |
| --- | --- |
| Dữ liệu thực hay đối tượng dùng chung | Có thể đếm thiếu hoặc đếm trùng payload |
| Đo trước/sau khi tạo đối tượng | Có thể tính nhầm chi phí của bước chuẩn bị |
| Cấu trúc giữ sức chứa dự phòng | Bộ nhớ sau `pop` không giảm ngay |
| Đang ở giữa resize/rehash | Có thể nhìn thấy đỉnh tạm thời rất cao |
| Số lần lặp và làm nóng môi trường | Chi phí cấp phát/thu hồi thay đổi giữa các lần |
| Phiên bản runtime và kiến trúc | Độ rộng con trỏ, header, allocator có thể khác |
| Phạm vi công cụ đo | `getsizeof`, `tracemalloc` và RSS đo những đại lượng khác nhau |

## 14. Tính một ngân sách RAM trước khi chọn cấu trúc

Giả sử dịch vụ có giới hạn RAM dành cho cấu trúc dữ liệu là `L` byte, phải lưu `n` phần tử. Một ước lượng hữu ích gồm:

\[
M_{\mathrm{retained}}(n)\leq L,
\]

và thêm điều kiện về bộ nhớ đỉnh:

\[
M_{\mathrm{peak}}(n)\leq L.
\]

Điều kiện thứ nhất chưa đủ nếu các thao tác resize hoặc rebuild tạo thêm bản sao lớn. Trong thực tế cần dự phòng bộ nhớ cho runtime, luồng xử lý, đầu vào/đầu ra và các cấu trúc khác; không nên dành toàn bộ RAM tiến trình cho riêng một vùng dữ liệu.

### 14.1. Bài toán giả định

Một ứng dụng lưu 1.000.000 bản ghi, mỗi bản ghi có 16 byte payload đóng gói. So sánh hai mô hình:

- **A — Mảng đóng gói:** 16 byte dữ liệu trực tiếp cho mỗi phần tử, giả sử sức chứa bằng kích thước và bỏ qua header chung.
- **B — Nút độc lập:** 16 byte payload + 8 byte con trỏ + 16 byte overhead/căn chỉnh giả định.

Khi đó:

\[
M_A=1.000.000\times16=16.000.000\ \text{byte}
\]

\[
M_B=1.000.000\times(16+8+16)
=40.000.000\ \text{byte}.
\]

B cần thêm khoảng 24 MB trong mô hình thô. Nếu runtime còn thêm quản lý đối tượng riêng, chênh lệch có thể khác. Những số này **không phải benchmark** của Python hoặc một thư viện cụ thể.

### 14.2. Khi nào vẫn nên chọn phương án tốn RAM hơn?

Nếu ứng dụng thường xuyên chèn hoặc xóa phần tử gần nút đã biết, danh sách liên kết có thể tránh dịch hàng trăm nghìn phần tử trong mảng. Việc trả thêm RAM có thể đổi lại thời gian cập nhật thấp hơn.

Ngược lại, nếu chủ yếu duyệt tuần tự và truy cập theo chỉ số, mảng liên tục thường hấp dẫn về số byte và tính cục bộ.

Vì vậy, lựa chọn phải giữ đúng **giao diện sử dụng và bất biến**, rồi mới tối ưu tài nguyên.

## 15. Những nhầm lẫn thường gặp

| Nhận định | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Hai cấu trúc đều O(n) nên dùng RAM bằng nhau.” | Big-O bỏ hệ số và overhead mỗi phần tử. | Tính payload, con trỏ, header, sức chứa dư và byte đỉnh. |
| “Một số nguyên 64 bit luôn chỉ dùng 8 byte trong mọi ngôn ngữ.” | Có thể lưu trong đối tượng có header hoặc qua tham chiếu. | Phân biệt giá trị đóng gói và biểu diễn đối tượng của runtime. |
| “Danh sách liên kết chèn O(1) nên không có chi phí khác.” | Phải cấp phát nút và có con trỏ/metadata; có thể phải tìm vị trí trước. | Tính cả cấp phát, byte/nút và thao tác thực tế. |
| “`size` giảm thì RAM cũng giảm ngay.” | Vùng đệm, pool hoặc allocator có thể giữ lại byte. | Đo bộ nhớ đang giữ và quy tắc thu nhỏ thực tế. |
| “Một lần thêm còn chỗ cấp phát 0 byte, nên mảng không tốn thêm bộ nhớ.” | Vùng chứa đã cấp phát trước đó và được chia sẻ cho nhiều lần thêm. | Tính theo sức chứa và tổng vòng đời. |
| “`getsizeof(list)` là tổng kích thước mọi phần tử bên trong.” | Nó không tự cộng đệ quy đối tượng được tham chiếu. | Ghi rõ phép đo nông; tránh đếm trùng trong đo sâu. |
| “Hash Map tìm nhanh nên luôn tiết kiệm bộ nhớ.” | Bucket và khoảng trống có overhead riêng. | Xét hệ số tải, chiến lược va chạm và rehash. |
| “Độ phức tạp khấu hao O(1) nghĩa là đỉnh bộ nhớ O(1).” | Resize có thể cần hai vùng lớn đồng thời. | Phân tích thời gian khấu hao và bộ nhớ đỉnh riêng. |
| “Ma trận kề luôn tốn đúng `V²` byte.” | Có thể lưu 1 byte/ô, nhiều byte/ô hoặc bitset. | Nêu đơn vị ô/bit và cách biểu diễn. |
| “Cứ dùng pool là tiết kiệm RAM.” | Pool có thể giữ nhiều ô trống lâu hơn cần thiết. | Đo cả mức đang dùng và mức giữ lại sau nhiều lần xóa. |

## 16. Bài tập vận dụng có gợi ý giải

### Bài 1 — Bộ nhớ mỗi phần tử của mảng động

Mảng có `size=75.000`, `capacity=100.000`, mỗi ô tham chiếu rộng 8 byte. Bỏ qua header và dữ liệu đối tượng được tham chiếu. Tính bộ nhớ vùng ô, byte vùng ô hiệu dụng mỗi phần tử và phần trăm ô đang dùng.

**Gợi ý:** Bộ nhớ vùng ô `100.000×8=800.000` byte; chia cho 75.000 được khoảng `10,67` byte/phần tử. Mức sử dụng `75.000/100.000=75%`. Phần 200.000 byte còn lại là ô dự phòng theo mô hình.

### Bài 2 — Mảng so với nút liên kết

Giả sử một phần tử có payload 8 byte. Một nút liên kết đơn thêm 8 byte con trỏ và 16 byte overhead; mảng đóng gói không có dung lượng dư. Với 200.000 phần tử, chênh lệch bộ nhớ là bao nhiêu?

**Gợi ý:** Mảng `8×200.000=1,6` MB. Liên kết đơn `(8+8+16)×200.000=6,4` MB. Chênh lệch `4,8` MB, theo các giả định đã cho; không phải giá trị thực của mọi runtime.

### Bài 3 — Căn chỉnh khối

Bộ cấp phát giả định làm tròn mọi khối lên bội của 16 byte. Một nút cần 33 byte trước khi làm tròn. Mỗi nút thực tế được cấp bao nhiêu byte? Với 10.000 nút, số byte dư do làm tròn là bao nhiêu?

**Gợi ý:** Làm tròn lên 48 byte, dư 15 byte/nút. Với 10.000 nút, dư 150.000 byte; chưa tính metadata khác.

### Bài 4 — Bộ nhớ đỉnh khi resize

Một mảng có `capacity=4096` ô, mỗi ô rộng 8 byte, đang đầy. Khi mở rộng, runtime cấp vùng mới `8192` ô và giữ vùng cũ cho tới khi sao chép xong. Tính byte vùng ô cũ, vùng mới, bộ nhớ đỉnh và bộ nhớ sau khi giải phóng vùng cũ.

**Gợi ý:** Cũ `4096×8=32.768` byte; mới `8192×8=65.536` byte. Đỉnh `98.304` byte; sau chuyển còn `65.536` byte của vùng ô mới, chưa kể metadata và payload khác.

### Bài 5 — Hai cách dùng tham chiếu

Có 10.000 mục trong một list. Tất cả mục trỏ tới **cùng một** đối tượng kích thước 100 byte theo mô hình giả định. So sánh với 10.000 đối tượng độc lập cùng kích thước, biết mỗi ô tham chiếu là 8 byte và bỏ qua header list.

**Gợi ý:** Trường hợp chia sẻ: `10.000×8+100=80.100` byte. Trường hợp độc lập: `10.000×8+10.000×100=1.080.000` byte. Không được nhân dung lượng đối tượng dùng chung 10.000 lần.

### Bài 6 — Chi phí bucket của Hash Map

Một bảng băm chaining có `n=50.000` mục, `b=100.000` bucket, mỗi bucket là một con trỏ 8 byte. Tính hệ số tải và overhead vùng bucket tính trên mỗi mục.

**Gợi ý:** `α=n/b=0,5`. Vùng bucket `800.000` byte, tương đương `16` byte/mục. Còn phải cộng vùng khóa/giá trị/nút và overhead khác.

### Bài 7 — Ma trận kề và CSR

Đồ thị có hướng có `V=5000` và `E=15.000`. Giả sử ma trận kề dùng bitset, còn CSR dùng chỉ số 4 byte. Tính phần bộ nhớ mô hình của mỗi biểu diễn.

**Gợi ý:** Bitset `5000²/8=3.125.000` byte. CSR `4(5001+15.000)=80.004` byte. Hai số chưa có metadata, căn chỉnh hay dữ liệu trọng số. Nếu thường xuyên thêm/xóa cạnh, CSR có thể cần nhiều công việc cập nhật hơn.

### Bài 8 — Vì sao giảm `size` chưa giảm RAM?

Một stack mảng động có lúc chứa 1.000.000 phần tử, sau đó `pop` còn 10 phần tử. Vùng đệm không tự thu nhỏ.

**Gợi ý:** `size` giảm nhưng `capacity` có thể vẫn phản ánh kích thước lớn nhất đã đạt; vùng nhớ các ô dự phòng còn được giữ lại. Cần xét chính sách thu nhỏ hoặc tạo một vùng mới nhỏ hơn. Nếu các phần tử bị loại vẫn còn được tham chiếu ở nơi khác, bộ nhớ của đối tượng đó không nhất thiết được thu hồi.

### Bài 9 — Đo sai với `sys.getsizeof`

Một lập trình viên so sánh `sys.getsizeof(list_of_objects)` với tổng kích thước payload trong mảng đóng gói rồi kết luận list “nhẹ hơn”. Điều gì chưa được tính?

**Gợi ý:** `getsizeof` của list thường chỉ phản ánh vùng chứa và ô tham chiếu, không tự cộng các đối tượng được tham chiếu. Cần thống nhất phạm vi sở hữu dữ liệu, tránh đếm trùng những đối tượng dùng chung và đo với runtime thực tế.

### Bài 10 — Chọn cấu trúc cho dịch vụ thực tế

Một dịch vụ có hai tính năng: (A) xử lý hàng đợi FIFO với rất nhiều thao tác đầu/cuối; (B) lưu đồ thị thưa gần như không đổi và thường xuyên duyệt láng giềng. Nên cân nhắc biểu diễn nào để giảm cấp phát và chi phí bộ nhớ?

**Gợi ý:** Với (A), Queue mảng vòng hoặc deque theo khối có thể tránh cấp phát một nút độc lập cho mỗi phần tử; cần kiểm tra sức chứa dư và chính sách resize. Với (B), danh sách kề dạng mảng hoặc CSR có thể tiết kiệm nhiều byte so với ma trận kề hoặc đồ thị xây từ nhiều đối tượng nút; nếu thêm/xóa cạnh thường xuyên, phải cân nhắc chi phí cập nhật của CSR.

## 17. Mẫu đánh giá byte/phần tử và chi phí cấp phát

Dùng mẫu này trước khi chọn hoặc tối ưu cấu trúc dữ liệu:

```text
Bài toán / hợp đồng thao tác:
Số phần tử hiện tại n:
Số phần tử lớn nhất dự kiến:
Kiểu dữ liệu và kích thước payload:
Môi trường / kiến trúc / runtime:

Biểu diễn:
  Mảng, nút liên kết, bucket, cây, heap, đồ thị?
  Dữ liệu trực tiếp hay tham chiếu?
  Những đối tượng nào được cấu trúc sở hữu?
  Có dùng chung đối tượng hay không?

Bộ nhớ đang giữ:
  Header cố định:
  Số ô hoặc sức chứa C:
  Byte mỗi ô:
  Byte metadata mỗi phần tử:
  Byte căn chỉnh/allocator ước lượng:
  Byte hiệu dụng trên mỗi phần tử (n > 0):
  Bộ nhớ đầu ra và phụ trợ:

Cấp phát và cập nhật:
  Số lần cấp phát cho n phần tử:
  Có resize/rehash/thu nhỏ không?
  Tổng byte được sao chép:
  Bộ nhớ đỉnh khi chuyển đổi:
  Phân mảnh hoặc pool giữ byte không sử dụng:

Thời gian:
  Truy cập / tìm kiếm / thêm / xóa / duyệt:
  Trường hợp xấu nhất:
  Chi phí kỳ vọng hoặc khấu hao (nếu áp dụng):

Đo đạc:
  Công cụ: getsizeof, tracemalloc, RSS, profiler khác?
  Phạm vi và thời điểm đo:
  Kích thước và phân bố dữ liệu thử:
  Giả định nào cần xác minh trên runtime thật?

Kết luận:
  Có đáp ứng giới hạn RAM và bộ nhớ đỉnh?
  Có giữ đúng bất biến và hợp đồng?
  Chi phí cập nhật có chấp nhận được?
```

**Điểm cốt lõi:** bộ nhớ O(n) mới nói lượng bộ nhớ tăng theo số phần tử; nó chưa nói **n phần tử tốn bao nhiêu byte**. Một lựa chọn tốt phải tính cả ô dữ liệu, con trỏ, header, sức chứa dư, cấp phát, phân mảnh, vùng nhớ tạm và bộ nhớ đỉnh. Khi đặt những chi phí đó cạnh độ phức tạp truy cập, tìm kiếm, chèn, xóa và duyệt, ta có cơ sở cụ thể để chọn cấu trúc dữ liệu hiệu quả và vẫn đúng hợp đồng.
