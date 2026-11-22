# BigDecimal: Constructor nhận `double` và nhiễu biểu diễn nhị phân

Trong Java, `java.math.BigDecimal` cho phép tính toán số **thập phân** với unscaled value và scale, không phải chịu sai số làm tròn nhị phân ở mỗi phép cộng, trừ, nhân như `double`. Tuy nhiên, **cách tạo `BigDecimal` quan trọng không kém cách tính**. Nếu đầu vào là một `double` vốn đã xấp xỉ số thập phân dự định, constructor `new BigDecimal(double)` sẽ **bảo toàn chính xác giá trị nhị phân đã nhận**, kể cả độ lệch nhỏ của nó, thay vì tự đoán số thập phân mà người viết mã muốn.

```java
import java.math.BigDecimal;

BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromFactory = BigDecimal.valueOf(0.1);

System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(fromText);    // 0.1
System.out.println(fromFactory); // 0.1
```

Dòng dài không phải “`BigDecimal` tạo ra sai số mới”. Nó là **cách viết thập phân chính xác của giá trị `double` đã bị lượng tử hóa theo nhị phân trước đó**. Hiểu điểm này giúp tránh lỗi khi tính tiền, đọc dữ liệu decimal, quy đổi đơn vị và đưa kết quả số vào báo cáo.

Bài học này tập trung vào: hai lớp số, nguồn gốc nhiễu nhị phân, hợp đồng của `BigDecimal(double)`, `BigDecimal.valueOf(double)`, `BigDecimal(String)`, scale/precision, trường hợp có và không có nhiễu, ảnh hưởng lên phép tính và so sánh, rounding, giới hạn khi dữ liệu đã đi qua `double`, và những cách chọn constructor an toàn.

## 1. Vì sao `0.1` không phải một số `double` thập phân chính xác?

`double` dùng **IEEE 754 binary64**, gồm thông tin dấu, số mũ và phần trị (*significand*) được biểu diễn theo cơ số **2**. Trong khi đó, chữ số `0.1` theo toán học là **một phần mười**, tức `1/10`.

Một phân số thập phân có thể biểu diễn hữu hạn theo nhị phân chỉ khi, sau khi rút gọn, mẫu số là lũy thừa của 2. `1/10` có mẫu số gồm cả thừa số 5, nên **không có khai triển nhị phân hữu hạn**.

Trình biên dịch Java phải chọn một giá trị binary64 gần với `0.1`. Giá trị thực được lưu là:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Đây chính là giá trị thập phân chính xác của bit pattern binary64 được chọn cho literal `0.1`, **không** phải nội dung gốc “một phần mười” ở độ chính xác vô hạn.

### Sơ đồ đường đi dữ liệu

```text
Mong muốn toán học:  0.1  (1/10)
          |
          | Gán cho literal / biến double
          v
binary64 gần nhất:   0.1000000000000000055511...
          |
          | new BigDecimal(double) bảo toàn chính xác giá trị binary64
          v
BigDecimal:          0.1000000000000000055511...
```

**Chốt:** `BigDecimal(double)` không “cố tình thêm nhiễu”; nó nhận đầu vào đã xấp xỉ và chuyển **chính xác** giá trị đó sang một số thập phân. Độ dài chuỗi là dấu hiệu của việc nguồn dữ liệu vốn là binary64.

### Thử các phân số khác

| Giá trị toán học | Có biểu diễn nhị phân hữu hạn? | `new BigDecimal(double)` khi nhận literal |
| --- | --- | --- |
| `0.5 = 1/2` | Có | `0.5` |
| `0.25 = 1/4` | Có | `0.25` |
| `0.125 = 1/8` | Có | `0.125` |
| `0.1 = 1/10` | Không | Một chuỗi thập phân dài, lớn hơn 0.1 một chút |
| `0.2 = 1/5` | Không | Một chuỗi thập phân dài |
| `0.3 = 3/10` | Không | Một chuỗi thập phân dài, tùy giá trị binary64 được chọn |

**Không phải mọi giá trị `double` đều tạo ra chuỗi dài.** Nhiều số nguyên nhỏ, phân số có mẫu số là lũy thừa của 2 và một số giá trị khác có biểu diễn thập phân gọn. Quyết định sai nhất là giả định `new BigDecimal(double)` luôn tương đương `new BigDecimal("giá-trị-muốn-nhập")`.

## 2. `BigDecimal` lưu giá trị như thế nào?

Về mặt khái niệm, giá trị số của một `BigDecimal` là:

\[
\mathrm{value} = \mathrm{unscaledValue} \times 10^{-\mathrm{scale}}
\]

`unscaledValue()` trả về một `BigInteger`; `scale()` trả số nguyên chỉ vị trí dấu thập phân. Có hai phần này, `BigDecimal` mô tả được số thập phân chính xác mà không cần giữ một giá trị `double` bên trong.

Ví dụ:

```java
BigDecimal value = new BigDecimal("12.34");

System.out.println(value.unscaledValue()); // 1234
System.out.println(value.scale());         // 2
```

`1234 × 10^-2 = 12.34`.

Với dữ liệu từ `new BigDecimal(0.1)`, phần không tỷ lệ là một số nguyên có rất nhiều chữ số, còn scale lớn hơn vì phải viết chính xác giá trị binary64 ở cơ số 10:

```java
BigDecimal fromDouble = new BigDecimal(0.1);

System.out.println(fromDouble.scale()); // 55
System.out.println(fromDouble.unscaledValue());
// 1000000000000000055511151231257827021181583404541015625
```

Điều này giải thích tại sao toán học trên các `BigDecimal` tạo từ `double` có thể kéo theo nhiều chữ số thập phân: chúng thật sự chứa **các giá trị decimal với precision/scale lớn**, và phép toán BigDecimal mặc định trên nhiều thao tác cố gắng giữ kết quả chính xác theo các toán hạng đó.

### `precision` không phải `scale`

- **Scale**: số mũ thập phân bị trừ đi (đối với scale dương, thường là số chữ số sau dấu phẩy).
- **Precision**: số chữ số trong `unscaledValue` (bỏ qua dấu), theo hợp đồng API.

```java
BigDecimal a = new BigDecimal("1.2300");
System.out.println(a.scale());     // 4
System.out.println(a.precision()); // 5

BigDecimal b = new BigDecimal("1.23");
System.out.println(b.scale());     // 2
System.out.println(b.precision()); // 3
```

Hai giá trị có thể bằng nhau về mặt số học mà khác scale. Vì vậy, khi quan sát chuỗi dài do `new BigDecimal(double)`, cần xét cả **giá trị số** lẫn **biểu diễn**; chỉ nhìn số lượng chữ số hiển thị không giải quyết được nguyên nhân.

## 3. Hợp đồng của `new BigDecimal(double)`

Oracle Java SE 17 API mô tả constructor:

```java
public BigDecimal(double val)
```

Nó tạo một `BigDecimal` có giá trị đúng bằng **giá trị floating-point nhị phân của đối số `double`**. Scale được chọn nhỏ nhất để giá trị đó có thể viết như một số nguyên nhân `10^-scale`.

```java
BigDecimal x = new BigDecimal(0.1);
System.out.println(x.toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

Hệ quả:
1. Constructor **không** đọc lại token `0.1` trong source để đoán ý định của người viết.
2. Constructor **không** dùng chuỗi rút gọn từ `Double.toString`.
3. Nó **không tự làm tròn** thành một chữ số thập phân vì “có vẻ giống 0.1”.
4. Giá trị của `BigDecimal` được tạo ra **chính xác đối với đầu vào `double`**, dù khác giá trị decimal mà ta mong muốn.
5. Nếu đối số là `NaN` hoặc `Infinity`, constructor ném `NumberFormatException`: BigDecimal không biểu diễn số không hữu hạn.
6. Với `-0.0`, dấu zero âm của binary64 không được giữ dưới dạng một trạng thái signed-zero BigDecimal riêng.

Tính “exact” ở đây có nghĩa **chuyển đổi đầu vào binary64 sang decimal không mất thêm thông tin số học của giá trị nguồn**, không có nghĩa **khôi phục một phân số thập phân trước khi nó được chuyển thành binary64**.

### Cùng một literal trông đơn giản nhưng giá trị khác

```java
BigDecimal exactBinary = new BigDecimal(0.1);
BigDecimal exactDecimal = new BigDecimal("0.1");

System.out.println(exactBinary.equals(exactDecimal));    // false
System.out.println(exactBinary.compareTo(exactDecimal)); // 1
```

`compareTo` trả dương bởi giá trị exact binary64 của `0.1` hơi **lớn hơn** đúng 0.1. Trường hợp này không phải chỉ khác `scale`: **hai giá trị toán học thực sự khác nhau**.

## 4. `new BigDecimal("0.1")`: tạo từ chữ số decimal gốc

Constructor:

```java
BigDecimal correctDecimal = new BigDecimal("0.1");
```

đọc **chuỗi ký tự thập phân**. Nó không ép chuỗi `"0.1"` qua `double` trước. Vì vậy, nó biểu diễn **chính xác phân số `1/10`**, với unscaled value 1 và scale 1.

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
```

Đây là cách phù hợp nếu dữ liệu vốn đã là **text decimal có ý nghĩa chính xác**: tiền tệ, tỷ lệ thập phân, dữ liệu đo được cung cấp với số chữ số cố định, giá trị đọc từ database DECIMAL/NUMERIC hoặc một cột CSV có schema decimal.

### Đừng biến chuỗi thành `double` ở giữa

```java
String input = "0.1";

// Tránh nếu yêu cầu giữ đúng decimal nhập vào:
BigDecimal lossyPath =
        new BigDecimal(Double.parseDouble(input));

// Giữ được decimal đúng như ký tự:
BigDecimal exactPath = new BigDecimal(input);
```

Dòng thứ nhất đi qua `double` và tạo giá trị binary64 xấp xỉ; dòng thứ hai đọc trực tiếp văn bản decimal. Sau khi dữ liệu đã qua `double`, không có API nào tự biết chắc nguồn gốc **ban đầu** có bao nhiêu chữ số, scale hay đơn vị.

### Hợp đồng nguồn quan trọng hơn tên constructor

`new BigDecimal("0.1")` đúng khi `"0.1"` là một chuỗi số thập phân hợp lệ theo schema. Không nên lấy chuỗi đã định dạng cho người đọc như `"1,234.50"` hoặc `"1.234,50"` rồi đưa thẳng cho `BigDecimal(String)`: constructor dùng cú pháp decimal riêng, không tự hiểu dấu phân nhóm locale.

Nếu đầu vào do người dùng nhập, cần parse theo locale/hợp đồng rõ ràng **mà không làm mất precision trước khi tới `BigDecimal`**. Với các thư viện parse số địa phương, hãy đảm bảo chúng có chế độ trả `BigDecimal` trực tiếp khi yêu cầu decimal chính xác, hoặc dùng một parser decimal riêng phù hợp schema.

## 5. `BigDecimal.valueOf(double)`: đường đi qua `Double.toString`

Khi dữ liệu **đã tồn tại dưới dạng `double`**, factory method sau thường được ưu tiên hơn constructor nhận `double`:

```java
BigDecimal friendly = BigDecimal.valueOf(0.1);
System.out.println(friendly); // 0.1
```

Oracle mô tả rằng `BigDecimal.valueOf(double)` dùng **biểu diễn chuỗi chuẩn từ `Double.toString(double)`** rồi tạo `BigDecimal` từ biểu diễn đó.

Về mặt kết quả có thể nghĩ:

```java
double source = 0.1;

BigDecimal a = BigDecimal.valueOf(source);
BigDecimal b = new BigDecimal(Double.toString(source));

System.out.println(a.equals(b)); // true
```

`Double.toString` cung cấp biểu diễn thập phân đủ để parse quay lại giá trị binary64 gốc theo quy tắc chuyển đổi `double`. Với `0.1`, biểu diễn ấy là chuỗi ngắn `"0.1"`. `BigDecimal.valueOf` từ đó tạo ra **số decimal 0.1**.

### Ba cách tạo, ba ý nghĩa

| Cách tạo | Nguồn được diễn giải | Kết quả `0.1` | Khi nào chọn |
| --- | --- | --- | --- |
| `new BigDecimal("0.1")` | Chuỗi decimal gốc | `0.1` chính xác | Khi **có decimal text đáng tin cậy** |
| `BigDecimal.valueOf(0.1)` | `Double.toString` của binary64 đầu vào | `0.1` | Khi **chỉ còn `double`** và muốn cách chuyển decimal theo chuỗi chuẩn |
| `new BigDecimal(0.1)` | Giá trị binary64 chính xác | `0.10000000000000000555...` | Khi **chủ đích cần chính xác giá trị binary64** |

**Không gọi `valueOf(double)` là máy “phục hồi giá trị gốc”**: nó chỉ chọn một cách biểu diễn ngắn và xác định của giá trị `double` đã có. Nếu sai số đã tích lũy trong tính toán `double`, kết quả ấy vẫn xuất hiện.

### Không phục hồi được sai số từ phép toán trung gian

```java
double binarySum = 0.1 + 0.2;

System.out.println(binarySum); // 0.30000000000000004

BigDecimal converted = BigDecimal.valueOf(binarySum);
System.out.println(converted); // 0.30000000000000004
```

Ở đây `Double.toString(binarySum)` là `"0.30000000000000004"`, nên factory giữ kết quả đó dưới dạng decimal. Nó **không sửa** phép cộng double thành decimal 0.3.

Muốn kết quả decimal chính xác:

```java
BigDecimal decimalSum =
        new BigDecimal("0.1").add(new BigDecimal("0.2"));

System.out.println(decimalSum); // 0.3
```

**Quy tắc vận hành:** nếu cần decimal exact, hãy tạo `BigDecimal` **ngay ở ranh giới đầu vào**, không đợi một chuỗi phép toán `double` kết thúc mới chuyển đổi.

## 6. Một thí nghiệm với phép cộng: nhiễu được giữ lại

Cùng hai literal `0.1` và `0.2`:

```java
BigDecimal sumExactOfBinary =
        new BigDecimal(0.1).add(new BigDecimal(0.2));

BigDecimal sumOfDecimalText =
        new BigDecimal("0.1").add(new BigDecimal("0.2"));

BigDecimal afterBinaryAddition =
        BigDecimal.valueOf(0.1 + 0.2);
```

Ba con đường khác nhau:

| Con đường | Giá trị kết quả |
| --- | --- |
| `new BigDecimal(0.1).add(new BigDecimal(0.2))` | `0.3000000000000000166533453693773481063544750213623046875` |
| `new BigDecimal("0.1").add(new BigDecimal("0.2"))` | `0.3` |
| `BigDecimal.valueOf(0.1 + 0.2)` | `0.30000000000000004` |

Các con số khác nhau không mâu thuẫn:
- Con đường 1 chuyển từng binary64 sang BigDecimal **chính xác**, rồi cộng hai giá trị chính xác ấy bằng decimal.
- Con đường 2 bắt đầu từ **decimal exact** và cộng exact.
- Con đường 3 **cộng bằng double trước**, nhận kết quả đã làm tròn nhị phân, rồi chuyển kết quả qua `Double.toString`.

`BigDecimal` không sửa được một nguồn đã bị tính sai theo yêu cầu. Cần thiết kế **toàn bộ tuyến dữ liệu số** phù hợp ngay từ đầu.

## 7. Khi nào constructor `double` là đúng?

Không nên hiểu `new BigDecimal(double)` luôn “sai”. Nó hoàn toàn có ý nghĩa khi bài toán thật sự cần **chuyển một số nhị phân floating-point cụ thể sang biểu diễn decimal exact của chính nó**.

Ví dụ:
- Phân tích sai số của thuật toán `double`.
- Kiểm tra ranh giới làm tròn từ binary64 sang decimal.
- Nghiên cứu serialization/quantization và sự khác nhau giữa chuỗi ngắn nhất với giá trị binary64 chính xác.
- Tạo tham chiếu số học không làm tròn thêm tại thời điểm **chuyển đổi**.

```java
double binaryValue = 0.1;
BigDecimal exactRepresentation = new BigDecimal(binaryValue);
```

Đây là một yêu cầu kỹ thuật hợp lệ. Nhưng nó **không** phù hợp khi yêu cầu là “giá sản phẩm người dùng nhập 0.10” hoặc “thuế suất decimal đúng 0.1” mà dữ liệu có sẵn ở dạng văn bản.

### Phân số nhị phân có biểu diễn hữu hạn

`0.5` bằng `1/2` nên được lưu đúng trong binary64:

```java
System.out.println(new BigDecimal(0.5)); // 0.5
```

Tương tự, `0.25`, `0.125` và nhiều số nguyên nhỏ cũng có thể chuyển đẹp. Việc một vài test đơn giản “cho chuỗi đẹp” không chứng minh constructor double an toàn cho mọi số decimal.

## 8. Không phải mọi số lớn đều giữ nguyên khi đi qua `double`

Lỗi dữ liệu không chỉ xảy ra với phần lẻ. `double` có 53 bit significand, vì vậy nó không biểu diễn chính xác **mọi** số nguyên lớn.

```java
long id = 9_007_199_254_740_993L; // 2^53 + 1

BigDecimal directly = BigDecimal.valueOf(id);
BigDecimal viaDouble = BigDecimal.valueOf((double) id);

System.out.println(directly.toPlainString());
// 9007199254740993

System.out.println(viaDouble.toPlainString());
// 9007199254740992
```

Lời gọi `BigDecimal.valueOf((double) id)` không thể lấy lại bit đã mất khi chuyển `long -> double`. `new BigDecimal((double) id)` cũng không thể phục hồi nó: constructor có thể biểu diễn chính xác binary64, nhưng binary64 **đã mang giá trị khác**.

Nếu nguồn là số nguyên:
- `BigDecimal.valueOf(long)` tạo decimal integer chính xác, scale 0.
- `new BigDecimal(long)` cũng tạo giá trị số nguyên chính xác.
- `new BigDecimal(BigInteger)` phù hợp với số nguyên vượt `long`.
- **Tránh** chuyển qua `double` chỉ để gọi một constructor nhận double.

Lưu ý sự khác biệt giữa hai overload **`BigDecimal.valueOf(long)`** và **`BigDecimal.valueOf(double)`**. Với `long`, factory không cần thuật toán biểu diễn floating-point.

## 9. `float` chuyển sang `double` không khôi phục chính xác decimal

`float` dùng binary32, có khoảng 24 bit significand. Khi truyền một `float` vào API nhận `double`, Java **mở rộng** giá trị float sang double, nhưng giá trị đã lượng tử hóa ở binary32 không quay trở thành literal decimal ban đầu.

```java
float sample = 0.1f;
double widened = sample;

System.out.println(widened); // 0.10000000149011612
System.out.println(BigDecimal.valueOf(widened));
// 0.10000000149011612
```

Đây là ví dụ hữu ích khi số đo đi qua `float`, sau đó được giao cho một module làm việc với `BigDecimal`. Chỉ vì module đích dùng BigDecimal, dữ liệu **không** tự có độ chính xác decimal của nguồn.

**Chiến lược theo yêu cầu:**
- Nếu muốn lưu chính xác **giá trị float**, constructor `new BigDecimal((double) sample)` có thể dùng để biểu diễn exact giá trị đã có.
- Nếu muốn decimal text ngắn theo `Float.toString(sample)`, có thể tạo `new BigDecimal(Float.toString(sample))` với hợp đồng rõ; điều này **khác** đường `BigDecimal.valueOf((double) sample)`.
- Nếu cần decimal gốc của dữ liệu từ trước khi bị ép thành float, phải đọc hoặc giữ **dữ liệu nguồn ban đầu**.

Không dùng `Float.toString` như cách sửa mọi sai số: nó là một chính sách biểu diễn giá trị float đã có, không phải bằng chứng về dữ liệu gốc.

## 10. Dùng `MathContext` có giúp tránh nhiễu không?

`BigDecimal` có constructor:

```java
new BigDecimal(double value, MathContext mc)
```

Nó chuyển từ `double` và làm tròn theo precision/rounding được chỉ định. Ví dụ:

```java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal rounded =
        new BigDecimal(0.1, new MathContext(4, RoundingMode.HALF_UP));
```

Kết quả có thể trông “gọn” vì được làm tròn ở 4 chữ số có nghĩa. Nhưng đó là **một phép làm tròn có chủ đích** từ giá trị binary64, **không phải phục hồi decimal gốc**.

`MathContext` quy định **precision** (số chữ số có nghĩa) và rounding mode. Nó không đồng nghĩa với “luôn giữ 2 chữ số sau dấu thập phân”. Để quy định số chữ số lẻ cố định, `setScale(scale, roundingMode)` thường phù hợp hơn.

### `setScale` giúp chuẩn hóa theo hợp đồng decimal

```java
BigDecimal exactBinary = new BigDecimal(0.1);

BigDecimal twoDecimals =
        exactBinary.setScale(2, RoundingMode.HALF_UP);

System.out.println(twoDecimals); // 0.10
```

Nếu nghiệp vụ là “số tiền được định nghĩa bằng cent và phải làm tròn HALF_UP”, việc setScale ở ranh giới xác định có thể hợp lý. **Nhưng nếu bạn không biết dữ liệu nguồn có đúng là 0.1 hay là 0.10000000000000001**, thao tác rounding không thể xác minh ý định của nguồn.

`setScale(2, RoundingMode.UNNECESSARY)` yêu cầu không mất thông tin theo mức scale đích; với `new BigDecimal(0.1)` thường ném `ArithmeticException` vì có các chữ số dư khác 0. Đây có thể là **một phép phát hiện dữ liệu không thỏa hợp đồng**, chứ không phải lỗi ngẫu nhiên của BigDecimal.

### Không chọn rounding mode tùy tiện

| Chính sách | Ý nghĩa thường dùng | Ghi chú |
| --- | --- | --- |
| `RoundingMode.HALF_UP` | Làm tròn ở phần nửa theo hướng tăng độ lớn | Phổ biến ở một số nghiệp vụ, không mặc định phù hợp mọi chuẩn |
| `RoundingMode.HALF_EVEN` | Rounding ties to even | Hữu ích giảm thiên lệch khi làm tròn nhiều lần |
| `RoundingMode.DOWN` | Cắt về 0 | Không phải floor cho số âm |
| `RoundingMode.FLOOR` | Về âm vô cùng | Khác DOWN nếu giá trị âm |
| `RoundingMode.UNNECESSARY` | Cấm mọi bước làm tròn | Ném exception nếu cần loại chữ số khác 0 |

Hợp đồng tài chính/thuế/đo lường phải chọn chế độ và **thời điểm** làm tròn. Không tự động gọi `setScale(2)` với mode tùy ý chỉ vì giá trị trông như số tiền.

## 11. So sánh: khác giá trị và khác scale là hai chuyện riêng

`BigDecimal.equals` so sánh cả **giá trị** và **scale**, còn `compareTo` so sánh thứ tự/giá trị số học.

```java
BigDecimal a = new BigDecimal("2.00");
BigDecimal b = new BigDecimal("2.0");

System.out.println(a.equals(b));     // false
System.out.println(a.compareTo(b));  // 0
```

Đây là trường hợp **giá trị số bằng nhau nhưng scale khác**.

Ngược lại:

```java
BigDecimal noisy = new BigDecimal(0.1);
BigDecimal exact = new BigDecimal("0.1");

System.out.println(noisy.equals(exact));    // false
System.out.println(noisy.compareTo(exact)); // 1
```

Trường hợp này **giá trị khác thật**; không thể sửa bằng `stripTrailingZeros()` bởi các chữ số thập phân dư của `noisy` là có ý nghĩa trong chính giá trị đang lưu, không phải toàn bộ là số 0 cuối.

Đừng dùng một tolerance `double` không rõ đơn vị để che sai số BigDecimal trong các quy trình phải exact. Nếu so sánh kiểu “gần bằng” thật sự là yêu cầu ứng dụng, hãy định nghĩa ngưỡng decimal tường minh, ví dụ:

```java
BigDecimal difference = noisy.subtract(exact).abs();
BigDecimal tolerance = new BigDecimal("0.000000000000001");

boolean close = difference.compareTo(tolerance) <= 0;
```

Đây là **một chính sách chấp nhận chênh lệch**, không phải phép biến `noisy` thành đúng 0.1. Với dữ liệu tiền tệ cần đúng cent, hãy dùng quy tắc scale/rounding trên dữ liệu đầu vào và loại bỏ việc chuyển qua double ngay từ đầu.

## 12. NaN, Infinity, zero âm và các giá trị đặc biệt

`double` có `NaN`, `+Infinity`, `-Infinity` và signed zero; `BigDecimal` không chứa các trạng thái không hữu hạn ấy như `double`.

```java
// Những lời gọi sau ném NumberFormatException:
new BigDecimal(Double.NaN);
BigDecimal.valueOf(Double.POSITIVE_INFINITY);
new BigDecimal(Double.NEGATIVE_INFINITY);
```

Chúng là các lệnh minh họa **cố ý gây exception**, không phải một đoạn mã có thể chạy tuần tự nếu không bắt lỗi.

Trước khi nhận một nguồn `double` có thể đến từ thiết bị hoặc tính toán, xác thực nếu ứng dụng yêu cầu số hữu hạn:

```java
static BigDecimal fromFiniteDouble(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("finite number required");
    }
    return BigDecimal.valueOf(value);
}
```

Phương thức minh họa trên từ chối NaN/Infinity và chọn chính sách chuyển đổi `valueOf(double)`, nhưng **không** hứa phục hồi decimal nguồn.

### Zero âm

`-0.0d` có mẫu bit khác `+0.0d` nhưng so sánh toán học `-0.0d == +0.0d` là true. `BigDecimal` không mô hình hóa signed zero riêng, nên:

```java
System.out.println(new BigDecimal(-0.0).toPlainString()); // 0
```

Nếu dấu zero trong dữ liệu cảm biến/IEEE 754 là một phần ngữ nghĩa cần bảo toàn, **chuyển sang BigDecimal không giữ thông tin đó**. Hãy thiết kế kiểu dữ liệu/schema riêng nếu cần.

## 13. Dữ liệu tài chính: không đưa qua `double` vì tiện

Giả sử nghiệp vụ có hai khoản decimal chính xác 0.10 và 0.20 đơn vị tiền tệ:

```java
BigDecimal first = new BigDecimal("0.10");
BigDecimal second = new BigDecimal("0.20");

BigDecimal total = first.add(second);
System.out.println(total.toPlainString()); // 0.30
```

Giá trị chính xác và scale được giữ theo phép cộng, vì `add` mặc định chọn scale là lớn nhất của hai toán hạng.

Một cách đi đường vòng không nên làm:

```java
double x = 0.10;
double y = 0.20;
BigDecimal convertedTooLate = BigDecimal.valueOf(x + y);
System.out.println(convertedTooLate);
// 0.30000000000000004
```

Nếu code đang nhận số từ file CSV, JSON hoặc JDBC, cần làm rõ **kiểu dữ liệu tại ranh giới**:
- Một cột `DECIMAL`/`NUMERIC` nên được đọc thành `BigDecimal` khi driver/framework hỗ trợ chính xác.
- Một JSON string decimal được schema quy định có thể parse trực tiếp qua `new BigDecimal(text)` sau khi validate.
- Một JSON number có thể được thư viện nhận thành `double`, `BigDecimal` hay kiểu khác; phải cấu hình parser để không mất precision khi cần.
- Một giá trị tiền với scale xác định có thể lưu số nguyên theo đơn vị nhỏ nhất (`long cents`) nếu miền/đơn vị phù hợp, nhưng không cần ép mọi mô hình tiền sang một cách duy nhất.

**Không xử lý dữ liệu định dạng theo locale như `"1.234,50"` bằng `new BigDecimal(String)` trực tiếp**. Phải có parser nhập liệu đúng locale và kiểu kết quả, tránh đi qua `double` nếu muốn exact decimal.

## 14. Một số trường hợp làm tròn và biểu diễn rất dễ nhầm

### 14.1. `new BigDecimal(0.1).toString()` không “phóng đại lỗi”

`toString` hiện ra tất cả chữ số cần thiết để diễn đạt chính xác giá trị BigDecimal. Nó **không tạo thêm số học hoặc tăng sai số**. Cùng một đối tượng ấy, `toPlainString` cũng chỉ thay cách hiển thị exponent/decimal theo hợp đồng, chứ không thay giá trị.

Nếu thấy một chuỗi dài sau khi gọi `toString`, nguyên nhân thường đã xảy ra ở **cách xây BigDecimal từ double**, không phải formatter đang tính sai.

### 14.2. `BigDecimal.valueOf(double)` vẫn mất thông tin về text gốc

`BigDecimal.valueOf(1.0)` có thể có scale khác `new BigDecimal("1.00")`. Factory chỉ biết binary64 **1.0** và chuỗi chuẩn của nó; nó không biết ban đầu người dùng nhập `"1.00"` với **hai chữ số lẻ**.

Nếu số chữ số lẻ/scale mang ý nghĩa chứng từ, hãy giữ decimal text hoặc scale như một phần hợp đồng.

### 14.3. `BigDecimal(double, MathContext)` và `setScale` không giống nhau

Constructor có `MathContext` làm tròn theo **tổng số chữ số có nghĩa**. `setScale(2,...)` làm tròn theo **vị trí hai chữ số sau dấu thập phân** nếu scale đích là 2. Hai cách có thể tạo kết quả khác, đặc biệt với số rất lớn hoặc rất nhỏ.

### 14.4. `BigDecimal` phép chia không tự sinh vô hạn chữ số

`BigDecimal.ONE.divide(new BigDecimal("3"))` ném `ArithmeticException` vì `1/3` không có biểu diễn thập phân hữu hạn, trừ khi cung cấp scale/rounding hoặc `MathContext` thích hợp. Điều này độc lập với vấn đề nhiễu do `double`, nhưng cùng cho thấy **BigDecimal yêu cầu bạn định nghĩa chính sách làm tròn** thay vì âm thầm chọn mặc định.

### 14.5. `BigDecimal.valueOf(double)` không làm mọi phép toán thành số học decimal

Một chương trình như:

```java
double balance = 0.0;
balance += 0.1;
balance += 0.2;

BigDecimal after = BigDecimal.valueOf(balance);
```

vẫn đã thực hiện phép cộng trong binary64. Cần chuyển **từng giá trị decimal nguồn** sang BigDecimal trước rồi mới cộng bằng `BigDecimal.add`. Không thể “bật chế độ decimal” cho một chuỗi phép tính `double` chỉ bằng cách đổi kiểu ở cuối.

## 15. Cách chọn constructor/factory theo nguồn thực tế

| Nguồn | Mục tiêu | Lựa chọn |
| --- | --- | --- |
| Chuỗi decimal hợp lệ `"0.10"` | Giữ đúng giá trị và scale nguồn | `new BigDecimal("0.10")` |
| Primitive `int`/`long` | Giữ nguyên số nguyên, scale 0 | `BigDecimal.valueOf(long)` hoặc constructor integer |
| `BigInteger` | Chuyển số nguyên rất lớn | `new BigDecimal(bigInteger)` |
| Đầu vào `double` đã có | Lấy decimal dựa trên canonical string của double | `BigDecimal.valueOf(d)` |
| Đầu vào `double` đã có | Chính xác giá trị binary64 tới chữ số cuối | `new BigDecimal(d)` |
| Đầu vào `float` đã có | Muốn decimal theo `Float.toString` | `new BigDecimal(Float.toString(f))` khi đó là policy |
| Chuỗi decimal có nhiều chữ số nhưng đang định parse qua `double` | Không được mất precision | Parse trực tiếp sang BigDecimal, bỏ bước double |
| JSON number trong API tài chính | Cần decimal exact khi parse | Cấu hình JSON deserializer nhận decimal token thành BigDecimal |
| Phép toán `double` đã xảy ra | Không thể tự phục hồi decimal gốc | Xem lại upstream hoặc xác lập rounding policy |
| Input có locale/grouping | Cần decimal exact | Parse theo locale/schema thành BigDecimal, không parse qua double |

### Hướng dẫn ra quyết định ngắn

1. **Có decimal text gốc?** Giữ và parse trực tiếp qua BigDecimal.
2. **Có integer primitive hoặc BigInteger?** Chuyển trực tiếp, không thông qua double.
3. **Chỉ còn `double`?** Nếu cần giá trị decimal theo chuỗi chuẩn, dùng `BigDecimal.valueOf(d)`; nếu cần giá trị binary64 **exact**, dùng `new BigDecimal(d)`.
4. **Dữ liệu tính tiền/decimal?** Thực hiện phép tính bằng BigDecimal từ đầu, có scale và rounding mode phù hợp.
5. **Cần giữ cả dấu zero, NaN, Infinity hoặc bit pattern?** BigDecimal không thay thế được mô hình floating-point đặc biệt ấy.

## 16. Chương trình Java 17+ chạy độc lập

Tạo tệp `DecimalDoubleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalDoubleDemo {
    public static void main(String[] args) {
        double d = 0.1;
        BigDecimal exact = new BigDecimal(d);
        BigDecimal text = new BigDecimal("0.1");
        BigDecimal factory = BigDecimal.valueOf(d);

        System.out.println("double text: " + Double.toString(d));
        System.out.println("new BigDecimal(0.1): " + exact.toPlainString());
        System.out.println("new BigDecimal(\"0.1\"): "
                + text.toPlainString());
        System.out.println("BigDecimal.valueOf(0.1): "
                + factory.toPlainString());
        System.out.println("exact equals text: " + exact.equals(text));
        System.out.println("factory equals text: " + factory.equals(text));
        System.out.println("exact compareTo text: "
                + exact.compareTo(text));
        System.out.println("exact scale: " + exact.scale());
        System.out.println("text scale: " + text.scale());
        System.out.println("exact unscaled: " + exact.unscaledValue());

        System.out.println("decimal sum: "
                + text.add(new BigDecimal("0.2")).toPlainString());
        System.out.println("double sum: " + Double.toString(0.1 + 0.2));
        System.out.println("factory after double sum: "
                + BigDecimal.valueOf(0.1 + 0.2).toPlainString());
        System.out.println("exact binary sum: "
                + new BigDecimal(0.1).add(new BigDecimal(0.2))
                    .toPlainString());

        System.out.println("half exactly representable: "
                + new BigDecimal(0.5).toPlainString());
        System.out.println("exact rounded to 2 decimals: "
                + exact.setScale(2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("factory rounded to 2 decimals: "
                + factory.setScale(2, RoundingMode.HALF_UP).toPlainString());

        System.out.println("float promoted: "
                + BigDecimal.valueOf((double) 0.1f).toPlainString());

        long big = 9_007_199_254_740_993L;
        System.out.println("long exact: "
                + BigDecimal.valueOf(big).toPlainString());
        System.out.println("long through double: "
                + BigDecimal.valueOf((double) big).toPlainString());

        try {
            new BigDecimal(Double.NaN);
        } catch (NumberFormatException ex) {
            System.out.println("NaN rejected: true");
        }
        try {
            BigDecimal.valueOf(Double.POSITIVE_INFINITY);
        } catch (NumberFormatException ex) {
            System.out.println("Infinity rejected: true");
        }

        System.out.println("negative zero from double: "
                + new BigDecimal(-0.0).toPlainString());
        System.out.println("2.00 equals 2.0: "
                + new BigDecimal("2.00")
                    .equals(new BigDecimal("2.0")));
        System.out.println("2.00 compareTo 2.0: "
                + new BigDecimal("2.00")
                    .compareTo(new BigDecimal("2.0")));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 DecimalDoubleDemo.java
java DecimalDoubleDemo
```

Stdout đã kiểm chứng:

```text
double text: 0.1
new BigDecimal(0.1): 0.1000000000000000055511151231257827021181583404541015625
new BigDecimal("0.1"): 0.1
BigDecimal.valueOf(0.1): 0.1
exact equals text: false
factory equals text: true
exact compareTo text: 1
exact scale: 55
text scale: 1
exact unscaled: 1000000000000000055511151231257827021181583404541015625
decimal sum: 0.3
double sum: 0.30000000000000004
factory after double sum: 0.30000000000000004
exact binary sum: 0.3000000000000000166533453693773481063544750213623046875
half exactly representable: 0.5
exact rounded to 2 decimals: 0.10
factory rounded to 2 decimals: 0.10
float promoted: 0.10000000149011612
long exact: 9007199254740993
long through double: 9007199254740992
NaN rejected: true
Infinity rejected: true
negative zero from double: 0
2.00 equals 2.0: false
2.00 compareTo 2.0: 0
```

Ví dụ này đối chiếu **ba cơ chế khởi tạo**, giá trị và scale, sự khác biệt trong phép cộng, ảnh hưởng của `float`, mất dữ liệu nguyên lớn qua `double`, NaN/Infinity và equality theo scale. Điều quan trọng nhất là các chuỗi rất dài **đã được giải thích bởi đầu vào binary64**, không phải “sự bất ổn” của phép cộng BigDecimal.

## 17. Bộ kiểm thử nên có

| Kiểm thử | Input / thao tác | Kỳ vọng |
| --- | --- | --- |
| Constructor double | `new BigDecimal(0.1)` | Giá trị decimal chính xác của binary64, có chữ số dài |
| Constructor text | `new BigDecimal("0.1")` | Decimal exact 0.1, scale 1 |
| Factory double | `BigDecimal.valueOf(0.1)` | `0.1`, tương ứng `Double.toString` |
| Factory sau cộng double | `BigDecimal.valueOf(0.1+0.2)` | `0.30000000000000004` |
| Cộng decimal exact | `new BigDecimal("0.1").add(new BigDecimal("0.2"))` | `0.3` |
| Cộng hai exact binary64 | `new BigDecimal(0.1).add(new BigDecimal(0.2))` | Không bằng đúng decimal 0.3 |
| Số biểu diễn nhị phân hữu hạn | `new BigDecimal(0.5)` | `0.5` |
| Float bị widen | `BigDecimal.valueOf((double)0.1f)` | `0.10000000149011612` |
| Số nguyên qua double | `2^53+1` chuyển long → double → BigDecimal | Mất 1 đơn vị |
| Tạo từ long | `BigDecimal.valueOf(9007199254740993L)` | Chính xác |
| NaN | `new BigDecimal(Double.NaN)` | `NumberFormatException` |
| Infinity | `BigDecimal.valueOf(+Infinity)` | `NumberFormatException` |
| Signed zero | `new BigDecimal(-0.0)` | Giá trị BigDecimal bằng 0, không giữ signed-zero |
| Scale vs numerical equality | `"2.00"` và `"2.0"` | `equals=false`, `compareTo=0` |
| Rounding 2 decimals | `exactBinary.setScale(2, HALF_UP)` | `0.10`; rounding là policy, không khôi phục text nguồn |

Ngoài test số học, hãy kiểm thử **chuỗi dữ liệu end-to-end** từ CSV/JSON/JDBC qua lớp service đến khi ghi DB hoặc xuất file: liệu có đoạn nào tự ép decimal thành `double`? Lỗi có thể nằm trong cấu hình framework, mapping kiểu, hoặc serializer chứ không nằm ngay ở constructor trong business code.

## 18. Những lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách phù hợp |
| --- | --- | --- |
| Dùng `new BigDecimal(0.1)` và mong đúng decimal 0.1 | Nhận chính xác binary64, tạo nhiều chữ số thập phân | Dùng `new BigDecimal("0.1")` khi có text decimal |
| Gọi chuỗi dài là “lỗi làm tròn của BigDecimal” | Chẩn đoán sai nguyên nhân | Xem dữ liệu đã qua `double` trước khi tạo BigDecimal |
| Tin `BigDecimal.valueOf(double)` luôn sửa sai số | Phép cộng double trước đó vẫn giữ lỗi | Tạo và tính BigDecimal từ nguồn |
| Dùng `String.valueOf(double)` để khôi phục mọi chữ số nhập ban đầu | Chuỗi ngắn chỉ giữ roundtrip double | Giữ text decimal từ đầu nếu cần |
| Đổi `long` lớn thành `double` rồi gọi `valueOf` | Mất chính xác số nguyên > 2^53 | `BigDecimal.valueOf(long)` hoặc `BigInteger` |
| Dùng `new BigDecimal(0.1f)` và nghĩ đó là decimal 0.1 | `float` đã xấp xỉ và widen thành double | Dùng nguồn decimal, hoặc Float.toString theo policy |
| Dùng `setScale(2, HALF_UP)` ở mọi nơi để che nhiễu | Có thể làm mất giá trị hợp lệ và sai quy tắc rounding | Xác định đơn vị/scale/mode ở biên |
| Tưởng `MathContext(2)` nghĩa là 2 chữ số lẻ | Nó là 2 chữ số **có nghĩa** | Phân biệt `precision` và `scale` |
| Dùng `equals` làm kiểm tra cùng giá trị toán học | `equals` xét cả scale | `compareTo==0` khi không cần scale |
| Tin `stripTrailingZeros` xóa được nhiễu | Chữ số dư không nhất thiết là zero | Xử lý đúng nguồn, không làm sạch mù |
| Nhập NaN/Infinity vào BigDecimal | `NumberFormatException` | Check `Double.isFinite`; schema xử lý riêng |
| Tin BigDecimal giữ dấu `-0.0` | Không có signed-zero như double | Giữ bit/metadata ở mô hình riêng nếu cần |
| Parse số decimal qua `Double.parseDouble` trước `BigDecimal` | Mất precision ở bước giữa | `new BigDecimal(text)` trực tiếp |
| Cho rằng BigDecimal luôn chia được với kết quả hữu hạn | 1/3 là decimal vô hạn | Dùng `divide` với scale/rounding khi phù hợp |
| Làm tròn tại nhiều bước trung gian không theo chính sách | Sai tổng/thuế/phép đo | Quy định điểm làm tròn và bảo toàn exact trước đó |
| Truyền money dưới dạng JSON number rồi client parse binary64 tùy ý | Mất precision/scale trong tích hợp | Thiết kế schema và parser decimal chính xác |

## 19. Câu hỏi tự kiểm tra

1. Vì sao literal `0.1` trong một `double` không giữ được phân số toán học `1/10` chính xác?
2. `new BigDecimal(0.1)` chứa giá trị gì? Vì sao một chuỗi thập phân dài lại có thể là **chuyển đổi exact**?
3. `new BigDecimal("0.1")` và `BigDecimal.valueOf(0.1)` trông cùng kết quả. Chúng có cùng nguồn thông tin không?
4. Tại sao `BigDecimal.valueOf(0.1 + 0.2)` không cho decimal 0.3?
5. Hai con đường `new BigDecimal(0.1).add(new BigDecimal(0.2))` và `BigDecimal.valueOf(0.1+0.2)` khác nhau về thứ tự làm tròn/convert thế nào?
6. Những phân số nào như `0.5`, `0.25`, `0.125` được binary64 biểu diễn hữu hạn? Tiêu chí mẫu số là gì?
7. `BigDecimal.valueOf(0.1f)` có phục hồi decimal text gốc 0.1 không? Vì sao widening float sang double không làm thế?
8. Vì sao `2^53+1` có thể mất chính xác khi chuyển từ `long` sang `double`?
9. Nếu nhận chuỗi tiền `"1234.50"`, bạn chọn constructor nào để giữ cả giá trị và scale? Điều gì xảy ra nếu parse qua double?
10. `MathContext` và `setScale` khác nhau ở precision và số chữ số sau dấu như thế nào?
11. `new BigDecimal(0.1).setScale(2, HALF_UP)` trả gì? Có phải nó đã khôi phục chắc chắn giá trị nguồn decimal không?
12. `BigDecimal.equals` và `compareTo` khác nhau khi so `2.00` với `2.0`?
13. `new BigDecimal(Double.NaN)` có tạo object không? Vì sao?
14. `BigDecimal` có bảo toàn bit dấu của `-0.0` không? Nếu ứng dụng cần điều đó, giải pháp là gì?
15. Bạn sẽ kiểm tra ở những ranh giới nào để bảo đảm toàn hệ thống tính decimal exact, từ nhập liệu đến database và API?

## 20. Tài liệu tham khảo chính thức

- [Java SE 17 — `BigDecimal(double)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#%3Cinit%3E(double)): định nghĩa chuyển giá trị binary64 thành decimal exact, ví dụ `0.1` và khuyến nghị không dùng constructor này nếu muốn decimal người dùng nghĩ đến.
- [Java SE 17 — `BigDecimal.valueOf(double)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#valueOf(double)): chuyển qua biểu diễn chuẩn của `Double.toString(double)`.
- [Java SE 17 — `BigDecimal(String)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#%3Cinit%3E(java.lang.String)): đọc trực tiếp chuỗi decimal, không qua double.
- [Java SE 17 — `BigDecimal`: precision, scale, MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): mô hình unscaled value/scale, các phép toán và làm tròn.
- [Java SE 17 — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `Double.toString`, `parseDouble`, binary64, NaN và Infinity.
- [Java Language Specification `4.2.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): miền, cách biểu diễn và hành vi số dấu phẩy động Java.

**Ghi nhớ:** `new BigDecimal(double)` là phép chuyển **chính xác giá trị binary64**, nên có thể xuất hiện chuỗi decimal dài như khi dùng `0.1`. `new BigDecimal("0.1")` giữ đúng decimal từ ký tự nguồn; `BigDecimal.valueOf(0.1)` tạo decimal từ chuỗi chuẩn `Double.toString` của double đã có. Không có cách nào tự khôi phục chắc chắn dữ liệu decimal **đã bị mất** ở các bước tính toán double. Với hệ thống cần decimal exact, lựa chọn đúng nhất là **giữ dữ liệu decimal và xử lý bằng BigDecimal từ ranh giới đầu vào**, rồi làm tròn theo chính sách được xác định rõ.