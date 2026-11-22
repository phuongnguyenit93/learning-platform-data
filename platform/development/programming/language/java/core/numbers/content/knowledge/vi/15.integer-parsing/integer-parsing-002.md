# valueOf(String) khác parse về kiểu kết quả trong Java

## 1. Mục tiêu của bài học

Khi phân tích một chuỗi chữ số thành số nguyên Java, hai cách viết dưới đây trông như nhau:

```java
int number = Integer.parseInt("42");
Integer boxed = Integer.valueOf("42");
```

Cả hai đều đọc ký tự `"42"` thành giá trị số bốn mươi hai, nhưng **kiểu trả về ở thời điểm biên dịch khác nhau**:

- `Integer.parseInt(String)` trả **primitive `int`**.
- `Integer.valueOf(String)` trả **đối tượng wrapper `Integer`**.

Đây là trọng tâm của bài **Java Core — Numbers / Phân tích số nguyên**. Với `Long`, `Short` và `Byte`, các cặp phương thức tương ứng cũng có khác biệt kiểu trả về như vậy. Chọn phương thức không chỉ là sở thích đặt tên: nó ảnh hưởng đến kiểu biến, autoboxing/unboxing, lời gọi phương thức quá tải, API generic/collection, xử lý `null` và cách đọc code.

Sau bài này, bạn có thể:

1. Đọc chữ ký phương thức để phân biệt `parseInt`/`parseLong`/`parseShort`/`parseByte` và `valueOf(String)`.
2. Hiểu vì sao `println` có thể in giống nhau dù kiểu kết quả khác.
3. Chọn cách parse phù hợp cho tính toán primitive hoặc API cần wrapper.
4. Nhận diện khi compiler tự boxing/unboxing và nguy cơ `NullPointerException`.
5. Biết rằng `valueOf(String)` **không nới lỏng** cú pháp chuỗi, phạm vi số, radix hay xử lý ngoại lệ so với phương thức parse tương ứng.
6. Dùng đúng overload `valueOf(primitive)`, `valueOf(String, radix)` và phân biệt `decode`, `parseUnsignedInt`.
7. Viết mã Java 17+ chạy được và dự đoán stdout đúng.

**Nguyên tắc nhanh:** *parse* thường đọc chuỗi thành **giá trị primitive**; *valueOf(String)* đọc cùng nội dung thành **wrapper của giá trị đó**. Đừng kết luận phương thức sau tạo ra một kiểu số mới hoặc tự đổi định dạng dữ liệu.

## 2. Bảng so sánh phương thức trên bốn họ số nguyên

| Nhóm | Parse chuỗi | Kiểu kết quả | valueOf chuỗi | Kiểu kết quả |
| --- | --- | --- | --- | --- |
| `byte` / `Byte` | `Byte.parseByte("127")` | `byte` | `Byte.valueOf("127")` | `Byte` |
| `short` / `Short` | `Short.parseShort("32767")` | `short` | `Short.valueOf("32767")` | `Short` |
| `int` / `Integer` | `Integer.parseInt("42")` | `int` | `Integer.valueOf("42")` | `Integer` |
| `long` / `Long` | `Long.parseLong("3000000000")` | `long` | `Long.valueOf("3000000000")` | `Long` |

Dạng tham số `String` ở bảng trên không bao gồm trường hợp `null`, và giả định chuỗi hợp lệ trong miền kiểu đích. Cả hai cách parse đều có thể ném `NumberFormatException` khi dữ liệu không hợp lệ.

### 2.1. Chữ ký phương thức quyết định kiểu kết quả

Các chữ ký tiêu biểu:

```java
// Tên và kiểu trả về minh họa; đây không phải các khai báo tự viết.
static int Integer.parseInt(String s)
static Integer Integer.valueOf(String s)

static long Long.parseLong(String s)
static Long Long.valueOf(String s)

static short Short.parseShort(String s)
static Short Short.valueOf(String s)

static byte Byte.parseByte(String s)
static Byte Byte.valueOf(String s)
```

Đoạn trên là **cách ghi chữ ký để học**, không phải source code Java hợp lệ đặt trong class. Trình biên dịch biết kiểu trả về từ API tương ứng, không dựa trên chuỗi đầu vào thực tế là bao nhiêu.

Ví dụ `"42"` hoặc `"-42"` đều không làm đổi kiểu trả về; `Integer.parseInt` vẫn trả `int`, còn `Integer.valueOf` vẫn trả `Integer`.

### 2.2. Phân biệt kiểu với văn bản in ra

```java
int primitive = Integer.parseInt("42");
Integer wrapper = Integer.valueOf("42");

System.out.println(primitive); // 42
System.out.println(wrapper);   // 42
```

Hai dòng cùng in `42` vì `println` có overload và cơ chế chuyển sang chuỗi phù hợp. Không thể suy từ stdout rằng `primitive` và `wrapper` có cùng **kiểu compile-time**.

`primitive` lưu một giá trị `int`; `wrapper` là một tham chiếu đến một đối tượng `Integer` mang giá trị `42`. Wrapper là immutable và có thể tham gia các API object-oriented như `equals`, `compareTo` hoặc generic collections.

## 3. Giá trị phân tích gần như giống nhau, kiểu trả về khác nhau

Về ý nghĩa nội dung, `Integer.valueOf(String)` đọc chuỗi như `Integer.parseInt(String)` ở radix 10, sau đó trả về một `Integer` chứa giá trị đã đọc. Đọc tài liệu API có thể hình dung:

```java
Integer result = Integer.valueOf(Integer.parseInt("42"));
```

Về giá trị số, cách viết này tương đương `Integer.valueOf("42")` đối với chuỗi hợp lệ. **Không** hiểu đây là cam kết số lượng đối tượng được cấp phát hoặc identity của đối tượng trong mọi lần gọi: Java/JVM có thể cache wrapper thường dùng.

Với chuỗi không hợp lệ, cả `Integer.parseInt(s)` và `Integer.valueOf(s)` đều **không thể tạo kết quả `int`/`Integer` hợp lệ** và đều ném `NumberFormatException`. `valueOf(String)` không phải một phương thức “parse an toàn trả null” hoặc “bỏ qua lỗi”.

### 3.1. Wrapper không tự có giá trị null khi parse lỗi

```java
// Integer.parseInt("abc");  // NumberFormatException
// Integer.valueOf("abc");   // NumberFormatException
```

Hai lời gọi trên được **comment lại cố ý** để ví dụ minh họa không làm chương trình dừng. Trên một API yêu cầu trả `null` khi dữ liệu sai, bạn phải chủ động thiết kế wrapper method và chính sách lỗi, chẳng hạn trả `OptionalInt`, `Optional<Integer>` hoặc kết quả có trạng thái lỗi.

Không sử dụng `null` để thay thế bất kỳ giá trị không hợp lệ nào một cách tùy tiện, vì `null` có thể làm chương trình ném `NullPointerException` khi được unbox về primitive.

## 4. Boxing và unboxing có thể che giấu sự khác biệt

Java hỗ trợ **autoboxing** từ primitive sang wrapper và **unboxing** từ wrapper về primitive trong các ngữ cảnh được phép.

```java
int a = Integer.parseInt("42");     // int -> int
Integer b = Integer.valueOf("42"); // Integer -> Integer

Integer c = Integer.parseInt("42"); // int -> Integer: boxing
int d = Integer.valueOf("42");     // Integer -> int: unboxing
```

Cả bốn dòng đều có thể biên dịch. Nhưng sự tiện lợi này làm bạn dễ bỏ qua kiểu trả về thực tế:

| Phía phải | Phía trái | Chuyển đổi |
| --- | --- | --- |
| `parseInt(...)` = `int` | `int` | Không boxing |
| `parseInt(...)` = `int` | `Integer` | Boxing |
| `valueOf(...)` = `Integer` | `Integer` | Không unboxing |
| `valueOf(...)` = `Integer` | `int` | Unboxing |

Đừng giải thích `int d = Integer.valueOf("42")` là bằng chứng `valueOf` trả `int`. Chính compiler đã áp dụng unboxing trong phép gán.

### 4.1. Tại sao nên chọn đúng API ngay từ đầu?

Nếu mục tiêu là một vòng lặp tính tổng theo kiểu `int`, `parseInt` truyền tải ý định trực tiếp. Nếu muốn truyền đối tượng vào API `List<Integer>`, `Map<String,Integer>` hoặc một method nhận `Integer`, `valueOf` làm rõ kiểu wrapper được yêu cầu.

Không cần tối ưu mù quáng: JIT có thể tối ưu những phép boxing trong một số ngữ cảnh, và `Integer.valueOf` có thể tái sử dụng object. **Điều quan trọng đầu tiên là kiểu dữ liệu, ngữ nghĩa null, miền giá trị và tính dễ đọc**, thay vì giả định mọi lời gọi `valueOf` chắc chắn tạo allocation mới.

### 4.2. Null là vấn đề của wrapper, không phải một kết quả parse hợp lệ

```java
Integer boxed = null;
// int unboxed = boxed; // NullPointerException lúc chạy
```

Không có giá trị `null` kiểu `int`. Khi một API nhận `Integer` có thể trả `null` để biểu thị “chưa có dữ liệu”, bạn phải kiểm tra trước unboxing:

```java
Integer optional = null;
int fallback = optional == null ? 0 : optional.intValue();
```

Việc dùng `0` làm fallback chỉ phù hợp nếu `0` mang nghĩa mà nghiệp vụ cho phép. Nếu `0` là một giá trị có ý nghĩa riêng, cần giữ trạng thái thiếu dữ liệu ở mô hình dữ liệu thay vì tự động dùng zero.

## 5. Khác biệt có thể quan sát ở quá tải phương thức

Khi code có overload `accept(int)` và `accept(Integer)`, kiểu kết quả của `parseInt`/`valueOf` có thể quyết định phương thức nào được chọn ngay lúc biên dịch.

Lưu thành tệp **`ParseReturnTypes.java`**:

```java
public class ParseReturnTypes {
    static String describe(int value) {
        return "primitive int: " + value;
    }

    static String describe(Integer value) {
        return "wrapper Integer: " + value;
    }

    public static void main(String[] args) {
        int raw = Integer.parseInt("42");
        Integer boxed = Integer.valueOf("42");

        System.out.println(describe(raw));
        System.out.println(describe(boxed));
        System.out.println(raw == boxed);
        System.out.println(boxed.getClass().getSimpleName());
    }
}
```

Chạy:

```bash
javac --release 17 ParseReturnTypes.java
java ParseReturnTypes
```

**Stdout chính xác:**

```text
primitive int: 42
wrapper Integer: 42
true
Integer
```

Diễn giải:

1. `describe(raw)` chọn overload `describe(int)`.
2. `describe(boxed)` chọn overload `describe(Integer)`.
3. Với biểu thức `raw == boxed`, `boxed` được unbox thành `int` để so sánh giá trị primitive; kết quả true.
4. `boxed.getClass().getSimpleName()` trả tên lớp wrapper `Integer`.

**Lưu ý:** nếu `boxed == null`, biểu thức so sánh `raw == boxed` có thể ném `NullPointerException` lúc unboxing. Ví dụ hiện tại không có trường hợp đó vì `Integer.valueOf("42")` trả đối tượng hợp lệ.

## 6. Kiểu trả về ảnh hưởng generic collections

Generic type arguments trong Java không được là primitive:

```java
// List<int> invalid;        // không hợp lệ
java.util.List<Integer> values = new java.util.ArrayList<>();

values.add(Integer.parseInt("12")); // int được boxing thành Integer
values.add(Integer.valueOf("34"));  // đã là Integer
```

Hai lời gọi `values.add` đều có thể chạy. Nhưng:

- Với `parseInt`, một bước boxing có thể diễn ra.
- Với `valueOf`, API nhận thẳng một `Integer`.
- Khi `values.get(0)` được gán sang `int`, có thể xảy ra unboxing.

`valueOf(String)` không “tốt hơn” trong mọi trường hợp. Chọn một cách nhất quán theo vai trò kiểu dữ liệu. Nếu đang làm API có thể thiếu dữ liệu, kiểu `Integer` giúp diễn tả nullability nhưng cũng buộc bạn phải xác định rõ cách xử lý `null`.

### 6.1. `Integer` là object, đừng so identity bằng `==`

```java
Integer x = Integer.valueOf("42");
Integer y = Integer.valueOf("42");

boolean equalValue = x.equals(y); // true
```

`x.equals(y)` so **giá trị `Integer`**. `x == y` nếu cả hai có kiểu `Integer` là phép so **tham chiếu object** và có thể chịu ảnh hưởng bởi cơ chế cache của `valueOf`. Java bảo đảm cache một miền giá trị nhỏ chuẩn đối với một số wrapper; nhưng code ứng dụng không nên phụ thuộc vào identity object để kết luận hai số có cùng giá trị.

Điều đó không mâu thuẫn với `raw == boxed` ở ví dụ trước: khi một toán hạng là primitive `int`, Java áp dụng unboxing/numeric equality. Kiểu của **cả hai** toán hạng quyết định ý nghĩa của toán tử.

## 7. Cùng quy tắc cú pháp chuỗi, cùng miền giá trị

### 7.1. Chuỗi hợp lệ trong hệ thập phân

`Integer.parseInt(String)` và `Integer.valueOf(String)` chấp nhận chuỗi biểu diễn số nguyên **signed decimal** hợp lệ. Ví dụ:

| Input | Kết quả số | Ý nghĩa |
| --- | ---: | --- |
| `"42"` | 42 | Thập phân thông thường |
| `"+42"` | 42 | Dấu cộng ASCII đầu chuỗi được chấp nhận |
| `"-42"` | −42 | Dấu trừ ASCII |
| `"0"` | 0 | Số không |
| `"-0"` | 0 | Số nguyên không có signed zero riêng |
| `"00042"` | 42 | Số 0 đầu chuỗi không tự làm chuyển sang octal |
| `"2147483647"` | 2147483647 | `Integer.MAX_VALUE` |
| `"-2147483648"` | −2147483648 | `Integer.MIN_VALUE` |

Java API cho phép ký tự chữ số được `Character.digit(char,radix)` nhận diện ở radix tương ứng, không chỉ ASCII trong mọi ngữ cảnh. Nhưng API không tự làm bước quốc tế hóa/chuẩn hóa mọi cách viết số theo locale; nếu đầu vào từ người dùng, cần xác định charset, chữ số chấp nhận và ràng buộc bảo mật phù hợp.

### 7.2. Chuỗi không hợp lệ

Những input sau không phải cách viết chuẩn được `Integer.parseInt(s)` hoặc `Integer.valueOf(s)` chấp nhận:

| Input | Vì sao sai |
| --- | --- |
| `""` | Chuỗi trống |
| `" "`, `" 42 "` | Có khoảng trắng; phương thức không tự trim |
| `"42.0"` | Có dấu chấm, không còn là chuỗi số nguyên |
| `"1e3"` | Ký hiệu mũ thuộc số thực, không phải signed integer string |
| `"1_000"` | Dấu gạch dưới chỉ được Java source grammar chấp nhận ở vị trí phù hợp trong literal, không phải ký tự được parser chuỗi này chấp nhận |
| `"0xFF"` | Prefix hex không được tự nhận dạng ở overload radix mặc định |
| `"+"`, `"-"` | Chỉ có dấu, thiếu chữ số |
| `"2147483648"` | Vượt `Integer.MAX_VALUE` |
| `"-2147483649"` | Nhỏ hơn `Integer.MIN_VALUE` |

`Integer.parseInt(null)` và `Integer.valueOf((String)null)` cũng không tạo giá trị hợp lệ; với overload `String`, JDK báo `NumberFormatException`. Với `null` và nhiều overload khác nhau, cần chú ý **chữ ký được chọn** và ngoại lệ được tài liệu hóa cho chữ ký đó.

### 7.3. Chuỗi literal và source literal khác nhau

```java
int a = 1_000;                 // hợp lệ: source code integer literal
// int b = Integer.parseInt("1_000"); // runtime NumberFormatException
```

`0xFF` viết trong mã nguồn Java là một **integer literal hệ 16**. Nhưng `"0xFF"` là **chuỗi chứa ký tự** `0`, `x`, `F`, `F` và không tự được parse theo source literal grammar.

**Đừng giải quyết bằng cách đổi `parseInt` sang `valueOf`:** hai cách có cùng giới hạn cơ bản đối với chuỗi đầu vào. Hãy chọn overload radix hoặc phương thức `decode` có hợp đồng phù hợp.

## 8. Overload có radix: `parseInt(String,int)` và `valueOf(String,int)`

Cả hai họ API cho phép chỉ định hệ cơ số `radix`:

```java
int primitiveHex = Integer.parseInt("FF", 16);       // 255
Integer boxedHex = Integer.valueOf("FF", 16);       // Integer(255)

int primitiveBinary = Integer.parseInt("101010", 2); // 42
Integer boxedBinary = Integer.valueOf("101010", 2); // Integer(42)
```

Sự khác biệt **vẫn chỉ là kiểu trả về**, còn quy tắc chuyển chuỗi trong radix tương ứng là như nhau.

Các API chấp nhận radix hợp lệ từ `Character.MIN_RADIX` (2) đến `Character.MAX_RADIX` (36). Với radix 16, ký tự `A`–`F` biểu thị chữ số 10–15 (không phân biệt hoa/thường trong phạm vi tương ứng). Dấu `+`/`-` ở đầu chuỗi được cho phép với signed parsing; dấu nằm giữa chuỗi thì không.

Các điểm cần chú ý:

- `Integer.parseInt("FF",16)` → 255.
- `Integer.parseInt("-FF",16)` → −255.
- `Integer.valueOf("FF",16)` → wrapper `Integer` giá trị 255.
- `Integer.parseInt("0xFF",16)` **không** tự bỏ tiền tố `0x`.
- `Integer.parseInt("010")` mặc định radix 10 → 10; không suy từ số 0 đầu chuỗi là octal.
- Radix không hợp lệ, ký tự không đúng radix hoặc kết quả ngoài miền `int` đều dẫn tới `NumberFormatException` với overload `String`.

### 8.1. `decode(String)` có nhiệm vụ khác

`Integer.decode("0xFF")` nhận tiền tố `0x` để đọc hex, `Integer.decode("#FF")` cũng có quy ước hex, còn số bắt đầu bằng `0` có thể được hiểu theo octal. Ví dụ:

```java
System.out.println(Integer.parseInt("010")); // 10
System.out.println(Integer.decode("010"));   // 8
System.out.println(Integer.decode("0xFF"));  // 255
```

`decode` trả **`Integer`**, nhưng không đồng nghĩa `valueOf(String)`: khác **ngữ pháp chuỗi chấp nhận**. Tùy yêu cầu dữ liệu, dùng radix tường minh thường ít gây bất ngờ hơn việc tự suy hệ từ prefix hoặc số 0 đầu chuỗi.

`Long.decode`, `Short.decode`, `Byte.decode` cũng có ý nghĩa tương ứng trong phạm vi kiểu của mỗi lớp. Nếu hệ thống nhận mã số theo format giao thức riêng, nên chỉ rõ quy ước (base, prefix, dấu, miền giá trị) thay vì trộn nhiều cách parse ngẫu nhiên.

## 9. Phạm vi giá trị của `Byte`, `Short`, `Integer` và `Long`

Cùng một chuỗi chỉ được nhận nếu giá trị nằm trong **miền của kiểu parse**:

| API | Miền signed |
| --- | --- |
| `Byte.parseByte` / `Byte.valueOf` | −128 đến 127 |
| `Short.parseShort` / `Short.valueOf` | −32768 đến 32767 |
| `Integer.parseInt` / `Integer.valueOf` | −2147483648 đến 2147483647 |
| `Long.parseLong` / `Long.valueOf` | −9223372036854775808 đến 9223372036854775807 |

`Byte.parseByte("128")` ném `NumberFormatException`; `Byte.valueOf("128")` cũng vậy. `Integer.parseInt("3000000000")` vượt phạm vi `int`, nhưng `Long.parseLong("3000000000")` hợp lệ và trả `long`. Với `Long.valueOf("3000000000")`, giá trị đó được bọc vào `Long`.

Đừng giải quyết lỗi miền giá trị bằng cách parse trước qua kiểu quá nhỏ rồi ép sang kiểu lớn: khi `Integer.parseInt` đã báo lỗi vì chuỗi ngoài miền, việc cast kết quả (vốn không được tạo ra) chẳng có tác dụng. **Chọn kiểu phù hợp trước khi parse.**

### 9.1. Trường hợp đặc biệt: phân tích không dấu

`Integer.parseUnsignedInt(String)` đọc giá trị unsigned 32-bit theo dạng chuỗi, nhưng vẫn trả **primitive `int`** chứa cùng mẫu bit 32-bit.

```java
int bits = Integer.parseUnsignedInt("4294967295");
System.out.println(bits);                           // -1
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
```

Giá trị `-1` ở dòng đầu là cách **đọc signed** của bit pattern toàn 1; dòng sau diễn giải **cùng bit pattern** dưới dạng unsigned. Không có primitive `unsigned int` riêng được tạo.

`Integer.valueOf("4294967295")` không thể thay cho `parseUnsignedInt` vì nó dùng signed parsing thông thường và giá trị vượt miền `int` signed. Nếu cần wrapper cho kết quả unsigned bits, viết:

```java
Integer bitsObject = Integer.valueOf(
        Integer.parseUnsignedInt("4294967295"));
```

Đối với 64 bit, `Long.parseUnsignedLong` có ý nghĩa tương tự và trả `long`. Hãy xác định rõ contract của hệ thống trước khi hiển thị hoặc so sánh signed/unsigned.

## 10. Chương trình hoàn chỉnh: giá trị số, wrapper và phạm vi

Lưu thành **`IntegerParsingTypes.java`**:

```java
public class IntegerParsingTypes {
    public static void main(String[] args) {
        int primitive = Integer.parseInt("42");
        Integer boxed = Integer.valueOf("42");

        System.out.println(primitive);
        System.out.println(boxed.getClass().getSimpleName());
        System.out.println(primitive == boxed);

        long large = Long.parseLong("3000000000");
        Long boxedLong = Long.valueOf("3000000000");
        System.out.println(large);
        System.out.println(boxedLong.getClass().getSimpleName());

        System.out.println(Byte.parseByte("127"));
        System.out.println(Short.valueOf("32767"));

        System.out.println(Integer.valueOf("42")
                .equals(Long.valueOf("42")));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 IntegerParsingTypes.java
java IntegerParsingTypes
```

**Stdout chính xác:**

```text
42
Integer
true
3000000000
Long
127
32767
false
```

Phân tích:

1. `primitive` là `int`, `boxed` là `Integer`; cùng một lượng số học `42`.
2. So sánh `primitive == boxed` sẽ unbox `boxed` thành `int`.
3. `Long.parseLong`/`Long.valueOf` có kiểu trả về `long`/`Long`, phù hợp khi `3000000000` vượt miền `int`.
4. `Byte.parseByte` trả `byte`; `Short.valueOf` trả wrapper `Short`.
5. `Integer.valueOf("42").equals(Long.valueOf("42"))` false vì `Integer.equals` chỉ nhận cùng lớp `Integer` với cùng giá trị; việc cùng số 42 không có nghĩa mọi wrapper loại khác nhau đều `equals`.

## 11. Chương trình hoàn chỉnh: radix, decode và unsigned

Lưu thành **`ParsingRadix.java`**:

```java
public class ParsingRadix {
    public static void main(String[] args) {
        System.out.println(Integer.parseInt("FF", 16));
        System.out.println(Integer.valueOf("FF", 16));
        System.out.println(Integer.parseInt("-FF", 16));

        System.out.println(Integer.parseInt("010"));
        System.out.println(Integer.decode("010"));
        System.out.println(Integer.decode("0xFF"));

        int unsignedBits =
                Integer.parseUnsignedInt("4294967295");
        System.out.println(unsignedBits);
        System.out.println(
                Integer.toUnsignedString(unsignedBits));

        System.out.println(Integer.parseInt("+42"));
        System.out.println(Integer.valueOf("-0"));
    }
}
```

Chạy:

```bash
javac --release 17 ParsingRadix.java
java ParsingRadix
```

**Stdout chính xác:**

```text
255
255
-255
10
8
255
-1
4294967295
42
0
```

Phương thức `decode` khác `parseInt` trong cách nhận diện tiền tố và số 0 đầu. Phương thức `parseUnsignedInt` khác `parseInt` trong miền dữ liệu được chấp nhận, **không** đổi kiểu primitive của kết quả. Mọi phép `println` ở đây in giá trị chứ không tự cho thấy kiểu `int` hoặc `Integer` của biểu thức; muốn xác minh kiểu hãy đọc chữ ký hoặc khai báo biến.

## 12. Kiểm tra lỗi parse đúng cách

Với dữ liệu từ nhập liệu, file, API hoặc database, `NumberFormatException` là một phần của hợp đồng. Mã mẫu nên xác định chính sách khi gặp input không hợp lệ, thay vì mặc định trả `0` mà không thông báo.

Lưu thành **`SafeIntegerParsing.java`**:

```java
public class SafeIntegerParsing {
    static void show(String raw) {
        try {
            int result = Integer.parseInt(raw);
            System.out.println("ok: " + result);
        } catch (NumberFormatException ex) {
            System.out.println("invalid: [" + raw + "]");
        }
    }

    public static void main(String[] args) {
        show("42");
        show(" 42 ");
        show("42.0");
        show("1_000");
        show("2147483648");
        show("");
    }
}
```

Chạy:

```bash
javac --release 17 SafeIntegerParsing.java
java SafeIntegerParsing
```

**Stdout chính xác:**

```text
ok: 42
invalid: [ 42 ]
invalid: [42.0]
invalid: [1_000]
invalid: [2147483648]
invalid: []
```

Có thể thay `Integer.parseInt(raw)` bằng `Integer.valueOf(raw)` rồi gán kết quả cho `Integer`; **các input sai vẫn sai**. Việc catch ngoại lệ trong ví dụ nhằm làm rõ ranh giới input hợp lệ/không hợp lệ, không phải khuyến nghị âm thầm nuốt lỗi trong ứng dụng thực tế.

### 12.1. Khi nào nên `trim` hoặc `strip`?

Nếu hợp đồng **cho phép khoảng trắng ở hai đầu**, chuẩn hóa một cách có chủ ý trước khi parse:

```java
String input = " 42 ";
int number = Integer.parseInt(input.strip()); // 42
```

Nếu hợp đồng cấm khoảng trắng, **đừng chuẩn hóa rồi lặng lẽ nhận input sai**. `strip` xử lý Unicode whitespace theo `Character.isWhitespace`, không đồng nghĩa mọi ký tự trông như khoảng trắng đều bị xóa. `trim` có quy tắc khác; chọn cách dựa trên định dạng dữ liệu.

Nếu chuỗi có hàng nghìn phân cách, ký hiệu tiền tệ hoặc số được định dạng theo locale, `parseInt`/`valueOf` không phải parser định dạng tổng quát. Cần định nghĩa format hoặc dùng công cụ thích hợp có kiểm soát.

### 12.2. Tránh dùng exception cho mọi dòng trong dữ liệu khối lớn mà không đánh giá

Với nguồn dữ liệu sạch đã validate, gọi parse trực tiếp là hợp lý. Với dữ liệu ngoài có thể lỗi nhiều, dùng một lớp validation và trả kết quả rõ trạng thái; cân nhắc chi phí tạo exception nếu parse hàng triệu bản ghi lỗi. Tuy nhiên, **đừng tự viết parser số tùy tiện** chỉ để tránh ngoại lệ khi không thật sự cần hiệu năng riêng.

## 13. Overload `valueOf` không chỉ nhận String

Một nguyên nhân gây nhầm là tên `valueOf` có nhiều overload:

```java
Integer fromNumber = Integer.valueOf(42);   // valueOf(int) -> Integer
Integer fromText = Integer.valueOf("42");  // valueOf(String) -> Integer
Integer fromHex = Integer.valueOf("2A", 16); // valueOf(String,int) -> Integer
```

Các phương thức trên có **đầu vào khác nhau** nhưng đều trả `Integer`.

`Integer.valueOf(42)` không parse ký tự nào: nó nhận sẵn primitive `int` để tạo/lấy wrapper. `Integer.valueOf("42")` parse `String`. `Integer.valueOf("2A",16)` parse chuỗi theo radix 16.

Đừng viết `Integer.parseInt(42)` vì `parseInt` cần chuỗi (hoặc overload `CharSequence` kèm chỉ số/radix), không có overload đơn giản nhận một `int`.

### 13.1. Phương thức trên CharSequence

Trong Java 17, `Integer.parseInt(CharSequence s, int beginIndex, int endIndex, int radix)` và `Long.parseLong(CharSequence,beginIndex,endIndex,radix)` cho phép parse một đoạn `CharSequence` mà không nhất thiết phải tạo `String` con theo cách thủ công.

Ví dụ:

```java
CharSequence line = "id=0042;";
int id = Integer.parseInt(line, 3, 7, 10); // 42
```

Đoạn trên là mảnh code; `beginIndex` được tính từ 0 và `endIndex` là **exclusive**. `"id=0042;"` có bốn chữ số ở chỉ số 3..6. Cần kiểm soát index và bảo đảm input không bị thay đổi đồng thời nếu `CharSequence` mutable. Đây vẫn là **parse trả primitive `int`**; không có overload tương ứng `Integer.valueOf(CharSequence,begin,end,radix)` trong Java 17.

## 14. So sánh `valueOf` với constructor wrapper cũ

Trong Java 17, constructor `new Integer(String)` và `new Integer(int)` đã được **deprecated for removal**. Đối với các ứng dụng mới, ưu tiên:

- `Integer.parseInt("42")` khi cần `int`.
- `Integer.valueOf("42")` khi cần `Integer` từ `String`.
- `Integer.valueOf(42)` khi đã có một `int` muốn dùng dưới dạng wrapper.

`valueOf` có thể tái sử dụng object được cache, trong khi constructor cũ tạo object mới, nhưng **đừng dùng điều này để viết logic dựa trên object identity**. Mục tiêu là API rõ ràng và tuân thủ khuyến nghị JDK chứ không phải tối ưu tùy tiện bằng `==` trên wrapper.

### 14.1. Vì sao không dùng `new Integer("42")` để né cache?

Một số code cũ cố ý tạo hai object khác nhau để `a == b` trả false. Đây không phải cơ chế kiểm tra giá trị đúng: `==` ở hai reference kiểm tra identity; `equals` mới là kiểm tra cùng giá trị trong cùng wrapper class. Việc tạo object mới chỉ để điều khiển `==` làm code phụ thuộc chi tiết không cần thiết.

## 15. Mở rộng để tránh kết luận sai về mọi lớp parse/valueOf

**Trong chủ đề số nguyên**, `Byte`, `Short`, `Integer`, `Long` có các cặp `parse...` trả primitive và `valueOf(String)` trả wrapper. Tuy nhiên, không được áp dụng một cách máy móc rằng “mọi lớp Java đều có `parseX` và `valueOf(String)` cùng quy tắc”.

Ví dụ:

- `Double.parseDouble(String)` trả primitive `double`; `Double.valueOf(String)` trả wrapper `Double`.
- `Float.parseFloat(String)` trả primitive `float`; `Float.valueOf(String)` trả wrapper `Float`.
- `Boolean.parseBoolean(String)` trả primitive `boolean` và `Boolean.valueOf(String)` trả `Boolean`, **nhưng quy tắc chuỗi khác số nguyên**: chỉ `"true"` (không phân biệt chữ hoa/thường) được coi true, các chuỗi khác false, không ném `NumberFormatException` như integer parser.
- `BigInteger` không có `parseBigInteger(String)` hay `valueOf(String)` tương ứng; thông dụng là `new BigInteger(String)`, còn `BigInteger.valueOf(long)` nhận primitive `long`.
- `BigDecimal` có constructor từ chuỗi để giữ số thập phân chính xác theo định dạng hỗ trợ; `BigDecimal.valueOf(long)` hay `valueOf(double)` có hợp đồng khác, không phải overload `valueOf(String)`.

Phải đọc **chữ ký và tài liệu của đúng lớp/overload**. Tên “parse” hoặc “valueOf” là một dấu hiệu hữu ích, không thay thế type checking.

## 16. Những lỗi thường gặp khi review code

1. **“`Integer.valueOf("12")` trả `int`.”** Sai: trả `Integer`. Unboxing ở phép gán có thể khiến ta tưởng ngược.
2. **“`parseInt` không thêm được vào `List<Integer>`.”** Sai: compiler có thể autobox. Nhưng `List<int>` không hợp lệ.
3. **“`valueOf(String)` tự trả null nếu chuỗi sai.”** Sai: ném `NumberFormatException`.
4. **“`valueOf` hiểu `"0xFF"` nhưng `parseInt` không hiểu.”** Sai với overload radix 10; dùng `decode` hoặc truyền `"FF",16` khi phù hợp.
5. **“Chuỗi `"1_000"` hợp lệ vì literal `1_000` hợp lệ.”** Sai: Java source literal và nội dung `String` có ngữ pháp khác nhau.
6. **“`Integer.parseInt("010")` hiểu octal.”** Sai: mặc định decimal 10; `Integer.decode("010")` mới có quy ước octal.
7. **“Nếu là `Integer` thì mọi số đều có thể là null.”** Lớp wrapper có thể nhận null **ở biến tham chiếu**, nhưng `valueOf("42")` không trả null; null thường đến từ một nguồn khác.
8. **“`Integer.valueOf("42") == Integer.valueOf("42")` luôn là cách so số đúng.”** Không nên dùng reference identity. Dùng `equals` cho cùng wrapper hoặc so primitive.
9. **“Trộn `Integer` và `Long` cùng giá trị sẽ `equals` true.”** Sai: wrapper equality phân biệt class.
10. **“Sau khi parse int quá lớn, cast `long` sẽ sửa.”** Sai: lỗi xảy ra trong `parseInt` trước khi có kết quả.
11. **“`parseUnsignedInt` trả unsigned primitive riêng.”** Sai: vẫn là `int` với bit được diễn giải unsigned theo API đi kèm.
12. **“Bất kỳ khoảng trắng nào đều tự được bỏ.”** Sai: `parseInt` và `valueOf` không tự trim.
13. **“`Integer.parseInt(null)` mặc định trả 0.”** Sai: không có giá trị hợp lệ; overload `String` ném `NumberFormatException`.
14. **“`Integer.valueOf(42)` và `Integer.valueOf("42")` cùng parse chuỗi.”** Sai: overload nhận `int` không parse, overload nhận `String` có parse.
15. **“`Integer.parseInt` có thể đọc số thập phân `"42.0"` rồi bỏ phần lẻ.”** Sai: `"42.0"` không là chuỗi integer hợp lệ; cast `double` và parse integer là hai thao tác khác nhau.

## 17. Bài tập có đáp án giải thích

### Bài 1 — Trả kiểu gì?

Chọn kiểu compile-time của `Integer.parseInt("7")`, `Integer.valueOf("7")`, `Long.parseLong("7")` và `Long.valueOf("7")`.

**Đáp án:** lần lượt `int`, `Integer`, `long`, `Long`. Chữ số trong chuỗi không quyết định kiểu trả về.

### Bài 2 — Boxing nằm ở đâu?

Tại sao `Integer x = Integer.parseInt("10");` vẫn hợp lệ?

**Đáp án:** `parseInt` trả `int`; compiler áp dụng boxing để gán vào `Integer`. `parseInt` không đổi chữ ký vì vế trái là wrapper.

### Bài 3 — Unboxing nằm ở đâu?

Tại sao `int x = Integer.valueOf("10");` hợp lệ?

**Đáp án:** `valueOf(String)` trả `Integer`; compiler unbox sang `int` khi gán. Nếu nhận `null` từ nguồn khác khi unbox, chương trình có thể ném NPE; `valueOf("10")` không phải nguồn null đó.

### Bài 4 — Sai cú pháp chuỗi

`Integer.parseInt("1_000")` và `Integer.valueOf("1_000")` có chấp nhận không?

**Đáp án:** không. Gạch dưới thuộc cú pháp literal trong Java source, không thuộc dạng chuỗi số nguyên mà hai phương thức này nhận.

### Bài 5 — Hex và radix

Làm sao lấy giá trị 255 từ chuỗi `"FF"` bằng cả parse và valueOf?

**Đáp án:** `int p = Integer.parseInt("FF",16);` và `Integer v = Integer.valueOf("FF",16);`. Cả hai cho giá trị số 255, khác kiểu kết quả.

### Bài 6 — Decode

`Integer.parseInt("010")` và `Integer.decode("010")` trả giá trị gì?

**Đáp án:** `10` và wrapper `Integer` giá trị `8`, vì `decode` nhận diện số 0 đầu theo octal, còn `parseInt` mặc định decimal.

### Bài 7 — Miền giá trị

`Byte.valueOf("128")`, `Integer.parseInt("3000000000")` và `Long.parseLong("3000000000")` diễn ra thế nào?

**Đáp án:** hai lời gọi đầu ném `NumberFormatException` vì vượt miền; lời gọi thứ ba hợp lệ và trả `long` 3000000000.

### Bài 8 — So wrapper

`Integer.valueOf("42").equals(Long.valueOf("42"))` trả gì?

**Đáp án:** false vì khác wrapper class, dù có cùng lượng toán học. Nếu thật sự cần numeric equality xuyên kiểu, phải định nghĩa chính sách chuyển kiểu và miền dữ liệu riêng.

### Bài 9 — Unsigned

`Integer.parseUnsignedInt("4294967295")` trả kiểu gì và in giá trị signed nào?

**Đáp án:** trả `int` có bit toàn 1; `System.out.println` với `int` in `-1`. `Integer.toUnsignedString(bits)` in `4294967295`.

### Bài 10 — Null

Nếu `String text = null;`, `Integer.parseInt(text)` và `Integer.valueOf(text)` có trả 0/null không?

**Đáp án:** không; overload nhận `String` ném `NumberFormatException`. `Integer.valueOf((String)null)` khác với việc một biến `Integer` đã có giá trị `null`.

### Bài 11 — Overload method

Cho hai phương thức `show(int)` và `show(Integer)`. `show(Integer.parseInt("9"))` chọn phương thức nào, và `show(Integer.valueOf("9"))` chọn phương thức nào?

**Đáp án:** đầu chọn `show(int)`, sau chọn `show(Integer)`. Kiểu biểu thức ở call site quyết định overload phù hợp.

### Bài 12 — Thiết kế API

Một method tính tổng triệu số nguyên và một method trả dữ liệu có trạng thái chưa nhập, nên dùng kiểu nào?

**Đáp án:** tổng tính toán có thể dùng primitive `int`/`long` tùy miền; trường có trạng thái thiếu phải có mô hình riêng như `Integer` nullable, `OptionalInt` hoặc record trạng thái. Không thể quyết định chỉ dựa trên tốc độ mà bỏ qua yêu cầu null/error.

### Bài 13 — Decimal và octal

Tại sao `Integer.valueOf("010")` không giống `Integer.decode("010")`?

**Đáp án:** `valueOf(String)` áp dụng signed decimal giống `parseInt(String)`, cho 10; `decode` hiểu prefix số 0 theo quy tắc riêng nên cho 8.

### Bài 14 — Chuyển sang wrapper có giải quyết giá trị vượt miền không?

Giá trị `"2147483648"` vượt `Integer.MAX_VALUE`. `Integer.valueOf("2147483648")` có thể chứa nó vì là object không?

**Đáp án:** không. `Integer` bọc chính miền giá trị của `int`. Dùng `Long.parseLong`/`Long.valueOf` hoặc `BigInteger` nếu miền dữ liệu yêu cầu, không suy rằng wrapper tăng độ rộng số.

## 18. Checklist và tài liệu chuẩn

- [ ] Tôi nhớ đúng `parseInt(String) -> int` và `valueOf(String) -> Integer`.
- [ ] Tôi đối chiếu được `parseLong/valueOf`, `parseShort/valueOf` và `parseByte/valueOf`.
- [ ] Tôi xác định được nơi boxing/unboxing diễn ra khi chọn kiểu biến đích.
- [ ] Tôi biết wrapper có thể được dùng trong generic collections nhưng `List<int>` không hợp lệ.
- [ ] Tôi không dùng `==` giữa hai reference wrapper để kiểm tra cùng giá trị.
- [ ] Tôi hiểu cả parse và valueOf đều có thể ném `NumberFormatException` trên input sai.
- [ ] Tôi kiểm tra signed range trước khi chọn `byte`, `short`, `int` hay `long`.
- [ ] Tôi dùng đúng overload radix khi chuỗi không phải hệ thập phân.
- [ ] Tôi không nhầm `decode` với `parseInt`/`valueOf(String)`.
- [ ] Tôi biết parseUnsignedInt vẫn trả `int` và cần API unsigned để hiển thị/so sánh tương ứng.
- [ ] Tôi phân biệt Java source literal có underscore/prefix với chuỗi cần parser.
- [ ] Tôi biết `valueOf(int)` không giống `valueOf(String)` về đầu vào.
- [ ] Tôi đã chạy cả ba chương trình Java 17+ và thử thêm input rỗng, khoảng trắng, ngoài miền, sai radix.
- [ ] Tôi ghi rõ hợp đồng parse lỗi và xử lý `null` trước khi unbox.

**Tài liệu Java SE 17 chính thức:**

- [Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `valueOf`, `decode`, `parseUnsignedInt`, `toUnsignedString`.
- [Long API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): `parseLong`, `valueOf`, `parseUnsignedLong`.
- [Byte API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): `parseByte`, `valueOf`.
- [Short API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html): `parseShort`, `valueOf`.
- [Character API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `digit` và khái niệm radix.
- [JLS 17, `5.1.7–`5.1.8 Boxing and Unboxing Conversions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7): quy tắc boxing/unboxing.
- [BigInteger API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): chuyển chuỗi thành số nguyên tùy độ chính xác khi vượt miền primitive.

**Kết luận:** khi đọc một chuỗi số nguyên, `parse...` và `valueOf(String)` phần lớn cùng cách hiểu **chuỗi số**, nhưng khác **kiểu trả về**. Hãy ưu tiên primitive khi API cần giá trị primitive, dùng wrapper khi mô hình cần object/generic/nullable, và nhớ rằng lỗi cú pháp, phạm vi, radix và chính sách xử lý dữ liệu không được `valueOf` tự động “giải quyết”.