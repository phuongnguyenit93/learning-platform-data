# Dùng valueOf thay cho constructor wrapper lỗi thời trong Java

> **Java core – numbers · Number và wrapper**  
> **Mục tiêu:** Thay đúng các lời gọi constructor wrapper đã lỗi thời bằng phương thức `valueOf`, phân biệt `valueOf` với `parseXxx` và autoboxing, hiểu tại sao không được dựa vào danh tính đối tượng wrapper, đồng thời tránh lỗi khi parse, so sánh và unboxing.

## 1. Vấn đề: wrapper không nên được tạo bằng constructor kiểu cũ

Java có các **kiểu nguyên thủy** (*primitive*) dùng để lưu số và giá trị logic/ký tự, cùng các **wrapper class** là đối tượng tương ứng:

| Primitive | Wrapper | Phương thức tạo từ primitive |
| --- | --- | --- |
| `byte` | `Byte` | `Byte.valueOf(byte)` |
| `short` | `Short` | `Short.valueOf(short)` |
| `int` | `Integer` | `Integer.valueOf(int)` |
| `long` | `Long` | `Long.valueOf(long)` |
| `float` | `Float` | `Float.valueOf(float)` |
| `double` | `Double` | `Double.valueOf(double)` |
| `char` | `Character` | `Character.valueOf(char)` |
| `boolean` | `Boolean` | `Boolean.valueOf(boolean)` |

Trước đây có thể gặp cú pháp:

```java
// Cách cũ: tránh dùng trong mã nguồn Java hiện đại.
// Integer boxed = new Integer(42);
// Long count = new Long(100L);
// Double rate = new Double(2.5);
// Boolean enabled = new Boolean(true);
```

Các **constructor công khai** của nhóm wrapper này đã bị đánh dấu **deprecated for removal** từ Java 9; với Java 17, mã dùng chúng có thể phát sinh cảnh báo biên dịch. Việc *deprecated* **không có nghĩa** constructor đã biến mất trong mọi JDK: mã cũ có thể vẫn biên dịch/chạy ở một số phiên bản, nhưng cách viết đó không còn được khuyến nghị và không nên dùng cho mã mới.

Cách viết được khuyến nghị:

```java
Integer boxed = Integer.valueOf(42);
Long count = Long.valueOf(100L);
Double rate = Double.valueOf(2.5);
Boolean enabled = Boolean.valueOf(true);
```

**Lý do chính:**

1. `valueOf` là **static factory method** phù hợp với quy ước API hiện đại.
2. Phương thức factory **có thể tái sử dụng** wrapper đã có sẵn thay vì bắt buộc tạo một đối tượng mới trong mọi lần gọi.
3. Wrapper là các **value-based class**: điều quan trọng là **giá trị được bọc**, không phải identity tham chiếu hoặc việc khóa trên đối tượng.
4. Cách viết này tránh phụ thuộc vào constructor đang được đánh dấu để loại bỏ trong tương lai.

**Kết luận ngắn:** Nếu thật sự cần một đối tượng `Integer`, dùng `Integer.valueOf(42)` hoặc autoboxing khi thích hợp; **không** dùng `new Integer(42)`.

## 2. Wrapper dùng để làm gì nếu đã có primitive?

Primitive thường đơn giản và hiệu quả cho số học:

```java
int quantity = 42;
double price = 19.5;
boolean available = true;
```

Nhưng một số API và cấu trúc dữ liệu cần **đối tượng tham chiếu**:

```java
import java.util.List;

List<Integer> counts = List.of(1, 2, 3);
Integer optionalCount = null;
Number number = Integer.valueOf(42);
```

Các tình huống thông dụng là:

- Tham số kiểu của collection/generic: `List<Integer>`, `Map<String, Long>`; Java generics không dùng trực tiếp `List<int>`.
- API nhận `Object`, `Number` hoặc interface liên quan thay vì primitive.
- Biểu diễn trạng thái *chưa có giá trị* bằng tham chiếu `null`, nếu hợp đồng dữ liệu cho phép.
- Thao tác với các phương thức của lớp như `Integer.compare`, `Integer.toHexString`, `Double.isFinite` hoặc `intValue()`.

Các wrapper số `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` là con của `java.lang.Number`. `Character` và `Boolean` **không** kế thừa `Number`; vì vậy đừng coi mọi wrapper đều là một `Number`.

Wrapper đều là đối tượng **bất biến** (*immutable*): không thể đổi giá trị bên trong một `Integer` đã tạo. Gán một wrapper khác vào biến chỉ khiến biến tham chiếu tới giá trị mới.

## 3. valueOf là factory method, không phải constructor

So sánh hai cách thể hiện ý định:

```java
// Cách cũ — constructor bị deprecated:
 // Integer oldStyle = new Integer(42);

// Cách mới — static factory:
Integer modern = Integer.valueOf(42);
```

Constructor kiểu `new Integer(42)` yêu cầu tạo một đối tượng mới. Trong khi đó `Integer.valueOf(42)` trả một tham chiếu tới `Integer` có giá trị 42; việc tham chiếu này trỏ đến đối tượng được tái sử dụng hay đối tượng vừa tạo **không phải điều mà chương trình nghiệp vụ nên phụ thuộc**.

Một số factory có quy tắc cache rõ ràng. Ví dụ trong Java, `Integer.valueOf(int)` bảo đảm cache các giá trị **từ −128 đến 127**; implementation có thể cache thêm ngoài miền đó. Nhưng nên nhớ:

- **Cache là chi tiết tối ưu/đặc tả factory, không phải cách so sánh số.**
- Không suy luận rằng mọi giá trị `Integer.valueOf(1000)` đều có cùng đối tượng hoặc luôn khác đối tượng.
- Không dùng danh tính wrapper để đại diện cho các trạng thái khác nhau.
- Không khóa (`synchronized`) trên wrapper: các wrapper được xem là **value-based** và những thao tác dựa trên identity có thể tạo rủi ro đồng bộ.

Đặc biệt, **`valueOf` không phải phương pháp “ép kiểu để được đối tượng mới mỗi lần”**. Nếu chương trình của bạn cần identity riêng, hãy tạo một lớp đối tượng nghiệp vụ riêng, thay vì cố dùng wrapper làm token định danh.

## 4. Cách thay từng constructor lỗi thời

Khi sửa mã Java cũ, có thể đối chiếu theo bảng sau:

| Constructor cũ (tránh dùng) | Cách thay đề xuất | Lưu ý |
| --- | --- | --- |
| `new Byte((byte) 7)` | `Byte.valueOf((byte) 7)` | Kiểu `byte` có miền −128..127 |
| `new Short((short) 300)` | `Short.valueOf((short) 300)` | Không đổi quy tắc ép hẹp |
| `new Integer(42)` | `Integer.valueOf(42)` | Không dùng `==` để so giá trị |
| `new Long(42L)` | `Long.valueOf(42L)` | Kết quả là wrapper `Long` |
| `new Float(1.25f)` | `Float.valueOf(1.25f)` | Dùng hậu tố `f` cho literal `float` |
| `new Double(1.25)` | `Double.valueOf(1.25)` | Nhận primitive `double` |
| `new Character('A')` | `Character.valueOf('A')` | Nhận một `char`, không nhận chuỗi |
| `new Boolean(true)` | `Boolean.valueOf(true)` | Có thể trả hằng `Boolean.TRUE` |

Các constructor từ **chuỗi** cũng nên thay bằng factory hoặc parser tương ứng:

```java
// Tránh:
// Integer n = new Integer("123");
// Long id = new Long("123456789");
// Double d = new Double("1.25");
// Boolean flag = new Boolean("true");

// Thay bằng:
Integer n = Integer.valueOf("123");
Long id = Long.valueOf("123456789");
Double d = Double.valueOf("1.25");
Boolean flag = Boolean.valueOf("true");
```

Không có cách thay constructor wrapper bằng việc tự viết `new Integer(Integer.parseInt(text))`: bước `new` vẫn tạo đối tượng qua API deprecated. Khi cần wrapper, chọn thẳng `Integer.valueOf(text)`.

## 5. valueOf với giá trị primitive và với chuỗi là hai trường hợp khác nhau

`Integer.valueOf` có nhiều overload:

```java
Integer fromInt = Integer.valueOf(123);        // primitive int -> wrapper Integer
Integer fromText = Integer.valueOf("123");    // String -> wrapper Integer
Integer fromHex = Integer.valueOf("FF", 16);  // String cơ số 16 -> Integer 255
```

Trong ví dụ thứ hai và thứ ba, phương thức phải **phân tích cú pháp chuỗi**. Chuỗi không hợp lệ có thể ném `NumberFormatException`. Trong ví dụ đầu, kiểu đầu vào đã là primitive hợp lệ nên không có bước parse chuỗi.

Một số ví dụ wrapper khác:

```java
Byte byteValue = Byte.valueOf("127");
Short shortValue = Short.valueOf("-123");
Long longValue = Long.valueOf("9000000000");
Float floatValue = Float.valueOf("1.25");
Double doubleValue = Double.valueOf("1.25");
Boolean boolValue = Boolean.valueOf("TrUe");
Character charValue = Character.valueOf('J');
```

**Không có** `Character.valueOf(String)` nhận một chuỗi bất kỳ. `Character.valueOf` nhận một `char`, tức một đơn vị mã UTF-16. Nếu yêu cầu xử lý ký tự Unicode ngoài BMP có thể cần **code point** bằng `int` hoặc `String`, không thể tùy tiện lấy phần tử `charAt(0)` rồi coi là cả ký tự.

## 6. valueOf khác parseXxx ở kiểu trả về

Với chuỗi số nguyên:

```java
String text = "42";

int primitive = Integer.parseInt(text); // int
Integer wrapper = Integer.valueOf(text); // Integer
```

Với chuỗi số thực:

```java
double primitive = Double.parseDouble("1.25"); // double
Double wrapper = Double.valueOf("1.25");        // Double
```

Bảng ghi nhớ:

| Cách gọi | Đầu vào | Kiểu kết quả |
| --- | --- | --- |
| `Integer.parseInt("42")` | String | `int` |
| `Integer.valueOf("42")` | String | `Integer` |
| `Long.parseLong("42")` | String | `long` |
| `Long.valueOf("42")` | String | `Long` |
| `Double.parseDouble("1.25")` | String | `double` |
| `Double.valueOf("1.25")` | String | `Double` |
| `Float.parseFloat("1.25")` | String | `float` |
| `Float.valueOf("1.25")` | String | `Float` |
| `Boolean.parseBoolean("true")` | String | `boolean` |
| `Boolean.valueOf("true")` | String | `Boolean` |

Về lựa chọn:

- Cần làm số học thông thường, biến có kiểu primitive và không yêu cầu đối tượng: ưu tiên **`parseXxx`** rồi dùng primitive.
- API/collection yêu cầu wrapper: dùng **`valueOf`** để nhận đúng kiểu đối tượng.
- Đã có primitive nhưng API cần wrapper: có thể dùng **`valueOf(primitive)`** hoặc **autoboxing**.
- Đã có wrapper và cần primitive: dùng **unboxing** hoặc các phương thức như `intValue()`, nhưng phải xử lý khả năng `null`.

Dù `parseXxx` và `valueOf(String)` có cùng cách phân tích chuỗi tương ứng, chúng không thể thay thế nhau một cách máy móc khi **kiểu trả về** là một phần của chữ ký API hoặc hợp đồng nullability.

## 7. Chuỗi cơ số và decode: tránh hiểu lầm 0x

Nếu cần parse cơ số khác 10:

```java
Integer decimal = Integer.valueOf("255");       // 255
Integer hex = Integer.valueOf("FF", 16);         // 255
Integer binary = Integer.valueOf("11111111", 2); // 255
```

Đối với overload có tham số radix, chuỗi truyền vào thường chỉ chứa chữ số phù hợp; **không** mặc định nhận tiền tố `0x`:

```java
// Integer.valueOf("0xFF", 16); // NumberFormatException
Integer prefixed = Integer.decode("0xFF"); // 255
```

`Integer.decode` có quy tắc riêng nhận tiền tố như `0x` hoặc `#` cho hex, `0` dẫn đầu cho octal; không dùng nó làm parser decimal cho dữ liệu người dùng nếu việc một số bắt đầu bằng 0 bị diễn giải là octal là ngoài ý muốn.

Đối với số nguyên âm, parser có quy tắc dấu:

```java
System.out.println(Integer.valueOf("-42"));   // -42
System.out.println(Integer.valueOf("-2A", 16)); // -42
```

Khi parse dữ liệu không đáng tin, giới hạn độ dài, validate radix và ghi rõ cách diễn giải dấu. Chuỗi quá lớn so với miền `int`/`long` ném `NumberFormatException`; `valueOf` **không mở rộng miền giá trị**. Nếu thực sự cần số nguyên ngoài miền `long`, dùng `BigInteger` theo yêu cầu của bài toán, không coi `Integer.valueOf` là arbitrary precision.

## 8. Boolean.valueOf: khác với parser số học nghiêm ngặt

`Boolean.valueOf(String)` và `Boolean.parseBoolean(String)` có hành vi quan trọng:

- Nếu chuỗi bằng `"true"` theo so sánh **không phân biệt hoa/thường**, kết quả là true.
- Các chuỗi khác, ví dụ `"yes"`, `"1"`, `"falsee"`, cho false thay vì ném `NumberFormatException`.

```java
System.out.println(Boolean.valueOf("TrUe")); // true
System.out.println(Boolean.valueOf("yes"));  // false
System.out.println(Boolean.parseBoolean("1")); // false
```

Vì vậy không nên dùng `Boolean.valueOf(text)` làm **bộ kiểm tra định dạng boolean nghiêm ngặt** khi API chỉ cho phép chính xác hai giá trị `"true"` và `"false"`. Nếu đầu vào có thể sai chính tả, một kết quả false im lặng dễ che giấu lỗi dữ liệu.

Ví dụ cách kiểm tra trước khi parse:

```java
static boolean parseStrictBoolean(String text) {
    if ("true".equalsIgnoreCase(text)) return true;
    if ("false".equalsIgnoreCase(text)) return false;
    throw new IllegalArgumentException("Expected true or false");
}
```

Đây là **phương thức minh họa** cần đặt trong một class nếu muốn biên dịch/chạy. Nó cố ý không tự chấp nhận khoảng trắng hoặc từ đồng nghĩa như `yes/no`; mở rộng quy tắc tùy theo hợp đồng API.

## 9. Autoboxing và unboxing: lúc nào Java tự xử lý?

**Autoboxing** là phép chuyển primitive sang wrapper được hỗ trợ bởi ngôn ngữ:

```java
Integer count = 42;     // boxing int -> Integer
Long length = 100L;     // boxing long -> Long
Boolean enabled = true; // boxing boolean -> Boolean
```

Cùng ý nghĩa giá trị với cách viết tường minh:

```java
Integer count = Integer.valueOf(42);
```

Khi code rõ ràng về kiểu, autoboxing thường ngắn gọn; khi muốn thể hiện quá trình tạo đối tượng, parse chuỗi hoặc chọn đúng overload, `valueOf` thích hợp hơn. Cả hai cách đều **không phải lời hứa cấp phát đối tượng mới**.

**Unboxing** lấy primitive từ wrapper:

```java
Integer boxed = Integer.valueOf(42);
int primitive = boxed;          // unboxing
int explicit = boxed.intValue(); // cùng giá trị
```

### Rủi ro null unboxing

```java
Integer maybe = null;
// int wrong = maybe; // biên dịch được, nhưng ném NullPointerException khi chạy
```

Một kiểu wrapper cho phép `null` ở vị trí tham chiếu, trong khi primitive không thể mang `null`. Để tránh lỗi, **kiểm tra null trước khi unbox** hoặc thiết kế API dùng một kiểu mô tả sự vắng mặt rõ ràng.

```java
Integer maybe = null;
int safeDefault = maybe == null ? 0 : maybe.intValue();
```

Lựa chọn giá trị mặc định 0 là **quyết định nghiệp vụ**, không phải quy tắc tự động của Java. Trong nhiều ứng dụng, phân biệt 0 với “không có giá trị” là bắt buộc; khi đó không thay `null` thành 0 một cách âm thầm.

## 10. Wrapper cache và phép ==: lỗi đặc biệt dễ gặp

Với primitive:

```java
int a = 1000;
int b = 1000;
System.out.println(a == b); // true: so sánh giá trị int
```

Với wrapper:

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
System.out.println(a.equals(b)); // true: cùng giá trị int 1000
```

Nhưng `a == b` khi hai vế đều là wrapper **so sánh tham chiếu**, không phải giá trị số học. Kết quả có thể phụ thuộc việc factory tái sử dụng đối tượng. **Không dựa vào biểu thức này để kiểm tra nội dung số nguyên**.

Cache của `Integer.valueOf` bao gồm bắt buộc miền `−128..127`. Ví dụ:

```java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);
System.out.println(a == b); // true với miền cache bắt buộc
```

Đây chỉ là minh họa khả năng tái sử dụng, **không phải mẫu code so sánh nên dùng**. Để so sánh nội dung:

```java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first.equals(second));    // true
System.out.println(first.compareTo(second)); // 0
```

Khi so sánh với primitive, Java có thể thực hiện unboxing:

```java
Integer boxed = Integer.valueOf(1000);
System.out.println(boxed == 1000); // true: unbox rồi so sánh số
```

Cần đặc biệt đề phòng nếu `boxed` có thể `null`: biểu thức `boxed == 1000` ném `NullPointerException` khi đánh giá.

**Quy tắc thực hành:** wrapper ↔ wrapper dùng `equals` hoặc `compareTo` cho giá trị; primitive ↔ primitive dùng `==`; nếu có `null`, kiểm tra trước hoặc dùng `Objects.equals(a,b)` cho phép so sánh tham chiếu null-safe.

## 11. Collection/generic: wrapper là cần thiết nhưng đừng boxing vô ích

`List<Integer>` hoạt động với đối tượng:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>();
numbers.add(10);               // autoboxing
numbers.add(Integer.valueOf(20)); // factory tường minh

int sum = 0;
for (Integer n : numbers) {
    sum += n; // unboxing
}
System.out.println(sum); // 30
```

Lưu ý danh sách này **có thể** chứa `null` nếu API cho phép; khi đó `sum += n` gây `NullPointerException`.

Về hiệu năng, các thao tác boxing/unboxing liên tục trong vòng lặp nhiều phần tử có thể tạo overhead và cấp phát tùy giá trị, compiler/JIT và cách sử dụng. Trong khối tính toán số học thuần túy, ưu tiên accumulator primitive:

```java
long total = 0L;
for (int i = 0; i < 1_000_000; i++) {
    total += i; // số học long, không cần bọc mỗi bước
}
Long boxedTotal = Long.valueOf(total); // chỉ bọc tại ranh giới API
```

Đừng biến mọi phép toán thành chuỗi gọi `Integer.valueOf` chỉ vì constructor cũ bị deprecated. Mục tiêu là **thay đúng cách tạo wrapper khi cần**, không phải bắt buộc mọi biến số học đều trở thành wrapper.

## 12. Các kiểu Float, Double: valueOf không chữa sai số nhị phân

`Float.valueOf` và `Double.valueOf` trả wrapper cho giá trị dấu phẩy động:

```java
Float f = Float.valueOf(1.25f);
Double d = Double.valueOf(0.1);
```

Dù `valueOf` là factory được khuyến nghị, nó **không làm số 0.1 trở thành chính xác thập phân**:

```java
Double wrapped = Double.valueOf(0.1);
System.out.println(Double.toHexString(wrapped)); // 0x1.999999999999ap-4
```

`Double.valueOf("0.1")` sẽ parse chuỗi thập phân và tạo wrapper chứa giá trị `double` gần 0.1; đây vẫn là số học nhị phân hữu hạn. Đối với bài toán tiền/decimal exact có yêu cầu scale và rounding, cân nhắc `BigDecimal` tạo từ chuỗi (ví dụ `new BigDecimal("0.1")`), không dùng `Double.valueOf` như giải pháp chính xác tuyệt đối.

Với `Double`, phương thức `equals` có ngữ nghĩa theo các bit chuẩn hóa để xử lý một số trường hợp đặc biệt như NaN và signed zero; nó **không hoàn toàn trùng** với phép so sánh số học `==` trên hai primitive. Khi làm việc với NaN, ±Infinity hoặc ±0.0, chọn quy tắc so sánh đúng hợp đồng nghiệp vụ.

## 13. Các lỗi parse: không tự giả định valueOf chấp nhận mọi đầu vào

Với `Integer.valueOf(String)` và tương tự cho số nguyên:

```java
Integer good = Integer.valueOf("42");

// NumberFormatException:
// Integer bad = Integer.valueOf("42abc");
// Integer tooLarge = Integer.valueOf("2147483648");
// Integer withSpaces = Integer.valueOf(" 42 ");
```

Đây là những lỗi **dữ liệu đầu vào**, không phải lý do quay lại dùng constructor deprecated. Cần xác định quy tắc: có cho phép khoảng trắng trước/sau, dấu cộng, dấu âm, prefix hay giới hạn miền số không?

Nếu cho phép khoảng trắng ASCII đầu/cuối, có thể chuẩn hóa rõ ràng:

```java
static int parseIntWithTrim(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Missing integer");
    }
    return Integer.parseInt(raw.trim());
}
```

Đây là phương thức minh họa. `trim()` chỉ là lựa chọn một tập ký tự whitespace theo đặc tả `String`; nếu cần quy tắc Unicode rộng hơn, phải định nghĩa parser phù hợp. Không tự động `trim` dữ liệu định danh hoặc chữ ký số nếu khoảng trắng là một phần của hợp đồng dữ liệu.

### Giữ đúng loại ngoại lệ

- `Integer.valueOf("invalid")` có thể ném `NumberFormatException`.
- `Integer.valueOf(1000)` nhận primitive hợp lệ nên không parse chuỗi.
- Unboxing từ wrapper `null` gây `NullPointerException`.
- `Boolean.valueOf("invalid")` **không** ném `NumberFormatException`; nó trả `false`, nên phải validate riêng nếu nghiêm ngặt.

Không “xử lý lỗi” bằng cách nuốt mọi ngoại lệ rồi trả 0 hoặc false nếu giá trị đó cũng có ý nghĩa nghiệp vụ, vì sẽ khó phân biệt dữ liệu sai với giá trị hợp lệ.

## 14. Chương trình Java 17+ chạy độc lập

Tạo tệp **`WrapperValueOfDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class WrapperValueOfDemo {
    private static boolean parseStrictBoolean(String text) {
        if ("true".equalsIgnoreCase(text)) return true;
        if ("false".equalsIgnoreCase(text)) return false;
        throw new IllegalArgumentException("Expected true or false");
    }

    public static void main(String[] args) {
        Integer boxed = Integer.valueOf(42);
        int parsed = Integer.parseInt("42");
        Integer parsedWrapper = Integer.valueOf("42");

        System.out.println("boxed = " + boxed);
        System.out.println("parsed primitive = " + parsed);
        System.out.println("parsed wrapper = " + parsedWrapper);
        System.out.println("hex = " + Integer.valueOf("FF", 16));
        System.out.println("prefixed hex = " + Integer.decode("0xFF"));

        Integer a = Integer.valueOf(1000);
        Integer b = Integer.valueOf(1000);
        System.out.println("value equals = " + a.equals(b));
        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("null-safe equals = "
                + Objects.equals(a, b));

        Integer cachedA = Integer.valueOf(127);
        Integer cachedB = Integer.valueOf(127);
        System.out.println("cached reference = " + (cachedA == cachedB));

        System.out.println("boolean TRUE = "
                + Boolean.valueOf("TrUe"));
        System.out.println("boolean yes = "
                + Boolean.valueOf("yes"));

        try {
            parseStrictBoolean("yes");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict boolean: rejected");
        }

        List<Integer> numbers = new ArrayList<>();
        numbers.add(10); // autoboxing
        numbers.add(Integer.valueOf(20));
        int sum = 0;
        for (Integer value : numbers) {
            sum += value; // unboxing
        }
        System.out.println("list sum = " + sum);

        Integer absent = null;
        try {
            int value = absent;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: rejected");
        }

        try {
            Integer.valueOf("2147483648");
        } catch (NumberFormatException ex) {
            System.out.println("int parse range: rejected");
        }

        System.out.println("double hex = "
                + Double.toHexString(Double.valueOf(0.1)));
    }
}
```

Chạy ở thư mục chứa tệp:

```bash
javac WrapperValueOfDemo.java
java WrapperValueOfDemo
```

**Đầu ra chuẩn:**

```text
boxed = 42
parsed primitive = 42
parsed wrapper = 42
hex = 255
prefixed hex = 255
value equals = true
compareTo = 0
null-safe equals = true
cached reference = true
boolean TRUE = true
boolean yes = false
strict boolean: rejected
list sum = 30
null unboxing: rejected
int parse range: rejected
double hex = 0x1.999999999999ap-4
```

**Giải thích theo nhóm:**

1. `valueOf(42)` trả wrapper, `parseInt("42")` trả primitive, còn `valueOf("42")` parse chuỗi rồi trả wrapper.
2. `valueOf("FF",16)` dùng radix; `decode("0xFF")` có quy tắc nhận tiền tố.
3. `equals`, `compareTo`, `Objects.equals` thực hiện các cách so sánh nội dung hoặc null-safe, không dựa vào reference identity.
4. Hai giá trị `127` được cache theo hợp đồng của `Integer.valueOf`; ví dụ minh họa cache chứ **không khuyến khích dùng `==`** cho wrapper.
5. `Boolean.valueOf("yes")` trả false; parser nghiêm ngặt tự viết thì từ chối.
6. `List<Integer>` dùng autoboxing khi thêm primitive và unboxing khi cộng dồn.
7. Unboxing `null` ném `NullPointerException`; chuỗi ngoài miền `int` ném `NumberFormatException`.
8. `Double.valueOf(0.1)` vẫn chứa giá trị nhị phân của `double`, không giải quyết sai số biểu diễn.

## 15. Checklist thay constructor trong codebase

Khi gặp `new Integer(...)`, `new Long(...)` hoặc constructor wrapper tương tự, làm lần lượt:

1. **Xác định kiểu đích**: API cần primitive hay wrapper? Nếu cần `int`, `Integer.parseInt` thường tự nhiên hơn `Integer.valueOf`.
2. **Xác định nguồn**: primitive hay chuỗi? Dùng overload `valueOf(primitive)` hoặc `valueOf(String)` cho đúng.
3. **Thay constructor** bằng `valueOf` hoặc autoboxing khi thích hợp; **không giữ `new` chỉ để tạo đối tượng mới**.
4. **Không dựa vào identity**: thay so sánh wrapper `==` bằng `equals`/`compareTo`, hoặc kiểm tra null và so sánh primitive.
5. **Rà soát nullability**: nếu wrapper có thể `null`, xem mọi phép unboxing, tính toán, so sánh với primitive hoặc dùng collection.
6. **Rà soát parser**: đầu vào có thể sai cú pháp, ngoài miền, khác radix, có khoảng trắng, boolean viết tùy ý?
7. **Rà soát hiệu năng**: tránh boxing/unboxing vô ích trong vòng lặp nặng, dùng primitive cho phần tính thuần túy.
8. **Kiểm tra giới hạn kiểu**: `Integer.valueOf` không lưu giá trị ngoài `int`; `Double.valueOf` không tạo decimal exact.
9. **Không dùng wrapper để khóa đồng bộ** hoặc làm identity token; chuyển sang đối tượng khóa được thiết kế riêng nếu cần.
10. **Biên dịch trên phiên bản Java đích** và xử lý cảnh báo deprecated-for-removal thực chất, không bỏ qua do chương trình “vẫn chạy”.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Constructor wrapper đã deprecated nghĩa là không thể biên dịch trong Java 17” | Có thể vẫn biên dịch với cảnh báo; tránh dùng vì deprecated for removal |
| “`valueOf` luôn cấp phát đối tượng mới” | Factory có thể tái sử dụng đối tượng/cache |
| “`valueOf` luôn cache mọi giá trị” | Chỉ một số miền/hành vi được bảo đảm; không dựa vào identity |
| “`Integer.valueOf("42")` và `Integer.parseInt("42")` trả cùng kiểu” | Một bên trả `Integer`, bên kia trả `int` |
| “`Integer.valueOf("0xFF",16)` giống `Integer.decode("0xFF")`” | Overload radix không tự nhận prefix `0x`; `decode` có quy tắc riêng |
| “Boolean.valueOf("yes") sẽ báo lỗi” | Nó trả false; cần parser nghiêm ngặt nếu muốn từ chối |
| “Hai wrapper số cùng giá trị thì `==` luôn true” | `==` với hai tham chiếu so identity; dùng `equals`/`compareTo` |
| “Autoboxing loại bỏ mọi chi phí” | Boxing/unboxing có thể tạo overhead, đặc biệt trong vòng lặp |
| “Wrapper mặc định null unbox thành 0” | Unboxing `null` ném `NullPointerException` |
| “`Double.valueOf("0.1")` giữ chính xác 1/10” | Nó trả `double` nhị phân gần 0.1, không phải BigDecimal |
| “Mọi wrapper đều kế thừa Number” | `Character` và `Boolean` không kế thừa `Number` |
| “Có thể dùng Integer wrapper làm khóa vì cache giúp chia sẻ” | Wrapper là value-based; không dùng để đồng bộ hoặc dựa vào identity |

## 17. Bài tập có lời giải

**Bài 1.** Viết lại `new Integer(123)` và `new Double("2.5")` theo API được khuyến nghị.  
**Lời giải:** `Integer.valueOf(123)` và `Double.valueOf("2.5")`. Nếu chỉ cần primitive, có thể chọn `123` và `Double.parseDouble("2.5")`.

**Bài 2.** Kiểu trả về của `Integer.parseInt("7")` và `Integer.valueOf("7")` khác nhau thế nào?  
**Lời giải:** lần lượt `int` và `Integer`. Các chữ số được parse tương ứng nhưng kết quả có dạng primitive hay wrapper khác nhau.

**Bài 3.** `Integer.valueOf("FF",16)` cho giá trị gì? Còn `Integer.valueOf("0xFF",16)`?  
**Lời giải:** 255; cách thứ hai ném `NumberFormatException` do prefix. `Integer.decode("0xFF")` là phương án có nhận prefix.

**Bài 4.** Có nên dùng `Integer.valueOf(1000) == Integer.valueOf(1000)` để xác định bằng giá trị?  
**Lời giải:** Không. Dù một implementation có thể cache thêm, `==` trên hai wrapper tham chiếu không phải hợp đồng so sánh số; dùng `equals` hoặc `compareTo`.

**Bài 5.** `Boolean.valueOf("YES")` cho gì, và nên xử lý thế nào nếu chỉ chấp nhận `true/false`?  
**Lời giải:** Cho false. Nếu yêu cầu từ chối mọi token không hợp lệ, validate đúng hai giá trị được chấp nhận rồi mới trả boolean hoặc ném lỗi.

**Bài 6.** Điều gì xảy ra với `Integer absent = null; int x = absent;`?  
**Lời giải:** Câu lệnh biên dịch được, nhưng khi unboxing tại runtime nó ném `NullPointerException`. Cần kiểm tra null hoặc thiết kế API rõ trạng thái vắng mặt.

**Bài 7.** Vì sao dùng `Double.valueOf(0.1)` không giúp tính tiền thập phân chính xác?  
**Lời giải:** Nó chỉ bọc một giá trị `double` nhị phân gần 0.1; bài toán decimal exact nên dùng biểu diễn decimal như `BigDecimal` từ chuỗi, kèm quy tắc làm tròn.

**Bài 8.** Vì sao không nên viết `Integer sum=0;` rồi lặp `sum += x` hàng triệu lần nếu chỉ cộng số nguyên?  
**Lời giải:** Biểu thức có thể unbox/rebox mỗi vòng, tạo overhead và cấp phát; dùng primitive accumulator phù hợp miền giá trị rồi chỉ boxing tại nơi cần đối tượng.

**Bài 9.** `Character.valueOf("A")` có biên dịch không?  
**Lời giải:** Không. Phương thức nhận `char`, nên viết `Character.valueOf('A')`. Một `String` có thể chứa nhiều UTF-16 code unit, vì vậy xử lý ký tự Unicode từ chuỗi cần hợp đồng rõ ràng.

**Bài 10.** Dùng `new Long("9000000000")` được thay bằng gì?  
**Lời giải:** `Long.valueOf("9000000000")` nếu API cần wrapper; `Long.parseLong("9000000000")` nếu cần primitive `long`.

**Ghi nhớ:** Wrapper là **đối tượng biểu diễn giá trị**, không phải nơi dựa vào identity. Khi cần wrapper, ưu tiên `valueOf` hoặc autoboxing thay cho constructor deprecated; khi cần primitive từ chuỗi, dùng `parseXxx`. Luôn kiểm soát parse lỗi, null unboxing, kiểu trả về và cách so sánh.
