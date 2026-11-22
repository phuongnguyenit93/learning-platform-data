# NumberFormatException và chuyển đổi dữ liệu đầu vào trong Java

Khi đọc dữ liệu từ biểu mẫu, API, file CSV, dòng lệnh hoặc cấu hình, chương trình thường nhận **String** trước khi chuyển thành **int**, **long**, **double** hay **BigDecimal**. Nếu chuỗi không đúng cú pháp số hoặc không thể biểu diễn trong kiểu đích, nhiều API Java báo **java.lang.NumberFormatException**.

Đây là **unchecked exception**, nằm trong chuỗi kế thừa **Throwable → Exception → RuntimeException → IllegalArgumentException → NumberFormatException**. Trình biên dịch không bắt buộc khai báo **throws NumberFormatException** hay sử dụng **try-catch**. Tuy nhiên, đầu vào không tin cậy cần được kiểm tra, phản hồi và ghi nhận rõ ràng. Một chuỗi parse thành công cũng chưa chắc thỏa mãn quy tắc nghiệp vụ.

Bài học trình bày cú pháp chuyển số nguyên và số thực, phạm vi kiểu số, cơ số, dấu/khoảng trắng, số thập phân chính xác, Unicode, locale và cách đặt ranh giới xử lý ngoại lệ. Các chương trình hoàn chỉnh chạy bằng Java 17+.

## 1. Hiểu đúng ngoại lệ và hợp đồng API

Ví dụ **Integer.parseInt("abc")** ném NumberFormatException, vì ký tự đầu vào không tạo thành số nguyên hợp lệ. **Integer.parseInt("2147483648")** cũng ném cùng loại lỗi dù chuỗi chỉ gồm chữ số: giá trị vượt giới hạn **Integer.MAX_VALUE = 2147483647**.

Điều cần phân biệt:

- **Lỗi cú pháp:** chuỗi rỗng, sai chữ số, có ký tự không được phép.
- **Lỗi miền biểu diễn:** giá trị số nguyên lớn hơn hoặc nhỏ hơn miền kiểu đích.
- **Lỗi nghiệp vụ:** parse thành công nhưng giá trị vi phạm quy tắc, chẳng hạn tuổi 200 hoặc số lượng âm.
- **Lỗi bước chuyển đổi khác:** long hợp lệ nhưng không thể chuyển chính xác xuống int bằng **Math.toIntExact**, khi ấy Java ném **ArithmeticException**, không phải NumberFormatException.

Vì NumberFormatException kế thừa IllegalArgumentException, một nhánh **catch (IllegalArgumentException ex)** có thể bắt nó. Nếu hai nhánh cùng cấp tồn tại thì phải đặt nhánh **catch (NumberFormatException ex)** trước; đặt nhánh cha trước sẽ che nhánh con, gây lỗi biên dịch.

Thông điệp **ex.getMessage()** không phải mã lỗi nghiệp vụ ổn định. Nó có thể chứa chuỗi đầu vào và thay đổi giữa overload/JDK; không nên phân loại lỗi bằng cách so sánh chính xác toàn bộ thông điệp từ JDK.

## 2. Cú pháp của Integer.parseInt(String)

Với cơ số 10, parser chấp nhận chữ số hợp lệ và có thể có dấu cộng/trừ ở đầu, miễn giá trị nằm trong miền int.

| Đầu vào | Kết quả |
| --- | --- |
| "42" | int 42 |
| "+7" | int 7 |
| "-12" | int -12 |
| "0009" | int 9 |
| "" | NumberFormatException |
| " 42 " | NumberFormatException vì không tự bỏ khoảng trắng |
| "12.5" | NumberFormatException vì đây không phải số nguyên |
| "1,000" | NumberFormatException vì có dấu phân nhóm |
| "1_000" | NumberFormatException; dấu gạch dưới trong source numeric literal không áp dụng cho chuỗi runtime |
| "0xFF" | NumberFormatException với parseInt cơ số 10 |
| "2147483648" | NumberFormatException vì vượt int |
| null | NumberFormatException |

Một chương trình Java có thể viết numeric literal **1_000**, nhưng **Integer.parseInt("1_000")** không tự hiểu cú pháp dấu gạch dưới đó. Tương tự, dấu thập phân dùng trong locale không tự động được parser số nguyên nhận diện.

### Chương trình 1: parse thành công và thất bại

Lưu thành **IntegerInputDemo.java**:

~~~java
public class IntegerInputDemo {
    static void inspect(String raw) {
        try {
            int value = Integer.parseInt(raw);
            System.out.println("ok=[" + raw + "]:" + value);
        } catch (NumberFormatException ex) {
            System.out.println("invalid=[" + raw + "]");
        }
    }

    public static void main(String[] args) {
        inspect("27");
        inspect("-4");
        inspect("+6");
        inspect("");
        inspect("2.5");
        inspect("2147483648");
        inspect(" 12 ");
    }
}
~~~

~~~bash
javac -encoding UTF-8 IntegerInputDemo.java
java IntegerInputDemo
~~~

Kết quả:

~~~text
ok=[27]:27
ok=[-4]:-4
ok=[+6]:6
invalid=[]
invalid=[2.5]
invalid=[2147483648]
invalid=[ 12 ]
~~~

Chương trình cố ý không in thông điệp JDK để stdout không phụ thuộc phiên bản. Khi hiển thị lỗi cho người dùng, hãy tự mô tả trường nhập và định dạng được phép.

## 3. Chọn phương thức theo kiểu số đích

| Nhu cầu | API |
| --- | --- |
| Số nguyên có dấu 32 bit | **Integer.parseInt(text)**, trả primitive int |
| Đối tượng Integer | **Integer.valueOf(text)**, trả wrapper Integer |
| Số nguyên có dấu 64 bit | **Long.parseLong(text)** |
| Số nguyên độ lớn tùy ý | **new BigInteger(text)** |
| Số nguyên với cơ số 2 đến 36 | **Integer.parseInt(text, radix)** |
| Chuỗi có tiền tố chỉ cơ số theo quy tắc Java | **Integer.decode(text)** |
| Số thực nhị phân 64 bit | **Double.parseDouble(text)** |
| Số thực nhị phân 32 bit | **Float.parseFloat(text)** |
| Giá trị decimal cần độ chính xác từ chuỗi | **new BigDecimal(text)** |
| Chuỗi số theo locale | **NumberFormat** hoặc **DecimalFormat** với Locale rõ |

**Integer.valueOf("42")** cho giá trị số bằng Integer.parseInt("42"), nhưng trả đối tượng wrapper. Không dùng phép so sánh tham chiếu **==** giữa hai wrapper để quyết định giá trị bằng nhau; dùng phương thức equals hoặc giá trị primitive khi thích hợp.

Đừng chọn kiểu số chỉ theo chiều dài chuỗi. Nếu dữ liệu là mã bưu chính hoặc ID có số 0 đầu, chuyển thành int có thể làm mất biểu diễn gốc. Trường đó có thể nên giữ kiểu String nếu không có phép toán số học.

## 4. Cơ số: parseInt(radix) và decode không giống nhau

Integer.parseInt(text, radix) đọc chữ số ở cơ số **2..36**. Trong khi đó, Integer.decode nhận cú pháp có tiền tố như **0x**, **#**, và có quy tắc octal khi chuỗi có số 0 đầu.

### Chương trình 2: khác biệt cơ số

Lưu thành **RadixAndDecodeDemo.java**:

~~~java
public class RadixAndDecodeDemo {
    public static void main(String[] args) {
        System.out.println("binary=" + Integer.parseInt("101101", 2));
        System.out.println("hex=" + Integer.parseInt("7F", 16));
        System.out.println("negativeHex=" + Integer.parseInt("-20", 16));
        System.out.println("base36=" + Integer.parseInt("Z", 36));
        System.out.println("decimal010=" + Integer.parseInt("010"));
        System.out.println("decode010=" + Integer.decode("010"));
        System.out.println("decodeHex=" + Integer.decode("0x2A"));
        System.out.println("decodeHash=" + Integer.decode("#2A"));

        try {
            Integer.parseInt("0x2A");
        } catch (NumberFormatException ex) {
            System.out.println("prefixed=invalid");
        }
        try {
            Integer.parseInt("101", 1);
        } catch (NumberFormatException ex) {
            System.out.println("radix1=invalid");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 RadixAndDecodeDemo.java
java RadixAndDecodeDemo
~~~

Kết quả:

~~~text
binary=45
hex=127
negativeHex=-32
base36=35
decimal010=10
decode010=8
decodeHex=42
decodeHash=42
prefixed=invalid
radix1=invalid
~~~

Khi dữ liệu người dùng là số thập phân, tránh dùng decode một cách tùy tiện: giá trị **"010"** có thể bị hiểu thành octal 8, không phải decimal 10. Dùng parseInt(text, 10) khi hợp đồng thật sự yêu cầu cơ số 10.

## 5. Overflow: lỗi parse khác lỗi ép kiểu

Giới hạn số nguyên Java:

~~~text
int  : -2147483648 .. 2147483647
long : -9223372036854775808 .. 9223372036854775807
~~~

Một chuỗi vượt giới hạn int gây NumberFormatException ở **Integer.parseInt**. Nhưng sau khi parse thành công một long, nếu muốn chuyển chính xác về int bằng **Math.toIntExact**, thất bại gây ArithmeticException.

### Chương trình 3: ba cách xử lý miền số nguyên

Lưu thành **NumericBoundsDemo.java**:

~~~java
import java.math.BigInteger;

public class NumericBoundsDemo {
    public static void main(String[] args) {
        String large = "2147483648";
        System.out.println("long=" + Long.parseLong(large));
        System.out.println("big=" + new BigInteger(large));

        try {
            Integer.parseInt(large);
        } catch (NumberFormatException ex) {
            System.out.println("int=out-of-range");
        }

        try {
            Math.toIntExact(Long.parseLong(large));
        } catch (ArithmeticException ex) {
            System.out.println("narrowing=out-of-range");
        }

        String huge = "9223372036854775808";
        try {
            Long.parseLong(huge);
        } catch (NumberFormatException ex) {
            System.out.println("long=out-of-range");
        }
        System.out.println("bigHuge=" + new BigInteger(huge));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NumericBoundsDemo.java
java NumericBoundsDemo
~~~

Kết quả:

~~~text
long=2147483648
big=2147483648
int=out-of-range
narrowing=out-of-range
long=out-of-range
bigHuge=9223372036854775808
~~~

Việc ép kiểu **(int) someLong** có thể làm mất các bit cao và không tạo ngoại lệ. Để kiểm tra chính xác, dùng Math.toIntExact hoặc kiểm tra miền trước khi chuyển. BigInteger cho phép số nguyên rất lớn nhưng vẫn cần giới hạn độ dài đầu vào để tránh chi phí CPU/bộ nhớ không kiểm soát.

## 6. Double.parseDouble và những giá trị không hữu hạn

NumberFormatException không được ném cho tất cả giá trị số thực mà nghiệp vụ không muốn chấp nhận. Double.parseDouble hỗ trợ ký hiệu mũ, NaN, Infinity và có thể trả Infinity cho số mũ quá lớn.

Ví dụ:

- **Double.parseDouble("1.5e2")** → 150.0.
- **Double.parseDouble("NaN")** → NaN.
- **Double.parseDouble("Infinity")** → vô cực dương.
- **Double.parseDouble("1e309")** → vô cực trên kiểu double.
- **Double.parseDouble("1,5")** → NumberFormatException.
- **Double.parseDouble("1_000")** → NumberFormatException.

Khác Integer.parseInt, Double.parseDouble chấp nhận một số khoảng trắng đầu/cuối theo hợp đồng parser tương ứng String.trim(). Không được suy luận rằng mọi API chuyển số đều có cùng chính sách khoảng trắng.

### Chương trình 4: tách parse sai khỏi giá trị không hữu hạn

Lưu thành **FloatingInputDemo.java**:

~~~java
public class FloatingInputDemo {
    static void inspect(String raw) {
        try {
            double value = Double.parseDouble(raw);
            if (!Double.isFinite(value)) {
                System.out.println("not-finite=[" + raw + "]");
            } else {
                System.out.println("finite=[" + raw + "]:" + value);
            }
        } catch (NumberFormatException ex) {
            System.out.println("invalid=[" + raw + "]");
        }
    }

    public static void main(String[] args) {
        inspect("12.5");
        inspect("1.5e2");
        inspect("NaN");
        inspect("Infinity");
        inspect("1e309");
        inspect("1,5");
        inspect("1_000");
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloatingInputDemo.java
java FloatingInputDemo
~~~

Kết quả:

~~~text
finite=[12.5]:12.5
finite=[1.5e2]:150.0
not-finite=[NaN]
not-finite=[Infinity]
not-finite=[1e309]
invalid=[1,5]
invalid=[1_000]
~~~

Với một trường yêu cầu số hữu hạn, parse thành công mới là bước đầu: tiếp tục kiểm tra **Double.isFinite(value)** rồi mới xét min/max và quy tắc nghiệp vụ.

## 7. BigDecimal(String) cho số thập phân cần chính xác

Double dùng biểu diễn nhị phân, nên **0.1 + 0.2** trong double thường không đúng chính xác giá trị thập phân 0.3. Khi dữ liệu nguồn là chuỗi số tiền, **new BigDecimal(String)** thường phù hợp hơn.

### Chương trình 5: số thập phân và lỗi chuyển đổi

Lưu thành **DecimalMoneyDemo.java**:

~~~java
import java.math.BigDecimal;

public class DecimalMoneyDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        System.out.println("exact=" + a.add(b));
        System.out.println("doubleSum=" + (0.1 + 0.2));
        System.out.println("scientific="
                + new BigDecimal("1.25e2").toPlainString());

        try {
            new BigDecimal("1,25");
        } catch (NumberFormatException ex) {
            System.out.println("comma=invalid");
        }

        try {
            new BigDecimal("NaN");
        } catch (NumberFormatException ex) {
            System.out.println("nan=invalid");
        }

        try {
            new BigDecimal("12.5").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("fraction=not-an-exact-int");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DecimalMoneyDemo.java
java DecimalMoneyDemo
~~~

Kết quả:

~~~text
exact=0.3
doubleSum=0.30000000000000004
scientific=125
comma=invalid
nan=invalid
fraction=not-an-exact-int
~~~

Giá trị decimal từ chuỗi được BigDecimal bảo toàn. BigDecimal không có giá trị NaN/Infinity như double; chuỗi không hợp lệ có thể tạo NumberFormatException. Còn phương thức **intValueExact()** có thể ném ArithmeticException khi có phần lẻ hoặc vượt miền int.

Tránh dùng new BigDecimal(someDouble) chỉ để cố phục hồi giá trị văn bản ban đầu: double có thể đã mang sai số nhị phân. Nếu nhận chuỗi decimal, ưu tiên parse trực tiếp từ chuỗi.

## 8. Xác thực đầu vào theo tầng, không chỉ thử parse

Một trường tuổi có thể có hợp đồng:

1. Bắt buộc nhập khác null/rỗng.
2. Cho phép bỏ khoảng trắng đầu và cuối bằng String.strip().
3. Chỉ chấp nhận chữ số ASCII 0..9, không cho dấu âm/dương.
4. Giá trị phải nằm trong miền int.
5. Tuổi phải không vượt 150.

~~~text
Raw input
  |
  +-- null / empty? -> "age required"
  |
  v
String.strip()
  |
  +-- not [0-9]+? -> "age must contain ASCII digits"
  |
  v
Integer.parseInt()
  |
  +-- NFE? -> "age out of integer range"
  |
  v
age <= 150?
  |
  +-- no -> "age must be <= 150"
  |
  v
Valid age
~~~

### Chương trình 6: lỗi đầu vào có ngữ cảnh và giữ cause

Lưu thành **ValidatedAgeDemo.java**:

~~~java
public class ValidatedAgeDemo {
    static int parseAge(String raw) {
        if (raw == null || raw.strip().isEmpty()) {
            throw new IllegalArgumentException("age required");
        }

        String text = raw.strip();
        if (!text.matches("[0-9]+")) {
            throw new IllegalArgumentException(
                    "age must contain ASCII digits");
        }

        final int age;
        try {
            age = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "age out of integer range", ex);
        }

        if (age > 150) {
            throw new IllegalArgumentException(
                    "age must be <= 150");
        }
        return age;
    }

    static void inspect(String raw) {
        try {
            System.out.println("age=" + parseAge(raw));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        inspect(" 21 ");
        inspect("-1");
        inspect("200");
        inspect("2147483648");
        inspect("");
        inspect(null);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidatedAgeDemo.java
java ValidatedAgeDemo
~~~

Kết quả:

~~~text
age=21
invalid=age must contain ASCII digits
invalid=age must be <= 150
invalid=age out of integer range
invalid=age required
invalid=age required
~~~

Ở đây, **"200"** parse đúng nhưng bị loại vì chính sách tuổi; **"-1"** bị loại ở bước grammar; **"2147483648"** qua bước grammar nhưng lỗi miền int. Khi chuyển NumberFormatException sang IllegalArgumentException với tham số **cause**, thông tin kỹ thuật ban đầu vẫn có thể truy ở tầng logging.

Một trường khác có thể cho phép dấu âm hoặc chữ số Unicode. Vì vậy không nên áp dụng chính sách regex ở ví dụ tuổi một cách máy móc cho mọi loại dữ liệu.

## 9. Chữ số Unicode và khác biệt với ASCII

Integer.parseInt sử dụng Character.digit để nhận chữ số theo cơ số, không chỉ ký tự ASCII trong một số tình huống. Ngược lại, regex **[0-9]+** trong ví dụ tuổi chỉ cho phép ASCII.

### Chương trình 7: số Arabic-Indic

Lưu thành **UnicodeDigitDemo.java**:

~~~java
public class UnicodeDigitDemo {
    public static void main(String[] args) {
        String arabicIndic = "\u0661\u0662";
        System.out.println("parsed=" + Integer.parseInt(arabicIndic));
        System.out.println("asciiOnly="
                + arabicIndic.matches("[0-9]+"));
        System.out.println("digit=" + Character.digit('\u0661', 10));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnicodeDigitDemo.java
java UnicodeDigitDemo
~~~

Kết quả:

~~~text
parsed=12
asciiOnly=false
digit=1
~~~

Các ký tự Unicode U+0661 và U+0662 là chữ số Arabic-Indic tương ứng 1 và 2. Nếu hệ thống giao tiếp với một dịch vụ chỉ chấp nhận ASCII, cần xác thực rõ; nếu hỗ trợ nhập liệu đa ngôn ngữ, cần công bố/kiểm thử chính sách Unicode. Một dấu trừ typographic không nhất thiết được parse như dấu trừ ASCII.

## 10. Xử lý batch: trả trạng thái cho từng mục

Nếu các dòng CSV độc lập, một mục nhập sai không nhất thiết phải dừng toàn bộ batch. Có thể chuyển từng mục thành một giá trị biểu diễn kết quả thay vì ném lỗi dừng vòng lặp.

### Chương trình 8: record mang kết quả hoặc lỗi

Lưu thành **BatchNumberParsingDemo.java**:

~~~java
import java.util.List;

public class BatchNumberParsingDemo {
    record ParseResult(String raw, Integer value, String error) {
        boolean success() {
            return error == null;
        }
    }

    static ParseResult parseOne(String raw) {
        try {
            return new ParseResult(raw, Integer.parseInt(raw), null);
        } catch (NumberFormatException ex) {
            return new ParseResult(raw, null, "invalid integer");
        }
    }

    public static void main(String[] args) {
        for (String raw : List.of("10", "bad", "25", "2147483648")) {
            ParseResult result = parseOne(raw);
            if (result.success()) {
                System.out.println("ok=" + result.raw()
                        + ":" + result.value());
            } else {
                System.out.println("error=" + result.raw()
                        + ":" + result.error());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BatchNumberParsingDemo.java
java BatchNumberParsingDemo
~~~

Kết quả:

~~~text
ok=10:10
error=bad:invalid integer
ok=25:25
error=2147483648:invalid integer
~~~

Record là tính năng chuẩn của Java 17. Ví dụ minh họa cách gom lỗi theo phần tử; ở môi trường sản xuất nên áp đặt bất biến như **thành công hoặc thất bại, không đồng thời cả hai**. Nếu tác vụ cần tính nguyên tử, việc tiếp tục sau lỗi có thể không phù hợp; lựa chọn này thuộc hợp đồng nghiệp vụ.

## 11. Dữ liệu dòng lệnh và kiểm tra số lượng đối số

Khi truy cập **args[0]**, một lỗi khác có thể xảy ra **trước khi parse**: nếu chương trình chạy không có đối số, việc truy cập mảng gây ArrayIndexOutOfBoundsException. Vì vậy phải kiểm tra **args.length**.

Lưu thành **CommandLineNumberDemo.java**:

~~~java
public class CommandLineNumberDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("usage: java CommandLineNumberDemo <count>");
            return;
        }

        final int count;
        try {
            count = Integer.parseInt(args[0]);
        } catch (NumberFormatException ex) {
            System.out.println("count must be an integer");
            return;
        }

        if (count < 0) {
            System.out.println("count must be non-negative");
            return;
        }

        System.out.println("count=" + count);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CommandLineNumberDemo.java
java CommandLineNumberDemo 12
java CommandLineNumberDemo abc
java CommandLineNumberDemo -2
~~~

Kết quả của ba lần chạy:

~~~text
count=12
count must be an integer
count must be non-negative
~~~

Khi không có đối số, chương trình in dòng usage. Một CLI thực tế có thể cần exit status khác 0, nhưng không nên dùng System.exit trong ví dụ chỉ nhằm giải thích cơ chế parse.

## 12. Dấu thập phân theo locale và phân tích toàn chuỗi

Integer.parseInt và Double.parseDouble không tự động phân tích định dạng theo mọi vùng miền. Chẳng hạn chuỗi **"1.234,5"** có nghĩa 1234.5 theo Locale.GERMANY, nhưng không hợp lệ khi đưa trực tiếp cho Double.parseDouble.

Có thể dùng **NumberFormat.getNumberInstance(Locale.GERMANY)**. Lưu ý: **NumberFormat.parse(String, ParsePosition)** có thể parse thành công một tiền tố rồi dừng trước hậu tố sai. Nếu dữ liệu phải khớp toàn chuỗi, hãy kiểm tra vị trí kết thúc.

Lưu thành **LocaleNumberDemo.java**:

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberDemo {
    static Number parseAll(String text, Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        ParsePosition position = new ParsePosition(0);
        Number value = format.parse(text, position);

        if (value == null || position.getIndex() != text.length()) {
            throw new IllegalArgumentException("invalid localized number");
        }
        return value;
    }

    public static void main(String[] args) {
        Number value = parseAll("1.234,5", Locale.GERMANY);
        System.out.println("value=" + value.doubleValue());

        try {
            parseAll("1.234,5tail", Locale.GERMANY);
        } catch (IllegalArgumentException ex) {
            System.out.println("suffix=invalid");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleNumberDemo.java
java LocaleNumberDemo
~~~

Kết quả với dữ liệu locale tiêu chuẩn:

~~~text
value=1234.5
suffix=invalid
~~~

Trong ví dụ, IllegalArgumentException được **hàm parseAll tự tạo** khi chuỗi không được tiêu thụ hết; không nên cho rằng NumberFormat.parse luôn ném NumberFormatException giống Integer.parseInt. Đối với tiền cần chính xác, có thể cấu hình DecimalFormat để nhận BigDecimal và kiểm tra scale/giới hạn.

## 13. Đặt catch đúng ranh giới, giữ nguyên nhân gốc

Đoạn mã sau có vấn đề về phạm vi bắt lỗi:

~~~java
try {
    int id = Integer.parseInt(input);
    process(id);
} catch (NumberFormatException ex) {
    showInvalidInput();
}
~~~

Đây là mã **minh họa không độc lập**, giả sử các hàm/biến đã định nghĩa. Nếu process(id) cũng ném NumberFormatException vì một lỗi nội bộ khác, nhánh catch có thể nhận nhầm thành lỗi dữ liệu đầu vào.

Nên tách vùng try chỉ quanh phép chuyển:

~~~java
final int id;
try {
    id = Integer.parseInt(input);
} catch (NumberFormatException ex) {
    throw new InputValidationException(
            "ID must be a decimal integer", ex);
}
process(id);
~~~

Đoạn sau giả định có **InputValidationException(String, Throwable)**. Nó giữ NumberFormatException gốc làm cause của lỗi ứng dụng và không nuốt các ngoại lệ khác phát sinh sau bước parse.

Nguyên tắc: **bắt ngoại lệ ở nơi có đủ ngữ cảnh**, nhưng đừng bao trùm quá nhiều logic không liên quan. Thông báo đưa ra cho người dùng nên xác định trường nhập và định dạng yêu cầu, không chỉ in nguyên stack trace hoặc dựa trên message có thể chứa dữ liệu nhạy cảm.

## 14. Parse thành công chưa chắc là hợp lệ

Một vài trường hợp cần xử lý riêng:

- **Integer.parseInt("-3")** thành công nhưng số lượng hàng hóa có thể phải không âm.
- **Integer.parseInt("0007")** trả 7 nhưng mã định danh có thể cần giữ đủ bốn ký tự.
- **Double.parseDouble("NaN")** thành công nhưng giá/điểm số thường phải hữu hạn.
- **new BigDecimal("1.234")** thành công nhưng đơn vị tiền có thể giới hạn hai chữ số sau dấu thập phân.
- **Integer.parseInt("+10")** chấp nhận dấu cộng nhưng hợp đồng giao thức có thể cấm.
- **Integer.parseInt** có thể chấp nhận chữ số Unicode trong khi một hệ thống khác chỉ hỗ trợ ASCII.
- Một chuỗi rất dài có thể gây chi phí parse quá lớn. Dữ liệu không tin cậy cần hạn mức độ dài và kích thước phù hợp.

Luồng xác thực có thể là: **kiểm tra hiện diện → chuẩn hóa được phép → grammar → parse → kiểm tra miền và ý nghĩa nghiệp vụ → tạo phản hồi**. Không nhất thiết dùng regex cho mọi trường; regex phức tạp còn có thể làm code khó bảo trì.

## 15. Lỗi thường gặp và cách tránh

| Sai lầm | Sự thật / cách sửa |
| --- | --- |
| Nghĩ NumberFormatException là checked exception | Nó là RuntimeException; compiler không buộc throws |
| Nghĩ parseInt tự trim | Không; cần chuẩn hóa đầu/cuối nếu hợp đồng cho phép |
| Nhầm numeric literal 1_000 và chuỗi "1_000" | Dấu gạch dưới trong chuỗi bị parseInt từ chối |
| Dùng parseInt("0xFF") để đọc hex có prefix | Dùng parseInt("FF",16) hoặc decode theo hợp đồng |
| Dùng decode cho decimal có số 0 đầu | Decode có thể hiểu octal |
| Cho rằng parseInt overflow thì wrap | ParseInt ném NumberFormatException |
| Bắt NumberFormatException cho Math.toIntExact | Math.toIntExact ném ArithmeticException |
| Xem parseDouble("NaN") là lỗi cú pháp | Nó trả NaN; phải tự kiểm tra hữu hạn |
| Dùng double cho tiền cần chính xác | Dùng BigDecimal từ chuỗi |
| Bỏ kiểm tra đầu vào null/rỗng | Hãy báo lỗi trường bắt buộc một cách rõ ràng |
| Xem NumberFormat.parse luôn đọc toàn chuỗi | Kiểm tra ParsePosition |
| Bắt Exception quá rộng rồi trả 0 | Có thể che bug nội bộ và làm dữ liệu giả thành hợp lệ |
| Chỉ test chuỗi đẹp | Test overflow, rỗng, dấu, locale, Unicode, NaN và domain |
| Ghi nguyên ex.getMessage() vào log công khai | Có thể lộ dữ liệu đầu vào không mong muốn |

## 16. Checklist code review và kiểm thử

1. Đây là giá trị số thật hay một ID dạng ký tự?
2. Kiểu đích int, long, BigInteger, double hay BigDecimal có đúng miền và độ chính xác?
3. Đầu vào null, rỗng, chỉ khoảng trắng được xử lý thế nào?
4. Cho phép dấu cộng/trừ, số 0 đầu, khoảng trắng, chữ số Unicode và dấu phân nhóm không?
5. Có chọn đúng cơ số và tránh decode khi không có cú pháp prefix không?
6. Khi số quá lớn, ứng dụng báo lỗi ổn định hay lỡ làm mất thông tin?
7. Số thực có kiểm tra Double.isFinite và miền nghiệp vụ không?
8. Dữ liệu locale được parse toàn chuỗi chưa?
9. Trường có giới hạn số ký tự và độ dài giá trị không?
10. Catch có chỉ bao phép parse, thay vì cả bước xử lý có thể lỗi nội bộ không?
11. Người dùng nhận tên trường và cách sửa, còn logger giữ cause khi cần không?
12. Với batch, chính sách dừng hay tiếp tục có phù hợp yêu cầu nguyên tử của giao dịch không?

## 17. Câu hỏi tự kiểm tra

**1.** NumberFormatException là checked hay unchecked? **Unchecked**, vì là subclass của RuntimeException.

**2.** Integer.parseInt(" 12 ") trả gì? Ném NumberFormatException; khoảng trắng không được tự bỏ.

**3.** Integer.parseInt("2147483648") có wrap thành âm không? Không; ném NumberFormatException vì vượt miền int.

**4.** Integer.parseInt("010") khác Integer.decode("010") thế nào? Kết quả 10 và 8.

**5.** Double.parseDouble("NaN") ném lỗi không? Không; trả NaN. Cần Double.isFinite khi domain yêu cầu số hữu hạn.

**6.** Khi nào chọn BigDecimal(String)? Khi cần giữ decimal chính xác từ chuỗi, đặc biệt trong tính toán tiền/giá trị có yêu cầu độ chính xác.

**7.** Math.toIntExact(Long.parseLong("2147483648")) ném loại gì? ArithmeticException ở bước narrowing.

**8.** Một tuổi 200 parse thành công có nghĩa hợp lệ chưa? Chưa; vi phạm miền tuổi trong ví dụ.

**9.** NumberFormat.parse có thể bỏ sót hậu tố sai không? Có thể; kiểm tra ParsePosition khi cần parse toàn chuỗi.

**10.** Vì sao không nên catch NumberFormatException quanh cả parse và process(id)? Vì có thể gán nhầm NumberFormatException từ process thành lỗi đầu vào.

**11.** Một dòng CSV lỗi có bắt buộc dừng mọi dòng còn lại không? Không nhất thiết; phụ thuộc hợp đồng và tính nguyên tử nghiệp vụ.

**12.** Vì sao không nên chỉ ghi ex.getMessage() ra UI? Vì thông điệp có thể thiếu ngữ cảnh hoặc chứa dữ liệu nhập nhạy cảm; hãy tạo thông báo lỗi theo trường và mã ứng dụng.

## Tài liệu tham khảo chuẩn

- [Java SE 21 API — NumberFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NumberFormatException.html).
- [Java SE 21 API — Integer.parseInt, Integer.valueOf, Integer.decode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html).
- [Java SE 21 API — Long.parseLong](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html).
- [Java SE 21 API — Double.parseDouble và Double.isFinite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [Java SE 21 API — BigInteger(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html).
- [Java SE 21 API — BigDecimal(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
- [Java SE 21 API — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html).
- [JLS Java SE 21 §11.1.1 — Checked và unchecked exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).

**Ghi nhớ:** NumberFormatException báo không thể chuyển một chuỗi thành số theo cú pháp hoặc miền của API. Chọn parser đúng ý nghĩa, chuẩn hóa có chủ đích, kiểm tra overflow, tính hữu hạn và quy tắc nghiệp vụ, rồi xử lý lỗi sát ranh giới input thay vì để dữ liệu sai lan qua nhiều tầng.
