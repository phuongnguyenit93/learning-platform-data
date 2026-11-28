# Vai trò của phân bố dữ liệu và chuỗi thao tác thực tế

> **Chương:** Đặc tả và chi phí · **Bài học:** Vai trò của phân bố dữ liệu và chuỗi thao tác thực tế

Hai ứng dụng đều lưu 100.000 hồ sơ trong một Map. Ứng dụng A gần như chỉ tìm lại 20 mã hồ sơ phổ biến; ứng dụng B nhận liên tục các khóa mới, xóa khóa cũ, đôi khi liệt kê mọi hồ sơ theo thứ tự tăng dần. Dù số hồ sơ gần như bằng nhau, cấu trúc dữ liệu phù hợp và hiệu năng quan sát được có thể khác hẳn.

Tương tự, hai đồ thị cùng có 10.000 đỉnh và 20.000 cạnh có thể khác nhau: một đồ thị có cạnh phân bố khá đều, đồ thị còn lại có vài đỉnh trung tâm nối với rất nhiều đỉnh. Nếu các truy vấn luôn bắt đầu từ đỉnh trung tâm, lượng công việc và vùng nhớ được chạm tới sẽ khác với việc bắt đầu ở một đỉnh trong thành phần nhỏ.

Bài học này tập trung vào hai thông tin dễ bị bỏ sót khi đọc bảng Big-O:

1. **Phân bố dữ liệu:** giá trị, khóa, thứ tự, tần suất, độ dài, mật độ và hình dạng dữ liệu được phân bố thế nào?
2. **Chuỗi thao tác thực tế:** ứng dụng thực sự gọi phép toán gì, theo thứ tự nào, với tần suất và tương quan ra sao?

Đây là một phần của mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`): học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị dựa trên bất biến, thao tác, độ phức tạp thời gian–bộ nhớ, để lựa chọn cấu trúc phục vụ đúng bài toán thay vì chỉ chọn theo một hàng trong bảng độ phức tạp.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Phân biệt **kích thước đầu vào**, **phân bố dữ liệu** và **phân bố thao tác**.
2. Giải thích cách khóa trùng, thứ tự chèn, khóa nóng, độ dài khóa, mật độ cạnh và phân bố bậc đỉnh ảnh hưởng chi phí.
3. Lập mô hình chi phí tổng của một chuỗi gồm truy cập, tìm kiếm, chèn, xóa và duyệt.
4. Phân biệt thời gian **xấu nhất**, **trung bình/kỳ vọng theo phân bố** và **khấu hao theo chuỗi thao tác**.
5. Phân tích các ví dụ thực tế trên mảng, danh sách liên kết, bảng băm, cây, Stack, Queue, Heap và Graph.
6. Thiết kế phép đo bằng **vết thao tác (workload trace)** có thể tái lập, kiểm tra tính đúng và tránh các sai lầm benchmark thông dụng.
7. Đưa ra quyết định dựa trên cả hiệu năng thông thường, độ trễ đỉnh, bộ nhớ và yêu cầu hành vi công khai.

## 2. Ba lớp thông tin phải tách biệt

Khi đánh giá một cấu trúc dữ liệu, hãy chia thông tin thành ba lớp.

| Lớp | Nội dung | Ví dụ |
| --- | --- | --- |
| **Quy mô** | Số phần tử và các tham số kích thước | `n=100.000` mục, `V=10.000` đỉnh, `E=20.000` cạnh |
| **Phân bố dữ liệu** | Giá trị, thứ tự, tỷ lệ trùng, độ dài khóa, bậc đỉnh | 80% khóa thuộc nhóm 100 mã phổ biến; 1% đỉnh có bậc rất cao |
| **Vết thao tác** | Những lệnh thực sự được gọi, thứ tự và trạng thái xảy ra | 90% `get`, 8% `put`, 2% `remove`, cập nhật dồn cuối ngày |

Chỉ biết `n` là chưa đủ để ước lượng độ trễ cụ thể. Nhưng phân bố dữ liệu **không thay thế** việc chứng minh độ phức tạp: vẫn cần chặn xấu nhất, điều kiện của kỳ vọng hoặc khấu hao nếu muốn đưa ra một bảo đảm.

### 2.1. Kích thước nên được định nghĩa theo thao tác

Các ký hiệu sẽ dùng trong bài:

- `n_t`: số phần tử logic đang có ngay trước thao tác thứ `t`.
- `m`: tổng số thao tác trong vết; `q` là số lần truy vấn, `u` là số lần cập nhật.
- `p_j`: tỷ lệ hoặc xác suất của loại thao tác `j`.
- `k`: độ dài khóa khi phép băm/so sánh không thể xem là hằng số.
- `V,E`: số đỉnh và số cạnh của đồ thị.
- `deg(v)`: số cạnh đi ra từ `v` trong biểu diễn danh sách kề của đồ thị có hướng.
- `C_t`: sức chứa vùng đệm ngay trước thao tác thứ `t`.

Đối với bài toán có nhiều tham số, một công thức như O(V+E) hay O(nk) thường chính xác hơn việc gom tất cả vào một biến không rõ nghĩa.

### 2.2. Vết thao tác khác một danh sách tần suất

Một bảng ghi “50% thêm, 50% xóa” **không cho biết thứ tự** thao tác. Hai chuỗi sau đều có ba lần thêm và ba lần xóa:

```text
A: push, pop, push, pop, push, pop
B: push, push, push, pop, pop, pop
```

Chuỗi A giữ Stack nhỏ; chuỗi B đạt kích thước cực đại lớn hơn. Nếu cấu trúc có cấp phát, tăng sức chứa, thu nhỏ hoặc cache, hai chuỗi có thể khác nhau về bộ nhớ đỉnh và các sự kiện đắt. **Tần suất chỉ là một phần của workload; thứ tự cũng quan trọng.**

## 3. Những kiểu phân bố dữ liệu thường gặp

### 3.1. Thứ tự tăng, giảm, gần sắp xếp và ngẫu nhiên

| Dạng dữ liệu | Đặc điểm | Tác động có thể xảy ra |
| --- | --- | --- |
| Khóa đã tăng dần | Mỗi khóa mới lớn hơn khóa trước | BST không tự cân bằng có thể lệch thành chuỗi |
| Khóa đã giảm dần | Mỗi khóa mới nhỏ hơn khóa trước | BST không tự cân bằng có thể lệch về phía còn lại |
| Gần sắp xếp | Ít phần tử ở sai vị trí | Một số thuật toán sắp xếp thích ứng có thể tận dụng |
| Hoán vị ngẫu nhiên | Không có xu hướng thứ tự rõ theo giả định | Dùng để nghiên cứu kỳ vọng nhưng không đại diện mọi tải |
| Khóa trùng nhiều | Nhiều bản ghi có cùng giá trị hoặc khóa | Cần quy tắc Map/Set/multiset và phép so sánh phù hợp |

**Không được đồng nhất “khóa tăng dần” với “mọi cài đặt đều chậm”.** Ví dụ, chỉ số mảng sắp xếp và tìm nhị phân có thể hưởng lợi vì không cần tiền xử lý sắp. Điều nguy hiểm là **thứ tự chèn tăng dần vào BST không tự cân bằng**, nếu cài đặt đặt khóa lớn hơn luôn về bên phải.

### 3.2. Phân bố đều và phân bố lệch (*skew*)

Giả sử ứng dụng có `n` mã sản phẩm nhưng tỷ lệ tìm theo mã không đều:

- **Đều (uniform):** mỗi mã có xác suất truy vấn xấp xỉ `1/n`.
- **Lệch (skewed):** một nhóm nhỏ mã được truy vấn phần lớn thời gian.
- **Có tính địa phương theo thời gian:** những mã vừa truy vấn có khả năng được truy vấn lại trong khoảng thời gian ngắn.
- **Thay đổi theo đợt:** nhóm mã phổ biến vào buổi sáng khác với nhóm phổ biến buổi chiều.

Các phân bố lệch thường được mô tả bằng “đầu nóng” (*hot keys*) hoặc gần các dạng Zipf trong một số tải thực tế. Tuy nhiên, **không được giả định mọi ứng dụng đều tuân phân bố Zipf** nếu chưa có dữ liệu kiểm chứng.

### 3.3. Khóa trùng, khóa vắng mặt và khóa dài

Ba thuộc tính này ảnh hưởng thao tác theo cách khác nhau:

- **Khóa trùng:** một Map có thể thay giá trị cũ theo cùng khóa; Set bỏ qua phần tử trùng; danh sách có thể giữ tất cả bản sao. Hợp đồng quyết định ý nghĩa.
- **Khóa vắng mặt:** tìm tuyến tính thường phải duyệt hết mảng; tìm trong bảng băm có thể đi hết bucket hoặc chuỗi dò.
- **Khóa dài:** tính hash/so sánh hai chuỗi có thể mất O(k), dù số khóa đang có không đổi.

Một bộ dữ liệu thử chỉ gồm các khóa nguyên ngắn, tất cả khác nhau và chắc chắn tồn tại sẽ che khuất những trường hợp quan trọng này.

### 3.4. Phân bố trên đồ thị

Hai đồ thị cùng `V,E` có thể có:

- Bậc đỉnh khá đồng đều.
- Một số **hub** có rất nhiều cạnh.
- Nhiều thành phần liên thông nhỏ.
- Một thành phần khổng lồ và rất nhiều đỉnh cô lập.
- Tỷ lệ cạnh theo hướng hoặc tự khuyên khác nhau nếu hợp đồng cho phép.

Chi phí duyệt từ một đỉnh, kích thước queue của BFS và khả năng tận dụng cache có thể khác nhiều dù bậc tăng trưởng toàn cục theo `V,E` không đổi.

## 4. Chuỗi thao tác thực tế: điều gì diễn ra giữa hai truy vấn?

Một cấu trúc dữ liệu là **đối tượng có trạng thái**. Chi phí thao tác thứ `t` có thể phụ thuộc những thao tác trước đó.

Ví dụ một Map liên tục nhận:

```text
get(A), get(A), get(B), put(C), remove(D),
put(E), put(F), put(G), get(A), ...
```

Để đánh giá workload này, ngoài tỷ lệ `get/put/remove` còn cần biết:

1. `n_t` thay đổi ra sao theo thời gian?
2. Những khóa nào xuất hiện lặp lại?
3. Tỷ lệ truy vấn tìm thấy so với không tìm thấy?
4. Thao tác nào làm cấu trúc tăng sức chứa hoặc tái tổ chức?
5. Có yêu cầu duyệt toàn bộ hay trả dữ liệu theo thứ tự không?
6. Các cập nhật có dồn thành đợt hay trải đều?
7. Bên gọi có thay đổi giá trị qua tham chiếu làm ảnh hưởng bất biến không?

Một bảng Big-O dùng `n` cố định chỉ là **một lát cắt**; khi kích thước và trạng thái thay đổi, phân tích tổng nên theo thời điểm.

### 4.1. Mô hình tổng chi phí theo vết

Gọi `\tau=(op_1,\ldots,op_m)` là một vết hợp lệ. Với trạng thái trước thao tác thứ `t` là `S_{t-1}` và chi phí thực tế `c(op_t,S_{t-1})`:

\[
T(\tau)=\sum_{t=1}^{m}c(op_t,S_{t-1}).
\]

Nếu có giai đoạn xây cấu trúc từ dữ liệu ban đầu, cộng thêm:

\[
T_{\mathrm{lifecycle}}=B(n_0)+T(\tau).
\]

Phải chú ý các chi phí như mở rộng mảng, tái băm, cân bằng cây đã được tính trong `c` của thao tác gây ra hay chưa. **Không cộng hai lần cùng một chi phí** khi vừa tính `put` vừa thêm một khoản `rehash` khác.

### 4.2. Mô hình theo tỷ lệ thao tác

Nếu trong một giai đoạn kích thước gần `n` và loại thao tác `j` có tỷ lệ `p_j`, một ước lượng là:

\[
\overline{c}(n)\approx\sum_j p_j\,\mathbb{E}[c_j\mid n,\text{mô hình dữ liệu và trạng thái}].
\]

Với `\sum_j p_j=1`. Kỳ vọng ở đây có thể lấy theo phân bố khóa hoặc trạng thái. Đây là **mô hình trung bình có điều kiện**, không tự chứng minh chặn xấu nhất.

Nếu `n_t` biến đổi mạnh hoặc thứ tự thao tác gây nhiều lần rebuild, cần dùng tổng theo vết `T(\tau)` thay vì nhân một chi phí trung bình với `m`.

### 4.3. Ví dụ hai tải có cùng số phần tử

| Tải | Phân bố thao tác | Khả năng phù hợp |
| --- | --- | --- |
| A — Báo cáo cuối ngày | 95% duyệt tuần tự, 5% tìm khóa | Mảng liên tục, dữ liệu sắp nếu cần thứ tự |
| B — Dịch vụ tra cứu | 90% tìm theo mã, 8% cập nhật, 2% duyệt | Bảng băm hoặc cây cân bằng theo yêu cầu |
| C — Lịch tác vụ | 60% thêm nhiệm vụ, 40% lấy ưu tiên nhất | Heap hoặc Priority Queue có hợp đồng phù hợp |
| D — Tương tác đồ thị | 80% kiểm tra cạnh, 20% liệt kê láng giềng | Ma trận kề/tập kề tùy mật độ và RAM |

Các tỷ lệ là **ví dụ giả định**, không phải số đo của một hệ thống thật. Lựa chọn cuối còn phụ thuộc kiểu khóa, độ lớn dữ liệu, bộ nhớ, truy vấn có thứ tự và những yêu cầu chức năng khác.

## 5. Tìm kiếm tuyến tính: vị trí khóa làm thay đổi trung bình

Xét mảng chưa sắp xếp và thuật toán tìm từ trái sang phải:

```python
def linear_search_counted(values, target):
    comparisons = 0
    for i, value in enumerate(values):
        comparisons += 1
        if value == target:
            return i, comparisons
    return -1, comparisons
```

Với `n≥1`:

- Phần tử đầu trùng: 1 lần so sánh.
- Phần tử thứ `i` (đánh số từ 1) trùng lần đầu: `i` lần so sánh.
- Không tìm thấy: `n` lần so sánh.

Vì vậy chi phí **xấu nhất** là Θ(n), bất kể phân bố truy vấn. Nhưng chi phí **trung bình** phụ thuộc xác suất tìm ở từng vị trí và xác suất vắng mặt.

### 5.1. Công thức kỳ vọng theo vị trí

Gọi `p_i` là xác suất vị trí trùng khớp đầu tiên nằm ở vị trí thứ `i`, `i=1,\ldots,n`, và `p_{\emptyset}` là xác suất không tìm thấy. Giả sử các sự kiện này tạo phân hoạch xác suất:

\[
\sum_{i=1}^{n}p_i+p_{\emptyset}=1.
\]

Số phép so sánh kỳ vọng là:

\[
\mathbb{E}[C]
=\sum_{i=1}^{n}i\,p_i+n\,p_{\emptyset}.
\]

Công thức này bao gồm cả các trường hợp truy vấn thiên lệch và vắng mặt. Nếu chắc chắn có mặt, vị trí trùng đầu phân bố đều, `p_i=1/n`, ta được `(n+1)/2` như trong phân tích trung bình quen thuộc.

### 5.2. Ví dụ với năm khóa

Giả sử mảng có năm khóa khác nhau và phân bố truy vấn như sau:

| Kết quả truy vấn | Xác suất | Số so sánh |
| --- | --- | --- |
| Trùng phần tử 1 | 0,54 | 1 |
| Trùng phần tử 2 | 0,09 | 2 |
| Trùng phần tử 3 | 0,09 | 3 |
| Trùng phần tử 4 | 0,09 | 4 |
| Trùng phần tử 5 | 0,09 | 5 |
| Không tìm thấy | 0,10 | 5 |

Tổng xác suất bằng 1. Chi phí kỳ vọng:

\[
\begin{aligned}
\mathbb{E}[C]
&=0,54\cdot1+0,09(2+3+4+5)+0,10\cdot5\\
&=0,54+1,26+0,50=2,30.
\end{aligned}
\]

Nếu chỉ giả định khóa **chắc chắn tồn tại** và có vị trí đều, kỳ vọng là `(5+1)/2=3`. Nếu nhiều truy vấn thất bại hơn, chi phí có thể tăng. **Không có một “trung bình 3 phép” đúng cho mọi workload.**

### 5.3. Có nên chuyển khóa nóng về đầu?

Một chiến lược thích ứng như *move-to-front* có thể đưa phần tử vừa tìm thấy lên đầu để giảm số so sánh cho các truy vấn tương lai tới cùng khóa.

Nhưng cần tính **cả chi phí thay đổi vị trí**:

- Trong mảng, đưa phần tử ở chỉ số `i` lên đầu nhưng giữ thứ tự các phần tử khác có thể phải dịch O(i) ô.
- Trong danh sách liên kết đơn, sau khi tìm được nút và nút trước, có thể nối lại vài tham chiếu O(1); **tuy nhiên công việc tìm nút trước đó vẫn có thể O(n)**.
- Di chuyển phần tử làm thay đổi thứ tự; nếu API cam kết thứ tự chèn hoặc thứ tự tăng dần thì chiến lược này có thể không hợp lệ.

Một tối ưu chỉ hợp lý khi **lợi ích trên chuỗi truy vấn tương lai** vượt chi phí thay đổi và vẫn giữ đúng hợp đồng.

## 6. Bảng băm: phân bố tần suất truy vấn khác phân bố va chạm

Đây là điểm rất dễ bị hiểu nhầm.

**Skew của tần suất truy vấn** nghĩa là một số khóa được `get` thường xuyên hơn. **Va chạm hash** nghĩa là nhiều khóa khác nhau được ánh xạ tới cùng vị trí hoặc vùng xử lý. Chúng là hai khái niệm khác nhau.

Ví dụ: một bảng băm có 100.000 khóa phân bố bucket tốt. Nếu 90% lượt `get` cùng truy vấn một khóa `A`, điều đó **không tự khiến 90% khóa va chạm**. Khóa `A` vẫn là một khóa; nhiều lượt tra lặp lại có thể còn tận dụng tính cục bộ cache.

### 6.1. Những yếu tố thật sự ảnh hưởng tra cứu

- **Hàm băm:** có phân bố đều những khóa đang có hay không?
- **Hệ số tải:** số khóa so với số bucket/ô có được kiểm soát?
- **Chi phí hash/so sánh:** khóa là số nguyên ngắn hay chuỗi dài?
- **Mẫu thành công/thất bại:** chuỗi dò hoặc bucket có thể xử lý khác nhau.
- **Lịch sử chèn/xóa:** việc xóa có để lại dấu vết, lỗ trống hoặc cần tái cấu trúc?
- **Chiến lược resize:** có cần chuyển nhiều khóa sau một lần chèn?
- **Tính cục bộ theo thời gian:** cùng khóa hoặc cùng bucket có được truy cập lặp lại không?

Với mô hình hash và hệ số tải phù hợp, `get/put/remove` thường O(1) **kỳ vọng** theo `n` nếu chi phí hash/so sánh khóa là O(1). Nhưng từng thao tác vẫn có thể đắt khi va chạm nặng hoặc phải tái băm.

### 6.2. Hai tập khóa có cùng `n` nhưng khác đặc điểm

| Tập khóa | Điều cần kiểm tra | Rủi ro hoặc lợi ích |
| --- | --- | --- |
| Số nguyên ngắn, phân bố hash phù hợp | Hệ số tải | Tra bucket nhanh theo kỳ vọng |
| Chuỗi rất dài `k` ký tự | Thời gian tính hash và so sánh | Có thể thêm O(k) cho một truy vấn |
| Khóa tạo có chủ ý để va chạm | Chất lượng hàm băm và chiến lược xử lý | Có thể tới O(n) trên một số cài đặt |
| Tập khóa ít đổi, truy vấn lặp khóa nóng | Cache và sự phân bố truy vấn | Có thể giảm chi phí thực tế dù Big-O không đổi |
| Liên tục thêm/xóa quanh ngưỡng tải | Tái băm và xử lý phần tử đã xóa | Độ trễ đỉnh và bộ nhớ tạm có thể tăng |

Lưu ý rằng cách xử lý va chạm và chiến lược làm sạch dấu xóa (*tombstones*) khác nhau theo thư viện; không được mặc định mọi Hash Map sử dụng cùng một thuật toán.

### 6.3. Khi cần đảm bảo trường hợp xấu

Nếu mã định danh hoặc dữ liệu do bên ngoài chủ động cung cấp và ứng dụng phải giới hạn chặt thời gian cho **từng** truy vấn, một cấu trúc có chặn xấu nhất rõ như cây tìm kiếm cân bằng có thể đáng cân nhắc. Đây là đánh đổi giữa thời gian kỳ vọng, thời gian xấu nhất, thứ tự khóa và overhead bộ nhớ.

## 7. Cây tìm kiếm: thứ tự chèn có thể làm thay đổi cấu trúc

Xét cây tìm kiếm nhị phân (BST) **không tự cân bằng**. Khi chèn lần lượt:

```text
Dãy A: 1, 2, 3, 4, 5

1
 \
  2
   \
    3
     \
      4
       \
        5

Dãy B: 3, 1, 5, 2, 4

      3
     / \
    1   5
     \ /
      2 4
```

Cùng năm khóa nhưng hình dạng cây khác nhau:

- Dãy A tạo một chuỗi dài nếu quy tắc BST thông thường không cân bằng.
- Dãy B tạo cây nông hơn.

Tìm/chèn/xóa trong BST dựa trên đường đi từ gốc, thường O(h) với `h` là chiều cao cây. Với cây lệch, `h=Θ(n)`; với cây được cân bằng, `h=O(log n)`.

### 7.1. Cùng dữ liệu, thay thứ tự xây dựng là đủ đổi chi phí

Nếu chỉ thử chèn hoán vị ngẫu nhiên, người học có thể quan sát một BST có vẻ cân bằng tương đối rồi ngộ nhận BST **luôn** O(log n). Một chuỗi khóa tăng hoặc giảm có thể bộc lộ trường hợp xấu.

Cây AVL và cây đỏ-đen duy trì bất biến cân bằng, giới hạn tìm/chèn/xóa theo khóa ở O(log n) trường hợp xấu, đổi lại phải cập nhật màu/chiều cao và có thể thực hiện quay cây.

### 7.2. Phân bố khóa tìm kiếm vẫn quan trọng với cây cân bằng

Ngay cả khi `find` có chặn xấu nhất O(log n), một lần tìm thấy khóa ở gốc chỉ cần một phép so sánh. Nếu phần lớn truy vấn nhắm vài khóa, số nút thăm **trung bình** có thể khác với phân bố đều.

Tuy nhiên, không thể chuyển một khóa nóng tùy ý lên gốc bằng cách phá bất biến thứ tự hoặc cân bằng mà vẫn coi cấu trúc là cây cân bằng đúng như trước. Mọi chiến lược thích ứng phải đi cùng chứng minh về tính đúng và chi phí cập nhật.

### 7.3. Truy vấn khoảng và thứ tự

Một workload thường xuyên yêu cầu “lấy các khóa từ `a` tới `b`” sẽ khác workload chỉ hỏi `get(key)`. Cây tìm kiếm cân bằng có thể tìm điểm đầu trong O(log n) rồi duyệt `k` phần tử kết quả trong O(k), với cài đặt duyệt phù hợp: tổng O(log n+k).

Bảng băm thường tốt cho tra cứu chính xác theo khóa nhưng không mặc định duy trì thứ tự tăng dần; có thể phải trích xuất và sắp xếp khóa khi cần. Phân bố **loại truy vấn**, không chỉ phân bố **giá trị khóa**, ảnh hưởng lựa chọn.

## 8. Mảng động: vị trí chèn quyết định số phần tử phải dịch

Với mảng chứa `n` phần tử còn đủ sức chứa, chèn ở chỉ số `i` (từ 0 tới `n`) cần dịch `n-i` phần tử.

\[
\mathrm{shifts}(i,n)=n-i.
\]

| Vị trí chèn | Số lần dịch |
| --- | --- |
| Cuối, `i=n` | 0 |
| Giữa, `i≈n/2` | Xấp xỉ `n/2` |
| Đầu, `i=0` | `n` |

Giả sử 90% lần chèn là thêm cuối, 10% là chèn đầu, kích thước trước chèn gần `n`. Số ô dịch **kỳ vọng** là:

\[
\mathbb{E}[\mathrm{shifts}]
=0,9\cdot0+0,1\cdot n=0,1n.
\]

Nếu 50% chèn đầu và 50% chèn cuối, kỳ vọng tăng thành `0,5n`. Hai workload có cùng `n`, cùng API `insert`, nhưng lượng dữ liệu phải di chuyển khác nhau rõ rệt.

### 8.1. Đừng nhầm kỳ vọng O(n) với append khấu hao O(1)

- `append` cuối mảng động có thể O(1) **khấu hao** khi vùng đệm tăng theo hệ số phù hợp; riêng lần resize có thể Θ(n).
- `insert(i,x)` vào vị trí tùy ý vẫn có thể phải dịch Θ(n) phần tử, ngay cả khi mảng còn chỗ.
- Nếu chỉ xét phân bố vị trí chèn và mỗi vị trí có xác suất, có thể tính số lần dịch **kỳ vọng** như trên.

Kết luận O(1) khấu hao cho **thêm cuối** không mở rộng thành O(1) cho **chèn tùy ý**. Hai phép toán cần hợp đồng và mô hình chi phí riêng.

### 8.2. Thứ tự thêm/xóa có thể tạo nhiều lần resize

Giả sử một mảng tăng sức chứa khi đầy và thu nhỏ quá sớm khi kích thước vừa giảm xuống một nửa dung lượng. Chuỗi:

```text
n = 5, capacity = 8
pop     -> n = 4, thu nhỏ capacity 8 -> 4
append  -> n = 5, mở rộng capacity 4 -> 8
pop     -> n = 4, thu nhỏ capacity 8 -> 4
append  -> ...
```

Nếu mỗi lần thu nhỏ/mở rộng phải sao chép các phần tử, một cặp thao tác có thể gây nhiều lần sao chép dù tổng số phần tử gần như không đổi. Đây là lý do cần **chính sách ngưỡng có khoảng đệm** và chứng minh khấu hao đúng cho các loại thao tác được cho phép.

**Workload “nửa thêm nửa xóa” không bộc lộ rủi ro nếu không biết thứ tự các thao tác và trạng thái sức chứa.**

## 9. Stack và Queue: chuỗi thao tác chi phối độ trễ từng lời gọi

### 9.1. Stack và lần lấy hàng loạt

Một Stack có `multiPop(k)` sẽ lấy tối đa `k` phần tử đang có. Một lần `multiPop` có thể phải lấy Θ(n) phần tử, nhưng nếu bắt đầu từ Stack rỗng và mỗi phần tử chỉ được thêm một lần trước khi bị lấy, tổng số phần tử bị lấy trong toàn bộ chuỗi **không vượt tổng số lần `push`**.

Đó là chặn **khấu hao**, không cần giả định ngẫu nhiên. Nếu một workload thường dồn nhiều `push` rồi gọi một `multiPop` rất lớn, độ trễ lời gọi `multiPop` vẫn có thể cao dù tổng công việc tuyến tính.

### 9.2. Queue bằng hai Stack

Queue FIFO có thể dùng một stack để nhận dữ liệu và một stack để trả dữ liệu. Khi cần lấy phần tử mà stack trả rỗng, cài đặt chuyển toàn bộ phần tử đang chờ từ stack nhận sang stack trả.

```python
class TwoStackQueue:
    def __init__(self):
        self.in_stack = []
        self.out_stack = []

    def enqueue(self, value):
        self.in_stack.append(value)

    def dequeue(self):
        if not self.out_stack:
            while self.in_stack:
                self.out_stack.append(self.in_stack.pop())
        if not self.out_stack:
            raise IndexError("empty queue")
        return self.out_stack.pop()
```

Nếu có một triệu lần `enqueue` liên tiếp rồi gọi `dequeue` lần đầu, lần lấy đầu có thể chuyển gần một triệu phần tử, Θ(n). Tuy nhiên, mỗi phần tử **chỉ được chuyển một lần**, nên tổng chi phí trên chuỗi O(m) khi `m` là số lời gọi hợp lệ và bắt đầu rỗng: O(1) khấu hao cho mỗi lời gọi theo mô hình các thao tác stack O(1).

### 9.3. Cùng FIFO, khác độ trễ đỉnh

| Biểu diễn Queue | Chi phí một lần `dequeue` | Ghi chú |
| --- | --- | --- |
| Mảng vòng đúng thiết kế | O(1) khi chỉ đổi `head` và xóa ô | `enqueue` có thể gây resize |
| Danh sách liên kết có `head, tail` | O(1) theo mô hình cập nhật con trỏ | Phải quản lý cấp phát nút cho lần thêm |
| Hai Stack | O(n) trường hợp xấu của một lần lấy | O(1) khấu hao trên chuỗi |

Một hệ thống batch có thể chấp nhận một lần chuyển hàng loạt. Hệ thống yêu cầu hạn thời gian cứng cho từng `dequeue` cần cân nhắc chặn **xấu nhất mỗi lời gọi**, không chỉ thông lượng trung bình.

## 10. Heap và Priority Queue: phân bố độ ưu tiên ảnh hưởng loại thao tác

Một Priority Queue có hợp đồng lấy phần tử ưu tiên nhất, không phải FIFO. Min-heap nhị phân thường cung cấp:

- `peek_min`: O(1).
- `insert`: O(log n) trường hợp xấu.
- `extract_min`: O(log n) trường hợp xấu.
- Tìm một phần tử **bất kỳ theo ID**: O(n) trường hợp xấu nếu không có chỉ mục bổ sung.

### 10.1. Thay đổi ưu tiên cũng là một thao tác

Một lịch tác vụ không chỉ thêm và lấy nhiệm vụ. Nó có thể thường xuyên **đổi độ ưu tiên** hoặc **hủy tác vụ theo ID**. Nếu chỉ có heap mảng và không biết vị trí tác vụ, muốn tìm ID trước khi sửa có thể tốn O(n).

Có thể giữ bảng `id -> vị trí trong heap` để tìm tác vụ nhanh hơn, nhưng mỗi lần hai phần tử trong heap đổi chỗ phải cập nhật bảng vị trí tương ứng. Chỉ mục làm tăng bộ nhớ và chi phí duy trì bất biến.

### 10.2. Nhiều tác vụ cùng độ ưu tiên

Nếu nhiều nhiệm vụ có độ ưu tiên bằng nhau, heap thông thường không tự cam kết chúng được xử lý theo thứ tự đến. Nếu API cần **ổn định** (*stable*), có thể dùng cặp khóa `(priority, insertion_order)` làm khóa so sánh.

Điều này thêm trường `insertion_order` vào dữ liệu và chi phí cập nhật bộ đếm; đổi lại đáp ứng đúng hành vi công khai. Phân bố nhiều độ ưu tiên trùng chỉ quan trọng khi hợp đồng quy định cách xử lý chúng.

### 10.3. Các workload khác nhau

| Workload | Điều cần xem |
| --- | --- |
| Thêm rất nhiều rồi liên tục lấy ưu tiên nhất | Có thể xây heap ban đầu bằng `heapify` Θ(n) |
| Thêm/lấy xen kẽ | `insert` và `extract_min` O(log n) xấu nhất |
| Thường xuyên hủy theo ID | Có cần chỉ mục ID → vị trí heap? |
| Nhiều khóa ưu tiên trùng | Có cần xử lý FIFO trong nhóm bằng ưu tiên? |
| Chủ yếu tra đúng mã tác vụ | Hash Map có thể phù hợp hơn nếu không có truy vấn ưu tiên |

Khối lượng công việc quyết định ADT cần thiết; không nên chọn heap chỉ vì `peek_min` nhanh nếu hệ thống thực tế chủ yếu dùng `get(id)`.

## 11. Đồ thị: số cạnh bằng nhau nhưng đường duyệt khác nhau

Với đồ thị có `V` đỉnh và `E` cạnh, danh sách kề lưu các cạnh thực có; ma trận kề lưu các vị trí có thể có cạnh.

- Duyệt toàn bộ bằng BFS/DFS trên danh sách kề tốn O(V+E) theo mô hình tra đỉnh/đánh dấu phù hợp.
- Duyệt toàn bộ bằng ma trận kề quét hàng có thể tốn O(V²).
- Kiểm tra `has_edge(u,v)` trong ma trận kề là O(1) khi định danh đỉnh được ánh xạ sẵn tới chỉ số.
- Kiểm tra cạnh trong danh sách kề bằng danh sách thường tốn O(deg(u)+1); bằng tập băm có thể O(1) kỳ vọng.

### 11.1. Phân bố bậc đỉnh ảnh hưởng truy vấn cục bộ

Giả sử hai đồ thị có cùng `V=10.000` và `E=20.000`:

- Đồ thị A phân bố cạnh khá đều, ít đỉnh có bậc lớn.
- Đồ thị B tập trung một phần đáng kể cạnh vào vài đỉnh hub.

Một lệnh `neighbors(u)` cần liệt kê đúng `deg(u)` láng giềng. Nếu người dùng thường hỏi các hub, số mục trả về và số phần tử phải duyệt có thể lớn hơn đáng kể.

Tương tự, `has_edge(u,v)` trên danh sách kề bằng danh sách có thể phải quét O(deg(u)) mục, nên chọn đỉnh nguồn `u` khác nhau làm chi phí khác nhau. Ma trận kề không phụ thuộc bậc `u` cho một phép kiểm tra cạnh, đổi lại dùng Θ(V²) bộ nhớ.

### 11.2. Phân bố đỉnh bắt đầu của BFS

BFS từ đỉnh `s` chỉ duyệt những đỉnh/cạnh **có thể tới được**. Nếu `V_r,E_r` mô tả phần được duyệt, chi phí lõi với danh sách kề là O(V_r+E_r).

Nếu phần lớn truy vấn bắt đầu tại những thành phần nhỏ, thời gian trung bình có thể ít hơn nhiều so với BFS toàn đồ thị. Nhưng phải có **phân bố đỉnh nguồn** để tính kỳ vọng; hai con số `V,E` không đủ.

Lưu ý: nếu thuật toán cấp phát mảng `visited` dài `V` trước mỗi BFS, riêng bước khởi tạo đã tốn O(V), ngay cả khi thành phần tìm được nhỏ. Cần phân tích mã thực tế, không chỉ phần vòng lặp duyệt.

### 11.3. Đồ thị có thay đổi cạnh liên tục

Nếu ứng dụng thường thêm/xóa cạnh, danh sách kề động hoặc tập kề có thể thuận tiện. Nếu đồ thị gần như bất biến và chủ yếu duyệt, một biểu diễn nén bằng mảng như CSR (*Compressed Sparse Row*) có thể có ưu thế về bộ nhớ và tính cục bộ.

Một biểu diễn tối ưu cho **duyệt lặp lại** không nhất thiết tối ưu cho **cập nhật liên tục**. Ngoài phân bố số đỉnh và cạnh, phải xét tỷ lệ thay đổi và yêu cầu đồng bộ của đồ thị.

## 12. Phân bố và tính cục bộ bộ nhớ: Big-O không nói hết

Hai cấu trúc đều có duyệt Θ(n), nhưng thời gian đo được có thể khác vì:

- **Mảng liên tục:** các ô gần nhau, phần cứng có thể nạp trước và tận dụng cache.
- **Danh sách liên kết:** phải đi theo con trỏ, các nút có thể nằm rải rác.
- **Khóa nóng:** lặp lại truy cập vài khóa có thể tăng khả năng dữ liệu còn trong cache.
- **Truy cập ngẫu nhiên trên miền rộng:** có thể khiến nhiều dòng cache bị thay thế.
- **Cấp phát liên tục và thu hồi:** có thể tăng phân mảnh hoặc chi phí quản lý bộ nhớ.

Tính cục bộ **không thay đổi chứng minh Big-O của mô hình RAM** trong phần lớn trường hợp, nhưng có thể thay đổi hệ số thực nghiệm đáng kể.

### 12.1. Bộ nhớ đang giữ và bộ nhớ đỉnh cũng phụ thuộc vết

Một workload tăng từ 100 lên 100.000 phần tử rồi giảm còn 100 có thể khiến mảng động giữ sức chứa lớn, nếu cài đặt không thu nhỏ. Một workload luôn dao động quanh 100 phần tử có thể giữ bộ nhớ nhỏ hơn dù số phần tử ở thời điểm kết thúc đều là 100.

Đừng chỉ đo `size` cuối cùng. Hãy ghi:

- Kích thước hiện tại `n_t` và kích thước lớn nhất.
- Dung lượng đã cấp phát hoặc số nút/bucket đang giữ lại.
- Bộ nhớ đỉnh trong lúc resize, rehash hoặc tạo bản sao.
- Số lần cấp phát và giải phóng nếu có công cụ quan sát phù hợp.

## 13. Phân biệt kỳ vọng theo workload với khấu hao trên chuỗi

Các thuật ngữ đôi khi đều được gọi là “bình quân”, nhưng có cơ sở khác nhau.

| Khái niệm | Cơ sở | Ví dụ |
| --- | --- | --- |
| **Tốt nhất/xấu nhất** | Tìm đầu vào hoặc trạng thái thuận lợi/bất lợi trong phạm vi `n` | Tìm tuyến tính: 1 hoặc `n` so sánh |
| **Trung bình** | Phân bố xác suất đầu vào, truy vấn hoặc trạng thái đã nêu | Một số khóa được tìm thường xuyên hơn |
| **Kỳ vọng của thuật toán ngẫu nhiên** | Lấy kỳ vọng theo lựa chọn ngẫu nhiên bên trong thuật toán | Pivot ngẫu nhiên của QuickSort |
| **Khấu hao** | Chặn tổng chi phí của mọi chuỗi thao tác hợp lệ trong mô hình | Mảng động `append` O(1) khấu hao khi nhân đôi |

### 13.1. Khấu hao không cần giả định phân bố ngẫu nhiên

Mảng động tăng gấp đôi sức chứa khi đầy có thể phải sao chép lần lượt khoảng:

```text
1, 2, 4, 8, 16, ...
```

Tổng số ô bị sao chép qua `m` lần `append` liên tiếp từ mảng rỗng bị chặn bởi O(m), vì tổng cấp số nhân nhỏ hơn `2m`. Cộng `m` lần ghi mới, tổng công việc O(m), nên mỗi lần thêm có O(1) khấu hao.

Đây là chặn cho **mọi chuỗi giá trị được thêm** theo quy tắc cài đặt đã nêu, không cần giá trị ngẫu nhiên. Một lần `append` vẫn có thể Θ(n) khi mở rộng.

### 13.2. Kỳ vọng không bảo đảm từng lời gọi

Hash Map tra cứu O(1) kỳ vọng trong những điều kiện băm phù hợp, nhưng một lần truy vấn có thể tốn O(n) do va chạm. Một bộ benchmark có trung bình thấp cũng có thể chứa một số yêu cầu rất chậm.

Khi ứng dụng cần **độ trễ ổn định**, cần xem chặn xấu nhất, độ trễ phân vị cao và các sự kiện tái cấu trúc, không chỉ trung bình.

### 13.3. Một bảng tỷ lệ không chứng minh được khấu hao

Nếu một báo cáo đo thấy 99% lần thêm mất 1 đơn vị, 1% mất 100 đơn vị thì chi phí trung bình của mẫu là khoảng 1,99. Điều đó **không đủ** để kết luận O(1) khấu hao cho mọi chuỗi.

Muốn chứng minh khấu hao, phải sử dụng tính chất cấu trúc (ví dụ mỗi phần tử được chuyển nhiều nhất một lần hoặc sức chứa tăng theo hệ số) và đưa ra chặn trên tổng chi phí cho mọi vết được phép.

## 14. Đánh giá một thiết kế theo toàn bộ vòng đời

Giả sử một dịch vụ lưu `n` bản ghi với `q` truy vấn theo khóa, `u` cập nhật và `r` lần xuất có thứ tự. Có ba lựa chọn:

| Phương án | Xây từ `n` bản ghi | Tra khóa | Cập nhật | Xuất tăng dần |
| --- | --- | --- | --- | --- |
| Mảng sắp xếp | O(n log n) nếu phải sắp | O(log n) | O(n) xấu nhất nếu chèn/xóa cần dịch | Θ(n) |
| Hash Map | O(n) kỳ vọng với giả định phù hợp | O(1) kỳ vọng | O(1) kỳ vọng/khấu hao với giả định phù hợp | Thường O(n log n) nếu phải sắp khóa |
| Cây tìm kiếm cân bằng | O(n log n) nếu chèn từng mục; có thể O(n) từ dãy đã sắp qua xây hàng loạt | O(log n) xấu nhất | O(log n) xấu nhất | Θ(n) duyệt inorder |

Đây không phải ba thiết kế tương đương về mọi hành vi. Cần xác định quy tắc khóa trùng, quan hệ thứ tự và khả năng cập nhật trước khi so sánh.

### 14.1. Chi phí tổng không chỉ là `q×Q`

Khi kích thước thay đổi theo thời gian:

\[
T_{\mathrm{all}}
=B(n_0)+\sum_{t=1}^{m}c(op_t,S_{t-1}).
\]

Nếu muốn dự toán gần đúng khi `n_t≈n` và tần suất ổn định:

\[
T_{\mathrm{estimate}}\approx B(n)+qQ(n)+uU(n)+rD(n).
\]

Nhưng `Q(n)`, `U(n)` và `D(n)` có thể là **chi phí xấu nhất** hoặc **kỳ vọng**, không được trộn tùy ý rồi xem tổng là bảo đảm xấu nhất.

Nếu chỉ có vài truy vấn, tiền xử lý sắp hoặc xây chỉ mục có thể không đáng. Nếu có hàng triệu truy vấn, chi phí xây ban đầu có thể được bù lại. Nếu cập nhật nhiều và liên tục, một cấu trúc duy trì thứ tự có chi phí logarit có thể hợp lý hơn mảng sắp phải dịch nhiều.

### 14.2. Ví dụ workload cụ thể

Giả định một dịch vụ có:

- `n≈100.000` bản ghi ổn định.
- `q=1.000.000` lượt tra theo mã.
- `u=20.000` lần thêm/xóa.
- `r=500` lần tạo báo cáo tăng dần.
- Khóa là mã ngắn, có quy tắc so sánh nhất quán.

Bảng băm có thể hỗ trợ tra theo khóa tốt về kỳ vọng, nhưng nếu **mỗi báo cáo** đều sắp lại toàn bộ khóa thì phần `r·n log n` có thể rất lớn. Cây cân bằng có truy vấn theo khóa O(log n), cập nhật O(log n) và duyệt tăng dần Θ(n), nên có thể đáng cân nhắc.

Nếu `r` chỉ bằng 1 và `u` rất nhỏ, kết luận có thể đảo chiều. **Không có cấu trúc tốt nhất nếu chưa biết cơ cấu thao tác.**

## 15. Thu thập vết thao tác thay vì benchmark mỗi phép toán độc lập

Một phép đo có ý nghĩa nên mô phỏng **lịch sử sử dụng** chứ không chỉ gọi cùng một hàm trong vòng lặp không đổi trạng thái.

Ví dụ, đo `get` một triệu lần trên cùng một khóa chỉ cho biết hiệu năng của một workload cực lệch. Nếu sản phẩm còn thường xuyên thêm/xóa khóa, xóa dữ liệu cũ hoặc truy vấn khóa vắng mặt, cần đo những hoạt động ấy.

### 15.1. Mỗi bản ghi vết nên chứa gì?

Có thể biểu diễn mỗi thao tác thành:

```text
(timestamp, operation, key, value_or_metadata)
```

Đối với phân tích đơn luồng, ta có thể bỏ timestamp nếu chỉ quan tâm **thứ tự** thao tác. Nhưng nếu phân tích burst theo thời gian, concurrency, chờ hàng đợi hoặc độ trễ cuối người dùng, timestamp trở nên quan trọng.

Một bản ghi ví dụ:

```text
(00:00:01.000, "get",    "HV-17", None)
(00:00:01.002, "get",    "HV-17", None)
(00:00:01.005, "put",    "HV-83", {"score": 8})
(00:00:01.006, "remove", "HV-02", None)
```

Vết không nên làm lộ thông tin cá nhân thật khi dùng để benchmark hay chia sẻ; có thể thay khóa và giá trị bằng dữ liệu tổng hợp vẫn giữ đặc điểm kích thước, tần suất và cấu trúc cần thử.

### 15.2. Các thống kê cần rút ra

| Nhóm thống kê | Ví dụ cần tính |
| --- | --- |
| Kích thước | `n_t` trung bình, lớn nhất; số phần tử tăng/giảm theo đợt |
| Thao tác | Tỷ lệ get/put/remove/scan; số lần thao tác liên tiếp cùng loại |
| Thành công/thất bại | Hit rate, miss rate, xóa khóa không tồn tại |
| Skew | Top 10 khóa chiếm bao nhiêu phần trăm truy vấn? |
| Khóa | Độ dài, tỷ lệ trùng, kiểu khóa, mẫu gây va chạm |
| Cập nhật | Chèn đầu/cuối/giữa, độ dài burst, vùng dung lượng gần ngưỡng |
| Duyệt | Duyệt tất cả hay chỉ khoảng? Có cần thứ tự ổn định? |
| Bộ nhớ | Dung lượng lớn nhất, số resize/rehash, đỉnh bộ nhớ |
| Độ trễ | Trung bình, trung vị, p95/p99 và giá trị tối đa quan sát |

Các phân vị đo trên một mẫu là **thống kê của mẫu**; không tự chứng minh giới hạn thời gian xấu nhất cho mọi đầu vào trong tương lai.

## 16. Sinh workload tái lập bằng Python

Nếu không có dữ liệu thực hoặc không thể sử dụng dữ liệu sản xuất, ta có thể tạo một vết **tổng hợp** có kiểm soát. Ví dụ sau có:

- Khóa nóng được tra nhiều hơn.
- Một phần truy vấn cố ý tìm khóa không tồn tại.
- Có chèn khóa mới và xóa khóa đang tồn tại.
- Dùng seed cố định để các cấu trúc khác nhau nhận **cùng một vết**.

```python
from collections import Counter
from random import Random


def make_trace(initial_size=100, steps=1000, seed=42,
               read_ratio=0.80, hot_ratio=0.70, miss_ratio=0.10):
    if initial_size < 0 or steps < 0:
        raise ValueError("size và steps phải không âm")
    for ratio in (read_ratio, hot_ratio, miss_ratio):
        if not 0 <= ratio <= 1:
            raise ValueError("ratio phải thuộc [0, 1]")

    rng = Random(seed)
    alive = list(range(initial_size))
    position = {key: i for i, key in enumerate(alive)}
    hot = list(range(min(10, initial_size)))
    next_key = initial_size
    trace = []

    def pick_existing():
        return alive[rng.randrange(len(alive))]

    def remove_existing(key):
        index = position.pop(key)
        last_key = alive.pop()
        if index < len(alive):
            alive[index] = last_key
            position[last_key] = index

    for _ in range(steps):
        if rng.random() < read_ratio:
            if not alive or rng.random() < miss_ratio:
                key = -1 - rng.randrange(1000)  # Luôn là khóa vắng mặt
            elif hot and rng.random() < hot_ratio:
                candidate = hot[rng.randrange(len(hot))]
                key = candidate if candidate in position else pick_existing()
            else:
                key = pick_existing()
            trace.append(("get", key))
        elif not alive or rng.random() < 0.50:
            key = next_key
            next_key += 1
            position[key] = len(alive)
            alive.append(key)
            trace.append(("put", key))
        else:
            key = pick_existing()
            remove_existing(key)
            trace.append(("remove", key))

    return trace


trace = make_trace()
counts = Counter(operation for operation, _ in trace)
assert sum(counts.values()) == 1000
```

Vì `rng=Random(seed)` được tạo riêng, chạy với cùng tham số tạo ra vết tái lập trong cùng môi trường Python. Trong ví dụ này, việc sinh vết dùng cấu trúc `alive/position` để chọn và xóa khóa hiện có mà không phải quét toàn bộ `alive` mỗi lần. **Không đưa thời gian sinh vết vào số đo của cấu trúc đang đánh giá.**

### 16.1. Kiểm tra hành vi bằng mô hình tham chiếu

Nếu ứng viên được so sánh là các Map có cùng quy tắc `get/put/remove`, có thể dùng `dict` làm mô hình tham chiếu:

```python
def replay_dict(trace, initial_size):
    data = {key: key * 2 for key in range(initial_size)}
    results = []

    for operation, key in trace:
        if operation == "get":
            results.append(data.get(key))
        elif operation == "put":
            data[key] = key * 2
        elif operation == "remove":
            results.append(data.pop(key))
        else:
            raise ValueError("unknown operation")

    return results, data


trace = make_trace(initial_size=100, steps=1000, seed=42)
results, final_data = replay_dict(trace, 100)
assert len(results) <= len(trace)
```

`replay_dict` minh họa hợp đồng cụ thể: giá trị bằng `key×2`, `get` vắng mặt trả `None`, `remove` phải nhắm khóa tồn tại. Với một cài đặt Map khác, hãy cho nó nhận cùng vết và so sánh **kết quả từng truy vấn, các ngoại lệ và trạng thái cuối** trước khi đo thời gian.

Nếu người dùng yêu cầu API phân biệt “không có khóa” với “khóa có giá trị `None`”, mô hình này phải được đổi để phản ánh đúng hợp đồng. Đừng đánh giá tốc độ trên một cấu trúc trả kết quả sai.

### 16.2. Thay đổi tỷ lệ để tạo kịch bản đối chiếu

```python
mostly_reads = make_trace(
    initial_size=1000, steps=5000, seed=7,
    read_ratio=0.95, hot_ratio=0.90, miss_ratio=0.02
)

mixed_updates = make_trace(
    initial_size=1000, steps=5000, seed=7,
    read_ratio=0.50, hot_ratio=0.20, miss_ratio=0.20
)
```

Hai vết này có cùng kích thước ban đầu, số thao tác và seed, nhưng **không có cùng chuỗi thao tác** vì tham số khác nhau. Đó chính là điều muốn kiểm tra: độ nhạy của cấu trúc theo workload.

Mã chỉ là ví dụ học tập; không nên xem một seed hoặc một mô hình ngẫu nhiên là đại diện cho sản xuất. Khi cần thống kê đáng tin cậy, đo nhiều seed, nhiều quy mô và đối chiếu với vết thực đã được xử lý an toàn.

## 17. Quy trình benchmark dựa trên vết thao tác

Để so sánh công bằng, làm theo thứ tự:

1. **Định nghĩa hợp đồng.** Các cấu trúc ứng viên phải trả cùng kết quả, giữ cùng quy tắc khóa trùng, thứ tự và lỗi.
2. **Chọn kích thước.** Đo nhiều `n`; ghi kích thước ban đầu, trung bình và lớn nhất.
3. **Chọn workload.** Dùng vết tổng hợp có tham số và/hoặc vết thực đại diện, gồm tỷ lệ truy vấn vắng mặt và cập nhật.
4. **Tách tạo dữ liệu khỏi thời gian đo.** Không tính chi phí sinh vết vào thao tác cấu trúc trừ khi chính việc sinh dữ liệu là phần của bài toán.
5. **Khởi tạo mới cho mỗi lần thử.** Tránh ứng viên sau nhận trạng thái đã bị ứng viên trước sửa.
6. **Chạy kiểm thử tính đúng.** So khớp kết quả, lỗi, số phần tử và những bất biến có thể kiểm tra.
7. **Làm nóng và lặp lại.** Tránh rút kết luận từ một lần chạy ngắn.
8. **Đo riêng và đo tổng.** Báo thời gian xây, từng loại thao tác và tổng thời gian xử lý vết.
9. **Đo bộ nhớ.** Phân biệt bộ nhớ giữ lại, bộ nhớ phụ và bộ nhớ đỉnh khi resize/rebuild.
10. **Báo giả định.** Nêu runtime, kiến trúc, cách tính hash/so sánh, tỷ lệ thao tác, seed và phương pháp thống kê.

### 17.1. Tránh so sánh không công bằng

Ví dụ không công bằng: tạo một hash map rồi đo 100.000 lần `get`, trong khi với cây cân bằng lại tính cả thời gian tạo cây. Nếu mục tiêu là **thời gian truy vấn khi cấu trúc đã có sẵn**, hãy loại chi phí xây ở cả hai. Nếu mục tiêu là **toàn vòng đời**, hãy tính chi phí xây ở cả hai.

Một ví dụ khác: đo `insert` vào mảng sắp theo thứ tự tăng nhưng cho cấu trúc đối chứng nhận khóa ngẫu nhiên. Hai ứng viên phải nhận cùng vết đầu vào khi so sánh trên cùng bài toán.

### 17.2. Tách thông lượng và độ trễ

Một cấu trúc có thể xử lý cả triệu thao tác nhanh nhưng có một số lần `put` rất chậm do rehash. Tổng thời gian thấp là tốt cho **thông lượng**, nhưng độ trễ một yêu cầu có thể quan trọng với dịch vụ trực tuyến.

Nên báo ít nhất thời gian tổng hoặc tốc độ thao tác, trung vị, phân vị cao và các sự kiện đắt quan sát được. Không coi một số đo trung bình là giới hạn xấu nhất.

### 17.3. Hiệu năng dưới nhiều kích thước

Với thuật toán Θ(n), khi tăng kích thước gấp đôi, lượng công việc lý thuyết thường tăng xấp xỉ hai lần. Với Θ(n²), có thể xấp xỉ bốn lần khi `n` đủ lớn. Đây chỉ là **xu hướng tiệm cận**; cache, giới hạn bộ nhớ, cấp phát và hệ số ẩn có thể khiến số đo thực tế lệch đáng kể.

Một benchmark chỉ ở `n=100` có thể không bộc lộ vấn đề xảy ra ở `n=1.000.000`, và ngược lại một tối ưu phức tạp cho dữ liệu rất lớn có thể không đáng ở quy mô nhỏ.

## 18. Năm tình huống thiết kế thực tế

### 18.1. Tra cứu học viên: đọc nhiều, cập nhật ít

Một hệ thống tra mã học viên hàng triệu lần trên bộ dữ liệu gần như cố định. Hash Map có thể hỗ trợ truy cập chính xác theo khóa O(1) kỳ vọng, đổi lại bộ nhớ chỉ mục. Nếu còn phải liệt kê theo mã tăng dần liên tục, cây cân bằng hoặc mảng sắp xếp có thể đáng cân nhắc.

**Cần đo:** tỷ lệ `get`, tỷ lệ khóa vắng mặt, độ dài mã và tần suất báo cáo có thứ tự.

### 18.2. Lịch đặt chỗ: thêm/xóa dồn theo giờ

Nếu phần lớn cập nhật xảy ra tại giờ cao điểm, một cấu trúc có thao tác **khấu hao** tốt vẫn có thể gặp đỉnh độ trễ khi mở rộng, tái băm hoặc dồn dữ liệu.

**Cần đo:** burst theo thời gian, `n_t` tại mỗi thao tác, độ trễ p95/p99, bộ nhớ đỉnh và chính sách cập nhật nguyên tử.

### 18.3. Hệ thống xử lý yêu cầu FIFO

Nếu phần lớn thời gian hàng đợi ngắn nhưng đôi lúc tăng lên rất lớn, Queue mảng vòng hoặc liên kết đầu/đuôi có thể có đặc tính bộ nhớ và độ trễ khác Queue hai Stack. Tất cả phải bảo đảm FIFO; lợi thế khấu hao không thay thế đúng hành vi.

**Cần đo:** chiều dài queue theo thời gian, tần suất burst, số lần resize, thời gian `dequeue` lâu nhất.

### 18.4. Bộ lập lịch ưu tiên

Nếu workload chủ yếu thêm/lấy tác vụ ưu tiên nhất, heap phù hợp. Nếu thường xuyên sửa mức ưu tiên hoặc hủy theo ID, cần đánh giá thêm chỉ mục và chi phí bảo trì ánh xạ ID → vị trí.

**Cần đo:** phân bố mức ưu tiên, tỷ lệ trùng, số lần đổi ưu tiên, số lần hủy và yêu cầu ổn định thứ tự trong nhóm bằng ưu tiên.

### 18.5. Mạng quan hệ và truy vấn láng giềng

Một đồ thị thưa gần như bất biến có thể dùng danh sách kề hoặc CSR để duyệt hiệu quả. Một hệ thống liên tục kiểm tra tồn tại cạnh có thể cân nhắc ma trận kề hoặc tập kề, tùy mật độ và giới hạn bộ nhớ.

**Cần đo:** `V,E`, phân bố bậc đỉnh, các nguồn truy vấn phổ biến, tỷ lệ thêm/xóa cạnh và nhu cầu duyệt toàn thành phần.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao gây lệch kết luận | Cách khắc phục |
| --- | --- | --- |
| Chỉ thử dữ liệu ngẫu nhiên đều | Bỏ sót khóa nóng, khóa trùng, dữ liệu đã sắp và truy vấn thất bại | Thử nhiều dạng phân bố có cơ sở |
| Chỉ ghi `n` mà không ghi `V,E,k` hoặc kiểu truy vấn | Thiếu những chiều ảnh hưởng chi phí | Định nghĩa đủ tham số kích thước |
| Coi 90% truy vấn một khóa đồng nghĩa nhiều va chạm hash | Truy vấn lặp không làm tăng số khóa khác nhau trong bucket | Tách tần suất truy cập với phân bố hàm băm |
| Tự giả định BST tìm O(log n) | BST không cân bằng có thể thành chuỗi | Thử thứ tự chèn tăng/giảm và dùng cây cân bằng nếu cần |
| Dùng tỷ lệ get/put/remove mà bỏ thứ tự | Không thấy burst, resize, dao động kích thước | Lưu và phát lại vết thao tác có thứ tự |
| Ghi “trung bình O(1)” nhưng không nêu phân bố | Không biết xác suất nào tạo ra kết luận | Ghi nguồn ngẫu nhiên và giả định |
| Gọi chi phí khấu hao là thời gian xấu nhất mỗi lời gọi | Một lần resize có thể Θ(n) | Tách tổng theo chuỗi khỏi đỉnh độ trễ |
| Đo khi ứng viên chưa có cùng dữ liệu ban đầu | Benchmark các bài toán khác nhau | Khởi tạo cùng trạng thái và kiểm tra kết quả |
| Tính thời gian tạo vết cho ứng viên này nhưng không cho ứng viên khác | So sánh không cùng phạm vi | Tách xây, sinh dữ liệu và xử lý |
| Chỉ tối ưu hiệu năng mà quên hợp đồng | Đổi thứ tự, khóa trùng hoặc kết quả | Kiểm thử tính đúng trước khi benchmark |
| Chỉ báo thời gian trung bình | Có thể che sự kiện hiếm nhưng rất chậm | Báo phân vị cao, cực đại quan sát và lý do |
| Không tính bộ nhớ đỉnh | Resize/rehash có thể giữ hai vùng cùng lúc | Đo cả bộ nhớ giữ lại và đỉnh cấp phát |

## 20. Bài tập vận dụng kèm gợi ý

### Bài 1 — Kỳ vọng khi truy vấn lệch

Một mảng có năm khóa khác nhau. Xác suất lần tìm thành công đầu tiên tại các vị trí `1,2,3,4,5` lần lượt là `0,54; 0,09; 0,09; 0,09; 0,09`. Xác suất vắng mặt là `0,10`. Tính số phép so sánh kỳ vọng của tìm kiếm tuyến tính.

**Gợi ý:** `0,54×1+0,09×(2+3+4+5)+0,10×5=2,30`. Trường hợp xấu nhất vẫn là 5 phép so sánh.

### Bài 2 — Cùng n, khác thứ tự chèn

Có các khóa `1,2,3,4,5,6,7`. So sánh việc chèn lần lượt theo thứ tự tăng dần vào BST không cân bằng với việc chèn `4,2,6,1,3,5,7`. Đường tìm khóa 7 khác nhau thế nào?

**Gợi ý:** Thứ tự tăng dần tạo chuỗi đi sang phải, tìm 7 có thể đi qua 7 nút. Thứ tự thứ hai tạo cây cân đối hơn, tìm 7 qua 3 nút. Cả hai cài cùng hợp đồng nhưng hình dạng khác; cây tự cân bằng bảo đảm chiều cao O(log n).

### Bài 3 — Phân bố vị trí chèn

Mảng có `n=2000` phần tử và còn đủ chỗ. Trong 100 thao tác chèn, giả định 90 thao tác ở cuối và 10 ở đầu, kích thước tạm coi gần 2000. Ước tính số ô dịch.

**Gợi ý:** Thêm cuối không phải dịch; chèn đầu dịch khoảng 2000 ô. Tổng gần `10×2000=20.000` lần dịch, tức gần 200 ô dịch trên mỗi thao tác. Đây là mô hình gần đúng vì kích thước thực thay đổi giữa các lần.

### Bài 4 — Hash skew và va chạm

Một Map có 100.000 khóa phân bố bucket hợp lý; 80% truy vấn `get` cùng nhắm khóa `A`. Có thể kết luận bucket của `A` chứa 80.000 khóa không?

**Gợi ý:** Không. 80% là **tỷ lệ lượt truy vấn**, không phải tỷ lệ khóa phân bố bucket. Va chạm phụ thuộc hàm băm, số khóa khác nhau và hệ số tải.

### Bài 5 — Khấu hao và đỉnh độ trễ

Queue hai Stack đang có 500.000 phần tử trong stack nhận, stack trả rỗng. `dequeue` tiếp theo có chi phí bao nhiêu? Tại sao vẫn có thể nói O(1) khấu hao trên một chuỗi dài?

**Gợi ý:** Lời gọi này chuyển Θ(500.000) phần tử. Nhưng mỗi phần tử chỉ chuyển một lần trong toàn chuỗi, nên tổng công việc được phân bổ trên các lần thêm/lấy; không có đảm bảo mỗi lần `dequeue` O(1).

### Bài 6 — Phân bố độ dài khóa

Hai bộ dữ liệu đều có 10.000 khóa, nhưng bộ A dùng số nguyên ngắn, bộ B dùng chuỗi dài trung bình 10.000 ký tự. Có thể so sánh `get` chỉ bằng số khóa `n` không?

**Gợi ý:** Chưa đủ. Việc tính hash và so sánh các chuỗi có thể phụ thuộc độ dài `k`; phải tính thêm chi phí theo `k` và xem khả năng cache hash/chiến lược cụ thể.

### Bài 7 — Hai đồ thị cùng số cạnh

Hai đồ thị có cùng `V=5000` và `E=10.000`. Đồ thị A có nhiều thành phần nhỏ, đồ thị B có một thành phần lớn. 90% BFS bắt đầu tại thành phần nhỏ của A. So sánh kết luận về BFS.

**Gợi ý:** Cận toàn đồ thị theo danh sách kề vẫn O(V+E). Nhưng phần có thể tới từ nguồn của A thường nhỏ hơn, khiến chi phí lõi trung bình có thể thấp hơn. Muốn định lượng phải biết phân bố đỉnh nguồn, kích thước thành phần và cách khởi tạo `visited`.

### Bài 8 — Tỷ lệ thao tác không đủ

Hai workload đều có 50% `push` và 50% `pop`, nhưng một workload luôn xen kẽ, workload kia dồn tất cả `push` trước rồi mới `pop`. Vì sao cần đo khác nhau?

**Gợi ý:** Kích thước lớn nhất và các lần mở rộng vùng đệm khác nhau, dù số lần mỗi thao tác giống nhau. Bộ nhớ đỉnh và độ trễ resize không thể suy ra chỉ từ tỷ lệ.

### Bài 9 — Benchmark hợp đồng

Một ứng viên Map trả `None` khi không có khóa, ứng viên khác ném `KeyError`. Có thể so thời gian hai ứng viên bằng cùng vết rồi nói chúng hoàn toàn tương đương không?

**Gợi ý:** Không nếu hợp đồng yêu cầu một hành vi lỗi cụ thể. Phải thống nhất quy tắc xử lý khóa vắng mặt trước khi so sánh và kiểm tra kết quả, lỗi trên từng thao tác.

### Bài 10 — Chọn cấu trúc theo workload

Một hệ thống có 100.000 hồ sơ, thực hiện khoảng một triệu tra khóa, 20.000 cập nhật và 500 lần xuất danh sách đã sắp theo mã. Chọn giữa mảng sắp xếp, Hash Map và cây cân bằng.

**Gợi ý:** Viết mô hình `B+qQ+uU+rD`. Mảng sắp có thể trả phí O(n) cho cập nhật; Hash Map tra cứu O(1) kỳ vọng nhưng có thể phải sắp khóa mỗi lần xuất; cây cân bằng tra/cập nhật O(log n) và duyệt có thứ tự Θ(n). Chọn theo yêu cầu bảo đảm độ trễ, bộ nhớ và các hệ số đo được, không tuyên bố một cấu trúc thắng tuyệt đối.

## 21. Checklist lựa chọn theo phân bố và vết thao tác

Trước khi quyết định dùng một cấu trúc dữ liệu, hãy điền mẫu sau:

```text
1. Hợp đồng:
   - Cần truy cập theo chỉ số, khóa hay thứ tự ưu tiên?
   - Trùng khóa được xử lý thế nào? Có yêu cầu thứ tự?
   - Truy vấn thiếu khóa có hành vi gì?

2. Quy mô:
   - n ban đầu, trung bình, tối đa?
   - Độ dài khóa k? Với đồ thị: V, E, phân bố bậc?

3. Phân bố dữ liệu:
   - Khóa đã sắp, gần sắp hay ngẫu nhiên?
   - Có khóa trùng, khóa nóng, khóa rất dài?
   - Dữ liệu có thay đổi phân bố theo thời gian không?

4. Vết thao tác:
   - Tỷ lệ get/put/remove/scan và thứ tự cụ thể?
   - Hit rate, miss rate, burst cập nhật?
   - Có các chuỗi làm resize/rehash hoặc chuyển hàng loạt?
   - Có cần duyệt khoảng, tìm min/max, thay độ ưu tiên?

5. Chứng minh chi phí:
   - Trường hợp xấu nhất mỗi lời gọi?
   - Kỳ vọng theo nguồn ngẫu nhiên và giả định nào?
   - Khấu hao áp dụng cho chuỗi thao tác nào?
   - Tổng thời gian xây + truy vấn + cập nhật + duyệt?

6. Bộ nhớ và đo đạc:
   - Byte/phần tử, số bucket/nút, sức chứa dự phòng?
   - Bộ nhớ đỉnh và tính cục bộ cache?
   - Benchmark có cùng vết và kiểm tra tính đúng không?
   - Kết quả có nhiều quy mô, seed và phân vị độ trễ không?

7. Kết luận:
   - Vì sao cấu trúc được chọn phù hợp với workload?
   - Điều kiện nào thay đổi sẽ khiến cần chọn lại?
```

**Kết luận:** Bảng độ phức tạp cho biết **cấu trúc có khả năng gì và giới hạn lý thuyết ra sao**. Phân bố dữ liệu và chuỗi thao tác cho biết **khả năng nào được dùng nhiều, trạng thái nào xảy ra và chi phí nào tích lũy trong thực tế**. Khi kết hợp đúng cả hai với bất biến, bộ nhớ và phép đo có thể tái lập, chúng ta mới có cơ sở để chọn mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap hay biểu diễn đồ thị cho từng bài toán.
