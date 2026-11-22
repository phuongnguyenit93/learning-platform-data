# @Target trong Java: FIELD, METHOD và CONSTRUCTOR

Trong Java, một annotation chỉ có thể xuất hiện ở các **vị trí khai báo** mà kiểu annotation đó cho phép. Ba đích thường gặp khi đánh dấu thành phần bên trong class là `ElementType.FIELD`, `ElementType.METHOD` và `ElementType.CONSTRUCTOR`. Chúng tương ứng với **trường dữ liệu**, **phương thức** và **constructor**.

Chẳng hạn, cùng một class có thể khai báo metadata riêng cho nơi lưu trạng thái, nơi cung cấp hành vi và nơi khởi tạo đối tượng:

```java
class Account {
    @ColumnName("account_id")  // Ví dụ annotation dành cho FIELD.
    private final String id;

    @CreatedBy("constructor") // Ví dụ annotation dành cho CONSTRUCTOR.
    Account(String id) {
        this.id = id;
    }

    @AccessLabel("read")      // Ví dụ annotation dành cho METHOD.
    String getId() {
        return id;
    }
}
```

Đoạn trên **chỉ minh họa vị trí đặt annotation**; để biên dịch, phải khai báo các annotation `ColumnName`, `CreatedBy` và `AccessLabel` tương ứng. Một chương trình Java 17+ đầy đủ, biên dịch độc lập, sẽ xuất hiện ở phần 7.

Bài học này tập trung vào **đích áp dụng (`@Target`)**. Đích áp dụng trả lời câu hỏi *“Được viết annotation ở đâu?”*; nó không quyết định metadata được giữ đến runtime hay framework sẽ làm gì với metadata đó.

## 1. Phân biệt ba đích qua khai báo Java

| `ElementType` | Cho phép annotation trên | Ví dụ vị trí hợp lệ | Những vị trí dễ nhầm |
| --- | --- | --- | --- |
| `FIELD` | Khai báo field của class hoặc interface, bao gồm hằng enum | `@Tag private int count;` | Biến cục bộ trong method, tham số, getter |
| `METHOD` | Khai báo method, kể cả method interface và element của annotation type | `@Tag public int size() { ... }` | Constructor, lời gọi method `size()`, tham số |
| `CONSTRUCTOR` | Khai báo constructor | `@Tag public Person() {}` | Method có tên gần giống constructor, câu lệnh `new Person()` |

Đây là các **declaration targets** (đích khai báo), không phải mọi chỗ mã nguồn có dùng đến field, method hoặc constructor.

- **FIELD:** phần tử khai báo để lưu trạng thái ở cấp class/interface. Java coi enum constant là một dạng khai báo field trong ngữ cảnh `@Target`.
- **METHOD:** phần tử khai báo method có tên, kiểu trả về (hoặc `void`) và danh sách tham số. Getter và setter đều là method; bản thân field mà chúng thao tác vẫn là một khai báo khác.
- **CONSTRUCTOR:** phần tử khai báo cách tạo đối tượng, mang cùng tên class và **không khai báo kiểu trả về**. Một constructor là thành phần riêng, không phải một method `void`.

Trong Java, ba tên này là các hằng của enum chuẩn `java.lang.annotation.ElementType`, được tham chiếu trong meta-annotation `java.lang.annotation.Target`.

## 2. Khai báo phạm vi với @Target

Giới hạn chỉ một vị trí:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldOnly {
    String value();
}
```

Khi một kiểu annotation phải sử dụng trên **nhiều vị trí**, truyền một mảng các giá trị enum:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface ReviewMark {
    String value();
}
```

Hai đoạn trên là **khai báo annotation type minh họa**, có thể biên dịch trong tệp Java thích hợp. `@Target` đứng **trên định nghĩa annotation**, còn `@ReviewMark("...")` hoặc `@FieldOnly("...")` đứng trên phần tử mà chúng đánh dấu.

Với `ReviewMark`, cả ba vị trí được cho phép; điều này **không bắt buộc** phải gắn annotation lên tất cả field, method hoặc constructor. Mỗi nơi muốn gắn đều được chọn độc lập.

### Nếu bỏ @Target?

Nếu một annotation type **không có `@Target`**, theo JLS, nó mặc định áp dụng được trong các ngữ cảnh **khai báo**. Điều đó không tự cho phép sử dụng trong mọi ngữ cảnh kiểu như `List<@Tag String>`; dùng ở type-use cần quyền thích hợp qua `ElementType.TYPE_USE`.

Để hợp đồng annotation rõ ràng, nên khai báo `@Target` chính xác với những vị trí consumer thực sự hỗ trợ. Một annotation chỉ được thiết kế để xử lý field mà lại cho phép gắn tùy ý lên method rất dễ gây hiểu nhầm.

### @Target khác @Retention

Hai meta-annotation giải quyết hai câu hỏi độc lập:

- `@Target`: **Được dùng annotation trên thành phần nào?**
- `@Retention`: **Annotation được giữ đến giai đoạn nào?** `SOURCE`, `CLASS`, hoặc `RUNTIME`.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface TrackedMethod {
    String value();
}
```

`TrackedMethod` chỉ áp dụng cho **khai báo method**, đồng thời cho phép code reflection truy xuất annotation trên method khi chạy. Nếu không khai báo `@Retention`, mặc định là `CLASS`, nên không nên trông chờ `getAnnotation()` tìm được annotation đó tại runtime.

Cả `@Target` và `@Retention` chỉ khai báo metadata. Java không tự thực hiện ghi log, kiểm tra quyền hay lưu database vì một annotation tùy chỉnh được đặt đúng vị trí.

## 3. FIELD: trường dữ liệu và enum constant

Ví dụ hợp lệ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldLabel {
    String value();
}

class Customer {
    @FieldLabel("database-key")
    private String customerId;

    @FieldLabel("display")
    public static final String CATEGORY = "CUSTOMER";
}
```

Ở đây, cả `customerId` và `CATEGORY` đều là **field**, dù một field là instance/private và field kia là static/final. `FIELD` không đồng nghĩa với “biến primitive” hay “biến không thể thay đổi”; nó chỉ định vị trí khai báo.

Với enum, hằng enum cũng là một vị trí thuộc `FIELD`:

```java
// Giả sử FieldLabel đã được khai báo như ví dụ phía trên.
enum OrderStatus {
    @FieldLabel("waiting")
    PENDING,

    @FieldLabel("done")
    COMPLETED
}
```

Đây là **đoạn minh họa bổ sung** sử dụng `FieldLabel` đã khai báo. Annotation có `@Target(FIELD)` hợp lệ trên enum constants.

### FIELD không áp dụng cho biến cục bộ

Ví dụ **cố ý lỗi biên dịch**:

```java
// FieldLabel chỉ có @Target(FIELD).
class InvalidLocal {
    void execute() {
        @FieldLabel("temporary")
        int attempts = 0;  // SAI: đây là LOCAL_VARIABLE, không phải FIELD.
    }
}
```

Cùng kiểu dữ liệu `int` không có nghĩa cùng ngữ cảnh khai báo. `int attempts` nằm trong thân method là biến cục bộ, thuộc `ElementType.LOCAL_VARIABLE`, còn `int attempts` trực tiếp trong class là field.

**FIELD cũng không tự đi theo getter.** Gắn `@FieldLabel` trên field `customerId` không làm method `getCustomerId()` tự được gắn annotation đó. Một số thư viện có quy tắc “field access” hoặc “property access” riêng; đây là quyết định của framework đang đọc metadata, không phải tác dụng mặc định của `@Target(FIELD)`.

## 4. METHOD: khai báo hành vi

Ví dụ hợp lệ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface ActionLabel {
    String value();
}

class UserService {
    @ActionLabel("query")
    public String findName() {
        return "An";
    }

    @ActionLabel("command")
    public void rename(String newName) {
        // Nội dung xử lý được lược bỏ trong ví dụ target.
    }
}
```

`findName()` và `rename(...)` là method nên có thể gắn `@ActionLabel`. Điều này không phụ thuộc vào method có trả về giá trị, có nhận tham số hay có modifier `public`.

Các vị trí method khác cũng có thể dùng annotation tương ứng:

- Khai báo method trong interface, bao gồm method abstract, default hoặc static.
- Khai báo method instance/static trong class.
- Method getter/setter.
- Các **annotation element** như `String value();` bên trong một `@interface` cũng thuộc ngữ cảnh method declaration theo JLS.

### METHOD không phải lời gọi method

Ví dụ sau **không hợp lệ**, vì ở dòng sau comment, `@ActionLabel` được đặt trước câu lệnh gọi thay vì khai báo method:

```java
// Minh họa SAI; không phải chương trình biên dịch được.
void perform(UserService service) {
    @ActionLabel("call")
    service.findName();
}
```

Annotation dạng `METHOD` nằm trên **khai báo** `findName()`, không nằm ở mỗi nơi gọi. Muốn thu thập thông tin khi method được gọi, cần cơ chế runtime rõ ràng (ví dụ interceptor/proxy hoặc instrumentation) đọc metadata và chủ động thực hiện hành động tương ứng.

### @Override là ví dụ quen thuộc

`@Override` là annotation chuẩn có `@Target(METHOD)`. Compiler dùng nó kiểm tra rằng một method thực sự override hoặc implement method phù hợp từ supertype:

```java
class Parent {
    void execute() {}
}

class Child extends Parent {
    @Override
    void execute() {}
}
```

Đoạn trên biên dịch hợp lệ. Nếu viết nhầm tên method, `@Override` sẽ giúp compiler phát hiện lỗi. `@Override` cũng không được đặt trên constructor.

## 5. CONSTRUCTOR: khai báo khởi tạo đối tượng

Một constructor có cùng tên với class và không có kiểu trả về. Nó được khai báo trong class; khác với cú pháp **gọi constructor** bằng `new`.

Ví dụ hợp lệ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.CONSTRUCTOR)
@interface InitLabel {
    String value();
}

class Report {
    @InitLabel("empty")
    public Report() {
    }

    @InitLabel("named")
    public Report(String title) {
    }
}
```

Hai constructor overload có chữ ký khác nhau, và annotation có thể gắn riêng cho từng constructor. Java không lấy annotation trên một constructor rồi mặc định áp dụng cho tất cả constructor khác của cùng class.

**CONSTRUCTOR không phải câu lệnh `new`.** Đoạn này là **ví dụ cố ý sai**:

```java
// Sai: annotation declaration-target không gắn vào biểu thức new.
Report report = @InitLabel("at-call") new Report();
```

Ở đây `@InitLabel` chỉ cho phép trên **constructor declaration**. Các dạng annotation được phép trong một số **type-use contexts** là cơ chế khác; ví dụ này không thể dùng annotation CONSTRUCTOR để gắn metadata lên mỗi lần khởi tạo.

### Method có tên giống class nhưng có kiểu trả về thì sao?

```java
class Printer {
    // Đây là CONSTRUCTOR.
    Printer() {
    }

    // Đây là METHOD bình thường vì khai báo kiểu trả về void.
    void Printer(int copies) {
    }
}
```

Dù tên `Printer` xuất hiện ở cả hai, `Printer()` là constructor và `void Printer(int copies)` là method. Để gắn annotation lần lượt lên hai khai báo, cần đích `CONSTRUCTOR` và `METHOD` phù hợp.

### Constructor mặc định và constructor của lớp cha

Nếu không viết constructor nào, compiler có thể cung cấp default constructor theo quy tắc của Java. Không có chỗ trong source để đặt một annotation tùy chọn riêng lên **constructor khai báo ngầm** đó. Khi cần annotation cho constructor, hãy tự khai báo constructor phù hợp.

Constructor **không được kế thừa** từ superclass. Annotation trên constructor của superclass không tự xuất hiện trên constructor của subclass, kể cả khi subclass gọi `super(...)`.

## 6. Vị trí hợp lệ và trường hợp không hợp lệ

Giả sử có một annotation:

```java
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Marker {}
```

Đoạn này **minh họa khai báo** và cần import `Target`, `ElementType` hoặc viết tên đầy đủ để biên dịch. Có thể đặt `@Marker` trên field, method và constructor.

Tuy nhiên, **nó không được phép** gắn lên:

| Vị trí | Đích tương ứng | Lý do `@Marker` không hợp lệ |
| --- | --- | --- |
| Khai báo class `class Device` | `TYPE` | `TYPE` không có trong tập target |
| Tham số `void save(String id)` | `PARAMETER` | `PARAMETER` chưa được cho phép |
| Biến cục bộ `int retries` trong method | `LOCAL_VARIABLE` | Không phải field |
| Cách sử dụng kiểu trong generic `List<@Marker String>` | `TYPE_USE` | Không hỗ trợ type-use |
| Khai báo package/module | `PACKAGE` / `MODULE` | Nằm ngoài ba target |
| Lời gọi `run()` hoặc `new Device()` | Không phải METHOD/CONSTRUCTOR declaration | Ba target chỉ dành cho vị trí khai báo |

Đừng tự suy ra `FIELD` từ việc một tham số hay một biến “đang chứa dữ liệu”. Trong Java, loại **khai báo** quyết định target.

### Ví dụ lỗi compiler trực tiếp

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface MethodOnly {}

class InvalidPlacement {
    @MethodOnly
    InvalidPlacement() { // LỖI: @MethodOnly không áp dụng cho constructor.
    }
}
```

Đoạn trên **cố ý không biên dịch được**; nó minh họa compiler kiểm tra tính phù hợp target trước khi chương trình chạy. Để sửa, đổi target của annotation thành `CONSTRUCTOR` (nếu annotation thực sự dùng cho constructor), hoặc chuyển annotation sang một method hợp lệ.

## 7. Ví dụ Java 17+ độc lập: cả ba target và reflection

Tạo **một file `TargetKindsDemo.java`** với toàn bộ nội dung bên dưới. Đây là chương trình đầy đủ: annotation được định nghĩa một lần và dùng trên field, method và constructor của cùng một class.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Audit {
    String value();
}

class Invoice {
    @Audit("field:code")
    private final String code;

    @Audit("constructor:create")
    public Invoice(String code) {
        this.code = code;
    }

    @Audit("method:read")
    public String getCode() {
        return code;
    }
}

public class TargetKindsDemo {
    public static void main(String[] args) throws NoSuchFieldException,
            NoSuchMethodException {
        Class<Invoice> type = Invoice.class;

        Audit fieldTag = type.getDeclaredField("code")
                .getAnnotation(Audit.class);
        Audit methodTag = type.getDeclaredMethod("getCode")
                .getAnnotation(Audit.class);
        Audit constructorTag = type.getDeclaredConstructor(String.class)
                .getAnnotation(Audit.class);

        System.out.println(fieldTag.value());
        System.out.println(methodTag.value());
        System.out.println(constructorTag.value());

        Invoice invoice = new Invoice("INV-42");
        System.out.println(invoice.getCode());
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 TargetKindsDemo.java
java TargetKindsDemo
```

Stdout **chính xác** từ lệnh `java TargetKindsDemo`:

```text
field:code
method:read
constructor:create
INV-42
```

Lý do:

1. `getDeclaredField("code")` trả về `Field` đại diện cho khai báo `code`, nơi có `@Audit("field:code")`.
2. `getDeclaredMethod("getCode")` trả về `Method` đại diện method getter, nơi có `@Audit("method:read")`.
3. `getDeclaredConstructor(String.class)` trả về `Constructor<Invoice>` tương ứng với constructor nhận một `String`. Metadata của nó là `constructor:create`.
4. Cuối cùng, `new Invoice("INV-42")` gọi constructor bình thường; `getCode()` trả về giá trị field. Annotation không thay đổi logic đọc/ghi field trong thân method.

Ví dụ dùng `@Retention(RUNTIME)` nên ba lời gọi `getAnnotation(Audit.class)` trả về annotation khác `null`. Nếu đổi retention sang `SOURCE` hoặc `CLASS`, annotation không xuất hiện qua reflection thông thường; khi gọi `value()` trên kết quả `null` sẽ gây `NullPointerException`. Để thử retention an toàn, kiểm tra `tag == null` trước khi đọc `value()`.

### Chọn đúng API reflection

| Đối tượng cần đọc | API lấy thành phần | Loại phản chiếu |
| --- | --- | --- |
| Field tên `code` | `Invoice.class.getDeclaredField("code")` | `java.lang.reflect.Field` |
| Method `getCode()` | `Invoice.class.getDeclaredMethod("getCode")` | `java.lang.reflect.Method` |
| Constructor nhận `String` | `Invoice.class.getDeclaredConstructor(String.class)` | `java.lang.reflect.Constructor` |

Đối với method overload, `getDeclaredMethod` cần thêm đúng các lớp của **kiểu tham số**; tương tự cho constructor overload. `getDeclared*` cho phép tìm khai báo kể cả private nhưng **chỉ đọc metadata không có nghĩa tự được quyền gọi private member** khi có ràng buộc truy cập hoặc module.

Phân biệt `getDeclaredMethod` (khai báo trực tiếp trong class được xét) và `getMethod` (public method có thể được thừa hưởng). Việc tìm một method được kế thừa khác với việc annotation trên method gốc tự sao chép sang method override.

## 8. Vì sao annotation trên field không tự xuất hiện ở getter?

Xét một class:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
@interface Rule {}

class User {
    @Rule
    private String username;

    public String getUsername() {
        return username;
    }
}
```

Đây là **đoạn minh họa**, cần các import `Retention`, `RetentionPolicy`, `Target`, `ElementType` phù hợp.

Qua reflection, hai phần tử là hai khai báo riêng:

```java
// Minh họa biểu thức nếu class User và annotation Rule tồn tại:
User.class.getDeclaredField("username")
        .isAnnotationPresent(Rule.class);      // true
User.class.getDeclaredMethod("getUsername")
        .isAnnotationPresent(Rule.class);      // false
```

Một công cụ dữ liệu có thể **quy ước** ưu tiên field annotation hoặc getter annotation để tìm cấu hình. Một công cụ khác có thể duyệt cả hai. Java không áp đặt một ý nghĩa nghiệp vụ duy nhất cho các vị trí hợp lệ.

Nếu muốn đánh dấu cả field và getter, có thể gắn annotation trên từng khai báo (khi target cho phép). Cũng không nên kỳ vọng `@Inherited` làm method override “tự thừa kế” annotation: `@Inherited` chỉ điều khiển tra cứu annotation trên **class** theo superclass trong phạm vi mà đặc tả hỗ trợ.

## 9. Lưu ý đặc biệt: enum constant, record component và type-use

### Enum constant thuộc FIELD

```java
@Target(ElementType.FIELD)
@interface Flag {}

enum Mode {
    @Flag FAST,
    @Flag SAFE
}
```

Đây là các khai báo minh họa (cần import `Target` và `ElementType`). `FAST` và `SAFE` là enum constant, được tính là field declaration cho quy tắc target.

### Record component có quy tắc riêng

Từ Java 16, record có **record component** trong header. Java có `ElementType.RECORD_COMPONENT`, nhưng các annotation áp dụng cho field/method/parameter cũng có thể được dùng trên khai báo record component và **được lan truyền đến thành phần tương ứng** theo quy tắc của record.

Ví dụ minh họa:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Stored {}

record Product(@Stored String id) {}
```

Đây là một khai báo Java 17 hợp lệ. `@Stored` đủ điều kiện áp dụng cho record component và được lan truyền đến **field ngầm định** tương ứng. Vì vậy, `Product.class.getDeclaredField("id").isAnnotationPresent(Stored.class)` là `true`. Tuy nhiên, annotation này không tự là annotation của accessor theo `METHOD`, vì kiểu `Stored` chỉ khai báo `FIELD`.

Hãy đọc quy tắc propagation của record khi làm việc với validation, serialization hoặc persistence; không nên khẳng định mọi annotation được gắn trên component đều xuất hiện giống hệt trên field, accessor, constructor parameter và bản thân `RecordComponent`.

### TYPE_USE là nhánh khác

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface NonBlankType {}

class Names {
    List<@NonBlankType String> values;
}
```

Ở đây `@NonBlankType` gắn trên **lần sử dụng kiểu `String` trong tham số generic**, khác với gắn trên một khai báo `FIELD`. `FIELD`, `METHOD`, `CONSTRUCTOR` không thay thế được `TYPE_USE`.

Một vị trí cú pháp có thể vừa là chỗ khai báo vừa gần một kiểu dữ liệu. Nếu annotation cho phép cả declaration target và `TYPE_USE`, JLS có quy tắc riêng xác định annotation có thể áp dụng cho cả hai. Với bài này, các ví dụ chính chỉ dùng ba declaration targets để làm rõ ý nghĩa.

## 10. Các lỗi phổ biến khi sử dụng FIELD, METHOD và CONSTRUCTOR

**Lỗi 1 — Gắn FIELD lên biến cục bộ.** Field là biến thành viên của class/interface, không phải mọi biến có tên. Cần `LOCAL_VARIABLE` nếu annotation thực sự phải áp dụng cho khai báo biến cục bộ.

**Lỗi 2 — Xem getter là field.** Getter dù đọc field vẫn là method, cần `METHOD`. Nên đọc tài liệu framework để quyết định cấu hình bằng field hay property.

**Lỗi 3 — Dùng METHOD cho constructor.** Constructor không có kiểu trả về, không phải method; cần `CONSTRUCTOR`.

**Lỗi 4 — Gắn annotation lên lời gọi.** `@Target(METHOD)` là trên khai báo method, không phải mọi lệnh `foo()`. `@Target(CONSTRUCTOR)` là trên khai báo constructor, không phải biểu thức `new`.

**Lỗi 5 — Bỏ retention nhưng dùng reflection.** `@Target` có thể đúng mà reflection vẫn không thấy annotation nếu retention chưa phải `RUNTIME`.

**Lỗi 6 — Gắn annotation là tự có hành vi.** Annotation custom như `@Audit` chỉ mang dữ liệu. Muốn ghi audit log phải có consumer thực sự đọc annotation và thực thi cơ chế ghi log.

**Lỗi 7 — Nghĩ FIELD/METHOD tự áp dụng cho record component giống class thường.** Record có quy tắc áp dụng/lan truyền annotation đặc biệt. Cần xét target, retention và thành phần đích cụ thể.

**Lỗi 8 — Nhầm kế thừa thành viên với sao chép annotation.** Override method hoặc khai báo constructor ở subclass không khiến annotation ở method/constructor gốc tự xuất hiện trên khai báo mới.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Gắn `@Target(FIELD)` lên `private String name;` có hợp lệ không? Còn `String name` nằm trong method?

**Đáp án:** Trên field hợp lệ. Biến nằm trong method là `LOCAL_VARIABLE`, nên annotation chỉ cho phép `FIELD` không hợp lệ ở đó.

**Câu 2.** `@Target(METHOD)` có đặt ngay trước `service.execute()` được không?

**Đáp án:** Không. `METHOD` áp dụng cho **khai báo method**, không phải câu lệnh gọi.

**Câu 3.** Hai overload `Customer()` và `Customer(String id)` có phải cùng một constructor để annotation tự dùng chung không?

**Đáp án:** Không. Đây là hai constructor riêng với chữ ký khác nhau; annotation được khai báo riêng trên từng constructor nếu cần.

**Câu 4.** Vì sao reflection trả về `null` khi một annotation có `@Target(METHOD)` đúng nhưng không có `@Retention(RUNTIME)`?

**Đáp án:** `@Target` chỉ định vị trí. Mặc định retention là `CLASS`, không được reflection thông thường truy cập lúc chạy.

**Câu 5.** Một annotation chỉ dùng cho getter JavaBean cần target gì?

**Đáp án:** `ElementType.METHOD`, vì getter là method. Annotation riêng cho field được khai báo bằng `ElementType.FIELD`.

**Câu 6.** `@Target(FIELD)` có dùng trên enum constant được không?

**Đáp án:** Có. JLS xếp enum constants vào field declaration contexts.

**Câu 7.** Khi một annotation đặt trên record component được lan truyền sang field, điều đó có đồng nghĩa nó cũng tự nằm trên method accessor không?

**Đáp án:** Không. Cần xem annotation có hỗ trợ `METHOD` và quy tắc propagation tương ứng hay không.

## Tài liệu tham khảo

- [Java Language Specification 17, §9.6.4.1 — @Target và declaration contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1).
- [Java Language Specification 17, §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).
- [Java Language Specification 17, §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3).
- [Java SE 17 API — ElementType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 API — Target](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html).

Để áp dụng đúng trong dự án, hãy bắt đầu từ **loại khai báo** muốn đánh dấu, chọn `FIELD`, `METHOD` hoặc `CONSTRUCTOR` bằng `@Target`, rồi quyết định annotation cần được xử lý ở bước biên dịch hay runtime. Khi cần truy xuất annotation lúc chạy, hãy kiểm tra tiếp `@Retention` và API reflection phù hợp.
