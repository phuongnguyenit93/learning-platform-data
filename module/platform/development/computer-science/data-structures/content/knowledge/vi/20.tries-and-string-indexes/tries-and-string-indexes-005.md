# Chi phí theo độ dài khóa và kích thước bảng chữ cái

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Chi phí theo độ dài khóa và kích thước bảng chữ cái

Hai trie cùng lưu 100.000 khóa nhưng có thể mang đặc tính chi phí rất khác nhau. Trie thứ nhất lưu các mã ngắn gồm chữ thường `a-z`; trie thứ hai lưu những chuỗi Unicode dài hàng nghìn ký hiệu. Nếu cả hai đều dùng một mảng con 26 ô tại mỗi nút, cấu trúc thứ nhất có thể phù hợp, còn cấu trúc thứ hai có thể không biểu diễn được toàn bộ ký hiệu đầu vào. Nếu cấp phát một ô cho mọi ký hiệu Unicode ở từng nút, bộ nhớ sẽ tăng rất lớn ngay cả khi phần lớn nút chỉ có một con.

Chính vì vậy, câu “tìm trong trie mất O(L)” cần được đọc kèm câu hỏi: **`L` là độ dài của cái gì, mỗi lần chọn một cạnh tốn bao nhiêu, và bảng chữ cái có kích thước `σ` bao nhiêu?** Khi chèn hoặc xóa, ta còn cần tính chi phí tạo/hủy nút, cấp phát bảng con và duy trì bất biến.

Bài học thuộc chương **Trie và chỉ mục chuỗi** của mô-đun **Cấu trúc dữ liệu** (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Ta sẽ dùng trie để luyện cách phân tích thời gian–bộ nhớ theo nhiều tham số, một kỹ năng áp dụng được cho cả mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị: phải nêu **mô hình chi phí, bất biến và loại thao tác** trước khi lựa chọn biểu diễn.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Phân biệt `n` (số khóa), `L` (độ dài khóa), `P` (độ dài tiền tố), `σ` (kích thước bảng chữ cái), `d_v` (số con của một nút), `N` (số nút) và `S` (tổng độ dài các khóa).
2. Giải thích vì sao tìm theo khóa trong trie thường có **chi phí theo `L`**, không trực tiếp theo `n`, nhưng điều đó cần giả định về giá lấy một cạnh.
3. Tính thời gian tìm/chèn/xóa với nút con lưu bằng mảng `σ` ô, Hash Map, mảng cạnh sắp hoặc cây cân bằng.
4. Phân tích cả **chi phí khởi tạo một nút mới** và **chi phí dọn nút khi xóa**, thay vì chỉ tính vòng lặp đi theo ký tự.
5. Ước lượng số nút và số ô bằng quan hệ `N≤1+S` và `\sum_v d_v=N-1`; nhận biết vai trò của chia sẻ tiền tố.
6. Phân biệt độ phức tạp của một phép tìm và **tổng chi phí xây** trie từ một dãy khóa có thể có trùng lặp.
7. Tính thêm chi phí duyệt cây con và ghi kết quả khi autocomplete; tránh nhầm O(P) cho toàn bộ truy vấn gợi ý.
8. Nhận biết tác động của code point Unicode, byte UTF-8, chuẩn hóa và chi phí so khớp đoạn trong trie nén.
9. Thiết lập bài đo với Python để quan sát số lần tra cạnh, số nút tạo và số ô mảng đang giữ; không đồng nhất số đếm logic với byte RAM thật.

## 2. Các tham số: “kích thước dữ liệu” không chỉ là số khóa

Một trie lưu **tập các chuỗi phân biệt**. Đặt:

| Ký hiệu | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| `n` | Số khóa phân biệt đang lưu | `n≥0` |
| `L` | Số ký hiệu của một khóa cần xử lý | `L≥0` |
| `P` | Số ký hiệu của tiền tố được hỏi | `P≥0` |
| `σ` | Số loại ký hiệu trong bảng chữ cái mà cấu trúc hỗ trợ | `σ≥1` khi bảng chữ cái không rỗng |
| `d_v` | Số cạnh ra **thật** của nút `v` | `0≤d_v≤σ` |
| `N` | Số nút của trie, bao gồm gốc | `N≥1` |
| `S` | Tổng độ dài của các **khóa phân biệt**: `\sum_{s\in K}|s|` | `S≥0` |
| `L_{\max}` | Độ dài khóa lớn nhất hiện có, nếu có | `L_{\max}≥0` |
| `k` | Số nút/cạnh **mới** phải tạo trong một lần chèn | `0≤k≤L` |

Ở đây `K` là tập khóa hiện có, vì vậy `n=|K|`. Ta sẽ dùng `S_{\mathrm{in}}` để chỉ tổng độ dài của **mọi chuỗi đưa tới quá trình xây dựng**, kể cả các khóa trùng; đại lượng này có thể lớn hơn `S` rất nhiều.

### 2.1. Ví dụ các tham số trên cùng một trie

Với:

```text
K = {"an", "anh", "ao", "ba", "ban"}
```

sơ đồ:

```text
                       root
                      /    \
                     a      b
                    / \      \
                   n*  o*     a*
                   |          |
                   h*         n*

* = dấu kết thúc khóa
```

Ta có:

- `n=5` khóa.
- `S=2+3+2+2+3=12` ký hiệu.
- Các tiền tố không rỗng phân biệt: `a, an, anh, ao, b, ba, ban`, nên `N=8`.
- Số cạnh `N-1=7`.
- Nút gốc có `d=2`, nút `a` có `d=2`, nút `an` có `d=1`, nút `anh` có `d=0`.
- Nếu bảng ký hiệu giới hạn `a-z`, thì `σ=26`, nhưng không nút nào cần sử dụng hết 26 nhánh.

### 2.2. Một khóa dài và một triệu khóa ngắn không cùng chi phí

Trường hợp A: tìm một khóa gồm `L=10.000` ký hiệu trong trie có 100 khóa. Trường hợp B: tìm một khóa dài 10 ký hiệu trong trie có một triệu khóa.

Nếu chọn cạnh là O(1), A có thể cần tới 10.000 bước chọn cạnh, B nhiều nhất 10. **Số khóa `n` không tự quyết định số bước tìm**, nhưng `n` và phân bố tiền tố vẫn ảnh hưởng số nút, bộ nhớ, cache và hình dạng các nhánh.

### 2.3. Độ dài theo đơn vị nào?

Bài sẽ phân tích trie **mỗi cạnh một ký hiệu**. Ký hiệu có thể là:

- Một byte (chẳng hạn trong trie trên dữ liệu UTF-8 đã mã hóa).
- Một Unicode code point (khi duyệt một chuỗi Python bằng `for ch in word`).
- Một bit (trie nhị phân, `σ=2`).
- Một đơn vị khác do ứng dụng quy định.

Không được dùng `L=“số chữ trông thấy”` rồi lấy thời gian xử lý **byte UTF-8** để suy ra O(L) mà không tính số byte thực sự phải đọc.

## 3. Mô hình lõi: chi phí một đường đi là tổng giá chọn cạnh

Đặt `g_{\mathrm{find}}(d,σ)` là chi phí tìm một cạnh có nhãn cho trước ở một nút có `d` nhánh, trong bảng chữ cái `σ` ký hiệu.

Nếu một khóa `word` có `L` ký hiệu và cả đường tồn tại, thao tác `contains(word)` phải chọn lần lượt các cạnh ở những nút:

\[
v_0\to v_1\to\cdots\to v_L.
\]

Gọi `d_i` là số con của nút `v_i` tại thời điểm tra ký hiệu thứ `i+1`. Chi phí có dạng:

\[
T_{\mathrm{lookup}}(word)
=O\left(1+\sum_{i=0}^{L-1}g_{\mathrm{find}}(d_i,σ)\right).
\]

Số `1` ở đây đại diện cho việc kiểm tra kết thúc khóa hoặc trả kết quả; nó giúp công thức bao quát cả `L=0`.

**Công thức theo từng nút quan trọng hơn chỉ một chữ O(L).** Khi `g_{\mathrm{find}}=O(1)` trên mọi nút, nó rút thành O(L+1). Nếu tìm một cạnh bằng quét `d_i` mục, tổng có thể lớn hơn nhiều.

### 3.1. Không phải lúc nào cũng đọc hết `L` ký hiệu

Với trie lưu `an, anh`:

- Tìm `anh`: đi qua cả ba ký hiệu.
- Tìm `axxxxxx`: thất bại ngay khi thử `x` sau `a`, không cần đọc toàn bộ phần còn lại.
- Tìm `a`: đường có nhưng nút `a` không terminal, phải trả False.
- Tìm `""`: không có bước chọn cạnh, chỉ kiểm tra gốc.

Do đó, O(L+1) là **chặn trên**. Một truy vấn thất bại sớm có thể chỉ tốn O(1) hoặc O(2) bước. Nếu phải phân tích trung bình, cần biết phân bố tiền tố xuất hiện trong truy vấn, không thể lấy mặc định `L/2`.

### 3.2. Chặn dưới trong mô hình trie không nén

Nếu tìm một khóa có đường đi dài `L` và thuật toán nhận khóa dưới dạng dãy ký hiệu chưa có chỉ mục phụ cho toàn khóa, nó phải đi qua `L` cạnh để tới nút terminal. Khi mỗi bước chọn cạnh được tính ít nhất một thao tác, chi phí **cho việc lần đường** là Ω(L).

Nhưng không được suy ra rằng **mọi** thao tác tìm thất bại đều Θ(L), hoặc mọi cấu trúc khác dùng khóa chuỗi cũng phải đi từng cạnh trie. Một Hash Map có thể dùng mã băm đã lưu, còn một trie nén có thể so khớp cả đoạn ký hiệu trên một cạnh theo cách khác.

## 4. Mảng con cố định: tra O(1) nhưng mỗi nút trả giá `σ`

Giả sử bảng chữ cái gồm `σ` ký hiệu được đánh chỉ số `0,\ldots,σ-1`. Mỗi nút giữ:

```text
children[0 .. sigma-1]
```

Ô `children[j]` là tham chiếu tới nút con theo ký hiệu thứ `j` hoặc `None` khi không có nhánh.

### 4.1. Chi phí tra một cạnh

Khi ký hiệu đã có chỉ số hoặc có thể ánh xạ tới chỉ số trong O(1):

\[
g_{\mathrm{find}}(d,σ)=\Theta(1).
\]

Do đó:

\[
T_{\mathrm{contains}}(L)=O(L+1).
\]

Điều đáng chú ý là **không phụ thuộc vào `d` hay `σ` trong phần chọn ô**, nhưng điều này cần giả định chỉ số có thể tính trong O(1) và bảng đã được cấp phát.

### 4.2. Cấp phát một nút mới không nhất thiết O(1)

Để tạo nút mới, một cài đặt mảng thường khởi tạo:

```python
children = [None] * sigma
```

Việc tạo mảng có `σ` ô thường cần **Θ(σ) thời gian và Θ(σ) ô nhớ**: có `σ` vị trí cần khởi tạo.

Giả sử chèn một khóa dài `L` và phải tạo `k` nút mới. Khi đó:

\[
T_{\mathrm{insert}}=O(L+1+kσ).
\]

- Nếu `σ=26` được coi là hằng số cố định, `T=O(L+1)`.
- Nếu `σ` biến động và `k=L`, thời gian có thể Θ(Lσ) trong mô hình khởi tạo mảng.
- Nếu đường của khóa đã tồn tại toàn bộ nhưng chưa terminal, `k=0`; vẫn cần đi `L` ký hiệu để xác nhận và đánh dấu.

**Câu “mỗi cạnh chọn O(1)” không xóa được chi phí khởi tạo các vùng chứa của nút mới.**

### 4.3. Xóa cạnh và giải phóng nút

Đổi một ô từ nút con thành `None` thường O(1). Tuy nhiên nếu xóa một khóa làm `r` nút trở nên không còn được tham chiếu, việc hủy hoặc tái chế **các mảng `σ` ô của những nút đó** có thể phải xử lý Θ(rσ) vị trí trong một runtime cần duyệt/giải phóng từng ô.

Vì vậy cần nêu mô hình:

- Nếu tính **thao tác cắt cạnh** và giả định thu hồi một nút là O(1), xóa dùng O(L+1) bước.
- Nếu mỗi nút bị thu hồi cần xử lý một mảng `σ` ô, một chặn trên có thể là O(L+1+rσ), với `0≤r≤L`.

Hai cách đếm đều hữu ích nếu ghi rõ giả định; không nên tuyên bố O(L) cho mọi cài đặt khi `σ` là tham số lớn.

### 4.4. Bộ nhớ vùng ô theo số nút

Nếu **mọi nút** đều cấp đúng `σ` ô:

\[
M_{\mathrm{slots}}=\Theta(Nσ)\quad\text{ô}.
\]

Phần lớn các ô có thể rỗng. Số cạnh **đang tồn tại** chỉ là `N-1`, còn số ô có thể có tới `Nσ`.

## 5. Bảng băm tại mỗi nút: chi phí kỳ vọng và tính thưa

Một cách khác là lưu `children` như một Hash Map:

```python
children = {"a": node_a, "n": node_n}
```

Bảng chỉ chứa những nhãn cạnh **thực sự tồn tại**.

### 5.1. Độ phức tạp chọn cạnh

Giả sử:

1. Một nhãn cạnh có thể được hash và so sánh trong O(1).
2. Chiến lược băm/phân bố va chạm phù hợp.
3. Hệ số tải của bảng con được kiểm soát.

Khi đó:

\[
\mathbb{E}[g_{\mathrm{find}}(d,σ)]=O(1).
\]

Ta suy ra:

\[
\mathbb{E}[T_{\mathrm{contains}}(L)]=O(L+1).
\]

Đây là **chặn kỳ vọng theo mô hình băm**. Trường hợp xấu nhất của một bảng băm tổng quát có thể gặp va chạm; một lần thêm cạnh cũng có thể kích hoạt tăng bảng/rehash.

### 5.2. Thời gian chèn và xóa

Một đường của khóa có tối đa `L` bước:

- Nếu tìm cạnh đã có, truy vấn Hash Map mỗi lần.
- Nếu thiếu cạnh, thêm mục nhãn → nút con mới.
- Nếu cần xóa nhánh chết, xóa mục trong Hash Map của cha.

Dưới giả định tra/cập nhật cạnh kỳ vọng O(1), cấp phát một nút chứa Hash Map rỗng có giá O(1), và chính sách mở rộng cho chi phí khấu hao phù hợp:

\[
T_{\mathrm{insert}},\ T_{\mathrm{delete}}
=O(L+1)\quad\text{theo kỳ vọng/khấu hao thích hợp}.
\]

Cần tách hai nguồn bảo đảm: **kỳ vọng** do va chạm hash và **khấu hao** do các lần đổi sức chứa. Một lần cập nhật riêng lẻ không nhất thiết có chặn O(L) xấu nhất.

### 5.3. Bộ nhớ không phải đúng `d` tham chiếu

Ở nút bậc ra `d`, Hash Map có thể cần:

- Dữ liệu `d` nhãn và nút con.
- Header của Map/dictionary.
- Các ô bucket dự phòng và metadata xử lý va chạm.
- Vùng đệm tạm khi tái băm.

Bộ nhớ tổng cho những cạnh thật có thể được mô hình hóa là O(N-1) mục với hệ số tải được giữ thích hợp, **cộng overhead của N bảng con**. Như vậy xét theo số nút/cạnh, thường O(N), nhưng số byte trên một nút có thể lớn.

### 5.4. Thứ tự nhãn không được bảo đảm

Hash Map phù hợp để **tìm đúng một nhãn**, nhưng nếu autocomplete yêu cầu liệt kê nhánh theo thứ tự từ điển, nó có thể phải sắp các nhãn ở mỗi nút:

\[
T_{\mathrm{sort\ children}}(d)=O(d\log(d+1)).
\]

Thứ tự chèn trong `dict` Python **không đồng nghĩa** thứ tự tăng dần của các ký tự. Vì vậy ứng dụng thường xuyên xuất theo thứ tự có thể muốn một biểu diễn con khác hoặc một chỉ mục/cached order bổ sung.

## 6. Tập cạnh có thứ tự: phải nêu rõ cấu trúc bên trong

“Tập cạnh có thứ tự” không phải một mô hình chi phí duy nhất. Hai triển khai quan trọng là **mảng cặp cạnh đã sắp** và **cây tìm kiếm cân bằng theo nhãn**.

### 6.1. Mảng các cạnh đã sắp

Ví dụ:

```text
labels = ["a", "m", "z"]
nodes  = [node_a, node_m, node_z]
```

Tại một nút có `d` cạnh:

- Tìm nhãn bằng tìm nhị phân: O(log(d+2)).
- Chèn nhãn mới: tìm vị trí O(log(d+2)), sau đó **dịch** tới O(d) mục.
- Xóa một nhãn: tìm vị trí O(log(d+2)), sau đó dịch tới O(d) mục.
- Duyệt toàn bộ cạnh tăng dần: Θ(d).

Với trie, tìm khóa dài `L` có thể được chặn bởi:

\[
T_{\mathrm{contains}}
=O\left(1+\sum_{i=0}^{L-1}\log(d_i+2)\right)
=O(1+L\log(σ+2)).
\]

Khi thêm hoặc xóa, cần cộng chi phí dịch những mảng của các nút có cạnh thật sự thay đổi:

\[
T_{\mathrm{update}}=
O\left(1+L\log(σ+2)+
\sum_{v\in U}(d_v+1)\right),
\]

trong đó `U` là tập nút cha có thêm/xóa một cạnh, và số hạng `d_v` là bậc ra tại lúc sửa.

### 6.2. Cây tìm kiếm cân bằng lưu các cạnh

Nếu mỗi nút trie giữ một ordered map dưới dạng cây AVL/đỏ-đen theo **nhãn cạnh**:

- Tìm cạnh: O(log(d+2)) trường hợp xấu nhất.
- Thêm cạnh: O(log(d+2)) trường hợp xấu nhất.
- Xóa cạnh: O(log(d+2)) trường hợp xấu nhất.
- Duyệt theo thứ tự: Θ(d).

Suy ra các thao tác theo đường khóa:

\[
T_{\mathrm{contains/insert/delete}}
=O(1+L\log(σ+2)),
\]

với giả định so sánh nhãn và cấp phát một nút nhỏ có giá O(1). Chi phí khởi tạo cấu trúc con rỗng phải được tính nếu không phải O(1).

Một mảng đã sắp **không tự trở thành cây cân bằng** chỉ vì ta dùng tìm kiếm nhị phân. Tìm O(log d) không có nghĩa chèn/xóa cũng O(log d) nếu phải dịch phần tử.

### 6.3. Tham số `σ` có thể che nhiều chi phí

Vì `d_v≤σ`, mọi lần tra theo cây hoặc mảng sắp có chặn trên bằng O(log(σ+2)). Nhưng chặn này có thể lỏng nếu hầu hết nút có `d_v=1`.

Khi phân tích thực tế, sử dụng dãy bậc ra `d_0,d_1,\ldots` trên **những đường truy vấn thật** chính xác hơn việc dùng `σ` tối đa ở mọi bước.

## 7. Bảng tổng hợp: chi phí tính theo `L`, `σ` và `d`

Các hàng sau đếm thao tác theo **mô hình từ máy**, với một ký hiệu cạnh/địa chỉ nút xử lý trong O(1). `k` là số nút mới và `r` là số nút bị loại sau xóa.

| Biểu diễn cạnh | Chọn cạnh tại nút bậc `d` | Tìm khóa độ dài `L` | Chèn khóa | Bộ nhớ bảng con |
| --- | --- | --- | --- | --- |
| Mảng cố định `σ` ô | O(1) xấu nhất | O(L+1) | O(L+1+kσ) nếu tạo mảng mới Θ(σ) | Θ(Nσ) ô |
| Hash Map | O(1) kỳ vọng | O(L+1) kỳ vọng | O(L+1) kỳ vọng/khấu hao theo giả định | Theo mục cạnh và overhead bảng, thường O(N) từ |
| Mảng cạnh đã sắp | O(log(d+2)) | O(1+L log(σ+2)) | Cộng chi phí dịch O(d) nơi tạo cạnh | O(N) mục/metadata trong mô hình |
| Cây cân bằng lưu cạnh | O(log(d+2)) xấu nhất | O(1+L log(σ+2)) | O(1+L log(σ+2)) | O(N) nút cạnh và metadata |

Đối với xóa:

- Mảng cố định: O(L+1) cho tra/cắt cạnh, có thể thêm O(rσ) để xử lý giải phóng các mảng nút bị dọn nếu tính chi phí ấy.
- Hash Map: O(L+1) kỳ vọng theo thao tác cạnh, cộng các sự kiện bảo trì nếu có.
- Mảng cạnh sắp: O(1+L log(σ+2)+\sum_{v\in U}(d_v+1)).
- Cây cân bằng lưu cạnh: O(1+L log(σ+2)) theo mô hình nêu trên.

**Không trộn “kỳ vọng”, “khấu hao” và “xấu nhất” thành một bảo đảm duy nhất.** Mỗi phát biểu phải đi với mô hình và tập thao tác được phép.

### 7.1. Bảng chữ cái cố định nhỏ

Khi `σ=26` là một **hằng số**, `d≤26`. Những hàm `σ`, `log(σ+2)` và `d` trở thành hằng số trong biểu thức theo `L`.

Vì vậy nhiều cài đặt có thể cùng chặn O(L+1), dù một cài đặt khởi tạo 26 ô mỗi nút, cài đặt khác tạo dictionary, và cài đặt thứ ba dùng tìm nhị phân trên tối đa 26 nhãn. **Đồng bậc Big-O không có nghĩa đồng byte hoặc đồng thời gian trên máy thật.**

### 7.2. Bảng chữ cái lớn và biến thiên

Nếu `σ` là biến theo bài toán, không thể bỏ nó khỏi công thức. Trie dùng mảng 1.000 ô mỗi nút và trie dùng mảng 26 ô mỗi nút có cùng logic tìm, nhưng khác rất xa về vùng nhớ cho nút một con.

### 7.3. Nút có độ phân nhánh nhỏ

Trên đường của nhiều khóa, `d_i` có thể chỉ bằng 0, 1 hoặc 2. Khi đó, mảng cạnh sắp có thể rất nhỏ; chọn một nhãn bằng so sánh tuyến tính thậm chí cũng có thể phù hợp với hệ số thực tế thấp. Big-O theo `σ` cực đại không thể thay thế thống kê bậc ra thật.

## 8. Chia sẻ tiền tố quyết định `N` và bộ nhớ của toàn trie

Mỗi nút không phải gốc tương ứng **một tiền tố không rỗng phân biệt** của ít nhất một khóa, khi trie không nén và luôn dọn nhánh chết.

Vì vậy:

\[
N=1+\left|\bigcup_{s\in K}
\{\text{các tiền tố không rỗng của }s\}\right|.
\]

Từ đó suy ra:

\[
1\le N\le 1+S.
\]

Nếu `n>0` và có khóa dài nhất `L_{\max}`, ta còn có:

\[
N\ge L_{\max}+1.
\]

Tổng cạnh:

\[
\sum_{v}d_v=N-1.
\]

Đây là cơ sở để so sánh **số ô đã cấp** với **số cạnh thật**.

### 8.1. Ví dụ cùng dữ liệu nhưng khác số nhánh

Với `K={"an","anh","ao","ba","ban"}`:

- `S=12`.
- `N=8`.
- Cạnh thật: `7`.
- Nếu dùng mảng 26 ô: `8\cdot26=208` ô, trong đó `201` ô không có cạnh.

Nếu giả sử mỗi ô tham chiếu rộng 8 byte, riêng vùng ô tham chiếu có:

\[
208\cdot8=1.664\ \text{byte}.
\]

Đây **không phải tổng RAM của trie**: còn đối tượng nút, header vùng chứa, bộ đếm và các vùng phụ.

### 8.2. Ví dụ có tiền tố chung rất dài

Giả sử có 26 khóa: mỗi khóa gồm 100 ký hiệu `a` theo sau bởi **một chữ cái khác nhau** `a,b,\ldots,z`.

Khi đó:

- `n=26`.
- Mỗi khóa dài 101, nên `S=26\cdot101=2.626`.
- Có 100 nút trên đoạn chung `a^{100}`, rồi 26 nút con cho ký hiệu cuối.
- Cộng gốc: `N=1+100+26=127`.
- Cạnh thật: 126.
- Mảng 26 ô mỗi nút cấp `127\cdot26=3.302` ô.

Nếu không chia sẻ đoạn đầu, mô hình tạo đường riêng cho mỗi từ sẽ cần gần `S` bước ký hiệu. Trie chia sẻ đường đầu giúp giảm **số nút cần thiết**, nhưng mỗi nút vẫn phải trả overhead do cách lưu nhánh.

### 8.3. Vì sao số khóa `n` không đủ ước lượng RAM?

Một tập gồm 26 khóa dài 101 và chung 100 ký hiệu đầu sẽ có số nút rất khác một tập gồm 26 khóa không có đoạn tiền tố chung dài. Cả hai cùng `n=26`, nhưng:

- `N` khác.
- Số nút lá và nút một con khác.
- Số dictionary/mảng con cần cấp phát khác.
- Dung lượng dự phòng và tính cục bộ bộ nhớ khác.

Muốn ước lượng RAM, phải biết **tổng ký hiệu và phân bố tiền tố**, không chỉ số khóa.

## 9. Một mô hình ước tính byte và điểm hòa vốn

Hãy tạm giả sử:

- Mỗi ô con trỏ trong mảng cố định rộng `p` byte.
- Overhead chung của một nút là `H_n` byte.
- Một Hash Map con có phần overhead cố định `H_h` byte.
- Mỗi cạnh thật trong mô hình Hash Map tốn khoảng `e_h` byte, đã gộp một phần metadata/bucket bình quân.

Khi đó:

\[
M_{\mathrm{array}}(d,σ)
\approx H_n+σp,
\]

\[
M_{\mathrm{hash}}(d)
\approx H_n+H_h+d\,e_h.
\]

Phương án mảng có thể tiết kiệm **theo mô hình giả định** khi:

\[
σp < H_h+d\,e_h.
\]

### 9.1. Ví dụ minh họa, không phải số đo Python

Giả định `σ=26`, `p=8`, `H_h=72` và `e_h=24` byte:

- Mảng có vùng ô: `26\cdot8=208` byte.
- Hash với `d=1`: `72+1\cdot24=96` byte.
- Hash với `d=8`: `72+8\cdot24=264` byte.

Trong mô hình này, hash thuận lợi về **byte vùng con** ở `d=1`, còn mảng thuận lợi ở `d=8`. Điểm hòa vốn là:

\[
d>\frac{208-72}{24}\approx5,67.
\]

Đây chỉ là ví dụ với **chi phí tuyến tính giả định**. Hash Map thực có các ngưỡng dung lượng rời rạc, header, padding và cách quản lý bộ nhớ riêng; không thể lấy `d=6` làm ngưỡng chung cho Python, C++ hoặc Java.

### 9.2. So sánh ở quy mô 100.000 nút

Với `N=100.000` nút, con trỏ 8 byte và mảng con ở **mọi** nút:

| `σ` | Tổng ô con | Byte vùng ô giả định |
| ---: | ---: | ---: |
| 2 | 200.000 | 1.600.000 byte (1,6 MB) |
| 26 | 2.600.000 | 20.800.000 byte (20,8 MB) |
| 256 | 25.600.000 | 204.800.000 byte (204,8 MB) |
| 1.114.112 | 111.411.200.000 | 891.289.600.000 byte (khoảng 891,3 GB) |

Hàng cuối minh họa việc cấp sẵn một ô cho **toàn bộ không gian giá trị code point từ 0 tới 0x10FFFF**, không khẳng định mọi giá trị đó là ký tự Unicode scalar hợp lệ. Một chương trình thực tế **không nên làm vậy ở mỗi nút**.

Các số chỉ tính ô con; chưa tính payload, header, allocator, bộ đếm, bảng chuyển đổi nhãn hoặc vùng RAM khác.

## 10. Chi phí xây trie từ một dãy đầu vào

Giả sử dữ liệu đầu vào gồm `m` chuỗi `s_1,\ldots,s_m`, có thể chứa những khóa trùng. Gọi:

\[
S_{\mathrm{in}}=\sum_{j=1}^{m}|s_j|.
\]

Tổng thời gian xử lý đường ký hiệu của mọi chuỗi ít nhất liên quan tới `S_{\mathrm{in}}` trong thuật toán thêm từng khóa. Với chọn cạnh O(1) và khởi tạo một nút mới O(1):

\[
T_{\mathrm{build}}
=O(m+S_{\mathrm{in}})
\]

theo mô hình truy cập cạnh tương ứng, không phải O(`S`) khi có nhiều khóa trùng rất dài.

### 10.1. Ví dụ bị trùng lặp nhiều

Một tập cuối chỉ có một khóa dài 100 ký hiệu. Nhưng dãy đầu vào yêu cầu chèn khóa đó **một triệu lần**.

- `n=1` khóa phân biệt.
- `S=100` ký hiệu của tập cuối.
- `S_{\mathrm{in}}=100.000.000` ký hiệu đã đưa qua các lời gọi chèn.

Bộ nhớ cấu trúc cuối có thể chỉ theo một đường dài 100, nhưng thời gian xử lý **một triệu yêu cầu** không thể suy ra từ `S=100`.

### 10.2. Tổng chi phí khởi tạo mảng con

Với mảng `σ` ô và `N-1` nút ngoài gốc được tạo (cộng gốc):

\[
T_{\mathrm{build,array}}
=O(m+S_{\mathrm{in}}+Nσ)
\]

trong mô hình tạo mỗi nút một mảng `σ` ô. Có thể viết chặt hơn theo số nút thực tạo, nhưng ý chính là **chi phí khởi tạo con** tăng theo `Nσ`.

Nếu `σ` cố định, giới hạn này rút về O(`m+S_{\mathrm{in}}`), vì số nút không thể vượt tổng số ký hiệu đã chèn cộng một.

### 10.3. Tạo trie từ khóa đã có thứ tự có làm giảm giá duyệt ký hiệu?

Khi các khóa được sắp và có chung tiền tố, một thuật toán xây chuyên dụng có thể tái sử dụng thông tin về tiền tố chung dài nhất với khóa trước để giảm việc đi lại từ gốc, tùy biểu diễn và cách tính tiền tố.

Tuy nhiên, nếu đọc dữ liệu đầy đủ và cần phân biệt mọi khóa, thời gian nhập liệu vẫn phải xử lý lượng dữ liệu tương ứng với kích thước đầu vào. **Đừng suy rằng “đã sắp xếp” khiến mọi bước xử lý ký hiệu trở thành O(1) cho toàn bộ tập**.

## 11. Chèn và xóa: số nút mới hay bị dọn quan trọng ra sao?

### 11.1. Chèn dùng chung tiền tố

Với khóa `word` dài `L`, gọi `r` là độ dài tiền tố đầu dài nhất đã có đường đi trong trie trước khi chèn.

Nếu `word` chưa là khóa hoàn chỉnh:

\[
k=L-r
\]

nút mới sẽ được tạo, khi đường của `word` trước đó chỉ có tới độ dài `r`.

Ví dụ:

- Trie đang chứa `"anh"`, chèn `"an"`: `L=2`, `r=2`, `k=0`. Chỉ đánh dấu terminal ở nút `an`.
- Trie chứa `"an"`, chèn `"anh"`: `L=3`, `r=2`, `k=1`.
- Trie chưa có nhánh `b`, chèn `"ban"`: `L=3`, `r=0`, `k=3`.

Độ dài tiền tố dùng chung quyết định **số nút cần cấp phát**, dù số lần tra ký hiệu vẫn có chặn O(L+1).

### 11.2. Chèn trùng không cấp thêm khóa

Nếu đường đi của khóa đã có và nút cuối `terminal=True`, một Set nên trả False và giữ nguyên bộ đếm. Có thể đã đi qua đủ `L` ký hiệu để biết điều đó, nhưng:

- Không tạo nút mới.
- Không tăng `size`.
- Không tăng `subtree_count` của bất kỳ nút nào.

### 11.3. Xóa an toàn nhánh dùng chung

Với tập `{an,anh}`, xóa `an` chỉ bỏ dấu terminal tại nút `an`, không xóa nhánh tới `anh`. Nếu xóa `anh` khi `an` vẫn còn, nút `h` có thể bị dọn, còn nút `an` vẫn phải giữ.

Để dọn đúng, mỗi nút có thể giữ số khóa hoàn chỉnh trong cây con:

\[
count(v)=\mathbf{1}_{terminal(v)}
+\sum_{u\in children(v)}count(u).
\]

Khi xóa một khóa có thật, giảm 1 trên đường từ gốc tới nút cuối. Chỉ cắt cạnh tới cây con có `count=0`.

### 11.4. Xóa tới khi trie rỗng

Gốc vẫn tồn tại dù mọi khóa đã bị xóa. Với mảng cố định, gốc vẫn giữ `σ` ô theo thiết kế cấp sẵn; với Hash Map, gốc có thể giữ một dictionary rỗng. Do đó **không nên chia bộ nhớ hiện tại cho số khóa** khi `n=0` — phép chia không xác định và overhead cố định vẫn tồn tại.

## 12. Truy vấn tiền tố và liệt kê: độ dài đầu ra cũng là kích thước dữ liệu

Có hai bài toán khác nhau:

1. **Kiểm tra có một đường tiền tố** `prefix`: lần theo `P` ký hiệu.
2. **Liệt kê tất cả khóa bắt đầu bằng `prefix`**: tìm nút tiền tố, rồi duyệt cây con và tạo kết quả.

Nếu `R` là số nút được thăm trong cây con, và `Z` là tổng số ký hiệu phải **xuất ra** của các khóa kết quả, ta có các thành phần chi phí:

\[
T_{\mathrm{autocomplete}}
=T_{\mathrm{locate}}(P)
+T_{\mathrm{traverse}}(R,σ,d)
+\Omega(Z)\ \text{công việc xuất}.
\]

Dấu Ω(Z) thể hiện **cận dưới cho đầu ra**: không thể tạo tổng cộng `Z` ký hiệu chuỗi trong thời gian ít hơn lượng công việc tương ứng dưới mô hình xuất từng ký hiệu.

### 12.1. Mảng cố định

Nếu mỗi nút phải quét đủ `σ` ô để liệt kê nhãn có con:

\[
T_{\mathrm{traverse,array}}=O(Rσ)
\]

cho phần duyệt ô, cộng chi phí tạo chuỗi kết quả. Với `σ` lớn, việc quét rất nhiều ô rỗng có thể chi phối thời gian gợi ý.

### 12.2. Bảng băm

Nếu duyệt trực tiếp các cạnh hiện có mà **không yêu cầu thứ tự**, tổng phần duyệt cạnh thường O(R) kỳ vọng/khấu hao theo cách biểu diễn.

Nếu muốn kết quả theo **thứ tự ký hiệu**, có thể phải sắp nhãn của mỗi nút đã thăm:

\[
T_{\mathrm{traverse,hash}}
=O\left(R+\sum_{v\ \text{được thăm}}d_v\log(d_v+1)\right)
\]

cộng chi phí tạo kết quả và các giả định thích hợp.

### 12.3. Mảng cạnh sắp hoặc cây cân bằng con

Các cạnh đã có thứ tự, nên phần liệt kê cạnh có thể O(R) nếu mỗi cạnh được thăm hữu hạn lần. Ta vẫn phải trả giá cho độ sâu các nút trung gian và các chuỗi kết quả.

### 12.4. Không tạo chuỗi mới ở mọi cạnh nếu cần tối ưu

Một DFS đơn giản:

```python
stack.append((prefix + char, child))
```

có thể sao chép toàn bộ tiền tố tại mỗi bước xuống. Nếu các nhánh rất dài, tổng byte sao chép các **chuỗi trung gian** lớn hơn số ký tự của kết quả cuối.

Một DFS giữ danh sách ký hiệu đường đi, dùng sự kiện **vào/ra nút**, chỉ `"".join(path)` tại nút terminal sẽ giúp tránh nhiều lần nối chuỗi trung gian. Điều này làm rõ rằng phân tích `R+Z` cần gắn với **cài đặt thực tế**, không chỉ với số nút đã duyệt.

## 13. Ví dụ Python: đo bước logic của hai biểu diễn

Để thấy sự khác biệt giữa “tìm mất bao nhiêu bước” và “đã cấp phát bao nhiêu ô”, ta xây hai trie cùng hợp đồng, cùng bảng ký hiệu `a-z`:

- `dense=True`: mọi nút có mảng 26 ô con.
- `dense=False`: mỗi nút có dictionary chỉ lưu các cạnh đang tồn tại.

Mã dưới đây đếm:

- `edge_probes`: số lần thử lấy một cạnh.
- `nodes_live`: số nút đang còn trong trie.
- `nodes_ever_created`: tổng số nút đã tạo trong vòng đời.
- `edge_count`: số cạnh thật đang còn.
- `dense_slots_live`: số ô con đã cấp trong bản mảng, **không phải byte RAM**.

### 13.1. Cài đặt minh họa

```python
class CostNode:
    __slots__ = ("children", "terminal", "subtree_keys")

    def __init__(self, dense):
        self.children = [None] * 26 if dense else {}
        self.terminal = False
        self.subtree_keys = 0


class CostTrie:
    def __init__(self, dense=False):
        self.dense = dense
        self.root = CostNode(dense)
        self.size = 0

        self.edge_probes = 0
        self.nodes_live = 1
        self.nodes_ever_created = 1
        self.edge_count = 0

    @staticmethod
    def _validate(word):
        if not isinstance(word, str):
            raise TypeError("khóa phải là str")
        if any(ch < "a" or ch > "z" for ch in word):
            raise ValueError("ví dụ chỉ hỗ trợ chữ thường ASCII a-z")

    def _get(self, node, char):
        self.edge_probes += 1
        if self.dense:
            return node.children[ord(char) - ord("a")]
        return node.children.get(char)

    def _put_new(self, node, char, child):
        if self.dense:
            node.children[ord(char) - ord("a")] = child
        else:
            node.children[char] = child
        self.edge_count += 1

    def _drop(self, node, char):
        if self.dense:
            node.children[ord(char) - ord("a")] = None
        else:
            del node.children[char]
        self.edge_count -= 1
        self.nodes_live -= 1

    def _new_node(self):
        self.nodes_live += 1
        self.nodes_ever_created += 1
        return CostNode(self.dense)

    def contains(self, word):
        self._validate(word)
        node = self.root
        for char in word:
            node = self._get(node, char)
            if node is None:
                return False
        return node.terminal

    def insert(self, word):
        self._validate(word)

        node = self.root
        path = [node]

        for char in word:
            child = self._get(node, char)
            if child is None:
                child = self._new_node()
                self._put_new(node, char, child)
            node = child
            path.append(node)

        if node.terminal:
            return False

        node.terminal = True
        for item in path:
            item.subtree_keys += 1
        self.size += 1
        return True

    def delete(self, word):
        self._validate(word)

        node = self.root
        path = [node]

        for char in word:
            node = self._get(node, char)
            if node is None:
                return False
            path.append(node)

        if not node.terminal:
            return False

        node.terminal = False
        for item in path:
            item.subtree_keys -= 1

        for index in range(len(word) - 1, -1, -1):
            parent = path[index]
            child = path[index + 1]
            if child.subtree_keys > 0:
                break
            self._drop(parent, word[index])

        self.size -= 1
        return True

    def count_prefix(self, prefix):
        self._validate(prefix)
        node = self.root
        for char in prefix:
            node = self._get(node, char)
            if node is None:
                return 0
        return node.subtree_keys

    @property
    def dense_slots_live(self):
        return 26 * self.nodes_live if self.dense else 0

    def stats(self):
        return {
            "keys": self.size,
            "nodes_live": self.nodes_live,
            "nodes_ever_created": self.nodes_ever_created,
            "edges_live": self.edge_count,
            "edge_probes": self.edge_probes,
            "dense_slots_live": self.dense_slots_live,
        }
```

**Phạm vi của số đo:** `nodes_live` và `dense_slots_live` là **số đếm logic** do lớp cập nhật, không trực tiếp đo được số byte đã trả cho hệ điều hành. Ở bản dictionary, `dense_slots_live=0` chỉ nghĩa không có *mảng cố định 26 ô*; nó **không** nghĩa dictionary tốn 0 byte.

### 13.2. Dùng cùng tập từ và kiểm tra kết quả

```python
words = ["an", "anh", "ao", "ba", "ban"]

for dense in (False, True):
    trie = CostTrie(dense=dense)

    for word in words:
        assert trie.insert(word)

    assert trie.size == 5
    assert trie.nodes_live == 8
    assert trie.edge_count == 7
    assert trie.count_prefix("a") == 3
    assert trie.count_prefix("an") == 2

    assert trie.contains("an")
    assert not trie.contains("a")
    assert not trie.insert("an")

    before = trie.edge_probes
    assert trie.contains("anh")
    assert trie.edge_probes - before == 3

    before = trie.edge_probes
    assert not trie.contains("axxxxxxxxx")
    assert trie.edge_probes - before == 2

    assert trie.delete("an")
    assert trie.contains("anh")
    assert trie.count_prefix("an") == 1

    assert trie.delete("anh")
    assert not trie.contains("anh")
    assert not trie.contains("an")
    assert trie.nodes_live == 6
    assert trie.edge_count == 5

    assert trie.nodes_live == trie.edge_count + 1
    if dense:
        assert trie.dense_slots_live == trie.nodes_live * 26
    else:
        assert trie.dense_slots_live == 0

    print("dense =", dense, trie.stats())
```

Ở ví dụ này:

- Ban đầu 8 nút, 7 cạnh là đúng theo tập khóa.
- Tìm `anh` đi qua đúng 3 cạnh.
- Tìm `axxxxxxxxx` thất bại ở bước thử ký hiệu thứ 2 vì không có nhánh `x` sau `a`.
- Xóa `an` không làm mất `anh`.
- Xóa tiếp `anh` cắt hai nút `h` và `n` dưới nhánh `a`; còn 6 nút, 5 cạnh vì `ao`, `ba` và `ban` vẫn tồn tại.

Những câu khẳng định trên là **kết quả logic được mong đợi từ mã**, không phải số liệu thời gian đo trên máy.

### 13.3. Ý nghĩa khi hai bản có cùng số cạnh đã dùng

Ở cùng một tập khóa và chuỗi thao tác, hai bản có:

- Cùng `nodes_live` và `edge_count` nếu giữ đúng bất biến và cùng quy tắc dọn nhánh.
- Cùng số lần **thử chọn cạnh theo đường ký tự** trong thuật toán này.
- Khác `dense_slots_live` và overhead biểu diễn.
- Có thể khác thời gian thực tế vì mảng chỉ số và dictionary là thao tác khác nhau.

Vì vậy, “cùng O(L)” **không chứng minh** thời gian chạy bằng nhau, và “số ô mảng lớn hơn” **không tự chứng minh** tổng byte lớn hơn nếu dictionary có header lớn. Cần đo cả hai.

## 14. Vết thao tác và phân bố truy vấn ảnh hưởng phép đo

Chi phí tìm một khóa không phải luôn đúng `L` bước:

| Kiểu truy vấn | Số lần thử chọn cạnh trong trie không nén |
| --- | --- |
| Khóa có đường đi đầy đủ, dù terminal True hay False | `L` |
| Thất bại tại ký hiệu thứ `j` (đếm từ 1) | `j≤L` |
| Chuỗi rỗng | 0 |
| Truy vấn cùng tiền tố dài nhưng sai ký hiệu cuối | Có thể gần `L` |
| Truy vấn ngẫu nhiên thường sai ngay ở gốc | Có thể rất ít bước |

### 14.1. Kỳ vọng số bước theo xác suất tiền tố sống

Giả sử mọi truy vấn dài đúng `L`. Đặt `q_j` là xác suất **đường của `j` ký hiệu đầu tiên** tồn tại trong trie, với `q_0=1`.

Vòng lặp phải thử cạnh thứ `j+1` khi và chỉ khi tiền tố dài `j` còn tồn tại. Vì vậy số lần thử cạnh kỳ vọng là:

\[
\mathbb{E}[C]
=\sum_{j=0}^{L-1}q_j.
\]

Nếu mọi truy vấn đều có đường tồn tại đầy đủ, `q_j=1` với mọi `j<L`, nên `\mathbb{E}[C]=L`. Nếu phần lớn truy vấn thiếu ngay nhánh đầu, chỉ số kỳ vọng có thể gần 1.

Công thức chỉ đếm **lần thử cạnh**; nếu một lần chọn cạnh tốn `g(d_j,σ)` khác hằng số, phải tính chi phí đó thay vì dùng trực tiếp số bước.

### 14.2. Tần suất khóa nóng và cache

Một khóa được tìm nhiều lần có thể khiến các nút trên đường của nó thường được CPU lưu trong cache. Hai cấu trúc đều O(L) theo mô hình RAM vẫn có thời gian thực tế khác vì:

- Nút của mảng và dictionary có cách bố trí bộ nhớ khác.
- Nhiều nút nhỏ có thể gây cấp phát và truy cập rải rác.
- Mảng cố định giữ nhiều ô rỗng làm tăng vùng bộ nhớ đang giữ.
- Các truy vấn rất dài có thể lặp lại nhiều nút một con.

Khi phân tích ứng dụng, phải ghi cả **phân bố độ dài khóa** và **phân bố các truy vấn**.

### 14.3. Đừng chỉ đo một lần tra cứu

Nếu ứng dụng thường xuyên chèn/xóa, nên đo:

- Chi phí xây dựng ban đầu.
- Số nút mới tạo theo từng lần chèn.
- Độ trễ của các lần tạo nhiều nút.
- Bộ nhớ đỉnh và vùng đệm được giữ lại.
- Chi phí autocomplete và số kết quả.
- Kết quả đúng sau chuỗi chèn/xóa.

Một biểu diễn tra nhanh nhưng dùng RAM vượt ngân sách hoặc làm cập nhật quá chậm không phải lựa chọn tốt cho ứng dụng đó.

## 15. Unicode có thể thay đổi cả `L` lẫn cách hiểu `σ`

Trie cho từ điển tiếng Việt cần định nghĩa **ký hiệu là gì**.

### 15.1. Byte UTF-8, code point và grapheme cluster

Xét một chữ có dấu:

- Ở mức **code point** Python, một ký tự dựng sẵn có thể là một đơn vị.
- Ở mức **UTF-8**, nó có thể cần nhiều byte.
- Ở mức **grapheme cluster**, một chữ hiển thị có thể gồm nhiều code point nhưng được xem là một cụm.

Ví dụ:

```python
word = "bàn"

print(len(word))                 # Số code point trong str Python.
print(len(word.encode("utf-8"))) # Số byte mã hóa UTF-8.
```

Cùng một từ nhìn thấy có thể có `L` khác nhau nếu trie được xây trên byte hay code point. Vì vậy bảng độ phức tạp phải ghi **đơn vị độ dài**.

### 15.2. Chuẩn hóa thay đổi biểu diễn khóa

```python
import unicodedata

composed = "bàn"
decomposed = "ba\u0300n"

assert composed != decomposed
assert unicodedata.normalize("NFC", composed) == \
       unicodedata.normalize("NFC", decomposed)
```

Nếu không chuẩn hóa, trie theo code point có thể tạo những đường khác nhau cho hai dạng biểu diễn. Muốn coi chúng là một khóa, cần chuẩn hóa **khi chèn, tìm và xóa**, và tính thêm chi phí của bước chuẩn hóa nếu đánh giá toàn bộ pipeline.

### 15.3. `σ` hữu hạn theo toàn bộ Unicode hay theo alphabet thật?

Không phải ứng dụng tiếng Việt nào cũng cần một ô cho mọi code point có thể biểu diễn. Có thể lựa chọn:

- **Bảng alphabet nhỏ đã xác định:** chỉ những ký hiệu hợp lệ được phép nhập, cùng hàm chuyển ký hiệu → chỉ số.
- **Hash Map ký hiệu:** chỉ lưu nhánh thực và hỗ trợ mở rộng ký hiệu.
- **Mảng cặp cạnh đã sắp:** dùng comparator ký hiệu đã định nghĩa.
- **Trie theo byte:** có tối đa 256 nhãn byte, nhưng đường đi của ký tự Unicode thường dài hơn.

Cần đánh đổi **`σ` ở mỗi nút** với **`L` sau cách mã hóa**, không chỉ tìm một phương án có số bước nhỏ hơn trên giấy.

### 15.4. Thứ tự gợi ý là một hợp đồng khác

Sắp nhãn theo code point Unicode chưa chắc trùng thứ tự từ điển tiếng Việt. Nếu cần thứ tự theo locale hoặc theo tần suất, phải bổ sung comparator hoặc thông tin xếp hạng phù hợp.

Cơ chế lựa chọn cạnh O(1) không làm chi phí **sắp hoặc xếp hạng gợi ý** biến mất.

## 16. Trie nén đường: ít nút hơn nhưng giá so khớp cạnh khác

Một **radix trie** hoặc trie nén đường có thể gộp các đoạn nút chỉ có một con thành một cạnh mang **chuỗi ký hiệu** thay vì một ký hiệu.

Ví dụ:

```text
Trie thường: root -> a -> b -> c -> d*
Trie nén:   root --"abcd"--> terminal
```

Số nút giảm, nhưng để theo một cạnh có nhãn `"abcd"`, thuật toán phải so khớp ký hiệu của đoạn với phần còn lại của khóa.

### 16.1. Điều gì xảy ra với O(L)?

Giả sử các cạnh trên đường tìm có nhãn đoạn dài `\ell_1,\ldots,\ell_t`, và tổng số ký hiệu được so khớp trên đường không vượt quá `L` trong tìm thông thường.

Khi việc so khớp đoạn được tính **theo số ký hiệu đã kiểm tra**, tổng chi phí xử lý ký hiệu trên một đường đầy đủ vẫn có thể O(L), cộng chi phí chọn cạnh tại `t` nút.

Nhưng nếu mỗi lần chọn một nhãn cạnh lại băm/so sánh **toàn bộ một chuỗi dài**, hoặc cài đặt tạo nhiều chuỗi tạm, cần bổ sung chi phí ấy. Không thể áp dụng máy móc công thức “mỗi cạnh O(1)” của trie không nén.

### 16.2. Chèn/xóa có thể phải tách hoặc gộp cạnh

Trong trie nén, chèn khóa mới có thể phải **tách một nhãn cạnh** ở điểm phân kỳ. Xóa khóa có thể khiến các đoạn trở nên gộp được.

Những thao tác này ảnh hưởng số nút, số đoạn chuỗi lưu lại và chi phí sao chép nhãn. Radix trie không phải chỉ “trie thường nhưng ít con trỏ hơn”; nó có bất biến và chi phí cập nhật riêng.

### 16.3. Khi nào đáng cân nhắc nén đường?

Nếu các khóa chia sẻ tiền tố dài và phần lớn nút có `d=1`, nén có thể giảm overhead nút đáng kể. Nhưng nếu có nhiều cập nhật hoặc cần lưu chỉ mục ở mọi độ sâu ký tự, phải xét việc tách/gộp và các truy vấn trung gian.

**Bài này đặt cơ sở chi phí cho trie không nén**, còn trie nén là một mở rộng cần xác định lại đơn vị cạnh.

## 17. Mô hình bit và kích thước từ máy khi `σ` lớn

Trong mô hình RAM/word-RAM, ta thường giả định một ký hiệu được mã hóa và chỉ số con có thể xử lý bằng số lượng hằng số thao tác từ máy.

Gọi `w` là số bit một từ máy. Để biểu diễn một ký hiệu trong bảng chữ cái có `σ` giá trị khác nhau, cần ít nhất:

\[
b=\lceil\log_2 σ\rceil
\]

bit cho **mã ký hiệu**, nếu sử dụng một mã nhị phân cố định và `σ≥2`. Với `σ=1`, có thể cần 0 bit để phân biệt giá trị duy nhất trong mô hình toán học, nhưng chương trình thực tế vẫn cần quy ước biểu diễn và độ dài chuỗi.

### 17.1. Ký hiệu không vừa một từ

Nếu một cạnh mang một nhãn rất dài hoặc một đơn vị ký hiệu phức tạp cần nhiều từ máy, việc hash hoặc so sánh nhãn không còn tự động O(1). Khi đó:

\[
g_{\mathrm{find}}=g(d,σ,k,w)
\]

có thể phụ thuộc cả kích thước biểu diễn `k` bit của nhãn và từ máy `w`.

Trie code point Unicode thông thường thường làm việc với mã ký hiệu nhỏ đủ để xử lý một từ máy trong mô hình cơ bản, nhưng trie lưu **nhãn là cả đoạn chuỗi** cần phân tích riêng như mục 16.

### 17.2. Số ô và số bit không giống nhau

Một mảng con `σ` **tham chiếu nút** cần khoảng `σ` từ máy để chứa tham chiếu (cộng header); nó **không phải** một bitset `σ` bit.

Bitset có thể đánh dấu cạnh **có hay không**, nhưng để tìm **nút con tương ứng** vẫn cần cách ánh xạ chỉ số cạnh tới địa chỉ nút, như một mảng tham chiếu nén hoặc cấu trúc rank.

Do đó không thể thay toàn bộ mảng con bằng một bitset rồi kết luận tra nút con O(1) mà không xác định cách tìm địa chỉ con trong biểu diễn mới.

## 18. Các lỗi phân tích và thiết kế thường gặp

| Phát biểu sai hoặc chưa đủ | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Trie tìm O(1) vì lấy cạnh O(1).” | Phải đi qua tới `L` ký hiệu. | Tính O(L+1) nếu mỗi cạnh O(1). |
| “Trie tìm O(log n) vì là cây.” | Chiều sâu phụ thuộc **độ dài khóa**, không phải số khóa như BST cân bằng. | Dùng `L` và chi phí chọn cạnh. |
| “Chèn O(L) cho mọi alphabet.” | Mảng con mới có thể cần Θ(σ) thời gian khởi tạo. | Tính O(L+kσ) khi `σ` là biến. |
| “Mảng con dùng O(N) byte trong mọi trường hợp.” | Mỗi nút có `σ` ô. | Ghi Θ(Nσ) ô, đổi sang byte theo kích thước ô. |
| “Hash Map luôn O(1) xấu nhất.” | Va chạm và resize có thể đắt. | Nêu kỳ vọng/khấu hao và giả định băm. |
| “Mảng cạnh sắp chèn O(log d).” | Tìm vị trí nhanh nhưng phải dịch mục. | Tính O(d) cho chèn/xóa trong mảng. |
| “Cây có thứ tự luôn ít bộ nhớ hơn mảng.” | Cây cạnh cần nút, con trỏ, metadata. | Đo số byte và phân bố bậc. |
| “Mọi nút trie có nhiều nhất `σ` con nên số cạnh là `Nσ`.” | `Nσ` là số **ô khả dụng**, không phải cạnh thật. | Với cây, cạnh thật luôn `N-1`. |
| “Xây trie mất O(S) với `S` của tập cuối.” | Đầu vào có thể chứa rất nhiều khóa trùng. | Tính theo `S_{\mathrm{in}}` và `m` khi xây từ danh sách yêu cầu. |
| “Khóa rỗng làm thuật toán lỗi.” | Gốc biểu diễn đường rỗng hợp lệ. | Đặc tả terminal ở gốc và dùng `O(L+1)`. |
| “Autocomplete O(P).” | Còn duyệt cây con và xuất kết quả. | Tính `R`, `Z` và chi phí liệt kê nhánh. |
| “Ký tự tiếng Việt luôn có độ dài 1.” | Byte, code point và grapheme khác nhau. | Nêu rõ đơn vị, chuẩn hóa và mã hóa. |
| “Dùng bitset `σ` bit là có ngay toàn bộ con.” | Bitset chỉ biểu diễn có/không, không phải địa chỉ nút. | Bổ sung ánh xạ từ bit tới tham chiếu. |
| “Xóa một khóa là xóa cả đường của nó.” | Có thể mất khóa khác chung tiền tố. | Giữ bất biến terminal và chỉ dọn cây con có count=0. |

## 19. Bài tập vận dụng có gợi ý giải

### Bài 1 — Độ dài khóa và số khóa

Trie A có 100 khóa dài 1.000 ký hiệu. Trie B có 1.000.000 khóa dài 10 ký hiệu. Nếu mỗi cạnh chọn trong O(1), hãy nêu chặn trên số lần chọn cạnh cho một truy vấn tìm khóa đầy đủ ở mỗi trie.

**Gợi ý:** A tối đa 1.000 lần, B tối đa 10 lần. Không được kết luận A nhanh hơn chỉ vì ít khóa hơn.

### Bài 2 — Đếm số ô mảng và cạnh thật

Trie có `N=1.000` nút, mảng con `σ=26` ô tại mỗi nút. Số ô cấp phát và số cạnh thật là bao nhiêu?

**Gợi ý:** `1.000\cdot26=26.000` ô. Cây có `N-1=999` cạnh thật; số ô không chứa cạnh là `25.001`, nếu mọi nút đều giữ đủ mảng.

### Bài 3 — Khởi tạo mảng khi chèn

Khóa có `L=40` ký hiệu, chia sẻ tiền tố dài `r=30` với đường đã có trong trie. Có `σ=256`. Tính số nút mới và số ô con cần khởi tạo theo mô hình mảng đầy đủ.

**Gợi ý:** `k=L-r=10` nút. Cần khởi tạo `10\cdot256=2.560` ô con mới, ngoài các phép theo đường ký hiệu và metadata.

### Bài 4 — Chèn từ ngắn sau từ dài

Trie chỉ chứa `"anh"`. Chèn `"an"`. Hãy tính `L`, `r` và `k`.

**Gợi ý:** `L=2`, đường `an` đã tồn tại nên `r=2`, `k=0`. Vẫn thêm được khóa mới bằng cách đặt terminal tại nút `an`; số nút không tăng.

### Bài 5 — Xóa khóa có chung tiền tố

Trie chứa `{an,anh,ao}`. Xóa `an` rồi `anh`. Những nhánh nào còn?

**Gợi ý:** Xóa `an` chỉ bỏ terminal ở nút `an` vì còn `anh`. Xóa tiếp `anh` có thể dọn `h` rồi `n`, nhưng nút `a` và nhánh `o` phải giữ vì `ao` còn tồn tại.

### Bài 6 — Hash và ký hiệu dài

Nếu một cạnh trie không nén mang **một code point** nhưng cạnh trong trie nén mang đoạn chuỗi dài `k` ký hiệu, có được coi chi phí hash nhãn ở cả hai là O(1) không?

**Gợi ý:** Không mặc định. Một code point thường có biểu diễn hữu hạn trong mô hình từ máy; đoạn chuỗi dài có thể cần O(k) công việc để hash hoặc so sánh. Phải định nghĩa lại giá chọn cạnh.

### Bài 7 — Mảng cạnh đã sắp

Nút có nhãn cạnh `['a','d','m','z']`. Chèn `'b'` vào giữa. Tìm vị trí và dịch phần tử tốn bao nhiêu theo `d`?

**Gợi ý:** Tìm O(log(d+2)), nhưng phải dịch các mục `d,m,z`, nên chi phí cập nhật có thể O(d). Nhãn và tham chiếu nút con phải được dịch đồng bộ.

### Bài 8 — Tổng xây trie có khóa trùng

Một chương trình nhận 100.000 lần chèn cùng chuỗi `"abcdefghij"` dài 10, vào trie Set. Số khóa cuối là 1; `S=10`. Vậy tham số tổng chiều dài **đầu vào** là bao nhiêu và tại sao vẫn tốn thời gian?

**Gợi ý:** `S_{\mathrm{in}}=100.000\cdot10=1.000.000` ký hiệu. Dù chỉ có một khóa phân biệt, mọi lời gọi vẫn phải xác nhận đường và terminal; thời gian xây không thể suy chỉ từ `S=10`.

### Bài 9 — Byte mảng con theo `σ`

Với `N=100.000` nút, con trỏ rộng 8 byte, so sánh `σ=26` và `σ=256` chỉ theo byte của vùng ô con.

**Gợi ý:** 26: `100.000\cdot26\cdot8=20.800.000` byte. 256: `100.000\cdot256\cdot8=204.800.000` byte. Chưa tính header, bộ cấp phát và payload.

### Bài 10 — Autocomplete không chỉ theo `P`

Một tiền tố dài `P=3` nhưng có 10.000 khóa hoàn chỉnh bên dưới. Hỏi việc trả **toàn bộ** những khóa đó có thể chỉ mất O(3) không?

**Gợi ý:** Không. Phải duyệt cây con và tạo đầu ra; thời gian tối thiểu liên quan tới `Z` là tổng độ dài các chuỗi được xuất. Duyệt mảng còn có thể quét `σ` ô ở mỗi nút.

### Bài 11 — Phân bố truy vấn và thất bại sớm

Trie lưu các khóa bắt đầu bằng `a` và `b`. Một truy vấn bắt đầu bằng `z` nhưng dài 10.000 ký hiệu. Trong trie mảng con, cần thử bao nhiêu cạnh để biết thiếu khóa?

**Gợi ý:** Chỉ một lần thử cạnh `z` ở gốc nếu không có nhánh ấy. O(L) là chặn trên, không phải giá của mọi truy vấn.

### Bài 12 — Độ dài Unicode

Giải thích tại sao cùng chuỗi hiển thị `"bàn"` có thể có số bước trie khác nhau khi lưu bằng code point Python, byte UTF-8 hoặc biểu diễn có dấu kết hợp.

**Gợi ý:** Mỗi cách dùng đơn vị ký hiệu khác nhau. Dạng tổ hợp sẵn và dạng code point + dấu kết hợp có thể có độ dài Python khác; UTF-8 dùng số byte khác số code point. Chuẩn hóa phải nhất quán.

### Bài 13 — Tổng số cạnh và bậc ra

Trong một trie có `N=500` nút, tổng bậc ra `\sum_v d_v` bằng bao nhiêu? Kết quả có phụ thuộc `σ` không?

**Gợi ý:** Bằng 499 vì mọi nút trừ gốc có đúng một cạnh cha. Kết quả không phụ thuộc `σ`, miễn biểu diễn là một cây thực sự và không chia sẻ nút con bằng nhiều cha.

### Bài 14 — Tối ưu byte hay tối ưu độ trễ?

Một ứng dụng chủ yếu chỉ tra khóa ngắn nhưng RAM hạn chế, các nút có `d=1` và `σ=1.000`. Nên cân nhắc các phương án nào?

**Gợi ý:** Mảng cố định 1.000 ô trên mỗi nút có thể tốn RAM rất lớn. Hash Map, mảng cạnh sắp hoặc trie nén đường đáng cân nhắc, nhưng cần đo chi phí metadata, thời gian cập nhật và cache. Không chọn chỉ dựa vào O(L).

### Bài 15 — Kỳ vọng số bước chọn cạnh

Mọi truy vấn dài `L=4`. Xác suất còn đường sau các tiền tố dài 0, 1, 2, 3 lần lượt là `1`; `0,6`; `0,3`; `0,1` (dùng dấu phẩy thập phân). Tính số lần thử cạnh kỳ vọng.

**Gợi ý:** Theo công thức `\sum_{j=0}^{L-1}q_j`: `1+0,6+0,3+0,1=2` lần thử. Bài toán giả định những xác suất này phù hợp với một phân bố truy vấn, không phải giả định mọi truy vấn đều đến nút terminal.

### Bài 16 — Chi phí bitset không tự là chi phí trie

Một bạn đề nghị thay mảng `σ` con trỏ bằng bitset `σ` bit và nói rằng như vậy đã lưu đủ mọi nút con. Sai ở đâu?

**Gợi ý:** Bitset chỉ biết cạnh nào có hoặc không; nó không lưu địa chỉ nút con. Cần thêm mảng con nén và cơ chế ánh xạ vị trí bit sang vị trí nút, ví dụ dùng rank, rồi phân tích chi phí chọn cạnh tương ứng.

## 20. Checklist phân tích trước khi chọn biểu diễn trie

Dùng mẫu sau để không bỏ sót tham số:

```text
1. Đặc tả khóa:
   - Trie lưu Set hay Map?
   - Khóa trùng xử lý thế nào? Có cho phép chuỗi rỗng không?
   - Ký hiệu là byte, code point, bit hay nhãn chuỗi nén?
   - Chuẩn hóa Unicode/casefold và quy tắc tiền tố là gì?

2. Quy mô:
   - n: số khóa phân biệt?
   - S: tổng độ dài khóa phân biệt?
   - S_in: tổng độ dài mọi khóa được đưa vào để xây?
   - L, P, L_max: chiều dài khóa và tiền tố?
   - sigma: bảng chữ cái có bao nhiêu ký hiệu?

3. Hình dạng:
   - N: số nút; số cạnh thật N-1?
   - Phân bố d_v: bao nhiêu nút 0, 1, 2, nhiều con?
   - Nút mới k và nút bị dọn r trong cập nhật?

4. Chi phí trên một nút:
   - Mảng: O(1) tra, Theta(sigma) ô và tạo mảng?
   - Hash: O(1) kỳ vọng, overhead và resize?
   - Mảng cạnh sắp: O(log(d+2)) tìm, O(d) cập nhật?
   - Cây cạnh cân bằng: O(log(d+2)) tìm/cập nhật?

5. Tổng đường thao tác:
   - Tìm: cộng g_find(d_i, sigma) dọc đường.
   - Chèn: thêm các nút mới và cập nhật count.
   - Xóa: chỉ dọn nhánh khi subtree_count = 0.
   - Thời gian và bộ nhớ phụ đã tính độc lập?

6. Truy vấn đầu ra:
   - Chỉ kiểm tra prefix hay phải liệt kê khóa?
   - Có yêu cầu thứ tự? Có phải sắp nhánh?
   - Số nút thăm R, tổng ký hiệu đầu ra Z?

7. Đo đạc:
   - Cùng bộ khóa và cùng vết thao tác cho các phương án?
   - Đo xây, tìm có/thất bại, thêm/xóa, autocomplete?
   - Số lần tra cạnh, số nút, byte được giữ và byte đỉnh?
   - Đã kiểm thử terminal, khóa rỗng và tiền tố chung?

8. Quyết định:
   - Giới hạn RAM, độ trễ mỗi lời gọi và yêu cầu sắp thứ tự?
   - Tham số nào thay đổi sẽ khiến phải chọn lại biểu diễn?
```

**Kết luận:** Độ phức tạp của trie không chỉ là “O(L)”. Kết luận ấy là **hệ quả của mô hình chọn cạnh** khi mỗi ký hiệu có chi phí O(1) và nút được cấp phát theo cách phù hợp. Với mảng con, `σ` quyết định số ô và giá tạo nút; với Hash Map, kỳ vọng của phép băm và overhead bảng là yếu tố quan trọng; với tập cạnh có thứ tự, bậc ra `d` quyết định số so sánh và số mục phải dịch hoặc cân bằng. Số nút `N` lại phụ thuộc tổng chiều dài và mức chia sẻ tiền tố, còn autocomplete phụ thuộc lượng kết quả phải tạo. Khi nêu đủ `L,σ,d,N,S`, quy tắc Unicode và workload thực tế, ta có thể chọn cấu trúc chỉ mục chuỗi phù hợp mà vẫn bảo toàn đúng bất biến và hành vi công khai.
