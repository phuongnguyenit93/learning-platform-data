# Độ dài và truy cập ký tự phụ thuộc vào cách mã hóa

Khi lập trình, ta dễ viết `length(s)` hoặc `s[i]` và cho rằng kết quả là số “ký tự” hoặc “ký tự thứ `i`”. Cách hiểu đó chỉ đúng sau khi biết rõ **đơn vị mà API sử dụng** và **dạng mã hóa/lưu trữ**. Một ký hiệu hiển thị có thể chiếm nhiều byte, nhiều đơn vị mã, thậm chí nhiều điểm mã Unicode. Sự khác biệt này quyết định cả tính chính xác lẫn độ phức tạp của thuật toán.

Bài thuộc chương **Chuỗi và dãy bit** trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là xây dựng tư duy cấu trúc dữ liệu: chỉ rõ bất biến của chỉ số, phân tích thao tác `length` và truy cập theo từng biểu diễn, biết khi nào cần quét tuần tự, lưu chỉ mục phụ hoặc chọn cấu trúc chuỗi khác. Những kỹ năng này giúp lựa chọn cấu trúc phù hợp theo thời gian và bộ nhớ, tương tự khi lựa chọn mảng, danh sách liên kết, bảng băm, cây, heap hay đồ thị.

## 1. Một chuỗi có nhiều khái niệm “độ dài”

Xét chuỗi văn bản:

```text
Aé🙂é
```

Ở đây phần cuối là chữ `e` theo sau bởi **dấu sắc kết hợp** `U+0301`. Trong tài liệu hoặc phông khác nhau, cách hiển thị dấu sắc có thể hơi khác, nhưng dãy code point không thay đổi.

Bốn đơn vị thường gặp là:

| Đơn vị | Định nghĩa | Độ dài của ví dụ |
|---|---|---:|
| **Byte** | Mỗi đơn vị lưu trữ 8 bit trong một dãy byte mã hóa | 10 byte với UTF-8 |
| **Code unit** | Đơn vị mã hóa 8 bit trong UTF-8, 16 bit trong UTF-16, 32 bit trong UTF-32 | UTF-8: 10; UTF-16: 6; UTF-32: 5 |
| **Code point** | Một giá trị Unicode, ví dụ `U+00E9` hoặc `U+1F642` | 5 |
| **Grapheme cluster** | Một cụm mà thuật toán phân đoạn Unicode thường coi như một ký tự dùng trong giao diện | 4 |

Ví dụ có **5 code point**: `A`, `é`, `🙂`, `e` và dấu sắc kết hợp. Tuy nhiên, `e` và dấu sắc thuộc **cùng một grapheme cluster**, nên số cụm hiển thị là 4 theo quy tắc phân đoạn Unicode hiện đại.

Không nên dùng “độ dài” khi chưa định nghĩa rõ đơn vị. Trong thiết kế API, các tên như `byteLength`, `codeUnitLength`, `codePointCount` và `graphemeCount` giảm nguy cơ nhầm lẫn hơn một thuộc tính `length` không có hợp đồng cụ thể.

### Mô hình toán học

Nếu xem chuỗi là dãy ký hiệu `S = (s₀, s₁, …, sₙ₋₁)` thì `n` là số phần tử của dãy **theo bảng ký hiệu đã chọn**. Nếu phần tử là byte, `n` là số byte. Nếu phần tử là Unicode code point, `n` là số code point. Đây là hai dãy trừu tượng khác nhau, dù cùng mô tả một văn bản sau khi giải mã.

Với một chuỗi gồm `P` Unicode scalar value hợp lệ:

- UTF-8 cần từ `P` đến `4P` byte để mã hóa các scalar value đó.
- UTF-16 cần từ `P` đến `2P` code unit 16 bit.
- UTF-32 cần đúng `P` code unit 32 bit.

Các bất đẳng thức trên giả định chỉ xét các scalar value hợp lệ, không tính byte-order mark hoặc metadata của đối tượng chuỗi. **Không thể suy ra số grapheme cluster chỉ từ `P`**, vì một grapheme có thể có nhiều code point.

## 2. Cùng văn bản, các offset khác nhau

Chuỗi `Aé🙂e\u0301` có dữ liệu theo các lớp như sau.

### Theo UTF-8

```text
Offset byte:    0    1    2    3    4    5    6    7    8    9
Byte (hex):    41   C3   A9   F0   9F   99   82   65   CC   81
               └A┘  └──é──┘  └─────🙂──────┘  └e┘  └dấu sắc┘
```

Các **offset bắt đầu code point** là `0, 1, 3, 7, 8`; offset kết thúc chuỗi là `10`. Nếu cần truy cập theo **grapheme cluster**, các ranh giới là `0, 1, 3, 7, 10`. Dấu sắc ở hai byte cuối thuộc cùng grapheme với `e`, vì thế offset byte 8 là ranh giới code point nhưng **không** phải ranh giới grapheme.

### Theo UTF-16

```text
Chỉ số code unit:   0      1      2      3      4      5
Giá trị (hex):     0041   00E9   D83D   DE42   0065   0301
                    A      é      └──🙂──┘   e    dấu sắc
```

`🙂` mã hóa thành cặp surrogate `D83D DE42`, vì vậy nó chiếm hai code unit UTF-16. Chỉ số `2` trỏ vào **high surrogate**, không phải một code point Unicode độc lập; cần đọc cả cặp mới có code point `U+1F642`.

### Theo code point và grapheme

| Vị trí logic | Code point | Grapheme cluster |
|---:|---|---|
| 0 | `A` | `A` |
| 1 | `é` | `é` |
| 2 | `🙂` | `🙂` |
| 3 | `e` | `e\u0301` |
| 4 | Dấu sắc kết hợp `U+0301` | Không có grapheme mới |

Như vậy “phần tử thứ 4” (chỉ số 3 tính từ 0) có thể là byte `F0`/`99` tùy biểu diễn và vị trí, một code point `e`, hoặc một grapheme `e\u0301`. Cần nói rõ **vừa loại chỉ số vừa hệ quy chiếu**.

### Bảng độ dài vật lý

| Biểu diễn | Số đơn vị | Dung lượng dữ liệu thuần |
|---|---:|---:|
| UTF-8 | 10 code unit × 1 byte | 10 byte |
| UTF-16 | 6 code unit × 2 byte | 12 byte |
| UTF-32 | 5 code unit × 4 byte | 20 byte |

Đây chỉ là số byte của dữ liệu mã hóa, chưa bao gồm metadata của đối tượng chuỗi, terminator, dự phòng dung lượng hoặc chỉ mục phụ. Dạng mã hóa tiết kiệm nhất **phụ thuộc nội dung**: với một chuỗi thiên về ASCII, UTF-8 thường tiết kiệm hơn; điều đó không có nghĩa UTF-8 luôn ít bộ nhớ nhất cho mọi văn bản.

## 3. Độ dài trong API: giá trị có sẵn hay phải tính?

Độ phức tạp của thao tác lấy độ dài không chỉ phụ thuộc dạng mã hóa mà còn phụ thuộc **cách cấu trúc lưu metadata**.

### Trường hợp 1: lưu sẵn độ dài

Một chuỗi có thể là đối tượng chứa:

```text
String {
    buffer
    byteLength
    optionalCodePointCount
    optionalGraphemeCount
}
```

Đọc trường `byteLength` đã có là `O(1)`. Tương tự, nếu số code point được giữ sẵn và cập nhật đúng mỗi khi sửa chuỗi, truy vấn `codePointCount` có thể `O(1)`. Tuy nhiên, duy trì metadata bổ sung tốn bộ nhớ hoặc công cập nhật khi chèn, xóa, thay thế.

### Trường hợp 2: phải quét dữ liệu

Với một bộ đệm UTF-8 chỉ biết số byte `B`, muốn biết có bao nhiêu code point phải giải mã hoặc kiểm tra ranh giới mã hóa trên dãy. Một lần quét có thời gian `O(B)`. Nếu chỉ cần đếm, có thể giữ bộ đếm và trạng thái bộ giải mã với bộ nhớ phụ `O(1)`, không nhất thiết tạo chuỗi Unicode mới.

Tương tự, với UTF-16 biết `U` code unit, đếm code point của chuỗi hợp lệ phải phân biệt cặp surrogate và các code unit đơn; duyệt mất `O(U)` trong trường hợp tổng quát nếu không có số đếm sẵn.

**Đếm grapheme cluster** yêu cầu áp dụng quy tắc phân đoạn Unicode. Trong thao tác duyệt tuần tự phổ biến, chi phí tỷ lệ với lượng dữ liệu đã xem; tuy nhiên thuật toán và trạng thái cụ thể quyết định giới hạn chính xác. Không được coi `graphemeCount` là `O(1)` chỉ vì `byteLength` hoặc `codeUnitLength` đã được lưu.

### Ví dụ Python

Python `str` cung cấp `len` theo số code point trong các chuỗi thông thường; `bytes` cung cấp số byte.

```python
text = "Aé🙂e\u0301"
raw = text.encode("utf-8")

print(len(text))              # 5 code point
print(len(raw))               # 10 byte
print(text[3])                # "e"
print(text[4])                # dấu sắc kết hợp, không phải một chữ mới

print(raw[3])                 # 240 = 0xF0, byte đầu của 🙂
print(raw[4])                 # 159 = 0x9F, byte tiếp diễn
```

Trong CPython, `len(str)` và truy cập một code point bằng chỉ số hợp lệ là `O(1)` nhờ biểu diễn chuỗi bên trong; điều này **không suy ra** rằng truy cập code point trong một **bộ đệm UTF-8 thuần** cũng `O(1)`. Phải xét chính cấu trúc lưu trữ mà chương trình đang dùng.

### Ví dụ JavaScript

JavaScript công bố `String.length` theo **UTF-16 code unit**, còn bộ lặp chuỗi (`for...of`) xử lý các code point theo quy tắc của ngôn ngữ.

```javascript
const text = "Aé🙂e\u0301";

console.log(text.length);             // 6 code unit UTF-16
console.log([...text].length);        // 5 code point
console.log(text[2]);                 // high surrogate của 🙂
console.log(text.codePointAt(2));     // 128578 = U+1F642

let count = 0;
for (const codePoint of text) count++;
console.log(count);                   // 5
```

`[...text]` tạo một mảng mới nên cần thêm bộ nhớ tỷ lệ với số phần tử; vòng lặp `for...of` dùng bộ đếm có thể tránh cấp phát mảng đó. Khi chuỗi lớn, cách đếm là một lựa chọn về **thời gian và bộ nhớ**, không chỉ cú pháp.

### Ví dụ Java

```java
String s = "Aé🙂e\u0301";

System.out.println(s.length());                 // 6 UTF-16 code unit
System.out.println(s.codePointCount(0, s.length())); // 5 code point
System.out.println(s.codePointAt(2));           // 128578 = U+1F642
```

`String.length()` lấy số code unit; `codePointCount` đếm code point trong vùng đã chọn. Nếu ứng dụng cần truy cập code point thứ `i`, hãy chú ý sự khác nhau giữa **offset code unit** và **thứ tự code point**: `codePointAt(2)` nhận chỉ số code unit, không phải “code point thứ 2” nói chung.

## 4. Vì sao truy cập theo chỉ số có độ phức tạp khác nhau?

### Mảng có đơn vị rộng cố định

Với mảng `a` có phần tử rộng `w` byte và địa chỉ bắt đầu `base`:

```text
address(a[i]) = base + i × w
```

Nếu `0 ≤ i < length`, địa chỉ phần tử có thể tính trực tiếp trong `O(1)`. Điều này đúng cho **byte thứ i** trong mảng byte, **code unit thứ i** trong mảng UTF-16 và **code unit thứ i** trong mảng UTF-32.

Khi các code point hợp lệ đều có độ rộng cố định một code unit UTF-32, code point thứ `i` có cùng chỉ số với code unit thứ `i`. Điều đó hỗ trợ truy cập code point `O(1)` trên mảng UTF-32 liên tiếp. Nhưng nếu hỏi “grapheme thứ i”, việc các code point rộng cố định vẫn chưa đủ, vì mỗi grapheme có thể chứa số code point khác nhau.

### UTF-8: từ chỉ số code point phải tìm offset byte

Giả sử dữ liệu UTF-8 hợp lệ nằm trong `buffer`. Muốn lấy **code point thứ i** mà không có bảng chỉ mục, ta cần xác định nơi bắt đầu của nó:

```text
offset = 0
repeat i times:
    width = number_of_utf8_bytes_at(buffer, offset)
    offset = offset + width

return decode_one_code_point(buffer, offset)
```

Đây là **giả mã**: hàm xác định độ rộng và hàm giải mã phải kiểm tra ranh giới, tính hợp lệ và tình huống vượt cuối bộ đệm khi triển khai thực tế. Với đầu vào hợp lệ và chỉ số `i` nằm trong phạm vi, mỗi lượt nhảy qua tối đa 4 byte, nên việc tìm offset mất `O(i)` thời gian và `O(1)` bộ nhớ phụ.

Nếu đã biết **byte offset đầu một code point**, việc giải mã code point tại vị trí ấy chỉ xét tối đa 4 byte UTF-8, có thể coi là `O(1)`. Vì vậy vấn đề khó nằm ở **chuyển chỉ số code point thành offset byte**, không phải ở việc giải mã một code point đơn lẻ.

Đối với UTF-8, phép `buffer[i]` trên mảng byte luôn trả về **byte thứ i**, có thể là byte tiếp diễn `10xxxxxx`. Không được coi mọi vị trí byte là ranh giới ký tự.

### UTF-16: biết chỉ số code unit chưa phải biết chỉ số code point

Một code point Unicode ở mặt phẳng cơ bản có thể được mã hóa bằng một code unit UTF-16; một code point ngoài mặt phẳng cơ bản cần **hai code unit (surrogate pair)**.

Khi đã biết chỉ số code unit `j`, đọc code unit `j` là `O(1)`, và tìm code point bắt đầu tại `j` có thể chỉ cần xem code unit liền kề. Tuy nhiên, nếu đầu vào là “**code point thứ i**” thì phải tính được bao nhiêu surrogate pair nằm trước nó. Không có chỉ mục hoặc metadata bổ trợ, việc đó đòi hỏi quét các code unit đi trước, thường `O(i)` theo số code point đã đi qua.

Hai kiểu API rất dễ bị nhầm:

- `codeUnitAt(j)`: nhận chỉ số code unit vật lý.
- `codePointAtCodeUnitOffset(j)`: giải mã code point từ offset code unit đã biết.
- `codePointAtOrdinal(i)`: lấy code point thứ `i` trong chuỗi logic, phải định vị offset trước.

Ngay cả khi thư viện chỉ cung cấp một tên phương thức, thiết kế của ứng dụng nên xác định rõ nó nhận loại offset nào.

### Grapheme: còn phụ thuộc quy tắc phân đoạn

Với chuỗi Unicode `e\u0301`, truy cập code point thứ 0 lấy `e`; code point thứ 1 là dấu sắc; nhưng truy cập **grapheme thứ 0** phải trả về cả `e\u0301`. Cần nhận biết ranh giới cụm theo quy tắc Unicode.

Việc tìm grapheme thứ `i` thường phải phân đoạn văn bản tới cụm đó hoặc tra một chỉ mục ranh giới grapheme được xây dựng trước. Khi lưu chỉ mục, vẫn phải quan tâm tới việc **sửa văn bản có thể thay đổi ranh giới cụm ở vùng lân cận**, thậm chí thay đổi cách phân nhóm các ký hiệu nối tiếp nhau.

## 5. Bảng tổng hợp độ phức tạp

Ký hiệu:

- `B`: số byte UTF-8; `U`: số code unit UTF-16; `P`: số Unicode code point; `G`: số grapheme cluster.
- `i`: thứ tự phần tử cần truy cập, tính từ 0 theo đơn vị mà thao tác yêu cầu.
- Giả định mảng liên tiếp và dữ liệu Unicode hợp lệ; trừ khi ghi rõ, **chưa có chỉ mục phụ**.

| Thao tác | UTF-8 liên tiếp | UTF-16 liên tiếp | UTF-32 liên tiếp |
|---|---|---|---|
| Đọc code unit thứ `i` | `O(1)` (cũng là byte thứ `i`) | `O(1)` | `O(1)` |
| Đọc code point từ **offset code unit hợp lệ đã biết** | `O(1)`, tối đa 4 byte | `O(1)`, tối đa 2 code unit | `O(1)` |
| Truy cập **code point thứ `i`** | `O(i)` nếu quét từ đầu | `O(i)` nếu quét từ đầu | `O(1)` |
| Đếm toàn bộ code point nếu chưa lưu kết quả | `O(B)` | `O(U)` | `O(1)` nếu có số code unit |
| Đếm byte dữ liệu mã hóa | `O(1)` nếu lưu `B` | `O(1)` nếu lưu số unit và không tính metadata khác | `O(1)` nếu lưu số unit |
| Đếm grapheme cluster | Cần phân đoạn Unicode | Cần phân đoạn Unicode | Cần phân đoạn Unicode |

Các giá trị `O(i)` là chi phí định vị qua tối đa `i` code point trước vị trí đích, chưa tính riêng xử lý lỗi. Thao tác đếm code point cũng có thể đạt `O(1)` **nếu lưu sẵn số đếm**; khi đó các phép thay đổi dữ liệu phải duy trì metadata. Với UTF-32, giả định một scalar value hợp lệ ứng với đúng một code unit.

Với grapheme, không nên tự gán `O(1)` hoặc `O(log n)` nếu chưa mô tả cấu trúc chỉ mục và cách cập nhật. Thao tác phân đoạn một chuỗi chưa có chỉ mục thường dựa trên duyệt dữ liệu; chi phí thực tế phụ thuộc thuật toán và phiên bản quy tắc Unicode.

## 6. Chỉ mục phụ: đổi bộ nhớ lấy tốc độ truy cập

Nếu ứng dụng liên tục hỏi “code point thứ `i` trong bộ đệm UTF-8 nằm tại byte nào?”, quét lại từ đầu mỗi lần có thể tốn kém. Một số giải pháp:

### 6.1. Bảng offset đầy đủ

Với ví dụ `Aé🙂e\u0301`, có thể xây:

```text
codePointOrdinal:   0   1   2   3   4   (sentinel)
byteOffset:         0   1   3   7   8      10
```

Bảng chứa offset đầu của từng code point. Sau khi xây trong `O(B)` thời gian, tìm offset của phần tử thứ `i` mất `O(1)`. Bộ nhớ phụ `O(P)` số nguyên (kích thước số nguyên tùy giới hạn dữ liệu). Mọi thao tác chèn/xóa trước một đoạn có thể khiến nhiều offset phía sau cần cập nhật.

### 6.2. Checkpoint thưa

Thay vì lưu offset của **mọi** code point, lưu offset của code point thứ `0, k, 2k, 3k, ...`.

Để tìm code point thứ `i`:

1. Tìm checkpoint có thứ tự `j = floor(i / k) × k`.
2. Lấy offset byte từ bảng tại `j`.
3. Giải mã tuần tự tối đa `k - 1` code point tiếp theo.

Nếu `k` cố định và bảng checkpoint truy cập ngẫu nhiên, truy vấn tốn `O(k)`, còn bảng cần khoảng `O(P / k)` offset. Chi phí xây ban đầu vẫn `O(B)`. Đây là một cách thực tế để đánh đổi thời gian truy cập và bộ nhớ.

### 6.3. Cấu trúc phân mảnh có metadata tổng hợp

Đối với tài liệu lớn, có thể lưu văn bản dưới dạng **rope** hoặc cây các mảnh. Mỗi nút giữ số byte, code point hoặc grapheme của cây con để dẫn hướng tới vùng cần tìm.

Nếu cây cân bằng và metadata chính xác, việc xác định mảnh chứa phần tử có thể mất `O(log p)` với `p` số mảnh, rồi truy cập trong mảnh theo cấu trúc cục bộ. Tuy nhiên, **đếm grapheme không luôn cộng được như đếm byte**: ranh giới cụm có thể thay đổi khi nối hai mảnh. Cấu trúc phải xử lý ngữ cảnh phân đoạn qua ranh giới hoặc áp dụng cơ chế cập nhật/phân đoạn bổ sung.

Ví dụ:

```text
Số grapheme của "e"       = 1
Số grapheme của "\u0301"  = 1
Số grapheme của "e\u0301" = 1, không phải 2
```

Tương tự, `"\r"` và `"\n"` đứng riêng mỗi chuỗi có một grapheme, nhưng `"\r\n"` là một grapheme cluster theo quy tắc phân đoạn tương ứng. Vì vậy, tổng số grapheme sau nối chuỗi **không nhất thiết bằng tổng số grapheme riêng lẻ**.

## 7. Biến đổi chỉ số và những bất biến cần giữ

Hãy phân biệt hai loại thông tin:

- **Chỉ số logic:** “code point thứ 10” hoặc “grapheme thứ 10”, gắn với đơn vị mà thuật toán định nghĩa.
- **Offset vật lý:** vị trí byte/code unit trong bộ đệm mã hóa.

Chuyển từ chỉ số logic sang offset vật lý phụ thuộc dạng mã hóa và chỉ mục. Sau khi sửa văn bản, offset có thể thay đổi ngay cả khi vị trí logic của một cụm nhìn giống như trước.

### Bất biến cho vùng cắt `[start, end)`

1. `0 ≤ start ≤ end ≤ length` phải đúng **theo một đơn vị xác định**.
2. Nếu cắt byte UTF-8 để tạo chuỗi UTF-8 hợp lệ, hai đầu phải ở **ranh giới code point hợp lệ**.
3. Nếu cắt để giao diện hiển thị trọn ký tự, hai đầu cần ở **ranh giới grapheme cluster**.
4. Nếu cắt UTF-16, không được tách một **surrogate pair** khi kết quả phải là chuỗi Unicode hợp lệ.
5. Mọi bảng offset hoặc metadata số lượng phải được làm mới khi dữ liệu thay đổi; không dùng index cũ với version mới của văn bản.

Chuẩn hóa Unicode cũng là một phép biến đổi dữ liệu. Ví dụ NFC có thể đổi `"e\u0301"` (hai code point, ba byte UTF-8) thành `"é"` (một code point, hai byte UTF-8). Nội dung có thể hiển thị giống nhau nhưng **offset, số byte và số code point** thay đổi. Vì vậy không thể áp dụng lại offset đã lưu trước chuẩn hóa mà không tính lại.

### Quy tắc thực hành

Đừng đặt tên một biến chung chung là `position` nếu nó sẽ chuyển qua nhiều tầng xử lý. Đặt tên `byteOffset`, `utf16Offset`, `codePointIndex` hoặc `graphemeIndex`, và tập trung phép chuyển đổi vào một API có điều kiện biên rõ ràng.

## 8. Bài tập lập trình: truy cập đúng theo mục đích

### Bài 1. Byte offset trong Python

Đoạn mã dưới đây minh họa một cách rõ ràng để tìm byte offset của code point thứ `i`, khi chuỗi đầu vào đã là `str` và Python có thể truy cập code point:

```python
def utf8_offset_of_code_point(text: str, i: int) -> int:
    if not 0 <= i <= len(text):
        raise IndexError("code-point index out of range")
    return len(text[:i].encode("utf-8"))

s = "Aé🙂e\u0301"

print(utf8_offset_of_code_point(s, 0))  # 0
print(utf8_offset_of_code_point(s, 1))  # 1
print(utf8_offset_of_code_point(s, 2))  # 3
print(utf8_offset_of_code_point(s, 3))  # 7
print(utf8_offset_of_code_point(s, 4))  # 8
print(utf8_offset_of_code_point(s, 5))  # 10
```

Cách này dễ hiểu nhưng phải tạo lát cắt và mã hóa tiền tố, nên mỗi lần gọi tốn công tỷ lệ với độ dài tiền tố (và cấp phát dữ liệu trung gian). Nếu có hàng nghìn truy vấn trên một chuỗi không đổi, một bảng offset xây một lần thường phù hợp hơn.

### Bài 2. Đếm grapheme trong JavaScript

Môi trường JavaScript có `Intl.Segmenter` cho phép lấy các ranh giới grapheme:

```javascript
const s = "Aé🙂e\u0301";
const seg = new Intl.Segmenter("vi", {
  granularity: "grapheme",
});

const clusters = [...seg.segment(s)].map(item => ({
  text: item.segment,
  utf16Offset: item.index,
}));

console.log(s.length);           // 6 UTF-16 code unit
console.log([...s].length);      // 5 code point
console.log(clusters.length);    // 4 grapheme cluster
console.log(clusters.map(x => x.utf16Offset)); // [0, 1, 2, 4]
```

`item.index` là offset **UTF-16 code unit** của phần tử trong chuỗi đầu vào, không phải byte offset UTF-8. Nếu truyền offset đó sang API byte mà không chuyển đổi, kết quả có thể sai.

Phân đoạn grapheme chịu ảnh hưởng quy tắc và dữ liệu Unicode được runtime hỗ trợ; vì vậy ứng dụng có yêu cầu đồng nhất nghiêm ngặt giữa client/server cần kiểm soát phiên bản thư viện và kiểm thử những trường hợp kết hợp phức tạp.

### Bài 3. Chọn cách kiểm tra giới hạn

Giả sử một API chỉ nhận tối đa 64 byte UTF-8 nhưng giao diện cho phép nhập tối đa 20 grapheme cluster.

- Dùng **UTF-8 byte length** để kiểm tra giới hạn 64 byte sau khi áp dụng chính sách chuẩn hóa (nếu có).
- Dùng **grapheme segmentation** để kiểm tra giới hạn 20 ký tự hiển thị theo quy tắc giao diện.
- Duy trì hai giới hạn độc lập. Một đoạn emoji dài 20 grapheme có thể vượt 64 byte; một đoạn ASCII dài 20 ký tự thường chỉ dùng 20 byte UTF-8.

## 9. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi `buffer[i]` của UTF-8 là code point thứ `i` | Đọc byte tiếp diễn, sai ký tự hoặc giải mã lỗi | Giải mã hoặc dùng bảng ranh giới code point |
| Coi `String.length` của JavaScript là số ký tự hiển thị | Đếm emoji surrogate pair thành 2 và dấu kết hợp thành đơn vị riêng | Xác định yêu cầu và dùng phân đoạn grapheme nếu cần |
| Cắt theo offset UTF-16 rồi giải mã/gửi như UTF-8 | Nhầm đơn vị chỉ số và có thể tách surrogate pair | Chuyển offset qua API được định nghĩa rõ |
| Tin rằng `O(1)` truy cập mảng đồng nghĩa `O(1)` truy cập mọi ký tự | Đánh giá thấp chi phí quét UTF-8 | Phân biệt code unit, code point và grapheme |
| Giữ bảng offset khi văn bản đã sửa/chuẩn hóa | Offset trỏ vào vùng sai | Invalidate/cập nhật chỉ mục theo phiên bản dữ liệu |
| Lấy tổng số grapheme của các mảnh để suy ra tổng sau nối | Sai ở ranh giới có dấu kết hợp, emoji nối, CRLF… | Áp dụng quy tắc phân đoạn cho ranh giới liên quan |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Với chuỗi `Aé🙂e\u0301`, hãy nêu số byte UTF-8, số code unit UTF-16, số code point và số grapheme cluster.

**Đáp án:** Lần lượt **10, 6, 5 và 4**.

**Câu 2.** Trên mảng byte UTF-8, truy cập `buffer[4]` có độ phức tạp `O(1)`. Điều đó chứng minh lấy code point thứ tư cũng `O(1)` không?

**Đáp án:** Không. `buffer[4]` chỉ là byte tại offset 4 (trong ví dụ, byte `0x9F` của emoji). Để lấy code point thứ tư theo chỉ số logic cần xác định ranh giới code point, thường phải quét hoặc dùng chỉ mục.

**Câu 3.** Nếu chuỗi được lưu bằng UTF-32 hợp lệ, code point thứ `i` có thể truy cập trực tiếp trong `O(1)` không? Grapheme thứ `i` thì sao?

**Đáp án:** Code point có thể truy cập trực tiếp bằng code unit `i` trong mảng UTF-32. Grapheme có thể gồm nhiều code point nên vẫn cần quy tắc phân đoạn/chỉ mục bổ sung.

**Câu 4.** Vì sao chỉ cập nhật metadata số byte sau khi chèn văn bản là chưa đủ với một trình soạn thảo hỗ trợ con trỏ theo grapheme?

**Đáp án:** Các ranh giới grapheme và số cụm có thể thay đổi, nhất là ở vùng nối/chèn dấu kết hợp hoặc ký tự tạo chuỗi emoji. Chỉ mục grapheme phải được cập nhật theo cách phân đoạn thực tế.

**Câu 5.** Một bảng offset đầy đủ cho `P` code point trên UTF-8 có ưu điểm và chi phí gì?

**Đáp án:** Sau khi xây bảng trong `O(B)`, xác định byte offset của code point thứ `i` đạt `O(1)`. Đổi lại tốn `O(P)` bộ nhớ phụ và có chi phí duy trì offset sau chỉnh sửa văn bản.

## Ghi nhớ

- **Độ dài luôn gắn với đơn vị đếm**: byte, code unit, code point hoặc grapheme. Cùng một văn bản có thể có bốn số đo khác nhau.
- **Truy cập mảng `O(1)` chỉ bảo đảm với đơn vị vật lý mà mảng đang lưu**. Trong UTF-8 và UTF-16, thứ tự code point và offset code unit có thể khác nhau.
- Muốn lấy code point thứ `i` trong UTF-8 không có chỉ mục thường phải quét từ ranh giới đã biết; UTF-32 có thể truy cập code point trực tiếp nhưng không tự giải quyết truy cập grapheme.
- Metadata độ dài và bảng offset có thể tăng tốc truy vấn, đổi lại tốn bộ nhớ và công cập nhật khi dữ liệu thay đổi.
- Chọn đơn vị theo nhu cầu: byte để lưu trữ/truyền tải, code point để xử lý ký hiệu Unicode, grapheme để thao tác gần với ký tự người dùng nhìn thấy.
