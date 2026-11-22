# Hàm khởi tạo bổ sung và ủy quyền tới hàm khởi tạo chuẩn trong Java Record (Java 17)

## Mục tiêu và ý tưởng chính

Một `record` trong Java biểu diễn một lớp dữ liệu có **trạng thái được định nghĩa bởi danh sách record components**. Mỗi record có một **canonical constructor** (hàm khởi tạo chuẩn) nhận chính xác các component values theo thứ tự khai báo để khởi tạo những component fields.

Ngoài canonical constructor, record có thể khai báo **non-canonical constructors**, còn gọi là **additional constructors** hoặc **overloaded constructors**, để cung cấp những cách tạo object tiện dụng hơn: dùng giá trị mặc định, nhận dữ liệu ở dạng khác, chuyển đổi tham số, hoặc xây dựng từ một input tổng hợp.

**Quy tắc bắt buộc ở Java 17:**

> **Mọi non-canonical constructor của record phải bắt đầu bằng một alternate constructor invocation `this(...)`. Chuỗi ủy quyền có thể qua constructor bổ sung khác, nhưng cuối cùng phải dẫn tới canonical constructor của cùng record.**

Vì vậy constructor bổ sung **không được tự gán trực tiếp các record component fields** như constructor của class thông thường.

Ví dụ trọng tâm:

```java
public record User(String name, int age) {
    public User(String name) {
        this(name, 0);
    }
}
```

- Canonical constructor của `User` có chữ ký `User(String name, int age)`. Vì không khai báo tường minh nên Java cung cấp nó ngầm định.
- `User(String name)` là constructor **bổ sung**, vì nó nhận danh sách parameters khác component list.
- `this(name, 0);` phải là câu lệnh đầu tiên của constructor bổ sung.
- Chính canonical constructor cuối cùng khởi tạo component fields `name` và `age`.
- `new User("An")` tạo `User[name=An, age=0]`, không tạo một loại User thứ hai.

Bài hướng dẫn đầy đủ Java 17: canonical ngầm định/tường minh/compact, constructor overload, phân biệt chữ ký, lựa chọn overload, `this(...)` chaining, thứ tự chạy/validation, access modifiers, checked exceptions, generics/varargs, snapshot dữ liệu mutable, anti-pattern, cách test và bài tập. Các chương trình **runnable** có tên file, lệnh `javac --release 17` và stdout cụ thể; ví dụ cố ý sai được ghi là **compile-negative**.

## 1. Một record có những gì?

Xét khai báo:

```java
record Point(int x, int y) {
}
```

Danh sách `(int x, int y)` khai báo hai **record components**.

Theo Java 17, các record components dẫn đến:
- Private final fields tương ứng.
- Public accessor methods `x()` và `y()`.
- Một canonical constructor `Point(int x, int y)` nếu không được khai báo tường minh.
- Các implementations mặc định của `equals`, `hashCode` và `toString`.
- Một cấu trúc kế thừa đặc biệt: record là final và kế thừa từ `java.lang.Record`.

Bạn có thể tạo:

```java
Point point = new Point(3, 4);
```

Đối số `3` và `4` được chuyển đến **canonical constructor**. Nó gán trạng thái final `x=3` và `y=4`.

**Lưu ý:** record không tự deep immutable. Nếu component là mutable array/list/object, final field giữ **reference** không thể gán lại, nhưng referent có thể thay đổi nếu chưa phòng vệ.

## 2. Runnable: canonical constructor ngầm định

Lưu file **`ImplicitCanonicalDemo.java`**:

```java
record Point(int x, int y) {
}

public class ImplicitCanonicalDemo {
    public static void main(String[] args) {
        Point first = new Point(3, 4);
        Point second = new Point(3, 4);

        System.out.println(first);
        System.out.println(first.x());
        System.out.println(first.y());
        System.out.println(first.equals(second));
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImplicitCanonicalDemo.java
java ImplicitCanonicalDemo
```

Stdout:

```text
Point[x=3, y=4]
3
4
true
false
```

Hai Points có component values bằng nhau nên `equals` do record sinh trả true; nhưng là hai objects khác nên `==` false.

**Điểm khởi đầu:** muốn thêm một cách tạo điểm với tọa độ mặc định, bạn không thay các component fields; bạn thêm constructor **ủy quyền**.

## 3. Canonical constructor nhận bao nhiêu tham số?

Với:

```java
record OrderItem(String sku, int quantity, long unitPrice) {
}
```

Canonical constructor có **ba** parameters đúng types và thứ tự:
1. `String sku`;
2. `int quantity`;
3. `long unitPrice`.

Bản chất canonical signature xuất phát từ record header, không do tên method hoặc convention đặt ra. Khi khai báo constructor nhận **một hoặc hai tham số**, đó là non-canonical constructor.

### Phân biệt bằng chữ ký

```java
record OrderItem(String sku, int quantity, long unitPrice) {
    OrderItem(String sku) {
        this(sku, 1, 0L);
    }

    OrderItem(String sku, int quantity) {
        this(sku, quantity, 0L);
    }
}
```

Cả hai constructors trên là additional:
- `OrderItem(String)`;
- `OrderItem(String, int)`.

Chúng đều ủy quyền tới canonical `OrderItem(String, int, long)`. Tập overload không làm xuất hiện thêm state fields ngoài ba components.

## 4. Vì sao Java ép constructor bổ sung phải ủy quyền?

Với class thông thường, một constructor có thể trực tiếp gán instance fields:

```java
class Person {
    private final String name;
    private final int age;

    Person(String name) {
        this.name = name;
        this.age = 0;
    }
}
```

Đối với **record**, Java dùng canonical constructor làm **một điểm khởi tạo đầy đủ các component fields**. Mọi non-canonical constructor phải đi qua constructor đó thay vì tự chọn bộ field assignments riêng.

Lợi ích:
- Không có constructor overload quên khởi tạo một component.
- Canonical validation/normalization không bị bypass.
- Record component state được khởi tạo thống nhất.
- Khi thêm một component mới, compiler buộc các constructor delegations được cập nhật phù hợp.
- Giữ invariant “mọi record instance có canonical representation”.

**Quan trọng:** compiler bảo đảm **đường đi constructor**, không tự chứng minh tất cả business invariants. Bạn vẫn phải code validation đúng trong canonical constructor.

## 5. Runnable: hai constructor bổ sung

Lưu **`RecordOverloadDemo.java`**:

```java
record OrderItem(String sku, int quantity, long unitPrice) {
    OrderItem(String sku) {
        this(sku, 1, 0L);
    }

    OrderItem(String sku, int quantity) {
        this(sku, quantity, 0L);
    }
}

public class RecordOverloadDemo {
    public static void main(String[] args) {
        System.out.println(new OrderItem("A"));
        System.out.println(new OrderItem("B", 3));
        System.out.println(new OrderItem("C", 2, 500L));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordOverloadDemo.java
java RecordOverloadDemo
```

Stdout:

```text
OrderItem[sku=A, quantity=1, unitPrice=0]
OrderItem[sku=B, quantity=3, unitPrice=0]
OrderItem[sku=C, quantity=2, unitPrice=500]
```

Ba lối gọi tạo ra ba instances có cùng record type và state schema. Giá trị mặc định là **quyết định của overload**, không phải khả năng “default parameter” gắn vào record header.

## 6. Quy tắc vị trí: `this(...)` phải là câu lệnh đầu tiên

Trong Java 17, một constructor bổ sung phải **bắt đầu bằng alternate constructor invocation**:

```java
record Ticket(String id, int priority) {
    Ticket(String id) {
        this(id, 1);
    }
}
```

Không hợp lệ:

```java
record Ticket(String id, int priority) {
    Ticket(String id) {
        System.out.println("before");
        this(id, 1);
    }
}
```

Đây là **compile-negative snippet**, vì `this(...)` không nằm đầu constructor body theo quy tắc Java 17. Ngay cả một lệnh log, kiểm tra `if` hoặc khai báo local variable trước `this(...)` cũng vi phạm.

**Lưu ý phiên bản:** một số phiên bản Java mới hơn có thay đổi về statements trước explicit constructor invocation. Bài này dùng **`--release 17`**; không áp quy tắc của bản Java mới hơn sang Java 17.

### Muốn tính toán giá trị trước khi chuyển tới canonical thì làm sao?

Đưa logic vào **argument expressions** của lời gọi `this(...)`, ví dụ gọi static helper:

```java
record Ticket(String id, int priority) {
    Ticket(String id) {
        this(normalize(id), 1);
    }

    private static String normalize(String id) {
        return id.trim();
    }
}
```

Cần đảm bảo helper không phụ thuộc instance fields chưa được khởi tạo.

## 7. Runnable: helper xử lý tham số trong `this(...)`

Lưu **`DelegationHelperDemo.java`**:

```java
import java.util.Objects;

record Username(String value, String category) {
    Username(String raw) {
        this(normalize(raw), "regular");
    }

    private static String normalize(String text) {
        return Objects.requireNonNull(text, "text")
                .strip()
                .toLowerCase(java.util.Locale.ROOT);
    }
}

public class DelegationHelperDemo {
    public static void main(String[] args) {
        Username name = new Username("  ALICE  ");

        System.out.println(name);
        System.out.println(name.value());
        System.out.println(name.category());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DelegationHelperDemo.java
java DelegationHelperDemo
```

Stdout:

```text
Username[value=alice, category=regular]
alice
regular
```

`normalize(raw)` được tính khi đánh giá đối số cho `this(...)`. Sau khi lấy kết quả, canonical constructor `Username(String, String)` nhận dữ liệu đã chuẩn hóa.

## 8. Một chuỗi ủy quyền nhiều constructor có được không?

Có. Constructor bổ sung A có thể gọi constructor bổ sung B, rồi B gọi canonical C.

```text
A (1 argument)
  └── this(...) → B (2 arguments)
                    └── this(...) → C (canonical)
                                      └── khởi tạo components
```

Không bắt buộc **mỗi** non-canonical constructor gọi trực tiếp canonical. Điều bắt buộc là mọi chuỗi constructor invocations hợp lệ **cuối cùng** phải đi tới canonical, không được vòng tròn và không thể bỏ qua bước khởi tạo record state.

Ví dụ:

```java
record ConnectionOptions(String host, int port, boolean tls) {
    ConnectionOptions(String host) {
        this(host, 443);
    }

    ConnectionOptions(String host, int port) {
        this(host, port, true);
    }
}
```

`new ConnectionOptions("example.com")` gọi constructor một tham số, rồi hai tham số, rồi canonical ba tham số.

### Không trùng số lượng parameters nhưng khác kiểu?

Có thể overload cùng số lượng parameters nếu types khác và không vi phạm signature conflicts; Java dùng overload resolution thông thường. Cần tránh ambiguity như `null` khi có `String` và `Integer`.

## 9. Runnable: trace chuỗi ủy quyền ba tầng

Lưu **`RecordDelegationChainDemo.java`**:

```java
record Endpoint(String host, int port, boolean secure) {
    Endpoint {
        System.out.println("canonical");
    }

    Endpoint(String host, int port) {
        this(host, port, true);
        System.out.println("two-args");
    }

    Endpoint(String host) {
        this(host, 443);
        System.out.println("one-arg");
    }
}

public class RecordDelegationChainDemo {
    public static void main(String[] args) {
        Endpoint endpoint = new Endpoint("api.example");

        System.out.println(endpoint);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordDelegationChainDemo.java
java RecordDelegationChainDemo
```

Stdout:

```text
canonical
two-args
one-arg
Endpoint[host=api.example, port=443, secure=true]
```

Đây là điểm rất dễ dự đoán ngược:

- Lời gọi đầu tiên ở constructor một tham số là `this(host, 443)`.
- Constructor hai tham số tiếp tục `this(host, port, true)`.
- **Canonical body thực thi trước khi các dòng sau `this(...)` của additional constructors được thực thi.**
- Sau khi canonical hoàn thành, điều khiển trở lại hai tham số rồi một tham số.

Bạn có thể tưởng tượng call stack **đi xuống canonical rồi quay ngược trở lên**.

## 10. Canonical constructor có những dạng nào?

Java record có đúng một canonical constructor về mặt ngữ nghĩa, có thể được cung cấp theo một trong ba cách:

1. **Implicit canonical** do compiler sinh nếu bạn không khai báo explicit canonical.
2. **Normal canonical** do bạn khai báo với đầy đủ parameter list khớp components.
3. **Compact canonical** do bạn khai báo bằng `RecordName { ... }`, không liệt kê parameters.

Bạn **không thể** khai báo đồng thời một normal canonical và một compact canonical cho cùng record.

### 10.1. Implicit canonical

```java
record Size(int width, int height) {
    Size(int edge) {
        this(edge, edge);
    }
}
```

Không khai báo normal/compact canonical, nhưng `this(edge, edge)` vẫn gọi canonical constructor ngầm định.

### 10.2. Normal canonical

```java
record Size(int width, int height) {
    Size(int width, int height) {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("negative size");
        }
        this.width = width;
        this.height = height;
    }

    Size(int edge) {
        this(edge, edge);
    }
}
```

Normal canonical **phải gán các component fields đầy đủ**, đồng thời parameter **names và types** phải khớp record components theo Java 17 rules.

### 10.3. Compact canonical

```java
record Size(int width, int height) {
    Size {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("negative size");
        }
    }

    Size(int edge) {
        this(edge, edge);
    }
}
```

Compact canonical **không lặp parameter list**. Compiler tự gán component fields từ implicit parameters **sau khi body compact hoàn tất bình thường**. Dùng dạng này khi validation/normalization là mục tiêu chính.

## 11. Runnable: implicit canonical + constructor bổ sung

Lưu **`ImplicitWithAuxiliaryDemo.java`**:

```java
record Rectangle(int width, int height) {
    Rectangle(int edge) {
        this(edge, edge);
    }

    int area() {
        return width * height;
    }
}

public class ImplicitWithAuxiliaryDemo {
    public static void main(String[] args) {
        Rectangle square = new Rectangle(5);
        Rectangle wide = new Rectangle(3, 8);

        System.out.println(square);
        System.out.println(square.area());
        System.out.println(wide.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ImplicitWithAuxiliaryDemo.java
java ImplicitWithAuxiliaryDemo
```

Stdout:

```text
Rectangle[width=5, height=5]
25
24
```

Mặc dù source chỉ khai báo constructor nhận một `int`, `new Rectangle(3,8)` vẫn hợp lệ vì record có canonical constructor ngầm định.

## 12. Runnable: normal canonical + validation

Lưu **`NormalCanonicalDemo.java`**:

```java
record Interval(int start, int end) {
    Interval(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException(
                    "start must not exceed end");
        }
        this.start = start;
        this.end = end;
    }

    Interval(int point) {
        this(point, point);
    }
}

public class NormalCanonicalDemo {
    public static void main(String[] args) {
        System.out.println(new Interval(7));
        System.out.println(new Interval(2, 9));

        try {
            new Interval(9, 2);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NormalCanonicalDemo.java
java NormalCanonicalDemo
```

Stdout:

```text
Interval[start=7, end=7]
Interval[start=2, end=9]
start must not exceed end
```

Constructor một tham số `this(point,point)` không tự gán fields: canonical thực hiện validation và assignments. Khi truyền (9,2), normal canonical ném exception và object không được khởi tạo thành công.

## 13. Compact canonical: tự gán fields sau body

Cú pháp:

```java
record Email(String address) {
    Email {
        address = address.strip().toLowerCase(
                java.util.Locale.ROOT);
    }
}
```

Trong compact constructor:
- Identifier `address` là **implicit constructor parameter**.
- Có thể gán lại parameter `address` để chuẩn hóa.
- Sau compact body, Java thực hiện implicit assignment `this.address = address`.
- Không được viết `this.address = ...` trong compact body.
- Không được viết `this(...)` trong compact canonical body.

Với record có nhiều components, mỗi component field được gán từ parameter tương ứng sau body.

### Sự khác biệt giữa `address` và `this.address`

Trong compact body, `address` đại diện cho parameter; còn component field `this.address` chưa đến lúc được gán bằng implicit assignment. Đừng đọc fields chưa được khởi tạo để validate; dùng parameters.

## 14. Runnable: compact canonical và overload cùng đi qua validation

Lưu **`CompactCanonicalDemo.java`**:

```java
import java.util.Locale;
import java.util.Objects;

record Email(String address, boolean verified) {
    Email {
        address = Objects.requireNonNull(address, "address")
                .strip().toLowerCase(Locale.ROOT);
        if (!address.contains("@")) {
            throw new IllegalArgumentException("invalid email");
        }
    }

    Email(String address) {
        this(address, false);
    }
}

public class CompactCanonicalDemo {
    public static void main(String[] args) {
        System.out.println(new Email("  ALICE@EXAMPLE.COM  "));
        System.out.println(new Email("Bob@Example.Com", true));

        try {
            new Email("invalid");
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CompactCanonicalDemo.java
java CompactCanonicalDemo
```

Stdout:

```text
Email[address=alice@example.com, verified=false]
Email[address=bob@example.com, verified=true]
invalid email
```

Cả `new Email(String)` lẫn `new Email(String, boolean)` đều trải qua compact canonical validation. Một constructor phụ không thể bypass quy tắc bắt buộc address chứa `@`.

## 15. Thứ tự thực thi và vị trí của default values

Với:

```java
record Value(int x, int y) {
    Value {
        System.out.println("canonical");
    }

    Value(int x) {
        this(x, 0);
        System.out.println("auxiliary");
    }
}
```

`new Value(7)`:
1. Đánh giá argument `7`.
2. Chọn constructor phụ `Value(int)`.
3. Thực hiện lời gọi `this(7, 0)` đầu tiên.
4. Compact canonical chạy, kiểm tra/chuyển đổi nếu có.
5. Compiler gán component fields từ parameters sau body.
6. Quay về constructor phụ, chạy log `auxiliary`.
7. Trả object hoàn chỉnh cho caller.

**Không phải** constructor phụ tạo object tạm trước rồi canonical tạo object khác. Trong một `new`, chỉ có **một object** được khởi tạo theo chuỗi constructors.

### Khi validation thất bại

Nếu canonical constructor ném exception:
- Control **không quay về** các statements sau `this(...)` của constructor phụ.
- Constructor caller không nhận được record instance hoàn tất.
- Logic side effects trước exception có thể đã chạy (tránh side effects không cần thiết trong constructors).
- Exception lan ra cho đến nơi xử lý phù hợp.

## 16. Runnable: lỗi tại canonical làm dừng chuỗi

Lưu **`RecordValidationFlowDemo.java`**:

```java
record Port(int value, String protocol) {
    Port {
        System.out.println("canonical:" + value);
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }

    Port(int value) {
        this(value, "tcp");
        System.out.println("aux-completed");
    }
}

public class RecordValidationFlowDemo {
    public static void main(String[] args) {
        try {
            new Port(0);
        } catch (IllegalArgumentException error) {
            System.out.println("caught:" + error.getMessage());
        }

        System.out.println(new Port(8080));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordValidationFlowDemo.java
java RecordValidationFlowDemo
```

Stdout:

```text
canonical:0
caught:invalid port
canonical:8080
aux-completed
Port[value=8080, protocol=tcp]
```

Lời gọi `new Port(0)` chưa bao giờ in `aux-completed`. Ngược lại, case 8080 validate thành công nên constructor phụ chạy tiếp sau canonical.

## 17. Vì sao không được gán trực tiếp component fields trong constructor phụ?

Compile-negative:

```java
record Pair(int left, int right) {
    Pair(int value) {
        this.left = value;
        this.right = value;
    }
}
```

Không hợp lệ theo hai lý do liên quan:
- Non-canonical constructor **phải bắt đầu bằng alternate `this(...)` invocation**.
- Đường khởi tạo component fields thuộc canonical constructor, không phải một constructor phụ tự gán fields theo cách thủ công.

Bản sửa:

```java
record Pair(int left, int right) {
    Pair(int value) {
        this(value, value);
    }
}
```

### Không dùng initializer blocks để lách

Record cũng hạn chế trạng thái instance ngoài components:
- Không được khai báo additional non-static instance fields.
- Không được khai báo instance initializer blocks.
- Có thể khai báo static members khi phù hợp.

Lý do là record state được mô tả bởi component header, không bởi một tập fields mở rộng tùy ý.

## 18. Compile-negative: constructor phụ bỏ qua `this(...)`

```java
record Point(int x, int y) {
    Point() {
        // Thiếu this(...).
    }
}
```

**Sai trên Java 17.** Không có lời gọi alternate constructor ở đầu body.

Sửa:

```java
record Point(int x, int y) {
    Point() {
        this(0, 0);
    }
}
```

Java không tự “điền mặc định 0,0” cho component fields khi developer khai báo một additional constructor rỗng. Record vẫn có canonical constructor, và additional constructor phải sử dụng nó.

## 19. Compile-negative: `super(...)` không thay thế `this(...)`

Sai:

```java
record Point(int x, int y) {
    Point() {
        super();
    }
}
```

`Point` là record và kế thừa đặc biệt từ `java.lang.Record`. Non-canonical constructor của Point vẫn phải gọi **constructor khác của cùng Point qua `this(...)`**, không được dùng explicit `super()` thay cho đường khởi tạo component fields.

Sửa:

```java
record Point(int x, int y) {
    Point() {
        this(0, 0);
    }
}
```

**Không nhầm `this(...)` với `this.x`**: một là constructor invocation, một là field access. Hai cú pháp có vai trò hoàn toàn khác nhau.

## 20. Chuỗi constructor vòng tròn không hợp lệ

Một constructor A gọi B, B gọi A, không có đường nào tới canonical:

```java
record Example(int value, String note) {
    Example(int value) {
        this(String.valueOf(value));
    }

    Example(String note) {
        this(0);
    }
}
```

Đây là **compile-negative**: recursive constructor invocation. Compiler phát hiện chu kỳ.

Sửa:

```java
record Example(int value, String note) {
    Example(int value) {
        this(value, "generated");
    }

    Example(String note) {
        this(0, note);
    }
}
```

Giờ cả hai constructors đều kết thúc tại canonical `Example(int, String)`.

### Cẩn thận với nhiều overload

Khi code nhiều constructors, bạn có thể vẽ directed graph với node là constructor signature và cạnh là `this(...)`. Đồ thị phải không chu kỳ và **mọi đường đi từ constructor bổ sung đều tới canonical**.

## 21. Quy tắc overload resolution áp dụng bình thường

Giả sử:

```java
record Label(String text, int priority) {
    Label(int priority) {
        this("default", priority);
    }

    Label(String text) {
        this(text, 0);
    }
}
```

`new Label(3)` chọn `Label(int)`; `new Label("A")` chọn `Label(String)`.

Java vẫn xét:
- Exact match.
- Primitive widening.
- Boxing/unboxing.
- Varargs.
- Most-specific selection.
- Ambiguity giữa reference types không liên quan khi truyền `null`.

**Không có quy tắc riêng “ưu tiên canonical”**: overload resolution chọn constructor phù hợp với expressions. Nếu `new Label("A", 1)`, canonical với hai parameters được chọn. Nếu `new Label("A")`, overload một parameter được chọn.

### Cẩn thận với `null`

Nếu có `Label(String)` và `Label(Integer)`, `new Label(null)` có thể ambiguous. Cast hoặc factory method tên rõ giúp loại ambiguity.

## 22. Runnable: overload và chọn constructor

Lưu **`RecordOverloadSelectionDemo.java`**:

```java
record Value(String text, long number) {
    Value(int number) {
        this("int", number);
    }

    Value(String text) {
        this(text, 0L);
    }
}

public class RecordOverloadSelectionDemo {
    public static void main(String[] args) {
        System.out.println(new Value(5));
        System.out.println(new Value("hello"));
        System.out.println(new Value("world", 9L));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordOverloadSelectionDemo.java
java RecordOverloadSelectionDemo
```

Stdout:

```text
Value[text=int, number=5]
Value[text=hello, number=0]
Value[text=world, number=9]
```

`Value(int)` truyền `int` sang vị trí `long` của canonical thông qua primitive widening. Canonical đảm nhận việc khởi tạo thành phần `long number`.

## 23. Parameter names và types của normal canonical

Với record:

```java
record User(String name, int age) {
}
```

Một **normal canonical constructor khai báo tường minh** phải có parameters trùng **tên và kiểu** với record components:

```java
record User(String name, int age) {
    User(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Cố đổi tên parameter:

```java
record User(String name, int age) {
    User(String name, int years) {
        this.name = name;
        this.age = years;
    }
}
```

Là **compile-negative**. Constructor `User(String, int)` có canonical signature theo parameter types nhưng parameter `years` không khớp component `age`. Java không coi nó là “overload bổ sung” chỉ vì parameter name khác.

### Không được tạo overload chỉ khác tên tham số

Đối với Java constructors/methods, parameter names **không phân biệt signatures**. Hai constructors `User(String name,int age)` và `User(String n,int a)` không phải hai overload khác nhau.

## 24. Normal canonical và compact canonical không đồng thời

Ví dụ cố ý sai:

```java
record Counter(int value) {
    Counter(int value) {
        this.value = value;
    }

    Counter {
        if (value < 0) {
            throw new IllegalArgumentException();
        }
    }
}
```

Cả hai đều là khai báo canonical constructor của cùng record `Counter`: một normal, một compact. Java từ chối duplicate canonical signatures.

Chọn **một**:
- Normal nếu cần assignments điều khiển tường minh.
- Compact nếu chỉ cần validation/normalization.

Đối với đa số value record, compact thường ngắn hơn, tránh lặp component field assignments dễ sai.

## 25. Compact constructor không gọi `this(...)`

Dạng sai:

```java
record Value(int x, int y) {
    Value {
        this(x, y);
    }
}
```

Đây là **compile-negative**: compact **chính là canonical constructor**, nên không được chứa explicit constructor invocation `this(...)`. Nó không cần “ủy quyền tới canonical” vì nó **đã là canonical**.

Thay vào đó:

```java
record Value(int x, int y) {
    Value {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}
```

Các component fields được compiler gán sau compact body.

### Compact constructor cũng không được `return;`

Compact canonical body không được có `return` statement, dù đó là bare `return;` để thoát sớm. Nếu validation không hợp lệ, ném exception; nếu có xử lý nhánh, dùng control flow thông thường không chứa explicit return.

## 26. Compact constructor không được gán trực tiếp field

Sai:

```java
record Email(String address) {
    Email {
        this.address = address.strip();
    }
}
```

Bản sửa:

```java
record Email(String address) {
    Email {
        address = address.strip();
    }
}
```

`address` không có `this.` là **implicit formal parameter**. Khi body kết thúc, implicit assignment gán field `this.address`.

Nếu cần rõ ràng về đọc dữ liệu trước khi chuẩn hóa:

```java
record Email(String address) {
    Email {
        String normalized = address.strip();
        address = normalized;
    }
}
```

Compiler vẫn gán field ở cuối.

## 27. Access modifier trên canonical và constructor phụ

Một record có thể khai báo public hoặc package-private ở top-level, hoặc dùng member visibility phù hợp khi nested.

Canonical constructor **phải có accessibility ít nhất bằng record** theo Java 17:
- `public record R(...)` → explicitly declared canonical constructor phải public.
- Package-private top-level record → canonical không được private.
- Private member record có quy tắc phù hợp với accessibility của record.
- Một implicitly declared canonical constructor có accessibility phù hợp record.

Ví dụ hợp lệ:

```java
public record PublicPoint(int x, int y) {
    public PublicPoint {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException();
        }
    }

    private PublicPoint(int same) {
        this(same, same);
    }
}
```

Ở đây constructor phụ một `int` có thể **private** vì nó không phải canonical. Một public static factory **bên trong record** vẫn có thể gọi nó.

**Lưu ý:** ví dụ trên là một snippet của file `PublicPoint.java`, không phải class Main hoàn chỉnh.

### Sai với public record

```java
public record R(int x) {
    private R {
    }
}
```

Là compile-negative do canonical constructor private có accessibility hẹp hơn public record.

## 28. Runnable: private constructor bổ sung và public factory

Lưu **`PrivateAuxiliaryDemo.java`**:

```java
record Product(String code, int quantity) {
    Product {
        if (quantity < 1) {
            throw new IllegalArgumentException("quantity");
        }
    }

    private Product(String code) {
        this(code, 1);
    }

    static Product single(String code) {
        return new Product(code);
    }
}

public class PrivateAuxiliaryDemo {
    public static void main(String[] args) {
        Product product = Product.single("P-1");

        System.out.println(product);
        System.out.println(product.quantity());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PrivateAuxiliaryDemo.java
java PrivateAuxiliaryDemo
```

Stdout:

```text
Product[code=P-1, quantity=1]
1
```

Factory giúp đặt tên ý định `single`. Private overload tránh mở rộng constructor API không cần thiết. Validation ở compact canonical vẫn chạy.

## 29. Checked exceptions: canonical và additional có quy tắc khác

**Java 17:** một explicitly declared normal canonical constructor **không được có `throws` clause**. Compact canonical cũng không dùng `throws` clause như một normal constructor có parameter list. Validation thường dùng unchecked exceptions như `IllegalArgumentException` hoặc `NullPointerException`.

Ví dụ canonical cố ý sai:

```java
record Document(String text) {
    Document(String text) throws java.io.IOException {
        this.text = text;
    }
}
```

**Compile-negative** do normal canonical constructor có checked `throws` clause. Ngay cả nếu body không ném exception, `throws` trên canonical vẫn bị cấm.

**Non-canonical constructor** có thể khai báo checked `throws` clause, ví dụ khi nó đọc file/parse nguồn rồi **ủy quyền** qua `this(...)`.

### Lưu ý đánh giá đối số

Checked exception có thể được ném **trong lúc đánh giá argument expression cho `this(...)`**. Additional constructor cần catch/declare phù hợp; không thể đặt một `try` statement trước `this(...)` trong Java 17.

## 30. Runnable: additional constructor đọc file và `throws IOException`

Lưu **`RecordCheckedExceptionDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

record Document(String text, String origin) {
    Document(Path path) throws IOException {
        this(Files.readString(path), path.toString());
    }
}

public class RecordCheckedExceptionDemo {
    public static void main(String[] args) {
        try {
            Document doc =
                    new Document(Path.of("missing-record-example.txt"));

            System.out.println(doc);
        } catch (IOException error) {
            System.out.println("io-error");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordCheckedExceptionDemo.java
java RecordCheckedExceptionDemo
```

Stdout **nếu file `missing-record-example.txt` không tồn tại**:

```text
io-error
```

Trong một working directory bất kỳ, file có thể tình cờ tồn tại; vì vậy output phụ thuộc điều kiện được nêu rõ. Nếu muốn test hoàn toàn deterministic, tạo một helper ném checked exception hoặc kiểm tra file setup rõ ràng trước khi chạy. Ví dụ minh họa syntax `throws` hợp lệ ở additional constructor, không dựa trên hành vi IO làm contract.

### Tại sao hai constructors khác nhau?

`Document(Path)` không phải canonical vì record header là `(String text, String origin)`. Nó có thể khai báo throws. `Document(String, String)` là canonical ngầm định và khởi tạo fields.

## 31. Runnable: kiểm thử checked exception với input giả lập xác định

Lưu **`DeterministicCheckedConstructorDemo.java`**:

```java
import java.io.IOException;

record ImportedText(String content, int version) {
    ImportedText(boolean fail) throws IOException {
        this(read(fail), 1);
    }

    private static String read(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("read failed");
        }
        return "ready";
    }
}

public class DeterministicCheckedConstructorDemo {
    public static void main(String[] args) {
        try {
            System.out.println(new ImportedText(false));

            new ImportedText(true);
        } catch (IOException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DeterministicCheckedConstructorDemo.java
java DeterministicCheckedConstructorDemo
```

Stdout:

```text
ImportedText[content=ready, version=1]
read failed
```

Tham số `fail` được dùng làm argument cho static helper. Khi helper ném `IOException`, canonical không được gọi và additional constructor không hoàn thành.

## 32. Generic record và constructor bổ sung

Record có thể generic:

```java
record Box<T>(T value, String label) {
    Box(T value) {
        this(value, "default");
    }
}
```

Canonical signature sử dụng `T` và `String` theo generic record declaration. Additional constructor `Box(T)` có thể chuyển value và label mặc định đến canonical.

### Overload/type inference

`Box<String> box = new Box<>("Java");` có thể suy ra `T=String` trong Java 17. Hãy phân biệt constructor **generic tự khai báo type parameters** với record có type parameter ở header; canonical constructor không được khai báo type parameters riêng, còn generic class parameter `T` là thuộc record.

### Runnable

Lưu **`GenericRecordAuxDemo.java`**:

```java
record Box<T>(T value, String label) {
    Box(T value) {
        this(value, "default");
    }
}

public class GenericRecordAuxDemo {
    public static void main(String[] args) {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(17, "version");

        System.out.println(text);
        System.out.println(number);
        System.out.println(text.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 GenericRecordAuxDemo.java
java GenericRecordAuxDemo
```

Stdout:

```text
Box[value=Java, label=default]
Box[value=17, label=version]
Java
```

Cả hai objects có component schema `(value,label)`; thêm constructor một parameter không làm xuất hiện instance field thứ ba.

## 33. Record có zero components vẫn có canonical

```java
record Marker() {
}
```

Canonical constructor ở đây có **zero parameters**: `Marker()`.

Bạn có thể khai báo **additional constructor có tham số**, miễn ủy quyền tới canonical:

```java
record Marker() {
    Marker(String ignored) {
        this();
    }
}
```

Không thể khai báo một `Marker()` riêng như “constructor bổ sung không tham số”: nó **trùng canonical signature**.

### Runnable

Lưu **`EmptyRecordDemo.java`**:

```java
record Marker() {
    Marker(String description) {
        this();
    }
}

public class EmptyRecordDemo {
    public static void main(String[] args) {
        Marker first = new Marker();
        Marker second = new Marker("ignored");

        System.out.println(first);
        System.out.println(second);
        System.out.println(first.equals(second));
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EmptyRecordDemo.java
java EmptyRecordDemo
```

Stdout:

```text
Marker[]
Marker[]
true
false
```

Hai zero-component record instances có equality theo components (không có components để khác nhau), nhưng `==` vẫn phân biệt reference identity.

## 34. Record có varargs component

Một record có thể khai báo varargs ở component cuối:

```java
record Tags(String... values) {
}
```

Canonical constructor có dạng variable arity tương ứng `String... values`. Bạn có thể thêm một additional constructor no-arg:

```java
record Tags(String... values) {
    Tags() {
        this(new String[0]);
    }
}
```

**Cẩn thận overload ambiguity:** một lệnh `this()` bên trong `Tags()` sẽ tự gọi lại constructor no-arg, gây recursion. Dùng `this(new String[0])` để chọn rõ canonical constructor (varargs nhận array).

### Snapshot arrays

Các component fields final chỉ giữ reference. String array vẫn mutable. Muốn record có value-like behavior an toàn, cần clone array khi nhận và khi trả accessor nếu public API cần isolation.

## 35. Runnable: varargs record với defensive copy

Lưu **`VarargsRecordDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Tags(String... values) {
    Tags {
        values = Objects.requireNonNull(values).clone();
    }

    Tags() {
        this(new String[0]);
    }

    @Override
    public String[] values() {
        return values.clone();
    }
}

public class VarargsRecordDemo {
    public static void main(String[] args) {
        String[] source = {"A", "B"};

        Tags tags = new Tags(source);
        source[0] = "CHANGED";

        System.out.println(Arrays.toString(tags.values()));
        System.out.println(Arrays.toString(new Tags().values()));

        String[] copy = tags.values();
        copy[1] = "OTHER";
        System.out.println(Arrays.toString(tags.values()));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 VarargsRecordDemo.java
java VarargsRecordDemo
```

Stdout:

```text
[A, B]
[]
[A, B]
```

Compact canonical clone incoming array; accessor clone outgoing array. Constructor bổ sung no-arg vẫn đi qua canonical và nhận cùng defensive-copy policy.

**Caveat:** record mặc định `equals` cho array components dựa trên reference equality của arrays, không deep content equality. Clone giúp ownership nhưng không tự biến array thành value component. Nếu cần deep structural equality, cân nhắc immutable `List.copyOf` làm component hoặc override value methods nhất quán với record invariants.

## 36. Additional constructors không thay đổi generated accessors/toString

Với `record Item(String sku,int qty)`, các constructor overload chỉ là **những đường tạo Item**. Sau khi Item đã khởi tạo:
- `sku()` trả component `sku`.
- `qty()` trả component `qty`.
- `toString()` phản ánh record components.
- `equals/hashCode` theo record components (trừ khi override hợp lệ).
- Không có thông tin mặc định về overload nào đã được dùng để tạo object.

Ví dụ hai đường tạo cùng state:

```java
Item a = new Item("A");      // this("A", 1)
Item b = new Item("A", 1);   // canonical
```

Nếu component values bằng nhau và không tùy biến equality, `a.equals(b)` true. Không có component “usedConstructor” ngầm định.

### Điều này dẫn đến cách thiết kế

Constructor overload nên tạo ra **cùng một ý nghĩa record** với canonical arguments đã normalize. Đừng dùng overload để bí mật tạo các “mode” khác nhau không được biểu diễn trong record components, vì các mode ấy không được thể hiện trong value equality hay toString.

## 37. Runnable: các cách tạo có cùng value semantics

Lưu **`EqualConstructionPathsDemo.java`**:

```java
record Item(String sku, int qty) {
    Item(String sku) {
        this(sku, 1);
    }
}

public class EqualConstructionPathsDemo {
    public static void main(String[] args) {
        Item first = new Item("A");
        Item second = new Item("A", 1);

        System.out.println(first);
        System.out.println(second);
        System.out.println(first.equals(second));
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EqualConstructionPathsDemo.java
java EqualConstructionPathsDemo
```

Stdout:

```text
Item[sku=A, qty=1]
Item[sku=A, qty=1]
true
false
```

Constructor bổ sung không phải factory cache. Hai `new` tạo hai objects riêng, nhưng cùng record value.

## 38. Tránh lặp validation trong mọi constructor phụ

Anti-pattern:

```java
record Person(String name, int age) {
    Person {
        if (age < 0) {
            throw new IllegalArgumentException("negative age");
        }
    }

    Person(String name) {
        this(name, 0);
        // Không cần kiểm tra lại age >= 0 ở đây.
    }
}
```

Validation về **tính hợp lệ của trạng thái record** nên nằm ở canonical (compact/normal) để tất cả đường khởi tạo đi qua.

Constructor phụ có thể kiểm tra **định dạng input riêng** trước lời gọi canonical bằng static helper:
- Parse một chuỗi.
- Chuyển đổi đơn vị.
- Decode external code.
- Đặt default.
- Validate input chỉ tồn tại ở overload đó.

**Phân biệt:** validation state invariant của record ≠ validation input format của một constructor adapter.

## 39. Runnable: nhiều overload chung invariant

Lưu **`UnifiedInvariantDemo.java`**:

```java
import java.util.Objects;

record Person(String name, int age) {
    Person {
        name = Objects.requireNonNull(name).strip();
        if (name.isEmpty() || age < 0) {
            throw new IllegalArgumentException("invalid person");
        }
    }

    Person(String name) {
        this(name, 0);
    }

    Person() {
        this("Guest");
    }
}

public class UnifiedInvariantDemo {
    public static void main(String[] args) {
        System.out.println(new Person());
        System.out.println(new Person("  An  "));
        System.out.println(new Person("Binh", 22));

        try {
            new Person("", 1);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 UnifiedInvariantDemo.java
java UnifiedInvariantDemo
```

Stdout:

```text
Person[name=Guest, age=0]
Person[name=An, age=0]
Person[name=Binh, age=22]
invalid person
```

Tất cả overloads, kể cả zero-arg, đều phải qua compact canonical. Validation không bị nhân bản giữa constructors.

## 40. Mặc định khác với “default parameters” của ngôn ngữ

Java **không** hỗ trợ khai báo constructor parameters có default expressions theo kiểu:

```java
// Không phải cú pháp Java:
record Person(String name, int age = 0) {}
```

Thay thế:
- Additional constructors với `this(...)`.
- Static factory methods có tên ý nghĩa.
- Builder khi có nhiều tùy chọn độc lập.
- Method overloads nếu API hợp lý.

Một constructor phụ `Person(String name)` tương đương một **convenience overload**, không phải language-level default argument trên canonical constructor.

### Bao nhiêu overload là quá nhiều?

Nếu record có 10 components và bạn tạo 20 overloads tùy các combinations mặc định, caller rất khó biết chính xác tổ hợp nào được chọn. Cân nhắc một parameter object, static named factories hoặc builder. Record thường hiệu quả nhất khi state components ít, rõ và có invariant chung.

## 41. Static factory thay vì constructor overload

Factory có thể hữu ích khi:
- Muốn đặt tên cho intent: `Money.zero(currency)`, `Range.single(value)`.
- Có nhiều overload trùng kiểu dễ gây nhầm.
- Input parse có lỗi cần trả `Optional`/`Result`.
- Muốn cache một số giá trị bất biến (nhưng record constructors vẫn tạo object mỗi lần `new`).
- Cần version/migration logic trước khi quyết định state.

```java
record Money(long cents, String currency) {
    static Money zero(String currency) {
        return new Money(0L, currency);
    }
}
```

Factory `zero` không phải constructor, không cần tuân quy tắc `this(...)`, nhưng cuối cùng vẫn dùng canonical construction để duy trì invariant.

**Đừng lầm rằng vì factory không bị ép `this(...)` nên có thể gán component fields tùy ý**: record component fields vẫn final và thuộc instance được canonical tạo.

## 42. Runnable: named factory + additional constructor

Lưu **`RecordFactoryDemo.java`**:

```java
import java.util.Objects;

record Money(long cents, String currency) {
    Money {
        if (cents < 0) {
            throw new IllegalArgumentException("negative");
        }
        currency = Objects.requireNonNull(currency).strip();
        if (currency.isEmpty()) {
            throw new IllegalArgumentException("currency");
        }
    }

    Money(long cents) {
        this(cents, "VND");
    }

    static Money zero(String currency) {
        return new Money(0L, currency);
    }
}

public class RecordFactoryDemo {
    public static void main(String[] args) {
        System.out.println(new Money(500L));
        System.out.println(Money.zero("USD"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordFactoryDemo.java
java RecordFactoryDemo
```

Stdout:

```text
Money[cents=500, currency=VND]
Money[cents=0, currency=USD]
```

`Money(long)` dùng `this(cents,"VND")`. Factory `zero` dùng canonical trực tiếp. Cả hai cùng đi qua compact validation.

## 43. Record constructor + escaping `this` và inheritance

Một record:
- Là `final`, không thể extends class tùy ý.
- Ngầm extends `java.lang.Record`.
- Có record components cố định.
- Không có mutable inherited instance fields từ user-defined superclass.
- Không thể dùng subclass constructor để mở rộng schema của record.

Do vậy constructor bổ sung nên **chuyển đổi dữ liệu đầu vào thành component tuple hợp lệ** thay vì mô phỏng inheritance polymorphic construction.

Cẩn thận khi truyền `this` từ canonical/auxiliary constructor ra nơi khác trước khi hoàn tất khởi tạo. Quy tắc record không làm việc publish partially constructed object trở nên an toàn. Trong Java 17, non-canonical constructor không được truy cập instance members trước explicit `this(...)`, còn canonical constructor cần tránh gọi overridable behavior/giao object reference ra global registry dù record là final.

### Dữ liệu mutable cần chú ý hơn

Một record giữ `List` hoặc array vẫn có thể liên quan tới shared mutable referents. Constructor overload nên đi qua defensive-copy policy ở canonical. Không để overload một tham số copy list còn canonical hai tham số lại giữ live alias nếu contract intended immutable snapshot.

## 44. Constructor overload và Java serialization của record

Java object serialization có cơ chế riêng đối với record classes. Record deserialization có thể gọi **canonical constructor** khi khôi phục state, theo quy tắc record serialization tương ứng.

Điều này làm validation trong canonical quan trọng hơn validation chỉ ở một overload:
- Nếu invariant chỉ nằm trong additional constructor, các đường tạo trực tiếp canonical có thể bypass.
- Java record serialization không có nghĩa mọi non-canonical overload sẽ được chọn khi đọc dữ liệu.
- External serializers/JSON mappers có quy tắc constructor-binding khác nhau; không tự khẳng định chúng luôn chọn canonical hoặc luôn chọn no-arg.

**Nên tập trung invariant state tại canonical**, còn integration serializer cần tests phù hợp với thư viện/phiên bản thực tế.

### Phân biệt construction và wire format

Thêm một overload tiện dụng thường không đổi record component schema; thêm/xóa/đổi tên/đổi kiểu components mới là thay đổi mạnh với các consumer dựa trên schema, reflection và serialization.

## 45. Reflection: canonical và additional đều là constructors

Java reflection có thể liệt kê `getDeclaredConstructors()` trên record class. Ngoài ra `Class.isRecord()` cho biết class có phải record và `getRecordComponents()` trả metadata về components.

Tuy nhiên reflection không cung cấp “constructor phụ nào đã được gọi” cho một record instance sau khi tạo.

Khi cần biết canonical signature:
1. Đọc `getRecordComponents()` theo thứ tự.
2. Lấy types từng component.
3. Canonical constructor có parameter types tương ứng thứ tự đó.
4. Các constructor signatures khác là overloads.

Nếu có generic erasure hoặc varargs, dùng Java reflection types phù hợp và hiểu compiler-generated signatures. Không dựa vào thứ tự `getDeclaredConstructors()` để chọn “constructor đầu tiên” là canonical.

### Vai trò của access modifiers

Private additional constructors vẫn có thể xuất hiện trong `getDeclaredConstructors()`. “Có metadata qua reflection” không có nghĩa code ngoài package/module được phép invoke chúng mà không có access checks.

## 46. Runnable: kiểm tra số constructors bằng Reflection

Lưu **`RecordReflectionDemo.java`**:

```java
record Pair(int left, int right) {
    Pair(int value) {
        this(value, value);
    }

    Pair() {
        this(0);
    }
}

public class RecordReflectionDemo {
    public static void main(String[] args) {
        Class<Pair> type = Pair.class;

        System.out.println(type.isRecord());
        System.out.println(type.getRecordComponents().length);
        System.out.println(type.getDeclaredConstructors().length);

        System.out.println(new Pair());
        System.out.println(new Pair(7));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordReflectionDemo.java
java RecordReflectionDemo
```

Stdout:

```text
true
2
3
Pair[left=0, right=0]
Pair[left=7, right=7]
```

Có ba constructors: canonical `Pair(int,int)`, auxiliary `Pair(int)` và auxiliary `Pair()`. Không suy ra thứ tự từ mảng phản xạ.

## 47. Compile-negative tổng hợp: 8 lỗi hay gặp

Mỗi snippet bên dưới **cố ý không biên dịch**; chúng không phải chương trình runnable.

**Lỗi A — Không gọi `this(...)`:**

```java
record R(int x) {
    R() { }
}
```

**Lỗi B — Lệnh khác đứng trước `this(...)` (Java 17):**

```java
record R(int x) {
    R() {
        System.out.println("start");
        this(0);
    }
}
```

**Lỗi C — Dùng `super()` thay `this(...)`:**

```java
record R(int x) {
    R() {
        super();
    }
}
```

**Lỗi D — Gán field trong constructor phụ, không delegate:**

```java
record R(int x) {
    R() {
        this.x = 0;
    }
}
```

**Lỗi E — Compact canonical tự gọi `this(...)`:**

```java
record R(int x) {
    R {
        this(x);
    }
}
```

**Lỗi F — Compact canonical gán component field:**

```java
record R(int x) {
    R {
        this.x = x;
    }
}
```

**Lỗi G — Canonical có throws clause:**

```java
record R(int x) {
    R(int x) throws Exception {
        this.x = x;
    }
}
```

**Lỗi H — Recursive constructor chain:**

```java
record R(int x, String s) {
    R(int x) { this("x"); }
    R(String s) { this(0); }
}
```

Cách sửa:
- A/B/C/D → làm `this(...)` là câu lệnh đầu trong additional constructor.
- E/F → bỏ explicit invocation/field assignment, xử lý implicit parameters của compact constructor.
- G → bỏ `throws` canonical, hoặc chuyển input adapter có checked error sang additional constructor/factory.
- H → đảm bảo mọi chain cuối cùng đi tới canonical với đầy đủ components.

## 48. Thứ tự đánh giá đối số trong `this(...)`

Java đánh giá constructor argument expressions từ trái sang phải. Nếu argument 1 có side effect, nó xảy ra trước argument 2, và cả hai xảy ra trước khi constructor được gọi chạy body.

Không khuyến khích lạm dụng side effects, nhưng hiểu quy tắc giúp trace log.

### Runnable

Lưu **`RecordArgumentOrderDemo.java`**:

```java
record Pair(int first, int second) {
    Pair {
        System.out.println("canonical:" + first + "," + second);
    }

    Pair() {
        this(left(), right());
        System.out.println("aux");
    }

    private static int left() {
        System.out.println("left");
        return 1;
    }

    private static int right() {
        System.out.println("right");
        return 2;
    }
}

public class RecordArgumentOrderDemo {
    public static void main(String[] args) {
        System.out.println(new Pair());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordArgumentOrderDemo.java
java RecordArgumentOrderDemo
```

Stdout:

```text
left
right
canonical:1,2
aux
Pair[first=1, second=2]
```

Constructor `Pair()` được chọn, `left()` và `right()` được evaluate để tạo parameters cho canonical theo thứ tự. Sau compact body, code phụ `aux` chạy.

## 49. Nếu một argument helper ném exception

Ví dụ:

```java
record Config(String name, int port) {
    Config() {
        this(readName(), 8080);
    }

    private static String readName() {
        throw new IllegalArgumentException("bad name");
    }
}
```

`readName()` có thể ném trước khi canonical constructor `Config(String,int)` bắt đầu. Constructor phụ cũng không chạy được bất kỳ statement nào sau lời gọi `this(...)`.

Nếu muốn checked exception, additional constructor có thể khai báo `throws` phù hợp như đã trình bày.

**Thiết kế tốt:** tránh side effects không thể rollback trong argument helpers; ưu tiên pure normalization/parsing khi có thể.

## 50. Phân biệt record constructor và overloaded static factory

Các đường tạo `Profile`:

```java
Profile a = new Profile("An", 20);      // canonical
Profile b = new Profile("An");          // auxiliary
Profile c = Profile.guest();            // factory
```

- Canonical luôn gắn với đúng component tuple.
- Auxiliary sử dụng `this(...)` và compiler kiểm tra delegation.
- Factory là static method, có thể thực hiện branching/IO/caching trước khi gọi constructor.
- Builder là một object hỗ trợ tập tùy chọn, khi build có thể gọi canonical.

Nếu factory trả về cached record instance, không phải mọi cuộc gọi factory đều tạo object mới. Điều đó khác với `new` construction semantics.

Không cố mô phỏng tên factory bằng nhiều overloaded constructors với cùng số lượng/type parameters nhưng ý nghĩa khác nhau.

## 51. Design smell: constructor overload quá mơ hồ

Giả sử:

```java
record Appointment(String location, String timezone) {
    Appointment(String value) {
        this(value, "UTC");
    }
}
```

Một chuỗi `"Asia/Ho_Chi_Minh"` được truyền vào constructor một String có nghĩa là location hay timezone? Chỉ một overload khó biểu đạt ý định.

Factory có tên rõ:

```java
record Appointment(String location, String timezone) {
    static Appointment atLocation(String location) {
        return new Appointment(location, "UTC");
    }

    static Appointment inTimezone(String timezone) {
        return new Appointment("unspecified", timezone);
    }
}
```

Đây là snippet thiết kế; việc dùng default location/timezone phải có domain meaning rõ, không tự chọn trong sản phẩm thật.

### Cách chọn

- Một default phổ biến, không gây mơ hồ → constructor overload.
- Hai conversion paths có cùng parameter type → named static factories.
- Nhiều tùy chọn tương tác → builder/config record riêng.
- Input ngoài hệ thống có parsing/IO/checked errors → factory hoặc additional constructor với contract rõ.

## 52. Test: invariant phải áp dụng cho mọi đường khởi tạo

Một số tests quan trọng:
- Canonical trực tiếp với dữ liệu hợp lệ.
- Mỗi additional overload với dữ liệu hợp lệ.
- Mỗi overload với dữ liệu bị canonical validation từ chối.
- Input normalization có áp dụng như nhau cho mọi overload không?
- Chuỗi `this(...)` có tạo correct defaults không?
- Boundary null/empty/range limits.
- Checked exceptions từ converter helpers.
- Array/list aliasing nếu record nhận mutable references.
- Value equality khi tạo hai record cùng components bằng hai cách khác nhau.
- Backward compatibility khi thêm component hoặc đổi schema.

**Không chỉ test output mặc định của một constructor**, vì bug có thể nằm trong việc một overload truyền sai tham số sang canonical.

## 53. Runnable: kiểm tra tất cả overloads với assertions không cần thư viện

Lưu **`RecordConstructorContractTestDemo.java`**:

```java
record Account(String owner, int limit, boolean enabled) {
    Account {
        if (owner == null || owner.isBlank() || limit < 0) {
            throw new IllegalArgumentException("invalid");
        }
    }

    Account(String owner, int limit) {
        this(owner, limit, true);
    }

    Account(String owner) {
        this(owner, 0);
    }
}

public class RecordConstructorContractTestDemo {
    public static void main(String[] args) {
        Account one = new Account("An");
        Account two = new Account("An", 0);
        Account three = new Account("An", 0, true);

        require(one.equals(two));
        require(two.equals(three));
        require(one.enabled());

        try {
            new Account("An", -1);
            throw new AssertionError("expected exception");
        } catch (IllegalArgumentException expected) {
            require(expected.getMessage().equals("invalid"));
        }

        System.out.println("CONTRACT_PASS");
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("contract failed");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordConstructorContractTestDemo.java
java RecordConstructorContractTestDemo
```

Stdout:

```text
CONTRACT_PASS
```

Test kiểm chứng các overloads tạo cùng record value khi truyền cùng effective components, đồng thời canonical validation vẫn áp dụng khi gọi overload hai tham số.

## 54. Bài tập 1 — Xác định canonical

```java
record Person(String name, int age) {
    Person(String name) {
        this(name, 0);
    }
}
```

**Câu hỏi:** constructor nào là canonical?

**Đáp án:** `Person(String,int)` là canonical ngầm định từ record header. `Person(String)` là additional constructor.

## 55. Bài tập 2 — Có cần ghi canonical tường minh?

Nếu record chỉ khai báo `Person(String name) { this(name,0); }` mà không viết `Person(String,int)`, chương trình biên dịch không?

**Đáp án:** Có. Java ngầm sinh canonical constructor vì chưa có explicit normal/compact canonical.

## 56. Bài tập 3 — Vị trí `this(...)`

```java
record Port(int value, String protocol) {
    Port(int value) {
        System.out.println("creating");
        this(value, "tcp");
    }
}
```

**Đáp án:** Không compile trên Java 17. `this(...)` phải là câu lệnh đầu của non-canonical constructor.

## 57. Bài tập 4 — Lệnh sau `this(...)` có hợp lệ?

```java
record Pair(int x, int y) {
    Pair(int x) {
        this(x, 0);
        System.out.println("constructed");
    }
}
```

**Đáp án:** Hợp lệ. Constructor phụ được thực thi tiếp **sau khi** lời gọi canonical `this(x,0)` hoàn thành.

## 58. Bài tập 5 — Chuỗi nhiều overloads

`Point()` gọi `Point(int)`, `Point(int)` gọi `Point(int,int)`. Hợp lệ không?

**Đáp án:** Có, nếu các signatures phù hợp và không có recursion. Cuối cùng `Point(int,int)` là canonical.

## 59. Bài tập 6 — Constructor phụ tự gán field

```java
record Pair(int a, int b) {
    Pair(int a) {
        this.a = a;
        this.b = 0;
    }
}
```

**Đáp án:** Không hợp lệ. Additional constructor phải bắt đầu `this(a,0)`, không tự khởi tạo fields.

## 60. Bài tập 7 — Compact canonical có parameters không?

```java
record User(String name) {
    User {
        name = name.trim();
    }
}
```

**Đáp án:** Compact canonical có implicit parameter `name` từ record header; body không viết lại parameter list.

## 61. Bài tập 8 — Compact assignment

`this.name = name.trim();` trong compact constructor có hợp lệ?

**Đáp án:** Không. Gán implicit parameter `name = name.trim();`; compiler sẽ gán component field khi compact body kết thúc.

## 62. Bài tập 9 — Compact `this(...)`

```java
record User(String name) {
    User {
        this(name);
    }
}
```

**Đáp án:** Không hợp lệ. Compact đã là canonical constructor, không gọi explicit constructor invocation.

## 63. Bài tập 10 — Normal canonical phải tự gán fields?

```java
record User(String name) {
    User(String name) {
        // Không gán this.name.
    }
}
```

**Đáp án:** Không hợp lệ vì component field final chưa được definitely assigned trong normal canonical. Dạng compact có assignment ngầm, normal canonical thì bạn phải gán đầy đủ.

## 64. Bài tập 11 — Đổi tên parameter của normal canonical

`record User(String name,int age) { User(String n,int age){...} }` có được coi là constructor phụ khác không?

**Đáp án:** Không. Signature theo types khớp canonical, nên parameter names phải khớp các record components (`name`, `age`). Đây là lỗi khai báo normal canonical.

## 65. Bài tập 12 — Canonical có `throws`?

Một normal canonical constructor khai báo `throws IOException`. Có hợp lệ không?

**Đáp án:** Không trên Java 17. Canonical constructor không được khai báo throws clause. Đặt IO parsing ở additional constructor/factory.

## 66. Bài tập 13 — Additional `throws`?

`Record(Path path) throws IOException { this(Files.readString(path)); }` với record header một String component. Có thể hợp lệ không?

**Đáp án:** Có, khi imports/overloads đúng. Additional constructor có thể khai báo checked throws và chuyển data qua canonical.

## 67. Bài tập 14 — Private additional constructor

Public record có thể có private convenience overload không?

**Đáp án:** Có, vì accessibility rule “không hẹp hơn record” áp cho canonical constructor, không bắt mọi non-canonical constructor public. Factory trong record có thể gọi private overload.

## 68. Bài tập 15 — Private canonical của public record

`public record User(String name) { private User { } }` hợp lệ không?

**Đáp án:** Không. Public record cần explicit canonical constructor public.

## 69. Bài tập 16 — Recursive invocation

Constructor `A()` gọi `A(int)` và `A(int)` gọi `A()`. Hợp lệ không?

**Đáp án:** Không. Recursive constructor invocation không có đường tới canonical.

## 70. Bài tập 17 — Generic record

`record Box<T>(T value,String label)` với additional `Box(T value){this(value,"default");}`. Một `Box<String>` có dùng `new Box<>("A")` được không?

**Đáp án:** Có trong Java 17 theo type inference phù hợp.

## 71. Bài tập 18 — Zero-component record

`record Marker()` có canonical signature gì?

**Đáp án:** `Marker()`. Additional overload phải có khác parameter types/list, ví dụ `Marker(String) { this(); }`.

## 72. Bài tập 19 — Varargs và constructor recursion

`record Tags(String... values) { Tags() { this(); } }` có hợp lệ không?

**Đáp án:** Không. `this()` ở `Tags()` tự gọi lại constructor no-arg, gây recursion. Dùng `this(new String[0])` để chọn canonical varargs với một array.

## 73. Bài tập 20 — Hai cách tạo cùng value

`new Item("A")` và `new Item("A",1)` khi overload một tham số gọi `this("A",1)`. `equals` và `==` thế nào?

**Đáp án:** Mặc định record equality theo components nên `equals` true, `==` false cho hai `new` khác nhau.

## 74. Bài tập 21 — Constructor overload cho optional config

Record có 12 optional parameters, tạo 20 constructors. Có tốt không?

**Đáp án:** Thường là dấu hiệu API quá phức tạp. Cân nhắc named factories, builder hoặc cấu trúc config hợp lý để giảm overload ambiguity và duy trì invariant rõ.

## 75. Bài tập 22 — Tham số mutable array

Constructor phụ nhận `String[]` và chuyển tới canonical nhưng canonical không copy. Record đã immutable chưa?

**Đáp án:** Chưa chắc. Final component field giữ array reference, array vẫn mutable. Canonical cần defensive copy nếu contract value snapshot; accessor cần xem lại exposure.

## 76. Bài tập 23 — Validation ở đâu?

Record có ba constructors phụ và canonical. Một `age >= 0` invariant nên viết ở đâu?

**Đáp án:** Tại canonical constructor (compact hoặc normal). Mọi additional constructor delegate qua đó, tránh việc chỉ một đường được validate.

## 77. Bài tập 24 — Thứ tự log

`R() { this(1); print("A"); }`, `R(int) { this(1,2); print("B"); }`, canonical in `C`. Output khi `new R()`?

**Đáp án:** `C`, rồi `B`, rồi `A` (mỗi dòng nếu print println). Chain vào canonical trước rồi unwind ngược.

## 78. Bài tập 25 — Thêm record component mới

`record User(String name)` có auxiliary `User(){this("Guest");}`. Thêm component `int age` vào header. Cần kiểm tra gì?

**Đáp án:** Canonical signature đổi thành `User(String,int)`. `this("Guest")` có thể trở thành recursive call vào constructor một String nếu constructor ấy tự tồn tại, hoặc không resolve/không compile; cập nhật delegation và default cho age, rồi test external schema/API compatibility.

## 79. Bài tập 26 — Reflection

`getDeclaredConstructors()` trả cả canonical và additional constructors không?

**Đáp án:** Có đối với record khai báo đó, kể cả constructors không public; thứ tự mảng không được dùng để suy ra canonical. Xác định canonical qua component-derived signature.

## 80. Bài tập 27 — Default values

Java record header `record Item(int qty=1)` có hợp lệ không?

**Đáp án:** Không. Java không khai báo default parameter trực tiếp trong record header. Dùng additional constructor `Item() { this(1); }` hoặc factory có tên.

## 81. Bài tập 28 — Canonical normal hay compact?

Bạn muốn strip String và validate range, không cần manual field assignment. Nên ưu tiên gì?

**Đáp án:** Compact canonical thường rõ hơn: chỉnh implicit parameters, ném exception khi không hợp lệ, để compiler gán fields sau body.

## 82. Bài tập 29 — Argument side effect

`this(left(),right());` trong constructor phụ: method nào chạy trước?

**Đáp án:** Java đánh giá argument expressions từ trái sang phải: left() trước right(), rồi mới vào constructor được gọi nếu không exception.

## 83. Bài tập 30 — Câu hỏi tổng hợp

Trong Java 17, đánh dấu Đúng/Sai:

1. Một record luôn có canonical constructor.
2. Một non-canonical constructor có thể bỏ `this(...)` nếu tự gán đủ fields.
3. Additional constructor có thể gọi another additional constructor.
4. Compact constructor cũng là canonical constructor.
5. Compact constructor có thể gọi `this(...)`.
6. Normal canonical có thể khai báo `throws IOException`.
7. Private additional constructor là hợp lệ khi record public.
8. Constructor overload có thể bypass validation ở canonical.
9. `new RecordType(...)` qua hai overloads có thể tạo hai objects bằng nhau theo `equals`.
10. Compiler cho phép constructor chaining tạo cycle A→B→A.

**Đáp án:** 1 đúng; 2 sai; 3 đúng; 4 đúng; 5 sai; 6 sai; 7 đúng; 8 sai; 9 đúng; 10 sai.

## 84. Bảng lỗi thường gặp và cách sửa

| Lỗi hoặc nhận định sai | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `record R(int x) { R() {} }` | Thiếu `this(...)` trong constructor phụ | `R(){this(0);}` |
| In log trước `this(...)` | `this(...)` không đứng đầu theo Java17 | Dời log sau invocation, hoặc pure helper trong arguments |
| `super()` trong auxiliary record constructor | Phải delegate cùng record | Dùng `this(...)` |
| Gán `this.x=...` ở constructor phụ | Bỏ qua canonical path | Chuyển tất cả component arguments tới canonical |
| Compact gán `this.x` | Compact fields gán ngầm từ parameters | Gán parameter `x` |
| Compact gọi `this(...)` | Compact đã là canonical | Bỏ explicit invocation |
| Hai canonical normal+compact | Signature duplicate | Chỉ giữ một canonical |
| Explicit canonical thiếu field assignment | Fields final chưa được khởi tạo | Gán đầy đủ trong normal canonical hoặc dùng compact |
| Canonical parameter name khác component | Vi phạm JLS normal canonical rules | Khớp names/types với header |
| Public record nhưng canonical private | Access hẹp hơn record | Public canonical |
| Canonical có `throws` | JLS cấm throws clause ở canonical | Validation unchecked; checked IO ở auxiliary/factory |
| Delegation A→B→A | Constructor recursion | Mọi chain tới canonical |
| `new Tags()` trong `Tags()` gọi `this()` | Chính overload no-arg tự gọi lại | `this(new String[0])` |
| Overload chọn sai do `null` | Có nhiều reference-type constructors | Explicit cast hoặc named factory |
| Copy validation ở mọi constructor | Lặp logic và nguy cơ lệch invariant | Validation trong canonical |
| Mutate component array từ caller | Không defensive copy | Copy trong canonical và accessor |
| Constructor quá nhiều combinations | API khó hiểu | Builder/named factories |
| Test chỉ một constructor | Bỏ sót path khác | Contract tests mọi overload |
| Tưởng `this(...)` tạo object thứ hai | Hiểu sai chaining | Một `new`, một object, nhiều ctor bodies |
| Dùng default parameter trong record header | Java syntax không hỗ trợ | Auxiliary constructor/factory |

## 85. Checklist khi thiết kế constructor bổ sung cho record

- [ ] Record header mô tả đầy đủ state/các components.
- [ ] Đã xác định canonical signature theo thứ tự component types.
- [ ] Đã chọn canonical implicit, normal hoặc compact (chỉ một).
- [ ] Nếu normal canonical, parameter names/types trùng header.
- [ ] Nếu normal canonical, mọi component fields được gán đúng một lần.
- [ ] Nếu compact canonical, dùng implicit parameters để normalize.
- [ ] Compact body không `return`/`this(...)`/gán component fields.
- [ ] Explicit canonical không khai báo `throws`.
- [ ] Canonical access không hẹp hơn record.
- [ ] Mỗi additional constructor có signature khác canonical.
- [ ] Mỗi additional constructor bắt đầu `this(...)` trong Java 17.
- [ ] Không có statement/log/assignment trước `this(...)`.
- [ ] Không dùng `super(...)` thay `this(...)`.
- [ ] Mọi constructor chain không có chu kỳ và cuối cùng tới canonical.
- [ ] Những giá trị default có ý nghĩa domain rõ ràng.
- [ ] Các helper tính arguments không phụ thuộc instance fields chưa khởi tạo.
- [ ] Validation state invariant tập trung ở canonical.
- [ ] Validation input-format-specific nằm trong helper/adapter phù hợp.
- [ ] Overload resolution và `null` không mơ hồ.
- [ ] Nếu có checked exception từ input, auxiliary/factory có contract rõ.
- [ ] Nếu record generic, type inference và erasure được kiểm tra.
- [ ] Nếu record có varargs, `this(new T[0])` tránh self-recursion.
- [ ] Nếu components mutable, defensive copy policy đồng nhất mọi paths.
- [ ] Các factories có tên thay thế overloads khi làm API sáng nghĩa.
- [ ] Không cần “constructor-private mode” ẩn ngoài record components.
- [ ] Reflection/serialization/framework expectations được test khi liên quan.
- [ ] Có compile với đúng `--release 17`, không vô tình dựa vào language features mới.
- [ ] Các ví dụ compile-negative được tách khỏi runnable source files.
- [ ] Tests bao phủ canonical và từng auxiliary path.
- [ ] Tests xác minh normalization, validation, defaults và equality.
- [ ] Khi thêm record component, đã cập nhật mọi constructor delegates.
- [ ] Public API/serialization compatibility đã được đánh giá khi record schema đổi.

## 86. Tóm tắt cốt lõi

**Mỗi record có một canonical constructor** được dẫn xuất từ record components. Canonical có thể do compiler sinh, được viết normal với đầy đủ parameters, hoặc được viết **compact** để validate/normalize ngắn gọn.

**Mọi constructor bổ sung của record trong Java 17 phải bắt đầu bằng `this(...)`**. Constructor đó có thể gọi một overload khác, nhưng chuỗi phải kết thúc ở canonical. Không được tự gán component fields, đặt log trước `this(...)`, thay bằng `super()` hoặc tạo vòng lặp constructor.

Đặt **invariant validation tại canonical**, dùng constructors bổ sung cho input adapters và defaults, cân nhắc named factories khi overload có thể gây nhầm. Với component mutable, canonical là nơi phù hợp để thống nhất defensive-copy policy.

**Cách nhớ ngắn:** Record cho phép nhiều **đường vào**, nhưng chỉ một **cửa chuẩn để khởi tạo state**. Các constructor phụ chỉ đưa dữ liệu đến cửa đó; chúng không xây state theo đường riêng.

## Tài liệu Java SE 17 chính thức

- **JLS `8.10.4 — Record Constructor Declarations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4
- **JLS `8.10.4.1 — Normal Canonical Constructors**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.1
- **JLS `8.10.4.2 — Compact Canonical Constructors**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.2
- **JLS `8.8.7.1 — Explicit Constructor Invocations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1
- **`java.lang.Record` API (Java 17)**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html
