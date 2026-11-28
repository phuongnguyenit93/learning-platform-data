# Kiểm tra kiểu nguyên thủy và phép chuyển đổi chính xác với instanceof

## 1. Trạng thái hiện tại: đây là một tính năng preview đã ngừng phát triển

Bài học này thuộc chương **Mẫu kiểu nguyên thủy** của module **JAVA_VERSION_JAVA25**. Mục tiêu ban đầu của JDK 25 là mở rộng pattern matching để có thể kiểm tra giá trị nguyên thủy và chuyển đổi số an toàn ngay trong biểu thức `instanceof`.

Tuy nhiên, cần cập nhật trạng thái trước khi học cú pháp:

| Mốc | JEP | Trạng thái |
| --- | --- | --- |
| JDK 23 | JEP 455 | Preview lần đầu |
| JDK 24 | JEP 488 | Preview lần thứ hai |
| JDK 25 | JEP 507 | Preview lần thứ ba |
| JDK 26 | JEP 530 | Preview lần thứ tư |
| JDK 27 | JEP 532 | Preview lần thứ năm |
| 11/11/2026 | Thông báo của nhóm Java | Ngừng phát triển; rút đề xuất preview lần thứ sáu |
| JDK 28 | Kế hoạch đã công bố | Loại bỏ tính năng khỏi JDK |

Tại ngày 27/11/2026, JDK 27 đã phát hành và tính năng vẫn có thể thử dưới dạng preview của JDK 27. Nhưng nhóm Java đã quyết định ngừng phát triển; bản preview thứ sáu dự kiến cho JDK 28 bị rút và tính năng sẽ bị loại bỏ khỏi JDK 28. Vì vậy, **không xây dựng mã production mới dựa trên primitive patterns hoặc primitive instanceof**. Bài học vẫn trình bày ngữ nghĩa của JDK 25 để bạn hiểu thiết kế, đọc mã thử nghiệm và biết cách thay thế bằng Java ổn định.

Điểm này đặc biệt quan trọng với yêu cầu chỉ học kiến thức còn áp dụng: phép kiểm tra kiểu tham chiếu bằng `instanceof` và pattern variable vẫn là Java ổn định; còn việc dùng primitive type ở vế phải `instanceof` hoặc trong type pattern là preview, chưa trở thành ngôn ngữ chuẩn.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `instanceof` kiểm tra kiểu tham chiếu ổn định với primitive type comparison trong preview.
2. Hiểu type pattern, pattern variable và điều kiện để pattern match thành công.
3. Giải thích testing conversion và khái niệm exact conversion.
4. Phân biệt conversion chính xác theo giá trị tại runtime với conversion luôn chính xác.
5. Hiểu vì sao `int instanceof byte` có thể đúng hoặc sai tùy giá trị.
6. Nhận biết tác động của boxing, unboxing, null và kiểu tĩnh của biểu thức.
7. Biên dịch ví dụ JDK 25 preview đúng cách khi cần duy trì hoặc tái hiện mã thử nghiệm.
8. Viết mã production thay thế bằng pattern matching tham chiếu ổn định, kiểm tra miền giá trị và API chuyển đổi chính xác.

## 2. Nền tảng: instanceof ổn định trước khi có primitive patterns

Trong Java ổn định, `instanceof` dùng để kiểm tra xem một giá trị tham chiếu có thể được xem như một kiểu tham chiếu đích hay không. Pattern matching for instanceof cho phép khai báo biến ngay tại phép kiểm tra:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Nếu giá trị tham chiếu đến một `String`, biểu thức trả về `true` và biến `text` được khởi tạo trong phạm vi hợp lệ. Nếu giá trị là `null` hoặc tham chiếu đến kiểu không tương thích, biểu thức trả về `false`.

Một cách viết tương đương nhưng dài hơn là kiểm tra rồi ép kiểu:

```java
Object value = "Java";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.toUpperCase());
}
```

Pattern matching gộp phép kiểm tra và khai báo biến, giúp compiler kiểm soát flow scope và tránh lặp ép kiểu.

### 2.1. Primitive và wrapper là hai nhóm kiểu khác nhau

Java có tám primitive types:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Wrapper là reference type, có thể mang `null`. Primitive không thể mang `null`. Do đó:

```java
Object value = Integer.valueOf(42);

if (value instanceof Integer number) {
    int primitive = number; // unboxing
    System.out.println(primitive);
}
```

Đây là mã Java ổn định. Nó kiểm tra object có phải `Integer` hay không, rồi unbox giá trị. Nó không hỏi một giá trị số bất kỳ có thể chuyển chính xác sang `int` hay không.

Ví dụ, một object `Long` chứa 42L không phải là `Integer`:

```java
Object value = Long.valueOf(42L);

System.out.println(value instanceof Integer); // false
```

Dù 42 có thể biểu diễn bằng `int`, kiểm tra kiểu tham chiếu vẫn là kiểm tra danh tính kiểu runtime của object. Phân biệt điều này với exact numeric conversion là nền tảng của bài học.

## 3. Primitive instanceof và primitive type patterns trong JDK 25 preview

JEP 507 (JDK 25, third preview) mở rộng testing context để biểu thức có thể được so sánh/chuyển đổi giữa primitive types và reference types theo những quy tắc xác định. Hai hình thức chính:

- **Type comparison:** kiểm tra một giá trị có thể được chuyển chính xác sang kiểu đích hay không; không khai báo biến.
- **Type pattern:** kiểm tra và nếu thành công thì khởi tạo pattern variable mang kiểu đích.

Ví dụ sau minh họa cú pháp preview của JDK 25:

```java
// JDK 25 preview only — not permanent Java syntax
int quantity = 42;

if (quantity instanceof byte) {
    System.out.println("The value fits exactly in byte");
}

if (quantity instanceof byte smallQuantity) {
    System.out.println(smallQuantity);
}
```

Với `quantity = 42`, phép chuyển từ `int` sang `byte` không mất thông tin nên phép kiểm tra thành công. Nếu `quantity = 1000`, giá trị không thể biểu diễn bằng `byte` mà không thay đổi magnitude, nên phép kiểm tra trả về `false`. Pattern variable `smallQuantity` chỉ được khởi tạo trong nhánh match thành công.

### 3.1. Type comparison không tạo biến

```java
int value = 1000;

if (value instanceof byte) {
    // Chỉ biết conversion chính xác có thể thực hiện.
    // Không có biến byte nào được tạo.
}
```

Nếu cần dùng kết quả đã chuyển đổi, type pattern cung cấp biến:

```java
int value = 1000;

if (value instanceof byte small) {
    consumeByte(small);
}
```

Không có phép ép kiểu mất dữ liệu trong nhánh thành công: giá trị pattern variable chính là giá trị đã chuyển đổi chính xác sang kiểu đích.

### 3.2. Primitive type pattern có thể nhận dữ liệu từ wrapper

Trong preview, testing conversion cũng có thể bao gồm unboxing và widening primitive conversion:

```java
Short boxed = Short.valueOf((short) 12);

if (boxed instanceof int number) {
    System.out.println(number); // 12
}
```

`Short` được unbox thành `short` rồi widen thành `int`. Cả hai bước đều không làm mất thông tin, nên conversion là exact.

Với wrapper có thể null, phép thử không ném NullPointerException chỉ vì unboxing. Nếu giá trị tham chiếu là null thì phép kiểm tra không match:

```java
Integer boxed = null;

boolean matches = boxed instanceof int; // false
```

Đây là hành vi của preview primitive testing context.

## 4. Testing conversion và exact conversion

Testing context là ngữ cảnh mà Java kiểm tra một giá trị có thể được so sánh/chuyển sang kiểu đích hay không. Trong JDK 25 preview, testing context rộng hơn assignment context thông thường ở một số khía cạnh; nó có thể bao gồm identity, widening/narrowing primitive, boxing, unboxing và một số tổ hợp chuyển đổi tham chiếu.

**Được phép thử chuyển đổi không có nghĩa mọi giá trị đều match.** Compiler xác định tổ hợp chuyển đổi có thể thực hiện; runtime xác định conversion có exact với giá trị cụ thể hay không.

### 4.1. Exact nghĩa là không mất thông tin và không phát sinh exception

Theo JLS preview của JDK 25, một testing conversion của một giá trị là exact nếu kết quả không làm mất magnitude, precision, range hoặc sign, và không phát sinh exception trong các bước conversion.

Nếu conversion mất một trong các thông tin trên hoặc có bước ném exception, conversion là inexact và phép kiểm tra không thành công. Kết quả trung gian của một conversion inexact bị loại bỏ như thể conversion đó chưa xảy ra.

Điều này khác với cast số thông thường. Một cast primitive có thể âm thầm cắt bit, làm tròn hoặc bão hòa về giới hạn của kiểu đích mà không ném exception. Primitive pattern preview chỉ match khi giá trị có thể được biểu diễn chính xác.

### 4.2. Narrowing có thể exact với một số giá trị

Ví dụ chuyển `int` sang `byte`:

```java
int fits = 100;
int tooLarge = 1000;

System.out.println(fits instanceof byte);      // true
System.out.println(tooLarge instanceof byte);  // false

if (fits instanceof byte small) {
    System.out.println(small); // 100
}
```

`int` có miền rộng hơn `byte`. Chuyển đổi là narrowing primitive conversion, nhưng narrowing không luôn inexact: các giá trị trong miền `Byte.MIN_VALUE` đến `Byte.MAX_VALUE` được biểu diễn chính xác.

Cast truyền thống cho kết quả khác về ý nghĩa:

```java
int tooLarge = 1000;
byte truncated = (byte) tooLarge;

System.out.println(truncated); // -24
```

Cast không kiểm tra giá trị có nằm trong miền byte hay không; nó giữ các bit thấp và có thể đổi dấu. Vì vậy, không thể thay một exact test bằng cast rồi giả định kết quả đã an toàn.

### 4.3. Widening cũng có thể mất precision

Tên gọi widening chỉ nói kiểu đích có miền biểu diễn rộng hơn theo phân loại Java; nó không đảm bảo mọi giá trị được giữ nguyên chính xác.

Ví dụ `int` sang `float`:

```java
int exactlyRepresentable = 16_777_216;
int roundedValue = 16_777_217;

System.out.println(exactlyRepresentable instanceof float); // true
System.out.println(roundedValue instanceof float);         // false
```

`float` IEEE 754 có 24 bit precision significand (tính cả bit ẩn), nên không biểu diễn được mọi số nguyên liên tiếp ở mọi độ lớn. `16_777_216` biểu diễn được; `16_777_217` được làm tròn thành một giá trị float khác. Dù chuyển `int` sang `float` là widening primitive conversion, giá trị cụ thể có thể inexact.

Tương tự, `long` sang `double` không luôn exact. `double` có 53 bit precision significand; các số nguyên lớn hơn \(2^{53}\) không phải giá trị nào cũng biểu diễn chính xác.

### 4.4. Floating-point sang integral chỉ exact khi không làm mất phần nào

Một giá trị floating-point chuyển sang integral có thể bị cắt phần thập phân, bão hòa ở giới hạn hoặc xử lý đặc biệt với NaN/infinity. Trong testing conversion, những trường hợp mất thông tin không match:

```java
double whole = 12.0;
double fraction = 12.5;
double nan = Double.NaN;
double infinity = Double.POSITIVE_INFINITY;
double negativeZero = -0.0d;

System.out.println(whole instanceof int);         // true
System.out.println(fraction instanceof int);      // false
System.out.println(nan instanceof int);           // false
System.out.println(infinity instanceof int);      // false
System.out.println(negativeZero instanceof int);  // false
```

`12.0` có thể biểu diễn chính xác bằng `int`. `12.5` mất phần lẻ nếu chuyển sang integral. NaN và infinity không có giá trị integral tương ứng. `-0.0` chuyển thành số nguyên 0 sẽ mất dấu âm của zero, nên không exact theo quy tắc preview.

### 4.5. Conversion nhiều bước phải exact ở mọi bước

Một testing conversion có thể gồm nhiều conversion thành phần. Chỉ cần một bước inexact hoặc ném exception thì toàn bộ phép thử không match.

Ví dụ `Short` sang `int`:

```java
Short value = 123;

if (value instanceof int number) {
    // unboxing: Short -> short
    // widening: short -> int
    System.out.println(number);
}
```

Unboxing tạo primitive `short`; widening sang `int` bảo toàn giá trị. Cả hai bước exact nên pattern match thành công.

### 4.6. Vì sao không thể kiểm tra bằng round-trip cast đơn giản?

Một cách thường thấy là cast sang kiểu đích, cast ngược lại rồi so sánh. Cách này không luôn phát hiện mất thông tin vì hai lần chuyển đổi có thể triệt tiêu sai lệch của nhau.

Ví dụ `byte` sang `char`:

```java
byte value = -128;

char converted = (char) value;
byte roundTrip = (byte) converted;

System.out.println(roundTrip == value); // true
System.out.println((int) converted);    // 65408
```

Round-trip trả lại -128 nên phép so sánh tưởng như chứng minh conversion an toàn. Nhưng `char` là số nguyên không dấu 16-bit, giá trị sau chuyển đổi là 65408, không còn là -128. Thông tin về magnitude/sign đã thay đổi.

JLS preview dùng một kiểu trung gian gọi là **exactly promoted type** để so sánh giá trị gốc và giá trị sau chuyển đổi trong cùng miền có thể biểu diễn cả hai. Với `byte` và `char`, kiểu trung gian là `int`:

```java
byte value = -128;
char converted = (char) value;

boolean exact = (int) converted == (int) value;
System.out.println(exact); // false
```

Không tự viết một hàm generic round-trip cast cho mọi cặp numeric types. Quy tắc exactness phải tính đến IEEE 754, signed/unsigned representation, overflow và kiểu trung gian thích hợp.

## 5. Conversion luôn exact và conversion exact theo giá trị

JLS preview của JDK 25 phân biệt hai khái niệm:

- **Exact testing conversion:** chỉ exact với một số giá trị tại runtime. Ví dụ `int` sang `byte` exact với 100 nhưng không exact với 1000.
- **Unconditionally exact testing conversion:** được chứng minh exact cho mọi giá trị của kiểu nguồn; compiler biết điều này ngay tại compile time.

Các loại unconditionally exact trong JDK 25 preview gồm:

1. Identity conversion.
2. Exact widening primitive conversion.
3. Widening reference conversion.
4. Boxing conversion.
5. Boxing conversion theo sau bởi widening reference conversion.

Ví dụ `byte` sang `int` luôn exact:

```java
byte small = 10;

if (small instanceof int value) {
    System.out.println(value);
}
```

Ngược lại, `int` sang `byte` chỉ exact tùy giá trị, nên không unconditional. Sự phân biệt này có ý nghĩa với compiler khi kiểm tra pattern dominance và switch exhaustiveness: một pattern chỉ có thể được xem là bao phủ mọi giá trị của kiểu nguồn nếu conversion là unconditional exact.

**Lưu ý về phiên bản:** JDK 26 đã chỉnh thuật ngữ và quy tắc unconditional exactness trong preview thứ tư; JDK 27 tiếp tục preview thứ năm. Không lấy toàn bộ quy tắc của các bản preview sau rồi gán ngược cho JDK 25. Khi đọc code thử nghiệm, luôn đối chiếu đúng JDK/source release đã dùng để biên dịch.

## 6. Thử nghiệm mã JDK 25 preview đúng cách

Primitive types in patterns, `instanceof` and `switch` là preview feature trong JDK 25. Muốn tái hiện ví dụ ở bài học bằng JDK 25, cả compiler và JVM phải bật preview:

```bash
javac --enable-preview --release 25 PrimitiveInstanceofPreview.java
java --enable-preview PrimitiveInstanceofPreview
```

`--release 25` chọn ngôn ngữ/API target Java 25; `--enable-preview` bật các preview features của chính release đó. Chỉ thêm flag ở bước compile hoặc chỉ ở bước run đều không đủ.

### 6.1. Preview bytecode gắn với release đã biên dịch

Preview feature được phát hành để thu thập phản hồi và có thể thay đổi hoặc bị rút. Class file được biên dịch với preview của một release chỉ chạy trên JVM tương ứng với release đó; không xem preview bytecode là artifact tương thích xuyên các JDK.

Ví dụ, mã thử nghiệm biên dịch bằng JDK 25 cần chạy trên JDK 25 với `--enable-preview`. JDK 27 có preview thứ năm và có thể có thay đổi ngữ nghĩa so với JDK 25; hãy biên dịch lại trên đúng JDK 27 nếu cần kiểm tra phiên bản đó. Không cố chạy class file preview JDK 25 như một artifact Java 27.

### 6.2. Xác nhận phiên bản toolchain

```bash
java --version
javac --version
```

Trong Maven/Gradle, cấu hình compiler release và preview flags phải được áp dụng nhất quán cho compile/test/run. Nếu một IDE sử dụng JDK khác với terminal, kết quả compile có thể khác. Với mã production, không bật preview chỉ để sử dụng một cú pháp đã được thông báo sẽ rút khỏi Java.

### 6.3. Preview feature không phải API ổn định

Preview không giống deprecated API:

- Deprecated API vẫn thuộc nền tảng, nhưng có cảnh báo hoặc lộ trình loại bỏ.
- Preview feature chưa được chốt thành một phần lâu dài của Java SE; thiết kế có thể thay đổi hoặc biến mất.
- Khi preview bị rút, code dựa vào cú pháp đó cần được viết lại để compile trên release mới.

Vì vậy, ví dụ preview trong bài này chỉ hữu ích để đọc/đánh giá mã tương thích với đúng JDK 25/26/27. Không dùng chúng làm chuẩn coding style cho dịch vụ production mới.

## 7. Cách viết mã production bằng Java ổn định

Mục tiêu nghiệp vụ thường là một trong hai việc khác nhau:

1. Kiểm tra object có thuộc một kiểu tham chiếu cụ thể không.
2. Chuyển một giá trị số sang kiểu hẹp hơn mà không làm mất thông tin.

Java ổn định đã có cách rõ ràng cho cả hai mục tiêu; không cần primitive instanceof.

### 7.1. Kiểm tra wrapper bằng reference pattern

Nếu đầu vào là `Object` và hợp đồng chỉ chấp nhận `Integer`:

```java
static int requireInteger(Object value) {
    if (value instanceof Integer number) {
        return number;
    }
    throw new IllegalArgumentException("Expected an Integer");
}
```

Đây là pattern matching for instanceof đã permanent. Nó kiểm tra đúng kiểu object, đồng thời xử lý `null` như không match.

Không nhầm với việc kiểm tra “giá trị có vừa trong int hay không”. Một `Long` chứa 42L vẫn không phải `Integer`. Nếu API chấp nhận nhiều loại Number, hãy xác định rõ conversion policy thay vì dựa vào lớp wrapper một cách ngầm định.

### 7.2. Dùng Number nhưng chuyển đổi theo hợp đồng

`Number` cung cấp `intValue()`, `longValue()`, `floatValue()` và `doubleValue()`. Các phương thức này phù hợp khi hợp đồng cho phép chuyển đổi theo quy tắc của từng wrapper, nhưng **không đảm bảo exactness**. Chúng có thể cắt phần thập phân hoặc làm mất range/precision.

Ví dụ:

```java
Number value = Long.valueOf(4_000_000_000L);

int truncated = value.intValue();
System.out.println(truncated); // -294967296
```

Nếu dữ liệu đầu vào có thể vượt miền của kiểu đích, không gọi `intValue()` rồi coi kết quả là an toàn. Hãy dùng API exact hoặc kiểm tra miền giá trị trước khi cast.

### 7.3. Dùng Math.toIntExact cho long sang int

`Math.toIntExact(long)` là API Java ổn định để chuyển `long` sang `int` mà phát hiện overflow:

```java
long valid = 2_000_000_000L;
long overflow = 4_000_000_000L;

int a = Math.toIntExact(valid); // thành công
int b = Math.toIntExact(overflow); // ArithmeticException
```

Nếu giá trị vượt `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`, method ném `ArithmeticException`. Đây là lựa chọn rõ ràng khi cần chuyển chính xác một số nguyên 64-bit về 32-bit.

### 7.4. Kiểm tra miền trước khi chuyển int sang byte

`Math.toIntExact` chỉ giải quyết `long → int`. Với `int → byte`, có thể viết helper kiểm tra miền:

```java
static byte toByteExact(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new ArithmeticException("Value does not fit in byte");
    }
    return (byte) value;
}
```

Sau khi xác minh miền, cast là an toàn vì mọi giá trị trong miền byte đều được biểu diễn chính xác.

### 7.5. Chuyển double sang int theo chính sách rõ ràng

Nếu nghiệp vụ yêu cầu số nguyên chính xác, cần loại bỏ NaN, infinity, phần thập phân, overflow và cả negative zero nếu hợp đồng coi dấu zero là thông tin:

```java
static int toIntExact(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value > Integer.MAX_VALUE
            || value != Math.rint(value)) {
        throw new ArithmeticException("Value is not an exact int");
    }

    int result = (int) value;

    // So sánh bit để phát hiện -0.0, vì -0.0 == 0.0 là true.
    if (Double.doubleToRawLongBits((double) result)
            != Double.doubleToRawLongBits(value)) {
        throw new ArithmeticException("Conversion changes the value");
    }

    return result;
}
```

Đây là policy helper cho trường hợp cần giá trị double có biểu diễn chính xác bằng int. Nếu nghiệp vụ chấp nhận làm tròn, hãy định nghĩa rõ rounding mode và dùng `Math.round`, `Math.rint` hoặc `BigDecimal` theo hợp đồng; đừng gọi cast rồi ngầm chấp nhận truncation.

### 7.6. Dùng BigDecimal khi dữ liệu là số thập phân nghiệp vụ

Với tiền tệ, thuế hoặc số thập phân cần giữ chính xác, dùng `BigDecimal` thay vì cố chuyển qua `float`/`double`:

```java
BigDecimal amount = new BigDecimal("123.00");

int wholeUnits = amount.intValueExact(); // 123

BigDecimal fractional = new BigDecimal("123.45");
// fractional.intValueExact() ném ArithmeticException
```

`BigDecimal.intValueExact()` yêu cầu giá trị không có phần lẻ và nằm trong miền `int`. `longValueExact()` có quy tắc tương tự cho `long`. Khi parse số tiền, dùng chuỗi thập phân hoặc nguồn decimal chính xác; không khởi tạo từ một phép tính double nếu cần bảo toàn decimal representation.

## 8. Kiểu tĩnh, generics và record patterns trong preview

### 8.1. Kiểu tĩnh của biểu thức có ảnh hưởng đến conversion

Trong JDK 25 preview, compiler không chỉ xét kiểu runtime của object. Kiểu tĩnh/kiểu suy diễn của biểu thức cũng quyết định testing conversion nào hợp lệ.

Ví dụ trong JLS preview:

```java
List<Short> values = List.of((short) 7);

if (values.get(0) instanceof int number) {
    System.out.println(number); // 7
}
```

Kiểu suy diễn của `values.get(0)` là `Short`. Testing conversion là unboxing `Short → short` rồi widening `short → int`. Cả hai exact.

Không nên rút gọn ví dụ thành raw `List` rồi nghĩ kết quả sẽ tương tự. Khi kiểu tĩnh chỉ là `Object`, các quy tắc narrowing reference và unboxing khác được áp dụng; compiler không thể giả định phần tử là `Short` chỉ vì một lần chạy cụ thể trả về Short. Đây là lý do generics và type erasure cần được hiểu khi đọc preview semantics.

### 8.2. Primitive patterns trong record patterns

JEP 507 cũng cho phép primitive type patterns xuất hiện ở component pattern của record. Ví dụ minh họa:

```java
record Measurement(short raw, long sequence) {}

static void inspect(Object value) {
    if (value instanceof Measurement(int raw, long sequence)) {
        System.out.println(raw);
        System.out.println(sequence);
    }
}
```

Component `raw` có kiểu `short` nhưng pattern khai báo `int`; conversion `short → int` là widening exact. Record patterns và pattern matching tham chiếu đã là phần của Java hiện đại, nhưng **primitive component pattern trong ví dụ vẫn phụ thuộc preview feature đã bị rút**. Với mã production, dùng kiểu component gốc hoặc chuyển đổi tường minh trong thân method.

### 8.3. Scope của pattern variable

Khi pattern match thành công trong điều kiện `&&`, pattern variable có thể được sử dụng ở vế phải và trong nhánh tương ứng:

```java
int value = 42;

if (value instanceof byte small && small > 0) {
    System.out.println(small);
}
```

Đây là ví dụ preview. Flow scoping của pattern variable giúp compiler bảo đảm biến chỉ được đọc ở nơi chắc chắn đã được khởi tạo. Không giả định biến tồn tại ở mọi nhánh sau biểu thức `instanceof`; quy tắc scope vẫn do flow analysis quyết định.

## 9. Mẫu thay thế cho các tình huống phổ biến

| Nhu cầu | Java ổn định nên dùng |
| --- | --- |
| Kiểm tra object là Integer | `value instanceof Integer i` |
| Kiểm tra object là một Number | `value instanceof Number n` rồi áp dụng policy |
| Chuyển long sang int và phát hiện overflow | `Math.toIntExact(longValue)` |
| Chuyển BigInteger sang int chính xác | `bigInteger.intValueExact()` |
| Chuyển BigDecimal sang int không có phần lẻ | `bigDecimal.intValueExact()` |
| Chuyển int sang byte | Kiểm tra `Byte.MIN_VALUE`/`Byte.MAX_VALUE` trước cast |
| Chuyển double sang int chính xác | Kiểm tra finite, integral, range và round-trip biểu diễn |
| Chuyển số tiền | Dùng `BigDecimal`, không dùng `float`/`double` |

### 9.1. Chuyển Number theo allowlist kiểu

Nếu API nhận `Number`, có thể định nghĩa rõ các wrapper/kiểu số được chấp nhận:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.Objects;

// Method body trong một utility class; toIntExact(double) ở phần 7.5.
static int toIntExact(Number value) {
    Objects.requireNonNull(value, "value");

    if (value instanceof Integer i) {
        return i;
    }
    if (value instanceof Short s) {
        return s.intValue();
    }
    if (value instanceof Byte b) {
        return b.intValue();
    }
    if (value instanceof Long l) {
        return Math.toIntExact(l);
    }
    if (value instanceof BigInteger bi) {
        return bi.intValueExact();
    }
    if (value instanceof BigDecimal bd) {
        return bd.intValueExact();
    }
    if (value instanceof Double d) {
        return toIntExact(d);
    }
    if (value instanceof Float f) {
        return toIntExact(f.doubleValue());
    }

    throw new IllegalArgumentException(
            "Unsupported numeric type: " + value.getClass().getName());
}
```

Helper này có policy rõ ràng: chấp nhận các kiểu số được liệt kê và từ chối những implementation `Number` khác. Nó không gọi `Number.intValue()` một cách mù quáng. Trong hệ thống thực, có thể chọn một policy khác, ví dụ cho phép làm tròn; khi đó cần đặt tên method và ghi rõ rounding rule.

### 9.2. Tránh những cách chuyển đổi dễ mất dữ liệu

Không dùng các mẫu sau khi yêu cầu là exact:

```java
// Có thể overflow và đổi dấu:
byte b = (byte) someInt;

// Có thể mất phần lẻ, overflow hoặc biến NaN thành 0:
int i = (int) someDouble;

// Có thể mất precision:
float f = someInt;

// Không chứng minh conversion exact:
boolean looksSafe = (int) (byte) someInt == someInt;
```

Nếu nghiệp vụ cho phép mất dữ liệu, hãy ghi rõ hành vi mong muốn. Ví dụ ép kiểu để lấy 8 bit thấp có thể hợp lệ trong xử lý binary protocol, nhưng đó là truncation có chủ đích chứ không phải exact conversion.

## 10. Chẩn đoán lỗi và quyết định nâng cấp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `javac` báo preview feature disabled | Chưa bật preview hoặc đang dùng JDK khác release | Dùng JDK đúng release và `--enable-preview` ở compile/run |
| JDK 25 compile được, JDK 27 không compile cùng flags | Preview flags gắn với release hiện tại; JDK 27 có preview thứ năm | Biên dịch lại với `--release 27` và đánh giá thay đổi; không tái sử dụng preview bytecode |
| `instanceof byte` trả false | Giá trị không biểu diễn chính xác trong byte | Kiểm tra miền và giá trị trước cast |
| `int instanceof float` false dù là widening | Giá trị int bị làm tròn khi biểu diễn float | Kiểm tra precision, không chỉ tên widening |
| Wrapper null không match | Null không thể unbox thành primitive | Dùng null check hoặc reference pattern |
| `Number.intValue()` cho kết quả âm/sai | Overflow hoặc narrowing không exact | Dùng `Math.toIntExact`, `BigInteger/BigDecimal.intValueExact` hoặc range validation |
| Round-trip cast trả true nhưng dữ liệu đã đổi | Hai narrowing conversions có thể che mất loss | Không dùng round-trip tổng quát; dùng API exact hoặc quy tắc chuyển đổi rõ |
| Preview source không chạy trên JDK khác | Preview class file bị ràng buộc với release | Recompile bằng release đích; tốt hơn là migrate sang Java ổn định |

### 10.1. Lộ trình xử lý code preview đang tồn tại

Nếu một codebase đã dùng primitive patterns từ JDK 25/26/27:

1. Xác định đúng JDK và preview release đã biên dịch code.
2. Tìm mọi biểu thức primitive ở vế phải `instanceof`, primitive type pattern trong `switch` và nested record pattern.
3. Phân loại mục đích: kiểm tra wrapper type, kiểm tra miền số, hay chuyển đổi có/không mất thông tin.
4. Thay type check bằng reference pattern ổn định khi hợp đồng yêu cầu một wrapper cụ thể.
5. Thay numeric conversion bằng `Math.toIntExact`, `BigInteger/BigDecimal.intValueExact` hoặc range/integrality validation.
6. Thêm test cho biên miền, overflow, fractional values, NaN, infinity, negative zero và null.
7. Bỏ `--enable-preview` nếu không còn preview feature khác trong project.

Không cần viết lại một phép kiểm tra wrapper đã dùng cú pháp `instanceof Integer i` ổn định. Chỉ các cú pháp liên quan primitive testing/patterns mới cần migration.

## 11. Bài tập thực hành và câu hỏi tự đánh giá

### Bài 1 — Phân biệt kiểm tra kiểu và kiểm tra giá trị

Với từng đầu vào, xác định câu hỏi nghiệp vụ cần trả lời:

- `Object` có tham chiếu đến `Integer` hay không?
- `Long` có nằm trong miền `int` hay không?
- `double` có phải số nguyên hữu hạn và biểu diễn chính xác bằng `int` hay không?
- `int` có nằm trong miền `byte` hay không?

Viết mỗi trường hợp bằng API Java ổn định phù hợp. Không dùng primitive `instanceof` trong code production.

### Bài 2 — Kiểm thử overflow

Viết test cho `Math.toIntExact(long)` với:

- `Integer.MIN_VALUE` và `Integer.MAX_VALUE` dưới dạng long.
- Một giá trị nhỏ hơn `Integer.MIN_VALUE`.
- Một giá trị lớn hơn `Integer.MAX_VALUE`.

Xác nhận hai biên hợp lệ và hai trường hợp ngoài miền ném `ArithmeticException`.

### Bài 3 — Kiểm thử double sang int

Dùng helper `toIntExact(double)` ở phần 7.5 để kiểm tra:

- `12.0` và `-12.0`.
- `12.5`.
- `Double.NaN` và hai giá trị infinity.
- `-0.0`.
- `Integer.MAX_VALUE + 1.0d`.

Ghi rõ trường hợp nào được chấp nhận và vì sao. Nếu nghiệp vụ muốn làm tròn thay vì exact conversion, viết một method riêng với rounding rule đã thống nhất.

### Bài 4 — Migration từ preview

Giả sử code cũ có:

```java
if (input instanceof byte small) {
    save(small);
}
```

Thay bằng helper `toByteExact(int)` hoặc một kiểu dữ liệu domain có constructor kiểm tra miền. Thêm test cho `-128`, `127`, `-129` và `128`. Không thay bằng cast đơn thuần.

### Câu hỏi tự đánh giá

1. `instanceof Integer i` trong Java ổn định kiểm tra điều gì?
2. Primitive type comparison trong JDK 25 preview khác reference type comparison như thế nào?
3. `int instanceof byte` có thể đúng với một số giá trị và sai với giá trị khác vì sao?
4. Exact testing conversion yêu cầu bảo toàn những thông tin nào?
5. Vì sao widening `int → float` vẫn có thể inexact?
6. Tại sao `-0.0 instanceof int` không match trong preview?
7. Vì sao round-trip cast không phải phép kiểm tra exact tổng quát?
8. Unconditionally exact khác exact theo giá trị tại runtime thế nào?
9. Vì sao `Short` có thể unbox rồi widen sang `int` trong ví dụ preview?
10. JDK 25 cần flag nào để compile và chạy preview feature?
11. Tại sao preview class file của một release không phải artifact tương thích với release khác?
12. Dùng API nào cho chuyển `long → int` có phát hiện overflow?
13. Vì sao `Number.intValue()` không bảo đảm exactness?
14. Tình trạng của primitive patterns tại thời điểm hiện tại và lộ trình JDK 28 là gì?

## 12. Checklist và nguồn tham khảo

### 12.1. Checklist khi đọc mã primitive-pattern preview

- [ ] Xác định code được biên dịch bằng JDK 25, 26 hay 27; không trộn quy tắc giữa các preview release.
- [ ] Xác định biểu thức dùng type comparison hay type pattern.
- [ ] Kiểm tra kiểu tĩnh của biểu thức, bao gồm generic type và boxing/unboxing.
- [ ] Xem conversion có thể thực hiện về mặt compile-time hay không.
- [ ] Kiểm tra exactness theo giá trị runtime: magnitude, precision, range, sign và exception.
- [ ] Xem xét null trước khi unbox wrapper.
- [ ] Không dùng primitive patterns làm nền tảng cho code production mới.
- [ ] Có kế hoạch thay thế preview syntax trước khi nâng cấp JDK.

### 12.2. Checklist cho mã production

- [ ] Dùng reference pattern `instanceof Wrapper value` khi cần xác nhận đúng wrapper class.
- [ ] Dùng `Math.toIntExact` cho `long → int`.
- [ ] Dùng `BigInteger.intValueExact` hoặc `BigDecimal.intValueExact` khi nguồn là số nguyên lớn/số thập phân.
- [ ] Với các conversion không có API exact chuyên dụng, kiểm tra miền, tính hữu hạn và phần lẻ trước khi cast.
- [ ] Không dựa vào `Number.intValue()` nếu cần phát hiện overflow hoặc mất precision.
- [ ] Có test cho biên, overflow, fractional values, NaN, infinity, negative zero và null.
- [ ] Không bật `--enable-preview` trong build production chỉ để giữ primitive patterns.

### 12.3. Nguồn tham khảo

- [JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507): phạm vi preview trong JDK 25.
- [Oracle Java SE 25 — JLS Preview Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): testing contexts, exact testing conversions, unconditionally exact conversions, pattern matching và `instanceof` trong JDK 25.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): các thay đổi trong preview JDK 26; chỉ tham khảo khi đọc mã theo release đó.
- [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532): trạng thái preview JDK 27.
- [JDK 27 is Now Available](https://inside.java/2026/09/15/jdk-27-available/): xác nhận JDK 27 và primitive patterns fifth preview.
- [Withdrawing the Primitive Patterns Preview Feature](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/): thông báo ngừng phát triển, rút đề xuất preview thứ sáu và kế hoạch loại bỏ khỏi JDK 28.
- [JEP 12 — Preview Features](https://openjdk.org/jeps/12): mục đích, giới hạn và cách sử dụng preview features.
- [Java SE API — Math.toIntExact](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#toIntExact(long)): chuyển long sang int và phát hiện overflow.
- [Java SE API — BigInteger.intValueExact](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigInteger.html#intValueExact()): chuyển BigInteger sang int nếu không mất thông tin.
- [Java SE API — BigDecimal.intValueExact](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html#intValueExact()): chuyển BigDecimal sang int nếu giá trị chính xác và nằm trong miền.

**Kết luận:** JDK 25 giới thiệu primitive type patterns và primitive `instanceof` dưới dạng preview thứ ba, với khái niệm exact testing conversion để chỉ match khi chuyển đổi không làm mất thông tin. Tính năng tiếp tục ở preview trong JDK 26 và JDK 27, nhưng nhóm Java đã thông báo ngừng phát triển vào ngày 11/11/2026 và dự kiến loại bỏ khỏi JDK 28. Vì vậy, hãy hiểu ngữ nghĩa để đọc/migrate mã preview; với code mới, dùng reference patterns ổn định và các API chuyển đổi chính xác như `Math.toIntExact`, `BigInteger.intValueExact`, `BigDecimal.intValueExact` cùng kiểm tra miền giá trị tường minh.





