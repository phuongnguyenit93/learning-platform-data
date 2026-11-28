# Lưu nhánh bằng mảng, bảng băm hoặc tập cạnh có thứ tự

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Lưu nhánh bằng mảng, bảng băm hoặc tập cạnh có thứ tự

Trong một trie, mỗi nút phải trả lời câu hỏi rất cụ thể: **“Với ký hiệu tiếp theo `c`, có cạnh nào đi đến nút con mang nhãn `c` hay không?”** Câu hỏi này xuất hiện trong mọi lần tìm, chèn và xóa khóa. Cách cài đặt các cạnh đi ra khỏi nút có thể quyết định lượng bộ nhớ và thời gian thực tế của toàn bộ cấu trúc.

Ta có thể lưu các nhánh bằng **mảng có chỉ số cố định**, **bảng băm** hoặc **tập cạnh được duy trì theo thứ tự**. Ba cách đều có thể biểu diễn chính xác cùng một trie về mặt logic, nhưng khác nhau ở giá tra cạnh, giá tạo/xóa cạnh, khả năng duyệt theo thứ tự và số byte bị giữ ở những nút có rất ít con.

Bài học thuộc chương **Trie và chỉ mục chuỗi** trong mô-đun **Cấu trúc dữ liệu** (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Chúng ta sẽ tập trung vào bất biến biểu diễn, phân tích thao tác và độ phức tạp thời gian–bộ nhớ, đồng thời liên hệ với mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị để hiểu cách chọn cấu trúc phù hợp với từng bài toán.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao tập nhánh đi ra khỏi một nút trie là một **ánh xạ từ ký hiệu sang nút con**, không đơn thuần là danh sách các nút.
2. Phân biệt ba cách lưu nhánh: **mảng cố định**, **Hash Map** và **tập cạnh có thứ tự**.
3. Tính độ phức tạp chọn, thêm, xóa và liệt kê cạnh theo bậc ra `d` của nút và kích thước bảng chữ cái `σ`.
4. Phân biệt **danh sách cặp cạnh đã sắp xếp** với **cây tìm kiếm cân bằng** lưu cạnh có thứ tự.
5. Phân tích overhead ở nút thưa và nút nhiều nhánh, cả bộ nhớ giữ lại lẫn chi phí cấp phát.
6. Cài đặt một `TrieSet` dùng ba kiểu bảng con có thể thay thế nhưng giữ nguyên hợp đồng tìm/chèn/xóa.
7. Hiểu vì sao autocomplete có thứ tự có thể đắt hơn với Hash Map nếu mỗi nút phải sắp nhãn con.
8. Nhận biết các ràng buộc về bảng ký hiệu cố định, Unicode, tiền tố và tính đúng khi xóa nhánh.
9. Đề xuất tiêu chí chọn biểu diễn theo số nhánh trung bình, tần suất cập nhật, giới hạn RAM và nhu cầu duyệt thứ tự.

## 2. Tập cạnh tại nút trie thực sự biểu diễn điều gì?

Trong trie **không nén**, mỗi cạnh mang một ký hiệu. Với một nút `v`, tập cạnh đi ra có dạng:

\[
children_v:\ c\longmapsto \text{nút con nhận được khi đi qua }c.
\]

Đây là một **ánh xạ từng phần**: chỉ những ký hiệu có cạnh thật mới có giá trị nút con; các ký hiệu khác được coi là không có cạnh.

Ví dụ trie lưu:

```text
S = {"an", "anh", "ao", "ba", "ban"}
```

Sơ đồ:

```text
                    root
                   /    \
                  a      b
                /   \     \
               n*    o*    a*
               |            |
               h*           n*

* = nút đánh dấu kết thúc một khóa
```

Tập cạnh ở một vài nút:

| Nút biểu diễn tiền tố | Các cặp (ký hiệu → nút con) | Bậc ra `d` |
| --- | --- | ---: |
| `""` (gốc) | `a→node_a`, `b→node_b` | 2 |
| `"a"` | `n→node_an`, `o→node_ao` | 2 |
| `"an"` | `h→node_anh` | 1 |
| `"ao"` | Không có | 0 |
| `"b"` | `a→node_ba` | 1 |
| `"ba"` | `n→node_ban` | 1 |
| `"anh"`, `"ban"` | Không có | 0 |

### 2.1. Bất biến cốt lõi

Với mọi nút `v` và ký hiệu `c`, **có tối đa một nút con ứng với `c`**. Nếu muốn giữ khóa `an` và `anh`, cả hai dùng chung cạnh `a` ở gốc, rồi cạnh `n` ở nút `a`.

Nếu một nút được phép giữ hai cạnh đều mang nhãn `n`, thao tác tìm `an...` sẽ trở nên mơ hồ: chương trình không biết nên đi theo nhánh nào. Các biểu diễn cần bảo đảm **duy nhất khóa cạnh**, giống như một Map.

### 2.2. Dấu kết thúc khóa là trường độc lập

Một nút vẫn cần cờ `terminal` hoặc dữ liệu tương đương, cho biết **tiền tố biểu diễn bởi nút** có phải khóa hoàn chỉnh không.

Tập cạnh của nút không thay thế được cờ ấy:

- `"an"` là khóa hoàn chỉnh **và** có con `h`.
- `"a"` chỉ là tiền tố; nó có hai con nhưng không phải khóa hoàn chỉnh.
- Nút `"anh"` là lá và là khóa hoàn chỉnh trong ví dụ này.

Bài học đang lựa chọn cách **lưu cạnh của nút**; nó không thay đổi khái niệm khóa hoàn chỉnh và bất biến terminal của trie.

## 3. Định nghĩa các tham số chi phí

Gọi:

- `n`: số khóa phân biệt đang lưu.
- `L`: số ký hiệu của khóa đang tìm/chèn/xóa.
- `P`: số ký hiệu của tiền tố cần tìm.
- `σ` (*sigma*): số ký hiệu có thể có trong bảng chữ cái của trie.
- `d_v`: số cạnh con **thật** tại nút `v`, với `0≤d_v≤σ`.
- `N`: tổng số nút trie, tính cả gốc.
- `E_c=N-1`: tổng số cạnh con trong cây.
- `S`: tổng số ký hiệu của các khóa phân biệt đã lưu.

Với trie không nén:

\[
N\le S+1,\qquad \sum_v d_v=N-1.
\]

Điều thứ hai đặc biệt quan trọng: tổng số **cạnh thật** của toàn cây luôn là `N-1`. Nhưng nếu mỗi nút dành sẵn `σ` ô, tổng số **ô đã cấp phát** lại có thể lên đến `Nσ`, kể cả khi chỉ có `N-1` cạnh thật.

### 3.1. Bậc ra của từng nút quan trọng hơn bậc trung bình đơn lẻ

Một trie có thể gồm rất nhiều nút với `d=1` và một vài nút có `d` lớn. Ví dụ, tập khóa dùng chung tiền tố dài sẽ tạo một chuỗi nhiều nút một con rồi mới phân nhánh ở phía cuối.

Vì vậy, khi so sánh:

- **Mảng cố định**: mỗi nút trả phí theo `σ`, ít phụ thuộc `d`.
- **Bảng băm**: vùng cạnh thường phụ thuộc `d` nhưng có overhead bảng và sức chứa dự phòng.
- **Tập cạnh có thứ tự**: vùng cạnh thường phụ thuộc `d`; thời gian phụ thuộc cách duy trì thứ tự.

Không nên chỉ biết `N` rồi kết luận ngay phương án nào nhanh hoặc tiết kiệm hơn.

### 3.2. Hai đơn vị cần tách biệt

Trong phần phân tích lý thuyết, “O(1) cho mỗi cạnh” giả định xử lý một ký hiệu và tham chiếu nút là phép toán có giá hằng số. Trong triển khai thực tế, một ký hiệu có thể là byte, code point hoặc cụm tự vị; một đối tượng Python có metadata và bộ cấp phát riêng.

Do đó, ta sẽ tách:

1. **Số phép chọn/cập nhật cạnh**.
2. **Bộ nhớ theo số ô và cạnh**.
3. **Byte thực tế và độ trễ thực nghiệm**, vốn phụ thuộc runtime và biểu diễn.

## 4. Phương án A: mảng con có chỉ số cố định

Giả sử chỉ chấp nhận 26 ký tự `a` đến `z`. Ta có thể lưu ở mỗi nút một mảng `children` dài 26:

```text
index:      0     1     2     ...    13    14    ...    25
symbol:     a     b     c            n     o            z
children:  node   None  None         node  node          None
```

Phép ánh xạ được định nghĩa bằng:

\[
index(c)=code(c)-code(\text{'a'}).
\]

Với ký tự hợp lệ `a-z`, chỉ số thuộc `[0,25]`. `None` biểu thị nhánh không tồn tại.

### 4.1. Tra một cạnh

Để tìm con ứng với `c`:

1. Kiểm tra `c` thuộc bảng chữ cái được hỗ trợ.
2. Tính chỉ số `index(c)`.
3. Đọc `children[index(c)]`.

Trong mô hình RAM, bước chọn con là **O(1) trường hợp xấu nhất** khi kiểm tra và tính chỉ số có giá hằng số.

### 4.2. Thêm và xóa một cạnh

- **Thêm cạnh mới**: gán tham chiếu nút con vào ô đang `None`, O(1) sau khi nút con đã được tạo.
- **Xóa cạnh**: gán lại ô thành `None`, O(1) tại nút cha.
- **Duyệt theo nhãn tăng dần**: quét các ô từ 0 đến 25, bỏ qua những ô `None`.

Nếu `σ` là biến, mỗi lượt duyệt tất cả vị trí mất O(σ), **dù nút chỉ có một con**.

### 4.3. Ưu điểm

- Tra nhánh đơn giản, trực tiếp, không phải hash hoặc tìm nhị phân.
- Có chặn O(1) cho truy cập một nhánh dưới mô hình chỉ số từ máy.
- Duyệt theo thứ tự bảng chữ cái được ánh xạ sẵn, không cần sắp.
- Các ô tham chiếu nằm liên tiếp, thường có lợi thế tính cục bộ bộ nhớ.

### 4.4. Nhược điểm

- **Nút lá vẫn có cả mảng `σ` ô**, dù không dùng cạnh nào.
- Nếu bảng ký hiệu lớn, cấp mảng cho mỗi nút có thể rất đắt.
- Muốn dùng Unicode nói chung, phải có chiến lược ánh xạ ký hiệu vào chỉ số; không được giả định mọi code point có thể lưu bằng mảng con cỡ 26.
- Khi tạo nút mới, khởi tạo mảng `σ` ô tốn Θ(σ) thời gian và bộ nhớ theo mô hình biến `σ`.

Nếu `σ=26` được xem là **hằng số cố định**, các khoản Θ(σ) được viết thành O(1). Nhưng đối với bảng ký hiệu rộng hoặc thay đổi theo dữ liệu, không được tự bỏ `σ`.

## 5. Phương án B: bảng băm ánh xạ ký hiệu sang con

Thay vì cấp sẵn `σ` ô, mỗi nút giữ một Hash Map chỉ chứa những nhánh đang có:

```text
children = {
    'n': node_an,
    'o': node_ao
}
```

Với nút `"a"` có hai con, bảng chỉ lưu hai mục ký hiệu → nút. Không cần một ô logic cho từng ký tự còn lại của bảng chữ cái.

### 5.1. Tra, thêm và xóa

- `get(c)`: tính hash của ký hiệu `c`, tìm bucket/ô tương ứng.
- `put(c, child)`: thêm ánh xạ khi `c` chưa có.
- `delete(c)`: loại ánh xạ khi nhánh không còn cần thiết.
- `items()`: duyệt các cặp đang lưu.

Với ký hiệu có chi phí hash/so sánh O(1), hệ số tải được duy trì phù hợp và phân bố băm thích hợp, tra và cập nhật một cạnh có chi phí **O(1) kỳ vọng**. Mở rộng bảng có thể làm một lần chèn đắt hơn; phần resize cần phân tích khấu hao riêng.

### 5.2. Khác biệt giữa số nhánh và số lượt truy vấn

Một nút có `d=2` vẫn chỉ có hai mục trong bảng, dù được tra một triệu lần. Khóa “nóng” được truy cập thường xuyên không tự làm số nhánh hay số va chạm tăng.

Độ dài khóa toàn bộ `L` cũng khác với kích thước ký hiệu cạnh: khi trie lưu **một code point trên mỗi cạnh**, hash một nhãn cạnh có kích thước giới hạn theo một ký hiệu. Nếu trie **nén đường** và dùng chuỗi dài làm nhãn cạnh, chi phí hash/so sánh nhãn có thể tăng theo chiều dài đoạn chuỗi.

### 5.3. Duyệt nhánh theo thứ tự: không miễn phí

Một Hash Map không tự cam kết các nhãn được duyệt theo thứ tự từ điển. Trong Python hiện đại, `dict` giữ **thứ tự thêm vào**, nhưng thứ tự thêm vào **không phải** thứ tự tăng của ký tự.

Ví dụ, nếu thêm `'z'` trước `'a'`, duyệt `dict` có thể thấy `z,a`. Nếu API của trie cam kết autocomplete theo thứ tự ký tự, ta có thể:

```python
for ch in sorted(children):
    child = children[ch]
    # Xử lý nhánh theo thứ tự ch tăng dần.
```

Với `d` nhánh, sắp nhãn ở một nút có chặn O(d log(d+1)) theo mô hình so sánh ký hiệu O(1). Làm vậy ở **mọi nút đã thăm** sẽ cộng dồn chi phí sắp vào cả lần duyệt cây con.

### 5.4. Đánh đổi bộ nhớ

Bảng băm thưa tránh một vùng `σ` ô tại từng nút, nhưng bản thân dictionary có:

- Header đối tượng, bảng lưu mục và thông tin tải.
- Dung lượng dự phòng để kiểm soát va chạm.
- Có thể phải cấp phát lại/tái băm khi số cạnh tăng.
- Overhead ở **mỗi dictionary rỗng**, nếu tạo dictionary riêng cho cả nút lá.

“Chỉ lưu `d` cạnh” không có nghĩa đúng `d` con trỏ và **không có** metadata. Byte thật phải đo theo runtime và biểu diễn cụ thể.

## 6. Phương án C: tập cạnh có thứ tự

Thay vì dùng hash, ta có thể giữ những cặp `(ký hiệu,nút_con)` **theo thứ tự tăng của ký hiệu**.

Ví dụ với nút `"a"`:

```text
[('n', node_an), ('o', node_ao)]
```

Cách lưu này trả lời cả hai nhu cầu:

- Tìm đúng cạnh có nhãn `c`.
- Duyệt các cạnh theo thứ tự từ điển **không cần sắp lại mỗi lần**.

Tuy nhiên, khái niệm **“tập cạnh có thứ tự”** chưa nói rõ thuật toán cài đặt. Có ít nhất hai lựa chọn có chi phí khác nhau.

### 6.1. Danh sách hoặc mảng các cạnh đã sắp

Lưu các nhãn trong một mảng đã sắp và các nút con ở vị trí tương ứng:

```text
labels = ['a', 'm', 'z']
nodes  = [node_a, node_m, node_z]
```

Để tìm `c`, dùng tìm kiếm nhị phân xác định vị trí. Với `d` cạnh:

- **Tra cứu:** O(log(d+1)) phép so sánh nhãn.
- **Thêm cạnh mới:** tìm vị trí O(log(d+1)), rồi có thể dịch O(d) phần tử để giữ thứ tự.
- **Xóa cạnh:** tìm O(log(d+1)), rồi dịch O(d) phần tử.
- **Duyệt theo thứ tự:** Θ(d) khi trả tất cả `d` cạnh.

Ta có thể dùng hai mảng song song như ví dụ, hoặc một mảng các cặp. Hai cách đều phải giữ **sự ghép đúng nhãn và nút con** khi chèn/xóa.

### 6.2. Cây tìm kiếm cân bằng lưu cạnh

Thay cho mảng sắp, mỗi nút trie có thể giữ một **cây tìm kiếm cân bằng** (ví dụ AVL hoặc đỏ-đen) với khóa là nhãn cạnh:

- Tìm nhãn: O(log(d+1)) trường hợp xấu nhất.
- Thêm cạnh: O(log(d+1)) trường hợp xấu nhất.
- Xóa cạnh: O(log(d+1)) trường hợp xấu nhất.
- Duyệt theo thứ tự: Θ(d) cho các cạnh được xuất, theo một thuật toán inorder thích hợp.

Đổi lại, mỗi cạnh trong cây cân bằng có thể mang liên kết trái/phải, màu hoặc chiều cao; chi phí bộ nhớ và cấp phát thường cao hơn một mảng cặp đơn giản.

**Không được gộp hai cách vào một nhận định “tập cạnh có thứ tự chèn O(log d)”**: mảng sắp cần dịch phần tử, có thể O(d); cây cân bằng mới có chặn O(log d) cho cập nhật theo nhãn.

### 6.3. Python `set` không phải tập có thứ tự

Tên “tập cạnh” không có nghĩa dùng ngay `set` của Python. `set` thường dựa trên hash và **không cam kết duyệt tăng dần**. `dict` cũng không cam kết thứ tự từ điển, dù giữ thứ tự thêm vào.

Để dạy rõ sự khác biệt, phần cài đặt dưới sẽ dùng một **danh sách nhãn được sắp** với `bisect_left`, chứ không giả vờ rằng `set` mặc định là một cây tìm kiếm cân bằng.

## 7. Bảng độ phức tạp của thao tác trên một nút

Giả sử `d` là số nhánh thật tại nút, `σ` là số ký hiệu trong bảng chữ cái. Thao tác trên nhãn ký hiệu đơn có chi phí so sánh O(1).

| Biểu diễn `children` | Tra một cạnh | Thêm cạnh chưa có | Xóa cạnh đã có | Liệt kê theo nhãn tăng |
| --- | --- | --- | --- | --- |
| **Mảng cố định `σ` ô** | O(1) xấu nhất | O(1) để gán ô, **cộng Θ(σ) khi tạo nút mới** | O(1) | O(σ) để quét các ô |
| **Hash Map** | O(1) kỳ vọng | O(1) kỳ vọng; resize có thể đắt | O(1) kỳ vọng | O(d log(d+1)) nếu sắp nhãn mỗi lần |
| **Mảng cặp đã sắp** | O(log(d+1)) | O(d+1) do tìm vị trí và dịch | O(d+1) do tìm và dịch | Θ(d) |
| **Cây cân bằng theo nhãn** | O(log(d+1)) xấu nhất | O(log(d+1)) xấu nhất | O(log(d+1)) xấu nhất | Θ(d) |

Để dễ so sánh ở `d=0`, một số chặn viết `log(d+1)` nên có thêm chi phí thao tác hằng số. Khi cần công thức đúng cả lúc rỗng, có thể dùng `O(1+\log(d+1))` hoặc `O(\log(d+2))`.

### 7.1. Đừng nhầm cập nhật một cạnh với chèn một khóa

Để chèn một khóa có `L` ký hiệu, trie phải đi theo **nhiều nút**. Nếu một cạnh mới được tạo, còn phải cấp phát một nút trie mới và bộ chứa cạnh của nút ấy.

Vì vậy, chặn “`put` một nhánh O(1)” **không tự động** làm `insert(word)` O(1). Nó chỉ mô tả một bước của thuật toán trên đường khóa.

### 7.2. Khi `σ=26` là hằng số

Với tập ký hiệu nhỏ cố định, `d≤26`, nên cả `O(d)` và `O(log(d+2))` đều được xem là O(1) theo `L`. Khi ấy tìm/chèn/xóa khóa có thể cùng bậc O(L), nhưng **hệ số thời gian, bộ nhớ và chi phí duyệt theo thứ tự vẫn khác nhau**.

### 7.3. Khi bảng ký hiệu lớn hoặc biến động

Nếu `σ` tăng theo bài toán, ta phải giữ tham số ấy:

- Mảng có thể trả giá `σ` ô mỗi nút và `σ` bước khi quét nhánh.
- Mảng cạnh sắp có thể dịch `d` phần tử ở một nút.
- Cây cân bằng con cần O(log(d+2)) bước cho một phép chọn/cập nhật cạnh.
- Hash vẫn cần giả định chi phí băm và hệ số tải.

Một trie có nhiều nhánh ở gốc nhưng rất ít nhánh ở nút sâu sẽ có lợi thế/nhược điểm khác trie hầu hết là các chuỗi một con.

## 8. Ước tính bộ nhớ: số cạnh thật khác số ô được cấp

Với trie mẫu `{"an","anh","ao","ba","ban"}`:

- Số nút `N=8` (gồm gốc).
- Tổng số cạnh thật `N-1=7`.
- Phân bố bậc ra: gốc có 2 con; nút `a` có 2; các nút `an`, `b`, `ba` có 1; ba nút còn lại có 0 con.

Tính chính xác theo sơ đồ:

| Nút | `d` |
| --- | ---: |
| `root` | 2 |
| `a` | 2 |
| `an` | 1 |
| `anh` | 0 |
| `ao` | 0 |
| `b` | 1 |
| `ba` | 1 |
| `ban` | 0 |
| **Tổng** | **7** |

### 8.1. Nếu mọi nút có mảng 26 ô

Số ô tham chiếu đã cấp phát:

\[
Nσ=8\cdot26=208\text{ ô}.
\]

Trong số đó chỉ **7 ô** trỏ tới nút con. Phần còn lại là `201` ô trống.

Nếu **giả định** mỗi ô tham chiếu rộng 8 byte, riêng vùng ô con cần:

\[
208\cdot8=1664\text{ byte}.
\]

Con số này **chưa bao gồm** các đối tượng nút, header mảng, dấu terminal, bộ đếm, dữ liệu từ hoặc metadata của bộ cấp phát. Nó chỉ minh họa vì sao nút thưa làm mảng cố định tốn nhiều ô.

### 8.2. Nếu lưu cạnh thưa

Hash Map hoặc mảng cặp sắp chỉ cần lưu các **7 ánh xạ cạnh thật**, cộng overhead riêng ở mỗi nút và sức chứa dự phòng của vùng chứa.

Không thể suy ra ngay “chỉ cần `7×8=56` byte” vì một ánh xạ thường còn cần nhãn, vị trí hoặc metadata, và Python `dict`/`list` có header. Khi nút rỗng vẫn tạo dictionary hoặc hai danh sách rỗng, overhead cố định đó có thể đáng kể.

### 8.3. Mô hình byte đơn giản

Gọi `p` là byte một tham chiếu. Đặt `H_n` là overhead chung của nút, `H_h` là overhead cố định của một bảng băm rỗng và `e_h` là chi phí trung bình mỗi mục cạnh, trong một **mô hình giả định**.

- Mảng cố định: `M_{\mathrm{dense}}\approx H_n+σp`.
- Hash: `M_{\mathrm{hash}}\approx H_n+H_h+d\,e_h`.
- Mảng cạnh sắp: `M_{\mathrm{sorted}}\approx H_n+H_s+d\,e_s`, với `H_s` là header vùng chứa và `e_s` là phần tử cạnh.

Nếu bỏ các phần chung, một điều kiện hòa vốn giả định là:

\[
σp < H_h+d\,e_h.
\]

Đừng lấy bất đẳng thức này làm công thức kích thước thật của Python: hash table thường cấp phát theo mức sức chứa rời rạc và có metadata, còn mảng cũng có header/căn chỉnh. Nó là **khung tư duy để đo và so sánh**, không phải định luật byte.

### 8.4. Byte đỉnh khi nút tăng số nhánh

Một Hash Map có thể cấp bảng lớn hơn rồi tái băm các mục cạnh. Mảng cạnh sắp của Python có thể mở rộng vùng đệm và dịch phần tử khi thêm nhãn. Một cấu trúc ordered tree cấp phát từng nút cạnh nhỏ. Các sự kiện này không nhất thiết xảy ra thường xuyên, nhưng có thể ảnh hưởng **bộ nhớ đỉnh** và độ trễ cập nhật.

## 9. Cài đặt giao diện chung để thay đổi biểu diễn

Ta sẽ viết ba loại bảng con có cùng bốn thao tác:

```text
get(char)            -> nút con hoặc None
put(char, child)     -> thêm cạnh chưa tồn tại
delete(char)         -> xóa cạnh đang tồn tại
items_sorted()       -> duyệt (char, child) theo nhãn tăng
```

Nhờ giao diện giống nhau, thuật toán trie sẽ chỉ phụ thuộc **hành vi chọn và cập nhật cạnh**, không phụ thuộc `children` là mảng, hash hay danh sách sắp.

Để so sánh công bằng với cùng hợp đồng, cả ba bản demo **chỉ nhận các khóa gồm chữ thường ASCII `a-z`**, ngoài khóa rỗng. Đây là giới hạn có chủ ý của ví dụ, **không phải giới hạn bắt buộc của trie**. Mục 15 sẽ bàn về Unicode.

### 9.1. Biểu diễn bằng mảng cố định

```python
class ArrayChildren:
    """Mảng con 26 ô cho bảng ký hiệu 'a'..'z'."""
    __slots__ = ("slots",)

    def __init__(self):
        self.slots = [None] * 26

    @staticmethod
    def _index(ch):
        if len(ch) != 1 or not ("a" <= ch <= "z"):
            raise ValueError("ký hiệu phải nằm trong a-z")
        return ord(ch) - ord("a")

    def get(self, ch):
        return self.slots[self._index(ch)]

    def put(self, ch, child):
        index = self._index(ch)
        if self.slots[index] is not None:
            raise ValueError("nhánh đã tồn tại")
        self.slots[index] = child

    def delete(self, ch):
        index = self._index(ch)
        if self.slots[index] is None:
            raise KeyError(ch)
        self.slots[index] = None

    def items_sorted(self):
        for index, child in enumerate(self.slots):
            if child is not None:
                yield chr(ord("a") + index), child
```

**Đặc điểm:** `get`, `put` và `delete` chọn ô trực tiếp. `items_sorted` quét cả 26 ô ở từng nút, bỏ qua ô rỗng. Với `σ` biến động, việc tạo `slots` có giá Θ(σ).

### 9.2. Biểu diễn bằng Hash Map

```python
class HashChildren:
    """Chỉ lưu nhánh thật bằng dict."""
    __slots__ = ("links",)

    def __init__(self):
        self.links = {}

    def get(self, ch):
        return self.links.get(ch)

    def put(self, ch, child):
        if ch in self.links:
            raise ValueError("nhánh đã tồn tại")
        self.links[ch] = child

    def delete(self, ch):
        del self.links[ch]

    def items_sorted(self):
        for ch in sorted(self.links):
            yield ch, self.links[ch]
```

**Đặc điểm:** đường tìm chỉ cần `get`, thường O(1) kỳ vọng trên một nhánh. Khi cần xuất theo thứ tự, `items_sorted` phải sắp các nhãn đang có. Nếu không cần thứ tự, có thể định nghĩa thêm `items_unordered` trả iterator của `links.items()`.

### 9.3. Biểu diễn bằng mảng nhãn có thứ tự

```python
from bisect import bisect_left


class SortedChildren:
    """Hai mảng song song, nhãn luôn tăng dần và duy nhất."""
    __slots__ = ("labels", "nodes")

    def __init__(self):
        self.labels = []
        self.nodes = []

    def _position(self, ch):
        return bisect_left(self.labels, ch)

    def get(self, ch):
        index = self._position(ch)
        if index < len(self.labels) and self.labels[index] == ch:
            return self.nodes[index]
        return None

    def put(self, ch, child):
        index = self._position(ch)
        if index < len(self.labels) and self.labels[index] == ch:
            raise ValueError("nhánh đã tồn tại")
        self.labels.insert(index, ch)
        self.nodes.insert(index, child)

    def delete(self, ch):
        index = self._position(ch)
        if index == len(self.labels) or self.labels[index] != ch:
            raise KeyError(ch)
        del self.labels[index]
        del self.nodes[index]

    def items_sorted(self):
        yield from zip(self.labels, self.nodes)
```

**Đặc điểm:** `bisect_left` định vị vị trí O(log(d+1)) phép so sánh nhãn, nhưng `list.insert` hoặc `del` có thể phải dịch O(d) mục. Đây **không phải** cài đặt ordered tree cân bằng.

### 9.4. Một quy ước nội bộ quan trọng

Trong ba kiểu bảng con, `None` nghĩa là **không có nút con**; giá trị của một cạnh đang tồn tại phải là một đối tượng nút, không phải `None`. Nhờ đó `get` có thể trả `None` khi thiếu cạnh mà không mơ hồ.

Một Map ứng dụng có thể lưu giá trị `None` làm **payload của khóa**; điều đó không liên quan tới quy ước `None` của con trỏ cạnh. Nên tách “không có cạnh” khỏi “khóa có dữ liệu None” trong thiết kế.

## 10. Một TrieSet dùng được cả ba kiểu bảng con

Đoạn mã sau dùng **một thuật toán trie chung**. Khi tạo `TrieSet(ArrayChildren)`, `TrieSet(HashChildren)` hoặc `TrieSet(SortedChildren)`, mỗi nút tự tạo vùng chứa cạnh theo kiểu được chọn.

### 10.1. Nút trie

```python
class TrieNode:
    __slots__ = ("children", "terminal", "subtree_count")

    def __init__(self, children_type):
        self.children = children_type()
        self.terminal = False
        self.subtree_count = 0
```

`terminal` đánh dấu khóa hoàn chỉnh. `subtree_count` là số khóa hoàn chỉnh trong toàn bộ cây con, tính cả khóa kết thúc ngay tại nút. Hai trường này **không phụ thuộc** cách lưu cạnh.

### 10.2. Lớp TrieSet

```python
class TrieSet:
    def __init__(self, children_type):
        self._children_type = children_type
        self._root = TrieNode(children_type)
        self._size = 0

    @staticmethod
    def _validate(text):
        if not isinstance(text, str):
            raise TypeError("khóa/tiền tố phải là str")
        if any(not ("a" <= ch <= "z") for ch in text):
            raise ValueError("ví dụ chỉ hỗ trợ chữ thường ASCII a-z")

    def __len__(self):
        return self._size

    def _walk(self, text):
        node = self._root
        for ch in text:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def contains(self, word):
        self._validate(word)
        node = self._walk(word)
        return node is not None and node.terminal

    def starts_with(self, prefix):
        """Có đường tiền tố; đường rỗng luôn tồn tại tại root."""
        self._validate(prefix)
        return self._walk(prefix) is not None

    def count_prefix(self, prefix):
        self._validate(prefix)
        node = self._walk(prefix)
        return 0 if node is None else node.subtree_count

    def insert(self, word):
        self._validate(word)

        node = self._root
        path = [node]

        for ch in word:
            child = node.children.get(ch)
            if child is None:
                child = TrieNode(self._children_type)
                node.children.put(ch, child)

            node = child
            path.append(node)

        if node.terminal:
            return False

        node.terminal = True
        for item in path:
            item.subtree_count += 1
        self._size += 1
        return True

    def delete(self, word):
        self._validate(word)

        node = self._root
        path = [node]

        for ch in word:
            node = node.children.get(ch)
            if node is None:
                return False
            path.append(node)

        if not node.terminal:
            return False

        node.terminal = False
        for item in path:
            item.subtree_count -= 1

        # Cắt các cạnh có cây con không còn khóa hoàn chỉnh.
        for index in range(len(word) - 1, -1, -1):
            parent = path[index]
            child = path[index + 1]

            if child.subtree_count > 0:
                break
            parent.children.delete(word[index])

        self._size -= 1
        return True

    def words_with_prefix(self, prefix="", limit=None):
        self._validate(prefix)
        if limit is not None:
            if not isinstance(limit, int) or limit < 0:
                raise ValueError("limit phải là số nguyên không âm")
            if limit == 0:
                return []

        start = self._walk(prefix)
        if start is None:
            return []

        result = []
        stack = [(prefix, start)]

        while stack:
            text, node = stack.pop()

            if node.terminal:
                result.append(text)
                if limit is not None and len(result) >= limit:
                    break

            # Stack LIFO: đẩy con theo chiều ngược để thăm tăng.
            children = list(node.children.items_sorted())
            for ch, child in reversed(children):
                stack.append((text + ch, child))

        return result
```

Cả ba backend đều cung cấp đúng giao diện `get/put/delete/items_sorted`, nên các thao tác `contains`, `insert`, `delete`, `count_prefix` và `words_with_prefix` có cùng thuật toán.

### 10.3. Vì sao cần xác thực bảng chữ cái ở tầng TrieSet?

`ArrayChildren` chỉ có 26 ô. Nếu một ứng viên nhận khóa `"đi"` còn ứng viên khác báo lỗi, ta không thể nói chúng **đáp ứng cùng hợp đồng**.

Bằng cách xác thực ở tầng chung, mọi backend demo đều nhận/khước từ cùng bộ đầu vào. Khi thiết kế cho Unicode thực tế, cần đổi chính sách và cách biểu diễn đồng bộ (mục 15), không lén để các backend có ngữ nghĩa khác nhau.

### 10.4. Xóa một cạnh và xóa một khóa là hai thao tác khác nhau

`parent.children.delete(ch)` chỉ loại **một cạnh** tại nút cha. `TrieSet.delete(word)` phải:

1. Xác nhận khóa đầy đủ có tồn tại.
2. Bỏ dấu terminal.
3. Giảm bộ đếm trên đường đi.
4. Dọn các cạnh chỉ khi cây con không còn khóa.
5. Cập nhật kích thước tập.

Nếu gọi xóa cạnh quá sớm, các từ chung tiền tố có thể bị mất. **Giao diện lưu nhánh không được tự quyết định liệu cả một khóa có được xóa hay không.**

## 11. Kiểm thử ba biểu diễn bằng cùng một hợp đồng

Cấu trúc dữ liệu đúng phải cho cùng **kết quả quan sát được**, không phụ thuộc việc các cạnh được đặt trong mảng, hash hay danh sách sắp.

### 11.1. Bộ kiểm thử chung

Đặt mã sau **sau tất cả các lớp** ở mục 9 và 10 trong cùng tệp Python:

```python
def check_backend(ChildrenType):
    trie = TrieSet(ChildrenType)

    assert len(trie) == 0
    assert trie.starts_with("")
    assert trie.count_prefix("") == 0

    for word in ["an", "anh", "ao", "ba", "ban"]:
        assert trie.insert(word)

    assert len(trie) == 5
    assert trie.contains("an")
    assert trie.contains("anh")
    assert not trie.contains("a")
    assert trie.starts_with("a")
    assert not trie.starts_with("ax")
    assert trie.count_prefix("a") == 3
    assert trie.count_prefix("an") == 2

    assert trie.words_with_prefix("an") == ["an", "anh"]
    assert trie.words_with_prefix("b") == ["ba", "ban"]
    assert trie.words_with_prefix("a", limit=2) == ["an", "anh"]
    assert trie.words_with_prefix("z") == []

    # Chèn trùng không tạo thêm khóa.
    assert not trie.insert("an")
    assert len(trie) == 5

    # Xóa tiền tố nhưng giữ từ dài.
    assert trie.delete("an")
    assert not trie.contains("an")
    assert trie.contains("anh")
    assert trie.starts_with("an")
    assert trie.count_prefix("an") == 1

    # Xóa từ dài: nhánh chết phải được cắt.
    assert trie.delete("anh")
    assert not trie.starts_with("an")
    assert trie.contains("ao")
    assert not trie.delete("anh")

    assert trie.delete("ba")
    assert trie.contains("ban")
    assert trie.count_prefix("b") == 1

    assert trie.insert("")
    assert trie.contains("")
    assert trie.words_with_prefix("", limit=1) == [""]
    assert trie.delete("")
    assert not trie.contains("")

    # Cùng hợp đồng lỗi của cả ba backend.
    try:
        trie.insert("đi")
    except ValueError:
        pass
    else:
        raise AssertionError("phải từ chối ký tự ngoài a-z")


for ChildrenType in (ArrayChildren, HashChildren, SortedChildren):
    check_backend(ChildrenType)
```

Các `assert` là **ví dụ kiểm thử**, không phải số đo hiệu năng. Bộ kiểm thử chủ ý gồm từ là tiền tố của từ khác, khóa rỗng, chèn trùng, xóa cạnh dùng chung và yêu cầu thứ tự gợi ý.

### 11.2. Kiểm tra hình thức bất biến

Dù kết quả tìm kiếm đúng trên vài ví dụ, bộ đếm nội bộ vẫn có thể sai sau nhiều thao tác. Ta có thể kiểm tra:

\[
count(v)=\mathbf{1}_{terminal(v)}
+\sum_{u\in children(v)}count(u).
\]

Một hàm kiểm tra debug áp dụng cho **mọi backend**:

```python
def validate_trie(trie):
    seen = set()
    totals = {}
    stack = [(trie._root, False)]

    while stack:
        node, expanded = stack.pop()

        if not expanded:
            assert id(node) not in seen
            seen.add(id(node))
            stack.append((node, True))

            labels = []
            for ch, child in node.children.items_sorted():
                labels.append(ch)
                assert len(ch) == 1 and "a" <= ch <= "z"
                stack.append((child, False))
            assert labels == sorted(set(labels))
        else:
            expected = int(node.terminal)
            for _, child in node.children.items_sorted():
                assert child.subtree_count > 0
                expected += totals[id(child)]

            assert node.subtree_count == expected
            totals[id(node)] = expected

    assert totals[id(trie._root)] == len(trie)


for ChildrenType in (ArrayChildren, HashChildren, SortedChildren):
    trial = TrieSet(ChildrenType)
    for word in ["", "an", "anh", "ao", "ba", "ban"]:
        assert trial.insert(word)
        validate_trie(trial)

    for word in ["an", "anh", "ba", "", "ban", "ao"]:
        assert trial.delete(word)
        validate_trie(trial)

    assert len(trial) == 0
```

Hàm duyệt toàn bộ cây để xác minh cấu trúc, nên nó thích hợp cho **kiểm thử phát triển**, không cần chạy sau mỗi lời gọi trong môi trường sản xuất.

### 11.3. Bất biến riêng của mảng cạnh có thứ tự

`SortedChildren` phải giữ:

```text
labels[i] < labels[i+1]  với mọi chỉ số i hợp lệ
len(labels) == len(nodes)
nodes[i] là nút con của nhãn labels[i]
```

Nếu chèn nhãn vào vị trí đúng nhưng quên dịch `nodes` cùng vị trí, tìm kiếm có thể đi sai nhánh dù danh sách nhãn vẫn được sắp tăng. Đây là lỗi biểu diễn nội bộ, không phải lỗi của Trie ADT.

## 12. Độ phức tạp của toàn bộ thao tác tìm, chèn và xóa

Gọi `v_0,\ldots,v_L` là các nút trên đường thao tác, khi những nút ấy tồn tại. Đặt `d_i` là số con của nút `v_i` tại lúc cần tìm nhánh kế tiếp.

### 12.1. Mảng cố định

Với bảng chữ cái cố định `σ=26`:

- `contains(word)`: O(L+1).
- `insert(word)`: O(L+1), vì tạo mỗi nút mới cần khởi tạo 26 ô — một hằng số.
- `delete(word)`: O(L+1), kể cả khi phải cắt tối đa `L` cạnh.
- Bộ nhớ vùng ô cho `N` nút: Θ(Nσ)=Θ(N) khi `σ` cố định.

Nếu `σ` là tham số, một lần tạo nút mới có chi phí Θ(σ). Với `k` nút mới, có thể viết chặn:

\[
T_{\mathrm{insert}}=O(L+1+kσ),\quad 0\le k\le L.
\]

Trong trường hợp phải tạo đủ `L` nút, chặn có thể thành O(Lσ). Đối với tìm/xóa cạnh đã có, số lần chọn ô vẫn O(L); việc duyệt toàn bộ cạnh theo thứ tự tại một nút có thể O(σ).

### 12.2. Hash Map

Với lookup theo ký hiệu O(1) kỳ vọng và chính sách kích thước phù hợp:

- `contains(word)`: O(L+1) kỳ vọng.
- `insert(word)`: O(L+1) kỳ vọng/khấu hao dưới những giả định băm và cấp phát phù hợp.
- `delete(word)`: O(L+1) kỳ vọng, chưa tính những sự kiện bảo trì đặc biệt nếu cài đặt có.
- `words_with_prefix`: phải cộng chi phí **sắp nhãn con** ở các nút đã thăm.

Không được gọi chặn O(L) là “xấu nhất tuyệt đối” với một Hash Map tổng quát. Một bảng có va chạm xấu hoặc một lần tái băm vẫn có thể khiến một thao tác đắt.

### 12.3. Mảng cạnh đã sắp

Tra cạnh thứ `i` bằng tìm nhị phân mất O(log(d_i+2)) phép so sánh nhãn. Khi tạo hoặc xóa một cạnh, phải dịch một số mục trong mảng của nút liên quan, tối đa O(d_i+1).

Chặn tổng quát cho `contains`:

\[
T_{\mathrm{contains}}(L)
=O\left(1+\sum_{i=0}^{L-1}\log(d_i+2)\right)
=O\left(1+L\log(σ+2)\right).
\]

Với `insert` hoặc `delete`, ngoài những lần tìm nhánh, còn có chi phí dịch ở các nút thực sự thêm/xóa cạnh:

\[
O\left(1+L\log(σ+2)+
\sum_{\text{nút sửa cạnh }v}(d_v+1)\right).
\]

Vì `d_v≤σ` và có tối đa O(L) nút được sửa cạnh, chặn đơn giản là O(L(σ+1)) trong trường hợp xấu nhất. Khi `σ=26` cố định, đây vẫn là O(L) theo độ dài khóa, nhưng dịch mảng có thể ảnh hưởng thời gian thực tế.

### 12.4. Tập cạnh là cây cân bằng

Nếu mỗi nút trie giữ một ordered map bằng cây cân bằng, một phép `get/put/delete` nhãn tốn O(log(d+2)) **trường hợp xấu nhất**, với so sánh nhãn O(1).

Do đó:

\[
T_{\mathrm{contains}},\
T_{\mathrm{insert}},\
T_{\mathrm{delete}}
=O(L\log(σ+2)+1)
\]

theo số bước so sánh cạnh/cập nhật cây, cộng chi phí cấp phát nút trie và cập nhật bộ đếm O(L).

Đánh đổi là bộ nhớ metadata cho từng nút của cây lưu cạnh và chi phí duy trì cân bằng. Nếu dùng một BST con **không cân bằng**, không thể tự áp dụng chặn O(log d) trong trường hợp xấu.

### 12.5. Chặn bộ nhớ phụ cho đường đi

Trong cài đặt chung, `insert` và `delete` lưu `path` gồm tối đa `L+1` tham chiếu, cần O(L+1) bộ nhớ phụ.

`contains` chỉ dùng một biến nút, nên cần O(1) bộ nhớ phụ bên cạnh chuỗi đầu vào. Những nút mới của `insert` thuộc **bộ nhớ cấu trúc được giữ lại**, không phải vùng phụ tạm `path`.

## 13. Autocomplete và phép duyệt nhánh theo thứ tự

Trie thường được chọn vì truy vấn tiền tố:

1. Đi theo `P` ký hiệu của tiền tố để tìm nút `v`.
2. Duyệt cây con của `v`.
3. Xuất các khóa tại những nút `terminal=True`.

Độ phức tạp không chỉ là chi phí của bước 1: phần duyệt và tạo chuỗi kết quả có thể rất lớn.

### 13.1. Sự khác nhau nằm ở `items_sorted`

| Backend | Cách lấy con theo nhãn tăng | Chi phí tại một nút bậc `d` |
| --- | --- | --- |
| ArrayChildren | Quét các ô `a-z` từ trái sang phải | Θ(σ) để xem hết các ô |
| HashChildren | `sorted(children)` rồi truy cập theo nhãn | O(d log(d+1)) thời gian, kể cả chi phí sắp |
| SortedChildren | Duyệt các cặp cạnh đã giữ tăng sẵn | Θ(d) |
| Cây cân bằng lưu cạnh | Duyệt inorder | Θ(d), cộng chi phí khởi tạo/trạng thái iterator tùy cách cài |

Nếu phải gợi ý nhiều lần nhưng ít cập nhật cạnh, việc **giữ thứ tự sẵn** có thể có giá trị: không cần sắp lại mỗi lần duyệt. Nếu ứng dụng chỉ tra chính xác theo khóa và hiếm khi liệt kê, Hash Map có thể thuận lợi hơn.

### 13.2. Chi phí tạo chuỗi trung gian

Trong mã `words_with_prefix` ở mục 10, ta đẩy `text + ch` vào Stack. Mỗi phép nối **tạo chuỗi mới**, thường phải sao chép tiền tố. Vì vậy thời gian liệt kê còn phụ thuộc tổng độ dài những chuỗi trung gian đã tạo, không chỉ số cạnh.

Để tối ưu, có thể giữ một danh sách ký hiệu đường đi và dùng sự kiện **vào/ra nút** khi DFS, chỉ tạo chuỗi hoàn chỉnh tại các nút terminal. Cách đó giảm sao chép trên những đoạn tiền tố trung gian nhưng vẫn phải tạo đúng lượng ký tự được trả về.

### 13.3. Giới hạn `limit` không bảo đảm O(limit)

Ngay cả khi chỉ cần hai gợi ý, thuật toán có thể phải xem nhiều cạnh để tới hai nút terminal. Bản cài đặt ở mục 10 còn gọi `list(node.children.items_sorted())` trên **mọi nút đã thăm**, có thể lấy tất cả con trước khi biết đã đủ kết quả.

Đây là ví dụ cho thấy **giao diện trả tối đa `k` kết quả** không tự làm thời gian O(k). Cần phân tích chi phí đi đến kết quả và tiêu chuẩn sắp thứ tự.

### 13.4. Thứ tự Unicode khác thứ tự từ điển theo ngôn ngữ

Duyệt nhãn `a-z` tăng dần cho thứ tự từ điển trên đúng alphabet demo. Với Unicode, thứ tự code point không nhất thiết là thứ tự phù hợp với từ điển tiếng Việt hoặc locale khác.

Nếu ứng dụng yêu cầu một quan hệ thứ tự riêng, cấu trúc lưu cạnh có thứ tự phải dùng **comparator tương ứng**, và quy tắc so sánh phải nhất quán ở tìm/chèn/xóa và duyệt.

## 14. Lựa chọn theo hình dạng trie và workload

Không có một loại bảng con tốt nhất trong mọi hoàn cảnh.

### 14.1. Khi phần lớn nút chỉ có 0 hoặc 1 con

Giả sử có rất nhiều khóa chia sẻ các đoạn tiền tố dài. Những đoạn này tạo hàng nghìn nút chỉ có một nhánh.

- Mảng 26 ô trả phí 26 ô trên **mỗi** nút.
- Dictionary hoặc mảng cặp sắp lưu một cạnh thật tại mỗi nút, cộng overhead cố định.
- Một cách nén đường đi (*radix/Patricia trie*) có thể giảm cả số nút, nhưng đó là thay đổi **hình thức trie**, không chỉ thay đổi bảng con.

Ở tình huống này, nên đo số nút `d=0`, `d=1` và bộ nhớ mỗi nút trước khi chọn.

### 14.2. Khi nhiều nút có bậc ra cao

Nếu `σ=26` và phần lớn nút có gần 26 con:

- Mảng trực tiếp tận dụng các ô đã cấp khá đầy và có lookup đơn giản.
- Hash Map không còn nhiều lợi thế về tính thưa; vẫn có metadata của bảng.
- Mảng cạnh sắp có thể phải dịch khá nhiều phần tử khi thêm/xóa, nhưng chỉ tối đa 26 trong demo.

Lợi ích thật sự phụ thuộc byte và thời gian đo trên runtime chứ không chỉ số bậc.

### 14.3. Khi cập nhật thường xuyên

Nếu thường xuyên thêm/xóa khóa làm phát sinh nhiều cạnh mới:

- Mảng cố định có giá gán/xóa cạnh rẻ, nhưng cấp ô ở mọi nút.
- Hash Map thường có cập nhật kỳ vọng nhanh, với những lần resize hiếm.
- Mảng cạnh sắp có thể dịch O(d) mục mỗi lần có cạnh mới.
- Cây cân bằng lưu cạnh có chặn cập nhật O(log d) nhưng chi phí metadata và cấp phát cao hơn.

Nếu `σ` nhỏ, dịch vài mục có thể vẫn nhanh hơn thao tác trên ordered tree phức tạp. Đừng suy từ Big-O rằng lựa chọn nào chắc chắn nhanh hơn tại `d≤26`.

### 14.4. Khi autocomplete theo thứ tự là thao tác chủ đạo

Khi nhiều truy vấn liệt kê kết quả theo thứ tự từ điển:

- Mảng cố định cho thứ tự trực tiếp nhưng phải quét ô trống.
- Mảng cạnh sắp có thể duyệt đúng `d` nhánh đang có.
- Hash Map cần sắp nhãn mỗi lần hoặc thêm cơ chế cache thứ tự.
- Cây cân bằng có thể duyệt theo thứ tự mà không phải sắp lại, đổi lại overhead.

Nếu cache danh sách nhãn đã sắp trong Hash Map, việc thêm/xóa cạnh phải **làm mất hiệu lực cache hoặc cập nhật nó**, làm bài toán trở thành đánh đổi cập nhật–truy vấn.

## 15. Từ bảng chữ cái ASCII đến Unicode và bảng ký hiệu động

Phần mã dùng `a-z` nhằm bảo đảm mọi backend có cùng tập khóa hợp lệ. Ứng dụng tiếng Việt thật cần thiết kế rộng hơn.

### 15.1. Vì sao `ord(ch) - ord('a')` không dùng trực tiếp cho mọi ký tự?

Chỉ số này có nghĩa cho chữ `a-z`. Với ký tự như `đ`, `ê`, chữ số, dấu kết hợp hoặc emoji, chỉ số không còn nằm trong `[0,25]`. Nếu không kiểm tra phạm vi, Python có thể truy cập sai vị trí hoặc báo lỗi không rõ nghĩa.

Không được “sửa” bằng cách cấp một mảng có ô cho mọi code point có thể tồn tại ở **mỗi nút**, vì bộ nhớ trên nút có thể khổng lồ.

### 15.2. Bảng ký hiệu hữu hạn được chuẩn hóa

Một phương án là xác định trước tập ký hiệu thực sự dùng:

```text
alphabet = ["a", "b", ..., "ă", "â", "đ", "ê", ...]
index = {symbol: position}
```

Sau đó, mảng cố định dùng `index[ch]` để lấy ô. Giải pháp này hợp lý nếu:

- Bảng ký hiệu hữu hạn và đủ nhỏ.
- Mọi ký hiệu đầu vào đã chuẩn hóa đúng cách.
- Thứ tự `alphabet` khớp quy tắc liệt kê mà ứng dụng cần.
- Ký hiệu mới không thể xuất hiện ngoài hợp đồng, hoặc có quy trình cập nhật bảng ký hiệu và dữ liệu.

Nếu bảng ký hiệu có thể thay đổi theo dữ liệu, cập nhật kích thước mảng ở mọi nút trie là vấn đề rất khác so với tăng một danh sách cạnh thưa.

### 15.3. Hash và tập cạnh có thứ tự thường linh hoạt hơn

Dictionary con hỗ trợ nhãn ký tự từ nhiều miền giá trị mà không cần cấp chỗ cho toàn bộ miền. Mảng cạnh sắp hoặc ordered tree cũng có thể dùng comparator cho ký hiệu, miễn comparator nhất quán.

Tuy nhiên, **chọn ký hiệu** vẫn phải được đặc tả: ứng dụng có thể lưu theo byte UTF-8, Unicode code point hoặc grapheme cluster. Nếu dùng cụm tự vị dài nhiều code point làm nhãn, chi phí hash/so sánh một nhãn không còn hiển nhiên O(1).

### 15.4. Chuẩn hóa khóa là một phần của hợp đồng

Ví dụ hai cách biểu diễn một ký tự có dấu:

```python
import unicodedata

a = "á"
b = "a\u0301"

assert a != b
assert unicodedata.normalize("NFC", a) == \
       unicodedata.normalize("NFC", b)
```

Nếu ứng dụng muốn coi chúng là cùng khóa, phải dùng **cùng quy tắc chuẩn hóa** khi tìm, chèn, xóa và truy vấn tiền tố. Việc đổi Hash Map thành mảng hay ordered set không tự giải quyết vấn đề khác biệt biểu diễn Unicode.

### 15.5. Thứ tự tăng của ký hiệu phải được định nghĩa

Đối với autocomplete tiếng Việt, “tăng dần” có thể có nghĩa thứ tự code point, thứ tự chữ cái theo quy ước ngôn ngữ hoặc sắp theo tần suất sử dụng.

- Mảng con thường cho thứ tự theo **chỉ số trong alphabet**.
- Hash Map cần sắp theo comparator được chọn.
- Mảng/cây cạnh có thứ tự phải được duy trì theo comparator ấy.

Nếu dùng comparator chỉ để hiển thị nhưng thứ tự của ordered map không tương thích với phép tìm, có thể gây lỗi nhận diện nhãn hoặc thứ tự không nhất quán.

## 16. Những lỗi triển khai cần tránh

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Cấp mảng `σ` ô cho mọi code point Unicode | Bộ nhớ trên nút quá lớn | Chỉ dùng alphabet nhỏ hoặc dùng biểu diễn thưa |
| Bỏ kiểm tra ký tự ở ArrayChildren | Chỉ số âm/ngoài miền; có thể truy cập sai | Xác thực alphabet trước khi tính chỉ số |
| Dùng Python `set` rồi kỳ vọng duyệt có thứ tự | Thứ tự autocomplete không được bảo đảm | Dùng cấu trúc ordered thật hoặc sắp khi cần |
| Coi thứ tự thêm của `dict` là thứ tự từ điển | Kết quả không tăng theo nhãn | Gọi `sorted` hoặc dùng bảng con có thứ tự |
| Viết mảng nhãn sắp nhưng không dịch mảng nút | Nhãn trỏ sai nút con | Cập nhật nhãn và con cùng vị trí |
| Coi `bisect_left` làm toàn bộ `insert` O(log d) | Quên chi phí dịch phần tử | Tính O(d) cho mảng cạnh sắp |
| Gọi mọi ordered set là cây cân bằng | Sai chặn cập nhật | Nêu rõ mảng sắp hay balanced tree |
| Ghi O(1) cho hash mà bỏ điều kiện | Che va chạm, resize, chi phí nhãn | Phân biệt kỳ vọng và xấu nhất |
| Xóa cạnh khi nút con vẫn chứa khóa | Làm mất nhiều từ chung tiền tố | Chỉ cắt nhánh có `subtree_count=0` |
| Chỉ kiểm tra đường đi để xác định khóa | Tiền tố bị coi là khóa hoàn chỉnh | Kiểm tra `terminal` ở nút cuối |
| Chèn trùng vẫn tăng `subtree_count` | Sai số khóa theo tiền tố | Chỉ cập nhật khi terminal từ False thành True |
| So sánh backend bằng bộ đầu vào khác nhau | Kết luận hiệu năng không công bằng | Dùng chung hợp đồng và vết thao tác |
| Đo mỗi `get` rồi kết luận toàn vòng đời | Bỏ chi phí xây, chèn, xóa và autocomplete | Đo cả xây, truy vấn, cập nhật, xuất |
| Tối ưu bộ nhớ bằng cách giữ nút chết mà không đổi `starts_with` | Có thể báo đường tiền tố “ảo” | Dọn nhánh hoặc kiểm tra count sống |

## 17. Thiết kế phép đo để lựa chọn có cơ sở

Big-O giúp loại phương án không phù hợp, nhưng không đo được số byte dictionary hay chi phí cache trên máy thực tế. Nếu cần chọn giữa ba backend, hãy dùng cùng một tập khóa và cùng vết thao tác.

### 17.1. Chọn dữ liệu thử có ý nghĩa

Thử ít nhất ba dạng:

1. **Tiền tố dài, ít phân nhánh:** nhiều khóa đi chung một đường rồi mới khác ở cuối.
2. **Phân nhánh dày:** nhiều ký hiệu khác nhau xuất hiện sau cùng một tiền tố.
3. **Khóa ngắn, nhiều nhánh rải rác:** gốc hoặc nhiều nút nông có bậc ra lớn.

Cùng với mỗi dữ liệu, ghi:

- Số khóa `n` và tổng độ dài `S`.
- Số nút `N`.
- Phân bố bậc ra: số nút `d=0`, `d=1`, `d≥2`.
- Số lần tra cạnh, tạo cạnh và xóa cạnh.
- Số lần duyệt theo thứ tự và số khóa được xuất.

### 17.2. Đo từng phần của vòng đời

| Giai đoạn | Chỉ số nên đo |
| --- | --- |
| Xây trie | Thời gian nạp `n` khóa, số nút tạo mới, bộ nhớ cuối |
| Tìm chính xác | Thời gian `contains` với khóa có/không có; độ dài khóa |
| Thêm | Thời gian chèn mới, chèn trùng, số cạnh tạo mới |
| Xóa | Thời gian xóa khóa ngắn/dài, số cạnh dọn, kích thước sau xóa |
| Autocomplete | Thời gian theo tiền tố, số kết quả, yêu cầu thứ tự |
| Bộ nhớ | Bộ nhớ giữ lại và bộ nhớ đỉnh khi cấp phát/resize |

Đo **tổng thời gian vết thao tác** nếu bài toán của ứng dụng thường xuyên thay đổi trạng thái. Một backend có tra nhanh nhưng cấp phát lớn có thể không thắng ở workload cập nhật dày.

### 17.3. Kiểm soát phạm vi khi đo Python

Nếu dùng `sys.getsizeof`, nhớ rằng nó không tự cộng sâu các đối tượng nút và dictionary được tham chiếu. Nếu dùng `tracemalloc`, nó theo dõi những cấp phát thuộc phạm vi công cụ, không đồng nghĩa tổng RAM tiến trình.

Không so sánh một con số “kích thước mảng con” với “kích thước toàn bộ trie” rồi rút kết luận về byte/phần tử. Cần thống nhất phạm vi và tránh đếm trùng đối tượng dùng chung.

### 17.4. Kiểm tra tính đúng trước khi đo

Trước khi so thời gian, ba ứng viên phải:

- Nhận cùng kiểu khóa và cùng quy tắc chuẩn hóa.
- Xử lý chèn trùng, khóa rỗng và xóa thiếu như nhau.
- Trả cùng tập khóa và số lượng theo tiền tố.
- Duyệt theo đúng thứ tự được hợp đồng yêu cầu.

Một cấu trúc “nhanh hơn” nhưng trả gợi ý sai thứ tự hoặc làm mất khóa sau xóa không phải phương án thay thế hợp lệ.

## 18. Bài tập vận dụng có gợi ý giải

### Bài 1 — Đếm cạnh thật và ô cấp phát

Trie chứa `{"an","anh","ao","ba","ban"}`, dùng 8 nút. Mỗi nút có mảng con 26 ô. Tính số ô và số cạnh thật.

**Gợi ý:** Có `8×26=208` ô được cấp, nhưng chỉ `8-1=7` cạnh thật. Có 201 ô trống trong mô hình mỗi nút cấp mảng.

### Bài 2 — Vì sao nút lá làm mảng tốn RAM?

Một trie có 10.000 nút lá, mỗi nút có mảng 26 con trỏ rộng 8 byte. Chỉ tính vùng ô của nút lá, cần bao nhiêu byte?

**Gợi ý:** `10.000×26×8=2.080.000` byte cho các ô ở nút lá, mặc dù các nút lá không có con. Còn phải cộng header của mảng và nút.

### Bài 3 — Chọn cạnh theo ba cấu trúc

Một nút có `d=12` cạnh trong bảng chữ cái `σ=26`. Nêu bậc chi phí `get(c)` của mảng cố định, Hash Map và mảng cạnh đã sắp.

**Gợi ý:** Mảng O(1) theo chỉ số, Hash Map O(1) kỳ vọng, mảng nhãn sắp O(log(d+2)) bằng tìm nhị phân. Không suy ra số micro giây từ các ký hiệu này.

### Bài 4 — Chèn vào mảng cạnh đã sắp

Nút có nhãn cạnh `['a','d','m','z']`. Thêm nhánh `'b'`. Danh sách nhãn mới và số phần tử phải dịch về bên phải là gì?

**Gợi ý:** `['a','b','d','m','z']`. Ba nhãn `d,m,z` cần dịch vị trí trong mảng nhãn, và ba nút tương ứng trong mảng con cũng phải dịch. Tìm vị trí O(log d) nhưng chèn có chi phí O(d).

### Bài 5 — Xóa nhánh theo thứ tự

Nút có `labels=['a','b','d','m','z']`. Xóa cạnh `'b'`. Mảng nhãn và mảng con cần được cập nhật thế nào?

**Gợi ý:** Tìm vị trí của `b` bằng `bisect_left`, rồi xóa ở **cả hai mảng**. Danh sách nhãn trở thành `['a','d','m','z']`; những mục phía sau dịch một vị trí.

### Bài 6 — Hash Map có tự giữ thứ tự từ điển?

Một dictionary nhận các nhánh theo thứ tự `z, a, m`. Nếu duyệt trực tiếp `dict.items()`, có được cam kết kết quả `a,m,z` không?

**Gợi ý:** Không. `dict` Python giữ thứ tự thêm vào, không tự sắp theo nhãn. Muốn thứ tự tăng, dùng `sorted(dictionary)` hoặc biểu diễn lưu cạnh theo thứ tự.

### Bài 7 — Tại sao `set` không là ordered set?

Một bạn học dùng `set` của Python để lưu `(char,node)` và cho rằng các cạnh luôn được duyệt tăng dần. Chỉ ra hai vấn đề.

**Gợi ý:** `set` không bảo đảm thứ tự tăng. Ngoài ra, một tập cặp không tự đảm bảo **mỗi ký hiệu chỉ đi tới một con**, nếu các cặp khác nút nhưng cùng ký hiệu được coi là phần tử khác. Cần một Map theo nhãn hoặc cấu trúc có bất biến duy nhất ký hiệu.

### Bài 8 — Hash Map và số con nhỏ

Phần lớn nút chỉ có `d=1`, nhưng bảng ký hiệu có 1000 ký hiệu. Vì sao biểu diễn thưa đáng cân nhắc?

**Gợi ý:** Mảng cố định dành 1000 ô cho mỗi nút, trong khi chỉ một cạnh là thật. Hash Map hoặc danh sách cặp sắp lưu nhãn và con thực, cộng overhead quản lý; phải đo byte thực tế nhưng chênh lệch số ô là lớn.

### Bài 9 — Truy vấn autocomplete nhiều lần

Một trie hiếm cập nhật nhưng được gọi `words_with_prefix` hàng triệu lần, luôn yêu cầu nhãn tăng. Vì sao mảng cạnh sắp hoặc ordered tree có thể hấp dẫn?

**Gợi ý:** Có thể duyệt nhãn tăng trực tiếp, không cần sắp lại ở mỗi lần gợi ý. Đổi lại, chèn/xóa vào mảng cạnh sắp có thể O(d), còn ordered tree cần metadata và cân bằng.

### Bài 10 — Xóa một từ, không xóa cả nhánh

Trie lưu `{"an","anh"}`. Xóa `an`. Trong bất kỳ backend nào, có được xóa cạnh `'n'` tại nút `a` không?

**Gợi ý:** Không. Nút `an` vẫn còn cây con chứa `anh`; bộ đếm tại nút đó sau xóa còn 1. Chỉ bỏ terminal của `an` và giảm count trên đường đi.

### Bài 11 — Xóa cạnh chết ở mảng sắp

Sau khi xóa khóa cuối cùng dưới nhánh có nhãn `b`, `SortedChildren.delete('b')` cần làm gì để giữ bất biến?

**Gợi ý:** Tìm vị trí bằng tìm nhị phân, xóa nhãn trong `labels` và nút tương ứng trong `nodes`. Hai mảng phải giữ độ dài bằng nhau, nhãn tăng và ánh xạ đúng.

### Bài 12 — Thời gian chèn theo `σ`

Một trie dùng mảng `σ` ô mỗi nút, chèn khóa dài `L` mà không có tiền tố chung, phải tạo `L` nút mới. Phân tích thời gian trong mô hình `σ` biến động.

**Gợi ý:** Đi theo ký hiệu O(L), nhưng khởi tạo `L` mảng mỗi mảng `σ` ô tốn Θ(Lσ). Vì thế O(Lσ) trong trường hợp này, không thể mặc định O(L) nếu `σ` không phải hằng số.

### Bài 13 — Chọn giữa mảng sắp và cây cân bằng

Một nút trie có `d` rất lớn, vừa cần tìm cạnh vừa chèn/xóa cạnh liên tục và duyệt thứ tự. So sánh mảng cạnh sắp với cây cân bằng theo nhãn.

**Gợi ý:** Mảng sắp tìm O(log d), chèn/xóa O(d) do dịch; cây cân bằng tìm/chèn/xóa O(log d) trường hợp xấu nhất và duyệt Θ(d), nhưng tốn metadata và có thể cấp phát nhiều nút. Cần đo thêm hệ số bộ nhớ.

### Bài 14 — Hợp đồng với Unicode

Ứng dụng tiếng Việt cần lưu `"đi"`, `"đỏ"` và `"đèn"`. Vì sao `ArrayChildren` trong bài sẽ báo lỗi? Nêu hai cách mở rộng.

**Gợi ý:** Nó chỉ nhận a-z theo chỉ số 0–25. Có thể chuẩn bị alphabet Unicode hữu hạn với bảng ánh xạ ký hiệu→chỉ số, hoặc dùng Hash Map/ordered map hỗ trợ ký hiệu Unicode. Phải chuẩn hóa chuỗi thống nhất.

### Bài 15 — Thiết kế benchmark công bằng

Hãy nêu những yếu tố phải giữ giống nhau khi so `ArrayChildren`, `HashChildren` và `SortedChildren`.

**Gợi ý:** Cùng bộ khóa, cùng hợp đồng xử lý khóa, cùng trình tự tìm/chèn/xóa, cùng quy tắc sắp thứ tự, cùng môi trường đo và cùng phạm vi bộ nhớ. Kiểm thử kết quả trước khi so thời gian; báo cả tải cập nhật và tải autocomplete.

## 19. Quy trình chọn biểu diễn tập nhánh

Có thể áp dụng checklist sau khi triển khai trie cho một bài toán mới.

```text
1. Hợp đồng và ký hiệu:
   - Trie lưu Set, Map hay Multiset?
   - Cạnh mang byte, code point hay chuỗi nén?
   - Bảng ký hiệu sigma nhỏ và cố định hay rất lớn?
   - Có quy tắc chuẩn hóa Unicode/collation không?

2. Thống kê hình dạng:
   - Số nút N và số cạnh thật N-1?
   - Phân bố bậc ra d: bao nhiêu lá, bao nhiêu nút 1 con?
   - Mức phân nhánh cao tập trung gần gốc hay sâu?

3. Các thao tác chính:
   - Tìm khóa chính xác chiếm bao nhiêu?
   - Chèn/xóa có tạo/xóa cạnh thường xuyên?
   - Có cần autocomplete theo thứ tự?
   - Kích thước kết quả và limit thường là bao nhiêu?

4. Các phương án:
   - Mảng sigma ô: O(1) truy cập, O(sigma) ô/nút.
   - Hash Map: O(1) kỳ vọng theo cạnh, phải sắp nhãn nếu cần thứ tự.
   - Mảng cạnh sắp: O(log d) tìm, O(d) cập nhật, O(d) duyệt tăng.
   - Cây cạnh cân bằng: O(log d) tìm/sửa, O(d) duyệt tăng.

5. Bất biến và kiểm thử:
   - Mỗi ký hiệu dẫn tới tối đa một nút con?
   - terminal và subtree_count giữ đúng qua thêm/xóa?
   - Xóa cạnh chỉ khi không còn khóa trong cây con?
   - Backend mới có trả đúng cùng API và thứ tự?

6. Đo đạc:
   - Thời gian xây, tra, thêm, xóa, autocomplete?
   - Số ô dư, metadata mỗi nút và bộ nhớ đỉnh?
   - Có cùng workload, cùng kích thước và cùng phạm vi đo?
   - Có trường hợp đầu vào gây chi phí xấu nhất đáng kể?

7. Quyết định:
   - Biểu diễn nào đáp ứng RAM và độ trễ của ứng dụng?
   - Nếu số nhánh hoặc workload thay đổi, có cần đổi biểu diễn?
```

## 20. Tổng kết và định hướng áp dụng

Ba cách lưu nhánh giải quyết cùng một yêu cầu: từ một nút trie và ký hiệu tiếp theo, xác định đúng **một** nút con hoặc kết luận không có cạnh. Nhưng chúng thực hiện yêu cầu bằng những đánh đổi khác nhau.

- **Mảng cố định**: truy cập cạnh trực tiếp, duyệt theo alphabet dễ dàng, nhưng trả bộ nhớ cho `σ` ô ở **mọi nút**, kể cả nút lá.
- **Bảng băm**: linh hoạt với nút thưa và ký hiệu đa dạng, tìm/cập nhật kỳ vọng nhanh, nhưng có overhead hash và không tự bảo đảm thứ tự từ điển.
- **Tập cạnh có thứ tự**: duyệt theo nhãn tăng thuận lợi. Nếu dùng **mảng cặp đã sắp**, tìm nhanh bằng nhị phân nhưng chèn/xóa có thể dịch O(d); nếu dùng **cây cân bằng**, cập nhật O(log d) nhưng tốn thêm cấu trúc quản lý.

**Điểm quan trọng nhất:** không được chọn biểu diễn chỉ dựa trên một kết luận Big-O tách rời ngữ cảnh. Hãy tính cả `L`, `σ`, bậc ra `d`, phân bố nhánh trong trie, tần suất tìm/chèn/xóa, nhu cầu autocomplete, quy tắc Unicode và số byte mỗi nút. Khi giữ nguyên bất biến của khóa và chỉ thay `children`, ta có thể cải tiến cài đặt mà **không làm thay đổi hành vi công khai của Trie** — đúng tinh thần thiết kế cấu trúc dữ liệu theo giao diện, thao tác và chi phí.
