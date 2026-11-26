# Chuyển mã kiểm tra đầu vào sang cú pháp chính thức và kiểm tra lỗi biên dịch

## Mục tiêu

Sau bài học này, bạn có thể:

- Chuyển validation trong constructor sang phần prologue trước `super(...)` hoặc `this(...)`.
- Phân biệt những thao tác được phép và không được phép trong *early construction context*.
- Chủ động khởi tạo field của lớp con trước khi constructor lớp cha chạy khi cần thiết.
- Dùng `javac` trên JDK 25 hoặc JDK 27 để xác nhận cú pháp chính thức và đọc lỗi biên dịch.

## Trạng thái của tính năng trên JDK hiện đại

Flexible Constructor Bodies được chuẩn hóa bởi JEP 513 trong JDK 25. Đây là tính năng ngôn ngữ chính thức, tiếp tục được hỗ trợ trên JDK 27. Không cần bật preview và không cần thêm cờ JVM riêng.

Lịch sử preview chỉ để nhận diện mã cũ: tính năng được preview lần đầu trong JDK 22 với JEP 447 (*Statements before super(...)*), tiếp tục ở JDK 23 với JEP 482 và JDK 24 với JEP 492. Từ JDK 25, hãy viết theo cú pháp final của JEP 513.

JEP 512 (*Compact Source Files and Instance Main Methods*) cũng trở thành chính thức trong JDK 25. Đây là tính năng độc lập giúp viết chương trình thử nghiệm ngắn bằng compact source file và instance `main`; nó không thay đổi quy tắc của constructor. Các ví dụ về kế thừa bên dưới vẫn dùng lớp có tên rõ ràng để tập trung vào constructor.

## Vấn đề của cách viết constructor trước đây

Trong chế độ ngôn ngữ ổn định trước JDK 25 (hoặc khi tắt preview trên JDK 22–24), lời gọi constructor lớp cha `super(...)` hoặc constructor cùng lớp `this(...)` phải đứng đầu constructor. Vì vậy, nếu muốn kiểm tra tham số trước khi tạo lớp cha, bạn thường phải chuyển validation sang một static helper và gọi helper trong đối số của `super(...)`.

Ví dụ, lớp `PositiveBigInteger` chỉ chấp nhận số nguyên dương:

```java
import java.math.BigInteger;

public final class PositiveBigInteger extends BigInteger {

    public PositiveBigInteger(long value) {
        super(toPositiveDecimal(value));
    }

    private static String toPositiveDecimal(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        return Long.toString(value);
    }
}
```

Cách này vẫn hợp lệ và không phải API lỗi thời. Tuy nhiên, nếu validation có nhiều bước, việc đưa toàn bộ logic vào helper chỉ để thỏa mãn vị trí của `super(...)` có thể làm luồng khởi tạo khó đọc.

## Chuyển sang Flexible Constructor Bodies

JEP 513 cho phép đặt các câu lệnh không truy cập instance đang được tạo trước lời gọi constructor tường minh. Phần đứng trước lời gọi `super(...)` hoặc `this(...)` được gọi là *prologue*; phần đứng sau là *epilogue*.

Ta có thể chuyển validation trực tiếp vào constructor:

```java
import java.math.BigInteger;

public final class PositiveBigInteger extends BigInteger {

    public PositiveBigInteger(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }

        super(Long.toString(value));
    }
}
```

Trình tự thực hiện là:

1. Kiểm tra `value` trong prologue.
2. Nếu không hợp lệ, ném exception và constructor kết thúc; constructor lớp cha không chạy.
3. Nếu hợp lệ, tính đối số và gọi `super(...)`.
4. Tiếp tục phần epilogue của constructor sau khi constructor lớp cha hoàn tất.

Điểm có ích là validation và việc chuẩn bị đối số của lớp cha nằm cùng một nơi, thể hiện rõ điều kiện trước khi đối tượng lớp cha được khởi tạo.

## Early construction context: được làm gì trước super?

Các câu lệnh trong prologue và các đối số của lời gọi constructor tường minh nằm trong *early construction context*. Ở giai đoạn này, instance hiện tại chưa được khởi tạo hoàn tất. Quy tắc quan trọng là không được đọc hoặc sử dụng instance như một đối tượng đã tồn tại.

| Thao tác trong prologue | Hợp lệ? | Giải thích |
|---|---|---|
| Đọc tham số constructor và biến local | Có | Đây là dữ liệu đầu vào, không cần truy cập instance. |
| Dùng `if`, `switch`, vòng lặp hoặc ném exception | Có | Có thể kiểm tra và chuẩn bị dữ liệu trước khi gọi constructor khác. |
| Gọi static method hoặc đọc static field | Có | Thành viên static không cần instance đang được tạo. |
| Tạo và dùng biến local | Có | Miễn là không truy cập instance đang được tạo. |
| Gán giá trị cho field của lớp đang được khởi tạo, ví dụ `this.id = id` | Có | Java cho phép khởi tạo field trước `super(...)`; không được đọc field đó trong prologue. |
| Đọc field instance, ví dụ `this.id` hoặc `id` khi nó là field | Không | Giá trị instance chưa sẵn sàng để đọc. |
| Gọi instance method, ví dụ `validate()` hoặc `this.validate()` | Không | Lời gọi có thể quan sát trạng thái chưa khởi tạo của instance. |
| Dùng `this` như một giá trị hoặc dùng `super` để truy cập thành viên | Không | Không được sử dụng instance hiện tại trước khi constructor lớp cha chạy. |

Một ngoại lệ có chủ đích là phép gán field. Ví dụ `this.id = id;` được cho phép, nhưng biểu thức đọc `this.id` vẫn không hợp lệ. Không suy rộng ngoại lệ này thành quyền gọi method hoặc truyền `this` cho một hàm khác.

## Ví dụ: khởi tạo field lớp con trước constructor lớp cha

Một constructor lớp cha có thể gọi một method có thể bị override. Nếu method override trong lớp con đọc field của lớp con, field đó có thể vẫn mang giá trị mặc định khi constructor lớp cha gọi method.

```java
class Base {
    Base() {
        printId();
    }

    void printId() {
        System.out.println("Base");
    }
}

class SafeChild extends Base {
    private final int id;

    SafeChild(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }

        // Gán field trước khi constructor Base gọi printId().
        this.id = id;
        super();
    }

    @Override
    void printId() {
        System.out.println(id);
    }
}
```

Khi chạy `new SafeChild(42)`, `id` được gán giá trị `42` trước khi `Base()` thực thi. Vì vậy, lời gọi `printId()` từ constructor lớp cha nhìn thấy giá trị `42` thay vì giá trị mặc định `0`.

Đây là một trường hợp đặc biệt hữu ích của JEP 513: không chỉ validation tham số, prologue còn có thể gán field để bảo đảm invariant của lớp con trước khi constructor lớp cha gọi method được override. Chỉ dùng cách này khi thật sự cần; nói chung constructor lớp cha nên tránh gọi method có thể override vì object vẫn đang trong quá trình khởi tạo.

## Dùng this(...) để ủy quyền constructor

Flexible Constructor Bodies cũng cho phép thực hiện kiểm tra hoặc chuẩn bị tham số trước khi gọi constructor khác trong cùng lớp bằng `this(...)`.

```java
public final class UserName {
    private final String value;

    public UserName(String value) {
        this.value = value;
    }

    public UserName(String rawValue, boolean trim) {
        if (rawValue == null) {
            throw new IllegalArgumentException("rawValue must not be null");
        }

        String normalized = trim ? rawValue.trim() : rawValue;
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        this(normalized);
    }
}
```

Constructor thứ hai kiểm tra và chuẩn hóa tham số trước, sau đó ủy quyền việc gán field cho constructor thứ nhất. Trong một constructor chỉ có một lời gọi tường minh: `this(...)` hoặc `super(...)`, không thể gọi cả hai.

## Quy tắc khi không viết super(...)

Với constructor của class thông thường, nếu constructor không chứa lời gọi constructor tường minh, Java tự chèn lời gọi `super()` ngầm định. Phần thân constructor khi đó được thực thi sau lời gọi ngầm định này. Record có quy tắc constructor riêng được trình bày ở phần tiếp theo.

Điều đó có nghĩa đoạn mã sau **không** kiểm tra trước constructor lớp cha:

```java
class Child extends Base {
    Child(int value) {
        validate(value); // Chạy sau super() ngầm định.
    }

    private static void validate(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
    }
}
```

Nếu cần validation trước constructor lớp cha, hãy đặt `super(...)` tường minh sau phần prologue:

```java
class Child extends Base {
    Child(int value) {
        validate(value);
        super();
    }

    private static void validate(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
    }
}
```

Ở đây `validate` phải là static method. Nếu đây là instance method, trình biên dịch từ chối lời gọi vì instance chưa sẵn sàng.

## Constructor của record

Record cũng có thể dùng câu lệnh trước lời gọi `this(...)` trong non-canonical constructor. Ví dụ:

```java
record Pair<T extends Number>(T x, T y) { }

record RectanglePair(float length, float width) {
    public RectanglePair(Pair<Float> corner) {
        if (corner == null) {
            throw new IllegalArgumentException("corner must not be null");
        }

        float x = corner.x().floatValue();
        float y = corner.y().floatValue();
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("coordinates must not be negative");
        }

        this(x, y);
    }
}
```

Constructor `RectanglePair(Pair<Float>)` không phải canonical constructor, vì vậy nó phải ủy quyền cho canonical constructor bằng `this(x, y)`. Các phép kiểm tra và tính toán trong prologue giúp bảo đảm dữ liệu hợp lệ trước khi ủy quyền.

Compact canonical constructor của record là trường hợp khác: nó được dùng để kiểm tra hoặc chuẩn hóa các tham số thành phần, còn compiler tự sinh các phép gán component field. Không đưa lời gọi `super(...)` hoặc `this(...)` vào compact canonical constructor.

## Kiểm tra lỗi biên dịch

Khi học một thay đổi cú pháp, hãy kiểm tra cả ví dụ hợp lệ và ví dụ cố ý sai. Điều này giúp phân biệt lỗi cú pháp cũ với giới hạn thực sự của early construction context.

### Trường hợp hợp lệ

Tệp `PositiveBigInteger.java` dùng validation trước `super(...)`:

```java
import java.math.BigInteger;

public final class PositiveBigInteger extends BigInteger {
    public PositiveBigInteger(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        super(Long.toString(value));
    }
}
```

Trên JDK 25 hoặc JDK 27, biên dịch mà không bật preview:

```bash
javac --release 25 PositiveBigInteger.java
```

Hoặc kiểm tra theo ngôn ngữ JDK 27:

```bash
javac --release 27 PositiveBigInteger.java
```

Cả hai lệnh đều sử dụng cú pháp final. Không thêm `--enable-preview`.

### Trường hợp không hợp lệ: đọc field trước super(...)

```java
class InvalidChild extends Base {
    private int id;

    InvalidChild(int value) {
        if (this.id != value) { // Lỗi: đọc instance field trong prologue.
            throw new IllegalArgumentException();
        }
        super();
    }
}
```

Compiler báo lỗi vì prologue không được đọc field của instance đang khởi tạo. Nếu muốn lưu tham số, hãy gán field bằng `this.id = value;` trước `super()`; không đọc lại field trong prologue.

### Trường hợp không hợp lệ: gọi instance method

```java
class InvalidChild extends Base {
    InvalidChild(int value) {
        if (!isValid(value)) { // Lỗi: isValid là instance method.
            throw new IllegalArgumentException();
        }
        super();
    }

    private boolean isValid(int value) {
        return value > 0;
    }
}
```

Đổi `isValid` thành `private static boolean isValid(int value)` thì lời gọi trong prologue hợp lệ. Thông báo lỗi cụ thể có thể khác giữa các phiên bản compiler, nhưng nguyên nhân vẫn là truy cập instance trước khi constructor lớp cha chạy.

### Cách kiểm tra bằng compiler

Lưu ví dụ hợp lệ và không hợp lệ vào các tệp riêng, sau đó chạy `javac --release 27`. Ví dụ hợp lệ phải biên dịch; ví dụ không hợp lệ phải thất bại. Không gộp hai lớp có cùng tên vào một lần biên dịch.

Để kiểm tra lịch sử preview, JDK 24 từng yêu cầu `--enable-preview --release 24` khi biên dịch Flexible Constructor Bodies và `java --enable-preview` khi chạy class tương ứng. Đây chỉ là thông tin lịch sử; bài học và mã ứng dụng hiện hành nên dùng JDK 25+ ở chế độ không preview.

## Ghi chú về preview trên JDK 27

JEP 513 và JEP 512 đều là tính năng final, không cần preview. Java SE 27 có JEP 532 (*Primitive Types in Patterns, instanceof, and switch*) ở trạng thái preview lần thứ năm; bài học này không sử dụng tính năng đó. Nếu thử nghiệm JEP 532 riêng, dùng `javac --enable-preview --release 27` và chạy bằng `java --enable-preview`.

Oracle Java SE 27 còn ghi chú một tương tác riêng trong phần Flexible Constructor Bodies: khi bật preview features, constructor của record tuân theo early construction context như value class. Ví dụ compact constructor gọi `this.toString()` có thể biên dịch ở chế độ ổn định nhưng bị từ chối khi bật preview. Đây là lưu ý về chế độ preview trong tài liệu JDK 27, không làm JEP 513 trở thành preview. Nếu tái hiện riêng tình huống này, dùng `javac --enable-preview --release 27` và chạy class bằng `java --enable-preview`; không bật preview cho các bài tập constructor thông thường.

```java
record Bag(String contents) {
    public Bag {
        if (contents == null) {
            throw new IllegalArgumentException("null argument: " + this.toString());
        }
    }
}
```

Để kiểm tra JEP 512 trên JDK 25+, có thể dùng một compact source file làm chương trình thử ngắn:

```java
void main() {
    IO.println("Flexible Constructor Bodies are final in Java 25+");
}
```

Lưu thành `CheckFeature.java`, sau đó chạy `javac --release 25 CheckFeature.java` và `java CheckFeature`. `IO` thuộc `java.lang`; gọi method tĩnh bằng `IO.println(...)` vì các static method của `IO` không được tự động import vào compact source file.

## Khi nào nên dùng?

Flexible Constructor Bodies hữu ích khi constructor cần:

- Kiểm tra tham số và ném exception trước khi tạo phần lớp cha.
- Chuẩn hóa dữ liệu đầu vào rồi truyền kết quả cho `super(...)` hoặc `this(...)`.
- Khởi tạo một số field của lớp con trước khi constructor lớp cha có thể gọi method được override.

Không nên dùng prologue để đưa nhiều logic nghiệp vụ vào constructor. Giữ phần này ngắn, xác định rõ dữ liệu nào chỉ là tham số/local và field nào được phép gán. Tránh để constructor lớp cha gọi method có thể override; việc gán field trước `super(...)` là công cụ xử lý một tình huống cần thiết, không phải lý do để thiết kế constructor lớp cha phụ thuộc vào trạng thái lớp con.

## Tự kiểm tra

1. JEP 513 trở thành tính năng chính thức từ JDK nào? Có cần `--enable-preview` không?
2. Vì sao `this.id = id` có thể hợp lệ trong prologue nhưng `if (this.id < 0)` lại không hợp lệ?
3. Nếu constructor không viết `super(...)`, validation trong thân constructor có chạy trước constructor lớp cha không?
4. Khi nào nên dùng `this(...)` thay vì `super(...)` sau phần prologue?
5. Vì sao không nên gọi instance method trong early construction context?
6. JEP 512 có thay đổi quy tắc khởi tạo constructor không?

## Tài liệu tham khảo

- [JEP 513: Flexible Constructor Bodies](https://openjdk.org/jeps/513)
- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
- [Java SE 27 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html)
- [Java SE 27 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [Java SE 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
