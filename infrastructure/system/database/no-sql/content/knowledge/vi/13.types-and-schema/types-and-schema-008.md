# Schema validation, giá trị mặc định và kiểm tra dữ liệu biên

Nhiều cơ sở dữ liệu NoSQL cho phép lưu tài liệu hoặc item có cấu trúc linh hoạt: hai bản ghi cùng một collection có thể có những field khác nhau, một field có thể xuất hiện sau khi nâng cấp ứng dụng, và một số hệ không bắt buộc khai báo trước toàn bộ kiểu dữ liệu. Tính linh hoạt đó hữu ích khi phát triển sản phẩm, nhưng **không có nghĩa dữ liệu không cần schema**.

Trong thực tế, API vẫn phải biết số lượng hàng là số nguyên dương, mã tiền tệ thuộc tập cho phép, thời điểm phải parse được, trạng thái đơn chỉ chuyển theo những bước hợp lệ, và một field bị bỏ qua có ý nghĩa khác với field được gửi bằng **null**. Nếu các điều kiện này không được thống nhất, dữ liệu lỗi có thể tồn tại lâu trong database, chỉ lộ ra khi truy vấn, tạo chỉ mục, nâng phiên bản, tính tổng hoặc đồng bộ sang dịch vụ khác.

**Schema validation** là việc kiểm tra cấu trúc và kiểu giá trị trước hoặc trong lúc ghi. **Giá trị mặc định** (*default value*) xác định điều gì xảy ra khi một giá trị không được cung cấp. **Kiểm tra dữ liệu biên** (*boundary-value validation*) bảo đảm các giới hạn như nhỏ nhất, lớn nhất, rỗng, quá dài, quá sâu, tràn số, định dạng thời gian và trường hợp thiếu dữ liệu được xử lý có chủ đích.

Bài học đặt các khái niệm này trong ngữ cảnh **kiểu dữ liệu và schema của NoSQL**: document databases như MongoDB, item/key–value như DynamoDB và Redis, wide-column như Cassandra/ScyllaDB, cùng tầng API và consumer sự kiện. Mục tiêu không phải biến mọi NoSQL thành bảng quan hệ cứng nhắc, mà tạo một **hợp đồng dữ liệu có thể kiểm chứng và tiến hóa an toàn**.

## 1. “Schemaless” không có nghĩa “không có hợp đồng dữ liệu”

Một collection có thể chấp nhận cả hai document:

~~~json
{
  "orderId": "O-101",
  "quantity": 2,
  "status": "PENDING"
}
~~~

~~~json
{
  "orderId": "O-102",
  "quantity": "two",
  "status": "unknown"
}
~~~

Cả hai đều là JSON hợp lệ về cú pháp. Nhưng document thứ hai không đáp ứng hợp đồng ứng dụng nếu **quantity** phải là số nguyên và **status** chỉ nhận **PENDING**, **PAID** hoặc **CANCELLED**.

Cần phân biệt ba lớp:

| Lớp | Ví dụ | Nó bảo đảm gì? |
| --- | --- | --- |
| **Cú pháp dữ liệu** | JSON parse thành công; BSON có kiểu được hỗ trợ | Payload có thể đọc theo encoding tương ứng. |
| **Schema và validation** | quantity là integer 1–1.000; status thuộc enum | Hình dạng, kiểu, giới hạn và một số điều kiện cục bộ hợp lệ. |
| **Bất biến nghiệp vụ** | Không bán vượt tồn; không thanh toán trùng; mỗi mã đơn duy nhất | Tính đúng sau các thao tác đồng thời và nhiều bản ghi. |

Một tài liệu hợp lệ theo schema vẫn có thể vi phạm bất biến. Ví dụ **stock = 0** và một đơn mới cùng xác nhận lấy một sản phẩm có thể là hai document riêng đều đúng kiểu, nhưng toàn hệ đã oversell.

Ngược lại, một ràng buộc duy nhất ở database hoặc một conditional update có thể bảo vệ bất biến quan trọng mà JSON Schema đơn lẻ không thực hiện được. **Validation, uniqueness, transaction và authorization là những cơ chế bổ sung cho nhau**, không thể dùng thay thế tùy ý.

## 2. Ba hình thức schema trong các hệ NoSQL

### 2.1. Schema khai báo ở cơ sở dữ liệu

Một số hệ yêu cầu cột có kiểu xác định khi tạo bảng. Cassandra/ScyllaDB theo CQL là ví dụ: khai báo **text**, **int**, **bigint**, **timestamp**, **uuid**, **list**, **map** hoặc **set**. Loại schema này giúp database kiểm tra tính tương thích kiểu của phép ghi, nhưng **không mặc nhiên kiểm tra mọi điều kiện** như số lượng dương, email đúng quy tắc hay trạng thái chuyển hợp lệ.

### 2.2. Schema validator trên tài liệu

MongoDB hỗ trợ **collection validator** và tập ràng buộc kiểu **$jsonSchema**, cho phép kiểm tra trường bắt buộc, kiểu BSON, enum, ngưỡng số, độ dài chuỗi và nhiều điều kiện khác. Việc bật validation, chế độ xử lý bản ghi cũ và khả năng cho phép bỏ qua validator cần được cấu hình cụ thể.

### 2.3. Schema ở ứng dụng hoặc luồng dữ liệu

DynamoDB, Redis và nhiều kho key–value có thể chấp nhận nhiều thuộc tính/giá trị khác nhau trên cùng nhóm key. Khi đó, API, service, message consumer và hợp đồng sự kiện phải thực thi phần lớn kiểm tra cấu trúc. Database vẫn có các ràng buộc **primary key, kiểu thuộc tính của khóa và điều kiện cập nhật**, nhưng đó chưa phải validator tổng quát cho mọi payload.

Một hệ thống có thể dùng đồng thời:

~~~text
HTTP API / Event consumer
    -> parse và kiểm tra kích thước
    -> validate request schema
    -> chuẩn hóa và áp dụng default
    -> kiểm tra quyền + bất biến nghiệp vụ
    -> conditional update / transaction
    -> database validation hoặc ràng buộc lưu trữ
    -> phát sự kiện đã được chuẩn hóa
~~~

Không nên dựa vào **một** lớp duy nhất: validator ở API có thể bị bỏ qua bởi script import dữ liệu; validator ở database chưa biết người dùng có quyền gì; kiểm tra ở consumer chưa giúp API trả lỗi sớm.

## 3. Ví dụ xuyên suốt: hợp đồng dữ liệu đơn hàng

Giả sử hệ thống nhận request tạo đơn:

~~~json
{
  "orderId": "O-101",
  "quantity": 2,
  "unitPriceMinor": 125000,
  "currency": "VND",
  "processingMode": "STANDARD",
  "note": null
}
~~~

Ta định nghĩa:

| Field | Kiểu dữ liệu | Bắt buộc? | Điều kiện | Default |
| --- | --- | --- | --- | --- |
| **orderId** | String | Có | 3–64 ký tự, định dạng ID đã quy định | Không có |
| **quantity** | Integer | Có | 1 đến 1.000 | Không có |
| **unitPriceMinor** | Integer/long thích hợp | Có | 0 đến trần tiền theo nghiệp vụ | Không có |
| **currency** | String | Có | Ví dụ VND hoặc USD | Không có |
| **processingMode** | String enum | Không | STANDARD hoặc EXPRESS | STANDARD khi thiếu |
| **note** | String hoặc null | Không | Tối đa 500 ký tự | Không có; thiếu khác null |
| **tenantId** | String | Server cung cấp | Lấy từ danh tính tin cậy | Không cho client quyết định |
| **status** | String enum | Server cung cấp | Ban đầu PENDING | PENDING lúc tạo |
| **createdAt** | Date/time | Server cung cấp | Thời gian UTC chính xác | Thời điểm tạo do server cấp |
| **schemaVersion** | Integer | Server cung cấp | Phiên bản schema được hỗ trợ | 2 cho record mới |

Điểm quan trọng là **request schema** và **stored schema** không nhất thiết giống nhau. Client không nên tùy ý gửi **status = PAID** chỉ vì bản ghi lưu trong database có field status. Tương tự, tenantId và createdAt có thể là thuộc tính database bắt buộc, nhưng phải do server thiết lập.

### 3.1. Request, trạng thái đã chuẩn hóa và bản ghi lưu trữ

~~~text
Request từ client:
    orderId, quantity, unitPriceMinor, currency,
    processingMode?, note?

Server:
    kiểm tra cấu trúc
    áp dụng processingMode nếu field thiếu
    gắn tenantId từ auth
    gắn status=PENDING
    gắn createdAt=clock UTC
    gắn schemaVersion=2
    kiểm tra bất biến và lưu

Stored document:
    đầy đủ các field mà hệ cam kết sẽ lưu
~~~

Cách tách này tránh nhầm lẫn giữa **default của API** và **default của database**. Nó cũng giúp chỉ rõ ai là chủ sở hữu từng field.

## 4. Ví dụ JSON Schema cho request

Đối với JSON được nhận qua HTTP, có thể biểu diễn phần lớn hợp đồng cấu trúc bằng JSON Schema tiêu chuẩn. Ví dụ minh họa theo JSON Schema Draft 2020-12:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CreateOrderRequest",
  "type": "object",
  "required": [
    "orderId",
    "quantity",
    "unitPriceMinor",
    "currency"
  ],
  "properties": {
    "orderId": {
      "type": "string",
      "minLength": 3,
      "maxLength": 64,
      "pattern": "^[A-Za-z0-9_-]+$"
    },
    "quantity": {
      "type": "integer",
      "minimum": 1,
      "maximum": 1000
    },
    "unitPriceMinor": {
      "type": "integer",
      "minimum": 0,
      "maximum": 9000000000000
    },
    "currency": {
      "type": "string",
      "enum": ["VND", "USD"]
    },
    "processingMode": {
      "type": "string",
      "enum": ["STANDARD", "EXPRESS"],
      "default": "STANDARD"
    },
    "note": {
      "type": ["string", "null"],
      "maxLength": 500
    }
  },
  "additionalProperties": false
}
~~~

Schema diễn đạt rõ: **processingMode** không nằm trong danh sách required; nhưng **nếu có mặt**, nó phải là một trong hai chuỗi được cho phép. **note** được phép null một cách chủ đích. Các field không khai báo bị từ chối vì **additionalProperties: false**.

### 4.1. Đặc biệt: default trong JSON Schema không tự ghi giá trị

Trong JSON Schema tiêu chuẩn, từ khóa **default** chủ yếu mang ý nghĩa **metadata/annotation**. Một validator không bị yêu cầu phải tự sửa input và thêm field bị thiếu. Một số thư viện có chế độ áp dụng default riêng, nhưng hành vi đó là **tính năng của thư viện**, không phải bảo đảm chung của định dạng schema.

Ví dụ:

~~~json
{
  "orderId": "O-101",
  "quantity": 2,
  "unitPriceMinor": 125000,
  "currency": "VND"
}
~~~

Request này có thể **hợp lệ** dù không có processingMode. Sau validation, nếu tầng ứng dụng muốn lưu STANDARD, nó phải **áp dụng default một cách tường minh** rồi kiểm tra và lưu đối tượng đã chuẩn hóa.

Không được cho rằng đặt **default: "STANDARD"** trong schema nghĩa là MongoDB, DynamoDB, Redis hay mọi thư viện JSON tự động ghi field ấy.

### 4.2. JSON Schema không hoàn toàn trùng với MongoDB $jsonSchema

MongoDB dùng biến thể kiểm tra theo **BSON type**, có từ khóa như **bsonType** và những quy tắc/giới hạn hỗ trợ JSON Schema tùy phiên bản. Vì vậy, không copy toàn bộ schema Draft 2020-12 vào collection validator rồi mặc định tất cả keyword đều có tác dụng.

JSON Schema trên request và MongoDB **$jsonSchema** trên stored document nên được xem là **hai hợp đồng có thể liên quan**, nhưng phải được viết/kiểm chứng theo công cụ tương ứng.

## 5. Phân biệt missing, null, rỗng, zero và false

Một nguồn lỗi lớn là gộp các giá trị “trông như không có” thành cùng một ý nghĩa.

| Trạng thái input | Ví dụ | Ý nghĩa có thể cần phân biệt |
| --- | --- | --- |
| **Missing/omitted** | Không có field processingMode | Client không cung cấp; có thể áp dụng default. |
| **Null** | "processingMode": null | Client chủ động gửi null; có thể là lỗi hoặc yêu cầu xóa field tùy API. |
| **Empty string** | "processingMode": "" | Có field string nhưng rỗng; thường không hợp lệ với enum. |
| **Whitespace-only** | "note": "   " | Có nội dung khoảng trắng; có chuẩn hóa hay giữ nguyên không? |
| **Zero** | "quantity": 0 | Số 0 hợp lệ về kiểu nhưng vi phạm min=1. |
| **False** | "sendEmail": false | Boolean hợp lệ, không phải thiếu dữ liệu. |
| **Empty array** | "items": [] | Mảng hợp lệ về kiểu nhưng có thể vi phạm minItems=1. |
| **Empty object** | "metadata": {} | Object hợp lệ về kiểu; có thể được phép. |
| **Wrong type** | "quantity": "2" | Chuỗi khác số nguyên, dù có thể ép kiểu. |

### 5.1. Lỗi default theo giá trị falsey

Trong JavaScript:

~~~javascript
// Sai nếu 0 hoặc false là giá trị hợp lệ:
const retryCount = input.retryCount || 3;
const enabled = input.enabled || true;

// Khác biệt: toán tử ?? chỉ fallback khi null hoặc undefined.
const retryCount2 = input.retryCount ?? 3;
const enabled2 = input.enabled ?? true;
~~~

Nhưng ngay cả **??** vẫn xem **null** là lý do để dùng default. Nếu hợp đồng quy định **chỉ default khi field thiếu, còn null phải bị từ chối**, cần kiểm tra property presence riêng:

~~~javascript
const hasMode = Object.prototype.hasOwnProperty.call(
  input,
  "processingMode"
);

let processingMode;

if (!hasMode) {
  processingMode = "STANDARD";
} else if (
  input.processingMode === "STANDARD" ||
  input.processingMode === "EXPRESS"
) {
  processingMode = input.processingMode;
} else {
  throw new Error("processingMode must be STANDARD or EXPRESS");
}
~~~

Mẫu này tránh âm thầm đổi **processingMode: null** thành STANDARD. Trong dự án thật, input phải được xác nhận là object thích hợp và có giới hạn kích thước trước khi truy cập thuộc tính.

### 5.2. Missing và null khi truy vấn MongoDB

Đối với MongoDB, một truy vấn theo field bằng null có thể khớp **document thiếu field hoặc field có null**:

~~~javascript
// Có thể khớp document thiếu note hoặc note = null.
db.orders.find({ note: null });

// Chỉ những document không có field note.
db.orders.find({ note: { $exists: false } });

// Chỉ những document có field note với kiểu BSON null.
db.orders.find({ note: { $type: "null" } });
~~~

Nếu nghiệp vụ cần biết “khách chưa nhập ghi chú” khác “khách xóa ghi chú”, việc coi missing và null là một sẽ ảnh hưởng query, migration và phân tích dữ liệu. Cần định nghĩa rõ ở contract.

## 6. Chiến lược áp dụng giá trị mặc định

Default không chỉ là con số điền vào chỗ trống. Nó thể hiện **quy tắc nghiệp vụ khi thông tin chưa được cung cấp**.

Có thể áp dụng tại:

| Vị trí | Ưu điểm | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Tầng API/service** | Có auth, context, version và ý nghĩa request | Worker/import khác có thể bỏ qua nếu không dùng chung logic. |
| **Lớp serialization/DTO** | Giảm boilerplate khi parse | Dễ gộp missing và explicit null; thay đổi theo thư viện. |
| **Database update expression** | Gần điểm ghi, có thể atomic khi dùng đúng primitive | Chỉ hỗ trợ một số biểu thức, không phải default chung cho mọi write. |
| **Consumer sự kiện** | Xử lý dữ liệu cũ/khác phiên bản | Có thể diễn giải khác producer nếu không chia sẻ contract. |
| **Tầng đọc legacy** | Dữ liệu cũ vẫn đọc được khi thiếu field | Có thể che giấu dữ liệu chưa được migration và khác kết quả query/index. |
| **Backfill/migration** | Ghi rõ default vào dữ liệu cũ | Cần xác định default tại thời điểm lịch sử, an toàn với cập nhật đồng thời. |

### 6.1. Default tại thời điểm tạo

Ví dụ:

~~~text
processingMode:
    missing -> STANDARD
    null    -> REJECT
    EXPRESS -> ACCEPT

createdAt:
    không nhận từ client
    server thiết lập thời điểm commit/nhận yêu cầu
    theo chính sách đã chọn

status:
    không nhận từ client
    server lưu PENDING lúc tạo
~~~

Nếu sử dụng thời điểm hiện tại làm default, phải xác định **clock nào** và **ở thời điểm nào**. “Default createdAt = now” sẽ khác nhau giữa lần retry nếu không có idempotency; yêu cầu tạo lại sau timeout có thể sinh bản ghi khác thời điểm.

### 6.2. Default khi đọc dữ liệu cũ

Giả sử schema v1 chưa có processingMode, còn v2 dùng STANDARD.

~~~text
Document v1:
    {orderId:"O-101", quantity:2}

Document v2:
    {orderId:"O-102", quantity:2, processingMode:"STANDARD"}
~~~

Tầng đọc có thể trả **STANDARD** cho document v1 theo luật tương thích. Nhưng **field vẫn không tồn tại trong bản ghi nguồn**, nên một index/query lọc processingMode có thể không tìm thấy v1 như mong muốn. Đọc fallback không thay thế việc **backfill** nếu nghiệp vụ cần query/sort/aggregation dựa trên field đã được bổ sung.

Quan trọng hơn, với các đơn cũ, **STANDARD có thật sự là hành vi lịch sử đúng không?** Không được tự gán default mới cho dữ liệu cũ khi nó thay đổi ý nghĩa phí, quyền lợi hoặc trách nhiệm pháp lý.

### 6.3. Không tái áp dụng default trên mọi lần cập nhật

Nếu một bản ghi đã có **processingMode = EXPRESS**, việc cập nhật ghi chú không được tự đặt lại STANDARD chỉ vì payload PATCH không chứa processingMode.

~~~text
Stored:
    processingMode = EXPRESS
    note = "giao buổi chiều"

PATCH:
    note = "giao giờ hành chính"

Kết quả đúng:
    processingMode = EXPRESS
    note = "giao giờ hành chính"
~~~

Default thường thuộc **lúc tạo** hoặc **lúc chuyển đổi phiên bản**, không phải một thao tác reset mặc định khi field bị bỏ qua trong mọi request.

## 7. Thứ tự của pipeline validation và chuẩn hóa

Một pipeline hợp lý phải phân biệt **kiểm tra tính hợp lệ** với **biến đổi dữ liệu có chủ đích**:

~~~mermaid
flowchart TD
    A[Nhận HTTP/event payload] --> B[Giới hạn byte, depth và parse]
    B --> C[Kiểm tra field được phép và kiểu dữ liệu]
    C --> D[Áp dụng default chỉ cho missing theo contract]
    D --> E[Validate đối tượng chuẩn hóa]
    E --> F[Authorization và cross-field business rules]
    F --> G[Conditional write / transaction / uniqueness]
    G --> H[Stored schema validation]
    H --> I[Commit và phát event đã chuẩn hóa]
~~~

Trong thực tế một số bước có thể đan xen, nhưng phải giữ nguyên các nguyên tắc:

1. **Không parse dữ liệu vô hạn** rồi mới kiểm tra kích thước.
2. **Không ép kiểu ngầm** làm một input sai trở thành giá trị khác mà client không biết.
3. **Không áp dụng default khi explicit null** trừ khi contract thực sự nói như vậy.
4. **Không lấy tenantId/role/status nhạy cảm từ input ngoài** khi server phải sở hữu chúng.
5. **Không chỉ validate trước khi đọc rồi ghi không điều kiện** đối với ràng buộc chịu cạnh tranh.
6. **Không phát sự kiện như thể đã commit** trước khi nguồn sự thật đã ghi thành công theo giao thức hệ chọn.

Một số validator hỗ trợ biến đổi input như trim/coerce/default. Khi dùng tính năng đó, phải xác định rõ **đối tượng nào được sửa** và **kiểm tra lại đầu ra sau biến đổi**. Đây là logic của công cụ, không phải hành vi chung của JSON Schema.

## 8. Kiểm tra dữ liệu biên với số nguyên, số thực và tiền

Giả sử quantity phải từ 1 đến 1.000.

| Input | Kết quả mong muốn | Lý do |
| --- | --- | --- |
| 1 | Hợp lệ | Chính xác ở biên dưới |
| 1000 | Hợp lệ | Chính xác ở biên trên |
| 0 | Từ chối | Dưới min |
| -1 | Từ chối | Giá trị âm |
| 1001 | Từ chối | Vượt max |
| 1.5 | Từ chối | Không phải số nguyên |
| "2" | Từ chối hoặc chuyển có chủ đích theo API | Sai kiểu JSON; không âm thầm ép |
| null | Từ chối | Field bắt buộc không được null |
| Một số nguyên quá lớn | Từ chối | Vượt miền kiểu dữ liệu an toàn |
| NaN, Infinity | Từ chối | Không phải giá trị số JSON chuẩn |
| Giá trị thiếu | Từ chối | Quantity là field required |

### 8.1. Tràn số và mất độ chính xác

Một số định dạng/thư viện có miền khác nhau:

- Java **int** là số nguyên signed 32-bit; **long** là signed 64-bit.
- JavaScript **Number** dùng số thực nhị phân IEEE 754; không biểu diễn chính xác mọi số nguyên lớn hơn **Number.MAX_SAFE_INTEGER**.
- MongoDB có nhiều kiểu BSON số: int32, int64, double, decimal128.
- DynamoDB biểu diễn thuộc tính Number theo quy tắc precision/range của dịch vụ; client phải chuyển giá trị đúng và không mặc định dùng Number của JavaScript cho mọi số lớn.
- Cassandra phân biệt **int**, **bigint**, **decimal**, **float**, **double** theo CQL.

Ví dụ:

~~~javascript
const unsafeId = 9007199254740993;

// Không dùng Number để giữ nguyên mọi số nguyên vượt safe range:
console.log(Number.isSafeInteger(unsafeId)); // false
~~~

Nếu một ID, số tiền hay counter có thể vượt miền số an toàn của ngôn ngữ, cần chọn kiểu và cách serialize phù hợp **trên toàn đường dữ liệu**, không chỉ ở database. String ID thường phù hợp hơn ép mọi định danh thành number.

### 8.2. Tiền và làm tròn

Không nên cộng tiền với **float/double** mà giả định luôn cho kết quả tiền tệ chính xác.

~~~text
unitPriceMinor = 125000 (đơn vị nhỏ đã quy định)
quantity       = 2
lineTotalMinor = 250000
~~~

Phải kiểm tra multiplication không tràn và các loại phí/discount theo thứ tự làm tròn đã thống nhất. Với ngoại tệ có độ chia nhỏ khác, một số nguyên “minor unit” chỉ có ý nghĩa khi currency và quy tắc scale được biết.

**Giá tiền 0** có thể hợp lệ cho sản phẩm miễn phí, nhưng **quantity 0** có thể không hợp lệ để tạo đơn. Đừng dùng cùng quy tắc “phải > 0” cho mọi trường số.

## 9. Chuỗi và Unicode: biên không chỉ là độ dài

Một chuỗi hợp lệ còn phụ thuộc encoding, chuẩn hóa và quy tắc định danh.

Các trường hợp cần xét:

- Empty string **""** và chuỗi chỉ chứa khoảng trắng **"   "**.
- Khoảng trắng đầu/cuối có được giữ không; trim có làm đổi tên hiển thị hợp lệ?
- Độ dài đo theo **byte UTF-8**, **Unicode code point** hay ký tự nhìn thấy (*grapheme cluster*)?
- Chữ có dấu tiếng Việt có thể có các biểu diễn Unicode khác nhau nhưng hiển thị tương tự.
- Chữ hoa/thường, dấu tiếng Việt, collation và case-folding có ảnh hưởng uniqueness?
- Control character, ký tự xuống dòng, ký tự zero-width, ký tự định hướng hoặc emoji có được phép không?
- Chuỗi rất dài có gây tốn bộ nhớ, index lớn hoặc log quá tải không?
- ID có cho phép dấu cách, dấu gạch ngang, ký tự quốc tế hay chỉ ASCII?
- Email và URL có cần quy tắc riêng cho format/IDN/punycode không?

### 9.1. Kiểm tra “tên hiển thị” khác “mã định danh”

~~~text
displayName:
    Cho phép Unicode và dấu tiếng Việt.
    Có min/max theo UX và an toàn dữ liệu.
    Có thể giữ khoảng trắng có chủ ý.

orderId:
    Chỉ cho phép các ký tự theo hợp đồng ID.
    Giới hạn độ dài và uniqueness.
    Không dùng displayName làm khóa storage nếu không chuẩn hóa.

username:
    Cần quy tắc normalize/case-fold rõ.
    Uniqueness phải được database bảo vệ
    bằng key/unique index/conditional write phù hợp.
~~~

Ví dụ **"Nguyễn"** và một chuỗi dùng ký tự Unicode tổ hợp có thể nhìn giống nhau nhưng khác byte. Không thể chỉ lowercase chuỗi rồi kết luận uniqueness chắc chắn đúng cho mọi ngôn ngữ. Hợp đồng nên chốt thuật toán normalization (nếu áp dụng) trước khi tạo khóa và phải migration an toàn nếu đổi thuật toán.

### 9.2. Giới hạn byte trước khi lưu

Một field có **maxLength: 500** ký tự không mặc nhiên bảo đảm nó chiếm tối đa **500 byte**. UTF-8 dùng nhiều byte cho nhiều ký tự Unicode. Nếu database/index/message broker có giới hạn byte, phải kiểm tra dung lượng thực sau serialize. Đồng thời, kiểm tra tổng dung lượng document và độ sâu lồng nhau để tránh một payload có nhiều field nhỏ nhưng tổng thể quá lớn.

## 10. Ngày, giờ và múi giờ là dữ liệu biên

Một ứng dụng có thể nhận:

~~~text
2026-11-14T10:30:00Z
2026-11-14T17:30:00+07:00
2026-11-14
2026-11-14 10:30
~~~

Hai dòng đầu có thể biểu diễn cùng một thời điểm theo offset khác nhau. Dòng thứ ba là **ngày lịch** không có thời điểm. Dòng cuối không chỉ rõ timezone, nên chưa xác định được một instant duy nhất.

Cần phân biệt:

- **Instant/timestamp:** một mốc thời gian tuyệt đối, thường serialize ở UTC.
- **Local date:** ngày nghiệp vụ như ngày sinh, ngày hóa đơn hoặc ngày lưu trú.
- **Local time:** giờ trong ngày, có thể không gắn một ngày hoặc múi giờ.
- **Zoned date/time:** thời gian địa phương gắn timezone định danh như Asia/Ho_Chi_Minh.
- **Offset:** +07:00 chỉ là offset ở một thời điểm, không thay thế toàn bộ quy tắc timezone.

### 10.1. Các trường hợp biên cần test

| Tình huống | Câu hỏi validation |
| --- | --- |
| Ngày không tồn tại | 2026-02-30 có bị từ chối không? |
| Năm nhuận | Ngày 29/02 hợp lệ với năm nào? |
| Timestamp không timezone | API có chấp nhận hay bắt buộc offset? |
| Ngày đổi tháng/năm | Chia bucket theo business timezone thế nào? |
| Daylight saving time | Local time bị lặp hoặc không tồn tại xử lý ra sao? |
| Event đến trễ | Dùng event time hay processing time để nhóm? |
| createdAt từ client | Có cần chống giả mạo thời gian không? |
| expiresAt trước createdAt | Có được phép không; cross-field validation thế nào? |

Ví dụ quy tắc:

~~~text
createdAt:
    do server cấp dưới dạng instant UTC.

businessDay:
    được tính bằng timezone nghiệp vụ đã chốt,
    không lấy đơn giản 10 ký tự đầu của mọi chuỗi timestamp.

expiresAt:
    phải lớn hơn createdAt nếu là một lease/expiration hợp lệ.
~~~

Một schema chỉ kiểm tra **bsonType: date** chưa chắc bảo vệ được quan hệ **expiresAt > createdAt**. Điều kiện giữa hai field có thể cần logic domain, validator expression hỗ trợ hoặc transaction theo thiết kế.

## 11. Object, array, collection và payload lồng nhau

Schema của NoSQL thường chứa array/object, nhưng nhiều loại lỗi không nằm ở một field đơn.

Ví dụ request đơn hàng:

~~~json
{
  "orderId": "O-101",
  "items": [
    { "sku": "P-100", "quantity": 2 },
    { "sku": "P-100", "quantity": 1 }
  ]
}
~~~

Từng phần tử có thể hợp lệ về kiểu, nhưng nếu hợp đồng yêu cầu **mỗi SKU chỉ xuất hiện một lần**, request trên vẫn sai về mặt cross-item rule. JSON Schema có thể giới hạn số phần tử hoặc uniqueness của toàn item, nhưng “không trùng theo riêng field sku” thường cần logic riêng hoặc cách biểu diễn lại thành map theo sku.

Các giới hạn cần quyết định:

- **minItems/maxItems:** giỏ có được rỗng không, tối đa bao nhiêu dòng?
- **minProperties/maxProperties:** metadata có thể chứa bao nhiêu key?
- **Độ sâu tối đa:** object lồng 1.000 cấp có làm parser hoặc business logic cạn bộ nhớ/stack?
- **Dung lượng tổng:** từng field nhỏ nhưng 100.000 field tạo payload lớn.
- **Trùng key JSON:** parser xử lý hai thuộc tính cùng tên thế nào? Có từ chối hay “last wins”?
- **Mảng trùng phần tử:** duplicate có hợp lệ không; unique theo toàn item hay một khóa con?
- **Array order:** thứ tự các phần tử có mang ý nghĩa không?
- **Kiểu không đồng nhất:** mảng chứa cả number/string/null có được phép?
- **Collection rỗng và null:** có khác nhau trong từng database/driver không?

### 11.1. Tránh nhận metadata tùy ý không giới hạn

Một field như:

~~~json
{
  "metadata": {
    "anything": "value"
  }
}
~~~

có thể thuận tiện khi mở rộng, nhưng không nên mở ra vô hạn nếu dữ liệu này được index, log, trả qua API hoặc đưa vào event. Nên xác định **allowlist namespace**, key length, số lượng, kích thước và kiểu giá trị tối đa, đặc biệt khi metadata do client bên ngoài gửi.

## 12. MongoDB: collection validator với $jsonSchema

MongoDB là ví dụ rõ về schema linh hoạt nhưng có thể cấu hình kiểm tra ở database. Một collection **orders** mới có thể được tạo với validator (cú pháp minh họa trong mongosh):

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "orderId",
        "quantity",
        "unitPriceMinor",
        "currency",
        "status",
        "processingMode",
        "createdAt",
        "schemaVersion"
      ],
      properties: {
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        orderId: {
          bsonType: "string",
          minLength: 3,
          maxLength: 64
        },
        quantity: {
          bsonType: "int",
          minimum: 1,
          maximum: 1000
        },
        unitPriceMinor: {
          bsonType: "long",
          minimum: 0
        },
        currency: {
          enum: ["VND", "USD"]
        },
        status: {
          enum: ["PENDING", "PAID", "CANCELLED"]
        },
        processingMode: {
          enum: ["STANDARD", "EXPRESS"]
        },
        createdAt: {
          bsonType: "date"
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 2
        },
        note: {
          bsonType: ["string", "null"],
          maxLength: 500
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Một bản ghi hợp lệ với kiểu BSON phù hợp:

~~~javascript
db.orders.insertOne({
  tenantId: "T1",
  orderId: "O-101",
  quantity: NumberInt(2),
  unitPriceMinor: NumberLong("125000"),
  currency: "VND",
  status: "PENDING",
  processingMode: "STANDARD",
  createdAt: ISODate("2026-11-14T10:30:00Z"),
  schemaVersion: NumberInt(2),
  note: null
});
~~~

### 12.1. BSON type khác JSON type

JSON Schema chung có **integer** hoặc **number**, nhưng MongoDB lưu **BSON** với **int**, **long**, **double** và **decimal**. Một giá trị có vẻ là số nguyên ở JSON hoặc JavaScript có thể được driver serialize sang kiểu BSON khác với validator yêu cầu.

Nếu schema buộc **unitPriceMinor** là **long**, code ghi phải serialize nhất quán thành BSON int64. Không nên “sửa lỗi” bằng cách nới validator thành mọi kiểu number nếu nghiệp vụ cần miền giá trị và độ chính xác chặt.

### 12.2. required không có nghĩa cấm null

**required** kiểm tra sự hiện diện của field. Nếu một field có mặt với giá trị null, nó không bị coi là thiếu; việc có hợp lệ hay không còn phụ thuộc ràng buộc kiểu. Ví dụ **note** có thể null vì được khai báo **bsonType: ["string","null"]**, nhưng **quantity** null sẽ không đạt **bsonType: "int"**.

### 12.3. Field ngoài schema và _id

Nếu muốn chặn mọi field không khai báo, có thể xem **additionalProperties: false** theo cú pháp MongoDB hỗ trợ. Cần lưu ý MongoDB document thường có field **_id**; nếu bật additionalProperties false, phải **khai báo/cho phép _id** trong schema để tránh từ chối document hợp lệ có ID. Ví dụ trên không bật additionalProperties false để tách riêng vấn đề này.

Về bảo mật, không nên chỉ dựa vào điều đó để chống mass assignment: vẫn phải có **allowlist ở API** và không để client ghi field hệ thống như role, tenantId hoặc status.

## 13. MongoDB: chế độ validation và dữ liệu đã tồn tại

Khi áp validator cho một collection cũ, cần tách **chế độ đánh giá write** khỏi **trạng thái dữ liệu đã lưu**.

Các lựa chọn phổ biến:

- **validationAction: "error"**: từ chối các thao tác ghi vi phạm validator theo phạm vi áp dụng.
- **validationAction: "warn"**: ghi nhận vi phạm nhưng cho phép write; phù hợp quan sát trước khi siết, không phải enforcement thực sự.
- **validationLevel: "strict"**: áp dụng kiểm tra cho các insert/update được điều chỉnh bởi validator.
- **validationLevel: "moderate"**: có cách xử lý linh hoạt hơn đối với các document cũ đã không đạt validator; phải xem ngữ nghĩa chính xác của bản MongoDB đang chạy.

Trên collection đã có dữ liệu, thay validator **không tự backfill hoặc làm sạch tất cả document cũ**. Một document tồn tại trước khi bật ràng buộc có thể vẫn có field sai kiểu. Cần **audit dữ liệu cũ**, xác định số bản ghi lỗi, sửa theo batch hoặc dùng cơ chế chuyển đổi phiên bản.

Ngoài ra, các công cụ/import với quyền phù hợp có thể sử dụng tùy chọn **bypassDocumentValidation** ở những thao tác được hỗ trợ. Vì vậy quy trình vận hành cần kiểm soát quyền và không mặc định “mọi nguồn ghi đều chắc chắn đi qua validator như nhau”.

### 13.1. Validation của một document không đảm bảo uniqueness

Nếu **orderId** phải duy nhất trong một tenant, validator về minLength chưa đủ. Cần unique index phù hợp:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);
~~~

Tương tự, nếu cập nhật từ PENDING sang PAID chỉ được thực hiện một lần, cần filter điều kiện khi cập nhật:

~~~javascript
const result = db.orders.updateOne(
  {
    tenantId: "T1",
    orderId: "O-101",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" }
  }
);

if (result.modifiedCount !== 1) {
  // Đơn không tồn tại, không ở PENDING, hoặc không có thay đổi.
}
~~~

Validator kiểm tra **status thuộc enum**, nhưng không tự biết **PENDING → PAID** hợp lệ còn **CANCELLED → PAID** có thể bị cấm. Điều kiện theo trạng thái/version hoặc transaction nghiệp vụ cần bảo vệ quy tắc chuyển trạng thái.

## 14. DynamoDB: schema linh hoạt nhưng khóa và điều kiện ghi rất quan trọng

DynamoDB không yêu cầu khai báo trước toàn bộ attributes của mỗi item. Bảng định nghĩa khóa chính, có thể có index và những giới hạn kiểu/độ lớn theo API; các attributes ngoài khóa có thể khác nhau giữa các item.

Ví dụ item với định dạng AttributeValue của API:

~~~json
{
  "PK": { "S": "TENANT#T1" },
  "SK": { "S": "ORDER#O-101" },
  "quantity": { "N": "2" },
  "unitPriceMinor": { "N": "125000" },
  "currency": { "S": "VND" },
  "status": { "S": "PENDING" },
  "processingMode": { "S": "STANDARD" }
}
~~~

Database biết **PK/SK** phải đáp ứng yêu cầu khóa, nhưng không tự áp dụng mọi điều kiện **quantity 1–1.000**, **status enum**, **unitPriceMinor không âm** trên mọi PutItem chỉ vì ứng dụng đã mô tả nó trong code.

### 14.1. Validate trước PutItem

Tầng service nên:

1. Parse input và từ chối sai kiểu.
2. Chỉ dùng tenantId từ danh tính đã xác thực.
3. Áp default cho field thiếu đúng contract.
4. Validate toàn bộ stored item định ghi.
5. Dùng **PutItem** có **ConditionExpression** để ngăn ghi đè khóa đã tồn tại khi cần uniqueness.

Ví dụ ý tưởng:

~~~text
PutItem:
    PK = TENANT#T1
    SK = ORDER#O-101
    ... attributes đã validate

ConditionExpression:
    attribute_not_exists(PK)
~~~

Điều kiện trên PutItem kiểm tra **item hiện tồn tại** ở khóa đó; nó **không thay thế validator tổng quát đối với payload mới**.

### 14.2. Conditional update bảo vệ trạng thái hiện tại

Nếu chỉ được xác nhận thanh toán từ trạng thái PENDING:

~~~text
UpdateItem:
    Key = (PK, SK)

UpdateExpression:
    SET #status = :paid

ConditionExpression:
    #status = :pending

ExpressionAttributeNames:
    #status = "status"

Values:
    :paid = "PAID"
    :pending = "PENDING"
~~~

Đây là kiểm tra điều kiện cập nhật **trên item hiện tại** để xử lý concurrency. Vẫn cần validate request và xem idempotency/transaction nếu thao tác liên quan nhiều item.

### 14.3. if_not_exists không phải default cho toàn hệ

Trong DynamoDB UpdateExpression có thể sử dụng **if_not_exists(path, value)** để gán một giá trị khi thuộc tính chưa có trong phạm vi update đó. Điều này hữu ích cho một số kiểu cập nhật, nhưng:

- Không có nghĩa mọi PutItem/UpdateItem tự động thêm default của schema.
- Không thay thế kiểm tra những field được gửi với giá trị sai.
- Một thuộc tính có kiểu **NULL** vẫn là thuộc tính tồn tại; không nên ngầm đồng nhất nó với missing.
- Khi nhiều writer đồng thời, phải xem điều kiện và mục tiêu nghiệp vụ để tránh cập nhật ngoài dự kiến.

Nếu một field default ảnh hưởng index phụ hoặc quyền, nên cân nhắc việc **ghi tường minh giá trị đã chuẩn hóa**, thay vì dựa hoàn toàn vào fallback lúc đọc.

## 15. Cassandra/ScyllaDB: schema kiểu cột và validation miền giá trị

CQL là ví dụ một mô hình NoSQL có schema bảng rõ ràng:

~~~sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id text,
    quantity int,
    unit_price_minor bigint,
    currency text,
    status text,
    processing_mode text,
    created_at timestamp,
    schema_version int,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Database kiểm tra dữ liệu theo kiểu CQL khi ghi. Nhưng **quantity int** chấp nhận các số nguyên trong miền kiểu, không tự có quy tắc **quantity >= 1**. **status text** không tự giới hạn giá trị trong một enum nghiệp vụ.

Một lệnh ghi từ service vẫn cần validate:

~~~text
quantity: integer, 1..1000
unit_price_minor: >= 0, trong miền bigint và business cap
currency: trong tập được phép
status: theo state machine
processing_mode: default do service gán nếu missing
~~~

Với cập nhật có điều kiện, một CQL engine hỗ trợ lightweight transaction có thể dùng cú pháp dạng:

~~~sql
UPDATE orders_by_id
SET status = 'PAID'
WHERE tenant_id = ? AND order_id = ?
IF status = 'PENDING';
~~~

LWT có chi phí và ngữ nghĩa riêng theo sản phẩm/phiên bản; nó hỗ trợ kiểm soát cạnh tranh **ở điều kiện đã khai báo**, không biến mọi câu SQL/CQL thành transaction serializable xuyên các bảng tùy ý.

### 15.1. Missing, null, UNSET và tombstone

Trong CQL, việc không cung cấp cột, truyền **null** hoặc dùng cơ chế **UNSET** của driver/bound statement có thể tạo những hành vi khác nhau với dữ liệu hiện có và tombstone. Không được xem ba trạng thái là một khi xây API PATCH hoặc migration.

Ngoài ra:

- Primary key phải được cung cấp đúng định dạng theo API.
- Các kiểu collection có ngữ nghĩa update/delete riêng.
- TTL làm giá trị hết hạn; một giá trị thiếu vì TTL khác với một field chưa từng được tạo về mặt nghiệp vụ.
- Một số công nghệ wide-column có counter riêng; counter có quy tắc schema/retry khác field bigint thường.
- Cassandra và ScyllaDB có khác biệt tính năng/phiên bản; không copy một quy tắc default hoặc validation chưa kiểm chứng từ hệ này sang hệ kia.

Vì vậy, validation miền giá trị và default thường thuộc tầng service/consumer, còn CQL schema bảo vệ kiểu lưu trữ và cấu trúc khóa.

## 16. Redis và search index: không nhầm kiểu lệnh với schema dữ liệu

### 16.1. Redis

Redis string, hash, set và sorted set có kiểu thao tác riêng. Ví dụ:

~~~redis
HSET order:T1:O-101 quantity 2 status PENDING processingMode STANDARD
HGETALL order:T1:O-101
~~~

Một hash có thể chứa các field tên bất kỳ; **HSET** không tự biết quantity phải 1–1.000 hay status thuộc enum. Một lệnh **HINCRBY** kiểm tra giá trị có phù hợp phép toán số nguyên của nó, nhưng điều đó không thay thế schema cho toàn bộ object.

Nếu Redis lưu JSON qua module/tính năng bổ sung, cần xem phiên bản/module và khả năng validation cụ thể. Không giả định mọi cách lưu JSON trên Redis đều có MongoDB-style collection validator.

Khi Redis là **cache**, có thể lựa chọn schema phiên bản hóa và fallback, nhưng cache không được trở thành nguồn duy nhất cho bất biến quan trọng nếu độ bền/nhất quán không đáp ứng nghiệp vụ.

### 16.2. Elasticsearch/OpenSearch và mapping

Search index có **mapping** để mô tả cách các field được index, ví dụ keyword, date, numeric hoặc text. Chế độ dynamic mapping có thể tự nhận field mới hoặc, với cấu hình strict phù hợp, từ chối field không được nhận diện. Tuy nhiên:

- Mapping không tương đương một validator đầy đủ cho mọi field bắt buộc và quy tắc cross-field.
- Một số engine có cơ chế **coercion** hoặc **ignore malformed** theo mapping; chúng có thể làm kết quả index khác kỳ vọng nếu không kiểm soát.
- Tùy chọn **null_value** có thể định nghĩa giá trị dùng khi index field null, nhưng không nên hiểu rằng nó tự sửa **_source** thành một stored default.
- Dữ liệu search thường là **read model**; nguồn nghiệp vụ vẫn cần schema/transaction riêng.

Đừng chỉ vì search query vẫn chạy mà kết luận dữ liệu nguồn đã hợp lệ.

## 17. Java: validation ở tầng API và phát hiện missing/null rõ ràng

Với backend Java, có thể dùng Jakarta Bean Validation kết hợp parser JSON và logic domain. Ví dụ DTO cho create:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateOrderRequest(
    @NotBlank String orderId,
    @NotNull @Min(1) @Max(1000) Integer quantity,
    @NotNull @PositiveOrZero Long unitPriceMinor,
    @NotNull @Pattern(regexp = "VND|USD") String currency,
    String processingMode,
    String note
) {}
~~~

Các annotation minh họa một phần schema; trong service vẫn phải:

- Giới hạn độ dài và pattern của orderId.
- Kiểm tra trần tiền nghiệp vụ.
- Phân biệt **processingMode thiếu** với **processingMode được gửi null**, nếu contract yêu cầu.
- Giới hạn note 500 ký tự.
- Gắn tenantId, status, createdAt từ server.
- Bảo vệ uniqueness/trạng thái bằng database operation.
- Trả lỗi validation có cấu trúc, không để exception nội bộ lộ chi tiết database.

### 17.1. Tại sao kiểu DTO đơn giản chưa đủ để phân biệt missing/null?

Với một số cấu hình deserialize, cả hai request:

~~~json
{}
~~~

~~~json
{
  "processingMode": null
}
~~~

đều tạo object có **processingMode == null**. Nếu hợp đồng yêu cầu chỉ missing được default, sau parse vào DTO kiểu trên có thể **mất thông tin field có mặt hay không**.

Có thể kiểm tra sự hiện diện bằng **Jackson JsonNode** hoặc dùng DTO wrapper biểu diễn ba trạng thái missing/null/value:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;

public final class RequestDefaults {
    private static final Set<String> MODES =
        Set.of("STANDARD", "EXPRESS");

    public static String resolveProcessingMode(JsonNode root) {
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Expected JSON object");
        }

        JsonNode mode = root.get("processingMode");

        // get(...) trả null khi field không có.
        if (mode == null) {
            return "STANDARD";
        }

        // Explicit JSON null không phải missing.
        if (!mode.isTextual()) {
            throw new IllegalArgumentException(
                "processingMode must be a string"
            );
        }

        String value = mode.textValue();

        if (!MODES.contains(value)) {
            throw new IllegalArgumentException(
                "Unsupported processingMode"
            );
        }
        return value;
    }
}
~~~

Code minh họa **một** field để làm rõ semantics; không nên tự viết lại toàn bộ JSON Schema validator từ đầu nếu dự án đã có thư viện phù hợp. Khi dùng Jackson, hãy cân nhắc cấu hình chặn duplicate JSON properties và nhận kiểu sai; không dựa vào tính năng ép kiểu mặc định của một phiên bản thư viện mà chưa xác minh.

### 17.2. Validation ở request chưa phải validation ở database

Ngay cả DTO đầy đủ cũng có thể bị bỏ qua khi dữ liệu được ghi bởi batch job, importer, test setup, migration hoặc consumer sự kiện. Những đường ghi này cần cùng contract, hoặc ít nhất một lớp ràng buộc tại database cho điều kiện hỗ trợ.

Ngoài ra, annotation **@Min** không giúp bảo vệ trường hợp hai request cùng đọc stock = 1 rồi cùng trừ. Phải dùng **conditional update/transaction** để bảo vệ bất biến concurrency.

## 18. PUT, PATCH và JSON Merge Patch: thiếu field có nghĩa gì?

Ngữ nghĩa cập nhật quyết định default và validation.

### PUT — thay thế toàn bộ resource theo contract

Một API PUT thường được thiết kế để gửi **representation đầy đủ**. Nếu processingMode là field bắt buộc trong representation lưu trữ mà client không gửi, server cần quy tắc rõ: từ chối, gán default theo API hay giữ giá trị cũ? Không được pha trộn tùy từng endpoint.

### PATCH — chỉ thay đổi field được nêu

Với partial update thông thường:

~~~json
{
  "note": "Giao tại quầy lễ tân"
}
~~~

Các field bị bỏ qua phải **giữ nguyên**. Không tự reset status, price hoặc processingMode về default.

### JSON Merge Patch — null có ngữ nghĩa xóa

Nếu API công bố sử dụng **JSON Merge Patch** (RFC 7396), một member mang giá trị **null** trong patch object có ngữ nghĩa **loại bỏ member đó** ở target, không đơn giản là “lưu JSON null”. Đây là lý do API phải nêu rõ mình dùng loại PATCH nào:

~~~json
{
  "note": null
}
~~~

Với JSON Patch (RFC 6902), thao tác xóa được biểu diễn tường minh bằng **op: remove**. Những quy tắc này **không tự áp dụng cho mọi endpoint PATCH**; sản phẩm có thể định nghĩa PATCH riêng nhưng phải tài liệu hóa.

### 18.1. Validate bản kết quả, không chỉ mảnh patch

Ngay cả patch chứa một field đúng kiểu vẫn có thể đưa document cuối vào trạng thái vi phạm quy tắc giữa các field.

Ví dụ:

~~~text
stored:
    startAt = 10:00
    endAt   = 12:00

patch:
    startAt = 13:00
~~~

startAt mới tự nó parse hợp lệ, nhưng **startAt < endAt** bị phá vỡ. Cần validate **trạng thái cuối** trong ranh giới cập nhật phù hợp. Khi dữ liệu bị sửa đồng thời, nên dùng version/CAS hoặc transaction để tránh kiểm tra trên snapshot cũ rồi ghi lên trạng thái mới.

## 19. Cross-field validation và bất biến không thể chỉ viết bằng schema

Một số quy tắc cần nhìn nhiều field:

~~~text
Nếu processingMode = EXPRESS:
    shippingAddress phải đầy đủ.
Nếu couponCode không null:
    discountAmount phải được xác định hợp lệ.
expiresAt phải sau createdAt.
paidAmount không thể lớn hơn amountDue nếu không có logic riêng.
status = PAID phải có paymentId hợp lệ.
~~~

Các rule này có thể được biểu diễn một phần bằng **if/then/else**, **oneOf**, hoặc validator expression tùy công cụ; nhưng khả năng thực thi khác nhau giữa JSON Schema library, MongoDB validator và các ngôn ngữ ứng dụng. Không phải trường hợp nào cũng phù hợp với một file schema tĩnh.

Càng quan trọng: nhiều rule dựa trên **dữ liệu bên ngoài document**:

- Username phải duy nhất trong tenant.
- Reservation không được trùng ghế đang có hiệu lực.
- Stock không thể âm khi nhiều khách đặt đồng thời.
- Coupon còn hạn sử dụng và chưa vượt quota.
- Không được cấp quyền ADMIN nếu caller không đủ thẩm quyền.

Đó không chỉ là validation cú pháp. Cần **đọc dữ liệu tham chiếu có ngữ nghĩa phù hợp**, kiểm tra quyền, unique index, transaction hoặc conditional write; và cân nhắc timeout/retry.

## 20. Schema evolution: từ version 1 lên version 2

NoSQL linh hoạt khiến một collection có thể chứa nhiều phiên bản document trong thời gian dài. Điều đó cần được quản lý bằng **schema evolution**, không phải chờ dữ liệu cũ tự biến mất.

Giả sử:

~~~json
{
  "orderId": "O-101",
  "quantity": 2,
  "schemaVersion": 1
}
~~~

V2 bổ sung **processingMode**, **currency** và **createdAt**. Những điều cần quyết định:

1. Có thể suy ra currency cho order cũ từ tenant/store không, hay cần xác định bằng nguồn lịch sử?
2. processingMode của order cũ có thực sự tương đương STANDARD không?
3. createdAt có tồn tại trong log/source khác không? Không gán tất cả đơn cũ thành thời điểm migration.
4. Query mới có lọc processingMode/currency không? Nếu có, fallback khi đọc liệu đã đủ hay phải backfill?
5. Old app instances còn ghi v1 không trong lúc rolling deployment?
6. Consumer cũ có hiểu event v2 không?
7. Chế độ DB validation có từ chối các bản ghi cũ khi update field khác không?
8. Nếu backfill sai, có rollback mà không phá dữ liệu đã được cập nhật sau đó không?

### 20.1. Expand → migrate → contract

Một kế hoạch triển khai thường an toàn hơn thay schema cứng ngay lập tức:

~~~mermaid
flowchart TD
    A[Đo dữ liệu cũ và trường hợp sai] --> B[Expand: reader chấp nhận v1 và v2]
    B --> C[Writer mới ghi v2 có default rõ ràng]
    C --> D[Backfill v1 theo batch có checkpoint]
    D --> E[Đối soát số lượng, index và ngữ nghĩa]
    E --> F[Siết validation / ngừng viết v1]
    F --> G[Contract: bỏ fallback khi đủ điều kiện]
~~~

Giai đoạn mở rộng có thể hỗ trợ cả v1/v2; giai đoạn migration chuẩn hóa bản ghi cũ; giai đoạn contract mới bắt buộc v2. Đừng siết **required** trong database khi phần lớn dữ liệu cũ chưa được xử lý và những đường ghi cũ vẫn đang hoạt động, nếu điều đó làm hỏng API.

### 20.2. Backfill không được ghi đè thay đổi mới

Một job migration đọc document v1, rồi có request thật sửa order. Nếu job ghi lại toàn bộ bản cũ kèm processingMode, nó có thể ghi đè cập nhật mới. Cần:

- Update chỉ các field cần bổ sung.
- Điều kiện theo **schemaVersion/version** hoặc field chưa tồn tại.
- Batch nhỏ, checkpoint và retry idempotent.
- Quan sát conflict; không retry ghi đè vô điều kiện.
- Thử rollback và đối soát dữ liệu đã chuyển đổi.

Ví dụ ý tưởng MongoDB:

~~~javascript
db.orders.updateMany(
  {
    processingMode: { $exists: false },
    schemaVersion: 1
  },
  {
    $set: {
      processingMode: "STANDARD",
      schemaVersion: 2
    }
  }
);
~~~

Ví dụ này **chỉ đúng nếu mọi record v1 thật sự có processingMode mặc định STANDARD và không có các field v2 khác còn thiếu**. Trong dự án thật, cần chuyển đổi đủ schema và xử lý các bản ghi ngoại lệ trước khi tuyên bố migration hoàn tất.

## 21. Schema validation cho event và hệ bất đồng bộ

Một bản ghi ở database có thể hợp lệ nhưng sự kiện truyền qua broker lại không hợp lệ với consumer, ví dụ producer đổi tên field từ **unitPriceMinor** sang **price** khi consumer cũ vẫn dùng tên cũ.

Một event contract nên có:

~~~json
{
  "eventId": "E-1001",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "aggregateId": "O-101",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-14T10:30:00Z",
  "payload": {
    "tenantId": "T1",
    "quantity": 2,
    "unitPriceMinor": 125000,
    "currency": "VND",
    "processingMode": "STANDARD"
  }
}
~~~

Cần kiểm tra:

- **Producer** có phát event đúng version với field đủ và kiểu đúng không?
- **Consumer** có xử lý version cũ còn tồn trong queue/replay không?
- Default nào được producer materialize; consumer có nên tự suy ra default mới từ event cũ không?
- Trường mới thêm có backward/forward compatibility theo chính sách không?
- Có field đổi ý nghĩa nhưng giữ nguyên tên không?
- Duplicate/out-of-order event có được bảo vệ bằng eventId và aggregateVersion không?
- Có giới hạn message size, nesting, dữ liệu cá nhân và retention không?

**Schema registry** hoặc định dạng có schema như Avro/Protobuf có thể giúp quản lý compatibility, nhưng cấu trúc hợp lệ vẫn không tự giải quyết **idempotency, business invariants hay thứ tự sự kiện**.

## 22. Rủi ro bảo mật khi validation lỏng

Schema sai không chỉ gây lỗi dữ liệu mà còn có thể mở đường cho thao tác không được phép.

### 22.1. Mass assignment

Client gửi:

~~~json
{
  "orderId": "O-101",
  "quantity": 2,
  "status": "PAID",
  "tenantId": "another-tenant",
  "isAdmin": true
}
~~~

Nếu service tự động sao chép mọi field của request vào stored document, client có thể sửa field mà server phải sở hữu. Cần **allowlist field được phép cập nhật**, lấy tenant từ auth và kiểm tra quyền khi thay đổi trạng thái. Validator DB có thể chặn những field không thuộc schema, nhưng không tự quyết định caller nào được quyền thay status từ PENDING sang PAID.

### 22.2. Key injection và đường cập nhật động

Không dùng nguyên một object không tin cậy để tạo lệnh update có operator hoặc path động nếu chưa kiểm tra. Với MongoDB, phải cẩn thận khi xây filter/update từ dữ liệu khách gửi; với Redis, không ghép tenantId từ input tùy ý thành key truy cập dữ liệu người khác. Cần dùng API parameterized, allowlist tên field và ràng buộc tenant.

### 22.3. Payload gây cạn tài nguyên

Một yêu cầu JSON lớn, mảng hàng trăm nghìn phần tử hoặc object lồng rất sâu có thể tiêu thụ CPU/RAM trước khi logic business kịp chạy. Giới hạn kích thước body, độ sâu parser, số phần tử, timeout và giới hạn số record trong batch phải nằm ở tầng cửa vào, không đợi database từ chối do vượt giới hạn item/document.

### 22.4. Lỗi validation cần an toàn thông tin

Phản hồi API nên giúp client biết field nào sai nhưng không lộ cấu trúc nội bộ, truy vấn database, thông tin của tenant khác hoặc secrets. Không ghi toàn bộ request chứa dữ liệu cá nhân vào log chỉ để debug. Có thể log mã lỗi, field path, requestId và các thống kê phù hợp quyền truy cập.

## 23. Thiết kế API lỗi validation nhất quán

Một lỗi validation nên có khả năng xử lý bằng máy và hữu ích cho người phát triển client:

~~~json
{
  "error": "VALIDATION_FAILED",
  "message": "Request payload does not satisfy the contract",
  "requestId": "req-123",
  "details": [
    {
      "path": "quantity",
      "code": "OUT_OF_RANGE",
      "min": 1,
      "max": 1000
    },
    {
      "path": "processingMode",
      "code": "INVALID_ENUM",
      "allowed": ["STANDARD", "EXPRESS"]
    }
  ]
}
~~~

Cần phân biệt:

| Nhóm lỗi | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **INVALID_JSON** | JSON sai cú pháp | Chưa parse được payload. |
| **UNKNOWN_FIELD** | Client gửi isAdmin | Không được phép cung cấp field. |
| **TYPE_MISMATCH** | quantity = "two" | Kiểu không đúng. |
| **MISSING_REQUIRED** | Không có orderId | Thiếu field bắt buộc. |
| **EXPLICIT_NULL_NOT_ALLOWED** | quantity = null | Có field nhưng null không hợp lệ. |
| **OUT_OF_RANGE** | quantity = 0 hoặc 1001 | Kiểu đúng nhưng vượt miền. |
| **INVALID_FORMAT** | Timestamp không hợp lệ | Không đáp ứng định dạng/ngữ nghĩa. |
| **BUSINESS_CONFLICT** | OrderId đã tồn tại | Xung đột dữ liệu hiện hành. |
| **STATE_TRANSITION_DENIED** | CANCELLED → PAID | Vi phạm state machine. |
| **FORBIDDEN** | Caller sửa field tenant khác | Không có quyền, không phải chỉ lỗi schema. |

HTTP status cụ thể phụ thuộc contract API; nhiều API dùng **400** cho input không hợp lệ, **409** cho xung đột trạng thái/uniqueness và **403** cho thiếu quyền, nhưng không nên tạo quy tắc cứng khi hệ đã có convention. Quan trọng là **phân loại chính xác**, để client không retry vô hạn một lỗi nhập liệu chắc chắn không hợp lệ.

## 24. Ma trận kiểm thử dữ liệu biên

Thiết kế test nên đi theo **partition of input domain**: hợp lệ điển hình, đúng biên, ngoài biên, thiếu, null, sai kiểu và dữ liệu có nguy cơ bảo mật.

| Nhóm | Trường hợp | Kỳ vọng nếu theo hợp đồng ví dụ |
| --- | --- | --- |
| Quantity | 1 | Chấp nhận |
| Quantity | 1000 | Chấp nhận |
| Quantity | 0, -1, 1001 | Từ chối |
| Quantity | 1.5, "2", null | Từ chối |
| Price minor | 0 | Chấp nhận nếu hàng miễn phí được phép |
| Price minor | Giá trị âm | Từ chối |
| Price minor | Vượt trần hoặc mất precision khi parse | Từ chối |
| Currency | VND | Chấp nhận |
| Currency | "vnd", "EUR" nếu không nằm trong enum | Từ chối hoặc mapping theo policy tường minh |
| Processing mode | Missing | Áp default STANDARD |
| Processing mode | Null | Từ chối, không tự default |
| Processing mode | EXPRESS | Chấp nhận |
| Note | Missing | Giữ thiếu theo contract |
| Note | Null | Chấp nhận theo contract |
| Note | Chuỗi 500 ký tự | Chấp nhận |
| Note | Chuỗi 501 ký tự | Từ chối |
| Order ID | Rỗng, quá dài, ký tự ngoài pattern | Từ chối |
| JSON object | Có field isAdmin không khai báo | Từ chối |
| JSON object | Property trùng tên | Từ chối theo parser policy |
| Array | Empty, > maxItems, phần tử sai kiểu | Theo rule đã chốt |
| Time | Ngày không tồn tại, timezone thiếu | Từ chối nếu yêu cầu instant có offset |
| PUT/PATCH | Thiếu processingMode trong PATCH | Giữ giá trị cũ |
| Legacy record | Thiếu field mới | Đọc theo compatibility hoặc backfill, không âm thầm sai ngữ nghĩa |
| Concurrent writes | Hai yêu cầu trùng orderId | Tối đa một create được chấp nhận |
| Import/consumer | Dữ liệu vượt schema | Bị chặn hoặc đưa quarantine theo policy |

Các test dùng những trường hợp **min-1, min, min+1, max-1, max, max+1** cho số và độ dài, không chỉ input “đẹp”. Với string Unicode, thử ký tự tổ hợp, emoji, dấu tiếng Việt, khoảng trắng và các format normalize khác nhau.

### 24.1. Property-based và fuzz testing

Ngoài case viết tay, có thể sinh tự động:

- Số nguyên quanh ranh giới int32/int64 và miền nghiệp vụ.
- Chuỗi ngẫu nhiên với Unicode, control characters và độ dài lớn.
- Cấu trúc JSON lồng sâu, mảng rỗng và phần tử sai kiểu.
- Field bị thiếu, null hoặc lặp.
- Date/time gần biên tháng, năm nhuận và timezone.
- Chuỗi cập nhật PATCH làm chuyển trạng thái giữa nhiều phiên bản schema.

Property quan trọng:

~~~text
Với mọi CreateOrderRequest được chấp nhận:
    quantity ∈ [1,1000]
    currency ∈ {VND, USD}
    processingMode ∈ {STANDARD, EXPRESS}
    tenantId là tenant đã xác thực
    status khởi tạo là PENDING
    stored record đáp ứng stored schema
~~~

Cần test riêng concurrency/transaction vì việc tạo input hợp lệ không chứng minh **hai request hợp lệ chạy đồng thời** giữ được uniqueness hoặc không oversell.

## 25. Kiểm thử xuyên lớp để tránh mỗi nơi hiểu schema khác nhau

Một bài học quan trọng với NoSQL là **cùng field đi qua nhiều hệ khác nhau**:

~~~text
Frontend JSON
    -> API parser
    -> Java DTO
    -> Domain model
    -> Driver serialization
    -> Database BSON/item/column
    -> CDC event
    -> Consumer
    -> Search index/cache
    -> API đọc
~~~

Ví dụ unitPriceMinor là **long** trong Java nhưng một consumer JavaScript parse thành Number không an toàn; hoặc createdAt là instant trong DB nhưng được xuất thành chuỗi không timezone; hoặc processingMode thiếu trong document v1 nhưng search index chỉ biết v2.

Kiểm thử hợp đồng có thể gồm:

1. **Round-trip test:** ghi qua driver và đọc lại, bảo đảm kiểu và precision không đổi.
2. **Cross-language test:** cùng payload qua Java/JavaScript hoặc các producer/consumer khác nhau.
3. **Schema compatibility test:** reader mới đọc được dữ liệu/event cũ theo policy và reader cũ xử lý field thêm đúng.
4. **Migration test:** backfill không làm mất field, không ghi đè cập nhật đồng thời.
5. **Index/query test:** missing/null/default được query như mong muốn trên dữ liệu đã migration.
6. **Authorization test:** field hệ thống không thể bị client sửa qua create/patch/bulk.
7. **Failure test:** khi một nơi từ chối dữ liệu, không phát event hoặc commit một phần trái hợp đồng.
8. **Retention/TTL test:** field mất vì TTL/delete không bị diễn giải nhầm là default nghiệp vụ nếu nó mang nghĩa khác.

## 26. Quy trình triển khai validation cho collection đã có dữ liệu

Giả sử một hệ đang vận hành có 10 triệu document, trong đó một số quantity là string do phiên bản cũ. Bật ngay validator strict có thể làm những thao tác update chạm các document lỗi bị từ chối.

Một quy trình triển khai có kiểm soát:

~~~mermaid
flowchart TD
    A[Định nghĩa contract và field ownership] --> B[Thống kê kiểu và dữ liệu lỗi hiện có]
    B --> C[Đưa validation vào producer/API]
    C --> D[Quan sát warn/shadow validation nếu công cụ hỗ trợ]
    D --> E[Backfill dữ liệu cũ theo batch có checkpoint]
    E --> F[Đối soát số record và query/index]
    F --> G[Bật enforcement tại database]
    G --> H[Theo dõi lỗi và rollback theo kế hoạch]
~~~

Các bước chi tiết:

1. **Inventorize dữ liệu:** đếm missing, null, sai kiểu, ngoài miền, enum lạ và field ngoại lai theo từng schemaVersion.
2. **Chốt policy:** giá trị nào được sửa tự động, giá trị nào cần người vận hành quyết định, cái nào phải đưa quarantine?
3. **Sửa các đường ghi mới trước:** API, consumer, importer và batch job phải cùng tuân hợp đồng.
4. **Shadow/warn validation:** thu metric lỗi mà chưa chặn lưu nếu sản phẩm hỗ trợ chế độ phù hợp.
5. **Backfill theo nhóm nhỏ:** có checkpoint, idempotency, điều kiện version và rate limiting.
6. **Đối soát:** schemaVersion, số bản ghi còn lỗi, index mới và tác động lên query.
7. **Bật enforcement:** chọn action/level rõ theo phiên bản database, tránh làm gián đoạn update legacy ngoài dự kiến.
8. **Giám sát:** tỷ lệ validation error, fail của migration, request bị từ chối, latency ghi, retry.
9. **Rollback có điều kiện:** nếu siết rule sai, phải có đường nới/khôi phục mà không âm thầm mất các bản ghi đã thay đổi.

Không sửa hàng triệu bản ghi bằng một lệnh update vô điều kiện chỉ để “có field mới” mà không kiểm tra ngữ nghĩa lịch sử.

## 27. Các sai lầm thường gặp

**“NoSQL schemaless nên không cần validation.”** Ứng dụng vẫn có contract. Dữ liệu sai có thể gây lỗi khi parse, index, tính toán hoặc migration.

**“required nghĩa là non-null và non-empty.”** Required chỉ kiểm tra hiện diện; null, chuỗi rỗng và giá trị ngoài miền phải có quy tắc riêng.

**“Thấy default trong JSON Schema nghĩa là database tự gán.”** Default là annotation theo chuẩn; áp dụng phải do công cụ/ứng dụng làm tường minh.

**“Missing và null luôn tương đương.”** Chúng khác về ngữ nghĩa request, PATCH, query, index và update expression.

**“Dùng || để gán default là an toàn.”** Nó có thể ghi đè 0 và false, là những giá trị hợp lệ trong nhiều hợp đồng.

**“Số trong JSON luôn vừa kiểu long và chính xác.”** Các thư viện/language có miền số, precision và coercion khác nhau.

**“Validator trong database thay thế business transaction.”** Một order hợp lệ theo schema vẫn có thể trùng ID, chuyển trạng thái sai hoặc bán quá tồn nếu không có điều kiện ghi.

**“Schema mới sẽ tự sửa document cũ.”** Thay validator không tự backfill dữ liệu lịch sử, và một số chế độ có thể gây lỗi update trên record cũ.

**“Một PATCH không có field nghĩa là reset default.”** Với partial update, thông thường nó có nghĩa giữ nguyên.

**“Đủ field để lưu là đủ cho read model.”** Field có default chỉ tại tầng đọc có thể không được index; query trực tiếp database vẫn thấy missing.

**“Mọi database JSON có cùng JSON Schema.”** MongoDB $jsonSchema, JSON Schema thư viện API và mapping của search engine là các cơ chế khác nhau.

**“Validate trước khi ghi là đủ để chống oversell.”** Kiểm tra dựa trên dữ liệu đọc trước có thể bị thay đổi bởi transaction khác; cần conditional write/transaction.

## 28. Bài thực hành: validator cho coupon

Xây dựng API tạo coupon với mô hình:

~~~json
{
  "couponCode": "WELCOME10",
  "tenantId": "T1",
  "discountType": "PERCENT",
  "discountValue": 10,
  "maxUses": 100,
  "usedCount": 0,
  "validFrom": "2026-11-14T00:00:00Z",
  "validUntil": "2026-12-31T23:59:59Z",
  "enabled": true
}
~~~

### Yêu cầu

- **couponCode** là string có định dạng và độ dài đã định nghĩa; duy nhất trong tenant.
- **discountType** chỉ là **PERCENT** hoặc **FIXED_AMOUNT**.
- Nếu PERCENT, **discountValue** nằm trong miền được phép, ví dụ 1–100.
- Nếu FIXED_AMOUNT, giá trị phải dương và gắn currency phù hợp.
- **maxUses** có thể được bỏ qua nếu “không giới hạn” là một trạng thái hợp lệ, nhưng không được ngầm coi null = 0 nếu không có policy.
- **usedCount** bắt đầu ở 0 và do server quản lý; client không được gửi để tự cấp quota.
- **validUntil** phải sau **validFrom**.
- **enabled** có default true khi tạo nhưng explicit false phải được giữ.
- Khi sử dụng coupon, phải bảo đảm **usedCount < maxUses** (nếu có giới hạn) và không tính trùng requestId.

### Câu hỏi học viên cần giải

1. Viết request schema phân biệt field do client và server sở hữu.
2. Quyết định **missing**, **null** và **0** có nghĩa gì với maxUses.
3. Tạo bảng case biên cho percent = 0, 1, 100, 101, số thực và chuỗi.
4. Chọn cách validate thời gian khi client gửi timezone khác nhau.
5. Chỉ ra rule nào thực hiện được bằng JSON Schema và rule nào phải ở domain/database.
6. Đề xuất unique constraint hoặc conditional create cho **(tenantId, couponCode)**.
7. Thiết kế conditional update hoặc transaction để không vượt maxUses khi nhiều người dùng coupon đồng thời.
8. Nêu cách migrate coupon v1 chưa có enabled nhưng một số coupon cũ vốn đã bị tạm khóa.
9. Xác định API PATCH cho explicit null và field thiếu.
10. Viết test retry cùng requestId sau timeout để không cộng usedCount hai lần.

Bài tập nhấn mạnh: **validation của hình dạng dữ liệu** và **bảo vệ bất biến khi ghi đồng thời** phải được kết hợp, nhưng không phải cùng một cơ chế.

## 29. Checklist ra quyết định trước khi triển khai

~~~text
[ ] Có request schema và stored schema riêng nếu cần.
[ ] Xác định field nào do client, server hoặc consumer sở hữu.
[ ] Mỗi field có required/optional/nullability rõ ràng.
[ ] Missing, null, empty, zero và false được phân biệt.
[ ] Default chỉ áp dụng tại thời điểm và điều kiện đã định.
[ ] Kiểu dữ liệu được serialize đúng qua mọi ngôn ngữ/driver.
[ ] Numeric range, precision, overflow và currency được kiểm tra.
[ ] Date/time/timezone và cross-field relation được định nghĩa.
[ ] String normalization, độ dài byte/ký tự và uniqueness rõ ràng.
[ ] Array/object có giới hạn phần tử, độ sâu và kích thước.
[ ] Database validator/ràng buộc được cấu hình theo đúng sản phẩm.
[ ] Unique key, state transition và concurrency được bảo vệ riêng.
[ ] PUT/PATCH semantics và cách xử lý explicit null được tài liệu hóa.
[ ] Dữ liệu cũ có audit, schemaVersion và kế hoạch migration.
[ ] Producer/consumer event có compatibility và validation.
[ ] API trả lỗi phân loại, không lộ dữ liệu nhạy cảm.
[ ] Có test biên, fuzz, round-trip, concurrent write và rollback.
~~~

Danh sách này là công cụ triển khai, không thay thế việc đọc tài liệu phiên bản cụ thể hoặc kiểm chứng trên môi trường thật.

## Kết luận

**Schema validation** giúp ngăn dữ liệu sai cấu trúc và kiểu; **giá trị mặc định** giúp xử lý field thiếu theo chính sách; **kiểm tra dữ liệu biên** bảo vệ các miền số, chuỗi, thời gian, array/object và giới hạn kích thước vốn dễ bị bỏ qua ở những trường hợp hiếm. Trong NoSQL, những trách nhiệm đó được phân bổ khác nhau giữa database, API, driver và consumer tùy sản phẩm.

Thiết kế tốt bắt đầu bằng một **hợp đồng tường minh cho request và dữ liệu lưu trữ**, phân biệt **missing/null/empty/zero/false**, kiểm soát default ở đúng thời điểm, xác định migration cho bản ghi cũ và test các giới hạn thật. Đồng thời, phải giữ một ranh giới rõ: **dữ liệu hợp lệ về schema chưa chắc đúng về nghiệp vụ khi có cạnh tranh**. Uniqueness, trạng thái, quota và tồn kho vẫn cần conditional write, transaction hoặc giao thức phù hợp.

Một hệ NoSQL đáng tin cậy không phải hệ từ chối mọi thay đổi schema, mà là hệ có thể **tiến hóa schema mà dữ liệu cũ và mới đều được diễn giải đúng, kiểm tra nhất quán và phục hồi được khi có lỗi**.
