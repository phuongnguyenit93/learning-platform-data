# Bảng chọn primitive, wrapper, BigInteger hoặc BigDecimal trong Java

## 1. Mục tiêu: chọn kiểu số theo yêu cầu, không theo thói quen

Java có nhiều cách biểu diễn dữ liệu số: kiểu nguyên thủy (**primitive**), lớp bao (**wrapper**), `BigInteger` và `BigDecimal`. Không có kiểu nào “tốt nhất cho mọi trường hợp”. Việc chọn kiểu cần dựa trên **miền giá trị**, **độ chính xác**, **đơn vị**, **null/có dữ liệu hay không**, **API sử dụng** và **chi phí thực thi**.

Bài này là bảng tra cứu để chọn loại số phù hợp khi khai báo biến, kiểu trường, tham số, kết quả tính toán, khóa collection và dữ liệu trao đổi. Các tiêu chí cốt lõi:

1. **Số nguyên hay thập phân?** Số lượng, thứ tự, chỉ mục thường là số nguyên; giá, tỷ lệ, phép đo có thể cần phần lẻ.
2. **Cần chính xác tuyệt đối hay gần đúng?** Không dùng `double` thay `BigDecimal` khi một chữ số tiền tệ sai cũng không chấp nhận.
3. **Có giới hạn trên/dưới không?** `int`, `long` có giới hạn cố định, `BigInteger` mở rộng theo tài nguyên.
4. **Có cần biểu diễn trạng thái thiếu dữ liệu?** Primitive không chứa `null`; wrapper có thể chứa `null` nhưng phải tránh unboxing không kiểm tra.
5. **Làm việc với generics/collection/framework?** `List<int>` không hợp lệ trong Java 17; `List<Integer>` hợp lệ.
6. **Kiểu lưu và kiểu tính trung gian có thể khác nhau.** Kết quả cuối có thể vừa `int` nhưng tổng hoặc tích trung gian cần `long` hay `BigInteger`.

## 2. Bảng chọn nhanh — trường hợp điển hình

| Nhu cầu | Lựa chọn nên cân nhắc | Vì sao | Tránh nhầm lẫn |
| --- | --- | --- | --- |
| Biến đếm, chỉ mục, số lượng nhỏ trong phạm vi 32 bit | `int` | Primitive gọn, phép toán đơn giản, không null | Tổng/tích của nhiều giá trị `int` vẫn có thể tràn |
| Tổng lớn, timestamp hoặc số nguyên trong phạm vi 64 bit | `long` | Miền rộng hơn `int` | `long` vẫn có giới hạn, phép cộng/nhân vẫn có thể tràn |
| Tập giá trị chỉ có byte hoặc short do giao thức/schema | `byte`, `short` | Đúng miền/định dạng bên ngoài | Số học `byte`/`short` thường được nâng thành `int` |
| Biểu thị ký tự UTF-16 code unit | `char` | Là primitive 16-bit cho code unit | Không dùng `char` thay kiểu số chỉ vì không dấu |
| Số đo, đồ họa, thống kê chấp nhận xấp xỉ | `double` | Floating point phổ biến, tốc độ tốt | 0.1 không lưu chính xác, có NaN/Infinity/-0.0 |
| Dữ liệu hoặc API thực sự yêu cầu float 32-bit | `float` | Bớt dung lượng, đúng giao thức | Chính xác thấp hơn `double`; tránh dùng mặc định |
| Số nguyên cần `null` hoặc tham gia `List<T>`, `Map<K,V>` | `Integer`, `Long` và wrapper phù hợp | Kiểu object hỗ trợ generics, nullable | Boxing/unboxing, `==`, `NullPointerException` |
| Số nguyên chính xác vượt `long` | `BigInteger` | Không giới hạn 64 bit cố định | Chi phí object, dùng `add`/`multiply` thay toán tử |
| Số thập phân chính xác, tiền và rounding có quy tắc | `BigDecimal` | Hệ thập phân có scale, phương thức rounding rõ ràng | Chia cần xử lý thương vô hạn; `equals` xét scale |
| Có thể vắng một số nguyên/real nhưng không muốn `null` | `OptionalInt`, `OptionalLong`, `OptionalDouble` (đặc biệt ở API kết quả) | Thể hiện rõ có/không có giá trị | Không phải kiểu số dùng để tính như primitive |
| Tiền đã chốt ở đơn vị nhỏ nhất, phạm vi vừa 64 bit | `long` cents (theo domain) | Exact integer với đơn vị cố định | Thuế/phần trăm có thể cần `BigDecimal` trung gian |
| ID gồm chữ số, có thể có số 0 đầu, không dùng toán học | `String` | Giữ định danh và số 0 đầu | Không chọn `int`/`long` chỉ vì nhìn giống số |

Đây là **gợi ý dựa trên hợp đồng domain**, không phải mệnh lệnh dùng một kiểu duy nhất. Ví dụ `Long` là hợp lý cho cột nullable nếu schema cho phép thiếu, trong khi `long` tốt hơn cho bộ đếm bắt buộc có dữ liệu.

## 3. Ma trận năng lực của các lựa chọn chính

| Tiêu chí | Primitive nguyên `int/long` | Primitive thực `float/double` | Wrapper `Integer/Long/Double/...` | `BigInteger` | `BigDecimal` |
| --- | --- | --- | --- | --- | --- |
| Giá trị `null` | Không | Không | Có | Có ở biến tham chiếu, nhưng null không phải số | Có ở biến tham chiếu, nhưng null không phải số |
| Miền | Cố định theo bit | Cố định theo IEEE 754 | Như primitive tương ứng | Độ lớn linh hoạt theo tài nguyên | Độ lớn thập phân linh hoạt theo tài nguyên |
| Số nguyên chính xác | Có trong miền | Chỉ một số miền và độ lớn; không phải mọi `long` | Theo primitive bọc | Có | Có thể biểu diễn số nguyên chính xác |
| Số thập phân chính xác | Không biểu diễn phần lẻ | Nói chung không chính xác decimal | Wrapper của `float/double` cũng xấp xỉ | Chỉ nguyên | Có với giá trị biểu diễn hữu hạn thập phân |
| Phép toán bằng `+ - * /` | Có | Có | Có nhờ unboxing (với nguy cơ null) | Không; dùng phương thức | Không; dùng phương thức |
| Dùng trực tiếp trong `List<T>` | Không | Không | Có | Có | Có |
| Tạo nhiều đối tượng khi tính | Không đối với giá trị primitive thuần | Không đối với giá trị primitive thuần | Có thể phát sinh boxing | Phép tính tạo đối tượng kết quả mới | Phép tính tạo đối tượng kết quả mới |
| Kiểm soát rounding decimal | Không phù hợp | Quy tắc floating point, không phải decimal business | Tương ứng primitive | Không có phần lẻ | Dùng `scale`, `MathContext`, `RoundingMode` |
| Nguy cơ thường gặp | Overflow, chia nguyên | Sai số, NaN/Infinity | Null unboxing, so `==` | Chuyển thu hẹp sai | Dùng constructor từ `double`, scale/rounding, `equals` |

Tính bất biến: `BigInteger`, `BigDecimal` và các wrapper số chuẩn là immutable. Ví dụ `total.add(value)` không sửa `total`; phải gán lại kết quả. Kiểu primitive không phải object nên không có trạng thái tham chiếu để chia sẻ theo cách wrapper.

## 4. Cây quyết định dạng văn bản

```text
Đầu vào có thực sự là giá trị số để tính toán?
  ├─ Không: mã, ID, số tài khoản, mã bưu chính... → cân nhắc String
  └─ Có
      ├─ Cần phần thập phân?
      │   ├─ Không, chỉ nguyên
      │   │   ├─ Vừa int và không cần null/generics? → int
      │   │   ├─ Vừa long và không cần null/generics? → long
      │   │   ├─ Vượt long nhưng phải exact? → BigInteger
      │   │   └─ Cần null/generics? → wrapper phù hợp miền (Integer/Long...)
      │   └─ Có
      │       ├─ Phải chính xác thập phân/rounding nghiệp vụ? → BigDecimal
      │       └─ Chấp nhận xấp xỉ IEEE 754? → double (hoặc float khi có lý do)
      └─ Trước khi lưu/trả API:
          kiểm tra miền, đơn vị, null, rounding và chuyển đổi exact
```

Lưu ý một giá trị có thể đồng thời có nhiều ràng buộc. Ví dụ “số tiền phải chính xác nhưng dùng `List`” không có nghĩa chọn `Double`: có thể chọn `List<BigDecimal>`. “Giá trị nguyên tùy chọn” có thể biểu diễn bằng `OptionalInt` ở ranh giới trả kết quả hoặc bằng `Integer` nullable theo yêu cầu framework.

## 5. Primitive: int, long, float và double

### 5.1. Số nguyên có dấu: byte, short, int, long

| Kiểu | Bit | Min | Max |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32.768 | 32.767 |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 |
| `long` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

Trong nhiều biểu thức số học, `byte`, `short` và `char` được nâng thành `int`; việc một trường lưu ở kiểu nhỏ không có nghĩa mọi phép tính sẽ giữ nguyên kiểu đó.

`int` là lựa chọn mặc định tốt cho bộ đếm/chỉ số có giới hạn rõ ràng. `long` phù hợp khi miền vượt `int`. Nhưng **lưu ý phép tính có thể tràn trước khi gán sang kiểu rộng**:

```java
int quantity = 50_000;
int price = 50_000;

long wrong = quantity * price;         // -1794967296
long right = (long) quantity * price;  // 2500000000
```

Cả hai dòng đều biên dịch; chỉ dòng thứ hai nhân ở kiểu `long`. Muốn kiểm tra overflow thay vì wraparound, dùng `Math.addExact`, `Math.multiplyExact`, `Math.subtractExact` và các overload phù hợp.

### 5.2. Số thực nhị phân: float, double

`double` là số dấu phẩy động 64-bit, với khoảng 53 bit significand; `float` là 32-bit, khoảng 24 bit significand. Chúng có thể biểu diễn số rất lớn và rất nhỏ, nhưng **không thể biểu diễn chính xác mọi số thập phân**.

```java
double result = 0.1 + 0.2;
// Thường in 0.30000000000000004, không phải đúng decimal 0.3
```

Kiểu này có `NaN`, `+Infinity`, `-Infinity`, `+0.0` và `-0.0`, cùng vùng subnormal gần 0. `Double.isFinite(value)` dùng để kiểm tra một giá trị có hữu hạn hay không, nhưng không đánh giá được độ chính xác nghiệp vụ.

**Đừng chọn `double` làm “số nguyên cực lớn”**: mọi số nguyên tới 2^53 đều biểu diễn chính xác, nhưng những số nguyên lớn hơn không còn được đảm bảo. `long` giữ các số nguyên trong miền của nó đúng tuyệt đối, dù miền độ lớn nhỏ hơn một phần dải của `double`.

`float` không tự nhiên chính xác hơn vì tên ngắn. Chỉ dùng `float` nếu yêu cầu giao thức, bộ nhớ, dữ liệu GPU hay API định rõ 32-bit hoặc sau khi đo đạc cân nhắc độ chính xác.

## 6. Wrapper: Integer, Long, Double và tự động boxing

Mỗi primitive số có wrapper tương ứng:

| Primitive | Wrapper |
| --- | --- |
| `byte` | `Byte` |
| `short` | `Short` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |
| `char` | `Character` |

`Boolean` cũng là wrapper của `boolean`, nhưng không phải kiểu số; không đưa vào nhóm lựa chọn cho dữ liệu số.

Wrapper là object và cho phép:

- Biểu diễn `null` khi domain hoặc framework cho phép thiếu dữ liệu.
- Sử dụng với generics như `List<Integer>`, `Map<Long, String>`.
- Dùng các phương thức tiện ích: `Integer.parseInt`, `Integer.valueOf`, `Long.compare`, `Double.isFinite`, `Integer.toString`.
- Thỏa yêu cầu API nhận object thay vì primitive.

Java hỗ trợ **autoboxing** (chuyển primitive thành wrapper) và **unboxing** (chuyển wrapper về primitive):

```java
int primitive = 42;
Integer boxed = primitive; // autoboxing
int unboxed = boxed;       // unboxing
```

Nhưng `Integer nullable = null; int x = nullable;` gây `NullPointerException` khi unboxing. Cũng đừng dùng toán tử `==` để so giá trị hai wrapper tham chiếu: `==` trên hai đối tượng wrapper có thể là so **định danh object**; kết quả với một số giá trị có thể bị ảnh hưởng bởi cache boxing. Dùng `Objects.equals(a,b)` khi hai bên nullable, hoặc unbox/`Integer.compare` sau khi đã kiểm tra null.

`Integer.parseInt("17")` trả primitive `int`; `Integer.valueOf("17")` trả wrapper `Integer`. Trong generic collection, Java 17 yêu cầu kiểu object: `List<int>` không hợp lệ, `List<Integer>` hợp lệ.

### Chọn wrapper không có nghĩa “luôn muốn null”

Nếu dữ liệu chắc chắn tồn tại và không bị ràng buộc bởi generics hoặc API, primitive thường đơn giản và tránh null. Wrapper chỉ nên dùng khi có lý do: contract nullable, generic, reflection/ORM hoặc một thư viện cần object.

Không đồng nhất `Integer` với `OptionalInt`: `Integer` có thể null, còn `OptionalInt` là object chứa trạng thái có/không của một `int` và chủ yếu có ích ở ranh giới kết quả. Tránh dùng `Optional` làm trường dữ liệu tùy tiện nếu framework hoặc serialization của hệ thống không hỗ trợ hợp đồng đó.

## 7. BigInteger: số nguyên exact vượt long

`java.math.BigInteger` biểu diễn số nguyên không bị giới hạn ở 32 hoặc 64 bit. Độ lớn thực tế bị giới hạn bởi bộ nhớ, thời gian tính toán và các giới hạn triển khai.

Ví dụ:

```java
BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE); // 9223372036854775808
```

Khác primitive, cần dùng phương thức:

| Phép toán | BigInteger |
| --- | --- |
| Cộng | `a.add(b)` |
| Trừ | `a.subtract(b)` |
| Nhân | `a.multiply(b)` |
| Chia nguyên | `a.divide(b)` |
| Chia lấy dư | `a.remainder(b)` hoặc `a.divideAndRemainder(b)` |
| So sánh | `a.compareTo(b)` |
| Lũy thừa nguyên không âm | `a.pow(exponent)` |
| Chuyển về long có kiểm tra | `a.longValueExact()` |
| Chuyển về int có kiểm tra | `a.intValueExact()` |

`BigInteger` chỉ dành cho số nguyên: chia `7 / 2` cho thương nguyên `3`; không có phần lẻ `3.5`. Muốn tính phân số hữu tỉ chính xác, có thể lưu tử số/mẫu số riêng hoặc chọn `BigDecimal` cùng chính sách precision/rounding khi cần một kết quả decimal.

**Không dùng `longValue()`/`intValue()` nếu cấm mất dữ liệu**, vì chúng có thể thu hẹp và bỏ bit. Dùng `longValueExact()` hoặc `intValueExact()` để nhận `ArithmeticException` nếu không vừa miền.

## 8. BigDecimal: số thập phân chính xác và rounding

`java.math.BigDecimal` biểu diễn giá trị:

```text
unscaledValue × 10^(-scale)
```

Ví dụ `new BigDecimal("12.34")` có unscaled value 1234 và scale 2. Dùng `BigDecimal` khi phép tính phải giữ decimal chính xác hoặc khi domain có chính sách làm tròn rõ ràng, chẳng hạn tiền, tỷ lệ thuế, hạn mức và số liệu kế toán.

### Tạo BigDecimal đúng

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(1234L, 2); // 12.34
BigDecimal c = BigDecimal.valueOf(0.1);
```

Đoạn này dùng trong phương thức có import `java.math.BigDecimal`.

`new BigDecimal("0.1")` là decimal đúng 0.1. `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi chuẩn của `double` 0.1; thường phù hợp hơn `new BigDecimal(0.1)` nếu đầu vào đã là `double`. Nhưng nếu các phép tính trước đó làm mất độ chính xác của nguồn, `valueOf` không phục hồi được thông tin đã mất.

**Tránh `new BigDecimal(0.1)` khi ý định là số decimal 0.1 chính xác**: constructor nhận `double` sẽ biểu diễn chính xác giá trị nhị phân gần đúng của `double`, vốn không bằng decimal 0.1.

### Phép tính, chia và làm tròn

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal tax = price.multiply(rate)
        .setScale(2, RoundingMode.HALF_UP); // 1.50
```

Ví dụ này giả định domain yêu cầu hai chữ số thập phân và làm tròn `HALF_UP`; không mặc định mọi đơn vị tiền tệ cần scale 2 hay mọi nghiệp vụ dùng cùng RoundingMode.

| Nhu cầu | API |
| --- | --- |
| Cộng | `a.add(b)` |
| Trừ | `a.subtract(b)` |
| Nhân | `a.multiply(b)` |
| Chia exact nếu thương kết thúc | `a.divide(b)` |
| Chia có làm tròn | `a.divide(b, scale, roundingMode)` |
| Đổi scale có kiểm soát | `a.setScale(scale, roundingMode)` |
| So giá trị toán học | `a.compareTo(b)` |
| Chuyển về int/long exact | `a.intValueExact()`, `a.longValueExact()` |
| Kiểm tra decimal vừa miền precision | Dùng `precision()`, `scale()` và validation của domain/schema |

`BigDecimal.ONE.divide(new BigDecimal("3"))` ném `ArithmeticException` vì `1/3` có khai triển decimal vô hạn. Dùng overload với scale/RoundingMode hoặc MathContext phù hợp khi phép chia được phép làm tròn.

`BigDecimal` là immutable. Lời gọi `balance.add(amount)` **không** thay đổi `balance`; phải viết `balance = balance.add(amount)`.

### equals khác compareTo

```java
BigDecimal first = new BigDecimal("2.0");
BigDecimal second = new BigDecimal("2.00");

System.out.println(first.compareTo(second) == 0); // true
System.out.println(first.equals(second));          // false
```

`compareTo` so theo giá trị số; `equals` xét cả giá trị và scale. Điều này ảnh hưởng `HashSet`/`HashMap` khi dùng `BigDecimal` làm khóa: 2.0 và 2.00 là hai key khác nhau nếu giữ nguyên biểu diễn. Nếu nghiệp vụ chỉ quan tâm giá trị số, cần một chính sách chuẩn hóa khóa nhất quán (ví dụ `stripTrailingZeros()`) trước cả lúc thêm và lúc tra cứu.

## 9. Chương trình Java 17+ minh họa lựa chọn theo tình huống

Lưu `NumberChoiceDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.List;
import java.util.OptionalInt;

public class NumberChoiceDemo {
    public static void main(String[] args) {
        int quantity = 50_000;
        int priceUnits = 50_000;
        long amount = Math.multiplyExact((long) quantity, priceUnits);
        System.out.println("long product: " + amount);

        BigInteger beyondLong = BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
        System.out.println("beyond long: " + beyondLong);

        BigDecimal exact = new BigDecimal("0.1").add(new BigDecimal("0.2"));
        System.out.println("decimal sum: " + exact);

        BigDecimal base = new BigDecimal("19.99");
        BigDecimal tax = base.multiply(new BigDecimal("0.075"))
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println("tax rounded: " + tax);
        System.out.println("with tax: " + base.add(tax));

        List<Integer> readings = List.of(3, 4);
        System.out.println("boxed list total: "
                + readings.stream().mapToInt(Integer::intValue).sum());
        OptionalInt missing = OptionalInt.empty();
        System.out.println("optional int empty: " + missing.isEmpty());
    }
}
```

Biên dịch và chạy:

```bash
javac NumberChoiceDemo.java
java NumberChoiceDemo
```

Stdout đã kiểm chứng bằng Java:

```text
long product: 2500000000
beyond long: 9223372036854775808
decimal sum: 0.3
tax rounded: 1.50
with tax: 21.49
boxed list total: 7
optional int empty: true
```

Một tình huống sử dụng nhiều kiểu là bình thường: `int` cho quantity, `long` cho tích cần miền 64 bit, `BigInteger` cho giá trị nguyên vượt 64 bit, `BigDecimal` cho decimal exact, và `Integer` trong generic collection. Không nên ép tất cả thành cùng một kiểu chỉ để trông nhất quán về mặt cú pháp.

## 10. Chuyển đổi qua ranh giới kiểu: dùng exact khi không cho mất dữ liệu

Dữ liệu có thể được tính bằng kiểu rộng hơn rồi cần lưu thành kiểu nhỏ; việc **chuyển đổi** phải là một bước có kiểm tra riêng.

| Chuyển từ | Có nguy cơ | Gợi ý |
| --- | --- | --- |
| `long` sang `int` | Mất bit/đổi dấu nếu ngoài miền | `Math.toIntExact(value)` |
| `BigInteger` sang `long` | Giá trị lớn hơn 64-bit | `longValueExact()` |
| `BigInteger` sang `int` | Giá trị ngoài 32-bit | `intValueExact()` |
| `BigDecimal` sang `long` | Phần lẻ hoặc vượt miền | `longValueExact()` |
| `BigDecimal` sang `int` | Phần lẻ hoặc vượt miền | `intValueExact()` |
| `BigDecimal` sang cents `long` | Còn phần nhỏ hơn đơn vị cents hoặc vượt miền | `movePointRight(2).longValueExact()` khi domain có scale 2 |
| `double` sang `int`/`long` | Làm tròn về 0, bão hòa ở biên, NaN; mất thông tin | Validation rõ miền/độ chính xác hoặc chuyển đổi theo domain |
| `BigDecimal` sang `double` | Mất độ chính xác, có thể ra vô cực | Chỉ khi bài toán chấp nhận xấp xỉ |

Đối với `BigDecimal`, chuyển exact sang `int`/`long` **không bắt buộc scale 0**: `new BigDecimal("2.00").longValueExact()` trả 2 vì không có phần lẻ có giá trị. Nhưng `new BigDecimal("2.01").longValueExact()` ném lỗi.

Không tự thay thế `longValueExact()` bằng `longValue()` nếu việc âm thầm bỏ phần thập phân hoặc bit vượt miền bị cấm.

### Ví dụ chuyển đổi có kiểm tra

Lưu `NumberBoundaryDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumberBoundaryDemo {
    public static void main(String[] args) {
        int x = 50_000;
        int y = 50_000;
        System.out.println("int overflow: " + (x * y));
        System.out.println("widen first: " + ((long) x * y));

        try {
            System.out.println(Math.toIntExact((long) x * y));
        } catch (ArithmeticException e) {
            System.out.println("narrowing rejected");
        }

        BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
        try {
            System.out.println(huge.longValueExact());
        } catch (ArithmeticException e) {
            System.out.println("big integer narrowing rejected");
        }

        BigDecimal amount = BigDecimal.valueOf(1234L, 2);
        System.out.println("minor units to decimal: " + amount);
        System.out.println("back to minor units: "
                + amount.movePointRight(2).longValueExact());

        try {
            new BigDecimal("12.345").movePointRight(2).longValueExact();
        } catch (ArithmeticException e) {
            System.out.println("fractional minor unit rejected");
        }

        BigDecimal d1 = new BigDecimal("2.0");
        BigDecimal d2 = new BigDecimal("2.00");
        System.out.println("numeric equal: " + (d1.compareTo(d2) == 0));
        System.out.println("object equal: " + d1.equals(d2));
        System.out.println("1/3 rounded: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"), 2, RoundingMode.HALF_UP));
    }
}
```

Biên dịch và chạy:

```bash
javac NumberBoundaryDemo.java
java NumberBoundaryDemo
```

Stdout đã kiểm chứng:

```text
int overflow: -1794967296
widen first: 2500000000
narrowing rejected
big integer narrowing rejected
minor units to decimal: 12.34
back to minor units: 1234
fractional minor unit rejected
numeric equal: true
object equal: false
1/3 rounded: 0.33
```

Ví dụ sử dụng **2 chữ số đơn vị nhỏ nhất** cho phép chuyển cents. Nếu domain không theo quy ước này (hoặc tỷ lệ cần nhiều chữ số trung gian), phải thay factor/scale và chính sách làm tròn phù hợp; không được áp dụng vô điều kiện cho mọi đơn vị tiền.

## 11. Wrapper và collection: null, boxing và hiệu năng

Lưu `BoxingChoiceDemo.java` để thấy rõ wrapper và primitive được chuyển đổi:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BoxingChoiceDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Integer wrapper = primitive;
        int unboxed = wrapper;
        System.out.println("unboxed: " + unboxed);
        System.out.println("wrapper value equality: "
                + Integer.valueOf(42).equals(wrapper));

        List<Integer> values = new ArrayList<>();
        values.add(3);
        values.add(4);
        System.out.println("collection sum: "
                + values.stream().mapToInt(Integer::intValue).sum());

        Integer nullable = null;
        System.out.println("nullable absent: " + Objects.isNull(nullable));
        try {
            int dangerous = nullable;
            System.out.println(dangerous);
        } catch (NullPointerException e) {
            System.out.println("null unboxing rejected");
        }

        System.out.println("parsed int: " + Integer.parseInt("17"));
    }
}
```

Chạy:

```bash
javac BoxingChoiceDemo.java
java BoxingChoiceDemo
```

Stdout:

```text
unboxed: 42
wrapper value equality: true
collection sum: 7
nullable absent: true
null unboxing rejected
parsed int: 17
```

Với các phép tổng hợp trên nhiều wrapper, có thể chuyển sang primitive stream bằng `mapToInt(Integer::intValue)`, `mapToLong(Long::longValue)` hoặc `mapToDouble(Double::doubleValue)`. **Chú ý kiểu luồng đầu vào**: `IntStream` đã là primitive, nên không dùng `mapToLong(Integer::longValue)` trên `IntStream`; thay vào đó dùng `asLongStream()` hoặc `mapToLong(x -> (long) x)`.

Primitive stream giúp hạn chế boxing trong những phép tính nhất định nhưng không xóa mọi chi phí object của collection gốc. Với dữ liệu khối lượng rất lớn, đo hiệu năng và profile thay vì chọn wrapper hay primitive theo cảm tính.

## 12. Chọn kiểu tính trung gian khác với kiểu lưu

Một số giá trị lưu được bằng `int` nhưng phép tính trung gian cần `long`; tương tự tổng hoặc tích của nhiều `long` có thể cần `BigInteger`. Khi tính decimal exact, có thể dùng `BigDecimal` rồi lưu bằng `long` số đơn vị nhỏ nhất **sau khi** đã làm tròn và kiểm tra.

Ví dụ xử lý đơn hàng:

```text
quantity: int hoặc long theo giới hạn từng dòng
unitPriceCents: long nếu đơn vị nhỏ nhất xác định
subtotalCents: long với multiplyExact, hoặc BigInteger nếu miền quá lớn
tax: BigDecimal với tỷ lệ/rounding từ domain
finalCents: long sau khi chuyển exact và kiểm tra miền
DB: BIGINT cents hoặc DECIMAL(p,s) theo schema
```

Đây là bản thiết kế tham khảo, không phải công thức bắt buộc cho hệ thống tiền tệ. Tùy phạm vi dữ liệu, có thể dùng `BigDecimal` làm cả kiểu tính lẫn kiểu lưu; hoặc dùng `BigInteger` ở bước tổng hợp khối lượng lớn. Phần quan trọng là **có contract rõ ràng tại ranh giới chuyển**.

Không chờ đến cuối mới phát hiện tràn: nếu một phép nhân `int` đã overflow, chuyển kết quả sai sang `BigInteger` không khôi phục được giá trị gốc. Hãy chọn kiểu đúng *trước* phép tính, hoặc dùng checked arithmetic.

## 13. Java API và database/JSON

Kiểu Java không tự quyết định miền và độ chính xác khi qua ranh giới hệ thống:

- **Database:** `INTEGER`, `BIGINT`, `DECIMAL(p,s)`, `FLOAT`/`DOUBLE` có miền và quy tắc chuyển đổi khác nhau tùy hệ quản trị. Kiểm tra schema, nullability, độ lớn, precision và scale, không trông chờ driver tự sửa dữ liệu.
- **JSON:** JSON number không phải kiểu `long` hay `BigDecimal` của Java. Một client JavaScript dùng `Number` có thể không giữ chính xác số nguyên lớn hơn `2^53 - 1`; cân nhắc chuỗi decimal hoặc giao thức hỗ trợ kiểu số lớn nếu tính nguyên vẹn là quan trọng.
- **NaN/Infinity:** `double` có giá trị không hữu hạn, nhưng JSON number chuẩn không biểu diễn NaN/Infinity. Cần chính sách từ chối hoặc encoding đặc biệt rõ ràng.
- **Nullable:** phân biệt `null` (không có giá trị), `0` (giá trị số không), và trường không xuất hiện. Tùy framework, wrapper có thể phù hợp cho nullable; primitive phù hợp cho trường bắt buộc với validation.
- **ID:** mã khách hàng, số tài khoản và chuỗi có số 0 đầu không mặc nhiên là số cần toán học; lưu dưới `String` khi tính chất định danh quan trọng.

Đặc biệt, nếu dữ liệu vào/ra phải chính xác decimal, đừng chuyển trung gian qua `double` trong serialization hoặc tính toán chỉ vì `double` dễ dùng.

## 14. Lỗi thường gặp khi chọn kiểu

| Sai lầm | Hậu quả | Quy tắc sửa |
| --- | --- | --- |
| Dùng `int` cho tổng có thể vượt 2^31-1 | Tràn âm/dương | `long`/`BigInteger` và kiểm tra miền |
| `long total = intA * intB` | Tràn `int` trước khi gán | Ép `(long) intA * intB` trước phép nhân |
| Dùng `double` cho cents exact | Sai số nhị phân | `long` đơn vị nhỏ nhất hoặc `BigDecimal` |
| Chọn `BigInteger` cho 7/2 rồi cần 3.5 | Chia nguyên không giữ phần lẻ | `BigDecimal`/phân số và rounding rõ |
| `new BigDecimal(0.1)` | Tạo decimal đúng với **xấp xỉ nhị phân**, không phải decimal 0.1 | `new BigDecimal("0.1")` |
| `BigDecimal.divide` khi 1/3 mà không rounding | `ArithmeticException` | Khai báo scale/MathContext/RoundingMode |
| `BigDecimal.equals` để so 2.0 và 2.00 theo giá trị số | False do scale khác | `compareTo == 0` |
| So hai wrapper bằng `==` | So identity object, phụ thuộc boxing/cache | `equals` hoặc `Objects.equals` |
| Unbox một wrapper null | `NullPointerException` | Kiểm tra null hoặc thiết kế API không nullable |
| Dùng `List<int>` | Không hợp lệ với Java 17 generics | `List<Integer>` hoặc primitive array/stream |
| `BigInteger.longValue()` khi dữ liệu vượt long | Mất bit | `longValueExact()` |
| `BigDecimal.longValue()` khi còn phần lẻ | Bỏ phần lẻ, có thể sai nghiệp vụ | `longValueExact()` khi cần exact |
| Dùng `float` để “tăng độ chính xác” | Thực tế ít precision hơn double | `double` hoặc `BigDecimal` theo nhu cầu |
| Dùng số nguyên cho mã có leading zero | Mất 0 đầu | `String` |
| Dùng `Integer` vì “object luôn tốt hơn” | Null/boxing/chi phí không cần thiết | Primitive khi bắt buộc có giá trị và không cần generics |
| Dùng `BigDecimal` ở mọi phép đo xấp xỉ | Chi phí phức tạp không mang lại độ chính xác nguồn | `double` khi sai số được chấp nhận |

## 15. Checklist lựa chọn trước khi quyết định

Dùng các câu hỏi sau để đi từ yêu cầu đến kiểu:

1. **Giá trị có phải số cần tính?** Nếu chỉ là định danh, cân nhắc `String`.
2. **Chỉ nguyên hay có phần lẻ?** Nguyên: `int`/`long`/`BigInteger`; thập phân: `double` hoặc `BigDecimal`.
3. **Miền lớn nhất của cả kết quả trung gian và cuối?** Tính cả nhân, cộng dồn, lũy thừa và dữ liệu tương lai.
4. **Có chấp nhận sai số IEEE 754?** Nếu không, đừng chọn `float`/`double` để giữ decimal chính xác.
5. **Có cần null?** Primitive không null; wrapper null nhưng phải kiểm tra trước unboxing; có thể dùng `OptionalInt/Long/Double` ở API kết quả.
6. **Có generics/collection không?** Chọn wrapper hoặc `BigInteger/BigDecimal` cho generic Java 17.
7. **Có yêu cầu rounding cụ thể?** Với `BigDecimal`, xác định scale và `RoundingMode` tại ranh giới đúng.
8. **Có conversion về kiểu nhỏ hơn không?** Dùng `Math.toIntExact`, `intValueExact/longValueExact` hoặc kiểm tra đầy đủ.
9. **Schema và client có hiểu giá trị không?** Kiểm tra JDBC, JSON/JavaScript, database precision/scale và nullability.
10. **Đã có test biên chưa?** Thử MIN/MAX, overflow, 0, số âm, 0.1, 1/3, null và biểu diễn decimal khác scale.

## 16. Câu hỏi tự kiểm tra

1. **Lưu số lượng nhỏ có giá trị bắt buộc và không cần generics?** Thường `int`.
2. **Tổng hai `int` có thể vượt `Integer.MAX_VALUE`?** Chuyển sang `long` trước phép cộng hoặc dùng checked arithmetic.
3. **Dùng `List<int>` trong Java 17 được không?** Không; dùng `List<Integer>`.
4. **Nếu `Integer` là null rồi unbox sang `int`?** Ném `NullPointerException`.
5. **Cần một số nguyên exact lớn hơn `Long.MAX_VALUE`?** `BigInteger`.
6. **Cần giữ 0.1 và 0.2 chính xác decimal?** `BigDecimal` từ chuỗi hoặc nguồn decimal chính xác.
7. **`BigInteger.divide` có cho phần lẻ không?** Không; nó là phép chia nguyên.
8. **Vì sao `BigDecimal("2.0").equals(BigDecimal("2.00"))` false?** Scale khác; `compareTo` mới phù hợp khi chỉ so giá trị toán học.
9. **Chuyển `BigDecimal("12.345")` thành cents `long` theo scale 2 mà cấm mất dữ liệu?** `movePointRight(2).longValueExact()` ném lỗi; cần xử lý rounding theo nghiệp vụ nếu được phép.
10. **`double` có chứa chính xác mọi số nguyên `long` không?** Không, vì precision hữu hạn.
11. **Khi nào chọn wrapper thay primitive?** Khi cần nullable, generics hoặc API yêu cầu object; không tự động chọn wrapper cho mọi trường.
12. **Tại sao `BigDecimal` không luôn tốt hơn `double`?** `double` phù hợp nhiều phép tính xấp xỉ và có chi phí thấp; `BigDecimal` có overhead và cần quản lý scale/rounding.

## 17. Kết luận

Có thể ghi nhớ một bảng chọn tối giản:

- **`int`/`long`:** số nguyên có miền xác định, giá trị bắt buộc; chọn theo phạm vi cả phép tính.
- **`Integer`/`Long` và wrapper:** cùng ý nghĩa số với primitive tương ứng nhưng cần object, nullable hoặc generics.
- **`double` (và `float` khi có lý do):** số thực nhị phân xấp xỉ, thích hợp nhiều bài toán khoa học/thống kê nhưng không bảo toàn mọi decimal.
- **`BigInteger`:** số nguyên exact vượt kiểu cố định.
- **`BigDecimal`:** thập phân exact và rounding nghiệp vụ, đặc biệt tiền hoặc dữ liệu decimal cần kiểm soát.

Luôn xác định **miền, độ chính xác, nullability, đơn vị và ranh giới dữ liệu** trước khi chọn. Trong một luồng xử lý thực tế, nhiều kiểu có thể cùng xuất hiện — đó là thiết kế đúng nếu mỗi kiểu có vai trò rõ ràng và chuyển đổi giữa chúng được kiểm tra.
