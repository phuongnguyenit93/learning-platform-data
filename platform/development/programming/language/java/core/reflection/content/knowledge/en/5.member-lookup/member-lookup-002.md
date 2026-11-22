# Tra cứu thành viên bằng `getField`, `getMethod`, `getConstructor` trong Java Reflection

Trong Java Reflection, đối tượng `Class<?>` cho phép tra cứu **field (trường)**, **method (phương thức)** và **constructor (hàm tạo)** từ thông tin kiểu tại runtime. Ba API `getField`, `getMethod`, `getConstructor` thường được sử dụng khi tên thành viên hoặc chữ ký constructor chỉ được xác định lúc chương trình chạy, chẳng hạn trong serializer, framework dependency injection, bộ kiểm tra API hoặc cơ chế plugin.

Điểm chung quan trọng: cả ba API đều tìm **thành viên `public`**. Tuy nhiên, **field và method có thể được kế thừa**, còn **constructor không được kế thừa**. Nếu cần cả thành viên `private`, `protected`, package-private, hoặc cần biết chính xác thành viên **khai báo ngay trên lớp**, dùng các API `getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor` phù hợp.

## 1. Bức tranh tổng thể

| API của `Class` | Giá trị trả về | Tiêu chí tìm | Có xét thành viên kế thừa? | Phạm vi truy cập khi tra cứu |
|---|---|---|---|---|
| `getField(String name)` | `Field` | Tên trường | Có, từ superclass hoặc interface theo quy tắc tra cứu field | Chỉ `public` |
| `getMethod(String name, Class<?>... parameterTypes)` | `Method` | Tên phương thức và dãy kiểu tham số | Có, gồm method được kế thừa từ superclass/interface | Chỉ `public` |
| `getConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Dãy kiểu tham số của constructor | **Không**; constructor chỉ thuộc lớp khai báo | Chỉ `public` |
| `getDeclaredField(String name)` | `Field` | Tên trường khai báo trực tiếp | Không | Tất cả mức truy cập |
| `getDeclaredMethod(String name, Class<?>... parameterTypes)` | `Method` | Tên và kiểu tham số của method khai báo trực tiếp | Không | Tất cả mức truy cập |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Kiểu tham số constructor khai báo trực tiếp | Không | Tất cả mức truy cập |

Ba API `get...` trả về **một** thành viên. Để liệt kê nhiều thành viên, sử dụng `getFields()`, `getMethods()`, `getConstructors()` hoặc những phiên bản `getDeclared...` số nhiều. Thứ tự các phần tử do các API liệt kê trả về **không được bảo đảm**; không dựa vào vị trí trong mảng để chọn thành viên.

Một lookup thành công chỉ chứng minh rằng Reflection **tìm được metadata**. Nó chưa đồng nghĩa thành viên có thể được đọc, ghi, gọi hoặc khởi tạo từ mọi caller: ở thời điểm sử dụng, Java vẫn áp dụng quy tắc access và giới hạn của module.

## 2. `getField(String name)`: tìm trường `public`

Chữ ký:

```java
Field field = SomeType.class.getField("fieldName");
```

`getField` tìm trường `public` có đúng tên được yêu cầu. Trường đó có thể được **khai báo trực tiếp** trên lớp đích hoặc được **kế thừa** từ superclass/interface. Trả về `java.lang.reflect.Field`, cung cấp metadata như `getName()`, `getType()`, `getModifiers()`, `getDeclaringClass()`.

Ví dụ giả định:

```java
class Base {
    public int count;
}

class Derived extends Base {
    private String secret;
}
```

- `Derived.class.getField("count")` **thành công**: `count` là trường `public` kế thừa từ `Base`.
- `Derived.class.getField("secret")` ném `NoSuchFieldException`: `secret` không phải `public`.
- `Derived.class.getDeclaredField("secret")` **thành công**: trường này được khai báo trực tiếp trên `Derived`, bất kể `private`.
- `Derived.class.getDeclaredField("count")` ném `NoSuchFieldException`: `count` được khai báo ở `Base`, không phải `Derived`.

Đừng nhầm **phát hiện một `Field`** với **đọc giá trị field**:

```java
Field field = Derived.class.getField("count");
Derived object = new Derived();
int value = field.getInt(object);
field.setInt(object, 42);
```

Đây là đoạn minh họa độc lập về thao tác `Field`, sử dụng hai class vừa khai báo ở trên. `field.getInt(object)` đọc giá trị trường kiểu `int` của instance; `setInt` gán lại giá trị. Với trường `static`, receiver cho `Field.get(null)` có thể là `null`. Quy tắc access và giới hạn ghi trường `final` vẫn áp dụng.

**Field hiding:** nếu subclass khai báo một trường mới **trùng tên** với trường ở superclass, hai trường vẫn là hai thành viên riêng; đây không phải cơ chế overriding như method. Khi cần chọn đúng trường gốc, hãy tra cứu trên `Base.class` hoặc dùng `getDeclaredField` trên lớp thực sự khai báo trường. Khi các interface cung cấp nhiều trường `public` trùng tên, đừng dựa vào một lookup không rõ ràng; chọn interface khai báo cụ thể.

## 3. `getMethod(String name, Class<?>... parameterTypes)`: tìm phương thức `public`

Chữ ký:

```java
Method method = SomeType.class.getMethod("methodName", String.class, int.class);
```

Lookup dùng **tên method** và **dãy kiểu tham số theo đúng thứ tự**. Phương thức `public` có thể thuộc lớp hiện tại hoặc được kế thừa từ superclass/interface. `getMethod("save", String.class)` khác `getMethod("save", Object.class)` và khác `getMethod("save")`.

Ví dụ:

```java
class Service {
    public void run() { }
    public void run(String text) { }
    public void run(String text, int count) { }
    private void reset() { }
}
```

```java
Method m0 = Service.class.getMethod("run");
Method m1 = Service.class.getMethod("run", String.class);
Method m2 = Service.class.getMethod("run", String.class, int.class);
Method hidden = Service.class.getDeclaredMethod("reset");
```

Các lệnh trên là **đoạn minh họa**, không phải chương trình có `main`. `m0`, `m1`, `m2` ứng với ba overload. `getMethod("reset")` không tìm thấy vì `reset` là `private`; `getDeclaredMethod("reset")` tìm thấy metadata.

### Kiểu tham số phải khớp chữ ký khai báo

- `int.class` **khác** `Integer.class`; tra cứu không tự boxing/unboxing để tìm một chữ ký khác.
- `String.class` **khác** `Object.class`; tra cứu không chọn overload chỉ vì một đối số runtime có thể gán cho kiểu tham số đó.
- Varargs `String... values` được khai báo dưới dạng mảng trong bytecode; tra cứu bằng `String[].class`.
- Với `List<String>`, chữ ký runtime thông thường dùng kiểu đã **erasure**: `List.class`, không có `List<String>.class`.
- Phân biệt thứ tự tham số: `(String, int)` khác `(int, String)`.
- Không truyền kiểu trả về vào `getMethod`; Java không overload method chỉ bằng return type ở mức mã nguồn thông thường.

Ví dụ minh họa cho hai chữ ký đặc biệt:

```java
// Giả sử Example khai báo:
// public void accept(int value) { }
// public void collect(String... values) { }

Method accept = Example.class.getMethod("accept", int.class);
Method collect = Example.class.getMethod("collect", String[].class);
```

`Integer.class` không thể thay `int.class` ở lookup `accept`. Đối với generic methods, bridge/synthetic methods có thể xuất hiện trong metadata; khi kiểm tra tập methods, có thể dùng `isBridge()` và `isSynthetic()` tùy mục đích.

### Tra cứu khác thực thi

`getMethod` chỉ lấy metadata. Khi cần thực thi:

```java
Method method = Service.class.getMethod("run", String.class);
Service service = new Service();
method.invoke(service, "hello");
```

`Method.invoke` mới gọi logic của method. Đối với method `static`, có thể dùng receiver `null`. Exception được method gọi ném ra thường được bọc trong `InvocationTargetException`; kiểm tra `getCause()` để tìm lỗi gốc. Kiểu tham số của đối số truyền vào `invoke` vẫn phải phù hợp; một lookup đúng không bảo đảm lời gọi có arguments đúng.

**Method overriding:** khi subclass override method `public`, `getMethod` thường trả về method tương ứng với phiên bản override cụ thể. Khi lớp chỉ kế thừa method và không override, `getDeclaringClass()` chỉ về lớp khai báo ở superclass/interface. Trong bytecode có thể tồn tại bridge methods hoặc những method cùng tên và tham số nhưng return type khác nhau; Reflection có quy tắc lựa chọn riêng, nên với trường hợp compiler sinh bridge hãy kiểm tra metadata thực tế thay vì suy từ một chữ ký Java nguồn đơn giản.

## 4. `getConstructor(Class<?>... parameterTypes)`: tìm constructor `public`

Chữ ký:

```java
Constructor<User> constructor = User.class.getConstructor(String.class);
```

Constructor không có tên phương thức riêng khi tra cứu; chỉ truyền **dãy kiểu tham số**. Nếu constructor không tham số, gọi `getConstructor()`. API này chỉ tìm constructor **`public` do chính lớp đích khai báo**. Constructor của superclass không được kế thừa.

```java
class Account {
    public Account() { }
    public Account(String id) { }
    private Account(int internalCode) { }
}
```

```java
Constructor<Account> a = Account.class.getConstructor();
Constructor<Account> b = Account.class.getConstructor(String.class);
Constructor<Account> internal = Account.class.getDeclaredConstructor(int.class);
```

Đây là đoạn minh họa. `Account.class.getConstructor(int.class)` thất bại vì constructor đó là `private`; `getDeclaredConstructor(int.class)` trả về metadata nhưng không tự cấp quyền gọi.

Tạo đối tượng bằng `Constructor.newInstance`:

```java
Constructor<Account> ctor = Account.class.getConstructor(String.class);
Account instance = ctor.newInstance("A-001");
```

Constructor thực sự chạy ở bước `newInstance`. Nếu class chưa được khởi tạo, JVM khởi tạo class trước khi tạo instance. Việc một class không khai báo constructor trong **mã nguồn** có thể dẫn đến constructor mặc định do compiler sinh, nhưng **mức truy cập của constructor mặc định phụ thuộc mức truy cập của class**. Đừng giả định `getConstructor()` luôn có kết quả: với một số class, không tồn tại constructor không tham số `public`.

Đối với interface, abstract class, array và primitive type, không thể suy rằng có constructor có thể tạo instance theo cách này. `getConstructor(...)` có thể báo không tìm thấy constructor phù hợp; ngay cả khi tìm được constructor của abstract class, `newInstance` vẫn không thể khởi tạo một instance của abstract class.

## 5. Ví dụ Java 17+ hoàn chỉnh: public, kế thừa, overload, constructor

Tạo tệp **`MemberLookupDemo.java`**. Các class lồng nhau được khai báo `static` để ví dụ có thể chạy từ một tệp độc lập:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class MemberLookupDemo {
    public interface Tagged {
        String TAG = "interface-tag";
    }

    public static class Parent {
        public int inherited = 10;

        public String origin() {
            return "Parent.origin";
        }
    }

    public static class Child extends Parent implements Tagged {
        public int own = 20;
        private String secret = "hidden";

        public Child() {
        }

        public Child(String text) {
            own = text.length();
        }

        private Child(int value) {
            own = value;
        }

        public String echo() {
            return "echo:empty";
        }

        public String echo(String text) {
            return "echo:" + text;
        }

        private void hidden() {
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;

        Field inherited = type.getField("inherited");
        Field fromInterface = type.getField("TAG");
        Field own = type.getField("own");

        System.out.println(inherited.getDeclaringClass().getSimpleName());
        System.out.println(fromInterface.getDeclaringClass().getSimpleName());
        System.out.println(own.getDeclaringClass().getSimpleName());

        Method origin = type.getMethod("origin");
        Method echoString = type.getMethod("echo", String.class);
        System.out.println(origin.getDeclaringClass().getSimpleName());
        System.out.println(echoString.getDeclaringClass().getSimpleName());
        System.out.println(type.getMethod("echo").getParameterCount());

        Constructor<Child> empty = type.getConstructor();
        Constructor<Child> withText = type.getConstructor(String.class);
        System.out.println(empty.getParameterCount());

        Child child = withText.newInstance("Java");
        System.out.println(child.own);
        System.out.println(inherited.getInt(child));
        System.out.println(origin.invoke(child));
        System.out.println(echoString.invoke(child, "Reflection"));

        try {
            type.getField("secret");
        } catch (NoSuchFieldException e) {
            System.out.println("secret: not public");
        }
        System.out.println(type.getDeclaredField("secret").getName());

        try {
            type.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("int constructor: not public");
        }
        System.out.println(type.getDeclaredConstructor(int.class).getParameterCount());

        try {
            type.getMethod("hidden");
        } catch (NoSuchMethodException e) {
            System.out.println("hidden: not public");
        }
        System.out.println(type.getDeclaredMethod("hidden").getName());
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac MemberLookupDemo.java
java MemberLookupDemo
```

Stdout:

```text
Parent
Tagged
Child
Parent
Child
0
0
4
10
Parent.origin
echo:Reflection
secret: not public
secret
int constructor: not public
1
hidden: not public
hidden
```

Đối chiếu output:

1. `getField("inherited")` trả `Field` khai báo ở `Parent`; `getField("TAG")` tìm trường `public static final` của interface `Tagged`; `getField("own")` thuộc `Child`. `getDeclaringClass()` giúp xác định **nơi khai báo thực tế**, không nhất thiết là `Class` dùng để tra cứu.
2. `getMethod("origin")` nhận method từ `Parent`; `getMethod("echo", String.class)` nhận method của `Child`. Overload `echo()` có `0` tham số.
3. `getConstructor()` thành công vì `Child` có constructor không tham số `public`. Constructor nhận `String` được gọi với `"Java"`, độ dài 4, nên `own` trở thành `4`.
4. `Field.getInt(child)` đọc trường được kế thừa `inherited = 10`; `Method.invoke` gọi thực sự hai method và nhận về `Parent.origin` cùng `echo:Reflection`.
5. Các thao tác `getField("secret")`, `getConstructor(int.class)`, `getMethod("hidden")` đều thất bại vì thành viên là `private`. Ba thao tác `getDeclared...` tương ứng **tra cứu được metadata**, ngay cả khi thành viên không `public`.
6. Ví dụ **không gọi** thành viên private. Tìm thấy bằng `getDeclared...` và được phép sử dụng bằng Reflection là hai vấn đề khác nhau.

## 6. Khi nào dùng `getDeclared...`?

Có hai câu hỏi khác nhau:

- **“Một caller có thể nhìn thấy những thành viên public nào qua kiểu này?”** → `getField`, `getMethod`, `getConstructor`.
- **“Chính class này đã khai báo những thành viên nào, bao gồm private?”** → `getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`.

Ví dụ, framework ánh xạ thuộc tính có thể cần tìm field `private` được khai báo trong class; bộ kiểm tra hợp đồng API có thể chỉ quan tâm method `public` kể cả được kế thừa.

Không suy ra một thành viên `private` lấy bằng `getDeclaredField` sẽ đọc được ngay:

```java
// Đoạn minh họa: type là một Class<?> đã được xác định.
Field privateField = type.getDeclaredField("secret");
boolean accessible = privateField.trySetAccessible();
if (!accessible) {
    throw new IllegalStateException("Private field is not reflectively accessible");
}
```

`trySetAccessible()` yêu cầu bỏ qua một số kiểm tra access của Java Reflection nếu nền tảng và quan hệ module cho phép; nó có thể trả `false`. Với named modules, việc có `private` metadata **không xóa** cơ chế encapsulation của Java Platform Module System. Trong ứng dụng thực, ưu tiên API public, constructor/factory, hoặc module `opens` có chủ đích khi cần truy cập phản chiếu sâu. Tránh tự động bật quyền cho mọi member.

**Lưu ý về tìm trong superclass:** `getDeclaredField("x")` không tự đi ngược cây kế thừa. Nếu ứng dụng phải tìm cả các trường non-public ở nhiều cấp, nó cần chủ động duyệt `getSuperclass()` và tra cứu `getDeclaredField` tại từng cấp, có quy tắc rõ ràng khi tên bị che khuất. Đây là thao tác khác với `getField`.

## 7. Xử lý thất bại và phân biệt lỗi

| Trường hợp | Exception hoặc hiện tượng | Cách xử lý |
|---|---|---|
| Không có field `public` đúng tên | `NoSuchFieldException` từ `getField` | Kiểm tra tên, nơi khai báo, mức truy cập; cân nhắc `getDeclaredField` nếu cần metadata non-public. |
| Không có method `public` đúng tên + kiểu tham số | `NoSuchMethodException` từ `getMethod` | Kiểm tra overload, `int.class` vs `Integer.class`, kiểu mảng của varargs và erasure generic. |
| Không có constructor `public` đúng dãy kiểu | `NoSuchMethodException` từ `getConstructor` | Kiểm tra constructor khai báo tại chính lớp và mức truy cập. |
| Đã tìm được method nhưng caller không được phép gọi | `IllegalAccessException` từ `Method.invoke` | Xem visibility và module exports/opens; dùng API public hoặc quyền phù hợp. |
| Method/constructor được gọi ném exception | `InvocationTargetException` | Kiểm tra `getCause()` để thấy exception gốc từ code được thực thi. |
| Constructor không thể tạo instance của class abstract | `InstantiationException` khi `newInstance` | Sử dụng concrete implementation có constructor phù hợp. |
| Đối số của `invoke`/`newInstance` không phù hợp | Có thể có `IllegalArgumentException` | So sánh số lượng, kiểu và receiver thực tế với parameter types. |
| Cố vượt giới hạn reflective access của module | Có thể nhận `InaccessibleObjectException` với `setAccessible(true)` | Xem module boundaries; không giả định mọi member đều có thể mở truy cập. |

Ở thời điểm **lookup**, đa số lỗi “không tồn tại đúng chữ ký” là checked exception `NoSuchFieldException`/`NoSuchMethodException`. Ở thời điểm **sử dụng** `Field`, `Method`, `Constructor`, các exception liên quan quyền truy cập, tham số và code thực thi mới quan trọng.

Ví dụ xử lý một method bắt buộc (đoạn code có `Class<?> type` đã xác định):

```java
try {
    Method method = type.getMethod("execute", String.class);
    // Quy trình tiếp theo có thể kiểm tra modifiers và quyền truy cập
    // trước khi gọi method với receiver/argument phù hợp.
} catch (NoSuchMethodException e) {
    throw new IllegalArgumentException(
            "Expected public execute(String) method on " + type.getName(), e);
}
```

Không dùng `catch (Exception)` để che mọi lỗi tra cứu rồi coi như class không hỗ trợ tính năng. Cần phân biệt **không tìm thấy member** với **đã tìm thấy nhưng việc invoke thất bại** để chẩn đoán đúng.

## 8. Các lỗi tư duy phổ biến

1. **“`getDeclaredMethod` bao gồm method kế thừa.”** Sai: `declared` chỉ những method được khai báo trực tiếp trong class/interface này.
2. **“`getConstructor` tự tìm constructor của superclass.”** Sai: constructor không được kế thừa.
3. **“`getMethod` tự chọn overload từ argument sẽ truyền vào sau.”** Sai: cần đưa đúng `Class<?>...` của parameter types **ngay tại lookup**.
4. **“`getField` chỉ tìm trường của chính class hiện tại.”** Sai: có thể tìm field `public` từ superclass/interface.
5. **“Tìm được member private nghĩa là gọi được member private.”** Sai: metadata retrieval và reflective access là hai bước riêng.
6. **“Truyền `Integer.class` sẽ tìm được method khai báo `int`.”** Sai: kiểu trong chữ ký reflection là chính xác, không boxing khi lookup.
7. **“`getMethod("work")` nghĩa là gọi method `work`.”** Sai: chỉ trả về `Method`; gọi bằng `invoke` hoặc Java bình thường.
8. **“`getMethods()[0]` luôn là method đầu tiên trong mã nguồn.”** Sai: API không bảo đảm thứ tự liệt kê.
9. **“Một field có getter nên `getField("name")` tìm được property đó.”** Sai: getter `getName()` là method; Java Reflection cơ bản không tự biến JavaBean property thành field cùng tên.
10. **“Tra cứu constructor không tham số phải viết `getConstructor(null)`.”** Không nên: dùng **`getConstructor()`** để truyền dãy kiểu tham số rỗng, rõ ràng và an toàn với varargs.

## 9. Bài tập tự kiểm tra

**Câu 1.** `Child extends Parent`, `Parent` khai báo `public void show()`, `Child` không override. Tra cứu nào tìm được `show` từ `Child.class`?

**Đáp án:** `Child.class.getMethod("show")` tìm được; `Child.class.getDeclaredMethod("show")` ném `NoSuchMethodException`.

**Câu 2.** `Service` khai báo `public void process(int n)`. Cần gọi `getMethod` với kiểu nào?

**Đáp án:** `Service.class.getMethod("process", int.class)`. `Integer.class` là chữ ký khác.

**Câu 3.** Một `Customer` có `private Customer(String id)`. `Customer.class.getConstructor(String.class)` và `Customer.class.getDeclaredConstructor(String.class)` có cùng kết quả không?

**Đáp án:** Không. Phiên bản không có `Declared` không tìm thấy constructor `private`; phiên bản `Declared` trả về metadata nhưng quyền gọi constructor còn tùy access.

**Câu 4.** Vì sao nên gọi `getDeclaringClass()` trên `Field`/`Method` đã tìm được?

**Đáp án:** Để biết thành viên thực sự được khai báo ở class/interface nào, đặc biệt khi tra cứu qua subclass và có inheritance hoặc field hiding.

**Câu 5.** Có thể tạo object bằng `getConstructor()` không?

**Đáp án:** `getConstructor()` chỉ trả metadata của một constructor `public` không tham số **nếu tồn tại**. Phải gọi `Constructor.newInstance()` để yêu cầu tạo đối tượng, và class phải có khả năng được khởi tạo.

## Tài liệu tra cứu chuẩn

- Java SE API, `java.lang.Class`: `getField`, `getMethod`, `getConstructor`; `getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`.
- Java SE API, `java.lang.reflect.Field`: `get`, `getInt`, `set`, `getDeclaringClass`.
- Java SE API, `java.lang.reflect.Method`: `invoke`, `getParameterTypes`, `isBridge`, `isSynthetic`.
- Java SE API, `java.lang.reflect.Constructor`: `newInstance`, `getParameterTypes`.
- Java Language Specification, phần về inheritance, access control, method signatures và constructor declarations.

**Ghi nhớ:** `getField` tra cứu **field public theo tên**; `getMethod` tra cứu **method public theo tên và tham số**; `getConstructor` tra cứu **constructor public của chính lớp theo tham số**. Thêm `Declared` khi muốn metadata thành viên khai báo trực tiếp bất kể mức truy cập, và luôn phân biệt **lookup** với **truy cập/thực thi**.