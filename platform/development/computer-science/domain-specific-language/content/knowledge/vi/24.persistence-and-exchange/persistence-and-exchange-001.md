# Định dạng văn bản

## 1. Định dạng văn bản là gì?

Trong hệ thống lưu trữ và trao đổi dữ liệu, **định dạng văn bản (text format)** quy định cách biểu diễn thông tin thành một chuỗi ký tự để con người có thể đọc, chỉnh sửa hoặc công cụ có thể phân tích. Một file văn bản có thể chứa văn xuôi, cấu hình, dữ liệu có cấu trúc, mã nguồn, log hoặc thông điệp trao đổi giữa các dịch vụ.

Ví dụ, cùng một thông tin về khách hàng có thể được biểu diễn dưới dạng văn bản thuần:

~~~text
id: 42
name: An
active: true
~~~

hoặc JSON:

~~~json
{
  "id": 42,
  "name": "An",
  "active": true
}
~~~

hoặc XML:

~~~xml
<customer>
  <id>42</id>
  <name>An</name>
  <active>true</active>
</customer>
~~~

Cả ba cách đều có thể truyền tải một số thông tin giống nhau, nhưng cấu trúc, quy tắc kiểu dữ liệu, khả năng mở rộng và cách xử lý khác nhau.

Một định dạng văn bản không chỉ là phần mở rộng file. Nó bao gồm ít nhất:

- Bộ ký tự và cách mã hóa byte thành ký tự.
- Quy tắc cú pháp và cấu trúc.
- Cách biểu diễn chuỗi, số, Boolean, null và dữ liệu nhị phân.
- Quy tắc escape và dấu phân cách.
- Cách biểu diễn trường tùy chọn, giá trị mặc định và thứ tự.
- Quy tắc kiểm tra hợp lệ hoặc schema.
- Quy ước tương thích giữa các phiên bản.

Trong DSL, định dạng văn bản có thể là cú pháp nguồn, file cấu hình, file schema, tài liệu mô tả, log hoặc giao thức trao đổi. Việc chọn định dạng phù hợp ảnh hưởng trực tiếp đến khả năng đọc, tích hợp, kiểm thử và duy trì dữ liệu.

## 2. Văn bản thuần và văn bản có cấu trúc

### 2.1 Văn bản thuần (plain text)

Plain text là chuỗi ký tự không yêu cầu một cấu trúc dữ liệu phức tạp được nhúng sẵn. Ví dụ:

~~~text
The service started successfully.
Retry count: 3
~~~

Ưu điểm:

- Dễ đọc bằng editor cơ bản.
- Dễ tìm kiếm bằng công cụ dòng lệnh.
- Ít phụ thuộc vào phần mềm chuyên dụng.
- Thuận tiện cho log, tài liệu và ghi chú.

Hạn chế:

- Không tự mô tả kiểu dữ liệu.
- Không có cấu trúc trường thống nhất.
- Công cụ cần quy ước riêng để tách và hiểu nội dung.
- Dễ phát sinh mơ hồ nếu format phát triển tự phát.

### 2.2 Văn bản có cấu trúc (structured text)

Structured text sử dụng quy tắc cú pháp để biểu diễn dữ liệu thành các trường, mảng, object, phần tử hoặc quan hệ.

Ví dụ:

~~~json
{
  "service": "billing",
  "retryCount": 3,
  "enabled": true
}
~~~

Parser có thể tạo cấu trúc dữ liệu tương ứng thay vì phải tự tách từng dòng.

Structured text phù hợp với:

- File cấu hình.
- API request và response.
- Schema và metadata.
- Dữ liệu trao đổi giữa dịch vụ.
- AST hoặc biểu diễn trung gian.
- Tệp mô tả workflow và policy.

### 2.3 Format không đồng nghĩa với semantics

JSON có thể biểu diễn một object nhưng không tự định nghĩa ý nghĩa nghiệp vụ của trường retryCount. Schema hoặc tài liệu API cần quy định trường đó có nghĩa gì, kiểu nào được chấp nhận và giá trị hợp lệ nằm trong khoảng nào.

Tương tự, parser có thể xác nhận XML đúng cú pháp nhưng không chứng minh nội dung đáp ứng quy tắc miền. Cần phân biệt:

1. Byte hợp lệ theo encoding.
2. Văn bản hợp lệ theo cú pháp format.
3. Cấu trúc hợp lệ theo schema.
4. Dữ liệu hợp lệ theo quy tắc ngữ nghĩa và nghiệp vụ.

Một bước thành công không tự động chứng minh các bước sau cũng thành công.

## 3. Từ byte đến ký tự

File được lưu thành byte. Để đọc đúng, chương trình phải biết cách giải mã byte thành ký tự.

~~~text
File bytes
   |
   v
Character encoding
   |
   v
Unicode text
   |
   v
Tokenizer / Parser
   |
   v
Structured data
~~~

Nếu encoding bị hiểu sai, nội dung có thể xuất hiện ký tự lỗi dù byte vẫn được đọc thành công.

### 3.1 Character set và encoding

Unicode định nghĩa các code point cho ký tự. Encoding quy định cách biểu diễn các code point đó thành byte.

Các encoding thường gặp:

- UTF-8.
- UTF-16.
- UTF-32.
- Một số encoding cũ như Windows-1252 hoặc Shift_JIS.

UTF-8 là lựa chọn phổ biến cho file văn bản trao đổi vì hỗ trợ toàn bộ Unicode và tương thích tốt với nhiều hệ thống.

### 3.2 UTF-8

UTF-8 dùng từ một đến bốn byte cho mỗi Unicode code point. Các ký tự ASCII dùng cùng byte value như ASCII, giúp tương thích với nhiều công cụ cũ.

Ví dụ, chuỗi:

~~~text
Hello
~~~

có thể được mã hóa bằng các byte ASCII tương ứng. Ký tự tiếng Việt có dấu cần nhiều byte hơn một ký tự ASCII.

Không được giả định một ký tự luôn bằng một byte. Điều này ảnh hưởng đến:

- Tính toán offset.
- Cắt chuỗi.
- Đếm độ dài.
- Định vị lỗi parser.
- Giới hạn kích thước trường.

### 3.3 UTF-8 BOM

Một số file bắt đầu bằng UTF-8 Byte Order Mark (BOM), là chuỗi byte đặc biệt biểu thị encoding. UTF-8 không cần BOM để xác định byte order, nhưng một số phần mềm vẫn thêm BOM.

Khi trao đổi file, cần thống nhất:

- Có chấp nhận BOM không?
- Parser có loại bỏ BOM ở đầu file không?
- Writer có tạo BOM không?
- BOM có bị coi nhầm là ký tự đầu tiên của nội dung không?

Không nên xóa mọi ký tự zero-width hoặc ký tự đặc biệt trong file một cách tùy tiện. Chỉ xử lý BOM theo đúng encoding và vị trí được định nghĩa.

### 3.4 Unicode normalization

Một ký tự có thể có nhiều biểu diễn code point tương đương về hình thức. Ví dụ, chữ có dấu có thể là một code point dựng sẵn hoặc chữ cái kết hợp với dấu.

Unicode normalization cung cấp các dạng như NFC và NFD. Nếu hệ thống so sánh tên, khóa hoặc identifier, cần quy định có chuẩn hóa hay không.

Không nên tự chuẩn hóa mọi nội dung văn bản khi lưu nếu việc giữ nguyên byte hoặc cách viết gốc là yêu cầu. Đối với identifier, có thể chuẩn hóa trong một bước rõ ràng và giữ source spelling riêng.

## 4. Dòng, dấu kết thúc dòng và khoảng trắng

Các hệ điều hành và công cụ có thể dùng quy ước kết thúc dòng khác nhau:

- LF: line feed, thường gặp trên Unix-like.
- CRLF: carriage return + line feed, thường gặp trên Windows.
- CR: quy ước cũ trên một số hệ thống.

Một file có thể bị thay đổi hàng loạt chỉ vì công cụ chuyển line ending. Điều này tạo diff lớn dù nội dung logic không đổi.

### 4.1 Chính sách line ending

Project nên quy định line ending và dùng editor hoặc repository attributes để giữ nhất quán. Parser thường nên chấp nhận những dạng line ending được format hỗ trợ, trong khi formatter hoặc writer có thể chuẩn hóa đầu ra.

### 4.2 Newline cuối file

Một số công cụ mong file văn bản kết thúc bằng newline. Đây là quy ước hữu ích cho diff, shell và nhiều editor. Tuy nhiên, parser cần xác định newline cuối file là bắt buộc hay tùy chọn.

### 4.3 Tab và space

Trong YAML, thụt lề bằng space có ý nghĩa cú pháp và tab không được dùng thay thế tùy tiện. Trong JSON, khoảng trắng thường không ảnh hưởng cấu trúc ngoài string. Trong CSV, khoảng trắng quanh giá trị có thể là dữ liệu thực.

Không nên trim toàn bộ giá trị khi parse nếu format không quy định. Ví dụ, chuỗi " An " có thể khác "An".

### 4.4 Khoảng trắng có ý nghĩa và không có ý nghĩa

Parser cần phân biệt:

- Whitespace giữa token có thể bị bỏ qua.
- Whitespace nằm trong string phải được giữ theo quy tắc escape.
- Whitespace đầu/cuối của block scalar YAML có thể có ý nghĩa.
- Whitespace trong CSV field có thể là nội dung.
- Indentation có thể biểu diễn cấu trúc trong YAML hoặc DSL indentation-sensitive.

## 5. Escape và biểu diễn ký tự đặc biệt

Các định dạng văn bản cần cách biểu diễn dấu nháy, dấu phân cách, newline và ký tự điều khiển.

### 5.1 Escape trong JSON

JSON dùng dấu nháy kép cho string. Một số ký tự phải escape:

~~~json
{
  "message": "He said: \"Hello\"\nNext line",
  "path": "C:\\data\\file.txt"
}
~~~

Các escape phổ biến gồm:

- Quote: \"
- Backslash: \\\\
- Newline: \\n
- Tab: \\t
- Carriage return: \\r
- Unicode escape: \\uXXXX

JSON string không cho phép mọi ký tự điều khiển xuất hiện trực tiếp. Serializer phải escape đúng thay vì nối chuỗi thủ công.

### 5.2 Escape trong XML

Trong text node và attribute, một số ký tự có ý nghĩa đặc biệt:

- &: &amp;
- <: &lt;
- >: &gt; trong những trường hợp cần thiết
- Quote trong attribute: &quot; hoặc dạng quote phù hợp

Ví dụ:

~~~xml
<message>R&amp;D uses &lt;DSL&gt;</message>
~~~

Không nên escape XML bằng cách thay chuỗi thủ công ở nhiều bước vì có thể double-escape hoặc bỏ sót ngữ cảnh attribute.

### 5.3 Escape trong CSV

Nếu field chứa dấu phân cách, newline hoặc quote, CSV cần quy tắc quoting. Một field có dấu quote thường được đặt trong quote kép và quote nội bộ được nhân đôi.

~~~csv
id,description
1,"Contains a comma, and a ""quoted"" word"
2,"Line one
Line two"
~~~

### 5.4 Context-specific escaping

Escape phụ thuộc ngữ cảnh. Escape cho JSON không thay thế escape cho HTML, SQL, XML hoặc shell. Khi dữ liệu đi qua nhiều tầng, mỗi tầng cần serializer riêng.

Ví dụ, một chuỗi JSON được nhúng trong HTML cần xử lý cả JSON serialization và quy tắc an toàn của HTML context. Không có một hàm escape chung phù hợp cho mọi nơi.

## 6. JSON

JSON (JavaScript Object Notation) là định dạng văn bản có cấu trúc phổ biến cho API, cấu hình và trao đổi dữ liệu.

### 6.1 Các kiểu dữ liệu JSON

JSON có:

- Object.
- Array.
- String.
- Number.
- Boolean true/false.
- Null.

Ví dụ:

~~~json
{
  "id": 42,
  "name": "An",
  "active": true,
  "tags": ["gold", "verified"],
  "address": null
}
~~~

### 6.2 Ưu điểm

- Cú pháp tương đối gọn.
- Nhiều ngôn ngữ có parser và serializer.
- Phù hợp với API web.
- Hỗ trợ object và array lồng nhau.
- Dễ xử lý bằng công cụ phổ biến.

### 6.3 Hạn chế

- Không có comment trong chuẩn JSON.
- Không có kiểu ngày giờ riêng.
- Không có cú pháp binary riêng.
- Number không mang đơn vị hoặc kiểu số chính xác theo nghiệp vụ.
- Schema và validation cần một cơ chế bổ sung.
- Duplicate object keys có thể được xử lý khác nhau giữa parser.

### 6.4 Duplicate keys

JSON object về mặt thực tế thường được dùng như tập cặp key/value. Tuy nhiên, một số parser chấp nhận key trùng và chọn giá trị đầu hoặc cuối, trong khi parser khác có thể từ chối.

Ví dụ:

~~~json
{
  "role": "user",
  "role": "admin"
}
~~~

Đây là dữ liệu nguy hiểm nếu các thành phần trong hệ thống diễn giải khác nhau. Hệ thống cần quy định từ chối duplicate keys hoặc xử lý theo một chính sách thống nhất.

### 6.5 JSON Schema

JSON Schema mô tả cấu trúc và ràng buộc của JSON:

~~~json
{
  "type": "object",
  "required": ["id", "name"],
  "properties": {
    "id": { "type": "integer" },
    "name": { "type": "string" },
    "active": { "type": "boolean" }
  },
  "additionalProperties": false
}
~~~

Schema có thể mô tả kiểu, trường bắt buộc, giới hạn, pattern và cấu trúc lồng nhau. Tuy nhiên, schema không tự chứng minh mọi quy tắc nghiệp vụ phức tạp.

### 6.6 Number và độ chính xác

JSON có một loại cú pháp number chung. Parser có thể ánh xạ thành integer, decimal hoặc floating point theo implementation.

Với tiền tệ hoặc dữ liệu chính xác, cần xác định rõ kiểu đích và cách parse. Không nên mặc định mọi number JSON đều an toàn khi đưa vào binary floating point.

## 7. XML

XML (Extensible Markup Language) biểu diễn dữ liệu theo dạng phần tử có thẻ mở/đóng, thuộc tính và nội dung.

Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<order id="1001">
  <customer>An</customer>
  <items>
    <item sku="A-1" quantity="2"/>
    <item sku="B-4" quantity="1"/>
  </items>
</order>
~~~

### 7.1 Đặc điểm

- Cấu trúc phân cấp rõ.
- Có namespace.
- Có attribute và element.
- Có thể dùng DTD hoặc XML Schema.
- Hỗ trợ nhiều hệ thống tích hợp lâu đời.

### 7.2 Element và attribute

Thông tin có thể được biểu diễn bằng element hoặc attribute. Cần chọn quy ước nhất quán.

Ví dụ:

~~~xml
<customer id="42">
  <name>An</name>
</customer>
~~~

id là attribute; name là element. Schema và hợp đồng dữ liệu nên quy định vị trí của từng trường.

### 7.3 Namespace

Namespace giúp phân biệt các tên trùng nhau đến từ những vocabulary khác nhau:

~~~xml
<a:order xmlns:a="urn:example:account">
  <a:id>42</a:id>
</a:order>
~~~

Prefix a chỉ là alias trong tài liệu. Identity của tên XML phụ thuộc namespace URI và local name, không chỉ chuỗi prefix.

### 7.4 Well-formed và valid

XML well-formed tuân theo cú pháp cơ bản: thẻ lồng đúng, attribute được quote, có một root element và các quy tắc liên quan.

XML valid là tài liệu đáp ứng DTD hoặc schema được áp dụng. Một tài liệu well-formed vẫn có thể không valid theo schema.

### 7.5 XSD

XML Schema Definition (XSD) mô tả element, attribute, kiểu dữ liệu, cardinality và ràng buộc. XSD hữu ích khi cần contract chặt giữa nhiều hệ thống.

### 7.6 Security của XML parser

Parser XML cần được cấu hình an toàn. External Entity (XXE) có thể khiến parser truy cập file nội bộ hoặc tài nguyên mạng thông qua entity reference nếu tính năng không được kiểm soát.

Với dữ liệu không tin cậy:

- Tắt external general entities nếu không cần.
- Tắt external parameter entities và external DTD loading nếu không cần.
- Giới hạn kích thước và độ sâu tài liệu.
- Không tải schema từ nguồn không tin cậy một cách tự động.
- Dùng parser được cập nhật và cấu hình rõ.

## 8. YAML

YAML là định dạng dữ liệu văn bản thường dùng cho cấu hình vì cú pháp thụt lề dễ đọc.

Ví dụ:

~~~yaml
service:
  name: billing
  enabled: true
  retry:
    count: 3
    delay: 5s
  endpoints:
    - https://api.example.test
    - https://backup.example.test
~~~

### 8.1 Kiểu dữ liệu

YAML có thể biểu diễn scalar, sequence và mapping. Parser có thể suy luận kiểu cho số, Boolean, null và một số dạng scalar khác theo phiên bản/specification.

Điều này có thể tạo bất ngờ nếu người viết muốn một chuỗi nhưng parser diễn giải thành kiểu khác. Với giá trị nhạy cảm, nên dùng quote tường minh.

### 8.2 Indentation

Indentation xác định cấu trúc lồng nhau. Dùng space nhất quán; tab không phải cách thay thế hợp lệ cho indentation trong YAML.

### 8.3 Anchors và aliases

YAML hỗ trợ anchors và aliases để tái sử dụng cấu trúc:

~~~yaml
defaults: &defaults
  timeout: 10s
  retries: 3

serviceA:
  <<: *defaults
  name: A
~~~

Hỗ trợ merge key và một số hành vi cụ thể có thể phụ thuộc phiên bản hoặc implementation. Khi trao đổi giữa nhiều parser, nên kiểm tra mức tương thích thực tế.

### 8.4 YAML và an toàn deserialization

Một số YAML library lịch sử cho phép tạo object theo tag hoặc gọi constructor đặc biệt. Khi parse file không tin cậy, cần dùng chế độ safe loading, giới hạn tag được phép và không deserialize thành class tùy ý.

### 8.5 YAML phù hợp với cấu hình

YAML dễ đọc cho cấu hình nhiều cấp, nhưng khoảng trắng có ý nghĩa và một số quy tắc implicit typing có thể làm dữ liệu khó dự đoán. Nếu cần format đơn giản, ít bất ngờ và dễ parse thống nhất, JSON hoặc TOML có thể phù hợp hơn.

## 9. TOML

TOML (Tom's Obvious Minimal Language) hướng đến file cấu hình dễ đọc, với table và key-value rõ ràng.

Ví dụ:

~~~toml
title = "Billing service"
enabled = true
retry_count = 3

[database]
host = "db.example.test"
port = 5432

[[workers]]
name = "primary"
threads = 4

[[workers]]
name = "secondary"
threads = 2
~~~

### 9.1 Đặc điểm

- Key-value rõ ràng.
- Table được khai báo bằng section.
- Array và array of tables.
- Có quy tắc kiểu dữ liệu cụ thể.
- Thường phù hợp với cấu hình ứng dụng.

### 9.2 TOML và YAML/JSON

TOML ít linh hoạt hơn YAML trong một số cấu trúc phức tạp, nhưng thường dễ đọc cho file cấu hình có schema tương đối ổn định. JSON phổ biến trong API; TOML thường được chọn cho file cấu hình do con người chỉnh sửa.

## 10. CSV và dữ liệu dạng bảng

CSV (Comma-Separated Values) biểu diễn dữ liệu theo hàng và cột:

~~~csv
customer_id,name,active
42,An,true
43,Binh,false
~~~

CSV phổ biến trong trao đổi dữ liệu bảng, spreadsheet và import/export.

### 10.1 CSV không có một kiểu dữ liệu phong phú

CSV chủ yếu lưu field dưới dạng văn bản. Schema hoặc hợp đồng bên ngoài cần quy định:

- Cột nào là integer, decimal, date hoặc Boolean.
- Cột nào được phép trống.
- Encoding.
- Delimiter.
- Quote character.
- Escape rule.
- Header có bắt buộc không.
- Null được biểu diễn như thế nào.

### 10.2 Delimiter

Tên CSV không bảo đảm dấu phẩy luôn là dấu phân cách. Một số hệ thống dùng semicolon hoặc tab tùy locale và convention. Format phải quy định delimiter rõ ràng.

### 10.3 Quoting

Field có delimiter, quote hoặc newline cần được quote đúng:

~~~csv
id,comment
1,"A value, with comma"
2,"A ""quoted"" phrase"
~~~

Không nên parse CSV bằng cách split chuỗi theo dấu phẩy. Cách đó sai khi field chứa delimiter bên trong quote.

### 10.4 Null và empty string

CSV thường không phân biệt null với empty string một cách phổ quát. Một field trống có thể có nghĩa là chuỗi rỗng, null, thiếu dữ liệu hoặc giá trị mặc định tùy hợp đồng.

Nếu cần phân biệt, phải định nghĩa quy ước rõ, chẳng hạn một sentinel riêng có escape phù hợp hoặc schema metadata.

### 10.5 CSV formula injection

Khi mở CSV trong spreadsheet, field bắt đầu bằng một số ký tự như dấu bằng, dấu cộng, dấu trừ hoặc dấu @ có thể bị diễn giải như công thức tùy ứng dụng.

Nếu xuất dữ liệu do người dùng kiểm soát ra CSV để mở bằng spreadsheet, cần cân nhắc cách xử lý an toàn cho các giá trị có khả năng trở thành formula. Việc thêm quote theo cú pháp CSV không phải lúc nào cũng ngăn spreadsheet diễn giải công thức.

Chính sách cần được chọn theo ứng dụng nhận file và phải tránh làm thay đổi dữ liệu một cách âm thầm.

## 11. JSON Lines và định dạng streaming

JSON Lines (JSONL hoặc NDJSON) lưu mỗi record JSON trên một dòng:

~~~text
{"id":1,"event":"created"}
{"id":2,"event":"updated"}
{"id":3,"event":"deleted"}
~~~

### 11.1 Ưu điểm

- Có thể xử lý từng record.
- Phù hợp với log và event stream.
- Dễ append dữ liệu.
- Có thể xử lý file lớn mà không cần nạp toàn bộ thành một JSON array.
- Dễ chia partition theo dòng.

### 11.2 Hạn chế

- Mỗi dòng cần là một JSON value hoàn chỉnh theo quy ước JSONL.
- Một record bị lỗi có thể ảnh hưởng cách tiếp tục đọc.
- Cần định nghĩa xử lý newline và dòng rỗng.
- Không có cấu trúc envelope chung trừ khi schema quy định.

### 11.3 Streaming parser

Với file lớn, parser streaming đọc từng record hoặc event thay vì tạo toàn bộ object graph trong bộ nhớ.

Một pipeline:

~~~text
Input stream
    |
    v
Decoder
    |
    v
Incremental parser
    |
    v
Record validation
    |
    v
Consumer
~~~

Streaming phù hợp với log, dữ liệu lớn và pipeline xử lý liên tục. Cần giới hạn kích thước record, xử lý lỗi giữa stream và xác định hành vi khi kết nối bị ngắt.

## 12. Các định dạng văn bản khác

### 12.1 INI

INI thường dùng section và key-value:

~~~ini
[database]
host=db.example.test
port=5432

[service]
enabled=true
~~~

INI đơn giản và dễ đọc nhưng có nhiều biến thể parser. Cần quy định comment, quote, duplicate key, type coercion và cách xử lý section trùng.

### 12.2 Properties

Java Properties thường dùng key-value:

~~~properties
service.name=billing
retry.count=3
feature.enabled=true
~~~

Định dạng này phù hợp với cấu hình đơn giản. Cần lưu ý quy tắc escape, encoding và sự khác biệt giữa các cách đọc file properties.

### 12.3 Markdown

Markdown phù hợp với tài liệu, hướng dẫn và nội dung có cấu trúc nhẹ:

~~~markdown
# Service configuration

The service retries failed requests up to three times.

- Timeout: 5 seconds
- Enabled: true
~~~

Markdown không phải format dữ liệu có schema chặt. Nếu cần trích xuất dữ liệu máy đọc được, nên dùng front matter hoặc file cấu hình riêng với hợp đồng rõ ràng.

### 12.4 Format DSL riêng

Một DSL có thể định nghĩa cú pháp văn bản riêng để gần ngôn ngữ miền:

~~~text
policy "Gold customer"
  when customer.tier == GOLD
  then discount 10 percent
~~~

DSL riêng giúp diễn đạt nghiệp vụ tự nhiên nhưng đòi hỏi lexer, parser, versioning, diagnostics và tài liệu. Không nên tạo DSL mới nếu JSON, YAML hoặc TOML đã đáp ứng nhu cầu.

## 13. So sánh các định dạng phổ biến

| Định dạng | Cấu trúc | Dễ đọc/chỉnh sửa | Schema/validation | Trường hợp thường dùng |
|---|---|---|---|---|
| Plain text | Tùy quy ước | Rất dễ | Cần tự định nghĩa | Log, ghi chú, nội dung |
| JSON | Object/array | Dễ | JSON Schema | API, dữ liệu trao đổi |
| XML | Element/tree | Tương đối dài | DTD/XSD | Tích hợp hệ thống, tài liệu có schema |
| YAML | Mapping/sequence | Dễ nhưng indentation-sensitive | Schema hoặc validator riêng | Cấu hình |
| TOML | Table/key-value | Dễ | Validator riêng | Cấu hình ứng dụng |
| CSV | Hàng/cột | Dễ với bảng đơn giản | Schema bên ngoài | Import/export bảng |
| JSONL | Record theo dòng | Dễ | Schema cho từng record | Log, event, streaming |
| Markdown | Nội dung tài liệu | Rất dễ | Không chặt | Tài liệu |
| INI | Section/key-value | Dễ | Thường tùy implementation | Cấu hình đơn giản |

Không có format tốt nhất cho mọi tình huống. Lựa chọn phụ thuộc cấu trúc dữ liệu, người chỉnh sửa, kích thước, yêu cầu tương thích và hệ sinh thái công cụ.

## 14. Schema và validation

Parser chỉ xác nhận cú pháp. Schema xác định hình dạng dữ liệu được phép; validation ngữ nghĩa kiểm tra các ràng buộc sâu hơn.

Ví dụ JSON:

~~~json
{
  "service": "billing",
  "retryCount": -1
}
~~~

JSON parser chấp nhận cú pháp này. Schema có thể yêu cầu retryCount là integer không âm:

~~~json
{
  "type": "object",
  "properties": {
    "service": { "type": "string" },
    "retryCount": {
      "type": "integer",
      "minimum": 0
    }
  },
  "required": ["service", "retryCount"]
}
~~~

### 14.1 Validation nhiều tầng

Một pipeline kiểm tra dữ liệu:

1. Decode bytes theo encoding.
2. Parse cú pháp.
3. Validate schema.
4. Chuyển sang domain model.
5. Kiểm tra invariant nghiệp vụ.
6. Kiểm tra quyền và điều kiện môi trường nếu cần.

Mỗi tầng cần diagnostic riêng để người dùng biết lỗi nằm ở encoding, syntax, schema hay nghiệp vụ.

### 14.2 Required và nullable

Một trường có thể bắt buộc xuất hiện nhưng vẫn cho phép giá trị null. Ngược lại, trường có thể không bắt buộc nhưng nếu xuất hiện thì phải có giá trị không null.

Hai thuộc tính này cần được mô tả riêng:

- Presence: field có xuất hiện không?
- Nullability: nếu xuất hiện, field có được null không?

### 14.3 Default value

Schema hoặc ứng dụng có thể áp dụng default khi trường vắng mặt. Cần quy định có áp dụng default khi field explicit null hay không. Không nên tự gộp missing và null.

## 15. Thiết kế tương thích và tiến hóa schema

Dữ liệu thường được lưu lâu hơn vòng đời của một phiên bản ứng dụng. Vì vậy, format cần có chiến lược tiến hóa.

### 15.1 Thêm field

Phiên bản mới thêm:

~~~json
{
  "id": 42,
  "name": "An",
  "preferredLocale": "vi-VN"
}
~~~

Nếu consumer cũ bỏ qua field không biết, thay đổi có thể tương thích theo hướng forward-compatible trong hợp đồng đó. Nếu consumer từ chối unknown field, thay đổi có thể gây lỗi.

### 15.2 Xóa hoặc đổi tên field

Xóa field có thể làm consumer cũ thiếu dữ liệu. Đổi tên field có thể phá contract nếu không hỗ trợ alias hoặc migration.

Một chiến lược:

1. Thêm field mới.
2. Trong giai đoạn chuyển đổi, đọc cả tên cũ và mới.
3. Writer bắt đầu ghi tên mới.
4. Theo dõi consumer đã chuyển đổi.
5. Ngừng hỗ trợ tên cũ ở phiên bản major phù hợp.

### 15.3 Thay đổi kiểu

Đổi integer thành string hoặc đổi đơn vị seconds thành milliseconds có thể là breaking change dù dữ liệu vẫn parse được.

Không nên chỉ dựa vào việc parser chấp nhận dữ liệu để kết luận tương thích.

### 15.4 Version trong payload

Có thể thêm version rõ:

~~~json
{
  "schemaVersion": 2,
  "id": 42,
  "name": "An"
}
~~~

Version giúp chọn migration hoặc parser phù hợp. Cần xác định version thuộc schema, message hay application contract.

### 15.5 Reader và writer compatibility

Có thể phân tích:

- Backward compatibility: reader mới đọc được dữ liệu cũ.
- Forward compatibility: reader cũ xử lý được dữ liệu mới theo quy ước.
- Full compatibility: cả hai chiều đều được hỗ trợ.

Kết quả phụ thuộc chính sách unknown fields, defaults, required fields, enum values và cách biểu diễn null.

## 16. Canonicalization và tính ổn định của văn bản

Hai file có thể biểu diễn cùng dữ liệu nhưng khác thứ tự key, khoảng trắng hoặc line ending.

Ví dụ JSON:

~~~json
{"a":1,"b":2}
~~~

và:

~~~json
{
  "b": 2,
  "a": 1
}
~~~

Có thể tương đương về cấu trúc theo hợp đồng JSON object, dù byte khác nhau.

### 16.1 Canonical form

Canonicalization chuyển dữ liệu sang một biểu diễn chuẩn theo quy tắc xác định, chẳng hạn:

- Sắp xếp key.
- Chuẩn hóa encoding.
- Quy định escape.
- Quy định số và dấu thập phân.
- Quy định line ending.
- Loại bỏ whitespace không có ý nghĩa.

Không có một canonical form chung cho mọi format. Cần dùng specification hoặc thuật toán canonicalization đúng với format và mục đích.

### 16.2 Hash và chữ ký số

Hash tính trên byte. Nếu hai file khác byte nhưng cùng cấu trúc, hash của chúng vẫn có thể khác.

Nếu cần ký dữ liệu theo semantics thay vì ký nguyên byte, hệ thống cần canonicalize theo một quy tắc đã thống nhất trước khi hash và ký.

Không được tự sắp xếp hoặc chuẩn hóa dữ liệu trước khi xác minh chữ ký nếu thuật toán ký quy định byte representation khác. Sai lệch canonicalization có thể làm chữ ký không hợp lệ hoặc tạo lỗ hổng xác minh.

### 16.3 Stable serialization

Stable serialization hữu ích cho:

- Cache key.
- Snapshot test.
- Version control.
- Content-addressed storage.
- Digital signatures.

Writer nên có thứ tự trường và format số xác định nếu hệ thống dựa vào so sánh byte.

## 17. Lưu trữ file văn bản an toàn

Khi ghi file, cần tránh tạo file dở dang nếu tiến trình bị dừng giữa chừng.

### 17.1 Atomic write

Một chiến lược phổ biến:

1. Ghi nội dung mới vào file tạm trong cùng filesystem.
2. Flush dữ liệu theo yêu cầu durability.
3. Đóng file.
4. Rename hoặc replace file đích theo cơ chế atomic được filesystem hỗ trợ.

~~~text
write temp file
      |
      v
flush / close
      |
      v
atomic replace
      |
      v
new file visible
~~~

Atomic rename không bảo đảm mọi hệ thống có cùng semantics. Cần hiểu filesystem, quyền truy cập và yêu cầu durability của ứng dụng.

### 17.2 Ghi đè và backup

Nếu dữ liệu quan trọng, có thể cần backup, version history hoặc transaction. Không nên giả định thao tác write luôn hoàn tất toàn bộ hoặc không thay đổi gì.

### 17.3 Concurrent writers

Hai tiến trình cùng ghi một file có thể làm mất cập nhật. Có thể cần lock, compare-and-swap theo version, atomic replace hoặc một storage service quản lý concurrency.

### 17.4 File encoding và metadata

Writer nên xác định rõ:

- Encoding.
- BOM policy.
- Line ending.
- Newline cuối file.
- File permissions.
- Content type nếu trao đổi qua mạng.

Không nên để các giá trị này phụ thuộc ngẫu nhiên vào môi trường chạy.

## 18. Trao đổi qua mạng và Content-Type

Khi gửi văn bản qua HTTP, Content-Type cho biết media type của nội dung.

Ví dụ:

~~~http
Content-Type: application/json
~~~

Hoặc:

~~~http
Content-Type: application/xml
~~~

Với text:

~~~http
Content-Type: text/plain; charset=utf-8
~~~

### 18.1 Content-Type và phần mở rộng file

Phần mở rộng .json hoặc .xml chỉ là gợi ý. Nội dung thực tế và Content-Type cần nhất quán. Không nên tin phần mở rộng file do người dùng cung cấp như bằng chứng rằng nội dung an toàn hoặc đúng format.

### 18.2 Charset

Nếu giao thức cho phép hoặc yêu cầu charset, cần công bố encoding chính xác. UTF-8 là lựa chọn phổ biến. Client và server cần xử lý đúng byte và header.

### 18.3 Content negotiation

Client có thể gửi Accept để mô tả format muốn nhận:

~~~http
Accept: application/json, application/xml;q=0.8
~~~

Server chọn representation phù hợp hoặc báo không hỗ trợ. Việc chọn format không được làm thay đổi semantics của tài nguyên.

### 18.4 Compression

Văn bản có thể được nén khi truyền để giảm băng thông. Content-Encoding như gzip mô tả lớp nén. Cần giới hạn kích thước sau giải nén để tránh resource exhaustion.

## 19. Hiệu năng và streaming

Định dạng văn bản dễ quan sát nhưng có thể tốn CPU và bộ nhớ khi parse hoặc serialize.

### 19.1 DOM-style parsing

Parser có thể tạo toàn bộ cây object trong bộ nhớ. Cách này thuận tiện khi dữ liệu vừa phải và cần truy cập ngẫu nhiên.

### 19.2 Event-based hoặc streaming parsing

Parser đọc từng phần và phát event hoặc record. Cách này phù hợp với file lớn hoặc luồng dữ liệu liên tục.

### 19.3 Buffering

Buffer giúp giảm số lần I/O nhỏ nhưng cần giới hạn kích thước. Một parser streaming không có nghĩa là không thể bị tấn công bằng một record cực lớn hoặc nesting quá sâu.

### 19.4 Backpressure

Trong pipeline streaming, producer cần điều chỉnh tốc độ khi consumer xử lý chậm. Nếu không, queue có thể tăng vô hạn và tiêu thụ hết bộ nhớ.

### 19.5 Giới hạn parser

Nên xem xét:

- Kích thước file tối đa.
- Kích thước string/field tối đa.
- Số phần tử tối đa.
- Độ sâu nesting tối đa.
- Số entity hoặc reference.
- Thời gian parse.
- Số lỗi được tích lũy.

Giới hạn cần phù hợp với workload thực tế và được cấu hình rõ ràng.

## 20. Bảo mật khi đọc và ghi text format

Văn bản có thể đến từ người dùng, dịch vụ ngoài hoặc file được tải xuống. Parser và consumer cần xem input là dữ liệu không tin cậy.

### 20.1 Injection

Nếu dữ liệu văn bản được nhúng vào ngữ cảnh khác mà không serialize đúng, có thể gây:

- SQL injection.
- HTML/script injection.
- XML injection.
- Shell injection.
- Log forging.

Giải pháp đúng là dùng parameterized API hoặc serializer theo đúng ngữ cảnh, không nối chuỗi tùy tiện.

### 20.2 XML External Entity

XXE có thể phát sinh khi XML parser xử lý external entity không an toàn. Tắt chức năng không cần thiết và giới hạn tài nguyên.

### 20.3 YAML deserialization

Không dùng unsafe loader cho file không tin cậy. Chỉ cho phép kiểu và tag cần thiết.

### 20.4 JSON resource exhaustion

JSON lồng sâu, string khổng lồ hoặc số lượng phần tử rất lớn có thể tiêu thụ tài nguyên. Cần giới hạn parser.

### 20.5 CSV formula injection

Giá trị do người dùng cung cấp có thể bị spreadsheet thực thi như công thức. Cần chính sách export phù hợp với consumer.

### 20.6 Path và file name

Nếu text format chứa path, không nối path không tin cậy trực tiếp vào thư mục lưu trữ. Cần chuẩn hóa, kiểm tra traversal và giới hạn vùng được phép truy cập.

### 20.7 Log injection

Newline hoặc ký tự điều khiển trong field có thể giả mạo một dòng log mới. Logger nên dùng structured logging hoặc encode giá trị theo quy ước.

## 21. Chọn định dạng phù hợp

Hãy bắt đầu từ nhu cầu dữ liệu và người sử dụng.

### 21.1 Câu hỏi cần trả lời

- Dữ liệu là tài liệu, cấu hình, bảng hay message?
- Ai tạo và ai đọc: con người, máy hay cả hai?
- Có cần schema chặt không?
- Có cần comment không?
- Dữ liệu có lồng sâu không?
- Có cần streaming hoặc append không?
- Có cần giữ thứ tự trường không?
- Có cần biểu diễn null, missing, binary hoặc timestamp?
- Có cần tương thích lâu dài giữa nhiều phiên bản?
- Có cần canonicalization để hash hoặc ký?
- Có yêu cầu bảo mật đặc biệt?

### 21.2 Gợi ý lựa chọn

| Nhu cầu | Định dạng có thể phù hợp | Lý do |
|---|---|---|
| API web phổ biến | JSON | Hỗ trợ rộng, object/array |
| Cấu hình nhiều cấp, dễ đọc | YAML | Cú pháp gọn, cấu trúc lồng nhau |
| Cấu hình ứng dụng đơn giản | TOML | Table và kiểu dữ liệu rõ |
| Tích hợp hệ thống cần schema XML | XML | Namespace và XSD |
| Dữ liệu bảng import/export | CSV | Đơn giản và tương thích spreadsheet |
| Log/event lớn theo record | JSONL | Xử lý từng dòng, append thuận tiện |
| Tài liệu hướng dẫn | Markdown | Dễ đọc và có cấu trúc nhẹ |
| Log văn bản đơn giản | Plain text | Dễ tìm kiếm và quan sát |

Đây là gợi ý, không phải quy tắc bắt buộc. Một API có thể dùng XML vì hợp đồng đối tác; một file cấu hình có thể dùng JSON nếu công cụ yêu cầu format nghiêm ngặt.

### 21.3 Đừng chọn format chỉ vì ngắn

Một format ít ký tự hơn chưa chắc dễ bảo trì. Cần cân bằng readability, parser behavior, schema, ecosystem, security và compatibility.

### 21.4 Tránh tạo format riêng không cần thiết

Format riêng có thể phù hợp khi DSL cần cú pháp miền đặc thù. Nhưng nó tạo chi phí:

- Lexer/parser.
- Formatter.
- Schema hoặc validation.
- Tooling.
- Tài liệu.
- Versioning.
- Migration.
- Interoperability.

Nếu format hiện có đáp ứng được yêu cầu, sử dụng format chuẩn thường giảm chi phí tích hợp.

## 22. Định dạng văn bản trong DSL

Một hệ thống DSL có thể sử dụng nhiều format ở các lớp khác nhau:

| Lớp | Ví dụ format | Mục đích |
|---|---|---|
| Source language | DSL riêng, YAML hoặc JSON | Người dùng mô tả logic |
| Configuration | TOML, YAML, JSON | Cấu hình compiler/runtime |
| Schema | JSON Schema, XSD | Kiểm tra cấu trúc dữ liệu |
| Intermediate exchange | JSON, XML, Protobuf text view | Trao đổi model |
| Documentation | Markdown | Hướng dẫn và đặc tả |
| Logs | Plain text, JSONL | Theo dõi vận hành |
| Diagnostics | JSON hoặc LSP payload | Báo lỗi cho tooling |

### 22.1 Không trộn các lớp

Một file cấu hình compiler không nhất thiết phải dùng cùng format với source DSL. Một API trao đổi semantic model cũng không nhất thiết dùng cú pháp mà người viết DSL sử dụng.

Mỗi lớp có người dùng và yêu cầu riêng. Tách chúng giúp có thể thay đổi format trao đổi mà không phải đổi grammar source.

### 22.2 Parser và serializer đối xứng

Nếu hệ thống hỗ trợ đọc và ghi cùng một format, cần định nghĩa:

- Parse có giữ thứ tự không?
- Serialize có giữ comment không?
- Unknown field được giữ lại hay bỏ?
- Default có được ghi ra không?
- Null và missing có được phân biệt?
- Số có giữ precision và notation không?

Không phải parser và serializer nào cũng round-trip nguyên văn. Cần phân biệt semantic round-trip với textual round-trip.

### 22.3 Round-trip

Semantic round-trip:

\[
parse(serialize(model)) \equiv model
\]

Textual round-trip mạnh hơn:

\[
serialize(parse(text)) = text
\]

Điều kiện textual round-trip khó hơn vì serializer có thể chuẩn hóa whitespace, thứ tự key hoặc escape. Nếu cần giữ comment và format người dùng, có thể cần concrete syntax tree hoặc lossless parser.

## 23. Quy trình thiết kế format trao đổi

Khi thiết kế hoặc chọn một định dạng văn bản, có thể làm theo:

1. **Xác định mục đích:** cấu hình, source, tài liệu, bảng, log hay API.
2. **Xác định consumer:** con người, chương trình nội bộ, đối tác hay công cụ bên thứ ba.
3. **Chọn format chuẩn:** đánh giá JSON, XML, YAML, TOML, CSV, JSONL hoặc DSL riêng.
4. **Chốt encoding:** thường là UTF-8; quy định BOM và Unicode normalization.
5. **Định nghĩa cú pháp:** escaping, newline, delimiter, indentation và duplicate key.
6. **Định nghĩa schema:** field, type, required, nullable, default và giới hạn.
7. **Định nghĩa versioning:** cách thêm, xóa, đổi tên và thay kiểu.
8. **Định nghĩa canonicalization:** nếu cần hash, signature hoặc stable diff.
9. **Định nghĩa bảo mật:** parser limits, safe loading, injection và quyền truy cập.
10. **Định nghĩa vận chuyển:** Content-Type, charset, compression và streaming.
11. **Viết ví dụ và test:** dữ liệu hợp lệ, không hợp lệ, Unicode, escape và phiên bản cũ.
12. **Tài liệu hóa contract:** quy định những gì parser và writer phải bảo đảm.

Một format tốt cần đủ rõ để hai implementation độc lập đọc và ghi cùng dữ liệu mà không phải suy đoán các quy ước ngầm.

## 24. Ví dụ tổng hợp: trao đổi cấu hình dịch vụ

Giả sử DSL quản lý cấu hình một dịch vụ:

~~~text
service billing {
  retry_count = 3
  timeout = 5 seconds
  enabled = true
}
~~~

Semantic model:

~~~text
ServiceConfig {
  name: String
  retryCount: Integer
  timeout: Duration
  enabled: Boolean
}
~~~

### 24.1 JSON representation

~~~json
{
  "schemaVersion": 1,
  "name": "billing",
  "retryCount": 3,
  "timeout": {
    "value": 5,
    "unit": "seconds"
  },
  "enabled": true
}
~~~

JSON không có kiểu Duration riêng nên contract biểu diễn Duration bằng object có value và unit.

### 24.2 YAML representation

~~~yaml
schemaVersion: 1
name: billing
retryCount: 3
timeout: 5s
enabled: true
~~~

Ở đây timeout dùng scalar dạng 5s. Parser cần có schema hoặc domain converter để chuyển thành Duration.

### 24.3 CSV representation

~~~csv
name,retry_count,timeout_value,timeout_unit,enabled
billing,3,5,seconds,true
~~~

CSV cần header và schema ngoài để hiểu kiểu từng cột.

### 24.4 Các contract cần giữ

- retryCount là integer không âm.
- timeout là Duration dương.
- enabled là Boolean.
- schemaVersion xác định quy tắc parse.
- Encoding là UTF-8.
- Unknown field được xử lý theo chính sách đã công bố.
- Missing và null được phân biệt nếu contract cần.

Các representation khác nhau nhưng phải chuyển về cùng semantic model theo quy tắc xác định. Nếu một format không thể biểu diễn đầy đủ thông tin, cần bổ sung cấu trúc hoặc từ chối chuyển đổi mất dữ liệu.

## 25. Câu hỏi tự kiểm tra

1. Phân biệt plain text và structured text.
2. Vì sao định dạng văn bản không tự định nghĩa ý nghĩa nghiệp vụ?
3. Phân biệt Unicode code point và encoding.
4. UTF-8 BOM, line ending và Unicode normalization ảnh hưởng trao đổi file như thế nào?
5. Vì sao escape phải phụ thuộc ngữ cảnh?
6. JSON có những kiểu dữ liệu nào và những hạn chế nào?
7. Phân biệt XML well-formed với XML valid.
8. YAML có những rủi ro nào khi deserialize dữ liệu không tin cậy?
9. Vì sao không nên parse CSV bằng cách split theo dấu phẩy?
10. JSONL phù hợp với streaming trong trường hợp nào?
11. Schema phân biệt required, nullable và default như thế nào?
12. Backward và forward compatibility khác nhau ra sao?
13. Canonicalization cần thiết khi hash hoặc ký dữ liệu như thế nào?
14. Atomic write giúp giảm rủi ro file dở dang ra sao?
15. Content-Type và charset có vai trò gì khi trao đổi qua HTTP?
16. Những biện pháp nào giúp parser xử lý input không tin cậy an toàn?
17. Phân biệt semantic round-trip và textual round-trip.
18. Làm thế nào để chọn format phù hợp cho cấu hình, API, log và dữ liệu bảng?

Định dạng văn bản là hợp đồng giữa nơi tạo dữ liệu và nơi đọc dữ liệu. Khi encoding, cú pháp, schema, versioning, escaping và bảo mật được quy định rõ, dữ liệu có thể được lưu trữ, trao đổi và diễn giải nhất quán qua nhiều công cụ và hệ thống.
