# Trường, phương thức và nhà máy static trong record (Java hiện đại)

## 1. Hiểu đúng phạm vi của record

Record là một loại lớp Java dùng để biểu diễn một **bộ giá trị được mô tả công khai bằng các component**. Tên, kiểu và thứ tự component nằm trong **record header**; body có thể chứa constructor, phương thức và các thành viên `static`. Đây là nền tảng để tổ chức record vừa ngắn gọn vừa có logic nghiệp vụ rõ ràng.

~~~java
record Point(int x, int y) {
    // Body có thể để trống hoặc thêm các member được phép.
}
~~~

`Point` có hai component `x` và `y`. Java cung cấp các field tương ứng, accessor `x()` và `y()`, canonical constructor `Point(int x, int y)`, cùng các phương thức giá trị `equals`, `hashCode`, `toString` nếu không có khai báo tường minh phù hợp.

**Phạm vi kiến thức còn áp dụng:** Java 14 giới thiệu records ở dạng preview; Java 16 chuẩn hóa record thành tính năng chính thức (JEP 395). Nội dung và mã của bài sử dụng **Java 17+**, không dựa vào cú pháp preview hay cờ `--enable-preview`. Quy tắc dưới đây tiếp tục áp dụng cho Java hiện đại.

Mục tiêu học tập:
- Phân biệt **component field do compiler tạo**, **field `static` do lập trình viên khai báo**, và **instance field bị cấm** trong record body.
- Biết cách viết **instance method**, **static method** và phương thức accessor tường minh.
- Hiểu **static factory method** là gì, dùng nó để đặt tên cách tạo record và xử lý/chuyển đổi đầu vào thế nào.
- Biết giới hạn quan trọng: **static factory không thay thế hoặc ẩn được canonical constructor `public` của một `public record`**.
- Thiết kế validation và bảo toàn bất biến (*invariants*) của record khi người gọi chọn cả `new` lẫn factory.

## 2. Trường trong record: cái nào có, cái nào được phép khai báo?

Xét khai báo:

~~~java
public record UserId(String value) {}
~~~

Về mặt mô hình ngôn ngữ, Java cung cấp một **component field** có tên `value` và kiểu `String`, tương tự:

~~~java
// Mô tả khái niệm; KHÔNG chép nguyên vào body của record.
private final String value;
~~~

Field đó là **`private`, `final`, không `static`**, và được Java tạo từ header. Người dùng không thể sửa nó sau khi record xây dựng xong; ngoài record, đọc qua accessor `userId.value()`. Trong body record, phương thức instance có thể đọc `value` hoặc `this.value`.

### 2.1. Ba nhóm trường dễ nhầm

| Loại | Ví dụ | Hợp lệ? | Ai sở hữu / ý nghĩa |
| --- | --- | --- | --- |
| Component field ngầm định | `record UserId(String value) {}` | Có | Compiler cung cấp field `private final value` từ header |
| Field `static` trong body | `private static final int LIMIT = 100;` | Có | Một field thuộc **lớp record**, không thuộc từng instance |
| Field `static` chứa hằng record | `public static final UserId UNKNOWN = new UserId("unknown");` | Có | Một đối tượng dùng chung, an toàn khi trạng thái thực sự bất biến |
| Field instance tự khai báo thêm | `private int attempts;` trong body | **Không** | Record không cho phép khai báo thêm field không `static` |
| Field instance `final` tự khai báo thêm | `private final int cache = 0;` trong body | **Không** | Thêm `final` không làm ngoại lệ được chấp nhận |

Quy tắc quan trọng: **tập instance state của record được quyết định hoàn toàn bởi header**. Không thể thêm field instance ẩn trong body dù field đó là `private`, `final` hay chỉ dùng để cache.

Ví dụ sai (chỉ minh họa lỗi biên dịch):

~~~java
record Wrong(String name) {
    private int visits;        // Sai: instance field tự khai báo.
    private final int id = 1; // Sai: cũng là instance field.
}
~~~

Nếu `visits` hay `id` thật sự là thành phần của giá trị, hãy đưa chúng vào header; nếu đó là trạng thái thay đổi riêng của từng đối tượng sau khi tạo, một **class thông thường** có thể phù hợp hơn.

### 2.2. `static` không tham gia vào giá trị của từng record

~~~java
record Size(int width, int height) {
    private static final String UNIT = "px";

    String label() {
        return width + "x" + height + UNIT;
    }
}
~~~

`UNIT` là field `static` dùng chung. Nó **không** xuất hiện trong canonical constructor, các accessor component, hay cơ chế mặc định của `equals`/`hashCode`/`toString`. Hai `Size` có cùng `width` và `height` được coi là bằng nhau theo mặc định, bất kể chúng gọi `label()` bao nhiêu lần.

Java cũng **cho phép field `static` có thể thay đổi**, nhưng không nên lưu dữ liệu nghiệp vụ mutable dùng chung chỉ để làm record “có trạng thái”. Dữ liệu mutable toàn cục có thể dẫn tới race condition và làm kết quả các phương thức phụ thuộc vào trạng thái bên ngoài, khiến record kém dễ đoán. Ưu tiên các hằng thực sự bất biến hoặc thành viên dùng chung không có side effect.

### 2.3. Static initializer có được phép không?

Có. Record body có thể có **static initializer**, giống class thường:

~~~java
record Code(String value) {
    private static final String PREFIX;

    static {
        PREFIX = "CODE-";
    }

    String formatted() {
        return PREFIX + value;
    }
}
~~~

Đây là một type hoàn chỉnh. `static { ... }` chạy khi lớp được khởi tạo, **không chạy mỗi lần tạo record**. Nếu chỉ cần gán hằng đơn giản, viết `private static final String PREFIX = "CODE-";` dễ đọc hơn.

**Khác biệt:** `static { ... }` hợp lệ; **instance initializer** độc lập `{ ... }` trong record body **không hợp lệ**. Việc kiểm tra/chuẩn hóa component thuộc về canonical constructor.

## 3. Phương thức instance trong record

Record **có thể khai báo instance methods** giống class bình thường, miễn không vi phạm các hạn chế của record. Thêm method để diễn đạt **hành vi suy ra từ component** hoặc tạo **record mới** là kiểu thiết kế thường gặp.

~~~java
record Rectangle(int width, int height) {
    long area() {
        return (long) width * height;
    }

    boolean isSquare() {
        return width == height;
    }

    Rectangle resized(int newWidth, int newHeight) {
        return new Rectangle(newWidth, newHeight);
    }
}
~~~

Đây là một type Java độc lập. Sau khi tạo `Rectangle r = new Rectangle(4, 5)`:
- `r.area()` trả `20L`; ép kiểu `(long)` trước khi nhân để tính theo kiểu `long`.
- `r.isSquare()` trả `false`.
- `r.resized(6, 6)` **trả một record mới**, không sửa `r`.

`area()` và `isSquare()` là method, không phải component: chúng không tự tạo field mới, không có tham số trong canonical constructor và không trở thành một phần riêng biệt trong `equals` mặc định. Nếu có logic dễ suy ra từ component, giữ dưới dạng phương thức giúp tránh dữ liệu lưu trữ dư thừa.

### 3.1. Truy cập field và accessor từ method

Trong body record, một instance method có thể đọc component field trực tiếp (`width`, `this.width`) hoặc gọi accessor (`width()`). Bên ngoài record, caller phải dùng accessor vì component field là `private`.

Ví dụ:

~~~java
Rectangle r = new Rectangle(4, 5);
System.out.println(r.width()); // 4
// System.out.println(r.width); // Không hợp lệ bên ngoài record.
~~~

Đây là đoạn sử dụng type `Rectangle` đã khai báo trước đó.

### 3.2. Có thể khai báo accessor tường minh

Nếu cần xử lý cụ thể khi truy cập component, bạn có thể khai báo tường minh đúng tên và kiểu:

~~~java
record Label(String text) {
    public String text() {
        return text;
    }
}
~~~

Accessor của record phải là **`public`**, không nhận tham số, và có kiểu trả về trùng component. Ở ví dụ đơn giản trên, việc tự viết accessor là **không cần thiết** vì compiler sinh ra cùng hành vi. Nó hữu ích hơn khi phải **sao chép phòng vệ** một mảng component lúc trả ra.

Hãy bảo toàn hợp đồng giá trị của record: accessor cần phản ánh hợp lý component mà record công bố. Tránh viết accessor đánh tráo hoặc tạo giá trị không nhất quán với trạng thái, vì nó có thể làm hỏng kỳ vọng khi tái tạo record từ các accessor.

### 3.3. Method trong record không được là `abstract` hay `native`

Record là **implicitly final**: không có lớp con để triển khai abstract instance method. Đặc tả Java cũng cấm khai báo method `abstract` hoặc `native` trong record body. Các method thông thường (`public`, `private`, `static`, v.v.) vẫn dùng theo quy tắc tương ứng.

Record có thể `implements` interface và triển khai method được yêu cầu. Ví dụ `record Score(int value) implements Comparable<Score>` hợp lệ khi body cung cấp `compareTo` đúng hợp đồng.

## 4. Phương thức `static` trong record

Phương thức `static` thuộc **lớp record**, không thuộc một instance cụ thể. Gọi trực tiếp qua tên type:

~~~java
record Distance(int meters) {
    static Distance ofKilometers(int kilometers) {
        return new Distance(Math.multiplyExact(kilometers, 1_000));
    }

    int toCentimeters() {
        return Math.multiplyExact(meters, 100);
    }
}
~~~

Đây là một record hoàn chỉnh. Trong cùng package, có thể dùng `Distance.ofKilometers(2)` để nhận record có `meters() == 2000`; sau đó gọi `distance.toCentimeters()` để nhận `200000`. Hai hướng gọi khác nhau:

| Cách gọi | Thuộc loại | Có `this`? | Thường dùng cho |
| --- | --- | --- | --- |
| `Distance.ofKilometers(2)` | `static` method | Không | Factory, phép chuyển đổi đầu vào, tiện ích ở cấp type |
| `distance.toCentimeters()` | Instance method | Có | Hành vi trên component của một instance |
| `distance.meters()` | Accessor instance | Có | Đọc component |
| `Distance.ZERO` (nếu khai báo) | `static` field | Không | Giá trị/hằng dùng chung |

Bên trong `static` method **không có `this`**. Nếu cần đọc component, phải có đối tượng cụ thể và gọi accessor của đối tượng đó hoặc truy cập hợp lệ qua đối tượng. Nếu muốn dùng tham số kiểu của **generic record** trong `static` method, hãy khai báo tham số kiểu của **chính phương thức static**; xem phần 8.

## 5. Static factory method: một cách tạo record có tên

**Static factory method** là phương thức `static` trả về một đối tượng (ở đây thường là một record) thay vì là constructor. Nó có **tên biểu đạt ý định** và có thể biến đổi, chuẩn hóa hoặc chọn nguồn dữ liệu trước khi tạo đối tượng.

Ví dụ các tên rõ nghĩa:

- `ofCents(long cents)`: dữ liệu đầu vào đã ở đơn vị cent.
- `ofUnits(long units)`: đầu vào ở đơn vị chính, cần chuyển sang cent.
- `from(...)`: tạo từ một biểu diễn khác.
- `parse(String text)`: phân tích chuỗi thành đối tượng, nếu API có nhu cầu này.

Tên `of`, `from` hoặc `parse` chỉ là **quy ước API**, Java không tự sinh chúng cho record và không mặc định gọi factory thay constructor.

~~~java
record Temperature(double celsius) {
    static Temperature ofCelsius(double value) {
        return new Temperature(value);
    }

    static Temperature fromFahrenheit(double value) {
        return new Temperature((value - 32) * 5 / 9);
    }
}
~~~

`Temperature.ofCelsius(25)` và `Temperature.fromFahrenheit(77)` đều tạo record có component `celsius` xấp xỉ `25`. Đây là minh họa cho **cách đặt tên factory**; mã số thực dùng `double` nên có thể chịu sai số số học dấu phẩy động.

### 5.1. Ưu điểm thực tế của factory

Factory có thể:
1. **Đặt tên cho đơn vị hay dạng đầu vào** thay vì dùng nhiều constructor với tham số có cùng kiểu nhưng khác ý nghĩa.
2. **Chuyển đổi dữ liệu** trước khi gọi canonical constructor.
3. **Trả về instance có sẵn** nếu record thực sự immutable và có chính sách tái sử dụng phù hợp (ví dụ `ZERO`).
4. **Xử lý từ nhiều nguồn** như chuỗi, cấu hình, kiểu khác, để các đường tạo dữ liệu kết thúc ở cùng constructor kiểm tra bất biến.
5. **Giữ một nơi xử lý ý định của API**, giúp tên lời gọi thể hiện rõ nguồn dữ liệu.

Factory không bắt buộc phải tạo instance mới mỗi lần; hợp đồng API nên nêu rõ nếu người dùng có lý do quan tâm tới danh tính đối tượng. Với record mang ngữ nghĩa **giá trị**, so sánh qua `equals` thường phù hợp hơn so sánh tham chiếu bằng `==`.

### 5.2. Giới hạn bắt buộc: không thể bắt người dùng chỉ đi qua factory của `public record`

Một điểm khác với nhiều class thường:

~~~java
public record Amount(long cents) {
    public Amount {
        if (cents < 0) {
            throw new IllegalArgumentException("negative cents");
        }
    }

    public static Amount ofCents(long cents) {
        return new Amount(cents);
    }
}
~~~

Với một **`public record`**, canonical constructor phải có mức truy cập `public`. Không thể làm canonical constructor `private` chỉ để buộc người dùng gọi `Amount.ofCents(...)`.

Người gọi có quyền dùng **cả** `new Amount(100)` **và** `Amount.ofCents(100)`. Vì vậy, **validation quan trọng phải nằm trong canonical constructor**, được thực hiện cho mọi đường khởi tạo. Nếu chỉ kiểm tra ở factory, lệnh `new Amount(...)` có thể bỏ qua kiểm tra và tạo record không hợp lệ.

Đối với record **không `public`** hoặc record lồng nhau có mức truy cập hẹp hơn, có thể có các quy tắc truy cập canonical constructor khác; đừng khái quát rằng *mọi* record đều luôn có constructor `public`. Quy tắc chính xác là canonical constructor phải có mức truy cập **ít nhất bằng record**.

## 6. Ví dụ hoàn chỉnh: field `static`, instance methods và factory

Chương trình sau cố ý kết hợp cả ba nhóm thành viên trên một record nhỏ, có **bất biến rõ ràng**: số cent không âm. Để tránh lỗi làm tròn khi biểu diễn số tiền, ví dụ lưu **đơn vị nhỏ nhất bằng `long`**, không dùng `double` để cộng tiền.

Lưu nguyên chương trình thành **`RecordMembersDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class RecordMembersDemo {
    public record Money(long cents) {
        private static final long CENTS_PER_UNIT = 100L;
        public static final Money ZERO = new Money(0);

        public Money {
            if (cents < 0) {
                throw new IllegalArgumentException("cents must be nonnegative");
            }
        }

        public static Money ofCents(long cents) {
            return new Money(cents);
        }

        public static Money ofUnits(long units) {
            return new Money(Math.multiplyExact(units, CENTS_PER_UNIT));
        }

        public Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            return new Money(Math.addExact(cents, other.cents()));
        }

        public String display() {
            return String.format(Locale.ROOT, "%d.%02d",
                    cents / 100, cents % 100);
        }

        public boolean isZero() {
            return cents == 0;
        }
    }

    public static void main(String[] args) {
        Money first = Money.ofUnits(3);
        Money second = Money.ofCents(250);
        Money total = first.plus(second);

        System.out.println("First: " + first.display());
        System.out.println("Second: " + second.display());
        System.out.println("Total: " + total.display());
        System.out.println("Component: " + total.cents());
        System.out.println("Constant: " + Money.ZERO.display());
        System.out.println("Is zero: " + Money.ZERO.isZero());
        System.out.println("Factory equals new: "
                + Money.ofCents(250).equals(new Money(250)));

        try {
            Money.ofCents(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("Negative rejected: true");
        }
        try {
            new Money(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("Constructor rejected: true");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 RecordMembersDemo.java
java RecordMembersDemo
~~~

**Stdout chính xác:**

~~~text
First: 3.00
Second: 2.50
Total: 5.50
Component: 550
Constant: 0.00
Is zero: true
Factory equals new: true
Negative rejected: true
Constructor rejected: true
~~~

### 6.1. Phân loại từng member trong `Money`

| Member / cú pháp | Loại | Trách nhiệm |
| --- | --- | --- |
| `long cents` trong header | Component | Mô tả instance state; Java tạo field `private final` và accessor `cents()` |
| `CENTS_PER_UNIT` | `private static final` field | Hằng tỷ lệ chuyển đổi dùng chung |
| `ZERO` | `public static final` field | Instance có giá trị `0` được chia sẻ |
| `public Money { ... }` | Compact canonical constructor | Chặn `cents < 0` cho **mọi** đường tạo record |
| `ofCents` | Static factory | Tạo record từ số cent |
| `ofUnits` | Static factory | Đổi số đơn vị chính sang cent có kiểm tra tràn |
| `plus` | Instance method | Cộng giá trị và trả record mới |
| `display` | Instance method | Định dạng giá trị theo quy ước ví dụ |
| `isZero` | Instance method | Tính predicate từ component |
| `cents()` | Accessor do Java sinh | Đọc giá trị component |

Không có instance field mới nào được thêm trong body. `ZERO` là một đối tượng `Money` dùng chung; bởi `Money` chỉ giữ `long` và không chứa mutable reference nên chia sẻ `ZERO` không tạo rò rỉ dữ liệu có thể sửa.

### 6.2. Vì sao kết quả là `5.50`?

`ofUnits(3)` gọi `Math.multiplyExact(3, 100)` nên tạo `new Money(300)`. `ofCents(250)` tạo `new Money(250)`. `plus` lấy `300 + 250 = 550` bằng `Math.addExact` rồi tạo **Money mới**, không sửa hai đối tượng đầu. `display()` định dạng `550 / 100 = 5` và phần dư `50` thành chuỗi `"5.50"`.

`Math.multiplyExact` và `Math.addExact` ném `ArithmeticException` khi phép tính `long` bị tràn; dùng chúng giúp tránh việc tràn số âm thầm tạo kết quả sai. Đây là hành vi chuẩn của Java hiện đại.

### 6.3. Kiểm tra bất biến ở cả hai đường tạo

- `Money.ofCents(-1)` → factory gọi `new Money(-1)` → canonical constructor ném `IllegalArgumentException`.
- `new Money(-1)` → chính canonical constructor ném **cùng loại ngoại lệ**.
- `Money.ofCents(250).equals(new Money(250))` → `true` nhờ `equals` do record sinh theo **component `cents`**, không dựa vào static fields hay cách tạo đối tượng.

Nếu chỉ đặt kiểm tra `cents < 0` trong `ofCents`, người gọi vẫn có thể chạy `new Money(-1)`. Đó là lý do canonical constructor mới là ranh giới đáng tin cậy để giữ bất biến.

### 6.4. Điều kiện phụ thuộc hợp đồng nghiệp vụ

`Money` trong ví dụ chỉ minh họa **giá trị không âm ở cùng một đơn vị quy ước** và phép cộng. Nó chưa mô hình hóa mã tiền tệ hoặc chuyển đổi tỷ giá; dùng nhiều đơn vị thực tế cần định nghĩa loại đơn vị/currency trong component và quy tắc cộng tương thích. Không tự hiểu chuỗi `"5.50"` là một định dạng tiền tệ đầy đủ cho tất cả locale.

## 7. Factory và constructor bổ sung: giống nhau ở đâu, khác nhau ở đâu?

| Khía cạnh | Canonical constructor | Constructor overload | Static factory |
| --- | --- | --- | --- |
| Tên | Trùng tên record | Trùng tên record | Tên method tùy thiết kế (`of`, `from`, `parse`) |
| Kiểu lời gọi | `new R(components)` | `new R(otherArgs)` | `R.of(...)` |
| Kết quả | Luôn tạo instance được khởi tạo | Ủy quyền tới constructor cùng record | Có thể tạo hoặc trả instance có sẵn |
| Ràng buộc đặc biệt | Nhận toàn bộ component theo thứ tự header | Phải bắt đầu bằng `this(...)` theo luật constructor | Không cần `this(...)`, nhưng phải giữ hợp đồng dữ liệu |
| Có thể là `static`? | Không | Không | Có, bắt buộc |
| Có tên ý nghĩa về nguồn dữ liệu? | Hạn chế | Hạn chế vì cùng tên record | Có |

Ví dụ kết hợp constructor overload và factory:

~~~java
record Meter(int value) {
    Meter {
        if (value < 0) {
            throw new IllegalArgumentException("negative length");
        }
    }

    Meter() {
        this(0); // Constructor overload phải ủy quyền.
    }

    static Meter fromCentimeters(int centimeters) {
        if (centimeters % 100 != 0) {
            throw new IllegalArgumentException("not a whole meter");
        }
        return new Meter(centimeters / 100);
    }
}
~~~

Record trên là một **type hoàn chỉnh**: `new Meter()` nhận `0`; `Meter.fromCentimeters(300)` nhận `3`. Factory có thể biểu đạt rõ **quy tắc chuyển đổi dữ liệu** và ném lỗi đối với đầu vào không đại diện được bằng kiểu đích. Cả constructor overload lẫn factory đều cuối cùng dùng canonical constructor giữ bất biến.

## 8. Trường hợp generic record: static factory có tham số kiểu riêng

Một `record` có thể là generic:

~~~java
record Box<T>(T value) {
    static <T> Box<T> of(T value) {
        return new Box<>(value);
    }

    boolean hasValue() {
        return value != null;
    }
}
~~~

Câu lệnh `Box<String> box = Box.of("hello");` hợp lệ. Điểm cần nhớ: `T` của **record generic** gắn với instance, trong khi **static method không được sử dụng trực tiếp tham số kiểu của record**. Vì thế factory phải khai báo **`static <T>`**: đây là tham số kiểu **riêng của phương thức** (tên có thể trùng `T` vì chúng ở phạm vi khác nhau).

Ví dụ **sai**:

~~~java
record BadBox<T>(T value) {
    // Sai: method static sử dụng T của record mà không tự khai báo.
    // static BadBox<T> of(T value) { return new BadBox<>(value); }
}
~~~

Ví dụ `BadBox` ở trên biên dịch được **khi giữ dòng sai ở dạng comment**; bỏ comment sẽ gây lỗi “non-static type variable ... cannot be referenced from a static context” hoặc thông báo tương đương. Cần viết `static <T> BadBox<T> of(T value)`.

**Đừng nhầm** `Box<T>` là component. `T` là tham số kiểu ở khai báo record; `value` mới là component duy nhất.

## 9. Thiết kế API rõ ràng và giữ record đúng vai trò

### 9.1. Factory làm rõ đầu vào, constructor giữ chuẩn trạng thái

~~~java
record UserCode(String value) {
    UserCode {
        if (value == null) {
            throw new IllegalArgumentException("missing code");
        }
        value = value.strip().toUpperCase(java.util.Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank code");
        }
    }

    static UserCode of(String input) {
        return new UserCode(input);
    }
}
~~~

Ví dụ này cho thấy chuẩn hóa trong **canonical constructor**. Cả `UserCode.of(" ab ")` và `new UserCode(" ab ")` tạo record có `value()` bằng `"AB"`. Nếu factory riêng còn thực hiện parse phức tạp, hãy để constructor tiếp tục bảo đảm các điều kiện không thể vi phạm.

### 9.2. Không thêm setter hay mutable instance state

~~~java
record Position(int x, int y) {
    Position move(int dx, int dy) {
        return new Position(
                Math.addExact(x, dx),
                Math.addExact(y, dy)
        );
    }
}
~~~

Đây là một type hoàn chỉnh. `move` tạo instance mới; không có method `setX` âm thầm sửa field `final`. Nếu thực sự cần một đối tượng liên tục thay đổi trạng thái theo thời gian, cân nhắc **class thông thường**.

### 9.3. Chọn `static` constant có ý nghĩa

Hằng kiểu nguyên thủy hoặc `String` `static final` là lựa chọn đơn giản. Nếu `static final` trỏ tới **một đối tượng mutable** (ví dụ một `ArrayList`), `final` vẫn **không chặn chỉnh sửa nội dung**. Khi công bố hằng record, hãy bảo đảm chính các component của record không làm rò rỉ dữ liệu mutable. Ví dụ `public static final Money ZERO` an toàn vì chỉ chứa `long`; một record có `byte[]` cần defensive copy ở constructor và accessor nếu muốn giữ giá trị bất biến có thể chia sẻ.

### 9.4. Đừng lạm dụng static global state

~~~java
// Minh họa anti-pattern, KHÔNG phải lời khuyên:
record CounterValue(int count) {
    // static int globalCounter; // Biên dịch được nhưng là mutable state toàn cục.
}
~~~

Để giữ trạng thái thay đổi của từng phiên hoặc từng yêu cầu, không nên đưa nó vào field `static` của record. Thay vào đó, lưu trạng thái trong dịch vụ hoặc class sở hữu vòng đời và đồng bộ phù hợp; record chỉ chuyển dữ liệu tại một thời điểm.

## 10. Lỗi thường gặp

| Lỗi / hiểu nhầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Khai báo `private int cache;` trong record body | Record cấm mọi field instance khai báo tường minh | Đưa dữ liệu có ý nghĩa giá trị vào header hoặc dùng class thường |
| Nghĩ `static final` là một record component | `static` field thuộc lớp, không gắn với instance | Chỉ các mục trong header mới là components |
| Gọi `Money.plus(other)` | `plus` là instance method, cần một đối tượng cụ thể | Gọi `money.plus(other)` |
| Trong static method viết `return cents;` | `cents` là instance field, static context không có `this` | Truyền một `Money` rồi đọc `money.cents()` |
| Chỉ validate trong factory | `new R(...)` vẫn có thể tạo record trực tiếp | Validate trong canonical constructor |
| Cố khai báo `private` canonical constructor của `public record` | Canonical constructor không được hẹp hơn record | Để `public` và dựa vào constructor để giữ invariant |
| Quên `static <T>` trong factory của generic record | Static context không dùng trực tiếp type parameter của instance record | Cho factory tham số kiểu riêng |
| Dùng static mutable cache mà không xét đồng thời | Trạng thái dùng chung có thể race/corrupt | Dùng dữ liệu immutable hoặc cơ chế đồng bộ/caching rõ ràng |
| Nghĩ thêm method sẽ tự đổi `equals` | `equals` mặc định phụ thuộc component, không phụ thuộc method hay static field | Định nghĩa component đúng ngữ nghĩa giá trị |
| Tạo record mới bằng cách sửa field cũ | Component fields là `private final` | Tạo instance mới với dữ liệu đã thay đổi |

## 11. Bài tập: tổ chức trường, method và factory

Hãy viết `record ItemCount(int value)` với yêu cầu:

1. Header chỉ có component `int value`; không khai báo thêm instance field.
2. Khai báo `public static final ItemCount ZERO` có giá trị `0`.
3. Canonical constructor từ chối `value < 0`.
4. `public static ItemCount of(int value)` tạo record từ số lượng.
5. `public ItemCount plus(int delta)` trả record mới và từ chối tổng âm; không làm tràn `int` âm thầm.
6. `public boolean isEmpty()` trả `true` nếu số lượng bằng 0.

**Đáp án tham khảo** (tệp `ItemCount.java`):

~~~java
public record ItemCount(int value) {
    public static final ItemCount ZERO = new ItemCount(0);

    public ItemCount {
        if (value < 0) {
            throw new IllegalArgumentException("negative quantity");
        }
    }

    public static ItemCount of(int value) {
        return new ItemCount(value);
    }

    public ItemCount plus(int delta) {
        return new ItemCount(Math.addExact(value, delta));
    }

    public boolean isEmpty() {
        return value == 0;
    }
}
~~~

Biên dịch bằng `javac --release 17 ItemCount.java` khi dùng JDK 17+. Khi gọi `ItemCount.of(4).plus(3).value()`, kết quả là `7`; `ItemCount.ZERO.isEmpty()` trả `true`. `ItemCount.of(-1)` và `new ItemCount(-1)` đều ném `IllegalArgumentException`. Nếu `Math.addExact` phát hiện tràn số, nó ném `ArithmeticException`; nếu tổng âm mà không tràn, canonical constructor từ chối.

Bài tập này nhấn mạnh quan hệ giữa ba loại member: **component trong header**, **hằng `static` dùng chung**, và **phương thức instance/static phục vụ nghiệp vụ**.

## 12. Ghi nhớ trọng tâm

- Record có **component fields `private final`** được sinh từ header; không được khai báo thêm **non-static instance fields** trong body, kể cả `final`.
- Body có thể có **`static` fields**, **`static` initializers**, **instance methods**, **`static` methods** và constructors đúng quy tắc.
- Instance method tính toán từ component hoặc trả record mới; static method/factory mô tả cách tạo/chuyển đổi ở cấp type.
- Static factory **chỉ là một phương thức đặt tên rõ nghĩa**; không có cơ chế tự động thay thế constructor. Với `public record`, canonical constructor vẫn phải `public`.
- **Validation và normalization cốt lõi nằm trong canonical constructor** để mọi đường tạo record đều đúng bất biến.
- Static fields không xuất hiện trong `equals/hashCode/toString` mặc định; chúng không phải trạng thái riêng của record instance.
- Với generic record, static factory muốn dùng `T` phải tự khai báo `static <T>`.
- Những quy tắc này là cú pháp Java **chính thức từ Java 16**, còn được sử dụng trong Java 17 và các JDK hiện đại.

**Nguồn chính thức:**
- [Java Language Specification (Java SE 25), `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10) — record body, fields, methods, constructors, accessibility.
- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html) — cách khai báo và sử dụng record.
- [Java SE 17 — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) — hợp đồng record, component fields và accessor.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395) — records trở thành tính năng chính thức từ Java 16.
