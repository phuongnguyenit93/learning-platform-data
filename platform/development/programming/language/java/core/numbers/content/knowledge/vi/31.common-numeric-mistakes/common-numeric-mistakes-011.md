# Nhầm Integer.parseInt, Integer.decode và Integer.getInteger

## 1. Ba phương thức, ba ý nghĩa hoàn toàn khác nhau

Trong Java, `java.lang.Integer` có những tên phương thức dễ khiến ta tưởng chúng đều nhận một chuỗi rồi chuyển thành số nguyên. Sự khác nhau nằm ở **chuỗi truyền vào là giá trị hay tên cấu hình** và **quy tắc cơ số**:

- **`Integer.parseInt(String)`** phân tích **nội dung chuỗi giá trị** theo **hệ thập phân**, trả primitive `int`. Overload `parseInt(String, int radix)` dùng cơ số tường minh từ 2 đến 36.
- **`Integer.decode(String)`** phân tích **nội dung chuỗi giá trị** và nhận các tiền tố để tự xác định cơ số: `0x`/`0X` hoặc `#` cho hex, số `0` dẫn đầu chuỗi nhiều chữ số cho octal, không prefix cho decimal. Kết quả là `Integer`.
- **`Integer.getInteger(String)`** coi chuỗi đối số là **tên JVM system property**, đọc property rồi diễn giải **giá trị property** theo cách `decode`; nó không parse chính đối số truyền vào. Kết quả là `Integer` hoặc `null` nếu không có/không parse được và không chỉ định mặc định.

Ví dụ:

```java
System.out.println(Integer.parseInt("010")); // 10
System.out.println(Integer.decode("010"));   // 8
```

`Integer.getInteger("010")` lại tìm **system property có tên `010`**; kết quả tùy thuộc cấu hình JVM, có thể là `null`. Nó không có nghĩa chuyển chuỗi `"010"` thành `10` hoặc `8`.

### Bảng so sánh

| Tiêu chí | `parseInt` | `decode` | `getInteger` |
| --- | --- | --- | --- |
| Tham số chuỗi | Giá trị cần parse | Giá trị cần decode | **Tên property** |
| Nguồn thực của số | Đối số `s` | Đối số `nm` | `System.getProperty(name)` |
| Mặc định radix | 10 | Suy ra từ prefix | Suy ra từ **giá trị property** |
| Đầu vào `"010"` | 10 | 8 | Tìm property tên `010` |
| Đầu vào `"0x10"` | Lỗi | 16 | Tìm property tên `0x10` |
| Kiểu trả về | `int` | `Integer` | `Integer` |
| Chuỗi số sai | Ném `NumberFormatException` | Ném `NumberFormatException` | `null` hoặc giá trị mặc định nếu property không parse được |
| Dùng cho | Số nguyên với radix rõ | Số nguyên cho phép prefix | Cấu hình `-D` của JVM |

Đây là bài học về **lựa chọn API theo hợp đồng dữ liệu**, không chỉ cách nhớ tên hàm. Sai lầm thường không xuất hiện khi test `"123"`, vì `parseInt` và `decode` đều trả 123; các ca có số 0 đầu và property JVM mới phơi bày khác biệt.

## 2. parseInt: số nguyên decimal mặc định

`Integer.parseInt(String s)` sử dụng radix 10:

```java
System.out.println(Integer.parseInt("42"));   // 42
System.out.println(Integer.parseInt("+42"));  // 42
System.out.println(Integer.parseInt("-42"));  // -42
System.out.println(Integer.parseInt("010"));  // 10
System.out.println(Integer.parseInt("08"));   // 8
```

Dấu `+` hoặc `-` có thể đứng **ở đầu** số. Dấu `0` dẫn đầu **không** biến chuỗi thành octal. Ngược lại, các chuỗi dưới đây **không hợp lệ** đối với overload decimal:

```java
// Mỗi dòng dưới đây ném NumberFormatException khi chạy:
Integer.parseInt("0x10");
Integer.parseInt("12.5");
Integer.parseInt("1_000");
Integer.parseInt(" 42 ");
Integer.parseInt("");
Integer.parseInt("2147483648");
```

`parseInt` không tự loại khoảng trắng, chấp nhận dấu phân nhóm hàng nghìn hoặc chấp nhận dấu gạch dưới `_` trong chuỗi. Java có literal số ở mã nguồn `1_000`, nhưng cú pháp literal Java **không giống** cú pháp chuỗi runtime của `parseInt`.

### Radix tường minh

`Integer.parseInt(String s, int radix)` cho phép radix từ `Character.MIN_RADIX` (2) đến `Character.MAX_RADIX` (36):

```java
System.out.println(Integer.parseInt("1010", 2)); // 10
System.out.println(Integer.parseInt("17", 8));   // 15
System.out.println(Integer.parseInt("10", 16));  // 16
System.out.println(Integer.parseInt("ff", 16));  // 255
System.out.println(Integer.parseInt("-ff", 16)); // -255
System.out.println(Integer.parseInt("Z", 36));   // 35
```

Ngay cả khi truyền radix 16, **prefix `0x` không được chấp nhận**:

```java
// Đều ném NumberFormatException:
Integer.parseInt("0x10", 16);
Integer.parseInt("0b1010", 2);
```

Muốn parse chuỗi `0x10` theo radix 16, có thể tách prefix sau khi validate rồi parse `"10"`, hoặc dùng `decode` nếu hợp đồng cú pháp cho phép nó. Nếu tự tách prefix, cần xử lý `+`/`-` trước prefix, chuỗi rỗng, và giới hạn `int`.

**Kiểu trả về:** `parseInt` trả primitive `int`, còn `Integer.valueOf("42")` trả wrapper `Integer` sau khi parse decimal. Cả hai không tìm system property.

## 3. decode: các prefix và bẫy octal

`Integer.decode(String nm)` cho phép các biểu diễn sau:

| Input | Radix | Kết quả |
| --- | ---: | ---: |
| `"42"` | 10 | 42 |
| `"0x2A"` | 16 | 42 |
| `"0X2a"` | 16 | 42 |
| `"#2A"` | 16 | 42 |
| `"052"` | 8 | 42 |
| `"-0x2A"` | 16 | -42 |
| `"+052"` | 8 | 42 |

```java
System.out.println(Integer.decode("42"));    // 42
System.out.println(Integer.decode("0x2A"));  // 42
System.out.println(Integer.decode("0X2a"));  // 42
System.out.println(Integer.decode("#2A"));   // 42
System.out.println(Integer.decode("052"));   // 42
System.out.println(Integer.decode("-0x2A")); // -42
System.out.println(Integer.decode("+052"));  // 42
```

Đặt dấu trước prefix: `"-0x2A"` hợp lệ, `"0x-2A"` không hợp lệ. Hex cho phép chữ số `a-f` hoặc `A-F`.

**Nguy cơ cao nhất: zero đầu có ý nghĩa octal.** Với các giá trị được thêm số 0 để hiển thị:

```java
System.out.println(Integer.parseInt("010")); // 10
System.out.println(Integer.decode("010"));   // 8
System.out.println(Integer.parseInt("08"));  // 8
// Integer.decode("08") -> NumberFormatException
```

Vì `8` và `9` không phải chữ số octal, `decode("08")` hoặc `decode("09")` thất bại. Nếu người dùng nhập số lượng dạng decimal zero-padded, dùng `parseInt` sẽ phù hợp hơn.

### decode không nhận mọi literal của Java

Java source hỗ trợ `0b1010` là binary integer literal, nhưng `Integer.decode("0b1010")` **không** parse được. Hãy dùng `Integer.parseInt("1010", 2)` khi contract xác định radix 2.

```java
System.out.println(0b1010);                    // 10: literal trong code
System.out.println(Integer.parseInt("1010", 2)); // 10
// Integer.decode("0b1010") ném NumberFormatException
```

`decode` cũng không parse phần thập phân như `"10.5"`. Nó trả signed `Integer`, nên input biểu diễn giá trị lớn hơn `Integer.MAX_VALUE` cũng không trở thành số dương hợp lệ chỉ vì viết ở dạng hex.

## 4. getInteger: đọc JVM system property, không đọc giá trị trực tiếp

`Integer.getInteger(String name)` tương đương về ý tưởng với việc tra chuỗi từ system property, sau đó decode **giá trị**:

```java
String raw = System.getProperty("app.maxWorkers");
Integer parsed = raw == null ? null : Integer.decode(raw);
```

Đây chỉ là minh họa **đường đi dữ liệu**; API thật có xử lý các trường hợp property sai cú pháp và giá trị mặc định. Cần nhớ:

```java
System.setProperty("app.maxWorkers", "0x10");

System.out.println(System.getProperty("app.maxWorkers")); // 0x10
System.out.println(Integer.getInteger("app.maxWorkers")); // 16
System.out.println(Integer.getInteger("app.maxWorkers", 4)); // 16
```

`System.getProperty` trả chuỗi raw, còn `getInteger` trả `Integer` sau khi decode. Không tự tin rằng `getInteger("100")` sẽ nhận số 100; nó đang tra property tên `100`.

### Ba overload

```java
Integer.getInteger(String name)
Integer.getInteger(String name, int defaultValue)
Integer.getInteger(String name, Integer defaultValue)
```

Đây là những **chữ ký minh họa**, không phải ba câu lệnh Java được đặt trong thân method. Overload không có default trả `null` nếu property không tồn tại **hoặc giá trị không decode được**. Overload có default trả giá trị mặc định cho cả hai trường hợp đó.

```java
System.setProperty("app.retryLimit", "08");

System.out.println(Integer.getInteger("app.retryLimit"));    // null
System.out.println(Integer.getInteger("app.retryLimit", 3)); // 3
```

Tại sao? `getInteger` dùng logic `decode` cho giá trị `"08"`, nên octal thất bại. Điều đáng lưu ý là ở `getInteger`, **lỗi cú pháp cấu hình có thể bị che bằng default**, trong khi `decode("08")` gọi trực tiếp ném `NumberFormatException`.

### JVM -D và environment variable khác nhau

System property có thể được truyền khi khởi động chương trình:

```bash
java -Dapp.maxWorkers=0x10 App
```

Khi đó `Integer.getInteger("app.maxWorkers")` có thể trả 16. Trái lại, biến môi trường `APP_MAX_WORKERS` phải đọc bằng:

```java
String raw = System.getenv("APP_MAX_WORKERS");
int maxWorkers = raw == null ? 4 : Integer.parseInt(raw);
```

Đoạn trên chỉ là minh họa; production cần báo lỗi về cú pháp và giới hạn giá trị. **`Integer.getInteger("APP_MAX_WORKERS")` không đọc environment variable** — trừ việc JVM có system property *riêng* trùng tên, hai không gian cấu hình là khác nhau.

System properties thuộc phạm vi JVM và có thể được thay đổi bởi chương trình. Trong test, nên lưu giá trị cũ, set property tạm rồi khôi phục bằng `finally`. Quyền truy cập property cũng có thể bị hạn chế, và `SecurityException` là một vấn đề khác với “không có property”.

## 5. Bảng các ca phân biệt ba API

| Biểu thức | Kết quả / ý nghĩa |
| --- | --- |
| `parseInt("10")` | 10 |
| `parseInt("010")` | 10 |
| `decode("010")` | 8 |
| `parseInt("10", 8)` | 8 |
| `parseInt("10", 16)` | 16 |
| `decode("0x10")` | 16 |
| `decode("#10")` | 16 |
| `decode("-0x10")` | -16 |
| `parseInt("08")` | 8 |
| `decode("08")` | `NumberFormatException` |
| `parseInt("0x10")` | `NumberFormatException` |
| `parseInt("0x10", 16)` | `NumberFormatException` |
| `parseInt("1010", 2)` | 10 |
| `decode("0b1010")` | `NumberFormatException` |
| `getInteger("app.limit")` | Giá trị đọc từ property `app.limit`; có thể `null` |
| `getInteger("010")` | Tra **property tên 010**, không parse số 010 |

Chọn parser bằng **đặc tả input**, không phải bằng cảm giác phương thức nào tiện nhất. Với decimal người dùng nhập, việc âm thầm hỗ trợ octal thường là thay đổi nguy hiểm.

## 6. Chương trình Java 17+ hoàn chỉnh và stdout xác định

Chương trình tự đặt các system property có tên riêng, xoá một property giả định “missing” trong phạm vi ví dụ và khôi phục trạng thái ban đầu bằng `finally`. Nó kiểm tra các trường hợp sai bằng cách bắt `NumberFormatException` rồi in tên ngoại lệ, không dựa vào thông điệp lỗi có thể thay đổi giữa các JDK.

Lưu thành **`IntegerMethodComparison.java`**:

```java
public class IntegerMethodComparison {

    static void restore(String key, String previous) {
        if (previous == null) {
            System.clearProperty(key);
        } else {
            System.setProperty(key, previous);
        }
    }

    static void expectBad(String label, String text, boolean decode) {
        try {
            if (decode) {
                Integer.decode(text);
            } else {
                Integer.parseInt(text);
            }
            System.out.println(label + ": unexpectedly accepted");
        } catch (NumberFormatException ex) {
            System.out.println(label + ": NumberFormatException");
        }
    }

    public static void main(String[] args) {
        System.out.println("parseInt 010 = " + Integer.parseInt("010"));
        System.out.println("decode 010 = " + Integer.decode("010"));
        System.out.println("parseInt base16 = "
                + Integer.parseInt("10", 16));
        System.out.println("decode hex = " + Integer.decode("0x10"));
        System.out.println("decode #2A = " + Integer.decode("#2A"));
        System.out.println("decode -010 = " + Integer.decode("-010"));

        expectBad("parseInt 0x10", "0x10", false);
        expectBad("decode 08", "08", true);
        expectBad("decode 0b1010", "0b1010", true);
        expectBad("parseInt overflow", "2147483648", false);

        String good = "lesson381.integer.good";
        String invalid = "lesson381.integer.invalid";
        String absent = "lesson381.integer.absent";
        String prevGood = System.getProperty(good);
        String prevInvalid = System.getProperty(invalid);
        String prevAbsent = System.getProperty(absent);

        try {
            System.setProperty(good, "0x10");
            System.setProperty(invalid, "08");
            System.clearProperty(absent);

            System.out.println("raw property = "
                    + System.getProperty(good));
            System.out.println("getInteger good = "
                    + Integer.getInteger(good));
            System.out.println("getInteger invalid default = "
                    + Integer.getInteger(invalid, 7));
            System.out.println("getInteger absent = "
                    + Integer.getInteger(absent));
            System.out.println("getInteger absent default = "
                    + Integer.getInteger(absent, 3));
        } finally {
            restore(good, prevGood);
            restore(invalid, prevInvalid);
            restore(absent, prevAbsent);
        }
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn, từ thư mục chứa file:

```bash
javac IntegerMethodComparison.java
java IntegerMethodComparison
```

Đầu ra dự kiến:

```text
parseInt 010 = 10
decode 010 = 8
parseInt base16 = 16
decode hex = 16
decode #2A = 42
decode -010 = -8
parseInt 0x10: NumberFormatException
decode 08: NumberFormatException
decode 0b1010: NumberFormatException
parseInt overflow: NumberFormatException
raw property = 0x10
getInteger good = 16
getInteger invalid default = 7
getInteger absent = null
getInteger absent default = 3
```

Ví dụ kiểm tra đồng thời **khác biệt radix** và **khác biệt nguồn dữ liệu**. Nó không dựa vào system property bất kỳ đã có sẵn; các giá trị được ghi đè tạm thời và phục hồi. Việc dùng tên property riêng giúp hạn chế tác động tới ứng dụng khác trong cùng JVM, tuy nhiên phần test thực tế vẫn cần cẩn thận với luồng chạy song song sử dụng cùng global properties.

## 7. Kiểm soát cú pháp input: parse decimal thật sự

Đối với dữ liệu số đếm nhận từ form hoặc API, người dùng thường mong decimal, có thể có số 0 đầu. Một hàm strict có thể từ chối mọi ký tự ngoài digit ASCII, kiểm tra giới hạn rồi parse:

```java
static int parseItemCount(String raw) {
    if (raw == null || !raw.matches("[0-9]+")) {
        throw new IllegalArgumentException(
                "Count must use ASCII decimal digits only");
    }
    final int count;
    try {
        count = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Count exceeds int range", ex);
    }
    if (count > 5000) {
        throw new IllegalArgumentException("Count too large");
    }
    return count;
}
```

Đây là **phương thức minh họa phải nằm trong một lớp**, không phải chương trình hoàn chỉnh. Nó chấp nhận `"0008"` làm decimal 8 và từ chối `"-2"`, `"+2"`, khoảng trắng, `"0x10"`, dấu phẩy và các chữ số Unicode không thuộc ASCII. Nếu hợp đồng cho phép số âm, dấu cộng hoặc whitespace bên ngoài, hãy thay validation rõ ràng chứ không tự đổi `parseInt` thành `decode`.

`parseInt` tự dùng `Character.digit` cho từng ký tự theo radix, nên có thể nhận một số chữ số Unicode. Nếu hệ thống yêu cầu **đúng dạng ASCII**, cần bước xác thực riêng như ví dụ trên.

### Làm gì khi người dùng muốn nhập hex?

Nếu hợp đồng cho phép decimal `42` hoặc hex `0x2A` nhưng **không** octal từ zero đầu, `decode` không hoàn toàn phù hợp. Có thể phát hiện prefix hex và áp dụng `parseInt` với radix 16, còn các chuỗi khác parse decimal. Chú ý dấu `-` và `+` phải được xử lý trước prefix, và không được để chuỗi chỉ có `0x` lọt qua.

Cần test `"08"`, `"010"`, `"0x2A"`, `"-0x2A"`, `"0x"` và giá trị vượt `int`. Cách triển khai parser nên được định nghĩa bởi giao thức cụ thể, không đơn thuần sao chép quy tắc của Java source literals.

## 8. getInteger có default có thể che lỗi cấu hình

Xét `-Dapp.poolSize=08`. Người vận hành mong tám luồng; nếu chương trình gọi:

```java
int poolSize = Integer.getInteger("app.poolSize", 4);
```

giá trị thực có thể trở thành **4**, vì `decode("08")` không hợp lệ trong octal và API trả default. Chương trình chạy nhưng không như cấu hình mong muốn. Điều này khác với `parseInt("08")` trả 8.

Một cách đọc **decimal strict** hơn:

```java
static int positiveDecimalProperty(String name, int defaultValue) {
    String raw = System.getProperty(name);
    if (raw == null) {
        return defaultValue; // Chỉ thiếu mới sử dụng mặc định.
    }

    final int value;
    try {
        value = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid decimal property: " + name, ex);
    }
    if (value <= 0) {
        throw new IllegalArgumentException(
                "Property must be positive: " + name);
    }
    return value;
}
```

Đây là phương thức minh họa, cần đặt trong một lớp; ví dụ giả định `defaultValue` hợp lệ theo miền dương, nên caller cũng cần kiểm tra giá trị mặc định. Nó phân biệt property **vắng mặt** với property **có mặt nhưng sai cú pháp**, đồng thời đảm bảo số lớn hơn 0.

Nếu property là bắt buộc, không nên trả default khi thiếu; có thể ném `IllegalStateException` hoặc ngoại lệ cấu hình có thông báo cụ thể. Nếu cho phép `0x` nhưng không cho phép octal ngầm, parser phải có chính sách rõ, không dùng `getInteger` như một trình kiểm tra magic.

## 9. Overflow, kiểu wrapper, null và signedness

`Integer.parseInt` và `Integer.decode` xử lý số nguyên có dấu 32 bit: miền `-2147483648` đến `2147483647`. Những chuỗi có giá trị ngoài miền tạo `NumberFormatException`:

```java
// Các lời gọi này ném NumberFormatException:
Integer.parseInt("2147483648");
Integer.decode("0x80000000");
```

Nếu mục tiêu là số nguyên lớn hơn `int`, cân nhắc `Long.parseLong`/`Long.decode` hoặc `java.math.BigInteger`. Với bit pattern unsigned 32-bit, `Integer.parseUnsignedInt` có hợp đồng khác: nó có thể trả một `int` mang bit pattern được diễn giải là âm theo signed; cần xử lý `Integer.toUnsignedString` hay kiểu rộng hơn khi trình bày. Đừng tự ép kiểu hay dùng `decode` rồi xem đó là unsigned parser.

Vì `getInteger` trả nullable `Integer`, auto-unboxing có thể ném `NullPointerException`:

```java
Integer maybePort = Integer.getInteger("app.port");
if (maybePort != null) {
    int port = maybePort;
    System.out.println(port);
}
```

Không viết `int port = Integer.getInteger("app.port");` nếu không có bảo đảm property tồn tại và hợp lệ. Dùng overload có default khi fallback được quy định hoặc kiểm tra null rõ.

`Integer.valueOf("123")` trả wrapper `Integer`; `Integer.parseInt("123")` trả primitive `int`. So sánh hai wrapper bằng `==` có thể phụ thuộc cache object; dùng `equals` cho value (sau khi kiểm tra null), hoặc so sánh primitive.

## 10. Bài kiểm tra hồi quy cho lỗi nhầm lẫn

Khi review việc dùng `parseInt`, `decode` và `getInteger`, tối thiểu hãy kiểm tra các nhóm đầu vào:

| Nhóm | Dữ liệu | Điều cần xác nhận |
| --- | --- | --- |
| Decimal thông thường | `"0"`, `"123"`, `"-9"` | Dấu và radix 10. |
| Zero-padded | `"010"`, `"08"`, `"009"` | `decode` thay đổi nghĩa hoặc từ chối. |
| Hex | `"0x2A"`, `"#2A"`, `"-0x2A"` | `decode` chấp nhận; `parseInt` decimal từ chối. |
| Binary | `"1010"` radix 2, `"0b1010"` | Prefix binary không được `decode` hỗ trợ. |
| Không sạch | `""`, `" 42 "`, `"1_000"`, `"12.0"` | Kiểm tra NFE/validation. |
| Biên kiểu int | `"2147483647"`, `"2147483648"`, `"-2147483648"` | Tràn hoặc chính xác. |
| Property thiếu | Khóa test chưa được đặt | `getInteger` trả null/default. |
| Property sai | `"08"`, `"abc"` | Default có thể che lỗi; strict parser phải phát hiện. |
| Property đúng | `"42"`, `"0x2A"` | Giá trị được parse theo `decode`. |
| Phân biệt nguồn | `-Dapp.x` và environment variable riêng | `getInteger` chỉ đọc system property. |

Trong unit test, đừng dùng property tên chung đã tồn tại như `java.version` để chứng minh một số nguyên cụ thể. Tạo khóa độc lập, lưu giá trị ban đầu, set/clear và restore trong `finally`. Nếu chạy test song song, system properties là **global state** và có thể gây race; ưu tiên đưa cấu hình vào hàm qua tham số hoặc lớp cấu hình thay vì dựa hoàn toàn vào trạng thái JVM.

### Checklist chẩn đoán khi giá trị cấu hình sai

1. Xem **đối số** của phương thức: là giá trị `"08"` hay key `"app.limit"`?
2. Kiểm tra **giá trị raw** từ `System.getProperty` nếu dùng `getInteger`.
3. Ghi rõ radix kỳ vọng: decimal, octal ngầm, hex hay binary.
4. Kiểm tra dấu, prefix, whitespace và ký tự không hợp lệ.
5. Kiểm tra phạm vi `int` và có cần `long`/`BigInteger` không.
6. Xác định thiếu cấu hình có được default hay phải là lỗi.
7. Ghi regression test cho `"010"`, `"08"` và `"0x10"`; ba ca này phân biệt parser nhanh hơn `"123"`.

## 11. Những sai lầm thường gặp

1. **Gọi `getInteger("42")` để chuyển `"42"` thành số:** thực chất tra property tên `42`.
2. **Cho rằng `getInteger` lấy biến môi trường:** nó đọc JVM system property, không phải `System.getenv`.
3. **Dùng `decode` cho số thập phân zero-padded:** `"010"` thành 8 và `"08"` ném lỗi.
4. **Truyền `0x` vào `parseInt(s,16)`:** cần chuỗi chữ số radix 16 không có prefix.
5. **Dùng `decode` để parse `0b`:** nó không hỗ trợ binary prefix.
6. **Cho rằng input chuỗi hỗ trợ underscore như Java literal:** `"1_000"` không hợp lệ với các parser nói trên.
7. **Không phân biệt property missing và invalid:** `getInteger(name,default)` có thể dùng default cho cả hai.
8. **Bỏ qua null từ `getInteger`:** auto-unboxing sẽ ném NPE khi property không có hoặc sai.
9. **Không kiểm tra overflow `int`:** chuỗi quá lớn không thể parse thành signed 32-bit number.
10. **Lạm dụng `decode` vì tiện:** giao thức cần decimal phải dùng decimal parser, không tự thay đổi nghĩa input.
11. **Dùng wrapper `==` làm kiểm tra nội dung:** nguy cơ nhầm instance caching; kiểm tra value bằng `equals`/primitive.
12. **Che mọi lỗi parsing bằng catch rồi trả 0:** cấu hình sai có thể trở thành lỗi nghiệp vụ âm thầm; nên phân loại và truyền thông báo có tên trường.
13. **Dùng `Integer` cho decimal có phần lẻ:** nếu dữ liệu là tiền/đo lường cần decimal exact, dùng `BigDecimal` và chính sách rounding phù hợp.
14. **Cho rằng `parseInt` là kiểm tra ASCII:** nó sử dụng `Character.digit`; validate format ASCII trước nếu giao thức yêu cầu.
15. **Không thử property qua `-D` và `System.setProperty`:** test chỉ gọi trực tiếp `decode` không phát hiện lỗi nhầm key/property.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `parseInt("075")` và `decode("075")` bằng bao nhiêu?

**Đáp án:** 75 và 61. `decode` coi `075` là octal, tức `7 × 8 + 5 = 61`.

**Câu 2.** Vì sao `parseInt("08")` thành 8 nhưng `decode("08")` ném lỗi?

**Đáp án:** `parseInt` mặc định radix 10; `decode` với số 0 đầu dùng radix 8, mà octal không có chữ số 8.

**Câu 3.** Muốn parse chuỗi `"0x2A"` thì chọn phương thức nào?

**Đáp án:** `Integer.decode("0x2A")` trả 42; nếu `parseInt` với radix 16 phải truyền phần chữ số `"2A"`.

**Câu 4.** `getInteger("123")` trả 123 không?

**Đáp án:** Không mặc định. Nó tìm JVM system property có tên `123`; chỉ khi property có giá trị phù hợp thì mới decode giá trị ấy.

**Câu 5.** Vì sao `getInteger("app.workers", 4)` có thể không phù hợp cho cấu hình bắt buộc?

**Đáp án:** Property không tồn tại hoặc sai cú pháp đều có thể dẫn đến default 4, che lỗi người vận hành nhập sai.

**Câu 6.** Chuỗi `"0b1010"` có được `decode` chấp nhận không?

**Đáp án:** Không. Dùng `Integer.parseInt("1010", 2)` khi radix đã rõ.

**Câu 7.** Với property `app.port` có giá trị `"0x1F90"`, `getInteger("app.port")` là bao nhiêu?

**Đáp án:** 8080, vì `0x1F90` là hexadecimal.

**Câu 8.** Khi nào cần validate `[0-9]+` trước `parseInt`?

**Đáp án:** Khi giao thức đòi digit ASCII thuần và không chấp nhận Unicode digit, dấu cộng/trừ hoặc ký tự khác mà parser có thể xử lý.

**Câu 9.** Tại sao `int x = Integer.getInteger("missing.key")` nguy hiểm?

**Đáp án:** Nếu property không có, `getInteger` trả `null`; auto-unboxing sang `int` gây `NullPointerException`.

**Câu 10.** Ba test có giá trị phát hiện nhầm parser nhất là gì?

**Đáp án:** `"010"`, `"08"`, `"0x10"` — chúng cho kết quả/lỗi khác nhau rõ rệt giữa `parseInt` và `decode`; với `getInteger` còn phải kiểm tra property có tên cụ thể.

## 13. Tài liệu tham khảo

- [Java SE 17 — Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `valueOf`, `decode`, `getInteger`, signed/unsigned và overload.
- [Java SE 17 — System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `getProperty`, `setProperty`, `clearProperty` và `getenv`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `Character.digit` và các chữ số theo radix.
- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): số nguyên vượt miền `int` khi ứng dụng cần.

**Ghi nhớ:** `parseInt` đọc **giá trị với radix được xác định**, `decode` đọc **giá trị có prefix hex/octal**, còn `getInteger` đọc **JVM system property theo tên** rồi decode nội dung property. Muốn code dễ hiểu, hãy gọi đúng API theo **nguồn dữ liệu, cú pháp và chính sách lỗi**; kiểm thử zero đầu và property invalid trước khi coi hai lời gọi tương đương.
