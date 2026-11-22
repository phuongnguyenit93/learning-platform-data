# Đọc annotation trên Class, Field, Method và Constructor bằng Java Reflection

## 1. Annotation được đọc ở đâu khi chương trình chạy?

Java annotation là **metadata** gắn với một phần tử của chương trình. Bạn có thể khai báo annotation trên class, field, method và constructor, rồi dùng **Java Reflection API** để kiểm tra annotation nào được gắn ở mỗi vị trí. Điều này thường xuất hiện trong framework DI, ORM, kiểm thử, validation, mapping hoặc những thư viện có quy ước dựa trên annotation.

Để đọc annotation bằng reflection lúc chạy, cần hai điều kiện cơ bản:

1. Annotation type phải dùng **`@Retention(RetentionPolicy.RUNTIME)`**. Nếu chỉ có `SOURCE` hoặc `CLASS`, annotation không được truy xuất qua API reflection thông thường.
2. Chương trình phải tra cứu đúng **phần tử được đánh dấu**: metadata ở class không tự trở thành metadata ở field; metadata trên method không tự xuất hiện trên constructor.

Bốn đối tượng reflection thường gặp:

| Đích được đánh dấu | API đại diện | Cách lấy ví dụ |
| --- | --- | --- |
| Class/interface/enum/record | `java.lang.Class<?>` | `OrderService.class`; `obj.getClass()` |
| Field | `java.lang.reflect.Field` | `type.getDeclaredField("id")` |
| Method | `java.lang.reflect.Method` | `type.getDeclaredMethod("save", String.class)` |
| Constructor | `java.lang.reflect.Constructor<?>` | `type.getDeclaredConstructor(String.class)` |

`Class`, `Field`, `Method` và `Constructor` đều triển khai giao diện **`java.lang.reflect.AnnotatedElement`**. Giao diện này cung cấp các phương thức như `getAnnotation(...)`, `getDeclaredAnnotation(...)`, `getAnnotations()`, `getDeclaredAnnotations()` và các phương thức `ByType` để đọc annotation có thể lặp.

**Phân biệt:** Reflection đọc annotation trên **khai báo**; nó không tự chạy business logic hay thay đổi giá trị field. Nếu một framework đọc `@Transactional` hoặc `@Column` và thực hiện điều gì đó, đó là hành vi do framework xây dựng trên metadata, không phải hành vi tự động của Java chỉ vì annotation đã được khai báo.

## 2. Định nghĩa annotation có RUNTIME retention và đúng Target

Ví dụ muốn đánh dấu class, field, method và constructor bằng cùng một loại annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Info {
    String value();
}
```

Giải thích:

- `@Retention(RUNTIME)` giữ metadata để gọi reflection khi chạy.
- `@Target(TYPE)` cho phép gắn lên khai báo class (và những khai báo type phù hợp khác), `FIELD` lên khai báo field, `METHOD` lên khai báo method và `CONSTRUCTOR` lên khai báo constructor.
- `String value()` là phần tử bắt buộc. Khi gắn có thể dùng dạng rút gọn `@Info("mô tả")`.
- `@Target` chỉ quyết định **nơi có thể gắn annotation**, còn `@Retention` quyết định khả năng **lưu giữ và quan sát**. Hai thứ độc lập.
- Dù annotation có thể đặt trên nhiều đích, **mỗi vị trí có metadata riêng**. Ví dụ `@Info` trên class không tự xuất hiện trong `getAnnotation(Info.class)` của từng method.

Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`, nên reflection thời gian chạy không đọc được annotation đó. Một annotation với `@Retention(SOURCE)` có thể hữu ích cho compiler hoặc annotation processor nhưng không có mặt trong class file để reflection đọc.

## 3. Ví dụ Java 17+ độc lập: đọc đủ bốn vị trí

Tất cả khai báo dưới đây nằm trong **một tệp** tên `ReflectionAnnotationDemo.java`. Trong đó có annotation runtime `@Info`, annotation không sẵn có qua reflection `@CompileOnly`, annotation `@Team` có tính kế thừa để chứng minh hành vi trên class, cùng một class nghiệp vụ chứa field, method và constructor được đánh dấu.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.TYPE,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.CONSTRUCTOR
})
@interface Info {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface CompileOnly {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Team {
    String value();
}

@Info("payment-service")
@CompileOnly
@Team("backend")
class PaymentService {
    @Info("transaction-id")
    private final String id;

    @Info("public-constructor")
    public PaymentService(String id) {
        this.id = id;
    }

    @Info("private-constructor")
    private PaymentService() {
        this("default");
    }

    @Info("pay-method")
    public String pay(int amount) {
        return id + ":" + amount;
    }

    @Info("internal-validation")
    private void validate() {
    }
}

class PaymentChild extends PaymentService {
    PaymentChild() {
        super("child");
    }
}

public class ReflectionAnnotationDemo {
    public static void main(String[] args)
            throws NoSuchFieldException, NoSuchMethodException {
        Class<PaymentService> type = PaymentService.class;
        Info classInfo = type.getAnnotation(Info.class);
        System.out.println("Class: " + classInfo.value());
        System.out.println("CLASS retention visible: "
                + type.isAnnotationPresent(CompileOnly.class));

        Field idField = type.getDeclaredField("id");
        System.out.println("Field: "
                + idField.getAnnotation(Info.class).value());

        Method payMethod = type.getDeclaredMethod("pay", int.class);
        System.out.println("Method: "
                + payMethod.getAnnotation(Info.class).value());

        Method validateMethod = type.getDeclaredMethod("validate");
        System.out.println("Private method: "
                + validateMethod.getAnnotation(Info.class).value());

        Constructor<PaymentService> publicCtor =
                type.getDeclaredConstructor(String.class);
        System.out.println("Constructor: "
                + publicCtor.getAnnotation(Info.class).value());

        Constructor<PaymentService> privateCtor =
                type.getDeclaredConstructor();
        System.out.println("Private constructor: "
                + privateCtor.getAnnotation(Info.class).value());

        System.out.println("Child inherited Team: "
                + PaymentChild.class.getAnnotation(Team.class).value());
        System.out.println("Child declares Team: "
                + (PaymentChild.class.getDeclaredAnnotation(Team.class) != null));
        System.out.println("Child inherits Info: "
                + (PaymentChild.class.getAnnotation(Info.class) != null));
    }
}
```

Dùng **JDK 17 trở lên**, mở terminal ở thư mục có tệp:

```bash
javac --release 17 ReflectionAnnotationDemo.java
java ReflectionAnnotationDemo
```

**Stdout:**

```text
Class: payment-service
CLASS retention visible: false
Field: transaction-id
Method: pay-method
Private method: internal-validation
Constructor: public-constructor
Private constructor: private-constructor
Child inherited Team: backend
Child declares Team: false
Child inherits Info: false
```

Phân tích:

1. `PaymentService.class` là đối tượng `Class<PaymentService>` đại diện cho kiểu. `getAnnotation(Info.class)` tìm metadata `@Info("payment-service")` **trên class**.
2. `@CompileOnly` có retention `CLASS` nên `isAnnotationPresent(CompileOnly.class)` trả `false` khi đọc bằng reflection, mặc dù khai báo annotation có trong source và class file.
3. `getDeclaredField("id")` lấy field `private final String id`. `Field.getAnnotation(Info.class)` trả `"transaction-id"`, không phải annotation trên class.
4. `getDeclaredMethod("pay", int.class)` dùng **tên phương thức và danh sách kiểu tham số** để định vị method. Vì method nhận `int`, phải truyền `int.class`; `getDeclaredMethod("pay")` sẽ không tìm thấy method này.
5. `getDeclaredMethod("validate")` lấy method `private` không tham số. Có thể **đọc annotation** từ đối tượng `Method` được trả về mà **không cần gọi `setAccessible(true)`**.
6. `getDeclaredConstructor(String.class)` lấy constructor nhận chuỗi; `getDeclaredConstructor()` lấy constructor không tham số, dù nó là `private`. Cả hai có annotation riêng.
7. `@Team` được đánh dấu `@Inherited` nên `PaymentChild.class.getAnnotation(Team.class)` tìm được giá trị từ superclass, trong khi `getDeclaredAnnotation(Team.class)` chỉ xét annotation khai báo trực tiếp trên `PaymentChild` và trả `null`.
8. `@Info` **không** được đánh dấu `@Inherited`, nên `PaymentChild.class.getAnnotation(Info.class)` trả `null` dù superclass mang `@Info`.

Ví dụ chỉ **đọc metadata**, không truy cập giá trị field và không gọi private method/constructor. Nó cũng không tạo instance `PaymentService` hay `PaymentChild`. Từ `Class` và các đối tượng reflection tương ứng đã có thể đọc annotation trên khai báo.

## 4. Đọc annotation trên Class

Ví dụ cơ bản:

```java
Class<PaymentService> type = PaymentService.class;
Info info = type.getAnnotation(Info.class);

if (info != null) {
    System.out.println(info.value());
}
```

`Class.getAnnotation(Info.class)` trả về annotation `Info` theo quy tắc “present annotation” của `AnnotatedElement`, hoặc `null` nếu không có. Luôn xét trường hợp `null` khi viết code dùng cho nhiều class thay vì mặc định annotation chắc chắn tồn tại.

Một số API thường dùng:

| API trên `Class` | Kết quả |
| --- | --- |
| `isAnnotationPresent(Info.class)` | `true` nếu annotation thuộc kiểu đó được coi là hiện diện theo quy tắc API; `false` nếu không |
| `getAnnotation(Info.class)` | Một annotation `Info` hoặc `null` |
| `getDeclaredAnnotation(Info.class)` | Chỉ annotation `Info` được khai báo trực tiếp trên class, hoặc `null` |
| `getAnnotations()` | Các annotation runtime hiện diện trên class, gồm annotation kế thừa phù hợp |
| `getDeclaredAnnotations()` | Các annotation runtime **khai báo trực tiếp** trên class |
| `getAnnotationsByType(Info.class)` | Mảng các annotation cùng kiểu; hỗ trợ annotation lặp và quy tắc kế thừa phù hợp |
| `getDeclaredAnnotationsByType(Info.class)` | Mảng các annotation cùng kiểu khai báo trên class, không tra superclass |

**Không phụ thuộc vào thứ tự của mảng `getAnnotations()` hoặc `getDeclaredAnnotations()`** khi có nhiều kiểu annotation khác nhau. Nếu muốn một annotation cụ thể, truy vấn theo `Info.class` thay vì lấy `[0]` rồi giả định đó là annotation mong muốn.

### 4.1. Kế thừa annotation trên class

Annotation chỉ được “kế thừa” theo cách của `Class.getAnnotation`/`getAnnotations` khi annotation type có **`@Inherited`**, và áp dụng trong chuỗi **superclass**. Đặt `@Inherited` lên annotation không khiến method/field/constructor tự kế thừa annotation; interface triển khai cũng không truyền annotation cho class theo cơ chế này.

Trong ví dụ:

- `Team` được định nghĩa với `@Inherited`; class con không tự khai báo `@Team` thì `getAnnotation(Team.class)` có thể nhận từ superclass.
- `Info` không có `@Inherited`; class con không nhận `@Info` từ cha qua `getAnnotation(Info.class)`.
- `getDeclaredAnnotation` trên class con **không** tự tra superclass dù annotation type có `@Inherited`.

Một class con nếu tự khai báo annotation cùng kiểu có thể thay thế kết quả kế thừa tương ứng. Nếu chương trình cần hợp nhất metadata ở nhiều cấp class, phải xây dựng quy tắc duyệt superclass riêng.

## 5. Đọc annotation trên Field

`Field` đại diện cho **khai báo field**, không phải giá trị riêng trong một instance.

```java
Field field = PaymentService.class.getDeclaredField("id");
Info info = field.getAnnotation(Info.class);
System.out.println(info.value()); // transaction-id
```

Các API tìm field:

- `getDeclaredField("id")`: tìm field khai báo **ngay trong class**, bao gồm `private`, `protected`, package-private và `public`; **không** tìm field được kế thừa từ superclass.
- `getField("id")`: tìm **public field** thuộc class hoặc được kế thừa phù hợp; không dùng để lấy private field `id` trong ví dụ.
- `getDeclaredFields()`: tất cả field khai báo ngay trong class, có thể gồm field tổng hợp (*synthetic*) do compiler tạo. Không nên phụ thuộc thứ tự trả về.
- `getFields()`: các public field được API quy định là thành viên của class, bao gồm trường hợp kế thừa phù hợp.

Sau khi có `Field`, gọi `field.getAnnotation(Info.class)` để đọc metadata trên khai báo field. Với class có nhiều object, annotation trên khai báo field là metadata chung; **không phải một bản sao được tạo cho từng object**.

### Đọc annotation và đọc giá trị field là hai việc khác

```java
Info metadata = field.getAnnotation(Info.class);
// metadata.value() là "transaction-id"
// field.get(instance) là một thao tác khác: đọc giá trị field trên instance
```

Nếu field là private, **đọc annotation bằng `Field.getAnnotation` không yêu cầu bỏ kiểm tra truy cập**. Nhưng muốn đọc giá trị private field bằng `field.get(instance)` thì phải xét kiểm soát truy cập và quy tắc module; `setAccessible(true)` không phải lúc nào cũng được cho phép (đặc biệt khi làm việc qua named module không mở package).

Không nên gọi `setAccessible(true)` chỉ vì mục đích duy nhất là đọc annotation.

## 6. Đọc annotation trên Method

`Method` đại diện cho **khai báo method**. Khi có nhiều method cùng tên (*overloading*), phải phân biệt bằng danh sách kiểu tham số.

```java
Method method = PaymentService.class.getDeclaredMethod("pay", int.class);
Info info = method.getAnnotation(Info.class);
System.out.println(info.value()); // pay-method
```

Các phương thức tra cứu:

| API | Phạm vi tìm |
| --- | --- |
| `getDeclaredMethod("pay", int.class)` | Method có tên/chữ ký tham số được khai báo **trên chính class**, mọi mức truy cập |
| `getMethod("pay", int.class)` | Method `public`, bao gồm method được kế thừa theo quy tắc reflection |
| `getDeclaredMethods()` | Các method được khai báo trên chính class, kể cả private, nhưng không gồm method chỉ kế thừa từ cha |
| `getMethods()` | Các public method, gồm method kế thừa phù hợp |

`getDeclaredMethod` và `getMethod` nhận các đối tượng `Class<?>` đại diện cho **kiểu tham số** theo đúng thứ tự. Với method không có tham số, chỉ viết `getDeclaredMethod("validate")` hoặc truyền varargs rỗng. Kiểu trả về không xuất hiện trong tham số tra cứu method; Java không cho overload chỉ theo kiểu trả về.

Method `private` vẫn có thể được lấy metadata:

```java
Method privateMethod = PaymentService.class.getDeclaredMethod("validate");
Info metadata = privateMethod.getAnnotation(Info.class);
System.out.println(metadata.value()); // internal-validation
```

**Annotation trên method không tự kế thừa theo `@Inherited`.** Nếu class con override một method từ cha mà không ghi lại annotation, truy vấn trên đối tượng `Method` của method override không tự trả annotation của method ở superclass. Một framework có thể tự thực hiện logic tìm annotation trong cây kế thừa, nhưng đó là cơ chế riêng của framework.

Với annotation đặt trên **tham số của method**, đối tượng phản chiếu tương ứng là `Parameter` hoặc các API như `Method.getParameterAnnotations()`; đây là vị trí metadata **khác** với annotation gắn trên bản thân method. Đừng mong `Method.getAnnotation(...)` thấy annotation chỉ đặt trên parameter.

## 7. Đọc annotation trên Constructor

`Constructor<?>` đại diện cho khai báo constructor, có thể có các overload với danh sách tham số khác nhau.

```java
Constructor<PaymentService> constructor =
        PaymentService.class.getDeclaredConstructor(String.class);

Info info = constructor.getAnnotation(Info.class);
System.out.println(info.value()); // public-constructor
```

Phân biệt:

- `getConstructor(String.class)` chỉ trả về **public constructor** khớp danh sách tham số.
- `getDeclaredConstructor(String.class)` trả về constructor được khai báo trên chính class, **dù public hay private**.
- `getConstructors()` trả các public constructor khai báo ở class.
- `getDeclaredConstructors()` trả các constructor khai báo ở class ở mọi mức truy cập.

**Constructor không được kế thừa** từ superclass. Class con có tập constructor riêng, nên tra cứu constructor của subclass không tự lấy constructor của superclass.

Trong ví dụ, `PaymentService` có hai constructor mang `@Info` khác nhau. Nếu bạn lấy constructor không tham số:

```java
Constructor<PaymentService> ctor =
        PaymentService.class.getDeclaredConstructor();
Info info = ctor.getAnnotation(Info.class);
System.out.println(info.value()); // private-constructor
```

Reflection có thể đọc annotation trên constructor private mà không cần `setAccessible(true)`. Tuy nhiên **gọi constructor private** bằng `ctor.newInstance()` là thao tác khác, chịu kiểm tra quyền truy cập và có thể thất bại. Đừng nhầm **đọc metadata** với **khởi tạo object**.

Một class chỉ có constructor mặc định do compiler sinh ra sẽ không tự nhiên nhận annotation mà bạn kỳ vọng trên một constructor được viết tường minh; muốn đánh dấu constructor, khai báo constructor và đặt annotation tại đúng vị trí. Đối với record, enum hoặc member inner class, chữ ký constructor ở mức reflection có thể có những đặc điểm bổ sung, cần xác định đúng tham số thực tế khi tra cứu.

## 8. getAnnotation, getDeclaredAnnotation và getAnnotationsByType

Cả bốn loại reflection ở bài này đều theo giao diện `AnnotatedElement`. Các API có khác biệt quan trọng:

### `getAnnotation(T.class)`

Trả một annotation kiểu `T` **được coi là hiện diện**, hoặc `null`. Với `Class`, quy tắc `@Inherited` có thể cho phép lấy annotation từ superclass. Với `Field`, `Method` và `Constructor`, không áp dụng cùng cơ chế kế thừa annotation như trên class.

### `getDeclaredAnnotation(T.class)`

Chỉ xét annotation **khai báo trên chính phần tử** (không tìm superclass). Dùng khi bạn muốn tránh nhận metadata kế thừa ở cấp class.

### `getAnnotations()` và `getDeclaredAnnotations()`

Trả mảng annotation nhìn thấy qua reflection (hoặc chỉ khai báo trực tiếp). Khi duyệt các phần tử, nên kiểm tra `annotation.annotationType()` và không dựa vào thứ tự giữa các kiểu annotation khác nhau.

### `getAnnotationsByType(T.class)` và `getDeclaredAnnotationsByType(T.class)`

Đặc biệt hữu ích khi `T` là **repeatable annotation** được khai báo với `@Repeatable(Container.class)`. Khi nhiều lần sử dụng `@T` được compiler biểu diễn thông qua container, `getAnnotation(T.class)` có thể trả `null`, còn `getAnnotationsByType(T.class)` mở container thích hợp và trả đủ các annotation thành phần theo quy tắc API.

Ví dụ minh họa (giả sử `Tag` là một repeatable annotation type với retention `RUNTIME`):

```java
@Tag("read")
@Tag("write")
class ReportEndpoint {}
```

Thay vì chỉ gọi `ReportEndpoint.class.getAnnotation(Tag.class)`, hãy dùng `getAnnotationsByType(Tag.class)` nếu cần **toàn bộ Tag**. Tương tự, `getDeclaredAnnotationsByType` giới hạn ở vị trí khai báo hiện tại.

**Lưu ý:** đây chỉ là cú pháp minh họa, muốn biên dịch phải khai báo `Tag` và container đúng với `@Repeatable`. Annotation lặp là một vấn đề về số lần hiện diện và cách reflection truy vấn, không thay đổi bản chất của `Class`, `Field`, `Method` hay `Constructor`.

## 9. Phân biệt annotation trên khai báo với TYPE_USE và TYPE_PARAMETER

Không phải tất cả annotation nhìn thấy trong source đều được tìm bằng `field.getAnnotation(...)`.

Ví dụ, một annotation được định nghĩa với `@Target(ElementType.TYPE_USE)` có thể đặt trên **một lần sử dụng kiểu**, như kiểu trả về của method, kiểu phần tử mảng hoặc đối số kiểu generic. Metadata type-use được mô tả qua các API thuộc họ `AnnotatedType`, ví dụ:

- `Field.getAnnotatedType()`;
- `Method.getAnnotatedReturnType()`;
- `Method.getAnnotatedParameterTypes()`;
- `Constructor.getAnnotatedParameterTypes()`.

Trong khi đó `Field.getAnnotation(...)` tìm annotation **trực tiếp trên khai báo field**; `Method.getAnnotation(...)` tìm annotation **trực tiếp trên khai báo method**. Khi một annotation có nhiều target hoặc cú pháp làm xuất hiện annotation ở một vị trí type-use, cần kiểm tra đúng API cho loại metadata muốn đọc.

Tương tự, annotation trên **type parameter** của class/method (`ElementType.TYPE_PARAMETER`) và annotation trên **tham số thường** của method/constructor (`ElementType.PARAMETER`) thuộc các vị trí khác nhau. Đọc annotation trên khai báo class/method không đồng nghĩa với đọc toàn bộ metadata trên mọi thành phần bên trong chúng.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `getAnnotation(...)` trả `null` dù trong source có annotation | Retention không phải `RUNTIME`; tìm nhầm phần tử; hoặc annotation lặp được chứa gián tiếp | Kiểm tra `@Retention`, `@Target`, vị trí gắn và cân nhắc `getAnnotationsByType` |
| `getDeclaredField("id")` báo `NoSuchFieldException` | Field không được khai báo trong class đó, khác tên hoặc nằm ở superclass | Kiểm tra đúng class/tên; duyệt superclass hoặc dùng API phù hợp nếu là public field |
| `getDeclaredMethod("pay")` báo `NoSuchMethodException` | Method thực tế có tham số `int` | Dùng `getDeclaredMethod("pay", int.class)` |
| `getMethod("validate")` không thấy method | Method là `private` | Dùng `getDeclaredMethod("validate")` |
| `getConstructor()` không thấy constructor private | `getConstructor` chỉ tra public constructor | Dùng `getDeclaredConstructor()` |
| Annotation trên subclass khác dự kiến | `@Inherited` chỉ hỗ trợ tra superclass cho annotation trên khai báo class | Phân biệt `getAnnotation` với `getDeclaredAnnotation` |
| Đọc được annotation private member nhưng không đọc được giá trị hoặc không gọi được member | Reflection metadata và quyền **truy cập thực thi** là hai vấn đề | Tôn trọng Java access/JPMS; không tùy tiện bật `setAccessible` |
| Đọc `@Info` trên class nhưng không thấy `@Info` của method | Metadata gắn trên các khai báo khác nhau | Lấy đúng đối tượng `Method` hoặc `Field` rồi gọi `getAnnotation` |
| Duyệt `getDeclaredMethods()` rồi coi phần tử đầu tiên là method mong muốn | Thứ tự reflection array không phải hợp đồng; có thể có synthetic/bridge methods | Lọc theo tên, chữ ký tham số, modifier và điều kiện cần thiết |

### Luôn xử lý trường hợp annotation vắng mặt

Một thư viện quét nhiều class không nên dùng:

```java
Info info = type.getAnnotation(Info.class);
String value = info.value(); // Có thể NullPointerException nếu thiếu annotation
```

Thay bằng:

```java
Info info = type.getAnnotation(Info.class);
if (info != null) {
    System.out.println(info.value());
}
```

Cả hai đoạn là **minh họa bên trong một method** có biến `type` kiểu `Class<?>` và annotation type `Info` đã được khai báo; không phải chương trình standalone. Cũng có thể dùng `isAnnotationPresent(Info.class)` để kiểm tra trước, nhưng nếu cần giá trị element thì lấy annotation một lần và kiểm tra `null` thường là đủ.

### Khi Reflection không tìm thấy member

Các phương thức tra cứu theo tên/chữ ký có thể ném `NoSuchFieldException` hoặc `NoSuchMethodException`. Chúng là lỗi **không tìm thấy phần tử**, khác với `getAnnotation(...) == null` nghĩa là **đã có phần tử phản chiếu nhưng không tìm thấy annotation**. Hai trường hợp cần xử lý riêng khi thiết kế bộ đọc metadata.

### Không tự giả định annotation thực hiện logic

Ví dụ `@Info("pay-method")` không làm `pay` được gọi, không tự ghi log và không thay đổi giao dịch. Reflection chỉ trả metadata. Nếu muốn dùng thông tin đó để routing, validation hay logging, phải xây dựng code xử lý riêng, đồng thời kiểm tra kiểu, giá trị và các quy tắc nghiệp vụ.

## 11. Cách tổ chức bộ đọc annotation trong dự án

Một cách làm có kiểm soát:

1. **Xác định contract annotation:** annotation dùng để đánh dấu loại khai báo nào và phải có `RUNTIME` hay không.
2. **Xác định phạm vi quét:** đọc một class cụ thể, toàn bộ field, method, constructor hay nhiều class. Đừng tự quét toàn classpath nếu không cần thiết.
3. **Chọn đúng API tìm phần tử:** `getDeclaredField`/`getDeclaredMethod`/`getDeclaredConstructor` cho phần tử khai báo trực tiếp (gồm private); API không có `Declared` cho public members theo quy tắc tương ứng.
4. **Tra cứu và kiểm tra null:** `getAnnotation` khi cần một annotation; `getAnnotationsByType` khi annotation lặp.
5. **Quy định rõ kế thừa:** nếu đọc annotation class có `@Inherited`, phân biệt dữ liệu khai báo riêng và dữ liệu có thể được coi là kế thừa. Với field/method, đừng tự áp dụng logic kế thừa của class annotation.
6. **Không trộn việc đọc và việc thực thi:** bộ scanner metadata nên lấy và xác thực annotation trước; code xử lý nghiệp vụ là bước sau.
7. **Cân nhắc quyền truy cập và module:** đọc annotation của private member thường không cần can thiệp `setAccessible`; gọi private member hoặc đọc giá trị private field có quy tắc bảo vệ riêng.
8. **Kiểm thử bằng Java 17+:** đặt annotation trên cả class/field/method/constructor, bổ sung một annotation `CLASS` và một subclass để xác nhận các trường hợp vắng mặt/kế thừa.

**Ghi nhớ:** `Class`, `Field`, `Method` và `Constructor` đều cho phép đọc annotation runtime qua `AnnotatedElement`, nhưng mỗi object reflection mô tả **một cấp khai báo khác nhau**. Bắt đầu bằng đúng member, kiểm tra retention, dùng đúng phương thức `getAnnotation`/`getDeclaredAnnotation`/`getAnnotationsByType`, sau đó mới diễn giải metadata theo nghiệp vụ.
