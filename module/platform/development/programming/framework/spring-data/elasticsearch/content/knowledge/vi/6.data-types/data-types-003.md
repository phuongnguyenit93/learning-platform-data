# Kiểu số nguyên, số thực, scaled_float và độ chính xác

Elasticsearch cung cấp nhiều kiểu dữ liệu số để lưu trữ, lọc, sắp xếp và tổng hợp các giá trị như số lượng, giá tiền, điểm đánh giá, trọng lượng hoặc tọa độ. Chọn kiểu số cần dựa trên miền giá trị, độ chính xác cần giữ và phép toán mà ứng dụng thực hiện. Một trường chứa số lượng hàng tồn kho có yêu cầu khác với trường chứa giá tiền hoặc phép đo khoa học.

Trong Spring Data Elasticsearch, kiểu số được khai báo trong mapping của document bằng `@Field`. Kiểu Java của thuộc tính và kiểu Elasticsearch cần được chọn nhất quán. Nếu chỉ dựa vào dynamic mapping, Elasticsearch có thể tự suy luận kiểu từ document đầu tiên; lựa chọn đó có thể không phù hợp với miền dữ liệu hoặc độ chính xác mà nghiệp vụ cần.

## 1. Các kiểu số trong Elasticsearch

Elasticsearch có các kiểu số nguyên, số thực dấu phẩy động và `scaled_float`.

| Kiểu Elasticsearch | Dữ liệu | Miền hoặc độ chính xác đặc trưng | Trường hợp sử dụng |
|---|---|---|---|
| `byte` | Số nguyên có dấu 8 bit | -128 đến 127 | Cờ số nhỏ, cấp độ giới hạn |
| `short` | Số nguyên có dấu 16 bit | -32.768 đến 32.767 | Số nguyên nhỏ có miền đã biết |
| `integer` | Số nguyên có dấu 32 bit | -2.147.483.648 đến 2.147.483.647 | Số lượng hoặc thứ tự trong miền vừa |
| `long` | Số nguyên có dấu 64 bit | -2^63 đến 2^63 - 1 | Bộ đếm lớn, thời gian dạng epoch, số tiền theo đơn vị nhỏ nhất |
| `unsigned_long` | Số nguyên không dấu 64 bit | 0 đến 2^64 - 1 | Giá trị không âm cần miền lớn hơn `long` |
| `half_float` | Số thực IEEE 754 16 bit | Độ chính xác khoảng 3 chữ số có nghĩa | Dữ liệu xấp xỉ khi cần tiết kiệm dung lượng |
| `float` | Số thực IEEE 754 32 bit | Khoảng 7 chữ số có nghĩa | Đo lường xấp xỉ, giá trị không cần độ chính xác cao |
| `double` | Số thực IEEE 754 64 bit | Khoảng 15–16 chữ số có nghĩa | Phép đo, tọa độ hoặc tính toán xấp xỉ cần độ chính xác cao hơn `float` |
| `scaled_float` | Số thực được lượng tử hóa theo hệ số | Độ phân giải do `scaling_factor` quyết định; lưu nội bộ bằng số nguyên 64 bit đã scale | Điểm số, tỷ lệ hoặc giá trị thập phân có số chữ số lẻ cố định |

Các con số về độ chính xác của kiểu dấu phẩy động là xấp xỉ, không phải cam kết rằng mọi giá trị thập phân trong khoảng đó đều biểu diễn chính xác. Kiểu `float` và `double` dùng biểu diễn nhị phân IEEE 754, nên nhiều phân số thập phân như 0,1 không có biểu diễn nhị phân hữu hạn.

### Số nguyên và số thực giải quyết hai nhu cầu khác nhau

Số nguyên phù hợp khi miền dữ liệu là các đơn vị rời rạc và không có phần lẻ, chẳng hạn số lượng sản phẩm, số lượt xem hoặc số lần thử. Số thực phù hợp khi dữ liệu có phần lẻ và ứng dụng chấp nhận sai số biểu diễn dấu phẩy động, chẳng hạn nhiệt độ, trọng lượng đo được hoặc tọa độ.

Không nên chọn `double` chỉ vì nó có miền lớn. Nếu dữ liệu là số lượng hàng, việc dùng kiểu số thực cho phép các giá trị như `3.5` xuất hiện dù nghiệp vụ chỉ cho phép số nguyên. Tương tự, không nên dùng `integer` cho một giá trị có thể vượt giới hạn 32 bit.

## 2. Miền giá trị và cách chọn kiểu nguyên

Khi chọn `byte`, `short`, `integer` hoặc `long`, hãy xác định cả giá trị nhỏ nhất, lớn nhất và tốc độ tăng trong suốt vòng đời dữ liệu.

Ví dụ:

- Số lượng hàng trong một kho có thể dùng `integer` nếu giới hạn nghiệp vụ luôn nằm trong miền 32 bit.
- Tổng số lượt xem tích lũy của một nội dung có thể tăng rất lớn, nên `long` thường phù hợp hơn.
- Mã định danh bên ngoài, số điện thoại, mã bưu chính hoặc SKU thường nên là `keyword`, dù chúng chỉ chứa chữ số. Chúng là định danh để so khớp, không phải đại lượng để cộng trừ.
- Giá tiền lưu theo đơn vị nhỏ nhất, ví dụ đồng hoặc xu, có thể dùng `long` nếu tổng giá trị không vượt miền 64 bit.

### Chọn kiểu nhỏ nhất hay kiểu đủ rộng?

Các kiểu nhỏ hơn có thể giúp giảm dung lượng trong một số trường hợp, nhưng không nên tối ưu quá sớm. `byte` và `short` có giới hạn hẹp; một giá trị vượt miền sẽ gây lỗi khi lập chỉ mục trừ khi hệ thống có chính sách ép kiểu hoặc bỏ qua lỗi. Nếu nghiệp vụ có khả năng mở rộng, dùng `integer` hoặc `long` thường dễ bảo trì hơn.

Elasticsearch không biến `integer` thành `long` một cách tự động chỉ vì một giá trị vượt giới hạn. Mapping đã khai báo sẽ quyết định miền hợp lệ. Hãy kiểm tra giới hạn ở tầng ứng dụng trước khi gửi document để lỗi được phát hiện với thông báo phù hợp.

### `unsigned_long`

`unsigned_long` biểu diễn số nguyên không âm trong miền 64 bit không dấu, từ 0 đến 2^64 - 1. Miền này lớn hơn `long` có dấu của Java ở nửa trên. Java không có primitive `unsigned long` tương đương có thể chứa toàn bộ miền đó; nếu ứng dụng cần dùng hết miền, phải chọn biểu diễn như `BigInteger` và xác minh bộ chuyển đổi/serializer cùng client có hỗ trợ đúng cách.

Không dùng `unsigned_long` chỉ vì giá trị luôn dương. Nếu miền nghiệp vụ nằm trong giới hạn `Long.MAX_VALUE`, Java `Long` và Elasticsearch `long` thường đơn giản hơn. Với định danh chỉ dùng để nhận diện, `keyword` thường phù hợp hơn cả hai kiểu số.

## 3. Độ chính xác của `float` và `double`

`float` và `double` lưu số theo chuẩn dấu phẩy động nhị phân. Giá trị thực tế được làm tròn về một số nhị phân có độ chính xác hữu hạn. Điều này có thể tạo ra kết quả khác với cách con người viết số thập phân.

Ví dụ trong Java:

```java
double a = 0.1;
double b = 0.2;

System.out.println(a + b); // thường in 0.30000000000000004
```

Đây không phải lỗi riêng của Elasticsearch. Nó là đặc tính của biểu diễn floating-point. Khi một giá trị `double` được gửi đến Elasticsearch và lập chỉ mục trong trường `double`, sai số biểu diễn có thể tiếp tục xuất hiện trong so sánh, sắp xếp hoặc aggregation.

### `float` hay `double`?

Chọn `float` khi độ chính xác khoảng 7 chữ số có nghĩa đủ cho ứng dụng và muốn giảm kích thước biểu diễn. Chọn `double` khi cần độ chính xác cao hơn, khoảng 15–16 chữ số có nghĩa, hoặc khi thư viện tính toán và mô hình Java vốn dùng `double`.

Ví dụ, nhiệt độ cảm biến có thể không cần độ chính xác tuyệt đối đến nhiều chữ số thập phân. Ngược lại, một phép đo khoa học có thể cần nhiều chữ số có nghĩa hơn. Cần dựa vào sai số cho phép của miền nghiệp vụ, không chỉ dựa vào số chữ số sau dấu phẩy.

### Không dùng floating-point cho phép tính tiền chính xác

Tiền tệ thường cần quy tắc làm tròn rõ ràng và kết quả có thể đối soát. `float` hoặc `double` có thể tạo ra sai số nhị phân và làm các phép cộng trừ tích lũy khó dự đoán. Hãy dùng `BigDecimal` trong logic nghiệp vụ và chọn cách biểu diễn phù hợp khi đưa giá trị sang Elasticsearch.

Một cách thường dùng là chuyển tiền sang đơn vị nhỏ nhất và lưu bằng `long`. Ví dụ, 125.990 đồng được biểu diễn bằng số nguyên 125990 nếu đơn vị lưu là đồng; 12,34 USD được biểu diễn bằng 1234 nếu đơn vị lưu là cent. Khi hiển thị, chuyển ngược bằng scale tương ứng và luôn lưu mã tiền tệ.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MoneyIndexValue {

    private MoneyIndexValue() {}

    public static long toMinorUnits(BigDecimal amount, int scale) {
        return amount
            .movePointRight(scale)
            .setScale(0, RoundingMode.UNNECESSARY)
            .longValueExact();
    }

    public static BigDecimal fromMinorUnits(long minorUnits, int scale) {
        return BigDecimal.valueOf(minorUnits, scale);
    }
}
```

`RoundingMode.UNNECESSARY` làm thao tác thất bại nếu giá trị có nhiều chữ số lẻ hơn scale cho phép. Nếu nghiệp vụ cho phép làm tròn, hãy chọn quy tắc cụ thể như `HALF_UP` hoặc `HALF_EVEN` tại tầng nghiệp vụ và kiểm thử quy tắc đó. Không để việc ép kiểu trong Elasticsearch quyết định quy tắc tiền tệ.

Khi lưu giá trị tiền theo đơn vị nhỏ nhất, nên lưu thêm `currency` dưới dạng `keyword`. Không cộng hoặc so sánh tổng tiền của nhiều loại tiền tệ như thể chúng cùng đơn vị.

## 4. `scaled_float` hoạt động như thế nào?

`scaled_float` là kiểu số thực có hệ số scale do người thiết kế mapping chọn. Elasticsearch nhân giá trị với `scaling_factor`, làm tròn thành số nguyên và lưu phần đã scale bằng biểu diễn số nguyên 64 bit. Khi đọc hoặc tính toán, giá trị được quy đổi lại theo hệ số đó.

Có thể hình dung phép chuyển đổi như sau:

\[
\text{stored} \approx \operatorname{round}(\text{value} \times \text{scaling\_factor})
\]

\[
\text{represented value} = \frac{\text{stored}}{\text{scaling\_factor}}
\]

Ví dụ với `scaling_factor = 100`:

| Giá trị gửi vào | Giá trị sau khi scale/làm tròn | Giá trị biểu diễn lại |
|---:|---:|---:|
| 12,34 | 1234 | 12,34 |
| 12,345 | xấp xỉ 1235 | xấp xỉ 12,35 |
| 8,90 | 890 | 8,90 |
| 4,567 | xấp xỉ 457 | xấp xỉ 4,57 |

Với hệ số 100, độ phân giải là 0,01. Các giá trị có nhiều hơn hai chữ số thập phân có thể bị làm tròn về mức gần nhất 0,01. Do đó, `scaled_float` không lưu mọi số thập phân chính xác tùy ý; nó lượng tử hóa dữ liệu theo độ phân giải đã chọn.

### Chọn `scaling_factor`

Hãy chọn hệ số theo độ phân giải cần giữ:

| `scaling_factor` | Bước giá trị xấp xỉ | Ví dụ |
|---:|---:|---|
| 1 | 1 | Điểm theo số nguyên |
| 10 | 0,1 | Điểm đánh giá có một chữ số thập phân |
| 100 | 0,01 | Tỷ lệ hoặc giá trị có hai chữ số thập phân |
| 1000 | 0,001 | Phép đo cần ba chữ số thập phân |

Hệ số càng lớn thì độ phân giải càng mịn, nhưng giá trị sau khi nhân cũng càng lớn. Vì `scaled_float` dùng miền của số nguyên 64 bit đã scale, hệ số quá lớn có thể làm giá trị vượt miền lưu trữ. Về xấp xỉ, độ lớn tuyệt đối tối đa phụ thuộc vào `Long.MAX_VALUE / scaling_factor`.

### `scaled_float` có chính xác tuyệt đối không?

Không. Nó cho độ phân giải thập phân có thể dự đoán, nhưng vẫn là phép lượng tử hóa có làm tròn. Nếu hệ số là 100, dữ liệu được biểu diễn theo bội số của 0,01. Với dữ liệu nghiệp vụ yêu cầu chính xác theo đơn vị nhỏ nhất và không cho phép làm tròn, hãy dùng số nguyên lưu đơn vị nhỏ nhất hoặc thiết kế một mô hình lưu trữ chính xác khác.

`scaled_float` hữu ích khi cần truy vấn số, lọc khoảng, sắp xếp và aggregation trên dữ liệu có độ phân giải cố định, đồng thời chấp nhận việc làm tròn theo scale. Nó thường phù hợp với điểm đánh giá, tỷ lệ hoặc số đo đã được chuẩn hóa độ chính xác.

## 5. Khai báo kiểu số trong Spring Data Elasticsearch

Spring Data Elasticsearch cho phép khai báo kiểu trường qua `@Field`. Nên khai báo rõ kiểu cho các thuộc tính số quan trọng thay vì phụ thuộc hoàn toàn vào dynamic mapping.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-v1")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Integer)
    private Integer stockQuantity;

    @Field(type = FieldType.Long)
    private Long viewCount;

    @Field(type = FieldType.Float)
    private Float packageWeight;

    @Field(type = FieldType.Double)
    private Double latitude;

    @Field(type = FieldType.Scaled_Float, scalingFactor = 100)
    private Double averageRating;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Keyword)
    private String currency;

    // Constructors, getters and setters
}
```

Các tên enum trong annotation là API của Spring Data Elasticsearch; mapping JSON gửi tới Elasticsearch dùng tên kiểu chữ thường như `integer`, `long`, `float`, `double` và `scaled_float`. Hãy kiểm tra enum và thuộc tính annotation của đúng phiên bản Spring Data trong dự án khi nâng cấp.

`averageRating` dùng `Double` trong ví dụ để minh họa thuộc tính Java được ánh xạ vào `scaled_float`. Nếu dùng `BigDecimal` trong entity, hãy xác nhận converter/serializer của ứng dụng ghi nó thành giá trị JSON số và đọc lại theo quy tắc mong muốn. Đối với tiền tệ cần chính xác, ví dụ dùng `Long` lưu đơn vị nhỏ nhất để tránh nhầm lẫn giữa độ chính xác Java và độ phân giải của mapping.

### Mapping JSON tương ứng

Một mapping tương ứng có thể có dạng:

```json
{
  "mappings": {
    "properties": {
      "stockQuantity": { "type": "integer" },
      "viewCount": { "type": "long" },
      "packageWeight": { "type": "float" },
      "latitude": { "type": "double" },
      "averageRating": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "priceMinorUnits": { "type": "long" },
      "currency": { "type": "keyword" }
    }
  }
}
```

Mapping này cần được tạo trước khi index dữ liệu đầu tiên nếu ứng dụng muốn kiểm soát kiểu trường. Có thể dùng annotation, index operations hoặc một quy trình quản lý index riêng để tạo mapping; tránh để một document đầu tiên vô tình quyết định kiểu dữ liệu.

## 6. Dynamic mapping và nguy cơ chọn sai kiểu

Nếu một field chưa có mapping, Elasticsearch có thể tự suy luận kiểu dựa trên giá trị đầu tiên nhận được. Ví dụ, một trường số có thể được tạo thành kiểu số nguyên hoặc số thực dựa trên JSON được gửi. Kiểu đã được tạo sẽ áp dụng cho các document tiếp theo.

Điều này có thể gây vấn đề nếu document đầu tiên không đại diện cho dữ liệu về sau. Chẳng hạn, một trường `rating` ban đầu chỉ nhận `5`, nên được suy luận là số nguyên; sau đó ứng dụng gửi `4.5` và gặp xung đột kiểu hoặc hành vi ép kiểu không mong muốn.

Với trường quan trọng, hãy tạo mapping tường minh:

- `stockQuantity`: `integer` nếu giới hạn đã rõ.
- `viewCount`: `long` nếu bộ đếm có thể tăng lớn.
- `rating`: `scaled_float` với scale phù hợp nếu chỉ cần một số chữ số thập phân cố định.
- `priceMinorUnits`: `long` nếu lưu tiền theo đơn vị nhỏ nhất.
- `sku`, số điện thoại, mã bưu chính: `keyword` dù nội dung có vẻ là chữ số.

### Ép kiểu dữ liệu (coercion)

Elasticsearch có cơ chế `coerce` cho một số trường số. Khi bật, dữ liệu dạng chuỗi số có thể được chuyển thành số và giá trị thập phân gửi vào trường nguyên có thể bị chuyển thành số nguyên theo quy tắc ép kiểu. Điều này thuận tiện với dữ liệu đầu vào không đồng nhất nhưng có thể che giấu lỗi ở tầng ứng dụng.

Nếu nghiệp vụ cần từ chối giá trị sai kiểu hoặc không chấp nhận phần thập phân ở trường nguyên, hãy cấu hình mapping để tắt coercion ở trường tương ứng và kiểm tra dữ liệu trước khi ghi. Đừng dựa vào việc Elasticsearch tự ép kiểu để thực thi quy tắc nghiệp vụ.

## 7. Truy vấn, sắp xếp và aggregation với trường số

Các kiểu số hỗ trợ truy vấn range, sắp xếp số học và aggregation. Ví dụ, tìm sản phẩm có trọng lượng từ 1,5 đến 5,0 kg:

```json
{
  "query": {
    "range": {
      "packageWeight": {
        "gte": 1.5,
        "lte": 5.0
      }
    }
  },
  "sort": [
    { "packageWeight": "asc" }
  ]
}
```

Ví dụ aggregation tính giá trung bình và giá lớn nhất:

```json
{
  "size": 0,
  "aggs": {
    "average_price_minor": {
      "avg": { "field": "priceMinorUnits" }
    },
    "maximum_price_minor": {
      "max": { "field": "priceMinorUnits" }
    }
  }
}
```

Aggregation trên số nguyên có thể trả về giá trị dạng số thực vì kết quả như trung bình có thể có phần lẻ. Nếu cần hiển thị tiền, hãy chuyển đổi đơn vị và làm tròn theo quy tắc nghiệp vụ. Cũng cần lọc theo `currency` trước khi tổng hợp để không cộng các loại tiền tệ khác nhau.

Với `scaled_float`, truy vấn range và sort hoạt động trên giá trị đã được lượng tử hóa. Nếu ngưỡng nghiệp vụ nằm giữa hai bước scale, hãy xác định rõ cách làm tròn và biên so sánh. Ví dụ scale 0,01 không thể phân biệt 12,341 với 12,344 nếu cả hai cùng được lượng tử hóa về một giá trị lưu trữ.

## 8. Số dạng định danh không nhất thiết là kiểu số

Một lỗi thiết kế thường gặp là dùng kiểu số cho mọi chuỗi chỉ chứa chữ số. Mã SKU `000123`, số điện thoại `0901234567` hoặc mã bưu chính có thể có số 0 ở đầu và không có ý nghĩa cộng trừ.

Nếu lưu `000123` dưới dạng integer, giá trị trở thành `123`; thông tin số 0 ở đầu bị mất. Truy vấn khoảng trên mã định danh cũng có thể mang ý nghĩa số học không mong muốn. Với những trường này, dùng `keyword`:

```java
@Field(type = FieldType.Keyword)
private String sku;

@Field(type = FieldType.Keyword)
private String postalCode;
```

Chỉ dùng kiểu số khi ứng dụng thực sự cần các phép toán số học hoặc range theo giá trị số. Nếu chỉ cần tìm chính xác, lọc hoặc aggregation theo nhóm mã, `keyword` thường là lựa chọn đúng.

## 9. Giới hạn số nguyên khi đi qua JSON và JavaScript

Elasticsearch `long` có thể lưu số nguyên 64 bit, nhưng không phải mọi thành phần trong hệ thống đều giữ chính xác toàn bộ miền đó. JavaScript dùng kiểu `Number` theo IEEE 754 double; các số nguyên chỉ được biểu diễn chính xác liên tục đến 2^53 - 1. Khi một API trung gian, trình duyệt hoặc công cụ phân tích parse một `long` lớn hơn giới hạn này thành `Number`, giá trị có thể bị làm tròn.

Ví dụ:

```javascript
const value = 9007199254740993;
console.log(value); // có thể thành 9007199254740992
```

Nếu giá trị 64 bit phải đi qua JavaScript, hãy cân nhắc truyền dưới dạng chuỗi ở ranh giới API, hoặc dùng cơ chế hỗ trợ `BigInt` mà không serialize trực tiếp thành JSON number không an toàn. JSON chuẩn không có kiểu BigInt riêng; cần thống nhất quy ước giữa producer và consumer.

Điều này cũng là một lý do để không dùng số nguyên lớn làm ID số học xuyên suốt mọi tầng nếu ID chỉ cần nhận diện. Một chuỗi `keyword` có thể giữ nguyên giá trị và định dạng.

## 10. Kiểm soát overflow, làm tròn và dữ liệu lỗi

Khi nhận dữ liệu từ API, message queue hoặc hệ thống bên ngoài, cần kiểm tra:

- Giá trị có nằm trong miền của kiểu Elasticsearch đã khai báo không?
- Giá trị có phải số hữu hạn và hợp lệ không?
- Có phần thập phân trong khi trường chỉ cho phép số nguyên không?
- Scale của `scaled_float` có phù hợp với độ phân giải nghiệp vụ không?
- Phép nhân với scaling factor có thể vượt miền số nguyên 64 bit không?
- Giá trị tiền có đúng scale của currency không?

Ví dụ kiểm tra số lượng trong Java:

```java
public static int requireQuantity(long value) {
    if (value < 0 || value > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Quantity is out of range");
    }
    return Math.toIntExact(value);
}
```

Ví dụ kiểm tra giá trị thập phân trước khi chuyển sang `double`:

```java
public static double requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Value must be finite");
    }
    return value;
}
```

Nên từ chối hoặc đưa dữ liệu không hợp lệ vào luồng xử lý lỗi có quan sát được. Việc âm thầm bỏ qua field hoặc ép kiểu có thể khiến kết quả tìm kiếm và aggregation không còn phản ánh dữ liệu nghiệp vụ.

## 11. Thay đổi kiểu số sau khi index đã tồn tại

Mapping của một field đã được tạo không thể tùy ý đổi từ `integer` sang `long`, `double` hoặc `scaled_float` trên cùng index. Thay đổi `scaling_factor` cũng làm thay đổi cách diễn giải giá trị đã lưu, vì vậy không nên xem đây là một thuộc tính có thể sửa nhẹ sau khi dữ liệu đã được index.

Nếu cần thay đổi kiểu hoặc độ phân giải, quy trình phổ biến là:

1. Tạo index mới với mapping đúng.
2. Chuyển đổi dữ liệu nguồn sang kiểu mới theo quy tắc rõ ràng.
3. Reindex hoặc backfill dữ liệu vào index mới.
4. Kiểm tra giá trị biên, số lượng document, range query và aggregation.
5. Chuyển alias hoặc cấu hình ứng dụng sang index mới.
6. Giữ index cũ trong thời gian cần thiết để có thể quay lại.

Ví dụ, nếu trước đây `rating` là `float` và sau này muốn dùng `scaled_float` với scale 100, cần quyết định cách làm tròn dữ liệu cũ, kiểm tra các truy vấn có ngưỡng sát nhau và bảo đảm kết quả sắp xếp/aggregation vẫn đáp ứng yêu cầu.

## 12. Bảng lựa chọn nhanh theo tình huống

| Dữ liệu | Lựa chọn thường phù hợp | Lưu ý |
|---|---|---|
| Số lượng tồn kho | `integer` | Kiểm tra giới hạn và không nhận số lẻ |
| Bộ đếm tích lũy | `long` | Có thể vượt giới hạn 32 bit |
| Mã SKU, số điện thoại | `keyword` | Giữ số 0 đầu, không có ý nghĩa số học |
| Giá tiền chính xác | `long` theo đơn vị nhỏ nhất | Lưu thêm currency và scale |
| Điểm đánh giá 0–5 với 1–2 chữ số lẻ | `scaled_float` | Chọn hệ số 10 hoặc 100 theo độ phân giải |
| Trọng lượng đo gần đúng | `float` hoặc `double` | Chọn theo sai số chấp nhận được |
| Tọa độ địa lý | `geo_point` nếu cần truy vấn địa lý | Không dùng `double` riêng nếu cần geo query, khoảng cách hoặc bounding box |
| Số nguyên không âm vượt miền signed 64 bit | `unsigned_long` | Kiểm tra khả năng biểu diễn ở Java và mọi tầng API |

## 13. Quy trình thiết kế trường số

Khi thêm một trường số vào search document, có thể làm theo trình tự:

1. Xác định ý nghĩa nghiệp vụ: đại lượng, bộ đếm, tiền tệ hay định danh.
2. Xác định giá trị nhỏ nhất/lớn nhất và khả năng tăng trong tương lai.
3. Xác định độ chính xác: số nguyên chính xác, số thực xấp xỉ hay số thập phân với scale cố định.
4. Chọn kiểu Elasticsearch phù hợp với miền và độ phân giải.
5. Chọn kiểu Java tương ứng; dùng `BigDecimal` cho tính toán thập phân nghiệp vụ và chuyển đổi có chủ đích khi index.
6. Khai báo mapping tường minh trước khi ghi document đầu tiên.
7. Kiểm tra giá trị biên, overflow, rounding, coercion và dữ liệu null/thiếu.
8. Kiểm tra range query, sort và aggregation với dữ liệu đại diện.
9. Kiểm tra các tầng JSON/API có giữ chính xác giá trị lớn hay không.
10. Có kế hoạch reindex nếu cần đổi kiểu hoặc scaling factor trong tương lai.

## 14. Kết luận

Kiểu số trong Elasticsearch cần được chọn dựa trên miền giá trị và yêu cầu độ chính xác. `byte`, `short`, `integer` và `long` phù hợp với số nguyên có giới hạn; `float` và `double` phù hợp với dữ liệu xấp xỉ theo chuẩn IEEE 754; `scaled_float` phù hợp với số thập phân có độ phân giải cố định và chấp nhận làm tròn theo scaling factor.

Trong Spring Data Elasticsearch, khai báo mapping rõ ràng bằng `@Field`, chọn kiểu Java tương ứng và kiểm tra dữ liệu trước khi lập chỉ mục. Với tiền tệ hoặc giá trị cần chính xác tuyệt đối, dùng `BigDecimal` trong logic nghiệp vụ và cân nhắc lưu số nguyên theo đơn vị nhỏ nhất. Với mã định danh chỉ chứa chữ số, dùng `keyword`. Khi thay đổi kiểu hoặc độ phân giải của field đã tồn tại, tạo index mới và reindex theo kế hoạch.
