# Phương thức instance, phương thức static và hằng số trong record

## 1. Record có thể chứa hành vi bên cạnh dữ liệu

Record thường được dùng để biểu diễn dữ liệu bằng các component trong header. Tuy nhiên, record không chỉ gồm constructor và accessor được sinh tự động. Body của record có thể khai báo **phương thức instance**, **phương thức static** và **field static**, bao gồm các hằng số dùng chung.

Ví dụ:

~~~java
public record Money(String currency, long amountInMinorUnits) {
    public boolean isZero() {
        return amountInMinorUnits == 0;
    }

    public static Money zero(String currency) {
        return new Money(currency, 0);
    }

    public static final String DEFAULT_CURRENCY = "VND";
}
~~~

- **isZero()** là phương thức instance, hoạt động trên một object Money cụ thể.
- **zero(...)** là phương thức static, được gọi qua tên kiểu Money.
- **DEFAULT_CURRENCY** là field static final, dùng chung cho class.

Các khả năng này là phần ổn định của record từ Java 16 và tiếp tục áp dụng trong Java hiện đại. Record vẫn giữ quy tắc quan trọng: trạng thái instance được mô tả bằng component; không thể bổ sung field instance tùy ý để lưu trạng thái riêng khác.

Mục tiêu bài học:

- Viết phương thức instance tính toán từ component.
- Khai báo và gọi phương thức static trong record.
- Tổ chức hằng số bằng static final.
- Hiểu sự khác nhau giữa instance context và static context.
- Dùng factory method và helper method để làm API record dễ sử dụng.
- Nhận diện giới hạn trạng thái của record khi thiết kế hành vi.

## 2. Phương thức instance: hành vi gắn với một object

Phương thức instance là phương thức không khai báo static. Nó được gọi thông qua một instance và có thể sử dụng component của instance đó.

~~~java
record Rectangle(double width, double height) {
    double area() {
        return width * height;
    }

    double perimeter() {
        return 2 * (width + height);
    }
}

Rectangle rectangle = new Rectangle(5, 3);

System.out.println(rectangle.area());      // 15.0
System.out.println(rectangle.perimeter()); // 16.0
~~~

**area()** và **perimeter()** không cần nhận width hoặc height làm tham số vì chúng đang hoạt động trên object rectangle. Các component là dữ liệu của instance hiện tại.

### Dùng accessor trong phương thức instance

Có thể gọi accessor để thể hiện rõ việc đọc component:

~~~java
record OrderLine(String sku, int quantity, long unitPrice) {
    long totalPrice() {
        return quantity() * unitPrice();
    }

    boolean hasSku(String candidate) {
        return sku().equals(candidate);
    }
}
~~~

Trong một phương thức instance, có thể truy cập component bằng tên field hoặc bằng accessor tương ứng. Dùng accessor như ví dụ trên thường làm rõ rằng phương thức đang đọc API component. Nếu accessor được khai báo tường minh để chuẩn hóa hoặc trả về bản sao, gọi accessor cũng giúp tuân theo hành vi truy cập đã thiết kế.

### Phương thức instance có thể nhận tham số và trả về kết quả

Record method tuân theo quy tắc khai báo phương thức Java thông thường:

~~~java
record Temperature(double celsius) {
    double toFahrenheit() {
        return celsius * 9.0 / 5.0 + 32.0;
    }

    boolean isAbove(double threshold) {
        return celsius > threshold;
    }

    Temperature plus(double delta) {
        return new Temperature(celsius + delta);
    }
}
~~~

Ví dụ sử dụng:

~~~java
Temperature room = new Temperature(25);

System.out.println(room.toFahrenheit()); // 77.0
System.out.println(room.isAbove(20));    // true

Temperature warmer = room.plus(2);
System.out.println(warmer.celsius());   // 27.0
System.out.println(room.celsius());     // 25.0
~~~

Phương thức plus() trả về một record mới thay vì thay đổi component của object hiện tại. Đây là cách phù hợp với mô hình giá trị: thao tác tính toán tạo ra giá trị mới.

### Có thể khai báo helper method

Không phải mọi phương thức đều cần là một phần API công khai. Có thể dùng private cho logic hỗ trợ nội bộ:

~~~java
record PersonName(String firstName, String lastName) {
    PersonName {
        firstName = java.util.Objects.requireNonNull(firstName, "firstName").strip();
        lastName = java.util.Objects.requireNonNull(lastName, "lastName").strip();
    }

    PersonName {
        firstName = firstName.strip();
        lastName = lastName.strip();
    }

    public String fullName() {
        return joinNames(firstName, lastName);
    }

    private static String joinNames(String first, String last) {
        return first + " " + last;
    }
}
~~~

fullName() là hành vi công khai; joinNames() là helper private. Vì helper không cần dữ liệu instance ngoài các đối số được truyền vào, khai báo static là hợp lý.

## 3. Phương thức instance không tạo thêm trạng thái

Record không cho khai báo field instance bổ sung ngoài component. Quy tắc này vẫn có hiệu lực dù body có nhiều phương thức.

~~~java
record ShoppingCartSummary(int itemCount, long totalInCents) {
    boolean isEmpty() {
        return itemCount == 0;
    }

    boolean exceedsBudget(long budgetInCents) {
        return totalInCents > budgetInCents;
    }

    // Không hợp lệ: record không được khai báo field instance bổ sung.
    // private boolean cached;
}
~~~

Có thể tính toán giá trị dẫn xuất khi gọi phương thức. Nếu một giá trị có thể được tính trực tiếp từ component, thường không cần lưu bản sao riêng trong field instance.

Một record cũng không thể khai báo instance initializer block để khởi tạo trạng thái bổ sung. Việc kiểm tra và chuẩn hóa component nên được thực hiện trong canonical constructor hoặc compact canonical constructor.

### Phương thức không làm component trở nên mutable

~~~java
record CounterValue(int value) {
    CounterValue increment() {
        return new CounterValue(value + 1);
    }
}

CounterValue first = new CounterValue(4);
CounterValue second = first.increment();

System.out.println(first.value());  // 4
System.out.println(second.value()); // 5
~~~

Không có setter tự động và không thể gán lại field component. Nếu cần một thao tác kiểu cập nhật, hãy trả về instance mới như increment().

Cần nhớ rằng field component là final nhưng object mà component tham chiếu đến vẫn có thể mutable. Phương thức instance có thể gọi phương thức thay đổi object lồng bên trong nếu thiết kế cho phép. Vì vậy, quy tắc không có field instance bổ sung không tự đảm bảo bất biến sâu.

## 4. Phương thức static: hành vi gắn với kiểu record

Phương thức static thuộc về class record, không gắn với một instance cụ thể. Nó được gọi qua tên record:

~~~java
record Temperature(double celsius) {
    static Temperature freezingPoint() {
        return new Temperature(0);
    }

    static Temperature boilingPointAtSeaLevel() {
        return new Temperature(100);
    }
}

Temperature freezing = Temperature.freezingPoint();
Temperature boiling = Temperature.boilingPointAtSeaLevel();
~~~

Phương thức static phù hợp với thao tác:

- Tạo instance theo một giá trị mặc định hoặc quy ước.
- Kiểm tra hoặc chuyển đổi dữ liệu không phụ thuộc vào một instance cụ thể.
- Cung cấp hàm tiện ích có liên quan trực tiếp đến kiểu record.
- Tập trung logic tạo object để code gọi không phải lặp lại quy tắc.

### Static context không có this

Vì không gắn với instance, phương thức static không có this và không thể đọc component của một object hiện tại nếu không có instance được truyền vào.

~~~java
record User(String name) {
    String normalizedName() {
        return name.strip();
    }

    static String normalize(String value) {
        return value.strip();
    }

    // Không hợp lệ: phương thức static không có instance hiện tại.
    // static String currentName() {
    //     return name;
    // }
}
~~~

Muốn phương thức static làm việc với dữ liệu của record, hãy truyền instance hoặc component làm tham số:

~~~java
record User(String name) {
    static String displayName(User user) {
        return user.name().strip();
    }

    static String normalize(String value) {
        return value.strip();
    }
}
~~~

displayName() nhận một User cụ thể và đọc component qua accessor. normalize() chỉ nhận chuỗi nên có thể tái sử dụng độc lập với instance.

### Gọi static method bằng tên kiểu

Nên viết:

~~~java
Temperature freezing = Temperature.freezingPoint();
~~~

Tránh gọi static method thông qua biến instance:

~~~java
Temperature value = new Temperature(25);

// Cú pháp Java cho phép tham chiếu static qua expression,
// nhưng dễ gây hiểu nhầm rằng phương thức phụ thuộc vào value.
Temperature freezing = value.freezingPoint();
~~~

Gọi qua tên kiểu làm rõ phương thức thuộc về class, không phụ thuộc object nào.

## 5. Static factory method: cách tạo record có tên và ý nghĩa

Một factory method static có thể cung cấp cách tạo instance dễ đọc hơn constructor, hoặc đóng gói giá trị mặc định và xác thực chung.

~~~java
import java.util.Objects;
import java.util.Locale;

record EmailAddress(String value) {
    EmailAddress {
        value = Objects.requireNonNull(value, "value").strip().toLowerCase(Locale.ROOT);
        if (!value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
    }

    static EmailAddress of(String value) {
        return new EmailAddress(value);
    }

    static EmailAddress support() {
        return new EmailAddress("support@example.com");
    }
}
~~~

Sử dụng:

~~~java
EmailAddress customer = EmailAddress.of("An@example.com");
EmailAddress support = EmailAddress.support();

System.out.println(customer.value()); // an@example.com
System.out.println(support.value());  // support@example.com
~~~

Factory method gọi constructor nên mọi quy tắc trong compact canonical constructor vẫn được áp dụng. Caller không thể bỏ qua xác thực bằng cách chọn một factory method khác.

Tên factory nên thể hiện ý nghĩa:

| Tên phương thức | Ý nghĩa thường gặp |
| --- | --- |
| of(...) | Tạo giá trị từ một hoặc nhiều đối số. |
| from(...) | Tạo từ một nguồn hoặc kiểu dữ liệu khác. |
| parse(...) | Phân tích chuỗi hoặc định dạng đầu vào. |
| defaultValue() | Tạo giá trị mặc định. |
| empty() | Tạo biểu diễn rỗng nếu mô hình có khái niệm đó. |

Đây là quy ước API, không phải từ khóa đặc biệt của Java.

## 6. Phương thức static generic trong generic record

Một static method không thể dùng trực tiếp type parameter của instance record, vì static context không gắn với một lần tham số hóa cụ thể.

Ví dụ generic record:

~~~java
record Box<T>(T value) {
    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

T là type parameter của record; U là type parameter riêng của phương thức static.

~~~java
Box<String> text = Box.of("Java");
Box<Integer> number = Box.of(16);

System.out.println(text.value());   // Java
System.out.println(number.value()); // 16
~~~

Không viết static method dùng T trực tiếp như sau:

~~~java
record Box<T>(T value) {
    // Không hợp lệ: T là type parameter của instance record,
    // static method cần khai báo type parameter riêng.
    // static Box<T> empty() {
    //     return new Box<>(null);
    // }
}
~~~

Nếu cần phương thức static trả về một Box<T> theo một kiểu cụ thể, hãy khai báo type parameter trên phương thức, hoặc truyền Class<T>/giá trị T vào để xác định kiểu.

## 7. Hằng số trong record: static final

Record có thể khai báo field static. Một cách phổ biến là dùng public static final cho hằng số cần chia sẻ:

~~~java
record HttpStatus(int code, String description) {
    public static final int OK = 200;
    public static final int NOT_FOUND = 404;
    public static final String DEFAULT_DESCRIPTION = "Unknown";
}
~~~

Sử dụng qua tên kiểu:

~~~java
System.out.println(HttpStatus.OK); // 200
System.out.println(HttpStatus.DEFAULT_DESCRIPTION);
~~~

Các field này thuộc về class HttpStatus, không thuộc riêng một instance. Không cần tạo HttpStatus để đọc hằng số.

### Phân biệt static final và compile-time constant

Không phải mọi field static final đều là compile-time constant theo định nghĩa của Java.

Một biến hằng compile-time thường phải có kiểu primitive hoặc String, được khai báo final và khởi tạo bằng constant expression:

~~~java
record Limits(int value) {
    public static final int MAX_RETRIES = 3;
    public static final String DEFAULT_REGION = "ap-southeast-1";
}
~~~

Ngược lại, một object collection dù được khai báo static final không phải compile-time constant:

~~~java
import java.util.List;

record FeatureFlags(String name) {
    public static final List<String> SUPPORTED =
        List.of("records", "streams");
}
~~~

SUPPORTED là field static final, nhưng không phải compile-time constant. Đây vẫn là cách hữu ích để công bố collection dùng chung; List.of() tạo danh sách không cho sửa cấu trúc.

### final trên tham chiếu không tự làm object bất biến

~~~java
record Registry(String name) {
    public static final java.util.List<String> TAGS =
        new java.util.ArrayList<>();
}
~~~

Tham chiếu TAGS không thể được gán lại, nhưng danh sách ArrayList vẫn có thể thay đổi nội dung. Với hằng collection, ưu tiên factory tạo collection không sửa đổi như List.of(), Set.of() hoặc Map.of() nếu dữ liệu phù hợp.

Không nên dùng static final cho mảng hoặc object mutable rồi xem chúng là hằng bất biến. final bảo vệ việc gán lại biến tham chiếu, không khóa trạng thái của object.

## 8. Kết hợp instance method, static method và constant

Một record có thể tổ chức ba loại thành viên cùng nhau. Ví dụ:

~~~java
import java.util.Objects;
import java.util.Locale;

public record Money(String currency, long minorUnits) {
    public static final String DEFAULT_CURRENCY = "VND";
    public static final Money ZERO_VND = new Money(DEFAULT_CURRENCY, 0);

    public Money {
        currency = Objects.requireNonNull(currency, "currency")
            .strip()
            .toUpperCase(Locale.ROOT);

        if (currency.isEmpty()) {
            throw new IllegalArgumentException("currency is required");
        }
        if (minorUnits < 0) {
            throw new IllegalArgumentException("minorUnits must be non-negative");
        }
    }

    public boolean isZero() {
        return minorUnits == 0;
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(currency, Math.addExact(minorUnits, other.minorUnits()));
    }

    public static Money zero(String currency) {
        return new Money(currency, 0);
    }

    public static Money ofVnd(long minorUnits) {
        return new Money(DEFAULT_CURRENCY, minorUnits);
    }
}
~~~

Sử dụng:

~~~java
Money first = Money.ofVnd(50_000);
Money second = Money.zero("VND");
Money total = first.plus(second);

System.out.println(first.isZero()); // false
System.out.println(total.minorUnits()); // 50000
System.out.println(Money.ZERO_VND); // Money[currency=VND, minorUnits=0]
~~~

Trong ví dụ:

- currency và minorUnits là component, xác định trạng thái từng instance.
- Compact canonical constructor chuẩn hóa và xác thực dữ liệu.
- isZero() và plus() là instance method vì chúng làm việc với giá trị của object hiện tại.
- zero() và ofVnd() là static factory method vì chúng tạo instance từ tham số.
- DEFAULT_CURRENCY là hằng số dùng chung.
- ZERO_VND là một object static final dùng chung. Nó không phải compile-time constant, nhưng Money là record và các component của instance này không bị gán lại.

Ví dụ này giả định nghiệp vụ dùng đơn vị tiền nhỏ nhất và không xử lý tỷ giá hoặc phép cộng giữa các loại tiền khác nhau.

## 9. Quy tắc và giới hạn cần nhớ

| Thành viên | Có thể khai báo? | Có thể truy cập component hiện tại? | Ghi chú |
| --- | --- | --- | --- |
| Instance method | Có | Có | Dùng this, accessor hoặc component field. |
| Private instance helper | Có | Có | Dùng để chia nhỏ logic nội bộ. |
| Static method | Có | Không có this; cần instance/tham số nếu muốn đọc component. | Có thể làm factory hoặc utility. |
| Static generic method | Có | Không dùng trực tiếp type parameter của record. | Khai báo type parameter riêng. |
| Static field | Có | Không thuộc instance cụ thể. | Có thể dùng cho dữ liệu dùng chung. |
| Static final constant | Có | Không thuộc instance cụ thể. | Chỉ một số khai báo là compile-time constant. |
| Instance field bổ sung | Không | — | Trạng thái instance chỉ được mô tả bằng component. |
| Instance initializer block | Không | — | Dùng constructor để xác thực/khởi tạo component. |

Những điểm dễ nhầm:

1. Phương thức instance có thể đọc component, nhưng không thể gán lại component.
2. Phương thức static không có this; muốn dùng dữ liệu record phải nhận instance hoặc component làm tham số.
3. Static method không được override như instance method; static method cùng chữ ký trong kiểu con thông thường là method hiding, nhưng record là final nên không có subclass.
4. Field static final không nhất thiết là compile-time constant.
5. Field static final tham chiếu đến object mutable không làm object đó bất biến.
6. Không thêm field instance để cache kết quả; hãy tính từ component hoặc dùng một cơ chế cache bên ngoài phù hợp nếu thực sự cần.

## 10. Bài tập thực hành

1. Khai báo record Rectangle(double width, double height). Viết instance method area() và perimeter().
2. Khai báo record Temperature(double celsius). Viết static factory method freezingPoint() và roomTemperature().
3. Viết record UserName(String value) có instance method normalized() và static method of(String raw).
4. Khai báo record RetryPolicy(int maxAttempts). Tạo hằng số DEFAULT_MAX_ATTEMPTS và viết static factory defaultPolicy().
5. Viết generic record Box<T> có static generic factory method of(U value). Giải thích vì sao method dùng U thay cho T.
6. Tìm lỗi trong một static method cố đọc component trực tiếp và sửa bằng cách nhận instance hoặc component làm tham số.
7. Giải thích vì sao static final List<String> không tự động là compile-time constant và vì sao nên dùng collection không sửa đổi cho hằng dùng chung.
8. Thiết kế một record giá trị có instance method trả về instance mới thay vì thay đổi component của object hiện tại.

## Ghi nhớ

Record có thể khai báo instance method để tính toán hoặc cung cấp hành vi dựa trên component; có thể khai báo static method để tạo instance, chuyển đổi hoặc cung cấp tiện ích gắn với kiểu; và có thể khai báo field static final cho hằng dùng chung. Instance method có quyền truy cập dữ liệu của object hiện tại, còn static method không có this và phải nhận dữ liệu qua tham số hoặc một instance. Static generic method cần type parameter riêng. Record vẫn không cho thêm field instance hoặc instance initializer block ngoài các component; vì vậy hãy giữ hành vi dựa trên dữ liệu đã khai báo và trả về instance mới khi cần biểu diễn giá trị thay đổi. static final chỉ ngăn gán lại field; nếu field tham chiếu object mutable, cần dùng kiểu bất biến hoặc bảo vệ nội dung phù hợp. Đây là các quy tắc Java record ổn định từ Java 16 và vẫn hữu ích trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification – Class Members and Static Contexts, mục 8.2 và 8.4](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html)
- [Java Language Specification – Constant Variables, mục 4.12.4](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.12.4)
