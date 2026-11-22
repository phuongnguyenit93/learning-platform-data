# Độ chính xác số, tiền tệ và chuyển đổi kiểu dữ liệu trong MongoDB

## 1. Vì sao kiểu số có thể làm sai dữ liệu?

MongoDB lưu document dưới dạng BSON (Binary JSON). BSON phân biệt nhiều kiểu số có **độ chính xác, miền giá trị và cách biểu diễn** khác nhau. Việc nhìn thấy cùng một giá trị trên màn hình, chẳng hạn `100`, không có nghĩa các trường đó có cùng kiểu BSON hay phù hợp cho cùng nghiệp vụ.

Với hệ thống lưu giá bán, hóa đơn, thuế, số lượng giao dịch hoặc mã định danh, chọn nhầm kiểu có thể dẫn tới:

- Kết quả cộng, nhân hoặc so sánh bị sai lệch vì làm tròn ở số dấu phẩy động nhị phân.
- Mất chữ số khi số nguyên lớn đi qua JavaScript `Number` hoặc một lớp JSON không giữ được kiểu.
- Dữ liệu đầu vào dạng chuỗi không thể chuyển thành số do sai định dạng, quá miền giá trị hoặc có phần thập phân.
- Các document cùng collection có trường `amount` mang kiểu `double`, `int`, `long` và `decimal` lẫn lộn, gây khó khăn cho ứng dụng, phân tích và kiểm soát dữ liệu.
- Tiền được làm tròn ở sai bước hoặc sai số chữ số thập phân của đồng tiền.

Bài học tập trung vào bốn kiểu số BSON, nguyên tắc biểu diễn tiền tệ và các cách chuyển đổi kiểu **an toàn, có kiểm soát** trong `mongosh`, aggregation pipeline và ứng dụng Java.

Sau bài học, bạn có thể đọc kiểu BSON thật của một trường, chọn kiểu số theo miền giá trị/nghiệp vụ, thực hiện chuyển đổi với `$convert` và `$to...`, xác định chính sách làm tròn, cũng như kiểm tra dữ liệu trước khi chuẩn hóa.

## 2. Phân biệt các kiểu số BSON

| Kiểu BSON | Nhãn thường thấy từ `$type` | Đặc điểm | Trường hợp sử dụng |
|---|---|---|---|
| **Int32** | `int` | Số nguyên có dấu 32 bit, từ `-2,147,483,648` đến `2,147,483,647` | Bộ đếm, số lượng hoặc giá trị nguyên nhỏ |
| **Int64** | `long` | Số nguyên có dấu 64 bit, từ `-9,223,372,036,854,775,808` đến `9,223,372,036,854,775,807` | Bộ đếm lớn, timestamp dạng số, số tiền theo đơn vị nhỏ nhất khi vừa miền |
| **Double** | `double` | Số dấu phẩy động nhị phân IEEE 754, thường có khoảng 15–17 chữ số thập phân có nghĩa | Đo lường, thống kê, dữ liệu khoa học chấp nhận sai số biểu diễn |
| **Decimal128** | `decimal` | Số dấu phẩy động **thập phân** IEEE 754 với tối đa 34 chữ số thập phân có nghĩa | Giá tiền, thuế, tỷ giá, tính toán cần độ chính xác thập phân xác định |

Kích thước phần giá trị BSON lần lượt là 4 byte, 8 byte, 8 byte và 16 byte; một trường BSON còn có chi phí lưu tên trường và metadata đi kèm.

**Độ chính xác và miền giá trị là hai khái niệm khác nhau.** Double biểu diễn được nhiều giá trị có độ lớn rất lớn nhưng không lưu chính xác mọi số thập phân hoặc mọi số nguyên lớn. Int64 giữ nguyên giá trị **nguyên** trong miền 64 bit nhưng không biểu diễn phân số. Decimal128 biểu diễn chính xác nhiều số thập phân, nhưng vẫn có giới hạn 34 chữ số có nghĩa và giới hạn về miền số mũ.

### 2.1. Int32 và Int64: chính xác với số nguyên đúng miền

Trong `mongosh`, có thể dùng constructor BSON rõ ràng:

~~~javascript
NumberInt(100)                 // BSON Int32
NumberLong("100")              // BSON Int64
NumberLong("9007199254740993") // Int64 lớn hơn giới hạn số nguyên an toàn của JS
~~~

Lý do đưa giá trị Int64 lớn vào **chuỗi** là JavaScript `Number` chỉ biểu diễn chính xác mọi số nguyên đến:

~~~javascript
Number.MAX_SAFE_INTEGER; // 9007199254740991 = 2^53 - 1
~~~

Nếu viết literal `9007199254740993` như một số JavaScript, chữ số có thể đã bị làm tròn **trước khi MongoDB nhận dữ liệu**. Một phép chuyển kiểu về Int64 ở bước sau không thể tự biết giá trị gốc ban đầu.

Dùng Int32 khi chắc chắn giá trị nằm trong miền 32 bit; dùng Int64 cho số nguyên cần miền lớn hơn. Cả hai vẫn cần kiểm tra overflow khi tổng cộng dồn hoặc nhân vượt giới hạn.

### 2.2. Double: không phải mọi số thập phân đều biểu diễn chính xác

Double lưu số theo cơ số 2. Các phân số thập phân quen thuộc như `0.1` và `0.2` thường không có biểu diễn nhị phân hữu hạn.

Thử trong `mongosh`:

~~~javascript
0.1 + 0.2;          // thường hiển thị 0.30000000000000004
(0.1 + 0.2) === 0.3; // false
~~~

Các phép toán này được tính trong JavaScript trên kiểu `Number`; nó minh họa đặc tính của dấu phẩy động nhị phân. Không nên đưa kết quả các phép cộng như vậy vào trường tiền tệ rồi kỳ vọng việc chuyển sang Decimal128 sẽ sửa được sai lệch đã tích lũy.

Double vẫn hữu ích khi đo lường hoặc tính toán mà sai số biểu diễn đã được xác định và chấp nhận, chẳng hạn tọa độ, nhiệt độ hay các mô hình thống kê.

### 2.3. Decimal128: chính xác theo cơ số 10 trong giới hạn định dạng

Trong `mongosh`, tạo Decimal128 từ **chuỗi thập phân**:

~~~javascript
NumberDecimal("0.1")
NumberDecimal("0.2")
NumberDecimal("19.99")
NumberDecimal("1234567890.123456789")
~~~

Có thể cho server thực hiện phép cộng Decimal128:

~~~javascript
db.runCommand({
  aggregate: 1,
  pipeline: [
    {
      $documents: [
        {
          a: NumberDecimal("0.1"),
          b: NumberDecimal("0.2")
        }
      ]
    },
    { $project: { _id: 0, total: { $add: ["$a", "$b"] } } }
  ],
  cursor: {}
});
~~~

Kết quả `total` là giá trị Decimal128 tương đương `0.3`. Ở một số phiên bản server, stage `$documents` không phù hợp với mọi ngữ cảnh hoặc phiên bản; cách thực hành tương thích hơn là lưu document rồi chạy `aggregate` trên collection như mục 3.

Điểm quan trọng là **đưa giá trị thập phân chính xác vào hệ thống ngay từ đầu** bằng chuỗi hoặc đối tượng decimal của ngôn ngữ lập trình. Ví dụ `NumberDecimal("19.99")` giữ biểu diễn thập phân cần thiết, trong khi một biểu thức JavaScript `19.99 + 0.01` đã sử dụng phép toán Double trước khi được chuyển kiểu.

Decimal128 không đồng nghĩa với “vô hạn chính xác”: kết quả có nhiều hơn 34 chữ số có nghĩa phải được làm tròn trong giới hạn định dạng. Với dữ liệu tài chính, ứng dụng vẫn phải quy định số chữ số thập phân được phép và cách xử lý khi làm tròn.

## 3. Thực hành kiểm tra kiểu số thật trong BSON

Sử dụng database độc lập để tránh đụng tới dữ liệu khác:

~~~javascript
use numeric_precision_lab

db.numericSamples.replaceOne(
  { _id: "sample-1" },
  {
    _id: "sample-1",
    quantity32: NumberInt(12),
    quantity64: NumberLong("12"),
    priceDouble: 19.99,
    priceDecimal: NumberDecimal("19.99"),
    bigIdLong: NumberLong("9007199254740993"),
    bigIdAsJsNumber: 9007199254740993,
    textAmount: "19.99"
  },
  { upsert: true }
);
~~~

`replaceOne` với `upsert: true` giúp có thể nạp lại đúng một document thực hành. Cần nhớ việc chạy lại sẽ **thay các trường trong document mẫu** bằng giá trị ban đầu.

Kiểm tra kiểu bằng aggregation operator `$type`:

~~~javascript
db.numericSamples.aggregate([
  {
    $project: {
      _id: 1,
      type32: { $type: "$quantity32" },
      type64: { $type: "$quantity64" },
      typeDouble: { $type: "$priceDouble" },
      typeDecimal: { $type: "$priceDecimal" },
      typeText: { $type: "$textAmount" }
    }
  }
]);
~~~

Kết quả tương ứng nên là:

~~~json
{
  "_id": "sample-1",
  "type32": "int",
  "type64": "long",
  "typeDouble": "double",
  "typeDecimal": "decimal",
  "typeText": "string"
}
~~~

Lọc theo kiểu BSON của một trường:

~~~javascript
db.numericSamples.find({
  priceDecimal: { $type: "decimal" }
});

db.numericSamples.find({
  priceDouble: { $type: "double" }
});
~~~

Lệnh `$type` cho biết **kiểu lưu trữ**, hữu ích hơn việc chỉ nhìn cách MongoDB Compass hoặc terminal in giá trị. Các lớp wrapper BSON trong shell cũng làm cho việc suy luận chỉ dựa vào JavaScript `typeof` không đủ để phân biệt mọi kiểu số BSON.

### 3.1. Quan sát số nguyên đã bị làm tròn ở phía client

~~~javascript
const unsafeId = 9007199254740993;

print(unsafeId); // có thể hiển thị 9007199254740992

db.numericSamples.findOne(
  { _id: "sample-1" },
  { _id: 0, bigIdLong: 1, bigIdAsJsNumber: 1 }
);
~~~

Giá trị `bigIdLong` được tạo từ chuỗi và giữ nguyên 9.007.199.254.740.993; giá trị `bigIdAsJsNumber` được truyền qua JavaScript Number nên có thể trở thành 9.007.199.254.740.992. Đây là **mất dữ liệu trước khi ghi**, không phải do MongoDB tự thay đổi Int64.

### 3.2. Extended JSON để bảo toàn thông tin kiểu khi trao đổi

JSON thông thường chỉ có dạng number chung. MongoDB cung cấp **Extended JSON** với các biểu thức đánh dấu kiểu BSON rõ ràng. Ví dụ dạng Canonical Extended JSON:

~~~json
{
  "_id": "sample-2",
  "quantity32": { "$numberInt": "12" },
  "quantity64": { "$numberLong": "12" },
  "priceDouble": { "$numberDouble": "19.99" },
  "priceDecimal": { "$numberDecimal": "19.99" },
  "bigIdLong": { "$numberLong": "9007199254740993" }
}
~~~

Có thể quan sát biểu diễn Extended JSON từ mongosh:

~~~javascript
const document = db.numericSamples.findOne({ _id: "sample-1" });
print(EJSON.stringify(document, null, 2, { relaxed: false }));
~~~

Chế độ **Canonical** (ví dụ `relaxed: false`) ưu tiên giữ kiểu. Chế độ **Relaxed** có thể sử dụng số JSON thông thường cho một số kiểu, thuận tiện để đọc nhưng có nguy cơ làm mất thông tin kiểu khi dữ liệu đi qua môi trường không hiểu BSON.

**Không nhập trực tiếp object `{"$numberDecimal":"19.99"}` vào một lệnh `insertOne` trong mongosh như cách tạo Decimal128 thông thường.** Đó là biểu diễn Extended JSON; khi ghi trực tiếp từ JavaScript shell hãy dùng `NumberDecimal("19.99")` hoặc phân tích Extended JSON bằng API tương ứng như `EJSON.parse`.

## 4. Hai chiến lược biểu diễn tiền tệ

Tiền tệ cần quy tắc rõ ràng về **đơn vị, loại tiền và cách làm tròn**. Hai cách phổ biến đều phù hợp nếu được áp dụng nhất quán.

| Cách lưu | Document minh họa | Ưu điểm | Điều cần kiểm soát |
|---|---|---|---|
| **Số nguyên đơn vị nhỏ nhất** | `{currency:"USD",scale:2,amountMinor:NumberLong("1299")}` | Cộng trừ chính xác trên số nguyên; phù hợp các hệ thống tính theo cent | Phải có scale/đơn vị rõ; không vượt Int64; xử lý chia và phân bổ phần dư |
| **Decimal128 theo đơn vị tiền chính** | `{currency:"USD",amount:NumberDecimal("12.99")}` | Biểu diễn trực tiếp số tiền thập phân; thuận tiện với thuế, tỷ giá, giá có phần lẻ | Quy định độ chính xác, scale, rounding và xử lý kết quả phép tính |

Không có quy tắc “mọi đồng tiền có 2 chữ số thập phân”. Một số đồng tiền thường không có đơn vị lẻ dùng trong giao dịch, một số có ba chữ số hoặc quy tắc khác. Bảng hệ số scale trong ứng dụng phải dựa trên yêu cầu nghiệp vụ, đơn vị thanh toán và chuẩn tiền tệ mà sản phẩm hỗ trợ.

### 4.1. Lưu số tiền dưới dạng Int64 đơn vị nhỏ nhất

Ví dụ hóa đơn USD có tiền hàng `12.99 USD` và phí vận chuyển `2.50 USD`. Khi quy ước `scale = 2`, giá trị lưu bằng số cent:

~~~javascript
db.invoices.replaceOne(
  { _id: "inv-minor-001" },
  {
    _id: "inv-minor-001",
    currency: "USD",
    scale: NumberInt(2),
    itemMinor: NumberLong("1299"),
    shippingMinor: NumberLong("250"),
    totalMinor: NumberLong("1549")
  },
  { upsert: true }
);
~~~

Công thức diễn giải đơn vị:

\[
\text{amountMajor} = \frac{\text{amountMinor}}{10^{\text{scale}}}
\]

Với `1549` cent và `scale=2`, số tiền hiển thị là `15.49 USD`. Phép cộng các số nguyên ở trên chính xác trong miền Int64. Tuy nhiên, **chia**, **tỷ lệ chiết khấu**, **thuế** và **phân bổ tiền lẻ** vẫn phải có quy tắc làm tròn riêng trước khi tạo thành số nguyên cent.

Vì định dạng BSON có miền hữu hạn, cần kiểm tra giới hạn tổng tiền và các phép nhân trước khi ghi vào Int64. Không tùy tiện đổi `amountMinor` thành Double để tránh lỗi tràn số.

### 4.2. Lưu Decimal128 với đơn vị tiền chính

~~~javascript
db.invoices.replaceOne(
  { _id: "inv-decimal-001" },
  {
    _id: "inv-decimal-001",
    currency: "USD",
    unitPrice: NumberDecimal("12.99"),
    quantity: NumberInt(3),
    taxRate: NumberDecimal("0.0825")
  },
  { upsert: true }
);
~~~

Tính thành tiền và tiền thuế trong aggregation:

~~~javascript
db.invoices.aggregate([
  { $match: { _id: "inv-decimal-001" } },
  {
    $set: {
      subtotal: { $multiply: ["$unitPrice", "$quantity"] }
    }
  },
  {
    $set: {
      taxExact: { $multiply: ["$subtotal", "$taxRate"] }
    }
  },
  {
    $project: {
      _id: 1,
      currency: 1,
      subtotal: 1,
      taxExact: 1,
      taxRounded: { $round: ["$taxExact", 2] }
    }
  }
]);
~~~

Với giá `12.99`, số lượng `3`, tổng trước thuế là `38.97`. Tiền thuế chưa làm tròn là `3.215025`, còn làm tròn hai chữ số với `$round` cho kết quả `3.22`.

**Đây chỉ là ví dụ về cơ chế làm tròn.** Thực tế cần xác định thuế làm tròn theo dòng hàng hay tổng hóa đơn, trước hay sau chiết khấu và quy tắc pháp lý tương ứng. Chọn sai thời điểm làm tròn vẫn khiến tổng tiền sai ngay cả khi dùng Decimal128.

Không cộng trực tiếp các số tiền thuộc hai loại tiền tệ khác nhau. Khi quy đổi tỷ giá, cần lưu/định nghĩa tỷ giá, thời điểm áp dụng, đơn vị tiền nguồn/đích và chính sách làm tròn sau quy đổi.

## 5. Quy tắc làm tròn và độ chính xác trong MongoDB

### 5.1. `$round` và `$trunc`

Hai aggregation expression thường gặp:

~~~javascript
{ $round: [<number>, <place>] }
{ $trunc: [<number>, <place>] }
~~~

- `$round` làm tròn tới vị trí chỉ định. Khi đúng điểm giữa (chữ số bỏ đi ở ngưỡng `5` với phần sau phù hợp), MongoDB dùng **round half to even**: chọn chữ số cuối giữ lại là chẵn.
- `$trunc` cắt bỏ phần lẻ ở vị trí chỉ định, tiến về `0`; không thực hiện làm tròn lên theo quy tắc số học.
- `place = 2` nghĩa là giữ hai chữ số sau dấu thập phân; `0` nghĩa là làm tròn/cắt đến số nguyên; giá trị âm làm tròn ở hàng chục, hàng trăm, v.v.
- Kiểu kết quả của `$round`/`$trunc` phụ thuộc kiểu đầu vào; với Decimal128 đầu vào, kết quả duy trì kiểu Decimal128.

Ví dụ rõ ràng với dữ liệu Decimal128:

~~~javascript
db.roundingSamples.replaceOne(
  { _id: "round-1" },
  {
    _id: "round-1",
    a: NumberDecimal("2.345"),
    b: NumberDecimal("2.355"),
    c: NumberDecimal("-2.349")
  },
  { upsert: true }
);

db.roundingSamples.aggregate([
  { $match: { _id: "round-1" } },
  {
    $project: {
      _id: 0,
      roundA: { $round: ["$a", 2] },
      roundB: { $round: ["$b", 2] },
      truncC: { $trunc: ["$c", 2] }
    }
  }
]);
~~~

Giá trị mong đợi:

| Phép toán | Kết quả Decimal128 | Giải thích |
|---|---|---|
| `$round("2.345", 2)` | `2.34` | Điểm giữa: chọn chữ số hàng phần trăm chẵn là 4 |
| `$round("2.355", 2)` | `2.36` | Điểm giữa: chọn chữ số hàng phần trăm chẵn là 6 |
| `$trunc("-2.349", 2)` | `-2.34` | Cắt về phía 0, không làm tròn xuống `-2.35` |

Nếu nghiệp vụ yêu cầu **half up** hoặc **half away from zero**, không được mặc định rằng `$round` đáp ứng. Cần triển khai quy tắc bằng logic riêng, kiểm thử với số âm và trường hợp biên, rồi áp dụng thống nhất ở server/backend.

### 5.2. Làm tròn ở bước nào?

Giả sử có ba dòng hàng, mỗi dòng tạo ra tiền thuế chưa làm tròn là `0.005 USD`:

- Làm tròn từng dòng theo half-to-even: mỗi `0.005` có thể thành `0.00`, tổng bằng `0.00`.
- Cộng trước: `0.005 + 0.005 + 0.005 = 0.015`, sau đó làm tròn hai chữ số theo half-to-even thành `0.02`.

Đây không phải lỗi tính toán: **quy tắc làm tròn theo dòng** và **quy tắc làm tròn theo tổng** là hai chính sách khác nhau. Ứng dụng cần chỉ rõ chính sách áp dụng; không nên làm tròn ngẫu nhiên tại nhiều tầng (frontend, backend và database).

Nếu dùng Int64 cent, kết quả của phép chia/nhân tỷ lệ phải được quantize theo chính sách xác định trước khi lưu. Nếu dùng Decimal128, vẫn cần bước quantize trước khi thanh toán hoặc đối soát.

## 6. Chuyển đổi kiểu dữ liệu với aggregation

MongoDB hỗ trợ các toán tử chuyển đổi chuyên biệt và toán tử tổng quát:

| Toán tử | Mục đích | Lưu ý |
|---|---|---|
| `$toInt` | Đưa đầu vào thích hợp về BSON Int32 | Lỗi nếu không chuyển được hoặc ngoài miền 32 bit |
| `$toLong` | Đưa về BSON Int64 | Lỗi nếu không chuyển được hoặc vượt miền 64 bit |
| `$toDouble` | Đưa về BSON Double | Có thể mất chính xác theo biểu diễn nhị phân |
| `$toDecimal` | Đưa về BSON Decimal128 | Hữu ích khi chuẩn hóa chuỗi thập phân hợp lệ |
| `$toString` | Đưa giá trị được hỗ trợ về chuỗi | Phù hợp cho hiển thị/trao đổi, không thay thế format tiền tệ |
| `$convert` | Chỉ rõ kiểu đích và cách xử lý lỗi/null | Hữu ích nhất cho dữ liệu đầu vào không đáng tin cậy |
| `$type` | Xem kiểu BSON của một biểu thức | Dùng để khảo sát và xác minh sau khi chuyển đổi |

Những toán tử `$to...` thường là dạng viết tắt của `$convert` và có thể làm **pipeline dừng với lỗi** khi gặp giá trị không chuyển được. Để xử lý riêng từng document khi dữ liệu bẩn, dùng `$convert` với `onError` và `onNull`.

### 6.1. Chuyển chuỗi thành Decimal128 và Int64

Nạp dữ liệu thô mô phỏng một bảng nhập từ hệ thống khác:

~~~javascript
const rawRows = [
  { _id: "r1", priceText: "125.50", quantityText: "3" },
  { _id: "r2", priceText: "0.10", quantityText: "2" },
  { _id: "r3", priceText: "12,50", quantityText: "3" },
  { _id: "r4", priceText: null, quantityText: "1" },
  { _id: "r5", priceText: "30.00", quantityText: "abc" }
];

rawRows.forEach(row => {
  db.rawAmounts.replaceOne({ _id: row._id }, row, { upsert: true });
});
~~~

Kết quả thử nghiệm chuyển đổi bằng `$convert`:

~~~javascript
db.rawAmounts.aggregate([
  {
    $project: {
      _id: 1,
      priceText: 1,
      quantityText: 1,
      priceDecimal: {
        $convert: {
          input: "$priceText",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      quantityLong: {
        $convert: {
          input: "$quantityText",
          to: "long",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với `r1` và `r2`, chuỗi giá có dạng thập phân hợp lệ nên chuyển được sang Decimal128; `quantityText` dạng số nguyên hợp lệ chuyển được thành Int64. Các trường hợp `"12,50"`, `null` hoặc `"abc"` được ánh xạ thành `null` nhờ `onError`/`onNull`.

Chuỗi có dấu phẩy phân cách thập phân hoặc hàng nghìn thường cần được **chuẩn hóa định dạng ở tầng nhập liệu**, dựa trên locale hợp lệ, trước khi chuyển kiểu. Không đơn giản xóa mọi dấu phẩy mà không biết liệu chúng biểu thị phân cách thập phân hay phân cách hàng nghìn.

### 6.2. Tính toán sau khi chuyển đổi

Nên chỉ nhân khi cả giá và số lượng đã được chuyển thành công:

~~~javascript
db.rawAmounts.aggregate([
  {
    $set: {
      priceDecimal: {
        $convert: {
          input: "$priceText",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      quantityLong: {
        $convert: {
          input: "$quantityText",
          to: "long",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      lineTotal: {
        $cond: [
          {
            $and: [
              { $ne: ["$priceDecimal", null] },
              { $ne: ["$quantityLong", null] }
            ]
          },
          { $multiply: ["$priceDecimal", "$quantityLong"] },
          null
        ]
      }
    }
  },
  {
    $project: {
      priceText: 1,
      quantityText: 1,
      priceDecimal: 1,
      quantityLong: 1,
      lineTotal: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với `r1`, tổng dòng là `376.50`. Với `r2`, tổng là `0.20`. Những hàng không hợp lệ được giữ lại để điều tra thay vì làm lỗi cả pipeline.

**Không nên âm thầm biến mọi lỗi thành 0 trong nghiệp vụ tiền tệ.** `null` ở ví dụ giúp phân biệt “không tính được” với số tiền thật bằng `0`. Trong hệ thống sản xuất, còn phải ghi nhận mã lỗi, nguồn nhập và lý do sai định dạng.

### 6.3. Nhận diện lỗi khác với dữ liệu null

Khi kiểm tra dữ liệu thô, có thể trả về ký hiệu riêng cho lỗi chuyển kiểu và giá trị null:

~~~javascript
db.rawAmounts.aggregate([
  {
    $project: {
      _id: 1,
      originalType: { $type: "$priceText" },
      parsed: {
        $convert: {
          input: "$priceText",
          to: "decimal",
          onError: "INVALID_NUMBER",
          onNull: "MISSING_VALUE"
        }
      }
    }
  }
]);
~~~

Toán tử trả về số Decimal128 cho chuỗi hợp lệ, nhưng chuỗi sentinel `"INVALID_NUMBER"` hay `"MISSING_VALUE"` cho hai tình huống khác nhau. **Đây là pipeline chẩn đoán**, không nên đưa `parsed` hỗn hợp number/string vào phép cộng hoặc lưu làm trường tiền tệ chính thức.

### 6.4. Các trường hợp chuyển đổi cần đặc biệt lưu ý

| Nguồn và kiểu đích | Ví dụ | Hệ quả |
|---|---|---|
| Chuỗi số nguyên → Int64 | `"42"` → `$toLong` | Thành công nếu hợp lệ và trong miền |
| Chuỗi có phần lẻ → Int64 | `"42.5"` → `$toLong` | Lỗi chuyển đổi; chuỗi phải có dạng số nguyên hợp lệ |
| Decimal128 có phần lẻ → Int64 | `NumberDecimal("42.9")` → `$toLong` | Cắt phần lẻ về phía 0 nếu giá trị nằm trong miền; không tự làm tròn theo chính sách tiền tệ |
| Int64 lớn → Double | `9007199254740993` → `$toDouble` | Có thể mất chữ số vì Double không chính xác với mọi số nguyên lớn |
| Double đã sai số → Decimal128 | Kết quả Double đã qua phép toán → `$toDecimal` | Không khôi phục được dữ liệu chính xác đã mất trước đó |
| Chuỗi sai format → Decimal128 | `"12,50"` → `$toDecimal` | Lỗi nếu không chuẩn hóa input |
| Giá trị vượt miền → Int32/Int64 | `"999999999999999999999999"` → `$toLong` | Lỗi tràn miền |
| Null/missing → `$convert` | Input rỗng hoặc thiếu | Xử lý bằng `onNull`; nếu không chỉ định sẽ trả về null |

Việc cắt phần lẻ khi chuyển một **giá trị số** sang số nguyên khác với phép chuyển trực tiếp từ **chuỗi chứa phần thập phân**. Nếu cần chuyển tiền Decimal128 sang cent Int64, hãy nhân theo scale, làm tròn theo chính sách, xác minh miền giá trị rồi mới chuyển về số nguyên.

Ví dụ biểu diễn ý tưởng chuyển số tiền USD sang cent:

~~~javascript
db.invoices.aggregate([
  { $match: { _id: "inv-decimal-001" } },
  {
    $project: {
      _id: 1,
      unitPriceMinor: {
        $toLong: {
          $round: [
            { $multiply: ["$unitPrice", NumberDecimal("100")] },
            0
          ]
        }
      }
    }
  }
]);
~~~

Ở đây `12.99 × 100` thành `1299` trước khi chuyển Int64. Với các giá trị âm, quy tắc khác half-to-even hoặc số cực lớn, cần xác minh chính sách và miền trước khi áp dụng tự động. Nên coi đơn vị nhỏ nhất và scale là phần của **hợp đồng dữ liệu**, không chỉ là cách hiển thị.

## 7. Chuyển đổi, tính toán và kiểu trả về

MongoDB thực hiện quy tắc quảng bá kiểu số (numeric promotion) trong nhiều aggregation operator như `$add`, `$multiply` và `$sum`. Khi đầu vào khác kiểu, kết quả có thể được nâng lên kiểu rộng hơn, ví dụ từ Int32 lên Int64, Double hoặc Decimal128 tùy phép toán và dữ liệu; overflow cũng có thể làm thay đổi cách xử lý kiểu.

Điều này dẫn đến ba nguyên tắc thiết kế:

1. **Định nghĩa một kiểu chuẩn cho mỗi trường nghiệp vụ.** Ví dụ mọi `unitPrice` của một collection là Decimal128; mọi `quantity` là Int32/Int64 theo yêu cầu; mọi `amountMinor` là Int64.
2. **Chuyển ở ranh giới nhập liệu.** Khi nhận chuỗi giá tiền, chuyển và kiểm tra trước khi lưu. Tránh để lẫn chuỗi, Double và Decimal128 rồi mới chuyển lúc báo cáo.
3. **Kiểm tra kiểu kết quả.** Phép tính có thể trả về kiểu khác kỳ vọng nếu đầu vào hỗn hợp; dùng `$type` để quan sát.

Ví dụ quan sát kiểu kết quả phép nhân Decimal128:

~~~javascript
db.invoices.aggregate([
  { $match: { _id: "inv-decimal-001" } },
  {
    $project: {
      _id: 0,
      lineTotal: { $multiply: ["$unitPrice", "$quantity"] },
      lineTotalType: {
        $type: { $multiply: ["$unitPrice", "$quantity"] }
      }
    }
  }
]);
~~~

Do `unitPrice` là Decimal128, kết quả được kỳ vọng ở kiểu `decimal` trong phép tính này. Đối với một trường tiền tệ, việc biết **kiểu của kết quả** quan trọng tương đương giá trị được hiển thị.

### 7.1. Cộng tiền trên nhiều document

Giả sử một collection có nhiều dòng hóa đơn:

~~~javascript
const lines = [
  {
    _id: "line-1",
    invoiceId: "invoice-A",
    unitPrice: NumberDecimal("19.99"),
    quantity: NumberInt(2)
  },
  {
    _id: "line-2",
    invoiceId: "invoice-A",
    unitPrice: NumberDecimal("5.25"),
    quantity: NumberInt(3)
  },
  {
    _id: "line-3",
    invoiceId: "invoice-B",
    unitPrice: NumberDecimal("8.50"),
    quantity: NumberInt(1)
  }
];

lines.forEach(row => {
  db.invoiceLines.replaceOne({ _id: row._id }, row, { upsert: true });
});
~~~

Tổng thành tiền cho từng hóa đơn:

~~~javascript
db.invoiceLines.aggregate([
  {
    $set: {
      lineTotal: { $multiply: ["$unitPrice", "$quantity"] }
    }
  },
  {
    $group: {
      _id: "$invoiceId",
      total: { $sum: "$lineTotal" },
      numberOfLines: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 1,
      numberOfLines: 1,
      total: { $round: ["$total", 2] },
      totalType: { $type: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Nếu chỉ có ba dòng mẫu, tổng trước thuế của `invoice-A` là `55.73` (`19.99 × 2 + 5.25 × 3`), còn `invoice-B` là `8.50`. Dữ liệu chứa Decimal128 giúp phép cộng thập phân được thực hiện với độ chính xác của kiểu này.

Với giao dịch có chiết khấu, thuế và nhiều loại tiền, nên nhóm theo **cả invoiceId lẫn currency** hoặc kiểm tra rằng hóa đơn chỉ chứa một loại tiền tệ, sau đó áp dụng quy tắc rounding tại bước đúng nghiệp vụ.

## 8. Lưu kiểu chính xác từ ứng dụng Java

Trong dự án Java, kiểu của giá trị **trước khi đưa tới MongoDB Driver** cũng quan trọng như kiểu BSON. Java `double` có hạn chế biểu diễn tương tự Double trong BSON; Java `BigDecimal` biểu diễn số thập phân và phù hợp hơn để làm việc với giá, thuế và tiền.

Ví dụ với MongoDB Java Driver:

~~~java
import java.math.BigDecimal;
import org.bson.Document;
import org.bson.types.Decimal128;

BigDecimal exactPrice = new BigDecimal("19.99");

Document product = new Document("_id", "product-001")
    .append("currency", "USD")
    .append("unitPrice", new Decimal128(exactPrice))
    .append("quantity", 3);

Decimal128 storedPrice = product.get("unitPrice", Decimal128.class);
BigDecimal valueForBusinessLogic = storedPrice.bigDecimalValue();
~~~

Cách tạo `new BigDecimal("19.99")` nhận đúng giá trị thập phân từ **chuỗi**. Tránh dùng `new BigDecimal(19.99)` nếu ý định là giá trị tiền `19.99`, vì constructor nhận `double` sẽ đưa cả sai số nhị phân của giá trị đầu vào vào BigDecimal.

`BigDecimal` có thể giữ độ chính xác lớn hơn Decimal128. Khi lưu một BigDecimal quá giới hạn biểu diễn của Decimal128, cần kiểm tra/quantize hoặc từ chối giá trị theo quy tắc nghiệp vụ; không giả định mọi BigDecimal đều lưu được nguyên vẹn.

Với Java `Long`, giá trị chính xác nằm trong miền 64 bit, tương ứng với BSON Int64. Khi cần trao đổi những giá trị nguyên lớn qua API JSON đến JavaScript frontend, nên dùng cơ chế serialization có giữ kiểu hoặc chuỗi thập phân có hợp đồng rõ ràng; không ép mọi số nguyên lớn thành JavaScript Number.

### 8.1. Ranh giới API và ứng dụng đa ngôn ngữ

Một quy trình an toàn thường là:

~~~text
HTTP/CSV/Input
    |
    v
Kiểm tra đơn vị tiền + định dạng + kiểu nguồn
    |
    v
Chuyển sang BigDecimal / Int64 chính xác
    |
    v
Kiểm tra miền, scale và rounding policy
    |
    v
Ghi BSON Decimal128 hoặc BSON Int64
    |
    v
Đọc lại → tính toán/hiển thị theo currency + scale
~~~

Nếu frontend gửi `"19.99"` dưới dạng chuỗi hợp đồng, backend có thể parse thẳng sang BigDecimal chính xác. Nếu frontend tính `19.99 + 0.01` bằng JavaScript rồi mới gửi một số JSON, sai số đã có thể xuất hiện trước khi backend bắt đầu xử lý.

Không tin vào định dạng hiển thị: giao diện có thể in `19.99` dù kiểu underlying là Double. Quyết định lưu kiểu và rounding thuộc hợp đồng dữ liệu của hệ thống.

## 9. MongoDB Compass: xem và sửa trường số mà không đổi nhầm kiểu

Compass giúp quan sát kiểu BSON trong document. Tùy phiên bản, trình biên tập document có thể có lựa chọn kiểu như Int32, Int64, Double, Decimal128, String hoặc các biểu diễn Extended JSON.

Hãy kết nối tới cùng database `numeric_precision_lab` và mở collection `numericSamples`:

1. Mở document `sample-1`, quan sát các giá trị `quantity32`, `quantity64`, `priceDouble`, `priceDecimal`.
2. Nếu giao diện hiển thị nhãn kiểu, đối chiếu với kết quả `$type` ở mục 3.
3. Khi sửa `priceDecimal`, xác nhận vẫn giữ kiểu **Decimal128**. Nếu thay `NumberDecimal("19.99")` bằng một số JSON thường trong môi trường không bảo toàn kiểu, trường có thể bị lưu khác kiểu dự định.
4. Nếu Compass sử dụng chế độ Extended JSON, có thể dựa vào wrapper như `{"$numberDecimal":"19.99"}` hoặc `{"$numberLong":"9007199254740993"}` theo cách giao diện phiên bản đó hỗ trợ.
5. Sau thao tác lưu, trở lại mongosh chạy:

~~~javascript
db.numericSamples.aggregate([
  { $match: { _id: "sample-1" } },
  {
    $project: {
      _id: 0,
      priceDecimalType: { $type: "$priceDecimal" },
      quantity64Type: { $type: "$quantity64" }
    }
  }
]);
~~~

Khi nhập trường tiền tệ vào Compass, phải kiểm tra **kiểu BSON**, **giá trị chính xác** và **đơn vị tiền**. Việc một field hiển thị với hai chữ số thập phân chưa chứng minh nó được lưu ở Decimal128.

## 10. Khảo sát và chuẩn hóa collection có nhiều kiểu lẫn lộn

Dữ liệu lịch sử có thể chứa tiền ở nhiều kiểu. Thử nạp ví dụ:

~~~javascript
const legacyRows = [
  { _id: "l1", amount: NumberDecimal("10.50"), currency: "USD" },
  { _id: "l2", amount: 10.50, currency: "USD" },
  { _id: "l3", amount: "10.50", currency: "USD" },
  { _id: "l4", amount: NumberInt(11), currency: "USD" },
  { _id: "l5", amount: "invalid", currency: "USD" }
];

legacyRows.forEach(row => {
  db.legacyPayments.replaceOne({ _id: row._id }, row, { upsert: true });
});
~~~

Nhóm và đếm theo kiểu BSON:

~~~javascript
db.legacyPayments.aggregate([
  {
    $group: {
      _id: { $type: "$amount" },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Xem trước khả năng chuyển đổi mà **không sửa dữ liệu**:

~~~javascript
db.legacyPayments.aggregate([
  {
    $project: {
      _id: 1,
      amount: 1,
      amountType: { $type: "$amount" },
      candidateDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: "INVALID_NUMBER",
          onNull: "MISSING_VALUE"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Từ kết quả preview, lập danh sách document không hợp lệ hoặc cần đối soát. **Không chuyển hàng loạt rồi ghi đè ngay** chỉ vì đa số document chuyển được: với nguồn Double, giá trị có thể đã trải qua các phép tính thiếu chính xác trước khi lưu. Cần đối chiếu nguồn nghiệp vụ, quyết định chính sách scale, định nghĩa cách xử lý sai lệch và có kế hoạch backup/rollback phù hợp trước khi migration.

Sau khi xác định kiểu chuẩn, hệ thống nên áp dụng validation ở tầng ứng dụng; tùy nhu cầu, có thể dùng MongoDB JSON Schema validator để yêu cầu `amount` là BSON `decimal` hoặc `long` và bắt buộc có `currency`. Validator giúp ngăn **sai kiểu** trong các bản ghi mới, nhưng không thay thế kiểm tra chính sách làm tròn và đơn vị tiền.

Một ví dụ schema có thể áp dụng cho một **collection mới**, khi thiết kế chính sách lưu Decimal128:

~~~javascript
db.createCollection("paymentsValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["currency", "amount"],
      properties: {
        currency: {
          bsonType: "string",
          description: "Mã loại tiền"
        },
        amount: {
          bsonType: "decimal",
          description: "Số tiền theo đơn vị tiền chính"
        }
      }
    }
  }
});
~~~

Lệnh `createCollection` chỉ chạy khi collection chưa tồn tại. Ví dụ này nhằm minh họa cơ chế validation; quy tắc nghiệp vụ thực còn có thể cần yêu cầu số tiền dương/không âm, mã tiền hợp lệ, số chữ số thập phân tối đa và trạng thái giao dịch.

## 11. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Tổng `0.1 + 0.2` không đúng `0.3` theo so sánh tuyệt đối | Double biểu diễn nhị phân | Với tiền, dùng Decimal128 từ chuỗi hoặc Int64 đơn vị nhỏ nhất |
| Int64 lớn đổi thành số khác sau khi frontend gửi dữ liệu | Bị đi qua JavaScript Number vượt `2^53 - 1` | Truyền bằng chuỗi hoặc định dạng có giữ kiểu; parse trực tiếp sang Int64 |
| Chuyển `"12,50"` sang Decimal128 bị lỗi | Chuỗi không đúng định dạng thập phân MongoDB yêu cầu | Chuẩn hóa theo locale trước khi parse |
| `$toInt` hoặc `$toLong` làm aggregation dừng | Dữ liệu không chuyển được hoặc vượt miền | Dùng `$convert` với xử lý lỗi, đồng thời ghi nhận bản ghi sai |
| Số tiền âm làm tròn khác dự kiến | Chính sách rounding khác nhau | Thống nhất half-even, half-up hay cách khác và kiểm thử giá trị âm |
| Dữ liệu cùng trường nhưng có nhiều kiểu BSON | Các nguồn ghi dữ liệu không thống nhất | Dùng `$type` để khảo sát, chuẩn hóa tại ranh giới nhập |
| Phép chuyển sang Decimal128 vẫn không khôi phục số gốc | Giá trị đã mất chính xác khi còn là Double/JS Number | Phục hồi từ nguồn dữ liệu chính xác, không chỉ ép kiểu |
| Hóa đơn lệch vài cent giữa các hệ thống | Làm tròn ở thời điểm khác nhau hoặc scale khác nhau | Đối chiếu từng bước tính thuế/chiết khấu, đơn vị tiền, quy tắc phân bổ phần dư |
| Driver báo lỗi khi lưu BigDecimal | Giá trị không vừa giới hạn Decimal128 | Kiểm tra precision, scale, miền và quy tắc làm tròn trước khi tạo Decimal128 |
| Compass hiển thị giá nhưng sau sửa bị sai kiểu | Editor/JSON nhập giá trị khác loại BSON dự định | Kiểm tra typed editor/EJSON và xác nhận lại với `$type` |

## 12. Bài thực hành tự kiểm tra

Thực hành trong database `numeric_precision_lab`:

1. Tạo `numericSamples` ở mục 3, sau đó truy vấn `$type` để phân biệt `int`, `long`, `double`, `decimal` và `string`.
2. So sánh `bigIdLong` với `bigIdAsJsNumber`. Giải thích vì sao giá trị Int64 từ chuỗi giữ được số nguyên hơn 53 bit chính xác, còn literal JavaScript thì không.
3. Thực hiện `0.1 + 0.2` trong shell, sau đó tính tổng với hai giá trị Decimal128 bằng aggregation. Ghi nhận sự khác nhau về cách biểu diễn.
4. Tạo hóa đơn `inv-minor-001` (Int64 cent) và `inv-decimal-001` (Decimal128 USD). Diễn giải rõ đơn vị của từng trường.
5. Tính `subtotal`, `taxExact`, `taxRounded` và xác định phép nào đang áp dụng rounding half-to-even.
6. Chạy `roundingSamples`, so sánh `$round` và `$trunc` ở số dương và số âm.
7. Nạp `rawAmounts`, dùng `$convert` với `onError` và `onNull`; chỉ ra những giá trị hợp lệ và không hợp lệ.
8. Dùng `$type` nhóm `legacyPayments` theo kiểu và xem preview chuẩn hóa, không cập nhật trực tiếp collection.
9. Trong Compass, mở `numericSamples` rồi kiểm tra kiểu của trường `priceDecimal` trước và sau khi chỉnh sửa; xác minh lại trong mongosh.
10. Giải thích chọn kiểu nào cho: số lượng hàng (0–10.000), số tiền USD, bộ đếm nguyên có thể vượt Int32 và số đo khoa học có sai số cho phép.

### Câu hỏi vận dụng

**Câu 1.** Một API trả về `{"amount":19.99}`. Chỉ từ JSON này có thể khẳng định MongoDB đang lưu trường `amount` bằng Decimal128 không?

*Đáp án:* Không. JSON number không biểu thị đầy đủ kiểu BSON; phải biết hợp đồng serialization hoặc kiểm tra dữ liệu nguồn bằng `$type`/Extended JSON.

**Câu 2.** Có nên chuyển một trường Double đang chứa tổng tiền sang Decimal128 bằng `$toDecimal` rồi xem đó là dữ liệu đã chính xác tuyệt đối?

*Đáp án:* Không. Chuyển kiểu không đảo ngược được sai số hay mất chữ số đã xảy ra trong các phép tính trước đó.

**Câu 3.** Khi hệ thống cần thu phí chính xác theo cent, chọn Int64 cent hay Decimal128 USD?

*Đáp án:* Cả hai có thể phù hợp; quyết định theo cách tính thuế, tỷ giá, miền giá trị, tích hợp API và chính sách rounding. Điều kiện tiên quyết là đơn vị và kiểu được thống nhất toàn hệ thống.

**Câu 4.** Dùng `$toLong` trực tiếp cho số Decimal128 `12.99` có tạo ra `1299` cent không?

*Đáp án:* Không. Chuyển trực tiếp thành số nguyên sẽ cắt phần thập phân và cho `12` nếu trong miền hợp lệ. Phải chuyển theo đơn vị: nhân `100`, làm tròn có chủ đích rồi mới chuyển thành Int64.

## 13. Nguyên tắc áp dụng vào hệ thống MongoDB

- **BSON lưu kiểu số thật**: Int32, Int64, Double và Decimal128 có ý nghĩa khác nhau; dùng `$type` để xác nhận.
- **Tiền cần chính xác từ điểm đầu vào**: truyền chuỗi thập phân → BigDecimal/Decimal128, hoặc số nguyên đơn vị nhỏ nhất → Int64. Không kỳ vọng ép kiểu có thể sửa một số đã sai.
- **Độ chính xác và rounding là hợp đồng nghiệp vụ**: khai báo currency, scale, thời điểm làm tròn và chính sách với số âm, thuế, chiết khấu.
- **Chuyển đổi có thể lỗi**: `$convert` giúp xử lý từng document; dữ liệu không hợp lệ cần được nhận diện và điều tra thay vì coi như bằng 0.
- **Ngăn kiểu dữ liệu lẫn lộn**: kiểm soát tầng API/driver, validate schema và theo dõi dữ liệu tồn tại trước khi migration.
- **Đoạn mã tính tiền phải giữ kiểu phù hợp xuyên suốt**: từ client đến backend Java, MongoDB, aggregation và đầu ra báo cáo.

Khi kết hợp kiểu BSON phù hợp, kiểm soát chuyển đổi và quy tắc tiền tệ nhất quán, MongoDB có thể lưu và xử lý các giá trị tài chính một cách rõ ràng, có thể kiểm chứng và phù hợp yêu cầu chính xác của ứng dụng.
