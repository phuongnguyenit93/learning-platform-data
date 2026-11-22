# Kiểu số, độ chính xác và giới hạn giữa các ngôn ngữ

## 1. Vì sao kiểu số là một phần của hợp đồng REST API?

Trong chương **Biểu diễn dữ liệu** của module **INTEGRATION_API_REST**, kiểu số quyết định liệu dữ liệu có giữ nguyên ý nghĩa khi đi qua HTTP, bộ phân tích JSON, mã ứng dụng, cơ sở dữ liệu và SDK phía client hay không. Một request có thể hợp lệ về cú pháp JSON nhưng vẫn tạo ra sai lệch nghiệp vụ nếu client làm tròn mã định danh hoặc server xử lý tiền bằng số dấu phẩy động.

Hãy xét response:

```json
{
  "orderId": 9007199254740993,
  "total": 0.3,
  "quantity": 2
}
```

Một server Java có thể giữ nguyên `orderId` trong `long`. Tuy nhiên, khi JavaScript phân tích response bằng `JSON.parse`, giá trị đó không còn được biểu diễn chính xác bằng `Number`. Số tiền `total` lại có rủi ro khác: phép cộng hoặc nhân tiếp theo có thể bộc lộ sai số nhị phân. Trong khi đó, `quantity` là số đếm nhỏ, thường có thể dùng số nguyên JSON với giới hạn rõ ràng.

Việc tất cả trường đều xuất hiện dưới dạng chữ số không có nghĩa chúng nên dùng cùng một kiểu dữ liệu. Hợp đồng cần nói rõ:

- Trường là số đếm, mã định danh, số tiền, tỷ lệ hay đại lượng đo?
- Miền giá trị, đơn vị và số chữ số thập phân được chấp nhận là gì?
- Giá trị cần chính xác tuyệt đối hay được phép có sai số?
- Làm tròn tại bước nào, theo quy tắc nào?
- Những client và ngôn ngữ nào phải đọc được dữ liệu?

Sau bài này, người học có thể lựa chọn cách biểu diễn số cho REST API, mô tả ràng buộc bằng OpenAPI và triển khai kiểm tra dữ liệu trong Java/Spring hoặc công nghệ tương đương.

## 2. JSON và kiểu số của ngôn ngữ lập trình

### 2.1. JSON không mang đầy đủ kiểu dữ liệu runtime

JSON có loại giá trị `number`, nhưng không gắn nhãn `int32`, `int64`, `BigInteger` hay `BigDecimal` vào từng số. Khái niệm `integer` trong schema bổ sung ràng buộc giá trị nguyên; nó không tạo ra một loại token JSON riêng.

Khi nhận một số, bộ phân tích và kiểu đích quyết định cách lưu nó. Một DTO Java khai báo `long` khác với DTO khai báo `double`; một client JavaScript dùng `JSON.parse` thông thường lại đọc số JSON vào `Number`. Cùng một body có thể giữ nguyên giá trị ở môi trường này và mất độ chính xác ở môi trường khác.

### 2.2. Hợp lệ về cú pháp chưa chắc hợp lệ với hợp đồng

| Biểu diễn | Ý nghĩa với JSON |
| --- | --- |
| `42`, `-12`, `0.5`, `1e3` | Là số JSON hợp lệ |
| `NaN`, `Infinity`, `-Infinity` | Không phải số JSON hợp lệ |
| `+1` | Không cho phép dấu cộng ở đầu số |
| `01` | Không cho phép số nguyên có số 0 đứng đầu như vậy |
| `.5`, `5.` | Thiếu chữ số bắt buộc trước hoặc sau dấu chấm |
| `1,25` | Dấu phẩy không phải dấu thập phân của JSON |

`1e400` hợp lệ về cú pháp, nhưng vượt miền hữu hạn của kiểu IEEE 754 binary64. Vì vậy, cần phân biệt **JSON hợp lệ**, **hợp đồng hợp lệ** và **giá trị có thể biểu diễn trong kiểu đích**.

Dữ liệu trao đổi dùng dấu chấm thập phân, không phụ thuộc locale. Nếu API nhận tiền dưới dạng chuỗi, hợp đồng cũng nên xác định một định dạng duy nhất:

```json
{
  "amount": "1234.50",
  "currency": "USD"
}
```

Không để client tự đoán dấu phân cách hàng nghìn hoặc đơn vị tiền. Giao diện có thể hiển thị dấu phẩy thập phân theo ngôn ngữ người dùng sau khi đọc đúng giá trị và đơn vị.

## 3. Các giới hạn thường gặp giữa các ngôn ngữ

### 3.1. Số nguyên có độ rộng cố định và số nguyên tùy ý

| Kiểu/môi trường | Miền hoặc khả năng biểu diễn | Ý nghĩa với API |
| --- | --- | --- |
| Java `int` | Từ −2³¹ đến 2³¹ − 1 | Phù hợp số đếm nhỏ nếu nghiệp vụ giới hạn rõ |
| Java `long` | Từ −2⁶³ đến 2⁶³ − 1 | Giữ chính xác nhiều số nguyên mà JavaScript `Number` không giữ được |
| Java `BigInteger` | Độ chính xác tùy ý, giới hạn thực tế bởi tài nguyên | Không tự giải quyết khả năng đọc của client |
| JavaScript `Number` | Kiểu binary64; số nguyên an toàn từ −(2⁵³ − 1) đến 2⁵³ − 1 | Cần giới hạn số nguyên JSON hoặc đổi biểu diễn |
| JavaScript `BigInt` | Số nguyên có độ chính xác tùy ý, giới hạn thực tế bởi tài nguyên | Không phải loại số JSON riêng; cần quy ước serialize/parse |
| Python `int` | Số nguyên có độ chính xác tùy ý, giới hạn thực tế bởi tài nguyên | Client Python giữ được số lớn không có nghĩa mọi client đều giữ được |
| Python `float` | Thường là binary64 trên môi trường thông dụng | Không thay thế kiểu decimal cho số thập phân cần chính xác |

Các mốc cần nhớ:

```text
Java int tối đa:                  2 147 483 647
Java long tối đa:     9 223 372 036 854 775 807
JS Number an toàn:        9 007 199 254 740 991
```

“Không an toàn” không có nghĩa mọi số nguyên lớn hơn mốc đều sai. Một số giá trị lớn vẫn biểu diễn chính xác. Vấn đề là không còn bảo đảm giữ được **mọi** số nguyên trong khoảng và phân biệt được từng giá trị liên tiếp.

### 3.2. Ví dụ mất mã định danh trên JavaScript

```javascript
const response = JSON.parse('{"orderId":9007199254740993}');

console.log(response.orderId);                       // 9007199254740992
console.log(Number.isSafeInteger(response.orderId)); // false
```

Sau khi `JSON.parse` đã làm mất thông tin, gọi `BigInt(response.orderId)` không khôi phục được mã ban đầu. Việc đổi sang chuỗi cũng chỉ tạo ra chuỗi của giá trị đã sai.

Hợp đồng nên gửi mã định danh dưới dạng chuỗi ngay từ đầu:

```json
{
  "orderId": "9007199254740993"
}
```

```javascript
const response = JSON.parse('{"orderId":"9007199254740993"}');
console.log(response.orderId); // Giữ nguyên từng chữ số

// Chỉ chuyển khi có nhu cầu tính toán số nguyên thực sự.
const numericId = BigInt(response.orderId);
```

Theo hành vi mặc định, `JSON.stringify` không serialize được giá trị `BigInt` và sẽ báo lỗi nếu không có xử lý tùy chỉnh. Nếu cần trao đổi số nguyên lớn dùng để tính toán, hãy thống nhất cách chuyển thành chuỗi và cách parse lại. Với ID chỉ dùng để tham chiếu resource, giữ dạng chuỗi thường đơn giản hơn.

### 3.3. Decimal không đồng nghĩa với không có giới hạn

Java có `BigDecimal`, Python có `decimal.Decimal`, còn JavaScript có thể dùng thư viện decimal. Các công cụ này hỗ trợ số thập phân chính xác theo mô hình riêng, nhưng vẫn cần cấu hình và ràng buộc phép tính.

Ví dụ, Python `Decimal` có context ảnh hưởng đến precision và làm tròn của phép toán. Java `BigDecimal` có thể dùng `MathContext` cho precision tính toán. Việc chọn kiểu decimal không tự quy định số chữ số được phép nhận, miền nghiệp vụ hoặc chính sách làm tròn của API.

## 4. Số dấu phẩy động và sai số nhị phân

### 4.1. Vì sao phép cộng đơn giản cho kết quả bất ngờ?

Các giá trị như `0.1` không có biểu diễn nhị phân hữu hạn. Khi lưu vào binary64, runtime dùng giá trị gần nhất có thể biểu diễn:

```javascript
console.log(0.1 + 0.2);         // 0.30000000000000004
console.log(0.1 + 0.2 === 0.3); // false
```

Hiện tượng tương tự xuất hiện khi dùng Java `double`. Đây là đặc tính biểu diễn; không thể sửa triệt để bằng cách thêm vài chữ số 0 trong JSON.

Khả năng chứa số rất lớn và khả năng giữ chính xác phần thập phân là hai thuộc tính khác nhau. Binary64 có miền giá trị rộng nhưng số chữ số có nghĩa hữu hạn. Chuyển sang kiểu có miền rộng hơn không mặc nhiên đáp ứng yêu cầu tiền tệ hoặc đối soát.

### 4.2. Sai số tuyệt đối và tương đối

Với dữ liệu đo lường, sai số nhỏ có thể chấp nhận được. Khi so sánh, có thể dùng cả ngưỡng tuyệt đối lẫn tương đối:

```text
|a − b| ≤ max(absTolerance, relTolerance × max(|a|, |b|))
```

- Ngưỡng tuyệt đối hữu ích gần 0.
- Ngưỡng tương đối hữu ích khi giá trị có độ lớn khác nhau.
- Hai ngưỡng phải xuất phát từ đơn vị và yêu cầu nghiệp vụ.

Không dùng một hằng số rất nhỏ cho mọi đại lượng. Ngưỡng dùng cho nhiệt độ không mặc nhiên phù hợp với khoảng cách hoặc tỷ giá. Cũng không dùng so sánh gần đúng để xác nhận mã định danh, số lượng nguyên hay số tiền phải chính xác.

### 4.3. Các trường hợp đặc biệt cần quyết định

| Trường hợp | Rủi ro | Hướng thiết kế |
| --- | --- | --- |
| Overflow | Kết quả vượt miền hữu hạn hoặc vượt kiểu đích | Từ chối hoặc xử lý theo quy tắc đã công bố |
| Underflow | Giá trị quá nhỏ bị làm tròn về 0 hoặc mất độ chính xác tương đối | Xác định miền đầu vào và cách biểu diễn phù hợp |
| `NaN`/vô cực | Có trong một số kiểu runtime nhưng không có trong JSON chuẩn | Kiểm tra giá trị hữu hạn trước khi xuất JSON |
| `-0` | Một số runtime phân biệt với `0` trong một số phép toán | Chuẩn hóa nếu nghiệp vụ không phân biệt |
| Ký hiệu mũ | Parser hoặc validation tự viết có thể xử lý khác nhau | Công bố cho phép hay cấm theo từng trường |

Đối với số đo như nhiệt độ hoặc tọa độ, số JSON dấu phẩy động có thể phù hợp nếu hợp đồng nêu rõ đơn vị, miền và sai số cho phép. Đối với giá trị thanh toán, cần chính sách chính xác chặt chẽ hơn.

## 5. Thiết kế số tiền và số thập phân chính xác

### 5.1. Lựa chọn A: chuỗi thập phân kèm đơn vị

```json
{
  "amount": "1234.50",
  "currency": "USD"
}
```

Ưu điểm là giữ được các chữ số trên đường truyền, kể cả client mặc định chỉ có binary64. Tuy nhiên, chuỗi không tự có ý nghĩa số học. Cần định nghĩa:

- Cho phép dấu âm hay không.
- Số chữ số tối đa trước và sau dấu chấm.
- Có cho phép ký hiệu mũ, khoảng trắng hoặc dấu cộng không.
- Miền giá trị và đơn vị tiền.
- `"12.5"` và `"12.50"` có cùng được chấp nhận không.
- Quy tắc làm tròn khi kết quả phép tính có nhiều chữ số hơn quy định.

Nếu quy ước yêu cầu đúng hai chữ số thập phân, server có thể chỉ chấp nhận `"12.50"`. Không nên âm thầm nhận `"12.509"` rồi làm tròn trong một API mà client được thông báo là truyền số tiền chính xác.

### 5.2. Lựa chọn B: số nguyên theo đơn vị nhỏ nhất

```json
{
  "amountMinor": 123450,
  "currency": "USD",
  "scale": 2
}
```

Công thức giải thích biểu diễn trên:

```text
amount = amountMinor × 10^(−scale)
       = 123450 × 10^(−2)
       = 1234.50
```

Cách này thuận tiện cho phép cộng, trừ và đối soát, nhưng vẫn cần giải quyết giới hạn số nguyên của client. Nếu `amountMinor` có thể vượt `Number.MAX_SAFE_INTEGER`, hãy truyền nó bằng chuỗi hoặc đặt miền nhỏ hơn và kiểm tra miền đó.

Không mặc định mọi tiền tệ hay mọi nghiệp vụ đều có `scale = 2`. Hệ thống có thể cần đơn vị nhỏ hơn cho đơn giá, tỷ giá hoặc tính trung gian. `scale` có thể là quy tắc cố định theo loại dữ liệu thay vì trường do client tự chọn. Nếu nhận `scale` từ client, server phải kiểm tra nó theo hợp đồng, không để client thay đổi ý nghĩa số tiền tùy ý.

### 5.3. Lựa chọn C: số JSON với thư viện decimal

Một server dùng `BigDecimal` có thể phát JSON như sau:

```json
{
  "amount": 1234.50
}
```

Server có thể giữ chính xác giá trị, nhưng JavaScript thông thường sẽ đọc thành `Number`. Vì vậy, lựa chọn này chỉ phù hợp khi các bên đã thống nhất bộ phân tích decimal và cách ánh xạ kiểu tương ứng, hoặc miền sử dụng chấp nhận đặc tính của client.

Việc đổi DTO server từ `double` sang `BigDecimal` là cần thiết trong nhiều bài toán tiền tệ, nhưng không tự tạo ra bảo đảm chính xác trên mọi client.

### 5.4. Precision và scale là hai ràng buộc khác nhau

Với `1234.50` trong `BigDecimal`:

- `precision` là 6: số chữ số trong phần số nguyên không chia tỉ lệ, ở đây là `123450`.
- `scale` là 2: giá trị tương ứng với `123450 × 10^−2`.

Các dạng `12.5` và `12.50` có cùng giá trị số nhưng khác scale. Cơ sở dữ liệu kiểu `DECIMAL(p, s)` cũng thường dùng precision và scale, nhưng hành vi khi chèn dữ liệu vượt giới hạn phụ thuộc hệ quản trị và cấu hình. API nên kiểm tra trước khi lưu, không dựa vào việc cơ sở dữ liệu sẽ tự làm tròn hoặc từ chối theo đúng mong muốn.

Trong `BigDecimal`, scale cũng có thể âm, chẳng hạn giá trị tạo từ `"1E+3"`. Vì thế, chỉ kiểm tra `scale <= 2` không đủ để áp đặt định dạng “đúng hai chữ số sau dấu chấm”. Nếu định dạng văn bản có ý nghĩa trong hợp đồng, hãy kiểm tra chuỗi đầu vào hoặc dùng deserializer có ràng buộc rõ ràng.

## 6. Java: dùng `BigDecimal` đúng mục đích

### 6.1. Khởi tạo từ dữ liệu thập phân chính xác

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);

System.out.println(sum.toPlainString()); // 0.3

BigDecimal fromBinary = new BigDecimal(0.1);
System.out.println(fromBinary.toPlainString());
// Chứa phần thập phân dài do chuyển chính xác giá trị double đã xấp xỉ.
```

Dùng constructor nhận chuỗi khi đầu vào gốc là số thập phân dạng văn bản. `BigDecimal.valueOf(double)` thường thuận tiện hơn constructor nhận `double` vì dựa trên biểu diễn chuỗi chuẩn của `double`, nhưng không khôi phục được thông tin đã mất trước đó:

```java
BigDecimal preservedError = BigDecimal.valueOf(0.1 + 0.2);
System.out.println(preservedError.toPlainString());
// 0.30000000000000004
```

Vì vậy, đừng parse số tiền thành `double` rồi mới chuyển sang `BigDecimal`.

### 6.2. Phép chia phải có chính sách làm tròn

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal total = new BigDecimal("10.00");
BigDecimal share = total.divide(
    new BigDecimal("3"),
    2,
    RoundingMode.HALF_EVEN
);

System.out.println(share.toPlainString()); // 3.33
```

`total.divide(new BigDecimal("3"))` không có kết quả thập phân hữu hạn nên có thể ném `ArithmeticException`. Hệ thống phải lựa chọn scale và chế độ làm tròn cho nghiệp vụ cụ thể.

| Chế độ | Ý nghĩa khái quát |
| --- | --- |
| `HALF_UP` | Gần nhất; nếu đúng giữa hai giá trị thì làm tròn ra xa 0 |
| `HALF_EVEN` | Gần nhất; nếu đúng giữa hai giá trị thì chọn chữ số giữ lại chẵn |
| `DOWN` | Bỏ phần dư theo hướng về 0 |
| `FLOOR` | Làm tròn về phía âm vô cực |
| `UNNECESSARY` | Không cho phép mất chữ số có nghĩa; cần làm tròn thì báo lỗi |

Với số âm, `DOWN` và `FLOOR` cho kết quả khác nhau. Không dùng tên gọi đời thường như “làm tròn xuống” mà không xác định chế độ cụ thể.

Nếu chia `10.00` thành ba phần đều `3.33`, tổng chỉ là `9.99`. Phần dư `0.01` phải được phân bổ theo một quy tắc xác định, ví dụ cấp cho phần đầu tiên theo thứ tự cố định. Quy tắc phân bổ là một phần của nghiệp vụ; chọn `BigDecimal` chưa giải quyết hết bài toán.

### 6.3. So sánh giá trị và so sánh cả scale

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));    // false
System.out.println(x.compareTo(y)); // 0
```

`equals` của `BigDecimal` xét cả giá trị và scale; `compareTo` so sánh giá trị số. Khi kiểm tra ngưỡng giá hoặc số dư, thường dùng `compareTo`. Khi dùng làm khóa `HashMap` hoặc phần tử `HashSet`, phải cân nhắc sự khác biệt này và chọn cách chuẩn hóa nhất quán nếu cần.

Để xuất chuỗi không có ký hiệu mũ, có thể dùng `toPlainString()`. Tuy nhiên, phương thức này không tự thêm đủ số 0 theo hợp đồng. Nếu hợp đồng yêu cầu hai chữ số thập phân, cần đặt scale phù hợp trước khi xuất.

### 6.4. Tránh overflow ở phép tính số nguyên trung gian

```java
long unitMinor = 8_000_000_000_000_000_000L;
long quantity = 2L;

long totalMinor = Math.multiplyExact(unitMinor, quantity);
// Ném ArithmeticException vì kết quả vượt miền long.
```

Một giá trị đầu vào có thể vừa `long` nhưng kết quả nhân lại không vừa. Có thể dùng phép toán kiểm tra overflow hoặc chuyển sang `BigInteger`/`BigDecimal` theo mô hình dữ liệu. Không ép kiểu hẹp từ `long` xuống `int` để làm mất phần vượt miền mà không kiểm tra.

Khi chuyển `BigDecimal` sang số nguyên mà yêu cầu tuyệt đối chính xác, các phương thức như `longValueExact()` giúp từ chối phần lẻ hoặc giá trị vượt miền. `longValue()` không cung cấp bảo đảm tương tự.

## 7. Thiết kế một hợp đồng OpenAPI rõ ràng

Giả sử API tạo đơn hàng áp dụng các quy tắc sau:

- Mã sản phẩm là chuỗi chữ số, tối đa 19 ký tự, không có số 0 đứng đầu.
- Số lượng là số nguyên từ 1 đến 1.000.
- Đơn giá là chuỗi thập phân không âm, tối đa 9 chữ số trước dấu chấm và đúng 2 chữ số sau dấu chấm.
- Ví dụ chỉ nhận `USD` và quy định đơn giá có scale bằng 2.
- Server tính tổng bằng phép toán decimal; không nhận tổng do client tự tính làm căn cứ thanh toán.

Phần schema tương ứng trong OpenAPI 3.1:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths: {}
components:
  schemas:
    CreateOrderRequest:
      type: object
      additionalProperties: false
      required:
        - productId
        - quantity
        - unitPrice
        - currency
      properties:
        productId:
          type: string
          minLength: 1
          maxLength: 19
          pattern: '^[1-9][0-9]{0,18}$'
          description: Mã định danh không dùng cho phép toán số học.
          example: '9007199254740993'
        quantity:
          type: integer
          format: int32
          minimum: 1
          maximum: 1000
          example: 3
        unitPrice:
          type: string
          minLength: 4
          maxLength: 12
          pattern: '^(0|[1-9][0-9]{0,8})\.[0-9]{2}$'
          description: Đơn giá từ 0.00 đến 999999999.99, đúng hai chữ số thập phân.
          example: '19.90'
        currency:
          type: string
          enum: [USD]
          example: USD
```

`productId` ở đây là mã chữ số có tối đa 19 ký tự, không phải lời cam kết rằng mọi mã đều chuyển được sang Java `long`. Nếu hệ thống chỉ cho phép miền dương của `long`, phải thêm kiểm tra giới hạn số tương ứng hoặc dùng loại mã định danh khác nhất quán từ đầu.

Các giới hạn chiều dài hỗ trợ kiểm soát tài nguyên và làm rõ hợp đồng. Trong YAML dùng chuỗi nháy đơn, `\.` trong pattern trên biểu diễn dấu chấm literal của biểu thức chính quy.

Các annotation `format: int32` hay `format: int64` không mở rộng khả năng biểu diễn của JavaScript. Mức thực thi `format` và ánh xạ kiểu phụ thuộc công cụ; cần có `minimum`, `maximum` và kiểm tra runtime tương ứng. Một schema `integer/int64` cho ID lớn vẫn có thể sinh SDK TypeScript dùng `number` và gây mất dữ liệu.

`additionalProperties: false` cũng cần được thực thi bởi lớp kiểm tra schema hoặc cấu hình bind JSON. Khai báo trong OpenAPI không tự thay đổi cách Spring xử lý thuộc tính lạ.

## 8. Ví dụ Java/Spring: nhận chuỗi, kiểm tra và tính bằng decimal

### 8.1. DTO bảo vệ định dạng và miền cơ bản

Ví dụ sau dùng Jakarta Bean Validation, thích hợp với dự án Spring sử dụng namespace `jakarta.validation`. Dự án cần có thành phần Bean Validation và cấu hình MVC tương ứng.

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
    @NotNull
    @Size(min = 1, max = 19)
    @Pattern(regexp = "[1-9][0-9]{0,18}")
    String productId,

    @NotNull
    @Min(1)
    @Max(1000)
    Integer quantity,

    @NotNull
    @Size(min = 4, max = 12)
    @Pattern(regexp = "(0|[1-9][0-9]{0,8})\\.[0-9]{2}")
    String unitPrice,

    @NotNull
    @Pattern(regexp = "USD")
    String currency
) {}
```

Dùng `Integer` thay cho `int` ở đây giúp phân biệt trường thiếu hoặc `null` với số 0. `@NotNull` xử lý trường thiếu/null; `@Min` và `@Max` xử lý miền giá trị. Các ràng buộc `@Pattern` kiểm tra toàn bộ chuỗi khi dùng Bean Validation.

DTO này được kiểm tra khi controller nhận `@Valid @RequestBody CreateOrderRequest request`. Tuy nhiên, annotation không tự kiểm soát mọi hành vi ép kiểu của JSON binder. Một cấu hình có thể chuyển số JSON sang `String`, hoặc chuyển số có phần lẻ sang số nguyên trước khi Bean Validation chạy.

Nếu hợp đồng đòi hỏi token `unitPrice` phải là chuỗi và `quantity` phải là số nguyên, cần cấu hình từ chối coercion phù hợp với phiên bản thư viện hoặc dùng deserializer/lớp kiểm tra schema có kiểm tra loại token. Kiểm thử phải bao gồm cả `"quantity": 1.5`, `"quantity": "3"` và `"unitPrice": 19.90` để xác nhận hệ thống thực sự từ chối những dạng bị cấm.

### 8.2. Tính tổng mà không đi qua `double`

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class OrderAmounts {
    private OrderAmounts() {}

    public static String totalOf(CreateOrderRequest request) {
        // Điều kiện trước: request đã qua kiểm tra định dạng và miền.
        BigDecimal unitPrice = new BigDecimal(request.unitPrice());
        BigDecimal quantity = BigDecimal.valueOf(request.quantity().longValue());

        BigDecimal total = unitPrice.multiply(quantity)
            .setScale(2, RoundingMode.UNNECESSARY);

        return total.toPlainString();
    }
}
```

Với đơn giá có đúng hai chữ số thập phân và số lượng nguyên, phép nhân không đòi hỏi bỏ phần lẻ vượt scale 2. `UNNECESSARY` thể hiện kỳ vọng đó: nếu một thay đổi trong luồng tính toán làm phát sinh nhu cầu làm tròn, hệ thống phải xử lý rõ ràng thay vì tự âm thầm đổi số tiền.

Request:

```json
{
  "productId": "9007199254740993",
  "quantity": 3,
  "unitPrice": "19.90",
  "currency": "USD"
}
```

Response minh họa khi tài nguyên đơn hàng được tạo:

```http
HTTP/1.1 201 Created
Location: /orders/ord_7f3a
Content-Type: application/json

{
  "id": "ord_7f3a",
  "productId": "9007199254740993",
  "quantity": 3,
  "unitPrice": "19.90",
  "total": "59.70",
  "currency": "USD"
}
```

Trong API bán hàng thực tế, server thường tra đơn giá từ nguồn đáng tin cậy và kiểm tra quyền thay đổi giá. Kiểm tra kiểu số chỉ bảo đảm dữ liệu có dạng và miền phù hợp; không thay thế xác thực, phân quyền hoặc quy tắc xác định giá.

### 8.3. Đồng bộ giới hạn của giá trị tính ra

Với đơn giá tối đa `999999999.99` và số lượng tối đa `1000`, tổng có thể đạt `999999999990.00`. Tổng cần tối đa 12 chữ số trước dấu chấm và 2 chữ số sau dấu chấm, tương ứng precision 14 ở giá trị biên.

Vì vậy, không tái sử dụng mù quáng schema hoặc cột cơ sở dữ liệu của `unitPrice` cho `total`. Response, kiểu lưu trữ và giới hạn nghiệp vụ phải chứa được kết quả tính ra. Nếu hệ thống đặt trần tổng đơn hàng thấp hơn, hãy kiểm tra trần đó trước khi lưu.

Ví dụ này chưa quyết định thời điểm tính thuế, khuyến mại hoặc quy tắc phân bổ phần dư. Khi bổ sung chúng, cần công bố rõ độ chính xác trung gian và thời điểm làm tròn.

## 9. Báo lỗi số liệu để client sửa được request

Lỗi cần phân biệt được loại token sai, định dạng sai, vượt miền và kết quả tính toán không hợp lệ. Hợp đồng có thể chọn `400 Bad Request` cho payload không đọc được hoặc sai kiểu, và `422 Unprocessable Content` cho payload đọc được nhưng vi phạm quy tắc nghiệp vụ. Đây là chính sách của ví dụ; dự án phải ánh xạ lỗi nhất quán và mô tả trong tài liệu API.

Ví dụ `quantity` bằng 0:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/numeric-validation",
  "title": "Giá trị số không hợp lệ",
  "status": 422,
  "detail": "Một hoặc nhiều trường vượt giới hạn cho phép.",
  "errors": [
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "quantity phải là số nguyên từ 1 đến 1000."
    }
  ]
}
```

`errors` là trường mở rộng do API quy định. Client nên dựa vào mã lỗi ổn định và tên trường; không phân tích chuỗi thông báo tiếng Việt để suy ra loại lỗi.

Nếu dùng Spring với `@Valid`, cần lớp xử lý ngoại lệ để tạo cấu trúc trên và thực hiện chính sách mã trạng thái đã chọn; DTO và Bean Validation tự thân không tự trả đúng response minh họa.

Một số quy tắc vận hành:

- Không để overflow hoặc `ArithmeticException` biến thành lỗi 500 khó hiểu khi nguyên nhân là dữ liệu ngoài miền được phép.
- Không tự đổi `"1,25"` thành `"1.25"` nếu hợp đồng không cho phép.
- Không biến số sai định dạng thành 0, vì 0 có thể là giá trị nghiệp vụ hợp lệ.
- Giới hạn kích thước request và độ dài token số ở lớp tiếp nhận; không đợi đến khi đã parse một giá trị cực dài mới áp dụng Bean Validation.
- Khi ghi log lỗi, chỉ ghi lượng dữ liệu cần thiết, tránh lặp nguyên payload quá lớn hoặc thông tin nhạy cảm.

## 10. Tính nhất quán với cache, idempotency và thay đổi hợp đồng

### 10.1. Cùng giá trị số chưa chắc cùng byte

Các tài liệu JSON sau có thể biểu đạt cùng giá trị số nhưng khác byte:

```json
{"amount":1}
```

```json
{"amount":1.0}
```

```json
{"amount":1e0}
```

Nếu tạo ETag hoặc hash từ body thô, chúng có thể tạo ra các kết quả khác nhau. Nếu hệ thống cần nhận biết request lặp lại dựa trên nội dung, cần quyết định so sánh byte hay so sánh dữ liệu đã chuẩn hóa.

Với chuỗi tiền tệ, `"1.0"` và `"1.00"` là hai chuỗi khác nhau. Hợp đồng yêu cầu đúng hai chữ số thập phân giúp tạo một dạng biểu diễn ổn định cho miền ví dụ, nhưng không thay thế cơ chế canonicalization cho toàn bộ JSON nếu hệ thống cần chữ ký hoặc hash chuẩn hóa.

Một luồng dùng `Idempotency-Key` có thể lưu dấu vân tay của payload đã chuẩn hóa theo hợp đồng. Khi cùng khóa được dùng lại, server đối chiếu dữ liệu tương ứng. Chuẩn hóa không được xóa những khác biệt có ý nghĩa nghiệp vụ như đơn vị tiền hoặc dấu của giá trị. Client cũng cần giữ được ID và số tiền nguyên vẹn khi thử lại request.

### 10.2. Đổi kiểu trường là thay đổi cần quản lý

Chuyển từ:

```json
{"id":123456789}
```

sang:

```json
{"id":"123456789"}
```

có thể làm hỏng client đã ràng buộc `id` là number. Đây là thay đổi hợp đồng, dù con người nhìn thấy cùng một dãy chữ số.

Các cách triển khai có thể gồm thêm trường mới trong thời gian chuyển tiếp, nâng phiên bản API hoặc phát hành SDK mới với thời hạn tương thích rõ ràng. Không thay đổi kiểu trên production rồi mặc định mọi client sẽ tự ép kiểu đúng.

## 11. Ma trận kiểm thử hợp đồng số

Kiểm thử nên bao phủ cả nội dung JSON thô, dữ liệu sau parse, phép tính và response sau serialize. So sánh lại hai đối tượng đã cùng bị làm tròn không đủ để phát hiện mất dữ liệu.

| Nhóm | Dữ liệu cần kiểm tra | Kết quả mong muốn |
| --- | --- | --- |
| ID lớn | `"9007199254740993"` | Giữ nguyên từng chữ số khi đọc và gửi lại |
| Số lượng hợp lệ | `1`, `1000` | Chấp nhận đúng hai giá trị biên |
| Ngoài miền | `0`, `1001`, số âm | Từ chối bằng mã lỗi đã quy định |
| Sai loại token | `"3"`, `1.5`, `true` cho quantity | Không bị âm thầm ép thành số lượng hợp lệ |
| Giá hợp lệ | `"0.00"`, `"19.90"`, `"999999999.99"` | Chấp nhận và giữ định dạng hai chữ số |
| Giá sai định dạng | `"19.9"`, `"019.90"`, `"1,20"`, `"1e2"` | Từ chối theo pattern của hợp đồng |
| Giá sai loại | `19.90` thay cho `"19.90"` | Từ chối khi hợp đồng bắt buộc chuỗi |
| Thiếu/null | Bỏ quantity hoặc gửi `null` | Phân biệt với 0 và trả lỗi rõ ràng |
| Tổng cực đại | Giá tối đa nhân số lượng tối đa | Không tràn cột lưu trữ/schema response |
| Giới hạn tài nguyên | Chuỗi số hoặc token số rất dài | Bị chặn theo giới hạn request/parser |
| Chia/làm tròn | `10.00 / 3`, điểm giữa, số âm | Theo đúng scale, chế độ và quy tắc phân bổ |
| Client khác nhau | Java, JavaScript và ngôn ngữ thực tế đang hỗ trợ | Cùng hiểu hợp đồng và giữ thông tin cần thiết |

Một phép kiểm tra nhỏ phía JavaScript cho hợp đồng ID và tiền dạng chuỗi:

```javascript
const raw = `{
  "id": "9007199254740993",
  "unitPrice": "19.90",
  "quantity": 3,
  "total": "59.70",
  "currency": "USD"
}`;

const order = JSON.parse(raw);

if (order.id !== "9007199254740993") {
  throw new Error("ID bị thay đổi");
}
if (typeof order.total !== "string" || order.total !== "59.70") {
  throw new Error("Số tiền không giữ đúng hợp đồng");
}
```

Không chuyển `order.total` sang `Number` để tính toán tiền chính xác. Hãy dùng thư viện decimal phù hợp hoặc giữ phép tính trên server theo hợp đồng.

## 12. Chọn biểu diễn theo ý nghĩa của trường

| Dữ liệu | Biểu diễn thường phù hợp | Điều cần công bố |
| --- | --- | --- |
| Số lượng, kích thước trang | Số nguyên JSON trong miền nhỏ | Minimum, maximum, giá trị mặc định nếu có |
| ID có thể lớn hoặc không dùng để tính | Chuỗi | Định dạng, chiều dài, phân biệt hoa/thường nếu liên quan |
| Tiền cần chính xác | Chuỗi decimal hoặc số nguyên đơn vị nhỏ nhất | Tiền tệ, scale, giới hạn, làm tròn |
| Tỷ lệ cần tính chính xác | Chuỗi decimal với precision phù hợp | Ý nghĩa 0.05 hay 5, scale, miền |
| Đại lượng đo có sai số | Số JSON với kiểu dấu phẩy động | Đơn vị, miền, sai số cho phép, giá trị hữu hạn |
| Số nguyên lớn dùng để tính | Chuỗi số nguyên hoặc parser chuyên biệt đã thống nhất | Miền, giới hạn tài nguyên, cách parse/serialize |

Không chỉ chọn kiểu từ tên trường. Ví dụ `rate = 5` có thể là 5%, hệ số 5 lần hoặc 5 đơn vị cơ sở; kiểu số không tự mô tả đơn vị. Có thể dùng tên trường như `discountPercent`, `ratio` hoặc một object có đơn vị rõ ràng theo quy ước của API.

Để áp dụng vào một endpoint, người học nên thực hiện theo thứ tự:

1. Ghi ý nghĩa và đơn vị của từng trường số.
2. Xác định miền giá trị cùng yêu cầu chính xác, kể cả kết quả trung gian.
3. Chọn biểu diễn trên đường truyền phù hợp với client cần hỗ trợ.
4. Mô tả trong OpenAPI và áp đặt cùng ràng buộc ở runtime.
5. Quy định làm tròn, lỗi và hình thức serialize.
6. Kiểm tra dữ liệu qua toàn bộ vòng nhận → tính → lưu → trả → client đọc lại.

## 13. Bài tập thực hành

### Bài tập 1: sửa hợp đồng gây mất thông tin

API hiện tại trả:

```json
{
  "accountId": 9007199254740993,
  "balance": 1250000.10,
  "interestRate": 0.05
}
```

Hãy thiết kế lại sao cho client trình duyệt đọc được ID và số dư chính xác. Nêu rõ đơn vị tiền, ý nghĩa của `interestRate`, số chữ số được chấp nhận và chính sách làm tròn tiền lãi. Không chỉ đổi kiểu Java; hãy viết lại cả JSON và schema của các trường đã đổi.

Gợi ý: ID có thể là chuỗi, số dư có thể là chuỗi decimal kèm tiền tệ, còn lãi suất cần quy định `0.05` là tỷ lệ 5% nếu đó là ý nghĩa mong muốn. Số chữ số của lãi suất không nhất thiết giống số chữ số của số tiền.

### Bài tập 2: chỉ ra bước làm mất dữ liệu

Một server dùng `BigDecimal` chính xác, trả `amount` dạng number. Client JavaScript dùng `JSON.parse`, sau đó chuyển kết quả sang thư viện decimal.

Hãy chỉ ra vì sao việc dùng thư viện decimal ở cuối chưa bảo đảm khôi phục được dữ liệu gốc. Đề xuất thay đổi biểu diễn hoặc parser để tránh đi qua giá trị `Number` đã bị làm tròn.

### Bài tập 3: kiểm tra giới hạn kết quả

Với `unitPrice` tối đa `999999999.99` và `quantity` tối đa `1000`:

1. Tính tổng lớn nhất.
2. Chọn giới hạn schema response và precision/scale lưu trữ đủ chứa tổng.
3. Viết trường hợp kiểm tra ngay tại giá trị biên và ngay ngoài miền.
4. Bổ sung phép tính thuế làm phát sinh chữ số thập phân thứ ba, rồi xác định rõ bước làm tròn và trường hợp điểm giữa.

Một hợp đồng số tốt giữ được ý nghĩa dữ liệu qua từng ranh giới công nghệ, đồng thời cho người dùng API biết chính xác giá trị nào được chấp nhận và kết quả nào có thể dự đoán được.
