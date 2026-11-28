# Tái cấu trúc hàm khởi tạo dài và kiểm thử tính bất biến của đối tượng

## 1. Bối cảnh, bài toán và mục tiêu

Bài này thuộc chương **Hàm khởi tạo linh hoạt** của module **JAVA_VERSION_JAVA25**. Java 25 có nhiều khả năng hữu ích cho phát triển Java hiện đại — compact source files, module import, flexible constructor bodies, `ScopedValue`, API dẫn xuất khóa, AOT cache và JFR. Ở đây chúng ta tập trung vào **JEP 513 — Flexible Constructor Bodies**, được chuẩn hóa trong **Java 25**, để cải thiện cách thiết kế constructor, quản lý trạng thái và bảo đảm đối tượng hợp lệ ngay từ khi được tạo.

Một constructor dài thường làm đồng thời quá nhiều việc:

- Kiểm tra tham số (null, chuỗi trống, giới hạn số, khoảng thời gian).
- Chuẩn hóa dữ liệu (bỏ khoảng trắng, chuyển định dạng).
- Chuyển cấu trúc mutable bên ngoài thành bản sao riêng.
- Truyền dữ liệu cho constructor lớp cha.
- Gán hàng loạt field, đôi khi khởi tạo side effects.
- Gặp lỗi sau khi lớp cha đã thực hiện công việc mà đáng ra nên tránh nếu input sai.

Một giải pháp thiếu thận trọng chỉ “dời tất cả dòng lên trước `super(...)`” có thể **không biên dịch**, hoặc vẫn tạo một object có trạng thái có thể thay đổi gián tiếp. Vì vậy phải thiết kế đồng thời **construction order**, **invariant** và **immutability**.

### Kết quả mong đợi

Sau bài học, bạn có thể:

1. Mô tả `prologue`, `super(...)`/`this(...)` và `epilogue` trong constructor Java 25.
2. Nhận biết thao tác **được phép** trước constructor invocation và thao tác **không được phép** trong *early construction context*.
3. Refactor constructor dài theo các bước: xác định invariant → validate/normalize input → tạo defensive snapshot → phân trách nhiệm cho value object → gọi parent → công bố trạng thái an toàn.
4. Phân biệt `final`, immutable object, defensive copy và *deep immutability*.
5. Kiểm thử việc từ chối input sai **trước side effect** của parent constructor; kiểm tra đối tượng không bị thay đổi sau khi khởi tạo.
6. Xây dựng bộ kiểm thử hồi quy JUnit 5 cho mọi đường khởi tạo và trường hợp mutable aliasing.
7. Giải thích vì sao **Java 25 không cần `--enable-preview` cho JEP 513** và không mang các quy tắc preview cũ vào môi trường hiện tại.

Bài tập gồm mã nguồn Java 25 minh họa và các đoạn JUnit 5. Đây là tài liệu hướng dẫn; chúng ta **chưa chạy build/test**, cần chạy trên JDK 25 trong dự án của bạn để xác nhận hành vi thực tế.

## 2. JEP 513 đã là tính năng chính thức trong Java 25

Các bản Java 22, 23 và 24 từng có những vòng preview của feature “statements before `super(...)`”. **Từ Java 25, JEP 513 — Flexible Constructor Bodies là tính năng permanent.** Không cấu hình `--enable-preview` chỉ để dùng nội dung bài này.

Cú pháp cũ vẫn hợp lệ:

~~~java
class Base {
    Base(String code) { }
}

class OldStyle extends Base {
    OldStyle(String input) {
        super(input);
        // Kiểm tra và xử lý sau khi super(...) đã chạy.
    }
}
~~~

Java 25 cho phép:

~~~java
class Base {
    Base(String code) {
        System.out.println("Base constructed for " + code);
    }
}

class NewStyle extends Base {

    NewStyle(String input) {
        // PROLOGUE: chạy trước super(...).
        String normalized = java.util.Objects.requireNonNull(input).strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("code must not be blank");
        }

        super(normalized);

        // EPILOGUE: chạy sau khi super(...) hoàn tất.
        System.out.println("Subclass constructed");
    }
}
~~~

Đoạn ví dụ hoạt động với `javac`/`java` của JDK 25; không phụ thuộc vào API preview hay incubator.

Điều mới là **có thể thực hiện thao tác cần thiết ở đầu constructor** trước khi ủy quyền khởi tạo cho lớp cha hoặc cho một constructor khác cùng lớp. Điều không thay đổi: quy trình tạo object vẫn tuân thủ ngữ nghĩa của Java và các hạn chế đối với việc đọc/dùng object chưa được khởi tạo hoàn tất.

Tham khảo chính: [Oracle Java 25 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html), [JLS 25 `8.8.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7).

## 3. Vòng đời khởi tạo: prologue, invocation, epilogue

Một constructor có lời gọi tường minh `super(...)` hoặc `this(...)` được chia thành:

~~~text
Constructor Child(...)
├── Prologue: các statement trước lời gọi constructor
├── super(...) HOẶC this(...)  (tối đa một lời gọi tường minh)
└── Epilogue: các statement sau lời gọi constructor
~~~

Theo quy tắc JLS, constructor invocation không thể được đặt tùy ý trong nhánh `if` hoặc một vòng lặp; nó thuộc cú pháp đặc biệt của constructor body. Đừng tưởng Java 25 cho phép hai lời gọi `super(...)` khác nhau trên hai nhánh điều kiện.

### 3.1. Điều gì chạy khi gọi super?

Ở mức khái niệm, với `Child extends Parent` và constructor có `super(...)`:

~~~mermaid
sequenceDiagram
    participant App as Mã gọi new Child(...)
    participant Child as Constructor Child
    participant Parent as Constructor Parent
    participant Fields as Field initializer của Child

    App->>Child: new Child(input)
    Child->>Child: Prologue: kiểm tra, chuẩn hóa, gán field được phép
    Child->>Parent: super(đối số đã chuẩn bị)
    Parent-->>Child: Parent constructor hoàn tất
    Child->>Fields: Chạy instance field/instance initializer của Child
    Fields-->>Child: Hoàn tất
    Child->>Child: Epilogue
    Child-->>App: Trả về instance đã khởi tạo
~~~

**Điểm tinh tế:** instance field initializers và instance initializer blocks của lớp con thường chạy sau lời gọi superclass constructor. Vì vậy nếu gán một trường trước `super(...)`, trường đó phải là trường mà phép gán sớm được JLS cho phép. Không khai báo initializer rồi cố gán lại cùng một blank `final` trong prologue.

Nếu constructor **không viết `super(...)` hoặc `this(...)`**, Java vẫn chèn lời gọi superclass constructor không tham số **ngầm định** trước phần thân được xem là epilogue. Muốn chạy validation *trước* parent không tham số, bạn phải viết `super();` tường minh ở đúng vị trí sau validation.

### 3.2. Early construction context

*Early construction context* bao gồm statement của prologue **và biểu thức đối số** trong `super(...)`/`this(...)`. Đây là thời điểm chưa được tùy ý dùng đối tượng đang được tạo.

| Thao tác trước `super(...)` | Hợp lệ? | Lý do |
| --- | --- | --- |
| Kiểm tra một tham số rồi `throw IllegalArgumentException` | Có | Không đọc trạng thái instance |
| Khai báo/gán biến local và chuẩn hóa `String` | Có | Hoàn toàn từ tham số/local |
| Gọi static helper hoặc dùng `Objects.requireNonNull` | Có | Không phụ thuộc instance chưa xây xong |
| Tạo `List.copyOf(input)` | Có | Xây snapshot từ dữ liệu input |
| Gán một blank field được khai báo **trong class hiện tại** và **không có initializer** bằng phép `=` đơn giản | Có, nếu tuân thủ definite assignment | Ngoại lệ được JLS cho phép cho việc thiết lập sớm field |
| Đọc `this.field` hoặc `field` của current instance | Không | Đọc trạng thái instance trước khởi tạo |
| `this.field++` hoặc `this.field += 1` | Không | Phép toán cần đọc giá trị field hiện tại |
| Gọi instance method `validate()` của object đang tạo | Không | Có thể dùng `this` và trạng thái chưa hoàn tất |
| Gọi `super.someMethod()` / đọc `super.field` | Không | Truy cập superclass instance trong early context |
| `System.out.println(this)` hoặc truyền `this` vào callback | Không | Object chưa hoàn tất, nguy cơ escape |
| Gán một field có initializer hoặc field của superclass từ prologue | Không | Không thuộc ngoại lệ được phép |
| Đặt `super(...)` trong nhánh `if` | Không | Sai cấu trúc constructor invocation |
| Viết `return;` trong constructor | Không | Constructor không cho return statement |

**Cẩn thận với `this`:** `this.value = prepared;` có thể hợp lệ nếu `value` là blank field của **chính lớp đang được khởi tạo**, nhưng dùng `this` theo các cách khác trong prologue bị giới hạn. Vì vậy câu “cấm mọi thứ có từ `this` trước `super`” là một cách diễn giải quá mức; câu “được tùy ý gọi method trên `this`” cũng sai.

## 4. Case study: một constructor dài có nhiều invariant

Chúng ta xây một miền nghiệp vụ đơn giản: **Subscription**.

Một subscription có:

- `UUID id` do lớp cha `EntityBase` quản lý.
- `accountCode`: không null, sau chuẩn hóa không rỗng.
- `Plan`: chính sách gồm số ghế được phép và danh sách tính năng đã chuẩn hóa.
- `startsAt` và `endsAt`: thời gian bắt đầu phải nhỏ hơn thời gian kết thúc.

**Bất biến cần bảo vệ:**

| Trường | Invariant |
| --- | --- |
| `id` | Không null |
| `accountCode` | Không null, không blank, không chứa khoảng trắng ở đầu/cuối |
| `plan.seats` | Lớn hơn 0 |
| `plan.features` | Snapshot không sửa được; item không null/blank và đã chuẩn hóa |
| `startsAt` | Không null |
| `endsAt` | Không null và **sau** `startsAt` |
| Đối tượng tổng thể | Không có public setter; không lộ collection mutable |

Với input bất hợp lệ, object **không được trả về** và ideally phải ngăn những side effect không cần thiết ở parent constructor.

### 4.1. Thiết kế ban đầu: nhiều tham số, logic rải rác

Ví dụ trước khi refactor (đoạn minh họa kỹ thuật, không phải thiết kế được đề xuất):

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

class EntityBase {
    private final UUID id;

    EntityBase(UUID id) {
        this.id = id;
    }

    public UUID id() { return id; }
}

final class SubscriptionLegacy extends EntityBase {
    private final String accountCode;
    private final int seats;
    private final List<String> features;
    private final Instant startsAt;
    private final Instant endsAt;

    SubscriptionLegacy(UUID id, String code, int seats,
                       List<String> features,
                       Instant startsAt, Instant endsAt) {
        super(id);
        this.accountCode = code;
        this.seats = seats;
        this.features = features;
        this.startsAt = startsAt;
        this.endsAt = endsAt;
    }
}
~~~

Constructor trên có nhiều vấn đề:

- `id`/`code` có thể null, `seats` có thể âm, khoảng thời gian có thể đảo.
- `features` giữ **reference đến List do caller sở hữu**, không tạo defensive snapshot.
- `final List<String> features` chỉ làm reference không thể gán lại; **nội dung List vẫn có thể bị thay đổi từ bên ngoài**.
- Constructor quá nhiều tham số cùng kiểu khiến việc đảo thứ tự dễ qua mắt code review.
- Chưa thể kiểm soát thứ tự validation so với công việc của constructor lớp cha.

**Không** kết luận “mọi constructor có sáu tham số đều sai”. Vấn đề là chúng biểu diễn nhiều khái niệm khác nhau và chưa có invariant rõ.

## 5. Bước refactor 1: nhóm giá trị thành immutable value object

Sử dụng `record Plan` để gom hai tham số liên quan; record có field cuối cùng nhưng vẫn phải **copy collection mutable**.

Tạo `src/Plan.java`:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public record Plan(int seats, List<String> features) {

    public Plan {
        if (seats <= 0) {
            throw new IllegalArgumentException("seats must be positive");
        }

        Objects.requireNonNull(features, "features");

        List<String> cleaned = features.stream()
            .map(value -> Objects.requireNonNull(value, "feature"))
            .map(String::strip)
            .map(value -> value.toUpperCase(Locale.ROOT))
            .toList();

        if (cleaned.isEmpty() || cleaned.stream().anyMatch(String::isBlank)) {
            throw new IllegalArgumentException("features must be non-empty");
        }

        if (cleaned.stream().distinct().count() != cleaned.size()) {
            throw new IllegalArgumentException("duplicate features");
        }

        // Thay parameter của record compact constructor.
        // Java sẽ gán bản snapshot này vào field của record.
        features = List.copyOf(cleaned);
    }
}
~~~

**Đã bảo vệ được gì?**

1. `seats` luôn dương trong mọi `Plan` khởi tạo thành công.
2. String từng phần tử được chuẩn hóa thành mã tính năng cố định.
3. `List.copyOf(...)` tạo list không sửa được; không lộ alias mutable từ caller.
4. `String` là kiểu immutable, nên danh sách này có thể xem là deep immutable ở tầng phần tử.
5. `Plan` là record không có setter và được thiết kế như một value object.

**Giới hạn:** record tự nó **không mặc nhiên deep immutable** nếu component chứa array, `List` mutable, `Date` hay một object mutable. Ở đây ta phải chủ động tạo defensive snapshot. Ngoài ra, input collection không nên bị thread khác sửa đồng thời lúc copy/normalize; nếu workflow đa luồng, cần đồng bộ/giao thức sở hữu input thích hợp.

### 5.1. Test cần viết ngay cho Plan

Kiểm tra bốn nhóm:

- `seats <= 0` bị từ chối.
- `features` null, rỗng, chứa null/blank hoặc trùng sau normalize bị từ chối.
- Thay đổi `ArrayList` đầu vào sau khi tạo không làm thay đổi `plan.features()`.
- Gọi `plan.features().add(...)` bị từ chối.

Đây là test **giá trị**, độc lập với Spring Boot hoặc bất kỳ framework DI nào.

## 6. Bước refactor 2: validate và chuẩn hóa trước `super(...)`

Tạo `src/EntityBase.java`:

~~~java
import java.util.Objects;
import java.util.UUID;

public abstract class EntityBase {
    private final UUID id;

    protected EntityBase(UUID id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    public final UUID id() {
        return id;
    }
}
~~~

Lớp cha chỉ quản lý ID và **không gọi overridable method trong constructor**. Điều này giúp tránh rò rỉ một `this` chưa được khởi tạo hoàn chỉnh.

Tạo `src/Subscription.java`:

~~~java
import java.time.Instant;
import java.util.Locale;
import java.util.Objects;
import java.util.UUID;

public final class Subscription extends EntityBase {
    private final String accountCode;
    private final Plan plan;
    private final Instant startsAt;
    private final Instant endsAt;

    public Subscription(UUID id, String rawCode, Plan plan,
                        Instant start, Instant end) {

        // 1. PROLOGUE: chỉ dùng input và local.
        String normalized = Objects.requireNonNull(rawCode, "accountCode")
            .strip()
            .toUpperCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("accountCode must not be blank");
        }

        Plan validPlan = Objects.requireNonNull(plan, "plan");
        Instant validStart = Objects.requireNonNull(start, "start");
        Instant validEnd = Objects.requireNonNull(end, "end");

        if (!validStart.isBefore(validEnd)) {
            throw new IllegalArgumentException("end must be after start");
        }

        UUID validId = Objects.requireNonNull(id, "id");

        // 2. Chỉ gán các blank final field do chính Subscription khai báo.
        this.accountCode = normalized;
        this.plan = validPlan;
        this.startsAt = validStart;
        this.endsAt = validEnd;

        // 3. Gọi constructor cha SAU KHI đã validate đầy đủ.
        super(validId);

        // 4. EPILOGUE: nếu cần, chỉ thực hiện việc không làm hỏng invariant.
    }

    public String accountCode() { return accountCode; }
    public Plan plan() { return plan; }
    public Instant startsAt() { return startsAt; }
    public Instant endsAt() { return endsAt; }
}
~~~

**Tính chất quan trọng của constructor mới:**

- `Subscription` là `final`, không thể có subclass override hành vi.
- Các field của `Subscription` là **blank final fields** (không initializer) nên được phép gán sớm theo JEP 513.
- `Plan` đã tự bảo đảm trạng thái hợp lệ và trả list không sửa được.
- `UUID`, `String`, `Instant` là kiểu immutable; các getter trả về reference tới kiểu này không gây rò rỉ mutable state.
- Không có setter, không nhận trực tiếp mutable `List` trong constructor `Subscription`.
- Các kiểm tra miền nghiệp vụ xảy ra trước khi parent constructor được gọi. Nếu input sai, không chạy vào `EntityBase`.
- Constructor parent vẫn là một phần bắt buộc của việc tạo đối tượng; sắp xếp lại validation **không** bỏ qua quy trình JVM.

**Giới hạn mô hình:** `end > start` chỉ là invariant nội tại giữa hai thời điểm. Bài này không kiểm tra `end` so với `Instant.now()` vì điều đó làm test phụ thuộc đồng hồ và gây hành vi khác nhau ở các lần chạy. Nếu nghiệp vụ thực sự cần “end trong tương lai”, hãy truyền `Clock` hoặc mốc thời gian tham chiếu thay vì dùng đồng hồ hệ thống ngầm.

### 6.1. Luồng dữ liệu sau refactor

~~~mermaid
flowchart TD
    A["Input: id, rawCode, plan, start, end"] --> B["Prologue: null checks, normalize, validate range"]
    B --> C{"Hợp lệ?"}
    C -->|Không| D["Ném exception; không gọi parent constructor"]
    C -->|Có| E["Gán blank final fields của Subscription"]
    E --> F["super(validId)"]
    F --> G["EntityBase khởi tạo id"]
    G --> H["Epilogue nếu có"]
    H --> I["Subscription hoàn tất và được trả về"]
~~~

Một đối tượng đã được cấp phát ở mức JVM không đồng nghĩa đã được công bố là một instance xây dựng thành công. Constructor ném exception thì caller không nhận được object thông thường; tuy nhiên nếu constructor hoặc parent **đã làm rò rỉ `this`**, những tác hại đó không tự được rollback. Vì vậy tránh đăng ký callback, phát event, mở thread hoặc công bố reference từ constructor.

## 7. Gán field sớm: hợp lệ nhưng không phải mặc định bắt buộc

JEP 513 cho phép tình huống đặc biệt: superclass constructor có lời gọi ảo (virtual dispatch) tới một method bị override trong subclass. Nếu field của subclass chưa được khởi tạo, method ấy có thể nhìn thấy giá trị mặc định như `0` hoặc `null`.

Ví dụ dùng để hiểu ngữ nghĩa:

~~~java
class Parent {
    Parent() {
        printValue();     // Thiết kế không tốt: gọi overridable method trong constructor.
    }

    void printValue() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    final int value;

    Child(int value) {
        this.value = value;  // Blank final của Child, phép gán được phép.
        super();
    }

    @Override
    void printValue() {
        System.out.println(value);
    }
}
~~~

Nếu chạy `new Child(42)` với Java 25, callback từ parent thấy `42` thay vì `0` trong kịch bản field chưa được gán. Nhưng **đây không phải khuyến nghị dùng constructor cha gọi phương thức overridable**. Đối tượng có thể có nhiều invariant và field khác chưa sẵn sàng; khởi tạo một field sớm không bảo đảm toàn bộ object đã hợp lệ.

**Thiết kế nên ưu tiên:** parent constructor không gọi method có thể override; không publish `this`; kiểm tra data trước khi gọi parent; dùng final classes hoặc composition khi thích hợp. Field assignment sớm là một công cụ hỗ trợ, không thay thế thiết kế object lifecycle đúng.

### 7.1. Những phép gán không hợp lệ trong prologue

~~~java
class BadChild extends Parent {
    private int value = 1;  // Field có initializer.

    BadChild(int n) {
        // this.value = n;   // Không dùng phép gán sớm cho field đã có initializer.
        // value++;          // Sai: cần đọc current instance trước super.
        // System.out.println(this); // Sai: dùng this khi chưa khởi tạo xong.
        // printValue();     // Sai: gọi instance method.
        super();
        this.value = n;      // Hợp lệ sau super.
    }
}
~~~

Các dòng comment không chạy là **ví dụ cố tình sai**. Khi học, hãy thử mở từng dòng rồi biên dịch để xem lỗi tương ứng; sau đó khôi phục code hợp lệ.

### 7.2. `this(...)` và constructor chaining

Với nhiều constructor, có thể chuẩn bị dữ liệu trước lời gọi `this(...)`:

~~~java
public final class Range {
    private final int min;
    private final int max;

    public Range(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min must not exceed max");
        }
        this.min = min;
        this.max = max;
    }

    public Range(String encoded) {
        String[] parts = java.util.Objects.requireNonNull(encoded).split(":");
        if (parts.length != 2) {
            throw new IllegalArgumentException("expected min:max");
        }

        int parsedMin = Integer.parseInt(parts[0].strip());
        int parsedMax = Integer.parseInt(parts[1].strip());

        this(parsedMin, parsedMax);
    }

    public int min() { return min; }
    public int max() { return max; }
}
~~~

Constructor nhận `String` chuẩn bị hai số nguyên **trước `this(...)`**; constructor nhận hai số là nơi duy nhất gán final fields. Không tự tạo hai chỗ gán cùng một blank `final` khi dùng constructor chaining: Java yêu cầu definite assignment và không cho gán lại.

**Mẫu nên tránh:** một overload chuẩn hóa rồi tự gán một số field, sau đó `this(...)` ủy quyền cho overload khác cũng gán các field ấy; quá trình definite-assignment/constructor chaining có thể bị compiler từ chối, đồng thời gây khó đọc. Đưa việc gán vào một constructor chịu trách nhiệm chính.

### 7.3. Record và constructor ngắn hơn

Nếu đối tượng không cần kế thừa một base class, có thể dùng record. Record canonical/compact constructor có cơ chế riêng, **không dùng `super(...)` của class thường**.

Ví dụ:

~~~java
public record MoneyAmount(long minorUnits, String currency) {
    public MoneyAmount {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("negative minorUnits");
        }
        currency = java.util.Objects.requireNonNull(currency).strip();
        if (currency.isEmpty()) {
            throw new IllegalArgumentException("currency must not be blank");
        }
    }
}
~~~

Nếu cần một **noncanonical record constructor**, nó phải ủy quyền tới canonical constructor bằng `this(...)`; Java 25 cho phép validate/prepare trước lời gọi đó. Không áp dụng trực tiếp cú pháp assignment blank final kiểu class thường vào record component trong compact canonical constructor.

## 8. Kiểm thử bất biến với JUnit 5

Để khẳng định một đối tượng bất biến, test phải kiểm tra **những đường mà trạng thái có thể thay đổi**, chứ không chỉ kiểm tra constructor không ném exception.

Giả sử project có JUnit Jupiter 5 và có thể biên dịch `EntityBase.java`, `Plan.java`, `Subscription.java` bằng JDK 25. Tạo `SubscriptionTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SubscriptionTest {

    private static final UUID ID =
        UUID.fromString("aa3f810c-86b0-4ca9-9a1d-3b2c0d8e2c33");

    private static final Instant START =
        Instant.parse("2026-01-01T00:00:00Z");
    private static final Instant END =
        Instant.parse("2027-01-01T00:00:00Z");

    @Test
    void normalizesInputsAndPreservesInvariants() {
        Plan plan = new Plan(3, List.of(" audit ", "report"));

        Subscription value = new Subscription(
            ID, "  member-42  ", plan, START, END
        );

        assertAll(
            () -> assertEquals(ID, value.id()),
            () -> assertEquals("MEMBER-42", value.accountCode()),
            () -> assertEquals(3, value.plan().seats()),
            () -> assertEquals(
                List.of("AUDIT", "REPORT"),
                value.plan().features()
            ),
            () -> assertEquals(START, value.startsAt()),
            () -> assertEquals(END, value.endsAt())
        );
    }

    @Test
    void takesSnapshotOfMutableInputCollection() {
        ArrayList<String> source = new ArrayList<>();
        source.add("audit");
        source.add("report");

        Plan plan = new Plan(2, source);
        Subscription value = new Subscription(
            ID, "member-42", plan, START, END
        );

        source.set(0, "REMOVED");
        source.add("ROOT");

        assertEquals(
            List.of("AUDIT", "REPORT"),
            value.plan().features()
        );

        assertThrows(
            UnsupportedOperationException.class,
            () -> value.plan().features().add("ADMIN")
        );
    }

    @Test
    void rejectsBlankAccountAndInvalidTimeRange() {
        Plan plan = new Plan(2, List.of("AUDIT"));

        assertThrows(
            IllegalArgumentException.class,
            () -> new Subscription(ID, "  ", plan, START, END)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new Subscription(ID, "member", plan, END, START)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new Subscription(ID, "member", plan, START, START)
        );
    }

    @Test
    void rejectsNullFields() {
        Plan plan = new Plan(1, List.of("READ"));

        assertThrows(
            NullPointerException.class,
            () -> new Subscription(null, "member", plan, START, END)
        );
        assertThrows(
            NullPointerException.class,
            () -> new Subscription(ID, null, plan, START, END)
        );
        assertThrows(
            NullPointerException.class,
            () -> new Subscription(ID, "member", null, START, END)
        );
        assertThrows(
            NullPointerException.class,
            () -> new Subscription(ID, "member", plan, null, END)
        );
        assertThrows(
            NullPointerException.class,
            () -> new Subscription(ID, "member", plan, START, null)
        );
    }

    @Test
    void rejectsInvalidPlanDefinitions() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Plan(0, List.of("READ"))
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new Plan(1, List.of())
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new Plan(1, List.of("   "))
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new Plan(1, List.of("audit", "AUDIT"))
        );
        assertThrows(
            NullPointerException.class,
            () -> new Plan(1, null)
        );
    }
}
~~~

### 8.1. Đọc kết quả test đúng cách

| Test | Invariant được chứng minh | Giới hạn |
| --- | --- | --- |
| `normalizesInputsAndPreservesInvariants` | Cấu trúc dữ liệu được chuẩn hóa, getter trả trạng thái phù hợp | Chưa chứng minh mọi input đều hợp lệ |
| `takesSnapshotOfMutableInputCollection` | Không có alias đơn giản tới `ArrayList` nguồn; list công khai không sửa được | Không tự chứng minh an toàn đồng thời khi nguồn bị sửa lúc constructor đang chạy |
| `rejectsBlankAccountAndInvalidTimeRange` | Từ chối mã rỗng và quan hệ thời gian sai | Chưa kiểm thử mọi biểu diễn chuỗi |
| `rejectsNullFields` | Chính sách null rõ ràng | Exception type là một phần hợp đồng cần cân nhắc |
| `rejectsInvalidPlanDefinitions` | Chính sách giới hạn và uniqueness cho Plan | Không thay thế static analysis/review dữ liệu quy mô lớn |

**Quan trọng:** kiểm thử các trường hợp thất bại nên dựa trên input cụ thể, không so thông điệp exception nếu message chưa phải contract công khai. Nếu muốn kiểm tra message, định nghĩa rõ chính sách lỗi của API.

### 8.2. Test riêng để xác minh thất bại trước parent constructor

Một phần lợi ích của Java 25 là đưa validation lên trước lời gọi parent. Để kiểm tra thứ tự mà không đo thời gian hoặc mở network, tạo *fixture*:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class FailFastOrderTest {

    static class TrackedBase {
        static int calls = 0;

        TrackedBase() {
            calls++;
        }
    }

    static final class ValidatedChild extends TrackedBase {
        final int quantity;

        ValidatedChild(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity");
            }

            this.quantity = quantity;
            super();
        }
    }

    @Test
    void rejectsInvalidValueBeforeCallingParent() {
        TrackedBase.calls = 0;

        assertThrows(
            IllegalArgumentException.class,
            () -> new ValidatedChild(-1)
        );
        assertEquals(0, TrackedBase.calls);

        ValidatedChild good = new ValidatedChild(5);
        assertEquals(1, TrackedBase.calls);
        assertEquals(5, good.quantity);
    }
}
~~~

Đây là fixture **tuần tự**, không được thiết kế để nhiều thread chạy song song do counter static được dùng để minh họa. Trong test thực tế, có thể dùng test double an toàn luồng hoặc một dependency tách biệt khi cần quan sát side effect. **Không coi constructor cha có side effect là lựa chọn mặc định**; test này dùng để chứng minh thứ tự ngữ nghĩa.

## 9. Kiểm thử sâu: mutation, property-based và concurrency

### 9.1. Ma trận kiểm tra đầu vào

| Đầu vào | Kỳ vọng | Vì sao quan trọng |
| --- | --- | --- |
| `accountCode = null` | Từ chối | Không để null lẻn vào trạng thái |
| `accountCode = "  "` | Từ chối | Strip khiến chuỗi rỗng |
| `accountCode = " a-1 "` | Thành `"A-1"` | Chuẩn hóa có thể dự đoán |
| `plan.seats = 0` hoặc âm | Từ chối | Giá trị không hợp lệ |
| `features` rỗng | Từ chối | Plan phải có một feature |
| `features` có null | Từ chối | Không cho null element |
| `features = ["read", "READ"]` | Từ chối | Trùng sau normalize |
| `endsAt == startsAt` | Từ chối | Khoảng thời gian phải có độ dài dương |
| `endsAt < startsAt` | Từ chối | Thứ tự không hợp lệ |
| Mutation list nguồn sau tạo | Subscription không đổi | Không có mutable alias |
| Attempt sửa list trả về | Bị từ chối | Getter không lộ mutable collection |
| Input thay đổi trong lúc khởi tạo | Không giả định an toàn tuyệt đối | Caller phải quản lý concurrency hoặc snapshot có đồng bộ |

Có thể viết property-based test bằng jqwik hoặc một thư viện tương đương **nếu dự án chủ động thêm dependency**: sinh chuỗi account code, tập feature và khoảng thời gian; kiểm tra rằng mọi instance được tạo thành công đều thỏa invariant. Không cần thêm thư viện chỉ để hiểu ý tưởng này.

### 9.2. Vì sao `final` chưa phải bất biến sâu?

So sánh:

~~~java
final class ShallowBox {
    private final java.util.List<String> items;

    ShallowBox(java.util.List<String> items) {
        this.items = items; // reference final, dữ liệu VẪN mutable.
    }

    java.util.List<String> items() { return items; }
}
~~~

với:

~~~java
final class SnapshotBox {
    private final java.util.List<String> items;

    SnapshotBox(java.util.List<String> items) {
        this.items = java.util.List.copyOf(items);
    }

    java.util.List<String> items() { return items; }
}
~~~

`SnapshotBox` mạnh hơn vì list không sửa được, nhưng nếu phần tử là **mutable object**, dùng `List.copyOf` **không copy sâu từng phần tử**. Khi đó phải copy/đóng băng từng phần tử (hoặc sử dụng immutable value object).

**Trường hợp array:** nếu constructor nhận `byte[]` làm secret/payload và muốn bảo vệ snapshot, phải `clone()` hoặc dùng phương án copy thích hợp ở cả đầu vào lẫn getter. `final byte[]` vẫn chứa các phần tử có thể sửa. Với thông tin nhạy cảm, cân nhắc vòng đời dữ liệu và việc xóa buffer; bài này tập trung vào mô hình bất biến, không thay thế thiết kế bảo mật chuyên biệt.

### 9.3. Không công bố `this` trong constructor

Một anti-pattern:

~~~java
class Dangerous {
    Dangerous(java.util.function.Consumer<Dangerous> callback) {
        // callback.accept(this);   // Không công bố this khi chưa hoàn tất.
    }
}
~~~

Trong early construction context của Java 25, hành động truyền `this` như vậy không được phép. **Sau `super(...)`**, compiler có thể cho phép dùng `this`, nhưng vẫn có rủi ro lộ đối tượng trước khi các invariant/initialization hoàn tất. Tốt hơn: thiết kế factory/service khởi tạo object xong rồi mới đăng ký event listener hoặc đưa reference vào registry ngoài constructor.

### 9.4. `final` và thread safety

Final field giúp Java có các bảo đảm memory-model quan trọng khi object được xây dựng đúng. Nhưng **không tự đảm bảo thread safety** nếu:

- object lộ `this` trước khi hoàn tất constructor;
- getter trả về cấu trúc mutable;
- field tham chiếu đến phần tử mutable bị sửa đồng thời;
- parent/child constructor chạy tác vụ background hay callback khi object còn chưa ổn định.

Do đó mục tiêu nên là **safe construction + defensive copies + no escape**, không chỉ viết `final` cho từng field.

## 10. Refactor constructor dài một cách có kiểm soát

Một quy trình thực tế:

### Bước A — Liệt kê trách nhiệm

Đọc constructor hiện tại và đánh dấu từng dòng thuộc nhóm:

- Validation thuần (null, range, format).
- Normalization thuần (strip, case, canonicalization).
- Derived values (tính toán từ input).
- Defensive copy/immutable snapshot.
- Parent/alternate constructor invocation.
- Gán field.
- Side effect (DB, network, publish event, logging có tương tác bên ngoài).

Không nhét I/O và các nghiệp vụ phức tạp vào prologue chỉ vì Java 25 cho phép statement ở đó. Constructor nên càng thuần và quyết định được càng tốt.

### Bước B — Viết invariant thành test trước

Tạo test để phát hiện input sai, test snapshot và test không làm side effect trước validation. Giữ kết quả baseline. Nếu module đang chạy JDK cũ, có thể bổ sung test trước rồi đổi toolchain ở nhánh nâng cấp riêng.

### Bước C — Tạo value object cho nhóm tham số

Ở ví dụ, chuyển `seats` và `features` thành `Plan`, nhưng không nên gom mọi tham số vào một “data bag” chứa nullable fields. Mỗi value object nên chịu trách nhiệm một tập invariant có ý nghĩa.

### Bước D — Đưa pure validation và precomputation vào prologue

Chuẩn hóa `accountCode`, kiểm tra `start/end` và chụp snapshot từ input. Chỉ dùng local/static method không phụ thuộc instance đang tạo. Nếu validate ném exception thì parent constructor chưa chạy.

### Bước E — Gán blank fields hợp lệ, gọi parent một lần

Gán field của chính lớp hiện tại nếu JEP 513 cho phép và điều đó làm thiết kế rõ ràng. Với `this(...)`, ưu tiên một constructor “chính” đảm trách assignment. Giữ `super(...)`/`this(...)` ở cấp constructor body, không đưa vào `if`.

### Bước F — Loại bỏ side effect khỏi quá trình tạo object

Việc lưu DB, publish event, gắn listener, gọi web service hoặc đăng ký vào một registry nên thuộc application service/factory hoặc bước sau khi object hoàn tất. Constructor chỉ tập trung tạo trạng thái hợp lệ.

### Bước G — Chạy lại test và review đường thoát

Tìm mọi nơi tạo object (`new`, reflection, serialization framework, ORM, dependency injection). Các đường khởi tạo khác nhau có thể bỏ qua constructor đang được kiểm tra hoặc yêu cầu no-arg constructor. Immutability của domain model **không thể suy từ một constructor** nếu các cơ chế khác sửa field.

### Bước H — Kiểm tra nhánh vận hành

So runtime JDK thực sự: `java -version`, `javac -version`; đảm bảo toolchain, container và CI dùng Java 25. Không tự thêm preview flag cho JEP 513.

## 11. Những ranh giới kỹ thuật khi áp dụng Flexible Constructor Bodies

### 11.1. Không phải mọi class đều cần một constructor dài

Nếu không kế thừa class có constructor đặc biệt, một class có thể dùng record hoặc static factory đơn giản. `JEP 513` hữu ích nhất khi cần validate/prepare dữ liệu **trước khi gọi `super(...)`/`this(...)`** hoặc gán blank fields có lý do chính đáng.

### 11.2. Không dùng superclass callback như một công cụ đo invariant

Việc JEP 513 cho phép gán field sớm để callback của parent nhìn thấy giá trị đã gán **không phải lý do để parent chủ động gọi overridable method trong constructor**. Constructor của base class không nên phụ thuộc vào subclass đã khởi tạo xong, bởi các field khác và invariants có thể còn thiếu.

### 11.3. Không áp dụng một cách mù quáng cho ORM và serialization

Framework persistence có thể có yêu cầu khác: constructor không tham số, proxy subclass, field access hay việc tạo object từ dữ liệu ngoài. `final class` và `final field` trong domain model có thể không phù hợp với mọi cách ORM tạo entity. Xác nhận cơ chế instantiation/proxy của framework cụ thể; khi cần, tách **domain immutable value object** khỏi entity persistence mutable.

### 11.4. Không bỏ qua hành vi của superclass

Validation trước `super(...)` giúp fail-fast **trước khi parent chạy**, nhưng **không thể rollback parent** nếu chính nó ném exception sau khi đã làm side effect. Giữ parent constructor tối giản, thuần và không làm lộ `this` mới là giải pháp bền vững.

### 11.5. Cẩn trọng với superclass instance fields

Ngoại lệ gán field sớm chỉ áp dụng cho những trường của **lớp đang được khởi tạo** đáp ứng quy tắc JLS, không cho phép ghi tùy ý một trường của superclass trước khi nó được xây dựng. Không truy cập `super.field` hoặc `super.method()` trong prologue.

### 11.6. Giữ semantic compatibility khi refactor

Refactor constructor có thể thay đổi thứ tự exception, kiểu exception, thông điệp, thời điểm gọi parent và cách normalize. Những thay đổi này có thể quan trọng với caller, test, instrumentation hoặc audit. Ghi lại những gì được xem là hợp đồng của API rồi thay đổi có chủ đích; đừng ngầm đổi behavior chỉ để làm constructor ngắn hơn.

### 11.7. Tính năng Java 25 vẫn còn áp dụng

JEP 513 là tính năng đã **final** từ Java 25, không còn là preview của JDK 22–24. Các khả năng Java 25 khác như compact source files (JEP 512), module import declarations (JEP 511), Scoped Values (JEP 506), KDF API (JEP 510) cũng đã được chuẩn hóa, nhưng không có mối liên hệ bắt buộc với thiết kế constructor ở đây. AOT cache và JFR là công cụ runtime; chúng không thay thế kiểm thử invariant của object.

**Không dùng tài liệu preview cũ** để yêu cầu `--enable-preview` khi biên dịch những đoạn JEP 513 trong bài này.

## 12. Bài thực hành tổng hợp

**Bối cảnh:** bạn nhận một class `LegacySubscription` có sáu tham số và danh sách tính năng mutable được gán trực tiếp. Nhiệm vụ là chuyển thành thiết kế dễ review và ít rủi ro hơn.

### Chặng 1 — Khảo sát

1. Xác định các invariant của ID, account code, plan và thời gian.
2. Tìm mọi đầu ra mutable và mọi vị trí có thể công bố `this`.
3. Chạy ví dụ với `javac`/`java` JDK 25 và ghi lại hành vi của bản cũ.
4. Đặt mục tiêu không thay đổi public API ngoài những thay đổi đã được phê duyệt.

### Chặng 2 — Refactor

1. Tạo `Plan` là record với validation và `List.copyOf`.
2. Viết `Subscription` final với blank final fields.
3. Đưa normalize/validate vào prologue.
4. Gán field hợp lệ rồi gọi `super(validId)`.
5. Loại bỏ setter và không trả mutable references.

### Chặng 3 — Kiểm thử

1. Test happy path với account code cần normalize.
2. Test null/blank/range invalid.
3. Test mutate list nguồn sau khi tạo và mutate list được trả về.
4. Test thứ tự fail-fast với fixture `TrackedBase`.
5. Thử thêm một field mutable dạng array để chứng minh `final` chưa đủ, rồi sửa bằng defensive copy.
6. Chạy bộ test trên JDK 25; không dùng `--enable-preview`.

### Chặng 4 — Review

Một bài làm đạt yêu cầu khi giải thích được:

- Đâu là prologue, constructor invocation và epilogue?
- Tại sao assignment một blank field được phép trước `super(...)` nhưng đọc field lại không?
- Vì sao sai input không chạy đến parent constructor?
- Bằng chứng nào chứng minh `Plan` không bị mutate qua input source hoặc getter?
- Nếu constructor cha gọi overridable method hoặc công bố object, vẫn còn rủi ro nào?
- Vì sao Java 25 không cần bật preview cho mã này?

## 13. Câu hỏi tự đánh giá

1. JEP 513 trở thành tính năng permanent từ Java nào? Có cần `--enable-preview` trong Java 25 không?
2. `prologue` khác `epilogue` ở điểm nào? Điều gì diễn ra giữa hai phần?
3. Có thể đặt `super(...)` trong `if` khi mỗi nhánh truyền đối số khác nhau không?
4. Vì sao `Objects.requireNonNull(param)` hợp lệ trong prologue?
5. Vì sao gọi `this.validate()` hoặc `hashCode()` trong prologue thường không hợp lệ?
6. Phép `this.value = n;` và `this.value++;` khác nhau ra sao trước `super(...)`?
7. Vì sao chỉ gán sớm **blank field** của lớp hiện tại mà không tùy ý gán field superclass?
8. Nếu class con có field initializer, thứ tự chạy của nó liên quan thế nào tới superclass constructor?
9. Vì sao test `assertEquals(3, plan.seats())` chưa chứng minh `features` là immutable?
10. `List.copyOf` khác `final List` như thế nào?
11. `List.copyOf` có copy sâu những đối tượng mutable nằm trong list không?
12. Trong ví dụ `Subscription`, vì sao không kiểm tra `end > Instant.now()` một cách ngầm định?
13. Test `TrackedBase` chứng minh điều gì về thứ tự thực thi khi input không hợp lệ?
14. Vì sao parent constructor gọi overridable method vẫn là anti-pattern dù có thể gán field sớm?
15. `this(...)` giúp giảm lặp assignment bằng cách nào? Cần tránh vấn đề gì với blank final field?
16. Những trường hợp nào record là thiết kế đơn giản hơn class thường?
17. Khi refactor entity JPA/ORM, vì sao không thể áp dụng `final class`/blank final fields mà không kiểm tra yêu cầu framework?
18. Khi một constructor ném exception, có bảo đảm không có side effect nào trước đó không? Vì sao?
19. Để bảo đảm thread safety, việc khai báo tất cả field `final` đã đủ chưa?
20. Những thay đổi hành vi nào (exception, normalization, parent call) cần review khi refactor constructor công khai?

## 14. Tài liệu tham khảo

- [OpenJDK JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): mục tiêu, trạng thái chuẩn hóa ở Java 25 và các thay đổi ngữ nghĩa.
- [Oracle Java SE 25 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): ví dụ validate trước `super(...)`, early construction context, gán field sớm, record constructor.
- [Java Language Specification SE 25 — `8.8.7 Constructor Body](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7): prologue, epilogue và cấu trúc constructor.
- [JLS SE 25 — `8.8.7.1 Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7.1): hạn chế truy cập instance trong early construction context.
- [JLS SE 25 — `12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.5): thứ tự prologue, gọi constructor cha, field initializer và epilogue.
- [JLS SE 25 — `16 Definite Assignment](https://docs.oracle.com/javase/specs/jls/se25/html/jls-16.html): kiểm tra các blank final fields.
- [Oracle Java SE 25 — Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html): trạng thái permanent của JEP 513.
- [Oracle Java SE 25 — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): compact canonical constructor và thành phần record.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Assertions, assertThrows và test lifecycle.

