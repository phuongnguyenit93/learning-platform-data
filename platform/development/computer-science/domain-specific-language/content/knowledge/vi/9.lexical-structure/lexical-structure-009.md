# Unicode và mã hóa

Ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL) thường phải xử lý tên khái niệm, từ khóa, chuỗi văn bản, chú thích và dữ liệu do người dùng nhập. Trong môi trường đa ngôn ngữ, những nội dung này có thể chứa tiếng Việt có dấu, chữ viết của nhiều hệ thống chữ, ký hiệu toán học hoặc emoji. Để đọc và xử lý chúng đúng, DSL cần có quy tắc rõ ràng về **Unicode** và **mã hóa ký tự**.

Unicode quy định cách gán mã cho các ký tự và đặc tính của chúng. UTF-8, UTF-16 và UTF-32 là những cách biểu diễn các giá trị Unicode thành đơn vị lưu trữ. Hai khái niệm này liên quan nhưng không giống nhau: Unicode xác định ký tự và mã của chúng; UTF xác định cách mã hóa các mã đó thành byte hoặc đơn vị mã.

Trong thiết kế DSL, lựa chọn mã hóa ảnh hưởng đến cách đọc tệp nguồn, phân tích từ vựng, so sánh tên, xử lý chuỗi, vị trí thông báo lỗi, khả năng tương tác và an toàn. Nếu các quy tắc này không được xác định từ đầu, cùng một văn bản có thể được hiểu khác nhau giữa trình soạn thảo, parser và runtime.

## 1. Unicode là gì?

Unicode là một tiêu chuẩn nhằm gán mã duy nhất cho các ký tự được dùng trong các hệ thống chữ viết và nhiều loại ký hiệu. Mỗi mã được viết theo dạng `U+` theo sau bởi các chữ số hệ 16, ví dụ `U+0041` là chữ Latin hoa A, `U+1EBF` là chữ ế viết sẵn, và `U+1F600` là một emoji mặt cười.

Unicode còn định nghĩa các thuộc tính ký tự như loại chữ, chữ hoa/chữ thường, dấu kết hợp, hướng hiển thị, khả năng dùng trong identifier và nhiều đặc tính khác. Những thuộc tính này giúp phần mềm xử lý văn bản theo quy tắc thay vì dựa vào hình dạng hiển thị.

### 1.1. Code point và Unicode scalar value

**Code point** là một vị trí trong không gian mã Unicode, được biểu diễn từ `U+0000` đến `U+10FFFF`. Không phải mọi code point đều là một ký tự Unicode hợp lệ để biểu diễn văn bản thông thường. Khoảng `U+D800` đến `U+DFFF` được dành cho surrogate trong UTF-16 và không phải Unicode scalar value.

**Unicode scalar value** là code point ngoại trừ vùng surrogate. Đây là đơn vị khái niệm hữu ích khi nói về một giá trị ký tự Unicode hợp lệ.

Ví dụ, chữ `ế` có thể được biểu diễn bằng một scalar value `U+1EBF`. Nhưng cùng hình thức văn bản cũng có thể được tạo từ nhiều scalar value: chữ `e` (`U+0065`) theo sau bởi dấu mũ kết hợp (`U+0302`) và dấu sắc kết hợp (`U+0301`). Hai chuỗi có thể hiển thị giống nhau nhưng chuỗi mã khác nhau.

### 1.2. Code point không đồng nghĩa với ký tự người dùng nhìn thấy

Một điều dễ gây nhầm lẫn là số code point không nhất thiết bằng số ký tự mà người dùng cảm nhận. Một ký tự hiển thị có thể gồm một code point hoặc nhiều code point kết hợp với nhau.

Các khái niệm cần phân biệt:

- **Byte:** đơn vị dữ liệu 8 bit thường dùng trong tệp và bộ nhớ.
- **Code unit:** đơn vị cơ bản của một dạng mã hóa, ví dụ 8 bit trong UTF-8 hoặc 16 bit trong UTF-16.
- **Code point:** vị trí mã trong không gian Unicode.
- **Grapheme cluster:** một chuỗi code point được hiển thị như một đơn vị ký tự mà người dùng thường nhận biết.

Ví dụ, `ế` có thể là một code point ở dạng dựng sẵn hoặc ba code point ở dạng phân rã. Emoji có thể gồm nhiều code point nối bằng ký tự ZWJ để tạo một hình ảnh duy nhất. Vì vậy, `length()` của chuỗi có thể đếm byte, code unit hoặc code point tùy ngôn ngữ; nó không nhất thiết đếm số ký tự hiển thị.

## 2. Mã hóa ký tự là gì?

Mã hóa ký tự (character encoding) là cách chuyển các giá trị ký tự thành chuỗi đơn vị lưu trữ để ghi vào tệp, truyền qua mạng hoặc lưu trong bộ nhớ. Máy tính lưu byte; muốn hiểu nội dung, chương trình cần biết cách diễn giải các byte đó.

Ví dụ, chữ `A` có code point `U+0041`. Trong UTF-8, nó được mã hóa thành một byte `41` hệ 16. Chữ `ế` (`U+1EBF`) được mã hóa thành nhiều byte trong UTF-8. Cùng một ký tự có thể có chuỗi byte khác nhau trong UTF-8, UTF-16 hoặc UTF-32.

Không nên nhầm mã hóa với font chữ. Encoding xác định cách byte biểu diễn văn bản; font quyết định hình dạng glyph khi hiển thị. Một văn bản có thể được giải mã đúng nhưng font thiếu glyph, khiến màn hình hiện ô vuông hoặc ký hiệu thay thế.

## 3. Các dạng mã hóa Unicode phổ biến

### 3.1. UTF-8

UTF-8 mã hóa một Unicode scalar value thành từ 1 đến 4 byte. Các ký tự ASCII có cùng byte với ASCII, nhờ đó UTF-8 tương thích tốt với nhiều giao thức và công cụ cũ. Các ký tự ngoài ASCII sử dụng nhiều byte hơn.

Đặc điểm chính:

- Dùng đơn vị byte 8 bit.
- Ký tự ASCII nằm trong khoảng `U+0000` đến `U+007F` được mã hóa bằng đúng một byte.
- Các scalar value khác dùng từ 2 đến 4 byte.
- Không cần byte order mark để xác định thứ tự byte vì mỗi đơn vị là một byte.
- Được dùng rộng rãi cho mã nguồn, tệp cấu hình và giao thức web.

UTF-8 thường là lựa chọn phù hợp cho tệp nguồn DSL vì hỗ trợ văn bản đa ngôn ngữ, tương thích ASCII và không phụ thuộc thứ tự byte. Tuy nhiên, parser phải giải mã UTF-8 theo chế độ nghiêm ngặt và xử lý rõ các chuỗi byte không hợp lệ.

### 3.2. UTF-16

UTF-16 biểu diễn văn bản bằng các code unit 16 bit. Một scalar value trong vùng cơ bản (BMP), ngoại trừ vùng surrogate, dùng một code unit. Các scalar value ngoài BMP dùng một cặp surrogate gồm hai code unit.

Ví dụ, một ký tự emoji ngoài BMP có thể chiếm hai code unit UTF-16. Vì vậy, độ dài chuỗi trong một số API dựa trên UTF-16 có thể lớn hơn số code point.

UTF-16 có hai thứ tự byte phổ biến là big-endian và little-endian. BOM có thể được dùng trong một số định dạng để chỉ thứ tự byte, nhưng cách nhận diện BOM phụ thuộc giao thức và định dạng tệp.

### 3.3. UTF-32

UTF-32 dùng một code unit 32 bit cho mỗi Unicode scalar value. Việc ánh xạ từ code unit sang scalar value đơn giản hơn so với UTF-8 hoặc UTF-16, nhưng dữ liệu thường chiếm nhiều dung lượng hơn. UTF-32 cũng có thể có thứ tự byte big-endian hoặc little-endian.

UTF-32 ít phổ biến hơn UTF-8 trong trao đổi tệp và mã nguồn. Một số runtime có thể dùng cách biểu diễn nội bộ khác với encoding của tệp, vì vậy không nên suy luận encoding đầu vào từ cách chuỗi được lưu trong bộ nhớ.

### 3.4. So sánh UTF-8, UTF-16 và UTF-32

| Tiêu chí | UTF-8 | UTF-16 | UTF-32 |
|---|---|---|---|
| Đơn vị mã | 8 bit | 16 bit | 32 bit |
| Độ dài mỗi scalar value | 1–4 byte | 1 hoặc 2 code unit | 1 code unit |
| Tương thích ASCII | Có | Không ở cấp byte | Không ở cấp byte |
| Thứ tự byte | Không cần chọn endian | Có thể big-endian hoặc little-endian | Có thể big-endian hoặc little-endian |
| Dung lượng | Hiệu quả với văn bản ASCII và nhiều nội dung phổ biến | Thường cân bằng giữa các nhóm ký tự | Thường lớn hơn |
| Sử dụng phổ biến | Tệp nguồn, web, giao thức | Một số API/runtime và hệ thống | Một số xử lý nội bộ chuyên biệt |

Ba dạng UTF có thể biểu diễn cùng một chuỗi Unicode. Chọn UTF-8 cho tệp nguồn không có nghĩa runtime bắt buộc lưu chuỗi dưới UTF-8; parser có thể giải mã thành dạng biểu diễn nội bộ khác.

## 4. Luồng xử lý văn bản trong DSL

Một trình biên dịch hoặc thông dịch DSL thường nhận nội dung tệp dưới dạng byte. Trước khi phân tích từ vựng, nó phải giải mã byte theo encoding đã quy định.

```text
Tệp nguồn (bytes)
      |
      v
Giải mã theo encoding đã chọn
      |
      v
Chuỗi Unicode
      |
      v
Lexer: nhận diện token và identifier
      |
      v
Parser: xây dựng cấu trúc cú pháp
      |
      v
Kiểm tra ngữ nghĩa và kiểu
      |
      v
Thực thi hoặc biên dịch DSL
```

Nếu giải mã sai, mọi bước phía sau có thể nhận nội dung sai. Ví dụ, một tệp UTF-8 bị đọc nhầm như một encoding đơn byte có thể biến tiếng Việt thành chuỗi ký tự lỗi. Lexer sau đó có thể không nhận ra identifier hoặc chuỗi đúng như người viết dự định.

Vì vậy, encoding phải được xác định trước khi lexer hoạt động. Không nên cố sửa văn bản lỗi bằng cách thay mọi byte không hợp lệ thành ký tự thay thế rồi tiếp tục phân tích mã nguồn, vì điều đó có thể biến một lỗi encoding thành một chương trình khác.

## 5. Chọn encoding cho tệp nguồn DSL

Một DSL nên công bố rõ encoding mặc định và cách xử lý tệp có encoding khác. Với phần lớn DSL hiện đại, quy định tệp nguồn là UTF-8 là lựa chọn đơn giản và tương thích rộng.

Chính sách encoding cần xác định:

- Tệp nguồn có bắt buộc UTF-8 không?
- Có chấp nhận UTF-8 BOM ở đầu tệp không?
- BOM có bị loại bỏ trước khi phân tích hay được xem là ký tự không hợp lệ?
- Byte sequence UTF-8 sai định dạng được báo lỗi thế nào?
- Có hỗ trợ UTF-16/UTF-32 hay không, và nếu có thì nhận diện encoding bằng cách nào?
- Công cụ formatter, IDE, compiler và runtime có dùng cùng chính sách không?

### 5.1. BOM (Byte Order Mark)

BOM là một dấu mã hóa có thể xuất hiện ở đầu tệp. Trong UTF-16 và UTF-32, nó có thể giúp xác định thứ tự byte. UTF-8 không cần BOM để xác định thứ tự byte, nhưng một số công cụ vẫn ghi ba byte BOM ở đầu tệp.

Với DSL dùng UTF-8, nên quy định rõ có chấp nhận BOM hay không. Nếu chấp nhận, parser thường nên nhận diện và bỏ BOM ở đầu tệp trước khi xử lý token đầu tiên. Nếu không chấp nhận, cần báo lỗi rõ thay vì để BOM làm ký tự lạ trước từ khóa đầu tiên.

Không nên loại bỏ ký tự U+FEFF ở mọi vị trí trong văn bản một cách mù quáng. Chính sách BOM thường chỉ áp dụng ở đầu tệp; ký tự tương tự xuất hiện trong nội dung cần được xử lý theo quy tắc Unicode và DSL.

### 5.2. Kết thúc dòng

Các hệ điều hành và công cụ có thể dùng `LF` (`U+000A`), `CRLF` (`U+000D U+000A`) hoặc đôi khi `CR` (`U+000D`) để kết thúc dòng. Lexer nên định nghĩa các dạng được chấp nhận và chuẩn hóa cách tính vị trí dòng.

Thông thường, DSL có thể chấp nhận cả LF và CRLF để hỗ trợ nhiều môi trường, trong khi formatter ghi ra một dạng chuẩn. Quy tắc này cần nhất quán để thông báo lỗi, diff và công cụ biên tập hoạt động dễ dự đoán.

## 6. Unicode normalization (chuẩn hóa Unicode)

Một ký tự hiển thị có thể được biểu diễn bằng nhiều chuỗi code point tương đương về mặt chuẩn tắc. **Unicode normalization** là quá trình biến chuỗi về một dạng chuẩn theo quy tắc Unicode.

Ví dụ tiếng Việt: chữ `ế` có thể được biểu diễn:

- Dạng dựng sẵn: `U+1EBF`.
- Dạng phân rã: `U+0065 U+0302 U+0301` (chữ e, dấu mũ kết hợp, dấu sắc kết hợp).

Hai chuỗi này có thể hiển thị giống nhau và được Unicode xem là tương đương chuẩn tắc, nhưng byte và dãy code point ban đầu khác nhau.

### 6.1. NFC và NFD

Unicode định nghĩa nhiều dạng chuẩn hóa. Hai dạng thường được nhắc đến là:

- **NFC (Normalization Form C):** phân rã chuẩn tắc rồi kết hợp lại khi có thể, thường tạo biểu diễn dựng sẵn.
- **NFD (Normalization Form D):** phân rã ký tự thành chuỗi thành phần theo chuẩn tắc.

Ví dụ minh họa bằng Python:

```python
import unicodedata

composed = "\u1EBF"
decomposed = "\u0065\u0302\u0301"

print(unicodedata.normalize("NFC", composed) ==
      unicodedata.normalize("NFC", decomposed))  # True
```

Kết quả cho thấy hai chuỗi có thể được chuẩn hóa về cùng một dạng NFC để so sánh. Đây là một vấn đề quan trọng khi identifier có thể được nhập từ nhiều trình soạn thảo hoặc nguồn dữ liệu khác nhau.

### 6.2. NFKC và NFKD

NFKC và NFKD thực hiện chuẩn hóa tương thích (compatibility normalization), ngoài phân rã chuẩn tắc còn có thể gộp các ký tự có quan hệ tương thích về một dạng chung. Việc này có thể làm mất một số khác biệt về trình bày hoặc ý nghĩa định dạng.

Không nên áp dụng NFKC một cách tự động cho mọi nội dung. Nó có thể hữu ích cho một số trường hợp so khớp identifier hoặc tìm kiếm, nhưng có thể làm thay đổi văn bản mà người dùng mong muốn giữ nguyên. Chọn dạng chuẩn hóa phải dựa trên mục đích của dữ liệu.

### 6.3. Chuẩn hóa identifier và chuỗi dữ liệu

Identifier dùng để tham chiếu cấu trúc trong DSL thường cần quy tắc so sánh ổn định. Một chính sách phổ biến là chuẩn hóa identifier về NFC trước khi lưu vào bảng ký hiệu hoặc so sánh tên. Parser cũng cần phát hiện hai tên khác chuỗi code point nhưng trở thành cùng tên sau chuẩn hóa.

Với nội dung chuỗi nghiệp vụ như tên người, địa chỉ hoặc ghi chú, không nên tự ý chuẩn hóa hay biến đổi nếu việc giữ nguyên dạng nhập có ý nghĩa. Có thể lưu dạng gốc và tạo dạng chuẩn riêng cho tìm kiếm hoặc so sánh nếu yêu cầu nghiệp vụ cho phép.

Chuẩn hóa Unicode không giải quyết mọi trường hợp hai chuỗi nhìn giống nhau. Những ký tự từ các hệ chữ khác nhau có thể trông gần như giống nhau nhưng không tương đương chuẩn tắc.

## 7. Unicode trong identifier của DSL

Identifier là tên dùng để đặt cho entity, thuộc tính, biến, quy tắc, hàm hoặc kiểu dữ liệu. Một DSL cần quyết định identifier có được chứa ký tự Unicode hay chỉ cho phép ASCII.

### 7.1. Chỉ dùng ASCII hay hỗ trợ Unicode?

Có hai hướng thiết kế phổ biến:

| Chính sách | Ưu điểm | Hạn chế |
|---|---|---|
| Identifier chỉ dùng ASCII | Đơn giản cho lexer, tìm kiếm, diff và kiểm tra bảo mật | Không thể dùng trực tiếp thuật ngữ có dấu hoặc chữ viết bản địa trong tên |
| Identifier hỗ trợ Unicode | Tự nhiên với người dùng nhiều ngôn ngữ; tên miền có thể giữ nguyên cách viết | Cần quy tắc chuẩn hóa, phân loại ký tự, xử lý ký tự nhìn giống nhau và hỗ trợ công cụ tốt |

Ví dụ nếu hỗ trợ Unicode:

```text
entity KháchHàng {
    mãKháchHàng: CustomerId
    họTên: String
}
```

Ví dụ này dễ đọc với người dùng tiếng Việt, nhưng lexer và toàn bộ công cụ phải hỗ trợ identifier Unicode theo cùng một chính sách. Nếu chỉ cho phép ASCII, có thể dùng tên `KhachHang`, `maKhachHang` và `hoTen`, đồng thời cung cấp nhãn tiếng Việt trong metadata hoặc tài liệu.

Không có lựa chọn duy nhất đúng cho mọi DSL. Cần dựa trên đối tượng sử dụng, hệ sinh thái công cụ, yêu cầu đa ngôn ngữ và chính sách bảo mật.

### 7.2. Quy tắc bắt đầu và tiếp tục identifier

Nếu DSL hỗ trợ Unicode identifier, không nên tự định nghĩa bằng cách cho phép mọi code point không phải dấu cách. Unicode có nhiều nhóm ký tự như dấu kết hợp, dấu định dạng, ký hiệu điều khiển và ký tự không nhìn thấy.

Có thể dựa trên các thuộc tính chuẩn của Unicode như `XID_Start` và `XID_Continue` (được mô tả trong Unicode Standard Annex #31) để xác định ký tự bắt đầu và ký tự tiếp tục identifier. Chính sách cụ thể vẫn cần quy định thêm:

- Có cho phép dấu gạch dưới ở đầu tên không?
- Có cho phép chữ số ở vị trí nào?
- Có cho phép dấu kết hợp ở đầu identifier không?
- Có giới hạn các hệ chữ được trộn trong cùng identifier không?
- Có cho phép ký tự định dạng hoặc ký tự mặc định không hiển thị không?

Ví dụ, một chính sách có thể cho phép chữ Unicode và dấu gạch dưới ở đầu; phần tiếp theo cho phép chữ, dấu kết hợp, chữ số và dấu gạch dưới. Lexer cần áp dụng cùng quy tắc trong mọi vị trí khai báo và tham chiếu tên.

### 7.3. Phân biệt chữ hoa và chữ thường

DSL cần xác định identifier có phân biệt hoa thường hay không. Nếu có, `Order`, `order` và `ORDER` có thể là ba tên khác nhau. Nếu không, việc so sánh cần một quy tắc Unicode case folding phù hợp.

Không nên giả định chuyển mọi chữ sang lowercase là đủ cho mọi ngôn ngữ. Một số chữ có quy tắc hoa thường phức tạp hoặc phụ thuộc ngôn ngữ. Unicode case folding được thiết kế cho mục đích so khớp không phân biệt hoa thường; nó khác với thao tác chuyển chữ thường để hiển thị.

Với từ khóa DSL, dùng bộ từ khóa ASCII phân biệt hoa thường thường đơn giản và dễ dự đoán. Identifier nghiệp vụ có thể có chính sách riêng, miễn là được công bố rõ.

### 7.4. Chữ số và ký tự giống nhau

Unicode chứa nhiều hệ chữ số. Chẳng hạn, chữ số ASCII `0` và chữ số Ả Rập-Ấn `٠` có thể cùng biểu thị giá trị không trong một số ngữ cảnh, nhưng là các ký tự khác nhau.

Đối với literal số trong DSL, thường nên chỉ chấp nhận chữ số ASCII `0` đến `9`, dấu thập phân và dấu phân cách đã định nghĩa. Điều này giảm nhầm lẫn khi đọc mã và giúp parser nhất quán. Nếu DSL cần nhập số theo định dạng địa phương, nên quy định riêng cho trường dữ liệu hoặc giao diện, không tự thay đổi cú pháp số nguồn.

## 8. Chuỗi ký tự và escape sequence

String literal là nơi DSL thường cần hỗ trợ Unicode đầy đủ. Ví dụ:

```text
message = "Xin chào, thế giới!"
city = "Thành phố Hồ Chí Minh"
emoji = "😀"
```

Nếu tệp nguồn dùng UTF-8, những ký tự này có thể xuất hiện trực tiếp trong literal. Parser giải mã tệp rồi lưu nội dung chuỗi dưới dạng Unicode theo mô hình của runtime.

### 8.1. Escape sequence

DSL có thể hỗ trợ escape để biểu diễn ký tự khó nhập hoặc có ý nghĩa cú pháp đặc biệt. Ví dụ, một ngôn ngữ có thể định nghĩa:

```text
newline = "Dòng thứ nhất\nDòng thứ hai"
tab = "Cột A\tCột B"
quote = "Từ khóa \"rule\" được đặt trong chuỗi"
symbol = "\u{1F600}"
```

Đây là cú pháp minh họa; `\u{...}` không phải cú pháp bắt buộc chung của mọi ngôn ngữ. Đặc tả DSL phải xác định escape nào hợp lệ, cách biểu diễn code point, cách xử lý surrogate nếu cú pháp dựa trên UTF-16, và hành vi khi escape sai.

### 8.2. Ký tự đơn và grapheme cluster

Nếu DSL có character literal, cần định nghĩa nó đại diện cho một byte, một code unit, một Unicode scalar value hay một grapheme cluster. Những cách hiểu này khác nhau.

Trong một DSL hiện đại, character literal có thể được định nghĩa là một Unicode scalar value; nếu cần lưu một ký tự người dùng cảm nhận gồm nhiều scalar value, hãy dùng string literal. Cách này giúp mô hình kiểu rõ ràng hơn.

### 8.3. Giữ nguyên nội dung chuỗi

Không nên áp dụng chuẩn hóa, case folding hoặc loại bỏ dấu cách một cách âm thầm lên mọi string literal. Với dữ liệu như mật khẩu, chữ ký số, mã định danh bên ngoài hoặc nội dung cần bảo toàn chính xác, việc thay đổi chuỗi có thể làm thay đổi ý nghĩa.

Nếu DSL có một kiểu dữ liệu cần so khớp không phân biệt chuẩn hóa, hãy định nghĩa hành vi đó ở kiểu hoặc hàm chuyên biệt thay vì thay đổi ngầm mọi chuỗi.

## 9. Unicode trong lexer và parser

Lexer chuyển luồng ký tự thành token. Khi hỗ trợ Unicode, lexer cần làm việc trên chuỗi đã giải mã, đồng thời tuân theo quy tắc ký tự của DSL.

### 9.1. Nhận diện khoảng trắng

Không phải mọi ký tự trông giống dấu cách đều là ASCII space. Unicode có nhiều ký tự khoảng trắng như tab, non-breaking space và các dạng space khác. DSL cần quy định nhóm nào được xem là khoảng trắng phân tách token.

Có thể chọn một chính sách hẹp, ví dụ chỉ cho phép ASCII space, tab, LF và CRLF ngoài chuỗi; hoặc chấp nhận tập Unicode White_Space đã xác định. Chính sách hẹp giúp giảm ký tự khó nhìn trong mã nguồn; chính sách rộng thuận tiện hơn với văn bản đa ngôn ngữ. Dù chọn cách nào, lexer phải nhất quán và thông báo rõ khi gặp ký tự không được hỗ trợ.

### 9.2. Từ khóa và identifier

Để giảm nhập nhằng, nhiều DSL dùng từ khóa ASCII cố định như `entity`, `rule`, `when`, `then`, trong khi identifier có thể hỗ trợ Unicode. Từ khóa cần được nhận diện theo quy tắc chính xác, tránh để một ký tự nhìn giống chữ Latin khiến parser hiểu nhầm từ khóa.

Ví dụ, từ khóa `rule` viết bằng chữ Latin ASCII khác với một chuỗi có ký tự Cyrillic hoặc Greek trông gần giống. Lexer không nên dựa vào hình dạng hiển thị để nhận diện từ khóa.

### 9.3. Vị trí lỗi và chỉ số ký tự

Khi parser báo lỗi, vị trí có thể được đo theo byte offset, code unit, code point hoặc cột hiển thị. Các hệ thống này không tương đương khi văn bản có Unicode.

Ví dụ, một ký tự ngoài BMP chiếm bốn byte trong UTF-8 và hai code unit trong UTF-16, nhưng chỉ một code point. Một grapheme cluster có thể gồm nhiều code point. Vì vậy, lexer nên giữ span nguồn nhất quán và công cụ hiển thị cần chuyển đổi vị trí sang hệ chỉ số mà editor sử dụng.

Không nên cộng một đơn vị cho mỗi ký tự nhìn thấy để tính offset byte. Nếu tích hợp Language Server Protocol hoặc IDE, cần tuân theo đơn vị vị trí mà giao thức và client quy định, đồng thời kiểm thử với ký tự ngoài BMP và dấu kết hợp.

## 10. Vấn đề bảo mật và ký tự gây nhầm lẫn

Unicode giúp DSL hỗ trợ nhiều ngôn ngữ, nhưng cũng tạo ra rủi ro khi những ký tự khác nhau có hình dạng gần giống nhau hoặc khi văn bản chứa ký tự điều khiển không nhìn thấy.

### 10.1. Homoglyph và confusable

**Homoglyph** là ký tự có hình dạng giống hoặc gần giống ký tự khác. Ví dụ, chữ Latin `a` và chữ Cyrillic `а` có thể trông gần như giống nhau trong một số font nhưng có code point khác nhau.

Kẻ tấn công có thể tạo identifier trông giống tên biến, tên hàm hoặc từ khóa đáng tin cậy nhưng thực chất là một chuỗi khác. Điều này có thể dẫn đến nhầm lẫn khi review mã, kiểm tra quyền hoặc tìm kiếm.

Biện pháp giảm rủi ro:

- Hạn chế identifier về ASCII nếu DSL không cần tên đa ngôn ngữ.
- Nếu cho phép Unicode, cân nhắc phát hiện identifier trộn nhiều hệ chữ bất thường.
- Cảnh báo hoặc từ chối các confusable nguy hiểm theo chính sách đã chọn.
- Hiển thị code point hoặc thông tin ký tự trong công cụ kiểm tra khi có nghi ngờ.
- Không dùng hình thức hiển thị làm căn cứ duy nhất cho so sánh identifier.

Unicode Technical Standard #39 cung cấp hướng dẫn và dữ liệu về Unicode security mechanisms, bao gồm confusable detection. Đây là tài liệu tham khảo hữu ích khi DSL cho phép identifier Unicode.

### 10.2. Ký tự điều khiển hướng văn bản

Unicode có các ký tự điều khiển hướng hiển thị như các ký tự bidi. Chúng có thể làm thứ tự hiển thị của một đoạn văn bản khác với thứ tự lưu trữ, gây khó khăn khi xem xét mã nguồn.

Đối với identifier và từ khóa, nên cấm các ký tự điều khiển hướng không cần thiết. Trong string literal hoặc bình luận, nếu cho phép thì cần có quy tắc hiển thị và escape rõ ràng. Công cụ review nên có cách thể hiện ký tự điều khiển để người đọc không bị đánh lừa.

### 10.3. Ký tự mặc định không hiển thị

Một số ký tự Unicode có thể không tạo glyph nhìn thấy hoặc có vai trò định dạng. Nếu xuất hiện trong identifier, chúng có thể khiến hai tên trông giống nhau nhưng khác nhau khi so sánh.

DSL nên quy định việc cấm hoặc cho phép các ký tự default-ignorable trong identifier. Nếu một ký tự không được phép, lexer cần báo lỗi thay vì âm thầm xóa nó, bởi việc xóa có thể làm hai tên khác nhau trở thành một tên.

### 10.4. Không âm thầm sửa đầu vào nguy hiểm

Khi gặp byte encoding sai, ký tự điều khiển bị cấm hoặc identifier có dạng không hợp lệ, parser nên báo lỗi rõ. Tự động thay thế, xóa hoặc chuẩn hóa quá mức có thể khiến mã được thực thi khác với nội dung mà người review nhìn thấy.

## 11. Unicode normalization, case folding và so sánh

Ba thao tác này phục vụ mục đích khác nhau và không nên được gộp thành một bước “làm sạch văn bản”.

| Thao tác | Mục đích | Ví dụ sử dụng |
|---|---|---|
| Normalization | Đưa chuỗi về dạng chuẩn Unicode | So sánh identifier tương đương chuẩn tắc |
| Case folding | So khớp không phân biệt hoa thường theo Unicode | Tra cứu tên không phân biệt hoa thường nếu DSL hỗ trợ |
| Trimming | Loại bỏ khoảng trắng ở đầu/cuối theo quy tắc cụ thể | Làm sạch trường nhập liệu khi nghiệp vụ cho phép |

Đối với identifier, DSL cần xác định thứ tự xử lý: giải mã, kiểm tra ký tự hợp lệ, chuẩn hóa, áp dụng quy tắc hoa thường nếu có, rồi tra cứu bảng ký hiệu. Các bước phải được thực hiện giống nhau ở khai báo và tham chiếu.

Đối với string literal, so sánh thường nên giữ nguyên semantics của kiểu chuỗi; nếu cần so khớp ngôn ngữ tự nhiên, cung cấp hàm hoặc kiểu chuyên biệt. Không nên để cùng toán tử `==` lúc so sánh byte/code point nguyên trạng, lúc lại chuẩn hóa hoặc case-fold mà người dùng không biết.

## 12. Quy tắc thực tế cho một DSL đa ngôn ngữ

Một đặc tả DSL có thể công bố chính sách mẫu như sau:

| Thành phần | Chính sách minh họa |
|---|---|
| Encoding tệp nguồn | UTF-8 nghiêm ngặt |
| BOM | Chấp nhận BOM UTF-8 ở đầu tệp và bỏ trước khi lex; không cho phép ở giữa tệp như ký tự định dạng nguồn |
| Identifier | Hỗ trợ Unicode theo `XID_Start` và `XID_Continue`, cộng dấu gạch dưới theo quy tắc riêng |
| Chuẩn hóa identifier | NFC trước khi đưa vào bảng ký hiệu |
| Phân biệt hoa thường | Có; identifier được so sánh theo dạng chuẩn hóa nhưng giữ phân biệt hoa thường |
| Từ khóa | Từ khóa ASCII, phân biệt hoa thường |
| Literal số | Chỉ chữ số ASCII `0`–`9` và dấu phân cách được quy định |
| String literal | Cho phép Unicode trực tiếp và một tập escape được định nghĩa |
| Khoảng trắng | Chấp nhận space, tab, LF và CRLF ngoài literal; các ký tự khác cần quy tắc rõ |
| Ký tự điều khiển trong identifier | Cấm ký tự bidi và default-ignorable theo profile của DSL |
| Byte sequence không hợp lệ | Báo lỗi encoding, không tự thay thế |

Đây chỉ là một profile minh họa. Một DSL dành cho dữ liệu khoa học, ngôn ngữ tự nhiên hoặc cấu hình quốc tế có thể cần chính sách khác. Điều quan trọng là đặc tả phải nói rõ và parser cùng công cụ phải tuân thủ.

## 13. Kiểm thử hỗ trợ Unicode

Kiểm thử Unicode cần bao gồm nhiều trường hợp hơn một chuỗi tiếng Việt thông thường. Có thể chia thành các nhóm:

### 13.1. Kiểm thử encoding

- Tệp UTF-8 hợp lệ chỉ chứa ASCII.
- Tệp UTF-8 có tiếng Việt, chữ viết khác và ký hiệu ngoài BMP.
- Tệp có UTF-8 BOM nếu DSL chấp nhận.
- Byte sequence UTF-8 không hợp lệ hoặc bị cắt giữa một ký tự nhiều byte.
- Tệp UTF-16/UTF-32 khi DSL chỉ chấp nhận UTF-8.

### 13.2. Kiểm thử normalization

- Identifier chứa ký tự dựng sẵn.
- Identifier chứa chuỗi dấu kết hợp tương đương chuẩn tắc.
- Hai identifier trùng nhau sau NFC phải được xử lý theo chính sách đã định.
- String literal được giữ nguyên hay chuẩn hóa đúng theo đặc tả.
- NFKC không được áp dụng ngoài những trường hợp được quy định.

### 13.3. Kiểm thử identifier và bảo mật

- Chữ Unicode hợp lệ ở đầu và giữa identifier.
- Dấu kết hợp ở vị trí hợp lệ và không hợp lệ.
- Chữ số từ hệ chữ khác trong identifier hoặc numeric literal.
- Identifier trộn nhiều hệ chữ.
- Ký tự bidi, default-ignorable và ký tự điều khiển.
- Hai tên nhìn giống nhau nhưng có code point khác nhau.

### 13.4. Kiểm thử vị trí lỗi và công cụ

- Lỗi sau một ký tự UTF-8 nhiều byte.
- Lỗi sau một ký tự ngoài BMP trong runtime dùng UTF-16.
- Lỗi sau chuỗi có dấu kết hợp.
- Formatter giữ nguyên nội dung string literal.
- IDE hiển thị đúng vị trí lỗi và selection range.
- Diff và diagnostic có thể làm rõ ký tự không nhìn thấy khi cần.

Kiểm thử nên dựa trên các ví dụ chuẩn và bộ dữ liệu Unicode phù hợp, đồng thời chạy trên những phiên bản Unicode mà DSL công bố hỗ trợ.

## 14. Phiên bản Unicode và khả năng tương thích

Unicode tiếp tục được cập nhật để bổ sung ký tự, thuộc tính và dữ liệu. Nếu DSL dùng thuộc tính Unicode để xác định identifier, case folding hoặc phân loại ký tự, kết quả có thể phụ thuộc phiên bản Unicode mà parser sử dụng.

Đặc tả DSL nên nêu phiên bản Unicode hoặc profile mà nó dựa vào. Khi nâng phiên bản thư viện Unicode, nhóm phát triển cần kiểm tra liệu có ký tự mới được chấp nhận làm identifier, thay đổi dữ liệu phân loại hay tác động đến công cụ kiểm tra bảo mật hay không.

Nếu nhiều công cụ cùng xử lý một DSL — chẳng hạn compiler, formatter, linter và IDE — chúng nên dùng cùng phiên bản hoặc có cơ chế tương thích được kiểm soát. Nếu mỗi công cụ áp dụng một bộ quy tắc Unicode khác nhau, một identifier có thể hợp lệ trong editor nhưng bị compiler từ chối.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm encoding với font | Văn bản giải mã đúng nhưng hiển thị thiếu glyph, hoặc văn bản bị giải mã sai | Kiểm tra byte encoding và font riêng biệt |
| Giả định một ký tự luôn bằng một byte | Cắt chuỗi hoặc tính offset sai | Phân biệt byte, code unit, code point và grapheme cluster |
| So sánh chuỗi mà không xét normalization | Tên nhìn giống nhau nhưng không khớp | Định nghĩa chính sách normalization cho identifier |
| Dùng lowercase thay cho Unicode case folding | Một số tên đa ngôn ngữ được so khớp sai | Dùng quy tắc case folding phù hợp nếu cần không phân biệt hoa thường |
| Chấp nhận mọi code point trong identifier | Có thể nhận ký tự điều khiển hoặc ký tự khó nhìn | Dùng profile identifier có kiểm soát |
| Tự thay byte lỗi bằng ký tự thay thế | Mã nguồn có thể bị hiểu khác với nội dung gốc | Báo lỗi encoding và dừng phân tích tệp |
| Không quy định whitespace Unicode | Ký tự giống dấu cách có thể tách token khác nhau | Công bố chính xác tập whitespace hợp lệ |
| Không thống nhất phiên bản Unicode | Các công cụ nhận diện identifier khác nhau | Pin phiên bản hoặc profile Unicode |

## 16. Kết luận

Unicode cung cấp hệ thống mã và thuộc tính để biểu diễn văn bản đa ngôn ngữ; UTF-8, UTF-16 và UTF-32 quy định cách mã hóa các giá trị Unicode thành đơn vị lưu trữ. Khi xây dựng DSL, cần phân biệt byte, code unit, code point và grapheme cluster để xử lý chuỗi, độ dài và vị trí lỗi chính xác.

Một DSL có hỗ trợ Unicode tốt cần quy định encoding tệp nguồn, normalization, identifier, từ khóa, whitespace, string literal, escape sequence, ký tự điều khiển và phiên bản Unicode. Những quy tắc này phải được áp dụng thống nhất trong lexer, parser, runtime, formatter và IDE.

UTF-8 nghiêm ngặt, chính sách identifier có kiểm soát và quy tắc chuẩn hóa rõ ràng là nền tảng thực tế cho nhiều DSL hiện đại. Mục tiêu là để cùng một văn bản được giải mã, phân tích và diễn giải theo cùng một cách trên mọi công cụ, đồng thời bảo vệ người dùng khỏi lỗi encoding và những ký tự Unicode dễ gây nhầm lẫn.
