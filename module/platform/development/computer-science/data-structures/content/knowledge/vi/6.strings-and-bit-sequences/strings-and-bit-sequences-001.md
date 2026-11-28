# Chuỗi như dãy ký hiệu và các lựa chọn biểu diễn

Trong cấu trúc dữ liệu, **chuỗi (string)** là một dãy ký hiệu có thứ tự. Ký hiệu có thể là chữ cái, chữ số, dấu câu, biểu tượng hoặc phần tử của một bảng chữ cái được định nghĩa riêng. Cùng một chuỗi nhìn thấy trên màn hình có thể được biểu diễn bằng các dãy byte và cấu trúc lưu trữ khác nhau; lựa chọn đó quyết định chi phí truy cập, nối, chèn, xóa và sử dụng bộ nhớ.

Bài học thuộc chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là biết mô hình hóa chuỗi bằng các bất biến rõ ràng, phân biệt ký hiệu logic với đơn vị lưu trữ vật lý, và lựa chọn biểu diễn dựa trên thao tác cần tối ưu. Những nguyên tắc này tiếp nối việc học mảng và chuẩn bị cho các cấu trúc như bảng băm, cây, trie và chỉ mục chuỗi.

## 1. Mô hình trừu tượng: chuỗi là một dãy, không nhất thiết là một mảng byte

Với bảng ký hiệu \(\Sigma\), một chuỗi độ dài \(n\) được viết:

\[
S = (s_0, s_1, \ldots, s_{n-1}), \quad s_i \in \Sigma.
\]

Ở mức mô hình, các thao tác cơ bản gồm:

- **Độ dài** `length(S)`: số ký hiệu theo quy ước của mô hình.
- **Truy cập** `S[i]`: lấy ký hiệu ở vị trí `i`, với `0 ≤ i < n`.
- **Đoạn con** `S[i:j]`: lấy các ký hiệu từ `i` đến trước `j`, với `0 ≤ i ≤ j ≤ n`.
- **Nối** `A + B`: ghép hai dãy theo thứ tự, độ dài kết quả bằng `length(A) + length(B)`.
- **Chèn, xóa, thay thế**: biến đổi một đoạn liên tiếp nếu kiểu chuỗi cho phép sửa đổi.
- **So sánh, tìm kiếm, duyệt**: xử lý tuần tự hoặc kiểm tra quan hệ giữa các chuỗi.

Chuỗi rỗng `""` có độ dài bằng 0. Thứ tự ký hiệu quan trọng: `"ab"` khác `"ba"`. Nếu có định nghĩa phép nối, chuỗi rỗng là phần tử trung hòa: `S + "" = "" + S = S`.

**Điểm mấu chốt:** phải xác định *một ký hiệu* nghĩa là gì trước khi định nghĩa `length` hoặc `S[i]`. Với văn bản Unicode, “một ký tự” có thể chỉ những đơn vị khác nhau.

## 2. Ký hiệu logic, Unicode và byte lưu trữ

| Đơn vị | Ý nghĩa | Ví dụ/ảnh hưởng |
|---|---|---|
| **Byte** | Nhóm 8 bit trong bộ nhớ hoặc tệp | Một ký hiệu UTF-8 có thể chiếm 1–4 byte. |
| **Code unit** | Đơn vị của cách mã hóa, như 8 bit trong UTF-8 hoặc 16 bit trong UTF-16 | Truy cập code unit thường là truy cập phần tử vật lý. |
| **Unicode code point** | Giá trị được gán trong không gian mã Unicode | Biểu tượng `🙂` là một code point, nhưng chiếm nhiều code unit trong UTF-8/UTF-16. |
| **Grapheme cluster** | Cụm mà người đọc thường cảm nhận là một ký tự | `e` cộng dấu sắc kết hợp có thể hiển thị thành một chữ có dấu dù gồm hai code point. |

Ví dụ xét chuỗi `Aé🙂`:

| Cách đếm/biểu diễn | Giá trị |
|---|---|
| Số Unicode code point | 3 |
| Số grapheme cluster | 3 |
| UTF-8 | 7 byte: `41 C3 A9 F0 9F 99 82` (hệ 16) |
| UTF-16 | 4 code unit 16 bit: `A` (1), `é` (1), `🙂` (2) |
| UTF-32 | 3 code unit 32 bit, tức 12 byte, nếu lưu liên tiếp và không tính metadata |

UTF-8 có ưu thế tương thích ASCII và thường tiết kiệm chỗ cho nhiều chuỗi có nhiều ký hiệu ASCII. UTF-16 sử dụng một hoặc hai code unit 16 bit cho mỗi Unicode scalar value. UTF-32 dùng một code unit 32 bit cho mỗi scalar value, nên thuận lợi hơn cho truy cập theo code point nhưng tốn ít nhất 4 byte cho mỗi phần tử. Không có lựa chọn nào luôn tối ưu cho mọi loại dữ liệu.

Hai chuỗi sau có thể hiển thị giống nhau nhưng khác dãy code point:

```python
composed = "é"           # U+00E9: một code point
decomposed = "e\u0301"   # U+0065, U+0301: hai code point

print(len(composed))      # 1 trong Python: đếm code point
print(len(decomposed))    # 2
print(composed == decomposed)  # False: khác chuỗi code point
```

Khi so sánh chuỗi theo nghĩa ngôn ngữ, có thể cần **chuẩn hóa Unicode** (ví dụ NFC) trước khi so sánh. Tuy nhiên, việc chuẩn hóa phải tuân theo hợp đồng dữ liệu: không tự ý thay đổi những giá trị mà hệ thống cần giữ nguyên từng byte, chẳng hạn dữ liệu giao thức hoặc chữ ký số.

### Độ dài và chỉ số phụ thuộc vào API

- Python `str` thường trình bày phép `len()` và chỉ số dưới dạng **code point**, nên `len("Aé🙂") == 3`.
- JavaScript `String.length` và Java `String.length()` đếm **UTF-16 code unit**, nên cùng chuỗi trên có độ dài 4 theo các API đó.
- Một bộ đệm UTF-8 thường giữ độ dài theo **byte**: dãy `Aé🙂` chiếm 7 byte, còn đếm code point đòi hỏi giải mã hoặc dùng chỉ mục bổ trợ.

Các ví dụ trên mô tả hợp đồng của API, không có nghĩa một ngôn ngữ bắt buộc phải dùng một dạng bố trí bộ nhớ duy nhất. Tách biệt **định nghĩa logic** và **biểu diễn bên trong** giúp tránh lỗi khi chuyển ngôn ngữ hoặc trao đổi dữ liệu.

## 3. Những biểu diễn chuỗi thông dụng

### 3.1. Vùng nhớ liên tiếp có lưu độ dài

Một chuỗi có thể lưu trong mảng các đơn vị mã hóa, kèm số phần tử thực tế:

```text
length = 5, capacity = 8
index:   0   1   2   3   4   5   6   7
buffer: [H] [e] [l] [l] [o] [_] [_] [_]
         <---- dữ liệu ----> <dung lượng dự phòng>
```

Các **bất biến** quan trọng là `0 ≤ length ≤ capacity`, và chỉ đoạn `[0, length)` mang nội dung chuỗi. Nếu bộ đệm có thể thay đổi kích thước, `capacity` cho biết sức chứa đã cấp phát; nếu là chuỗi bất biến, dung lượng có thể vừa đúng số phần tử thực tế.

Ưu điểm: bố trí liên tiếp, tận dụng cache CPU, dễ gửi/đọc dữ liệu tuần tự và lấy phần tử tại chỉ số **vật lý** trong `O(1)`. Nhược điểm: chèn/xóa ở giữa đòi hỏi dịch chuyển phần tử hoặc cấp phát chuỗi mới. Nếu mã hóa có độ rộng thay đổi như UTF-8, truy cập code point thứ `i` không thể mặc nhiên coi là `O(1)` chỉ vì byte được lưu liên tiếp.

Trong **chuỗi bất biến (immutable string)**, một khi tạo ra, nội dung không thay đổi. Điều này đơn giản hóa chia sẻ giá trị, dùng chuỗi làm khóa và tránh sửa dữ liệu từ xa ngoài ý muốn. Đổi lại, nối hoặc thay thế thường tạo vùng nhớ mới. Một số runtime có tối ưu riêng, nhưng không nên dựa vào chúng khi ước lượng chi phí thuật toán tổng quát.

### 3.2. Chuỗi kết thúc bằng ký hiệu đặc biệt (null-terminated)

Trong quy ước C truyền thống, chuỗi ký tự kết thúc tại byte `\0`:

```c
#include <stdio.h>
#include <string.h>

int main(void) {
    char data[] = {'H', 'i', '\0', 'X'};
    printf("%zu\n", strlen(data));  // 2: đếm tới byte NUL
    printf("%zu\n", sizeof data);   // 4: tổng số byte mảng
}
```

Biểu diễn này không bắt buộc có trường độ dài nên thuận tiện cho nhiều API C. Đổi lại, `strlen` chạy `O(n)` để tìm ký hiệu kết thúc; byte NUL nằm giữa dữ liệu sẽ bị coi là kết thúc chuỗi. Một vùng nhớ phải có byte kết thúc hợp lệ trong phạm vi có thể đọc trước khi truyền vào API dựa trên NUL; thiếu điều này có thể dẫn tới đọc vượt giới hạn. Với văn bản UTF-8, `strlen` đếm **byte**, không đếm code point hay ký tự hiển thị.

### 3.3. Bộ đệm có thể mở rộng (dynamic character buffer)

Một bộ đệm có `length` và `capacity` cho phép sửa trực tiếp. Khi đầy, hệ thống cấp phát vùng lớn hơn và sao chép dữ liệu, thường sử dụng quy tắc tăng dung lượng theo hệ số.

- Thêm một đơn vị ở cuối tốn `O(1)` nếu còn chỗ; khi phải cấp phát lại có thể tốn `O(n)`.
- Với chiến lược tăng dung lượng theo hệ số, thêm liên tiếp nhiều đơn vị có chi phí **khấu hao** `O(1)` cho mỗi đơn vị.
- Chèn một đơn vị vào đầu hoặc giữa vẫn có thể tốn `O(n)` vì phải dời phần tử phía sau.

Khác biệt quan trọng là `length` nói về dữ liệu đang có, còn `capacity` nói về bộ nhớ đã đặt trước. Không được đọc phần chưa thuộc chuỗi như thể đó là nội dung hợp lệ.

### 3.4. Gap buffer: tối ưu sửa gần con trỏ

**Gap buffer** giữ một khoảng trống ngay tại vị trí chỉnh sửa:

```text
Chuỗi logic:  "abXYcd"
Vùng nhớ:    [a][b][_][_][_][X][Y][c][d]
                   ^ khoảng trống
```

Ký hiệu trong bộ nhớ nằm hai phía của gap; thứ tự logic được khôi phục bằng cách bỏ qua khoảng trống. Bất biến là `0 ≤ gapStart ≤ gapEnd ≤ capacity`; chiều dài logic bằng `capacity - (gapEnd - gapStart)` nếu toàn bộ phần ngoài gap đều là dữ liệu.

Chèn gần gap có thể chỉ mất `O(k)` để ghi `k` đơn vị; đưa gap sang nơi khác phải dịch chuyển các phần tử qua gap, mất `O(d)` với `d` là khoảng cách di chuyển. Vì vậy, gap buffer phù hợp với thao tác gõ liên tục gần vị trí con trỏ, nhưng không tối ưu cho nhiều điểm sửa cách xa nhau.

### 3.5. Rope: chuỗi gồm nhiều mảnh trên cây

**Rope** lưu chuỗi bằng các đoạn (leaf) và nút cây; các nút trong có thể giữ tổng độ dài của cây con để hỗ trợ tìm vị trí:

```text
              (độ dài 11)
               /        \
          "Hello"       " World"
```

Hình minh họa là một cây có hai lá; rope lớn hơn có thể phân chia thành nhiều tầng. Nếu cây **được duy trì cân bằng** và có metadata độ dài phù hợp, tìm vị trí, tách hoặc nối có thể thực hiện theo đường đi cao `O(log p)` với `p` là số mảnh/nút liên quan, cộng phần việc trên mảnh bị sửa. Những phép nối chỉ tạo nút mới mà không tái cân bằng có thể làm cây suy biến, khiến thao tác sau đó chậm hơn.

Rope hữu ích với văn bản lớn, chỉnh sửa nhiều và cần chia sẻ các đoạn cũ giữa các phiên bản. Chi phí đi kèm là nhiều con trỏ/nút, khả năng truy cập cache kém hơn mảng liên tiếp và logic quản lý cây phức tạp hơn.

### 3.6. Piece table: giữ bản gốc và nhật ký phần thêm

**Piece table** thường gồm bộ đệm gốc chỉ đọc, bộ đệm chỉ nối thêm, và danh sách/cây các mô tả mảnh `(nguồn, vị trí bắt đầu, độ dài)`:

```text
original: "Hello world"
add:      "brave "
pieces:   (original, 0, 6)
          (add,      0, 6)
          (original, 6, 5)
logic:    "Hello brave world"
```

Thao tác chèn chủ yếu ghi văn bản mới vào bộ đệm `add`, sau đó cập nhật mô tả các mảnh; không cần chép lại toàn bộ bản gốc. Chi phí tìm vị trí phụ thuộc vào cách lưu các mảnh: duyệt danh sách có thể là `O(p)`, trong khi cây cân bằng có tổng độ dài cây con có thể đạt `O(log p)` để định vị. Piece table phù hợp cho trình soạn thảo muốn hỗ trợ undo/redo và giữ dữ liệu gốc ít thay đổi, nhưng phải quản lý số mảnh và độ phức tạp của bộ chỉ mục.

### 3.7. View/slice chia sẻ bộ nhớ

Một **view** có thể chỉ lưu `(tham chiếu bộ đệm, offset, length)` để biểu diễn đoạn con mà không sao chép dữ liệu, tạo mô tả trong `O(1)` sau khi đã biết offset vật lý. Nếu sao chép đoạn con dài `k` đơn vị thì cần `O(k)` thời gian và bộ nhớ mới.

View phải có giới hạn hợp lệ và cơ chế bảo đảm dữ liệu gốc còn sống; nếu bộ đệm gốc có thể bị sửa, view còn cần quy định rõ kết quả khi nội dung thay đổi. Giữ một view rất nhỏ nhưng tham chiếu tới vùng nhớ gốc rất lớn cũng có thể làm vùng nhớ đó không được giải phóng.

## 4. So sánh chi phí thao tác

Đặt `n` là số **đơn vị lưu trữ** của chuỗi hiện tại, `m` là số đơn vị được nối/thêm, `k` là số đơn vị của đoạn cần lấy, `d` là khoảng cách chuyển con trỏ trong gap buffer, và `p` là số mảnh trong cấu trúc phân mảnh. Các độ phức tạp dưới đây nói về truy cập theo đơn vị mà cấu trúc đã đánh chỉ số (byte, code unit hoặc code point), **không tự động** bao gồm chi phí tách grapheme cluster Unicode.

| Thao tác | Mảng liên tiếp bất biến | Bộ đệm động | Gap buffer | Rope/piece table có chỉ mục cân bằng |
|---|---|---|---|---|
| Lấy độ dài đã lưu | `O(1)` | `O(1)` | `O(1)` | `O(1)` nếu giữ tổng độ dài |
| Đọc vị trí đã đánh chỉ số | `O(1)` | `O(1)` | `O(1)` với phép đổi chỉ số qua gap | Thường `O(log p)` |
| Nối hoặc thêm `m` đơn vị ở cuối | Tạo mới `O(n + m)` | Khấu hao `O(m)` khi tăng theo hệ số | `O(d + m)` nếu phải đưa gap tới cuối | Phụ thuộc cây/mảnh và cân bằng, thường gần `O(log p + m)` |
| Chèn `m` đơn vị vào giữa | Tạo mới `O(n + m)` | `O(n + m)` trong trường hợp xấu | `O(d + m)` | Khoảng `O(log p + m)` với cấu trúc phù hợp |
| Lấy đoạn có sao chép dài `k` | `O(k)` | `O(k)` | `O(k)` | `O(log p + k)` khi phải thu thập các mảnh |
| Duyệt hết chuỗi | `O(n)` | `O(n)` | `O(n)` | `O(n + p)` theo triển khai |

Đây là **ước lượng theo thiết kế**, không phải cam kết cố định của mọi thư viện. Ví dụ, `String.length` có thể là `O(1)` nếu metadata đã lưu, trong khi `strlen` của chuỗi kết thúc bằng NUL phải quét `O(n)`. Với UTF-8 không có chỉ mục code point bổ trợ, lấy *code point thứ i* bằng cách giải mã từ đầu thường mất `O(i)`; lấy *byte thứ i* vẫn là `O(1)`. Nếu hệ thống cần truy cập theo grapheme cluster, có thể phải làm thêm bước phân đoạn theo quy tắc Unicode.

## 5. Ví dụ: cùng đầu ra, khác chi phí xây dựng chuỗi

Giả sử chương trình cần xây câu từ nhiều đoạn. Với chuỗi bất biến, cách cộng dồn liên tục có thể làm các tiền tố trước đó bị sao chép nhiều lần:

```python
parts = ["Cấu", " ", "trúc", " ", "dữ", " ", "liệu"]

# Có thể tốn tổng O(N^2) với nhiều đoạn nhỏ nếu mỗi lần nối sao chép tiền tố.
result = ""
for part in parts:
    result += part

# Ghép một lần từ các đoạn: tổng công việc xấp xỉ O(N).
result = "".join(parts)
print(result)  # Cấu trúc dữ liệu
```

Ở đây `N` là tổng số đơn vị của tất cả các đoạn. Với `k` đoạn độ dài gần bằng nhau, nếu mỗi lần nối phải sao chép toàn bộ kết quả trước đó, tổng số phần tử được sao chép tăng như `1 + 2 + ... + k = O(k²)`. Một số runtime tối ưu phép `+=` trong trường hợp cụ thể; với thuật toán cần hiệu năng ổn định, hãy chọn cơ chế xây dựng chuỗi theo hợp đồng rõ ràng, chẳng hạn bộ đệm động hoặc phép `join`.

Ví dụ khác cho thấy sự khác nhau giữa chỉ số logic và byte vật lý:

```python
s = "Aé🙂"
raw = s.encode("utf-8")

print(len(s))          # 3 code point
print(len(raw))        # 7 byte
print(s[2])           # 🙂
print(raw[2])         # 169 (0xA9), byte tiếp diễn của é
print(list(raw))      # [65, 195, 169, 240, 159, 153, 130]
```

Lưu ý: `raw[2]` là số `169` (`0xA9`), **không phải** ký hiệu Unicode thứ ba. Nếu đặt con trỏ byte ngay giữa chuỗi byte mã hóa của một code point rồi cố giải mã như đầu ký tự, phép giải mã có thể thất bại. Các thư viện xử lý UTF-8 phải tôn trọng ranh giới mã hóa.

## 6. Chuỗi văn bản và dãy bit: liên quan nhưng khác mức trừu tượng

Dãy bit cũng là một chuỗi theo nghĩa toán học với bảng ký hiệu `Σ = {0, 1}`. Khi lưu dãy bit dài `n`, có thể dành một byte cho mỗi bit để đơn giản hóa thao tác, hoặc **đóng gói** tám bit vào một byte và dùng khoảng `ceil(n / 8)` byte, chưa tính metadata. Với quy ước bit thấp nhất trước, bit tại chỉ số `i` được truy cập qua:

```text
byte_index = i // 8
bit_offset = i % 8
value = (buffer[byte_index] >> bit_offset) & 1
```

Bất biến cần lưu là `0 ≤ i < bitLength` và `bitLength ≤ 8 * số_byte_đã_cấp_phát`. Các bit đệm ở byte cuối không thuộc dãy logic nếu độ dài không chia hết cho 8. Thứ tự bit trong byte phải được quy định thống nhất khi ghi/đọc dữ liệu.

**Mã hóa văn bản thành bit** là ánh xạ từ ký hiệu Unicode sang byte rồi sang bit. Dãy bit chứa các byte mã hóa không còn được thao tác như dãy ký hiệu Unicode nếu chưa giải mã; một phép cắt theo vị trí bit/byte tùy ý có thể phá vỡ một code point UTF-8.

## 7. Chọn biểu diễn theo bài toán

| Tình huống | Lựa chọn đáng cân nhắc | Lý do chính |
|---|---|---|
| Tên khóa cấu hình, mã định danh và giá trị ít sửa | Chuỗi bất biến, dạng liên tiếp | Dễ so sánh, chia sẻ, dùng làm khóa; duyệt và truy cập đơn vị lưu trữ nhanh. |
| Ghép log, tạo tài liệu từ nhiều phần nhỏ | Bộ đệm động hoặc builder/join | Giảm số lần sao chép tiền tố và số lần cấp phát. |
| Soạn thảo văn bản quanh một vị trí con trỏ | Gap buffer | Chèn/xóa gần gap thuận lợi. |
| Tài liệu lớn, chỉnh sửa nhiều vị trí, chia sẻ phiên bản | Rope hoặc piece table có chỉ mục | Tránh phải sao chép toàn bộ dữ liệu mỗi lần sửa. |
| Trích nhiều đoạn con mà vẫn giữ nguồn | View/slice với quản lý vòng đời rõ ràng | Có thể giảm chi phí sao chép; cần cân nhắc giữ bộ nhớ nguồn. |
| Trạng thái bật/tắt số lượng lớn | Bitset/dãy bit đóng gói | Tốn ít bộ nhớ hơn một byte cho mỗi cờ. |

Khi thiết kế API, hãy trả lời lần lượt: dữ liệu là văn bản hay byte/bit tùy ý; `length` đếm đơn vị nào; có cần sửa thường xuyên không; truy cập ngẫu nhiên hay chủ yếu duyệt tuần tự; chi phí bộ nhớ, sao chép và vòng đời dữ liệu được ưu tiên ra sao. Một cấu trúc phù hợp với mẫu thao tác cụ thể thường hiệu quả hơn cấu trúc có một thao tác lý tưởng nhưng làm các thao tác khác đắt đỏ.

### Những lỗi thiết kế dễ gặp

1. **Đồng nhất byte với ký tự.** Cắt `n` byte đầu của UTF-8 không bảo đảm thu được `n` code point, càng không bảo đảm `n` ký tự hiển thị.
2. **Quên đơn vị đo độ dài.** Một API trả về số UTF-16 code unit trong khi API khác cần số byte UTF-8; dùng chung chỉ số dễ gây lỗi biên.
3. **Nhầm chi phí khấu hao với chi phí từng lần.** Thêm cuối bộ đệm động thường nhanh, nhưng lần tăng dung lượng có thể phải sao chép toàn bộ nội dung.
4. **Dùng mảng liên tiếp cho hàng loạt chèn giữa.** Mỗi lần dịch chuyển có thể là `O(n)`; cần xem xét gap buffer hoặc cấu trúc phân mảnh.
5. **Bỏ qua bất biến và vòng đời.** View có offset sai, chuỗi NUL thiếu ký hiệu kết thúc, hoặc rope chứa độ dài cây con không khớp đều dẫn đến kết quả sai hoặc lỗi bộ nhớ.

## 8. Tự kiểm tra

**Câu 1.** Chuỗi `"Aé🙂"` có bao nhiêu byte UTF-8 và bao nhiêu code point? Vì sao hai con số khác nhau?

**Đáp án:** 7 byte UTF-8 và 3 code point, vì UTF-8 mã hóa các code point bằng số byte biến thiên.

**Câu 2.** Một trình soạn thảo chủ yếu nhận thao tác gõ gần con trỏ. Vì sao gap buffer có thể phù hợp hơn việc tạo một chuỗi bất biến mới sau mỗi phím?

**Đáp án:** Gap buffer để sẵn vùng trống gần con trỏ, giúp ghi thêm phần tử mà ít phải sao chép cả chuỗi; chỉ khi di chuyển con trỏ xa mới cần dời gap đáng kể.

**Câu 3.** Một chương trình lưu 1 triệu cờ boolean. Dãy bit đóng gói cần khoảng bao nhiêu byte cho chính các bit, chưa tính metadata?

**Đáp án:** `ceil(1_000_000 / 8) = 125_000` byte, vì một byte chứa tối đa tám cờ.

**Câu 4.** Có thể kết luận truy cập code point thứ `i` trong chuỗi UTF-8 luôn `O(1)` chỉ vì bytes được lưu trong mảng không?

**Đáp án:** Không. Mảng bảo đảm truy cập **byte** tại offset đã biết trong `O(1)`; muốn tìm offset của code point thứ `i` cần giải mã từ điểm đã biết hoặc dùng chỉ mục bổ trợ. Chi phí phụ thuộc cách triển khai.

## Ghi nhớ

Chuỗi là **dãy ký hiệu có thứ tự**; bộ nhớ chỉ là cách hiện thực dãy đó. Khi đánh giá một biểu diễn, luôn nêu rõ đơn vị của `length` và chỉ số, bất biến lưu trữ, và tập thao tác cần tối ưu. Chuỗi liên tiếp đơn giản và hiệu quả cho đọc tuần tự; bộ đệm động tốt cho xây dựng dần; gap buffer, rope và piece table xử lý những kiểu chỉnh sửa khác nhau. Với Unicode, byte, code unit, code point và ký tự hiển thị là những khái niệm cần phân biệt để lập luận đúng cả về tính chính xác lẫn độ phức tạp.
