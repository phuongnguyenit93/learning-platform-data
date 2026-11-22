# Bản địa hóa thông báo

Trong một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), parser, bộ kiểm tra ngữ nghĩa và runtime thường phát hiện nhiều loại vấn đề: token không hợp lệ, thiếu dấu phân cách, tên chưa được khai báo, sai kiểu dữ liệu, vi phạm ràng buộc hoặc thao tác không được phép. Người dùng cần hiểu vấn đề, tìm được vị trí xảy ra và biết cách sửa. **Bản địa hóa thông báo (localization of diagnostics/messages)** là quá trình trình bày những chẩn đoán đó bằng ngôn ngữ và quy ước phù hợp với locale của người dùng.

Bản địa hóa thông báo không chỉ là dịch một câu tiếng Anh sang tiếng Việt. Một hệ thống tốt cần tách dữ liệu chẩn đoán khỏi câu chữ hiển thị, quản lý mã lỗi ổn định, truyền tham số có kiểu, xử lý số ít và số nhiều, định dạng ngày giờ và số theo locale, hỗ trợ thông báo trong CLI và editor, đồng thời giữ thông tin đủ rõ cho công cụ tự động.

Ví dụ, cùng một lỗi có thể được hiển thị bằng hai ngôn ngữ:

~~~text
English:
Unexpected token ')'; expected an expression.

Tiếng Việt:
Token ')' không được mong đợi; cần một biểu thức.
~~~

Hai câu có thể khác nhau về trật tự từ và cách diễn đạt, nhưng đều xuất phát từ cùng một chẩn đoán: parser gặp token đóng ngoặc tại vị trí cần một biểu thức. Hệ thống không nên tạo hai loại lỗi riêng chỉ vì có hai ngôn ngữ hiển thị.

Bài học này trình bày cách thiết kế chẩn đoán có thể bản địa hóa trong DSL, từ mô hình dữ liệu, message catalog và lựa chọn locale đến pluralization, định dạng, tích hợp editor, kiểm thử và quản lý bản dịch.

## 1. Bản địa hóa thông báo trong chẩn đoán lỗi là gì?

**Chẩn đoán (diagnostic)** là một bản ghi có cấu trúc mô tả một vấn đề hoặc một thông tin mà hệ thống phát hiện khi phân tích hay thực thi DSL. Diagnostic có thể là:

- Lỗi cú pháp (syntax error): token hoặc cấu trúc không phù hợp grammar.
- Lỗi ngữ nghĩa (semantic error): tên không tồn tại, sai loại ký hiệu hoặc tham chiếu không hợp lệ.
- Lỗi kiểu (type error): giá trị hoặc biểu thức không tương thích kiểu.
- Cảnh báo (warning): cấu trúc có thể hợp lệ nhưng đáng chú ý, chẳng hạn dùng cú pháp đã deprecated.
- Thông tin (information): gợi ý hoặc thông tin hỗ trợ người dùng.
- Lỗi runtime: dữ liệu hoặc trạng thái thực thi không đáp ứng điều kiện đã định nghĩa.

Bản địa hóa là bước chuyển diagnostic thành nội dung hướng đến người dùng theo locale được chọn. Nó có thể ảnh hưởng đến ngôn ngữ, định dạng số, ngày giờ, dấu phân cách, thứ tự tham số và cách diễn đạt số lượng.

### 1.1. Phân biệt diagnostic với message

Một diagnostic nên lưu **ý nghĩa của vấn đề** dưới dạng dữ liệu. Message là cách diễn đạt ý nghĩa đó cho một người đọc cụ thể.

Ví dụ dữ liệu:

~~~json
{
  "code": "DSL-PARSE-001",
  "severity": "error",
  "messageKey": "parser.unexpected-token",
  "arguments": {
    "actual": ")",
    "expected": "expression"
  }
}
~~~

Message tiếng Anh:

~~~text
Unexpected token ')'; expected an expression.
~~~

Message tiếng Việt:

~~~text
Token ')' không được mong đợi; cần một biểu thức.
~~~

Diagnostic giữ mã lỗi và dữ liệu giống nhau. Chỉ lớp trình bày chọn message tương ứng với locale.

### 1.2. Localization và internationalization

Hai khái niệm thường đi cùng nhau:

- **Internationalization (i18n):** thiết kế hệ thống để có thể hỗ trợ nhiều ngôn ngữ và quy ước vùng miền mà không phải viết lại logic cốt lõi.
- **Localization (l10n):** cung cấp nội dung và quy tắc cụ thể cho một locale, chẳng hạn tiếng Việt tại Việt Nam hoặc tiếng Anh tại Hoa Kỳ.

Một DSL muốn hỗ trợ nhiều ngôn ngữ cần chuẩn bị kiến trúc i18n trước, rồi bổ sung bản dịch và quy tắc locale trong quá trình l10n. Nếu parser gắn trực tiếp câu tiếng Anh vào mọi nhánh xử lý lỗi, việc bổ sung ngôn ngữ mới sẽ khó và dễ tạo ra nội dung không nhất quán.

## 2. Vì sao thông báo lỗi cần được bản địa hóa?

Thông báo lỗi là một phần của giao diện DSL. Người viết DSL thường cần hiểu lỗi ngay tại nơi họ soạn cấu hình, mô hình hoặc quy trình. Nếu thông báo chỉ dùng một ngôn ngữ mà người dùng không quen, thời gian tìm hiểu và sửa lỗi có thể tăng lên.

Bản địa hóa có một số lợi ích:

- **Dễ hiểu:** người dùng đọc thông báo bằng ngôn ngữ quen thuộc.
- **Giảm thời gian sửa lỗi:** mô tả nguyên nhân và gợi ý rõ hơn.
- **Hỗ trợ đào tạo:** tài liệu, editor và thông báo sử dụng cùng thuật ngữ.
- **Phù hợp môi trường địa phương:** ngày, giờ, số thập phân và cách trình bày có thể theo quy ước địa phương.
- **Tăng khả năng tiếp cận:** người dùng ở nhiều quốc gia có thể sử dụng cùng DSL.

Tuy nhiên, dịch thuật không được làm thay đổi ý nghĩa kỹ thuật. Một thông báo tiếng Việt có thể dùng câu tự nhiên hơn tiếng Anh, nhưng mã lỗi, vị trí nguồn, loại token và các dữ liệu máy cần đọc phải giữ ổn định.

### 2.1. Người đọc khác nhau cần cách trình bày khác nhau

Một diagnostic có thể được sử dụng bởi nhiều đối tượng:

| Đối tượng | Thông tin cần ưu tiên |
| --- | --- |
| Người viết DSL | Nguyên nhân dễ hiểu, vị trí lỗi, cách sửa |
| Người phát triển DSL | Mã lỗi, loại lỗi, dữ liệu nội bộ có thể tái hiện |
| Editor hoặc Language Server | Mã, severity, source range, related information |
| CI/CD và công cụ tự động | Mã ổn định, đường dẫn, vị trí, dữ liệu có cấu trúc |
| Nhóm dịch thuật | Message key, ngữ cảnh, placeholder và quy tắc hiển thị |

Một câu thông báo duy nhất không thể đáp ứng hoàn hảo tất cả nhu cầu. Nên giữ diagnostic có cấu trúc, sau đó tạo các cách trình bày phù hợp.

## 3. Nguyên tắc cốt lõi: tách logic khỏi câu chữ

Parser và semantic analyzer nên phát ra diagnostic theo mã và tham số, thay vì tự ghép câu thông báo.

Thiết kế dễ mở rộng:

~~~text
Parser / Semantic Analyzer
          |
          v
Structured Diagnostic
  - code
  - severity
  - message key
  - arguments
  - source location
          |
          v
Localization / Message Resolver
          |
          v
Localized Message
          |
          v
CLI / IDE / API / Log Renderer
~~~

Với cách tổ chức này, parser không cần biết người dùng đang chọn tiếng Việt hay tiếng Anh. Lớp localization chịu trách nhiệm tìm message phù hợp.

### 3.1. Không dùng câu thông báo làm mã lỗi

Không nên dùng chính câu tiếng Anh làm định danh lỗi. Nếu câu này thay đổi do sửa ngữ pháp hoặc dịch sang tiếng Việt, các hệ thống khác có thể không nhận ra đây vẫn là cùng một lỗi.

Hãy dùng mã ổn định, ví dụ **DSL-PARSE-001**, và khóa thông báo, ví dụ **parser.unexpected-token**.

Mã lỗi dùng để phân loại và liên kết tài liệu; message key dùng để tìm bản dịch. Hai giá trị có thể có quan hệ một-một, nhưng không nhất thiết phải giống nhau.

### 3.2. Không phân tích ngược câu đã hiển thị

Một lỗi thiết kế là tạo câu tiếng Anh trong parser rồi để lớp khác tìm chuỗi con hoặc biểu thức chính quy nhằm suy ra tham số. Cách này dễ hỏng khi đổi câu hoặc dịch.

Thay vào đó, parser truyền trực tiếp dữ liệu:

~~~text
code = DSL-PARSE-001
actualToken = RIGHT_PAREN
expectedCategory = EXPRESSION
sourceRange = line 8, column 14..15
~~~

Renderer mới quyết định cách diễn đạt các trường này.

### 3.3. Giữ thông tin máy đọc được

Dù message đã được dịch, diagnostic vẫn cần dữ liệu ổn định để IDE, CI và công cụ phân tích sử dụng. Không nên yêu cầu công cụ tự trích mã lỗi hoặc vị trí từ câu văn bản đã bản địa hóa.

## 4. Mô hình dữ liệu diagnostic

Một mô hình diagnostic có thể chứa các trường sau:

~~~text
Diagnostic
  code: DiagnosticCode
  severity: Severity
  source: DiagnosticSource
  messageKey: MessageKey
  arguments: Map<String, Value>
  primaryLocation: SourceLocation?
  relatedLocations: List<RelatedLocation>
  tags: Set<DiagnosticTag>
  fixes: List<CodeAction>
~~~

Ý nghĩa:

| Trường | Mục đích |
| --- | --- |
| code | Mã lỗi hoặc cảnh báo ổn định |
| severity | Error, warning, information hoặc hint |
| source | Thành phần phát hiện lỗi, ví dụ parser hoặc type checker |
| messageKey | Khóa tra cứu nội dung bản địa hóa |
| arguments | Giá trị được chèn hoặc định dạng trong message |
| primaryLocation | Vị trí chính của vấn đề |
| relatedLocations | Vị trí liên quan, chẳng hạn nơi khai báo ban đầu |
| tags | Nhãn như deprecated hoặc unnecessary |
| fixes | Các hành động sửa có thể áp dụng |

Không phải mọi diagnostic đều cần tất cả trường. Ví dụ, một thông tin tổng quát về tệp có thể không có source range; một lỗi cú pháp thường cần vị trí nguồn.

### 4.1. Severity độc lập với ngôn ngữ

Severity nên được biểu diễn bằng enum hoặc giá trị máy đọc được:

~~~text
ERROR
WARNING
INFORMATION
HINT
~~~

Renderer có thể dịch nhãn hiển thị, nhưng công cụ tự động phải nhận diện severity bằng giá trị chuẩn. Không nên xác định lỗi nghiêm trọng bằng cách tìm từ “Error” trong message.

### 4.2. Source location độc lập với cách hiển thị

Vị trí nguồn nên lưu bằng cấu trúc có quy ước rõ:

~~~text
SourceLocation
  documentUri
  startLine
  startColumn
  endLine
  endColumn
~~~

Cần thống nhất chỉ số dòng và cột bắt đầu từ 0 hay 1, cột tính theo byte, code point hay UTF-16 code unit, và range có bao gồm ký tự cuối hay không. Đây là chi tiết kỹ thuật của giao thức; bản địa hóa không nên thay đổi giá trị gốc.

Renderer có thể trình bày vị trí theo dạng file.dsl:8:14 hoặc theo cách thân thiện hơn, nhưng API vẫn giữ range chuẩn.

## 5. Message key và message catalog

**Message catalog** là tập hợp các bản dịch được tổ chức theo khóa. Mỗi locale có thể có một catalog riêng.

Ví dụ cấu trúc:

~~~text
messages/
  en/
    diagnostics.properties
  vi/
    diagnostics.properties
  ja/
    diagnostics.properties
~~~

Một catalog tiếng Anh:

~~~properties
parser.unexpected-token=Unexpected token {actual}; expected {expected}.
parser.missing-token=Expected {expected} before {actual}.
semantic.unknown-name=Unknown name {name}.
type.mismatch=Expected a value of type {expected}, but found {actual}.
~~~

Catalog tiếng Việt:

~~~properties
parser.unexpected-token=Token {actual} không được mong đợi; cần {expected}.
parser.missing-token=Cần {expected} trước {actual}.
semantic.unknown-name=Không tìm thấy tên {name}.
type.mismatch=Cần giá trị có kiểu {expected}, nhưng nhận được {actual}.
~~~

Các message key phải ổn định và có ý nghĩa. Không nên dùng câu dịch làm key vì khi sửa bản dịch sẽ phải sửa mọi nơi tham chiếu.

### 5.1. Quy tắc đặt message key

Nên đặt key theo nhóm chức năng và loại lỗi:

- lexer.invalid-character
- parser.unexpected-token
- parser.missing-token
- semantic.unknown-name
- semantic.duplicate-declaration
- type.mismatch
- constraint.out-of-range
- runtime.action-not-available

Tên key nên ngắn, có cấu trúc và không phụ thuộc ngôn ngữ. Tránh key quá chung như error1 hoặc key chứa nguyên câu thông báo.

### 5.2. Một key có thể có nhiều biến thể theo ngữ cảnh

Không nên tái sử dụng một key nếu cùng từ ngữ nhưng ý nghĩa hoặc ngữ cảnh khác nhau khiến bản dịch cần cách diễn đạt khác.

Ví dụ, từ “type” có thể chỉ kiểu dữ liệu hoặc loại một đối tượng. Nếu ngữ cảnh khác nhau, dùng key và mô tả riêng để người dịch chọn thuật ngữ đúng.

### 5.3. Ghi chú cho người dịch

Catalog nên có tài liệu ngữ cảnh cho từng key:

~~~text
Key: type.mismatch
Meaning: A value or expression has a type incompatible with the expected type.
Arguments:
  expected: human-readable type name
  actual: human-readable type name
Context: Shown next to the expression in the DSL editor.
English example: Expected Integer, but found String.
~~~

Ghi chú giúp người dịch hiểu message nói về kiểu dữ liệu, không phải loại sự vật thông thường. Nó cũng làm rõ placeholder, giới hạn độ dài và vị trí hiển thị.

## 6. Placeholder và tham số có kiểu

Thông báo thường cần chèn tên, kiểu dữ liệu, token, số lượng hoặc giá trị. Những phần này được biểu diễn bằng placeholder.

Ví dụ:

~~~text
semantic.unknown-name=Unknown name {name}.
~~~

Khi phát diagnostic:

~~~text
messageKey = semantic.unknown-name
arguments.name = customerAdress
~~~

Renderer có thể tạo:

~~~text
Unknown name customerAdress.
~~~

hoặc:

~~~text
Không tìm thấy tên customerAdress.
~~~

### 6.1. Dùng tên placeholder thay vì vị trí khi có thể

Placeholder có tên như {expected} và {actual} giúp dễ đọc và ít phụ thuộc thứ tự tham số.

Nếu dùng placeholder đánh số {0}, {1}, người dịch có thể cần đảo thứ tự trong câu nhưng phải nhớ vị trí nào đại diện cho giá trị nào. Một số thư viện cho phép tham số có tên; nếu thư viện không hỗ trợ, có thể dùng một lớp định dạng riêng.

### 6.2. Tham số phải có kiểu và ý nghĩa rõ

Không nên truyền mọi thứ dưới dạng chuỗi tùy ý. Một argument có thể là:

- Identifier: tên do người dùng khai báo.
- TokenDisplay: cách trình bày token trong message.
- TypeDisplay: tên kiểu đã định dạng.
- Integer hoặc Decimal: số lượng hoặc giới hạn.
- DateTime: thời điểm cần định dạng theo locale.
- Path: đường dẫn tệp.
- List: danh sách giá trị cần pluralize hoặc liệt kê.

Thông tin kiểu cho phép renderer chọn cách định dạng phù hợp và tránh lỗi như định dạng số theo locale sai hoặc dịch nhầm tên identifier.

### 6.3. Không dịch tên do người dùng đặt

Nếu người dùng khai báo:

~~~text
entity CustomerOrder {
  property deliveryDate: Date
}
~~~

Tên CustomerOrder và deliveryDate phải được giữ nguyên khi xuất hiện trong thông báo. Chúng là identifier trong mã nguồn, không phải nội dung ngôn ngữ tự nhiên cần dịch.

Có thể thêm mô tả bản địa hóa xung quanh identifier:

~~~text
Không tìm thấy thuộc tính deliveryDate trong thực thể CustomerOrder.
~~~

Không nên đổi tên thành ĐơnHàngKháchHàng trong thông báo nếu đó không phải tên thực tế trong DSL.

## 7. Pluralization và thông báo có số lượng

Một câu có số lượng thường không thể dịch bằng cách nối số với một từ cố định. Ngôn ngữ khác nhau có quy tắc số ít, số nhiều và các nhóm số lượng khác nhau.

Ví dụ, một thông báo tổng hợp:

~~~text
Found 1 error.
Found 4 errors.
~~~

Tiếng Việt thường không biến đổi danh từ theo số lượng như tiếng Anh:

~~~text
Tìm thấy 1 lỗi.
Tìm thấy 4 lỗi.
~~~

Nếu dùng một mẫu câu chung trong mọi ngôn ngữ, cần bảo đảm cấu trúc tự nhiên và hỗ trợ các quy tắc plural category của locale.

### 7.1. Plural category

Một số hệ thống định dạng hỗ trợ các nhóm như:

- zero
- one
- two
- few
- many
- other

Không phải locale nào cũng dùng tất cả nhóm. Renderer nên dựa vào thư viện quốc tế hóa có hỗ trợ quy tắc plural của locale thay vì tự viết điều kiện kiểu count == 1.

Ví dụ theo cú pháp minh họa kiểu ICU MessageFormat:

~~~text
{count, plural,
  =0 {No errors found.}
  one {Found # error.}
  other {Found # errors.}
}
~~~

Bản dịch tiếng Việt có thể là:

~~~text
{count, plural,
  other {Tìm thấy # lỗi.}
}
~~~

Ví dụ này cho thấy một locale có thể dùng cùng cách diễn đạt cho nhiều giá trị. Cú pháp chính xác phụ thuộc thư viện định dạng được chọn.

### 7.2. Tránh nối chuỗi để tạo câu

Cách sau dễ tạo câu sai trong ngôn ngữ khác:

~~~java
"Found " + count + " error" + (count == 1 ? "" : "s")
~~~

Nó gắn quy tắc ngữ pháp tiếng Anh vào code. Hãy để message catalog và thư viện pluralization quyết định toàn bộ mẫu câu.

### 7.3. Danh sách và số lượng nhiều loại lỗi

Nếu diagnostic summary cần hiển thị nhiều nhóm, nên dùng một mẫu cho từng loại hoặc một message tổng hợp có pluralization phù hợp. Không nên ghép nhiều mảnh câu được dịch độc lập nếu thứ tự và biến đổi ngữ pháp có thể khác nhau giữa các ngôn ngữ.

## 8. Định dạng số, ngày giờ và đơn vị theo locale

Locale ảnh hưởng cách người dùng đọc số, ngày, giờ, tiền tệ và một số đơn vị. Diagnostic nên định dạng dữ liệu theo locale được chọn, nhưng giá trị nội bộ phải giữ kiểu và độ chính xác ban đầu.

### 8.1. Số thập phân và phân cách hàng nghìn

Ví dụ cùng một giá trị số có thể hiển thị:

| Locale | Cách hiển thị minh họa |
| --- | --- |
| en-US | 1,234.56 |
| de-DE | 1.234,56 |
| vi-VN | 1.234,56 |

Không nên tự thay dấu chấm và dấu phẩy bằng các phép thay chuỗi đơn giản. Hãy dùng formatter theo locale vì quy tắc còn phụ thuộc số chữ số, dấu âm và cách nhóm.

### 8.2. Ngày và giờ

Cùng một thời điểm có thể được hiển thị theo nhiều định dạng. Ví dụ:

- en-US: 11/15/2026
- vi-VN: 15/11/2026

Định dạng ngày không làm thay đổi instant hoặc timestamp lưu trong diagnostic. Cần xác định múi giờ được dùng: múi giờ của máy, dự án, người dùng hay UTC. Với lỗi liên quan đến thời điểm thực thi, hiển thị múi giờ có thể cần thiết để tránh hiểu nhầm.

### 8.3. Đơn vị và độ chính xác

Thông báo có thể chứa thời lượng, kích thước, phần trăm hoặc tiền tệ:

~~~text
Timeout must be at least 250 ms.
~~~

Bản địa hóa có thể thay đổi dấu thập phân hoặc cách đặt khoảng trắng, nhưng đơn vị phải rõ. Không được tự chuyển đơn vị nếu việc chuyển đổi làm mất độ chính xác hoặc thay đổi ý nghĩa của giới hạn.

Với tiền tệ, cần biết mã tiền tệ thay vì chỉ có số. Giá trị 100 không đủ để biết là 100 VND, USD hay EUR.

### 8.4. Định dạng ngày giờ có thể tái lập

Log và báo cáo CI thường cần định dạng nhất quán để so sánh giữa máy. Có thể giữ timestamp ISO 8601 trong dữ liệu máy đọc được và chỉ bản địa hóa ở giao diện người dùng.

## 9. Locale và cách chọn ngôn ngữ hiển thị

**Locale** là cấu hình ngôn ngữ và vùng miền, thường được biểu diễn bằng language tag theo BCP 47, chẳng hạn vi-VN, en-US hoặc ja-JP.

Hệ thống cần xác định locale nào được dùng khi hiển thị diagnostic.

Một thứ tự ưu tiên minh họa:

1. Locale được truyền trực tiếp trong yêu cầu hoặc cấu hình của editor.
2. Locale được khai báo trong cấu hình dự án.
3. Biến môi trường hoặc thiết lập của tiến trình.
4. Locale hệ điều hành hoặc người dùng.
5. Locale mặc định của ứng dụng, chẳng hạn en.

Thứ tự cụ thể phải được tài liệu hóa. Một CLI chạy trong CI có thể ưu tiên cấu hình tường minh để log luôn ổn định; editor có thể ưu tiên locale giao diện người dùng.

### 9.1. Locale không chỉ là ngôn ngữ

en-US và en-GB đều là tiếng Anh nhưng có thể khác cách viết ngày, số và một số thuật ngữ. pt-BR và pt-PT có thể cần bản dịch riêng.

Nếu chỉ có catalog theo ngôn ngữ, ứng dụng có thể dùng fallback theo ngôn ngữ chung. Nếu có catalog vùng miền, cần chọn đúng mức cụ thể nhất.

### 9.2. Fallback khi thiếu bản dịch

Một chiến lược phổ biến:

~~~text
vi-VN
  |
  | không có key
  v
vi
  |
  | không có key
  v
en
  |
  | không có key
  v
message key hoặc thông báo dự phòng
~~~

Fallback cần được xác định ở cả cấp catalog và cấp key. Một catalog vi-VN có thể chỉ chứa một phần bản dịch; các key còn thiếu được lấy từ vi hoặc en.

Trong môi trường phát triển, thiếu key nên tạo cảnh báo để nhóm biết cần bổ sung bản dịch. Trong môi trường người dùng cuối, có thể hiển thị message dự phòng bằng ngôn ngữ mặc định cùng mã diagnostic.

### 9.3. Locale không hợp lệ

Nếu người dùng cấu hình locale không được hỗ trợ, hệ thống nên chọn fallback ổn định và có thể thông báo rằng locale không khả dụng. Không nên làm parser thất bại chỉ vì không tải được catalog.

### 9.4. Locale của máy và locale của dự án

Một nhóm có thể muốn cùng một tệp DSL tạo ra log CI nhất quán bất kể máy chạy ở quốc gia nào. Khi đó, cấu hình dự án hoặc CI có thể đặt locale cố định. Trong editor, người dùng vẫn có thể chọn locale riêng để đọc diagnostics.

Cần phân biệt locale dùng cho nội dung hiển thị với locale ảnh hưởng đến cách đọc dữ liệu. Cú pháp DSL thường nên có quy tắc literal độc lập với locale, ví dụ dấu chấm thập phân trong số nguồn không tự thay đổi theo thiết lập máy nếu grammar quy định như vậy.

## 10. Dịch thông báo cú pháp mà vẫn giữ nguyên ngôn ngữ DSL

Thông báo parser có một điểm đặc biệt: nó nói về cú pháp của một ngôn ngữ lập trình hoặc DSL. Một số phần là thuật ngữ có thể dịch; một số phần phải giữ nguyên để người dùng tìm thấy đúng văn bản trong mã nguồn.

Ví dụ:

~~~text
Unexpected token '}'.
Expected one of: IDENTIFIER, STRING, NUMBER.
~~~

Có thể bản địa hóa phần giải thích:

~~~text
Token '}' không được mong đợi.
Cần một trong các loại token: tên định danh, chuỗi hoặc số.
~~~

Tên token nội bộ như IDENTIFIER có thể được ánh xạ sang nhãn hiển thị, nhưng parser vẫn giữ token kind chuẩn.

### 10.1. Tên token nội bộ và nhãn người dùng

Có thể định nghĩa một bảng nhãn:

| Token kind | Nhãn tiếng Anh | Nhãn tiếng Việt |
| --- | --- | --- |
| IDENTIFIER | identifier | tên định danh |
| STRING | string literal | chuỗi ký tự |
| NUMBER | number literal | giá trị số |
| RIGHT_BRACE | closing brace | dấu ngoặc nhọn đóng |
| SEMICOLON | semicolon | dấu chấm phẩy |
| EOF | end of file | cuối tệp |

Không nên dịch tên token trong log máy hoặc API nếu công cụ bên ngoài cần dùng giá trị chuẩn. Nhãn bản địa hóa chỉ dành cho message renderer.

### 10.2. Giữ nguyên lexeme và identifier

Nếu parser gặp token custmerName do người dùng viết sai, thông báo có thể hiển thị nguyên lexeme:

~~~text
Không tìm thấy tên custmerName.
Có phải bạn muốn dùng customerName không?
~~~

Không dịch hoặc chuẩn hóa tên thành một từ khác. Nếu có gợi ý sửa tên, candidate phải trỏ đến symbol thực tế và không tự động áp dụng nếu chưa có xác nhận.

### 10.3. Không dịch cú pháp trong ví dụ sửa

Một gợi ý có thể chứa đoạn DSL:

~~~text
Expected:
property name: String
~~~

Từ khóa property, dấu hai chấm và tên kiểu là cú pháp DSL. Nếu DSL chỉ có một cú pháp, đoạn mã nên giữ nguyên giữa các locale. Phần giải thích xung quanh có thể được dịch.

## 11. Bản địa hóa expected-token và danh sách lựa chọn

Parser thường có thể liệt kê nhiều token được chấp nhận ở vị trí hiện tại. Danh sách này cần được trình bày tự nhiên.

Dữ liệu nội bộ:

~~~text
expected = [IDENTIFIER, STRING, NUMBER]
~~~

Một renderer có thể tạo:

~~~text
Expected one of: identifier, string literal, or number.
~~~

Tiếng Việt:

~~~text
Cần một trong các loại sau: tên định danh, chuỗi ký tự hoặc số.
~~~

Không nên tự nối danh sách bằng dấu phẩy theo một quy tắc cứng. Ngôn ngữ có thể cần từ nối, dấu câu hoặc cách nhóm khác nhau. Hãy dùng formatter danh sách theo locale nếu thư viện hỗ trợ.

### 11.1. Tránh liệt kê quá nhiều token

Một lỗi parser có thể có hàng chục token hợp lệ tiếp theo. Hiển thị tất cả sẽ khiến thông báo dài và khó hiểu.

Có thể nhóm token theo khái niệm người dùng:

- Giá trị: chuỗi, số, boolean.
- Tên: identifier.
- Cấu trúc: dấu ngoặc mở, dấu ngoặc đóng.
- Từ khóa: if, else, from.

Nếu danh sách dài, hiển thị một số lựa chọn phổ biến và phần “cùng các lựa chọn khác”, nhưng dữ liệu diagnostic đầy đủ vẫn nên giữ nguyên để editor hoặc công cụ có thể sử dụng.

### 11.2. Expected token không phải lúc nào cũng là gợi ý sửa

Thông báo “Expected )” mô tả điều parser cần để tiếp tục. Nó không nhất thiết có nghĩa người dùng chỉ cần chèn ) tại vị trí hiện tại; có thể lỗi thực sự nằm ở một biểu thức trước đó. Nên phân biệt mô tả cú pháp mong đợi với code action có thể áp dụng.

## 12. Bản địa hóa thông báo ngữ nghĩa và kiểu dữ liệu

Thông báo ngữ nghĩa thường có tên miền, kiểu, quan hệ và các khái niệm riêng. Bản dịch cần nhất quán về thuật ngữ và giữ nguyên identifier.

Ví dụ dữ liệu:

~~~text
code = DSL-SEM-004
messageKey = semantic.unknown-property
arguments:
  property = deliveryDate
  entity = Order
~~~

Tiếng Anh:

~~~text
Property deliveryDate does not exist on entity Order.
~~~

Tiếng Việt:

~~~text
Thực thể Order không có thuộc tính deliveryDate.
~~~

### 12.1. Thuật ngữ kiểu dữ liệu

Có thể chọn dịch hoặc giữ một số thuật ngữ:

| Thuật ngữ | Cách dùng có thể chọn |
| --- | --- |
| Integer | số nguyên |
| Decimal | số thập phân |
| Boolean | kiểu Boolean hoặc kiểu logic |
| String | chuỗi |
| Nullable | cho phép null |
| Collection | tập hợp hoặc collection |
| Type mismatch | không tương thích kiểu |

Điều quan trọng là dùng nhất quán trong tài liệu, editor và thông báo. Nếu một thuật ngữ được giữ bằng tiếng Anh trong tài liệu kỹ thuật, có thể giữ nguyên trong message hoặc cung cấp cách diễn đạt song ngữ.

### 12.2. Bản địa hóa thông báo có nhiều tên

Một diagnostic có thể chứa tên kiểu, tên property, giá trị thực tế và giá trị mong đợi. Cần biết tham số nào là identifier và tham số nào là nhãn hiển thị.

Ví dụ:

~~~text
Expected value of type Decimal for property total, but found String.
~~~

Bản dịch cần thay đổi trật tự câu nếu tự nhiên hơn, nhưng phải giữ nguyên total, Decimal và String nếu đó là tên trong DSL hoặc kiểu dựng sẵn được công bố.

### 12.3. Gợi ý dựa trên tên gần giống

Nếu hệ thống tìm được tên tương tự, nên đưa gợi ý như một tham số có cấu trúc:

~~~text
unknownName = custmerName
suggestion = customerName
~~~

Renderer dịch câu dẫn, còn hai identifier giữ nguyên. Không nên nhúng sẵn câu “Did you mean…” trong thuật toán phân giải tên.

## 13. Thông báo nhiều dòng và related information

Một diagnostic có thể cần giải thích nhiều vị trí liên quan.

Ví dụ, khai báo trùng:

~~~text
entity Customer {
  property id: CustomerId
  property id: Integer
}
~~~

Diagnostic chính có thể chỉ vị trí khai báo thứ hai. Related information trỏ đến khai báo đầu tiên.

Tiếng Việt:

~~~text
Thuộc tính id đã được khai báo trong thực thể Customer.
Khai báo đầu tiên nằm tại dòng 2.
~~~

Dữ liệu nên tách thành:

- Message chính.
- Related location.
- Message cho related location.
- Source range của từng vị trí.

Không nên gộp tất cả thành một chuỗi nhiều dòng duy nhất nếu editor cần tô sáng từng vị trí hoặc điều hướng đến khai báo ban đầu.

### 13.1. Thứ tự thông tin

Ngôn ngữ khác nhau có thể cần trật tự câu khác nhau. Hãy để mỗi bản dịch kiểm soát toàn bộ mẫu thông báo, không ghép các đoạn dịch nhỏ theo thứ tự cố định trong code.

### 13.2. Thông báo dài và trợ giúp chi tiết

Một diagnostic nên có message ngắn tại vị trí lỗi. Giải thích dài hơn có thể đặt trong phần documentation, help hoặc related information.

Ví dụ:

- Message: Không tìm thấy tên customerAdress.
- Detail: Tên này không được khai báo trong phạm vi truy vấn hiện tại.
- Suggestion: Có phải bạn muốn dùng customerAddress?

Tách lớp nội dung giúp editor có thể hiển thị một dòng ngắn và mở rộng khi người dùng yêu cầu.

## 14. API và cách triển khai localization

Một kiến trúc thường gồm ba thành phần:

1. Diagnostic producer tạo diagnostic có cấu trúc.
2. Message catalog cung cấp mẫu thông báo theo locale.
3. Renderer định dạng tham số và tạo nội dung hiển thị.

### 14.1. Diagnostic producer

Ví dụ pseudocode:

~~~java
Diagnostic diagnostic = Diagnostic.builder()
    .code("DSL-PARSE-001")
    .severity(Severity.ERROR)
    .messageKey("parser.unexpected-token")
    .argument("actual", token.displayText())
    .argument("expected", TokenCategory.EXPRESSION)
    .location(token.location())
    .build();
~~~

Parser không chọn tiếng Việt hay tiếng Anh. Nó chỉ ghi nhận loại lỗi và dữ liệu cần thiết.

### 14.2. Message resolver

Một interface có thể có dạng:

~~~java
interface MessageResolver {
    String resolve(
        String messageKey,
        Map<String, Object> arguments,
        Locale locale
    );
}
~~~

Triển khai sẽ:

- Tìm catalog theo locale.
- Tìm message key.
- Chọn fallback nếu thiếu key.
- Định dạng placeholder theo kiểu.
- Trả về chuỗi đã bản địa hóa.

Nếu định dạng thất bại do thiếu placeholder hoặc sai kiểu, hệ thống cần fallback an toàn và ghi nhận lỗi catalog cho nhóm phát triển. Không nên làm mất diagnostic gốc chỉ vì message template có lỗi.

### 14.3. Ví dụ với Java ResourceBundle và MessageFormat

Java có thể dùng ResourceBundle để nạp catalog theo locale và MessageFormat để định dạng placeholder đánh số.

Catalog:

~~~properties
# messages_en.properties
parser.unexpected-token=Unexpected token {0}; expected {1}.
semantic.unknown-name=Unknown name {0}.
~~~

~~~properties
# messages_vi.properties
parser.unexpected-token=Token {0} không được mong đợi; cần {1}.
semantic.unknown-name=Không tìm thấy tên {0}.
~~~

Code minh họa:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");

ResourceBundle bundle =
    ResourceBundle.getBundle("messages", locale);

String pattern = bundle.getString("parser.unexpected-token");

MessageFormat formatter = new MessageFormat(pattern, locale);

String message = formatter.format(
    new Object[] {")", "một biểu thức"}
);
~~~

Kết quả:

~~~text
Token ) không được mong đợi; cần một biểu thức.
~~~

Đây là ví dụ đơn giản. MessageFormat dùng placeholder theo vị trí; khi cần placeholder có tên hoặc plural/select phức tạp, có thể xây lớp định dạng riêng hoặc dùng thư viện hỗ trợ ICU MessageFormat.

### 14.4. Dùng ICU MessageFormat khi cần quy tắc phức tạp

Các thông báo có plural, select hoặc lựa chọn theo giới tính/ngữ cảnh cần thư viện biết quy tắc locale. ICU MessageFormat là một lựa chọn phổ biến cho các mẫu này.

Ví dụ:

~~~text
{count, plural,
  one {Found # diagnostic.}
  other {Found # diagnostics.}
}
~~~

Mỗi locale có thể có các plural category khác nhau. Không nên tự cài đặt quy tắc số ít/số nhiều bằng điều kiện rải rác trong code.

## 15. Bản địa hóa trong CLI, IDE và API

Một DSL có thể được dùng qua nhiều giao diện. Mỗi giao diện có cách trình bày khác nhau nhưng nên dùng chung diagnostic model.

### 15.1. CLI

CLI thường hiển thị:

~~~text
config.dsl:8:14: error DSL-PARSE-001
Token ')' không được mong đợi; cần một biểu thức.
~~~

CLI có thể có tùy chọn locale:

~~~text
dsl check --locale vi-VN config.dsl
~~~

Cần định nghĩa thứ tự ưu tiên giữa tùy chọn CLI, biến môi trường và cấu hình dự án. Với CI, có thể cố định locale để log nhất quán.

### 15.2. IDE và Language Server

Editor có thể hiển thị:

- Message ngắn cạnh đoạn mã.
- Severity bằng biểu tượng hoặc màu.
- Hover với giải thích chi tiết.
- Related information trỏ đến khai báo liên quan.
- Quick fix hoặc code action.
- Tên lỗi và tài liệu theo locale.

Nếu dùng Language Server Protocol, diagnostic được gửi dưới dạng cấu trúc gồm range, severity, code, source, message và related information. Message có thể đã được bản địa hóa, nhưng code và range vẫn giữ định dạng chuẩn.

Một số editor có thể muốn tự chọn locale. Vì vậy, Language Server nên có cơ chế nhận locale từ client hoặc cấu hình rõ ràng thay vì luôn dùng locale của máy chủ.

### 15.3. API và định dạng máy đọc được

API có thể trả về dữ liệu:

~~~json
{
  "code": "DSL-SEM-004",
  "severity": "error",
  "messageKey": "semantic.unknown-property",
  "arguments": {
    "property": "deliveryDate",
    "entity": "Order"
  },
  "message": "Thực thể Order không có thuộc tính deliveryDate.",
  "range": {
    "startLine": 4,
    "startColumn": 8,
    "endLine": 4,
    "endColumn": 20
  }
}
~~~

Trường message có thể được bản địa hóa theo yêu cầu, còn code, messageKey, arguments và range giữ dạng có cấu trúc.

Nếu API cần hỗ trợ nhiều client, có thể cho phép client gửi locale trong header hoặc tham số yêu cầu. Không nên yêu cầu client phân tích message để biết loại lỗi.

### 15.4. Log và telemetry

Log phục vụ vận hành có thể cần thông điệp ổn định để tìm kiếm và tổng hợp. Có thể lưu:

- Diagnostic code.
- Message key.
- Locale.
- Arguments đã được lọc dữ liệu nhạy cảm.
- Source location.
- Message hiển thị nếu cần.

Không nên chỉ lưu câu đã dịch vì câu có thể thay đổi giữa phiên bản catalog. Mã lỗi và key giúp nhóm phân tích xu hướng qua nhiều locale.

## 16. Hỗ trợ hướng chữ và khả năng tiếp cận

Một số ngôn ngữ được viết từ phải sang trái (RTL), chẳng hạn tiếng Ả Rập và tiếng Hebrew. Khi message chứa identifier, đường dẫn hoặc đoạn DSL theo hướng trái sang phải, giao diện cần xử lý hỗn hợp hướng chữ (bidirectional text).

Ví dụ một câu RTL có chứa:

~~~text
Unknown property customerId in Order.dsl
~~~

Nếu không có biện pháp định hướng phù hợp, thứ tự hiển thị của dấu ngoặc, dấu hai chấm hoặc đường dẫn có thể gây nhầm lẫn.

Các giao diện nên:

- Dùng thuộc tính hoặc cơ chế bidi phù hợp của nền tảng.
- Đánh dấu đoạn identifier, path và code theo hướng hiển thị thích hợp.
- Không tự đảo chuỗi nguồn.
- Giữ source range theo dữ liệu gốc.

### 16.1. Độ dài bản dịch

Bản dịch có thể dài hơn hoặc ngắn hơn nguồn. Không nên giả định mọi message vừa một dòng hoặc có cùng chiều dài giữa các locale.

Editor cần cho phép wrap, mở rộng tooltip và hiển thị nội dung nhiều dòng. CLI cần tránh cắt message giữa placeholder hoặc mã lỗi.

### 16.2. Khả năng đọc bằng công nghệ hỗ trợ

Thông báo nên có câu chữ rõ ràng, không phụ thuộc hoàn toàn vào màu sắc. Severity cần có nhãn hoặc văn bản để screen reader nhận biết. Vị trí lỗi và gợi ý sửa nên được đọc theo thứ tự hợp lý.

## 17. Bảo mật và quyền riêng tư trong thông báo bản địa hóa

Thông báo lỗi có thể chứa dữ liệu do người dùng cung cấp, đường dẫn nội bộ, tên tài khoản, truy vấn hoặc thông tin nhạy cảm. Localization không được làm lộ dữ liệu ngoài ý muốn.

### 17.1. Không ghép chuỗi không an toàn

Không đưa trực tiếp nội dung không tin cậy vào HTML hoặc giao diện mà không escape theo ngữ cảnh. Một identifier có thể chứa ký tự đặc biệt được cho phép bởi DSL; khi hiển thị trên web, nó vẫn cần được escape phù hợp.

### 17.2. Không đưa bí mật vào message

Không hiển thị password, access token, khóa API hoặc giá trị cấu hình bí mật trong diagnostic. Có thể hiển thị tên trường hoặc một phần giá trị đã che nếu cần hỗ trợ người dùng.

### 17.3. Tách nội dung người dùng khỏi mẫu dịch

Message template nên được quản lý bởi ứng dụng. Giá trị do người dùng nhập chỉ là argument. Không coi giá trị đầu vào như một mẫu thông báo có thể thực thi placeholder hoặc format string.

### 17.4. Giữ log an toàn

Nếu log được gửi đến dịch vụ tập trung, cần lọc arguments có thể chứa dữ liệu cá nhân hoặc bí mật. Có thể lưu mã lỗi và loại dữ liệu thay vì lưu nguyên giá trị.

## 18. Quản lý catalog và quy trình dịch thuật

Bản địa hóa là một phần của vòng đời phát triển DSL. Khi thêm diagnostic mới, cần thêm message key, nội dung mặc định và metadata cho người dịch.

Một quy trình có thể gồm:

1. Nhà phát triển tạo diagnostic code và message key.
2. Catalog mặc định được cập nhật.
3. Tài liệu ngữ cảnh và danh sách placeholder được bổ sung.
4. Người dịch tạo hoặc cập nhật bản dịch.
5. Công cụ kiểm tra key còn thiếu, placeholder không khớp và cú pháp catalog.
6. Bản dịch được đóng gói cùng phiên bản DSL.
7. Runtime chọn locale và dùng fallback nếu catalog chưa đầy đủ.

### 18.1. Quản lý trạng thái bản dịch

Có thể theo dõi các trạng thái:

- New: key mới, chưa dịch.
- Translated: đã có bản dịch.
- Reviewed: đã được người có chuyên môn rà soát.
- Deprecated: không còn dùng nhưng vẫn cần hỗ trợ trong thời gian chuyển tiếp.

Trạng thái này có thể được lưu trong công cụ quản lý bản dịch hoặc metadata riêng. Không nên nhúng trạng thái vào nội dung message.

### 18.2. Placeholder phải khớp giữa các locale

Nếu bản nguồn dùng {expected} và {actual}, bản dịch phải tham chiếu đúng các argument đó. Công cụ build có thể phát hiện placeholder bị thiếu, sai chính tả hoặc dùng tham số không tồn tại.

### 18.3. Thay đổi message key

Khi đổi key, cần cập nhật mọi nơi phát diagnostic và catalog. Nếu code hoặc plugin bên ngoài phụ thuộc key, có thể cần giữ alias hoặc deprecation period.

Message key và diagnostic code là giao diện có thể được công cụ khác sử dụng. Thay đổi chúng cần được quản lý như thay đổi API.

### 18.4. Không ghép các mảnh câu quá nhỏ

Tách một câu thành nhiều mảnh như “Expected”, tên kiểu, “but found” và kiểu thực tế rồi ghép trong code có thể làm bản dịch sai ngữ pháp. Mỗi message nên là một mẫu câu hoàn chỉnh với placeholder rõ ràng, để người dịch kiểm soát trật tự và dấu câu.

## 19. Kiểm thử bản địa hóa thông báo

Kiểm thử localization không chỉ kiểm tra rằng catalog có tồn tại. Cần bảo đảm message có thể được định dạng, placeholder đúng và diagnostic vẫn giữ nguyên dữ liệu kỹ thuật.

### 19.1. Kiểm thử catalog

Kiểm tra:

- Mọi message key đang được sử dụng có bản dịch mặc định.
- Placeholder trong bản dịch khớp với placeholder được khai báo.
- Không có key trùng hoặc key không hợp lệ.
- Mẫu plural/select có cú pháp hợp lệ.
- Catalog được nạp đúng theo locale.
- Fallback hoạt động khi thiếu locale hoặc key.

### 19.2. Kiểm thử định dạng

Dùng dữ liệu đại diện:

- Identifier có dấu gạch dưới hoặc Unicode.
- Tên kiểu dài.
- Số âm và số thập phân.
- Số lượng 0, 1, 2 và nhiều hơn.
- Ngày giờ gần ranh giới ngày hoặc múi giờ.
- Danh sách token dài.
- Đường dẫn có dấu cách hoặc ký tự Unicode.

Kiểm tra message không bị lỗi placeholder, không làm mất ký tự và vẫn dễ đọc.

### 19.3. Kiểm thử theo locale

Cùng một diagnostic nên được kiểm tra trên các locale được hỗ trợ:

~~~text
Diagnostic:
  code = DSL-PARSE-001
  actual = RIGHT_PAREN
  expected = EXPRESSION

Locale en:
  Unexpected token ')'; expected an expression.

Locale vi:
  Token ')' không được mong đợi; cần một biểu thức.
~~~

Điều cần bảo đảm là code, severity và source range không đổi giữa các locale.

### 19.4. Snapshot test

Snapshot test có thể lưu kết quả hiển thị theo locale để phát hiện thay đổi ngoài dự kiến. Khi bản dịch được cập nhật có chủ ý, snapshot cần được cập nhật cùng thay đổi.

Không nên chỉ dùng snapshot thay cho kiểm tra cấu trúc. Một message có thể giống về văn bản nhưng range hoặc mã lỗi bị sai; cần kiểm tra các trường diagnostic riêng.

### 19.5. Kiểm thử fallback và catalog thiếu

Mô phỏng trường hợp vi-VN thiếu một key nhưng vi hoặc en có key. Kiểm tra ứng dụng chọn fallback đúng và ghi nhận thiếu bản dịch theo cách phù hợp.

## 20. Những lỗi thiết kế thường gặp

**Dịch câu lỗi ngay trong parser.** Điều này làm logic cú pháp phụ thuộc ngôn ngữ và khó mở rộng. Hãy phát diagnostic có cấu trúc rồi bản địa hóa ở lớp trình bày.

**Dùng message làm mã lỗi.** Câu chữ có thể thay đổi theo locale hoặc phiên bản. Hãy dùng diagnostic code ổn định.

**Nối chuỗi để tạo câu.** Trật tự từ và quy tắc số nhiều khác nhau giữa các ngôn ngữ. Hãy dùng message template hoàn chỉnh và formatter theo locale.

**Dịch identifier hoặc token nguồn.** Người dùng cần tìm đúng tên trong DSL. Giữ nguyên lexeme và chỉ dịch phần giải thích.

**Dùng một quy tắc plural cho mọi ngôn ngữ.** Các locale có plural category khác nhau. Dùng thư viện hỗ trợ CLDR/ICU.

**Để parser tự định dạng số và ngày theo locale máy.** Cú pháp nguồn cần có quy tắc ổn định. Locale chủ yếu ảnh hưởng phần hiển thị, trừ khi DSL đặc tả rõ quy tắc khác.

**Không có fallback.** Một key thiếu có thể khiến diagnostic biến mất hoặc làm quá trình phân tích thất bại. Cần catalog mặc định và fallback xác định.

**Không lưu source range.** Một câu dịch đúng nhưng không chỉ vị trí khiến người dùng khó sửa lỗi. Hãy lưu range độc lập với message.

**Chỉ kiểm thử một ngôn ngữ.** Placeholder hoặc câu plural có thể hỏng ở locale khác. Cần kiểm thử catalog và formatter trên tất cả locale được hỗ trợ.

**Để bản dịch làm thay đổi dữ liệu máy đọc được.** Code, severity, token kind và range phải ổn định để công cụ không phụ thuộc câu chữ.

## 21. Quy trình thiết kế thông báo có thể bản địa hóa

Khi thêm một diagnostic mới cho DSL, có thể thực hiện theo các bước:

### Bước 1: Xác định sự kiện và loại lỗi

Ghi rõ thành phần phát hiện lỗi, điều kiện xảy ra và vị trí nguồn liên quan. Phân biệt lỗi cú pháp, lỗi ngữ nghĩa, lỗi kiểu, cảnh báo và lỗi runtime.

### Bước 2: Định nghĩa diagnostic code ổn định

Chọn mã không phụ thuộc câu chữ hoặc locale. Ghi rõ mã được dùng trong tài liệu, CLI, IDE và API như thế nào.

### Bước 3: Thiết kế arguments có kiểu

Xác định các dữ liệu cần để giải thích lỗi. Phân biệt identifier, token display, type display, số lượng, thời gian và đường dẫn.

### Bước 4: Viết message key và mẫu nguồn

Tạo một mẫu câu hoàn chỉnh, ngắn gọn, có ngữ cảnh. Tránh nối các mảnh câu trong code.

### Bước 5: Cung cấp ghi chú dịch thuật

Giải thích ý nghĩa kỹ thuật, placeholder, đối tượng đọc, giới hạn hiển thị và thuật ngữ nên giữ nguyên.

### Bước 6: Bổ sung catalog theo locale

Dịch message theo ngữ pháp tự nhiên của từng ngôn ngữ. Dùng formatter hỗ trợ plural, select và định dạng số/ngày giờ.

### Bước 7: Chọn locale và fallback

Xác định nguồn locale, thứ tự ưu tiên, quy tắc chuẩn hóa language tag và hành vi khi thiếu catalog hoặc key.

### Bước 8: Tạo renderer cho từng giao diện

CLI, editor, API và log có thể trình bày khác nhau nhưng dùng chung diagnostic model. Giữ code và source range ở dạng máy đọc được.

### Bước 9: Kiểm thử bản dịch và dữ liệu

Kiểm tra placeholder, plural, locale fallback, Unicode, identifier, source range và tính ổn định của diagnostic code.

### Bước 10: Quản lý thay đổi theo phiên bản

Khi thêm hoặc sửa message key, cập nhật catalog, tài liệu và các client liên quan. Đánh giá ảnh hưởng nếu diagnostic code hoặc schema arguments thay đổi.

## 22. Ví dụ tổng hợp: bản địa hóa lỗi trong DSL mô hình đơn hàng

Giả sử DSL có khai báo:

~~~text
entity Order {
  property id: OrderId
  property total: Decimal
}

query expensiveOrders {
  from Order
  where total > "100"
}
~~~

Parser có thể phân tích cú pháp thành công. Bước kiểm tra kiểu phát hiện total có kiểu Decimal nhưng literal "100" có kiểu String.

Diagnostic có cấu trúc:

~~~json
{
  "code": "DSL-TYPE-012",
  "severity": "error",
  "messageKey": "type.incompatible-operands",
  "arguments": {
    "operator": ">",
    "leftType": "Decimal",
    "rightType": "String"
  },
  "location": {
    "startLine": 6,
    "startColumn": 18,
    "endLine": 6,
    "endColumn": 23
  }
}
~~~

Catalog tiếng Anh:

~~~properties
type.incompatible-operands=Operator {operator} cannot compare {leftType} with {rightType}.
~~~

Catalog tiếng Việt:

~~~properties
type.incompatible-operands=Toán tử {operator} không thể so sánh kiểu {leftType} với kiểu {rightType}.
~~~

Thông báo tiếng Anh:

~~~text
Operator > cannot compare Decimal with String.
~~~

Thông báo tiếng Việt:

~~~text
Toán tử > không thể so sánh kiểu Decimal với kiểu String.
~~~

Editor có thể hiển thị message cạnh biểu thức "100", trong khi API vẫn trả về DSL-TYPE-012, arguments và source range. Người dùng có thể sửa literal thành số:

~~~text
where total > 100
~~~

Diagnostic biến mất sau khi phân tích lại. Nếu locale thay đổi từ en-US sang vi-VN, cùng một lỗi trước khi sửa sẽ được diễn đạt bằng ngôn ngữ mới, nhưng mã lỗi và vị trí vẫn như cũ.

Ví dụ này thể hiện ranh giới giữa phân tích cú pháp, kiểm tra kiểu, dữ liệu diagnostic và lớp localization.

## 23. Kết luận

Bản địa hóa thông báo trong DSL là quá trình chuyển diagnostic có cấu trúc thành nội dung dễ hiểu theo locale của người dùng. Diagnostic nên giữ mã lỗi, severity, message key, arguments có kiểu và source range độc lập với câu chữ. Parser và semantic analyzer chỉ phát hiện vấn đề và cung cấp dữ liệu; message resolver chọn catalog, áp dụng fallback và định dạng nội dung cho CLI, IDE, API hoặc log.

Khi thiết kế, cần dùng message key ổn định, không dịch identifier hoặc cú pháp nguồn, không ghép câu theo quy tắc của một ngôn ngữ, đồng thời hỗ trợ pluralization, định dạng số/ngày giờ, locale fallback và nội dung nhiều dòng. Catalog cần có ghi chú ngữ cảnh, kiểm tra placeholder và quy trình quản lý bản dịch theo phiên bản.

Một hệ thống chẩn đoán được bản địa hóa tốt giúp người dùng hiểu và sửa lỗi bằng ngôn ngữ quen thuộc mà vẫn giữ được dữ liệu kỹ thuật nhất quán cho parser, editor, CI và các công cụ tự động.

