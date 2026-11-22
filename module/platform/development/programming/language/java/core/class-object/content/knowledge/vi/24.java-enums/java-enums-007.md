# Enum: values(), valueOf(), name() và ordinal() trong Java

> **Java Core → Class/Object → Enum**  
> **Phạm vi chính:** bốn API `values()`, `valueOf()`, `name()`, `ordinal()`, cách chúng liên hệ với identity và thứ tự enum constants.  
> **Môi trường:** Java 17+; các ví dụ độc lập có lệnh `javac`/`java` và stdout cố định.

## 1. Tổng quan: bốn thao tác làm bốn việc khác nhau

Một `enum` là một kiểu đặc biệt biểu diễn tập named constants được khai báo trong source:

~~~java
enum Direction {
    NORTH, EAST, SOUTH, WEST
}
~~~

Với `Direction`:

| API | Mục đích chính | Ví dụ và kết quả |
| --- | --- | --- |
| `Direction.values()` | Lấy **mảng chứa tất cả enum constants**, theo thứ tự khai báo | `[NORTH, EAST, SOUTH, WEST]` |
| `Direction.valueOf("EAST")` | Tra constant bằng **đúng tên khai báo** | `Direction.EAST` |
| `Direction.EAST.name()` | Đọc **tên định danh** của một constant | `"EAST"` |
| `Direction.EAST.ordinal()` | Đọc **vị trí** trong thứ tự khai báo, bắt đầu từ 0 | `1` |

Những thao tác này **không tạo thêm enum constant instance**. `values()` tạo/trả một array mới chứa references đến các constants đã có; `valueOf()` trả existing constant tương ứng; `name()` trả String name; `ordinal()` trả primitive int.

Đặc biệt:

- `name()` dùng tên chính xác khai báo trong source, **không phụ thuộc override `toString()`**.
- `valueOf()` match theo tên chính xác, **case-sensitive**, không tự dùng display label.
- `ordinal()` là vị trí phụ thuộc thứ tự khai báo, **không phải business/database ID ổn định**.
- `values()` trả một mảng riêng cho mỗi lần gọi, nhưng **các phần tử vẫn là references tới canonical enum constants**.

Đây là các quy tắc đầu tiên cần phân biệt khi làm menu, xử lý input, lưu enum vào database, switch, collections, hoặc test.

## 2. Bắt đầu từ identity và tập constants

Trong Java, một enum constant là một object có reference identity cố định trong một runtime enum class. Với:

~~~java
Direction a = Direction.NORTH;
Direction b = Direction.NORTH;
~~~

`a == b` là true. Cả hai references trỏ đến cùng `Direction.NORTH`, không phải hai object riêng có chung nội dung.

### 2.1. `values()` không tạo lại các instances

~~~java
Direction[] first = Direction.values();
Direction[] second = Direction.values();

System.out.println(first == second);   // false
System.out.println(first[0] == second[0]); // true
~~~

**Mảng mới** và **enum instances mới** là hai chuyện khác nhau. `first != second` vì `values()` trả array riêng; `first[0] == second[0]` vì cả hai phần tử trỏ cùng constant NORTH.

### 2.2. `valueOf()` cũng trả về canonical constant

~~~java
Direction parsed = Direction.valueOf("NORTH");
System.out.println(parsed == Direction.NORTH); // true
~~~

`valueOf` tra cứu declared constant, không gọi enum constructor để tạo object mới.

### 2.3. `null` không phải một enum constant

Một biến kiểu enum là reference variable nên có thể giữ null:

~~~java
Direction value = null;
~~~

Điều này **không thêm “giá trị null” vào `Direction.values()`**. Khi gọi instance method như `value.name()` hoặc `value.ordinal()` với variable null, sẽ có `NullPointerException`; xử lý null theo contract của API bạn thiết kế.

### 2.4. Enum và so sánh `==`

Vì constants là canonical objects, dùng `==` để so hai enum references có type thích hợp thường đơn giản, rõ ràng và an toàn cả khi một operand null:

~~~java
Direction direction = null;
System.out.println(direction == Direction.NORTH); // false
~~~

Ngược lại, gọi `direction.equals(Direction.NORTH)` sẽ ném NPE nếu direction null. `Enum.equals` là final và so theo identity; không thể override để thay semantics của equality.

## 3. `values()` — lấy các constants theo thứ tự khai báo

`values()` là **static method được khai báo ngầm cho từng enum type** theo Java language rules. Với `Direction`, chữ ký tương đương:

~~~java
public static Direction[] values()
~~~

Bạn gọi nó bằng **tên enum class**:

~~~java
Direction[] all = Direction.values();
~~~

### 3.1. Thứ tự là declaration order

Nếu khai báo:

~~~java
enum State {
    NEW, ACTIVE, PAUSED, CLOSED
}
~~~

thì `State.values()` trả references theo thứ tự:

~~~text
[NEW, ACTIVE, PAUSED, CLOSED]
~~~

Không sắp xếp alphabetical, không dựa trên `toString()`, không dựa trên database ID hoặc hash order.

Thứ tự này chính là thứ tự mà `ordinal()` phản ánh.

### 3.2. Mảng có thể sửa, nhưng không thay enum declaration

~~~java
State[] values = State.values();
values[0] = State.CLOSED;
~~~

Dòng này **hợp lệ** vì array elements có thể gán lại. Nhưng chỉ sửa chính array do caller giữ. Lần gọi `State.values()` tiếp theo vẫn đưa `NEW` ở index 0. Bạn không sửa static enum constants, không đổi ordinal, cũng không chèn thêm constants.

### 3.3. `values()` được gọi nhiều lần và allocation

Java language rules yêu cầu trả array riêng mỗi lần gọi. Với enum nhỏ, chi phí thường không đáng kể. Nhưng trong một hot loop gọi `values()` hàng triệu lần, tạo nhiều arrays có thể phát sinh allocation overhead.

Nếu chỉ cần duyệt tập constants nhiều lần, có thể giữ một private cache array **không để lộ quyền sửa array đó**. Đối với public API, không nên trả trực tiếp một cached mutable array; caller có thể thay elements và làm hỏng nội dung cache.

Ví dụ thiết kế có chủ đích:

~~~java
enum Mode {
    OFF, ON;

    private static final Mode[] CACHE = values();

    static int count() {
        return CACHE.length;
    }
}
~~~

Đây là declaration fragment; method `count()` chỉ trả size, không làm lộ array. Nếu muốn public List bất biến để dùng lại, có thể tạo:

~~~java
private static final java.util.List<Mode> ALL =
        java.util.List.of(values());
~~~

Với enum Mode trong fragment, `List.of(values())` nhận array được trải thành elements của varargs; List chứa constants và không cho mutate cấu trúc. Cần cân nhắc rằng việc giữ một List cố định cũng là một API/desgin choice: tránh copy mỗi lần dùng nhưng bảo đảm không lộ mutable backing array.

### 3.4. Không dùng `values()` như một registry động

Ngay cả khi người dùng tự thêm tên mới qua form, `values()` vẫn trả tập values được khai báo trong enum source. Muốn các trạng thái có thể đăng ký tại runtime, phải dùng một abstraction khác như record/value class, Map registry hoặc interface implementations.

## 4. Chương trình hoàn chỉnh 1 — bốn API và hai mức identity

Tạo tệp **`EnumCoreMethodsDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumCoreMethodsDemo {
    enum Direction {
        NORTH, EAST, SOUTH, WEST
    }

    public static void main(String[] args) {
        Direction[] first = Direction.values();
        Direction[] second = Direction.values();

        System.out.println("All = " + Arrays.toString(first));
        System.out.println("Name = " + Direction.EAST.name());
        System.out.println("Ordinal = " + Direction.EAST.ordinal());
        System.out.println("Parsed = " + Direction.valueOf("WEST"));
        System.out.println("Same constant = "
                + (Direction.valueOf("NORTH") == Direction.NORTH));

        System.out.println("Different arrays = " + (first != second));
        System.out.println("Same elements = "
                + (first[0] == second[0]));

        first[0] = Direction.SOUTH;
        System.out.println("First array changed = "
                + Arrays.toString(first));
        System.out.println("New values unchanged = "
                + Direction.values()[0]);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 EnumCoreMethodsDemo.java
java EnumCoreMethodsDemo
~~~

**Stdout chính xác:**

~~~text
All = [NORTH, EAST, SOUTH, WEST]
Name = EAST
Ordinal = 1
Parsed = WEST
Same constant = true
Different arrays = true
Same elements = true
First array changed = [SOUTH, EAST, SOUTH, WEST]
New values unchanged = NORTH
~~~

### 4.1. Đọc kỹ ba phép so sánh

- `first != second`: **array identity** khác nhau.
- `first[0] == second[0]`: **enum constant identity** giống nhau.
- `Direction.valueOf("NORTH") == Direction.NORTH`: phép lookup trả canonical constant.

### 4.2. Vì sao mảng first có SOUTH ở hai vị trí?

Ban đầu first là [NORTH, EAST, SOUTH, WEST]. Gán `first[0] = Direction.SOUTH` làm first thành [SOUTH, EAST, SOUTH, WEST]. Array cho phép repeated references. Nhưng enum declaration vẫn có bốn named constants distinct; `Direction.values()` mới vẫn theo declaration order.

### 4.3. Vì sao không in hashCode?

`Enum.hashCode()` identity-based, nhưng numeric value không có đầu ra cố định để dạy về enum method. Các test nên dùng identity `==` và thứ tự declaration thay vì so hash codes.

## 5. `valueOf(String)` — tra chính xác theo tên

Mỗi enum type có static method `valueOf(String)` được khai báo ngầm. Ví dụ:

~~~java
Direction direction = Direction.valueOf("SOUTH");
~~~

Kết quả là `Direction.SOUTH`, **không** là một object Direction mới.

### 5.1. Exact name, phân biệt hoa/thường

`Direction.valueOf("EAST")` hợp lệ. `Direction.valueOf("east")` không tự uppercase, và `Direction.valueOf("East")` cũng không tự chuyển thành EAST.

Nếu tên không trùng constant đã khai báo, method ném **`IllegalArgumentException`**.

### 5.2. Không tự trim

`Direction.valueOf("EAST ")` không khớp `EAST` vì có dấu cách thừa. Nếu input từ form/API có whitespace, cần xử lý normalize rõ trước khi lookup, khi nghiệp vụ cho phép.

### 5.3. Đối số null

`Direction.valueOf(null)` ném **`NullPointerException`**, không trả null, không trả một constant đặc biệt và không tự chọn giá trị mặc định.

### 5.4. `valueOf()` dùng `name()`, không dùng `toString()`

Nếu một constant override `toString()` để hiển thị "Chưa giao", bạn vẫn phải dùng declared name như `PENDING` khi gọi `valueOf`.

### 5.5. Không có lookup một phần

`valueOf("RE")` không tự chọn `RED` hay `READ` theo prefix; `valueOf` không phải fuzzy parser, không hỗ trợ aliases, lower-case, dịch tiếng Việt hay wildcards.

### 5.6. Ngoại lệ là một phần hợp đồng

Khi input không đáng tin, đừng mặc định mọi chuỗi đều đúng. API có thể:

- Để `IllegalArgumentException` đi lên nếu input sai là lỗi lập trình.
- Catch exception và trả `Optional<E>` nếu unknown là trường hợp bình thường.
- Chuyển thành domain validation error cho HTTP 400.
- Map aliases qua một explicit map để hỗ trợ external codes.
- Reject null bằng `Objects.requireNonNull` hoặc trả Optional.empty tùy thiết kế.

Cần tránh bắt mọi `RuntimeException` rồi coi là input sai: điều này có thể che giấu lỗi khác ngoài enum parsing.

## 6. `Enum.valueOf(Class<T>, String)` — biến thể generic

Ngoài `Direction.valueOf(String)` do compiler cung cấp cho từng enum, Java có static generic method trên `java.lang.Enum`:

~~~java
Direction result =
        Enum.valueOf(Direction.class, "EAST");
~~~

Method dạng khái niệm:

~~~java
public static <T extends Enum<T>> T valueOf(
        Class<T> enumClass, String name)
~~~

Hai APIs trả về cùng constant khi arguments hợp lệ:

~~~java
Direction a = Direction.valueOf("EAST");
Direction b = Enum.valueOf(Direction.class, "EAST");
System.out.println(a == b); // true
~~~

### 6.1. Khi nào dùng từng dạng?

- **Có sẵn enum type tại compile time:** `Direction.valueOf("EAST")` dễ đọc và ngắn.
- **Viết utility generic cho bất kỳ enum type:** `Enum.valueOf(enumType, input)` hữu ích khi có `Class<E>` token.

### 6.2. Type parameter và type safety

Ràng buộc `E extends Enum<E>` cho phép utility generic giữ kết quả type `E`, không cần ép kiểu từ Object. Đừng xóa type information một cách không cần thiết bằng raw `Class` hoặc casts không kiểm soát.

### 6.3. Null class token

`Enum.valueOf(null, "EAST")` không có enum Class hợp lệ; không dùng null class token. Một generic parser nên validate `Class<E>` argument. Đối với non-enum Class được đưa vào qua raw/unchecked code, API không thể hoạt động như enum lookup hợp lệ.

## 7. Chương trình hoàn chỉnh 2 — parsing hợp lệ, unknown, case và null

Tạo tệp **`EnumValueOfDemo.java`**:

~~~java
public class EnumValueOfDemo {
    enum Mode {
        READ_ONLY, EDIT
    }

    public static void main(String[] args) {
        Mode direct = Mode.valueOf("EDIT");
        Mode generic = Enum.valueOf(Mode.class, "READ_ONLY");

        System.out.println("Direct = " + direct);
        System.out.println("Generic = " + generic);
        System.out.println("Canonical = "
                + (direct == Mode.EDIT));

        try {
            Mode.valueOf("edit");
        } catch (IllegalArgumentException ex) {
            System.out.println("Lowercase rejected");
        }

        try {
            Mode.valueOf("UNKNOWN");
        } catch (IllegalArgumentException ex) {
            System.out.println("Unknown rejected");
        }

        try {
            Mode.valueOf(null);
        } catch (NullPointerException ex) {
            System.out.println("Null rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumValueOfDemo.java
java EnumValueOfDemo
~~~

**Stdout chính xác:**

~~~text
Direct = EDIT
Generic = READ_ONLY
Canonical = true
Lowercase rejected
Unknown rejected
Null rejected
~~~

### 7.1. Vì sao bắt các exception cụ thể?

`"edit"` và `"UNKNOWN"` là String non-null không khớp named constants, nên dùng `IllegalArgumentException`. `null` là argument không hợp lệ riêng, nên code bắt `NullPointerException`. Demo in thông báo tự đặt **ổn định**, thay vì in raw exception message có thể thay tùy JVM.

### 7.2. `toString()` mặc định

Trong demo Mode không override toString, nên `System.out.println(direct)` in "EDIT". Phần sau sẽ cho thấy tên in ra có thể khác `name()` nếu override toString.

### 7.3. Normalization phải có chủ đích

Nếu muốn người dùng nhập `" edit "` và được hiểu là EDIT, có thể xử lý:

~~~java
Mode parsed =
        Mode.valueOf(
                input.trim().toUpperCase(java.util.Locale.ROOT));
~~~

Đây là **fragment**, giả định input non-null và normalize kiểu này phù hợp với domain. `Locale.ROOT` làm việc uppercase có hành vi ngôn ngữ ổn định hơn default locale; tuy nhiên normalization không biến unknown value thành hợp lệ và có thể gây collision khi aliases khác nhau. Mã hóa external protocol có thể dùng code mapping riêng thay vì dựa trên source names.

## 8. `name()` — tên khai báo của enum constant

`name()` là **instance method final** kế thừa từ `java.lang.Enum`. Nó trả về **exact identifier name** mà constant đã được khai báo trong source.

~~~java
enum Transport {
    TRAIN, BUS, AIRPLANE
}
~~~

`Transport.TRAIN.name()` trả `"TRAIN"`. Với `Transport.AIRPLANE.name()`, kết quả `"AIRPLANE"`.

### 8.1. Name là identifier, không phải display label

Tên enum thường theo naming convention uppercase + underscore, nhưng UI có thể cần tiếng Việt, khoảng trắng, accent, hoặc text phụ thuộc locale. Không nên buộc UI display name phải giống identifier.

Có thể thêm một field `label`:

~~~java
enum DeliveryStatus {
    PENDING("Chưa giao"),
    DELIVERED("Đã giao");

    private final String label;

    DeliveryStatus(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }
}
~~~

`DeliveryStatus.PENDING.name()` vẫn là `"PENDING"`, còn `label()` trả `"Chưa giao"`.

### 8.2. `name()` không thể override

`Enum.name()` được khai báo final. Một enum không thể định nghĩa lại method `name()` với cùng signature để thay text:

~~~java
enum Broken {
    A;

    @Override
    public String name() { // Cố ý không biên dịch.
        return "Alias";
    }
}
~~~

Nếu muốn custom name, hãy dùng `label()`, `code()`, `displayName()` hoặc override `toString()` nếu phù hợp.

### 8.3. Khi lưu text lâu dài cần tính phiên bản

Dùng `name()` trong database/file có thể chấp nhận được nếu bạn coi **tên constant là protocol identifier và không đổi nó tùy tiện**. Nếu rename enum constant sau khi đã lưu string cũ, `valueOf(oldName)` sẽ thất bại khi đọc dữ liệu cũ.

Với dữ liệu bên ngoài có stability requirements, một explicit stable code field thường an toàn hơn:

~~~java
PENDING("P", "Chưa giao")
~~~

Tên Java constant có thể refactor còn stable code vẫn giữ theo contract. Việc chọn name hay code cần thống nhất và có migration strategy.

### 8.4. `name()` khác `getDeclaringClass()`

`name()` cho biết **tên constant**. `getDeclaringClass()` cho biết **enum type khai báo constant**. Nếu constant có class body riêng, runtime class của constant có thể là anonymous subclass; điều đó không đổi `name()`.

## 9. `toString()` có thể khác `name()`

Mặc định `Enum.toString()` trả cùng nội dung với `name()`. Nhưng `toString()` **không final** và có thể override trong enum.

Đây là một nguyên nhân lớn khiến developer dùng nhầm `valueOf(displayLabel)`.

### 9.1. Chương trình hoàn chỉnh 3 — name, display label và valueOf

Tạo tệp **`EnumNameToStringDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumNameToStringDemo {
    enum DeliveryStatus {
        PENDING("Chưa giao"),
        DELIVERED("Đã giao");

        private final String label;

        DeliveryStatus(String label) {
            this.label = label;
        }

        String label() {
            return label;
        }

        @Override
        public String toString() {
            return label;
        }
    }

    public static void main(String[] args) {
        DeliveryStatus status = DeliveryStatus.PENDING;

        System.out.println("name = " + status.name());
        System.out.println("toString = " + status.toString());
        System.out.println("label = " + status.label());
        System.out.println("values display = "
                + Arrays.toString(DeliveryStatus.values()));

        System.out.println("valueOf name = "
                + DeliveryStatus.valueOf("DELIVERED").name());

        try {
            DeliveryStatus.valueOf("Đã giao");
        } catch (IllegalArgumentException ex) {
            System.out.println("Display text rejected");
        }

        System.out.println("same name and display = "
                + status.name().equals(status.toString()));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumNameToStringDemo.java
java EnumNameToStringDemo
~~~

**Stdout chính xác:**

~~~text
name = PENDING
toString = Chưa giao
label = Chưa giao
values display = [Chưa giao, Đã giao]
valueOf name = DELIVERED
Display text rejected
same name and display = false
~~~

### 9.2. `Arrays.toString(values())` gọi phương thức nào?

`Arrays.toString(Object[])` tạo string bằng biểu diễn của elements, trong trường hợp này dùng `toString()` của enum constants. Vì thế output là các labels, **không** là các name() identifiers.

Muốn danh sách tên định danh, lặp và gọi `name()` trực tiếp:

~~~java
for (DeliveryStatus s : DeliveryStatus.values()) {
    System.out.println(s.name());
}
~~~

Đây là fragment sử dụng enum đã khai báo trong demo.

### 9.3. Vì sao `valueOf("Đã giao")` lỗi?

`valueOf` tra tên constant `PENDING` hoặc `DELIVERED`. Nó không lookup chuỗi được `toString()` trả ra. Nếu input từ người dùng là label tiếng Việt, hãy parse thông qua mapping do ứng dụng định nghĩa (và cân nhắc duplicate labels, localization, case sensitivity).

### 9.4. Lúc nào nên override `toString()`?

Có thể hữu ích cho debug-friendly output hoặc human-readable descriptions. Nhưng nếu thư viện/API khác dựa vào `toString()` như identifier (không phải contract chuẩn của `valueOf`), việc override có thể gây bất ngờ. Tách `name()`, `code()` và `displayName()` tường minh thường dễ bảo trì.

## 10. `ordinal()` — vị trí khai báo, bắt đầu từ 0

`ordinal()` là instance method final của `Enum`, trả một `int` tương ứng với **zero-based position** trong enum declaration.

Với:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}
~~~

kết quả:

- `Priority.LOW.ordinal() == 0`
- `Priority.MEDIUM.ordinal() == 1`
- `Priority.HIGH.ordinal() == 2`

Quan hệ với `values()`:

~~~java
Priority[] all = Priority.values();

for (int i = 0; i < all.length; i++) {
    System.out.println(all[i].ordinal() == i);
}
~~~

Mỗi dòng in `true` cho một enum declaration thông thường. Index trong mảng values theo declaration order chính là ordinal.

### 10.1. Không phải số lượng đã được tạo

`ordinal()` không phải instance count, không phải số lần gọi constructor, không phải ID ngẫu nhiên. Nó được gán theo **thứ tự khai báo constants**, không đổi trong quá trình chạy đối với cùng runtime enum type.

### 10.2. Đổi thứ tự làm đổi ordinal

Phiên bản 1:

~~~java
enum StatusV1 {
    OPEN, CLOSED
}
~~~

Phiên bản 2:

~~~java
enum StatusV2 {
    PENDING, OPEN, CLOSED
}
~~~

StatusV1.OPEN có ordinal 0; StatusV2.OPEN có ordinal 1.

Điều này gây rủi ro nếu bạn lưu `ordinal()` vào database: sau khi upgrade và chèn constant mới, dữ liệu cũ có thể map sang trạng thái khác.

### 10.3. Không thể override ordinal

`Enum.ordinal()` là final. Bạn không thể đặt custom ordinal cố định bằng cách override method. Muốn stable numeric code, tạo một `private final int code` và method `code()`.

### 10.4. Mục đích của ordinal trong thư viện

Ordinal hữu ích cho **internal representation** như enum-indexed arrays, `EnumSet`/`EnumMap` và một số algorithms gắn với declaration order khi lifecycle/versioning được kiểm soát. Nhưng exposed persistence/public protocols nên sử dụng stable identifiers hoặc explicit mapping.

### 10.5. `compareTo()` dùng natural order

Enum `compareTo` dựa trên relative ordinal order trong cùng enum type; không phải alphabetical string comparison. Một enum constant ở index trước được coi là nhỏ hơn theo natural enum order.

Không dùng `ordinal()` để suy đoán business ranking nếu declaration order không được định nghĩa như thứ tự nghiệp vụ. Một explicit weight/priority field có thể rõ hơn.

## 11. Chương trình hoàn chỉnh 4 — ordinal thay đổi qua các khai báo phiên bản

Tạo tệp **`EnumOrdinalVersionDemo.java`**:

~~~java
public class EnumOrdinalVersionDemo {
    enum StatusV1 {
        OPEN("O"), CLOSED("C");

        private final String code;

        StatusV1(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    enum StatusV2 {
        PENDING("P"), OPEN("O"), CLOSED("C");

        private final String code;

        StatusV2(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        System.out.println("V1 OPEN ordinal = "
                + StatusV1.OPEN.ordinal());
        System.out.println("V2 OPEN ordinal = "
                + StatusV2.OPEN.ordinal());
        System.out.println("V1 OPEN code = "
                + StatusV1.OPEN.code());
        System.out.println("V2 OPEN code = "
                + StatusV2.OPEN.code());
        System.out.println("V2 PENDING ordinal = "
                + StatusV2.PENDING.ordinal());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumOrdinalVersionDemo.java
java EnumOrdinalVersionDemo
~~~

**Stdout chính xác:**

~~~text
V1 OPEN ordinal = 0
V2 OPEN ordinal = 1
V1 OPEN code = O
V2 OPEN code = O
V2 PENDING ordinal = 0
~~~

### 11.1. Vì sao dùng hai enum types trong demo?

Java không thể đồng thời chạy hai định nghĩa source khác nhau của cùng enum class trong một cách biên dịch đơn giản. Demo dùng StatusV1 và StatusV2 để **mô phỏng** thay đổi thứ tự/constants giữa hai versions.

Ý tưởng về persistence giữ nguyên: dựa vào index 0 của phiên bản trước có thể làm dữ liệu map sai ở phiên bản sau, trong khi code "O" vẫn giữ được ý nghĩa OPEN nếu bạn duy trì mã ổn định.

### 11.2. Stable code cũng có trách nhiệm phiên bản

Một explicit field `code="O"` chỉ ổn định nếu developer cam kết không đổi nó hoặc có migration rõ ràng. Java không tự bảo đảm uniqueness/stability của arbitrary business codes; cần validate duplicates và tests.

## 12. Quan hệ giữa `values()` và `ordinal()`

Có một bất biến cơ bản:

Với từng constant c trong enum E, `E.values()[c.ordinal()] == c` đúng khi dùng array mới từ values theo declaration order.

Điều này là nền tảng giúp EnumSet/EnumMap có thể biểu diễn data compactly.

### 12.1. Chương trình hoàn chỉnh 5 — iteration và EnumSet/EnumMap

Tạo tệp **`EnumIterationCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumIterationCollectionsDemo {
    enum Stage {
        NEW, RUNNING, DONE
    }

    public static void main(String[] args) {
        for (Stage stage : Stage.values()) {
            System.out.println(
                    stage.name() + ":" + stage.ordinal());
        }

        EnumSet<Stage> selected =
                EnumSet.of(Stage.DONE, Stage.NEW);

        EnumMap<Stage, Integer> order =
                new EnumMap<>(Stage.class);
        order.put(Stage.DONE, 3);
        order.put(Stage.RUNNING, 2);
        order.put(Stage.NEW, 1);

        System.out.println("Set = " + selected);
        System.out.println("Map = " + order);
        System.out.println("Index matches = "
                + (Stage.values()[Stage.RUNNING.ordinal()]
                        == Stage.RUNNING));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumIterationCollectionsDemo.java
java EnumIterationCollectionsDemo
~~~

**Stdout chính xác:**

~~~text
NEW:0
RUNNING:1
DONE:2
Set = [NEW, DONE]
Map = {NEW=1, RUNNING=2, DONE=3}
Index matches = true
~~~

### 12.2. Tại sao Set/Map có thứ tự như vậy?

`EnumSet` và `EnumMap` iterate theo natural enum order, tức **declaration order**, không theo thứ tự insert. `EnumSet.of(DONE, NEW)` vẫn hiển thị [NEW, DONE]. `EnumMap` cũng duyệt keys theo enum order.

Điều này khác HashMap/HashSet, nơi không nên dựa vào thứ tự iteration ổn định trừ khi loại collection có contract phù hợp.

### 12.3. Giới hạn scope

Một `EnumMap<Stage,Integer>` có keys thuộc chính enum Stage. Không thể thêm dynamic Stage constant. Nếu requirement là arbitrary strings, một ordinary Map theo stable code key có thể phù hợp hơn.

## 13. Parsing dùng name khác với parsing dùng business code

Trong domain thực tế, API có thể nhận:

~~~text
"ready"
"in_progress"
"done"
~~~

trong khi Java enum constants có names:

~~~java
READY, RUNNING, DONE
~~~

Không nên ép external identifiers phải viết y hệt enum Java names, nhất là khi có mobile clients, APIs nhiều phiên bản, database cũ hoặc localization.

### 13.1. Dùng explicit code field

~~~java
enum WorkflowState {
    READY("ready"),
    RUNNING("in_progress"),
    DONE("done");

    private final String code;

    WorkflowState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

Đây là declaration fragment. Mỗi constant có một stable external code do ứng dụng quản lý. Code `"in_progress"` không giống `RUNNING.name()`, cũng không giống `RUNNING.ordinal()`.

### 13.2. Lookup map sau khi constants được khởi tạo

Có thể tạo `Map<String,WorkflowState>` trong static initialization:

~~~java
private static final Map<String, WorkflowState> BY_CODE;

static {
    Map<String, WorkflowState> map = new HashMap<>();
    for (WorkflowState state : values()) {
        if (map.putIfAbsent(state.code, state) != null) {
            throw new IllegalStateException("Duplicate code");
        }
    }
    BY_CODE = Map.copyOf(map);
}
~~~

Đây là enum-member fragment, với imports `Map`/`HashMap`. Xây lookup sau constants đã được khởi tạo tránh dependency order surprises. `Map.copyOf` cho cấu trúc map không sửa được qua BY_CODE; Strings/enums cũng phù hợp làm immutable map keys/values.

### 13.3. Unknown input phải được xử lý rõ

Nếu external code không có trong map, có thể trả `Optional.empty()`, domain error, hoặc một explicit UNKNOWN representation khác nếu data model có. Không dùng `valueOf()` để “tạo custom enum case”.

### 13.4. Null input và Map lookup

Đừng giả định mọi Map implementation chấp nhận `get(null)`. Ví dụ các unmodifiable maps từ `Map.copyOf` không hỗ trợ null keys. Nếu parser contract cho phép null là missing, kiểm tra null **trước khi lookup**.

## 14. Chương trình hoàn chỉnh 6 — lookup stable code bằng Optional

Tạo tệp **`EnumStableCodeDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class EnumStableCodeDemo {
    enum WorkflowState {
        READY("ready"),
        RUNNING("in_progress"),
        DONE("done");

        private final String code;
        private static final Map<String, WorkflowState> BY_CODE;

        static {
            Map<String, WorkflowState> map = new HashMap<>();

            for (WorkflowState state : values()) {
                WorkflowState old =
                        map.putIfAbsent(state.code, state);
                if (old != null) {
                    throw new IllegalStateException("Duplicate code");
                }
            }

            BY_CODE = Map.copyOf(map);
        }

        WorkflowState(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }

        static Optional<WorkflowState> fromCode(String code) {
            if (code == null) {
                return Optional.empty();
            }
            return Optional.ofNullable(BY_CODE.get(code));
        }
    }

    public static void main(String[] args) {
        System.out.println("Name = "
                + WorkflowState.RUNNING.name());
        System.out.println("Code = "
                + WorkflowState.RUNNING.code());
        System.out.println("Lookup = "
                + WorkflowState.fromCode("in_progress"));
        System.out.println("Unknown = "
                + WorkflowState.fromCode("RUNNING"));
        System.out.println("Null = "
                + WorkflowState.fromCode(null));
        System.out.println("Canonical = "
                + (WorkflowState.fromCode("done").orElseThrow()
                        == WorkflowState.DONE));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumStableCodeDemo.java
java EnumStableCodeDemo
~~~

**Stdout chính xác:**

~~~text
Name = RUNNING
Code = in_progress
Lookup = Optional[RUNNING]
Unknown = Optional.empty
Null = Optional.empty
Canonical = true
~~~

### 14.1. Vì sao `fromCode("RUNNING")` là Optional.empty?

BY_CODE dùng `"in_progress"` làm key cho WorkflowState.RUNNING. `"RUNNING"` là `name()`, không phải `code()`. Method `fromCode` không fallback tự động sang Java identifiers.

### 14.2. Vì sao `Optional[RUNNING]` không hiển thị external code?

`Optional.toString()` biểu diễn contained enum object bằng `toString()`; enum trong demo không override toString nên hiển thị `RUNNING`. Không suy rằng Optional dùng String code map key.

### 14.3. Kiểm tra duplicated codes

Static initializer dùng `putIfAbsent` để phát hiện 2 constants mang cùng code. Nếu không kiểm tra, Map.put có thể overwrite silently, làm input external code không còn xác định duy nhất.

### 14.4. Trade-off

Lookup map chiếm thêm một ít memory nhưng có direct lookup theo external code, không cần quét values() mỗi lần. Với enum nhỏ và ít parse, một vòng for đơn giản cũng có thể đủ; lựa chọn dựa trên clarity, validation và workload.

## 15. Biến thể dùng `Class<E>` cho code generic

Khi framework xử lý nhiều enum types khác nhau, ta có thể viết generic utility với `Class<E>`.

`Class.getEnumConstants()` trả array các enum constants của enum class tương ứng, hoặc null nếu Class không biểu diễn enum type. Điều này hữu ích khi bạn có type token ở runtime thay vì biết trực tiếp `SomeEnum.values()` tại compile time.

### 15.1. Chương trình hoàn chỉnh 7 — tiện ích generic

Tạo tệp **`EnumGenericUtilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class EnumGenericUtilityDemo {
    enum Role {
        VIEWER, EDITOR
    }

    enum Severity {
        LOW, HIGH
    }

    static <E extends Enum<E>> List<String> names(Class<E> type) {
        E[] constants = type.getEnumConstants();
        if (constants == null) {
            throw new IllegalArgumentException("Not an enum class");
        }

        List<String> result = new ArrayList<>();
        for (E value : constants) {
            result.add(value.name());
        }
        return List.copyOf(result);
    }

    static <E extends Enum<E>> E lookup(
            Class<E> type, String name) {
        return Enum.valueOf(type, name);
    }

    public static void main(String[] args) {
        System.out.println("Roles = " + names(Role.class));
        System.out.println("Severities = " + names(Severity.class));

        Role chosen = lookup(Role.class, "EDITOR");
        System.out.println("Role = " + chosen);
        System.out.println("Same instance = "
                + (chosen == Role.EDITOR));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumGenericUtilityDemo.java
java EnumGenericUtilityDemo
~~~

**Stdout chính xác:**

~~~text
Roles = [VIEWER, EDITOR]
Severities = [LOW, HIGH]
Role = EDITOR
Same instance = true
~~~

### 15.2. Vì sao cần `<E extends Enum<E>>`?

Ràng buộc generic cho phép Java giữ association giữa type E và enum class Class<E>. Method `lookup` trả E đúng type theo compile-time type inference, tránh raw casts. Nó không cho phép arbitrary class không phải enum lọt vào generic parameter hợp lệ.

### 15.3. Giá trị trả về của `names`

Method thu thập `name()` thành List rồi dùng `List.copyOf` để trả một unmodifiable List snapshot. Nếu chỉ return ArrayList trực tiếp, caller có thể mutate List nhưng cũng không thể thay enum declaration; tuy nhiên immutable return API giúp caller hiểu nó là một danh sách mô tả cố định.

### 15.4. Không phải mọi API generic nên dùng reflection

Nếu bạn chỉ xử lý một enum cụ thể, gọi `Role.values()` hoặc `Role.valueOf(...)` trực tiếp dễ đọc hơn. `Class<E>` và `getEnumConstants()` phù hợp khi code thực sự cần xử lý nhiều enum types.

## 16. Constant-specific class body không phá `name()` và `ordinal()`

Một enum constant có thể khai báo class body riêng để override instance method:

~~~java
enum Operation {
    PLUS {
        @Override
        String symbol() {
            return "+";
        }
    },
    TIMES {
        @Override
        String symbol() {
            return "*";
        }
    };

    abstract String symbol();
}
~~~

Java compiler có thể tạo anonymous constant-specific subclasses. `PLUS.getClass()` khi đó không nhất thiết bằng `Operation.class`, nhưng:

- `PLUS.name()` vẫn là `"PLUS"`.
- `PLUS.ordinal()` vẫn là 0.
- `TIMES.name()` vẫn là `"TIMES"`.
- `TIMES.ordinal()` vẫn là 1.
- `Operation.values()` vẫn trả hai constants theo declaration order.
- `Operation.valueOf("PLUS")` vẫn trả canonical PLUS constant.
- `PLUS.getDeclaringClass()` vẫn là `Operation.class`.

**Đừng nhầm runtime implementation class của constant với declaring enum type.**

### 16.1. `getDeclaringClass()` dùng làm gì?

`Enum.getDeclaringClass()` trả Class object của enum type thực sự đã khai báo constant. Khi constant có class body, `getClass()` trả anonymous subclass, vì vậy `getDeclaringClass()` đáng tin hơn để biết enum type của constant.

### 16.2. Không thể dùng subclass để bổ sung names/ordinals

Client không thể tạo arbitrary subclass và thêm `PLUS2`. Tập enum constants vẫn được đóng trong declaration, nên các method trên có semantics cố định cho mỗi compiled enum version.

## 17. Chương trình hoàn chỉnh 8 — constant-specific behavior và metadata

Tạo tệp **`EnumConstantBodyMethodsDemo.java`**:

~~~java
public class EnumConstantBodyMethodsDemo {
    enum Operation {
        PLUS {
            @Override
            String symbol() {
                return "+";
            }
        },
        TIMES {
            @Override
            String symbol() {
                return "*";
            }
        };

        abstract String symbol();
    }

    public static void main(String[] args) {
        Operation plus = Operation.PLUS;

        System.out.println("name = " + plus.name());
        System.out.println("ordinal = " + plus.ordinal());
        System.out.println("symbol = " + plus.symbol());
        System.out.println("same class = "
                + (plus.getClass() == Operation.class));
        System.out.println("declaring class = "
                + plus.getDeclaringClass().getSimpleName());
        System.out.println("parsed identity = "
                + (Operation.valueOf("PLUS") == plus));
        System.out.println("values length = "
                + Operation.values().length);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumConstantBodyMethodsDemo.java
java EnumConstantBodyMethodsDemo
~~~

**Stdout chính xác:**

~~~text
name = PLUS
ordinal = 0
symbol = +
same class = false
declaring class = Operation
parsed identity = true
values length = 2
~~~

### 17.1. Có hai loại “tên” khác nhau

`plus.name()` trả named constant PLUS. `plus.getDeclaringClass().getSimpleName()` trả tên enum type Operation. Nếu mục đích là lưu một reference có enum type và enum constant name, hãy xem cả hai thay vì dùng raw runtime subclass name.

### 17.2. Tránh hard-code synthetic class names

Compiler có thể tạo class file kiểu `Operation$1` cho constant body, nhưng tên synthetic artifact không phải một stable public API. Không lưu hoặc so sánh nó trong business code.

### 17.3. Vì sao ordinal vẫn 0?

Ordinal đi theo **vị trí constant trong declaration**, không phụ thuộc việc constant có riêng class body hay override method.

## 18. Kết hợp bốn API với switch trong Java 17

Enum type có một tập declared constants giúp `switch` dễ đọc và có thể exhaustively cover tất cả cases.

~~~java
enum Signal {
    STOP, WAIT, GO
}

static String instruction(Signal signal) {
    return switch (signal) {
        case STOP -> "stop";
        case WAIT -> "wait";
        case GO -> "move";
    };
}
~~~

Đây là declaration/method fragments (chưa là standalone file). `switch` sử dụng enum constant cases, không cần `ordinal()` hoặc `name()` làm intermediate key.

### 18.1. Không switch theo ordinal nếu muốn readability

Code như:

~~~java
switch (signal.ordinal()) {
    case 0 -> ...
    case 1 -> ...
}
~~~

dễ sai khi reorder constants. Hãy switch trực tiếp trên enum values. Nếu cần custom stable numeric codes, parse code thành enum trước rồi switch trên enum.

### 18.2. Với switch expression, cần exhaustive cases

Trong Java 17, switch expression trên một enum có thể không cần `default` nếu đã cover mọi constant theo compiler's exhaustiveness rules. Nếu bạn thêm một constant mới ở version sau, khi recompile code có thể yêu cầu bổ sung case mới. Đây là lợi ích của enum như một closed set of cases.

### 18.3. Null vẫn cần xử lý

`null` không phải một enum constant. Trong Java 17, switch expression với null không được xử lý như một constant enum case thông thường và thường ném `NullPointerException` nếu chưa kiểm tra null. Nếu API cho phép missing value, xử lý trước khi switch.

## 19. Chương trình hoàn chỉnh 9 — switch với enum, không dùng ordinal

Tạo tệp **`EnumSwitchDemo.java`**:

~~~java
public class EnumSwitchDemo {
    enum Signal {
        STOP, WAIT, GO
    }

    static String instruction(Signal value) {
        if (value == null) {
            return "missing";
        }

        return switch (value) {
            case STOP -> "stop";
            case WAIT -> "wait";
            case GO -> "move";
        };
    }

    public static void main(String[] args) {
        for (Signal value : Signal.values()) {
            System.out.println(
                    value.name() + " => " + instruction(value));
        }

        System.out.println("Null => " + instruction(null));
        System.out.println("Parse => "
                + instruction(Signal.valueOf("GO")));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumSwitchDemo.java
java EnumSwitchDemo
~~~

**Stdout chính xác:**

~~~text
STOP => stop
WAIT => wait
GO => move
Null => missing
Parse => move
~~~

### 19.1. Vì sao case names không cần `Signal.STOP`?

Trong switch trên enum type, case labels có syntax dành cho enum constants. Compiler biết type từ switch expression, nên có thể viết `case STOP`.

### 19.2. Vì sao không viết `case 0`?

Signal là enum type, không phải int. `ordinal()` là một field-like method kết quả int phục vụ metadata/ordering; không biến enum thành numeric primitive.

## 20. Bẫy với enum không có constant nào

Java cho phép khai báo một enum **không có constants**:

~~~java
enum Empty {
    ;
}
~~~

`Empty.values()` trả một array length 0. `Empty.valueOf("ANY")` sẽ ném IllegalArgumentException vì không có named constants. Không có instance `Empty` hợp lệ để gọi `name()` hay `ordinal()`.

### 20.1. Vì sao có enum rỗng?

Trong một số patterns, enum rỗng có thể dùng như non-instantiable namespace/container cho static utility methods hoặc là một type được định nghĩa trước khi có variants, nhưng với mục tiêu business enumerated states, enum rỗng thường không có ích.

### 20.2. Không giả định luôn có phần tử đầu tiên

`E.values()[0]` có thể ném ArrayIndexOutOfBoundsException nếu enum E rỗng. Khi viết generic enum utilities, kiểm tra length trước khi lấy phần tử đầu hoặc dùng logic cho empty case.

### 20.3. Không thể `new Empty()` để tạo constant thứ nhất

Empty là enum, vẫn chịu restrictions về instance creation; không thể bổ sung phần tử bằng new.

## 21. Static initialization và `values()`

Enum constants được khởi tạo theo một trình tự đặc biệt khi enum class initialization diễn ra. Với field metadata trong constructors và static lookup maps, cần hiểu initialization ordering.

### 21.1. Xây map sau khi constants có mặt

Một pattern đúng:

~~~java
enum Code {
    A("a"),
    B("b");

    final String text;
    private static final java.util.Map<String, Code> LOOKUP;

    static {
        java.util.Map<String, Code> tmp = new java.util.HashMap<>();
        for (Code c : values()) {
            tmp.put(c.text, c);
        }
        LOOKUP = java.util.Map.copyOf(tmp);
    }

    Code(String text) {
        this.text = text;
    }
}
~~~

Static block được chạy sau enum constant initialization, nên có thể dùng `values()` để dựng table.

### 21.2. Đừng truy cập nonconstant static field của chính enum từ constructor

Java có một restriction đặc biệt: enum constructor/instance initializer/instance variable initializer không được tham chiếu trực tiếp đến một static field của chính enum trừ khi field là constant variable.

Cố ý không biên dịch:

~~~java
enum Bad {
    A, B;

    static int created;

    Bad() {
        created++; // Illegal reference to static field from enum initializer.
    }
}
~~~

Nếu cần count of constants, `values().length` trong static context là cách rõ ràng. Nếu cần runtime metric mutable, chọn holder/service có lifecycle và concurrency policy thay vì ép enum constructor can thiệp vào static field của chính nó.

### 21.3. Avoid static initialization cycles

Dù các rules bảo vệ một số tình huống, static initialization có thể phức tạp nếu nhiều classes/enums gọi lẫn nhau khi class initialization chưa hoàn tất. Giữ metadata constructors đơn giản, fields immutable khi có thể, và xây lookup tables sau constants.

## 22. Hiệu năng và chi phí của bốn API

| API | Ý nghĩa chi phí thông thường | Nên làm gì |
| --- | --- | --- |
| `values()` | Tạo array chứa references tới mọi constants, copy danh sách refs O(n) | Với hot path và enum lớn, cân nhắc cache immutable view |
| `valueOf(name)` | Tra trong metadata/map enum constants, trả existing constant | Dùng trực tiếp cho exact-name lookup |
| `name()` | Trả String name metadata của constant | Dùng khi cần declared identifier |
| `ordinal()` | Trả int vị trí metadata | Dùng nội bộ theo declaration order, tránh persistence ID |

Không cần tối ưu quá sớm. Enum thường nhỏ; `values()` trong setup code, test hoặc thao tác UI không phải hotspot đáng lo. Ưu tiên correctness và clarity trước.

### 22.1. `values()` trong nested loops

Nếu cần iterate nhiều lần, bạn có thể:

~~~java
Direction[] directions = Direction.values();
for (int i = 0; i < 100; i++) {
    for (Direction direction : directions) {
        // Do something with each direction.
    }
}
~~~

Đây là fragment. Nó chỉ gọi values một lần. Nhưng đừng đưa `directions` mutable array ra public API nếu muốn tránh callers sửa thứ tự/nội dung refs.

### 22.2. `name()` không phải free localization

Nếu mỗi lần render UI lại tự ánh xạ name sang bản dịch, có thể dùng `ResourceBundle`/localization service theo locale. Enum name chỉ là một stable identifier trong compiled source cho đến khi developer đổi code.

### 22.3. `ordinal()` không cho tốc độ mà đủ lý do hi sinh schema stability

Dù ordinal là int tiện cho array indexing, dùng nó làm external ID có thể tạo lỗi migration đắt đỏ khi reorder constants. Chọn explicit code khi dữ liệu vượt ranh giới của compiled code version.

## 23. Sai lầm phổ biến và cách sửa

1. **Nghĩ `values()` trả List.** Thực tế trả `E[]` array; dùng `Arrays.asList`/`List.of` khi cần List semantics phù hợp.
2. **Nghĩ `values()` tạo các enum objects mới.** Nó trả array mới chứa canonical references.
3. **Sửa array `values()` rồi nghĩ enum declaration bị thay.** Chỉ caller-owned array bị sửa.
4. **Nghĩ `valueOf()` parse lowercase tự động.** Exact case-sensitive match.
5. **Nghĩ `valueOf()` trim input.** Không; spaces làm string khác.
6. **Truyền null cho `valueOf()` rồi kỳ vọng trả null.** Nó ném NullPointerException.
7. **Nghĩ `valueOf("UNKNOWN")` tạo unknown enum constant.** Không; IllegalArgumentException.
8. **Truyền label từ `toString()` vào `valueOf()`.** Lookup dùng declared name().
9. **Suy rằng `name()` có thể override.** Nó final.
10. **Suy rằng `ordinal()` có thể override thành business ID.** Nó final.
11. **Dùng ordinal làm database ID.** Reorder hoặc insert constants làm đổi mapping.
12. **Dùng `toString()` làm stable protocol ID vô điều kiện.** Có thể override/localize.
13. **Dùng `name()` làm protocol nhưng rename constant không migration.** Dữ liệu cũ có thể không parse được.
14. **Dùng `ordinal()` để switch.** Switch trực tiếp theo enum values rõ ràng và ít lỗi hơn.
15. **Nghĩ `ordinal()` là số lần enum instance được tạo.** Nó là declaration position.
16. **Nghĩ `EnumSet`/`EnumMap` iterate theo insertion order.** Chúng dùng natural enum order.
17. **Dùng `HashMap` rồi kỳ vọng natural enum order.** Chọn EnumMap nếu keys là enum và semantics phù hợp.
18. **Cho rằng `getClass() == E.class` đúng cho mọi constant.** Constant-specific bodies có anonymous subclasses.
19. **Không dùng `getDeclaringClass()` khi cần enum declaring type.** Đây là API đúng ý nghĩa đó.
20. **Tự tạo enum bằng `new` trong factory.** Không thể; chỉ chọn existing constants.
21. **Quên rằng biến enum có thể null.** `name()/ordinal()` trên null ném NPE.
22. **Gọi `values()[0]` cho enum rỗng.** Có thể ném ArrayIndexOutOfBoundsException.
23. **Đưa mutable cached values array cho caller.** Có thể làm bẩn cache application.
24. **Không kiểm tra duplicate stable codes trong lookup map.** Parser có thể mapping nhầm.
25. **Dùng Map.copyOf và gọi get(null) không kiểm tra.** Những unmodifiable maps không nhận null key.
26. **Catch mọi RuntimeException khi parse.** Dễ che lỗi khác; catch đúng IllegalArgumentException cho unknown, xử lý null riêng.
27. **Tạo heavy allocations để micro-optimize sai chỗ.** Dùng profiling nếu performance là yêu cầu thực sự.
28. **Không xét source version khi thêm/rename constants.** Exhaustive switches và persisted names cần review.
29. **Nghĩ Enum.valueOf generic và E.valueOf khác semantics lookup.** Cả hai trả canonical constant theo declared name.
30. **Không phân biệt enum name, display text, external stable code, ordinal.** Bốn khái niệm phục vụ bốn nhu cầu khác nhau.

## 24. Bảng quyết định API theo tình huống

| Tình huống | Lựa chọn phù hợp | Tránh nhầm lẫn |
| --- | --- | --- |
| Hiển thị tất cả lựa chọn enum trên form | `E.values()` để iterate constants | Values trả array, không phải registry runtime |
| Đọc giá trị do code/config ghi đúng tên Java constant | `E.valueOf(name)` | Phải exact, case-sensitive |
| Viết parser dùng nhiều enum types | `Enum.valueOf(Class<E>, name)` | Cần type token và validation |
| Lấy tên source identifier để log/debug | `constant.name()` | Không phải localized display label |
| Hiển thị tên thân thiện cho người dùng | `label()/displayName()` hoặc localization | Không dựa vào name/ordinal |
| Sắp xếp theo thứ tự khai báo | `values()`/natural enum ordering | Order thay nếu declaration reorder |
| Dùng ordinal để index bảng nội bộ có cùng enum version | `constant.ordinal()` khi thật sự cần | Không lưu ordinal dài hạn |
| Lưu ID ổn định qua nhiều deploy | Explicit `code()`/mapping | Không dùng ordinal |
| Parse stable external code | `fromCode` qua Map | Không phụ thuộc source enum names |
| Đối chiếu cùng constant | `==` | Không cần value-based custom equals |
| Enum constant có riêng class body | `getDeclaringClass()` cho declaring enum | `getClass()` có thể khác |
| Tập constants rỗng | `values().length == 0` | Không truy cập values()[0] |

## 25. Bài tập luyện tập có đáp án

**Câu 1.** `enum E {A, B, C}` có mấy elements trong `E.values()`?

**Đáp án:** Ba, lần lượt A, B, C theo declaration order.

**Câu 2.** `E.A.ordinal()` bằng bao nhiêu?

**Đáp án:** 0.

**Câu 3.** `E.C.ordinal()` bằng bao nhiêu?

**Đáp án:** 2.

**Câu 4.** Hai lời gọi `E.values() == E.values()` trả gì?

**Đáp án:** False, vì mỗi call trả array object riêng.

**Câu 5.** `E.values()[0] == E.A` trả gì?

**Đáp án:** True.

**Câu 6.** Sửa `E[] arr = E.values(); arr[0]=E.C;` có thay declaration không?

**Đáp án:** Không, chỉ array arr bị sửa; lần values() mới vẫn bắt đầu bằng A.

**Câu 7.** `E.valueOf("B") == E.B` trả gì?

**Đáp án:** True.

**Câu 8.** `E.valueOf("b")` có tự uppercase thành B không?

**Đáp án:** Không, ném IllegalArgumentException.

**Câu 9.** `E.valueOf(" B ")` có tự trim không?

**Đáp án:** Không; không khớp name và ném IllegalArgumentException.

**Câu 10.** `E.valueOf(null)` có trả null không?

**Đáp án:** Không, ném NullPointerException.

**Câu 11.** `E.valueOf("UNKNOWN")` có tạo một enum constant mới không?

**Đáp án:** Không, ném IllegalArgumentException.

**Câu 12.** `E.A.name()` trả gì?

**Đáp án:** String "A", là declared constant identifier.

**Câu 13.** Có thể override `name()` để trả label không?

**Đáp án:** Không, method final.

**Câu 14.** Có thể override `toString()` không?

**Đáp án:** Có; khi đó `toString()` có thể khác `name()`.

**Câu 15.** Nếu toString trả "Đẹp", `valueOf("Đẹp")` có lookup constant đó không?

**Đáp án:** Không nếu "Đẹp" không chính là declared constant name. `valueOf` dùng declared name.

**Câu 16.** `ordinal()` là thứ tự tạo objects theo thời gian?

**Đáp án:** Không, là zero-based declaration index.

**Câu 17.** Nếu chèn constant mới vào đầu enum, ordinal các constants sau có đổi không?

**Đáp án:** Có, khi biên dịch phiên bản enum mới.

**Câu 18.** Có nên dùng ordinal làm permanent DB code?

**Đáp án:** Không, dùng explicit stable code nếu cần persistence.

**Câu 19.** `Enum.valueOf(E.class, "B")` có trả cùng object như `E.valueOf("B")` không?

**Đáp án:** Có, cùng canonical constant.

**Câu 20.** Khi viết generic enum utility, `<T extends Enum<T>>` giúp gì?

**Đáp án:** Giữ type safety giữa Class<T> token và giá trị T được lookup.

**Câu 21.** `EnumMap` duyệt theo insertion order không?

**Đáp án:** Không; natural enum order theo declaration order.

**Câu 22.** `EnumSet.of(C, A)` thường iterate theo thứ tự nào trong `enum E{A,B,C}`?

**Đáp án:** [A, C].

**Câu 23.** Constant-specific enum class body có thể khiến `constant.getClass()` khác E.class không?

**Đáp án:** Có, do compiler-generated anonymous subclass.

**Câu 24.** Khi cần enum type của constant, nên dùng gì?

**Đáp án:** `constant.getDeclaringClass()`.

**Câu 25.** `name()` của constant có body riêng có đổi theo subclass name không?

**Đáp án:** Không, vẫn là named constant.

**Câu 26.** `ordinal()` của constant có body riêng có bị reset theo anonymous subclass không?

**Đáp án:** Không, vẫn theo thứ tự constants trong declaring enum.

**Câu 27.** Với enum rỗng, `values().length` trả gì?

**Đáp án:** 0.

**Câu 28.** Với enum rỗng, `values()[0]` có hợp lệ không?

**Đáp án:** Có thể biên dịch nhưng ném ArrayIndexOutOfBoundsException khi chạy.

**Câu 29.** Dùng `List.copyOf` trên list chứa mutable element objects có deep-copy objects không?

**Đáp án:** Không. Đây là structural copy, nên phải xét mutable elements riêng.

**Câu 30.** Dùng stable code field thì có được miễn kiểm tra uniqueness không?

**Đáp án:** Không, code uniqueness/migration là business invariant cần bảo đảm.

**Câu 31.** Vì sao không nên catch RuntimeException chung khi parse?

**Đáp án:** Nó có thể che giấu code bugs khác; phân biệt unknown name và null/input validation.

**Câu 32.** Nếu muốn hiển thị enum label bằng tiếng Việt và lưu stable code, dùng cùng `ordinal()` được không?

**Đáp án:** Không nên; tạo fields riêng `displayName` và `code`, giữ ordinal cho vị trí khai báo.

## 26. Bài tập thực hành có gợi ý

### Bài 1 — đọc metadata không thay đổi constants

Viết enum `MonthPart {START, MIDDLE, END}`, dùng `values()` để in theo thứ tự. Kiểm tra `name()` và `ordinal()`. Sau đó thay phần tử đầu trong array returned by values; gọi values lần hai và giải thích vì sao source constants không đổi.

**Gợi ý:** Tách identity của array và identity của enum constant. Dùng `==` để test references và `Arrays.toString` cho list values.

### Bài 2 — parser chấp nhận case-insensitive input

Viết `parseMode(String input)` nhận `" on "` và trả `Mode.ON`. Kiểm tra null/blank/unknown. Đừng đổi semantics của `Mode.valueOf`; normalize **trước** khi gọi và xử lý invalid values riêng.

**Gợi ý:** `trim()`, `toUpperCase(Locale.ROOT)` và try/catch `IllegalArgumentException`. Nếu input=null, reject hoặc return Optional.empty theo contract.

### Bài 3 — stable external code

Viết enum `PaymentState` với names `PENDING`/`PAID`/`FAILED` và stable codes `P`/`D`/`F`. Tạo lookup Map, validate duplicated code, và thử refactor display labels mà không làm code mapping đổi.

**Gợi ý:** Static Map được dựng sau constants; mỗi code là immutable String field.

### Bài 4 — ordinal regression test

Tạo một test cho enum `Severity`, assert `Severity.HIGH.ordinal()==2` khi order là LOW, MEDIUM, HIGH. Sau đó chèn INFO trước LOW. Quan sát test thất bại; thay use case persistence bằng explicit stable code.

**Gợi ý:** Không dùng ordinal test làm căn cứ cho business ID nếu bạn muốn thứ tự declarations có thể thay đổi.

### Bài 5 — enum có constant body riêng

Tạo enum Operation với ADD/SUB có method apply riêng. In `name()`, `ordinal()`, `getClass()==Operation.class` và `getDeclaringClass()==Operation.class`. Giải thích phần nào phản ánh constant identity, phần nào phản ánh compiler-generated implementation class.

**Gợi ý:** Constant-specific body không thêm mới named enum instances.

## 27. Checklist dùng enum API trong dự án

1. Đã phân biệt `values()` trả array với `valueOf()` trả one constant chưa?
2. Có hiểu `values()` trả array mới nhưng elements là canonical references không?
3. Có dùng `==` khi muốn so cùng enum constant không?
4. Có xử lý nullable enum variable trước khi gọi name()/ordinal() không?
5. Có dựa vào declaration order của values đúng phạm vi không?
6. Có tránh sửa một cached mutable array làm ảnh hưởng global cache không?
7. Có biết `valueOf()` exact case-sensitive lookup không?
8. Có trim/normalize input chỉ khi business contract cho phép không?
9. Có xử lý unknown name bằng IllegalArgumentException đúng cách không?
10. Có xử lý null name rõ ràng không?
11. Có dùng `Enum.valueOf(Class<E>,name)` khi utility generic cần type token không?
12. Có phân biệt `name()` với `toString()` và display label không?
13. Có tránh override name()/ordinal() final methods không?
14. Có nhớ ordinal bắt đầu từ 0 và thay khi reorder constants không?
15. Có tránh dùng ordinal làm stable DB ID không?
16. Có explicit stable codes nếu external protocol yêu cầu không?
17. Có validation duplicate codes/unknown codes ở code-map parser không?
18. Có phân biệt EnumMap/EnumSet iteration order với HashMap/HashSet không?
19. Có switch trên enum trực tiếp thay vì trên ordinal không?
20. Có biết constant-specific subclass khiến getClass khác getDeclaringClass không?
21. Có xử lý enum rỗng khi writing generic utilities không?
22. Có tránh lưu compiler synthetic class names không?
23. Có xét versioning khi đổi tên/thêm enum constants không?
24. Có tránh micro-optimization thiếu profiling đối với values() không?
25. Có unit tests cho exact names, codes, unknown/null inputs và ordinal migration risks không?

## 28. Kết luận

Bốn API enum quen thuộc có bốn trách nhiệm rõ ràng:

- **`values()`:** liệt kê các named constants trong declaration order; trả **một array mới** chứa **references tới những constants có sẵn**.
- **`valueOf(name)`:** tra đúng **declared constant name**; trả canonical enum instance, phân biệt hoa/thường, unknown ném IllegalArgumentException và null ném NullPointerException.
- **`name()`:** lấy identifier name của constant; method final, không bị thay bởi override toString.
- **`ordinal()`:** lấy zero-based declaration position; method final, hữu ích cho ordering/implementation details nhưng **không phải external ID ổn định**.

Đừng gộp những khái niệm **source name**, **display label**, **external stable code**, **declaration index** và **runtime object identity** thành một. Khi cần UI, dùng label/localization; khi cần parse declared names, dùng valueOf; khi cần storage lâu dài, chọn stable code có validation; khi cần duyệt constants, dùng values; khi cần natural enum order, hiểu đúng ordinal mà không để nó rò thành một database contract dễ vỡ.

Đó là cách sử dụng enum vừa đúng cú pháp Java 17+, vừa dễ bảo trì khi source code và dữ liệu ứng dụng thay đổi theo thời gian.
