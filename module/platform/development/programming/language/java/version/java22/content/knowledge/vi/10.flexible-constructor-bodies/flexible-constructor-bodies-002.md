# Tổ chức phần xử lý trước và sau lời gọi constructor super hoặc this

## Flexible Constructor Bodies trong Java hiện đại

Trong module `JAVA_VERSION_JAVA22`, cần phân biệt phiên bản giới thiệu một tính năng với trạng thái của nó trên JDK hiện hành. Flexible Constructor Bodies xuất hiện lần đầu dưới dạng preview ở JDK 22 với JEP 447, tiếp tục được preview ở JDK 23 và JDK 24, rồi trở thành tính năng ngôn ngữ chính thức trong JDK 25 theo JEP 513. Trên JDK 25, 26 và 27, có thể dùng tính năng này mà không bật `--enable-preview`.

**Trạng thái hiện tại:** JEP 513 là stable từ JDK 25. Những ví dụ trong bài dùng cú pháp chính thức từ JDK 25 trở lên. Các phiên bản preview JDK 22–24 chỉ được nhắc đến để giải thích lịch sử và lưu ý khi nâng cấp.

Trước đây, lời gọi tường minh `super(...)` hoặc `this(...)` phải đứng đầu thân constructor. Quy tắc này khiến lập trình viên khó kiểm tra dữ liệu hoặc tính toán đối số trước khi constructor của lớp cha chạy. Flexible Constructor Bodies cho phép đặt các câu lệnh hợp lệ trước lời gọi constructor, miễn là phần xử lý đó không truy cập đối tượng đang được khởi tạo theo cách bị cấm.

Thân constructor vì thế có thể gồm hai phần:

- **Prologue:** các câu lệnh đứng trước lời gọi constructor tường minh `super(...)` hoặc `this(...)`.
- **Epilogue:** các câu lệnh đứng sau lời gọi constructor đó.

```java
class Child extends Parent {
    Child(String input) {
        // Prologue: kiểm tra và chuẩn bị dữ liệu
        String normalized = input.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("input must not be blank");
        }

        super(normalized);

        // Epilogue: có thể sử dụng this và thành viên instance
        System.out.println(this.getClass().getSimpleName());
    }
}
```

## 1. Vì sao cần prologue và epilogue?

Constructor thường phải chuẩn bị đối số cho lớp cha, kiểm tra điều kiện hợp lệ hoặc thiết lập một số trường của lớp con trước khi constructor lớp cha chạy. Trước JDK 25, một số việc phải được đẩy vào phương thức `static`, lồng trực tiếp trong đối số `super(...)`, hoặc thực hiện sau khi constructor lớp cha đã chạy.

Ví dụ, nếu lớp cha xác nhận dữ liệu trong constructor, lớp con có thể kiểm tra đầu vào trước khi gọi lớp cha:

```java
class Message {
    private final String text;

    Message(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

class NonEmptyMessage extends Message {
    NonEmptyMessage(String raw) {
        String normalized = java.util.Objects.requireNonNull(raw).strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("message must not be blank");
        }

        super(normalized);
    }
}
```

Nếu dữ liệu không hợp lệ, constructor ném exception ngay trong prologue. Constructor của `Message` chưa được gọi, nên không phát sinh các side effect của lớp cha cho đối tượng không hợp lệ.

Prologue cũng có thể tính toán nhiều giá trị bằng biến cục bộ rồi truyền kết quả vào `super(...)` hoặc `this(...)`. Cách này giúp phần kiểm tra và chuẩn bị dữ liệu có cấu trúc rõ ràng, thay vì nhồi toàn bộ biểu thức vào danh sách đối số constructor.

## 2. Early construction context và giới hạn truy cập đối tượng

Các câu lệnh trong prologue và các biểu thức đối số của `super(...)` hoặc `this(...)` thuộc *early construction context* — ngữ cảnh khởi tạo sớm. Đối tượng hiện tại chưa hoàn tất bước gọi constructor lớp cha, vì vậy mã trong ngữ cảnh này không được sử dụng nó như một đối tượng đã khởi tạo.

Trong early construction context, nhìn chung không được:

- Dùng biểu thức `this` để đọc hoặc truyền đối tượng đang khởi tạo.
- Đọc trường instance của lớp đang khởi tạo hoặc trường instance kế thừa từ lớp cha.
- Gọi phương thức instance hoặc tạo method reference gắn với đối tượng đang khởi tạo.
- Truy cập thành viên hoặc gọi phương thức của lớp cha qua `super`.
- Tạo inner class cần chính đối tượng đang khởi tạo làm enclosing instance.

Có thể dùng tham số constructor, biến cục bộ, hằng và phương thức `static`, hoặc đối tượng độc lập khác. Những thao tác đó không cần truy cập instance chưa hoàn tất.

Ví dụ không hợp lệ:

```java
class InvalidChild extends Parent {
    private int value;

    InvalidChild(int value) {
        System.out.println(this.value); // Không được đọc instance field ở prologue.
        printValue();                    // Không được gọi instance method ở prologue.
        super();
    }

    void printValue() { }
}
```

Riêng phép gán trường được xét theo ngoại lệ hẹp ở phần tiếp theo: chỉ một phép gán đơn giản vào trường instance được khai báo trong chính lớp đó và không có initializer mới được phép trong prologue.

## 3. Gán trường instance trước khi gọi super

Một điểm quan trọng của JEP 513 là cho phép gán trường instance của lớp đang khởi tạo trước `super(...)`, nếu trường đó được khai báo mà không có initializer. Điều này hữu ích khi constructor lớp cha gọi một phương thức có thể được override ở lớp con.

Xét lớp cha gọi một hook trong constructor:

```java
class Base {
    Base() {
        showState();
    }

    void showState() {
        System.out.println("Base");
    }
}
```

Nếu lớp con chỉ gán `id` sau khi constructor lớp cha hoàn tất, hook override có thể nhìn thấy giá trị mặc định `0`:

```java
class Child extends Base {
    private final int id;

    Child(int id) {
        super();
        this.id = id;
    }

    @Override
    void showState() {
        System.out.println("id = " + id);
    }
}
```

Khi `Base()` gọi `showState()`, phương thức được dispatch đến `Child.showState()` trước khi câu lệnh gán `id` chạy. Kết quả in ra là `id = 0`.

Với Flexible Constructor Bodies, có thể gán blank field trước `super()`:

```java
class SafeChild extends Base {
    private final int id;

    SafeChild(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }

        this.id = id;
        super();
    }

    @Override
    void showState() {
        System.out.println("id = " + id);
    }
}
```

Khi `Base()` gọi hook, `id` đã được gán và kết quả là `id =` giá trị truyền vào. Câu lệnh gán này là ngoại lệ được ngôn ngữ cho phép trong early construction context.

### Quy tắc của phép gán sớm

| Thao tác trước `super(...)` | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `this.id = id;` | Có, nếu `id` là field khai báo trong lớp hiện tại và không có initializer | Đây là phép gán đơn giản vào blank instance field được cho phép. |
| `id = id + 1;` với `id` là field instance | Không | Cần đọc giá trị hiện tại của field. |
| `this.id++;` | Không | Phép tăng cần đọc field và không phải phép gán đơn giản được cho phép. |
| `System.out.println(this.id);` | Không | Đọc trạng thái của đối tượng đang khởi tạo. |
| `this.print();` hoặc `print();` | Không | Gọi phương thức instance trước khi superclass constructor hoàn tất. |
| `this.name = name;` nếu `name` đã có initializer | Không | Ngoại lệ chỉ áp dụng cho field được khai báo mà không có initializer. |
| `staticValidate(value);` | Có | Gọi phương thức static không cần instance đang khởi tạo. |

Các phép gán sớm vẫn phải tuân thủ quy tắc definite assignment của Java. Một blank `final` field chỉ được gán đúng một lần trên mọi đường đi hợp lệ. Không thể dùng ngoại lệ này để đọc field chưa được khởi tạo hoặc để thay đổi field đã có initializer.

**Lưu ý về an toàn thiết kế:** ví dụ trên giải quyết trường hợp constructor lớp cha gọi phương thức override. Tuy nhiên, gọi phương thức có thể override từ constructor vẫn là thiết kế cần thận trọng vì các field khác của lớp con và các instance initializer chưa chạy. Hãy ưu tiên tránh gọi phương thức override trong constructor lớp cha; chỉ dùng gán sớm khi cần tương thích với API hiện có hoặc có lý do rõ ràng.

## 4. Chuẩn bị dữ liệu trước lời gọi this(...)

`this(...)` gọi một constructor khác trong cùng lớp. Prologue cho phép kiểm tra hoặc chuẩn hóa dữ liệu trước khi chuyển quyền khởi tạo cho constructor đích.

Ví dụ lớp `Port` nhận đầu vào dạng chuỗi rồi chuyển sang constructor nhận số nguyên:

```java
import java.util.Objects;

class Port {
    private final int number;

    Port(String raw) {
        String normalized = Objects.requireNonNull(raw).strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("port is required");
        }

        int parsed = Integer.parseInt(normalized);
        this(parsed);
    }

    Port(int number) {
        if (number < 1 || number > 65_535) {
            throw new IllegalArgumentException("port out of range");
        }

        this.number = number;
    }

    int number() {
        return number;
    }
}
```

Constructor `Port(String)` chuẩn hóa và phân tích chuỗi trước khi gọi `this(parsed)`. Constructor `Port(int)` chịu trách nhiệm xác thực miền giá trị và gán field. Nhờ vậy, mọi đường tạo đối tượng đều dùng chung logic khởi tạo số cổng.

Khi constructor dùng `this(...)`, constructor được gọi sẽ chịu trách nhiệm hoàn tất chuỗi khởi tạo. Không gán cùng blank final field ở constructor gọi rồi lại gán trong constructor đích; quy tắc definite assignment yêu cầu các blank final field vẫn chưa được gán sau danh sách đối số của lời gọi constructor thay thế.

## 5. Khi không viết super() hoặc this() tường minh

Nếu thân constructor không có lời gọi constructor tường minh, Java tự chèn lời gọi `super()` không đối số. Các câu lệnh trong thân constructor khi đó thuộc epilogue và chạy sau constructor lớp cha.

Ví dụ:

```java
class Child extends Parent {
    Child(int value) {
        validate(value);
        // super() ngầm định đã được gọi trước câu lệnh này.
    }

    private static void validate(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative value");
        }
    }
}
```

Đoạn trên vẫn gọi constructor `Parent()` trước khi chạy `validate(value)`. Nếu muốn validation chạy trước constructor lớp cha, hãy viết lời gọi tường minh sau prologue:

```java
class Child extends Parent {
    Child(int value) {
        validate(value);
        super();
    }

    private static void validate(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative value");
        }
    }
}
```

Một constructor chỉ có tối đa một lời gọi constructor tường minh: hoặc `this(...)`, hoặc `super(...)`. Không thể đặt hai lời gọi này trong các nhánh `if` khác nhau. Nếu cần chọn nhiều cách khởi tạo, hãy tính đối số trong prologue rồi gọi một constructor phù hợp, hoặc dùng static factory method để chọn constructor.

## 6. Constructor của record

Record có các quy tắc khởi tạo riêng:

- Record không thể gọi `super(...)` tường minh.
- Constructor không canonical phải gọi một constructor khác của cùng record bằng `this(...)`.
- Các câu lệnh có thể đứng trước `this(...)` trong constructor không canonical để phân tích hoặc kiểm tra dữ liệu.
- Constructor canonical chịu trách nhiệm khởi tạo các component; compact canonical constructor dùng cơ chế gán component tự động sau phần thân compact constructor.

Ví dụ một record nhận chuỗi tọa độ:

```java
record Point(int x, int y) {
    Point(String text) {
        String[] parts = java.util.Objects.requireNonNull(text)
            .split(",", -1);

        if (parts.length != 2) {
            throw new IllegalArgumentException("Expected x,y");
        }

        int parsedX = Integer.parseInt(parts[0].strip());
        int parsedY = Integer.parseInt(parts[1].strip());
        this(parsedX, parsedY);
    }
}
```

Constructor `Point(String)` là noncanonical. Nó phân tích dữ liệu trong prologue rồi gọi canonical constructor `Point(int, int)` bằng `this(...)`.

### Caveat preview riêng trên JDK 27

Flexible Constructor Bodies đã stable từ JDK 25. Tuy nhiên, tài liệu Java SE 27 ghi rõ một thay đổi liên quan đến preview features: nếu bật preview features trên JDK 27, constructor code của record được xem là nằm trong early construction context, tương tự value class đang được preview. Vì vậy, việc gọi instance method hoặc sử dụng `this` trong phần thân constructor record có thể bị compiler từ chối khi bật preview.

Đây là hành vi gắn với preview features của JDK 27, không phải điều kiện để sử dụng JEP 513 stable. Với ứng dụng không dùng preview, áp dụng quy tắc record constructor của Java SE 25+ như bình thường. Không bật `--enable-preview` chỉ để dùng Flexible Constructor Bodies.

## 7. Trình tự khởi tạo và ảnh hưởng đến field initializer

Trong quá trình tạo đối tượng lớp thường, các bước quan trọng có thể hình dung như sau:

1. Bộ nhớ cho đối tượng được cấp phát và các field nhận giá trị mặc định (`0`, `false`, `null`).
2. Prologue của constructor chạy nếu có lời gọi constructor tường minh; tại đây chỉ được thực hiện các thao tác hợp lệ trong early construction context.
3. Lời gọi `super(...)` được thực hiện. Sau khi constructor lớp cha hoàn tất, các instance field initializer và instance initializer của lớp hiện tại chạy theo thứ tự văn bản.
4. Epilogue của constructor hiện tại chạy.

Khi constructor gọi `this(...)`, constructor được gọi tiếp tục chuỗi khởi tạo và cuối cùng gọi constructor lớp cha. Các constructor trong chuỗi không chạy lại toàn bộ field initializer của cùng lớp nhiều lần.

Điểm cần nhớ là gán một blank field trong prologue xảy ra trước khi instance initializer chạy. Java chỉ cho phép gán sớm vào field không có initializer để tránh trường hợp giá trị vừa gán bị một field initializer ghi đè sau lời gọi `super(...)`.

## 8. Khi nào nên dùng Flexible Constructor Bodies?

| Tình huống | Cách sử dụng |
| --- | --- |
| Kiểm tra tham số trước khi constructor lớp cha thực hiện side effect | Đặt validation trong prologue rồi gọi `super(...)`. |
| Chuẩn hóa hoặc chuyển đổi tham số trước khi truyền lên lớp cha | Tạo biến cục bộ trong prologue rồi truyền biến vào `super(...)`. |
| Chuyển dữ liệu từ một constructor overload sang constructor chính | Phân tích dữ liệu rồi gọi `this(...)`. |
| Constructor lớp cha gọi hook override và hook cần đọc blank field của lớp con | Cân nhắc gán blank field trước `super(...)`, đồng thời xem xét lại thiết kế gọi phương thức override trong constructor. |
| Cần dùng `this`, đọc field hoặc gọi instance method | Đặt xử lý sau `super(...)`/`this(...)` trong epilogue. |
| Cần nhiều nhánh lựa chọn constructor hoặc logic tạo object phức tạp | Dùng static factory method hoặc builder để chọn cách khởi tạo. |

## 9. Lịch sử preview và cách biên dịch

| JDK | Trạng thái | JEP |
| --- | --- | --- |
| 22 | Preview lần đầu, tên ban đầu là *Statements before super(...)* | JEP 447 |
| 23 | Preview lần thứ hai, đổi tên thành *Flexible Constructor Bodies* | JEP 482 |
| 24 | Preview lần thứ ba | JEP 492 |
| 25 | Stable, không còn yêu cầu bật preview | JEP 513 |
| 26 và 27 | Stable | JEP 513 |

Khi biên dịch bằng JDK 25 trở lên, có thể dùng cú pháp bình thường:

```bash
javac --release 25 -d out src/example/NonEmptyMessage.java
```

Hoặc nếu dự án nhắm đến JDK 27:

```bash
javac --release 27 -d out src/example/NonEmptyMessage.java
```

Không thêm `--enable-preview` cho Flexible Constructor Bodies trên các JDK này. Nếu duy trì mã nguồn preview cũ từ JDK 22–24, hãy kiểm tra và chuyển sang đặc tả stable JEP 513; không mặc định rằng cờ preview của release cũ có thể dùng nguyên trạng trên JDK mới.

## Kết luận

Flexible Constructor Bodies chia constructor thành prologue và epilogue, cho phép xác thực, chuẩn hóa và chuẩn bị dữ liệu trước `super(...)` hoặc `this(...)`. Phần prologue vẫn chịu giới hạn của early construction context: không đọc hoặc gọi instance đang khởi tạo, ngoại trừ phép gán đơn giản vào blank field của lớp hiện tại theo quy tắc Java. JEP 513 đã stable từ JDK 25, vì vậy có thể dùng tính năng này trên JDK hiện đại mà không bật preview. Khi làm việc với record trên JDK 27 có bật preview features, cần lưu ý quy tắc early construction context mở rộng được tài liệu JDK 27 mô tả.

## Tài liệu tham khảo

- [JEP 513: Flexible Constructor Bodies](https://openjdk.org/jeps/513)
- [JEP 447: Statements before super(...)](https://openjdk.org/jeps/447)
- [Java SE 27 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html)
- [Java SE 27 — The Java Language Specification, Chapter 8: Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html)
- [Java SE 25 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-summary.html)
- [JDK 25 Release Notes: Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html)
