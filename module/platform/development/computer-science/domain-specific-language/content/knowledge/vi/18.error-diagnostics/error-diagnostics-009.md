# Mã lỗi và mức độ

Trong một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), công cụ thường phải thông báo khi chương trình có cú pháp sai, tham chiếu không hợp lệ, vi phạm quy tắc nghiệp vụ hoặc gặp vấn đề trong lúc thực thi. Những thông báo có cấu trúc này được gọi là **chẩn đoán** (*diagnostics*). Hai thông tin quan trọng trong một diagnostic là **mã lỗi** (*diagnostic/error code*) và **mức độ** (*severity*).

Mã lỗi định danh một loại vấn đề để người dùng, IDE, tài liệu và công cụ tự động có thể tham chiếu nhất quán. Mức độ cho biết vấn đề nghiêm trọng đến đâu và thường gợi ý người dùng cần xử lý như thế nào. Ví dụ, lỗi cú pháp khiến chương trình không thể phân tích thường có mức `error`, trong khi một cách viết cũ vẫn được hỗ trợ nhưng sắp bị loại bỏ có thể được báo ở mức `warning`.

Mã lỗi và mức độ có quan hệ nhưng không thay thế nhau. Mã trả lời “đây là loại vấn đề nào?”, còn mức độ trả lời “vấn đề này ảnh hưởng đến việc sử dụng chương trình đến mức nào?”. Một mã có thể được dùng cho nhiều lần xuất hiện của cùng loại vấn đề, còn mức độ có thể được cấu hình theo chính sách của dự án nếu công cụ hỗ trợ.

## 1. Diagnostic trong công cụ DSL

Một diagnostic là bản ghi có cấu trúc mô tả một vấn đề hoặc thông tin mà công cụ phát hiện trong mã nguồn. Nó có thể được tạo bởi lexer, parser, semantic analyzer, validator, compiler, formatter hoặc runtime.

Ví dụ, xét cấu hình DSL:

```text
service "catalog" {
    replicas = 0
    region = "unknown-region"
}
```

Công cụ có thể phát hiện:

- `replicas` phải là số nguyên dương, nhưng giá trị là `0`.
- `region` không thuộc danh sách vùng được hệ thống hỗ trợ.

Hai vấn đề này có thể có mã khác nhau vì chúng thuộc hai quy tắc miền khác nhau. Cả hai có thể cùng có severity `error` nếu chương trình không thể được triển khai với cấu hình đó.

Một diagnostic thường chứa những trường sau:

| Trường | Ý nghĩa |
|---|---|
| `code` | Mã định danh ổn định của loại vấn đề |
| `severity` | Mức độ nghiêm trọng hoặc mức độ cần chú ý |
| `message` | Mô tả ngắn gọn vấn đề bằng ngôn ngữ người dùng |
| `range` hoặc `span` | Vị trí nguồn cần đánh dấu |
| `source` | Thành phần tạo diagnostic, ví dụ parser hoặc validator |
| `relatedInformation` | Vị trí hoặc thông tin bổ sung liên quan |
| `help` hoặc `suggestion` | Hướng xử lý hoặc cách sửa có thể áp dụng |
| `tags` | Nhãn bổ sung như deprecated hoặc unnecessary |

Không phải công cụ nào cũng có tất cả trường này. Điều quan trọng là định dạng diagnostic phải đủ rõ để cả con người lẫn máy có thể sử dụng.

## 2. Mã lỗi là gì?

Mã lỗi là một định danh ngắn gọn, ổn định cho một loại diagnostic. Ví dụ:

```text
DSL1001: Unknown identifier 'customerId'
DSL2004: Expected closing brace '}'
DSL3012: Property 'replicas' must be greater than zero
```

Các mã trên chỉ là ví dụ minh họa. Một dự án cần tự định nghĩa dải mã, quy tắc đặt tên và ý nghĩa của từng mã.

### 2.1. Mã giúp nhận diện loại vấn đề

Thông điệp văn bản có thể thay đổi theo phiên bản, ngôn ngữ hiển thị hoặc ngữ cảnh. Mã lỗi giúp công cụ nhận diện cùng một loại vấn đề mà không phải phân tích câu chữ.

Ví dụ, IDE có thể biết `DSL3012` là quy tắc về giá trị thuộc tính `replicas`, từ đó cung cấp tài liệu hoặc quick fix tương ứng.

### 2.2. Mã không nên mã hóa toàn bộ thông điệp

Mã nên ngắn, ổn định và không phụ thuộc vào một câu thông báo cụ thể. Không nên tạo một mã mới cho mọi giá trị sai khác nhau nếu chúng cùng vi phạm một quy tắc.

Ví dụ, các trường hợp sau có thể dùng cùng mã:

```text
replicas = 0
replicas = -1
replicas = 2.5
```

Nếu cả ba đều vi phạm quy tắc “replicas phải là số nguyên dương”, chúng có thể dùng chung mã `DSL3012`, trong khi message chứa giá trị thực tế và lý do cụ thể.

### 2.3. Mã lỗi và mã định danh diagnostic

Một mã lỗi thường định danh **loại vấn đề**, không nhất thiết định danh duy nhất một lần xuất hiện. Một tệp có thể có nhiều diagnostic cùng mã nếu cùng quy tắc bị vi phạm ở nhiều vị trí.

Nếu cần định danh từng lần xuất hiện để cập nhật trong IDE, công cụ có thể tạo một diagnostic ID riêng dựa trên tài liệu, vị trí, mã quy tắc hoặc trạng thái phân tích. ID đó có vòng đời khác với mã lỗi công khai.

## 3. Thiết kế hệ thống mã lỗi

Một hệ thống mã tốt giúp người dùng tra cứu nhanh và giúp đội phát triển duy trì công cụ trong thời gian dài.

### 3.1. Chọn định dạng mã

Các định dạng phổ biến gồm:

```text
DSL1001
PARSER-004
SEM-012
CFG203
```

Một mã có thể gồm:

- Tiền tố sản phẩm hoặc ngôn ngữ, như `DSL`.
- Nhóm chức năng, như `LEX`, `PARSE`, `TYPE`, `MODEL`.
- Số thứ tự trong nhóm.

Ví dụ:

```text
DSL-PARSE-0042
DSL-TYPE-0017
DSL-MODEL-0008
```

Mã có cấu trúc giúp người đọc nhận biết nhóm vấn đề, nhưng không nên làm mã quá dài hoặc khiến việc phân loại trở nên cứng nhắc. Mã phải được tra cứu trong tài liệu hoặc registry chính thức.

### 3.2. Phân nhóm mã theo giai đoạn xử lý

Một DSL có thể chia mã theo giai đoạn phát hiện:

| Nhóm | Ví dụ tiền tố | Loại vấn đề |
|---|---|---|
| Phân tích từ vựng | `LEX` | Ký tự hoặc literal không hợp lệ |
| Phân tích cú pháp | `PARSE` | Thiếu token, sai cấu trúc grammar |
| Phân giải tên | `NAME` | Tên không tồn tại hoặc mơ hồ |
| Kiểu dữ liệu | `TYPE` | Không tương thích kiểu hoặc toán tử |
| Quy tắc miền | `RULE` | Vi phạm bất biến hoặc điều kiện nghiệp vụ |
| Cấu hình | `CONFIG` | Giá trị cấu hình sai hoặc thiếu |
| Deprecation | `DEPR` | Cú pháp hoặc API cũ sắp bị loại bỏ |
| Runtime | `RUN` | Lỗi khi thực thi chương trình |

Đây là một cách tổ chức tham khảo. Dự án có thể chọn nhóm khác miễn là phạm vi và quyền sở hữu mã được xác định rõ.

### 3.3. Dải số và quyền sở hữu

Nếu dùng mã dạng số, nên dành các dải cho từng nhóm hoặc module. Ví dụ:

| Dải mã giả định | Nhóm |
|---|---|
| `1000–1999` | Lexer và token |
| `2000–2999` | Parser và grammar |
| `3000–3999` | Tên, kiểu và phân tích ngữ nghĩa |
| `4000–4999` | Quy tắc miền và validation |
| `5000–5999` | Runtime và tích hợp |
| `6000–6999` | Cảnh báo tương thích và deprecation |

Không nên tái sử dụng mã đã công bố cho một ý nghĩa khác. Nếu quy tắc bị loại bỏ, có thể đánh dấu mã cũ là retired trong registry và giữ lịch sử tra cứu.

### 3.4. Mã ổn định qua phiên bản

Mã lỗi có thể được sử dụng trong:

- Tài liệu hướng dẫn và FAQ.
- Bộ lọc trong IDE.
- Cấu hình nâng severity thành error.
- Script CI phân loại vấn đề.
- Báo cáo lỗi và telemetry.
- Hệ thống hỗ trợ người dùng.

Nếu cùng mã đổi ý nghĩa giữa các phiên bản, các tích hợp này có thể xử lý sai. Vì vậy, nên giữ ý nghĩa mã ổn định. Nếu bản chất quy tắc thay đổi đáng kể, cân nhắc tạo mã mới hoặc ghi rõ thay đổi trong lịch sử.

## 4. Mức độ của diagnostic

Severity mô tả mức độ nghiêm trọng hoặc mức độ cần chú ý của một diagnostic. Một bộ mức độ phổ biến có thể gồm:

1. `error` – lỗi làm chương trình hoặc một phần quan trọng không hợp lệ.
2. `warning` – vấn đề có thể gây lỗi, hành vi không mong muốn hoặc rủi ro trong tương lai, nhưng công cụ vẫn có thể tiếp tục.
3. `information` – thông tin hữu ích về cách công cụ hiểu hoặc xử lý chương trình.
4. `hint` – gợi ý nhỏ về cách viết, cải thiện hoặc đơn giản hóa mã.

Một số hệ thống còn có `fatal`, `critical`, `note`, `debug` hoặc `off`. Những mức này không phải chuẩn thống nhất giữa mọi DSL; cần định nghĩa rõ thứ tự và hành vi của chúng.

### 4.1. Error

`error` được dùng khi công cụ xác định chương trình không hợp lệ theo quy tắc bắt buộc hoặc không thể tiếp tục một thao tác cần thiết.

Ví dụ:

```text
service "catalog" {
    replicas = "three"
}
```

Nếu `replicas` phải là số nguyên, giá trị chuỗi khiến cấu hình không hợp lệ. Validator có thể phát:

```text
DSL-TYPE-0017 error: property 'replicas' expects Integer, found String
```

Trong chế độ compiler nghiêm ngặt, error thường làm bước biên dịch hoặc xác thực thất bại. Tuy nhiên, một IDE vẫn có thể tiếp tục phân tích phần còn lại để hiển thị thêm diagnostic.

### 4.2. Warning

`warning` cảnh báo một vấn đề đáng chú ý nhưng chưa nhất thiết ngăn công cụ tiếp tục.

Ví dụ:

```text
service "catalog" {
    legacyNetworkMode = true
}
```

Nếu `legacyNetworkMode` vẫn được hỗ trợ nhưng đã lỗi thời, công cụ có thể báo:

```text
DSL-DEPR-0003 warning: 'legacyNetworkMode' is deprecated; use 'network.mode'
```

Warning thường được dùng cho:

- API hoặc cú pháp sắp bị loại bỏ.
- Giá trị có thể gây hành vi không mong muốn.
- Cấu hình thiếu tối ưu nhưng vẫn hợp lệ.
- Khai báo có khả năng không bao giờ được sử dụng.
- Rủi ro tương thích hoặc bảo trì.

Warning cần được chọn lọc. Nếu quá nhiều cảnh báo không quan trọng, người dùng có thể bỏ qua cả những cảnh báo thực sự cần xử lý.

### 4.3. Information

`information` cung cấp thông tin hữu ích nhưng không nhất thiết chỉ ra lỗi hoặc rủi ro.

Ví dụ:

```text
DSL-INFO-0002 information: module 'analytics' was resolved from dependency version 2.1
```

Thông tin này có thể giúp người dùng hiểu công cụ đã chọn module hoặc cấu hình nào. Không nên dùng information để báo lỗi bắt buộc sửa.

### 4.4. Hint

`hint` thường gợi ý cải thiện nhỏ, ví dụ dùng cú pháp ngắn hơn hoặc loại bỏ thành phần thừa.

Ví dụ:

```text
DSL-STYLE-0010 hint: parentheses around this expression are unnecessary
```

Hint có thể đi kèm quick fix. Người dùng thường có thể bỏ qua mà không ảnh hưởng tính hợp lệ của chương trình.

### 4.5. Fatal hoặc critical

Một số công cụ dùng `fatal` hoặc `critical` cho lỗi nghiêm trọng khiến toàn bộ tiến trình không thể tiếp tục, ví dụ không đọc được tệp cấu hình khởi động hoặc không nạp được grammar cần thiết.

Nếu dùng `fatal`, cần phân biệt nó với `error` thông thường:

- `error`: chương trình hoặc một phần đầu vào không hợp lệ; công cụ có thể tiếp tục phân tích để báo thêm lỗi.
- `fatal`: công cụ không thể tiếp tục công việc hiện tại một cách có ý nghĩa.

Không nên tạo quá nhiều mức severity gần giống nhau nếu chúng không dẫn đến hành vi khác biệt rõ.

## 5. Mức độ và hành vi của công cụ

Severity không chỉ là màu sắc hiển thị. Nó có thể ảnh hưởng đến exit code, quyết định triển khai, chính sách CI hoặc cách IDE hiển thị diagnostic.

Một chính sách đơn giản:

| Severity | Chương trình hợp lệ? | CI mặc định | Hiển thị thường gặp |
|---|---|---|---|
| Fatal | Không thể tiếp tục | Thất bại | Thông báo lỗi nghiêm trọng |
| Error | Không hợp lệ theo quy tắc bắt buộc | Thất bại | Đánh dấu lỗi |
| Warning | Có thể tiếp tục nhưng có rủi ro | Tùy chính sách | Cảnh báo |
| Information | Không phải lỗi | Thành công nếu không có lỗi khác | Thông tin |
| Hint | Không phải lỗi | Thành công | Gợi ý |

Bảng này là chính sách ví dụ. Mỗi công cụ cần nói rõ severity nào làm bước kiểm tra thất bại.

### 5.1. Severity không đồng nhất với exit code

Exit code là kết quả của một tiến trình hoặc lệnh CLI. Severity là thuộc tính của từng diagnostic. Một lần chạy có thể tạo nhiều diagnostic ở nhiều mức nhưng chỉ có một exit code tổng thể.

Ví dụ:

```text
DSL-TYPE-0017 error: invalid property type
DSL-DEPR-0003 warning: deprecated property
DSL-STYLE-0010 hint: unnecessary parentheses

Process exit code: 1
```

Exit code `1` có thể biểu thị lần kiểm tra thất bại vì có error, dù vẫn có warning và hint. Công cụ cần định nghĩa quy tắc tổng hợp exit code rõ ràng.

### 5.2. Warning có thể trở thành lỗi theo cấu hình

Một dự án có thể chọn chế độ nghiêm ngặt, trong đó một số warning được nâng thành error. Ví dụ, nhóm phát triển có thể yêu cầu không còn cú pháp deprecated trong nhánh chuẩn bị phát hành.

```text
diagnostics {
    warningsAsErrors = ["DSL-DEPR-0003"]
}
```

Đây là cú pháp giả định. Cần phân biệt severity gốc do analyzer phát ra với severity hiệu lực sau khi áp dụng chính sách cấu hình. Điều này giúp công cụ vẫn giữ được bản chất diagnostic trong khi cho phép từng dự án đặt ngưỡng chất lượng khác nhau.

### 5.3. Tắt hoặc lọc diagnostic

Một công cụ có thể cho phép bỏ qua một số mã:

```text
diagnostics {
    disabled = ["DSL-STYLE-0010"]
}
```

Việc tắt diagnostic nên được kiểm soát và có phạm vi rõ, chẳng hạn theo dự án, tệp, dòng hoặc khối. Nếu tắt quá rộng, người dùng có thể vô tình che mất vấn đề quan trọng.

## 6. Phân biệt severity với loại vấn đề

Severity trả lời mức độ nghiêm trọng. **Category** hoặc **kind** mô tả nhóm nội dung của diagnostic. Hai thuộc tính này nên được lưu riêng.

Ví dụ:

| Diagnostic | Category | Severity |
|---|---|---|
| Không nhận diện được ký tự `@` | Lexical | Error |
| Tên `Customer` không tồn tại | Name resolution | Error |
| Thuộc tính `legacyMode` đã deprecated | Compatibility | Warning |
| Import không được sử dụng | Style/Usage | Hint hoặc Warning |
| Đã chọn phiên bản dependency 2.1 | Build/Resolution | Information |

Một category có thể chứa diagnostic ở nhiều mức độ. Ví dụ, một cảnh báo kiểu dữ liệu có thể là warning trong chế độ linh hoạt nhưng thành error trong chế độ nghiêm ngặt.

## 7. Thiết kế thông điệp gắn với mã lỗi

Mã lỗi định danh quy tắc; message giải thích trường hợp cụ thể. Một thông báo tốt cần dễ hiểu, chỉ rõ đối tượng liên quan và tránh bắt người dùng phải suy luận quá nhiều.

Ví dụ thông báo kém:

```text
Invalid value.
```

Thông báo rõ hơn:

```text
DSL-RULE-0042 error: property 'replicas' must be an integer greater than 0; found 0
```

Thông báo thứ hai cho biết:

- Mã quy tắc: `DSL-RULE-0042`.
- Mức độ: `error`.
- Thành phần liên quan: `replicas`.
- Điều kiện mong đợi: số nguyên lớn hơn 0.
- Giá trị thực tế: `0`.

### 7.1. Message nên mô tả vấn đề, không chỉ lặp mã

Không nên tạo message như `Error DSL1001` vì nó không giúp người dùng hiểu cần sửa gì. Mã dùng để tra cứu; message dùng để giải thích tại ngữ cảnh cụ thể.

### 7.2. Tách message template và tham số

Một cách triển khai tốt là lưu message template cùng các tham số:

```text
code: DSL-RULE-0042
template: "property '{property}' must be greater than {minimum}; found {actual}"
arguments:
  property: replicas
  minimum: 0
  actual: 0
```

Renderer có thể tạo message cho terminal, IDE hoặc tài liệu. Cách này hỗ trợ localization và giúp công cụ máy đọc dữ liệu mà không phải phân tích chuỗi message.

### 7.3. Hướng dẫn sửa và quick fix

Diagnostic có thể bổ sung `help` hoặc `suggestion`:

```text
DSL-DEPR-0003 warning: 'legacyNetworkMode' is deprecated
Help: replace it with 'network.mode'
```

Nếu có thể tạo sửa tự động an toàn, công cụ có thể cung cấp quick fix với vùng thay thế và văn bản mới. Không nên đề xuất sửa tự động khi công cụ chưa đủ thông tin để bảo đảm không đổi ý nghĩa chương trình.

## 8. Vị trí nguồn và thông tin liên quan

Một diagnostic hữu ích thường gắn với vị trí cụ thể trong mã nguồn. Công cụ có thể lưu một khoảng nguồn (*source span*) gồm tệp, offset bắt đầu và kết thúc, hoặc range theo dòng/cột.

Ví dụ:

```text
config.dsl:2:16: error DSL-RULE-0042: property 'replicas' must be greater than 0
    replicas = 0
               ^
```

Vị trí giúp IDE gạch chân đúng đoạn mã và người dùng tìm được nơi cần sửa.

### 8.1. Span chính

Span chính chỉ vị trí quan trọng nhất của vấn đề. Với lỗi kiểu dữ liệu, có thể tô sáng giá trị sai. Với lỗi tên không tồn tại, có thể tô sáng tên định danh.

### 8.2. Thông tin liên quan

Một vấn đề có thể liên quan đến nhiều vị trí. Ví dụ, tên biến bị khai báo trùng:

```text
let region = "asia"
let region = "europe"
```

Diagnostic tại khai báo thứ hai có thể kèm vị trí khai báo đầu tiên để giải thích xung đột. Thông tin liên quan không nhất thiết là một diagnostic độc lập.

### 8.3. Lỗi không có vị trí nguồn

Một số diagnostic phát sinh ngoài văn bản, ví dụ không tải được plugin hoặc không kết nối được dịch vụ. Khi không có span phù hợp, công cụ có thể gắn diagnostic với tệp cấu hình liên quan hoặc hiển thị ở cấp workspace/process. Không nên tạo một vị trí giả gây hiểu nhầm.

## 9. Diagnostic có cấu trúc và định dạng máy đọc

Terminal có thể hiển thị diagnostic dưới dạng văn bản, nhưng IDE và CI thường cần định dạng máy đọc được.

Một cấu trúc JSON minh họa:

```json
{
  "code": "DSL-RULE-0042",
  "severity": "error",
  "category": "domain-validation",
  "message": "property 'replicas' must be greater than 0; found 0",
  "source": "dsl-validator",
  "range": {
    "file": "config.dsl",
    "start": { "line": 2, "character": 16 },
    "end": { "line": 2, "character": 17 }
  }
}
```

Tên trường và quy ước tọa độ phụ thuộc định dạng giao tiếp. Ví dụ trên minh họa dữ liệu có cấu trúc, không phải schema bắt buộc.

### 9.1. Vì sao không nên chỉ xuất chuỗi văn bản?

Nếu CI phải phân loại lỗi bằng cách tìm từ `error` hoặc phân tích câu message, thay đổi ngôn ngữ hiển thị có thể làm script hỏng. Trường `code` và `severity` riêng giúp máy xử lý ổn định hơn.

### 9.2. LSP và IDE

Language Server Protocol (LSP) định nghĩa cách server gửi diagnostics đến editor. Diagnostic trong LSP có thể có range, severity, code, source, message, tags và related information.

Một DSL server có thể gửi cùng mã lỗi cho nhiều editor. IDE quyết định cách tô màu, gạch chân và trình bày thông tin, còn server chịu trách nhiệm tạo diagnostic chính xác.

### 9.3. Định dạng cho CI

CI có thể cần JSON, SARIF hoặc định dạng riêng để tổng hợp kết quả từ nhiều công cụ. Khi xuất, cần giữ code và severity riêng biệt, đồng thời giữ vị trí nguồn nếu có.

## 10. Severity trong các giai đoạn chẩn đoán

Mỗi giai đoạn của pipeline DSL có thể phát diagnostic với mã và mức độ khác nhau.

```text
Source
  |
  v
Lexer
  |  LEX-xxxx
  v
Parser
  |  PARSE-xxxx
  v
Name / Type analysis
  |  NAME-xxxx, TYPE-xxxx
  v
Domain validation
  |  RULE-xxxx
  v
Code generation / Runtime
     GEN-xxxx, RUN-xxxx
```

Ví dụ:

| Giai đoạn | Diagnostic | Severity thường gặp |
|---|---|---|
| Lexer | Ký tự không thuộc tập token | Error |
| Parser | Thiếu dấu `}` | Error |
| Name resolution | Tham chiếu đến tên chưa khai báo | Error |
| Type checking | Truyền chuỗi vào tham số cần số nguyên | Error |
| Validation | Thuộc tính deprecated | Warning |
| Validation | Import không dùng | Hint hoặc Warning |
| Code generation | Backend không hỗ trợ một tính năng tùy chọn | Error hoặc Warning tùy hợp đồng |
| Runtime | Dịch vụ bên ngoài tạm thời không phản hồi | Error tại lần thực thi, có thể retry |

Severity không nên được quyết định chỉ bởi giai đoạn phát hiện. Một vấn đề parser thường là error, nhưng một thông báo runtime có thể là warning nếu đó chỉ là tình huống phục hồi được và chương trình tiếp tục đúng theo thiết kế.

## 11. Mã lỗi và mức độ trong CLI

Một CLI cho DSL thường cần trình bày diagnostics rõ ràng và có thể lọc theo mức độ.

Ví dụ:

```text
$ dsl check config.dsl

config.dsl:2:16: error DSL-RULE-0042: property 'replicas' must be greater than 0; found 0
config.dsl:3:5: warning DSL-DEPR-0003: 'legacyRegion' is deprecated; use 'region'
config.dsl:8:1: hint DSL-STYLE-0010: remove the unused declaration 'oldEndpoint'

1 error, 1 warning, 1 hint
```

### 11.1. Exit code

CLI cần quy định rõ khi nào trả exit code khác 0. Một chính sách thường gặp:

- Có ít nhất một error hoặc fatal: trả mã thất bại.
- Chỉ có warning, information hoặc hint: trả thành công, trừ khi cấu hình yêu cầu warning làm thất bại.
- Không có diagnostic: trả thành công.

Không nên suy ra exit code từ số lượng diagnostic mà không có chính sách được công bố.

### 11.2. Lọc theo severity

CLI có thể cung cấp tùy chọn như:

```text
dsl check --min-severity warning config.dsl
```

Lệnh có thể chỉ hiển thị warning và các mức nghiêm trọng hơn. Nếu hỗ trợ lọc, cần xác định việc lọc chỉ ảnh hưởng hiển thị hay còn ảnh hưởng kết quả kiểm tra và exit code.

### 11.3. Tắt một mã cụ thể

Ví dụ:

```text
dsl check --disable DSL-STYLE-0010 config.dsl
```

Tùy chọn này có thể hữu ích khi một hint không phù hợp với quy ước dự án. Tuy nhiên, công cụ nên hỗ trợ cấu hình có thể kiểm tra trong repository để các thành viên nhóm dùng cùng chính sách.

## 12. Chính sách severity theo dự án

Một quy tắc có thể có mức độ mặc định, nhưng dự án có thể muốn điều chỉnh theo môi trường.

Ví dụ:

| Diagnostic | Mặc định | Dự án phát triển | CI phát hành |
|---|---|---|---|
| Cú pháp không hợp lệ | Error | Error | Error |
| Tên không tồn tại | Error | Error | Error |
| API deprecated | Warning | Warning | Error |
| Import không dùng | Hint | Hint | Warning |
| Định dạng không chuẩn | Information hoặc Hint | Hint | Warning nếu bắt buộc format |

Chính sách này giúp nhóm tăng dần mức nghiêm ngặt mà không buộc mọi dự án thay đổi cùng lúc.

### 12.1. Cấu hình theo mã

Cho phép cấu hình severity theo mã cụ thể giúp tránh phải nâng tất cả warning thành error khi chỉ một số quy tắc quan trọng cần được bắt buộc.

### 12.2. Cấu hình theo phạm vi

Một số dự án cho phép ngoại lệ theo tệp hoặc đoạn mã. Nếu hỗ trợ, cần xác định thứ tự ưu tiên giữa cấu hình toàn cục, cấu hình module và suppression cục bộ.

### 12.3. Suppression có lý do

Nếu cho phép bỏ qua diagnostic trong mã nguồn, nên yêu cầu hoặc khuyến khích ghi lý do:

```text
// diagnostic-disable DSL-DEPR-0003: compatibility with partner schema v1
legacyNetworkMode = true
```

Đây là cú pháp giả định. Một suppression có lý do giúp người bảo trì hiểu vì sao ngoại lệ tồn tại và khi nào có thể gỡ bỏ.

## 13. Vòng đời và quản lý phiên bản mã lỗi

Hệ thống mã lỗi cần được quản lý như một phần của giao diện công cụ. Một khi mã xuất hiện trong tài liệu, script hoặc cấu hình, việc đổi mã có thể ảnh hưởng đến người dùng.

### 13.1. Registry mã lỗi

Một registry có thể lưu:

- Mã.
- Tên ngắn của quy tắc.
- Mô tả dài.
- Severity mặc định.
- Category.
- Thành phần sở hữu.
- Phiên bản được giới thiệu.
- Trạng thái active hoặc retired.
- Liên kết tài liệu và hướng sửa.

Registry giúp tránh cấp trùng mã và tạo tài liệu tham khảo tự động.

### 13.2. Không tái sử dụng mã đã nghỉ

Nếu mã `DSL-RULE-0042` đã từng có nghĩa là “replicas phải lớn hơn 0”, không nên dùng lại mã đó cho một lỗi khác sau khi quy tắc cũ bị loại bỏ. Người dùng có thể còn lưu cấu hình suppression hoặc script nhận diện mã cũ.

### 13.3. Thay đổi message

Message có thể được cải thiện mà không cần đổi mã nếu ý nghĩa quy tắc không đổi. Ví dụ, câu thông báo có thể được viết rõ hơn hoặc dịch sang ngôn ngữ khác.

Nếu quy tắc thay đổi bản chất, cần cân nhắc mã mới hoặc ghi rõ trong tài liệu để tích hợp bên ngoài không hiểu sai.

### 13.4. Thay đổi severity

Severity mặc định có thể thay đổi nếu mức rủi ro được đánh giá lại, nhưng thay đổi này có thể làm CI trước đây thành công nay thất bại hoặc ngược lại. Nên ghi chú trong release notes và cho dự án thời gian điều chỉnh.

### 13.5. Retired và obsolete codes

Mã đã nghỉ nên vẫn có trang tra cứu hoặc mục lịch sử, ghi rõ phiên bản cuối cùng còn sử dụng và mã thay thế nếu có. Điều này hữu ích khi người dùng gặp log cũ hoặc đọc tài liệu của phiên bản trước.

## 14. Localization và khả năng đọc của message

Mã lỗi nên ổn định và độc lập ngôn ngữ. Message có thể được dịch để phục vụ người dùng ở nhiều môi trường.

Ví dụ cùng một diagnostic:

```text
code: DSL-RULE-0042
severity: error
messageId: property.range.invalid
arguments:
  property: replicas
  minimum: 1
  actual: 0
```

Renderer tiếng Việt có thể hiển thị:

```text
Thuộc tính 'replicas' phải có giá trị ít nhất là 1; giá trị hiện tại là 0.
```

Renderer tiếng Anh có thể hiển thị:

```text
Property 'replicas' must be at least 1; found 0.
```

Script và IDE nên dựa vào code, severity và dữ liệu có cấu trúc, không dựa vào câu message đã được dịch.

## 15. Bảo mật và thông tin nhạy cảm trong diagnostic

Diagnostic có thể xuất hiện trong terminal, log CI, báo cáo hoặc hệ thống theo dõi lỗi. Vì vậy, message không nên vô tình tiết lộ bí mật.

Ví dụ không nên đưa trực tiếp vào message:

- Password hoặc access token.
- Khóa API.
- Nội dung dữ liệu cá nhân không cần thiết.
- Đường dẫn nội bộ hoặc thông tin hạ tầng nhạy cảm nếu người nhận không được phép xem.

Thay vì hiển thị toàn bộ giá trị bí mật, có thể chỉ ra tên thuộc tính hoặc dạng lỗi:

```text
DSL-CONFIG-0012 error: credential 'database.password' is missing or invalid
```

Nếu cần ghi log để điều tra, nên dùng cơ chế bảo vệ quyền truy cập và che dữ liệu nhạy cảm. Severity cao không phải lý do để in toàn bộ dữ liệu nguồn hoặc thông tin bí mật.

## 16. Ví dụ tổng hợp: thiết kế catalog diagnostic

Một DSL triển khai dịch vụ có thể định nghĩa registry như sau:

| Code | Category | Severity mặc định | Ý nghĩa |
|---|---|---|---|
| `DSL-LEX-0001` | Lexical | Error | Ký tự không hợp lệ |
| `DSL-PARSE-0004` | Parsing | Error | Thiếu dấu đóng khối |
| `DSL-NAME-0010` | Name resolution | Error | Không tìm thấy định danh |
| `DSL-TYPE-0017` | Type checking | Error | Giá trị không đúng kiểu |
| `DSL-RULE-0042` | Domain validation | Error | Số replica không hợp lệ |
| `DSL-DEPR-0003` | Compatibility | Warning | Thuộc tính đã deprecated |
| `DSL-STYLE-0010` | Style | Hint | Có thể bỏ khai báo không dùng |
| `DSL-INFO-0002` | Resolution | Information | Đã chọn phiên bản dependency |

Với tệp:

```text
service "catalog" {
    replicas = "three"
    legacyNetworkMode = true
    unusedEndpoint = "https://example.invalid"
}
```

Công cụ có thể phát:

```text
config.dsl:2:16: error DSL-TYPE-0017: property 'replicas' expects Integer, found String
config.dsl:3:5: warning DSL-DEPR-0003: 'legacyNetworkMode' is deprecated; use 'network.mode'
config.dsl:4:5: hint DSL-STYLE-0010: declaration 'unusedEndpoint' is not referenced

1 error, 1 warning, 1 hint
```

Lần kiểm tra có thể trả exit code thất bại vì có error. Warning và hint vẫn được hiển thị để người dùng có thể xử lý thêm.

## 17. Hướng dẫn cho người dùng khi gặp mã lỗi

Khi gặp diagnostic, người dùng có thể thực hiện theo trình tự:

1. Đọc severity để hiểu mức độ ảnh hưởng.
2. Đọc message để biết thành phần và điều kiện bị vi phạm.
3. Ghi lại code để tra tài liệu hoặc tìm kiếm trong hệ thống hỗ trợ.
4. Xem vị trí nguồn và thông tin liên quan.
5. Đọc hướng sửa hoặc áp dụng quick fix nếu có.
6. Nếu chưa rõ, tra registry mã lỗi và ghi kèm phiên bản công cụ khi báo sự cố.

Khi gửi báo cáo lỗi, nên cung cấp mã, phiên bản DSL tool, đoạn mã tối thiểu có thể tái hiện và thông điệp đầy đủ. Không nên gửi bí mật hoặc dữ liệu nhạy cảm trong tệp cấu hình.

## 18. Những sai lầm thường gặp

**Dùng message làm định danh.** Message có thể thay đổi hoặc được dịch; công cụ tích hợp nên dùng mã ổn định.

**Tạo mã mới cho mọi lần xuất hiện.** Mã nên định danh loại quy tắc, còn vị trí và tham số mô tả từng lần xuất hiện.

**Không định nghĩa severity nhất quán.** Nếu mỗi analyzer hiểu warning hoặc error khác nhau, người dùng không thể dự đoán kết quả CLI và CI.

**Dùng warning cho mọi vấn đề.** Cảnh báo quá nhiều làm người dùng mất niềm tin và bỏ qua cả cảnh báo quan trọng.

**Đồng nhất severity với exit code.** Một lần chạy có thể chứa nhiều diagnostic; exit code là kết quả tổng hợp theo chính sách CLI.

**Tái sử dụng mã đã nghỉ.** Script hoặc cấu hình suppression cũ có thể áp dụng nhầm vào một quy tắc mới.

**Không tách category và severity.** Nhóm vấn đề và mức độ nghiêm trọng là hai thuộc tính độc lập.

**Chỉ xuất chuỗi văn bản.** IDE và CI cần code, severity, range và các trường có cấu trúc để xử lý ổn định.

**Đưa bí mật vào message.** Diagnostic có thể được lưu trong log hoặc gửi đến dịch vụ bên ngoài; cần che thông tin nhạy cảm.

## 19. Ghi nhớ

- Diagnostic là bản ghi có cấu trúc mô tả lỗi, cảnh báo hoặc thông tin do công cụ DSL phát hiện.
- Mã lỗi định danh loại vấn đề; severity cho biết mức độ nghiêm trọng hoặc mức độ cần chú ý.
- Mã nên ổn định, không phụ thuộc message và không được tái sử dụng cho ý nghĩa khác.
- Một bộ mức độ phổ biến gồm fatal, error, warning, information và hint; ý nghĩa cụ thể phải được công cụ định nghĩa.
- Severity có thể ảnh hưởng đến hiển thị, CI, exit code và chính sách triển khai, nhưng không đồng nhất với exit code.
- Category mô tả nhóm vấn đề và nên được lưu riêng với severity.
- Diagnostic hữu ích cần message rõ, vị trí nguồn, thông tin liên quan và hướng sửa khi có thể.
- Định dạng máy đọc giúp IDE, LSP, CI và script xử lý diagnostic mà không phân tích câu message.
- Registry và versioning giúp duy trì mã lỗi ổn định qua các phiên bản.
- Message cần tránh tiết lộ password, token và dữ liệu nhạy cảm.

## 20. Câu hỏi tự kiểm tra

1. Mã lỗi và severity trả lời hai câu hỏi khác nhau nào?
2. Vì sao mã lỗi nên ổn định trong khi message có thể thay đổi hoặc được dịch?
3. Một diagnostic thường có những trường dữ liệu nào?
4. Phân biệt error, warning, information và hint bằng ví dụ trong DSL.
5. Vì sao severity không đồng nhất với exit code của CLI?
6. Category khác severity như thế nào?
7. Tại sao không nên tái sử dụng mã lỗi đã nghỉ cho một quy tắc mới?
8. Một dự án có thể nâng warning thành error theo chính sách như thế nào?
9. Vì sao IDE và CI cần diagnostic có cấu trúc thay vì chỉ nhận một chuỗi message?
10. Khi một tên bị khai báo trùng, diagnostic có thể sử dụng span chính và related information ra sao?
11. Những thông tin nào không nên xuất hiện trong message hoặc log diagnostic?
12. Hãy đề xuất một hệ thống mã lỗi cho lexer, parser, type checker và validator của một DSL nhỏ.
