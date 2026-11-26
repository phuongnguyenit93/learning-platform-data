# Dùng biến cục bộ cùng phép tính dùng chung để chuẩn bị đối số constructor

Flexible Constructor Bodies cho phép viết các câu lệnh trước lời gọi constructor tường minh `super(...)` hoặc `this(...)`. Nhờ đó, constructor có thể chuẩn hóa dữ liệu, phân tích chuỗi, tính toán giá trị trung gian và kiểm tra điều kiện trước khi chuyển các đối số đã chuẩn bị cho constructor lớp cha hoặc constructor khác trong cùng lớp.

Khi có nhiều bước xử lý, nên đưa phép tính có thể tái sử dụng vào các phương thức `static` và lưu kết quả vào biến cục bộ. Cách này giúp mỗi đối số được tính một lần, làm rõ thứ tự kiểm tra và tránh gọi phương thức instance khi đối tượng hiện tại chưa được khởi tạo xong.

Flexible Constructor Bodies được preview lần đầu ở Java 22 (JEP 447), preview lần hai ở Java 23 (JEP 482), preview lần ba ở Java 24 (JEP 492), và trở thành tính năng ngôn ngữ chính thức trong Java 25 qua JEP 513. Trên JDK 25 và JDK 27, cú pháp này đã stable, không cần bật `--enable-preview`. JDK 27 là feature release mới nhất tại ngày 25-11-2026; JDK 25 là LTS mới nhất.

## 1. Prologue và early construction context

Phần câu lệnh nằm trước lời gọi constructor tường minh được gọi là **prologue**. Phần nằm sau lời gọi đó là **epilogue**.

```java
class Child extends Parent {
    Child(String rawValue) {
        String normalized = normalize(rawValue); // Prologue
        int value = parse(normalized);             // Prologue
        super(value);                              // Constructor invocation
        logCreated(value);                         // Epilogue
    }

    private static String normalize(String value) { /* ... */ }
    private static int parse(String value) { /* ... */ }
    private void logCreated(int value) { /* ... */ }
}
```

Prologue và các biểu thức đối số của `super(...)` hoặc `this(...)` tạo thành **early construction context** (ngữ cảnh khởi tạo sớm). Tại thời điểm đó, constructor của lớp cha chưa hoàn tất. Vì vậy, Java cho phép xử lý dữ liệu độc lập với instance đang được tạo, nhưng giới hạn truy cập vào chính instance đó.

Các việc thường phù hợp với prologue:

- Khai báo và gán biến cục bộ.
- Tính toán trên tham số constructor và các biến cục bộ.
- Gọi phương thức `static` để chuẩn hóa, phân tích hoặc xác thực dữ liệu.
- Tạo đối tượng phụ trợ độc lập, chẳng hạn `BigInteger`, `Path` hoặc một mảng kết quả phân tích.
- Ném ngoại lệ nếu dữ liệu không hợp lệ; khi đó lời gọi `super(...)` hoặc `this(...)` không diễn ra.

## 2. Quy tắc truy cập trong prologue

Early construction context không cho phép sử dụng instance đang được tạo như một đối tượng đã sẵn sàng.

| Có thể thực hiện | Không thể thực hiện |
|---|---|
| Đọc tham số constructor. | Đọc trường instance của `this` hoặc của lớp cha. |
| Đọc/ghi biến cục bộ. | Gọi phương thức instance của đối tượng đang xây dựng. |
| Gọi phương thức `static`. | Dùng `this` như một biểu thức hoặc truyền `this` làm đối số. |
| Gọi phương thức trên một tham số hoặc đối tượng độc lập. | Truy cập thành viên của `super` hoặc dùng `super` làm biểu thức. |
| Dùng biểu thức, điều kiện và ném ngoại lệ. | Gọi phương thức instance không ghi `this` tường minh nhưng ngầm truy cập đối tượng hiện tại. |

Ví dụ không hợp lệ:

```java
class Account extends BaseAccount {
    private String code;

    Account(String rawCode) {
        String normalized = rawCode.strip();

        // Không hợp lệ: đang đọc/ghi instance trước super(...).
        if (code != null) {
            throw new IllegalStateException();
        }

        // Không hợp lệ: instance method của đối tượng chưa được khởi tạo.
        validateCode(normalized);

        super(normalized);
    }

    private void validateCode(String value) { }
}
```

Hãy chuyển logic xác thực độc lập với instance sang phương thức `static`:

```java
class Account extends BaseAccount {
    Account(String rawCode) {
        String normalized = normalizeAndValidate(rawCode);
        super(normalized);
    }

    private static String normalizeAndValidate(String rawCode) {
        String value = java.util.Objects.requireNonNull(rawCode).strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Account code must not be blank");
        }
        return value;
    }
}
```

Phương thức `static` không có receiver `this`. Vì vậy, nó có thể xử lý tham số và trả về kết quả để prologue dùng làm đối số constructor. Phương thức này không được dựa vào instance đang xây dựng thông qua một đường gọi gián tiếp.

### Ngoại lệ có chủ đích: gán trường của lớp đang xây dựng

JEP 482 bổ sung khả năng gán trường được khai báo trong chính lớp đang xây dựng trước khi gọi constructor lớp cha. Đây là phép gán đơn giản để khởi tạo trường; prologue vẫn không được đọc giá trị trường đó. Quy tắc này hữu ích khi constructor lớp cha gọi một phương thức có thể bị override và phương thức override đọc trường của lớp con.

Ví dụ:

```java
class Parent {
    Parent() {
        printValue();
    }

    void printValue() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private final int value;

    Child(int value) {
        this.value = value;
        super();
    }

    @Override
    void printValue() {
        System.out.println(value);
    }
}
```

Trường `value` được gán trước `super()`, nên lời gọi override từ constructor `Parent` nhìn thấy giá trị đã gán. Đây là ngoại lệ phục vụ khởi tạo trường; nó không cho phép prologue đọc trường hoặc gọi phương thức instance.

## 3. Chuẩn bị đối số `super(...)` bằng biến cục bộ và phương thức static dùng chung

Giả sử cần tạo một số nguyên lớn dương từ đầu vào dạng chuỗi hoặc `long`. Cả hai constructor cần dùng chung phép phân tích và kiểm tra giá trị.

```java
import java.math.BigInteger;
import java.util.Objects;

public final class PositiveBigInteger extends BigInteger {
    public PositiveBigInteger(String rawValue) {
        String normalized = normalize(rawValue);
        BigInteger parsed = parsePositive(normalized);
        super(parsed.toString());
    }

    public PositiveBigInteger(long rawValue) {
        BigInteger parsed = parsePositive(Long.toString(rawValue));
        super(parsed.toString());
    }

    private static String normalize(String rawValue) {
        return Objects.requireNonNull(rawValue, "rawValue").strip();
    }

    private static BigInteger parsePositive(String decimal) {
        BigInteger value = new BigInteger(decimal);
        if (value.signum() <= 0) {
            throw new IllegalArgumentException("Value must be positive");
        }
        return value;
    }
}
```

Hai constructor dùng chung `parsePositive(...)`. Constructor nhận chuỗi còn gọi `normalize(...)` để loại bỏ khoảng trắng đầu/cuối trước khi phân tích. Mỗi kết quả trung gian được lưu vào biến cục bộ, sau đó mới được chuyển cho `super(...)`.

Trình tự của constructor nhận chuỗi:

1. `normalize(rawValue)` kiểm tra null và chuẩn hóa chuỗi.
2. `parsePositive(normalized)` tạo `BigInteger` và xác nhận giá trị dương.
3. `super(parsed.toString())` chuyển chuỗi thập phân chuẩn hóa cho constructor của `BigInteger`.

Nếu đầu vào null, không phải số nguyên hợp lệ hoặc không dương, ngoại lệ được ném trong prologue và constructor `BigInteger` chưa chạy. Constructor nhận `long` cũng dùng chung `parsePositive`, nên quy tắc kiểm tra không bị sao chép ở nhiều nơi.

## 4. Chuẩn bị nhiều đối số và gọi `this(...)`

Flexible Constructor Bodies cũng cho phép thực hiện nhiều phép tính trước lời gọi `this(...)`. Điều này hữu ích khi một constructor nhận dữ liệu dạng gộp, phân tách thành các giá trị riêng, rồi ủy quyền cho constructor chính.

Ví dụ lớp `Dimensions` hỗ trợ ba cách khởi tạo: từ chuỗi `"12x8"`, từ hai chuỗi riêng, hoặc từ hai số nguyên.

```java
import java.util.Objects;

public final class Dimensions {
    private final int width;
    private final int height;

    public Dimensions(String dimensions) {
        String[] parts = splitDimensions(dimensions);
        int parsedWidth = parsePositive(parts[0]);
        int parsedHeight = parsePositive(parts[1]);
        this(parsedWidth, parsedHeight);
    }

    public Dimensions(String width, String height) {
        int parsedWidth = parsePositive(width);
        int parsedHeight = parsePositive(height);
        this(parsedWidth, parsedHeight);
    }

    public Dimensions(int width, int height) {
        this.width = requirePositive(width);
        this.height = requirePositive(height);
    }

    private static String[] splitDimensions(String raw) {
        String value = Objects.requireNonNull(raw, "dimensions").strip();
        String[] parts = value.split("x", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Expected format: width x height");
        }
        return parts;
    }

    private static int parsePositive(String raw) {
        int value = Integer.parseInt(
            Objects.requireNonNull(raw, "dimension").strip()
        );
        return requirePositive(value);
    }

    private static int requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("Dimension must be positive");
        }
        return value;
    }

    public int width() {
        return width;
    }

    public int height() {
        return height;
    }
}
```

Hai constructor đầu tiên dùng biến cục bộ để tính `parsedWidth` và `parsedHeight`, rồi gọi `this(parsedWidth, parsedHeight)`. Constructor thứ ba là nơi duy nhất gán các trường và bảo đảm bất biến của đối tượng. Các phương thức `static` dùng chung phép phân tích và xác thực cho cả hai đường khởi tạo.

Có thể sử dụng:

```java
Dimensions fromCombinedText = new Dimensions("12x8");
Dimensions fromSeparateText = new Dimensions("12", "8");
Dimensions fromNumbers = new Dimensions(12, 8);

System.out.println(fromCombinedText.width()); // 12
System.out.println(fromSeparateText.height()); // 8
```

Constructor `this(...)` chuyển quyền khởi tạo cho constructor khác trong cùng lớp. Constructor được gọi tiếp tục chịu trách nhiệm gọi constructor lớp cha. Một constructor chỉ có tối đa một constructor invocation; không thể vừa gọi `this(...)` vừa gọi `super(...)` trong cùng thân constructor.

## 5. Cách tổ chức phép tính dùng chung

Khi chuẩn bị đối số, nên chia logic thành các bước có tên rõ ràng:

| Bước | Câu hỏi | Cách tổ chức |
|---|---|---|
| Chuẩn hóa | Dữ liệu có khoảng trắng, định dạng hoặc biểu diễn thay thế không? | Phương thức `static normalize...(...)`. |
| Phân tích | Cần chuyển chuỗi thành số, ngày, đường dẫn hoặc kiểu domain nào? | Phương thức `static parse...(...)`. |
| Xác thực | Đối số có thỏa điều kiện để constructor tiếp tục không? | Phương thức `static require...(...)` hoặc `validate...(...)`. |
| Kết hợp | Constructor đích cần những giá trị nào và theo thứ tự nào? | Gán từng kết quả vào biến cục bộ rồi truyền vào `super(...)`/`this(...)`. |

Một helper có thể trả về đối tượng nhỏ chứa nhiều giá trị đã chuẩn bị nếu logic phức tạp. Tuy nhiên, không nên tạo abstraction quá lớn cho một phép chuyển đổi đơn giản. Mục tiêu là để thứ tự xử lý và điều kiện hợp lệ dễ đọc.

Ví dụ, nếu cần tính cả tên chuẩn hóa và mã số:

```java
private static PreparedInput prepare(String rawName, String rawCode) {
    String name = normalizeName(rawName);
    int code = parseCode(rawCode);
    validatePair(name, code);
    return new PreparedInput(name, code);
}

private record PreparedInput(String name, int code) { }
```

Trong constructor, có thể nhận kết quả từ helper rồi truyền các thành phần của nó cho `super(...)` hoặc `this(...)`. Đối tượng phụ trợ được tạo từ tham số và dữ liệu độc lập; không được tạo hoặc truy cập thành viên của instance đang xây dựng trong prologue.

## 6. Điều gì xảy ra nếu phép tính thất bại?

Prologue có thể kết thúc bất thường, chẳng hạn ném `IllegalArgumentException`, `NullPointerException` hoặc ngoại lệ phân tích. Trong trường hợp đó, constructor invocation chưa được thực hiện và constructor lớp cha không chạy.

Đây là đặc tính hữu ích khi cần từ chối dữ liệu sớm:

```java
class PortAddress extends BaseAddress {
    PortAddress(String host, String portText) {
        String normalizedHost = normalizeHost(host);
        int port = parsePort(portText);
        super(normalizedHost, port);
    }

    private static String normalizeHost(String host) {
        String value = java.util.Objects.requireNonNull(host).strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Host must not be blank");
        }
        return value;
    }

    private static int parsePort(String rawPort) {
        int port = Integer.parseInt(rawPort.strip());
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Port out of range");
        }
        return port;
    }
}
```

Trong ví dụ, `BaseAddress` chỉ được gọi sau khi host và port đã được chuẩn hóa, phân tích và kiểm tra. Nếu một bước thất bại, constructor lớp cha không nhận dữ liệu chưa hợp lệ.

## 7. Những lỗi thường gặp khi viết prologue

| Lỗi | Vì sao sai hoặc khó bảo trì | Cách sửa |
|---|---|---|
| Gọi instance method để chuẩn hóa dữ liệu | Phương thức instance cần đối tượng hiện tại, nhưng đối tượng chưa sẵn sàng. | Chuyển logic độc lập sang phương thức `static`. |
| Đọc field để làm đối số `super(...)` | Field của instance chưa được phép đọc trong early construction context. | Tính từ tham số hoặc biến cục bộ. |
| Tính cùng một giá trị nhiều lần trong danh sách đối số | Có thể lặp công việc hoặc tạo kết quả không nhất quán nếu hàm có tác dụng phụ. | Tính một lần vào biến cục bộ rồi truyền biến đó. |
| Sao chép cùng quy tắc xác thực ở nhiều constructor | Các overload dễ lệch quy tắc theo thời gian. | Dùng helper `static` hoặc constructor đích chung qua `this(...)`. |
| Gọi `this(...)` rồi gọi tiếp `super(...)` | Một constructor không thể có cả hai lời gọi tường minh. | Constructor hiện tại gọi `this(...)`; constructor được ủy quyền sẽ gọi `super(...)`. |
| Dùng helper `static` nhưng dựa vào mutable static state | Kết quả có thể phụ thuộc trạng thái dùng chung và khó kiểm soát. | Truyền mọi dữ liệu cần thiết qua tham số, giữ helper thuần khi phù hợp. |
| Cho rằng mọi câu lệnh trong prologue đều được phép | Early construction context vẫn có giới hạn truy cập instance và quy tắc definite assignment. | Chỉ thao tác với tham số, biến cục bộ, dữ liệu độc lập và các phép gán field được cho phép. |

## 8. Biên dịch theo JDK hiện hành

Flexible Constructor Bodies là ngôn ngữ Java stable từ JDK 25. Có thể biên dịch ví dụ bằng JDK 25 hoặc JDK 27 mà không bật preview:

```bash
javac --release 25 -d out src/PositiveBigInteger.java src/Dimensions.java
```

Nếu dự án dùng JDK 27 làm compiler và runtime:

```bash
javac --release 27 -d out src/PositiveBigInteger.java src/Dimensions.java
java -cp out demo.Main
```

Không dùng `--enable-preview` cho Flexible Constructor Bodies. Trong JDK 27 có một preview language feature khác là **Primitive Types in Patterns, `instanceof`, and `switch` (JEP 532, Fifth Preview)**. Nếu một chương trình riêng có dùng feature đó, phải bật preview ở cả hai bước:

```bash
javac --enable-preview --release 27 -d out src/PreviewPatternDemo.java
java --enable-preview -cp out demo.PreviewPatternDemo
```

Các ví dụ trong bài không sử dụng JEP 532 nên không cần các cờ preview này. Không lấy mã preview của Java 22, 23 hoặc 24 làm cú pháp hiện hành: các giai đoạn đó chỉ là lịch sử trước khi JEP 513 trở thành final trong Java 25.

## 9. Checklist khi chuẩn bị đối số constructor

- Xác định constructor sẽ gọi `super(...)` hay `this(...)`.
- Tách chuẩn hóa, phân tích và xác thực thành các bước dễ đọc.
- Dùng biến cục bộ để lưu kết quả sẽ truyền cho constructor đích.
- Tái sử dụng phép tính qua helper `static` thay vì gọi instance method.
- Bảo đảm helper không truy cập gián tiếp vào instance đang xây dựng.
- Chỉ gán field của chính lớp đang xây dựng trong prologue khi có lý do rõ ràng; không đọc field đó trước constructor invocation.
- Đặt lời gọi `super(...)` hoặc `this(...)` sau các bước chuẩn bị.
- Giữ các thao tác cần `this` trong epilogue, sau constructor invocation.
- Dùng JDK 25+ và không bật preview cho Flexible Constructor Bodies.

## 10. Kết luận

Flexible Constructor Bodies giúp constructor chuẩn bị dữ liệu trước khi gọi constructor lớp cha hoặc constructor khác trong cùng lớp. Biến cục bộ giữ các kết quả trung gian; helper `static` gom các phép chuẩn hóa, phân tích và xác thực có thể dùng chung; cuối cùng, constructor chuyển các giá trị đã chuẩn bị qua `super(...)` hoặc `this(...)`.

Giới hạn cốt lõi vẫn là early construction context: chưa được đọc hoặc sử dụng instance đang xây dựng. Khi giữ prologue độc lập với `this`, đồng thời để một constructor đích chịu trách nhiệm khởi tạo trạng thái cuối cùng, mã constructor dễ đọc và ít lặp logic hơn. Cú pháp này đã stable từ Java 25 và tiếp tục áp dụng trên JDK 27.

## Tài liệu tham khảo

- [JEP 513 – Flexible Constructor Bodies (Java 25)](https://openjdk.org/jeps/513)
- [JEP 492 – Flexible Constructor Bodies (Third Preview, Java 24)](https://openjdk.org/jeps/492)
- [JEP 482 – Flexible Constructor Bodies (Second Preview, Java 23)](https://openjdk.org/jeps/482)
- [JEP 447 – Statements before `super(...)` (Preview, Java 22)](https://openjdk.org/jeps/447)
- [Flexible Constructor Bodies – Java SE 27 Language Guide](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html)
- [Java Language Changes by Release – Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [JEP 532 – Primitive Types in Patterns, `instanceof`, and `switch` (Fifth Preview, Java 27)](https://openjdk.org/jeps/532)
