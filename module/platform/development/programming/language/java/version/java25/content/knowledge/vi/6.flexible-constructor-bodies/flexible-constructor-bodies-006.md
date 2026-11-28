# Phép gán trường được phép trước super và giới hạn truy cập trạng thái đối tượng

> **Chương:** Hàm khởi tạo linh hoạt
>
> **Phiên bản:** Java 25, **JEP 513 — Flexible Constructor Bodies**, đã chính thức (không cần `--enable-preview`). Bài học chỉ dùng ngữ nghĩa còn áp dụng trong Java hiện đại, phân biệt rõ việc **ghi trường** được cho phép với việc **đọc hoặc làm lộ đối tượng** vẫn bị cấm trong giai đoạn khởi tạo sớm.

## 1. Vấn đề: muốn chuẩn bị trạng thái trước khi gọi superclass

Một lớp con có thể cần kiểm tra dữ liệu, chuẩn bị các tham số cho constructor cha và thiết lập một phần trạng thái trước khi superclass được khởi tạo. Điều này đặc biệt liên quan đến trường hợp không lý tưởng: constructor cha gọi một method có thể được override, khiến method của lớp con nhìn thấy các field còn giá trị mặc định.

Trong Java cũ, lời gọi `super(...)` hoặc `this(...)` phải đứng đầu constructor, nên code thường phải đưa validation vào static helper, vào biểu thức đối số hoặc đợi sau `super(...)` mới gán field. **Java 25 chính thức hóa Flexible Constructor Bodies (JEP 513)**: cho phép một đoạn **prologue** chứa một số lệnh trước explicit constructor invocation.

Điều dễ nhầm nhất: “không được dùng `this` trước `super`” **không còn đúng nếu diễn giải tuyệt đối**. Java 25 cho phép **`this.field = value`** trong điều kiện cụ thể, nhưng vẫn không cho phép đọc field, gọi instance method hay truyền reference `this` đi.

Trong bài này, trọng tâm không phải làm cho mọi constructor dài hơn. Mục tiêu là hiểu chính xác ranh giới ngôn ngữ để xử lý invariant, `final` field, constructor chaining và lỗi biên dịch mà **không làm lộ object chưa khởi tạo xong**.

### Sau bài học, bạn sẽ

1. Phân biệt prologue, explicit `super(...)`/`this(...)`, epilogue và early construction context.
2. Viết phép gán đơn `this.field = ...` trước `super(...)` cho **field do class hiện tại khai báo, không có initializer**.
3. Giải thích vì sao `this.field++`, `field += 1`, `System.out.println(field)` và `this.helper()` không hợp lệ trước `super(...)`.
4. Xử lý `blank final`, trật tự chạy field initializer, instance initializer và constructor chaining.
5. Viết test/bảng dự đoán thứ tự gọi constructor và chuẩn bị bản nâng cấp JDK có kiểm soát.

## 2. Mô hình constructor của Java 25

Một constructor có lời gọi tường minh tới constructor khác được nhìn theo ba vùng:

~~~java
class Parent {
    Parent(int capacity) {
        System.out.println("Parent: " + capacity);
    }
}

class Child extends Parent {
    final String name;

    Child(String rawName, int capacity) {
        // 1) PROLOGUE: validate, tính toán, gán field hợp lệ.
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        String cleaned = java.util.Objects.requireNonNull(rawName).strip();
        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException("name is empty");
        }
        this.name = cleaned;       // Hợp lệ: blank final thuộc Child.

        // 2) EXPLICIT CONSTRUCTOR INVOCATION.
        super(capacity);

        // 3) EPILOGUE: có thể truy cập object đã qua constructor cha.
        System.out.println("Child: " + name);
    }
}
~~~

Trong constructor này:

- **Prologue**: tất cả các statement nằm trước `super(capacity)`.
- **Early construction context**: prologue **và** những biểu thức bên trong `super(...)`/`this(...)`. Ở đây truy cập current instance bị hạn chế.
- **Epilogue**: các statement nằm sau explicit invocation. Lúc này các quy tắc truy cập instance thông thường có hiệu lực, dù constructor vẫn chưa hoàn tất.

Trạng thái object tại mỗi thời điểm:

~~~mermaid
flowchart TD
    A["Cấp phát object, field nhận giá trị mặc định"] --> B["Child constructor: prologue"]
    B --> C{"Có validation exception?"}
    C -->|"Có"| X["Dừng xây dựng, không gọi constructor cha"]
    C -->|"Không"| D["super(...)"]
    D --> E["Khởi tạo superclass theo chuỗi kế thừa"]
    E --> F["Field initializers / instance initializers của Child"]
    F --> G["Child constructor: epilogue"]
    G --> H["Constructor hoàn tất"]
~~~

**Điểm rất quan trọng:** trước khi constructor cha chạy, JVM đã cấp phát object và đặt các field về giá trị mặc định. Bởi vậy phép gán sớm có thể ghi vào vùng nhớ field thuộc lớp con. Nhưng Java vẫn ngăn các thao tác **đọc hoặc làm lộ instance chưa được xây dựng đầy đủ**.

Nếu constructor **không viết rõ** `super(...)` hoặc `this(...)`, compiler hiểu có `super()` ngầm ở **đầu** constructor và toàn bộ các statement bạn viết thuộc **epilogue**. Do đó muốn thay đổi thời điểm gán field từ “sau cha” thành “trước cha” thì phải viết explicit `super()` đúng vị trí.

## 3. Điều kiện cho phép gán field trước super

Phép gán field trong prologue là một **ngoại lệ hẹp** của giới hạn early construction context. Một trường hợp hợp lệ phải đáp ứng:

1. Dùng **phép gán đơn `=`** vào một instance field của **chính class đang khai báo constructor**.
2. Field ấy **không có initializer ngay trong khai báo** (`int count;` hoặc `final String id;`, không phải `int count = 0;`).
3. Vế phải là biểu thức có thể đánh giá **mà không đọc trạng thái current instance**. Có thể dùng constructor parameters, local variables, constants, static helpers hoặc một object đã được truyền vào.
4. Nếu là `final`, vẫn phải tuân theo kiểm tra **definite assignment / definite unassignment**: không gán hai lần và phải được gán trên những đường chạy yêu cầu.
5. Không dùng field đó qua một thao tác đọc trước explicit constructor invocation, **kể cả vừa gán xong**.

### Ví dụ hợp lệ: gán cả trường thường và blank final

~~~java
// File: EarlyWrite.java
class Base {
    Base() {}
}

public class EarlyWrite extends Base {

    private final String code;    // Blank final: không có initializer.
    private int quantity;         // Không có initializer.

    EarlyWrite(String rawCode, int count) {
        String normalized = java.util.Objects.requireNonNull(rawCode).strip();
        if (normalized.isEmpty() || count <= 0) {
            throw new IllegalArgumentException("Invalid input");
        }

        this.code = normalized;  // GHI field được phép.
        quantity = count;        // GHI bằng tên đơn cũng được phép.
        super();                 // Explicit superclass constructor.

        // Sau super(), có thể đọc fields như bình thường.
        System.out.println(code + ":" + quantity);
    }

    public static void main(String[] args) {
        new EarlyWrite(" A-10 ", 3);
    }
}
~~~

~~~bash
javac --release 25 EarlyWrite.java
java EarlyWrite
~~~

Kết quả:

~~~text
A-10:3
~~~

`this.code` là **ngoại lệ chỉ để ghi**; từ khóa `this` ở đây không cho phép bạn thực hiện những cách sử dụng khác của instance. Trong cùng prologue, `this.code` không thể dùng như giá trị của biểu thức `super(...)`.

## 4. Không được đọc field, kể cả sau khi gán

Đây là quy tắc dễ sai nhất. **Được gán không có nghĩa đã được phép đọc** trước `super(...)`.

~~~java
// Mẫu sai — các dòng ERROR được chú thích, KHÔNG biên dịch nguyên khối.
class Parent {
    Parent() {}
}

class WrongAccess extends Parent {
    int value;

    WrongAccess(int input) {
        this.value = input;             // OK: gán đơn.
        // int current = this.value;    // ERROR: đọc trường của current instance.
        // int also = value;            // ERROR: đọc không qualified cũng bị cấm.
        // System.out.println(value);   // ERROR: ngầm đọc field.
        // this.value++;                // ERROR: ++ vừa đọc vừa ghi.
        // value += 1;                  // ERROR: compound assignment đọc trước khi ghi.
        // System.out.println(this);    // ERROR: đưa this ra ngoài.
        // inspect();                    // ERROR: gọi instance method.
        // this.inspect();               // ERROR: gọi qua this.
        // super.toString();             // ERROR: gọi qua super.
        super();

        int after = this.value;         // OK: đã qua explicit super().
        System.out.println(after);
    }

    void inspect() {}
}
~~~

| Câu lệnh trong prologue | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `this.value = input;` | **Có** | Gán trực tiếp field do lớp hiện tại khai báo, không có initializer. |
| `value = input;` | **Có** | Vế trái là field của lớp hiện tại, không phải thao tác đọc. |
| `int copy = value;` | **Không** | Đọc field của current instance. |
| `int copy = this.value;` | **Không** | `this` không được dùng để lấy giá trị field sớm. |
| `value += 1;` | **Không** | `+=` phải đọc giá trị cũ. |
| `this.value++;` | **Không** | `++` phải đọc giá trị cũ. |
| `process(this);` | **Không** | Làm reference object chưa khởi tạo thoát ra ngoài. |
| `this.process();`, `process();` | **Không** | Gọi method trên instance đang xây dựng. |
| `super.value = input;` | **Không** | Không được dùng `super` để truy cập instance field trong early context. |
| `int doubled = input * 2;` | **Có** | Chỉ đọc constructor parameter/local variable. |
| `int checked = Math.max(input, 1);` | **Có** | Gọi static method, không chạm current instance. |

Để tính toán dựa vào giá trị vừa chuẩn hóa, hãy giữ nó trong **local variable**, rồi gán field; không “đọc ngược” field trong prologue:

~~~java
class FormData {
    final String normalized;
    final int length;

    FormData(String raw) {
        String local = java.util.Objects.requireNonNull(raw).strip();
        this.normalized = local;
        this.length = local.length();  // OK: đọc local, không đọc field.
        super();
    }
}
~~~

Trong ví dụ trên, `local.length()` là method trên **local reference đã tồn tại**, không phải method của object `FormData` đang xây dựng. Java không cấm gọi mọi instance method trong prologue; điều bị cấm là gọi method trên **current instance** (hoặc phụ thuộc vào instance chưa tạo xong).

## 5. Chỉ field không có declaration initializer mới được gán sớm

Khác biệt giữa hai khai báo sau quyết định việc gán trước `super()` có hợp lệ:

~~~java
class Parent {
    Parent() {}
}

class Allowed extends Parent {
    int count;            // Không có initializer.

    Allowed(int count) {
        this.count = count; // OK.
        super();
    }
}
~~~

~~~java
// Ví dụ CỐ Ý SAI: không biên dịch trên Java 25.
class Disallowed extends Parent {
    int count = 0;        // Có declaration initializer.

    Disallowed(int count) {
        this.count = count; // ERROR: không được gán initialized field trước super.
        super();
    }
}
~~~

**Lý do:** với `super(...)`, các **field initializers** và **instance initializer blocks** của lớp con chạy **sau khi superclass constructor hoàn thành**. Nếu trường đã có initializer tại khai báo, việc gán sớm rồi bị initializer ghi đè sẽ gây nhầm lẫn. Java 25 chặn phép gán sớm vào field như vậy.

Đừng viết `int count = 0;` chỉ để “tự khởi tạo mặc định”: instance field kiểu `int` vốn được JVM cấp giá trị mặc định `0`. Nhưng cũng **đừng xóa initializer có ý nghĩa nghiệp vụ** chỉ để dùng tính năng mới. Nếu giá trị mặc định được chủ ý khai báo, hãy tiếp tục gán sau `super(...)` hoặc xem lại thiết kế.

### Instance initializer block cũng cần được xem xét

~~~java
class ResettingChild extends Parent {
    int retries;           // Không có declaration initializer.

    {
        retries = 99;      // Instance initializer chạy sau super().
    }

    ResettingChild(int requested) {
        this.retries = requested;  // Có thể gán sớm vì field không có initializer.
        super();
        System.out.println(retries); // 99, không phải requested.
    }
}
~~~

Phép gán sớm có thể hợp lệ về **cú pháp** nhưng không tạo ra **trạng thái cuối** như bạn mong muốn, vì instance initializer block có thể ghi đè sau đó. Với **blank final**, các quy tắc definite assignment ngăn việc gán nhiều lần trên cùng đường chạy; không lấy ví dụ trường thường ở trên để suy luận rằng gán đè `final` cũng hợp lệ.

## 6. Blank final: trường hợp sử dụng rất đáng giá

Một blank final field là `final` field **không gán giá trị ngay tại khai báo**:

~~~java
final String requestId;
~~~

Java 25 cho phép gán field này trong prologue bằng `this.requestId = ...`, nếu không có assignment trùng lặp về sau và các đường chạy hợp lệ đều gán trước khi constructor kết thúc.

~~~java
// File: RequestEnvelope.java
class Envelope {
    Envelope(int payloadSize) {
        if (payloadSize < 0) {
            throw new IllegalArgumentException("Negative size");
        }
    }
}

public class RequestEnvelope extends Envelope {
    private final String requestId;

    RequestEnvelope(String rawId, int size) {
        String clean = java.util.Objects.requireNonNull(rawId).strip();
        if (clean.isBlank()) {
            throw new IllegalArgumentException("Request id required");
        }
        this.requestId = clean;      // Blank final được gán đúng một lần.
        super(size);                 // Không dùng this.requestId trong đối số.
    }

    String requestId() { return requestId; }

    public static void main(String[] args) {
        System.out.println(new RequestEnvelope(" R-7 ", 128).requestId());
    }
}
~~~

### Tránh gán lần hai

~~~java
// CỐ Ý SAI: field final được gán hai lần.
class BadFinal extends Envelope {
    final String requestId;

    BadFinal(String raw) {
        this.requestId = raw;             // Gán sớm.
        super(raw.length());
        // this.requestId = raw.strip();  // ERROR nếu mở comment: gán lần hai.
    }
}
~~~

Nếu cần chuẩn hóa, tính toán vào một **biến local** trước, rồi gán một lần. Với nhiều nhánh `if/else`, compiler dùng quy tắc definite assignment để kiểm tra mọi đường đi; `final` không biến thành mutable field chỉ vì Java 25 có prologue.

## 7. Thứ tự khởi tạo và trường hợp superclass gọi method override

Java luôn cho phép constructor của superclass gọi một method có thể bị override, nhưng đó là **thiết kế có rủi ro** vì tại thời điểm này subclass chưa hoàn tất khởi tạo. Đôi khi JEP 513 giúp giảm nguy cơ đọc phải field mặc định.

### 7.1. Gán sau super: method override thấy giá trị mặc định

~~~java
// File: VirtualDispatchDemo.java
class Base {
    Base() {
        onCreated();
    }

    void onCreated() {}
}

class LateChild extends Base {
    final int id;

    LateChild(int id) {
        super();
        this.id = id;
    }

    @Override
    void onCreated() {
        System.out.println("LateChild: " + id);
    }
}

class EarlyChild extends Base {
    final int id;

    EarlyChild(int id) {
        this.id = id;     // Ghi sớm, không đọc.
        super();
    }

    @Override
    void onCreated() {
        System.out.println("EarlyChild: " + id);
    }
}

public class VirtualDispatchDemo {
    public static void main(String[] args) {
        new LateChild(42);
        new EarlyChild(42);
    }
}
~~~

Kết quả:

~~~text
LateChild: 0
EarlyChild: 42
~~~

Trong `EarlyChild`, field `id` đã được ghi trước khi `Base()` gọi `onCreated()`. Tuy nhiên **đây không phải lý do để khuyến khích constructor cha gọi method có thể override**:

- Các field khác của subclass vẫn có thể chưa được khởi tạo.
- Instance initializers của subclass vẫn chưa chạy.
- Đối tượng có thể bị rò rỉ qua callback hoặc listener trong constructor cha.
- Một thay đổi nhỏ ở subclass có thể phá assumption của superclass trong tương lai.

**Thiết kế ưu tiên:** tránh gọi method có thể override từ constructor; khởi tạo xong rồi mới kích hoạt callback hoặc qua factory/lifecycle phase rõ ràng. Gán sớm là cơ chế cần hiểu để xử lý code hiện hữu hoặc invariant đặc biệt, không phải phương pháp thay thế thiết kế lifecycle tốt.

### 7.2. Timeline chi tiết

| Giai đoạn | `LateChild(42)` | `EarlyChild(42)` |
| --- | --- | --- |
| Cấp phát | `id = 0` | `id = 0` |
| Prologue | Trống | `id = 42` |
| Constructor `Base()` | Gọi override, đọc `0` | Gọi override, đọc `42` |
| Subclass instance initializers | Chạy sau `Base()` | Chạy sau `Base()` |
| Epilogue | Gán `id = 42` | Không cần gán lần nữa |
| Sau hoàn tất | `42` | `42` |

Nếu `id` có initializer tại khai báo (`final int id = 1;`), không thể làm phép gán sớm `this.id = 42` như mẫu trên. Đừng bỏ qua quy tắc của mục 5.

## 8. Prologue hợp lệ cho validation và biến local

Không phải constructor nào cũng cần gán field trước `super`. **Giá trị thực tế thường đến từ validation và tính toán local**:

~~~java
// File: CheckedCapacity.java
class Capacity {
    Capacity(int value) {
        System.out.println("Base capacity: " + value);
    }
}

public class CheckedCapacity extends Capacity {

    CheckedCapacity(int requested) {
        if (requested <= 0) {
            throw new IllegalArgumentException("Capacity must be positive");
        }
        int aligned = Math.multiplyExact(requested, 2);
        super(aligned);        // Dùng biến local, không đọc field.
    }

    public static void main(String[] args) {
        new CheckedCapacity(4);
    }
}
~~~

Ở đây có thể gọi `Math.multiplyExact` vì đây là **static method**. Nếu `requested` không hợp lệ thì `throw` xảy ra **trước khi bắt đầu gọi constructor cha**; các side effect trong constructor cha không xảy ra. Tương tự, `Objects.requireNonNull(param)` hoặc method trên object tham số có thể được sử dụng nếu không truy cập current instance.

### Không được ẩn super trong if

~~~java
// CỐ Ý SAI: explicit constructor invocation không được đặt trong branch.
class ConditionalChild extends Capacity {
    ConditionalChild(int value) {
        // if (value > 0) {
        //     super(value);   // ERROR: vị trí không hợp lệ.
        // } else {
        //     super(1);       // ERROR: vị trí không hợp lệ.
        // }
        // Ví dụ này được comment để không biến thành code chạy.
        super(value > 0 ? value : 1); // Một constructor invocation rõ ràng.
    }
}
~~~

Constructor body có nhiều statement, nhưng vẫn có **tối đa một explicit constructor invocation** theo cú pháp JLS. Không gọi `super(...)` hai lần, không đặt nó vào lambda/loop/nhánh điều kiện để “chọn constructor”.

## 9. this(...) cũng có prologue, nhưng phải để ý final field

JEP 513 không giới hạn ở `super(...)`; constructor có thể kiểm tra/tính toán trước `this(...)` khi gọi một constructor khác **của cùng lớp**.

~~~java
// File: UserSession.java
public class UserSession {
    private final String id;
    private final int timeoutSeconds;

    UserSession(String id, int timeoutSeconds) {
        this.id = id;
        this.timeoutSeconds = timeoutSeconds;
    }

    UserSession(CharSequence rawId) {
        String normalized = java.util.Objects.requireNonNull(rawId)
                .toString().strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("id is empty");
        }
        this(normalized, 30); // Có lệnh ở trước this(...).
    }

    public static void main(String[] args) {
        var session = new UserSession(new StringBuilder(" S-8 "));
        System.out.println(session.id + ":" + session.timeoutSeconds);
    }
}
~~~

Kết quả:

~~~text
S-8:30
~~~

**Không gán blank final trước `this(...)` rồi để constructor được gọi gán lại.** JLS §16 yêu cầu các blank final của class phải **definitely unassigned** sau danh sách đối số của alternate constructor invocation. Trong đa số thiết kế, hãy để constructor **đích** chịu trách nhiệm gán field final; constructor ủy quyền chỉ chuẩn hóa/kiểm tra tham số qua local variables.

~~~java
// CỐ Ý SAI nếu mở comment: gán final trước khi ủy quyền qua this(...).
class BadDelegation {
    final int id;

    BadDelegation(int id) {
        this.id = id;
    }

    BadDelegation(String text) {
        int parsed = Integer.parseInt(text);
        // this.id = parsed; // ERROR: blank final không được gán trước this(...).
        this(parsed);
    }
}
~~~

**Một constructor không thể trực tiếp hoặc gián tiếp gọi chính nó** qua chuỗi `this(...)`. Quy tắc này không đổi ở Java 25.

## 10. Quy tắc truy cập: cái gì được và không được dùng trước super

### 10.1. Tổng hợp

| Thao tác trong prologue của `Child` | Cho phép? | Diễn giải |
| --- | --- | --- |
| Kiểm tra constructor parameter, dùng local variable | Có | Chưa truy cập current instance. |
| Gọi `Objects.requireNonNull(value)`, `Math.max(...)` | Có | Static methods chỉ xử lý input. |
| Gọi `value.strip()` khi `value` là tham số | Có | Method trên object truyền vào, không phải `this`. |
| `this.own = value` | Có điều kiện | `own` phải do `Child` khai báo, không có initializer. |
| `own = value` | Có điều kiện | Tương tự, `own` là field cùng class, không có initializer. |
| `this.own++`, `own += n` | Không | Đọc giá trị hiện tại. |
| `int copy = own`, `log(own)` | Không | Đọc field current instance. |
| `inherited = value`, `super.inherited = value` | Không | Không gán/read inherited field qua current instance trong early context. |
| `this.doWork()`, `doWork()` | Không | Instance method của current instance. |
| `System.out.println(this)` | Không | Làm lộ reference current instance. |
| `staticCounter++` (trường static truy cập hợp lệ) | Hợp lệ về ngôn ngữ | Nhưng side effect toàn cục trong constructor thường không đáng khuyến khích. |
| Dùng `Outer.this` từ early context của một *inner class* | Có điều kiện | Có thể truy cập outer instance đã tồn tại; khác với `this` của inner instance đang xây dựng. |

### 10.2. Instance inner class của chính lớp đang xây dựng

~~~java
// CỐ Ý SAI nếu mở comment.
class Outer {
    class Inner {}

    Outer() {
        // Inner inner = new Inner(); // ERROR trước super(): cần Outer.this chưa an toàn.
        super();
        Inner inner = new Inner();    // OK sau super().
    }
}
~~~

Ở prologue của **một inner class**, `Outer.this` chỉ outer object đã tồn tại có thể có quy tắc khác. Nhưng không suy ra có thể tạo inner instance của **chính object đang xây dựng** trước `super()`.

## 11. Câu chuyện record và enum: không áp dụng sai phạm vi

### Record

Một record có canonical constructor quản lý các component fields; **record constructor không được gọi `super(...)`**. Tuy nhiên một **non-canonical constructor** có thể đặt validation và local computations trước lời gọi `this(...)` bắt buộc:

~~~java
// File: Dimensions.java
public record Dimensions(int width, int height) {

    public Dimensions(int side) {
        if (side <= 0) {
            throw new IllegalArgumentException("side must be positive");
        }
        int value = Math.multiplyExact(side, 2);
        this(value, value);
    }
}
~~~

Trong record, **không cố gán component field trực tiếp ở non-canonical constructor trước `this(...)`**. Constructor ủy quyền phải gọi canonical constructor; cách tốt nhất là truyền đối số đã chuẩn hóa vào `this(...)` như trên.

### Enum

Constructor của enum không được gọi `super(...)` tường minh. Đừng sao chép ví dụ về `this.field = ...; super();` từ class thường sang enum. Những hạn chế riêng của enum và quá trình tạo constants vẫn phải được giữ; nên dùng constructor enum thông thường cho các tham số bất biến, không lợi dụng JEP 513 để biến enum thành đối tượng có lifecycle tùy ý.

## 12. Tương thích Java 25 và chiến lược nâng cấp

JEP 513 từng trải qua nhiều vòng preview ở các JDK trước, nhưng **đã final từ Java 25**. Những ví dụ dùng `super(...)` sau các statement và phép gán sớm vào field theo quy tắc này **không cần `--enable-preview` khi biên dịch bằng JDK 25**.

~~~bash
java -version
javac --release 25 -d out EarlyWrite.java
java -cp out EarlyWrite
~~~

Chỉ sử dụng lệnh cho file ví dụ tồn tại. Nếu làm theo bài và lưu nhiều đoạn code vào cùng thư mục, hãy đặt chúng theo tên `public class` để không tạo xung đột về các class `Parent`/`Base` trong các ví dụ riêng rẽ.

### Ma trận tương thích

| Loại dự án | Quyết định |
| --- | --- |
| Ứng dụng nội bộ chạy đúng Java 25+ | Có thể dùng flexible constructor bodies nếu giảm độ phức tạp, có test rõ ràng. |
| Dịch vụ nâng từ Java 21 lên 25 | Tách bài toán **nâng runtime** khỏi việc dùng **cú pháp mới**; không refactor hàng loạt trước khi qua test hồi quy. |
| Thư viện vẫn công bố hỗ trợ Java 17/21 | Không đưa prologue có field assignment trước `super(...)` vào source biên dịch `--release 17/21`. |
| Thư viện nâng minimum JDK lên 25 | Công bố yêu cầu mới, test với toolchain và toàn bộ consumer quan trọng. |
| Code do generator/Lombok sinh | Xác minh phiên bản compiler/IDE/annotation processors có hỗ trợ cú pháp JDK 25; không suy luận chỉ từ `java -version`. |
| Preview examples từ Java 22–24 | Đọc lại JEP 513/JLS SE 25; không đánh đồng tài liệu preview với quy tắc final. |

Đây là tính năng **ngôn ngữ**; nó không tự cải thiện throughput, GC, AOT cache hay JFR. Với service quan trọng, giá trị của thay đổi chủ yếu nằm ở tính đúng đắn và cấu trúc khởi tạo; hiệu năng vẫn cần đo riêng nếu có lý do.

## 13. Bảng chẩn đoán lỗi biên dịch thường gặp

| Triệu chứng / mẫu code | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `cannot reference this before supertype constructor...` khi `System.out.println(this)` | Làm lộ current instance. | Bỏ tham chiếu `this` khỏi prologue. |
| Báo lỗi khi `this.field++` | `++` đọc giá trị field cũ. | Tính giá trị qua local/param rồi gán bằng `=`, hoặc chuyển thao tác sau `super`. |
| Báo lỗi khi `int x = this.field;` | Không được đọc field trước explicit invocation. | Dùng local variable; chỉ đọc sau `super(...)`. |
| Lỗi gán initialized field | Field có initializer tại khai báo. | Gán sau `super(...)` hoặc giữ initializer; không xóa default có chủ đích. |
| Lỗi `final field already assigned` | Blank final bị gán nhiều lần hoặc qua hai constructor. | Để một nơi chịu trách nhiệm gán và kiểm tra mọi đường đi. |
| Báo lỗi `this.foo()` / `super.foo()` | Không gọi instance method của current instance trong prologue. | Dùng static helper/parameter method; gọi instance method sau `super`. |
| Gán `super.field = value` không hợp lệ | Đang truy cập superclass part trước khi nó được khởi tạo. | Để superclass tự khởi tạo field qua constructor params/API. |
| `super(...)` bị đặt bên trong `if` | Grammar chỉ cho phép invocation ở vị trí xác định, không nằm trong branch. | Validation ở prologue; dùng biểu thức/biến local để chọn tham số. |
| Prologue gán field nhưng giá trị sau constructor bị đổi | Instance initializer block/field initializer chạy sau `super(...)`. | Kiểm tra thứ tự khởi tạo và không gán sớm nếu không cần. |
| Source chạy Java 25 nhưng fail trên 21 | Cú pháp chưa final ở release thấp hơn, class file target cao hơn. | Cố định `--release` theo minimum JDK và test phiên bản cũ. |

**Quan trọng:** thông báo lỗi chính xác của `javac`/IDE có thể khác giữa minor release hoặc công cụ biên dịch. Xác minh bản JDK, source/release level và code thực tế trước khi chẩn đoán; bảng mô tả **nguyên nhân**, không khẳng định mọi compiler in cùng một chuỗi thông báo.

## 14. Bài tập thực hành

### Bài A — Gán blank final trước super

Tạo `Ticket.java` gồm `TicketBase(int seat)` và `Ticket(String code, int seat)`. Trong `Ticket`:

1. Khai báo `private final String normalizedCode;` **không có initializer**.
2. Validation `seat > 0`; tính `String normalized = code.strip().toUpperCase(java.util.Locale.ROOT)` từ input.
3. Gán `this.normalizedCode = normalized` trước `super(seat)`.
4. In field ra console sau `super(...)`; thử code rỗng và seat không hợp lệ.

**Tiêu chí đạt:** không đọc field ở prologue, không gán blank final hai lần, input không hợp lệ không kích hoạt side effect của parent constructor.

### Bài B — Dự đoán compile

Với `int retries;` (không initializer) ở class con, đánh dấu mỗi dòng trong prologue là **hợp lệ/không hợp lệ** và giải thích:

~~~java
this.retries = 3;
int local = 3 * 2;
// int copy = retries;
// retries += 1;
// this.toString();
super();
~~~

Thử bỏ comment từng dòng lỗi **trong một class ví dụ riêng**. Đừng bỏ comment tất cả cùng lúc, vì lỗi đầu tiên sẽ che mất lỗi còn lại. Đối chiếu kết quả với JLS SE 25 và bảng mục 4.

### Bài C — Phân tích sự khác nhau khi có initializer

So sánh hai class con:

- Class X: `int quantity;` và `this.quantity = value; super();`.
- Class Y: `int quantity = 1;` và cùng code.

**Câu hỏi:** cái nào biên dịch? Nếu đổi class Y sang gán sau `super()` thì giá trị cuối là bao nhiêu? Thêm instance initializer block vào class X có thể tác động ra sao?

### Bài D — Constructor cha gọi method override

Chạy `VirtualDispatchDemo` ở mục 7, ghi lại hai giá trị in ra. Sau đó **thiết kế lại**: bỏ callback từ `Base()`, cung cấp một method `start()` gọi **sau khi constructor hoàn tất**. Giải thích vì sao thiết kế mới an toàn hơn, kể cả khi Java 25 cho phép gán sớm.

### Bài E — Constructor chaining

Viết hai overload của `Session`:

- `Session(String normalized, int timeout)` gán các blank final fields.
- `Session(CharSequence raw)` tính local, kiểm tra và gọi `this(normalized, 30)`.

**Điều kiện:** overload thứ hai **không gán final field trước `this(...)`**. Viết test xác nhận giá trị và lỗi đầu vào.

## 15. Checklist đưa vào codebase hiện đại

Trước khi dùng field assignment trước `super(...)` ở mã thật:

- [ ] **JDK 25+** và source/release target tương thích; không bật preview flag cho JEP 513 đã final.
- [ ] Có **explicit `super(...)`** đúng chỗ; không nhầm body với prologue khi chỉ có implicit `super()`.
- [ ] Field được gán thuộc **chính class hiện tại** và **không có declaration initializer**.
- [ ] Dùng **`=`**; không đọc current instance qua `field`, `this.field`, `++`, `+=` hoặc method call.
- [ ] Với blank final, đã kiểm tra **definite assignment**, không gán trùng giữa constructors/initializers.
- [ ] Không gọi `this`/`super` method hoặc làm rò reference object đang xây dựng.
- [ ] Đã rà lại field initializers và instance initializer blocks có thể ghi đè state sau `super`.
- [ ] Không dùng field trước `this(...)` khi constructor đích còn trách nhiệm gán final fields.
- [ ] Validation chỉ phụ thuộc input/local/static state phù hợp; có test trường hợp exception.
- [ ] Không dùng JEP 513 như lý do để superclass gọi overridable method trong constructor; xem lại lifecycle nếu có thể.
- [ ] Có test compile/runtime bằng **JDK 25 thật**, không chỉ tin IDE, không chạy “di trú tự động” toàn bộ constructor đang ổn định.

### Tài liệu chính thức

1. [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513) — feature final trong JDK 25 và động cơ thiết kế.
2. [Java SE 25 Language Guide — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html) — prologue, early construction context, gán field trước `super(...)`, record và nested classes.
3. [Java SE 25 JLS §8.8.7 — Constructor Body](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7) — cú pháp prologue/epilogue và implicit invocation.
4. [Java SE 25 JLS §8.8.7.1 — Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7.1) — giới hạn invocation, thứ tự initialization.
5. [Java SE 25 JLS §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se25/html/jls-16.html) — gán blank final, kiểm tra khi delegation qua `this(...)`.
6. [Java SE 25 JLS §15.8.3 — `this`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.8.3) và [§15.11.2 — `super`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.11.2) — điều kiện dùng references trong early construction context.
7. [Java SE 25 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html) — vị trí của JEP 513 so với các thay đổi ngôn ngữ Java 25.

**Kết luận:** Java 25 cho phép **ghi có kiểm soát** vào field của lớp con trước `super(...)`, đặc biệt hữu ích cho **blank final** hoặc xử lý invariant trước superclass initialization. Nhưng việc **đọc current instance, gọi method trên nó, truy cập superclass state hoặc cho reference `this` thoát ra ngoài** vẫn bị cấm. Hiểu đúng khác biệt giữa **write** và **read**, trật tự **prologue → constructor cha → initializers → epilogue** cùng quy tắc final assignment là cách áp dụng JEP 513 an toàn, còn giá trị lâu dài.
