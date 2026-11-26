# Ngoại lệ, tác dụng phụ và tránh làm lộ đối tượng đang khởi tạo

Flexible Constructor Bodies cho phép viết một số câu lệnh trước lời gọi `super(...)` hoặc `this(...)` trong constructor. Nhờ đó, constructor có thể kiểm tra tham số, chuẩn hóa dữ liệu và chuẩn bị đối số trước khi constructor của lớp cha hoặc constructor khác trong cùng lớp chạy. Tuy nhiên, phần mã chạy sớm này có quy tắc truy cập rất chặt chẽ và có thể tạo ra tác dụng phụ trước khi quá trình khởi tạo hoàn tất.

Điểm cần hiểu kỹ là thứ tự thực thi: prologue chạy trước constructor được gọi; sau khi constructor lớp cha hoàn tất, các field initializer và instance initializer của lớp hiện tại mới chạy; cuối cùng epilogue mới được thực thi. Nếu một bước ném ngoại lệ, các bước sau không chạy, nhưng tác dụng phụ đã xảy ra không tự được hoàn tác. Ngoài ra, constructor lớp cha vẫn có thể gọi method bị override và gián tiếp làm lộ đối tượng con khi nó chưa được khởi tạo đầy đủ.

## 1. Trạng thái hiện hành của Flexible Constructor Bodies

Flexible Constructor Bodies là tính năng ngôn ngữ Java, không phải một API thư viện. Tính năng này được phát triển qua các phiên bản:

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| JDK 22 | JEP 447 — Statements before `super(...)` | Preview lần đầu. |
| JDK 23 | JEP 482 — Flexible Constructor Bodies | Preview lần thứ hai. |
| JDK 24 | JEP 492 — Flexible Constructor Bodies | Preview lần thứ ba. |
| JDK 25 | JEP 513 — Flexible Constructor Bodies | Chính thức (final). |

Tại ngày 25-11-2026, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất. Flexible Constructor Bodies đã là tính năng chính thức từ JDK 25, vì vậy mã mới nên dùng ngữ nghĩa final và không bật `--enable-preview`.

JEP 512 — Compact Source Files and Instance Main Methods — cũng trở thành tính năng chính thức trong JDK 25, nhưng là một thay đổi ngôn ngữ riêng dành cho cách viết chương trình nguồn gọn và điểm vào `main`. Nó không thay đổi quy tắc khởi tạo constructor trong bài này. Các lần preview trước JDK 25 chỉ có ý nghĩa lịch sử, không phải cách cấu hình cần dùng hiện nay.

## 2. Prologue, constructor invocation và epilogue

Kể từ Flexible Constructor Bodies, thân constructor có thể có ba phần:

```java
class Parent {
    Parent(String value) { }
}

class Child extends Parent {
    Child(String input) {
        // Prologue: các câu lệnh trước constructor invocation.
        String normalized = input == null ? "" : input.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("input is required");
        }

        super(normalized);

        // Epilogue: các câu lệnh sau constructor invocation.
        System.out.println("Child initialized: " + normalized);
    }
}
```

- **Prologue** gồm các câu lệnh đứng trước lời gọi constructor tường minh `super(...)` hoặc `this(...)`.
- **Constructor invocation** gọi constructor của lớp cha (`super(...)`) hoặc một constructor khác trong cùng lớp (`this(...)`). Một constructor chỉ có tối đa một lời gọi constructor tường minh.
- **Epilogue** gồm các câu lệnh sau lời gọi constructor đó.

Nếu constructor không viết `super(...)` hoặc `this(...)`, Java vẫn chèn lời gọi `super()` ngầm định. Khi đó prologue rỗng và toàn bộ câu lệnh được viết trong thân constructor là epilogue. Vì vậy, muốn chạy kiểm tra trước constructor lớp cha, phải viết lời gọi constructor tường minh.

Prologue và các biểu thức đối số của `super(...)` hoặc `this(...)` đều thuộc *early construction context*. Các quy tắc hạn chế truy cập đối tượng đang khởi tạo áp dụng cho cả hai vị trí này.

## 3. Những gì được phép trong early construction context

Trong prologue, Java chưa cho phép sử dụng đối tượng hiện tại như một instance đã sẵn sàng. Điều này ngăn phần lớn trường hợp truy cập nhầm field hoặc gọi method khi các phần của object chưa được khởi tạo.

Thông thường, prologue có thể:

- Đọc tham số constructor và biến cục bộ đã khai báo.
- Khai báo biến cục bộ, thực hiện tính toán và kiểm tra điều kiện.
- Gọi static method, đọc static field hoặc dùng các object độc lập được truyền vào.
- Ném ngoại lệ nếu tham số không hợp lệ.
- Gán giá trị cho một blank instance field của chính lớp hiện tại bằng phép gán đơn `=` theo ngoại lệ được Java cho phép.

Các thao tác sau không hợp lệ trong early construction context:

- Đọc field của đối tượng hiện tại, kể cả field được truy cập không ghi `this`.
- Gọi instance method hoặc method reference của đối tượng hiện tại.
- Dùng `this` như một giá trị để truyền cho method, lưu vào biến hoặc đăng ký callback.
- Truy cập member của lớp cha thông qua `super`.
- Đọc field hoặc gọi instance method của lớp cha bằng tên không định danh; việc bỏ từ khóa `super` không làm thao tác đó trở nên hợp lệ.

Ví dụ các biểu thức sau không hợp lệ trước `super(...)`:

```java
class Parent {
    Parent() { }
}

class Child extends Parent {
    int value;

    Child(int input) {
        int current = value;       // Lỗi: đọc field của instance đang tạo.
        setValue(input);           // Lỗi: gọi instance method.
        register(this);            // Lỗi: dùng this làm đối số.
        super();
    }

    void setValue(int value) {
        this.value = value;
    }

    private static void register(Child child) { }
}
```

Quy tắc này không có nghĩa mọi biểu thức `this` đều bị cấm tuyệt đối: Java cho phép một ngoại lệ hẹp để gán blank instance field, được giải thích ở phần tiếp theo.

## 4. Gán blank field trước khi gọi constructor lớp cha

Một điểm quan trọng của Flexible Constructor Bodies là có thể gán field của chính lớp hiện tại trước khi gọi `super(...)`. Việc gán này phải là phép gán đơn cho field chưa có initializer trong khai báo. Không được đọc field trước khi gán, dùng `++`, `+=` hoặc thực hiện phép cập nhật cần đọc giá trị cũ.

Ví dụ:

```java
class Parent {
    Parent(String key) {
        System.out.println("Parent key: " + key);
    }
}

class Account extends Parent {
    private final String accountId;

    Account(String rawId) {
        String normalized = normalize(rawId);
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("accountId is blank");
        }

        this.accountId = normalized;
        super(normalized);
    }

    private static String normalize(String value) {
        return value == null ? "" : value.strip();
    }
}
```

`accountId` là blank `final` field vì khai báo không có initializer. Constructor có thể gán field đó trước `super(...)`, sau khi kiểm tra và chuẩn hóa tham số. Điều này hữu ích nếu constructor lớp cha gọi một method được override ở lớp con và method đó cần đọc field đã gán.

Giới hạn cần nhớ:

| Trường hợp | Được phép trước `super(...)`? |
| --- | --- |
| `this.id = normalized;` với `id` là blank field của lớp hiện tại | Có, nếu thỏa quy tắc definite assignment. |
| `this.id` để đọc giá trị field | Không. |
| `this.count++;` hoặc `this.count += 1;` | Không; đây là thao tác cần đọc giá trị cũ. |
| Gán field có initializer như `int count = 1;` | Không được gán lại trong prologue. |
| Gọi `this.initialize()` | Không. |

Không thể dùng khả năng gán blank field như cách truy cập tùy ý vào đối tượng đang tạo. Phần lớn thao tác với `this` vẫn bị cấm; chỉ phép gán đơn cho field đáp ứng điều kiện mới được chấp nhận.

Nếu constructor gọi `this(...)` để ủy quyền cho constructor khác, blank `final` field của lớp phải vẫn ở trạng thái chưa được gán tại lời gọi ủy quyền. Constructor được ủy quyền chịu trách nhiệm gán các field `final` đó. Vì vậy, hãy dùng prologue trước `this(...)` để kiểm tra và chuẩn bị đối số; không áp dụng ví dụ gán `final` field trước `super(...)` cho constructor đang ủy quyền bằng `this(...)`.

## 5. Ngoại lệ có thể xảy ra ở những thời điểm nào?

Một constructor có thể kết thúc bất thường ở nhiều giai đoạn:

1. **Prologue:** kiểm tra tham số, chuẩn hóa dữ liệu hoặc gọi static helper có thể ném ngoại lệ.
2. **Đánh giá đối số constructor invocation:** biểu thức truyền cho `super(...)` hoặc `this(...)` có thể ném ngoại lệ trước khi constructor đích được gọi.
3. **Constructor được gọi:** constructor lớp cha hoặc constructor khác trong cùng lớp có thể ném ngoại lệ.
4. **Field initializer và instance initializer:** sau khi constructor lớp cha hoàn tất, initializer của lớp hiện tại có thể ném ngoại lệ.
5. **Epilogue:** các câu lệnh sau constructor invocation có thể ném ngoại lệ.

Nếu một bước kết thúc bất thường, các bước tiếp theo trong quy trình khởi tạo không chạy. Ví dụ, nếu prologue ném ngoại lệ thì `super(...)` chưa được gọi; nếu constructor lớp cha ném ngoại lệ thì field initializer, instance initializer và epilogue của lớp con không được thực thi.

Các ngoại lệ checked vẫn tuân theo quy tắc thông thường: constructor phải bắt ngoại lệ hoặc khai báo trong `throws`. Flexible Constructor Bodies không thay đổi hệ thống kiểm tra ngoại lệ của Java.

### Ví dụ kiểm tra trước khi khởi tạo lớp cha

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ParentNode {
    ParentNode(String path) {
        if (path.isBlank()) {
            throw new IllegalArgumentException("path is blank");
        }
    }
}

class FileNode extends ParentNode {
    private final Path path;

    FileNode(Path input) throws IOException {
        Path checked = input.toRealPath(); // Có thể ném IOException.
        if (!Files.isRegularFile(checked)) {
            throw new IllegalArgumentException("Not a regular file");
        }

        this.path = checked;
        super(checked.toString());
    }
}
```

Nếu `toRealPath()` hoặc kiểm tra file thất bại, constructor `ParentNode` không được gọi. Điều này giúp lớp cha không phải khởi tạo dựa trên đường dẫn không hợp lệ. Nếu constructor lớp cha ném ngoại lệ, `path` đã được gán trong prologue nhưng object vẫn không được trả về từ biểu thức `new`.

## 6. Thứ tự khởi tạo và tác dụng phụ không được rollback

Với constructor gọi `super(...)`, thứ tự khái quát như sau:

```text
new Child(...)
    |
    v
Gán tham số constructor
    |
    v
Prologue của Child
    |
    v
Đánh giá đối số và gọi super(...)
    |
    v
Constructor lớp cha và chuỗi constructor phía trên
    |
    v
Field initializers + instance initializer blocks của Child
    |
    v
Epilogue của Child
    |
    v
Đối tượng được khởi tạo hoàn tất
```

Nếu constructor dùng `this(...)`, constructor được gọi sẽ thực hiện chuỗi khởi tạo tiếp theo; epilogue của constructor gọi nó chỉ chạy sau khi constructor được ủy quyền hoàn tất bình thường. Các instance initializer của lớp chỉ chạy một lần trong nhánh constructor thực hiện lời gọi lên superclass.

Một ngoại lệ ở bất kỳ giai đoạn nào làm quá trình `new` kết thúc bất thường. Tuy nhiên, **Java không tự hoàn tác tác dụng phụ đã xảy ra**. Nếu prologue tăng bộ đếm static, ghi log, gửi request, cập nhật database hoặc đăng ký một listener, những thay đổi bên ngoài đó vẫn tồn tại khi constructor lớp cha hoặc epilogue ném ngoại lệ.

Ví dụ:

```java
class ParentJob {
    ParentJob(String id) {
        if (id.startsWith("blocked-")) {
            throw new IllegalStateException("job is blocked");
        }
    }
}

class Job extends ParentJob {
    private static int attempts;
    private final String id;

    Job(String rawId) {
        attempts++; // Tác dụng phụ xảy ra trước khi gọi ParentJob.
        String checkedId = validate(rawId);
        this.id = checkedId;
        super(checkedId); // Có thể ném ngoại lệ.
    }

    private static String validate(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        return value.strip();
    }
}
```

Nếu `ParentJob` ném ngoại lệ, `attempts` vẫn đã tăng. Nếu `validate(...)` ném ngoại lệ, bộ đếm cũng không tự giảm về giá trị cũ. Vì vậy, prologue nên ưu tiên kiểm tra và tính toán thuần; tránh thực hiện side effect khó đảo ngược trước khi biết toàn bộ quá trình khởi tạo có thể hoàn tất.

Nếu bắt buộc phải tạo tài nguyên trước khi gọi constructor lớp cha, phải thiết kế rõ cách giải phóng tài nguyên khi bước tiếp theo thất bại. Không giả định rằng constructor ném ngoại lệ sẽ tự gọi một hàm cleanup cho các tác dụng phụ đã phát sinh.

## 7. Flexible Constructor Bodies không tự ngăn `this-escape`

Early construction context hạn chế việc dùng `this` trực tiếp trong prologue. Tuy nhiên, đối tượng vẫn có thể bị lộ gián tiếp khi constructor lớp cha gọi một instance method có thể override. Java dùng dynamic dispatch: nếu lớp con override method đó, phiên bản của lớp con có thể chạy trong lúc constructor lớp cha đang thực thi.

Điều này đặc biệt nguy hiểm vì tại thời điểm constructor lớp cha chạy:

- Các blank field được gán trong prologue có thể đã có giá trị.
- Field initializer và instance initializer của lớp con chưa chạy.
- Epilogue của constructor lớp con chưa chạy.
- Các bất biến mà constructor lớp con dự định thiết lập sau `super(...)` có thể chưa được bảo đảm.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

class Base {
    Base() {
        onStart(); // Gọi virtual method trong constructor lớp cha.
    }

    protected void onStart() { }
}

class Child extends Base {
    private static final List<Child> REGISTRY = new ArrayList<>();

    private final String name;
    private int retryLimit = 3;

    Child(String name) {
        this.name = Objects.requireNonNull(name);
        super();

        if (name.length() > 40) {
            throw new IllegalArgumentException("name is too long");
        }
    }

    @Override
    protected void onStart() {
        REGISTRY.add(this); // Đối tượng bị công bố khi chưa hoàn tất.
        System.out.println(name + ", retryLimit=" + retryLimit);
    }
}
```

Khi `Base()` gọi `onStart()`, JVM dispatch tới `Child.onStart()`. `name` đã được gán trong prologue, nhưng `retryLimit = 3` là field initializer nên chưa chạy; giá trị quan sát được lúc này là `0`. `this` cũng đã bị đưa vào `REGISTRY` trước khi epilogue của `Child` hoàn tất. Nếu kiểm tra độ dài sau `super()` ném ngoại lệ, registry vẫn giữ tham chiếu tới object không hoàn tất.

Gán `name` trước `super()` chỉ bảo đảm field cụ thể đó đã có giá trị. Nó không làm cho mọi field initializer hoặc mọi bất biến của lớp con trở nên sẵn sàng, cũng không biến việc công bố `this` trong constructor thành an toàn.

## 8. Cách tránh làm lộ đối tượng đang khởi tạo

### Không gọi method có thể override từ constructor

Constructor của lớp cha nên tránh gọi instance method có thể bị lớp con override. Nếu cần bước tùy biến sau khởi tạo, hãy cung cấp method khởi động riêng hoặc dùng factory để gọi sau khi `new` hoàn tất.

```java
import java.util.ArrayList;
import java.util.List;

class Base {
    Base() {
        // Chỉ thiết lập trạng thái nội bộ của Base.
    }
}

class Child extends Base {
    private static final List<Child> REGISTRY = new ArrayList<>();
    private final String name;

    private Child(String input) {
        String checked = validate(input);
        this.name = checked;
        super();
    }

    private static String validate(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return input.strip();
    }

    private void start() {
        REGISTRY.add(this); // Công bố sau khi constructor hoàn tất.
    }

    static Child create(String input) {
        Child child = new Child(input);
        child.start();
        return child;
    }
}
```

Factory gọi `start()` sau khi constructor đã hoàn tất bình thường. Nếu validation hoặc constructor lớp cha thất bại, đối tượng chưa được đăng ký. Phương thức `start()` vẫn cần có hợp đồng lỗi và cleanup riêng nếu bản thân nó thực hiện nhiều side effect.

### Chỉ công bố `this` sau khi các bất biến đã được thiết lập

Tránh đưa `this` vào registry, static field, listener, callback, executor hoặc thread trong constructor. Nếu một thành phần khác giữ tham chiếu tới object trước khi constructor kết thúc, thành phần đó có thể đọc trạng thái mặc định hoặc gọi method khi object chưa sẵn sàng.

### Dùng composition hoặc truyền dữ liệu đã chuẩn bị cho lớp cha

Nếu lớp cha cần dữ liệu để khởi tạo, hãy truyền giá trị đã kiểm tra qua `super(...)`. Nếu lớp cha cần hành vi tùy biến, cân nhắc truyền một collaborator độc lập thay vì gọi method override trên đối tượng con đang khởi tạo.

### Dùng final hoặc private cho helper phù hợp

Các helper `private static` dùng để kiểm tra hoặc chuẩn hóa tham số phù hợp với prologue vì chúng không cần instance đang tạo. Nếu cần helper instance, hãy chuyển logic đó sang static helper nhận tham số rõ ràng hoặc một object độc lập.

## 9. Những điều Flexible Constructor Bodies không giải quyết

| Hiểu nhầm | Thực tế |
| --- | --- |
| Có thể chạy mọi câu lệnh trước `super()` | Chỉ những câu lệnh không truy cập instance đang tạo, ngoài ngoại lệ gán blank field được quy định. |
| Gán một field trước `super()` nghĩa là object đã sẵn sàng | Các field initializer và instance initializer của lớp con vẫn chạy sau constructor lớp cha. |
| Prologue ném ngoại lệ thì side effect bị hoàn tác | Java không tự rollback log, counter, I/O, database hoặc tài nguyên bên ngoài. |
| Không thể làm lộ `this` vì prologue cấm tham chiếu `this` | Constructor lớp cha vẫn có thể gọi method override và gián tiếp để lớp con công bố object. |
| Gọi `super()` ngầm định vẫn để các câu lệnh trước nó chạy trước | Không. Nếu không có constructor invocation tường minh, `super()` ngầm định chạy trước và các câu lệnh trong thân là epilogue. |
| JEP 513 yêu cầu bật preview | Không. Tính năng final từ JDK 25, dùng được mà không bật preview. |

## 10. Phiên bản, biên dịch và preview liên quan

Với mã nguồn dùng Flexible Constructor Bodies, có thể biên dịch bằng JDK 25 trở lên:

```bash
javac --release 25 -d out src/Child.java
```

Không cần `--enable-preview`. Mã này cũng có thể biên dịch bằng JDK 27 với `--release 25` để giữ baseline Java 25.

JDK 27 có preview feature riêng là Primitive Types in Patterns, `instanceof`, and `switch` (JEP 532, fifth preview). Nếu một chương trình khác thực sự dùng cú pháp preview đó, phải biên dịch và chạy trên JDK 27 với cờ preview tương ứng:

```bash
javac --enable-preview --release 27 -d out src/PreviewExample.java
java --enable-preview -cp out PreviewExample
```

Preview JEP 532 không liên quan tới Flexible Constructor Bodies và không cần thiết cho các ví dụ trong bài. Không bật preview chỉ để sử dụng `super(...)` sau các câu lệnh prologue.

## 11. Quy trình thiết kế constructor an toàn

Khi cần dùng Flexible Constructor Bodies, có thể tự kiểm tra theo trình tự:

1. **Xác định dữ liệu đầu vào:** tham số nào cần kiểm tra hoặc chuẩn hóa trước khi gọi constructor lớp cha?
2. **Giữ prologue nhỏ:** ưu tiên validation, tính toán và tạo giá trị cục bộ; hạn chế I/O và side effect.
3. **Kiểm tra early construction context:** không đọc field, gọi instance method hoặc truyền `this`; chỉ gán blank field khi thật sự cần.
4. **Đánh giá failure point:** nếu prologue, đối số `super(...)` hoặc constructor lớp cha ném ngoại lệ, side effect nào đã xảy ra và cần xử lý ra sao?
5. **Rà soát constructor lớp cha:** nó có gọi method có thể override, đăng ký callback hoặc công bố tham chiếu tới object không?
6. **Kiểm tra thứ tự field initializer:** field initializer và instance initializer của lớp con chỉ chạy sau khi constructor lớp cha hoàn tất.
7. **Công bố object sau cùng:** chỉ đăng ký listener, khởi động thread hoặc đưa `this` ra bên ngoài sau khi constructor hoàn tất và bất biến của object đã được thiết lập.

## 12. Kiến thức cần nhớ

- Flexible Constructor Bodies cho phép prologue trước `super(...)` hoặc `this(...)`; phần sau lời gọi là epilogue.
- Prologue và biểu thức đối số constructor invocation thuộc early construction context, nơi bị giới hạn truy cập đối tượng đang tạo.
- Có thể gán blank instance field của lớp hiện tại bằng phép gán đơn trước `super(...)`; không được đọc field hoặc cập nhật dựa trên giá trị cũ.
- Nếu không viết constructor invocation tường minh, `super()` ngầm định chạy trước các câu lệnh trong thân constructor.
- Nếu prologue hoặc constructor được gọi ném ngoại lệ, các bước khởi tạo sau đó không chạy; side effect đã thực hiện không tự rollback.
- Field initializer và instance initializer của lớp con chạy sau khi constructor lớp cha hoàn tất, trước epilogue.
- Gán blank field trước `super()` có thể giúp constructor lớp cha nhìn thấy giá trị cần thiết khi gọi override, nhưng không làm object hoàn tất.
- Không gọi method có thể override từ constructor và không công bố `this` trước khi object được khởi tạo xong.
- JEP 513 là tính năng final từ JDK 25; JEP 512 cũng final từ JDK 25 nhưng là tính năng riêng. Không cần `--enable-preview` cho cả hai.

## Tài liệu tham khảo

- [JEP 513: Flexible Constructor Bodies](https://openjdk.org/jeps/513) — phiên bản chính thức của tính năng trong JDK 25.
- [JEP 447: Statements before `super(...)` (Preview)](https://openjdk.org/jeps/447) — preview lần đầu trong JDK 22.
- [JEP 482: Flexible Constructor Bodies (Second Preview)](https://openjdk.org/jeps/482) — preview lần thứ hai trong JDK 23.
- [JEP 492: Flexible Constructor Bodies (Third Preview)](https://openjdk.org/jeps/492) — preview lần thứ ba trong JDK 24.
- [Java Language Specification, Java SE 27 — §8.8.7 Constructor Body](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.8.7) — prologue, epilogue và early construction context.
- [Java Language Specification, Java SE 27 — §12.5 Creation of New Class Instances](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-12.html#jls-12.5) — thứ tự khởi tạo và cách xử lý khi constructor hoàn tất bất thường.
- [Flexible Constructor Bodies — Java Language Updates, Release 27](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html) — giới hạn truy cập instance, gán field trước `super(...)`, nested classes và record constructors.
- [Java Language Changes Summary, Release 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html) — xác nhận JEP 513 và JEP 512 là tính năng permanent từ JDK 25, cùng preview JEP 532 của JDK 27.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — ngày GA 15-09-2026 và các preview feature của JDK 27.
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — xác nhận JDK 25 là LTS và JDK 27 là feature release non-LTS.
- [Java Downloads — Oracle](https://www.oracle.com/java/technologies/downloads/) — xác nhận JDK 27 là release mới nhất và JDK 25 là LTS mới nhất tại thời điểm cập nhật bài.
- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512) — tính năng final JDK 25, độc lập với Flexible Constructor Bodies.
