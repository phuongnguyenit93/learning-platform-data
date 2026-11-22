# Kiểu số, độ chính xác tiền tệ và giới hạn khi dùng JSON

Trong hệ thống NoSQL, dữ liệu thường được trao đổi dưới dạng JSON hoặc lưu bằng các định dạng gần với JSON. Điều này khiến việc biểu diễn số có vẻ rất đơn giản:

~~~json
{
  "productId": "P-1001",
  "price": 199000,
  "quantity": 2,
  "discountRate": 0.15
}
~~~

Nhưng **một số trong JSON chưa nói rõ đó là số nguyên 32 bit, số nguyên 64 bit, số thực nhị phân hay số thập phân chính xác**. Hệ thống nhận JSON có thể đọc giá trị bằng một kiểu số khác hệ thống gửi. Với dữ liệu đo lường, sai số nhỏ đôi khi chấp nhận được; với số tiền, số dư, khoản thuế hoặc số lượng đã thanh toán, sai một đơn vị nhỏ nhất cũng có thể gây lỗi đối soát.

Bài học này giải thích cách lựa chọn và kiểm soát **kiểu số trong NoSQL**, đặc biệt khi dữ liệu đi qua JSON, JavaScript, Java và một số DBMS như MongoDB. Trọng tâm là:

1. Phân biệt **giá trị số theo nghiệp vụ**, **cách mã hóa bằng JSON** và **kiểu số thật trong bộ nhớ/DBMS**.
2. Hiểu giới hạn của `Number` và biểu diễn dấu phẩy động theo chuẩn IEEE 754.
3. Chọn cách biểu diễn **tiền tệ chính xác** bằng số nguyên đơn vị nhỏ nhất hoặc decimal có độ chính xác thích hợp.
4. Thiết kế schema, API, phép tính, làm tròn và migration để không tự đánh mất chữ số.
5. Nhận diện những trường hợp JSON **không thể mang đầy đủ thông tin kiểu số** nếu không có một hợp đồng bổ sung.

Không có một kiểu dữ liệu tốt nhất cho mọi loại số. **Số lượng hàng, mã định danh, tỉ lệ chiết khấu, tiền thanh toán, nhiệt độ và số đo khoa học** có những yêu cầu khác nhau. Việc thiết kế schema phải bắt đầu từ ý nghĩa và miền giá trị của chúng.

## 1. Ba tầng phải phân biệt khi xử lý số

Một số tiền đi từ giao diện đến database thường trải qua nhiều tầng:

~~~text
Nghiệp vụ
  "19,99 USD" (giá trị tiền, đơn vị tiền, quy tắc làm tròn)
       │
       ▼
Hợp đồng API / JSON
  {"amountMinor":1999,"currency":"USD"}
       │
       ▼
Ngôn ngữ lập trình
  Java: long / BigDecimal
  JavaScript: Number / BigInt / decimal library
       │
       ▼
DBMS NoSQL
  BSON Int64 / Decimal128 / Double ...
  hoặc kiểu Number riêng của một hệ quản trị khác
       │
       ▼
Trả kết quả qua JSON cho client khác
~~~

Mỗi tầng có những câu hỏi khác nhau:

| Tầng | Câu hỏi quan trọng |
| --- | --- |
| **Nghiệp vụ** | Giá trị là số lượng, số đo, tỉ lệ hay tiền? Có được âm? Độ chính xác cần bao nhiêu? |
| **Hợp đồng dữ liệu** | `1999` nghĩa là 1.999 đơn vị lớn hay 1.999 đơn vị nhỏ? Đơn vị tiền tệ là gì? |
| **JSON** | Giá trị biểu diễn là number hay string? Có metadata để khôi phục kiểu không? |
| **Ngôn ngữ** | Parser dùng số thực nhị phân, số nguyên có giới hạn hay decimal? |
| **DBMS** | Số được lưu bằng kiểu gì? Index, so sánh, phép cộng/trừ dùng kiểu nào? |
| **Liên thông** | Khi đọc/ghi lại qua một dịch vụ khác, có bị làm tròn hoặc đổi kiểu không? |

**Một tài liệu JSON hợp lệ không đồng nghĩa dữ liệu tiền tệ chính xác.** Dữ liệu đúng phải giữ nguyên ý nghĩa từ đầu đến cuối, kể cả qua bước serialization và deserialization.

### Ví dụ về mất nghĩa dù không mất chữ số

~~~json
{"amount": 5000}
~~~

Giá trị trên có thể nghĩa là:

- 5.000 VND.
- 50,00 USD nếu quy ước là cent.
- 5.000 USD nếu quy ước là dollar.
- 5.000 điểm thưởng, không phải tiền.

Vì vậy **kiểu số không thay thế schema nghiệp vụ**. Tên trường, currency, đơn vị và quy tắc scale là một phần của hợp đồng dữ liệu.

## 2. JSON number biểu diễn điều gì?

Theo cú pháp JSON, number là một chuỗi ký tự số có thể gồm dấu trừ, phần nguyên, phần thập phân và số mũ:

~~~json
{
  "count": 42,
  "debt": -125,
  "ratio": 0.125,
  "small": 1.5e-6,
  "large": 1.25E+20
}
~~~

**JSON không có các từ khóa kiểu số riêng** như `int32`, `int64`, `float32`, `double`, `BigDecimal` hay `Decimal128`. Trong JSON chuẩn, `42` và `42.0` là hai cách viết number; việc parser gán kiểu nội bộ nào tùy môi trường và thư viện.

Một số quy tắc cú pháp đáng nhớ:

| Ví dụ | JSON number hợp lệ? | Lý do |
| --- | --- | --- |
| `0`, `-12` | Có | Số nguyên dạng JSON |
| `12.50` | Có | Có phần thập phân |
| `1.2e3` | Có | Có số mũ |
| `01` | Không | JSON không cho số 0 đầu trong phần nguyên không phải 0 |
| `+5` | Không | JSON number không có dấu cộng đứng đầu |
| `.5` | Không | Phải viết `0.5` |
| `5.` | Không | Phải có chữ số sau dấu chấm |
| `NaN`, `Infinity` | Không | Không thuộc tập token number hợp lệ trong JSON |
| `"19.99"` | Không phải number | Đây là **string** hợp lệ chứa ký tự biểu diễn số |

Một JSON number có thể mang nhiều chữ số như:

~~~json
{"transactionId": 9007199254740993}
~~~

Cú pháp này hợp lệ, nhưng **không phải mọi chương trình đọc được số nguyên đó một cách chính xác**. Độ chính xác thuộc về cách parser và kiểu số đích, chứ không được JSON bảo đảm chỉ bằng cú pháp.

### Ngữ nghĩa number không được xác định bằng dấu chấm

Không nên dùng quy tắc “có dấu chấm thì là decimal chính xác, không có dấu chấm thì là integer 64 bit”. Parser JavaScript dùng cùng kiểu `Number` cho cả `19` và `19.99`. Một hệ khác có thể phân biệt số nguyên và số thực khi parse, hoặc cấu hình parser để tạo `BigDecimal`.

Ngay cả số `1e3` có thể mang giá trị toán học 1000 nhưng không nói rằng sender muốn một `long`, `double` hay `Decimal128`. Nếu nghiệp vụ yêu cầu một kiểu cụ thể, hợp đồng dữ liệu phải quy định cách đọc.

## 3. Vì sao số dấu phẩy động nhị phân gây vấn đề?

Nhiều môi trường lập trình sử dụng kiểu dấu phẩy động theo chuẩn **IEEE 754 binary64**, thường gọi là `double`. JavaScript `Number` về cơ bản là kiểu số này.

Binary64 dùng một số bit hữu hạn để biểu diễn các giá trị theo **cơ số 2**. Nó biểu diễn chính xác nhiều số nguyên trong miền nhất định và những phân số có mẫu số là lũy thừa của 2, chẳng hạn `0.5` hoặc `0.125`. Nhưng các phân số thập phân quen thuộc như `0.1` hay `0.2` thường **không thể biểu diễn chính xác bằng một số bit nhị phân hữu hạn**.

Ví dụ JavaScript:

~~~javascript
console.log(0.1 + 0.2);
// 0.30000000000000004

console.log((0.1 + 0.2) === 0.3);
// false
~~~

Hiện tượng này không phải lỗi riêng của JSON hay MongoDB. Nó xảy ra **ngay trong phép tính trên kiểu số binary64**. JSON có thể truyền `0.1` dưới dạng ký tự ngắn, nhưng khi một parser chuyển sang binary64, giá trị trong bộ nhớ là một số nhị phân gần nhất trong phạm vi có thể biểu diễn.

### Một sai lầm phổ biến trong tính tiền

~~~javascript
const unitPrice = 0.1;
const quantity = 3;
const total = unitPrice * quantity;

console.log(total);
// Có thể hiển thị 0.30000000000000004
~~~

Nếu hệ thống làm tròn hoặc so sánh số tiền qua nhiều bước, những sai lệch kiểu này có thể dẫn đến kết quả không khớp nhau giữa dịch vụ, đặc biệt khi áp dụng thuế, chiết khấu hoặc phân bổ tiền.

**Không giải quyết bằng cách chỉ ẩn số lẻ khi hiển thị.** Gọi `toFixed(2)` cho một giá trị hiển thị đẹp không khôi phục được quy tắc tính toán ở các bước trước, và còn trả về **string**, không phải một kiểu decimal chính xác cho phép tiếp tục tính tùy ý.

## 4. Giới hạn số nguyên chính xác của JavaScript Number

Binary64 có **53 bit độ chính xác của phần định trị**. Trong JavaScript, miền các số nguyên **an toàn** để phân biệt và thực hiện các thao tác số nguyên thông thường là:

\[
-(2^{53}-1)\ \leq n\ \leq\ 2^{53}-1
\]

Giới hạn dương là:

~~~javascript
console.log(Number.MAX_SAFE_INTEGER);
// 9007199254740991

console.log(Number.isSafeInteger(9007199254740991));
// true
~~~

Một số nguyên lớn hơn vẫn có thể được biểu diễn như một `Number`, nhưng **không còn bảo đảm mỗi số nguyên liền kề là một giá trị phân biệt**.

~~~javascript
console.log(9007199254740992 === 9007199254740993);
// true — hai literal không còn phân biệt được bằng Number
~~~

Đặc biệt nguy hiểm khi parse JSON:

~~~javascript
const doc = JSON.parse(
  '{"amountMinor":9007199254740993}'
);

console.log(doc.amountMinor);
// 9007199254740992
~~~

JSON đầu vào có một số nguyên lớn chính xác dưới dạng ký tự, nhưng **sau khi chuyển thành JavaScript Number**, giá trị đã bị làm tròn. Nếu ứng dụng serialize lại, ghi vào DBMS hoặc dùng làm ID, chữ số gốc có thể mất vĩnh viễn.

### BigInt không tự giải quyết JSON

JavaScript có kiểu `BigInt` để làm việc với số nguyên lớn:

~~~javascript
const amount = BigInt("9007199254740993");

console.log(amount + 1n);
// 9007199254740994n
~~~

Nhưng JSON chuẩn **không có literal BigInt**. Ví dụ:

~~~javascript
JSON.stringify({ amountMinor: 9007199254740993n });
// TypeError: Do not know how to serialize a BigInt
~~~

Một API thường phải **chuyển BigInt thành string** hoặc dùng serializer có hợp đồng rõ, chẳng hạn:

~~~javascript
const payload = JSON.stringify({
  amountMinor: amount.toString(),
  currency: "USD"
});

// {"amountMinor":"9007199254740993","currency":"USD"}
~~~

Client nhận phải parse `amountMinor` theo kiểu số nguyên lớn hoặc decimal tương ứng, **không được gọi `Number(...)` một cách mù quáng**.

### ID số lớn và số tiền có cùng nguy cơ ở tầng JSON

Mã giao dịch `9007199254740993` có thể là **định danh**, không phải giá trị cần cộng trừ. Dù vậy, nếu gửi nó dưới dạng JSON number và JavaScript làm tròn, hai ID khác nhau có thể trở nên giống nhau. Vì vậy, với ID dài, một **string** thường thích hợp hơn number, ngay cả khi ID chỉ gồm chữ số.

## 5. Kiểu số trong NoSQL không giống nhau giữa các hệ

“NoSQL” là một nhóm kiến trúc rộng. Mỗi DBMS cung cấp kiểu số, phép toán và giới hạn riêng. Không nên thấy cú pháp giống JSON mà kết luận mọi hệ đều lưu giá trị dưới cùng một kiểu.

| Hệ/định dạng | Kiểu hoặc cách biểu diễn liên quan | Điểm cần lưu ý |
| --- | --- | --- |
| **JSON chuẩn** | Number không có nhãn kiểu int64/decimal | Parser quyết định kiểu số trong ứng dụng |
| **JavaScript** | `Number` (binary64), `BigInt` | Number có giới hạn số nguyên an toàn; BigInt không serialize trực tiếp bằng JSON |
| **Java** | `int`, `long`, `float`, `double`, `BigInteger`, `BigDecimal` | Phải chọn kiểu và kiểm soát chuyển đổi trong serializer/deserializer |
| **MongoDB BSON** | Int32, Int64, Double, Decimal128 và các kiểu khác | BSON có thông tin kiểu số mà JSON thường không biểu diễn trực tiếp |
| **Amazon DynamoDB** | Thuộc tính kiểu Number `N`; API thể hiện trị số thành string trong cấu trúc AttributeValue | Phải phân biệt string dùng để mã hóa một thuộc tính số với string nghiệp vụ |
| **Redis** | Các giá trị có thể là string và các lệnh số học theo kiểu/giới hạn Redis | Cần xem từng lệnh, không suy luận decimal tiền tệ tự động |

### MongoDB: BSON có kiểu số cụ thể

MongoDB dùng **BSON**, không lưu tất cả giá trị như chuỗi JSON thuần túy. Một số kiểu quan trọng:

- **Int32:** số nguyên có dấu 32 bit.
- **Int64 / Long:** số nguyên có dấu 64 bit.
- **Double:** số dấu phẩy động nhị phân.
- **Decimal128:** số thập phân theo định dạng decimal128 với **tối đa 34 chữ số thập phân có nghĩa** theo giới hạn của định dạng.

Điều này rất quan trọng khi lưu số tiền. `Decimal128` có thể biểu diễn chính xác nhiều giá trị thập phân như `19.99` trong giới hạn của nó; `Double` có thể lưu giá trị xấp xỉ nhị phân.

Tuy nhiên, **Decimal128 không phải số thập phân vô hạn độ chính xác**. Nó vẫn có giới hạn chữ số và miền số mũ; các phép tính phải xem quy tắc làm tròn, tràn/thiếu phạm vi và cách driver thao tác với giá trị.

Ví dụ ở `mongosh`:

~~~javascript
db.payments.insertOne({
  paymentId: "PAY-001",
  amountDecimal: NumberDecimal("19.99"),
  amountMinor: NumberLong("1999"),
  currency: "USD"
});
~~~

Ở đây `amountDecimal` và `amountMinor` là **hai cách biểu diễn cùng số tiền** cho mục đích minh họa; trong hệ thống thật nên chọn **một dạng có thẩm quyền** để tránh chênh lệch giữa các trường.

Các hàm `NumberDecimal` và `NumberLong` là cách làm việc trong `mongosh` với những kiểu BSON tương ứng, **không phải cú pháp JSON chuẩn**. Không thể gửi nguyên văn `NumberDecimal("19.99")` trong một payload JSON thông thường rồi mong parser JSON tự hiểu.

### MongoDB Extended JSON giữ được thông tin kiểu

Để đưa kiểu BSON qua môi trường JSON, MongoDB có **Extended JSON**, gồm các biểu diễn có nhãn kiểu. Ví dụ:

~~~json
{
  "paymentId": "PAY-001",
  "amountDecimal": {
    "$numberDecimal": "19.99"
  },
  "amountMinor": {
    "$numberLong": "1999"
  },
  "currency": "USD"
}
~~~

Ở biểu diễn này, dấu `$numberDecimal` và `$numberLong` giúp một parser **hiểu Extended JSON** khôi phục kiểu BSON. Nhưng với một client chỉ dùng `JSON.parse` thông thường, hai trường đó đơn giản là **object có khóa bắt đầu bằng dấu `$`**, không tự trở thành đối tượng decimal hay Int64.

Vì vậy phải thống nhất **API dùng business JSON hay MongoDB Extended JSON**. Không nên gửi Extended JSON ngầm định cho mọi khách hàng chỉ vì backend lưu BSON.

### DynamoDB: string trong wire format có thể đại diện cho Number

Trong API mức thấp của DynamoDB, một thuộc tính số có thể xuất hiện ở dạng:

~~~json
{
  "amount": {
    "N": "19.99"
  },
  "currency": {
    "S": "USD"
  }
}
~~~

Ở đây `"N"` báo **kiểu Number của DynamoDB**, còn `"19.99"` là chuỗi dùng để truyền trị số theo hợp đồng API của DynamoDB. Điều đó **khác** với việc tạo một thuộc tính DynamoDB kiểu String mang nội dung `"19.99"`.

Các SDK có lớp ánh xạ để chuyển đổi giữa kiểu của ngôn ngữ và kiểu DynamoDB; cần kiểm tra cách xử lý số lớn/decimal cụ thể. Không nên mặc định rằng JavaScript Number có thể nhận mọi giá trị số DynamoDB mà không mất chữ số.

## 6. Những cách biểu diễn tiền tệ được dùng phổ biến

**Tiền tệ** không chỉ có một số. Một giá trị tiền đầy đủ thường có:

- **Số lượng** (*amount*).
- **Loại tiền** (*currency*), ví dụ `VND`, `USD`, `JPY`.
- **Đơn vị và scale** của amount.
- **Quy tắc làm tròn**, thường gắn với loại phép tính và chính sách nghiệp vụ.

Ba cách biểu diễn thường gặp:

| Cách biểu diễn | Ví dụ 19,99 USD | Điểm mạnh | Rủi ro/đánh đổi |
| --- | --- | --- | --- |
| **Integer minor units** | `amountMinor: 1999`, `currency: "USD"` | Chính xác với số đơn vị nhỏ nhất đã chọn; cộng trừ số nguyên dễ kiểm soát | Cần biết scale, kiểm tra overflow, phân bổ/làm tròn khi nhân chia |
| **Decimal chính xác** | `Decimal128("19.99")` hoặc Java `BigDecimal("19.99")` | Thuận tiện cho tỉ lệ, thuế và giá trị có số lẻ theo thập phân | Cần giới hạn precision/scale, chọn rounding và quản lý kiểu xuyên các tầng |
| **String thập phân trong JSON** | `"amount": "19.99"`, `"currency": "USD"` | Truyền chính xác chuỗi chữ số qua các parser JSON | Phải parse/validate và chuyển sang decimal; sort chuỗi không phải sort số |

Không nên chọn `Double`/JavaScript `Number` làm dạng tính toán **có thẩm quyền** cho tiền chỉ vì việc parse JSON hoặc gọi MongoDB dễ thực hiện. Có những ứng dụng hiển thị số tiền xấp xỉ, nhưng nghiệp vụ thu–chi, thanh toán và đối soát thường cần mô hình chính xác rõ ràng.

### Mô hình A — Integer minor units

Đối với USD, ta có thể thống nhất **1 USD = 100 cent** và lưu:

~~~json
{
  "orderId": "O-1001",
  "totalMinor": 1999,
  "currency": "USD"
}
~~~

Ở đây `totalMinor = 1999` nghĩa là **1.999 cent = 19,99 USD**.

Ưu điểm:

- `1999 + 250` là số nguyên chính xác nếu nằm trong miền kiểu số đã chọn.
- So sánh, cộng/trừ tổng số tiền không cần số thực nhị phân.
- Mô hình lưu JSON rất rõ khi đặt tên trường `*Minor` hoặc có metadata `unit`.

Nhưng **integer minor units không giải quyết mọi bài toán**:

- Phải biết chính xác **currency** và số đơn vị nhỏ nhất theo hợp đồng.
- Giá đơn vị, thuế hoặc tỷ giá có thể cần độ chính xác **nhỏ hơn đơn vị thanh toán cuối cùng** trước khi làm tròn.
- Với số tiền rất lớn, `Number` JavaScript hoặc `int32` có thể không đủ.
- Tính trung bình, phân bổ chiết khấu và nhân tỉ lệ tạo ra phân số cần quy tắc làm tròn.

### Không mặc định mọi currency có hai chữ số thập phân

Các loại tiền có quy ước đơn vị nhỏ nhất khác nhau. Trong nhiều hệ thanh toán:

| Currency | Ví dụ về đơn vị nhỏ nhất thông dụng | Hệ số minh họa |
| --- | --- | --- |
| USD | 1 USD = 100 cent | 100 |
| VND | Thường biểu diễn số tiền giao dịch bằng đơn vị đồng nguyên, không có phần thập phân | 1 |
| JPY | Thường biểu diễn tiền bằng yen nguyên | 1 |
| KWD | Có đơn vị nhỏ đến phần nghìn theo quy ước tiền tệ | 1000 |

Các ví dụ nhằm làm rõ **không có một scale = 2 áp dụng cho tất cả tiền tệ**. Quy định về đơn vị tiền, mạng thanh toán và chính sách nghiệp vụ có thể khác nhau hoặc thay đổi. Trong hệ thật, cần dùng bảng định nghĩa currency/scale được quản lý và version hóa khi cần, thay vì tự suy ra từ việc tên mã gồm ba chữ cái.

Ví dụ cùng number `1999`:

~~~text
USD với scale=2: 19.99 USD
VND với scale=0: 1999 VND
KWD với scale=3: 1.999 KWD
~~~

**Không bao giờ chuyển trực tiếp hai số amountMinor của hai currency khác nhau bằng phép cộng.** Kể cả khi cùng scale, 19,99 USD và 19,99 EUR không phải cùng một giá trị tiền.

### Mô hình B — Decimal theo đơn vị tiền lớn

Ví dụ một document lưu `Decimal128`:

~~~javascript
db.products.insertOne({
  sku: "P-1001",
  currency: "USD",
  unitPrice: NumberDecimal("19.99")
});
~~~

Decimal phù hợp với tính toán cần giữ chữ số thập phân có nghĩa, miễn các hệ liên quan đều sử dụng kiểu decimal tương ứng và quy tắc scale/rounding nhất quán.

Nếu đưa tài liệu ra JSON API thông thường, nên có một hợp đồng rõ, ví dụ:

~~~json
{
  "sku": "P-1001",
  "unitPrice": "19.99",
  "currency": "USD"
}
~~~

Trong trường hợp này `unitPrice` là **string chứa số thập phân**, không phải string tùy ý. Phải validate nó theo quy tắc cú pháp và miền hợp lệ rồi parse bằng kiểu decimal chính xác trong ứng dụng.

## 7. Giá hiển thị, giá đơn vị tính toán và số tiền thanh toán

Một sai lầm khác là buộc **mọi trường số liên quan tới tiền** có cùng scale và cách làm tròn.

Ví dụ hệ thống bán nhiên liệu hoặc dịch vụ có giá theo lượng sử dụng:

~~~text
Đơn giá:       0.0375 USD / đơn vị
Số lượng:      125 đơn vị
Thành tiền:    4.6875 USD trước làm tròn
Tiền thu:      4.69 USD nếu quy tắc là làm tròn hai chữ số
~~~

Nếu lưu giá đơn vị bằng **cent nguyên** ngay từ đầu, `0.0375 USD` sẽ bị làm tròn thành 0.04 USD hoặc 0.03 USD. Việc làm tròn quá sớm có thể tạo sai lệch lớn khi nhân với số lượng.

Một thiết kế hợp lý có thể phân biệt:

1. **Unit price ở độ chính xác tính toán**: decimal với scale phù hợp hoặc một đơn vị đo nhỏ hơn.
2. **Quantity**: integer nếu đếm vật, decimal nếu đo khối lượng, thể tích hoặc thời lượng.
3. **Unrounded amount**: kết quả tính toán trước khi làm tròn.
4. **Rounded payable amount**: số tiền thực sự được tính vào hóa đơn/thanh toán, ở đơn vị tiền hợp lệ.
5. **Rounding adjustment**: phần chênh lệch cần ghi để đối soát nếu quy tắc yêu cầu.

Vì vậy, quy tắc “tiền luôn lưu bằng cents” hữu ích cho **số tiền đã chốt theo minor units**, nhưng không phải lúc nào cũng đủ để lưu **đơn giá hoặc phép tính trung gian** có độ chính xác lớn hơn.

### Ví dụ hợp đồng cho một dòng hóa đơn

~~~json
{
  "lineId": "L-001",
  "sku": "SERVICE-01",
  "quantity": "125",
  "unitPrice": "0.0375",
  "currency": "USD",
  "lineAmountBeforeRounding": "4.6875",
  "lineAmountMinor": 469,
  "roundingMode": "HALF_UP"
}
~~~

Đây là **mô hình minh họa**, không phải mẫu hóa đơn chuẩn. Những trường dạng string phải được parse thành decimal, và thời điểm làm tròn có thể khác tùy quy định thuế, hợp đồng hoặc hệ thanh toán. Nếu hệ thống chỉ cần lưu số tiền cuối cùng, có thể không cần lưu mọi bước trung gian; nhưng nếu cần kiểm toán hoặc tính lại, cần đủ dữ liệu và **phiên bản quy tắc**.

## 8. Làm tròn là quy tắc nghiệp vụ, không phải chi tiết hiển thị

Phép nhân/chia trên decimal có thể tạo nhiều chữ số thập phân hơn số được phép thanh toán. Khi đó phải chọn:

- **Scale đầu ra**: số chữ số sau dấu chấm hoặc đơn vị làm tròn.
- **Rounding mode**: cách xử lý phần dư.
- **Thời điểm làm tròn**: theo từng dòng, từng khoản thuế, từng giao dịch hay tổng hóa đơn.
- **Cách xử lý số âm**: quan trọng với refund, điều chỉnh và phí hoàn.

Một số chế độ làm tròn thường gặp:

| Chế độ | Ý nghĩa khái quát | Ví dụ dương ở nửa đơn vị |
| --- | --- | --- |
| `HALF_UP` | Làm tròn về phía lớn hơn về độ lớn khi đúng giữa hai giá trị | `1.005 → 1.01` ở 2 chữ số |
| `HALF_EVEN` | Khi đúng giữa, chọn chữ số cuối chẵn | `1.005 → 1.00`, `1.015 → 1.02` |
| `DOWN` | Bỏ phần lẻ về phía 0 | `1.019 → 1.01` |
| `UP` | Làm tròn ra xa 0 nếu có phần lẻ | `1.011 → 1.02` |
| `CEILING` | Làm tròn về phía dương vô cực | `-1.011 → -1.01` |
| `FLOOR` | Làm tròn về phía âm vô cực | `-1.011 → -1.02` |

Những ví dụ ở bảng giả định làm tròn đến **hai chữ số thập phân** và phép toán decimal chính xác. Một hệ có thể dùng những quy tắc khác hoặc quy tắc cụ thể của từng loại tiền/tax; phải thống nhất và ghi vào hợp đồng nghiệp vụ.

### Làm tròn từng dòng và làm tròn tổng có thể cho kết quả khác

Giả sử ba dòng, mỗi dòng có số tiền trước làm tròn là `0.335 USD`.

**Cách A — làm tròn từng dòng theo HALF_UP:**

~~~text
round(0.335, 2) = 0.34
round(0.335, 2) = 0.34
round(0.335, 2) = 0.34
Tổng = 1.02 USD
~~~

**Cách B — cộng trước, làm tròn sau:**

~~~text
0.335 + 0.335 + 0.335 = 1.005
round(1.005, 2) = 1.01 USD
~~~

Chênh lệch **0.01 USD** không phải do JSON, mà vì **quy tắc thứ tự làm tròn**. Hệ thống hóa đơn và thanh toán phải chọn chính sách phù hợp rồi sử dụng nhất quán ở frontend, backend, báo cáo và đối soát.

### Chia tiền thành nhiều phần

Ví dụ có `1001 cent` cần chia đều cho ba người:

~~~text
1001 / 3 = 333 cent dư 2 cent

Một cách chia có tổng bảo toàn:
  A nhận 334 cent
  B nhận 334 cent
  C nhận 333 cent
  Tổng = 1001 cent
~~~

Không thể chỉ làm tròn cả ba phần đều thành 334 cent, vì tổng sẽ là 1002 cent. Cần quy tắc **phân bổ phần dư** xác định và có thể tái lập, ví dụ ưu tiên theo thứ tự ID ổn định hoặc theo quy định nghiệp vụ.

**Bất biến có thể kiểm tra:**

\[
\sum_{i=1}^{n} allocatedMinor_i = totalMinor
\]

Đây là lý do dùng integer minor units cho các khoản đã chốt thường hữu ích: tổng phân bổ được kiểm tra chính xác bằng số nguyên mà không cần so sánh số thực gần đúng.

## 9. Java BigDecimal: một cách xử lý decimal chính xác

Trong Java, `BigDecimal` phù hợp với nhiều phép tính tiền đòi hỏi decimal chính xác. Nhưng phải **khởi tạo đúng cách**.

### Tránh tạo BigDecimal trực tiếp từ double

~~~java
import java.math.BigDecimal;

BigDecimal wrong = new BigDecimal(0.1);
BigDecimal correct = new BigDecimal("0.1");

System.out.println(wrong);
// Có thể thấy một chuỗi thập phân dài phản ánh xấp xỉ nhị phân của 0.1.

System.out.println(correct);
// 0.1
~~~

`new BigDecimal(0.1)` nhận **giá trị double đã xấp xỉ** trước đó; nó không thể biết ý định của lập trình viên là đúng `0.1` thập phân. Cách dùng string hoặc parse trực tiếp từ token thập phân giúp tránh bước mất chính xác ban đầu.

`BigDecimal.valueOf(0.1)` trong Java thường cho kết quả thập phân trực quan dựa trên biểu diễn chuỗi chuẩn của double, nhưng nếu double đã mất những chữ số quan trọng ở bước trước, `valueOf` **không phục hồi được dữ liệu gốc**. Với nguồn tiền, tốt nhất là không đi qua double ngay từ đầu.

### Tính tổng và làm tròn

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalMoneyExample {
    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.99");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal gross = unitPrice.multiply(quantity);

        BigDecimal discountRate = new BigDecimal("0.15");
        BigDecimal discount = gross.multiply(discountRate);
        BigDecimal payable = gross.subtract(discount)
                .setScale(2, RoundingMode.HALF_UP);

        System.out.println(gross);     // 59.97
        System.out.println(discount);  // 8.9955
        System.out.println(payable);   // 50.97
    }
}
~~~

Ví dụ cố ý giữ chiết khấu ở độ chính xác trung gian, rồi làm tròn số tiền cuối. Nếu chính sách nghiệp vụ yêu cầu làm tròn tiền chiết khấu từng dòng trước, công thức phải được thay đổi tương ứng.

### Phép chia cần quy tắc làm tròn

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");

BigDecimal result = one.divide(three, 2, RoundingMode.HALF_EVEN);
System.out.println(result); // 0.33
~~~

`1 / 3` không có biểu diễn thập phân hữu hạn. Nếu yêu cầu `BigDecimal.divide` cho kết quả chính xác vô hạn mà không chỉ định cách xử lý, phép chia có thể ném ngoại lệ. Với tiền, cần chọn precision/scale và rounding mode theo nghĩa nghiệp vụ.

### Đừng nhầm equals với so sánh giá trị

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));     // false
System.out.println(a.compareTo(b));  // 0
~~~

`BigDecimal.equals` xét cả scale, còn `compareTo` so sánh giá trị số. Trong logic “hai khoản tiền có cùng giá trị không?”, cách so sánh phải phù hợp, đồng thời **không quên currency**. Hai BigDecimal bằng nhau không có nghĩa 100 USD bằng 100 EUR.

## 10. Chuyển BigDecimal thành integer minor units an toàn

Giả sử API nhận `"19.99"` USD và doanh nghiệp đã xác định scale lưu trữ là 2.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MinorUnitConversion {
    public static long toMinorUnitsExact(
            String amountMajor,
            int scale
    ) {
        BigDecimal amount = new BigDecimal(amountMajor);

        // Không âm thầm làm tròn nếu đầu vào có độ chính xác ngoài hợp đồng.
        BigDecimal normalized = amount.setScale(
                scale,
                RoundingMode.UNNECESSARY
        );

        return normalized.movePointRight(scale).longValueExact();
    }

    public static void main(String[] args) {
        System.out.println(toMinorUnitsExact("19.99", 2)); // 1999
        System.out.println(toMinorUnitsExact("1500", 0));  // 1500

        // toMinorUnitsExact("19.999", 2) sẽ báo lỗi:
        // không được bí mật làm tròn thành 20.00.
    }
}
~~~

Đây là một **bộ chuyển đổi có chủ đích không làm tròn**. Nếu hệ thống thực sự cho phép số tiền đầu vào có nhiều chữ số hơn và cần làm tròn, hãy xử lý làm tròn ở một bước nghiệp vụ **rõ ràng trước khi chuyển đổi**.

`longValueExact()` giúp phát hiện không thể biểu diễn giá trị nguyên bằng Java `long`. Không dùng `longValue()` cho tiền nếu việc cắt phần lẻ hoặc overflow không được phép.

### Kiểm soát overflow cả khi đã dùng integer

Java `long` có giới hạn:

\[
-2^{63} \leq n \leq 2^{63}-1
\]

Vì vậy, cộng các khoản tiền lớn hoặc nhân số lượng có thể overflow:

~~~java
long totalMinor = Math.addExact(8_000L, 3_000L);
long lineMinor = Math.multiplyExact(1_999L, 3L);
~~~

Các hàm `Math.addExact` và `Math.multiplyExact` ném ngoại lệ khi kết quả không nằm trong miền `long`; điều này an toàn hơn việc để một phép toán tràn âm thầm. Nếu miền dữ liệu thực sự vượt quá `long`, cần `BigInteger`, một kiểu decimal hoặc thiết kế độ lớn/scale khác.

## 11. JavaScript: kiểm tra dữ liệu số trước khi gửi sang NoSQL

Trong JavaScript, nếu đã chọn **integer minor units dưới dạng JSON number**, phải kiểm tra **safe integer**:

~~~javascript
function assertSafeMinorUnits(amountMinor) {
  if (!Number.isSafeInteger(amountMinor)) {
    throw new Error("amountMinor must be a safe integer");
  }
  if (amountMinor < 0) {
    throw new Error("amountMinor must not be negative");
  }
}

assertSafeMinorUnits(1999); // hợp lệ
assertSafeMinorUnits(19.99); // lỗi: không phải số nguyên
assertSafeMinorUnits(Number.MAX_SAFE_INTEGER + 1); // lỗi
~~~

Đoạn này phục vụ trường hợp **khoản tiền không âm**, ví dụ giá bán. Với số dư, hoàn tiền hoặc bút toán điều chỉnh có thể âm, không được áp dụng điều kiện `amountMinor >= 0` một cách mù quáng; phải thiết kế dấu và loại giao dịch riêng.

### Cẩn thận với việc nhân số nguyên

Hai toán hạng đều là safe integer **không bảo đảm tích của chúng vẫn an toàn**:

~~~javascript
const unitMinor = 9007199254740000;
const quantity = 10;

console.log(Number.isSafeInteger(unitMinor)); // true
console.log(Number.isSafeInteger(quantity));  // true

const totalMinor = unitMinor * quantity;
console.log(Number.isSafeInteger(totalMinor)); // false
~~~

Phải kiểm tra **kết quả của phép cộng/nhân** hoặc dùng số nguyên lớn. Không chỉ validate từng trường đầu vào rồi cho rằng tổng luôn đúng.

### Parse chuỗi số lớn theo kiểu phù hợp

~~~javascript
function parseUnsignedMinorString(raw) {
  if (typeof raw !== "string" || !/^(0|[1-9][0-9]*)$/.test(raw)) {
    throw new Error("Invalid nonnegative integer string");
  }
  return BigInt(raw);
}

const amountMinor = parseUnsignedMinorString("9007199254740993");
console.log(amountMinor + 2n); // 9007199254740995n
~~~

Ví dụ này chỉ cho số nguyên **không âm**, và `BigInt` không có phần thập phân. Khi cần phép chia có kết quả lẻ hoặc tiền nhiều loại, phải xác định rounding/scale; `BigInt` không tự đóng vai trò decimal.

### Cách lưu String không được làm mất khả năng tính

Một JSON API:

~~~json
{
  "amountMinor": "9007199254740993",
  "currency": "USD"
}
~~~

được chọn để bảo toàn chữ số qua parser; nhưng ứng dụng không được làm:

~~~javascript
const amount = Number(payload.amountMinor);
// Giá trị có thể mất chính xác.
~~~

Thay vào đó, parse qua `BigInt` hoặc kiểu decimal/số nguyên lớn tương ứng rồi validate miền giá trị. Nếu dữ liệu được lưu vào một cột/thuộc tính **string** trong DBMS, sắp xếp theo từ điển không phải sắp xếp số:

~~~text
Lexicographic string order:
  "100" < "20"

Numeric order:
  20 < 100
~~~

Vì vậy không thể tự coi “lưu số thành string” là giải pháp toàn diện. Phải cân nhắc **yêu cầu query/index/tính tổng** cùng với bảo toàn độ chính xác.

## 12. Số không hợp lệ và những hành vi JSON dễ gây bất ngờ

Trong ngôn ngữ JavaScript có các giá trị số `NaN` và `Infinity`, nhưng JSON chuẩn **không có literal tương ứng**.

~~~javascript
const raw = {
  ratio: NaN,
  overflow: Infinity
};

console.log(JSON.stringify(raw));
// {"ratio":null,"overflow":null}
~~~

Nếu ứng dụng không kiểm tra trước khi serialize, một kết quả phép tính sai có thể âm thầm biến thành `null` trong JSON, làm cho downstream hiểu nó như “chưa có dữ liệu” thay vì “phép tính không hợp lệ”.

Do đó cần:

~~~javascript
function assertFiniteNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error("Expected a finite number");
  }
}
~~~

Một JSON number có số mũ lớn cũng có thể dẫn đến giá trị không hữu hạn trong một parser dùng binary64:

~~~javascript
const doc = JSON.parse('{"magnitude":1e309}');
console.log(doc.magnitude); // Infinity trong JavaScript
~~~

Đây là ví dụ cho thấy **cú pháp JSON hợp lệ chưa bảo đảm miền giá trị hợp lệ trong ứng dụng**. Cần validation sau parsing và giới hạn numeric range phù hợp trước khi lưu.

### Phân biệt 0, null và trường bị thiếu

~~~json
{"amountMinor": 0}
~~~

khác với:

~~~json
{"amountMinor": null}
~~~

và khác với:

~~~json
{}
~~~

Ví dụ:

- `0` có thể là số tiền hợp lệ, như đơn hàng miễn phí.
- `null` có thể có nghĩa chưa tính được số tiền, nếu hợp đồng cho phép.
- Trường bị thiếu có thể là lỗi dữ liệu hoặc tài liệu schema cũ.

Không nên tự đổi tất cả thành 0 bằng một giá trị mặc định nếu hệ thống cần phân biệt **miễn phí**, **chưa biết giá** và **dữ liệu bị lỗi**.

### Số âm và âm 0

JSON cho phép cách viết `-0`. Trong JavaScript, `-0 === 0` là `true`, mặc dù một số phép toán có thể phân biệt dấu của zero. Với money, nên chuẩn hóa giá trị zero theo hợp đồng để tránh payload có nhiều biểu diễn không cần thiết.

Với hoàn tiền, số âm có thể mang ý nghĩa rõ; nhưng một số thiết kế chọn lưu `amountMinor` luôn không âm kèm `transactionType` (DEBIT/CREDIT/REFUND) để tránh nhầm dấu. Không có một quy tắc chung áp dụng cho mọi ledger; điều quan trọng là **không cho âm tùy tiện ở trường vốn chỉ cho giá bán dương**.

## 13. Thiết kế JSON Schema cho số tiền

JSON Schema cho phép kiểm tra **hình dạng payload**: kiểu, trường bắt buộc, khoảng giá trị, pattern, enum, v.v. Nhưng schema cần phù hợp với miền biểu diễn mà các hệ thống thực sự hỗ trợ.

### Trường hợp A — integer minor units an toàn cho JavaScript

Ví dụ một API chỉ phục vụ USD và các khoản giá bán không âm, giới hạn amount trong miền safe integer:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UsdPrice",
  "type": "object",
  "required": ["amountMinor", "currency"],
  "additionalProperties": false,
  "properties": {
    "amountMinor": {
      "type": "integer",
      "minimum": 0,
      "maximum": 9007199254740991
    },
    "currency": {
      "const": "USD"
    }
  }
}
~~~

Đây là một **hợp đồng API minh họa**, không phải giới hạn bắt buộc của mọi DBMS. Trường `maximum` được chọn vì client JavaScript Number có thể biểu diễn an toàn mọi số nguyên trong miền này.

Những vấn đề vẫn cần xử lý ngoài JSON Schema:

- Kiểu số lưu trong DBMS có tương ứng với miền đã công bố không?
- Tổng sau phép nhân/cộng có vượt giới hạn không?
- Không ai được gửi một số nguyên đã mất chữ số **trước khi JSON Schema được kiểm tra**.
- Đơn vị `amountMinor` được hiểu là cent vì currency cố định là USD theo hợp đồng.

**Cẩn thận:** nếu một parser đã làm tròn một JSON number lớn rồi mới đưa đến validator, validator **không thể khôi phục token số nguyên gốc** chỉ từ giá trị đã làm tròn. Khi yêu cầu bảo toàn số lớn, cần cơ chế parse lossless hoặc dùng string trong hợp đồng.

### Trường hợp B — decimal string có cú pháp kiểm soát

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UsdPriceDecimalString",
  "type": "object",
  "required": ["amount", "currency"],
  "additionalProperties": false,
  "properties": {
    "amount": {
      "type": "string",
      "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]{1,2})?$"
    },
    "currency": {
      "const": "USD"
    }
  }
}
~~~

Pattern này cho phép chuỗi như `"0"`, `"19.9"`, `"19.99"` và không cho giá trị âm, dấu cộng hoặc quá hai chữ số thập phân. Nó **chỉ kiểm soát cú pháp**, chưa kiểm soát giá trị cực đại và những quy tắc nghiệp vụ khác. Muốn biết `"9999999999999999999999.99"` có được phép không, ứng dụng phải parse bằng decimal rồi kiểm tra giới hạn.

Nếu hỗ trợ nhiều currency, phải xác định **scale phù hợp cho từng currency** và những quy tắc cụ thể khi giá trị không có cùng số chữ số thập phân. Không nên gắn mặc định toàn cục `multipleOf: 0.01` với mọi số tiền.

### `number`, `integer` và `multipleOf` có đủ để bảo đảm tiền chính xác?

JSON Schema phân biệt kiểu `number` và `integer` theo ngữ nghĩa JSON Schema, nhưng:

- Nó không quyết định kiểu bộ nhớ của mọi parser.
- Một validator dùng dấu phẩy động có thể gặp khó khăn khi xử lý một số giá trị thập phân hoặc `multipleOf` nếu không dùng thuật toán số thích hợp.
- Nó không định nghĩa cách tính thuế, làm tròn, quy đổi currency hoặc idempotency.
- Nó không cứu dữ liệu đã bị làm tròn trước lúc validate.

Vì vậy nên kết hợp schema với **quy tắc parsing và tính toán ở tầng ứng dụng** và kiểu lưu DBMS phù hợp.

## 14. Mô hình một tài liệu giao dịch tiền tệ

Giả sử hệ thống thanh toán cần lưu khoản tiền cuối cùng đã được chốt, không cần lưu đơn giá có scale sâu hơn. Một biểu diễn JSON có thể là:

~~~json
{
  "paymentId": "PAY-1001",
  "schemaVersion": 2,
  "currency": "USD",
  "amountMinor": 5097,
  "status": "CAPTURED",
  "createdAt": "2026-11-14T08:00:00Z"
}
~~~

Hợp đồng nghiệp vụ:

~~~text
paymentId:
  Định danh thanh toán ổn định, không dùng floating-point.

currency:
  Mã tiền tệ trong danh mục được hệ thống hỗ trợ.

amountMinor:
  Số tiền đã chốt trong đơn vị nhỏ nhất được quy định cho currency.
  Không âm với một payment capture thông thường.
  Không phải "dollar", cũng không phải số thực nhị phân.

schemaVersion:
  Phiên bản hợp đồng dữ liệu để phân biệt cách diễn giải trường.
~~~

### Khi tiền liên quan đến hai currency

Không nên dùng:

~~~json
{
  "total": 100,
  "sourceCurrency": "USD",
  "targetCurrency": "VND"
}
~~~

vì `total` đang biểu diễn số tiền **trước hay sau chuyển đổi**? Tỷ giá nào, tại thời điểm nào, làm tròn ra sao?

Có thể cần một biểu diễn rõ hơn:

~~~json
{
  "conversionId": "FX-1001",
  "source": {
    "amountMinor": 10000,
    "currency": "USD"
  },
  "target": {
    "amountMinor": 2500000,
    "currency": "VND"
  },
  "rate": "25000",
  "rateDirection": "VND_PER_USD",
  "rateCapturedAt": "2026-11-14T08:00:00Z",
  "roundingPolicy": "SETTLEMENT_V1"
}
~~~

Ví dụ này giả định **100,00 USD = 2.500.000 VND** với tỷ giá minh họa 25.000 VND/USD; **không phải tỷ giá thị trường hiện tại**. Thực tế còn có spread, phí, quy định settlement, ngày tỷ giá và độ chính xác của giá trị rate.

Mục đích là chứng minh **currency conversion là một phép tính có dữ liệu nguồn và quy tắc**, không phải thao tác đổi tên currency trên một con số.

### Không nhầm với decimal của hệ thống đo lường

Một tài liệu cảm biến:

~~~json
{
  "deviceId": "D-17",
  "temperatureC": 28.4375,
  "confidence": 0.998
}
~~~

có thể chấp nhận binary64 trong một số ứng dụng nếu sai số đo và phép tính được kiểm soát theo domain. Tính toán nhiệt độ có sai số phép đo vốn dĩ khác yêu cầu **thu đúng 19,99 USD**. Việc bắt mọi số đo vào Decimal128 cũng không nhất thiết đem lại lợi ích tương xứng.

## 15. Chọn kiểu và index theo đường truy cập

Trong NoSQL, việc chọn kiểu lưu ảnh hưởng đến **so sánh, sắp xếp, index và aggregate**:

| Kiểu lưu | Truy vấn số học | Sắp xếp/điều kiện range | Ghi chú |
| --- | --- | --- | --- |
| BSON Int64 | Có hỗ trợ số nguyên theo ngữ nghĩa DBMS | Theo giá trị số | Cần driver giữ đúng int64 |
| BSON Decimal128 | Có các phép tính decimal theo khả năng DBMS | Theo giá trị số | Cần kiểm soát precision/rounding |
| BSON Double | Có phép tính số thực | Theo giá trị số xấp xỉ | Có nguy cơ biểu diễn tiền thập phân không chính xác |
| String chứa chữ số | Cần parse/chuyển kiểu để làm phép tính số | Mặc định thường theo chuỗi, không theo trị số | Bảo toàn chữ số, nhưng không tự có semantics số |
| DynamoDB Number | Có semantics thuộc tính số theo DBMS | Theo khả năng điều kiện/index của DynamoDB | API dùng chuỗi cho trị số trong AttributeValue |

Ví dụ nếu một collection MongoDB có:

~~~json
{"price": "100"}
{"price": "20"}
{"price": "9"}
~~~

thì sort theo `price` kiểu string không tương đương với sort số `9, 20, 100`. Việc bổ sung `priceNumber` để tra cứu có thể hữu ích trong một số hệ thống, nhưng sẽ tạo **hai biểu diễn** cần được duy trì nhất quán. Khi có thể, nên chọn **kiểu số thích hợp trong DBMS** và giữ định dạng JSON API rõ ràng, thay vì chỉ dựa vào string mọi nơi.

### Cẩn thận khi cùng trường có nhiều kiểu

Giả sử dữ liệu cũ:

~~~text
price = "199.00"       (string)
price = 199.00         (double)
price = Decimal128     (decimal)
~~~

Một bộ lọc hoặc index trên `price` sẽ có hành vi phụ thuộc quy tắc so sánh kiểu của DBMS. Không nên tin kết quả đúng khi cùng field chứa string, double và decimal lẫn lộn. Với MongoDB, BSON có quy tắc thứ tự và so sánh kiểu; dữ liệu số có thể được so sánh khác dữ liệu string. Hệ thống cần **làm sạch và thống nhất kiểu**, không chỉ thêm index.

Một câu truy vấn phục vụ kiểm tra có thể là:

~~~javascript
db.products.find({
  price: { $type: "string" }
});

db.products.find({
  price: { $type: "double" }
});

db.products.find({
  price: { $type: "decimal" }
});
~~~

Các lệnh chỉ minh họa **cách nhận diện kiểu trường trong MongoDB**, không phải một migration tự động. Trước khi chuyển, phải xác định giá trị nguồn còn đủ chính xác không.

## 16. Thao tác đồng thời với tiền: độ chính xác chưa đủ

Lưu tiền bằng integer minor units hoặc Decimal128 **không tự động bảo vệ bất biến số dư khi nhiều request đồng thời**.

Ví dụ một ví có `balanceMinor = 1000` cent. Hai request cùng muốn trừ 700 cent:

~~~text
Client A đọc 1000 cent → đủ
Client B đọc 1000 cent → đủ

A ghi số dư 300.
B ghi số dư 300.

Cả A và B đều báo đã trừ 700, dù số dư cuối chỉ trừ 700.
~~~

Đây là **lost update**. Kiểu integer chính xác không giải quyết cuộc đua giữa kiểm tra và ghi.

Một hướng thiết kế trong MongoDB là **điều kiện và cập nhật trong một lệnh trên một document**, ví dụ với số tiền trong miền số có thể biểu diễn:

~~~javascript
const debitMinor = 700;

const result = db.wallets.updateOne(
  {
    _id: "W-1001",
    balanceMinor: { $gte: debitMinor }
  },
  {
    $inc: { balanceMinor: -debitMinor }
  }
);

if (result.matchedCount !== 1) {
  // Không đủ số dư, ví không tồn tại hoặc điều kiện không khớp.
}
~~~

Đây là **mẫu ý tưởng**, không phải hệ thống ví điện tử hoàn chỉnh. Cần xác định rõ kiểu `balanceMinor`, xử lý dấu, quyền, phạm vi giao dịch, idempotency, bút toán đối ứng, audit và xử lý timeout. Nếu ứng dụng dùng JavaScript Number cho `debitMinor`, phải đảm bảo nó là safe integer.

**Phân biệt hai lớp tính đúng đắn:**

1. **Độ chính xác số học:** cộng/trừ không tạo sai lệch chữ số.
2. **Tính nguyên tử và ràng buộc nghiệp vụ:** các phép cập nhật đồng thời không phá số dư, không xử lý trùng và giữ ledger nhất quán.

Một hệ tài chính cần cả hai; chỉ chọn Decimal128 mà không thiết kế transaction và kiểm toán là chưa đủ.

## 17. JSON truyền giữa nhiều ngôn ngữ: hợp đồng nào an toàn?

Giả sử backend Java lưu khoản tiền trong `BigDecimal` hoặc `long`, còn frontend JavaScript nhận qua HTTP JSON. Những lựa chọn:

### Phương án 1 — JSON number là integer minor units có giới hạn

~~~json
{
  "amountMinor": 1999,
  "currency": "USD"
}
~~~

**Có thể dùng khi:** miền giá trị đã giới hạn trong safe integer của JavaScript, mọi phía hiểu scale và các phép tính không vượt miền. Ưu điểm: API đơn giản, dễ làm việc với number.

**Không phù hợp khi:** có số nguyên lớn hơn safe integer hoặc một client có thể parse thành kiểu số hẹp hơn mà không kiểm soát.

### Phương án 2 — JSON string là integer minor units

~~~json
{
  "amountMinor": "9007199254740993",
  "currency": "USD"
}
~~~

**Có thể dùng khi:** cần giữ nguyên một số nguyên lớn qua nhiều parser. Các phía phải parse bằng `BigInteger`/`BigInt` hoặc kiểu số nguyên lớn phù hợp, validate định dạng và quản lý sort/index trong DBMS.

### Phương án 3 — JSON string là decimal major units

~~~json
{
  "amount": "19.99",
  "currency": "USD"
}
~~~

**Có thể dùng khi:** cần hỗ trợ decimal chính xác, đặc biệt với đơn giá và phép tính trung gian. Các phía parse bằng decimal library, xác định precision/scale và chính sách làm tròn trước khi lưu hoặc chuyển sang minor units.

### Phương án 4 — JSON có nhãn kiểu, như Extended JSON

~~~json
{
  "amount": {
    "$numberDecimal": "19.99"
  },
  "currency": "USD"
}
~~~

**Có thể dùng khi:** hợp đồng tích hợp cụ thể hiểu Extended JSON và muốn giữ kiểu BSON. Không phù hợp nếu consumer tưởng đây là business JSON thông thường và không có parser chuyên biệt.

**Không tồn tại một “định dạng JSON số tiền chuẩn duy nhất” cho mọi ứng dụng.** Hãy chọn một biểu diễn có quy tắc rõ và bảo đảm tất cả ngôn ngữ/driver giữ được ý nghĩa tương ứng.

## 18. Migration từ số thực sang decimal hoặc minor units

Giả sử hệ thống cũ lưu:

~~~json
{
  "orderId": "O-1001",
  "currency": "USD",
  "total": 19.99
}
~~~

trong một field `total` đã được parse và lưu bằng binary64. Sau một thời gian, hệ thống muốn chuyển sang:

~~~json
{
  "orderId": "O-1001",
  "schemaVersion": 2,
  "currency": "USD",
  "totalMinor": 1999
}
~~~

Không được cho rằng chỉ cần nhân mọi giá trị `total` cũ với 100 rồi ép kiểu nguyên là **luôn khôi phục chính xác dữ liệu ban đầu**. Với những giá trị đã trải qua phép tính dấu phẩy động, làm tròn có thể sai; có thể còn lỗi từ quy tắc tính giá, thuế hoặc tỷ giá cũ.

### Câu hỏi phải giải quyết trước khi chuyển

1. **Nguồn gốc giá trị cũ:** nó được nhập từ chuỗi thập phân, tính từ nhiều phép float hay đã được làm tròn một lần?
2. **Đơn vị tiền tệ và scale:** có biết chắc currency của từng bản ghi?
3. **Dải giá trị:** có khoản nào vượt miền số nguyên đích không?
4. **Cách làm tròn cũ:** có tồn tại hợp đồng hoặc phiên bản thuật toán không?
5. **Tài liệu bất thường:** null, missing, string, NaN sau chuyển đổi, giá trị âm, currency không được hỗ trợ.
6. **Tác động lên consumer:** API, báo cáo, search index, cache, job nhập/xuất.
7. **Bằng chứng đối soát:** có thể so với hóa đơn gốc, cổng thanh toán hoặc ledger không?

### Chuyển đổi có kiểm soát

Một quy trình:

~~~text
1. Đo số bản ghi theo kiểu dữ liệu và schema version.
2. Định nghĩa biểu diễn đích, scale, rounding, giới hạn.
3. Triển khai reader hiểu được cả v1 và v2.
4. Writer mới chỉ tạo dữ liệu v2.
5. Backfill từng batch, có ID và checkpoint.
6. Với bản ghi cũ:
     - Ưu tiên nguồn thập phân/ledger đáng tin cậy nếu còn.
     - Nếu chỉ có double, áp dụng chính sách chuyển được phê duyệt.
     - Từ chối/cách ly bản ghi không xác định chính xác.
7. Đối chiếu theo từng giao dịch và tổng báo cáo.
8. Chuyển toàn bộ consumer sang v2 khi an toàn.
9. Gỡ hỗ trợ v1 sau khi xác minh hoàn thành.
~~~

### Không tự “làm tròn rồi cho qua” dữ liệu lịch sử

Nếu một giá trị đã được làm tròn thành `9007199254740992` trước khi lưu nhưng token gốc là `9007199254740993`, **không thuật toán chuyển kiểu nào suy ra chắc chắn token gốc chỉ từ số đã làm tròn**.

Tương tự, nếu giá sản phẩm được tính sai do float ở nhiều bước và tổng thanh toán đã được chốt theo một thuật toán cũ, migration không thể tùy ý đổi tổng thanh toán rồi coi là đúng. Cần **nguồn dữ liệu có thẩm quyền, chính sách sửa sai và audit trail**.

## 19. Một số anti-pattern khi dùng JSON và NoSQL

| Anti-pattern | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Dùng `double` cho số tiền cần đối soát chính xác | Sai số biểu diễn nhị phân | Integer minor units hoặc decimal phù hợp |
| Lưu `amount: 1999` nhưng không ghi scale | Không biết là 19,99 USD hay 1.999 USD | `amountMinor` + currency hoặc metadata scale |
| Mặc định mọi currency có 2 chữ số thập phân | Sai với VND, JPY, KWD và các quy tắc khác | Bảng currency/scale do hệ thống quản lý |
| Gửi int64 lớn trong JSON number cho JavaScript | Vượt safe integer, mất chữ số | String hoặc parser lossless có hợp đồng |
| Dùng `BigInt` rồi `JSON.stringify` trực tiếp | Serialization ném lỗi | Encode thành string/định dạng đã thống nhất |
| Coi chuỗi `"19.99"` là số trong DBMS | Sort/index có thể theo từ điển | Parse và lưu kiểu numeric phù hợp |
| Tạo `BigDecimal` từ double đã bị làm tròn | Không phục hồi giá trị thập phân gốc | Parse từ chuỗi/token decimal |
| Chỉ `toFixed(2)` trước hiển thị | Chỉ giải quyết hình thức, không xử lý tính đúng của các bước trước | Quy tắc tính toán/rounding nhất quán |
| Làm tròn quá sớm | Tổng hóa đơn lệch | Chọn đúng độ chính xác trung gian và thời điểm rounding |
| Cộng tiền khác currency | Tổng số không có nghĩa | Quy đổi có rate, direction, policy và thời điểm |
| Không kiểm tra overflow | Tổng hoặc tích số nguyên bị sai | Kiểu đủ lớn, phép toán exact, giới hạn miền |
| Cho cả string/double/decimal lẫn trong cùng field | Query/index/aggregate khó dự đoán | Validation, migration và schema version |
| Dùng `null` cho lỗi NaN/Infinity | Che giấu phép tính lỗi | Kiểm tra giá trị hữu hạn trước khi serialize |
| Tin rằng Decimal128 tự chống concurrent writes | Có thể lost update dù độ chính xác số học tốt | Atomic conditional update/transaction |
| Ghi đồng thời total decimal và total minor không đồng bộ | Hai nguồn số tiền có thể lệch | Chọn một nguồn chính, tính derived value có quy tắc |

## 20. Kiểm thử các trường hợp biên về số và tiền

Kiểm thử không nên chỉ có giá sản phẩm thông thường như 10 hoặc 100. Các trường hợp cần chú ý:

### 20.1. Kiểm thử serialization round-trip

Nếu hợp đồng dùng string số nguyên lớn:

~~~text
Đầu vào: "9007199254740993"
  → Parse BigInt/BigInteger
  → Lưu kiểu thích hợp
  → Đọc ra
  → Serialize thành JSON string
Đầu ra phải: "9007199254740993"
~~~

Nếu đầu ra là `"9007199254740992"`, một bước đã làm tròn mất chữ số.

### 20.2. Kiểm thử cộng/trừ và phân bổ

Ví dụ:

~~~text
Input:
  totalMinor = 1001
  recipients = 3

Output:
  allocations = [334, 334, 333]

Assertions:
  allocations đều là integer không âm
  sum(allocations) = totalMinor
  max(allocations) - min(allocations) <= 1
~~~

Với số tiền âm hoặc nhiều loại khoản phí, phải sửa điều kiện theo quy tắc nghiệp vụ; bài thử trên chỉ cho trường hợp chia đều một tổng **không âm**.

### 20.3. Kiểm thử làm tròn

Nên có bảng ca được nghiệp vụ phê duyệt:

| Đầu vào thập phân | Scale đích | Rounding mode | Kỳ vọng |
| --- | ---: | --- | --- |
| `1.005` | 2 | HALF_UP | `1.01` |
| `1.005` | 2 | HALF_EVEN | `1.00` |
| `1.015` | 2 | HALF_EVEN | `1.02` |
| `-1.005` | 2 | HALF_UP | `-1.01` |
| `100.000` | 2 | UNNECESSARY | `100.00` |
| `19.999` | 2 | UNNECESSARY | Báo lỗi vì cần làm tròn |

Các kết quả trên giả định đầu vào đã được parse bằng **decimal chính xác**, không qua double.

### 20.4. Kiểm thử miền giá trị

- Giá trị bằng 0, số tiền tối thiểu và tối đa hợp lệ.
- Số âm ở trường không cho phép âm.
- Số lượng thập phân ở trường đòi hỏi số nguyên.
- Số nguyên sát giới hạn `Number.MAX_SAFE_INTEGER`.
- Giá trị vượt `long` hoặc giới hạn decimal lưu trữ.
- Chuỗi có dấu cách, ký tự phân tách hàng nghìn, dấu phẩy địa phương hoặc số mũ ngoài hợp đồng.
- `null`, trường thiếu, sai kiểu.
- Chuỗi biểu diễn số rất dài gây chi phí parse/bộ nhớ cao.
- Currency sai hoặc không được hỗ trợ.
- Hai client đồng thời ghi cùng số dư/đơn hàng.
- Request bị gửi lại sau timeout.

Những bài thử này giúp phát hiện cả **mất chữ số**, **nhầm đơn vị** và **vi phạm cập nhật đồng thời**.

## 21. Bài tập thực hành

### Bài 1 — Nhận diện mất chính xác qua JSON

Một API trả:

~~~json
{"ledgerEntryId": 9007199254740993}
~~~

Frontend JavaScript dùng `JSON.parse` rồi gửi lại ID đó cho backend. Hãy giải thích nguy cơ và đề xuất một biểu diễn JSON khác có thể giữ nguyên ID.

**Gợi ý:** JavaScript Number không phân biệt mọi số nguyên lớn hơn `2^53 - 1`. ID dài nên được gửi dưới dạng string và không chuyển qua `Number`.

### Bài 2 — Đổi đơn vị tiền

Cho ba bản ghi:

~~~json
{"amountMinor":1999,"currency":"USD"}
{"amountMinor":1999,"currency":"VND"}
{"amountMinor":1999,"currency":"KWD"}
~~~

Giả sử hợp đồng sử dụng scale USD=2, VND=0, KWD=3. Hãy diễn giải số tiền lớn tương ứng và giải thích vì sao không được cộng ba giá trị `amountMinor` để tạo một tổng tiền.

**Gợi ý:** lần lượt là 19,99 USD; 1.999 VND; 1,999 KWD. Khác đơn vị tiền nên tổng không có nghĩa trước khi quy đổi.

### Bài 3 — Java BigDecimal

Vì sao:

~~~java
new BigDecimal(0.1)
~~~

khác với:

~~~java
new BigDecimal("0.1")
~~~

trong bối cảnh tính tiền?

**Gợi ý:** literal `0.1` kiểu double đã bị xấp xỉ nhị phân trước khi truyền vào constructor; chuỗi `"0.1"` giữ đúng các chữ số thập phân được chỉ định.

### Bài 4 — Quy tắc làm tròn

Một hóa đơn có ba dòng giá trước làm tròn mỗi dòng `0.335 USD`. Hãy tính:

1. Tổng nếu làm tròn HALF_UP từng dòng về hai chữ số.
2. Tổng nếu cộng ba dòng trước rồi làm tròn HALF_UP.
3. Chênh lệch và lý do hệ thống cần chọn một quy tắc.

**Gợi ý:** các kết quả là 1,02 USD và 1,01 USD; chênh lệch 0,01 USD.

### Bài 5 — Thiết kế schema cho đơn hàng đa tiền tệ

Một ứng dụng có đơn hàng USD, VND, JPY và KWD. Đề xuất một JSON schema nghiệp vụ phù hợp cho số tiền **đã chốt**. Hãy chỉ ra:

- Cần lưu trường nào để biết currency và đơn vị amount?
- Có nên cho phép `price` kiểu double không?
- Nếu frontend JavaScript phải đọc những khoản vượt safe integer thì payload nên chọn kiểu gì?
- Khi báo cáo tổng nhiều currency, quy đổi cần lưu metadata nào?

**Gợi ý:** một cách là `currency + amountMinor` với quy tắc scale theo currency, dùng string cho số nguyên vượt miền an toàn của JSON parser phổ biến.

### Bài 6 — Kiểu số trong MongoDB

Một collection có trường `amount` lưu lẫn string `"19.99"`, double và Decimal128. Vì sao index hoặc sort trên `amount` không đảm bảo ý nghĩa số đồng nhất? Hãy đề xuất một cách kiểm kê, chuyển đổi và versioning an toàn.

**Gợi ý:** phải phân biệt kiểu dữ liệu hiện có, nguồn đáng tin cậy, quy tắc đổi/rounding, kiểm tra dữ liệu lỗi và khả năng của consumer cũ.

### Bài 7 — Số dư ví điện tử

Một ví lưu số dư bằng integer minor units. Hai request cùng trừ 700 cent từ số dư 1.000 cent. Nếu mỗi request đọc trước rồi cập nhật sau, điều gì có thể xảy ra? Kiểu integer đã đủ để tránh lỗi chưa?

**Gợi ý:** integer giúp độ chính xác số học nhưng không tự bảo đảm nguyên tử đọc–kiểm tra–ghi. Cần conditional update/transaction và quy tắc idempotency.

### Bài 8 — Phân bổ số tiền

Hãy viết pseudocode chia đều 1.001 cent cho ba người sao cho:

- Mọi phần là số nguyên cent.
- Không ai nhận số âm.
- Các phần chênh nhau tối đa 1 cent.
- Tổng đúng 1.001 cent.

**Gợi ý:** chia lấy phần nguyên và phân bổ phần dư theo một thứ tự ổn định.

## 22. Mẫu đặc tả số tiền để thống nhất giữa các dịch vụ

Một nhóm phát triển có thể ghi hợp đồng dữ liệu như sau:

~~~yaml
field: totalMinor
businessMeaning: "Final charged amount"
currencyField: currency
amountUnit: "Currency-specific minor unit"
minorScaleSource: "Versioned supported-currency configuration"
jsonRepresentation:
  type: string
  reason: "Preserve all integer digits across JSON consumers"
internalRepresentation:
  java: "BigInteger or bounded long after range check"
  javascript: "BigInt after strict string validation"
databaseRepresentation:
  mongodb: "BSON Int64 when within range, or another approved exact numeric representation"
constraints:
  - "Integer amount"
  - "Nonnegative for capture operations"
  - "Currency must be supported"
  - "No implicit binary floating-point conversion"
arithmetic:
  - "Overflow checked"
  - "No addition across different currencies"
rounding:
  input: "Defined by pricing/settlement business rule"
  finalAmount: "Already quantized to the selected minor unit"
schemaVersion: 2
verification:
  - "Round-trip exactness"
  - "Currency scale cases"
  - "Maximum amount and overflow"
  - "Idempotency and concurrent updates"
~~~

Đây là **mẫu đặc tả minh họa**, không phải cấu hình của MongoDB hay JSON Schema tự thực thi. Những hệ không cần amount lớn có thể chọn JSON number với giới hạn safe integer; những hệ cần decimal có thể dùng decimal string với kiểu decimal tương ứng trong backend. Điểm cốt lõi là **quyết định phải minh bạch và nhất quán qua mọi tầng**.

## 23. Ghi nhớ

Khi thiết kế kiểu số và schema trong NoSQL, cần phân biệt ba khía cạnh:

**Thứ nhất — kiểu số là một cam kết về biểu diễn.** JSON number không mang nhãn int64 hay decimal chính xác. Khi parse sang JavaScript Number, số nguyên lớn có thể mất chữ số và số thập phân như 0.1 có thể bị xấp xỉ nhị phân. MongoDB BSON, Java BigDecimal hoặc các kiểu số khác có khả năng riêng nhưng không tự được giữ nguyên qua một payload JSON tùy ý.

**Thứ hai — tiền tệ cần đơn vị và quy tắc nghiệp vụ.** Có thể dùng **integer minor units** cho số tiền đã chốt hoặc **decimal chính xác** cho phép tính có nhiều chữ số thập phân. Phải lưu currency, chọn scale thích hợp, kiểm soát overflow và xác định thời điểm/kiểu làm tròn. Không mặc định mọi loại tiền có hai chữ số thập phân.

**Thứ ba — tính chính xác phải được bảo vệ xuyên suốt.** Một kiểu số chính xác trong DBMS sẽ không giúp ích nếu API parse thành Number và làm tròn trước khi ghi. Một số tiền chính xác cũng không tự ngăn lost update hoặc xử lý request hai lần. Validation, serialization, lưu trữ, phép tính, transaction, migration, đối soát và kiểm thử phải cùng tuân theo hợp đồng.

**Nguyên tắc thực hành:** với từng trường numeric, hãy viết rõ **ý nghĩa, đơn vị, miền giá trị, precision/scale, kiểu lưu, cách truyền JSON, phép toán và quy tắc làm tròn** trước khi triển khai. Đây là nền tảng để dùng schema NoSQL linh hoạt mà không đánh mất độ chính xác của dữ liệu quan trọng.
