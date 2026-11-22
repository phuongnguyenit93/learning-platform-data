# Chuyển `Method`, `Constructor` và `Field` thành handle bằng `unreflect`

## 1. Tại sao cần `unreflect`?

Trong Java, `java.lang.reflect` giúp khám phá cấu trúc lớp tại runtime. `Method`, `Constructor<?>` và `Field` là các đối tượng **metadata** mô tả thành viên; bản thân việc tìm được metadata chưa gọi method, chưa tạo instance và chưa đọc/ghi field.

`java.lang.invoke` cung cấp `MethodHandle` để biểu diễn thao tác gọi có chữ ký xác định và `VarHandle` để truy cập biến qua các access mode. Khi framework đã có metadata reflection (ví dụ sau khi tìm bằng tên, annotation hoặc cấu hình), đối tượng `MethodHandles.Lookup` có thể chuyển metadata ấy thành handle:

| Metadata đầu vào | API của `MethodHandles.Lookup` | Handle nhận được |
| --- | --- | --- |
| `Method` | `unreflect(Method)` | `MethodHandle` gọi method |
| `Constructor<?>` | `unreflectConstructor(Constructor<?>)` | `MethodHandle` tạo instance |
| `Field` cần đọc | `unreflectGetter(Field)` | `MethodHandle` đọc giá trị |
| `Field` cần ghi | `unreflectSetter(Field)` | `MethodHandle` ghi giá trị nếu được phép |
| `Field` cần access mode | `unreflectVarHandle(Field)` | `VarHandle` (Java 9+) |

Không có overload chung `unreflect(Field)`: cần chọn getter, setter hoặc VarHandle theo mục đích. Từ “unreflect” có nghĩa **chuyển biểu diễn reflection thành handle có thể gọi**, không có nghĩa “bỏ kiểm soát quyền truy cập”.

Luồng sử dụng:

```text
Class<?> -> Method / Constructor<?> / Field
                 |
                 v
         MethodHandles.Lookup
                 |
        kiểm tra quyền truy cập
                 |
                 v
     MethodHandle hoặc VarHandle
                 |
                 v
       invokeExact / invoke / get / set ...
```

**Hai thời điểm cần phân biệt:** `lookup.unreflect(method)` tạo handle; `handle.invokeExact(...)` mới chạy method đích. Tương tự `unreflectConstructor` chưa tạo object cho đến lúc handle được gọi.

## 2. Chữ ký của handle và vai trò của receiver

`MethodHandle.type()` trả về `MethodType` mô tả kiểu trả về cùng các kiểu tham số thực tế khi gọi handle. Instance member cần đối tượng nhận lời gọi (**receiver**) ở vị trí tham số đầu tiên; static member không cần receiver. Constructor cũng không cần receiver vì chính nó tạo instance mới.

Giả sử có:

```java
public static class Person {
    public String name;

    public Person(String name) {
        this.name = name;
    }

    public String greet(String prefix) {
        return prefix + ", " + name;
    }

    public static String language() {
        return "Java";
    }
}
```

Đây là đoạn khai báo minh họa, sẽ có một chương trình độc lập hoàn chỉnh ở mục tiếp theo.

| Thành viên | Chữ ký handle sau khi `unreflect` |
| --- | --- |
| `Person.greet(String)` | `(Person, String)String` |
| `Person.language()` static | `()String` |
| `Person(String)` constructor | `(String)Person` |
| Getter của `Person.name` | `(Person)String` |
| Setter của `Person.name` | `(Person, String)void` |

Việc reflection tìm method dùng **chữ ký khai báo** như `getMethod("greet", String.class)`, không có tham số receiver. Ngược lại, khi gọi MethodHandle của method instance, `person` phải là đối số đầu tiên. Setter trả `void`, còn constructor handle trả về instance mới. Với `Field` static, getter không có tham số và setter chỉ nhận giá trị mới.

## 3. Chương trình hoàn chỉnh Java 17+: Method, Constructor, Field

Lưu tệp **`UnreflectDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class UnreflectDemo {
    public static class Person {
        public String name;

        public Person(String name) {
            this.name = name;
        }

        public String greet(String prefix) {
            return prefix + ", " + name;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Constructor<Person> constructor =
                Person.class.getConstructor(String.class);
        Method method = Person.class.getMethod("greet", String.class);
        Field field = Person.class.getField("name");

        MethodHandle create = lookup.unreflectConstructor(constructor);
        MethodHandle greet = lookup.unreflect(method);
        MethodHandle getter = lookup.unreflectGetter(field);
        MethodHandle setter = lookup.unreflectSetter(field);
        VarHandle variable = lookup.unreflectVarHandle(field);

        Person person = (Person) create.invokeExact("Lan");
        System.out.println((String) greet.invokeExact(person, "Xin chào"));

        setter.invokeExact(person, "Mai");
        System.out.println((String) getter.invokeExact(person));

        variable.set(person, "An");
        System.out.println((String) variable.get(person));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac UnreflectDemo.java
java UnreflectDemo
```

Stdout:

```text
Xin chào, Lan
Mai
An
```

Giải thích theo thứ tự:

1. `getConstructor(String.class)`, `getMethod("greet", String.class)` và `getField("name")` lấy metadata **public**. Các lệnh này không chạy constructor hay method.
2. `unreflectConstructor` tạo handle `(String)Person`. Lệnh `create.invokeExact("Lan")` mới tạo `Person` chứa tên `Lan`.
3. `unreflect(method)` tạo handle `(Person, String)String`. `person` là receiver, `"Xin chào"` là tham số khai báo của method.
4. `unreflectGetter(field)` tạo `(Person)String`. `unreflectSetter(field)` tạo `(Person, String)void`. Sau setter, tên của `person` đổi thành `Mai`.
5. `unreflectVarHandle(field)` cũng lấy handle cho field `name`. Gọi `variable.set(person, "An")` rồi `variable.get(person)` khiến dòng cuối in `An`.
6. Ví dụ dùng class, constructor, method và field `public` để hoạt động trên classpath mà không cần mở truy cập private.

`main` khai báo `throws Throwable` vì các lời gọi `MethodHandle.invokeExact` có thể lan truyền lỗi từ thao tác đích. Khi viết sản phẩm, nên xử lý những loại lỗi phù hợp thay vì bỏ qua tất cả.

## 4. `invokeExact`, `invoke` và `MethodType`

`MethodHandle.invokeExact` là phương thức **signature-polymorphic**. Kiểu tham số **và kiểu trả về được kỳ vọng tại vị trí gọi** phải tương thích *chính xác* với `handle.type()`. Trong chương trình trên:

```java
Person person = (Person) create.invokeExact("Lan");
String text = (String) greet.invokeExact(person, "Xin chào");
```

Đây là hai dòng minh họa đặt trong `main` của ví dụ đầy đủ.

Phép ép kiểu `(Person)` và `(String)` không chỉ mang tính trình bày: chúng tạo ngữ cảnh kiểu trả về phù hợp cho `invokeExact`. Nếu cố nhận kết quả constructor thành `Object` trong khi handle trả `Person`, hoặc truyền kiểu `Integer` cho tham số `String`, có thể xảy ra `WrongMethodTypeException`.

`invoke(...)` cho phép một số phép biến đổi kiểu có kiểm tra, theo cơ chế method handle; `asType(...)` dùng để tạo handle đã thích nghi chữ ký khi cần. `invokeWithArguments(...)` phục vụ lời gọi với danh sách đối số động, thuận tiện hơn nhưng thường có thêm chuyển đổi/boxing. Không hình thức nào cho phép biến một tham số không tương thích thành kiểu bất kỳ.

Trong đoạn minh họa khác, static method không cần receiver:

```java
Method m = Math.class.getMethod("abs", int.class);
MethodHandle abs = MethodHandles.lookup().unreflect(m);
int result = (int) abs.invokeExact(-7);  // 7
```

Đoạn này cần đặt trong method có xử lý các checked exception tương ứng và `throws Throwable` cho `invokeExact`. Chữ ký của `abs` là `(int)int`, không phải `(Math, int)int`.

Với method overload, trước khi chuyển đổi phải tìm `Method` mang **đúng các kiểu tham số được khai báo**; `getMethod("f", int.class)` không tự chuyển sang `f(Integer)`. `handle.type()` giúp kiểm tra cấu trúc lời gọi cuối cùng. Với method varargs, handle có thể mang cơ chế variable-arity; nếu cần chữ ký cố định, cân nhắc `asFixedArity()`.

## 5. `unreflect(Method)` khác `Method.invoke` thế nào?

Cả hai đều có thể gọi một method runtime, nhưng mô hình vận hành khác nhau:

| `Method.invoke(receiver, args...)` | `MethodHandle.invokeExact(args...)` |
| --- | --- |
| Gọi qua đối tượng metadata reflection | Gọi qua handle có `MethodType` cụ thể |
| Tham số động theo cơ chế reflection; giá trị trả về thường là `Object` | Receiver (nếu là instance member) nằm ở đầu danh sách tham số của handle |
| Exception do method đích ném được bọc trong `InvocationTargetException` | Exception do code đích ném thường truyền trực tiếp qua handle |
| Xử lý kết quả có thể cần ép kiểu và unboxing | `invokeExact` đòi chữ ký lời gọi chính xác |

Việc chuyển từ `Method` sang `MethodHandle` **không tự đảm bảo nhanh hơn**. Hiệu quả còn phụ thuộc JVM/JIT, khả năng inline, nơi gọi, khối lượng thao tác, warm-up và cách benchmark. Với các đường gọi lặp lại, tránh liên tục `getDeclaredMethod` và `unreflect` nếu có thể tìm một lần, giữ handle và tái sử dụng.

## 6. `unreflectConstructor(Constructor<?>)`: tạo instance từ constructor

Nếu đã tìm đúng constructor:

```java
Constructor<Person> constructor =
        Person.class.getConstructor(String.class);
MethodHandle create =
        MethodHandles.lookup().unreflectConstructor(constructor);
Person person = (Person) create.invokeExact("Lan");
```

Đây là đoạn dựa trên `Person` trong chương trình `UnreflectDemo.java`.

`getConstructor(...)` chỉ tìm constructor `public`. `getDeclaredConstructor(...)` tìm constructor khai báo trực tiếp, kể cả non-public; **tìm được không đồng nghĩa có quyền gọi**. `unreflectConstructor(...)` tạo handle với kiểu trả về là kiểu được khởi tạo, ở đây `Person`, dù constructor trong Java không khai báo kiểu trả về.

Constructor không được kế thừa. Abstract class và interface không thể tạo instance trực tiếp theo cách thông thường; constructor phù hợp có thể vắng mặt hoặc không truy cập được. Việc chuyển handle có thể thất bại vì access, còn thao tác khởi tạo có thể ném exception do constructor đích phát sinh.

Đừng nhầm `Constructor.newInstance(...)` của Reflection với `MethodHandle.invokeExact(...)`. Cả hai có thể tạo instance, nhưng cách truyền đối số/kiểu và cách truyền lỗi khác nhau. `Class.newInstance()` đã deprecated; nên chọn constructor cụ thể và cơ chế xử lý lỗi rõ ràng.

## 7. `unreflectGetter`, `unreflectSetter` và `unreflectVarHandle`

`Field` mô tả trường dữ liệu; API cần chọn theo thao tác:

```java
Field field = Person.class.getField("name");
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.unreflectGetter(field);
MethodHandle setter = lookup.unreflectSetter(field);
VarHandle variable = lookup.unreflectVarHandle(field);
```

Đây là snippet minh họa trên `Person` của chương trình `UnreflectDemo.java`; lời gọi `getField` có thể ném `NoSuchFieldException`, còn unreflect có thể ném `IllegalAccessException`.

**Instance vs static:** getter instance dùng receiver; setter instance dùng receiver và giá trị. Getter static không dùng receiver; setter static chỉ dùng giá trị. Kiểm tra `getter.type()` / `setter.type()` trước khi xây adapter gọi động.

**Final field:** Không suy ra có getter là có setter. Việc tạo setter cho final field có thể bị từ chối tùy quyền truy cập và điều kiện JVM. `VarHandle` đối với final field thường chỉ hỗ trợ mode đọc, và mode ghi có thể ném `UnsupportedOperationException`. Không dùng thủ thuật deep reflection để xây cơ chế cập nhật object bất biến.

**VarHandle và memory ordering:** `VarHandle` có `varType()`, `coordinateTypes()` và các access mode như `get`/`set`, `getVolatile`/`setVolatile` hay `compareAndSet` nếu hỗ trợ. Không coi mode thông thường mặc nhiên là volatile hoặc atomic. Có thể kiểm tra `isAccessModeSupported(...)`; một mode không hỗ trợ đối với kiểu field nhất định sẽ gây lỗi khi gọi.

`VarHandle` phù hợp với thao tác trên biến có nhu cầu rõ về access mode và concurrency. `unreflectGetter`/`unreflectSetter` phù hợp khi chỉ cần handle đọc/ghi với `MethodType` cụ thể.

## 8. Quyền truy cập của `Lookup`, private member và JPMS

`MethodHandles.lookup()` tạo `Lookup` mang quyền truy cập theo **lớp gọi**; `publicLookup()` hạn chế hơn. `unreflect*` vẫn kiểm tra quyền phù hợp với member và `Lookup`. Ví dụ `getDeclaredField("secret")` có thể trả `Field` của field private, nhưng `lookup.unreflectGetter(field)` có thể ném `IllegalAccessException` nếu không có quyền truy cập.

Khi thực sự cần deep access, `MethodHandles.privateLookupIn(Target.class, callerLookup)` có thể tạo `Lookup` với quyền private phù hợp nếu các điều kiện được đáp ứng. Trên Java 17+, JPMS còn yêu cầu module đích mở package thích hợp cho module gọi khi khác module: `exports` không thay thế `opens`. Nên cấp quyền tối thiểu cần thiết.

Ví dụ độc lập sau dùng cùng nest và cùng module để minh họa truy cập private hợp lệ. Tạo **`PrivateLookupDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class PrivateLookupDemo {
    private static class Vault {
        private String secret;

        private Vault(String secret) {
            this.secret = secret;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup =
                MethodHandles.privateLookupIn(
                        Vault.class, MethodHandles.lookup());

        Constructor<Vault> constructor =
                Vault.class.getDeclaredConstructor(String.class);
        Field field = Vault.class.getDeclaredField("secret");

        MethodHandle create = lookup.unreflectConstructor(constructor);
        MethodHandle read = lookup.unreflectGetter(field);

        Vault vault = (Vault) create.invokeExact("đã bảo vệ");
        System.out.println((String) read.invokeExact(vault));
    }
}
```

```bash
javac PrivateLookupDemo.java
java PrivateLookupDemo
```

Stdout:

```text
đã bảo vệ
```

`privateLookupIn` trong ví dụ không phải đường tắt vượt quyền: do `Vault` nằm trong cùng nest, caller có quyền cần thiết. Với class ở module khác, package phải mở hợp lệ; nếu thiếu quyền, lời gọi có thể bị từ chối.

Ví dụ khai báo module **minh họa**, không phải chương trình chạy độc lập:

```java
module com.example.domain {
    opens com.example.domain.model to com.example.framework;
}
```

Trong trường hợp này, module `com.example.domain` mở package nêu trên cho module `com.example.framework`, ngoài các điều kiện lookup/module khác. Tránh mở toàn bộ module chỉ để xử lý một field.

`Method`/`Field` còn có `trySetAccessible()` và `setAccessible(true)`. Accessibility override có thể ảnh hưởng cách `unreflect` kiểm tra member, nhưng vẫn tuân thủ JPMS và các ràng buộc đặc biệt như final field; không nên giả định rằng `setAccessible(true)` luôn thành công hoặc biến mọi private member thành public.

## 9. Lỗi và cách xử lý

| Giai đoạn | Lỗi thường gặp | Cách nhận biết |
| --- | --- | --- |
| Tìm `Method`/constructor | Tên hoặc signature sai | `NoSuchMethodException` |
| Tìm `Field` | Tên field sai | `NoSuchFieldException` |
| Chuyển metadata | Lookup thiếu quyền | `IllegalAccessException` |
| Gọi handle | Sai chữ ký mong đợi | `WrongMethodTypeException` |
| Gọi handle | Receiver/ép kiểu không tương thích | Có thể có `ClassCastException` hoặc lỗi runtime tương ứng |
| Gọi method/constructor đích | Code đích ném exception | Lỗi đích có thể được truyền trực tiếp |
| Dùng `VarHandle` | Access mode không hỗ trợ | `UnsupportedOperationException` |
| Deep reflection qua `setAccessible` | Bị module từ chối | Có thể gặp `InaccessibleObjectException` |

Không nên dùng `catch (Exception ignored)` quanh toàn bộ pipeline. `invokeExact` có thể truyền `Throwable` từ code đích. Khi xử lý, phân biệt lỗi **tìm thành viên**, lỗi **liên kết handle** và lỗi **thực thi**; ghi ngữ cảnh tên method, kiểu tham số, class loader và module khi chẩn đoán.

Ba nhầm lẫn phổ biến:

1. “Tìm được `Method` thì `unreflect` luôn thành công.” Sai, vì `Lookup` còn phải có quyền.
2. “`invokeExact` giống `Method.invoke`, truyền `Object[]` bất kỳ.” Sai, vì chữ ký phải khớp `MethodType`.
3. “`unreflectGetter(field)` sẽ đọc field ngay.” Sai, vì thao tác thật xảy ra khi gọi handle.

## 10. Chọn `unreflect` hay `findVirtual`/`findStatic`?

`unreflect` thích hợp khi đã có metadata `Method`, `Constructor` hoặc `Field`, ví dụ framework scan annotation hoặc chọn member động từ cấu hình. Nếu đã biết tên, kiểu và muốn handle trực tiếp, `Lookup` có những hàm như `findVirtual`, `findStatic`, `findConstructor`, `findGetter` và `findSetter`.

Ví dụ minh họa với class `Person` của `UnreflectDemo.java`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle direct = lookup.findVirtual(
        Person.class,
        "greet",
        java.lang.invoke.MethodType.methodType(
                String.class, String.class));
```

`direct` cũng biểu diễn handle dạng `(Person, String)String`. Hai cách tiếp cận vẫn chịu kiểm tra quyền. Khi dùng nhiều lần, có thể cache handle thích hợp; lưu ý cache giữ `Class<?>` lâu dài có thể giữ class loader của plugin. Kiểm chứng lợi ích hiệu năng bằng benchmark có warm-up và workload thật; không khẳng định mọi lời gọi method handle nhanh hơn reflection.

## 11. Quy trình thực hành và tự kiểm tra

1. Xác định member đúng tên/chữ ký, biết đó là instance hay static và dùng loader/module nào.
2. Chọn `Lookup` với quyền cần thiết; nếu gặp non-public thì kiểm tra `privateLookupIn` và `opens`.
3. Dùng đúng `unreflect*` theo `Method`/`Constructor`/`Field` và nhu cầu đọc/ghi.
4. Xem `MethodHandle.type()` hoặc `VarHandle.varType()` / `coordinateTypes()` để biết chính xác đối số.
5. Gọi handle khi cần thao tác; dùng `invokeExact` với kiểu cố định, `invoke` nếu phép thích nghi hợp lệ là có chủ đích.
6. Xử lý lỗi lookup khác lỗi code đích, cân nhắc tái sử dụng handle và đo hiệu năng trước khi tối ưu.

Tự kiểm tra:

- Vì sao `unreflect(Method)` không làm method chạy ngay?
- Với instance method nhận một `String`, vì sao handle cần thêm receiver?
- `unreflectConstructor` tạo handle hay tạo instance? Instance được tạo vào lúc nào?
- Muốn đọc/ghi một `Field` thì dùng API nào? Khác nhau thế nào với `VarHandle`?
- Vì sao `getDeclaredField` có thể thành công nhưng `unreflectGetter` thất bại?
- `invokeExact` khác `invoke` ở đâu và vì sao các ví dụ ép kiểu kết quả?
- `exports` trong JPMS đã đủ cho deep reflection vào private field chưa?

**Ghi nhớ:** Reflection cung cấp metadata của thành viên; `MethodHandles.Lookup.unreflect*` chuyển metadata ấy thành handle với quyền truy cập tương ứng. Handle chỉ thực hiện thao tác khi được gọi, theo đúng chữ ký, receiver và access mode.