# Ràng buộc biến mẫu nguyên thủy và sử dụng giá trị trong nhánh điều kiện

## 1. Vì sao cần biến mẫu nguyên thủy?

Trong Java, nhiều dữ liệu đến từ phép tính, API số học, thư viện hoặc cấu trúc dữ liệu có kiểu nguyên thủy như `int`, `long`, `float` và `double`. Khi cần kiểm tra một giá trị có thể chuyển sang kiểu hẹp hơn mà không mất dữ liệu, cách viết truyền thống thường phải tự kiểm tra giới hạn rồi ép kiểu:

```java
int raw = 120;

if (raw >= Byte.MIN_VALUE && raw <= Byte.MAX_VALUE) {
    byte small = (byte) raw;
    process(small);
}
```

Nếu quên một điều kiện hoặc ép kiểu sai, phép chuyển đổi nguyên thủy có thể âm thầm làm mất phần lớn giá trị. Ví dụ ép `1000` từ `int` sang `byte` cho kết quả `-24`.

**Primitive type patterns** cho phép kiểm tra khả năng chuyển đổi và khai báo luôn biến nhận giá trị đã chuyển đổi:

```java
int raw = 120;

if (raw instanceof byte small) {
    process(small);
}
```

Biến mẫu `small` chỉ được khởi tạo khi giá trị có thể chuyển sang `byte` mà không mất thông tin. Trong nhánh đúng, bạn sử dụng trực tiếp biến đã có kiểu `byte`, không phải ép kiểu lần nữa.

Tính năng này thuộc **JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)** của Java 25. Nó mở rộng pattern matching sang các kiểu nguyên thủy, cho phép kiểm tra an toàn giữa các kiểu số, kiểm tra giá trị trong `instanceof`, tách thành phần record và dùng pattern trong `switch`.

### Kết quả cần đạt

Sau bài học, bạn có thể:

1. Hiểu biến mẫu nguyên thủy được khai báo và khởi tạo như thế nào.
2. Phân biệt phép chuyển đổi chính xác với phép ép kiểu có thể mất dữ liệu.
3. Sử dụng biến mẫu trong nhánh `if`, biểu thức `&&` và luồng thoát sớm.
4. Hiểu vì sao biến mẫu không thể được dùng ở nhánh mà phép kiểm tra có thể thất bại.
5. Dùng primitive pattern với wrapper, record pattern và `switch` có guard.
6. Biên dịch và chạy ví dụ Java 25 đúng chế độ preview.
7. Nhận biết khác biệt giữa Java 25, Java 26 và trạng thái preview mới hơn.

> **Trạng thái tính năng:** Primitive type patterns không phải tính năng permanent của Java 25. Java 25 cung cấp lần preview thứ ba; tài liệu Java 26 liệt kê lần preview thứ tư và tài liệu Java 27 hiện liệt kê lần preview thứ năm. Có thể học, thử nghiệm và đánh giá trong môi trường kiểm soát; không xem cú pháp preview là cam kết tương thích cho production.


## 2. Primitive type pattern là gì?

Một type pattern gồm một kiểu và một biến mẫu. Với kiểu tham chiếu, cú pháp quen thuộc là:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Với primitive type pattern, kiểu khai báo biến mẫu là kiểu nguyên thủy:

```java
double measurement = 42.0;

if (measurement instanceof int whole) {
    System.out.println(whole);
}
```

Ở đây:

- `measurement` là biểu thức cần kiểm tra, có kiểu `double`.
- `int` là kiểu đích của pattern.
- `whole` là biến mẫu được khởi tạo nếu phép chuyển đổi `double` sang `int` là chính xác.
- Nếu phép chuyển đổi làm mất phần thập phân, vượt miền giá trị hoặc làm mất dấu, pattern không khớp.

Primitive pattern không tạo wrapper object chỉ để kiểm tra. Khi phép thử thành công, biến mẫu mang giá trị primitive theo kiểu được khai báo.

### 2.1. Hai cách dùng `instanceof`

Java 25 preview cho phép kiểm tra khả năng chuyển đổi mà không khai báo biến:

```java
int value = 100;

if (value instanceof byte) {
    // Chỉ biết rằng value có thể chuyển sang byte một cách chính xác.
    byte result = (byte) value;
}
```

Nếu cần sử dụng giá trị đã chuyển đổi, dùng pattern variable:

```java
int value = 100;

if (value instanceof byte small) {
    // small đã có kiểu byte và chứa giá trị đã được chuyển đổi.
    sendToLegacyDevice(small);
}
```

Cách thứ hai thường rõ ràng hơn vì điều kiện và giá trị được sử dụng gắn liền với nhau. Phép kiểm tra kiểu không tự thay đổi biến nguồn; `value` vẫn là `int`.

### 2.2. Những kiểu nguyên thủy được áp dụng

Primitive type patterns áp dụng cho các kiểu nguyên thủy:

| Nhóm | Kiểu |
|---|---|
| Số nguyên | `byte`, `short`, `char`, `int`, `long` |
| Số dấu phẩy động | `float`, `double` |
| Logic | `boolean` |

Khả năng một pattern khớp còn phụ thuộc vào phép chuyển đổi kiểm tra giữa kiểu nguồn và kiểu đích. Không phải mọi cặp kiểu đều có thể chuyển đổi chính xác với mọi giá trị.

## 3. Điều kiện cốt lõi: phép chuyển đổi phải chính xác

Primitive pattern sử dụng **testing conversion**. Một giá trị khớp pattern nếu phép chuyển đổi sang kiểu đích không làm mất thông tin và không gây exception. Nếu không thỏa điều kiện, phép thử trả về `false` và biến mẫu không được khởi tạo.

Điều này khác với ép kiểu thông thường:

```java
int raw = 1000;
byte truncated = (byte) raw;

System.out.println(truncated); // -24
```

Ép kiểu trên vẫn thực hiện, nhưng giá trị đã thay đổi. Primitive pattern sẽ từ chối phép chuyển đổi không chính xác:

```java
int raw = 1000;

if (raw instanceof byte small) {
    // Không chạy: 1000 không biểu diễn được bằng byte.
    System.out.println(small);
} else {
    System.out.println("Giá trị nằm ngoài miền byte");
}
```

### 3.1. Exact conversion phụ thuộc vào giá trị

Có những cặp kiểu mà chỉ một số giá trị mới chuyển đổi chính xác.

| Kiểu nguồn → đích | Giá trị ví dụ | Kết quả |
|---|---|---|
| `int` → `byte` | `100` | Khớp; giá trị biểu diễn được bằng byte |
| `int` → `byte` | `128` | Không khớp; vượt miền byte |
| `int` → `byte` | `-128` | Khớp; đúng biên dưới |
| `int` → `float` | `42` | Khớp; giá trị biểu diễn chính xác |
| `int` → `float` | `16_777_217` | Không khớp; mất độ chính xác |
| `float` → `double` | Bất kỳ giá trị float hợp lệ | Khớp; chuyển đổi mở rộng chính xác |
| `float` → `int` | `100.0f` | Khớp; không có phần lẻ và nằm trong miền int |
| `float` → `int` | `100.25f` | Không khớp; mất phần lẻ |

Ví dụ kiểm tra miền byte:

```java
static void printIfByte(int value) {
    if (value instanceof byte small) {
        System.out.println("byte = " + small);
    } else {
        System.out.println("Không thể chuyển chính xác sang byte: " + value);
    }
}
```

Gọi thử:

```java
printIfByte(127);  // byte = 127
printIfByte(128);  // Không khớp
printIfByte(-128); // byte = -128
printIfByte(-129); // Không khớp
```

### 3.2. Không chỉ kiểm tra miền giá trị

Với số dấu phẩy động, kiểm tra an toàn còn phải xét độ chính xác, dấu và các giá trị đặc biệt:

```java
static void printWholeNumber(double value) {
    if (value instanceof int whole) {
        System.out.println("Số nguyên chính xác: " + whole);
    } else {
        System.out.println("Không thể biểu diễn chính xác bằng int: " + value);
    }
}
```

Ví dụ:

- `42.0` có thể chuyển sang `int` với giá trị `42`.
- `42.5` không khớp vì mất phần thập phân.
- Giá trị nằm ngoài miền `int` không khớp.
- `NaN` và vô cực không thể chuyển chính xác sang kiểu nguyên.
- `-0.0` không khớp khi chuyển sang kiểu nguyên vì dấu âm của zero sẽ mất.

Không thay primitive pattern bằng phép so sánh miền giá trị tự viết nếu mục tiêu là xác minh phép chuyển đổi có bảo toàn thông tin. Các kiểu dấu phẩy động có quy tắc biểu diễn riêng; việc chỉ kiểm tra giá trị nhỏ hơn hoặc lớn hơn một ngưỡng là chưa đủ.

### 3.3. Phân biệt chuyển đổi luôn chính xác và chuyển đổi phụ thuộc giá trị

Một số phép chuyển đổi được biết là luôn chính xác, ví dụ:

- `byte` sang `int`.
- `int` sang `long`.
- `float` sang `double`.
- `byte` sang `Byte` thông qua boxing.

Một số phép chuyển đổi chỉ chính xác với một tập giá trị, ví dụ `int` sang `byte` hoặc `int` sang `float`. Compiler dùng khái niệm unconditional exactness khi phân tích tính đầy đủ và dominance của pattern trong `switch`. Phần này rất quan trọng khi nhiều case pattern có thể khớp cùng một giá trị.

## 4. Dùng biến mẫu trong nhánh `if`

Mẫu đơn giản nhất là khai báo biến ngay trong điều kiện và dùng biến ở nhánh đúng:

```java
static void handleQuantity(int quantity) {
    if (quantity instanceof short q) {
        // q chỉ tồn tại trong nhánh mà conversion đã thành công.
        System.out.println("Số lượng short: " + q);
        reserveLegacyInventory(q);
    } else {
        System.out.println("Số lượng không nằm trong miền short");
    }
}
```

Khi điều kiện đúng, biến mẫu đã được khởi tạo. Khi điều kiện sai, biến không có giá trị hợp lệ và không được sử dụng trong nhánh `else`.

### 4.1. Kiểm tra rồi sử dụng trực tiếp

Thay vì kiểm tra rồi ép kiểu lại:

```java
static void writeByteOld(int value) {
    if (value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE) {
        byte converted = (byte) value;
        outputByte(converted);
    }
}
```

Có thể viết:

```java
static void writeByte(int value) {
    if (value instanceof byte converted) {
        outputByte(converted);
    }
}
```

Biến `converted` là kết quả chuyển đổi đã được kiểm tra. Điều này giảm nguy cơ điều kiện kiểm tra và phép ép kiểu không còn đồng nhất sau một lần sửa code.

### 4.2. Biến mẫu có phạm vi trong nhánh đúng

Ví dụ dưới đây hợp lệ:

```java
static void inspect(int value) {
    if (value instanceof byte b) {
        System.out.println(b);
        logByteValue(b);
    }

    // b không nằm trong phạm vi ở đây.
}
```

Không thể truy cập `b` sau khối `if` vì phép thử có thể trả về `false`. Tương tự, biến mẫu không được dùng trong nhánh `else`:

```java
if (value instanceof byte b) {
    use(b);
} else {
    // b không được khởi tạo và không thể dùng ở đây.
    reportFailure();
}
```

Quy tắc này là flow scoping: phạm vi của biến mẫu được xác định theo đường đi mà compiler biết chắc phép thử đã thành công.


## 5. Dùng biến mẫu với `&&`, `||` và phủ định

Biến mẫu có thể được dùng trong phần còn lại của điều kiện khi luồng điều khiển bảo đảm pattern đã khớp.

### 5.1. Dùng `&&` để kiểm tra thêm điều kiện

`&&` chỉ đánh giá vế phải khi vế trái đúng. Vì vậy, nếu vế trái là primitive pattern, biến mẫu có thể được dùng ở vế phải:

```java
static void acceptPositiveByte(int raw) {
    if (raw instanceof byte b && b > 0) {
        System.out.println("Byte dương: " + b);
        process(b);
    }
}
```

Thứ tự có ý nghĩa:

1. JVM kiểm tra `raw instanceof byte b`.
2. Nếu chuyển đổi chính xác, biến `b` được khởi tạo.
3. Điều kiện `b > 0` mới được đánh giá.
4. Nếu cả hai điều kiện đúng, nhánh `if` được thực thi.

Nếu pattern không khớp, vế phải không được chạy và `b` không cần có giá trị.

### 5.2. Dùng `!` để thoát sớm

Phủ định pattern thường hữu ích khi muốn loại giá trị không hợp lệ ở đầu method:

```java
static void sendToDevice(int raw) {
    if (!(raw instanceof byte value)) {
        throw new IllegalArgumentException("Giá trị vượt miền byte");
    }

    // Sau if, compiler biết rằng đường chạy tiếp theo chỉ xảy ra
    // khi primitive pattern đã khớp.
    device.write(value);
}
```

Đây là cách viết gọn cho guard clause. Khi điều kiện phủ định là đúng, method thoát bằng exception. Khi method đi tiếp, pattern chắc chắn đã khớp và biến `value` có thể sử dụng.

Có thể dùng cùng kỹ thuật với `return`:

```java
static void processIfExact(int raw) {
    if (!(raw instanceof short value)) {
        return;
    }

    calculate(value);
}
```

### 5.3. Vì sao không dùng biến mẫu ở vế phải của `||`?

`||` đánh giá vế phải khi vế trái sai. Nếu vế trái là pattern, trường hợp đó chính là trường hợp pattern không khớp, nên biến mẫu chưa được khởi tạo:

```java
int raw = 100;

// Không hợp lệ: b không chắc đã được khởi tạo ở vế phải.
if (raw instanceof byte b || b == 0) {
    System.out.println("Matched");
}
```

Muốn kiểm tra pattern và điều kiện bổ sung, hãy dùng `&&`:

```java
if (raw instanceof byte b && (b == 0 || b > 10)) {
    System.out.println(b);
}
```

Trong biểu thức này, `b` chỉ được đọc sau khi pattern thành công. Biểu thức con `b == 0 || b > 10` có thể dùng `||` vì cả hai vế đều chỉ được đánh giá sau khi biến đã tồn tại.

### 5.4. Không suy luận phạm vi chỉ từ dấu ngoặc

Khi biểu thức điều kiện phức tạp, hãy hỏi: tại vị trí đọc biến mẫu, mọi đường chạy đi đến đó có bảo đảm pattern đã khớp không?

Ví dụ an toàn:

```java
if (value instanceof byte b && isAllowed(b)) {
    persist(b);
}
```

Ví dụ không an toàn:

```java
if (value instanceof byte b || isFallbackEnabled()) {
    // Không thể dùng b ở đây: nhánh đúng có thể do vế phải tạo ra.
}
```

Nếu điều kiện khó đọc, tách thành guard clause hoặc các khối `if` nhỏ để flow scoping dễ kiểm tra hơn.

## 6. Pattern với wrapper và giá trị null

Primitive pattern cũng có thể kiểm tra giá trị đến từ kiểu tham chiếu nếu có testing conversion phù hợp, chẳng hạn unboxing từ wrapper sang primitive.

```java
Object raw = Integer.valueOf(42);

if (raw instanceof int number) {
    System.out.println(number + 1);
}
```

Ở đây, pattern kiểm tra đối tượng có thể được chuyển đổi chính xác sang `int` hay không. Nếu khớp, biến `number` là primitive `int`.

### 6.1. Wrapper null không khớp primitive pattern

```java
Integer boxed = null;

if (boxed instanceof int value) {
    // Không chạy; null không thể unbox thành int.
    System.out.println(value);
} else {
    System.out.println("Không có giá trị int");
}
```

Pattern trả về `false` thay vì để thao tác unboxing ném `NullPointerException`. Điều này giúp kiểm tra an toàn trước khi sử dụng giá trị primitive.

### 6.2. Pattern primitive không thay thế kiểm tra domain

Ví dụ, `Integer` có thể chuyển sang `int` chính xác, nhưng điều đó không bảo đảm giá trị hợp lệ theo nghiệp vụ:

```java
Integer ageFromRequest = 250;

if (ageFromRequest instanceof int age) {
    // Conversion thành công, nhưng 250 vẫn không phải tuổi hợp lệ.
    if (age >= 0 && age <= 130) {
        registerAge(age);
    }
}
```

Primitive pattern chỉ trả lời câu hỏi chuyển đổi kiểu có an toàn hay không. Quy tắc nghiệp vụ như giới hạn tuổi, số tiền, số lượng hoặc trạng thái vẫn cần được kiểm tra riêng.

## 7. Sử dụng biến mẫu trong `switch` và `when`

Java 25 preview mở rộng pattern matching cho selector primitive. Biến mẫu có thể được dùng trong nhánh case và trong guard `when`.

Ví dụ phân loại điểm số kiểu `double`:

```java
static String rating(double score) {
    return switch (score) {
        case 0.0d -> "Chưa có điểm";

        case double value when value > 0.0d && value < 2.5d ->
            "Cần cải thiện: " + value;

        case double value when value >= 2.5d && value < 5.0d ->
            "Đạt yêu cầu: " + value;

        case 5.0d -> "Xuất sắc";

        default -> "Điểm không hợp lệ";
    };
}
```

Trong mỗi guard, biến `value` chỉ có hiệu lực trong pattern label của chính case đó. Nếu pattern không khớp hoặc guard trả về false, switch tiếp tục xét label kế tiếp.

### 7.1. Đặt constant, guarded pattern và pattern tổng quát hợp lý

Các case pattern được kiểm tra theo thứ tự. Compiler phát hiện pattern bị dominance nếu một pattern phía trước luôn khớp mọi giá trị mà pattern phía sau có thể khớp.

Với `switch` có primitive patterns, hãy chú ý unconditional exact conversion. Ví dụ, nếu selector là `float` thì mọi giá trị `float` đều có thể chuyển chính xác sang `double`. Vì vậy, `case double d` bao phủ toàn bộ giá trị `float` và có thể khiến các pattern hẹp hơn phía sau bị unreachable.

```java
static String describe(float value) {
    return switch (value) {
        case 0.0f -> "zero";

        case float positive when positive > 0.0f ->
            "positive: " + positive;

        case float negative when negative < 0.0f ->
            "negative: " + negative;

        case float other ->
            "zero-like or special: " + other;
    };
}
```

Pattern cuối cùng `case float other` bao phủ phần còn lại. Không đặt một pattern không guard đã bao phủ mọi giá trị trước những case cần xử lý riêng.

### 7.2. Selector kiểu `long`, `float`, `double` và `boolean`

Trong Java 25 preview, selector của `switch` có thể là các primitive này và các kiểu boxed tương ứng. Với selector `long`, `float`, `double` hoặc `boolean`, constant case phải dùng đúng kiểu tương ứng.

Ví dụ với `float`:

```java
static String classify(float value) {
    return switch (value) {
        case 0.0f -> "zero";
        case 1.0f -> "one";
        case float n when n > 1.0f -> "greater than one";
        case float n -> "negative or between zero and one";
    };
}
```

Không thay `1.0f` bằng `1` trong selector float. Constant case phải tương thích đúng kiểu theo quy tắc của preview language feature.

## 8. Primitive pattern trong record pattern

Record pattern cho phép tách component của record ngay trong điều kiện. Khi component là kiểu nguyên thủy, primitive pattern có thể kiểm tra một kiểu chuyển đổi khác cho component đó.

```java
record Cup(double volume) {}

static void inspectCup(Cup cup) {
    if (cup instanceof Cup(float volume)) {
        System.out.println("Volume as float: " + volume);
    } else {
        System.out.println("Volume cannot be represented exactly as float");
    }
}
```

Accessor của record trả về `double`. Pattern `float volume` chỉ khớp nếu giá trị có thể biểu diễn chính xác bằng `float`.

Ví dụ:

```java
Cup a = new Cup(34.567f);
Cup b = new Cup(34.567d);

inspectCup(a); // Khớp: double là kết quả mở rộng từ float.
inspectCup(b); // Không khớp: giá trị double này không biểu diễn chính xác bằng float.
```

Pattern variable `volume` chỉ dùng được sau khi toàn bộ record pattern khớp. Với record nhiều component, mọi component pattern tương ứng phải khớp thì các biến mẫu mới được khởi tạo.

### 8.1. Kết hợp record pattern và guard

```java
record Measurement(double value, String unit) {}

static void acceptTemperature(Object input) {
    if (input instanceof Measurement(float value, String unit)
            && unit.equals("C")
            && value >= -273.15f) {
        storeTemperature(value, unit);
    }
}
```

Đoạn code thực hiện theo thứ tự:

1. Kiểm tra đối tượng có phải `Measurement` hay không.
2. Tách `value` và `unit`.
3. Chuyển `double` sang `float` một cách chính xác.
4. Kiểm tra unit và miền giá trị.
5. Chỉ khi tất cả điều kiện đúng mới gọi `storeTemperature`.

Trong ứng dụng thực tế, việc dùng `float` hay `double` phải dựa trên độ chính xác nghiệp vụ. Primitive pattern không thay thế quyết định chọn kiểu dữ liệu.


## 9. Cấu hình biên dịch và chạy Java 25 preview

Primitive type patterns là preview feature của Java 25. Phải bật preview ở cả bước biên dịch và runtime.

Ví dụ file `PrimitivePatternDemo.java`:

```java
public class PrimitivePatternDemo {

    static void printByte(int raw) {
        if (raw instanceof byte value) {
            System.out.println("byte = " + value);
        } else {
            System.out.println("out of byte range: " + raw);
        }
    }

    static String classify(double value) {
        return switch (value) {
            case 0.0d -> "zero";
            case double n when n > 0.0d && n < 100.0d -> "positive";
            case double n when n < 0.0d -> "negative";
            default -> "large or special value";
        };
    }

    public static void main(String[] args) {
        printByte(100);
        printByte(1000);

        System.out.println(classify(12.5d));
        System.out.println(classify(-2.0d));
    }
}
```

Biên dịch bằng JDK 25:

```bash
javac --enable-preview --release 25 -Xlint:preview PrimitivePatternDemo.java
```

Chạy bằng JDK 25:

```bash
java --enable-preview PrimitivePatternDemo
```

Hai bước đều cần `--enable-preview`. Nếu chỉ bật ở compiler mà không bật ở runtime, JVM từ chối nạp class phụ thuộc preview feature. Nếu không bật ở compiler, javac báo preview feature bị tắt.

### 9.1. Kiểm tra JDK đang dùng

```bash
java --version
javac --version
```

Đảm bảo `java` và `javac` thuộc cùng JDK 25. Trong CI, container và IDE, kiểm tra toolchain vì rất dễ biên dịch bằng một JDK rồi chạy bằng JDK khác.

### 9.2. Không mang class preview Java 25 sang JDK mới

Class file phụ thuộc preview feature của một release được gắn với release đó. Không giả định class biên dịch với preview Java 25 có thể chạy trên Java 26 hoặc 27 chỉ vì runtime mới cũng có primitive patterns ở một phiên bản preview khác.

Nếu chuyển sang JDK mới:

1. Đọc JEP và language guide của đúng release đích.
2. Cập nhật code nếu quy tắc preview đã thay đổi.
3. Biên dịch lại bằng compiler của release đích và `--enable-preview`.
4. Chạy bằng runtime cùng release.
5. Chạy lại toàn bộ test cho các giá trị biên và luồng điều kiện.

## 10. Trạng thái qua các phiên bản và ảnh hưởng đến code

Primitive type patterns đã trải qua nhiều vòng preview. Đây là thông tin cần giữ trong tài liệu Java 25 để người học không nhầm ví dụ của một release với cú pháp ổn định.

| Release | JEP | Trạng thái |
|---|---|---|
| Java 23 | JEP 455 | Preview lần đầu |
| Java 24 | JEP 488 | Preview lần hai |
| Java 25 | JEP 507 | Preview lần ba |
| Java 26 | JEP 530 | Preview lần bốn; cập nhật unconditional exactness và dominance |
| Java 27 | JEP 532 | Tài liệu Java SE 27 hiện liệt kê preview lần năm |

Tại thời điểm đối chiếu 27/11/2026, primitive type patterns vẫn chưa trở thành tính năng permanent. Vì vậy:

- Ví dụ trong bài được viết theo Java 25 / JEP 507.
- Khi dùng Java 26 hoặc Java 27, phải đọc quy tắc của JEP preview tương ứng.
- Không phát hành class file preview Java 25 rồi kỳ vọng chạy trên JDK khác.
- Nếu tổ chức không cho phép preview feature trong production, không bật cú pháp này trong code sản phẩm; dùng phép kiểm tra và chuyển đổi tường minh đã có trong Java.

### 10.1. Thay đổi đáng chú ý từ Java 25 sang Java 26

Java 26 cập nhật định nghĩa unconditional exactness và siết chặt kiểm tra dominance trong switch. Điều này có thể làm một số tổ hợp pattern được chấp nhận ở phiên bản trước bị compiler từ chối hoặc yêu cầu sắp xếp lại case.

Đặc biệt, khi pattern phía trước luôn khớp mọi giá trị mà pattern sau có thể nhận, pattern sau bị dominance. Hãy không dựa vào thứ tự case tùy ý; viết các case cụ thể/guarded trước pattern tổng quát và kiểm tra compiler của release mục tiêu.

## 11. Các lỗi thường gặp khi sử dụng biến mẫu nguyên thủy

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Biến mẫu không nằm trong nhánh `else` | Pattern chỉ khởi tạo khi điều kiện đúng | Dùng biến mẫu trong nhánh đúng hoặc sau guard clause |
| Biến mẫu không dùng được ở vế phải `||` | Vế phải có thể chạy khi pattern thất bại | Dùng `&&` nếu điều kiện sau cần biến mẫu |
| `int` không khớp `byte` dù giá trị nhìn có vẻ nhỏ | Kiểm tra actual runtime value, không phải kiểu khai báo mong muốn | In giá trị, kiểm tra miền và độ chính xác |
| `float` không khớp `int` | Phần thập phân hoặc chuyển đổi mất thông tin | Chỉ dùng pattern nếu cần phép chuyển đổi chính xác |
| Wrapper null không khớp primitive pattern | Null không thể unbox thành primitive | Xử lý nhánh không khớp hoặc kiểm tra null theo nghiệp vụ |
| Switch không compile do pattern dominance | Pattern trước bao phủ pattern sau | Sắp xếp lại case và xem unconditional exact conversion |
| Compile thành công nhưng runtime từ chối class | Chưa bật preview ở runtime hoặc sai JDK release | Chạy đúng JDK và thêm `--enable-preview` |
| Java mới không chạy class preview cũ | Preview class file gắn với release đã biên dịch | Biên dịch lại trên JDK đích |
| Code chạy nhưng dữ liệu nghiệp vụ sai | Exact conversion không đồng nghĩa giá trị hợp lệ theo domain | Thêm validation nghiệp vụ sau pattern |

### 11.1. Tránh dùng ép kiểu như một cách sửa nhanh

Không sửa lỗi pattern không khớp bằng cách ép kiểu trước rồi pattern lại trên kết quả đã mất dữ liệu:

```java
int raw = 1000;

// Không làm vậy nếu yêu cầu là kiểm tra chuyển đổi chính xác.
byte truncated = (byte) raw;

if (truncated instanceof byte value) {
    process(value);
}
```

Pattern trên chỉ kiểm tra giá trị `truncated` đã bị thay đổi, không còn biết giá trị ban đầu là `1000`. Hãy kiểm tra trực tiếp biến nguồn:

```java
if (raw instanceof byte exactValue) {
    process(exactValue);
}
```

### 11.2. Tách kiểm tra kiểu và kiểm tra nghiệp vụ

Pattern thành công chỉ có nghĩa phép chuyển đổi kiểu an toàn. Ví dụ `-1` là một `byte` hợp lệ nhưng có thể không phải số lượng hợp lệ trong nghiệp vụ kho.

```java
static void reserve(int rawQuantity) {
    if (rawQuantity instanceof byte quantity && quantity > 0) {
        reserveStock(quantity);
    } else {
        rejectQuantity(rawQuantity);
    }
}
```

Ở đây có hai lớp điều kiện riêng: conversion exact và quantity phải dương. Cách tách này làm rõ trách nhiệm của từng kiểm tra.

## 12. Thiết kế test cho primitive patterns

Không chỉ kiểm thử một giá trị thông thường. Hãy kiểm tra biên kiểu, giá trị mất độ chính xác và các nhánh flow scoping.

### 12.1. Bộ test cho `int` sang `byte`

| Giá trị | Kỳ vọng |
|---:|---|
| `Byte.MIN_VALUE` | Khớp |
| `-127` | Khớp |
| `0` | Khớp |
| `Byte.MAX_VALUE` | Khớp |
| `Byte.MIN_VALUE - 1` | Không khớp |
| `Byte.MAX_VALUE + 1` | Không khớp |
| `1000` | Không khớp |

### 12.2. Bộ test cho số dấu phẩy động

| Giá trị nguồn | Pattern đích | Kỳ vọng |
|---|---|---|
| `42.0d` | `int` | Khớp |
| `42.5d` | `int` | Không khớp |
| `-0.0d` | `int` | Không khớp do mất dấu |
| `Double.NaN` | `int` | Không khớp |
| `Double.POSITIVE_INFINITY` | `int` | Không khớp |
| `1000.01f` | `double` | Khớp |
| `16_777_217` kiểu int | `float` | Không khớp nếu mất độ chính xác |

### 12.3. Kiểm thử flow scoping

Biên dịch các trường hợp:

- Biến mẫu được dùng trong nhánh đúng.
- Biến mẫu được dùng ở vế phải của `&&`.
- Biến mẫu được dùng sau guard clause có `return` hoặc `throw`.
- Biến mẫu không được dùng trong nhánh `else`.
- Biến mẫu không được dùng ở vế phải `||` nếu vế trái là pattern có thể thất bại.

Một số trường hợp không hợp lệ phải được kiểm tra ở bước compile test. Chỉ chạy test runtime không đủ để xác minh quy tắc phạm vi biến của compiler.


## 13. Bài thực hành: bộ chuyển đổi dữ liệu an toàn

### 13.1. Mục tiêu

Xây một lớp tiện ích nhận dữ liệu số từ API, chỉ xử lý khi có thể chuyển đổi chính xác sang kiểu đích. Dùng primitive pattern để lấy biến mẫu và dùng guard để kiểm tra nghiệp vụ.

### 13.2. Code thực hành

```java
public final class SafeNumericProcessor {

    static void processByte(int raw) {
        if (raw instanceof byte value && value >= 0) {
            System.out.println("Accepted byte: " + value);
        } else {
            System.out.println("Rejected int: " + raw);
        }
    }

    static void processWholeNumber(double raw) {
        if (raw instanceof int value) {
            System.out.println("Accepted int: " + value);
        } else {
            System.out.println("Not an exact int: " + raw);
        }
    }

    static void processObject(Object raw) {
        if (raw instanceof int value) {
            System.out.println("Unboxed integer: " + value);
        } else {
            System.out.println("Not convertible to int");
        }
    }

    static String describe(float raw) {
        return switch (raw) {
            case 0.0f -> "zero";
            case float value when value > 0.0f && value <= 100.0f ->
                "within positive range: " + value;
            case float value when value < 0.0f ->
                "negative: " + value;
            case float value ->
                "outside normal range: " + value;
        };
    }

    public static void main(String[] args) {
        processByte(100);
        processByte(1000);

        processWholeNumber(42.0d);
        processWholeNumber(42.5d);

        processObject(Integer.valueOf(12));
        processObject(null);
        processObject("12");

        System.out.println(describe(0.0f));
        System.out.println(describe(12.5f));
        System.out.println(describe(-1.0f));
        System.out.println(describe(150.0f));
    }
}
```

Biên dịch và chạy:

```bash
javac --enable-preview --release 25 -Xlint:preview SafeNumericProcessor.java
java --enable-preview SafeNumericProcessor
```

### 13.3. Bài tập mở rộng

1. Viết hàm `toShortIfExact(int raw)` trả về giá trị `Short` nếu pattern khớp và `Optional.empty()` nếu không khớp.
2. Viết hàm kiểm tra `double` có thể chuyển chính xác sang `long` hay không.
3. Tạo record `SensorReading(double value, String unit)` và dùng record pattern để chỉ nhận component `float` khi conversion chính xác.
4. Viết switch expression phân loại `long` theo các ngưỡng, dùng biến mẫu trong guard `when`.
5. Viết compile test chứng minh biến mẫu không thể dùng trong vế phải `||`.
6. Chạy lại cùng bộ test trên JDK 26 hoặc JDK 27 preview và ghi nhận mọi thay đổi compiler yêu cầu.

## 14. Checklist áp dụng

Trước khi dùng primitive type patterns:

- [ ] Đã xác nhận JDK release và trạng thái preview của tính năng.
- [ ] Đã bật preview ở cả compiler và runtime khi thử nghiệm.
- [ ] Biến mẫu chỉ được sử dụng ở nơi compiler xác định chắc chắn pattern đã khớp.
- [ ] Dùng `&&` khi điều kiện sau cần biến mẫu.
- [ ] Không dùng biến mẫu ở nhánh có thể chạy khi pattern thất bại.
- [ ] Đã kiểm thử các giá trị biên và trường hợp mất độ chính xác.
- [ ] Đã xử lý wrapper null và unboxing.
- [ ] Đã tách conversion safety khỏi validation nghiệp vụ.
- [ ] Đã kiểm tra dominance và exhaustiveness của switch.
- [ ] Không dùng preview class file của Java 25 trên runtime khác.
- [ ] Đã đọc JEP/language guide đúng release trước khi nâng JDK.
- [ ] Không coi preview feature là hợp đồng tương thích production.

## 15. Tài liệu chính thức và phạm vi phiên bản

- [JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507): phạm vi primitive type patterns trong Java 25.
- [Java SE 25 — Type Patterns](https://docs.oracle.com/en/java/javase/25/language/type-patterns.html): primitive type patterns, biến mẫu và ví dụ với `float`, `double`, `int`.
- [Java SE 25 — Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/25/language/safe-casting-instanceof-switch.html): testing conversion, conversion an toàn và dominance.
- [Java SE 25 — Record Patterns](https://docs.oracle.com/en/java/javase/25/language/record-patterns.html): primitive type patterns trong record component.
- [Java SE 25 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-switch.html): guard `when`, biến mẫu trong switch và primitive selector.
- [Java SE 25 — Preview Features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html): cách bật preview khi compile và run.
- [Java SE 25 — JLS Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/25/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): quy tắc testing conversion, exactness, pattern matching và flow.
- [JEP 530 — Java 26 Fourth Preview](https://openjdk.org/jeps/530): cập nhật unconditional exactness và dominance.
- [Java SE 26 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html): trạng thái preview lần thứ tư.
- [JEP 532 — Java 27 Fifth Preview](https://openjdk.org/jeps/532): vòng preview tiếp theo.
- [Java SE 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): tài liệu hiện liệt kê primitive patterns ở preview lần thứ năm.

*Phạm vi đối chiếu: 27/11/2026.* Bài giải thích cú pháp và quy tắc của Java 25 / JEP 507. Tính năng vẫn ở trạng thái preview trong các tài liệu Java 26 và Java 27 hiện hành; preview có thể thay đổi hoặc bị rút lại. Khi thử nghiệm trên JDK khác, hãy dùng compiler và runtime cùng release, đọc JEP tương ứng và biên dịch lại toàn bộ class. Không dùng preview class file Java 25 như artifact tương thích xuyên phiên bản.
