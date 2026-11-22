# Phân biệt gọi virtual với mong muốn gọi riêng triển khai super trong Java Reflection

## 1. Vấn đề: đã lấy Method của lớp cha, sao vẫn chạy code lớp con?

Một người dùng Reflection có thể lấy đối tượng `Method` được khai báo ở lớp cha rồi gọi nó trên đối tượng của lớp con:

~~~java
Method method = Parent.class.getDeclaredMethod("message");
Object result = method.invoke(new Child());
~~~

Nếu `Child` **override** `message()`, kết quả là phần triển khai của `Child`, **không phải** phần triển khai trong `Parent`. Đây là hành vi đúng của `Method.invoke` đối với phương thức instance có cơ chế gọi ảo (virtual dispatch).

Điều cần phân biệt:

- **Method được tìm ở đâu?** `Parent.class.getDeclaredMethod(...)` trả về metadata của phương thức khai báo trong `Parent`.
- **Method được gọi trên đối tượng nào?** Đối tượng truyền vào `invoke(receiver)` có kiểu runtime là `Child`.
- **JVM chọn thân phương thức nào?** Với phương thức instance có thể override, `Method.invoke` sử dụng **dynamic method lookup**; lớp con override sẽ được chọn.
- **Làm sao cố ý gọi triển khai `super`?** Câu lệnh `super.message()` trong mã lớp con, hoặc `MethodHandles.Lookup.findSpecial(...)` / `unreflectSpecial(...)` trong ngữ cảnh caller có đủ quyền, mới biểu đạt ý định tương tự `invokespecial`.

Đây là bài học thuộc nhóm **Method của Java Reflection**, tập trung vào dispatch và cách gọi đúng thân phương thức, thay vì chỉ cách lấy tên hoặc annotation của method.

## 2. Mô hình nền tảng: kiểu biên dịch và kiểu runtime

Ví dụ:

~~~java
class Parent {
    public String message() {
        return "Parent.message";
    }
}

class Child extends Parent {
    @Override
    public String message() {
        return "Child.message";
    }

    public String callSuper() {
        return super.message();
    }
}
~~~

Với:

~~~java
Parent p = new Child();
System.out.println(p.message());       // Child.message
System.out.println(((Parent) p).message()); // Child.message
System.out.println(((Child) p).callSuper()); // Parent.message
~~~

**Vì sao?** Biểu thức có kiểu khai báo `Parent` và phép cast `(Parent)` chỉ chi phối việc kiểm tra/giải quyết lời gọi tại thời điểm biên dịch; đối tượng thực vẫn là `Child`. Với lời gọi virtual, JVM lựa chọn override phù hợp theo lớp thực tế của receiver. Phép cast không chuyển object thành một instance `Parent` mới.

Ngược lại, `super.message()` là một lời gọi đặc biệt xuất hiện trong **mã của lớp con**. Java dùng ngữ nghĩa gọi thành viên lớp cha trong ngữ cảnh đó, bỏ qua override đang có ở lớp con. `super` không phải giá trị đối tượng có thể truyền cho `Method.invoke`; bạn không thể viết `method.invoke(super)` ở chỗ bình thường vì `super` không phải biểu thức biến độc lập như `this`.

### Minh họa đường đi

~~~text
Parent p = new Child()
        |
        +-- p.message()
        |       |
        |       +-- virtual dispatch theo receiver thực: Child.message()
        |
        +-- Parent.class.getMethod("message").invoke(p)
        |       |
        |       +-- Method mô tả Parent.message
        |       +-- Method.invoke vẫn dispatch: Child.message()
        |
        +-- ((Child) p).callSuper()
                |
                +-- mã trong Child gọi super.message(): Parent.message()
~~~

Một điểm quan trọng về từ “virtual”: trong Java, các phương thức instance có khả năng override thường dùng dynamic dispatch. Không áp dụng quy tắc đó một cách máy móc cho mọi method như `static`, `private`, constructor hay các phương thức không thể override.

## 3. Những API tìm Method KHÔNG quyết định thân hàm được chạy

| Cách lấy Method | Method metadata có thể đại diện cho | Khi `invoke(child)` với override hợp lệ |
| --- | --- | --- |
| `Parent.class.getMethod("message")` | Method public của `Parent` | Chạy `Child.message` |
| `Parent.class.getDeclaredMethod("message")` | Method khai báo trực tiếp trong `Parent` | Chạy `Child.message` |
| `Child.class.getMethod("message")` | Method public mà tra cứu từ `Child` thấy | Chạy `Child.message` |
| `Child.class.getDeclaredMethod("message")` | Method khai báo trực tiếp trong `Child` nếu có | Chạy `Child.message` |
| `Parent.class.getSuperclass()` | Trả về lớp cha của `Parent`, không phải một lệnh gọi method | Không tác động đến dispatch |

Các điểm kỹ thuật:

1. `getMethod` tìm phương thức `public` theo quy tắc của `Class`, trong đó có thể bao gồm phương thức kế thừa.
2. `getDeclaredMethod` tìm khai báo ở **chính lớp/interface được hỏi**, bất kể `public`, `protected`, package-private hay `private`; không tự đi tìm khai báo trong superclass.
3. `Method.getDeclaringClass()` cho biết **lớp khai báo Method**, không cho biết override nào sẽ được chọn khi chạy.
4. Truyền đúng danh sách `Class<?>` của tham số vào `getMethod/getDeclaredMethod` khi method có tham số hoặc overload.
5. Dùng `setAccessible(true)` hoặc `trySetAccessible()` (khi được cho phép) để thay đổi **kiểm tra quyền truy cập**, không thay đổi virtual dispatch. Mở quyền cho một Method khai báo ở Parent không có nghĩa JVM phải chọn thân Parent.

Tài liệu Java SE 17 về `Method.invoke` xác nhận rằng, với phương thức instance, JVM dùng dynamic method lookup; việc override dựa trên kiểu runtime của đối tượng đích vẫn diễn ra.

### Hai mục tiêu khác nhau

- **Mục tiêu A — gọi hành vi đa hình trên receiver hiện tại:** dùng `Method.invoke(receiver, args...)` hoặc method handle có ngữ nghĩa virtual.
- **Mục tiêu B — gọi riêng phần triển khai của superclass:** cần một vị trí gọi có quyền thực hiện `super`/`invokespecial`; cách đó không thể tạo ra bằng cách đổi mỗi đối tượng `Method` hoặc ép kiểu receiver.

## 4. Ví dụ Java 17+ độc lập: nhìn thấy mọi kết quả trong một lần chạy

Đặt toàn bộ mã sau vào tệp **`VirtualDispatchDemo.java`**. Chương trình dùng nested class để dễ biên dịch, đồng thời thực hiện `findSpecial` từ **bên trong `Child`**, nơi lookup được tạo với quyền truy cập phù hợp.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class VirtualDispatchDemo {
    public static class Parent {
        public String message() { return "Parent.message"; }
        public static String category() { return "Parent.category"; }
        public final String fixed() { return "Parent.fixed"; }
    }

    public static class Child extends Parent {
        @Override
        public String message() { return "Child.message"; }

        public static String category() { return "Child.category"; }

        public String directSuper() { return super.message(); }

        public String specialSuper() throws Throwable {
            MethodHandle handle = MethodHandles.lookup().findSpecial(
                    Parent.class, "message",
                    MethodType.methodType(String.class),
                    Child.class);
            return (String) handle.invoke(this);
        }
    }

    public static void main(String[] args) throws Throwable {
        Child child = new Child();
        Parent parentRef = child;
        Method fromParent = Parent.class.getMethod("message");
        Method fromChild = Child.class.getDeclaredMethod("message");
        Method staticParent = Parent.class.getMethod("category");
        Method finalParent = Parent.class.getMethod("fixed");

        System.out.println("normal: " + parentRef.message());
        System.out.println("declared by: "
                + fromParent.getDeclaringClass().getSimpleName());
        System.out.println("parent Method.invoke: "
                + fromParent.invoke(child));
        System.out.println("child Method.invoke: "
                + fromChild.invoke(child));
        System.out.println("super in Child: " + child.directSuper());
        System.out.println("findSpecial from Child: "
                + child.specialSuper());

        MethodHandle virtual = MethodHandles.lookup().findVirtual(
                Parent.class, "message",
                MethodType.methodType(String.class));
        System.out.println("findVirtual: " + (String) virtual.invoke(child));
        System.out.println("static Parent method: "
                + staticParent.invoke(null));
        System.out.println("final Parent method: "
                + finalParent.invoke(child));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac --release 17 VirtualDispatchDemo.java
java VirtualDispatchDemo
~~~

**Stdout chính xác của ví dụ đã được biên dịch và chạy bằng OpenJDK 21 với `--release 17`:**

~~~text
normal: Child.message
declared by: Parent
parent Method.invoke: Child.message
child Method.invoke: Child.message
super in Child: Parent.message
findSpecial from Child: Parent.message
findVirtual: Child.message
static Parent method: Parent.category
final Parent method: Parent.fixed
~~~

### Phân tích từng kết quả

- `normal`: biến `parentRef` có kiểu khai báo `Parent` nhưng trỏ vào `Child`; lời gọi ảo chọn `Child.message`.
- `declared by`: chính đối tượng `Method` thuộc `Parent`, xác nhận lookup ở lớp cha, nhưng nó **không khóa** dispatch vào Parent.
- `parent Method.invoke` và `child Method.invoke`: cả hai chạy `Child.message`; điều này tách bạch metadata của Method với lựa chọn triển khai tại runtime.
- `super in Child`: phương thức `directSuper` trong Child dùng đúng từ khóa `super` nên thực thi `Parent.message`.
- `findSpecial from Child`: tạo method handle có ngữ nghĩa gọi đặc biệt từ lookup đủ quyền của Child, bỏ qua override và chạy `Parent.message`.
- `findVirtual`: method handle tạo bằng `findVirtual` vẫn dùng virtual dispatch khi nhận Child, nên chạy `Child.message`.
- `static Parent method`: `static` dùng method hiding chứ không override; Reflection gọi đúng phương thức static mô tả ở Parent; receiver có thể là `null`.
- `final Parent method`: `final` không thể được Child override; gọi trên Child vẫn dùng thân `Parent.fixed`.

Ví dụ chạy bằng classpath, không cần tùy chọn JVM đặc biệt. Nếu sửa ví dụ để chia thành các **named module** có quyền truy cập hạn chế, hành vi tạo method handle còn phụ thuộc JPMS và quyền của lookup.

## 5. Giới hạn của `Method.invoke` trong bài toán gọi super

Trong ví dụ ở mục 4, `fromParent.getDeclaringClass()` vẫn là `Parent.class`, nhưng `fromParent.invoke(child)` gọi `Child.message()`. Đây là **virtual dispatch**, giống lời gọi instance bình thường. Thay `getMethod` bằng `getDeclaredMethod`, ép `child` về `Parent`, hoặc bật `setAccessible(true)` đều **không** đổi cơ chế chọn override.

`Method.invoke` nhận receiver và đối số; API này **không có tùy chọn “gọi riêng thân super”**. Nếu chỉ cần hành vi đa hình thì tiếp tục dùng `invoke`; khi thực sự muốn gọi triển khai lớp cha, cần cơ chế special invocation có quyền phù hợp, được trình bày dưới đây.

## 6. Khi nào gọi được triển khai super bằng MethodHandles?

Java cung cấp `java.lang.invoke.MethodHandle` và `MethodHandles.Lookup`. Một method handle có thể biểu diễn cách gọi tương tự một số lệnh bytecode JVM, trong đó có:

| API | Loại gọi được nhấn mạnh | Khi receiver là Child override Parent |
| --- | --- | --- |
| `Method.invoke` trên method instance của Parent | Dynamic lookup theo receiver | Child override |
| `Lookup.findVirtual(Parent.class, "message", type)` | Gọi ảo tương tự `invokevirtual` | Child override |
| `Lookup.findSpecial(Parent.class, "message", type, Child.class)` từ lookup đủ quyền của Child | Gọi đặc biệt tương tự `invokespecial` | Triển khai Parent, theo quy tắc `invokespecial` |
| `Lookup.unreflectSpecial(parentMethod, Child.class)` từ lookup đủ quyền của Child | Tạo handle gọi đặc biệt từ Method metadata | Có thể gọi triển khai Parent |
| `super.message()` trong mã Child | Cú pháp ngôn ngữ cho lời gọi superclass | Triển khai Parent |

### 6.1. `findSpecial` và các tham số

Trong ví dụ:

~~~java
MethodHandle handle = MethodHandles.lookup().findSpecial(
        Parent.class,
        "message",
        MethodType.methodType(String.class),
        Child.class);
String result = (String) handle.invoke(this);
~~~

- `Parent.class`: lớp mà method đặc biệt được tra cứu.
- `"message"`: tên method cần gọi.
- `MethodType.methodType(String.class)`: kiểu trả về và các kiểu tham số của method; không chứa receiver.
- `Child.class`: **special caller**, tức lớp được phép thực hiện kiểu gọi `invokespecial` trong ngữ cảnh này.
- `MethodHandles.lookup()`: sinh ra bên trong phương thức của `Child`, nên lookup class đúng là `Child` và có quyền truy cập để kiểm tra lời gọi này.
- `this`: receiver mà handle cần để thực thi. Với method instance, kiểu handle bao gồm một tham số receiver phía trước các tham số method.

`findSpecial` không chỉ là một cách viết khác của `findVirtual`. Nó mang **ngữ nghĩa gọi không thông qua override thông thường** và chỉ được tạo khi lookup có quyền tương ứng. Theo API, nếu `specialCaller` không phù hợp với lookup class hoặc lookup thiếu quyền private cần thiết, thao tác có thể thất bại bằng `IllegalAccessException`.

Một ví dụ không hợp lệ về kỳ vọng: đưa đoạn `MethodHandles.lookup().findSpecial(Parent.class, ..., Child.class)` ra mã bất kỳ ngoài Child rồi cho rằng mọi caller đều được quyền gọi phần `super` của Child. Ngữ nghĩa `super` gắn với **vị trí/lớp gọi được cấp quyền**, không phải với một chuỗi tên lớp tự khai báo.

### 6.2. `unreflectSpecial` khi đã có Method

Nếu đã lấy Method bằng Reflection, từ mã trong `Child` có thể dùng:

~~~java
Method parent = Parent.class.getDeclaredMethod("message");
MethodHandle special = MethodHandles.lookup()
        .unreflectSpecial(parent, Child.class);
String result = (String) special.invoke(this);
~~~

Đây là đoạn mã **để đặt trong một phương thức instance của `Child`**, với `Parent`/`Child` theo phần 4; cần khai báo/lan truyền các checked exception và `Throwable` thích hợp. `unreflectSpecial` tái sử dụng Method metadata để tạo một method handle có ngữ nghĩa gọi đặc biệt. Nó **không** biến bản thân `parent.invoke(child)` thành lời gọi super.

Việc có thể đọc một `Method` bằng Reflection không tự cấp phép cho `unreflectSpecial`. API vẫn kiểm tra quyền của lookup và giới hạn truy cập. `privateLookupIn` cũng không phải một cơ chế “đột nhập” tùy ý: việc chuyển sang lookup có quyền private chịu ràng buộc bởi quyền caller và sự mở package của module liên quan.

### 6.3. Lý do nên ưu tiên `super` trực tiếp khi kiểm soát mã lớp con

Khi chính bạn viết Child, cách đơn giản, rõ nghĩa và ổn định nhất là:

~~~java
@Override
public String message() {
    return "Child wrapper -> " + super.message();
}
~~~

Cách này thực hiện trực tiếp lời gọi superclass trong ngữ cảnh mà Java cho phép, không phải tạo Reflection hay method handle. Nếu một thư viện muốn cho client bên ngoài gọi phần logic của cha, có thể cung cấp một **phương thức tường minh** của Child (ví dụ `callParentMessage()`) thay vì buộc client dùng quyền truy cập đặc biệt.

`findSpecial` có ích khi viết framework, bộ máy gọi động hoặc tích hợp cần kiểm soát cách dispatch, nhưng nó phức tạp hơn `super` và có giới hạn quyền rõ ràng.

## 7. Những trường hợp không theo mô hình override thông thường

| Loại method | Có bị override theo cách của method instance thông thường? | Hành vi cần nhớ |
| --- | --- | --- |
| Instance method có thể override | Có | `Method.invoke` chọn override phù hợp với receiver runtime |
| `static` | Không; cùng tên/chữ ký là **hiding** | Reflection gọi đúng static Method đã tìm, receiver bị bỏ qua |
| `private` | Không bị override | Method private của cha là thành viên riêng; khai báo cùng chữ ký trong con không phải override nó |
| `final` instance | Không thể override | Receiver là subclass vẫn chỉ có phần triển khai final kế thừa |
| Constructor | Không là Method, không được kế thừa/override | Dùng `Constructor.newInstance`; không áp dụng virtual dispatch như `Method.invoke` |
| Method `abstract` ở cha hoặc interface | Có thể được triển khai ở con | `Method.invoke` với receiver cụ thể sẽ đi đến triển khai hợp lệ, nếu có |
| Interface default method | Có thể được override | `Method.invoke` trên receiver có override thường đi đến override; muốn gọi riêng default cần ngữ nghĩa gọi đặc biệt hợp lệ |

Đặc biệt với private method, đừng thấy hai phương thức cùng tên rồi kết luận “Child override private method của Parent”. Java không cho override một private member như vậy. Nếu Reflection gọi đúng private method của Parent trên một Child instance và có quyền truy cập, thân của Parent được gọi vì nó không có dynamic override tương ứng — **đó không phải là kỹ thuật gọi `super` của một method public/protected có thể override**.

Tương tự, khi method là `static`, gọi `Parent.class.getMethod("category").invoke(null)` chạy `Parent.category`; `Child` có thể khai báo `category` cùng tên nhưng chỉ ẩn method static của Parent. Không lấy kết quả đó làm bằng chứng rằng phương thức instance thông thường có thể gọi đúng super qua `Method.invoke`.

### Phương thức mặc định (default) của interface

Ví dụ khái niệm:

~~~java
interface Greeting {
    default String hello() { return "Greeting.hello"; }
}

class Friendly implements Greeting {
    @Override
    public String hello() { return "Friendly.hello"; }

    String interfaceDefault() {
        return Greeting.super.hello();
    }
}
~~~

Nếu lấy `Greeting.class.getMethod("hello")` rồi gọi `invoke(new Friendly())`, kết quả phản ánh override `Friendly.hello`. Muốn gọi trực tiếp default từ `Friendly`, cú pháp `Greeting.super.hello()` biểu đạt rõ ý định. Với method handle, trường hợp default cũng liên quan đến lookup đặc biệt nhưng phải tuân thủ quy tắc special caller/interface phù hợp; đừng dùng một `findSpecial` tùy ý từ mã ngoài class rồi cho rằng chắc chắn hợp lệ. Đây là đoạn mã minh họa, không phải chương trình Java độc lập có `main`.

## 8. Quyền truy cập và module là vấn đề riêng với dispatch

Ba câu hỏi sau phải được xét riêng:

1. **Có tìm được metadata không?** `getMethod` chỉ tra cứu public Method phù hợp; `getDeclaredMethod` tìm khai báo trực tiếp, kể cả private.
2. **Có quyền gọi hoặc tạo special handle không?** Kiểm tra Java access control, quyền lookup và ranh giới JPMS khi dùng named module.
3. **Thân phương thức nào được chọn khi đã gọi hợp lệ?** Với `Method.invoke` cho method instance có override, vẫn là virtual dispatch; với handle hợp lệ được tạo qua `findSpecial` thì theo quy tắc lời gọi đặc biệt.

Vì thế, `method.setAccessible(true)` (nếu runtime cho phép) **chỉ xử lý kiểm tra truy cập**. Nó không đổi đối tượng receiver, không xóa override và không buộc Parent chạy. Đối với các named module, một package không được `opens` phù hợp có thể khiến nỗ lực bỏ kiểm tra quyền bị `InaccessibleObjectException` hoặc `trySetAccessible() == false`.

Phân biệt lỗi:

| Dấu hiệu | Vấn đề có khả năng nhất |
| --- | --- |
| `NoSuchMethodException` | Tên/chữ ký sai, chọn `getMethod` thay cho `getDeclaredMethod`, hoặc lớp tra cứu không khai báo method |
| `IllegalArgumentException` từ `Method.invoke` | Receiver không tương thích với lớp khai báo Method hoặc danh sách/kiểu đối số không hợp lệ |
| `NullPointerException` với instance `Method.invoke(null)` | Không có receiver instance |
| `IllegalAccessException` từ `Method.invoke` | Caller không có quyền truy cập method |
| `InvocationTargetException` | Bản thân thân phương thức đích ném ngoại lệ; đọc `getCause()` |
| `IllegalAccessException` khi `findSpecial` / `unreflectSpecial` | Lookup hoặc special caller không đủ quyền cho ngữ nghĩa gọi đặc biệt |
| `WrongMethodTypeException` khi gọi `MethodHandle.invokeExact` | Kiểu tại call site không khớp chính xác với method handle |
| Chạy thành công nhưng ra `Child.message` thay vì `Parent.message` | **Không phải lỗi Reflection**; đây chính là virtual dispatch |

`MethodHandle.invoke`/`invokeExact` có quy tắc kiểm tra/adapt kiểu khác với `Method.invoke`. Đặc biệt, `invokeExact` yêu cầu kiểu call site chính xác; `invoke` có một số cơ chế thích nghi kiểu theo API. Tránh nhầm lỗi kiểu của method handle với lỗi phân giải quyền hoặc dispatch.

## 9. Những cách thử sai phổ biến

### Sai 1 — Ép receiver về Parent

~~~java
Child child = new Child();
Method m = Parent.class.getMethod("message");
System.out.println(m.invoke((Parent) child)); // vẫn Child.message
~~~

Cast chỉ cho cùng object một góc nhìn khác ở compile time, không tạo thêm object Parent và không vô hiệu hóa override.

### Sai 2 — Dùng getDeclaredMethod để “khóa” khai báo ở superclass

~~~java
Method m = Parent.class.getDeclaredMethod("message");
System.out.println(m.invoke(new Child())); // vẫn Child.message
~~~

`Declared` nghĩa là metadata khai báo tại Parent; không có nghĩa “chạy đúng thân khai báo của Parent”.

### Sai 3 — Gọi setAccessible(true) để tránh override

~~~java
Method m = Parent.class.getDeclaredMethod("message");
m.setAccessible(true);
System.out.println(m.invoke(new Child())); // vẫn Child.message
~~~

Đoạn này có thể chạy với các class trong ví dụ classpath, nhưng ở named module quyền truy cập sâu có thể không được cấp. Dù bật thành công, virtual dispatch vẫn giữ nguyên.

### Sai 4 — Tạo Lookup ở vị trí tùy ý nhưng khai specialCaller là Child

~~~java
// Minh họa kỳ vọng sai khi đặt trong một lớp gọi không có quyền tương ứng:
MethodHandles.lookup().findSpecial(
        Parent.class, "message",
        MethodType.methodType(String.class), Child.class);
~~~

Chỉ việc gõ `Child.class` ở tham số không biến lookup của lớp gọi thành lookup có quyền của Child. Ngữ cảnh tạo lookup và các kiểm tra đặc biệt mới là yếu tố quyết định. Đặt lời gọi trong Child như ví dụ phần 4 hoặc thiết kế một phương thức ủy quyền hợp pháp.

### Sai 5 — Gọi phần super trong framework để bỏ qua mọi logic của lớp con

Một framework cố tình bỏ qua override có thể phá vỡ invariant mà Child duy trì (kiểm tra input, đồng bộ, transaction, logging, bảo mật hay cache). Chỉ gọi superclass trực tiếp khi hợp đồng API thật sự cho phép. Trong nhiều tình huống, gọi đa hình là hành vi đúng và an toàn hơn.

## 10. Quy trình lựa chọn trong một tình huống thực tế

Giả sử bạn đang viết bộ chạy lệnh dựa vào annotation:

1. **Muốn chạy hành vi của đối tượng thực:** tìm `Method` hợp lệ và `invoke(receiver)`; giữ đa hình nếu method có thể override.
2. **Muốn đọc annotation hoặc chữ ký trên superclass:** dùng `Parent.class.getDeclaredMethod(...)` và kiểm tra metadata; đừng suy ra từ đó thân Parent sẽ được gọi.
3. **Muốn đóng gói logic của Parent để Child chủ động gọi:** viết lời gọi `super.foo()` trong Child hoặc một phương thức forwarding rõ nghĩa.
4. **Cần cơ chế gọi động có ngữ nghĩa super và có quyền của Child:** cân nhắc `Lookup.findSpecial` hoặc `unreflectSpecial` từ lookup hợp lệ, kiểm thử quyền trong môi trường module thực tế.
5. **Không kiểm soát Child hoặc thiếu quyền lookup:** đừng dựa vào việc đổi `getDeclaredMethod`, cast hay `setAccessible` để lách dispatch. Xem lại thiết kế và cung cấp API được chủ sở hữu lớp cho phép.

Nếu mục tiêu là chẩn đoán một kết quả lạ, hãy ghi lại cả **`method.getDeclaringClass()`** và **`receiver.getClass()`**, tên method, signature và kiểu lời gọi (`invoke`, `findVirtual` hay `findSpecial`). Hai kiểu class này là chứng cứ quan trọng nhưng cần hiểu chúng giữ vai trò khác nhau.

## 11. Bài tập tự kiểm tra (kèm đáp án)

**Bài 1.** `Parent p = new Child();`, `Method m = Parent.class.getMethod("message");`. `m.invoke(p)` chạy gì?

**Đáp án:** `Child.message` vì receiver thật là Child và method có override hợp lệ.

**Bài 2.** Đổi `getMethod` thành `getDeclaredMethod` nhưng giữ receiver Child. Kết quả có khác không?

**Đáp án:** Không; thay cơ chế tìm Method metadata không thay virtual dispatch.

**Bài 3.** Có thể viết `((Parent) child).message()` để thực hiện `Parent.message` không?

**Đáp án:** Không. Ép kiểu tham chiếu không thay lớp runtime của object, nên lời gọi ảo vẫn chọn `Child.message`.

**Bài 4.** `setAccessible(true)` của `Parent.message` đã thành công. Điều đó có buộc Reflection gọi thân Parent không?

**Đáp án:** Không. Quyền truy cập và dispatch là hai cơ chế riêng.

**Bài 5.** Trong `Child` muốn gọi phần triển khai của `Parent` một cách đơn giản nhất thì dùng gì?

**Đáp án:** `super.message()` trong phương thức instance của Child có quyền gọi. Khi phải tạo lời gọi động, `findSpecial` từ lookup đủ quyền mới phù hợp.

**Bài 6.** `Parent.category` và `Child.category` đều là `static`. Gọi `Parent.class.getMethod("category").invoke(null)` chạy phương thức nào?

**Đáp án:** `Parent.category`, vì static method không có override theo kiểu instance; đây là hiding.

**Bài 7.** Method của Parent là `final`. Có thể viết override cùng chữ ký trong Child để Reflection chọn Child không?

**Đáp án:** Không. Java cấm override phương thức final; gọi method hợp lệ trên Child dùng phần triển khai final được kế thừa.

**Bài 8.** Một tool ở module khác tạo `findSpecial(Parent.class, "message", ..., Child.class)` nhưng nhận `IllegalAccessException`. Có nên dùng `setAccessible(true)` trên một Method bất kỳ để sửa?

**Đáp án:** Không. Phải xét ngữ cảnh lookup, quyền của specialCaller và ranh giới module; `setAccessible` trên `Method` không tự cấp quyền để tạo special handle hay thay ngữ nghĩa dispatch.

## 12. Ghi nhớ và nguồn tham khảo

**Quy tắc trọng tâm:** `Method.invoke` với phương thức instance có thể override vẫn dùng **virtual dispatch**; một `Method` khai báo ở Parent không bảo đảm thực thi thân Parent trên Child receiver. Để cố ý gọi triển khai superclass, dùng `super` trong mã có quyền, hoặc method handle **special** được tạo với lookup hợp lệ. `getDeclaredMethod`, ép kiểu receiver và `setAccessible` không phải cách thay đổi dispatch.

Tài liệu chính thức Java SE 17:

- [`java.lang.reflect.Method` — mục `invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): dynamic method lookup theo kiểu runtime và ngoại lệ khi gọi bằng Reflection.
- [`MethodHandles.Lookup` — `findVirtual`, `findSpecial`, `unreflectSpecial`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): các kiểu handle, quyền lookup và caller đặc biệt.
- [JLS `15.12.4.4 — Locate Method to Invoke](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.4): quy tắc xác định method đích khi gọi.
- [JVMS `6.5 — `invokevirtual` và `invokespecial`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): ngữ nghĩa chỉ thị gọi ở JVM.
