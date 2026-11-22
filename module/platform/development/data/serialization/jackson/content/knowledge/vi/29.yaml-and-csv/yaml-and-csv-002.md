# Phân biệt kiểu dữ liệu YAML và biểu diễn JSON tương ứng

YAML và JSON đều dùng để trao đổi dữ liệu có cấu trúc. Một file cấu hình có thể được viết bằng YAML để dễ đọc, sau đó được ứng dụng Java đọc vào object bằng Jackson. Một API lại thường nhận hoặc trả JSON. Khi làm việc với cả hai định dạng, cần hiểu rằng chúng có thể biểu diễn cùng một ý nghĩa dữ liệu nhưng cú pháp, cách nhận diện kiểu scalar và khả năng của định dạng không hoàn toàn giống nhau.

YAML có ba nhóm node cơ bản: **scalar**, **sequence** và **mapping**. JSON có các kiểu tương ứng là **string/number/boolean/null**, **array** và **object**. Tuy nhiên, YAML còn có tag, anchor, alias, block scalar, nhiều cách viết scalar và khả năng biểu diễn key không phải chuỗi. JSON có một tập kiểu nhỏ và cú pháp chặt hơn. Đặc biệt, một scalar YAML không có dấu ngoặc kép có thể được parser nhận diện thành số, boolean, null hoặc một kiểu đặc biệt tùy schema và phiên bản parser.

Khi chuyển YAML sang JSON hoặc bind YAML vào Java bằng Jackson, điều quan trọng là xác định **kiểu dữ liệu mong muốn**, không chỉ nhìn vào hình thức chữ. Hãy dùng quote khi muốn bảo đảm một scalar là string, chọn kiểu Java theo semantics, kiểm thử với đúng phiên bản Jackson/SnakeYAML đang chạy và không giả định mọi cấu trúc YAML đều có thể được biểu diễn nguyên trạng trong JSON.

## 1. Cấu trúc dữ liệu cơ bản của hai định dạng

YAML và JSON có thể mô tả cùng một cây dữ liệu bằng ba cấu trúc chính:

| Ý nghĩa | YAML node | JSON tương ứng | Ví dụ |
|---|---|---|---|
| Một giá trị đơn | Scalar | String, number, boolean hoặc null | Tên, tuổi, trạng thái |
| Danh sách có thứ tự | Sequence | Array | Danh sách server |
| Tập cặp key-value | Mapping | Object | Cấu hình ứng dụng |

Ví dụ YAML:

~~~yaml
service:
  name: billing-api
  port: 8080
  enabled: true
  tags:
    - finance
    - internal
~~~

JSON tương ứng:

~~~json
{
  "service": {
    "name": "billing-api",
    "port": 8080,
    "enabled": true,
    "tags": [
      "finance",
      "internal"
    ]
  }
}
~~~

Mapping YAML tương ứng với object JSON; sequence YAML tương ứng với array JSON; scalar YAML được chuyển thành một trong các kiểu scalar JSON. Cùng một cấu trúc logic có thể có cách trình bày khác nhau: YAML thường dùng indentation và dấu gạch đầu dòng, còn JSON dùng dấu ngoặc nhọn, ngoặc vuông và dấu phẩy.

### 1.1. Mapping và object

Mapping chứa các cặp key-value. YAML cho phép viết theo block style:

~~~yaml
database:
  host: db.internal
  port: 5432
~~~

Hoặc flow style:

~~~yaml
database: {host: db.internal, port: 5432}
~~~

JSON chỉ có dạng object với key là string:

~~~json
{
  "database": {
    "host": "db.internal",
    "port": 5432
  }
}
~~~

Tên key trong JSON bắt buộc được đặt trong dấu ngoặc kép. YAML thường cho phép key dạng plain scalar không có quote. Trong các object thông thường, key YAML thường được dùng như tên property JSON; tuy nhiên YAML còn cho phép key có kiểu node khác, là điểm khác biệt cần lưu ý khi chuyển đổi.

### 1.2. Sequence và array

Sequence YAML là danh sách có thứ tự:

~~~yaml
regions:
  - ap-southeast-1
  - ap-southeast-2
  - eu-west-1
~~~

JSON array tương ứng:

~~~json
{
  "regions": [
    "ap-southeast-1",
    "ap-southeast-2",
    "eu-west-1"
  ]
}
~~~

Phần tử trong sequence/array có thể là scalar, mapping hoặc sequence khác. Ví dụ YAML:

~~~yaml
servers:
  - name: api-1
    port: 8080
  - name: api-2
    port: 8081
~~~

JSON:

~~~json
{
  "servers": [
    {"name": "api-1", "port": 8080},
    {"name": "api-2", "port": 8081}
  ]
}
~~~

Cả hai định dạng đều hỗ trợ cấu trúc lồng nhau. Jackson có thể bind sequence thành List/Set/array và mapping thành POJO/Map khi kiểu đích được cung cấp.

## 2. Scalar YAML không phải lúc nào cũng là string

Một scalar YAML có thể được diễn giải thành nhiều kiểu. Ví dụ:

~~~yaml
name: An
age: 29
active: true
nickname: null
~~~

Ý nghĩa mong muốn thường là name là string, age là integer, active là boolean và nickname là null. JSON tương ứng:

~~~json
{
  "name": "An",
  "age": 29,
  "active": true,
  "nickname": null
}
~~~

Điểm quan trọng là YAML có thể dùng plain scalar không quote, nên parser cần một schema để quyết định kiểu. JSON có cú pháp phân biệt rõ: string luôn có dấu ngoặc kép; number không có quote; boolean là true/false; null là null.

Với YAML, cùng một chuỗi ký tự có thể được hiểu khác nhau theo YAML version, schema hoặc cấu hình parser. Ví dụ các từ yes/no/on/off từng được nhận diện là boolean trong YAML 1.1, trong khi YAML 1.2 Core schema chỉ nhận các dạng true/false làm boolean. Một parser tương thích YAML 1.1 có thể cho kết quả khác parser áp dụng YAML 1.2.

**Quy tắc thực hành:** nếu dữ liệu phải là string, hãy quote nó; nếu dữ liệu phải là số/boolean/null, dùng dạng rõ ràng và kiểm thử parser. Đừng dựa vào cách một editor tô màu để kết luận kiểu thực tế.

## 3. String trong YAML và JSON

JSON chỉ có một cách biểu diễn string: đặt nội dung trong dấu ngoặc kép và escape các ký tự đặc biệt.

~~~json
{
  "message": "Hello\nJackson",
  "quote": "He said \"hello\""
}
~~~

YAML có nhiều scalar style để thể hiện string.

### 3.1. Plain scalar

Plain scalar không có quote:

~~~yaml
name: billing-api
description: Internal billing service
url: https://example.com/api
~~~

Cách viết này gọn và dễ đọc, nhưng cần cẩn trọng với chuỗi có nội dung giống boolean, null, number hoặc cú pháp YAML. Một số ký tự ở vị trí đầu có ý nghĩa cú pháp nên không thể dùng tùy ý trong plain scalar.

### 3.2. Single-quoted scalar

Single quote giữ phần lớn nội dung nguyên văn. Một dấu nháy đơn bên trong được viết thành hai dấu nháy đơn:

~~~yaml
message: 'It''s ready'
version: '0012'
switch: 'on'
~~~

Các giá trị version và switch được quote để giữ chúng là string, không phụ thuộc quy tắc implicit typing của parser.

### 3.3. Double-quoted scalar

Double quote hỗ trợ escape sequence:

~~~yaml
message: "Line one\nLine two"
path: "C:\\apps\\billing"
quote: "He said \"hello\""
~~~

JSON cũng dùng double quote và escape theo cú pháp JSON. Một số escape trong YAML có thể rộng hơn tập escape của JSON; vì vậy không thể luôn sao chép nguyên văn mọi double-quoted YAML scalar vào JSON mà không chuyển đổi.

### 3.4. Literal block scalar: dấu |

Dấu | giữ các dấu xuống dòng trong nội dung block:

~~~yaml
description: |
  Billing API
  Handles invoice creation.
  Publishes payment events.
~~~

JSON tương ứng phải biểu diễn nội dung thành một string có newline:

~~~json
{
  "description": "Billing API\nHandles invoice creation.\nPublishes payment events.\n"
}
~~~

Các quy tắc chomping như |-, | và |+ ảnh hưởng tới newline cuối. Chúng không tạo kiểu dữ liệu mới; kết quả vẫn là string.

### 3.5. Folded block scalar: dấu >

Dấu > thường gộp các dòng văn bản thông thường thành một dòng có khoảng trắng:

~~~yaml
summary: >
  This service processes invoices
  and publishes payment events
  to downstream systems.
~~~

Nội dung string thường tương đương:

~~~json
{
  "summary": "This service processes invoices and publishes payment events to downstream systems.\n"
}
~~~

Các dòng trống và indentation sâu có quy tắc riêng. Nếu nội dung cần giữ nguyên xuống dòng, dùng literal style |; nếu muốn đoạn văn dễ đọc trong YAML và được gộp dòng, dùng folded style >.

### 3.6. Khi nào cần quote string?

Nên quote các giá trị dễ bị nhận diện nhầm kiểu hoặc có ý nghĩa đặc biệt:

~~~yaml
buildNumber: "00127"
featureCode: "NO"
release: "1.0"
dateLabel: "2026-11-12"
emptyText: ""
booleanWord: "false"
nullWord: "null"
~~~

Nếu các giá trị trên phải là string, quote giúp ý định rõ ràng. Đặc biệt, mã định danh có số 0 ở đầu như postal code, account code hoặc version không nên để parser tự hiểu thành số.

## 4. Boolean: true/false và khác biệt YAML schema

Trong JSON, boolean chỉ có hai literal viết thường:

~~~json
{
  "enabled": true,
  "maintenance": false
}
~~~

YAML 1.2 Core schema cũng nhận true/false và các biến thể chữ hoa/thường tương ứng, nhưng YAML 1.1 có cách implicit resolution rộng hơn, thường bao gồm yes/no, on/off và các biến thể chữ hoa/thường.

Ví dụ YAML dễ gây nhầm:

~~~yaml
featureA: yes
featureB: no
switch: on
legacyMode: off
~~~

Tùy parser/schema, những scalar này có thể được hiểu là boolean hoặc string. Khi chuyển sang JSON, nếu chúng được hiểu là boolean thì kết quả sẽ là:

~~~json
{
  "featureA": true,
  "featureB": false,
  "switch": true,
  "legacyMode": false
}
~~~

Nếu mục tiêu thực tế là các chuỗi yes/no/on/off, hãy quote:

~~~yaml
featureA: "yes"
featureB: "no"
switch: "on"
legacyMode: "off"
~~~

Đối với cấu hình dùng nhiều công cụ khác nhau, không nên dựa vào các từ boolean ngoài true/false. Dùng true/false không quote cho boolean; dùng quote cho string.

## 5. Null, empty string và field không xuất hiện

YAML có nhiều cách biểu diễn null. Những dạng thường gặp gồm:

~~~yaml
a: null
b: Null
c: NULL
d: ~
e:
f: ""
~~~

Theo schema phổ biến, a đến e là null hoặc giá trị rỗng được resolve thành null; f là string rỗng. Kết quả JSON tương ứng có thể là:

~~~json
{
  "a": null,
  "b": null,
  "c": null,
  "d": null,
  "e": null,
  "f": ""
}
~~~

Cần phân biệt:

| YAML | Ý nghĩa thường gặp | JSON |
|---|---|---|
| key: null | Null | "key": null |
| key: ~ | Null trong schema phổ biến | "key": null |
| key: | Empty plain scalar, thường resolve thành null | "key": null |
| key: "" | String rỗng | "key": "" |
| Không có key | Property không hiện diện | Không có member |

Field không xuất hiện khác với field có giá trị null. Điều này quan trọng khi bind request cập nhật: thiếu field có thể mang nghĩa giữ nguyên; null có thể mang nghĩa xóa hoặc đặt null. YAML và JSON đều có thể thể hiện sự khác biệt đó, nhưng Java DTO và null policy phải được thiết kế tương ứng.

## 6. Integer: decimal, octal và hexadecimal

JSON number dùng cú pháp số thập phân. JSON không có literal hexadecimal hoặc octal, không cho phép dấu cộng ở đầu và không cho phép số nguyên có leading zero tùy ý.

JSON hợp lệ:

~~~json
{
  "decimal": 12,
  "negative": -12,
  "hexAsText": "0xC",
  "octalAsText": "014"
}
~~~

YAML có thể hỗ trợ nhiều dạng số nguyên theo schema:

~~~yaml
decimal: 12
hexadecimal: 0xC
octal: 0o14
~~~

Theo YAML 1.2 Core schema, prefix 0x biểu diễn hexadecimal và 0o biểu diễn octal. Các parser theo YAML 1.1 có thể có quy tắc octal khác, ví dụ cách diễn giải số bắt đầu bằng 0. Do đó, không nên dùng dạng số có leading zero nếu muốn cùng kết quả trên nhiều parser.

Khi chuyển sang JSON, các số được resolve thành giá trị số tương ứng rồi thường được ghi ở dạng decimal:

~~~json
{
  "decimal": 12,
  "hexadecimal": 12,
  "octal": 12
}
~~~

Nếu chuỗi 0xC là mã hoặc nhãn, phải quote trong YAML để giữ string:

~~~yaml
registerCode: "0xC"
~~~

## 7. Floating-point, exponent và giá trị đặc biệt

Cả JSON và YAML đều có thể biểu diễn số thực thông thường:

~~~yaml
ratio: 0.75
scientific: 1.25e3
negative: -0.5
~~~

JSON tương ứng:

~~~json
{
  "ratio": 0.75,
  "scientific": 1250.0,
  "negative": -0.5
}
~~~

JSON không có literal chuẩn cho NaN hoặc Infinity. YAML có thể hỗ trợ các scalar đặc biệt như .nan, .inf và -.inf tùy schema/parser:

~~~yaml
notANumber: .nan
positiveInfinity: .inf
negativeInfinity: -.inf
~~~

Những giá trị này không có biểu diễn number tương ứng trong JSON chuẩn. Khi chuyển đổi, cần chọn chính sách rõ ràng: từ chối, chuyển thành string sentinel, hoặc dùng null nếu hợp đồng cho phép. Không nên âm thầm serialize chúng thành JSON number vì JSON không định nghĩa các literal đó.

Nếu một trường là giá trị đo lường hoặc tài chính, cần xác định kiểu Java và precision phù hợp. Jackson có thể bind số vào Integer, Long, BigInteger, Double hoặc BigDecimal tùy kiểu đích và cấu hình. Không để việc implicit resolution của YAML quyết định kiểu Java mà không kiểm thử.

## 8. Date và time: YAML có thể có timestamp tag, JSON chỉ có scalar

JSON không có kiểu date/time riêng. Ngày giờ thường được biểu diễn thành string theo ISO-8601:

~~~json
{
  "date": "2026-11-12",
  "instant": "2026-11-12T10:30:00Z"
}
~~~

YAML có thể viết ngày giờ dưới dạng plain scalar:

~~~yaml
date: 2026-11-12
instant: 2026-11-12T10:30:00Z
~~~

Một số YAML parser/schema, đặc biệt hành vi tương thích YAML 1.1, có thể nhận diện scalar dạng ngày như timestamp thay vì string thông thường. Các parser khác hoặc schema khác có thể để chúng là string. Jackson YAML còn phụ thuộc cách YAML parser phát token và kiểu Java đích được yêu cầu.

Để hợp đồng rõ ràng và tương thích tốt hơn, có thể quote ngày giờ trong YAML:

~~~yaml
businessDate: "2026-11-12"
occurredAt: "2026-11-12T10:30:00Z"
~~~

Sau đó bind vào kiểu Java cụ thể bằng JavaTimeModule:

~~~java
import java.time.Instant;
import java.time.LocalDate;

public record EventConfig(
        LocalDate businessDate,
        Instant occurredAt
) {
}
~~~

~~~java
ObjectMapper mapper = new ObjectMapper(new YAMLFactory())
        .registerModule(new JavaTimeModule());
~~~

Kiểu Java cần phản ánh semantics: LocalDate là ngày không có timezone; Instant là thời điểm tuyệt đối; LocalDateTime không chứa offset/zone. Một string có định dạng ISO không tự mang semantics giống nhau cho mọi kiểu.

## 9. Binary và dữ liệu dạng byte

YAML có tag chuẩn !!binary để biểu diễn dữ liệu nhị phân, thường dùng Base64:

~~~yaml
certificate: !!binary |
  SGVsbG8gSmFja3Nvbg==
~~~

JSON không có kiểu binary. Hợp đồng JSON thường dùng string Base64:

~~~json
{
  "certificate": "SGVsbG8gSmFja3Nvbg=="
}
~~~

Khi bind vào byte[] hoặc kiểu wrapper, cần kiểm tra serializer/deserializer của Jackson và representation thực tế. Không phải mọi YAML tag đều được bảo toàn thành metadata trong object Java. Nếu dữ liệu nhị phân là một phần của API, hãy tài liệu hóa encoding, padding, giới hạn kích thước và xử lý lỗi Base64.

## 10. Explicit YAML tags và kiểu JSON

YAML có thể gắn tag để chỉ định kiểu hoặc cách diễn giải scalar/node. Một số tag chuẩn phổ biến:

| YAML tag | Ý nghĩa | JSON tương ứng |
|---|---|---|
| !!str | String | JSON string |
| !!int | Integer | JSON number nếu nằm trong phạm vi/độ chính xác phù hợp |
| !!float | Floating-point | JSON number nếu hữu hạn |
| !!bool | Boolean | JSON true/false |
| !!null | Null | JSON null |
| !!seq | Sequence | JSON array |
| !!map | Mapping | JSON object khi key phù hợp |
| !!binary | Binary | Thường là Base64 string |
| !!timestamp | Timestamp trong parser/schema hỗ trợ | Thường là ISO string theo contract |

Ví dụ buộc một giá trị nhìn giống số thành string:

~~~yaml
accountCode: !!str 001234
~~~

Hoặc chỉ định integer:

~~~yaml
retryCount: !!int "12"
~~~

JSON không có tag cú pháp tương ứng. Khi chuyển sang JSON, kiểu đã được resolve sẽ được biểu diễn bằng kiểu JSON cơ bản. Nếu ứng dụng cần giữ thông tin kiểu miền nghiệp vụ, hãy dùng field discriminator hoặc schema riêng thay vì trông chờ tag YAML được chuyển nguyên vẹn.

Các tag tùy chỉnh như !Money hoặc !Customer không tự động có kiểu JSON tương ứng. Cần một quy tắc mapping cụ thể ở tầng ứng dụng, custom constructor/deserializer hoặc representation JSON có schema rõ.

## 11. Mapping key: YAML linh hoạt hơn JSON

JSON object bắt buộc key là string:

~~~json
{
  "1": "one",
  "true": "enabled"
}
~~~

YAML mapping có thể dùng scalar key không phải string:

~~~yaml
1: one
true: enabled
null: empty
~~~

YAML còn cho phép key là sequence hoặc mapping trong một số cấu trúc phức tạp:

~~~yaml
? [north, 1]
: primary

? [south, 2]
: secondary
~~~

JSON object không thể giữ nguyên key array như vậy vì key JSON phải là string. Khi chuyển đổi, cần chuẩn hóa key thành string hoặc chuyển cấu trúc thành array các cặp key-value:

~~~json
[
  {
    "key": ["north", 1],
    "value": "primary"
  },
  {
    "key": ["south", 2],
    "value": "secondary"
  }
]
~~~

Với YAML cấu hình ứng dụng, nên dùng key dạng string đơn giản. Nếu key thực sự có kiểu, cần thiết kế representation JSON riêng và không giả định Jackson có thể bind mọi YAML mapping phức tạp vào Map thông thường.

### 11.1. Map key trong Java

Một property Java có thể là:

~~~java
Map<String, Integer> ports;
Map<Integer, String> labels;
Map<UUID, Config> configs;
~~~

Jackson sử dụng key deserializer tương ứng để chuyển field name của mapping sang kiểu key. JSON vẫn ghi tên property dưới dạng string, ngay cả khi key Java là Integer hoặc UUID. Khi đọc YAML, YAML parser và Jackson YAML module phải chuyển mapping key thành token phù hợp cho databinding. Nếu YAML dùng key không phải scalar string, hãy kiểm tra khả năng hỗ trợ của parser và kiểu đích cụ thể.

## 12. Anchor và alias: YAML có tham chiếu, JSON không có cú pháp tương ứng

YAML hỗ trợ anchor (&) và alias (*) để tái sử dụng một node:

~~~yaml
defaults: &defaults
  timeout: 30
  retries: 3

serviceA:
  <<: *defaults
  endpoint: https://a.example.com

serviceB:
  <<: *defaults
  endpoint: https://b.example.com
~~~

Cả serviceA và serviceB dùng lại cấu hình defaults. Cú pháp merge key << được hỗ trợ bởi nhiều parser YAML, nhưng đây là phần mở rộng/cơ chế có lịch sử khác nhau giữa các schema/parser; cần kiểm tra đúng implementation đang dùng.

JSON không có cú pháp anchor/alias. JSON tương ứng thường phải mở rộng dữ liệu:

~~~json
{
  "defaults": {
    "timeout": 30,
    "retries": 3
  },
  "serviceA": {
    "timeout": 30,
    "retries": 3,
    "endpoint": "https://a.example.com"
  },
  "serviceB": {
    "timeout": 30,
    "retries": 3,
    "endpoint": "https://b.example.com"
  }
}
~~~

YAML alias có thể biểu diễn việc nhiều vị trí cùng tham chiếu một node trong cấu trúc YAML representation graph. JSON chỉ có cây giá trị; khi chuyển sang JSON thông thường, dữ liệu được mở rộng thành các nhánh độc lập. Identity dùng chung trong bộ nhớ không được bảo đảm giữ lại.

Không nên nhầm YAML alias với cơ chế polymorphic type ID hoặc object identity của Jackson. Nếu JSON cần biểu diễn quan hệ tham chiếu, hãy dùng ID/link theo hợp đồng riêng.

## 13. Nhiều YAML document trong một stream

YAML hỗ trợ dấu phân cách document:

~~~yaml
---
name: api
port: 8080
---
name: worker
port: 9090
...
~~~

Một YAML stream có thể chứa nhiều document. JSON chuẩn thường biểu diễn một JSON value/document trong một văn bản. Nếu cần nhiều record JSON, hệ thống thường dùng array hoặc một định dạng framing riêng như NDJSON; NDJSON là quy ước dòng, không phải một JSON document duy nhất.

Jackson YAML có thể làm việc với YAML stream thông qua API đọc sequence/iterator phù hợp. Cần chọn API rõ ràng nếu file chứa nhiều document; đừng giả định một lời gọi readValue() sẽ tự trả về toàn bộ stream thành một List theo ý muốn.

## 14. Ví dụ so sánh một cấu hình đầy đủ

YAML:

~~~yaml
application:
  name: "billing-api"
  enabled: true
  retryCount: 3
  maxAmount: 1250.50
  optionalLabel: null
  releaseCode: "0012"
  businessDate: "2026-11-12"
  endpoints:
    - name: public
      url: https://api.example.com
    - name: internal
      url: https://billing.internal
  message: |
    Invoice processing
    is enabled.
~~~

JSON tương ứng:

~~~json
{
  "application": {
    "name": "billing-api",
    "enabled": true,
    "retryCount": 3,
    "maxAmount": 1250.50,
    "optionalLabel": null,
    "releaseCode": "0012",
    "businessDate": "2026-11-12",
    "endpoints": [
      {
        "name": "public",
        "url": "https://api.example.com"
      },
      {
        "name": "internal",
        "url": "https://billing.internal"
      }
    ],
    "message": "Invoice processing\nis enabled.\n"
  }
}
~~~

Ví dụ này cho thấy enabled là boolean vì YAML dùng true không quote; retryCount là integer; maxAmount là number thập phân; optionalLabel là null; releaseCode vẫn là string do được quote; businessDate được quote để parser không tự diễn giải timestamp; endpoints là sequence các mapping; message là string nhiều dòng được tạo từ literal block scalar.

## 15. Đọc YAML và JSON bằng Jackson

Jackson dùng các module data format để hỗ trợ nhiều cú pháp đầu vào. JSON thường dùng ObjectMapper mặc định; YAML dùng YAMLFactory từ artifact jackson-dataformat-yaml.

Maven dependency nên được quản lý cùng phiên bản Jackson bằng BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>VERSION_FROM_PROJECT_BOM</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
~~~

Jackson YAML module dựa trên parser YAML (SnakeYAML trong các bản Jackson YAML 2.x thông dụng). Phiên bản Jackson và parser đi kèm ảnh hưởng đến schema, tag, alias, duplicate key và giới hạn parser. Dùng BOM để tránh trộn phiên bản không tương thích.

### 15.1. Đọc YAML thành POJO

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public record Endpoint(String name, String url) {
}

public record ApplicationConfig(
        String name,
        boolean enabled,
        int retryCount,
        BigDecimal maxAmount,
        String releaseCode,
        LocalDate businessDate,
        List<Endpoint> endpoints,
        String message
) {
}

ObjectMapper yamlMapper = new ObjectMapper(new YAMLFactory())
        .registerModule(new JavaTimeModule());

ApplicationConfig config = yamlMapper.readValue(
        yamlText,
        ApplicationConfig.class
);
~~~

Đoạn code minh họa việc bind YAML vào kiểu Java đã xác định. Trong ứng dụng thực tế, đặt record và import trong các file phù hợp. Jackson sử dụng kiểu đích để chuyển token thành field Java. Nếu YAML chứa string ở vị trí int, kết quả phụ thuộc coercion configuration và kiểu đích. Không nên dựa vào coercion rộng nếu cấu hình là dữ liệu nhạy cảm hoặc cần schema chặt.

### 15.2. Đọc JSON bằng mapper tương ứng

~~~java
ObjectMapper jsonMapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());

ApplicationConfig config = jsonMapper.readValue(
        jsonText,
        ApplicationConfig.class
);
~~~

Cùng DTO có thể được dùng cho cả YAML và JSON nếu hai định dạng cung cấp cùng kiểu dữ liệu logic. Tuy nhiên, cần kiểm thử riêng vì scalar resolution của YAML khác cú pháp JSON.

### 15.3. Chuyển YAML thành JSON

Một cách thực hiện là đọc YAML thành cây JSON của Jackson rồi serialize bằng mapper JSON:

~~~java
JsonNode tree = yamlMapper.readTree(yamlText);
String jsonText = jsonMapper.writeValueAsString(tree);
~~~

Cách này tạo JSON tương ứng với cấu trúc mà YAML parser và Jackson tree model đã hiểu. Nó không bảo toàn nguyên văn YAML: comment, quote style, indentation, anchor/alias, tag và cách viết số có thể mất hoặc được chuẩn hóa.

Nếu cần giữ kiểu Java cụ thể, đọc vào DTO rồi ghi ra JSON:

~~~java
ApplicationConfig config = yamlMapper.readValue(
        yamlText,
        ApplicationConfig.class
);

String jsonText = jsonMapper.writeValueAsString(config);
~~~

Cách DTO giúp xác định kiểu đích và validation rõ hơn. Tuy nhiên, những field không có trong DTO có thể bị bỏ qua hoặc gây lỗi tùy cấu hình; cần chọn unknown-property policy phù hợp.

## 16. Cây YAML và cây JSON trong Jackson

Jackson cung cấp Tree Model với các lớp như JsonNode, ObjectNode và ArrayNode. Dù tên là JsonNode, cây này cũng có thể được tạo từ YAML thông qua YAMLFactory:

~~~java
JsonNode root = yamlMapper.readTree(yamlText);

JsonNode enabled = root.path("application").path("enabled");
JsonNode endpoints = root.path("application").path("endpoints");

boolean isEnabled = enabled.asBoolean();
int endpointCount = endpoints.size();
~~~

Tree Model hữu ích khi cấu trúc input động hoặc cần kiểm tra field trước khi bind vào DTO. Tuy nhiên, JsonNode thể hiện cấu trúc token mà Jackson giữ lại; nó không phải một representation lossless của mọi tính năng YAML.

Ví dụ, YAML comment không trở thành property trong JsonNode. Anchor/alias thường được parser giải quyết trước khi cây được tạo. Tag YAML không nhất thiết được giữ như metadata có thể truy cập qua JsonNode thông thường. Các kiểu đặc biệt có thể được chuẩn hóa hoặc chuyển đổi tùy parser.

Nếu ứng dụng cần bảo toàn comment, tag tùy chỉnh hoặc style YAML để chỉnh sửa file cấu hình rồi ghi lại gần nguyên trạng, JsonNode không phải công cụ round-trip lossless. Cần dùng API YAML representation/model chuyên biệt hoặc lưu source text và chỉnh sửa có kiểm soát.

## 17. Những khác biệt có thể làm thay đổi kiểu Java

Một scalar YAML có thể được parse thành token khác với điều người viết file mong muốn. Bảng dưới đây mô tả các trường hợp cần chú ý; kết quả chính xác phụ thuộc YAML version/schema và cấu hình parser.

| YAML scalar | Ý định thường gặp | Rủi ro | Cách viết rõ |
|---|---|---|---|
| yes / no | String hoặc boolean legacy | YAML 1.1 parser có thể resolve thành boolean | Quote nếu là string; dùng true/false nếu là boolean |
| on / off | String hoặc boolean legacy | Có thể được resolve thành boolean theo schema cũ | Quote nếu là string |
| 0012 | Mã string hoặc số | Có thể bị parse/coerce thành số và mất leading zero | "0012" |
| 0x10 | Mã string hoặc số hex | Có thể thành integer 16 | "0x10" nếu là mã |
| ~ | String ký hiệu hoặc null | Thường resolve thành null | "~" nếu là string |
| (empty scalar) | String rỗng hoặc null | Thường resolve thành null | "" nếu là string rỗng |
| 2026-11-12 | Label string hoặc date | Parser/schema có thể nhận diện timestamp | Quote nếu muốn string |
| .nan / .inf | Chuỗi đặc biệt hoặc số phi hữu hạn | Không có JSON number tương ứng | Quote hoặc từ chối theo contract |
| 1.25e3 | Number | Có thể bind vào kiểu số với precision khác nhau | Chọn BigDecimal/Double rõ ràng |

Khi ứng dụng phụ thuộc vào kiểu, hãy khai báo kiểu Java đích cụ thể và kiểm thử input thực tế. Một giá trị YAML nhìn giống số không nhất thiết nên bind vào Integer; một ngày nhìn giống timestamp không nhất thiết phải trở thành Date; một mã có chữ số không nhất thiết là number.

## 18. Duplicate keys và thứ tự mapping

YAML mapping và JSON object về mặt dữ liệu không nên được xem là danh sách key có thứ tự. Một số parser giữ thứ tự insertion để tiện làm việc, nhưng consumer không nên dựa vào thứ tự key để xác định semantics.

Duplicate key là vấn đề khác: YAML text có thể chứa cùng một key nhiều lần. Parser có thể từ chối duplicate, giữ giá trị sau, hoặc áp dụng behavior tùy cấu hình/phiên bản. JSON cũng có vấn đề tương tự ở mức parser; RFC JSON không khuyến khích tên member trùng và hành vi giữa consumer có thể khác nhau.

Ví dụ YAML:

~~~yaml
port: 8080
port: 9090
~~~

Không nên dùng duplicate key để override cấu hình. Hãy thể hiện override bằng một cấu trúc rõ ràng, nhiều file cấu hình có thứ tự nạp xác định hoặc một bước merge có quy tắc. Với dữ liệu đầu vào quan trọng, cấu hình parser để phát hiện duplicate key nếu thư viện và phiên bản hỗ trợ.

## 19. YAML không phải superset hoàn toàn tương đương với JSON trong mọi ứng dụng

YAML 1.2 được thiết kế để tương thích cú pháp JSON ở mức phù hợp, và JSON document hợp lệ cũng có thể được đọc như YAML theo đặc tả. Nhưng điều đó không có nghĩa mọi tính năng YAML đều có thể chuyển sang JSON mà không mất thông tin.

Các khả năng YAML không có biểu diễn cú pháp tương ứng trong JSON gồm comment, anchor và alias, explicit tag, block scalar style và quote style, mapping key không phải string, nhiều document trong một stream và các scalar được resolve theo schema YAML ngoài tập kiểu JSON.

Khi chuyển YAML sang JSON, ứng dụng thường phải chuẩn hóa những phần này thành cây JSON: mở rộng alias, chuyển key thành string hoặc cấu trúc cặp, chuyển tag thành field/string theo contract, và biến date/binary thành string nếu cần.

## 20. Cẩn trọng với parser và phiên bản YAML

Cùng một file YAML có thể được xử lý khác nhau bởi các parser hoặc phiên bản khác nhau, đặc biệt ở implicit scalar typing, duplicate key, merge key, custom tag và giới hạn alias.

Jackson YAML module sử dụng parser YAML bên dưới; do đó behavior không chỉ phụ thuộc annotation Jackson. Hãy kiểm tra:

- Phiên bản jackson-dataformat-yaml đang dùng.
- Phiên bản SnakeYAML đi kèm hoặc được dependency resolution chọn.
- YAML version/schema mà parser áp dụng.
- Chính sách duplicate key.
- Chính sách alias và giới hạn số alias/depth.
- Custom tag nào được cho phép.
- Coercion của Jackson khi token không khớp kiểu Java.

Không nên nâng riêng SnakeYAML hoặc Jackson YAML module mà không kiểm tra dependency compatibility. Dùng Jackson BOM cho các artifact Jackson và quản lý parser transitive theo hướng dẫn của phiên bản dự án.

## 21. Chọn kiểu Java đích theo ý nghĩa dữ liệu

Khi bind YAML hoặc JSON, kiểu Java đích quyết định cách Jackson diễn giải giá trị. Một số lựa chọn phổ biến:

| Ý nghĩa dữ liệu | Kiểu Java thường phù hợp | YAML rõ ràng | JSON |
|---|---|---|---|
| Mã có leading zero | String | "001234" | "001234" |
| Số đếm trong phạm vi int | int / Integer | 12 | 12 |
| Số nguyên lớn | long / BigInteger | 9000000000 | 9000000000 |
| Giá trị thập phân chính xác | BigDecimal | 1250.50 | 1250.50 |
| Bật/tắt | boolean / Boolean | true | true |
| Giá trị không bắt buộc | Optional<T> hoặc nullable type | null hoặc field thiếu theo contract | null hoặc field thiếu |
| Ngày lịch | LocalDate | "2026-11-12" | "2026-11-12" |
| Thời điểm tuyệt đối | Instant | "2026-11-12T10:30:00Z" | "2026-11-12T10:30:00Z" |
| Danh sách | List<T> | sequence | array |
| Cấu hình key-value | Map<String,T> hoặc DTO | mapping | object |

Đối với tiền hoặc số thập phân cần chính xác, ưu tiên BigDecimal thay vì Double. Đối với mã định danh, ưu tiên String ngay cả khi chỉ gồm chữ số. Đối với ngày giờ, dùng kiểu java.time thể hiện đúng semantics và đăng ký JavaTimeModule khi cần.

## 22. Kiểm thử YAML/JSON parity

Nếu cùng một DTO có thể được nạp từ YAML và JSON, nên kiểm thử rằng hai representation tạo ra cùng giá trị Java.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDate;

import static org.junit.jupiter.api.Assertions.*;

class YamlJsonParityTest {
    record AppConfig(
            String releaseCode,
            boolean enabled,
            int retries,
            BigDecimal limit,
            LocalDate businessDate
    ) {
    }

    private final ObjectMapper yamlMapper = new ObjectMapper(new YAMLFactory())
            .registerModule(new JavaTimeModule());

    private final ObjectMapper jsonMapper = new ObjectMapper()
            .registerModule(new JavaTimeModule());

    @Test
    void yamlAndJsonProduceEquivalentJavaValues() throws Exception {
        String yaml = """
                releaseCode: "0012"
                enabled: true
                retries: 3
                limit: 1250.50
                businessDate: "2026-11-12"
                """;

        String json = """
                {
                  "releaseCode": "0012",
                  "enabled": true,
                  "retries": 3,
                  "limit": 1250.50,
                  "businessDate": "2026-11-12"
                }
                """;

        AppConfig fromYaml = yamlMapper.readValue(yaml, AppConfig.class);
        AppConfig fromJson = jsonMapper.readValue(json, AppConfig.class);

        assertEquals(fromJson, fromYaml);
        assertEquals("0012", fromYaml.releaseCode());
        assertEquals(new BigDecimal("1250.50"), fromYaml.limit());
        assertEquals(LocalDate.parse("2026-11-12"), fromYaml.businessDate());
    }
}
~~~

Test này thể hiện mục tiêu parity: cùng dữ liệu logic phải tạo cùng giá trị Java. Cần bổ sung các trường hợp scalar dễ nhập nhằng như yes/no, leading zero, null, empty string, timestamp và số phi hữu hạn theo schema/parser thực tế của ứng dụng.

Nếu YAML và JSON có quy tắc đầu vào khác nhau có chủ ý, không nhất thiết phải ép chúng giống nhau. Khi đó, hãy tài liệu hóa format riêng và chuyển về một domain model đã chuẩn hóa ở tầng ứng dụng.

## 23. Quy trình chuyển đổi YAML sang JSON an toàn

Khi cần chuyển file YAML thành JSON, có thể làm theo các bước:

1. **Đọc bằng parser YAML phù hợp:** dùng Jackson YAML module hoặc parser YAML đã được chọn cho dự án.
2. **Xác định schema/kiểu đích:** không để scalar implicit typing quyết định ngoài ý muốn.
3. **Quote giá trị string nhập nhằng:** mã, version, ngày dạng label, yes/no, on/off.
4. **Xử lý tag:** chuyển custom tag thành representation JSON có schema rõ hoặc từ chối.
5. **Chuẩn hóa mapping key:** bảo đảm key là string hoặc chuyển sang array các cặp key-value.
6. **Mở rộng alias:** xác định JSON có chấp nhận lặp dữ liệu hay cần ID tham chiếu.
7. **Chọn chính sách multi-document:** chuyển thành array hoặc xử lý từng document riêng.
8. **Bind/validate:** kiểm tra kiểu, range, field bắt buộc và dữ liệu lồng nhau.
9. **Serialize JSON:** dùng ObjectMapper JSON với format number/date đã thống nhất.
10. **Kiểm thử round-trip/parity:** xác nhận giá trị Java và JSON output đúng hợp đồng.

## 24. Chọn cách biểu diễn theo mục tiêu

| Mục tiêu | YAML nên dùng | JSON tương ứng |
|---|---|---|
| Object cấu hình | Mapping block style | Object |
| Danh sách có thứ tự | Sequence với dấu gạch đầu dòng | Array |
| String thông thường | Plain scalar nếu không nhập nhằng | String có quote |
| String có ký tự escape | Double-quoted scalar | String có escape |
| Văn bản nhiều dòng | Literal block scalar | String có newline escape |
| Đoạn văn tự động gộp dòng | Folded block scalar | String đã gộp |
| Integer/decimal | Scalar số rõ ràng | JSON number |
| Boolean | true/false | true/false |
| Null | null hoặc dạng null được schema hỗ trợ | null |
| Mã có số 0 đầu | Quoted string | JSON string |
| Ngày giờ | Quoted ISO-8601 string khi muốn tránh implicit timestamp | JSON string |
| Binary | !!binary/Base64 nếu parser hỗ trợ | Base64 string |
| Dữ liệu dùng chung | Anchor/alias nếu công cụ hỗ trợ | Expand value hoặc dùng ID/link |
| Key phức tạp | Mapping key có kiểu | Array các object key/value hoặc chuẩn hóa thành string |

## 25. Kết luận

YAML và JSON có thể biểu diễn cùng các cấu trúc dữ liệu cơ bản: mapping tương ứng object, sequence tương ứng array và scalar tương ứng string, number, boolean hoặc null. Khác biệt lớn nằm ở cách viết và cách parser xác định kiểu scalar. YAML có plain scalar, nhiều kiểu quote, block string, tag, anchor/alias, mapping key linh hoạt và có thể chứa nhiều document; JSON có cú pháp chặt, key object luôn là string và chỉ có một tập kiểu dữ liệu cơ bản. Những giá trị như yes/no, on/off, leading zero, null shorthand, date-like scalar, hexadecimal hoặc NaN/Infinity có thể được diễn giải khác nhau tùy YAML version/schema/parser và không phải tất cả đều có JSON equivalent trực tiếp.

Khi dùng Jackson YAML, hãy quản lý phiên bản jackson-dataformat-yaml và parser đi kèm, chọn kiểu Java đích rõ ràng, quote các scalar nhập nhằng và kiểm thử trên đúng runtime. Nếu cần chuyển YAML thành JSON, hãy xem đó là quá trình chuẩn hóa cây dữ liệu: tag, alias, key phức tạp, binary và multi-document cần được chuyển thành representation JSON có hợp đồng cụ thể. Điều này giúp cùng một cấu hình tạo ra giá trị Java dự đoán được và tránh lỗi do implicit typing hoặc mất thông tin khi đổi định dạng.

