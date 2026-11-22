# Kiểm tra toàn chuỗi và xử lý dữ liệu không hợp lệ khi chuyển đổi String trong Java

## 1. Vì sao kiểm tra toàn chuỗi quan trọng?

Một giá trị nhận từ bàn phím, biểu mẫu, file, cấu hình hoặc API ban đầu thường là `String`. Trước khi chuyển thành `int`, `long`, `BigDecimal`, `boolean` hay `LocalDate`, chương trình cần xác định **toàn bộ chuỗi** có thuộc định dạng hợp lệ được yêu cầu hay không. Không nên chỉ tìm thấy **một đoạn con trông có vẻ hợp lệ** rồi coi cả dữ liệu đầu vào là đúng.

Ví dụ, chuỗi `"order=42x"` có chứa `42`, nhưng không phải một số nguyên thập phân thuần túy. Nếu trường nhập liệu yêu cầu số lượng, giá trị như `"42kg"`, `"12 3"`, `"7;DELETE"` hoặc `"19.95 USD"` phải được đánh giá theo **quy ước của cả trường**, không tự ý tách phần số rồi bỏ qua phần còn lại.

Kiểm tra đầy đủ gồm hai tầng:

1. **Định dạng và chính sách nhập liệu:** Có cho phép khoảng trắng đầu/cuối, dấu `+`/`-`, số 0 đứng đầu, dấu phẩy thập phân, số mũ, Unicode digit hoặc chuỗi rỗng hay không?
2. **Khả năng chuyển đổi thực sự:** Giá trị có nằm trong phạm vi kiểu đích, hợp lệ về lịch hoặc thỏa các ràng buộc nghiệp vụ không?

Regex có thể xác nhận cú pháp, nhưng **không thay thế hoàn toàn bước parse và kiểm tra phạm vi**. Ngược lại, một số API parse có quy ước rộng hơn chính sách của ứng dụng; vì vậy thành công ở bước parse cũng chưa luôn đồng nghĩa dữ liệu đáp ứng yêu cầu.

## 2. `matches()` kiểm tra toàn chuỗi, `find()` chỉ tìm một đoạn

Trong `java.util.regex`:

- `pattern.matcher(input).matches()` chỉ trả `true` nếu **toàn bộ vùng đầu vào của Matcher** phù hợp với regex.
- `pattern.matcher(input).find()` chỉ cần tìm được **một đoạn con** khớp regex, không nhất thiết bao phủ toàn chuỗi.
- `input.matches(regex)` có hành vi kiểm tra toàn bộ chuỗi tương đương khi áp dụng regex đó qua `Pattern`; với mẫu sử dụng nhiều lần nên biên dịch `Pattern` một lần.

Ví dụ:

```java
import java.util.regex.Pattern;

Pattern digits = Pattern.compile("[0-9]+");
System.out.println(digits.matcher("42").matches());      // true
System.out.println(digits.matcher("id=42x").matches());   // false
System.out.println(digits.matcher("id=42x").find());      // true
```

Đây là đoạn minh họa trong một phương thức hoặc môi trường JShell, không phải một chương trình độc lập. Regex `[0-9]+` ở đây chỉ chấp nhận chữ số ASCII `0`–`9`. Việc `find()` trả `true` với `"id=42x"` **không xác nhận đầu vào là một số**.

Với `Matcher.matches()`, không cần thêm `^...$` để ép kiểm tra toàn chuỗi. Ngoài ra, `^` và `$` còn có những quy tắc về ranh giới dòng và cờ regex; dùng `matches()` sẽ thể hiện trực tiếp ý định “toàn chuỗi”. Nếu đã thay đổi `Matcher.region(...)`, `matches()` kiểm tra toàn **region đang chọn**, không nhất thiết là toàn chuỗi gốc; các ví dụ ở đây luôn dùng `Matcher` mới trên toàn input.

## 3. Một quy trình chuyển đổi dữ liệu đáng tin cậy

Quy trình khuyến nghị cho đầu vào `String` là:

1. **Phân biệt thiếu dữ liệu:** Xác định `null` có nghĩa “không gửi”, `""` có nghĩa “trống”, hay cả hai đều không hợp lệ. Không gọi `strip()` trực tiếp khi `input == null`.
2. **Chuẩn hóa có kiểm soát:** Chỉ loại khoảng trắng ở hai đầu nếu hợp đồng dữ liệu cho phép. Java 11+ có `strip()` theo `Character.isWhitespace`; `trim()` có cơ chế cũ khác, và không phải mọi ký tự khoảng trắng Unicode đều bị `strip()` loại. Không âm thầm loại ký tự ở giữa nếu chưa được cho phép.
3. **Xác nhận toàn chuỗi đúng cú pháp:** Ví dụ số nguyên `[+-]?[0-9]+`, ngày ISO `[0-9]{4}-[0-9]{2}-[0-9]{2}`, hoặc tập giá trị `true`/`false`.
4. **Parse đúng kiểu:** Dùng `Integer.parseInt`, `Long.parseLong`, `new BigDecimal`, `LocalDate.parse`... và bắt đúng ngoại lệ có thể xảy ra. Regex không kiểm tra được tràn `int` hoặc ngày 29/02 của năm không nhuận.
5. **Kiểm tra nghiệp vụ:** Ví dụ tuổi nằm trong phạm vi hợp lệ, số tiền không âm, ngày bắt đầu không sau ngày kết thúc. Cú pháp đúng không đồng nghĩa dữ liệu phù hợp về nghiệp vụ.
6. **Trả kết quả có trạng thái rõ ràng:** Không biến mọi dữ liệu lỗi thành giá trị `0`, `false` hoặc ngày hiện tại. Với ví dụ đơn giản có thể dùng `Optional<T>`; ứng dụng cần thông báo riêng nên dùng result type hoặc mã lỗi phân biệt thiếu/định dạng/phạm vi.

**Thứ tự quan trọng:** Khi các bước chuẩn hóa hoặc parse có thể thay đổi dữ liệu, cần ghi rõ hợp đồng. Ví dụ với mã định danh `"00123"`, chuyển sang `int` sẽ mất hai số 0 đầu; nếu các số 0 là một phần của định danh thì nên giữ dạng `String`, không ép kiểu số chỉ vì nó chỉ chứa chữ số.

## 4. Ví dụ Java 17+ hoàn chỉnh: số, boolean và ngày

Lưu file `StrictConversionDemo.java`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Optional;
import java.util.regex.Pattern;

public class StrictConversionDemo {
    // Chính sách: chữ số ASCII, có thể có dấu +/-.
    private static final Pattern INTEGER =
            Pattern.compile("[+-]?[0-9]+");

    // Chính sách: số thập phân dùng dấu chấm, không cho 00.5 hay số mũ.
    private static final Pattern DECIMAL =
            Pattern.compile("[+-]?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?");

    // Yêu cầu ngày ISO đúng 10 ký tự, rồi mới kiểm tra ngày có thật.
    private static final Pattern DATE =
            Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}");

    static Optional<Integer> integer(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if (!INTEGER.matcher(value).matches()) return Optional.empty();

        try {
            return Optional.of(Integer.parseInt(value));
        } catch (NumberFormatException ex) {
            // Ví dụ số vượt phạm vi int, dù cú pháp toàn chuỗi hợp lệ.
            return Optional.empty();
        }
    }

    static Optional<BigDecimal> decimal(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if (!DECIMAL.matcher(value).matches()) return Optional.empty();

        try {
            return Optional.of(new BigDecimal(value));
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    static Optional<Boolean> booleanValue(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if ("true".equalsIgnoreCase(value)) return Optional.of(true);
        if ("false".equalsIgnoreCase(value)) return Optional.of(false);
        return Optional.empty();
    }

    static Optional<LocalDate> date(String input) {
        if (input == null) return Optional.empty();
        String value = input.strip();
        if (!DATE.matcher(value).matches()) return Optional.empty();

        try {
            return Optional.of(
                    LocalDate.parse(value, DateTimeFormatter.ISO_LOCAL_DATE));
        } catch (DateTimeParseException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        System.out.println("Integer 42: "
                + integer(" 42 ").map(Object::toString).orElse("INVALID"));
        System.out.println("Integer 12x: "
                + integer("12x").map(Object::toString).orElse("INVALID"));
        System.out.println("Integer overflow: "
                + integer("2147483648").map(Object::toString).orElse("INVALID"));
        System.out.println("Integer empty: "
                + integer("   ").map(Object::toString).orElse("INVALID"));

        System.out.println("Decimal 19.95: "
                + decimal("19.95").map(Object::toString).orElse("INVALID"));
        System.out.println("Decimal suffix: "
                + decimal("19.95 USD").map(Object::toString).orElse("INVALID"));
        System.out.println("Decimal leading zero: "
                + decimal("00.5").map(Object::toString).orElse("INVALID"));

        System.out.println("Boolean TRUE: "
                + booleanValue("TRUE").map(Object::toString).orElse("INVALID"));
        System.out.println("Boolean yes: "
                + booleanValue("yes").map(Object::toString).orElse("INVALID"));

        System.out.println("Date leap: "
                + date("2024-02-29").map(Object::toString).orElse("INVALID"));
        System.out.println("Date invalid: "
                + date("2023-02-29").map(Object::toString).orElse("INVALID"));

        Pattern digits = Pattern.compile("[0-9]+");
        System.out.println("Partial find: "
                + digits.matcher("id=42x").find());
        System.out.println("Whole matches: "
                + digits.matcher("id=42x").matches());
    }
}
```

Biên dịch và chạy:

```bash
javac StrictConversionDemo.java
java StrictConversionDemo
```

Đầu ra:

```text
Integer 42: 42
Integer 12x: INVALID
Integer overflow: INVALID
Integer empty: INVALID
Decimal 19.95: 19.95
Decimal suffix: INVALID
Decimal leading zero: INVALID
Boolean TRUE: true
Boolean yes: INVALID
Date leap: 2024-02-29
Date invalid: INVALID
Partial find: true
Whole matches: false
```

Các kết quả minh họa hai lớp kiểm tra. `"2147483648"` vượt `Integer.MAX_VALUE` (2.147.483.647) dù phù hợp regex số nguyên. `"2023-02-29"` có hình thức `yyyy-MM-dd` nhưng ngày đó không tồn tại; `LocalDate.parse` với `ISO_LOCAL_DATE` kiểm tra tính hợp lệ của lịch. `"00.5"` có thể được một số bộ parse nhận, nhưng chính sách `DECIMAL` của **bài này** chủ động từ chối số 0 thừa ở đầu.

Các hàm trả `Optional.empty()` khi không parse được để dễ minh họa; chúng **không phân biệt lý do lỗi**. Với giao diện người dùng hoặc API thực tế, nên trả một kết quả có loại lỗi như `REQUIRED`, `BAD_FORMAT`, `OUT_OF_RANGE`, `INVALID_DATE` để hiển thị thông báo phù hợp.

## 5. Một số API có hành vi dễ gây nhầm

### Số nguyên: parse kiểm tra toàn giá trị và phạm vi

`Integer.parseInt("123")` trả `123`. `Integer.parseInt("12abc")` ném `NumberFormatException`; `Integer.parseInt("2147483648")` cũng ném ngoại lệ vì tràn phạm vi. `Long.parseLong` có nguyên tắc tương tự nhưng phạm vi `long` khác.

Không phải lúc nào cần regex trước parse: nếu chỉ cần đúng **cú pháp mà API parse hỗ trợ** và chấp nhận báo lỗi bằng ngoại lệ, có thể trực tiếp gọi parse trong `try/catch`. Thêm bước kiểm tra toàn chuỗi hữu ích khi **chính sách đầu vào chặt hơn** hành vi mặc định của parser hoặc khi cần thông báo lỗi chi tiết. Ví dụ, parser số nguyên Java có thể nhận một số chữ số Unicode mà `[0-9]` ASCII chủ động từ chối.

### Boolean: `parseBoolean` không phân biệt sai định dạng với `false`

`Boolean.parseBoolean("true")` trả `true`; `Boolean.parseBoolean("FALSE")`, `Boolean.parseBoolean("yes")` và `Boolean.parseBoolean(null)` đều trả `false`. Đây là API thuận tiện khi muốn coi mọi thứ khác `true` là `false`, nhưng **không phù hợp nếu `"yes"` phải bị báo dữ liệu không hợp lệ**. Khi cần đúng hai giá trị `true`/`false`, hãy kiểm tra rõ từng giá trị như phương thức `booleanValue`.

### Số thực: `Double.parseDouble` có thể chấp nhận dạng đặc biệt

`Double.parseDouble` hỗ trợ ký pháp số mũ và một số giá trị đặc biệt như `NaN` hoặc `Infinity`. Vì vậy, **parse thành công không có nghĩa đây là số hữu hạn theo chính sách của ứng dụng**. Nếu dùng `double` và yêu cầu giá trị hữu hạn, kiểm tra thêm `Double.isFinite(value)`. Với số tiền cần độ chính xác thập phân, `BigDecimal` thường thích hợp hơn `double`; nhưng chính sách định dạng, phạm vi, dấu thập phân và số chữ số sau dấu chấm vẫn cần được xác định riêng.

### Ngày: đúng định dạng chưa đủ để có ngày hợp lệ

Regex `[0-9]{4}-[0-9]{2}-[0-9]{2}` chấp nhận hình thức `"2023-02-29"`, nhưng điều này không đảm bảo ngày tồn tại. Dùng `java.time.LocalDate` và formatter có chế độ kiểm tra nghiêm ngặt, chẳng hạn `DateTimeFormatter.ISO_LOCAL_DATE`. Với mẫu tùy chỉnh, cần hiểu các ký hiệu như `uuuu` so với `yyyy` và `ResolverStyle.STRICT`: một định dạng tùy chỉnh có thể có hành vi resolve khác với kỳ vọng nếu chỉ ghép mẫu mà không kiểm tra kiểu lịch. Ngày được parse đúng vẫn có thể vi phạm ràng buộc nghiệp vụ, ví dụ ngày sinh nằm trong tương lai.

## 6. Dữ liệu có dấu phân cách và locale

Một số dữ liệu cần quy tắc theo **locale**, ví dụ `1.234,56` tại nhiều vùng dùng dấu phẩy làm dấu thập phân, nhưng `1,234.56` tại một số vùng khác. `new BigDecimal(String)` nhận biểu diễn số chuẩn theo cú pháp của nó; nó không tự suy đoán locale hoặc tự loại đơn vị `"USD"`.

Nếu ứng dụng thật sự cho phép cách viết số theo locale, có thể dùng `NumberFormat`/`DecimalFormat` với `Locale` chỉ định và `ParsePosition` để xác nhận parser đã tiêu thụ **đến hết đầu vào**. Ví dụ về nguyên tắc:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

NumberFormat format = NumberFormat.getNumberInstance(Locale.GERMANY);
String input = "1.234,56";
ParsePosition position = new ParsePosition(0);
Number number = format.parse(input, position);

boolean fullyConsumed =
        number != null && position.getIndex() == input.length();
```

Đoạn mã trên là **minh họa trong một khối lệnh**, không phải chương trình chạy độc lập. `fullyConsumed` kiểm tra parser có bỏ sót hậu tố hay không; **nó chưa tự bảo đảm chính sách định dạng chặt chẽ**, vì `NumberFormat` có thể linh hoạt về nhóm chữ số, dấu và một số chi tiết khác. Tùy ứng dụng, phải cấu hình parser phù hợp hoặc kết hợp kiểm tra cú pháp được chỉ định và chuyển đổi giá trị. Không tự xóa tất cả dấu `.`, `,` khi chưa biết chắc dấu nào là dấu nhóm và dấu nào là dấu thập phân.

Nếu định dạng là mã định danh hoặc mã bưu chính, đừng chuyển sang số rồi serialize lại vì có thể làm mất số 0 đứng đầu hoặc thay cách biểu diễn. Lưu dạng `String` và kiểm tra toàn chuỗi theo hợp đồng là lựa chọn đúng hơn.

## 7. Xử lý lỗi: báo đúng lý do, giữ đúng dữ liệu

Ứng dụng thực tế có thể phân biệt:

| Trường hợp | Dữ liệu ví dụ | Kết quả xử lý phù hợp |
| --- | --- | --- |
| Không được gửi | `null` | Lỗi `REQUIRED` nếu trường bắt buộc; nếu tùy chọn thì trạng thái “không có giá trị”. |
| Chỉ có khoảng trắng | `"   "` | Lỗi rỗng sau chuẩn hóa nếu chính sách cho phép `strip()`. |
| Sai cú pháp | `"12x"` | Báo đúng định dạng được hỗ trợ, không cắt lấy `12`. |
| Tràn miền kiểu | `"2147483648"` cho `int` | Báo ngoài phạm vi, không ép thành `int` bằng phép cắt hoặc chuyển kiểu không kiểm soát. |
| Sai ràng buộc nghiệp vụ | `"-5"` khi số lượng phải dương | Parse có thể thành công nhưng validation nghiệp vụ phải từ chối. |
| Ngày không tồn tại | `"2023-02-29"` | Báo ngày không hợp lệ; không tự sửa thành ngày khác trừ khi hợp đồng cho phép. |
| Không thuộc tập boolean | `"yes"` khi chỉ nhận `true/false` | Báo sai lựa chọn, không coi `yes` là `false`. |
| Có phần dư | `"19.95 USD"` khi trường yêu cầu số tiền thuần túy | Từ chối hoặc chuyển sang parser đơn vị có quy tắc rõ ràng. |

**Không xử lý bằng giá trị mặc định âm thầm:** Nếu `Integer.parseInt` thất bại, việc trả `0` mà không có trạng thái lỗi có thể khiến ứng dụng nhầm dữ liệu hỏng với giá trị 0 hợp lệ. Tránh đặt `catch (Exception ex)` rộng quanh cả chuỗi xử lý; bắt ngoại lệ dự kiến như `NumberFormatException` hoặc `DateTimeParseException`, rồi chuyển sang lỗi đầu vào thích hợp ở ranh giới hệ thống.

**Không ghi đè dữ liệu chưa hợp lệ:** Khi hiển thị lỗi cho người dùng, nên giữ lại input ban đầu để họ hiểu và sửa, đồng thời có thể lưu bản đã chuẩn hóa riêng khi chuyển đổi thành công. Khi ghi log, tránh đưa toàn bộ dữ liệu nhạy cảm hoặc giá trị không đáng tin trực tiếp vào log mà không cân nhắc.

**Không dựa vào kiểm tra client:** Nếu đầu vào đi vào hệ thống backend, phải kiểm tra theo hợp đồng ở điểm xử lý tin cậy, kể cả khi giao diện đã có validation. Regex dùng để kiểm tra định dạng không thay thế tham số hóa SQL, kiểm tra quyền truy cập, giới hạn kích thước input hoặc xử lý lỗi nghiệp vụ.

## 8. Lưu ý với Unicode, khoảng trắng và dữ liệu dài

- **Chính sách chữ số:** `[0-9]` chỉ cho phép các chữ số ASCII. Nếu muốn nhận chữ số từ nhiều hệ chữ viết, phải xác định quy tắc Unicode và hành vi parser tiếp theo; đừng giả sử regex và API parse luôn chấp nhận đúng cùng tập ký tự.
- **Khoảng trắng:** `strip()` xử lý các ký tự theo `Character.isWhitespace` nhưng không loại mọi ký tự khoảng trắng, ví dụ có những khoảng trắng không ngắt dòng. Nếu đầu vào phải tuân theo giao thức với khoảng trắng ASCII cụ thể, hãy định nghĩa chính sách tương ứng.
- **Số rất dài:** Regex đúng về hình thức không kiểm tra được giới hạn `int`/`long`. Cần kiểm tra trước kích thước tối đa, bắt lỗi parse, và không dùng `BigInteger`/`BigDecimal` vô giới hạn đối với dữ liệu không đáng tin nếu hệ thống có giới hạn tài nguyên.
- **Thông báo lỗi:** Nên diễn đạt bằng yêu cầu cụ thể (“Chỉ nhập số nguyên từ 1 đến 100”), thay vì hiển thị stack trace hoặc thông điệp nội bộ của `NumberFormatException`.
- **Regex dùng nhiều lần:** Tái sử dụng `Pattern` đã biên dịch, như trong ví dụ, thay vì biên dịch lại ở mỗi bản ghi. Tránh regex có backtracking tốn kém khi xử lý dữ liệu lớn hoặc không đáng tin.
- **Kiểm thử ranh giới:** Thử `null`, chuỗi rỗng, khoảng trắng, số âm, dấu cộng, chữ số Unicode, dấu phân cách, số 0 đầu, số tràn, ngày nhuận, dữ liệu có hậu tố và kích thước tối đa.

## 9. Câu hỏi thực hành

1. Vì sao `Pattern.compile("[0-9]+").matcher("id=42x").find()` trả `true` nhưng không thể dùng để xác nhận cả input là một số nguyên?
2. Nếu `"2147483648"` khớp `[0-9]+`, tại sao `Integer.parseInt` vẫn ném `NumberFormatException`?
3. Vì sao dùng `Boolean.parseBoolean("yes")` có thể gây sai dữ liệu nếu hệ thống yêu cầu nhập rõ `true` hoặc `false`?
4. Với ngày `"2023-02-29"`, regex xác nhận được điều gì và `LocalDate.parse` kiểm tra thêm điều gì?
5. Nếu người dùng nhập `"00123"` làm mã thành viên, có nên đổi thành `int` trước khi lưu không? Vì sao?
6. Khi parse số theo locale, vì sao chỉ parse được một đoạn đầu của input chưa được coi là dữ liệu hợp lệ?

**Ghi nhớ:** Chuyển đổi `String` an toàn yêu cầu **kiểm tra toàn chuỗi theo chính sách**, **parse đúng kiểu và phạm vi**, **kiểm tra nghiệp vụ**, rồi **trả lỗi rõ ràng** nếu bất kỳ bước nào thất bại. Không được đánh đồng “tìm thấy một đoạn phù hợp” với “cả dữ liệu đầu vào hợp lệ”.