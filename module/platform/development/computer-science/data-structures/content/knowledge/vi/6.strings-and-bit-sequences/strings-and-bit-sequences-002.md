# Phân biệt byte, đơn vị mã, điểm mã Unicode và ký tự hiển thị

Một chuỗi văn bản có thể trông rất ngắn trên màn hình nhưng gồm nhiều byte trong bộ nhớ. Chẳng hạn, ký hiệu `é`, biểu tượng `🙂` và lá cờ `🇻🇳` có độ dài khác nhau tùy đơn vị đếm. Nếu dùng nhầm đơn vị, chương trình có thể cắt hỏng dữ liệu, đặt con trỏ sai vị trí, kiểm tra giới hạn nhập liệu thiếu chính xác hoặc đánh giá sai chi phí thuật toán.

Trong chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, việc phân biệt các đơn vị này tạo nền tảng để thiết kế cấu trúc dữ liệu và API xử lý văn bản. Người học cần nắm **bất biến biểu diễn**, thao tác hợp lệ và độ phức tạp thời gian/bộ nhớ khi chuyển giữa dạng byte, đơn vị mã, điểm mã Unicode và ký tự hiển thị.

## 1. Bốn khái niệm ở bốn mức trừu tượng

| Đơn vị | Nó biểu diễn điều gì? | Dùng khi nào? | Điều dễ nhầm |
|---|---|---|---|
| **Byte** | Nhóm 8 bit lưu trữ/truyền tải dữ liệu | Kích thước tệp, bộ đệm, truyền mạng, offset vật lý | Một byte không nhất thiết là một ký tự |
| **Code unit (đơn vị mã)** | Đơn vị cơ bản của một dạng mã hóa Unicode: 8 bit ở UTF-8, 16 bit ở UTF-16, 32 bit ở UTF-32 | Chỉ số của một số API chuỗi, bố trí bộ nhớ | Một code point có thể cần nhiều code unit |
| **Code point (điểm mã)** | Một vị trí mang số trong không gian mã Unicode, thường viết `U+XXXX` | Phân tích ký hiệu Unicode, phân loại chữ, chuẩn hóa | Một code point không nhất thiết là một ký tự người dùng nhìn thấy |
| **Grapheme cluster (cụm ký tự hiển thị)** | Một nhóm code point mà quy tắc phân đoạn văn bản thường coi là một ký tự để di chuyển con trỏ/chọn văn bản | Giao diện nhập liệu, giới hạn ký tự hiển thị, xóa theo phím Backspace | Một cụm có thể chứa nhiều code point và nhiều glyph |

Có thể hình dung quá trình xử lý văn bản theo các lớp:

```text
Byte trên thiết bị / đường truyền
       │ giải mã UTF-8, UTF-16, ...
       ▼
Các code point Unicode
       │ phân đoạn grapheme theo quy tắc Unicode
       ▼
Các grapheme cluster (đơn vị thao tác văn bản)
       │ hệ thống định hình chữ + phông + bố cục
       ▼
Các glyph được vẽ trên màn hình
```

**Không phải mọi lớp có quan hệ 1–1**. Một code point có thể chiếm nhiều byte; một grapheme cluster có thể chứa nhiều code point; cách vẽ chữ có thể dùng một hoặc nhiều glyph cho một cụm. Do đó cần chọn đơn vị rõ ràng trước khi nói “độ dài 5” hoặc “ký tự thứ 3”.

## 2. Byte: đơn vị lưu trữ, không phải đơn vị ngôn ngữ

Một byte gồm 8 bit, có 256 tổ hợp giá trị từ `0x00` đến `0xFF`. Với văn bản ASCII, một ký hiệu ASCII chiếm đúng một byte trong UTF-8. Điều đó không đúng cho toàn bộ Unicode.

Xem ví dụ ký tự `é` trong UTF-8:

```text
Điểm mã:        U+00E9
Byte UTF-8:     C3       A9
Dãy bit:        11000011 10101001
                └── byte 1 └── byte 2
```

Hai byte trên **cùng mã hóa một code point**. Byte `A9` đứng riêng lẻ là một byte tiếp diễn UTF-8, không phải một ký tự có thể giải mã độc lập. Việc cắt một chuỗi byte ở vị trí bất kỳ có thể tạo ra dãy UTF-8 không hợp lệ.

Một lưu ý thực tế: byte không nói trước dữ liệu là văn bản. Dãy byte có thể là hình ảnh, tệp nén, giao thức hoặc một chuỗi ở bất kỳ bảng mã nào. Chỉ khi có **quy ước mã hóa** (như UTF-8) mới có thể giải mã byte thành văn bản đúng nghĩa.

## 3. Code unit: phụ thuộc dạng mã hóa UTF

Unicode định nghĩa các code point; UTF-8, UTF-16 và UTF-32 là những **dạng mã hóa** để biểu diễn các giá trị Unicode bằng code unit.

| Dạng mã hóa | Kích thước một code unit | Số code unit cho một Unicode scalar value | Nhận xét |
|---|---:|---:|---|
| **UTF-8** | 8 bit = 1 byte | 1–4 | Tương thích ASCII cho `U+0000` đến `U+007F`; có độ rộng biến thiên |
| **UTF-16** | 16 bit = 2 byte | 1 hoặc 2 | Một số code point phải dùng cặp surrogate |
| **UTF-32** | 32 bit = 4 byte | 1 | Độ rộng cố định theo scalar value, nhưng tốn 4 byte mỗi đơn vị |

*Unicode scalar value* là code point ngoại trừ dải surrogate `U+D800`–`U+DFFF`. Các giá trị surrogate dành riêng cho cơ chế UTF-16 và không phải ký hiệu Unicode độc lập có thể mã hóa hợp lệ bằng UTF-8. Một số API chuỗi vẫn có thể chứa **surrogate lẻ** nên cần phân biệt dữ liệu trong bộ nhớ với văn bản Unicode hợp lệ.

### UTF-8: từ 1 đến 4 code unit

UTF-8 nhận biết độ dài mã hóa nhờ mẫu bit đầu mỗi byte:

```text
1 byte:   0xxxxxxx
2 byte:   110xxxxx 10xxxxxx
3 byte:   1110xxxx 10xxxxxx 10xxxxxx
4 byte:   11110xxx 10xxxxxx 10xxxxxx 10xxxxxx
```

Mẫu bit giúp bộ giải mã xác định vị trí các điểm mã, nhưng một dãy có mẫu bit gần đúng chưa chắc hợp lệ: bộ giải mã còn phải loại mã hóa dài hơn mức cần thiết, code point surrogate và giá trị vượt `U+10FFFF`.

Ví dụ các byte UTF-8:

| Ký hiệu | Code point | Byte UTF-8 hệ 16 | Số byte |
|---|---|---|---:|
| `A` | `U+0041` | `41` | 1 |
| `é` | `U+00E9` | `C3 A9` | 2 |
| `中` | `U+4E2D` | `E4 B8 AD` | 3 |
| `🙂` | `U+1F642` | `F0 9F 99 82` | 4 |

Đối với bộ đệm UTF-8 dài `B` byte, lấy byte thứ `i` tại offset hợp lệ là thao tác trên mảng và thường `O(1)`. Tuy nhiên tìm **code point thứ i** phải tìm được ranh giới code point, thường đòi hỏi giải mã từ một vị trí đã biết hoặc dùng chỉ mục bổ trợ.

### UTF-16: code unit 16 bit và cặp surrogate

Các code point từ `U+0000` đến `U+FFFF` (trừ surrogate) được biểu diễn bằng một code unit UTF-16. Các scalar value lớn hơn `U+FFFF` được biểu diễn bằng **hai** code unit, gọi là surrogate pair.

Ví dụ ký hiệu `🙂` (`U+1F642`) trong UTF-16:

```text
Code point:     U+1F642
Code units:     D83D DE42
                └──┬───┘
                  2 code unit (4 byte)
```

Khi lưu thành byte, thứ tự byte của mỗi code unit 16 bit còn phụ thuộc UTF-16BE hoặc UTF-16LE. Vì vậy **UTF-16 code unit** và **byte** là hai đơn vị khác nhau; không thể dùng chỉ số byte như chỉ số code unit nếu không có phép chuyển đổi rõ ràng.

### UTF-32: đơn giản về vị trí, đắt hơn về bộ nhớ

Với dãy scalar value hợp lệ được lưu liên tiếp bằng UTF-32, code point thứ `i` tương ứng code unit 32 bit thứ `i`. Tìm code point theo chỉ số vật lý có thể `O(1)` và dễ tính offset. Đổi lại cần tối thiểu 4 byte cho mỗi scalar value, chưa kể bộ nhớ quản lý. UTF-32 **không** khiến một grapheme cluster luôn chiếm một đơn vị: một chữ có dấu ghép hoặc emoji kết hợp vẫn gồm nhiều code point.

## 4. Code point: giá trị Unicode, không đồng nghĩa với “chữ”

Mỗi code point được ký hiệu bằng tiền tố `U+` và giá trị hệ 16:

- `U+0041` là chữ `A`.
- `U+00E9` là chữ `é` dạng dựng sẵn (precomposed).
- `U+0065` là chữ `e`; `U+0301` là dấu sắc kết hợp (combining acute accent).
- `U+1F642` là emoji `🙂`.
- `U+200D` là ký tự nối độ rộng bằng không (zero-width joiner, ZWJ).

Một chữ có thể dùng **một code point dựng sẵn** hoặc **nhiều code point kết hợp**. Hai dãy dưới đây thường hiển thị gần như giống hệt nhau:

```text
Dạng dựng sẵn:
  "é"       = [U+00E9]                 → 1 code point

Dạng phân rã:
  "e\u0301"  = [U+0065, U+0301]         → 2 code point
                e      dấu sắc
```

Hai chuỗi không giống nhau nếu so sánh từng code point hoặc từng byte. Unicode cung cấp các dạng **chuẩn hóa** để xử lý nhiều trường hợp tương đương; ví dụ NFC có thể gộp cặp `e` + dấu sắc thành `é` dựng sẵn.

Các code point còn bao gồm dấu kết hợp, ký tự điều khiển, ký tự định dạng và nhiều ký hiệu không trực tiếp tạo thành một chữ độc lập. Ngược lại, một ký tự người dùng nhận thấy có thể tạo từ nhiều code point.

## 5. Grapheme cluster: đơn vị hợp lý cho nhiều thao tác giao diện

**Grapheme cluster** là đơn vị phân đoạn được Unicode quy định (thường là *extended grapheme cluster* trong các API hiện đại). Nó gần với khái niệm “một ký tự nhìn thấy” hơn code point, nhưng vẫn chỉ là **quy tắc phân đoạn văn bản**, không phải cam kết về số glyph, độ rộng trên màn hình hoặc cảm nhận giống nhau trong mọi ngôn ngữ.

Một số mẫu thường gặp:

- `e\u0301`: chữ `e` và dấu sắc kết hợp thường tạo **một** grapheme cluster dù gồm **hai** code point.
- `🇻🇳`: lá cờ Việt Nam là **hai** code point thuộc nhóm regional indicator, nhưng thường là **một** grapheme cluster.
- `👩🏽‍💻`: emoji gồm người phụ nữ, dấu bổ sung màu da, ZWJ và máy tính; thường là **một** grapheme cluster, gồm **bốn** code point.
- Một ký tự có thể trải trên nhiều vị trí ký tự in terminal hoặc hiển thị khác nhau tùy phông, thiết bị và cách định hình chữ.

Bảng so sánh, dùng UTF-8 và UTF-16 hợp lệ với cách phân đoạn grapheme Unicode hiện đại:

| Văn bản | Byte UTF-8 | Code unit UTF-8 | Code unit UTF-16 | Code point | Grapheme cluster |
|---|---:|---:|---:|---:|---:|
| `A` | 1 | 1 | 1 | 1 | 1 |
| `é` (dựng sẵn) | 2 | 2 | 1 | 1 | 1 |
| `e\u0301` (phân rã) | 3 | 3 | 2 | 2 | 1 |
| `🙂` | 4 | 4 | 2 | 1 | 1 |
| `🇻🇳` | 8 | 8 | 4 | 2 | 1 |
| `👩🏽‍💻` | 15 | 15 | 7 | 4 | 1 |

**Kiểm tra bảng:** UTF-8 có code unit 8 bit nên số **code unit UTF-8 bằng số byte UTF-8**. Điều đó không đúng khi chuyển sang UTF-16; ký hiệu `🙂` có 4 byte UTF-8 nhưng chỉ 2 code unit UTF-16. Code point và grapheme lại là hai phép đếm khác nữa.

### Grapheme không phải glyph

*Glyph* là hình dạng do bộ máy vẽ chữ chọn để hiển thị văn bản. Một grapheme cluster không bảo đảm vẽ thành đúng một glyph: dấu và chữ có thể dùng nhiều glyph, các chữ cái có thể tạo ligature, và phông chữ có thể thiếu glyph để hiển thị. Bởi vậy **số grapheme**, **số glyph** và **chiều rộng hiển thị** cần ba cơ chế riêng khi sản phẩm có yêu cầu cụ thể.

## 6. Các ngôn ngữ và API thực tế đang đếm đơn vị nào?

Tên thuộc tính `length` hoặc phép truy cập `s[i]` không tự nói rõ loại đơn vị. Hãy đọc hợp đồng API thay vì suy diễn từ từ “string”.

### Python: `str` theo code point, `bytes` theo byte

```python
import unicodedata

text = "Aé🙂"
raw = text.encode("utf-8")

print(len(text))                  # 3: code point
print(len(raw))                   # 7: byte
print(list(raw))                  # [65, 195, 169, 240, 159, 153, 130]
print(text[2])                    # 🙂
print(raw[2])                     # 169 (0xA9), chỉ là byte của é

composed = "é"                    # U+00E9
decomposed = "e\u0301"            # U+0065 + U+0301

print(len(composed))              # 1 code point
print(len(decomposed))            # 2 code point
print(composed == decomposed)     # False
print(unicodedata.normalize("NFC", decomposed) == composed)
# True trong ví dụ này
```

`len(str)` trong Python đếm code point; **không** trực tiếp đếm grapheme cluster. Nếu người dùng gõ `e` rồi thêm dấu sắc kết hợp, giới hạn nhập “10 ký tự” dựa trên `len` có thể không tương ứng với 10 ký tự hiển thị.

### JavaScript: `length` và `slice` theo UTF-16 code unit

```javascript
const text = "Aé🙂";

console.log(text.length);              // 4 code unit UTF-16
console.log(Array.from(text).length);  // 3 code point
console.log([...text]);                // ["A", "é", "🙂"]

const emoji = "🙂";
console.log(emoji.length);             // 2
console.log(emoji.slice(0, 1).length); // 1: chỉ một surrogate
console.log(emoji.slice(0, 1) === emoji); // false
```

`Array.from(string)` duyệt các code point mà bộ lặp chuỗi JavaScript cung cấp, **không** tự ghép các code point thành grapheme cluster. Với chuỗi chứa surrogate lẻ, JavaScript vẫn có thể lưu code unit đó; nhiều phép mã hóa văn bản sẽ cần xử lý hay thay thế giá trị không hợp lệ.

Đếm grapheme cluster trong môi trường JavaScript hỗ trợ `Intl.Segmenter`:

```javascript
function graphemeCount(text) {
  const segmenter = new Intl.Segmenter("vi", {
    granularity: "grapheme",
  });
  return Array.from(segmenter.segment(text)).length;
}

const s = "e\u0301🙂🇻🇳";
console.log(s.length);                 // 8 code unit UTF-16
console.log(Array.from(s).length);     // 5 code point
console.log(graphemeCount(s));         // 3 grapheme cluster
```

Trong ví dụ, `e\u0301` chiếm 2 code unit, `🙂` chiếm 2 và `🇻🇳` chiếm 4, tổng là **8**. Số code point là 2 + 1 + 2 = **5**; số grapheme cluster là **3**. Việc phân đoạn chịu ảnh hưởng của phiên bản dữ liệu/quy tắc Unicode mà môi trường hỗ trợ.

### Java: `String.length()` theo UTF-16 code unit

```java
String s = "Aé🙂";

System.out.println(s.length());                // 4 code unit
System.out.println(s.codePointCount(0, s.length())); // 3 code point
System.out.println(s.codePointAt(2));          // 128578 = U+1F642
```

Các API tiêu chuẩn trả về đơn vị khác nhau ngay trong cùng một ngôn ngữ. Ví dụ trên minh họa vì sao việc đặt tên biến như `byteOffset`, `codeUnitIndex`, `codePointIndex` hay `graphemeIndex` giúp tránh lẫn lộn.

## 7. Những lỗi thường gặp khi đếm và cắt chuỗi

### Lỗi 1: cắt giữa một chuỗi byte UTF-8

```python
encoded = "é".encode("utf-8")         # b'\xc3\xa9'
print(encoded[:1])                    # b'\xc3'
# encoded[:1].decode("utf-8")         # UnicodeDecodeError (strict)
```

Dữ liệu cắt ra không chứa đủ các byte cho một code point. Khi phải cắt UTF-8 theo giới hạn byte, cần tìm **ranh giới code point hợp lệ** trước khi giải mã. Nếu muốn bảo toàn ký tự hiển thị, còn phải cắt theo ranh giới grapheme.

### Lỗi 2: cắt một surrogate pair UTF-16

```javascript
const full = "🙂";
const broken = full.slice(0, 1);
console.log(broken.length);  // 1 code unit
console.log(broken === full); // false
```

`slice(0, 1)` cắt theo code unit UTF-16 nên có thể để lại surrogate lẻ. Chọn theo code point sẽ tránh cắt đôi một surrogate pair hợp lệ, nhưng vẫn **có thể** cắt giữa `e` và dấu kết hợp, hoặc giữa các code point cấu thành emoji.

### Lỗi 3: coi chuẩn hóa là so sánh theo ngôn ngữ

`NFC` có thể khiến hai cách mã hóa của `é` trở thành cùng dãy code point, nhưng không giải quyết mọi yêu cầu so sánh văn bản. So sánh bỏ qua hoa/thường, sắp xếp theo tiếng Việt, ký tự gần giống nhau về hình dạng và nhận diện tên người cần quy tắc riêng. Dạng chuẩn hóa tương thích như `NFKC` có thể thay đổi khác biệt ký tự mà ứng dụng muốn giữ lại; chỉ áp dụng khi hợp đồng dữ liệu yêu cầu.

### Lỗi 4: áp dụng giới hạn “ký tự” nhưng không nêu đơn vị

Giả sử biểu mẫu cho phép nhập “tối đa 20 ký tự”. Hệ thống phải quyết định đó là:

1. **20 byte UTF-8:** phù hợp khi giới hạn từ giao thức hoặc dung lượng lưu trữ.
2. **20 code point:** phù hợp với một số quy tắc xử lý Unicode xác định.
3. **20 grapheme cluster:** thường dễ hiểu hơn cho yêu cầu giao diện liên quan tới ký tự người dùng nhìn thấy.

Các giới hạn có thể cần **đồng thời**: kiểm tra số grapheme cho giao diện và số byte sau mã hóa để đáp ứng kích thước trường dữ liệu. Không nên thay đổi đơn vị ngầm giữa client, server và cơ sở dữ liệu.

## 8. Bất biến dữ liệu và độ phức tạp

Gọi `B` là số byte mã hóa, `U` là số code unit, `P` là số code point và `G` là số grapheme cluster. Những đại lượng này có quan hệ nhưng không bằng nhau trong trường hợp tổng quát.

| Tác vụ | Đơn vị và cách làm | Chi phí thường gặp |
|---|---|---|
| Lấy byte ở vị trí `i` của mảng byte | Chỉ số byte, có kiểm tra `0 ≤ i < B` | `O(1)` |
| Lấy code unit ở vị trí `i` trong mảng UTF-16 | Chỉ số code unit, có kiểm tra `0 ≤ i < U` | `O(1)` |
| Đếm code point từ byte UTF-8 chưa có chỉ mục | Giải mã toàn bộ các code point hợp lệ | `O(B)` thời gian |
| Tìm offset byte của code point thứ `i` trong UTF-8 không có chỉ mục | Duyệt tuần tự từ điểm đã biết | `O(i)` theo số code point đã duyệt |
| Đếm grapheme cluster của văn bản chưa được phân đoạn | Phân đoạn Unicode trên chuỗi | Thường tuyến tính theo chiều dài đầu vào, `O(P)` với mô hình triển khai tuần tự thông dụng |
| Truy cập grapheme thứ `i` nhiều lần | Lưu chỉ mục ranh giới grapheme bổ trợ | Có thể truy cập nhanh hơn, đổi lấy thêm bộ nhớ/công cập nhật khi chỉnh sửa |

Bảng là mô hình chi phí phổ biến; runtime có thể giữ metadata hoặc chỉ mục bổ sung. Ví dụ chuỗi bất biến có lưu sẵn độ dài code unit sẽ đọc `length` trong `O(1)`, trong khi phép đếm code point trên dữ liệu UTF-8 không có chỉ mục thường phải quét.

Khi thiết kế cấu trúc lưu văn bản, cần bảo đảm những bất biến sau:

- **Đơn vị chỉ số nhất quán.** Một biến offset được xác định là byte, code unit, code point hoặc grapheme và chỉ được chuyển đổi bằng thao tác rõ ràng.
- **Giới hạn hợp lệ.** Với lát cắt `[start, end)` luôn có `0 ≤ start ≤ end ≤ length` theo đúng loại đơn vị đang dùng.
- **Ranh giới giải mã hợp lệ.** Không bắt đầu giải mã UTF-8 từ byte tiếp diễn hoặc coi một surrogate lẻ là scalar value hợp lệ.
- **Metadata được cập nhật cùng nội dung.** Nếu lưu sẵn số code point, số grapheme hoặc bảng offset, cần tính lại hoặc điều chỉnh sau khi văn bản bị sửa.
- **Chính sách xử lý dữ liệu lỗi rõ ràng.** Từ chối, thay thế hoặc báo lỗi giải mã UTF không hợp lệ theo hợp đồng API; không âm thầm coi mọi byte là ký tự.

Chuyển sang chỉ mục grapheme không phải lúc nào cũng tối ưu: nếu chỉ đọc/ghi tệp, dùng offset byte là tự nhiên; nếu cần tìm code point Unicode, cần quan tâm đến điểm mã; nếu làm trình soạn thảo, chọn vùng hoặc di chuyển con trỏ, grapheme thường là đơn vị thích hợp hơn.

## 9. Tình huống thiết kế: trường tên, con trỏ và giới hạn lưu trữ

Một ứng dụng lưu tên hiển thị bằng UTF-8, cho phép tối đa 30 ký tự người dùng nhìn thấy và cơ sở dữ liệu chỉ nhận tối đa 128 byte. Người dùng nhập cả tiếng Việt có dấu và emoji.

Một thiết kế có thể gồm:

1. Nhận văn bản Unicode và xác định chính sách chuẩn hóa (nếu cần) ngay tại biên xử lý.
2. Dùng bộ phân đoạn grapheme phù hợp để kiểm tra tối đa 30 **grapheme cluster** cho giới hạn giao diện.
3. Mã hóa UTF-8 để kiểm tra tối đa 128 **byte** cho giới hạn lưu trữ.
4. Khi cắt hoặc xóa theo vị trí con trỏ, dùng ranh giới grapheme; khi ghi tệp hoặc gửi mạng, dùng byte của bản mã hóa cuối cùng.
5. Nếu lưu chỉ mục con trỏ bằng byte, chuyển đổi sang ranh giới grapheme hợp lệ trước khi thao tác; làm mới chỉ mục sau khi nội dung thay đổi.

Ví dụ một tên có 25 grapheme vẫn có thể vượt 128 byte nếu chứa nhiều emoji hoặc các tổ hợp code point. Ngược lại, một tên ASCII gồm 30 chữ chỉ cần 30 byte UTF-8. Cả hai điều kiện phải được kiểm tra độc lập để đảm bảo yêu cầu của ứng dụng.

## 10. Tự kiểm tra

**Câu 1.** Tại sao ký tự `🙂` chiếm bốn byte UTF-8 nhưng `"🙂".length` trong JavaScript trả về 2?

**Gợi ý trả lời:** `🙂` là một code point `U+1F642`, được mã hóa bằng bốn code unit 8 bit trong UTF-8 hoặc hai code unit 16 bit trong UTF-16. `String.length` của JavaScript đếm UTF-16 code unit.

**Câu 2.** `"é"` và `"e\u0301"` nhìn giống nhau. Chúng có bao nhiêu code point và bao nhiêu grapheme cluster?

**Gợi ý trả lời:** Dạng dựng sẵn có 1 code point; dạng phân rã có 2 code point. Mỗi dạng thường được phân đoạn thành 1 grapheme cluster. Chúng có thể trở thành cùng dãy code point sau chuẩn hóa NFC.

**Câu 3.** Cắt một UTF-8 buffer ở byte thứ 100 có chắc vẫn tạo văn bản hợp lệ không?

**Gợi ý trả lời:** Không. Byte thứ 100 có thể nằm giữa nhiều byte mã hóa một code point. Cần cắt ở ranh giới mã hóa hợp lệ; nếu yêu cầu cắt theo ký tự hiển thị, cần thêm ranh giới grapheme.

**Câu 4.** Một trình soạn thảo văn bản nên xóa một byte, một code unit, một code point hay một grapheme cluster khi người dùng nhấn Backspace?

**Gợi ý trả lời:** Thông thường nên xóa theo **grapheme cluster** để tránh làm sót dấu kết hợp hoặc cắt đôi emoji. Quy tắc điều hướng và xóa thực tế còn phụ thuộc ngôn ngữ và hành vi của trình soạn thảo.

**Câu 5.** Tại sao thêm chỉ mục theo code point hoặc grapheme có thể cải thiện tốc độ truy cập vị trí trong UTF-8, và phải trả giá gì?

**Gợi ý trả lời:** Chỉ mục lưu offset byte của các ranh giới đã tính, giúp tránh quét lại từ đầu trong nhiều lần truy cập. Đổi lại tốn bộ nhớ và phải duy trì tính đúng đắn của metadata khi chuỗi bị sửa.

## Ghi nhớ

- **Byte** là đơn vị lưu trữ; **code unit** là đơn vị của dạng mã hóa; **code point** là giá trị Unicode; **grapheme cluster** là đơn vị phân đoạn gần với ký tự người dùng nhìn thấy.
- UTF-8, UTF-16 và UTF-32 biểu diễn cùng văn bản Unicode bằng những chuỗi code unit khác nhau; code unit không nhất thiết tương ứng 1–1 với code point.
- Một grapheme cluster có thể chứa nhiều code point, và số grapheme không bảo đảm bằng số glyph hoặc số ô hiển thị.
- Đọc hợp đồng `length`, `index` và `slice` của từng API; ghi rõ đơn vị cho mọi offset và giới hạn.
- Chọn đơn vị dựa trên bài toán: **byte** cho lưu trữ/giao thức, **code point** cho xử lý giá trị Unicode, **grapheme** cho nhiều thao tác giao diện văn bản.
