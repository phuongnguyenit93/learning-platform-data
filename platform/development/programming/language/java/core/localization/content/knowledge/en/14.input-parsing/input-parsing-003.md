# `ParsePosition`: vị trí kết thúc và vị trí lỗi khi phân tích đầu vào trong Java

## 1. Vì sao parse thành công chưa chắc đầu vào hợp lệ?

Trong ứng dụng bản địa hóa, người dùng nhập số, ngày tháng và các chuỗi có dấu phân cách khác nhau tùy `Locale`. Java có những API như `NumberFormat`, `DecimalFormat` và `DateFormat` để đọc dữ liệu ấy. Tuy nhiên, nhiều phương thức phân tích của `java.text` **được phép đọc một tiền tố hợp lệ rồi dừng**, dù phía sau còn ký tự chưa được xử lý.

Ví dụ, với bộ ký hiệu Đức:

```text
Đầu vào: 1.234,56abc
          └──────┘└─┘
          đã đọc  chưa đọc
Giá trị: 1234.56
Vị trí kết thúc: 8 (đếm từ 0)
```

Nếu chương trình chỉ kiểm tra `parse(...)` trả về `Number` khác `null`, nó có thể coi `1.234,56abc` là một số hợp lệ, dù yêu cầu nghiệp vụ là **toàn bộ ô nhập phải là một số**.

`java.text.ParsePosition` cho phép ta biết **vị trí bắt đầu**, **vị trí parser dừng sau khi đọc**, và **vị trí lỗi khi parser không đọc được đầu vào**. Đây là công cụ thiết yếu để phân biệt:

- **Thành công một phần:** đọc được một giá trị, nhưng còn hậu tố chưa tiêu thụ.
- **Thành công toàn bộ:** đọc được một giá trị và vị trí dừng bằng độ dài đầu vào.
- **Không thể phân tích:** không đọc được giá trị tại vị trí yêu cầu; phương thức thường trả `null` và cập nhật error index.
- **Sai quy tắc nghiệp vụ:** parser có thể đọc hết chuỗi nhưng giá trị vẫn không phù hợp với loại dữ liệu, độ chính xác, phạm vi hoặc định dạng mà sản phẩm quy định.

**Nguyên tắc:** `ParsePosition` cung cấp thông tin về tiến độ parser; nó **không tự biến parser thành bộ kiểm tra dữ liệu nghiêm ngặt**. Ứng dụng phải tự đặt tiêu chí chấp nhận phù hợp.

## 2. `ParsePosition` là gì?

Lớp `java.text.ParsePosition` là một đối tượng **mutable** giữ hai số nguyên:

| Thành phần | Phương thức | Ý nghĩa |
| --- | --- | --- |
| Vị trí đang đọc (`index`) | `getIndex()`, `setIndex(int)` | Vị trí bắt đầu khi truyền vào parser; sau khi đọc thành công, thường là vị trí **ngay sau ký tự cuối cùng được tiêu thụ** |
| Vị trí lỗi (`errorIndex`) | `getErrorIndex()`, `setErrorIndex(int)` | Vị trí lỗi mà parser ghi nhận nếu việc phân tích không thành công |
| Khởi tạo | `new ParsePosition(startIndex)` | Chỉ định chỉ số bắt đầu, thường là `0`; error index mặc định là `-1` |

Cách sử dụng điển hình:

```java
ParsePosition position = new ParsePosition(0);
Number value = numberFormat.parse(input, position);

if (value == null) {
    // Không có giá trị đọc được ở vị trí yêu cầu.
} else if (position.getIndex() != input.length()) {
    // Chỉ mới đọc một phần chuỗi.
} else {
    // Đã đọc toàn bộ chuỗi ở mức parser.
}
```

Đây là **đoạn mã minh họa**, sử dụng các biến `numberFormat` và `input` đã có; ví dụ chạy độc lập có đầy đủ import và class ở phần sau.

### Hai vị trí khác nhau

- `getIndex()` trả **vị trí parser đã đi tới**, không phải lúc nào cũng là độ dài chuỗi.
- `getErrorIndex()` trả **vị trí parser báo lỗi**, không phải “số ký tự còn lại” và cũng không phải “vị trí dừng” trong mọi trường hợp.
- `-1` ở `errorIndex` có nghĩa **không ghi nhận vị trí lỗi**. Điều này **không bảo đảm toàn bộ chuỗi hợp lệ**.
- Khi có một kết quả `Number` khác `null` nhưng `index < input.length()`, cần phát hiện **dữ liệu dư** bằng `index` — ngay cả khi `errorIndex == -1`.

Chỉ số của `ParsePosition` là vị trí trong chuỗi Java, tức chỉ số của **đơn vị mã UTF-16** như các phương thức `String.length()` và `substring()`. Không nên nhầm chúng với số byte UTF-8 hoặc số ký tự người dùng nhìn thấy. Với emoji và những ký tự ngoài BMP, một code point có thể chiếm hai đơn vị UTF-16.

## 3. API nào nhận `ParsePosition`?

Các API quan trọng của `java.text` gồm:

```java
NumberFormat.parse(String source, ParsePosition pos)
DateFormat.parse(String source, ParsePosition pos)
Format.parseObject(String source, ParsePosition pos)
```

Các bộ định dạng chuyên biệt như `DecimalFormat` và `SimpleDateFormat` thừa kế/triển khai các khả năng này.

| Cách gọi | Giá trị trả về | Trường hợp lỗi | Phạm vi tiêu thụ đầu vào |
| --- | --- | --- | --- |
| `NumberFormat.parse(text, pos)` | `Number` hoặc `null` | Thường trả `null`, ghi error index | Có thể chỉ đọc tiền tố hợp lệ |
| `DateFormat.parse(text, pos)` | `Date` hoặc `null` | Thường trả `null`, ghi error index | Có thể chỉ đọc tiền tố hợp lệ |
| `Format.parseObject(text, pos)` | `Object` hoặc `null` | Phụ thuộc formatter cụ thể | Có thể chỉ đọc tiền tố hợp lệ |
| `NumberFormat.parse(text)` | `Number` | Có thể ném `ParseException` nếu không parse được từ đầu | **Không tự bảo đảm toàn bộ text được tiêu thụ** |

Sự khác biệt cần nhớ: overload **không có** `ParsePosition` trông tiện lợi nhưng thường không cung cấp vị trí dừng để bạn kiểm tra hậu tố. `ParseException` không phải bằng chứng duy nhất của dữ liệu sai; nếu parser đã đọc được tiền tố hợp lệ, có thể **không ném exception** dù vẫn còn chữ ở cuối.

## 4. Ví dụ đầy đủ: phân tích số kiểu Đức và quan sát ba trạng thái

Tạo tệp **`ParsePositionNumberDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParsePositionNumberDemo {
    private static DecimalFormat createFormatter() {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        formatter.setParseBigDecimal(true);
        return formatter;
    }

    private static void check(String input, DecimalFormat formatter) {
        ParsePosition pos = new ParsePosition(0);
        Number value = formatter.parse(input, pos);
        boolean whole = value != null && pos.getIndex() == input.length();

        System.out.printf(
                "input=%s, value=%s, index=%d, error=%d, whole=%s%n",
                input, value, pos.getIndex(), pos.getErrorIndex(), whole);
    }

    public static void main(String[] args) {
        DecimalFormat formatter = createFormatter();

        check("1.234,56", formatter);
        check("1.234,56abc", formatter);
        check("abc", formatter);
        check("12,3", formatter);
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac -encoding UTF-8 ParsePositionNumberDemo.java
java -cp . ParsePositionNumberDemo
```

Kết quả với bộ ký hiệu Đức trên JDK hỗ trợ locale tương ứng:

```text
input=1.234,56, value=1234.56, index=8, error=-1, whole=true
input=1.234,56abc, value=1234.56, index=8, error=-1, whole=false
input=abc, value=null, index=0, error=0, whole=false
input=12,3, value=12.3, index=4, error=-1, whole=true
```

**Đọc từng dòng:**

1. `1.234,56` có tám đơn vị UTF-16; `DecimalFormat` đọc hết và trả về số `1234.56`.
2. `1.234,56abc` trả **cùng giá trị**, nhưng dừng ở `index=8`, trong khi `input.length()=11`. Đây là **thành công một phần**.
3. `abc` không bắt đầu bằng số phù hợp, nên `value=null`, `index=0` và `errorIndex=0` ở ví dụ.
4. `12,3` được đọc trọn, dù pattern có hai chữ số phần thập phân. **Pattern format hai chữ số không phải quy tắc bắt buộc dữ liệu nhập phải có đúng hai chữ số.** Nếu nghiệp vụ yêu cầu đúng hai chữ số thập phân, cần kiểm tra bổ sung.

Lời gọi `formatter.setParseBigDecimal(true)` giúp nhận `BigDecimal` cho giá trị số thập phân thông thường, thuận lợi để giảm vấn đề sai số nhị phân trong tính toán tiền và các giá trị thập phân. Điều đó không tự bảo đảm đầu vào đã được xác thực theo tất cả ràng buộc nghiệp vụ.

## 5. `index` là vị trí bắt đầu và vị trí kết thúc

Không bắt buộc phân tích từ đầu chuỗi. Khi dữ liệu có **tiền tố được phép** hoặc được nhúng trong một định dạng lớn, có thể bắt đầu từ vị trí khác 0.

Ví dụ chuỗi:

```text
x:1.234,56!
01234567890
  ^       ^
  start=2 end=10
```

Tệp **`ParseFromOffsetDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParseFromOffsetDemo {
    public static void main(String[] args) {
        String source = "x:1.234,56!";
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        formatter.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(2);
        Number number = formatter.parse(source, position);

        System.out.println("number=" + number);
        System.out.println("start=2");
        System.out.println("end=" + position.getIndex());
        System.out.println("error=" + position.getErrorIndex());
        System.out.println("remaining=" +
                source.substring(position.getIndex()));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ParseFromOffsetDemo.java
java -cp . ParseFromOffsetDemo
```

Kết quả:

```text
number=1234.56
start=2
end=10
error=-1
remaining=!
```

Lưu ý: `index=10` là chỉ số **tuyệt đối trong chuỗi nguồn**, không phải “số ký tự đã đọc” tính từ vị trí 2. Số đơn vị UTF-16 đã đọc là `end - start = 8`. Với parser một giá trị toàn chuỗi, điều kiện là `pos.getIndex() == source.length()` khi bắt đầu tại 0. Với parser một đoạn con, điều kiện kết thúc cần so với **ranh giới của đoạn được phép**, không nhất thiết là hết toàn bộ chuỗi nguồn.

Trường hợp start index nằm ngoài phần có thể đọc hoặc ký tự tại start không phù hợp, hãy kiểm tra kết quả và error index; đừng giả định parser tự bỏ qua mọi tiền tố hoặc mọi khoảng trắng.

## 6. `getErrorIndex()`: vị trí lỗi không giống vị trí kết thúc

Khi parse thất bại, error index cho biết nơi parser ghi nhận lỗi (theo cách triển khai của formatter). Ví dụ:

```text
input = "abc"
NumberFormat tại index 0
→ value = null
→ index = 0
→ errorIndex = 0
```

Nhưng trong `input="1.234,56abc"`, Java đã đọc được một giá trị số và dừng ở chữ `a`. **Đây không được tự coi là lỗi của formatter**; nó có thể trả `errorIndex=-1` vì nhận được một tiền tố số hợp lệ. **Chỉ ứng dụng mới biết hậu tố `abc` có bị cấm hay không.**

Nếu muốn báo lỗi giao diện với nội dung “Có ký tự không hợp lệ tại vị trí X”, một quy tắc thực tiễn:

```java
if (value == null) {
    int errorAt = pos.getErrorIndex();
    // báo lỗi parse tại errorAt nếu giá trị này >= 0
} else if (pos.getIndex() < input.length()) {
    int unexpectedAt = pos.getIndex();
    // báo dữ liệu dư tại unexpectedAt
}
```

Đoạn trên minh họa với các biến `value`, `pos` và `input` đã khai báo trước; không phải chương trình độc lập.

Một số parser báo vị trí lỗi ở nơi **chúng phát hiện ra** lỗi, có thể là cuối chuỗi hoặc sau vài ký tự đã khớp, không nhất thiết là vị trí ký tự “sai” theo cảm nhận của người dùng. Vì thế hãy xem `errorIndex` là **thông tin chẩn đoán do parser cung cấp**, không phải một bảo đảm UI có thể tô sáng ngay một grapheme.

## 7. Viết hàm nhận số chỉ khi đọc hết chuỗi

Nếu trường nhập liệu yêu cầu **một số duy nhất**, ta nên kiểm tra cả kết quả trả về và số ký tự đã tiêu thụ. Ví dụ độc lập sau trả về `Optional<BigDecimal>`.

Tạo **`StrictNumberInputDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Optional;

public class StrictNumberInputDemo {
    private static Optional<BigDecimal> parseWholeGermanNumber(
            String input) {
        if (input == null || input.isEmpty()) {
            return Optional.empty();
        }

        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        formatter.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = formatter.parse(input, position);

        if (!(parsed instanceof BigDecimal amount)
                || position.getIndex() != input.length()) {
            return Optional.empty();
        }

        return Optional.of(amount);
    }

    public static void main(String[] args) {
        for (String input : new String[] {
                "1.234,56", "1.234,56xyz", "abc", "12,3"
        }) {
            System.out.println(input + " -> " +
                    parseWholeGermanNumber(input)
                            .map(BigDecimal::toPlainString)
                            .orElse("INVALID"));
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 StrictNumberInputDemo.java
java -cp . StrictNumberInputDemo
```

Đầu ra:

```text
1.234,56 -> 1234.56
1.234,56xyz -> INVALID
abc -> INVALID
12,3 -> 12.3
```

Hàm này chấp nhận `12,3` vì parser đã đọc hết chuỗi. Nếu biểu mẫu bắt buộc **hai chữ số phần thập phân**, không cho dấu nhóm tùy ý, chỉ chấp nhận giá trị dương, hoặc giới hạn số chữ số, hãy **thêm validation** phù hợp. `ParsePosition` chỉ giải quyết việc parser đã **đọc được bao nhiêu**, không quy định đầy đủ chuẩn dữ liệu của ứng dụng.

### Khoảng trắng có được phép không?

Cần xác định chính sách ngay từ thiết kế:

- Nếu muốn chấp nhận khoảng trắng hai đầu, có thể chuẩn hóa đầu vào **trước** khi parse. Nhưng sau đó vị trí lỗi sẽ tính trên chuỗi **đã chuẩn hóa**, không còn tương ứng trực tiếp với chỉ số của chuỗi gốc.
- Nếu muốn chỉ chấp nhận đúng một định dạng và không có khoảng trắng đầu/cuối, không tự `trim()` hoặc `strip()` trước khi kiểm tra.
- Trong nhiều locale, dấu phân cách nhóm có thể là **khoảng trắng đặc biệt** (ví dụ no-break space hoặc narrow no-break space), không giống ký tự space ASCII. Tránh tự thay thế mọi khoảng trắng bằng khoảng trắng thường khi chưa hiểu dữ liệu và yêu cầu.

## 8. Ngày tháng: `DateFormat` cũng có thể đọc một phần

`java.text.DateFormat` và `SimpleDateFormat` cũng nhận `ParsePosition`. Có thêm một vấn đề: ngày `31.02.2025` là **ngày không tồn tại** dù hình thức trông giống mẫu `dd.MM.yyyy`. Với `SimpleDateFormat`, đặt `setLenient(false)` để tránh tự điều chỉnh ngày không hợp lệ.

Tạo **`DateParsePositionDemo.java`**:

```java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class DateParsePositionDemo {
    private static void check(SimpleDateFormat formatter, String input) {
        ParsePosition position = new ParsePosition(0);
        Date value = formatter.parse(input, position);
        boolean whole = value != null &&
                position.getIndex() == input.length();

        System.out.printf(
                "input=%s, parsed=%s, index=%d, error=%d, whole=%s%n",
                input, value != null, position.getIndex(),
                position.getErrorIndex(), whole);
    }

    public static void main(String[] args) {
        SimpleDateFormat formatter =
                new SimpleDateFormat("dd.MM.yyyy", Locale.GERMANY);
        formatter.setLenient(false);
        formatter.setTimeZone(TimeZone.getTimeZone("UTC"));

        check(formatter, "28.02.2025");
        check(formatter, "28.02.2025tail");
        check(formatter, "31.02.2025");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DateParsePositionDemo.java
java -cp . DateParsePositionDemo
```

Kết quả với pattern và dữ liệu trong ví dụ:

```text
input=28.02.2025, parsed=true, index=10, error=-1, whole=true
input=28.02.2025tail, parsed=true, index=10, error=-1, whole=false
input=31.02.2025, parsed=false, index=0, error=10, whole=false
```

Nhìn vào `28.02.2025tail`: `setLenient(false)` kiểm soát tính hợp lệ của **giá trị ngày**, nhưng **không có nghĩa** parser bắt buộc tiêu thụ hết chuỗi. Để kiểm tra toàn bộ đầu vào, vẫn phải so `position.getIndex()` với `input.length()`.

`31.02.2025` bị từ chối do ngày không tồn tại; trong ví dụ này, `errorIndex=10` đánh dấu nơi parser ghi nhận lỗi khi đã phân tích hình thức ngày. Đừng dùng con số 10 như một quy tắc phổ quát cho mọi lỗi ngày tháng hoặc mọi JDK.

Đặt timezone UTC ở ví dụ để tránh phụ thuộc môi trường khi chuyển ngày thành `Date`, dù chương trình chỉ in trạng thái thành công/thất bại. Đối với dự án mới, nên cân nhắc API `java.time` như `LocalDate` và `DateTimeFormatter` khi làm việc với ngày lịch.

## 9. Khác biệt giữa API `java.text` và `java.time`

Trong Java 8+, `DateTimeFormatter` thuộc `java.time.format` cũng có overload:

```java
TemporalAccessor parse(CharSequence text, ParsePosition position)
```

Nhưng **không nên mặc định** cách báo lỗi của `DateTimeFormatter` giống `NumberFormat.parse(text, position)`. `java.time` có bước phân tích thành các trường thời gian và bước **resolve** các trường thành ngày/giờ hợp lệ; lỗi tại bước resolve có thể ném `DateTimeParseException` ngay cả khi `ParsePosition` đã tiến tới cuối chuỗi.

Ví dụ:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

ParsePosition position = new ParsePosition(0);
TemporalAccessor parsed =
        formatter.parse("2025-02-28tail", position);
LocalDate date = LocalDate.from(parsed);
```

Đây là **trích đoạn** cần các import `java.text.ParsePosition`, `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle`, `java.time.temporal.TemporalAccessor`. Nó minh họa cơ chế đọc một phần và cách chuyển `TemporalAccessor` thành `LocalDate`.

Nếu đầu vào là `2025-02-31`, resolver `STRICT` không tạo được một ngày hợp lệ và có thể ném `DateTimeParseException`. Vì vậy:

- Với `java.text.NumberFormat` hoặc `DateFormat`, phải kiểm tra `null`, `index` và `errorIndex` theo hợp đồng của từng API.
- Với `java.time.DateTimeFormatter`, cần xử lý **ngoại lệ** khi parse/resolve, và hiểu `ParsePosition` là thông tin vị trí trong thao tác phân tích.
- Với một chuỗi đầu vào được yêu cầu phải là **một ngày hoàn chỉnh**, `LocalDate.parse(text, formatter)` thường đơn giản và trực tiếp hơn overload có `ParsePosition`; nó yêu cầu một kết quả phù hợp trong phạm vi phương thức parse toàn chuỗi và báo lỗi bằng exception.

**Không trộn `DateTimeFormatter` với `SimpleDateFormat` như thể hai lớp có cùng quy tắc pattern và xử lý lỗi.** Chúng thuộc hai hệ API khác nhau, đặc biệt về resolver và đối tượng ngày/giờ.

## 10. Những bẫy tinh vi khi dùng `ParsePosition`

### 10.1. Tái sử dụng `ParsePosition` mà không reset

`ParsePosition` có trạng thái. Nếu sau một phép parse, `index` đang là 8 và bạn đưa lại cùng đối tượng cho chuỗi khác, parser sẽ **bắt đầu từ vị trí 8**, không phải tự quay về 0.

Tương tự, `errorIndex` có thể là thông tin cũ nếu bạn tái sử dụng đối tượng và formatter không đặt lại nó theo cách bạn kỳ vọng. Một phép parse thành công không có hợp đồng chung rằng mọi phương thức sẽ tự reset `errorIndex` về `-1`.

Cách an toàn nhất cho các trường nhập độc lập:

```java
ParsePosition pos = new ParsePosition(0);
Number value = formatter.parse(input, pos);
```

Tạo **đối tượng mới cho mỗi lần kiểm tra**. Nếu thực sự phải dùng lại, đặt cả `setIndex(start)` và `setErrorIndex(-1)`, và hiểu rõ parser sử dụng đối tượng như thế nào.

### 10.2. Nhầm `errorIndex == -1` với đã parse toàn bộ

Đầu vào `1.234,56abc` đã cho ví dụ rõ: `value != null`, `errorIndex == -1`, nhưng `index == 8` trong chuỗi dài 11. Nếu nghiệp vụ yêu cầu cả chuỗi phải là số, đó là lỗi **dữ liệu dư** mà Java không nhất thiết coi là lỗi cú pháp ở phần đã đọc.

### 10.3. Chỉ kiểm tra `index > 0`

Nếu bắt đầu ở vị trí 5, `index > 0` không nói được parser đã đọc thêm ký tự nào. Hãy kiểm tra `value != null` và chỉ số đầu/cuối theo đúng phạm vi mong muốn.

### 10.4. Không tính tới Unicode

`ParsePosition` đếm chỉ số theo UTF-16. Ví dụ chuỗi chứa emoji ở đầu có thể có `String.length()` lớn hơn số code point. Khi hiển thị vị trí lỗi cho người dùng, nhất là nếu bôi chọn trong UI, cần ánh xạ chỉ số theo hệ biểu diễn của giao diện và không cắt giữa surrogate pair.

### 10.5. Tin rằng pattern của `DecimalFormat` xác thực hình thức nhập

Pattern `#,##0.00` phục vụ chủ yếu cho định dạng; việc parser chấp nhận `12,3` chứng minh nó không tự bắt buộc hai chữ số thập phân. Quy tắc grouping cũng có thể linh hoạt tùy formatter. Đừng lấy thành công của parser làm chứng nhận input đáp ứng mọi yêu cầu về dấu nhóm, số chữ số, số âm, giới hạn giá trị hay chuẩn dữ liệu kế toán.

### 10.6. Coi parse locale như parse dữ liệu giao thức

Dữ liệu máy-máy (API JSON, ID, mã ISO, file trao đổi) thường có **định dạng chuẩn riêng** không phụ thuộc ngôn ngữ UI. Không dùng `Locale.getDefault()` một cách ngầm định để đọc các trường máy-máy. Phân biệt:

- **Input người dùng:** có thể cần `NumberFormat` / `DateFormat` / `DateTimeFormatter` theo locale và chính sách sản phẩm.
- **Input giao thức:** dùng parser theo chuẩn giao thức, không cho dấu nhóm và dấu decimal đổi theo tùy chọn UI.
- **Input dữ liệu nghiệp vụ quan trọng:** ngoài đúng cú pháp, cần kiểm tra miền giá trị, precision, rounding, currency/timezone, đơn vị và an toàn.

### 10.7. Chia sẻ formatter mutable giữa các luồng

`DecimalFormat` và `SimpleDateFormat` là các đối tượng mutable, không mặc định an toàn để dùng chung giữa các thread. `ParsePosition` cũng mutable; không chia sẻ một instance cho các tác vụ parse đồng thời. Dùng instance riêng hoặc quản lý đồng bộ thích hợp. Với `java.time.DateTimeFormatter`, đối tượng formatter bất biến và có thể chia sẻ an toàn hơn theo thiết kế API.

## 11. Cách thiết kế validator đầu vào có vị trí lỗi

Một validator thực tế nên phân biệt ít nhất ba loại kết quả:

| Trạng thái | Ví dụ | Thông tin cần hiển thị |
| --- | --- | --- |
| `VALID` | `1.234,56` | Giá trị đã parse; chính sách miền giá trị tiếp tục áp dụng |
| `PARSE_ERROR` | `abc` | Vị trí lỗi từ `getErrorIndex()` nếu có |
| `TRAILING_INPUT` | `1.234,56abc` | Vị trí bắt đầu phần dư từ `getIndex()` |

Nếu dùng form nhận một giá trị số, logic trung tâm có thể là:

```text
parse(input, new ParsePosition(0))
         |
         +-- value == null --------> PARSE_ERROR
         |                           vị trí = errorIndex (nếu có)
         |
         +-- index != input.length()
         |                       ---> TRAILING_INPUT
         |                           vị trí = index
         |
         +-- giá trị đọc được hết --> Kiểm tra nghiệp vụ
                                     (min/max, scale, sign, ...)
                                     rồi mới VALID
```

Đừng hiển thị tràn lan lỗi parser thô cho người dùng cuối; lỗi UI cần hướng dẫn đúng locale, ví dụ “Nhập số với dấu phẩy thập phân” khi ngôn ngữ/vùng sử dụng dấu phẩy. Với `errorIndex < 0` trong một phép parse thất bại, hãy dùng một thông báo tổng quát hoặc đánh dấu toàn trường; không tạo vị trí lỗi giả.

Để đánh dấu một đoạn con, luôn kiểm tra giới hạn `0 <= position <= input.length()` trước khi dùng `substring`, đặc biệt khi giá trị chỉ số xuất phát từ các parser khác nhau hoặc bị thay đổi trong code.

## 12. Kiểm thử tối thiểu nên có

Để bảo đảm validator vừa đúng locale vừa không bỏ lọt hậu tố:

1. **Chuỗi hợp lệ hoàn toàn:** với số Đức `1.234,56`, kỳ vọng `value != null`, `index == length`.
2. **Chuỗi có hậu tố:** `1.234,56abc` có thể parse ra số nhưng phải bị từ chối nếu trường yêu cầu số nguyên vẹn.
3. **Lỗi ngay đầu:** `abc` → `null`, có error index theo parser.
4. **Vị trí bắt đầu khác 0:** kiểm tra `index` cuối là chỉ số tuyệt đối.
5. **Chuỗi rỗng/null:** chính sách nhập bắt buộc/không bắt buộc phải rõ; đừng truyền `null` cho parser nếu API không chấp nhận.
6. **Khoảng trắng và dấu Unicode:** kiểm tra dấu grouping thực dùng và chính sách khoảng trắng.
7. **Ngày hợp lệ nhưng có hậu tố:** `28.02.2025tail` phải bị từ chối trong validator toàn chuỗi.
8. **Ngày không tồn tại:** `31.02.2025` phải bị từ chối nếu dùng parsing nghiêm ngặt.
9. **Phân biệt thành công parser và hợp đồng nghiệp vụ:** `12,3` có thể parse hết nhưng vẫn không phù hợp trường yêu cầu đúng hai số lẻ.
10. **Dữ liệu cực lớn hoặc chính xác cao:** kiểm tra kiểu Number trả về, `BigDecimal`, scale và giới hạn nghiệp vụ.
11. **Tái sử dụng đối tượng:** xác nhận không dùng `index` hoặc `errorIndex` còn sót từ lần trước.
12. **Đa locale và đa runtime:** đối chiếu US, Đức, Việt Nam và các locale triển khai thực tế; dữ liệu locale trong JDK/CLDR có thể thay đổi giữa các phiên bản.

## 13. Phân biệt `ParsePosition`, `FieldPosition` và `ParseException`

Ba tên dễ gây nhầm:

- **`ParsePosition`**: dùng trong **parse** để mang vị trí bắt đầu, vị trí kết thúc và vị trí lỗi; không tự ném ngoại lệ chỉ vì tồn tại ký tự dư.
- **`FieldPosition`**: thường dùng trong **format** để xác định vị trí một trường trong chuỗi đầu ra, chẳng hạn phần nguyên; không thay thế `ParsePosition`.
- **`ParseException`**: một số overload parse báo lỗi bằng exception, có `getErrorOffset()`, nhưng bạn vẫn cần hiểu liệu API đó có buộc tiêu thụ hết input hay không.

Không nên chọn một trong ba chỉ vì chúng đều có chữ “Position” hoặc “Parse”. Nếu ứng dụng cần báo **vị trí phần dư của số** và giữ quyền quyết định chấp nhận toàn chuỗi, `ParsePosition` là công cụ trực tiếp.

## 14. Ghi nhớ

- **`ParsePosition.getIndex()`** là vị trí ngay sau phần đầu vào parser đã tiêu thụ thành công, không nhất thiết là hết chuỗi.
- **`getErrorIndex()`** biểu thị vị trí lỗi do parser ghi nhận; `-1` **không có nghĩa** không còn dữ liệu dư.
- Với yêu cầu **chỉ chấp nhận một giá trị chiếm toàn bộ input**, phải kiểm tra **giá trị trả về khác `null` và `getIndex() == input.length()`**; sau đó vẫn áp dụng validation nghiệp vụ.
- Khi parse từ một offset, `index` là vị trí **tuyệt đối trong chuỗi nguồn**; chỉ số Java tính theo **UTF-16**, không phải byte.
- **Dùng `ParsePosition` mới** cho mỗi phép phân tích độc lập để tránh trạng thái `index`/`errorIndex` cũ.
- Với ngày tháng, còn phải kiểm soát **tính hợp lệ lịch** (`setLenient(false)` hoặc resolver nghiêm ngặt), không chỉ vị trí kết thúc.
- Trên `java.time`, các bước resolve có thể ném `DateTimeParseException`; đừng giả định mọi API parse có cùng hợp đồng lỗi như `java.text.NumberFormat`.
