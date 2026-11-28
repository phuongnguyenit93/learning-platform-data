# Tái cấu trúc hàm khởi tạo với kiểm tra đầu vào và bất biến đối tượng

## 1. Mục tiêu và bối cảnh Java 25

Bài thuộc chương **Thực hành tổng hợp** của module **JAVA_VERSION_JAVA25**. Chủ đề là thiết kế constructor để một object chỉ được xem là hợp lệ sau khi hoàn tất khởi tạo: dữ liệu đầu vào đã được kiểm tra, giá trị đã được chuẩn hóa, collection đã được sao chép an toàn và các bất biến của lớp luôn đúng.

Java 25 hoàn thiện **Flexible Constructor Bodies — JEP 513**. Trước đây, lời gọi `this(...)` hoặc `super(...)` phải đứng ở đầu constructor. Từ Java 25, constructor có thể có một phần lệnh giới hạn trước lời gọi đó. Phần này được gọi là *prologue*; phần sau lời gọi là *epilogue*.

Tính năng giúp:

- Kiểm tra tham số trước khi constructor lớp cha chạy.
- Tính toán và chuẩn bị đối số cho `super(...)` hoặc `this(...)`.
- Khởi tạo một số blank `final` field của lớp hiện tại trước khi gọi constructor lớp cha.
- Giảm các helper workaround chỉ tồn tại vì giới hạn cú pháp cũ.

**JEP 513 là tính năng ngôn ngữ đã hoàn tất trong JDK 25**, không còn là preview. Ví dụ Java 25 trong bài không cần `--enable-preview`. Mã mẫu tập trung vào cú pháp và quy tắc hiện hành; không dùng cú pháp preview cũ.

### Kết quả cần đạt

Sau bài thực hành, bạn có thể:

1. Phân biệt prologue và epilogue của constructor.
2. Viết validation trước `super(...)` và `this(...)`.
3. Tính đối số constructor bằng biến cục bộ và static helper.
4. Hiểu giới hạn không được đọc instance đang xây dựng trong prologue.
5. Thiết lập blank `final` field trước `super(...)` trong trường hợp phù hợp.
6. Thiết kế constructor chaining mà không lặp validation.
7. Bảo đảm class và record giữ invariant sau khi khởi tạo.
8. Sao chép collection đầu vào để ngăn caller thay đổi trạng thái nội bộ.
9. Viết unit test cho input không hợp lệ, normalization và defensive copy.
10. Đánh giá ranh giới giữa constructor, static factory và validation nghiệp vụ.

## 2. Constructor tốt phải bảo vệ invariant

### 2.1. Invariant là gì?

Invariant là điều kiện phải luôn đúng đối với mọi instance hợp lệ của một lớp sau khi constructor hoàn tất. Ví dụ:

- `accountId` không null, không rỗng và đã được chuẩn hóa.
- `balance` không âm nếu nghiệp vụ không cho phép thấu chi.
- `startDate` không sau `endDate`.
- `email` có dạng hợp lệ theo quy tắc ứng dụng.
- Danh sách quyền không null và không bị caller bên ngoài sửa đổi.
- Hai field liên quan luôn được thiết lập đồng bộ, chẳng hạn `currency` và `amount`.

Một object vi phạm invariant có thể khiến lỗi xuất hiện ở một method hoàn toàn khác, làm cho việc tìm nguyên nhân khó hơn. Constructor là nơi phù hợp để chặn dữ liệu sai trước khi instance được đưa vào sử dụng.

### 2.2. Ví dụ constructor chỉ kiểm tra một phần

~~~java
public final class BankAccount {
    private final String accountId;
    private final long balance;

    public BankAccount(String accountId, long balance) {
        this.accountId = accountId;
        this.balance = balance;
    }
}
~~~

Đoạn code cho phép tạo instance với `accountId == null`, chuỗi trắng hoặc balance âm. Mỗi method sử dụng account sau đó phải tự kiểm tra những điều kiện này, khiến quy tắc bị phân tán.

### 2.3. Đặt validation ở ranh giới khởi tạo

~~~java
import java.util.Objects;

public final class BankAccount {
    private final String accountId;
    private final long balance;

    public BankAccount(String accountId, long balance) {
        String normalizedId = Objects.requireNonNull(accountId, "accountId").strip();

        if (normalizedId.isEmpty()) {
            throw new IllegalArgumentException("accountId must not be blank");
        }
        if (balance < 0) {
            throw new IllegalArgumentException("balance must not be negative");
        }

        this.accountId = normalizedId;
        this.balance = balance;
    }
}
~~~

Ở ví dụ này, `super()` được compiler chèn ngầm sau prologue rỗng và trước phần còn lại của constructor. Vì lớp không khai báo superclass khác `Object`, code vẫn hợp lệ trên Java hiện hành. Tuy nhiên, nếu cần kiểm tra tham số trước khi constructor lớp cha chạy, Flexible Constructor Bodies cho phép đặt prologue trước `super(...)` một cách tường minh.

Một số quy tắc lựa chọn exception:

| Tình huống | Cách xử lý thường dùng |
| --- | --- |
| Tham số bắt buộc là null | `Objects.requireNonNull(...)` hoặc `NullPointerException` có message |
| Giá trị không đáp ứng miền hợp lệ | `IllegalArgumentException` |
| Trạng thái object hiện có không cho phép thao tác | `IllegalStateException` ở method nghiệp vụ |
| Không tìm thấy resource khi khởi tạo | Exception phù hợp với contract, thường bọc nguyên nhân I/O |

Không dùng `assert` để kiểm tra dữ liệu đầu vào từ caller. Assertion có thể bị tắt khi chạy JVM và không phải cơ chế validation cho public constructor.

## 3. Flexible Constructor Bodies: prologue và epilogue

### 3.1. Cấu trúc constructor trong Java 25

Một constructor có thể có dạng:

~~~java
class Child extends Parent {
    Child(Input input) {
        // Prologue: kiểm tra và chuẩn bị dữ liệu
        Prepared prepared = prepare(input);

        super(prepared.value());

        // Epilogue: có thể dùng instance sau khi super hoàn tất
        finishSetup();
    }
}
~~~

- **Prologue:** các statement trước lời gọi `super(...)` hoặc `this(...)`.
- **Constructor invocation:** một lời gọi `super(...)` hoặc `this(...)`.
- **Epilogue:** các statement sau lời gọi constructor.

Một constructor chỉ có tối đa một constructor invocation. Không thể gọi cả `this(...)` và `super(...)` trong cùng một constructor. Nếu không viết lời gọi tường minh, compiler chèn `super()` ngầm; khi đó các statement trong constructor là epilogue.

### 3.2. Prologue được phép làm gì?

Prologue và các đối số của constructor invocation thuộc *early construction context*. Ở thời điểm này, instance hiện tại chưa được xây dựng xong. Có thể:

- Đọc tham số constructor.
- Khai báo và gán biến cục bộ.
- Gọi static method.
- Tạo giá trị trung gian và chuẩn bị đối số cho `super(...)` hoặc `this(...)`.
- Kiểm tra điều kiện và ném exception.
- Gán blank instance field của chính lớp đang khởi tạo, theo quy tắc definite assignment.

Không được đọc instance đang xây dựng:

- Không dùng `this` như một giá trị.
- Không đọc instance field, kể cả field viết không kèm `this`.
- Không gọi instance method.
- Không truy cập field hoặc method của `super`.
- Không tạo anonymous/inner class theo cách cần instance đang xây dựng.
- Không gọi method reference dựa trên instance đang xây dựng.

Ví dụ không hợp lệ:

~~~java
class InvalidChild extends Parent {
    private final String name = "child";

    InvalidChild(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input is required");
        }

        System.out.println(name); // Lỗi: đọc instance field trước super
        validate();               // Lỗi: gọi instance method trước super
        super();
    }

    private void validate() { }
}
~~~

Có thể gọi `validateInput(input)` nếu đó là static method không truy cập instance:

~~~java
class ValidChild extends Parent {
    ValidChild(String input) {
        validateInput(input);
        super();
    }

    private static void validateInput(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("input is required");
        }
    }
}
~~~

### 3.3. Ngoại lệ có chủ đích: gán blank field trước super

Java 25 cho phép gán field của instance đang xây dựng trong prologue, nhưng không cho phép đọc giá trị field đó. Trường hợp thường gặp là blank `final` field chưa có initializer:

~~~java
class Parent {
    Parent() {
        describe();
    }

    void describe() {
        System.out.println("Parent");
    }
}

final class Child extends Parent {
    private final String label;

    Child(String label) {
        this.label = Objects.requireNonNull(label, "label").strip();
        super();
    }

    @Override
    void describe() {
        System.out.println(label);
    }
}
~~~

Khi `Parent()` gọi method được override, field `label` đã có giá trị thay vì còn giá trị mặc định `null`. Đây là một khả năng đặc biệt của Flexible Constructor Bodies.

Tuy nhiên, thiết kế superclass gọi method có thể override trong constructor vốn rất dễ tạo lỗi khởi tạo. Hãy ưu tiên không gọi overridable method trong constructor lớp cha. Chỉ dùng việc gán field sớm khi phải tích hợp với superclass hiện có và đã hiểu chính xác luồng gọi.

**Điều kiện:** field gán sớm phải là field chưa được khởi tạo bằng initializer và phải tuân thủ quy tắc gán definite assignment của `final`. Không gán trước rồi lại gán lần nữa ở epilogue.

### 3.4. Khi nào nên dùng prologue?

Dùng prologue khi việc kiểm tra hoặc chuẩn bị tham số cần diễn ra trước constructor lớp cha:

- Superclass mở resource, đăng ký listener hoặc ghi nhận object khi khởi tạo.
- Superclass yêu cầu một giá trị đã chuẩn hóa.
- Đối số cho `super(...)` cần tính qua nhiều bước.
- Cần từ chối input sai trước khi superclass thực hiện side effect.
- Cần gán blank field trước `super(...)` trong một tình huống kế thừa đặc biệt.

Nếu không có yêu cầu như vậy, constructor thông thường với validation và field assignment sau `super()` vẫn dễ đọc. Không cần thêm prologue chỉ để dùng cú pháp mới.

## 4. Bài toán tích hợp: tái cấu trúc Customer

### 4.1. Thiết kế lớp cha

Giả sử hệ thống có một superclass đăng ký entity vào registry khi khởi tạo. Constructor lớp con cần bảo đảm dữ liệu đã hợp lệ trước khi gọi constructor này:

~~~java
import java.util.Objects;

abstract class RegisteredEntity {
    private final String id;

    protected RegisteredEntity(String id) {
        this.id = Objects.requireNonNull(id, "id");
        EntityRegistry.register(id);
    }

    public final String id() {
        return id;
    }
}
~~~

`EntityRegistry.register` đại diện cho side effect của hệ thống (ví dụ ghi nhận entity hoặc đăng ký metadata). Nếu gọi superclass trước khi kiểm tra dữ liệu, side effect có thể xảy ra với input không hợp lệ.

### 4.2. Constructor lớp con dùng prologue

~~~java
import java.util.Collection;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public final class Customer extends RegisteredEntity {
    private final String email;
    private final List<String> tags;

    public Customer(String id, String email, Collection<String> tags) {
        String normalizedId = requireText(id, "id");
        String normalizedEmail = normalizeEmail(email);
        List<String> immutableTags = normalizeTags(tags);

        super(normalizedId);

        this.email = normalizedEmail;
        this.tags = immutableTags;
    }

    private static String requireText(String value, String name) {
        Objects.requireNonNull(value, name);
        String normalized = value.strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return normalized;
    }

    private static String normalizeEmail(String email) {
        String value = requireText(email, "email").toLowerCase(Locale.ROOT);
        int at = value.indexOf('@');

        if (at <= 0 || at == value.length() - 1 || value.indexOf('@', at + 1) >= 0) {
            throw new IllegalArgumentException("email must contain one non-edge @");
        }
        return value;
    }

    private static List<String> normalizeTags(Collection<String> tags) {
        Objects.requireNonNull(tags, "tags");

        return tags.stream()
            .map(tag -> requireText(tag, "tag").toLowerCase(Locale.ROOT))
            .distinct()
            .toList();
    }

    public String email() {
        return email;
    }

    public List<String> tags() {
        return tags;
    }
}
~~~

Phần trước `super(normalizedId)` là prologue:

- Kiểm tra `id`, `email` và `tags`.
- Loại bỏ khoảng trắng ở đầu/cuối.
- Chuẩn hóa email và tag về chữ thường theo `Locale.ROOT`.
- Loại bỏ tag trùng nhau.
- Tạo list không thể sửa đổi bằng `Stream.toList()`.

Chỉ khi các bước này thành công, constructor mới gọi `super(...)`. Nếu validation ném exception, constructor `RegisteredEntity` chưa chạy và `EntityRegistry.register(...)` chưa được gọi.

Phần sau `super(...)` là epilogue. Tại đây constructor gán các field `final` của Customer. Khi constructor hoàn tất, object có `id`, `email` và `tags` hợp lệ.

Đoạn kiểm tra email ở ví dụ chỉ là quy tắc định dạng tối thiểu để minh họa. Hệ thống thật cần áp dụng chính sách validation theo domain và không nên xem kiểm tra một ký tự `@` là xác thực đầy đủ địa chỉ email.

### 4.3. Nếu muốn gán field trước super

Có thể chuyển hai phép gán field `final` vào prologue:

~~~java
public Customer(String id, String email, Collection<String> tags) {
    String normalizedId = requireText(id, "id");
    this.email = normalizeEmail(email);
    this.tags = normalizeTags(tags);

    super(normalizedId);
}
~~~

Cách này hợp lệ vì `email` và `tags` là blank `final` field, được gán một lần và không được đọc trước `super(...)`. Nó hữu ích khi superclass constructor có thể gọi một method được override và method đó cần đọc field subclass.

Nếu superclass không gọi method override và không cần đọc state của subclass, gán field trong epilogue thường dễ hiểu hơn. Không dùng early field assignment như một lý do để cho phép superclass gọi method override trong constructor.

### 4.4. Kiểm tra defensive copy

`Stream.toList()` trả về list không thể sửa đổi. Vì vậy caller không thể thay đổi collection thông qua reference trả về từ `tags()`:

~~~java
Customer customer = new Customer(
    "  C-100  ",
    "  USER@EXAMPLE.COM ",
    List.of("VIP", "NEWS")
);

System.out.println(customer.id());    // C-100
System.out.println(customer.email()); // user@example.com
System.out.println(customer.tags());  // [vip, news]
~~~

Nếu đầu vào là một collection mutable, list được tạo từ stream là một kết quả mới. Việc caller thay đổi collection nguồn sau khi constructor trả về không làm thay đổi `customer.tags()`.

Lưu ý đây là defensive copy nông. Nếu collection chứa object mutable, `toList()` không tự sao chép sâu các phần tử. Với domain object phức tạp, phần tử cũng cần immutable hoặc phải được sao chép theo quy tắc riêng.

## 5. Constructor chaining bằng this(...)

### 5.1. Prologue trước constructor cùng lớp

Flexible Constructor Bodies cũng cho phép kiểm tra và chuẩn hóa dữ liệu trước lời gọi `this(...)`:

~~~java
public final class TenantCode {
    private final String value;

    public TenantCode(CharSequence raw) {
        String normalized = normalize(raw);
        this(normalized);
    }

    private TenantCode(String normalized) {
        this.value = normalized;
    }

    private static String normalize(CharSequence raw) {
        Objects.requireNonNull(raw, "raw");
        String value = raw.toString().strip().toUpperCase(Locale.ROOT);

        if (value.isEmpty()) {
            throw new IllegalArgumentException("tenant code must not be blank");
        }
        return value;
    }

    public String value() {
        return value;
    }
}
~~~

Constructor nhận `CharSequence` chuẩn hóa đầu vào, sau đó delegate tới constructor nhận `String`. Constructor đích chịu trách nhiệm gán field.

### 5.2. Tránh validation lặp giữa các constructor

Khi có nhiều overload, nên chọn một constructor làm điểm khởi tạo chuẩn (canonical constructor của class theo quy ước thiết kế):

~~~java
public final class Endpoint {
    private final URI uri;
    private final Duration timeout;

    public Endpoint(URI uri) {
        this(uri, Duration.ofSeconds(3));
    }

    public Endpoint(String uri, Duration timeout) {
        String normalized = Objects.requireNonNull(uri, "uri").strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("uri must not be blank");
        }

        this(URI.create(normalized), timeout);
    }

    public Endpoint(URI uri, Duration timeout) {
        this.uri = validateUri(uri);
        this.timeout = validateTimeout(timeout);
    }

    private static URI validateUri(URI uri) {
        Objects.requireNonNull(uri, "uri");
        if (!uri.isAbsolute()) {
            throw new IllegalArgumentException("uri must be absolute");
        }
        return uri.normalize();
    }

    private static Duration validateTimeout(Duration timeout) {
        Objects.requireNonNull(timeout, "timeout");
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        return timeout;
    }
}
~~~

Ở ví dụ này, overload nhận `String` kiểm tra chuỗi trước rồi delegate. Constructor nhận `URI` thực hiện validation cuối cùng và gán field. Với dữ liệu có thể được tạo từ nhiều nguồn, đây là nơi tập trung invariant của object.

Quy tắc thiết kế:

- Chọn một constructor làm điểm gán field và thực thi invariant cuối cùng.
- Overload tiện ích chỉ chuyển đổi/chuẩn bị tham số rồi gọi `this(...)`.
- Không lặp cùng một validation phức tạp ở mọi overload.
- Không để constructor delegate vòng lặp, ví dụ A gọi B rồi B lại gọi A.
- Constructor dùng `this(...)` không gọi thêm `super(...)`; constructor đích sẽ gọi superclass.

### 5.3. Kiểm tra thứ tự và phạm vi

Trong prologue, chỉ sử dụng tham số và biến cục bộ đã khai báo. Không truyền `this` vào `this(...)`, không gọi instance method để tạo đối số và không đọc field chưa được khởi tạo.

Nếu validation cần cấu hình hoặc dependency bên ngoài, hãy cân nhắc static factory nhận dependency rõ ràng. Constructor không nên tự tra cứu service locator hoặc thực hiện I/O phức tạp.

## 6. Record: compact constructor và invariant của component

### 6.1. Compact canonical constructor

Record có thể kiểm tra và chuẩn hóa component trong compact constructor:

~~~java
import java.util.Objects;

record UserName(String value) {
    UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
~~~

Trong compact constructor:

- Không viết danh sách tham số; record components là tham số ngầm định.
- Có thể kiểm tra và gán lại tham số component.
- Compiler tự gán các giá trị tham số cuối cùng vào component field sau khi body hoàn tất.
- Không tự gán `this.value = value` trong compact constructor.

Khi `value` được chuẩn hóa bằng `strip()`, record lưu chính giá trị đã chuẩn hóa đó.

### 6.2. Noncanonical record constructor và prologue

Constructor không canonical của record phải delegate bằng `this(...)`; không được gọi `super(...)`. Java 25 cho phép đặt statement trước lời gọi đó:

~~~java
record SizeInput(int width, int height) { }

record Size(int width, int height) {
    Size(SizeInput input) {
        Objects.requireNonNull(input, "input");

        int checkedWidth = input.width();
        int checkedHeight = input.height();

        this(checkedWidth, checkedHeight);
    }

    Size {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions must be positive");
        }
    }
}
~~~

Constructor nhận `SizeInput` kiểm tra null và tách dữ liệu thành biến cục bộ trước `this(...)`. Compact canonical constructor là nơi duy nhất kiểm tra invariant cuối cùng của `Size`.

### 6.3. Defensive copy trong record

Record không tự làm collection component immutable. Hãy sao chép ở compact constructor:

~~~java
record AccessPolicy(Set<String> roles) {
    AccessPolicy {
        roles = Set.copyOf(Objects.requireNonNull(roles, "roles"));
    }
}
~~~

`Set.copyOf` tạo snapshot không thể sửa đổi và từ chối null collection hoặc null element. Record giữ reference tới snapshot mới, không giữ collection mutable do caller truyền vào.

Đây vẫn là copy nông. Nếu phần tử là object mutable, cần quy tắc immutable/copy riêng cho phần tử.

## 7. Các lỗi thiết kế thường gặp

### 7.1. Quên viết super(...) tường minh khi muốn có prologue

Nếu constructor không chứa lời gọi `super(...)` hoặc `this(...)` tường minh, compiler chèn `super()` ngầm ở đầu constructor. Vì vậy các statement trong thân constructor là epilogue, không phải prologue.

Muốn validation chạy trước constructor lớp cha, hãy viết rõ cả lời gọi `super()` không tham số:

~~~java
class Child extends Parent {
    Child(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }

        super();
    }
}
~~~

Nếu superclass không có constructor không tham số có thể truy cập, phải gọi constructor phù hợp bằng `super(arguments...)`.

### 7.2. Dùng instance method trong prologue

Sai:

~~~java
class Child extends Parent {
    Child(String value) {
        validate(value); // Nếu validate là instance method thì không hợp lệ
        super();
    }

    private void validate(String value) { }
}
~~~

Đúng:

~~~java
class Child extends Parent {
    Child(String value) {
        validate(value);
        super();
    }

    private static void validate(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
~~~

Nếu helper cần trạng thái instance để quyết định tính hợp lệ, hãy thiết kế lại dữ liệu đầu vào hoặc thực hiện phần kiểm tra đó trong epilogue trước khi object được công bố.

### 7.3. Gọi superclass trước khi kiểm tra input

Nếu constructor superclass mở file, đăng ký listener hoặc tạo resource, gọi nó trước validation có thể để lại side effect khi input lớp con không hợp lệ.

Dùng prologue để kiểm tra mọi điều kiện có thể kiểm tra độc lập với instance trước `super(...)`. Tuy nhiên, prologue không tự rollback side effect. Nếu epilogue còn có bước có thể thất bại sau khi superclass đã tạo resource, cần thiết kế cleanup/transaction hoặc dùng static factory điều phối lifecycle.

### 7.4. Cho this thoát ra ngoài trước khi constructor hoàn tất

Không đăng ký `this` vào registry, event listener, static collection hoặc thread khác trước khi mọi field invariant đã được thiết lập. Không khởi chạy thread từ constructor nếu thread có thể quan sát instance trước khi constructor kết thúc.

Object bị publish quá sớm có thể bị thread khác nhìn thấy ở trạng thái một phần. Hãy khởi tạo xong rồi mới publish instance từ factory hoặc lifecycle method.

### 7.5. Lặp validation ở mọi overload

Nếu mọi constructor overload tự chuẩn hóa và kiểm tra riêng, quy tắc có thể lệch nhau theo thời gian. Hãy dùng `this(...)` để đưa dữ liệu về một constructor chuẩn và chỉ để constructor đó gán field.

Nếu các overload có semantics khác nhau thật sự, tách thành static factory có tên mô tả rõ mục đích thay vì dùng nhiều boolean flag khó hiểu.

### 7.6. Dùng constructor để làm quá nhiều việc

Constructor nên thiết lập trạng thái ban đầu và invariant. Tránh:

- Gọi HTTP/database để nạp dữ liệu.
- Đọc file cấu hình lớn hoặc tải model.
- Đăng ký nhiều callback bên ngoài trước khi object hoàn chỉnh.
- Khởi chạy background thread.
- Chạy workflow nghiệp vụ dài.
- Tự tìm dependency từ global service locator.

Những việc này có thể thất bại, block hoặc cần retry. Hãy đặt chúng trong factory/service có thể biểu diễn timeout, exception, cleanup và observability rõ ràng.

## 8. Unit test cho validation và invariant

Có thể dùng JUnit Jupiter để kiểm tra contract của constructor. Ví dụ với record `Size`, `UserName` và `AccessPolicy` đã xây dựng ở phần trước:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;

class ConstructorInvariantTest {

    @Test
    void rejectsInvalidDimensions() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Size(0, 10)
        );
    }

    @Test
    void normalizesRecordComponent() {
        UserName name = new UserName("  Alice  ");

        assertEquals("Alice", name.value());
    }

    @Test
    void rejectsBlankRecordComponent() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new UserName("   ")
        );
    }

    @Test
    void copiesMutableInputCollection() {
        Set<String> input = new HashSet<>(Set.of("reader"));
        AccessPolicy policy = new AccessPolicy(input);

        input.add("admin");

        assertEquals(Set.of("reader"), policy.roles());
    }

    @Test
    void exposesUnmodifiableCollection() {
        AccessPolicy policy = new AccessPolicy(Set.of("reader"));

        assertThrows(
            UnsupportedOperationException.class,
            () -> policy.roles().add("admin")
        );
    }
}
~~~

Bộ test này kiểm tra cả input sai và hành vi sau khởi tạo. Một constructor được xem là bảo vệ invariant khi caller không thể tạo object sai hoặc thay đổi trạng thái nội bộ qua collection nguồn.

Với lớp `Customer`, nên bổ sung test rằng:

- `id` và `email` trắng bị từ chối.
- Tag null hoặc blank bị từ chối theo contract.
- Tag được chuẩn hóa và loại trùng.
- `EntityRegistry.register(...)` không được gọi khi validation prologue thất bại.
- Khi khởi tạo thành công, registry chỉ nhận id đã chuẩn hóa.

Nếu registry là dependency thật, nên inject một abstraction hoặc dùng test double thay vì dựa vào static global state.

## 9. Thực hành tổng hợp: xây dựng Customer và Subscription an toàn

### 9.1. Yêu cầu nghiệp vụ

Xây dựng model cho hệ thống subscription với các quy tắc:

- Mã khách hàng bắt buộc, loại bỏ khoảng trắng đầu/cuối.
- Email bắt buộc và chuẩn hóa theo chính sách của ứng dụng.
- Tập tag không null, không chứa phần tử null/trắng, không trùng nhau.
- Ngày bắt đầu và ngày kết thúc phải hợp lệ.
- Số tiền không âm và currency phải thuộc danh sách được hỗ trợ.
- Collection được lưu dưới dạng snapshot không thể sửa đổi.
- Constructor lớp con phải kiểm tra dữ liệu trước khi gọi superclass có side effect.

### 9.2. Phần A — Xác định invariant

Viết ra invariant trước khi viết constructor. Ví dụ:

| Thuộc tính | Invariant |
| --- | --- |
| `customerId` | Non-null, non-blank, đã strip |
| `email` | Non-null, non-blank, normalized |
| `tags` | Non-null, unmodifiable, không null/blank, không trùng |
| `startDate` | Non-null |
| `endDate` | Non-null, không trước startDate |
| `amount` | Non-null, signum không âm |
| `currency` | Non-null, nằm trong tập currency hỗ trợ |

Không trộn quy tắc cú pháp với quy tắc nghiệp vụ. Ví dụ, định dạng email có thể kiểm tra tại constructor, nhưng việc email đã xác minh quyền sở hữu hay chưa là trạng thái nghiệp vụ cần workflow riêng.

### 9.3. Phần B — Dùng prologue để chuẩn bị tham số superclass

Tạo một subclass nhận dữ liệu thô. Trong prologue:

1. Kiểm tra customer ID.
2. Chuẩn hóa ID.
3. Kiểm tra các tham số độc lập khác.
4. Tạo defensive copy cho collection.
5. Chỉ gọi `super(normalizedId)` sau khi mọi validation cần thiết đã thành công.

Đảm bảo constructor superclass chỉ nhận ID đã chuẩn hóa. Nếu superclass có side effect, kiểm tra rằng invalid input không kích hoạt side effect đó.

### 9.4. Phần C — Tập trung invariant vào constructor chuẩn

Tạo overload nhận `CharSequence` hoặc một input DTO. Overload này chỉ đọc input, chuẩn hóa và gọi `this(...)`. Constructor đích:

- Gọi superclass.
- Gán toàn bộ field `final`.
- Không gọi lại cùng một validation nếu dữ liệu đã được bảo đảm bởi contract nội bộ.
- Không publish `this` trước khi hoàn tất.

Có thể giữ validation phòng thủ ở constructor public nếu nó là ranh giới API. Constructor private/internal có thể nhận dữ liệu đã chuẩn hóa từ factory, nhưng phải bảo đảm không có caller không tin cậy đi vòng qua validation.

### 9.5. Phần D — Tạo record value object

Tạo `SubscriptionPeriod` bằng record:

~~~java
import java.time.LocalDate;
import java.util.Objects;

record SubscriptionPeriod(LocalDate start, LocalDate end) {
    SubscriptionPeriod {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end must not be before start");
        }
    }
}
~~~

Tạo overload nhận input DTO và delegate về canonical constructor bằng `this(...)` sau khi kiểm tra input null và chuẩn bị biến cục bộ. Không viết `super(...)` trong record constructor.

### 9.6. Phần E — Kiểm thử

Viết test cho:

- ID null, rỗng và có khoảng trắng.
- Email null, trắng và sai format theo chính sách đã chọn.
- Tag null, có phần tử null, có phần tử trắng và tag trùng.
- Ngày kết thúc trước ngày bắt đầu.
- Amount âm và currency không hỗ trợ.
- Collection nguồn bị thay đổi sau khi constructor trả về.
- Collection trả về từ getter không thể sửa đổi.
- Superclass không nhận input invalid.
- Mọi overload tạo ra cùng invariant cho cùng một dữ liệu.

### 9.7. Tiêu chí hoàn thành

Bài thực hành đạt khi:

1. Không thể tạo instance vi phạm invariant qua bất kỳ constructor public nào.
2. Input được chuẩn hóa một lần theo contract thống nhất.
3. Superclass chỉ chạy sau validation prologue.
4. Mọi field `final` được gán đúng một lần.
5. Không có reference mutable từ caller làm thay đổi state nội bộ ngoài ý muốn.
6. Record component được kiểm tra trong compact constructor.
7. Unit test chứng minh cả trường hợp hợp lệ và không hợp lệ.
8. Code không cần preview flag trên JDK 25.

## 10. Khi nào dùng constructor, static factory hoặc builder?

| Cách tạo object | Nên dùng khi | Điểm cần lưu ý |
| --- | --- | --- |
| Constructor | Input bắt buộc, quy tắc rõ và object tạo trực tiếp | Dùng validation để bảo vệ invariant |
| Static factory | Cần tên mô tả, chọn implementation, trả cache/instance đặc biệt hoặc điều phối nhiều bước | Có thể ném checked exception và gọi dependency |
| Builder | Có nhiều option tùy chọn, cấu hình nhiều bước hoặc muốn API fluent | `build()` vẫn phải kiểm tra invariant cuối cùng |
| Record compact constructor | Value object có component cố định | Chuẩn hóa/kiểm tra component trước implicit assignment |

Flexible Constructor Bodies mở rộng khả năng của constructor, nhưng không thay thế static factory hoặc builder. Nếu việc tạo object cần gọi database, kiểm tra quyền, resolve dependency hoặc mở nhiều resource, một factory/service thường thể hiện lifecycle rõ ràng hơn.

## 11. Checklist review constructor

### Input và invariant

- [ ] Mọi tham số bắt buộc đều được kiểm tra null.
- [ ] Chuỗi được chuẩn hóa theo quy tắc rõ ràng.
- [ ] Range/relationship giữa các tham số được kiểm tra.
- [ ] Exception phản ánh đúng loại input sai.
- [ ] Không dùng `assert` thay validation.

### Flexible constructor body

- [ ] Prologue chỉ dùng tham số, local variable và static helper.
- [ ] Không đọc field hoặc gọi instance method trước `super(...)`/`this(...)`.
- [ ] Có lời gọi constructor tường minh nếu cần prologue.
- [ ] Chỉ có một constructor invocation.
- [ ] Blank `final` field được gán đúng một lần nếu gán trước `super(...)`.
- [ ] Không lạm dụng early field assignment để che giấu superclass constructor nguy hiểm.

### Object lifecycle

- [ ] Không để `this` thoát ra ngoài trước khi constructor hoàn tất.
- [ ] Không thực hiện I/O hoặc workflow dài trong constructor.
- [ ] Collection đầu vào được defensive copy.
- [ ] Phần tử mutable được xử lý theo chính sách riêng.
- [ ] Constructor chaining tập trung vào một điểm gán field.
- [ ] Record compact constructor không tự gán `this.component`.

### Kiểm thử và build

- [ ] Có test cho null, blank, range và dữ liệu biên.
- [ ] Có test cho normalization và defensive copy.
- [ ] Có test cho constructor overload.
- [ ] Có test chứng minh superclass không chạy khi prologue validation thất bại.
- [ ] Compile bằng JDK 25 trở lên, không bật preview cho JEP 513.

## 12. Câu hỏi tự đánh giá

1. JEP nào hoàn thiện Flexible Constructor Bodies trong JDK 25?
2. Prologue và epilogue khác nhau như thế nào?
3. Vì sao constructor cần một invariant rõ ràng?
4. Khi nào cần viết `super()` tường minh để có prologue?
5. Prologue được phép đọc những dữ liệu nào?
6. Vì sao prologue không được gọi instance method?
7. Có thể gọi static helper trong prologue không?
8. Có thể gán blank `final` field trước `super(...)` trong điều kiện nào?
9. Vì sao không nên đọc field vừa gán trong prologue?
10. Khi nào nên dùng `this(...)` để tập trung logic khởi tạo?
11. Vì sao constructor chaining không nên lặp validation?
12. Record compact constructor gán component field vào thời điểm nào?
13. Vì sao không tự gán `this.component` trong compact constructor?
14. Noncanonical record constructor phải delegate như thế nào?
15. `List.copyOf` hoặc `Stream.toList()` giúp bảo vệ invariant collection ra sao?
16. Defensive copy nông khác deep copy như thế nào?
17. Vì sao không nên publish `this` trước khi constructor hoàn tất?
18. Vì sao constructor không nên gọi HTTP/database?
19. Khi nào static factory phù hợp hơn constructor?
20. Những test nào chứng minh object không thể được tạo ở trạng thái không hợp lệ?

## 13. Tài liệu tham khảo

- [OpenJDK JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): phạm vi và mục tiêu của tính năng được hoàn thiện trong JDK 25.
- [Oracle Java 25 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): prologue, epilogue, early construction context, field assignment trước `super(...)` và constructor record.
- [Java Language Specification, Java SE 25 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8): cú pháp constructor body, constructor invocation và quy tắc definite assignment.
- [Oracle Java 25 — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): canonical constructor, compact constructor và component fields.
- [Java SE 25 API — Objects](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html): `requireNonNull` và các helper kiểm tra null.
- [Java SE 25 API — List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): `copyOf` và collection không thể sửa đổi.
- [Java SE 25 API — Set](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): `copyOf` và contract của immutable set.











