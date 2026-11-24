# Quy tắc quoting, escape và kiểu dữ liệu YAML

## Mục tiêu học tập

Trong **Spring Cloud Contract**, hợp đồng giữa **producer** (bên cung cấp API hoặc phát thông điệp) và **consumer** (bên sử dụng API hoặc nhận thông điệp) có thể được viết bằng **YAML DSL** hoặc **Groovy DSL**. Spring Cloud Contract dùng hợp đồng để sinh kiểm thử phía producer và tạo stub cho consumer chạy với **Stub Runner**; CI có thể kiểm tra khi hai phía không còn tương thích.

Bài này thuộc chương **YAML và DSL khác** và tập trung vào một nguồn lỗi dễ bị bỏ qua: *YAML trông giống văn bản, nhưng trình phân tích cú pháp biến nó thành các kiểu dữ liệu cụ thể*. Một chuỗi không được quote đúng có thể thành số, boolean hoặc null. Một dấu gạch chéo ngược trong double quote có thể gây lỗi parse. Những sai khác này ảnh hưởng trực tiếp đến request, body, matcher, generated test và stub.

Sau bài học, bạn có thể:

- Phân biệt **plain scalar**, **single-quoted scalar** và **double-quoted scalar**.
- Viết đúng các ký tự đặc biệt như dấu `:`, `#`, dấu nháy, backslash, xuống dòng và biểu thức chính quy.
- Kiểm soát kiểu **string, number, boolean, null, mapping, sequence** trong hợp đồng.
- Phân biệt **danh sách rỗng**, **object rỗng**, **JSON null** và **không có body**.
- Nhận diện sự khác biệt giữa **lỗi YAML** và **hợp đồng hợp lệ về cú pháp nhưng sai về ngữ nghĩa**.
- Rà soát thay đổi YAML trước khi sinh test, phát hành stub và chạy CI.

## 1. YAML nằm ở đâu trong luồng Spring Cloud Contract?

Một file hợp đồng YAML thường có cấu trúc như sau:

~~~yaml
description: Tra ve ton kho theo SKU
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 12
~~~

Trong ví dụ này:

| Thành phần | Kiểu YAML | Ý nghĩa đối với hợp đồng |
|---|---|---|
| `request`, `response`, `headers`, `body` | Mapping (key–value) | Gom các thuộc tính của request/response |
| `method`, `url`, `description` | String | Dữ liệu văn bản của hợp đồng |
| `status: 200` | Number | HTTP status 200 |
| `available: true` | Boolean | Trường JSON boolean `true` |
| `quantity: 12` | Number | Trường JSON numeric |
| `sku: 'SKU-101'` | String | Mã định danh, không được hiểu thành số |

Luồng xử lý có thể hình dung:

~~~mermaid
flowchart LR
    A["Tệp hợp đồng YAML"] --> B["YAML parser<br/>xác định cấu trúc và kiểu"]
    B --> C["Spring Cloud Contract<br/>đọc DSL"]
    C --> D["Generated producer tests"]
    C --> E["HTTP / message stubs"]
    E --> F["Stub Runner / consumer tests"]
~~~

Một file hợp lệ về cú pháp YAML **chưa chắc** hợp lệ theo **schema DSL** của Spring Cloud Contract. Ví dụ `response.statusCode` có thể là một key YAML hợp lệ nhưng không phải key mà DSL phiên bản đang dùng mong đợi. Ngược lại, một field được schema chấp nhận vẫn có thể chứa sai kiểu, làm generated test hoặc stub không phản ánh hành vi consumer cần.

Chúng ta vì thế cần kiểm tra **hai lớp**: cú pháp và kiểu dữ liệu YAML, rồi đến ngữ nghĩa hợp đồng tại ranh giới producer–consumer.

## 2. Ba kiểu viết scalar: plain, single-quoted, double-quoted

**Scalar** là một giá trị đơn lẻ trong YAML, chẳng hạn chuỗi, số, boolean hoặc null. Cách viết ảnh hưởng đến cả việc phân tích cú pháp lẫn kiểu dữ liệu được suy ra.

| Cách viết | Ví dụ | Cách hiểu và mục đích |
|---|---|---|
| **Plain scalar** (không quote) | `method: GET` | Phù hợp cho chuỗi đơn giản, nhưng một số từ có thể được hiểu thành kiểu khác tùy parser/schema |
| **Single-quoted** | `sku: '00123'` | Giữ giá trị là string; backslash không dùng để escape |
| **Double-quoted** | `message: "Line 1\nLine 2"` | Giữ giá trị là string và hỗ trợ các escape sequence được YAML định nghĩa |

Ví dụ:

~~~yaml
# Cả ba đều biểu diễn string trong các trường hợp thông thường.
namePlain: Java
nameSingle: 'Java'
nameDouble: "Java"

# Có chủ ý khác kiểu.
quantityNumber: 12
quantityString: '12'
enabledBoolean: true
enabledString: 'true'
~~~

### Khi nào nên quote?

Dùng quote khi giá trị **phải là chuỗi** hoặc chứa ký tự dễ gây nhầm lẫn:

- Mã SKU, số điện thoại, mã bưu chính, mã có số 0 đầu: `'00123'`.
- Trạng thái dạng chữ như `'on'`, `'off'`, `'yes'`, `'no'`: cách suy kiểu của một số parser YAML khác nhau.
- Chuỗi giống số, ngày, timestamp hoặc null nhưng cần giữ nguyên văn: `'2026-11-24'`, `'1e3'`, `'null'`.
- URL, message, JSONPath và regex phức tạp: quote để dễ review và không phụ thuộc vào các quy tắc plain scalar.
- Chuỗi có `: ` (dấu hai chấm theo sau là khoảng trắng) hoặc ` #` (khoảng trắng rồi dấu thăng): dùng quote để tránh bị hiểu thành mapping/comment.

Ví dụ lỗi và cách sửa:

~~~yaml
# Sai cú pháp hoặc không diễn đạt đúng ý:
# message: Stock status: out of stock
# note: Please retry # after checking

# Rõ ràng:
message: 'Stock status: out of stock'
note: 'Please retry # after checking'
~~~

Không phải mọi dấu `:` hoặc `#` đều bắt buộc quote. Ví dụ chuỗi `http://example.test` có dấu `:` nhưng không có khoảng trắng ngay sau; `SKU#123` không có khoảng trắng trước `#`. Tuy nhiên, quote nhất quán cho các giá trị do consumer phụ thuộc giúp giảm nhầm lẫn khi sửa file.

## 3. Single quote: lựa chọn an toàn cho regex và chuỗi chứa backslash

Trong **single-quoted scalar**, ký tự backslash `\` có nghĩa **nguyên văn**. Muốn biểu diễn dấu nháy đơn bên trong chuỗi, hãy **nhân đôi** dấu nháy đó:

~~~yaml
message: 'Producer''s response is ready'
regex: '^[A-Z]{3}-\d{4}$'
windowsPath: 'C:\contracts\inventory.yml'
~~~

Các giá trị được hiểu lần lượt là:

- `Producer's response is ready`.
- Regex `^[A-Z]{3}-\d{4}$`, trong đó `\d` được giữ nguyên để engine regex diễn giải.
- Đường dẫn Windows có dấu `\`, không tạo các ký tự xuống dòng hay tab.

Đừng viết kiểu escape của JavaScript hoặc Java bên trong YAML single quote:

~~~yaml
# Sai ý định: dấu \ được giữ nguyên, không "escape" dấu nháy đơn.
# message: 'Producer\'s response'
~~~

Với mẫu regex, single quote thường dễ đọc nhất vì không phải đếm hai lớp escaping: lớp YAML và lớp biểu thức chính quy.

## 4. Double quote: escape được nhưng phải dùng đúng cú pháp YAML

Trong **double-quoted scalar**, YAML xử lý các escape hợp lệ như:

| Viết trong YAML | Giá trị nhận được |
|---|---|
| `\n` | Ký tự xuống dòng |
| `\t` | Ký tự tab |
| `\"` | Dấu ngoặc kép |
| `\\` | Một dấu backslash |
| `\u0041` | Ký tự Unicode `A` |

Ví dụ hợp lệ:

~~~yaml
message: "Line 1\nLine 2"
quotedText: "Producer said: \"OK\""
path: "C:\\contracts\\inventory.yml"
regex: "^SKU-\\d{3}$"
~~~

Đặc biệt chú ý **biểu thức chính quy**:

~~~yaml
# Sai: \d là escape không hợp lệ trong YAML double quote.
# regex: "^\d{3}$"

# Đúng: YAML giữ lại một backslash sau khi parse.
regexSingle: '^\d{3}$'
regexDouble: "^\\d{3}$"
~~~

Hai biểu thức đúng ở trên tạo cùng giá trị chuỗi regex. Nhưng nếu dùng double quote và quên escape, parser có thể báo lỗi từ **YAML** trước khi Spring Cloud Contract kịp tạo test.

Đối với JSONPath trong matcher, phần đường dẫn như `$.items[0].id` thường có thể được quote đơn để bảo toàn văn bản:

~~~yaml
jsonPathExample: '$.items[0].id'
regexExample: '^SKU-[0-9]{3}$'
~~~

Hai key `jsonPathExample` và `regexExample` chỉ là ví dụ YAML về chuỗi; **không phải** key matcher của Spring Cloud Contract. Khi đưa vào contract, phải đặt chuỗi ở các field matcher được DSL hỗ trợ.

### Không nhầm nhiều lớp escape

Nếu producer gửi một trường JSON có dấu backslash, có thể xuất hiện nhiều lớp:

1. **Mã nguồn YAML** mô tả giá trị.
2. **Giá trị sau YAML parser**.
3. **JSON serialization** của response body.
4. **Nội dung mà consumer thực sự nhận và giải mã**.

Ví dụ:

~~~yaml
body:
  filePath: 'C:\data\stock.csv'
~~~

YAML cung cấp **string chứa các dấu backslash nguyên vẹn**. Khi được tuần tự hóa thành JSON, dấu backslash trong JSON text sẽ được escape theo quy tắc JSON. Điều quan trọng là consumer giải mã được đúng chuỗi đường dẫn; đừng đếm ký tự `\` trong file JSON sinh ra mà bỏ qua lớp encoding.

## 5. Suy kiểu dữ liệu: string, number, boolean, null

Các giá trị không quote có thể được parser YAML chuyển thành kiểu khác trước khi DSL xử lý. Một số trường hợp điển hình:

| Ý định | Viết nên dùng | Lý do |
|---|---|---|
| HTTP status 200 (số) | `status: 200` | Kiểu numeric |
| Số lượng còn 0 (số) | `quantity: 0` | Kiểu numeric, không phải chuỗi `"0"` |
| Cờ có hàng (boolean) | `available: false` | Kiểu boolean thật |
| Mã SKU `00123` (string) | `sku: '00123'` | Giữ số 0 đầu và kiểu string |
| Text `true` (string) | `literal: 'true'` | Tránh bị biến thành boolean |
| Trạng thái `on` (string) | `state: 'on'` | Tránh khác biệt giữa schema/parser YAML |
| Giá trị null theo YAML | `value: null` hoặc `value: ~` | Giá trị null của cấu trúc YAML |
| Text `null` (string) | `value: 'null'` | Chính là bốn ký tự `n-u-l-l` |
| Ngày được coi là ID hoặc text | `dateCode: '2026-11-24'` | Tránh cách suy kiểu timestamp/date ở một số loader |
| Số dạng chuỗi khoa học | `raw: '1e3'` | Giữ chuỗi nguyên văn |

**YAML 1.1 và YAML 1.2 có khác biệt về cách suy boolean và một số dạng số.** Một số thư viện hoặc phiên bản loader vẫn coi `yes`, `no`, `on`, `off` là boolean, trong khi cách hiểu của YAML 1.2 đã thay đổi. Spring Cloud Contract còn phụ thuộc vào parser được dùng trong phiên bản cụ thể của dự án. Cách viết an toàn, dễ kiểm soát là:

- Boolean: dùng `true`/`false` không quote khi thật sự cần boolean.
- Văn bản: quote `'yes'`, `'no'`, `'on'`, `'off'`, `'true'`, `'false'` khi muốn **string**.
- Mã định danh và số có số 0 đầu: luôn quote.
- Giá trị ngày/giờ: quote nếu cần giữ nguyên **chuỗi**; đừng dựa vào YAML tự chuyển sang kiểu ngày.

### Cùng một ký tự, khác kiểu là khác hợp đồng

~~~yaml
# Nếu consumer mong available là boolean:
body:
  sku: '00123'
  available: true
  quantity: 0
~~~

Khác với:

~~~yaml
# Đây là string "true" và string "0".
body:
  sku: '00123'
  available: 'true'
  quantity: '0'
~~~

Một consumer deserialize sang Java record có trường `boolean available` và `int quantity` có thể xử lý hai trường hợp rất khác nhau, tùy cấu hình JSON deserializer. Contract test cần bảo vệ đúng kiểu đã cam kết thay vì chỉ nhìn thấy chữ `true` và `0` trong file.

## 6. Mapping và sequence: object khác array

YAML dùng:

- **Mapping** (key–value) để mô tả object, ví dụ `body:` với các key `sku`, `quantity`.
- **Sequence** (dấu `-`) để mô tả array/list, ví dụ danh sách các item.
- **Scalar** để mô tả một giá trị đơn.

Ví dụ response body là object:

~~~yaml
body:
  sku: 'SKU-101'
  available: true
  quantity: 12
~~~

Response body là danh sách hai object:

~~~yaml
body:
  - sku: 'SKU-101'
    quantity: 12
  - sku: 'SKU-202'
    quantity: 0
~~~

Response body là **mảng rỗng**:

~~~yaml
body: []
~~~

Response body là **object rỗng**:

~~~yaml
body: {}
~~~

Bốn ví dụ có **shape khác nhau**. Một consumer mong JSON array không thể mặc định xử lý JSON object; tương tự, `[]` và `{}` không thay thế được cho nhau. Khi danh sách không có phần tử, nếu API đã công bố `200 OK` cùng mảng rỗng, hợp đồng cần giữ đúng `body: []`.

### Phân biệt YAML null, JSON null và không có response body

Ba cấu trúc sau không được coi là giống nhau:

~~~yaml
# Không khai báo thuộc tính body trong response.
response:
  status: 204
~~~

~~~yaml
# Khai báo body nhưng đặt giá trị YAML null.
response:
  status: 200
  body: null
~~~

~~~yaml
# Body là chuỗi có chữ "null".
response:
  status: 200
  body: 'null'
~~~

Ở mức YAML, `body: null` là một **null scalar**, `body: 'null'` là **string** và việc không có key `body` là **key bị thiếu**. Cách Spring Cloud Contract xử lý các biến thể khi sinh HTTP response/stub còn phụ thuộc schema DSL và cách diễn giải body; **không nên dùng chúng thay thế nhau để biểu diễn JSON null mà chưa kiểm tra phản hồi thực tế**.

Với HTTP `204 No Content`, response về nguyên tắc không có body. Với HTTP `200` kèm JSON literal `null`, đó là một biểu diễn khác về mặt giao thức và thường yêu cầu cấu hình rõ ràng, kiểm thử trên stub/producer thực sự.

## 7. Dùng YAML block scalar khi nội dung nhiều dòng

YAML có hai dạng block scalar thường gặp:

- `|` (**literal**): giữ các xuống dòng trong nội dung.
- `>` (**folded**): gộp nhiều xuống dòng thường thành khoảng trắng, trừ các trường hợp xử lý riêng theo quy tắc YAML.

Ví dụ:

~~~yaml
literalMessage: |
  Line 1
  Line 2

foldedMessage: >
  Line 1
  Line 2
~~~

Thông thường, `literalMessage` chứa hai dòng, còn `foldedMessage` tương đương đoạn văn “Line 1 Line 2” (với cách kết thúc theo quy tắc block scalar). **Chúng đều là string**, không phải mapping hay sequence.

### Dấu `-`, `+` kiểm soát newline cuối

| Chỉ thị | Ý nghĩa thông thường |
|---|---|
| `|` | Giữ newline ở cuối khối (clip) |
| `|-` | Loại bỏ newline cuối (strip) |
| `|+` | Giữ các newline cuối (keep) |
| `>`, `>-`, `>+` | Tương tự về xử lý cuối, nhưng nội dung dùng kiểu folded |

Ví dụ:

~~~yaml
withoutTrailingNewline: |-
  PRODUCT_NOT_FOUND

withTrailingNewline: |
  PRODUCT_NOT_FOUND
~~~

Hai giá trị **khác nhau**: giá trị thứ hai thường có thêm newline ở cuối. Với contract so khớp nguyên văn response body hoặc thông điệp, ký tự này có thể khiến test thất bại.

### Khi nào dùng block scalar trong hợp đồng?

Với một response là JSON, thường nên dùng **mapping/sequence YAML** vì các kiểu dữ liệu bên trong được thể hiện rõ:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
~~~

Nếu thật sự cần mô tả **text thuần nhiều dòng**, block scalar giúp giữ nội dung:

~~~yaml
exampleTextBody: |-
  Validation failed:
  - SKU missing
  - Quantity invalid
~~~

`exampleTextBody` ở đây là ví dụ YAML độc lập, **không phải key của Spring Cloud Contract**. Khi đem block scalar vào `response.body`, cần nhớ parser trả về **một string**, khác với mapping JSON có các field được định kiểu. Hãy chọn theo content type và schema body của API, rồi xác minh output thực tế được generated test và stub tạo ra.

## 8. Thụt lề, dấu gạch đầu dòng và cú pháp đặc biệt

YAML phụ thuộc vào **indentation** để biểu diễn cấu trúc. Sử dụng **dấu cách**, không sử dụng tab để thụt lề.

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    products:
      - id: 'P-101'
        price: 10
      - id: 'P-102'
        price: 20
~~~

Dấu `-` tạo phần tử danh sách; các key thuộc **cùng một phần tử** phải có độ thụt lề phù hợp. Nếu đặt `price` lệch cấp, có thể tạo cấu trúc sai hoặc lỗi parse.

### Các ký tự cần chú ý ở đầu plain scalar

Một số ký tự có ý nghĩa cú pháp đặc biệt khi đứng ở vị trí đầu giá trị không quote, chẳng hạn `#` (comment), `*` (alias), `&` (anchor), `!` (tag), `[` và `{` (flow collection), `|`/`>` (block style), và dấu `-` khi theo sau là khoảng trắng. Hãy quote nếu chúng là **văn bản**.

~~~yaml
# Ý định là văn bản, không phải comment, alias hoặc collection.
code: '#NOT_FOUND'
patternText: '*inventory*'
literalArrayText: '[one, two]'
description: '- item is missing'
~~~

Đối với URL và query string, quote thường làm file dễ đọc:

~~~yaml
request:
  method: GET
  url: '/api/products?category=books&page=0'
~~~

Ví dụ trên là **URL text** cho request. Chuỗi `&page=0` bên trong quote không phải YAML anchor. Dấu `:` bên trong chuỗi cũng không được tách thành mapping.

### Duplicate key và comment

Tránh lặp key trong cùng một mapping:

~~~yaml
# Không nên:
# response:
#   status: 200
#   status: 404
~~~

Một số parser từ chối key trùng; một số có thể giữ giá trị đầu hoặc cuối. Vì hành vi không đồng nhất, đừng dựa vào nó. Tương tự, comment bắt đầu bằng `#` ngoài giá trị được quote không phải dữ liệu gửi tới consumer:

~~~yaml
response:
  status: 200 # ghi chú nội bộ cho người đọc YAML
~~~

Comment giúp giải thích cấu hình, nhưng **không nằm trong response body**.

## 9. Ví dụ hợp đồng Spring Cloud Contract YAML đầy đủ

Giả sử producer là **Inventory Service**, consumer là **Checkout Service**. Checkout cần gọi `GET /api/inventory/00123` và nhận SKU dạng chuỗi (giữ số 0 đầu), boolean `available`, number `quantity`.

File có thể nằm tại `src/test/resources/contracts/inventory/stockAvailable.yml` trong producer (khi dự án đã cấu hình Spring Cloud Contract để đọc hợp đồng ở đó):

~~~yaml
description: 'Tra ve ton kho cua SKU bat dau bang so 0'
request:
  method: GET
  url: '/api/inventory/00123'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: '00123'
    available: true
    quantity: 12
    tags:
      - 'featured'
      - 'same-day'
~~~

**Tại sao quote như vậy?**

- `url` là string đường dẫn HTTP. Quote cho rõ ràng.
- `sku` là string `00123`, bảo toàn số 0 đầu.
- `available` là boolean; nếu viết `'true'` sẽ chuyển thành string.
- `quantity` là number; nếu viết `'12'` sẽ chuyển thành string.
- `tags` là sequence của các chuỗi; consumer nhận cấu trúc list/array.
- `headers` là mapping; tên header và nội dung văn bản được viết rõ.

Phản hồi HTTP minh họa theo hợp đồng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "00123",
  "available": true,
  "quantity": 12,
  "tags": ["featured", "same-day"]
}
~~~

Tùy cấu hình plugin, Spring Cloud Contract sinh **generated test phía producer** từ file này. Test kiểm tra triển khai producer theo request và expected response. Stub tương ứng được dùng cho consumer chạy với **Stub Runner**. Chỉ khi producer tests và consumer tests dùng stub tương ứng được thực thi phù hợp, ta mới có bằng chứng cho cả hai phía.

### Hợp đồng cho danh sách rỗng

Ở API tìm kiếm trả **danh sách**, khi không có sản phẩm phù hợp, nếu đã thống nhất dùng `200` cùng JSON array rỗng, hãy biểu diễn trực tiếp:

~~~yaml
description: 'Tim san pham hop le nhung khong co ket qua'
request:
  method: GET
  url: '/api/products?category=no-match'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body: []
~~~

`body: []` khác `body: '[]'` về **kiểu dữ liệu ở mức YAML** (sequence rỗng so với string chứa hai ký tự ngoặc vuông). Cần kiểm tra cách phiên bản Spring Cloud Contract thực sự tạo response từ hai dạng đó; chọn một dạng đã được kiểm chứng theo contract thay vì thay đổi tùy tiện.

### Hợp đồng lỗi với message có dấu hai chấm và dấu nháy

~~~yaml
description: 'Tra loi khi SKU khong ton tai'
request:
  method: GET
  url: '/api/inventory/UNKNOWN'
response:
  status: 404
  headers:
    Content-Type: 'application/json'
  body:
    code: 'SKU_NOT_FOUND'
    message: "SKU 'UNKNOWN' was not found: check the code"
~~~

Dấu `: ` trong message nằm bên trong double quote, vì vậy không bị diễn giải thành cặp key–value. Nếu dùng single quote thì phải nhân đôi dấu nháy đơn ở `'UNKNOWN'`:

~~~yaml
message: 'SKU ''UNKNOWN'' was not found: check the code'
~~~

Hai cách viết cho cùng một string. Khi error message có thể được dịch hoặc chứa dữ liệu động, consumer nên dựa vào **mã lỗi ổn định** (ví dụ `SKU_NOT_FOUND`), không phân nhánh bằng toàn bộ text của `message`.

## 10. Regex matcher: quote chuỗi quy tắc cho đúng

Spring Cloud Contract hỗ trợ các kiểu matcher để tránh so khớp nguyên văn mọi dữ liệu động. YAML parser cần giữ nguyên **string regex** trước khi Spring Cloud Contract xử lý matcher.

Ví dụ một hợp đồng phản hồi có trường `sku` cần đúng mẫu `SKU-` cộng ba chữ số:

~~~yaml
description: 'Tra ve SKU co dinh dang dung'
request:
  method: GET
  url: '/api/inventory/SKU-101'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
  matchers:
    body:
      - path: '$.sku'
        type: by_regex
        value: '^SKU-\d{3}$'
~~~

**Đọc kỹ hai kiểu giá trị**:

- `body.sku` là ví dụ string mà stub có thể cung cấp.
- `matchers.body[].value` là **regex string** để generated test kiểm chứng giá trị thực theo quy tắc, không phải một JSON field mới trả về cho consumer.
- Dấu `\d` được giữ nguyên nhờ **single quote**. Nếu đổi thành double quote mà không viết `\\d`, YAML có thể lỗi parse.
- `path: '$.sku'` là JSONPath string, không phải phép nội suy của shell hoặc build tool.

Cấu trúc matcher chính xác và khả năng kiểm tra kích thước mảng, kiểu dữ liệu, regex hoặc ngữ nghĩa request/response cần được đối chiếu với **Spring Cloud Contract phiên bản dự án dùng**. Không được tự ý mang schema Groovy DSL sang YAML DSL: chúng diễn đạt mục tiêu tương tự nhưng cấu trúc cú pháp khác nhau.

## 11. Từ YAML tới consumer: kiểm tra điều gì?

Một change nhỏ trong YAML có thể làm thay đổi hợp đồng lớn:

~~~diff
 response:
   status: 200
   body:
-    sku: '00123'
-    available: true
-    quantity: 12
+    sku: 00123
+    available: 'true'
+    quantity: '12'
~~~

Dù reviewer vẫn “nhìn thấy” các giá trị quen thuộc, kiểu có thể bị thay đổi:

- `sku` không còn được bảo đảm là string giữ số 0 đầu.
- `available` trở thành string, không còn boolean.
- `quantity` trở thành string, không còn number.

**Producer:** generated contract tests cần phát hiện implementation trả sai kỳ vọng mới hoặc cũ trong các trường hợp hợp đồng bao phủ. Nhưng nếu nhóm vừa sửa contract vừa sửa producer cùng kiểu sai, generated tests mới có thể vẫn xanh.

**Consumer:** test dùng **Stub Runner** với **candidate stub đúng revision** cần kiểm tra code tiêu thụ response: deserialize `sku`, xử lý `available` và phép tính dùng `quantity`. Test stub cũ có thể không phát hiện breaking change mới.

**CI:** nên kết hợp validate YAML/DSL, sinh và chạy producer tests, tạo stub cùng revision, chạy consumer tests bị ảnh hưởng và kiểm tra tương thích trước khi xuất bản artifact. Đừng coi “YAML parse thành công” là đủ để phê duyệt một thay đổi kiểu dữ liệu.

### Checklist review pull request YAML

- [ ] Những mã định danh, timestamp và chuỗi giống số đã được quote đúng.
- [ ] Boolean dùng `true/false` không quote khi thực sự là boolean.
- [ ] Regex chứa `\` ưu tiên single quote hoặc double quote đã escape đúng.
- [ ] Các chuỗi có `: `, ` #` và ký tự cú pháp được quote phù hợp.
- [ ] Không có tab indentation, key trùng hoặc block scalar sai newline cuối.
- [ ] Body giữ đúng shape mapping/sequence/null/absent theo API.
- [ ] DSL được parser và plugin **Spring Cloud Contract** phiên bản hiện tại chấp nhận.
- [ ] Generated producer tests và consumer tests qua Stub Runner dùng cùng revision hợp đồng/stub được dự định phát hành.
- [ ] Nếu thay đổi tương thích, những consumer phụ thuộc kiểu cũ đã được đánh giá và có kế hoạch nâng cấp.

## 12. Bài tập thực hành: tìm lỗi trong YAML

Một người viết hợp đồng cho endpoint kiểm tra SKU như sau:

~~~yaml
description: Check stock
request:
  method: GET
  url: /api/inventory/00123
response:
  status: 200
  body:
    sku: 00123
    available: on
    quantity: '0'
    errorMessage: Stock status: empty
    pattern: "^\d{3}$"
~~~

Yêu cầu nghiệp vụ:

- `sku` phải là chuỗi `00123`.
- `available` phải là boolean `false` (không còn hàng).
- `quantity` phải là số `0`.
- `errorMessage` chỉ là một chuỗi mô tả, chứa dấu `:`.
- `pattern` là một chuỗi regex có `\d`.

**Hãy chỉ ra vấn đề trước khi xem lời giải.**

### Lời giải tham khảo

~~~yaml
description: 'Check stock'
request:
  method: GET
  url: '/api/inventory/00123'
response:
  status: 200
  body:
    sku: '00123'
    available: false
    quantity: 0
    errorMessage: 'Stock status: empty'
    pattern: '^\d{3}$'
~~~

Phân tích:

1. `sku: 00123` có thể bị suy kiểu thành số hoặc được xử lý không nhất quán giữa parser; quote để giữ mã định danh chính xác.
2. `available: on` mơ hồ giữa text và boolean theo một số loader YAML; yêu cầu là boolean `false` nên viết rõ `false`.
3. `quantity: '0'` là string; đổi thành `0` để biểu diễn number.
4. `errorMessage: Stock status: empty` có `: ` bên trong plain scalar nên dễ lỗi cú pháp; quote toàn bộ thông điệp.
5. `pattern: "^\d{3}$"` có `\d` không phải escape YAML hợp lệ trong double quote; dùng single quote hoặc double quote với `\\d`.

**Bài mở rộng:** nếu trường `pattern` là metadata phục vụ matcher và không phải trường response mà API phải công bố, đừng đặt `pattern` trong `response.body`. Chuyển quy tắc sang **matcher** theo cú pháp Spring Cloud Contract của dự án. Contract phải mô tả đúng dữ liệu consumer nhìn thấy, tránh vô tình làm lộ thông tin kiểm thử trong JSON response.

## 13. Ghi nhớ

**Quoting và escaping trong YAML là một phần của thiết kế hợp đồng, không chỉ là cách trình bày.** Chọn quote sai có thể đổi string thành number/boolean/null, làm hỏng regex hoặc làm mất ký tự xuống dòng; nhầm mapping với sequence làm đổi shape JSON mà consumer đọc. Khi viết YAML DSL cho Spring Cloud Contract, hãy kiểm tra kiểu dữ liệu đã được parse, ngữ nghĩa request/response, matcher, generated producer tests và stub mà Stub Runner cung cấp cho consumer. Quản lý revision và chạy các bước kiểm tra trong CI giúp phát hiện sớm những thay đổi giao diện không tương thích.
