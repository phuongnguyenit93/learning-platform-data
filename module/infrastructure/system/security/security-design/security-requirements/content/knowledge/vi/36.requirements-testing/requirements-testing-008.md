# Input validation test: kiểm chứng yêu cầu bảo mật đối với dữ liệu đầu vào

## 1. Kiểm thử đầu vào cần chứng minh điều gì?

Input validation test kiểm chứng việc hệ thống chỉ chấp nhận dữ liệu đáp ứng hợp đồng đầu vào và quy tắc nghiệp vụ đã xác định, đồng thời xử lý dữ liệu không hợp lệ theo cách có kiểm soát.

Trong đặc tả bảo mật, mục tiêu không dừng ở câu “nhập sai thì báo lỗi”. Cần xác định:

- Dữ liệu nào được phép đi qua từng ranh giới tin cậy.
- Kiểu, cấu trúc, định dạng, miền giá trị và quan hệ nào bắt buộc.
- Dữ liệu được giải mã hoặc chuẩn hóa như thế nào trước khi đánh giá.
- Giới hạn tài nguyên nào phải được thực thi.
- Phản hồi, trạng thái và tác dụng phụ nào được phép khi đầu vào bị từ chối.

Ví dụ, API từ chối số lượng âm nhưng vẫn tạo công việc xử lý nền trước khi trả lỗi chưa đáp ứng yêu cầu “chỉ tạo công việc từ đầu vào hợp lệ”.

Một bộ kiểm thử tốt phải chứng minh cả hai phía: dữ liệu hợp lệ được chấp nhận đúng, dữ liệu không hợp lệ bị xử lý đúng. Nếu chỉ thử các chuỗi bất thường, nhóm có thể bỏ sót việc hệ thống từ chối nhầm tên có dấu hoặc âm thầm ép một chuỗi thành số.

Bài học tập trung vào cách chuyển yêu cầu đầu vào thành các phân vùng dữ liệu, giá trị biên, assertion và bằng chứng có thể kiểm tra lại.

## 2. Phân biệt các lớp kiểm tra

Dữ liệu có thể đi qua nhiều lớp, mỗi lớp có trách nhiệm khác nhau:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Giải mã và parse | Dữ liệu có đọc được theo định dạng đã chọn không? | Body UTF-8 có thể parse thành một JSON object |
| Cấu trúc và kiểu | Các trường, kiểu và mức lồng có đúng hợp đồng không? | `maxRows` là số nguyên, không phải chuỗi |
| Cú pháp trường | Biểu diễn của một trường có đúng dạng không? | Mã báo cáo chỉ có các ký tự ASCII đã cho phép |
| Ngữ nghĩa và quan hệ | Giá trị có hợp lệ trong nghiệp vụ không? | Ngày bắt đầu không sau ngày kết thúc |
| Xác thực và phân quyền | Ai gửi và có được thực hiện hành động trên phạm vi này không? | Người gọi có quyền tạo báo cáo cho workspace đích |
| Sử dụng an toàn tại nơi xử lý | Dữ liệu được đưa vào truy vấn, giao diện hoặc tệp đúng cách không? | Dùng truy vấn tham số hóa, mã hóa đầu ra theo ngữ cảnh |

Một workspace ID đúng định dạng chưa chứng minh người dùng có quyền với workspace đó. Một tiêu đề vượt qua validation cũng chưa chứng minh nó được hiển thị an toàn trong HTML.

Không nên coi input validation là lớp thay thế cho phân quyền, truy vấn tham số hóa hoặc mã hóa đầu ra. Các lớp này cần yêu cầu và kiểm chứng tương ứng.

### 2.1. Kiểm tra phía client và phía máy chủ

Kiểm tra phía client giúp người dùng nhận phản hồi sớm. Nó không bảo đảm mọi yêu cầu gửi đến máy chủ đều tuân thủ quy tắc.

Bộ thử cần gọi trực tiếp điểm vào phía máy chủ trong phạm vi được kiểm thử, bằng dữ liệu không hợp lệ mà giao diện có thể không cho nhập. Nếu sản phẩm có API, import, công việc nền hoặc kênh tích hợp khác, cần xác định ranh giới validation của từng đường.

Không tự suy ra rằng một bộ kiểm tra trên giao diện đã bảo vệ các đường này.

### 2.2. Kiểm tra trước khi tạo tác dụng phụ bị cấm

Các kiểm tra rẻ và giới hạn tài nguyên thường cần thực hiện sớm. Tuy nhiên, thứ tự cụ thể phải phù hợp kiến trúc và hợp đồng.

Điều quan trọng là dữ liệu chưa đáp ứng điều kiện không được gây tác động nghiệp vụ bị cấm, chẳng hạn:

- Ghi một bản ghi báo cáo hợp lệ.
- Đưa công việc xuất dữ liệu vào hàng đợi.
- Tạo tệp hoặc gọi dịch vụ bên ngoài.
- Gán trường nhạy cảm do phía gọi tự cung cấp.
- Làm lộ dữ liệu qua phản hồi hoặc log.

Audit từ chối, telemetry và counter bảo vệ có thể được phép thay đổi. Vì vậy, assertion cần nhắm vào tác dụng phụ nghiệp vụ, không mặc định mọi trạng thái hệ thống đều phải giữ nguyên.

## 3. Ví dụ hợp đồng: API tạo báo cáo

### 3.1. Bối cảnh

Một ứng dụng nhiều workspace nhận yêu cầu tạo báo cáo:

```text
POST /workspaces/{workspaceId}/reports
Content-Type: application/json
```

Người gọi phải có phiên hợp lệ và quyền tạo báo cáo trong workspace. Các test validation trong ví dụ dùng một người gọi đã thỏa các điều kiện đó, trừ khi test có mục tiêu riêng về tương tác giữa các lớp.

Body hợp lệ minh họa:

```json
{
  "reportCode": "RPT_2026_06",
  "title": "Báo cáo dự án tháng 6",
  "format": "csv",
  "period": {
    "fromDate": "2026-06-01",
    "toDate": "2026-06-30"
  },
  "maxRows": 1000,
  "includeArchived": false,
  "labels": ["noi-bo", "du-an-a"]
}
```

Các giá trị và giới hạn dưới đây là lựa chọn minh họa cho sản phẩm này. Không phải mọi API đều cần cùng quy tắc.

### 3.2. Quy tắc ở cấp request và parser

| Mã yêu cầu | Quy tắc |
| --- | --- |
| IV-REQ-01 | Chỉ chấp nhận kiểu nội dung JSON đã quy định; không đoán định dạng khác từ body |
| IV-REQ-02 | Body tối đa 16 KiB, tức 16.384 byte, đo trước parse JSON sau xử lý truyền tải; ví dụ này không hỗ trợ body nén |
| IV-PARSE-01 | Body phải là UTF-8 hợp lệ, parse được và có object ở gốc |
| IV-PARSE-02 | Từ chối khóa trùng trong cùng một object sau khi giải mã tên khóa |
| IV-PARSE-03 | Từ chối cấu trúc vượt độ sâu 4; object hoặc array gốc tính là mức 1, mỗi container bên trong tăng một mức |
| IV-SCHEMA-01 | Chỉ chấp nhận các trường đã khai báo, tại cả object gốc và object `period` |

Giới hạn trước parse giúp kiểm soát cả những đầu vào chưa đến được bước kiểm tra schema. Schema cuối chỉ có vài mức lồng không đồng nghĩa parser tự được bảo vệ trước một body lồng rất sâu.

### 3.3. Quy tắc từng trường

| Trường | Bắt buộc và kiểu | Quy tắc giá trị |
| --- | --- | --- |
| `reportCode` | Bắt buộc, string | Khớp toàn bộ mẫu `[A-Z][A-Z0-9_-]{0,31}`; không tự trim hoặc đổi hoa/thường |
| `title` | Bắt buộc, string Unicode hợp lệ | Chuẩn hóa NFC, sau đó có 1–120 Unicode code point; cấm U+0000–U+001F và U+007F |
| `format` | Bắt buộc, string | Chỉ nhận chính xác `csv` hoặc `json` |
| `period` | Bắt buộc, object | Chỉ có `fromDate` và `toDate`, cả hai bắt buộc |
| `period.fromDate` | Bắt buộc, string | Ngày lịch hợp lệ, đúng dạng ASCII `YYYY-MM-DD` |
| `period.toDate` | Bắt buộc, string | Cùng quy tắc biểu diễn ngày |
| `maxRows` | Bắt buộc, số nguyên | Từ 1 đến 10.000; hợp đồng ví dụ chỉ nhận token số nguyên thập phân, không nhận phần thập phân hoặc số mũ |
| `includeArchived` | Bắt buộc, boolean | Chỉ nhận giá trị boolean `true` hoặc `false`, không ép kiểu |
| `labels` | Không bắt buộc, array | Mặc định mảng rỗng khi thiếu; tối đa 10 phần tử, không trùng; mỗi phần tử khớp toàn bộ `[a-z0-9][a-z0-9-]{0,23}` |

Quy tắc bổ sung:

- Các trường bắt buộc không được nhận `null`.
- `labels: null` không tương đương với bỏ trường `labels`.
- Không tự biến string thành số, số thành boolean hoặc một phần tử thành array.
- `fromDate` không sau `toDate`.
- Khoảng báo cáo tối đa 31 ngày lịch, tính cả hai đầu mút.
- Chuỗi Unicode có surrogate đứng riêng không được coi là chuỗi Unicode hợp lệ trong hợp đồng này.
- NFC chỉ áp dụng cho `title`; không tự áp dụng cho token, chữ ký hoặc mọi trường khác.
- Không tự trim `title`. Hợp đồng này chưa đặt quy tắc riêng cấm tiêu đề chỉ gồm dấu cách; nếu nghiệp vụ cần cấm, phải bổ sung trước khi viết test tương ứng.
- Phía gọi không được thêm các trường như `ownerId`, `status` hoặc `workspaceId` vào body để điều khiển giá trị do máy chủ quản lý.

Vì hợp đồng `maxRows` phân biệt hình thức token số, parser hoặc bước kiểm tra phải giữ đủ thông tin để phân biệt `1000`, `1000.0` và `1e3`. Nếu parser đã âm thầm ép tất cả thành cùng một số nguyên, bước validation phía sau không thể tự chứng minh yêu cầu đó.

Một API khác có thể chấp nhận các biểu diễn có cùng giá trị số. Điều cần kiểm thử là hợp đồng đã chọn, không phải giả định của người viết test.

### 3.4. Phản hồi và tác dụng phụ

Hợp đồng minh họa chọn:

| Tình huống | Kết quả |
| --- | --- |
| Dữ liệu hợp lệ, người gọi có quyền | 202 và tạo đúng công việc tương ứng |
| Không parse được hoặc vi phạm quy tắc parser | 400 với lỗi có cấu trúc |
| Parse được nhưng sai schema hoặc quy tắc trường/nghiệp vụ | 422 với lỗi có cấu trúc |
| Body vượt giới hạn | 413 theo hợp đồng |
| Kiểu nội dung hoặc cơ chế nén không hỗ trợ | 415 theo hợp đồng |

Mã lỗi là lựa chọn của ví dụ, không phải quy tắc chung cho mọi sản phẩm. Request đồng thời vi phạm nhiều điều kiện cần được đánh giá theo thứ tự xử lý và hợp đồng thực tế; đừng viết test giả định thứ tự chưa được quy định.

Mọi request bị từ chối không được tạo báo cáo, job, tệp hoặc lời gọi xử lý bên ngoài từ dữ liệu đó. Phản hồi không được chứa stack trace nội bộ hoặc sao chép bí mật từ đầu vào.

Đối với request hợp lệ, phải kiểm tra dữ liệu lưu và đưa vào job đúng với quy tắc chuẩn hóa, giá trị mặc định và danh tính do máy chủ xác định.

## 4. Thiết kế phân vùng dữ liệu và giá trị biên

### 4.1. Phân vùng tương đương

Chia đầu vào thành các nhóm có kỳ vọng xử lý khác nhau. Với `maxRows`:

- Số nguyên trong miền cho phép.
- Số nguyên nhỏ hơn giới hạn.
- Số nguyên lớn hơn giới hạn.
- Token số có phần thập phân hoặc số mũ.
- String trông giống số.
- Boolean, `null`, array hoặc object.
- Thiếu trường.
- Số có biểu diễn quá lớn đối với kiểu lưu trữ thông thường.

Mỗi nhóm cần test đại diện; các giá trị gần ranh giới thường cần thêm test riêng.

Ví dụ, `"1000"` và `1000` không thuộc cùng nhóm kiểu. Nếu hệ thống nhận cả hai do tự ép kiểu trong khi hợp đồng cấm, test phải không đạt.

### 4.2. Giá trị biên

| Quy tắc | Giá trị cần thử |
| --- | --- |
| `maxRows` từ 1 đến 10.000 | 0, 1, 2, 9.999, 10.000, 10.001 |
| `title` dài 1–120 code point sau NFC | 0, 1, 119, 120, 121 code point |
| `reportCode` dài tối đa 32 ký tự ASCII | 1, 31, 32, 33 ký tự và sai ký tự đầu |
| `labels` tối đa 10 phần tử | 0, 1, 9, 10, 11 phần tử |
| Mỗi label dài tối đa 24 ký tự | 1, 23, 24, 25 ký tự |
| Body tối đa 16.384 byte | Dưới, đúng và trên ngưỡng, trong điều kiện parser/schema còn lại phù hợp |
| Khoảng báo cáo tối đa 31 ngày, tính cả hai đầu | 1, 30, 31, 32 ngày và khoảng đảo ngược |

Với body, có thể dùng whitespace hợp lệ của JSON để tạo kích thước gần ngưỡng mà không làm sai trường dữ liệu. Bộ thử phải tính byte thực sự gửi, gồm cả phần whitespace đó.

Nếu body lớn hơn ngưỡng đồng thời có cú pháp sai, test không cô lập được điều kiện kích thước. Hãy tạo một trường hợp chỉ vi phạm giới hạn đang kiểm tra trước.

### 4.3. Thiếu, rỗng và null là các trường hợp khác nhau

Các đầu vào sau có thể mang ý nghĩa khác nhau:

```json
{}
```

```json
{"labels": null}
```

```json
{"labels": []}
```

Đây chỉ là các mảnh minh họa; một request hoàn chỉnh còn phải có các trường bắt buộc khác.

Theo hợp đồng ví dụ, thiếu `labels` và mảng rỗng được chấp nhận, còn `null` bị từ chối. Với `title`, thiếu trường, `null` và string rỗng đều bị từ chối nhưng vì những điều kiện tương ứng.

Không để framework tự chọn ngữ nghĩa mặc định mà không có test xác nhận.

## 5. Unicode, độ dài và thứ tự xử lý

### 5.1. Một ký tự nhìn thấy có thể có nhiều cách biểu diễn

Cần phân biệt:

- **Byte:** kích thước biểu diễn khi truyền hoặc lưu.
- **Code unit:** đơn vị của một cách mã hóa, chẳng hạn UTF-16.
- **Code point:** điểm mã Unicode.
- **Grapheme cluster:** nhóm mà người dùng thường cảm nhận là một ký tự hiển thị.

Các đại lượng này không đồng nhất. Một emoji đơn giản có thể là một code point nhưng chiếm hai UTF-16 code unit và nhiều byte UTF-8. Một emoji ghép có thể gồm nhiều code point dù trông như một hình.

Nếu yêu cầu giới hạn `title` theo code point, không dùng độ dài UTF-16 hoặc số byte làm assertion thay thế.

### 5.2. Chuẩn hóa phải có phạm vi rõ

Một ký tự có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cơ sở cùng dấu kết hợp. NFC có thể đưa những biểu diễn tương đương thích hợp về cùng dạng.

Theo hợp đồng ví dụ:

**Giải mã chuỗi Unicode hợp lệ → NFC cho title → kiểm tra độ dài và ký tự cấm → dùng đúng giá trị đã kiểm tra.**

Bộ thử cần kiểm tra:

- Tên tiếng Việt hợp lệ được chấp nhận và giữ đúng nội dung.
- Hai biểu diễn tương đương theo NFC cho kết quả lưu mong đợi.
- Giới hạn 120 code point được đánh giá sau NFC.
- Ký tự điều khiển bị cấm không đi qua.
- Giá trị đưa vào job không khác giá trị đã validation.

Không chuẩn hóa hoặc trim password, token, chữ ký và định danh tùy ý chỉ vì `title` có bước NFC. Những trường đó cần hợp đồng riêng.

NFC cũng không tự giải quyết mọi trường hợp ký tự nhìn giống nhau hoặc lừa người dùng. Nếu sản phẩm cần chống nhầm lẫn định danh, phải có quy tắc và test tương ứng.

### 5.3. Không kiểm tra một dạng rồi sử dụng dạng khác

Một rủi ro thường gặp là dữ liệu bị giải mã, chuẩn hóa hoặc biến đổi thêm sau validation. Khi đó giá trị tới nơi xử lý có thể khác giá trị đã được đánh giá.

Test cần theo dõi biểu diễn tại các ranh giới có liên quan, không chỉ đầu vào và phản hồi lỗi. Đặc biệt với đường dẫn, định danh hoặc giá trị được truyền sang dịch vụ khác, các thành phần phải thống nhất cách diễn giải.

Không áp dụng lặp việc giải mã chỉ để “làm sạch thêm”. Số lần và nơi giải mã phải theo giao thức và thiết kế đã xác định.

## 6. Kiểm thử parser và cách diễn giải không thống nhất

### 6.1. Khóa trùng cần được kiểm tra trước khi mất thông tin

Một parser có thể chỉ giữ một giá trị khi gặp nhiều khóa cùng tên. Nếu bước kiểm tra phía trước và ứng dụng chọn giá trị khác nhau, kết quả xử lý có thể không thống nhất.

Mảnh body minh họa:

```json
{
  "maxRows": 1,
  "maxRows": 10000
}
```

Theo IV-PARSE-02, request chứa khóa trùng phải bị từ chối. Không được coi việc chọn “giá trị đầu” hoặc “giá trị cuối” là đáp ứng yêu cầu này.

Cần thử cả tên khóa được viết bằng escape nhưng giải mã thành cùng tên:

```json
{
  "maxRows": 1,
  "\u006daxRows": 10000
}
```

Hai mảnh trên cần được đưa vào request có đầy đủ các trường còn lại khi kiểm thử API, để lỗi thiếu trường không che việc kiểm tra khóa trùng. Thử thêm khóa trùng trong object `period`.

Bộ thử phải gửi được đúng body chứa khóa trùng. Nếu dùng một map rồi serialize, map có thể đã loại khóa trùng trước khi request tới hệ thống.

### 6.2. Trường lạ và gán thuộc tính ngoài hợp đồng

Thử bổ sung các trường như:

```json
{
  "ownerId": "OTHER-USER",
  "status": "COMPLETED",
  "workspaceId": "OTHER-WORKSPACE"
}
```

Đây là mảnh bổ sung vào body thử, không phải request hoàn chỉnh.

Theo hợp đồng ví dụ, server phải từ chối trường không khai báo. Sau đó phải kiểm tra không có đối tượng, job hoặc thuộc tính nhạy cảm nào bị gán từ các giá trị này.

Đồng thời, với request hợp lệ, kiểm tra owner và workspace thực sự đến từ nguồn danh tính, phân quyền và tham số đã được xác nhận của máy chủ.

Một sản phẩm có thể chọn bỏ qua trường lạ thay vì từ chối. Nếu vậy, cần quy định rõ và chứng minh các trường đó không tác động đến trạng thái. Không để cơ chế ánh xạ object tự quyết định chính sách.

### 6.3. Các lỗi hình thức cần thử

Theo phạm vi parser và giao thức đã chọn, bộ thử có thể bao gồm:

- JSON không hoàn chỉnh, dấu phân cách không hợp lệ hoặc dữ liệu thừa sau giá trị gốc.
- Array, string hoặc `null` ở gốc khi hợp đồng yêu cầu object.
- Chuỗi UTF-8 không hợp lệ.
- Escape không hợp lệ hoặc chuỗi chứa surrogate đứng riêng.
- Số có biểu diễn không được hợp đồng chấp nhận.
- Object hoặc array lồng quá sâu.
- Body quá lớn hoặc kiểu nội dung không hỗ trợ.

Với dữ liệu UTF-8 không hợp lệ, phải tạo request từ byte phù hợp. Chuyển dữ liệu qua một string encoder có thể thay byte lỗi bằng ký tự thay thế và làm test không còn thử điều kiện ban đầu.

Tương tự, test `1000.0` hoặc `1e3` phải bảo toàn token trên đường gửi. Một bộ serialize tự chuyển chúng thành `1000` sẽ làm mất tình huống cần kiểm tra.

### 6.4. Không trộn nguồn giá trị theo cách chưa được quy định

Nếu một endpoint nhận giá trị từ path, query, header và body, cần xác định nguồn nào có thẩm quyền và cách xử lý khi chúng mâu thuẫn.

Trong ví dụ, workspace được chọn qua path rồi kiểm tra quyền; body không có trường `workspaceId`. Không được để một trường body thay thế workspace đã được kiểm tra.

Với endpoint nhận tham số lặp trong query hoặc form, cần yêu cầu riêng về việc từ chối, nhận danh sách hay chọn một giá trị. Không áp dụng chính sách khóa trùng của JSON một cách ngầm định cho mọi giao thức.

## 7. Kiểm thử ngữ nghĩa và quan hệ giữa các trường

### 7.1. Ngày đúng dạng chưa chắc là ngày hợp lệ

Các trường hợp cần phân biệt:

| Giá trị | Kỳ vọng theo hợp đồng ví dụ |
| --- | --- |
| `2026-06-01` | Ngày hợp lệ |
| `2026-13-01` | Từ chối vì tháng không hợp lệ |
| `2026-02-29` | Từ chối vì ngày lịch không hợp lệ |
| `2028-02-29` | Ngày hợp lệ nếu các quan hệ khác đều thỏa |
| `2026-6-1` | Từ chối vì không đúng biểu diễn đã chọn |
| `2026-06-01T00:00:00Z` | Từ chối vì hợp đồng nhận ngày, không nhận timestamp |

Không kiểm tra ngày lịch chỉ bằng một regex nhận dạng chữ số. Cần cách parse và đánh giá ngày nghiêm ngặt, không tự cuộn một ngày không tồn tại sang tháng khác.

### 7.2. Từng trường hợp lệ nhưng cả request không hợp lệ

Ví dụ:

- `fromDate = 2026-06-30`, `toDate = 2026-06-01`: hai ngày hợp lệ nhưng thứ tự sai.
- `fromDate = 2026-06-01`, `toDate = 2026-07-01`: đúng 31 ngày tính cả hai đầu, được chấp nhận.
- `fromDate = 2026-06-01`, `toDate = 2026-07-02`: 32 ngày, bị từ chối.

Các test này phát hiện thiếu kiểm tra liên trường và lỗi lệch một đơn vị.

Với `labels`, từng chuỗi có thể đúng mẫu nhưng mảng vẫn không hợp lệ nếu vượt số phần tử hoặc có phần tử trùng. Hợp đồng ví dụ dùng các nhãn ASCII đúng mẫu và không tự đổi hoa/thường; cần kiểm tra đúng quy tắc đó.

### 7.3. Không nhầm dữ liệu đúng với quyền truy cập

Một request có schema hoàn toàn hợp lệ nhưng người gọi không có quyền tạo báo cáo vẫn phải bị xử lý theo yêu cầu phân quyền.

Để kiểm thử validation riêng, dùng người gọi có quyền. Để kiểm thử tương tác, viết test riêng chỉ rõ:

- Request đang vi phạm điều kiện nào.
- Lớp nào dự kiến xử lý trước.
- Có thông tin nào không được tiết lộ cho người chưa có quyền.
- Những tác dụng phụ nào bị cấm.

Không dùng một request đồng thời sai quyền, sai kiểu và quá lớn rồi kết luận cả ba lớp kiểm soát đã được kiểm chứng.

## 8. Input validation và các yêu cầu bảo mật liên quan

### 8.1. Chuỗi có dấu nháy chưa chắc phải bị từ chối

Một tiêu đề như:

```text
O'Reilly & <b>nội bộ</b>
```

không vi phạm quy tắc `title` đã nêu nếu độ dài và các điều kiện Unicode đều thỏa. Trong hợp đồng ví dụ, nó là dữ liệu văn bản.

Bộ thử cần kiểm tra hệ thống lưu đúng giá trị và không âm thầm xóa ký tự để “làm sạch”. Khi giá trị được dùng trong truy vấn hoặc hiển thị, cần kiểm chứng cơ chế an toàn tương ứng.

Chỉ cấm dấu nháy hoặc một danh sách chuỗi đáng ngờ không chứng minh đã ngăn injection. Ngược lại, chấp nhận một ký tự hợp lệ cũng không có nghĩa được phép ghép trực tiếp nó vào câu lệnh hoặc HTML.

### 8.2. Không dùng validation làm bằng chứng thay cho bảo vệ tại nơi sử dụng

| Nơi dữ liệu được sử dụng | Yêu cầu cần xét ngoài validation |
| --- | --- |
| Truy vấn dữ liệu | Tách dữ liệu khỏi cấu trúc câu lệnh bằng cơ chế phù hợp |
| Trang HTML hoặc giao diện | Mã hóa đầu ra đúng ngữ cảnh hiển thị |
| Tệp xuất | Xử lý an toàn theo định dạng và ứng dụng tiêu thụ |
| Đường dẫn hoặc tên tệp | Ràng buộc tài nguyên đích và phạm vi được phép |
| Địa chỉ dịch vụ bên ngoài | Chính sách đích được phép, không chỉ đúng dạng URL |
| Log và audit | Giới hạn dữ liệu, cấu trúc sự kiện và bảo vệ bí mật |

Một giá trị hợp lệ ở tầng biểu mẫu vẫn có thể bị dùng sai ở nơi xử lý. Traceability cần giữ liên kết giữa các yêu cầu này, thay vì đánh dấu tất cả đã đạt vì một test validation từ chối vài chuỗi.

### 8.3. Giới hạn tài nguyên cũng là điều kiện đầu vào

Kích thước body, độ sâu, số phần tử và độ dài chuỗi cần được kiểm tra tại điểm thích hợp.

Bộ thử có thể tạo dữ liệu gần giới hạn để đánh giá:

- Request bị chặn đúng mức mà không tạo tác dụng phụ.
- Parser không tạo lỗi không kiểm soát hoặc làm tiến trình dừng.
- Phản hồi không chứa chi tiết nội bộ.
- Các request hợp lệ khác tiếp tục được phục vụ trong điều kiện tải đã quy định.

Nếu cần kết luận về thời gian hoặc tài nguyên, phải có ngưỡng, điều kiện tải và cách đo. Một lần gọi “cảm thấy chậm” chưa đủ để kết luận vi phạm.

Kiểm tra biểu thức chính quy cũng cần chú ý độ dài đầu vào và dữ liệu bất lợi. Không dùng một thử nghiệm đơn lẻ để khẳng định mọi mẫu và mọi độ dài đều an toàn.

Nếu sản phẩm hỗ trợ body hoặc tệp nén, phải đặc tả giới hạn sau giải nén và cách xử lý tài nguyên liên quan. Không suy ra giới hạn nội dung xử lý chỉ từ kích thước truyền. Ví dụ xuyên suốt không hỗ trợ nén nên kiểm tra việc từ chối đúng hợp đồng.

## 9. Tổ chức một test case có thể thực thi

### 9.1. Mẫu đặc tả

```yaml
testId: IV-MAXROWS-UPPER-BOUND
requirementIds:
  - IV-SCHEMA-01
field: maxRows
preconditions:
  - "Người gọi có quyền tạo báo cáo trong workspace thử"
  - "Body hợp lệ ở mọi điều kiện khác"
mutation:
  rawValue: "10001"
  tokenType: "Số nguyên JSON"
expected:
  status: 422
  errorField: maxRows
  forbiddenBusinessEffects:
    - "Không tạo báo cáo"
    - "Không tạo job"
    - "Không tạo tệp hoặc lời gọi xử lý bên ngoài"
observations:
  - "Phản hồi"
  - "Dữ liệu nghiệp vụ gắn với lần thử"
  - "Hàng đợi và phụ thuộc mô phỏng"
```

Trong ví dụ, `rawValue` mô tả token gửi trên đường truyền. Đây là đặc tả test, không phải body API có trường `rawValue`.

Định danh yêu cầu cần đủ cụ thể cho từng quy tắc. Khi xây dựng danh mục thực tế, có thể gán ID riêng cho miền giá trị `maxRows`, độ dài `title` và quan hệ ngày để không gom mọi phát hiện vào một ID schema tổng quát.

### 9.2. Mã giả cho các biến thể đầu vào

```text
fixture = createAuthorizedWorkspaceFixture(runId)
validRequest = buildValidReportRequest()

positive = sendReportRequest(validRequest, fixture.session)
assert positive.status == 202
assert exactlyOneExpectedJobCreated(positive.traceId)

for case in validationCases:
    request = buildExactRequestBytes(validRequest, case.mutation)
    before = snapshotRelevantBusinessState(fixture.workspace)

    response = sendRawRequest(request, fixture.session)

    assert response.status == case.expectedStatus
    assert matchesStableErrorContract(response)
    assert doesNotExposeForbiddenData(response)

    boundary = waitForRelevantProcessingToSettle(response.traceId)
    if not boundary.reached:
        recordInconclusive(case, "Chưa đủ quan sát tác dụng phụ")
        continue

    assert businessStateUnchangedForRejectedInvocation(
        before, fixture.workspace, response.traceId
    )
    assert noReportJobFor(response.traceId)
    assert noExportArtifactFor(response.traceId)
    assert noExternalProcessingCallFor(response.traceId)

    recordAssertionsAndEvidence(case)
```

Đây là mã giả, không phải API của một thư viện cụ thể. Các assertion phải được bộ chạy thực thi và làm test không đạt khi điều kiện sai.

Fixture và snapshot phải tách được hoạt động của từng lần thử. Positive control đã tạo một job hợp lệ nên không thể assert tổng số job toàn hệ thống bằng không ở các test sau.

Mốc ổn định cần có cơ sở từ kiến trúc và khả năng điều khiển bộ thử. Không thấy job ngay sau phản hồi chưa đủ nếu vẫn còn tác vụ liên quan chưa hoàn tất.

### 9.3. Kiểm tra cả dữ liệu được chấp nhận

Với request hợp lệ, không chỉ assert 202:

- Title lưu đúng dạng NFC đã chốt.
- `labels` thiếu được đưa về mảng rỗng.
- Giá trị số không bị cắt, làm tròn hoặc thay đổi ngoài hợp đồng.
- Khoảng ngày đúng, không lệch do chuyển đổi không được yêu cầu.
- Owner và workspace đúng nguồn phía máy chủ.
- Job nhận đúng dữ liệu đã được validation.
- Mỗi request tạo đúng hiệu ứng theo quy tắc của endpoint.

Chấp nhận request nhưng lưu sai giá trị cũng là không đáp ứng yêu cầu.

## 10. Chọn tầng kiểm thử và đo độ bao phủ

### 10.1. Các tầng bổ sung cho nhau

| Tầng | Nên kiểm tra | Giới hạn |
| --- | --- | --- |
| Logic validation | Phân vùng, biên, ngày và quan hệ trường | Chưa chứng minh parser, middleware và ánh xạ dữ liệu đúng |
| Parser và binding | Byte lỗi, khóa trùng, số, kiểu và giới hạn cấu trúc | Chưa chứng minh không có tác dụng phụ nghiệp vụ |
| API tích hợp | Hợp đồng phản hồi, quyền fixture, trạng thái và job | Phải giữ đủ dữ liệu và quan sát có thể tái hiện |
| Luồng xử lý nền | Dữ liệu được truyền và dùng đúng sau validation | Cần điểm đồng bộ và trace liên quan |
| Đường nhập khác | Import, tích hợp hoặc thông điệp theo ranh giới tin cậy | Không tự được bao phủ bởi test API chính |

Một thành phần nội bộ có thể nhận dữ liệu từ nhiều nguồn. Cần quyết định nó được phép tin những gì và phải tự kiểm tra những gì. Không mặc định mọi thông điệp trong mạng nội bộ đều đã đi qua cùng một validator.

### 10.2. Kiểm thử dựa trên thuộc tính

Ngoài test ví dụ cố định, có thể tạo nhiều dữ liệu theo các thuộc tính:

- Mọi giá trị `maxRows` ngoài miền đều bị từ chối nếu các trường khác hợp lệ.
- Thứ tự trường trong object không làm đổi kết quả.
- Các dạng tương đương theo NFC của title cho giá trị chuẩn hóa mong đợi.
- Bổ sung một trường lạ làm request bị từ chối theo hợp đồng.
- Dữ liệu hợp lệ sau parse không bị biến đổi thành một giá trị chưa được kiểm tra.

Bộ sinh phải giữ được điều kiện nền. Nếu mọi request đều thiếu một trường bắt buộc, hàng nghìn lần bị từ chối vẫn chưa kiểm chứng miền giá trị đang nhắm tới.

Với test ngẫu nhiên hoặc fuzzing, lưu seed, byte đầu vào cần thiết và phiên bản bộ thử để tái hiện. Không lưu bí mật thật vào các tệp kết quả.

### 10.3. Ma trận bao phủ theo quy tắc

Có thể theo dõi mỗi quy tắc với các nhóm:

- Hợp lệ thông thường.
- Hợp lệ tại biên.
- Không hợp lệ ngay ngoài biên.
- Sai kiểu, thiếu và null.
- Biểu diễn khác nhau hoặc chuẩn hóa.
- Quan hệ với trường khác.
- Tác dụng phụ và dữ liệu được lưu.
- Giới hạn và hành vi lỗi của parser khi liên quan.

Số test nhiều không tự chứng minh chất lượng. Cần biết quy tắc nào còn chưa có assertion hoặc chưa chạy trên đúng đường vào.

## 11. Bằng chứng và cách đánh giá kết quả

Một kết quả hữu ích cần có:

| Nội dung | Mục đích |
| --- | --- |
| Requirement ID và test ID | Biết quy tắc nào được kiểm chứng |
| Build, cấu hình và phiên bản parser/validator liên quan | Tái lập cách diễn giải thực tế |
| Môi trường và fixture | Phân biệt lỗi quyền, dữ liệu nền và validation |
| Request đúng byte hoặc mô tả tái tạo được | Giữ token số, khóa trùng và encoding cần thử |
| Kỳ vọng và assertion thực tế | Giải thích vì sao đạt hoặc không đạt |
| Trace, job và dữ liệu đối chiếu | Kiểm tra tác dụng phụ |
| Nguồn và khoảng quan sát | Giới hạn kết luận |
| Dữ liệu đã che và quy tắc che | Bảo vệ thông tin trong bằng chứng |

Không tự lưu toàn bộ request nếu nó chứa dữ liệu nhạy cảm. Dùng fixture tổng hợp và giữ đúng phần cần thiết để tái hiện.

Phân biệt các kết quả:

- **PASS:** các assertion bắt buộc được quan sát và đạt.
- **FAIL:** có kết quả trái hợp đồng, chẳng hạn nhận chuỗi thay số hoặc vẫn tạo job sau từ chối.
- **ERROR:** bộ thử hoặc hạ tầng không thực hiện được phép thử như dự định.
- **INCONCLUSIVE:** thiếu quan sát để kết luận, chẳng hạn không biết xử lý nền đã ổn định chưa.
- **SKIPPED:** không thực hiện test và có lý do được ghi nhận.

Nếu mong đợi 422 nhưng nhận 500, không coi đó là “đã chặn đầu vào”. Cần xác định lỗi nằm ở sản phẩm hay môi trường và kiểm tra trạng thái, dữ liệu bị lộ hoặc tác động liên quan.

Khi sửa lỗi, lưu liên kết với phát hiện cũ và chạy lại các test bị ảnh hưởng. Nếu thay parser, chế độ ép kiểu hoặc quy tắc chuẩn hóa, cần đánh giá lại phần hợp đồng có thể đổi nghĩa.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ test phía giao diện | API hoặc đường import có thể không áp dụng cùng quy tắc | Kiểm tra từng điểm vào và ranh giới tin cậy |
| Chỉ có test đầu vào sai | Có thể từ chối nhầm dữ liệu hợp lệ | Thêm positive control, Unicode và giá trị tại biên |
| Dùng số ký tự nhưng không rõ đơn vị | Client và server hiểu giới hạn khác nhau | Chốt byte, code point hoặc đơn vị phù hợp |
| Để parser ép kiểu ngầm | Request sai hợp đồng vẫn được chấp nhận | Kiểm thử token và cấu hình binding thực tế |
| Tạo khóa trùng bằng map thông thường | Test mất dữ liệu trùng trước khi gửi | Dùng biểu diễn byte hoặc chuỗi giữ nguyên cấu trúc |
| Dùng regex nhận dạng ngày làm kiểm tra duy nhất | Ngày không tồn tại vẫn qua | Parse ngày nghiêm ngặt và kiểm tra quan hệ |
| Validation xong lại biến đổi thêm | Giá trị sử dụng khác giá trị đã kiểm tra | Thống nhất thứ tự và kiểm tra các ranh giới |
| Xóa ký tự đáng ngờ ở mọi string | Hỏng dữ liệu nhưng vẫn không chứng minh chống injection | Chốt hợp đồng trường và bảo vệ nơi sử dụng |
| Chỉ assert mã lỗi | Bỏ qua job, tệp hoặc trạng thái đã thay đổi | Đối chiếu tác dụng phụ nghiệp vụ |
| Dùng một request sai nhiều điều kiện | Không biết lớp nào thực sự được thử | Cô lập điều kiện trước, rồi thêm test tương tác |
| Coi schema nông là đã giới hạn parser | Body lồng sâu có thể gây tác động trước validation | Đặt và kiểm tra giới hạn tại parser |
| Tự đặt quy tắc chưa có trong yêu cầu | Test và sản phẩm tranh luận về kết quả | Làm rõ yêu cầu và cập nhật phiên bản trước |

## 13. Checklist chốt bộ input validation test

- [ ] Mỗi trường có kiểu, tính bắt buộc, miền giá trị và ý nghĩa null rõ.
- [ ] Độ dài có đơn vị đo và thứ tự chuẩn hóa được xác định.
- [ ] Có test hợp lệ, tại biên và ngay ngoài biên.
- [ ] Có test thiếu trường, sai kiểu, trường lạ và cấu trúc sai.
- [ ] Token số, khóa trùng và byte encoding được bảo toàn trong request thử.
- [ ] Ngày và các quan hệ liên trường được kiểm tra theo ngữ nghĩa.
- [ ] Giới hạn body, độ sâu và số phần tử được kiểm chứng đúng tầng.
- [ ] Không dùng validation thay cho phân quyền hoặc bảo vệ nơi sử dụng.
- [ ] Phản hồi lỗi có cấu trúc và không làm lộ dữ liệu bị cấm.
- [ ] Request bị từ chối không tạo tác dụng phụ nghiệp vụ ngoài hợp đồng.
- [ ] Request hợp lệ được lưu và truyền đi đúng giá trị đã kiểm tra.
- [ ] Môi trường, phiên bản, fixture và bằng chứng đủ để tái hiện.
- [ ] Các trường hợp chưa chạy hoặc thiếu quan sát không được tính là PASS.
