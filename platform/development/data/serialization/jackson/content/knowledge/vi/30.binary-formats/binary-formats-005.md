# Kiểm tra hỗ trợ kiểu số và đặc điểm của từng định dạng

Các định dạng nhị phân không dùng chung một mô hình số. Có định dạng biểu diễn số nguyên theo độ rộng cố định, có định dạng dùng integer và floating-point theo chuẩn máy, có định dạng hỗ trợ số nguyên hoặc số thập phân độ chính xác lớn, và có định dạng yêu cầu schema mô tả kiểu trước khi đọc dữ liệu.

Vì vậy, không thể kết luận một định dạng nhị phân luôn giữ số chính xác hơn JSON hoặc mọi định dạng đều hỗ trợ Java BigInteger và BigDecimal như nhau. Cần xem xét đồng thời ba lớp:

1. **Chuẩn định dạng:** định dạng trên wire có những kiểu số nào, giới hạn độ rộng và cách mã hóa ra sao.
2. **Jackson module:** module cụ thể có thể ghi, đọc và ánh xạ những kiểu Java nào; có hỗ trợ logical type, tag hoặc extension nào không.
3. **Kiểu Java và cấu hình ứng dụng:** dữ liệu được đọc vào int, long, BigInteger, float, double hay BigDecimal; coercion, overflow và độ chính xác được xử lý thế nào.

Bài này tập trung vào việc đánh giá khả năng số của các định dạng nhị phân thường gặp trong hệ sinh thái Jackson như Smile, CBOR, BSON, Avro, Protobuf và Ion. Một số module có thể thay đổi API hoặc mức hỗ trợ theo phiên bản; hãy xác nhận trên đúng dependency mà dự án đang dùng.

## 1. Vì sao cần kiểm tra kiểu số trước khi chọn định dạng?

Một hệ thống có thể truyền dữ liệu mà không gặp lỗi cú pháp nhưng vẫn làm sai giá trị số. Ví dụ:

- Một số nguyên 64-bit bị đọc vào int 32-bit.
- Một số nguyên lớn hơn Long.MAX_VALUE bị ép về long.
- BigDecimal được chuyển qua double và mất độ chính xác thập phân.
- Một số tiền có scale 4 bị lưu thành Decimal128 có giới hạn precision.
- Giá trị unsigned 64-bit được diễn giải như signed long âm.
- NaN hoặc Infinity được ghi thành một giá trị mà consumer khác không chấp nhận.

Ví dụ hai giá trị:

~~~text
9007199254740992
9007199254740993
~~~

Hai số này khác nhau một đơn vị. Nếu chuyển qua kiểu double IEEE 754 binary64, chúng có thể không còn phân biệt được vì binary64 chỉ biểu diễn chính xác mọi số nguyên đến một giới hạn nhất định quanh 2^53.

Tương tự, decimal 0.1 không có biểu diễn nhị phân hữu hạn trong hệ cơ số 2. Nếu chuyển BigDecimal sang double rồi quay lại BigDecimal, kết quả có thể chứa phần sai số nhị phân.

Chọn định dạng phải bắt đầu từ yêu cầu dữ liệu: có cần số nguyên lớn hơn 64-bit không, có cần decimal chính xác không, có cần unsigned không, có cần schema không và consumer có dùng cùng quy tắc không.

## 2. Phân biệt kiểu Java với kiểu số trên wire

Các kiểu Java thường gặp:

| Kiểu Java | Đặc điểm |
|---|---|
| byte | Số nguyên có dấu 8-bit |
| short | Số nguyên có dấu 16-bit |
| int | Số nguyên có dấu 32-bit |
| long | Số nguyên có dấu 64-bit |
| BigInteger | Số nguyên độ chính xác tùy ý, giới hạn thực tế bởi bộ nhớ |
| float | IEEE 754 binary32 |
| double | IEEE 754 binary64 |
| BigDecimal | Số thập phân có precision và scale tùy ý |

Không phải định dạng nào cũng có một kiểu wire riêng cho từng kiểu Java. Ví dụ, BSON không có kiểu int8 hoặc int16 độc lập; các giá trị Java byte và short thường cần được mở rộng vào kiểu integer BSON phù hợp. Avro có int và long, nhưng không có primitive unsigned hoặc BigInteger. Protobuf có nhiều biến thể integer và fixed-width, nhưng không có kiểu decimal tùy ý tích hợp sẵn.

Khi đọc dữ liệu, Jackson có thể ánh xạ một kiểu wire rộng hơn vào kiểu Java hẹp hơn. Việc chuyển đổi có thể thành công, bị từ chối hoặc phụ thuộc coercion/configuration. Không nên giả định module sẽ luôn báo overflow theo cùng một cách.

## 3. Những câu hỏi cần trả lời cho mỗi định dạng

Khi đánh giá một định dạng nhị phân, hãy kiểm tra:

1. Số nguyên có dấu được biểu diễn tối đa bao nhiêu bit?
2. Có số nguyên unsigned không?
3. Có BigInteger hoặc integer lớn hơn 64-bit không?
4. Floating-point dùng binary16, binary32 hay binary64?
5. Có NaN, positive/negative Infinity và negative zero không?
6. Có kiểu decimal chính xác không?
7. Decimal có giữ scale/trailing zeros không?
8. Có giới hạn precision hoặc exponent không?
9. Có schema bắt buộc để biết kiểu số không?
10. Jackson module ánh xạ kiểu Java nào trực tiếp?
11. Khi đọc vào Object hoặc Map, module trả về Number subtype nào?
12. Có cần custom serializer, logical type hoặc wrapper class không?

Đặc biệt, phải phân biệt **định dạng có khả năng biểu diễn** với **Jackson module có hỗ trợ trực tiếp**. Một chuẩn có thể định nghĩa decimal tag nhưng module ở phiên bản đang dùng chưa ánh xạ nó thành BigDecimal theo cách ứng dụng mong muốn.

## 4. Bức tranh tổng quan về kiểu số

Bảng sau tóm tắt mô hình số ở mức định dạng. Đây là đặc điểm của wire format; mức hỗ trợ thực tế trong Jackson cần được kiểm tra theo module và phiên bản:

| Định dạng | Số nguyên | Floating-point | Decimal chính xác |
|---|---|---|---|
| Smile | Có integer/long và biểu diễn số lớn theo khả năng module | Có float/double | Có hỗ trợ biểu diễn số lớn/decimal trong hệ sinh thái Smile; kiểm tra module |
| CBOR | Integer unsigned/negative đến 64-bit và bignum qua tag | Half, single, double | Decimal fraction qua tag |
| BSON | int32 và int64 | double | Decimal128 |
| Avro | int32 và int64 theo schema | float32 và float64 | Logical type decimal trên bytes/fixed |
| Protobuf | int32/int64, unsigned, zigzag và fixed-width | float32 và float64 | Không có primitive decimal chuẩn |
| Ion | Integer độ chính xác lớn | Float binary64 | Decimal có precision/exponent riêng |

Không nên dùng bảng này để suy ra mọi module Jackson hỗ trợ mọi dạng số. Ví dụ BSON chuẩn có Decimal128 nhưng một Jackson BSON module cụ thể có thể cần kiểu BSON Decimal128 riêng hoặc custom conversion thay vì tự động chuyển BigDecimal.

## 5. Smile: định dạng nhị phân được thiết kế cho dữ liệu kiểu JSON

Smile là định dạng nhị phân của Jackson, được thiết kế để biểu diễn dữ liệu dạng JSON hiệu quả hơn trong nhiều trường hợp. Nó giữ cấu trúc object, array và scalar quen thuộc với Databind nhưng mã hóa thành token nhị phân.

Smile có các token số chuyên biệt thay vì lưu mọi giá trị dưới dạng chuỗi ký tự thập phân. Điều này giúp parser biết giá trị là integer, long, float, double hoặc một dạng số lớn mà không cần parse chuỗi JSON text.

Trong ứng dụng Jackson, thường tạo mapper bằng SmileFactory:

~~~java
ObjectMapper smileMapper =
    new ObjectMapper(new SmileFactory());
~~~

Ghi dữ liệu:

~~~java
byte[] bytes = smileMapper.writeValueAsBytes(value);
~~~

Đọc dữ liệu:

~~~java
Measurement restored =
    smileMapper.readValue(bytes, Measurement.class);
~~~

Smile phù hợp khi muốn một định dạng nhị phân có cách dùng gần với JSON và muốn tiếp tục dùng POJO, Map, List cùng các serializer/deserializer của Jackson.

## 6. Đặc điểm số của Smile

Smile có token riêng cho các nhóm số thông dụng. Integer và long được mã hóa theo dạng nhị phân có độ dài biến đổi; float và double giữ kiểu floating-point tương ứng. Các dạng số lớn như BigInteger và BigDecimal có thể được xử lý qua khả năng số lớn của Smile/Jackson module.

Những điểm cần kiểm tra:

- int và long có round-trip đúng ở cả biên âm và dương.
- BigInteger có được module ghi/đọc trực tiếp trong phiên bản đang dùng không.
- BigDecimal có giữ giá trị và scale theo yêu cầu không.
- Float và Double có giữ được các giá trị đặc biệt như NaN hoặc Infinity theo cấu hình không.
- Khi đọc thành Object, parser trả về kiểu Number nào.

Không nên chỉ kiểm tra một giá trị nhỏ như 10 hoặc 1.5. Hãy kiểm tra các giá trị ở ranh giới kiểu Java và các giá trị có precision lớn.

## 7. Smile và BigInteger

BigInteger dùng khi số nguyên vượt quá phạm vi long:

~~~java
BigInteger huge = new BigInteger(
    "1234567890123456789012345678901234567890"
);
~~~

Một bài test round-trip có thể kiểm tra:

~~~java
byte[] bytes = smileMapper.writeValueAsBytes(huge);
BigInteger restored =
    smileMapper.readValue(bytes, BigInteger.class);

assertEquals(huge, restored);
~~~

Nếu phiên bản module không hỗ trợ kiểu BigInteger theo cách mong đợi hoặc dữ liệu được đọc vào Object thay vì BigInteger, cần kiểm tra serializer/parser và kiểu Number trả về. Không nên giả định mọi consumer Smile ở ngôn ngữ khác đều xử lý số lớn giống Jackson.

## 8. Smile và BigDecimal

BigDecimal có hai thành phần quan trọng:

- Unscaled value: số nguyên chưa áp dụng scale.
- Scale: số chữ số thập phân được xác định bởi lũy thừa của 10.

Ví dụ:

~~~java
BigDecimal amount = new BigDecimal("123.4500");
~~~

Giá trị có unscaled value 1234500 và scale 4. Về số học, 123.4500 bằng 123.45, nhưng BigDecimal.equals() xem scale là một phần của trạng thái nên hai object này không bằng nhau theo equals.

Khi kiểm tra Smile, hãy quyết định yêu cầu là:

- Bảo toàn giá trị số học.
- Bảo toàn scale.
- Bảo toàn biểu diễn có trailing zero.

Nếu chỉ cần so sánh số học, dùng compareTo. Nếu cần bảo toàn scale cho nghiệp vụ tiền tệ hoặc dữ liệu đo lường, hãy kiểm tra equals và scale sau round-trip.

## 9. CBOR: mô hình số theo chuẩn Concise Binary Object Representation

CBOR là định dạng nhị phân được chuẩn hóa, có cấu trúc dữ liệu tổng quát và được thiết kế để mã hóa gọn. CBOR có major type dành cho unsigned integer, negative integer, byte string, text string, array, map, tag và simple value.

Trong Jackson, có thể tạo mapper với CBORFactory:

~~~java
ObjectMapper cborMapper =
    new ObjectMapper(new CBORFactory());
~~~

CBOR không yêu cầu schema cho các cấu trúc cơ bản. Parser có thể nhận ra kiểu token từ chính dữ liệu nhị phân. Tuy nhiên, một số tag và quy ước ứng dụng vẫn cần cả hai phía hiểu giống nhau.

## 10. CBOR integer: unsigned và negative

CBOR major type 0 biểu diễn số nguyên không âm. Major type 1 biểu diễn số nguyên âm theo quy tắc giá trị âm được mã hóa từ phép biến đổi dựa trên -1-n.

Phần thông tin bổ sung của CBOR có thể mã hóa giá trị đến 64-bit. Điều này tạo ra một khác biệt quan trọng so với Java signed long:

- Java long có miền từ -2^63 đến 2^63 - 1.
- CBOR unsigned 64-bit có thể biểu diễn đến 2^64 - 1.

Một số unsigned CBOR lớn hơn Long.MAX_VALUE không thể được biểu diễn trực tiếp bằng một Java long có dấu mà vẫn giữ cùng giá trị số học. Ứng dụng cần BigInteger hoặc một quy ước unsigned riêng.

Không nên đọc một giá trị CBOR unsigned lớn vào long rồi coi kết quả âm là giá trị đúng. Cần kiểm tra kiểu token và cách module biểu diễn số ngoài miền signed.

## 11. CBOR bignum và BigInteger

CBOR định nghĩa tag 2 và tag 3 cho positive bignum và negative bignum. Các tag này cho phép biểu diễn số nguyên vượt quá miền integer 64-bit cơ bản.

Về nguyên tắc:

- Tag 2 biểu diễn số nguyên dương lớn bằng byte string.
- Tag 3 biểu diễn số nguyên âm lớn theo quy tắc bignum của CBOR.

Jackson CBOR có thể hỗ trợ BigInteger qua các quy tắc bignum của module, nhưng cần xác nhận phiên bản và cách cấu hình parser/generator. Đừng chỉ dựa vào việc chuẩn CBOR có tag bignum để kết luận module đang dùng chắc chắn hỗ trợ mọi trường hợp.

Test:

~~~java
BigInteger value = new BigInteger(
    "184467440737095516160000000000000000001"
);

byte[] encoded = cborMapper.writeValueAsBytes(value);
BigInteger decoded =
    cborMapper.readValue(encoded, BigInteger.class);

assertEquals(value, decoded);
~~~

Hãy kiểm tra cả số dương lớn và số âm có độ lớn vượt 64-bit.

## 12. CBOR floating-point

CBOR hỗ trợ các dạng floating-point:

- Half precision, binary16.
- Single precision, binary32.
- Double precision, binary64.

Binary16 có độ chính xác và miền biểu diễn nhỏ hơn binary32/binary64. Khi chuyển một giá trị Java float hoặc double sang định dạng có thể chọn độ rộng nhỏ hơn, cần xác nhận module có làm giảm precision hay không.

CBOR cũng có thể biểu diễn các giá trị floating-point đặc biệt như NaN và positive/negative Infinity theo quy tắc IEEE 754 được định dạng hỗ trợ.

Với dữ liệu khoa học, hãy kiểm tra:

- Giá trị nhỏ nhất/lớn nhất.
- Subnormal values.
- Negative zero.
- NaN.
- Positive và negative Infinity.
- Sai số sau khi chuyển đổi độ rộng.

Nếu hợp đồng yêu cầu binary64, đừng để một tối ưu kích thước tự động ghi binary16 hoặc binary32 mà không có test.

## 13. CBOR decimal fraction

CBOR định nghĩa tag 4 cho decimal fraction. Dữ liệu có thể được biểu diễn như một cặp gồm exponent và mantissa:

~~~text
tag(4) [exponent, mantissa]
~~~

Giá trị số được hiểu theo dạng mantissa nhân 10 mũ exponent. Đây là một biểu diễn decimal dựa trên số nguyên, không phải floating-point binary.

Ví dụ một giá trị có thể được biểu diễn với mantissa 12345 và exponent -2 để cho ra 123.45.

CBOR cũng có tag liên quan đến bigfloat. Tuy nhiên, mức hỗ trợ tag và ánh xạ trực tiếp thành BigDecimal/BigInteger trong Jackson phụ thuộc module và phiên bản.

Khi trao đổi decimal qua CBOR, hãy kiểm tra:

- Module có ghi tag decimal fraction không.
- Parser có trả về BigDecimal hay một cấu trúc tagged value khác.
- Scale có được bảo toàn không.
- Consumer ngoài Jackson có hiểu tag 4 không.

## 14. BSON: kiểu số gắn với tài liệu document

BSON là dạng biểu diễn nhị phân của document, thường được dùng trong hệ sinh thái MongoDB. BSON có các kiểu số cụ thể được đánh dấu trong document.

Các kiểu số quan trọng:

- Double.
- 32-bit integer.
- 64-bit integer.
- Decimal128.

BSON không có các kiểu integer 8-bit và 16-bit độc lập như Java byte và short. Các kiểu này thường được ánh xạ lên integer rộng hơn.

Khi dùng Jackson BSON module hoặc kết hợp Jackson với BSON driver, phải xác định rõ lớp nào chịu trách nhiệm cho codec. Một BSON driver có thể hỗ trợ Decimal128 tốt hơn một Jackson module cụ thể; không nên gộp hai khả năng thành một.

## 15. BSON int32

BSON có kiểu int32 cho số nguyên có dấu 32-bit:

~~~text
-2,147,483,648 đến 2,147,483,647
~~~

Java int ánh xạ tự nhiên vào kiểu này. Byte và short có thể được mở rộng thành int32 khi serialize, nhưng sau khi đọc lại cần biết target Java type để chuyển về byte/short.

Test biên:

~~~java
int[] values = {
    Integer.MIN_VALUE,
    -1,
    0,
    1,
    Integer.MAX_VALUE
};
~~~

Nếu một số vượt miền int32, writer hoặc driver cần dùng int64 hoặc báo lỗi tùy kiểu dữ liệu và API. Không nên giả định mọi BSON writer tự động chọn int64 cho mọi kiểu Java Number.

## 16. BSON int64

BSON int64 là signed 64-bit integer, tương ứng tự nhiên với Java long:

~~~text
-9,223,372,036,854,775,808
đến
 9,223,372,036,854,775,807
~~~

Các giá trị lớn hơn phạm vi này không thể lưu trong BSON int64. Nếu cần số nguyên lớn hơn, phải dùng một biểu diễn khác như Decimal128 nếu miền giá trị phù hợp, chuỗi thập phân hoặc một schema ứng dụng riêng.

Decimal128 không phải thay thế hoàn hảo cho BigInteger vì nó là decimal floating-point với precision hữu hạn.

## 17. BSON double

BSON double là IEEE 754 binary64. Nó phù hợp với Java double và thường được dùng cho số thực gần đúng.

Những điểm cần nhớ:

- 0.1 không có biểu diễn binary64 hữu hạn chính xác.
- Số nguyên lớn hơn 2^53 có thể mất khả năng phân biệt từng đơn vị nếu lưu bằng double.
- NaN và Infinity có thể tồn tại trong miền IEEE 754.
- Negative zero có thể khác positive zero ở một số phép toán/bit-level.

Không dùng BSON double cho số tiền hoặc decimal cần chính xác chỉ vì Java double dễ dùng. Nếu cần decimal, hãy đánh giá Decimal128 hoặc một biểu diễn decimal khác.

## 18. BSON Decimal128

Decimal128 là kiểu decimal floating-point có precision tối đa 34 chữ số có nghĩa theo định dạng IEEE 754 decimal128. Nó có miền exponent hữu hạn và không phải số thập phân precision tùy ý.

So với double:

- Decimal128 dùng cơ số thập phân cho biểu diễn decimal.
- Nhiều giá trị decimal như 0.1 có thể được biểu diễn chính xác nếu nằm trong giới hạn precision/exponent.
- Precision bị giới hạn ở 34 chữ số có nghĩa.
- Một BigDecimal có precision hoặc scale ngoài miền Decimal128 có thể cần làm tròn hoặc bị từ chối.

Ví dụ giá trị:

~~~text
1234567890123456789012345678901234.56
~~~

có nhiều hơn 34 chữ số có nghĩa và không thể được giữ nguyên hoàn toàn trong Decimal128.

Khi chuyển BigDecimal sang Decimal128, cần xác định chính sách rounding và overflow. Không nên âm thầm làm tròn dữ liệu tiền tệ mà không có quy tắc nghiệp vụ.

## 19. BSON và BigDecimal không đồng nghĩa

Java BigDecimal có precision và scale tùy ý. BSON Decimal128 có giới hạn cụ thể. Do đó, việc ánh xạ BigDecimal sang Decimal128 là phép chuyển đổi có giới hạn.

Một số Jackson BSON module có thể:

- Ánh xạ BigDecimal vào BSON Decimal128.
- Dùng string hoặc một representation khác.
- Yêu cầu custom serializer/deserializer.
- Không hỗ trợ BigDecimal trực tiếp ở phiên bản đang dùng.

Hãy kiểm tra API thực tế của module/driver. Với MongoDB Java driver, kiểu Decimal128 thường là kiểu riêng; việc convert BigDecimal cần API chuyển đổi của driver và có thể ném lỗi nếu giá trị nằm ngoài miền.

Nếu cần giữ BigDecimal bất kỳ precision, có thể lưu unscaled integer và scale thành hai field, hoặc lưu decimal string theo một schema rõ ràng. Hai cách này cần consumer cùng tuân thủ.

## 20. Avro: định dạng nhị phân dựa trên schema

Avro là định dạng dữ liệu nhị phân có schema. Schema mô tả record, field và kiểu dữ liệu; binary payload thường không lặp lại toàn bộ tên field và kiểu như một định dạng self-describing.

Các primitive numeric của Avro:

- int: số nguyên có dấu 32-bit.
- long: số nguyên có dấu 64-bit.
- float: IEEE 754 binary32.
- double: IEEE 754 binary64.

Avro không có primitive unsigned integer, BigInteger hay BigDecimal độc lập. Decimal được mô tả bằng logical type trên underlying bytes hoặc fixed.

Điều này khiến schema trở thành một phần thiết yếu của khả năng đọc dữ liệu. Reader cần writer schema hoặc cơ chế schema resolution tương ứng để diễn giải binary payload.

## 21. Avro int và long

Avro int là signed 32-bit; Avro long là signed 64-bit. Khi mapping Java:

| Avro type | Java type thường dùng |
|---|---|
| int | int / Integer |
| long | long / Long |

Byte và short có thể được chuyển vào Avro int nếu giá trị nằm trong miền. Nhưng Avro schema không ghi lại rằng field ban đầu là byte hay short.

Khi đọc vào kiểu hẹp, phải kiểm tra overflow. Nếu schema là long nhưng DTO Java dùng int, một giá trị lớn hơn Integer.MAX_VALUE không thể được biểu diễn đúng.

Không nên dùng Avro int cho một counter có thể tăng vượt 2^31-1 chỉ vì dữ liệu hiện tại còn nhỏ. Hãy chọn long từ đầu nếu miền nghiệp vụ yêu cầu.

## 22. Avro float và double

Avro float là binary32 và double là binary64. Đây là floating-point nhị phân, không phải decimal chính xác.

Nếu schema dùng float nhưng Java model giữ double, giá trị có thể bị giảm precision khi encode. Khi schema dùng double và Java đọc vào float, giá trị có thể bị làm tròn hoặc không biểu diễn được.

Với phép đo khoa học, tọa độ hoặc số liệu chấp nhận sai số, float/double có thể phù hợp. Với tiền tệ, thuế hoặc tỷ lệ cần decimal chính xác, nên dùng logical decimal thay vì float/double.

## 23. Avro decimal logical type

Avro định nghĩa logical type decimal trên underlying bytes hoặc fixed. Giá trị được biểu diễn bằng unscaled integer theo two's-complement big-endian, cùng precision và scale trong schema.

Ví dụ schema:

~~~json
{
  "type": "bytes",
  "logicalType": "decimal",
  "precision": 18,
  "scale": 2
}
~~~

Với precision 18 và scale 2, schema mô tả số decimal có tối đa 18 chữ số có nghĩa theo quy tắc Avro decimal. Scale 2 nghĩa giá trị được diễn giải với hai chữ số thập phân.

Ví dụ unscaled value 12345 với scale 2 biểu diễn 123.45.

Schema decimal phải được thống nhất giữa writer và reader. Hai schema có precision/scale khác nhau không thể được xem là tương đương chỉ vì cả hai cùng dùng bytes.

## 24. Avro decimal và BigDecimal

Trong Avro Java ecosystem, logical decimal thường được chuyển qua Conversion giữa Avro decimal và Java BigDecimal. Jackson Avro module có thể tham gia mapping nhưng cần schema và conversion hỗ trợ phù hợp.

Hãy kiểm tra:

- Logical type decimal có được nhận diện không.
- Schema có precision/scale phù hợp dữ liệu không.
- Avro conversion được đăng ký hoặc kích hoạt như thế nào trong phiên bản đang dùng.
- BigDecimal được serialize và deserialize có giữ scale mong muốn không.
- Consumer dùng Avro GenericRecord, SpecificRecord hay Jackson có cùng cách chuyển đổi không.

Không nên chỉ thấy schema underlying là bytes rồi giả định BigDecimal sẽ tự động được xử lý đúng. Nếu logical type bị bỏ qua, ứng dụng có thể nhận ByteBuffer/byte[] hoặc representation khác thay vì BigDecimal.

## 25. Avro schema evolution và kiểu số

Avro có quy tắc schema resolution. Việc đổi kiểu numeric cần được đánh giá theo khả năng promotion được chuẩn hỗ trợ và schema compatibility policy.

Một số promotion như int sang long hoặc float sang double được Avro định nghĩa trong quá trình resolution. Nhưng không phải mọi chuyển đổi đều hợp lệ hoặc không mất dữ liệu.

Ví dụ:

- int sang long có thể mở rộng miền số nguyên.
- float sang double có thể giữ giá trị float ban đầu chính xác trong miền double.
- long sang int có thể mất dữ liệu và không phải promotion an toàn.
- double sang float có thể mất precision.
- Thay decimal precision/scale cần kiểm tra quy tắc logical type và miền giá trị.

Không nên dựa vào Jackson coercion để thay thế schema resolution của Avro. Schema là hợp đồng wire format.

## 26. Protobuf: kiểu số khai báo trong .proto

Protocol Buffers (Protobuf) là định dạng binary dựa trên schema message. Các field có field number và type được định nghĩa trong file .proto.

Protobuf có nhiều kiểu số:

| Nhóm | Kiểu |
|---|---|
| Signed integer varint | int32, int64 |
| Signed integer ZigZag | sint32, sint64 |
| Unsigned integer varint | uint32, uint64 |
| Fixed-width unsigned | fixed32, fixed64 |
| Fixed-width signed | sfixed32, sfixed64 |
| Floating-point | float, double |

Protobuf không có kiểu BigInteger hoặc BigDecimal chuẩn. Nếu cần decimal chính xác, phải dùng message riêng, string hoặc một kiểu quy ước như unscaled integer cộng scale.

## 27. Protobuf int32 và int64

int32 và int64 là số nguyên có dấu. Dạng wire varint có hiệu quả với các giá trị nhỏ không âm, nhưng số âm của int32/int64 có thể cần nhiều byte hơn do cách mã hóa.

Java mapping thường là:

| Protobuf | Java |
|---|---|
| int32 | int |
| int64 | long |

Protobuf int32 có một chi tiết cần chú ý khi giá trị âm: encoding varint của int32 âm thường chiếm 10 byte. Nếu miền dữ liệu thường có số âm và kích thước quan trọng, sint32 hoặc sfixed32 có thể phù hợp hơn tùy phân phối giá trị.

## 28. Protobuf sint32 và sint64 dùng ZigZag

ZigZag ánh xạ số nguyên có dấu thành số không âm để giá trị âm nhỏ cũng có varint ngắn:

- 0 → 0
- -1 → 1
- 1 → 2
- -2 → 3
- 2 → 4

Do đó, sint32/sint64 thường tiết kiệm hơn int32/int64 khi giá trị âm nhỏ xuất hiện thường xuyên.

Điều này là khác biệt về kích thước wire encoding, không phải khác biệt về miền giá trị. Hai kiểu vẫn biểu diễn signed integer trong độ rộng tương ứng.

Không đổi field type từ int32 sang sint32 tùy tiện sau khi đã phát hành schema. Chúng có wire type tương tự nhưng cách diễn giải payload khác nhau; thay đổi có thể làm reader hiểu sai dữ liệu.

## 29. Protobuf uint32 và uint64

Protobuf có unsigned integer:

- uint32: 0 đến 2^32 - 1.
- uint64: 0 đến 2^64 - 1.

Java không có primitive unsigned 32-bit/64-bit tương ứng. Generated Java code thường dùng int và long để giữ bit pattern.

Với uint32, nếu giá trị lớn hơn Integer.MAX_VALUE, biến int có thể hiển thị thành số âm nếu in trực tiếp. Dùng Integer.toUnsignedLong để lấy giá trị số học không dấu.

Với uint64, giá trị lớn hơn Long.MAX_VALUE không thể biểu diễn dưới dạng Java long có dấu theo nghĩa số học. Có thể cần logic unsigned hoặc BigInteger ở tầng ứng dụng.

Không nên dùng phép so sánh signed thông thường cho uint64 nếu miền giá trị có thể vượt Long.MAX_VALUE. Hãy dùng helper unsigned hoặc kiểu wrapper được thiết kế rõ.

## 30. Protobuf fixed32, fixed64, sfixed32 và sfixed64

Các kiểu fixed-width luôn dùng số byte cố định:

- fixed32: 32-bit unsigned.
- sfixed32: 32-bit signed.
- fixed64: 64-bit unsigned.
- sfixed64: 64-bit signed.

Khác với varint, kích thước không phụ thuộc giá trị. Với các số thường lớn hoặc cần đọc nhanh, fixed-width có thể phù hợp; với số nhỏ, varint thường tiết kiệm hơn.

Chọn kiểu dựa trên miền giá trị và phân phối dữ liệu, không chỉ dựa vào tên Java type. Field number và wire type đã công bố phải được giữ ổn định khi schema tiến hóa.

## 31. Protobuf float và double

Protobuf float là IEEE 754 binary32; double là binary64. Chúng lưu số gần đúng, không phải decimal chính xác.

Nếu cần:

- Số đo có sai số cho phép: float/double có thể phù hợp.
- Số tiền: tránh float/double; dùng decimal message hoặc unscaled integer.
- Số nguyên lớn: dùng int64/uint64 hoặc một representation BigInteger.

Protobuf float/double có thể biểu diễn các giá trị đặc biệt theo IEEE 754 như NaN và Infinity. Consumer phải có chính sách xử lý các giá trị này, nhất là khi dữ liệu sau đó được chuyển sang JSON, database hoặc ngôn ngữ không hỗ trợ chúng theo cùng cách.

## 32. Protobuf không có decimal primitive

Một message có thể biểu diễn decimal theo cặp unscaled value và scale:

~~~proto
message DecimalValue {
  bytes unscaled_value = 1;
  int32 scale = 2;
}
~~~

Hoặc với miền nhỏ hơn, có thể dùng int64 unscaled value và scale:

~~~proto
message Money {
  int64 units = 1;
  int32 nanos_or_scale = 2;
}
~~~

Thiết kế cụ thể cần định nghĩa:

- Quy ước dấu và byte order.
- Scale âm/dương có cho phép không.
- Precision tối đa.
- Overflow xử lý thế nào.
- Có normalize trailing zeros hay giữ scale không.

Một lựa chọn khác là lưu decimal dạng string. String dễ đọc và giữ chữ số nhưng cần parse/validate ở cả hai phía, đồng thời cần định nghĩa canonical representation.

## 33. Protobuf JSON mapping không phải binary wire format

Protobuf có một JSON mapping riêng. Ví dụ, int64 và uint64 thường được biểu diễn dưới dạng JSON string trong mapping chuẩn để tránh mất precision ở các môi trường JavaScript dùng Number.

Điều đó không có nghĩa binary Protobuf lưu int64 như chuỗi. Binary wire format vẫn dùng varint hoặc fixed-width theo field type.

Hãy phân biệt:

- Binary Protobuf: dữ liệu nhị phân theo wire type.
- Protobuf JSON: quy tắc chuyển message sang JSON text.
- Jackson JSON: cách ObjectMapper serialize POJO hoặc generated class.

Không nên dùng hành vi của Protobuf JSON để kết luận kiểu số trên binary wire format.

## 34. Ion: định dạng dữ liệu có mô hình số phong phú

Amazon Ion là định dạng dữ liệu tự mô tả, có cả text và binary representation. Ion có kiểu số nguyên, float và decimal. Ion integer hỗ trợ độ chính xác lớn, còn decimal có mô hình thập phân với exponent/scale riêng.

Ion phù hợp với các hệ thống cần dữ liệu có kiểu phong phú và khả năng biểu diễn số chính xác. Jackson Ion module có thể cung cấp mapper tích hợp với Databind, nhưng mức ánh xạ cụ thể phụ thuộc phiên bản module và Ion Java library.

Khi đánh giá Ion, cần kiểm tra:

- BigInteger có được round-trip không.
- BigDecimal có giữ precision/scale không.
- Float có dùng binary floating-point như kỳ vọng không.
- Timestamp và các typed value khác có ảnh hưởng schema không.
- Consumer không dùng Jackson có đọc đúng binary Ion không.

## 35. Ion integer và BigInteger

Ion integer có thể biểu diễn số nguyên có độ lớn tùy ý, khác với các định dạng chỉ có integer 32/64-bit cơ bản.

Ví dụ:

~~~java
BigInteger value = new BigInteger(
    "999999999999999999999999999999999999999999999999"
);
~~~

Với Ion, khả năng biểu diễn của định dạng phù hợp với BigInteger. Tuy nhiên, cần kiểm tra Jackson Ion module có ánh xạ trực tiếp giá trị đó về BigInteger trong phiên bản sử dụng hay không.

Định dạng hỗ trợ không đồng nghĩa mọi thư viện ngôn ngữ đều có API thuận tiện giống nhau. Nếu dữ liệu được trao đổi đa ngôn ngữ, cần test với Ion implementation của consumer.

## 36. Ion decimal

Ion decimal là kiểu thập phân có precision tùy ý theo mô hình Ion, khác với binary floating-point. Nó phù hợp với số tiền và dữ liệu cần giữ chữ số thập phân chính xác.

Ion decimal có thể lưu giá trị như:

~~~text
123.4500
~~~

và giữ thông tin decimal theo mô hình định dạng. Tuy nhiên, ứng dụng cần xác định có yêu cầu bảo toàn exponent/scale hay chỉ cần giá trị số học.

Khi ánh xạ vào Java BigDecimal, hãy test:

- Precision lớn.
- Scale dương và âm.
- Trailing zeros.
- Số rất nhỏ và rất lớn.
- Giá trị âm.
- Round-trip qua binary Ion.

## 37. So sánh decimal giữa BSON, CBOR, Avro, Protobuf và Ion

| Định dạng | Cách biểu diễn decimal | Giới hạn/điều kiện chính |
|---|---|---|
| BSON | Decimal128 | Precision hữu hạn 34 chữ số có nghĩa; exponent hữu hạn |
| CBOR | Decimal fraction tag, mantissa/exponent | Cần consumer hiểu tag và module hỗ trợ |
| Avro | Logical decimal trên bytes/fixed | Precision và scale nằm trong schema |
| Protobuf | Không có primitive decimal chuẩn | Cần custom message, integer+scale hoặc string |
| Ion | Decimal native | Precision lớn; kiểm tra mapping Java/module |
| Smile | Hỗ trợ số lớn theo khả năng Smile/Jackson | Kiểm tra module, scale và consumer |

Nếu yêu cầu tiền tệ với scale cố định và schema quản lý tập trung, Avro decimal hoặc một Protobuf Decimal message có thể phù hợp. Nếu cần decimal có precision lớn và không muốn schema định nghĩa từng field, Ion hoặc CBOR decimal tag có thể đáng xem xét. Nếu làm việc với MongoDB, Decimal128 là lựa chọn native nhưng cần chấp nhận giới hạn precision.

Không có một định dạng thắng trong mọi trường hợp. Hãy chọn theo precision, interoperability, schema governance và hỗ trợ thư viện.

## 38. Độ chính xác binary floating-point

Float và double lưu giá trị theo hệ nhị phân. Nhiều số thập phân không có biểu diễn nhị phân hữu hạn:

~~~java
double value = 0.1;
System.out.println(value);
~~~

Giá trị lưu trong binary64 gần với 0.1 nhưng không chính xác tuyệt đối. Điều này không phải lỗi của Smile, CBOR, BSON, Avro hay Protobuf; đó là đặc tính của IEEE 754 binary floating-point.

Nếu serialize một double sang định dạng khác rồi đọc lại double, giá trị thường có thể round-trip theo bit pattern tùy định dạng và module. Nhưng nếu convert BigDecimal thành double trước khi serialize, precision decimal đã mất từ trước.

Để giữ decimal chính xác, hãy dùng decimal representation hoặc integer minor units với quy tắc scale rõ ràng.

## 39. BigDecimal.equals và compareTo trong kiểm thử

BigDecimal:

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");
~~~

Hai giá trị có cùng giá trị số học:

~~~java
a.compareTo(b) == 0
~~~

nhưng:

~~~java
a.equals(b) == false
~~~

vì scale khác nhau. Khi kiểm thử round-trip:

- Dùng compareTo nếu chỉ quan tâm giá trị số học.
- Dùng equals nếu scale là một phần hợp đồng.
- Kiểm tra scale riêng nếu cần bảo toàn định dạng decimal.

Một test chỉ dùng compareTo có thể bỏ qua việc format scale đã bị thay đổi.

## 40. BigInteger và overflow

BigInteger không bị giới hạn ở 64-bit, nhưng các wire format có thể có giới hạn. Trước khi chuyển:

~~~java
BigInteger value = new BigInteger("999999999999999999999");
long narrowed = value.longValue();
~~~

longValue() có thể bỏ các bit cao và không báo overflow. Nếu cần chuyển an toàn:

~~~java
long exact = value.longValueExact();
~~~

Phương thức exact ném ArithmeticException nếu giá trị không vừa long.

Tương tự, khi đọc wire value vào int/long, cần kiểm tra module có từ chối giá trị ngoài miền hay có coercion. Đừng dùng một phép cast hẹp rồi giả định dữ liệu được bảo toàn.

## 41. Unsigned integer trong Java

Java primitive int và long là signed. Một định dạng hỗ trợ unsigned 64-bit có thể mang giá trị lớn hơn Long.MAX_VALUE.

Với uint32:

~~~java
int raw = -1;
long unsigned = Integer.toUnsignedLong(raw);
~~~

unsigned có giá trị 4294967295.

Với uint64, Java cung cấp một số helper như Long.toUnsignedString và Long.compareUnsigned. Nếu cần số học tổng quát hoặc chuyển thành decimal, có thể cần BigInteger được tạo từ biểu diễn unsigned.

Không nên:

- So sánh uint64 bằng toán tử signed thông thường.
- Ghi giá trị unsigned thành decimal string mà không định nghĩa rõ.
- Ép uint64 vào BigInteger mà quên xử lý bit dấu.

Trong hệ thống đa ngôn ngữ, cần quy định rõ cách biểu diễn unsigned ở API/application layer.

## 42. NaN, Infinity và negative zero

Các kiểu float/double có giá trị đặc biệt:

- NaN: Not a Number.
- Positive Infinity.
- Negative Infinity.
- Positive zero.
- Negative zero.

Một số định dạng nhị phân có thể biểu diễn NaN và Infinity trực tiếp theo IEEE 754. Nhưng định dạng trung gian hoặc consumer có thể không chấp nhận chúng. JSON chuẩn không có literal NaN/Infinity.

Khi chuyển dữ liệu binary sang JSON, ứng dụng có thể:

- Từ chối giá trị đặc biệt.
- Chuyển thành string theo quy ước.
- Chuyển thành null.
- Dùng một cấu trúc tagged object.

Không nên để quyết định này xảy ra ngầm. Hãy xác định policy trước khi dữ liệu đi qua nhiều định dạng.

Negative zero có thể so sánh bằng zero trong Java nhưng có bit pattern khác. Nếu bit-level fidelity quan trọng, test bằng raw bits:

~~~java
long bits = Double.doubleToRawLongBits(value);
~~~

## 43. Kiểu số khi deserialize vào Object hoặc Map

Khi đọc vào DTO có kiểu rõ:

~~~java
public class Measurement {
    private long count;
    private BigDecimal amount;
}
~~~

Jackson biết kiểu đích cho từng property. Khi đọc vào Object, Map hoặc List không có generic type cụ thể, parser phải chọn Number subtype theo token và cấu hình.

Ví dụ:

~~~java
Map<String, Object> values =
    mapper.readValue(bytes, new TypeReference<Map<String, Object>>() {});
~~~

Một số nguyên có thể thành Integer hoặc Long; số lớn có thể thành BigInteger nếu module/cấu hình hỗ trợ; số thực có thể thành Double nếu không yêu cầu BigDecimal.

Với dữ liệu untyped, có thể cân nhắc:

~~~java
ObjectMapper mapper = new ObjectMapper(factory);
mapper.enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS);
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
~~~

Các feature này yêu cầu parser cung cấp token số phù hợp và module hỗ trợ conversion. Hãy test với từng format thay vì giả định mọi binary parser có cùng hành vi.

## 44. Typed DTO thường an toàn hơn untyped Map cho hợp đồng số

Nếu schema đã biết, dùng DTO có kiểu rõ:

~~~java
public class Invoice {
    private BigInteger invoiceNumber;
    private BigDecimal total;
    private long itemCount;
}
~~~

Điều này giúp Jackson biết kiểu đích và giúp code nghiệp vụ thể hiện rõ yêu cầu precision.

Map<String, Object> linh hoạt nhưng kiểu Number có thể thay đổi theo module, cấu hình hoặc kích thước giá trị. Nếu dùng Map làm boundary giữa nhiều định dạng, cần chuẩn hóa Number subtype sau deserialize.

## 45. Cấu hình coercion và làm tròn

Jackson có các cơ chế coercion giữa scalar types. Tùy module và cấu hình, một giá trị số có thể được chuyển sang kiểu Java khác. Ví dụ double thành int có thể bị từ chối hoặc chuyển theo chính sách.

Không nên dựa vào coercion mặc định cho dữ liệu tài chính hoặc dữ liệu có miền giá trị quan trọng.

Hãy quyết định:

- Có cho phép string số như "123" không?
- Có cho phép decimal vào integer không?
- Nếu có phần thập phân, từ chối hay làm tròn?
- Có cho phép giá trị vượt miền target không?
- Có chấp nhận NaN/Infinity không?

Coercion là quy tắc ứng dụng, không nên xem là đặc tính bảo đảm chung của mọi định dạng nhị phân.

## 46. Định dạng có schema và định dạng tự mô tả

Smile và CBOR có cấu trúc token cho biết loại dữ liệu trong payload. BSON cũng gắn type marker cho từng value. Ion có type system tự mô tả.

Avro và Protobuf phụ thuộc schema để biết field nào tồn tại và kiểu số nào đang được mã hóa. Binary payload không tự mang đầy đủ tên field và schema theo cùng cách một document tự mô tả.

Điều này ảnh hưởng việc kiểm tra kiểu số:

| Đặc điểm | Tự mô tả hoặc token-based | Schema-based |
|---|---|---|
| Kiểu số tại từng value | Có thể suy ra từ token/type marker | Đọc theo schema |
| Field name | Thường có trong payload hoặc token | Thường do schema cung cấp |
| Đọc payload thiếu schema | Có thể đọc cấu trúc cơ bản | Thường cần writer schema/descriptor |
| Đổi kiểu field | Reader có thể thấy kiểu wire mới | Cần schema evolution rules |
| Kiểm tra precision | Dựa vào token và target type | Dựa vào schema và logical type |

Không nên đánh giá hiệu quả của format chỉ dựa vào kích thước bytes. Schema-based format có thể nhỏ hơn do không lặp field names, nhưng yêu cầu quản lý schema chặt chẽ.

## 47. So sánh đặc điểm tổng thể của các định dạng

| Định dạng | Schema | Numeric strengths | Hạn chế cần chú ý |
|---|---|---|---|
| Smile | Không bắt buộc schema ngoài model/contract | Token số phong phú, tích hợp Jackson tự nhiên | Interoperability phụ thuộc Smile implementation |
| CBOR | Không bắt buộc cho cấu trúc cơ bản | Integer 64-bit, bignum tag, float16/32/64, decimal fraction tag | Tag cần consumer hiểu; module version matters |
| BSON | Document có type marker | int32/int64/double/Decimal128 | BigInteger không native; Decimal128 có precision hữu hạn |
| Avro | Có schema | int/long/float/double và logical decimal | Schema resolution; decimal precision/scale cố định |
| Protobuf | Có .proto descriptor | Signed/unsigned, ZigZag, fixed-width, float/double | Không có decimal primitive; unsigned Java cần xử lý |
| Ion | Type system tự mô tả | BigInteger và decimal native | Cần kiểm tra hỗ trợ module và hệ sinh thái consumer |

## 48. MessagePack trong hệ sinh thái mở rộng

MessagePack là một định dạng nhị phân kiểu JSON, có các dạng integer signed/unsigned và float32/float64. Một số Jackson module của cộng đồng hỗ trợ MessagePack, nhưng không nên mặc định nó là module chính thức hoặc có cùng mức hỗ trợ với Smile/CBOR.

MessagePack có thể biểu diễn integer đến 64-bit theo các dạng của chuẩn. Nó không có kiểu BigDecimal native phổ quát tương đương BSON Decimal128 hoặc Avro logical decimal. Giá trị lớn hơn 64-bit thường cần extension type hoặc quy ước ứng dụng.

Nếu dự án dùng MessagePack:

- Xác định module và version cụ thể.
- Kiểm tra BigInteger/BigDecimal có dùng extension type hay string không.
- Kiểm tra consumer ngoài Java có cùng quy ước extension không.
- Test integer unsigned và floating-point ở biên.

## 49. Không nhầm kiểu số của định dạng với kiểu số của database

Một ứng dụng có thể đọc BSON Decimal128 rồi ghi vào database decimal khác, hoặc đọc Avro decimal rồi chuyển thành SQL DECIMAL.

Mỗi hệ thống có precision/scale riêng:

- BSON Decimal128 có precision tối đa 34 chữ số có nghĩa.
- Avro decimal định nghĩa precision/scale trong schema.
- SQL DECIMAL thường có precision/scale do column schema quy định.
- Java BigDecimal không có giới hạn precision cố định ở mức kiểu.

Một phép round-trip qua nhiều hệ thống chỉ an toàn nếu giao của các miền giá trị đều bao phủ dữ liệu cần lưu.

Ví dụ, BigDecimal precision 40 có thể tồn tại trong Java nhưng không vừa Decimal128 hoặc một SQL DECIMAL(34, 10). Cần kiểm tra trước khi ghi, không chờ database tự làm tròn.

## 50. Thiết kế decimal bằng integer minor units

Với tiền tệ có scale cố định, có thể lưu đơn vị nhỏ nhất dưới dạng integer:

~~~java
long amountInCents = 12345;
~~~

Giá trị tương ứng 123.45 nếu scale là 2.

Ưu điểm:

- Integer encoding thường đơn giản và chính xác.
- Tránh sai số binary floating-point.
- Có thể dùng Avro long hoặc Protobuf int64.

Giới hạn:

- Phải biết scale/currency ở mọi consumer.
- Một số tiền có thể có số chữ số thập phân khác nhau tùy currency.
- Miền long có giới hạn.
- Đổi scale cần migration rõ ràng.

Không nên chỉ gửi integer 12345 mà không ghi rõ nó là minor units của loại tiền nào hoặc scale bao nhiêu.

## 51. Thiết kế decimal bằng unscaled value và scale

Một representation tổng quát hơn:

~~~json
{
  "unscaledValue": "1234500",
  "scale": 4
}
~~~

Giá trị là unscaledValue × 10^-scale. Có thể chuyển sang Java:

~~~java
BigDecimal value = new BigDecimal(
    new BigInteger(unscaledValue),
    scale
);
~~~

Trong binary schema, unscaledValue có thể là bytes hoặc BigInteger representation; scale là integer. Cần định nghĩa:

- Byte order.
- Signed integer encoding.
- Scale range.
- Precision limit.
- Canonicalization.

Representation này linh hoạt nhưng yêu cầu contract rõ và code chuyển đổi ở mọi ngôn ngữ.

## 52. Thiết kế decimal bằng string

Một lựa chọn đơn giản là serialize BigDecimal thành decimal string:

~~~json
{
  "amount": "12345678901234567890.123400"
}
~~~

Ưu điểm:

- Giữ chữ số thập phân.
- Không phụ thuộc floating-point.
- Dễ đọc và hỗ trợ trong nhiều ngôn ngữ.

Nhược điểm:

- Consumer phải parse string.
- Cần định nghĩa format/canonical form.
- Không còn là numeric type ở tầng wire.
- Có thể làm validation và query khó hơn.

Trong một số định dạng binary, string vẫn được mã hóa thành text bytes. Điều đó không làm nó trở thành decimal native.

## 53. Kiểm tra độ rộng integer bằng các giá trị biên

Tạo tập giá trị đại diện:

~~~java
List<BigInteger> integerCases = List.of(
    BigInteger.valueOf(Integer.MIN_VALUE),
    BigInteger.valueOf(Integer.MAX_VALUE),
    BigInteger.valueOf(Long.MIN_VALUE),
    BigInteger.valueOf(Long.MAX_VALUE),
    BigInteger.ONE.shiftLeft(63),
    BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE),
    BigInteger.ONE.shiftLeft(100)
);
~~~

Với mỗi format, xác định:

- Giá trị nào được ghi trực tiếp.
- Giá trị nào cần bignum/tag/logical type.
- Giá trị nào bị từ chối.
- Giá trị nào cần custom representation.
- Reader trả về kiểu Java nào.

Không chỉ test round-trip với cùng mapper. Nếu dữ liệu trao đổi giữa nhiều ngôn ngữ, test bằng implementation của consumer thực tế.

## 54. Kiểm tra decimal bằng bộ dữ liệu đại diện

Một tập test hữu ích:

~~~java
List<BigDecimal> decimalCases = List.of(
    new BigDecimal("0.1"),
    new BigDecimal("1.00"),
    new BigDecimal("123.4500"),
    new BigDecimal("-999999999999999999.9999"),
    new BigDecimal("1E+20"),
    new BigDecimal("1E-20"),
    new BigDecimal("12345678901234567890123456789012345.6")
);
~~~

Các giá trị này kiểm tra:

- Decimal thường gặp.
- Scale và trailing zero.
- Giá trị âm.
- Exponent dương.
- Exponent âm.
- Precision rất lớn.

Với BSON Decimal128, một số giá trị có thể vượt precision/range. Test phải xác nhận việc từ chối hoặc rounding đúng chính sách thay vì loại bỏ case thất bại.

## 55. Kiểm tra float và double

Tập test có thể gồm:

~~~java
double[] values = {
    0.1d,
    -0.0d,
    Double.MIN_VALUE,
    Double.MIN_NORMAL,
    Double.MAX_VALUE,
    Double.NaN,
    Double.POSITIVE_INFINITY,
    Double.NEGATIVE_INFINITY
};
~~~

Không phải mọi format hoặc module đều xử lý các giá trị này giống nhau. Nếu format không hỗ trợ một giá trị hoặc module từ chối, hãy coi đó là kết quả kiểm tra quan trọng.

Đối với round-trip bit-level:

~~~java
long before = Double.doubleToRawLongBits(value);
long after = Double.doubleToRawLongBits(restored);
assertEquals(before, after);
~~~

Chỉ dùng bit-level equality khi contract cần giữ nguyên IEEE representation. Với tính toán thông thường, có thể dùng delta/tolerance nhưng phải chọn sai số phù hợp miền nghiệp vụ.

## 56. Ví dụ kiểm tra round-trip Smile và CBOR

Một test có thể dùng cùng một cấu trúc dữ liệu với hai factory:

~~~java
static void assertNumericRoundTrip(JsonFactory factory)
        throws Exception {

    ObjectMapper mapper = new ObjectMapper(factory);

    Map<String, Object> source = new LinkedHashMap<>();
    source.put("count", new BigInteger("123456789012345678901234"));
    source.put("amount", new BigDecimal("123.4500"));
    source.put("ratio", 0.1d);

    byte[] bytes = mapper.writeValueAsBytes(source);

    ObjectReader reader = mapper.readerFor(
        new TypeReference<Map<String, Object>>() {}
    ).with(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
     .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

    Map<String, Object> restored = reader.readValue(bytes);

    assertEquals(
        source.get("count"),
        restored.get("count")
    );
    assertEquals(
        0,
        ((BigDecimal) source.get("amount"))
            .compareTo((BigDecimal) restored.get("amount"))
    );
}
~~~

Gọi với SmileFactory và CBORFactory nếu module/phiên bản đang dùng hỗ trợ các kiểu trên:

~~~java
assertNumericRoundTrip(new SmileFactory());
assertNumericRoundTrip(new CBORFactory());
~~~

Đây là khung kiểm thử; nếu module biểu diễn BigDecimal hoặc BigInteger theo một quy ước khác, hãy dùng reader/serializer tương ứng và kiểm tra representation thực tế. Không nên ép mọi format vào một kỳ vọng chung khi chuẩn của chúng khác nhau.

## 57. Ví dụ kiểm tra BigDecimal typed property

Khi DTO khai báo BigDecimal:

~~~java
public class MoneyRecord {
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Test:

~~~java
MoneyRecord original = new MoneyRecord();
original.setAmount(new BigDecimal("123.4500"));

byte[] bytes = mapper.writeValueAsBytes(original);
MoneyRecord restored =
    mapper.readValue(bytes, MoneyRecord.class);

assertEquals(
    original.getAmount().scale(),
    restored.getAmount().scale()
);
assertEquals(
    0,
    original.getAmount().compareTo(restored.getAmount())
);
~~~

Typed property giúp tránh việc parser chọn Double cho một decimal khi đọc vào Object. Tuy nhiên, format và module vẫn phải có representation phù hợp để giữ BigDecimal.

## 58. Kiểm tra schema Avro decimal

Với Avro, test phải sử dụng writer schema có logical decimal:

~~~json
{
  "type": "record",
  "name": "Payment",
  "fields": [
    {
      "name": "amount",
      "type": {
        "type": "bytes",
        "logicalType": "decimal",
        "precision": 18,
        "scale": 4
      }
    }
  ]
}
~~~

Kiểm tra:

- BigDecimal có precision không vượt schema.
- Scale có khớp hoặc được chuyển đổi theo quy tắc được hỗ trợ.
- Writer và reader cùng hiểu logical type.
- Schema resolution khi thay precision/scale.
- Consumer GenericRecord/SpecificRecord có đọc cùng giá trị không.

Không nên chỉ test Jackson Avro module mà bỏ qua Avro schema resolution, vì schema là một phần của wire contract.

## 59. Kiểm tra Protobuf unsigned và decimal message

Với Protobuf, tạo fixture có:

- int32 và int64 âm/dương.
- sint32/sint64 âm nhỏ.
- uint32 gần giới hạn 2^32-1.
- uint64 có bit cao nhất được bật.
- fixed32/fixed64 và sfixed32/sfixed64.
- float/double có giá trị đặc biệt nếu ứng dụng cho phép.

Nếu dùng DecimalValue message, test:

- Unscaled integer âm và dương.
- Scale 0, dương và âm nếu schema cho phép.
- Precision tối đa.
- Byte order và signed encoding.
- Giá trị không hợp lệ hoặc scale vượt giới hạn.

Protobuf generated Java class có kiểu số cố định; không thể chỉ thay field Java thành BigInteger rồi mong wire schema tự thay đổi.

## 60. Kiểm tra BSON Decimal128

Với BSON, test cần xác định rõ kiểu BSON được tạo ra:

- Java int có thành BSON int32 không?
- Java long có thành BSON int64 không?
- Java double có thành BSON double không?
- BigDecimal có thành Decimal128 hay một kiểu khác?

Nếu dùng BSON driver, kiểm tra BSON type của field trong document sau khi encode. Đừng chỉ deserialize lại bằng cùng một codec vì cả encode và decode có thể cùng áp dụng một conversion không mong muốn.

Với Decimal128:

- Test precision tối đa 34 chữ số có nghĩa.
- Test exponent/range.
- Test số âm, zero và trailing zeros.
- Test NaN/Infinity nếu miền dữ liệu có sử dụng Decimal128 special values.
- Test BigDecimal vượt giới hạn và xác nhận chính sách reject/rounding.

## 61. Kiểm tra Ion integer và decimal

Với Ion, test riêng:

- BigInteger vượt 64-bit.
- BigDecimal precision lớn.
- Decimal có scale khác nhau nhưng cùng giá trị.
- Exponent dương/âm.
- Float binary64.
- Null có type nếu hợp đồng sử dụng typed null.

Nếu Jackson Ion module trả về một kiểu Ion-specific thay vì BigInteger/BigDecimal, cần thêm conversion ở boundary. Hãy kiểm tra cả Ion Java API và Jackson Databind mapping.

## 62. Không chỉ test cùng một serializer và parser

Round-trip qua cùng mapper có thể che giấu một lỗi tương thích. Ví dụ writer tạo một extension tag riêng và reader cùng module hiểu tag đó, nhưng consumer khác không hiểu.

Nên có ba lớp test:

1. **Round-trip nội bộ:** cùng module ghi rồi đọc.
2. **Interoperability:** một implementation độc lập đọc dữ liệu do Jackson tạo và ngược lại.
3. **Wire inspection:** kiểm tra type marker, schema, BSON type, CBOR tag hoặc Avro/Protobuf field type.

Nếu hệ thống chỉ giao tiếp giữa các service Java cùng version, round-trip vẫn hữu ích nhưng chưa đủ cho việc nâng cấp thư viện hoặc thêm consumer khác ngôn ngữ.

## 63. Đặc điểm kích thước và hiệu năng

Khả năng số chỉ là một tiêu chí. Các định dạng còn khác nhau về:

- Kích thước payload.
- Chi phí encode/decode.
- Tự mô tả hay cần schema.
- Khả năng stream.
- Hỗ trợ ngôn ngữ.
- Khả năng tương thích lâu dài.
- Công cụ inspect/debug.

Một số nguyên nhỏ có thể được mã hóa rất gọn bằng varint hoặc integer có độ dài biến đổi. Fixed-width có kích thước dễ dự đoán. Decimal tag có thể thêm overhead nhưng giữ semantics tốt hơn double.

Không nên kết luận format nào luôn nhỏ nhất. Kích thước phụ thuộc tên field, giá trị, schema, token distribution, compression và cách module ghi dữ liệu.

## 64. Chọn format theo nhu cầu số

| Nhu cầu | Lựa chọn đáng cân nhắc | Lý do |
|---|---|---|
| POJO kiểu JSON, muốn tích hợp Jackson đơn giản | Smile | Cấu trúc gần JSON và token nhị phân |
| Interoperability theo chuẩn binary tổng quát, cần bignum/tag | CBOR | Có integer, tag bignum và decimal fraction |
| Document MongoDB, cần Decimal128 | BSON | Kiểu số phù hợp hệ sinh thái MongoDB |
| Event có schema quản lý, decimal precision/scale rõ | Avro | Schema và logical decimal |
| RPC/message có schema, cần unsigned và wire size tối ưu | Protobuf | Nhiều kiểu integer, ZigZag, fixed-width |
| Cần integer/decimal precision lớn trong data model tự mô tả | Ion | Mô hình số phong phú |

Đây là định hướng ban đầu. Hãy chọn sau khi xác nhận thư viện ở cả producer và consumer, khả năng schema governance và các giới hạn dữ liệu thật.

## 65. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Nghĩ binary luôn chính xác hơn JSON | Vẫn có thể mất precision qua float/double | Chọn numeric representation phù hợp |
| Lưu tiền bằng double | Sai số thập phân | Dùng decimal hoặc integer minor units |
| Ép BigInteger thành long | Tràn hoặc mất bit | Kiểm tra miền, dùng exact conversion |
| Dùng uint64 như signed long | Giá trị lớn hiển thị âm | Dùng unsigned helper hoặc BigInteger |
| Nghĩ BSON Decimal128 chứa mọi BigDecimal | Precision/range bị giới hạn | Kiểm tra 34-digit precision và exponent |
| Nghĩ Avro bytes tự động là BigDecimal | Logical type có thể bị bỏ qua | Dùng schema decimal và conversion |
| Nghĩ Protobuf có decimal primitive | Không có kiểu decimal chuẩn | Thiết kế message hoặc string representation |
| Đọc float thành BigDecimal rồi cho rằng chính xác | Sai số binary đã có từ trước | Ghi decimal từ nguồn chính xác |
| Chỉ test số nhỏ | Bỏ sót overflow/precision boundary | Test min/max và giá trị vượt miền |
| Chỉ round-trip cùng module | Không phát hiện lỗi interoperability | Test implementation độc lập |
| Không phân biệt schema với wire bytes | Reader không thể giải mã đúng | Quản lý writer/reader schema |

## 66. Checklist đánh giá một module định dạng nhị phân

Trước khi dùng trong production:

- Xác định module và version cụ thể.
- Kiểm tra chuẩn định dạng hỗ trợ numeric types nào.
- Kiểm tra module ánh xạ Java byte/short/int/long ra sao.
- Kiểm tra BigInteger và BigDecimal trực tiếp.
- Kiểm tra unsigned integer nếu format có hỗ trợ.
- Kiểm tra float/double, NaN, Infinity và negative zero.
- Kiểm tra decimal precision, scale và exponent.
- Kiểm tra overflow và coercion.
- Kiểm tra untyped Map/Object Number subtype.
- Kiểm tra schema/logical type/tag nếu định dạng cần chúng.
- Kiểm tra interoperability với consumer khác thư viện/ngôn ngữ.
- Kiểm tra nâng cấp module có làm thay đổi wire encoding không.
- Lưu fixture binary hoặc schema versioned để regression test.

## 67. Quy trình kiểm tra thực tế

Một quy trình đánh giá có thể thực hiện như sau:

1. Liệt kê kiểu Java thực tế của từng field số.
2. Ghi miền giá trị tối thiểu/tối đa theo nghiệp vụ.
3. Ghi precision/scale cần giữ cho decimal.
4. Chọn format và module Jackson dự kiến.
5. Ghi dữ liệu biên thành fixture.
6. Serialize và kiểm tra wire type/marker nếu có thể.
7. Deserialize vào đúng kiểu Java.
8. So sánh giá trị, scale hoặc bit pattern theo yêu cầu.
9. Đọc dữ liệu bằng consumer độc lập.
10. Kiểm tra schema evolution và backward compatibility.
11. Đo kích thước và hiệu năng trên dữ liệu đại diện.
12. Ghi rõ các giá trị không được hỗ trợ và chính sách từ chối/chuyển đổi.

Sơ đồ:

~~~text
Yêu cầu nghiệp vụ về số
          |
          v
Chọn Java numeric type
          |
          v
Chọn binary format + schema/tag
          |
          v
Kiểm tra khả năng của Jackson module
          |
          v
Round-trip + boundary tests
          |
          v
Interoperability tests
          |
          v
Chấp nhận hoặc chọn representation khác
~~~

## 68. Nguyên tắc thực hành

- Đánh giá chuẩn wire format và Jackson module như hai lớp riêng.
- Dùng int/long khi miền giá trị nằm trong giới hạn tương ứng.
- Dùng BigInteger khi cần integer vượt 64-bit và format/module hỗ trợ hoặc có representation rõ.
- Không dùng float/double cho tiền tệ cần decimal chính xác.
- Dùng BigDecimal, decimal logical type, Decimal128 hoặc unscaled integer theo giới hạn của format.
- Nhớ BSON Decimal128 chỉ có precision hữu hạn 34 chữ số có nghĩa.
- Nhớ Avro decimal cần schema precision/scale.
- Nhớ Protobuf không có decimal primitive và unsigned Java cần xử lý.
- Nhớ CBOR bignum/decimal fraction là tag, consumer phải hiểu.
- Nhớ Ion có integer/decimal phong phú nhưng vẫn cần kiểm tra mapping.
- Kiểm tra Smile/CBOR/format-specific module trên đúng version.
- Phân biệt giá trị số học với scale của BigDecimal.
- Kiểm tra overflow, coercion và unsigned semantics.
- Kiểm tra NaN, Infinity, negative zero khi miền dữ liệu cho phép.
- Test typed DTO và untyped Map/Object riêng.
- Không chỉ round-trip bằng cùng mapper; kiểm tra wire và consumer độc lập.
- Chọn format dựa trên dữ liệu, schema, interoperability và yêu cầu vận hành.

Khả năng biểu diễn số của một định dạng nhị phân không chỉ được quyết định bởi việc nó có token integer hay float. Cần biết độ rộng, signedness, decimal precision, scale, schema và cách Jackson module ánh xạ các giá trị đó vào Java. Khi kiểm tra cả chuẩn định dạng, phiên bản module, biên dữ liệu và consumer độc lập, ứng dụng mới có thể chọn representation bảo toàn giá trị thay vì chỉ tạo ra payload đọc được trong một lần round-trip nội bộ.
