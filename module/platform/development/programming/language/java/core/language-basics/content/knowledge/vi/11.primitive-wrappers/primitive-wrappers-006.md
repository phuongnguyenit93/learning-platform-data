# `parseInt()`, `parseDouble()`, `valueOf()` và kiểu kết quả — Java 17+

Khi đọc số từ cấu hình, tham số dòng lệnh hoặc biểu mẫu, Java thường nhận dữ liệu ban đầu dưới dạng `String`. Muốn tính toán, cần **phân tích chuỗi** (*parsing*) để lấy giá trị số. Các phương thức tên gần giống nhau nhưng **kiểu trả về khác nhau**:

- `Integer.parseInt("42")` trả về **primitive `int`**.
- `Double.parseDouble("3.5")` trả về **primitive `double`**.
- `Integer.valueOf("42")` trả về **đối tượng wrapper `Integer`**.
- `Double.valueOf("3.5")` trả về **đối tượng wrapper `Double`**.

Không có phương thức `valueOf()` chung cho mọi lớp với cùng kiểu trả về. **Tên lớp đứng trước dấu chấm quyết định phương thức và kiểu kết quả**: `Integer.valueOf(...)` trả `Integer`, `Long.valueOf(...)` trả `Long`, `String.valueOf(...)` trả `String`.

## 1. Bảng so sánh kiểu trả về

| Lệnh Java | Đối số | Kiểu trả về khai báo | Giá trị minh họa |
| --- | --- | --- | --- |
| `Integer.parseInt("42")` | `String` | `int` | 42 |
| `Integer.valueOf("42")` | `String` | `Integer` | 42 |
| `Integer.valueOf(42)` | `int` | `Integer` | 42 |
| `Double.parseDouble("3.5")` | `String` | `double` | 3.5 |
| `Double.valueOf("3.5")` | `String` | `Double` | 3.5 |
| `Double.valueOf(3.5)` | `double` | `Double` | 3.5 |
| `Long.parseLong("9000000000")` | `String` | `long` | 9000000000 |
| `Long.valueOf("9000000000")` | `String` | `Long` | 9000000000 |
| `Boolean.parseBoolean("true")` | `String` | `boolean` | true |
| `Boolean.valueOf("true")` | `String` | `Boolean` | true |
| `String.valueOf(42)` | `int` | `String` | `"42"` |

`parseInt` và `parseDouble` thuộc **lớp khác nhau**. Không có `Integer.parseDouble` hay `Double.parseInt`. Tên `valueOf` là **overload** trong mỗi lớp, không có nghĩa mọi `valueOf` đều làm cùng một việc.

### Sơ đồ luồng dữ liệu

~~~text
"42" : String
  ├── Integer.parseInt("42") ──────> 42 : int
  └── Integer.valueOf("42") ───────> Integer chua gia tri 42

"3.5" : String
  ├── Double.parseDouble("3.5") ───> 3.5 : double
  └── Double.valueOf("3.5") ───────> Double chua gia tri 3.5

42 : int
  └── String.valueOf(42) ──────────> "42" : String
~~~

## 2. Chương trình Java 17+ chạy độc lập

Tạo tệp **`ParsingReturnTypesDemo.java`** với nội dung sau:

~~~java
public class ParsingReturnTypesDemo {
    static String typeOf(int ignored) {
        return "int";
    }

    static String typeOf(Integer ignored) {
        return "Integer";
    }

    static String typeOf(double ignored) {
        return "double";
    }

    static String typeOf(Double ignored) {
        return "Double";
    }

    public static void main(String[] args) {
        String wholeText = "42";
        String decimalText = "3.5";

        int primitiveInt = Integer.parseInt(wholeText);
        Integer boxedInt = Integer.valueOf(wholeText);
        double primitiveDouble = Double.parseDouble(decimalText);
        Double boxedDouble = Double.valueOf(decimalText);

        System.out.println("parseIntType=" + typeOf(primitiveInt));
        System.out.println("valueOfIntType=" + typeOf(boxedInt));
        System.out.println("parseDoubleType=" + typeOf(primitiveDouble));
        System.out.println("valueOfDoubleType=" + typeOf(boxedDouble));

        System.out.println("intValue=" + primitiveInt);
        System.out.println("doubleValue=" + primitiveDouble);
        System.out.println("wrapperIntPlusOne=" + (boxedInt + 1));
        System.out.println("wrapperDoublePlusHalf="
                + (boxedDouble + 0.5));

        Integer boxedByAssignment = Integer.parseInt("7");
        int unboxedByAssignment = Integer.valueOf("8");
        System.out.println("boxedAssignment=" + boxedByAssignment);
        System.out.println("unboxedAssignment=" + unboxedByAssignment);

        int hexPrimitive = Integer.parseInt("FF", 16);
        Integer hexWrapper = Integer.valueOf("FF", 16);
        System.out.println("hexPrimitive=" + hexPrimitive);
        System.out.println("hexWrapper=" + hexWrapper);

        long bigPrimitive = Long.parseLong("9000000000");
        Long bigWrapper = Long.valueOf("9000000000");
        System.out.println("longPrimitive=" + bigPrimitive);
        System.out.println("longWrapper=" + bigWrapper);

        boolean flagPrimitive = Boolean.parseBoolean("TrUe");
        Boolean flagWrapper = Boolean.valueOf("true");
        System.out.println("booleanPrimitive=" + flagPrimitive);
        System.out.println("booleanWrapper=" + flagWrapper);
        System.out.println("booleanUnknown="
                + Boolean.parseBoolean("yes"));

        String backToText = String.valueOf(primitiveInt);
        System.out.println("stringType=" + backToText.getClass().getSimpleName());
        System.out.println("stringValue=" + backToText);

        System.out.println("scientific="
                + Double.parseDouble("1e3"));
        System.out.println("nanAccepted="
                + Double.isNaN(Double.parseDouble("NaN")));
        System.out.println("infinityAccepted="
                + Double.isInfinite(Double.parseDouble("Infinity")));

        try {
            Integer.parseInt("42.0");
        } catch (NumberFormatException ex) {
            System.out.println("invalidInteger=NumberFormatException");
        }

        try {
            Double.parseDouble("not-a-number");
        } catch (NumberFormatException ex) {
            System.out.println("invalidDouble=NumberFormatException");
        }

        try {
            Integer.parseInt("2147483648");
        } catch (NumberFormatException ex) {
            System.out.println("integerOverflow=NumberFormatException");
        }

        try {
            Integer.parseInt(" 42 ");
        } catch (NumberFormatException ex) {
            System.out.println("integerSpaces=NumberFormatException");
        }

        System.out.println("strippedInteger="
                + Integer.parseInt(" 42 ".strip()));

        Integer missing = null;
        System.out.println("wrapperMissing=" + (missing == null));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa tệp và chạy với **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ParsingReturnTypesDemo.java
java ParsingReturnTypesDemo
~~~

**Expected output chính xác của lệnh `java ParsingReturnTypesDemo`** (không tính đầu ra phiên bản JDK):

~~~text
parseIntType=int
valueOfIntType=Integer
parseDoubleType=double
valueOfDoubleType=Double
intValue=42
doubleValue=3.5
wrapperIntPlusOne=43
wrapperDoublePlusHalf=4.0
boxedAssignment=7
unboxedAssignment=8
hexPrimitive=255
hexWrapper=255
longPrimitive=9000000000
longWrapper=9000000000
booleanPrimitive=true
booleanWrapper=true
booleanUnknown=false
stringType=String
stringValue=42
scientific=1000.0
nanAccepted=true
infinityAccepted=true
invalidInteger=NumberFormatException
invalidDouble=NumberFormatException
integerOverflow=NumberFormatException
integerSpaces=NumberFormatException
strippedInteger=42
wrapperMissing=true
~~~

Các hàm `typeOf(...)` được **overload** với tham số `int`, `Integer`, `double`, `Double` để chứng minh compiler chọn kiểu đầu vào. Đây là minh họa theo **kiểu tĩnh** của biểu thức, không dựa vào `getClass()` của primitive (primitive không có phương thức `getClass()`).

## 3. `parseInt()`: trả về `int`, kiểm tra chuỗi số nguyên

~~~java
int amount = Integer.parseInt("42");
int negative = Integer.parseInt("-15");
int hex = Integer.parseInt("FF", 16);
~~~

`Integer.parseInt(String)` dùng cơ số 10. Overload `Integer.parseInt(String, int radix)` cho phép chọn cơ số từ 2 đến 36:

| Mã | Kết quả | Ghi chú |
| --- | ---: | --- |
| `Integer.parseInt("1010", 2)` | 10 | Nhị phân |
| `Integer.parseInt("17", 8)` | 15 | Bát phân |
| `Integer.parseInt("42")` | 42 | Thập phân |
| `Integer.parseInt("FF", 16)` | 255 | Hexadecimal |
| `Integer.parseInt("-10")` | −10 | Số âm |
| `Integer.parseInt("+10")` | 10 | Dấu cộng hợp lệ |

Nếu chuỗi không phải biểu diễn số nguyên hợp lệ theo cơ số được chọn, giá trị vượt miền `int` hoặc tham số không hợp lệ, phương thức sẽ ném `NumberFormatException`. Ví dụ `"42.0"` không phải cú pháp số nguyên, và `"2147483648"` vượt `Integer.MAX_VALUE`.

`"0xFF"` **không** được `Integer.parseInt(..., 16)` tự bỏ tiền tố `0x`. Để phân tích `"FF"` với radix 16, truyền đúng phần chữ số. API `Integer.decode("0xFF")` là một cơ chế khác, có quy tắc nhận tiền tố riêng.

## 4. `parseDouble()`: trả về `double`

~~~java
double a = Double.parseDouble("3.5");
double b = Double.parseDouble("1e3");  // 1000.0.
double special = Double.parseDouble("NaN");
~~~

`Double.parseDouble` nhận cú pháp biểu diễn `double` của Java cho chuỗi thích hợp; ngoài số thập phân, có thể nhận ký hiệu khoa học như `1e3` và các giá trị đặc biệt `NaN`, `Infinity`. Do vậy, **phân tích cú pháp thành công không có nghĩa dữ liệu là số hữu hạn**.

Nếu nghiệp vụ yêu cầu số hữu hạn:

~~~java
double rate = Double.parseDouble("1e3");
if (!Double.isFinite(rate)) {
    throw new IllegalArgumentException("Must be finite");
}
~~~

Nếu chuỗi không hợp lệ, ví dụ `"not-a-number"`, phương thức ném `NumberFormatException`. Lưu ý `double` là số thực nhị phân IEEE 754, nên giá trị thập phân như `0.1` thường không được biểu diễn hoàn toàn chính xác. Với tiền tệ cần độ chính xác thập phân, cân nhắc `BigDecimal` và quy tắc làm tròn rõ ràng thay vì chỉ dựa vào `double`.

## 5. `valueOf()`: kết quả phụ thuộc lớp và overload

### `Integer.valueOf`

~~~java
Integer fromText = Integer.valueOf("42");
Integer fromPrimitive = Integer.valueOf(42);
Integer fromHex = Integer.valueOf("FF", 16);
~~~

Cả ba biểu thức trên đều có kiểu **`Integer`**. Một số giá trị nhỏ có thể dùng đối tượng wrapper được cache. Vì thế **không dùng `==` giữa hai wrapper để kiểm tra giá trị số**; dùng `equals()` hoặc `Objects.equals()` khi có null.

### `Double.valueOf`

~~~java
Double fromText = Double.valueOf("3.5");
Double fromPrimitive = Double.valueOf(3.5);
~~~

Cả hai trả về kiểu **`Double`**. Khác với `Double.parseDouble`, kiểu trả về được khai báo là wrapper, không phải primitive.

### `String.valueOf` có chức năng hoàn toàn khác

~~~java
String text = String.valueOf(42);     // "42".
String flagText = String.valueOf(true); // "true".
~~~

`String.valueOf(...)` trả về **`String`**, chuyển một giá trị thành biểu diễn văn bản. Nó không phân tích chuỗi sang số. Nói “`valueOf` luôn trả wrapper” là sai vì còn phải xác định lớp chứa phương thức.

### `Boolean` cũng có `parseBoolean` và `valueOf`

~~~java
boolean primitive = Boolean.parseBoolean("true");
Boolean wrapper = Boolean.valueOf("true");
~~~

`Boolean.parseBoolean` chỉ trả `true` khi chuỗi bằng `"true"` không phân biệt hoa/thường; các chuỗi khác như `"yes"` trả `false` thay vì `NumberFormatException`. Nếu cần từ chối đầu vào ngoài `true/false`, phải **validation riêng**.

## 6. Boxing và unboxing không đổi kiểu trả về của phương thức

~~~java
Integer boxed = Integer.parseInt("42"); // parseInt TRA int, sau do boxing.
int primitive = Integer.valueOf("42"); // valueOf TRA Integer, sau do unboxing.
~~~

Hai câu trên biên dịch được nhưng **không** chứng minh `parseInt` trả wrapper hay `valueOf` trả primitive. Kiểu trả về thực tế được khai báo bởi phương thức; Java có thể tự chuyển ở **ngữ cảnh gán**.

| Biểu thức bên phải | Kiểu phương thức trả về | Kiểu biến bên trái | Chuyển đổi thêm |
| --- | --- | --- | --- |
| `Integer.parseInt("42")` | `int` | `int` | Không |
| `Integer.parseInt("42")` | `int` | `Integer` | Boxing |
| `Integer.valueOf("42")` | `Integer` | `Integer` | Không |
| `Integer.valueOf("42")` | `Integer` | `int` | Unboxing |
| `Double.parseDouble("3.5")` | `double` | `Double` | Boxing |
| `Double.valueOf("3.5")` | `Double` | `double` | Unboxing |

**Bẫy `null`:** nếu một biến `Integer` hoặc `Double` đang là null mà được unbox, Java ném `NullPointerException`. Việc gọi phương thức parsing trên chuỗi đầu vào sai lại là một dạng vấn đề khác, thường là `NumberFormatException`.

## 7. Làm sạch và kiểm tra đầu vào

`Integer.parseInt(" 42 ")` ném `NumberFormatException` vì dấu cách đầu/cuối không thuộc cú pháp số nguyên. Nếu ứng dụng cho phép khoảng trắng viền, chủ động chuẩn hóa:

~~~java
String raw = " 42 ";
int parsed = Integer.parseInt(raw.strip()); // 42.
~~~

**Không bao giờ mặc định mọi khoảng trắng đều vô hại** trong dữ liệu chính thức: ứng dụng cần quyết định có được bỏ chúng hay phải báo sai định dạng.

Một hàm đơn giản xử lý đầu vào bắt buộc là số nguyên:

~~~java
static int parseRequiredInt(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Value is required");
    }
    return Integer.parseInt(raw.strip());
}
~~~

- `null` và chuỗi trắng bị báo là thiếu.
- Chuỗi hợp lệ sau chuẩn hóa được phân tích thành `int`.
- Chuỗi sai định dạng hoặc vượt miền `int` ném `NumberFormatException`. Có thể bắt ngoại lệ này ở tầng tương tác người dùng để trả thông báo rõ ràng, thay vì nuốt lỗi và mặc định giá trị 0 khi không được phép.

### Phân biệt parsing với ép kiểu

~~~java
String text = "42";
// int bad = (int) text;  // LOI BIEN DICH.
int value = Integer.parseInt(text);
~~~

Cast số không đọc các chữ số trong `String`. Parsing chuỗi và ép kiểu số là hai thao tác khác nhau.

## 8. Chọn API nào khi viết Java?

| Nhu cầu | Cách chọn | Lý do |
| --- | --- | --- |
| Cần số nguyên primitive để tính toán | `Integer.parseInt(raw)` | Trả trực tiếp `int` |
| Cần `Integer` cho API/generic | `Integer.valueOf(raw)` | Trả wrapper |
| Cần số thực primitive | `Double.parseDouble(raw)` | Trả `double` |
| Cần wrapper số thực | `Double.valueOf(raw)` | Trả `Double` |
| Cần đọc số nguyên dài | `Long.parseLong(raw)` | Trả `long` |
| Cần wrapper số nguyên dài | `Long.valueOf(raw)` | Trả `Long` |
| Cần chuyển primitive thành văn bản | `String.valueOf(value)` | Trả `String` |
| Cần kiểm soát base 16 | `Integer.parseInt(raw, 16)` | Kết quả `int`, chuỗi chữ số hex |
| Cần giá trị tiền tệ chính xác | `new BigDecimal(raw)` và thiết kế scale/rounding | Tránh sai số nhị phân của `double` |

Lưu ý `valueOf` trên một wrapper **không nhất thiết tạo đối tượng mới mỗi lần**. API có thể cache các đối tượng bất biến. Vì thế đừng đánh đồng “kiểu trả về là wrapper” với “mỗi lần gọi luôn cấp phát mới”.

## 9. Những lỗi thường gặp

| Hiểu sai | Điều đúng |
| --- | --- |
| “`Integer.parseInt` trả `Integer`.” | Trả **`int`**; có thể được boxing khi gán vào `Integer` |
| “`Integer.valueOf` trả `int`.” | Trả **`Integer`**; có thể unbox khi gán vào `int` |
| “Mọi `valueOf` đều trả wrapper.” | `String.valueOf` trả **`String`** |
| “`Integer.parseInt("42.0")` ra 42.” | Ném `NumberFormatException` |
| “`Double.parseDouble` chỉ đọc số hữu hạn.” | Có thể nhận `NaN` hoặc `Infinity` |
| “`parseInt(" 42 ")` luôn tự trim.” | Không; nên chuẩn hóa theo hợp đồng |
| “`Integer.parseInt` tự đọc `0xFF` theo base 16.” | Cần xử lý cú pháp/tiền tố hoặc dùng API phù hợp |
| “Gán vào `Integer` khiến `parseInt` đổi kiểu trả về.” | Không; đó là **boxing sau phương thức** |
| “Hai kết quả `valueOf` bằng số thì `==` chắc đúng.” | Không; so wrapper theo **giá trị** bằng `equals` |

## 10. Bài tập tự kiểm tra

1. **Kiểu kết quả:** `Integer.parseInt("7")` và `Integer.valueOf("7")` lần lượt trả kiểu nào?  
   *Đáp án:* `int` và `Integer`.
2. **Số thực:** `Double.parseDouble("2.5")` khác `Double.valueOf("2.5")` ở kiểu trả về thế nào?  
   *Đáp án:* `double` và `Double`.
3. **Overload:** `Integer.parseInt("FF", 16)` và `Integer.valueOf("FF", 16)` cho giá trị và kiểu nào?  
   *Đáp án:* Cùng giá trị 255, lần lượt kiểu `int` và `Integer`.
4. **Ngữ cảnh gán:** `Integer n = Integer.parseInt("8");` có biên dịch không?  
   *Đáp án:* Có, nhờ boxing `int -> Integer`.
5. **Dữ liệu sai:** `Integer.parseInt("8.0")` có hợp lệ không?  
   *Đáp án:* Không, ném `NumberFormatException`.
6. **Boolean:** `Boolean.parseBoolean("YES")` ném ngoại lệ hay cho false?  
   *Đáp án:* Cho `false`. Muốn từ chối “YES” phải tự validation.
7. **NaN:** `Double.parseDouble("NaN")` thất bại hay thành công?  
   *Đáp án:* Thành công, trả `double` NaN; `Double.isNaN(...)` trả true.

## Checklist ghi nhớ

- [ ] `parseInt` / `parseLong` / `parseDouble` trả về **primitive** tương ứng.
- [ ] Wrapper `valueOf` trả về **đối tượng wrapper** tương ứng.
- [ ] `String.valueOf` trả về **String**, không phải wrapper số.
- [ ] Boxing/unboxing xảy ra **sau** lời gọi phương thức nếu ngữ cảnh cần.
- [ ] Phân biệt cú pháp, miền giá trị, radix và exception khi parsing.
- [ ] Phân tích `double` thành công không bảo đảm giá trị hữu hạn hoặc chính xác tuyệt đối.
- [ ] Chuẩn hóa whitespace và validate null theo yêu cầu ứng dụng.
- [ ] Không dùng cast để thay parsing và không dùng `==` để so giá trị wrapper.

**Kết luận:** Khi đọc `"42"`, hãy chọn API theo **kiểu kết quả cần sử dụng**: `Integer.parseInt` cho `int`, `Integer.valueOf` cho `Integer`. Tương tự, `Double.parseDouble` cho `double` và `Double.valueOf` cho `Double`. Cùng tên `valueOf` ở lớp khác có thể trả loại hoàn toàn khác, vì thế luôn xem **lớp khai báo + chữ ký phương thức + ngữ cảnh boxing/unboxing**.
