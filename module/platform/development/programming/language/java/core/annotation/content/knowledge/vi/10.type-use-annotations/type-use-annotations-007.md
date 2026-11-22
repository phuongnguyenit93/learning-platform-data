# Tham số nhận (receiver parameter) và annotation của kiểu this trong Java

## 1. Receiver parameter là gì?

Java cho phép viết **receiver parameter** để chỉ rõ kiểu của đối tượng nhận lời gọi một **instance method**, hoặc kiểu của đối tượng bao ngoài khi khai báo constructor của một **inner class**. Mục tiêu chính của cú pháp này là tạo ra một **vị trí trong mã nguồn để gắn annotation lên kiểu của receiver**.

Ví dụ:

```java
class Account {
    void print(Account this, String message) {
        System.out.println(message);
    }
}
```

Trong `void print(Account this, String message)`:

- `Account this` là **receiver parameter**: biểu diễn kiểu của đối tượng `Account` đang nhận lời gọi `print`.
- `String message` là **formal parameter** (tham số hình thức) thật sự, nhận đối số khi gọi.
- `Account this` **không khai báo một biến mới**, **không nhận thêm đối số** và **không làm thay đổi số tham số hoặc chữ ký của phương thức**.
- Gọi `new Account().print("hello")` là hợp lệ. Không truyền thêm `Account` vào danh sách đối số.

Theo Java Language Specification (JLS §8.4), receiver parameter là một cú pháp tùy chọn để thể hiện kiểu receiver nhằm có thể chú thích kiểu đó. Việc có hay không có receiver parameter **không làm thay đổi hành vi runtime** của phương thức.

Đây là khác biệt quan trọng với các cú pháp có vẻ tương tự trong ngôn ngữ khác, nơi receiver có thể được khai báo thành tham số thực sự. Trong Java, receiver parameter của instance method chỉ là vị trí có thể chứa **type-use annotation**.

## 2. Cú pháp annotation cho kiểu this

Để chú thích kiểu receiver, định nghĩa annotation với đích `ElementType.TYPE_USE`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface ReceiverInfo {
    String value();
}
```

Sau đó dùng trên receiver parameter:

```java
class Mailbox {
    void send(@ReceiverInfo("sender") Mailbox this, String text) {
        System.out.println(text);
    }
}
```

Trong `@ReceiverInfo("sender") Mailbox this`, annotation áp dụng lên **lần sử dụng kiểu `Mailbox` của receiver**, không áp dụng lên khai báo method `send` và cũng không áp dụng lên tham số `text`.

Đối với instance method, cú pháp có dạng:

```text
ReturnType methodName(
    @TypeUseAnnotation ClassOrInterfaceName this,
    OtherType firstArgument,
    ...
)
```

Các phần `@TypeUseAnnotation` và các formal parameter khác là tùy chọn; khi có receiver parameter và các formal parameter, receiver phải đứng **đầu danh sách**. Kiểu receiver phải là kiểu class/interface chứa chính phương thức đó; tên receiver phải là từ khóa `this`.

Ví dụ có thể viết `void send(Mailbox this, String text)` dù không có annotation, nhưng cách viết này thường không đem lại lợi ích; mục đích thực tế phổ biến nhất là gắn type-use metadata lên receiver.

### Vì sao cần @Target(TYPE_USE) thay vì PARAMETER?

Java phân biệt rõ:

| Target | Chú thích cho | Ví dụ |
| --- | --- | --- |
| `ElementType.TYPE_USE` | Một vị trí **sử dụng kiểu**, bao gồm kiểu của receiver | `void send(@ReceiverInfo Mailbox this)` |
| `ElementType.PARAMETER` | **Khai báo formal parameter** của method/constructor | `void send(@Input String message)` |
| `ElementType.METHOD` | **Khai báo phương thức** | `@Audited void send(...)` |

Receiver parameter **không phải formal parameter** và không khai báo biến. Vì vậy, annotation chỉ có `@Target(ElementType.PARAMETER)` không đủ để gắn lên kiểu receiver. Nếu muốn sử dụng cùng loại annotation ở cả kiểu receiver và khai báo tham số bình thường, có thể cân nhắc `@Target({ElementType.TYPE_USE, ElementType.PARAMETER})`; tuy nhiên điều này mở hai ngữ cảnh áp dụng khác nhau và cần diễn giải metadata cho đúng.

Ví dụ minh họa lỗi (không biên dịch độc lập):

```java
@Target(ElementType.PARAMETER)
@interface ParamOnly {}

// LỖI nếu đặt @ParamOnly lên kiểu receiver:
class WrongExample {
    void run(@ParamOnly WrongExample this) {}
}
```

Compiler từ chối vì tại vị trí receiver annotation phải hợp lệ trong **type context**.

## 3. Receiver khác this thông thường ở đâu?

Hãy so sánh:

```java
class Counter {
    private int value;

    void increase(Counter this, int amount) {
        this.value += amount;
    }
}
```

- `Counter this` trong danh sách parameter là **receiver parameter syntax**; nó không tạo ra một biến `this` mới.
- `this.value` trong method body là **biểu thức tham chiếu tới đối tượng hiện tại**, vẫn hoạt động như trong phương thức không khai báo receiver.
- `amount` là formal parameter thực sự.
- `increase(3)` nhận đúng **một đối số**; receiver parameter không làm nó thành phương thức hai đối số.
- Không thể gán giá trị cho `this`, bởi `this` không phải biến tham số được định nghĩa bằng cú pháp này.

**Ý nghĩa type-use:** annotation trên `Counter this` diễn đạt một thuộc tính của **kiểu đối tượng nhận lời gọi** ở phương thức `increase`. Nó không tự áp dụng cho mọi `Counter` trong chương trình, cũng không tự kiểm tra tính chất như immutable, thread-safe hoặc non-null.

### Receiver parameter không phải tham số ẩn cần truyền bằng tay

Trong Java, khi gọi một instance method, biểu thức đứng trước dấu chấm đã chỉ ra đối tượng nhận lời gọi:

```java
Counter counter = new Counter();
counter.increase(3);
```

Đối tượng `counter` là receiver của lời gọi. Đưa `Counter this` vào khai báo chỉ tạo chỗ biểu diễn kiểu receiver trong source, **không thêm parameter nào vào bytecode signature để caller cung cấp**. Khi quan sát phương thức bằng reflection, `getParameterCount()` vẫn chỉ đếm formal parameter `amount`.

## 4. Phương thức nào được phép có receiver parameter?

JLS giới hạn vị trí của receiver parameter:

1. **Instance method** khai báo trong class/interface: có thể sử dụng receiver parameter với kiểu khai báo phù hợp.
2. **Constructor của inner class** không được khai báo trong static context: có thể dùng **qualified receiver parameter** đại diện cho enclosing instance.
3. **Static method**: không được khai báo receiver parameter, bởi static method không có đối tượng nhận lời gọi theo nghĩa instance method.
4. **Constructor của top-level class, static nested class, local class hoặc anonymous class**: không thể dùng receiver parameter theo cú pháp dành cho inner member class constructor.
5. **Constructor thông thường của chính class bên ngoài**: không có receiver parameter `ClassName this`. Constructor đang tạo đối tượng, nên không có receiver theo vai trò đó.

Ví dụ sai (chỉ minh họa lỗi):

```java
class InvalidReceiver {
    static void utility(InvalidReceiver this) {} // LỖI: static method.

    InvalidReceiver(InvalidReceiver this) {}      // LỖI: constructor top-level.
}
```

Ở instance method, kiểu receiver phải đúng với class/interface khai báo phương thức và tên phải là `this`:

```java
class Printer {
    void print(Printer this) {} // Hợp lệ.
    // void wrong(String this) {} // LỖI: kiểu receiver không phù hợp.
}
```

Các đoạn tại mục này là **mã minh họa quy tắc**, không phải một file dùng để chạy trực tiếp toàn bộ vì có ví dụ lỗi được cố ý đưa vào.

## 5. Ví dụ Java 17+ hoàn chỉnh: annotation receiver và reflection

Chương trình sau chỉ dùng JDK, tự định nghĩa annotation cho **TYPE_USE** có `RUNTIME` retention và đọc nó qua `Method.getAnnotatedReceiverType()`.

Tạo file **ReceiverAnnotationDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ReceiverTag {
    String value();
}

public class ReceiverAnnotationDemo {
    private final String prefix;

    public ReceiverAnnotationDemo(String prefix) {
        this.prefix = prefix;
    }

    public String greet(
            @ReceiverTag("greeting receiver")
            ReceiverAnnotationDemo this,
            String name) {
        return prefix + name;
    }

    public String ordinary(String name) {
        return prefix + name;
    }

    public static void utility() {}

    public static void main(String[] args)
            throws NoSuchMethodException {
        Method greetMethod = ReceiverAnnotationDemo.class
                .getDeclaredMethod("greet", String.class);
        AnnotatedType receiver = greetMethod.getAnnotatedReceiverType();
        ReceiverTag tag = receiver.getAnnotation(ReceiverTag.class);

        System.out.println("receiver type=" + receiver.getType().getTypeName());
        System.out.println("receiver tag=" + tag.value());
        System.out.println("formal parameters=" + greetMethod.getParameterCount());
        System.out.println("method tag="
                + greetMethod.isAnnotationPresent(ReceiverTag.class));

        Method ordinaryMethod = ReceiverAnnotationDemo.class
                .getDeclaredMethod("ordinary", String.class);
        System.out.println("ordinary receiver annotations="
                + ordinaryMethod.getAnnotatedReceiverType()
                        .getAnnotations().length);

        Method staticMethod = ReceiverAnnotationDemo.class
                .getDeclaredMethod("utility");
        System.out.println("static receiver="
                + staticMethod.getAnnotatedReceiverType());

        ReceiverAnnotationDemo demo = new ReceiverAnnotationDemo("Hello, ");
        System.out.println(demo.greet("Lan"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên, trong thư mục chứa file:

```bash
javac ReceiverAnnotationDemo.java
java ReceiverAnnotationDemo
```

Stdout dự kiến chính xác:

```text
receiver type=ReceiverAnnotationDemo
receiver tag=greeting receiver
formal parameters=1
method tag=false
ordinary receiver annotations=0
static receiver=null
Hello, Lan
```

**Giải thích từng dòng:**

1. `receiver.getType().getTypeName()` trả kiểu receiver của `greet`, ở đây là `ReceiverAnnotationDemo`.
2. `receiver.getAnnotation(ReceiverTag.class)` tìm annotation trực tiếp trên **kiểu receiver**, rồi `tag.value()` trả chuỗi `greeting receiver`.
3. `getParameterCount()` bằng **1** vì `name` là formal parameter duy nhất; `ReceiverAnnotationDemo this` không được tính.
4. `greetMethod.isAnnotationPresent(ReceiverTag.class)` bằng **false** vì `ReceiverTag` nhắm vào **type use của receiver**, không phải annotation trên khai báo method.
5. Một instance method không viết receiver parameter, như `ordinary`, vẫn có kiểu receiver mà reflection có thể biểu diễn thành `AnnotatedType` **không chứa annotation**. Vì thế chiều dài mảng annotation bằng 0.
6. Static method `utility` **không có receiver**. `getAnnotatedReceiverType()` trả về `null` đối với static method.
7. `demo.greet("Lan")` trả `Hello, Lan` như một instance method bình thường; annotation không tự thêm logic.

Đây là ví dụ về **khả năng lưu và đọc type-use metadata**, không phải ví dụ về việc thay đổi luồng thực thi bằng annotation.

## 6. getAnnotatedReceiverType() khác getParameters() và getAnnotatedParameterTypes()

Với `java.lang.reflect.Executable`, các API phục vụ những câu hỏi riêng:

| API | Thông tin được truy vấn |
| --- | --- |
| `getAnnotatedReceiverType()` | **Kiểu receiver** của instance method hoặc enclosing instance phù hợp, kèm type-use annotation |
| `getParameters()` | Danh sách **formal parameter** của method/constructor |
| `getParameterCount()` | Số formal parameter theo reflection |
| `getAnnotatedParameterTypes()` | Kiểu của các **formal parameter**, kèm type-use annotation |
| `getAnnotation(ReceiverTag.class)` trên `Method` | Annotation **trên khai báo method**, không phải tự tìm annotation receiver |

Điểm quyết định là receiver parameter **không phải formal parameter**. Do đó, không tìm annotation của kiểu `this` trong `method.getParameters()[0]`; phần tử đầu tiên ở đó là formal parameter `name`.

Trong chương trình có annotation kiểu phù hợp với `RUNTIME`, cách đọc đúng thường là:

```java
Method method = SomeClass.class.getDeclaredMethod("someMethod");
AnnotatedType receiver = method.getAnnotatedReceiverType();

if (receiver != null) {
    ReceiverTag annotation = receiver.getAnnotation(ReceiverTag.class);
    if (annotation != null) {
        System.out.println(annotation.value());
    }
}
```

Đoạn này **chỉ là mẫu gọi API**, cần có kiểu `SomeClass`, phương thức `someMethod`, và định nghĩa/import `ReceiverTag` trong chương trình cụ thể. Không nên gọi `receiver.getAnnotation(...)` mà không xét `null` khi xử lý static method hoặc constructor không thể có receiver.

### Trường hợp phương thức không khai báo receiver tường minh

Theo API Java Reflection, với **instance method**, `getAnnotatedReceiverType()` có thể trả về một `AnnotatedType` **không có annotation**, dù source không ghi `ClassName this`. Vì vậy:

- **Receiver object có trong ngữ nghĩa instance method**.
- **Việc có viết receiver parameter trong source là lựa chọn cú pháp**.
- **Việc receiver type có annotation là câu hỏi khác**.

Không thể dùng điều kiện `getAnnotatedReceiverType() != null` để suy rằng lập trình viên nhất thiết đã ghi receiver parameter tường minh trong source.

## 7. Constructor của inner class: qualified receiver parameter

Một **non-static inner member class** có thể chứa constructor nhận thông tin về kiểu **enclosing instance** qua qualified receiver parameter. Cú pháp khác với instance method:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface OwnerTag {
    String value();
}

class Outer {
    class Inner {
        Inner(@OwnerTag("enclosing") Outer Outer.this, int number) {
            System.out.println(number);
        }
    }
}
```

Ở đây:

- `Inner` là inner class không `static`, được khai báo bên trong `Outer`.
- `Outer Outer.this` là **qualified receiver parameter** của constructor `Inner`; nó mô tả **kiểu của đối tượng `Outer` bao ngoài** đối tượng `Inner` mới.
- Tên receiver phải có dạng **`Outer.this`**, trong đó `Outer` là tên đơn giản của kiểu bao ngay bên ngoài; kiểu khai báo receiver phải phù hợp với enclosing type.
- `int number` là formal parameter thật sự trong source. Khi khởi tạo, người dùng viết chẳng hạn `outer.new Inner(5)` và **không cung cấp thêm đối số có tên `Outer.this`**.

Đây là đoạn **minh họa cấu trúc**. Nếu muốn đọc `@OwnerTag` bằng reflection, annotation cần `@Retention(RUNTIME)`; đoạn hiện tại chưa khai báo retention nên mặc định `CLASS`.

**Chi tiết cần phân biệt:** JVM có thể dùng một tham số tổng hợp/ẩn khi thực thi constructor của inner class để chuyển enclosing instance. Điều này thuộc cách biên dịch inner class và có thể xuất hiện trong reflection constructor. Nó **không phải** receiver parameter do lập trình viên viết `Outer Outer.this` trong source. Đừng kết luận số lượng tham số thực thi của inner class constructor chỉ từ cú pháp receiver parameter mà bỏ qua các tham số do compiler tạo.

### Vì sao không viết receiver trong constructor của top-level class?

Một constructor của top-level class đang xây dựng đối tượng hiện tại; receiver parameter trong Java không có vai trò mô tả kiểu của đối tượng đang tạo theo cách đó. JLS chỉ cho phép receiver trong constructor của inner class thích hợp để chú thích kiểu enclosing instance, và compiler từ chối những trường hợp constructor khác.

## 8. Retention, class file và type annotation

`@Target(TYPE_USE)` cho phép annotation xuất hiện ở các **ngữ cảnh sử dụng kiểu**, trong đó có receiver type. **`@Retention`** quyết định metadata được giữ trong vòng đời biên dịch/chạy:

| Retention | Ý nghĩa với type annotation trên receiver |
| --- | --- |
| `SOURCE` | Phục vụ xử lý source/compile, không duy trì vào class file theo chính sách retention |
| `CLASS` | Metadata được giữ trong class file ở vị trí hỗ trợ, nhưng reflection runtime không cung cấp theo cách RUNTIME |
| `RUNTIME` | Có thể truy xuất annotation của kiểu receiver qua `getAnnotatedReceiverType()` và `AnnotatedType.getAnnotation()` |

Nếu không khai báo `@Retention`, mặc định là **`RetentionPolicy.CLASS`**, nên muốn dùng reflection như ví dụ mục 5 phải khai báo `RUNTIME` rõ ràng.

Công cụ `javap -v ReceiverAnnotationDemo` (sau khi biên dịch) có thể giúp quan sát metadata type annotation ở cấp class file. Các dạng type annotation runtime thường được biểu diễn qua thuộc tính như `RuntimeVisibleTypeAnnotations` và vị trí nhận biết receiver của method. Đừng nhầm chúng với annotation khai báo method được truy xuất trực tiếp bởi `Method.getAnnotation(...)`.

## 9. TYPE_USE metadata không tự áp đặt ràng buộc

Giả sử một thư viện định nghĩa:

```java
@Target(ElementType.TYPE_USE)
@interface ReadOnly {}

class Document {
    void inspect(@ReadOnly Document this) {
        // ...
    }
}
```

Việc `@ReadOnly` gắn lên kiểu receiver **không tự khiến Document bất biến**. Nó chỉ là thông tin tĩnh; hiệu lực tùy compiler plugin, static analyzer, framework hoặc quy tắc tự viết có đọc và hiểu annotation đó hay không.

Một hệ thống kiểm tra tính null, quyền truy cập hoặc trạng thái của receiver có thể thiết kế annotation trên kiểu `this` như một phần hợp đồng, nhưng **Java Core không mặc định thực thi** những yêu cầu do annotation tùy ý diễn đạt. Cũng không vì có annotation trên receiver mà phương thức bị chuyển thành static hay nhận thêm đối số.

Nếu bài toán đơn giản chỉ là mô tả phương thức được gọi hay ghi audit metadata ở cấp phương thức, `@Target(METHOD)` có thể phù hợp hơn. Khi muốn mô tả **kiểu của đối tượng nhận lời gọi**, type-use annotation trên receiver cho mô hình chính xác hơn.

## 10. Sai lầm thường gặp

**1. Xem receiver parameter là formal parameter.** `ClassName this` không phải biến nhận đối số và không làm tăng số tham số khi gọi method. `getParameters()` không trả về receiver parameter trong danh sách formal parameters.

**2. Dùng @Target(PARAMETER) cho receiver.** Chú thích receiver thuộc **type-use context**. Nếu annotation chỉ áp dụng cho PARAMETER, compiler sẽ từ chối tại vị trí receiver.

**3. Viết receiver sau một tham số bình thường.** Nếu khai báo receiver cùng formal parameter, receiver phải đứng đầu danh sách.

**4. Viết receiver trong static method.** Static method không có instance receiver, nên khai báo kiểu `ClassName this` ở đó là lỗi biên dịch.

**5. Viết receiver trong constructor top-level.** Chỉ constructor của non-static inner class đủ điều kiện mới dùng receiver kiểu enclosing instance. Constructor top-level không cho phép.

**6. Nhầm method receiver và constructor receiver.** Instance method dùng dạng `CurrentType this`. Constructor inner class dùng qualified `EnclosingType EnclosingName.this`.

**7. Truy vấn annotation của receiver bằng Method.getAnnotation.** API đó trả annotation của khai báo method. Cần lấy `AnnotatedType` từ `getAnnotatedReceiverType()` để truy vấn type-use annotation.

**8. Nghĩ AnnotatedType khác null chứng minh source có receiver parameter.** Instance method không khai báo tường minh vẫn có thể có `AnnotatedType` receiver không chứa annotation. Kiểm tra metadata theo ý nghĩa thực tế.

**9. Quên @Retention(RUNTIME) khi dùng reflection.** Annotation TYPE_USE thiếu retention tường minh có mặc định CLASS và không hiển thị qua reflection runtime.

**10. Xem type-use annotation như một cơ chế kiểm tra tự động.** Java chỉ cung cấp cú pháp, ràng buộc ngôn ngữ và khả năng truy vấn metadata; xử lý nghiệp vụ phải do thành phần hỗ trợ thực thi.

**11. Giả định tất cả constructor inner class chỉ có số tham số như source.** Cơ chế enclosing instance có thể sinh parameter tại bytecode/reflection; việc này khác với cú pháp receiver và cần được phân biệt.

## 11. Bài tập tự kiểm tra

1. Trong `ReceiverAnnotationDemo`, đổi giá trị `@ReceiverTag("greeting receiver")` thành `@ReceiverTag("service receiver")`, biên dịch lại và dự đoán dòng `receiver tag=...`.
2. Thêm một formal parameter `int times` vào `greet`; sửa `getDeclaredMethod` và `getParameterCount()`. Giải thích vì sao số tham số tăng từ 1 lên 2 dù receiver parameter vẫn không đổi.
3. Thử chuyển `greet` thành `static` mà giữ `ReceiverAnnotationDemo this`; ghi lại lỗi compiler và giải thích.
4. Thử thay `@Target(ElementType.TYPE_USE)` của `ReceiverTag` thành `@Target(ElementType.PARAMETER)`. Tìm nguyên nhân lỗi ở cú pháp receiver và phân biệt nó với formal parameter `name`.
5. Xóa `@Retention(RetentionPolicy.RUNTIME)` khỏi `ReceiverTag`. Trước khi gọi `tag.value()`, sửa code kiểm tra `tag == null` và giải thích vì sao reflection không đọc được annotation CLASS mặc định.
6. Thêm một instance method khác không khai báo receiver tường minh. So sánh `getAnnotatedReceiverType()`, các annotation của nó và giá trị trả về trên static method.
7. Với đoạn `Outer.Inner`, giải thích sự khác nhau giữa `Outer Outer.this` trong constructor declaration và biểu thức `outer.new Inner(5)` trong code tạo object.

## 12. Tài liệu chuẩn để tra cứu

- [JLS §8.4 – Method Declarations và Receiver Parameter (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4): định nghĩa receiver parameter, vị trí hợp lệ, kiểu và tên bắt buộc.
- [JLS §9.7.4 – Where Annotations May Appear (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): phân biệt declaration annotation và type-use annotation.
- [Executable.getAnnotatedReceiverType() (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getAnnotatedReceiverType()): kết quả reflection của receiver type, cả trường hợp có và không có annotation.

**Kết luận:** Receiver parameter là cú pháp giúp Java gắn **TYPE_USE annotation lên kiểu của `this`** hoặc lên kiểu enclosing instance của constructor inner class. Nó **không khai báo formal parameter mới, không thay đổi lời gọi và không tự tạo hành vi runtime**. Để đọc metadata lúc chạy, dùng annotation có `RUNTIME` retention cùng `getAnnotatedReceiverType()`, đồng thời phân biệt rõ với `getParameters()` và `Method.getAnnotation()`.
