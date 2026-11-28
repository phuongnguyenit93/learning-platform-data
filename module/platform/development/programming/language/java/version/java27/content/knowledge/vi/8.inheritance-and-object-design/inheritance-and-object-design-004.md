# Default method, static method và private method của interface

Trong **Java 27**, `interface` không chỉ mô tả những phương thức mà lớp triển khai phải cung cấp. Interface còn có thể định nghĩa hành vi dùng chung bằng **default method**, cung cấp thao tác gắn với chính interface bằng **static method**, và giấu logic hỗ trợ bằng **private method**. Hiểu ranh giới giữa ba nhóm này giúp thiết kế API dễ sử dụng, giữ các quy tắc chung nhất quán và xử lý đúng những xung đột khi kế thừa nhiều interface.

Đây là bài học thuộc chương **Kế thừa và thiết kế hướng đối tượng** của module **JAVA_VERSION_JAVA27 — Java 27 và các kiến thức liên quan**. Default và static interface methods đã được hỗ trợ ổn định từ Java 8; private interface methods từ Java 9. Cả ba tiếp tục là thành phần chính thức trong Java 27, không cần bật tính năng preview. Những ví dụ dưới đây tập trung vào cách sử dụng còn phù hợp hiện nay.

## 1. Bốn nhóm phương thức trong một interface

Một interface thông thường có thể khai báo các loại phương thức sau:

| Loại phương thức | Có phần thân? | Gắn với instance? | Có được kế thừa / override? | Cách gọi |
|---|---|---|---|---|
| `abstract` | Không | Có | Phương thức yêu cầu lớp triển khai cung cấp; có thể được override | Qua đối tượng |
| `default` | Có | Có | Có thể được kế thừa và override | Qua đối tượng |
| `static` | Có | Không | **Không** kế thừa và không override như phương thức instance | `InterfaceName.method()` |
| `private` | Có | Có, trừ khi khai báo `private static` | **Không** kế thừa, không override | Chỉ được gọi trong nội bộ interface khai báo |

Ví dụ nhìn nhanh cấu trúc:

```java
interface DocumentView {
    String title(); // public abstract được ngầm hiểu.

    default String heading() {
        return normalize(title());
    }

    static boolean validTitle(String value) {
        return hasText(value);
    }

    private String normalize(String value) {
        return value == null ? "(không có tiêu đề)" : value.strip();
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
```

Với một phương thức không có `private`, `default` hoặc `static` và kết thúc bằng dấu `;`, Java ngầm hiểu đó là `public abstract`. Ngược lại, các phương thức `default`, `static` và `private` **phải có phần thân**.

Interface không có trường instance; các trường khai báo trực tiếp trong interface là `public static final`. Vì thế, default method có thể dùng trạng thái do đối tượng triển khai cung cấp thông qua phương thức, nhưng không thể sở hữu riêng một trường instance của chính interface.

## 2. Default method: hành vi mặc định cho đối tượng triển khai

**Default method** là phương thức instance có phần thân và được khai báo với từ khóa `default`. Nếu lớp triển khai không cung cấp một phiên bản khác và không có quy tắc ưu tiên kế thừa đặc biệt, đối tượng sẽ sử dụng triển khai mặc định của interface.

```java
interface Greeter {
    String name();

    default String greeting() {
        return "Xin chào, " + name() + "!";
    }
}

class Customer implements Greeter {
    private final String name;

    Customer(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}
```

Đoạn mã sử dụng:

```java
Greeter greeter = new Customer("Lan");
System.out.println(greeter.greeting());
// Xin chào, Lan!
```

Lớp `Customer` chỉ cần hiện thực phương thức `name()`. Default method `greeting()` gọi `name()` trên đối tượng thực tế, rồi tạo ra câu chào. Đây là cách giữ phần **chính sách chung** trong interface và trao cho từng triển khai quyền quyết định dữ liệu riêng.

### 2.1. Lớp triển khai có quyền override

Lớp triển khai có thể thay thế hành vi mặc định:

```java
class FormalCustomer implements Greeter {
    @Override
    public String name() {
        return "Minh";
    }

    @Override
    public String greeting() {
        return "Kính chào " + name();
    }
}
```

Phương thức override phải có mức truy cập phù hợp: default method của interface là `public` nên phương thức trong lớp triển khai phải là `public`. Annotation `@Override` giúp trình biên dịch kiểm tra việc override và nên được sử dụng.

### 2.2. Khi nào nên viết default method?

Default method phù hợp khi hành vi có thể được diễn đạt hoàn toàn từ **hợp đồng đã có** của interface, chẳng hạn một hàm hỗ trợ tính toán hoặc hiển thị:

```java
interface Rectangle {
    double width();
    double height();

    default double area() {
        return width() * height();
    }
}
```

Một lớp triển khai chỉ cần cung cấp `width()` và `height()` để nhận được hành vi `area()`. Tuy nhiên, hãy kiểm tra rằng công thức thực sự phù hợp với **mọi** triển khai hợp lệ, không chỉ một trường hợp hiện tại.

Default method không tự động là lựa chọn tốt chỉ vì muốn tránh viết mã. Nếu các lớp cần quản lý trạng thái chung, đồng bộ hóa, vòng đời tài nguyên hoặc cần nhiều dữ liệu nội bộ, một lớp chuyên trách hoặc cơ chế **composition** có thể rõ ràng hơn.

## 3. Static method: chức năng gắn với tên interface

Phương thức `static` thuộc về interface khai báo, **không phụ thuộc vào một đối tượng cụ thể**. Cú pháp gọi chính xác:

```java
interface CurrencyRules {
    static boolean isSupported(String code) {
        return "VND".equals(code) || "USD".equals(code);
    }
}

class Checkout implements CurrencyRules {}

class Example {
    public static void main(String[] args) {
        System.out.println(CurrencyRules.isSupported("VND")); // true
        System.out.println(CurrencyRules.isSupported("EUR")); // false

        // Checkout.isSupported("VND");     // Không biên dịch.
        // new Checkout().isSupported("VND"); // Không biên dịch.
    }
}
```

Điểm cần ghi nhớ:

- Gọi qua **tên interface khai báo**: `CurrencyRules.isSupported(...)`.
- Phương thức `static` của interface **không được kế thừa** bởi lớp `implements` hoặc interface con `extends`, nên không gọi qua tên lớp triển khai hay biến đối tượng.
- Phương thức `static` không có `this`; không thể gọi trực tiếp một phương thức instance nếu chưa có đối tượng phù hợp.
- Một phương thức `static` của interface không được override thông qua polymorphism. Một lớp hoặc interface khác có thể định nghĩa phương thức cùng tên theo các quy tắc riêng, nhưng đó không phải việc override phương thức `static` đã khai báo.

Các trường hợp sử dụng phù hợp gồm **factory method**, xác thực đầu vào, parse/convert giá trị và thao tác tiện ích gắn chặt với hợp đồng của interface.

Ví dụ factory nhỏ:

```java
interface Formatter {
    String format(String input);

    static Formatter trimmed() {
        return String::strip;
    }
}

Formatter formatter = Formatter.trimmed();
System.out.println(formatter.format("  hello  ")); // hello
```

Factory trả về một đối tượng thực thi interface. Bản thân `trimmed()` là static, còn `format(...)` là lời gọi instance trên đối tượng `formatter`.

## 4. Private method: tái sử dụng chi tiết cài đặt trong interface

Phương thức `private` trong interface giúp các default hoặc static method dùng chung logic mà **không mở rộng API công khai**. Có hai dạng:

| Dạng | Phạm vi và đặc điểm |
|---|---|
`private ReturnType helper(...)` | Phương thức instance riêng của interface; dùng được từ default/private instance method |
`private static ReturnType helper(...)` | Phương thức static riêng của interface; dùng được trong cả static và instance context phù hợp |

Ví dụ hai default method chia sẻ bước định dạng:

```java
interface AuditLabel {
    String source();

    default String createdLabel() {
        return decorate("CREATED");
    }

    default String removedLabel() {
        return decorate("REMOVED");
    }

    private String decorate(String operation) {
        return "[" + source() + "] " + operation;
    }
}
```

Phương thức `decorate(...)` có thể gọi `source()` của chính đối tượng triển khai. Bên ngoài interface, các lớp triển khai không thể gọi `decorate(...)` hoặc override nó để thay đổi hành vi của các default method. Thay đổi logic private không tạo ra phương thức công khai mới cho người sử dụng API.

Một helper không phụ thuộc instance có thể dùng `private static`:

```java
interface NameRules {
    static boolean isValid(String name) {
        return hasText(name) && name.length() <= 50;
    }

    private static boolean hasText(String text) {
        return text != null && !text.isBlank();
    }
}
```

Không thể khai báo `private abstract` hoặc `private default`. Private method trong interface **phải có thân** và không được kế thừa, do đó không dùng làm điểm mở rộng cho bên triển khai. Nếu muốn bắt buộc lớp triển khai một hành vi, hãy khai báo phương thức abstract công khai.

## 5. Ví dụ hoàn chỉnh dùng cả ba loại phương thức

Lưu đoạn sau thành `InterfaceMethodDemo.java` và chạy bằng `java InterfaceMethodDemo.java` trên JDK 27:

```java
public class InterfaceMethodDemo {
    interface Report {
        String title();

        default String header() {
            return decorate("Báo cáo: " + title());
        }

        default String status() {
            return decorate("Sẵn sàng");
        }

        private String decorate(String text) {
            return "[" + text.strip() + "]";
        }

        static boolean validTitle(String title) {
            return hasText(title);
        }

        private static boolean hasText(String text) {
            return text != null && !text.isBlank();
        }
    }

    record DailyReport(String title) implements Report {}

    public static void main(String[] args) {
        Report report = new DailyReport("Doanh số");

        System.out.println(Report.validTitle(report.title()));
        System.out.println(report.header());
        System.out.println(report.status());
    }
}
```

Kết quả:

```text
true
[Báo cáo: Doanh số]
[Sẵn sàng]
```

Trong ví dụ:

1. `title()` là phương thức abstract của interface; record `DailyReport` cung cấp accessor `public title()` tương ứng để thực hiện hợp đồng.
2. `header()` và `status()` là default methods được đối tượng kế thừa từ `Report`.
3. `decorate(...)` là private instance method, dùng chung logic của hai default methods.
4. `validTitle(...)` là static method, được gọi qua tên `Report`.
5. `hasText(...)` là private static helper; lớp ngoài không thể gọi nó.

Ví dụ kết hợp cú pháp record đã ổn định với interface methods được Java 27 hỗ trợ chính thức.

## 6. Giải quyết xung đột khi kế thừa default method

Java cho phép một lớp `implements` nhiều interface và một interface `extends` nhiều interface. Vì thế, các phương thức có cùng chữ ký có thể gặp nhau. Có ba quy tắc thiết kế cần nhớ, nhưng mỗi trường hợp vẫn phải tuân theo điều kiện override và kế thừa trong JLS.

### 6.1. Phương thức concrete của lớp được ưu tiên

Khi hệ thống lớp cha cung cấp một phương thức instance concrete hợp lệ cùng chữ ký với default method, hành vi từ **lớp** được ưu tiên.

```java
interface Welcome {
    default String message() {
        return "từ interface";
    }
}

class Parent {
    public String message() {
        return "từ lớp cha";
    }
}

class Child extends Parent implements Welcome {}

System.out.println(new Child().message()); // từ lớp cha
```

Nguyên tắc thường gọi là **class wins**. Đừng cho rằng default method luôn ghi đè một phương thức concrete có sẵn trong hệ thống lớp. Nếu lớp cha khai báo một phương thức **abstract** tương đương, lớp con concrete có thể vẫn cần triển khai rõ ràng; không nên dùng quy tắc “class wins” để bỏ qua các ràng buộc đó.

### 6.2. Interface cụ thể hơn có thể override default method của interface cha

Nếu một interface con override default method của interface cha, lớp triển khai nhận phiên bản **cụ thể hơn**:

```java
interface BaseLabel {
    default String label() {
        return "base";
    }
}

interface DetailedLabel extends BaseLabel {
    @Override
    default String label() {
        return "detailed";
    }
}

class LabelView implements DetailedLabel {}

System.out.println(new LabelView().label()); // detailed
```

Đây là trường hợp quan hệ kế thừa đã xác định rõ phiên bản được override. Không áp dụng cách hiểu “đường dẫn gần hơn” một cách máy móc cho mọi cặp interface độc lập.

### 6.3. Hai default methods độc lập trùng chữ ký: phải giải quyết rõ

Giả sử một lớp cùng triển khai hai interface không có quan hệ kế thừa, và cả hai đều định nghĩa `default label()`:

```java
interface ShortLabel {
    default String label() {
        return "ngắn";
    }
}

interface LongLabel {
    default String label() {
        return "chi tiết";
    }
}

// Không hợp lệ vì xung đột default methods:
// class BadLabel implements ShortLabel, LongLabel {}

class CombinedLabel implements ShortLabel, LongLabel {
    @Override
    public String label() {
        return ShortLabel.super.label()
                + " / " + LongLabel.super.label();
    }
}
```

`CombinedLabel` chủ động override `label()`; cú pháp `ShortLabel.super.label()` và `LongLabel.super.label()` gọi triển khai mặc định của từng **direct superinterface**. Kết quả:

```text
ngắn / chi tiết
```

Lời gọi dạng `InterfaceName.super.method()` chỉ hợp lệ trong ngữ cảnh và quan hệ superinterface thích hợp; không thể gọi tùy ý trên một interface không được kế thừa trực tiếp hoặc đã bị một superinterface cụ thể hơn che khuất.

Tương tự, nếu một **interface con** kế thừa các default methods xung đột, interface đó phải khai báo một phương thức tương đương để giải quyết (có thể chọn một default implementation cụ thể hoặc tái khai báo abstract theo quy tắc ngôn ngữ):

```java
interface UnifiedLabel extends ShortLabel, LongLabel {
    @Override
    default String label() {
        return ShortLabel.super.label();
    }
}
```

**Chú ý:** một interface con cũng có thể xung đột nếu nhận một default method và một abstract method cùng chữ ký từ hai interface khác nhau. Việc tồn tại một bản mặc định không có nghĩa Java tự chọn nó để đáp ứng hợp đồng abstract kia.

### 6.4. Không dùng default method để ghi đè các phương thức của `Object`

Interface không được định nghĩa default method có chữ ký override-equivalent với phương thức không private của `Object` như `toString()`, `equals(Object)` hoặc `hashCode()`:

```java
interface InvalidDescription {
    // Không biên dịch:
    // default String toString() { return "interface"; }
}
```

Nếu cần định dạng chung, hãy định nghĩa phương thức tên khác như `description()`, rồi cho lớp triển khai chủ động quyết định có override `toString()` để gọi tới phương thức đó hay không.

## 7. Static và private method không tham gia cơ chế chọn default method

Khi một lớp triển khai interface, chỉ các phương thức instance phù hợp mới tham gia cơ chế kế thừa và override. Hai điểm thường gây nhầm lẫn:

**Static method được gọi tĩnh theo interface khai báo.**

```java
interface First {
    static String name() {
        return "First";
    }
}

interface Second extends First {}

System.out.println(First.name()); // First
// Second.name();                 // Không hợp lệ: không kế thừa static method.
```

**Private method thuộc chi tiết cài đặt của interface.**

```java
interface Greeting {
    default String greet() {
        return internalGreeting();
    }

    private String internalGreeting() {
        return "Xin chào";
    }
}

class GreetingImpl implements Greeting {
    // Khai báo cùng tên ở lớp không override private method của interface:
    public String internalGreeting() {
        return "Lời chào của lớp";
    }
}
```

`new GreetingImpl().greet()` vẫn trả về `"Xin chào"`, vì lời gọi `internalGreeting()` bên trong `Greeting.greet()` tham chiếu tới phương thức private của interface và không bị override. Trường hợp cần thay đổi hành vi theo lớp triển khai phải khai báo một hook `public abstract` hoặc `default` thích hợp.

## 8. Interface với lambda và functional interface

Một interface có **một phương thức abstract chức năng** vẫn có thể là `@FunctionalInterface`, dù nó chứa nhiều default, static hoặc private methods. Các phương thức có triển khai này không làm tăng số lượng abstract methods dùng để xác định hợp đồng lambda.

```java
@FunctionalInterface
interface TextConverter {
    String convert(String text);

    default String convertTrimmed(String text) {
        return convert(normalize(text));
    }

    private String normalize(String text) {
        return text == null ? "" : text.strip();
    }

    static TextConverter uppercase() {
        return text -> text.toUpperCase(java.util.Locale.ROOT);
    }
}

TextConverter converter = TextConverter.uppercase();
System.out.println(converter.convertTrimmed("  java  ")); // JAVA
```

Đoạn mã minh họa cách factory static tạo lambda, default method thêm hành vi dùng chung và private method giữ phần chuẩn hóa nội bộ. Với một tham chiếu có thể là `null`, phương thức `convertTrimmed` xử lý đầu vào trước khi chuyển cho lambda.

## 9. Chọn loại phương thức theo trách nhiệm

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
Mọi lớp phải tự cung cấp một hành vi | Abstract method | Thể hiện hợp đồng bắt buộc |
Hành vi hợp lệ cho phần lớn/mọi triển khai và chỉ dùng API sẵn có | Default method | Tái sử dụng mà vẫn cho phép override |
Factory, parser hoặc phép xác thực không cần instance | Static method | Chức năng có tên đi cùng interface |
Logic dùng chung giữa các default methods và cần instance | Private instance method | Giấu chi tiết và tránh lặp |
Logic hỗ trợ không cần instance, dùng trong static/default methods | Private static method | Tái sử dụng trong interface |
Hành vi phức tạp, có nhiều phụ thuộc hoặc trạng thái riêng | Lớp dịch vụ hoặc composition | Tách trách nhiệm, hỗ trợ thay đổi và kiểm thử độc lập |

### 9.1. Khi mở rộng một API đã phát hành

Một lý do lịch sử của default method là cho phép **bổ sung hành vi** vào interface trong nhiều tình huống mà không buộc mọi lớp triển khai cũ phải viết lại ngay. Ví dụ:

```java
interface DeviceStatus {
    boolean online();

    default String stateLabel() {
        return online() ? "ONLINE" : "OFFLINE";
    }
}
```

Các lớp đã triển khai `online()` có thể nhận được `stateLabel()`. Tuy nhiên, **không phải mọi bổ sung default method đều bảo đảm tương thích tuyệt đối**: tên và chữ ký mới có thể xung đột với phương thức của interface khác hay phương thức đã tồn tại trong lớp. Khi công bố API thư viện, cần đánh giá tương thích nguồn và nhị phân theo tập người dùng thực tế.

### 9.2. Những nguyên tắc thiết kế nên giữ

1. **Giữ hợp đồng nhỏ và rõ:** default method cần có ngữ nghĩa thống nhất cho mọi triển khai dự kiến.
2. **Tôn trọng quy tắc kế thừa:** khi sử dụng nhiều interface, chủ động kiểm tra trùng chữ ký và xử lý xung đột bằng override công khai.
3. **Tránh tác dụng phụ gây bất ngờ:** default method không nên âm thầm thay đổi trạng thái hoặc thực hiện I/O nặng nếu tên và hợp đồng không thể hiện điều đó.
4. **Giấu helper bằng private:** tránh đưa hàm chỉ phục vụ triển khai vào API công khai.
5. **Dùng static qua tên interface:** giúp phân biệt một thao tác có tính toàn cục với hành vi của một đối tượng.
6. **Không ép interface chứa trạng thái:** nếu cần dữ liệu instance và vòng đời phức tạp, cân nhắc composition, dependency injection hoặc một kiểu lớp phù hợp.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Biểu hiện | Cách xử lý |
|---|---|---|
Thiếu `default` trước phương thức instance có thân | Trình biên dịch không chấp nhận phương thức abstract có body | Khai báo `default`, hoặc bỏ body để thành abstract |
Viết `default static` hoặc `private default` | Kết hợp modifier không hợp lệ | Chọn đúng một mô hình; `private static` được phép |
Khai báo default method cùng chữ ký với `Object.toString()`/`equals()` | Lỗi biên dịch | Đổi tên thành một phương thức hành vi riêng |
Gọi `Interface.staticMethod()` qua đối tượng hoặc lớp triển khai | Không tìm thấy phương thức | Gọi qua tên interface khai báo |
Giả định private helper có thể override | Thay đổi phương thức cùng tên trong lớp nhưng default method vẫn hoạt động như cũ | Thiết kế hook public nếu cần tùy biến |
Hai interface độc lập cung cấp default cùng chữ ký | Xung đột kế thừa | Override công khai và xác định hành vi rõ ràng |
Override default method với quyền truy cập yếu hơn `public` | Lỗi giảm quyền truy cập | Khai báo phương thức triển khai là `public` |
Đặt logic nghiệp vụ quá phức tạp vào default method | Khó kiểm thử, khó thay đổi, gây phụ thuộc không rõ ràng | Chuyển logic sang thành phần chuyên trách và gọi qua hợp đồng |

## 11. Tự kiểm tra hiểu biết

### Bài tập 1: Dự đoán kết quả

```java
interface A {
    default int value() {
        return 10;
    }
}

interface B extends A {
    @Override
    default int value() {
        return 20;
    }

    static int scale(int n) {
        return n * 2;
    }
}

class C implements B {}

System.out.println(new C().value());
System.out.println(B.scale(3));
```

Kết quả lần lượt là `20` và `6`. `B` override default method của `A` nên `C` nhận phiên bản cụ thể hơn. Phương thức `scale` được gọi qua tên `B`; không gọi bằng `C.scale(3)`.

### Bài tập 2: Thiết kế lại một interface

Giả sử ba lớp thanh toán phải thực hiện chung bước kiểm tra mã giao dịch, nhưng mỗi lớp có cách thực hiện `pay()` khác nhau. Hãy phác thảo interface với:

- Một phương thức abstract `pay(String transactionId)`.
- Một default method `payVerified(String transactionId)` kiểm tra đầu vào trước khi gọi `pay(...)`.
- Một private static helper kiểm tra chuỗi có rỗng hoặc chỉ chứa khoảng trắng không.
- Một static factory hoặc utility chỉ khi có nhu cầu thực tế, tránh thêm phương thức cho đủ loại.

Gợi ý: điều kiện `transactionId == null || transactionId.isBlank()` phù hợp để chặn giá trị không hợp lệ trước lời gọi `pay(...)`.

## 12. Tài liệu tham khảo chính thức

- [Java SE 27 — Java Language Specification §9.4: Method Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.4): loại phương thức, modifier, private/default/static và các giới hạn.
- [Java SE 27 — Java Language Specification §9.4.1: Inheritance and Overriding](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.4.1): quy tắc kế thừa, override và xử lý xung đột default methods.
- [Java SE 27 — Java Language Specification §9.4.3: Interface Method Body](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.4.3): yêu cầu phần thân cho default, static, private và abstract.
- [Java SE 27 — Java Language Specification §9.8: Functional Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.8): xác định hợp đồng của functional interface và tương tác với lambda.
- [Java SE 27 — Java Language Specification §8.4.8](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.8): kế thừa, override và hiding của phương thức trong hệ thống lớp.
