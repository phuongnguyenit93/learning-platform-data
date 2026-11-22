# Khai báo hằng enum và danh tính của từng hằng trong Java 17

Trong Java, **`enum`** là một kiểu dữ liệu tham chiếu đặc biệt dùng để mô hình hóa một **tập hữu hạn các giá trị được đặt tên**. Mỗi giá trị được khai báo trong danh sách hằng enum là **một đối tượng riêng biệt** thuộc enum type đó; object ấy có **danh tính (identity)** riêng và được JVM khởi tạo theo quy tắc của kiểu enum.

Ví dụ:

```java
enum TrafficLight {
    RED, YELLOW, GREEN
}
```

Ở đây:
- `TrafficLight` là **một enum type**, không phải ba biến kiểu `String`.
- `TrafficLight.RED`, `TrafficLight.YELLOW`, `TrafficLight.GREEN` là **ba enum constants**, mỗi hằng biểu diễn một enum instance khác nhau.
- `TrafficLight.RED == TrafficLight.RED` là `true` vì cùng một enum constant reference.
- `TrafficLight.RED == TrafficLight.GREEN` là `false` vì là hai constants khác danh tính.
- `TrafficLight.RED.name()` là `"RED"`, tên khai báo của hằng; `name()` không phải chính enum object.
- `TrafficLight.RED.ordinal()` là `0` do RED được khai báo đầu tiên; **ordinal không phải định danh nghiệp vụ ổn định**.

Một câu tóm lược rất quan trọng:

> **Enum constant có identity bằng chính object reference của hằng, còn tên và vị trí khai báo là các thuộc tính của hằng, không phải object identity.**

Bài học thuộc Java Core — Class/Object, dành cho **Java 17+**. Nội dung bao gồm cú pháp khai báo hằng, constructors và fields, identity/`==`/`equals`, `name()`/`ordinal()`/`toString()`, `values()`/`valueOf()`, thứ tự khởi tạo, constant-specific class bodies, interface, `switch`, `EnumSet`/`EnumMap`, serialization/reflection, nested/local enum, concurrency, thiết kế mã định danh nghiệp vụ, lỗi phổ biến, ví dụ chạy được và bài tập có đáp án.

## 1. Vì sao cần enum thay cho String hay int?

Giả sử trạng thái đơn hàng được lưu bằng String:

```java
String status = "PAID";
```

Một method nhận String có thể bị truyền nhầm `"PAYD"`, `"paid"` hoặc `"UNKNOWN"`. Compiler không ngăn được những lỗi tên ấy.

Với enum:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

OrderStatus status = OrderStatus.PAID;
```

Trình biên dịch biết `status` phải là `OrderStatus`, không phải String tùy ý. Muốn thêm trạng thái, developer cập nhật chính declaration của enum.

Các lợi ích:
- Type safety: các constants chỉ thuộc kiểu khai báo.
- Tên rõ ràng, có autocomplete và refactoring support.
- So sánh identity bằng `==` an toàn trong những tình huống thông thường.
- `switch` có thể biểu diễn hành vi theo từng constant.
- Có thể khai báo fields, methods, constructors và implement interfaces.
- JDK có collections tối ưu cho enum như `EnumSet` và `EnumMap`.

**Không phải dữ liệu hữu hạn nào cũng nên dùng enum.** Nếu các giá trị do người dùng cấu hình, liên tục bổ sung hoặc có lifecycle động từ database, một registry/domain entity có thể hợp lý hơn.

## 2. Cú pháp tối thiểu của một enum

```java
enum Day {
    MONDAY,
    TUESDAY,
    WEDNESDAY,
    THURSDAY,
    FRIDAY,
    SATURDAY,
    SUNDAY
}
```

Các identifier giữa `{` và `}` được ngăn cách bởi dấu phẩy. Mỗi identifier là tên của **enum constant**.

Viết reference:

```java
Day today = Day.MONDAY;
```

Không khai báo enum constants như static fields thủ công:

```java
// Không phải cú pháp enum:
enum Day {
    // public static final Day MONDAY = new Day();
}
```

Trong phần enum constant list, cú pháp `MONDAY` đã được Java xử lý đặc biệt. Các constants được cung cấp như các **public static final fields** của enum type theo semantics của ngôn ngữ; developer không tự viết `new Day()` để tạo hằng.

### Dấu `;` khi có members

Nếu chỉ có hằng, có thể không cần dấu chấm phẩy:

```java
enum Color {
    RED, BLUE
}
```

Nếu sau danh sách hằng còn có fields, constructors, methods, hãy kết thúc constant list bằng `;`:

```java
enum Color {
    RED, BLUE;

    String describe() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
```

### Danh sách hằng phải xuất hiện trước các members thông thường

Không đặt một method declaration trước `RED` và `BLUE`. Enum constant declarations là phần đặc biệt ở đầu enum body.

## 3. Runnable: khai báo và sử dụng các hằng đầu tiên

Lưu **`BasicEnumDemo.java`**:

```java
enum Direction {
    NORTH, EAST, SOUTH, WEST
}

public class BasicEnumDemo {
    public static void main(String[] args) {
        Direction current = Direction.NORTH;

        System.out.println(current);
        System.out.println(current == Direction.NORTH);
        System.out.println(current == Direction.SOUTH);
        System.out.println(Direction.WEST.name());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BasicEnumDemo.java
java BasicEnumDemo
```

**Stdout chính xác:**

```text
NORTH
true
false
WEST
```

`System.out.println(current)` gọi `toString()`; nếu enum không override, `Enum.toString()` mặc định trả tên hằng giống `name()`. Đó không có nghĩa enum là String.

## 4. Enum là một reference type, không phải primitive

`Direction` là một enum type và thuộc hệ thống kiểu tham chiếu của Java. Một biến `Direction` chứa reference đến một trong các enum constants, hoặc `null`.

Ví dụ:

```java
Direction a = Direction.NORTH;
Direction b = a;
```

`b = a` **không clone hay tạo một NORTH mới**; hai references trỏ đúng cùng object constant.

`a == b` là true.

Một biến enum vẫn có thể null:

```java
Direction unknown = null;
System.out.println(unknown == Direction.NORTH); // false
```

Nhưng:

```java
// unknown.name(); // NullPointerException khi chạy.
```

**Enum không tự loại bỏ null khỏi mọi API.** Muốn field luôn non-null, kiểm tra invariant ở constructor, setter hoặc boundary nhập dữ liệu. `Objects.requireNonNull` có thể giúp biểu đạt contract.

## 5. Danh tính của một enum constant

Trong phạm vi một enum class được tải và khởi tạo trong một Java runtime, mỗi hằng được biểu diễn bởi một **instance canonical** do cơ chế enum cung cấp.

Từ một reference đến `Direction.NORTH`, bất kỳ chỗ nào truy cập cùng hằng của cùng enum type ấy đều nhận cùng reference identity.

```java
Direction first = Direction.NORTH;
Direction second = Direction.valueOf("NORTH");

System.out.println(first == second); // true
```

Đừng hiểu “mỗi hằng chỉ có một instance” thành “chỉ có một object enum trên toàn thế giới”. Có **một object cho mỗi declared constant trong enum class tương ứng**. Các constants khác tên có objects khác nhau. Những chi tiết như class-loader identity cũng có thể ảnh hưởng cách một Java type được xác định giữa các loader/runtime khác nhau.

### Identity khác value equality thông thường

Với class `Person`, hai objects có fields bằng nhau vẫn có thể khác references:

```java
new Person("A") != new Person("A")
```

Với enum, developer không thể tạo tùy tiện một `Direction.NORTH` object thứ hai bằng constructor. Vì thế comparison theo reference identity phù hợp với chính **tập constant instances** do enum khai báo.

## 6. Runnable: ba biến nhưng chỉ hai hằng

Lưu **`EnumIdentityDemo.java`**:

```java
enum AccessLevel {
    GUEST, ADMIN
}

public class EnumIdentityDemo {
    public static void main(String[] args) {
        AccessLevel one = AccessLevel.ADMIN;
        AccessLevel two = AccessLevel.ADMIN;
        AccessLevel three = AccessLevel.GUEST;

        System.out.println(one == two);
        System.out.println(one == three);
        System.out.println(two.equals(one));
        System.out.println(one.getClass() == AccessLevel.class);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumIdentityDemo.java
java EnumIdentityDemo
```

Stdout:

```text
true
false
true
true
```

Trong ví dụ không có constant-specific class body nên runtime class của ADMIN chính là `AccessLevel.class`. Ở phần sau, khi mỗi constant có body riêng, cần dùng `getDeclaringClass()` nếu mục tiêu là xác định **enum type** của constant.

## 7. Dùng `==` hay `equals()` cho enum?

**Khuyến nghị:** so sánh hai enum constants cùng type bằng `==` hoặc `!=`:

```java
if (status == OrderStatus.PAID) {
    // ...
}
```

Lý do:
- Các enum constants có canonical identity.
- `Enum.equals(Object)` là final và dựa trên reference identity.
- `==` không ném `NullPointerException` khi một toán hạng là null.
- Compiler kiểm tra tính tương thích của kiểu tham chiếu trong so sánh.

`status.equals(OrderStatus.PAID)` cũng cho kết quả đúng khi status không null, nhưng nhận thêm nguy cơ NPE nếu status null.

**Đừng dùng `==` để so sánh Strings**. Hai String objects có thể cùng nội dung nhưng khác references; enum khác bởi bộ hằng được quản lý bởi cơ chế enum.

### Có thể override `equals` hoặc `hashCode` của enum không?

Không. `java.lang.Enum` định nghĩa `equals` và `hashCode` là final. Bạn không được thay identity semantics của enum bằng một equality policy theo fields.

Nếu bài toán cần hai đối tượng có cùng mã nghiệp vụ được coi là bằng nhau bất kể tạo lúc nào, có thể một immutable record/value object sẽ phù hợp hơn enum.

## 8. Runnable: `==`, `equals` và null

Lưu **`EnumComparisonDemo.java`**:

```java
enum State {
    OPEN, CLOSED
}

public class EnumComparisonDemo {
    public static void main(String[] args) {
        State state = State.OPEN;
        State missing = null;

        System.out.println(state == State.OPEN);
        System.out.println(state.equals(State.OPEN));
        System.out.println(state == State.CLOSED);
        System.out.println(missing == State.OPEN);
        System.out.println(State.OPEN.equals(missing));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumComparisonDemo.java
java EnumComparisonDemo
```

Stdout:

```text
true
true
false
false
false
```

Trong source này không gọi `missing.equals(...)`, vì hành vi đó là NullPointerException, không phải false.

## 9. Hai enum types có constant cùng tên vẫn khác nhau

```java
enum OrderState {
    OPEN, CLOSED
}

enum TicketState {
    OPEN, CLOSED
}
```

`OrderState.OPEN` và `TicketState.OPEN` đều có tên `"OPEN"` nhưng thuộc **hai enum types độc lập**.

Điều này có nghĩa:
- Không thể gán `TicketState.OPEN` cho biến `OrderState`.
- Không được so sánh trực tiếp bằng `==` khi hai operand types hoàn toàn không thể convert hợp lệ để thực hiện reference equality theo type rules.
- `OrderState.OPEN.equals(TicketState.OPEN)` hợp lệ do `equals(Object)` nhận Object, nhưng trả **false**.
- `name()` giống nhau không làm hai constants trở thành một identity.

### Runnable

Lưu **`SameNameDifferentEnumsDemo.java`**:

```java
enum OrderState {
    OPEN, CLOSED
}

enum TicketState {
    OPEN, CLOSED
}

public class SameNameDifferentEnumsDemo {
    public static void main(String[] args) {
        System.out.println(OrderState.OPEN.name());
        System.out.println(TicketState.OPEN.name());
        System.out.println(
                OrderState.OPEN.equals(TicketState.OPEN));
        System.out.println(
                OrderState.OPEN.getDeclaringClass()
                == TicketState.OPEN.getDeclaringClass());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SameNameDifferentEnumsDemo.java
java SameNameDifferentEnumsDemo
```

Stdout:

```text
OPEN
OPEN
false
false
```

Enum type cũng là một phần không thể bỏ qua của danh tính hằng, ngay cả khi nhãn hiển thị giống nhau.

## 10. `name()`: tên khai báo của constant

Mỗi enum constant có tên được công bố bởi final method `name()`:

```java
Direction.NORTH.name() // "NORTH"
```

Tên này là **identifier chính xác được dùng trong khai báo nguồn**. Đây là cách máy đọc hằng theo tên, nhưng cũng tạo rủi ro nếu tên được lưu làm identifier ngoài hệ thống rồi sau đó developer đổi tên source constant.

Đặc điểm:
- `name()` trả String, không trả enum object.
- Không override được `name()`: nó final.
- Nếu rename hằng từ `PAID` thành `SETTLED`, `name()` thay đổi; persisted data cũ cần migration/mapping.
- `name()` thường phù hợp cho các thao tác muốn định danh theo khai báo hiện hành.
- Không nên mặc định dùng `name()` làm nhãn UI đa ngôn ngữ.

### `name()` khác `toString()`

`toString()` mặc định của enum trả tên hằng, nhưng có thể **override** để tạo nhãn thân thiện với người đọc. `name()` không override được.

## 11. `ordinal()`: vị trí khai báo, không phải mã ID

`ordinal()` là method final trả vị trí zero-based của constant theo thứ tự khai báo.

```java
enum Size {
    SMALL, MEDIUM, LARGE
}
```

Giá trị:
- `SMALL.ordinal() == 0`.
- `MEDIUM.ordinal() == 1`.
- `LARGE.ordinal() == 2`.

Cảnh báo quan trọng:

> **Không dùng ordinal làm mã cơ sở dữ liệu, public API code hoặc protocol field ổn định.**

Chèn một hằng mới lên đầu enum sẽ đổi ordinal của các hằng phía sau. Thứ tự khai báo thường phản ánh thứ tự tự nhiên của enumeration, không phải stable business key.

Nếu cần mã bền vững, định nghĩa field riêng được chọn rõ ràng.

## 12. Runnable: `name` và `ordinal`

Lưu **`EnumNameOrdinalDemo.java`**:

```java
enum Priority {
    LOW, NORMAL, HIGH
}

public class EnumNameOrdinalDemo {
    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(priority.name()
                    + ":" + priority.ordinal());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumNameOrdinalDemo.java
java EnumNameOrdinalDemo
```

Stdout:

```text
LOW:0
NORMAL:1
HIGH:2
```

Nếu đổi thứ tự khai báo enum, output ordinal đổi theo. `ordinal()` có công dụng đặc biệt trong các cơ chế dựa vào thứ tự/tối ưu như `EnumSet`/`EnumMap`, nhưng ứng dụng không nên mặc định biến nó thành business identity.

## 13. `toString()` có thể là tên trình bày, không phải tên nguồn

Bạn có thể viết:

```java
enum PaymentStatus {
    PENDING, SUCCESS;

    @Override
    public String toString() {
        return switch (this) {
            case PENDING -> "Đang chờ";
            case SUCCESS -> "Thành công";
        };
    }
}
```

`PaymentStatus.SUCCESS.name()` vẫn là `"SUCCESS"`; `toString()` cho kết quả `"Thành công"`.

**Đừng phụ thuộc `toString()` làm serialization ID** nếu mục tiêu của nó là UI label; sau này đổi ngôn ngữ, copywriting hoặc format sẽ phá compatibility.

### Runnable

Lưu **`EnumStringDemo.java`**:

```java
enum ResultStatus {
    OK, FAIL;

    @Override
    public String toString() {
        return this == OK ? "Thành công" : "Thất bại";
    }
}

public class EnumStringDemo {
    public static void main(String[] args) {
        ResultStatus value = ResultStatus.OK;

        System.out.println(value.name());
        System.out.println(value.toString());
        System.out.println(value == ResultStatus.OK);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumStringDemo.java
java EnumStringDemo
```

Stdout:

```text
OK
Thành công
true
```

Identity không phụ thuộc nội dung `toString()`. Đổi label `"Thành công"` thành `"Hoàn tất"` vẫn không tạo object constant mới.

## 14. `values()`: lấy tất cả hằng theo thứ tự khai báo

Đối với enum `Color`, compiler cung cấp method `Color.values()` trả mảng chứa các enum constants theo thứ tự declaration.

```java
Color[] all = Color.values();
```

Các điểm cần nhớ:
- Đây là một **mảng mới** cho mỗi lần gọi theo API contract.
- Các phần tử trong mảng là **references tới các canonical enum constant objects**, không phải deep copies.
- Thứ tự elements là declaration order.
- Sửa phần tử mảng mà bạn nhận **không sửa danh sách enum constants** của type.
- Mảng có thể chứa tất cả constants dù không hề có logic tạo mới từng hằng lúc gọi `values()`.

### Phân biệt hai thứ identity

```java
Color[] a = Color.values();
Color[] b = Color.values();
```

`a == b` là false vì hai array objects khác nhau. Nhưng `a[0] == b[0]` là true khi cả hai chứa constant đầu tiên.

**Mảng mới không đồng nghĩa các enum constants mới.**

## 15. Runnable: mảng mới, constant cũ

Lưu **`EnumValuesIdentityDemo.java`**:

```java
enum Color {
    RED, GREEN, BLUE
}

public class EnumValuesIdentityDemo {
    public static void main(String[] args) {
        Color[] one = Color.values();
        Color[] two = Color.values();

        System.out.println(one == two);
        System.out.println(one[0] == two[0]);

        one[0] = Color.BLUE;

        System.out.println(two[0]);
        System.out.println(Color.values()[0]);
        System.out.println(Color.values().length);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumValuesIdentityDemo.java
java EnumValuesIdentityDemo
```

Stdout:

```text
false
true
RED
RED
3
```

Việc gán `one[0] = Color.BLUE` chỉ thay reference trong array `one`. Hằng `Color.RED` vẫn tồn tại, và những lần gọi `values()` khác vẫn trả lại danh sách ban đầu.

## 16. `valueOf(String)`: ánh xạ tên hằng sang object identity

Với enum `Color`:

```java
Color red = Color.valueOf("RED");
```

Compiler sinh method `Color.valueOf(String)` để tìm hằng có **tên khai báo đúng**. Giá trị trả về là **chính canonical constant**, không phải bản sao.

`Color.valueOf("RED") == Color.RED` là true.

Lỗi cần biết:
- Tên không khớp, ví dụ `"red"`: `IllegalArgumentException`.
- Chuỗi `null`: `NullPointerException`.
- Tên hằng phân biệt chữ hoa/thường.
- `valueOf` không tìm theo `toString()`; nhãn UI không đồng nghĩa enum name.
- Nếu dữ liệu bên ngoài không đáng tin, cần validate/handle errors.

Bạn cũng có overload generic `Enum.valueOf(Color.class, "RED")`, hữu ích khi enum type là một `Class<T>` được truyền vào generic API.

## 17. Runnable: `valueOf` giữ identity và xử lý lỗi

Lưu **`EnumValueOfDemo.java`**:

```java
enum Channel {
    EMAIL, SMS
}

public class EnumValueOfDemo {
    public static void main(String[] args) {
        Channel fromName = Channel.valueOf("EMAIL");
        Channel generic = Enum.valueOf(
                Channel.class, "SMS");

        System.out.println(fromName == Channel.EMAIL);
        System.out.println(generic == Channel.SMS);

        try {
            Channel.valueOf("email");
        } catch (IllegalArgumentException error) {
            System.out.println("invalid-name");
        }

        try {
            Channel.valueOf(null);
        } catch (NullPointerException error) {
            System.out.println("null-name");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumValueOfDemo.java
java EnumValueOfDemo
```

Stdout:

```text
true
true
invalid-name
null-name
```

Không in trực tiếp exception message vì text của message không phải contract phù hợp cho stdout cố định trong bài này; chúng ta chỉ kiểm tra exception types.

## 18. Constructor và dữ liệu riêng của từng enum constant

Enum không bị giới hạn ở constants không tham số. Bạn có thể cấp đối số cho constructor của enum ngay trong constant declaration:

```java
enum HttpStatus {
    OK(200),
    NOT_FOUND(404);

    private final int code;

    HttpStatus(int code) {
        this.code = code;
    }

    int code() {
        return code;
    }
}
```

Mỗi hằng là **một enum object riêng** có `code` được khởi tạo khác nhau. Tên `OK` và `NOT_FOUND` vẫn là enum identities; field `code` là **dữ liệu đi kèm**.

### Constructor của enum có đặc biệt gì?

- Không được tự ý tạo instance bằng `new HttpStatus(200)` từ application source.
- Constructors của enum có access bị giới hạn: có thể viết `private` hoặc bỏ modifier; không được public/protected.
- Chỉ enum constants ở phần đầu enum declaration sử dụng các constructor này trong quá trình tạo constants.
- Nếu không khai báo constructor, Java cung cấp constructor phù hợp theo quy tắc enum.
- Constructors có thể overload.
- Nếu enum constant mang argument list `(…)`, compiler chọn matching constructor.
- Enum constructor không thể dùng để tạo một bộ vô hạn các “instances mới” như constructor class bình thường.

**Ranh giới:** ngoài source declaration, người dùng làm việc với những constant objects có sẵn.

## 19. Runnable: enum constants mang thuộc tính và code ổn định

Lưu **`EnumConstructorDemo.java`**:

```java
enum HttpStatus {
    OK(200, "Thành công"),
    BAD_REQUEST(400, "Yêu cầu không hợp lệ"),
    NOT_FOUND(404, "Không tìm thấy");

    private final int code;
    private final String message;

    HttpStatus(int code, String message) {
        this.code = code;
        this.message = message;
    }

    int code() {
        return code;
    }

    String message() {
        return message;
    }
}

public class EnumConstructorDemo {
    public static void main(String[] args) {
        HttpStatus status = HttpStatus.NOT_FOUND;

        System.out.println(status.name());
        System.out.println(status.code());
        System.out.println(status.message());
        System.out.println(status == HttpStatus.NOT_FOUND);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumConstructorDemo.java
java EnumConstructorDemo
```

Stdout:

```text
NOT_FOUND
404
Không tìm thấy
true
```

`code=404` là mã domain/HTTP của hằng NOT_FOUND; `ordinal()` của NOT_FOUND là 2 trong source hiện tại. **404 và 2 không được trộn lẫn.**

### Nên dùng final fields?

Nếu field là state mô tả hằng, `private final` giúp mọi object constant có attributes được gán trong constructor và không bị code tùy ý gán lại. Nhưng một final reference tới object mutable vẫn có thể trỏ một referent mutable; cần defensive copy khi cần.

## 20. Hằng có cùng field value vẫn khác identity

Hai constants khác tên vẫn là hai instances khác nhau, ngay cả khi constructor arguments trùng:

```java
enum AliasCode {
    PRIMARY(1),
    SECONDARY(1);

    final int code;

    AliasCode(int code) {
        this.code = code;
    }
}
```

`AliasCode.PRIMARY.code == AliasCode.SECONDARY.code` là true.

Nhưng `AliasCode.PRIMARY == AliasCode.SECONDARY` là false.

Điều này cho thấy **identity không phải kết quả so sánh field values**. Enum constant name/declaration định nghĩa hai members độc lập.

Nếu domain yêu cầu một code phải ánh xạ duy nhất tới một constant, **bạn phải tự thực hiện validation** trong thiết kế/code mapping; Java không tự cấm hai enum constants có cùng field value.

## 21. Runnable: hai hằng cùng mã

Lưu **`EnumSameFieldDifferentIdentityDemo.java`**:

```java
enum Code {
    FIRST(10),
    SECOND(10),
    THIRD(20);

    private final int numeric;

    Code(int numeric) {
        this.numeric = numeric;
    }

    int numeric() {
        return numeric;
    }
}

public class EnumSameFieldDifferentIdentityDemo {
    public static void main(String[] args) {
        System.out.println(Code.FIRST.numeric()
                == Code.SECOND.numeric());
        System.out.println(Code.FIRST == Code.SECOND);
        System.out.println(Code.FIRST.equals(Code.SECOND));
        System.out.println(Code.FIRST.ordinal());
        System.out.println(Code.SECOND.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSameFieldDifferentIdentityDemo.java
java EnumSameFieldDifferentIdentityDemo
```

Stdout:

```text
true
false
false
0
1
```

Nếu muốn dùng field `numeric` làm lookup key, phải quyết định thế nào khi duplicate codes xuất hiện; đừng giả định compiler đã chứng minh unique.

## 22. Không có public/protected enum constructor

Đoạn sau **cố ý không biên dịch**:

```java
enum Invalid {
    ONE(1);

    public Invalid(int code) {
    }
}
```

Constructor của enum không được public. Tương tự `protected Invalid(...)` không được phép.

Viết:

```java
enum Valid {
    ONE(1);

    private final int code;

    Valid(int code) {
        this.code = code;
    }
}
```

hoặc thêm `private` vào constructor theo nhu cầu.

**Không sửa bằng cách dùng `new Valid(1)` ở nơi khác.** Enum type deliberately restricts construction để giữ tập constants cố định theo declaration.

### Ngoài ra: enum không thể khai báo constructor tùy ý có lệnh gọi `super(...)`

Một enum extends `java.lang.Enum<E>` theo quy tắc ngôn ngữ, với cơ chế đặc biệt cho tên/ordinal. Programmer không trực tiếp gọi Enum constructor hay tự truyền tên/ordinal.

## 23. Thứ tự khởi tạo các enum constants

Các enum constants là những static fields được khởi tạo trong quá trình **class initialization**, theo thứ tự chúng xuất hiện trong khai báo trước khi static initializers/fields thông thường trong enum body được xử lý theo quy tắc phù hợp.

Ví dụ:

```java
enum Stage {
    FIRST(1),
    SECOND(2);

    Stage(int id) {
        System.out.println("construct:" + name() + ":" + id);
    }

    static {
        System.out.println("static-block");
    }
}
```

Trong một chương trình kích hoạt initialization của `Stage`, có thể dự đoán những dòng in từ constructor của FIRST, constructor của SECOND, rồi static initializer.

Điểm quan trọng:
- **Mỗi enum constant object được khởi tạo một lần khi enum class được initialize** (trong ngữ cảnh class initialization cụ thể).
- Gọi `Stage.FIRST` nhiều lần không chạy lại constructor.
- Gọi `Stage.values()` nhiều lần cũng không tạo lại enum constants.
- Không cần tạo enum instance đầu tiên bằng một lời gọi `new` thủ công.
- Static initialization của enum là bước riêng với việc sau này dùng object.

## 24. Runnable: quan sát construction order

Lưu **`EnumInitializationDemo.java`**:

```java
enum Stage {
    FIRST(1),
    SECOND(2),
    THIRD(3);

    private final int id;

    Stage(int id) {
        this.id = id;
        System.out.println("construct:" + name() + ":" + id);
    }

    static {
        System.out.println("static-block");
    }

    int id() {
        return id;
    }
}

public class EnumInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before");
        System.out.println(Stage.SECOND.id());
        System.out.println(Stage.FIRST.id());
        System.out.println(Stage.SECOND.id());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumInitializationDemo.java
java EnumInitializationDemo
```

Stdout:

```text
before
construct:FIRST:1
construct:SECOND:2
construct:THIRD:3
static-block
2
1
2
```

Mặc dù lần đầu caller truy cập `Stage.SECOND`, Java initialize **cả enum constants theo thứ tự declaration**: FIRST, SECOND, THIRD. Các lần truy cập tiếp theo không chạy constructors lại.

### Một bẫy trong enum constructor

Tránh tham chiếu trực tiếp tới **static field không phải constant variable của chính enum** trong constructor/instance initializer. Java có các compile-time restrictions để ngăn những trường hợp đọc state enum chưa được initialize đầy đủ. Nếu cần lookup map của enum values, thường xây map sau khi constants đã tạo, ví dụ trong static initializer.

## 25. Constructors overload trong enum

Một enum có thể có constructor overload:

```java
enum Severity {
    LOW,
    HIGH(10);

    private final int weight;

    Severity() {
        this(1);
    }

    Severity(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}
```

- `LOW` dùng no-arg constructor, rồi constructor chaining tới `Severity(int)`.
- `HIGH(10)` dùng constructor với `int`.
- `LOW` và `HIGH` vẫn là hai constants distinct identities.
- Constructor chaining bằng `this(...)` xảy ra trong constructors của enum; không có `new Severity()` bên ngoài declaration.

### Runnable

Lưu **`EnumConstructorOverloadDemo.java`**:

```java
enum Severity {
    LOW,
    HIGH(10);

    private final int weight;

    Severity() {
        this(1);
    }

    Severity(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}

public class EnumConstructorOverloadDemo {
    public static void main(String[] args) {
        System.out.println(Severity.LOW.weight());
        System.out.println(Severity.HIGH.weight());
        System.out.println(Severity.LOW == Severity.HIGH);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumConstructorOverloadDemo.java
java EnumConstructorOverloadDemo
```

Stdout:

```text
1
10
false
```

Nếu muốn defaults rõ trong API, overload có thể giúp; nhưng đừng tạo quá nhiều constructor signatures mơ hồ khiến constant declarations khó đọc.

## 26. Phần thân riêng cho từng hằng không đổi danh tính

Một constant có thể có *constant-specific class body* để override hành vi, nhưng vẫn là **chính hằng có tên ấy**, không phải một cách tạo enum instances mới theo yêu cầu. Ví dụ:

~~~java
enum Operation {
    ADD { @Override int apply(int a, int b) { return a + b; } },
    MULTIPLY { @Override int apply(int a, int b) { return a * b; } };

    abstract int apply(int a, int b);
}
~~~

Đây là enum declaration hợp lệ, chưa có `main`. `ADD != MULTIPLY`, mỗi hằng vẫn giữ `name()` và `ordinal()` như được khai báo. **Điểm identity dễ bỏ sót:** với constant-specific body, `Operation.ADD.getClass()` có thể khác `Operation.class`, trong khi `Operation.ADD.getDeclaringClass() == Operation.class` luôn true. Điều này thuộc cơ chế anonymous subclass được compiler quản lý, không làm enum trở thành tập mở.

Ví dụ runnable kế tiếp sẽ thực nghiệm behavior và identity; bài riêng về **phần thân từng hằng** đi sâu abstract method, shared implementation, visibility và lựa chọn so với `switch`.

## 27. Runnable: behavior và identity theo từng constant

Lưu **`EnumConstantBodyDemo.java`**:

```java
enum Operation {
    ADD("+") {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY("*") {
        @Override
        int apply(int a, int b) {
            return a * b;
        }
    };

    private final String symbol;

    Operation(String symbol) {
        this.symbol = symbol;
    }

    String symbol() {
        return symbol;
    }

    abstract int apply(int a, int b);
}

public class EnumConstantBodyDemo {
    public static void main(String[] args) {
        Operation add = Operation.ADD;
        Operation multiply = Operation.MULTIPLY;

        System.out.println(add.apply(3, 4));
        System.out.println(multiply.apply(3, 4));
        System.out.println(add.symbol());
        System.out.println(add.name());
        System.out.println(add == Operation.ADD);
        System.out.println(add.getClass() == Operation.class);
        System.out.println(
                add.getDeclaringClass() == Operation.class);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumConstantBodyDemo.java
java EnumConstantBodyDemo
```

Stdout:

```text
7
12
+
ADD
true
false
true
```

Mỗi hằng truyền `symbol` vào constructor enum và override `apply` bằng behavior riêng. `Operation.ADD` vẫn là một constant cố định, dù runtime subclass dùng để triển khai behavior riêng.

## 28. Constant-specific body và phương thức `toString()`

Một constant có thể override `toString()` riêng:

```java
enum Format {
    JSON {
        @Override
        public String toString() {
            return "application/json";
        }
    },
    TEXT {
        @Override
        public String toString() {
            return "text/plain";
        }
    }
}
```

`Format.JSON.name()` vẫn `"JSON"`; `Format.JSON.toString()` trả `"application/json"`.

Nhưng **không thể override `name()`**, `ordinal()`, `equals` hoặc `hashCode` vì các methods tương ứng trong `Enum` là final.

### Lỗi thiết kế dễ mắc

Nếu serializer dùng `toString()` làm identifier, một UI change có thể phá dữ liệu. Hãy dùng explicit stable code nếu đó là contract, và dùng `name()` khi bạn thực sự chấp nhận coupling với source identifier.

## 29. Interface không làm mất bản sắc enum constant

Enum có thể `implements` interface dù không thể tự `extends` một class bất kỳ. Reference có kiểu interface vẫn giữ nguyên **đối tượng hằng gốc**:

~~~java
interface Labelled {
    String label();
}

enum Status implements Labelled {
    ACTIVE, SUSPENDED;
    @Override
    public String label() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

Đây là declarations hợp lệ. `Labelled label = Status.ACTIVE;` dùng method qua API interface, nhưng object được tham chiếu vẫn là `Status.ACTIVE`. Enum constant-specific methods có thể triển khai behavior khác nhau trong cùng contract.

Trọng tâm tại đây là **canonical identity bất biến qua upcast**. Bài `Enum hiện thực interface` đào sâu default methods, multiple/generic interfaces, `Predicate`, `Function`, `Comparator` và cách kiểm thử hợp đồng.

## 30. Runnable: enum và interface

Lưu **`EnumInterfaceDemo.java`**:

```java
interface Command {
    String execute(String input);
}

enum CommandType implements Command {
    UPPER {
        @Override
        public String execute(String input) {
            return input.toUpperCase(
                    java.util.Locale.ROOT);
        }
    },
    WRAP {
        @Override
        public String execute(String input) {
            return "[" + input + "]";
        }
    }
}

public class EnumInterfaceDemo {
    public static void main(String[] args) {
        Command first = CommandType.UPPER;
        Command second = CommandType.WRAP;

        System.out.println(first.execute("java"));
        System.out.println(second.execute("java"));
        System.out.println(first == CommandType.UPPER);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumInterfaceDemo.java
java EnumInterfaceDemo
```

Stdout:

```text
JAVA
[java]
true
```

Enum constant có thể được truyền qua interface `Command`, nhưng identity với `CommandType.UPPER` vẫn được giữ khi reference được gán vào một biến interface.

## 31. `switch` chọn nhánh theo hằng đã khai báo

Nếu `status` có kiểu enum `OrderStatus` với hằng `NEW`, `PAID`, `SHIPPED`, `CANCELLED`, bạn có thể phân nhánh trực tiếp theo **constant identity**, thay vì tự so tên String:

~~~java
String label = switch (status) {
    case NEW -> "New";
    case PAID -> "Paid";
    case SHIPPED -> "Shipped";
    case CANCELLED -> "Cancelled";
};
~~~

Đây là snippet Java 17 cần `status` đã khai báo. Compiler kiểm tra case labels và tính bao phủ nhánh của switch expression; với selector null, switch enum trong Java 17 thông thường ném NPE. Trong code này, `case NEW` dùng tên hằng **không kèm qualifier** theo cú pháp Java 17.

Bài về `==` và `switch` sẽ thực hành đầy đủ dạng colon/arrow, fall-through, `yield`, null, exhaustiveness và trade-off với đa hình. Phần hiện tại chỉ cho thấy enum được dùng đúng theo danh tính có kiểu.

## 32. Runnable: switch expression theo enum

Lưu **`EnumSwitchDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

public class EnumSwitchDemo {
    static String label(OrderStatus status) {
        return switch (status) {
            case NEW -> "new";
            case PAID -> "paid";
            case SHIPPED -> "shipped";
            case CANCELLED -> "cancelled";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(OrderStatus.NEW));
        System.out.println(label(OrderStatus.SHIPPED));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSwitchDemo.java
java EnumSwitchDemo
```

Stdout:

```text
new
shipped
```

Một enum constant có identity duy nhất; switch chọn nhánh theo giá trị enum. Không cần tự tạo bảng `String→int ordinal` để rẽ nhánh.

## 33. `EnumSet` làm việc với tập các canonical constants

`EnumSet<Role>` là `Set` chuyên biệt cho một enum type; các phần tử vẫn là **chính enum constants**, không phải clones:

~~~java
java.util.EnumSet<Role> roles =
        java.util.EnumSet.of(Role.READER, Role.WRITER);
~~~

Đây là snippet yêu cầu enum `Role` chứa `READER`, `WRITER`. `EnumSet` không chứa null/duplicates, duyệt theo thứ tự khai báo enum thay vì thứ tự thêm. Nếu tạo tập rỗng, `EnumSet.noneOf(Role.class)` nêu rõ type; `copyOf` từ collection rỗng không phải `EnumSet` có thể thiếu thông tin kiểu để suy ra.

Bài này chỉ quan sát tính **canonical** của các members. Ví dụ runnable tiếp theo minh họa hành vi collection; tránh đồng nhất tập references với việc tạo mới constant objects.

## 34. Runnable: EnumSet giữ constants và thứ tự khai báo

Lưu **`EnumSetDemo.java`**:

```java
import java.util.EnumSet;

enum Permission {
    READ, WRITE, EXECUTE
}

public class EnumSetDemo {
    public static void main(String[] args) {
        EnumSet<Permission> set =
                EnumSet.of(Permission.EXECUTE, Permission.READ);

        System.out.println(set);
        System.out.println(set.contains(Permission.READ));

        set.add(Permission.WRITE);

        for (Permission permission : set) {
            System.out.println(permission.name());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSetDemo.java
java EnumSetDemo
```

Stdout:

```text
[READ, EXECUTE]
true
READ
WRITE
EXECUTE
```

Dù gọi `of(EXECUTE, READ)`, `EnumSet` iteration là declaration order, không phải insertion order. Đây là đặc trưng hữu ích nhưng **đừng dùng nó để mã hóa một thứ tự nghiệp vụ có thể thay đổi** nếu cần independent explicit ordering.

## 35. `EnumMap` dùng hằng enum làm khóa có kiểu

`EnumMap<Role, String>` gắn values với keys là **các canonical enum constants**; nó không tạo thêm constants hay đánh đồng hai hằng chỉ vì field/label giống nhau.

~~~java
java.util.EnumMap<Role, String> labels =
        new java.util.EnumMap<>(Role.class);
labels.put(Role.READER, "Read");
~~~

Đây là snippet cần `Role` đã khai báo. `EnumMap` không cho null keys, có thể cho null values, và thứ tự duyệt các keys theo declaration order. Dùng nó khi cần bảng ánh xạ bằng dữ liệu; dùng switch nếu một phép phân nhánh nhỏ rõ hơn; dùng enum method nếu behavior thực sự thuộc constant.

Chương trình kế tiếp chứng minh những keys vẫn là **chính hằng**; không cần xem `EnumMap` là một factory hoặc một cơ chế đổi identity.

## 36. Runnable: EnumMap

Lưu **`EnumMapDemo.java`**:

```java
import java.util.EnumMap;

enum Phase {
    START, RUNNING, DONE
}

public class EnumMapDemo {
    public static void main(String[] args) {
        EnumMap<Phase, String> messages =
                new EnumMap<>(Phase.class);

        messages.put(Phase.DONE, "complete");
        messages.put(Phase.START, "begin");
        messages.put(Phase.RUNNING, "work");

        for (var entry : messages.entrySet()) {
            System.out.println(entry.getKey().name()
                    + "=" + entry.getValue());
        }

        System.out.println(
                messages.get(Phase.DONE));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumMapDemo.java
java EnumMapDemo
```

Stdout:

```text
START=begin
RUNNING=work
DONE=complete
complete
```

Iteration order không phụ thuộc insertion order; nó theo declaration order của `Phase`.

## 37. `ordinal` và sắp xếp hằng

`Enum` implements `Comparable` theo thứ tự tự nhiên là **declaration order** của các constants cùng enum type. Vì vậy `compareTo` dùng ordinal-based ordering.

`Priority.LOW.compareTo(Priority.HIGH)` âm nếu LOW khai báo trước HIGH.

Điều cần phân biệt:
- Dùng declaration order làm thứ tự tự nhiên khi **đó thực sự là thứ tự domain** có thể hợp lý.
- Dùng ordinal làm **ID được lưu/persist** không an toàn khi declaration có thể thay đổi.
- Nếu muốn priority score khác declaration order, thêm field `rank` riêng.
- `EnumSet`/`EnumMap` iterate declaration order dù caller thêm keys khác thứ tự.

### Nếu thứ tự nghiệp vụ khác ordinal

Dùng `Comparator.comparingInt(Priority::rank)` hoặc một quy tắc explicit. Đừng reorder enum constants chỉ để thay đổi UI rank nếu việc ấy gây tác động thứ tự elsewhere.

## 38. Mã nghiệp vụ là thuộc tính, không phải identity của hằng

Khi một enum constant cần **external code** ổn định, khai báo field riêng:

~~~java
enum InvoiceState {
    DRAFT("D"), APPROVED("A"), REJECTED("R");

    private final String code;
    InvoiceState(String code) { this.code = code; }
    String code() { return code; }
}
~~~

Đây là declaration hợp lệ. Đổi vị trí hằng không tự đổi code `"A"`; nhưng hai hằng vẫn có thể vô tình mang cùng code, vì compiler không kiểm tra tính unique của field ấy.

**Phân biệt hai hợp đồng:** `InvoiceState.APPROVED` là canonical enum object; `"A"` là giá trị có thể gửi tới DB/API theo contract do ứng dụng đặt ra. Ví dụ tiếp theo chứng minh `fromCode` trả lại hằng canonical. Bài riêng về rủi ro `ordinal()` phân tích schema, migration, versioning và unknown external data.

## 39. Runnable: stable code và parse từ dữ liệu ngoài

Lưu **`EnumStableCodeDemo.java`**:

```java
enum PaymentState {
    PENDING("P"),
    PAID("S"),
    FAILED("F");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static PaymentState fromCode(String code) {
        for (PaymentState candidate : values()) {
            if (candidate.code.equals(code)) {
                return candidate;
            }
        }
        throw new IllegalArgumentException(
                "unknown code");
    }
}

public class EnumStableCodeDemo {
    public static void main(String[] args) {
        PaymentState paid = PaymentState.fromCode("S");

        System.out.println(paid.name());
        System.out.println(paid.code());
        System.out.println(paid == PaymentState.PAID);

        try {
            PaymentState.fromCode("X");
        } catch (IllegalArgumentException error) {
            System.out.println("unknown");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumStableCodeDemo.java
java EnumStableCodeDemo
```

Stdout:

```text
PAID
S
true
unknown
```

`fromCode` trả canonical constant. Đổi thứ tự khai báo PENDING/PAID/FAILED không làm code `"S"` tự thay đổi.

**Lưu ý:** `candidate.code.equals(code)` không ném NPE khi code input null vì `candidate.code` được gán String không null. Ở production cần validate uniqueness và null contract kỹ hơn.

## 40. `name()` làm external identifier: quyết định có chủ đích

Lưu `name()` có thể hợp lý nếu **tên constant là một phần của contract ổn định**, team kiểm soát rename/remove và có migration. Nhưng `name()` phản ánh **tên trong Java source**, nên đổi `PAID` thành `SETTLED` có thể làm `valueOf("PAID")` không còn tìm được hằng cũ.

Không dùng `toString()` làm identifier nếu method đó chỉ phục vụ nhãn hiển thị/localization. Với giao thức cần ổn định qua nhiều releases, explicit `code()` và `fromCode(...)` thường rõ hơn. Các mapping ORM/JPA và lựa chọn code/string/ordinal có contract riêng ngoài Java Core; **không có annotation mặc định nào thay thế chiến lược migration/versioning**.

Đây là phân biệt giữa **tên khai báo** và **identity dữ liệu bền vững**. Bài cuối chương chuyên sâu tác động của thứ tự ordinal, rolling deployments và migration legacy records.

## 41. Serialization của enum và identity

Java serialization có **cơ chế đặc biệt cho enum constants**: serialized form dựa vào enum type và tên constant, và khi deserialize theo điều kiện tương thích sẽ resolve về **canonical constant** của enum type hiện có, không tạo một enum instance song song bằng cách gọi constructor thường.

Điểm cần nhớ:
- Enum objects vẫn có identity riêng ổn định sau serialization round-trip hợp lệ.
- Enum deserialization không giống constructor-based cloning một POJO.
- Instance fields riêng không được dùng như serializable payload theo default enum serialization mechanism.
- Nếu enum constant name bị rename/remove, dữ liệu serialized theo name cũ có thể không resolve được.
- Các công nghệ JSON/custom serializers có thể có representation riêng, cần đọc contract của thư viện, không suy từ Java native serialization.

### Tại sao enum singleton thường “an toàn hơn” khi serialize?

Một enum singleton pattern `INSTANCE` dùng serialization semantics của enum thay vì dựa vào tự viết `readResolve` cho ordinary serializable singleton class. Tuy vậy đừng tự khẳng định mọi external serialization library đều giữ identity nếu library ánh xạ thành DTO/string theo cách riêng.

## 42. `clone()` và reflection có tạo được một enum constant thứ hai?

Cơ chế Java cố tình hạn chế việc tạo enum objects:
- Không gọi `new EnumType(...)` trong source.
- `Enum.clone()` là final và ngăn cloning theo cách thông thường.
- Reflection `Constructor.newInstance` không cho tạo enum object mới tùy ý theo cơ chế thông thường.
- Java serialization đặc biệt resolve canonical constant theo tên/type.

Điều này hỗ trợ identity semantics của enum trong những đường tạo object chuẩn.

**Không nên biến đây thành phát biểu rằng mọi hack với JVM internals/Unsafe/native code đều bất khả thi về vật lý.** Bài học đề cập **Java language/runtime APIs được hỗ trợ thông thường**, không khai thác internal implementation.

### Enum singleton

`enum Singleton { INSTANCE; }` là pattern biểu diễn một global instance **trong phạm vi enum type/class loader tương ứng**. Nó gọn và có ưu điểm về serialization/identity, nhưng nếu `INSTANCE` chứa mutable state, vẫn cần thread-safety.

## 43. Mutable fields trong enum: một instance dùng chung vẫn có thể mutable

Hãy cẩn thận với:

```java
enum Counter {
    INSTANCE;

    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

`Counter.INSTANCE` có canonical identity, nhưng field `value` **có thể thay đổi**.

Hệ quả:
- Mọi code dùng Counter.INSTANCE có thể tương tác với **cùng mutable state**.
- `final` của constant reference không làm mọi instance fields trở thành final.
- `value++` không atomic dưới concurrency.
- Enum không tự cung cấp thread safety cho mutable state.
- Các tests chia sẻ JVM/class loader có thể ảnh hưởng nhau nếu không reset/design đúng.

### Tốt hơn trong nhiều trường hợp

Nếu constants chỉ mang metadata:
- Dùng `private final` fields.
- Gán immutable values ở enum constructors.
- Nếu cần mutable global state, dùng explicit service/atomic abstraction với owner/lifecycle rõ.
- Tránh stateful enum constants khi điều đó làm tính đúng khó hiểu.

## 44. Runnable: identity cố định, state mutable

Lưu **`MutableEnumDemo.java`**:

```java
enum Counter {
    INSTANCE;

    private int value = 0;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class MutableEnumDemo {
    public static void main(String[] args) {
        Counter first = Counter.INSTANCE;
        Counter second = Counter.INSTANCE;

        first.increment();
        second.increment();

        System.out.println(first == second);
        System.out.println(first.value());
        System.out.println(second.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableEnumDemo.java
java MutableEnumDemo
```

Stdout:

```text
true
2
2
```

Ví dụ chạy tuần tự nên stdout xác định. Nếu cùng Counter.INSTANCE được tăng từ nhiều threads, `value++` có thể gây lost updates; cần synchronization/atomic mechanisms phù hợp.

## 45. Enum, immutable metadata và safe publication

Mỗi enum constant có thể là một nơi giữ cấu hình immutable:

```java
enum Timeout {
    SHORT(java.time.Duration.ofSeconds(5)),
    LONG(java.time.Duration.ofSeconds(30));

    private final java.time.Duration duration;

    Timeout(java.time.Duration duration) {
        this.duration = duration;
    }

    java.time.Duration duration() {
        return duration;
    }
}
```

`Duration` là immutable value type; field final giúp cấu hình mỗi constant ổn định và dễ chia sẻ.

Java class initialization có các guarantees liên quan tới visibility/happens-before cho việc khởi tạo static state đúng chuẩn, nhưng nếu bạn **sau đó mutate** một field/mutable object được enum giữ, bạn vẫn phải thực hiện synchronization riêng.

**Mỗi hằng được xây dựng một lần không đồng nghĩa mọi operation trên nó đều thread-safe mãi về sau.**

## 46. Cẩn thận dùng hằng enum trong switch/collections khi thêm hằng mới

Thêm enum constant có thể làm những nơi sử dụng enum cần cập nhật:
- `switch` expression đã liệt kê tất cả constants cũ.
- `EnumSet.allOf(Type.class)` sẽ bao gồm constant mới.
- `values()` có thêm phần tử và ordinal có thể thay đổi.
- UI tự build menu từ `values()` hiển thị mục mới.
- `EnumMap` code tạo entries cho danh sách cũ có thể thiếu key mới.
- Validators/dữ liệu serialized/cross-service protocols cần hỗ trợ value mới.

Không phải mọi lần thêm constant đều là compatible change đối với mọi consumer. Phân biệt **source compatibility**, **binary compatibility**, **runtime data compatibility** và **business semantics**.

### Sửa thứ tự constants

Thay đổi thứ tự không thay Java reference identity của tên hằng trong một build, nhưng làm ordinal, natural ordering và iteration order của `values`/`EnumSet`/`EnumMap` thay đổi. Nếu consumer dựa vào thứ tự cũ, đây là thay đổi có tác động.

## 47. Nested enum và local enum trong Java 17

Một enum có thể là member nested type:

```java
class Order {
    enum Status {
        NEW, PAID
    }
}
```

Member enum có static semantics, không yêu cầu một enclosing `Order` instance. Dùng `Order.Status.NEW` từ ngữ cảnh có access thích hợp.

Java 17 cũng cho phép **local enum** được khai báo trong block:

```java
void run() {
    enum Mode {
        FAST, SAFE
    }

    Mode selected = Mode.FAST;
}
```

Local enum implicitly static, tên chỉ thấy trong lexical scope của block. Nó không capture local variables theo cơ chế của local normal inner class.

**Dù enum nested/local, mỗi declared constant vẫn có enum identity semantics.** Vị trí khai báo ảnh hưởng scope/visibility, không đổi bản chất hằng.

## 48. Runnable: nested enum không cần enclosing object

Lưu **`NestedEnumDemo.java`**:

```java
public class NestedEnumDemo {
    enum Mode {
        FAST, SAFE
    }

    public static void main(String[] args) {
        NestedEnumDemo.Mode a = NestedEnumDemo.Mode.FAST;
        Mode b = Mode.FAST;

        System.out.println(a == b);
        System.out.println(a.name());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NestedEnumDemo.java
java NestedEnumDemo
```

Stdout:

```text
true
FAST
```

Không có một `new NestedEnumDemo()` nào. Nested member enum implicitly static, hai references cùng trỏ một constant `FAST`.

## 49. Reflection: xác định enum type của constant

Nếu không có constant-specific body:

```java
MyEnum.VALUE.getClass() == MyEnum.class
```

thường true vì object runtime class là enum class.

Nhưng nếu hằng có constant-specific body:

```java
enum Action {
    RUN {
        @Override
        void perform() {
        }
    };

    abstract void perform();
}
```

`Action.RUN.getClass()` là một anonymous subclass runtime class; so sánh với `Action.class` không còn bảo đảm true.

Để lấy **declaring enum class** của constant, dùng:

```java
Action.RUN.getDeclaringClass() == Action.class
```

là true.

### Không dùng compiler-generated class name làm identifier

Các tên như `Action$1` trong bytecode không phải public business contract. Không lưu chúng vào database để mô hình enum identity. Dùng enum type và constant name/code thích hợp.

## 50. Một tập enum constants có phải Set không?

Enum type là **tập khai báo các khả năng**, nhưng bản thân enum declaration không phải một `java.util.Set` object.

`values()` tạo array snapshot các constants; `EnumSet.allOf(MyEnum.class)` tạo Set chứa tất cả enum constants; chúng khác kinds và API.

Ví dụ:
- `MyEnum.values().length`: số hằng ở declaration.
- `EnumSet.allOf(MyEnum.class).size()`: số enum constants trong set.
- `EnumSet.noneOf(MyEnum.class)`: set rỗng với enum type biết trước.

Không được tạo enum constants mới bằng `mySet.add(new MyEnum())`; Set chỉ thêm references đến những constants đã khai báo.

## 51. Enum type vs sealed hierarchy vs record

Enum phù hợp khi:
- Tập hợp các giá trị **đóng và hữu hạn** được biết khi compile.
- Mỗi giá trị có một tên canonical và identity.
- Mỗi constant có thể mang metadata/behavior.
- Client không cần tạo thêm instances mới lúc runtime.

Nếu các variants phải mang payload khác nhau do caller truyền lúc runtime, ví dụ:
- `Success(value)`;
- `Failure(reason)`;
- `Pending(retryAt)`;

thì một **sealed interface + records** có thể tự nhiên hơn enum duy nhất, vì sẽ có **nhiều instances** của mỗi variant.

Không nên biến `enum Error { ONE; mutable Object payload; }` thành “biến chứa kết quả cho mọi request” vì một constant sẽ chia sẻ mutable payload giữa các calls.

### Quyết định identity

- Enum: identity theo constant object `State.SUCCESS`.
- Record/value object: equality theo components (mặc định đối với record, có caveats với arrays).
- Entity: identity theo domain ID/lifecycle, không phải enum constant.
- Sealed variant instances: có thể nhiều objects thuộc cùng subtype.

Hiểu identity giúp tránh chọn enum cho một bài toán dữ liệu động.

## 52. Những vấn đề khi dùng enum như tập trạng thái workflow

Enum trạng thái rất tiện:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
```

Nhưng enum declaration **không tự định nghĩa transition rules**:
- Có được NEW → SHIPPED bỏ qua PAID không?
- Có được CANCELLED → PAID không?
- Ai có quyền thay đổi state?
- Transition có side effect hoặc transaction cần atomicity không?
- Audit lịch sử ở đâu?

Bạn có thể dùng enum làm **state label**, rồi cho workflow/service kiểm tra transition hoặc thêm behavior lên enum nếu domain đủ nhỏ.

**Không gán mutable current order state vào `OrderStatus.PAID` object**. Current state phải nằm trong từng Order instance/entity, còn `OrderStatus.PAID` là shared constant mô tả một trạng thái.

## 53. Runnable: enum constant được dùng làm field của nhiều objects

Lưu **`OrderWithEnumDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID
}

final class Order {
    private OrderStatus status = OrderStatus.NEW;

    void pay() {
        status = OrderStatus.PAID;
    }

    OrderStatus status() {
        return status;
    }
}

public class OrderWithEnumDemo {
    public static void main(String[] args) {
        Order a = new Order();
        Order b = new Order();

        a.pay();

        System.out.println(a.status());
        System.out.println(b.status());
        System.out.println(a.status() == OrderStatus.PAID);
        System.out.println(b.status() == OrderStatus.NEW);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrderWithEnumDemo.java
java OrderWithEnumDemo
```

Stdout:

```text
PAID
NEW
true
true
```

Hai Orders có **state field độc lập**, nhưng mỗi field trỏ tới một enum constant canonical. Thay reference `a.status` sang PAID không mutate `OrderStatus.NEW` hoặc làm b đổi state.

## 54. Lỗi nhầm tên constant với String

Code sai ý định thường gặp:

```java
if (status.name() == "PAID") {
    // ...
}
```

Toán tử `==` trên Strings so sánh references, không phải nội dung. Dù Java có String interning và tên enum có thể liên quan literal internals, code trên **không nên dựa vào một sự trùng reference tình cờ**.

Thay:

```java
if (status == OrderStatus.PAID) {
    // ...
}
```

Hoặc nếu bạn thực sự nhận String từ external input và cần parse:

```java
OrderStatus parsed = OrderStatus.valueOf(input);
```

kèm validate/catch lỗi.

**Enum identity comparison trực tiếp** rõ hơn việc biến constant thành String rồi so sánh ngược.

## 55. Equality với enum: không có object “cùng tên nhưng mới”

Trong ordinary class, `new Item("A")` tạo instance mới, nên hai Items có thể cùng field value nhưng khác references.

Trong enum:
- Enum constants được xác định trong declaration.
- Code Java thường không được new thêm hằng cùng tên.
- `valueOf` trả existing constant.
- `values` trả references tới existing constants.
- Java native serialization resolve existing constant.

Vì vậy so sánh `status == OrderStatus.PAID` là một biểu thức theo **identity** nhưng đồng thời là cách thông thường để kiểm tra **giá trị trạng thái** của enum.

Đó là điểm khác biệt với object value types thường cần `equals`.

## 56. Bài tập 1 — Nhận diện type và constants

Cho:

```java
enum Direction {
    NORTH, SOUTH
}
```

Có bao nhiêu enum type và bao nhiêu declared constants?

**Đáp án:** Một type `Direction`; hai constants `NORTH` và `SOUTH`, tương ứng hai enum instances khác danh tính.

## 57. Bài tập 2 — Hai reference cùng hằng

```java
Direction a = Direction.NORTH;
Direction b = Direction.NORTH;
```

`a == b`?

**Đáp án:** `true`. Hai variables cùng trỏ canonical constant NORTH.

## 58. Bài tập 3 — Hai constants khác nhau

`Direction.NORTH == Direction.SOUTH`?

**Đáp án:** `false` vì khác enum objects.

## 59. Bài tập 4 — `values` clone constants không?

```java
Direction[] x = Direction.values();
Direction[] y = Direction.values();
```

`x == y` và `x[0] == y[0]`?

**Đáp án:** `false` và `true` (với enum có ít nhất một constant), vì mỗi lần values tạo array mới, nhưng các phần tử là same canonical constants.

## 60. Bài tập 5 — `valueOf` tạo instance mới?

```java
Direction a = Direction.valueOf("NORTH");
```

`a == Direction.NORTH`?

**Đáp án:** `true`. valueOf trả existing constant.

## 61. Bài tập 6 — `name` là object?

`Direction.NORTH.name()` trả type gì?

**Đáp án:** `String`, nội dung `"NORTH"`. Nó không phải một enum constant.

## 62. Bài tập 7 — `ordinal` bắt đầu mấy?

Với `enum Rank { BRONZE, SILVER, GOLD }`, `Rank.GOLD.ordinal()`?

**Đáp án:** `2` (zero-based declaration order).

## 63. Bài tập 8 — Dùng ordinal cho database

Bạn lưu `GOLD.ordinal() = 2` trong database. Sau đó chèn `PLATINUM` trước GOLD.

**Đáp án:** Giá trị ordinal của GOLD thay đổi; mapping cũ không còn đúng. Dùng explicit stable code hoặc storage representation được quản lý/migrated.

## 64. Bài tập 9 — Override `name()`?

Có được khai báo trong enum:

```java
// @Override
// public String name() { return "custom"; }
```

**Đáp án:** Không, `name()` là final method trong `Enum`. Muốn custom label, khai báo method riêng hoặc override `toString()` nếu phù hợp.

## 65. Bài tập 10 — Override `toString()`?

Enum có được override `toString()` không?

**Đáp án:** Có. Nhưng `name()` vẫn là tên khai báo. Đừng dùng UI label từ toString làm stable external key nếu có thể thay đổi.

## 66. Bài tập 11 — Hai constants cùng mã

```java
enum Code {
    A(7), B(7);

    private final int id;

    Code(int id) {
        this.id = id;
    }
}
```

A và B có cùng identity không?

**Đáp án:** Không. `A == B` false; constructor arguments trùng chỉ khiến field values trùng.

## 67. Bài tập 12 — Constructor public?

`public Color(int code) { ... }` trong enum có hợp lệ không?

**Đáp án:** Không. Enum constructors không được public/protected; dùng private hoặc không ghi access modifier.

## 68. Bài tập 13 — `new EnumType()`?

Một client có thể gọi `new Direction()` để tạo một hằng nữa?

**Đáp án:** Không. Enum construction là cơ chế đặc biệt gắn với constant declarations, không mở constructor cho client.

## 69. Bài tập 14 — Static initialization một hằng được truy cập trước

Với `enum E { A, B, C; ... }` và constructor in tên, main truy cập E.C lần đầu.

**Đáp án:** Enum class initialization tạo các hằng theo thứ tự khai báo A, B, C. Không chỉ xây C; constructor hằng không chạy lại ở truy cập sau.

## 70. Bài tập 15 — Constructor dùng `name()`

Enum constructor in `name()`. Có giá trị nào?

**Đáp án:** Tên enum constant tương ứng đã được thiết lập theo cơ chế enum instance construction, nên constructor có thể in tên hằng. Không tự gán name/ordinal bằng Java source constructor.

## 71. Bài tập 16 — Constant-specific behavior

Một enum `Operation` có ADD và MULTIPLY với bodies override `apply`.

**Đáp án:** Hai hằng vẫn có distinct identities. Runtime class của hằng có class body có thể là anonymous subtype; dùng `getDeclaringClass()` để xác định `Operation.class`.

## 72. Bài tập 17 — `getClass()` của hằng

`Action.RUN` có constant-specific class body. `Action.RUN.getClass() == Action.class` luôn true không?

**Đáp án:** Không. Có thể false vì runtime class là constant-specific anonymous subclass. `Action.RUN.getDeclaringClass() == Action.class` true.

## 73. Bài tập 18 — Enum khác type nhưng cùng tên

`OrderState.OPEN.equals(TicketState.OPEN)`?

**Đáp án:** `false`, mặc dù cả hai có `name() == "OPEN"` theo nội dung String. Mỗi type có tập constants riêng.

## 74. Bài tập 19 — Null và `==`

`OrderStatus status = null;`. `status == OrderStatus.PAID`?

**Đáp án:** `false`, không NPE. Nhưng `status.name()` ném NPE.

## 75. Bài tập 20 — EnumSet order

`EnumSet.of(Permission.EXECUTE, Permission.READ)` iterate theo thứ tự nào, với declaration `READ, WRITE, EXECUTE`?

**Đáp án:** READ trước EXECUTE. EnumSet iteration theo natural declaration order, không insertion order.

## 76. Bài tập 21 — EnumMap order

Thêm keys theo DONE, START, RUNNING vào EnumMap; declaration START, RUNNING, DONE.

**Đáp án:** Iterate theo START, RUNNING, DONE.

## 77. Bài tập 22 — Mutable enum có thread-safe không?

`enum Counter { INSTANCE; int value; void inc(){ value++; } }`.

**Đáp án:** Không tự thread-safe. Canonical identity không làm `value++` atomic; cần synchronization/atomic API nếu dùng đồng thời.

## 78. Bài tập 23 — Enum làm current state?

Có nên đặt `int currentOrderId` mutable field vào `OrderStatus.PAID` để lưu ID đơn đang paid không?

**Đáp án:** Thường không. PAID là shared constant giữa mọi orders; current state/ID thuộc từng Order entity. Mutable data trên constant dễ gây global shared-state bugs.

## 79. Bài tập 24 — Tên hằng và nhãn UI

`PaymentStatus.SUCCESS` cần hiển thị “Thanh toán thành công” ở tiếng Việt và “Payment successful” ở tiếng Anh.

**Đáp án:** Không rename enum constant theo ngôn ngữ. Giữ identifier ổn định, dùng localization/mapping labels theo locale. Có thể có method displayName nhưng đừng biến toString thành business identity ngoài hệ thống.

## 80. Bài tập 25 — Thêm hằng mới vào giữa

Thêm `PAUSED` vào giữa RUNNING và DONE ảnh hưởng những gì?

**Đáp án:** Thứ tự `values`, ordinals của các hằng phía sau, EnumSet/EnumMap natural order và những switch/logic exhaustiveness liên quan. External mappings lưu ordinal có thể bị hỏng.

## 81. Bài tập 26 — Enum serialization

Một enum constant được serialize/deserialize bằng Java native enum serialization.

**Đáp án:** Deserialization resolve hằng canonical theo enum type/name; không tự cấp phát một instance song song bằng constructor thông thường. Rename/remove constant có thể làm dữ liệu serialized cũ không resolve được.

## 82. Bài tập 27 — Enum singleton

`enum Singleton { INSTANCE; }` luôn có đúng một instance trên mọi JVM/class loader ở thế giới?

**Đáp án:** Không nên khẳng định mức đó. Trong một enum class runtime được tải ở một class loader context, INSTANCE là canonical constant; class loaders/processes khác không có cùng object reference.

## 83. Bài tập 28 — Custom stable code

`enum Status { PENDING("P"), PAID("S") }`, sau đó reorder constants.

**Đáp án:** `code()` vẫn trả mã được gắn trong declarations, nếu không sửa dữ liệu. Ordinals đổi, nhưng explicit business code không tự đổi.

## 84. Bài tập 29 — `valueOf` với toString tùy chỉnh

`enum State { OK; @Override public String toString(){return "Success";} }`. `State.valueOf("Success")`?

**Đáp án:** `IllegalArgumentException` vì valueOf tìm theo `name()=="OK"`, không tìm theo toString label.

## 85. Bài tập 30 — Type thích hợp hơn enum?

Một response có variants `Success(result)` và `Failure(reason)`, mỗi invocation mang payload khác nhau.

**Đáp án:** Thường xem xét sealed interface + records hoặc hierarchy phù hợp, vì mỗi call cần value object riêng. Không dùng shared mutable singleton enum constant để cất per-request payload.

## 86. Những hiểu lầm phổ biến

| Nhận định sai | Sự thật |
| --- | --- |
| Enum constant chỉ là String | Là object thuộc enum type, có reference identity |
| Mỗi lần đọc `Status.PAID` tạo object mới | Đọc cùng canonical constant |
| `values()` tạo hằng mới | Trả array mới, elements vẫn là constants cũ |
| `valueOf("PAID")` clone PAID | Trả chính constant PAID |
| Enum luôn bất biến hoàn toàn | Có thể có mutable instance fields/referents |
| Enum tự thread-safe cho mọi mutation | Identity/initialization không tự đồng bộ operations |
| `ordinal()` là stable code | Ordinal đổi nếu declaration order đổi |
| `toString()` luôn bằng `name()` | toString có thể override |
| Có thể override `equals` theo code field | Enum.equals là final và identity-based |
| Hằng cùng field value là cùng hằng | Hai names khác nhau là hai constant instances |
| Enum constructor có thể public | Không; hạn chế construction |
| Có thể `new SomeEnum()` như class thường | Không |
| Hằng có class body có `getClass()==Enum.class` chắc chắn | Runtime class có thể anonymous subtype |
| EnumSet giữ insertion order | Duyệt declaration order |
| EnumMap dùng arbitrary object key | Keys phải là enum constants cùng key enum type |
| Rename enum constant không ảnh hưởng serialized data | Dữ liệu dựa vào name có thể cần migration |
| Enum state fields lưu được per-user data an toàn | Constants được chia sẻ giữa users/calls |
| enum và record đều có equality theo field | Enum identity-based; record mặc định component-based |
| Switch enum tự chấp nhận null trong Java 17 | Selector null thường gây NPE |
| Mọi kiểu hữu hạn ở runtime đều nên là enum | Enum tốt khi set of values được đóng và biết ở compile time |

## 87. Checklist thiết kế enum đúng

1. Đây có phải **tập giá trị đóng, hữu hạn**, được biết khi compile không?
2. Các constants đã được đặt tên rõ ràng, có nghĩa nghiệp vụ không?
3. Có tránh dùng String/int tự do ở API khi enum phù hợp không?
4. Có phân biệt **enum type** và **từng constant object** không?
5. Đã hiểu mỗi declared constant có canonical reference identity không?
6. Đã so sánh enum bằng `==` khi phù hợp chưa?
7. Có null input cần xử lý trước khi gọi method/switch không?
8. Có nhầm `==` enum với `==` String không?
9. Có dùng `name()` làm persisted key mà không có migration strategy không?
10. Có dùng `ordinal()` làm stable external ID không? Nếu có, cần sửa.
11. Có cần explicit stable business code field không?
12. Các code fields có unique và valid không?
13. Mã external khi không khớp được xử lý rõ ràng không?
14. `toString()` là label/diagnostic hay identifier? Đã phân biệt chưa?
15. Có sử dụng `values()` đúng khi cần mọi constants không?
16. Có hiểu `values()` trả array mới nhưng elements canonical không?
17. Có hiểu `valueOf` tìm theo tên chính xác và ném exception khi sai không?
18. Constructor enum có access private/package-private phù hợp không?
19. Có tránh tự gọi `new EnumType()` không?
20. Constructor arguments có đúng signature/type không?
21. Có static initialization dependencies vòng tròn dễ gây lỗi không?
22. Có tránh tham chiếu static enum fields chưa initialized trong constructor không?
23. State của hằng nên là `final` và immutable không?
24. Có mutable referents cần defensive copy không?
25. Có mutable enum state cần thread-safety không?
26. Có thực sự cần constant-specific class body hay switch rõ ràng hơn?
27. Nếu constant-specific body, code có dùng `getDeclaringClass()` khi cần enum type không?
28. Các `switch` có xử lý đúng constants và thay đổi sau này không?
29. Có tận dụng `EnumSet`/`EnumMap` khi phù hợp không?
30. Có phụ thuộc iteration order/ordinal mà không chủ động định nghĩa domain order không?
31. Data serialization/ORM mapping có chịu được rename/add/remove/reorder constants không?
32. Có phân biệt class-loader identity với một global singleton “mọi JVM” không?
33. Có tránh gắn per-request/per-user mutable data vào enum constants không?
34. Có cần sealed hierarchy/records cho payload động thay vì enum không?
35. Các chương trình thử nghiệm có compile đúng `--release 17` và stdout xác định không?

## 88. Tóm tắt cốt lõi

- **Khai báo enum constants** bằng danh sách tên ở đầu enum body, ví dụ `enum Direction { NORTH, SOUTH }`.
- **Mỗi tên hằng biểu diễn một enum object riêng**, có identity ổn định trong enum type runtime tương ứng; các references đến cùng hằng so sánh bằng `==` là true.
- **`name()` là tên khai báo**, **`ordinal()` là vị trí zero-based**, **`toString()` là chuỗi có thể tùy chỉnh**. Không thay thế lẫn nhau.
- **`values()` tạo mảng mới nhưng không tạo hằng mới**. **`valueOf(name)` trả lại chính constant canonical**.
- Enum constants có thể mang dữ liệu qua **private constructors**, fields và methods; hai constants có cùng code field vẫn là hai objects khác identity.
- Một hằng có **constant-specific body** có runtime anonymous subclass; `getDeclaringClass()` mới là cách rõ để lấy enum type gốc.
- **EnumSet** và **EnumMap** tận dụng enum keys/elements và duyệt theo declaration order.
- **Không lưu ordinal như stable business ID**; dùng explicit code khi cần. Không đồng nhất enum identity với mutable field values hay UI labels.
- Enum hỗ trợ identity/serialization/initialization semantics đặc biệt, nhưng **mutable fields không tự bất biến hay thread-safe**.
- Khi giá trị có payload tùy biến cho từng request, cân nhắc một immutable record/sealed hierarchy thay vì ép per-request state vào shared enum constant.

**Kết luận:** Sức mạnh của enum không nằm ở việc thay String bằng những chữ viết hoa, mà ở việc Java bảo đảm một **tập constant objects có type và identity rõ ràng**. Hiểu đúng identity của từng hằng giúp chọn phép so sánh, thiết kế constructor, lưu dữ liệu, xử lý switch và đồng bộ trạng thái một cách an toàn.

## Tham khảo chuẩn Java SE 17

- **Java Language Specification `8.9 — Enum Classes`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- **JLS `8.9.1 — Enum Constants`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.1
- **JLS `8.9.2 — Enum Body Declarations`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.2
- **`java.lang.Enum` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html
- **`java.util.EnumSet` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html
- **`java.util.EnumMap` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html
